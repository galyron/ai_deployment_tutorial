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
- Create `rg-acct-strategy` in `westeurope` (closest region with Azure OpenAI capacity at time of writing — adjust if your free trial defaults elsewhere).
- Export the resource group name so later steps reuse it.

**Code / commands:**
```bash
az login
az account set --subscription "<your-subscription-id>"

export RG=rg-acct-strategy
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

### Step 0.4 — Create Azure OpenAI and deploy GPT-4o + embeddings

**Goal:** A deployed chat model and a deployed embedding model you can call from Python.

**Do:**
- Create an Azure OpenAI resource (kind `OpenAI`, SKU `S0`).
- Deploy `gpt-4o` and `text-embedding-3-small` under known deployment names.
- Grab the endpoint and key.

**Code / commands:**
```bash
export AOAI=aoai-acct-strategy-$RANDOM
az cognitiveservices account create \
  --name "$AOAI" --resource-group "$RG" --location "$LOC" \
  --kind OpenAI --sku S0 --yes

az cognitiveservices account deployment create \
  --name "$AOAI" --resource-group "$RG" \
  --deployment-name gpt-4o \
  --model-name gpt-4o --model-version "2024-08-06" --model-format OpenAI \
  --sku-name Standard --sku-capacity 10

az cognitiveservices account deployment create \
  --name "$AOAI" --resource-group "$RG" \
  --deployment-name text-embedding-3-small \
  --model-name text-embedding-3-small --model-version "1" --model-format OpenAI \
  --sku-name Standard --sku-capacity 10

export AOAI_ENDPOINT=$(az cognitiveservices account show --name "$AOAI" --resource-group "$RG" --query properties.endpoint -o tsv)
export AOAI_KEY=$(az cognitiveservices account keys list --name "$AOAI" --resource-group "$RG" --query key1 -o tsv)
```

**Self-check:**
```bash
az cognitiveservices account deployment list \
  --name "$AOAI" --resource-group "$RG" \
  --query "[].{name:name, state:properties.provisioningState}" -o table
```
Both `gpt-4o` and `text-embedding-3-small` rows must show `Succeeded`.

**If broken:**
- `DeploymentModelNotSupported` → region lacks capacity for that model version. Try `swedencentral` or `eastus`, or check `az cognitiveservices model list --location $LOC -o table` for available `model-version` values.
- `QuotaExceeded` → lower `--sku-capacity` to `1`.

**Time estimate:** ~20m.

---

### Step 0.5 — Create AI Search (free tier) and Key Vault

**Goal:** A vector-search index host and a place to store secrets for the deployed app.

**Do:**
- Create AI Search with `--sku free` (one free instance per subscription; reuse if you've used the quota).
- Create Key Vault.
- Grab the AI Search admin key.

**Code / commands:**
```bash
export SEARCH=srch-acct-strategy-$RANDOM
az search service create \
  --name "$SEARCH" --resource-group "$RG" --location "$LOC" \
  --sku free --partition-count 1 --replica-count 1

export SEARCH_ENDPOINT="https://$SEARCH.search.windows.net"
export SEARCH_KEY=$(az search admin-key show --service-name "$SEARCH" --resource-group "$RG" --query primaryKey -o tsv)

export KV=kv-acct-$RANDOM
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
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small
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
# Expected: gpt-4o https://srch-acct-strategy-XXXXX.search.windows.net
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
(`embedding dims` may differ if you chose a different embedding model; `1536` is correct for `text-embedding-3-small`.)

**If broken:**
- `401 Unauthorized` → wrong key in `.env`. Rotate with `az cognitiveservices account keys list`.
- `DeploymentNotFound` → `azure_deployment` must match the deployment *name* from Step 0.4, not the model name.
- `404 from Search` → endpoint URL is wrong; must be `https://<service>.search.windows.net`.

**Time estimate:** ~15m.

---

Phase 0 is done when Step 0.8's three-line output renders. Commit now: `git add -A && git commit -m "phase 0: setup scaffolding"`.
