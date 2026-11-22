"""Gera o fundo do painel e o tema JSON do Power BI.

Versão "terminal financeiro escuro" (padrão):
    python gerar_fundo.py           -> fundo_terminal_1920.png e tema_bcb_terminal.json
Versão clara antiga (v2), para reprodução:
    python gerar_fundo.py --claro   -> fundo_painel_1920.png e tema_credito_pix.json

O menu lateral (degradê #0B1F3A -> #14365D, arcos e divisórias) é idêntico nas duas versões.
"""
import json
import sys
from PIL import Image, ImageDraw

CLARO = "--claro" in sys.argv

S = 1.5                    # escala: 1280x720 * 1,5 = 1920x1080, o tamanho exato da página do Power BI
W, H = int(1280 * S), int(720 * S)
SIDEBAR = int(232 * S)
NAVY_TOP, NAVY_BOTTOM = (11, 31, 58), (20, 54, 93)
CONTEUDO = (243, 246, 251) if CLARO else (11, 20, 36)     # #F3F6FB (claro) | #0B1424 (escuro)
AZUL, TURQUESA = (30, 94, 255), (0, 184, 169)
AA = 4                     # superamostragem do logotipo (desenha 4x maior e reduz)


def gradiente_vertical(w, h, c1, c2):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(c1, c2)))
    return img


def gradiente_diagonal(w, h, c1, c2):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for x in range(w):
        for y in range(h):
            t = (x + y) / (w + h - 2)
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))
    return img


def logotipo_tendencia(lado):
    """Logotipo da v2: quadrado em degradê com uma linha de tendência."""
    marca = gradiente_diagonal(lado, lado, AZUL, TURQUESA)
    d = ImageDraw.Draw(marca)
    u = lado / 40
    pts = [(9 * u, 29 * u), (17 * u, 21 * u), (23 * u, 25 * u), (31 * u, 13 * u)]
    d.line(pts, fill="white", width=max(1, round(3 * u)), joint="curve")
    r = 3 * u
    d.ellipse([pts[-1][0] - r, pts[-1][1] - r, pts[-1][0] + r, pts[-1][1] + r], fill="white")
    return marca


def logotipo_banco(lado):
    """Prédio de banco clássico, genérico: frontão, barra, 4 colunas e base em degrau.

    Coordenadas numa grade de 40 x 40 unidades (o tamanho do logotipo na escala 1280).
    """
    marca = gradiente_diagonal(lado, lado, AZUL, TURQUESA)
    d = ImageDraw.Draw(marca)
    u = lado / 40
    br = "white"
    # frontão triangular
    d.polygon([(8.5 * u, 15 * u), (20 * u, 8 * u), (31.5 * u, 15 * u)], fill=br)
    # barra horizontal (arquitrave)
    d.rectangle([9.5 * u, 16.2 * u, 30.5 * u, 18.0 * u], fill=br)
    # 4 colunas
    larg = 2.6
    for cx in (12.6, 17.53, 22.47, 27.4):
        d.rectangle([(cx - larg / 2) * u, 19.4 * u, (cx + larg / 2) * u, 27.4 * u], fill=br)
    # base em degrau
    d.rectangle([9.5 * u, 28.6 * u, 30.5 * u, 30.2 * u], fill=br)
    d.rectangle([7.5 * u, 31.2 * u, 32.5 * u, 33.0 * u], fill=br)
    return marca


fundo = Image.new("RGB", (W, H), CONTEUDO)

# menu lateral com gradiente e arcos decorativos (igual nas duas versões)
lateral = gradiente_vertical(SIDEBAR, H, NAVY_TOP, NAVY_BOTTOM)
deco = Image.new("L", (SIDEBAR, H), 0)
dd = ImageDraw.Draw(deco)
dd.ellipse([-SIDEBAR * 0.6, H * 0.62, SIDEBAR * 1.3, H * 1.35], outline=40, width=int(3 * S))
dd.ellipse([-SIDEBAR * 0.3, H * 0.70, SIDEBAR * 1.5, H * 1.45], outline=25, width=int(2 * S))
lateral.paste(Image.new("RGB", lateral.size, (120, 170, 255)), (0, 0), deco)
fundo.paste(lateral, (0, 0))

