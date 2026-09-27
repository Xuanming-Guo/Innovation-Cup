-- DB03/04/06/07/08: normalised read models, private drafts and explicit consent.
create table app.operating_groups(
 id uuid primary key default gen_random_uuid(), company_id uuid not null references app.companies(id),
 key text not null check(key in ('product','software')),label text not null,
 unique(company_id,id),unique(company_id,key)
);
create table app.employee_operating_group_memberships(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,employee_id uuid not null,group_id uuid not null,
 valid_from timestamptz not null,valid_to timestamptz,
 unique(company_id,id),foreign key(company_id,employee_id) references app.employee_profiles(company_id,id),
 foreign key(company_id,group_id) references app.operating_groups(company_id,id),check(valid_to is null or valid_to>valid_from)
);
create table app.skills(
 id uuid primary key default gen_random_uuid(),company_id uuid not null references app.companies(id),
 key text not null check(key ~ '^[a-z][a-z0-9_-]{0,63}$'),label text not null check(length(label) between 1 and 120),
 unique(company_id,id),unique(company_id,key)
);
create table app.employee_skill_evidence(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,employee_id uuid not null,skill_id uuid not null,
 evidence_kind text not null check(evidence_kind in ('declaration','accepted_experience','verified_qualification')),
 source_version_id uuid,accepted_submission_id uuid,status text not null check(status in ('declared','verified','revoked')),
 valid_from timestamptz not null default clock_timestamp(),valid_to timestamptz,recorded_by uuid references auth.users(id),
 unique(company_id,id),foreign key(company_id,employee_id) references app.employee_profiles(company_id,id),
 foreign key(company_id,skill_id) references app.skills(company_id,id),
 foreign key(company_id,source_version_id) references app.source_versions(company_id,id),
 foreign key(company_id,accepted_submission_id) references app.submissions(company_id,id),
 check(valid_to is null or valid_to>valid_from),
 check(evidence_kind<>'accepted_experience' or accepted_submission_id is not null),
 check(evidence_kind<>'verified_qualification' or (source_version_id is not null and status='verified'))
);
create table app.employee_working_rules(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,employee_id uuid not null,
 timezone text not null,weekly_windows jsonb not null check(jsonb_typeof(weekly_windows)='array'),
 capacity_limits jsonb not null check(jsonb_typeof(capacity_limits)='object'),
 valid_from timestamptz not null,valid_to timestamptz,source_version_id uuid,
 unique(company_id,id),foreign key(company_id,employee_id) references app.employee_profiles(company_id,id),
 foreign key(company_id,source_version_id) references app.source_versions(company_id,id),
 check(valid_to is null or valid_to>valid_from)
);
create table app.integration_connections(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,owner_membership_id uuid not null,
 provider text not null check(provider in ('teams','outlook','sharepoint')),
 mode text not null check(mode in ('fixture','live')),
 status text not null default 'unconfigured' check(status in ('unconfigured','ready','degraded','revoked')),
 timezone text not null default 'America/Los_Angeles',last_sync_at timestamptz,last_error_code text,
 updated_at timestamptz not null default clock_timestamp(),row_version bigint not null default 1 check(row_version>0),
 unique(company_id,id),foreign key(company_id,owner_membership_id) references app.company_memberships(company_id,id)
);
create table app.integration_grants(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,connection_id uuid not null,
 capability text not null check(length(capability) between 1 and 80),provider_scope text not null,
 access_mode text not null check(access_mode in ('read','write')),granted_by uuid not null,
 granted_at timestamptz not null default clock_timestamp(),revoked_at timestamptz,
 unique(company_id,id),foreign key(company_id,connection_id) references app.integration_connections(company_id,id),
 foreign key(company_id,granted_by) references app.company_memberships(company_id,id)
);
create table app.integration_sync_state(
 company_id uuid not null,connection_id uuid not null,cursor text,row_version bigint not null default 1,
 last_success_at timestamptz,primary key(company_id,connection_id),
 foreign key(company_id,connection_id) references app.integration_connections(company_id,id)
);
create table app.external_object_mappings(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,connection_id uuid not null,
 external_object_key text not null,local_subject_type text not null check(local_subject_type in ('source','task','calendar_event')),
 local_subject_id uuid not null,etag text,unique(company_id,id),unique(company_id,connection_id,external_object_key),
 foreign key(company_id,connection_id) references app.integration_connections(company_id,id)
);
create table app.calendar_event_versions(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,connection_id uuid not null,
 employee_id uuid not null,external_object_key text not null,external_version text not null,
 start_at timestamptz not null,end_at timestamptz not null,timezone text not null,
 status text not null check(status in ('busy','tentative','cancelled')),
 visibility text not null check(visibility in ('busy_only','owner','company')),
 title text check(length(title)<=240),source_version_id uuid,version_digest bytea not null check(octet_length(version_digest)=32),
 created_at timestamptz not null default clock_timestamp(),unique(company_id,id),
 unique(company_id,connection_id,external_object_key,external_version),
 foreign key(company_id,connection_id) references app.integration_connections(company_id,id),
 foreign key(company_id,employee_id) references app.employee_profiles(company_id,id),
 foreign key(company_id,source_version_id) references app.source_versions(company_id,id),check(end_at>start_at)
);
alter table app.projects add column goal_label text,add column accepted_at timestamptz,add column accepted_by_employee_id uuid,
 add foreign key(company_id,accepted_by_employee_id) references app.employee_profiles(company_id,id);
