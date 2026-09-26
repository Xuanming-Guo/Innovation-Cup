-- Durable worker leases, transactional outbox delivery, persisted notifications and
-- constant private Realtime invalidation signals.

alter table app.outbox_intents
  add column idempotency_key text,
  add column payload_digest bytea,
  add column state text not null default 'pending',
  add column max_attempts integer not null default 6,
  add column next_attempt_at timestamptz,
  add column lease_owner uuid,
  add column lease_token uuid,
  add column leased_until timestamptz,
  add column last_error_code text,
  add column delivery_result jsonb,
  add column review_required_at timestamptz,
  add column cancelled_at timestamptz;

update app.outbox_intents
set idempotency_key = intent_kind || ':' || aggregate_type || ':' || aggregate_id::text
  || ':' || encode(extensions.digest(convert_to(payload::text, 'UTF8'), 'sha256'), 'hex'),
    payload_digest = extensions.digest(convert_to(payload::text, 'UTF8'), 'sha256'),
    state = case when processed_at is null then 'pending' else 'delivered' end,
    next_attempt_at = case when processed_at is null then available_at end;

alter table app.outbox_intents
  alter column idempotency_key set not null,
  alter column payload_digest set not null,
  alter column next_attempt_at set default clock_timestamp(),
  add constraint outbox_idempotency_length
    check (length(idempotency_key) between 16 and 300),
  add constraint outbox_payload_digest_size check (octet_length(payload_digest) = 32),
  add constraint outbox_state_check check (state in (
    'pending', 'leased', 'retry_scheduled', 'delivered', 'dead_letter',
    'review_required', 'cancelled'
  )),
  add constraint outbox_attempt_limit check (
    max_attempts between 1 and 20 and attempt_count <= max_attempts
  ),
  add constraint outbox_error_code_length
    check (last_error_code is null or length(last_error_code) between 1 and 120),
  add constraint outbox_delivery_result_shape
    check (delivery_result is null or jsonb_typeof(delivery_result) = 'object'),
  add constraint outbox_lease_shape check (
    (state = 'leased') =
    (lease_owner is not null and lease_token is not null and leased_until is not null)
  ),
  add constraint outbox_processed_shape check (
    (state = 'delivered') = (processed_at is not null)
  );

create unique index outbox_logical_idempotency
  on app.outbox_intents (company_id, idempotency_key);
drop index app.outbox_ready_lookup;
create index outbox_ready_lookup on app.outbox_intents (next_attempt_at, created_at)
  where state in ('pending', 'retry_scheduled');

create or replace function app.prepare_outbox_intent()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app, extensions
as $$
begin
  new.payload_digest := extensions.digest(convert_to(new.payload::text, 'UTF8'), 'sha256');
  new.idempotency_key := coalesce(
    new.idempotency_key,
    new.intent_kind || ':' || new.aggregate_type || ':' || new.aggregate_id::text
      || ':' || encode(new.payload_digest, 'hex')
  );
  new.next_attempt_at := coalesce(new.next_attempt_at, new.available_at);
  return new;
end
$$;

create trigger outbox_intents_prepare_durable_state
  before insert on app.outbox_intents
  for each row execute function app.prepare_outbox_intent();

create table app.durable_jobs (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  job_kind text not null check (job_kind in (
    'interpretation.run', 'planning.run', 'private_file.scan', 'outbox.deliver'
  )),
  aggregate_id uuid not null,
  subject_version bigint not null default 1 check (subject_version > 0),
  payload jsonb not null check (
    jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 16384
  ),
  requested_by_membership_id uuid null,
  idempotency_key text not null check (length(idempotency_key) between 16 and 300),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  correlation_id uuid not null,
  state text not null default 'queued' check (state in (
    'queued', 'leased', 'retry_scheduled', 'succeeded', 'dead_letter',
    'review_required', 'cancelled'
  )),
  priority smallint not null default 50 check (priority between 0 and 100),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 6 check (max_attempts between 1 and 20),
  available_at timestamptz not null default clock_timestamp(),
  lease_owner uuid null,
  lease_token uuid null,
  leased_at timestamptz null,
  leased_until timestamptz null,
  cancel_requested_at timestamptz null,
  cancelled_by_membership_id uuid null,
  cancellation_reason text null check (
    cancellation_reason is null or length(btrim(cancellation_reason)) between 1 and 500
  ),
  cancellation_idempotency_key text null check (
    cancellation_idempotency_key is null
    or length(cancellation_idempotency_key) between 16 and 128
  ),
  cancellation_command_digest bytea null check (
    cancellation_command_digest is null or octet_length(cancellation_command_digest) = 32
  ),
  result jsonb null check (
    result is null or (jsonb_typeof(result) = 'object' and octet_length(result::text) <= 32768)
  ),
  result_digest bytea null check (result_digest is null or octet_length(result_digest) = 32),
  last_error_code text null check (
    last_error_code is null or length(last_error_code) between 1 and 120
  ),
  last_error_message text null check (
    last_error_message is null or length(last_error_message) <= 1000
  ),
  created_at timestamptz not null default clock_timestamp(),
  started_at timestamptz null,
  completed_at timestamptz null,
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  unique (company_id, job_kind, aggregate_id),
  unique (company_id, job_kind, idempotency_key),
  foreign key (company_id, requested_by_membership_id)
    references app.company_memberships(company_id, id),
  foreign key (company_id, cancelled_by_membership_id)
    references app.company_memberships(company_id, id),
  check (attempt_count <= max_attempts),
  check (
    (state = 'leased') =
    (lease_owner is not null and lease_token is not null
      and leased_at is not null and leased_until is not null)
  ),
  check (
    state not in ('succeeded', 'dead_letter', 'review_required', 'cancelled')
    or completed_at is not null
  ),
  check ((state = 'succeeded') = (result is not null and result_digest is not null)),
  check (
    (cancel_requested_at is null and cancelled_by_membership_id is null
      and cancellation_reason is null and cancellation_idempotency_key is null
      and cancellation_command_digest is null)
    or
    (cancel_requested_at is not null and cancelled_by_membership_id is not null
      and cancellation_reason is not null and cancellation_idempotency_key is not null
      and cancellation_command_digest is not null)
  )
);

