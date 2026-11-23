"""
What went into a BER calculation, where each value came from, and how the results follow.

``calculation_inputs()`` lists every value the calculator used for a building: the ones read
from the images or the census, the presets from the Kaiser Excel tool, and any the user
changed. ``energy_formulas()`` writes out each result's formula with the building's numbers.
Both are for display (the app); neither changes the calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from ber_automation.ber_engine.calculator import _co2_factor, _pef, resolve_presets
from ber_automation.ber_engine.constants import (
    AIR_HEAT_CAPACITY,
    DIRT_FACTOR,
    FLOOR_THICKNESS,
    FLOOR_U_FACTOR,
    FRAME_FACTOR,
    HDD_TO_KWH_FACTOR,
    HEATING_DAYS,
    HEATING_DEGREE_DAYS,
    HOT_WATER_LITRES_PER_PERSON_PER_DAY,
    HOT_WATER_TEMP_RISE_K,
    NET_TO_GROSS_RATIO,
    SHADING_FACTOR,
    SOLAR_IRRADIANCE,
    THERMAL_BRIDGE_FACTOR,
    THERMAL_BRIDGE_REFERENCE,
)
from ber_automation.models import (
    BERResult,
    BuildingInput,
    BuildingType,
    ConstructionEpoch,
)

# Where a value came from
IMAGES, CENSUS, PRESET, YOU, CLIMATE = "images", "census", "preset", "you", "climate"

ORIGIN_LABELS: dict[str, str] = {
    IMAGES: "From the images",
    CENSUS: "From the census",
    PRESET: "Preset",
    YOU: "Set by you",
    CLIMATE: "Country climate data",
}

# Pipeline source names (PipelineResult.*_source) → origin
_PIPELINE_SOURCES: dict[str, str] = {
    "satellite": IMAGES,
    "streetview": IMAGES,
    "census": CENSUS,
    "census_urban": CENSUS,
    "override": YOU,
    "default": PRESET,
}

EXCEL = "Kaiser Excel tool (MTU, 2025)"

_ERA_TEXT: dict[ConstructionEpoch, str] = {
    ConstructionEpoch.BEFORE_1980: "before 1980",
    ConstructionEpoch.EPOCH_1980_1990: "1980–1990",
    ConstructionEpoch.EPOCH_1990_2000: "1990–2000",
    ConstructionEpoch.EPOCH_2000_2010: "2000–2010",
    ConstructionEpoch.AFTER_2010: "after 2010",
}

_TYPE_TEXT: dict[BuildingType, str] = {
    BuildingType.DETACHED: "detached",
    BuildingType.SEMI_D_LENGTH: "semi-detached",
    BuildingType.SEMI_D_WIDTH: "semi-detached",
    BuildingType.TERRACED_LENGTH: "terraced",
    BuildingType.TERRACED_WIDTH: "terraced",
}

# Plain-language meaning of each editable preset, shared by the inputs table and the editor
PRESET_HELP: dict[str, str] = {
    "u_window": "Heat lost through 1 m² of window for each degree between inside and outside.",
    "u_wall": "Heat lost through 1 m² of outer wall per degree of temperature difference.",
    "u_roof": "Heat lost through 1 m² of roof per degree of temperature difference.",
    "u_floor": "Heat lost through 1 m² of ground floor per degree (reduced by 0.7 for ground contact).",
    "g_value": "Share of the sun's energy that passes through the glass.",
    "window_share": "Window and door area as a share of the outer wall area (walls + windows).",
    "air_change_rate": "How many times per hour the air in the home is replaced by outside air.",
    "internal_gain_w_m2": (
        "Heat given off inside the home by people, cooking, appliances and lighting, "
        "per m² of net floor area. It reduces the heat the heating system must supply."
    ),
    "heating_efficiency": (
        "Useful heat delivered per unit of fuel or electricity bought (above 1 for heat pumps: SCOP)."
    ),
}

PRESET_NAMES: dict[str, tuple[str, str]] = {
    "u_window": ("Window U-value", "W/m²K"),
    "u_wall": ("Wall U-value", "W/m²K"),
    "u_roof": ("Roof U-value", "W/m²K"),
    "u_floor": ("Floor U-value", "W/m²K"),
    "g_value": ("Glazing g-value", ""),
    "window_share": ("Window share of wall area", ""),
    "air_change_rate": ("Air change rate", "per hour"),
    "internal_gain_w_m2": ("Internal gains", "W/m²"),
    "heating_efficiency": ("Heating efficiency", ""),
}


@dataclass
class InputRow:
    group: str
    name: str
    value: Union[float, str]
    unit: str
    origin: str           # one of ORIGIN_LABELS
    source: str           # where the value comes from, in words
    key: str = ""         # CalculationOverrides field when the user can change it


def _origin(source: str | None, manual: bool) -> str:
    if manual:
        return YOU
    return _PIPELINE_SOURCES.get(source or "default", PRESET)


def _preset_source(key: str, b: BuildingInput) -> str:
    era = _ERA_TEXT[b.construction_epoch]
    if key in ("u_window", "u_wall", "u_roof", "u_floor", "g_value"):
        return f"Preset for homes built {era}: {EXCEL}, Data sheet, from Austrian OIB guidance"
    if key == "window_share":
        return (f"Preset for a {_TYPE_TEXT[b.building_type]} house (15 % detached, 14 % semi-detached, "
                f"13 % terraced): {EXCEL}, Input!J2")
    if key == "air_change_rate":
        return f"Preset: {EXCEL}, Calculations!BB2"
    if key == "internal_gain_w_m2":
        return f"Preset (people, cooking, appliances, lighting): {EXCEL}, Calculations!BG2"
    if key == "heating_efficiency":
        heating = b.heating_system.value.replace("_", " ")
        return f"Preset for a {heating}: {EXCEL}, Energy+CO2 sheet, column K"
    return ""


def calculation_inputs(
    building: BuildingInput,
    sources: dict[str, str | None] | None = None,
) -> list[InputRow]:
    """Every value the calculation uses for *building*, with where it came from.

    *sources* holds the pipeline's source names for ``dimensions``, ``building_type``,
    ``storeys``, ``epoch`` and ``heating`` (e.g. ``PipelineResult.epoch_source``). Without
    it (manual input) those values count as set by the user.
    """
    b = building
    manual = sources is None
    src = sources or {}
    p = resolve_presets(b)
    set_by_user = (
        {k for k, v in b.overrides.model_dump().items() if v is not None} if b.overrides else set()
    )
    rows: list[InputRow] = []

    # --- Geometry and classification ---
    dims = _origin(src.get("dimensions"), manual)
    dims_note = {
        IMAGES: "Footprint measured on the satellite image",
        PRESET: "Footprint not measured with enough confidence: typical house 10 × 8 m",
        YOU: "Entered by you",
    }[dims if dims in (IMAGES, PRESET) else YOU]
    rows += [
        InputRow("Geometry", "Length", round(b.length, 1), "m", dims, dims_note),
        InputRow("Geometry", "Width", round(b.width, 1), "m", dims, dims_note),
    ]
    storeys = _origin(src.get("storeys"), manual)
    rows.append(InputRow(
        "Geometry", "Heated storeys", b.heated_storeys, "", storeys,
        {IMAGES: "Counted in the Street View images", PRESET: "Preset: 2 storeys"}.get(storeys, "Entered by you"),
    ))
    height_preset = b.storey_height == 3.0 and not manual
    rows.append(InputRow(
        "Geometry", "Storey height", b.storey_height, "m", PRESET if height_preset else YOU,
        f"Preset: {EXCEL}, Input!H2" if height_preset else "Entered by you",
    ))
    btype = _origin(src.get("building_type"), manual)
    rows.append(InputRow(
        "Geometry", "Dwelling type", _TYPE_TEXT[b.building_type], "", btype,
        {IMAGES: "Seen in the Street View and satellite images",
         PRESET: "Preset: detached"}.get(btype, "Entered by you"),
    ))
    era = _origin(src.get("epoch"), manual)
    rows.append(InputRow(
        "Geometry", "Construction era", _ERA_TEXT[b.construction_epoch], "", era,
        {IMAGES: "Read from the Street View images", CENSUS: "Census 2022: commonest era in the Small Area",
         PRESET: "Preset: before 1980"}.get(era, "Entered by you"),
    ))

    # --- Fabric, ventilation, gains: the editable presets ---
    for group, keys in (
        ("Fabric", ("u_window", "u_wall", "u_roof", "u_floor", "g_value", "window_share")),
        ("Ventilation and gains", ("air_change_rate", "internal_gain_w_m2")),
    ):
        for key in keys:
            name, unit = PRESET_NAMES[key]
            if key == "window_share" and b.window_door_areas is not None:
                rows.append(InputRow(group, "Window and door area",
                                     round(sum(b.window_door_areas.model_dump().values()), 1),
                                     "m²", YOU, "Entered by you"))
                continue
            who = YOU if key in set_by_user else PRESET
            rows.append(InputRow(
                group, name, round(p[key], 3), unit, who,
                "Changed by you" if who == YOU else _preset_source(key, b), key,
            ))
    rows += [
        InputRow("Ventilation and gains", "Window shading factor", SHADING_FACTOR, "", PRESET,
                 f"Preset: {EXCEL}, Calculations!BS2"),
        InputRow("Ventilation and gains", "Window frame share of glass", FRAME_FACTOR, "", PRESET,
                 f"Preset: {EXCEL}, Calculations!BT2"),
        InputRow("Ventilation and gains", "Dirt on glass factor", DIRT_FACTOR, "", PRESET,
                 f"Preset: {EXCEL}, Calculations!BT2"),
    ]

    # --- Climate (country) ---
    irr = SOLAR_IRRADIANCE[b.country]
    country = b.country.value.title()
    rows += [
        InputRow("Climate", "Heating degree days", HEATING_DEGREE_DAYS[b.country], "K·day", CLIMATE,
                 f"{country}, base 15.5 °C: degreedays.net (2022), via {EXCEL}"),
        InputRow("Climate", "Heating days", HEATING_DAYS[b.country], "days/yr", CLIMATE,
                 f"{country}: PHPP, via {EXCEL}"),
        InputRow("Climate", "Solar radiation S / E / W / N",
                 f"{irr['south']:.0f} / {irr['east']:.0f} / {irr['west']:.0f} / {irr['north']:.0f}",
                 "kWh/m² per heating season", CLIMATE, f"{country}: PHPP, via {EXCEL}"),
    ]

    # --- Heating and hot water ---
    heat = _origin(src.get("heating"), manual)
    rows.append(InputRow(
        "Heating", "Heating system", b.heating_system.value.replace("_", " "), "", heat,
        {IMAGES: "Seen in the Street View images (flue, tank, heat pump unit)",
         CENSUS: "Census 2022: commonest fuel in the area",
         PRESET: "Preset: gas boiler"}.get(heat, "Entered by you"),
    ))
    name, unit = PRESET_NAMES["heating_efficiency"]
    who = YOU if "heating_efficiency" in set_by_user else PRESET
    rows.append(InputRow("Heating", name, round(p["heating_efficiency"], 3), unit, who,
                         "Changed by you" if who == YOU else _preset_source("heating_efficiency", b),
                         "heating_efficiency"))
    rows += [
        InputRow("Heating", "Primary energy factor", _pef(b.heating_system, b.country), "", PRESET,
                 "SEAI / national EPBD values"),
        InputRow("Heating", "CO₂ factor", round(_co2_factor(b.heating_system, b.country), 4),
                 "kg/kWh", PRESET, "SEAI conversion factors; national grid for electricity"),
        InputRow("Heating", "Residents", round(b.effective_residents, 1), "",
                 YOU if b.residents is not None else PRESET,
                 "Entered by you" if b.residents is not None
                 else f"Floor area ÷ 52 m² per person: {EXCEL}, Input!P2"),
        InputRow("Heating", "Hot water use", HOT_WATER_LITRES_PER_PERSON_PER_DAY, "litres/person/day",
                 PRESET, f"Preset, heated by {HOT_WATER_TEMP_RISE_K:.0f} K: {EXCEL}, Calculations!CB2"),
    ]
    return rows


@dataclass
class Formula:
    name: str
    meaning: str
    formula: str      # with the building's numbers put in
    result: str


def _n(x: float, digits: int = 0) -> str:
    return f"{x:,.{digits}f}"


def energy_formulas(ber: BERResult) -> list[Formula]:
    """Each result of the calculation as its formula with this building's numbers."""
    hw = ber.hwb_result
    b = ber.building_input
    p = hw.presets or resolve_presets(b)
    pef = _pef(b.heating_system, b.country)
    co2 = _co2_factor(b.heating_system, b.country)
    g_eff = p["g_value"] * FRAME_FACTOR * DIRT_FACTOR
    floor_part = p["u_floor"] * hw.ground_floor_area * FLOOR_U_FACTOR
    return [
        Formula(
            "Transmission loss",
            "Heat escaping through walls, roof, floor and windows over the heating season.",
            (f"L_e = U_win×A_win + U_roof×A_roof + 0.7×U_floor×A_floor + U_wall×A_wall"
             f" = {p['u_window']:g}×{_n(hw.window_area, 1)} + {p['u_roof']:g}×{_n(hw.roof_area, 1)}"
             f" + {_n(floor_part, 1)} + {p['u_wall']:g}×{_n(hw.external_wall_area, 1)}"
             f" = {_n(hw.basic_transmission_w_k, 1)} W/K; thermal bridges"
             f" max({THERMAL_BRIDGE_FACTOR}×({THERMAL_BRIDGE_REFERENCE} − mean U)×L_e, 0)"
             f" = {_n(hw.thermal_bridge_w_k, 1)} W/K; Q_t = {HDD_TO_KWH_FACTOR} × L_t × HDD"
             f" = {HDD_TO_KWH_FACTOR} × {_n(hw.transmission_heat_loss, 1)} × {_n(hw.hdd, 1)}"),
            f"{_n(hw.transmission_loss_kwh)} kWh/yr",
        ),
        Formula(
            "Ventilation loss",
            "Heat carried away by outside air replacing warm inside air.",
            (f"Volume = net area × (storey height − {FLOOR_THICKNESS}) × storeys"
             f" = {_n(hw.heated_volume)} m³; L_v = {AIR_HEAT_CAPACITY} × {p['air_change_rate']}"
             f" × volume = {_n(hw.ventilation_heat_loss, 1)} W/K; Q_v = {HDD_TO_KWH_FACTOR} × L_v × HDD"),
            f"{_n(hw.ventilation_loss_kwh)} kWh/yr",
        ),
        Formula(
            "Internal gains",
            PRESET_HELP["internal_gain_w_m2"],
            (f"Q_i = {HDD_TO_KWH_FACTOR} × {p['internal_gain_w_m2']} W/m² × net area"
             f" {_n(hw.net_area, 1)} m² ({NET_TO_GROSS_RATIO} × gross) × {_n(hw.heating_days)} heating days"),
            f"{_n(hw.internal_gains)} kWh/yr",
        ),
        Formula(
            "Solar gains",
            "Sunshine through the windows during the heating season.",
            (f"Q_s = Σ(radiation × window area, window area split equally N/E/S/W)"
             f" × shading {SHADING_FACTOR} × g_eff {g_eff:.3f}"
             f" (g {p['g_value']} × frame {FRAME_FACTOR} × dirt {DIRT_FACTOR})"),
            f"{_n(hw.solar_gains)} kWh/yr",
        ),
        Formula(
            "Heating demand",
            "Heat the heating system must deliver: losses not covered by the free gains.",
            (f"Q_h = Q_t + Q_v − Q_i − Q_s = {_n(hw.transmission_loss_kwh)} + {_n(hw.ventilation_loss_kwh)}"
             f" − {_n(hw.internal_gains)} − {_n(hw.solar_gains)} (not below 0)"),
            f"{_n(hw.heating_demand_kwh)} kWh/yr",
        ),
        Formula(
            "HWB",
            "Heating demand per m² of floor area, so homes of different sizes can be compared.",
            f"HWB = Q_h ÷ gross floor area = {_n(hw.heating_demand_kwh)} ÷ {_n(hw.floor_area, 1)} m²",
            f"{_n(hw.hwb, 1)} kWh/m²/yr",
        ),
        Formula(
            "Hot water",
            "Heat to warm the household's hot water.",
            (f"Q_w = residents {_n(hw.residents, 1)} × {HOT_WATER_LITRES_PER_PERSON_PER_DAY:.0f} L/day"
             f" × 365 × (4.2/3600) kWh/(kg·K) × {HOT_WATER_TEMP_RISE_K:.0f} K"),
            f"{_n(hw.hot_water_kwh)} kWh/yr",
        ),
        Formula(
            "Delivered energy",
            "Fuel or electricity bought for heating and hot water.",
            (f"Heating {_n(hw.heating_demand_kwh)} ÷ efficiency {p['heating_efficiency']}"
             f" = {_n(hw.final_energy_kwh)} kWh/yr; hot water {_n(hw.hot_water_final_kwh)} kWh/yr;"
             f" per m² = total ÷ {_n(hw.floor_area, 1)} m²"),
            f"{_n(hw.total_kwh_per_m2, 1)} kWh/m²/yr",
        ),
        Formula(
            "Primary energy (the BER)",
            "Delivered energy including the energy used to produce and deliver it.",
            f"{_n(hw.total_kwh_per_m2, 1)} kWh/m²/yr × primary energy factor {pef}",
            f"{_n(ber.kwh_per_m2, 1)} kWh/m²/yr → band {ber.ber_band}",
        ),
        Formula(
            "CO₂",
            "Emissions from the delivered energy.",
            f"Delivered energy × CO₂ factor {co2:.4f} kg/kWh ÷ floor area",
            f"{_n(hw.co2_kg_per_m2, 1)} kg/m²/yr ({_n(hw.co2_kg)} kg/yr)",
        ),
    ]


__all__ = [
    "Formula", "InputRow", "ORIGIN_LABELS", "PRESET_HELP", "PRESET_NAMES",
    "calculation_inputs", "energy_formulas",
]
