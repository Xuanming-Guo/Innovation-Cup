-- Permission-bounded request retrieval and untrusted Gemini interpretation ledger.

create table app.projects (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  owning_team_id uuid not null,
  manager_employee_id uuid not null,
  title text not null check (length(btrim(title)) between 1 and 160),
  purpose text not null check (length(btrim(purpose)) between 1 and 2000),
  status text not null default 'active' check (status in ('active', 'paused', 'completed', 'cancelled')),
  requested_deadline timestamptz null,
  agreed_deadline timestamptz null,
  default_priority_key text null check (default_priority_key is null or length(default_priority_key) <= 80),
  visibility_classification text not null default 'internal'
    check (visibility_classification in ('internal', 'confidential', 'restricted')),
  source_brief_id uuid null,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  foreign key (company_id, owning_team_id) references app.teams(company_id, id),
  foreign key (company_id, manager_employee_id)
    references app.employee_profiles(company_id, id),
  foreign key (company_id, source_brief_id) references app.source_records(company_id, id),
  check (agreed_deadline is null or requested_deadline is not null)
);

create table app.planning_requests (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  project_id uuid null,
  requester_membership_id uuid not null,
  original_prompt text not null check (length(btrim(original_prompt)) between 1 and 8000),
  requested_priority_key text null
    check (requested_priority_key is null or length(requested_priority_key) <= 80),
  requested_deadline timestamptz null,
  requested_deadline_timezone text null
    check (requested_deadline_timezone is null or length(requested_deadline_timezone) <= 64),
  status text not null default 'pending_interpretation'
    check (status in (
      'pending_interpretation',
      'interpretation_running',
      'clarification_required',
      'interpreted',
      'failed',
      'cancelled'
    )),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  request_digest bytea not null check (octet_length(request_digest) = 32),
  request_version integer not null default 1 check (request_version > 0),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  row_version bigint not null default 1 check (row_version > 0),
  unique (company_id, id),
  unique (company_id, requester_membership_id, idempotency_key),
  foreign key (company_id, project_id) references app.projects(company_id, id),
  foreign key (company_id, requester_membership_id)
    references app.company_memberships(company_id, id),
  check ((requested_deadline is null) = (requested_deadline_timezone is null))
);

create table app.planning_request_sources (
  company_id uuid not null,
  request_id uuid not null,
  source_id uuid not null,
  source_version_id uuid not null,
  selected_at timestamptz not null default clock_timestamp(),
  primary key (company_id, request_id, source_id),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id) on delete cascade,
  foreign key (company_id, source_id)
    references app.source_records(company_id, id),
  foreign key (company_id, source_version_id)
    references app.source_versions(company_id, id)
);

create table app.source_excerpts (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  source_id uuid not null,
  source_version_id uuid not null,
  locator text not null check (length(locator) between 1 and 240),
  permitted_text text not null check (length(permitted_text) between 1 and 12000),
  text_sha256 bytea not null check (octet_length(text_sha256) = 32),
  extraction_version text not null check (length(extraction_version) between 1 and 120),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, source_version_id, locator),
  foreign key (company_id, source_id)
    references app.source_records(company_id, id) on delete cascade,
  foreign key (company_id, source_version_id)
    references app.source_versions(company_id, id) on delete cascade
);

create table app.retrieval_runs (
  id uuid primary key,
  company_id uuid not null,
  request_id uuid not null,
  actor_membership_id uuid not null,
  purpose text not null check (length(purpose) between 1 and 120),
  allowed_scope jsonb not null check (jsonb_typeof(allowed_scope) = 'object'),
  selected_manifest jsonb not null check (jsonb_typeof(selected_manifest) = 'array'),
  omitted_manifest jsonb not null check (jsonb_typeof(omitted_manifest) = 'array'),
  missing_manifest jsonb not null check (jsonb_typeof(missing_manifest) = 'array'),
  projection_digest bytea not null check (octet_length(projection_digest) = 32),
  projection_characters integer not null check (projection_characters >= 0),
  status text not null check (status in ('complete', 'failed')),
  started_at timestamptz not null,
  completed_at timestamptz not null,
  unique (company_id, id),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, actor_membership_id)
    references app.company_memberships(company_id, id),
  check (completed_at >= started_at)
);

