"""Servidor comunitario (nodo local / kiosco) del diseño unificado.

Bloques que implementa:
  - Recepción del enlace de campo (LoRa simulado sobre UDP local) con
    validación de CRC, confirmación (ACK) y descarte de duplicados.
  - Almacenamiento local (SQLite).
  - Motor de alertas de helada con umbrales explícitos y auditables:
    preventiva <= 3 °C, crítica <= 0 °C, histéresis de 1 °C.
  - Pasarela SMS en modo prueba: escribe cada mensaje en una cola
    (resultados/sms_salida.csv) con su marca de tiempo. No envía SMS reales.
  - API HTTP para la PWA (sincronización por deltas) y monitoreo de nodos.

Uso:  python3 servidor_comunitario.py   (PWA en http://localhost:8080)
"""
import csv
import json
import pathlib
import socket
import sqlite3
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import protocolo

RAIZ = pathlib.Path(__file__).parent
PWA = RAIZ / "pwa"
RESULTADOS = RAIZ / "resultados"

UMBRAL_PREVENTIVA = 3.0
UMBRAL_CRITICA = 0.0
HISTERESIS = 1.0

# Padrón de PRUEBA (números ficticios). En operación real el número exige
# autorización previa e informada del titular (Ley 1581 de 2012, art. 9).
PADRON = [
    {"nombre": "Agricultor prueba 1", "celular": "+57 300 000 0001", "vereda": "Diravita"},
    {"nombre": "Agricultor prueba 2", "celular": "+57 300 000 0002", "vereda": "Alcaparral"},
    {"nombre": "Agricultor prueba 3", "celular": "+57 300 000 0003", "vereda": "Baratoa"},
]

MENSAJES = {
    "preventiva": "ALERTA HELADA PREVENTIVA {vereda}: {temp:.1f} C a las {hora}. "
                  "Cubra cultivos y riegue antes del amanecer. Info: kiosco JAC.",
    "critica": "ALERTA HELADA CRITICA {vereda}: {temp:.1f} C a las {hora}. "
               "Proteja cultivos y animales YA. Info: kiosco JAC.",
}


