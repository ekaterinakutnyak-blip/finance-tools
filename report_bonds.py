"""
PDF-отчёт по портфелю облигаций (investtools.pro) — полный, альбомный.
Переносит весь экран: метрики, структуру, позиции, кредитный риск, стресс, купоны.
Водяной знак investtools.pro на каждой странице.
"""
import io, base64
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image, PageBreak)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FD = "/usr/share/fonts/truetype/dejavu"
try:
    pdfmetrics.registerFont(TTFont("DejaVu", _FD+"/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", _FD+"/DejaVuSans-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVu-Mono", _FD+"/DejaVuSansMono.ttf"))
    FONT, FONT_B, FONT_M = "DejaVu", "DejaVu-Bold", "DejaVu-Mono"
except Exception:
    FONT, FONT_B, FONT_M = "Helvetica", "Helvetica-Bold", "Courier"

bonds_router = APIRouter(prefix="/api/bonds", tags=["bonds-report"])

GREEN    = colors.HexColor("#2D5A3D")
GREEN2   = colors.HexColor("#2D7A4F")
GREEN_LT = colors.HexColor("#EDF7F1")
BLUE     = colors.HexColor("#2B6CB0")
BLUE_LT  = colors.HexColor("#EAF2FB")
RED      = colors.HexColor("#B03030")
RED_LT   = colors.HexColor("#FDF0F0")
TEXT     = colors.HexColor("#1A1A18")
TEXT2    = colors.HexColor("#6B6A65")
TEXT3    = colors.HexColor("#9C9B96")
BORDER   = colors.HexColor("#E5E4DF")
SURF2    = colors.HexColor("#F3F2EE")
GOLD_LT  = colors.HexColor("#FEF9E7")

# ---------- Модели ----------
class Metric(BaseModel):
    label: str; value: str; sub: Optional[str] = ""; kind: Optional[str] = "green"  # green|blue

class StructRow(BaseModel):
    label: str; pct: float; amount: str

class Position(BaseModel):
    name: str; ccy: str; ctype: str; qty: float; weight: float
    value: str; ytm: Optional[float]=None; coupon_year: str=""
    duration: Optional[float]=None; convexity: Optional[float]=None
    price: Optional[float]=None; maturity: str=""

class StressCell(BaseModel):
    shift: int; pct: float; rub: str

class CreditSummary(BaseModel):
    g_spread: Optional[str]=None; z_spread: Optional[str]=None; pd_year: Optional[str]=None
    note: Optional[str]=""

class CreditZone(BaseModel):
    label: str; pct: float; amount: str

class CreditRow(BaseModel):
    name: str; ytm: Optional[float]=None; g_spread: str=""; z_spread: str=""
    horizon: str=""; pd_year: str=""; pd_cum: str=""; el: str=""; zone: str=""

class BondReport(BaseModel):
    portfolio_value: Optional[float]=None
    ytm: Optional[float]=None
    duration: Optional[float]=None
    metrics: List[Metric]=[]
    struct_ccy: List[StructRow]=[]
    struct_type: List[StructRow]=[]
    positions: List[Position]=[]
    positions_total: Optional[dict]=None
    stress: List[StressCell]=[]
    credit_summary: Optional[CreditSummary]=None
    credit_zones: List[CreditZone]=[]
    credit_rows: List[CreditRow]=[]
    chart_coupons: Optional[str]=None
    coupons_note: Optional[str]=""


def _img(b64, max_w_mm):
    if not b64: return None
    if b64.startswith("data:"): b64=b64.split(",",1)[1]
    bio=io.BytesIO(base64.b64decode(b64))
    from reportlab.lib.utils import ImageReader
    ir=ImageReader(bio); iw,ih=ir.getSize()
    w=max_w_mm*mm; h=w*ih/iw; bio.seek(0)
    return Image(bio,width=w,height=h)


def _watermark(canvas, doc):
    """Водяной знак + подпись источника на каждой странице."""
    canvas.saveState()
    W, H = landscape(A4)
    # диагональный бледный знак
    canvas.setFont(FONT_B, 46)
    canvas.setFillColor(colors.Color(0.18,0.35,0.24, alpha=0.05))
    canvas.translate(W/2, H/2); canvas.rotate(30)
    canvas.drawCentredString(0, 0, "investtools.pro")
    canvas.restoreState()
    # нижний колонтитул
    canvas.saveState()
    canvas.setFont(FONT, 7); canvas.setFillColor(TEXT3)
    canvas.drawString(15*mm, 8*mm, "investtools.pro · Данные: MOEX ISS API · "+datetime.now().strftime("%d.%m.%Y"))
    canvas.drawRightString(W-15*mm, 8*mm, f"стр. {doc.page}")
    canvas.restoreState()


