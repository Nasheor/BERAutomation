"""Compare the pipeline with official BER certificates (data/validation/official/sample.csv).

For each home: run the pipeline on its Eircode and compare at three levels (see
ber_automation/evaluation/official_compare.py): (a) the inputs read from the images against
the certificate, (b) the calculator with the certificate's values put in, (c) the pipeline's
band and kWh/m²/yr against the official BER. The commonest-band baseline is always shown.

Usage:
    python scripts/validate_official.py --offline              # baseline only, no API calls
    python scripts/validate_official.py                        # 1 run per home, LLM_PROVIDER
    python scripts/validate_official.py --runs 3 --provider both
    python scripts/validate_official.py --ids 1,4,9            # only these sample ids

Writes output/official_validation/report_<provider>.json (report_offline.json with --offline).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ber_automation.config import get_settings  # noqa: E402
from ber_automation.evaluation.official_compare import (  # noqa: E402
    certificate_level,
    commonest_band_baseline,
    compare_inputs,
    run_agreement,
    score,
    summarise_inputs,
    summarise_scores,
)
from ber_automation.evaluation.official_sample import (  # noqa: E402
    OfficialHome,
    load_official_sample,
)
from ber_automation.models import Country  # noqa: E402
from ber_automation.pipeline import BERPipeline  # noqa: E402
from ber_automation.vision.providers import (  # noqa: E402
    KEY_ENV_NAMES,
    PROVIDER_LABELS,
    PROVIDERS,
    api_key,
    model_name,
    resolve_provider,
)

SAMPLE = ROOT / "data" / "validation" / "official" / "sample.csv"
OUT_DIR = ROOT / "output" / "official_validation"


def evaluate_run(home: OfficialHome, result) -> dict:
    """One pipeline result scored at the three levels (errors only if it has no BER)."""
    run: dict = {"errors": result.errors,
                 "geocoded": result.coordinates.formatted_address if result.coordinates else None}
    if not result.ber_result:
        return run
    b = result.ber_result.building_input
    run.update({
        "epoch_source": result.epoch_source,
        "heating_source": result.heating_source,
        "footprint_source": result.footprint.source if result.footprint else None,
        "inputs": {"building_type": b.building_type.value, "length": round(b.length, 1),
                   "width": round(b.width, 1), "storeys": b.heated_storeys,
                   "epoch": b.construction_epoch.value, "heating": b.heating_system.value},
        "a_inputs": compare_inputs(home, b),
        "b_certificate": certificate_level(home, b),
        "c_pipeline": score(home, result.ber_result.ber_band, result.ber_result.kwh_per_m2),
    })
    return run


async def run_home(home: OfficialHome, runs: int, provider: str, images_from=None):
    """Run the pipeline *runs* times; later runs (and *images_from*) reuse the same images.

    Returns:
        (scored runs, first PipelineResult)
    """
    out = OUT_DIR / home.eircode.replace(" ", "_")
    pipeline = BERPipeline(output_dir=out, provider=provider)
    if images_from is None:
        first = await pipeline.run(home.eircode, country=Country.IRELAND)
    else:
        first = await pipeline.reanalyse(images_from, country=Country.IRELAND)
    results = [first]
    for _ in range(runs - 1):
        if first.coordinates is None:
            break
        results.append(await pipeline.reanalyse(first, country=Country.IRELAND))
    for i, r in enumerate(results, start=1):
        name = f"result_{provider}.json" if i == 1 else f"result_{provider}_run{i}.json"
        (out / name).write_text(r.model_dump_json(indent=2), encoding="utf-8")
    return [evaluate_run(home, r) for r in results], first


def _print_summary(title: str, s: dict) -> None:
    if not s.get("n"):
        print(f"  {title:<34} no results")
        return
    print(f"  {title:<34} n={s['n']:<3} exact {s['band_exact']}/{s['n']}  "
          f"within one {s['band_within_one']}/{s['n']}  mean offset {s['mean_band_offset']:+.2f}  "
          f"|kWh err| {s['mean_abs_kwh_error_pct']:.0f}%  median {s['median_kwh_error_pct']:+.0f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="baseline only, no API calls")
    ap.add_argument("--runs", type=int, default=1,
                    help="pipeline repeats per home on the same images (run-to-run variance)")
    ap.add_argument("--provider", choices=[*PROVIDERS, "both"], default=None,
                    help="vision model (default: the LLM_PROVIDER setting); 'both' runs each "
                         "model on the same fetched images")
    ap.add_argument("--ids", default="", help="comma-separated sample ids to run (default: all)")
    ap.add_argument("--sample", type=Path, default=SAMPLE, help="sample CSV")
    args = ap.parse_args()

    homes, problems = load_official_sample(args.sample)
    for p in problems:
        print(f"sample: {p}")
    if not homes:
        sys.exit("No usable homes in the sample.")
    # The baseline uses every home, whichever are run
    baseline = dict(zip((h.id for h in homes), commonest_band_baseline(homes)))
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",") if i.strip()}
        homes = [h for h in homes if h.id in wanted]
        if unknown := wanted - {h.id for h in homes}:
            sys.exit(f"Not in the sample: {', '.join(sorted(unknown))}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    providers: list[str] = []
    results: dict[str, list[list[dict]]] = {}
    if not args.offline:
        settings = get_settings()
        providers = (list(PROVIDERS) if args.provider == "both"
                     else [resolve_provider(args.provider, settings)])
        missing = [KEY_ENV_NAMES[p] for p in providers if not api_key(p, settings)]
        if missing:
            sys.exit(f"Not configured: {', '.join(missing)}")

        # One event loop for the whole batch (see validate_daft.py)
        async def run_all() -> dict[str, list]:
            out: dict[str, list] = {p: [] for p in providers}
            for h in homes:
                images_from = None
                for p in providers:
                    print(f"  {h.id:>3} {h.eircode}  {PROVIDER_LABELS[p]}: pipeline x{args.runs}...",
                          flush=True)
                    try:
                        runs, first = await run_home(h, args.runs, p, images_from)
                        if images_from is None and first.coordinates is not None:
                            images_from = first
                        out[p].append(runs)
                    except Exception as e:  # keep going so one failure doesn't lose the batch
                        out[p].append([{"errors": [f"{type(e).__name__}: {e}"]}])
            return out

        results = asyncio.run(run_all())

    row = "  {:>3} {:<9} {:<13} {:<5} {:>6}  {:<26} {:<26}"
    print("\n" + "=" * 100)
    print("Official BER vs commonest-band baseline (b) certificate values (c) pipeline")
    print("=" * 100)
    for p in providers or [None]:
        label = f"{PROVIDER_LABELS[p]} ({model_name(p, settings)})" if p else "offline"
        print(f"\n--- {label} ---")
        print(row.format("id", "eircode", "type", "BER", "kWh", "(b) per run", "(c) per run"))
        report_homes = []
        for i, h in enumerate(homes):
            runs = results[p][i] if p else []
            done = [r for r in runs if "c_pipeline" in r]
            print(row.format(
                h.id, h.eircode, h.dwelling_type or "?", h.ber_band, f"{h.ber_kwh_m2_yr:.0f}",
                " ".join(r["b_certificate"]["band"] for r in done),
                " ".join(r["c_pipeline"]["band"] for r in done)))
            for n, r in enumerate(runs, start=1):
                for err in r.get("errors", []):
                    print(f"        run {n}: {err}")
            report_homes.append({
                "id": h.id, "eircode": h.eircode, "county": h.county,
                "settlement": h.settlement,
                "certificate": {"band": h.ber_band, "kwh_m2_yr": h.ber_kwh_m2_yr,
                                "dwelling_type": h.dwelling_type, "year_built": h.year_built,
                                "floor_area_m2": h.floor_area_m2, "storeys": h.storeys,
                                "heating": h.heating.value if h.heating else None},
                "baseline_commonest_band": baseline[h.id],
                "band_agreement": run_agreement([r["c_pipeline"]["band"] for r in done]),
                "runs": runs,
            })

        # Every run counts once (n = homes × runs)
        all_runs = [r for rh in report_homes for r in rh["runs"] if "c_pipeline" in r]
        summary = {
            "baseline_commonest_band": summarise_scores([rh["baseline_commonest_band"]
                                                         for rh in report_homes]),
            "a_inputs": summarise_inputs([r["a_inputs"] for r in all_runs]),
            "b_certificate": summarise_scores([r["b_certificate"] for r in all_runs]),
            "c_pipeline": summarise_scores([r["c_pipeline"] for r in all_runs]),
            "epoch_source": _count(r["epoch_source"] for r in all_runs),
            "heating_source": _count(r["heating_source"] for r in all_runs),
        }
        agreements = [rh["band_agreement"] for rh in report_homes
                      if rh["band_agreement"] is not None]
        if agreements:
            summary["mean_band_agreement"] = round(sum(agreements) / len(agreements), 2)

        print()
        _print_summary("baseline (commonest band)", summary["baseline_commonest_band"])
        if p:
            _print_summary("(b) certificate values", summary["b_certificate"])
            _print_summary("(c) pipeline", summary["c_pipeline"])
            for key, s in summary["a_inputs"].items():
                detail = (f"mean |error| {s['mean_abs_error_pct']:.0f}%, "
                          f"median {s['median_error_pct']:+.0f}%"
                          if key == "floor_area_m2" else f"{s['match']}/{s['n']} match")
                print(f"  (a) {key:<30} {detail}")
            print(f"  era from: {summary['epoch_source']}   heating from: {summary['heating_source']}")
            if "mean_band_agreement" in summary:
                print(f"  runs giving the commonest band: {summary['mean_band_agreement']:.0%}")

        report = {
            "provider": p,
            "model": model_name(p, settings) if p else None,
            "runs_per_home": args.runs if p else 0,
            "sample": str(args.sample),
            "summary": summary,
            "homes": report_homes,
        }
        path = OUT_DIR / (f"report_{p}.json" if p else "report_offline.json")
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {path}")


def _count(values) -> dict[str, int]:
    return dict(Counter(v or "none" for v in values))


if __name__ == "__main__":
    main()
