begin;
select plan(14);

select has_table('app', 'durable_job_recoveries', 'durable recovery ledger exists');
select has_function(
  'app', 'retry_durable_planning_job',
  array['uuid', 'uuid', 'text', 'text', 'bytea'],
  'manager recovery command exists'
);
select ok(
  has_function_privilege(
    'coordination_api',
    'app.retry_durable_planning_job(uuid,uuid,text,text,bytea)',
    'EXECUTE'
  ),
  'API role can execute the guarded recovery command'
);
select ok(
  not has_function_privilege(
    'coordination_worker',
    'app.retry_durable_planning_job(uuid,uuid,text,text,bytea)',
    'EXECUTE'
  ),
  'worker cannot issue manager recovery commands'
);
select ok(
  not has_table_privilege(
    'coordination_api', 'app.durable_job_recoveries', 'SELECT'
  ),
  'API role has no direct recovery-ledger access'
);

insert into auth.users (
  id, instance_id, aud, role, email, encrypted_password, created_at, updated_at
) values
  ('bbbbbbbb-aaaa-4aaa-8aaa-aaaaaaaaaaa1', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'recovery-manager@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp()),
  ('bbbbbbbb-aaaa-4aaa-8aaa-aaaaaaaaaaa2', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'recovery-member@example.invalid',
   extensions.crypt('local-test-only', extensions.gen_salt('bf')),
   clock_timestamp(), clock_timestamp());

insert into app.company_memberships (
  id, company_id, user_id, membership_status, administrative_role, joined_at
) values
  ('bbbbbbbb-0000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   'bbbbbbbb-aaaa-4aaa-8aaa-aaaaaaaaaaa1', 'active', 'manager', clock_timestamp()),
  ('bbbbbbbb-0000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   'bbbbbbbb-aaaa-4aaa-8aaa-aaaaaaaaaaa2', 'active', 'member', clock_timestamp());

insert into app.planning_requests (
  id, company_id, requester_membership_id, original_prompt,
  idempotency_key, request_digest
) values
  ('bbbbbbbb-1000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
   'bbbbbbbb-0000-4000-8000-000000000001', 'Recover a reviewed interpretation.',
   'recovery-request-fixture-0001', decode(repeat('b1', 32), 'hex')),
  ('bbbbbbbb-1000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111',
   'bbbbbbbb-0000-4000-8000-000000000001', 'Keep member recovery forbidden.',
   'recovery-request-fixture-0002', decode(repeat('b2', 32), 'hex'));

update app.durable_jobs
set state = 'review_required', attempt_count = 1,
    last_error_code = 'model_bad_request',
    last_error_message = 'safe fixture error', completed_at = clock_timestamp()
where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001';
update app.durable_jobs
set state = 'dead_letter', attempt_count = max_attempts,
    last_error_code = 'fixture_exhausted',
    last_error_message = 'safe fixture error', completed_at = clock_timestamp()
where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000002';

create temporary table recovery_results (
  label text primary key,
  observed text not null
) on commit drop;
grant insert, select on recovery_results to coordination_api;

set local role coordination_api;
select set_config('app.actor_id', 'bbbbbbbb-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:durable-recovery', true);
insert into recovery_results
select 'first-state', state from app.retry_durable_planning_job(
  '11111111-1111-4111-8111-111111111111',
  (select id from app.durable_jobs
   where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001'),
  'Provider request schema was corrected.', 'recovery-command-key-0001',
  decode(repeat('b3', 32), 'hex')
);
insert into recovery_results
select 'replay-state', state from app.retry_durable_planning_job(
  '11111111-1111-4111-8111-111111111111',
  (select id from app.durable_jobs
   where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001'),
  'Provider request schema was corrected.', 'recovery-command-key-0001',
  decode(repeat('b3', 32), 'hex')
);
do $$
begin
  begin
    perform app.retry_durable_planning_job(
      '11111111-1111-4111-8111-111111111111',
      (select id from app.durable_jobs
       where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001'),
      'Conflicting replay.', 'recovery-command-key-0001',
      decode(repeat('b4', 32), 'hex')
    );
    insert into recovery_results values ('idempotency-conflict', 'false');
  exception when serialization_failure then
    insert into recovery_results values ('idempotency-conflict', 'true');
  end;
end
$$;
reset role;

set local role coordination_api;
select set_config('app.actor_id', 'bbbbbbbb-aaaa-4aaa-8aaa-aaaaaaaaaaa2', true);
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true);
select set_config('app.purpose', 'test:durable-recovery-denied', true);
do $$
begin
  begin
    perform app.retry_durable_planning_job(
      '11111111-1111-4111-8111-111111111111',
      (select id from app.durable_jobs
       where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000002'),
      'Member must not recover jobs.', 'recovery-command-key-0002',
      decode(repeat('b5', 32), 'hex')
    );
    insert into recovery_results values ('member-denied', 'false');
  exception when insufficient_privilege then
    insert into recovery_results values ('member-denied', 'true');
  end;
end
$$;
reset role;

select is((select observed from recovery_results where label = 'first-state'),
  'queued', 'manager can deliberately requeue a side-effect-free planning stage');
select is((select observed from recovery_results where label = 'replay-state'),
  'queued', 'identical recovery command replays idempotently');
select is((select observed from recovery_results where label = 'idempotency-conflict'),
  'true', 'conflicting recovery command reuse is rejected');
select is((select observed from recovery_results where label = 'member-denied'),
  'true', 'ordinary member cannot recover durable jobs');
select is(
  (select attempt_count::text from app.durable_jobs
   where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001'),
  '1', 'recovery preserves the immutable attempt count'
);
select is(
  (select max_attempts::text from app.durable_jobs
   where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001'),
  '7', 'recovery grants a bounded six-attempt retry window'
);
select is(
  (select concat_ws('|', last_error_code, completed_at::text)
   from app.durable_jobs
   where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001'),
  '', 'recovery clears terminal error and completion fields'
);
select is(
  (select count(*)::text from app.durable_job_recoveries
   where job_id = (select id from app.durable_jobs
     where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001')),
  '1', 'recovery records one immutable audit row'
);
select is(
  (select prior_state || '|' || prior_error_code from app.durable_job_recoveries
   where job_id = (select id from app.durable_jobs
     where aggregate_id = 'bbbbbbbb-1000-4000-8000-000000000001')),
  'review_required|model_bad_request',
  'recovery audit retains the prior terminal state and safe error code'
);

select * from finish();
rollback;
