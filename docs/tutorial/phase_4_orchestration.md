# Phase 4 — Agentic Orchestration

**Capabilities touched:** agentic workflow design, multi-agent systems, orchestration + state, human-in-the-loop switch.
**Exit criterion:** A LangGraph run produces a structured synthesis for any account, with every claim citing a retrieved chunk; flipping `review_required=True` pauses the graph at the synthesis step.
**Budget:** 2–2.5h. **This phase is protected — do not cut.**

---

### Step 4.1 — Define the graph state

**Goal:** A single TypedDict that every node reads from and writes to. State carries the account ID, retrieved evidence, the predictive score, the synthesis output, and the HITL flag.

**Do:**

- Create `src/acnt_strat_synth/graph/state.py`.
- Define `EvidenceItem` (matches the retrieval contract), `Synthesis` (the structured output we want), and `GraphState`.

**Code / commands:**

```bash
mkdir -p src/acnt_strat_synth/graph
touch src/acnt_strat_synth/graph/__init__.py
```

```python
# src/acnt_strat_synth/graph/state.py
from typing import TypedDict, Optional
from pydantic import BaseModel, Field

class EvidenceItem(BaseModel):
    chunk_id: str
    account_id: str
    source_type: str
    text: str

class Claim(BaseModel):
    statement: str
    cites: list[str] = Field(description="chunk_id values that support this statement; at least one")

class Synthesis(BaseModel):
    account_id: str
    headline: str
    claims: list[Claim]
    next_best_action: str
    competitive_risk_flag: bool
    risk_score: float

class GraphState(TypedDict, total=False):
    account_id: str
    evidence: list[EvidenceItem]
    score: Optional[dict]
    synthesis: Optional[Synthesis]
    review_required: bool
    approved: Optional[bool]
```

**Self-check:**

```bash
uv run python -c "from acnt_strat_synth.graph.state import GraphState, Synthesis; print(Synthesis.model_fields.keys())"
# Expected: dict_keys(['account_id','headline','claims','next_best_action','competitive_risk_flag','risk_score'])
```

**If broken:**

- `ImportError` for `TypedDict` → use `from typing import TypedDict` (Python 3.12 supports it directly).

**Time estimate:** ~15m.

---

### Step 4.2 — The Extract node

**Goal:** Pull qualitative evidence for the target account and stash it on state with chunk IDs.

**Do:**

- Implement `extract_node(state)`.
- Query the index with several topic-y queries to cover the four source types, dedupe by `chunk_id`.

**Code / commands:**

```python
# src/acnt_strat_synth/graph/nodes.py
from acnt_strat_synth.graph.state import GraphState, EvidenceItem
from acnt_strat_synth.retrieval.search import retrieve
import uuid

QUERIES = [
    "prescribing trends and brand loyalty",
    "competitive pressure and alternative therapies",
    "rep relationship and access dynamics",
    "market dynamics for this specialty",
]

def extract_node(state: GraphState) -> GraphState:
    acnt = state["account_id"]
    seen: dict[str, EvidenceItem] = {}
    for q in QUERIES:
        for hit in retrieve(acnt, q, k=4):
            key = hit.text[:60]  # cheap dedupe; chunk_id isn't returned by retrieve
            if key in seen:
                continue
            seen[key] = EvidenceItem(
                chunk_id=f"E-{len(seen)+1:03d}",
                account_id=hit.account_id,
                source_type=hit.source_type,
                text=hit.text,
            )
    return {**state, "evidence": list(seen.values())}
```

**Self-check:**

```bash
uv run python - <<'PY'
from acnt_strat_synth.graph.nodes import extract_node
s = extract_node({"account_id": "HCP-002"})
print(len(s["evidence"]), "items")
print({e.source_type for e in s["evidence"]})
PY
```

At least 2 evidence items; `source_type` set includes `comp_intel`.

**If broken:**

- 0 items → run `uv run python scripts/check_traceability.py` to confirm the index is populated.

**Time estimate:** ~15m.

---

### Step 4.3 — The Score node

**Goal:** Call the predictive tool from Phase 3 and stash the result on state. No LLM here — the agent doesn't get to "decide" the number.

