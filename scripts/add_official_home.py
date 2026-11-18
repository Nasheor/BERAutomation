"""Add homes to the official-BER sample, one at a time, as a step-by-step checklist.

Usage:
    python scripts/add_official_home.py
    python scripts/add_official_home.py --type
    python scripts/add_official_home.py path/to/other.csv

For each home you open the listing and the SEAI register in your browser, by hand, and
copy each page (Ctrl+A, Ctrl+C); the script reads the values from the clipboard and asks
only for what it cannot find there. With --type it asks for every value instead. Every
value is checked; a home is saved only when the whole row passes the same checks as
scripts/check_official_sample.py. No web requests.
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
    county_from_listing_url,
    dwelling_from_register,
    first_number,
    load_official_sample,
    normalise_eircode,
    parse_listing_text,
    parse_rating,
    parse_register_text,
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


def read_clipboard() -> str:
    """The text on the clipboard ("" when it holds no text)."""
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    except tkinter.TclError:
        return ""
    finally:
        root.destroy()


def _wait(prompt: str, read) -> str:
    """Wait for Enter; returns what was typed, lower-case. Raises Skip or Quit."""
    answer = read(f"  {prompt}: ").strip().lower()
    if answer == "skip":
        raise Skip
    if answer == "quit":
        raise Quit
    return answer


def run(path: Path, read=input, today: date | None = None,
        clipboard: Callable[[], str] | None = None) -> int:
    """The checklist loop. Returns the number of homes added.

    With *clipboard* (a function returning the clipboard text) the values are read from
    the copied listing and register pages; without it every value is asked for.
    """
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
            row = _ask_home(read, eircodes, ber_numbers, clipboard)
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


def _ask_home(read, eircodes: set[str], ber_numbers: set[str],
              clipboard: Callable[[], str] | None = None) -> dict[str, str]:
    """Get one home's values, from the copied pages or by asking. Raises Skip or Quit."""
    found: dict[str, str] = {}

    def get(key: str, prompt: str, check, optional: bool = False) -> str:
        """The value found on the copied page when it passes *check*, else ask for it."""
        text = found.get(key, "")
        if text:
            value, message = check(text)
            if value is not None:
                print(f"  {prompt}: {value}")
                return value
            print(f"  {prompt}: found {text!r}. {message}")
        return ask(prompt, check, read, optional)

    print("  From the listing:")
    url = ask("Listing link", _url, read)
    if clipboard:
        _wait("Copy the listing page (Ctrl+A, Ctrl+C), then press Enter", read)
        found.update(parse_listing_text(clipboard()))
        found["county"] = county_from_listing_url(url)
        if "eircode_candidates" in found:
            print(f"  The page shows several Eircodes: {found['eircode_candidates']}")

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

    eircode = get("eircode", "Eircode", eircode_check)
    county = get("county", "County (e.g. Cork)", lambda t: (t.strip().title(), ""))
    settlement = ask("urban or rural", _one_of(("urban", "rural")), read)
    ber_number = get("ber_number", "BER number (9 digits)", ber_number_check)
    storeys = heating = ""
    if not clipboard:
        storeys = ask("Storeys, if the listing says (Enter to leave out)",
                      lambda t: (t, "") if t in ("1", "2", "3", "4") else (None, "1 to 4"),
                      read, optional=True)
        heating = ask("Heating, if the listing says (Enter to leave out)",
                      _one_of(HEATING_VALUES), read, optional=True)

    print(f"\n  Now on the SEAI register ({REGISTER_URL}), search {ber_number}:")
    while clipboard:
        answer = _wait("Copy the result page (Ctrl+A, Ctrl+C), then press Enter "
                       "('type' to type the values)", read)
        if answer == "type":
            break
        text = clipboard()
        if ber_number not in "".join(text.split()):
            print(f"    The copied page does not show BER {ber_number}. Copy it again.")
            continue
        values = parse_register_text(text)
        if "rating" not in values:
            print("    No Building Energy Rating on the copied page. Copy it again.")
            continue
        found.update(values)
        break

    def rating_check(text: str) -> tuple[str | None, str]:
        rating = parse_rating(text)
        return (text, "") if rating else (None, "Copy it as shown, e.g. 'C2 177.03'.")

    rating = parse_rating(get("rating", "Building Energy Rating (e.g. C2 177.03)",
                              rating_check))

    def dwelling_check(text: str) -> tuple[str | None, str]:
        value = dwelling_from_register(text)
        if value:
            return value, ""
        return None, (f"Houses only ({', '.join(DWELLING_TYPES)}). For a flat or "
                      "maisonette, type 'skip'.")

    dwelling = get("dwelling", "Dwelling Type (e.g. Semi-detached house)", dwelling_check)
    year = get("year", "Year Of Construction",
               lambda t: (first_number(t), "") if first_number(t) else (None, "e.g. 2001"))
    area = get("area", "Floor Area",
               lambda t: (first_number(t), "") if first_number(t) else (None, "e.g. 137.17"))
    issued = get("issued", "Date Of Issue (Enter to leave out)", lambda t: (t, ""),
                 optional=True)
    notes = "" if clipboard else ask("Notes (Enter for none)", lambda t: (t, ""), read,
                                     optional=True)
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
    args = [a for a in sys.argv[1:] if a != "--type"]
    path = Path(args[0]) if args else DEFAULT_SAMPLE
    clipboard = None if "--type" in sys.argv[1:] else read_clipboard
    if clipboard:
        try:
            read_clipboard()
        except Exception:  # no tkinter or no display: fall back to typing
            print("Cannot read the clipboard here; asking for every value instead.")
            clipboard = None
    try:
        run(path, clipboard=clipboard)
    except (EOFError, KeyboardInterrupt):
        print("\nStopped. Homes saved so far are kept.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
