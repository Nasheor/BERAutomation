"""Tests for comparing pipeline estimates with official BER certificates."""

from __future__ import annotations

from datetime import date

import pytest

from ber_automation.evaluation.official_compare import (
    band_distance,
    certificate_level,
    commonest_band_baseline,
    compare_inputs,
    run_agreement,
    score,
    summarise_inputs,
    summarise_scores,
    with_certificate_values,
)
from ber_automation.evaluation.official_sample import OfficialHome
from ber_automation.models import BuildingInput, BuildingType, ConstructionEpoch, HeatingSystem


def _home(**kw) -> OfficialHome:
    base = dict(id="1", eircode="T12 K7AC", county="Cork", settlement="urban",
                listing_source="daft.ie", date_recorded=date(2026, 11, 13),
                ber_number="113779219", ber_band="C2", ber_kwh_m2_yr=180.0)
    return OfficialHome(**(base | kw))


def _building(**kw) -> BuildingInput:
    base = dict(length=10.0, width=8.0, heated_storeys=2,
                building_type=BuildingType.SEMI_D_WIDTH,
                construction_epoch=ConstructionEpoch.BEFORE_1980,
                heating_system=HeatingSystem.GAS_BOILER)
    return BuildingInput(**(base | kw))


def test_band_distance_counts_steps_across_letters():
    assert band_distance("A3", "B1") == 1
    assert band_distance("C2", "C2") == 0
    assert band_distance("F", "D2") == 3


def test_score_signs_and_tolerance():
    s = score(_home(), "C3", 207.0)
    assert not s["band_exact"] and s["band_within_one"]
    assert s["band_offset"] == 1          # rated one band worse
    assert s["kwh_error_pct"] == 15.0
    assert not score(_home(), "B3", 140.0)["band_within_one"]


def test_compare_inputs_reports_only_recorded_values():
    assert compare_inputs(_home(), _building()) == {}

    home = _home(dwelling_type="semi_detached", year_built=2001, floor_area_m2=137.17,
                 storeys=2, heating=HeatingSystem.OIL_BOILER)
    a = compare_inputs(home, _building())
    assert a["dwelling_type"]["match"]
    assert a["era"] == {"ours": "before_1980", "certificate": "2000_2010", "match": False}
    assert a["floor_area_m2"]["ours"] == 160.0
    assert a["floor_area_m2"]["error_pct"] == pytest.approx(16.6, abs=0.05)
    assert a["storeys"]["match"]
    assert not a["heating"]["match"]


def test_certificate_values_replace_era_area_storeys_heating():
    home = _home(year_built=2018, floor_area_m2=120.0, storeys=1,
                 heating=HeatingSystem.HEAT_PUMP_AIR)
    b = with_certificate_values(home, _building())
    assert b.construction_epoch == ConstructionEpoch.AFTER_2010
    assert b.heated_storeys == 1
    assert b.heating_system == HeatingSystem.HEAT_PUMP_AIR
    assert b.length * b.width * b.heated_storeys == pytest.approx(120.0)
    assert b.length / b.width == pytest.approx(10.0 / 8.0)   # plan shape kept


def test_certificate_type_keeps_pipeline_side_when_kind_agrees():
    semi = _home(dwelling_type="semi_detached")
    assert with_certificate_values(semi, _building()).building_type == BuildingType.SEMI_D_WIDTH
    detached = _home(dwelling_type="detached")
    assert with_certificate_values(detached, _building()).building_type == BuildingType.DETACHED
    assert (with_certificate_values(semi, _building(building_type=BuildingType.DETACHED))
            .building_type == BuildingType.SEMI_D_LENGTH)


def test_certificate_values_leave_unrecorded_inputs_alone():
    b = _building()
    assert with_certificate_values(_home(), b) == b


def test_certificate_level_runs_the_calculator():
    out = certificate_level(_home(year_built=2020, floor_area_m2=110.0), _building())
    assert out["inputs"]["epoch"] == "after_2010"
    assert out["band"] and out["kwh_m2_yr"] > 0


def test_commonest_band_baseline_leaves_the_home_out():
    homes = [_home(id="1", ber_band="C3", ber_kwh_m2_yr=210.0),
             _home(id="2", ber_band="C3", ber_kwh_m2_yr=220.0),
             _home(id="3", ber_band="A3", ber_kwh_m2_yr=60.0)]
    base = commonest_band_baseline(homes)
    # Home 1 sees one C3 and one A3: a tie, broken towards the middle of the scale
    assert base[0]["band"] == "C3" and base[0]["kwh_m2_yr"] == 220.0
    assert base[2]["band"] == "C3" and base[2]["kwh_m2_yr"] == 215.0
    assert commonest_band_baseline(homes[:1]) == [{}]


def test_summaries():
    home = _home()
    s = summarise_scores([score(home, "C2", 180.0), score(home, "D1", 234.0), {}])
    assert s["n"] == 2 and s["band_exact"] == 1 and s["band_within_one"] == 1
    assert s["mean_abs_kwh_error_pct"] == 15.0
    assert summarise_scores([]) == {"n": 0}

    full = _home(dwelling_type="detached", floor_area_m2=100.0)
    a = summarise_inputs([compare_inputs(full, _building()), compare_inputs(_home(), _building())])
    assert a["dwelling_type"] == {"n": 1, "match": 0}
    assert a["floor_area_m2"]["mean_abs_error_pct"] == 60.0


def test_run_agreement():
    assert run_agreement(["C2"]) is None
    assert run_agreement(["C2", "C2", "C3"]) == pytest.approx(2 / 3)