**Code / commands:**

```python
# src/acnt_strat_synth/graph/nodes.py  (append)
from acnt_strat_synth.predict.tool import account_risk_score

def score_node(state: GraphState) -> GraphState:
    out = account_risk_score.invoke({"account_id": state["account_id"]})
    return {**state, "score": out}
```

**Self-check:**

```bash
uv run python -c "from acnt_strat_synth.graph.nodes import score_node; print(score_node({'account_id':'HCP-001'})['score'])"
# Expected dict with risk_score, features
```

**If broken:**

- `KeyError` → account ID typo; valid IDs are `HCP-001` through `HCP-050`.

**Time estimate:** ~10m.

---

### Step 4.4 — The Synthesis node (structured output + citations)

**Goal:** GPT-4o emits a `Synthesis` object where every `Claim.cites` references a real `EvidenceItem.chunk_id` from state. This is the traceability proof.

**Do:**

- Use `with_structured_output(Synthesis)` to constrain the output.
- Pass evidence as a numbered list keyed by `chunk_id`.
- The prompt makes citation mandatory.

**Code / commands:**

```python
# src/acnt_strat_synth/graph/nodes.py  (append)
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from acnt_strat_synth.graph.state import Synthesis
from acnt_strat_synth.config import settings

_llm_synth = AzureChatOpenAI(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    # gpt-5-mini fixes temperature at 1 (same as the o-series reasoning models).
    # If you deploy a classic chat model instead, drop this to 0.2 for tighter output.
    azure_deployment=settings.chat_deployment, temperature=1,
).with_structured_output(Synthesis)

SYNTH_SYSTEM = """You are an account-strategy synthesist.
You will receive: an HCP account ID, a predictive risk score, and a numbered list of evidence chunks each tagged with chunk_id and source_type.
Produce a Synthesis with:
- A one-sentence headline.
- 3-5 Claims. Each Claim.cites MUST list one or more chunk_ids from the evidence. Never cite a chunk you were not given. If a claim is derived solely from the risk score, cite the special id 'PREDICT'.
- A concrete next_best_action.
- competitive_risk_flag=true if any cited evidence describes competitive pressure.
Be concise. No filler."""

def synth_node(state):
    ev_block = "\n".join(
        f"[{e.chunk_id}] ({e.source_type}) {e.text}" for e in state["evidence"]
    ) or "(no qualitative evidence available for this account)"
    user = (
        f"account_id: {state['account_id']}\n"
        f"risk_score: {state['score']['risk_score']}\n"
        f"features: {state['score']['features']}\n"
        f"evidence:\n{ev_block}"
    )
    out: Synthesis = _llm_synth.invoke([SystemMessage(SYNTH_SYSTEM), HumanMessage(user)])
    out.account_id = state["account_id"]
    out.risk_score = state["score"]["risk_score"]
    return {**state, "synthesis": out}
```

**Self-check:**

```bash
uv run python - <<'PY'
from acnt_strat_synth.graph.nodes import extract_node, score_node, synth_node
s = extract_node({"account_id": "HCP-002"})
s = score_node(s)
s = synth_node(s)
syn = s["synthesis"]
chunk_ids = {e.chunk_id for e in s["evidence"]} | {"PREDICT"}
bad = [c for c in syn.claims if not set(c.cites) <= chunk_ids]
print(syn.headline)
print("claims:", len(syn.claims), "ungrounded:", len(bad))
assert not bad, bad
PY
```

Headline prints; ungrounded count is `0`.

**If broken:**

- `ungrounded != 0` → the model invented chunk IDs. Tighten the SYSTEM message: "If a chunk_id is not in the provided list, your output will be rejected."
- `with_structured_output` errors → upgrade `langchain-openai`; older versions used `function_calling` mode that didn't enforce strictly.
- `BadRequestError: 'temperature' does not support 0.2 with this model` → you're on gpt-5-mini (or another reasoning model) and left `temperature=0.2`. Set `temperature=1`; you can't tune the sampler on these models.

**Time estimate:** ~20m.

---

### Step 4.5 — Wire the LangGraph graph

**Goal:** A compiled graph: `extract → score → synth → END`, with a checkpointer so we can pause and resume in the next steps.

