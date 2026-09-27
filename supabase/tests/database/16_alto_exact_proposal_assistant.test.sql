-- Exact proposal-bound assistant threads are manager-only, project-scoped and
-- hidden immediately when their planning authority is no longer current.
begin;
select no_plan();

create temporary table proposal_assistant_results(
  label text,expected text,actual text
) on commit drop;
grant insert,select on proposal_assistant_results to coordination_api,coordination_worker;
create function pg_temp.capture_error(label text,statement text,expected text)
returns void language plpgsql security invoker as $$
declare observed text := '00000';
begin
  begin execute statement;
  exception when others then get stacked diagnostics observed=returned_sqlstate;
  end;
  insert into proposal_assistant_results values(label,expected,observed);
end $$;

insert into auth.users(id,instance_id,aud,role,email,created_at,updated_at)
values('16161616-aaaa-4aaa-8aaa-aaaaaaaaaaa1','00000000-0000-0000-0000-000000000000',
  'authenticated','authenticated','proposal-assistant@example.invalid',now(),now());
insert into app.company_memberships(
  id,company_id,user_id,membership_status,administrative_role,joined_at
) values('16161616-1000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','16161616-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
  'active','manager',now());
insert into app.employee_profiles(id,company_id,membership_id)
values('16161616-2000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','16161616-1000-4000-8000-000000000001');
insert into app.teams(id,company_id,name)
values('16161616-3000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','Proposal assistant fixture');
insert into app.projects(
  id,company_id,owning_team_id,manager_employee_id,title,purpose
) values
 ('16161616-4000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
  '16161616-3000-4000-8000-000000000001','16161616-2000-4000-8000-000000000001',
  'Bound project','Verify exact proposal assistant binding.'),
 ('16161616-4000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111',
  '16161616-3000-4000-8000-000000000001','16161616-2000-4000-8000-000000000001',
  'Other project','Must not accept the bound proposal.');
insert into app.planning_requests(
  id,company_id,project_id,requester_membership_id,original_prompt,idempotency_key,request_digest
) values('16161616-5000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','16161616-4000-4000-8000-000000000001',
  '16161616-1000-4000-8000-000000000001','Check the exact candidate.',
  'proposal-assistant-request',decode(repeat('16',32),'hex'));
insert into app.retrieval_runs(
  id,company_id,request_id,actor_membership_id,purpose,allowed_scope,selected_manifest,
  omitted_manifest,missing_manifest,projection_digest,projection_characters,status,
  started_at,completed_at
) values('16161616-6000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','16161616-5000-4000-8000-000000000001',
  '16161616-1000-4000-8000-000000000001','proposal-assistant-test','{}','[]','[]','[]',
  decode(repeat('16',32),'hex'),0,'complete',now(),now());
insert into app.interpretation_runs(
  id,company_id,request_id,retrieval_run_id,model_id,sdk_version,prompt_version,
  schema_version,safety_profile,configuration,status,outcome,started_at,completed_at
) values('16161616-7000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','16161616-5000-4000-8000-000000000001',
  '16161616-6000-4000-8000-000000000001','fixture','fixture','fixture','fixture','fixture',
  '{}','completed','admitted',now(),now());
insert into app.candidate_contracts(
  id,company_id,request_id,interpretation_run_id,contract_json,contract_digest,
  admission_status,validation_issues
) values('16161616-8000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','16161616-5000-4000-8000-000000000001',
  '16161616-7000-4000-8000-000000000001','{}',decode(repeat('16',32),'hex'),
  'admitted','[]');
insert into app.planning_snapshots(
  id,company_id,request_id,candidate_contract_id,schema_version,base_company_revision,
  horizon_start,horizon_end,slot_minutes,source_manifest_digest,permission_revision,
  profile_revision,estimate_revision,compiler_version,policy,normalized_snapshot,
  snapshot_digest,frozen_at
) values('16161616-9000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','16161616-5000-4000-8000-000000000001',
  '16161616-8000-4000-8000-000000000001','planning-snapshot.v1',0,now(),now()+interval '1 day',30,
  decode(repeat('16',32),'hex'),'fixture','fixture','fixture','fixture','{}','{}',
  decode(repeat('17',32),'hex'),now());
insert into app.ai_plan_proposals(
  id,company_id,snapshot_id,version,candidate_payload,candidate_digest,author_kind
) values('16161616-a000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','16161616-9000-4000-8000-000000000001',
  1,'{}',decode(repeat('18',32),'hex'),'authored_check');
