-- DB10: operator-authored fixture templates are cloned, never another visitor's private run.
create table app.demo_scenario_manifests(
 company_id uuid not null references app.companies(id),scenario_key text not null,version integer not null check(version>0),
 manifest_digest bytea not null check(octet_length(manifest_digest)=32),fixture_schema_version text not null,
 manifest_payload jsonb not null check(jsonb_typeof(manifest_payload)='object' and octet_length(manifest_payload::text)<=2097152),
 created_at timestamptz not null default clock_timestamp(),primary key(company_id,scenario_key,version)
);
alter table app.demo_scenario_manifests enable row level security;
revoke all on app.demo_scenario_manifests from public,anon,authenticated,service_role,coordination_api,coordination_worker;
create trigger scenario_manifest_immutable before update or delete on app.demo_scenario_manifests
 for each row execute function app.alto_immutable_row();
alter table app.demo_runs add column initialised_at timestamptz;
create table app.demo_run_events(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,run_id uuid not null,
 event_key text not null check(length(event_key) between 16 and 128),event_type text not null check(event_type in ('initialised','clock_advanced','archived','joined')),
 clock_before timestamptz,clock_after timestamptz,performed_by_auth_user_id uuid not null references auth.users(id),
 simulated_actor_employee_id uuid,related_record_id uuid,created_at timestamptz not null default clock_timestamp(),
 unique(company_id,id),unique(company_id,run_id,event_key),foreign key(company_id,run_id) references app.demo_runs(company_id,id),
 foreign key(company_id,simulated_actor_employee_id) references app.employee_profiles(company_id,id)
);
alter table app.demo_run_events enable row level security;
create policy demo_run_event_read on app.demo_run_events for select to coordination_api,coordination_worker
 using(company_id=app.current_company_id() and app.can_access_demo_run(company_id,run_id,app.current_actor_id()));
grant select on app.demo_run_events to coordination_api,coordination_worker;
create trigger run_event_immutable before update or delete on app.demo_run_events for each row execute function app.alto_immutable_row();
create function app.demo_record_id(p_run uuid,p_key text) returns uuid
language plpgsql immutable set search_path=pg_catalog,extensions as $$
declare b bytea;
begin
 -- RFC 4122 UUIDv3: namespace run UUID + UTF-8 record key, correct version/variant bits.
 b:=extensions.digest(uuid_send(p_run)||convert_to(p_key,'UTF8'),'md5');
 b:=set_byte(b,6,(get_byte(b,6)&15)|48); b:=set_byte(b,8,(get_byte(b,8)&63)|128);
 return encode(b,'hex')::uuid;
