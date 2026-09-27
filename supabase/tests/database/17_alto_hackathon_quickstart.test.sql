begin;
select plan(15);
create temporary table hackathon_results(label text,expected text,actual text) on commit drop;
grant insert,select on hackathon_results to coordination_api;
create function pg_temp.hackathon_error(label text,statement text,expected text) returns void
language plpgsql as $$
declare observed text:='no_error'; begin
 begin execute statement; exception when others then get stacked diagnostics observed=returned_sqlstate; end;
 insert into hackathon_results values(label,expected,observed);
end $$;

insert into auth.users(id,instance_id,aud,role,email,created_at,updated_at) values
 ('17171717-aaaa-4aaa-8aaa-aaaaaaaaaaa1','00000000-0000-0000-0000-000000000000','authenticated','authenticated','hackathon-owner@example.invalid',now(),now()),
 ('17171717-aaaa-4aaa-8aaa-aaaaaaaaaaa2','00000000-0000-0000-0000-000000000000','authenticated','authenticated','hackathon-one@example.invalid',now(),now()),
 ('17171717-aaaa-4aaa-8aaa-aaaaaaaaaaa3','00000000-0000-0000-0000-000000000000','authenticated','authenticated','hackathon-two@example.invalid',now(),now());
insert into app.company_memberships(id,company_id,user_id,membership_status,administrative_role,joined_at) values
 ('17171717-1000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111','17171717-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','manager',now()),
 ('17171717-1000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111','17171717-aaaa-4aaa-8aaa-aaaaaaaaaaa2','active','manager',now()),
 ('17171717-1000-4000-8000-000000000003','11111111-1111-4111-8111-111111111111','17171717-aaaa-4aaa-8aaa-aaaaaaaaaaa3','active','manager',now());
insert into app.demo_workspace_policies(company_id,enabled,scenario_key,scenario_version)
 values('11111111-1111-4111-8111-111111111111',true,'northstar-launch',1)
 on conflict(company_id) do update set enabled=true;
insert into app.demo_provider_profiles(id,company_id,owner_membership_id) values
 ('17171717-2000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111','17171717-1000-4000-8000-000000000001');
insert into app.demo_provider_profile_versions(
 id,company_id,profile_id,version,provider,credential_kind,vault_secret_id,
 credential_fingerprint,credential_hint,validated_model,vertex_project_id,
 vertex_client_email,vertex_location
) values
 ('17171717-3000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111','17171717-2000-4000-8000-000000000001',1,
  'vertex_ai','vertex_service_account',vault.create_secret('synthetic-hackathon-one','alto-hackathon-test-one'),decode(repeat('17',32),'hex'),'171717171717','gemini-hackathon-test','test-vertex-project','test@test-vertex-project.iam.gserviceaccount.com','global'),
 ('17171717-3000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111','17171717-2000-4000-8000-000000000001',2,
  'vertex_ai','vertex_service_account',vault.create_secret('synthetic-hackathon-two','alto-hackathon-test-two'),decode(repeat('18',32),'hex'),'181818181818','gemini-hackathon-test','test-vertex-project','test@test-vertex-project.iam.gserviceaccount.com','global');
insert into app.demo_operator_provider_defaults(
 company_id,profile_version_id,credential_owner_membership_id
) values('11111111-1111-4111-8111-111111111111','17171717-3000-4000-8000-000000000001','17171717-1000-4000-8000-000000000001');
insert into app.demo_runs(id,company_id,owner_membership_id,scenario_key,scenario_version,mode,idempotency_key) values
 ('17171717-4000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111','17171717-1000-4000-8000-000000000002','northstar-launch',1,'live','hackathon-run-one'),
 ('17171717-4000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111','17171717-1000-4000-8000-000000000002','northstar-launch',1,'live','hackathon-run-two'),
 ('17171717-4000-4000-8000-000000000003','11111111-1111-4111-8111-111111111111','17171717-1000-4000-8000-000000000002','northstar-launch',1,'authored_replay','hackathon-run-replay'),
 ('17171717-4000-4000-8000-000000000004','11111111-1111-4111-8111-111111111111','17171717-1000-4000-8000-000000000002','northstar-launch',1,'live','hackathon-run-wrong-model');
