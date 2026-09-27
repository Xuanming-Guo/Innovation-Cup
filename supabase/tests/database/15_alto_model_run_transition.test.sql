-- Disposable/local database only, run as the migration/function owner. Fixtures,
-- temporary triggers and actual non-owner model checkpoints are all rolled back.
begin;
select no_plan();

create temporary table model_transition_probe (
  id integer primary key,
  company_id uuid not null,
  demo_run_id uuid,
  scope_id uuid generated always as (coalesce(demo_run_id, company_id)) stored,
  provider_profile_version_id uuid,
  input_digest bytea not null,
  model text not null default 'synthetic-no-provider-call',
  status text not null,
  output_digest bytea,
  usage jsonb not null default '{}',
  error_code text,
  completed_at timestamptz
) on commit drop;
create temporary table model_transition_before (like model_transition_probe including all)
  on commit drop;

-- This is the exact pre-35000 function body, confined to pg_temp. The regression
-- uses the REAL migrated app.model_run_transition() for every corrected case.
create function pg_temp.pre35000_model_run_transition() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
 if old.status in ('succeeded','failed','cancelled') or (to_jsonb(new)-array['status','output_digest','usage','error_code','completed_at'])
    is distinct from (to_jsonb(old)-array['status','output_digest','usage','error_code','completed_at'])
 then raise exception using errcode='55000',message='model_run_immutable_binding'; end if;
 return new;
end $$;
create trigger model_transition_control before update on model_transition_before
  for each row execute function pg_temp.pre35000_model_run_transition();
create trigger model_transition_actual before update on model_transition_probe
  for each row execute function app.model_run_transition();

insert into model_transition_probe(id,company_id,demo_run_id,provider_profile_version_id,input_digest,status)
select number, '15151515-1000-4000-8000-000000000001'::uuid,
  case when number % 2 = 1 then '15151515-2000-4000-8000-000000000001'::uuid end,
  '15151515-3000-4000-8000-000000000001'::uuid, decode(repeat('15',32),'hex'), 'running'
from generate_series(1,4) number;
insert into model_transition_before(id,company_id,demo_run_id,provider_profile_version_id,input_digest,status)
select id,company_id,demo_run_id,provider_profile_version_id,input_digest,status
from model_transition_probe;

select throws_ok($q$update model_transition_before set status='failed',
  error_code='model_invalid_output',completed_at=now() where id=1$q$,
  '55000','model_run_immutable_binding','old trigger rejects a valid run-scoped failure checkpoint');
select throws_ok($q$update model_transition_before set status='succeeded',
  output_digest=decode(repeat('16',32),'hex'),completed_at=now() where id=2$q$,
  '55000','model_run_immutable_binding','old trigger rejects a valid company-scoped success checkpoint');

select lives_ok($q$update model_transition_probe set status='succeeded',
  output_digest=decode(repeat('16',32),'hex'),usage='{"candidate_tokens":10}',completed_at=now()
  where id=1$q$,'actual patched trigger permits a run-scoped success checkpoint');
select lives_ok($q$update model_transition_probe set status='failed',
  error_code='model_invalid_output',completed_at=now() where id=2$q$,
  'actual patched trigger permits a company-scoped failure checkpoint');
select lives_ok($q$update model_transition_probe set status='cancelled',completed_at=now()
  where id=4$q$,'actual patched trigger permits cancellation from running');
select is((select scope_id from model_transition_probe where id=1),
  '15151515-2000-4000-8000-000000000001'::uuid,'run-scoped checkpoint retains generated run identity');
select is((select scope_id from model_transition_probe where id=2),
  '15151515-1000-4000-8000-000000000001'::uuid,'company-scoped checkpoint retains generated company identity');

select throws_ok($q$update model_transition_probe set company_id=gen_random_uuid() where id=3$q$,
  '55000','model_run_immutable_binding','company binding remains immutable');
select throws_ok($q$update model_transition_probe set demo_run_id=gen_random_uuid() where id=3$q$,
  '55000','model_run_immutable_binding','demo-run binding remains immutable');
select throws_ok($q$update model_transition_probe set provider_profile_version_id=gen_random_uuid()
  where id=3$q$,'55000','model_run_immutable_binding','provider-version binding remains immutable');
select throws_ok($q$update model_transition_probe set input_digest=decode(repeat('17',32),'hex')
  where id=3$q$,'55000','model_run_immutable_binding','input digest remains immutable');
select throws_ok($q$update model_transition_probe set model='changed-model' where id=3$q$,
  '55000','model_run_immutable_binding','model identity remains immutable');
select throws_ok($q$update model_transition_probe set usage='{"candidate_tokens":11}' where id=1$q$,
  '55000','model_run_immutable_binding','succeeded run cannot be changed');
select throws_ok($q$update model_transition_probe set error_code='changed' where id=2$q$,
  '55000','model_run_immutable_binding','failed run cannot be changed');
select throws_ok($q$update model_transition_probe set status='running',completed_at=null where id=4$q$,
  '55000','model_run_immutable_binding','cancelled run cannot be reopened');

-- Exercise the actual application table, its RLS, least-privileged column grants,
-- generated scope, immutable transition and live lease fence together. Company
-- scope avoids needing any scenario/provider/Auth login or model invocation.
select set_config('app.company_id','',true),set_config('app.demo_run_id','',true),
  set_config('app.demo_actor_session_id','',true),set_config('app.actor_id','',true);
