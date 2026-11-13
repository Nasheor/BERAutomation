"""The official-BER sample for the paper: one row per home with its certificate values.

The sample is a CSV filled in by hand (data/validation/official/sample.csv; the columns
are described in the README next to it). This module reads it and reports problems in the
rows, so typing mistakes are caught while the sample is being collected.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ber_automation.ber_engine.constants import BER_BANDS
from ber_automation.ber_engine.rating import get_ber_band
from ber_automation.models import ConstructionEpoch, HeatingSystem

REQUIRED_COLUMNS: tuple[str, ...] = (
    "id", "eircode", "county", "settlement", "listing_source", "date_recorded",
    "ber_number", "ber_band", "ber_kwh_m2_yr",
)
OPTIONAL_COLUMNS: tuple[str, ...] = (
    "listing_url", "dwelling_type", "year_built", "floor_area_m2", "storeys", "heating",
    "register_checked", "notes",
)
COLUMNS: tuple[str, ...] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

SETTLEMENTS: tuple[str, ...] = ("urban", "rural")
# The pipeline handles houses only; an end-of-terrace house has one shared wall, so it
# is recorded as semi_detached
DWELLING_TYPES: tuple[str, ...] = ("detached", "semi_detached", "terraced")
BANDS: tuple[str, ...] = tuple(band for band, _, _ in BER_BANDS)
HEATING_VALUES: tuple[str, ...] = tuple(h.value for h in HeatingSystem)

# Study design targets (docs/plans/mistral_provider_and_paper_plan.md)
TARGET_HOMES = 250
TARGET_COUNTIES = 4

_EIRCODE = re.compile(r"^([AC-FHKNPRTV-Y]\d{2}|D6W)([0-9AC-FHKNPRTV-Y]{4})$")
_BER_NUMBER = re.compile(r"^\d{9}$")


class OfficialHome(BaseModel):
    """One home of the sample, with the values from its listing and BER certificate."""
    id: str
    eircode: str                      # normalised, e.g. "T12 K7AC"
    county: str
    settlement: str                   # "urban" | "rural"
    listing_source: str
    date_recorded: date
    ber_number: str
    ber_band: str
    ber_kwh_m2_yr: float
    listing_url: str = ""
    dwelling_type: Optional[str] = None
    year_built: Optional[int] = None
    floor_area_m2: Optional[float] = None
    storeys: Optional[int] = None
    heating: Optional[HeatingSystem] = None
    register_checked: bool = False
    notes: str = ""

    @property
    def epoch(self) -> ConstructionEpoch | None:
        """Construction era of the calculator for the certificate's year of construction."""
        return epoch_from_year(self.year_built) if self.year_built else None


def epoch_from_year(year: int) -> ConstructionEpoch:
    """The calculator's construction era for a year of construction."""
    if year < 1980:
        return ConstructionEpoch.BEFORE_1980
    if year < 1990:
        return ConstructionEpoch.EPOCH_1980_1990
    if year < 2000:
        return ConstructionEpoch.EPOCH_1990_2000
    if year < 2010:
        return ConstructionEpoch.EPOCH_2000_2010
    return ConstructionEpoch.AFTER_2010


def normalise_eircode(text: str) -> str | None:
    """"t12k7ac" → "T12 K7AC"; None when the text is not an Eircode."""
    match = _EIRCODE.match(re.sub(r"\s+", "", text).upper())
    return f"{match.group(1)} {match.group(2)}" if match else None


def _number(text: str, low: float, high: float) -> float | None:
    """The number in *text* when it lies within [low, high], else None."""
    try:
        value = float(text.replace(",", ""))
    except ValueError:
        return None
    return value if low <= value <= high else None


