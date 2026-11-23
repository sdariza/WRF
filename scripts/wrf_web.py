#!/usr/bin/env python3
"""
Interactive Windy-style web map from a WRF output file (wrfout).

Creates ONE self-contained HTML file (no internet needed) with:
  - smooth temperature / wind speed / rainfall layers
  - animated wind particles
  - timeline with play/pause to go through the simulation
  - hover to read values at any point

Usage:
  python wrf_web.py /path/wrfout_d01_YYYY-MM-DD_HH:MM:SS [output.html]
Then open the HTML in any browser.
"""
import json
import sys

import contourpy
import numpy as np
import pandas as pd
import xarray as xr

UTC_OFFSET = -5
TZ_NAME = "COT"
EDGE_CELLS = 8
TITLE = "Colombian Caribbean · WRF simulation"
CREDIT = "WRF test run (15 km) · NCEP FNL data · Not a forecast"
# Cities with a line chart in the side panel (in this order; must also be in CITIES)
CHART_CITIES = ["Barranquilla", "Cartagena", "Santa Marta", "Valledupar", "Montería", "Medellín"]
CITIES = [
    ("Barranquilla", 10.96, -74.80), ("Cartagena", 10.39, -75.51),
    ("Santa Marta", 11.24, -74.20), ("Valledupar", 10.46, -73.25),
    ("Montería", 8.75, -75.88), ("Sincelejo", 9.30, -75.40),
    ("Riohacha", 11.54, -72.91), ("Cúcuta", 7.89, -72.50),
    ("Bucaramanga", 7.12, -73.12), ("Medellín", 6.24, -75.58),
    ("Maracaibo", 10.65, -71.64),
]


def r1(a):
    return np.round(a.astype(float), 1).ravel().tolist()


