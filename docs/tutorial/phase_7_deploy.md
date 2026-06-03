# Phase 7 — Deploy

**Capabilities touched:** model selection + deployment in cloud.
**Exit criterion:** `curl` against a public Azure Container Apps URL returns HTTP 200 with a valid synthesis JSON for a known account.
**Budget:** 1.5h. **Protected phase — do not cut.**

---

### Step 7.1 — Wrap the graph in a FastAPI endpoint

**Goal:** A single `POST /synthesize` route that accepts an account ID, runs the graph, and returns the synthesis JSON.

**Do:**
- Create `src/api/main.py`.
- Reuse `build_graph()` from Phase 4. Load `.env` on startup.

**Code / commands:**
```bash
mkdir -p src/api
touch src/api/__init__.py
```

```python
# src/api/main.py
from dotenv import load_dotenv; load_dotenv()
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.graph.build import build_graph

app = FastAPI(title="Account Strategy Synthesizer")
_graph = build_graph()

class SynthRequest(BaseModel):
    account_id: str
    review_required: bool = False

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/synthesize")
def synthesize(req: SynthRequest):
    cfg = {"configurable": {"thread_id": f"api-{req.account_id}"}}
    try:
        state = _graph.invoke(req.model_dump(), config=cfg)
    except KeyError as e:
        raise HTTPException(404, str(e))
    syn = state.get("synthesis")
    if syn is None:
        return {"account_id": req.account_id, "synthesis": None,
                "note": "awaiting review (review_required=True)"}
    return {"account_id": req.account_id, "synthesis": syn.model_dump()}
```

**Self-check:**
```bash
uv run uvicorn src.api.main:app --port 8000 &
sleep 3
curl -s http://localhost:8000/healthz
curl -sX POST http://localhost:8000/synthesize -H 'content-type: application/json' \
     -d '{"account_id":"HCP-002"}' | jq '.synthesis.headline, .synthesis.competitive_risk_flag'
kill %1
```
`healthz` returns `{"status":"ok"}`; the second call prints a non-null headline and a boolean.

**If broken:**
- 500 on `/synthesize` → check the uvicorn log; missing env vars are the most common cause. The endpoint requires the same `.env` Phase 0 set up.

**Time estimate:** ~15m.

---

### Step 7.2 — Multi-stage Dockerfile with uv

**Goal:** A small image that runs the FastAPI app with the right Python and dependencies.

**Do:**
- Write a multi-stage Dockerfile using `uv` for resolve + install.
- `.dockerignore` excludes `data/`, `.venv/`, `__pycache__/`, `.git/`.

**Code / commands:**

```dockerfile
# Dockerfile
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && cp /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```
# .dockerignore
.venv/
data/
docs/
.git/
__pycache__/
*.pyc
.env
```

**Self-check:**
```bash
docker build -t acnt-strat-synth:local .
docker images | grep acnt-strat-synth
# Expected: a tag 'local' with a size around 600-800 MB.
```

**If broken:**
- `uv: not found` inside the image → the install path differs in the base image; replace with `pip install uv` as a fallback.

**Time estimate:** ~20m.

---

### Step 7.3 — Smoke-test the container locally

**Goal:** Container responds to `/synthesize` using the local `.env`.

**Do:**
- Run with `.env` mounted via `--env-file`.

**Code / commands:**
```bash
docker run --rm -d --name acnt-strat-synth -p 8000:8000 --env-file .env acnt-strat-synth:local
sleep 5
curl -s http://localhost:8000/healthz
curl -sX POST http://localhost:8000/synthesize -H 'content-type: application/json' \
     -d '{"account_id":"HCP-001"}' | jq '.synthesis.headline'
