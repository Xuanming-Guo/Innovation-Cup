-- Local/disposable database only. Every fixture and mutation is rolled back.
begin;
select plan(9);

insert into auth.users(id,instance_id,aud,role,email,created_at,updated_at) values
 ('18181818-aaaa-4aaa-8aaa-aaaaaaaaaaa1','00000000-0000-0000-0000-000000000000',
  'authenticated','authenticated','expired-job@example.invalid',now(),now());
insert into app.company_memberships(
 id,company_id,user_id,membership_status,administrative_role,joined_at
) values (
 '18181818-1000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '18181818-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','manager',now()
);
insert into app.employee_profiles(
 id,company_id,profile_kind,synthetic_key,display_name,function_key,scenario_detail
) values (
 '18181818-2000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 'synthetic','maya','Maya','leadership','rich'
);
insert into app.demo_runs(
 id,company_id,owner_membership_id,scenario_key,scenario_version,mode,idempotency_key
) values (
 '18181818-3000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '18181818-1000-4000-8000-000000000001','northstar-launch',1,'live',
 'expired-job-run-fixture'
);
insert into app.demo_run_memberships(company_id,run_id,membership_id,run_role) values (
 '11111111-1111-4111-8111-111111111111','18181818-3000-4000-8000-000000000001',
 '18181818-1000-4000-8000-000000000001','owner'
);
insert into app.demo_actor_sessions(
 id,company_id,run_id,performed_by_auth_user_id,simulated_actor_employee_id
) values (
 '18181818-4000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '18181818-3000-4000-8000-000000000001','18181818-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
 '18181818-2000-4000-8000-000000000001'
);

select set_config('app.actor_id','18181818-aaaa-4aaa-8aaa-aaaaaaaaaaa1',true),
 set_config('app.company_id','11111111-1111-4111-8111-111111111111',true),
 set_config('app.purpose','test:expired-job',true),
 set_config('app.demo_run_id','18181818-3000-4000-8000-000000000001',true),
 set_config('app.demo_actor_session_id','18181818-4000-4000-8000-000000000001',true);

insert into app.planning_requests(
 id,company_id,requester_membership_id,original_prompt,status,idempotency_key,request_digest
) values (
 '18181818-5000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '18181818-1000-4000-8000-000000000001','Reconcile an expired interpretation lease.',
 'interpretation_running','expired-job-request-fixture',decode(repeat('18',32),'hex')
);
insert into app.retrieval_runs(
 id,company_id,request_id,actor_membership_id,purpose,allowed_scope,selected_manifest,
 omitted_manifest,missing_manifest,projection_digest,projection_characters,status,
 started_at,completed_at
) values (
 '18181818-6000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '18181818-5000-4000-8000-000000000001','18181818-1000-4000-8000-000000000001',
 'expired-job-test','{}','[]','[]','[]',decode(repeat('19',32),'hex'),1,'complete',now(),now()
);
insert into app.interpretation_runs(
 id,company_id,request_id,retrieval_run_id,model_id,sdk_version,prompt_version,
 schema_version,safety_profile,configuration,status,started_at
) values (
 '18181818-7000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '18181818-5000-4000-8000-000000000001','18181818-6000-4000-8000-000000000001',
 'fixture','fixture','fixture','candidate-task-contract.v1','no-tools','{}','running',now()
);

update app.durable_jobs
set state='leased', attempt_count=1,
 lease_owner='18181818-8000-4000-8000-000000000001',
 lease_token='18181818-9000-4000-8000-000000000001', leased_at=now()-interval '2 minutes',
 leased_until=now()-interval '1 minute'
where job_kind='interpretation.run'
  and aggregate_id='18181818-5000-4000-8000-000000000001';
insert into app.job_attempts(
 company_id,demo_run_id,job_id,attempt_number,lease_token,worker_id,started_at
) select company_id,demo_run_id,id,1,lease_token,lease_owner,leased_at
from app.durable_jobs where job_kind='interpretation.run'
  and aggregate_id='18181818-5000-4000-8000-000000000001';

select set_config('app.actor_id','',true),set_config('app.company_id','',true),
 set_config('app.purpose','',true),set_config('app.demo_run_id','',true),
 set_config('app.demo_actor_session_id','',true);
create temporary table expired_reconciliation_result(value integer) on commit drop;
grant insert,select on expired_reconciliation_result to coordination_worker;
set local role coordination_worker;
insert into expired_reconciliation_result select app.reconcile_expired_durable_jobs();
reset role;

select is((select value from expired_reconciliation_result),1,
 'worker reconciles the expired scoped job');
select is((select state from app.durable_jobs where aggregate_id='18181818-5000-4000-8000-000000000001'),
 'retry_scheduled','expired job becomes retryable');
select is((select outcome from app.job_attempts where job_id=(select id from app.durable_jobs
 where aggregate_id='18181818-5000-4000-8000-000000000001')),'lease_expired',
 'attempt records lease expiry');
select is((select status from app.interpretation_runs where id='18181818-7000-4000-8000-000000000001'),
 'failed','running interpretation is closed');
select is((select outcome from app.interpretation_runs where id='18181818-7000-4000-8000-000000000001'),
 'transient_failure','interpretation uses a schema-valid transient outcome');
select is((select error_code from app.interpretation_runs where id='18181818-7000-4000-8000-000000000001'),
 'worker_lease_lost','interpretation retains the precise failure code');
select is((select status from app.planning_requests where id='18181818-5000-4000-8000-000000000001'),
 'failed','request is ready for its durable retry');
select ok(app.current_company_id() is null and app.current_demo_run_id() is null
 and app.current_actor_id() is null,'reconciliation restores the unscoped worker context');
select ok(has_function_privilege('coordination_worker','app.reconcile_expired_durable_jobs()','EXECUTE')
 and not has_function_privilege('coordination_api','app.reconcile_expired_durable_jobs()','EXECUTE'),
 'only the worker can execute expiry reconciliation');

select * from finish();
rollback;
