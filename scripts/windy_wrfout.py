#!/usr/bin/env python3
"""
Windy-style plots from a WRF output file (wrfout): smooth temperature field
with a Windy-like color palette and white 10 m wind streamlines.

Outputs:
  windy_afternoon.png   First afternoon (1 PM local time)
  windy_animation.gif   Every model output, animated

Usage:
  python windy_wrfout.py /path/wrfout_d01_YYYY-MM-DD_HH:MM:SS [output_folder]
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import LinearSegmentedColormap

UTC_OFFSET = -5
TZ_NAME = "COT"
EDGE_CELLS = 8
ANIMATION_SECONDS = 10   # length of the GIF, whatever the number of outputs
CITIES = [
    ("Barranquilla", 10.96, -74.80), ("Cartagena", 10.39, -75.51),
    ("Santa Marta", 11.24, -74.20), ("Valledupar", 10.46, -73.25),
    ("Montería", 8.75, -75.88), ("Riohacha", 11.54, -72.91),
    ("Cúcuta", 7.89, -72.50), ("Bucaramanga", 7.12, -73.12),
    ("Medellín", 6.24, -75.58), ("Maracaibo", 10.65, -71.64),
]
CREDIT = "WRF test run (15 km) · NCEP FNL data · Not a forecast"
BG = "#1c1c1e"

# Windy-like temperature palette (°C)
_STOPS = [(10, "#3a4fb5"), (15, "#3b8fd0"), (20, "#3cbfa8"), (24, "#8fd14f"),
          (27, "#e6d43a"), (30, "#f29b2e"), (33, "#e8572b"), (36, "#c62a3a"),
          (40, "#8e1a5a")]
TMIN, TMAX = _STOPS[0][0], _STOPS[-1][0]
WINDY = LinearSegmentedColormap.from_list(
    "windy", [((t - TMIN) / (TMAX - TMIN), c) for t, c in _STOPS])
HALO = [pe.withStroke(linewidth=2.5, foreground="black")]


def load(path):
    ds = xr.open_dataset(path)
    times = pd.to_datetime(ds["Times"].values.astype(str), format="%Y-%m-%d_%H:%M:%S")
    e = EDGE_CELLS
    sl = (slice(e, -e or None), slice(e, -e or None))
    tsl = (slice(None),) + sl
    return dict(
        local=times + pd.Timedelta(hours=UTC_OFFSET),
        lat=ds["XLAT"].isel(Time=0).values[sl],
        lon=ds["XLONG"].isel(Time=0).values[sl],
        land=ds["LANDMASK"].isel(Time=0).values[sl],
        t2=ds["T2"].values[tsl] - 273.15,
        u=ds["U10"].values[tsl],
        v=ds["V10"].values[tsl],
    )


def setup(d):
    """Figure drawn in grid-index space (regular grid, needed by streamplot)."""
    ny, nx = d["lat"].shape
    fig = plt.figure(figsize=(8, 8.4), facecolor=BG)
    ax = fig.add_axes([0, 0.11, 1, 0.77])
    ax.set_facecolor(BG)
    ax.set_xlim(0, nx - 1)
    ax.set_ylim(0, ny - 1)
    ax.axis("off")
    img = ax.imshow(d["t2"][0], origin="lower", cmap=WINDY, vmin=TMIN, vmax=TMAX,
                    interpolation="bicubic", extent=(0, nx - 1, 0, ny - 1), zorder=1)
    ax.contour(d["land"], levels=[0.5], colors="white", linewidths=0.7, alpha=0.8, zorder=3)
    for name, clat, clon in CITIES:
        if d["lat"].min() < clat < d["lat"].max() and d["lon"].min() < clon < d["lon"].max():
            j, i = np.unravel_index(np.argmin((d["lat"] - clat) ** 2 + (d["lon"] - clon) ** 2),
                                    d["lat"].shape)
            ax.plot(i, j, "o", ms=3.5, color="white", zorder=5)
            ax.annotate(name, (i, j), xytext=(4, 3), textcoords="offset points", fontsize=9,
                        color="white", path_effects=HALO, zorder=5)
    title = fig.text(0.03, 0.965, "Temperature & wind", fontsize=18, fontweight="bold",
                     color="white", va="top")
    sub = fig.text(0.03, 0.925, "", fontsize=11, color="#c7c7cc", va="top")

    cax = fig.add_axes([0.25, 0.065, 0.5, 0.018])
    cb = fig.colorbar(img, cax=cax, orientation="horizontal")
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors="#c7c7cc", labelsize=9, length=0)
    cb.set_label("°C   ·   white lines: 10 m wind", color="#c7c7cc", fontsize=9)
    fig.text(0.03, 0.015, CREDIT, fontsize=7.5, color="#8e8e93")
    return fig, ax, img, sub, title


def draw_wind(ax, d, n):
    u, v = d["u"][n], d["v"][n]
    speed = np.hypot(u, v)
    lw = 0.3 + 0.9 * speed / max(speed.max(), 1e-6)
    return ax.streamplot(np.arange(u.shape[1]), np.arange(u.shape[0]), u, v,
                         color=(1, 1, 1, 0.55), linewidth=lw, density=1.6, arrowsize=0.6,
                         zorder=2)


def clear_wind(ax, sp):
    sp.lines.remove()
    for p in list(ax.patches):
        p.remove()


def label(t):
    return f"{t:%b %d, %Y · %H:%M} local time ({TZ_NAME})"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else "windy"
    os.makedirs(out, exist_ok=True)
    d = load(sys.argv[1])
    local = d["local"]

    # Static afternoon map
    target = local[0].normalize() + pd.Timedelta(hours=13)
    if target < local[0]:
        target += pd.Timedelta(days=1)
    n = int(np.argmin(np.abs((local - target).total_seconds())))
    fig, ax, img, sub, _ = setup(d)
    img.set_data(d["t2"][n])
    sub.set_text(label(local[n]))
    draw_wind(ax, d, n)
    path = os.path.join(out, "windy_afternoon.png")
    fig.savefig(path, dpi=135, facecolor=BG)
    plt.close(fig)
    print(f"  saved: {path}")

    # Animation
    fig, ax, img, sub, _ = setup(d)
    state = {"sp": None}

    def frame(k):
        if state["sp"] is not None:
            clear_wind(ax, state["sp"])
        img.set_data(d["t2"][k])
        sub.set_text(label(local[k]))
        state["sp"] = draw_wind(ax, d, k)
        return [img, sub]

    anim = FuncAnimation(fig, frame, frames=len(local), blit=False)
    path = os.path.join(out, "windy_animation.gif")
    anim.save(path, writer=PillowWriter(fps=len(local) / ANIMATION_SECONDS), dpi=100, savefig_kwargs={"facecolor": BG})
    plt.close(fig)
    print(f"  saved: {path} ({len(local)} frames)")


if __name__ == "__main__":
    main()
