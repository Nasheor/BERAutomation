"""Convert Google Maps zoom level to meters-per-pixel for measurement."""

from __future__ import annotations

import math

# Earth's circumference at the equator in meters
EARTH_CIRCUMFERENCE = 40_075_016.686

# Google Maps tile size in pixels
TILE_SIZE = 256


def meters_per_pixel(lat: float, zoom: int) -> float:
    """Calculate the ground resolution (meters per pixel) at a given latitude and zoom.

    Uses the standard Web Mercator formula:
        resolution = C × cos(lat) / 2^(zoom+8)

    where C is Earth's circumference and the +8 accounts for 256-pixel tiles.

    Args:
        lat: Latitude in degrees.
        zoom: Google Maps zoom level (0–21).

    Returns:
        Meters per pixel at the given location and zoom.
    """
    lat_rad = math.radians(lat)
    return EARTH_CIRCUMFERENCE * math.cos(lat_rad) / (2 ** (zoom + 8))


def pixels_to_meters(pixels: float, lat: float, zoom: int) -> float:
    """Convert a pixel distance to meters."""
    return pixels * meters_per_pixel(lat, zoom)


def meters_to_pixels(meters: float, lat: float, zoom: int) -> float:
    """Convert a distance in meters to pixels."""
    mpp = meters_per_pixel(lat, zoom)
    if mpp == 0:
        return 0.0
    return meters / mpp
