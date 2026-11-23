"""Descarga datos meteorológicos históricos reales de Firavitoba (Boyacá).

Fuente: Open-Meteo Historical Weather API (reanálisis ERA5 / ERA5-Land).
Periodo: 1 de enero a 31 de marzo de 2020 (90 días), temporada seca con el
evento de heladas del 21 de febrero de 2020 reportado por el DANE (SIPSA).

Los datos son horarios; el nodo de campo los interpola a 15 minutos, que es
el periodo de muestreo del diseño (T_s = 900 s).

Uso:  python3 descargar_datos.py
"""
import csv
import json
import pathlib
import urllib.request

LAT, LON = 5.6667, -72.9833  # Firavitoba, Boyacá
URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    f"?latitude={LAT}&longitude={LON}"
    "&start_date=2020-01-01&end_date=2020-03-30"
    "&hourly=temperature_2m,relative_humidity_2m,precipitation"
    "&timezone=America%2FBogota"
)
SALIDA = pathlib.Path(__file__).with_name("firavitoba_2020_horario.csv")


def main():
    with urllib.request.urlopen(URL, timeout=60) as r:
        d = json.load(r)
    h = d["hourly"]
    with SALIDA.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fecha_hora", "temperatura_c", "humedad_pct", "lluvia_mm"])
        for row in zip(h["time"], h["temperature_2m"],
                       h["relative_humidity_2m"], h["precipitation"]):
            w.writerow(row)
    print(f"{len(h['time'])} registros horarios -> {SALIDA.name} "
          f"(elevación de la celda: {d.get('elevation')} m)")


if __name__ == "__main__":
    main()
