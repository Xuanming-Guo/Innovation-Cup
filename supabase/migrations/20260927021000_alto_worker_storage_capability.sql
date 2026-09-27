-- Leased worker Storage access is a per-file capability; Python never receives a global Storage secret.
create function app.current_job_targets(p_company_id uuid,p_kind text,p_aggregate_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.durable_jobs j where j.company_id=p_company_id
  and j.id=nullif(current_setting('app.job_id',true),'')::uuid
  and j.lease_token=nullif(current_setting('app.lease_token',true),'')::uuid
  and j.job_kind=p_kind and j.aggregate_id=p_aggregate_id and j.state='leased'
  and j.leased_until>statement_timestamp() and j.cancel_requested_at is null
  and j.demo_run_id is not distinct from app.current_demo_run_id() and app.alto_job_authorized(j.company_id,j.id))
$$;
create policy leased_file_metadata on app.private_files for select to coordination_worker using(
 app.current_job_targets(company_id,'private_file.scan',id) or app.current_job_targets(company_id,'voice.transcribe',id));
create policy leased_file_validation_metadata on app.private_files for update to coordination_worker using(
 app.current_job_targets(company_id,'private_file.scan',id) or app.current_job_targets(company_id,'voice.transcribe',id))
 with check(app.current_job_targets(company_id,'private_file.scan',id) or app.current_job_targets(company_id,'voice.transcribe',id));
grant select,update(validation_metadata,audio_duration_seconds,deleted_at) on app.private_files to coordination_worker;
create policy feedback_suggestion_worker on app.employee_feedback_entries for select to coordination_worker using(
 employee_id=app.effective_employee_id(company_id,app.current_actor_id()) and app.current_job_targets(company_id,'preference.suggest',id));
grant select on app.employee_feedback_entries to coordination_worker;
create policy preference_worker_suggestion on app.employee_preference_versions for insert to coordination_worker with check(
 employee_id=app.effective_employee_id(company_id,app.current_actor_id()) and origin='model_suggestion' and status='tentative'
 and model_run_id is not null and app.assert_alto_job_lease(company_id,nullif(current_setting('app.job_id',true),'')::uuid,
   nullif(current_setting('app.lease_token',true),'')::uuid));
grant select,insert on app.employee_preference_versions to coordination_worker;
alter table app.employee_preference_versions add foreign key(company_id,model_run_id) references app.model_runs(company_id,id);
alter table app.assistant_messages add foreign key(company_id,model_run_id) references app.model_runs(company_id,id);
create policy citation_worker_write on app.assistant_citations for insert to coordination_worker with check(
 exists(select 1 from app.assistant_messages m where m.company_id=assistant_citations.company_id and m.id=message_id
   and app.owns_thread(m.company_id,m.thread_id))
 and ((task_id is not null and app.can_read_task(app.current_actor_id(),company_id,task_id))
 or(source_version_id is not null and exists(select 1 from app.source_versions s where s.company_id=assistant_citations.company_id
   and s.id=source_version_id and app.can_read_source(app.current_actor_id(),s.company_id,s.source_id)))));
grant insert on app.assistant_citations to coordination_worker;
do $fences$ declare t text; begin
 foreach t in array array['assistant_messages','assistant_citations','employee_preference_versions'] loop
 execute format('create trigger alto_private_worker_lease before insert on app.%I for each row execute function app.fence_alto_ledger_lease()',t);
 end loop;
end $fences$;
create table app.voice_transcriptions(
 id uuid primary key,company_id uuid not null,file_id uuid not null,thread_id uuid not null,model_run_id uuid,
 transcript text not null check(length(transcript)<=8000),created_at timestamptz not null default clock_timestamp(),
 expires_at timestamptz not null default(clock_timestamp()+interval '1 hour'),unique(company_id,id),
 foreign key(company_id,id) references app.durable_jobs(company_id,id),
 foreign key(company_id,file_id) references app.private_files(company_id,id),
 foreign key(company_id,thread_id) references app.assistant_threads(company_id,id),
 foreign key(company_id,model_run_id) references app.model_runs(company_id,id),check(expires_at>created_at)
);
select app_private.install_alto_scope('app.voice_transcriptions');
select app_private.link_alto_scopes();
create policy voice_transcript_private_read on app.voice_transcriptions for select to coordination_api,coordination_worker
 using(expires_at>statement_timestamp() and app.owns_thread(company_id,thread_id));
create policy voice_transcript_worker_insert on app.voice_transcriptions for insert to coordination_worker with check(
 app.owns_thread(company_id,thread_id) and app.current_job_targets(company_id,'voice.transcribe',file_id)
 and id=nullif(current_setting('app.job_id',true),'')::uuid);
