"""Unit tests for initial_bearing() geodesic bearing function."""

from __future__ import annotations

import pytest

from ber_automation.geospatial.scale import initial_bearing


class TestInitialBearing:
    """Verify bearing calculations against known directions."""

    def test_due_north(self):
        """Point directly north should give bearing ~0."""
        bearing = initial_bearing(53.0, -6.0, 54.0, -6.0)
        assert bearing == pytest.approx(0.0, abs=0.5)

    def test_due_east(self):
        """Point directly east should give bearing ~90."""
        bearing = initial_bearing(53.0, -6.0, 53.0, -5.0)
        assert bearing == pytest.approx(90.0, abs=0.5)

    def test_due_south(self):
        """Point directly south should give bearing ~180."""
        bearing = initial_bearing(54.0, -6.0, 53.0, -6.0)
        assert bearing == pytest.approx(180.0, abs=0.5)

    def test_due_west(self):
        """Point directly west should give bearing ~270."""
        bearing = initial_bearing(53.0, -5.0, 53.0, -6.0)
        assert bearing == pytest.approx(270.0, abs=0.5)

    def test_same_point_returns_zero(self):
        """Bearing from a point to itself should be 0."""
        bearing = initial_bearing(53.35, -6.26, 53.35, -6.26)
        assert bearing == 0.0

    def test_short_distance_streetview_scenario(self):
        """Typical Street View distance (~20m offset) should still produce a sensible bearing."""
        # Camera slightly south-west of target building
        cam_lat, cam_lng = 53.34980, -6.26020
        bld_lat, bld_lng = 53.35000, -6.26000
        bearing = initial_bearing(cam_lat, cam_lng, bld_lat, bld_lng)
        # Should be roughly north-east (somewhere in 0-90 range)
        assert 0 < bearing < 90

    def test_known_long_distance(self):
        """Dublin to London — well-known bearing (~115 degrees)."""
        # Dublin (53.35, -6.26) -> London (51.51, -0.13)
        bearing = initial_bearing(53.35, -6.26, 51.51, -0.13)
        assert bearing == pytest.approx(115.0, abs=3.0)

    def test_result_in_valid_range(self):
        """Bearing should always be in [0, 360)."""
        test_cases = [
            (0.0, 0.0, 1.0, 1.0),
            (0.0, 0.0, -1.0, -1.0),
            (89.0, 179.0, -89.0, -179.0),
            (53.0, -6.0, 53.0, -6.0),
        ]
        for lat1, lng1, lat2, lng2 in test_cases:
            bearing = initial_bearing(lat1, lng1, lat2, lng2)
            assert 0 <= bearing < 360, f"Bearing {bearing} out of range for ({lat1},{lng1})->({lat2},{lng2})"
