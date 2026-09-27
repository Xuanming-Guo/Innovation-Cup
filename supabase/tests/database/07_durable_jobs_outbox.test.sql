begin;
select plan(42);

select has_table('app', 'durable_jobs', 'durable jobs exist');
select has_table('app', 'job_attempts', 'durable attempt ledger exists');
select has_table('app', 'worker_heartbeats', 'worker heartbeats exist');
select has_table('app', 'notifications', 'persisted notifications exist');
select is(
  app.private_refresh_payload()::text,
  '{"type": "authorised_state_stale", "schema_version": 1}',
  'Realtime payload is a constant invalidation envelope'
);
select is(
  (select count(*)::integer from pg_publication_tables where schemaname = 'app'),
  0,
  'application tables are not exposed through Postgres Changes'
);
select is(
  (select count(*)::integer from pg_policies
   where schemaname = 'realtime' and tablename = 'messages'
     and policyname = 'coordination_private_refresh_receive' and cmd = 'SELECT'),
  1,
  'private Realtime topic has one receive-only policy'
);
select is(
  (select count(*)::integer from pg_policies
   where schemaname = 'realtime' and tablename = 'messages'
     and policyname = 'coordination_private_refresh_receive' and cmd <> 'SELECT'),
  0,
  'private Realtime topic grants no client write policy'
);

