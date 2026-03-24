"""BER rating scale: map kWh/m²/year to band A1–G, plus native EPC scales."""

from __future__ import annotations

from ber_automation.ber_engine.constants import BER_BANDS, EPC_SCALE_NAME, NATIVE_EPC_BANDS
from ber_automation.models import Country


def get_ber_band(kwh_per_m2: float) -> tuple[str, str]:
    """Return (band_name, hex_color) for the given primary energy value on the Irish BER scale.

    Args:
        kwh_per_m2: Total primary energy in kWh/m²/year.

    Returns:
        Tuple of (band label e.g. "B2", hex color e.g. "#FFF200").
    """
    for band, threshold, color in BER_BANDS:
        if kwh_per_m2 <= threshold:
            return band, color
    return "G", "#4A1525"


def get_native_epc(kwh_per_m2: float, country: Country) -> tuple[str, str, str]:
    """Return the native EPC rating for a given country.

    Args:
        kwh_per_m2: Total primary energy in kWh/m²/year.
        country: The country whose EPC scale to use.

    Returns:
        Tuple of (band_label, hex_color, scale_name)
        e.g. ("C", "#CBDA4B", "DPE") for France.
    """
    bands = NATIVE_EPC_BANDS.get(country, BER_BANDS)
    scale = EPC_SCALE_NAME.get(country, "BER")
    for band, threshold, color in bands:
        if kwh_per_m2 <= threshold:
            return band, color, scale
    # Fallback to worst band
    last_band, _, last_color = bands[-1]
    return last_band, last_color, scale
