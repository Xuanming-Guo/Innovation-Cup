-- Descriptive self-declared skills are scoped profile presentation, never qualification authority.
create function app_private.valid_alto_declared_skills(p_skills jsonb) returns boolean
language sql immutable set search_path=pg_catalog as $$
 select case when jsonb_typeof(p_skills)='array' then jsonb_array_length(p_skills)<=20 and not exists(
   select 1 from jsonb_array_elements(p_skills) skill where jsonb_typeof(skill)<>'string'
     or length(skill#>>'{}') not between 1 and 120 or length(btrim(skill#>>'{}'))=0)
 else false end
$$;
revoke all on function app_private.valid_alto_declared_skills(jsonb) from public,anon,authenticated,service_role,coordination_api,coordination_worker;
create table app.employee_profile_overrides(
 company_id uuid not null,employee_id uuid not null,
 declared_skills jsonb not null check(app_private.valid_alto_declared_skills(declared_skills)),
 row_version bigint not null check(row_version>0),updated_at timestamptz not null default clock_timestamp(),
 updated_by_auth_user_id uuid not null references auth.users(id),simulated_actor_employee_id uuid,
 foreign key(company_id,employee_id) references app.employee_profiles(company_id,id),
 foreign key(company_id,simulated_actor_employee_id) references app.employee_profiles(company_id,id)
);
select app_private.install_alto_scope('app.employee_profile_overrides');
alter table app.employee_profile_overrides add primary key(company_id,scope_id,employee_id),
 add constraint profile_override_actor_shape check(
   simulated_actor_employee_id is null
   or(demo_run_id is not null and simulated_actor_employee_id=employee_id));
create policy profile_override_directory_read on app.employee_profile_overrides for select to coordination_api,coordination_worker
 using(company_id=app.current_company_id() and app.has_active_membership(company_id,app.current_actor_id()));
grant select on app.employee_profile_overrides to coordination_api,coordination_worker;

create function app.update_alto_profile_skills(p_company_id uuid,p_employee_id uuid,p_expected_version bigint,p_skills jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog,app as $$
declare canonical_version bigint; current_override app.employee_profile_overrides%rowtype;
begin
 if p_company_id is distinct from app.current_company_id()
   or not app.scope_access(p_company_id,app.current_demo_run_id(),true)
   or p_employee_id is distinct from app.effective_employee_id(p_company_id,app.current_actor_id()) then
   raise exception using errcode='42501',message='profile_edit_denied'; end if;
 if p_expected_version is null or p_expected_version<1 or not app_private.valid_alto_declared_skills(p_skills) then
   raise exception using errcode='22023',message='profile_skills_invalid'; end if;
 -- Serialize initial inserts without mutating the canonical company-owned synthetic employee.
 perform pg_advisory_xact_lock(hashtextextended('alto-profile:'||p_company_id::text||':'||app.current_scope_id()::text||':'||p_employee_id::text,0));
 select row_version into canonical_version from app.employee_profiles
   where company_id=p_company_id and id=p_employee_id and status='active' for share;
 if not found then raise exception using errcode='42501',message='profile_edit_denied'; end if;
 select * into current_override from app.employee_profile_overrides
   where company_id=p_company_id and scope_id=app.current_scope_id() and employee_id=p_employee_id for update;
 if found then
   if current_override.row_version<>p_expected_version then
     raise exception using errcode='40001',message='profile_version_stale'; end if;
   update app.employee_profile_overrides set declared_skills=p_skills,row_version=row_version+1,
     updated_at=clock_timestamp(),updated_by_auth_user_id=app.current_actor_id(),
     simulated_actor_employee_id=app.authorised_demo_actor(p_company_id,app.current_demo_run_id(),app.current_actor_id())
   where company_id=p_company_id and scope_id=app.current_scope_id() and employee_id=p_employee_id returning * into current_override;
 else
   if canonical_version<>p_expected_version then
     raise exception using errcode='40001',message='profile_version_stale'; end if;
   insert into app.employee_profile_overrides(company_id,employee_id,demo_run_id,declared_skills,row_version,
     updated_by_auth_user_id,simulated_actor_employee_id)
   values(p_company_id,p_employee_id,app.current_demo_run_id(),p_skills,canonical_version+1,app.current_actor_id(),
     app.authorised_demo_actor(p_company_id,app.current_demo_run_id(),app.current_actor_id())) returning * into current_override;
 end if;
 return jsonb_build_object('employee_id',current_override.employee_id,'row_version',current_override.row_version,
   'declared_skills',current_override.declared_skills);
end $$;
revoke all on function app.update_alto_profile_skills(uuid,uuid,bigint,jsonb)
 from public,anon,authenticated,service_role,coordination_api,coordination_worker;
grant execute on function app.update_alto_profile_skills(uuid,uuid,bigint,jsonb) to coordination_api;
insert into app_private.migration_contract(version,name) values ('20260927029000','alto_self_declared_profile_skills');