def _parse_row(row: dict[str, str], line: int) -> tuple[OfficialHome | None, list[str]]:
    """One CSV row → (home, problems). The home is None when a required value is unusable."""
    cell = {k: (row.get(k) or "").strip() for k in COLUMNS}
    where = f"line {line} (id {cell['id'] or '?'})"
    problems: list[str] = []
    fatal = False

    for name in REQUIRED_COLUMNS:
        if not cell[name]:
            problems.append(f"{where}: {name} is empty")
            fatal = True

    eircode = normalise_eircode(cell["eircode"]) if cell["eircode"] else None
    if cell["eircode"] and eircode is None:
        problems.append(f"{where}: eircode {cell['eircode']!r} is not a valid Eircode")
        fatal = True

    settlement = cell["settlement"].lower()
    if settlement and settlement not in SETTLEMENTS:
        problems.append(f"{where}: settlement {cell['settlement']!r} must be urban or rural")
        fatal = True

    recorded: date | None = None
    if cell["date_recorded"]:
        try:
            recorded = date.fromisoformat(cell["date_recorded"])
        except ValueError:
            problems.append(f"{where}: date_recorded {cell['date_recorded']!r} must be YYYY-MM-DD")
            fatal = True

    ber_number = re.sub(r"\s+", "", cell["ber_number"])
    if ber_number and not _BER_NUMBER.match(ber_number):
        problems.append(f"{where}: ber_number {cell['ber_number']!r} must have 9 digits")
        fatal = True

    band = cell["ber_band"].upper()
    if band and band not in BANDS:
        problems.append(f"{where}: ber_band {cell['ber_band']!r} is not a BER band (A1 to G)")
        fatal = True

    kwh = _number(cell["ber_kwh_m2_yr"], 0.01, 2000) if cell["ber_kwh_m2_yr"] else None
    if cell["ber_kwh_m2_yr"] and kwh is None:
        problems.append(f"{where}: ber_kwh_m2_yr {cell['ber_kwh_m2_yr']!r} is not a usable number")
        fatal = True
    if kwh is not None and band in BANDS and get_ber_band(kwh)[0] != band:
        problems.append(
            f"{where}: ber_band {band} does not match {kwh:g} kWh/m2/yr "
            f"(that value is band {get_ber_band(kwh)[0]}); check both against the listing"
        )

    # Optional certificate values: a bad one is reported and left out
    dwelling = cell["dwelling_type"].lower().replace("-", "_").replace(" ", "_") or None
    if dwelling and dwelling not in DWELLING_TYPES:
        problems.append(f"{where}: dwelling_type {cell['dwelling_type']!r} must be one of "
                        f"{', '.join(DWELLING_TYPES)}")
        dwelling = None

    year = _number(cell["year_built"], 1700, date.today().year) if cell["year_built"] else None
    if cell["year_built"] and year is None:
        problems.append(f"{where}: year_built {cell['year_built']!r} is not a usable year")

    area = _number(cell["floor_area_m2"], 20, 1000) if cell["floor_area_m2"] else None
    if cell["floor_area_m2"] and area is None:
        problems.append(f"{where}: floor_area_m2 {cell['floor_area_m2']!r} is outside 20 to 1000")

    storeys = _number(cell["storeys"], 1, 4) if cell["storeys"] else None
    if cell["storeys"] and (storeys is None or storeys != int(storeys)):
        problems.append(f"{where}: storeys {cell['storeys']!r} must be 1, 2, 3 or 4")
        storeys = None

    heating = cell["heating"].lower() or None
    if heating and heating not in HEATING_VALUES:
        problems.append(f"{where}: heating {cell['heating']!r} must be one of "
                        f"{', '.join(HEATING_VALUES)}")
        heating = None

    checked = cell["register_checked"].lower()
    if checked not in ("", "yes", "no"):
        problems.append(f"{where}: register_checked {cell['register_checked']!r} must be yes or no")

    if fatal:
        return None, problems
    return OfficialHome(
        id=cell["id"], eircode=eircode, county=cell["county"].title(), settlement=settlement,
        listing_source=cell["listing_source"], date_recorded=recorded, ber_number=ber_number,
        ber_band=band, ber_kwh_m2_yr=kwh, listing_url=cell["listing_url"],
        dwelling_type=dwelling, year_built=int(year) if year else None, floor_area_m2=area,
        storeys=int(storeys) if storeys else None,
        heating=HeatingSystem(heating) if heating else None,
        register_checked=checked == "yes", notes=cell["notes"],
    ), problems


