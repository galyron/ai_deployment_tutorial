"""Generate the tutorial's seed dataset.

You don't need to run this. The output is committed under `data/seed/`.
This script exists for provenance: it documents exactly how the seed was
produced and lets you regenerate it if you want to extend the dataset.

Deterministic: fixed seeds for both random.Random() instances.
Stdlib-only: needs nothing beyond Python 3.10+.

Outputs:
    data/seed/accounts_quant.csv     50 HCP accounts, one row each.
    data/seed/accounts_qual.jsonl    ~120 free-text documents tagged with
                                     account_id and source_type.

Invariants checked at the end:
    - Exactly 50 quantitative rows.
    - HCP-005 has zero qualitative documents (graceful-degradation test).
    - 'Brand-X' appears in exactly one document, namely HCP-004's
      market_research paragraph (traceability test).
    - HCP-002's comp_intel describes a competitive threat.
    - HCP-001's rep_call_notes are all positive / never mention decline.
    - HCP-003's rep_call_notes describe cooling enthusiasm.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "seed"
OUT.mkdir(parents=True, exist_ok=True)

SEGMENTS = ["high_potential", "growing", "stable", "at_risk"]
TERRITORIES = ["T-North", "T-South", "T-East", "T-West", "T-Central"]

# --- Quantitative -----------------------------------------------------------

# The five accounts whose quantitative fields are pinned to specific values.
# Phase 5 evals treat these as ground truth; do not change without updating
# src/evals/ground_truth.py.
QUANT_TENSIONS: dict[str, dict] = {
    "HCP-001": dict(segment="growing",        rx_trend_pct=-22.5, nps_proxy=60,  call_count_last_q=18, rx_volume_last_q=180, market_potential_score=8),
    "HCP-002": dict(segment="growing",        rx_trend_pct=18.0,  nps_proxy=50,  call_count_last_q=8,  rx_volume_last_q=420, market_potential_score=9),
    "HCP-003": dict(segment="stable",         rx_trend_pct=1.0,   nps_proxy=-35, call_count_last_q=10, rx_volume_last_q=320, market_potential_score=7),
    "HCP-004": dict(segment="high_potential", rx_trend_pct=5.0,   nps_proxy=20,  call_count_last_q=6,  rx_volume_last_q=260, market_potential_score=10),
    "HCP-005": dict(segment="at_risk",        rx_trend_pct=-10.0, nps_proxy=10,  call_count_last_q=2,  rx_volume_last_q=80,  market_potential_score=5),
}


def gen_quant() -> list[dict]:
    rng = random.Random(7)
    rows: list[dict] = []
    for i in range(1, 51):
        seg = rng.choices(SEGMENTS, weights=[2, 3, 4, 1])[0]
        rows.append({
            "account_id": f"HCP-{i:03d}",
            "segment": seg,
            "territory": rng.choice(TERRITORIES),
            "rx_volume_last_q": rng.randint(20, 800),
            "rx_trend_pct": round(rng.uniform(-30, 30), 1),
            "call_count_last_q": rng.randint(0, 20),
            "market_potential_score": rng.randint(3, 10),
            "nps_proxy": rng.randint(-40, 70),
        })
    by_id = {r["account_id"]: r for r in rows}
    for aid, patch in QUANT_TENSIONS.items():
        by_id[aid].update(patch)
    return rows


# --- Qualitative: hand-written tension docs ---------------------------------

TENSION_DOCS: dict[str, list[tuple[str, str]]] = {
    "HCP-001": [
        ("rep_call_note",
         "Dr. Hansen was in great spirits today. Workflow on her end looks healthy; she walked me through two recent patient cases where she's been pleased with the response. Strong relationship overall, she remains a vocal advocate for the therapy among her peers. Plan to keep cadence steady and bring the updated patient-support materials next visit."),
        ("rep_call_note",
         "Caught Dr. Hansen between consults. Tone was confident and very engaged. She praised our clinical team's responsiveness and said her patients are doing well overall. We discussed possibly hosting a small local peer-to-peer event with her presenting. Excellent visit, no asks on our side."),
        ("rep_call_note",
         "Dr. Hansen continues to be one of the most enthusiastic providers in the territory. Her clinic team likes the patient-support materials and she repeated that she has no complaints. Optimistic on the relationship trajectory; she is a clear advocate of the brand."),
        ("msl_summary",
         "MSL discussion centered on real-world evidence for adherence. Dr. Hansen showed strong interest in the most recent registry data and asked about subgroup outcomes in the elderly population. Tone was constructive and forward-looking."),
    ],
    "HCP-002": [
        ("rep_call_note",
         "Dr. Iqbal had a productive Q3. Volume continues to climb week-over-week and he is confident in the patient profile he has been targeting. Walked through the new dosing visual aid; he absorbed it quickly. Asked for additional samples to support the new-patient ramp. Good visit."),
        ("rep_call_note",
         "Solid visit with Dr. Iqbal. Steady progression on starts. He mentioned a desire to attend our upcoming regional advisory board. No friction in office workflow; office manager confirmed the patient-support hub has been responsive."),
        ("comp_intel",
         "Local intelligence flags a notable shift in Dr. Iqbal's catchment. A competing brand has begun aggressive specialist-targeted promotion in the area, including a paid speaker series featuring two providers who refer into Dr. Iqbal's practice. Patient pull-through has not yet been affected, but the contracting team should treat this account as a credible competitive watch-list candidate from this quarter onward."),
        ("market_research",
         "Specialty area in T-East shows balanced competitive dynamics overall. Class growth low-single-digit. No major guideline updates expected this cycle."),
    ],
    "HCP-003": [
        ("rep_call_note",
         "Visit with Dr. Romero felt cooler than recent calls. He mentioned the office is reviewing all current vendor relationships and that the patient-education materials we updated last quarter 'aren't quite what they were looking for.' Volume conversation was brief; he wanted to move on. Plan to dig in on specifics next call."),
        ("rep_call_note",
         "Dr. Romero raised that two of his patients have asked about alternative options recently. He did not press the point, but this is the second visit in a row where dissatisfaction has surfaced from the patient side. Office manager also noted small administrative friction with the patient-support hub."),
        ("rep_call_note",
         "Short call. Dr. Romero was time-pressed and seemed less engaged than usual. We rescheduled the deeper dose-optimization discussion. Worth flagging that enthusiasm for the relationship has visibly cooled over the last three visits, even though prescribing volume itself looks unchanged on paper."),
        ("msl_summary",
         "MSL session with Dr. Romero focused on the comparative-tolerability section of the latest publication. Provider asked a number of pointed questions about discontinuation rates and the management of common adverse events; tone was clinical and probing."),
    ],
    "HCP-004": [
        ("rep_call_note",
         "Dr. Park is a high-energy practitioner with strong influence across the specialty network in T-Central. Excellent visit. Walked her through the clinical update deck; she had detailed questions about pivotal trial subgroups. Comfortable with current therapy choices."),
        ("rep_call_note",
         "Follow-up with Dr. Park. She is preparing a grand-rounds presentation on best practices in the class. Asked us to source two specific publications for her literature list. Positive engagement throughout."),
        ("comp_intel",
         "Account-level competitive picture stable. No notable new entrants in Dr. Park's practice network this quarter."),
        ("market_research",
         "Regional analysis for T-Central highlights the rising profile of Brand-X within the specialty area. Adoption is still concentrated among early-adopter prescribers, but field surveys suggest Brand-X is increasingly mentioned in peer-to-peer discussions across the territory. The therapeutic class overall continues to grow at low-single-digit rates, with prescriber preferences influenced by recent symposium content."),
    ],
    # HCP-005: no qualitative documents on purpose (graceful-degradation test).
}


# --- Qualitative: templated docs for the other 45 accounts ------------------

REP_TEMPLATES = [
    "Met with Dr. {last} on {day}. Walked through the latest dosing data and answered formulary questions. Pace felt steady; no objections raised. Following up with the rebate paperwork next week.",
    "Quick visit with Dr. {last}'s practice manager — Dr. {last} was between procedures. Left the updated patient-education flyers and confirmed they are using the prior-auth template we shared in Q2.",
    "Dr. {last} engaged on the latest comparative-effectiveness deck. Asked thoughtful questions about adherence at the 12-week mark. Plans to keep current patients on therapy and reassess in two months.",
    "Routine call. Dr. {last} reported steady volumes and no access friction. Office staff requested more sample kits. Booked a follow-up for the new specialty pharmacy onboarding.",
    "Discussed the Q3 advisory-board recap with Dr. {last}. Useful exchange on the subgroup analysis. Workflow is unchanged from last visit.",
    "Dr. {last} reviewed the recent adherence dashboard with me. The trend is stable. He raised a question on payer mix that I will follow up on with the access team.",
]

MSL_TEMPLATES = [
    "MSL engagement covered mechanism-of-action questions and a recent peer-reviewed publication. Dr. {last} raised a nuanced question on long-term safety in the {pop} population; followed up with relevant references.",
    "Clinical discussion focused on biomarker patterns in {pop}. The provider expressed interest in the upcoming Phase 4 readout. Educational materials shared.",
    "Provider sought clarity on the dosing adjustment for renal-impairment patients. Referenced label and recent guideline update; sent the consensus statement for review.",
]

COMP_TEMPLATES = [
    "Local market remains stable. Generic substitution rates flat quarter-over-quarter. No new competitive launches expected in the territory through year-end.",
    "Competitor field activity has been minimal in {terr} this quarter. Account-level switching has been negligible.",
    "Steady-state competitive landscape. The main alternative therapy continues to hold its baseline share in this segment; no aggressive contracting moves observed.",
]

MR_TEMPLATES = [
    "Therapeutic class in {terr} shows modest growth, driven by demographic shifts in the prescriber's primary patient panel. Reimbursement environment is stable. No formulary changes anticipated in the next two cycles.",
    "Regional analysis for {terr}: overall class volume up low-single-digits year-over-year. Specialist density consistent with national norms. Payer mix tilts commercial.",
    "Market dynamics in {terr} indicate continued physician preference for established regimens. New-to-class adoption is gradual rather than disruptive. No major guideline updates pending.",
]

LAST_NAMES = ["Lee", "Chen", "Patel", "Rivera", "Berg", "Mueller", "Alvarez", "Tanaka",
              "O'Connor", "Kapoor", "Schmidt", "Khan", "Silva", "Hassan", "Krishnan",
              "Popescu", "Rossi", "Nguyen", "Andersson", "Yamamoto"]
POPS = ["elderly", "treatment-naive", "polypharmacy", "comorbid cardiovascular", "treatment-experienced"]
DAYS = ["Tue 11:00", "Thu 14:30", "Wed 09:15", "Mon 15:45", "Fri 10:30"]


def gen_qual(quant_rows: list[dict]) -> list[dict]:
    docs: list[dict] = []

    # Hand-written tension docs first.
    for aid, items in TENSION_DOCS.items():
        for src, text in items:
            docs.append({"account_id": aid, "source_type": src, "text": text})

    # Templated docs for the remaining 45 accounts.
    rng = random.Random(13)
    skip = set(TENSION_DOCS.keys()) | {"HCP-005"}
    for row in quant_rows:
        aid = row["account_id"]
        if aid in skip:
            continue
        terr = row["territory"]

        # 1-3 rep call notes
        for _ in range(rng.randint(1, 3)):
            tmpl = rng.choice(REP_TEMPLATES)
            docs.append({"account_id": aid, "source_type": "rep_call_note",
                         "text": tmpl.format(last=rng.choice(LAST_NAMES), day=rng.choice(DAYS))})

        if rng.random() < 0.6:
            tmpl = rng.choice(MSL_TEMPLATES)
            docs.append({"account_id": aid, "source_type": "msl_summary",
                         "text": tmpl.format(last=rng.choice(LAST_NAMES), pop=rng.choice(POPS))})

        if rng.random() < 0.5:
            tmpl = rng.choice(COMP_TEMPLATES)
            docs.append({"account_id": aid, "source_type": "comp_intel",
                         "text": tmpl.format(terr=terr)})

        if rng.random() < 0.4:
            tmpl = rng.choice(MR_TEMPLATES)
            docs.append({"account_id": aid, "source_type": "market_research",
                         "text": tmpl.format(terr=terr)})

    return docs


# --- Invariants -------------------------------------------------------------

def check_invariants(quant_rows: list[dict], qual_docs: list[dict]) -> None:
    assert len(quant_rows) == 50, f"expected 50 quant rows, got {len(quant_rows)}"

    by_acct: dict[str, list[dict]] = {}
    for d in qual_docs:
        by_acct.setdefault(d["account_id"], []).append(d)

    assert "HCP-005" not in by_acct, "HCP-005 must have zero qualitative docs"

    brandx = [d for d in qual_docs if "Brand-X" in d["text"]]
    assert len(brandx) == 1, f"Brand-X must appear exactly once, found {len(brandx)}"
    assert brandx[0]["account_id"] == "HCP-004" and brandx[0]["source_type"] == "market_research", \
        f"Brand-X must be in HCP-004 market_research, got {brandx[0]['account_id']} / {brandx[0]['source_type']}"

    h002 = [d["text"].lower() for d in by_acct["HCP-002"] if d["source_type"] == "comp_intel"]
    assert h002 and any("watch-list" in t or "competit" in t for t in h002), \
        "HCP-002 comp_intel must describe a competitive threat"

    h001_reps = [d["text"].lower() for d in by_acct["HCP-001"] if d["source_type"] == "rep_call_note"]
    assert h001_reps, "HCP-001 must have rep_call_notes"
    assert not any("declin" in t or "drop" in t for t in h001_reps), \
        "HCP-001 rep_call_notes must not mention decline (the whole point of the tension)"

    h003_reps = [d["text"].lower() for d in by_acct["HCP-003"] if d["source_type"] == "rep_call_note"]
    assert h003_reps and any(("cooler" in t) or ("dissatisfaction" in t) or ("cooled" in t) for t in h003_reps), \
        "HCP-003 rep_call_notes must describe cooling enthusiasm"


# --- Main -------------------------------------------------------------------

def main() -> None:
    quant_rows = gen_quant()
    qual_docs = gen_qual(quant_rows)

    check_invariants(quant_rows, qual_docs)

    quant_path = OUT / "accounts_quant.csv"
    qual_path  = OUT / "accounts_qual.jsonl"

    with quant_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(quant_rows[0].keys()))
        w.writeheader()
        w.writerows(quant_rows)

    qual_path.write_text("\n".join(json.dumps(d) for d in qual_docs) + "\n")

    by_acct = {}
    for d in qual_docs:
        by_acct.setdefault(d["account_id"], []).append(d)
    print(f"wrote {quant_path.relative_to(ROOT)} ({len(quant_rows)} rows)")
    print(f"wrote {qual_path.relative_to(ROOT)} ({len(qual_docs)} docs across {len(by_acct)} accounts)")
    print("invariants ok")


if __name__ == "__main__":
    main()
