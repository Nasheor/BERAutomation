"""Streamlit UI for BER Automation pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from ber_automation.ber_engine.calculator import HWBCalculator
from ber_automation.ber_engine.constants import BER_BANDS
from ber_automation.ber_engine.rating import get_ber_band
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
    st.markdown("### BER Automation")
    st.caption("v1.0")
    mode = st.radio(
        "Mode",
        ["Full Pipeline (Eircode)", "Manual Input"],
        index=1,
        help="**Full Pipeline** geocodes an Eircode, fetches imagery, "
             "runs AI analysis, and calculates the BER automatically. "
             "**Manual Input** lets you enter building details directly.",
    )
    st.divider()
    with st.expander("About this tool"):
        st.markdown(
            "This tool estimates an Irish Building Energy Rating (BER) "
            "using the HWB annual heat-balance method.\n\n"
            "**Data sources**\n"
            "- U-values: OIB / Austrian guidelines\n"
            "- Climate: degreedays.net & PHPP\n"
            "- CO\u2082 factors: SEAI conversion factors\n"
            "- BER scale: SEAI domestic BER thresholds"
        )
    st.caption("\u00a9 2025 BER Automation")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "ber_result" not in st.session_state:
    st.session_state.ber_result = None
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None

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

def _display_ber(ber: BERResult):
    """Render the BER result card."""
    st.markdown("<div class='section-header'><h3>BER Rating</h3></div>",
                unsafe_allow_html=True)

    text_col = _text_color_for_bg(ber.color_hex)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        # Main rating badge with contrast-safe text color
        st.markdown(
            f"<div style='background-color:{ber.color_hex}; color:{text_col}; "
            f"text-align:center; padding:20px; border-radius:10px; "
            f"font-size:48px; font-weight:bold;'>{ber.ber_band}</div>",
            unsafe_allow_html=True,
        )
        st.metric("Energy", f"{ber.kwh_per_m2:.0f} kWh/m\u00b2/yr")

    with col2:
        hw = ber.hwb_result
        st.plotly_chart(_make_energy_breakdown_chart(hw), width="stretch")

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
        width="stretch",
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
# MODE 1: Full Pipeline
# ===================================================================
if mode == "Full Pipeline (Eircode)":
    st.markdown("<div class='section-header'><h3>Enter Eircode</h3></div>",
                unsafe_allow_html=True)
    col1, col2 = st.columns([3, 1])
    with col1:
        eircode = st.text_input(
            "Eircode",
            placeholder="e.g. D02 X285",
            help="An Irish Eircode (7 characters). This is used to geocode "
                 "the property and fetch satellite/street imagery.",
        )
    with col2:
        run_btn = st.button("Analyse", type="primary", width="stretch")

    if run_btn and eircode:
        with st.status("Running BER pipeline\u2026", expanded=True) as status:
            st.write("Geocoding Eircode and fetching imagery\u2026")
            pipeline = BERPipeline(output_dir=Path("output"))
            result = _run_async(pipeline.run(eircode))
            st.session_state.pipeline_result = result

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
                st.image(pr.satellite_image_path, caption="Satellite View", width=400)

            sv_dir = Path("output") / "streetview"
            sv_images = sorted(sv_dir.glob("streetview_*.jpg")) if sv_dir.exists() else []
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
                                st.image(str(img_p), caption=label)
            elif pr.streetview_image_path and Path(pr.streetview_image_path).exists():
                st.image(pr.streetview_image_path, caption="Street View")

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

    elif not (st.session_state.get("pipeline_result")):
        # Empty state / onboarding
        st.markdown("---")
        oc1, oc2, oc3 = st.columns(3)
        with oc1:
            st.markdown(
                "<div class='onboard-card'>"
                "<span class='step-num'>1</span>"
                "<h4>Enter Eircode</h4>"
                "<p>Type an Irish Eircode above, e.g. <b>D02 X285</b> "
                "or <b>T12 AB34</b></p>"
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
        _display_ber(st.session_state.ber_result)
    elif mode == "Manual Input":
        # Empty state for manual mode
        st.info(
            "Configure your building details in the tabs above and press "
            "**Calculate BER** to see the energy rating."
        )
