"""Gera static/painel.svg: o painel de instrumentos da tela de login.

Uso: python scripts/gerar_painel.py static/painel.svg
Velocímetro, horizonte artificial, altímetro, coordenador de curva,
indicador de proa e variômetro, desenhados com geometria simples.
"""
import math, sys
W, H = 720, 440
R = 92  # raio do instrumento
out = []
a = out.append

def pol(cx, cy, r, graus):
    t = math.radians(graus - 90)
    return cx + r * math.cos(t), cy + r * math.sin(t)

def ticks(cx, cy, ini, fim, n, maior_cada, r1=R-10):
    for i in range(n + 1):
        g = ini + (fim - ini) * i / n
        maior = i % maior_cada == 0
        x1, y1 = pol(cx, cy, r1, g)
        x2, y2 = pol(cx, cy, r1 - (12 if maior else 6), g)
        a(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#E8EDF3" stroke-width="{2.4 if maior else 1.2}" stroke-linecap="round"/>')

def bezel(cx, cy):
    a(f'<circle cx="{cx}" cy="{cy}" r="{R+12}" fill="#0A1626"/>')
    a(f'<circle cx="{cx}" cy="{cy}" r="{R+6}" fill="url(#aro)"/>')
    a(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="#0E1B2C"/>')
    for g in ():
        x, y = pol(cx, cy, R + 22, g)
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#24364F"/><line x1="{x-2.5:.1f}" y1="{y:.1f}" x2="{x+2.5:.1f}" y2="{y:.1f}" stroke="#0A1626" stroke-width="1.2"/>')

def ponteiro(cx, cy, g, comp, cor="#FFFFFF", larg=4):
    x, y = pol(cx, cy, comp, g)
    xb, yb = pol(cx, cy, 14, g + 180)
    a(f'<line x1="{xb:.1f}" y1="{yb:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{cor}" stroke-width="{larg}" stroke-linecap="round"/>')
    a(f'<circle cx="{cx}" cy="{cy}" r="7" fill="#24364F" stroke="#E8EDF3" stroke-width="1.5"/>')

def rotulo(cx, cy, texto, dy=34):
    a(f'<text x="{cx}" y="{cy+dy}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="11" fill="#9FB0C7" letter-spacing="1">{texto}</text>')

a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="Painel de instrumentos de um avião">')
a('<defs><linearGradient id="aro" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3A4E6B"/><stop offset="1" stop-color="#16243A"/></linearGradient>'
  '<linearGradient id="painel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1B2C44"/><stop offset="1" stop-color="#122036"/></linearGradient>'
  f'<clipPath id="ai"><circle cx="360" cy="118" r="{R}"/></clipPath></defs>')
a(f'<rect x="6" y="6" width="{W-12}" height="{H-12}" rx="28" fill="url(#painel)" stroke="#2A3D59" stroke-width="2"/>')

for sx, sy in ((26, 26), (W-26, 26), (26, H-26), (W-26, H-26)):
    a(f'<circle cx="{sx}" cy="{sy}" r="5" fill="#2A3D59"/><line x1="{sx-3}" y1="{sy}" x2="{sx+3}" y2="{sy}" stroke="#0A1626" stroke-width="1.5"/>')

centros = [(130, 118), (360, 118), (590, 118), (130, 322), (360, 322), (590, 322)]

# 1. Velocímetro (KT)
cx, cy = centros[0]; bezel(cx, cy)
a(f'<path d="M{pol(cx,cy,R-6,40)[0]:.1f},{pol(cx,cy,R-6,40)[1]:.1f} A{R-6},{R-6} 0 0 1 {pol(cx,cy,R-6,200)[0]:.1f},{pol(cx,cy,R-6,200)[1]:.1f}" fill="none" stroke="#2BB673" stroke-width="5"/>')
a(f'<path d="M{pol(cx,cy,R-6,200)[0]:.1f},{pol(cx,cy,R-6,200)[1]:.1f} A{R-6},{R-6} 0 0 1 {pol(cx,cy,R-6,250)[0]:.1f},{pol(cx,cy,R-6,250)[1]:.1f}" fill="none" stroke="#F2B705" stroke-width="5"/>')
ticks(cx, cy, 0, 300, 30, 5)
for i, v in enumerate(range(40, 200, 40)):
    x, y = pol(cx, cy, R - 34, 40 + i * 60)
    a(f'<text x="{x:.1f}" y="{y+5:.1f}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="14" font-weight="600" fill="#E8EDF3">{v}</text>')
rotulo(cx, cy, "KNOTS"); ponteiro(cx, cy, 128, R - 18)

# 2. Horizonte artificial
cx, cy = centros[1]; bezel(cx, cy)
a(f'<g clip-path="url(#ai)"><g transform="rotate(-12 {cx} {cy})">'
  f'<rect x="{cx-140}" y="{cy-140}" width="280" height="148" fill="#3D7FD1"/>'
  f'<rect x="{cx-140}" y="{cy+8}" width="280" height="140" fill="#8A5A2B"/>'
  f'<line x1="{cx-140}" y1="{cy+8}" x2="{cx+140}" y2="{cy+8}" stroke="#FFFFFF" stroke-width="2.5"/>')
for d in (-30, -15, 15, 30):
    w = 34 if abs(d) == 30 else 22
    a(f'<line x1="{cx-w}" y1="{cy+8+d}" x2="{cx+w}" y2="{cy+8+d}" stroke="#FFFFFF" stroke-width="2"/>')
a('</g></g>')
ticks(cx, cy, -60, 60, 4, 1, R - 4)
a(f'<path d="M{cx-58},{cy} h38 l12,12 l12,-12 h38" fill="none" stroke="#F2B705" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
a(f'<circle cx="{cx}" cy="{cy}" r="4" fill="#F2B705"/>')
a(f'<path d="M{cx},{cy-R+4} l-8,14 h16 z" fill="#F2B705"/>')

# 3. Altímetro
cx, cy = centros[2]; bezel(cx, cy)
ticks(cx, cy, 0, 360, 50, 5)
for i in range(10):
    x, y = pol(cx, cy, R - 34, i * 36)
    a(f'<text x="{x:.1f}" y="{y+5:.1f}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="15" font-weight="600" fill="#E8EDF3">{i}</text>')
a(f'<rect x="{cx-22}" y="{cy+20}" width="44" height="18" rx="3" fill="#0A1626" stroke="#3A4E6B"/>')
a(f'<text x="{cx}" y="{cy+33}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="11" fill="#E8EDF3">1013</text>')
rotulo(cx, cy, "ALT", -24); ponteiro(cx, cy, 75, R - 46, larg=6); ponteiro(cx, cy, 252, R - 16, larg=3)

# 4. Coordenador de curva
cx, cy = centros[3]; bezel(cx, cy)
for g in (-90, 90, -110, 110):
    x1, y1 = pol(cx, cy, R - 8, g); x2, y2 = pol(cx, cy, R - 26, g)
    a(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#E8EDF3" stroke-width="3" stroke-linecap="round"/>')
a(f'<g transform="rotate(-8 {cx} {cy})"><path d="M{cx-60},{cy} h46 a14,14 0 0 1 28,0 h46" fill="none" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round"/><line x1="{cx}" y1="{cy-14}" x2="{cx}" y2="{cy-30}" stroke="#FFFFFF" stroke-width="4" stroke-linecap="round"/></g>')
a(f'<rect x="{cx-44}" y="{cy+34}" width="88" height="20" rx="10" fill="#0A1626" stroke="#3A4E6B"/><circle cx="{cx-6}" cy="{cy+44}" r="7" fill="#E8EDF3"/>')
a(f'<text x="{cx-62}" y="{cy+20}" font-family="IBM Plex Mono, monospace" font-size="13" font-weight="600" fill="#E8EDF3">L</text><text x="{cx+54}" y="{cy+20}" font-family="IBM Plex Mono, monospace" font-size="13" font-weight="600" fill="#E8EDF3">R</text>')
rotulo(cx, cy, "TURN COORD", -30)

# 5. Indicador de proa
cx, cy = centros[4]; bezel(cx, cy)
a(f'<g transform="rotate(-30 {cx} {cy})">')
ticks(cx, cy, 0, 360, 72, 2)
for i, s in enumerate(["N", "3", "6", "E", "12", "15", "S", "21", "24", "W", "30", "33"]):
    x, y = pol(cx, cy, R - 32, i * 30)
    cor = "#F2B705" if s in "NESW" else "#E8EDF3"
    a(f'<text x="{x:.1f}" y="{y+5:.1f}" text-anchor="middle" transform="rotate({i*30} {x:.1f} {y:.1f})" font-family="IBM Plex Mono, monospace" font-size="14" font-weight="600" fill="{cor}">{s}</text>')
a('</g>')
a(f'<path d="M{cx},{cy-34} l-6,20 h4 v26 l-18,8 v6 l18,-4 v12 l-8,6 v4 l10,-3 l10,3 v-4 l-8,-6 v-12 l18,4 v-6 l-18,-8 v-26 h4 z" fill="#F2B705"/>')
a(f'<path d="M{cx},{cy-R+2} l-7,12 h14 z" fill="#F2B705"/>')

# 6. Variômetro
cx, cy = centros[5]; bezel(cx, cy)
ticks(cx, cy, -100, 100, 20, 5)
ticks(cx, cy, 80, 280, 20, 5)
for txt, g in (("0", -90), ("1", -50), ("2", -10), ("1", -130), ("2", -170)):
    x, y = pol(cx, cy, R - 34, g + 360 if g < 0 else g)
    a(f'<text x="{x:.1f}" y="{y+5:.1f}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="14" font-weight="600" fill="#E8EDF3">{txt}</text>')
rotulo(cx, cy, "VERT SPEED", 30); ponteiro(cx, cy, -70, R - 18)

a('</svg>')
open(sys.argv[1], 'w').write('\n'.join(out))
