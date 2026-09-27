-- A reserved review is executed once. Its exact decision completes its review node.
create table app.task_review_links(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,subject_task_id uuid not null,review_task_id uuid not null,
 source_plan_id uuid not null,active boolean not null default true,unique(company_id,id),
 unique(company_id,subject_task_id,review_task_id,source_plan_id),
 foreign key(company_id,subject_task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,review_task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,source_plan_id) references app.plans(company_id,id),check(subject_task_id<>review_task_id)
);
create table app.task_gate_uses(
 id uuid primary key default gen_random_uuid(),company_id uuid not null,task_id uuid not null,gate_requirement_id uuid not null,
 resulting_task_version bigint not null,required_submission_id uuid,required_task_event_id uuid,
 consumed_at timestamptz not null default clock_timestamp(),unique(company_id,id),
 unique(company_id,task_id,gate_requirement_id,resulting_task_version),
 foreign key(company_id,task_id) references app.work_items(company_id,task_id),
 foreign key(company_id,gate_requirement_id) references app.task_gate_requirements(company_id,id),
 foreign key(company_id,required_submission_id) references app.submissions(company_id,id),
 foreign key(company_id,required_task_event_id) references app.task_events(company_id,id),
 check(required_submission_id is not null or required_task_event_id is not null)
);
select app_private.install_alto_scope('app.task_review_links');
select app_private.install_alto_scope('app.task_gate_uses');
select app_private.link_alto_scopes();
create policy task_review_link_read on app.task_review_links for select to coordination_api,coordination_worker
 using(app.can_read_task(app.current_actor_id(),company_id,subject_task_id) or app.can_read_task(app.current_actor_id(),company_id,review_task_id));
create policy task_gate_use_read on app.task_gate_uses for select to coordination_api,coordination_worker
 using(app.can_read_task(app.current_actor_id(),company_id,task_id));
grant select on app.task_review_links,app.task_gate_uses to coordination_api,coordination_worker;
create trigger gate_uses_immutable before update or delete on app.task_gate_uses for each row execute function app.alto_immutable_row();
create function app.record_task_gate_evidence() returns trigger
language plpgsql security definer set search_path=pg_catalog,app as $$
declare g record; submission_id uuid; event_id uuid;
begin
 if new.status=old.status or new.status not in ('in_progress','submitted','accepted') then return new; end if;
 for g in select * from app.task_gate_requirements where company_id=new.company_id and task_id=new.task_id loop
   submission_id:=null;event_id:=null;
   select s.id into submission_id from app.submissions s where s.company_id=g.company_id and s.task_id=g.required_task_id
     and (g.required_submission_id is null or s.id=g.required_submission_id)
     and ((g.required_state='submitted' and s.state in ('submitted','accepted'))
       or(g.required_state<>'submitted' and s.state='accepted')) order by s.version desc limit 1;
   if submission_id is null then
     select e.id into event_id from app.task_events e where e.company_id=g.company_id and e.task_id=g.required_task_id
       and e.event_type='accepted' order by e.occurred_at desc,e.id desc limit 1;
   end if;
   if submission_id is null and event_id is null then
     raise exception using errcode='23514',message='exact_gate_evidence_required'; end if;
   insert into app.task_gate_uses(company_id,demo_run_id,task_id,gate_requirement_id,resulting_task_version,required_submission_id,required_task_event_id)
   values(new.company_id,new.demo_run_id,new.task_id,g.id,new.row_version,submission_id,event_id);
 end loop;
 return new;
end $$;
create trigger zz_task_gate_evidence after update of status on app.work_items
 for each row execute function app.record_task_gate_evidence();
