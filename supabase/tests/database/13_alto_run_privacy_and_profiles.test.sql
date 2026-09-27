begin;
select no_plan();
create temporary table alto_results(label text,expected text,actual text) on commit drop;
grant insert,select on alto_results to coordination_api,coordination_worker,service_role;
create function pg_temp.alto_error(label text,statement text,expected text) returns void language plpgsql as $$
declare observed text:='no_error'; begin
 begin execute statement; exception when others then get stacked diagnostics observed=returned_sqlstate; end;
 insert into alto_results values(label,expected,observed);
end $$;

insert into auth.users(id,instance_id,aud,role,email,created_at,updated_at) values
 ('13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa1','00000000-0000-0000-0000-000000000000','authenticated','authenticated','alto-one@example.invalid',now(),now()),
 ('13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa2','00000000-0000-0000-0000-000000000000','authenticated','authenticated','alto-two@example.invalid',now(),now());
insert into app.company_memberships(id,company_id,user_id,membership_status,administrative_role,joined_at) values
 ('13131313-1000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111','13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','manager',now()),
 ('13131313-1000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111','13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa2','active','manager',now());
insert into app.employee_profiles(id,company_id,profile_kind,synthetic_key,display_name,function_key,scenario_detail) values
 ('13131313-2000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111','synthetic','iris','Iris','design','rich'),
 ('13131313-2000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111','synthetic','maya','Maya','leadership','rich');
insert into app.demo_runs(id,company_id,owner_membership_id,scenario_key,scenario_version,mode,idempotency_key) values
 ('13131313-3000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111','13131313-1000-4000-8000-000000000001','northstar-launch',1,'authored_replay','alto-run-one-fixture'),
 ('13131313-3000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111','13131313-1000-4000-8000-000000000001','northstar-launch',1,'authored_replay','alto-run-two-fixture');
insert into app.demo_run_memberships(company_id,run_id,membership_id,run_role)
 select company_id,id,owner_membership_id,'owner' from app.demo_runs where id in (
 '13131313-3000-4000-8000-000000000001','13131313-3000-4000-8000-000000000002');
insert into app.demo_actor_sessions(id,company_id,run_id,performed_by_auth_user_id,simulated_actor_employee_id) values
 ('13131313-4000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111','13131313-3000-4000-8000-000000000001','13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa1','13131313-2000-4000-8000-000000000001'),
 ('13131313-4000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111','13131313-3000-4000-8000-000000000001','13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa1','13131313-2000-4000-8000-000000000002'),
 ('13131313-4000-4000-8000-000000000003','11111111-1111-4111-8111-111111111111','13131313-3000-4000-8000-000000000002','13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa1','13131313-2000-4000-8000-000000000001');
select set_config('app.actor_id','13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa1',true),
 set_config('app.company_id','11111111-1111-4111-8111-111111111111',true),set_config('app.purpose','test:alto',true),
 set_config('app.demo_run_id','13131313-3000-4000-8000-000000000001',true),
 set_config('app.demo_actor_session_id','13131313-4000-4000-8000-000000000001',true);
set local role coordination_api;
insert into alto_results values('real manager selected as Iris is not planning manager','false',app.can_manage_planning(app.current_company_id(),app.current_actor_id())::text);
with saved as(insert into app.employee_preference_versions(id,company_id,employee_id,version,text,origin,status)
 values('13131313-5000-4000-8000-000000000001',app.current_company_id(),'13131313-2000-4000-8000-000000000001',1,'More product-storytelling work','employee','confirmed') returning id)
 insert into alto_results select 'self preference INSERT RETURNING succeeds','1',count(*)::text from saved;
with saved as(insert into app.assistant_threads(id,company_id,owner_membership_id,simulated_employee_id,context_type)
 values('13131313-6000-4000-8000-000000000001',app.current_company_id(),'13131313-1000-4000-8000-000000000001','13131313-2000-4000-8000-000000000001','workspace') returning id)
 insert into alto_results select 'self thread INSERT RETURNING succeeds','1',count(*)::text from saved;
insert into app.employee_preference_share_decisions(company_id,preference_version_id,audience_membership_id,audience_employee_id,decision,decided_by_auth_user_id,simulated_actor_employee_id)
 values(app.current_company_id(),'13131313-5000-4000-8000-000000000001','13131313-1000-4000-8000-000000000001','13131313-2000-4000-8000-000000000002','share',app.current_actor_id(),'13131313-2000-4000-8000-000000000001');