end $$;
create function app.initialise_demo_run(p_company_id uuid,p_run_id uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog,app as $$
declare r app.demo_runs%rowtype; payload jsonb; item jsonb; project_id uuid; source_id uuid; version_id uuid; connection_id uuid;
 prior_run text:=current_setting('app.demo_run_id',true); prior_session text:=current_setting('app.demo_actor_session_id',true); audience jsonb;
begin
 select * into r from app.demo_runs where company_id=p_company_id and id=p_run_id for update;
 if not found or p_company_id<>app.current_company_id() or not app.can_access_demo_run(p_company_id,p_run_id,app.current_actor_id(),true) then
   raise exception using errcode='42501',message='demo_initialisation_denied'; end if;
 project_id:=app.demo_record_id(p_run_id,'project:launch');
 if r.initialised_at is not null then return jsonb_build_object('run_id',r.id,'project_id',project_id,'replayed',true); end if;
 select manifest_payload into payload from app.demo_scenario_manifests where company_id=p_company_id
   and scenario_key=r.scenario_key and version=r.scenario_version;
 if not found then raise exception using errcode='P0002',message='demo_scenario_not_provisioned'; end if;
 perform set_config('app.demo_run_id',p_run_id::text,true); perform set_config('app.demo_actor_session_id','',true);
 insert into app.projects(id,company_id,demo_run_id,owning_team_id,manager_employee_id,title,purpose,goal_label,requested_deadline)
 values(project_id,p_company_id,p_run_id,(payload#>>'{project,owning_team_id}')::uuid,(payload#>>'{project,manager_employee_id}')::uuid,
   payload#>>'{project,title}',payload#>>'{project,purpose}',payload#>>'{project,goal_label}',(payload#>>'{project,requested_deadline}')::timestamptz);
 insert into app.project_workstreams(id,company_id,demo_run_id,project_id,function_key,label,display_order)
 select app.demo_record_id(p_run_id,'workstream:'||x.key),p_company_id,p_run_id,project_id,x.key,x.label,x.ord
 from (values('engineering','Engineering',0),('design','Design',1),('qa','QA',2),('marketing','Marketing',3),('support','Support',4)) x(key,label,ord);
 for item in select value from jsonb_array_elements(coalesce(payload->'sources','[]')) loop
   source_id:=app.demo_record_id(p_run_id,'source:'||(item->>'key')); version_id:=app.demo_record_id(p_run_id,'source-version:'||(item->>'key'));
   insert into app.source_records(id,company_id,demo_run_id,owning_team_id,source_kind,title,classification,authority_status)
   values(source_id,p_company_id,p_run_id,(item->>'owning_team_id')::uuid,'fixture',item->>'title',coalesce(item->>'classification','internal'),'authoritative');
   insert into app.source_versions(id,company_id,demo_run_id,source_id,provider_version,content_sha256,retrieved_at,
     extraction_version,access_snapshot,expires_at)
   values(version_id,p_company_id,p_run_id,source_id,'fixture-'||r.scenario_version::text,
     extensions.digest(convert_to(item->>'text','UTF8'),'sha256'),clock_timestamp(),'alto-fixture.v1',
     jsonb_build_object('scenario_key',r.scenario_key,'scenario_version',r.scenario_version,'fixture',true),null);
   update app.source_records set current_version_id=version_id where company_id=p_company_id and id=source_id;
   insert into app.source_excerpts(id,company_id,demo_run_id,source_id,source_version_id,locator,permitted_text,text_sha256,extraction_version)
   values(app.demo_record_id(p_run_id,'excerpt:'||(item->>'key')),p_company_id,p_run_id,source_id,version_id,item->>'key',
     item->>'text',extensions.digest(convert_to(item->>'text','UTF8'),'sha256'),'alto-fixture.v1');
   if jsonb_typeof(item->'audience_employee_ids')='array' then
     for audience in select value from jsonb_array_elements(item->'audience_employee_ids') loop
       insert into app.source_access_grants(company_id,demo_run_id,source_id,principal_kind,employee_id,access_type,authority_reference)
       values(p_company_id,p_run_id,source_id,'employee',(audience#>>'{}')::uuid,'read','Operator-authored synthetic scenario scope');
     end loop;
   else
     insert into app.source_access_grants(company_id,demo_run_id,source_id,principal_kind,access_type,authority_reference)
     values(p_company_id,p_run_id,source_id,'company','read','Operator-authored company-readable synthetic fixture');
   end if;
 end loop;
 for item in select value from jsonb_array_elements(coalesce(payload->'connections','[]')) loop
   connection_id:=app.demo_record_id(p_run_id,'connection:'||(item->>'provider'));
   insert into app.integration_connections(id,company_id,demo_run_id,owner_membership_id,provider,mode,status,timezone,last_sync_at)
   values(connection_id,p_company_id,p_run_id,r.owner_membership_id,item->>'provider','fixture','ready',coalesce(item->>'timezone','America/Los_Angeles'),clock_timestamp());
   insert into app.integration_grants(company_id,demo_run_id,connection_id,capability,provider_scope,access_mode,granted_by)
   values(p_company_id,p_run_id,connection_id,'fixture.read','synthetic_scenario','read',r.owner_membership_id);
 end loop;
 for item in select value from jsonb_array_elements(coalesce(payload->'calendar','[]')) loop
   insert into app.calendar_event_versions(id,company_id,demo_run_id,connection_id,employee_id,external_object_key,external_version,
    start_at,end_at,timezone,status,visibility,title,version_digest)
   values(app.demo_record_id(p_run_id,'calendar:'||(item->>'key')),p_company_id,p_run_id,
    app.demo_record_id(p_run_id,'connection:'||(item->>'provider')),(item->>'employee_id')::uuid,item->>'key',r.scenario_version::text,
    (item->>'start_at')::timestamptz,(item->>'end_at')::timestamptz,item->>'timezone',coalesce(item->>'status','busy'),
    coalesce(item->>'visibility','busy_only'),case when coalesce(item->>'visibility','busy_only')<>'busy_only' then item->>'title' end,
    extensions.digest(convert_to(item::text,'UTF8'),'sha256'));
 end loop;
 for item in select value from jsonb_array_elements(coalesce(payload->'resource_profiles','[]')) loop
   insert into app.planning_resource_profiles(company_id,demo_run_id,resource_id,timezone,availability_windows,capability_keys,permission_keys,daily_active_minutes)
   values(p_company_id,p_run_id,(item->>'resource_id')::uuid,item->>'timezone',item->'availability_windows',
     coalesce(item->'capability_keys','[]'),coalesce(item->'permission_keys','[]'),(item->>'daily_active_minutes')::integer);
 end loop;
 for item in select value from jsonb_array_elements(coalesce(payload->'groups','[]')) loop
   insert into app.employee_operating_group_memberships(company_id,demo_run_id,employee_id,group_id,valid_from,valid_to)
   values(p_company_id,p_run_id,(item->>'employee_id')::uuid,(item->>'group_id')::uuid,(item->>'valid_from')::timestamptz,(item->>'valid_to')::timestamptz);
 end loop;
 for item in select value from jsonb_array_elements(coalesce(payload->'skills','[]')) loop
   insert into app.employee_skill_evidence(company_id,demo_run_id,employee_id,skill_id,evidence_kind,status)
   values(p_company_id,p_run_id,(item->>'employee_id')::uuid,(item->>'skill_id')::uuid,'declaration','declared');
 end loop;
 for item in select value from jsonb_array_elements(coalesce(payload->'working_rules','[]')) loop
   insert into app.employee_working_rules(company_id,demo_run_id,employee_id,timezone,weekly_windows,capacity_limits,valid_from,valid_to)
   values(p_company_id,p_run_id,(item->>'employee_id')::uuid,item->>'timezone',item->'weekly_windows',item->'capacity_limits',
    (item->>'valid_from')::timestamptz,(item->>'valid_to')::timestamptz);
 end loop;
 update app.demo_runs set initialised_at=clock_timestamp() where company_id=p_company_id and id=p_run_id;
 insert into app.demo_run_events(company_id,run_id,event_key,event_type,performed_by_auth_user_id,related_record_id)
 values(p_company_id,p_run_id,'initialise:'||p_run_id::text,'initialised',app.current_actor_id(),project_id);
 perform set_config('app.demo_run_id',coalesce(prior_run,''),true); perform set_config('app.demo_actor_session_id',coalesce(prior_session,''),true);
 return jsonb_build_object('run_id',r.id,'project_id',project_id,'replayed',false);
end $$;
-- Fork is atomic with fixture initialisation. Existing run retries retain the same identifiers.
do $fork$ declare d text; begin
 d:=replace(pg_get_functiondef('app.fork_demo_run(uuid,text,uuid,text)'::regprocedure),chr(13),'');
 d:=replace(d,'return v_id;','perform app.initialise_demo_run(p_company_id,v_id); return v_id;'); execute d;
end $fork$;
create function app.advance_demo_clock(p_company_id uuid,p_run_id uuid,p_expected_clock_version bigint,p_new_clock_at timestamptz,p_idempotency_key text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,app as $$
declare r app.demo_runs%rowtype; e app.demo_run_events%rowtype;
begin
 select * into r from app.demo_runs where company_id=p_company_id and id=p_run_id for update;
 if not found or p_company_id<>app.current_company_id() or not exists(select 1 from app.demo_run_memberships rm
   join app.company_memberships m on m.company_id=rm.company_id and m.id=rm.membership_id
   where rm.company_id=p_company_id and rm.run_id=p_run_id and rm.revoked_at is null and rm.run_role in ('owner','operator')
     and m.user_id=app.current_actor_id() and m.membership_status='active') then
   raise exception using errcode='42501',message='demo_operator_required'; end if;
 select * into e from app.demo_run_events where company_id=p_company_id and run_id=p_run_id and event_key=p_idempotency_key;
 if found then
   if e.event_type<>'clock_advanced' or e.clock_after<>p_new_clock_at then raise exception using errcode='23505',message='idempotency_key_reused'; end if;
   return jsonb_build_object('clock_at',r.clock_at,'clock_version',r.clock_version,'replayed',true);
 end if;
 if r.state<>'active' or r.clock_version<>p_expected_clock_version or p_new_clock_at<r.clock_at then
   raise exception using errcode='40001',message='demo_clock_stale'; end if;
 update app.demo_runs set clock_at=p_new_clock_at,clock_version=clock_version+1 where company_id=p_company_id and id=p_run_id;
 insert into app.demo_run_events(company_id,run_id,event_key,event_type,clock_before,clock_after,performed_by_auth_user_id)
 values(p_company_id,p_run_id,p_idempotency_key,'clock_advanced',r.clock_at,p_new_clock_at,app.current_actor_id());
 return jsonb_build_object('clock_at',p_new_clock_at,'clock_version',r.clock_version+1,'replayed',false);
end $$;
create function app.archive_demo_run(p_company_id uuid,p_run_id uuid,p_expected_version bigint) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
declare r app.demo_runs%rowtype; prior_run text:=current_setting('app.demo_run_id',true);
begin
 select * into r from app.demo_runs where company_id=p_company_id and id=p_run_id for update;
 if not found or p_company_id<>app.current_company_id() or not exists(select 1 from app.demo_run_memberships rm
   join app.company_memberships m on m.company_id=rm.company_id and m.id=rm.membership_id
   where rm.company_id=p_company_id and rm.run_id=p_run_id and rm.revoked_at is null and rm.run_role in ('owner','operator')
     and m.user_id=app.current_actor_id() and m.membership_status='active') then
   raise exception using errcode='42501',message='demo_operator_required'; end if;
 if r.state='archived' then return; end if;
 if r.row_version<>p_expected_version then raise exception using errcode='40001',message='demo_run_stale'; end if;
 perform set_config('app.demo_run_id',p_run_id::text,true);
 update app.durable_jobs set cancel_requested_at=clock_timestamp(),state='cancelled',completed_at=clock_timestamp(),
   lease_owner=null,lease_token=null,leased_at=null,leased_until=null,row_version=row_version+1
   where company_id=p_company_id and demo_run_id=p_run_id and state in ('queued','leased','retry_scheduled');
 update app.outbox_intents set state='cancelled',cancelled_at=clock_timestamp(),lease_owner=null,lease_token=null,leased_until=null
   where company_id=p_company_id and demo_run_id=p_run_id and state in ('pending','leased','retry_scheduled');
 update app.demo_actor_sessions set revoked_at=coalesce(revoked_at,clock_timestamp()) where company_id=p_company_id and run_id=p_run_id;
 insert into app.demo_run_events(company_id,run_id,event_key,event_type,performed_by_auth_user_id)
   values(p_company_id,p_run_id,'archive:'||p_run_id::text,'archived',app.current_actor_id());
 update app.demo_runs set state='archived',archived_at=clock_timestamp() where company_id=p_company_id and id=p_run_id;
 perform set_config('app.demo_run_id',coalesce(prior_run,''),true);
end $$;
revoke all on function app.demo_record_id(uuid,text),app.initialise_demo_run(uuid,uuid),
 app.advance_demo_clock(uuid,uuid,bigint,timestamptz,text),app.archive_demo_run(uuid,uuid,bigint) from public;
grant execute on function app.demo_record_id(uuid,text),app.initialise_demo_run(uuid,uuid),
 app.advance_demo_clock(uuid,uuid,bigint,timestamptz,text),app.archive_demo_run(uuid,uuid,bigint) to coordination_api;
insert into app_private.migration_contract(version,name) values ('20260927018000','alto_scenario_fork_and_clock');
