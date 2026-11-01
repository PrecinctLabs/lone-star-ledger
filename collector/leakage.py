#!/usr/bin/env python3
"""Cross-county leakage: voters a county's OWN roster lists as having voted there, whom the
Secretary of State credits to a DIFFERENT county. Aggregate counts only — no voter-level file is
written by this script at all.

The main dashboard's "county_only" bucket (on a county's own list, not on the SOS list for that
county) mixes two very different things: voters the SOS simply has not posted yet, and voters the
SOS HAS — but filed under another county's column. This script splits them. For each home county
X we take its county_only VUIDs and look each one up in the SOS's rosters for the OTHER counties
we collect. A hit means X says the person voted in X, the SOS agrees they voted, but the SOS's
county column says somewhere else. That is the "Dallas voters filed under Collin/Denton" pattern.

  * "filed under <Y>" is the SOS's reported county, not the voter's registered county (the SOS's
    roster puts Y in its county column for that VUID).
  * Visibility is limited to the counties we fetch SOS rosters for (the 12 reconciled). We can see
    a voter leak X -> Y only when Y is one of those 12; a leak to a county we don't collect falls
    into "not in any roster we hold." We state that limit plainly rather than imply full coverage.

Both sides are real records: X's own published roster, and the SOS's own published rosters. No
names or VUIDs are emitted — only per-pair counts. Writes frontend/dashboard/leakage.json.

Usage: python3 collector/leakage.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import match  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "dashboard" / "leakage.json"

ORDER = ["harris", "dallas", "bexar", "collin", "denton", "travis", "hidalgo", "el-paso", "cameron", "hays", "tarrant", "randall"]
NICE = {"harris": "Harris", "dallas": "Dallas", "bexar": "Bexar", "travis": "Travis",
        "hidalgo": "Hidalgo", "el-paso": "El Paso", "cameron": "Cameron", "hays": "Hays",
        "tarrant": "Tarrant", "collin": "Collin", "denton": "Denton", "randall": "Randall"}


def main() -> int:
    print("cross-county leakage (aggregate counts only)")

    # SOS side: vuid -> {county: method} across every county we hold SOS rosters for.
    sos_by_vuid: dict[str, dict[str, str]] = collections.defaultdict(dict)
    sos_present = []
    for c in ORDER:
        sos, _ = match.sos_rosters(c)
        if not sos:
            continue
        sos_present.append(c)
        for v, (_date, meth) in sos.items():
            sos_by_vuid[v][c] = meth
    print(f"  SOS rosters loaded for: {', '.join(sos_present)}")

    counties = []
    sw_county_only = sw_leaked = sw_absent = 0
    matrix = {}  # home -> {filed_under: count}
    for home in ORDER:
        if home not in sos_present:
            continue
        try:
            cty = match.COUNTY_PARSERS[home]()
        except Exception as e:
            print(f"  {home}: county parser failed: {type(e).__name__}: {e}")
            continue
        if not cty:
            continue
        home_sos = {v for v, who in sos_by_vuid.items() if home in who}
        county_only = set(cty) - home_sos
        if not county_only:
            continue
        filed_under = collections.Counter()   # Y -> count of this home's county_only found under Y
        leaked = 0
        for v in county_only:
            others = [y for y in sos_by_vuid.get(v, {}) if y != home]
            if others:
                leaked += 1
                for y in others:
                    filed_under[y] += 1
        absent = len(county_only) - leaked
        matrix[home] = {y: n for y, n in filed_under.items()}
        counties.append({
            "slug": home, "name": NICE[home],
            "county_only": len(county_only),
            "leaked_to_other_county": leaked,
            "not_in_any_roster_we_hold": absent,
            "filed_under": sorted(
                ({"slug": y, "name": NICE[y], "count": n} for y, n in filed_under.items()),
                key=lambda d: -d["count"]),
        })
        sw_county_only += len(county_only)
        sw_leaked += leaked
        sw_absent += absent
        top = ", ".join(f"{NICE[y]} {n}" for y, n in filed_under.most_common(4)) or "—"
        print(f"    {NICE[home]:9} county_only={len(county_only):>7,}  leaked={leaked:>5,}  absent={absent:>7,}  into: {top}")

    data = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "label": "Voters each county's own roster lists as voting there, whom the Secretary of State credits to a different county's roster (election 53815). 'Filed under' is the SOS's reported county. Visibility is limited to the counties we collect SOS rosters for.",
        "counties_collected": [NICE[c] for c in sos_present],
        "statewide": {"county_only": sw_county_only, "leaked_to_other_county": sw_leaked,
                      "not_in_any_roster_we_hold": sw_absent},
        "counties": counties,
    }
    OUT.write_text(json.dumps(data, indent=1))
    print(f"  written {OUT}  (statewide: {sw_leaked:,} of {sw_county_only:,} county-only voters are filed by the SOS under another county we collect)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