insert into alto_results select 'first profile edit advances from canonical version','2',app.update_alto_profile_skills(
 app.current_company_id(),'13131313-2000-4000-8000-000000000001',1,'["Product design"]')->>'row_version';
select pg_temp.alto_error('stale profile edit rejected',$q$select app.update_alto_profile_skills(app.current_company_id(),'13131313-2000-4000-8000-000000000001',1,'[]')$q$,'40001');
select pg_temp.alto_error('other employee edit rejected',$q$select app.update_alto_profile_skills(app.current_company_id(),'13131313-2000-4000-8000-000000000002',1,'[]')$q$,'42501');
select pg_temp.alto_error('malformed skill labels rejected',$q$select app.update_alto_profile_skills(app.current_company_id(),'13131313-2000-4000-8000-000000000001',2,'[null]')$q$,'22023');
select pg_temp.alto_error('direct profile mutation denied',$q$update app.employee_profile_overrides set declared_skills='[]'$q$,'42501');
select pg_temp.alto_error('API cannot read pinned operator manifest',$q$select app.get_demo_scenario_manifest()$q$,'42501');
insert into alto_results select 'canonical synthetic profile remains version one','1',row_version::text from app.employee_profiles where id='13131313-2000-4000-8000-000000000001';
select set_config('app.demo_actor_session_id','13131313-4000-4000-8000-000000000002',true);
insert into alto_results values('Maya can manage the owned run','true',app.can_manage_planning(app.current_company_id(),app.current_actor_id())::text);
insert into alto_results select 'exact manager sees shared preference','1',count(*)::text from app.employee_preference_versions;
insert into alto_results select 'exact manager sees current consent timestamp','1',count(*)::text from app.employee_preference_share_decisions;
insert into alto_results select 'actor switch does not reveal Iris thread','0',count(*)::text from app.assistant_threads;
select set_config('app.demo_run_id','13131313-3000-4000-8000-000000000002',true),set_config('app.demo_actor_session_id','13131313-4000-4000-8000-000000000003',true);
insert into alto_results select 'second run has no first-run override','0',count(*)::text from app.employee_profile_overrides;
insert into alto_results select 'second run has no first-run preference','0',count(*)::text from app.employee_preference_versions;
insert into alto_results select 'second run has no first-run thread','0',count(*)::text from app.assistant_threads;
select set_config('app.demo_run_id','13131313-3000-4000-8000-000000000001',true),set_config('app.demo_actor_session_id','13131313-4000-4000-8000-000000000001',true);
update app.employee_preference_share_decisions set revoked_at=clock_timestamp() where preference_version_id='13131313-5000-4000-8000-000000000001';
select set_config('app.demo_actor_session_id','13131313-4000-4000-8000-000000000002',true);
insert into alto_results select 'revoked manager loses preference wording','0',count(*)::text from app.employee_preference_versions;
insert into alto_results select 'revoked manager loses consent row','0',count(*)::text from app.employee_preference_share_decisions;
select set_config('app.actor_id','13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa2',true);
insert into alto_results select 'other visitor cannot read owned run','0',count(*)::text from app.demo_runs;
insert into alto_results values('other visitor cannot reuse actor session','true',app.authorised_demo_actor(app.current_company_id(),app.current_demo_run_id(),app.current_actor_id()) is null);
reset role;
-- Privileged fixture creation is isolated; every runtime assertion uses the non-owner worker role.
select set_config('app.actor_id','13131313-aaaa-4aaa-8aaa-aaaaaaaaaaa1',true),
 set_config('app.demo_actor_session_id','13131313-4000-4000-8000-000000000001',true);
insert into app.demo_scenario_manifests(company_id,scenario_key,version,manifest_digest,fixture_schema_version,manifest_payload)
 values(app.current_company_id(),'northstar-launch',1,decode(repeat('13',32),'hex'),'alto-test.v1','{"fixture":"pinned"}');
insert into app.source_records(id,company_id,source_kind,title,authority_status)
 values('13131313-7000-4000-8000-000000000001',app.current_company_id(),'fixture','Permitted synthetic source','authoritative');
insert into app.source_access_grants(company_id,source_id,principal_kind,access_type,authority_reference)
 values(app.current_company_id(),'13131313-7000-4000-8000-000000000001','company','read','Explicit synthetic test authority');
