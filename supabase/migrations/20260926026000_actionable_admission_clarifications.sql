-- Surface every deterministic clarification requirement and prevent future silent dead ends.

with clarification_issues as (
  select candidate.company_id,
         candidate.id as candidate_contract_id,
         candidate.request_id,
         candidate.contract_json,
         issue.value as issue,
         issue.ordinality
  from app.candidate_contracts as candidate
  cross join lateral jsonb_array_elements(candidate.validation_issues)
    with ordinality as issue(value, ordinality)
  where candidate.admission_status = 'clarification_required'
    and issue.value ->> 'disposition' = 'clarify'
)
insert into app.clarification_questions (
  company_id, request_id, candidate_contract_id, question_key,
  category, question, blocks_planning, related_task_keys
)
select issue.company_id,
       issue.request_id,
       issue.candidate_contract_id,
       'admission_' || issue.ordinality::text || '_' || substring(
         encode(
           extensions.digest(
             convert_to(
               coalesce(issue.issue ->> 'code', '') || ':'
                 || coalesce(issue.issue ->> 'path', ''),
               'UTF8'
             ),
             'sha256'
           ),
           'hex'
         )
         from 1 for 8
       ),
       case
         when issue.issue ->> 'code' in (
           'authority_unknown', 'deadline_authority_unknown',
           'material_assumption', 'unconfirmed_source_authority'
         ) then 'authority'
         when issue.issue ->> 'code' = 'insufficient_context' then 'missing_data'
         when issue.issue ->> 'code' = 'sensitive_request' then 'disclosure'
         else 'ambiguity'
       end,
       left(
         case
           when issue.issue ->> 'code' = 'material_assumption' then
             'Confirm or correct this material assumption: '
             || coalesce(
               issue.contract_json #>> array[
                 'assumptions',
                 substring(issue.issue ->> 'path' from '^assumptions\[([0-9]+)\]$'),
                 'statement'
               ],
               issue.issue ->> 'message'
             )
             || ' Required decision authority: '
             || replace(
               coalesce(
                 issue.contract_json #>> array[
                   'assumptions',
                   substring(issue.issue ->> 'path' from '^assumptions\[([0-9]+)\]$'),
                   'authority_required'
                 ],
                 'manager'
               ),
               '_', ' '
             )
             || '.'
           when issue.issue ->> 'code' = 'deadline_authority_unknown' then
             'Confirm whether the proposed deadline is fixed or negotiable and identify '
             || 'the decision authority.'
           when issue.issue ->> 'code' in (
             'unsupported_constraint', 'unsupported_action', 'insufficient_context'
           ) then
             'The requested plan contains this unresolved item: '
             || coalesce(issue.issue ->> 'message', 'Additional context is required.')
             || ' Explain how it should be handled.'
           when issue.issue ->> 'code' = 'model_clarification' then
             coalesce(issue.issue ->> 'message', 'Additional clarification is required.')
           else
             'Resolve this planning issue before continuing: '
             || coalesce(issue.issue ->> 'message', 'Additional clarification is required.')
         end,
         1000
       ),
       true,
       '[]'::jsonb
from clarification_issues as issue
where not exists (
  select 1
  from app.clarification_questions as existing
  where existing.company_id = issue.company_id
    and existing.candidate_contract_id = issue.candidate_contract_id
    and (
      existing.question_key = 'admission_' || issue.ordinality::text || '_' || substring(
        encode(
          extensions.digest(
            convert_to(
              coalesce(issue.issue ->> 'code', '') || ':'
                || coalesce(issue.issue ->> 'path', ''),
              'UTF8'
            ),
            'sha256'
          ),
          'hex'
        )
        from 1 for 8
      )
      or (
        issue.issue ->> 'code' = 'model_clarification'
        and existing.question = issue.issue ->> 'message'
      )
    )
)
on conflict (company_id, candidate_contract_id, question_key) do nothing;

-- Historical rows may pre-date deterministic validation issues. Give every remaining
-- clarification-required candidate one visible manager action before enabling the invariant.
insert into app.clarification_questions (
  company_id, request_id, candidate_contract_id, question_key,
  category, question, blocks_planning, related_task_keys
)
select candidate.company_id,
       candidate.request_id,
       candidate.id,
       'admission_fallback',
       'ambiguity',
       'Review the interpretation and provide the missing planning decision before continuing.',
       true,
       '[]'::jsonb
from app.candidate_contracts as candidate
where candidate.admission_status = 'clarification_required'
  and not exists (
    select 1
    from app.clarification_questions as question
    where question.company_id = candidate.company_id
      and question.candidate_contract_id = candidate.id
      and question.blocks_planning
  )
on conflict (company_id, candidate_contract_id, question_key) do nothing;

create or replace function app.assert_candidate_has_blocking_clarification()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
begin
  if new.admission_status = 'clarification_required'
     and not exists (
       select 1
       from app.clarification_questions as question
       where question.company_id = new.company_id
         and question.candidate_contract_id = new.id
         and question.blocks_planning
     ) then
    raise exception using
      errcode = '23514',
      message = 'clarification_required_candidate_has_no_blocking_question';
  end if;
  return null;
end
$$;

revoke execute on function app.assert_candidate_has_blocking_clarification()
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;

create constraint trigger candidate_contracts_require_blocking_clarification
  after insert or update of admission_status on app.candidate_contracts
  deferrable initially deferred
  for each row execute function app.assert_candidate_has_blocking_clarification();

insert into app_private.migration_contract (version, name)
values ('20260926026000', 'actionable_admission_clarifications');
