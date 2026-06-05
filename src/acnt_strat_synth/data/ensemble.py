from typing import TypedDict
from acnt_strat_synth.data.loader import load_quant, _qual_by_account


# TypedDict declares the SHAPE of a dict for type checkers (mypy, pyright) but
# carries zero runtime overhead -- a Payload IS just a plain dict at runtime.
# We use TypedDict here instead of a pydantic BaseModel because the loader
# already validated the inputs; re-validating at this layer would be wasted
# work. Use pydantic when you need runtime validation, TypedDict when you
# just want type-checked dict access.
class Payload(TypedDict):
    account_id: str
    segment: str
    territory: str
    features: dict[str, float | int]      # numeric inputs the predictive tool reads (Phase 3)
    docs_by_source: dict[str, list[str]]  # qualitative text grouped by source_type (Phase 4)


# The features the predictive tool (Phase 3) actually consumes. Pulled out as
# a list so the field order is stable AND the source of truth is one constant
# instead of being repeated in every call site that builds the features dict.
_FEATURE_FIELDS = ["rx_volume_last_q", "rx_trend_pct", "call_count_last_q",
                   "market_potential_score", "nps_proxy"]


# Module-level caches: the seed data is read from disk exactly once, the
# first time this module is imported. Subsequent calls to assemble() use the
# in-memory dicts. The seed dataset is small (~45KB) and read-only, so
# import-time caching is safe and fast.
#
# Caveat: if you edit the seed files on disk during a running process, the
# changes won't show up until the process restarts.
_quant_index = {q.account_id: q for q in load_quant()}  # account_id -> AccountQuant
_qual_index  = _qual_by_account()                       # account_id -> list[QualDoc]


def assemble(account_id: str) -> Payload:
    """Build the per-account payload the LLM-facing nodes consume.

    This function is the single contract between "how the seed data is shaped
    on disk" and "how downstream code expects to see it". Phase 3, Phase 4,
    and Phase 5 all go through assemble() -- nothing else in the codebase
    needs to know about CSVs, JSONL, or pydantic models.
    """
    if account_id not in _quant_index:
        # Fail loudly at the boundary -- nothing useful downstream can come
        # from an unknown account ID, so it's better to error immediately
        # than to return some half-empty Payload.
        raise KeyError(f"Unknown account: {account_id}")
    q = _quant_index[account_id]

    # Group qualitative text by source_type so prompts can iterate them in
    # source-aware ways ("for each rep_call_note, ..."). Same setdefault
    # idiom as in loader._qual_by_account(): get-or-create the list, then
    # append.
    docs_by_source: dict[str, list[str]] = {}
    for d in _qual_index.get(account_id, []):
        docs_by_source.setdefault(d.source_type, []).append(d.text)

    return Payload(
        account_id=q.account_id,
        segment=q.segment,
        territory=q.territory,
        # getattr(obj, name) reads an attribute by its string name -- the
        # dynamic-lookup cousin of `obj.attr`. We use it here so the same
        # _FEATURE_FIELDS list drives both the dict keys and the attribute
        # reads. If we ever add a feature, only _FEATURE_FIELDS changes.
        features={f: getattr(q, f) for f in _FEATURE_FIELDS},
        docs_by_source=docs_by_source,
    )