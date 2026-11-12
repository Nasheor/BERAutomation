"""Census priors for construction era, heating fuel and home size (Ireland only).

Street View cannot reliably separate adjacent decades: most older Irish homes have
replacement PVC windows and re-tiled roofs, and Claude reads 1980s estates as 1990s.
Heating equipment is usually out of sight, so the heating system is mostly a guess
from the setting. The census records both for every home, aggregated per Small Area
(80-120 homes, usually one estate or part of one). Its room counts also say how big
the homes are, which settles how many homes share a roof when the satellite image
cannot.

Data (built by ``scripts/build_census_data.py``; CSO Census 2022, CC BY 4.0):
- ``ber_automation/data/cso_year_built_sa2022.csv`` (table SAP2022T6T2SA)
- ``ber_automation/data/cso_heating_sa2022.csv`` (table SAP2022T6T5SA)
- ``ber_automation/data/cso_rooms_sa2022.csv`` (table SAP2022T6T4SA)
The point → Small Area lookup queries the CSO / Tailte Éireann Small Area boundary
service (ArcGIS REST, generalised 20 m), which also gives the CSO urban-area flag.
"""

from __future__ import annotations

import csv
import logging
import math
from functools import lru_cache
from pathlib import Path

import httpx

from ber_automation.models import (
    CensusArea,
    CensusEraPrior,
    ConstructionEpoch,
    Coordinates,
    Country,
    HeatingSystem,
    StreetViewAnalysis,
)

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
YEAR_BUILT_FILE = DATA_DIR / "cso_year_built_sa2022.csv"
HEATING_FILE = DATA_DIR / "cso_heating_sa2022.csv"
ROOMS_FILE = DATA_DIR / "cso_rooms_sa2022.csv"
SMALL_AREA_URL = (
    "https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/ArcGIS/rest/services/"
    "SMALL_AREA_2022_Genralised_20m_view/FeatureServer/0/query"
)

EPOCH_ORDER = [
    ConstructionEpoch.BEFORE_1980,
    ConstructionEpoch.EPOCH_1980_1990,
    ConstructionEpoch.EPOCH_1990_2000,
    ConstructionEpoch.EPOCH_2000_2010,
    ConstructionEpoch.AFTER_2010,
]

# Fewer stated households than this and a mix is too noisy to use.
MIN_HOUSEHOLDS = 20
# Era: Claude's band must hold at least this share of the area's homes to beat the
# prior when it is two or more bands from the dominant one...
DISTANT_MIN_SHARE = 0.10
# ...and this share, with this confidence, when it is the adjacent band.
ADJACENT_MIN_SHARE = 0.25
ADJACENT_MIN_CONFIDENCE = 0.8
# Street View confidence below which its classification is not used at all
# (matches the pipeline's gate).
STREETVIEW_MIN_CONFIDENCE = 0.4
# Heating: at this share of gas-heated homes the gas network serves the area, and an
# estate home defaults to gas whatever its age (older homes there may still use oil).
GAS_AVAILABLE_SHARE = 0.15
# Census fuel -> heating system, for the non-gas default. LPG, coal, peat and "other"
# have no HWB equivalent and are skipped.
FUEL_TO_SYSTEM = {
    "oil": HeatingSystem.OIL_BOILER,
    "electricity": HeatingSystem.ELECTRIC_DIRECT,
    "wood": HeatingSystem.BIOMASS,
}
# Home count: the census "rooms" of a home (kitchens, living rooms, bedrooms; not
# bathrooms or halls) and its gross floor area are modelled as floor ~ rooms x 20 m2
# (an Irish 3-bed semi: 5 rooms, ~100 m2), log-normal spread 0.25; "8 or more" counts
# as 8.5. Only the ranking of the possible counts is used, and on the validation houses
# it is the same for 18-22 m2 per room and a spread of 0.15-0.3.
FLOOR_M2_PER_ROOM = 20.0
ROOMS_8_PLUS = 8.5
FLOOR_AREA_SPREAD = 0.25
# Narrowest frontage of one home in a pair or row (old city terraces are ~4.5 m).
MIN_FRONTAGE_M = 4.0
MAX_UNITS = 12


def _load(path: Path) -> dict[str, dict[str, int]]:
    with path.open(encoding="utf-8") as f:
        return {
            row.pop("sa_guid"): {k: int(v) for k, v in row.items()}
            for row in csv.DictReader(f)
        }


@lru_cache(maxsize=1)
def _year_built_table() -> dict[str, dict[str, int]]:
    return _load(YEAR_BUILT_FILE)


