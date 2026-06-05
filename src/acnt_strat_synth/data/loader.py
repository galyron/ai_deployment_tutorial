import csv
import json
from pathlib import Path
from acnt_strat_synth.data.schemas import AccountQuant, QualDoc
from collections.abc import Iterator

# SEED_DIR resolves to <repo_root>/data/seed regardless of where Python is
# invoked from. Breakdown:
#   __file__              -> .../src/acnt_strat_synth/data/loader.py
#   .resolve()            -> absolute, symlink-free path
#   .parents[3]           -> three levels up: out of data/, out of
#                            acnt_strat_synth/, out of src/, into repo root.
# Using __file__ instead of a relative string like "data/seed" means callers
# can run scripts from any working directory without breaking the lookup.
SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed"
QUANT_PATH = SEED_DIR / "accounts_quant.csv"
QUAL_PATH  = SEED_DIR / "accounts_qual.jsonl"

# CSV stores everything as text. Pydantic v2 can auto-coerce most strings,
# but being explicit here keeps the boundary visible and avoids relying on
# coercion rules that might change between pydantic versions. These two sets
# enumerate which columns to cast and to what numeric type.
_INT_FIELDS   = {"rx_volume_last_q", "call_count_last_q", "market_potential_score", "nps_proxy"}
_FLOAT_FIELDS = {"rx_trend_pct"}


def _coerce_quant_row(row: dict) -> dict:
    """Cast numeric CSV columns back to int/float before pydantic sees them."""
    out = dict(row)  # copy first so we don't mutate csv.DictReader's row in-place
    for k in _INT_FIELDS:   out[k] = int(out[k])
    for k in _FLOAT_FIELDS: out[k] = float(out[k])
    return out


def load_quant() -> list[AccountQuant]:
    """Eagerly load the 50-row CSV and return validated AccountQuant objects."""
    # csv.DictReader yields one dict per data row, keyed by the column names
    # from the header line. The list comprehension validates each row through
    # the schema; any malformed row raises ValidationError here, at the
    # boundary, instead of producing nonsense further along.
    with QUANT_PATH.open() as f:
        return [AccountQuant(**_coerce_quant_row(r)) for r in csv.DictReader(f)]


def load_qual() -> list[QualDoc]:
    """Eagerly load the JSONL file and return validated QualDoc objects."""
    # JSONL = "one JSON object per line". splitlines() returns each line as a
    # string; the `if line.strip()` guard skips blank lines so a trailing
    # newline at the end of the file doesn't blow up json.loads.
    return [QualDoc(**json.loads(line))
            for line in QUAL_PATH.read_text().splitlines() if line.strip()]


def _qual_by_account() -> dict[str, list[QualDoc]]:
    """Same data as load_qual(), but grouped into a dict keyed by account_id."""
    grouped: dict[str, list[QualDoc]] = {}
    with QUAL_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = QualDoc(**json.loads(line))
            # setdefault(key, []) returns the existing list for that key, or
            # creates and returns an empty one if the key is new. Either way
            # we append to the returned list -- a concise group-by idiom.
            grouped.setdefault(doc.account_id, []).append(doc)
    return grouped


def iter_accounts() -> Iterator[tuple[AccountQuant, list[QualDoc]]]:
    """Yield (quant, docs) pairs one account at a time.

    The function is a generator: every `yield` pauses execution and hands the
    next pair to whoever is iterating over the result. Use this when you want
    to process accounts one by one (memory-friendly, predictable) instead of
    materialising all 50 quant+qual sets at once.
    """
    # Build the qual lookup once up front. Without this we'd re-read the qual
    # file inside every loop iteration -- O(N^2) instead of O(N).
    qual_idx = _qual_by_account()
    for q in load_quant():
        # .get(key, default) returns the default (an empty list here) when an
        # account has no qualitative docs at all -- e.g. HCP-005 in the seed
        # data. We still yield that account; callers need to see all 50 IDs,
        # including the empty-qual one, so the graceful-degradation tests
        # downstream can fire on it.
        yield q, qual_idx.get(q.account_id, [])