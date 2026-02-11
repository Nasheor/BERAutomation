"""BER rating scale: map kWh/m²/year to band A1–G."""

from __future__ import annotations

from ber_automation.ber_engine.constants import BER_BANDS


def get_ber_band(kwh_per_m2: float) -> tuple[str, str]:
    """Return (band_name, hex_color) for the given energy value.

    Args:
        kwh_per_m2: Total primary energy in kWh/m²/year.

    Returns:
        Tuple of (band label e.g. "B2", hex color e.g. "#FFF200").
    """
    for band, threshold, color in BER_BANDS:
        if kwh_per_m2 <= threshold:
            return band, color
    # Should not reach here, but fallback to G
    return "G", "#4A1525"
