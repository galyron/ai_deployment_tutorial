from acnt_strat_synth.graph.state import GraphState, EvidenceItem
from acnt_strat_synth.retrieval.search import retrieve
from acnt_strat_synth.predict.tool import account_risk_score

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from acnt_strat_synth.graph.state import Synthesis
from acnt_strat_synth.config import settings

import uuid

QUERIES = [
    "prescribing trends and brand loyalty",
    "competitive pressure and alternative therapies",
    "rep relationship and access dynamics",
    "market dynamics for this specialty",
]

_llm_synth = AzureChatOpenAI(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    # gpt-5-mini fixes temperature at 1 (same as the o-series reasoning models).
    azure_deployment=settings.chat_deployment, temperature=1,
).with_structured_output(Synthesis)

SYNTH_SYSTEM = """
You will receive: an HCP account ID, a predicted risk score, and and a numbered list of evidence chunks, each tagged with chunk_id and source type.
Produce a Synthesis with:
- A one-sentence headline
- 3-5 claims structured as Claim objects. Each Claim.cites MUST list one ore more chunk_idsfrom the evidence. Beverr cite a chunk you were not given. If a claim is derived solely from the risk score, cite the special id 'PREDICT'
- A concrete next_best_action
- competitive_risk_flag=true if any cited evidence describes competitive pressure
Be concise. No filler. No side-tracking.
"""


def extract_node(state: GraphState) -> GraphState:
    acnt = state["account_id"]
    seen: dict[str, EvidenceItem] = {}

    for q in QUERIES:
        for hit in retrieve(acnt, q, k=4):
            key = hit.text[:60] # cheap dedupe; chunk_id isn't returned by retrieve
            if key in seen:
                continue
            seen[key] = EvidenceItem(
                chunk_id=f"E-{len(seen)+1:03d}",
                account_id=hit.account_id,
                source_type=hit.source_type,
                text=hit.text,
            )
    return {**state, "evidence": list(seen.values())}

def score_node(state: GraphState) -> GraphState:
    out = account_risk_score.invoke({"account_id": state["account_id"]})
    return {**state, "score": out}

def synth_node(state):
    ev_block = "\n".join(
        f"[{e.chunk_id}] ({e.source_type}) {e.text}" for e in state["evidence"]
    ) or "(no qualitiative evidence available for this account)"

    user_qry = (
        f"account_id: {state['account_id']}\n"
        f"risk_score: {state['score']['risk_score']}\n"
        f"features: {state['score']['features']}\n"
        f"evidence:\n{ev_block}"
    )

    out: Synthesis = _llm_synth.invoke([SystemMessage(SYNTH_SYSTEM), HumanMessage(user_qry)])
    out.account_id = state["account_id"]
    out.risk_score = state["score"]["risk_score"]

    return {**state, "synthesis": out}