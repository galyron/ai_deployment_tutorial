from typing import TypedDict, Optional
from pydantic import BaseModel, Field

class EvidenceItem(BaseModel):
    chunk_id: str
    account_id: str
    source_type: str
    text: str

class Claim(BaseModel):
    statement: str
    cites: list[str] = Field(description="chunk_id values that support this statement; at least one")

class Synthesis(BaseModel):
    account_id: str
    headline: str
    claims: list[Claim]
    next_best_action: str
    competitive_risk_flag: bool
    risk_score: float

class GraphState(TypedDict, total=False):
    account_id: str
    evidence: list[EvidenceItem]
    score: Optional[dict]
    synthesis: Optional[Synthesis]
    review_required: bool
    approved: Optional[bool]