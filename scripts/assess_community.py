"""Assess a community from a list of addresses (CIRCUS).

    python scripts/assess_community.py homes.csv --name "Ballyvillage"
    python scripts/assess_community.py homes.csv --name "Ballyvillage" --analyse 10
    python scripts/assess_community.py homes.csv --name "Ballyvillage" --analyse all --provider claude

The CSV has a header with an ``address`` or ``eircode`` column (and optionally ``id``), or is a
plain list with one address per line. Every home gets a census estimate (geocoding and census
lookups only, no AI credit). ``--analyse`` adds image analysis (the full pipeline, about a
minute and some API credit per home): ``all``, a number of homes spread over the Small Areas,
or comma-separated ids. Results go to ``output/communities/<name>/community.json``; rerunning
reuses them, so an interrupted run resumes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ber_automation.community.addresses import read_addresses  # noqa: E402
from ber_automation.community.assess import assess_community, community_dir  # noqa: E402
from ber_automation.community.summary import (  # noqa: E402
    agreement,
    area_totals,
    band_counts,
    ranking,
    totals,
)
from ber_automation.models import Country  # noqa: E402


def _analyse(value: str):
    if value in ("none", "all"):
        return value
    if value.isdigit():
        return int(value)
    return [v.strip() for v in value.split(",") if v.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", help="address list (CSV with address/eircode column, or one per line)")
    parser.add_argument("--name", required=True, help="community name (output folder)")
    parser.add_argument("--analyse", default="none", help="none | all | N | id,id,...")
    parser.add_argument("--provider", default=None, help="vision model: claude | mistral")
    parser.add_argument("--country", default=Country.IRELAND.value,
                        choices=[c.value for c in Country])
    args = parser.parse_args()

    entries = read_addresses(Path(args.csv).read_text(encoding="utf-8-sig"))
    if not entries:
        print("No addresses found.")
        return 1
    print(f"{len(entries)} addresses; image analysis: {args.analyse}")

    def progress(done, total, message):
        print(f"  [{done}/{total}] {message}", flush=True)

    result = asyncio.run(assess_community(
        entries, args.name, country=Country(args.country), analyse=_analyse(args.analyse),
        provider=args.provider, progress=progress,
    ))

    t = totals(result)
    print(f"\n{args.name}: {t['rated']} of {t['homes']} homes rated "
          f"({t['from_images']} from images, {t['rated'] - t['from_images']} census only, "
          f"{t['not_located']} not located)")
    print(f"  listed homes: {t['heat_demand_mwh']:,.0f} MWh/yr heat demand, "
          f"{t['primary_mwh']:,.0f} MWh/yr primary, {t['co2_t']:,.1f} t CO2/yr, "
          f"mean {t['mean_primary_kwh_m2']:.0f} kWh/m²/yr")
    a = area_totals(result)
    if a["small_areas"]:
        print(f"  their {a['small_areas']} Small Areas ({a['households']} households, census model): "
              f"{a['heat_demand_mwh']:,.0f} MWh/yr heat demand, {a['co2_t']:,.0f} t CO2/yr, "
              f"mean {a['mean_primary_kwh_m2']:.0f} kWh/m²/yr")
    print("  bands: " + ", ".join(f"{b} {n}" for b, n in band_counts(result).items()))
    ag = agreement(result)
    if ag["n"]:
        print(f"  census vs images: same band {ag['exact']}/{ag['n']}, within one {ag['within_one']}/{ag['n']}")
    print("\nWorst first:")
    for r in ranking(result)[:15]:
        print(f"  {r['rank']:>3} {r['id']:>4} {r['address'][:28]:<28} {r['band']:<3} {r['kwh_m2']:>6.0f} "
              f"{r['source']:<7} {r['era']:<12} {r['heating']}")
    for h in result.homes:
        for e in h.errors:
            print(f"  ! {h.id} {h.address}: {e}")
    print(f"\nSaved: {community_dir(args.name) / 'community.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
