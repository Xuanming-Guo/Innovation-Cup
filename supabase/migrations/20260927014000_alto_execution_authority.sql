-- DB02/05/06 completion: real identity stays immutable; simulation is explicit and scoped.
create or replace function app.can_manage_planning(p_company_id uuid,p_user_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select app.has_active_membership(p_company_id,p_user_id)
 and case when app.current_demo_run_id() is null then exists(select 1 from app.company_memberships
   where company_id=p_company_id and user_id=p_user_id and membership_status='active' and administrative_role in ('manager','company_admin'))
 else app.scope_access(p_company_id,app.current_demo_run_id(),true)
   and app.can_access_demo_run(p_company_id,app.current_demo_run_id(),p_user_id,true) and
   case when nullif(current_setting('app.demo_actor_session_id',true),'') is null then exists(select 1 from app.company_memberships
     where company_id=p_company_id and user_id=p_user_id and membership_status='active' and administrative_role in ('manager','company_admin'))
   else exists(select 1 from app.employee_profiles where company_id=p_company_id
     and id=app.authorised_demo_actor(p_company_id,app.current_demo_run_id(),p_user_id) and synthetic_key in ('maya','jordan')) end end
$$;
create or replace function app.can_read_planning_request(p_company_id uuid,p_user_id uuid,p_request_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select app.can_manage_planning(p_company_id,p_user_id) and exists(select 1 from app.planning_requests
   where company_id=p_company_id and id=p_request_id and app.scope_access(company_id,demo_run_id,false))
$$;
create or replace function app.can_read_task(p_user_id uuid,p_company_id uuid,p_task_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.work_items i where i.company_id=p_company_id and i.task_id=p_task_id
 and app.scope_access(i.company_id,i.demo_run_id,false) and (
   app.can_manage_planning(p_company_id,p_user_id)
   or exists(select 1 from app.work_assignments a join app.execution_resources r on r.company_id=a.company_id and r.id=a.resource_id
     where a.company_id=i.company_id and a.task_id=i.task_id and a.active and r.status='active'
       and r.employee_id=app.effective_employee_id(p_company_id,p_user_id))
   or exists(select 1 from app.task_access_grants g where g.company_id=i.company_id and g.task_id=i.task_id and g.active
     and g.employee_id=app.effective_employee_id(p_company_id,p_user_id))
   or exists(select 1 from app.task_review_policies p where p.company_id=i.company_id and p.task_id=i.task_id and p.active
     and p.reviewer_employee_id=app.effective_employee_id(p_company_id,p_user_id))))
$$;
create or replace function app.can_manage_task(p_user_id uuid,p_company_id uuid,p_task_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.work_items i where i.company_id=p_company_id and i.task_id=p_task_id
   and app.scope_access(i.company_id,i.demo_run_id,true) and (app.can_manage_planning(p_company_id,p_user_id)
   or exists(select 1 from app.task_access_grants g where g.company_id=i.company_id and g.task_id=i.task_id and g.active
     and g.access_role='manager' and g.employee_id=app.effective_employee_id(p_company_id,p_user_id))))
$$;
-- Source grants are evaluated against the selected fictional person, never against an impersonated Auth user.
create or replace function app.can_read_source(p_user_id uuid,p_company_id uuid,p_source_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select app.has_active_membership(p_company_id,p_user_id) and exists(select 1 from app.source_records s
 where s.company_id=p_company_id and s.id=p_source_id and s.status='active' and app.scope_access(s.company_id,s.demo_run_id,false)
 and ((s.demo_run_id is null and app.is_company_admin(p_company_id,p_user_id)) or exists(
   select 1 from app.source_access_grants g where g.company_id=s.company_id and g.source_id=s.id
   and g.revoked_at is null and (g.expires_at is null or g.expires_at>statement_timestamp())
   and (g.principal_kind='company' or (g.principal_kind='employee' and g.employee_id=app.effective_employee_id(p_company_id,p_user_id))
     or (g.principal_kind='team' and exists(select 1 from app.team_memberships tm
       where tm.company_id=p_company_id and tm.team_id=g.team_id and tm.employee_id=app.effective_employee_id(p_company_id,p_user_id)
       and tm.valid_from<=statement_timestamp() and (tm.valid_to is null or tm.valid_to>statement_timestamp())))))))
$$;
-- Rebind existing employee-only commands and audience checks without changing the real identity resolver.
-- The allowlist is explicit; catalog definitions retain all original transition/idempotency checks.
do $actors$ declare v record; d text; begin
 for v in select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname='app' and p.proname in ('transition_employee_task','submit_employee_task','review_task_submission',
   'can_read_employee_brief','can_manage_employee_brief','can_read_private_file','task_reviewer_display_name','task_employee_display_name')
 loop
   d:=pg_get_functiondef(v.oid);
   d:=replace(d,'app.employee_id_for_actor(', 'app.effective_employee_id(');
   execute d;
 end loop;
end $actors$;
-- Public employee/project projections cannot regain real-manager visibility while a specialist actor is selected.
create or replace function app.can_read_alto_project(p_company_id uuid,p_project_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.projects p where p.company_id=p_company_id and p.id=p_project_id
   and app.scope_access(p.company_id,p.demo_run_id,false) and (
   app.can_manage_planning(p_company_id,app.current_actor_id()) or exists(select 1 from app.project_access_grants g
     where g.company_id=p.company_id and g.project_id=p.id and g.revoked_at is null
       and g.employee_id=app.effective_employee_id(p_company_id,app.current_actor_id()))
   or exists(select 1 from app.work_items i where i.company_id=p.company_id and i.project_id=p.id
     and app.can_read_task(app.current_actor_id(),p_company_id,i.task_id))))
$$;
create or replace function app.actor_satisfies_plan_requirement(p_company_id uuid,p_user_id uuid,p_requirement_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.plan_approval_requirements r where r.company_id=p_company_id and r.id=p_requirement_id
 and app.scope_access(r.company_id,r.demo_run_id,false) and (
   (r.authority_kind='company_manager' and app.can_manage_planning(p_company_id,p_user_id))
   or(r.authority_kind='company_admin' and r.demo_run_id is null and app.is_company_admin(p_company_id,p_user_id))
   or(r.authority_kind='team_manager' and exists(select 1 from app.team_memberships tm
     where tm.company_id=p_company_id and tm.team_id=r.authority_team_id and tm.team_role='manager'
       and tm.employee_id=app.effective_employee_id(p_company_id,p_user_id)
       and tm.valid_from<=statement_timestamp() and (tm.valid_to is null or tm.valid_to>statement_timestamp())))))
$$;

create function app.scope_planning_revision(p_company_id uuid,p_lock boolean default false) returns bigint
language plpgsql security definer set search_path=pg_catalog,app as $$
declare v bigint;
begin
 if not app.scope_access(p_company_id,app.current_demo_run_id(),p_lock) then
   raise exception using errcode='42501',message='scope_access_denied'; end if;
 if app.current_demo_run_id() is null then
   if p_lock then select planning_revision into v from app.companies where id=p_company_id for update;
   else select planning_revision into v from app.companies where id=p_company_id; end if;
 else
   if p_lock then select planning_revision into v from app.demo_runs where company_id=p_company_id and id=app.current_demo_run_id() for update;
   else select planning_revision into v from app.demo_runs where company_id=p_company_id and id=app.current_demo_run_id(); end if;
 end if;
 return v;
end $$;
create function app.advance_scope_revision(p_company_id uuid,p_expected bigint,p_new bigint) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if not app.scope_access(p_company_id,app.current_demo_run_id(),true) or p_new<>p_expected+1 then
   raise exception using errcode='42501',message='scope_revision_invalid'; end if;
 if app.current_demo_run_id() is null then update app.companies set planning_revision=p_new where id=p_company_id and planning_revision=p_expected;
 else update app.demo_runs set planning_revision=p_new where company_id=p_company_id and id=app.current_demo_run_id() and planning_revision=p_expected; end if;
 if not found then raise exception using errcode='40001',message='scope_revision_stale'; end if;
end $$;
create function app.plan_validation_report(p_company_id uuid,p_plan_id uuid) returns jsonb
language sql stable security definer set search_path=pg_catalog,app as $$
 select case when p.author_kind='legacy_solver' then s.validation_report
   when v.product_status='CHECKED' and v.native_status='sat' and x.passed and x.candidate_digest=p.proposal_digest
    and v.pre_candidate_digest=p.proposal_digest and v.post_candidate_digest=p.proposal_digest
    and v.snapshot_digest=ss.snapshot_digest and cardinality(v.unverified_rule_ids)=0 and v.required_rule_ids<@v.covered_rule_ids
   then jsonb_build_object('valid',true,'validator_version',x.validator_version) else null end
 from app.plans p join app.planning_snapshots ss on ss.company_id=p.company_id and ss.id=p.snapshot_id
 left join app.solver_runs s on s.company_id=p.company_id and s.id=p.solver_run_id
 left join app.plan_verification_runs v on v.company_id=p.company_id and v.id=p.verification_run_id and v.proposal_id=p.ai_proposal_id
 left join app.plan_validation_runs x on x.company_id=p.company_id and x.id=p.validation_run_id and x.proposal_id=p.ai_proposal_id
 where p.company_id=p_company_id and p.id=p_plan_id and app.scope_access(p.company_id,p.demo_run_id,false)
$$;
-- Apply narrowly asserted substitutions to the established transactions, keeping all
-- approval, source freshness, outbox, audit and exact-placement checks intact.
do $commit$ declare d text; before_d text; begin
 select pg_get_functiondef('app.commit_approved_plan(uuid,uuid,bytea,bytea,bytea,bigint,bigint,text,text,bytea,uuid)'::regprocedure) into d;
 d:=replace(d,chr(13),''); before_d:=d;
 d:=replace(d,'join app.solver_runs as solver','left join app.solver_runs as solver');
 d:=replace(d,'request.project_id, solver.validation_report','request.project_id, app.plan_validation_report(plan.company_id,plan.id) as validation_report');
 d:=replace(d,'v_company.planning_revision <> p_base_company_revision','app.scope_planning_revision(p_company_id,true) <> p_base_company_revision');
 d:=replace(d,'and administrative_role in (''manager'', ''company_admin'')','and app.can_manage_planning(p_company_id,app.current_actor_id())');
 d:=replace(d,E'update app.companies\n  set planning_revision = v_new_revision\n  where id = p_company_id;',
   'perform app.advance_scope_revision(p_company_id,p_base_company_revision,v_new_revision);');
 d:=replace(d,'and committed_by_membership_id = v_membership_id','and scope_id=app.current_scope_id() and committed_by_membership_id = v_membership_id');
 if d=before_d or d like '%update app.companies%' or d not like '%app.plan_validation_report%' then
   raise exception 'ALTO commit compatibility precondition changed; review the current function'; end if;
 execute d;
 select pg_get_functiondef('app.record_plan_approval_decision(uuid,uuid,uuid,text,text,bytea,bytea,bytea,bytea,bigint,bigint,text,text,bytea,uuid)'::regprocedure) into d;
 d:=replace(d,'v_company.planning_revision <> p_base_company_revision','app.scope_planning_revision(p_company_id,false) <> p_base_company_revision');
 d:=replace(d,'and actor_membership_id = v_membership_id','and scope_id=app.current_scope_id() and actor_membership_id = v_membership_id');
 execute d;
end $commit$;

do $audit$ declare t text; begin
 foreach t in array array['task_events','task_reviews','plan_approval_decisions','plan_commitments','audit_events'] loop
  execute format('alter table app.%I add column performed_by_auth_user_id uuid references auth.users(id), add column simulated_actor_employee_id uuid, add foreign key(company_id,simulated_actor_employee_id) references app.employee_profiles(company_id,id)',t);
 end loop;
end $audit$;
create function app.record_alto_actor() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 new.performed_by_auth_user_id:=app.current_actor_id();
 new.simulated_actor_employee_id:=app.authorised_demo_actor(new.company_id,new.demo_run_id,app.current_actor_id());
 return new;
end $$;
do $audit$ declare t text; begin
 foreach t in array array['task_events','task_reviews','plan_approval_decisions','plan_commitments','audit_events'] loop
  execute format('create trigger alto_actor_audit before insert on app.%I for each row execute function app.record_alto_actor()',t);
 end loop;
end $audit$;

create function app.guard_task_dependency() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if not exists(select 1 from app.work_items a join app.work_items b on b.company_id=a.company_id and b.project_id=a.project_id
   where a.company_id=new.company_id and a.task_id=new.predecessor_task_id and b.task_id=new.successor_task_id
     and a.project_id=new.project_id and a.scope_id=b.scope_id) then
   raise exception using errcode='23514',message='dependency_project_mismatch'; end if;
 perform pg_advisory_xact_lock(hashtextextended(new.project_id::text,0));
 if exists(with recursive reachable(task_id) as (
   select new.successor_task_id union
   select e.successor_task_id from app.task_dependency_edges e join reachable r on r.task_id=e.predecessor_task_id
     where e.company_id=new.company_id and e.project_id=new.project_id and e.id<>new.id)
   select 1 from reachable where task_id=new.predecessor_task_id) then
   raise exception using errcode='23514',message='dependency_cycle'; end if;
 return new;
end $$;
create trigger dependency_cycle_guard before insert or update on app.task_dependency_edges
 for each row execute function app.guard_task_dependency();
create function app.guard_task_gate_transition() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if new.status=old.status or new.status not in ('in_progress','submitted','accepted') then return new; end if;
 if exists(select 1 from app.task_gate_requirements g join app.work_items i on i.company_id=g.company_id and i.task_id=g.required_task_id
   where g.company_id=new.company_id and g.task_id=new.task_id and (
    (g.required_state='accepted' and i.status<>'accepted')
    or(g.required_state='submitted' and i.status not in ('submitted','accepted'))
    or(g.required_submission_id is not null and not exists(select 1 from app.submissions s
      where s.company_id=g.company_id and s.id=g.required_submission_id and s.task_id=g.required_task_id
        and s.state=case when g.required_state='accepted' then 'accepted' else s.state end
        and s.state in ('submitted','accepted'))))) then
   raise exception using errcode='23514',message='task_acceptance_gate_blocked'; end if;
 return new;
end $$;
create trigger task_gate_transition before update of status on app.work_items for each row execute function app.guard_task_gate_transition();
revoke all on function app.scope_planning_revision(uuid,boolean),app.advance_scope_revision(uuid,bigint,bigint),
 app.plan_validation_report(uuid,uuid),app.record_alto_actor(),app.guard_task_dependency(),app.guard_task_gate_transition() from public;
grant execute on function app.scope_planning_revision(uuid,boolean),app.plan_validation_report(uuid,uuid) to coordination_api,coordination_worker;
insert into app_private.migration_contract(version,name) values ('20260927014000','alto_execution_authority');
