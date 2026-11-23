// PWA offline-first: muestra primero lo guardado en el celular (IndexedDB) y
// después sincroniza solo los datos nuevos (deltas) cuando hay conexión.
// Mide su propia latencia de carga (KPI: <= 1,5 s, percentil 95).

const $ = (id) => document.getElementById(id);
const BD = "clima-firavitoba";
const PREVENTIVA = 3, CRITICA = 0;

function abrirBD() {
  return new Promise((ok, mal) => {
    const r = indexedDB.open(BD, 1);
    r.onupgradeneeded = () => {
      r.result.createObjectStore("lecturas", { keyPath: "t" });
      r.result.createObjectStore("alertas", { keyPath: "ts" });
    };
    r.onsuccess = () => ok(r.result);
    r.onerror = () => mal(r.error);
  });
}

function leerTodo(bd, almacen) {
  return new Promise((ok, mal) => {
    const r = bd.transaction(almacen).objectStore(almacen).getAll();
    r.onsuccess = () => ok(r.result);
    r.onerror = () => mal(r.error);
  });
}

function guardar(bd, almacen, filas) {
  return new Promise((ok, mal) => {
    const tx = bd.transaction(almacen, "readwrite");
    const s = tx.objectStore(almacen);
    filas.forEach((f) => s.put(f));
    tx.oncomplete = ok;
    tx.onerror = () => mal(tx.error);
  });
}

const hora = (ts) => new Date(ts * 1000).toLocaleString("es-CO",
  { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function pintar(lecturas, alertas) {
  $("registros").textContent = lecturas.length;
  if (!lecturas.length) return;
  const u = lecturas[lecturas.length - 1];
  $("temp").textContent = u.temp.toFixed(1);
  $("hum").textContent = Math.round(u.hum);
  $("hora").textContent = hora(u.t);
  const inicioDia = u.t - ((u.t - 5 * 3600) % 86400); // medianoche en Colombia (UTC-5)
  $("lluvia").textContent = lecturas.filter((l) => l.t >= inicioDia)
    .reduce((s, l) => s + l.lluvia, 0).toFixed(1);

  const tarjeta = $("alerta");
  const a = alertas[alertas.length - 1];
  const vigente = a && u.t - a.ts < 12 * 3600;
  tarjeta.className = "tarjeta " + (vigente ? "alerta-" + a.nivel : "alerta-ninguna");
  $("alerta-texto").textContent = vigente
    ? (a.nivel === "critica" ? "PELIGRO: helada" : "Cuidado: posible helada") +
      ` (${a.temp.toFixed(1)} °C, ${hora(a.ts)}). Proteja sus cultivos.`
    : `Sin riesgo de helada. Mínima de hoy: ${minimaHoy(lecturas, inicioDia)} °C`;
  graficar(lecturas);
}

const minimaHoy = (ls, desde) =>
  Math.min(...ls.filter((l) => l.t >= desde).map((l) => l.temp)).toFixed(1);

function graficar(lecturas) {
  const dias = new Map();
  for (const l of lecturas) {
    const d = Math.floor((l.t - 5 * 3600) / 86400);
    const v = dias.get(d) || { min: Infinity, max: -Infinity };
    v.min = Math.min(v.min, l.temp); v.max = Math.max(v.max, l.temp);
    dias.set(d, v);
  }
  const serie = [...dias.values()];
  const W = 600, H = 220, m = 30, tmin = -2, tmax = 26;
  const x = (i) => m + (i * (W - 2 * m)) / Math.max(serie.length - 1, 1);
  const y = (t) => H - m - ((t - tmin) * (H - 2 * m)) / (tmax - tmin);
  const linea = (k) => serie.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v[k]).toFixed(1)}`).join("");
  let ejes = "";
  for (let t = 0; t <= 25; t += 5)
    ejes += `<line x1="${m}" x2="${W - m}" y1="${y(t)}" y2="${y(t)}" stroke="#ddd"/>` +
            `<text x="4" y="${y(t) + 5}" font-size="13">${t}°</text>`;
  $("grafica").innerHTML = ejes +
    `<rect x="${m}" y="${y(PREVENTIVA)}" width="${W - 2 * m}" height="${y(tmin) - y(PREVENTIVA)}" fill="#cfe3ff" opacity=".6"/>` +
    `<path d="${linea("max")}" fill="none" stroke="#c0392b" stroke-width="2"/>` +
    `<path d="${linea("min")}" fill="none" stroke="#1f5fbf" stroke-width="2"/>`;
}

function hablar() {
  const texto = `${$("alerta-texto").textContent}. Temperatura ahora: ${$("temp").textContent} grados.`;
  const u = new SpeechSynthesisUtterance(texto);
  u.lang = "es-CO";
  u.rate = 0.9;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

// --- Métricas de latencia (cola local; se envían al servidor cuando hay red)
function registrarMetrica(m) {
  let cola = [];
  try { cola = JSON.parse(localStorage.getItem("metricas") || "[]"); } catch {}
  cola.push(m);
  try { localStorage.setItem("metricas", JSON.stringify(cola)); } catch {}
}

async function enviarMetricas() {
  let cola = [];
  try { cola = JSON.parse(localStorage.getItem("metricas") || "[]"); } catch {}
  if (!cola.length) return;
  const r = await fetch("/api/metricas", { method: "POST", body: JSON.stringify(cola) });
  if (r.ok) localStorage.removeItem("metricas");
}

async function sincronizar(bd, lecturas) {
  const desde = lecturas.length ? lecturas[lecturas.length - 1].t : 0;
  const r = await fetch(`/api/sync?desde=${desde}`, { cache: "no-store" });
  if (!r.ok) throw new Error(r.status);
  const d = await r.json();
  const nuevas = d.t.map((t, i) => ({ t, temp: d.temp[i], hum: d.hum[i], lluvia: d.lluvia[i] }));
  await guardar(bd, "lecturas", nuevas);
  await guardar(bd, "alertas", d.alertas);
  return nuevas.length;
}

async function iniciar() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
  $("escuchar").onclick = hablar;

  const bd = await abrirBD();
  // 1) Carga desde el celular: esto es lo que se mide como latencia local.
  let lecturas = await leerTodo(bd, "lecturas");
  let alertas = await leerTodo(bd, "alertas");
  pintar(lecturas, alertas);
  const ms = performance.now();
  $("latencia").textContent = Math.round(ms);

  // 2) Sincronización por deltas.
  let offline = 0;
  try {
    const n = await sincronizar(bd, lecturas);
    $("conexion").textContent = n ? `En línea · ${n} datos nuevos` : "En línea";
    if (n) pintar(await leerTodo(bd, "lecturas"), await leerTodo(bd, "alertas"));
  } catch {
    offline = 1;
    $("conexion").textContent = "Sin conexión · datos guardados";
  }
  registrarMetrica({ tipo: "carga_local", ms, offline, registros: lecturas.length });

  // Modo de prueba: ?bench=N recarga la página N veces para medir la latencia.
  const p = new URLSearchParams(location.search);
  const n = parseInt(p.get("bench") || "0", 10);
  if (n > 1) { p.set("bench", n - 1); location.search = p.toString(); return; }
  if (!offline) enviarMetricas().catch(() => {});
}

iniciar();
