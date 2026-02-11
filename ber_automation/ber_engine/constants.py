"""
Constants for the HWB calculation engine.

All lookup tables ported from the Excel tool "Building Assessment using Google Maps
and Google Street View" by Benjamin Kaiser (MTU, Jan 2025).

Values extracted directly from the Excel Data sheet and Energy+CO2 Calculations sheet.
U-values sourced from Austrian OIB guidelines via the Sources PDF.
Climate data from degreedays.net (HDD) and PHPP software (solar irradiance, heating days).
CO2 factors from SEAI conversion factors.
"""

from __future__ import annotations

from ber_automation.models import (
    BuildingType,
    ConstructionEpoch,
    Country,
    HeatingSystem,
)

# ---------------------------------------------------------------------------
# U-VALUES by construction epoch (W/m²K)
# From Excel Data sheet rows 9-13, columns B-E
# Columns: B=U_Window, C=U_Roof, D=U_Floor, E=U_Wall
# Our keys: FE=windows, OD=roof, KD=floor, AW=external wall
# ---------------------------------------------------------------------------
U_VALUES: dict[ConstructionEpoch, dict[str, float]] = {
    ConstructionEpoch.BEFORE_1980: {
        "KD": 1.35,    # D13: floor
        "OD": 0.65,    # C13: roof
        "AW": 1.20,    # E13: external wall
        "FE": 3.00,    # B13: windows
    },
    ConstructionEpoch.EPOCH_1980_1990: {
        "KD": 0.75,    # D12: =(0.8+0.7)/2
        "OD": 0.275,   # C12: =(0.3+0.25)/2
        "AW": 0.60,    # E12: =(0.7+0.5)/2
        "FE": 2.50,    # B12: =(2.5+2.5)/2
    },
    ConstructionEpoch.EPOCH_1990_2000: {
        "KD": 0.60,    # D11: =(0.5+0.7)/2
        "OD": 0.235,   # C11: =(0.22+0.25)/2
        "AW": 0.45,    # E11: =(0.4+0.5)/2
        "FE": 2.15,    # B11: =(1.8+2.5)/2
    },
    ConstructionEpoch.EPOCH_2000_2010: {
        "KD": 0.40,    # D10
        "OD": 0.20,    # C10
        "AW": 0.35,    # E10
        "FE": 1.40,    # B10
    },
    ConstructionEpoch.AFTER_2010: {
        "KD": 0.25,    # D9
        "OD": 0.20,    # C9
        "AW": 0.22,    # E9
        "FE": 1.00,    # B9
    },
}

# ---------------------------------------------------------------------------
# G-VALUES (solar energy transmittance) by epoch
# From Excel Data sheet, column G, rows 9-13
# ---------------------------------------------------------------------------
G_VALUES: dict[ConstructionEpoch, float] = {
    ConstructionEpoch.BEFORE_1980: 0.81,      # G13
    ConstructionEpoch.EPOCH_1980_1990: 0.70,   # G12
    ConstructionEpoch.EPOCH_1990_2000: 0.65,   # G11
    ConstructionEpoch.EPOCH_2000_2010: 0.585,  # G10
    ConstructionEpoch.AFTER_2010: 0.465,       # G9
}

# ---------------------------------------------------------------------------
# HEATING DEGREE DAYS (base 15.5°C) by country/region
# From Excel Data sheet, column C, rows 16-22
# Source: degreedays.net (2022)
# ---------------------------------------------------------------------------
HEATING_DEGREE_DAYS: dict[Country, float] = {
    Country.IRELAND: 2149.1,        # C21 (Mullingar)
    Country.FRANCE: 1461.9999999999995,  # C17 (Le Mans, NW)
    Country.GERMANY: 2157.1,        # C19 (Paderborn, NW)
    Country.BELGIUM: 1825.5,        # C16 (Beauvechain)
    Country.NETHERLANDS: 1921.3,    # C22 (Herwijnen)
    Country.AUSTRIA: 3400.0,        # placeholder - not in Excel data
}