class Servidor:
    def __init__(self, db=":memory:", archivo_sms=None):
        self.db = sqlite3.connect(db, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS lecturas(
                nodo INT, seq INT, ts INT, temp_c REAL, hum_pct REAL,
                lluvia_mm REAL, bat_mv INT, recibido REAL,
                PRIMARY KEY(nodo, seq));
            CREATE TABLE IF NOT EXISTS alertas(
                id INTEGER PRIMARY KEY, nodo INT, nivel TEXT, ts INT,
                temp_c REAL, detectado REAL, encolado REAL, n_sms INT);
            CREATE TABLE IF NOT EXISTS metricas_pwa(
                tipo TEXT, valor_ms REAL, offline INT, recibido REAL);
        """)
        self.estado_alerta = {}  # nodo -> nivel activo (None/preventiva/critica)
        self.ultimo_visto = {}
        self.tramas_invalidas = 0
        self.duplicados = 0
        self.archivo_sms = archivo_sms or (RESULTADOS / "sms_salida.csv")
        self.archivo_sms.parent.mkdir(exist_ok=True)
        with self.archivo_sms.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["encolado_epoch", "celular", "nivel", "caracteres", "mensaje"])

    # ---------------- Enlace de campo ----------------
    def procesar_trama(self, trama: bytes):
        """Valida, guarda y evalúa una trama. Devuelve True si debe enviarse ACK."""
        t0 = time.perf_counter()
        try:
            r = protocolo.desempaquetar(trama)
        except ValueError:
            self.tramas_invalidas += 1
            return False
        with self.lock:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO lecturas VALUES (?,?,?,?,?,?,?,?)",
                (r["nodo"], r["seq"], r["ts"], r["temp_c"], r["hum_pct"],
                 r["lluvia_mm"], r["bat_mv"], time.time()))
            nueva = cur.rowcount == 1
            self.db.commit()
        if not nueva:
            self.duplicados += 1   # reintento de una trama ya recibida
            return True            # se confirma de nuevo para que el nodo no insista
        self.ultimo_visto[r["nodo"]] = time.time()
        self.evaluar_helada(r, t0)
        return True

    def evaluar_helada(self, r, t0):
        nodo, temp = r["nodo"], r["temp_c"]
        activo = self.estado_alerta.get(nodo)
        nivel = None
        if temp <= UMBRAL_CRITICA and activo != "critica":
            nivel = "critica"
        elif temp <= UMBRAL_PREVENTIVA and activo is None:
            nivel = "preventiva"
        if nivel:
            self.estado_alerta[nodo] = nivel
            self.encolar_sms(r, nivel, t0)
        elif activo and temp > UMBRAL_PREVENTIVA + HISTERESIS:
            self.estado_alerta[nodo] = None  # fin del evento

    def encolar_sms(self, r, nivel, t0):
        hora = time.strftime("%H:%M", time.localtime(r["ts"]))
        filas = []
        for p in PADRON:
            msg = MENSAJES[nivel].format(vereda=p["vereda"], temp=r["temp_c"], hora=hora)
            filas.append([f"{time.time():.6f}", p["celular"], nivel, len(msg), msg])
        with self.archivo_sms.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(filas)
        t1 = time.perf_counter()
        with self.lock:
            self.db.execute(
                "INSERT INTO alertas(nodo,nivel,ts,temp_c,detectado,encolado,n_sms)"
                " VALUES (?,?,?,?,?,?,?)",
                (r["nodo"], nivel, r["ts"], r["temp_c"], t0, t1, len(filas)))
            self.db.commit()

    def escuchar_udp(self, puerto=5005, detener=None):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", puerto))
        s.settimeout(0.2)
        while not (detener and detener.is_set()):
            try:
                trama, origen = s.recvfrom(64)
            except socket.timeout:
                continue
            if self.procesar_trama(trama):
                s.sendto(protocolo.ACK + trama[3:7], origen)  # ACK + seq
        s.close()

    # ---------------- API para la PWA ----------------
    def sync(self, desde_ts=0, limite=20000):
        with self.lock:
            filas = self.db.execute(
                "SELECT ts, temp_c, hum_pct, lluvia_mm FROM lecturas "
                "WHERE ts > ? ORDER BY ts LIMIT ?", (desde_ts, limite)).fetchall()
            alertas = self.db.execute(
                "SELECT nivel, ts, temp_c FROM alertas WHERE ts > ? ORDER BY ts",
                (desde_ts,)).fetchall()
        # Formato compacto: columnas separadas para reducir bytes por el enlace.
        return {"t": [f[0] for f in filas], "temp": [f[1] for f in filas],
                "hum": [f[2] for f in filas], "lluvia": [f[3] for f in filas],
                "alertas": [{"nivel": a[0], "ts": a[1], "temp": a[2]} for a in alertas]}

    def estado(self):
        ahora = time.time()
        with self.lock:
            n = self.db.execute("SELECT COUNT(*) FROM lecturas").fetchone()[0]
            ult = self.db.execute("SELECT MAX(ts), MIN(ts) FROM lecturas").fetchone()
        return {"lecturas": n, "ultima_ts": ult[0], "primera_ts": ult[1],
                "tramas_invalidas": self.tramas_invalidas,
                "duplicados": self.duplicados,
                "nodos": {str(k): round(ahora - v, 1) for k, v in self.ultimo_visto.items()},
                "alerta_activa": {str(k): v for k, v in self.estado_alerta.items()}}


def crear_http(servidor: Servidor, puerto=8080):
    class Manejador(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(PWA), **k)

        def log_message(self, *a):
            pass

        def _json(self, obj, codigo=200):
            cuerpo = json.dumps(obj, separators=(",", ":")).encode()
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/api/sync":
                return self._json(servidor.sync(int(q.get("desde", ["0"])[0])))
            if u.path == "/api/estado":
                return self._json(servidor.estado())
            if u.path == "/api/metricas":
                with servidor.lock:
                    filas = servidor.db.execute(
                        "SELECT tipo, valor_ms, offline FROM metricas_pwa").fetchall()
                return self._json([{"tipo": a, "ms": b, "offline": c} for a, b, c in filas])
            return super().do_GET()

        def do_POST(self):
            if urlparse(self.path).path == "/api/metricas":
                n = int(self.headers.get("Content-Length", 0))
                datos = json.loads(self.rfile.read(n) or b"[]")
                with servidor.lock:
                    servidor.db.executemany(
                        "INSERT INTO metricas_pwa VALUES (?,?,?,?)",
                        [(m["tipo"], m["ms"], int(m.get("offline", 0)), time.time())
                         for m in datos])
                    servidor.db.commit()
                return self._json({"ok": len(datos)})
            self.send_error(404)

    return ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)


def main():
    srv = Servidor(db=str(RESULTADOS / "servidor.db"))
    threading.Thread(target=srv.escuchar_udp, daemon=True).start()
    http = crear_http(srv)
    print("Servidor comunitario listo:")
    print("  enlace de campo (LoRa simulado): UDP 127.0.0.1:5005")
    print("  PWA y API: http://localhost:8080")
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
