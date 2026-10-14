"""Книга XLSX эмитента без сторонних библиотек: чтение (zip + XML) и разбор месячной книги результатов.

**Чтение** — `read(body)`: листы книги по порядку, у листа — ячейки `{(строка, столбец): значение}`
(строка — номер листа с единицы, столбец — с нуля); числа — `float`, текст — `str` (общие строки и
строки внутри ячейки), пустые ячейки пропущены. Формулы не вычисляются: берётся сохранённое
значение. Файл — чужой ввод: потолки на число частей и листов, на размер части после распаковки и
на число ячеек; часть с объявлением типа документа или сущностей не разбирается (`BookError`).

**Разбор месячной книги** — `parse_monthly(body, spec)`. Что где лежит, называет настройка
(`sources.yaml → issuer_docs.monthly_book`); слов эмитента в коде нет:

* `flows` — лист потоков (`sheet` — выражение по имени листа). Столбцы названы в строке заголовка:
  месяцем («август'2026», «апр'2024» — `month_column` с группами `month_name`, `year`) или числом
  месяцев с начала года («8М'2026», «4 мес'2023» — `ytd_column` с группами `months`, `year`).
  **Период книги** — самый поздний столбец нарастающего итога. Строка `rows` (основа метрики →
  начало метки) даёт `<основа>_m` из столбца месяца книги и `<основа>_ytd` из столбца нарастающего
  итога; в книге без столбца месяца (два месяца одной суммой) есть только нарастающий итог.
* `stocks` — лист остатков: столбцы — даты в заголовке (число дней Excel или «ДД.ММ.ГГГГ»).
  Значение месяца книги — столбец на её последний день; дата на первое число (нормативы «на 01.09»)
  относится к месяцу, который кончился накануне.
* Числа прочих столбцов (тот же месяц год назад, конец прошлого месяца, конец прошлого года) —
  в `comparative` по периодам: ими заполняются месяцы, за которые отдельной книги не было.

Метка сравнивается после чистки (пробелы и переводы строк — один пробел, нижний регистр, «ё» → «е»)
выражением от начала метки; метрика берётся из первой совпавшей строки. Доли остаются долями,
деньги — как напечатаны (расходы и резервы — со знаком книги).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from typing import Any, Mapping
from xml.etree import ElementTree as ET

from indicators import periods

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ZIP_MAGIC = b"PK\x03\x04"
MAX_PARTS = 400                       # частей архива: у книги эмитента их десятки
MAX_SHEETS = 40
MAX_PART_BYTES = 24 * 1024 * 1024     # одна часть после распаковки
MAX_CELLS = 2 ** 19                   # ячеек во всей книге
FORBIDDEN_MARKUP = (b"<!DOCTYPE", b"<!ENTITY")
EXCEL_EPOCH = (1899, 12, 30)          # день «ноль» счёта дат Excel
# Дата заголовка столбца остатков — число дней Excel в окне вокруг периода книги: год с небольшим назад
# (конец прошлого года, тот же месяц год назад) и первые дни следующего месяца.
DATE_WINDOW_BACK_DAYS = 800
DATE_WINDOW_AHEAD_DAYS = 5
MONTH_STEMS = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
MAY_FORMS = ("мая", "мае")            # «май» в косвенных падежах теряет основу из трёх букв
SUFFIX_MONTH, SUFFIX_YTD = "_m", "_ytd"
DIGITS = 10                           # знаков после запятой: хвост двоичной дроби в ряды не идёт

Cells = dict[tuple[int, int], Any]


class BookError(ValueError):
    """Файл не читается как книга XLSX или не похож на месячную книгу настройки."""


# ------------------------------------------------------------------ чтение

def is_xlsx(body: bytes) -> bool:
    """Архив zip с оглавлением книги (PDF и прочее — нет)."""
    if not body.startswith(ZIP_MAGIC):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            return "xl/workbook.xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


def _part(z: zipfile.ZipFile, name: str) -> bytes:
    try:
        info = z.getinfo(name)
    except KeyError as exc:
        raise BookError(f"в книге нет части {name}") from exc
    if info.file_size > MAX_PART_BYTES:
        raise BookError(f"часть {name} больше потолка ({info.file_size} байт)")
    data = z.read(info)
    head = data[:4096].upper()
    if any(mark in head for mark in FORBIDDEN_MARKUP):
        raise BookError(f"часть {name} объявляет тип документа или сущности — не разбирается")
    return data


def _xml(z: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        return ET.fromstring(_part(z, name))
    except ET.ParseError as exc:
        raise BookError(f"часть {name} не разбирается как XML: {exc}") from exc


def _column(ref: str) -> int:
    """«C7» → 2 (столбец с нуля)."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - ord("A") + 1)
    return n - 1


def _text(node: ET.Element) -> str:
    return "".join(t.text or "" for t in node.iter(f"{{{MAIN_NS}}}t"))


