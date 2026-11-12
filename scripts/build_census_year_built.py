"""Build ber_automation/data/cso_year_built_sa2022.csv from CSO Census 2022 SAPS.

Source: CSO table SAP2022T6T2SA, permanent private households by year built for every
Small Area (about 18,900 areas of 80-120 homes). The CSO's 11 year-built bands are
merged into the 5 construction epochs of the HWB tool. "Not stated" is dropped.

Usage:
    python scripts/build_census_year_built.py [--source path/to/SAP2022T6T2SA.csv]

Licence: CSO open data, CC BY 4.0. Attribution: Central Statistics Office, Census 2022.
"""

from __future__ import annotations

import argparse
import csv
import io
from collections import defaultdict
from pathlib import Path

import httpx

URL = "https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/SAP2022T6T2SA/CSV/1.0/en"
OUT = Path(__file__).resolve().parents[1] / "ber_automation" / "data" / "cso_year_built_sa2022.csv"

# CSO year-built code -> HWB construction epoch
BAND_TO_EPOCH = {
    "PRE19": "before_1980", "19_45": "before_1980", "46_60": "before_1980",
    "61_70": "before_1980", "71_80": "before_1980",
    "81_90": "1980_1990",
    "91_00": "1990_2000",
    "01_10": "2000_2010",
    "11_15": "after_2010", "16L": "after_2010",
}
HOUSEHOLDS = "SAP2022T6T2C01"  # permanent private households (C02 = persons in them)
EPOCHS = ["before_1980", "1980_1990", "1990_2000", "2000_2010", "after_2010"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path, help="local copy of the SAP2022T6T2SA CSV")
    args = ap.parse_args()

    if args.source:
        text = args.source.read_text(encoding="utf-8-sig")
    else:
        print(f"Downloading {URL} ...")
        resp = httpx.get(URL, timeout=300, follow_redirects=True)
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig")

    counts: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(EPOCHS, 0))
    for row in csv.DictReader(io.StringIO(text)):
        if row["STATISTIC"] != HOUSEHOLDS:  # the table also holds person counts
            continue
        epoch = BAND_TO_EPOCH.get(row["C03782V04531"])
        if epoch is None:  # "NS" (not stated) and "T" (total)
            continue
        counts[row["C04172V04943"]][epoch] += int(row["VALUE"] or 0)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sa_guid", *EPOCHS])
        for guid in sorted(counts):
            w.writerow([guid, *(counts[guid][e] for e in EPOCHS)])
    print(f"Wrote {len(counts)} small areas to {OUT}")


if __name__ == "__main__":
    main()
