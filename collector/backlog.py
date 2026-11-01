#!/usr/bin/env python3
"""The backlog, over time: early voters a county has already recorded on its own roster
that the Secretary of State's data has not matched yet (county_only, by VUID), summed
across every matched county, at each hourly match snapshot. Aggregate counts only — no
voter-level data. Writes frontend/dashboard/backlog.json.

This is the "does the backlog drain?" view. It is NOT a prediction: it plots what the
archive already holds, snapshot by snapshot. Each evening a county posts a fresh early-vote
day, so the backlog jumps; over the following day the state matches those voters and the
line falls. Whether it reaches zero is only answerable once the state declares its backlog
processed and we re-run the comparison then.

Source: data/match/<ts>/summary.json (result[].county_only), already archived hourly.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "dashboard" / "backlog.json"

NICE = {"harris": "Harris", "dallas": "Dallas", "bexar": "Bexar", "travis": "Travis",
        "hidalgo": "Hidalgo", "el-paso": "El Paso", "cameron": "Cameron", "hays": "Hays",
        "tarrant": "Tarrant", "collin": "Collin", "denton": "Denton", "randall": "Randall"}
# Display order (most populous first), same spine as the other producers.
ORDER = ["harris", "dallas", "bexar", "travis", "collin", "denton", "tarrant",
         "hidalgo", "el-paso", "cameron", "hays", "randall"]


def snap_ts(path: Path) -> str | None:
    """ISO UTC timestamp for a match snapshot, from its directory name (…/<ts>/summary.json)."""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d)(\d\d)(\d\d)Z$", path.parent.name)
    if not m:
        return None
    return f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}Z"


def main() -> int:
    points = []
    seen_counties: set[str] = set()
    for p in sorted(glob.glob(str(ROOT / "data" / "match" / "*" / "summary.json"))):
        ts = snap_ts(Path(p))
        if not ts:
            continue
        try:
            d = json.load(open(p))
        except Exception:
            continue
        by: dict[str, int] = {}
        for r in d.get("results", []):
            slug = r.get("county")
            co = r.get("county_only")
            if slug is None or co is None:
                continue
            by[slug] = int(co)
            seen_counties.add(slug)
        if not by:
            continue
        points.append({"t": ts, "total": sum(by.values()), "by": by})

    counties = [s for s in ORDER if s in seen_counties] + sorted(seen_counties - set(ORDER))
    latest = points[-1] if points else None
    data = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "label": ("Early voters each county has recorded on its own roster that the Secretary "
                  "of State's data has not matched yet (by voter ID), summed across every matched "
                  "county, at each hourly snapshot. This is the backlog as it stands — not a forecast."),
        "counties": counties,
        "names": {s: NICE.get(s, s.title()) for s in counties},
        "points": points,
        "latest": {"t": latest["t"], "total": latest["total"]} if latest else None,
    }
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    span = f"{points[0]['t']} .. {points[-1]['t']}" if points else "no snapshots"
    print(f"written {OUT} ({OUT.stat().st_size:,} bytes); {len(points)} snapshots, {span}")
    if latest:
        print(f"  latest backlog {latest['total']:,} across {len(latest['by'])} counties "
              + ", ".join(f"{NICE.get(k,k)}={v:,}" for k, v in sorted(latest["by"].items(), key=lambda kv: -kv[1])[:5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
