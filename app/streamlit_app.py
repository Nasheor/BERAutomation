"""Streamlit UI for BER Automation pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.ber_engine.constants import BER_BANDS
from ber_automation.ber_engine.rating import get_ber_band, get_native_epc
from ber_automation.models import (
    BERResult,
    BuildingInput,
    BuildingType,
    ConstructionEpoch,
    Country,
    HeatingSystem,
    HWBResult,
    RetrofitInput,
)
from ber_automation.pipeline import BERPipeline

# ---------------------------------------------------------------------------
# Human-readable label dictionaries
# ---------------------------------------------------------------------------
BUILDING_TYPE_LABELS: dict[str, str] = {
    BuildingType.DETACHED.value: "Detached",
    BuildingType.SEMI_D_LENGTH.value: "Semi-Detached (Length Adjoining)",
    BuildingType.SEMI_D_WIDTH.value: "Semi-Detached (Width Adjoining)",
    BuildingType.TERRACED_LENGTH.value: "Terraced (Length Adjoining)",
    BuildingType.TERRACED_WIDTH.value: "Terraced (Width Adjoining)",
}

EPOCH_LABELS: dict[str, str] = {
    ConstructionEpoch.BEFORE_1980.value: "Before 1980",
    ConstructionEpoch.EPOCH_1980_1990.value: "1980 \u2013 1990",
    ConstructionEpoch.EPOCH_1990_2000.value: "1990 \u2013 2000",
    ConstructionEpoch.EPOCH_2000_2010.value: "2000 \u2013 2010",
    ConstructionEpoch.AFTER_2010.value: "After 2010",
}

HEATING_LABELS: dict[str, str] = {
    HeatingSystem.OIL_BOILER.value: "Oil Boiler",
    HeatingSystem.GAS_BOILER.value: "Gas Boiler",
    HeatingSystem.BIOMASS.value: "Biomass",
    HeatingSystem.ELECTRIC_DIRECT.value: "Electric (Direct)",
    HeatingSystem.HEAT_PUMP_AIR.value: "Heat Pump (Air)",
    HeatingSystem.HEAT_PUMP_GROUND.value: "Heat Pump (Ground)",
    HeatingSystem.HEAT_PUMP_WATER.value: "Heat Pump (Water)",
    HeatingSystem.DISTRICT_HEATING.value: "District Heating",
}

COUNTRY_LABELS: dict[str, str] = {
    Country.IRELAND.value: "Ireland",
    Country.FRANCE.value: "France",
    Country.GERMANY.value: "Germany",
    Country.BELGIUM.value: "Belgium",
    Country.NETHERLANDS.value: "Netherlands",
    Country.LUXEMBOURG.value: "Luxembourg",
    Country.SWITZERLAND.value: "Switzerland",
    Country.AUSTRIA.value: "Austria",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_color_for_bg(hex_color: str) -> str:
    """Return '#FFFFFF' or '#1A1A2E' based on background luminance."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#1A1A2E" if luminance > 150 else "#FFFFFF"


