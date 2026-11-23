"""Community mode of the Streamlit app: many homes from an address list (CIRCUS).

Kept apart from ``streamlit_app.py``; the app passes in what it shares (labels, the async
runner, the single-home result view, the AI model choice). Chart builders are plain functions
so they can be tested without Streamlit.
"""

from __future__ import annotations

import csv
import io
import math
from pathlib import Path
from typing import Callable, Optional

import plotly.graph_objects as go
import streamlit as st

from ber_automation.ber_engine.constants import BER_BANDS
from ber_automation.community.addresses import read_addresses
from ber_automation.community.assess import DEFAULT_BASE_DIR, assess_community, community_dir
from ber_automation.community.models import CommunityResult
from ber_automation.community.summary import (
    agreement,
    area_totals,
    band_counts,
    ranking,
    totals,
)
from ber_automation.models import Country

# Image analysis in the app is capped: about a minute and some API credit per home, and a
# Streamlit session should not run for hours. Larger lists go through the CLI.
APP_IMAGE_LIMIT = 25
BAND_COLORS = {b: c for b, _, c in BER_BANDS}
BAND_NAMES = [b for b, _, _ in BER_BANDS]

ASSUMPTIONS = """
**How the community estimate works**

- **Census estimate (every home, instant, no AI credit).** Each address is located and matched to
  its CSO Census 2022 Small Area (80–120 homes). The area's mix of build periods, heating fuels
  and room counts gives typical homes, each rated by the same calculator. A listed home gets the
  area's most likely home (commonest era and fuel, commonest size); the whole Small Area gets the
  weighted mix of all typical homes, scaled to its number of households.
- **Image estimate (chosen homes).** The full single-home pipeline: satellite and Street View
  images read by the AI model, about a minute and some API credit per home. Where a home has both,
  the image estimate is used and the two are compared.
- **Assumptions of the census model:** era, fuel and size are taken as independent (the census
  publishes them separately); semi-detached in towns, detached in rural areas; rooms × 20 m²
  floor area, one storey under 70 m²; homes heated with coal, peat, LPG or other fuels are
  assumed to perform like the rest. Ireland only.
- **Accuracy so far:** on 21 homes with official BERs the census estimate gave the exact band for
  4 and within one band for 7; both estimates rate older homes better than their certificates.
  Use the results to compare and prioritise homes, not as ratings.
"""


# ---------------------------------------------------------------------------
# Charts (testable without Streamlit)
# ---------------------------------------------------------------------------

def make_band_chart(counts: dict[str, int], title: str = "Homes per BER band") -> go.Figure:
    bands = [b for b in BAND_NAMES if counts.get(b)]
    fig = go.Figure(go.Bar(
        x=bands, y=[counts[b] for b in bands],
        marker_color=[BAND_COLORS[b] for b in bands],
        text=[counts[b] for b in bands], textposition="outside", cliponaxis=False,
    ))
    top = max([counts[b] for b in bands], default=1)
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)), height=320,
        margin=dict(l=50, r=10, t=50, b=40), yaxis_title="Homes",
        yaxis=dict(range=[0, top * 1.18]), xaxis=dict(type="category"),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def make_area_band_chart(result: CommunityResult) -> go.Figure:
    """Band mix of all homes in the Small Areas (census model), weighted by households."""
    weights: dict[str, float] = {}
    for a in result.areas.values():
        for band, share in a.band_shares.items():
            weights[band] = weights.get(band, 0.0) + share * a.households
    rounded = {b: round(v) for b, v in weights.items() if round(v) > 0}
    return make_band_chart(rounded, "All homes in these Small Areas (census model)")


def make_map(rows: list[dict]) -> Optional[go.Figure]:
    pts = [r for r in rows if r.get("lat") is not None]
    if not pts:
        return None
    fig = go.Figure()
    for band in BAND_NAMES:
        group = [r for r in pts if r["band"] == band]
        if not group:
            continue
        fig.add_trace(go.Scattermap(
            lat=[r["lat"] for r in group], lon=[r["lng"] for r in group], mode="markers",
            marker=dict(size=13, color=BAND_COLORS[band]), name=band,
            text=[f"{r['address']}<br>{r['band']} · {r['kwh_m2']:.0f} kWh/m²/yr ({r['source']})"
                  for r in group],
            hoverinfo="text",
        ))
    lats, lngs = [r["lat"] for r in pts], [r["lng"] for r in pts]
    mid_lat = (max(lats) + min(lats)) / 2
    fig.update_layout(
        map=dict(style="carto-positron", zoom=fit_zoom(lats, lngs),
                 center=dict(lat=mid_lat, lon=(max(lngs) + min(lngs)) / 2)),
        height=460, margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(title="BER band", orientation="h", y=0),
    )
    return fig


