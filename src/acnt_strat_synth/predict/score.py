import math
import pandas as pd
from acnt_strat_synth.data.loader import load_quant

_FEATURES = ["rx_trend_pct", "nps_proxy", "call_count_last_q", "market_potential_score", "rx_volume_last_q"]

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def _risk(row) -> float:
    # Higher score = higher risk. Hand-tuned weights, transparent on purpose.
    z = (
        -0.10 * row["rx_trend_pct"]          # falling Rx -> risk up
        - 0.012 * row["nps_proxy"]           # low NPS -> risk up
        - 0.08 * row["call_count_last_q"]    # thin coverage -> risk up
        - 0.05 * row["market_potential_score"]
        - 0.001 * row["rx_volume_last_q"]
        + 1.2
    )
    return round(_sigmoid(z), 3)

# load_quant() returns list[AccountQuant] (pydantic objects); the predictive
# scorer below uses pandas (loc, iterrows) for tabular operations, so we
# materialize once at module load. model_dump() turns each pydantic object
# into a plain dict, which DataFrame can ingest.
_DF = pd.DataFrame([q.model_dump() for q in load_quant()]).set_index("account_id")

def score_account(account_id: str) -> float:
    if account_id not in _DF.index:
        raise KeyError(f"Unknown account: {account_id}")
    return _risk(_DF.loc[account_id])

def score_all() -> dict[str, float]:
    return {aid: _risk(row) for aid, row in _DF.iterrows()}