# ---------------------------------------------------------------------------
# HEATING DAYS per year by country
# From Excel Data sheet, column F, rows 16-22
# Source: PHPP software
# ---------------------------------------------------------------------------
HEATING_DAYS: dict[Country, float] = {
    Country.IRELAND: 219.0,    # F21 (Birr)
    Country.FRANCE: 187.0,     # F17 (Rennes, NW)
    Country.GERMANY: 211.0,    # F19 (Munster, NW)
    Country.BELGIUM: 209.0,    # F16 (Ukkel)
    Country.NETHERLANDS: 212.0, # F22 (De Bilt)
    Country.AUSTRIA: 260.0,    # placeholder
}

# ---------------------------------------------------------------------------
# SOLAR IRRADIANCE during heating season by orientation (kWh/m²)
# From Excel Data sheet, columns G-J, rows 16-22
# Source: PHPP software
# ---------------------------------------------------------------------------
SOLAR_IRRADIANCE: dict[Country, dict[str, float]] = {
    Country.IRELAND: {
        "north": 102.0,   # G21
        "east": 227.0,    # H21
        "south": 423.0,   # I21
        "west": 240.0,    # J21
    },
    Country.FRANCE: {
        "north": 95.0,    # G17 (NW)
        "east": 207.0,    # H17
        "south": 412.0,   # I17
        "west": 219.0,    # J17
    },
    Country.GERMANY: {
        "north": 133.0,   # G19 (NW)
        "east": 215.0,    # H19
        "south": 331.0,   # I19
        "west": 207.0,    # J19
    },
    Country.BELGIUM: {
        "north": 160.0,   # G16
        "east": 222.0,    # H16
        "south": 321.0,   # I16
        "west": 225.0,    # J16
    },
    Country.NETHERLANDS: {
        "north": 162.0,   # G22
        "east": 239.0,    # H22
        "south": 365.0,   # I22
        "west": 243.0,    # J22
    },
    Country.AUSTRIA: {
        "north": 90.0,
        "east": 150.0,
        "south": 290.0,
        "west": 150.0,
    },
}

# ---------------------------------------------------------------------------
# HEATING SYSTEM EFFICIENCIES / SCOP
# From Excel Energy+CO2 Calculations sheet, column K
# For heat pumps, this is the SCOP (>1), so final < useful
# ---------------------------------------------------------------------------
HEATING_SYSTEM_EFFICIENCY: dict[HeatingSystem, float] = {
    HeatingSystem.OIL_BOILER: 0.85,       # K4
    HeatingSystem.GAS_BOILER: 0.90,       # K5
    HeatingSystem.BIOMASS: 0.875,         # K6
    HeatingSystem.ELECTRIC_DIRECT: 0.99,  # K7
    HeatingSystem.HEAT_PUMP_AIR: 3.50,    # K8 (SCOP)
    HeatingSystem.HEAT_PUMP_GROUND: 4.50, # K9 (SCOP)
    HeatingSystem.HEAT_PUMP_WATER: 4.50,  # K10 (SCOP)
    HeatingSystem.DISTRICT_HEATING: 0.95, # not in Excel, reasonable default
}

# ---------------------------------------------------------------------------
# PRIMARY ENERGY FACTORS (converts final energy to primary energy)
# Source: SEAI / EU conventions
# (Not explicitly in the Excel but needed for BER rating)
# ---------------------------------------------------------------------------
PRIMARY_ENERGY_FACTOR: dict[HeatingSystem, float] = {
    HeatingSystem.OIL_BOILER: 1.10,
    HeatingSystem.GAS_BOILER: 1.10,
    HeatingSystem.BIOMASS: 1.10,
    HeatingSystem.ELECTRIC_DIRECT: 2.08,
    HeatingSystem.HEAT_PUMP_AIR: 2.08,
    HeatingSystem.HEAT_PUMP_GROUND: 2.08,
    HeatingSystem.HEAT_PUMP_WATER: 2.08,
    HeatingSystem.DISTRICT_HEATING: 1.10,
}

