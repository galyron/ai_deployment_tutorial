# Phase 3 — The Predictive Tool

**Capabilities touched:** tool/function calling, predictive layer.
**Exit criterion:** A callable tool returns a deterministic risk score in `[0, 1]` for an account; the LLM never invents the number.
**Budget:** 1h.

---

### Step 3.1 — Define the feature contract and label

**Goal:** Decide what features feed the model and what the score *means*. Decide once, document inline.

**Do:**
- Features (from `accounts_quant.parquet`): `rx_trend_pct`, `nps_proxy`, `call_count_last_q`, `market_potential_score`, `rx_volume_last_q`.
- Target: `risk_score` in `[0, 1]` where `1` = high-risk (declining + low NPS + thin coverage).
- We are *not* training on real outcomes; this is a transparent rule-based scorer surfaced as if it were a model. The agent shouldn't care.

**Code / commands:**
```bash
mkdir -p acnt_strat_synth/predict
touch acnt_strat_synth/predict/__init__.py
```

```python
# acnt_strat_synth/predict/score.py
import math
import pandas as pd
from acnt_strat_synth.data.loader import load_quant

_FEATURES = ["rx_trend_pct", "nps_proxy", "call_count_last_q", "market_potential_score", "rx_volume_last_q"]

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def _risk(row) -> float:
    # Higher score = higher risk. Hand-tuned weights, transparent on purpose.
    z = (
        -0.06 * row["rx_trend_pct"]          # falling Rx -> risk up
        - 0.012 * row["nps_proxy"]           # low NPS -> risk up
        - 0.08 * row["call_count_last_q"]    # thin coverage -> risk up
        - 0.05 * row["market_potential_score"]
        - 0.001 * row["rx_volume_last_q"]
        + 1.2
    )
    return round(_sigmoid(z), 3)
```

**Self-check:**
```bash
uv run python -c "from acnt_strat_synth.predict.score import _risk; print(_risk({'rx_trend_pct':-25,'nps_proxy':-40,'call_count_last_q':1,'market_potential_score':4,'rx_volume_last_q':50}))"
# Expected: a value > 0.7
```

**If broken:**
- Always returns the same number → check the weight signs; a positive weight on `nps_proxy` would invert the contract.

**Time estimate:** ~10m.

---

### Step 3.2 — Score function over the whole dataset

**Goal:** A pure function `score_account(account_id) -> float` callable from anywhere.

**Do:**
- Cache the quant DataFrame at module load.
- Provide a friendly `score_account(account_id)` API + a batch helper.

**Code / commands:**
```python
# acnt_strat_synth/predict/score.py  (append)
_DF = load_quant().set_index("account_id")

def score_account(account_id: str) -> float:
    if account_id not in _DF.index:
        raise KeyError(f"Unknown account: {account_id}")
    return _risk(_DF.loc[account_id])

def score_all() -> dict[str, float]:
    return {aid: _risk(row) for aid, row in _DF.iterrows()}
```

**Self-check:**
```bash
uv run python - <<'PY'
from acnt_strat_synth.predict.score import score_account, score_all
print("HCP-001:", score_account("HCP-001"))   # rep-over-optimistic: declining Rx -> high risk
print("HCP-002:", score_account("HCP-002"))   # growing: lower risk
scores = score_all()
assert min(scores.values()) >= 0 and max(scores.values()) <= 1
print("range ok; distinct scores:", len(set(scores.values())))
PY
```
HCP-001 score should be noticeably higher than HCP-002. Distinct-scores count is > 30 (non-degenerate).

**If broken:**
- All scores cluster around 0.5 → feature scaling is off; halve the bias term or double the leading coefficients.

**Time estimate:** ~10m.

---

### Step 3.3 — Sanity test on the tension accounts

**Goal:** Order is intuitive: HCP-001 (declining) and HCP-005 (at_risk + thin coverage) score above HCP-002 (growing).

**Do:**
- Print scores for the five tension IDs sorted descending.

