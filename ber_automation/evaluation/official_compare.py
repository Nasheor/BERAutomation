"""Compare pipeline estimates with official BER certificates (the paper's three levels).

(a) inputs:      what the pipeline read from the images (type, era, floor area, and storeys
                 and heating when recorded) against the certificate.
(b) certificate: the calculator on the pipeline's inputs with the values the certificate
                 gives put in (type, era, floor area; storeys and heating when recorded).
                 The register shows no storeys, heating or U-values, so this is not the
                 calculator on the full certificate inputs: what is left is calculator error
                 plus the inputs the certificate does not give.
(c) pipeline:    the pipeline's band and kWh/m²/yr against the official BER.

Plus a baseline that ignores the house: the commonest band among the other homes.
No API calls here; scripts/validate_official.py runs the pipeline.
"""

from __future__ import annotations

import math
from collections import Counter
from statistics import mean, median

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.evaluation.official_sample import BANDS, OfficialHome
from ber_automation.models import BuildingInput, BuildingType

_BAND_INDEX = {band: i for i, band in enumerate(BANDS)}

DWELLING_OF_TYPE: dict[BuildingType, str] = {
    BuildingType.DETACHED: "detached",
    BuildingType.SEMI_D_LENGTH: "semi_detached",
    BuildingType.SEMI_D_WIDTH: "semi_detached",
    BuildingType.TERRACED_LENGTH: "terraced",
    BuildingType.TERRACED_WIDTH: "terraced",
}
# Which side is shared is not on the certificate; used only when the pipeline's type is of
# another kind (otherwise the pipeline's side is kept)
_TYPE_OF_DWELLING: dict[str, BuildingType] = {
    "detached": BuildingType.DETACHED,
    "semi_detached": BuildingType.SEMI_D_LENGTH,
    "terraced": BuildingType.TERRACED_LENGTH,
}


def band_distance(a: str, b: str) -> int:
    """Number of bands between two BER bands (A1 to A2 is 1, A3 to B1 is 1)."""
    return abs(_BAND_INDEX[a] - _BAND_INDEX[b])


def pct_error(ours: float, ref: float) -> float:
    """Signed error of *ours* against *ref*, in percent."""
    return (ours - ref) / ref * 100.0 if ref else math.nan


def score(home: OfficialHome, band: str, kwh_m2_yr: float) -> dict:
    """An estimate (band, primary kWh/m²/yr) against the home's certificate."""
    return {
        "band": band,
        "kwh_m2_yr": round(kwh_m2_yr, 1),
        "band_exact": band == home.ber_band,
        "band_within_one": band_distance(band, home.ber_band) <= 1,
        "band_offset": _BAND_INDEX[band] - _BAND_INDEX[home.ber_band],  # + = rated worse
        "kwh_error_pct": round(pct_error(kwh_m2_yr, home.ber_kwh_m2_yr), 1),
    }


def compare_inputs(home: OfficialHome, b: BuildingInput) -> dict:
    """Level (a): the pipeline's inputs against what the certificate (or listing) records.

    Each entry is {"ours", "certificate", "match"} (floor area: "error_pct" instead of
    "match"); a value the certificate does not record is left out. Floor area is the
    calculator's gross area (length × width × storeys); the certificate's is DEAP's total
    floor area.
    """
    out: dict[str, dict] = {}
    if home.dwelling_type:
        ours = DWELLING_OF_TYPE[b.building_type]
        out["dwelling_type"] = {"ours": ours, "certificate": home.dwelling_type,
                                "match": ours == home.dwelling_type}
    if home.epoch:
        out["era"] = {"ours": b.construction_epoch.value, "certificate": home.epoch.value,
                      "match": b.construction_epoch == home.epoch}
    if home.floor_area_m2:
        ours = b.length * b.width * b.heated_storeys
        out["floor_area_m2"] = {"ours": round(ours, 1), "certificate": home.floor_area_m2,
                                "error_pct": round(pct_error(ours, home.floor_area_m2), 1)}
    if home.storeys:
        out["storeys"] = {"ours": b.heated_storeys, "certificate": home.storeys,
                          "match": b.heated_storeys == home.storeys}
    if home.heating:
        out["heating"] = {"ours": b.heating_system.value, "certificate": home.heating.value,
                          "match": b.heating_system == home.heating}
    return out


