-- Completion of explicit audience, authenticated discovery, assistant and worker boundaries.
create or replace function public.resolve_coordination_host(p_company_id uuid) returns text
language sql stable security definer set search_path=pg_catalog as $$
 select e.api_origin from app.host_runtime_endpoints e where e.company_id=p_company_id
 and e.expires_at>statement_timestamp() and auth.uid() is not null and (
   app.has_active_membership(p_company_id,auth.uid()) or exists(select 1 from app.demo_workspace_policies p
     join app.companies c on c.id=p.company_id where p.company_id=p_company_id and p.enabled and c.is_demo and c.status='active'))
$$;

alter table app.employee_preference_share_decisions add column audience_employee_id uuid,
 add foreign key(company_id,audience_employee_id) references app.employee_profiles(company_id,id),
 add constraint preference_demo_audience check(decision<>'share' or
  (demo_run_id is null and audience_employee_id is null) or (demo_run_id is not null and audience_employee_id is not null));
create or replace function app.can_read_preference(p_company_id uuid,p_version_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.employee_preference_versions p where p.company_id=p_company_id and p.id=p_version_id
   and app.scope_access(p.company_id,p.demo_run_id,false) and (
     p.employee_id=app.effective_employee_id(p.company_id,app.current_actor_id()) or
     exists(select 1 from app.employee_preference_share_decisions d join app.company_memberships m
       on m.company_id=d.company_id and m.id=d.audience_membership_id
       where d.company_id=p.company_id and d.preference_version_id=p.id and d.decision='share' and d.revoked_at is null
         and m.user_id=app.current_actor_id() and m.membership_status='active'
         and (p.demo_run_id is null or d.audience_employee_id=app.effective_employee_id(p.company_id,app.current_actor_id())))))
$$;
create function app.validate_preference_share() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if new.decision='share' and not exists(select 1 from app.company_memberships m where m.company_id=new.company_id
   and m.id=new.audience_membership_id and m.membership_status='active'
   and ((new.demo_run_id is null and m.administrative_role in ('manager','company_admin'))
     or(new.demo_run_id is not null and app.can_access_demo_run(new.company_id,new.demo_run_id,m.user_id)
       and exists(select 1 from app.employee_profiles e where e.company_id=new.company_id and e.id=new.audience_employee_id
         and e.profile_kind='synthetic' and e.synthetic_key in ('maya','jordan'))))) then
   raise exception using errcode='42501',message='preference_audience_invalid'; end if;
 return new;
end $$;
create trigger preference_audience_guard before insert on app.employee_preference_share_decisions
 for each row execute function app.validate_preference_share();
create trigger preference_version_immutable before update or delete on app.employee_preference_versions
 for each row execute function app.alto_immutable_row();

create function app.enqueue_alto_assistant(p_company_id uuid,p_thread_id uuid,p_message_id uuid,p_idempotency_key text)
returns uuid language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if not app.owns_thread(p_company_id,p_thread_id) or not exists(select 1 from app.assistant_messages m
   where m.company_id=p_company_id and m.id=p_message_id and m.thread_id=p_thread_id and m.role='user') then
   raise exception using errcode='42501',message='assistant_thread_access_denied'; end if;
 return app.enqueue_alto_job(p_company_id,'assistant.respond',p_message_id,
   jsonb_build_object('thread_id',p_thread_id,'message_id',p_message_id),p_idempotency_key,
   extensions.digest(convert_to(p_thread_id::text||':'||p_message_id::text,'UTF8'),'sha256'),gen_random_uuid());
end $$;
create function app.cancel_alto_assistant(p_company_id uuid,p_thread_id uuid,p_idempotency_key text)
returns void language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if not app.owns_thread(p_company_id,p_thread_id) or length(p_idempotency_key) not between 16 and 128 then
   raise exception using errcode='42501',message='assistant_thread_access_denied'; end if;
 update app.durable_jobs j set cancel_requested_at=coalesce(j.cancel_requested_at,clock_timestamp()),
   state=case when j.state in ('queued','retry_scheduled') then 'cancelled' else j.state end,
   completed_at=case when j.state in ('queued','retry_scheduled') then clock_timestamp() else j.completed_at end,
   row_version=j.row_version+1
 where j.company_id=p_company_id and j.scope_id=app.current_scope_id() and j.job_kind='assistant.respond'
   and j.payload->>'thread_id'=p_thread_id::text and j.state in ('queued','retry_scheduled','leased');