**Do:**

- Create `src/acnt_strat_synth/graph/build.py`.
- Use `MemorySaver` for the in-process checkpointer.

**Code / commands:**

```python
# src/acnt_strat_synth/graph/build.py
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from acnt_strat_synth.graph.state import GraphState
from acnt_strat_synth.graph.nodes import extract_node, score_node, synth_node

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("extract", extract_node)
    g.add_node("score",   score_node)
    g.add_node("synth",   synth_node)
    g.add_edge(START, "extract")
    g.add_edge("extract", "score")
    g.add_edge("score", "synth")
    g.add_edge("synth", END)
    return g.compile(checkpointer=MemorySaver(), interrupt_before=["synth"])
```

**Self-check:**

```bash
uv run python -c "from acnt_strat_synth.graph.build import build_graph; g = build_graph(); print(g.get_graph().draw_ascii())"
```

Prints an ASCII diagram with `extract` → `score` → `synth` → `__end__`.

**If broken:**

- `draw_ascii` requires `grandalf`; install with `uv add grandalf` or skip the visualization and just print `g.nodes`.

**Time estimate:** ~15m.

---

### Step 4.6 — Single-account end-to-end run (autonomous mode)

**Goal:** Run the graph through to completion when `review_required=False`. This is the autonomous path.

**Do:**

- Build the graph, invoke for `HCP-002` with a thread ID, pre-approve the interrupt by passing `approved=True`.

**Code / commands:**

```python
# scripts/run_one.py
from acnt_strat_synth.graph.build import build_graph

g = build_graph()
cfg = {"configurable": {"thread_id": "demo-1"}}

state = g.invoke({"account_id": "HCP-002", "review_required": False}, config=cfg)
# In autonomous mode we step past the interrupt unconditionally:
state = g.invoke(None, config=cfg)
syn = state["synthesis"]
print("HEADLINE:", syn.headline)
print("RISK:", syn.risk_score, "FLAG:", syn.competitive_risk_flag)
print("NBA:", syn.next_best_action)
for c in syn.claims:
    print(" -", c.statement, "  cites:", c.cites)
```

```bash
uv run python scripts/run_one.py
```

**Self-check:** Output shows a non-empty headline, a risk score between 0 and 1, 3–5 claims each with at least one `cites` entry.

**If broken:**

- `interrupt_before` is active for both autonomous and HITL paths — the second `g.invoke(None, config=cfg)` is required to step past it. If you skip it, `state["synthesis"]` will be `None`.

**Time estimate:** ~15m.

---

### Step 4.7 — Make the HITL switch real

**Goal:** When `review_required=True`, the graph pauses before synthesis and waits for `approved` on state. When `False`, it proceeds unconditionally.

**Do:**

- Replace the unconditional interrupt with a conditional gate: a tiny `gate_node` between `score` and `synth` that decides whether to interrupt.

**Code / commands:**

```python
# src/acnt_strat_synth/graph/build.py  (replace previous build_graph)
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from acnt_strat_synth.graph.state import GraphState
from acnt_strat_synth.graph.nodes import extract_node, score_node, synth_node

def _gate(state: GraphState):
    if state.get("review_required") and not state.get("approved"):
        return "wait"
    return "go"

def _wait_node(state: GraphState) -> GraphState:
    # Pause point: graph interrupts here.
    return state

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("extract", extract_node)
    g.add_node("score",   score_node)
    g.add_node("wait",    _wait_node)
    g.add_node("synth",   synth_node)

    g.add_edge(START, "extract")
    g.add_edge("extract", "score")
    g.add_conditional_edges("score", _gate, {"wait": "wait", "go": "synth"})
    g.add_edge("wait", "synth")
    g.add_edge("synth", END)
    return g.compile(checkpointer=MemorySaver(), interrupt_before=["wait"])
```

```python
# scripts/run_one.py  (replace)
from acnt_strat_synth.graph.build import build_graph

g = build_graph()
cfg = {"configurable": {"thread_id": "auto-1"}}

# Autonomous: no interrupt because gate routes to 'go'.
state = g.invoke({"account_id": "HCP-002", "review_required": False}, config=cfg)
print("autonomous synthesis present:", state.get("synthesis") is not None)
```

