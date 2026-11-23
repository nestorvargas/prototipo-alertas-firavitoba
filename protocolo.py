"""Trama de 32 bytes del enlace de campo (estación -> servidor comunitario).

Corresponde a la variable de diseño de la Etapa 3: 96 registros/día x 32 B
= 3,07 KB/día.

Estructura (big-endian):
  B   versión
  H   id del nodo
  I   número de secuencia
  I   marca de tiempo (epoch, s)
  h   temperatura (centésimas de °C)
  H   humedad relativa (centésimas de %)
  H   lluvia (décimas de mm)
  H   tensión de batería (mV)
  B   banderas (bit0 = reintento)
  10x relleno reservado (futuros sensores)
  H   CRC-16/CCITT de los 30 bytes anteriores
"""
import struct

FORMATO = ">BHIIhHHHB10x"
TAM_DATOS = struct.calcsize(FORMATO)  # 30
TAM_TRAMA = TAM_DATOS + 2             # 32
VERSION = 1
ACK = b"ACK"


def crc16_ccitt(datos: bytes, crc: int = 0xFFFF) -> int:
    for b in datos:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def empaquetar(nodo, seq, ts, temp_c, hum_pct, lluvia_mm, bat_mv, banderas=0):
    cuerpo = struct.pack(
        FORMATO, VERSION, nodo, seq, int(ts),
        round(temp_c * 100), round(hum_pct * 100), round(lluvia_mm * 10),
        int(bat_mv), banderas,
    )
    return cuerpo + struct.pack(">H", crc16_ccitt(cuerpo))


def desempaquetar(trama: bytes):
    """Devuelve un dict o lanza ValueError si la trama es inválida."""
    if len(trama) != TAM_TRAMA:
        raise ValueError(f"longitud {len(trama)} != {TAM_TRAMA}")
    cuerpo, (crc,) = trama[:TAM_DATOS], struct.unpack(">H", trama[TAM_DATOS:])
    if crc16_ccitt(cuerpo) != crc:
        raise ValueError("CRC inválido")
    v, nodo, seq, ts, t, h, ll, bat, fl = struct.unpack(FORMATO, cuerpo)
    return {"version": v, "nodo": nodo, "seq": seq, "ts": ts,
            "temp_c": t / 100, "hum_pct": h / 100, "lluvia_mm": ll / 10,
            "bat_mv": bat, "reintento": bool(fl & 1)}


def tiempo_en_aire_lora(payload=TAM_TRAMA, sf=9, bw=125_000, cr=1,
                        preambulo=8, cabecera_explicita=True, crc=True):
    """Tiempo en el aire (s) de una trama LoRa, fórmula de la nota AN1200.13
    de Semtech. cr=1 equivale a 4/5."""
    tsym = (2 ** sf) / bw
    de = 1 if tsym > 0.016 else 0  # optimización para baja tasa
    ih = 0 if cabecera_explicita else 1
    num = 8 * payload - 4 * sf + 28 + 16 * int(crc) - 20 * ih
    n_payload = 8 + max(-(-num // (4 * (sf - 2 * de))) * (cr + 4), 0)
    return (preambulo + 4.25) * tsym + n_payload * tsym
