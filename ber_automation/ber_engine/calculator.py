"""
HWB Calculator — ported from the Excel tool.

Implements the Austrian HWB (Heizwaermebedarf) annual balance method from
"Leitfaden fuer die Berechnung des Heizwaermebedarfs" (Die Umweltberatung, 2019).

Every formula references its Excel cell (Calculations sheet row 2) for traceability.

Excel Calculation Flow:
    C2  = gross_area = length * width * storeys
    D2  = net_area = gross_area * 0.8
    E2  = envelope_area = ((length+width)*2) * storeys * storey_height
    F2  = window/door total area (from Input!J2)
    K2  = roof_area = length * width
    L2  = floor_area = length * width
    M2  = walls = envelope_area - window_area
    N2  = external_walls = walls - adjacent_walls
    O2  = adjacent walls (party walls for semi-d/terraced)
    P2  = volume = net_area * (storey_height - 0.35) * storeys

    Transmission: AT2 = U_win*A_win*1 + U_roof*A_roof*1 + U_floor*A_floor*0.7 + U_wall*A_extwall*1
    Thermal bridge: AU2 = MAX(0.2*(0.75 - AT2/(A_win+A_roof+A_floor+A_extwall)) * AT2, 0)
    L_t: AV2 = AT2 + AU2
    Q_t: AW2 = 0.024 * L_t * HDD
    Q_v: BC2 = 0.024 * (0.34 * 0.4 * volume) * HDD
    Q_i: BG2 = 0.024 * 3.75 * net_area * heating_days
    Q_s: BU2 = (Irr_N*A_N + Irr_E*A_E + Irr_S*A_S + Irr_W*A_W) * F_s * g_eff
    Q_heating: BY2 = Q_t + Q_v - Q_i - Q_s
    Q_hotwater: CB2 = residents * 40 * 365 * (4.2/3600) * 45
"""

from __future__ import annotations

from ber_automation.ber_engine.constants import (
    AIR_CHANGE_RATE,
    AIR_HEAT_CAPACITY,
    CO2_FACTOR,
    DIRT_FACTOR,
    FLOOR_THICKNESS,
    FLOOR_U_FACTOR,
    FRAME_FACTOR,
    G_VALUES,
    HDD_TO_KWH_FACTOR,
    HEATING_DAYS,
    HEATING_DEGREE_DAYS,
    HEATING_SYSTEM_EFFICIENCY,
    HOT_WATER_LITRES_PER_PERSON_PER_DAY,
    HOT_WATER_SPECIFIC_HEAT,
    HOT_WATER_TEMP_RISE_K,
    INSULATION_CONDUCTIVITY,
    INTERNAL_GAIN_RATE,
    NET_TO_GROSS_RATIO,
    PRIMARY_ENERGY_FACTOR,
    SHADING_FACTOR,
    SOLAR_IRRADIANCE,
    THERMAL_BRIDGE_FACTOR,
    THERMAL_BRIDGE_REFERENCE,
    U_VALUES,
    WINDOW_AREA_FRACTION,
)
from ber_automation.ber_engine.rating import get_ber_band
from ber_automation.models import (
    BERResult,
    BuildingInput,
    BuildingType,
    HeatingSystem,
    HWBResult,
    RetrofitInput,
    WindowDoorAreas,
)


