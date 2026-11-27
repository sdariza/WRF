#!/usr/bin/env bash
# Compila todo lo necesario para correr WRF: librerías, WRF (em_real, dmpar), WPS
# y baja los datos geográficos de baja resolución. Si algo ya está compilado, lo salta.
#
# Uso: bash scripts/build_wrf.sh
# Variables opcionales:
#   WRF_HOME     carpeta de trabajo (por defecto ~/wrf_build)
#   WRF_DEPS     librerías (por defecto $WRF_HOME/deps)
#   WRF_VERSION  etiqueta de WRF (por defecto v4.6.1)
#   WPS_VERSION  etiqueta de WPS (por defecto v4.6.0)
#   LOG_DIR      dónde copiar los logs de compilación (por defecto $WRF_HOME/logs)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export WRF_HOME="${WRF_HOME:-$HOME/wrf_build}"
export WRF_DEPS="${WRF_DEPS:-$WRF_HOME/deps}"
WRF_VERSION="${WRF_VERSION:-v4.6.1}"
WPS_VERSION="${WPS_VERSION:-v4.6.0}"
LOG_DIR="${LOG_DIR:-$WRF_HOME/logs}"
JOBS="${JOBS:-$(nproc)}"
GEOG_URL="https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_low_res_mandatory.tar.gz"

mkdir -p "$WRF_HOME" "$LOG_DIR"
echo "==> Carpeta de trabajo: $WRF_HOME  (núcleos: $JOBS)"

# 1. Librerías (zlib, netCDF, mpich). install_deps.sh ya salta lo instalado.
bash "$SCRIPT_DIR/install_deps.sh"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/env.sh"
export WRFIO_NCD_LARGE_FILE_SUPPORT=1

gfortran_new() { [ "$(gfortran -dumpversion | cut -d. -f1)" -ge 10 ]; }

# Muestra el final del log y los errores si una compilación falla
fail() {
  local log="$1" msg="$2"
  echo "ERROR: $msg"
  echo "---- Errores en $log ----"
  grep -n -i -E "error|undefined reference" "$log" | head -n 40 || true
  echo "---- Últimas líneas de $log ----"
  tail -n 60 "$log"
  exit 1
}

# 2. WRF
cd "$WRF_HOME"
if [ -x WRF/main/wrf.exe ] && [ -x WRF/main/real.exe ]; then
  echo "==> WRF ya está compilado, se salta"
else
  echo "==> WRF $WRF_VERSION"
  if [ ! -d WRF ]; then
    git clone --depth 1 --branch "$WRF_VERSION" --recurse-submodules --shallow-submodules \
      https://github.com/wrf-model/WRF.git WRF
  fi
  cd WRF
  # 34 = GNU (gfortran/gcc) dmpar; 1 = nesting básico
  printf '34\n1\n' | ./configure > "$LOG_DIR/wrf_configure.log" 2>&1 \
    || fail "$LOG_DIR/wrf_configure.log" "falló ./configure de WRF"
  ./compile -j "$JOBS" em_real > "$LOG_DIR/wrf_compile.log" 2>&1 || true
  [ -x main/wrf.exe ] && [ -x main/real.exe ] \
    || fail "$LOG_DIR/wrf_compile.log" "WRF no generó wrf.exe / real.exe"
  echo "==> WRF compilado"
fi

# 3. WPS (con sus propias librerías GRIB2: zlib, libpng, jasper)
cd "$WRF_HOME"
if [ -e WPS/geogrid/src/geogrid.exe ] && [ -e WPS/ungrib/src/ungrib.exe ] && [ -e WPS/metgrid/src/metgrid.exe ]; then
  echo "==> WPS ya está compilado, se salta"
else
  echo "==> WPS $WPS_VERSION"
  if [ ! -d WPS ]; then
    git clone --depth 1 --branch "$WPS_VERSION" https://github.com/wrf-model/WPS.git WPS
  fi
  cd WPS
  (
    # --build-grib2-libs compila su propio jasper; no mezclar con el de env.sh
    unset JASPERLIB JASPERINC
    export WRF_DIR="$WRF_HOME/WRF"
    # 1 = Linux x86_64, gfortran (serial)
    printf '1\n' | ./configure --build-grib2-libs > "$LOG_DIR/wps_configure.log" 2>&1 \
      || fail "$LOG_DIR/wps_configure.log" "falló ./configure de WPS"
    if gfortran_new; then
      sed -i -E 's/^(FFLAGS[[:space:]]*=.*)$/\1 -fallow-argument-mismatch/; s/^(F77FLAGS[[:space:]]*=.*)$/\1 -fallow-argument-mismatch/' configure.wps
    fi
    ./compile > "$LOG_DIR/wps_compile.log" 2>&1 || true
  )
  [ -e geogrid/src/geogrid.exe ] && [ -e ungrib/src/ungrib.exe ] && [ -e metgrid/src/metgrid.exe ] \
    || fail "$LOG_DIR/wps_compile.log" "WPS no generó geogrid.exe / ungrib.exe / metgrid.exe"
  echo "==> WPS compilado"
fi

# 4. Datos geográficos obligatorios de baja resolución
cd "$WRF_HOME"
if [ -d WPS_GEOG_LOW_RES ]; then
  echo "==> Datos geográficos ya están, se salta"
else
  echo "==> Bajando geog_low_res_mandatory"
  wget -q "$GEOG_URL" -O geog.tar.gz
  tar xzf geog.tar.gz
  rm -f geog.tar.gz
  [ -d WPS_GEOG_LOW_RES ] || { echo "ERROR: no apareció WPS_GEOG_LOW_RES"; exit 1; }
fi

echo "==> Listo: WRF, WPS y datos geográficos en $WRF_HOME"
