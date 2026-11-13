"""Validate the calculator and the vision pipeline against the Daft.ie workbooks.

Each data/validation/daft/N.xlsx is a copy of the Kaiser Excel tool filled in by a human
assessor for one Irish property (Eircode in Input!A2).

Part A (offline): feed the assessor's inputs to HWBCalculator and compare with the
                  Excel Output sheet  -> calculator parity.
Part B (live):    run BERPipeline on the Eircode and compare the vision-derived
                  inputs and resulting energy/BER with the assessor's -> pipeline accuracy.

Usage:
    python scripts/validate_daft.py              # A + B (uses Google + Anthropic APIs)
    python scripts/validate_daft.py --offline    # A only
    python scripts/validate_daft.py --runs 3     # repeat vision+calc 3x per property
    python scripts/validate_daft.py --runs 3 --provider both   # Claude and Mistral, same images
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import warnings
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ber_automation.ber_engine.calculator import HWBCalculator  # noqa: E402
from ber_automation.models import (  # noqa: E402
    BuildingInput,
    BuildingType,
    ConstructionEpoch,
    Country,
    HeatingSystem,
    WindowDoorAreas,
)
from ber_automation.config import get_settings  # noqa: E402
from ber_automation.pipeline import BERPipeline  # noqa: E402
from ber_automation.vision.providers import (  # noqa: E402
    KEY_ENV_NAMES,
    PROVIDER_LABELS,
    PROVIDERS,
    api_key,
    model_name,
    resolve_provider,
)

DAFT_DIR = ROOT / "data" / "validation" / "daft"
OUT_DIR = ROOT / "output" / "daft_validation"

BUILDING_TYPES = {
    "Detached": BuildingType.DETACHED,
    "Semi-Detached (Length adjacent)": BuildingType.SEMI_D_LENGTH,
    "Semi-Detached (Width adjacent)": BuildingType.SEMI_D_WIDTH,
    "Terraced (Length adjacent)": BuildingType.TERRACED_LENGTH,
    "Terraced (Width adjacent)": BuildingType.TERRACED_WIDTH,
}
EPOCHS = {
    "before 1980": ConstructionEpoch.BEFORE_1980,
    "1980-1990": ConstructionEpoch.EPOCH_1980_1990,
    "1990-2000": ConstructionEpoch.EPOCH_1990_2000,
    "2000-2010": ConstructionEpoch.EPOCH_2000_2010,
    "after 2010": ConstructionEpoch.AFTER_2010,
}
HEATING = {
    "Oil": HeatingSystem.OIL_BOILER,
    "Gas": HeatingSystem.GAS_BOILER,
    "Biomass": HeatingSystem.BIOMASS,
    "All Electric": HeatingSystem.ELECTRIC_DIRECT,
}


def load_workbook_case(path: Path) -> dict:
    """Read the assessor's inputs (Input row 2) and the Excel 'Current Status' outputs."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    r = next(wb["Input"].iter_rows(min_row=2, max_row=2, values_only=True))
    building = BuildingInput(
        length=r[4],
        width=r[5],
        heated_storeys=int(r[6]),
        storey_height=r[7],
        building_type=BUILDING_TYPES[r[3].strip()],
        construction_epoch=EPOCHS[str(r[8]).strip().lower()],
        country=Country(r[14].strip().lower()),
        residents=r[15],
        window_door_areas=WindowDoorAreas(north=r[10], east=r[11], south=r[12], west=r[13]),
        heating_system=HEATING[r[16].strip()],
        hot_water_electric_separate=(r[17] or "").strip().lower() == "x",
    )

    excel: dict[str, float] = {}
    for row in wb["Output"].iter_rows(values_only=True):
        vals = [c for c in row if c is not None]
        if len(vals) < 2 or not isinstance(vals[0], str):
            continue
        label = vals[0].strip()
        if label.startswith("Useful Energy Demand"):
            excel.setdefault("useful_kwh", vals[1])
        elif label.startswith("Final Energy Demand Heating [kWh"):
            excel.setdefault("final_heating_kwh", vals[1])
        elif label.startswith("Final Energy Demand Hot Water [kWh"):
            excel.setdefault("final_hotwater_kwh", vals[1])
        elif label.startswith("Final Energy Demand Heating and Hot Water [kWh"):
            excel.setdefault("final_total_kwh", vals[1])
        elif label.startswith("Final Energy Demand Heating and Hot Water [t CO2"):
            excel.setdefault("co2_t", vals[1])
    wb.close()
    return {"file": path.name, "eircode": str(r[0]).strip(), "building": building, "excel": excel}


