-- DB09: private document/image artifacts and short-lived audio. A ticket is not a clean scan.
alter table app.private_files drop constraint private_files_purpose_check;
alter table app.private_files add constraint private_files_purpose_check check(purpose in ('source','submission','evidence','voice_audio')),
 add column task_id uuid,add column thread_id uuid,add column expires_at timestamptz,add column deleted_at timestamptz,
 add column validation_metadata jsonb not null default '{}' check(jsonb_typeof(validation_metadata)='object'),
 add column audio_duration_seconds numeric check(audio_duration_seconds>0 and audio_duration_seconds<=60),
 add foreign key(company_id,task_id) references app.work_items(company_id,task_id),
 add foreign key(company_id,thread_id) references app.assistant_threads(company_id,id),
 add constraint voice_file_shape check(purpose<>'voice_audio' or
  (thread_id is not null and task_id is null and source_id is null and expires_at is not null and size_bytes<=8388608
   and declared_mime_type in ('audio/webm','audio/mp4','audio/wav'))),
 add constraint nonvoice_file_mime check(purpose='voice_audio' or declared_mime_type not in ('audio/webm','audio/mp4','audio/wav')),
 add constraint image_file_limit check(declared_mime_type not in ('image/png','image/jpeg') or size_bytes<=10485760);
select app_private.link_alto_scopes();
create index private_audio_expiry on app.private_files(expires_at) where purpose='voice_audio' and deleted_at is null;
update storage.buckets set public=false,file_size_limit=26214400,allowed_mime_types=array[
 'application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','text/csv','text/plain',
 'image/png','image/jpeg','audio/webm','audio/mp4','audio/wav'] where id in ('coordination-quarantine','coordination-private');

create or replace function app.effective_employee_id(p_company_id uuid,p_user_id uuid)
returns uuid language sql stable security definer set search_path=pg_catalog,app as $$
 select case when app.current_demo_run_id() is null or nullif(current_setting('app.demo_actor_session_id',true),'') is null
 then app.employee_id_for_actor(p_company_id,p_user_id)
 else app.authorised_demo_actor(p_company_id,app.current_demo_run_id(),p_user_id) end
$$;
create or replace function app.can_read_private_file(p_user_id uuid,p_company_id uuid,p_file_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.private_files f where f.company_id=p_company_id and f.id=p_file_id
   and f.state='available' and f.scan_state='clean' and f.deleted_at is null
   and (f.expires_at is null or f.expires_at>statement_timestamp())
   and app.scope_access(f.company_id,f.demo_run_id,false) and (
    (f.uploader_employee_id=app.effective_employee_id(p_company_id,p_user_id)
     and (f.thread_id is null or app.owns_thread(p_company_id,f.thread_id)))
    or(f.purpose<>'voice_audio' and (
      (f.purpose='source' and f.source_id is not null and app.can_read_source(p_user_id,p_company_id,f.source_id))
      or exists(select 1 from app.submission_files sf join app.submissions s on s.company_id=sf.company_id and s.id=sf.submission_id
        where sf.company_id=f.company_id and sf.file_id=f.id and app.can_read_task(p_user_id,p_company_id,s.task_id))
      or exists(select 1 from app.task_input_links i where i.company_id=f.company_id and i.private_file_id=f.id
        and app.can_read_task(p_user_id,p_company_id,i.task_id))))))
$$;

create function app.issue_private_storage_ticket(p_action text,p_company_id uuid,p_file_id uuid,p_object_path text,
 p_purpose text,p_source_id uuid,p_display_filename text,p_content_type text,p_size_bytes bigint,
 p_demo_run_id uuid,p_demo_actor_session_id uuid,p_task_id uuid,p_thread_id uuid)
