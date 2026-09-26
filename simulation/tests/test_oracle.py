"""Exhaustive four-slot independent oracle, solely evaluation code."""
import itertools
import unittest

from coordination_sim.benchmark.contracts import Dependency, Outcome, Reservation, Segment, Span
from coordination_sim.benchmark.generation import generate
from coordination_sim.benchmark.validation import validate


class OracleTests(unittest.TestCase):
    def test_all_sixteen_pairs_match_independent_oracle(self):
        s=generate()
        first=s.tasks[0].model_copy(update={'effort_slots':1,'window':Span(start=0,end=4),'agreed_deadline_slot':4,'requested_deadline_slot':4})
        second=s.tasks[1].model_copy(update={'effort_slots':1,'window':Span(start=0,end=4),'agreed_deadline_slot':4,'requested_deadline_slot':4,
                 'required_skills':('api',),'eligible_owners':('e0004',),'dependencies':(Dependency(predecessor='h0'),),
                 'reviewer_id':None,'review_task_id':None,'self_certifiable':True,'separation_of_duties':False})
        s=s.model_copy(update={'sources':tuple(x.model_copy(update={'fields':{**x.fields,'deadline_slot':4}}) if x.source_id=='hikari-commitment-v1' else x for x in s.sources),'tasks':(first,second),'schedule':(), 'reservations':(Reservation(reservation_id='oracle-busy',company_id=s.company.company_id,employee_id='e0004',span=Span(start=2,end=3),source_ref='opaque-capacity-v1'),)})
        accepted=[]
        for a,b in itertools.product(range(4),repeat=2):
            # Independent finite-domain specification: two ordered one-slot jobs,
            # neither occupies unavailable slot 2; exclusive capacity is automatic
            # from strict order. No baseline/validator call determines this label.
            expected=a<b and a!=2 and b!=2
            blocks=tuple(Segment(block_id=f'b-{tid}',company_id=s.company.company_id,task_id=tid,employee_id='e0004',span=Span(start=t,end=t+1)) for tid,t in [('h0',a),('h1',b)])
            o=Outcome(method='naive',classification='FEASIBLE',terminal='COMPLETED',schedule=blocks,considered_task_ids=('h0','h1'),iterations=1,plan_versions=1)
            actual=not validate(s,o).violations
            self.assertEqual(actual,expected,(a,b))
            if actual:accepted.append((a,b))
        self.assertEqual(accepted,[(0,1),(0,3),(1,3)])
