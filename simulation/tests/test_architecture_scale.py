import ast
import json
import unittest
from pathlib import Path

from coordination_sim.benchmark.generation import generate
from coordination_sim.benchmark.contracts import Outcome
from coordination_sim.benchmark.metrics import registry
from coordination_sim.benchmark.validation import validate
from coordination_sim.serialization import digest


class ArchitectureScaleTests(unittest.TestCase):
    def test_registry_export_drift(self):
        self.assertEqual(json.loads(Path('metrics/registry.v2.json').read_text()),registry())

    def test_no_product_modules_or_planner_dependencies(self):
        forbidden={'coordination','z3','supabase','google','fastapi','sqlalchemy'}
        forbidden_functions={'compile_model','solve_insertion','solve_repair','commit_plan','run_outbox','update_employee_skills'}
        for path in Path('coordination_sim').rglob('*.py'):
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.ImportFrom):self.assertNotIn((node.module or '').split('.')[0],forbidden,path)
                if isinstance(node,ast.Import):
                    for name in node.names:self.assertNotIn(name.name.split('.')[0],forbidden,path)
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):self.assertNotIn(node.name,forbidden_functions,path)
                if path.name=='sut.py' and isinstance(node,ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[-1],{'naive','validation','scoring'},path)

    def test_medium_initial_fixture_regression(self):
        s=generate('medium')
        self.assertEqual((len(s.employees),len(s.teams),len(s.tasks)),(100,10,350))
        o=Outcome(method='naive',classification='FEASIBLE',terminal='COMPLETED',schedule=s.schedule,considered_task_ids=(),iterations=0,plan_versions=0)
        self.assertEqual(validate(s,o).violations,())
        self.assertEqual(digest(s),digest(generate('medium')))

    def test_no_prohibited_profile_fields_or_credentials(self):
        snapshot=generate().model_dump(mode='json')
        forbidden={'personality','loyalty','salary','health','demographic','work_ethic','productivity_score','global_rank','bearer_token','api_key','private_reason','subject'}
        def inspect(value):
            if isinstance(value,dict):
                self.assertFalse(forbidden&set(value))
                for v in value.values():inspect(v)
            if isinstance(value,list):
                for v in value:inspect(v)
        inspect(snapshot)

    def test_unknown_case_retains_failed_manifest(self):
        from coordination_sim.benchmark.runner import run
        path=run(cases=('unknown-case',))
        manifest=json.loads((path/'manifest.json').read_text())
        self.assertEqual(manifest['status'],'FAILED')
        self.assertEqual(manifest['product_status'],'NOT_RUN')
