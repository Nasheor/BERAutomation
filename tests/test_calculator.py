"""Tests for the HWB calculator and BER rating."""

from __future__ import annotations

import pytest

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.ber_engine.rating import get_ber_band
from ber_automation.models import (
    BuildingInput,
    BuildingType,
    ConstructionEpoch,
    Country,
    HeatingSystem,
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
