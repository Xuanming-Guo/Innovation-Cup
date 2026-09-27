-- Recover side-effect-free planning stages deliberately, and repair employee notification
-- delivery without broadening either runtime role.

create table app.durable_job_recoveries (
  id uuid primary key default extensions.gen_random_uuid(),
  company_id uuid not null,
  job_id uuid not null,
  requested_by_membership_id uuid not null,
  prior_state text not null check (prior_state in ('dead_letter', 'review_required')),
  prior_error_code text null check (
    prior_error_code is null or length(prior_error_code) between 1 and 120
  ),
  reason text not null check (length(btrim(reason)) between 1 and 500),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, idempotency_key),
  foreign key (company_id, job_id)
    references app.durable_jobs(company_id, id) on delete cascade,
  foreign key (company_id, requested_by_membership_id)
    references app.company_memberships(company_id, id)
);

alter table app.durable_job_recoveries enable row level security;
revoke all on table app.durable_job_recoveries
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;

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
  if v_job.job_kind not in ('interpretation.run', 'planning.materialize', 'planning.run')
     or v_job.state not in ('dead_letter', 'review_required')
     or v_job.attempt_count >= 20 then
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

create or replace function app.can_read_notification(
  p_company_id uuid,
  p_user_id uuid,
  p_notification_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.notifications as notification
    join app.company_memberships as membership
      on membership.company_id = notification.company_id
     and membership.id = notification.recipient_membership_id
     and membership.user_id = p_user_id
     and membership.membership_status = 'active'
    where notification.company_id = p_company_id
      and notification.id = p_notification_id
      and (
        (notification.subject_type = 'task'
          and app.can_read_task(p_user_id, p_company_id, notification.subject_id))
        or (notification.subject_type = 'plan'
          and app.can_read_plan(p_company_id, p_user_id, notification.subject_id))
        or (notification.subject_type = 'employee_brief'
          and app.can_read_employee_brief(
            p_user_id, p_company_id, notification.subject_id
          ))
      )
  )
$$;

create or replace function app.deliver_internal_outbox_intent(
  p_company_id uuid,
  p_intent_id uuid,
  p_job_id uuid,
  p_lease_token uuid
)
returns table (notification_count integer, replayed boolean)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_intent app.outbox_intents%rowtype;
  v_membership record;
  v_subject_type text;
  v_subject_id uuid;
  v_message_key text;
  v_count integer := 0;
begin
  if not exists (select 1 from app.durable_jobs
    where company_id = p_company_id and id = p_job_id
      and job_kind = 'outbox.deliver' and aggregate_id = p_intent_id
      and state = 'leased' and lease_token = p_lease_token
      and leased_until > clock_timestamp()) then
    raise exception using errcode = '40001', message = 'outbox_job_lease_invalid';
  end if;
  select * into v_intent from app.outbox_intents
  where company_id = p_company_id and id = p_intent_id for update;
  if not found then
    raise exception using errcode = '22023', message = 'outbox_intent_missing';
  end if;
  if v_intent.state = 'delivered' then
    notification_count := coalesce((v_intent.delivery_result ->> 'notification_count')::integer, 0);
    replayed := true; return next; return;
  end if;

  if v_intent.intent_kind = 'task.changed' then
    v_subject_type := 'task';
    v_subject_id := coalesce((v_intent.payload ->> 'task_id')::uuid, v_intent.aggregate_id);
    v_message_key := 'task_state_changed';
  elsif v_intent.intent_kind = 'employee_brief.publish' then
    v_subject_type := 'employee_brief';
    v_subject_id := v_intent.aggregate_id;
    v_message_key := 'employee_brief_changed';
  elsif v_intent.intent_kind = 'approval.changed' then
    v_subject_type := 'plan'; v_subject_id := v_intent.aggregate_id;
    v_message_key := 'approval_state_changed';
  else
    v_subject_type := 'plan'; v_subject_id := v_intent.aggregate_id;
    v_message_key := 'plan_state_changed';
  end if;

  for v_membership in
    select membership.id, membership.user_id
    from app.company_memberships as membership
    where membership.company_id = p_company_id
      and membership.membership_status = 'active'
      and (
        (v_subject_type = 'task'
          and app.can_read_task(membership.user_id, p_company_id, v_subject_id))
        or (v_subject_type = 'plan'
          and app.can_read_plan(p_company_id, membership.user_id, v_subject_id))
        or (v_subject_type = 'employee_brief'
          and app.can_read_employee_brief(membership.user_id, p_company_id, v_subject_id))
      )
  loop
    insert into app.notifications (
      company_id, recipient_membership_id, origin_outbox_intent_id,
      idempotency_key, message_key, subject_type, subject_id
    ) values (
      p_company_id, v_membership.id, p_intent_id,
      'notification:' || p_intent_id::text || ':' || v_membership.id::text,
      v_message_key, v_subject_type, v_subject_id
    ) on conflict (company_id, recipient_membership_id, idempotency_key) do nothing;
    if found then v_count := v_count + 1; end if;
  end loop;
  update app.outbox_intents
  set state = 'delivered', processed_at = clock_timestamp(),
      lease_owner = null, lease_token = null, leased_until = null,
      delivery_result = jsonb_build_object('notification_count', v_count),
      last_error_code = null, last_error = null
  where company_id = p_company_id and id = p_intent_id;
  notification_count := v_count; replayed := false; return next;
