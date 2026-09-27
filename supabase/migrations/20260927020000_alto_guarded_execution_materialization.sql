-- Exact checked changes may reschedule unaccepted work, never overwrite accepted evidence.
alter table app.task_dependency_edges drop constraint task_dependency_edges_required_state_check;
alter table app.task_dependency_edges add constraint task_dependency_edges_required_state_check
 check(required_state in ('submitted','accepted','approved','self_certified'));
alter table app.task_gate_requirements drop constraint task_gate_requirements_required_state_check;
alter table app.task_gate_requirements add constraint task_gate_requirements_required_state_check
 check(required_state in ('submitted','accepted','approved','self_certified'));

create function app.prepare_alto_plan_changes(p_company_id uuid,p_plan_id uuid) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
declare candidate jsonb; task jsonb; existing app.work_items%rowtype; expected_version bigint;
begin
 select a.candidate_payload into candidate from app.plans p join app.ai_plan_proposals a on a.company_id=p.company_id and a.id=p.ai_proposal_id
   where p.company_id=p_company_id and p.id=p_plan_id;
 if not found then return; end if;
 for task in select value from jsonb_array_elements(candidate#>'{proposal,draft,tasks}') order by value->>'task_id' loop
  select * into existing from app.work_items where company_id=p_company_id and task_id=(task->>'task_id')::uuid for update;
  expected_version:=(task->>'expected_work_version')::bigint;
  if found then
   if not app.scope_access(p_company_id,existing.demo_run_id,true) or expected_version is null or existing.row_version<>expected_version then
     raise exception using errcode='40001',message='work_version_stale'; end if;
   if existing.status in ('submitted','accepted','cancelled') then
     raise exception using errcode='55000',message='reviewed_work_requires_explicit_supersession'; end if;
   if not exists(select 1 from app.work_item_versions where company_id=p_company_id and task_id=existing.task_id) then
    insert into app.work_item_versions(company_id,demo_run_id,task_id,version,source_plan_id,content_digest,payload)
    values(p_company_id,existing.demo_run_id,existing.task_id,existing.row_version,existing.source_plan_id,
     extensions.digest(convert_to(to_jsonb(existing)::text,'UTF8'),'sha256'),to_jsonb(existing));
   end if;
   update app.work_assignments set active=false where company_id=p_company_id and task_id=existing.task_id and active;
   update app.committed_schedule_blocks set active=false where company_id=p_company_id and task_id=existing.task_id and active;
   update app.task_review_policies set active=false,superseded_at=clock_timestamp()
     where company_id=p_company_id and task_id=existing.task_id and active;
  elsif expected_version is not null then raise exception using errcode='40001',message='expected_work_missing'; end if;
 end loop;
end $$;
create function app.bind_alto_task_metadata() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
declare t jsonb;
begin
 select x.value into t from app.plans p join app.ai_plan_proposals a on a.company_id=p.company_id and a.id=p.ai_proposal_id
 cross join lateral jsonb_array_elements(a.candidate_payload#>'{proposal,draft,tasks}') x(value)
 where p.company_id=new.company_id and p.id=new.source_plan_id and x.value->>'task_id'=new.task_id::text;
 if found then
  new.task_code:=upper(t->>'task_key'); new.purpose:=t->>'purpose'; new.deliverable:=t->>'deliverable';
  new.acceptance_criteria:=array(select jsonb_array_elements_text(t->'acceptance_criteria'));
  select e.function_key into new.workstream_key from app.execution_resources r join app.employee_profiles e
   on e.company_id=r.company_id and e.id=r.employee_id where r.company_id=new.company_id and r.id=new.owner_resource_id;
  new.layout_key:=t->>'task_key';
 end if;
 return new;
end $$;
create trigger alto_task_metadata before insert on app.work_items for each row execute function app.bind_alto_task_metadata();
-- The original default policy remains for legacy plans, not as a fallback for AI-authored reviewer choices.
alter function app.create_default_committed_task_review_policy() rename to create_legacy_committed_task_review_policy;
create function app.create_default_committed_task_review_policy() returns trigger
language plpgsql security definer set search_path=pg_catalog,app as $$
begin return new; end $$;
drop trigger work_items_create_default_review_policy on app.work_items;
-- Legacy default remains attached under its original function OID for genuinely legacy plans.
create function app.create_alto_or_legacy_review_policy() returns trigger
language plpgsql security definer set search_path=pg_catalog,app as $$
declare reviewer uuid; requester uuid; author text;
begin
 select p.author_kind,r.requester_membership_id into author,requester from app.plans p join app.planning_requests r
 on r.company_id=p.company_id and r.id=p.request_id where p.company_id=new.company_id and p.id=new.source_plan_id;
 if author<>'legacy_solver' then return new; end if;
 select id into reviewer from app.employee_profiles where company_id=new.company_id and membership_id=requester and status='active';
 if reviewer is null or reviewer=new.owner_resource_id then return new; end if;
 insert into app.task_review_policies(company_id,demo_run_id,task_id,version,reviewer_employee_id,self_certifiable,
 assigned_by_membership_id,idempotency_key,command_digest,correlation_id,resulting_task_version)
 values(new.company_id,new.demo_run_id,new.task_id,1,reviewer,false,requester,'commit-review:'||new.task_id::text,
 extensions.digest(convert_to(new.task_id::text||':'||reviewer::text,'UTF8'),'sha256'),gen_random_uuid(),new.row_version)
 on conflict(company_id,task_id,version) do nothing;
 return new;
end $$;
create trigger work_items_create_default_review_policy after insert on app.work_items
 for each row execute function app.create_alto_or_legacy_review_policy();

create function app.materialize_alto_execution_plan(p_company_id uuid,p_plan_id uuid) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
declare candidate jsonb; t jsonb; gate jsonb; reviewer uuid; requester uuid; project uuid; task app.work_items%rowtype;
 policy text; policy_version integer; previous_version uuid;
begin
 select a.candidate_payload,r.requester_membership_id,r.project_id into candidate,requester,project
 from app.plans p join app.ai_plan_proposals a on a.company_id=p.company_id and a.id=p.ai_proposal_id
 join app.planning_requests r on r.company_id=p.company_id and r.id=p.request_id where p.company_id=p_company_id and p.id=p_plan_id;
 if not found then return; end if;
 for t in select value from jsonb_array_elements(candidate#>'{proposal,draft,tasks}') loop
   select * into strict task from app.work_items where company_id=p_company_id and task_id=(t->>'task_id')::uuid and source_plan_id=p_plan_id;
   policy:=t->>'review_policy'; reviewer:=null;
   if policy='exact_review' then
     select employee_id into reviewer from app.execution_resources where company_id=p_company_id
       and id=(t#>>'{reviewer_resource_ids,0}')::uuid and resource_kind='human' and status='active';
     if reviewer is null then raise exception using errcode='23514',message='named_reviewer_required'; end if;
   end if;
   if policy in ('exact_review','self_certifiable_internal_draft') then
     select coalesce(max(version),0)+1 into policy_version from app.task_review_policies where company_id=p_company_id and task_id=task.task_id;
     insert into app.task_review_policies(company_id,demo_run_id,task_id,version,reviewer_employee_id,self_certifiable,self_certification_rule,
       assigned_by_membership_id,idempotency_key,command_digest,correlation_id,resulting_task_version)
     values(p_company_id,task.demo_run_id,task.task_id,policy_version,reviewer,policy='self_certifiable_internal_draft',
       case when policy='self_certifiable_internal_draft' then 'Exact internal draft criteria; no external publication authority.' end,
       requester,'alto-review:'||p_plan_id::text||':'||task.task_id::text,
       extensions.digest(convert_to(t::text,'UTF8'),'sha256'),gen_random_uuid(),task.row_version);
   end if;
   select id into previous_version from app.work_item_versions where company_id=p_company_id and task_id=task.task_id order by version desc limit 1;
   insert into app.work_item_versions(company_id,demo_run_id,task_id,version,source_plan_id,previous_version_id,content_digest,payload)
   values(p_company_id,task.demo_run_id,task.task_id,task.row_version,p_plan_id,previous_version,
     extensions.digest(convert_to(to_jsonb(task)::text,'UTF8'),'sha256'),to_jsonb(task));
 end loop;
 for gate in select value from jsonb_array_elements(candidate#>'{proposal,draft,gates}') loop
   insert into app.task_dependency_edges(company_id,demo_run_id,project_id,predecessor_task_id,successor_task_id,edge_kind,required_state,minimum_lag_minutes)
   values(p_company_id,app.current_demo_run_id(),project,(gate->>'predecessor_task_id')::uuid,(gate->>'successor_task_id')::uuid,
    'acceptance',gate->>'required_state',coalesce((gate->>'minimum_lag_minutes')::integer,0))
   on conflict(company_id,predecessor_task_id,successor_task_id,edge_kind) do nothing;
   insert into app.task_gate_requirements(company_id,demo_run_id,task_id,gate_key,required_task_id,required_state)
   values(p_company_id,app.current_demo_run_id(),(gate->>'successor_task_id')::uuid,gate->>'rule_id',
     (gate->>'predecessor_task_id')::uuid,gate->>'required_state')
   on conflict(company_id,task_id,gate_key,required_task_id) do nothing;
 end loop;
end $$;
do $commit$ declare d text; begin
 d:=replace(pg_get_functiondef('app.commit_approved_plan(uuid,uuid,bytea,bytea,bytea,bigint,bigint,text,text,bytea,uuid)'::regprocedure),chr(13),'');
 d:=replace(d,'  insert into app.work_items (','  perform app.prepare_alto_plan_changes(p_company_id,p_plan_id);'||E'\n  insert into app.work_items (');
 d:=replace(d,'where placement.company_id = p_company_id and placement.plan_id = p_plan_id;',
 'where placement.company_id = p_company_id and placement.plan_id = p_plan_id
  on conflict(company_id,task_id) do update set source_request_id=excluded.source_request_id,source_plan_id=excluded.source_plan_id,
   title=excluded.title,scheduling_kind=excluded.scheduling_kind,start_at=excluded.start_at,finish_at=excluded.finish_at,
   owner_resource_id=excluded.owner_resource_id,committed_company_revision=excluded.committed_company_revision,
   employee_brief_version_id=excluded.employee_brief_version_id,task_code=excluded.task_code,workstream_key=excluded.workstream_key,
   purpose=excluded.purpose,deliverable=excluded.deliverable,acceptance_criteria=excluded.acceptance_criteria,
   status=case when app.work_items.owner_resource_id is distinct from excluded.owner_resource_id then excluded.status else app.work_items.status end
  where app.work_items.scope_id=excluded.scope_id
    and exists(select 1 from app.plans pp where pp.company_id=excluded.company_id and pp.id=excluded.source_plan_id and pp.author_kind<>''legacy_solver'');');
 d:=replace(d,'  insert into app.plan_approval_uses (','  perform app.materialize_alto_execution_plan(p_company_id,p_plan_id);'||E'\n  insert into app.plan_approval_uses (');
 execute d;
end $commit$;
-- Extend gate checking to preserve explicit approval and self-certification claims.
do $gates$ declare d text; begin
 d:=pg_get_functiondef('app.guard_task_gate_transition()'::regprocedure);
 d:=replace(d,'g.required_state=''accepted'' and i.status<>''accepted''',
   'g.required_state in (''accepted'',''approved'',''self_certified'') and i.status<>''accepted''');
 d:=replace(d,'or(g.required_submission_id is not null',
   'or(g.required_state=''self_certified'' and not exists(select 1 from app.task_reviews rv where rv.company_id=g.company_id and rv.task_id=g.required_task_id and rv.decision=''accepted'' and rv.self_certification_rule is not null))
    or(g.required_submission_id is not null');
 execute d;
end $gates$;
revoke all on function app.prepare_alto_plan_changes(uuid,uuid),app.bind_alto_task_metadata(),
 app.create_default_committed_task_review_policy(),app.create_alto_or_legacy_review_policy(),app.materialize_alto_execution_plan(uuid,uuid) from public;
insert into app_private.migration_contract(version,name) values ('20260927020000','alto_guarded_execution_materialization');
