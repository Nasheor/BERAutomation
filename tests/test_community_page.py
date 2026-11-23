"""Tests for the Community page's chart builders (no Streamlit session)."""

from __future__ import annotations

import csv
import io
import math

from app.community_page import fit_zoom, make_band_chart, make_map, ranking_csv

ROWS = [
    {"rank": 1, "id": "1", "address": "Killarney", "band": "C2", "kwh_m2": 185.0, "source": "census",
     "lat": 52.06, "lng": -9.51},
    {"rank": 2, "id": "2", "address": "Malahide", "band": "B1", "kwh_m2": 93.0, "source": "images",
     "lat": 53.45, "lng": -6.15},
    {"rank": 3, "id": "3", "address": "Not found", "band": "A3", "kwh_m2": 60.0, "source": "census",
     "lat": None, "lng": None},
]


def _visible(zoom, lat0, lng0, width=800, height=460):
    """Half-extent in degrees of a MapLibre view (512 px tiles)."""
    deg_per_px = 360 / (512 * 2 ** zoom)
    return width / 2 * deg_per_px, height / 2 * deg_per_px * math.cos(math.radians(lat0))


def test_fit_zoom_shows_every_home():
    lats, lngs = [52.06, 53.45, 51.9], [-9.51, -6.15, -8.47]
    z = fit_zoom(lats, lngs)
    half_lng, half_lat = _visible(z, (max(lats) + min(lats)) / 2, 0)
    assert (max(lngs) - min(lngs)) / 2 <= half_lng
    assert (max(lats) - min(lats)) / 2 <= half_lat
    assert 3 <= z <= 16
    assert fit_zoom([53.0, 53.0005], [-6.0, -6.0005]) > 12  # one street: close in


def test_map_has_one_trace_per_band_and_skips_unlocated():
    fig = make_map(ROWS)
    assert {t.name for t in fig.data} == {"C2", "B1"}
    assert make_map([ROWS[2]]) is None


def test_band_chart_in_scale_order_with_counts():
    fig = make_band_chart({"C1": 2, "A3": 5, "B2": 1})
    assert list(fig.data[0].x) == ["A3", "B2", "C1"]
    assert list(fig.data[0].y) == [5, 1, 2]


def test_ranking_csv_round_trips():
    rows = list(csv.DictReader(io.StringIO(ranking_csv(ROWS))))
    assert [r["address"] for r in rows] == ["Killarney", "Malahide", "Not found"]
    assert rows[0]["band"] == "C2" and rows[2]["lat"] == ""
