-- Immutable manager clarification answers and derived-request resume.

alter table app.planning_requests
  add column clarification_parent_request_id uuid null,
  add column clarification_parent_request_version integer null,
  add column clarification_parent_candidate_id uuid null,
  add constraint planning_requests_clarification_parent_request_fk
    foreign key (company_id, clarification_parent_request_id)
    references app.planning_requests(company_id, id),
  add constraint planning_requests_clarification_parent_candidate_fk
    foreign key (company_id, clarification_parent_candidate_id)
    references app.candidate_contracts(company_id, id) on delete cascade,
  add constraint planning_requests_clarification_parent_complete check (
    (clarification_parent_request_id is null
      and clarification_parent_request_version is null
      and clarification_parent_candidate_id is null)
    or
    (clarification_parent_request_id is not null
      and clarification_parent_request_version is not null
      and clarification_parent_request_version > 0
      and clarification_parent_candidate_id is not null)
  );

alter table app.planning_requests
  drop constraint planning_requests_status_check,
  add constraint planning_requests_status_check check (status in (
    'pending_interpretation',
    'interpretation_running',
    'clarification_required',
    'clarification_answered',
    'interpreted',
    'failed',
    'cancelled'
  ));

create table app.clarification_answer_submissions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  request_id uuid not null,
  request_version integer not null check (request_version > 0),
  candidate_contract_id uuid not null,
  derived_request_id uuid not null,
  actor_membership_id uuid not null,
  authority_role text not null check (authority_role in ('manager', 'company_admin')),
  idempotency_key text not null check (length(idempotency_key) between 16 and 128),
  command_digest bytea not null check (octet_length(command_digest) = 32),
  correlation_id uuid not null,
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, actor_membership_id, idempotency_key),
  unique (company_id, request_id, request_version, candidate_contract_id),
  unique (company_id, derived_request_id),
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id) on delete cascade,
  foreign key (company_id, candidate_contract_id)
    references app.candidate_contracts(company_id, id) on delete cascade,
  foreign key (company_id, derived_request_id)
    references app.planning_requests(company_id, id) on delete cascade,
  foreign key (company_id, actor_membership_id)
    references app.company_memberships(company_id, id)
);

create table app.clarification_responses (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references app.companies(id) on delete cascade,
  submission_id uuid not null,
  request_id uuid not null,
  request_version integer not null check (request_version > 0),
  candidate_contract_id uuid not null,
  clarification_question_id uuid not null,
  actor_membership_id uuid not null,
  answer text not null check (length(btrim(answer)) between 1 and 4000),
  answer_digest bytea not null check (octet_length(answer_digest) = 32),
  created_at timestamptz not null default clock_timestamp(),
  unique (company_id, id),
  unique (company_id, clarification_question_id),
  foreign key (company_id, submission_id)
    references app.clarification_answer_submissions(company_id, id) on delete cascade,
  foreign key (company_id, request_id)
    references app.planning_requests(company_id, id) on delete cascade,
  foreign key (company_id, candidate_contract_id)
    references app.candidate_contracts(company_id, id) on delete cascade,
  foreign key (company_id, clarification_question_id)
    references app.clarification_questions(company_id, id) on delete cascade,
  foreign key (company_id, actor_membership_id)
    references app.company_memberships(company_id, id)
);

create index clarification_submissions_request_lookup
  on app.clarification_answer_submissions (company_id, request_id, created_at);
create index clarification_responses_derived_lookup
  on app.clarification_answer_submissions (company_id, derived_request_id);

alter table app.clarification_answer_submissions enable row level security;
alter table app.clarification_answer_submissions force row level security;
alter table app.clarification_responses enable row level security;
alter table app.clarification_responses force row level security;

create policy clarification_answer_submissions_select
  on app.clarification_answer_submissions for select
  to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

create policy clarification_responses_select
  on app.clarification_responses for select
  to coordination_api, coordination_worker
  using (
    app.request_context_present()
    and company_id = app.current_company_id()
    and app.can_read_planning_request(company_id, app.current_actor_id(), request_id)
  );

revoke all on table app.clarification_answer_submissions
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;
revoke all on table app.clarification_responses
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;
grant select on app.clarification_answer_submissions, app.clarification_responses
  to coordination_api, coordination_worker;

