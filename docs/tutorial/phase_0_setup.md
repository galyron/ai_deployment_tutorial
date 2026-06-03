# Phase 0 — Setup & Scaffolding

**Capabilities touched:** deployment foundation, project hygiene.
**Exit criterion:** a Python script that authenticates to Azure OpenAI and to Azure AI Search and prints a response from each.
**Budget:** 1.5–2h.

---

### Step 0.1 — Install local prerequisites

**Goal:** Have `uv`, `az`, Docker, and `jq` available in the shell.

**Do:**
- Install Homebrew if missing.
- Install `uv` (Python tooling), Azure CLI, Docker Desktop, `jq`.
- Start Docker Desktop once so its daemon is running.

**Code / commands:**
```bash
# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# az + docker + jq
brew install azure-cli jq
brew install --cask docker

open -a Docker
```

**Self-check:**
```bash
uv --version          # e.g. uv 0.5.x
az --version | head   # azure-cli 2.x
docker info > /dev/null && echo "docker ok"
jq --version          # jq-1.7.x
```
All four lines must succeed without errors.

**If broken:**
- `uv: command not found` → restart the shell or `source ~/.zshrc`; the installer appends `~/.local/bin` to PATH.
- `docker info` fails → Docker Desktop is still booting; wait for the whale icon to stop animating.

**Time estimate:** ~10m.

---

### Step 0.2 — Sign up for Azure and set a 25 EUR budget alert

**Goal:** A fresh Azure subscription with a hard-visible budget alert so you never wonder what you're spending.

**Do:**
- Sign up at `https://azure.microsoft.com/free` with a personal email. Free tier grants ~$200 credits for 30 days.
- In Portal, go to *Subscriptions → your subscription → Budgets → + Add*.
- Create a budget named `tutorial-budget`, amount `25`, currency `EUR`, period `Monthly`, alert at `80%` actual and `100%` forecasted, recipient = your email.

**Code / commands:** None — Portal only.

**Self-check:** *Portal → Cost Management → Budgets* lists `tutorial-budget` at 25 EUR, status `Active`. Within ~10 minutes you should receive a Microsoft confirmation email for the alert recipient.

**If broken:**
- "No subscription found" → the free signup hasn't propagated yet; wait 5 minutes and refresh.
- Budget creation requires the *Cost Management Contributor* role; on a fresh subscription you have it by default. If not, you signed in with a guest account.

**Time estimate:** ~15m.

---

### Step 0.3 — Log in via CLI and create the resource group

**Goal:** All work scoped to one resource group so tear-down is one command.

**Do:**
- `az login` and select the new subscription.
- Create `rg-acnt-strat-synth` in `swedencentral`.
- Export the resource group name so later steps reuse it.

> **Why swedencentral.** In 2026 Microsoft picks two regions per geo as "default-on" lanes where new free-tier subscriptions ship with usable Azure OpenAI quotas out of the box: **`swedencentral`** (EU) and **`eastus2`** (US-East). Every other region — including the obvious picks `westeurope`, `germanywestcentral`, `francecentral`, `uksouth`, `eastus`, `westus` — ships at *zero* default quota for production chat and modern embedding models, forcing a Foundry quota request before you can deploy anything. Stay in swedencentral unless you have a hard compliance reason to be elsewhere. (eastus2 is the equivalent US default if you must host there.)

**Code / commands:**
```bash
az login
az account set --subscription "<your-subscription-id>"

export RG=rg-acnt-strat-synth
export LOC=swedencentral
az group create --name "$RG" --location "$LOC"

# Persist for new shells
echo "export RG=$RG"  >> ~/.zshrc
echo "export LOC=$LOC" >> ~/.zshrc
```

**Self-check:**
```bash
az group show --name "$RG" --query "properties.provisioningState" -o tsv
# Expected: Succeeded
```

**If broken:**
- `LocationNotAvailableForResourceType` later → you almost certainly didn't deviate from `swedencentral`. If you did and you're hitting this on a different region, see Step 0.4's *Fallback* section.
- `az account set` errors → run `az account list -o table` to get the right `SubscriptionId`.

**Time estimate:** ~10m.

---

### Step 0.4 — Create Azure OpenAI and deploy the models

**Goal:** A live Azure OpenAI resource with `gpt-5-mini` (chat) and `text-embedding-3-small` (embeddings) deployments, both callable from Python.

