"""Tests for the census housing-stock model (no network)."""

from __future__ import annotations

import pytest

from ber_automation.community.stock import (
    census_home_estimate,
    rooms_to_floor_m2,
    small_area_stock,
    typical_building,
)
from ber_automation.geospatial.census import area_from_counts
from ber_automation.models import BuildingType, ConstructionEpoch, HeatingSystem


def _area(year_built, heating, rooms=None, urban=False):
    return area_from_counts(year_built, heating, small_area="SA1", urban=urban, rooms=rooms)


OLD_OIL = _area({"before_1980": 80, "1980_1990": 0, "1990_2000": 0, "2000_2010": 0, "after_2010": 0},
                {"oil": 70, "peat": 10}, {"5": 40, "6": 40})
NEW_GAS = _area({"before_1980": 0, "1980_1990": 0, "1990_2000": 0, "2000_2010": 0, "after_2010": 80},
                {"gas": 80}, {"5": 40, "6": 40}, urban=True)


def test_weights_cover_every_home_and_scale_with_households():
    stock = small_area_stock(OLD_OIL)
    assert sum(stock.band_shares.values()) == pytest.approx(1.0, abs=1e-3)
    assert stock.households == 80
    double = small_area_stock(_area({"before_1980": 160}, {"oil": 140, "peat": 20}, {"5": 80, "6": 80}))
    assert double.heat_demand_mwh == pytest.approx(2 * stock.heat_demand_mwh, rel=1e-3)
    assert double.mean_primary_kwh_m2 == pytest.approx(stock.mean_primary_kwh_m2)


def test_old_oil_area_rates_worse_than_new_gas_area():
    old, new = small_area_stock(OLD_OIL), small_area_stock(NEW_GAS)
    assert old.mean_primary_kwh_m2 > 2 * new.mean_primary_kwh_m2
    assert old.co2_t > new.co2_t


def test_unmodelled_fuels_are_reported():
    stock = small_area_stock(OLD_OIL)
    assert stock.modelled_share == pytest.approx(70 / 80, abs=1e-3)
    assert stock.fuel_shares == {"oil": 1.0}
    assert any("not cover" in n for n in stock.notes)


def test_missing_mixes_fall_back_and_say_so():
    stock = small_area_stock(_area({"1990_2000": 50}, None, None, urban=True))
    assert stock.fuel_shares == {}  # stored shares are the census ones
    assert any("gas-heated" in n for n in stock.notes)
    assert any("5 rooms" in n for n in stock.notes)
    assert stock.heat_demand_mwh > 0
    assert small_area_stock(_area(None, {"gas": 50})).heat_demand_mwh == 0


def test_typical_building_size_and_type():
    small = typical_building(60, ConstructionEpoch.BEFORE_1980, HeatingSystem.OIL_BOILER, urban=False)
    assert small.heated_storeys == 1 and small.building_type == BuildingType.DETACHED
    assert small.total_heated_area == pytest.approx(60, rel=1e-3)
    big = typical_building(rooms_to_floor_m2("8+"), ConstructionEpoch.AFTER_2010,
                           HeatingSystem.GAS_BOILER, urban=True)
    assert big.heated_storeys == 2 and big.building_type == BuildingType.SEMI_D_LENGTH
    assert big.total_heated_area == pytest.approx(170, rel=1e-3)


def test_one_home_estimate_uses_the_pipeline_rules():
    est = census_home_estimate(NEW_GAS)
    assert est.building_input.construction_epoch == ConstructionEpoch.AFTER_2010
    assert est.building_input.heating_system == HeatingSystem.GAS_BOILER
    old = census_home_estimate(OLD_OIL)
    assert old.building_input.heating_system == HeatingSystem.OIL_BOILER
    assert old.kwh_per_m2 > est.kwh_per_m2
    assert census_home_estimate(_area(None, {"gas": 50})) is None
