"""Streamlit UI for BER Automation pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

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

st.set_page_config(page_title="BER Automation", page_icon="🏠", layout="wide")

st.title("Building Energy Rating — Automated Assessment")
st.markdown(
    "Estimate an Irish BER from an Eircode using satellite imagery, "
    "Street View analysis, and the HWB annual balance method."
)

# --- Sidebar: Configuration ---
with st.sidebar:
    st.header("Settings")
    mode = st.radio("Mode", ["Full Pipeline (Eircode)", "Manual Input"], index=1)

# --- Session state ---
if "ber_result" not in st.session_state:
    st.session_state.ber_result = None
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None


def _run_async(coro):
    """Run an async coroutine from sync Streamlit code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _display_ber(ber: BERResult):
    """Render the BER result card."""
    st.divider()
    st.subheader("BER Rating")

    # Main rating badge
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        st.markdown(
            f"<div style='background-color:{ber.color_hex}; color:white; "
            f"text-align:center; padding:20px; border-radius:10px; "
            f"font-size:48px; font-weight:bold;'>{ber.ber_band}</div>",
            unsafe_allow_html=True,
        )
        st.metric("Energy", f"{ber.kwh_per_m2:.0f} kWh/m²/yr")

    with col2:
        hw = ber.hwb_result
        st.markdown("**Breakdown**")
        st.text(f"Floor area:           {hw.floor_area:.0f} m²")
        st.text(f"Heated volume:        {hw.heated_volume:.0f} m³")
        st.text(f"Transmission loss:    {hw.transmission_heat_loss:.1f} W/K")
        st.text(f"Ventilation loss:     {hw.ventilation_heat_loss:.1f} W/K")
        st.text(f"Solar gains:          {hw.solar_gains:.0f} kWh/yr")
        st.text(f"Internal gains:       {hw.internal_gains:.0f} kWh/yr")
        st.text(f"Heating demand (HWB): {hw.hwb:.1f} kWh/m²/yr")
        st.text(f"Final energy:         {hw.final_energy_kwh_per_m2:.1f} kWh/m²/yr")
        st.text(f"Hot water:            {hw.hot_water_kwh:.0f} kWh/yr")

    with col3:
        st.metric("CO2 Emissions", f"{hw.co2_kg_per_m2:.1f} kg/m2/yr")
        st.metric("Total CO2", f"{hw.co2_kg:.0f} kg/yr")

    # Retrofit comparison
    if ber.retrofit_ber_band:
        st.divider()
        st.subheader("After Retrofit")
        r_band, r_color = get_ber_band(ber.retrofit_kwh_per_m2)

        rc1, rc2 = st.columns(2)
        with rc1:
            st.markdown("**Before**")
            st.markdown(
                f"<div style='background-color:{ber.color_hex}; color:white; "
                f"text-align:center; padding:10px; border-radius:5px; "
                f"font-size:32px; font-weight:bold;'>{ber.ber_band} -- "
                f"{ber.kwh_per_m2:.0f} kWh/m2/yr</div>",
                unsafe_allow_html=True,
            )
        with rc2:
            st.markdown("**After**")
            st.markdown(
                f"<div style='background-color:{r_color}; color:white; "
                f"text-align:center; padding:10px; border-radius:5px; "
                f"font-size:32px; font-weight:bold;'>{ber.retrofit_ber_band} -- "
                f"{ber.retrofit_kwh_per_m2:.0f} kWh/m2/yr</div>",
                unsafe_allow_html=True,
            )

        savings = ber.kwh_per_m2 - ber.retrofit_kwh_per_m2
        pct = (savings / ber.kwh_per_m2 * 100) if ber.kwh_per_m2 > 0 else 0
        st.success(f"Energy savings: {savings:.0f} kWh/m2/yr ({pct:.0f}%)")

    # BER scale visualization
    st.divider()
    st.subheader("BER Scale")
    scale_html = "<div style='display:flex; gap:2px;'>"
    for band, threshold, color in BER_BANDS:
        opacity = "1.0" if band == ber.ber_band else "0.4"
        border = "3px solid white" if band == ber.ber_band else "none"
        scale_html += (
            f"<div style='flex:1; background-color:{color}; color:white; "
            f"text-align:center; padding:5px 2px; opacity:{opacity}; "
            f"border:{border}; border-radius:3px; font-size:11px;'>{band}</div>"
        )
    scale_html += "</div>"
    st.markdown(scale_html, unsafe_allow_html=True)