# ---------------------------------------------------------------------------
# CO2 EMISSION FACTORS (t CO2 per kWh final energy)
# From Excel Energy+CO2 Calculations sheet, column L
# Note: Excel uses tonnes, we store as tonnes for consistency
# ---------------------------------------------------------------------------
CO2_FACTOR_TONNES: dict[HeatingSystem, float] = {
    HeatingSystem.OIL_BOILER: 263.9e-6,           # L4: 263.9*10^-6
    HeatingSystem.GAS_BOILER: (184 + 204) / 2e6,  # L5: (184+204)/2*10^-6 = 194e-6
    HeatingSystem.BIOMASS: 0.0,                    # L6: 0
    HeatingSystem.ELECTRIC_DIRECT: 210e-6,         # L7: 210*10^-6
    HeatingSystem.HEAT_PUMP_AIR: 210e-6,           # L8: 210*10^-6
    HeatingSystem.HEAT_PUMP_GROUND: 210e-6,        # L9: 210*10^-6
    HeatingSystem.HEAT_PUMP_WATER: 210e-6,         # L10: 210*10^-6
    HeatingSystem.DISTRICT_HEATING: 180e-6,        # not in Excel
}

# Convenience: kg CO2 per kWh (multiply tonnes by 1000)
CO2_FACTOR: dict[HeatingSystem, float] = {
    k: v * 1000.0 for k, v in CO2_FACTOR_TONNES.items()
}

# ---------------------------------------------------------------------------
# DEFAULT WINDOW/DOOR AREA as fraction of ENVELOPE area (exterior walls)
# by building type
# From Excel Input!J2 formula:
#   Detached: Calculations!E2 * 0.15
#   Semi-D: Calculations!E2 * 0.14
#   Terraced: Calculations!E2 * 0.13
# where Calculations!E2 = envelope area (exterior walls + windows)
# ---------------------------------------------------------------------------
WINDOW_AREA_FRACTION: dict[BuildingType, float] = {
    BuildingType.DETACHED: 0.15,
    BuildingType.SEMI_D_LENGTH: 0.14,
    BuildingType.SEMI_D_WIDTH: 0.14,
    BuildingType.TERRACED_LENGTH: 0.13,
    BuildingType.TERRACED_WIDTH: 0.13,
}

# ---------------------------------------------------------------------------
# HOT WATER DEMAND
# From Excel CB2: =Input!P2 * 40 * 365 * (4.2/3600) * 45
# This is: residents * 40 litres/day * 365 days * (4.2 kJ/kg·K / 3600 s) * 45K temp rise
# = residents * 40 * 365 * 0.001167 * 45
# = residents * 765.45 kWh/year
# ---------------------------------------------------------------------------
HOT_WATER_LITRES_PER_PERSON_PER_DAY: float = 40.0
HOT_WATER_TEMP_RISE_K: float = 45.0
HOT_WATER_SPECIFIC_HEAT: float = 4.2 / 3600.0  # kWh/(kg·K)

# ---------------------------------------------------------------------------
# INSULATION CONDUCTIVITY for retrofit calculations (W/mK)
# ---------------------------------------------------------------------------
INSULATION_CONDUCTIVITY: float = 0.035  # typical EPS/mineral wool

# ---------------------------------------------------------------------------
# SOLAR GAIN FACTORS (from Excel Calculations sheet)
# BT2: =W2*0.9*0.98 → g_effective = g_value * 0.9 (frame factor) * 0.98 (dirt factor)
# BS2: 0.75 → shading factor F_s
# ---------------------------------------------------------------------------
FRAME_FACTOR: float = 0.9     # fraction of window that is glazing
DIRT_FACTOR: float = 0.98     # correction for dirt on glazing
SHADING_FACTOR: float = 0.75  # F_s, shading reduction (Excel BS2)

