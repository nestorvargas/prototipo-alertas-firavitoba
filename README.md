# Prototipo digital de bajo nivel – Etapa 4 (Nestor Fabian Vargas Ferrucho)

Proyecto de Ingeniería I (202337120) · Grupo 202337120_417 · Firavitoba (Boyacá)

Equipo del repositorio: Nestor Fabian Vargas Ferrucho y Miguel Angel Carrion Perez

Prototipo **simulado con apoyo de TIC** del diseño unificado de la Etapa 3:

```
[Nodo de campo]  --trama 32 B, LoRa P2P simulado (UDP) + ACK + 3 reintentos-->  [Servidor comunitario / kiosco]
 datos reales ERA5                                                                SQLite · motor de alertas (3 °C / 0 °C)
 muestreo 15 min                                                                   cola SMS (modo prueba) · API
                                                                                          |
                                                                     sincronización por deltas (JSON)
                                                                                          v
                                                                     [PWA offline-first en el celular]
                                                                      Service Worker + IndexedDB · íconos grandes · voz
```

| Bloque del diseño (Figura 4, Etapa 3) | Archivo |
|---|---|
| Entrada: sensores de campo (T, HR, lluvia) | `nodo_campo.py` + `datos/firavitoba_2020_horario.csv` |
| Enlace de campo LoRa punto a punto | `protocolo.py` (trama 32 B, CRC-16, tiempo en el aire SX1276) |
| Procesamiento: servidor comunitario y motor de alertas | `servidor_comunitario.py` |
| Salida: pasarela SMS (modo prueba) | `servidor_comunitario.py` → `resultados/sms_salida.csv` |
| Salida: PWA offline-first accesible | `pwa/` |
| Control y realimentación: ACK, duplicados, estado de nodos, métricas | `servidor_comunitario.py` (`/api/estado`, `/api/metricas`) |
| Pruebas experimentales y gráficas | `pruebas/experimentos.py`, `pruebas/graficas.py` |

Solo usa Python 3 estándar (sin instalar nada) y un navegador.

## Cómo correrlo (para el video)

Terminal 1, el servidor comunitario:

```bash
cd "prototipo_nestor"
python3 servidor_comunitario.py
```

Terminal 2, el nodo de campo (una muestra cada 0,2 s para verlo en vivo, con 10 % de pérdida):

```bash
python3 nodo_campo.py --perdida 0.1 --pausa 0.2
```

Abrir `http://localhost:8080` en Chrome. Para ver la alerta de helada (escenario de microclima de −4 °C hasta el 6 de febrero de 2020):

```bash
python3 nodo_campo.py --offset -4 --dias 36.25
```

Para empezar de cero: detener el servidor y borrar `resultados/servidor.db`; en la PWA, borrar los datos del sitio (Chrome → Configuración del sitio → Borrar datos).

Prueba sin conexión: con la PWA abierta una vez, detener el servidor (Ctrl+C) y recargar. Abre igual con los datos guardados. `http://localhost:8080/?bench=20` recarga 20 veces y mide la latencia.

## Pruebas experimentales

```bash
python3 pruebas/experimentos.py
```

Genera en `resultados/` las tablas CSV (E1 a E5), las gráficas (SVG y PNG) y `resultados.json`. El análisis está en `informe_pruebas.md`.

## Datos reales y límites honestos

- Temperatura, humedad y lluvia: Open-Meteo Historical Weather API (reanálisis ERA5), Firavitoba, 1 de enero a 30 de marzo de 2020, interpolado a 15 min. Se descarga con `python3 datos/descargar_datos.py`.
- El enlace LoRa se **simula** sobre UDP local con pérdidas aleatorias; el tiempo en el aire sí se calcula con la fórmula de Semtech.
- La energía se **calcula** con las corrientes de diseño y el tiempo real de cada transmisión; no es una medición con amperímetro.
- La pasarela SMS está en **modo prueba**: encola los mensajes, no los envía. Los números del padrón son ficticios.
