"""Add homes to the official-BER sample, one at a time, as a step-by-step checklist.

Usage:
    python scripts/add_official_home.py
    python scripts/add_official_home.py path/to/other.csv

For each home it asks for the values from the property listing, then tells you which BER
number to look up on the SEAI register (by hand, in your browser) and asks for the values
shown there. Every answer is checked as you type it; a home is saved only when the whole
row passes the same checks as scripts/check_official_sample.py. No web requests.
Type "skip" at any question to drop the current home, "quit" to stop.
"""

from __future__ import annotations

import csv
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ber_automation.evaluation.official_sample import (  # noqa: E402
    COLUMNS,
    DWELLING_TYPES,
    HEATING_VALUES,
    TARGET_COUNTIES,
    TARGET_HOMES,
    check_row,
    dwelling_from_register,
    first_number,
    load_official_sample,
    normalise_eircode,
    parse_rating,
    summarise,
)

DEFAULT_SAMPLE = ROOT / "data" / "validation" / "official" / "sample.csv"
REGISTER_URL = "https://ndber.seai.ie/pass/ber/search.aspx"


class Skip(Exception):
    """The user typed "skip": drop the current home."""


class Quit(Exception):
    """The user typed "quit": stop adding homes."""


def ask(prompt: str, check: Callable[[str], tuple[str | None, str]], read=input,
        optional: bool = False) -> str:
    """Ask until *check* accepts the answer; return the accepted (cleaned) value.

    *check* returns (value, message): value None means rejected, and message says why.
    With *optional*, an empty answer is accepted and returns "".
    """
    while True:
        answer = read(f"  {prompt}: ").strip()
        if answer.lower() == "skip":
            raise Skip
        if answer.lower() == "quit":
            raise Quit
        if not answer:
            if optional:
                return ""
            print("    Needed. Type it, or 'skip' to drop this home.")
            continue
        value, message = check(answer)
        if value is not None:
            return value
        print(f"    {message}")


def _one_of(values: tuple[str, ...]) -> Callable[[str], tuple[str | None, str]]:
    def check(text: str) -> tuple[str | None, str]:
        value = text.lower().replace("-", "_").replace(" ", "_")
        return (value, "") if value in values else (None, f"Use one of: {', '.join(values)}")
    return check


def _url(text: str) -> tuple[str | None, str]:
    host = urlparse(text).netloc
    return (text, "") if host else (None, "Paste the full link, starting with https://")


