"""Fetch satellite and Street View imagery from Google Maps APIs."""

from __future__ import annotations

from pathlib import Path

import httpx

from ber_automation.config import get_settings
from ber_automation.models import Coordinates

STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"
STREETVIEW_URL = "https://maps.googleapis.com/maps/api/streetview"
STREETVIEW_META_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"


async def fetch_satellite_image(
    coords: Coordinates,
    output_path: str | Path,
    zoom: int | None = None,
    size: str | None = None,
) -> Path:
    """Download a satellite image centred on *coords*.

    Args:
        coords: GPS coordinates.
        output_path: File path to save the image.
        zoom: Map zoom level (default from settings, typically 20).
        size: Image size as "WxH" (default from settings, typically "640x640").

    Returns:
        Path to the saved image file.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY not configured")

    params = {
        "center": f"{coords.lat},{coords.lng}",
        "zoom": zoom or settings.satellite_zoom,
        "size": size or settings.satellite_size,
        "maptype": "satellite",
        "key": settings.google_maps_api_key,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(STATIC_MAP_URL, params=params)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)

    return output_path


async def fetch_streetview_image(
    coords: Coordinates,
    output_path: str | Path,
    heading: int = 0,
    fov: int | None = None,
    pitch: int | None = None,
    size: str | None = None,
) -> Path | None:
    """Download a Street View image near *coords*.

    Args:
        coords: GPS coordinates.
        output_path: File path to save the image.
        heading: Camera heading (0-360 degrees).
        fov: Field of view (default from settings).
        pitch: Camera pitch (default from settings).
        size: Image size as "WxH".

    Returns:
        Path to the saved image, or None if no Street View is available.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY not configured")

    location = f"{coords.lat},{coords.lng}"

    # Check availability first
    meta_params = {
        "location": location,
        "key": settings.google_maps_api_key,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        meta_resp = await client.get(STREETVIEW_META_URL, params=meta_params)
        meta_resp.raise_for_status()
        meta = meta_resp.json()

    if meta.get("status") != "OK":
        return None

    params = {
        "location": location,
        "heading": heading,
        "fov": fov or settings.streetview_fov,
        "pitch": pitch or settings.streetview_pitch,
        "size": size or settings.streetview_size,
        "key": settings.google_maps_api_key,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(STREETVIEW_URL, params=params)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)

    return output_path
