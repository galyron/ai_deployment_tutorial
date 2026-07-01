from langchain_core.tools import tool
from acnt_strat_synth.predict.score import _DF, score_account

@tool
def account_risk_score(account_id: str) -> dict:
    """Return the predictive risk score in [0,1] for an HCP account, plus the quantitative features used."""
    score = score_account(account_id)
    feats = _DF.loc[account_id, ["rx_trend_pct", "nps_proxy", "call_count_last_q", "market_potential_score", "rx_volume_last_q"]].to_dict()
    return {"account_id": account_id, "risk_score": score, "features": feats}