"""Fetch satellite and Street View imagery from Google Maps APIs."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from ber_automation.config import get_settings
from ber_automation.geospatial.scale import initial_bearing
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
    """Download a satellite image centred on *coords* via Mapbox Static Images API.

    Args:
        coords: GPS coordinates.
        output_path: File path to save the image.
        zoom: Map zoom level (default from settings, typically 20).
        size: Image size as "WxH" (default from settings, typically "640x640").

    Returns:
        Path to the saved image file.
    """
    settings = get_settings()
    if not settings.mapbox_access_token:
        raise ValueError("MAPBOX_ACCESS_TOKEN not configured")

    zoom_level = zoom or settings.satellite_zoom
    size_str = size or settings.satellite_size
    width, height = (int(v) for v in size_str.split("x"))

    url = (
        f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
        f"{coords.lng},{coords.lat},{zoom_level},0/{width}x{height}"
        f"?access_token={settings.mapbox_access_token}"
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)

    return output_path


async def fetch_streetview_image(
    coords: Coordinates,
    output_path: str | Path,
    heading: float | None = None,
    fov: int | None = None,
    pitch: int | None = None,
    size: str | None = None,
) -> Path | None:
    """Download a Street View image near *coords*.

    Args:
        coords: GPS coordinates.
        output_path: File path to save the image.
        heading: Camera heading in degrees (0-360). When *None* (default) the
            heading is auto-computed from the camera position to *coords*.
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

    # Auto-compute heading from camera position to target building
    if heading is None:
        cam = meta.get("location")
        if cam and "lat" in cam and "lng" in cam:
            heading = initial_bearing(cam["lat"], cam["lng"], coords.lat, coords.lng)
        else:
            heading = 0

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


async def fetch_streetview_images(
    coords: Coordinates,
    output_dir: str | Path,
    fov: int | None = None,
    pitch: int | None = None,
    size: str | None = None,
) -> list[Path]:
    """Download Street View images at 4 headings (every 90 degrees) around *coords*.

    The base heading is auto-computed from camera position → building, then
    images are fetched at base+0, base+90, base+180, base+270.

    Args:
        coords: GPS coordinates of the building.
        output_dir: Directory to save images (streetview_0.jpg … streetview_3.jpg).
        fov: Field of view (default from settings).
        pitch: Camera pitch (default from settings).
        size: Image size as "WxH".

    Returns:
        List of Paths to saved images (may be fewer than 4 if Street View
        is unavailable).
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY not configured")

    location = f"{coords.lat},{coords.lng}"

    # Check availability and get camera position
    meta_params = {
        "location": location,
        "key": settings.google_maps_api_key,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        meta_resp = await client.get(STREETVIEW_META_URL, params=meta_params)
        meta_resp.raise_for_status()
        meta = meta_resp.json()

    if meta.get("status") != "OK":
        return []

    # Compute base heading from camera → building
    cam = meta.get("location")
    if cam and "lat" in cam and "lng" in cam:
        base_heading = initial_bearing(cam["lat"], cam["lng"], coords.lat, coords.lng)
    else:
        base_heading = 0.0

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    headings = [(base_heading + offset) % 360 for offset in (0, 90, 180, 270)]

    async def _fetch_one(heading: float, index: int) -> Path:
        params = {
            "location": location,
            "heading": heading,
            "fov": fov or settings.streetview_fov,
            "pitch": pitch or settings.streetview_pitch,
            "size": size or settings.streetview_size,
            "key": settings.google_maps_api_key,
        }
        out = output_dir / f"streetview_{index}.jpg"
        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.get(STREETVIEW_URL, params=params)
            resp.raise_for_status()
            out.write_bytes(resp.content)
        return out

    tasks = [_fetch_one(h, i) for i, h in enumerate(headings)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    paths: list[Path] = []
    for r in results:
        if isinstance(r, Path):
            paths.append(r)
    return paths