def build_data(path):
    ds = xr.open_dataset(path)
    e = EDGE_CELLS
    sl = (slice(e, -e or None), slice(e, -e or None))
    tsl = (slice(None),) + sl
    times = pd.to_datetime(ds["Times"].values.astype(str), format="%Y-%m-%d_%H:%M:%S")
    local = times + pd.Timedelta(hours=UTC_OFFSET)
    lat = ds["XLAT"].isel(Time=0).values[sl]
    lon = ds["XLONG"].isel(Time=0).values[sl]
    land = ds["LANDMASK"].isel(Time=0).values[sl]
    t2 = ds["T2"].values[tsl] - 273.15
    u = ds["U10"].values[tsl]
    v = ds["V10"].values[tsl]
    rain = (ds["RAINC"] + ds["RAINNC"]).values[tsl]
    rain = rain - rain[0]
    ny, nx = lat.shape

    coast = [np.round(seg, 2).tolist()
             for seg in contourpy.contour_generator(z=land.astype(float)).lines(0.5)
             if len(seg) > 2]

    cities = []
    for name, clat, clon in CITIES:
        if lat.min() < clat < lat.max() and lon.min() < clon < lon.max():
            j, i = np.unravel_index(np.argmin((lat - clat) ** 2 + (lon - clon) ** 2), lat.shape)
            cities.append([name, int(i), int(j)])

    return dict(
        title=TITLE, credit=CREDIT, tz=TZ_NAME, nx=nx, ny=ny,
        times=[int(t.value // 10**6) for t in local],  # ms, local clock stored as UTC
        t2=[r1(f) for f in t2], u=[r1(f) for f in u], v=[r1(f) for f in v],
        rain=[r1(f) for f in rain],
        lat=np.round(lat, 3).ravel().tolist(), lon=np.round(lon, 3).ravel().tolist(),
        coast=coast, cities=cities, chart_cities=CHART_CITIES,
    )


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WRF · Interactive map</title>
<style>
  :root { --bg:#15171c; --panel:rgba(22,24,30,.82); --fg:#eceef2; --muted:#9aa0aa; --acc:#e8a33a; }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--fg);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; overflow:hidden; }
  #stage { position:fixed; inset:0; }
  #stage canvas { position:absolute; inset:0; width:100%; height:100%; }
  .panel { position:fixed; background:var(--panel); backdrop-filter:blur(8px); border-radius:12px;
    box-shadow:0 4px 18px rgba(0,0,0,.35); }
  #head { top:14px; left:50%; transform:translateX(-50%); padding:12px 20px; text-align:center; white-space:nowrap; }
  #head h1 { margin:0; font-size:17px; font-weight:700; }
  #head .t { margin-top:4px; font-size:22px; font-weight:700; color:var(--acc); }
  #layers { top:14px; right:14px; padding:8px; display:flex; flex-direction:column; gap:6px; }
  #layers button { all:unset; cursor:pointer; padding:8px 14px; border-radius:8px; font-size:14px;
    color:var(--fg); text-align:right; }
  #layers button:hover { background:rgba(255,255,255,.08); }
  #layers button.on { background:var(--acc); color:#1a1a1a; font-weight:600; }
  #layers label { font-size:13px; color:var(--muted); padding:6px 14px 2px; cursor:pointer; }
  #bar { left:14px; right:14px; bottom:14px; padding:10px 14px; display:flex; align-items:center; gap:12px; }
  #play { all:unset; cursor:pointer; width:34px; height:34px; border-radius:50%; background:var(--acc);
    color:#1a1a1a; display:grid; place-items:center; font-size:15px; flex:none; }
  #slider { flex:1; accent-color:var(--acc); }
  #legend { display:flex; flex-direction:column; gap:3px; min-width:200px; flex:none; }
  #legend .g { height:10px; border-radius:5px; }
  #legend .l { display:flex; justify-content:space-between; font-size:11px; color:var(--muted); }
  #credit { position:fixed; left:16px; right:16px; bottom:72px; font-size:11px; color:var(--muted);
    text-align:center; text-shadow:0 1px 2px #000; }
  #charts { top:100px; left:14px; bottom:96px; width:280px; padding:12px 14px; display:none;
    flex-direction:column; gap:6px; }
  #charts .ct { font-size:12px; color:var(--muted); letter-spacing:.02em; }
  #charts .card { flex:1; min-height:0; display:flex; flex-direction:column; gap:2px;
    border-top:1px solid rgba(255,255,255,.07); padding-top:6px; }
  #charts .h { display:flex; justify-content:space-between; align-items:baseline; font-size:13px; }
  #charts .v { font-weight:700; font-size:15px; }
  #charts canvas { flex:1; min-height:0; width:100%; display:block; }
  #charts.strip { top:auto; left:14px; right:14px; bottom:80px; width:auto; flex-direction:row;
    overflow-x:auto; padding:8px 10px; gap:10px; scroll-snap-type:x mandatory; -webkit-overflow-scrolling:touch; }
  #charts.strip .ct { display:none; }
  #charts.strip .card { flex:0 0 150px; border-top:none; padding-top:0; scroll-snap-align:start; }
  #charts.strip .card + .card { border-left:1px solid rgba(255,255,255,.07); padding-left:10px; }
  #charts.strip .h { font-size:12px; }
  #charts.strip .v { font-size:14px; }
  #tip { position:fixed; pointer-events:none; padding:8px 10px; font-size:12px; line-height:1.45;
    display:none; white-space:nowrap; }
  #tip b { font-size:14px; }
  @media (max-width:640px) {
    #legend { display:none; }
    #head h1 { font-size:15px; }
    #head .t { font-size:17px; }
    #credit { font-size:10px; }
    #head { left:14px; right:14px; transform:none; padding:10px 14px; white-space:normal; }
    #layers { top:84px; left:14px; right:14px; flex-direction:row; align-items:center;
      justify-content:space-between; padding:6px; gap:4px; }
    #layers button { padding:6px 10px; font-size:13px; }
    #layers label { padding:0 6px; font-size:12px; }
  }
</style>
</head>
<body>
<div id="stage">
  <canvas id="field"></canvas>
  <canvas id="particles"></canvas>
  <canvas id="overlay"></canvas>