> **Why this is straightforward in swedencentral.** In swedencentral (and eastus2) the relevant default quotas are non-zero out of the box:
>
> - `OpenAI.GlobalStandard.gpt-5-mini` → ~500K TPM
> - `OpenAI.GlobalStandard.text-embedding-3-small` → ~1000K TPM
>
> Most other regions ship at zero, forcing a quota request in **Azure AI Foundry** (`https://ai.azure.com`) before you can deploy anything. If you ignored Step 0.3's advice and landed elsewhere, jump to the **Fallback** at the end of this step.

**Do:**

**(a) Create the Azure OpenAI resource.**

```bash
export AOAI=aoai-acnt-strat-synth-$RANDOM
az cognitiveservices account create \
  --name "$AOAI" --resource-group "$RG" --location "$LOC" \
  --kind OpenAI --sku S0 --yes

export AOAI_ENDPOINT=$(az cognitiveservices account show --name "$AOAI" --resource-group "$RG" --query properties.endpoint -o tsv)
export AOAI_KEY=$(az cognitiveservices account keys list --name "$AOAI" --resource-group "$RG" --query key1 -o tsv)
```

**(b) Sanity-check quota.** Don't guess — the table is canonical.

```bash
az cognitiveservices usage list --location "$LOC" \
  --query "[?contains(name.value, 'gpt-5-mini') || contains(name.value, 'text-embedding-3-small')].{name:name.value, limit:limit}" \
  -o table
```

`OpenAI.GlobalStandard.gpt-5-mini` and `OpenAI.GlobalStandard.text-embedding-3-small` should both show a non-zero `limit` (~500 and ~1000 respectively). If both are zero, you're in the wrong region — jump to the **Fallback**.

**(c) Deploy `gpt-5-mini`.**

```bash
az cognitiveservices account deployment create \
  --name "$AOAI" --resource-group "$RG" \
  --deployment-name gpt-5-mini \
  --model-name gpt-5-mini --model-version "2025-08-07" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 30
```

`--sku-capacity 30` = 30K tokens/minute. Generous headroom for the tutorial; the regional cap is 500K so adjust upward if you ever need to.

> If the version `2025-08-07` is no longer in the catalog (Microsoft rolls these forward), find the current value:
> ```bash
> az cognitiveservices model list --location "$LOC" \
>   --query "[?model.name=='gpt-5-mini'].{ver:model.version, sku:model.skus[0].name}" -o table
> ```
> Note the field path is `model.name` / `model.version`, not the top-level `name` / `version`.

**(d) Deploy `text-embedding-3-small`.**

```bash
az cognitiveservices account deployment create \
  --name "$AOAI" --resource-group "$RG" \
  --deployment-name text-embedding-3-small \
  --model-name text-embedding-3-small --model-version "1" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 30
```

Vector dimension is 1536, which is what Phase 2's index schema hard-codes — so the embedding model is later swappable to `text-embedding-3-large` (3072-d, needs a schema change) or `text-embedding-ada-002` (1536-d, drop-in) without code edits beyond the deployment name.

**Self-check:**
```bash
az cognitiveservices account deployment list \
  --name "$AOAI" --resource-group "$RG" \
  --query "[].{name:name, state:properties.provisioningState}" -o table
```
Both `gpt-5-mini` and `text-embedding-3-small` rows must show `Succeeded`.

**If broken:**
- `InsufficientQuota` on either deploy → you're not in swedencentral / eastus2 (or Microsoft retired the default in your region). Go to *Fallback*.
- `DeploymentModelNotSupported` → the `model-version` is no longer current. Use the `az cognitiveservices model list` command in (c) to find the live version and re-run.
- The deployment name in `.env` (Step 0.7) must match `--deployment-name` from (c) and (d) exactly. Typos here surface as `DeploymentNotFound` later in Step 0.8.

---

**Fallback — if you must use a region other than swedencentral or eastus2.**

Most regions (westeurope, eastus, germanywestcentral, francecentral, uksouth, westus, etc.) ship with zero default quota for production chat models. The path:

