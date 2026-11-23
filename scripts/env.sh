# Variables de entorno para compilar y correr WRF/WPS.
# Uso: source scripts/env.sh
# La carpeta de librerías se puede cambiar con WRF_DEPS (por defecto ~/wrf_dependencies).

export dir="${WRF_DEPS:-$HOME/wrf_dependencies}"
export NETCDF="${dir}/netcdf"
export LD_LIBRARY_PATH="${NETCDF}/lib:${dir}/grib2/lib:${dir}/lib:${LD_LIBRARY_PATH:-}"
export PATH="${NETCDF}/bin:${dir}/mpich/bin:${dir}/bin:${PATH}"
export JASPERLIB="${dir}/grib2/lib"
export JASPERINC="${dir}/grib2/include"