</div>
<div id="head" class="panel"><h1 id="title"></h1><div class="t" id="time"></div></div>
<div id="layers" class="panel">
  <button data-layer="temp" class="on">Temperature</button>
  <button data-layer="wind">Wind</button>
  <button data-layer="rain">Rain</button>
  <label><input type="checkbox" id="ptoggle" checked> Wind particles</label>
</div>
<div id="charts" class="panel"><div class="ct" id="ctitle"></div></div>
<div id="credit"></div>
<div id="bar" class="panel">
  <button id="play" aria-label="Play">▶</button>
  <input id="slider" type="range" min="0" step="0.01" value="0">
  <div id="legend"><div class="g" id="lg"></div><div class="l" id="ll"></div></div>
</div>
<div id="tip" class="panel"></div>
<script>
const D = __DATA__;
const NX = D.nx, NY = D.ny, NT = D.times.length;
const DURATION_S = 10;          // seconds to play the whole simulation
const PARTICLE_SPEED = 0.007;   // lower = slower wind particles
const PARTICLE_LIFE = 160;      // frames before a particle respawns

// ---------- palettes: [value, color]
const PAL = {
  temp: { unit:"°C", stops:[[10,"#3a4fb5"],[15,"#3b8fd0"],[20,"#3cbfa8"],[24,"#8fd14f"],[27,"#e6d43a"],
          [30,"#f29b2e"],[33,"#e8572b"],[36,"#c62a3a"],[40,"#8e1a5a"]] },
  wind: { unit:"km/h", stops:[[0,"#5b4aa8"],[8,"#3b7fd0"],[16,"#38b7c8"],[24,"#4cc36f"],[32,"#c9d63a"],
          [40,"#f0a23a"],[50,"#e5533a"],[65,"#b0245a"]] },
  rain: { unit:"mm", stops:[[0.2,"#7fd3ff"],[2,"#3b9cff"],[5,"#3d5fe0"],[10,"#7b45d9"],[20,"#c03ad3"],[40,"#ff5aa8"]] },
};
function hex(c){ return [parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16)]; }
function lut(stops){
  const lo = stops[0][0], hi = stops[stops.length-1][0], out = new Uint8ClampedArray(256*3);
  for (let k=0;k<256;k++){
    const v = lo + (hi-lo)*k/255; let s=0;
    while (s < stops.length-2 && v > stops[s+1][0]) s++;
    const a = stops[s], b = stops[s+1], f = Math.min(1,Math.max(0,(v-a[0])/(b[0]-a[0])));
    const ca = hex(a[1]), cb = hex(b[1]);
    for (let c=0;c<3;c++) out[k*3+c] = ca[c] + (cb[c]-ca[c])*f;
  }
  return {lo, hi, rgb:out};
}
for (const k in PAL) PAL[k].lut = lut(PAL[k].stops);

// ---------- state
let layer = "temp", tf = 0, playing = false, showParticles = true;