def S():
    ss=getSampleStyleSheet()
    return {
        "h1":ParagraphStyle("h1",parent=ss["Title"],fontName=FONT_B,fontSize=17,textColor=GREEN,spaceAfter=2,alignment=TA_LEFT),
        "sub":ParagraphStyle("sub",parent=ss["Normal"],fontName=FONT,fontSize=8.5,textColor=TEXT2,spaceAfter=8),
        "h2":ParagraphStyle("h2",parent=ss["Heading2"],fontName=FONT_B,fontSize=11,textColor=GREEN,spaceBefore=10,spaceAfter=5),
        "body":ParagraphStyle("body",parent=ss["Normal"],fontName=FONT,fontSize=8.5,textColor=TEXT,leading=12),
        "small":ParagraphStyle("small",parent=ss["Normal"],fontName=FONT,fontSize=7.5,textColor=TEXT2,leading=10),
    }


def _bar(pct, w_mm, color):
    """Мини-полоска доли (как на экране)."""
    from reportlab.graphics.shapes import Drawing, Rect
    d=Drawing(w_mm*mm, 4*mm)
    d.add(Rect(0,1*mm,w_mm*mm,2*mm, fillColor=SURF2, strokeColor=None))
    d.add(Rect(0,1*mm,w_mm*mm*min(pct,100)/100,2*mm, fillColor=color, strokeColor=None))
    return d