def calc_summary(building: BuildingInput) -> dict:
    ber = HWBCalculator().calculate_ber(building)
    h = ber.hwb_result
    final_total = h.total_kwh_per_m2 * h.floor_area
    return {
        "useful_kwh": h.heating_demand_kwh + h.hot_water_kwh,
        "final_heating_kwh": h.final_energy_kwh,
        "final_hotwater_kwh": final_total - h.final_energy_kwh,
        "final_total_kwh": final_total,
        "co2_t": h.co2_kg / 1000.0,
        "floor_area": h.floor_area,
        "final_kwh_per_m2": h.total_kwh_per_m2,
        "primary_kwh_per_m2": ber.kwh_per_m2,
        "ber_band": ber.ber_band,
    }


def pct(ours: float, ref: float) -> float:
    return (ours - ref) / ref * 100.0 if ref else float("nan")


def input_summary(b: BuildingInput) -> dict:
    return {
        "building_type": b.building_type.value,
        "length": round(b.length, 1),
        "width": round(b.width, 1),
        "footprint_m2": round(b.length * b.width, 1),
        "storeys": b.heated_storeys,
        "epoch": b.construction_epoch.value,
        "heating": b.heating_system.value,
    }


async def run_pipeline_case(case: dict, runs: int, provider: str, images_from=None):
    """Run the pipeline *runs* times with one vision model.

    Run 1 fetches images; later runs re-analyse the same images, so differences between
    runs are model variance only. With *images_from* (the first result of another model)
    nothing is fetched: every run re-analyses that result's images, so both models see
    identical inputs.

    Returns:
        (summaries, first PipelineResult)
    """
    out = OUT_DIR / case["eircode"].replace(" ", "_")
    pipeline = BERPipeline(output_dir=out, provider=provider)
    if images_from is None:
        first = await pipeline.run(case["eircode"], country=Country.IRELAND)
    else:
        first = await pipeline.reanalyse(images_from, country=Country.IRELAND)
    results = [first]
    for _ in range(runs - 1):
        if first.coordinates is None:
            break
        results.append(await pipeline.reanalyse(first, country=Country.IRELAND))
    tag = "" if provider == "claude" else f"_{provider}"
    for i, r in enumerate(results, start=1):
        name = f"result{tag}.json" if i == 1 else f"result{tag}_run{i}.json"
        (out / name).write_text(r.model_dump_json(indent=2), encoding="utf-8")
    return [_summarise_result(r) for r in results], first


