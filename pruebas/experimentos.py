"""Banco de pruebas experimentales del prototipo (Etapa 4).

Ejecuta el sistema completo (nodo de campo -> enlace LoRa simulado ->
servidor comunitario -> motor de alertas -> cola SMS -> API de la PWA) y
contrasta los resultados con los KPIs de la Etapa 3.

Experimentos:
  E1  Operación nominal con datos reales ERA5 (90 días, enlace sin pérdidas).
  E2  Confiabilidad del enlace: pérdidas de 0 a 30 % con 3 reintentos.
  E3  Sensibilidad del motor de alertas al microclima (desplazamiento de
      0 a -5 °C sobre la serie real, escenario de prueba).
  E4  Consumo de datos de la PWA (sincronización por deltas, bytes reales HTTP).

Salidas en ../resultados: CSV por experimento, gráficas SVG y resumen.md.

Uso:  python3 pruebas/experimentos.py
"""
import csv
import http.client
import json
import pathlib
import statistics
import sys
import threading
import time

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))
import nodo_campo as N            # noqa: E402
import protocolo as P             # noqa: E402
import servidor_comunitario as S  # noqa: E402
import graficas as G              # noqa: E402

RES = RAIZ / "resultados"
RES.mkdir(exist_ok=True)

# Parámetros de diseño de la Etapa 3
BATERIA_WH = 3.2 * 2.6          # LiFePO4 3,2 V 2,6 Ah = 8,32 Wh
DOD, EFICIENCIA = 0.80, 0.90
I_DISENO_MA = 1.34
KPI_ENTREGA = 98.0
KPI_DATOS_KB_DIA = 10.0
KPI_AUTONOMIA_D = 30.0


def autonomia_dias(i_ma):
    p_w = i_ma / 1000 * N.V_NOMINAL
    return BATERIA_WH * DOD * EFICIENCIA / (p_w * 24)


def pct(x, q):
    xs = sorted(x)
    return xs[min(len(xs) - 1, int(round(q / 100 * (len(xs) - 1))))]


def correr(muestras, perdida=0.0, puerto=5100, semilla=42):
    """Corre nodo + servidor y devuelve (nodo, servidor, segundos)."""
    srv = S.Servidor(archivo_sms=RES / f"sms_salida_p{puerto}.csv")
    ev = threading.Event()
    th = threading.Thread(target=srv.escuchar_udp,
                          kwargs={"puerto": puerto, "detener": ev})
    th.start()
    nodo = N.Nodo(servidor=("127.0.0.1", puerto), perdida=perdida, semilla=semilla)
    t0 = time.perf_counter()
    for m in muestras:
        nodo.enviar_muestra(*m)
    seg = time.perf_counter() - t0
    ev.set()
    th.join()
    return nodo, srv, seg


def escribir_csv(nombre, cabecera, filas):
    with (RES / nombre).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecera)
        w.writerows(filas)


def e1_nominal():
    muestras = N.cargar_muestras(90)
    nodo, srv, seg = correr(muestras, 0.0, 5101)
    temps = [m[1] for m in muestras]
    n_alertas = srv.db.execute("SELECT COUNT(*) FROM alertas").fetchone()[0]
    escribir_csv("e1_serie_temperatura.csv", ["epoch", "temperatura_c", "humedad_pct", "lluvia_mm"],
                 [(int(m[0]), round(m[1], 2), round(m[2], 1), round(m[3], 2)) for m in muestras])
    G.serie_temperatura(muestras, RES / "g1_temperatura_90dias.svg")
    return {
        "muestras": len(muestras), "dias": round(len(muestras) / 96, 2),
        "recibidas": srv.estado()["lecturas"], "tmin": min(temps), "tmax": max(temps),
        "tmedia": round(statistics.mean(temps), 2), "alertas": n_alertas,
        "bytes_dia_campo": 96 * P.TAM_TRAMA, "toa_ms": round(nodo.toa_s * 1000, 1),
        "i_ma": round(nodo.corriente_promedio_ma(), 4),
        "autonomia_d": round(autonomia_dias(nodo.corriente_promedio_ma()), 1),
        "seg": round(seg, 2),
    }