insert into app.ai_plan_proposals(
  id,company_id,snapshot_id,parent_proposal_id,version,candidate_payload,
  candidate_digest,author_kind
) values
 ('16161616-a000-4000-8000-000000000002','11111111-1111-4111-8111-111111111111',
  '16161616-9000-4000-8000-000000000001','16161616-a000-4000-8000-000000000001',
  2,'{}',decode(repeat('23',32),'hex'),'authored_check'),
 ('16161616-a000-4000-8000-000000000003','11111111-1111-4111-8111-111111111111',
  '16161616-9000-4000-8000-000000000001','16161616-a000-4000-8000-000000000002',
  3,'{}',decode(repeat('24',32),'hex'),'authored_check'),
 ('16161616-a000-4000-8000-000000000004','11111111-1111-4111-8111-111111111111',
  '16161616-9000-4000-8000-000000000001','16161616-a000-4000-8000-000000000003',
  4,'{}',decode(repeat('25',32),'hex'),'authored_check'),
 ('16161616-a000-4000-8000-000000000005','11111111-1111-4111-8111-111111111111',
  '16161616-9000-4000-8000-000000000001','16161616-a000-4000-8000-000000000004',
  5,'{}',decode(repeat('26',32),'hex'),'authored_check');
insert into app.durable_jobs(
  id,company_id,job_kind,aggregate_id,payload,requested_by_membership_id,
  idempotency_key,command_digest,correlation_id,state,attempt_count,max_attempts,
  last_error_code,completed_at
) values('16161616-f000-4000-8000-000000000001',
  '11111111-1111-4111-8111-111111111111','plan.propose',
  '16161616-9000-4000-8000-000000000001','{}',
  '16161616-1000-4000-8000-000000000001','bounded-plan-revision-fixture',
  decode(repeat('27',32),'hex'),'16161616-f000-4000-8000-000000000002',
  'review_required',1,3,'fixed_plan_not_verified',now());

select set_config('app.actor_id','16161616-aaaa-4aaa-8aaa-aaaaaaaaaaa1',true),
  set_config('app.company_id','11111111-1111-4111-8111-111111111111',true),
  set_config('app.demo_run_id','',true),set_config('app.demo_actor_session_id','',true),
  set_config('app.purpose','test:proposal-assistant',true);
set local role coordination_api;
with retried as(
  select * from app.retry_durable_planning_job(
    app.current_company_id(),'16161616-f000-4000-8000-000000000001',
    'Continue the exact failed proposal repair.','bounded-plan-retry-command',
    decode(repeat('28',32),'hex'))
) insert into proposal_assistant_results
  select 'manager may continue a bounded failed Live proposal','queued',state from retried;
insert into proposal_assistant_results values(
  'manager can bind the exact proposal to its project','true',
  app.can_bind_assistant_proposal(app.current_company_id(),
    '16161616-4000-4000-8000-000000000001',
    '16161616-a000-4000-8000-000000000001')::text);
insert into proposal_assistant_results values(
  'proposal cannot be rebound to another project','false',
  app.can_bind_assistant_proposal(app.current_company_id(),
    '16161616-4000-4000-8000-000000000002',
    '16161616-a000-4000-8000-000000000001')::text);
with saved as(
  insert into app.assistant_threads(
    id,company_id,owner_membership_id,context_type,context_id,proposal_id
  ) values('16161616-b000-4000-8000-000000000001',app.current_company_id(),
    '16161616-1000-4000-8000-000000000001','project',
    '16161616-4000-4000-8000-000000000001',
    '16161616-a000-4000-8000-000000000001') returning id
) insert into proposal_assistant_results
  select 'exact proposal thread INSERT RETURNING succeeds','1',count(*)::text from saved;
insert into app.assistant_messages(
  id,company_id,thread_id,role,content,status,idempotency_key
) values('16161616-c000-4000-8000-000000000002',app.current_company_id(),
  '16161616-b000-4000-8000-000000000001','user','Suggest a checked plan revision.',
  'completed','proposal-action-request');
select pg_temp.capture_error('cross-project proposal thread is rejected',$q$
  insert into app.assistant_threads(
    id,company_id,owner_membership_id,context_type,context_id,proposal_id
  ) values('16161616-b000-4000-8000-000000000002',app.current_company_id(),
    '16161616-1000-4000-8000-000000000001','project',
    '16161616-4000-4000-8000-000000000002',
    '16161616-a000-4000-8000-000000000001')$q$,'42501');
reset role;

insert into app.durable_jobs(
  id,company_id,job_kind,aggregate_id,payload,requested_by_membership_id,
  idempotency_key,command_digest,correlation_id,state,attempt_count,lease_owner,
  lease_token,leased_at,leased_until,started_at
) values(
  '16161616-e000-4000-8000-000000000001',app.current_company_id(),
  'assistant.respond','16161616-c000-4000-8000-000000000002',
  '{"thread_id":"16161616-b000-4000-8000-000000000001"}',
  '16161616-1000-4000-8000-000000000001','proposal-action-response',
  decode(repeat('22',32),'hex'),'16161616-e000-4000-8000-000000000002',
  'leased',1,'16161616-e000-4000-8000-000000000003',
  '16161616-e000-4000-8000-000000000004',now(),now()+interval '5 minutes',now()
);
insert into app.job_attempts(
  company_id,job_id,attempt_number,lease_token,worker_id
) values(app.current_company_id(),'16161616-e000-4000-8000-000000000001',1,
  '16161616-e000-4000-8000-000000000004','16161616-e000-4000-8000-000000000003');
set local role coordination_worker;
select set_config('app.job_id','16161616-e000-4000-8000-000000000001',true),
  set_config('app.lease_token','16161616-e000-4000-8000-000000000004',true);
