import re, uuid
from acnt_strat_synth.data.loader import load_qual
from pydantic import BaseModel

class Chunk(BaseModel):
    id: str
    account_id: str
    source_type: str
    text: str

def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= 30]

def build_chunks() -> list[Chunk]:
    out = []
    for doc in load_qual():
        for para in split_paragraphs(doc.text) or [doc.text]:
            out.append(Chunk(
                id=str(uuid.uuid4()),
                account_id=doc.account_id,
                source_type=doc.source_type,
                text=para,
            ))
    return out