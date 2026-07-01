from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchableField, SearchField, SearchFieldDataType,
    VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile,
)
from acnt_strat_synth.config import settings

client = SearchIndexClient(settings.search_endpoint, AzureKeyCredential(settings.search_key))

fields = [
    SimpleField(name="id", type=SearchFieldDataType.String, key=True),
    SimpleField(name="account_id", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="source_type", type=SearchFieldDataType.String, filterable=True),
    SearchableField(name="text", type=SearchFieldDataType.String),
    SearchField(
        name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable=True, vector_search_dimensions=1536,
        vector_search_profile_name="hnsw-profile",
    ),
]
vs = VectorSearch(
    algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
    profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")],
)
client.create_or_update_index(SearchIndex(name=settings.search_index, fields=fields, vector_search=vs))
print("index ready:", settings.search_index)