docker stop acnt-strat-synth
```

**Self-check:** Both curls succeed; `synthesis.headline` prints.

**If broken:**
- Container exits immediately → `docker logs acnt-strat-synth` shows the traceback. Almost always a missing env var.

**Time estimate:** ~10m.

---

### Step 7.4 — Push secrets to Key Vault

**Goal:** The deployed app reads keys from Key Vault, not from a baked-in `.env`.

**Do:**
- Store the four sensitive values: `AZURE_OPENAI_KEY`, `AZURE_SEARCH_KEY`, `LANGSMITH_API_KEY` (if used), and a single combined `APP_CONFIG` JSON for non-secret defaults — or just push each separately.

**Code / commands:**
```bash
az keyvault secret set --vault-name "$KV" --name AZURE-OPENAI-KEY  --value "$AOAI_KEY"      > /dev/null
az keyvault secret set --vault-name "$KV" --name AZURE-SEARCH-KEY  --value "$SEARCH_KEY"    > /dev/null
[[ -n "$LANGSMITH_API_KEY" ]] && az keyvault secret set --vault-name "$KV" --name LANGSMITH-API-KEY --value "$LANGSMITH_API_KEY" > /dev/null
echo "stored:"
az keyvault secret list --vault-name "$KV" --query "[].name" -o tsv
```

**Self-check:** The listed names include `AZURE-OPENAI-KEY` and `AZURE-SEARCH-KEY`.

**If broken:**
- `Forbidden` → your user lacks `Key Vault Secrets Officer` on the vault. Grant: `az role assignment create --role "Key Vault Secrets Officer" --assignee $(az ad signed-in-user show --query id -o tsv) --scope $(az keyvault show -n "$KV" --query id -o tsv)`.

**Time estimate:** ~15m.

---

### Step 7.5 — Create ACR and build the image into it

**Goal:** A registry the Container App can pull from.

**Do:**
- Create an Azure Container Registry, build remotely with `az acr build` (no local push needed).

**Code / commands:**
```bash
export ACR=acracntstratsynth$RANDOM
az acr create --name "$ACR" --resource-group "$RG" --sku Basic --admin-enabled false
az acr build --registry "$ACR" --image acnt-strat-synth:v1 .
```

**Self-check:**
```bash
az acr repository show-tags --name "$ACR" --repository acnt-strat-synth -o tsv
# Expected: v1
```

**If broken:**
- ACR name conflict → ACR names are globally unique; bump `$RANDOM` and re-run.
- Build OOM in ACR Basic → switch to `--sku Standard` (still cheap; about ~0.16 EUR/day prorated).

**Time estimate:** ~15m.

---

### Step 7.6 — Deploy to Container Apps with Key Vault secrets

**Goal:** A live Container App pulling the image from ACR, reading secrets from Key Vault via managed identity.

**Do:**
- Create a Container Apps environment.
- Create the Container App with system-assigned identity, ACR access via that identity, and `secretref` env vars pointing at Key Vault.

**Code / commands:**
```bash
export CAENV=cae-acnt-strat-synth
export APP=acnt-strat-synth-api

az containerapp env create --name "$CAENV" --resource-group "$RG" --location "$LOC"

az containerapp create \
  --name "$APP" --resource-group "$RG" --environment "$CAENV" \
  --image "$ACR.azurecr.io/acnt-strat-synth:v1" \
  --target-port 8000 --ingress external \
  --registry-server "$ACR.azurecr.io" --registry-identity system \
  --system-assigned \
  --min-replicas 0 --max-replicas 1 \
  --cpu 0.5 --memory 1.0Gi

# Grant the app's identity access to ACR (pull) and Key Vault (get secrets).
APP_PRINCIPAL_ID=$(az containerapp identity show --name "$APP" --resource-group "$RG" --query principalId -o tsv)
az role assignment create --role AcrPull --assignee "$APP_PRINCIPAL_ID" --scope "$(az acr show -n "$ACR" --query id -o tsv)"
az role assignment create --role "Key Vault Secrets User" --assignee "$APP_PRINCIPAL_ID" --scope "$(az keyvault show -n "$KV" --query id -o tsv)"

