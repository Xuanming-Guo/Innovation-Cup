from __future__ import annotations

import ast
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from coordination_sim.benchmark.contracts import (Acceptance, Approval, Disclosure, Outcome, Segment, Snapshot, Span)
from coordination_sim.benchmark.generation import apply_change, change, generate, instant
from coordination_sim.benchmark.naive import NaiveCoordinator
from coordination_sim.benchmark.trace import Trace
from coordination_sim.benchmark.validation import candidate_digest, validate
from coordination_sim.benchmark.workspaces import SimulatedWorkspace, authorised_manifest
from coordination_sim.serialization import digest


def initial(s):
    return Outcome(method="naive", classification="FEASIBLE", terminal="COMPLETED", schedule=s.schedule,
                   considered_task_ids=(), iterations=0, plan_versions=0)


class FixtureValidationTests(unittest.TestCase):
    def setUp(self):
        self.s=generate()
        self.o=initial(self.s)

    def codes(self,o=None,s=None,at=0):
        return {v.code for v in validate(s or self.s,o or self.o,at).violations}

    def test_coherent_tiny_counts_and_initial_validity(self):
        self.assertEqual((len(self.s.employees),len(self.s.teams),len(self.s.tasks)),(25,4,75))
        self.assertEqual(sum(len(e.team_ids)>1 for e in self.s.employees),20)
        self.assertEqual(self.codes(),set())
        self.assertEqual(digest(self.s),digest(generate()))
        self.assertNotEqual(digest(self.s),digest(generate(seed=18)))
        self.assertEqual(len({e.employee_id for e in self.s.employees}),25)
        self.assertEqual({s.provider for s in self.s.sources},{"teams","calendar","planner","sharepoint","github"})

    def test_structural_rejection(self):
        for mutation in (lambda d:d['tasks'][0].update(effort_slots=-1),
                         lambda d:d['tasks'][0].update(effort_slots=True),
                         lambda d:d['employees'][0].update(company_id='other'),
                         lambda d:d['tasks'][0].update(dependencies=[{'predecessor':'h4'}]),
                         lambda d:d['tasks'][0].update(source_ref='absent'),
                         lambda d:d['company'].update(anchor='2026-09-28T09:00:00')):
            d=self.s.model_dump(mode='json');mutation(d)
            with self.assertRaises(ValidationError):Snapshot.model_validate(d)
        with self.assertRaises(ValidationError):Snapshot.model_validate_json('{bad')

    def test_effort_owner_segments_unknown_and_tenant(self):
        first=self.o.schedule[0]
        bad=first.model_copy(update={'company_id':'other','employee_id':'e0005','span':Span(start=1,end=2)})
        result=self.codes(self.o.model_copy(update={'schedule':(bad,*self.o.schedule[1:])}))
        self.assertTrue({'cross_tenant','owner_eligibility','effort_total'}<=result)
        self.assertIn('missing_or_multiple_owners',self.codes(self.o.model_copy(update={'schedule':self.o.schedule[1:]})))
        self.assertIn('duplicate_block',self.codes(self.o.model_copy(update={'schedule':(*self.o.schedule,first)})))
        self.assertIn('unknown_reference',self.codes(self.o.model_copy(update={'schedule':(first.model_copy(update={'task_id':'foreign'}),)})))

    def test_windows_budgets_fixed_and_overlap(self):
        e=self.s.employees[4].model_copy(update={'daily_budget_slots':1,'weekly_budget_slots':1})
        s=self.s.model_copy(update={'employees':(*self.s.employees[:4],e,*self.s.employees[5:])})
        self.assertTrue({'daily_budget','weekly_budget'}<=self.codes(s=s))
        b=self.o.schedule[0].model_copy(update={'span':Span(start=10,end=14)})
        self.assertIn('working_window',self.codes(self.o.model_copy(update={'schedule':(b,*self.o.schedule[1:])})))
        t=self.s.tasks[0].model_copy(update={'timing':'fixed'})
        self.assertIn('fixed_attendance',self.codes(s=self.s.model_copy(update={'tasks':(t,*self.s.tasks[1:])})))

    def test_source_revocation_qualifications_and_no_transitive_access(self):
        revoked=apply_change(self.s,change('revoked'))
        self.assertTrue({'source_access','unsupported_constraint'}<=self.codes(s=revoked))
        e=self.s.employees[6].model_copy(update={'qualifications':()})
        self.assertIn('owner_eligibility',self.codes(s=self.s.model_copy(update={'employees':(*self.s.employees[:6],e,*self.s.employees[7:])})))
        d=Disclosure(viewer_id='e0012',source_refs=('incident-declaration-v1',),brief_ids=('brief-incident',))
        self.assertTrue({'forbidden_source','unapproved_brief'}<=self.codes(self.o.model_copy(update={'disclosures':(d,)})))

    def test_dependencies_review_and_actual_acceptance(self):
        o=self.o.model_copy(update={'actual_starts':{'h3':288}})
        self.assertIn('acceptance_release',self.codes(o))
        t=self.s.tasks[1].model_copy(update={'reviewer_id':'e0005'})
        self.assertTrue({'reviewer_eligibility','review_capacity_missing'}<=self.codes(s=self.s.model_copy(update={'tasks':(self.s.tasks[0],t,*self.s.tasks[2:])})))
        b=self.o.schedule[2].model_copy(update={'span':Span(start=16,end=20)})
        self.assertIn('precedence_or_lag',self.codes(self.o.model_copy(update={'schedule':(*self.o.schedule[:2],b,*self.o.schedule[3:])})))

    def test_deadline_priority_forecast_protection_and_exact_approval(self):
        self.assertTrue({'deadline_change','priority_change','forecast_mismatch','protection_or_cancellation_change'}<=self.codes(self.o.model_copy(update={
            'agreed_deadlines':{'h0':416},'priorities':{'h0':0},'forecast_deadlines':{'h0':2},'protected_values':{'h0':True}})))
        b=self.o.schedule[0].model_copy(update={'span':Span(start=0,end=4)})
        o=self.o.model_copy(update={'schedule':(b,*self.o.schedule[1:])})
        self.assertIn('protected_or_started_movement',self.codes(o,at=17))
        task=self.s.tasks[0].model_copy(update={'required_approver':'e0000'})
        s=self.s.model_copy(update={'tasks':(task,*self.s.tasks[1:])})
        self.assertIn('required_approval',self.codes(o,s))
        approval=Approval(actor_id='e0000',task_ids=('h0',),proposal_digest=candidate_digest(o),base_revision=0,decision='approved',source_ref='policy-v1')
        self.assertNotIn('required_approval',self.codes(o.model_copy(update={'approvals':(approval,)}),s))
        self.assertIn('required_approval',self.codes(o.model_copy(update={'approvals':(approval.model_copy(update={'base_revision':4}),)}),s))

    def test_split_minimum_and_passive_capacity(self):
        t=self.s.tasks[0].model_copy(update={'min_segment_slots':2,'max_segments':2})
        s=self.s.model_copy(update={'tasks':(t,*self.s.tasks[1:])})
        b=self.o.schedule[0]
        split=(b.model_copy(update={'span':Span(start=16,end=17)}),b.model_copy(update={'block_id':'split','span':Span(start=18,end=21)}))
        self.assertIn('minimum_run',self.codes(self.o.model_copy(update={'schedule':(*split,*self.o.schedule[1:])}),s))
        passive=t.model_copy(update={'timing':'passive','effort_slots':0,'passive_slots':4})
        s=s.model_copy(update={'tasks':(passive,*s.tasks[1:])})
        self.assertEqual(self.codes(s=s),set())

    def test_utc_slots_handle_dst_with_explicit_timezone(self):
        company=self.s.company.model_copy(update={'anchor':datetime(2026,11,1,5,tzinfo=timezone.utc),'timezone':'America/New_York'})
        self.assertEqual((instant(company,8)-instant(company,0)).total_seconds(),7200)
        self.assertNotEqual(instant(company,0).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).utcoffset(),
                            instant(company,8).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).utcoffset())


