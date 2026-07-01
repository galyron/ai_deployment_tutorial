import json
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from acnt_strat_synth.config import settings

client = SearchClient(settings.search_endpoint, settings.search_index, AzureKeyCredential(settings.search_key))
docs = [json.loads(l) for l in open("data/chunks_embedded.jsonl")]

BATCH = 100
for i in range(0, len(docs), BATCH):
    client.upload_documents(docs[i:i+BATCH])
print("uploaded", len(docs))