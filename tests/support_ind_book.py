"""Синтетические документы эмитента этой копии для тестов индикаторов: книга XLSX и страница перечня.

Файлы собираются кодом теста — в репозитории нет ни одного файла эмитента. **Формат** — как у источника
(листы потоков и остатков месячной книги, заголовки столбцов «август'2026» и «8М'2026», даты остатков
числом дней Excel; страница — ссылки на файлы с повторённым заголовком и подписью «размер, дата»),
**числа сочинены** и с настоящими не совпадают. Контактов, оговорок и подписей эмитента в них нет.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from typing import Any, Iterable, Sequence
from xml.sax.saxutils import escape

from indicators import periods

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
EXCEL_EPOCH = date(1899, 12, 30)
MONTH_NOMINATIVE = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
                    "ноябрь", "декабрь")
MONTH_GENITIVE = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
                  "ноября", "декабря")
PAGE_URL = "https://www.vtb.ru/ir/statements/results/"
FILES = "/media-files/vtb.ru/sitepages/ir/statements/results/"

# Строки листа потоков: (метка книги, основа метрики); расходы и резервы — со знаком минус, как в книге.
FLOW_ROWS = (("  Чистые процентные доходы", "nii"), ("  Чистые комиссионные доходы", "fee"),
             ("  Прочие операционные доходы", "other"), ("ЧОД до резервов", "opinc"),
             ("  Создание резервов под кредитные убытки\n  и прочие резервы ", "prov"),
             ("  Расходы на содержание персонала и\n  административные расходы", "opex"),
             ("Прибыль до налогообложения", "pretax"), ("  Расходы по налогу на прибыль", "tax"),
             ("Чистая прибыль", "np"))
RATIO_ROWS = (("Чистая процентная маржа (NIM) ", "nim"), ("Чистая комиссионная маржа (NCM) ", None),
              ("Стоимость риска (CoR)", "cor"), (" -  CoR ЮЛ", None), ("Расходы / Доходы (CIR)", "cir"),
              ("Расходы / Активы", None), ("Возврат на капитал (ROE)", "roe"))
STOCK_ROWS = (("Кредиты и авансы клиентам (до резервов)", "loans_gross"), (" -   Кредиты ЮЛ", "loans_ul"),
              (" -   Кредиты ФЛ ", "loans_fl"), ("Итого активы", "assets"),
              ("Средства банков и прочие заемные средства", None), ("Средства клиентов", "funds_total"),
              ("-   Средства клиентов ЮЛ", "funds_ul"), ("-   Средства клиентов ФЛ", "funds_fl"),
              ("Итого собственные средства", "equity"))
QUALITY_ROWS = (("Коэф. неработающих кредитов (NPL 90+)", "npl90"), ("Кредиты / Депозиты ", None))
CAPITAL_ROWS = (("Норматив Н20.0 ", "n20_0"), ("Норматив Н20.1 ", "n20_1"), ("Норматив Н20.2", "n20_2"))


def excel_serial(day: date) -> float:
    return float((day - EXCEL_EPOCH).days)


def _ref(row: int, col: int) -> str:
    letters = ""
    n = col + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return f"{letters}{row}"


def make_xlsx(sheets: Sequence[tuple[str, Sequence[Sequence[Any]]]], *, start_row: int = 1) -> bytes:
    """Книга XLSX из листов `[(имя, строки)]`: строка — список ячеек (`None` — пустая, текст — общая строка,
    число — число). Достаточно для чтения `indicators.xlsx_book.read`; стилей и формул нет."""
    shared: list[str] = []
    index: dict[str, int] = {}
    parts: dict[str, str] = {}
    for n, (_, rows) in enumerate(sheets, start=1):
        body = []
        for r, cells in enumerate(rows, start=start_row):
            out = []
            for c, value in enumerate(cells):
                if value is None:
                    continue
                if isinstance(value, str):
                    if value not in index:
                        index[value] = len(shared)
                        shared.append(value)
                    out.append(f'<c r="{_ref(r, c)}" t="s"><v>{index[value]}</v></c>')
                else:
                    out.append(f'<c r="{_ref(r, c)}"><v>{float(value)!r}</v></c>')
            if out:
                body.append(f'<row r="{r}">{"".join(out)}</row>')
        parts[f"xl/worksheets/sheet{n}.xml"] = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{MAIN_NS}"><sheetData>'
            f'{"".join(body)}</sheetData></worksheet>')
    names = "".join(f'<sheet name="{escape(name, {chr(34): "&quot;"})}" sheetId="{n}" r:id="rId{n}"/>'
                    for n, (name, _) in enumerate(sheets, start=1))
    parts["xl/workbook.xml"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{MAIN_NS}" '
                                f'xmlns:r="{REL_NS}"><sheets>{names}</sheets></workbook>')
    rels = "".join(f'<Relationship Id="rId{n}" Type="{REL_NS}/worksheet" Target="worksheets/sheet{n}.xml"/>'
                   for n in range(1, len(sheets) + 1))
    parts["xl/_rels/workbook.xml.rels"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                                           f'<Relationships xmlns="{PKG_NS}">{rels}</Relationships>')
    strings = "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in shared)
    parts["xl/sharedStrings.xml"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst xmlns="{MAIN_NS}" '
                                     f'count="{len(shared)}" uniqueCount="{len(shared)}">{strings}</sst>')
    parts["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/></Types>')
    parts["_rels/.rels"] = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PKG_NS}">'
                            f'<Relationship Id="rId1" Type="{REL_NS}/officeDocument" Target="xl/workbook.xml"/>'
                            f'</Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(parts):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))     # одни и те же байты при повторе
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, parts[name])
    return buf.getvalue()


def _month_flows(year: int, m: int, seed: float = 0.0) -> dict[str, float]:
    """Сочинённые потоки одного месяца (млрд ₽, один знак после запятой)."""
    k = (year - 2020) + m / 10.0 + seed
    month = {"nii": 50.0 + k, "fee": 20.0 + k / 2, "other": 5.0 + k / 4, "prov": -(10.0 + k / 5), "opex": -(30.0 + k / 3),
             "tax": -(6.0 + k / 10)}
    month = {key: round(value, 1) for key, value in month.items()}
    month["opinc"] = round(month["nii"] + month["fee"] + month["other"], 1)
    month["pretax"] = round(month["opinc"] + month["prov"] + month["opex"], 1)
    month["np"] = round(month["pretax"] + month["tax"], 1)
    return month


def synthetic_numbers(period: str, *, seed: float = 0.0) -> dict[str, float]:
    """Сочинённые числа месяца: поток с начала года — сумма потоков месяцев года (тождество «итог = прошлый
    итог + месяц» сходится), доли — доли. `seed` сдвигает числа месяца: книга того же месяца с другим `seed` —
    пересмотр."""
    year, m = periods.parse_month(period)
    k = (year - 2020) + m / 10.0 + seed
    own = _month_flows(year, m, seed)
    out: dict[str, float] = {}
    for key, value in own.items():
        out[f"{key}_m"] = value
        out[f"{key}_ytd"] = round(value + sum(_month_flows(year, j)[key] for j in range(1, m)), 1)
    for key, level in (("nim", 0.02), ("cor", 0.008), ("cir", 0.4), ("roe", 0.15)):
        out[f"{key}_m"] = round(level + k / 10000.0, 4)
        out[f"{key}_ytd"] = round(level + k / 20000.0, 4)
    out.update({"loans_gross": 20000.0 + 100 * k, "loans_ul": 14000.0 + 70 * k, "loans_fl": 6000.0 + 30 * k,
                "assets": 30000.0 + 150 * k, "funds_total": 22000.0 + 90 * k, "funds_ul": 12000.0 + 50 * k,
                "funds_fl": 10000.0 + 40 * k, "equity": 2500.0 + 10 * k, "npl90": 0.035, "n20_0": 0.1 + k / 10000.0,
                "n20_1": 0.07, "n20_2": 0.085})
    return {key: round(value, 4) for key, value in out.items()}


def monthly_book(period: str, *, numbers: dict[str, float] | None = None, month_column: bool | None = None,
                 comparative: bool = True, seed: float = 0.0, first_format: bool = False) -> bytes:
    """Месячная книга в формате источника за месяц `period`.

    `month_column=False` — книга «за два месяца»: только нарастающий итог (так печатается февраль).
    `comparative` — столбцы того же месяца год назад, конца прошлого месяца и конца прошлого года.
    `first_format` — ранний вид: «апрель'2023», «4 мес'2023», без столбцов сравнения и нормативов."""
    year, m = periods.parse_month(period)
    own = numbers or synthetic_numbers(period, seed=seed)
    month_column = (m != 2) if month_column is None else month_column
    ago = synthetic_numbers(periods.shift_month(period, -12))
    prev = synthetic_numbers(periods.shift_month(period, -1))
    start = synthetic_numbers(periods.month(year - 1, 12))
    ytd_title = f"{m} мес'{year}" if first_format else f"{m}М'{year}"
    header: list[Any] = ["Ключевые показатели отчета о прибылях и убытках  (млрд. рублей)"]
    columns: list[tuple[str, dict[str, float]]] = []
    if month_column:
        header.append(f"{MONTH_NOMINATIVE[m - 1]}'{year}")
        columns.append(("_m", own))
        if comparative and not first_format:
            header += [f"{MONTH_NOMINATIVE[m - 1]}'{year - 1}", "изменение"]
            columns += [("_m", ago), ("", {})]
    header.append(ytd_title)
    columns.append(("_ytd", own))
    if comparative and not first_format:
        header += [f"{m}М'{year - 1}", "изменение"]
        columns += [("_ytd", ago), ("", {})]

    def flow_row(label: str, base: str | None, change: Any = 0.05) -> list[Any]:
        cells: list[Any] = [label]
        for suffix, source in columns:
            cells.append(change if not suffix else (0.007 if base is None else source.get(f"{base}{suffix}")))
        return cells

    flows = [[None], ["Неаудированные ключевые показатели (сочинённые числа теста)"], [None], header]
    flows += [flow_row(label, base) for label, base in FLOW_ROWS]
    flows.append(["Показатели  эффективности"] + header[1:])
    flows += [flow_row(label, base, "10 б.п.") for label, base in RATIO_ROWS]

    end = periods.month_end(period)
    dates: list[Any] = [excel_serial(end)]
    sources = [own]
    if comparative and not first_format:
        if month_column:
            dates += [excel_serial(periods.month_end(periods.shift_month(period, -1))), "  изменение за месяц"]
            sources += [prev, {}]
        dates += [excel_serial(date(year - 1, 12, 31)), "  изменение с начала года"]
        sources += [start, {}]

    def stock_row(label: str, key: str | None, change: Any = 0.01) -> list[Any]:
        return [label] + [(change if not source else (1000.0 if key is None else source.get(key))) for source in sources]

    stocks = [["Неаудированные ключевые показатели (сочинённые числа теста)"],
              ["Ключевые балансовые показатели \n(млрд. рублей)"] + dates]
    stocks += [stock_row(label, key) for label, key in STOCK_ROWS]
    stocks.append(["Балансовые коэффициенты  и показатели кредитного качества "] + dates)
    stocks += [stock_row(label, key, "0 б.п.") for label, key in QUALITY_ROWS]
    if not first_format:
        # нормативы — на первое число следующего месяца: тот же месяц данных
        first_days = [excel_serial(periods.month_start(periods.shift_month(period, 1)))] + [
            (d + 1.0 if isinstance(d, float) else d) for d in dates[1:]]
        stocks.append(["Достаточность капитала"] + first_days)
        stocks += [stock_row(label, key, "-20 б.п.") for label, key in CAPITAL_ROWS]
    return make_xlsx([("Ключевые показатели P&L", flows), ("Ключевые балансовые показатели", stocks),
                      ("Показатели и коэффициенты", [["Показатели и коэффициенты"], ["ЧОД до резервов", "пояснение"]])])


def caption(day: str, size: str = "41.66 Кб") -> str:
    d = date.fromisoformat(day)
    return f"{size}, {d.day:02d} {MONTH_GENITIVE[d.month - 1]} {d.year}"


def results_page(entries: Iterable[dict[str, Any]]) -> bytes:
    """Страница перечня в формате источника: у файла — ссылка с повторённым заголовком и подписью «размер, дата»,
    рядом — ссылка «Пресс-релиз» на страницу новости (в перечень не входит). `entries` — `{file, title, day}`."""
    blocks = []
    for n, e in enumerate(entries):
        blocks.append(
            f'<div class="doc-{n}"><a aria-disabled="false" href="{FILES}{e["file"]}" class="x{n}">'
            f'<div role="document"><svg width="48px" viewBox="0 0 24 24"><path d="M20 9.5V6"></path></svg><div><div>'
            f'<div class="full">{e["title"]}</div><span class="short">{e["title"]}</span></div>'
            f'<span class="sub">{caption(e["day"], e.get("size", "41.66 Кб"))}</span></div></div></a></div>\n'
            f'<div><a aria-disabled="false" href="/about/press/news/?id={1000 + n}" class="y{n}">Пресс-релиз<svg '
            f'width="16"></svg></a></div>')
    page = ('<!DOCTYPE html><html lang="ru"><head><title>Результаты по МСФО</title><script>var x = "<a href=\\"/media-'
            'files/skip.pdf\\">";</script></head><body><p>Документы</p>' + "\n".join(blocks)
            + '<a href="https://example.org/media-files/foreign.pdf">чужой файл</a></body></html>')
    return page.encode("utf-8")