end $$;
create policy assistant_owned_job_read on app.durable_jobs for select to coordination_api using(
 job_kind='assistant.respond' and app.owns_thread(company_id,(payload->>'thread_id')::uuid));
create function app.revoke_alto_connection(p_company_id uuid,p_connection_id uuid,p_expected_version bigint) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 update app.integration_connections c set status='revoked',updated_at=clock_timestamp(),row_version=c.row_version+1
 where c.company_id=p_company_id and c.id=p_connection_id and c.row_version=p_expected_version
 and app.scope_access(c.company_id,c.demo_run_id,true) and exists(select 1 from app.company_memberships m
   where m.company_id=c.company_id and m.id=c.owner_membership_id and m.user_id=app.current_actor_id());
 if not found then raise exception using errcode='40001',message='connection_version_or_authority_stale'; end if;
 update app.integration_grants set revoked_at=coalesce(revoked_at,clock_timestamp()) where company_id=p_company_id and connection_id=p_connection_id;
end $$;

-- Row-level expressions, as well as command bodies, must use explicit effective actor identity.
do $policies$ declare p record; u text; w text; begin
 for p in select pol.*,c.oid as rel from pg_policy pol join pg_class c on c.oid=pol.polrelid
  join pg_namespace n on n.oid=c.relnamespace where n.nspname='app' loop
   u:=pg_get_expr(p.polqual,p.rel); w:=pg_get_expr(p.polwithcheck,p.rel);
   if coalesce(u,'') like '%employee_id_for_actor%' or coalesce(w,'') like '%employee_id_for_actor%' then
     execute format('alter policy %I on %s %s %s',p.polname,p.rel::regclass,
       case when u is null then '' else 'using ('||replace(u,'app.employee_id_for_actor(','app.effective_employee_id(')||')' end,
       case when w is null then '' else 'with check ('||replace(w,'app.employee_id_for_actor(','app.effective_employee_id(')||')' end);
   end if;
 end loop;
end $policies$;
-- Scope-qualified replay lookups prevent the same command key in two runs from returning another run's IDs.
do $replay$ declare f record; d text; t text; begin
 for f in select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='app'
 and p.proname in ('transition_employee_task','submit_employee_task','review_task_submission','set_task_review_policy','retry_durable_planning_job') loop
   d:=replace(pg_get_functiondef(f.oid),chr(13),'');
   foreach t in array array['task_events','submissions','task_reviews','task_review_policies','durable_job_recoveries'] loop
     d:=replace(d,'from app.'||t||E'\n  where company_id = p_company_id',
        'from app.'||t||E'\n  where scope_id=app.current_scope_id() and company_id = p_company_id');
   end loop;
   execute d;
 end loop;
end $replay$;
-- Safe metadata on a model run still belongs to its initiating actor, not to any other visitor.
alter table app.model_runs add column performed_by_auth_user_id uuid default app.current_actor_id() references auth.users(id),
 add column simulated_employee_id uuid,add foreign key(company_id,simulated_employee_id) references app.employee_profiles(company_id,id);
create function app.bind_model_provider() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
declare version_id uuid; mode text;
begin
 new.performed_by_auth_user_id:=app.current_actor_id();
 new.simulated_employee_id:=app.authorised_demo_actor(new.company_id,new.demo_run_id,app.current_actor_id());
 if new.demo_run_id is not null then
   select r.mode,b.profile_version_id into mode,version_id from app.demo_runs r
    left join app.demo_run_provider_bindings b on b.company_id=r.company_id and b.run_id=r.id
    where r.company_id=new.company_id and r.id=new.demo_run_id;
   if mode='live' and version_id is null then raise exception using errcode='42501',message='demo_provider_not_bound'; end if;
   if new.provider_profile_version_id is not null and new.provider_profile_version_id is distinct from version_id then
     raise exception using errcode='42501',message='demo_provider_version_mismatch'; end if;
   new.provider_profile_version_id:=version_id;
 end if;
 return new;
