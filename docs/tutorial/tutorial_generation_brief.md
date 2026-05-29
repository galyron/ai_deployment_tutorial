# Tutorial Generation Brief — Context for Claude Code / Cursor

Companion to `account_strategy_synthesizer_tutorial.md` (the plan). This file provides the operational context, step contract, and self-check methodology a code-generating assistant needs to produce a usable step-by-step tutorial from the plan.

**How to use these two files together:**
- Drop both files into Claude Code → ask it to generate the full tutorial as a sequence of steps following the contract below.
- Give both files to Cursor as context → ask it questions when stuck during execution.

---

## Learner profile

- **OS:** macOS (Apple Silicon assumed; flag if Intel-specific commands diverge).
- **Python:** strong. Concise explanations. No need to explain `async`, typing, virtualenvs, env vars, basic git, basic Docker concepts.
- **Python tooling:** **uv** (https://docs.astral.sh/uv/). The single tool for Python version + virtualenv + dependency management. Tutorial commands should use `uv` throughout (`uv init`, `uv add`, `uv run`, etc.) rather than `pip`, `poetry`, or `pyenv`.
- **Cloud:** fresh Azure free account, no prior Azure CLI setup, no existing subscription. Treat Azure as new but the learner as technically strong.
- **Background to assume:** built agentic systems before on LangChain / OpenAI SDK / Anthropic SDK. Knows RAG, function calling, tool use, prompt engineering. New to: Azure-native services specifically, LangGraph specifically (but knows the orchestration concepts).
- **Editor/workflow:** Cursor with integrated terminal. Browser tab open to Azure Portal. Tutorial markdown opens as a Cursor tab inside the repo. Nothing else.

## Goals & success criteria

The tutorial must produce, end-to-end in 8–12 hours:

1. A working repo (`account-strategy-synthesizer` or similar) on the learner's laptop.
2. A live Azure Container Apps endpoint that accepts an account ID and returns a structured synthesis with source citations.
3. One LangSmith / Azure Monitor trace screenshot the learner can point at.
4. An eval results table (groundedness + LLM-as-judge quality scores) over a small batch of synthetic accounts.
5. A torn-down resource group at the end.

The tutorial must **cover all nine list-1 capabilities** from the plan's coverage table. Don't drop any; if time-constrained, prefer the cut order in the plan's Risk + cut order section.

## What the tutorial is NOT

- **Not a production guide.** No Kubernetes, no advanced security hardening, no multi-environment CI/CD. Container Apps + free-tier services are the deliberate ceiling.
- **Not a Python crash course.** Don't explain language fundamentals.
- **Not exhaustive on alternatives.** Make one good choice per decision, explain it in one sentence, move on. Don't enumerate options unless it's a load-bearing decision (e.g., LangGraph vs alternatives — already chosen, don't re-litigate).
- **Not a chat.** No "great question!" preamble. No closing pep talk per step.

---

## Step contract (THE most important section)

The tutorial is a sequence of steps. **Every step must follow this exact structure:**

```
### Step N.M — [short imperative title]

**Goal:** One sentence. What this step accomplishes.

**Do:**
- Concrete action 1 (command, code, click)
- Concrete action 2
- ...

**Code / commands:** (if applicable, in fenced blocks with language tag)

**Self-check:** Exactly how the learner verifies this step worked. MUST be one of:
- A command to run and the expected output (literal text or pattern).
- A specific file/state to inspect and what it should contain.
- A specific Azure Portal screen and what should be visible.
- An assertion in Python / a pytest line that should pass.
NOT "you should now see things working" — concrete, falsifiable, copy-pasteable.

**If broken:** One or two most common failure modes and what to check.
**Time estimate:** ~Xm.
```

**Granularity rule:** A step should be 5–20 minutes of work. If a step would take longer, split it. If smaller than 5 minutes, merge it into the next. Phase 0 will have ~6-8 steps; Phase 4 (centerpiece) ~8-10 steps.

**No step without a self-check.** Even "create a folder" gets `ls` + expected output. This is non-negotiable — the entire point of the tutorial is the learner can verify they're on track without external help.

---

## Self-check methodology — patterns to apply

For each phase's typical checks:

| Phase | Self-check style |
|---|---|
| 0 (Setup) | `az` CLI commands returning specific resource state; a Python script that imports + authenticates without exception |
| 1 (Data gen) | Row counts, column schemas, spot-check that "interesting accounts" have the tensions described |
| 2 (RAG) | A retrieval query returning N>0 chunks, each with `account_id` + `source_type` metadata visible |
| 3 (Predictive tool) | The tool returns a score for a known input; assertion on score range |
| 4 (Orchestration) | A LangGraph run produces a structured output; the review-toggle pause is observable (stdout or state inspection); cited sources match retrieved chunks |
| 5 (Evals) | A results table prints/persists; numbers are non-degenerate (not all 1.0 or 0.0) |
| 6 (Observability + guardrails) | A trace exists in the chosen tool (LangSmith or Azure Monitor); a unit test proves the minimization step strips the expected fields |
| 7 (Deploy) | `curl` against the Azure endpoint returns a 200 with valid synthesis JSON |

The tutorial should make these checks explicit at every step, not just at phase boundaries.

---

## Decisions already locked (do not re-debate)

The tutorial should treat these as settled. No "you might also consider..." asides.

- **Orchestration:** LangGraph.
- **LLM:** Azure OpenAI, GPT-4o (and an Azure OpenAI embedding model — `text-embedding-3-small` or similar).
- **Retrieval:** Azure AI Search, free tier.
- **Predictive tool:** simple sklearn classifier or rules-based — whichever generates faster. Not a deep model.
- **Eval:** custom harness with LLM-as-judge + groundedness check. No third-party eval platform.
- **Tracing:** LangSmith (free tier) is the default. If LangSmith setup is friction, fall back to OpenTelemetry → Azure Monitor.
- **Deploy target:** Azure Container Apps. Not AKS, not App Service, not Functions.
- **Secrets:** Azure Key Vault for the deployed app; `.env` (gitignored) for local dev. No hybrid weirdness.
- **Package management:** uv only.
- **HTTP framework for the deployed endpoint:** FastAPI.

If the generator hits a question not answered here, it should make the simplest choice that ships and note the choice in one sentence.

---

## Cost discipline (must appear in tutorial)

Mention these explicitly:

- **Step in Phase 0:** Set a 25 EUR budget alert on the subscription. Concrete walkthrough.
- **Step in Phase 0:** Provision AI Search at **free tier**, not Basic. Call out the 70 EUR/month trap explicitly.
- **Final step in Phase 7:** Tear-down checklist — `az group delete --name <rg> --yes --no-wait`. Verify with `az group list`.

Realistic total cost target: **5–15 EUR** if tidy.

---

## Synthetic data spec (Phase 1 needs more detail than the plan provides)

Phase 1 needs ~50 HCP accounts. Schema:

**Quantitative (CSV/parquet):**
- `account_id` (string, e.g. `HCP-001`)
- `segment` (one of: `high_potential`, `growing`, `stable`, `at_risk`)
- `territory` (one of ~5 fake territories)
- `rx_volume_last_q` (int)
- `rx_trend_pct` (float, -50 to +50)
- `call_count_last_q` (int, 0-20)
- `market_potential_score` (int, 1-10)
- `nps_proxy` (int, -100 to +100)

**Qualitative (per account, generate via LLM):**
- 1–3 rep call notes (~50-150 words each), free text
- 0–1 MSL summary (~100 words)
- 0–1 competitive-intel snippet (~80 words)
- 0–1 market-research paragraph (~120 words)

**Tension seeds (the eval ground truth):** at least 5 accounts must contain deliberately conflicting signals:
- Account where Rx is declining but call notes are upbeat → "rep over-optimistic" pattern
- Account with rising Rx but competitive threat in qualitative only → "watch-list" pattern
- Account with stable Rx but NPS dropping → "early-warning" pattern
- Account where competitor name appears in MR snippet but nowhere else → traceability test
- Account with no qualitative data at all → graceful-degradation test

The synthesis system should produce outputs that *correctly identify these patterns* on the seeded accounts. That's the eval target in Phase 5.

---

## Tone and format requirements for the generated tutorial

- Markdown, single file or one file per phase — generator's choice.
- Imperative voice: "Run", "Create", "Verify", not "You should run".
- No emojis. No "🚀". No "Congrats!" between phases.
- Code blocks with language tags so Cursor highlights correctly.
- File paths in backticks.
- Commands prefixed with `$` only if mixing shell + output; otherwise plain.
- When a step requires Azure Portal navigation: name the exact menu path, e.g. *"Portal → Resource groups → `rg-acct-strategy` → + Create → 'Azure AI Search'"*.

---

## What the generator should output

A complete tutorial file (or set of files) where:
1. Phase 0 through Phase 7 each have their own section.
2. Each phase has 5–10 steps following the contract.
3. Each step has goal / do / code / self-check / if-broken / time.
4. A final section: "Tear-down + what you built", with the resource group delete command and a recap of what's now claimable from the Stephan email's list 1.

If the generator must abbreviate, the priority order matches the plan's cut order: trim Phase 6 detail first, then simplify Phase 5. Never thin Phase 4 or Phase 7.

---

## Companion file

The accompanying plan (`account_strategy_synthesizer_tutorial.md`) carries the system design, capability coverage table, and per-phase methodology rationale. This brief carries the operational context, step contract, and self-check standard.

Both files together are sufficient input. No further clarification should be needed; if it is, the generator should make the simplest choice that ships.
