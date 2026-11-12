"""Census priors for construction era and heating fuel (Ireland only).

Street View cannot reliably separate adjacent decades: most older Irish homes have
replacement PVC windows and re-tiled roofs, and Claude reads 1980s estates as 1990s.
Heating equipment is usually out of sight, so the heating system is mostly a guess
from the setting. The census records both for every home, aggregated per Small Area
(80-120 homes, usually one estate or part of one).

Data (built by ``scripts/build_census_data.py``; CSO Census 2022, CC BY 4.0):
- ``ber_automation/data/cso_year_built_sa2022.csv`` (table SAP2022T6T2SA)
- ``ber_automation/data/cso_heating_sa2022.csv`` (table SAP2022T6T5SA)
The point → Small Area lookup queries the CSO / Tailte Éireann Small Area boundary
service (ArcGIS REST, generalised 20 m), which also gives the CSO urban-area flag.
"""

from __future__ import annotations

import csv
import logging
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


def area_from_counts(
    year_built: dict[str, int] | None,
    heating: dict[str, int] | None,
    small_area: str = "",
    urban: bool = False,
    urban_area: str = "",
) -> CensusArea:
    """Assemble a CensusArea from the two count tables (either may be missing)."""
    area = CensusArea(small_area=small_area, urban=urban, urban_area=urban_area)
    if year_built:
        area.era = prior_from_counts(year_built)
    if heating:
        total = sum(heating.values())
        if total >= MIN_HOUSEHOLDS:
            area.heating_households = total
            area.heating_shares = {k: v / total for k, v in heating.items()}
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
