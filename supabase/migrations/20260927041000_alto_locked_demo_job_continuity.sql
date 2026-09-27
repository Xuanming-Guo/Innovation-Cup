-- The locked Northstar walkthrough is a deterministic planning pipeline. Keep
-- its queued planning work bound to the authenticated run owner, but do not
-- invalidate it merely because the UI rotated its short-lived persona session.
create or replace function app.alto_job_authorized(p_company_id uuid, p_job_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, app
as $$
  select exists(
    select 1
    from app.durable_jobs as job
    left join app.company_memberships as membership
      on membership.company_id=job.company_id
     and membership.id=job.requested_by_membership_id
    where job.company_id=p_company_id and job.id=p_job_id
      and (
        (
          job.demo_run_id is null
          and (
            job.requested_by_membership_id is null
            or membership.membership_status='active'
          )
        )
        or (
          job.demo_run_id is not null
          and app.can_access_demo_run(
            job.company_id, job.demo_run_id, membership.user_id, true
          )
          and (
            job.demo_actor_session_id is null
            or exists(
              select 1
              from app.demo_actor_sessions as session
              where session.company_id=job.company_id
                and session.id=job.demo_actor_session_id
                and session.run_id=job.demo_run_id
                and session.performed_by_auth_user_id=membership.user_id
                and session.simulated_actor_employee_id=job.simulated_employee_id
                and session.revoked_at is null
                and session.expires_at>statement_timestamp()
            )
            or (
              job.job_kind in ('interpretation.run','planning.materialize','plan.propose')
              and exists(
                select 1
                from app.demo_runs as run
                join app.demo_workspace_policies as policy
                  on policy.company_id=run.company_id
                 and policy.scenario_key=run.scenario_key
                 and policy.scenario_version=run.scenario_version
                join app.companies as company on company.id=run.company_id
                where run.company_id=job.company_id
                  and run.id=job.demo_run_id
                  and run.state='active'
                  and run.mode='live'
                  and policy.enabled
                  and company.is_demo
                  and company.status='active'
              )
            )
          )
        )
      )
  )
$$;

-- Release any deterministic planning request that the old session-level gate
-- already sent to manual review. Provider/model failures are not included.
with recoverable as materialized (
  select job.company_id, job.id, job.job_kind, job.aggregate_id
  from app.durable_jobs as job
  join app.demo_runs as run
    on run.company_id=job.company_id and run.id=job.demo_run_id
  join app.demo_workspace_policies as policy
    on policy.company_id=run.company_id
   and policy.scenario_key=run.scenario_key
   and policy.scenario_version=run.scenario_version
  join app.companies as company on company.id=run.company_id
  join app.company_memberships as membership
    on membership.company_id=job.company_id
   and membership.id=job.requested_by_membership_id
  where job.state='review_required'
    and job.last_error_code='requester_authority_revoked'
    and job.job_kind in ('interpretation.run','planning.materialize','plan.propose')
    and run.state='active' and run.mode='live'
    and policy.enabled and company.is_demo and company.status='active'
    and membership.membership_status='active'
    and app.can_access_demo_run(job.company_id,job.demo_run_id,membership.user_id,true)
), reset_requests as (
  update app.planning_requests as request
  set status='pending_interpretation'
  from recoverable
  where recoverable.job_kind='interpretation.run'
    and request.company_id=recoverable.company_id
    and request.id=recoverable.aggregate_id
    and request.status='failed'
  returning request.id
)
update app.durable_jobs as job
set state='queued',
    available_at=clock_timestamp(),
    lease_owner=null, lease_token=null, leased_at=null, leased_until=null,
    result=null, result_digest=null,
    last_error_code=null, last_error_message=null,
    completed_at=null, row_version=job.row_version+1
from recoverable
where job.company_id=recoverable.company_id and job.id=recoverable.id;

revoke all on function app.alto_job_authorized(uuid,uuid)
  from public,anon,authenticated,service_role,coordination_api,coordination_worker;
grant execute on function app.alto_job_authorized(uuid,uuid) to coordination_worker;

insert into app_private.migration_contract(version,name)
values ('20260927041000','alto_locked_demo_job_continuity');
