"""House diagram of the annual energy balance (kWh per year), drawn with Plotly shapes.

Heat comes in as internal gains, solar gains and heating from the boiler; it leaves by
transmission (walls, roof, floor, windows) and ventilation. Hot water is drawn as a tank fed by
the boiler. Arrow widths grow with the value so the largest flows stand out.
"""

from __future__ import annotations

import plotly.graph_objects as go

from ber_automation.models import HWBResult

GAIN = "#2E9E44"
SOLAR = "#E0A100"
HEAT = "#F47920"
LOSS = "#D7263D"
WATER = "#1F78B4"
LINE = "#1A1A2E"


def _kwh(v: float) -> str:
    return f"{v:,.0f} kWh/yr"


def _width(value: float, largest: float) -> float:
    """Arrow line width between 1.5 and 7 px, by share of the largest flow."""
    if largest <= 0:
        return 1.5
    return 1.5 + 5.5 * max(0.0, value) / largest


def make_house_energy_diagram(hw: HWBResult, heating_label: str = "Boiler") -> go.Figure:
    """Draw the house with its heat flows in kWh/yr (see module docstring)."""
    largest = max(
        hw.transmission_loss_kwh, hw.ventilation_loss_kwh, hw.internal_gains,
        hw.solar_gains, hw.heating_demand_kwh, hw.hot_water_kwh, 1.0,
    )
    fig = go.Figure()
    shapes = [
        # house body, roof, door, two windows with glazing bars
        dict(type="rect", x0=30, y0=10, x1=64, y1=40, line=dict(color=LINE, width=2),
             fillcolor="#F4F1EA"),
        dict(type="path", path="M 27,40 L 47,56 L 67,40 Z", line=dict(color=LINE, width=2),
             fillcolor="#D9D2C3"),
        dict(type="rect", x0=45, y0=10, x1=49.5, y1=22, line=dict(color=LINE, width=1.5),
             fillcolor="#B5A58A"),
        dict(type="rect", x0=34, y0=26, x1=42, y1=35, line=dict(color=LINE, width=1.5),
             fillcolor="#CFE8F7"),
        dict(type="rect", x0=52, y0=26, x1=60, y1=35, line=dict(color=LINE, width=1.5),
             fillcolor="#CFE8F7"),
        dict(type="line", x0=38, y0=26, x1=38, y1=35, line=dict(color=LINE, width=1)),
        dict(type="line", x0=34, y0=30.5, x1=42, y1=30.5, line=dict(color=LINE, width=1)),
        dict(type="line", x0=56, y0=26, x1=56, y1=35, line=dict(color=LINE, width=1)),
        dict(type="line", x0=52, y0=30.5, x1=60, y1=30.5, line=dict(color=LINE, width=1)),
        # boiler and the pipes to the house and to the hot-water tank
        dict(type="rect", x0=80, y0=8, x1=94, y1=22, line=dict(color=LINE, width=2),
             fillcolor="#FBE3CF"),
        dict(type="line", x0=87, y0=22, x1=87, y1=30, line=dict(color=HEAT, width=3)),
        dict(type="line", x0=87, y0=8, x1=87, y1=-6, line=dict(color=WATER, width=3)),
        dict(type="line", x0=87, y0=-6, x1=58, y1=-6, line=dict(color=WATER, width=3)),
        # hot-water tank with a tap
        dict(type="rect", x0=40, y0=-14, x1=58, y1=0, line=dict(color=LINE, width=2),
             fillcolor="#D6E9F8"),
        dict(type="path", path="M 40,-9 C 44,-7 48,-11 52,-9 C 54,-8 56,-9 58,-9 L 58,-14 L 40,-14 Z",
             line=dict(width=0), fillcolor="#8EC3EA"),
        dict(type="line", x0=40, y0=-3, x1=35, y1=-3, line=dict(color=LINE, width=2)),
        dict(type="line", x0=35, y0=-3, x1=35, y1=-6, line=dict(color=LINE, width=2)),
        # sun
        dict(type="circle", x0=2, y0=40, x1=10, y1=48, line=dict(color=SOLAR, width=2),
             fillcolor="#FFE08A"),
    ]
    for shape in shapes:
        fig.add_shape(**shape, layer="below")

    def arrow(x, y, ax, ay, color, value, text, xanchor="center", yanchor="middle"):
        """Arrow from (ax, ay) to (x, y); the label sits at the tail."""
        fig.add_annotation(
            x=x, y=y, ax=ax, ay=ay, xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=_width(value, largest),
            arrowcolor=color, text="",
        )
        fig.add_annotation(
            x=ax, y=ay, xref="x", yref="y", showarrow=False, text=text,
            font=dict(size=12, color=color), xanchor=xanchor, yanchor=yanchor, align="center",
        )

    # gains in
    arrow(37, 31, 11, 42, SOLAR, hw.solar_gains, "")
    fig.add_annotation(
        x=6, y=38.5, xref="x", yref="y", showarrow=False, yanchor="top",
        text=f"<b>Solar gains</b><br>{_kwh(hw.solar_gains)}",
        font=dict(size=12, color=SOLAR), align="center",
    )
    arrow(33, 18, 14, 18, GAIN, hw.internal_gains,
          f"<b>Internal gains</b><br>{_kwh(hw.internal_gains)}<br>"
          "<span style='font-size:10px'>people, cooking,<br>appliances, lighting</span>",
          xanchor="right")
    arrow(64, 30, 87, 30, HEAT, hw.heating_demand_kwh, "")
    fig.add_annotation(
        x=87, y=32, xref="x", yref="y", showarrow=False, yanchor="bottom",
        text=(f"<b>Heating</b><br>{_kwh(hw.heating_demand_kwh)}<br>"
              f"<span style='font-size:10px'>= HWB {hw.hwb:.1f} kWh/m²/yr × {hw.floor_area:.0f} m²</span>"),
        font=dict(size=12, color=HEAT), align="center",
    )
    fig.add_annotation(x=87, y=15, xref="x", yref="y", showarrow=False,
                       text=f"<b>{heating_label}</b>", font=dict(size=11, color=LINE))

    # losses out
    arrow(64, 64, 58, 48, LOSS, hw.transmission_loss_kwh, "")
    fig.add_annotation(
        x=66, y=64, xref="x", yref="y", showarrow=False, xanchor="left",
        text=(f"<b>Transmission loss</b><br>{_kwh(hw.transmission_loss_kwh)}<br>"
              "<span style='font-size:10px'>walls, roof, floor, windows</span>"),
        font=dict(size=12, color=LOSS), align="left",
    )
    arrow(30, 64, 36, 48, LOSS, hw.ventilation_loss_kwh, "")
    fig.add_annotation(
        x=28, y=64, xref="x", yref="y", showarrow=False, xanchor="right",
        text=(f"<b>Ventilation loss</b><br>{_kwh(hw.ventilation_loss_kwh)}<br>"
              "<span style='font-size:10px'>air exchange</span>"),
        font=dict(size=12, color=LOSS), align="right",
    )

    # hot water
    fig.add_annotation(
        x=60, y=-10, xref="x", yref="y", showarrow=False, xanchor="left",
        text=f"<b>Hot water</b><br>{_kwh(hw.hot_water_kwh)}",
        font=dict(size=12, color=WATER), align="left",
    )

    fig.update_xaxes(visible=False, range=[-8, 108], fixedrange=True)
    fig.update_yaxes(visible=False, range=[-17, 72], fixedrange=True, scaleanchor="x", scaleratio=1)
    fig.update_layout(
        height=430, margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
    )
    return fig


def balance_line(hw: HWBResult) -> str:
    """One line checking losses against gains plus heating (all kWh/yr)."""
    losses = hw.transmission_loss_kwh + hw.ventilation_loss_kwh
    supplied = hw.internal_gains + hw.solar_gains + hw.heating_demand_kwh
    surplus = supplied - losses > 1
    line = (f"Heat lost {losses:,.0f} kWh/yr (transmission {hw.transmission_loss_kwh:,.0f} + "
            f"ventilation {hw.ventilation_loss_kwh:,.0f}) {'<' if surplus else '='} heat supplied "
            f"{supplied:,.0f} kWh/yr (internal {hw.internal_gains:,.0f} + solar {hw.solar_gains:,.0f} + "
            f"heating {hw.heating_demand_kwh:,.0f}).")
    if surplus:
        line += (" The free gains exceed the losses, so no heating is needed; "
                 "the surplus is not counted.")
    return line
