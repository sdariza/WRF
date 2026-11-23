#!/usr/bin/env python3
"""
Gráficas rápidas de una salida de WRF (wrfout).

Genera:
  1. t2_max.png        Temperatura máxima a 2 m en todo el periodo
  2. t2_tarde.png      Temperatura a 2 m en la primera tarde (13:00 hora local)
  3. lluvia_total.png  Lluvia acumulada en el periodo
  4. t2_punto.png      Serie de tiempo de temperatura en un punto (Barranquilla)

Uso:
  python graficar_wrfout.py /ruta/wrfout_d01_AAAA-MM-DD_HH:MM:SS [carpeta_salida]
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

# Punto de interés: (nombre, latitud, longitud)
PUNTO = ("Barranquilla", 10.96, -74.80)
UTC_OFFSET = -5  # Colombia


def leer_wrfout(ruta):
    ds = xr.open_dataset(ruta)
    tiempos = pd.to_datetime(ds["Times"].values.astype(str), format="%Y-%m-%d_%H:%M:%S")
    lat = ds["XLAT"].isel(Time=0).values
    lon = ds["XLONG"].isel(Time=0).values
    tierra = ds["LANDMASK"].isel(Time=0).values
    return ds, tiempos, lat, lon, tierra


def punto_mas_cercano(lat, lon, plat, plon):
    d2 = (lat - plat) ** 2 + (lon - plon) ** 2
    return np.unravel_index(np.argmin(d2), d2.shape)


def mapa(campo, lat, lon, tierra, titulo, unidades, cmap, archivo, vmin=None, vmax=None):
    fig, ax = plt.subplots(figsize=(8, 7))
    m = ax.pcolormesh(lon, lat, campo, cmap=cmap, shading="auto", vmin=vmin, vmax=vmax)
    ax.contour(lon, lat, tierra, levels=[0.5], colors="k", linewidths=0.8)  # línea de costa
    nombre, plat, plon = PUNTO
    ax.plot(plon, plat, "k^", markersize=8)
    ax.annotate(nombre, (plon, plat), xytext=(5, 5), textcoords="offset points", fontsize=9)
    fig.colorbar(m, ax=ax, label=unidades, shrink=0.85)
    ax.set_title(titulo)
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(archivo, dpi=130)
    plt.close(fig)
    print(f"  guardado: {archivo}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ruta = sys.argv[1]
    salida = sys.argv[2] if len(sys.argv) > 2 else "graficas"
    os.makedirs(salida, exist_ok=True)

    ds, tiempos, lat, lon, tierra = leer_wrfout(ruta)
    local = tiempos + pd.Timedelta(hours=UTC_OFFSET)
    print(f"Archivo: {ruta}")
    print(f"Periodo (UTC): {tiempos[0]} a {tiempos[-1]}  ({len(tiempos)} salidas)")

    t2 = ds["T2"].values - 273.15  # K a °C
    lluvia = (ds["RAINC"] + ds["RAINNC"]).values
    lluvia_total = lluvia[-1] - lluvia[0]

    # 1. Máxima del periodo
    t2_max = t2.max(axis=0)
    mapa(t2_max, lat, lon, tierra,
         f"Temperatura máxima a 2 m\n{local[0]:%d %b %Y} a {local[-1]:%d %b %Y} (hora local)",
         "°C", "inferno", os.path.join(salida, "t2_max.png"))

    # 2. Primera tarde: salida más cercana a las 13:00 hora local
    objetivo = local[0].normalize() + pd.Timedelta(hours=13)
    if objetivo < local[0]:
        objetivo += pd.Timedelta(days=1)
    i_tarde = int(np.argmin(np.abs((local - objetivo).total_seconds())))
    mapa(t2[i_tarde], lat, lon, tierra,
         f"Temperatura a 2 m\n{local[i_tarde]:%d %b %Y %H:%M} hora local",
         "°C", "inferno", os.path.join(salida, "t2_tarde.png"))

    # 3. Lluvia acumulada
    mapa(lluvia_total, lat, lon, tierra,
         f"Lluvia acumulada\n{local[0]:%d %b} a {local[-1]:%d %b %Y}",
         "mm", "Blues", os.path.join(salida, "lluvia_total.png"), vmin=0)

    # 4. Serie de tiempo en el punto
    nombre, plat, plon = PUNTO
    j, i = punto_mas_cercano(lat, lon, plat, plon)
    serie = t2[:, j, i]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(local, serie, "o-", color="tab:red")
    ax.set_title(f"Temperatura a 2 m en {nombre} (punto de malla {lat[j, i]:.2f}, {lon[j, i]:.2f})")
    ax.set_ylabel("°C")
    ax.set_xlabel("Hora local")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    archivo = os.path.join(salida, "t2_punto.png")
    fig.savefig(archivo, dpi=130)
    plt.close(fig)
    print(f"  guardado: {archivo}")

    # Resumen numérico
    sobre_tierra = tierra > 0.5
    print("\nResumen:")
    print(f"  T2 máxima sobre tierra: {t2_max[sobre_tierra].max():.1f} °C")
    print(f"  T2 máxima en {nombre}: {serie.max():.1f} °C, mínima: {serie.min():.1f} °C")
    print(f"  Lluvia máxima acumulada: {lluvia_total.max():.1f} mm")
    print(f"  Lluvia acumulada en {nombre}: {lluvia_total[j, i]:.1f} mm")


if __name__ == "__main__":
    main()
