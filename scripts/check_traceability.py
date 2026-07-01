from acnt_strat_synth.retrieval.search import retrieve

cases = [
    ("HCP-001", "rep enthusiasm",       "rep_call_note"),
    ("HCP-002", "competitive pressure", "comp_intel"),
    ("HCP-003", "customer satisfaction signals", "rep_call_note"),
    ("HCP-004", "competitor Brand-X",   "market_research"),
]
for acnt, q, expected in cases:
    hits = retrieve(acnt, q, k=4)
    types = [h.source_type for h in hits]
    print(acnt, "->", types, "OK" if expected in types[:3] else "MISS")