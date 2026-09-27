-- Local/disposable database only. Every fixture and mutation is rolled back.
begin;
select no_plan();

create temporary table renewal_results(label text, expected boolean, actual boolean) on commit drop;
grant insert, select on renewal_results to coordination_worker;

-- Queue renewal uses worker_transaction (no actor/company selection), not a
-- tenant business transaction. The function still receives its exact company ID.
select set_config('app.company_id', '', true),
  set_config('app.demo_run_id', '', true), set_config('app.demo_actor_session_id', '', true),
  set_config('app.actor_id', '', true), set_config('app.purpose', 'test:lease-renewal', true);

-- Ordinary-scope operator-owned queue rows need no invented Auth account, request,
-- model output or scenario completion. A job has no outbox counterpart here.
insert into app.durable_jobs(
  id, company_id, job_kind, aggregate_id, payload, idempotency_key, command_digest,
  correlation_id, state, attempt_count, lease_owner, lease_token, leased_at, leased_until
)
values (
  '14141414-1000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  'interpretation.run', '14141414-2000-4000-8000-000000000001', '{}',
  'lease-renewal-regression-ordinary', decode(repeat('14', 32), 'hex'), gen_random_uuid(),
  'leased', 1, '14141414-3000-4000-8000-000000000001',
  '14141414-4000-4000-8000-000000000001', clock_timestamp(),
  clock_timestamp() + interval '30 seconds'
);

create function pg_temp.renew_test_job(
  p_worker uuid default '14141414-3000-4000-8000-000000000001',
  p_token uuid default '14141414-4000-4000-8000-000000000001',
  p_company uuid default '11111111-1111-4111-8111-111111111111'
) returns boolean language sql as $$
  select app.renew_durable_job_lease(p_company,
    '14141414-1000-4000-8000-000000000001', p_worker, p_token, 120)
$$;

set local role coordination_worker;
insert into renewal_results values
  ('non-outbox job renewal reports success', true, pg_temp.renew_test_job()),
  ('wrong worker cannot renew', false,
    pg_temp.renew_test_job(p_worker => '14141414-3000-4000-8000-000000000002')),
  ('wrong token cannot renew', false,
    pg_temp.renew_test_job(p_token => '14141414-4000-4000-8000-000000000002')),
  ('wrong company cannot renew', false,
    pg_temp.renew_test_job(p_company => '14141414-5000-4000-8000-000000000001'));
reset role;

select is((select row_version from app.durable_jobs
  where id = '14141414-1000-4000-8000-000000000001'), 2::bigint,
  'only the valid renewal updates the job revision');
select ok((select leased_until > clock_timestamp() + interval '90 seconds'
  from app.durable_jobs where id = '14141414-1000-4000-8000-000000000001'),
  'successful ordinary renewal extends the actual lease');

-- Exact current-scope fencing is retained even for an otherwise valid lease token.
select set_config('app.company_id', '11111111-1111-4111-8111-111111111111', true),
  set_config('app.demo_run_id', '14141414-6000-4000-8000-000000000001', true);
set local role coordination_worker;
insert into renewal_results values ('different selected run cannot renew', false,
  pg_temp.renew_test_job());
reset role;
select set_config('app.demo_run_id', '', true), set_config('app.company_id', '', true);

update app.durable_jobs set leased_until = clock_timestamp() - interval '1 second'
where id = '14141414-1000-4000-8000-000000000001';
set local role coordination_worker;
insert into renewal_results values ('expired lease cannot renew', false, pg_temp.renew_test_job());
reset role;

update app.durable_jobs set state = 'review_required', completed_at = clock_timestamp(),
  lease_owner = null, lease_token = null, leased_at = null, leased_until = null
where id = '14141414-1000-4000-8000-000000000001';
set local role coordination_worker;
insert into renewal_results values ('terminal job cannot renew', false, pg_temp.renew_test_job());
reset role;

update app.durable_jobs set state = 'cancelled'
where id = '14141414-1000-4000-8000-000000000001';
set local role coordination_worker;
insert into renewal_results values ('cancelled job cannot renew', false, pg_temp.renew_test_job());
reset role;

-- Normal outbox lease synchronization remains intact. The enqueue trigger creates
-- its queue row; this transaction never runs a worker or delivers the fixture intent.
insert into app.outbox_intents(
  id, company_id, intent_kind, aggregate_type, aggregate_id, payload, correlation_id,
  state, lease_owner, lease_token, leased_until
)
values (
  '14141414-7000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111',
  'task.changed', 'task', '14141414-8000-4000-8000-000000000001', '{}', gen_random_uuid(),
  'leased', '14141414-3000-4000-8000-000000000001',
  '14141414-4000-4000-8000-000000000003', clock_timestamp() + interval '30 seconds'
);
update app.durable_jobs set state = 'leased', attempt_count = 1,
  lease_owner = '14141414-3000-4000-8000-000000000001',
  lease_token = '14141414-4000-4000-8000-000000000003', leased_at = clock_timestamp(),
  leased_until = clock_timestamp() + interval '30 seconds'
where company_id = '11111111-1111-4111-8111-111111111111'
  and job_kind = 'outbox.deliver' and aggregate_id = '14141414-7000-4000-8000-000000000001';
create temporary table renewal_outbox_job as
  select id from app.durable_jobs where company_id = '11111111-1111-4111-8111-111111111111'
  and job_kind = 'outbox.deliver' and aggregate_id = '14141414-7000-4000-8000-000000000001';
grant select on renewal_outbox_job to coordination_worker;

set local role coordination_worker;
insert into renewal_results values ('outbox job renewal also reports success', true,
  app.renew_durable_job_lease('11111111-1111-4111-8111-111111111111',
    (select id from renewal_outbox_job), '14141414-3000-4000-8000-000000000001',
    '14141414-4000-4000-8000-000000000003', 120));
reset role;
select ok((select job.leased_until = intent.leased_until
  from app.durable_jobs job join app.outbox_intents intent on intent.company_id = job.company_id
    and intent.id = job.aggregate_id where job.id = (select id from renewal_outbox_job)),
  'outbox and job lease timestamps remain synchronized');

select is(actual, expected, label) from renewal_results order by label;
select ok(has_function_privilege('coordination_worker',
  'app.renew_durable_job_lease(uuid,uuid,uuid,uuid,integer)', 'EXECUTE'),
  'worker retains renewal execute permission');
select ok(not has_function_privilege('coordination_api',
  'app.renew_durable_job_lease(uuid,uuid,uuid,uuid,integer)', 'EXECUTE'),
  'API cannot renew worker leases');
select ok(not has_function_privilege('anon',
  'app.renew_durable_job_lease(uuid,uuid,uuid,uuid,integer)', 'EXECUTE'),
  'anonymous users cannot renew worker leases');

select * from finish();
rollback;
