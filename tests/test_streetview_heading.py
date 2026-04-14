"""Mocked integration tests for Street View auto-heading logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ber_automation.geospatial.imagery import fetch_streetview_image
from ber_automation.models import Coordinates


def _make_response(json_data: dict | None = None, content: bytes = b"img") -> httpx.Response:
    """Build a fake httpx.Response."""
    request = httpx.Request("GET", "https://fake.test/")
    if json_data is not None:
        resp = httpx.Response(200, json=json_data, request=request)
    else:
        resp = httpx.Response(200, content=content, request=request)
    return resp


def _meta_ok(cam_lat: float = 53.3490, cam_lng: float = -6.2610) -> dict:
    """Metadata response with status OK and a camera location."""
    return {
        "status": "OK",
        "location": {"lat": cam_lat, "lng": cam_lng},
    }


_META_NO_LOCATION = {"status": "OK"}
_META_NOT_FOUND = {"status": "ZERO_RESULTS"}

_COORDS = Coordinates(lat=53.3500, lng=-6.2600)


@pytest.fixture(autouse=True)
def _mock_settings():
    """Provide dummy settings so we never need a real API key."""
    fake = type("S", (), {
        "google_maps_api_key": "FAKE_KEY",
        "streetview_fov": 90,
        "streetview_pitch": 10,
        "streetview_size": "640x640",
    })()
    with patch("ber_automation.geospatial.imagery.get_settings", return_value=fake):
        yield


class TestAutoHeading:
    """When heading=None the bearing should be computed from metadata."""

    @pytest.mark.asyncio
    async def test_auto_heading_from_metadata(self, tmp_path: Path):
        """Heading is computed from camera position to target coords."""
        meta_resp = _make_response(json_data=_meta_ok())
        img_resp = _make_response(content=b"\x89PNG")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[meta_resp, img_resp])
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("ber_automation.geospatial.imagery.httpx.AsyncClient", return_value=client):
            out = tmp_path / "sv.jpg"
            result = await fetch_streetview_image(_COORDS, out)

        assert result is not None
        # The image-fetch call is the second .get() call
        img_call_kwargs = client.get.call_args_list[1]
        heading_used = img_call_kwargs.kwargs.get("params", img_call_kwargs.args[1] if len(img_call_kwargs.args) > 1 else {}).get("heading", None)
        # Fallback: just check the params dict passed to get()
        if heading_used is None:
            # params passed as keyword arg
            for call_args in client.get.call_args_list[1:]:
                params = call_args.kwargs.get("params", {})
                if "heading" in params:
                    heading_used = params["heading"]
                    break
        assert heading_used is not None
        # Camera is south-west of building, so bearing should be ~NE (roughly 20-60 degrees)
        assert 0 < heading_used < 90

    @pytest.mark.asyncio
    async def test_explicit_heading_skips_auto(self, tmp_path: Path):
        """When an explicit heading is provided, use it as-is."""
        meta_resp = _make_response(json_data=_meta_ok())
        img_resp = _make_response(content=b"\x89PNG")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[meta_resp, img_resp])
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("ber_automation.geospatial.imagery.httpx.AsyncClient", return_value=client):
            out = tmp_path / "sv.jpg"
            result = await fetch_streetview_image(_COORDS, out, heading=222.0)

        assert result is not None
        params = client.get.call_args_list[1].kwargs.get("params", {})
        assert params["heading"] == 222.0

    @pytest.mark.asyncio
    async def test_missing_location_falls_back_to_zero(self, tmp_path: Path):
        """If metadata lacks a location, heading defaults to 0."""
        meta_resp = _make_response(json_data=_META_NO_LOCATION)
        img_resp = _make_response(content=b"\x89PNG")

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=[meta_resp, img_resp])
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("ber_automation.geospatial.imagery.httpx.AsyncClient", return_value=client):
            out = tmp_path / "sv.jpg"
            result = await fetch_streetview_image(_COORDS, out)

        assert result is not None
        params = client.get.call_args_list[1].kwargs.get("params", {})
        assert params["heading"] == 0

    @pytest.mark.asyncio
    async def test_no_streetview_returns_none(self, tmp_path: Path):
        """If metadata says no coverage, return None without fetching image."""
        meta_resp = _make_response(json_data=_META_NOT_FOUND)

        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(return_value=meta_resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch("ber_automation.geospatial.imagery.httpx.AsyncClient", return_value=client):
            out = tmp_path / "sv.jpg"
            result = await fetch_streetview_image(_COORDS, out)

        assert result is None
        # Only one call (metadata), no image fetch
        assert client.get.call_count == 1
