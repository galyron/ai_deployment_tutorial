import json
from pathlib import Path
from acnt_strat_synth.graph.build import build_graph
from acnt_strat_synth.data.loader import load_quant

g = build_graph()
ids = sorted(q.account_id for q in load_quant())

out = []

for aid in ids:

    cfg = {"configurable": {"thread_id": f"batch-{aid}"}}

    state= g.invoke({"account_id": aid, "review_required": False}, config=cfg)
    syn = state.get("synthesis")
    out.append({
        "account_id": aid,
        "headline": syn.headline if syn else None,
        "claims": [c.model_dump() for c in syn.claims] if syn else [],
        "next_best_action": syn.next_best_action if syn else None,
        "competitive_risk_flag": syn.competitive_risk_flag if syn else False,
        "risk_score": syn.risk_score if syn else None,
        "evidence_ids": [e.chunk_id for e in state.get("evidence",[])],
    })
    print(aid, "done")

ofname = "data/syntheses.jsonl"
Path(ofname).write_text("\n".join(json.dumps(o) for o in out))
print(f"wrote to {ofname}", len(out), "syntheses")