end $$;
create trigger alto_model_provider before insert on app.model_runs for each row execute function app.bind_model_provider();
create policy model_private_operation_insert on app.model_runs for insert to coordination_worker with check(
 stage in ('assistant.respond','preference.suggest','voice.transcribe') and performed_by_auth_user_id=app.current_actor_id());
create policy model_private_operation_update on app.model_runs for update to coordination_worker
 using(performed_by_auth_user_id=app.current_actor_id()) with check(performed_by_auth_user_id=app.current_actor_id());
create policy model_private_operation_read on app.model_runs for select to coordination_api,coordination_worker
 using(performed_by_auth_user_id=app.current_actor_id() and simulated_employee_id is not distinct from
 app.authorised_demo_actor(company_id,demo_run_id,app.current_actor_id()));

create function app.get_demo_provider_binding() returns jsonb
language sql stable security definer set search_path=pg_catalog,app as $$
 select jsonb_build_object('profile_id',p.id,'current_profile_version_id',b.profile_version_id,
  'latest_profile_version_id',v.id,'version',v.version,'credential_hint',v.credential_hint,'provider',v.provider,
  'status',case when v.revoked_at is null then 'configured' else 'revoked' end)
 from app.demo_provider_profiles p join app.company_memberships m on m.company_id=p.company_id and m.id=p.owner_membership_id
 join lateral(select x.* from app.demo_provider_profile_versions x where x.company_id=p.company_id and x.profile_id=p.id
   order by x.version desc limit 1) v on true
 left join app.demo_run_provider_bindings b on b.company_id=p.company_id and b.run_id=app.current_demo_run_id()
 where p.company_id=app.current_company_id() and m.user_id=app.current_actor_id() and m.membership_status='active'
$$;
create function app.record_demo_ai_credential_test(p_provider text,p_credential_kind text,p_test_outcome text,p_validated_model text,p_correlation_id uuid)
returns void language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if not app.can_manage_planning(app.current_company_id(),app.current_actor_id())
   or p_provider not in ('gemini_developer_api','vertex_ai') or p_credential_kind not in ('api_key','vertex_service_account')
   or p_test_outcome not in ('accepted','rejected','unavailable') then
   raise exception using errcode='42501',message='demo_provider_test_invalid'; end if;
 insert into app.audit_events(company_id,demo_run_id,actor_membership_id,event_type,aggregate_type,aggregate_id,outcome,
   policy_revision,details,correlation_id)
 select m.company_id,app.current_demo_run_id(),m.id,'demo.provider.tested','demo_provider_profile',m.id,
   case when p_test_outcome='accepted' then 'accepted' else 'rejected' end,c.policy_revision,
   jsonb_build_object('provider',p_provider,'credential_kind',p_credential_kind,'test_outcome',p_test_outcome,'model',p_validated_model),p_correlation_id
 from app.company_memberships m join app.companies c on c.id=m.company_id where m.company_id=app.current_company_id() and m.user_id=app.current_actor_id();
end $$;
-- Keep seed and fork writes compatible with FORCE RLS on the internal capacity projection.
create policy resource_projection_owner_insert on app.planning_resource_profiles for insert to current_user
 with check(app.scope_access(company_id,demo_run_id,true));

revoke all on function app.validate_preference_share(),app.enqueue_alto_assistant(uuid,uuid,uuid,text),app.cancel_alto_assistant(uuid,uuid,text),
 app.revoke_alto_connection(uuid,uuid,bigint),app.bind_model_provider(),app.get_demo_provider_binding(),
 app.record_demo_ai_credential_test(text,text,text,text,uuid) from public;
grant execute on function app.enqueue_alto_assistant(uuid,uuid,uuid,text),app.cancel_alto_assistant(uuid,uuid,text),
 app.revoke_alto_connection(uuid,uuid,bigint),app.get_demo_provider_binding(),app.record_demo_ai_credential_test(text,text,text,text,uuid) to coordination_api;
insert into app_private.migration_contract(version,name) values ('20260927019000','alto_privacy_and_command_completion');
