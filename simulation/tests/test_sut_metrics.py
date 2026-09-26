import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from coordination_sim.benchmark.generation import apply_change, change, generate
from coordination_sim.benchmark.metrics import Observation, PRIMARY, compute, headline, product_cells, ratio, registry
from coordination_sim.benchmark.runner import RECORDING, run
from coordination_sim.benchmark.sut import (ActorResponse, DeterministicActors, ProductUnavailable, RecordedReplay, check_mapping)
from coordination_sim.benchmark.trace import Trace
from coordination_sim.benchmark.workspaces import authorised_manifest
from coordination_sim.serialization import digest


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.s=generate();self.trace=Trace('test',self.s.company);self.replay=RecordedReplay(RECORDING,self.trace)

    def test_port_reset_seed_drive_response_observe_projection_export(self):
        self.assertEqual(len(self.replay.discover().supported),7)
        self.replay.reset(self.s.company.company_id);self.replay.seed(self.s)
        state=self.s
        for case in ('A','B'):
            event=change(case);snapshot=apply_change(state,event)
            manifest=authorised_manifest(snapshot,event,self.trace,'product_replay')
            requests=self.replay.submit(event,manifest)
            with self.assertRaisesRegex(ValueError,'NOT_TERMINAL'):self.replay.export()
            for req in requests:
                actors=DeterministicActors(snapshot,self.trace)
                response=actors.answer(req,case,'product_replay')
                with self.assertRaisesRegex(ValueError,'BINDING'):self.replay.respond(response.model_copy(update={'actor_id':'e0000'}))
                self.replay.respond(response)
                with self.assertRaisesRegex(ValueError,'UNISSUED'):self.replay.respond(response)
            self.assertEqual(len(self.replay.observe()),1)
            projection=self.replay.capture('e0008')
            self.assertNotIn('SSO',json.dumps(projection.model_dump()))
            self.assertEqual(projection.states.commitment,'NOT_AVAILABLE')
            with self.assertRaisesRegex(ValueError,'UNAVAILABLE'):self.replay.capture('unknown')
            outcome=self.replay.export()
            self.assertEqual(outcome,self.replay.frame.outcome)
            state=snapshot.model_copy(update={'schedule':outcome.schedule,'revision':state.revision+1})
            self.assertEqual(digest(state),self.replay.state_digest)
        self.replay.reset(self.s.company.company_id);self.replay.seed(self.s)
        self.assertEqual(self.replay.index,0)

    def test_missing_changed_and_broadened_mapping(self):
        event=change('A');s=apply_change(self.s,event)
        manifest=authorised_manifest(s,event,self.trace,'naive')
        self.assertEqual(check_mapping(manifest,copy.deepcopy(manifest)).status,'EQUIVALENT')
        for mutation in (lambda d:d['snapshot']['tasks'][0].update(effort_slots=1),
                         lambda d:d['snapshot']['tasks'][0].update(agreed_deadline_slot=416),
                         lambda d:d['snapshot']['grants'][0]['actions'].append('write'),
                         lambda d:d['snapshot'].pop('reservations'),
                         lambda d:d['snapshot']['employees'][0].update(daily_budget_slots=100)):
            bad=copy.deepcopy(manifest);mutation(bad)
            self.assertEqual(check_mapping(manifest,bad).status,'INVALID')
        self.replay.seed(self.s)
        bad=copy.deepcopy(manifest);bad['snapshot']['seed']=18
        with self.assertRaisesRegex(ValueError,'INPUT_MISMATCH'):self.replay.submit(event,bad)
        with self.assertRaisesRegex(ValueError,'RESET_SCOPE'):self.replay.reset('other-tenant')
        with self.assertRaisesRegex(ValueError,'SEED_MISMATCH'):self.replay.seed(generate(seed=18))

    def test_unavailable_real_product_and_no_gold_in_payloads(self):
        cap=ProductUnavailable().discover()
        self.assertEqual(cap.label,'NOT_RUN');self.assertIsNone(cap.product_commit)
        for method in ('seed','reset','submit','respond','observe','capture','export'):
            with self.assertRaises(NotImplementedError):getattr(ProductUnavailable(),method)()
        raw=RECORDING.read_text()
        for field in ('expected_classification','material_source_refs','review_note_ref','ground_truth'):
            self.assertNotIn(field,raw)


class RunMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.path=run()

    def test_primary_registry_provenance_and_product_nonclaim(self):
        self.assertEqual(len(PRIMARY),20)
        definitions={r['metric_id'] for r in registry()['metrics']}
        for case in ('A','B'):
            path=self.path/f'{case}-naive'
            observations=[Observation.model_validate(o) for o in json.loads((path/'metrics.json').read_text())]
            self.assertEqual({o.metric_id for o in observations},definitions)
            for o in observations:
                for ref in o.source_event_or_artifact_refs:self.assertTrue((self.path/ref).exists())
            product=product_cells('run',case)
            self.assertTrue(all(o.value is None and o.status=='NOT_RUN' for o in product))
            replay=[Observation.model_validate(o) for o in json.loads((self.path/f'{case}-product_replay/metrics.json').read_text())]
            inputs=json.loads((path/'input-manifest.json').read_text());mapping=check_mapping(inputs,inputs)
            self.assertEqual(headline(observations,replay,mapping)['status'],'NOT_RUN')
            self.assertIsNone(ratio(0,0))

    def test_main_manual_arithmetic(self):
        values={case:{o['metric_id']:o['value'] for o in json.loads((self.path/f'{case}-naive/metrics.json').read_text())} for case in ('A','B')}
        # A: |16-0|+|20-8|+|96-16|+|288-20|+|404-24| = 756 slots.
        a,b=values['A'],values['B']
        self.assertEqual(a['changed_commitments']['tasks'],5)
        self.assertEqual(a['displacement']['total'],756*15)
        self.assertEqual(a['owner_churn']['count'],0)
        self.assertEqual(b['changed_commitments']['tasks'],3)
        self.assertEqual(b['displacement']['total'],6*15)
        self.assertEqual(b['priority_service']['incident_resolution'],16*15)
        self.assertEqual(b['priority_service']['blocking_tasks'],14*15)
        self.assertEqual(b['replans']['planning_attempts'],8)
        self.assertEqual(b['hard_violations']['count'],0)
        self.assertEqual(b['capacity_overload']['active_minutes'],0)

    def test_integrity_causality_reset_reproducibility_and_failure_retention(self):
        import hashlib
        m=json.loads((self.path/'manifest.json').read_text())
        for name,sha in m['artifact_sha256'].items():self.assertEqual(hashlib.sha256((self.path/name).read_bytes()).hexdigest(),sha)
        events=[json.loads(line) for line in (self.path/'trace.jsonl').read_text().splitlines()]
        for i,row in enumerate(events):
            self.assertEqual(row['sequence_number'],i+1)
            self.assertEqual(row['causation_event_id'],events[i-1]['event_id'] if i else None)
            if i:self.assertGreaterEqual(row['simulated_at'],events[i-1]['simulated_at'])
        again=run();other=json.loads((again/'manifest.json').read_text())
        self.assertEqual(m['deterministic_trace_digest'],other['deterministic_trace_digest'])
        for before,after in zip(m['attempts'],other['attempts']):self.assertEqual(before['outcome_digest'],after['outcome_digest'])
        failed=run(iteration_cap=1)
        fm=json.loads((failed/'manifest.json').read_text())
        self.assertTrue(any(a['terminal']=='TIMED_OUT' for a in fm['attempts']))
        self.assertEqual(json.loads((failed/'aggregate.json').read_text())['eligible_case_count'],2)
        self.assertEqual(fm['product_status'],'NOT_RUN')

    def test_zero_denominators_and_missing_cannot_be_zero(self):
        cells=product_cells('r','A')
        with self.assertRaises(ValueError):Observation.model_validate({**cells[0].model_dump(),'value':0})
        path=run(cases=('no-impact',))
        metric={o['metric_id']:o for o in json.loads((path/'no-impact-naive/metrics.json').read_text())}
        self.assertIsNone(metric['preservation']['value']['rate'])
        self.assertIsNone(metric['cost']['value'])
        self.assertEqual(metric['changed_commitments']['value']['tasks'],0)