class HWBCalculator:
    """Calculate HWB (annual heating demand) following the Excel tool logic exactly."""

    # --- public API ---

    def calculate(self, building: BuildingInput) -> HWBResult:
        """Run the full HWB calculation for *building*."""
        u = U_VALUES[building.construction_epoch]
        g = G_VALUES[building.construction_epoch]
        return self._calculate_core(building, u, g)

    def calculate_ber(
        self,
        building: BuildingInput,
        retrofit: RetrofitInput | None = None,
    ) -> BERResult:
        """Calculate BER rating, optionally including retrofit scenario."""
        hwb_result = self.calculate(building)

        pef = PRIMARY_ENERGY_FACTOR[building.heating_system]
        primary_kwh_per_m2 = hwb_result.total_kwh_per_m2 * pef
        band, color = get_ber_band(primary_kwh_per_m2)

        result = BERResult(
            ber_band=band,
            kwh_per_m2=round(primary_kwh_per_m2, 1),
            color_hex=color,
            hwb_result=hwb_result,
            building_input=building,
        )

        if retrofit:
            retrofit_hwb = self.calculate_with_retrofit_uvalues(building, retrofit)
            retrofit_building = self._apply_retrofit(building, retrofit)
            pef_r = PRIMARY_ENERGY_FACTOR[retrofit_building.heating_system]
            retrofit_primary = retrofit_hwb.total_kwh_per_m2 * pef_r
            r_band, _ = get_ber_band(retrofit_primary)
            result.retrofit_ber_band = r_band
            result.retrofit_kwh_per_m2 = round(retrofit_primary, 1)
            result.retrofit_hwb_result = retrofit_hwb

        return result

    def calculate_with_retrofit_uvalues(
        self, building: BuildingInput, retrofit: RetrofitInput
    ) -> HWBResult:
        """Calculate HWB with explicit retrofit U-value overrides."""
        original_u = U_VALUES[building.construction_epoch].copy()

        # Wall: add insulation layer (R_new = R_old + thickness/conductivity)
        if retrofit.wall_insulation_cm > 0:
            r_added = (retrofit.wall_insulation_cm / 100.0) / INSULATION_CONDUCTIVITY
            r_original = 1.0 / original_u["AW"]
            original_u["AW"] = 1.0 / (r_original + r_added)

        # Roof: add insulation layer
        if retrofit.roof_insulation_cm > 0:
            r_added = (retrofit.roof_insulation_cm / 100.0) / INSULATION_CONDUCTIVITY
            r_original = 1.0 / original_u["OD"]
            original_u["OD"] = 1.0 / (r_original + r_added)

        # Windows: replace with specified U-value
        if retrofit.window_u_value > 0:
            original_u["FE"] = retrofit.window_u_value

        retrofit_building = self._apply_retrofit(building, retrofit)
        g = G_VALUES[building.construction_epoch]
        return self._calculate_core(retrofit_building, original_u, g)

    # --- core calculation (mirrors Excel Calculations sheet exactly) ---

    def _calculate_core(
        self,
        building: BuildingInput,
        u: dict[str, float],
        g: float,
    ) -> HWBResult:
        """Core HWB calculation with explicit U-values and g-value."""
        b = building

        # --- Geometry (Excel Calculations C2-P2) ---
        # C2: gross storey area
        gross_area = b.length * b.width * b.heated_storeys

        # D2: net storey area = gross * 0.8
        net_area = gross_area * NET_TO_GROSS_RATIO

        # E2: envelope area (all exterior walls incl. windows)
        #     = perimeter * storeys * storey_height
        envelope_area = ((b.length + b.width) * 2) * b.heated_storeys * b.storey_height

        # K2, L2: roof and floor = single storey footprint
        roof_area = b.length * b.width
        floor_area = b.length * b.width

        # O2: adjacent (party) walls
        adjacent_walls = self._adjacent_wall_area(b)

        # F2: window/door total area
        win_door_total = self._window_door_total(b, envelope_area)

        # M2: total walls = envelope - windows
        total_walls = envelope_area - win_door_total

        # N2: external walls = total walls - adjacent walls
        external_walls = total_walls - adjacent_walls

        # G2-J2: window areas by orientation (equal split)
        win_doors = self._window_door_by_orientation(b, win_door_total)

        # P2: net inner volume
        # =D2 * (storey_height - 0.35) * storeys
        # But D2 already has storeys factored in via gross_area
        # Actually: P2 = net_area * (storey_height - 0.35) * storeys / storeys
        # Looking at formula: =D2*(Input!H2-0.35)*Input!G2
        # D2 is already gross*0.8 (which includes storeys multiplication)
        # So P2 = net_area * (storey_height - 0.35)
        # Wait - that multiplies by storeys again. Let me re-check:
        # C2 = E*F*G (length*width*storeys) = gross area INCLUDING storeys
        # D2 = C2*0.8 = net area including all storeys
        # P2 = D2 * (H2-0.35) * G2 = net_area * (height-0.35) * storeys
        # That would double-count storeys since D2 already includes them.
        # Actually looking more carefully: D2 = C2*0.8 where C2 = length*width*storeys
        # So D2 = length*width*storeys*0.8 (total net floor area across all storeys)
        # P2 = D2 * (storey_height - 0.35) * storeys
        # This seems like it might be a volume = net_floor_area_per_storey * height * storeys
        # Let me re-read: P2 = D2*(H2-0.35)*G2
        # If D2 = total net area (all storeys), then this gives too much volume.
        # More likely D2 is meant as net area per storey, and C2 is total gross.
        # Actually C2 = E2*F2*G2 = length*width*storeys IS total gross area.
        # So D2 = total_net_area = total_gross * 0.8
        # And P2 = total_net_area * (storey_height - 0.35) * storeys
        # That DOES double-count storeys.
        # But in the Excel, this is the formula. Let me just follow it faithfully:
        volume = net_area * (b.storey_height - FLOOR_THICKNESS) * b.heated_storeys

        # --- Transmission Heat Loss (Excel AT2-AV2) ---
        # AT2: L_e = U_win*A_win*f_win + U_roof*A_roof*f_roof + U_floor*A_floor*f_floor + U_wall*A_extwall*f_wall
        # f_win = 1, f_roof = 1, f_floor = 0.7, f_wall = 1
        a_win = win_door_total
        l_e = (
            u["FE"] * a_win * 1.0           # AH2*AI2*AJ2
            + u["OD"] * roof_area * 1.0      # AK2*AL2*AM2
            + u["KD"] * floor_area * FLOOR_U_FACTOR  # AN2*AO2*AP2
            + u["AW"] * external_walls * 1.0  # AQ2*AR2*AS2
        )

        # AU2: thermal bridge supplement
        # =MAX(0.2*(0.75-(AT2/(AI2+AL2+AO2+AR2)))*AT2, 0)
        total_area = a_win + roof_area + floor_area + external_walls
        if total_area > 0:
            u_mean = l_e / total_area
            l_psi = max(THERMAL_BRIDGE_FACTOR * (THERMAL_BRIDGE_REFERENCE - u_mean) * l_e, 0.0)
        else:
            l_psi = 0.0

        # AV2: total transmission coefficient
        l_t = l_e + l_psi

        # AW2: transmission heat loss (kWh/a)
        hdd = HEATING_DEGREE_DAYS[b.country]
        q_t = HDD_TO_KWH_FACTOR * l_t * hdd

        # --- Ventilation Heat Loss (Excel BA2-BC2) ---
        # BA2 = P2 (volume)
        # BB2 = 0.34 * 0.4 * BA2
        l_v = AIR_HEAT_CAPACITY * AIR_CHANGE_RATE * volume

        # BC2 = 0.024 * BB2 * AE2
        q_v = HDD_TO_KWH_FACTOR * l_v * hdd

        # --- Internal Gains (Excel BG2) ---
        # BG2 = 0.024 * 3.75 * D2 * AF2
        heating_days = HEATING_DAYS[b.country]
        q_i = HDD_TO_KWH_FACTOR * INTERNAL_GAIN_RATE * net_area * heating_days

        # --- Solar Gains (Excel BU2) ---
        # BT2 = W2 * 0.9 * 0.98  (g_effective)
        g_eff = g * FRAME_FACTOR * DIRT_FACTOR

        # BU2 = (Irr_N*A_N + Irr_E*A_E + Irr_S*A_S + Irr_W*A_W) * F_s * g_eff
        irr = SOLAR_IRRADIANCE[b.country]
        q_s = (
            irr["north"] * win_doors.north
            + irr["east"] * win_doors.east
            + irr["south"] * win_doors.south
            + irr["west"] * win_doors.west
        ) * SHADING_FACTOR * g_eff

        # --- Heating Demand (Excel BY2) ---
        # BY2 = AW2 + BC2 - BG2 - BU2  (no utilisation factor!)
        q_heating = q_t + q_v - q_i - q_s
        # In the Excel, this can go negative (no MAX(0,...) applied)
        # But physically it should be >= 0
        q_heating = max(0.0, q_heating)

        # BZ2: specific = Q_heating / gross_area
        hwb = q_heating / gross_area if gross_area > 0 else 0.0

        # --- Hot Water (Excel CB2) ---
        # CB2 = Input!P2 * 40 * 365 * (4.2/3600) * 45
        # Input!P2 = Calculations!C2/52 = gross_area / 52
        residents = b.effective_residents
        q_hotwater = (
            residents
            * HOT_WATER_LITRES_PER_PERSON_PER_DAY
            * 365
            * HOT_WATER_SPECIFIC_HEAT
            * HOT_WATER_TEMP_RISE_K
        )

        # --- Final Energy ---
        eff = HEATING_SYSTEM_EFFICIENCY[b.heating_system]

        # Hot water system: if electric & separate, use electric efficiency
        if b.hot_water_electric_separate:
            hw_eff = HEATING_SYSTEM_EFFICIENCY[HeatingSystem.ELECTRIC_DIRECT]
        else:
            hw_eff = eff

        final_heating = q_heating / eff
        final_hotwater = q_hotwater / hw_eff
        final_total = final_heating + final_hotwater
        total_kwh_per_m2 = final_total / gross_area if gross_area > 0 else 0.0

        # --- CO2 ---
        co2_heating = final_heating * CO2_FACTOR[b.heating_system]
        if b.hot_water_electric_separate:
            co2_hotwater = final_hotwater * CO2_FACTOR[HeatingSystem.ELECTRIC_DIRECT]
        else:
            co2_hotwater = final_hotwater * CO2_FACTOR[b.heating_system]
        co2_total = co2_heating + co2_hotwater

        return HWBResult(
            floor_area=gross_area,
            heated_volume=volume,
            envelope_area=envelope_area,
            transmission_heat_loss=l_t,
            ventilation_heat_loss=l_v,
            solar_gains=q_s,
            internal_gains=q_i,
            heating_demand_kwh=q_heating,
            hwb=hwb,
            final_energy_kwh=final_heating,
            final_energy_kwh_per_m2=final_heating / gross_area if gross_area > 0 else 0.0,
            hot_water_kwh=q_hotwater,
            total_kwh_per_m2=total_kwh_per_m2,
            co2_kg=co2_total,
            co2_kg_per_m2=co2_total / gross_area if gross_area > 0 else 0.0,
        )

    # --- private helpers ---

    def _adjacent_wall_area(self, b: BuildingInput) -> float:
        """Calculate party wall area (O2 in Excel).

        O2 formula:
        Semi-D (Length adj): length * storeys * storey_height
        Semi-D (Width adj):  width * storeys * storey_height
        Terraced (Length adj): length * storeys * storey_height * 2
        Terraced (Width adj):  width * storeys * storey_height * 2
        Detached: 0
        """
        h = b.heated_storeys * b.storey_height
        if b.building_type == BuildingType.SEMI_D_LENGTH:
            return b.length * h
        elif b.building_type == BuildingType.SEMI_D_WIDTH:
            return b.width * h
        elif b.building_type == BuildingType.TERRACED_LENGTH:
            return b.length * h * 2
        elif b.building_type == BuildingType.TERRACED_WIDTH:
            return b.width * h * 2
        else:  # DETACHED
            return 0.0

    def _window_door_total(self, b: BuildingInput, envelope_area: float) -> float:
        """Calculate total window/door area (F2 / Input!J2).

        J2 = envelope_area * fraction (0.15/0.14/0.13 by building type)
        """
        if b.window_door_areas is not None:
            wd = b.window_door_areas
            return wd.north + wd.east + wd.south + wd.west + wd.doors

        frac = WINDOW_AREA_FRACTION[b.building_type]
        return envelope_area * frac

    def _window_door_by_orientation(
        self, b: BuildingInput, total: float
    ) -> WindowDoorAreas:
        """Split window area equally across 4 orientations (K2-N2).

        K2 = J2 * (1/4), L2 = J2 * (1/4), M2 = J2 * (1/4), N2 = J2 * (1/4)
        """
        if b.window_door_areas is not None:
            return b.window_door_areas

        quarter = total / 4.0
        return WindowDoorAreas(
            north=quarter,
            east=quarter,
            south=quarter,
            west=quarter,
            doors=0.0,  # doors are included in the total split equally
        )

    def _apply_retrofit(
        self, b: BuildingInput, r: RetrofitInput
    ) -> BuildingInput:
        """Create a modified BuildingInput reflecting retrofit heating system changes."""
        data = b.model_dump()
        if r.heating_system_after is not None:
            data["heating_system"] = r.heating_system_after
        data["hot_water_electric_separate"] = r.hot_water_electric_separate_after
        return BuildingInput(**data)
