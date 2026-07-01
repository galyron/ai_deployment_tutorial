from dataclasses import dataclass
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from langchain_openai import AzureOpenAIEmbeddings
from acnt_strat_synth.config import settings

@dataclass
class Evidence:
    account_id: str
    source_type: str
    text: str
    score: float

_client = SearchClient(settings.search_endpoint, settings.search_index, AzureKeyCredential(settings.search_key))
_emb = AzureOpenAIEmbeddings(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.embed_deployment,
)

def retrieve(account_id: str, query: str, k: int = 8) -> list[Evidence]:
    qv = _emb.embed_query(query)
    vq = VectorizedQuery(vector=qv, k_nearest_neighbors=k, fields="content_vector")
    results = _client.search(
        search_text=None,
        vector_queries=[vq],
        filter=f"account_id eq '{account_id}'",
        select=["account_id", "source_type", "text"],
        top=k,
    )
    return [Evidence(r["account_id"], r["source_type"], r["text"], r["@search.score"]) for r in results]