// ---------- field access (bilinear in space, linear in time)
function arr(name, t){
  if (name === "wind") return null;
  return D[name === "temp" ? "t2" : "rain"][t];
}
function cellValue(name, t0, t1, a, idx){
  if (name === "wind"){
    const s0 = Math.hypot(D.u[t0][idx], D.v[t0][idx]), s1 = Math.hypot(D.u[t1][idx], D.v[t1][idx]);
    return (s0 + (s1-s0)*a) * 3.6;
  }
  const A = arr(name,t0), B = arr(name,t1);
  return A[idx] + (B[idx]-A[idx])*a;
}
function timeParts(){
  const t0 = Math.min(NT-1, Math.floor(tf)), t1 = Math.min(NT-1, t0+1);
  return [t0, t1, tf - t0];
}
function sample(name, x, y){
  const [t0,t1,a] = timeParts();
  const i0 = Math.max(0,Math.min(NX-2,Math.floor(x))), j0 = Math.max(0,Math.min(NY-2,Math.floor(y)));
  const fx = Math.min(1,Math.max(0,x-i0)), fy = Math.min(1,Math.max(0,y-j0));
  const g = (i,j)=>cellValue(name,t0,t1,a,j*NX+i);
  return (g(i0,j0)*(1-fx)+g(i0+1,j0)*fx)*(1-fy) + (g(i0,j0+1)*(1-fx)+g(i0+1,j0+1)*fx)*fy;
}
function sampleUV(x, y){
  const [t0,t1,a] = timeParts();
  const i0 = Math.max(0,Math.min(NX-2,Math.floor(x))), j0 = Math.max(0,Math.min(NY-2,Math.floor(y)));
  const fx = x-i0, fy = y-j0;
  const g = (F,i,j)=>{ const k=j*NX+i; return F[t0][k] + (F[t1][k]-F[t0][k])*a; };
  const bl = F => (g(F,i0,j0)*(1-fx)+g(F,i0+1,j0)*fx)*(1-fy) + (g(F,i0,j0+1)*(1-fx)+g(F,i0+1,j0+1)*fx)*fy;
  return [bl(D.u), bl(D.v)];
}

// ---------- canvases & geometry
const cf = document.getElementById("field"), cp = document.getElementById("particles"),
      co = document.getElementById("overlay");
const xf = cf.getContext("2d"), xp = cp.getContext("2d"), xo = co.getContext("2d");
const small = document.createElement("canvas"); small.width = NX; small.height = NY;
const xs = small.getContext("2d"); const img = xs.createImageData(NX, NY);
let box = {x:0,y:0,w:1,h:1}, dpr = 1;

function resize(){
  dpr = window.devicePixelRatio || 1;
  for (const c of [cf,cp,co]){ c.width = innerWidth*dpr; c.height = innerHeight*dpr; }
  const mobile = innerWidth < 640, wide = innerWidth >= 1000 && charts.length > 0;
  const strip = !wide && charts.length > 0 && innerHeight >= 560;   // phones & tablets
  const stripH = innerHeight < 720 ? 128 : 165;
  chartsEl.style.display = (wide || strip) ? "flex" : "none";
  chartsEl.classList.toggle("strip", strip);
  chartsEl.style.height = strip ? stripH + "px" : "";
  timeEl.textContent = fmtTime();   // header must have its final height before measuring
  const layersEl = document.getElementById("layers");
  layersEl.style.top = mobile ? (headEl.getBoundingClientRect().bottom + 8) + "px" : "";
  const top = mobile ? layersEl.getBoundingClientRect().bottom + 12 : 100;
  const bottom = strip ? 80 + stripH + (mobile ? 40 : 28) : 96;
  const left = wide ? 310 : (mobile ? 8 : 20), right = wide ? 200 : (mobile ? 8 : 20);
  const availW = innerWidth - left - right, availH = innerHeight - top - bottom;
  const s = Math.min(availW/(NX-1), availH/(NY-1));
  box = { w:s*(NX-1), h:s*(NY-1) };
  box.x = left + (availW - box.w)/2; box.y = top + (availH - box.h)/2;
  headEl.style.left = mobile ? "" : (box.x + box.w/2) + "px";
  creditEl.style.left = box.x + "px"; creditEl.style.right = "auto"; creditEl.style.width = box.w + "px";
  creditEl.style.top = (box.y + box.h + 6) + "px"; creditEl.style.bottom = "auto";
  sizeCharts();
  drawField(); drawOverlay(); drawCharts();
  xp.clearRect(0,0,cp.width,cp.height);
}
const toScreen = (x,y)=>[box.x + x/(NX-1)*box.w, box.y + (1 - y/(NY-1))*box.h];
const toGrid = (sx,sy)=>[(sx-box.x)/box.w*(NX-1), (1-(sy-box.y)/box.h)*(NY-1)];

