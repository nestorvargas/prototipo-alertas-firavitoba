# Informe de pruebas experimentales – Prototipo de Nestor Fabian Vargas Ferrucho

Etapa 4 – Componente práctico · Proyecto de Ingeniería I (202337120) · Grupo 202337120_417
Pruebas ejecutadas el 19 de noviembre de 2026 con `pruebas/experimentos.py` y Chrome.

## 1. Qué se construyó

Un prototipo digital de bajo nivel (simulado con apoyo de TIC) que materializa los bloques del diseño unificado de la Etapa 3 (Figura 4): nodo de campo → enlace LoRa punto a punto → servidor comunitario con motor de alertas y cola SMS → PWA offline-first. Cada bloque es un programa que corre de verdad y se comunica con el siguiente; la única parte simulada es el medio físico (radio LoRa, sensores y batería).

Entrada de datos: serie real de temperatura, humedad y lluvia de Firavitoba (reanálisis ERA5, Open-Meteo), del 1 de enero al 30 de marzo de 2020, 8 636 muestras cada 15 min (89,96 días).

## 2. Contraste con los KPIs de la Etapa 3

| KPI (Tabla 9, Etapa 3) | Umbral | Resultado medido | Estado |
|---|---|---|---|
| Latencia de la PWA desde caché | ≤ 1,5 s (p95) | Sin conexión: media 53,9 ms, **p95 79,1 ms** (20 cargas). En línea: media 69,8 ms, p95 243 ms (24 cargas) | Cumple (en PC; falta gama baja) |
| Historial sin conexión | 90 días | 8 636 registros (89,96 días) visibles con el servidor apagado, 20 de 20 cargas | Cumple |
| Entrega de datos del enlace de campo | ≥ 98 % | Recibidas en el servidor: 100 % con 0–10 % de pérdida, **99,78 %** con 20 %, **99,06 %** con 30 % | Cumple hasta 30 % de pérdida |
| Entrega de alerta de helada por SMS | ≥ 98 % en ≤ 5 min | Detección → SMS en cola: p95 ≤ 0,73 ms; 3 de 3 destinatarios por alerta; mensajes de 114–117 caracteres (1 segmento) | Parcial: falta la entrega real del operador |
| Autonomía del nodo de campo | ≥ 30 días | 439–550 días calculados (0,1375–0,1721 mA) | Cumple (cálculo, falta medición) |
| Consumo de datos por usuario | ≤ 10 KB/día | **2,61 KB/día** (sincronización diaria real por HTTP, con cabeceras) | Cumple |
| Accesibilidad | WCAG 2.2 AA, ≥ 80 % de tareas | Texto de 20 px, botón de 64 px, alto contraste, lectura en voz alta | Pendiente prueba con ≥ 5 usuarios |
| Cobertura de alertas | 100 % de inscritos | 100 % del padrón de prueba (3/3) por alerta | Cumple en prueba |

## 3. Experimentos y datos

### E1 – Operación nominal (datos reales, enlace sin pérdidas)

| Variable | Valor |
|---|---|
| Muestras enviadas / recibidas | 8 636 / 8 636 |
| Temperatura mínima / media / máxima | 3,8 °C / 15,73 °C / 26,8 °C |
| Alertas generadas | 0 |
| Volumen del enlace de campo | 96 × 32 B = 3 072 B/día (igual al diseño: 3,07 KB/día) |
| Tiempo en el aire LoRa (SF9, 125 kHz, 32 B) | 246,8 ms |

Gráfica: `resultados/g1_temperatura_90dias.png`.

### E2 – Confiabilidad del enlace (3 reintentos con ACK)

| Pérdida (%) | Confirmadas al 1er intento (%) | Recibidas en servidor (%) | Transmisiones por muestra | Duplicados descartados | Corriente (mA) | Autonomía (días) |
|---|---|---|---|---|---|---|
| 0 | 100,00 | 100,000 | 1,000 | 0 | 0,1375 | 550,0 |
| 5 | 90,83 | 100,000 | 1,100 | 423 | 0,1414 | 535,0 |
| 10 | 80,88 | 100,000 | 1,230 | 918 | 0,1464 | 516,7 |
| 20 | 62,97 | 99,780 | 1,548 | 2 005 | 0,1587 | 476,7 |
| 30 | 49,12 | 99,062 | 1,896 | 2 868 | 0,1721 | 439,4 |

La pérdida se aplica a la trama y al ACK por separado, así que la probabilidad de que un intento falle es 1 − (1 − p)². Con p = 0,30 y 4 intentos, la entrega esperada es 1 − 0,51⁴ = 93,2 % confirmada por el nodo, y lo medido fue 93,63 %. El servidor recibe más (99,06 %) porque muchas tramas llegan aunque se pierda el ACK; esas llegadas repetidas son los duplicados que descarta. Gráficas: `g2_entrega_vs_perdida.png`, `g3_corriente_vs_perdida.png`.

