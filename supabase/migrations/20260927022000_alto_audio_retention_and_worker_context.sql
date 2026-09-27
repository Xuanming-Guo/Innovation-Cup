-- Expired audio has a deletion-only capability independent of user/run/session lifetime.
create table app_private.alto_audio_cleanup_leases(
 company_id uuid not null,file_id uuid primary key,cleanup_token uuid not null unique,worker_id uuid not null,
 leased_until timestamptz not null,attempt_count integer not null default 1 check(attempt_count>0),completed_at timestamptz,
 foreign key(company_id,file_id) references app.private_files(company_id,id)
);
revoke all on app_private.alto_audio_cleanup_leases from public,anon,authenticated,service_role,coordination_api,coordination_worker;
create function app.claim_expired_audio_cleanup(p_worker_id uuid,p_limit integer)
returns table(file_id uuid,cleanup_token uuid) language plpgsql security definer set search_path=pg_catalog,app,app_private as $$
declare f record; token uuid;
begin
 if p_worker_id is null or p_limit not between 1 and 50 then raise exception using errcode='22023',message='cleanup_bounds_invalid'; end if;
 for f in select pf.company_id,pf.id from app.private_files pf
 left join app_private.alto_audio_cleanup_leases l on l.file_id=pf.id
 where pf.purpose='voice_audio' and pf.expires_at<=clock_timestamp() and pf.deleted_at is null
   and (l.file_id is null or (l.leased_until<=clock_timestamp() and l.completed_at is null))
 order by pf.expires_at for update of pf skip locked limit p_limit loop
   token:=gen_random_uuid();
   insert into app_private.alto_audio_cleanup_leases(company_id,file_id,cleanup_token,worker_id,leased_until)
   values(f.company_id,f.id,token,p_worker_id,clock_timestamp()+interval '60 seconds')
   on conflict on constraint alto_audio_cleanup_leases_pkey do update set cleanup_token=excluded.cleanup_token,
     worker_id=excluded.worker_id,leased_until=excluded.leased_until,attempt_count=app_private.alto_audio_cleanup_leases.attempt_count+1;
   return query select f.id,token;
 end loop;
end $$;
create function app.audio_object_paths(p_company_id uuid,p_demo_run_id uuid,p_file_id uuid,p_original_path text) returns jsonb
language sql immutable set search_path=pg_catalog as $$
 select jsonb_build_array(
   jsonb_build_object('bucket_id','coordination-quarantine','object_path',p_company_id::text||'/'||
     case when p_demo_run_id is null then '' else 'runs/'||p_demo_run_id::text||'/' end||p_file_id::text||'/payload'||substring(p_original_path from '\.[a-z0-9]+$')),
   jsonb_build_object('bucket_id','coordination-private','object_path',p_company_id::text||'/'||
     case when p_demo_run_id is null then '' else 'runs/'||p_demo_run_id::text||'/' end||p_file_id::text||'/validated'||substring(p_original_path from '\.[a-z0-9]+$')))
