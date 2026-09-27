-- Assistant text may stage a manager action, but it never performs the action.
-- Confirmation is handled by the API through the existing planning, approval
-- and commitment commands, which recheck the exact binding and current authority.
alter table app.assistant_action_previews
  drop constraint assistant_action_previews_command_type_check,
  drop constraint assistant_action_previews_state_check;

update app.assistant_action_previews
set state=case state
  when 'pending' then 'pending_confirmation'
  when 'confirmed' then 'completed'
  when 'cancelled' then 'dismissed'
  else state end;

alter table app.assistant_action_previews
  alter column state set default 'pending_confirmation',
  add column title text not null default 'Suggested action'
    check(length(title) between 1 and 160),
  add column summary text not null default '' check(length(summary)<=2000),
  add column project_id uuid,
  add column proposal_id uuid,
  add column plan_id uuid,
  add column action_payload jsonb not null default '{}'::jsonb
    check(jsonb_typeof(action_payload)='object' and octet_length(action_payload::text)<=20000),
  add column result jsonb
    check(result is null or (jsonb_typeof(result)='object' and octet_length(result::text)<=4096)),
  add column row_version bigint not null default 1 check(row_version>0),
  add column decided_by_auth_user_id uuid references auth.users(id),
  add column decided_at timestamptz,
  add constraint assistant_action_previews_command_type_check
    check(command_type in ('acknowledge_task','open_plan_review','open_task','share_preference',
      'plan_change','plan_approval','plan_commit')),
  add constraint assistant_action_previews_state_check
    check(state in ('pending_confirmation','executing','completed','dismissed','expired','failed')),
  add constraint assistant_action_previews_project_fk
    foreign key(company_id,project_id) references app.projects(company_id,id),
  add constraint assistant_action_previews_proposal_fk
    foreign key(company_id,proposal_id) references app.ai_plan_proposals(company_id,id),
  add constraint assistant_action_previews_plan_fk
    foreign key(company_id,plan_id) references app.plans(company_id,id),
  add constraint assistant_action_plan_scope_check check(
    command_type not in ('plan_change','plan_approval','plan_commit')
    or (project_id is not null and proposal_id is not null)
  ),
  add constraint assistant_action_decision_check check(
    command_type not in ('plan_change','plan_approval','plan_commit')
    or (state='pending_confirmation' and decided_by_auth_user_id is null and decided_at is null)
    or (state<>'pending_confirmation' and decided_by_auth_user_id is not null and decided_at is not null)
  );

create index assistant_action_previews_message_idx
  on app.assistant_action_previews(company_id,message_id);

create policy action_preview_worker_insert on app.assistant_action_previews
for insert to coordination_worker with check(
  exists(
    select 1 from app.assistant_messages message
    join app.assistant_threads thread
      on thread.company_id=message.company_id and thread.id=message.thread_id
    where message.company_id=assistant_action_previews.company_id
      and message.id=assistant_action_previews.message_id
      and message.role='assistant' and message.status='completed'
      and app.owns_thread(thread.company_id,thread.id)
      and thread.context_type='project'
      and assistant_action_previews.demo_run_id is not distinct from thread.demo_run_id
      and thread.context_id=assistant_action_previews.project_id
      and thread.proposal_id=assistant_action_previews.proposal_id
      and (assistant_action_previews.plan_id is null or exists(
        select 1 from app.plans plan
        where plan.company_id=assistant_action_previews.company_id
          and plan.id=assistant_action_previews.plan_id
          and plan.ai_proposal_id=assistant_action_previews.proposal_id
      ))
  )
);

create policy action_preview_manager_update on app.assistant_action_previews
for update to coordination_api
using(
  state='pending_confirmation'
  and app.can_manage_planning(company_id,app.current_actor_id())
  and exists(select 1 from app.assistant_messages message
    where message.company_id=assistant_action_previews.company_id
      and message.id=assistant_action_previews.message_id
      and app.owns_thread(message.company_id,message.thread_id))
)
with check(
  state in ('completed','dismissed','expired','failed')
  and decided_by_auth_user_id=app.current_actor_id() and decided_at is not null
  and app.can_manage_planning(company_id,app.current_actor_id())
  and exists(select 1 from app.assistant_messages message
    where message.company_id=assistant_action_previews.company_id
      and message.id=assistant_action_previews.message_id
      and app.owns_thread(message.company_id,message.thread_id))
);

grant insert on app.assistant_action_previews to coordination_worker;
grant update(state,result,row_version,decided_by_auth_user_id,decided_at)
  on app.assistant_action_previews to coordination_api;

insert into app_private.migration_contract(version,name)
values ('20260927037000','alto_confirmed_assistant_plan_actions');