alter table app.work_items add column task_code text,add column workstream_key text,
 add column display_order integer not null default 0,add column layout_key text,
 add column purpose text,add column deliverable text,add column acceptance_criteria text[] not null default '{}';
create table app.project_workstreams(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,project_id uuid not null,
 function_key text not null check(function_key in ('engineering','design','qa','marketing','support')),
 label text not null,display_order integer not null,unique(company_id,id),unique(company_id,project_id,function_key),
 foreign key(company_id,project_id) references app.projects(company_id,id)
);
create table app.task_dependency_edges(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,project_id uuid not null,
 predecessor_task_id uuid not null,successor_task_id uuid not null,
 edge_kind text not null check(edge_kind in ('dependency','handoff','review','acceptance')),
 required_state text not null check(required_state in ('submitted','accepted')),
 required_submission_id uuid,minimum_lag_minutes integer not null default 0 check(minimum_lag_minutes>=0),
 unique(company_id,id),unique(company_id,predecessor_task_id,successor_task_id,edge_kind),
 foreign key(company_id,project_id) references app.projects(company_id,id),
 foreign key(company_id,predecessor_task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,successor_task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,required_submission_id) references app.submissions(company_id,id),check(predecessor_task_id<>successor_task_id)
);
create table app.task_gate_requirements(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,task_id uuid not null,gate_key text not null,
 required_task_id uuid not null,required_state text not null check(required_state in ('submitted','accepted')),
 required_submission_id uuid,unique(company_id,id),unique(company_id,task_id,gate_key,required_task_id),
 foreign key(company_id,task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,required_task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,required_submission_id) references app.submissions(company_id,id),check(task_id<>required_task_id)
);
create table app.task_input_links(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,task_id uuid not null,
 source_version_id uuid,private_file_id uuid,relation_kind text not null check(relation_kind in ('input','reference','acceptance_evidence')),
 unique(company_id,id),foreign key(company_id,task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,source_version_id) references app.source_versions(company_id,id),
 foreign key(company_id,private_file_id) references app.private_files(company_id,id),
 check((source_version_id is null)<>(private_file_id is null))
);
create table app.project_access_grants(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,project_id uuid not null,employee_id uuid not null,
 permission text not null check(permission in ('read','manage')),granted_by uuid not null,revoked_at timestamptz,
 unique(company_id,id),unique(company_id,project_id,employee_id,permission),
 foreign key(company_id,project_id) references app.projects(company_id,id),
 foreign key(company_id,employee_id) references app.employee_profiles(company_id,id),
 foreign key(company_id,granted_by) references app.company_memberships(company_id,id)
);
create table app.submission_drafts(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,task_id uuid not null,employee_id uuid not null,
 body text not null default '' check(length(body)<=50000),version bigint not null default 1 check(version>0),
 updated_at timestamptz not null default clock_timestamp(),unique(company_id,id),unique(company_id,task_id,employee_id),
 foreign key(company_id,task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,employee_id) references app.employee_profiles(company_id,id)
);
create table app.employee_feedback_entries(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,employee_id uuid not null,task_id uuid,
 body text not null check(length(btrim(body)) between 1 and 10000),created_at timestamptz not null default clock_timestamp(),
 unique(company_id,id),foreign key(company_id,employee_id) references app.employee_profiles(company_id,id),
 foreign key(company_id,task_id) references app.work_items(company_id,task_id)
);
create table app.employee_preference_versions(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,employee_id uuid not null,
 version integer not null check(version>0),parent_version_id uuid,
 text text not null check(length(btrim(text)) between 1 and 2000),
 origin text not null check(origin in ('employee','model_suggestion')),model_run_id uuid,
 status text not null check(status in ('tentative','confirmed','superseded')),
 created_at timestamptz not null default clock_timestamp(),unique(company_id,id),
 foreign key(company_id,employee_id) references app.employee_profiles(company_id,id),
 foreign key(company_id,parent_version_id) references app.employee_preference_versions(company_id,id)
);
create table app.employee_preference_share_decisions(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,preference_version_id uuid not null,
 audience_membership_id uuid,decision text not null check(decision in ('share','keep_private')),
 decided_by_auth_user_id uuid not null references auth.users(id),simulated_actor_employee_id uuid,
 decided_at timestamptz not null default clock_timestamp(),revoked_at timestamptz,
 unique(company_id,id),foreign key(company_id,preference_version_id) references app.employee_preference_versions(company_id,id),
 foreign key(company_id,audience_membership_id) references app.company_memberships(company_id,id),
 foreign key(company_id,simulated_actor_employee_id) references app.employee_profiles(company_id,id),
 check(decision<>'share' or audience_membership_id is not null)
);
create table app.assistant_threads(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,owner_membership_id uuid not null,
 simulated_employee_id uuid,
 context_type text not null check(context_type in ('workspace','project','task','person')),context_id uuid,
 created_at timestamptz not null default clock_timestamp(),archived_at timestamptz,
 unique(company_id,id),foreign key(company_id,owner_membership_id) references app.company_memberships(company_id,id),
 foreign key(company_id,simulated_employee_id) references app.employee_profiles(company_id,id),
 check((context_type='workspace')=(context_id is null))
);
create table app.assistant_messages(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,thread_id uuid not null,
 role text not null check(role in ('user','assistant')),content text not null check(length(content)<=20000),
 status text not null check(status in ('pending','running','completed','failed','cancelled')),
 model_run_id uuid,operation_id uuid,idempotency_key text not null check(length(idempotency_key) between 16 and 128),
 created_at timestamptz not null default clock_timestamp(),unique(company_id,id),unique(company_id,thread_id,idempotency_key),
 foreign key(company_id,thread_id) references app.assistant_threads(company_id,id),
 foreign key(company_id,operation_id) references app.durable_jobs(company_id,id)
);
create table app.assistant_citations(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,message_id uuid not null,
 source_version_id uuid,task_id uuid,permitted_label text not null check(length(permitted_label) between 1 and 240),
 unique(company_id,id),foreign key(company_id,message_id) references app.assistant_messages(company_id,id),
 foreign key(company_id,source_version_id) references app.source_versions(company_id,id),
 foreign key(company_id,task_id) references app.work_items(company_id,task_id),
 check((source_version_id is null)<>(task_id is null))
);
create table app.assistant_action_previews(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,message_id uuid not null,
 command_type text not null check(command_type in ('acknowledge_task','open_plan_review','open_task','share_preference')),
 target_id uuid not null,expected_version bigint not null check(expected_version>0),
 command_digest bytea not null check(octet_length(command_digest)=32),
 state text not null default 'pending' check(state in ('pending','confirmed','expired','cancelled')),
 expires_at timestamptz not null,unique(company_id,id),
 foreign key(company_id,message_id) references app.assistant_messages(company_id,id)
);

