# Phase 5 — Evals

**Capabilities touched:** evaluation harness, benchmark + monitor quality.
**Exit criterion:** A results table on stdout (and CSV on disk) showing groundedness pass-rate and LLM-as-judge quality scores over the 50-account batch, with non-degenerate variance.
**Budget:** 1.5h.

---

### Step 5.1 — Define the eval dataset

**Goal:** Ground-truth labels for the five tension accounts, plus a general "must be grounded" check applied to all 50.

**Do:**
- Encode the five expected patterns as machine-checkable expectations.

**Code / commands:**
```bash
mkdir -p acnt_strat_synth/evals
touch acnt_strat_synth/evals/__init__.py
```

```python
# acnt_strat_synth/evals/ground_truth.py
# Each entry: account_id -> expected behaviour.
# `must_flag` = competitive_risk_flag must be True.
# `must_mention_substr` = synthesis text must include this substring (case-insensitive).
# `expected_pattern` = informal description used by the LLM judge.

GROUND_TRUTH = {
    "HCP-001": dict(must_flag=False, must_mention_substr="decline",
                    expected_pattern="rep over-optimistic: notes upbeat but Rx declining; synthesis should call out the contradiction"),
    "HCP-002": dict(must_flag=True,  must_mention_substr="competit",
                    expected_pattern="watch-list: rising Rx but competitive threat present in qualitative; flag should be True"),
    "HCP-003": dict(must_flag=False, must_mention_substr="nps",
                    expected_pattern="early-warning: stable Rx but NPS dropping; synthesis should surface the leading indicator"),
    "HCP-004": dict(must_flag=True,  must_mention_substr="brand-x",
                    expected_pattern="traceability test: competitor 'Brand-X' appears only in market-research; synthesis must surface Brand-X and cite the market_research chunk"),
    "HCP-005": dict(must_flag=False, must_mention_substr=None,
                    expected_pattern="graceful degradation: no qualitative; synthesis must rely on score alone and acknowledge missing evidence"),
}
```

**Self-check:**
```bash
uv run python -c "from acnt_strat_synth.evals.ground_truth import GROUND_TRUTH; print(len(GROUND_TRUTH))"
# Expected: 5
```

**Time estimate:** ~10m.

---

### Step 5.2 — Groundedness check

**Goal:** For every synthesis, every claim's `cites` references either a real chunk_id from that account's evidence or the special `PREDICT` token. No invented citations.

**Do:**
- Reconstruct evidence per account via the extract node (cached lookup).
- For each synthesis, count grounded vs. ungrounded claims.

**Code / commands:**
```python
# acnt_strat_synth/evals/groundedness.py
import json
from acnt_strat_synth.graph.nodes import extract_node

_evidence_cache: dict[str, set[str]] = {}

def _allowed_ids(account_id: str) -> set[str]:
    if account_id not in _evidence_cache:
        s = extract_node({"account_id": account_id})
        _evidence_cache[account_id] = {e.chunk_id for e in s["evidence"]} | {"PREDICT"}
    return _evidence_cache[account_id]

def evaluate_one(synth_row: dict) -> dict:
    allowed = _allowed_ids(synth_row["account_id"])
    total = len(synth_row["claims"])
    if total == 0:
        return {"account_id": synth_row["account_id"], "grounded": 0, "total": 0, "pass": True}
    ungrounded = sum(
        1 for c in synth_row["claims"]
        if not set(c["cites"]).issubset(allowed) or not c["cites"]
    )
    return {
        "account_id": synth_row["account_id"],
        "grounded": total - ungrounded,
        "total": total,
        "pass": ungrounded == 0,
    }

def evaluate_all(path: str = "data/syntheses.jsonl") -> list[dict]:
    rows = [json.loads(l) for l in open(path)]
    return [evaluate_one(r) for r in rows]
```

