"""SUT contracts, exact mapping and recorded replay. No product workflow logic."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field
from ..contracts import Contract
from .. import REPLAY_LABEL
from ..serialization import digest
from .contracts import Change, Outcome, Snapshot, StageStates
from .trace import Trace


class Capability(Contract):
    contract_version: Literal["sut-1"] = "sut-1"
    mode: Literal["product_replay", "coordination_engine_product"]
    label: str
    adapter_version: str
    product_commit: str | None = None
    product_version: str | None = None
    api_schema_version: str | None = None
    supported: tuple[str, ...]
    unavailable: tuple[str, ...]


class MappingReport(Contract):
    mapping_version: Literal["exact-canonical-1"] = "exact-canonical-1"
    status: Literal["EQUIVALENT", "INVALID"]
    canonical_digest: str
    mapped_digest: str
    mismatches: tuple[str, ...]
    decisions: tuple[str, ...] = ("UTC-relative 15-minute slots; no unit conversion.",
                                "Explicit source/resource grants; no access expansion.",
                                "Requested/agreed deadlines and movement freedoms retained.")


def check_mapping(canonical: dict, mapped: dict) -> MappingReport:
    """Strict reference mapper. A future API mapper must round-trip to these facts."""
    differences=[]

    def compare(a,b,path):
        if type(a)!=type(b): differences.append(path or "/");return
        if isinstance(a,dict):
            for key in sorted(set(a)|set(b)):
                if key not in a or key not in b: differences.append(path+"/"+key)
                else: compare(a[key],b[key],path+"/"+key)
        elif isinstance(a,(list,tuple)):
            if len(a)!=len(b): differences.append(path+"/length")
            for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+f"/{i}")
        elif a!=b:differences.append(path or "/")
    compare(canonical,mapped,"")
    return MappingReport(status="INVALID" if differences else "EQUIVALENT", canonical_digest=digest(canonical),
                         mapped_digest=digest(mapped), mismatches=tuple(differences))


class ResponseRequest(Contract):
    request_id: str
    actor_id: str
    kind: Literal["clarify", "approve", "acknowledge", "submit", "review"]
    exact_version: str
    proposal_digest: str | None = None
    base_revision: int | None = None
    permitted_answer: str


class ActorResponse(Contract):
    request_id: str
    actor_id: str
    exact_version: str
    answer: str
    proposal_digest: str | None = None
    base_revision: int | None = None
    policy_version: Literal["responses-1"] = "responses-1"


class CapturedProjection(Contract):
    schema_version: Literal["projection-1"] = "projection-1"
    label: Literal["REPLAY — NOT A PRODUCT RESULT"] = REPLAY_LABEL
    viewer_id: str
    role: Literal["manager", "employee"]
    permitted_source_refs: tuple[str, ...]
    brief_refs: tuple[str, ...]
    panels: dict[str, str | int | list | dict | None]
    states: StageStates = StageStates()


class ReplayFrame(Contract):
    scenario_id: str
    event_digest: str
    input_digest: str
    before_digest: str
    after_snapshot_digest: str
    requests: tuple[ResponseRequest, ...]
    observations: tuple[dict, ...]
    projections: tuple[CapturedProjection, ...]
    outcome: Outcome


class ReplayRecording(Contract):
    schema_version: Literal["sut-replay-1"] = "sut-replay-1"
    recording_version: str
    label: Literal["REPLAY — NOT A PRODUCT RESULT"] = REPLAY_LABEL
    provenance: Literal["authored_synthetic_example_not_product_capture"] = "authored_synthetic_example_not_product_capture"
    initial_digest: str
    frames: tuple[ReplayFrame, ...]


class SystemUnderTestPort(Protocol):
    def discover(self) -> Capability: ...
    def reset(self, company_id: str) -> None: ...
    def seed(self, snapshot: Snapshot) -> dict: ...
    def submit(self, event: Change, manifest: dict) -> tuple[ResponseRequest, ...]: ...
    def respond(self, response: ActorResponse) -> None: ...
    def observe(self, cursor: int = 0) -> tuple[dict, ...]: ...
    def capture(self, viewer_id: str) -> CapturedProjection: ...
    def export(self) -> Outcome: ...


class DeterministicActors:
    """Answer only exact issued requests using declared fixture permissions."""
    def __init__(self,snapshot,trace):self.actors={a.actor_id:a for a in snapshot.actors};self.trace=trace

    def answer(self,request,scenario,approach):
        actor=self.actors.get(request.actor_id)
        if actor is None or request.kind not in actor.permitted_actions:
            raise ValueError("UNSUPPORTED_ACTOR_ACTION")
        self.trace.emit("actor_response","Returned the version-bound scripted response to an issued request.",
            scenario=scenario,approach=approach,actor=actor.actor_id,role=actor.role,phase="response",
            detail={"request_id":request.request_id,"kind":request.kind,"policy_version":actor.policy_version})
        return ActorResponse(request_id=request.request_id,actor_id=request.actor_id,exact_version=request.exact_version,
                             answer=request.permitted_answer,proposal_digest=request.proposal_digest,base_revision=request.base_revision)


class RecordedReplay:
    def __init__(self,path:Path,trace:Trace):
        self.recording=ReplayRecording.model_validate_json(path.read_bytes())
        self.trace=trace;self.index=0;self.state_digest=None;self.frame=None;self.pending={};self.exported=False

    def _event(self,action,summary,**kwargs):
        self.trace.emit(action,summary,approach="product_replay",origin="replay",actor="replay-adapter",
                        role="recorded_adapter",scenario=self.frame.scenario_id if self.frame else "setup",
                        visibility=("judge_only","synthetic",REPLAY_LABEL),**kwargs)

    def discover(self):
        self._event("sut_capabilities","Discovered replay contract capabilities; real product is NOT_RUN.")
        return Capability(mode="product_replay",label=REPLAY_LABEL,adapter_version="recorded-1",api_schema_version="sut-1",
                          supported=("reset","seed","submit","respond","observe","capture","export"),
                          unavailable=("real_product","solver_internals","product_latency","live_connectors"))

    def reset(self,company_id):
        if company_id!="soraworks-synthetic":raise ValueError("RESET_SCOPE_DENIED")
        self.index=0;self.state_digest=None;self.frame=None;self.pending={};self.exported=False
        self._event("sut_reset","Reset only the in-memory replay cursor for the synthetic company.")

    def seed(self,snapshot):
        if digest(snapshot)!=self.recording.initial_digest:raise ValueError("REPLAY_SEED_MISMATCH")
        self.state_digest=digest(snapshot)
        self._event("sut_seeded","Bound replay to the exact immutable starting snapshot.",after=self.state_digest)
        return {"mode":"product_replay","input_digest":self.state_digest}

    def submit(self,event,manifest):
        if self.frame is not None and not self.exported:raise ValueError("PREVIOUS_FRAME_NOT_EXPORTED")
        if self.index>=len(self.recording.frames):raise ValueError("REPLAY_FRAME_UNAVAILABLE")
        frame=self.recording.frames[self.index]
        if (frame.scenario_id!=event.scenario_id or frame.event_digest!=digest(event) or
            frame.input_digest!=digest(manifest) or frame.before_digest!=self.state_digest):
            raise ValueError("REPLAY_INPUT_MISMATCH")
        self.frame=frame;self.pending={r.request_id:r for r in frame.requests};self.exported=False
        self._event("change_received","Loaded the exact recorded scenario frame; no product request executed.",before=self.state_digest)
        return frame.requests

    def respond(self,response):
        request=self.pending.get(response.request_id)
        if request is None:raise ValueError("UNISSUED_OR_DUPLICATE_RESPONSE")
        expected={k:v for k,v in request.model_dump().items() if k not in ("kind","permitted_answer")}
        actual={k:v for k,v in response.model_dump().items() if k not in ("answer","policy_version")}
        if expected!=actual or response.answer!=request.permitted_answer:raise ValueError("RESPONSE_BINDING_MISMATCH")
        del self.pending[response.request_id]
        self._event("replay_response_matched","Matched the response to the recorded actor, version and digest.")

    def observe(self,cursor=0):
        if self.frame is None:raise ValueError("NO_REPLAY_FRAME")
        if cursor<0 or cursor>len(self.frame.observations):raise ValueError("INVALID_CURSOR")
        rows=self.frame.observations[cursor:]
        for r in rows:
            self._event("replay_observation",r["summary"],detail={"recorded_event_id":r["event_id"],"recording_version":self.recording.recording_version,
                                                              "observed_state":r.get("state","NOT_AVAILABLE")})
        return rows

    def capture(self,viewer_id):
        if self.frame is None:raise ValueError("NO_REPLAY_FRAME")
        projection=next((p for p in self.frame.projections if p.viewer_id==viewer_id),None)
        if projection is None:raise ValueError("PROJECTION_UNAVAILABLE")
        self._event("projection_captured","Captured a stored, explicitly permitted replay POV.",detail={"viewer_id":viewer_id})
        return projection

    def export(self):
        if self.frame is None or self.pending:raise ValueError("REPLAY_NOT_TERMINAL")
        if self.exported:raise ValueError("FRAME_ALREADY_EXPORTED")
        self.state_digest=self.frame.after_snapshot_digest;self.index+=1;self.exported=True
        self._event("terminal_exported","Exported recorded evidence verbatim; product performance stays NOT_RUN.",after=self.state_digest)
        return self.frame.outcome


class ProductUnavailable:
    """Deliberately unavailable until a supported real FastAPI test boundary exists."""
    def discover(self):
        return Capability(mode="coordination_engine_product",label="NOT_RUN",adapter_version="NOT IMPLEMENTED",
                          supported=(),unavailable=("synthetic_seed_reset","scenario_submission","actor_responses",
                                                   "progress_observation","role_projections","terminal_export"))

    def reset(self,*args,**kwargs):raise NotImplementedError("NOT_RUN: supported synthetic tenant reset required")
    def seed(self,*args,**kwargs):raise NotImplementedError("NOT_RUN: supported synthetic tenant import required")
    def submit(self,*args,**kwargs):raise NotImplementedError("NOT_RUN: supported scenario submission required")
    def respond(self,*args,**kwargs):raise NotImplementedError("NOT_RUN: supported actor actions required")
    def observe(self,*args,**kwargs):raise NotImplementedError("NOT_AVAILABLE: product progress evidence required")
    def capture(self,*args,**kwargs):raise NotImplementedError("NOT_AVAILABLE: authorised product projections required")
    def export(self,*args,**kwargs):raise NotImplementedError("NOT_AVAILABLE: product terminal evidence required")