d = ImageDraw.Draw(fundo)

# logotipo: 40 x 40 em x=20, y=22 (escala 1280), desenhado em 4x e reduzido com LANCZOS
LX, LY, LS = int(20 * S), int(22 * S), int(40 * S)
grande = LS * AA
marca = (logotipo_tendencia if CLARO else logotipo_banco)(grande)
mascara = Image.new("L", (grande, grande), 0)
ImageDraw.Draw(mascara).rounded_rectangle([0, 0, grande - 1, grande - 1], radius=10 * S * AA, fill=255)
marca = marca.resize((LS, LS), Image.LANCZOS)
mascara = mascara.resize((LS, LS), Image.LANCZOS)
fundo.paste(marca, (LX, LY), mascara)

# linhas divisórias do menu
for y in (82, 300, 640):
    d.line([(int(20 * S), int(y * S)), (SIDEBAR - int(20 * S), int(y * S))], fill=(44, 72, 110), width=max(1, int(1 * S)))

# faixa de destaque ao lado do título, em degradê azul -> turquesa
barra = gradiente_diagonal(int(4 * S), int(34 * S), AZUL, TURQUESA)
fundo.paste(barra, (SIDEBAR + int(24 * S), int(22 * S)))

fundo.save("fundo_painel_1920.png" if CLARO else "fundo_terminal_1920.png", optimize=True)


def cor(c):
    return {"solid": {"color": c}}


if CLARO:
    with open("tema_credito_pix.json", encoding="utf-8") as f:
        tema = json.load(f)          # o tema claro da v2 fica como está
    sys.exit(0)

# ---------- tema "terminal financeiro escuro" ----------
FUNDO, CARTAO, BORDA, GRADE = "#0B1424", "#111C30", "#22314A", "#1A2740"
T1, T2, T3 = "#FFFFFF", "#B6C2D6", "#7F8DA6"
NAVY, LINHA_ALT, DATA_SLICER = "#14365D", "#0F182A", "#1B3F6B"

