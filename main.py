"""CLI entry point for BER Automation pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.models import (
    BERResult,
    BuildingInput,
    BuildingType,
    ConstructionEpoch,
    Country,
    HeatingSystem,
    RetrofitInput,
)
from ber_automation.pipeline import BERPipeline


def main():
    parser = argparse.ArgumentParser(
        description="BER Automation — estimate Building Energy Rating from Eircode or manual input"
    )
    sub = parser.add_subparsers(dest="command")

    # --- pipeline command ---
    pipe_p = sub.add_parser("pipeline", help="Run full pipeline from Eircode")
    pipe_p.add_argument("eircode", help="Irish Eircode (e.g. D02X285)")
    pipe_p.add_argument("--output-dir", default="output", help="Output directory")

    # --- manual command ---
    man_p = sub.add_parser("manual", help="Calculate BER from manual inputs")
    man_p.add_argument("--length", type=float, required=True, help="Building length (m)")
    man_p.add_argument("--width", type=float, required=True, help="Building width (m)")
    man_p.add_argument("--storeys", type=int, default=2, help="Heated storeys")
    man_p.add_argument("--storey-height", type=float, default=3.0, help="Storey height (m)")
    man_p.add_argument(
        "--type",
        choices=[bt.value for bt in BuildingType],
        default="detached",
    )
    man_p.add_argument(
        "--epoch",
        choices=[e.value for e in ConstructionEpoch],
        default="before_1980",
    )
    man_p.add_argument(
        "--country",
        choices=[c.value for c in Country],
        default="ireland",
    )
    man_p.add_argument(
        "--heating",
        choices=[h.value for h in HeatingSystem],
        default="gas_boiler",
    )
    man_p.add_argument("--hw-electric", action="store_true", help="Hot water electric & separate")

    # --- streamlit command ---
    sub.add_parser("app", help="Launch Streamlit web app")

    args = parser.parse_args()

    if args.command == "pipeline":
        _run_pipeline(args)
    elif args.command == "manual":
        _run_manual(args)
    elif args.command == "app":
        _run_app()
    else:
        parser.print_help()
        sys.exit(1)


def _run_pipeline(args):
    pipeline = BERPipeline(output_dir=args.output_dir)
    result = asyncio.run(pipeline.run(args.eircode))

    if result.errors:
        print("Warnings:")
        for err in result.errors:
            print(f"  - {err}")

    if result.ber_result:
        _print_ber(result.ber_result)
    else:
        print("BER calculation could not be completed.")
        sys.exit(1)


def _run_manual(args):
    building = BuildingInput(
        length=args.length,
        width=args.width,
        heated_storeys=args.storeys,
        storey_height=args.storey_height,
        building_type=BuildingType(args.type),
        construction_epoch=ConstructionEpoch(args.epoch),
        country=Country(args.country),
        heating_system=HeatingSystem(args.heating),
        hot_water_electric_separate=args.hw_electric,
    )

    calculator = HWBCalculator()
    ber = calculator.calculate_ber(building)
    _print_ber(ber)


def _run_app():
    import subprocess
    app_path = Path(__file__).parent / "app" / "streamlit_app.py"
    subprocess.run(["streamlit", "run", str(app_path)], check=True)


def _print_ber(ber: BERResult):
    hw = ber.hwb_result
    print(f"\n{'='*50}")
    print(f"  BER Rating: {ber.ber_band}")
    print(f"  Energy: {ber.kwh_per_m2:.0f} kWh/m2/yr (primary)")
    print(f"{'='*50}")
    print(f"  Floor area:        {hw.floor_area:.0f} m2")
    print(f"  Heated volume:     {hw.heated_volume:.0f} m3")
    print(f"  HWB:               {hw.hwb:.1f} kWh/m2/yr")
    print(f"  Final energy:      {hw.final_energy_kwh_per_m2:.1f} kWh/m2/yr")
    print(f"  Hot water:         {hw.hot_water_kwh:.0f} kWh/yr")
    print(f"  CO2:               {hw.co2_kg_per_m2:.1f} kg/m2/yr")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
