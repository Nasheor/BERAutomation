"""Address geocoding via Google Geocoding API.

Supports all Interreg NWE (CIRCUS) programme countries and Ireland.
"""

from __future__ import annotations

import re

import httpx

from ber_automation.config import get_settings
from ber_automation.models import Coordinates, Country


# Irish Eircode: 3 chars (routing key) + space? + 4 chars (unique identifier)
_EIRCODE_RE = re.compile(r"^[A-Z]\d{2}\s?[A-Z0-9]{4}$", re.IGNORECASE)

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# ISO 3166-1 alpha-2 codes for each supported country
COUNTRY_ISO: dict[Country, str] = {
    Country.IRELAND: "IE",
    Country.FRANCE: "FR",
    Country.GERMANY: "DE",
    Country.BELGIUM: "BE",
    Country.NETHERLANDS: "NL",
    Country.LUXEMBOURG: "LU",
    Country.SWITZERLAND: "CH",
    Country.AUSTRIA: "AT",
}


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


async def geocode_address(
    address: str,
    country: Country | None = None,
) -> Coordinates:
    """Geocode any address string to GPS coordinates via Google Geocoding API.

    Args:
        address: Free-text address or postal code (e.g. "D02 X285",
                 "1 Rue de la Paix, Paris", "4001 Basel").
        country: Optional country to restrict results. When *None* the API
                 searches globally; when provided it filters by ISO country code.

    Returns:
        Coordinates with lat, lng, and formatted address.

    Raises:
        ValueError: If the address is not found.
        httpx.HTTPError: On network errors.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY not configured")

    params: dict = {
        "address": address,
        "key": settings.google_maps_api_key,
    }
    if country is not None:
        iso = COUNTRY_ISO.get(country)
        if iso:
            params["components"] = f"country:{iso}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(GEOCODING_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data["status"] != "OK" or not data.get("results"):
        raise ValueError(f"Geocoding failed for {address!r}: {data.get('status')}")

    result = data["results"][0]
    loc = result["geometry"]["location"]
    return Coordinates(
        lat=loc["lat"],
        lng=loc["lng"],
        formatted_address=result.get("formatted_address", ""),
    )


async def geocode_eircode(eircode: str) -> Coordinates:
    """Geocode an Irish Eircode. Thin wrapper around geocode_address."""
    eircode = validate_eircode(eircode)
    return await geocode_address(eircode, country=Country.IRELAND)