do $scope$ declare t text; begin
 foreach t in array array['employee_operating_group_memberships','employee_skill_evidence','employee_working_rules',
 'integration_connections','integration_grants','integration_sync_state','external_object_mappings','calendar_event_versions',
 'project_workstreams','task_dependency_edges','task_gate_requirements','task_input_links','project_access_grants',
 'submission_drafts','employee_feedback_entries','employee_preference_versions','employee_preference_share_decisions',
 'assistant_threads','assistant_messages','assistant_citations','assistant_action_previews']
 loop perform app_private.install_alto_scope(('app.'||t)::regclass); end loop;
end $scope$;
select app_private.link_alto_scopes();
alter table app.employee_operating_group_memberships add constraint employee_group_period_no_overlap
 exclude using gist(company_id with =,scope_id with =,employee_id with =,tstzrange(valid_from,valid_to,'[)') with &&);
create unique index preference_version_number on app.employee_preference_versions(company_id,scope_id,employee_id,version);

create function app.can_read_alto_project(p_company_id uuid,p_project_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.projects p where p.company_id=p_company_id and p.id=p_project_id
   and app.scope_access(p.company_id,p.demo_run_id,false) and (
     exists(select 1 from app.company_memberships m where m.company_id=p.company_id and m.user_id=app.current_actor_id()
       and m.membership_status='active' and m.administrative_role in ('manager','company_admin'))
     or exists(select 1 from app.project_access_grants g where g.company_id=p.company_id and g.project_id=p.id
       and g.employee_id=app.effective_employee_id(p.company_id,app.current_actor_id()) and g.revoked_at is null)
     or exists(select 1 from app.work_items i where i.company_id=p.company_id and i.project_id=p.id
       and app.can_read_task(app.current_actor_id(),i.company_id,i.task_id))))
