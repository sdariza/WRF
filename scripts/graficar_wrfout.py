#!/usr/bin/env python3
"""
Quick plots from a WRF output file (wrfout).

Outputs:
  t2_max.png        Maximum 2 m temperature over the whole run
  t2_afternoon.png  2 m temperature map on the first afternoon (1 PM local)
                    together with the time series at the point of interest
  rain_total.png    Accumulated rainfall
  t2_point.png      2 m temperature time series at the point of interest

Usage:
  python graficar_wrfout.py /path/wrfout_d01_YYYY-MM-DD_HH:MM:SS [output_folder]
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

POINT = ("Barranquilla", 10.96, -74.80)   # (name, latitude, longitude)
UTC_OFFSET = -5                           # Colombia
TZ_NAME = "COT"
CMAP = "viridis"
EDGE_CELLS = 8                            # hide border cells (boundary artifacts)


def load(path):
    ds = xr.open_dataset(path)
    times = pd.to_datetime(ds["Times"].values.astype(str), format="%Y-%m-%d_%H:%M:%S")
    e = EDGE_CELLS
    sl = (slice(e, -e or None), slice(e, -e or None))
    lat = ds["XLAT"].isel(Time=0).values[sl]
    lon = ds["XLONG"].isel(Time=0).values[sl]
    land = ds["LANDMASK"].isel(Time=0).values[sl]
    t2 = ds["T2"].values[(slice(None),) + sl] - 273.15
    rain = (ds["RAINC"] + ds["RAINNC"]).values[(slice(None),) + sl]
    local = times + pd.Timedelta(hours=UTC_OFFSET)
    return dict(local=local, lat=lat, lon=lon, land=land, t2=t2, rain=rain)


def nearest(lat, lon, plat, plon):
    d2 = (lat - plat) ** 2 + (lon - plon) ** 2
    return np.unravel_index(np.argmin(d2), d2.shape)


def draw_map(ax, d, field, cmap, vmin=None, vmax=None):
    m = ax.pcolormesh(d["lon"], d["lat"], field, cmap=cmap, shading="auto", vmin=vmin, vmax=vmax)
    ax.contour(d["lon"], d["lat"], d["land"], levels=[0.5], colors="k", linewidths=0.8)
    name, plat, plon = POINT
    ax.plot(plon, plat, "k^", markersize=8)
    ax.annotate(name, (plon, plat), xytext=(5, 5), textcoords="offset points", fontsize=9)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    return m


def draw_series(ax, d, series, highlight=None):
    ax.plot(d["local"], series, "o-", color="tab:red")
    if highlight is not None:
        ax.axvline(d["local"][highlight], color="gray", lw=1, ls="--")
        ax.plot(d["local"][highlight], series[highlight], "o", ms=11,
                mfc="none", mec="k", mew=1.5)
    ax.set_ylabel("°C")
    ax.set_xlabel(f"Local time ({TZ_NAME})")
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))


def save(fig, path):
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"  saved: {path}")


def simple_map(d, field, title, label, cmap, path, vmin=None):
    fig, ax = plt.subplots(figsize=(8, 7))
    m = draw_map(ax, d, field, cmap, vmin=vmin)
    fig.colorbar(m, ax=ax, label=label, shrink=0.85)
    ax.set_title(title)
    fig.tight_layout()
    save(fig, path)


def map_with_series(d, n, series, path):
    """Map at output n (top) + time series at the point (bottom)."""
    fig, (ax_map, ax_ts) = plt.subplots(2, 1, figsize=(8, 10),
                                        gridspec_kw={"height_ratios": [3, 1.1]})
    m = draw_map(ax_map, d, d["t2"][n], CMAP)
    fig.colorbar(m, ax=ax_map, label="°C", shrink=0.85)
    ax_map.set_title(f"2 m temperature\n{d['local'][n]:%b %d, %Y %H:%M} local time ({TZ_NAME})")
    draw_series(ax_ts, d, series, highlight=n)
    ax_ts.set_title(f"2 m temperature in {POINT[0]}", fontsize=10)
    fig.tight_layout()
    save(fig, path)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else "plots"
    os.makedirs(out, exist_ok=True)
    d = load(sys.argv[1])
    local = d["local"]
    print(f"Period ({TZ_NAME}): {local[0]} to {local[-1]} ({len(local)} outputs)")

    j, i = nearest(d["lat"], d["lon"], POINT[1], POINT[2])
    series = d["t2"][:, j, i]
    period = f"{local[0]:%b %d} to {local[-1]:%b %d, %Y} (local time)"

    t2max = d["t2"].max(axis=0)
    simple_map(d, t2max, f"Maximum 2 m temperature\n{period}", "°C", CMAP,
               os.path.join(out, "t2_max.png"))

    target = local[0].normalize() + pd.Timedelta(hours=13)
    if target < local[0]:
        target += pd.Timedelta(days=1)
    n = int(np.argmin(np.abs((local - target).total_seconds())))
    map_with_series(d, n, series, os.path.join(out, "t2_afternoon.png"))

    rain = d["rain"][-1] - d["rain"][0]
    simple_map(d, rain, f"Accumulated rainfall\n{period}", "mm", "Blues",
               os.path.join(out, "rain_total.png"), vmin=0)

    fig, ax = plt.subplots(figsize=(9, 4))
    draw_series(ax, d, series)
    ax.set_title(f"2 m temperature in {POINT[0]} "
                 f"(grid point {d['lat'][j, i]:.2f}, {d['lon'][j, i]:.2f})")
    fig.tight_layout()
    save(fig, os.path.join(out, "t2_point.png"))

    land = d["land"] > 0.5
    print("\nSummary:")
    print(f"  Max 2 m temperature over land: {t2max[land].max():.1f} °C")
    print(f"  {POINT[0]}: max {series.max():.1f} °C, min {series.min():.1f} °C, "
          f"rain {rain[j, i]:.1f} mm")


if __name__ == "__main__":
    main()