# ===================================================================
# MODE 1: Full Pipeline
# ===================================================================
if mode == "Full Pipeline (Eircode)":
    st.subheader("Enter Eircode")
    col1, col2 = st.columns([3, 1])
    with col1:
        eircode = st.text_input("Eircode", placeholder="e.g. D02 X285")
    with col2:
        run_btn = st.button("Analyse", type="primary", use_container_width=True)

    if run_btn and eircode:
        with st.spinner("Running pipeline..."):
            pipeline = BERPipeline(output_dir=Path("output"))
            result = _run_async(pipeline.run(eircode))
            st.session_state.pipeline_result = result

    pr = st.session_state.pipeline_result
    if pr:
        # Show errors
        if pr.errors:
            with st.expander(f"Warnings ({len(pr.errors)})", expanded=False):
                for err in pr.errors:
                    st.warning(err)

        # Images
        img_cols = st.columns(2)
        if pr.satellite_image_path and Path(pr.satellite_image_path).exists():
            with img_cols[0]:
                st.image(pr.satellite_image_path, caption="Satellite View")
        if pr.streetview_image_path and Path(pr.streetview_image_path).exists():
            with img_cols[1]:
                st.image(pr.streetview_image_path, caption="Street View")

        # Footprint
        if pr.footprint:
            st.subheader("Building Footprint")
            fp = pr.footprint
            st.metric("Estimated Dimensions", f"{fp.length_m}m × {fp.width_m}m")
            source_labels = {
                "claude_vision": "AI Vision",
                "opencv": "Image Processing",
                "fallback": "Default",
            }
            method = source_labels.get(fp.source, fp.source)
            st.caption(f"Area: {fp.area_m2} m² | Confidence: {fp.confidence:.0%} | Method: {method}")

        # Claude analysis
        if pr.street_analysis:
            st.subheader("AI Building Analysis")
            sa = pr.street_analysis
            a_cols = st.columns(4)
            a_cols[0].metric("Type", sa.building_type.value.replace("_", " ").title())
            a_cols[1].metric("Era", sa.construction_epoch.value.replace("_", "–"))
            a_cols[2].metric("Storeys", sa.estimated_storeys)
            a_cols[3].metric("Heating", sa.heating_system_guess.value.replace("_", " ").title())
            if sa.reasoning:
                st.caption(sa.reasoning)

        # BER result
        if pr.ber_result:
            _display_ber(pr.ber_result)


# ===================================================================
# MODE 2: Manual Input
# ===================================================================
else:
    st.subheader("Building Details")

    col1, col2, col3 = st.columns(3)
    with col1:
        length = st.number_input("Length (m)", min_value=3.0, value=10.0, step=0.5)
        width = st.number_input("Width (m)", min_value=3.0, value=8.0, step=0.5)
        storeys = st.number_input("Heated Storeys", min_value=1, max_value=4, value=2)
        storey_h = st.number_input("Storey Height (m)", min_value=2.0, value=3.0, step=0.1)

    with col2:
        building_type = st.selectbox(
            "Building Type",
            [bt.value for bt in BuildingType],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        epoch = st.selectbox(
            "Construction Era",
            [e.value for e in ConstructionEpoch],
            format_func=lambda x: x.replace("_", "–"),
        )
        country = st.selectbox(
            "Country",
            [c.value for c in Country],
            format_func=lambda x: x.title(),
        )

    with col3:
        heating = st.selectbox(
            "Heating System",
            [h.value for h in HeatingSystem],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        hw_electric = st.checkbox("Hot water: electric & separate?")
        residents = st.number_input("Residents (0 = auto)", min_value=0.0, value=0.0, step=1.0)

    # Retrofit section
    with st.expander("Retrofit Measures"):
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            wall_ins = st.slider("Wall insulation (cm)", 0, 30, 12)
            roof_ins = st.slider("Roof insulation (cm)", 0, 40, 20)
            win_u = st.slider("Window U-value (W/m²K)", 0.5, 3.0, 1.0, step=0.1)
        with r_col2:
            heating_after = st.selectbox(
                "Heating after retrofit",
                ["Same"] + [h.value for h in HeatingSystem],
                format_func=lambda x: x.replace("_", " ").title() if x != "Same" else "Same as current",
            )
            hw_electric_after = st.checkbox("Hot water electric after retrofit?")
        show_retrofit = st.checkbox("Show retrofit comparison")

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

    if st.session_state.ber_result:
        _display_ber(st.session_state.ber_result)