create table app.interpretation_runs (
  id uuid primary key,
  company_id uuid not null,
  request_id uuid not null,
  retrieval_run_id uuid not null,
  model_id text not null check (length(model_id) between 1 and 200),
  model_version text null check (model_version is null or length(model_version) <= 200),
  sdk_version text not null check (length(sdk_version) between 1 and 80),
  prompt_version text not null check (length(prompt_version) between 1 and 80),
  schema_version text not null check (length(schema_version) between 1 and 80),
  safety_profile text not null check (length(safety_profile) between 1 and 120),
  configuration jsonb not null check (jsonb_typeof(configuration) = 'object'),
  status text not null check (status in ('running', 'completed', 'failed')),
  outcome text null check (outcome is null or outcome in (
    'admitted',
    'clarification_required',
    'rejected',
    'refused',
    'timeout',
    'throttled',
    'invalid_output',
    'transient_failure',
    'permanent_failure',
    'budget_exhausted'
  )),
  latency_ms integer null check (latency_ms is null or latency_ms >= 0),
  prompt_tokens integer null check (prompt_tokens is null or prompt_tokens >= 0),
  candidate_tokens integer null check (candidate_tokens is null or candidate_tokens >= 0),
  total_tokens integer null check (total_tokens is null or total_tokens >= 0),
  thought_tokens integer null check (thought_tokens is null or thought_tokens >= 0),
  provider_response_id text null check (provider_response_id is null or length(provider_response_id) <= 240),
  finish_reason text null check (finish_reason is null or length(finish_reason) <= 120),
  error_code text null check (error_code is null or length(error_code) <= 120),
  started_at timestamptz not null,
  completed_at timestamptz null,
  unique (company_id, id),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, retrieval_run_id)
    references app.retrieval_runs(company_id, id),
  check ((status = 'running') = (completed_at is null)),
  check ((status = 'running') = (outcome is null)),
  check ((status = 'failed') = (error_code is not null)),
  check (status <> 'completed' or outcome in ('admitted', 'clarification_required', 'rejected')),
  check (status <> 'failed' or outcome in (
    'refused',
    'timeout',
    'throttled',
    'invalid_output',
    'transient_failure',
    'permanent_failure',
    'budget_exhausted'
  )),
  check (completed_at is null or completed_at >= started_at)
);

create table app.candidate_contracts (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  request_id uuid not null,
  interpretation_run_id uuid not null,
  contract_json jsonb not null check (jsonb_typeof(contract_json) = 'object'),
  contract_digest bytea not null check (octet_length(contract_digest) = 32),
  admission_status text not null
    check (admission_status in ('admitted', 'clarification_required', 'rejected')),
  validation_issues jsonb not null check (jsonb_typeof(validation_issues) = 'array'),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, interpretation_run_id),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, interpretation_run_id)
    references app.interpretation_runs(company_id, id)
);

create table app.clarification_questions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  request_id uuid not null,
  candidate_contract_id uuid not null,
  question_key text not null check (question_key ~ '^[a-z][a-z0-9_-]{0,63}$'),
  category text not null
    check (category in ('missing_data', 'authority', 'timezone', 'ambiguity', 'disclosure')),
  question text not null check (length(question) between 1 and 1000),
  blocks_planning boolean not null,
  related_task_keys jsonb not null check (jsonb_typeof(related_task_keys) = 'array'),
  status text not null default 'open' check (status in ('open', 'answered', 'dismissed')),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, candidate_contract_id, question_key),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, candidate_contract_id)
    references app.candidate_contracts(company_id, id) on delete cascade
);

create table app.trace_steps (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null,
  request_id uuid not null,
  retrieval_run_id uuid null,
  interpretation_run_id uuid null,
  step_type text not null check (step_type in (
    'request_loaded',
    'permission_checked',
    'source_retrieved',
    'projection_frozen',
    'model_called',
    'candidate_validated'
  )),
  input_digest bytea null check (input_digest is null or octet_length(input_digest) = 32),
  output_digest bytea null check (output_digest is null or octet_length(output_digest) = 32),
  tool_version text null check (tool_version is null or length(tool_version) <= 200),
  status text not null check (status in ('complete', 'failed')),
  viewer_safe_projection jsonb not null check (jsonb_typeof(viewer_safe_projection) = 'object'),
  occurred_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id),
  foreign key (company_id, retrieval_run_id)
    references app.retrieval_runs(company_id, id),
  foreign key (company_id, interpretation_run_id)
    references app.interpretation_runs(company_id, id),
  check (retrieval_run_id is not null or interpretation_run_id is not null)
);

create index planning_requests_status_lookup
  on app.planning_requests (company_id, status, created_at);
create index source_excerpts_version_lookup
  on app.source_excerpts (company_id, source_version_id);
create index interpretation_runs_request_lookup
  on app.interpretation_runs (company_id, request_id, started_at desc);
