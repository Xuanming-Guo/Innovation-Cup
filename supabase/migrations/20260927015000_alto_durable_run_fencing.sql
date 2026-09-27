-- ALTO uses the existing leased queue. Provider stages are bounded checkpoints in one job.
alter table app.durable_jobs add column demo_actor_session_id uuid,add column simulated_employee_id uuid,
 add foreign key(company_id,demo_actor_session_id) references app.demo_actor_sessions(company_id,id),
 add foreign key(company_id,simulated_employee_id) references app.employee_profiles(company_id,id),
 add constraint job_actor_shape check((demo_actor_session_id is null)=(simulated_employee_id is null));
alter table app.durable_jobs drop constraint durable_jobs_job_kind_check;
alter table app.durable_jobs add constraint durable_jobs_job_kind_check check(job_kind in (
 'interpretation.run','planning.materialize','planning.run','plan.propose',
 'private_file.scan','outbox.deliver','assistant.respond','preference.suggest','voice.transcribe'));
create function app.bind_job_actor() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if new.demo_run_id is not null then
   if new.requested_by_membership_id is null then
     select id into new.requested_by_membership_id from app.company_memberships
       where company_id=new.company_id and user_id=app.current_actor_id() and membership_status='active';
   end if;
   new.demo_actor_session_id:=nullif(current_setting('app.demo_actor_session_id',true),'')::uuid;
   new.simulated_employee_id:=app.authorised_demo_actor(new.company_id,new.demo_run_id,app.current_actor_id());
   if new.demo_actor_session_id is not null and new.simulated_employee_id is null then
     raise exception using errcode='42501',message='job_actor_session_invalid'; end if;
 end if;
 return new;
end $$;
create trigger alto_job_bind_actor before insert on app.durable_jobs for each row execute function app.bind_job_actor();
create function app.alto_job_authorized(p_company_id uuid,p_job_id uuid) returns boolean
language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.durable_jobs j
 left join app.company_memberships m on m.company_id=j.company_id and m.id=j.requested_by_membership_id
 where j.company_id=p_company_id and j.id=p_job_id and (
   (j.demo_run_id is null and (j.requested_by_membership_id is null or m.membership_status='active'))
   or (j.demo_run_id is not null and app.can_access_demo_run(j.company_id,j.demo_run_id,m.user_id,true)
     and (j.demo_actor_session_id is null or exists(select 1 from app.demo_actor_sessions s
       where s.company_id=j.company_id and s.id=j.demo_actor_session_id and s.run_id=j.demo_run_id
         and s.performed_by_auth_user_id=m.user_id and s.simulated_actor_employee_id=j.simulated_employee_id
         and s.revoked_at is null and s.expires_at>statement_timestamp())))))
