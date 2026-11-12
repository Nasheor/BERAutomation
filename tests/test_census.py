"""Tests for the census priors: construction era and heating fuel."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ber_automation.geospatial import census
from ber_automation.geospatial.census import (
    area_from_counts,
    choose_epoch,
    choose_heating,
    lookup_census_area,
    prior_from_counts,
)
from ber_automation.models import (
    CensusArea,
    ConstructionEpoch as E,
    Coordinates,
    Country,
    HeatingSystem as H,
    PipelineResult,
    StreetViewAnalysis,
)
from ber_automation.pipeline import BERPipeline


def _counts(**kw):
    keys = {"pre80": "before_1980", "e80": "1980_1990", "e90": "1990_2000",
            "e00": "2000_2010", "post10": "after_2010"}
    return {keys[k]: v for k, v in kw.items()}


def _fuel(**kw):
    base = dict.fromkeys(["gas", "oil", "electricity", "wood", "lpg", "coal", "peat", "other", "none"], 0)
    base.update(kw)
    return base


def _sv(epoch=E.EPOCH_1990_2000, conf=0.6, heating=H.OIL_BOILER, observed=False):
    return StreetViewAnalysis(construction_epoch=epoch, confidence=conf,
                              heating_system_guess=heating, heating_observed=observed)


# Validation houses' Small Areas (households, Census 2022)
HYW6 = prior_from_counts(_counts(pre80=29, e80=46, e90=3, e00=2))
RK10 = prior_from_counts(_counts(pre80=7, e80=36, e90=34, e00=2))
K7AC = prior_from_counts(_counts(e90=7, e00=102, post10=2))
RK10_AREA = area_from_counts(_counts(pre80=7, e80=36, e90=34, e00=2),
                             _fuel(gas=30, oil=41, electricity=1, wood=2, lpg=2, coal=3),
                             small_area="047054013", urban=True, urban_area="Tower")


# --- era ---------------------------------------------------------------------------

def test_prior_shares_and_dominant():
    assert HYW6.dominant_epoch == E.EPOCH_1980_1990
    assert HYW6.households == 80
    assert HYW6.dominant_share == pytest.approx(46 / 80)
    assert sum(HYW6.shares.values()) == pytest.approx(1.0)


def test_too_few_households_gives_no_prior():
    assert prior_from_counts(_counts(e80=10, e90=5)) is None


def test_adjacent_band_defers_to_census():
    # Claude reads the 1980s estate as 1990s: census wins
    assert choose_epoch(HYW6, _sv(E.EPOCH_1990_2000)) == (E.EPOCH_1980_1990, "census")
    assert choose_epoch(RK10, _sv(E.EPOCH_1990_2000, 0.6)) == (E.EPOCH_1980_1990, "census")


def test_adjacent_band_kept_when_common_and_confident():
    assert choose_epoch(RK10, _sv(E.EPOCH_1990_2000, 0.85)) == (E.EPOCH_1990_2000, "streetview")


def test_distant_band_kept_when_present_in_area():
    assert choose_epoch(HYW6, _sv(E.BEFORE_1980)) == (E.EPOCH_1980_1990, "census")  # adjacent
    mixed = prior_from_counts(_counts(pre80=20, e80=10, e90=60, e00=10))
    assert choose_epoch(mixed, _sv(E.BEFORE_1980)) == (E.BEFORE_1980, "streetview")


def test_distant_band_absent_from_area_rejected():
    assert choose_epoch(K7AC, _sv(E.BEFORE_1980)) == (E.EPOCH_2000_2010, "census")


def test_matching_and_missing_readings():
    assert choose_epoch(K7AC, _sv(E.EPOCH_2000_2010)) == (E.EPOCH_2000_2010, "census")
    assert choose_epoch(K7AC, None) == (E.EPOCH_2000_2010, "census")
    # Low-confidence (e.g. privacy-blurred) reading is ignored
    assert choose_epoch(K7AC, _sv(E.EPOCH_1990_2000, 0.2)) == (E.EPOCH_2000_2010, "census")
    assert choose_epoch(None, _sv(E.EPOCH_1990_2000)) == (E.EPOCH_1990_2000, "streetview")
    assert choose_epoch(None, None) == (None, "default")


# --- heating -----------------------------------------------------------------------

def test_gas_area_overrides_unobserved_oil_guess():
    # RK10: Claude guessed oil ("rural locality"); 38 % of the area is on gas
    assert choose_heating(RK10_AREA, _sv(heating=H.OIL_BOILER)) == (H.GAS_BOILER, "census")


def test_observed_heating_clue_is_kept():
    seen = _sv(heating=H.OIL_BOILER, observed=True)
    assert choose_heating(RK10_AREA, seen) == (H.OIL_BOILER, "streetview")
    # ...but not from a low-confidence reading
    assert choose_heating(RK10_AREA, _sv(conf=0.2, observed=True)) == (H.GAS_BOILER, "census")


def test_no_gas_area_uses_most_common_other_fuel():
    village = area_from_counts(None, _fuel(gas=1, oil=60, electricity=10, wood=8), urban=True)
    assert choose_heating(village, _sv(heating=H.GAS_BOILER)) == (H.OIL_BOILER, "census")
    flats = area_from_counts(None, _fuel(gas=2, oil=3, electricity=90))
    assert choose_heating(flats, None) == (H.ELECTRIC_DIRECT, "census")
    # Electric in a post-2010 home is a heat pump
    assert choose_heating(flats, None, E.AFTER_2010) == (H.HEAT_PUMP_AIR, "census")


def test_urban_flag_is_the_fallback_without_fuel_mix():
    assert choose_heating(CensusArea(urban=True, urban_area="Tower"), None) == (H.GAS_BOILER, "census_urban")
    assert choose_heating(CensusArea(urban=False), _sv(heating=H.GAS_BOILER)) == (H.OIL_BOILER, "census_urban")


def test_no_census_keeps_claude_guess():
    assert choose_heating(None, _sv(heating=H.OIL_BOILER)) == (H.OIL_BOILER, "streetview")
    assert choose_heating(None, None) == (None, "default")


def test_small_fuel_sample_ignored():
    area = area_from_counts(None, _fuel(gas=5, oil=5), urban=False)
    assert area.heating_shares == {}
    assert choose_heating(area, None) == (H.OIL_BOILER, "census_urban")


# --- lookup ------------------------------------------------------------------------

def _client(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_lookup_reads_small_area(monkeypatch):
    monkeypatch.setattr(census, "_year_built_table",
                        lambda: {"guid-1": _counts(pre80=29, e80=46, e90=3, e00=2, post10=0)})
    monkeypatch.setattr(census, "_heating_table", lambda: {"guid-1": _fuel(gas=66, oil=7)})
    client = _client({"features": [{"attributes": {
        "SA_GUID_2022": "guid-1", "SA_PUB2022": "048051004",
        "SA_URBAN_AREA_FLAG": 1, "SA_URBAN_AREA_NAME": "Cork city and suburbs"}}]})
    area = await lookup_census_area(Coordinates(lat=51.9, lng=-8.5), client=client)
    assert area.small_area == "048051004"
    assert area.urban and area.urban_area == "Cork city and suburbs"
    assert area.era.dominant_epoch == E.EPOCH_1980_1990
    assert area.heating_shares["gas"] == pytest.approx(66 / 73)
    assert client.get.call_args.kwargs["params"]["geometry"] == "-8.5,51.9"


@pytest.mark.asyncio
async def test_lookup_rural_area_without_name(monkeypatch):
    monkeypatch.setattr(census, "_year_built_table", lambda: {})
    monkeypatch.setattr(census, "_heating_table", lambda: {})
    client = _client({"features": [{"attributes": {
        "SA_GUID_2022": "g", "SA_PUB2022": "1", "SA_URBAN_AREA_FLAG": 0,
        "SA_URBAN_AREA_NAME": None}}]})
    area = await lookup_census_area(Coordinates(lat=52.0, lng=-8.8), client=client)
    assert not area.urban and area.urban_area == ""
    assert area.era is None and area.heating_shares == {}


@pytest.mark.asyncio
async def test_lookup_outside_ireland_or_failing_returns_none():
    assert await lookup_census_area(Coordinates(lat=49.6, lng=6.1), Country.LUXEMBOURG) is None
    assert await lookup_census_area(Coordinates(lat=0, lng=0), client=_client({"features": []})) is None
    broken = MagicMock()
    broken.get = AsyncMock(side_effect=RuntimeError("offline"))
    assert await lookup_census_area(Coordinates(lat=51.9, lng=-8.5), client=broken) is None


def test_data_files_cover_all_small_areas():
    guid = "4c07d11e-1f14-851d-e053-ca3ca8c0ca7f"  # RK10
    years, fuels = census._year_built_table(), census._heating_table()
    assert len(years) > 18_000 and len(fuels) > 18_000
    assert years[guid] == _counts(pre80=7, e80=36, e90=34, e00=2, post10=0)
    assert fuels[guid] == _fuel(gas=30, oil=41, electricity=1, wood=2, lpg=2, coal=3)


# --- pipeline ----------------------------------------------------------------------

def test_build_input_uses_census_and_respects_overrides():
    result = PipelineResult(address="x", census=RK10_AREA,
                            street_analysis=_sv(E.EPOCH_1990_2000, heating=H.OIL_BOILER))
    pipe = BERPipeline.__new__(BERPipeline)
    bi = pipe._build_input(result)
    assert (bi.construction_epoch, bi.heating_system) == (E.EPOCH_1980_1990, H.GAS_BOILER)
    assert (result.epoch_source, result.heating_source) == ("census", "census")
    bi = pipe._build_input(result, overrides={"construction_epoch": E.AFTER_2010,
                                              "heating_system": H.HEAT_PUMP_AIR})
    assert (bi.construction_epoch, bi.heating_system) == (E.AFTER_2010, H.HEAT_PUMP_AIR)
    assert (result.epoch_source, result.heating_source) == ("override", "override")