create index clarification_questions_request_lookup
  on app.clarification_questions (company_id, request_id, status);

create or replace function app.can_manage_planning(p_company_id uuid, p_user_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists (
    select 1
    from app.company_memberships
    where company_id = p_company_id
      and user_id = p_user_id
      and membership_status = 'active'
      and administrative_role in ('manager', 'company_admin')
  )
$$;

create or replace function app.can_read_planning_request(
  p_company_id uuid,
  p_user_id uuid,
  p_request_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select app.can_manage_planning(p_company_id, p_user_id)
    and exists (
      select 1
      from app.planning_requests
      where company_id = p_company_id and id = p_request_id
    )
$$;

revoke execute on function app.can_manage_planning(uuid, uuid) from public;
revoke execute on function app.can_read_planning_request(uuid, uuid, uuid) from public;
grant execute on function app.can_manage_planning(uuid, uuid)
  to coordination_api, coordination_worker;
grant execute on function app.can_read_planning_request(uuid, uuid, uuid)
  to coordination_api, coordination_worker;

alter table app.projects enable row level security;
alter table app.planning_requests enable row level security;
alter table app.planning_request_sources enable row level security;
alter table app.source_excerpts enable row level security;
alter table app.retrieval_runs enable row level security;
alter table app.interpretation_runs enable row level security;
alter table app.candidate_contracts enable row level security;
alter table app.clarification_questions enable row level security;
alter table app.trace_steps enable row level security;

create policy projects_manager_select on app.projects
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_manage_planning(company_id, app.current_actor_id())
  );

create policy planning_requests_manager_select on app.planning_requests
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), id)
  );

create policy planning_requests_manager_insert on app.planning_requests
  for insert to coordination_api
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_manage_planning(company_id, app.current_actor_id())
    and exists (
      select 1
      from app.company_memberships as membership
      where membership.company_id = planning_requests.company_id
        and membership.id = planning_requests.requester_membership_id
        and membership.user_id = app.current_actor_id()
        and membership.membership_status = 'active'
    )
  );

create policy planning_requests_worker_update on app.planning_requests
  for update to coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), id)
  )
  with check (
    company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), id)
  );

create policy planning_request_sources_manager_select on app.planning_request_sources
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy planning_request_sources_manager_insert on app.planning_request_sources
  for insert to coordination_api
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
    and app.can_read_source(app.current_actor_id(), company_id, source_id)
  );

create policy source_excerpts_authorized_select on app.source_excerpts
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_source(app.current_actor_id(), company_id, source_id)
  );

create policy source_excerpts_worker_insert on app.source_excerpts
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_source(app.current_actor_id(), company_id, source_id)
  );

create policy retrieval_runs_manager_select on app.retrieval_runs
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy retrieval_runs_worker_insert on app.retrieval_runs
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy interpretation_runs_manager_select on app.interpretation_runs
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy interpretation_runs_worker_insert on app.interpretation_runs
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy interpretation_runs_worker_update on app.interpretation_runs
  for update to coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  )
  with check (
    company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy candidate_contracts_manager_select on app.candidate_contracts
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy candidate_contracts_worker_insert on app.candidate_contracts
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy clarification_questions_manager_select on app.clarification_questions
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy clarification_questions_worker_insert on app.clarification_questions
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy trace_steps_manager_select on app.trace_steps
  for select to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy trace_steps_worker_insert on app.trace_steps
  for insert to coordination_worker
  with check (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

grant select on app.projects to coordination_api, coordination_worker;
grant select, insert on app.planning_requests to coordination_api;
grant select, update on app.planning_requests to coordination_worker;
grant select, insert on app.planning_request_sources to coordination_api;
grant select on app.planning_request_sources to coordination_worker;
grant select on app.source_excerpts to coordination_api;
grant select, insert on app.source_excerpts to coordination_worker;
grant select on app.retrieval_runs, app.interpretation_runs, app.candidate_contracts,
  app.clarification_questions, app.trace_steps to coordination_api;
grant select, insert on app.retrieval_runs, app.candidate_contracts,
  app.clarification_questions, app.trace_steps to coordination_worker;
grant select, insert, update on app.interpretation_runs to coordination_worker;

create trigger projects_touch_updated before update on app.projects
  for each row execute function app.touch_updated_row();
create trigger planning_requests_touch_updated before update on app.planning_requests
  for each row execute function app.touch_updated_row();

insert into app_private.migration_contract (version, name)
values ('20260926014000', 'interpretation_pipeline');
