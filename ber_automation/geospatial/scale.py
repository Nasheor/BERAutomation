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


def initial_bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute the initial (forward) geodesic bearing from point 1 to point 2.

    Uses the spherical law formula. Returns a bearing in degrees [0, 360).

    Args:
        lat1: Latitude of the origin point (degrees).
        lng1: Longitude of the origin point (degrees).
        lat2: Latitude of the destination point (degrees).
        lng2: Longitude of the destination point (degrees).

    Returns:
        Bearing in degrees, 0 = North, 90 = East, etc.
    """
    φ1 = math.radians(lat1)
    φ2 = math.radians(lat2)
    Δλ = math.radians(lng2 - lng1)

    x = math.sin(Δλ) * math.cos(φ2)
    y = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(Δλ)

    θ = math.degrees(math.atan2(x, y))
    return θ % 360
