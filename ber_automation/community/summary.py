"""Community summaries: ranking, band mix, totals, and census-versus-image agreement."""

from __future__ import annotations

from ber_automation.ber_engine.constants import BER_BANDS
from ber_automation.community.models import IMAGES, CommunityResult, SmallAreaStock

BAND_NAMES = [b for b, _, _ in BER_BANDS]


def band_offset(estimate: str, reference: str) -> int:
    """Bands from *reference* to *estimate*; negative = estimate rates the home better."""
    return BAND_NAMES.index(estimate) - BAND_NAMES.index(reference)


def ranking(result: CommunityResult) -> list[dict]:
    """One row per rated home, worst primary energy first (retrofit priority)."""
    rows = []
    for h in result.homes:
        ber = h.best
        if ber is None:
            continue
        b, hw = ber.building_input, ber.hwb_result
        rows.append({
            "id": h.id,
            "address": h.address,
            "band": ber.ber_band,
            "kwh_m2": round(ber.kwh_per_m2, 1),
            "source": h.source,
            "floor_m2": round(hw.floor_area, 1),
            "era": b.construction_epoch.value,
            "type": b.building_type.value,
            "heating": b.heating_system.value,
            "primary_mwh": round(ber.kwh_per_m2 * hw.floor_area / 1000, 2),
            "co2_t": round(hw.co2_kg / 1000, 2),
            "small_area": h.small_area,
            "lat": h.coordinates.lat if h.coordinates else None,
            "lng": h.coordinates.lng if h.coordinates else None,
        })
    rows.sort(key=lambda r: -r["kwh_m2"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def band_counts(result: CommunityResult) -> dict[str, int]:
    counts = {b: 0 for b in BAND_NAMES}
    for h in result.homes:
        if h.best is not None:
            counts[h.best.ber_band] += 1
    return {b: n for b, n in counts.items() if n}


def totals(result: CommunityResult) -> dict:
    """Totals over the listed homes, using each home's best estimate."""
    rated = [h for h in result.homes if h.best is not None]
    floor = sum(h.best.hwb_result.floor_area for h in rated)
    primary = sum(h.best.kwh_per_m2 * h.best.hwb_result.floor_area for h in rated)
    return {
        "homes": len(result.homes),
        "rated": len(rated),
        "from_images": sum(1 for h in rated if h.source == IMAGES),
        "not_located": sum(1 for h in result.homes if h.coordinates is None),
        "floor_area_m2": round(floor, 1),
        "heat_demand_mwh": round(sum(h.best.hwb_result.heating_demand_kwh for h in rated) / 1000, 2),
        "delivered_mwh": round(sum(h.best.hwb_result.total_kwh_per_m2 * h.best.hwb_result.floor_area
                                   for h in rated) / 1000, 2),
        "primary_mwh": round(primary / 1000, 2),
        "co2_t": round(sum(h.best.hwb_result.co2_kg for h in rated) / 1000, 2),
        "mean_primary_kwh_m2": round(primary / floor, 1) if floor > 0 else 0.0,
    }


def area_totals(result: CommunityResult) -> dict:
    """Totals over all homes in the Small Areas the listed homes are in (census stock model)."""
    areas: list[SmallAreaStock] = list(result.areas.values())
    floor = sum(a.floor_area_m2 for a in areas)
    primary = sum(a.primary_mwh for a in areas)
    return {
        "small_areas": len(areas),
        "households": sum(a.households for a in areas),
        "floor_area_m2": round(floor, 1),
        "heat_demand_mwh": round(sum(a.heat_demand_mwh for a in areas), 1),
        "delivered_mwh": round(sum(a.delivered_mwh for a in areas), 1),
        "primary_mwh": round(primary, 1),
        "co2_t": round(sum(a.co2_t for a in areas), 1),
        "mean_primary_kwh_m2": round(primary * 1000 / floor, 1) if floor > 0 else 0.0,
    }


def agreement(result: CommunityResult) -> dict:
    """How the census estimate compares with the image estimate, where a home has both."""
    rows = []
    for h in result.homes:
        if h.census_estimate is None or h.image_estimate is None:
            continue
        c, i = h.census_estimate, h.image_estimate
        rows.append({
            "id": h.id,
            "census_band": c.ber_band,
            "image_band": i.ber_band,
            "band_offset": band_offset(c.ber_band, i.ber_band),
            "kwh_diff_pct": round((c.kwh_per_m2 - i.kwh_per_m2) / i.kwh_per_m2 * 100, 1)
            if i.kwh_per_m2 else None,
        })
    n = len(rows)
    return {
        "n": n,
        "exact": sum(1 for r in rows if r["band_offset"] == 0),
        "within_one": sum(1 for r in rows if abs(r["band_offset"]) <= 1),
        "rows": rows,
    }