1. Open `https://ai.azure.com` → bottom-left **Management center** → **Quota** → **Azure OpenAI** → select your subscription.
2. Filter region = your `$LOC`. Request quota for `GlobalStandard gpt-5-mini`, ask for **30** (= 30K TPM). Request `GlobalStandard text-embedding-3-small` the same way if its limit is also zero.
3. Justification text to paste in the form:

   > *Personal learning project. Self-paced tutorial building a small RAG + agentic synthesis app against ~50 synthetic records using LangGraph, Azure AI Search, and Azure OpenAI. Educational use only — no production traffic, no end users. Expected peak workload well under 30K TPM over the next 30 days.*

4. Small free-tier asks like this typically auto-approve within minutes; large asks queue for human review. While you wait, work through Steps 0.5–0.7. Return to (c) and (d) once approved.
5. If approval drags more than a day, the faster path is to delete the AOAI resource and recreate in `swedencentral` or `eastus2` — usually faster than the queue.

**Time estimate:** ~15m in swedencentral/eastus2. "+ async wait" if you take the fallback.

---

### Step 0.5 — Create AI Search (free tier) and Key Vault

**Goal:** A vector-search index host and a place to store secrets for the deployed app.

**Do:**
- Create AI Search with `--sku free` (one free instance per subscription; reuse if you've used the quota).
- Create Key Vault.
- Grab the AI Search admin key.

**Code / commands:**
```bash
export SEARCH=srch-acnt-strat-synth-$RANDOM
az search service create \
  --name "$SEARCH" --resource-group "$RG" --location "$LOC" \
  --sku free --partition-count 1 --replica-count 1

export SEARCH_ENDPOINT="https://$SEARCH.search.windows.net"
export SEARCH_KEY=$(az search admin-key show --service-name "$SEARCH" --resource-group "$RG" --query primaryKey -o tsv)

export KV=kv-acnt-strat-synth-$RANDOM
az keyvault create --name "$KV" --resource-group "$RG" --location "$LOC"
```

> **Cost note:** AI Search Basic is ~70 EUR/month and bills immediately. Verify the SKU below before continuing.

**Self-check:**
```bash
az search service show --name "$SEARCH" --resource-group "$RG" --query "sku.name" -o tsv
# Expected: free
az keyvault show --name "$KV" --query "properties.provisioningState" -o tsv
# Expected: Succeeded
```

**If broken:**
- `Free sku is not available because there is already a search service` → you've used your free quota in another subscription. Delete the old one or use a different subscription. Do not silently fall back to Basic.

**Time estimate:** ~15m.

---

### Step 0.6 — Initialize the local Python project with uv

**Goal:** A `uv`-managed project with the dependency set used throughout the tutorial.

> This repo *is* the Python project. `pyproject.toml`, `acnt_strat_synth/`, `scripts/`, `data/`, `docs/`, and `tests/` all live at the repo root — there's no wrapper directory. `uv init --name` sets the package name in `pyproject.toml` without creating a subfolder.

**Do:**
- From the repo root, run `uv init` to add `pyproject.toml`, `uv.lock`, and `.python-version`.
- Pin Python `3.12`.
- Add LangGraph, LangChain Azure OpenAI, Azure SDK clients, FastAPI, scikit-learn, pytest.

**Code / commands:**
```bash
# Run from the repo root (the directory that already contains README.md and docs/).
uv init --name acnt-strat-synth --python 3.12

# uv may drop a 'hello.py' starter file at the root — delete it; the project
# code lives under acnt_strat_synth/.
rm -f hello.py

uv add \
  langgraph langchain langchain-openai langchain-core \
  azure-identity azure-search-documents azure-keyvault-secrets \
  openai pydantic fastapi "uvicorn[standard]" \
  pandas pyarrow scikit-learn python-dotenv tenacity

uv add --dev pytest ruff
```

**Self-check:**
```bash
uv run python -c "import langgraph, langchain_openai, azure.search.documents, fastapi; print('ok')"
# Expected single line: ok
ls pyproject.toml uv.lock .python-version
# Expected: all three files present at the repo root
```

**If broken:**
- `Cannot determine Python interpreter` → `uv python install 3.12` then re-run `uv init`.
- A resolver conflict on `openai` vs `langchain-openai` → re-run `uv lock --upgrade`.
- `uv init` complains it can't initialize because the directory isn't empty → it shouldn't (it's non-destructive for existing files), but if it does, run `uv init --bare --name acnt-strat-synth` instead, which only writes `pyproject.toml`.
- Later phases hit `ModuleNotFoundError: No module named 'acnt_strat_synth'` → your package directory in Step 0.7 must be named exactly `acnt_strat_synth/` (underscores). Hatch auto-discovers the package by normalizing the project name's hyphens to underscores; a mismatch means no editable install.