def build_pdf(p: BondReport) -> io.BytesIO:
    buf=io.BytesIO()
    PAGE=landscape(A4)
    doc=SimpleDocTemplate(buf,pagesize=PAGE,leftMargin=15*mm,rightMargin=15*mm,
                          topMargin=13*mm,bottomMargin=14*mm)
    st=S(); story=[]; CW=267  # рабочая ширина альбомного A4 (мм)

    # ---- ШАПКА ----
    story.append(Paragraph("Портфель облигаций", st["h1"]))
    dt=datetime.now().strftime("%d.%m.%Y")
    ex=[]
    if p.portfolio_value: ex.append(f"Стоимость {p.portfolio_value:,.0f} \u20bd".replace(","," "))
    if p.ytm is not None: ex.append(f"YTM {p.ytm:.2f}%")
    if p.duration is not None: ex.append(f"дюрация {p.duration:.2f} лет")
    story.append(Paragraph("investtools.pro · MOEX ISS API · "+dt+(" · "+" · ".join(ex) if ex else ""), st["sub"]))

    # ---- МЕТРИКИ (плашки, 3 в ряд) ----
    if p.metrics:
        cells=[]
        for m in p.metrics:
            bg = BLUE_LT if m.kind=="blue" else GREEN_LT
            col = BLUE if m.kind=="blue" else GREEN2
            txt=f'<font size=13 color="#{col.hexval()[2:]}"><b>{m.value}</b></font><br/><font size=7 color="#6B6A65">{m.label}'
            if m.sub: txt+=f'<br/>{m.sub}'
            txt+='</font>'
            cells.append((Paragraph(txt,st["body"]), bg))
        rows=[]; bgmap=[]
        for i in range(0,len(cells),3):
            chunk=cells[i:i+3]
            row=[c[0] for c in chunk]; bgs=[c[1] for c in chunk]
            while len(row)<3: row.append(""); bgs.append(colors.white)
            rows.append(row); bgmap.append(bgs)
        mt=Table(rows,colWidths=[CW/3*mm]*3)
        ms=[("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9),
            ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
            ("INNERGRID",(0,0),(-1,-1),3,colors.white),("BOX",(0,0),(-1,-1),3,colors.white)]
        for r,bgs in enumerate(bgmap):
            for c,bg in enumerate(bgs):
                ms.append(("BACKGROUND",(c,r),(c,r),bg))
        mt.setStyle(TableStyle(ms))
        story.append(mt)

    # ---- СТРУКТУРА ПОРТФЕЛЯ ----
    if p.struct_ccy or p.struct_type:
        story.append(Paragraph("Структура портфеля", st["h2"]))
        def struct_block(title, rows):
            data=[[Paragraph(f'<b>{title}</b>',st["small"]),"",""]]
            for r in rows:
                data.append([r.label, f"{r.pct:.1f}%", r.amount])
            t=Table(data,colWidths=[52*mm,20*mm,42*mm])
            t.setStyle(TableStyle([
                ("FONTNAME",(0,0),(-1,-1),FONT),("FONTSIZE",(0,0),(-1,-1),8.5),
                ("FONTNAME",(1,1),(1,-1),FONT_B),
                ("ALIGN",(1,0),(-1,-1),"RIGHT"),("TEXTCOLOR",(2,1),(2,-1),TEXT2),
                ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
                ("SPAN",(0,0),(-1,0)),
            ]))
            return t
        left = struct_block("По валюте номинала", p.struct_ccy) if p.struct_ccy else ""
        right = struct_block("По типу купона", p.struct_type) if p.struct_type else ""
        wrap=Table([[left,right]],colWidths=[CW/2*mm]*2)
        wrap.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.append(wrap)

    # ---- ПОЗИЦИИ ----
    if p.positions:
        story.append(Paragraph("Позиции", st["h2"]))
        head=["Бумага","Вал","Купон","Кол-во","Доля","Стоимость","YTM","Купон/год","Дюр.","Выпукл.","Цена","Погашение"]
        rows=[head]
        for x in p.positions:
            rows.append([
                x.name, x.ccy, x.ctype,
                f"{x.qty:g}", f"{x.weight:.1f}%", x.value,
                f"{x.ytm:.2f}%" if x.ytm is not None else "—",
                x.coupon_year,
                f"{x.duration:.2f}" if x.duration is not None else "—",
                f"{x.convexity:.1f}" if x.convexity is not None else "—",
                f"{x.price:.2f}%" if x.price is not None else "—",
                x.maturity,
            ])
        if p.positions_total:
            t=p.positions_total
            rows.append(["ИТОГО","","","",t.get("weight","100%"),t.get("value",""),
                         t.get("ytm",""),t.get("coupon_year",""),t.get("duration",""),
                         t.get("convexity",""),"",""])
        cw=[CW*w*mm for w in [0.13,0.045,0.06,0.06,0.05,0.10,0.06,0.09,0.05,0.06,0.07,0.10]]
        pt=Table(rows,colWidths=cw,repeatRows=1)
        pstyle=[
            ("BACKGROUND",(0,0),(-1,0),GREEN),("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),FONT_B),("FONTNAME",(0,1),(-1,-1),FONT),
            ("FONTSIZE",(0,0),(-1,-1),7.3),
            ("ALIGN",(3,0),(-1,-1),"RIGHT"),("ALIGN",(0,0),(0,-1),"LEFT"),
            ("ALIGN",(1,0),(2,-1),"CENTER"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),
            ("ROWBACKGROUNDS",(0,1),(-1,-2 if p.positions_total else -1),[colors.white,SURF2]),
            ("LINEBELOW",(0,0),(-1,0),1,GREEN),
        ]
        if p.positions_total:
            n=len(rows)-1
            pstyle+=[("BACKGROUND",(0,n),(-1,n),GREEN_LT),("FONTNAME",(0,n),(-1,n),FONT_B),
                     ("TEXTCOLOR",(0,n),(-1,n),GREEN),("LINEABOVE",(0,n),(-1,n),1,GREEN)]
        pt.setStyle(TableStyle(pstyle))
        story.append(pt)

    # ---- КРЕДИТНЫЙ РИСК ----
    if p.credit_summary or p.credit_rows:
        story.append(PageBreak())
        story.append(Paragraph("Кредитный риск · рублёвые бумаги со спредом", st["h2"]))
        if p.credit_summary and p.credit_summary.note:
            story.append(Paragraph(p.credit_summary.note, st["small"]))
            story.append(Spacer(1,3*mm))
        # сводка 3 колонки
        cs=p.credit_summary
        if cs:
            sm=Table([[
                Paragraph(f'<font size=8 color="#6B6A65">Средневзвеш. G-spread</font><br/><font size=13><b>{cs.g_spread or "—"}</b></font><br/><font size=7 color="#9C9B96">YTM − КБД ОФЗ</font>',st["body"]),
                Paragraph(f'<font size=8 color="#6B6A65">Средневзвеш. Z-spread</font><br/><font size=13><b>{cs.z_spread or "—"}</b></font><br/><font size=7 color="#9C9B96">параллельный сдвиг КБД</font>',st["body"]),
                Paragraph(f'<font size=8 color="#6B6A65">Средневзвеш. PD (год)</font><br/><font size=13><b>{cs.pd_year or "—"}</b></font><br/><font size=7 color="#9C9B96">risk-neutral, RR 20%</font>',st["body"]),
            ]],colWidths=[CW/3*mm]*3)
            sm.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),GREEN_LT),
                ("BOX",(0,0),(-1,-1),3,colors.white),("INNERGRID",(0,0),(-1,-1),3,colors.white),
                ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
                ("LEFTPADDING",(0,0),(-1,-1),10),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
            story.append(sm); story.append(Spacer(1,4*mm))
        # зоны качества
        if p.credit_zones:
            story.append(Paragraph("Распределение по зонам кредитного качества (по Z-spread)", st["body"]))
            zr=[]
            for z in p.credit_zones:
                zr.append([z.label, f"{z.pct:.1f}%", z.amount])
            zt=Table(zr,colWidths=[80*mm,25*mm,45*mm])
            zt.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),FONT),("FONTSIZE",(0,0),(-1,-1),8.5),
                ("FONTNAME",(1,0),(1,-1),FONT_B),("ALIGN",(1,0),(-1,-1),"RIGHT"),
                ("TEXTCOLOR",(2,0),(2,-1),TEXT2),
                ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
            story.append(zt); story.append(Spacer(1,4*mm))
        # таблица по бумагам
        if p.credit_rows:
            story.append(Paragraph("По каждой бумаге", st["body"]))
            head=["Бумага","YTM","G-spread","Z-spread","Горизонт","PD (год)","PD кум.","EL","Зона"]
            rows=[head]
            for r in p.credit_rows:
                rows.append([r.name, f"{r.ytm:.2f}%" if r.ytm is not None else "—",
                    r.g_spread, r.z_spread, r.horizon, r.pd_year, r.pd_cum, r.el, r.zone])
            cw=[CW*w*mm for w in [0.15,0.08,0.10,0.10,0.19,0.09,0.09,0.08,0.12]]
            ct=Table(rows,colWidths=cw,repeatRows=1)
            cstyle=[("BACKGROUND",(0,0),(-1,0),GREEN),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("FONTNAME",(0,0),(-1,0),FONT_B),("FONTNAME",(0,1),(-1,-1),FONT),
                ("FONTSIZE",(0,0),(-1,-1),7.3),
                ("ALIGN",(1,0),(-2,-1),"RIGHT"),("ALIGN",(0,0),(0,-1),"LEFT"),
                ("ALIGN",(4,0),(4,-1),"RIGHT"),("ALIGN",(8,0),(8,-1),"CENTER"),
                ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,SURF2]),
                ("LINEBELOW",(0,0),(-1,0),1,GREEN)]
            ct.setStyle(TableStyle(cstyle))
            story.append(ct)

    # ---- СТРЕСС-ТЕСТ (плашки) ----
    if p.stress:
        story.append(PageBreak())
        story.append(Paragraph("Стресс-тест: изменение стоимости портфеля при сдвиге ключевой ставки", st["h2"]))
        story.append(Paragraph("Оценка через модифицированную дюрацию и выпуклость: ΔP ≈ −D·Δy + ½·C·Δy². Выпуклость даёт асимметрию — при снижении ставки портфель прибавляет чуть больше, чем теряет при таком же росте.", st["small"]))
        story.append(Spacer(1,3*mm))
        sp=sorted(p.stress,key=lambda x:x.shift)
        def cell(sc):
            up = sc.pct>0
            bg = GREEN_LT if up else RED_LT
            col= GREEN2 if up else RED
            txt=f'<font size=7 color="#6B6A65">{"+" if sc.shift>0 else ""}{sc.shift} бп</font><br/><font size=13 color="#{col.hexval()[2:]}"><b>{"+" if sc.pct>0 else ""}{sc.pct:.2f}%</b></font><br/><font size=7 color="#9C9B96">{sc.rub}</font>'
            return (Paragraph(txt,st["body"]),bg)
        cells=[cell(s) for s in sp]
        # по 5 в ряд
        rows=[]; bgm=[]
        for i in range(0,len(cells),5):
            ch=cells[i:i+5]
            rows.append([c[0] for c in ch]+[""]*(5-len(ch)))
            bgm.append([c[1] for c in ch]+[colors.white]*(5-len(ch)))
        stt=Table(rows,colWidths=[CW/5*mm]*5)
        sst=[("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,0),(-1,-1),"CENTER"),
             ("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9),
             ("INNERGRID",(0,0),(-1,-1),4,colors.white),("BOX",(0,0),(-1,-1),4,colors.white)]
        for r,bgs in enumerate(bgm):
            for c,bg in enumerate(bgs):
                sst.append(("BACKGROUND",(c,r),(c,r),bg))
        stt.setStyle(TableStyle(sst))
        story.append(stt)

    # ---- КУПОННЫЙ КАЛЕНДАРЬ ----
    if p.chart_coupons:
        story.append(Spacer(1,6*mm))
        story.append(Paragraph("Купонный календарь (ближайшие 12 месяцев)", st["h2"]))
        im=_img(p.chart_coupons, CW*0.75)
        if im: story.append(im)
        if p.coupons_note:
            story.append(Spacer(1,2*mm))
            story.append(Paragraph(p.coupons_note, st["small"]))

    doc.build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    buf.seek(0); return buf


@bonds_router.post("/report")
async def make_report(payload: BondReport):
    try:
        pdf=build_pdf(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF build error: {e}")
    fn=f"bond_portfolio_{datetime.now().strftime('%Y%m%d')}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf",
        headers={"Content-Disposition":f'attachment; filename="{fn}"'})
