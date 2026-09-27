-- Keep the normal per-session authorization boundary. The worker queue may
-- replace a stale persona session only with a current session for the same
-- authenticated user, run and simulated employee before it leases planning.
create or replace function app.alto_job_authorized(p_company_id uuid,p_job_id uuid)
returns boolean
language sql
stable
security definer
set search_path=pg_catalog,app
as $$
  select exists(
    select 1 from app.durable_jobs job
    left join app.company_memberships membership
      on membership.company_id=job.company_id
     and membership.id=job.requested_by_membership_id
    where job.company_id=p_company_id and job.id=p_job_id and (
      (job.demo_run_id is null and (
        job.requested_by_membership_id is null
        or membership.membership_status='active'
      ))
      or (
        job.demo_run_id is not null
        and app.can_access_demo_run(
          job.company_id,job.demo_run_id,membership.user_id,true
        )
        and (
          job.demo_actor_session_id is null
          or exists(
            select 1 from app.demo_actor_sessions session
            where session.company_id=job.company_id
              and session.id=job.demo_actor_session_id
              and session.run_id=job.demo_run_id
              and session.performed_by_auth_user_id=membership.user_id
              and session.simulated_actor_employee_id=job.simulated_employee_id
              and session.revoked_at is null
              and session.expires_at>statement_timestamp()
          )
        )
      )
    )
  )
$$;

create or replace function app.reconcile_unauthorised_durable_jobs()
returns integer
language plpgsql
security definer
set search_path=pg_catalog,app
as $$
declare
  changed integer;
begin
  with replacement as materialized (
    select job.company_id,job.id,replacement_session.id as session_id
    from app.durable_jobs job
    join app.company_memberships membership
      on membership.company_id=job.company_id
     and membership.id=job.requested_by_membership_id
     and membership.membership_status='active'
    join app.demo_runs run
      on run.company_id=job.company_id and run.id=job.demo_run_id
    join app.demo_workspace_policies policy
      on policy.company_id=run.company_id
     and policy.scenario_key=run.scenario_key
     and policy.scenario_version=run.scenario_version
     and policy.enabled
    join app.companies company
      on company.id=run.company_id and company.is_demo and company.status='active'
    join lateral (
      select session.id
      from app.demo_actor_sessions session
      where session.company_id=job.company_id
        and session.run_id=job.demo_run_id
        and session.performed_by_auth_user_id=membership.user_id
        and session.simulated_actor_employee_id=job.simulated_employee_id
        and session.revoked_at is null
        and session.expires_at>statement_timestamp()
      order by session.created_at desc,session.id desc
      limit 1
    ) replacement_session on true
    where job.state in ('queued','retry_scheduled')
      and job.job_kind in ('interpretation.run','planning.materialize','plan.propose')
      and run.state='active' and run.mode='live'
      and job.demo_actor_session_id is not null
      and not exists(
        select 1 from app.demo_actor_sessions current_session
        where current_session.company_id=job.company_id
          and current_session.id=job.demo_actor_session_id
          and current_session.run_id=job.demo_run_id
          and current_session.performed_by_auth_user_id=membership.user_id
          and current_session.simulated_actor_employee_id=job.simulated_employee_id
          and current_session.revoked_at is null
          and current_session.expires_at>statement_timestamp()
      )
  )
  update app.durable_jobs job
  set demo_actor_session_id=replacement.session_id,
      row_version=job.row_version+1
  from replacement
  where job.company_id=replacement.company_id and job.id=replacement.id;

  with invalid as (
    select job.company_id,job.id
    from app.durable_jobs job
    left join app.company_memberships membership
      on membership.company_id=job.company_id
     and membership.id=job.requested_by_membership_id
    where job.state in ('queued','retry_scheduled') and (
      not app.alto_job_authorized(job.company_id,job.id)
      or (
        job.demo_run_id is null
        and job.job_kind in (
          'interpretation.run','planning.materialize','planning.run','plan.propose'
        )
        and (
          membership.id is null
          or membership.membership_status<>'active'
          or membership.administrative_role not in ('manager','company_admin')
        )
      )
    )
    for update of job skip locked
  )
  update app.durable_jobs job
  set state='review_required',last_error_code='requester_authority_revoked',
      last_error_message=null,completed_at=clock_timestamp(),
      row_version=job.row_version+1
  from invalid
  where job.company_id=invalid.company_id and job.id=invalid.id;
  get diagnostics changed=row_count;
  return changed;
end
$$;

-- Repair the request that was terminalled while its replacement session already
-- existed. Only the canonical interpretation stage and these two known errors
-- are eligible; model/provider failures remain terminal and recorded.
with recoverable as materialized (
  select job.company_id,job.id,job.aggregate_id,
         replacement_session.id as session_id
  from app.durable_jobs job
  join app.planning_requests request
    on request.company_id=job.company_id and request.id=job.aggregate_id
  join app.company_memberships membership
    on membership.company_id=job.company_id
   and membership.id=job.requested_by_membership_id
   and membership.membership_status='active'
  join app.demo_runs run
    on run.company_id=job.company_id and run.id=job.demo_run_id
  join app.demo_workspace_policies policy
    on policy.company_id=run.company_id
   and policy.scenario_key=run.scenario_key
   and policy.scenario_version=run.scenario_version
   and policy.enabled
  join app.companies company
    on company.id=run.company_id and company.is_demo and company.status='active'
  join lateral (
    select session.id
    from app.demo_actor_sessions session
    where session.company_id=job.company_id
      and session.run_id=job.demo_run_id
      and session.performed_by_auth_user_id=membership.user_id
      and session.simulated_actor_employee_id=job.simulated_employee_id
      and session.revoked_at is null
      and session.expires_at>statement_timestamp()
    order by session.created_at desc,session.id desc
    limit 1
  ) replacement_session on true
  where job.state='review_required'
    and job.job_kind='interpretation.run'
    and job.last_error_code in (
      'requester_authority_revoked','planning_request_unavailable'
    )
    and request.status in ('failed','pending_interpretation')
    and run.state='active' and run.mode='live'
), reset_requests as (
  update app.planning_requests request
  set status='pending_interpretation'
  from recoverable
  where request.company_id=recoverable.company_id
    and request.id=recoverable.aggregate_id
  returning request.id
)
update app.durable_jobs job
set demo_actor_session_id=recoverable.session_id,
    state='queued',available_at=clock_timestamp(),
    lease_owner=null,lease_token=null,leased_at=null,leased_until=null,
    result=null,result_digest=null,last_error_code=null,last_error_message=null,
    completed_at=null,row_version=job.row_version+1
from recoverable
where job.company_id=recoverable.company_id and job.id=recoverable.id;

revoke all on function app.alto_job_authorized(uuid,uuid),
  app.reconcile_unauthorised_durable_jobs()
  from public,anon,authenticated,service_role,coordination_api,coordination_worker;
grant execute on function app.alto_job_authorized(uuid,uuid),
  app.reconcile_unauthorised_durable_jobs() to coordination_worker;

insert into app_private.migration_contract(version,name)
values ('20260927042000','alto_locked_demo_session_rebind');
