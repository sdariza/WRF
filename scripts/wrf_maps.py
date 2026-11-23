#!/usr/bin/env python3
"""
News-style maps from a WRF output file (wrfout), with a realistic basemap.

Outputs (in the output folder):
  temp_max.png         Maximum 2 m temperature over the whole run
  temp_afternoon.png   2 m temperature on the first afternoon (1 PM local time)
  rain_total.png       Accumulated rainfall
  temp_point.png       2 m temperature time series at one city
  temp_animation.gif   Animated 2 m temperature (one frame per model output)

Usage:
  python wrf_maps.py /path/wrfout_d01_YYYY-MM-DD_HH:MM:SS [output_folder]

Requires: xarray netCDF4 matplotlib contextily pyproj
The basemap tiles are downloaded from the internet. If that fails, the maps
are still drawn on a plain dark background.
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
from pyproj import Transformer

try:
    import contextily as ctx
except ImportError:
    ctx = None

# ---------------------------------------------------------------- settings
BASEMAP = "satellite"      # "satellite", "dark", "light" or "none"
TEMP_CMAP = "viridis"
RAIN_CMAP = "viridis"
OVERLAY_ALPHA = 0.70       # transparency of the data over the basemap
EDGE_CELLS = 8             # grid cells hidden at each border (boundary artifacts)
UTC_OFFSET = -5            # Colombia
TZ_NAME = "COT"
POINT = ("Barranquilla", 10.96, -74.80)
CITIES = [
    ("Barranquilla", 10.96, -74.80), ("Cartagena", 10.39, -75.51),
    ("Santa Marta", 11.24, -74.20), ("Valledupar", 10.46, -73.25),
    ("Montería", 8.75, -75.88), ("Sincelejo", 9.30, -75.40),
    ("Riohacha", 11.54, -72.91), ("Cúcuta", 7.89, -72.50),
    ("Bucaramanga", 7.12, -73.12), ("Medellín", 6.24, -75.58),
    ("Bogotá", 4.71, -74.07), ("Maracaibo", 10.65, -71.64),
]
CREDIT = "WRF test run (15 km) · Data: NCEP FNL · Not a forecast"

BG = "#0e1117"
FG = "#e8eaed"
MUTED = "#9aa0a6"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "text.color": FG,
    "axes.labelcolor": FG,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
})

TO_MERC = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
HALO = [pe.withStroke(linewidth=2.5, foreground="black")]


# ---------------------------------------------------------------- data
def load(path):
    ds = xr.open_dataset(path)
    times = pd.to_datetime(ds["Times"].values.astype(str), format="%Y-%m-%d_%H:%M:%S")
    local = times + pd.Timedelta(hours=UTC_OFFSET)
    lat = ds["XLAT"].isel(Time=0).values
    lon = ds["XLONG"].isel(Time=0).values
    e = EDGE_CELLS
    crop = (slice(e, -e or None), slice(e, -e or None))
    lat, lon = lat[crop], lon[crop]
    x, y = TO_MERC.transform(lon, lat)
    t2 = ds["T2"].values[(slice(None),) + crop] - 273.15
    rain = (ds["RAINC"] + ds["RAINNC"]).values[(slice(None),) + crop]
    return dict(local=local, lat=lat, lon=lon, x=x, y=y, t2=t2, rain=rain)


def nearest(lat, lon, plat, plon):
    d2 = (lat - plat) ** 2 + (lon - plon) ** 2
    return np.unravel_index(np.argmin(d2), d2.shape)


def fmt_time(t):
    return t.strftime("%b %d, %Y · %I:%M %p ").replace(" 0", " ") + TZ_NAME


# ---------------------------------------------------------------- map frame
def base_map(d, title, subtitle):
    fig = plt.figure(figsize=(8, 8.6))
    ax = fig.add_axes([0.04, 0.17, 0.92, 0.70])
    ax.set_xlim(d["x"].min(), d["x"].max())
    ax.set_ylim(d["y"].min(), d["y"].max())
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    if BASEMAP != "none" and ctx is not None:
        providers = {
            "satellite": ctx.providers.Esri.WorldImagery,
            "dark": ctx.providers.CartoDB.DarkMatter,
            "light": ctx.providers.CartoDB.Positron,
        }
        try:
            ctx.add_basemap(ax, source=providers[BASEMAP], attribution_size=6)
        except Exception as err:  # no internet, tile server down...
            print(f"  (basemap not available: {err.__class__.__name__}; plain background used)")

    # cities inside the map
    for name, clat, clon in CITIES:
        if d["lat"].min() < clat < d["lat"].max() and d["lon"].min() < clon < d["lon"].max():
            cx, cy = TO_MERC.transform(clon, clat)
            ax.plot(cx, cy, "o", ms=4, color="white", mec="black", mew=0.8, zorder=5)
            ax.annotate(name, (cx, cy), xytext=(5, 4), textcoords="offset points",
                        fontsize=9, color="white", path_effects=HALO, zorder=5)

    fig.text(0.04, 0.955, title, fontsize=20, fontweight="bold", va="top")
    sub = fig.text(0.04, 0.905, subtitle, fontsize=12, color=MUTED, va="top")
    fig.text(0.04, 0.02, CREDIT, fontsize=8, color=MUTED)
    return fig, ax, sub


def colorbar(fig, mappable, label):
    cax = fig.add_axes([0.20, 0.10, 0.60, 0.022])
    cb = fig.colorbar(mappable, cax=cax, orientation="horizontal")
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=9, length=0)
    cb.set_label(label, fontsize=10, color=FG)
    return cb


# ---------------------------------------------------------------- products
def temp_map(d, field, title, subtitle, path, vmin=None, vmax=None):
    fig, ax, _ = base_map(d, title, subtitle)
    m = ax.pcolormesh(d["x"], d["y"], field, cmap=TEMP_CMAP, shading="auto",
                      alpha=OVERLAY_ALPHA, vmin=vmin, vmax=vmax, zorder=2)
    colorbar(fig, m, "Temperature (°C)")
    fig.savefig(path, dpi=135)
    plt.close(fig)
    print(f"  saved: {path}")


def rain_map(d, field, title, subtitle, path):
    fig, ax, _ = base_map(d, title, subtitle)
    masked = np.ma.masked_less(field, 0.5)  # no rain = transparent
    vmax = max(5.0, float(np.nanpercentile(field, 99.5)))
    m = ax.pcolormesh(d["x"], d["y"], masked, cmap=RAIN_CMAP, shading="auto",
                      alpha=0.85, vmin=0.5, vmax=vmax, zorder=2)
    colorbar(fig, m, "Rainfall (mm)")
    fig.savefig(path, dpi=135)
    plt.close(fig)
    print(f"  saved: {path}")


def point_series(d, path):
    name, plat, plon = POINT
    j, i = nearest(d["lat"], d["lon"], plat, plon)
    s = d["t2"][:, j, i]
    t = d["local"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    fig.subplots_adjust(left=0.08, right=0.97, top=0.78, bottom=0.18)
    color = matplotlib.colormaps[TEMP_CMAP](0.75)
    ax.fill_between(t, s, s.min() - 1, color=color, alpha=0.18)
    ax.plot(t, s, "-o", color=color, lw=2.2, ms=4)
    k = int(np.argmax(s))
    ax.annotate(f"{s[k]:.1f} °C", (t[k], s[k]), xytext=(0, 8), textcoords="offset points",
                ha="center", fontsize=10, fontweight="bold")
    ax.set_ylim(s.min() - 1, s.max() + 1.5)
    ax.set_ylabel("°C")
    ax.grid(axis="y", color="#2a2f3a", lw=0.8)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#2a2f3a")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d\n%I %p"))
    fig.text(0.08, 0.95, f"Air temperature in {name}", fontsize=17, fontweight="bold", va="top")
    fig.text(0.08, 0.87, f"2 m, local time ({TZ_NAME}) · grid point {d['lat'][j, i]:.2f}°, "
             f"{d['lon'][j, i]:.2f}°", fontsize=10, color=MUTED, va="top")
    fig.text(0.08, 0.02, CREDIT, fontsize=8, color=MUTED)
    fig.savefig(path, dpi=135)
    plt.close(fig)
    print(f"  saved: {path}")
    return s


def animation(d, path, fps=3):
    t2 = d["t2"]
    vmin = np.floor(np.percentile(t2, 1))
    vmax = np.ceil(np.percentile(t2, 99.5))
    fig, ax, sub = base_map(d, "Air temperature (2 m)", fmt_time(d["local"][0]))
    m = ax.pcolormesh(d["x"], d["y"], t2[0], cmap=TEMP_CMAP, shading="auto",
                      alpha=OVERLAY_ALPHA, vmin=vmin, vmax=vmax, zorder=2)
    colorbar(fig, m, "Temperature (°C)")

    def frame(n):
        m.set_array(t2[n].ravel())
        sub.set_text(fmt_time(d["local"][n]))
        return m, sub

    anim = FuncAnimation(fig, frame, frames=len(t2), blit=False)
    anim.save(path, writer=PillowWriter(fps=fps), dpi=100)
    plt.close(fig)
    print(f"  saved: {path} ({len(t2)} frames)")


# ---------------------------------------------------------------- main
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "maps"
    os.makedirs(out, exist_ok=True)

    d = load(path)
    local = d["local"]
    print(f"File: {path}")
    print(f"Period ({TZ_NAME}): {local[0]} to {local[-1]} ({len(local)} outputs)")

    t2max = d["t2"].max(axis=0)
    period = f"{local[0]:%b %d} – {local[-1]:%b %d, %Y}"
    temp_map(d, t2max, "Maximum temperature", period,
             os.path.join(out, "temp_max.png"))

    target = local[0].normalize() + pd.Timedelta(hours=13)
    if target < local[0]:
        target += pd.Timedelta(days=1)
    n = int(np.argmin(np.abs((local - target).total_seconds())))
    temp_map(d, d["t2"][n], "Afternoon temperature", fmt_time(local[n]),
             os.path.join(out, "temp_afternoon.png"))

    rain = d["rain"][-1] - d["rain"][0]
    rain_map(d, rain, "Accumulated rainfall", period, os.path.join(out, "rain_total.png"))

    s = point_series(d, os.path.join(out, "temp_point.png"))
    animation(d, os.path.join(out, "temp_animation.gif"))

    name = POINT[0]
    j, i = nearest(d["lat"], d["lon"], POINT[1], POINT[2])
    print("\nSummary:")
    print(f"  Highest temperature in the map: {t2max.max():.1f} °C")
    print(f"  {name}: max {s.max():.1f} °C, min {s.min():.1f} °C, rain {rain[j, i]:.1f} mm")


if __name__ == "__main__":
    main()