insert into auth.users(id,instance_id,aud,role,email,created_at,updated_at) values(
  '15151515-aaaa-4aaa-8aaa-aaaaaaaaaaa1','00000000-0000-0000-0000-000000000000',
  'authenticated','authenticated','model-transition-test@example.invalid',now(),now());
insert into app.company_memberships(id,company_id,user_id,membership_status,administrative_role,joined_at)
values('15151515-4000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
  '15151515-aaaa-4aaa-8aaa-aaaaaaaaaaa1','active','manager',now());
insert into app.durable_jobs(id,company_id,job_kind,aggregate_id,payload,requested_by_membership_id,
  idempotency_key,command_digest,correlation_id,state,attempt_count,lease_owner,lease_token,
  leased_at,leased_until)
values('15151515-5000-4000-8000-000000000001','11111111-1111-4111-8111-111111111111',
  'plan.propose','15151515-6000-4000-8000-000000000001','{}',
  '15151515-4000-4000-8000-000000000001','model-transition-regression-lease',
  decode(repeat('15',32),'hex'),gen_random_uuid(),'leased',1,
  '15151515-7000-4000-8000-000000000001','15151515-8000-4000-8000-000000000001',
  clock_timestamp(),clock_timestamp()+interval '5 minutes');
select set_config('app.company_id','11111111-1111-4111-8111-111111111111',true),
  set_config('app.actor_id','15151515-aaaa-4aaa-8aaa-aaaaaaaaaaa1',true),
  set_config('app.purpose','test:model-transition',true),
  set_config('app.job_id','15151515-5000-4000-8000-000000000001',true),
  set_config('app.lease_token','15151515-8000-4000-8000-000000000001',true);
-- pgTAP is intentionally unavailable to the runtime role. Execute each business
-- statement as that role, record its result in a temporary invoker-owned harness,
-- then make pgTAP assertions after RESET ROLE. No application privileges change.
create temporary table model_checkpoint_results(label text,expected text,actual text) on commit drop;
grant insert,select on model_checkpoint_results to coordination_worker;
create function pg_temp.checkpoint_result(label text,statement text,expected text)
returns void language plpgsql security invoker as $$
declare observed text := '00000';
begin
  begin
    execute statement;
  exception when others then
    get stacked diagnostics observed = returned_sqlstate;
  end;
  insert into model_checkpoint_results values(label,expected,observed);
end $$;
set local role coordination_worker;
insert into app.model_runs(id,company_id,stage,model,prompt_version,schema_version,
  config_digest,input_digest,status)
select identity,'11111111-1111-4111-8111-111111111111','plan.propose',
  'synthetic-no-provider-call','regression.v1','regression.v1',
  decode(repeat('15',32),'hex'),decode(repeat('15',32),'hex'),'running'
from unnest(array['15151515-9000-4000-8000-000000000001'::uuid,
  '15151515-9000-4000-8000-000000000002'::uuid,
  '15151515-9000-4000-8000-000000000003'::uuid]) identity;

select pg_temp.checkpoint_result('non-owner worker can checkpoint an actual model failure',
  $q$update app.model_runs set status='failed',error_code='model_invalid_output',
  completed_at=now() where company_id=app.current_company_id()
  and id='15151515-9000-4000-8000-000000000001' and status='running'
  and demo_run_id is not distinct from app.current_demo_run_id() returning id$q$,'00000');
select pg_temp.checkpoint_result('non-owner worker can checkpoint an actual model success',
  $q$update app.model_runs set status='succeeded',output_digest=decode(repeat('16',32),'hex'),
  usage='{"candidate_tokens":10}',completed_at=now() where company_id=app.current_company_id()
  and id='15151515-9000-4000-8000-000000000002' and status='running'
  and demo_run_id is not distinct from app.current_demo_run_id() returning id$q$,'00000');
insert into model_checkpoint_results
select 'both real worker checkpoints persist with unchanged generated scope','2',count(*)::text
from app.model_runs where company_id=app.current_company_id()
  and id in ('15151515-9000-4000-8000-000000000001','15151515-9000-4000-8000-000000000002')
  and status in ('failed','succeeded') and scope_id=company_id;
select pg_temp.checkpoint_result('worker cannot reopen an actual terminal model run',
  $q$update app.model_runs set status='running',completed_at=null
  where company_id=app.current_company_id() and id='15151515-9000-4000-8000-000000000001'$q$,
  '55000');
select set_config('app.lease_token','15151515-8000-4000-8000-000000000002',true);
select pg_temp.checkpoint_result('model checkpoint still requires its exact current lease token',
  $q$update app.model_runs set status='failed',error_code='model_invalid_output',
  completed_at=now() where company_id=app.current_company_id()
  and id='15151515-9000-4000-8000-000000000003'$q$,'40001');
reset role;
select is(actual,expected,label) from model_checkpoint_results order by label;
select is((select status from app.model_runs where id='15151515-9000-4000-8000-000000000003'),
  'running','rejected lease checkpoint leaves the model run unchanged');
select ok(not has_column_privilege('coordination_worker','app.model_runs','provider_profile_version_id','UPDATE'),
  'worker still cannot update provider binding directly');
select ok(not has_column_privilege('coordination_api','app.model_runs','status','UPDATE'),
  'API still cannot checkpoint model runs');

select * from finish();
rollback;
