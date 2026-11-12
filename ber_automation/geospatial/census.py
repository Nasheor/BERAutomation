"""Construction-era prior from CSO Census 2022 (Ireland only).

Street View cannot reliably separate adjacent decades: most older Irish homes have
replacement PVC windows and re-tiled roofs, and Claude reads 1980s estates as 1990s.
The census records the year built of every home, aggregated per Small Area (80-120
homes, usually one estate or part of one). The mix of build periods at the property's
location is a strong prior for its era.

Data: ``ber_automation/data/cso_year_built_sa2022.csv`` (built by
``scripts/build_census_year_built.py`` from CSO table SAP2022T6T2SA; CC BY 4.0,
Central Statistics Office). The point → Small Area lookup queries the CSO / Tailte
Éireann Small Area boundary service (ArcGIS REST, generalised 20 m).
"""

from __future__ import annotations

import csv
import logging
from functools import lru_cache
from pathlib import Path

import httpx

from ber_automation.models import (
    CensusEraPrior,
    ConstructionEpoch,
    Coordinates,
    Country,
    StreetViewAnalysis,
)

log = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "cso_year_built_sa2022.csv"
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

# Fewer stated households than this and the mix is too noisy to use.
MIN_HOUSEHOLDS = 20
# Claude's band must hold at least this share of the area's homes to beat the prior
# when it is two or more bands from the dominant one.
DISTANT_MIN_SHARE = 0.10
# ...and this share, with this confidence, when it is the adjacent band.
ADJACENT_MIN_SHARE = 0.25
ADJACENT_MIN_CONFIDENCE = 0.8
# Street View confidence below which its classification is not used at all
# (matches the pipeline's gate).
STREETVIEW_MIN_CONFIDENCE = 0.4


@lru_cache(maxsize=1)
def _year_built_table() -> dict[str, dict[str, int]]:
    with DATA_FILE.open(encoding="utf-8") as f:
        return {
            row.pop("sa_guid"): {k: int(v) for k, v in row.items()}
            for row in csv.DictReader(f)
        }


def prior_from_counts(
    counts: dict[str, int], small_area: str = "", urban_area: str = "",
) -> CensusEraPrior | None:
    """Build the prior from household counts per epoch; None when too few homes."""
    total = sum(counts.get(e.value, 0) for e in EPOCH_ORDER)
    if total < MIN_HOUSEHOLDS:
        return None
    shares = {e.value: counts.get(e.value, 0) / total for e in EPOCH_ORDER}
    dominant = max(EPOCH_ORDER, key=lambda e: shares[e.value])
    return CensusEraPrior(
        small_area=small_area,
        urban_area=urban_area,
        households=total,
        shares=shares,
        dominant_epoch=dominant,
        dominant_share=shares[dominant.value],
    )


async def lookup_era_prior(
    coords: Coordinates,
    country: Country | None = None,
    client: httpx.AsyncClient | None = None,
) -> CensusEraPrior | None:
    """Return the census era prior for the Small Area containing ``coords``.

    Ireland only (the default country). Returns None for other countries, when the
    point is outside every Small Area, or on any network/data error, so the
    pipeline falls back to the Street View era.
    """
    if country not in (None, Country.IRELAND):
        return None
    params = {
        "geometry": f"{coords.lng},{coords.lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "SA_GUID_2022,SA_PUB2022,SA_URBAN_AREA_NAME",
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
        counts = _year_built_table().get(attrs["SA_GUID_2022"])
    except Exception as e:  # network, JSON, missing data file
        log.warning("Census era lookup failed: %s", e)
        return None
    if counts is None:
        return None
    return prior_from_counts(
        counts,
        small_area=str(attrs.get("SA_PUB2022") or ""),
        urban_area=str(attrs.get("SA_URBAN_AREA_NAME") or ""),
    )


def choose_epoch(
    prior: CensusEraPrior | None,
    analysis: StreetViewAnalysis | None,
) -> tuple[ConstructionEpoch | None, str]:
    """Combine the census prior with Claude's Street View era.

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
    visual = (
        analysis.construction_epoch
        if analysis is not None and analysis.confidence >= STREETVIEW_MIN_CONFIDENCE
        else None
    )
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