set constraints all immediate;
select pg_temp.alto_error('cross-run source-version parent rejected',$q$
 insert into app.source_versions(company_id,demo_run_id,source_id,content_sha256,retrieved_at,access_snapshot)
 values(app.current_company_id(),'13131313-3000-4000-8000-000000000002','13131313-7000-4000-8000-000000000001',decode(repeat('14',32),'hex'),now(),'{}')$q$,'23503');
insert into app.durable_jobs(id,company_id,job_kind,aggregate_id,payload,requested_by_membership_id,idempotency_key,command_digest,correlation_id,
 state,attempt_count,lease_owner,lease_token,leased_at,leased_until)
 values('13131313-8000-4000-8000-000000000001',app.current_company_id(),'assistant.respond','13131313-8000-4000-8000-000000000002',
 '{"thread_id":"13131313-6000-4000-8000-000000000001"}','13131313-1000-4000-8000-000000000001','alto-worker-lease-fixture',
 decode(repeat('15',32),'hex'),'13131313-8000-4000-8000-000000000003','leased',1,
 '13131313-9000-4000-8000-000000000001','13131313-9000-4000-8000-000000000002',now(),now()+interval '5 minutes');
select set_config('app.job_id','13131313-8000-4000-8000-000000000001',true),
 set_config('app.lease_token','13131313-9000-4000-8000-000000000002',true);
