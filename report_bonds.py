"""
Генератор PDF-отчёта для портфеля облигаций (investtools.pro).
Данные приходят от браузера (метрики, состав, стресс-тест, график купонов).
Тот же стиль/шрифты, что у Markowitz-отчёта.
"""
import io
import base64
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_DIR = "/usr/share/fonts/truetype/dejavu"
try:
    pdfmetrics.registerFont(TTFont("DejaVu", _FONT_DIR + "/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", _FONT_DIR + "/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Mono", _FONT_DIR + "/DejaVuSansMono.ttf"))
    FONT, FONT_B, FONT_M = "DejaVu", "DejaVu-Bold", "DejaVu-Mono"
except Exception:
    FONT, FONT_B, FONT_M = "Helvetica", "Helvetica-Bold", "Courier"

bonds_router = APIRouter(prefix="/api/bonds", tags=["bonds-report"])

GREEN    = colors.HexColor("#2D5A3D")
GREEN_LT = colors.HexColor("#EDF7F1")
BLUE     = colors.HexColor("#2B6CB0")
TEXT     = colors.HexColor("#1A1A18")
TEXT2    = colors.HexColor("#6B6A65")
BORDER   = colors.HexColor("#E5E4DF")
SURFACE2 = colors.HexColor("#F3F2EE")
RED      = colors.HexColor("#B03030")

class Metric(BaseModel):
    label: str
    value: str
    sub: Optional[str] = ""

class Holding(BaseModel):
    isin: str
    name: str
    weight: float          # доля %
    ctype: str             # тип купона: фикс/флоатер/дисконт/...
    ytm: Optional[float] = None
    duration: Optional[float] = None
    ccy: Optional[str] = "RUB"

class StressPoint(BaseModel):
    shift: int             # сдвиг ставки, бп
    change: float          # Δ стоимости, %

class BondReport(BaseModel):
    portfolio_value: Optional[float] = None
    ytm: Optional[float] = None
    duration: Optional[float] = None
    metrics: List[Metric] = []          # плашки (стоимость/купон/дох/дюр по ₽ и $)
    holdings: List[Holding] = []        # состав
    stress: List[StressPoint] = []      # стресс-тест
    chart_coupons: Optional[str] = None # база64 PNG купонного календаря


def _img(b64, max_w_mm):
    if not b64: return None
    if b64.startswith("data:"): b64 = b64.split(",",1)[1]
    raw = base64.b64decode(b64); bio = io.BytesIO(raw)
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(bio); iw, ih = ir.getSize()
    w = max_w_mm*mm; h = w*ih/iw; bio.seek(0)
    return Image(bio, width=w, height=h)


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName=FONT_B, fontSize=18,
                             textColor=GREEN, spaceAfter=2, alignment=TA_LEFT),
        "sub": ParagraphStyle("sub", parent=ss["Normal"], fontName=FONT, fontSize=9,
                              textColor=TEXT2, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName=FONT_B, fontSize=11,
                             textColor=GREEN, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontName=FONT, fontSize=9,
                               textColor=TEXT, leading=13),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontName=FONT, fontSize=8,
                                textColor=TEXT2, leading=11),
    }