**Time estimate:** ~10m.

---

### Step 0.7 — Wire `.env` and load it from Python

**Goal:** Local dev reads Azure config from `.env`. Nothing secret in git.

**Do:**
- Confirm `.env` is gitignored (the root `.gitignore` already excludes it).
- Write `.env` from the variables exported earlier.
- Add a `acnt_strat_synth/config.py` that loads and validates them.

**Code / commands:**
```bash
cat > .env <<EOF
AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT
AZURE_OPENAI_KEY=$AOAI_KEY
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5-mini
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small
AZURE_SEARCH_ENDPOINT=$SEARCH_ENDPOINT
AZURE_SEARCH_KEY=$SEARCH_KEY
AZURE_SEARCH_INDEX=hcp-evidence
EOF

mkdir -p acnt_strat_synth && touch acnt_strat_synth/__init__.py
```

```python
# acnt_strat_synth/config.py
from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass(frozen=True)
class Settings:
    aoai_endpoint: str = os.environ["AZURE_OPENAI_ENDPOINT"]
    aoai_key: str = os.environ["AZURE_OPENAI_KEY"]
    aoai_api_version: str = os.environ["AZURE_OPENAI_API_VERSION"]
    chat_deployment: str = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]
    embed_deployment: str = os.environ["AZURE_OPENAI_EMBED_DEPLOYMENT"]
    search_endpoint: str = os.environ["AZURE_SEARCH_ENDPOINT"]
    search_key: str = os.environ["AZURE_SEARCH_KEY"]
    search_index: str = os.environ["AZURE_SEARCH_INDEX"]

settings = Settings()
```

**Self-check:**
```bash
uv run python -c "from acnt_strat_synth.config import settings; print(settings.chat_deployment, settings.search_endpoint)"
# Expected: gpt-5-mini https://srch-acnt-strat-synth-XXXXX.search.windows.net
```

**If broken:**
- `KeyError` → an env var wasn't exported in the current shell; reload `.env` or re-source `~/.zshrc`.

**Time estimate:** ~10m.

---

### Step 0.8 — Hello-world round-trip to both services

**Goal:** Prove auth works to Azure OpenAI (chat + embedding) and to AI Search.

**Do:**
- Write `scripts/hello.py` that calls chat, embedding, and the Search service stats endpoint.
- Run it.

**Code / commands:**
```python
# scripts/hello.py
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
from acnt_strat_synth.config import settings

chat = AzureChatOpenAI(
    azure_endpoint=settings.aoai_endpoint,
    api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.chat_deployment,
)
print("chat:", chat.invoke("Say 'pong' and nothing else.").content)

emb = AzureOpenAIEmbeddings(
    azure_endpoint=settings.aoai_endpoint,
    api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.embed_deployment,
)
v = emb.embed_query("ping")
print("embedding dims:", len(v))

idx_client = SearchIndexClient(settings.search_endpoint, AzureKeyCredential(settings.search_key))
stats = idx_client.get_service_statistics()
print("search storage used:", stats["counters"]["storage_size_counter"]["usage"], "bytes")
```

```bash
uv run python scripts/hello.py
```

**Self-check:** Output contains three lines:
```
chat: pong
embedding dims: 1536
search storage used: 0 bytes
```
(`embedding dims` is `1536` for `text-embedding-3-small`. The vector field in Phase 2 is hard-coded to 1536, so the embedding model is drop-in swappable with `text-embedding-ada-002` if you ever need to. Switching up to `text-embedding-3-large` would change the dimension to 3072 and require a Phase 2 schema edit.)

**If broken:**
- `401 Unauthorized` → wrong key in `.env`. Rotate with `az cognitiveservices account keys list`.
- `DeploymentNotFound` → `azure_deployment` must match the deployment *name* from Step 0.4, not the model name.
- `404 from Search` → endpoint URL is wrong; must be `https://<service>.search.windows.net`.

**Time estimate:** ~15m.

---

Phase 0 is done when Step 0.8's three-line output renders. Commit now: `git add -A && git commit -m "phase 0: setup scaffolding"`.