```bash
uv run python scripts/run_one.py
```

**Self-check:** Prints `autonomous synthesis present: True`.

**If broken:**

- `True` is unexpectedly `False` → `interrupt_before=["wait"]` triggers even when the gate routes to `go`. Replace with `interrupt_before=[]` and use the `wait` node's interrupt semantics implicitly — LangGraph only interrupts before nodes that are actually scheduled.

**Time estimate:** ~20m.

---

### Step 4.8 — Pause and resume with a review toggle

**Goal:** When `review_required=True`, the graph stops at `wait`. A second invocation with `approved=True` completes the synthesis.

**Do:**

- Run twice with the same `thread_id`. First call produces no synthesis; second call (with `approved=True`) does.

**Code / commands:**

```python
# scripts/run_hitl.py
from acnt_strat_synth.graph.build import build_graph

g = build_graph()
cfg = {"configurable": {"thread_id": "hitl-1"}}

# First invocation: pauses at wait.
state_1 = g.invoke({"account_id": "HCP-001", "review_required": True}, config=cfg)
print("pause: synthesis is", state_1.get("synthesis"))
print("next nodes:", g.get_state(cfg).next)

# Approve and resume.
g.update_state(cfg, {"approved": True})
state_2 = g.invoke(None, config=cfg)
print("resume: headline =", state_2["synthesis"].headline)
```

```bash
uv run python scripts/run_hitl.py
```

**Self-check:**

- First print: `pause: synthesis is None`
- `next nodes:` shows `('wait',)`.
- Second print: a non-empty `headline` from the synthesis.

**If broken:**

- Second invocation re-runs from start → `thread_id` differs; reuse the same config dict.
- `get_state(cfg).next` is empty → the checkpointer wasn't passed in `compile()`.

**Time estimate:** ~15m.

---

### Step 4.9 — Batch run over all accounts

**Goal:** A loop over `HCP-001..HCP-050` that produces a synthesis (or `None` for the graceful-degradation case) per account.

**Do:**

- Run autonomously; persist results as JSONL for Phase 5.

**Code / commands:**

```python
# scripts/run_batch.py
import json
from pathlib import Path
from acnt_strat_synth.graph.build import build_graph
from acnt_strat_synth.data.loader import load_quant

g = build_graph()
ids = sorted(q.account_id for q in load_quant())

out = []
for aid in ids:
    cfg = {"configurable": {"thread_id": f"batch-{aid}"}}
    s = g.invoke({"account_id": aid, "review_required": False}, config=cfg)
    syn = s.get("synthesis")
    out.append({
        "account_id": aid,
        "headline": syn.headline if syn else None,
        "claims": [c.model_dump() for c in syn.claims] if syn else [],
        "next_best_action": syn.next_best_action if syn else None,
        "competitive_risk_flag": syn.competitive_risk_flag if syn else False,
        "risk_score": syn.risk_score if syn else None,
        "evidence_ids": [e.chunk_id for e in s.get("evidence", [])],
    })
    print(aid, "done")

Path("data/syntheses.jsonl").write_text("\n".join(json.dumps(o) for o in out))
print("wrote", len(out), "syntheses")
```

```bash
uv run python scripts/run_batch.py
```

**Self-check:**

```bash
uv run python - <<'PY'
import json
rows = [json.loads(l) for l in open("data/syntheses.jsonl")]
assert len(rows) == 50
got = sum(1 for r in rows if r["headline"])
print("with synthesis:", got, "without:", 50 - got)
# Expected: at least 49 with synthesis (HCP-005 may still get one off the score alone)
PY
```

At least 49 syntheses present.

**If broken:**

- All HCP-005 fields are `None` → that's expected only if you chose to skip synthesis when evidence is empty. The reference implementation still calls synth; the synth prompt handles the "no evidence" branch and produces a score-only synthesis citing `PREDICT`.

**Time estimate:** ~15m.

---

Phase 4 done. The graph runs autonomously, pauses on demand, and writes 50 structured syntheses to disk. Commit: `git add -A && git commit -m "phase 4: langgraph orchestration with HITL gate"`.