### E3 – Sensibilidad del motor de alertas al microclima

Escenario de prueba: a la serie real se le resta de 0 a 5 °C para representar el enfriamiento de los fondos de valle y del nivel del cultivo, que una celda de reanálisis de unos 9 km no captura.

| Desplazamiento (°C) | Mínima (°C) | Alertas preventivas | Alertas críticas | SMS en cola | Latencia p95 (ms) |
|---|---|---|---|---|---|
| 0 | 3,8 | 0 | 0 | 0 | – |
| −1 | 2,8 | 1 | 0 | 3 | 0,418 |
| −2 | 1,8 | 1 | 0 | 3 | 0,407 |
| −3 | 0,8 | 2 | 0 | 6 | 0,366 |
| −4 | −0,2 | 9 | 1 | 30 | 0,730 |
| −5 | −1,2 | 19 | 1 | 60 | 0,495 |

Con −4 °C, la alerta crítica cae el 6 de febrero de 2020 a las 03:00 (−0,2 °C), precedida por una preventiva a las 23:45 del día anterior: 3 h 15 min de anticipación. Detalle: `e3_alertas_detalle_offset_-4.csv`. Gráfica: `g4_latencia_alertas.png`.

### E4 – Consumo de datos de la PWA (bytes reales por HTTP)

| Escenario | Registros | Cuerpo (B) | Cabeceras (B) | Total (KB) | KB/día |
|---|---|---|---|---|---|
| Sincronización diaria | 96 | 2 510 | 167 | 2,61 | 2,61 |
| Sincronización semanal | 672 | 17 366 | 168 | 17,12 | 2,45 |
| Carga inicial (90 días) | 8 636 | 221 712 | 169 | 216,68 | 2,41 |

### E5 – Latencia de carga de la PWA (Chrome, Performance API)

| Condición | Cargas | Media (ms) | p95 (ms) | Máx. (ms) |
|---|---|---|---|---|
| En línea | 24 | 69,8 | 243,0 | 287,4 |
| Sin conexión (servidor apagado) | 20 | 53,9 | 79,1 | 86,2 |

Gráfica: `g5_latencia_pwa.png`. Evidencias: `evidencias/pwa_sin_conexion.jpg`, `evidencias/pwa_alerta_helada_critica.jpg`.

## 4. Desvíos frente al modelo conceptual

1. **Corriente del nodo: 0,1375 mA frente a 1,34 mA del diseño (−89,7 %).** El diseño suponía 10 s activos a 120 mA en cada ciclo. El tiempo real de la transmisión LoRa es de 0,247 s; lo que más consume es la lectura de sensores (2 s a 40 mA) y la ventana del ACK. La autonomía pasa de unos 57 días a unos 550 días calculados. Es una cota optimista: no incluye el regulador, la autodescarga ni la corriente en reposo de los sensores. Hay que medirlo en banco con un sensor INA219.
2. **El reanálisis no muestra heladas (mínima de 3,8 °C).** El DANE reportó heladas en Boyacá en febrero de 2020, pero la celda ERA5 promedia unos 9 km y no capta el enfriamiento radiativo del fondo del valle. El hallazgo más importante es que **los datos abiertos no bastan para alertar heladas**: hace falta la estación local, que es justamente el bloque de entrada del diseño.
3. **Datos por usuario: 2,61 KB/día frente a 10 KB/día del KPI.** Cada registro viaja en unos 26 B de JSON (las columnas van separadas), menos que la trama de 32 B.
4. **El ACK cambia la métrica de entrega.** Con pérdidas, el nodo "cree" que perdió más tramas de las que en realidad faltan en el servidor (93,63 % contra 99,06 % al 30 %). El KPI se debe medir en el servidor, y la pérdida de ACK cuesta energía, porque genera reintentos innecesarios.
5. **La latencia se midió en un PC.** Falta repetirla en un celular de gama baja o con la CPU limitada 4× en Chrome DevTools.

## 5. Recomendaciones de mejora y escalabilidad

- Medir en banco la corriente real del nodo (ESP32 + SX1276 + DHT22) con un INA219 y ajustar la autonomía.
- Calibrar el umbral con una estación local o con un desplazamiento por vereda, estimado a partir de mediciones de campo, en vez de usar el reanálisis.
- Hacer la prueba SMS real con la cuenta gratuita de Twilio (números verificados) para medir la entrega y la latencia del operador.
- Hacer la prueba de accesibilidad con al menos 5 adultos mayores en el kiosco de la JAC.
- Escalar a 16 veredas: 16 nodos × 3 KB/día = 49 KB/día por el enlace LoRa, muy por debajo del ciclo de trabajo permitido (cada nodo transmite 96 × 0,247 s = 23,7 s/día, el 0,027 %).
