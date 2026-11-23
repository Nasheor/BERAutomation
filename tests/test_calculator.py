"""Tests for the HWB calculator and BER rating."""

from __future__ import annotations

import pytest

from ber_automation.ber_engine.calculator import HWBCalculator, resolve_presets
from ber_automation.ber_engine.rating import get_ber_band
from ber_automation.models import (
    BuildingInput,
    BuildingType,
    CalculationOverrides,
    ConstructionEpoch,
    Country,
    HeatingSystem,
    HWBResult,
    RetrofitInput,
)


class TestBERRating:
    """Test BER band mapping."""

    @pytest.mark.parametrize(
        "kwh, expected_band",
        [
            (20, "A1"),
            (25, "A1"),
            (50, "A2"),
            (100, "B1"),
            (125, "B2"),
            (200, "C2"),
            (300, "D2"),
            (450, "F"),
            (500, "G"),
        ],
    )
    def test_ber_bands(self, kwh: float, expected_band: str):
        band, color = get_ber_band(kwh)
        assert band == expected_band
        assert color.startswith("#")


class TestHWBCalculator:
    """Test the HWB calculation engine."""

    def setup_method(self):
        self.calc = HWBCalculator()

    def test_typical_old_house_high_hwb(self, typical_irish_house):
        """Pre-1980 detached house should have high energy demand."""
        result = self.calc.calculate(typical_irish_house)
        assert result.floor_area == 160.0  # 10 * 8 * 2
        # Volume = net_area * (storey_height - 0.35) * storeys
        # = (160*0.8) * (3.0-0.35) * 2 = 128 * 2.65 * 2 = 678.4
        assert abs(result.heated_volume - 678.4) < 0.1
        assert result.hwb > 100  # old house = high HWB
        assert result.transmission_heat_loss > 0
        assert result.ventilation_heat_loss > 0

    def test_modern_house_low_hwb(self, modern_semi_d):
        """Post-2010 semi-D with heat pump should have low energy demand."""
        result = self.calc.calculate(modern_semi_d)
        assert result.hwb < 100  # modern = lower HWB

    def test_semi_d_less_loss_than_detached(self):
        """Semi-D should have less transmission loss (shared wall)."""
        base = dict(
            length=10.0, width=8.0, heated_storeys=2, storey_height=3.0,
            construction_epoch=ConstructionEpoch.BEFORE_1980,
            country=Country.IRELAND, heating_system=HeatingSystem.GAS_BOILER,
        )
        detached = BuildingInput(building_type=BuildingType.DETACHED, **base)
        semi_d = BuildingInput(building_type=BuildingType.SEMI_D_LENGTH, **base)

        r_det = self.calc.calculate(detached)
        r_sem = self.calc.calculate(semi_d)

        assert r_sem.transmission_heat_loss < r_det.transmission_heat_loss

    def test_terraced_least_loss(self):
        """Terraced should have the least transmission loss."""
        base = dict(
            length=10.0, width=8.0, heated_storeys=2, storey_height=3.0,
            construction_epoch=ConstructionEpoch.BEFORE_1980,
            country=Country.IRELAND, heating_system=HeatingSystem.GAS_BOILER,
        )
        detached = BuildingInput(building_type=BuildingType.DETACHED, **base)
        terraced = BuildingInput(building_type=BuildingType.TERRACED_LENGTH, **base)

        r_det = self.calc.calculate(detached)
        r_ter = self.calc.calculate(terraced)

        assert r_ter.transmission_heat_loss < r_det.transmission_heat_loss

    def test_heat_pump_lower_final_energy(self):
        """Heat pump should yield lower final energy than oil boiler."""
        base = dict(
            length=10.0, width=8.0, heated_storeys=2, storey_height=3.0,
            building_type=BuildingType.DETACHED,
            construction_epoch=ConstructionEpoch.BEFORE_1980,
            country=Country.IRELAND,
        )
        oil = BuildingInput(heating_system=HeatingSystem.OIL_BOILER, **base)
        hp = BuildingInput(heating_system=HeatingSystem.HEAT_PUMP_AIR, **base)

        r_oil = self.calc.calculate(oil)
        r_hp = self.calc.calculate(hp)

        # Heat pump COP=3, oil efficiency=0.85
        # Final energy should be much lower for heat pump
        assert r_hp.final_energy_kwh < r_oil.final_energy_kwh

    def test_newer_epoch_lower_hwb(self):
        """Newer construction epoch should have lower HWB."""
        base = dict(
            length=10.0, width=8.0, heated_storeys=2, storey_height=3.0,
            building_type=BuildingType.DETACHED,
            country=Country.IRELAND, heating_system=HeatingSystem.GAS_BOILER,
        )
        old = BuildingInput(construction_epoch=ConstructionEpoch.BEFORE_1980, **base)
        new = BuildingInput(construction_epoch=ConstructionEpoch.AFTER_2010, **base)

        r_old = self.calc.calculate(old)
        r_new = self.calc.calculate(new)

        assert r_new.hwb < r_old.hwb

    def test_ber_rating_output(self, typical_irish_house):
        """BER calculation should produce valid band."""
        ber = self.calc.calculate_ber(typical_irish_house)
        assert ber.ber_band in ["A1", "A2", "A3", "B1", "B2", "B3",
                                 "C1", "C2", "C3", "D1", "D2",
                                 "E1", "E2", "F", "G"]
        assert ber.kwh_per_m2 > 0
        assert ber.color_hex.startswith("#")

    def test_retrofit_improves_rating(self, typical_irish_house):
        """Retrofit should improve (lower) the energy rating."""
        retrofit = RetrofitInput(
            wall_insulation_cm=12,
            roof_insulation_cm=20,
            window_u_value=1.0,
            heating_system_after=HeatingSystem.HEAT_PUMP_AIR,
        )
        ber = self.calc.calculate_ber(typical_irish_house, retrofit)
        assert ber.retrofit_kwh_per_m2 is not None
        assert ber.retrofit_kwh_per_m2 < ber.kwh_per_m2

    def test_hot_water_included(self, typical_irish_house):
        """Hot water demand should be included in total."""
        result = self.calc.calculate(typical_irish_house)
        assert result.hot_water_kwh > 0
        assert result.total_kwh_per_m2 > result.hwb  # total > just heating

    def test_co2_positive(self, typical_irish_house):
        """CO2 emissions should be positive."""
        result = self.calc.calculate(typical_irish_house)
        assert result.co2_kg > 0
        assert result.co2_kg_per_m2 > 0


