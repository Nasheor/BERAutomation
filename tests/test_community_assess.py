"""Tests for community assessment and its summaries (geocoder, census and pipeline mocked)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.community.assess import assess_community, pick_sample
from ber_automation.community.models import CommunityHome, CommunityResult
from ber_automation.community.summary import agreement, area_totals, band_counts, ranking, totals
from ber_automation.geospatial.census import area_from_counts
from ber_automation.models import BuildingInput, ConstructionEpoch, Coordinates, HeatingSystem

AREAS = {
    "OLD": area_from_counts({"before_1980": 90}, {"oil": 90}, small_area="OLD", rooms={"5": 90}),
    "NEW": area_from_counts({"after_2010": 60}, {"gas": 60}, small_area="NEW", urban=True,
                            rooms={"5": 60}),
}
# address -> (lat, Small Area); "lost" cannot be geocoded
PLACES = {"1 Old Rd": (52.0, "OLD"), "2 Old Rd": (52.1, "OLD"), "3 New Rd": (53.0, "NEW"),
          "4 New Rd": (53.1, "NEW")}


async def fake_geocode(address, country=None):
    if address not in PLACES:
        raise ValueError("ZERO_RESULTS")
    return Coordinates(lat=PLACES[address][0], lng=-8.0, formatted_address=address)


async def fake_census(coords, country=None):
    return next(AREAS[a] for lat, a in PLACES.values() if lat == coords.lat)


class FakePipeline:
    calls: list[str] = []

    def __init__(self, output_dir=None, provider=None):
        self.output_dir = output_dir

    async def run(self, address, country=None):
        FakePipeline.calls.append(address)
        if address == "4 New Rd":
            raise RuntimeError("Street View quota")
        ber = HWBCalculator().calculate_ber(BuildingInput(
            length=9, width=7, construction_epoch=ConstructionEpoch.EPOCH_1990_2000,
            heating_system=HeatingSystem.GAS_BOILER,
        ))
        return SimpleNamespace(ber_result=ber, errors=["No Street View available at this location"])


def _entries(*addresses):
    return [{"id": str(i), "address": a} for i, a in enumerate(addresses, 1)]


def _run(tmp_path, entries, analyse="none"):
    return asyncio.run(assess_community(
        entries, "Test village", analyse=analyse, base_dir=tmp_path,
        geocode=fake_geocode, census_lookup=fake_census, pipeline_factory=FakePipeline,
    ))


@pytest.fixture(autouse=True)
def _reset_calls():
    FakePipeline.calls = []


def test_census_estimate_for_every_located_home(tmp_path):
    res = _run(tmp_path, _entries("1 Old Rd", "3 New Rd", "lost"))
    by_id = {h.id: h for h in res.homes}
    assert by_id["1"].small_area == "OLD" and by_id["1"].source == "census"
    assert by_id["1"].best.kwh_per_m2 > by_id["2"].best.kwh_per_m2
    assert by_id["3"].best is None and "Address not found" in by_id["3"].errors[0]
    assert set(res.areas) == {"OLD", "NEW"} and res.areas["OLD"].households == 90
    assert FakePipeline.calls == []
    assert (tmp_path / "Test_village" / "community.json").exists()


def test_images_for_chosen_homes_and_failures_kept(tmp_path):
    res = _run(tmp_path, _entries("1 Old Rd", "2 Old Rd", "3 New Rd", "4 New Rd"), analyse="all")
    by_id = {h.id: h for h in res.homes}
    assert sorted(FakePipeline.calls) == ["1 Old Rd", "2 Old Rd", "3 New Rd", "4 New Rd"]
    assert by_id["1"].source == "images" and by_id["1"].image_runs == 1
    assert any("No Street View" in e for e in by_id["1"].errors)
    assert by_id["4"].source == "census" and "Street View quota" in by_id["4"].errors[-1]


def test_rerun_reuses_saved_results(tmp_path):
    entries = _entries("1 Old Rd", "3 New Rd")
    _run(tmp_path, entries, analyse=["1"])
    assert FakePipeline.calls == ["1 Old Rd"]
    FakePipeline.calls = []
    res = _run(tmp_path, entries, analyse="all")  # only the home not yet analysed runs
    assert FakePipeline.calls == ["3 New Rd"]
    assert CommunityResult.load(tmp_path / "Test_village" / "community.json").homes[0].image_estimate
    assert all(h.source == "images" for h in res.homes)


def test_sample_spreads_over_small_areas():
    homes = [CommunityHome(id=str(i), address=a, small_area=s,
                           coordinates=Coordinates(lat=0, lng=0))
             for i, (a, s) in enumerate([("a", "X"), ("b", "X"), ("c", "X"), ("d", "Y")], 1)]
    assert pick_sample(homes, 2) == ["1", "4"]
    assert pick_sample(homes, 10) == ["1", "4", "2", "3"]


def test_summaries(tmp_path):
    res = _run(tmp_path, _entries("1 Old Rd", "2 Old Rd", "3 New Rd", "lost"), analyse=["3"])
    rows = ranking(res)
    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert rows[0]["kwh_m2"] >= rows[-1]["kwh_m2"] and rows[0]["source"] == "census"
    t = totals(res)
    assert t["homes"] == 4 and t["rated"] == 3 and t["from_images"] == 1 and t["not_located"] == 1
    assert t["primary_mwh"] == pytest.approx(sum(r["primary_mwh"] for r in rows), abs=0.05)
    assert sum(band_counts(res).values()) == 3
    a = area_totals(res)
    assert a["households"] == 150 and a["small_areas"] == 2
    agree = agreement(res)
    assert agree["n"] == 1 and agree["rows"][0]["id"] == "3"


def test_read_addresses_csv_and_plain_list():
    from ber_automation.community.addresses import read_addresses
    csv_text = "\ufeffid,eircode,county\n7,R35 HH93,Offaly\n8,k36 ha21,Dublin\n9,R35 HH93,Offaly\n"
    assert read_addresses(csv_text) == [{"id": "7", "address": "R35 HH93"},
                                        {"id": "8", "address": "k36 ha21"}]
    assert read_addresses("R35 HH93\n\nD13 DC65,\n") == [{"id": "1", "address": "R35 HH93"},
                                                         {"id": "2", "address": "D13 DC65"}]
    assert read_addresses("Address\n1 Main St, Tullamore\n") == [
        {"id": "1", "address": "1 Main St, Tullamore"}]
    assert read_addresses("  ") == []
