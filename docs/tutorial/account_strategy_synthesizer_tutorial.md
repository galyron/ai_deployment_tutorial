# Account Strategy Synthesizer — Weekend Tutorial Plan

Hands-on tutorial to convert Bucket 2 (LangChain/OpenAI SDK skills, conceptual Azure) into Bucket 1 (built and deployed an agentic system on Azure). Outcome: every bullet under "Agentic GenAI workflows" in the Stephan email becomes a true hands-on claim, defensible in colleague calls.

---

## Target system

**Account Strategy Synthesizer** — pharma-sales-centered agentic system that ingests quantitative + qualitative inputs per HCP account and produces a structured account-level engagement recommendation with competitive context. Mirrors the Stephan use-case (synthesis from mixed inputs) but in a sales frame Gabriell knows cold.

- **Quantitative synthetic inputs:** sales/Rx data per account, call activity, segment, territory, market potential, NPS-style scores.
- **Qualitative synthetic inputs:** rep call notes, MSL interaction summaries, competitive-intel snippets, fake market-research paragraphs.
- **Output:** per-account synthesis — what's happening, why, recommended next best action, competitive risk flag — every claim traceable to its source input.

---

## Guiding principle

One system, thin vertical slices, each slice lighting up one or two list-1 capabilities. Every capability touched hands-on and credibly; none gold-plated. Goal is *"I built and deployed this, here's the repo"* — not production-grade. Synthetic data throughout.

---

## Stack & workflow

**Framework:** LangGraph for orchestration (transfer path from existing LangChain knowledge) + Azure services around it.

**Apps:**
- **Cursor** — code, notebooks, tutorial markdown as side-by-side tabs. Integrated terminal for `az` CLI, container build/push, scripts.
- **Browser** — Azure Portal only. One tab. Provisioning, deploys, traces.
- Tutorial markdown lives *inside the repo* as a Cursor tab. No fourth window.

**Code structure:** `.py` project (not notebooks as primary). Optional `explore.ipynb` for Phase 1 data scratchpad.

---

## Cost discipline (do this before Phase 0)

- Set subscription **spend cap / budget alert at 25 EUR**. Two minutes, saves real money.
- **Use AI Search free tier**, not Basic. Basic is ~70 EUR/month and the most common Azure-newbie surprise charge.
- **Tear-down at end:** delete the resource group. One click nukes everything in it.
- Realistic total cost if tidy: **5–15 EUR.** Free Azure account gives $200 credits for 30 days.

---

## Phase 0 — Setup & scaffolding (1.5–2h)

**Capabilities touched:** deployment foundation, project hygiene.

**Build:**
- Azure account + subscription, resource group, Azure OpenAI resource (deploy GPT-4o + embedding model), Azure AI Search instance (free tier), Key Vault for keys.
- Local repo: Python, LangGraph, env management, Azure SDK clients wired and authenticating.

**Methodology:** Get "hello world" round-trips working to each Azure service *before* any real logic. Fail fast on auth/config — this is where Azure eats time.

**Exit criterion:** Script that calls Azure OpenAI and writes/reads from AI Search.

---

## Phase 1 — Synthetic data generation (1–1.5h)

**Capabilities touched:** qualitative + quantitative input handling (core to the use-case).

**Build:**
- *Quantitative:* ~50 synthetic HCP accounts — Rx volume, trend, segment, territory, call count, market potential, NPS-style score. CSV/parquet.
- *Qualitative:* per-account free-text — rep call notes, MSL summary, competitive-intel snippet, one "market-research paragraph." Use the LLM to generate realistic varied text.

**Methodology:** Deliberately seed accounts with *tension* — declining Rx but positive notes, competitive threat buried in qualitative text only. A demo where the answer is obvious proves nothing. The "interesting accounts" become your eval ground truth in Phase 5.

**Exit criterion:** Data on disk + a few interesting accounts where you know the right answer.

---

## Phase 2 — Retrieval + grounding layer (1.5h)

**Capabilities touched:** RAG, source traceability.

**Build:**
- Chunk + embed qualitative docs, index in Azure AI Search with metadata (`account_id`, `source_type`) so retrieval is filterable and every chunk carries its origin.
- Retrieval function: given an account, returns its qualitative evidence with source tags.

**Methodology:** Traceability is the design constraint. Every retrieved snippet returns `{text, source_type, account_id}`. This is what makes "every claim traces to its input" demonstrable, not aspirational.

**Exit criterion:** Query an account, get back tagged evidence.

---

## Phase 3 — The predictive tool (1h)

**Capabilities touched:** tool/function calling, the predictive layer.

