-- Preserve ordinary commit/outbox behavior after the idempotency key gains scope_id.
do $compatibility$
declare signature text; definition text; old_target text; new_target text;
begin
 foreach signature in array array[
   'app.enqueue_committed_assignment_notification()',
   'app.enqueue_publishable_employee_brief(uuid,uuid,uuid)',
   'app.deliver_internal_outbox_intent(uuid,uuid,uuid,uuid)'
 ] loop
   definition:=pg_get_functiondef(signature::regprocedure);
   old_target:=case when signature like '%deliver_internal_outbox_intent%'
     then 'on conflict (company_id, recipient_membership_id, idempotency_key)'
     else 'on conflict (company_id, idempotency_key)' end;
   new_target:=case when signature like '%deliver_internal_outbox_intent%'
     then 'on conflict (company_id, scope_id, recipient_membership_id, idempotency_key)'
     else 'on conflict (company_id, scope_id, idempotency_key)' end;
   if position(old_target in definition)=0 then
     raise exception using errcode='55000',message='legacy_outbox_conflict_contract_changed'; end if;
   execute replace(definition,old_target,new_target);
 end loop;
end $compatibility$;
-- An ordinary manager still needs a task grant; a replaced reviewer retains the exact
-- already-submitted version they were appointed to review, not future submissions.
create or replace function app.can_read_task(p_user_id uuid,p_company_id uuid,p_task_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.work_items i where i.company_id=p_company_id and i.task_id=p_task_id
 and app.scope_access(i.company_id,i.demo_run_id,false) and (
   (i.demo_run_id is not null and app.can_manage_planning(p_company_id,p_user_id))
   or exists(select 1 from app.work_assignments a join app.execution_resources r on r.company_id=a.company_id and r.id=a.resource_id
     where a.company_id=i.company_id and a.scope_id=i.scope_id and a.task_id=i.task_id and a.active and r.status='active'
       and r.employee_id=app.effective_employee_id(p_company_id,p_user_id))
   or exists(select 1 from app.task_access_grants g where g.company_id=i.company_id and g.scope_id=i.scope_id and g.task_id=i.task_id and g.active
     and g.employee_id=app.effective_employee_id(p_company_id,p_user_id))
   or exists(select 1 from app.task_review_policies p where p.company_id=i.company_id and p.scope_id=i.scope_id and p.task_id=i.task_id and p.active
     and p.reviewer_employee_id=app.effective_employee_id(p_company_id,p_user_id))
   or exists(select 1 from app.submissions s join app.task_review_policies p on p.company_id=s.company_id and p.scope_id=s.scope_id and p.id=s.review_policy_id
     where s.company_id=i.company_id and s.scope_id=i.scope_id and s.task_id=i.task_id and s.state='submitted'
       and p.reviewer_employee_id=app.effective_employee_id(p_company_id,p_user_id))))
$$;
create or replace function app.can_manage_task(p_user_id uuid,p_company_id uuid,p_task_id uuid)
returns boolean language sql stable security definer set search_path=pg_catalog,app as $$
 select exists(select 1 from app.work_items i where i.company_id=p_company_id and i.task_id=p_task_id
   and app.scope_access(i.company_id,i.demo_run_id,true) and (
     (i.demo_run_id is not null and app.can_manage_planning(p_company_id,p_user_id))
     or exists(select 1 from app.task_access_grants g where g.company_id=i.company_id and g.scope_id=i.scope_id and g.task_id=i.task_id
       and g.active and g.access_role='manager' and g.employee_id=app.effective_employee_id(p_company_id,p_user_id))))
$$;
-- Operator-owned ordinary seed writes may have no request GUC; their explicit company
-- argument still identifies ordinary scope. Runtime writes remain fenced by their row scope.
do $workload$ declare definition text; begin
 definition:=pg_get_functiondef('app.refresh_employee_workload(uuid,uuid)'::regprocedure);
 execute replace(definition,'app.current_scope_id()','coalesce(app.current_demo_run_id(),p_company_id)');
end $workload$;
-- Renewal retains its boolean lost-lease contract; mutation paths still raise on a stale fence.
do $renew$ declare definition text; begin
 definition:=pg_get_functiondef('app.renew_durable_job_lease(uuid,uuid,uuid,uuid,integer)'::regprocedure);
 execute replace(definition,
   'perform app.assert_alto_job_lease(p_company_id,p_job_id,p_lease_token);',
   'begin perform app.assert_alto_job_lease(p_company_id,p_job_id,p_lease_token);
    exception when serialization_failure then return false; end;');
end $renew$;
do $completion$ declare definition text; begin
 definition:=replace(pg_get_functiondef('app.complete_durable_job(uuid,uuid,uuid,uuid,jsonb,bytea,jsonb)'::regprocedure),chr(13),'');
 definition:=replace(definition,'  perform app.assert_alto_job_lease(p_company_id,p_job_id,p_lease_token);','');
 definition:=replace(definition,'  if v_job.state = ''succeeded'' then',
 '  if v_job.state = ''succeeded'' then
    if not app.alto_job_authorized(p_company_id,p_job_id) or not exists(
      select 1 from app.job_attempts a where a.company_id=p_company_id and a.job_id=p_job_id
        and a.lease_token=p_lease_token and a.worker_id=p_worker_id and a.outcome=''succeeded'') then
      raise exception using errcode=''40001'',message=''job_lease_invalid''; end if;');
 definition:=replace(definition,'  if v_job.state <> ''leased'' or v_job.lease_owner',
 '  perform app.assert_alto_job_lease(p_company_id,p_job_id,p_lease_token);
  if v_job.state <> ''leased'' or v_job.lease_owner');
 execute definition;
end $completion$;
-- Only run-scoped ALTO snapshots enter the new proposal workflow. Ordinary company
-- snapshots retain their existing compatible planner and immutable history.
do $routing$ declare definition text; begin
 definition:=pg_get_functiondef('app.enqueue_snapshot_job()'::regprocedure);
 definition:=replace(definition,'''plan.propose'',new.id',
   'case when new.demo_run_id is null then ''planning.run'' else ''plan.propose'' end,new.id');
 definition:=replace(definition,'''plan.propose:''||new.id::text',
   '(case when new.demo_run_id is null then ''planning.run:'' else ''plan.propose:'' end)||new.id::text');
 execute definition;
end $routing$;
insert into app_private.migration_contract(version,name) values ('20260927031000','alto_legacy_outbox_scope_conflicts');
