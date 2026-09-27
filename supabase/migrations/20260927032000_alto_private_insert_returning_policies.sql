-- INSERT RETURNING must evaluate new-row ownership directly: a stable lookup helper
-- cannot see that row in the same statement's policy snapshot.
alter policy preference_read on app.employee_preference_versions using(
 employee_id=app.effective_employee_id(company_id,app.current_actor_id())
 or app.can_read_preference(company_id,id));
alter policy thread_owner on app.assistant_threads using(
 exists(select 1 from app.company_memberships m where m.company_id=assistant_threads.company_id
   and m.id=owner_membership_id and m.user_id=app.current_actor_id() and m.membership_status='active')
 and simulated_employee_id is not distinct from app.authorised_demo_actor(company_id,demo_run_id,app.current_actor_id())
 and (context_type='workspace'
   or(context_type='project' and app.can_read_alto_project(company_id,context_id))
   or(context_type='task' and app.can_read_task(app.current_actor_id(),company_id,context_id))
   or(context_type='person' and exists(select 1 from app.employee_profiles e
     where e.company_id=assistant_threads.company_id and e.id=context_id))));
insert into app_private.migration_contract(version,name) values ('20260927032000','alto_private_insert_returning_policies');
