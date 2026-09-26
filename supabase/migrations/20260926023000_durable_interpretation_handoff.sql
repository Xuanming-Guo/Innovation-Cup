-- Repair the explicit durable interpretation handoff without broadening runtime roles.

create or replace function app.ensure_durable_job(
  p_company_id uuid,
  p_job_kind text,
  p_aggregate_id uuid,
  p_idempotency_key text,
  p_command_digest bytea,
  p_correlation_id uuid
)
returns table (
  job_id uuid, job_kind text, aggregate_id uuid, state text,
  attempt_count integer, max_attempts integer, available_at timestamptz,
  leased_until timestamptz, cancellation_requested boolean,
  last_error_code text, created_at timestamptz, completed_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
  v_payload jsonb;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id()
     or not app.can_manage_planning(p_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'manager_authority_required';
  end if;
  if p_job_kind <> 'interpretation.run'
     or not exists (select 1 from app.planning_requests as request
       where request.company_id = p_company_id and request.id = p_aggregate_id) then
    raise exception using errcode = '22023', message = 'job_target_invalid';
  end if;
  select membership.id into v_membership_id
  from app.company_memberships as membership
  where membership.company_id = p_company_id
    and membership.user_id = app.current_actor_id()
    and membership.membership_status = 'active';
  v_payload := jsonb_build_object('request_id', p_aggregate_id);
  insert into app.durable_jobs (
    company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
    idempotency_key, command_digest, correlation_id
  ) values (
    p_company_id, p_job_kind, p_aggregate_id, v_payload, v_membership_id,
    p_idempotency_key, p_command_digest, p_correlation_id
  ) on conflict on constraint durable_jobs_company_id_job_kind_aggregate_id_key
    do nothing;
  return query
  select job.id, job.job_kind, job.aggregate_id, job.state, job.attempt_count,
    job.max_attempts, job.available_at, job.leased_until,
    job.cancel_requested_at is not null, job.last_error_code,
    job.created_at, job.completed_at
  from app.durable_jobs as job
  where job.company_id = p_company_id and job.job_kind = p_job_kind
    and job.aggregate_id = p_aggregate_id;
end
$$;

revoke execute on function app.ensure_durable_job(
  uuid, text, uuid, text, bytea, uuid
) from public, anon, authenticated, service_role, coordination_worker;
grant execute on function app.ensure_durable_job(
  uuid, text, uuid, text, bytea, uuid
) to coordination_api;

-- Deleting assignments fires workload refresh. Remove assignments first, then remove the
-- refreshed workload rows before the legacy guarded reset deletes employee profiles.
create or replace function app_private.reset_demo_company(p_company_id uuid)
returns void
language plpgsql
security definer
set search_path = pg_catalog, app, app_private, vault
as $$
declare
  v_secret_id uuid;
begin
  if not exists (
    select 1 from app.companies where id = p_company_id and is_demo is true
  ) then
    raise exception 'demo reset refused for non-demo or unknown company'
      using errcode = '42501';
  end if;

  delete from app.company_ai_provider_configurations
  where company_id = p_company_id
  returning vault_secret_id into v_secret_id;
  if v_secret_id is not null then
    delete from vault.secrets where id = v_secret_id;
  end if;

  delete from app.work_assignments where company_id = p_company_id;
  delete from app.employee_workload_state where company_id = p_company_id;
  perform app_private.reset_demo_company_without_ai_provider(p_company_id);
end
$$;

revoke execute on function app_private.reset_demo_company(uuid)
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;

-- Queue age uses clock_timestamp(), so the metrics routine is intentionally volatile.
alter function app.company_durable_metrics(uuid) volatile;

insert into app_private.migration_contract (version, name)
values ('20260926023000', 'durable_interpretation_handoff');
