-- A viewer switching actors must not change who approved an immutable disclosure.
create function app.decision_authority_current(p_company_id uuid,p_decision_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.plan_approval_decisions d
 join app.plan_approval_requirements r on r.company_id=d.company_id and r.id=d.requirement_id
 join app.company_memberships m on m.company_id=d.company_id and m.id=d.actor_membership_id and m.membership_status='active'
 left join app.employee_profiles e on e.company_id=d.company_id and e.id=d.simulated_actor_employee_id
 where d.company_id=p_company_id and d.id=p_decision_id and app.scope_access(d.company_id,d.demo_run_id,false)
 and ((d.demo_run_id is null and app.actor_satisfies_plan_requirement(p_company_id,m.user_id,r.id))
   or(d.demo_run_id is not null and app.can_access_demo_run(p_company_id,d.demo_run_id,m.user_id,true) and (
     (r.authority_kind='company_manager' and
       ((d.simulated_actor_employee_id is null and m.administrative_role in ('manager','company_admin'))
         or(e.profile_kind='synthetic' and e.status='active' and e.synthetic_key in ('maya','jordan'))))
     or(r.authority_kind='team_manager' and exists(select 1 from app.team_memberships tm
       where tm.company_id=p_company_id and tm.team_id=r.authority_team_id and tm.employee_id=e.id and tm.team_role='manager'
       and tm.valid_from<=statement_timestamp() and (tm.valid_to is null or tm.valid_to>statement_timestamp())))))))
$$;
do $authority$ declare d text; begin
 d:=replace(pg_get_functiondef('app.can_read_employee_brief(uuid,uuid,uuid)'::regprocedure),chr(13),'');
 d:=replace(d,E'app.actor_satisfies_plan_requirement(\n        p_company_id, approver.user_id, requirement.id\n      )',
   'app.decision_authority_current(p_company_id,latest.id)');
 execute d;
 d:=replace(pg_get_functiondef('app.commit_approved_plan(uuid,uuid,bytea,bytea,bytea,bigint,bigint,text,text,bytea,uuid)'::regprocedure),chr(13),'');
 d:=replace(d,E'app.actor_satisfies_plan_requirement(\n          p_company_id, approver.user_id, requirement.id\n        )',
   'app.decision_authority_current(p_company_id,decision.id)'); execute d;
end $authority$;
create or replace function app.task_reviewer_display_name(p_user_id uuid,p_company_id uuid,p_policy_id uuid)
returns text language sql stable security definer set search_path=pg_catalog,app as $$
 select coalesce(e.display_name,u.display_name) from app.task_review_policies p
 join app.employee_profiles e on e.company_id=p.company_id and e.id=p.reviewer_employee_id and e.status='active'
 left join app.company_memberships m on m.company_id=e.company_id and m.id=e.membership_id and m.membership_status='active'
 left join app.user_profiles u on u.user_id=m.user_id
 where p.company_id=p_company_id and p.id=p_policy_id and app.can_read_task(p_user_id,p_company_id,p.task_id)
$$;
create or replace function app.task_employee_display_name(p_user_id uuid,p_company_id uuid,p_task_id uuid,p_employee_id uuid)
returns text language sql stable security definer set search_path=pg_catalog,app as $$
 select coalesce(e.display_name,u.display_name) from app.employee_profiles e
 left join app.company_memberships m on m.company_id=e.company_id and m.id=e.membership_id and m.membership_status='active'
 left join app.user_profiles u on u.user_id=m.user_id where e.company_id=p_company_id and e.id=p_employee_id
 and e.status='active' and app.can_read_task(p_user_id,p_company_id,p_task_id)
 and (exists(select 1 from app.work_assignments a join app.execution_resources er on er.company_id=a.company_id and er.id=a.resource_id
   where a.company_id=p_company_id and a.task_id=p_task_id and a.active and er.employee_id=p_employee_id)
 or exists(select 1 from app.submissions s where s.company_id=p_company_id and s.task_id=p_task_id and s.submitting_employee_id=p_employee_id))
$$;
-- Scope current-source checks cannot treat an absent or differently scoped plan as vacuously current.
alter function app.plan_sources_are_current(uuid,uuid) rename to legacy_plan_sources_are_current;
revoke all on function app.legacy_plan_sources_are_current(uuid,uuid) from public,anon,authenticated,service_role,coordination_api,coordination_worker;
create function app.plan_sources_are_current(p_company_id uuid,p_plan_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.plans p where p.company_id=p_company_id and p.id=p_plan_id and app.scope_access(p.company_id,p.demo_run_id,false))
 and app.legacy_plan_sources_are_current(p_company_id,p_plan_id)
$$;
-- Existing scoped gate requirements may be retained only if their meaning is unchanged.
do $gate_revisions$ declare d text; begin
 d:=replace(pg_get_functiondef('app.materialize_alto_execution_plan(uuid,uuid)'::regprocedure),chr(13),'');
 d:=replace(d,'   insert into app.task_dependency_edges(',
 '   if exists(select 1 from app.task_dependency_edges e where e.company_id=p_company_id
    and e.predecessor_task_id=(gate->>''predecessor_task_id'')::uuid and e.successor_task_id=(gate->>''successor_task_id'')::uuid
    and (e.required_state<>gate->>''required_state'' or e.minimum_lag_minutes<>coalesce((gate->>''minimum_lag_minutes'')::integer,0))) then
     raise exception using errcode=''55000'',message=''gate_revision_requires_explicit_supersession''; end if;
   insert into app.task_dependency_edges('); execute d;
end $gate_revisions$;
revoke all on function app.decision_authority_current(uuid,uuid),app.plan_sources_are_current(uuid,uuid) from public;
grant execute on function app.decision_authority_current(uuid,uuid),app.plan_sources_are_current(uuid,uuid) to coordination_api,coordination_worker;
insert into app_private.migration_contract(version,name) values ('20260927024000','alto_recorded_authority_and_brief_views');