// ---------- drawing
function drawField(){
  const P = PAL[layer].lut, [t0,t1,a] = timeParts();
  for (let j=0;j<NY;j++) for (let i=0;i<NX;i++){
    const v = cellValue(layer,t0,t1,a,j*NX+i);
    const p = ((NY-1-j)*NX + i)*4;
    if (layer === "rain" && v < 0.2){ img.data[p]=44; img.data[p+1]=47; img.data[p+2]=56; img.data[p+3]=255; continue; }
    const k = Math.round(Math.min(1,Math.max(0,(v-P.lo)/(P.hi-P.lo)))*255)*3;
    img.data[p]=P.rgb[k]; img.data[p+1]=P.rgb[k+1]; img.data[p+2]=P.rgb[k+2]; img.data[p+3]=255;
  }
  xs.putImageData(img,0,0);
  xf.setTransform(dpr,0,0,dpr,0,0);
  xf.clearRect(0,0,innerWidth,innerHeight);
  xf.imageSmoothingEnabled = true; xf.imageSmoothingQuality = "high";
  // half-cell padding so cell centres line up with the grid
  const cw = box.w/(NX-1), ch = box.h/(NY-1);
  xf.drawImage(small, box.x-cw/2, box.y-ch/2, box.w+cw, box.h+ch);
}
function drawOverlay(){
  xo.setTransform(dpr,0,0,dpr,0,0);
  xo.clearRect(0,0,innerWidth,innerHeight);
  xo.save(); xo.beginPath(); xo.rect(box.x,box.y,box.w,box.h); xo.clip();
  xo.strokeStyle = "rgba(255,255,255,.75)"; xo.lineWidth = 1.1;
  for (const seg of D.coast){
    xo.beginPath();
    seg.forEach(([x,y],n)=>{ const [sx,sy]=toScreen(x,y); n?xo.lineTo(sx,sy):xo.moveTo(sx,sy); });
    xo.stroke();
  }
  xo.restore();
  xo.lineJoin = "round"; xo.miterLimit = 2;
  xo.font = "600 12px -apple-system,Segoe UI,Roboto,Arial,sans-serif";
  for (const [name,i,j] of D.cities){
    const [sx,sy] = toScreen(i,j);
    xo.fillStyle = "#fff"; xo.beginPath(); xo.arc(sx,sy,3,0,7); xo.fill();
    xo.lineWidth = 3; xo.strokeStyle = "rgba(0,0,0,.7)"; xo.strokeText(name,sx+6,sy-5);
    xo.fillText(name,sx+6,sy-5);
  }
}

// ---------- city line charts
const chartsEl = document.getElementById("charts"), headEl = document.getElementById("head"),
      creditEl = document.getElementById("credit");
const LINE = { temp:"#f0883a", wind:"#38b7c8", rain:"#4f9dff" };
const LNAME = { temp:"Temperature", wind:"Wind speed", rain:"Accumulated rain" };
const charts = (D.chart_cities || []).map(n => D.cities.find(c => c[0] === n)).filter(Boolean)
  .map(([name,i,j]) => {
    const card = document.createElement("div"); card.className = "card";
    card.innerHTML = `<div class="h"><span>${name}</span><span class="v"></span></div><canvas></canvas>`;
    chartsEl.appendChild(card);
    return { idx:j*NX+i, cv:card.querySelector("canvas"), val:card.querySelector(".v") };
  });