**Build:**
- Simple model over the quantitative data — rules-based or light sklearn classifier that scores each account's "risk" or "opportunity." Doesn't need to be sophisticated; needs to be a real callable tool the agent invokes, not the LLM guessing numbers.
- Wrap as a LangGraph tool / function-call.

**Methodology:** This is where the "agent vs tool" decision becomes visible — LLM orchestrates, model computes. That distinction is the credibility line with the GenAI peer. Keep the model dumb, make the integration clean.

**Exit criterion:** Agent can call the tool and get a score back.

---

## Phase 4 — Agentic orchestration (2–2.5h, the centerpiece)

**Capabilities touched:** design agentic workflows, multi-agent systems, orchestration + state, human-in-the-loop switch.

**Build — LangGraph graph with worker nodes:**
- *Extract node* — pull + structure qualitative evidence (uses Phase 2).
- *Score node* — call predictive tool (uses Phase 3).
- *Synthesis node* — combine quant score + qual evidence into account narrative + recommended next best action + competitive flag, every claim citing its source.
- *Orchestrator* — runs the graph, holds state.

**Human-in-the-loop switch:** `review_required` flag in state → LangGraph interrupt/checkpoint pauses for approval when on, runs autonomous when off.

**Methodology:** Build single-account first, end-to-end, then loop over accounts. Get one full traversal working before adding the review toggle. The toggle is the *"I've actually built agentic systems"* proof — don't skip it for time.

**Exit criterion:** Run an account through the full graph, get a sourced synthesis; flip the flag and watch it pause for review.

---

## Phase 5 — Evals (1.5h)

**Capabilities touched:** develop/implement evaluation harnesses, benchmark + monitor quality.

**Build — two eval layers:**
- *Groundedness/traceability:* does every claim in the output map to a real retrieved source? (catch hallucination)
- *Quality:* LLM-as-judge scoring synthesis usefulness against the Phase-1 interesting accounts ground truth.
- Run as a harness over a batch, produce a score table.

**Methodology:** This is where "benchmarked, not guessed" becomes honestly claimable. Tie it back to the competitive-scenario A/B idea from the Stephan use-case even if not built — you'll have the harness that *would* compare them.

**Exit criterion:** A results table you could show someone.

---

## Phase 6 — Observability + guardrails (1h)

**Capabilities touched:** observability (tracing, cost, latency), guardrails/compliance.

**Build:**
- *Tracing:* instrument the graph (LangSmith or OpenTelemetry → Azure Monitor) so each node's calls, tokens, cost, latency are visible.
- *Guardrails:* a data-minimization pass (strip fields the LLM doesn't need before it sees the data) + a basic PII-handling note + content grounding check.

**Methodology:** Don't over-build. Get *one* trace visible and *one* guardrail real. The point is "I instrument and I think about compliance," provable with a screenshot, not a production observability stack.

**Exit criterion:** A trace you can point at; a documented minimization step.

---

## Phase 7 — Deploy (1.5h)

**Capabilities touched:** deployment in cloud — the claim being made true.

**Build:**
- Containerize the system, deploy to Azure Container Apps (simplest real deploy), expose a minimal endpoint that runs an account through the graph.

**Methodology:** Simplest real deploy that counts as real. Container Apps over AKS — goal is "it runs on Azure," not "I configured Kubernetes."

**Exit criterion:** Hit a live Azure endpoint, get a synthesis back. This is the screenshot that makes the deployment bullet true.

---

## Capability coverage check

All nine list-1 bullets from the Stephan email touched:

| List-1 bullet | Phase |
|---|---|
| Design agentic workflows | 4 |
| Build multi-agent systems (qual+quant inputs) | 1, 4 |
| Orchestration + state, human-in-the-loop switch | 4 |
| RAG + source traceability | 2 |
| Tool/function calling into predictive models | 3, 4 |
| Model selection + deployment in cloud | 0, 7 |
| Evals harness | 5 |
| Observability + monitoring | 6 |
| Guardrails + compliance | 6 |

---

## Risk + cut order

Total planned: ~12–13h in a 12h budget. Azure friction always overruns.

**If falling behind, cut in this order:**
1. Trim Phase 6 to tracing only (drop guardrail build, document it instead).
2. Simplify Phase 5 to the groundedness check only.

**Never cut Phase 4 or Phase 7.** Orchestration and the real deploy are the two things that make the claims true. Protect those.

---

## Done means

- A repo with the system.
- A live Azure Container Apps endpoint that returns a synthesis for an account.
- A screenshot of one trace.
- An eval results table.
- The resource group deleted at the end.

When the colleague calls land, this is what makes the agentic bullets in the email *true*, not aspirational.