tema = {
    "name": "BCB terminal escuro",
    "dataColors": ["#4C82FF", "#00C2B2", "#F6A609", "#F85149", "#9B7BFF",
                   "#5DCAA5", "#FF7A45", "#B6C2D6", "#7F8DA6", "#22314A"],
    "background": CARTAO,
    "foreground": T1,
    "tableAccent": "#4C82FF",
    "good": "#5DCAA5", "neutral": "#F6A609", "bad": "#F85149",
    "maximum": "#4C82FF", "center": "#7F8DA6", "minimum": "#0B1424",
    "textClasses": {
        "callout": {"fontSize": 26, "fontFace": "Segoe UI Semibold", "color": T1},
        "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": T1},
        "header": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": T1},
        "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": T2},
        "smallLabel": {"fontSize": 9, "fontFace": "Segoe UI", "color": T3},
        "largeTitle": {"fontSize": 14, "fontFace": "Segoe UI Semibold", "color": T1}
    },
    "visualStyles": {
        "*": {"*": {
            "background": [{"show": True, "color": cor(CARTAO), "transparency": 0}],
            "border": [{"show": True, "color": cor(BORDA), "radius": 10, "width": 1}],
            "dropShadow": [{"show": False}],
            "visualHeader": [{"show": False}],
            "padding": [{"top": 12, "bottom": 10, "left": 14, "right": 14}],
            "title": [{"show": True, "fontColor": cor(T1), "fontSize": 12, "fontFamily": "Segoe UI Semibold"}],
            "subTitle": [{"fontColor": cor(T2), "fontSize": 10}],
            "divider": [{"color": cor(BORDA)}],
            "valueAxis": [{"labelColor": cor(T3), "titleColor": cor(T2), "gridlineColor": cor(GRADE),
                           "gridlineShow": True}],
            "categoryAxis": [{"labelColor": cor(T3), "titleColor": cor(T2), "gridlineColor": cor(GRADE)}],
            "legend": [{"labelColor": cor(T2), "titleColor": cor(T2)}],
            "labels": [{"color": cor(T2)}],
            "categoryLabels": [{"color": cor(T2)}],
            "trend": [{"lineColor": cor(T2)}],
            "plotArea": [{"transparency": 100}]
        }},
        "page": {"*": {
            "outspace": [{"color": cor(FUNDO)}],
            "background": [{"color": cor(FUNDO), "transparency": 100}]
        }},
        "textbox": {"*": {
            "background": [{"show": False}],
            "border": [{"show": False}]
        }},
        "pageNavigator": {"*": {
            "background": [{"show": False}],
            "border": [{"show": False}]
        }},
        "actionButton": {"*": {
            "background": [{"show": False}],
            "border": [{"show": False}]
        }},
        "slicer": {"*": {
            "background": [{"show": False}],
            "border": [{"show": False}],
            "items": [{"fontColor": cor(T1), "fontSize": 10, "background": cor(NAVY)}],
            "header": [{"fontColor": cor("#9FB3D1"), "fontSize": 9, "fontFamily": "Segoe UI Semibold"}],
            "date": [{"fontColor": cor(T1), "background": cor(DATA_SLICER)}],
            "numericInputStyle": [{"fontColor": cor(T1), "background": cor(DATA_SLICER)}],
            "slider": [{"color": cor("#4C82FF")}]
        }},
        "tableEx": {"*": {
            "grid": [{"gridVerticalColor": cor(BORDA), "gridHorizontalColor": cor(BORDA),
                      "outlineColor": cor(BORDA), "rowPadding": 4}],
            "columnHeaders": [{"fontColor": cor(T1), "backColor": cor(NAVY)}],
            "values": [{"fontColorPrimary": cor(T2), "backColorPrimary": cor(CARTAO),
                        "fontColorSecondary": cor(T2), "backColorSecondary": cor(LINHA_ALT)}],
            "total": [{"fontColor": cor(T1), "backColor": cor(NAVY)}]
        }},
        "pivotTable": {"*": {
            "grid": [{"gridVerticalColor": cor(BORDA), "gridHorizontalColor": cor(BORDA),
                      "outlineColor": cor(BORDA), "rowPadding": 4}],
            "columnHeaders": [{"fontColor": cor(T1), "backColor": cor(NAVY)}],
            "rowHeaders": [{"fontColor": cor(T2), "backColor": cor(CARTAO)}],
            "values": [{"fontColorPrimary": cor(T2), "backColorPrimary": cor(CARTAO),
                        "fontColorSecondary": cor(T2), "backColorSecondary": cor(LINHA_ALT)}],
            "subTotals": [{"fontColor": cor(T1), "backColor": cor(NAVY)}],
            "total": [{"fontColor": cor(T1), "backColor": cor(NAVY)}]
        }},
        "cardVisual": {"*": {
            "background": [{"show": True, "color": cor(CARTAO), "transparency": 0}],
            "border": [{"show": True, "color": cor(BORDA), "radius": 10, "width": 1}],
            "label": [{"fontColor": cor(T2), "fontSize": 10}],
            "value": [{"fontColor": cor(T1), "fontSize": 26}],
            "referenceLabelTitle": [{"fontColor": cor(T3), "fontSize": 9}],
            "referenceLabelValue": [{"fontColor": cor(T2), "fontSize": 10}],
            "divider": [{"color": cor(BORDA)}]
        }},
        "card": {"*": {
            "labels": [{"color": cor(T1), "fontSize": 26}],
            "categoryLabels": [{"color": cor(T2), "fontSize": 10}]
        }},
        "multiRowCard": {"*": {
            "dataLabels": [{"color": cor(T1)}],
            "categoryLabels": [{"color": cor(T2)}],
            "cardTitle": [{"color": cor(T1)}]
        }}
    }
}
with open("tema_bcb_terminal.json", "w", encoding="utf-8") as f:
    json.dump(tema, f, ensure_ascii=False, indent=2)
print("ok")
