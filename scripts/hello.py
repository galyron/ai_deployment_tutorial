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
print("search storage used:", stats.counters.storage_size_counter.usage, "bytes")