grant select on app.voice_transcriptions to coordination_api,coordination_worker;
grant insert on app.voice_transcriptions to coordination_worker;
create trigger voice_transcript_immutable before update on app.voice_transcriptions for each row execute function app.alto_immutable_row();
create trigger voice_transcript_lease before insert on app.voice_transcriptions for each row execute function app.fence_alto_ledger_lease();

create function public.authorize_alto_worker_storage(p_company_id uuid,p_job_id uuid,p_lease_token uuid,p_file_id uuid,p_action text)
returns jsonb language plpgsql security definer set search_path=pg_catalog,app as $$
declare j app.durable_jobs%rowtype; f app.private_files%rowtype; actor uuid; path text; bucket text; extension text;
begin
 -- This public-schema RPC is executable only by the Edge server's service role, never a client JWT.
 perform app.assert_alto_job_lease(p_company_id,p_job_id,p_lease_token);
 select * into strict j from app.durable_jobs where company_id=p_company_id and id=p_job_id;
 if j.aggregate_id<>p_file_id or j.job_kind not in ('private_file.scan','voice.transcribe') then
   raise exception using errcode='42501',message='worker_storage_target_denied'; end if;
 select m.user_id into actor from app.company_memberships m where m.company_id=j.company_id and m.id=j.requested_by_membership_id and m.membership_status='active';
 if actor is null then raise exception using errcode='42501',message='worker_storage_actor_denied'; end if;
 perform set_config('app.actor_id',actor::text,true); perform set_config('app.company_id',p_company_id::text,true);
 perform set_config('app.purpose','worker:storage-capability',true);
 perform set_config('app.demo_run_id',coalesce(j.demo_run_id::text,''),true);
 perform set_config('app.demo_actor_session_id',coalesce(j.demo_actor_session_id::text,''),true);
 select * into f from app.private_files where company_id=p_company_id and id=p_file_id and scope_id=j.scope_id;
 if not found or f.deleted_at is not null or not app.scope_access(f.company_id,f.demo_run_id,true) then
   raise exception using errcode='42501',message='worker_storage_target_denied'; end if;
 if j.job_kind='voice.transcribe' and (f.purpose<>'voice_audio' or f.thread_id is null or not app.owns_thread(p_company_id,f.thread_id)
   or f.uploader_employee_id<>app.effective_employee_id(p_company_id,actor)) then
   raise exception using errcode='42501',message='worker_storage_target_denied'; end if;
 bucket:=f.bucket_id; path:=f.object_path;
 if p_action='download-quarantine' then
   if j.job_kind<>'private_file.scan' or f.state<>'quarantined' or f.scan_state<>'pending' or bucket<>'coordination-quarantine' then
     raise exception using errcode='42501',message='worker_storage_state_denied'; end if;
 elsif p_action='upload-private' then
   if j.job_kind<>'private_file.scan' or f.state<>'quarantined' or f.scan_state<>'pending' then
     raise exception using errcode='42501',message='worker_storage_state_denied'; end if;
   extension:=substring(f.object_path from '\.[a-z0-9]+$');
   if extension not in ('.pdf','.docx','.csv','.txt','.png','.jpg','.jpeg','.webm','.mp4','.wav') then
     raise exception using errcode='42501',message='worker_storage_type_denied'; end if;
   bucket:='coordination-private';
   path:=p_company_id::text||'/'||case when f.demo_run_id is null then '' else 'runs/'||f.demo_run_id::text||'/' end||f.id::text||'/validated'||extension;
 elsif p_action='download-private' then
   if j.job_kind<>'voice.transcribe' or not app.can_read_private_file(actor,p_company_id,p_file_id) then
     raise exception using errcode='42501',message='worker_storage_state_denied'; end if;
 elsif p_action='delete-audio' then
   if f.purpose<>'voice_audio' then raise exception using errcode='42501',message='worker_storage_delete_denied'; end if;
 else raise exception using errcode='22023',message='worker_storage_action_invalid'; end if;
 if p_action<>'delete-audio' and f.expires_at is not null and f.expires_at<=statement_timestamp() then
   raise exception using errcode='42501',message='worker_storage_expired'; end if;
 return jsonb_build_object('file_id',f.id,'bucket_id',bucket,'object_path',path,'content_type',f.declared_mime_type,
   'size_bytes',f.size_bytes,'file_state',f.state,'purpose',f.purpose,'expires_at',f.expires_at);
end $$;
revoke all on function app.current_job_targets(uuid,text,uuid) from public;
grant execute on function app.current_job_targets(uuid,text,uuid) to coordination_worker;
revoke all on function public.authorize_alto_worker_storage(uuid,uuid,uuid,uuid,text)
 from public,anon,authenticated,coordination_api,coordination_worker;
grant execute on function public.authorize_alto_worker_storage(uuid,uuid,uuid,uuid,text) to service_role;
insert into app_private.migration_contract(version,name) values ('20260927021000','alto_worker_storage_capability');
