-- DB02: fail-closed run scoping on every existing mutable domain descendant.
-- Historical rows retain NULL run / company scope. No historical digest is rewritten.
create function app_private.install_alto_scope(p_table regclass) returns void
language plpgsql set search_path=pg_catalog,app as $$
declare v_name text := p_table::text; v_constraint record; v_columns text;
begin
  execute format('alter table %s add column demo_run_id uuid, add column scope_id uuid generated always as (coalesce(demo_run_id,company_id)) stored',p_table);
  execute format('alter table %s add constraint %I foreign key(company_id,demo_run_id) references app.demo_runs(company_id,id)',p_table,'alto_run_'||md5(v_name));
  -- Add scoped identity keys for every existing unique key, without removing legacy keys.
  for v_constraint in select c.oid,c.conkey from pg_constraint c where c.conrelid=p_table and c.contype in ('p','u') loop
    select string_agg(quote_ident(a.attname),',' order by k.ord) into v_columns
      from unnest(v_constraint.conkey) with ordinality k(num,ord)
      join pg_attribute a on a.attrelid=p_table and a.attnum=k.num;
    execute format('create unique index %I on %s(scope_id,%s)', 'alto_key_'||md5(v_name||v_columns),p_table,v_columns);
  end loop;
  execute format('alter table %s enable row level security',p_table);
  execute format('create policy alto_scope_boundary on %s as restrictive for all to coordination_api,coordination_worker using(app.scope_access(company_id,demo_run_id,false)) with check(app.scope_access(company_id,demo_run_id,true))',p_table);
  execute format('create trigger aaa_alto_scope_fence before insert or update or delete on %s for each row execute function app.fence_scope_write()',p_table);
end $$;

create function app.fence_scope_write() returns trigger
language plpgsql security definer set search_path=pg_catalog,app as $$
declare v_row jsonb; v_run uuid; v_company uuid; v_runtime text := current_setting('role',true);
begin
  v_row := case when tg_op='DELETE' then to_jsonb(old) else to_jsonb(new) end;
  v_company := (v_row->>'company_id')::uuid;
  v_run := (v_row->>'demo_run_id')::uuid;
  if tg_op='INSERT' and v_run is null and app.current_demo_run_id() is not null then
    new.demo_run_id := app.current_demo_run_id(); v_run := new.demo_run_id;
  end if;
  if tg_op='UPDATE' and (new.company_id<>old.company_id or new.demo_run_id is distinct from old.demo_run_id) then
    raise exception using errcode='23514',message='scope_is_immutable';
  end if;
  -- Queue leasing is a narrow worker-only definer operation; business writes still require full context.
  if v_runtime='coordination_worker' and tg_table_name in ('durable_jobs','job_attempts','outbox_intents')
     and app.current_company_id() is null then
    if v_run is not null and not exists(select 1 from app.demo_runs where company_id=v_company and id=v_run and state='active') then
      raise exception using errcode='40001',message='demo_run_archived'; end if;
  elsif v_runtime in ('coordination_api','coordination_worker','authenticated') then
    if not app.scope_access(v_company,v_run,true) then
      raise exception using errcode='42501',message='scope_access_denied'; end if;
  end if;
  if tg_op='DELETE' then return old; end if;
  return new;
end $$;

do $scope$ declare v_table text; begin
  foreach v_table in array array[
    'source_records','source_versions','source_access_grants','private_files',
    'projects','planning_requests','planning_request_sources','source_excerpts','retrieval_runs',
    'interpretation_runs','candidate_contracts','clarification_questions','trace_steps',
    'validated_constraints','constraint_source_evidence','planning_snapshots','planning_snapshot_constraints',
    'solver_runs','plans','plan_task_placements','plan_schedule_blocks','plan_changes','employee_brief_versions',
    'plan_approval_requirements','plan_approval_decisions','plan_commitments','plan_approval_uses',
    'work_items','work_assignments','committed_schedule_blocks','outbox_intents','audit_events',
    'task_review_policies','task_access_grants','employee_brief_audience_grants','task_events','task_corrections',
    'submissions','submission_files','task_reviews','employee_workload_state','familiarity_evidence','effort_observations',
    'durable_jobs','job_attempts','notifications','planning_resource_profiles','durable_job_recoveries',
    'clarification_answer_submissions','clarification_responses'
  ] loop perform app_private.install_alto_scope(('app.'||v_table)::regclass); end loop;