const seriesCache = {};
function series(name, idx){
  const key = name + ":" + idx;
  if (!seriesCache[key]){
    const s = [];
    for (let t=0;t<NT;t++) s.push(Math.max(name === "temp" ? -99 : 0, cellValue(name,t,t,0,idx)));
    seriesCache[key] = s;
  }
  return seriesCache[key];
}
function fmtVal(v){
  return layer === "temp" ? v.toFixed(1) + " °C" : layer === "wind" ? v.toFixed(0) + " km/h" : v.toFixed(1) + " mm";
}
function sizeCharts(){
  for (const c of charts){
    const r = c.cv.getBoundingClientRect();
    c.cv.width = Math.max(1, r.width*dpr); c.cv.height = Math.max(1, r.height*dpr);
  }
}
function drawCharts(){
  if (chartsEl.style.display === "none") return;
  document.getElementById("ctitle").textContent = LNAME[layer] + " · cities";
  const [t0,t1,a] = timeParts();
  for (const c of charts){
    const s = series(layer, c.idx), ctx = c.cv.getContext("2d");
    const W = c.cv.width/dpr, H = c.cv.height/dpr;
    ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,W,H);
    let lo = Math.min(...s), hi = Math.max(...s);
    if (layer === "rain"){ lo = 0; hi = Math.max(hi, 1); }
    if (hi - lo < 1){ const m = (hi+lo)/2; lo = m - 0.5; hi = m + 0.5; }
    const px = 26, py = 5;
    const X = k => px + k/(NT-1)*(W-px-4), Y = v => H - py - (v-lo)/(hi-lo)*(H-2*py);
    ctx.fillStyle = "rgba(255,255,255,0.045)";
    for (let k=0;k<NT-1;k++){
      const h = new Date(D.times[k]).getUTCHours();
      if (h >= 18 || h < 6) ctx.fillRect(X(k), 0, X(k+1)-X(k), H);
    }
    ctx.fillStyle = "#9aa0aa"; ctx.font = "10px -apple-system,Segoe UI,Roboto,Arial,sans-serif";
    ctx.textBaseline = "top"; ctx.fillText(hi.toFixed(0), 0, 0);
    ctx.textBaseline = "bottom"; ctx.fillText(lo.toFixed(0), 0, H);
    ctx.beginPath(); s.forEach((v,k)=> k ? ctx.lineTo(X(k),Y(v)) : ctx.moveTo(X(k),Y(v)));
    ctx.strokeStyle = LINE[layer]; ctx.lineWidth = 1.8; ctx.lineJoin = "round"; ctx.stroke();
    ctx.lineTo(X(NT-1), H); ctx.lineTo(X(0), H); ctx.closePath();
    ctx.globalAlpha = 0.15; ctx.fillStyle = LINE[layer]; ctx.fill(); ctx.globalAlpha = 1;
    const v = s[t0] + (s[t1]-s[t0])*a, cx = X(tf);
    ctx.strokeStyle = "rgba(255,255,255,.4)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx,0); ctx.lineTo(cx,H); ctx.stroke();
    ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(cx, Y(v), 3.2, 0, 7); ctx.fill();
    c.val.textContent = fmtVal(v); c.val.style.color = LINE[layer];
  }
}

// ---------- particles
const NP = Math.round(Math.min(4000, 2500 * (innerWidth*innerHeight)/(1400*900)));
const parts = [];
function spawn(p){ p.x = Math.random()*(NX-1); p.y = Math.random()*(NY-1); p.age = Math.random()*80|0; return p; }
for (let k=0;k<NP;k++) parts.push(spawn({}));
function stepParticles(){
  xp.setTransform(dpr,0,0,dpr,0,0);
  xp.globalCompositeOperation = "destination-in";
  xp.fillStyle = "rgba(0,0,0,0.90)"; xp.fillRect(0,0,innerWidth,innerHeight);
  xp.globalCompositeOperation = "source-over";
  if (!showParticles) return;
  xp.strokeStyle = "rgba(255,255,255,0.85)"; xp.lineWidth = 1.1;
  xp.beginPath();
  for (const p of parts){
    const [u,v] = sampleUV(p.x,p.y);
    const nx = p.x + u*PARTICLE_SPEED, ny = p.y + v*PARTICLE_SPEED;
    if (++p.age > PARTICLE_LIFE || nx<0 || ny<0 || nx>NX-1 || ny>NY-1){ spawn(p); p.age = 0; continue; }
    const [a,b] = toScreen(p.x,p.y), [c,d] = toScreen(nx,ny);
    xp.moveTo(a,b); xp.lineTo(c,d);
    p.x = nx; p.y = ny;
  }
  xp.stroke();
}

