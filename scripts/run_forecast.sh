#!/usr/bin/env bash
# Corre un pronóstico WRF de 48 h sobre el Caribe colombiano con datos GFS 0.25°.
# Necesita que antes se haya corrido scripts/build_wrf.sh.
#
# Uso: bash scripts/run_forecast.sh
# Variables opcionales:
#   DATE    fecha del ciclo GFS, YYYYMMDD (por defecto hoy en UTC)
#   CYCLE   ciclo GFS: 00, 06, 12 o 18 (por defecto 00)
#   FHOURS  horas de pronóstico (por defecto 48)
#   NP      procesos MPI (por defecto todos los núcleos)
#   WRF_HOME, WRF_DEPS  como en build_wrf.sh
#   WORK    carpeta para los datos GFS (por defecto ~/wrf_run)
#   LOG_DIR carpeta para los logs (por defecto $WORK/logs)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export WRF_HOME="${WRF_HOME:-$HOME/wrf_build}"
export WRF_DEPS="${WRF_DEPS:-$WRF_HOME/deps}"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/env.sh"
export WRFIO_NCD_LARGE_FILE_SUPPORT=1

DATE="${DATE:-$(date -u +%Y%m%d)}"
CYCLE="${CYCLE:-00}"
FHOURS="${FHOURS:-48}"
STEP_H=3
NP="${NP:-$(nproc)}"
WORK="${WORK:-$HOME/wrf_run}"
LOG_DIR="${LOG_DIR:-$WORK/logs}"
GFS_DIR="$WORK/gfs"
WPS_DIR="$WRF_HOME/WPS"
RUN_DIR="$WRF_HOME/WRF/run"
GEOG_DIR="$WRF_HOME/WPS_GEOG_LOW_RES"

for exe in "$WPS_DIR/geogrid.exe" "$WPS_DIR/ungrib.exe" "$WPS_DIR/metgrid.exe" "$RUN_DIR/real.exe" "$RUN_DIR/wrf.exe"; do
  [ -e "$exe" ] || { echo "ERROR: falta $exe. Corre primero scripts/build_wrf.sh"; exit 1; }
done

# Fechas de inicio y fin
START_EPOCH=$(date -u -d "${DATE} ${CYCLE}:00" +%s)
END_EPOCH=$((START_EPOCH + FHOURS * 3600))
fmt() { date -u -d "@$1" "+$2"; }
START_WPS=$(fmt "$START_EPOCH" "%Y-%m-%d_%H:00:00")
END_WPS=$(fmt "$END_EPOCH" "%Y-%m-%d_%H:00:00")
read -r SY SM SD SH <<<"$(fmt "$START_EPOCH" "%Y %m %d %H")"
read -r EY EM ED EH <<<"$(fmt "$END_EPOCH" "%Y %m %d %H")"
INTERVAL=$((STEP_H * 3600))

mkdir -p "$GFS_DIR" "$LOG_DIR"
echo "==> Pronóstico desde $START_WPS hasta $END_WPS (GFS ${DATE} ${CYCLE}Z, $NP procesos)"

# ---------------------------------------------------------------------------
# 1. Bajar GFS 0.25° recortado a 0-20 N, 270-300 E (filtro de NOMADS)
# ---------------------------------------------------------------------------
download_gfs() {
  local fff="$1" out="$2" tmp="$2.part" url attempt
  url="https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?dir=%2Fgfs.${DATE}%2F${CYCLE}%2Fatmos&file=gfs.t${CYCLE}z.pgrb2.0p25.f${fff}&all_var=on&all_lev=on&subregion=&toplat=20&leftlon=270&rightlon=300&bottomlat=0"
  for attempt in $(seq 1 8); do
    if curl -fsS --retry 2 --connect-timeout 30 --max-time 600 -o "$tmp" "$url" \
       && [ "$(head -c 4 "$tmp")" = "GRIB" ]; then
      mv "$tmp" "$out"
      return 0
    fi
    echo "    f${fff}: intento $attempt falló; reintento en $((attempt * 30)) s"
    rm -f "$tmp"
    sleep $((attempt * 30))
  done
  return 1
}

rm -f "$GFS_DIR"/gfs.*
for ((fh = 0; fh <= FHOURS; fh += STEP_H)); do
  fff=$(printf "%03d" "$fh")
  out="$GFS_DIR/gfs.t${CYCLE}z.pgrb2.0p25.f${fff}"
  echo "==> GFS f${fff}"
  download_gfs "$fff" "$out" || { echo "ERROR: no se pudo bajar GFS f${fff} (¿ya salió el ciclo ${DATE} ${CYCLE}Z?)"; exit 1; }
  sleep 2   # no saturar NOMADS
done