$$;
create function app.assert_alto_job_lease(p_company_id uuid,p_job_id uuid,p_token uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if not exists(select 1 from app.durable_jobs j where j.company_id=p_company_id and j.id=p_job_id
   and j.state='leased' and j.lease_token=p_token and j.leased_until>clock_timestamp()
   and j.cancel_requested_at is null and app.alto_job_authorized(j.company_id,j.id)
   and (app.current_company_id() is null or (j.company_id=app.current_company_id()
     and j.demo_run_id is not distinct from app.current_demo_run_id()
     and j.demo_actor_session_id is not distinct from nullif(current_setting('app.demo_actor_session_id',true),'')::uuid))) then
   raise exception using errcode='40001',message='job_lease_invalid'; end if;
 return true;
end $$;
create function app.fence_alto_ledger_lease() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if current_setting('role',true)='coordination_worker' then
   perform app.assert_alto_job_lease(new.company_id,nullif(current_setting('app.job_id',true),'')::uuid,
      nullif(current_setting('app.lease_token',true),'')::uuid);
 end if;
 return new;
end $$;
do $fences$ declare t text; begin
 foreach t in array array['model_runs','ai_plan_proposals','plan_verification_runs','plan_verification_rule_results','plan_validation_runs'] loop
   execute format('create trigger alto_lease_fence before insert or update on app.%I for each row execute function app.fence_alto_ledger_lease()',t);
 end loop;
end $fences$;

-- Return type extension requires drop/recreate; no table or historical job is dropped.
drop function app.lease_durable_jobs(uuid,integer,integer);
create function app.lease_durable_jobs(p_worker_id uuid,p_limit integer,p_lease_seconds integer)
returns table(job_id uuid,company_id uuid,job_kind text,aggregate_id uuid,payload jsonb,requested_by_membership_id uuid,
 requested_by_user_id uuid,administrative_role text,employee_id uuid,correlation_id uuid,attempt_count integer,
 max_attempts integer,lease_token uuid,leased_until timestamptz,demo_run_id uuid,demo_actor_session_id uuid,simulated_employee_id uuid)
language plpgsql security definer set search_path=pg_catalog,app as $$
declare j app.durable_jobs%rowtype; token uuid; until_at timestamptz;
begin
 if p_limit not between 1 and 32 or p_lease_seconds not between 15 and 900 then
   raise exception using errcode='22023',message='lease_bounds_invalid'; end if;
 perform app.reconcile_expired_durable_jobs();
 perform app.reconcile_unauthorised_durable_jobs();
 for j in select q.* from app.durable_jobs q where q.state in ('queued','retry_scheduled')
   and q.available_at<=clock_timestamp() and q.cancel_requested_at is null
   and app.alto_job_authorized(q.company_id,q.id)
   order by q.priority desc,q.available_at,q.created_at for update skip locked limit p_limit
 loop
   token:=gen_random_uuid(); until_at:=clock_timestamp()+make_interval(secs=>p_lease_seconds);
   update app.durable_jobs q set state='leased',attempt_count=q.attempt_count+1,lease_owner=p_worker_id,lease_token=token,
    leased_at=clock_timestamp(),leased_until=until_at,started_at=coalesce(q.started_at,clock_timestamp()),
    last_error_code=null,last_error_message=null,completed_at=null,row_version=q.row_version+1
    where q.company_id=j.company_id and q.id=j.id returning q.attempt_count into j.attempt_count;
   insert into app.job_attempts(company_id,demo_run_id,job_id,attempt_number,lease_token,worker_id)
     values(j.company_id,j.demo_run_id,j.id,j.attempt_count,token,p_worker_id);
   if j.job_kind='outbox.deliver' then
    update app.outbox_intents o set state='leased',attempt_count=j.attempt_count,lease_owner=p_worker_id,
      lease_token=token,leased_until=until_at,next_attempt_at=null,last_error_code=null,last_error=null
      where o.company_id=j.company_id and o.id=j.aggregate_id and o.state<>'delivered';
   end if;
   return query select j.id,j.company_id,j.job_kind,j.aggregate_id,j.payload,j.requested_by_membership_id,
     m.user_id,m.administrative_role,e.id,j.correlation_id,j.attempt_count,j.max_attempts,token,until_at,
     j.demo_run_id,j.demo_actor_session_id,j.simulated_employee_id
   from (select 1) singleton left join app.company_memberships m on m.company_id=j.company_id and m.id=j.requested_by_membership_id
   left join app.employee_profiles e on e.company_id=m.company_id and e.membership_id=m.id and e.status='active';
 end loop;
end $$;
create or replace function app.enqueue_snapshot_job() returns trigger
language plpgsql security definer set search_path=pg_catalog,app as $$
declare requester uuid;
begin
 select requester_membership_id into requester from app.planning_requests where company_id=new.company_id and id=new.request_id;
 insert into app.durable_jobs(company_id,demo_run_id,job_kind,aggregate_id,payload,requested_by_membership_id,idempotency_key,command_digest,correlation_id,max_attempts)
 values(new.company_id,new.demo_run_id,'plan.propose',new.id,jsonb_build_object('snapshot_id',new.id),requester,
   'plan.propose:'||new.id::text,extensions.digest(convert_to(new.id::text||':'||encode(new.snapshot_digest,'hex'),'UTF8'),'sha256'),gen_random_uuid(),3)
 on conflict(company_id,job_kind,aggregate_id) do nothing;
 return new;
end $$;

create function app.enqueue_alto_job(p_company_id uuid,p_job_kind text,p_aggregate_id uuid,p_payload jsonb,
 p_idempotency_key text,p_command_digest bytea,p_correlation_id uuid) returns uuid
language plpgsql security definer set search_path=pg_catalog,app as $$
declare member_id uuid; job_id uuid; existing_digest bytea;
begin
 if not app.scope_access(p_company_id,app.current_demo_run_id(),true) then
   raise exception using errcode='42501',message='job_access_denied'; end if;
 if not (
   (p_job_kind='assistant.respond' and exists(select 1 from app.assistant_messages m where m.company_id=p_company_id
     and m.id=p_aggregate_id and m.role='user' and app.owns_thread(m.company_id,m.thread_id)))
   or(p_job_kind='preference.suggest' and exists(select 1 from app.employee_feedback_entries f where f.company_id=p_company_id
     and f.id=p_aggregate_id and f.employee_id=app.effective_employee_id(p_company_id,app.current_actor_id())))
   or(p_job_kind='voice.transcribe' and exists(select 1 from app.private_files f where f.company_id=p_company_id
     and f.id=p_aggregate_id and f.purpose='voice_audio' and f.state='available'
     and f.uploader_employee_id=app.effective_employee_id(p_company_id,app.current_actor_id())))
 ) then raise exception using errcode='42501',message='job_target_not_authorized'; end if;
 select id into member_id from app.company_memberships where company_id=p_company_id and user_id=app.current_actor_id() and membership_status='active';
 perform pg_advisory_xact_lock(hashtextextended(p_company_id::text||app.current_scope_id()::text||p_idempotency_key,0));
 select id,command_digest into job_id,existing_digest from app.durable_jobs
   where company_id=p_company_id and scope_id=app.current_scope_id() and job_kind=p_job_kind and idempotency_key=p_idempotency_key;
 if found then
   if existing_digest<>p_command_digest then raise exception using errcode='23505',message='idempotency_key_reused'; end if;
   return job_id;
 end if;
 insert into app.durable_jobs(company_id,demo_run_id,job_kind,aggregate_id,payload,requested_by_membership_id,
   idempotency_key,command_digest,correlation_id,max_attempts)
 values(p_company_id,app.current_demo_run_id(),p_job_kind,p_aggregate_id,p_payload,member_id,p_idempotency_key,p_command_digest,p_correlation_id,3)
 returning id into job_id;
 return job_id;
end $$;

-- Existing lease completion, renew and file-scan writes retain their worker/token checks,
-- with current run/actor authority added before they can mutate business state.
do $leases$ declare v record; d text; begin
 for v in select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='app'
 and p.proname in ('renew_durable_job_lease','complete_durable_job','record_leased_private_file_scan') loop
   d:=replace(pg_get_functiondef(v.oid),chr(13),'');
   d:=replace(d,E'begin\n',E'begin\n  perform app.assert_alto_job_lease(p_company_id,p_job_id,p_lease_token);\n');
   execute d;
 end loop;
end $leases$;
revoke all on function app.bind_job_actor(),app.alto_job_authorized(uuid,uuid),app.assert_alto_job_lease(uuid,uuid,uuid),
 app.fence_alto_ledger_lease(),app.lease_durable_jobs(uuid,integer,integer),app.enqueue_alto_job(uuid,text,uuid,jsonb,text,bytea,uuid) from public;
grant execute on function app.alto_job_authorized(uuid,uuid),app.assert_alto_job_lease(uuid,uuid,uuid),app.lease_durable_jobs(uuid,integer,integer) to coordination_worker;
grant execute on function app.enqueue_alto_job(uuid,text,uuid,jsonb,text,bytea,uuid) to coordination_api;
insert into app_private.migration_contract(version,name) values ('20260927015000','alto_durable_run_fencing');
