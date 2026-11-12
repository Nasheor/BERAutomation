"""Build the per-Small-Area census files in ber_automation/data/ from CSO Census 2022 SAPS.

- cso_year_built_sa2022.csv  <- SAP2022T6T2SA, households by year built. The CSO's 11
  bands are merged into the 5 construction epochs of the HWB tool.
- cso_heating_sa2022.csv     <- SAP2022T6T5SA, households by central heating fuel.
- cso_rooms_sa2022.csv       <- SAP2022T6T4SA, households by number of rooms (1-7, 8+).

Only household counts (statistic ...C01) are used; the tables also hold person counts
(...C02). "Not stated" and "Total" are dropped. About 18,900 Small Areas of 80-120 homes.

Usage:
    python scripts/build_census_data.py [--source-dir DIR]
    (DIR holds SAP2022T6T2SA.csv, SAP2022T6T4SA.csv and SAP2022T6T5SA.csv; otherwise they are downloaded)

Licence: CSO open data, CC BY 4.0. Attribution: Central Statistics Office, Census 2022.
"""

from __future__ import annotations

import argparse
import csv
import io
from collections import defaultdict
from pathlib import Path

import httpx

API = "https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/{table}/CSV/1.0/en"
DATA = Path(__file__).resolve().parents[1] / "ber_automation" / "data"
SA_COLUMN = "C04172V04943"  # Small Area GUID

TABLES = {
    "SAP2022T6T2SA": {
        "out": DATA / "cso_year_built_sa2022.csv",
        "column": "C03782V04531",  # year built
        "map": {
            "PRE19": "before_1980", "19_45": "before_1980", "46_60": "before_1980",
            "61_70": "before_1980", "71_80": "before_1980",
            "81_90": "1980_1990", "91_00": "1990_2000", "01_10": "2000_2010",
            "11_15": "after_2010", "16L": "after_2010",
        },
    },
    "SAP2022T6T5SA": {
        "out": DATA / "cso_heating_sa2022.csv",
        "column": "C03750V04499",  # central heating fuel
        "map": {
            "NGCH": "gas", "OCH": "oil", "ECH": "electricity", "WCH": "wood",
            "LPGCH": "lpg", "CCH": "coal", "PCH": "peat", "OTH": "other", "NCH": "none",
        },
    },
    "SAP2022T6T4SA": {
        "out": DATA / "cso_rooms_sa2022.csv",
        "column": "C03771V04520",  # number of rooms
        "map": {
            "1R": "1", "2R": "2", "3R": "3", "4R": "4", "5R": "5", "6R": "6", "7R": "7", "GE8R": "8+",
        },
    },
}


def _read(table: str, source_dir: Path | None) -> str:
    if source_dir is not None:
        return (source_dir / f"{table}.csv").read_text(encoding="utf-8-sig")
    url = API.format(table=table)
    print(f"Downloading {url} ...")
    resp = httpx.get(url, timeout=300, follow_redirects=True)
    resp.raise_for_status()
    return resp.content.decode("utf-8-sig")


def build(table: str, spec: dict, source_dir: Path | None) -> None:
    columns = list(dict.fromkeys(spec["map"].values()))
    households = table[:-2] + "C01"  # e.g. SAP2022T6T2C01 = permanent private households
    counts: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(columns, 0))
    for row in csv.DictReader(io.StringIO(_read(table, source_dir))):
        if row["STATISTIC"] != households:
            continue
        key = spec["map"].get(row[spec["column"]])
        if key is None:  # "NS" (not stated) and "T" (total)
            continue
        counts[row[SA_COLUMN]][key] += int(row["VALUE"] or 0)

    spec["out"].parent.mkdir(parents=True, exist_ok=True)
    with spec["out"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sa_guid", *columns])
        for guid in sorted(counts):
            w.writerow([guid, *(counts[guid][c] for c in columns)])
    print(f"Wrote {len(counts)} small areas to {spec['out']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-dir", type=Path, help="folder with local copies of the CSO CSVs")
    args = ap.parse_args()
    for table, spec in TABLES.items():
        build(table, spec, args.source_dir)


if __name__ == "__main__":
    main()
