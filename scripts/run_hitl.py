from acnt_strat_synth.graph.build import build_graph

g = build_graph()
cfg = {"configurable": {"thread_id": "hitl-1"}}

# Autonomous: no interrupt because gate routes to 'go'.
state_1 = g.invoke({"account_id": "HCP-002", "review_required": True}, config=cfg)
print("pause: syntheisis is", state_1.get("synthesis"))
print("next nodes:", g.get_state(cfg).next)

# Approve 
g.update_state(cfg, {"approved": True})
# ... and resume
state_2 = g.invoke(None, config=cfg)

print("resume: headline is", state_2.get("synthesis").headline)