def _run_async(coro):
    """Run an async coroutine from sync Streamlit code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _ber_band_index(band: str) -> int:
    """Return the 0-based index of a BER band in BER_BANDS."""
    for i, (b, _, _) in enumerate(BER_BANDS):
        if b == band:
            return i
    return 0


# ---------------------------------------------------------------------------
# Page config & global CSS
# ---------------------------------------------------------------------------
st.set_page_config(page_title="BER Automation", page_icon="\U0001f3e0", layout="wide")

st.markdown("""
<style>
    /* Card-style metrics */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E0E3E8;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    [data-testid="stMetric"] label {
        color: #6B7280;
        font-size: 0.85rem;
    }

    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #00664E 0%, #004D3A 100%);
    }
    section[data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #E0F0EB !important;
    }
    section[data-testid="stSidebar"] .stRadio label span {
        color: #FFFFFF !important;
    }

    /* Section header accent */
    .section-header {
        border-left: 4px solid #00664E;
        padding-left: 12px;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
    }

    /* Hide default footer & hamburger */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Onboarding cards */
    .onboard-card {
        background: #FFFFFF;
        border: 1px solid #E0E3E8;
        border-radius: 12px;
        padding: 24px 20px;
        text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.05);
        height: 100%;
    }
    .onboard-card .step-num {
        display: inline-block;
        background: #00664E;
        color: white;
        width: 32px; height: 32px;
        border-radius: 50%;
        line-height: 32px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .onboard-card h4 { margin: 8px 0 6px; color: #1A1A2E; }
    .onboard-card p { color: #6B7280; font-size: 0.9rem; margin: 0; }

    /* Larger form labels and inputs in manual-input tabs */
    .stTabs [data-baseweb="tab-panel"] label,
    .stTabs [data-baseweb="tab-panel"] .stMarkdown p {
        font-size: 1rem !important;
    }
    .stTabs [data-baseweb="tab-panel"] input,
    .stTabs [data-baseweb="tab-panel"] [data-baseweb="select"] {
        font-size: 1rem !important;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 1.05rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Branded header
# ---------------------------------------------------------------------------
st.markdown(
    "<h1 style='color:#00664E; margin-bottom:0;'>Building Energy Rating</h1>"
    "<p style='color:#6B7280; font-size:1.05rem; margin-top:4px;'>"
    "Automated BER assessment using satellite imagery, Street View analysis, "
    "and the HWB annual balance method.</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image(Path(__file__).parent.parent / "images" / "circus_logo.jpg", width="stretch")
    st.markdown("### BER Automation")
    st.caption("v1.0")
    mode = st.radio(
        "Mode",
        ["Full Pipeline", "Manual Input"],
        index=1,
        help="**Full Pipeline** geocodes an address, fetches imagery, "
             "runs AI analysis, and calculates the BER automatically. "
             "**Manual Input** lets you enter building details directly.",
    )
    st.divider()
    with st.expander("About this tool"):
        st.markdown(
            "Estimates building energy performance using the HWB annual "
            "heat-balance method for all CIRCUS Interreg NWE partner countries.\n\n"
            "**Data sources**\n"
            "- U-values: OIB / Austrian guidelines\n"
            "- Climate: degreedays.net & PHPP\n"
            "- CO\u2082 factors: national grid operators (2022)\n"
            "- Primary energy factors: national EPBD regulations\n"
            "- Ratings: Irish BER (reference) + native country EPC scale"
        )
    st.caption("\u00a9 2025 BER Automation")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "ber_result" not in st.session_state:
    st.session_state.ber_result = None
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "whatif_history" not in st.session_state:
    st.session_state.whatif_history = []   # list[dict] — one entry per scenario
if "whatif_latest" not in st.session_state:
    st.session_state.whatif_latest = None  # BERResult | None
if "uploaded_satellite" not in st.session_state:
    st.session_state.uploaded_satellite = None  # bytes | None
if "uploaded_sv_images" not in st.session_state:
    st.session_state.uploaded_sv_images = {}    # dict[int, bytes]

# ---------------------------------------------------------------------------
# Plotly helpers
# ---------------------------------------------------------------------------

def _make_energy_breakdown_chart(hw: HWBResult) -> go.Figure:
    """Horizontal bar chart of energy losses vs gains."""
    categories = [
        "Transmission Loss",
        "Ventilation Loss",
        "Solar Gains",
        "Internal Gains",
        "Heating Demand (HWB)",
        "Hot Water",
    ]
    values = [
        hw.transmission_heat_loss,
        hw.ventilation_heat_loss,
        hw.solar_gains,
        hw.internal_gains,
        hw.hwb,
        hw.hot_water_kwh,
    ]
    colors = [
        "#EF4136", "#F47920",  # losses (red-orange)
        "#4DB848", "#8CC63F",  # gains (greens)
        "#F99D1C",             # demand (amber)
        "#00A3E0",             # hot water (blue)
    ]
    units = ["W/K", "W/K", "kWh/yr", "kWh/yr", "kWh/m\u00b2/yr", "kWh/yr"]

    fig = go.Figure(go.Bar(
        x=values,
        y=categories,
        orientation="h",
        marker_color=colors,
        text=[f"{v:,.1f} {u}" for v, u in zip(values, units)],
        textposition="outside",
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=10, r=80, t=10, b=10),
        xaxis_title="",
        yaxis_title="",
        xaxis=dict(showticklabels=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
    )
    return fig


def _make_ber_gauge(band: str, kwh: float) -> go.Figure:
    """BER gauge/dial showing position on the A1\u2013G spectrum."""
    # Build gauge steps from BER_BANDS
    steps = []
    prev = 0
    for b, threshold, color in BER_BANDS:
        upper = min(threshold, 500)
        steps.append(dict(range=[prev, upper], color=color))
        prev = upper
        if upper >= 500:
            break

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=min(kwh, 500),
        number=dict(suffix=" kWh/m\u00b2/yr", font=dict(size=20)),
        title=dict(text=f"BER {band}", font=dict(size=24, color="#1A1A2E")),
        gauge=dict(
            axis=dict(range=[0, 500], tickwidth=1, tickcolor="#CCC"),
            bar=dict(color="#1A1A2E", thickness=0.2),
            steps=steps,
            threshold=dict(
                line=dict(color="#1A1A2E", width=4),
                thickness=0.8,
                value=min(kwh, 500),
            ),
        ),
    ))
    fig.update_layout(
        height=260,
        margin=dict(l=30, r=30, t=60, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ---------------------------------------------------------------------------
# Display BER result
# ---------------------------------------------------------------------------

def _display_ber(ber: BERResult, key_suffix: str = "main"):
    """Render the BER result card."""
    st.markdown("<div class='section-header'><h3>BER Rating</h3></div>",
                unsafe_allow_html=True)

    text_col = _text_color_for_bg(ber.color_hex)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        # Main rating badge (Irish BER — common reference scale)
        st.markdown(
            f"<div style='background-color:{ber.color_hex}; color:{text_col}; "
            f"text-align:center; padding:20px; border-radius:10px; "
            f"font-size:48px; font-weight:bold;'>{ber.ber_band}</div>",
            unsafe_allow_html=True,
        )
        st.caption("Irish BER (reference scale)")
        st.metric("Primary Energy", f"{ber.kwh_per_m2:.0f} kWh/m\u00b2/yr")

        # Native country EPC badge (shown when country is not Ireland)
        if ber.native_epc_band and ber.native_epc_scale and ber.building_input.country.value != "ireland":
            native_text = _text_color_for_bg(ber.native_epc_color or "#888888")
            st.markdown(
                f"<div style='background-color:{ber.native_epc_color}; color:{native_text}; "
                f"text-align:center; padding:12px; border-radius:10px; "
                f"font-size:32px; font-weight:bold; margin-top:8px;'>{ber.native_epc_band}</div>",
                unsafe_allow_html=True,
            )
            st.caption(f"Native scale: {ber.native_epc_scale}")

    with col2:
        hw = ber.hwb_result
        st.plotly_chart(_make_energy_breakdown_chart(hw), use_container_width=True, key=f"breakdown_{key_suffix}")

    with col3:
        st.metric("CO\u2082 Emissions", f"{hw.co2_kg_per_m2:.1f} kg/m\u00b2/yr")
        st.metric("Total CO\u2082", f"{hw.co2_kg:.0f} kg/yr")

    # Key metrics table
    hw = ber.hwb_result
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Floor Area", f"{hw.floor_area:.0f} m\u00b2")
    m2.metric("Heated Volume", f"{hw.heated_volume:.0f} m\u00b3")
    m3.metric("Final Energy", f"{hw.final_energy_kwh_per_m2:.1f} kWh/m\u00b2/yr")
    m4.metric("Hot Water", f"{hw.hot_water_kwh:.0f} kWh/yr")

    # BER gauge
    st.plotly_chart(
        _make_ber_gauge(ber.ber_band, ber.kwh_per_m2),
        use_container_width=True,
        key=f"gauge_{key_suffix}",
    )

    # --- Retrofit comparison ---
    if ber.retrofit_ber_band:
        st.markdown("<div class='section-header'><h3>Retrofit Comparison</h3></div>",
                    unsafe_allow_html=True)

        r_band, r_color = get_ber_band(ber.retrofit_kwh_per_m2)
        r_text = _text_color_for_bg(r_color)
        before_text = _text_color_for_bg(ber.color_hex)

        savings = ber.kwh_per_m2 - ber.retrofit_kwh_per_m2
        pct = (savings / ber.kwh_per_m2 * 100) if ber.kwh_per_m2 > 0 else 0

        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.markdown("**Current Rating**")
            st.markdown(
                f"<div style='background-color:{ber.color_hex}; color:{before_text}; "
                f"text-align:center; padding:14px; border-radius:8px; "
                f"font-size:28px; font-weight:bold;'>{ber.ber_band}</div>",
                unsafe_allow_html=True,
            )
            st.metric("Current Energy", f"{ber.kwh_per_m2:.0f} kWh/m\u00b2/yr")

        with rc2:
            st.markdown("**After Retrofit**")
            st.markdown(
                f"<div style='background-color:{r_color}; color:{r_text}; "
                f"text-align:center; padding:14px; border-radius:8px; "
                f"font-size:28px; font-weight:bold;'>{ber.retrofit_ber_band}</div>",
                unsafe_allow_html=True,
            )
            st.metric(
                "Retrofit Energy",
                f"{ber.retrofit_kwh_per_m2:.0f} kWh/m\u00b2/yr",
                delta=f"-{savings:.0f} kWh/m\u00b2/yr",
                delta_color="inverse",
            )

        with rc3:
            st.markdown("**Savings**")
            st.metric(
                "Energy Reduction",
                f"{pct:.0f}%",
                delta=f"-{savings:.0f} kWh/m\u00b2/yr",
                delta_color="inverse",
            )
            band_jump = _ber_band_index(ber.ber_band) - _ber_band_index(ber.retrofit_ber_band)
            if band_jump > 0:
                st.success(f"Improved by {band_jump} BER band{'s' if band_jump > 1 else ''}")
            if ber.retrofit_native_epc_band and ber.native_epc_scale and ber.building_input.country.value != "ireland":
                st.info(f"Native {ber.native_epc_scale}: {ber.native_epc_band} → {ber.retrofit_native_epc_band}")

    # --- BER Scale bar ---
    st.markdown("<div class='section-header'><h3>BER Scale</h3></div>",
                unsafe_allow_html=True)
    scale_html = "<div style='display:flex; gap:2px; align-items:end;'>"
    for band, threshold, color in BER_BANDS:
        is_active = band == ber.ber_band
        txt = _text_color_for_bg(color)
        height = "48px" if is_active else "36px"
        font_size = "14px" if is_active else "11px"
        font_weight = "bold" if is_active else "normal"
        opacity = "1.0" if is_active else "0.45"
        shadow = "0 0 8px rgba(0,0,0,0.35)" if is_active else "none"
        scale_html += (
            f"<div style='flex:1; background-color:{color}; color:{txt}; "
            f"text-align:center; padding:5px 2px; opacity:{opacity}; "
            f"border-radius:4px; font-size:{font_size}; font-weight:{font_weight}; "
            f"height:{height}; line-height:{height}; "
            f"box-shadow:{shadow};'>{band}</div>"
        )
    scale_html += "</div>"
    st.markdown(scale_html, unsafe_allow_html=True)


# ===================================================================
# What-If: constants and helpers
# ===================================================================

# Policy thresholds (primary energy kWh/m²/yr) that trigger grant eligibility
# or regulatory requirements in each country.
_POLICY_THRESHOLDS: dict[str, list[tuple[str, float]]] = {
    "ireland":     [("SEAI Better Energy Homes grant (target ≤B3)", 150.0),
                    ("Nearly Zero-Energy Building A3", 75.0)],
    "france":      [("MaPrimeRénov' grant eligibility (DPE ≤C)", 180.0),
                    ("BBC Rénovation low-energy label", 80.0)],
    "germany":     [("BEG KfW55 EE federal grant threshold", 60.0),
                    ("BEG KfW40 deep-retrofit threshold", 45.0)],
    "belgium":     [("Flanders EPB renovation target (EPC ≤B)", 200.0),
                    ("BEN near-zero standard", 100.0)],
    "netherlands": [("ISDE subsidy threshold (Energielabel ≤A)", 160.0),
                    ("BENG near-zero standard", 50.0)],
    "luxembourg":  [("Klimabonus subsidy eligibility (≤Energiepass C)", 150.0),
                    ("AAA near-zero standard", 45.0)],
    "switzerland": [("Cantonal energy programme (GEAK ≤C)", 140.0),
                    ("Minergie standard (GEAK A)", 55.0)],
    "austria":     [("Sanierungsscheck grant eligibility (≤C)", 120.0),
                    ("OIB A near-zero standard", 55.0)],
}

# Recommended retrofit insulation levels by construction epoch
_INSULATION_BY_EPOCH: dict[str, dict[str, float]] = {
    "before_1980": {"wall": 14.0, "roof": 25.0, "win_u": 1.0},
    "1980_1990":   {"wall": 12.0, "roof": 20.0, "win_u": 1.2},
    "1990_2000":   {"wall": 10.0, "roof": 16.0, "win_u": 1.2},
    "2000_2010":   {"wall":  8.0, "roof": 12.0, "win_u": 1.0},
    "after_2010":  {"wall":  6.0, "roof": 10.0, "win_u": 0.8},
}


def _policy_thresholds_for(country_value: str) -> list[tuple[str, float]]:
    return _POLICY_THRESHOLDS.get(country_value.lower(), [])


# ---------------------------------------------------------------------------
# What-If: tailored advice helpers
# ---------------------------------------------------------------------------

def _advice_fabric(epoch: ConstructionEpoch, country: Country) -> str:
    age_note = {
        ConstructionEpoch.BEFORE_1980: (
            "Pre-1980 buildings typically have solid masonry walls with no cavity insulation "
            "(U-wall ≈ 1.2 W/m²K). External wall insulation (EWI) is the most durable "
            "solution. Confirm wall construction type before specifying."
        ),
        ConstructionEpoch.EPOCH_1980_1990: (
            "1980s buildings usually have unfilled cavity walls. Cavity fill injection is "
            "cheaper than EWI and nearly as effective — commission a cavity survey first."
        ),
        ConstructionEpoch.EPOCH_1990_2000: (
            "1990s buildings may have partial cavity fill. Roof insulation top-up to 300 mm "
            "and window replacement are typically the most cost-effective fabric measures."
        ),
        ConstructionEpoch.EPOCH_2000_2010: (
            "2000s buildings are reasonably insulated. Topping up attic insulation and "
            "replacing older double glazing with triple glazing will give the best gains."
        ),
        ConstructionEpoch.AFTER_2010: (
            "Post-2010 buildings are generally well insulated. Airtightness improvements "
            "and mechanical ventilation with heat recovery (MVHR) are likely the next step."
        ),
    }.get(epoch, "Upgrade insulation to reduce heat loss through the building envelope.")

    grant = {
        "ireland":     "SEAI grants: up to €8,100 for wall + roof insulation combined.",
        "france":      "MaPrimeRénov' covers up to 75 % of insulation cost for low-income households.",
        "germany":     "BEG EM: up to 20 % grant for individual fabric measures.",
        "belgium":     "Flanders Mijn VerbouwPremie and Mijn VerbouwLening for insulation works.",
        "netherlands": "ISDE subsidie available for qualifying insulation measures.",
        "luxembourg":  "Klimabonus (Ministry of Energy) covers up to 50 % of eligible insulation costs.",
        "switzerland": "Gebäudeprogramm cantonal subsidies for wall and roof insulation.",
        "austria":     "Sanierungsscheck and regional Wohnbauförderung for insulation.",
    }.get(country.value, "Check national grant schemes for fabric improvement measures.")

    return f"{age_note}\n\n{grant}"


def _advice_heating(heating: HeatingSystem, country: Country) -> str:
    hp_note = {
        HeatingSystem.OIL_BOILER: (
            "Replacing an oil boiler with an air-source heat pump typically cuts CO\u2082 "
            "by 60-80 % and removes exposure to volatile oil prices. "
            "Ensure the radiator system is checked for compatibility."
        ),
        HeatingSystem.GAS_BOILER: (
            "Switching from gas to a heat pump removes ongoing exposure to gas price volatility "
            "and aligns with EU Fit-for-55 phase-out timelines. "
            "SCOP 3.5 means 3.5 kWh heat per 1 kWh electricity."
        ),
        HeatingSystem.ELECTRIC_DIRECT: (
            "Direct electric heating is the most expensive option. "
            "A heat pump at SCOP 3.5 delivers 3.5× more heat per kWh, "
            "cutting both energy bills and emissions dramatically."
        ),
        HeatingSystem.BIOMASS: (
            "Biomass is already low-carbon. A heat pump upgrade is most worthwhile "
            "if electricity is clean (France, Switzerland) or biomass supply is unreliable."
        ),
        HeatingSystem.HEAT_PUMP_AIR: (
            "You already have an air-source heat pump. Consider upgrading to ground-source "
            "(SCOP 4.5 vs 3.5) if outdoor space allows."
        ),
        HeatingSystem.HEAT_PUMP_GROUND: (
            "Ground-source is the highest-efficiency option. Focus remaining effort on "
            "reducing demand through fabric improvements."
        ),
        HeatingSystem.HEAT_PUMP_WATER: (
            "Water-source heat pump is highly efficient. Focus remaining effort on "
            "reducing demand through fabric improvements."
        ),
        HeatingSystem.DISTRICT_HEATING: (
            "District heating efficiency depends on the network's fuel mix. "
            "Check whether the local network is transitioning to renewable sources."
        ),
    }.get(heating, "Consider a heat pump to reduce carbon emissions from heating.")

    country_note = ""
    if country == Country.FRANCE:
        country_note = "\n\n**France:** Electricity is ~52 g CO\u2082/kWh (nuclear-dominated). A heat pump here achieves exceptional CO\u2082 savings — typically 90%+ vs gas."
    elif country == Country.GERMANY:
        country_note = "\n\n**Germany:** The grid is still coal-heavy (~385 g/kWh). Insulating the building fabric before switching gives better combined CO\u2082 outcomes than a heat pump in a poorly-insulated shell."
    elif country == Country.SWITZERLAND:
        country_note = "\n\n**Switzerland:** Electricity is nearly carbon-free (hydro + nuclear, ~29 g/kWh). A heat pump is one of the best CO\u2082 investments available."

    grant = {
        "ireland":     "SEAI Heat Pump Grant: up to \u20ac6,500 for air-source, \u20ac3,500 for ground-source.",
        "france":      "MaPrimeRénov' S\u00e9r\u00e9nit\u00e9 + CEE certificates available for heat pump installation.",
        "germany":     "BEG EM: up to 35 % grant for heat pump (+ 5 % climate-speed bonus for fossil boiler replacement).",
        "belgium":     "Flanders Mijn VerbouwPremie for heat pump systems.",
        "netherlands": "ISDE subsidie: \u20ac1,800\u2013\u20ac3,700 depending on heat pump type.",
        "luxembourg":  "Klimabonus grants for heat pump installation.",
        "switzerland": "Gebäudeprogramm cantonal subsidies for heat pump replacement.",
        "austria":     "Raus aus \u00d6l und Gas: \u20ac7,500 replacement subsidy for oil/gas boiler switch.",
    }.get(country.value, "Check national grant schemes for heat pump installation.")

    return f"{hp_note}{country_note}\n\n{grant}"


def _advice_deep(epoch: ConstructionEpoch, heating: HeatingSystem, country: Country) -> str:
    intro = (
        "A whole-house deep retrofit combining fabric upgrades with a heat pump "
        "typically achieves the largest energy savings and qualifies for the highest grant rates. "
        "Engage an energy advisor or BER assessor to prepare a tailored retrofit plan before starting."
    )
    program = {
        "ireland":     "The **SEAI One Stop Shop** scheme manages the full retrofit journey and can combine grants for insulation, heat pump, and ventilation in a single application.",
        "france":      "**Mon Accompagnateur R\u00e9nov'** (MAR) is mandatory for grants above \u20ac5,000. MaPrimeR\u00e9nov' S\u00e9r\u00e9nit\u00e9 covers whole-house retrofit projects.",
        "germany":     "An **iSFP** (individueller Sanierungsfahrplan) qualifies for an extra 5 % BEG bonus. A certified Energieeffizienz-Experte should prepare it.",
        "belgium":     "Flanders **Mijn VerbouwPremie** + **Mijn VerbouwLening** can cover staged deep retrofit. An EPC assessment before and after is recommended.",
        "netherlands": "The **Nationaal Warmtefonds** provides low-interest loans for deep retrofit. **Energiebespaargarantie** offers a certified performance guarantee.",
        "luxembourg":  "**Klimabonus** covers up to 50 % of eligible deep-retrofit costs. A certified Energieberater report is required for the application.",
        "switzerland": "**Gebäudeprogramm** (cantonal) + **GEAK Plus** assessment provides a government-recognised retrofit roadmap with cantonal subsidies.",
        "austria":     "**Sanierungsscheck** + **Wohnbauförderung** (state level). A thermal energy advisor prepares the OIB Energieausweis for the application.",
    }.get(country.value, "")
    return f"{intro}\n\n{program}" if program else intro


# ---------------------------------------------------------------------------
# What-If: pathway scenario generation
# ---------------------------------------------------------------------------

def _generate_pathway_scenarios(original: BERResult) -> list[dict]:
    """Generate 3 tailored retrofit pathway scenarios from the original pipeline result."""
    b = original.building_input
    calc = HWBCalculator()
    fabric = _INSULATION_BY_EPOCH.get(b.construction_epoch.value,
                                      _INSULATION_BY_EPOCH["before_1980"])

    is_hp = b.heating_system in (
        HeatingSystem.HEAT_PUMP_AIR,
        HeatingSystem.HEAT_PUMP_GROUND,
        HeatingSystem.HEAT_PUMP_WATER,
    )
    hp_system = HeatingSystem.HEAT_PUMP_GROUND if is_hp else HeatingSystem.HEAT_PUMP_AIR
    hp_label = "Upgrade to Ground-Source Heat Pump" if is_hp else "Switch to Air-Source Heat Pump"

    def _make_ber(kwh: float, hwb: "HWBResult", building: BuildingInput) -> BERResult:
        band, color = get_ber_band(kwh)
        n_band, n_color, n_scale = get_native_epc(kwh, building.country)
        return BERResult(
            ber_band=band, kwh_per_m2=kwh, color_hex=color,
            hwb_result=hwb, building_input=building,
            native_epc_band=n_band, native_epc_color=n_color, native_epc_scale=n_scale,
        )

    # Scenario 1 — Fabric only
    r_fabric = RetrofitInput(
        wall_insulation_cm=fabric["wall"],
        roof_insulation_cm=fabric["roof"],
        window_u_value=fabric["win_u"],
    )
    ber1 = calc.calculate_ber(b, r_fabric)
    scenario1_ber = _make_ber(ber1.retrofit_kwh_per_m2, ber1.retrofit_hwb_result, b)

    # Scenario 2 — Heat pump only (keep existing fabric)
    hp_building = BuildingInput(**{**b.model_dump(), "heating_system": hp_system})
    ber2 = calc.calculate_ber(hp_building)
    scenario2_ber = _make_ber(ber2.kwh_per_m2, ber2.hwb_result, hp_building)

    # Scenario 3 — Full deep retrofit
    r_deep = RetrofitInput(
        wall_insulation_cm=fabric["wall"],
        roof_insulation_cm=fabric["roof"],
        window_u_value=fabric["win_u"],
        heating_system_after=hp_system,
    )
    ber3 = calc.calculate_ber(b, r_deep)
    scenario3_ber = _make_ber(ber3.retrofit_kwh_per_m2, ber3.retrofit_hwb_result, b)

    return [
        {
            "title": "Step 1 — Fabric Upgrade",
            "description": "Insulate walls, roof, and windows. No change to heating system.",
            "ber_result": scenario1_ber,
            "steps": [
                f"Add {int(fabric['wall'])} cm external/cavity wall insulation",
                f"Top up roof/attic insulation to {int(fabric['roof'])} cm",
                f"Replace windows to U = {fabric['win_u']} W/m\u00b2K",
            ],
            "advice": _advice_fabric(b.construction_epoch, b.country),
        },
        {
            "title": "Step 2 — Heat Pump",
            "description": "Switch to a low-carbon heat pump. Existing building fabric unchanged.",
            "ber_result": scenario2_ber,
            "steps": [
                hp_label,
                "Install buffer tank and upgrade radiators if needed",
                "Connect heat pump to existing hot water cylinder or install new",
            ],
            "advice": _advice_heating(b.heating_system, b.country),
        },
        {
            "title": "Step 3 — Full Deep Retrofit",
            "description": "Combine fabric improvements and heat pump for maximum savings.",
            "ber_result": scenario3_ber,
            "steps": [
                f"Add {int(fabric['wall'])} cm wall insulation",
                f"Add {int(fabric['roof'])} cm roof insulation",
                f"Replace windows to U = {fabric['win_u']} W/m\u00b2K",
                hp_label,
                "Commission updated energy performance certificate",
            ],
            "advice": _advice_deep(b.construction_epoch, b.heating_system, b.country),
        },
    ]


# ---------------------------------------------------------------------------
# What-If: comparison and panel rendering
# ---------------------------------------------------------------------------

def _render_scenario_comparison(original: BERResult, scenario: BERResult) -> None:
    """Side-by-side BER comparison: original pipeline result vs a what-if scenario."""
    savings_kwh = original.kwh_per_m2 - scenario.kwh_per_m2
    pct = (savings_kwh / original.kwh_per_m2 * 100) if original.kwh_per_m2 > 0 else 0.0
    co2_delta = original.hwb_result.co2_kg_per_m2 - scenario.hwb_result.co2_kg_per_m2

    st.markdown("#### Result vs Original")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**Original (pipeline)**")
        orig_txt = _text_color_for_bg(original.color_hex)
        st.markdown(
            f"<div style='background:{original.color_hex}; color:{orig_txt}; "
            f"text-align:center; padding:14px; border-radius:8px; "
            f"font-size:28px; font-weight:bold;'>{original.ber_band}</div>",
            unsafe_allow_html=True,
        )
        st.metric("Primary Energy", f"{original.kwh_per_m2:.0f} kWh/m\u00b2/yr")
        st.metric("CO\u2082", f"{original.hwb_result.co2_kg_per_m2:.1f} kg/m\u00b2/yr")
        if original.native_epc_band and original.building_input.country.value != "ireland":
            st.caption(f"{original.native_epc_scale}: {original.native_epc_band}")

    with c2:
        st.markdown("**This scenario**")
        scen_txt = _text_color_for_bg(scenario.color_hex)
        st.markdown(
            f"<div style='background:{scenario.color_hex}; color:{scen_txt}; "
            f"text-align:center; padding:14px; border-radius:8px; "
            f"font-size:28px; font-weight:bold;'>{scenario.ber_band}</div>",
            unsafe_allow_html=True,
        )
        st.metric(
            "Primary Energy",
            f"{scenario.kwh_per_m2:.0f} kWh/m\u00b2/yr",
            delta=f"{-savings_kwh:.0f} kWh/m\u00b2/yr",
            delta_color="inverse",
        )
        st.metric(
            "CO\u2082",
            f"{scenario.hwb_result.co2_kg_per_m2:.1f} kg/m\u00b2/yr",
            delta=f"{-co2_delta:.1f} kg/m\u00b2/yr",
            delta_color="inverse",
        )
        if scenario.native_epc_band and scenario.building_input.country.value != "ireland":
            st.caption(f"{scenario.native_epc_scale}: {scenario.native_epc_band}")

    with c3:
        st.markdown("**Change**")
        band_jump = _ber_band_index(original.ber_band) - _ber_band_index(scenario.ber_band)
        if band_jump > 0:
            st.success(f"Improved {band_jump} BER band{'s' if band_jump > 1 else ''}")
        elif band_jump < 0:
            st.error(f"Worsened {abs(band_jump)} BER band{'s' if abs(band_jump) > 1 else ''}")
        else:
            st.info("No band change")
        st.metric("Energy saving", f"{pct:.0f}%")
        st.metric("CO\u2082 saving", f"{co2_delta:.1f} kg/m\u00b2/yr")

        # Highlight policy threshold crossings
        country_val = scenario.building_input.country.value
        for label, threshold in _policy_thresholds_for(country_val):
            if original.kwh_per_m2 > threshold >= scenario.kwh_per_m2:
                st.success(f"\U0001f3c6 Crossed: **{label}**")


def _render_whatif_panel(original: BERResult) -> None:
    """Render the full Customise / What-If expander below the pipeline BER result."""
    with st.expander("\U0001f6e0\ufe0f Customise / What-If", expanded=False):
        tab_edit, tab_pathway, tab_history = st.tabs(
            ["\u270f\ufe0f Edit & Recalculate", "\U0001f4cd Recommended Pathway", "\U0001f4cb Scenario History"]
        )

        # ── Tab 1: Edit & Recalculate ──────────────────────────────────────
        with tab_edit:
            st.caption(
                "Adjust any building parameter below — values are pre-filled from the pipeline. "
                "Press **Recalculate BER** to run a what-if scenario."
            )
            b = original.building_input

            wi_geom, wi_class, wi_heat, wi_retro = st.tabs(
                ["Geometry", "Classification", "Heating", "Retrofit"]
            )

            with wi_geom:
                wg1, wg2 = st.columns(2)
                with wg1:
                    wi_length = st.number_input(
                        "Length (m)", min_value=3.0, value=float(b.length), step=0.5,
                        key="wi_length",
                    )
                    wi_width = st.number_input(
                        "Width (m)", min_value=3.0, value=float(b.width), step=0.5,
                        key="wi_width",
                    )
                with wg2:
                    wi_storeys = st.number_input(
                        "Heated Storeys", min_value=1, max_value=4,
                        value=int(b.heated_storeys), key="wi_storeys",
                    )
                    wi_storey_h = st.number_input(
                        "Storey Height (m)", min_value=2.0,
                        value=float(b.storey_height), step=0.1, key="wi_storey_h",
                    )

            with wi_class:
                wc1, wc2 = st.columns(2)
                with wc1:
                    wi_btype = st.selectbox(
                        "Building Type",
                        [bt.value for bt in BuildingType],
                        index=[bt.value for bt in BuildingType].index(b.building_type.value),
                        format_func=lambda x: BUILDING_TYPE_LABELS.get(x, x),
                        key="wi_btype",
                    )
                    wi_epoch = st.selectbox(
                        "Construction Era",
                        [e.value for e in ConstructionEpoch],
                        index=[e.value for e in ConstructionEpoch].index(b.construction_epoch.value),
                        format_func=lambda x: EPOCH_LABELS.get(x, x),
                        key="wi_epoch",
                    )
                with wc2:
                    wi_country = st.selectbox(
                        "Country",
                        [c.value for c in Country],
                        index=[c.value for c in Country].index(b.country.value),
                        format_func=lambda x: COUNTRY_LABELS.get(x, x),
                        key="wi_country",
                    )
                    wi_residents = st.number_input(
                        "Residents (0 = auto)", min_value=0.0,
                        value=float(b.residents) if b.residents is not None else 0.0,
                        step=1.0, key="wi_residents",
                    )

            with wi_heat:
                wh1, wh2 = st.columns(2)
                with wh1:
                    wi_heating = st.selectbox(
                        "Heating System",
                        [h.value for h in HeatingSystem],
                        index=[h.value for h in HeatingSystem].index(b.heating_system.value),
                        format_func=lambda x: HEATING_LABELS.get(x, x),
                        key="wi_heating",
                    )
                with wh2:
                    wi_hw_elec = st.checkbox(
                        "Hot water: electric & separate?",
                        value=b.hot_water_electric_separate,
                        key="wi_hw_elec",
                    )

            with wi_retro:
                st.markdown("Apply retrofit measures on top of the edited configuration above.")
                wi_show_retro = st.checkbox("Enable retrofit comparison", key="wi_show_retro")
                if wi_show_retro:
                    wr1, wr2 = st.columns(2)
                    with wr1:
                        wi_wall_ins = st.slider(
                            "Wall insulation (cm)", 0, 30, 12, key="wi_wall_ins",
                        )
                        wi_roof_ins = st.slider(
                            "Roof insulation (cm)", 0, 40, 20, key="wi_roof_ins",
                        )
                        wi_win_u = st.slider(
                            "Window U-value (W/m\u00b2K)", 0.5, 3.0, 1.0,
                            step=0.1, key="wi_win_u",
                        )
                    with wr2:
                        wi_heat_after = st.selectbox(
                            "Heating after retrofit",
                            ["Same"] + [h.value for h in HeatingSystem],
                            format_func=lambda x: (
                                HEATING_LABELS.get(x, x) if x != "Same" else "Same as current"
                            ),
                            key="wi_heat_after",
                        )
                        wi_hw_elec_after = st.checkbox(
                            "Hot water electric after retrofit?",
                            key="wi_hw_elec_after",
                        )

            if st.button("Recalculate BER", type="primary", key="wi_recalc_btn"):
                wi_building = BuildingInput(
                    length=wi_length,
                    width=wi_width,
                    heated_storeys=wi_storeys,
                    storey_height=wi_storey_h,
                    building_type=BuildingType(wi_btype),
                    construction_epoch=ConstructionEpoch(wi_epoch),
                    country=Country(wi_country),
                    heating_system=HeatingSystem(wi_heating),
                    hot_water_electric_separate=wi_hw_elec,
                    residents=wi_residents if wi_residents > 0 else None,
                )
                wi_retrofit = None
                if wi_show_retro:
                    wi_retrofit = RetrofitInput(
                        wall_insulation_cm=float(wi_wall_ins),
                        roof_insulation_cm=float(wi_roof_ins),
                        window_u_value=float(wi_win_u),
                        heating_system_after=(
                            HeatingSystem(wi_heat_after) if wi_heat_after != "Same" else None
                        ),
                        hot_water_electric_separate_after=wi_hw_elec_after,
                    )

                calculator = HWBCalculator()
                new_ber = calculator.calculate_ber(wi_building, wi_retrofit)
                st.session_state.whatif_latest = new_ber
                st.session_state.whatif_history.append({
                    "label": f"Scenario {len(st.session_state.whatif_history) + 1}",
                    "ber_band": new_ber.ber_band,
                    "kwh_per_m2": new_ber.kwh_per_m2,
                    "co2_kg_per_m2": new_ber.hwb_result.co2_kg_per_m2,
                    "heating": wi_heating,
                    "epoch": wi_epoch,
                    "color_hex": new_ber.color_hex,
                    "native_epc_band": new_ber.native_epc_band,
                    "native_epc_scale": new_ber.native_epc_scale,
                    "with_retrofit": wi_show_retro,
                })
                st.toast("What-if BER calculated!", icon="\u2705")
                st.rerun()

            if st.session_state.whatif_latest is not None:
                st.divider()
                _render_scenario_comparison(original, st.session_state.whatif_latest)
                with st.expander("Full scenario details"):
                    _display_ber(st.session_state.whatif_latest, key_suffix="whatif")

        # ── Tab 2: Recommended Pathway ─────────────────────────────────────
        with tab_pathway:
            b = original.building_input
            st.markdown(
                f"Auto-generated 3-step improvement pathway for a **"
                f"{EPOCH_LABELS.get(b.construction_epoch.value, b.construction_epoch.value)}** "
                f"**{BUILDING_TYPE_LABELS.get(b.building_type.value, b.building_type.value)}** "
                f"in **{COUNTRY_LABELS.get(b.country.value, b.country.value)}** with "
                f"**{HEATING_LABELS.get(b.heating_system.value, b.heating_system.value)}** heating."
            )

            scenarios = _generate_pathway_scenarios(original)
            thresholds = _policy_thresholds_for(b.country.value)

            for i, sc in enumerate(scenarios):
                sc_ber: BERResult = sc["ber_result"]
                sc_txt = _text_color_for_bg(sc_ber.color_hex)
                orig_txt = _text_color_for_bg(original.color_hex)
                kwh_saving = original.kwh_per_m2 - sc_ber.kwh_per_m2
                co2_saving = (
                    original.hwb_result.co2_kg_per_m2 - sc_ber.hwb_result.co2_kg_per_m2
                )
                pct_saving = (kwh_saving / original.kwh_per_m2 * 100) if original.kwh_per_m2 > 0 else 0

                with st.container(border=True):
                    hdr, badge_new, badge_orig = st.columns([4, 1, 1])
                    with hdr:
                        st.markdown(f"### {sc['title']}")
                        st.caption(sc["description"])
                    with badge_new:
                        st.markdown(
                            f"<div style='background:{sc_ber.color_hex}; color:{sc_txt}; "
                            f"text-align:center; padding:8px; border-radius:6px; "
                            f"font-size:22px; font-weight:bold;'>{sc_ber.ber_band}</div>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"{sc_ber.kwh_per_m2:.0f} kWh/m\u00b2")
                        if sc_ber.native_epc_band and b.country.value != "ireland":
                            st.caption(f"{sc_ber.native_epc_scale}: {sc_ber.native_epc_band}")
                    with badge_orig:
                        st.markdown(
                            f"<div style='background:{original.color_hex}; color:{orig_txt}; "
                            f"text-align:center; padding:8px; border-radius:6px; "
                            f"font-size:14px; opacity:0.55;'>{original.ber_band} now</div>",
                            unsafe_allow_html=True,
                        )

                    # Action steps
                    step_cols = st.columns(min(len(sc["steps"]), 3))
                    for j, step in enumerate(sc["steps"]):
                        with step_cols[j % len(step_cols)]:
                            st.markdown(
                                f"<div style='background:#F0FFF8; border-left:3px solid #00664E; "
                                f"padding:8px 10px; border-radius:4px; margin:4px 0; "
                                f"font-size:0.88rem;'><b>{j+1}.</b> {step}</div>",
                                unsafe_allow_html=True,
                            )

                    # Savings metrics
                    sm1, sm2, sm3 = st.columns(3)
                    sm1.metric("Energy saving", f"{kwh_saving:.0f} kWh/m\u00b2/yr",
                               delta=f"{pct_saving:.0f}% reduction", delta_color="off")
                    sm2.metric("CO\u2082 saving", f"{co2_saving:.1f} kg/m\u00b2/yr")
                    sm3.metric("Target band", sc_ber.ber_band)

                    # Policy threshold callout
                    for t_label, t_kwh in thresholds:
                        if original.kwh_per_m2 > t_kwh >= sc_ber.kwh_per_m2:
                            st.success(
                                f"\U0001f3c6 This step crosses the **{t_label}** "
                                f"threshold ({t_kwh:.0f} kWh/m\u00b2/yr)."
                            )

                    with st.expander("Tailored advice & available grants"):
                        st.markdown(sc["advice"])

        # ── Tab 3: Scenario History ────────────────────────────────────────
        with tab_history:
            history = st.session_state.whatif_history
            if not history:
                st.info(
                    "No scenarios yet. Use the **Edit & Recalculate** tab to explore "
                    "different building configurations."
                )
            else:
                st.markdown(f"**{len(history)} scenario(s) recorded this session.**")
                cols = st.columns([2, 1, 2, 2, 2, 1])
                for h, label in zip(
                    cols,
                    ["Scenario", "Band", "Primary energy", "CO\u2082", "Heating", "Retrofit?"],
                ):
                    h.markdown(f"**{label}**")
                st.divider()
                for entry in history:
                    row = st.columns([2, 1, 2, 2, 2, 1])
                    txt = _text_color_for_bg(entry["color_hex"])
                    row[0].markdown(entry["label"])
                    e_bg = entry["color_hex"]
                    e_band = entry["ber_band"]
                    row[1].markdown(
                        f"<span style='background:{e_bg}; color:{txt}; "
                        f"padding:3px 8px; border-radius:4px; font-weight:bold;'>"
                        f"{e_band}</span>",
                        unsafe_allow_html=True,
                    )
                    row[2].markdown(f"{entry['kwh_per_m2']:.0f} kWh/m\u00b2/yr")
                    row[3].markdown(f"{entry['co2_kg_per_m2']:.1f} kg/m\u00b2/yr")
                    row[4].markdown(HEATING_LABELS.get(entry["heating"], entry["heating"]))
                    row[5].markdown("Yes" if entry["with_retrofit"] else "No")

                if st.button("Clear history", key="wi_clear_history"):
                    st.session_state.whatif_history = []
                    st.session_state.whatif_latest = None
                    st.rerun()


# ===================================================================
# MODE 1: Full Pipeline
# ===================================================================
if mode == "Full Pipeline":
    st.markdown("<div class='section-header'><h3>Enter Address</h3></div>",
                unsafe_allow_html=True)
    col1, col2, col3 = st.columns([3, 2, 1])
    with col1:
        address = st.text_input(
            "Address or postal code",
            placeholder="e.g. D02 X285 or 1010 Luxembourg",
            help="Any address or postal code in a supported CIRCUS NWE country. "
                 "Used to geocode the property and fetch satellite/street imagery.",
        )
    with col2:
        pipeline_country = st.selectbox(
            "Country",
            [c.value for c in Country],
            format_func=lambda x: COUNTRY_LABELS.get(x, x),
            help="Select the country to restrict geocoding and set climate data.",
            key="pipeline_country",
        )
    with col3:
        st.markdown('<div style="margin-top:28px;"></div>', unsafe_allow_html=True)
        run_btn = st.button("Analyse", type="primary", use_container_width=True)

    if run_btn and address:
        with st.status("Running BER pipeline\u2026", expanded=True) as status:
            st.write("Geocoding address and fetching imagery\u2026")
            pipeline = BERPipeline(output_dir=Path("output"))
            result = _run_async(pipeline.run(address, country=Country(pipeline_country)))
            st.session_state.pipeline_result = result
            st.session_state.whatif_history = []
            st.session_state.whatif_latest = None
            st.session_state.uploaded_satellite = None
            st.session_state.uploaded_sv_images = {}

            if result.coordinates:
                st.write("\u2705 Location found")
            if result.satellite_image_path:
                st.write("\u2705 Satellite imagery captured")
            if result.street_analysis:
                st.write("\u2705 AI building analysis complete")
            if result.ber_result:
                st.write("\u2705 BER rating calculated")
            status.update(label="Pipeline complete", state="complete", expanded=False)
        st.toast("BER analysis complete!", icon="\u2705")

    pr = st.session_state.pipeline_result
    if pr:
        # Show errors
        if pr.errors:
            with st.expander(f"Warnings ({len(pr.errors)})", expanded=False):
                for err in pr.errors:
                    st.warning(err)

        # --- Satellite & Street View imagery ---
        with st.container(border=True):
            st.markdown("<div class='section-header'><h3>Property Imagery</h3></div>",
                        unsafe_allow_html=True)

            if pr.satellite_image_path and Path(pr.satellite_image_path).exists():
                ann_sat = Path("output") / "satellite_annotated.jpg"
                display_sat = str(ann_sat) if ann_sat.exists() else pr.satellite_image_path
                caption_sat = "Satellite View (annotated)" if ann_sat.exists() else "Satellite View"
                st.image(display_sat, caption=caption_sat, width=400)

            sv_dir = Path("output") / "streetview"
            sv_images = sorted(
                p for p in sv_dir.glob("streetview_*.jpg")
                if "_annotated" not in p.name
            ) if sv_dir.exists() else []
            if sv_images:
                st.markdown("**Street View (Multi-Angle)**")
                # 2x2 grid instead of 1x4
                labels = ["Front", "Right", "Rear", "Left"]
                row1_imgs = sv_images[:2]
                row2_imgs = sv_images[2:4]
                for row_imgs, offset in [(row1_imgs, 0), (row2_imgs, 2)]:
                    if row_imgs:
                        cols = st.columns(2)
                        for i, img_p in enumerate(row_imgs):
                            idx = offset + i
                            label = labels[idx] if idx < len(labels) else f"View {idx}"
                            with cols[i]:
                                ann = img_p.parent / f"{img_p.stem}_annotated.jpg"
                                display_sv = str(ann) if ann.exists() else str(img_p)
                                st.image(display_sv, caption=label)
            elif pr.streetview_image_path and Path(pr.streetview_image_path).exists():
                st.image(pr.streetview_image_path, caption="Street View")

        # --- Image replacement & re-analysis ---
        with st.container(border=True):
            st.markdown("<div class='section-header'><h3>Replace Images</h3></div>",
                        unsafe_allow_html=True)
            with st.expander("Replace images with your own photos", expanded=False):
                st.caption(
                    "Upload your own photos to replace the Google images above. "
                    "Only the slots you fill will be overwritten — leave the rest blank "
                    "to keep the Google originals."
                )
                sat_file = st.file_uploader(
                    "Satellite image", type=["jpg", "jpeg", "png"], key="upload_sat",
                )
                sv_cols = st.columns(4)
                sv_labels = ["Front (0°)", "Right (90°)", "Rear (180°)", "Left (270°)"]
                sv_files = [
                    sv_cols[i].file_uploader(sv_labels[i], type=["jpg", "jpeg", "png"], key=f"upload_sv_{i}")
                    for i in range(4)
                ]

                reanalyse_btn = st.button("Re-analyse with my images", type="primary")

            if reanalyse_btn:
                any_uploaded = sat_file is not None or any(f is not None for f in sv_files)
                if not any_uploaded:
                    st.info("No images uploaded — re-analysing with existing Google images.")

                # Write uploaded files to disk, overwriting Google images.
                # Delete stale annotated siblings first so old overlays
                # are never shown while re-analysis is in progress.
                out_dir = Path("output")
                if sat_file is not None:
                    (out_dir / "satellite.jpg").write_bytes(sat_file.getvalue())
                    (out_dir / "satellite_annotated.jpg").unlink(missing_ok=True)
                for i, sv_file in enumerate(sv_files):
                    if sv_file is not None:
                        (out_dir / "streetview" / f"streetview_{i}.jpg").write_bytes(sv_file.getvalue())
                        (out_dir / "streetview" / f"streetview_{i}_annotated.jpg").unlink(missing_ok=True)

                try:
                    with st.status("Re-analysing with uploaded images…", expanded=True) as reanalyse_status:
                        pipeline = BERPipeline(output_dir=out_dir)
                        new_result = _run_async(pipeline.reanalyse(
                            pr,
                            country=Country(pipeline_country),
                            satellite_uploaded=sat_file is not None,
                        ))
                        st.session_state.pipeline_result = new_result
                        st.session_state.whatif_history = []
                        st.session_state.whatif_latest = None
                        reanalyse_status.update(label="Re-analysis complete", state="complete", expanded=False)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

        # --- Footprint ---
        if pr.footprint:
            with st.container(border=True):
                st.markdown("<div class='section-header'><h3>Building Footprint</h3></div>",
                            unsafe_allow_html=True)
                fp = pr.footprint
                fc1, fc2, fc3 = st.columns(3)
                fc1.metric("Dimensions", f"{fp.length_m}m \u00d7 {fp.width_m}m")
                fc2.metric("Area", f"{fp.area_m2} m\u00b2")
                source_labels = {
                    "claude_vision": "AI Vision",
                    "opencv": "Image Processing",
                    "fallback": "Default",
                }
                method = source_labels.get(fp.source, fp.source)
                fc3.metric("Confidence", f"{fp.confidence:.0%}")
                st.caption(f"Method: {method}")

        # --- AI Building Analysis ---
        if pr.street_analysis:
            with st.container(border=True):
                st.markdown("<div class='section-header'><h3>AI Building Analysis</h3></div>",
                            unsafe_allow_html=True)
                sa = pr.street_analysis
                a_cols = st.columns(4)
                a_cols[0].metric("Type", BUILDING_TYPE_LABELS.get(sa.building_type.value, sa.building_type.value))
                a_cols[1].metric("Era", EPOCH_LABELS.get(sa.construction_epoch.value, sa.construction_epoch.value))
                a_cols[2].metric("Storeys", sa.estimated_storeys)
                a_cols[3].metric("Heating", HEATING_LABELS.get(sa.heating_system_guess.value, sa.heating_system_guess.value))
                if sa.reasoning:
                    st.caption(sa.reasoning)

        # --- BER result ---
        if pr.ber_result:
            with st.container(border=True):
                _display_ber(pr.ber_result)
            _render_whatif_panel(pr.ber_result)

    elif not (st.session_state.get("pipeline_result")):
        # Empty state / onboarding
        st.markdown("---")
        oc1, oc2, oc3 = st.columns(3)
        with oc1:
            st.markdown(
                "<div class='onboard-card'>"
                "<span class='step-num'>1</span>"
                "<h4>Enter Address</h4>"
                "<p>Type a postal code or address, e.g. <b>D02 X285</b> "
                "(Ireland) or <b>1010 Luxembourg</b></p>"
                "</div>",
                unsafe_allow_html=True,
            )
        with oc2:
            st.markdown(
                "<div class='onboard-card'>"
                "<span class='step-num'>2</span>"
                "<h4>AI Analysis</h4>"
                "<p>We fetch satellite &amp; Street View imagery and "
                "analyse the building with AI</p>"
                "</div>",
                unsafe_allow_html=True,
            )
        with oc3:
            st.markdown(
                "<div class='onboard-card'>"
                "<span class='step-num'>3</span>"
                "<h4>Get BER</h4>"
                "<p>Receive an estimated BER rating with full energy "
                "breakdown and retrofit options</p>"
                "</div>",
                unsafe_allow_html=True,
            )


# ===================================================================
# MODE 2: Manual Input
# ===================================================================
else:
    st.markdown("<div class='section-header'><h3>Building Details</h3></div>",
                unsafe_allow_html=True)

    tab_geom, tab_class, tab_heat, tab_retro = st.tabs(
        ["Geometry", "Classification", "Heating", "Retrofit"]
    )

    with tab_geom:
        gc1, gc2 = st.columns(2)
        with gc1:
            length = st.number_input(
                "Length (m)", min_value=3.0, value=10.0, step=0.5,
                help="External length of the building in metres.",
            )
            width = st.number_input(
                "Width (m)", min_value=3.0, value=8.0, step=0.5,
                help="External width (depth) of the building in metres.",
            )
        with gc2:
            storeys = st.number_input(
                "Heated Storeys", min_value=1, max_value=4, value=2,
                help="Number of heated storeys (not including unheated attic).",
            )
            storey_h = st.number_input(
                "Storey Height (m)", min_value=2.0, value=3.0, step=0.1,
                help="Floor-to-floor height in metres (typically 2.4\u20133.0m).",
            )

    with tab_class:
        cc1, cc2 = st.columns(2)
        with cc1:
            building_type = st.selectbox(
                "Building Type",
                [bt.value for bt in BuildingType],
                format_func=lambda x: BUILDING_TYPE_LABELS.get(x, x),
                help="Detached = standalone. Semi-D = shares one party wall. "
                     "Terraced = shares two party walls. Length/Width refers "
                     "to which side is adjoining.",
            )
            epoch = st.selectbox(
                "Construction Era",
                [e.value for e in ConstructionEpoch],
                format_func=lambda x: EPOCH_LABELS.get(x, x),
                help="The decade the building was originally constructed. "
                     "Determines default U-values for walls, roof, floor, and windows.",
            )
        with cc2:
            country = st.selectbox(
                "Country",
                [c.value for c in Country],
                format_func=lambda x: COUNTRY_LABELS.get(x, x),
                help="Determines climate data: heating degree days, "
                     "solar irradiance, and heating season length.",
            )
            residents = st.number_input(
                "Residents (0 = auto)", min_value=0.0, value=0.0, step=1.0,
                help="Number of occupants. Leave at 0 to auto-calculate "
                     "based on floor area (\u2248 1 person per 52 m\u00b2).",
            )

    with tab_heat:
        hc1, hc2 = st.columns(2)
        with hc1:
            heating = st.selectbox(
                "Heating System",
                [h.value for h in HeatingSystem],
                format_func=lambda x: HEATING_LABELS.get(x, x),
                help="Primary space-heating system. Heat pumps have SCOP > 1 "
                     "and dramatically reduce final energy.",
            )
        with hc2:
            hw_electric = st.checkbox(
                "Hot water: electric & separate?",
                help="Check if hot water is heated by a separate electric "
                     "immersion rather than the main heating system.",
            )

    with tab_retro:
        st.markdown("Configure retrofit measures to compare before/after ratings.")
        show_retrofit = st.checkbox("Enable retrofit comparison")
        if show_retrofit:
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                wall_ins = st.slider(
                    "Wall insulation (cm)", 0, 30, 12,
                    help="Additional external wall insulation thickness in cm.",
                )
                roof_ins = st.slider(
                    "Roof insulation (cm)", 0, 40, 20,
                    help="Additional roof/attic insulation thickness in cm.",
                )
                win_u = st.slider(
                    "Window U-value (W/m\u00b2K)", 0.5, 3.0, 1.0, step=0.1,
                    help="Replacement window U-value. Lower = better insulated. "
                         "Triple glazing \u2248 0.8, double \u2248 1.4.",
                )
            with r_col2:
                heating_after = st.selectbox(
                    "Heating after retrofit",
                    ["Same"] + [h.value for h in HeatingSystem],
                    format_func=lambda x: HEATING_LABELS.get(x, x) if x != "Same" else "Same as current",
                    help="Optionally upgrade the heating system as part of the retrofit.",
                )
                hw_electric_after = st.checkbox(
                    "Hot water electric after retrofit?",
                    help="Check if hot water will be electric after the retrofit.",
                )

    calc_btn = st.button("Calculate BER", type="primary")

    if calc_btn:
        building = BuildingInput(
            length=length,
            width=width,
            heated_storeys=storeys,
            storey_height=storey_h,
            building_type=BuildingType(building_type),
            construction_epoch=ConstructionEpoch(epoch),
            country=Country(country),
            heating_system=HeatingSystem(heating),
            hot_water_electric_separate=hw_electric,
            residents=residents if residents > 0 else None,
        )

        retrofit = None
        if show_retrofit:
            retrofit = RetrofitInput(
                wall_insulation_cm=wall_ins,
                roof_insulation_cm=roof_ins,
                window_u_value=win_u,
                heating_system_after=HeatingSystem(heating_after) if heating_after != "Same" else None,
                hot_water_electric_separate_after=hw_electric_after,
            )

        calculator = HWBCalculator()
        ber = calculator.calculate_ber(building, retrofit)
        st.session_state.ber_result = ber
        st.toast("BER calculated!", icon="\u2705")

    if st.session_state.ber_result:
        _display_ber(st.session_state.ber_result, key_suffix="manual")
    elif mode == "Manual Input":
        # Empty state for manual mode
        st.info(
            "Configure your building details in the tabs above and press "
            "**Calculate BER** to see the energy rating."
        )
