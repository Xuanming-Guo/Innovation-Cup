-- Let a manager explicitly continue a saved Live fixed-plan repair for two more
-- candidate versions. Existing candidates and failed verifier results remain immutable.

alter table app.ai_plan_proposals
  drop constraint ai_plan_proposals_version_check;

alter table app.ai_plan_proposals
  add constraint ai_plan_proposals_version_check
  check (version between 1 and 5);

create or replace function app.retry_durable_planning_job(
  p_company_id uuid,
  p_job_id uuid,
  p_reason text,
  p_idempotency_key text,
  p_command_digest bytea
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
  v_job app.durable_jobs%rowtype;
  v_membership_id uuid;
  v_existing app.durable_job_recoveries%rowtype;
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id()
     or not app.can_manage_planning(p_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'manager_authority_required';
  end if;
  if p_reason is null or length(btrim(p_reason)) not between 1 and 500
     or p_idempotency_key is null or length(p_idempotency_key) not between 16 and 128
     or p_command_digest is null or octet_length(p_command_digest) <> 32 then
    raise exception using errcode = '22023', message = 'job_retry_invalid';
  end if;

  select membership.id into strict v_membership_id
  from app.company_memberships as membership
  where membership.company_id = p_company_id
    and membership.user_id = app.current_actor_id()
    and membership.membership_status = 'active';

  select recovery.* into v_existing
  from app.durable_job_recoveries as recovery
  where recovery.company_id = p_company_id
    and recovery.idempotency_key = p_idempotency_key;
  if found then
    if v_existing.job_id <> p_job_id
       or v_existing.command_digest <> p_command_digest then
      raise exception using errcode = '40001', message = 'job_retry_idempotency_conflict';
    end if;
    return query
    select job.id, job.job_kind, job.aggregate_id, job.state, job.attempt_count,
      job.max_attempts, job.available_at, job.leased_until,
      job.cancel_requested_at is not null, job.last_error_code,
      job.created_at, job.completed_at
    from app.durable_jobs as job
    where job.company_id = p_company_id and job.id = p_job_id;
    return;
  end if;

  select job.* into v_job
  from app.durable_jobs as job
  where job.company_id = p_company_id and job.id = p_job_id
  for update;
  if not found then
    raise exception using errcode = '22023', message = 'job_not_found';
  end if;
  if v_job.job_kind not in (
       'interpretation.run', 'planning.materialize', 'planning.run', 'plan.propose'
     )
     or v_job.state not in ('dead_letter', 'review_required')
     or v_job.attempt_count >= 20 then
    raise exception using errcode = '40001', message = 'job_retry_not_permitted';
  end if;
  if v_job.job_kind = 'plan.propose'
     and (
       v_job.last_error_code is distinct from 'fixed_plan_not_verified'
       or (
         select count(*)
         from app.ai_plan_proposals as proposal
         where proposal.company_id = p_company_id
           and proposal.snapshot_id = v_job.aggregate_id
           and proposal.author_kind = 'ai_authored'
       ) >= 5
     ) then
    raise exception using errcode = '40001', message = 'job_retry_not_permitted';
  end if;

  insert into app.durable_job_recoveries (
    company_id, job_id, requested_by_membership_id, prior_state, prior_error_code,
    reason, idempotency_key, command_digest
  ) values (
    p_company_id, p_job_id, v_membership_id, v_job.state, v_job.last_error_code,
    btrim(p_reason), p_idempotency_key, p_command_digest
  );

  update app.durable_jobs as job
  set state = 'queued',
      max_attempts = least(20, greatest(job.max_attempts, job.attempt_count + 6)),
      available_at = clock_timestamp(),
      lease_owner = null, lease_token = null, leased_at = null, leased_until = null,
      result = null, result_digest = null,
      last_error_code = null, last_error_message = null,
      completed_at = null, row_version = row_version + 1
  where job.company_id = p_company_id and job.id = p_job_id;

  return query
  select job.id, job.job_kind, job.aggregate_id, job.state, job.attempt_count,
    job.max_attempts, job.available_at, job.leased_until,
    job.cancel_requested_at is not null, job.last_error_code,
    job.created_at, job.completed_at
  from app.durable_jobs as job
  where job.company_id = p_company_id and job.id = p_job_id;
end
$$;

revoke execute on function app.retry_durable_planning_job(
  uuid, uuid, text, text, bytea
) from public, anon, authenticated, service_role, coordination_worker;
grant execute on function app.retry_durable_planning_job(
  uuid, uuid, text, text, bytea
) to coordination_api;

insert into app_private.migration_contract(version, name)
values ('20260927038000', 'alto_bounded_live_plan_revision');
