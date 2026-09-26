"""Local harness commands; all artifacts stay under simulation/runs."""
import argparse
import json
import uuid
from pathlib import Path

from ..runner import ROOT, run_directory
from ..serialization import write_json
from .contracts import Snapshot, Outcome
from .generation import PRESETS, generate
from .runner import run
from .service import serve
from .validation import validate


def main():
    parser=argparse.ArgumentParser(description='ALTO synthetic benchmark. Product NOT_RUN.')
    parser.add_argument('command',choices=('benchmark','generate','serve','benchmark-schemas','acceptance'))
    parser.add_argument('--preset',choices=tuple(PRESETS),default='tiny')
    parser.add_argument('--seed',type=int,default=17)
    parser.add_argument('--cases',nargs='+',choices=('A','B','portfolio','impossible','revoked','no-impact','unavailable','concurrent','HR'),default=['A','B'])
    parser.add_argument('--run',type=Path)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if args.seed<0:parser.error('seed must be nonnegative')
    if args.command=='acceptance':
        from .acceptance import acceptance
        path,passed=acceptance()
        report=json.loads((path/'acceptance.json').read_text())
        print(f"Section 13.1: {report['section_13_1']}; Section 13.2: NOT_RUN")
        print(path.relative_to(ROOT));return 0 if passed else 1
    if args.command=='generate':
        snapshot=generate(args.preset,args.seed)
        out=Outcome(method='naive',classification='FEASIBLE',terminal='COMPLETED',schedule=snapshot.schedule,
                    considered_task_ids=(),iterations=0,plan_versions=0)
        report=validate(snapshot,out)
        path=run_directory(f'fixture-{args.preset}-{uuid.uuid4().hex}')
        write_json(path/'initial.json',snapshot);write_json(path/'validation.json',report)
        print(f'{args.preset}: {len(snapshot.employees)} employees, {len(snapshot.teams)} teams, {len(snapshot.tasks)} tasks, {len(report.violations)} violations')
        print(path.relative_to(ROOT));return int(bool(report.violations))
    if args.command=='benchmark-schemas':
        from . import contracts,sut,metrics,evidence
        from ..contracts import Contract
        path=run_directory(f'benchmark-schemas-{uuid.uuid4().hex}')
        count=0
        for module in (contracts,sut,metrics,evidence):
            for name,model in vars(module).items():
                if isinstance(model,type) and issubclass(model,Contract) and model is not Contract and model.__module__==module.__name__:
                    write_json(path/f'{name}.schema.json',model.model_json_schema());count+=1
        print(f'Exported {count} schemas');print(path.relative_to(ROOT));return 0
    path=args.run.resolve() if args.run else run(preset=args.preset,seed=args.seed,cases=tuple(args.cases))
    if args.command=='serve':serve(path,args.port);return 0
    manifest=json.loads((path/'manifest.json').read_text())
    print('SYNTHETIC BENCHMARK — REPLAY IS NOT A PRODUCT RESULT')
    for attempt in manifest['attempts']:
        print(f"{attempt['scenario']} / {attempt['method']}: {attempt['terminal']}, {attempt['violations']} neutral violation records")
    print('ALTO: NOT_RUN');print(path.relative_to(ROOT))
    return int(manifest['status']!='COMPLETED')