def read(body: bytes) -> list[tuple[str, Cells]]:
    """Листы книги: [(имя листа, {(строка, столбец): значение})] в порядке книги."""
    try:
        z = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise BookError("файл — не архив zip") from exc
    with z:
        names = set(z.namelist())
        if len(names) > MAX_PARTS:
            raise BookError(f"в архиве {len(names)} частей — больше потолка")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared = [_text(si) for si in _xml(z, "xl/sharedStrings.xml").findall(f"{{{MAIN_NS}}}si")]
        book = _xml(z, "xl/workbook.xml")
        rels = _xml(z, "xl/_rels/workbook.xml.rels")
        target = {r.get("Id"): r.get("Target") or "" for r in rels.findall(f"{{{PKG_NS}}}Relationship")}
        sheets = book.find(f"{{{MAIN_NS}}}sheets")
        listed = [] if sheets is None else sheets.findall(f"{{{MAIN_NS}}}sheet")
        if len(listed) > MAX_SHEETS:
            raise BookError(f"в книге {len(listed)} листов — больше потолка")
        out: list[tuple[str, Cells]] = []
        total = 0
        for sheet in listed:
            where = target.get(sheet.get(f"{{{REL_NS}}}id") or "", "")
            if not where:
                continue
            path = where.lstrip("/") if where.startswith("/") else "xl/" + where
            cells: Cells = {}
            for c in _xml(z, path).iter(f"{{{MAIN_NS}}}c"):
                ref = c.get("r") or ""
                digits = "".join(ch for ch in ref if ch.isdigit())
                if not digits or not ref[:1].isalpha():
                    continue
                kind = c.get("t")
                v = c.find(f"{{{MAIN_NS}}}v")
                raw = None if v is None else v.text
                value: Any
                if kind == "inlineStr":
                    value = _text(c)
                elif raw is None:
                    continue
                elif kind == "s":
                    try:
                        value = shared[int(raw)]
                    except (ValueError, IndexError):
                        continue
                elif kind in ("str", "e"):
                    value = raw
                elif kind == "b":
                    value = raw.strip() == "1"
                else:
                    try:
                        value = float(raw)
                    except ValueError:
                        value = raw
                if value == "":
                    continue
                cells[(int(digits), _column(ref))] = value
                total += 1
                if total > MAX_CELLS:
                    raise BookError("в книге больше ячеек, чем потолок разбора")
            out.append((str(sheet.get("name") or ""), cells))
        return out


def rows_of(cells: Cells) -> list[tuple[int, dict[int, Any]]]:
    """{(строка, столбец): значение} → [(строка, {столбец: значение})] по возрастанию строк."""
    by: dict[int, dict[int, Any]] = {}
    for (r, c), v in cells.items():
        by.setdefault(r, {})[c] = v
    return sorted(by.items())


# ------------------------------------------------------------------ значения и заголовки

def clean(text: Any) -> str:
    """Метка для сравнения: один пробел вместо любых пробелов и переводов строк, нижний регистр, «ё» → «е»."""
    t = str(text).replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip().lower().replace("ё", "е")


def number(value: Any) -> float | None:
    """Число ячейки: `float` как есть; текст «2,6%» — доля, «12,5» — число; прочий текст — None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    t = str(value).replace(" ", "").replace(" ", "").replace("−", "-")
    m = re.fullmatch(r"(-?\d+(?:[.,]\d+)?)(%?)", t)
    if m is None:
        return None
    v = float(m.group(1).replace(",", "."))
    return v / 100.0 if m.group(2) else v


def month_number(word: str) -> int | None:
    """Месяц по слову или сокращению: «август», «авг», «апр.», «мая» → номер; не месяц — None."""
    w = clean(word).rstrip(".")
    if w in MAY_FORMS:
        return MONTH_STEMS.index("май") + 1
    stem = w[:3]
    return MONTH_STEMS.index(stem) + 1 if stem in MONTH_STEMS else None


def excel_day(value: Any) -> date | None:
    """Дата заголовка: целое число дней Excel или текст «ДД.ММ.ГГГГ»; иное — None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value != int(value) or value <= 0:
            return None
        try:
            return date(*EXCEL_EPOCH) + timedelta(days=int(value))
        except OverflowError:
            return None
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", str(value).strip())
    if m is None:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def stock_month(day: date) -> str:
    """Месяц остатка по дате заголовка: первое число — месяц, который кончился накануне."""
    return periods.month_of(day - timedelta(days=1)) if day.day == 1 else periods.month_of(day)


def _flow_column(header: Any, spec: Mapping[str, Any]) -> tuple[str, str] | None:
    """Заголовок столбца листа потоков → («m» | «ytd», месяц) или None."""
    text = clean(header)
    for scope, key in ((SUFFIX_YTD, "ytd_column"), (SUFFIX_MONTH, "month_column")):
        pattern = spec.get(key)
        m = re.fullmatch(str(pattern), text, re.I) if pattern else None
        if m is None:
            continue
        got = m.groupdict()
        try:
            year = int(got["year"])
            n = int(got["months"]) if scope == SUFFIX_YTD else month_number(got["month_name"])
        except (KeyError, TypeError, ValueError):
            continue
        if n is not None and 1 <= n <= 12:
            return scope, periods.month(year, n)
    return None


