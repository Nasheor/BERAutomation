"""Tests for the list of calculation inputs and the worked formulas (display only)."""

from __future__ import annotations

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.ber_engine.inputs import calculation_inputs, energy_formulas
from ber_automation.models import BuildingInput, CalculationOverrides, ConstructionEpoch

PIPELINE_SOURCES = {
    "dimensions": "satellite", "building_type": "streetview", "storeys": "streetview",
    "epoch": "census", "heating": "census_urban",
}


def _row(rows, name):
    return next(r for r in rows if r.name == name)


def test_window_u_value_is_the_era_preset(typical_irish_house):
    rows = calculation_inputs(typical_irish_house, PIPELINE_SOURCES)
    win = _row(rows, "Window U-value")
    assert win.value == 3.0 and win.unit == "W/m\u00b2K"
    assert win.origin == "preset" and win.key == "u_window"
    assert "before 1980" in win.source and "OIB" in win.source


def test_pipeline_sources_become_origins(typical_irish_house):
    rows = calculation_inputs(typical_irish_house, PIPELINE_SOURCES)
    assert _row(rows, "Length").origin == "images"
    assert _row(rows, "Heated storeys").origin == "images"
    assert _row(rows, "Construction era").origin == "census"
    assert _row(rows, "Heating system").origin == "census"
    assert _row(rows, "Heating degree days").origin == "climate"
    assert _row(rows, "Storey height").origin == "preset"


def test_default_footprint_is_marked_as_preset(typical_irish_house):
    rows = calculation_inputs(typical_irish_house, {**PIPELINE_SOURCES, "dimensions": "default"})
    assert _row(rows, "Length").origin == "preset"
    assert "10 \u00d7 8" in _row(rows, "Length").source


def test_manual_input_counts_as_set_by_user(typical_irish_house):
    rows = calculation_inputs(typical_irish_house)
    assert _row(rows, "Length").origin == "you"
    assert _row(rows, "Construction era").origin == "you"
    assert _row(rows, "Wall U-value").origin == "preset"  # presets stay presets


def test_overrides_show_as_set_by_user(typical_irish_house):
    house = typical_irish_house.model_copy(update={"overrides": CalculationOverrides(u_window=1.4)})
    rows = calculation_inputs(house, PIPELINE_SOURCES)
    assert _row(rows, "Window U-value").value == 1.4
    assert _row(rows, "Window U-value").origin == "you"
    assert _row(rows, "Wall U-value").origin == "preset"


def test_preset_follows_the_era():
    house = BuildingInput(length=9, width=7, construction_epoch=ConstructionEpoch.AFTER_2010)
    assert _row(calculation_inputs(house), "Window U-value").value == 1.0


def test_formulas_cover_every_result_with_this_homes_numbers(typical_irish_house):
    ber = HWBCalculator().calculate_ber(typical_irish_house)
    formulas = {f.name: f for f in energy_formulas(ber)}
    assert {"Transmission loss", "Ventilation loss", "Internal gains", "Solar gains",
            "Heating demand", "HWB", "Hot water", "Primary energy (the BER)"} <= set(formulas)
    hw = ber.hwb_result
    assert formulas["Heating demand"].result == f"{hw.heating_demand_kwh:,.0f} kWh/yr"
    assert f"{hw.floor_area:,.1f} m\u00b2" in formulas["HWB"].formula
    assert "3.75 W/m\u00b2" in formulas["Internal gains"].formula
    assert "people" in formulas["Internal gains"].meaning
    assert ber.ber_band in formulas["Primary energy (the BER)"].result