# ---------------------------------------------------------------------------
# 2. WPS: geogrid, ungrib y metgrid
# ---------------------------------------------------------------------------
cd "$WPS_DIR"
rm -f FILE:* met_em.d01.* GRIBFILE.* geo_em.d01.nc ./*.log
cat > namelist.wps <<EOF
&share
 wrf_core = 'ARW',
 max_dom = 1,
 start_date = '${START_WPS}',
 end_date   = '${END_WPS}',
 interval_seconds = ${INTERVAL},
/

&geogrid
 parent_id         = 1,
 parent_grid_ratio = 1,
 i_parent_start    = 1,
 j_parent_start    = 1,
 e_we              = 80,
 e_sn              = 80,
 geog_data_res     = 'lowres',
 dx = 15000,
 dy = 15000,
 map_proj  = 'mercator',
 ref_lat   = 9.5,
 ref_lon   = -74.5,
 truelat1  = 10.0,
 stand_lon = -74.5,
 geog_data_path = '${GEOG_DIR}/'
/

&ungrib
 out_format = 'WPS',
 prefix = 'FILE',
/

&metgrid
 fg_name = 'FILE'
/
EOF
cp namelist.wps "$LOG_DIR/"

# WPS no siempre devuelve error al fallar: se revisa el mensaje de éxito del log
check_wps() {
  local name="$1"
  cp "$name.log" "$LOG_DIR/" 2>/dev/null || true
  if ! grep -q "Successful completion of $name" "$name.log" 2>/dev/null; then
    echo "ERROR: $name.exe falló"
    tail -n 40 "$name.log" 2>/dev/null || true
    exit 1
  fi
}

echo "==> geogrid"
./geogrid.exe > "$LOG_DIR/geogrid.out" 2>&1 || true
check_wps geogrid

echo "==> ungrib"
./link_grib.csh "$GFS_DIR"/gfs.t"${CYCLE}"z.pgrb2.0p25.f*
ln -sf ungrib/Variable_Tables/Vtable.GFS Vtable
./ungrib.exe > "$LOG_DIR/ungrib.out" 2>&1 || true
check_wps ungrib

echo "==> metgrid"
./metgrid.exe > "$LOG_DIR/metgrid.out" 2>&1 || true
check_wps metgrid

FIRST_MET="$WPS_DIR/met_em.d01.${START_WPS}.nc"
NUM_LEVELS=$(ncdump -h "$FIRST_MET" | awk '/num_metgrid_levels =/ {print $3; exit}')
NUM_SOIL=$(ncdump -h "$FIRST_MET" | awk -F'= ' '/:NUM_METGRID_SOIL_LEVELS/ {gsub(/[^0-9]/, "", $2); print $2; exit}')
NUM_SOIL="${NUM_SOIL:-4}"
echo "==> num_metgrid_levels = $NUM_LEVELS, num_metgrid_soil_levels = $NUM_SOIL"

# ---------------------------------------------------------------------------
# 3. WRF: real.exe y wrf.exe
# ---------------------------------------------------------------------------
cd "$RUN_DIR"
rm -f met_em.d01.* wrfinput_d01 wrfbdy_d01 wrfout_d01_* rsl.out.* rsl.error.*
ln -sf "$WPS_DIR"/met_em.d01.* .

cat > namelist.input <<EOF
&time_control
 run_days = 0, run_hours = ${FHOURS}, run_minutes = 0, run_seconds = 0,
 start_year = ${SY}, start_month = ${SM}, start_day = ${SD}, start_hour = ${SH},
 end_year   = ${EY}, end_month   = ${EM}, end_day   = ${ED}, end_hour   = ${EH},
 interval_seconds   = ${INTERVAL},
 input_from_file    = .true.,
 history_interval   = 60,
 frames_per_outfile = 1000,
 restart            = .false.,
 restart_interval   = 100000,
 io_form_history = 2, io_form_restart = 2, io_form_input = 2, io_form_boundary = 2,
/

&domains
 time_step = 90,
 max_dom = 1,
 e_we = 80, e_sn = 80, e_vert = 45,
 p_top_requested = 5000,
 num_metgrid_levels = ${NUM_LEVELS},
 num_metgrid_soil_levels = ${NUM_SOIL},
 dx = 15000, dy = 15000,
 grid_id = 1, parent_id = 0,
 i_parent_start = 1, j_parent_start = 1,
 parent_grid_ratio = 1, parent_time_step_ratio = 1,
 feedback = 0,
/

&physics
 mp_physics         = 8,
 cu_physics         = 1,
 ra_lw_physics      = 4,
 ra_sw_physics      = 4,
 radt               = 15,
 bl_pbl_physics     = 1,
 sf_sfclay_physics  = 1,
 sf_surface_physics = 2,
 num_land_cat       = 21,
/

&dynamics
 w_damping = 1, diff_opt = 1, km_opt = 4,
 damp_opt = 3, zdamp = 5000., dampcoef = 0.2,
/

&bdy_control
 spec_bdy_width = 5, specified = .true.,
/

&namelist_quilt
 nio_tasks_per_group = 0, nio_groups = 1,
/
EOF
cp namelist.input "$LOG_DIR/"

run_mpi() {
  local exe="$1" ok="$2" tag="$3"
  echo "==> $exe ($NP procesos)"
  mpirun -launcher fork -np "$NP" "./$exe" > "$LOG_DIR/$tag.out" 2>&1 || true
  mkdir -p "$LOG_DIR/$tag"
  cp rsl.out.* rsl.error.* "$LOG_DIR/$tag/" 2>/dev/null || true
  if ! grep -q "$ok" rsl.error.0000 2>/dev/null; then
    echo "ERROR: $exe falló"
    tail -n 40 rsl.error.0000 2>/dev/null || tail -n 40 "$LOG_DIR/$tag.out"
    exit 1
  fi
  rm -f rsl.out.* rsl.error.*
}

run_mpi real.exe "SUCCESS COMPLETE REAL_EM" real
run_mpi wrf.exe "SUCCESS COMPLETE WRF" wrf

WRFOUT="$RUN_DIR/wrfout_d01_${START_WPS}"
[ -f "$WRFOUT" ] || { echo "ERROR: no apareció $WRFOUT"; exit 1; }
echo "==> Listo: $WRFOUT"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "wrfout=$WRFOUT"
    echo "label=$(fmt "$START_EPOCH" "%Y-%m-%d %H")Z"
  } >> "$GITHUB_OUTPUT"
fi
