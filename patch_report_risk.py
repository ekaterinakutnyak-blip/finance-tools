# -*- coding: utf-8 -*-
"""
Добавляет в /opt/finance-api/report_us.py таблицу «Риск по бумагам · sigma, beta, R2».

Что делает:
  1. снимает резервную копию report_us.py рядом, с датой в имени;
  2. вставляет модель StockRisk и поле stock_risk в ReportPayload;
  3. вставляет блок отрисовки таблицы перед секцией аналитики;
  4. проверяет, что файл компилируется; если нет — откатывает всё обратно.

Запускать повторно безопасно: если правка уже стоит, скрипт ничего не делает.
Ничего, кроме report_us.py, не трогает.
"""

import io, os, shutil, sys, py_compile, datetime

TARGET = "/opt/finance-api/report_us.py"

A1 = "class ReportPayload(BaseModel):"
A2 = "    analytics: Optional[Analytics] = None"
A3 = "    # ---- НОВЫЕ БЛОКИ: периоды, коэффициенты, просадки, месяцы ----"

MODEL = '''class StockRisk(BaseModel):
    ticker: str
    weight: Optional[float] = None     # доля в портфеле, %
    vol: Optional[float] = None        # годовая волатильность бумаги, %
    beta: Optional[float] = None       # бета к индексу
    r2: Optional[float] = None         # доля R2, 0..1


'''

FIELD = "    stock_risk: List[StockRisk] = []   # риск по бумагам: sigma, beta, R2\n"

BLOCK = '''    # ---- РИСК ПО БУМАГАМ: sigma, beta, R2 ----
    if p.stock_risk:
        _bm = p.benchmark or ("IMOEX" if p.market == "ru" else "SPY")
        story.append(Paragraph("Риск по бумагам \\u00b7 \\u03c3, \\u03b2 и R\\u00b2", S["h2"]))
        story.append(Paragraph(
            "\\u03c3 \\u2014 годовая волатильность самой бумаги: насколько сильно она колеблется "
            "независимо от рынка. R\\u00b2 \\u2014 какая доля её колебаний объясняется рынком "
            "(систематический риск, он не убирается диверсификацией). Остальное \\u2014 собственный "
            "риск эмитента, он гасится при диверсификации несвязанными бумагами. "
            "\\u03b2 \\u2014 сила движения относительно индекса.", S["small"]))
        story.append(Spacer(1, 2 * mm))
        _rows = [["Тикер", "Доля", "\\u03c3, %", "\\u03b2", "R\\u00b2 к " + _bm, "Риск в основном"]]
        for _s in p.stock_risk:
            _r2p = None if _s.r2 is None else int(round(_s.r2 * 100))
            if _r2p is None:
                _kind = "\\u2014"
            elif _r2p >= 60:
                _kind = "рыночный"
            elif _r2p <= 30:
                _kind = "собственный"
            else:
                _kind = "смешанный"
            _rows.append([
                _s.ticker,
                "\\u2014" if _s.weight is None else "%.1f%%" % _s.weight,
                "\\u2014" if _s.vol is None else "%.1f" % _s.vol,
                "\\u2014" if _s.beta is None else "%.2f" % _s.beta,
                "\\u2014" if _r2p is None else "%d%%" % _r2p,
                _kind,
            ])
        _fr = [0.17, 0.13, 0.13, 0.12, 0.17, 0.28]
        _t = Table(_rows, colWidths=[f * CONTENT_W * mm for f in _fr], hAlign="LEFT")
        _t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), FONT_B),
            ("FONTNAME", (0, 1), (-1, -1), FONT),
            ("FONTNAME", (0, 1), (0, -1), FONT_B),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), GREEN),
            ("TEXTCOLOR", (5, 1), (5, -1), TEXT2),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (4, -1), "RIGHT"),
            ("ALIGN", (5, 0), (5, -1), "LEFT"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, GREEN),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, TEXT2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(_t)
        story.append(Spacer(1, 4 * mm))

'''


def main():
    if not os.path.isfile(TARGET):
        print("ОШИБКА: не найден " + TARGET)
        return 1

    src = io.open(TARGET, encoding="utf-8").read()

    if "class StockRisk" in src or "stock_risk" in src:
        print("УЖЕ СТОИТ: правка была применена раньше, ничего не меняю.")
        return 0

    missing = [n for n, a in (("модель ReportPayload", A1),
                              ("поле analytics", A2),
                              ("секция аналитики", A3)) if src.count(a) != 1]
    if missing:
        print("ОШИБКА: не нашла однозначную точку вставки: " + ", ".join(missing))
        print("Файл не тронут. Покажи этот вывод Claude.")
        return 1

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = TARGET + ".bak_" + stamp
    shutil.copy2(TARGET, backup)

    out = src.replace(A1, MODEL + A1, 1)

    i = out.index(A2)
    j = out.index("\n", i) + 1
    out = out[:j] + FIELD + out[j:]

    out = out.replace(A3, BLOCK + A3, 1)

    io.open(TARGET, "w", encoding="utf-8").write(out)

    try:
        py_compile.compile(TARGET, doraise=True)
    except Exception as e:
        shutil.copy2(backup, TARGET)
        print("ОШИБКА КОМПИЛЯЦИИ, всё откачено назад:")
        print(e)
        return 1

    print("ГОТОВО")
    print("  резервная копия: " + backup)
    print("  добавлено строк: " + str(out.count("\n") - src.count("\n")))
    print("Дальше: systemctl restart finance-api")
    return 0


if __name__ == "__main__":
    sys.exit(main())