def e2_enlace():
    muestras = N.cargar_muestras(90)
    filas = []
    for k, perdida in enumerate([0.0, 0.05, 0.10, 0.20, 0.30]):
        nodo, srv, _ = correr(muestras, perdida, 5110 + k)
        st = nodo.stats
        i = nodo.corriente_promedio_ma()
        recibidas = srv.estado()["lecturas"]
        filas.append([
            int(perdida * 100), st["muestras"],
            round(100 * st["entregadas_1er_intento"] / st["muestras"], 2),
            round(100 * st["entregadas"] / st["muestras"], 3),
            round(100 * recibidas / st["muestras"], 3),
            st["muestras"] - recibidas, round(st["transmisiones"] / st["muestras"], 3),
            srv.duplicados, round(i, 4), round(autonomia_dias(i), 1)])
    escribir_csv("e2_confiabilidad_enlace.csv",
                 ["perdida_pct", "muestras", "confirmadas_1er_intento_pct",
                  "confirmadas_con_reintentos_pct", "recibidas_servidor_pct",
                  "muestras_perdidas_servidor", "transmisiones_por_muestra",
                  "duplicados_descartados", "corriente_promedio_ma", "autonomia_dias"], filas)
    G.dispersion(
        [("Confirmadas al 1er intento", [(f[0], f[2]) for f in filas], "#c0392b"),
         ("Recibidas en servidor (3 reintentos)", [(f[0], f[4]) for f in filas], "#1f6f43")],
        "Pérdida en el enlace (%)", "Muestras entregadas (%)",
        RES / "g2_entrega_vs_perdida.svg", kpi=(KPI_ENTREGA, "KPI 98 %"), ymin=40, ymax=100)
    G.dispersion(
        [("Corriente calculada por transmisión", [(f[0], f[8]) for f in filas], "#1f5fbf")],
        "Pérdida en el enlace (%)", "Corriente promedio (mA)",
        RES / "g3_corriente_vs_perdida.svg", kpi=(I_DISENO_MA, "Diseño Etapa 3: 1,34 mA"),
        ymin=0, ymax=1.5)
    return filas


def e3_microclima():
    filas, latencias = [], []
    for k, off in enumerate([0, -1, -2, -3, -4, -5]):
        muestras = N.cargar_muestras(90, offset_c=off)
        _, srv, _ = correr(muestras, 0.0, 5120 + k)
        al = srv.db.execute(
            "SELECT nivel, ts, temp_c, (encolado-detectado)*1000, n_sms FROM alertas").fetchall()
        prev = sum(1 for a in al if a[0] == "preventiva")
        crit = sum(1 for a in al if a[0] == "critica")
        lat = [a[3] for a in al]
        latencias += [(off, x) for x in lat]
        largo = 0
        with srv.archivo_sms.open(encoding="utf-8") as f:
            r = list(csv.DictReader(f))
            largo = max((int(x["caracteres"]) for x in r), default=0)
        filas.append([off, round(min(m[1] for m in muestras), 2), prev, crit,
                      sum(a[4] for a in al),
                      round(pct(lat, 95), 3) if lat else "",
                      round(max(lat), 3) if lat else "", largo])
        if off == -4:
            escribir_csv("e3_alertas_detalle_offset_-4.csv",
                         ["nivel", "fecha_hora", "temperatura_c", "latencia_ms", "sms"],
                         [(a[0], time.strftime("%Y-%m-%d %H:%M", time.localtime(a[1])),
                           a[2], round(a[3], 3), a[4]) for a in al])
    escribir_csv("e3_sensibilidad_microclima.csv",
                 ["desplazamiento_c", "minima_c", "alertas_preventivas", "alertas_criticas",
                  "sms_encolados", "latencia_p95_ms", "latencia_max_ms", "sms_max_caracteres"], filas)
    G.dispersion([("Latencia por alerta", latencias, "#8e44ad")],
                 "Desplazamiento de microclima (°C)", "Detección → SMS en cola (ms)",
                 RES / "g4_latencia_alertas.svg", ymin=0,
                 ymax=max([x for _, x in latencias] + [1]) * 1.2)
    return filas


