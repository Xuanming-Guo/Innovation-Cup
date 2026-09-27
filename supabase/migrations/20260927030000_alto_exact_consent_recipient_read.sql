-- A shared version is visible to its exact current audience, including its consent timestamp.
create policy preference_decision_recipient_read on app.employee_preference_share_decisions
for select to coordination_api using(
 decision='share' and revoked_at is null and exists(select 1 from app.company_memberships m
   where m.company_id=employee_preference_share_decisions.company_id
     and m.id=audience_membership_id and m.user_id=app.current_actor_id() and m.membership_status='active')
 and ((demo_run_id is null and audience_employee_id is null)
   or(demo_run_id is not null and audience_employee_id=app.effective_employee_id(company_id,app.current_actor_id())))
 and app.can_read_preference(company_id,preference_version_id));
insert into app_private.migration_contract(version,name) values ('20260927030000','alto_exact_consent_recipient_read');