def check_row(row: dict[str, str]) -> tuple[OfficialHome | None, list[str]]:
    """Check one row (column → text) the way load_official_sample does.

    Returns:
        (home, problems): home is None when a required value is unusable.
    """
    return _parse_row(row, 0)


# Dwelling types as the SEAI register writes them → the sample's values. An end-of-terrace
# house has one shared wall, so it counts as semi_detached (see DWELLING_TYPES).
_REGISTER_DWELLINGS: dict[str, str] = {
    "detached house": "detached",
    "semi-detached house": "semi_detached",
    "end of terrace house": "semi_detached",
    "mid-terrace house": "terraced",
}


def dwelling_from_register(text: str) -> str | None:
    """"Semi-detached house" → "semi_detached"; None for flats and unknown text."""
    key = re.sub(r"\s+", " ", text.strip().lower()).replace("end-of-terrace", "end of terrace")
    if key in _REGISTER_DWELLINGS:
        return _REGISTER_DWELLINGS[key]
    simple = key.replace("-", "_").replace(" ", "_")
    return simple if simple in DWELLING_TYPES else None


def parse_rating(text: str) -> tuple[str, float] | None:
    """The register's "Building Energy Rating" text → (band, kWh/m²/yr).

    "C2 177.03 (kWh/m2/yr)" → ("C2", 177.03). None when band or value is missing.
    """
    match = re.match(r"^\s*([A-Ga-g][1-3]?)\s+([\d,]+(?:\.\d+)?)", text)
    if not match:
        return None
    band = match.group(1).upper()
    value = _number(match.group(2), 0.01, 2000)
    if band not in BANDS or value is None:
        return None
    return band, value


def first_number(text: str) -> str:
    """The first number in *text* ("137.17 (m2)" → "137.17"), or "" when there is none."""
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    return match.group(0).replace(",", "") if match else ""


def load_official_sample(path: str | Path) -> tuple[list[OfficialHome], list[str]]:
    """Read the sample CSV.

    Args:
        path: The CSV file (UTF-8, with or without a byte-order mark; header row first).

    Returns:
        (homes, problems): the usable rows, and one message per problem found. A row
        with an unusable required value is left out of homes.
    """
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            return [], [f"missing column(s): {', '.join(missing)}"]
        homes: list[OfficialHome] = []
        problems: list[str] = []
        for line, row in enumerate(reader, start=2):
            row = {(k or "").strip(): v for k, v in row.items()}
            if not any((v or "").strip() for v in row.values()):
                continue  # blank line
            home, row_problems = _parse_row(row, line)
            problems.extend(row_problems)
            if home:
                homes.append(home)

    for field in ("id", "eircode", "ber_number"):
        counts = Counter(getattr(h, field) for h in homes)
        problems.extend(
            f"{field} {value} appears {n} times" for value, n in counts.items() if n > 1
        )
    return homes, problems


def summarise(homes: list[OfficialHome]) -> dict[str, dict[str, int]]:
    """Counts per county, settlement, dwelling type, era and band, to balance the sample."""
    def count(values) -> dict[str, int]:
        return dict(sorted(Counter(v if v else "(not recorded)" for v in values).items()))

    band_order = {band: i for i, band in enumerate(BANDS)}
    bands = Counter(h.ber_band for h in homes)
    return {
        "county": count(h.county for h in homes),
        "settlement": count(h.settlement for h in homes),
        "dwelling_type": count(h.dwelling_type for h in homes),
        "era": count(h.epoch.value if h.epoch else None for h in homes),
        "ber_band": dict(sorted(bands.items(), key=lambda kv: band_order[kv[0]])),
    }