@lru_cache(maxsize=1)
def _heating_table() -> dict[str, dict[str, int]]:
    return _load(HEATING_FILE)


@lru_cache(maxsize=1)
def _rooms_table() -> dict[str, dict[str, int]]:
    return _load(ROOMS_FILE)


def prior_from_counts(counts: dict[str, int]) -> CensusEraPrior | None:
    """Build the era prior from household counts per epoch; None when too few homes."""
    total = sum(counts.get(e.value, 0) for e in EPOCH_ORDER)
    if total < MIN_HOUSEHOLDS:
        return None
    shares = {e.value: counts.get(e.value, 0) / total for e in EPOCH_ORDER}
    dominant = max(EPOCH_ORDER, key=lambda e: shares[e.value])
    return CensusEraPrior(
        households=total,
        shares=shares,
        dominant_epoch=dominant,
        dominant_share=shares[dominant.value],
    )


def _shares(counts: dict[str, int] | None) -> tuple[int, dict[str, float]]:
    """(households, shares) of one table row; (0, {}) when too few households."""
    total = sum(counts.values()) if counts else 0
    if total < MIN_HOUSEHOLDS:
        return 0, {}
    return total, {k: v / total for k, v in counts.items()}


def area_from_counts(
    year_built: dict[str, int] | None,
    heating: dict[str, int] | None,
    small_area: str = "",
    urban: bool = False,
    urban_area: str = "",
    rooms: dict[str, int] | None = None,
) -> CensusArea:
    """Assemble a CensusArea from the count tables (any may be missing)."""
    area = CensusArea(small_area=small_area, urban=urban, urban_area=urban_area)
    if year_built:
        area.era = prior_from_counts(year_built)
    area.heating_households, area.heating_shares = _shares(heating)
    area.rooms_households, area.rooms_shares = _shares(rooms)
    return area


