-- Narrow leased-worker projections; capacity changes invalidate the exact planning snapshot.
create function app.current_alto_lease_worker() returns uuid
language plpgsql security definer set search_path=pg_catalog,app as $$
declare company uuid:=app.current_company_id(); job uuid:=nullif(current_setting('app.job_id',true),'')::uuid; worker uuid;
begin
 if company is null then raise exception using errcode='42501',message='worker_context_required'; end if;
 perform app.assert_alto_job_lease(company,job,nullif(current_setting('app.lease_token',true),'')::uuid);
 select lease_owner into strict worker from app.durable_jobs where company_id=company and id=job;
 return worker;
end $$;
create function app.preference_is_shared_to_viewer(p_company_id uuid,p_version_id uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if p_company_id is distinct from app.current_company_id() then return false; end if;
 perform app.assert_alto_job_lease(p_company_id,nullif(current_setting('app.job_id',true),'')::uuid,
   nullif(current_setting('app.lease_token',true),'')::uuid);
 -- Unlike owner readability, this predicate never treats private wording as shared.
 return exists(select 1 from app.employee_preference_versions p
   join app.employee_preference_share_decisions d on d.company_id=p.company_id and d.scope_id=p.scope_id and d.preference_version_id=p.id
   join app.company_memberships m on m.company_id=d.company_id and m.id=d.audience_membership_id
   where p.company_id=p_company_id and p.id=p_version_id and p.status='confirmed'
     and app.scope_access(p.company_id,p.demo_run_id,false) and d.decision='share' and d.revoked_at is null
     and m.user_id=app.current_actor_id() and m.membership_status='active'
     and ((p.demo_run_id is null and d.audience_employee_id is null)
       or(p.demo_run_id is not null and d.audience_employee_id=app.effective_employee_id(p.company_id,app.current_actor_id()))));
end $$;
revoke all on function app.current_alto_lease_worker(),app.preference_is_shared_to_viewer(uuid,uuid)
 from public,anon,authenticated,service_role,coordination_api,coordination_worker;
grant execute on function app.current_alto_lease_worker(),app.preference_is_shared_to_viewer(uuid,uuid) to coordination_worker;

create function app.source_in_assistant_context(p_company_id uuid,p_thread_id uuid,p_source_id uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog,app as $$
declare thread app.assistant_threads%rowtype; project uuid;
begin
 if p_company_id is distinct from app.current_company_id() or not app.owns_thread(p_company_id,p_thread_id)
   or not app.can_read_source(app.current_actor_id(),p_company_id,p_source_id) then return false; end if;
 perform app.assert_alto_job_lease(p_company_id,nullif(current_setting('app.job_id',true),'')::uuid,
   nullif(current_setting('app.lease_token',true),'')::uuid);
 if not exists(select 1 from app.durable_jobs j where j.company_id=p_company_id
   and j.id=nullif(current_setting('app.job_id',true),'')::uuid and j.job_kind='assistant.respond'
   and j.payload->>'thread_id'=p_thread_id::text) then return false; end if;
 select * into strict thread from app.assistant_threads where company_id=p_company_id and id=p_thread_id;
 if thread.context_type='person' then return false; end if;
 -- A revoked provider mapping cannot be laundered into a still-current source projection.
 if exists(select 1 from app.external_object_mappings x where x.company_id=p_company_id and x.scope_id=thread.scope_id
   and x.local_subject_type='source' and x.local_subject_id=p_source_id and not exists(
     select 1 from app.integration_connections c where c.company_id=x.company_id and c.scope_id=x.scope_id and c.id=x.connection_id
       and c.status in ('ready','degraded') and exists(select 1 from app.integration_grants g where g.company_id=c.company_id
         and g.scope_id=c.scope_id and g.connection_id=c.id and g.access_mode='read' and g.revoked_at is null))) then return false; end if;
 if thread.context_type='workspace' then return true; end if;
 if thread.context_type='project' and app.can_read_alto_project(p_company_id,thread.context_id) then project:=thread.context_id;
 elsif thread.context_type='task' and app.can_read_task(app.current_actor_id(),p_company_id,thread.context_id) then
   select project_id into project from app.work_items where company_id=p_company_id and scope_id=thread.scope_id and task_id=thread.context_id;
 else return false; end if;
 -- Only the relationship is disclosed; employees gain no SELECT access to the planning ledger.
 return exists(select 1 from app.planning_request_sources rs join app.planning_requests r
   on r.company_id=rs.company_id and r.scope_id=rs.scope_id and r.id=rs.request_id
   where rs.company_id=p_company_id and rs.scope_id=thread.scope_id and rs.source_id=p_source_id and r.project_id=project);
end $$;
revoke all on function app.source_in_assistant_context(uuid,uuid,uuid)
 from public,anon,authenticated,service_role,coordination_api,coordination_worker;
grant execute on function app.source_in_assistant_context(uuid,uuid,uuid) to coordination_worker;

create function app.invalidate_alto_capacity_revision() returns trigger
language plpgsql security definer set search_path=pg_catalog,app as $$
declare changed jsonb; company uuid; run uuid;
begin
 if tg_op='UPDATE' and (to_jsonb(new)-'updated_at')=(to_jsonb(old)-'updated_at') then return new; end if;
 changed:=case when tg_op='DELETE' then to_jsonb(old) else to_jsonb(new) end;
 company:=(changed->>'company_id')::uuid; run:=(changed->>'demo_run_id')::uuid;
 if run is null then
   update app.companies set planning_revision=planning_revision+1 where id=company;
 else
   update app.demo_runs set planning_revision=planning_revision+1 where company_id=company and id=run;
 end if;
 if tg_op='DELETE' then return old; end if;
 return new;
end $$;
revoke all on function app.invalidate_alto_capacity_revision() from public,anon,authenticated,service_role,coordination_api,coordination_worker;
-- Committed schedule rows deliberately keep the existing commit's single atomic revision advance.
create trigger alto_capacity_revision after insert or update or delete on app.planning_resource_profiles
 for each row execute function app.invalidate_alto_capacity_revision();
create trigger alto_capacity_revision after insert or update or delete on app.calendar_event_versions
 for each row execute function app.invalidate_alto_capacity_revision();
create trigger alto_capacity_revision after insert or update or delete on app.integration_connections
 for each row execute function app.invalidate_alto_capacity_revision();
create trigger alto_capacity_revision after insert or update or delete on app.integration_grants
 for each row execute function app.invalidate_alto_capacity_revision();
insert into app_private.migration_contract(version,name) values ('20260927028000','alto_worker_projection_and_capacity_freshness');