def _label(row: Mapping[int, Any]) -> tuple[int, str] | None:
    """Метка строки — самая левая текстовая ячейка: (столбец, текст после чистки)."""
    for c in sorted(row):
        if isinstance(row[c], str) and clean(row[c]):
            return c, clean(row[c])
    return None


def _sheet(sheets: list[tuple[str, Cells]], pattern: Any) -> Cells | None:
    if not pattern:
        return None
    for name, cells in sheets:
        if re.search(str(pattern), clean(name), re.I):
            return cells
    return None


def _metric(label: str, rows: Mapping[str, Any]) -> str | None:
    for metric, pattern in rows.items():
        if re.match(str(pattern), label, re.I):
            return str(metric)
    return None


# ------------------------------------------------------------------ месячная книга

def _flows(cells: Cells, spec: Mapping[str, Any]) -> tuple[dict[str, dict[str, float]], dict[int, tuple[str, str]]]:
    """Лист потоков → ({месяц: {метрика: значение}}, столбцы последнего заголовка)."""
    rows = dict(spec.get("rows") or {})
    by_period: dict[str, dict[str, float]] = {}
    columns: dict[int, tuple[str, str]] = {}
    seen: dict[int, tuple[str, str]] = {}
    for _, row in rows_of(cells):
        header = {c: got for c, got in ((c, _flow_column(v, spec)) for c, v in row.items()) if got}
        if header:
            columns = header
            seen.update(header)
            continue
        label = _label(row)
        if not columns or label is None:
            continue
        base = _metric(label[1], rows)
        if base is None:
            continue
        for c, (scope, month) in columns.items():
            v = number(row[c]) if c in row else None
            if v is not None:
                by_period.setdefault(month, {}).setdefault(f"{base}{scope}", round(v, DIGITS))
    return by_period, seen


def _stocks(cells: Cells, spec: Mapping[str, Any], period: str) -> dict[str, dict[str, float]]:
    """Лист остатков → {месяц: {метрика: значение}}. Строка заголовка — та, где все числа — даты Excel в окне
    вокруг периода книги (в строках значений рядом с остатками стоят дробные изменения)."""
    rows = dict(spec.get("rows") or {})
    end = periods.month_end(period)
    lo, hi = end - timedelta(days=DATE_WINDOW_BACK_DAYS), end + timedelta(days=DATE_WINDOW_AHEAD_DAYS)
    by_period: dict[str, dict[str, float]] = {}
    columns: dict[int, str] = {}
    for _, row in rows_of(cells):
        label = _label(row)
        first = label[0] if label else -1
        values = {c: v for c, v in row.items() if c > first and not isinstance(v, str)}
        days = {c: excel_day(v) for c, v in row.items() if c > first}
        dated = {c: d for c, d in days.items() if d is not None and lo <= d <= hi}
        if dated and all(c in dated for c in values):
            pattern = spec.get("header")
            if not pattern or (label is not None and re.match(str(pattern), label[1], re.I)):
                columns = {c: stock_month(d) for c, d in dated.items()}
                continue
        if not columns or label is None:
            continue
        metric = _metric(label[1], rows)
        if metric is None:
            continue
        for c, month in columns.items():
            v = number(row[c]) if c in row else None
            if v is not None:
                by_period.setdefault(month, {}).setdefault(metric, round(v, DIGITS))
    return by_period


def parse_monthly(body: bytes, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Месячная книга → {period, numbers, comparative, months_column}.

    `numbers` — числа месяца книги: `<основа>_m`, `<основа>_ytd`, остатки и нормативы на конец месяца.
    `comparative` — {месяц: {метрика: значение}} прочих столбцов. `months_column` — есть ли в книге
    столбец самого месяца (нет — книга несёт только нарастающий итог). Нет листа потоков или столбца
    нарастающего итога — `BookError`.
    """
    sheets = read(body)
    flows_spec = dict(spec.get("flows") or {})
    cells = _sheet(sheets, flows_spec.get("sheet"))
    if cells is None:
        raise BookError("в книге нет листа потоков настройки")
    flows, columns = _flows(cells, flows_spec)
    ytd = sorted(month for scope, month in columns.values() if scope == SUFFIX_YTD)
    if not ytd:
        raise BookError("на листе потоков нет столбца нарастающего итога")
    period = ytd[-1]
    by_period: dict[str, dict[str, float]] = {m: dict(v) for m, v in flows.items()}
    stocks_spec = dict(spec.get("stocks") or {})
    stock_cells = _sheet(sheets, stocks_spec.get("sheet"))
    if stock_cells is not None:
        for month, values in _stocks(stock_cells, stocks_spec, period).items():
            for metric, v in values.items():
                by_period.setdefault(month, {}).setdefault(metric, v)
    numbers = by_period.pop(period, {})
    if not numbers:
        raise BookError("в книге нет чисел её периода")
    return {"period": period, "numbers": numbers,
            "comparative": {m: v for m, v in sorted(by_period.items()) if v},
            "months_column": (SUFFIX_MONTH, period) in columns.values()}