end
$$;

create or replace function app.enqueue_committed_assignment_notification()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if new.active and new.assignment_role = 'owner' then
    insert into app.outbox_intents (
      company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id
    ) values (
      new.company_id, 'task.changed', 'task', new.task_id,
      jsonb_build_object('task_id', new.task_id, 'event', 'assigned'),
      extensions.gen_random_uuid()
    ) on conflict (company_id, idempotency_key) do nothing;
  end if;
  return new;
end
$$;

create trigger work_assignment_notify_employee
  after insert on app.work_assignments
  for each row execute function app.enqueue_committed_assignment_notification();

create or replace function app.enqueue_publishable_employee_brief(
  p_company_id uuid,
  p_plan_id uuid,
  p_correlation_id uuid
)
returns void
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_brief_id uuid;
  v_decision_id uuid;
begin
  if not exists (
    select 1 from app.plan_commitments as commitment
    where commitment.company_id = p_company_id and commitment.plan_id = p_plan_id
  ) then
    return;
  end if;

  select brief.id, latest.id into v_brief_id, v_decision_id
  from app.employee_brief_versions as brief
  join app.plan_approval_requirements as requirement
    on requirement.company_id = brief.company_id
   and requirement.plan_id = brief.plan_id
   and requirement.approval_domain = 'disclosure'
   and requirement.artifact_digest = brief.brief_digest
  join lateral (
    select decision.id, decision.decision, decision.expires_at
    from app.plan_approval_decisions as decision
    where decision.company_id = requirement.company_id
      and decision.requirement_id = requirement.id
    order by decision.decided_at desc, decision.id desc
    limit 1
  ) as latest on latest.decision = 'approved'
             and latest.expires_at > clock_timestamp()
  where brief.company_id = p_company_id and brief.plan_id = p_plan_id
  order by brief.version desc
  limit 1;
  if v_brief_id is not null then
    insert into app.outbox_intents (
      company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id
    ) values (
      p_company_id, 'employee_brief.publish', 'employee_brief', v_brief_id,
      jsonb_build_object(
        'plan_id', p_plan_id,
        'brief_version_id', v_brief_id,
        'approval_decision_id', v_decision_id
      ),
      p_correlation_id
    ) on conflict (company_id, idempotency_key) do nothing;
  end if;
end
$$;

create or replace function app.enqueue_brief_after_disclosure_approval()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if new.decision = 'approved' and exists (
    select 1
    from app.plan_approval_requirements as requirement
    where requirement.company_id = new.company_id
      and requirement.id = new.requirement_id
      and requirement.plan_id = new.plan_id
      and requirement.approval_domain = 'disclosure'
  ) then
    perform app.enqueue_publishable_employee_brief(
      new.company_id, new.plan_id, extensions.gen_random_uuid()
    );
  end if;
  return new;
end
$$;

create or replace function app.enqueue_brief_after_plan_commitment()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  perform app.enqueue_publishable_employee_brief(
    new.company_id, new.plan_id, new.correlation_id
  );
  return new;
end
$$;

create trigger disclosure_approval_notify_brief_audience
  after insert on app.plan_approval_decisions
  for each row execute function app.enqueue_brief_after_disclosure_approval();

create trigger plan_commitment_notify_approved_brief_audience
  after insert on app.plan_commitments
  for each row execute function app.enqueue_brief_after_plan_commitment();

revoke execute on function app.enqueue_committed_assignment_notification() from public;
revoke execute on function app.enqueue_publishable_employee_brief(uuid, uuid, uuid) from public;
revoke execute on function app.enqueue_brief_after_disclosure_approval() from public;
revoke execute on function app.enqueue_brief_after_plan_commitment() from public;

-- The durable reset introduced in migration 18000 deletes task reviews before their accepted
-- effort observations. Clear that dependent evidence, plus assignment-triggered workload rows,
-- before delegating to the legacy reset body so a completed demo can be seeded and run again.
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

  delete from app.effort_observations where company_id = p_company_id;
  delete from app.work_assignments where company_id = p_company_id;
  delete from app.employee_workload_state where company_id = p_company_id;
  perform app_private.reset_demo_company_without_ai_provider(p_company_id);
end
$$;

revoke execute on function app_private.reset_demo_company(uuid)
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;

insert into app_private.migration_contract (version, name)
values ('20260926024000', 'backend_workflow_recovery');