def with_certificate_values(home: OfficialHome, b: BuildingInput) -> BuildingInput:
    """Level (b): the pipeline's inputs with the certificate's values put in.

    Storeys and heating are replaced when recorded. The floor area is matched by scaling
    length and width by the same factor (the plan shape and storeys are kept). For the
    dwelling type only the kind is taken from the certificate; the shared side stays the
    pipeline's when the kind agrees, else the length side.
    """
    update: dict = {}
    if home.storeys:
        update["heated_storeys"] = home.storeys
    if home.heating:
        update["heating_system"] = home.heating
    if home.epoch:
        update["construction_epoch"] = home.epoch
    if home.dwelling_type and DWELLING_OF_TYPE[b.building_type] != home.dwelling_type:
        update["building_type"] = _TYPE_OF_DWELLING[home.dwelling_type]
    if home.floor_area_m2:
        storeys = update.get("heated_storeys", b.heated_storeys)
        factor = math.sqrt(home.floor_area_m2 / (b.length * b.width * storeys))
        update["length"] = b.length * factor
        update["width"] = b.width * factor
    return b.model_copy(update=update)


def certificate_level(home: OfficialHome, b: BuildingInput) -> dict:
    """Level (b) scored against the certificate, with the inputs used."""
    corrected = with_certificate_values(home, b)
    ber = HWBCalculator().calculate_ber(corrected)
    return {
        **score(home, ber.ber_band, ber.kwh_per_m2),
        "inputs": {
            "building_type": corrected.building_type.value,
            "length": round(corrected.length, 1),
            "width": round(corrected.width, 1),
            "storeys": corrected.heated_storeys,
            "epoch": corrected.construction_epoch.value,
            "heating": corrected.heating_system.value,
        },
    }


def commonest_band_baseline(homes: list[OfficialHome]) -> list[dict]:
    """For each home, the commonest band among the other homes (leave-one-out), scored.

    Ties go to the band nearest the middle of the scale (C1), then the better band.
    The kWh value used is the median of those other homes in that band.
    """
    middle = _BAND_INDEX["C1"]
    out: list[dict] = []
    for i, home in enumerate(homes):
        others = homes[:i] + homes[i + 1:]
        if not others:
            out.append({})
            continue
        counts = Counter(h.ber_band for h in others)
        band = min(counts, key=lambda b: (-counts[b], abs(_BAND_INDEX[b] - middle),
                                          _BAND_INDEX[b]))
        kwh = median(h.ber_kwh_m2_yr for h in others if h.ber_band == band)
        out.append(score(home, band, kwh))
    return out


def summarise_scores(scores: list[dict]) -> dict:
    """Counts and mean errors over a list of score() results (empty ones are skipped)."""
    done = [s for s in scores if s]
    if not done:
        return {"n": 0}
    errors = [s["kwh_error_pct"] for s in done]
    return {
        "n": len(done),
        "band_exact": sum(s["band_exact"] for s in done),
        "band_within_one": sum(s["band_within_one"] for s in done),
        "mean_band_offset": round(mean(s["band_offset"] for s in done), 2),
        "mean_abs_kwh_error_pct": round(mean(abs(e) for e in errors), 1),
        "median_kwh_error_pct": round(median(errors), 1),
    }


def summarise_inputs(comparisons: list[dict]) -> dict:
    """Level (a) over many homes: matches per recorded value, mean |floor area error|."""
    out: dict[str, dict] = {}
    for key in ("dwelling_type", "era", "storeys", "heating"):
        items = [c[key] for c in comparisons if key in c]
        if items:
            out[key] = {"n": len(items), "match": sum(i["match"] for i in items)}
    areas = [c["floor_area_m2"]["error_pct"] for c in comparisons if "floor_area_m2" in c]
    if areas:
        out["floor_area_m2"] = {"n": len(areas),
                                "mean_abs_error_pct": round(mean(abs(a) for a in areas), 1),
                                "median_error_pct": round(median(areas), 1)}
    return out


def run_agreement(bands: list[str]) -> float | None:
    """Share of runs giving the commonest band (1.0 = every run the same); None if < 2 runs."""
    if len(bands) < 2:
        return None
    return Counter(bands).most_common(1)[0][1] / len(bands)
