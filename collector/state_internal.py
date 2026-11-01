#!/usr/bin/env python3
"""State-internal consistency check (in-person): the Secretary of State's own early-vote TOTAL
for a county vs. the number of distinct voters the SOS's OWN named roster lists for that county,
over time. Aggregate counts only, no voter-level data.

Both figures come entirely from the state — no county data is involved. This is the in-person
analog of the mail check in Finding 3, and the "state totals page vs. state voter list" column
lostvotes.us surfaces for Dallas. It answers one question: does the state's headline number for a
county match the number of people the state can actually name as having voted there?

  * totals_page: the SOS Civix turnout feed's total_in_person_votes_for_election (data/raw/sos).
    This is the aggregate the state publishes — "votes," by its own description of the feed.
  * state_list:  distinct ID_VOTER on the SOS's per-date in-person rosters, as already counted by
    match.py (data/match/<ts>/summary.json -> sos_by_method["in-person"]). This is "people."

A positive gap means the totals page claims more in-person votes than the state's own roster can
put a name to; negative means the roster names more people than the total admits. Either way the
state is not internally consistent, and the gap is timed only to the window between two captures.

Hays is flagged "sampled" (pulled a few times a day); the gap is still the state-vs-state figure,
only noisier in time. No county is set apart here — unlike the mail page, every county the state
rosters is comparable, because both sides are the state's.

Usage: python3 collector/state_internal.py
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "frontend" / "dashboard" / "state_internal.json"

ORDER = ["harris", "dallas", "bexar", "collin", "denton", "travis", "hidalgo", "el-paso", "cameron", "hays", "tarrant", "randall"]
NICE = {"harris": "Harris", "dallas": "Dallas", "bexar": "Bexar", "travis": "Travis",
        "hidalgo": "Hidalgo", "el-paso": "El Paso", "cameron": "Cameron", "hays": "Hays",
        "tarrant": "Tarrant", "collin": "Collin", "denton": "Denton", "randall": "Randall"}
SAMPLED = {"hays"}             # pulled a few times a day, not every 15 min


def norm(s: str) -> str:
    return re.sub(r"[^A-Z]", "", (s or "").upper())


def parse_ts(s: str) -> dt.datetime | None:
    for fmt in ("%Y-%m-%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
        except (ValueError, TypeError):
            pass
    return None


def totals_page_series() -> dict:
    """slug-norm -> sorted list of (datetime, total_in_person) change-points from the turnout feed."""
    pts: dict[str, list] = {}
    for f in sorted(glob.glob(str(RAW / "sos" / "*" / "*turnout_53815_*.json"))):
        m = re.search(r"/sos/(\d{4}-\d\d-\d\d)/(\d\d)(\d\d)(\d\d)_", f)
        if not m:
            continue
        ts = dt.datetime(int(m[1][:4]), int(m[1][5:7]), int(m[1][8:10]),
                         int(m[2]), int(m[3]), int(m[4]), tzinfo=dt.timezone.utc)
        try:
            d = json.load(open(f))
        except Exception:
            continue
        for r in d.get("turnout_by_county", []):
            k = norm(r.get("name", ""))
            c = r.get("total_in_person_votes_for_election")
            if c is None:
                continue
            lst = pts.setdefault(k, [])
            if not lst or lst[-1][1] != c:
                lst.append((ts, c))
    for k in pts:
        pts[k].sort()
    return pts


def value_at(series: list, when: dt.datetime):
    """Latest value at or before `when`."""
    val = None
    for ts, c in series:
        if ts <= when:
            val = c
        else:
            break
    return val


def main() -> int:
    print("state-internal consistency (in-person): totals page vs. the state's own roster")
    totals = totals_page_series()

    # state_list per county over time, from match summaries (chronological)
    lst: dict[str, list] = {c: [] for c in ORDER}  # slug -> [(datetime, state_list)]
    for p in sorted(glob.glob(str(ROOT / "data" / "match" / "*" / "summary.json"))):
        try:
            d = json.load(open(p))
        except Exception:
            continue
        when = parse_ts(d.get("ts", "")) or parse_ts(Path(p).parent.name)
        if not when:
            continue
        for r in d.get("results", []):
            slug = r["county"]
            if slug not in lst:
                continue
            ip = (r.get("sos_by_method") or {}).get("in-person")
            if ip is not None:
                lst[slug].append((when, ip))

    counties = []
    sw_t = sw_l = 0
    for slug in ORDER:
        pts = lst[slug]
        if not pts:
            continue
        tser = totals.get(norm(slug.replace("-", " ")), [])
        # daily series: last observation per calendar day
        byday: dict[str, dict] = {}
        for when, state_list in pts:
            tp = value_at(tser, when)
            byday[when.strftime("%Y-%m-%d")] = {
                "date": when.strftime("%Y-%m-%d"),
                "totals_page": tp,
                "state_list": state_list,
                "gap": (tp - state_list) if tp is not None else None,
            }
        series = [byday[k] for k in sorted(byday)]
        cur = series[-1]
        if cur["totals_page"] is not None:
            sw_t += cur["totals_page"]
            sw_l += cur["state_list"]
        counties.append({
            "slug": slug, "name": NICE[slug], "sampled": slug in SAMPLED,
            "totals_page": cur["totals_page"], "state_list": cur["state_list"], "gap": cur["gap"],
            "gap_pct": round(100 * cur["gap"] / cur["totals_page"], 2) if (cur["gap"] is not None and cur["totals_page"]) else None,
            "series": series,
        })

    data = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "label": "The Secretary of State's own in-person early-vote TOTAL for each county vs. the number of distinct voters the state's OWN roster names for that county (election 53815). Both figures are the state's; the gap is the state against itself.",
        "statewide": {"totals_page": sw_t, "state_list": sw_l, "gap": sw_t - sw_l,
                      "gap_pct": round(100 * (sw_t - sw_l) / sw_t, 2) if sw_t else None},
        "counties": counties,
    }
    OUT.write_text(json.dumps(data, indent=1))
    print(f"  written {OUT}  ({len(counties)} counties; statewide gap {sw_t-sw_l:+,} of {sw_t:,} totals-page votes)")
    for c in counties:
        print(f"    {c['name']:9} totals_page={c['totals_page']!s:>9} state_list={c['state_list']!s:>9} gap={c['gap']:+,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
