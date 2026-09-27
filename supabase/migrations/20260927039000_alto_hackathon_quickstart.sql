-- Locked hackathon access: operator-managed Vertex defaults and safe immutable run bindings.
create table app.demo_operator_provider_defaults (
  company_id uuid primary key references app.companies(id),
  profile_version_id uuid not null,
  credential_owner_membership_id uuid not null,
  enabled boolean not null default true,
  configured_at timestamptz not null default clock_timestamp(),
  disabled_at timestamptz,
  foreign key(company_id,profile_version_id)
    references app.demo_provider_profile_versions(company_id,id),
  foreign key(company_id,credential_owner_membership_id)
    references app.company_memberships(company_id,id),
  check ((enabled and disabled_at is null) or (not enabled and disabled_at is not null))
);

alter table app.demo_run_provider_bindings
  add column binding_source text not null default 'visitor_owned'
    check (binding_source in ('visitor_owned','operator_default'));

alter table app.demo_operator_provider_defaults enable row level security;
revoke all on app.demo_operator_provider_defaults
  from public,anon,authenticated,service_role,coordination_api,coordination_worker;

create function app.bind_demo_operator_provider(
  p_company_id uuid,
  p_run_id uuid,
  p_validated_model text
) returns uuid
language plpgsql security definer set search_path=pg_catalog,app as $$
declare
  member_id uuid;
  existing app.demo_run_provider_bindings%rowtype;
  default_version uuid;
begin
  if not app.request_context_present() or p_company_id<>app.current_company_id()
    or not app.can_access_demo_run(p_company_id,p_run_id,app.current_actor_id(),true)
    or not exists(select 1 from app.demo_runs r where r.company_id=p_company_id
      and r.id=p_run_id and r.mode='live' and r.state='active')
    or not exists(select 1 from app.demo_workspace_policies policy
      join app.companies company on company.id=policy.company_id
      where policy.company_id=p_company_id and policy.enabled and company.is_demo
        and company.status='active') then
    raise exception using errcode='42501',message='hackathon_demo_access_denied';
  end if;

  select * into existing from app.demo_run_provider_bindings
    where company_id=p_company_id and run_id=p_run_id;
  if found then
    if existing.binding_source<>'operator_default'
      or not exists(select 1 from app.demo_operator_provider_defaults d
        where d.company_id=p_company_id and d.enabled)
      or not exists(select 1 from app.demo_provider_profile_versions v
        join app.demo_provider_profiles p on p.company_id=v.company_id and p.id=v.profile_id
        where v.company_id=p_company_id and v.id=existing.profile_version_id
          and v.provider='vertex_ai' and v.credential_kind='vertex_service_account'
          and v.validation_status='validated' and v.validated_model=p_validated_model
          and v.revoked_at is null and p.status='active') then
      raise exception using errcode='P0001',message='hackathon_demo_ai_unavailable';
    end if;
    return existing.profile_version_id;
  end if;

  select d.profile_version_id into default_version
  from app.demo_operator_provider_defaults d
  join app.demo_provider_profile_versions v
    on v.company_id=d.company_id and v.id=d.profile_version_id
  join app.demo_provider_profiles p
    on p.company_id=v.company_id and p.id=v.profile_id
  where d.company_id=p_company_id and d.enabled
    and v.provider='vertex_ai' and v.credential_kind='vertex_service_account'
    and v.validation_status='validated' and v.validated_model=p_validated_model
    and v.revoked_at is null and p.status='active';
  if default_version is null then
    raise exception using errcode='P0001',message='hackathon_demo_ai_unavailable';
  end if;

  select id into strict member_id from app.company_memberships
    where company_id=p_company_id and user_id=app.current_actor_id()
      and membership_status='active';
  insert into app.demo_run_provider_bindings(
    company_id,run_id,profile_version_id,bound_by,binding_source
  ) values(p_company_id,p_run_id,default_version,member_id,'operator_default');
  return default_version;
end $$;

