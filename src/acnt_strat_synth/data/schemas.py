from typing import Literal
from pydantic import BaseModel, Field

# Literal restricts a string to a fixed set of allowed values. Pydantic rejects
# anything else when a model is constructed, so we get enum-like behaviour
# without an Enum subclass and downstream code can rely on the field being
# one of the listed strings.
Segment    = Literal["high_potential", "growing", "stable", "at_risk"]
Territory  = Literal["T-North", "T-South", "T-East", "T-West", "T-Central"]
SourceType = Literal["rep_call_note", "msl_summary", "comp_intel", "market_research"]


# Pydantic BaseModel: when you call AccountQuant(**row), pydantic checks every
# field against the declared type and any Field(...) constraints. Invalid data
# raises ValidationError at construction; valid data becomes a regular Python
# object with typed attributes (acct.segment, acct.rx_volume_last_q, ...).
# This is the validation "boundary" -- past this point downstream code can
# trust the shape of what it received.
class AccountQuant(BaseModel):
    account_id: str
    segment: Segment
    territory: Territory
    # Field(ge=0) means "must be >= 0"; le=N means "must be <= N". Pydantic
    # enforces these on construction so out-of-range values fail fast here
    # instead of producing weird numbers deep inside the predictive scorer
    # or the synthesis prompt.
    rx_volume_last_q: int = Field(ge=0)
    rx_trend_pct: float = Field(ge=-50, le=50)
    call_count_last_q: int = Field(ge=0, le=20)
    market_potential_score: int = Field(ge=1, le=10)
    nps_proxy: int = Field(ge=-100, le=100)


# One qualitative document (a rep call note, MSL summary, comp-intel snippet,
# or market-research paragraph). source_type tells downstream code which kind
# it is, so retrieval can filter on it and the synthesis prompt can group by
# it ("for each rep_call_note, ...").
class QualDoc(BaseModel):
    account_id: str
    source_type: SourceType
    text: str


