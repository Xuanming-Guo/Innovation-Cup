-- Local/disposable database only. Every fixture and mutation is rolled back.
begin;
select plan(4);

create temporary table continuity_results(label text, value boolean) on commit drop;
grant insert,select on continuity_results to coordination_worker;

insert into auth.users(id,instance_id,aud,role,email,created_at,updated_at) values
 ('19191919-aaaa-4aaa-8aaa-aaaaaaaaaaa1','00000000-0000-0000-0000-000000000000',
  'authenticated','authenticated','continuity@example.invalid',now(),now());
insert into app.company_memberships(
 id,company_id,user_id,membership_status,administrative_role,joined_at
) values (
 '19191919-1000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '19191919-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','manager',now()
);
insert into app.employee_profiles(
 id,company_id,profile_kind,synthetic_key,display_name,function_key,scenario_detail
) values (
 '19191919-2000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 'synthetic','continuity-maya','Maya','leadership','rich'
);
insert into app.demo_workspace_policies(company_id,enabled,scenario_key,scenario_version)
values('11111111-1111-4111-8111-111111111111',true,'northstar-launch',1)
on conflict(company_id) do update set enabled=true,scenario_key=excluded.scenario_key,
 scenario_version=excluded.scenario_version;
insert into app.demo_runs(
 id,company_id,owner_membership_id,scenario_key,scenario_version,mode,idempotency_key
) values (
 '19191919-3000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '19191919-1000-4000-8000-000000000001','northstar-launch',1,'live',
 'locked-demo-continuity'
);
insert into app.demo_run_memberships(company_id,run_id,membership_id,run_role) values (
 '11111111-1111-4111-8111-111111111111','19191919-3000-4000-8000-000000000001',
 '19191919-1000-4000-8000-000000000001','owner'
);
insert into app.demo_actor_sessions(
 id,company_id,run_id,performed_by_auth_user_id,simulated_actor_employee_id,revoked_at
) values (
 '19191919-4000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
 '19191919-3000-4000-8000-000000000001','19191919-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
 '19191919-2000-4000-8000-000000000001',now()
);
insert into app.durable_jobs(
 id,company_id,demo_run_id,demo_actor_session_id,simulated_employee_id,job_kind,
 aggregate_id,payload,requested_by_membership_id,idempotency_key,command_digest,correlation_id
) values
 ('19191919-5000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
  '19191919-3000-4000-8000-000000000001','19191919-4000-4000-8000-000000000001',
  '19191919-2000-4000-8000-000000000001','interpretation.run',gen_random_uuid(),'{}',
  '19191919-1000-4000-8000-000000000001','locked-planning-continuity',
  decode(repeat('19',32),'hex'),gen_random_uuid()),
 ('19191919-5000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111',
  '19191919-3000-4000-8000-000000000001','19191919-4000-4000-8000-000000000001',
  '19191919-2000-4000-8000-000000000001','assistant.respond',gen_random_uuid(),'{}',
 '19191919-1000-4000-8000-000000000001','nonplanning-session-fence',
  decode(repeat('20',32),'hex'),gen_random_uuid());
update app.durable_jobs
set demo_actor_session_id='19191919-4000-4000-8000-000000000001',
    simulated_employee_id='19191919-2000-4000-8000-000000000001'
where id in (
 '19191919-5000-4000-8000-000000000001',
 '19191919-5000-4000-8000-000000000002'
);

set local role coordination_worker;
insert into continuity_results values
 ('planning',app.alto_job_authorized('11111111-1111-4111-8111-111111111111',
   '19191919-5000-4000-8000-000000000001')),
 ('assistant',app.alto_job_authorized('11111111-1111-4111-8111-111111111111',
   '19191919-5000-4000-8000-000000000002'));
reset role;

select ok(not (select value from continuity_results where label='planning'),
 'planning remains fenced until the queue rebinds the current persona session');
select ok(not (select value from continuity_results where label='assistant'),
 'non-planning work remains fenced by the revoked session');

update app.company_memberships set membership_status='suspended',suspended_at=now()
where id='19191919-1000-4000-8000-000000000001';
set local role coordination_worker;
insert into continuity_results values
 ('suspended',app.alto_job_authorized('11111111-1111-4111-8111-111111111111',
   '19191919-5000-4000-8000-000000000001'));
reset role;
select ok(not (select value from continuity_results where label='suspended'),
 'locked planning still requires an active run membership');
select ok(has_function_privilege('coordination_worker','app.alto_job_authorized(uuid,uuid)','EXECUTE')
 and not has_function_privilege('coordination_api','app.alto_job_authorized(uuid,uuid)','EXECUTE'),
 'job authorization remains worker-only');

select * from finish();
rollback;
