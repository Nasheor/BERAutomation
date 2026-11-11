"""Tests for fetch_streetview_images(): panorama pinning, duplicate removal, stale files."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from ber_automation.geospatial import imagery
from ber_automation.models import Coordinates

COORDS = Coordinates(lat=51.9, lng=-8.47)


def _jpeg(seed: int) -> bytes:
    """A distinct test picture per seed (different stripe positions)."""
    img = Image.new("RGB", (640, 640), (40, 40, 40))
    draw = ImageDraw.Draw(img)
    for i in range(6):
        x = (seed * 97 + i * 110) % 640
        draw.rectangle([x, 0, x + 50, 640], fill=(220, 220, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class _FakeClient:
    """Stands in for httpx.AsyncClient; records every request."""

    def __init__(self, meta_by_source: dict, image_for_heading):
        self.meta_by_source = meta_by_source
        self.image_for_heading = image_for_heading
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, *args, **kwargs):  # used as the AsyncClient constructor
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if url == imagery.STREETVIEW_META_URL:
            resp.json.return_value = self.meta_by_source.get(params.get("source"), {"status": "ZERO_RESULTS"})
        else:
            resp.content = self.image_for_heading(params["heading"])
        return resp


def _settings():
    s = MagicMock()
    s.google_maps_api_key = "test-key"
    s.streetview_fov = 90
    s.streetview_pitch = 10
    s.streetview_size = "640x640"
    return s


OK_META = {"status": "OK", "pano_id": "PANO123", "location": {"lat": 51.8999, "lng": -8.4701}}


@pytest.mark.asyncio
async def test_all_views_pinned_to_outdoor_panorama(tmp_path):
    fake = _FakeClient({"outdoor": OK_META}, lambda h: _jpeg(int(h) // 90))
    with patch.object(imagery, "get_settings", return_value=_settings()), \
         patch.object(imagery.httpx, "AsyncClient", fake):
        paths = await imagery.fetch_streetview_images(COORDS, tmp_path)

    assert len(paths) == 4
    meta_calls = [p for u, p in fake.calls if u == imagery.STREETVIEW_META_URL]
    assert meta_calls[0]["source"] == "outdoor"
    image_calls = [p for u, p in fake.calls if u == imagery.STREETVIEW_URL]
    assert all(p["pano"] == "PANO123" and "location" not in p for p in image_calls)


@pytest.mark.asyncio
async def test_falls_back_to_any_panorama_when_no_outdoor(tmp_path):
    fake = _FakeClient({None: OK_META}, lambda h: _jpeg(int(h) // 90))
    with patch.object(imagery, "get_settings", return_value=_settings()), \
         patch.object(imagery.httpx, "AsyncClient", fake):
        paths = await imagery.fetch_streetview_images(COORDS, tmp_path)

    assert len(paths) == 4
    meta_calls = [p for u, p in fake.calls if u == imagery.STREETVIEW_META_URL]
    assert [c.get("source") for c in meta_calls] == ["outdoor", None]


@pytest.mark.asyncio
async def test_duplicate_views_are_dropped(tmp_path):
    """Headings that return the same picture (partial panorama) keep only the first copy."""
    # Front == Right, Rear == Left — the pattern seen in the app screenshot
    first = _jpeg(1)
    second = _jpeg(5)
    base = None

    def image_for_heading(h):
        nonlocal base
        if base is None:
            base = h
        offset = round((h - base) % 360)
        return first if offset in (0, 90) else second

    fake = _FakeClient({"outdoor": OK_META}, image_for_heading)
    with patch.object(imagery, "get_settings", return_value=_settings()), \
         patch.object(imagery.httpx, "AsyncClient", fake):
        paths = await imagery.fetch_streetview_images(COORDS, tmp_path)

    assert [p.name for p in paths] == ["streetview_0.jpg", "streetview_2.jpg"]
    assert not (tmp_path / "streetview_1.jpg").exists()
    assert not (tmp_path / "streetview_3.jpg").exists()


@pytest.mark.asyncio
async def test_previous_property_files_are_cleared(tmp_path):
    (tmp_path / "streetview_3.jpg").write_bytes(b"old")
    (tmp_path / "streetview_3_annotated.jpg").write_bytes(b"old overlay")
    fake = _FakeClient({}, lambda h: _jpeg(0))  # no panorama at all
    with patch.object(imagery, "get_settings", return_value=_settings()), \
         patch.object(imagery.httpx, "AsyncClient", fake):
        paths = await imagery.fetch_streetview_images(COORDS, tmp_path)

    assert paths == []
    assert list(tmp_path.glob("streetview_*")) == []
