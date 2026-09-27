-- Consent events carry IDs only; wording is resolved through current audience permissions.
alter table app.outbox_intents drop constraint outbox_intents_intent_kind_check;
alter table app.outbox_intents add constraint outbox_intents_intent_kind_check check(intent_kind in (
 'plan.committed','employee_brief.publish','task.changed','approval.changed','preference.shared'));
alter table app.notifications drop constraint notifications_message_key_check;
alter table app.notifications add constraint notifications_message_key_check check(message_key in (
 'plan_state_changed','approval_state_changed','employee_brief_changed','task_state_changed','employee_preference_shared'));
alter table app.notifications drop constraint notifications_subject_type_check;
alter table app.notifications add constraint notifications_subject_type_check check(subject_type in ('plan','employee_brief','task','employee_preference')),
 add column recipient_employee_id uuid,add foreign key(company_id,recipient_employee_id) references app.employee_profiles(company_id,id);
create function app.emit_preference_consent_event() returns trigger language plpgsql security definer set search_path=pg_catalog,app as $$
declare audience_user uuid;
begin
 if tg_op='INSERT' and new.decision='share' and new.revoked_at is null then
   insert into app.outbox_intents(company_id,demo_run_id,intent_kind,aggregate_type,aggregate_id,payload,correlation_id)
   values(new.company_id,new.demo_run_id,'preference.shared','employee_preference',new.preference_version_id,
     jsonb_build_object('share_decision_id',new.id,'preference_version_id',new.preference_version_id),gen_random_uuid());
 end if;
 if tg_op='UPDATE' and old.revoked_at is null and new.revoked_at is not null then
   select user_id into audience_user from app.company_memberships where company_id=new.company_id and id=new.audience_membership_id;
   if audience_user is not null and to_regprocedure('realtime.send(jsonb,text,text,boolean)') is not null then
     execute 'select realtime.send($1,$2,$3,$4)' using app.private_refresh_payload(),'refresh','user:'||audience_user::text,true;
   end if;
 end if;
 return new;
end $$;
create trigger preference_consent_outbox after insert or update of revoked_at on app.employee_preference_share_decisions
 for each row execute function app.emit_preference_consent_event();
create function app.deliver_preference_outbox(p_company_id uuid,p_intent_id uuid,p_job_id uuid,p_lease_token uuid)
returns table(notification_count integer,replayed boolean) language plpgsql security definer set search_path=pg_catalog,app as $$
declare intent app.outbox_intents%rowtype; share app.employee_preference_share_decisions%rowtype;
begin
 perform app.restore_alto_job_context(p_company_id,p_job_id,p_lease_token);
 select * into strict intent from app.outbox_intents where company_id=p_company_id and id=p_intent_id and intent_kind='preference.shared' for update;
 if intent.state='delivered' then return query select coalesce((intent.delivery_result->>'notification_count')::integer,0),true; return; end if;
 select d.* into share from app.employee_preference_share_decisions d join app.company_memberships m
   on m.company_id=d.company_id and m.id=d.audience_membership_id and m.membership_status='active'
 where d.company_id=p_company_id and d.id=(intent.payload->>'share_decision_id')::uuid and d.decision='share' and d.revoked_at is null
  and (d.demo_run_id is null or app.can_access_demo_run(p_company_id,d.demo_run_id,m.user_id));
 notification_count:=0;
 if found then
   insert into app.notifications(company_id,demo_run_id,recipient_membership_id,recipient_employee_id,origin_outbox_intent_id,
     idempotency_key,message_key,subject_type,subject_id)
   values(p_company_id,intent.demo_run_id,share.audience_membership_id,share.audience_employee_id,intent.id,
     'preference-shared:'||share.id::text,'employee_preference_shared','employee_preference',share.preference_version_id)
   on conflict do nothing;
   get diagnostics notification_count=row_count;
 end if;
 update app.outbox_intents set state='delivered',processed_at=clock_timestamp(),lease_owner=null,lease_token=null,leased_until=null,
   delivery_result=jsonb_build_object('notification_count',notification_count)
   where company_id=p_company_id and id=p_intent_id;
 replayed:=false;return next;