# Wire Key Vault refs as Container Apps secrets.
KV_URI=$(az keyvault show -n "$KV" --query properties.vaultUri -o tsv)
az containerapp secret set --name "$APP" --resource-group "$RG" --secrets \
  aoai-key="keyvaultref:${KV_URI}secrets/AZURE-OPENAI-KEY,identityref:system" \
  search-key="keyvaultref:${KV_URI}secrets/AZURE-SEARCH-KEY,identityref:system"

# Set non-secret env + bind secrets to env names the app expects.
az containerapp update --name "$APP" --resource-group "$RG" --set-env-vars \
  AZURE_OPENAI_ENDPOINT="$AOAI_ENDPOINT" \
  AZURE_OPENAI_API_VERSION="2024-10-21" \
  AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-5-mini" \
  AZURE_OPENAI_EMBED_DEPLOYMENT="text-embedding-3-small" \
  AZURE_SEARCH_ENDPOINT="$SEARCH_ENDPOINT" \
  AZURE_SEARCH_INDEX="hcp-evidence" \
  AZURE_OPENAI_KEY=secretref:aoai-key \
  AZURE_SEARCH_KEY=secretref:search-key
```

**Self-check:**
```bash
az containerapp show -n "$APP" -g "$RG" --query "properties.runningStatus" -o tsv
# Expected: Running
az containerapp show -n "$APP" -g "$RG" --query "properties.configuration.ingress.fqdn" -o tsv
# Expected: a *.azurecontainerapps.io URL — note it down.
```

**If broken:**
- `Status: Failed` revision → `az containerapp logs show --name $APP --resource-group $RG --tail 200`. Almost always a secret name mismatch.

**Time estimate:** ~20m.

---

### Step 7.7 — Hit the live endpoint

**Goal:** A `curl` against the public FQDN returns a real synthesis. This is the screenshot.

**Do:**
- Resolve the FQDN, curl both `/healthz` and `/synthesize`.

**Code / commands:**
```bash
export APP_URL="https://$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
echo "$APP_URL"
curl -s "$APP_URL/healthz"
curl -sX POST "$APP_URL/synthesize" -H 'content-type: application/json' \
     -d '{"account_id":"HCP-002"}' | tee /tmp/synth.json | jq '.synthesis.headline, .synthesis.competitive_risk_flag, (.synthesis.claims | length)'
```

**Self-check:**
- `/healthz` returns `{"status":"ok"}`.
- `/synthesize` returns HTTP 200 with a non-null headline, a boolean flag, and a claims length >= 3.

**If broken:**
- 200 on healthz, 500 on synthesize → almost always a Key Vault secret didn't resolve at app startup. Restart the revision: `az containerapp revision restart --name $APP --resource-group $RG --revision $(az containerapp revision list -n $APP -g $RG --query "[0].name" -o tsv)`.
- AI Search returns no results → the index was created locally but is hosted on AI Search; data is already there. If results are empty, the wrong `AZURE_SEARCH_INDEX` env was set.

**Time estimate:** ~10m.

---

### Step 7.8 — Tear-down

**Goal:** Delete the resource group. Verify nothing's left to bill.

**Do:**
- `az group delete` on the whole `$RG`. Single command nukes Container Apps, ACR, AI Search, Azure OpenAI, Key Vault.

**Code / commands:**
```bash
az group delete --name "$RG" --yes --no-wait
# Wait ~3-5 minutes, then verify:
az group list --query "[?name=='$RG'].name" -o tsv
# Expected: empty output.
```

**Self-check:** The verification command prints nothing. `az cognitiveservices account list -o table` and `az search service list -o table` both show no resources from this tutorial.

**If broken:**
- Group still listed after 10 minutes → some resources have delete locks. `az lock list --resource-group "$RG"` and remove with `az lock delete`.

> Save the final eval results CSV and the LangSmith trace screenshot *before* tear-down. The repo + those two artefacts are what makes the claims defensible after the resources are gone.

**Time estimate:** ~5m.

---

Phase 7 done. Commit: `git add -A && git commit -m "phase 7: container apps deploy + tear-down"`.
