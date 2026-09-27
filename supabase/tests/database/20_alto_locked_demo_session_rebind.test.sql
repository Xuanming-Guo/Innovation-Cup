-- Local/disposable database only. Every fixture and mutation is rolled back.
begin;
select plan(5);

create temporary table rebind_results(label text,value text) on commit drop;
grant insert,select on rebind_results to coordination_worker;

insert into auth.users(id,instance_id,aud,role,email,created_at,updated_at) values
 ('20202020-aaaa-4aaa-8aaa-aaaaaaaaaaa1','00000000-0000-0000-0000-000000000000',
  'authenticated','authenticated','rebind@example.invalid',now(),now());
insert into app.company_memberships(
 id,company_id,user_id,membership_status,administrative_role,joined_at
) values (
 '20202020-1000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '20202020-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','manager',now()
);
insert into app.employee_profiles(
 id,company_id,profile_kind,synthetic_key,display_name,function_key,scenario_detail
) values (
 '20202020-2000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 'synthetic','rebind-maya','Maya','leadership','rich'
);
insert into app.demo_workspace_policies(company_id,enabled,scenario_key,scenario_version)
values('11111111-1111-4111-8111-111111111111',true,'northstar-launch',1)
on conflict(company_id) do update set enabled=true,scenario_key=excluded.scenario_key,
 scenario_version=excluded.scenario_version;
insert into app.demo_runs(
 id,company_id,owner_membership_id,scenario_key,scenario_version,mode,idempotency_key
) values (
 '20202020-3000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '20202020-1000-4000-8000-000000000001','northstar-launch',1,'live','session-rebind-run'
);
insert into app.demo_run_memberships(company_id,run_id,membership_id,run_role) values (
 '11111111-1111-4111-8111-111111111111','20202020-3000-4000-8000-000000000001',
 '20202020-1000-4000-8000-000000000001','owner'
);
insert into app.demo_actor_sessions(
 id,company_id,run_id,performed_by_auth_user_id,simulated_actor_employee_id,revoked_at
) values
 ('20202020-4000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
  '20202020-3000-4000-8000-000000000001','20202020-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
  '20202020-2000-4000-8000-000000000001',now()),
 ('20202020-4000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111',
  '20202020-3000-4000-8000-000000000001','20202020-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
  '20202020-2000-4000-8000-000000000001',null);
insert into app.durable_jobs(
 id,company_id,demo_run_id,job_kind,aggregate_id,payload,requested_by_membership_id,
 idempotency_key,command_digest,correlation_id
) values
 ('20202020-5000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
  '20202020-3000-4000-8000-000000000001','interpretation.run',gen_random_uuid(),'{}',
  '20202020-1000-4000-8000-000000000001','rebind-planning-job',
  decode(repeat('20',32),'hex'),gen_random_uuid()),
 ('20202020-5000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111',
  '20202020-3000-4000-8000-000000000001','assistant.respond',gen_random_uuid(),'{}',
  '20202020-1000-4000-8000-000000000001','rebind-assistant-job',
  decode(repeat('21',32),'hex'),gen_random_uuid());
update app.durable_jobs
set demo_actor_session_id='20202020-4000-4000-8000-000000000001',
    simulated_employee_id='20202020-2000-4000-8000-000000000001'
where id in (
 '20202020-5000-4000-8000-000000000001',
 '20202020-5000-4000-8000-000000000002'
);

set local role coordination_worker;
insert into rebind_results values
 ('changed',app.reconcile_unauthorised_durable_jobs()::text);
-- The STABLE authorization function reads the calling statement's snapshot.
-- Check it after reconciliation, as the worker's separate lease query does.
insert into rebind_results values
 ('planning_authorized',app.alto_job_authorized(
   '11111111-1111-4111-8111-111111111111',
   '20202020-5000-4000-8000-000000000001')::text);
reset role;

select is((select value from rebind_results where label='changed'),'1',
 'only the non-planning job is rejected');
select is((select demo_actor_session_id::text from app.durable_jobs
 where id='20202020-5000-4000-8000-000000000001'),
 '20202020-4000-4000-8000-000000000002','planning job binds the current persona session');
select is((select state from app.durable_jobs
 where id='20202020-5000-4000-8000-000000000001'),'queued',
 'rebound planning job remains queued');
select is((select value from rebind_results where label='planning_authorized'),'true',
 'rebound planning job passes strict authorization');
select is((select state from app.durable_jobs
 where id='20202020-5000-4000-8000-000000000002'),'review_required',
 'non-planning job with a revoked session remains blocked');

select * from finish();
rollback;