def fit_zoom(lats: list[float], lngs: list[float], width_px: int = 800, height_px: int = 460) -> float:
    """Web-map zoom that shows every point with a margin (MapLibre: 512 px tiles, Mercator)."""
    lng_span = max(max(lngs) - min(lngs), 0.002) * 1.4
    lat_span = max(max(lats) - min(lats), 0.002) * 1.4
    cos_lat = math.cos(math.radians((max(lats) + min(lats)) / 2))
    z_lng = math.log2(360 * width_px / 512 / lng_span)
    z_lat = math.log2(360 * height_px / 512 * cos_lat / lat_span)
    return round(max(3.0, min(16.0, z_lng, z_lat)), 2)


def ranking_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    cols = ["rank", "id", "address", "band", "kwh_m2", "source", "floor_m2", "era", "type",
            "heating", "primary_mwh", "co2_t", "small_area", "lat", "lng"]
    writer = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def _saved_communities(base_dir: Path = DEFAULT_BASE_DIR) -> list[Path]:
    return sorted(base_dir.glob("*/community.json")) if base_dir.exists() else []


def render_community_page(
    run_async: Callable,
    show_home: Callable,
    labels: dict[str, dict[str, str]],
    provider: Optional[str] = None,
) -> None:
    """Draw the Community mode. *show_home(ber, key_suffix)* draws one home's result."""
    st.markdown("<div class='section-header'><h3>Community Assessment</h3></div>",
                unsafe_allow_html=True)
    st.caption("Rate every home on an address list at once: an instant census estimate for all "
               "of them, and image analysis for those you choose.")
    with st.expander("How it works and what it assumes"):
        st.markdown(ASSUMPTIONS)

    tab_new, tab_open = st.tabs(["New address list", "Open a saved community"])
    with tab_new:
        name = st.text_input("Community name", value="My community", key="comm_name")
        upload = st.file_uploader(
            "Address list (CSV with an address or eircode column, or one address per line)",
            type=["csv", "txt"], key="comm_upload",
        )
        pasted = st.text_area("…or paste addresses / Eircodes, one per line", height=120,
                              key="comm_paste")
        country = st.selectbox(
            "Country", [Country.IRELAND.value], format_func=lambda c: "Ireland (census data)",
            help="The census estimate needs the CSO Small Area data, so Ireland only for now.",
            key="comm_country",
        )
        text = upload.getvalue().decode("utf-8-sig") if upload is not None else pasted
        entries = read_addresses(text or "")
        st.caption(f"{len(entries)} addresses read." if entries else "No addresses yet.")
        if st.button("Quick census estimate", type="primary", disabled=not entries, key="comm_census"):
            bar = st.progress(0.0, text="Locating homes…")
            result = run_async(assess_community(
                entries, name, country=Country(country), analyse="none",
                progress=lambda d, t, m: bar.progress(min(d / max(t, 1), 1.0), text=m),
            ))
            bar.empty()
            st.session_state.community_result = result
            st.rerun()

    with tab_open:
        saved = _saved_communities()
        if saved:
            pick = st.selectbox("Saved communities", saved,
                                format_func=lambda p: p.parent.name, key="comm_saved")
            if st.button("Open", key="comm_open"):
                st.session_state.community_result = CommunityResult.load(pick)
                st.rerun()
        else:
            st.caption("No saved communities yet.")
        json_upload = st.file_uploader("…or open a community.json file", type=["json"],
                                       key="comm_json")
        if json_upload is not None and st.button("Open file", key="comm_open_file"):
            st.session_state.community_result = CommunityResult.model_validate_json(
                json_upload.getvalue())
            st.rerun()

    result: Optional[CommunityResult] = st.session_state.get("community_result")
    if result is None:
        return
    _render_result(result, run_async, show_home, labels, provider)