create function app.materialize_alto_review_links(p_company_id uuid,p_plan_id uuid) returns void
language plpgsql security definer set search_path=pg_catalog,app as $$
begin
 insert into app.task_review_links(company_id,demo_run_id,subject_task_id,review_task_id,source_plan_id)
 select p_company_id,p.demo_run_id,(c.payload->>'task_id')::uuid,(r.value#>>'{}')::uuid,p_plan_id
 from app.plans p join app.planning_snapshot_constraints sc on sc.company_id=p.company_id and sc.snapshot_id=p.snapshot_id
 join app.validated_constraints c on c.company_id=sc.company_id and c.id=sc.constraint_id
 cross join lateral jsonb_array_elements(coalesce(c.payload->'review_task_ids','[]')) r(value)
 where p.company_id=p_company_id and p.id=p_plan_id and p.author_kind<>'legacy_solver'
   and c.payload->>'family'='task_review_policy'
 on conflict(company_id,subject_task_id,review_task_id,source_plan_id) do nothing;
end $$;
do $links$ declare d text; begin
 d:=replace(pg_get_functiondef('app.commit_approved_plan(uuid,uuid,bytea,bytea,bytea,bigint,bigint,text,text,bytea,uuid)'::regprocedure),chr(13),'');
 d:=replace(d,'perform app.materialize_alto_execution_plan(p_company_id,p_plan_id);',
 'perform app.materialize_alto_execution_plan(p_company_id,p_plan_id); perform app.materialize_alto_review_links(p_company_id,p_plan_id);'); execute d;
 d:=replace(pg_get_functiondef('app.prepare_alto_plan_changes(uuid,uuid)'::regprocedure),chr(13),'');
 d:=replace(d,'update app.work_assignments set active=false','update app.task_review_links set active=false where company_id=p_company_id and subject_task_id=existing.task_id and active;'||E'\n   update app.work_assignments set active=false'); execute d;
 d:=replace(pg_get_functiondef('app.bind_work_item_execution_context()'::regprocedure),chr(13),'');
 d:=replace(d,'where brief.company_id = new.company_id and brief.plan_id = new.source_plan_id',
 'where brief.company_id = new.company_id and brief.plan_id = new.source_plan_id
   and (brief.brief_payload->>''task_id''=new.task_id::text or exists(select 1 from app.plans p
     where p.company_id=new.company_id and p.id=new.source_plan_id and p.author_kind=''legacy_solver'' and not (brief.brief_payload ? ''task_id'')))'); execute d;
end $links$;

create function app.complete_scheduled_review_node() returns trigger
language plpgsql security definer set search_path=pg_catalog,app as $$
declare linked record; member_id uuid; event_id uuid;
begin
 select id into strict member_id from app.company_memberships where company_id=new.company_id and user_id=app.current_actor_id() and membership_status='active';
 for linked in select i.* from app.task_review_links l join app.work_items i on i.company_id=l.company_id and i.task_id=l.review_task_id
 join app.execution_resources er on er.company_id=i.company_id and er.id=i.owner_resource_id
 where l.company_id=new.company_id and l.subject_task_id=new.task_id and l.active and er.employee_id=new.reviewer_employee_id
 for update of i loop
   if linked.task_code='R2' and exists(select 1 from app.demo_runs r where r.company_id=new.company_id and r.id=linked.demo_run_id and r.scenario_key='northstar-launch')
    and nullif(current_setting('app.gate_approval_id',true),'')::uuid is distinct from linked.task_id then
     raise exception using errcode='42501',message='final_gate_confirmation_required'; end if;
   update app.work_items set status=new.decision where company_id=linked.company_id and task_id=linked.task_id;
   insert into app.task_events(company_id,demo_run_id,task_id,actor_membership_id,event_type,from_status,to_status,
    resulting_task_version,event_payload,idempotency_key,command_digest,correlation_id)
   values(new.company_id,new.demo_run_id,linked.task_id,member_id,new.decision,linked.status,new.decision,linked.row_version+1,
    jsonb_build_object('review_id',new.id,'submission_id',new.submission_id,'reserved_review',true),
    'reserved-review:'||new.id::text||':'||linked.task_id::text,new.command_digest,new.correlation_id) returning id into event_id;
   if linked.task_code='R2' and new.decision='accepted' and exists(select 1 from app.demo_runs r
     where r.company_id=new.company_id and r.id=linked.demo_run_id and r.scenario_key='northstar-launch') then
     update app.projects set status='completed',accepted_at=clock_timestamp(),accepted_by_employee_id=new.reviewer_employee_id
       where company_id=new.company_id and id=linked.project_id;
   end if;
 end loop;
 return new;
end $$;
create trigger task_review_complete_reserved_node after insert on app.task_reviews
 for each row execute function app.complete_scheduled_review_node();

create function app.approve_alto_gate(p_company_id uuid,p_task_id uuid,p_expected_version bigint,
 p_required_submission_id uuid,p_required_submission_digest bytea,p_idempotency_key text,p_correlation_id uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog,app as $$
declare t app.work_items%rowtype; s app.submissions%rowtype; member_id uuid; actor_employee uuid; command_digest bytea; prior_status text;
begin
 select * into t from app.work_items where company_id=p_company_id and task_id=p_task_id for update;
 actor_employee:=app.effective_employee_id(p_company_id,app.current_actor_id());
 if not found or not app.scope_access(p_company_id,t.demo_run_id,true) or t.task_code not in ('R1','R2')
  or not exists(select 1 from app.demo_runs r where r.company_id=p_company_id and r.id=t.demo_run_id and r.scenario_key='northstar-launch')
  or not exists(select 1 from app.execution_resources er join app.employee_profiles e on e.company_id=er.company_id and e.id=er.employee_id
    where er.company_id=p_company_id and er.id=t.owner_resource_id and er.employee_id=actor_employee and e.synthetic_key='maya') then
   raise exception using errcode='42501',message='named_gate_approver_required'; end if;
 if t.status='accepted' then return jsonb_build_object('task_id',t.task_id,'status',t.status,'version',t.row_version,'replayed',true); end if;
 if t.row_version<>p_expected_version then raise exception using errcode='40001',message='task_version_stale'; end if;
 select id into strict member_id from app.company_memberships where company_id=p_company_id and user_id=app.current_actor_id() and membership_status='active';
 command_digest:=extensions.digest(convert_to(p_task_id::text||':'||p_expected_version::text||':'||coalesce(p_required_submission_id::text,''),'UTF8'),'sha256');
 if t.task_code='R2' then
   select sub.* into s from app.submissions sub join app.work_items i on i.company_id=sub.company_id and i.task_id=sub.task_id
   where sub.company_id=p_company_id and sub.id=p_required_submission_id and sub.submission_digest=p_required_submission_digest
     and sub.state='submitted' and i.project_id=t.project_id and i.scope_id=t.scope_id and i.task_code='S4' for update of sub;
   if not found then raise exception using errcode='40001',message='final_gate_submission_stale'; end if;
   if not exists(select 1 from app.work_items i where i.company_id=p_company_id and i.project_id=t.project_id and i.scope_id=t.scope_id
     and i.task_code='Q3' and i.status='accepted') then raise exception using errcode='23514',message='task_acceptance_gate_blocked'; end if;
   perform set_config('app.gate_approval_id',t.task_id::text,true);
   perform app.review_task_submission(p_company_id,s.id,s.version,s.submission_digest,'accepted','[]'::jsonb,null,
      p_idempotency_key,command_digest,p_correlation_id);
   perform set_config('app.gate_approval_id','',true);
   select * into t from app.work_items where company_id=p_company_id and task_id=p_task_id;
   if t.status<>'accepted' then raise exception using errcode='23514',message='final_gate_review_binding_missing'; end if;
 else
   if p_required_submission_id is not null or p_required_submission_digest is not null then
     raise exception using errcode='22023',message='readiness_gate_does_not_take_submission'; end if;
   prior_status:=t.status;
   update app.work_items set status='accepted' where company_id=p_company_id and task_id=p_task_id returning * into t;
   insert into app.task_events(company_id,demo_run_id,task_id,actor_membership_id,event_type,from_status,to_status,resulting_task_version,
    event_payload,idempotency_key,command_digest,correlation_id)
   values(p_company_id,t.demo_run_id,t.task_id,member_id,'accepted',prior_status,'accepted',t.row_version,
     jsonb_build_object('readiness_approval',true),p_idempotency_key,command_digest,p_correlation_id);
 end if;
 return jsonb_build_object('task_id',t.task_id,'status',t.status,'version',t.row_version,'replayed',false);
end $$;
-- Accepted work may improve a run's synthetic capability projection, never mutate its shared directory.
do $profiles$ declare d text; begin
 d:=replace(pg_get_functiondef('app.review_task_submission(uuid,uuid,integer,bytea,text,jsonb,text,text,bytea,uuid)'::regprocedure),chr(13),'');
 d:=replace(d,'where company_id = p_company_id and id = v_submission.submitting_employee_id;',
 'where company_id = p_company_id and id = v_submission.submitting_employee_id and profile_kind=''member'';
    update app.planning_resource_profiles set profile_revision=profile_revision+1
    where company_id=p_company_id and scope_id=app.current_scope_id() and resource_id=v_submission.submitting_employee_id;'); execute d;
end $profiles$;
create policy resource_projection_owner_update on app.planning_resource_profiles for update to current_user
 using(app.scope_access(company_id,demo_run_id,true)) with check(app.scope_access(company_id,demo_run_id,true));
revoke all on function app.record_task_gate_evidence(),app.materialize_alto_review_links(uuid,uuid),app.complete_scheduled_review_node(),
 app.approve_alto_gate(uuid,uuid,bigint,uuid,bytea,text,uuid) from public;
grant execute on function app.approve_alto_gate(uuid,uuid,bigint,uuid,bytea,text,uuid) to coordination_api;
insert into app_private.migration_contract(version,name) values ('20260927023000','alto_exact_review_and_goal_gates');