// ---------- UI
const slider = document.getElementById("slider"), timeEl = document.getElementById("time"),
      playBtn = document.getElementById("play"), tip = document.getElementById("tip");
document.getElementById("title").textContent = D.title;
document.getElementById("credit").textContent = D.credit + (NT>1 ? " · Animation interpolates between model outputs" : "");
slider.max = NT-1;
const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtTime(){
  const [t0,t1,a] = timeParts();
  const ms = D.times[t0] + (D.times[t1]-D.times[t0])*a;
  const d = new Date(Math.round(ms/600000)*600000);
  const hh = String(d.getUTCHours()).padStart(2,"0"), mm = String(d.getUTCMinutes()).padStart(2,"0");
  return `${MON[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()} · ${hh}:${mm} ${D.tz}`;
}
function legend(){
  const s = PAL[layer].stops, lo = s[0][0], hi = s[s.length-1][0];
  document.getElementById("lg").style.background =
    "linear-gradient(90deg," + s.map(([v,c])=>`${c} ${((v-lo)/(hi-lo)*100).toFixed(1)}%`).join(",") + ")";
  const ticks = [s[0], s[Math.floor(s.length/3)], s[Math.floor(2*s.length/3)], s[s.length-1]];
  document.getElementById("ll").innerHTML =
    ticks.map(([v])=>`<span>${v}</span>`).join("") + `<span>${PAL[layer].unit}</span>`;
}
function refresh(){ timeEl.textContent = fmtTime(); slider.value = tf; drawField(); drawCharts(); }
document.querySelectorAll("#layers button").forEach(b=>b.onclick=()=>{
  document.querySelectorAll("#layers button").forEach(x=>x.classList.remove("on"));
  b.classList.add("on"); layer = b.dataset.layer; legend(); refresh();
});
document.getElementById("ptoggle").onchange = e=>{ showParticles = e.target.checked; };
slider.oninput = ()=>{ tf = parseFloat(slider.value); refresh(); };
playBtn.onclick = ()=>{ playing = !playing; playBtn.textContent = playing ? "❚❚" : "▶";
  if (playing && tf >= NT-1) tf = 0; };

addEventListener("pointermove", e=>{
  const [x,y] = toGrid(e.clientX, e.clientY);
  if (x<0||y<0||x>NX-1||y>NY-1){ tip.style.display="none"; return; }
  const i = Math.round(x), j = Math.round(y), k = j*NX+i;
  const [u,v] = sampleUV(x,y);
  tip.innerHTML = `<b>${sample("temp",x,y).toFixed(1)} °C</b><br>` +
    `Wind ${(Math.hypot(u,v)*3.6).toFixed(0)} km/h<br>Rain ${Math.max(0,sample("rain",x,y)).toFixed(1)} mm<br>` +
    `<span style="color:var(--muted)">${D.lat[k].toFixed(2)}°, ${D.lon[k].toFixed(2)}°</span>`;
  tip.style.display = "block";
  tip.style.left = Math.min(e.clientX+14, innerWidth-150) + "px";
  tip.style.top = (e.clientY+14) + "px";
});
addEventListener("mouseleave", ()=>tip.style.display="none");

// ---------- loop
let last = performance.now();
function loop(now){
  const dt = Math.min(0.1,(now-last)/1000); last = now;
  if (playing){
    tf += dt * (NT-1) / DURATION_S;
    if (tf >= NT-1){ tf = NT-1; playing = false; playBtn.textContent = "▶"; }
    refresh();
  }
  stepParticles();
  requestAnimationFrame(loop);
}
addEventListener("resize", resize);
legend(); resize(); refresh(); requestAnimationFrame(loop);
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else "wrf_map.html"
    data = build_data(sys.argv[1])
    html = HTML.replace("__DATA__", json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: {out} ({len(html) / 1e6:.1f} MB, {len(data['times'])} time steps)")


if __name__ == "__main__":
    main()