def _summarise_result(result) -> dict:
    info: dict = {
        "llm_provider": result.llm_provider,
        "llm_model": result.llm_model,
        "errors": result.errors,
        "geocoded": result.coordinates.formatted_address if result.coordinates else None,
        "footprint_source": result.footprint.source if result.footprint else None,
        "footprint_conf": result.footprint.confidence if result.footprint else None,
        "street_conf": result.street_analysis.confidence if result.street_analysis else None,
    }
    hd = result.house_description
    if hd:
        info["description"] = {
            "target_view": hd.target_view, "similar_house_view": hd.similar_house_view,
            "inferred_from_similar": hd.inferred_from_similar,
            "similar_house_windows": result.similar_house_windows,
            "text": hd.description,
        }
    fp = result.footprint
    if fp and fp.units_in_block is not None:
        info["block"] = {
            "length": fp.block_length_m, "width": fp.block_width_m,
            "units": fp.units_in_block, "units_claude": fp.units_claude,
            "units_visible": fp.units_visible, "units_source": fp.units_source,
            "clipped": fp.block_clipped,
        }
    if result.ber_result:
        info["inputs"] = input_summary(result.ber_result.building_input)
        info["calc"] = calc_summary(result.ber_result.building_input)
    return info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="calculator parity only, no API calls")
    ap.add_argument("--runs", type=int, default=1,
                    help="vision+calc repeats per property on the same images (measures run-to-run variance)")
    ap.add_argument("--provider", choices=[*PROVIDERS, "both"], default=None,
                    help="vision model (default: the LLM_PROVIDER setting). 'both' runs each model "
                         "on the same fetched images and writes one report per model")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = [load_workbook_case(p) for p in sorted(DAFT_DIR.glob("*.xlsx"))]

    print("=" * 100)
    print("PART A - calculator parity (assessor inputs -> HWBCalculator vs Excel Output sheet)")
    print("=" * 100)
    metrics = ["useful_kwh", "final_heating_kwh", "final_hotwater_kwh", "final_total_kwh", "co2_t"]
    for c in cases:
        c["ours"] = calc_summary(c["building"])
        print(f"\n{c['file']}  {c['eircode']}  -> reference BER {c['ours']['ber_band']} "
              f"({c['ours']['primary_kwh_per_m2']} kWh/m2a primary)")
        for m in metrics:
            e, o = c["excel"][m], c["ours"][m]
            print(f"    {m:<20} excel={e:>10.2f}  python={o:>10.2f}  diff={pct(o, e):+7.2f}%")

    providers: list[str] = []
    if not args.offline:
        settings = get_settings()
        providers = (list(PROVIDERS) if args.provider == "both"
                     else [resolve_provider(args.provider, settings)])
        missing = [KEY_ENV_NAMES[p] for p in providers if not api_key(p, settings)]
        if missing:
            sys.exit(f"Not configured: {', '.join(missing)}")

        # One event loop for the whole batch: asyncio.run() per case closes the loop
        # before the Anthropic/httpx clients are torn down (noisy on Windows).
        async def run_all() -> dict[str, list]:
            out: dict[str, list] = {p: [] for p in providers}
            for c in cases:
                images_from = None
                for p in providers:
                    print(f"  {c['eircode']}  {PROVIDER_LABELS[p]}: running pipeline x{args.runs}...",
                          flush=True)
                    try:
                        summaries, first = await run_pipeline_case(c, args.runs, p, images_from)
                        if images_from is None and first.coordinates is not None:
                            images_from = first
                        out[p].append(summaries)
                    except Exception as e:  # keep going so one failure doesn't lose the batch
                        out[p].append([{"errors": [f"{type(e).__name__}: {e}"]}])
            return out

        print("\n" + "=" * 100)
        print("PART B - pipeline (Eircode -> vision -> calc) vs assessor")
        print("=" * 100)
        all_results = asyncio.run(run_all())
        row = "    {:<9} {:<16} {:>5} x {:<5} {:>7} {:>3}  {:<10} {:<12} {:>8} {:>4}"
        for p in providers:
            print(f"\n--- {PROVIDER_LABELS[p]} ({model_name(p, settings)}) ---")
            for c, run_results in zip(cases, all_results[p]):
                c.setdefault("pipeline", {})[p] = run_results
                human, ho = input_summary(c["building"]), c["ours"]
                print(f"\n{c['file']}  {c['eircode']}  ({run_results[0].get('geocoded')})")
                print(row.format("", "type", "len", "wid", "area", "st", "epoch", "heating", "kWh/m2a", "BER"))
                print(row.format("assessor", human["building_type"], human["length"], human["width"],
                                 human["footprint_m2"], human["storeys"], human["epoch"], human["heating"],
                                 ho["primary_kwh_per_m2"], ho["ber_band"]))
                for i, r in enumerate(run_results, start=1):
                    for err in r["errors"]:
                        print(f"    run {i} ERROR: {err}")
                    if "inputs" not in r:
                        continue
                    pi, po = r["inputs"], r["calc"]
                    print(row.format(f"run {i}", pi["building_type"], pi["length"], pi["width"],
                                     f"{pct(pi['footprint_m2'], human['footprint_m2']):+.0f}%", pi["storeys"],
                                     pi["epoch"], pi["heating"], po["primary_kwh_per_m2"], po["ber_band"]))
                done = [r for r in run_results if "inputs" in r]
                if len(done) > 1:
                    varying = [k for k in human if len({r["inputs"][k] for r in done}) > 1]
                    bands = {r["calc"]["ber_band"] for r in done}
                    print(f"    runs agree: {'yes' if not varying else 'NO - differs in ' + ', '.join(varying)}"
                          f"{'' if len(bands) == 1 else '  (BER band varies: ' + '/'.join(sorted(bands)) + ')'}")

    # One report per model: report.json for Claude (as before), report_<provider>.json
    # for the others; report_offline.json when no model was run.
    for p in providers or [None]:
        report = [
            {
                "file": c["file"],
                "eircode": c["eircode"],
                "assessor_inputs": input_summary(c["building"]),
                "excel": c["excel"],
                "python_on_assessor_inputs": c["ours"],
                "pipeline": c["pipeline"][p] if p else None,
            }
            for c in cases
        ]
        name = ("report_offline.json" if p is None
                else "report.json" if p == "claude" else f"report_{p}.json")
        path = OUT_DIR / name
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {path}")


if __name__ == "__main__":
    main()
