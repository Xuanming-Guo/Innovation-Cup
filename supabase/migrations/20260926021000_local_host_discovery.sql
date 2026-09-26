-- Lease-based discovery for the single-laptop hosted-demo runtime.
-- Applied migrations are immutable; corrections use a later timestamped migration.

create table app.host_runtime_endpoints (
  company_id uuid primary key references app.companies(id) on delete cascade,
  instance_id uuid not null,
  api_origin text not null check (
    length(api_origin) between 12 and 300
    and api_origin = lower(api_origin)
    and api_origin ~ '^https://[a-z0-9][a-z0-9.-]*[a-z0-9](:[0-9]{1,5})?$'
    and position('..' in api_origin) = 0
  ),
  build_commit text not null check (build_commit ~ '^[0-9a-f]{40}$'),
  registered_at timestamptz not null,
  last_heartbeat_at timestamptz not null,
  expires_at timestamptz not null,
  check (expires_at > last_heartbeat_at)
);

alter table app.host_runtime_endpoints enable row level security;
revoke all on table app.host_runtime_endpoints
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;

create or replace function app.heartbeat_host_runtime_endpoint(
  p_company_id uuid,
  p_instance_id uuid,
  p_api_origin text,
  p_build_commit text,
  p_ttl_seconds integer
)
returns table (api_origin text, expires_at timestamptz)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_now timestamptz := clock_timestamp();
begin
  if p_company_id is null or p_instance_id is null then
    raise exception 'company and host instance are required' using errcode = '22023';
  end if;
  if not app.request_context_present()
     or app.current_company_id() <> p_company_id
     or not app.is_company_admin(p_company_id, app.current_actor_id()) then
    raise exception 'company administrator host context is required'
      using errcode = '42501';
  end if;
  if p_ttl_seconds not between 60 and 300 then
    raise exception 'host endpoint TTL must be between 60 and 300 seconds'
      using errcode = '22023';
  end if;
  if p_api_origin is null
     or length(p_api_origin) not between 12 and 300
     or p_api_origin <> lower(p_api_origin)
     or p_api_origin !~ '^https://[a-z0-9][a-z0-9.-]*[a-z0-9](:[0-9]{1,5})?$'
     or position('..' in p_api_origin) <> 0 then
    raise exception 'host API origin must be one canonical HTTPS origin'
      using errcode = '22023';
  end if;
  if p_build_commit is null or p_build_commit !~ '^[0-9a-f]{40}$' then
    raise exception 'host build commit must be a full lowercase Git commit'
      using errcode = '22023';
  end if;
  if not exists (
    select 1 from app.companies
    where id = p_company_id and status = 'active'
  ) then
    raise exception 'active company was not found' using errcode = 'P0002';
  end if;

  return query
  insert into app.host_runtime_endpoints as endpoint (
    company_id,
    instance_id,
    api_origin,
    build_commit,
    registered_at,
    last_heartbeat_at,
    expires_at
  ) values (
    p_company_id,
    p_instance_id,
    p_api_origin,
    p_build_commit,
    v_now,
    v_now,
    v_now + make_interval(secs => p_ttl_seconds)
  )
  on conflict (company_id) do update
  set instance_id = excluded.instance_id,
      api_origin = excluded.api_origin,
      build_commit = excluded.build_commit,
      registered_at = case
        when endpoint.instance_id = excluded.instance_id then endpoint.registered_at
        else excluded.registered_at
      end,
      last_heartbeat_at = excluded.last_heartbeat_at,
      expires_at = excluded.expires_at
  where endpoint.instance_id = excluded.instance_id
     or endpoint.expires_at <= v_now
  returning endpoint.api_origin, endpoint.expires_at;

  if not found then
    raise exception 'another host holds the active company lease' using errcode = '55006';
  end if;
end
$$;

create or replace function app.release_host_runtime_endpoint(
  p_company_id uuid,
  p_instance_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if not app.request_context_present()
     or app.current_company_id() <> p_company_id
     or not app.is_company_admin(p_company_id, app.current_actor_id()) then
    raise exception 'company administrator host context is required'
      using errcode = '42501';
  end if;
  delete from app.host_runtime_endpoints
  where company_id = p_company_id
    and instance_id = p_instance_id;
  return found;
end
$$;

create or replace function public.resolve_coordination_host(p_company_id uuid)
returns text
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select endpoint.api_origin
  from app.host_runtime_endpoints as endpoint
  where endpoint.company_id = p_company_id
    and endpoint.expires_at > statement_timestamp()
    and app.has_active_membership(p_company_id, auth.uid())
$$;

revoke execute on function app.heartbeat_host_runtime_endpoint(uuid, uuid, text, text, integer)
  from public, anon, authenticated, service_role, coordination_worker;
revoke execute on function app.release_host_runtime_endpoint(uuid, uuid)
  from public, anon, authenticated, service_role, coordination_worker;
grant execute on function app.heartbeat_host_runtime_endpoint(uuid, uuid, text, text, integer)
  to coordination_api;
grant execute on function app.release_host_runtime_endpoint(uuid, uuid)
  to coordination_api;

revoke execute on function public.resolve_coordination_host(uuid)
  from public, anon, service_role, coordination_api, coordination_worker;
grant execute on function public.resolve_coordination_host(uuid) to authenticated;

insert into app_private.migration_contract (version, name)
values ('20260926021000', 'local_host_discovery');
