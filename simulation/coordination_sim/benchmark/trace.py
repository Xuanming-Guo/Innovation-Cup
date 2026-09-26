"""Append-only factual observer events; no hidden actor/model reasoning."""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contracts import Company
from ..serialization import canonical, digest


class Trace:
    def __init__(self, run_id: str, company: Company, path: Path | None = None):
        self.run_id, self.company, self.path = run_id, company, path
        self.rows = []
        self.current_slot = 0
        if path is not None:
            path.open("xb").close()

    def emit(self, action, summary, *, scenario="setup", approach="naive", origin="harness",
             actor="observer", role="benchmark", phase="observation", status="succeeded", at=0,
             refs=(), sources=(), inputs=(), outputs=(), before=None, after=None, detail=None,
             visibility=("judge_only", "synthetic"), error=None):
        sequence=len(self.rows)+1
        at=max(at,self.current_slot)
        self.current_slot=at
        row={"schema_version":"benchmark-2", "event_id":f"event-{sequence:06}", "run_id":self.run_id,
             "scenario_id":scenario, "approach":approach, "event_origin":origin, "sequence_number":sequence,
             "simulated_at":(self.company.anchor.astimezone(timezone.utc)+timedelta(minutes=at*15)).isoformat(),
             "recorded_at":datetime.now(timezone.utc).isoformat(), "correlation_id":f"{approach}:{scenario}",
             "causation_event_id":self.rows[-1]["event_id"] if self.rows else None,
             "actor_id":actor, "actor_type":"workspace" if origin=="workspace_fixture" else "synthetic_actor",
             "actor_role":role,"actor_scope_refs":[self.company.company_id],"action_type":action,
             "phase":phase,"status":status,"summary":summary,"input_refs":list(inputs),"output_refs":list(outputs),
             "source_version_refs":list(sources),"constraint_refs":[],"authorization_basis_refs":["synthetic-benchmark-scope"],
             "affected_entity_refs":list(refs),"state_before_hash":before,"state_after_hash":after,
             "duration_ms":None,"error_code":error,"error_summary":error,"visibility_labels":list(visibility),
             "detail":detail or {}}
        if self.path:
            with self.path.open("ab") as f: f.write(canonical(row)+b"\n")
        self.rows.append(row)
        return row["event_id"]

    def semantic_digest(self):
        return digest([{k:v for k,v in r.items() if k not in ("run_id","recorded_at","duration_ms")} for r in self.rows])

    def export(self, folder):
        with (folder/"timeline.txt").open("x",encoding="utf-8") as f:
            for r in self.rows: f.write(f"{r['sequence_number']:06} {r['approach']} / {r['scenario_id']} / {r['action_type']}: {r['summary']}\n")
        keys=("event_id","scenario_id","approach","actor_id","actor_role","phase","action_type","status","simulated_at","summary")
        with (folder/"events.csv").open("x",newline="",encoding="utf-8") as f:
            writer=csv.DictWriter(f,fieldnames=keys,extrasaction="ignore");writer.writeheader();writer.writerows(self.rows)
