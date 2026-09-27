-- Preserve the existing all-or-none cancellation audit contract, including for
-- employee-owned assistant work and operator-owned demo lifecycle commands.
create or replace function app.cancel_alto_assistant(p_company_id uuid,p_thread_id uuid,p_idempotency_key text)
returns void language plpgsql security definer set search_path=pg_catalog,app as $$
declare membership_id uuid; command_hash bytea; previous_hash bytea;
begin
 if not app.owns_thread(p_company_id,p_thread_id) or p_idempotency_key is null
   or length(p_idempotency_key) not between 16 and 128 then
   raise exception using errcode='42501',message='assistant_thread_access_denied'; end if;
 select id into strict membership_id from app.company_memberships
   where company_id=p_company_id and user_id=app.current_actor_id() and membership_status='active';
 command_hash:=extensions.digest(convert_to('assistant.cancel:'||p_thread_id::text,'UTF8'),'sha256');
 perform pg_advisory_xact_lock(hashtextextended(p_company_id::text||':'||app.current_scope_id()::text
   ||':'||app.current_actor_id()::text||':assistant.cancel:'||p_idempotency_key,0));
 select command_digest into previous_hash from app.alto_command_receipts
   where company_id=p_company_id and scope_id=app.current_scope_id() and actor_id=app.current_actor_id()
     and command_key='assistant.cancel' and idempotency_key=p_idempotency_key;
 if found then
   if previous_hash<>command_hash then
     raise exception using errcode='40001',message='cancellation_idempotency_conflict'; end if;
   return;
 end if;
 update app.durable_jobs j set cancel_requested_at=clock_timestamp(),
   cancelled_by_membership_id=membership_id,cancellation_reason='Assistant cancellation requested by thread owner',
   cancellation_idempotency_key=p_idempotency_key,cancellation_command_digest=command_hash,
   state=case when j.state in ('queued','retry_scheduled') then 'cancelled' else j.state end,
   completed_at=case when j.state in ('queued','retry_scheduled') then clock_timestamp() else j.completed_at end,
   last_error_code=case when j.state in ('queued','retry_scheduled') then 'cancelled' else j.last_error_code end,
   row_version=j.row_version+1
 where j.company_id=p_company_id and j.scope_id=app.current_scope_id() and j.job_kind='assistant.respond'
   and j.payload->>'thread_id'=p_thread_id::text and j.state in ('queued','retry_scheduled','leased')
   and j.cancel_requested_at is null;
 insert into app.alto_command_receipts(company_id,actor_id,command_key,idempotency_key,command_digest,result)
   values(p_company_id,app.current_actor_id(),'assistant.cancel',p_idempotency_key,command_hash,
     jsonb_build_object('thread_id',p_thread_id));
end $$;

create or replace function app.archive_demo_run(p_company_id uuid,p_run_id uuid,p_expected_version bigint) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
declare r app.demo_runs%rowtype; prior_run text:=current_setting('app.demo_run_id',true); membership_id uuid;
begin
 select * into r from app.demo_runs where company_id=p_company_id and id=p_run_id for update;
 if not found or p_company_id<>app.current_company_id() then
   raise exception using errcode='42501',message='demo_operator_required'; end if;
 select m.id into membership_id from app.demo_run_memberships rm
   join app.company_memberships m on m.company_id=rm.company_id and m.id=rm.membership_id
   where rm.company_id=p_company_id and rm.run_id=p_run_id and rm.revoked_at is null and rm.run_role in ('owner','operator')
     and m.user_id=app.current_actor_id() and m.membership_status='active';
 if membership_id is null then raise exception using errcode='42501',message='demo_operator_required'; end if;
 if r.state='archived' then return; end if;
 if p_expected_version is null or r.row_version<>p_expected_version then
   raise exception using errcode='40001',message='demo_run_stale'; end if;
 perform set_config('app.demo_run_id',p_run_id::text,true);
 update app.job_attempts a set outcome='cancelled',finished_at=clock_timestamp(),error_code='demo_run_archived'
   from app.durable_jobs j where j.company_id=p_company_id and j.demo_run_id=p_run_id and j.state='leased'
     and a.company_id=j.company_id and a.job_id=j.id and a.lease_token=j.lease_token and a.outcome is null;
 update app.durable_jobs set cancel_requested_at=coalesce(cancel_requested_at,clock_timestamp()),
   cancelled_by_membership_id=coalesce(cancelled_by_membership_id,membership_id),
   cancellation_reason=coalesce(cancellation_reason,'Demo run archived by its owner or operator'),
   cancellation_idempotency_key=coalesce(cancellation_idempotency_key,'archive:'||p_run_id::text),
   cancellation_command_digest=coalesce(cancellation_command_digest,
     extensions.digest(convert_to('archive:'||p_run_id::text,'UTF8'),'sha256')),
   state='cancelled',completed_at=clock_timestamp(),last_error_code='demo_run_archived',
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

insert into app_private.migration_contract(version,name) values ('20260927033000','alto_cancellation_audit_integrity');
