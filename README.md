# Account Strategy Synthesizer — Weekend Tutorial

A hands-on, 8–12 hour tutorial that builds and deploys an agentic system on Azure end-to-end. Outcome: a live Azure Container Apps endpoint that takes an HCP account ID and returns a structured strategy synthesis with source citations, plus an eval table and one trace screenshot.

## What you build

- A LangGraph workflow with three nodes — `extract` (RAG over qualitative evidence), `score` (predictive tool over quantitative features), `synth` (GPT-4o structured synthesis with mandatory citations).
- A human-in-the-loop switch that pauses the graph at synthesis when toggled.
- A `POST /synthesize` FastAPI endpoint on Azure Container Apps reading secrets from Azure Key Vault.
- An eval harness producing per-account groundedness + LLM-as-judge scores.
- One observable trace per run via LangSmith (fallback: OpenTelemetry → Azure Monitor).

All synthetic data. Deliberately seeded with five *tension* accounts that double as eval ground truth.

## Prerequisites

- macOS (Apple Silicon assumed).
- Strong Python; no Python fundamentals are taught here.
- A new Azure free account ($200 credits, 30 days).
- A LangSmith free account (optional; Azure Monitor fallback documented in Phase 6).
- Tooling: `uv`, `az` CLI, Docker Desktop, `jq` — installed in Step 0.1.

Realistic total cost if you tear down at the end: **5–15 EUR**. A 25 EUR budget alert is mandatory in Step 0.2.

## Locked design decisions

These are settled in the planning brief. The tutorial does not re-debate them.

| Concern | Choice |
|---|---|
| Orchestration | LangGraph |
| LLM | Azure OpenAI GPT-4o + `text-embedding-3-small` |
| Retrieval | Azure AI Search, **free tier** |
| Predictive tool | Hand-tuned rule scorer (transparent on purpose), wrapped as a LangChain tool |
| Eval | Custom harness, groundedness + LLM-as-judge |
| Tracing | LangSmith (Azure Monitor fallback) |
| Deploy | Azure Container Apps + Azure Container Registry |
| Secrets | Azure Key Vault in cloud; `.env` (gitignored) locally |
| Package manager | `uv` only |
| HTTP framework | FastAPI |

Design rationale and capability-coverage table: [`docs/tutorial/account_strategy_synthesizer_tutorial.md`](docs/tutorial/account_strategy_synthesizer_tutorial.md).
Step contract and self-check methodology: [`docs/tutorial/tutorial_generation_brief.md`](docs/tutorial/tutorial_generation_brief.md).

## Tutorial — run phases in order

Each phase is self-contained and ends with a `git commit` checkpoint. Every step has a goal, concrete actions, code/commands, a falsifiable self-check, common failure modes, and a time estimate.

| Phase | File | Capabilities | Budget |
|---|---|---|---|
| 0 | [Setup & scaffolding](docs/tutorial/phase_0_setup.md) | Deployment foundation, project hygiene | 1.5–2h |
| 1 | [Data: loading, streaming, ensembling](docs/tutorial/phase_1_data.md) | IO surface over the seed dataset | 45m–1h |
| 2 | [Retrieval + grounding layer](docs/tutorial/phase_2_retrieval.md) | RAG, source traceability | 1.5h |
| 3 | [Predictive tool](docs/tutorial/phase_3_predictive.md) | Tool/function calling | 1h |
| 4 | [Agentic orchestration](docs/tutorial/phase_4_orchestration.md) | Workflow design, multi-agent, state, HITL | 2–2.5h |
| 5 | [Evals](docs/tutorial/phase_5_evals.md) | Eval harness, benchmark + monitor | 1.5h |
| 6 | [Observability + guardrails](docs/tutorial/phase_6_observability.md) | Tracing, cost, latency, guardrails | 1h |
| 7 | [Deploy](docs/tutorial/phase_7_deploy.md) | Model selection + cloud deployment | 1.5h |

Total: ~10–12h. If time-constrained, the cut order (per the brief) is *(1)* trim Phase 6 to tracing only, then *(2)* simplify Phase 5 to groundedness only. Phases 4 and 7 are protected.

## The seed dataset

`data/seed/` ships with the repo: `accounts_quant.csv` (50 HCP accounts) and `accounts_qual.jsonl` (173 free-text documents — rep call notes, MSL summaries, competitive-intel snippets, market-research paragraphs). Total size ~45KB.

It's committed because it's small enough to keep the repo runnable from clone — no LLM call, no provisioning, no fetch step before you can start Phase 1. Five of the accounts (`HCP-001` through `HCP-005`) are deliberately seeded with conflicting signals; Phase 5 uses them as eval ground truth.

This is a tutorial-scope convenience trade-off. In a real ingest path, data lives in cloud storage (Blob, Lakehouse, warehouse), not in git. Don't copy the pattern to production work.

`scripts/seed_data.py` is the generator: stdlib-only, deterministic, with invariant checks on the tension accounts. You don't need to run it — the output is already on disk. It's there as documentation of how the seed was built and lets you regenerate or extend it if you want.

## Repository layout (after completion)

```
account-strategy-synthesizer/
├── pyproject.toml, uv.lock
├── .env                            # gitignored
├── src/
│   ├── config.py
│   ├── data/        schemas + loader
│   ├── retrieval/   chunking + AI Search client
│   ├── predict/     rule-based scorer + LangChain tool
│   ├── graph/       state, nodes, build_graph()
│   ├── evals/       groundedness + LLM judge
│   ├── guardrails/  data minimization
│   └── api/         FastAPI app
├── scripts/         one-off runners + seed_data.py (deterministic seed generator)
├── tests/           pytest unit tests (guardrails contract)
├── data/
│   ├── seed/        committed seed dataset (CSV + JSONL, ~45KB)
│   └── ...          artefacts you produce (syntheses, eval results — gitignored)
├── Dockerfile, .dockerignore
└── docs/tutorial/   plan + brief + the eight phase files
```

## Tear-down (single command)

Everything in this tutorial lives inside one Azure resource group named `rg-acct-strategy`. Phase 7 ends with:

```bash
az group delete --name "$RG" --yes --no-wait
az group list --query "[?name=='$RG'].name" -o tsv   # must print nothing
```

Save these *before* tear-down:

- The eval results CSV (`data/eval_results.csv`).
- The LangSmith trace screenshot from Phase 6.
- A copy of one `curl` response from the live endpoint in Phase 7.

The repo plus those three artefacts are what makes the deployment, observability, and eval claims defensible after the resources are gone.

## What's claimable after this

Each bullet maps to one phase in the tutorial.

| Claim | Evidence |
|---|---|
| Designed agentic workflows | Phase 4 graph + nodes |
| Built multi-agent systems with qual+quant inputs | Phases 1, 4 |
| Orchestration + state, human-in-the-loop | Phase 4 (gate + interrupt + resume) |
| RAG with source traceability | Phase 2 + Phase 4 citation contract |
| Tool/function calling into predictive models | Phase 3 |
| Model selection + deployment in cloud | Phases 0, 7 |
| Evals harness, benchmarked quality | Phase 5 results CSV |
| Observability — tracing, cost, latency | Phase 6 LangSmith trace |
| Guardrails + compliance — data minimization | Phase 6 unit tests + wired into extract |
