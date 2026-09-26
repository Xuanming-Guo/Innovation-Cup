import json
import unittest
from pathlib import Path

from coordination_sim.benchmark.runner import run


class GoldenTests(unittest.TestCase):
    def test_all_eight_reviewed_cases_and_all_primary_aspects(self):
        pack=json.loads(Path('evals/golden.v1.json').read_text())
        self.assertEqual(len(pack['cases']),8)
        connected=run()
        for case in pack['cases']:
            path=connected if case['id'] in ('A','B') else run(cases=(case['id'],))
            folder=path/f"{case['id']}-naive"
            outcome=json.loads((folder/'outcome.json').read_text())
            self.assertEqual((outcome['classification'],outcome['terminal']),(case['expected'],case['terminal']),case['id'])
            metrics={o['metric_id']:o for o in json.loads((folder/'metrics.json').read_text())}
            for field,expected in case['checks'].items():
                parts=field.split('.');value=metrics[parts[0]]['value']
                for key in parts[1:]:value=value[key]
                self.assertEqual(value,expected,(case['id'],field))
            for mid,status in case['statuses'].items():self.assertEqual(metrics[mid]['status'],status,(case['id'],mid))
            if metrics['planning_latency']['status']=='MEASURED':
                for value in metrics['planning_latency']['value']['stage_ms'].values():self.assertGreaterEqual(value,0)
        covered={field.split('.')[0] for c in pack['cases'] for field in (*c['checks'],*c['statuses'])}
        from coordination_sim.benchmark.metrics import PRIMARY
        self.assertTrue(set(PRIMARY)<=covered)
