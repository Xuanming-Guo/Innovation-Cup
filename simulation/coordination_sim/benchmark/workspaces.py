"""Deterministic external-provider fixtures, not product connector ingestion."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .contracts import Grant, Source, Snapshot
from .trace import Trace
from ..serialization import digest


@dataclass(frozen=True)
class ReadResult:
    status: str
    records: tuple[dict, ...] = ()
    next_cursor: int | None = None
    mode: str = "simulated"


class WorkspaceEnvironmentPort(Protocol):
    def capabilities(self) -> dict: ...
    def read(self, company_id: str, principal_id: str, resource_ids: tuple[str, ...], *, fields: tuple[str, ...], now: datetime, cursor: int = 0) -> ReadResult: ...


class SimulatedWorkspace:
    """A provider owns its source objects, grants, scripted failures and versions."""
    def __init__(self, provider: str, snapshot: Snapshot, trace: Trace, scenario="setup", approach="naive", page_size=2):
        self.provider, self.company_id, self.trace = provider, snapshot.company.company_id, trace
        self.scenario, self.approach, self.page_size = scenario, approach, page_size
        self.objects = {s.source_id:s for s in snapshot.sources if s.provider==provider}
        self.grants = snapshot.grants
        self.unavailable=False
        self.throttle_once=False
        self.deliveries=set()
        self.receipts={}
        self.effects={}
        self.script={}
        self.committed_evidence={}  # External fixture expectations, never product state.

    def _event(self, action, summary, status="succeeded", **detail):
        self.trace.emit(action,summary,scenario=self.scenario,approach=self.approach,origin="workspace_fixture",
                        actor=f"sim-{self.provider}",role="simulated_provider",phase="workspace",status=status,
                        detail={"mode":"simulated",**detail})

    def capabilities(self):
        result={"schema_version":"workspace-1","provider":self.provider,"mode":"simulated",
                "reads":["bounded_fields","excerpt","incremental"],
                "writes":["update"] if self.provider in ("planner","calendar") else [],
                "conditional_version":True,"idempotency":True,"page_size":self.page_size}
        self._event("workspace_capabilities","Discovered simulated provider capabilities.")
        return result

    def _allowed(self,cid,principal,source,action,now):
        return (cid==self.company_id and source.company_id==cid and not source.revoked and
                any(g.company_id==cid and g.principal_id==principal and g.connection_id==source.connection_id and
                    g.resource_id==source.source_id and action in g.actions and not g.revoked and g.expires_at>now for g in self.grants))

    def read(self, company_id, principal_id, resource_ids, *, fields, now, cursor=0):
        # Permission-safe failures reveal neither existence nor private resource names.
        selected=[self.objects.get(sid) for sid in resource_ids]
        if any(s is None or not self._allowed(company_id,principal_id,s,"read",now) for s in selected):
            self._event("source_authorized","Scoped read denied; no source content returned.","failed",code="DENIED")
            return ReadResult("DENIED")
        self._event("source_authorized","Company, connection, principal and resource grants checked.")
        if self.unavailable:
            self._event("source_retrieved","Provider availability is unknown.","failed",code="UNAVAILABLE")
            return ReadResult("UNAVAILABLE")
        if self.throttle_once:
            self.throttle_once=False
            self._event("source_retrieved","Scripted provider throttle; retry remains bounded.","failed",code="THROTTLED")
            return ReadResult("THROTTLED")
        if cursor<0 or cursor>len(selected):
            raise ValueError("invalid cursor")
        if any(s.freshness!="current" or s.expires_at<=now for s in selected):
            self._event("source_retrieved","Source freshness is insufficient.","failed",code="STALE")
            return ReadResult("STALE")
        if not set(fields)<= {"fields","excerpt"}:
            raise ValueError("unsupported bounded field projection")
        records=[]
        seen=set()
        for s in selected[cursor:cursor+self.page_size]:
            # Imported owned exports are reduced to mappings; no extra capacity block.
            if s.internal_block_ref and s.internal_block_ref in seen: continue
            if s.internal_block_ref: seen.add(s.internal_block_ref)
            row={k:getattr(s,k) for k in ("source_id","company_id","provider","connection_id","external_id","version","classification","authoritative_for","origin","internal_block_ref","mode")}
            row.update(retrieved_at=s.retrieved_at.isoformat(),expires_at=s.expires_at.isoformat(),freshness=s.freshness)
            for field in fields:
                if self.provider=="calendar":
                    row[field] = {k:v for k,v in s.fields.items() if k in ("known","start_slot","end_slot","employee_id")} if field=="fields" else "Opaque capacity; private title and reason omitted."
                else:
                    row[field]=getattr(s,field)
            records.append(row)
        end=cursor+self.page_size
        self._event("source_retrieved","Returned bounded authorised simulated records.",count=len(records),cursor=cursor,
                    source_versions=[f"{s.source_id}@{s.version}" for s in selected[cursor:end]])
        return ReadResult("OK",tuple(records),end if end<len(selected) else None)

    def revoke(self, resource_id):
        if resource_id not in self.objects: raise ValueError("unknown fixture resource")
        self.objects[resource_id]=self.objects[resource_id].model_copy(update={"revoked":True})
        self._event("source_revoked","Fixture grant/source revoked; later reads denied.")

    def poll(self, deliveries):
        unique=[]
        for delivery_id, resource_id in deliveries:
            duplicate=delivery_id in self.deliveries
            self._event("provider_event","Observed simulated incremental delivery.",duplicate=duplicate,delivery_id=delivery_id)
            if not duplicate:
                self.deliveries.add(delivery_id)
                unique.append((delivery_id,resource_id))
        return tuple(unique)

    def write(self, *, company_id, principal_id, resource_id, expected_version, idempotency_key, fields, proposal_digest, committed_revision, now):
        source=self.objects.get(resource_id)
        request=digest({"resource":resource_id,"fields":fields,"version":expected_version,
                        "proposal":proposal_digest,"revision":committed_revision})
        status="DENIED"
        if (source and self.provider in ("planner","calendar") and self._allowed(company_id,principal_id,source,"write",now)
            and self.committed_evidence.get(proposal_digest)==committed_revision):
            prior=self.receipts.get(idempotency_key)
            if prior:
                status="IDEMPOTENT" if prior[0]==request else "KEY_CONFLICT"
            elif source.version!=expected_version:
                status="STALE_VERSION"
            else:
                status=self.script.get(resource_id,"SUCCESS")
                if status in ("SUCCESS","TIMEOUT_AFTER_WRITE"):
                    version=str(int(source.version)+1)
                    self.objects[resource_id]=source.model_copy(update={"version":version,"fields":{**source.fields,**fields}})
                    self.effects[idempotency_key]={"resource_id":resource_id,"version":version,"fields":fields}
                    self.receipts[idempotency_key]=(request,self.effects[idempotency_key])
        self._event("external_action_attempted","Simulated provider returned a scripted write outcome.",
                    "succeeded" if status in ("SUCCESS","IDEMPOTENT") else "failed",outcome=status)
        return {"mode":"simulated","status":status,"effect":self.effects.get(idempotency_key) if status in ("SUCCESS","IDEMPOTENT") else None}

    def reconcile(self,idempotency_key):
        self._event("external_action_reconciled","Read the simulated provider effect after an uncertain response.")
        return self.effects.get(idempotency_key)


def environments(snapshot,trace,**kwargs):
    return {p:SimulatedWorkspace(p,snapshot,trace,**kwargs) for p in ("teams","calendar","planner","sharepoint","github")}


def authorised_manifest(snapshot, event, trace, approach):
    """Canonical safe fixture import; provider payload shape stops at this boundary."""
    providers=environments(snapshot,trace,scenario=event.scenario_id,approach=approach,page_size=100)
    required=set(event.source_refs)|{"working-rules-v1","opaque-capacity-v1","policy-v1"}
    required.update(t.source_ref for t in snapshot.tasks if t.task_id in event.task_ids)
    # Both methods receive the identical canonical snapshot, including bounded
    # per-project structured records. No raw private calendar data exists in it.
    records=[]
    from .generation import instant
    for provider in providers.values():
        provider.capabilities()
        ids=tuple(sorted(sid for sid in required if sid in provider.objects))
        if not ids: continue
        cursor=0
        while True:
            result=provider.read(snapshot.company.company_id,"coordinator",ids,fields=("fields","excerpt"),now=instant(snapshot.company,event.at_slot),cursor=cursor)
            records.extend(result.records)
            if result.status!="OK" or result.next_cursor is None: break
            cursor=result.next_cursor
    return {"schema_version":"mapping-1","snapshot":snapshot.model_dump(mode="json"),
            "event":event.model_dump(mode="json"),"workspace_records":records,
            "connector_modes":{p:"simulated" for p in providers}}