create index durable_jobs_ready_lookup
  on app.durable_jobs (priority desc, available_at, created_at)
  where state in ('queued', 'retry_scheduled');
create index durable_jobs_company_state_lookup
  on app.durable_jobs (company_id, state, created_at);
create index durable_jobs_expired_lease_lookup
  on app.durable_jobs (leased_until) where state = 'leased';

create table app.job_attempts (
  company_id uuid not null,
  job_id uuid not null,
  attempt_number integer not null check (attempt_number > 0),
  lease_token uuid not null unique,
  worker_id uuid not null,
  outcome text null check (outcome is null or outcome in (
    'succeeded', 'retryable_failure', 'permanent_failure', 'ambiguous',
    'lease_expired', 'cancelled'
  )),
  error_code text null check (error_code is null or length(error_code) between 1 and 120),
  metrics jsonb not null default '{}'::jsonb check (
    jsonb_typeof(metrics) = 'object' and octet_length(metrics::text) <= 8192
  ),
  started_at timestamptz not null default clock_timestamp(),
  finished_at timestamptz null,
  primary key (company_id, job_id, attempt_number),
  foreign key (company_id, job_id)
    references app.durable_jobs(company_id, id) on delete cascade,
  check ((outcome is null) = (finished_at is null)),
  check (finished_at is null or finished_at >= started_at)
);

create table app.worker_heartbeats (
  worker_id uuid primary key,
  instance_name text not null check (length(instance_name) between 1 and 200),
  build_commit text not null check (length(build_commit) between 1 and 80),
  environment text not null check (environment in ('development', 'test', 'staging', 'production')),
  current_job_id uuid null,
  started_at timestamptz not null default clock_timestamp(),
  last_seen_at timestamptz not null default clock_timestamp()
);

create table app.notifications (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  recipient_membership_id uuid not null,
  origin_outbox_intent_id uuid not null,
  idempotency_key text not null check (length(idempotency_key) between 16 and 400),
  message_key text not null check (message_key in (
    'plan_state_changed', 'approval_state_changed', 'employee_brief_changed',
    'task_state_changed'
  )),
  subject_type text not null check (subject_type in ('plan', 'employee_brief', 'task')),
  subject_id uuid not null,
  safe_parameters jsonb not null default '{}'::jsonb check (
    safe_parameters = '{}'::jsonb
  ),
  created_at timestamptz not null default clock_timestamp(),
  refresh_emitted_at timestamptz null,
  delivered_at timestamptz null,
  seen_at timestamptz null,
  acknowledged_at timestamptz null,
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  unique (company_id, recipient_membership_id, idempotency_key),
  foreign key (company_id, recipient_membership_id)
    references app.company_memberships(company_id, id),
  foreign key (company_id, origin_outbox_intent_id)
    references app.outbox_intents(company_id, id),
  check (seen_at is null or delivered_at is not null),
  check (acknowledged_at is null or seen_at is not null)
);

create index notifications_recipient_lookup
  on app.notifications (company_id, recipient_membership_id, created_at, id);

create or replace function app.private_refresh_payload()
returns jsonb
language sql
immutable
parallel safe
set search_path = pg_catalog
as $$
  select '{"schema_version":1,"type":"authorised_state_stale"}'::jsonb
$$;

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
            p_company_id, p_user_id, notification.subject_id
          ))
      )
  )
$$;

create or replace function app.emit_private_notification_refresh()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_user_id uuid;
begin
  select user_id into v_user_id
  from app.company_memberships
  where company_id = new.company_id
    and id = new.recipient_membership_id
    and membership_status = 'active';
  if v_user_id is not null
     and to_regprocedure('realtime.send(jsonb,text,text,boolean)') is not null then
    execute 'select realtime.send($1, $2, $3, $4)'
      using app.private_refresh_payload(), 'refresh', 'user:' || v_user_id::text, true;
    new.refresh_emitted_at := clock_timestamp();
  end if;
  return new;
end
$$;

create trigger notifications_emit_private_refresh
  before insert on app.notifications
  for each row execute function app.emit_private_notification_refresh();

do $realtime_policy$
begin
  if to_regclass('realtime.messages') is not null then
    execute 'drop policy if exists coordination_private_refresh_receive on realtime.messages';
    execute $policy$
      create policy coordination_private_refresh_receive
      on realtime.messages for select to authenticated
      using (
        realtime.messages.extension = 'broadcast'
        and realtime.topic() = 'user:' || (select auth.uid())::text
      )
    $policy$;
  end if;
end
$realtime_policy$;

create or replace function app.reconcile_expired_durable_jobs()
returns integer
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_job app.durable_jobs%rowtype;
  v_state text;
  v_count integer := 0;