def build_pdf(p: BondReport) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16*mm, rightMargin=16*mm,
                            topMargin=14*mm, bottomMargin=14*mm)
    S = _styles(); story = []; CW = 178

    # ШАПКА
    story.append(Paragraph("Портфель облигаций", S["h1"]))
    dt = datetime.now().strftime("%d.%m.%Y")
    extra = []
    if p.portfolio_value: extra.append(f"Стоимость {p.portfolio_value:,.0f} \u20bd".replace(",", " "))
    if p.ytm is not None: extra.append(f"YTM {p.ytm:.2f}%")
    if p.duration is not None: extra.append(f"дюрация {p.duration:.2f} лет")
    tail = (" \u00b7 " + " \u00b7 ".join(extra)) if extra else ""
    story.append(Paragraph(f"investtools.pro \u00b7 MOEX ISS API \u00b7 {dt}{tail}", S["sub"]))

    # ПЛАШКИ МЕТРИК (по 3 в ряд)
    if p.metrics:
        story.append(Paragraph("Параметры портфеля", S["h2"]))
        rows = []
        cells = []
        for mtr in p.metrics:
            cell = f"<b>{mtr.value}</b><br/><font size=7 color='#6B6A65'>{mtr.label}"
            if mtr.sub: cell += f" · {mtr.sub}"
            cell += "</font>"
            cells.append(Paragraph(cell, S["body"]))
        # разбить по 3 в ряд
        for i in range(0, len(cells), 3):
            row = cells[i:i+3]
            while len(row) < 3: row.append("")
            rows.append(row)
        mt = Table(rows, colWidths=[CW/3*mm]*3)
        mt.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),GREEN_LT),
            ("BOX",(0,0),(-1,-1),0.5,BORDER),
            ("INNERGRID",(0,0),(-1,-1),0.5,colors.white),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
            ("LEFTPADDING",(0,0),(-1,-1),8),
        ]))
        story.append(mt)

    # СОСТАВ ПОРТФЕЛЯ
    if p.holdings:
        story.append(Paragraph("Состав портфеля", S["h2"]))
        head = ["Бумага", "Доля", "Тип", "YTM", "Дюрация"]
        rows = [head]
        for h in sorted(p.holdings, key=lambda x:-x.weight):
            rows.append([
                h.name or h.isin,
                f"{h.weight:.1f}%",
                h.ctype,
                f"{h.ytm:.1f}%" if h.ytm is not None else "—",
                f"{h.duration:.2f}" if h.duration is not None else "—",
            ])
        t = Table(rows, colWidths=[CW*0.40*mm, CW*0.12*mm, CW*0.20*mm, CW*0.14*mm, CW*0.14*mm])
        style = [
            ("BACKGROUND",(0,0),(-1,0),GREEN),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),FONT_B),
            ("FONTNAME",(0,1),(-1,-1),FONT),
            ("FONTSIZE",(0,0),(-1,-1),8.5),
            ("ALIGN",(1,0),(-1,-1),"RIGHT"),
            ("ALIGN",(0,0),(0,-1),"LEFT"),
            ("ALIGN",(2,0),(2,-1),"CENTER"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,SURFACE2]),
            ("LINEBELOW",(0,0),(-1,0),1,GREEN),
        ]
        t.setStyle(TableStyle(style))
        story.append(t)

    # СТР 2: КУПОННЫЙ КАЛЕНДАРЬ + СТРЕСС
    if p.chart_coupons or p.stress:
        story.append(PageBreak())
        if p.chart_coupons:
            story.append(Paragraph("Купонный календарь (ближайшие 12 месяцев)", S["h2"]))
            im = _img(p.chart_coupons, CW)
            if im: story.append(im)
            story.append(Spacer(1, 6*mm))
        if p.stress:
            story.append(Paragraph("Стресс-тест: изменение стоимости при сдвиге ключевой ставки", S["h2"]))
            story.append(Paragraph("Оценка через дюрацию и выпуклость. Рост ставки снижает стоимость, падение — повышает.", S["small"]))
            story.append(Spacer(1, 2*mm))
            sp = sorted(p.stress, key=lambda x:x.shift)
            head = [""] + [f"{'+' if s.shift>0 else ''}{s.shift} бп" for s in sp]
            vals = ["Δ стоимости"] + [f"{s.change:+.1f}%" for s in sp]
            st = Table([head, vals], colWidths=[30*mm] + [(CW-30)/len(sp)*mm]*len(sp))
            sstyle = [
                ("BACKGROUND",(0,0),(-1,0),GREEN),
                ("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("FONTNAME",(0,0),(-1,0),FONT_B),
                ("FONTNAME",(0,1),(0,1),FONT_B),
                ("FONTNAME",(1,1),(-1,1),FONT_M),
                ("FONTSIZE",(0,0),(-1,-1),8),
                ("ALIGN",(1,0),(-1,-1),"CENTER"),
                ("ALIGN",(0,0),(0,-1),"LEFT"),
                ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
                ("GRID",(0,0),(-1,-1),0.5,BORDER),
            ]
            # цвет значений: рост стоимости зелёным, падение красным
            for ci, s in enumerate(sp, start=1):
                col = GREEN if s.change > 0 else (RED if s.change < 0 else TEXT)
                sstyle.append(("TEXTCOLOR",(ci,1),(ci,1),col))
            st.setStyle(TableStyle(sstyle))
            story.append(st)

    doc.build(story)
    buf.seek(0)
    return buf


@bonds_router.post("/report")
async def make_report(payload: BondReport):
    try:
        pdf = build_pdf(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF build error: {e}")
    fname = f"bond_portfolio_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