class NaiveTests(unittest.TestCase):
    def run_case(self,s,case,cap=200):
        e=change(case);s=apply_change(s,e);tr=Trace('test',s.company)
        return s,NaiveCoordinator(cap).run(s,e,tr),tr

    def test_connected_chain_and_determinism(self):
        a,o,t=self.run_case(generate(),'A')
        self.assertEqual(validate(a,o).violations,())
        self.assertEqual([(b.span.start,b.span.end) for b in o.schedule if b.task_id.startswith('h')],[(0,4),(8,12),(16,20),(20,24),(24,28)])
        b,ob,tb=self.run_case(a.model_copy(update={'schedule':o.schedule,'revision':1}),'B')
        self.assertEqual(validate(b,ob,4).violations,())
        self.assertEqual(ob.iterations,8)
        self.assertEqual(sum(r['action_type']=='conflict_discovered' for r in tb.rows),3)
        _,again,ta=self.run_case(generate(),'A')
        self.assertEqual(digest(o),digest(again));self.assertEqual(t.semantic_digest(),ta.semantic_digest())

    def test_failure_noimpact_and_hr_paths(self):
        for case,terminal in [('no-impact','COMPLETED'),('impossible','REFUSED'),('revoked','REFUSED'),('unavailable','UNKNOWN'),('concurrent','UNKNOWN'),('HR','COMPLETED')]:
            s,o,t=self.run_case(generate(),case)
            self.assertEqual(o.terminal,terminal,case)
            if terminal=='COMPLETED':self.assertEqual(validate(s,o,change(case).at_slot).violations,(),case)
        _,o,_=self.run_case(generate(),'A',1)
        self.assertEqual(o.terminal,'TIMED_OUT')

    def test_no_scorer_or_product_imports(self):
        forbidden={'validation','scoring','z3','coordination','supabase','google','solver','compile_model'}
        for path in [Path('coordination_sim/benchmark/naive.py')]:
            tree=ast.parse(path.read_text())
            imports={n.module.split('.')[-1] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module}
            self.assertFalse(forbidden & imports)
        tree=ast.parse(Path('coordination_sim/benchmark/validation.py').read_text())
        imports={n.module.split('.')[-1] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module}
        self.assertFalse({'naive','generation','sut','workspaces'} & imports)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.s=generate();self.trace=Trace('test',self.s.company)
        self.w=SimulatedWorkspace('calendar',self.s,self.trace)
        self.now=self.s.company.anchor

    def test_scoped_denial_and_private_calendar_reduction(self):
        src=self.w.objects['working-rules-v1']
        self.w.objects[src.source_id]=src.model_copy(update={'fields':{'subject':'PRIVATE SUBJECT','known':True},'excerpt':'PRIVATE REASON'})
        for cid,person in [('other','coordinator'),(self.s.company.company_id,'unknown')]:
            r=self.w.read(cid,person,('working-rules-v1',),fields=('fields','excerpt'),now=self.now)
            self.assertEqual((r.status,r.records),('DENIED',()))
        r=self.w.read(self.s.company.company_id,'coordinator',('working-rules-v1',),fields=('fields','excerpt'),now=self.now)
        self.assertNotIn('PRIVATE',json.dumps(r.records));self.assertEqual(r.status,'OK')
        self.w.revoke('working-rules-v1')
        self.assertEqual(self.w.read(self.s.company.company_id,'coordinator',('working-rules-v1',),fields=(),now=self.now).status,'DENIED')

    def test_stale_unavailable_throttle_pagination_duplicate(self):
        self.w.page_size=1
        args=(self.s.company.company_id,'coordinator',('working-rules-v1','opaque-capacity-v1'))
        r=self.w.read(*args,fields=(),now=self.now);self.assertEqual(r.next_cursor,1)
        self.w.throttle_once=True
        self.assertEqual(self.w.read(*args,fields=(),now=self.now).status,'THROTTLED')
        self.w.unavailable=True
        self.assertEqual(self.w.read(*args,fields=(),now=self.now).status,'UNAVAILABLE')
        self.w.unavailable=False
        self.assertEqual(self.w.read(*args,fields=(),now=self.now+timedelta(days=9)).status,'DENIED')
        self.w.objects['working-rules-v1']=self.w.objects['working-rules-v1'].model_copy(update={'freshness':'stale'})
        self.assertEqual(self.w.read(*args,fields=(),now=self.now).status,'STALE')
        self.assertEqual(len(self.w.poll([('delivery-1','working-rules-v1')]*2)),1)

    def test_write_binding_partial_timeout_idempotency_and_human_edit(self):
        w=SimulatedWorkspace('planner',self.s,self.trace)
        sid='hikari-commitment-v1'
        w.grants=tuple(g.model_copy(update={'actions':('read','write')}) if g.principal_id=='coordinator' and g.resource_id==sid else g for g in w.grants)
        kwargs=dict(company_id=self.s.company.company_id,principal_id='coordinator',resource_id=sid,expected_version='1',idempotency_key='action-1',fields={'due':216},proposal_digest='exact',committed_revision=1,now=self.now)
        self.assertEqual(w.write(**kwargs)['status'],'DENIED')
        w.committed_evidence={'exact':1};w.script[sid]='TIMEOUT_AFTER_WRITE'
        self.assertEqual(w.write(**kwargs)['status'],'TIMEOUT_AFTER_WRITE')
        self.assertEqual(w.reconcile('action-1')['version'],'2')
        self.assertEqual(w.write(**kwargs)['status'],'IDEMPOTENT')
        self.assertEqual(w.write(**{**kwargs,'fields':{'due':217}})['status'],'KEY_CONFLICT')
        self.assertEqual(w.write(**{**kwargs,'idempotency_key':'next'})['status'],'STALE_VERSION')
        self.assertEqual(len(w.effects),1)
        w.script[sid]='PERMANENT_FAILURE'
        self.assertEqual(w.write(**{**kwargs,'expected_version':'2','idempotency_key':'failure'})['status'],'PERMANENT_FAILURE')
        self.assertEqual(len(w.effects),1)


class PriorityAndScopeRegressionTests(unittest.TestCase):
    def test_ready_critical_work_cannot_be_delayed_behind_movable_lower_priority(self):
        s=apply_change(generate(),change('B'))
        out=NaiveCoordinator().run(s,change('B'),Trace('test',s.company))
        blocks=list(out.schedule)
        # Critical Security task is ready at 10. Put lower-priority Hikari Security
        # at 10–14, and defer the Critical Security task to 16–18 on the same person.
        blocks=[b.model_copy(update={'span':Span(start=10,end=14)}) if b.task_id=='h3' else
                b.model_copy(update={'span':Span(start=16,end=18)}) if b.task_id=='i2' else b for b in blocks]
        codes={v.code for v in validate(s,out.model_copy(update={'schedule':tuple(blocks)}),4).violations}
        self.assertIn('ready_priority_inversion',codes)