insert into app.assistant_messages(
  id,company_id,thread_id,role,content,status,operation_id,idempotency_key
) values('16161616-c000-4000-8000-000000000001',app.current_company_id(),
  '16161616-b000-4000-8000-000000000001','assistant','Review this action.',
  'completed','16161616-e000-4000-8000-000000000001','proposal-action-message');
insert into app.assistant_action_previews(
  id,company_id,message_id,command_type,target_id,expected_version,command_digest,
  expires_at,project_id,proposal_id,title,summary,action_payload
) values('16161616-d000-4000-8000-000000000001',app.current_company_id(),
  '16161616-c000-4000-8000-000000000001','plan_change',
  '16161616-a000-4000-8000-000000000001',1,decode(repeat('19',32),'hex'),
  now()+interval '30 minutes','16161616-4000-4000-8000-000000000001',
  '16161616-a000-4000-8000-000000000001','Prepare a revised plan','Move one task.',
  '{"scope":[{"label":"Project","value":"16161616-4000-4000-8000-000000000001"}],
    "changes":[],"violations":[],"warnings":[]}'::jsonb);
select pg_temp.capture_error('worker cannot stage action for another project',$q$
  insert into app.assistant_action_previews(
    id,company_id,message_id,command_type,target_id,expected_version,command_digest,
    expires_at,project_id,proposal_id,title,summary,action_payload
  ) values('16161616-d000-4000-8000-000000000002',app.current_company_id(),
    '16161616-c000-4000-8000-000000000001','plan_change',
    '16161616-a000-4000-8000-000000000001',1,decode(repeat('20',32),'hex'),
    now()+interval '30 minutes','16161616-4000-4000-8000-000000000002',
    '16161616-a000-4000-8000-000000000001','Unsafe action','Wrong project.','{}')$q$,
  '42501');
reset role;
set local role coordination_api;
insert into proposal_assistant_results
  select 'manager reads exact pending action preview','pending_confirmation',state
  from app.assistant_action_previews where id='16161616-d000-4000-8000-000000000001';
update app.assistant_action_previews set state='dismissed',result='{"outcome":"dismissed"}',
  row_version=row_version+1,decided_by_auth_user_id=app.current_actor_id(),decided_at=now()
where id='16161616-d000-4000-8000-000000000001';
insert into proposal_assistant_results
  select 'manager may complete the explicit action decision','dismissed:2',
    state||':'||row_version::text from app.assistant_action_previews
  where id='16161616-d000-4000-8000-000000000001';
reset role;

update app.company_memberships set administrative_role='member'
where id='16161616-1000-4000-8000-000000000001';
set local role coordination_api;
insert into proposal_assistant_results values(
  'member cannot bind a planning proposal','false',
  app.can_bind_assistant_proposal(app.current_company_id(),
    '16161616-4000-4000-8000-000000000001',
    '16161616-a000-4000-8000-000000000001')::text);
insert into proposal_assistant_results
  select 'proposal thread is hidden after planning authority is lost','0',count(*)::text
  from app.assistant_threads where id='16161616-b000-4000-8000-000000000001';
reset role;
set local role coordination_worker;
select pg_temp.capture_error('member cannot stage a planning action',$q$
  insert into app.assistant_action_previews(
    id,company_id,message_id,command_type,target_id,expected_version,command_digest,
    expires_at,project_id,proposal_id,title,summary,action_payload
  ) values('16161616-d000-4000-8000-000000000003',app.current_company_id(),
    '16161616-c000-4000-8000-000000000001','plan_change',
    '16161616-a000-4000-8000-000000000001',1,decode(repeat('21',32),'hex'),
    now()+interval '30 minutes','16161616-4000-4000-8000-000000000001',
    '16161616-a000-4000-8000-000000000001','Unauthorised','Member action.','{}')$q$,
  '42501');
reset role;

select is(actual,expected,label) from proposal_assistant_results order by label;
select is((select max(version) from app.ai_plan_proposals
  where snapshot_id='16161616-9000-4000-8000-000000000001'),5,
  'proposal chain accepts the bounded fifth revision');
select col_is_null('app','assistant_threads','proposal_id',
  'proposal binding remains nullable for existing non-proposal conversations');
select ok(not has_column_privilege('coordination_api','app.assistant_threads','proposal_id','UPDATE'),
  'API cannot rebind a saved assistant thread');
select ok(has_column_privilege('coordination_api','app.assistant_action_previews','state','UPDATE'),
  'API may advance only reviewed action lifecycle columns');
select ok(not has_column_privilege('coordination_api','app.assistant_action_previews','title','UPDATE'),
  'API cannot rewrite the staged action description');
select ok(has_function_privilege('coordination_api',
  'app.retry_durable_planning_job(uuid,uuid,text,text,bytea)','EXECUTE'),
  'API retains explicit bounded planning retry permission');
select ok(not has_function_privilege('coordination_worker',
  'app.retry_durable_planning_job(uuid,uuid,text,text,bytea)','EXECUTE'),
  'worker cannot authorize its own planning retry');
select * from finish();
rollback;