def e4_datos_pwa():
    muestras = N.cargar_muestras(90)
    _, srv, _ = correr(muestras, 0.0, 5130)
    http_srv = S.crear_http(srv, 8099)
    th = threading.Thread(target=http_srv.serve_forever, daemon=True)
    th.start()
    ult = srv.estado()["ultima_ts"]

    def medir(desde):
        c = http.client.HTTPConnection("127.0.0.1", 8099)
        c.request("GET", f"/api/sync?desde={desde}")
        r = c.getresponse()
        cuerpo = r.read()
        cab = sum(len(k) + len(v) + 4 for k, v in r.getheaders()) + 17
        c.close()
        return len(json.loads(cuerpo)["t"]), len(cuerpo), cab

    filas = []
    for nombre, desde in [("Sincronización diaria (1 día)", ult - 86400),
                          ("Sincronización semanal (7 días)", ult - 7 * 86400),
                          ("Carga inicial (90 días)", 0)]:
        n, cuerpo, cab = medir(desde)
        dias = max((ult - desde) / 86400, 1) if desde else len(muestras) / 96
        filas.append([nombre, n, cuerpo, cab, round((cuerpo + cab) / 1024, 2),
                      round((cuerpo + cab) / 1024 / dias, 2)])
    http_srv.shutdown()
    escribir_csv("e4_datos_pwa.csv",
                 ["escenario", "registros", "bytes_cuerpo", "bytes_cabeceras",
                  "kb_total", "kb_por_dia"], filas)
    return filas


def e5_latencia_pwa():
    """Lee las latencias que la PWA reportó al servidor (prueba en navegador)."""
    import sqlite3
    db = RES / "metricas_pwa.db"   # copia de servidor.db tras la prueba en navegador
    if not db.exists():
        db = RES / "servidor.db"
    if not db.exists():
        return None
    filas = sqlite3.connect(db).execute(
        "SELECT valor_ms, offline FROM metricas_pwa ORDER BY recibido").fetchall()
    if not filas:
        return None
    escribir_csv("e5_latencia_pwa.csv", ["carga", "latencia_ms", "sin_conexion"],
                 [(k + 1, round(ms, 1), off) for k, (ms, off) in enumerate(filas)])
    res = {}
    for off, nombre in [(0, "en_linea"), (1, "sin_conexion")]:
        v = [ms for ms, o in filas if o == off]
        if v:
            res[nombre] = {"n": len(v), "media_ms": round(statistics.mean(v), 1),
                           "p95_ms": round(pct(v, 95), 1), "max_ms": round(max(v), 1)}
    G.dispersion(
        [("En línea", [(k + 1, ms) for k, (ms, o) in enumerate(filas) if not o], "#1f6f43"),
         ("Sin conexión (servidor apagado)", [(k + 1, ms) for k, (ms, o) in enumerate(filas) if o], "#c0392b")],
        "Número de carga", "Latencia de carga local (ms)",
        RES / "g5_latencia_pwa.svg", kpi=(1500, "KPI 1 500 ms"), ymin=0, ymax=1600)
    return res


def main():
    t0 = time.time()
    r1 = e1_nominal()
    print("E1", r1)
    r2 = e2_enlace()
    print("E2", *r2, sep="\n  ")
    r3 = e3_microclima()
    print("E3", *r3, sep="\n  ")
    r4 = e4_datos_pwa()
    print("E4", *r4, sep="\n  ")
    r5 = e5_latencia_pwa()
    print("E5", r5)
    (RES / "resultados.json").write_text(json.dumps(
        {"e1": r1, "e2": r2, "e3": r3, "e4": r4, "e5": r5,
         "ejecutado": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    # PNG para Word y el foro (requiere macOS: qlmanage + sips)
    import shutil
    import subprocess
    if shutil.which("qlmanage"):
        for svg in RES.glob("g*.svg"):
            subprocess.run(["qlmanage", "-t", "-s", "1200", "-o", str(RES), str(svg)],
                           capture_output=True)
            png = RES / (svg.name + ".png")
            if png.exists():
                destino = svg.with_suffix(".png")
                png.replace(destino)
                subprocess.run(["sips", "-c", "663", "1200", str(destino)], capture_output=True)
    for f in RES.glob("sms_salida_p*.csv"):
        if f.name != "sms_salida_p5124.csv":   # se conserva el escenario de -4 °C
            f.unlink()
    print(f"Listo en {time.time() - t0:.1f} s. Resultados en {RES}")


if __name__ == "__main__":
    main()