def _render_result(result, run_async, show_home, labels, provider) -> None:
    st.divider()
    st.markdown(f"### {result.name}")
    t = totals(result)
    c = st.columns(5)
    c[0].metric("Homes rated", f"{t['rated']} / {t['homes']}",
                help=f"{t['from_images']} from images, {t['rated'] - t['from_images']} census only")
    c[1].metric("Heat demand", f"{t['heat_demand_mwh']:,.0f} MWh/yr",
                help="Space heating the listed homes need: sum of HWB × floor area.")
    c[2].metric("Primary energy", f"{t['primary_mwh']:,.0f} MWh/yr")
    c[3].metric("CO₂", f"{t['co2_t']:,.1f} t/yr")
    c[4].metric("Average", f"{t['mean_primary_kwh_m2']:.0f} kWh/m²/yr",
                help="Total primary energy ÷ total floor area of the listed homes.")

    a = area_totals(result)
    if a["small_areas"]:
        st.caption(
            f"The listed homes are in {a['small_areas']} census Small Area(s) with "
            f"{a['households']:,} households in all. Census model for all of them: "
            f"{a['heat_demand_mwh']:,.0f} MWh/yr heat demand, {a['primary_mwh']:,.0f} MWh/yr primary "
            f"energy, {a['co2_t']:,.0f} t CO₂/yr, average {a['mean_primary_kwh_m2']:.0f} kWh/m²/yr."
        )

    rows = ranking(result)
    left, right = st.columns(2)
    with left:
        st.plotly_chart(make_band_chart(band_counts(result), "Listed homes per BER band"),
                        use_container_width=True, key="comm_bands")
    with right:
        if result.areas:
            st.plotly_chart(make_area_band_chart(result), use_container_width=True,
                            key="comm_area_bands")
    fig = make_map(rows)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True, key="comm_map")

    st.markdown("**Retrofit priority: worst first**")
    era, heat, kind = labels.get("era", {}), labels.get("heating", {}), labels.get("type", {})
    st.dataframe(
        [{
            "Rank": r["rank"], "Id": r["id"], "Address": r["address"], "Band": r["band"],
            "kWh/m²/yr": r["kwh_m2"], "From": r["source"], "Floor m²": r["floor_m2"],
            "Era": era.get(r["era"], r["era"]), "Type": kind.get(r["type"], r["type"]),
            "Heating": heat.get(r["heating"], r["heating"]), "MWh/yr primary": r["primary_mwh"],
            "t CO₂/yr": r["co2_t"],
        } for r in rows],
        hide_index=True, use_container_width=True,
    )
    d1, d2 = st.columns(2)
    d1.download_button("Download ranking (CSV)", ranking_csv(rows),
                       file_name=f"{community_dir(result.name).name}_ranking.csv", mime="text/csv")
    d2.download_button("Download full result (JSON)", result.model_dump_json(indent=1),
                       file_name=f"{community_dir(result.name).name}.json", mime="application/json")

    ag = agreement(result)
    if ag["n"]:
        st.caption(f"Census versus images, {ag['n']} homes analysed both ways: same band "
                   f"{ag['exact']}, within one band {ag['within_one']}.")

    problems = [(h, e) for h in result.homes for e in h.errors]
    if problems:
        with st.expander(f"Problems ({len(problems)})"):
            for h, e in problems:
                st.caption(f"{h.id} · {h.address}: {e}")

    _render_image_analysis(result, run_async, provider)

    rated = [h for h in result.homes if h.best is not None]
    if rated:
        with st.expander("One home in detail"):
            home = st.selectbox("Home", rated, format_func=lambda h: f"{h.id} · {h.address} ({h.source})",
                                key="comm_home")
            if home.source == "census":
                st.info("Census estimate: the most likely home for its Small Area, not this house's "
                        "own features. Analyse its images for a house-specific estimate.")
            show_home(home.best, f"community_{home.id}")


def _render_image_analysis(result: CommunityResult, run_async, provider) -> None:
    pending = [h for h in result.homes if h.coordinates is not None and h.image_estimate is None]
    with st.expander(f"Analyse with images ({len(pending)} homes not analysed yet)",
                     expanded=False):
        if not pending:
            st.caption("Every located home has been analysed.")
            return
        st.caption(f"About a minute and some API credit per home. Up to {APP_IMAGE_LIMIT} homes at a "
                   f"time here; for more, run scripts/assess_community.py with --analyse.")
        how = st.radio("Which homes", ["A sample spread over the Small Areas", "Chosen homes",
                                       "All not yet analysed"], key="comm_img_how")
        if how.startswith("A sample"):
            n = st.number_input("How many", 1, min(APP_IMAGE_LIMIT, len(pending)),
                                min(5, len(pending)), key="comm_img_n")
            choice = int(n)
        elif how.startswith("Chosen"):
            picked = st.multiselect("Homes", pending, format_func=lambda h: f"{h.id} · {h.address}",
                                    max_selections=APP_IMAGE_LIMIT, key="comm_img_pick")
            choice = [h.id for h in picked]
        else:
            choice = "all"
        count = (choice if isinstance(choice, int) else
                 len(pending) if choice == "all" else len(choice))
        too_many = count > APP_IMAGE_LIMIT
        if too_many:
            st.warning(f"{count} homes is more than {APP_IMAGE_LIMIT}: use the command line for this many.")
        if st.button(f"Analyse {count} home{'s' if count != 1 else ''}", type="primary",
                     disabled=too_many or count == 0, key="comm_img_go"):
            bar = st.progress(0.0, text="Starting…")
            entries = [{"id": h.id, "address": h.address} for h in result.homes]
            new = run_async(assess_community(
                entries, result.name, country=result.country, analyse=choice, provider=provider,
                progress=lambda d, t, m: bar.progress(min(d / max(t, 1), 1.0), text=m),
            ))
            bar.empty()
            st.session_state.community_result = new
            st.rerun()