end $scope$;

-- Same-company UUIDs alone cannot enforce same-run parentage. Add scope to every
-- existing FK whose two endpoints are scoped. Original FKs stay for legacy callers.
create function app_private.link_alto_scopes() returns void
language plpgsql set search_path=pg_catalog,app as $$
declare v_fk record; v_from text; v_to text; v_name text;
begin
  for v_fk in select c.* from pg_constraint c
    join pg_namespace n on n.oid=c.connamespace and n.nspname='app'
    where c.contype='f' and c.conname not like 'alto_parent_%'
      and exists(select 1 from pg_attribute a where a.attrelid=c.conrelid and a.attname='scope_id' and not a.attisdropped)
      and exists(select 1 from pg_attribute a where a.attrelid=c.confrelid and a.attname='scope_id' and not a.attisdropped)
      and not exists(select 1 from pg_attribute a where a.attrelid=c.conrelid and a.attname='scope_id' and a.attnum=any(c.conkey))
  loop
    v_name := 'alto_parent_'||md5(v_fk.conrelid::text||v_fk.conname);
    if exists(select 1 from pg_constraint where conrelid=v_fk.conrelid and conname=v_name) then continue; end if;
    select string_agg(quote_ident(a.attname),',' order by k.ord) into v_from
      from unnest(v_fk.conkey) with ordinality k(num,ord) join pg_attribute a on a.attrelid=v_fk.conrelid and a.attnum=k.num;
    select string_agg(quote_ident(a.attname),',' order by k.ord) into v_to
      from unnest(v_fk.confkey) with ordinality k(num,ord) join pg_attribute a on a.attrelid=v_fk.confrelid and a.attnum=k.num;
    execute format('alter table %s add constraint %I foreign key(scope_id,%s) references %s(scope_id,%s) deferrable initially deferred',
      v_fk.conrelid::regclass,v_name,v_from,v_fk.confrelid::regclass,v_to);
  end loop;
end $$;
select app_private.link_alto_scopes();

-- Resource identity is company-wide; mutable workload and capacity are run-specific.
alter table app.employee_workload_state drop constraint employee_workload_state_pkey;
alter table app.employee_workload_state add primary key(company_id,scope_id,employee_id);
alter table app.planning_resource_profiles drop constraint planning_resource_profiles_pkey;
alter table app.planning_resource_profiles add primary key(company_id,scope_id,resource_id);
drop index app.outbox_logical_idempotency;
create unique index outbox_logical_idempotency on app.outbox_intents(company_id,scope_id,idempotency_key);
-- Replace command-key constraints; UUID identity constraints remain compatible.
do $keys$ declare v record; v_cols text; begin
  for v in select c.* from pg_constraint c join pg_namespace n on n.oid=c.connamespace and n.nspname='app'
    where c.contype='u' and exists(select 1 from pg_attribute a where a.attrelid=c.conrelid and a.attname='scope_id')
      and exists(select 1 from pg_attribute a where a.attrelid=c.conrelid and a.attnum=any(c.conkey) and a.attname='idempotency_key')
  loop
    select string_agg(quote_ident(a.attname),',' order by k.ord) into v_cols
      from unnest(v.conkey) with ordinality k(num,ord) join pg_attribute a on a.attrelid=v.conrelid and a.attnum=k.num;
    execute format('alter table %s drop constraint %I',v.conrelid::regclass,v.conname);
    execute format('alter table %s add constraint %I unique(scope_id,%s)',v.conrelid::regclass,v.conname,v_cols);
  end loop;
