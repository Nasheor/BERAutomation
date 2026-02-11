"""Eircode geocoding via Google Geocoding API."""

from __future__ import annotations

import re

import httpx

from ber_automation.config import get_settings
from ber_automation.models import Coordinates


# Irish Eircode: 3 chars (routing key) + space? + 4 chars (unique identifier)
_EIRCODE_RE = re.compile(r"^[A-Z]\d{2}\s?[A-Z0-9]{4}$", re.IGNORECASE)

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def validate_eircode(eircode: str) -> str:
    """Validate and normalise an Eircode (remove spaces, uppercase).

    Raises ValueError if the format is invalid.
    """
    cleaned = eircode.strip().upper().replace(" ", "")
    # Re-format with space: ABC 1234
    formatted = f"{cleaned[:3]} {cleaned[3:]}"
    if not _EIRCODE_RE.match(formatted):
        raise ValueError(f"Invalid Eircode format: {eircode!r}")
    return formatted


async def geocode_eircode(eircode: str) -> Coordinates:
    """Geocode an Eircode to GPS coordinates using Google Geocoding API.

    Args:
        eircode: Irish Eircode (e.g. "D02 X285").

    Returns:
        Coordinates with lat, lng, and formatted address.

    Raises:
        ValueError: If the Eircode format is invalid or not found.
        httpx.HTTPError: On network errors.
    """
    eircode = validate_eircode(eircode)
    settings = get_settings()

    if not settings.google_maps_api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY not configured")

    params = {
        "address": eircode,
        "components": "country:IE",
        "key": settings.google_maps_api_key,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(GEOCODING_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data["status"] != "OK" or not data.get("results"):
        raise ValueError(f"Geocoding failed for {eircode}: {data.get('status')}")

    result = data["results"][0]
    loc = result["geometry"]["location"]
    return Coordinates(
        lat=loc["lat"],
        lng=loc["lng"],
        formatted_address=result.get("formatted_address", ""),
    )
