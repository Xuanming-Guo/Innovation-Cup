-- Expired interpretation jobs are reconciled by the unscoped worker queue.
-- Install the job's recorded tenant/run context only for the related business
-- state writes, then return to the unscoped queue context before continuing.
create or replace function app.reconcile_expired_durable_jobs()
returns integer
language plpgsql
security definer
set search_path = pg_catalog, app
as $$
declare
  v_job app.durable_jobs%rowtype;
  v_state text;
  v_count integer := 0;
  v_actor_id uuid;
  v_prior_actor text := current_setting('app.actor_id', true);
  v_prior_company text := current_setting('app.company_id', true);
  v_prior_purpose text := current_setting('app.purpose', true);
  v_prior_run text := current_setting('app.demo_run_id', true);
  v_prior_session text := current_setting('app.demo_actor_session_id', true);
begin
  perform set_config('app.actor_id', '', true);
  perform set_config('app.company_id', '', true);
  perform set_config('app.demo_run_id', '', true);
  perform set_config('app.demo_actor_session_id', '', true);

  for v_job in
    select * from app.durable_jobs
    where state = 'leased' and leased_until <= clock_timestamp()
    order by leased_until
    for update skip locked
  loop
    v_state := case
      when v_job.cancel_requested_at is not null then 'cancelled'
      when v_job.attempt_count >= v_job.max_attempts then 'dead_letter'
      else 'retry_scheduled'
    end;

    update app.job_attempts
    set outcome = case when v_state = 'cancelled' then 'cancelled' else 'lease_expired' end,
        error_code = case when v_state = 'cancelled' then 'cancelled' else 'lease_expired' end,
        finished_at = clock_timestamp()
    where company_id = v_job.company_id and job_id = v_job.id
      and attempt_number = v_job.attempt_count and outcome is null;

    update app.durable_jobs
    set state = v_state,
        available_at = case when v_state = 'retry_scheduled'
          then clock_timestamp() else available_at end,
        lease_owner = null, lease_token = null, leased_at = null, leased_until = null,
        last_error_code = case when v_state = 'cancelled'
          then 'cancelled' else 'lease_expired' end,
        last_error_message = null,
        completed_at = case when v_state in ('cancelled', 'dead_letter')
          then clock_timestamp() else null end,
        row_version = row_version + 1
    where company_id = v_job.company_id and id = v_job.id;

    if v_job.job_kind = 'interpretation.run' then
      select membership.user_id into v_actor_id
      from app.company_memberships as membership
      where membership.company_id = v_job.company_id
        and membership.id = v_job.requested_by_membership_id;

      begin
        perform set_config('app.actor_id', coalesce(v_actor_id::text, ''), true);
        perform set_config('app.company_id', v_job.company_id::text, true);
        perform set_config('app.purpose', 'worker:reconcile-expired-job', true);
        perform set_config('app.demo_run_id', coalesce(v_job.demo_run_id::text, ''), true);
        perform set_config(
          'app.demo_actor_session_id',
          coalesce(v_job.demo_actor_session_id::text, ''),
          true
        );

        update app.interpretation_runs
        set status = 'failed', outcome = 'transient_failure',
            error_code = 'worker_lease_lost', completed_at = clock_timestamp()
        where company_id = v_job.company_id
          and request_id = v_job.aggregate_id and status = 'running';
        update app.planning_requests
        set status = 'failed'
        where company_id = v_job.company_id and id = v_job.aggregate_id
          and status = 'interpretation_running';
      exception when insufficient_privilege then
        -- Revoked or archived scope must not wedge the global worker queue. The
        -- queue ledger above remains authoritative and unauthorised work cannot retry.
        null;
      end;

      perform set_config('app.actor_id', '', true);
      perform set_config('app.company_id', '', true);
      perform set_config('app.purpose', '', true);
      perform set_config('app.demo_run_id', '', true);
      perform set_config('app.demo_actor_session_id', '', true);
    end if;

    if v_job.job_kind = 'outbox.deliver' then
      update app.outbox_intents
      set state = v_state, attempt_count = v_job.attempt_count,
          next_attempt_at = case when v_state = 'retry_scheduled'
            then clock_timestamp() else null end,
          lease_owner = null, lease_token = null, leased_until = null,
          last_error_code = case when v_state = 'cancelled'
            then 'cancelled' else 'lease_expired' end,
          last_error = null,
          review_required_at = case when v_state = 'dead_letter'
            then clock_timestamp() else null end,
          cancelled_at = case when v_state = 'cancelled'
            then clock_timestamp() else null end
      where company_id = v_job.company_id and id = v_job.aggregate_id
        and state <> 'delivered';
    end if;

    v_count := v_count + 1;
  end loop;

  perform set_config('app.actor_id', coalesce(v_prior_actor, ''), true);
  perform set_config('app.company_id', coalesce(v_prior_company, ''), true);
  perform set_config('app.purpose', coalesce(v_prior_purpose, ''), true);
  perform set_config('app.demo_run_id', coalesce(v_prior_run, ''), true);
  perform set_config('app.demo_actor_session_id', coalesce(v_prior_session, ''), true);
  return v_count;
end
$$;

revoke all on function app.reconcile_expired_durable_jobs()
  from public, anon, authenticated, service_role, coordination_api, coordination_worker;
grant execute on function app.reconcile_expired_durable_jobs() to coordination_worker;

insert into app_private.migration_contract(version, name)
values ('20260927040000', 'alto_expired_job_reconciliation');
