"""Tests for the house diagram of the annual energy balance."""

from __future__ import annotations

from app.energy_diagram import balance_line, make_house_energy_diagram
from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.models import CalculationOverrides


def _texts(fig) -> str:
    return " ".join(a.text or "" for a in fig.layout.annotations)


def test_diagram_labels_every_flow_in_kwh_per_year(typical_irish_house):
    hw = HWBCalculator().calculate(typical_irish_house)
    text = _texts(make_house_energy_diagram(hw, "Oil Boiler"))
    for label in ("Solar gains", "Internal gains", "Heating", "Transmission loss",
                  "Ventilation loss", "Hot water", "Oil Boiler"):
        assert label in text
    assert f"{hw.heating_demand_kwh:,.0f} kWh/yr" in text
    assert "kWh/m\u00b2/yr \u00d7" in text  # heating shown as HWB × floor area
    assert "W/K" not in text


def test_balance_line_closes(typical_irish_house):
    line = balance_line(HWBCalculator().calculate(typical_irish_house))
    assert " = heat supplied" in line and "surplus" not in line


def test_no_heating_needed_still_draws(modern_semi_d):
    house = modern_semi_d.model_copy(update={"overrides": CalculationOverrides(internal_gain_w_m2=10.0, g_value=1.0)})
    hw = HWBCalculator().calculate(house)
    assert hw.heating_demand_kwh == 0
    assert "0 kWh/yr" in _texts(make_house_energy_diagram(hw))
    assert "surplus" in balance_line(hw)
