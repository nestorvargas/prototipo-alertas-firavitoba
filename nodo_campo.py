"""Nodo de campo (estación agrometeorológica) simulado.

Reproduce el comportamiento del nodo del diseño unificado:
  - Muestreo cada 15 min (T_s = 900 s) a partir de datos meteorológicos
    reales de Firavitoba (Open-Meteo / ERA5, 2020), interpolados de horario
    a 15 min.
  - Arma la trama de 32 bytes y la envía por el enlace LoRa punto a punto,
    simulado sobre UDP local con una probabilidad de pérdida configurable.
  - Espera confirmación (ACK) y reintenta hasta N veces.
  - Lleva la contabilidad de energía con el tiempo en el aire LoRa real
    de cada transmisión (SX1276: 120 mA en TX a +20 dBm, 10,3 mA en RX).

El tiempo se comprime: el nodo no espera 15 min reales entre muestras.

Uso:  python3 nodo_campo.py --perdida 0.1 --dias 90
"""
import argparse
import csv
import datetime as dt
import pathlib
import random
import socket
import time

import protocolo

DATOS = pathlib.Path(__file__).parent / "datos" / "firavitoba_2020_horario.csv"
ZONA = dt.timezone(dt.timedelta(hours=-5))  # America/Bogota

# Corrientes de diseño (Etapa 3) y hojas de datos
I_TX_MA = 120.0      # SX1276 a +20 dBm
I_RX_MA = 10.3       # SX1276 en recepción (ventana de ACK)
I_MCU_MA = 40.0      # MCU activo midiendo sensores (supuesto de diseño)
I_SLEEP_MA = 0.01    # sueño profundo
T_SENSORES_S = 2.0   # lectura de sensores por muestra (supuesto)
T_VENTANA_ACK_S = 0.5
V_NOMINAL = 3.3


def cargar_muestras(dias=90, offset_c=0.0):
    """Lee el CSV horario y devuelve muestras cada 15 min (interpolación lineal).
    offset_c permite un escenario de prueba (p. ej. microclima de ladera)."""
    filas = []
    with DATOS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["temperatura_c"] in ("", "None"):
                continue
            t = dt.datetime.fromisoformat(r["fecha_hora"]).replace(tzinfo=ZONA)
            filas.append((t.timestamp(), float(r["temperatura_c"]),
                          float(r["humedad_pct"]), float(r["lluvia_mm"])))
    muestras = []
    for (t0, a0, h0, l0), (t1, a1, h1, l1) in zip(filas, filas[1:]):
        for k in range(4):
            x = k / 4
            muestras.append((t0 + 900 * k, a0 + (a1 - a0) * x + offset_c,
                             h0 + (h1 - h0) * x, l0 / 4))
    return muestras[: int(dias * 96)]


class Nodo:
    def __init__(self, nodo_id=1, servidor=("127.0.0.1", 5005), perdida=0.0,
                 reintentos=3, semilla=42, sf=9):
        self.id = nodo_id
        self.servidor = servidor
        self.perdida = perdida
        self.reintentos = reintentos
        self.rng = random.Random(semilla)
        self.toa_s = protocolo.tiempo_en_aire_lora(sf=sf)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.05)
        self.seq = 0
        self.stats = {"muestras": 0, "transmisiones": 0, "entregadas": 0,
                      "entregadas_1er_intento": 0, "perdidas": 0, "carga_mAs": 0.0}

    def _enlace(self, trama):
        """Canal LoRa simulado: la trama o su ACK pueden perderse."""
        if self.rng.random() < self.perdida:
            return False                         # se pierde la trama
        self.sock.sendto(trama, self.servidor)
        try:
            resp, _ = self.sock.recvfrom(16)
        except socket.timeout:
            return False
        if self.rng.random() < self.perdida:
            return False                         # se pierde el ACK
        return resp.startswith(protocolo.ACK) and resp[3:7] == trama[3:7]

    def enviar_muestra(self, ts, temp, hum, lluvia, bat_mv=3300):
        self.seq += 1
        self.stats["muestras"] += 1
        carga = I_MCU_MA * T_SENSORES_S
        for intento in range(self.reintentos + 1):
            trama = protocolo.empaquetar(self.id, self.seq, ts, temp, hum, lluvia,
                                         bat_mv, banderas=int(intento > 0))
            self.stats["transmisiones"] += 1
            carga += I_TX_MA * self.toa_s + I_RX_MA * T_VENTANA_ACK_S
            if self._enlace(trama):
                self.stats["entregadas"] += 1
                if intento == 0:
                    self.stats["entregadas_1er_intento"] += 1
                break
        else:
            self.stats["perdidas"] += 1
        self.stats["carga_mAs"] += carga
        return carga

    def corriente_promedio_ma(self):
        """Corriente media con ciclo de trabajo, a partir de las cargas medidas."""
        n = self.stats["muestras"]
        if not n:
            return 0.0
        q_activa = self.stats["carga_mAs"] / n          # mA·s por muestra
        return (q_activa + I_SLEEP_MA * 900) / 900       # promedio en 15 min


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perdida", type=float, default=0.0)
    ap.add_argument("--dias", type=float, default=90)
    ap.add_argument("--reintentos", type=int, default=3)
    ap.add_argument("--pausa", type=float, default=0.0,
                    help="segundos reales entre muestras (0 = lo más rápido)")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="escenario de microclima: °C sumados a la serie real (p. ej. -4)")
    a = ap.parse_args()
    nodo = Nodo(perdida=a.perdida, reintentos=a.reintentos)
    for ts, t, h, ll in cargar_muestras(a.dias, offset_c=a.offset):
        nodo.enviar_muestra(ts, t, h, ll)
        if a.pausa:
            time.sleep(a.pausa)
    print(nodo.stats)
    print(f"Corriente promedio: {nodo.corriente_promedio_ma():.3f} mA")


if __name__ == "__main__":
    main()