end $keys$;
-- Use the catalog identity rather than assuming PostgreSQL's generated exclusion name.
do $capacity$ declare v_name text; begin
  select conname into strict v_name from pg_constraint where conrelid='app.committed_schedule_blocks'::regclass and contype='x';
  execute format('alter table app.committed_schedule_blocks drop constraint %I',v_name);
end $capacity$;
alter table app.committed_schedule_blocks add constraint committed_scope_no_overlap
  exclude using gist(company_id with =,scope_id with =,resource_id with =,time_range with &&) where(active and exclusive);

create or replace function app.refresh_employee_workload(p_company_id uuid,p_employee_id uuid)
returns void language plpgsql security definer set search_path=pg_catalog,app as $$
begin
  insert into app.employee_workload_state(company_id,demo_run_id,employee_id,assigned_count,in_progress_count,blocked_count,submitted_count,last_event_at)
  select p_company_id,app.current_demo_run_id(),p_employee_id,
    count(distinct i.task_id) filter(where i.status in ('assigned','acknowledged')),
    count(distinct i.task_id) filter(where i.status='in_progress'),
    count(distinct i.task_id) filter(where i.status='blocked'),
    count(distinct i.task_id) filter(where i.status='submitted'),max(e.occurred_at)
  from app.execution_resources r
  left join app.work_assignments a on a.company_id=r.company_id and a.resource_id=r.id and a.active
    and a.assignment_role='owner' and a.scope_id=app.current_scope_id()
  left join app.work_items i on i.company_id=a.company_id and i.task_id=a.task_id and i.scope_id=a.scope_id
  left join app.task_events e on e.company_id=i.company_id and e.task_id=i.task_id and e.scope_id=i.scope_id
  where r.company_id=p_company_id and r.employee_id=p_employee_id
  group by r.company_id,r.employee_id
  on conflict(company_id,scope_id,employee_id) do update set assigned_count=excluded.assigned_count,
    in_progress_count=excluded.in_progress_count,blocked_count=excluded.blocked_count,submitted_count=excluded.submitted_count,
    last_event_at=excluded.last_event_at,updated_at=clock_timestamp(),row_version=app.employee_workload_state.row_version+1;
end $$;

create function app.resolve_demo_context(p_company_id uuid,p_run_id uuid,p_session_id uuid)
returns jsonb language plpgsql stable security definer set search_path=pg_catalog,app as $$
declare v_employee uuid; v_role text;
begin
  if p_company_id<>app.current_company_id() or p_run_id is distinct from app.current_demo_run_id()
    or not app.can_access_demo_run(p_company_id,p_run_id,app.current_actor_id()) then
    raise exception using errcode='42501',message='demo_context_access_denied'; end if;
  if p_session_id is not null then
    if p_session_id is distinct from nullif(current_setting('app.demo_actor_session_id',true),'')::uuid then
      raise exception using errcode='42501',message='demo_actor_access_denied'; end if;
    v_employee:=app.authorised_demo_actor(p_company_id,p_run_id,app.current_actor_id());
    if v_employee is null then raise exception using errcode='42501',message='demo_actor_access_denied'; end if;
    select case when synthetic_key in ('maya','jordan') then 'manager' else 'member' end into v_role
      from app.employee_profiles where company_id=p_company_id and id=v_employee;
  else
    select administrative_role into v_role from app.company_memberships
      where company_id=p_company_id and user_id=app.current_actor_id() and membership_status='active';
  end if;
  return jsonb_build_object('employee_id',v_employee,'simulated_employee_id',v_employee,'effective_role',v_role,'demo_run_id',p_run_id);
end $$;
revoke all on function app.fence_scope_write(),app_private.install_alto_scope(regclass),app_private.link_alto_scopes(),
  app.resolve_demo_context(uuid,uuid,uuid) from public;
grant execute on function app.resolve_demo_context(uuid,uuid,uuid) to coordination_api,coordination_worker;

insert into app_private.migration_contract(version,name) values ('20260927011000','alto_run_scope_integrity');
