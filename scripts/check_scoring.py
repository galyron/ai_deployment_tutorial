from acnt_strat_synth.predict.score import score_account
ids = ["HCP-001", "HCP-002", "HCP-003", "HCP-004", "HCP-005"]
for aid in sorted(ids, key=score_account, reverse=True):
    print(f"{aid}: {score_account(aid):.3f}")