# ---------------------------------------------------------------------------
# VENTILATION (from Excel Calculations sheet)
# BB2: =0.34 * 0.4 * BA2  → air change rate = 0.4 h⁻¹
# ---------------------------------------------------------------------------
AIR_HEAT_CAPACITY: float = 0.34  # Wh/(m³·K)
AIR_CHANGE_RATE: float = 0.4     # h⁻¹ (Excel uses 0.4, not 0.5)

# ---------------------------------------------------------------------------
# INTERNAL GAINS (from Excel Calculations sheet)
# BG2: =0.024 * 3.75 * D2 * AF2
# where D2 = net storey area (0.8 * gross), AF2 = heating days
# So internal gain rate = 3.75 W/m² (of NET area)
# and 0.024 = 24h/1000 kWh conversion factor
# ---------------------------------------------------------------------------
INTERNAL_GAIN_RATE: float = 3.75  # W/m² of net floor area

# ---------------------------------------------------------------------------
# AREA FACTORS (from Excel Calculations sheet)
# D2: =C2*0.8 → net = 0.8 × gross
# P2: =D2*(Input!H2-0.35)*Input!G2 → volume uses (storey_height - 0.35)
# AP2: 0.7 → floor U-value reduction factor (ground contact)
# ---------------------------------------------------------------------------
NET_TO_GROSS_RATIO: float = 0.8
FLOOR_THICKNESS: float = 0.35   # meters deducted from storey height for volume
FLOOR_U_FACTOR: float = 0.7     # f_Floor reduction factor (ground contact)

# ---------------------------------------------------------------------------
# THERMAL BRIDGE CORRECTION (from Excel Calculations sheet)
# AU2: =MAX(0.2*(0.75-(AT2/(AI2+AL2+AO2+AR2)))*AT2, 0)
# L_psi = max(0.2 × (0.75 - U_mean) × L_e, 0)
# where U_mean = L_e / total_area and L_e is the basic transmission coefficient
# ---------------------------------------------------------------------------
THERMAL_BRIDGE_REFERENCE: float = 0.75  # reference U-value for thermal bridges
THERMAL_BRIDGE_FACTOR: float = 0.2      # scaling factor

# ---------------------------------------------------------------------------
# TRANSMISSION HEAT LOSS (from Excel Calculations sheet)
# AW2: =0.024 * AV2 * AE2  → Q_t = 0.024 × L_t × HDD
# where 0.024 = 24/1000 (hours to kWh conversion)
# ---------------------------------------------------------------------------
HDD_TO_KWH_FACTOR: float = 0.024  # = 24h / 1000

# ---------------------------------------------------------------------------
# BER RATING SCALE (kWh/m²/year thresholds)
# Based on Irish BER scale
# ---------------------------------------------------------------------------
BER_BANDS: list[tuple[str, float, str]] = [
    # (band, upper_threshold_inclusive, hex_color)
    ("A1",  25.0,  "#00A651"),
    ("A2",  50.0,  "#4DB848"),
    ("A3",  75.0,  "#8CC63F"),
    ("B1", 100.0,  "#BFD730"),
    ("B2", 125.0,  "#FFF200"),
    ("B3", 150.0,  "#FFC20E"),
    ("C1", 175.0,  "#F99D1C"),
    ("C2", 200.0,  "#F47920"),
    ("C3", 225.0,  "#EF4136"),
    ("D1", 260.0,  "#ED1C24"),
    ("D2", 300.0,  "#C1272D"),
    ("E1", 340.0,  "#A1232B"),
    ("E2", 380.0,  "#8B1A29"),
    ("F",  450.0,  "#6D1A27"),
    ("G",  float("inf"), "#4A1525"),
]