async def lookup_census_area(
    coords: Coordinates,
    country: Country | None = None,
    client: httpx.AsyncClient | None = None,
) -> CensusArea | None:
    """Return the census facts for the Small Area containing ``coords``.

    Ireland only (the default country). Returns None for other countries, when the
    point is outside every Small Area, or on any network/data error, so the
    pipeline falls back to Street View alone.
    """
    if country not in (None, Country.IRELAND):
        return None
    params = {
        "geometry": f"{coords.lng},{coords.lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "SA_GUID_2022,SA_PUB2022,SA_URBAN_AREA_FLAG,SA_URBAN_AREA_NAME",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=20) as c:
                resp = await c.get(SMALL_AREA_URL, params=params)
        else:
            resp = await client.get(SMALL_AREA_URL, params=params)
        resp.raise_for_status()
        features = resp.json().get("features") or []
        if not features:
            return None
        attrs = features[0]["attributes"]
        guid = attrs["SA_GUID_2022"]
        return area_from_counts(
            _year_built_table().get(guid),
            _heating_table().get(guid),
            small_area=str(attrs.get("SA_PUB2022") or ""),
            urban=attrs.get("SA_URBAN_AREA_FLAG") == 1,
            urban_area=str(attrs.get("SA_URBAN_AREA_NAME") or ""),
            rooms=_rooms_table().get(guid),
        )
    except Exception as e:  # network, JSON, missing data file
        log.warning("Census lookup failed: %s", e)
        return None


def _usable(analysis: StreetViewAnalysis | None) -> bool:
    return analysis is not None and analysis.confidence >= STREETVIEW_MIN_CONFIDENCE


def choose_epoch(
    prior: CensusEraPrior | None,
    analysis: StreetViewAnalysis | None,
) -> tuple[ConstructionEpoch | None, str]:
    """Combine the census era prior with Claude's Street View era.

    Returns (epoch, source), where source is "census", "streetview" or "default"
    (epoch None: let BuildingInput use its default).

    Rules:
    - No usable Street View reading: the area's dominant period.
    - No prior: Claude's reading.
    - Claude's band is adjacent to the dominant one: the dominant one, unless that band
      is common in the area (>= 25 %) and Claude is confident (>= 0.8). Adjacent decades
      look alike from the street, and Claude reads them one band newer.
    - Claude's band is two or more bands away: Claude, if at least 10 % of the area's
      homes are from that period (e.g. a 1970s house in a mixed area); otherwise the
      dominant period.
    """
    visual = analysis.construction_epoch if _usable(analysis) else None
    if prior is None:
        return (visual, "streetview") if visual is not None else (None, "default")
    dominant = prior.dominant_epoch
    if visual is None or visual == dominant:
        return dominant, "census"

    share = prior.shares.get(visual.value, 0.0)
    gap = abs(EPOCH_ORDER.index(visual) - EPOCH_ORDER.index(dominant))
    if gap == 1:
        keep = share >= ADJACENT_MIN_SHARE and analysis.confidence >= ADJACENT_MIN_CONFIDENCE
    else:
        keep = share >= DISTANT_MIN_SHARE
    return (visual, "streetview") if keep else (dominant, "census")


def choose_heating(
    area: CensusArea | None,
    analysis: StreetViewAnalysis | None,
    epoch: ConstructionEpoch | None = None,
) -> tuple[HeatingSystem | None, str]:
    """Pick the heating system: what Claude saw, else the area's census default.

    Returns (system, source): "streetview", "census" (heating-fuel mix),
    "census_urban" (urban flag only) or "default" (system None).

    Rules:
    - Claude saw a heating clue on the property (heating_observed): Claude's system.
    - Gas heats >= 15 % of the area's homes: the gas network is there → gas boiler.
    - Otherwise the area's most common of oil / electricity / wood. Electricity in a
      home built after 2010 means a heat pump (NZEB rules), not direct electric.
    - No usable fuel mix: CSO urban area → gas boiler, rural → oil boiler.
    - No census at all: Claude's guess (from the setting rule in its prompt).
    """
    if _usable(analysis) and analysis.heating_observed:
        return analysis.heating_system_guess, "streetview"
    if area is None:
        return (analysis.heating_system_guess, "streetview") if _usable(analysis) else (None, "default")

    shares = area.heating_shares
    if shares:
        if shares.get("gas", 0.0) >= GAS_AVAILABLE_SHARE:
            return HeatingSystem.GAS_BOILER, "census"
        fuel = max(FUEL_TO_SYSTEM, key=lambda k: shares.get(k, 0.0))
        system = FUEL_TO_SYSTEM[fuel]
        if system == HeatingSystem.ELECTRIC_DIRECT and epoch == ConstructionEpoch.AFTER_2010:
            system = HeatingSystem.HEAT_PUMP_AIR
        return system, "census"
    return (HeatingSystem.GAS_BOILER if area.urban else HeatingSystem.OIL_BOILER), "census_urban"


def home_size_likelihood(floor_m2: float, rooms_shares: dict[str, float]) -> float:
    """How typical a home of ``floor_m2`` gross floor area is for the area's room mix.

    A mixture, over the area's room counts, of log-normal floor areas centred on
    rooms x FLOOR_M2_PER_ROOM. Unnormalised: only compare values within one area.
    """
    if floor_m2 <= 0:
        return 0.0
    total = 0.0
    for key, share in rooms_shares.items():
        rooms = ROOMS_8_PLUS if key == "8+" else float(key)
        z = math.log(floor_m2 / (rooms * FLOOR_M2_PER_ROOM)) / FLOOR_AREA_SPREAD
        total += share * math.exp(-0.5 * z * z)
    return total


def choose_unit_count(
    block_long_m: float,
    block_short_m: float,
    claude_units: int,
    units_visible: bool,
    area: CensusArea | None,
    storeys: int | None = None,
    detached: bool = False,
) -> tuple[int, str]:
    """Number of homes in the satellite block outline: Claude's count or the census's.

    Returns (units, source), source "claude" or "census".

    Claude outlines the whole attached block and counts its homes, but party walls are
    often invisible from above, and then it guesses from the block length (a 17 m block
    came back as 1, 2, 3 or 4 homes across runs). When Claude says it could not see
    where the homes end, the count whose per-home floor area (block area / n x storeys)
    best fits the Small Area's room mix is used instead, among the counts that leave
    each home at least MIN_FRONTAGE_M wide (ties go to Claude's count).

    Claude's count is kept when it saw the boundaries, when Street View says the house
    is detached (never split it), and when there is no census room mix.
    """
    claude_units = max(1, claude_units)
    if units_visible or detached or area is None or not area.rooms_shares:
        return claude_units, "claude"
    floors = max(1, storeys or 2)
    candidates = {claude_units} | {
        n for n in range(1, MAX_UNITS + 1) if n == 1 or block_long_m / n >= MIN_FRONTAGE_M
    }

    def score(n: int) -> tuple[float, bool]:
        floor = block_long_m * block_short_m / n * floors
        return home_size_likelihood(floor, area.rooms_shares), n == claude_units

    return max(candidates, key=score), "census"