insert into app.demo_run_memberships(company_id,run_id,membership_id,run_role)
 select company_id,id,owner_membership_id,'owner' from app.demo_runs
 where id::text like '17171717-4000-4000-8000-00000000000%';

select set_config('app.actor_id','17171717-aaaa-4aaa-8aaa-aaaaaaaaaaa2',true),
 set_config('app.company_id','11111111-1111-4111-8111-111111111111',true),
 set_config('app.purpose','test:hackathon-quickstart',true),
 set_config('app.demo_run_id','17171717-4000-4000-8000-000000000001',true),
 set_config('app.demo_actor_session_id','',true);
set local role coordination_api;
insert into hackathon_results values('judge binds validated default','17171717-3000-4000-8000-000000000001',
 app.bind_demo_operator_provider('11111111-1111-4111-8111-111111111111','17171717-4000-4000-8000-000000000001','gemini-hackathon-test')::text);
insert into hackathon_results values('safe binding identifies Vertex AI','vertex_ai',app.get_demo_provider_binding()->>'provider');
insert into hackathon_results values('binding is visibly operator managed','operator_managed',app.get_demo_provider_binding()->>'management_mode');
insert into hackathon_results values('judge cannot manage shared version','false',app.get_demo_provider_binding()->>'can_manage');
insert into hackathon_results values('safe binding omits profile ID','false',(app.get_demo_provider_binding() ? 'profile_id')::text);
insert into hackathon_results values('safe binding omits fingerprint hint','false',(app.get_demo_provider_binding() ? 'credential_hint')::text);
select pg_temp.hackathon_error('replay run rejects shared credential',$q$select app.bind_demo_operator_provider(
 '11111111-1111-4111-8111-111111111111','17171717-4000-4000-8000-000000000003','gemini-hackathon-test')$q$,'42501');
select pg_temp.hackathon_error('wrong model fails closed',$q$select app.bind_demo_operator_provider(
 '11111111-1111-4111-8111-111111111111','17171717-4000-4000-8000-000000000004','wrong-model')$q$,'P0001');
reset role;
insert into hackathon_results select 'binding records protected source','operator_default',binding_source
 from app.demo_run_provider_bindings where run_id='17171717-4000-4000-8000-000000000001';
update app.demo_operator_provider_defaults set profile_version_id='17171717-3000-4000-8000-000000000002',configured_at=clock_timestamp();
set local role coordination_api;
insert into hackathon_results values('rotation preserves existing run','17171717-3000-4000-8000-000000000001',
 app.bind_demo_operator_provider('11111111-1111-4111-8111-111111111111','17171717-4000-4000-8000-000000000001','gemini-hackathon-test')::text);
insert into hackathon_results values('new run pins rotated default','17171717-3000-4000-8000-000000000002',
 app.bind_demo_operator_provider('11111111-1111-4111-8111-111111111111','17171717-4000-4000-8000-000000000002','gemini-hackathon-test')::text);
reset role;
update app.demo_operator_provider_defaults set enabled=false,disabled_at=clock_timestamp();
set local role coordination_api;
select set_config('app.demo_run_id','17171717-4000-4000-8000-000000000001',true);
insert into hackathon_results values('disable is visible safely','unavailable',app.get_demo_provider_binding()->>'status');
select pg_temp.hackathon_error('disable blocks shared binding',$q$select app.bind_demo_operator_provider(
 '11111111-1111-4111-8111-111111111111','17171717-4000-4000-8000-000000000001','gemini-hackathon-test')$q$,'P0001');
select set_config('app.actor_id','17171717-aaaa-4aaa-8aaa-aaaaaaaaaaa3',true);
insert into hackathon_results select 'another judge cannot read first run','0',count(*)::text
 from app.demo_runs where id='17171717-4000-4000-8000-000000000001';
reset role;

select is(actual,expected,label) from hackathon_results;
select ok(not has_table_privilege('coordination_api','app.demo_operator_provider_defaults','SELECT'),'API cannot select operator defaults directly');
select * from finish();
rollback;
