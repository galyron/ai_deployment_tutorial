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
- Create `rg-acnt-strat-synth` in `westeurope` (closest region with Azure OpenAI capacity at time of writing — adjust if your free trial defaults elsewhere).
- Export the resource group name so later steps reuse it.

**Code / commands:**
```bash
az login
az account set --subscription "<your-subscription-id>"

export RG=rg-acnt-strat-synth
export LOC=westeurope
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
- `LocationNotAvailableForResourceType` later → pick a different region. `westeurope`, `swedencentral`, `eastus` are good defaults for Azure OpenAI.
- `az account set` errors → run `az account list -o table` to get the right `SubscriptionId`.

**Time estimate:** ~10m.

---

### Step 0.4 — Create Azure OpenAI, check quota, deploy embeddings, request chat quota

**Goal:** A live Azure OpenAI resource, a deployed embedding model you can call immediately, and a pending GPT-4o quota request so chat is unblocked by the time you need it.

> **Why this step is longer than it looks.** On a fresh free-tier subscription in 2026, Microsoft ships **zero default quota for GPT-4o** across all SKUs (`Standard`, `GlobalStandard`, `DataZoneStandard`, `Batch`, `Provisioned`). You have to request it. Embedding quota is also zero for the modern `text-embedding-3-*` models, but the older `text-embedding-ada-002` ships with usable default quota (~240K TPM) and produces the same 1536-dimensional vectors Phase 2 expects. So: deploy ada-002 now, request GPT-4o quota in parallel, continue to Step 0.5 while you wait.
>
> **Where quota lives.** Azure OpenAI quota management moved into **Azure AI Foundry** (`https://ai.azure.com`). The older *Portal → Cognitive Services → Quotas* path is deprecated for OpenAI. The `az cognitiveservices` CLI still works against the same resource — only the management UI moved.

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

**(b) Inspect what quota you actually have in this region.** Don't guess — the table is canonical.

```bash
az cognitiveservices usage list --location "$LOC" \
  --query "[?contains(name.value, 'gpt-4o') || contains(name.value, 'embedding')].{name:name.value, current:currentValue, limit:limit}" \
  -o table
```

Read off the `limit` column for the two rows you care about:
- `OpenAI.GlobalStandard.gpt-4o` — likely `0` on a fresh sub. That's the row you'll request quota for in step (d).
- `OpenAI.Standard.text-embedding-ada-002` — should be `240` or similar. That's what you'll deploy in step (c).

**(c) Deploy `text-embedding-ada-002`** — usable immediately, 1536-d, same dimension as `text-embedding-3-small`, Phase 2 needs no changes.

```bash
az cognitiveservices account deployment create \
  --name "$AOAI" --resource-group "$RG" \
  --deployment-name text-embedding-ada-002 \
  --model-name text-embedding-ada-002 --model-version "2" --model-format OpenAI \
  --sku-name Standard --sku-capacity 10
```

(`--sku-capacity 10` means 10K tokens/minute — plenty for the tutorial, well under the 240K cap.)

**(d) Request GPT-4o quota in Azure AI Foundry.** This is the gating action. Do it now and move on; approval usually lands in minutes to a few hours.

1. Open `https://ai.azure.com`.
2. Bottom-left → **Management center** → **Quota**.
3. **Azure OpenAI** tab → select your subscription.
4. Filter: region = your `$LOC`, model = `gpt-4o`, SKU = `GlobalStandard`.
5. Click **Request quota**. Ask for **30** (= 30K TPM). Small free-tier asks like this typically auto-approve.

> **If you don't want to wait:** check whether another region has non-zero defaults.
>
> ```bash
> for region in swedencentral eastus eastus2 northcentralus; do
>   echo "== $region =="
>   az cognitiveservices usage list --location "$region" \
>     --query "[?name.value=='OpenAI.GlobalStandard.gpt-4o'].{limit:limit}" -o tsv
> done
> ```
>
> If one shows a non-zero limit, delete the westeurope AOAI account, recreate in that region, and re-export `$LOC`, `$AOAI`, `$AOAI_ENDPOINT`, `$AOAI_KEY`.

