"""
Генератор PDF-отчёта для Markowitz-US (investtools.pro).
Принимает данные от браузера (метрики, веса, готовые графики в base64),
собирает цветной документ через ReportLab. Графики рисует фронт (Chart.js),
сервер только верстает — поэтому не нужны matplotlib/numpy/pandas.
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
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_DIR = "/usr/share/fonts/truetype/dejavu"
try:
    pdfmetrics.registerFont(TTFont("DejaVu", _FONT_DIR + "/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", _FONT_DIR + "/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Mono", _FONT_DIR + "/DejaVuSansMono.ttf"))
    FONT = "DejaVu"
    FONT_B = "DejaVu-Bold"
    FONT_M = "DejaVu-Mono"
except Exception:
    FONT = "Helvetica"; FONT_B = "Helvetica-Bold"; FONT_M = "Courier"


report_router = APIRouter(prefix="/api/us", tags=["us-report"])

# ---- Фирменная палитра ----
GREEN      = colors.HexColor("#2D5A3D")
GREEN_LT   = colors.HexColor("#EDF7F1")
GOLD       = colors.HexColor("#C79A3A")
TEXT       = colors.HexColor("#1A1A18")
TEXT2      = colors.HexColor("#6B6A65")
BORDER     = colors.HexColor("#E5E4DF")
SURFACE2   = colors.HexColor("#F3F2EE")
RED        = colors.HexColor("#B03030")

# ---- Модель входных данных ----
class Metric(BaseModel):
    label: str
    ret: float          # доходность %
    vol: float          # волатильность %
    dd: float           # макс. просадка %
    sharpe: float
    beta: Optional[float] = None

class Weight(BaseModel):
    ticker: str
    weight: float       # доля % (>0, нули фронт не шлёт)

class CorrPair(BaseModel):
    a: str
    b: str
    corr: float

class ReportPayload(BaseModel):
    market: str = "us"                  # "us" | "ru"
    benchmark: str = "SPY"              # SPY | IMOEX
    portfolio_value: Optional[float] = None
    your: Metric                       # метрики "Вашего портфеля"
    optimals: List[Metric]             # Max Sharpe / Min Vol / Min DD / Equal
    weights: List[Weight]              # состав Вашего портфеля, без нулей
    chart_frontier: Optional[str] = None   # base64 PNG эффективной границы
    chart_cumulative: Optional[str] = None # base64 PNG кумулятивной доходности
    chart_drawdown: Optional[str] = None   # base64 PNG просадки
    chart_corr: Optional[str] = None       # base64 PNG матрицы корреляций
    corr_avg: Optional[float] = None
    corr_top: List[CorrPair] = []          # самые связанные пары
    corr_low: List[CorrPair] = []          # самые независимые пары


def _img_from_b64(b64: str, max_w_mm: float):
    """base64 data-URL -> reportlab Image, вписанный по ширине."""
    if not b64:
        return None
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    bio = io.BytesIO(raw)
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(bio)
    iw, ih = ir.getSize()
    w = max_w_mm * mm
    h = w * ih / iw
    bio.seek(0)
    return Image(bio, width=w, height=h)


def _styles():
    ss = getSampleStyleSheet()
    styles = {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName=FONT_B,
                             fontSize=18, textColor=GREEN, spaceAfter=2, alignment=TA_LEFT),
        "sub": ParagraphStyle("sub", parent=ss["Normal"], fontName=FONT,
                              fontSize=9, textColor=TEXT2, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName=FONT_B,
                             fontSize=11, textColor=GREEN, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontName=FONT,
                               fontSize=9, textColor=TEXT, leading=13),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontName=FONT,
                                fontSize=8, textColor=TEXT2, leading=11),
    }
    return styles


def build_pdf(p: ReportPayload) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=16*mm, rightMargin=16*mm,
                            topMargin=14*mm, bottomMargin=14*mm)
    S = _styles()
    story = []
    CONTENT_W = 178  # мм рабочей ширины

    # ---- ШАПКА ----
    is_ru = (p.market == "ru")
    title = "Оптимизация портфеля · Россия" if is_ru else "Оптимизация портфеля · США"
    exchange = "Московская биржа" if is_ru else "NYSE / NASDAQ"
    cur = "₽" if is_ru else "$"
    story.append(Paragraph(title, S["h1"]))
    dt = datetime.now().strftime("%d.%m.%Y")
    if p.portfolio_value:
        val = f" · Стоимость портфеля {p.portfolio_value:,.0f} {cur}".replace(",", " ")
    else:
        val = ""
    story.append(Paragraph(f"investtools.pro · Markowitz · {exchange} · {dt}{val}", S["sub"]))

    # ---- ЭФФЕКТИВНАЯ ГРАНИЦА ----
    story.append(Paragraph("Эффективная граница (риск vs доходность)", S["h2"]))
    img = _img_from_b64(p.chart_frontier, CONTENT_W)
    if img:
        story.append(img)
    story.append(Spacer(1, 4*mm))

    # ---- ПАРАМЕТРЫ ВАШЕГО ПОРТФЕЛЯ ----
    story.append(Paragraph("Ваш портфель", S["h2"]))
    y = p.your
    beta_txt = f"{y.beta:.2f}" if y.beta is not None else "—"
    param_rows = [
        ["Доходность", "Волатильность", "Макс. просадка", "Sharpe", f"β к {p.benchmark}"],
        [f"{y.ret:.1f}%", f"{y.vol:.1f}%", f"{y.dd:.1f}%", f"{y.sharpe:.2f}", beta_txt],
    ]
    pt = Table(param_rows, colWidths=[CONTENT_W/5*mm]*5)
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), GREEN),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), FONT_B),
        ("FONTNAME", (0,1), (-1,1), FONT_B),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("TEXTCOLOR", (0,1), (-1,1), GREEN),
        ("BACKGROUND", (0,1), (-1,1), GREEN_LT),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("GRID", (0,0), (-1,-1), 0.5, colors.white),
    ]))
    story.append(pt)

    # ---- СРАВНЕНИЕ С ОПТИМАЛЬНЫМИ ----
    story.append(Paragraph("Сравнение с оптимальными портфелями", S["h2"]))
    head = ["Стратегия", "Доходность", "Волатильность", "Просадка", "Sharpe"]
    rows = [head]
    all_metrics = p.optimals + [y]
    for m in all_metrics:
        rows.append([m.label, f"{m.ret:.1f}%", f"{m.vol:.1f}%", f"{m.dd:.1f}%", f"{m.sharpe:.2f}"])
    ct = Table(rows, colWidths=[46*mm] + [ (CONTENT_W-46)/4*mm ]*4)
    style = [
        ("BACKGROUND", (0,0), (-1,0), GREEN),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), FONT_B),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LINEBELOW", (0,0), (-1,0), 1, GREEN),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, SURFACE2]),
    ]
    # выделить строку "Ваш" (последняя) золотом
    style.append(("BACKGROUND", (0,len(rows)-1), (-1,len(rows)-1), GREEN_LT))
    style.append(("FONTNAME", (0,len(rows)-1), (-1,len(rows)-1), FONT_B))
    style.append(("TEXTCOLOR", (0,len(rows)-1), (-1,len(rows)-1), GREEN))
    ct.setStyle(TableStyle(style))
    story.append(ct)

    # ---- СОСТАВ ПОРТФЕЛЯ (без нулей) ----
    story.append(Paragraph("Состав портфеля", S["h2"]))
    ws = sorted(p.weights, key=lambda w: -w.weight)
    # в 3 колонки для компактности
    per_col = (len(ws) + 2) // 3
    cols = [ws[i:i+per_col] for i in range(0, len(ws), per_col)]
    max_rows = max((len(c) for c in cols), default=0)
    grid = []
    for r in range(max_rows):
        row = []
        for c in cols:
            if r < len(c):
                row.append(c[r].ticker)
                row.append(f"{c[r].weight:.1f}%")
            else:
                row.append("")
                row.append("")
        grid.append(row)
    if grid:
        ncols = len(cols)*2
        colw = CONTENT_W/ncols*mm
        wt = Table(grid, colWidths=[colw]*ncols)
        wst = [
            ("FONTNAME", (0,0), (-1,-1), FONT),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("TOPPADDING", (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]
        for ci in range(len(cols)):
            wst.append(("FONTNAME", (ci*2,0), (ci*2,-1), FONT_B))
            wst.append(("ALIGN", (ci*2+1,0), (ci*2+1,-1), "RIGHT"))
            wst.append(("TEXTCOLOR", (ci*2+1,0), (ci*2+1,-1), GREEN))
        wt.setStyle(TableStyle(wst))
        story.append(wt)

    # ---- ГРАФИКИ ДОХОДНОСТИ И ПРОСАДКИ ----
    if p.chart_cumulative or p.chart_drawdown:
        story.append(PageBreak())
        if p.chart_cumulative:
            story.append(Paragraph("Кумулятивная доходность", S["h2"]))
            im = _img_from_b64(p.chart_cumulative, CONTENT_W)
            if im: story.append(im)
            story.append(Spacer(1, 4*mm))
        if p.chart_drawdown:
            story.append(Paragraph("Просадка от пика", S["h2"]))
            im = _img_from_b64(p.chart_drawdown, CONTENT_W)
            if im: story.append(im)

    # ---- КОРРЕЛЯЦИИ ----
    if p.chart_corr or p.corr_top:
        story.append(PageBreak())
        story.append(Paragraph("Корреляции бумаг портфеля", S["h2"]))
        if p.corr_avg is not None:
            lvl = ("низкая — хорошая диверсификация" if p.corr_avg < 0.3
                   else "умеренная" if p.corr_avg < 0.6
                   else "высокая — бумаги движутся похоже")
            story.append(Paragraph(f"Средняя корреляция портфеля: <b>{p.corr_avg:.2f}</b> ({lvl}).", S["body"]))
            story.append(Spacer(1, 3*mm))
        if p.chart_corr:
            im = _img_from_b64(p.chart_corr, min(CONTENT_W, 150))
            if im: story.append(im)
            story.append(Spacer(1, 4*mm))
        if p.corr_top:
            story.append(Paragraph("Самые связанные пары (риск дублирования):", S["body"]))
            for c in p.corr_top[:5]:
                story.append(Paragraph(f"• {c.a} ↔ {c.b}: {c.corr:.2f}", S["small"]))
            story.append(Spacer(1, 2*mm))
        if p.corr_low:
            story.append(Paragraph("Самые независимые пары (диверсификация):", S["body"]))
            for c in p.corr_low[:5]:
                story.append(Paragraph(f"• {c.a} ↔ {c.b}: {c.corr:.2f}", S["small"]))

    doc.build(story)
    buf.seek(0)
    return buf


@report_router.post("/report")
async def make_report(payload: ReportPayload):
    try:
        pdf = build_pdf(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF build error: {e}")
    fname = f"portfolio_us_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