$$;
create function public.authorize_alto_audio_cleanup(p_file_id uuid,p_cleanup_token uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog,app,app_private as $$
declare f app.private_files%rowtype;
begin
 select pf.* into f from app.private_files pf join app_private.alto_audio_cleanup_leases l on l.company_id=pf.company_id and l.file_id=pf.id
 where pf.id=p_file_id and l.cleanup_token=p_cleanup_token and l.leased_until>clock_timestamp() and l.completed_at is null
   and pf.purpose='voice_audio' and pf.expires_at<=clock_timestamp() and pf.deleted_at is null;
 if not found then raise exception using errcode='42501',message='audio_cleanup_capability_invalid'; end if;
 return jsonb_build_object('file_id',f.id,'object_paths',app.audio_object_paths(f.company_id,f.demo_run_id,f.id,f.object_path));
end $$;
create function public.complete_alto_audio_cleanup(p_file_id uuid,p_cleanup_token uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog,app,app_private as $$
begin
 perform public.authorize_alto_audio_cleanup(p_file_id,p_cleanup_token);
 update app.private_files set state='deleted',deleted_at=clock_timestamp() where id=p_file_id;
 update app_private.alto_audio_cleanup_leases set completed_at=clock_timestamp() where file_id=p_file_id and cleanup_token=p_cleanup_token;
 return true;
end $$;
do $storage$ declare d text; begin
 d:=replace(pg_get_functiondef('public.authorize_alto_worker_storage(uuid,uuid,uuid,uuid,text)'::regprocedure),chr(13),'');
 d:=replace(d,E'if j.job_kind<>''voice.transcribe'' or not app.can_read_private_file(actor,p_company_id,p_file_id) then',
 'if j.job_kind=''private_file.scan'' and f.state=''quarantined'' then
     bucket:=''coordination-private'';
     path:=p_company_id::text||''/''||case when f.demo_run_id is null then '''' else ''runs/''||f.demo_run_id::text||''/'' end||f.id::text||''/validated''||substring(f.object_path from ''\.[a-z0-9]+$'');
   elsif j.job_kind<>''voice.transcribe'' or not app.can_read_private_file(actor,p_company_id,p_file_id) then');
 d:=replace(d,'''size_bytes'',f.size_bytes,''file_state'',f.state,''purpose'',f.purpose,''expires_at'',f.expires_at)',
 '''size_bytes'',f.size_bytes,''file_state'',f.state,''purpose'',f.purpose,''expires_at'',f.expires_at,
   ''object_paths'',case when p_action=''delete-audio'' then app.audio_object_paths(f.company_id,f.demo_run_id,f.id,f.object_path) end)');
 execute d;
end $storage$;
-- Existing global queue handlers restore the authoritative job context before domain writes.
create function app.restore_alto_job_context(p_company_id uuid,p_job_id uuid,p_token uuid) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
declare j app.durable_jobs%rowtype; actor uuid;
begin
 perform app.assert_alto_job_lease(p_company_id,p_job_id,p_token);
 select * into strict j from app.durable_jobs where company_id=p_company_id and id=p_job_id;
 select user_id into actor from app.company_memberships where company_id=j.company_id and id=j.requested_by_membership_id and membership_status='active';
 if actor is null then return; end if;
 perform set_config('app.actor_id',actor::text,true);perform set_config('app.company_id',p_company_id::text,true);
 perform set_config('app.demo_run_id',coalesce(j.demo_run_id::text,''),true);
 perform set_config('app.demo_actor_session_id',coalesce(j.demo_actor_session_id::text,''),true);
 perform set_config('app.job_id',p_job_id::text,true);perform set_config('app.lease_token',p_token::text,true);
end $$;
do $restore$ declare f record; d text; begin
 for f in select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='app'
   and p.proname in ('record_leased_private_file_scan','deliver_internal_outbox_intent') loop
 d:=replace(pg_get_functiondef(f.oid),chr(13),'');
 d:=replace(d,E'begin\n',E'begin\n  perform app.restore_alto_job_context(p_company_id,p_job_id,p_lease_token);\n');
 execute d;
 end loop;
end $restore$;
revoke all on function app.claim_expired_audio_cleanup(uuid,integer),app.audio_object_paths(uuid,uuid,uuid,text),
 public.authorize_alto_audio_cleanup(uuid,uuid),public.complete_alto_audio_cleanup(uuid,uuid),app.restore_alto_job_context(uuid,uuid,uuid)
 from public,anon,authenticated,coordination_api,coordination_worker;
grant execute on function app.claim_expired_audio_cleanup(uuid,integer),app.restore_alto_job_context(uuid,uuid,uuid) to coordination_worker;
grant execute on function public.authorize_alto_audio_cleanup(uuid,uuid),public.complete_alto_audio_cleanup(uuid,uuid) to service_role;
insert into app_private.migration_contract(version,name) values ('20260927022000','alto_audio_retention_and_worker_context');
