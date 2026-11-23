"""Gráficas SVG sin dependencias externas (solo biblioteca estándar)."""
import datetime as dt
from html import escape

W, H = 760, 420
ML, MR, MT, MB = 70, 20, 40, 60


def _lienzo(titulo_x, titulo_y, xmin, xmax, ymin, ymax, ticks_x, ticks_y, fmt_x=str):
    sx = lambda v: ML + (v - xmin) * (W - ML - MR) / ((xmax - xmin) or 1)
    sy = lambda v: H - MB - (v - ymin) * (H - MT - MB) / ((ymax - ymin) or 1)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'font-family="Arial, sans-serif" font-size="13">',
         f'<rect width="{W}" height="{H}" fill="#fff"/>']
    for t in ticks_y:
        s.append(f'<line x1="{ML}" x2="{W - MR}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="#e3e3e3"/>'
                 f'<text x="{ML - 8}" y="{sy(t) + 4:.1f}" text-anchor="end">{t:g}</text>')
    for t in ticks_x:
        s.append(f'<line x1="{sx(t):.1f}" x2="{sx(t):.1f}" y1="{H - MB}" y2="{H - MB + 5}" stroke="#333"/>'
                 f'<text x="{sx(t):.1f}" y="{H - MB + 20}" text-anchor="middle">{escape(fmt_x(t))}</text>')
    s.append(f'<line x1="{ML}" x2="{W - MR}" y1="{H - MB}" y2="{H - MB}" stroke="#333"/>'
             f'<line x1="{ML}" x2="{ML}" y1="{MT}" y2="{H - MB}" stroke="#333"/>'
             f'<text x="{(ML + W - MR) / 2}" y="{H - 15}" text-anchor="middle" font-size="15">{escape(titulo_x)}</text>'
             f'<text transform="translate(18 {(MT + H - MB) / 2}) rotate(-90)" text-anchor="middle" font-size="15">{escape(titulo_y)}</text>')
    return s, sx, sy


def _ticks(a, b, n=6):
    paso = (b - a) / n
    mag = 10 ** len(str(int(abs(paso)))) / 10 if paso >= 1 else 0.1
    for m in (1, 2, 2.5, 5, 10):
        if paso <= m * mag:
            paso = m * mag
            break
    t, out = (a // paso) * paso, []
    while t <= b + 1e-9:
        if t >= a - 1e-9:
            out.append(round(t, 6))
        t += paso
    return out


def dispersion(series, tx, ty, archivo, kpi=None, ymin=None, ymax=None):
    xs = [p[0] for _, pts, _ in series for p in pts]
    ys = [p[1] for _, pts, _ in series for p in pts]
    xmin, xmax = min(xs), max(xs)
    if xmin == xmax:
        xmin, xmax = xmin - 1, xmax + 1
    pad = (xmax - xmin) * 0.05
    xmin, xmax = xmin - pad, xmax + pad
    ymin = min(ys) if ymin is None else ymin
    ymax = max(ys) if ymax is None else ymax
    s, sx, sy = _lienzo(tx, ty, xmin, xmax, ymin, ymax,
                        _ticks(xmin, xmax), _ticks(ymin, ymax), lambda v: f"{v:g}")
    if kpi:
        v, et = kpi
        s.append(f'<line x1="{ML}" x2="{W - MR}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" '
                 f'stroke="#e67e22" stroke-width="2" stroke-dasharray="6 4"/>'
                 f'<text x="{W - MR - 4}" y="{sy(v) - 6:.1f}" text-anchor="end" fill="#e67e22">{escape(et)}</text>')
    for k, (nombre, pts, color) in enumerate(series):
        for x, y in pts:
            s.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5" fill="{color}" fill-opacity=".8"/>')
        s.append(f'<circle cx="{ML + 15}" cy="{MT - 18 + 0 * k}" r="0"/>'
                 f'<rect x="{ML + 10 + 190 * k}" y="{MT - 28}" width="12" height="12" fill="{color}"/>'
                 f'<text x="{ML + 28 + 190 * k}" y="{MT - 18}">{escape(nombre)}</text>')
    s.append("</svg>")
    archivo.write_text("\n".join(s), encoding="utf-8")


def serie_temperatura(muestras, archivo):
    t0, t1 = muestras[0][0], muestras[-1][0]
    temps = [m[1] for m in muestras]
    ymin, ymax = min(0, min(temps)) - 1, max(temps) + 1
    fmt = lambda t: dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=-5))).strftime("%d %b")
    ticks_x = [t0 + d * 86400 for d in range(0, 91, 15)]
    s, sx, sy = _lienzo("Fecha (2020)", "Temperatura (°C)", t0, t1, ymin, ymax,
                        ticks_x, _ticks(ymin, ymax), fmt)
    s.append(f'<rect x="{ML}" y="{sy(3):.1f}" width="{W - ML - MR}" height="{sy(ymin) - sy(3):.1f}" '
             f'fill="#cfe3ff" opacity=".6"/>'
             f'<text x="{ML + 6}" y="{sy(3) + 16:.1f}" fill="#1f5fbf">Zona de helada preventiva (≤ 3 °C)</text>')
    pts = " ".join(f"{sx(m[0]):.1f},{sy(m[1]):.1f}" for m in muestras[::2])
    s.append(f'<polyline points="{pts}" fill="none" stroke="#c0392b" stroke-width="0.8"/>')
    s.append(f'<text x="{ML}" y="{MT - 14}" font-size="15">Serie real ERA5 Firavitoba, muestreo de 15 min '
             f'({len(muestras)} muestras) · mínima {min(temps):.1f} °C</text></svg>')
    archivo.write_text("\n".join(s), encoding="utf-8")