$$;
create function app.owns_thread(p_company_id uuid,p_thread_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.assistant_threads t join app.company_memberships m
   on m.company_id=t.company_id and m.id=t.owner_membership_id
   where t.company_id=p_company_id and t.id=p_thread_id and m.user_id=app.current_actor_id()
     and t.simulated_employee_id is not distinct from app.authorised_demo_actor(t.company_id,t.demo_run_id,app.current_actor_id())
     and app.scope_access(t.company_id,t.demo_run_id,false)
     and (t.context_type='workspace'
       or (t.context_type='task' and app.can_read_task(app.current_actor_id(),t.company_id,t.context_id))
       or (t.context_type='project' and app.can_read_alto_project(t.company_id,t.context_id))
       or (t.context_type='person' and exists(select 1 from app.employee_profiles e where e.company_id=t.company_id and e.id=t.context_id))))
$$;

create function app.can_read_preference(p_company_id uuid,p_version_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.employee_preference_versions p where p.company_id=p_company_id and p.id=p_version_id
   and app.scope_access(p.company_id,p.demo_run_id,false) and (
     p.employee_id=app.effective_employee_id(p.company_id,app.current_actor_id()) or
     exists(select 1 from app.employee_preference_share_decisions d join app.company_memberships m
       on m.company_id=d.company_id and m.id=d.audience_membership_id
       where d.company_id=p.company_id and d.preference_version_id=p.id and d.decision='share'
         and d.revoked_at is null and m.user_id=app.current_actor_id() and m.membership_status='active')))
