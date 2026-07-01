from acnt_strat_synth.graph.build import build_graph

g = build_graph()
cfg = {"configurable": {"thread_id": "auto-1"}}

# Autonomous: no interrupt because gate routes to 'go'.
state = g.invoke({"account_id": "HCP-002", "review_required": False}, config=cfg)

# this one was the original instance, because we told the model to stop before synth
# state = g.invoke(None, config=cfg)

syn = state["synthesis"]

print("HEADLINE:", syn.headline)
print("RISK:", syn.risk_score, "; FLAG:", syn.competitive_risk_flag)
print("NBA:", syn.next_best_action)

for c in syn.claims:
    print(" -", c.statement, " cites:", c.cites)