def run(path: Path, read=input, today: date | None = None) -> int:
    """The checklist loop. Returns the number of homes added."""
    today = today or date.today()
    homes, problems = load_official_sample(path)
    if problems:
        print("The sample has problems; fix them first (python scripts/check_official_sample.py).")
        for problem in problems:
            print(f"  - {problem}")
        return 0
    eircodes = {h.eircode for h in homes}
    ber_numbers = {h.ber_number for h in homes}
    numeric_ids = [int(h.id) for h in homes if h.id.isdigit()]
    next_id = max(numeric_ids, default=0) + 1
    added = 0

    print(f"{path}\n{len(homes)} of {TARGET_HOMES} homes so far. "
          "Type 'skip' to drop a home, 'quit' to stop.")

    while True:
        print(f"\n=== Home {next_id} ===")
        try:
            row = _ask_home(read, eircodes, ber_numbers)
        except Skip:
            print("  Skipped; nothing saved.")
            continue
        except Quit:
            break

        row.update(id=str(next_id), date_recorded=today.isoformat(), register_checked="yes")
        home, row_problems = check_row(row)
        if home is None or row_problems:
            print("  Not saved:")
            for problem in row_problems:
                print(f"    - {problem.split(': ', 1)[-1]}")
            continue

        print(f"\n  {home.eircode}, {home.county} ({home.settlement}): {home.ber_band} "
              f"{home.ber_kwh_m2_yr:g} kWh/m2/yr, {home.dwelling_type or '?'}, "
              f"{home.year_built or '?'}, {home.floor_area_m2 or '?'} m2")
        try:
            confirm = read("  Save this home? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if confirm not in ("", "y", "yes"):
            print("  Not saved.")
            continue

        _append(path, row)
        eircodes.add(home.eircode)
        ber_numbers.add(home.ber_number)
        homes.append(home)
        next_id += 1
        added += 1
        counties = len({h.county for h in homes})
        print(f"  Saved. {len(homes)} of {TARGET_HOMES} homes, "
              f"{counties} of {TARGET_COUNTIES}+ counties.")

    _print_progress(homes, added)
    return added


def _ask_home(read, eircodes: set[str], ber_numbers: set[str]) -> dict[str, str]:
    """Ask for one home's values. Raises Skip or Quit."""
    print("  From the listing:")
    url = ask("Listing link", _url, read)

    def eircode_check(text: str) -> tuple[str | None, str]:
        code = normalise_eircode(text)
        if code is None:
            return None, "Not a valid Eircode (e.g. T12 K7AC)."
        if code in eircodes:
            return None, f"{code} is already in the sample. Type 'skip'."
        return code, ""

    def ber_number_check(text: str) -> tuple[str | None, str]:
        number = "".join(text.split())
        if not (number.isdigit() and len(number) == 9):
            return None, "A BER number has 9 digits."
        if number in ber_numbers:
            return None, f"BER {number} is already in the sample. Type 'skip'."
        return number, ""

    eircode = ask("Eircode", eircode_check, read)
    county = ask("County (e.g. Cork)", lambda t: (t.strip().title(), ""), read)
    settlement = ask("urban or rural", _one_of(("urban", "rural")), read)
    ber_number = ask("BER number (9 digits)", ber_number_check, read)
    storeys = ask("Storeys, if the listing says (Enter to leave out)",
                  lambda t: (t, "") if t in ("1", "2", "3", "4") else (None, "1 to 4"),
                  read, optional=True)
    heating = ask("Heating, if the listing says (Enter to leave out)",
                  _one_of(HEATING_VALUES), read, optional=True)

    print(f"\n  Now on the SEAI register ({REGISTER_URL}), search {ber_number}:")

    def rating_check(text: str) -> tuple[str | None, str]:
        rating = parse_rating(text)
        return (text, "") if rating else (None, "Copy it as shown, e.g. 'C2 177.03'.")

    rating = parse_rating(ask("Building Energy Rating (e.g. C2 177.03)", rating_check, read))

    def dwelling_check(text: str) -> tuple[str | None, str]:
        value = dwelling_from_register(text)
        if value:
            return value, ""
        return None, (f"Houses only ({', '.join(DWELLING_TYPES)}). For a flat or "
                      "maisonette, type 'skip'.")

    dwelling = ask("Dwelling Type (e.g. Semi-detached house)", dwelling_check, read)
    year = ask("Year Of Construction",
               lambda t: (first_number(t), "") if first_number(t) else (None, "e.g. 2001"), read)
    area = ask("Floor Area",
               lambda t: (first_number(t), "") if first_number(t) else (None, "e.g. 137.17"),
               read)
    issued = ask("Date Of Issue (Enter to leave out)", lambda t: (t, ""), read, optional=True)
    notes = ask("Notes (Enter for none)", lambda t: (t, ""), read, optional=True)
    if issued:
        notes = f"Register: issued {issued}" + (f"; {notes}" if notes else "")

    return {
        "eircode": eircode, "county": county, "settlement": settlement,
        "listing_source": urlparse(url).netloc.removeprefix("www."),
        "ber_number": ber_number, "ber_band": rating[0], "ber_kwh_m2_yr": f"{rating[1]:g}",
        "listing_url": url, "dwelling_type": dwelling, "year_built": year,
        "floor_area_m2": area, "storeys": storeys, "heating": heating, "notes": notes,
    }


def _append(path: Path, row: dict[str, str]) -> None:
    """Append one row to the CSV, in column order, keeping its CRLF line endings."""
    text = path.read_bytes()
    with open(path, "a", encoding="utf-8", newline="") as handle:
        if text and not text.endswith(b"\n"):
            handle.write("\r\n")
        csv.writer(handle, lineterminator="\r\n").writerow([row.get(c, "") for c in COLUMNS])


def _print_progress(homes, added: int) -> None:
    print(f"\nAdded {added} home(s). Sample: {len(homes)} of {TARGET_HOMES}.")
    if homes:
        for title, counts in summarise(homes).items():
            print(f"  {title}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE
    try:
        run(path)
    except (EOFError, KeyboardInterrupt):
        print("\nStopped. Homes saved so far are kept.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
