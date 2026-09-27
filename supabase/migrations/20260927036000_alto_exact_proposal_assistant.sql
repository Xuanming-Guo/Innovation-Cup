-- Bind a project assistant thread to one immutable proposal when discussing
-- verification results. Existing workspace/project/task/person threads remain
-- valid with a null proposal binding.
alter table app.assistant_threads
  add column proposal_id uuid,
  add constraint assistant_thread_proposal_project_check
    check(proposal_id is null or (context_type='project' and context_id is not null)),
  add constraint assistant_thread_proposal_company_fk
    foreign key(company_id,proposal_id) references app.ai_plan_proposals(company_id,id);

create function app.can_bind_assistant_proposal(
  p_company_id uuid,p_project_id uuid,p_proposal_id uuid
) returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
  select p_project_id is not null and p_proposal_id is not null
    and app.can_manage_planning(p_company_id,app.current_actor_id())
    and exists(
      select 1
      from app.ai_plan_proposals proposal
      join app.planning_snapshots snapshot
        on snapshot.company_id=proposal.company_id and snapshot.id=proposal.snapshot_id
      join app.planning_requests request
        on request.company_id=snapshot.company_id and request.id=snapshot.request_id
      where proposal.company_id=p_company_id and proposal.id=p_proposal_id
        and request.project_id=p_project_id
        and proposal.scope_id=app.current_scope_id()
        and snapshot.scope_id=proposal.scope_id and request.scope_id=proposal.scope_id
    )
$$;

create or replace function app.owns_thread(p_company_id uuid,p_thread_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.assistant_threads t join app.company_memberships m
   on m.company_id=t.company_id and m.id=t.owner_membership_id
   where t.company_id=p_company_id and t.id=p_thread_id and m.user_id=app.current_actor_id()
     and m.membership_status='active'
     and t.simulated_employee_id is not distinct from
       app.authorised_demo_actor(t.company_id,t.demo_run_id,app.current_actor_id())
     and app.scope_access(t.company_id,t.demo_run_id,false)
     and (t.context_type='workspace'
       or (t.context_type='task' and app.can_read_task(app.current_actor_id(),t.company_id,t.context_id))
       or (t.context_type='project' and app.can_read_alto_project(t.company_id,t.context_id))
       or (t.context_type='person' and exists(select 1 from app.employee_profiles e
         where e.company_id=t.company_id and e.id=t.context_id)))
     and (t.proposal_id is null
       or app.can_bind_assistant_proposal(t.company_id,t.context_id,t.proposal_id)))
$$;

alter policy thread_owner on app.assistant_threads using(
 exists(select 1 from app.company_memberships m where m.company_id=assistant_threads.company_id
   and m.id=owner_membership_id and m.user_id=app.current_actor_id()
   and m.membership_status='active')
 and simulated_employee_id is not distinct from
   app.authorised_demo_actor(company_id,demo_run_id,app.current_actor_id())
 and app.scope_access(company_id,demo_run_id,false)
 and (context_type='workspace'
   or(context_type='project' and app.can_read_alto_project(company_id,context_id))
   or(context_type='task' and app.can_read_task(app.current_actor_id(),company_id,context_id))
   or(context_type='person' and exists(select 1 from app.employee_profiles e
     where e.company_id=assistant_threads.company_id and e.id=context_id)))
 and (proposal_id is null
   or app.can_bind_assistant_proposal(company_id,context_id,proposal_id)));

alter policy thread_insert on app.assistant_threads with check(
 exists(select 1 from app.company_memberships m where m.company_id=assistant_threads.company_id
   and m.id=owner_membership_id and m.user_id=app.current_actor_id()
   and m.membership_status='active')
 and simulated_employee_id is not distinct from
   app.authorised_demo_actor(company_id,demo_run_id,app.current_actor_id())
 and app.scope_access(company_id,demo_run_id,false)
 and (context_type='workspace'
   or(context_type='project' and app.can_read_alto_project(company_id,context_id))
   or(context_type='task' and app.can_read_task(app.current_actor_id(),company_id,context_id))
   or(context_type='person' and exists(select 1 from app.employee_profiles e
     where e.company_id=assistant_threads.company_id and e.id=context_id)))
 and (proposal_id is null
   or app.can_bind_assistant_proposal(company_id,context_id,proposal_id)));

revoke all on function app.can_bind_assistant_proposal(uuid,uuid,uuid)
  from public,anon,authenticated,service_role,coordination_api,coordination_worker;
grant execute on function app.can_bind_assistant_proposal(uuid,uuid,uuid)
  to coordination_api,coordination_worker;

insert into app_private.migration_contract(version,name)
values ('20260927036000','alto_exact_proposal_assistant');