create or replace function app.submit_planning_clarifications(
  p_company_id uuid,
  p_request_id uuid,
  p_request_version integer,
  p_candidate_contract_id uuid,
  p_answers jsonb,
  p_idempotency_key text,
  p_command_digest bytea,
  p_correlation_id uuid
)
returns table (
  request_id uuid,
  status text,
  request_version integer,
  created boolean
)
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_actor_membership_id uuid;
  v_actor_role text;
  v_original app.planning_requests%rowtype;
  v_submission app.clarification_answer_submissions%rowtype;
  v_latest_candidate_id uuid;
  v_derived_request_id uuid := gen_random_uuid();
  v_submission_id uuid := gen_random_uuid();
  v_question record;
  v_answer text;
  v_blocking_count integer;
  v_answered_blocking_count integer;
begin
  if not app.request_context_present()
     or p_company_id <> app.current_company_id()
     or not app.can_manage_planning(p_company_id, app.current_actor_id()) then
    raise exception using errcode = '42501', message = 'manager_authority_required';
  end if;
  if p_request_version <= 0
     or length(p_idempotency_key) not between 16 and 128
     or octet_length(p_command_digest) <> 32
     or jsonb_typeof(p_answers) <> 'object'
     or p_answers = '{}'::jsonb then
    raise exception using errcode = '22023', message = 'clarification_command_invalid';
  end if;

  select membership.id, membership.administrative_role
    into v_actor_membership_id, v_actor_role
  from app.company_memberships as membership
  where membership.company_id = p_company_id
    and membership.user_id = app.current_actor_id()
    and membership.membership_status = 'active'
    and membership.administrative_role in ('manager', 'company_admin');
  if v_actor_membership_id is null then
    raise exception using errcode = '42501', message = 'manager_authority_required';
  end if;

  select submission.* into v_submission
  from app.clarification_answer_submissions as submission
  where submission.company_id = p_company_id
    and submission.actor_membership_id = v_actor_membership_id
    and submission.idempotency_key = p_idempotency_key;
  if found then
    if v_submission.command_digest <> p_command_digest then
      raise exception using errcode = '23505', message = 'clarification_idempotency_conflict';
    end if;
    return query
    select derived.id, derived.status, derived.request_version, false
    from app.planning_requests as derived
    where derived.company_id = p_company_id
      and derived.id = v_submission.derived_request_id;
    return;
  end if;

  select submission.* into v_submission
  from app.clarification_answer_submissions as submission
  where submission.company_id = p_company_id
    and submission.request_id = p_request_id
    and submission.request_version = p_request_version
    and submission.candidate_contract_id = p_candidate_contract_id;
  if found then
    if v_submission.command_digest <> p_command_digest then
      raise exception using errcode = '40001', message = 'clarification_already_answered';
    end if;
    return query
    select derived.id, derived.status, derived.request_version, false
    from app.planning_requests as derived
    where derived.company_id = p_company_id
      and derived.id = v_submission.derived_request_id;
    return;
  end if;

  select original.* into v_original
  from app.planning_requests as original
  where original.company_id = p_company_id and original.id = p_request_id
  for update;
  if not found then
    raise exception using errcode = '22023', message = 'planning_request_not_found';
  end if;
  if v_original.request_version <> p_request_version then
    raise exception using errcode = '40001', message = 'stale_request_version';
  end if;
  if v_original.status <> 'clarification_required' then
    raise exception using errcode = '40001', message = 'clarification_not_required';
  end if;

  select candidate.id into v_latest_candidate_id
  from app.candidate_contracts as candidate
  join app.interpretation_runs as interpretation
    on interpretation.company_id = candidate.company_id
   and interpretation.id = candidate.interpretation_run_id
  where candidate.company_id = p_company_id
    and candidate.request_id = p_request_id
  order by interpretation.started_at desc, interpretation.id desc
  limit 1;
  if v_latest_candidate_id is distinct from p_candidate_contract_id then
    raise exception using errcode = '40001', message = 'stale_candidate_contract';
  end if;

  if exists (
    select 1 from jsonb_object_keys(p_answers) as supplied(question_key)
    where not exists (
      select 1 from app.clarification_questions as question
      where question.company_id = p_company_id
        and question.request_id = p_request_id
        and question.candidate_contract_id = p_candidate_contract_id
        and question.question_key = supplied.question_key
        and question.status = 'open'
    )
  ) then
    raise exception using errcode = '22023', message = 'clarification_question_invalid';
  end if;

  select count(*)::integer,
         count(*) filter (where p_answers ? question.question_key)::integer
    into v_blocking_count, v_answered_blocking_count
  from app.clarification_questions as question
  where question.company_id = p_company_id
    and question.request_id = p_request_id
    and question.candidate_contract_id = p_candidate_contract_id
    and question.status = 'open'
    and question.blocks_planning;
  if v_blocking_count = 0 or v_answered_blocking_count <> v_blocking_count then
    raise exception using errcode = '22023', message = 'blocking_clarifications_incomplete';
  end if;

  for v_question in
    select question.id, question.question_key
    from app.clarification_questions as question
    where question.company_id = p_company_id
      and question.request_id = p_request_id
      and question.candidate_contract_id = p_candidate_contract_id
      and question.status = 'open'
      and p_answers ? question.question_key
    order by question.question_key
  loop
    v_answer := btrim(p_answers ->> v_question.question_key);
    if v_answer is null or length(v_answer) not between 1 and 4000 then
      raise exception using errcode = '22023', message = 'clarification_answer_invalid';
    end if;
  end loop;

  insert into app.planning_requests (
    id, company_id, project_id, requester_membership_id, original_prompt,
    requested_priority_key, requested_deadline, requested_deadline_timezone,
    status, idempotency_key, request_digest, request_version,
    clarification_parent_request_id, clarification_parent_request_version,
    clarification_parent_candidate_id
  ) values (
    v_derived_request_id, p_company_id, v_original.project_id,
    v_original.requester_membership_id, v_original.original_prompt,
    v_original.requested_priority_key, v_original.requested_deadline,
    v_original.requested_deadline_timezone, 'pending_interpretation',
    'clarification:' || v_submission_id::text, p_command_digest,
    p_request_version + 1, p_request_id, p_request_version, p_candidate_contract_id
  );

  insert into app.planning_request_sources (
    company_id, request_id, source_id, source_version_id, selected_at
  )
  select selected.company_id, v_derived_request_id, selected.source_id,
         selected.source_version_id, clock_timestamp()
  from app.planning_request_sources as selected
  where selected.company_id = p_company_id and selected.request_id = p_request_id;

  insert into app.clarification_answer_submissions (
    id, company_id, request_id, request_version, candidate_contract_id,
    derived_request_id, actor_membership_id, authority_role, idempotency_key,
    command_digest, correlation_id
  ) values (
    v_submission_id, p_company_id, p_request_id, p_request_version,
    p_candidate_contract_id, v_derived_request_id, v_actor_membership_id,
    v_actor_role, p_idempotency_key, p_command_digest, p_correlation_id
  );

  for v_question in
    select question.id, question.question_key
    from app.clarification_questions as question
    where question.company_id = p_company_id
      and question.request_id = p_request_id
      and question.candidate_contract_id = p_candidate_contract_id
      and question.status = 'open'
      and p_answers ? question.question_key
    order by question.question_key
  loop
    v_answer := btrim(p_answers ->> v_question.question_key);
    insert into app.clarification_responses (
      company_id, submission_id, request_id, request_version,
      candidate_contract_id, clarification_question_id, actor_membership_id,
      answer, answer_digest
    ) values (
      p_company_id, v_submission_id, p_request_id, p_request_version,
      p_candidate_contract_id, v_question.id, v_actor_membership_id,
      v_answer, extensions.digest(convert_to(v_answer, 'UTF8'), 'sha256')
    );
    update app.clarification_questions as question
    set status = 'answered'
    where question.company_id = p_company_id
      and question.id = v_question.id
      and question.status = 'open';
  end loop;

  update app.planning_requests as original
  set status = 'clarification_answered'
  where original.company_id = p_company_id
    and original.id = p_request_id
    and original.status = 'clarification_required';

  insert into app.audit_events (
    company_id, actor_membership_id, event_type, aggregate_type, aggregate_id,
    outcome, policy_revision, input_digest, output_digest, details, correlation_id
  ) values (
    p_company_id, v_actor_membership_id, 'planning.clarifications_answered',
    'planning_request', p_request_id, 'accepted', 0, p_command_digest,
    extensions.digest(convert_to(v_derived_request_id::text, 'UTF8'), 'sha256'),
    jsonb_build_object(
      'candidate_contract_id', p_candidate_contract_id,
      'derived_request_id', v_derived_request_id,
      'request_version', p_request_version,
      'resumed_request_version', p_request_version + 1
    ),
    p_correlation_id
  );

  return query
  select derived.id, derived.status, derived.request_version, true
  from app.planning_requests as derived
  where derived.company_id = p_company_id and derived.id = v_derived_request_id;
end
$$;

revoke execute on function app.submit_planning_clarifications(
  uuid, uuid, integer, uuid, jsonb, text, bytea, uuid
) from public, anon, authenticated, service_role, coordination_worker;
grant execute on function app.submit_planning_clarifications(
  uuid, uuid, integer, uuid, jsonb, text, bytea, uuid
) to coordination_api;

insert into app_private.migration_contract (version, name)
values ('20260926025000', 'clarification_resume');
