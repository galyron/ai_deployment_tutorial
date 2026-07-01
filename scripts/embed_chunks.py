from acnt_strat_synth.retrieval.chunk import build_chunks
from langchain_openai import AzureOpenAIEmbeddings
from acnt_strat_synth.config import settings
import json, pathlib

chunks = build_chunks()
emb = AzureOpenAIEmbeddings(
    azure_endpoint=settings.aoai_endpoint, api_key=settings.aoai_key,
    api_version=settings.aoai_api_version,
    azure_deployment=settings.embed_deployment,
)
vectors = emb.embed_documents([c.text for c in chunks])
assert len(vectors) == len(chunks)
assert len(vectors[0]) == 1536

records = [{**c.model_dump(), "content_vector": v} for c, v in zip(chunks, vectors)]
pathlib.Path("data/chunks_embedded.jsonl").write_text("\n".join(json.dumps(r) for r in records))
print("embedded", len(records), "chunks")