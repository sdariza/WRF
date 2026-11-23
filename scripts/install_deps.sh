#!/usr/bin/env bash
# Compila las librerías que necesitan WRF y WPS: zlib, netCDF-c, netCDF-fortran y mpich.
# Sigue la guía oficial de NCAR (sin HDF5). Si una librería ya está instalada, la salta.
# Uso: bash scripts/install_deps.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/env.sh"

JOBS="${JOBS:-$(nproc)}"
TUT="https://www2.mmm.ucar.edu/wrf/OnLineTutorial/compile_tutorial/tar_files"

echo "==> Librerías en: $dir  (núcleos: $JOBS)"

for cmd in gcc g++ gfortran cpp csh perl m4 make wget tar; do
  command -v "$cmd" >/dev/null || { echo "Falta '$cmd'. Instálalo antes de seguir."; exit 1; }
done

mkdir -p "$dir"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
cd "$BUILD"

# Variables solo para compilar las librerías (no quedan en tu terminal)
export CC=gcc CXX=g++ FC=gfortran F77=gfortran
FLAGS="-m64"
# gfortran 10+ necesita este flag para el código viejo de las librerías
if [ "$(gfortran -dumpversion | cut -d. -f1)" -ge 10 ]; then
  FLAGS="$FLAGS -fallow-argument-mismatch"
fi
export FCFLAGS="$FLAGS" FFLAGS="$FLAGS"
export LDFLAGS="-L${NETCDF}/lib -L${dir}/grib2/lib"
export CPPFLAGS="-I${NETCDF}/include -I${dir}/grib2/include -fcommon"

if [ ! -f "$dir/grib2/lib/libz.a" ]; then
  echo "==> zlib"
  wget -q "$TUT/zlib-1.2.11.tar.gz"
  tar xzf zlib-1.2.11.tar.gz && cd zlib-1.2.11
  ./configure --prefix="$dir/grib2"
  make -j "$JOBS" && make install
  cd "$BUILD"
else
  echo "==> zlib ya está, se salta"
fi

if [ ! -f "$NETCDF/lib/libnetcdf.so" ]; then
  echo "==> netCDF-c"
  wget -q https://github.com/Unidata/netcdf-c/archive/v4.7.2.tar.gz -O netcdf-c.tar.gz
  tar xzf netcdf-c.tar.gz && cd netcdf-c-4.7.2
  ./configure --prefix="$NETCDF" --disable-dap --enable-netcdf4 --disable-hdf5 --enable-shared
  make -j "$JOBS" && make install
  cd "$BUILD"
else
  echo "==> netCDF-c ya está, se salta"
fi

if [ ! -f "$NETCDF/lib/libnetcdff.so" ]; then
  echo "==> netCDF-fortran"
  export LIBS="-lnetcdf -lz"
  wget -q https://github.com/Unidata/netcdf-fortran/archive/v4.5.2.tar.gz -O netcdf-fortran.tar.gz
  tar xzf netcdf-fortran.tar.gz && cd netcdf-fortran-4.5.2
  ./configure --prefix="$NETCDF" --disable-hdf5 --enable-shared
  make -j "$JOBS" && make install
  unset LIBS
  cd "$BUILD"
else
  echo "==> netCDF-fortran ya está, se salta"
fi

if [ ! -x "$dir/mpich/bin/mpif90" ]; then
  echo "==> mpich (este es el más lento)"
  wget -q "$TUT/mpich-3.0.4.tar.gz"
  tar xzf mpich-3.0.4.tar.gz && cd mpich-3.0.4
  ./configure --prefix="$dir/mpich"
  make -j "$JOBS" && make install
  cd "$BUILD"
else
  echo "==> mpich ya está, se salta"
fi

echo
echo "==> Verificación"
nc-config --version
nf-config --version
mpif90 --version | head -n 1
echo "==> Listo. Abre una terminal nueva antes de compilar WRF."