begin
  for v_job in
    select * from app.durable_jobs
    where state = 'leased' and leased_until <= clock_timestamp()
    order by leased_until
    for update skip locked
  loop
    v_state := case
      when v_job.cancel_requested_at is not null then 'cancelled'
      when v_job.attempt_count >= v_job.max_attempts then 'dead_letter'
      else 'retry_scheduled'
    end;
    update app.job_attempts
    set outcome = case when v_state = 'cancelled' then 'cancelled' else 'lease_expired' end,
        error_code = case when v_state = 'cancelled' then 'cancelled' else 'lease_expired' end,
        finished_at = clock_timestamp()
    where company_id = v_job.company_id and job_id = v_job.id
      and attempt_number = v_job.attempt_count and outcome is null;
    update app.durable_jobs
    set state = v_state,
        available_at = case when v_state = 'retry_scheduled'
          then clock_timestamp() else available_at end,
        lease_owner = null, lease_token = null, leased_at = null, leased_until = null,
        last_error_code = case when v_state = 'cancelled'
          then 'cancelled' else 'lease_expired' end,
        last_error_message = null,
        completed_at = case when v_state in ('cancelled', 'dead_letter')
          then clock_timestamp() else null end,
        row_version = row_version + 1
    where company_id = v_job.company_id and id = v_job.id;
    if v_job.job_kind = 'interpretation.run' then
      update app.interpretation_runs
      set status = 'failed', outcome = 'worker_lease_lost',
          error_code = 'worker_lease_lost', completed_at = clock_timestamp()
      where company_id = v_job.company_id
        and request_id = v_job.aggregate_id and status = 'running';
      update app.planning_requests
      set status = 'failed'
      where company_id = v_job.company_id and id = v_job.aggregate_id
        and status = 'interpretation_running';
    end if;
    if v_job.job_kind = 'outbox.deliver' then
      update app.outbox_intents
      set state = v_state, attempt_count = v_job.attempt_count,
          next_attempt_at = case when v_state = 'retry_scheduled'
            then clock_timestamp() else null end,
          lease_owner = null, lease_token = null, leased_until = null,
          last_error_code = case when v_state = 'cancelled'
            then 'cancelled' else 'lease_expired' end,
          last_error = null,
          review_required_at = case when v_state = 'dead_letter'
            then clock_timestamp() else null end,
          cancelled_at = case when v_state = 'cancelled'
            then clock_timestamp() else null end
      where company_id = v_job.company_id and id = v_job.aggregate_id
        and state <> 'delivered';
    end if;
    v_count := v_count + 1;
  end loop;
  return v_count;
end
$$;

create or replace function app.reconcile_unauthorised_durable_jobs()
returns integer
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_count integer;
begin
  with invalid_jobs as (
    select job.company_id, job.id
    from app.durable_jobs as job
    left join app.company_memberships as membership
      on membership.company_id = job.company_id
     and membership.id = job.requested_by_membership_id
     and membership.membership_status = 'active'
     and membership.administrative_role in ('manager', 'company_admin')
    where job.state in ('queued', 'retry_scheduled')
      and job.job_kind in ('interpretation.run', 'planning.run')
      and membership.id is null
    for update of job skip locked
  )
  update app.durable_jobs as job
  set state = 'review_required',
      last_error_code = 'requester_authority_revoked',
      last_error_message = null,
      completed_at = clock_timestamp(),
      row_version = job.row_version + 1
  from invalid_jobs
  where job.company_id = invalid_jobs.company_id and job.id = invalid_jobs.id;
  get diagnostics v_count = row_count;
  return v_count;
end
$$;