class TestPresetsAndOverrides:
    """Presets the user replaces (CalculationOverrides) and the annual energy balance."""

    calc = HWBCalculator()

    def _with(self, house: BuildingInput, **values) -> BuildingInput:
        return house.model_copy(update={"overrides": CalculationOverrides(**values)})

    def test_presets_come_from_era_type_and_heating(self, typical_irish_house):
        p = resolve_presets(typical_irish_house)
        assert p["u_window"] == 3.0 and p["u_wall"] == 1.2  # before 1980
        assert p["window_share"] == 0.15                     # detached
        assert p["heating_efficiency"] == 0.85               # oil boiler
        assert p["air_change_rate"] == 0.4 and p["internal_gain_w_m2"] == 3.75

    def test_empty_overrides_change_nothing(self, typical_irish_house):
        plain = self.calc.calculate_ber(typical_irish_house)
        empty = self.calc.calculate_ber(self._with(typical_irish_house))
        assert empty.kwh_per_m2 == plain.kwh_per_m2
        assert empty.hwb_result.hwb == plain.hwb_result.hwb

    @pytest.mark.parametrize("field, value, direction", [
        ("u_window", 1.2, -1),
        ("u_wall", 0.3, -1),
        ("u_roof", 0.15, -1),
        ("u_floor", 0.3, -1),
        ("g_value", 0.9, -1),
        ("air_change_rate", 1.0, +1),
        ("internal_gain_w_m2", 6.0, -1),
    ])
    def test_override_moves_heating_demand(self, typical_irish_house, field, value, direction):
        base = self.calc.calculate(typical_irish_house).heating_demand_kwh
        changed = self.calc.calculate(self._with(typical_irish_house, **{field: value})).heating_demand_kwh
        assert (changed - base) * direction > 0

    def test_window_share_sets_window_area(self, typical_irish_house):
        # More glass loses more heat but also lets in more sun, so only the area is certain
        base = self.calc.calculate(typical_irish_house)
        more = self.calc.calculate(self._with(typical_irish_house, window_share=0.30))
        assert more.window_area == pytest.approx(base.window_area * 2)
        assert more.solar_gains == pytest.approx(base.solar_gains * 2)

    def test_efficiency_override_changes_delivered_not_demand(self, typical_irish_house):
        base = self.calc.calculate(typical_irish_house)
        better = self.calc.calculate(self._with(typical_irish_house, heating_efficiency=0.95))
        assert better.heating_demand_kwh == pytest.approx(base.heating_demand_kwh)
        assert better.final_energy_kwh < base.final_energy_kwh

    def test_retrofit_insulates_the_overridden_wall(self, typical_irish_house):
        retrofit = RetrofitInput(wall_insulation_cm=10, roof_insulation_cm=0, window_u_value=3.0)
        preset = self.calc.calculate_with_retrofit_uvalues(typical_irish_house, retrofit)
        good_wall = self._with(typical_irish_house, u_wall=0.3)
        better = self.calc.calculate_with_retrofit_uvalues(good_wall, retrofit)
        assert better.presets["u_wall"] == pytest.approx(1 / (1 / 0.3 + 0.1 / 0.035))
        assert preset.presets["u_wall"] == pytest.approx(1 / (1 / 1.2 + 0.1 / 0.035))
        assert better.heating_demand_kwh < preset.heating_demand_kwh

    def test_new_heating_system_drops_old_efficiency(self, typical_irish_house):
        house = self._with(typical_irish_house, heating_efficiency=0.6, u_window=2.0)
        retrofit = RetrofitInput(wall_insulation_cm=0, roof_insulation_cm=0, window_u_value=2.0,
                                 heating_system_after=HeatingSystem.HEAT_PUMP_AIR)
        after = self.calc.calculate_with_retrofit_uvalues(house, retrofit)
        assert after.presets["heating_efficiency"] == 3.5
        assert after.presets["u_window"] == 2.0

    def test_energy_balance_closes(self, typical_irish_house, modern_semi_d):
        for house in (typical_irish_house, modern_semi_d):
            hw = self.calc.calculate(house)
            losses_less_gains = (hw.transmission_loss_kwh + hw.ventilation_loss_kwh
                                 - hw.internal_gains - hw.solar_gains)
            assert hw.heating_demand_kwh == pytest.approx(max(0.0, losses_less_gains))
            assert hw.hwb * hw.floor_area == pytest.approx(hw.heating_demand_kwh)
            assert hw.transmission_loss_kwh == pytest.approx(0.024 * hw.transmission_heat_loss * hw.hdd)

    def test_old_saved_results_still_load(self, typical_irish_house):
        data = self.calc.calculate(typical_irish_house).model_dump()
        for key in ("transmission_loss_kwh", "ventilation_loss_kwh", "presets", "hdd"):
            data.pop(key)
        assert HWBResult(**data).transmission_loss_kwh == 0.0