**Code / commands:**
```python
# scripts/check_scoring.py
from acnt_strat_synth.predict.score import score_account
ids = ["HCP-001", "HCP-002", "HCP-003", "HCP-004", "HCP-005"]
for aid in sorted(ids, key=score_account, reverse=True):
    print(f"{aid}: {score_account(aid):.3f}")
```

```bash
uv run python scripts/check_scoring.py
```

**Self-check:** HCP-001 and HCP-005 occupy positions 1 and 2; HCP-002 is at the bottom of the list.

**If broken:**
- Ordering wrong → adjust weights in `_risk`; document the change with a one-line comment.

**Time estimate:** ~10m.

---

### Step 3.4 — Wrap as a LangChain tool

**Goal:** A `BaseTool` LangGraph can call by name with structured args.

**Do:**
- Use `langchain_core.tools.tool` decorator. Input is `account_id: str`, output is a JSON-serializable dict with `risk_score` and the input feature values used.

**Code / commands:**
```python
# acnt_strat_synth/predict/tool.py
from langchain_core.tools import tool
from acnt_strat_synth.predict.score import _DF, score_account

@tool
def account_risk_score(account_id: str) -> dict:
    """Return the predictive risk score in [0,1] for an HCP account, plus the quantitative features used."""
    score = score_account(account_id)
    feats = _DF.loc[account_id, ["rx_trend_pct", "nps_proxy", "call_count_last_q", "market_potential_score", "rx_volume_last_q"]].to_dict()
    return {"account_id": account_id, "risk_score": score, "features": feats}
```

**Self-check:**
```bash
uv run python - <<'PY'
from acnt_strat_synth.predict.tool import account_risk_score
out = account_risk_score.invoke({"account_id": "HCP-001"})
print(out)
assert 0 <= out["risk_score"] <= 1
assert set(out["features"]) == {"rx_trend_pct","nps_proxy","call_count_last_q","market_potential_score","rx_volume_last_q"}
print("ok")
PY
```
Prints the dict and `ok`.

**If broken:**
- `ToolException` on input → the decorator expects the arg as a dict in `.invoke({})`; verify the call shape above.

**Time estimate:** ~15m.

---

### Step 3.5 — End-to-end tool call from a minimal LLM agent

**Goal:** Confirm an Azure-OpenAI-backed LangChain agent can pick the tool, call it, and get the same number a direct call returns. Wires up function calling end-to-end before Phase 4 builds the full graph.

**Do:**
- Bind the tool to the chat model, ask it to score `HCP-001`, parse the tool call, execute it, compare.

**Code / commands:**
```python
# scripts/tool_smoke.py
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from acnt_strat_synth.predict.tool import account_risk_score
from acnt_strat_synth.predict.score import score_account
from acnt_strat_synth.config import settings

llm = AzureChatOpenAI(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.chat_deployment, temperature=0,
).bind_tools([account_risk_score])

ai = llm.invoke([HumanMessage("Get the risk score for HCP-001 using the tool.")])
assert ai.tool_calls, f"no tool call: {ai}"
call = ai.tool_calls[0]
print("tool requested:", call["name"], call["args"])

tool_out = account_risk_score.invoke(call["args"])
print("tool output:", tool_out)
assert tool_out["risk_score"] == score_account("HCP-001")
print("ok")
```

```bash
uv run python scripts/tool_smoke.py
```

**Self-check:** `tool requested: account_risk_score {'account_id': 'HCP-001'}` followed by `ok`.

**If broken:**
- `ai.tool_calls` is empty → model returned text instead. Re-run; or sharpen the prompt: `"Call the account_risk_score tool with account_id=HCP-001. Do not answer in prose."`
- API error mentioning `tool_choice` → upgrade `langchain-openai` (`uv add 'langchain-openai>=0.3'`).

**Time estimate:** ~10m.

---

Phase 3 done. The agent vs. tool boundary is now real and the same number arrives whether you call the function directly or via the LLM. Commit: `git add -A && git commit -m "phase 3: predictive tool + LangChain binding"`.
