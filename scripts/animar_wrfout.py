#!/usr/bin/env python3
"""
Animación (GIF) de la temperatura a 2 m de una salida de WRF (wrfout).

Cada cuadro es una salida del modelo (con history_interval = 180, una cada 3 horas).
La escala de colores es fija para todos los cuadros, así se ve cómo se calienta
y se enfría la región entre el día y la noche.

Uso:
  python animar_wrfout.py /ruta/wrfout_d01_AAAA-MM-DD_HH:MM:SS [archivo_salida.gif]
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.animation import FuncAnimation, PillowWriter

PUNTO = ("Barranquilla", 10.96, -74.80)
UTC_OFFSET = -5  # Colombia
CUADROS_POR_SEGUNDO = 3


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ruta = sys.argv[1]
    salida = sys.argv[2] if len(sys.argv) > 2 else "t2_animacion.gif"

    ds = xr.open_dataset(ruta)
    tiempos = pd.to_datetime(ds["Times"].values.astype(str), format="%Y-%m-%d_%H:%M:%S")
    local = tiempos + pd.Timedelta(hours=UTC_OFFSET)
    lat = ds["XLAT"].isel(Time=0).values
    lon = ds["XLONG"].isel(Time=0).values
    tierra = ds["LANDMASK"].isel(Time=0).values
    t2 = ds["T2"].values - 273.15  # K a °C

    # Escala fija para todos los cuadros
    vmin = np.floor(np.percentile(t2, 1))
    vmax = np.ceil(np.percentile(t2, 99.5))

    fig, ax = plt.subplots(figsize=(7, 6.5))
    malla = ax.pcolormesh(lon, lat, t2[0], cmap="inferno", shading="auto", vmin=vmin, vmax=vmax)
    ax.contour(lon, lat, tierra, levels=[0.5], colors="w", linewidths=0.8)
    nombre, plat, plon = PUNTO
    ax.plot(plon, plat, "w^", markersize=8)
    ax.annotate(nombre, (plon, plat), xytext=(5, 5), textcoords="offset points",
                fontsize=9, color="w")
    fig.colorbar(malla, ax=ax, label="°C", shrink=0.85)
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.set_aspect("equal")
    titulo = ax.set_title("")
    fig.text(0.01, 0.01, "Simulación WRF de prueba (15 km), datos NCEP FNL. No es un pronóstico.",
             fontsize=7, color="gray")
    fig.tight_layout()

    def cuadro(n):
        malla.set_array(t2[n].ravel())
        titulo.set_text(f"Temperatura a 2 m\n{local[n]:%d %b %Y, %H:%M} hora local")
        return malla, titulo

    anim = FuncAnimation(fig, cuadro, frames=len(tiempos), blit=False)
    anim.save(salida, writer=PillowWriter(fps=CUADROS_POR_SEGUNDO), dpi=110)
    plt.close(fig)
    print(f"Animación guardada: {salida} ({len(tiempos)} cuadros)")


if __name__ == "__main__":
    main()