create or replace function app.resolve_company_ai_credential() returns table(
  provider text,credential_kind text,credential_secret text,validated_model text,
  vertex_project_id text,vertex_client_email text,vertex_location text
)
language plpgsql security definer set search_path=pg_catalog,app,vault as $$
begin
  if app.current_demo_run_id() is null then
    return query select * from app.resolve_ordinary_company_ai_credential();
    return;
  end if;
  perform app.assert_alto_job_lease(app.current_company_id(),
    nullif(current_setting('app.job_id',true),'')::uuid,
    nullif(current_setting('app.lease_token',true),'')::uuid);
  return query select v.provider,v.credential_kind,s.decrypted_secret,v.validated_model,
    v.vertex_project_id,v.vertex_client_email,v.vertex_location
  from app.demo_run_provider_bindings b
  join app.demo_runs r on r.company_id=b.company_id and r.id=b.run_id
  join app.demo_provider_profile_versions v
    on v.company_id=b.company_id and v.id=b.profile_version_id
  join app.demo_provider_profiles p on p.company_id=v.company_id and p.id=v.profile_id
  join vault.decrypted_secrets s on s.id=v.vault_secret_id
  where b.company_id=app.current_company_id() and b.run_id=app.current_demo_run_id()
    and r.state='active' and r.mode='live' and v.revoked_at is null
    and v.validation_status='validated' and p.status='active'
    and app.scope_access(r.company_id,r.id,true)
    and (
      (b.binding_source='visitor_owned' and p.owner_membership_id=r.owner_membership_id)
      or (b.binding_source='operator_default' and exists(
        select 1 from app.demo_operator_provider_defaults d
        join app.demo_workspace_policies policy on policy.company_id=d.company_id
        where d.company_id=b.company_id and d.enabled and policy.enabled
      ))
    );
  if not found then
    raise exception using errcode='P0002',message='demo_provider_not_bound';
  end if;
end $$;

create or replace function app.get_demo_provider_binding() returns jsonb
language plpgsql stable security definer set search_path=pg_catalog,app as $$
declare value jsonb;
begin
  select jsonb_build_object(
      'provider',v.provider,
      'credential_kind',v.credential_kind,
      'management_mode','operator_managed',
      'can_manage',false,
      'status',case when v.revoked_at is null and p.status='active'
        and exists(select 1 from app.demo_operator_provider_defaults d
          where d.company_id=b.company_id and d.enabled)
        then 'configured' else 'unavailable' end
    ) into value
  from app.demo_run_provider_bindings b
  join app.demo_provider_profile_versions v
    on v.company_id=b.company_id and v.id=b.profile_version_id
  join app.demo_provider_profiles p on p.company_id=v.company_id and p.id=v.profile_id
  join app.demo_runs r on r.company_id=b.company_id and r.id=b.run_id
  where b.company_id=app.current_company_id() and b.run_id=app.current_demo_run_id()
    and b.binding_source='operator_default'
    and app.can_access_demo_run(b.company_id,b.run_id,app.current_actor_id());
  if value is not null then return value; end if;

  select jsonb_build_object(
    'profile_id',p.id,
    'current_profile_version_id',b.profile_version_id,
    'latest_profile_version_id',v.id,
    'version',v.version,
    'credential_hint',v.credential_hint,
    'provider',v.provider,
    'credential_kind',v.credential_kind,
    'management_mode','visitor_owned',
    'can_manage',true,
    'status',case when v.revoked_at is null then 'configured' else 'revoked' end
  ) into value
  from app.demo_provider_profiles p
  join app.company_memberships m
    on m.company_id=p.company_id and m.id=p.owner_membership_id
  join lateral(
    select version.* from app.demo_provider_profile_versions version
    where version.company_id=p.company_id and version.profile_id=p.id
    order by version.version desc limit 1
  ) v on true
  left join app.demo_run_provider_bindings b
    on b.company_id=p.company_id and b.run_id=app.current_demo_run_id()
      and b.binding_source='visitor_owned'
  where p.company_id=app.current_company_id() and m.user_id=app.current_actor_id()
    and m.membership_status='active';
  return value;
end $$;

revoke all on function app.bind_demo_operator_provider(uuid,uuid,text),
  app.resolve_company_ai_credential(),app.get_demo_provider_binding() from public;
grant execute on function app.bind_demo_operator_provider(uuid,uuid,text),
  app.get_demo_provider_binding() to coordination_api;
grant execute on function app.resolve_company_ai_credential() to coordination_worker;

insert into app_private.migration_contract(version,name)
values ('20260927039000','alto_hackathon_quickstart');
