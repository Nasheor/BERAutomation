"""Check the official-BER sample and show how balanced it is.

Usage:
    python scripts/check_official_sample.py
    python scripts/check_official_sample.py path/to/other.csv

Reads data/validation/official/sample.csv (columns: see the README next to it), lists
every problem found in the rows, and prints counts per county, settlement, dwelling
type, era and BER band against the study targets. No API calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ber_automation.evaluation.official_sample import (  # noqa: E402
    TARGET_COUNTIES,
    TARGET_HOMES,
    load_official_sample,
    summarise,
)

DEFAULT_SAMPLE = ROOT / "data" / "validation" / "official" / "sample.csv"


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE
    homes, problems = load_official_sample(path)

    print(f"{path}")
    print(f"Usable homes: {len(homes)} of {TARGET_HOMES} planned")
    if problems:
        print(f"\nProblems ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("No problems found.")

    if homes:
        summary = summarise(homes)
        counties = len(summary["county"])
        print(f"\nCounties: {counties} (plan: at least {TARGET_COUNTIES})")
        for title, counts in summary.items():
            print(f"\n{title}")
            for value, n in counts.items():
                print(f"  {value:<18} {n:>4}  {100 * n / len(homes):>3.0f}%")
        with_inputs = sum(
            1 for h in homes if h.dwelling_type and h.year_built and h.floor_area_m2
        )
        checked = sum(1 for h in homes if h.register_checked)
        print(f"\nWith type, year and floor area from the certificate: {with_inputs}")
        print(f"Checked against the SEAI register: {checked}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