insert into auth.users (
  id, instance_id, aud, role, email, encrypted_password, created_at, updated_at
) values
  ('88888888-aaaa-4aaa-8aaa-aaaaaaaaaaa1', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'durable-manager@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp()),
  ('88888888-aaaa-4aaa-8aaa-aaaaaaaaaaa2', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'durable-member@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp());

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  ('88888888-0000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   '88888888-aaaa-4aaa-8aaa-aaaaaaaaaaa1', 'active', 'manager', clock_timestamp()),
  ('88888888-0000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   '88888888-aaaa-4aaa-8aaa-aaaaaaaaaaa2', 'active', 'member', clock_timestamp());

insert into app.employee_profiles (id, company_id, membership_id) values
  ('88888888-e000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   '88888888-0000-4000-8000-000000000001'),
  ('88888888-e000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   '88888888-0000-4000-8000-000000000002');

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt,
  idempotency_key, request_digest
) values (
  '88888888-1000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '88888888-0000-4000-8000-000000000001', 'Exercise the durable worker state machine.',
  'durable-request-fixture-0001', decode(repeat('81', 32), 'hex')
);

select is(
  (select count(*)::integer from app.durable_jobs
   where job_kind = 'interpretation.run'
     and aggregate_id = '88888888-1000-4000-8000-000000000001'),
  1,
  'planning request transactionally enqueues interpretation'
);

create temporary table durable_results (
  label text primary key,
  observed text not null
) on commit drop;
create temporary table first_lease (
  job_id uuid, company_id uuid, job_kind text, aggregate_id uuid, payload jsonb,
  requested_by_membership_id uuid, requested_by_user_id uuid,
  administrative_role text, employee_id uuid, correlation_id uuid,
  attempt_count integer, max_attempts integer, lease_token uuid,
  leased_until timestamptz,demo_run_id uuid,demo_actor_session_id uuid,simulated_employee_id uuid
) on commit drop;
create temporary table second_lease (like first_lease) on commit drop;
create temporary table outbox_lease (like first_lease) on commit drop;
create temporary table expiry_lease (like first_lease) on commit drop;
create temporary table expiry_second_lease (like first_lease) on commit drop;
create temporary table ambiguous_lease (like first_lease) on commit drop;
grant select, insert, update on durable_results, first_lease, second_lease, outbox_lease,
  expiry_lease, expiry_second_lease, ambiguous_lease
  to coordination_api, coordination_worker;

set local role coordination_api;
select set_config('app.actor_id', '88888888-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:durable-ensure', true);
insert into durable_results
select 'ensured-trigger-job', job_id::text from app.ensure_durable_job(
  '11111111-1111-4111-8111-111111111111',
  'interpretation.run',
  '88888888-1000-4000-8000-000000000001',
  'durable-explicit-ensure-0001',
  decode(repeat('80', 32), 'hex'),
  '88888888-c000-4000-8000-000000000080'
);
reset role;

set local role coordination_worker;
insert into first_lease select * from app.lease_durable_jobs(
  '88888888-b000-4000-8000-000000000001', 1, 60
);
insert into durable_results values (
  'first-attempt', (select attempt_count::text from first_lease)
);
reset role;

insert into durable_results values
  ('first-state', (select state from app.durable_jobs
    where id = (select job_id from first_lease))),
  ('attempt-ledger', (select count(*)::text from app.job_attempts
    where job_id = (select job_id from first_lease)));

set local role coordination_worker;
insert into durable_results values
  ('competing-lease-count', (select count(*)::text from app.lease_durable_jobs(
    '88888888-b000-4000-8000-000000000002', 1, 60))),
  ('wrong-renewal', app.renew_durable_job_lease(
    (select company_id from first_lease), (select job_id from first_lease),
    '88888888-b000-4000-8000-000000000001',
    '88888888-bad0-4000-8000-000000000001', 60
  )::text);
insert into durable_results
select 'retry-state', job_state from app.fail_durable_job(
  (select company_id from first_lease), (select job_id from first_lease),
  '88888888-b000-4000-8000-000000000001', (select lease_token from first_lease),
  'fixture_transient', 'fixture_transient', true, false, '{"runtime_ms":4}'::jsonb
);
reset role;

update app.durable_jobs set available_at = clock_timestamp()
where id = (select job_id from first_lease);

set local role coordination_worker;
insert into second_lease select * from app.lease_durable_jobs(
  '88888888-b000-4000-8000-000000000001', 1, 60
);
insert into durable_results values
  ('second-attempt', (select attempt_count::text from second_lease));
insert into durable_results
select 'complete-state', job_state from app.complete_durable_job(
  (select company_id from second_lease), (select job_id from second_lease),
  '88888888-b000-4000-8000-000000000001', (select lease_token from second_lease),
  '{"fixture":"complete"}'::jsonb, decode(repeat('82', 32), 'hex'),
  '{"runtime_ms":3}'::jsonb
);
insert into durable_results
select 'completion-replayed', replayed::text from app.complete_durable_job(
  (select company_id from second_lease), (select job_id from second_lease),
  '88888888-b000-4000-8000-000000000001', (select lease_token from second_lease),
  '{"fixture":"complete"}'::jsonb, decode(repeat('82', 32), 'hex'),
  '{"runtime_ms":3}'::jsonb
);
do $$
begin
  begin
    perform app.complete_durable_job(
      (select company_id from second_lease), (select job_id from second_lease),
      '88888888-b000-4000-8000-000000000001', (select lease_token from second_lease),
      '{"fixture":"different"}'::jsonb, decode(repeat('83', 32), 'hex'), '{}'::jsonb
    );
    insert into durable_results values ('completion-conflict', 'false');
  exception when serialization_failure then
    insert into durable_results values ('completion-conflict', 'true');
  end;
end
$$;
reset role;

insert into app.durable_jobs (
  id, company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
  idempotency_key, command_digest, correlation_id, max_attempts
) values (
  '88888888-9000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  'interpretation.run', '88888888-9100-4000-8000-000000000001', '{}'::jsonb,
  '88888888-0000-4000-8000-000000000001', 'lease-expiry-fixture-0001',
  decode(repeat('90', 32), 'hex'), '88888888-c000-4000-8000-000000000090', 2
);

set local role coordination_worker;
insert into expiry_lease select * from app.lease_durable_jobs(
  '88888888-b000-4000-8000-000000000003', 1, 60
);
reset role;
update app.durable_jobs set leased_until = clock_timestamp() - interval '1 second'
where id = '88888888-9000-4000-8000-000000000001';
set local role coordination_worker;
select app.reconcile_expired_durable_jobs();
reset role;
insert into durable_results values
  ('expiry-retry-state', (select state from app.durable_jobs
    where id = '88888888-9000-4000-8000-000000000001')),
  ('expiry-attempt-outcome', (select outcome from app.job_attempts
    where job_id = '88888888-9000-4000-8000-000000000001' and attempt_number = 1)),
  ('expiry-backoff-bounded', (select (available_at <= clock_timestamp()
    and available_at >= clock_timestamp() - interval '5 seconds')::text
    from app.durable_jobs where id = '88888888-9000-4000-8000-000000000001'));

set local role coordination_worker;
insert into expiry_second_lease select * from app.lease_durable_jobs(
  '88888888-b000-4000-8000-000000000003', 1, 60
);
reset role;
update app.durable_jobs set leased_until = clock_timestamp() - interval '1 second'
where id = '88888888-9000-4000-8000-000000000001';
set local role coordination_worker;
select app.reconcile_expired_durable_jobs();
reset role;
insert into durable_results values
  ('expiry-dead-letter-state', (select state from app.durable_jobs
    where id = '88888888-9000-4000-8000-000000000001')),
  ('expiry-second-outcome', (select outcome from app.job_attempts
    where job_id = '88888888-9000-4000-8000-000000000001' and attempt_number = 2));

insert into app.durable_jobs (
  id, company_id, job_kind, aggregate_id, payload, requested_by_membership_id,
  idempotency_key, command_digest, correlation_id
) values (
  '88888888-9000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
  'interpretation.run', '88888888-9100-4000-8000-000000000002', '{}'::jsonb,
  '88888888-0000-4000-8000-000000000001', 'ambiguous-fixture-job-0001',
  decode(repeat('91', 32), 'hex'), '88888888-c000-4000-8000-000000000091'
);
set local role coordination_worker;
insert into ambiguous_lease select * from app.lease_durable_jobs(
  '88888888-b000-4000-8000-000000000004', 1, 60
);
insert into durable_results
select 'ambiguous-review-state', job_state from app.fail_durable_job(
  (select company_id from ambiguous_lease), (select job_id from ambiguous_lease),
  '88888888-b000-4000-8000-000000000004', (select lease_token from ambiguous_lease),
  'fixture_ambiguous', 'fixture_ambiguous', false, true, '{}'::jsonb
);
reset role;

insert into app.retrieval_runs (
  id, company_id, request_id, actor_membership_id, purpose, allowed_scope,
  selected_manifest, omitted_manifest, missing_manifest, projection_digest,
  projection_characters, status, started_at, completed_at
) values (
  '88888888-2000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '88888888-1000-4000-8000-000000000001', '88888888-0000-4000-8000-000000000001',
  'durable-test', '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
  decode(repeat('84', 32), 'hex'), 10, 'complete', clock_timestamp(), clock_timestamp()
);
insert into app.interpretation_runs (
  id, company_id, request_id, retrieval_run_id, model_id, sdk_version,
  prompt_version, schema_version, safety_profile, configuration, status,
  outcome, started_at, completed_at
) values (
  '88888888-3000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '88888888-1000-4000-8000-000000000001', '88888888-2000-4000-8000-000000000001',
  'fixture', 'fixture', 'fixture', 'candidate-task-contract.v1', 'no-tools',
  '{}'::jsonb, 'completed', 'admitted', clock_timestamp(), clock_timestamp()
);
insert into app.candidate_contracts (
  id, company_id, request_id, interpretation_run_id, contract_json,
  contract_digest, admission_status, validation_issues
) values (
  '88888888-4000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '88888888-1000-4000-8000-000000000001', '88888888-3000-4000-8000-000000000001',
  '{"schema_version":"candidate-task-contract.v1"}'::jsonb,
  decode(repeat('85', 32), 'hex'), 'admitted', '[]'::jsonb
);
insert into app.planning_snapshots (
  id, company_id, request_id, candidate_contract_id, schema_version,
  base_company_revision, horizon_start, horizon_end, slot_minutes,
  source_manifest_digest, permission_revision, profile_revision, estimate_revision,
  compiler_version, policy, normalized_snapshot, snapshot_digest, frozen_at
) values (
  '88888888-5000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '88888888-1000-4000-8000-000000000001', '88888888-4000-4000-8000-000000000001',
  'planning-snapshot.v1', 0, '2026-09-28 09:00:00+00', '2026-09-28 10:00:00+00', 30,
  decode(repeat('86', 32), 'hex'), 'permissions:1', 'profiles:1', 'estimates:1',
  'coordination-z3-compiler.v1', '{}'::jsonb, '{}'::jsonb,
  decode(repeat('87', 32), 'hex'), clock_timestamp()
);
insert into app.solver_runs (
  id, company_id, snapshot_id, scope, application_classification, raw_status,
  termination, model_digest, compiler_version, solver_version, validator_version,
  timeout_ms, resource_limit, runtime_ms, objective_vector,
  diagnostic_constraint_keys, validation_report, started_at, completed_at
) values (
  '88888888-6000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '88888888-5000-4000-8000-000000000001', 'pinned_insertion', 'FEASIBLE', 'sat',
  'completed', decode(repeat('88', 32), 'hex'), 'coordination-z3-compiler.v1',
  'fixture-z3', 'coordination-schedule-validator.v1', 1000, 100000, 2,
  '[]'::jsonb, '[]'::jsonb, '{"valid":true}'::jsonb,
  clock_timestamp(), clock_timestamp()
);
insert into app.plans (
  id, company_id, request_id, snapshot_id, solver_run_id,
  state, classification, proposal_digest
) values (
  '88888888-7000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  '88888888-1000-4000-8000-000000000001', '88888888-5000-4000-8000-000000000001',
  '88888888-6000-4000-8000-000000000001', 'proposed', 'FEASIBLE',
  decode(repeat('89', 32), 'hex')
);

select is(
  (select count(*)::integer from app.durable_jobs
   where job_kind = 'planning.run'
     and aggregate_id = '88888888-5000-4000-8000-000000000001'),
  1,
  'frozen snapshot transactionally enqueues real solver work'
);

insert into app.outbox_intents (
  id, company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id
) values (
  '88888888-8000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  'plan.committed', 'plan', '88888888-7000-4000-8000-000000000001',
  '{"plan_id":"88888888-7000-4000-8000-000000000001"}'::jsonb,
  '88888888-c000-4000-8000-000000000001'
);
update app.durable_jobs set priority = case
  when job_kind = 'outbox.deliver' then 100 else 0 end
where aggregate_id in (
  '88888888-5000-4000-8000-000000000001',
  '88888888-8000-4000-8000-000000000001'
);

select is(
  (select count(*)::integer from app.durable_jobs
   where job_kind = 'outbox.deliver'
     and aggregate_id = '88888888-8000-4000-8000-000000000001'),
  1,
  'outbox intent transactionally enqueues delivery'
);

set local role coordination_worker;
insert into outbox_lease select * from app.lease_durable_jobs(
  '88888888-b000-4000-8000-000000000001', 1, 60
);
insert into durable_results
select 'notification-count', notification_count::text
from app.deliver_internal_outbox_intent(
  (select company_id from outbox_lease), (select aggregate_id from outbox_lease),
  (select job_id from outbox_lease), (select lease_token from outbox_lease)
);
do $$
begin
  perform app.complete_durable_job(
    (select company_id from outbox_lease), (select job_id from outbox_lease),
    '88888888-b000-4000-8000-000000000001', (select lease_token from outbox_lease),
    '{"notification_count":1}'::jsonb, decode(repeat('8a', 32), 'hex'), '{}'::jsonb
  );
end
$$;
reset role;

select is(
  (select state from app.outbox_intents
   where id = '88888888-8000-4000-8000-000000000001'),
  'delivered',
  'leased outbox intent reaches delivered state'
);
select is(
  (select count(*)::integer from app.notifications
   where origin_outbox_intent_id = '88888888-8000-4000-8000-000000000001'),
  1,
  'outbox delivery persists one authorised recipient notification'
);
select is(
  (select safe_parameters::text from app.notifications
   where origin_outbox_intent_id = '88888888-8000-4000-8000-000000000001'),
  '{}',
  'persisted notification contains no sensitive payload fields'
);
select ok(
  (select refresh_emitted_at is not null from app.notifications
   where origin_outbox_intent_id = '88888888-8000-4000-8000-000000000001'),
  'notification emits a private refresh hint when local Realtime is available'
);

set local role coordination_api;
select set_config('app.actor_id', '88888888-aaaa-4aaa-8aaa-aaaaaaaaaaa2', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:notification-isolation', true);
insert into durable_results values (
  'member-notification-count', (select count(*)::text from app.notifications)
);
reset role;

set local role coordination_api;
select set_config('app.actor_id', '88888888-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:notification-ack', true);
insert into durable_results
select 'notification-ack-complete',
  (delivered_at is not null and seen_at is not null and acknowledged_at is not null)::text
from app.advance_notification_state(
  '11111111-1111-4111-8111-111111111111',
  (select id from app.notifications
   where origin_outbox_intent_id = '88888888-8000-4000-8000-000000000001'),
  'acknowledged'
);
reset role;

update app.durable_jobs set state = 'cancelled', completed_at = clock_timestamp(),
  last_error_code = 'fixture_cancelled'
where job_kind = 'planning.run'
  and aggregate_id = '88888888-5000-4000-8000-000000000001';

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt,
  idempotency_key, request_digest
) values
  ('88888888-1000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   '88888888-0000-4000-8000-000000000001', 'This request will lose manager authority.',
   'durable-request-fixture-0002', decode(repeat('8b', 32), 'hex')),
  ('88888888-1000-4000-8000-000000000003', '11111111-1111-4111-8111-111111111111',
   '88888888-0000-4000-8000-000000000001', 'This request will be cancelled.',
   'durable-request-fixture-0003', decode(repeat('8c', 32), 'hex'));

set local role coordination_api;
select set_config('app.actor_id', '88888888-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:durable-cancel', true);
insert into durable_results
select 'cancel-state', state from app.request_durable_job_cancellation(
  '11111111-1111-4111-8111-111111111111',
  (select id from app.durable_jobs
   where aggregate_id = '88888888-1000-4000-8000-000000000003'),
  'No longer required', 'durable-cancel-key-0001', decode(repeat('8d', 32), 'hex')
);
reset role;

update app.company_memberships set administrative_role = 'member'
where id = '88888888-0000-4000-8000-000000000001';

set local role coordination_worker;
insert into durable_results values (
  'revoked-lease-count', (select count(*)::text from app.lease_durable_jobs(
    '88888888-b000-4000-8000-000000000001', 8, 60
  ))
);
reset role;

select is((select observed from durable_results where label = 'first-state'),
  'leased', 'ready work is atomically leased');
select is(
  (select observed from durable_results where label = 'ensured-trigger-job'),
  (select id::text from app.durable_jobs
   where job_kind = 'interpretation.run'
     and aggregate_id = '88888888-1000-4000-8000-000000000001'),
  'explicit ensure returns the interpretation job created by the request trigger'
);
select is((select observed from durable_results where label = 'first-attempt'),
  '1', 'first lease increments the attempt counter');
select is((select observed from durable_results where label = 'attempt-ledger'),
  '1', 'lease creates an immutable attempt ledger row');
select is((select observed from durable_results where label = 'competing-lease-count'),
  '0', 'a competing worker cannot lease active work');
select is((select observed from durable_results where label = 'wrong-renewal'),
  'false', 'wrong lease token cannot renew work');
select is((select observed from durable_results where label = 'retry-state'),
  'retry_scheduled', 'retryable failure schedules bounded retry');
select is((select observed from durable_results where label = 'second-attempt'),
  '2', 'retry receives a new fenced attempt');
select is((select observed from durable_results where label = 'complete-state'),
  'succeeded', 'leased work completes durably');
select is((select observed from durable_results where label = 'completion-replayed'),
  'true', 'matching terminal completion safely replays');
select is((select observed from durable_results where label = 'completion-conflict'),
  'true', 'conflicting terminal completion is rejected');
select is((select observed from durable_results where label = 'expiry-retry-state'),
  'retry_scheduled', 'an expired non-final lease becomes retryable');
select is((select observed from durable_results where label = 'expiry-attempt-outcome'),
  'lease_expired', 'expired attempt is closed in the immutable ledger');
select is((select observed from durable_results where label = 'expiry-backoff-bounded'),
  'true', 'lease-expiry retry is immediately available within a bounded window');
select is((select observed from durable_results where label = 'expiry-dead-letter-state'),
  'dead_letter', 'max-attempt lease expiry reaches dead letter');
select is((select observed from durable_results where label = 'expiry-second-outcome'),
  'lease_expired', 'final expired attempt retains its explicit outcome');
select is((select observed from durable_results where label = 'ambiguous-review-state'),
  'review_required', 'ambiguous side-effect outcome stops for human review');
select is((select observed from durable_results where label = 'notification-count'),
  '1', 'outbox targets only currently authorised recipients');
select is((select observed from durable_results where label = 'member-notification-count'),
  '0', 'recipient RLS hides another member notification');
select is((select observed from durable_results where label = 'notification-ack-complete'),
  'true', 'notification acknowledgement advances every prior delivery state');
select is((select observed from durable_results where label = 'cancel-state'),
  'cancelled', 'manager cancellation terminates queued work');
select is((select observed from durable_results where label = 'revoked-lease-count'),
  '0', 'worker does not lease planning work after requester authority is revoked');
select is(
  (select state from app.durable_jobs
   where aggregate_id = '88888888-1000-4000-8000-000000000002'),
  'review_required',
  'revoked requester work is quarantined for review'
);
select is(
  (select last_error_code from app.durable_jobs
   where aggregate_id = '88888888-1000-4000-8000-000000000002'),
  'requester_authority_revoked',
  'quarantined work records a stable non-sensitive reason'
);
select ok(
  not has_function_privilege(
    'anon', 'app.reconcile_unauthorised_durable_jobs()', 'EXECUTE'
  ),
  'Data API anonymous role cannot invoke worker reconciliation'
);
select ok(
  has_function_privilege(
    'coordination_worker', 'app.reconcile_unauthorised_durable_jobs()', 'EXECUTE'
  ),
  'worker can invoke requester-authority reconciliation'
);
select ok(
  not has_function_privilege(
    'coordination_worker',
    'app.ensure_durable_job(uuid,text,uuid,text,bytea,uuid)',
    'EXECUTE'
  ),
  'worker cannot invoke the manager durable-job command function'
);

select * from finish();
rollback;