**(e) Once Foundry approval lands, deploy `gpt-4o`** with the `GlobalStandard` SKU.

```bash
az cognitiveservices account deployment create \
  --name "$AOAI" --resource-group "$RG" \
  --deployment-name gpt-4o \
  --model-name gpt-4o --model-version "2024-08-06" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10
```

While waiting for approval, work through **Steps 0.5 through 0.7** (AI Search, Key Vault, `uv` project, `.env`). Return here to run (e), then jump to Step 0.8.

**Self-check (after (c)):** The embedding deployment is live.
```bash
az cognitiveservices account deployment show \
  --name "$AOAI" --resource-group "$RG" --deployment-name text-embedding-ada-002 \
  --query "properties.provisioningState" -o tsv
# Expected: Succeeded
```

**Self-check (after (e)):** Both deployments are live.
```bash
az cognitiveservices account deployment list \
  --name "$AOAI" --resource-group "$RG" \
  --query "[].{name:name, state:properties.provisioningState}" -o table
# Expected: gpt-4o and text-embedding-ada-002 both Succeeded.
```

**If broken:**
- `InsufficientQuota` on the embedding deploy → check the `limit` for `OpenAI.Standard.text-embedding-ada-002` was actually non-zero in (b). If it's zero, request it in Foundry the same way as gpt-4o.
- `DeploymentModelNotSupported` → region lacks that exact `model-version`. Run `az cognitiveservices model list --location "$LOC" --query "[?name=='gpt-4o'].{ver:version}" -o table` to see available versions; use the newest one.
- Foundry quota request still pending after a day → submit a smaller ask (10 instead of 30), or pivot to a different region using the loop above.

**Time estimate:** ~15m active. Foundry quota approval is async; treat (e) as a "return to this step later" gate.

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

**Do:**
- Create `account-strategy-synthesizer/` and initialize with `uv`.
- Pin Python `3.12`.
- Add LangGraph, LangChain Azure OpenAI, Azure SDK clients, FastAPI, scikit-learn, pytest.

**Code / commands:**
```bash
mkdir -p ~/code && cd ~/code
uv init account-strategy-synthesizer --python 3.12
cd account-strategy-synthesizer

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
```

**If broken:**
- `Cannot determine Python interpreter` → `uv python install 3.12` then re-run `uv init`.
- A resolver conflict on `openai` vs `langchain-openai` → re-run `uv lock --upgrade`.

**Time estimate:** ~10m.

---

### Step 0.7 — Wire `.env` and load it from Python

**Goal:** Local dev reads Azure config from `.env`. Nothing secret in git.

**Do:**
- Confirm `.env` is gitignored (the root `.gitignore` already excludes it).
- Write `.env` from the variables exported earlier.
- Add a `src/config.py` that loads and validates them.

**Code / commands:**
```bash
cat > .env <<EOF
AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT
AZURE_OPENAI_KEY=$AOAI_KEY
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-ada-002
AZURE_SEARCH_ENDPOINT=$SEARCH_ENDPOINT
AZURE_SEARCH_KEY=$SEARCH_KEY
AZURE_SEARCH_INDEX=hcp-evidence
EOF

mkdir -p src && touch src/__init__.py
```

```python
# src/config.py
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
uv run python -c "from src.config import settings; print(settings.chat_deployment, settings.search_endpoint)"
# Expected: gpt-4o https://srch-acnt-strat-synth-XXXXX.search.windows.net
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
from src.config import settings

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
(`embedding dims` should be `1536` for both `text-embedding-ada-002` and `text-embedding-3-small` — the vector field in Phase 2 is hard-coded to 1536, so switching between the two later requires no schema change.)

**If broken:**
- `401 Unauthorized` → wrong key in `.env`. Rotate with `az cognitiveservices account keys list`.
- `DeploymentNotFound` → `azure_deployment` must match the deployment *name* from Step 0.4, not the model name.
- `404 from Search` → endpoint URL is wrong; must be `https://<service>.search.windows.net`.

**Time estimate:** ~15m.

---

Phase 0 is done when Step 0.8's three-line output renders. Commit now: `git add -A && git commit -m "phase 0: setup scaffolding"`.