$$;
do $access$ declare t text; begin
 foreach t in array array['operating_groups','skills'] loop
   execute format('alter table app.%I enable row level security',t);
   execute format('create policy alto_company_read on app.%I for select to coordination_api,coordination_worker using(company_id=app.current_company_id() and app.has_active_membership(company_id,app.current_actor_id()))',t);
   execute format('grant select on app.%I to coordination_api,coordination_worker',t);
 end loop;
 foreach t in array array['employee_operating_group_memberships','employee_skill_evidence','employee_working_rules',
   'integration_connections','integration_grants','project_workstreams'] loop
   execute format('create policy alto_scoped_read on app.%I for select to coordination_api,coordination_worker using(app.scope_access(company_id,demo_run_id,false))',t);
   execute format('grant select on app.%I to coordination_api,coordination_worker',t);
 end loop;
 foreach t in array array['task_dependency_edges','task_gate_requirements','task_input_links','project_access_grants'] loop
   execute format('grant select on app.%I to coordination_api,coordination_worker',t);
 end loop;
end $access$;
create policy alto_project_read on app.projects for select to coordination_api,coordination_worker
 using(app.can_read_alto_project(company_id,id));
create policy dependency_read on app.task_dependency_edges for select to coordination_api,coordination_worker
 using(app.can_read_task(app.current_actor_id(),company_id,predecessor_task_id)
   and app.can_read_task(app.current_actor_id(),company_id,successor_task_id));
create policy gate_read on app.task_gate_requirements for select to coordination_api,coordination_worker
 using(app.can_read_task(app.current_actor_id(),company_id,task_id));
create policy task_input_read on app.task_input_links for select to coordination_api,coordination_worker
 using(app.can_read_task(app.current_actor_id(),company_id,task_id));
create policy project_grant_read on app.project_access_grants for select to coordination_api,coordination_worker
 using(app.can_read_alto_project(company_id,project_id));
alter table app.calendar_event_versions add constraint busy_title_private check(visibility<>'busy_only' or title is null);
create policy calendar_safe_read on app.calendar_event_versions for select to coordination_api,coordination_worker
 using(visibility in ('busy_only','company') or employee_id=app.effective_employee_id(company_id,app.current_actor_id()));
grant select on app.calendar_event_versions to coordination_api,coordination_worker;
create policy submission_drafts_self on app.submission_drafts for all to coordination_api
 using(employee_id=app.effective_employee_id(company_id,app.current_actor_id()) and exists(
   select 1 from app.work_items i join app.execution_resources r on r.company_id=i.company_id and r.id=i.owner_resource_id
     where i.company_id=submission_drafts.company_id and i.task_id=submission_drafts.task_id and r.employee_id=submission_drafts.employee_id))
 with check(employee_id=app.effective_employee_id(company_id,app.current_actor_id()) and exists(
   select 1 from app.work_items i join app.execution_resources r on r.company_id=i.company_id and r.id=i.owner_resource_id
     where i.company_id=submission_drafts.company_id and i.task_id=submission_drafts.task_id and r.employee_id=submission_drafts.employee_id));
grant select,insert,update on app.submission_drafts to coordination_api;
create policy feedback_self on app.employee_feedback_entries for all to coordination_api
 using(employee_id=app.effective_employee_id(company_id,app.current_actor_id()))
 with check(employee_id=app.effective_employee_id(company_id,app.current_actor_id()));
grant select,insert on app.employee_feedback_entries to coordination_api;
create policy preference_read on app.employee_preference_versions for select to coordination_api,coordination_worker
 using(app.can_read_preference(company_id,id));
create policy preference_self_insert on app.employee_preference_versions for insert to coordination_api
 with check(employee_id=app.effective_employee_id(company_id,app.current_actor_id()) and origin='employee' and model_run_id is null);
grant select,insert on app.employee_preference_versions to coordination_api;
create policy preference_decision_self on app.employee_preference_share_decisions for all to coordination_api
 using(exists(select 1 from app.employee_preference_versions p where p.company_id=employee_preference_share_decisions.company_id
   and p.id=preference_version_id and p.employee_id=app.effective_employee_id(p.company_id,app.current_actor_id())))
 with check(decided_by_auth_user_id=app.current_actor_id() and simulated_actor_employee_id is not distinct from
   app.authorised_demo_actor(company_id,app.current_demo_run_id(),app.current_actor_id()) and exists(
   select 1 from app.employee_preference_versions p where p.company_id=employee_preference_share_decisions.company_id
    and p.id=preference_version_id and p.employee_id=app.effective_employee_id(p.company_id,app.current_actor_id())
    and p.status='confirmed'));