end $$;
do $delivery$ declare d text; begin
 d:=replace(pg_get_functiondef('app.deliver_internal_outbox_intent(uuid,uuid,uuid,uuid)'::regprocedure),chr(13),'');
 d:=replace(d,'  if v_intent.state = ''delivered'' then',
 '  if v_intent.intent_kind=''preference.shared'' then
    return query select * from app.deliver_preference_outbox(p_company_id,p_intent_id,p_job_id,p_lease_token); return;
  end if;
  if v_intent.state = ''delivered'' then');execute d;
end $delivery$;
create or replace function app.can_read_notification(p_company_id uuid,p_user_id uuid,p_notification_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.notifications n join app.company_memberships m
   on m.company_id=n.company_id and m.id=n.recipient_membership_id and m.user_id=p_user_id and m.membership_status='active'
 where n.company_id=p_company_id and n.id=p_notification_id and app.scope_access(n.company_id,n.demo_run_id,false)
   and (n.recipient_employee_id is null or n.recipient_employee_id=app.effective_employee_id(p_company_id,p_user_id))
   and ((n.subject_type='task' and app.can_read_task(p_user_id,p_company_id,n.subject_id))
     or(n.subject_type='plan' and app.can_read_plan(p_company_id,p_user_id,n.subject_id))
     or(n.subject_type='employee_brief' and app.can_read_employee_brief(p_user_id,p_company_id,n.subject_id))
     or(n.subject_type='employee_preference' and app.can_read_preference(p_company_id,n.subject_id))))
$$;

create or replace function app.reconcile_unauthorised_durable_jobs() returns integer
language plpgsql security definer set search_path=pg_catalog,app as $$
declare changed integer;
begin
 with invalid as(select j.company_id,j.id from app.durable_jobs j
   left join app.company_memberships m on m.company_id=j.company_id and m.id=j.requested_by_membership_id
   where j.state in ('queued','retry_scheduled') and (
     not app.alto_job_authorized(j.company_id,j.id)
     or(j.demo_run_id is null and j.job_kind in ('interpretation.run','planning.materialize','planning.run','plan.propose')
       and (m.id is null or m.membership_status<>'active' or m.administrative_role not in ('manager','company_admin'))))
   for update of j skip locked)
 update app.durable_jobs j set state='review_required',last_error_code='requester_authority_revoked',last_error_message=null,
   completed_at=clock_timestamp(),row_version=j.row_version+1 from invalid i where j.company_id=i.company_id and j.id=i.id;
 get diagnostics changed=row_count;return changed;
end $$;
-- Terminal reconciliation is allowed to record why an archived job cannot execute;
-- only new business writes and nonterminal lease transitions require an active run.
do $fence$ declare d text; begin
 d:=replace(pg_get_functiondef('app.fence_scope_write()'::regprocedure),chr(13),'');
 d:=replace(d,'if v_run is not null and not exists(select 1 from app.demo_runs where company_id=v_company and id=v_run and state=''active'') then',
 'if v_run is not null and not exists(select 1 from app.demo_runs where company_id=v_company and id=v_run and state=''active'')
     and not(tg_op=''UPDATE'' and ((tg_table_name=''durable_jobs'' and v_row->>''state'' in (''review_required'',''cancelled'',''dead_letter''))
       or(tg_table_name=''outbox_intents'' and v_row->>''state'' in (''review_required'',''cancelled'',''dead_letter''))
       or tg_table_name=''job_attempts'')) then');execute d;
end $fence$;
create function app.join_demo_run(p_company_id uuid,p_run_id uuid,p_membership_id uuid,p_role text) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 if p_role not in ('participant','viewer') or p_company_id<>app.current_company_id()
  or not exists(select 1 from app.demo_runs r join app.company_memberships m on m.company_id=r.company_id and m.id=r.owner_membership_id
    where r.company_id=p_company_id and r.id=p_run_id and r.state='active' and m.user_id=app.current_actor_id() and m.membership_status='active')
  or not exists(select 1 from app.company_memberships m where m.company_id=p_company_id and m.id=p_membership_id and m.membership_status='active') then
   raise exception using errcode='42501',message='demo_join_authority_required'; end if;
 insert into app.demo_run_memberships(company_id,run_id,membership_id,run_role)
   values(p_company_id,p_run_id,p_membership_id,p_role)
 on conflict(company_id,run_id,membership_id) do nothing;
end $$;
revoke all on function app.emit_preference_consent_event(),app.deliver_preference_outbox(uuid,uuid,uuid,uuid),app.join_demo_run(uuid,uuid,uuid,text) from public;
grant execute on function app.join_demo_run(uuid,uuid,uuid,text) to coordination_api;
insert into app_private.migration_contract(version,name) values ('20260927025000','alto_consent_notifications_and_reconciliation');