returns table(file_id uuid,bucket_id text,object_path text,file_state text)
language plpgsql security definer set search_path=pg_catalog,app as $$
declare actor uuid:=auth.uid(); employee uuid; prefix text; extension text; f app.private_files%rowtype;
begin
 if actor is null or not app.has_active_membership(p_company_id,actor) then return; end if;
 -- The JWT remains the real user. Scope/session selectors are verified, never substituted for auth.uid().
 perform set_config('app.actor_id',actor::text,true);
 perform set_config('app.company_id',p_company_id::text,true);
 perform set_config('app.purpose','storage:ticket',true);
 if p_action='create-download' then
  select * into f from app.private_files where company_id=p_company_id and id=p_file_id;
  if not found or f.demo_run_id is distinct from p_demo_run_id then return; end if;
 end if;
 perform set_config('app.demo_run_id',coalesce(p_demo_run_id::text,''),true);
 perform set_config('app.demo_actor_session_id',coalesce(p_demo_actor_session_id::text,''),true);
 if not app.scope_access(p_company_id,p_demo_run_id,p_action='create-upload') then return; end if;
 if p_demo_actor_session_id is not null and app.authorised_demo_actor(p_company_id,p_demo_run_id,actor) is null then return; end if;
 employee:=app.effective_employee_id(p_company_id,actor);
 if employee is null then return; end if;
 if p_action='create-download' then
   return query select x.id,x.bucket_id,x.object_path,x.state from app.private_files x
     where x.company_id=p_company_id and x.id=p_file_id and app.can_read_private_file(actor,p_company_id,p_file_id);
   return;
 end if;
 if p_action<>'create-upload' or p_file_id is null or p_display_filename is null
   or length(p_display_filename) not between 1 and 240 or p_display_filename ~ '[[:cntrl:]]'
   or p_size_bytes is null or p_size_bytes not between 1 and 26214400
   or p_purpose is null or p_purpose not in ('source','submission','evidence','voice_audio') then return; end if;
 extension:=case p_content_type
   when 'application/pdf' then '.pdf' when 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' then '.docx'
   when 'text/csv' then '.csv' when 'text/plain' then '.txt' when 'image/png' then '.png'
   when 'image/jpeg' then case when lower(p_display_filename) like '%.jpeg' then '.jpeg' else '.jpg' end
   when 'audio/webm' then '.webm' when 'audio/mp4' then '.mp4' when 'audio/wav' then '.wav' else null end;
 prefix:=p_company_id::text||'/'||case when p_demo_run_id is null then '' else 'runs/'||p_demo_run_id::text||'/' end||p_file_id::text||'/';
 if extension is null or lower(right(p_display_filename,length(extension)))<>extension
    or p_object_path is distinct from prefix||'payload'||extension then return; end if;
 if p_source_id is not null and not app.can_read_source(actor,p_company_id,p_source_id) then return; end if;
 if p_purpose='source' and p_source_id is null then return; end if;
 if p_task_id is not null and not app.can_read_task(actor,p_company_id,p_task_id) then return; end if;
 if p_thread_id is not null and not app.owns_thread(p_company_id,p_thread_id) then return; end if;
 if (p_content_type like 'audio/%')<>(p_purpose='voice_audio')
   or (p_purpose='voice_audio' and (p_thread_id is null or p_source_id is not null or p_task_id is not null or p_size_bytes>8388608))
   or (p_content_type in ('image/png','image/jpeg') and p_size_bytes>10485760) then return; end if;
 insert into app.private_files(id,company_id,demo_run_id,bucket_id,object_path,purpose,source_id,uploader_employee_id,
   display_filename,declared_mime_type,size_bytes,upload_intent_expires_at,task_id,thread_id,expires_at)
 values(p_file_id,p_company_id,p_demo_run_id,'coordination-quarantine',p_object_path,p_purpose,p_source_id,employee,
   p_display_filename,p_content_type,p_size_bytes,clock_timestamp()+interval '10 minutes',p_task_id,p_thread_id,
   case when p_purpose='voice_audio' then clock_timestamp()+interval '1 hour' end);
 return query select x.id,x.bucket_id,x.object_path,x.state from app.private_files x where x.company_id=p_company_id and x.id=p_file_id;
end $$;
-- Preserve callers using the original nine-argument signature, without its weaker path checks.
create or replace function app.issue_private_storage_ticket(p_action text,p_company_id uuid,p_file_id uuid,
 p_object_path text default null,p_purpose text default null,p_source_id uuid default null,p_display_filename text default null,
 p_content_type text default null,p_size_bytes bigint default null)
returns table(file_id uuid,bucket_id text,object_path text,file_state text)
language sql security definer set search_path=pg_catalog,app as $$
 select * from app.issue_private_storage_ticket(p_action,p_company_id,p_file_id,p_object_path,p_purpose,p_source_id,
   p_display_filename,p_content_type,p_size_bytes,null,null,null,null)
$$;
-- Finalisation only changes pending -> quarantined. Actual worker byte inspection alone can mark clean.
create function app.finalize_alto_upload(p_company_id uuid,p_file_id uuid,p_observed_size bigint)
returns boolean language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 update app.private_files f set state='quarantined',uploaded_at=clock_timestamp()
 where f.company_id=p_company_id and f.id=p_file_id and app.scope_access(f.company_id,f.demo_run_id,true)
   and f.uploader_employee_id=app.effective_employee_id(p_company_id,app.current_actor_id())
   and f.state='pending_upload' and f.upload_intent_expires_at>clock_timestamp()
   and f.size_bytes=p_observed_size and f.deleted_at is null and (f.expires_at is null or f.expires_at>clock_timestamp());
 return found;
end $$;
do $scan$ declare d text; begin
 d:=replace(pg_get_functiondef('app.record_private_file_scan(uuid,uuid,text,text,bigint,bytea,text,text)'::regprocedure),chr(13),'');
 d:=replace(d,'p_company_id::text || ''/'' || p_file_id::text || ''/%''',
   'p_company_id::text || ''/'' || (case when v_file.demo_run_id is null then '''' else ''runs/'' || v_file.demo_run_id::text || ''/'' end) || p_file_id::text || ''/%''');
 execute d;
end $scan$;
revoke all on function app.issue_private_storage_ticket(text,uuid,uuid,text,text,uuid,text,text,bigint,uuid,uuid,uuid,uuid),
 app.finalize_alto_upload(uuid,uuid,bigint) from public;
grant execute on function app.issue_private_storage_ticket(text,uuid,uuid,text,text,uuid,text,text,bigint,uuid,uuid,uuid,uuid) to authenticated;
grant execute on function app.finalize_alto_upload(uuid,uuid,bigint) to coordination_api;
insert into app_private.migration_contract(version,name) values ('20260927017000','alto_private_storage_lifecycle');