create or replace function app.lease_durable_jobs(
  p_worker_id uuid,
  p_limit integer,
  p_lease_seconds integer
)
returns table (
  job_id uuid,
  company_id uuid,
  job_kind text,
  aggregate_id uuid,
  payload jsonb,
  requested_by_membership_id uuid,
  requested_by_user_id uuid,
  administrative_role text,
  employee_id uuid,
  correlation_id uuid,
  attempt_count integer,
  max_attempts integer,
  lease_token uuid,
  leased_until timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_job app.durable_jobs%rowtype;
  v_token uuid;
  v_until timestamptz;
begin
  if p_limit not between 1 and 32 or p_lease_seconds not between 15 and 900 then
    raise exception using errcode = '22023', message = 'lease_bounds_invalid';
  end if;
  perform app.reconcile_expired_durable_jobs();
  perform app.reconcile_unauthorised_durable_jobs();
  for v_job in
    select * from app.durable_jobs
    where state in ('queued', 'retry_scheduled')
      and available_at <= clock_timestamp()
      and cancel_requested_at is null
    order by priority desc, available_at, created_at
    for update skip locked
    limit p_limit
  loop
    v_token := gen_random_uuid();
    v_until := clock_timestamp() + make_interval(secs => p_lease_seconds);
    update app.durable_jobs as job
    set state = 'leased', attempt_count = job.attempt_count + 1,
        lease_owner = p_worker_id, lease_token = v_token,
        leased_at = clock_timestamp(), leased_until = v_until,
        started_at = coalesce(job.started_at, clock_timestamp()),
        last_error_code = null, last_error_message = null,
        completed_at = null, row_version = job.row_version + 1
    where job.id = v_job.id and job.company_id = v_job.company_id
    returning job.attempt_count into v_job.attempt_count;
    insert into app.job_attempts (
      company_id, job_id, attempt_number, lease_token, worker_id
    ) values (v_job.company_id, v_job.id, v_job.attempt_count, v_token, p_worker_id);
    if v_job.job_kind = 'outbox.deliver' then
      update app.outbox_intents as intent
      set state = 'leased', attempt_count = v_job.attempt_count,
          lease_owner = p_worker_id, lease_token = v_token, leased_until = v_until,
          next_attempt_at = null, last_error_code = null, last_error = null
      where intent.company_id = v_job.company_id and intent.id = v_job.aggregate_id
        and intent.state <> 'delivered';
    end if;
    return query
    select v_job.id, v_job.company_id, v_job.job_kind, v_job.aggregate_id,
      v_job.payload, v_job.requested_by_membership_id,
      membership.user_id, membership.administrative_role,
      employee.id, v_job.correlation_id, v_job.attempt_count,
      v_job.max_attempts, v_token, v_until
    from (select 1) as singleton
    left join app.company_memberships as membership
      on membership.company_id = v_job.company_id
     and membership.id = v_job.requested_by_membership_id
     and membership.membership_status = 'active'
    left join app.employee_profiles as employee
      on employee.company_id = membership.company_id
     and employee.membership_id = membership.id
     and employee.status = 'active';
  end loop;
end
$$;

create or replace function app.renew_durable_job_lease(
  p_company_id uuid,
  p_job_id uuid,
  p_worker_id uuid,
  p_lease_token uuid,
  p_lease_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_until timestamptz;
begin
  if p_lease_seconds not between 15 and 900 then
    raise exception using errcode = '22023', message = 'lease_bounds_invalid';
  end if;
  v_until := clock_timestamp() + make_interval(secs => p_lease_seconds);
  update app.durable_jobs set leased_until = v_until, row_version = row_version + 1
  where company_id = p_company_id and id = p_job_id and state = 'leased'
    and lease_owner = p_worker_id and lease_token = p_lease_token
    and leased_until > clock_timestamp() and cancel_requested_at is null;
  if found then
    update app.outbox_intents set leased_until = v_until
    where company_id = p_company_id
      and id = (select aggregate_id from app.durable_jobs
        where company_id = p_company_id and id = p_job_id and job_kind = 'outbox.deliver')
      and lease_token = p_lease_token and state = 'leased';
  end if;
  return found;
end
$$;

create or replace function app.complete_durable_job(
  p_company_id uuid,
  p_job_id uuid,
  p_worker_id uuid,
  p_lease_token uuid,
  p_result jsonb,
  p_result_digest bytea,
  p_metrics jsonb
)
returns table (job_state text, replayed boolean)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_job app.durable_jobs%rowtype;
begin
  if jsonb_typeof(p_result) <> 'object' or octet_length(p_result::text) > 32768
     or octet_length(p_result_digest) <> 32
     or jsonb_typeof(p_metrics) <> 'object' or octet_length(p_metrics::text) > 8192 then
    raise exception using errcode = '22023', message = 'job_result_invalid';
  end if;
  select * into v_job from app.durable_jobs
  where company_id = p_company_id and id = p_job_id for update;
  if not found then
    raise exception using errcode = '40001', message = 'job_lease_invalid';
  end if;
  if v_job.state = 'succeeded' then
    if v_job.result_digest <> p_result_digest then
      raise exception using errcode = '40001', message = 'job_result_conflict';
    end if;
    job_state := 'succeeded'; replayed := true; return next; return;
  end if;
  if v_job.state <> 'leased' or v_job.lease_owner <> p_worker_id
     or v_job.lease_token <> p_lease_token or v_job.leased_until <= clock_timestamp() then
    raise exception using errcode = '40001', message = 'job_lease_invalid';
  end if;
  if v_job.cancel_requested_at is not null then
    update app.durable_jobs
    set state = 'cancelled', lease_owner = null, lease_token = null,
        leased_at = null, leased_until = null, completed_at = clock_timestamp(),
        last_error_code = 'cancelled', row_version = row_version + 1
    where company_id = p_company_id and id = p_job_id;
    update app.job_attempts set outcome = 'cancelled', error_code = 'cancelled',
      metrics = p_metrics, finished_at = clock_timestamp()
    where company_id = p_company_id and job_id = p_job_id
      and attempt_number = v_job.attempt_count and lease_token = p_lease_token;
    job_state := 'cancelled'; replayed := false; return next; return;
  end if;
  update app.durable_jobs
  set state = 'succeeded', result = p_result, result_digest = p_result_digest,
      lease_owner = null, lease_token = null, leased_at = null, leased_until = null,
      last_error_code = null, last_error_message = null,
      completed_at = clock_timestamp(), row_version = row_version + 1
  where company_id = p_company_id and id = p_job_id;
  update app.job_attempts
  set outcome = 'succeeded', metrics = p_metrics, finished_at = clock_timestamp()
  where company_id = p_company_id and job_id = p_job_id
    and attempt_number = v_job.attempt_count and lease_token = p_lease_token;
  job_state := 'succeeded'; replayed := false; return next;
end
$$;

create or replace function app.fail_durable_job(
  p_company_id uuid,
  p_job_id uuid,
  p_worker_id uuid,
  p_lease_token uuid,
  p_error_code text,
  p_error_message text,
  p_retryable boolean,
  p_ambiguous boolean,
  p_metrics jsonb
)
returns table (job_state text, next_attempt_at timestamptz)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_job app.durable_jobs%rowtype;
  v_state text;
  v_next timestamptz;
begin
  if nullif(btrim(p_error_code), '') is null or length(p_error_code) > 120
     or length(p_error_message) > 1000 or jsonb_typeof(p_metrics) <> 'object'
     or octet_length(p_metrics::text) > 8192 then
    raise exception using errcode = '22023', message = 'job_failure_invalid';
  end if;
  select * into v_job from app.durable_jobs
  where company_id = p_company_id and id = p_job_id for update;
  if not found or v_job.state <> 'leased' or v_job.lease_owner <> p_worker_id
     or v_job.lease_token <> p_lease_token or v_job.leased_until <= clock_timestamp() then
    raise exception using errcode = '40001', message = 'job_lease_invalid';
  end if;
  v_state := case
    when v_job.cancel_requested_at is not null then 'cancelled'
    when p_ambiguous then 'review_required'
    when p_retryable and v_job.attempt_count < v_job.max_attempts then 'retry_scheduled'
    when p_retryable then 'dead_letter'
    else 'review_required'
  end;
  v_next := case when v_state = 'retry_scheduled' then
    clock_timestamp() + make_interval(
      secs => least(300, 5 * (2 ^ least(v_job.attempt_count - 1, 6))::integer)
    ) end;
  update app.durable_jobs
  set state = v_state, available_at = coalesce(v_next, available_at),
      lease_owner = null, lease_token = null, leased_at = null, leased_until = null,
      last_error_code = p_error_code,
      last_error_message = case when p_error_message = p_error_code then null
        else p_error_message end,
      completed_at = case when v_state in ('dead_letter', 'review_required', 'cancelled')
        then clock_timestamp() else null end,
      row_version = row_version + 1
  where company_id = p_company_id and id = p_job_id;
  update app.job_attempts
  set outcome = case
      when v_state = 'cancelled' then 'cancelled'
      when p_ambiguous then 'ambiguous'
      when p_retryable then 'retryable_failure'
      else 'permanent_failure'
    end,
    error_code = p_error_code, metrics = p_metrics, finished_at = clock_timestamp()
  where company_id = p_company_id and job_id = p_job_id
    and attempt_number = v_job.attempt_count and lease_token = p_lease_token;
  if v_job.job_kind = 'outbox.deliver' then
    update app.outbox_intents
    set state = v_state, attempt_count = v_job.attempt_count,
        next_attempt_at = v_next, lease_owner = null, lease_token = null,
        leased_until = null, last_error_code = p_error_code,
        last_error = case when p_error_message = p_error_code then null else p_error_message end,
        review_required_at = case when v_state in ('dead_letter', 'review_required')
          then clock_timestamp() else null end,
        cancelled_at = case when v_state = 'cancelled' then clock_timestamp() else null end
    where company_id = p_company_id and id = v_job.aggregate_id
      and state <> 'delivered';
  end if;
  job_state := v_state; next_attempt_at := v_next; return next;
end
$$;

create or replace function app.record_worker_heartbeat(
  p_worker_id uuid,
  p_instance_name text,
  p_build_commit text,
  p_environment text,
  p_current_job_id uuid
)
returns void
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  insert into app.worker_heartbeats (
    worker_id, instance_name, build_commit, environment, current_job_id
  ) values (
    p_worker_id, p_instance_name, p_build_commit, p_environment, p_current_job_id
  ) on conflict (worker_id) do update set
    instance_name = excluded.instance_name,
    build_commit = excluded.build_commit,
    environment = excluded.environment,
    current_job_id = excluded.current_job_id,
    last_seen_at = clock_timestamp();
end
$$;

create or replace function app.enqueue_request_job()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  insert into app.durable_jobs (
    company_id, job_kind, aggregate_id, subject_version, payload,
    requested_by_membership_id, idempotency_key, command_digest, correlation_id
  ) values (
    new.company_id, 'interpretation.run', new.id, new.request_version,
    jsonb_build_object('request_id', new.id, 'request_version', new.request_version),
    new.requester_membership_id,
    'interpretation.run:' || new.id::text || ':' || new.request_version::text,
    extensions.digest(
      convert_to(new.id::text || ':' || new.request_version::text || ':'
        || encode(new.request_digest, 'hex'), 'UTF8'), 'sha256'
    ), gen_random_uuid()
  ) on conflict (company_id, job_kind, aggregate_id) do nothing;
  return new;
end
$$;

create trigger planning_requests_enqueue_interpretation
  after insert on app.planning_requests
  for each row execute function app.enqueue_request_job();

insert into app.durable_jobs (
  company_id, job_kind, aggregate_id, subject_version, payload,
  requested_by_membership_id, idempotency_key, command_digest, correlation_id
)
select request.company_id, 'interpretation.run', request.id, request.request_version,
  jsonb_build_object('request_id', request.id, 'request_version', request.request_version),
  request.requester_membership_id,
  'interpretation.run:' || request.id::text || ':' || request.request_version::text,
  extensions.digest(convert_to(request.id::text || ':' || request.request_version::text
    || ':' || encode(request.request_digest, 'hex'), 'UTF8'), 'sha256'),
  gen_random_uuid()
from app.planning_requests as request
where request.status in ('pending_interpretation', 'failed')
on conflict (company_id, job_kind, aggregate_id) do nothing;

create or replace function app.enqueue_snapshot_job()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_requester uuid;
begin
  select requester_membership_id into v_requester
  from app.planning_requests
  where company_id = new.company_id and id = new.request_id;
  insert into app.durable_jobs (
    company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
    idempotency_key, command_digest, correlation_id
  ) values (
    new.company_id, 'planning.run', new.id,
    jsonb_build_object('snapshot_id', new.id), v_requester,
    'planning.run:' || new.id::text,
    extensions.digest(convert_to(new.id::text || ':'
      || encode(new.snapshot_digest, 'hex'), 'UTF8'), 'sha256'),
    gen_random_uuid()
  ) on conflict (company_id, job_kind, aggregate_id) do nothing;
  return new;
end
$$;

create trigger planning_snapshots_enqueue_solver
  after insert on app.planning_snapshots
  for each row execute function app.enqueue_snapshot_job();

insert into app.durable_jobs (
  company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
  idempotency_key, command_digest, correlation_id
)
select snapshot.company_id, 'planning.run', snapshot.id,
  jsonb_build_object('snapshot_id', snapshot.id), request.requester_membership_id,
  'planning.run:' || snapshot.id::text,
  extensions.digest(convert_to(snapshot.id::text || ':'
    || encode(snapshot.snapshot_digest, 'hex'), 'UTF8'), 'sha256'),
  gen_random_uuid()
from app.planning_snapshots as snapshot
join app.planning_requests as request
  on request.company_id = snapshot.company_id and request.id = snapshot.request_id
on conflict (company_id, job_kind, aggregate_id) do nothing;

create or replace function app.enqueue_outbox_job()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
begin
  select id into v_membership_id from app.company_memberships
  where company_id = new.company_id and user_id = app.current_actor_id()
    and membership_status = 'active';
  insert into app.durable_jobs (
    company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
    idempotency_key, command_digest, correlation_id
  ) values (
    new.company_id, 'outbox.deliver', new.id,
    jsonb_build_object('outbox_intent_id', new.id), v_membership_id,
    'outbox.deliver:' || new.id::text,
    extensions.digest(convert_to(new.id::text || ':'
      || encode(new.payload_digest, 'hex'), 'UTF8'), 'sha256'),
    new.correlation_id
  ) on conflict (company_id, job_kind, aggregate_id) do nothing;
  return new;
end
$$;

create trigger outbox_intents_enqueue_delivery
  after insert on app.outbox_intents
  for each row execute function app.enqueue_outbox_job();

-- Existing intents predate the enqueue trigger.
insert into app.durable_jobs (
  company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
  idempotency_key, command_digest, correlation_id, state, completed_at,
  result, result_digest
)
select intent.company_id, 'outbox.deliver', intent.id,
  jsonb_build_object('outbox_intent_id', intent.id), null,
  'outbox.deliver:' || intent.id::text,
  extensions.digest(convert_to(intent.id::text || ':'
    || encode(intent.payload_digest, 'hex'), 'UTF8'), 'sha256'),
  intent.correlation_id,
  case when intent.state = 'delivered' then 'succeeded' else 'queued' end,
  intent.processed_at,
  case when intent.state = 'delivered' then coalesce(intent.delivery_result, '{}'::jsonb) end,
  case when intent.state = 'delivered' then extensions.digest(
    convert_to(coalesce(intent.delivery_result, '{}'::jsonb)::text, 'UTF8'), 'sha256'
  ) end
from app.outbox_intents as intent
on conflict (company_id, job_kind, aggregate_id) do nothing;

create or replace function app.enqueue_quarantined_file_job()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_membership_id uuid;
begin
  if new.state = 'quarantined' and old.state is distinct from new.state then
    select employee.membership_id into v_membership_id
    from app.employee_profiles as employee
    where employee.company_id = new.company_id and employee.id = new.uploader_employee_id;
    insert into app.durable_jobs (
      company_id, job_kind, aggregate_id, subject_version, payload,
      requested_by_membership_id, idempotency_key, command_digest, correlation_id,
      max_attempts
    ) values (
      new.company_id, 'private_file.scan', new.id, new.row_version,
      jsonb_build_object('file_id', new.id, 'file_version', new.row_version),
      v_membership_id,
      'private_file.scan:' || new.id::text || ':' || new.row_version::text,
      extensions.digest(convert_to(new.id::text || ':' || new.row_version::text,
        'UTF8'), 'sha256'), gen_random_uuid(), 3
    ) on conflict (company_id, job_kind, aggregate_id) do nothing;
  end if;
  return new;
end
$$;

create trigger private_files_enqueue_scan
  after update of state on app.private_files
  for each row execute function app.enqueue_quarantined_file_job();

insert into app.durable_jobs (
  company_id, job_kind, aggregate_id, subject_version, payload,
  requested_by_membership_id, idempotency_key, command_digest, correlation_id,
  max_attempts
)
select file.company_id, 'private_file.scan', file.id, file.row_version,
  jsonb_build_object('file_id', file.id, 'file_version', file.row_version),
  employee.membership_id,
  'private_file.scan:' || file.id::text || ':' || file.row_version::text,
  extensions.digest(convert_to(file.id::text || ':' || file.row_version::text,
    'UTF8'), 'sha256'), gen_random_uuid(), 3
from app.private_files as file
join app.employee_profiles as employee
  on employee.company_id = file.company_id and employee.id = file.uploader_employee_id
where file.state = 'quarantined'
on conflict (company_id, job_kind, aggregate_id) do nothing;

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
     or not exists (select 1 from app.planning_requests
       where company_id = p_company_id and id = p_aggregate_id) then
    raise exception using errcode = '22023', message = 'job_target_invalid';
  end if;
  select id into v_membership_id from app.company_memberships
  where company_id = p_company_id and user_id = app.current_actor_id()
    and membership_status = 'active';
  v_payload := jsonb_build_object('request_id', p_aggregate_id);
  insert into app.durable_jobs (
    company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
    idempotency_key, command_digest, correlation_id
  ) values (
    p_company_id, p_job_kind, p_aggregate_id, v_payload, v_membership_id,
    p_idempotency_key, p_command_digest, p_correlation_id
  ) on conflict (company_id, job_kind, aggregate_id) do nothing;
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

create or replace function app.request_durable_job_cancellation(
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
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id()
     or not app.can_manage_planning(p_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'manager_authority_required';
  end if;
  select id into v_membership_id from app.company_memberships
  where company_id = p_company_id and user_id = app.current_actor_id()
    and membership_status = 'active';
  select * into v_job from app.durable_jobs
  where company_id = p_company_id and id = p_job_id for update;
  if not found or v_job.job_kind = 'outbox.deliver' then
    return;
  end if;
  if v_job.cancellation_idempotency_key is not null then
    if v_job.cancellation_idempotency_key <> p_idempotency_key
       or v_job.cancellation_command_digest <> p_command_digest then
      raise exception using errcode = '40001', message = 'cancellation_idempotency_conflict';
    end if;
  elsif v_job.state not in ('succeeded', 'dead_letter', 'review_required', 'cancelled') then
    update app.durable_jobs as job
    set cancel_requested_at = clock_timestamp(), cancelled_by_membership_id = v_membership_id,
        cancellation_reason = p_reason, cancellation_idempotency_key = p_idempotency_key,
        cancellation_command_digest = p_command_digest,
        state = case when job.state in ('queued', 'retry_scheduled')
          then 'cancelled' else job.state end,
        completed_at = case when job.state in ('queued', 'retry_scheduled')
          then clock_timestamp() else job.completed_at end,
        last_error_code = case when job.state in ('queued', 'retry_scheduled')
          then 'cancelled' else job.last_error_code end,
        row_version = job.row_version + 1
    where job.company_id = p_company_id and job.id = p_job_id;
  end if;
  return query
  select job.id, job.job_kind, job.aggregate_id, job.state, job.attempt_count,
    job.max_attempts, job.available_at, job.leased_until,
    job.cancel_requested_at is not null, job.last_error_code,
    job.created_at, job.completed_at
  from app.durable_jobs as job
  where job.company_id = p_company_id and job.id = p_job_id;
end
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
          and app.can_read_employee_brief(p_company_id, membership.user_id, v_subject_id))
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

create or replace function app.record_leased_private_file_scan(
  p_company_id uuid,
  p_job_id uuid,
  p_worker_id uuid,
  p_lease_token uuid,
  p_file_id uuid,
  p_verdict text,
  p_detected_mime_type text,
  p_observed_size_bytes bigint,
  p_content_sha256 bytea,
  p_scan_engine_version text,
  p_final_object_path text
)
returns text
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if not exists (
    select 1 from app.durable_jobs
    where company_id = p_company_id and id = p_job_id
      and job_kind = 'private_file.scan' and aggregate_id = p_file_id
      and state = 'leased' and lease_owner = p_worker_id
      and lease_token = p_lease_token and leased_until > clock_timestamp()
      and cancel_requested_at is null
  ) then
    raise exception using errcode = '40001', message = 'file_scan_job_lease_invalid';
  end if;
  perform set_config('app.actor_id', coalesce((
    select membership.user_id::text
    from app.durable_jobs as job
    join app.company_memberships as membership
      on membership.company_id = job.company_id
     and membership.id = job.requested_by_membership_id
    where job.company_id = p_company_id and job.id = p_job_id
  ), '00000000-0000-0000-0000-000000000000'), true);
  perform set_config('app.company_id', p_company_id::text, true);
  perform set_config('app.purpose', 'file-scan:complete', true);
  return app.record_private_file_scan(
    p_company_id, p_file_id, p_verdict, p_detected_mime_type,
    p_observed_size_bytes, p_content_sha256, p_scan_engine_version,
    p_final_object_path
  );
end
$$;

create or replace function app.company_durable_metrics(p_company_id uuid)
returns table (
  queued bigint, leased bigint, retry_scheduled bigint, dead_letter bigint,
  review_required bigint, cancelled bigint, succeeded bigint,
  oldest_ready_seconds integer, outbox_pending bigint, notifications_unread bigint
)
language plpgsql
stable
security definer
set search_path = pg_catalog, app
as $$
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id()
     or not app.can_manage_planning(p_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'manager_authority_required';
  end if;
  return query
  select
    count(*) filter (where job.state = 'queued'),
    count(*) filter (where job.state = 'leased'),
    count(*) filter (where job.state = 'retry_scheduled'),
    count(*) filter (where job.state = 'dead_letter'),
    count(*) filter (where job.state = 'review_required'),
    count(*) filter (where job.state = 'cancelled'),
    count(*) filter (where job.state = 'succeeded'),
    extract(epoch from (clock_timestamp() - min(job.available_at)
      filter (where job.state in ('queued', 'retry_scheduled'))))::integer,
    (select count(*) from app.outbox_intents as intent
      where intent.company_id = p_company_id and intent.state <> 'delivered'),
    (select count(*) from app.notifications as notification
      where notification.company_id = p_company_id and notification.seen_at is null)
  from app.durable_jobs as job where job.company_id = p_company_id;
end
$$;

create or replace function app.advance_notification_state(
  p_company_id uuid,
  p_notification_id uuid,
  p_action text
)
returns table (
  notification_id uuid, message_key text, subject_type text, subject_id uuid,
  safe_parameters jsonb, created_at timestamptz, delivered_at timestamptz,
  seen_at timestamptz, acknowledged_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if not app.request_context_present() or p_company_id <> app.current_company_id()
     or not app.can_read_notification(
       p_company_id, app.current_actor_id(), p_notification_id
     ) then
    return;
  end if;
  if p_action = 'seen' then
    update app.notifications as notification set
      delivered_at = coalesce(notification.delivered_at, clock_timestamp()),
      seen_at = coalesce(notification.seen_at, clock_timestamp()),
      row_version = notification.row_version + 1
    where notification.company_id = p_company_id
      and notification.id = p_notification_id;
  elsif p_action = 'acknowledged' then
    update app.notifications as notification set
      delivered_at = coalesce(notification.delivered_at, clock_timestamp()),
      seen_at = coalesce(notification.seen_at, clock_timestamp()),
      acknowledged_at = coalesce(notification.acknowledged_at, clock_timestamp()),
      row_version = notification.row_version + 1
    where notification.company_id = p_company_id
      and notification.id = p_notification_id;
  else
    raise exception using errcode = '22023', message = 'notification_action_invalid';
  end if;
  return query
  select notification.id, notification.message_key, notification.subject_type,
    notification.subject_id, notification.safe_parameters, notification.created_at,
    notification.delivered_at, notification.seen_at, notification.acknowledged_at
  from app.notifications as notification
  where notification.company_id = p_company_id and notification.id = p_notification_id;
end
$$;

alter table app.durable_jobs enable row level security;
alter table app.job_attempts enable row level security;
alter table app.worker_heartbeats enable row level security;
alter table app.notifications enable row level security;

create policy durable_jobs_manager_select on app.durable_jobs
  for select to coordination_api
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_manage_planning(company_id, app.current_actor_id()));
create policy job_attempts_manager_select on app.job_attempts
  for select to coordination_api
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_manage_planning(company_id, app.current_actor_id()));
create policy notifications_recipient_select on app.notifications
  for select to coordination_api
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_notification(company_id, app.current_actor_id(), id));
create policy notifications_recipient_update on app.notifications
  for update to coordination_api
  using (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_notification(company_id, app.current_actor_id(), id))
  with check (app.request_context_present() and company_id = app.current_company_id()
    and app.can_read_notification(company_id, app.current_actor_id(), id));

grant select on app.durable_jobs, app.job_attempts to coordination_api;
grant select, update on app.notifications to coordination_api;

revoke execute on function app.private_refresh_payload() from public;
revoke execute on function app.can_read_notification(uuid, uuid, uuid) from public;
revoke execute on function app.emit_private_notification_refresh() from public;
revoke execute on function app.prepare_outbox_intent() from public;
revoke execute on function app.reconcile_expired_durable_jobs() from public;
revoke execute on function app.reconcile_unauthorised_durable_jobs() from public;
revoke execute on function app.lease_durable_jobs(uuid, integer, integer) from public;
revoke execute on function app.renew_durable_job_lease(uuid, uuid, uuid, uuid, integer) from public;
revoke execute on function app.complete_durable_job(
  uuid, uuid, uuid, uuid, jsonb, bytea, jsonb
) from public;
revoke execute on function app.fail_durable_job(
  uuid, uuid, uuid, uuid, text, text, boolean, boolean, jsonb
) from public;
revoke execute on function app.record_worker_heartbeat(uuid, text, text, text, uuid) from public;
revoke execute on function app.enqueue_request_job() from public;
revoke execute on function app.enqueue_snapshot_job() from public;
revoke execute on function app.enqueue_outbox_job() from public;
revoke execute on function app.enqueue_quarantined_file_job() from public;
revoke execute on function app.ensure_durable_job(uuid, text, uuid, text, bytea, uuid) from public;
revoke execute on function app.request_durable_job_cancellation(
  uuid, uuid, text, text, bytea
) from public;
revoke execute on function app.deliver_internal_outbox_intent(uuid, uuid, uuid, uuid) from public;
revoke execute on function app.record_leased_private_file_scan(
  uuid, uuid, uuid, uuid, uuid, text, text, bigint, bytea, text, text
) from public;
revoke execute on function app.company_durable_metrics(uuid) from public;
revoke execute on function app.advance_notification_state(uuid, uuid, text) from public;

grant execute on function app.private_refresh_payload() to coordination_worker;
grant execute on function app.can_read_notification(uuid, uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.reconcile_expired_durable_jobs() to coordination_worker;
grant execute on function app.reconcile_unauthorised_durable_jobs() to coordination_worker;
grant execute on function app.lease_durable_jobs(uuid, integer, integer) to coordination_worker;
grant execute on function app.renew_durable_job_lease(uuid, uuid, uuid, uuid, integer)
  to coordination_worker;
grant execute on function app.complete_durable_job(
  uuid, uuid, uuid, uuid, jsonb, bytea, jsonb
) to coordination_worker;
grant execute on function app.fail_durable_job(
  uuid, uuid, uuid, uuid, text, text, boolean, boolean, jsonb
) to coordination_worker;
grant execute on function app.record_worker_heartbeat(uuid, text, text, text, uuid)
  to coordination_worker;
grant execute on function app.ensure_durable_job(uuid, text, uuid, text, bytea, uuid)
  to coordination_api;
grant execute on function app.request_durable_job_cancellation(
  uuid, uuid, text, text, bytea
) to coordination_api;
revoke execute on function app.record_private_file_scan(
  uuid, uuid, text, text, bigint, bytea, text, text
) from coordination_worker;
grant execute on function app.deliver_internal_outbox_intent(uuid, uuid, uuid, uuid)
  to coordination_worker;
grant execute on function app.record_leased_private_file_scan(
  uuid, uuid, uuid, uuid, uuid, text, text, bigint, bytea, text, text
) to coordination_worker;
grant execute on function app.company_durable_metrics(uuid) to coordination_api;
grant execute on function app.advance_notification_state(uuid, uuid, text)
  to coordination_api;

-- Reset remains hard-gated to demo companies and now removes durable dependants first.
create or replace function app_private.reset_demo_company(p_company_id uuid)
returns void
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if not exists (
    select 1 from app.companies where id = p_company_id and is_demo is true
  ) then
    raise exception 'demo reset refused for non-demo or unknown company'
      using errcode = '42501';
  end if;
  delete from app.notifications where company_id = p_company_id;
  delete from app.job_attempts where company_id = p_company_id;
  delete from app.durable_jobs where company_id = p_company_id;
  delete from app.task_reviews where company_id = p_company_id;
  delete from app.effort_observations where company_id = p_company_id;
  delete from app.familiarity_evidence where company_id = p_company_id;
  delete from app.submission_files where company_id = p_company_id;
  delete from app.submissions where company_id = p_company_id;
  delete from app.task_corrections where company_id = p_company_id;
  delete from app.task_events where company_id = p_company_id;
  delete from app.task_review_policies where company_id = p_company_id;
  delete from app.task_access_grants where company_id = p_company_id;
  delete from app.employee_workload_state where company_id = p_company_id;
  delete from app.work_assignments where company_id = p_company_id;
  delete from app.committed_schedule_blocks where company_id = p_company_id;
  delete from app.work_items where company_id = p_company_id;
  delete from app.plan_approval_uses where company_id = p_company_id;
  delete from app.plan_commitments where company_id = p_company_id;
  delete from app.plan_approval_decisions where company_id = p_company_id;
  delete from app.plan_approval_requirements where company_id = p_company_id;
  delete from app.employee_brief_audience_grants where company_id = p_company_id;
  delete from app.employee_brief_versions where company_id = p_company_id;
  delete from app.plan_changes where company_id = p_company_id;
  delete from app.plan_schedule_blocks where company_id = p_company_id;
  delete from app.plan_task_placements where company_id = p_company_id;
  delete from app.audit_events where company_id = p_company_id;
  delete from app.outbox_intents where company_id = p_company_id;
  delete from app.plans where company_id = p_company_id;
  delete from app.solver_runs where company_id = p_company_id;
  delete from app.planning_snapshot_constraints where company_id = p_company_id;
  delete from app.planning_snapshots where company_id = p_company_id;
  delete from app.constraint_source_evidence where company_id = p_company_id;
  delete from app.validated_constraints where company_id = p_company_id;
  delete from app.clarification_questions where company_id = p_company_id;
  delete from app.trace_steps where company_id = p_company_id;
  delete from app.candidate_contracts where company_id = p_company_id;
  delete from app.interpretation_runs where company_id = p_company_id;
  delete from app.retrieval_runs where company_id = p_company_id;
  delete from app.planning_request_sources where company_id = p_company_id;
  delete from app.planning_requests where company_id = p_company_id;
  delete from app.private_files where company_id = p_company_id;
  delete from app.source_excerpts where company_id = p_company_id;
  delete from app.source_access_grants where company_id = p_company_id;
  update app.source_records set current_version_id = null where company_id = p_company_id;
  delete from app.source_versions where company_id = p_company_id;
  delete from app.source_records where company_id = p_company_id;
  delete from app.execution_resources where company_id = p_company_id;
  delete from app.projects where company_id = p_company_id;
  delete from app.invitations where company_id = p_company_id;
  delete from app.team_memberships where company_id = p_company_id;
  delete from app.teams where company_id = p_company_id;
  delete from app.employee_profiles where company_id = p_company_id;
  delete from app.company_memberships where company_id = p_company_id;
  update app.companies set planning_revision = 0, policy_revision = 0
  where id = p_company_id;
end
$$;

revoke execute on function app_private.reset_demo_company(uuid) from public, anon,
  authenticated, service_role, coordination_api, coordination_worker;

insert into app_private.migration_contract (version, name)
values ('20260926018000', 'durable_jobs_outbox_realtime');