grant select,insert,update(revoked_at) on app.employee_preference_share_decisions to coordination_api;
create policy thread_owner on app.assistant_threads for select to coordination_api,coordination_worker using(app.owns_thread(company_id,id));
create policy thread_insert on app.assistant_threads for insert to coordination_api with check(exists(
 select 1 from app.company_memberships m where m.company_id=assistant_threads.company_id and m.id=owner_membership_id
   and m.user_id=app.current_actor_id()) and simulated_employee_id is not distinct from
   app.authorised_demo_actor(company_id,demo_run_id,app.current_actor_id()) and (context_type='workspace'
   or(context_type='project' and app.can_read_alto_project(company_id,context_id))
   or(context_type='task' and app.can_read_task(app.current_actor_id(),company_id,context_id))
   or(context_type='person' and exists(select 1 from app.employee_profiles e where e.company_id=assistant_threads.company_id and e.id=context_id))));
grant select,insert on app.assistant_threads to coordination_api;
grant select on app.assistant_threads to coordination_worker;
create policy message_read on app.assistant_messages for select to coordination_api,coordination_worker using(app.owns_thread(company_id,thread_id));
create policy message_user_insert on app.assistant_messages for insert to coordination_api
 with check(app.owns_thread(company_id,thread_id) and role='user' and status='completed' and model_run_id is null);
create policy message_worker_insert on app.assistant_messages for insert to coordination_worker
 with check(app.owns_thread(company_id,thread_id) and role='assistant');
grant select,insert on app.assistant_messages to coordination_api,coordination_worker;
create policy citation_read on app.assistant_citations for select to coordination_api,coordination_worker
 using(exists(select 1 from app.assistant_messages m where m.company_id=assistant_citations.company_id and m.id=message_id
   and app.owns_thread(m.company_id,m.thread_id)) and (
   (task_id is not null and app.can_read_task(app.current_actor_id(),company_id,task_id)) or
   (source_version_id is not null and exists(select 1 from app.source_versions s where s.company_id=assistant_citations.company_id
     and s.id=source_version_id and app.can_read_source(app.current_actor_id(),s.company_id,s.source_id)))));
grant select on app.assistant_citations,app.assistant_action_previews to coordination_api,coordination_worker;
create policy action_preview_read on app.assistant_action_previews for select to coordination_api,coordination_worker
 using(exists(select 1 from app.assistant_messages m where m.company_id=assistant_action_previews.company_id and m.id=message_id
   and app.owns_thread(m.company_id,m.thread_id)));

create table app.alto_command_receipts(
 company_id uuid not null,actor_id uuid not null references auth.users(id),command_key text not null,
 idempotency_key text not null check(length(idempotency_key) between 16 and 128),
 command_digest bytea not null check(octet_length(command_digest)=32),
 result jsonb not null check(jsonb_typeof(result)='object' and octet_length(result::text)<=4096),
 created_at timestamptz not null default clock_timestamp()
);
select app_private.install_alto_scope('app.alto_command_receipts');
alter table app.alto_command_receipts add primary key(company_id,scope_id,actor_id,command_key,idempotency_key);
create policy command_receipt_self on app.alto_command_receipts for all to coordination_api
 using(actor_id=app.current_actor_id()) with check(actor_id=app.current_actor_id());
grant select,insert on app.alto_command_receipts to coordination_api;
revoke all on function app.can_read_alto_project(uuid,uuid),app.owns_thread(uuid,uuid),app.can_read_preference(uuid,uuid) from public;
grant execute on function app.can_read_alto_project(uuid,uuid),app.owns_thread(uuid,uuid),app.can_read_preference(uuid,uuid)
 to coordination_api,coordination_worker;
insert into app_private.migration_contract(version,name) values ('20260927012000','alto_workspace_domains');