**Self-check:**
```bash
uv run python - <<'PY'
from acnt_strat_synth.evals.groundedness import evaluate_all
res = evaluate_all()
pass_rate = sum(r["pass"] for r in res) / len(res)
print(f"groundedness pass rate: {pass_rate:.0%}")
print("failures:", [r for r in res if not r["pass"]][:3])
PY
```
Pass rate >= 95% (one or two stragglers acceptable; if more, the synthesis prompt isn't strict enough — go fix Step 4.4).

**If broken:**
- Pass rate < 80% → most likely the chunk_ids in evidence don't match what synth sees because extract was non-deterministic between runs. Persist evidence alongside syntheses in Phase 4 (`evidence_ids` is already there; switch the allowed set to use that field instead of recomputing).

**Time estimate:** ~20m.

---

### Step 5.3 — LLM-as-judge quality scorer

**Goal:** A GPT-4o judge rates each synthesis on a 1–5 scale against the expected pattern for that account. Generic patterns apply to non-tension accounts.

**Do:**
- Prompt the judge with: account ID, expected pattern, synthesis JSON. Ask for `{score: int, reason: str}`.
- For non-tension accounts the expected pattern is `"plausible and grounded synthesis based on the inputs"`.

**Code / commands:**
```python
# acnt_strat_synth/evals/judge.py
import json
from pydantic import BaseModel, Field
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from acnt_strat_synth.evals.ground_truth import GROUND_TRUTH
from acnt_strat_synth.config import settings

class Judgement(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str

_llm_judge = AzureChatOpenAI(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.chat_deployment, temperature=0,
).with_structured_output(Judgement)

JUDGE_SYSTEM = (
    "You rate account syntheses for usefulness on a 1-5 scale.\n"
    "5 = nails the expected pattern, concrete next action, no fluff.\n"
    "3 = generic but not wrong.\n"
    "1 = misleading or contradicts the evidence.\n"
    "Be strict and terse."
)

def judge_one(synth_row: dict) -> Judgement:
    aid = synth_row["account_id"]
    expected = GROUND_TRUTH.get(aid, {}).get("expected_pattern",
                                            "plausible, grounded synthesis based on the inputs")
    user = (
        f"account_id: {aid}\n"
        f"expected_pattern: {expected}\n"
        f"synthesis_json: {json.dumps(synth_row, default=str)}"
    )
    return _llm_judge.invoke([SystemMessage(JUDGE_SYSTEM), HumanMessage(user)])
```

**Self-check:**
```bash
uv run python - <<'PY'
import json
from acnt_strat_synth.evals.judge import judge_one
row = next(json.loads(l) for l in open("data/syntheses.jsonl") if json.loads(l)["account_id"] == "HCP-002")
j = judge_one(row)
print(j.score, "-", j.reason[:120])
PY
```
Prints a score 1–5 and a one-sentence reason.

**If broken:**
- Judge returns plain text instead of structured → confirm `with_structured_output(Judgement)`; older `langchain-openai` versions need `method="function_calling"` argument.

**Time estimate:** ~20m.

---

### Step 5.4 — Run the harness over all 50 accounts

**Goal:** Single command produces per-account groundedness + judge results.

**Do:**
- For each synthesis row: run `evaluate_one` + `judge_one`, also check the `must_flag` and `must_mention_substr` expectations for tension accounts.

**Code / commands:**
```python
# scripts/run_evals.py
import json, csv, pathlib
from acnt_strat_synth.evals.groundedness import evaluate_one
from acnt_strat_synth.evals.judge import judge_one
from acnt_strat_synth.evals.ground_truth import GROUND_TRUTH

rows = [json.loads(l) for l in open("data/syntheses.jsonl")]
out = []
for r in rows:
    aid = r["account_id"]
    grnd = evaluate_one(r)
    judg = judge_one(r)
    gt = GROUND_TRUTH.get(aid, {})

    flag_ok = True
    if "must_flag" in gt:
        flag_ok = (r.get("competitive_risk_flag") is gt["must_flag"])
    mention_ok = True
    if gt.get("must_mention_substr"):
        blob = json.dumps(r).lower()
        mention_ok = gt["must_mention_substr"].lower() in blob

    out.append({
        "account_id": aid,
        "grounded_pass": grnd["pass"],
        "grounded_ratio": (grnd["grounded"] / grnd["total"]) if grnd["total"] else None,
        "judge_score": judg.score,
        "flag_ok": flag_ok,
        "mention_ok": mention_ok,
        "judge_reason": judg.reason,
    })
    print(aid, "judge", judg.score, "grounded", grnd["pass"], "flag", flag_ok, "mention", mention_ok)

path = pathlib.Path("data/eval_results.csv")
with path.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)
print("wrote", path)
```

```bash
uv run python scripts/run_evals.py
```

**Self-check:** Output ends with `wrote data/eval_results.csv`. Per-row scores are present.

**Time estimate:** ~15m.

---

### Step 5.5 — Print the summary table

**Goal:** A single small table the colleague-call screenshot points at.

**Do:**
- Aggregate: overall groundedness pass-rate, mean judge score, tension-account-specific pass-rate.

**Code / commands:**
```python
# scripts/summarize_evals.py
import pandas as pd
from acnt_strat_synth.evals.ground_truth import GROUND_TRUTH

df = pd.read_csv("data/eval_results.csv")

tension_ids = list(GROUND_TRUTH)
tdf = df[df["account_id"].isin(tension_ids)]
rest = df[~df["account_id"].isin(tension_ids)]

print("== Overall ==")
print(f"  groundedness pass-rate: {df['grounded_pass'].mean():.0%}")
print(f"  mean judge score:        {df['judge_score'].mean():.2f}")
print(f"  judge score std:         {df['judge_score'].std():.2f}")

print("\n== Tension accounts ==")
print(tdf[["account_id","judge_score","flag_ok","mention_ok","grounded_pass"]].to_string(index=False))

print("\n== Non-tension accounts ==")
print(f"  mean judge score: {rest['judge_score'].mean():.2f}  (n={len(rest)})")
```

```bash
uv run python scripts/summarize_evals.py
```

**Self-check:** Output contains three sections; tension table shows all five accounts with their per-row outcomes; non-tension mean is between 3.0 and 4.5.

**Time estimate:** ~10m.

---

### Step 5.6 — Verify non-degenerate variance

**Goal:** Catch the failure mode where the judge gives everyone the same score and the harness lies to you.

**Do:**
- Assert std > 0.3 on the judge score; assert at least one judge_score < 5; flag if pass-rate is exactly 0 or 1.

**Code / commands:**
```bash
uv run python - <<'PY'
import pandas as pd
df = pd.read_csv("data/eval_results.csv")
assert df["judge_score"].std() > 0.3, f"judge degenerate: std={df['judge_score'].std()}"
assert df["judge_score"].min() < 5, "judge gave everyone 5; not credible"
assert 0 < df["grounded_pass"].mean() <= 1, "grounded pass-rate out of expected range"
print("eval signal looks healthy")
PY
```

**Self-check:** Prints `eval signal looks healthy`.

**If broken:**
- `judge degenerate` → tighten the JUDGE_SYSTEM rubric or include adversarial examples; also lower temperature is already 0 so don't touch that.

**Time estimate:** ~10m.

---

Phase 5 done. Commit: `git add -A && git commit -m "phase 5: eval harness with groundedness + LLM judge"`.