set local role coordination_worker;
insert into alto_results values('lease helper returns only current worker','13131313-9000-4000-8000-000000000001',app.current_alto_lease_worker()::text);
insert into alto_results values('worker receives exact pinned scenario','pinned',app.get_demo_scenario_manifest()#>>'{manifest_payload,fixture}');
insert into alto_results values('authorised workspace source matches current thread','true',
 app.source_in_assistant_context(app.current_company_id(),'13131313-6000-4000-8000-000000000001','13131313-7000-4000-8000-000000000001')::text);
insert into alto_results values('private owner wording is not treated as shared','false',
 app.preference_is_shared_to_viewer(app.current_company_id(),'13131313-5000-4000-8000-000000000001')::text);
select pg_temp.alto_error('worker cannot request another run manifest',$q$select app.get_demo_scenario_manifest(app.current_company_id(),'13131313-3000-4000-8000-000000000002')$q$,'42501');
select set_config('app.lease_token','13131313-9000-4000-8000-000000000003',true);
select pg_temp.alto_error('wrong lease token cannot resolve worker',$q$select app.current_alto_lease_worker()$q$,'40001');
select set_config('app.lease_token','13131313-9000-4000-8000-000000000002',true);
reset role;
insert into app.private_files(id,company_id,bucket_id,object_path,purpose,uploader_employee_id,thread_id,
 display_filename,declared_mime_type,size_bytes,state,uploaded_at,upload_intent_expires_at,expires_at)
 values('13131313-a000-4000-8000-000000000001',app.current_company_id(),'coordination-quarantine',
 '11111111-1111-4111-8111-111111111111/runs/13131313-3000-4000-8000-000000000001/13131313-a000-4000-8000-000000000001/payload.wav',
 'voice_audio','13131313-2000-4000-8000-000000000001','13131313-6000-4000-8000-000000000001',
 'recording.wav','audio/wav',128,'pending_upload',now(),now()+interval '10 minutes',now()+interval '1 hour');
update app.private_files set state='quarantined' where id='13131313-a000-4000-8000-000000000001';
update app.durable_jobs set state='leased',attempt_count=1,lease_owner='13131313-9000-4000-8000-000000000001',
 lease_token='13131313-9000-4000-8000-000000000004',leased_at=now(),leased_until=now()+interval '5 minutes'
 where job_kind='private_file.scan' and aggregate_id='13131313-a000-4000-8000-000000000001';
create temporary table alto_file_lease as select id from app.durable_jobs
 where job_kind='private_file.scan' and aggregate_id='13131313-a000-4000-8000-000000000001';
grant select on alto_file_lease to service_role,coordination_worker;
set local role service_role;
insert into alto_results values('scan promotion path is server generated',
 '11111111-1111-4111-8111-111111111111/runs/13131313-3000-4000-8000-000000000001/13131313-a000-4000-8000-000000000001/validated.wav',
 public.authorize_alto_worker_storage('11111111-1111-4111-8111-111111111111',(select id from alto_file_lease),
 '13131313-9000-4000-8000-000000000004','13131313-a000-4000-8000-000000000001','upload-private')->>'object_path');
insert into alto_results values('scan retry can compare the validated object','coordination-private',
 public.authorize_alto_worker_storage('11111111-1111-4111-8111-111111111111',(select id from alto_file_lease),
 '13131313-9000-4000-8000-000000000004','13131313-a000-4000-8000-000000000001','download-private')->>'bucket_id');
insert into alto_results values('audio deletion lists exactly quarantine and private objects','2',
 jsonb_array_length(public.authorize_alto_worker_storage('11111111-1111-4111-8111-111111111111',(select id from alto_file_lease),
 '13131313-9000-4000-8000-000000000004','13131313-a000-4000-8000-000000000001','delete-audio')->'object_paths')::text);
select pg_temp.alto_error('file capability rejects arbitrary file identity',$q$
 select public.authorize_alto_worker_storage('11111111-1111-4111-8111-111111111111',(select id from alto_file_lease),
 '13131313-9000-4000-8000-000000000004','13131313-a000-4000-8000-000000000002','upload-private')$q$,'42501');
reset role;
update app.private_files set expires_at=clock_timestamp()-interval '1 second' where id='13131313-a000-4000-8000-000000000001';
set local role service_role;
select pg_temp.alto_error('expired audio capability cannot download bytes',$q$
 select public.authorize_alto_worker_storage('11111111-1111-4111-8111-111111111111',(select id from alto_file_lease),
 '13131313-9000-4000-8000-000000000004','13131313-a000-4000-8000-000000000001','download-quarantine')$q$,'42501');
reset role;
update app.demo_actor_sessions set revoked_at=clock_timestamp() where id='13131313-4000-4000-8000-000000000001';
create temporary table alto_cleanup(file_id uuid,cleanup_token uuid) on commit drop;
grant select,insert on alto_cleanup to coordination_worker,service_role;
set local role coordination_worker;
select pg_temp.alto_error('revoked actor invalidates existing worker lease',$q$select app.current_alto_lease_worker()$q$,'40001');
insert into alto_cleanup select * from app.claim_expired_audio_cleanup('13131313-9000-4000-8000-000000000001',1);
insert into alto_results select 'expired audio cleanup survives revoked actor','1',count(*)::text from alto_cleanup;
reset role;
set local role service_role;
insert into alto_results select 'cleanup capability grants exactly two delete paths','2',
 jsonb_array_length(public.authorize_alto_audio_cleanup(file_id,cleanup_token)->'object_paths')::text from alto_cleanup;
insert into alto_results select 'cleanup completion can record deletion','true',public.complete_alto_audio_cleanup(file_id,cleanup_token)::text from alto_cleanup;
reset role;
insert into alto_results select 'completed cleanup marks file deleted','deleted',state from app.private_files where id='13131313-a000-4000-8000-000000000001';
-- Cancellation and archive preserve the legacy all-or-none audit shape. Runtime
-- calls use a second run, leaving the first run's records and revision untouched.
select set_config('app.demo_run_id','13131313-3000-4000-8000-000000000002',true),
 set_config('app.demo_actor_session_id','13131313-4000-4000-8000-000000000003',true);
insert into app.assistant_threads(id,company_id,owner_membership_id,simulated_employee_id,context_type)
 values('13131313-6000-4000-8000-000000000002',app.current_company_id(),'13131313-1000-4000-8000-000000000001',
 '13131313-2000-4000-8000-000000000001','workspace');
insert into app.durable_jobs(id,company_id,job_kind,aggregate_id,payload,requested_by_membership_id,idempotency_key,command_digest,correlation_id)
 select ('13131313-b000-4000-8000-'||lpad(n::text,12,'0'))::uuid,app.current_company_id(),'assistant.respond',
 ('13131313-c000-4000-8000-'||lpad(n::text,12,'0'))::uuid,'{"thread_id":"13131313-6000-4000-8000-000000000002"}',
 '13131313-1000-4000-8000-000000000001','alto-cancel-fixture-'||n,decode(repeat('17',32),'hex'),gen_random_uuid()
 from generate_series(1,2) n;
update app.durable_jobs set state='leased',attempt_count=1,lease_owner='13131313-9000-4000-8000-000000000001',
 lease_token='13131313-9000-4000-8000-000000000005',leased_at=now(),leased_until=now()+interval '5 minutes'
 where id='13131313-b000-4000-8000-000000000002';
insert into app.job_attempts(company_id,job_id,attempt_number,lease_token,worker_id)
 values(app.current_company_id(),'13131313-b000-4000-8000-000000000002',1,
 '13131313-9000-4000-8000-000000000005','13131313-9000-4000-8000-000000000001');
set local role coordination_api;
select app.cancel_alto_assistant(app.current_company_id(),'13131313-6000-4000-8000-000000000002','alto-cancel-command-fixture');
reset role;
insert into alto_results select 'queued assistant cancellation is terminal','cancelled',state
 from app.durable_jobs where id='13131313-b000-4000-8000-000000000001';
insert into alto_results select 'assistant cancellation retains complete audit','2',count(*)::text from app.durable_jobs
 where id in ('13131313-b000-4000-8000-000000000001','13131313-b000-4000-8000-000000000002')
 and cancel_requested_at is not null and cancelled_by_membership_id='13131313-1000-4000-8000-000000000001'
 and cancellation_reason is not null and cancellation_idempotency_key='alto-cancel-command-fixture'
 and octet_length(cancellation_command_digest)=32;
select set_config('app.job_id','13131313-b000-4000-8000-000000000002',true),
 set_config('app.lease_token','13131313-9000-4000-8000-000000000005',true);
set local role coordination_worker;
select pg_temp.alto_error('cancel request immediately fences leased worker',$q$select app.current_alto_lease_worker()$q$,'40001');
reset role;
insert into app.durable_jobs(id,company_id,job_kind,aggregate_id,payload,requested_by_membership_id,idempotency_key,command_digest,correlation_id)
 values('13131313-b000-4000-8000-000000000003',app.current_company_id(),'assistant.respond',
 '13131313-c000-4000-8000-000000000003','{"thread_id":"13131313-6000-4000-8000-000000000002"}',
 '13131313-1000-4000-8000-000000000001','alto-cancel-fixture-later',decode(repeat('18',32),'hex'),gen_random_uuid());
set local role coordination_api;
select app.cancel_alto_assistant(app.current_company_id(),'13131313-6000-4000-8000-000000000002','alto-cancel-command-fixture');
reset role;
insert into alto_results select 'cancel replay does not cancel newer work','queued',state
 from app.durable_jobs where id='13131313-b000-4000-8000-000000000003';
select set_config('app.demo_run_id','',true),set_config('app.demo_actor_session_id','',true);
set local role coordination_api;
select pg_temp.alto_error('archive checks exact run version',$q$select app.archive_demo_run(app.current_company_id(),'13131313-3000-4000-8000-000000000002',99)$q$,'40001');
select app.archive_demo_run(app.current_company_id(),'13131313-3000-4000-8000-000000000002',1);
insert into alto_results values('archive restores ordinary request context','true',(app.current_demo_run_id() is null)::text);
reset role;
insert into alto_results select 'archive cancels all remaining jobs','3',count(*)::text from app.durable_jobs
 where demo_run_id='13131313-3000-4000-8000-000000000002' and state='cancelled' and lease_token is null;
insert into alto_results select 'archive closes the exact outstanding attempt','cancelled',outcome from app.job_attempts
 where job_id='13131313-b000-4000-8000-000000000002';
insert into alto_results select 'archive supplies audit for newly cancelled work','archive:13131313-3000-4000-8000-000000000002',cancellation_idempotency_key
 from app.durable_jobs where id='13131313-b000-4000-8000-000000000003';
insert into alto_results select 'archive preserves previous cancellation authority','alto-cancel-command-fixture',cancellation_idempotency_key
 from app.durable_jobs where id='13131313-b000-4000-8000-000000000002';
insert into alto_results select 'archive does not archive another run','active',state from app.demo_runs
 where id='13131313-3000-4000-8000-000000000001';
insert into alto_results select 'archive revokes its actor session','true',(revoked_at is not null)::text from app.demo_actor_sessions
 where id='13131313-4000-4000-8000-000000000003';
select is(actual,expected,label) from alto_results;
select ok(not has_table_privilege('coordination_api','app.employee_profile_overrides','UPDATE'),'API has no broad profile write grant');
select ok(not has_table_privilege('coordination_worker','app.durable_jobs','SELECT'),'worker has no broad queue read grant');
select ok(not has_function_privilege('coordination_api','app.current_alto_lease_worker()','EXECUTE'),'API cannot resolve worker capability');
select * from finish();
rollback;
