"""Факты эмитента (data/facts/*.json) — ВТБ: факты прежнего якоря + листы квартала этапа 1 из папки передачи.

Запуск из корня репозитория (нужна папка передачи; в CI не запускается — JSON закоммичены):

    BANK_HANDOFF_DIR=<папка передачи> python -B ops/tools/build_facts.py            # переписать data/facts
    BANK_HANDOFF_DIR=<папка передачи> python -B ops/tools/build_facts.py --check    # сверить с data/facts, не писать
    BANK_HANDOFF_DIR=<папка передачи> python -B ops/tools/build_facts.py --out DIR  # записать в DIR
    … build_facts.py --anchor 2026Q4 --out DIR [--base DIR] [--report ОТЧЁТ.json]   # якорь — следующий квартал
    python -B ops/tools/build_facts.py --report ОТЧЁТ.json --facts DIR              # отчёт квартала из готовых фактов
    python -B ops/tools/build_facts.py --expected ОТЧЁТ.json --out DIR [--facts DIR]  # отчёт квартала → факты (без папки)

КАК СОБИРАЕТ. Сборка «катится»: факты якоря К = факты прежнего якоря (К − 1) + листы квартала К. История (строки
баланса, ОПУ, упр. метрик, мостов, капитала и дивидендов до К − 1) идёт из фактов прежнего якоря с их источниками;
квартал К — из листов квартала; правила, которые решения ведущего распространили на всю историю (остатки книг ЧПД
на концы кварталов, ROE банка по дням, стартовый реестр, мост C/I медианой), пересчитываются на каждом якоре.
Факты прежнего якоря — `--base КАТАЛОГ`; по умолчанию — data/facts, если они стоят на прежнем квартале, иначе
последний коммит истории git, где data/facts/anchor.json стоит на прежнем квартале (у `--check` на якоре фактов —
так и есть: на 3К2026 база — факты 2К2026 в истории). Ядро ВТБ стартовало с фактов 2К2026, собранных
build_draft_facts.py этапа 1 — это первая база цепочки.

Листы квартала К — каталог `stage1/facts-<К>/sheets/` папки передачи (конвейер этапа 1 квартала: work/parse_notes.py →
build_books.py → extract_supplement_<к>.py → nii_split_<к>.py; разбор PDF и xlsx — там, сборщик его не повторяет):
  documents.csv                      документы квартала (отчётность, файл эмитента, презентация): путь, заголовок, дата
  books_balances.csv, books_balances_history.csv   книги на концы кварталов (строки состава, знаки, источники)
  ifrs_notes_balances.csv            строки примечаний отчётности квартала (sha256 сверяется с файлом)
  supplement_<ММГГ>.csv              файл эмитента: ОПУ квартала, коэффициенты, строки баланса (sha256 сверяется)
  notes_<NM|FY><ГГГГ>_manual.csv     ручные выписки квартала с документом и страницей (суффиксы метрик: _q<к>, _<3к>m,
                                     _<мес> месяца после якоря)
  nii_split_q<к>.json                проценты книг квартала (правило листа потока nii)
  capital_forms_q<к>.csv             формы 0409135 банка и 0409805 группы (ряды сервера)
  capital_inputs.csv, npf_assets_fy.csv, insurance_liabilities.csv, funds_current_shares.csv, key_rate_quarterly.csv,
  at1_coupons.csv, one_offs.csv      входы прошлых лет и рынка (строки прежних кварталов — в листах прежних якорей)
  facts_notes.csv                    записки узлов квартала: слова, которых правилом не вывести (суждения, разбивки
                                     из текста отчёта), — узел, текст, документ и страница
  guidance_events.csv                события гайденса квартала: подтверждение без изменений, новый пункт
Кривая ОФЗ — primary/market/zcyc_quarter_ends_*.csv. Каждое число — узел {"v", "src"} (документ, страница или ячейка,
sha256) или {"v", "calc"}; sha256 документов листов пересчитывается по файлу и сверяется. Схема — data/facts/SCHEMA.md,
происхождение — docs/FACTS.md.

СОСТАВ — таблицы в начале файла: книги ЧПД (BOOKS: строки листа книг, роли, сегменты), строки ОПУ движка
(PNL_LINES, PNL_REPORTED), прочие активы (OTHER_ASSETS, постоянная часть OTHER_ASSETS_FIXED), капитал (EQUITY),
метрики ручного листа. Функции от квартала не зависят: следующий квартал — новые листы, не правка кода.

calendar.json и peers.json ведутся вручную (календари эмитента и ЦБ, отчёты аналогов): сборщик их не пишет.

Сверки печатаются; при расхождении сборка останавливается, файлы не пишутся: база — факты прежнего квартала; состав
книг (таблица 1) = листу книг; книги = строкам примечаний и файла эмитента; баланс якоря; проценты книг = ЧПД;
тождества ОПУ; фонды капитала по движению = строке баланса; мосты; дивиденды года.

`--report` пишет файл отчёта квартала якоря (`quarter-report/1`) — вход `ops/tools/reanchor.py --facts`.

`--expected` — сухой прогон перезаякоривания (docs/MODEL.md §15.2, docs/REANCHOR.md): факты следующего квартала
из фактов якоря (`--facts`, по умолчанию data/facts) и отчёта квартала — того же `quarter-report/1`, что пишет
`ops/tools/reanchor.py --expected` (ожидание модели). Папка передачи не нужна; пишет только в `--out`, и это не
data/facts: ожидание — не факт. Вторая, независимая от `reanchor.py` сборка фактов нового якоря: ядро обязано
прочесть из обеих одно состояние (`reanchor.py --compare-facts`).

Код выхода: 0 — собрано (или --check: файлы совпали); 1 — расхождение, ошибка сверки или нет папки.
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FACTS = REPO / "data" / "facts"

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ТАБЛИЦА 1. Книги ЧПД → строки состава листа книг (books_balances.csv: строки component книги, по началу подписи;
# знак — из листа). side — сторона баланса; segment — сегмент кредитной книги (стоимость риска, концы прошлого года);
# cite — откуда ссылка calc: "notes" — примечания отчётности (номер и страница из колонки source листа), "sup" — ячейки
# файла эмитента; judgement — суждение о составе, которое печатается в calc. Книга liquidity — только доходные
# размещения (решение ведущего B2): деньги, обязательные резервы и деньги НПФ из строк листа уходят в прочие активы
# (moved). Книги средств физлиц делятся долей текущих счетов презентации (лист funds_current_shares.csv).
# ══════════════════════════════════════════════════════════════════════════════════════════════════
BOOKS: dict[str, dict] = {
    "corp_loans": dict(name="Корпоративные кредиты", side="asset", segment="corporate", cite="notes",
                       rows=("финансирование текущей деятельности", "проектное финансирование", "финансовая аренда",
                             "кредиты ЮЛ по справедливой стоимости", "кредиты ЮЛ через прочий совокупный доход",
                             "кредиты ЮЛ через прочий совокупный доход, в залоге")),
    "mortgage": dict(name="Ипотека", side="asset", segment="retail", cite="notes",
                     rows=("ипотечные кредиты (АС)", "ипотечные кредиты, заложенные", "кредиты ФЛ через прочий совокупный доход",
                           "кредиты ФЛ через прочий совокупный доход, в залоге"),
                     judgement="кредиты ФЛ через ПСД отнесены к ипотеке — суждение 2К2026"),
    "consumer_loans": dict(name="Потребительские кредиты", side="asset", segment="retail", cite="notes",
                           rows=("потребительские", "кредиты на покупку", "кредитные карты")),
    "securities": dict(name="Долговые бумаги", side="asset", cite="notes",
                       rows=("торговые долговые бумаги", "торговые долговые бумаги, в залоге", "инвестиционные долговые через прочий",
                             "то же, в залоге", "инвестиционные долговые через прибыль", "инвестиционные долговые по АС",
                             "резерв по ним", "инвестиционные долговые по АС, в залоге", "резерв по ним (репо)",
                             "минус торговые бумаги НПФ", "минус инвестиционные бумаги НПФ")),
    "liquidity": dict(name="Ликвидность", side="asset", cite="b2",
                      rows=("средства в банках", "обратное репо с юридическими", "обратное репо с физическими",
                            "минус средства НПФ в банках"),
                      moved=("денежные средства и краткосрочные активы", "обязательные резервы", "минус денежные средства НПФ")),
    "retail_current": dict(name="Текущие счета физлиц", side="liability", cite="share", rows=("средства физических лиц × доля",)),
    "retail_term": dict(name="Срочные средства физлиц", side="liability", cite="share", rows=("средства физических лиц × (1",)),
    "corp_funds": dict(name="Средства юрлиц", side="liability", cite="notes",
                       rows=("государственные органы власти", "прочие юридические лица", "договоры репо в средствах клиентов")),
    "wholesale": dict(name="Оптовое фондирование", side="liability", cite="sup",
                      rows=("средства банков", "прочие заёмные средства", "выпущенные долговые", "субординированная задолженность")),
}
SECURITIES, LIQUIDITY, RETAIL_CURRENT, RETAIL_TERM = "securities", "liquidity", "retail_current", "retail_term"
# Строки примечаний (ifrs_notes_balances.csv) для частей книг и сверок: книга долговых бумаг по категориям, обратное
# репо, средства клиентов, резерв по кредитам (юрлица, физлица, заложенные).
NOTE_LINES = dict(
    trading_debt="trading_debt", trading_debt_repo="trading_debt_repo", fvoci_debt="inv_fvoci_debt",
    fvoci_repo="inv_fvoci_debt_repo", fvtpl_debt="inv_fvtpl_debt", ac_debt="inv_ac_debt", ac_ecl="inv_ac_ecl",
    ac_repo="inv_ac_debt_repo", ac_repo_ecl="inv_ac_repo_ecl", revrepo_corp="loans_corp_revrepo",
    revrepo_retail="loans_retail_revrepo", dep_ind="dep_ind", dep_gov="dep_gov", dep_corp_other="dep_corp_other",
    dep_repo="dep_repo", dtb_repo="dtb_repo", ob_cb="ob_cb_total",
    trading_equity="trading_equity", trading_equity_repo="trading_equity_repo", fvoci_equity="inv_fvoci_equity",
    fvtpl_equity="inv_fvtpl_equity")
ALLOWANCE = (("loans_corp_ecl", "юридические лица"), ("loans_retail_ecl", "физические лица"),
             ("loans_retail_pledged_ecl", "заложенные"))   # резерв по кредитам АС (в отчёте — со знаком минус)
NPF_LINES = ("cash", "trading", "dfb", "loans", "investments", "other")   # строки активов НПФ годового отчёта (прим. 6)

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ТАБЛИЦА 2. Строки ОПУ движка → строки файла эмитента (supplement_<ММГГ>.csv, колонка квартала); строки прибыли
# (PNL_REPORTED) — отчётные. Прочие строки движка — расчётные: insurance_net (выручка + расходы по страхованию),
# misc_net (остаток до прибыли до налога; что внутри — записка квартала), noncore_net (непрофильного блока нет), pbt
# (с убытком дочерних компаний для перепродажи: ni = pbt + tax), ni_ordinary (без купонов AT1).
# ══════════════════════════════════════════════════════════════════════════════════════════════════
PNL_LINES: dict[str, str] = {"nii": "nii", "fees_net": "fees_net", "llp_debt_fa": "llp_debt_fa", "opex": "opex_staff_admin"}
PNL_REPORTED = {"pbt": "pbt", "tax": "tax", "np_after_tax": "np_after_tax", "np_resale_subs": "np_resale_subs", "ni": "np"}
PNL_INSURANCE = ("ins_revenue", "ins_expense")
PNL_OTHER_PROVISIONS = ("llp_commitments", "prov_legal")
MGMT_PRINTED = ("nim", "cor", "cir", "roe", "roa")   # коэффициенты банка квартала (проценты документа → доли)
MGMT_COPIED = ("cor_corp", "cor_retail", "op_np", "op_equity", "cost_of_funding", "asset_yield", "clients_total",
               "clients_active")                # нераскрытое по кварталам: узел прежнего квартала
MGMT_ANCHOR = (("loans_gross", "loans_gross_kpi"), ("loans_corp_gross", "loans_corp_kpi"),
               ("loans_retail_gross", "loans_retail_kpi"), ("funds_corp", "funds_corp_kpi"),
               ("funds_retail", "funds_retail_kpi"))   # остатки в определении банка (ручной лист квартала)

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ТАБЛИЦА 3. Прочие активы и обязательства: части — строки outside_part листа книг (в порядке листа) и строки книг,
# вынесенные правилом B2; постоянная часть прочих активов (решение ведущего № 3) — метрики ручного листа.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
OTHER_ASSETS = "other_assets"
OTHER_LIABILITIES = "other_liabilities"
OTHER_ASSETS_FIXED = (("dta", "отложенный налоговый актив"), ("goodwill", "гудвил"),
                      ("associates", "вложения в ассоциированные компании и совместные предприятия"))
INTANGIBLES = (("intang_software", "программное обеспечение"), ("intang_wip", "программное обеспечение в процессе разработки"),
               ("intang_rights", "прочие права"), ("intang_brands", "фирменные наименования и товарные знаки"))
EQUITY = {"total": "eq_total", "shareholders": "eq_shareholders", "at1": "eq_perpetual", "nci": "eq_nci",
          "share_capital": "eq_share_capital", "share_premium": "eq_share_premium", "treasury_cost": "eq_treasury",
          "other_funds": "eq_other_funds", "retained_earnings": "eq_retained"}
EQUITY_KEPT_CALC = ("at1", "treasury_cost")      # calc этих узлов — слова прежнего якоря

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Параметры сборщика (не допущения модели): листы, начала рядов, решения ведущего, на которые ссылаются тексты.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
STAGE = "stage1/facts-{period}"                  # каталог конвейера квартала в папке передачи; листы — STAGE/sheets
SHEET_SUPPLEMENT = "supplement_{mm}{yy}.csv"
SHEET_MANUAL = "notes_{ytd}_manual.csv"          # ytd: 9m2026; год — fy2026
SHEET_SPLIT, SHEET_SPLIT_CSV = "nii_split_q{k}.json", "nii_split_q{k}.csv"
SHEET_FORMS = "capital_forms_q{k}.csv"
SPLIT_SCRIPT = "nii_split_q{k}.py"
CURVE_FILE = "primary/market/zcyc_quarter_ends_2024_2026.csv"
CURVE_NODES = ("1", "3", "5", "10")
RULES_FROM = "2К2026"           # квартал, на котором приняты правила книг и состава (первый якорь книги)
RULES_FROM_PERIOD = "2026Q2"
RATES_CARRY_FROM = "2026Q3"     # с этого якоря (первый после книги 1.0) ставки книг активов несут и проценты вне книг
FLOATING_FROM = "2024-12-31"    # рублёвые бессрочные сверх остатка на эту дату — выпуски «ключевая + 5 %» (прим. 23)
FLOATING_SPREAD = 0.05
# Решения ведущего, на которые ссылаются тексты фактов (docs: vtb-850-handoff/reanchor-2026Q3/DECISIONS-1.0*.md).
DECISION_B2 = "решение B2"
DECISION_FIXED = "решение ведущего № 3, раздел 2"
DECISION_PRINTED_RATIOS = "Р6 (решение ведущего 04.11.2026)"   # нормативы группы, напечатанные эмитентом, до формы 0409805
DECISION_CIR_MEDIAN = "РЕШЕНИЕ ВЕДУЩЕГО Р4 (книга 1.0, 04.11.2026)"   # мост C/I — медиана по окну
BRIDGE_MEDIAN = ("cir",)        # блоки моста, у которых значение — медиана gap по окну (правило 2К2026, Р4)
MONTH_TAGS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
COUNT_WORDS = {2: "двух", 3: "трёх", 4: "четырёх", 5: "пяти", 6: "шести", 7: "семи", 8: "восьми", 9: "девяти", 10: "десяти"}

BUILT = ("anchor", "balance", "nii_books", "pnl_quarterly", "capital", "shares", "dividends",
         "bridge_mgmt_ifrs", "bridge_ras_ifrs", "mgmt_quarterly", "guidance")
MANUAL = ("calendar", "peers")
REPORT_SCHEMA = "quarter-report/1"


class BuildError(RuntimeError):
    """Нет листа, строки или документа; не сошлась сверка."""


# ------------------------------------------------------------------ периоды

def q_parse(p: str) -> tuple[int, int]:
    return int(p[:4]), int(p[5])


def q_range(a: str, b: str) -> list[str]:
    y, k = q_parse(a)
    out = []
    while f"{y}Q{k}" <= b:
        out.append(f"{y}Q{k}")
        y, k = (y + 1, 1) if k == 4 else (y, k + 1)
    return out


def q_end(p: str) -> dt.date:
    y, k = q_parse(p)
    return dt.date(y, 3 * k, 31 if k in (1, 4) else 30)


def q_prev(p: str) -> str:
    y, k = q_parse(p)
    return f"{y - 1}Q4" if k == 1 else f"{y}Q{k - 1}"


def q_next(p: str) -> str:
    y, k = q_parse(p)
    return f"{y + 1}Q1" if k == 4 else f"{y}Q{k + 1}"


def q_days(p: str) -> int:
    return (q_end(p) - q_end(q_prev(p))).days


def ifrs_q(p: str) -> str:
    """2026Q2 → 2Q2026 (обозначение листов МСФО этапа 1)."""
    y, k = q_parse(p)
    return f"{k}Q{y}"


def d_ru(iso: str) -> str:
    """2026-03-31 → 31.03.2026 (даты в текстах calc)."""
    return dt.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")


def q_ru(p: str) -> str:
    """2026Q2 → 2К2026."""
    y, k = q_parse(p)
    return f"{k}К{y}"


def ytd_ru(p: str) -> str:
    """Нарастающий итог по квартал p в текстах: 2026Q3 → 9М2026; 2026Q4 → 12М2026."""
    y, k = q_parse(p)
    return f"{3 * k}М{y}"


@dataclass(frozen=True)
class Anchor:
    """Якорь сборки и всё, что из него выводится (перечень — data/facts/SCHEMA.md §3)."""

    period: str                            # 2026Q3

    def __post_init__(self):
        if not re.fullmatch(r"\d{4}Q[1-4]", self.period):
            raise BuildError(f"якорь {self.period!r}: нужен квартал вида ГГГГQк (год, Q, номер квартала)")

    @property
    def year(self) -> int:
        return q_parse(self.period)[0]

    @property
    def quarter(self) -> int:
        return q_parse(self.period)[1]

    @property
    def date(self) -> str:                 # конец квартала якоря
        return q_end(self.period).isoformat()

    @property
    def open_date(self) -> str:            # конец прошлого квартала — начало квартала якоря
        return q_end(q_prev(self.period)).isoformat()

    @property
    def prev_year_end(self) -> str:
        return f"{self.year - 1}-12-31"

    @property
    def ytd(self) -> str:                  # нарастающий итог якоря в листах МСФО: 9M2026; год — FY2026
        return f"FY{self.year}" if self.quarter == 4 else f"{3 * self.quarter}M{self.year}"

    @property
    def ytd_ru(self) -> str:               # то же в текстах: 9М2026; год — 12М2026
        return ytd_ru(self.period)

    @property
    def year_quarters(self) -> list[str]:  # отчётные кварталы года якоря
        return [f"{self.year}Q{k}" for k in range(1, self.quarter + 1)]

    @property
    def stage(self) -> str:                # каталог листов квартала в папке передачи
        return STAGE.format(period=self.period)

    @property
    def tag_q(self) -> str:                # суффикс метрик ручного листа: поток квартала
        return f"q{self.quarter}"

    @property
    def tag_ytd(self) -> str:              # суффикс метрик ручного листа: нарастающий итог
        return f"{3 * self.quarter}m"

    @property
    def tag_next_month(self) -> str:       # суффикс метрик ручного листа: первое число после якоря
        return MONTH_TAGS[q_end(self.period).month % 12]

    @property
    def next_day(self) -> str:             # первое число после якоря (дата форм Банка России)
        return (q_end(self.period) + dt.timedelta(days=1)).isoformat()


def default_anchor() -> str:
    """Якорь по умолчанию — квартал закоммиченных фактов (data/facts/anchor.json)."""
    path = FACTS / "anchor.json"
    if not path.exists():
        raise BuildError("нет data/facts/anchor.json — задайте якорь аргументом --anchor")
    return str(json.loads(path.read_text(encoding="utf-8"))["period"])


# ------------------------------------------------------------------ числа в текстах

def ru(x: float, n: int = 1) -> str:
    """Число для текстов calc (форма листов этапа 1): запятая, минус — знаком «−», без разделения тысяч."""
    return (("%." + str(n) + "f") % x).replace(".", ",").replace("-", "−")


def ruk(x: float, n: int = 1) -> str:
    """То же с пробелом между тысячами: 1 408,2."""
    return f"{x:,.{n}f}".replace(",", " ").replace(".", ",").replace("-", "−")


def rud(x: float, n: int = 1) -> str:
    """С пробелом между тысячами и точкой: 25 314.9 (форма записок решений ведущего)."""
    return f"{x:,.{n}f}".replace(",", " ")


def pct(x: float, n: int = 2) -> str:
    return ru(x * 100, n) + " %"


def r1(x: float | None) -> float | None:
    return None if x is None else round(x + 0.0, 1)


def r3(x: float | None) -> float | None:
    return None if x is None else round(x + 0.0, 3)


def r6(x: float | None) -> float | None:
    return None if x is None else round(x + 0.0, 6) + 0.0   # + 0.0: минус ноль не пишется


def r9(x: float | None) -> float | None:
    return None if x is None else round(x + 0.0, 9) + 0.0   # точность файла отчёта квартала


def shares_words(n: float) -> str:
    """12927766417 → 12 927 766 417 (штуки в текстах)."""
    return f"{int(round(n)):,}".replace(",", " ")


# ------------------------------------------------------------------ узлы

def node(v, src: str | None = None, calc: str | None = None, **extra) -> dict:
    """Узел факта. Число без источника и без формулы — ошибка сборки."""
    if v is None:
        raise BuildError(f"узел без значения: используйте na(причина) ({src or calc})")
    if not (src or calc):
        raise BuildError(f"число {v} без src и calc")
    out = {"v": v}
    if src:
        out["src"] = src
    if calc:
        out["calc"] = calc
    out.update(extra)
    return out


def est(v, calc: str, src: str | None = None, rng=None, **extra) -> dict:
    """Узел-оценка: пометка estimated и диапазон (если есть) — после остальных полей."""
    out = node(v, src, calc, estimated=True, **extra)
    if rng is not None:
        out["range"] = list(rng)
    return out


def na(reason: str, **extra) -> dict:
    """Нераскрытое: null с причиной (не ноль)."""
    return {"v": None, "calc": reason, **extra}


def page_words(page: str) -> str:
    """«6» → «с. 6»; «13 и 15» → «с. 13 и 15»; адрес «Лист!Ячейка» и слова — как есть."""
    page = str(page or "").strip()
    return f"с. {page}" if re.fullmatch(r"\d+(?:\s*(?:,|и|–|-)\s*\d+)*", page) else page


def put(obj: dict, dotted: str, value) -> None:
    *head, last = dotted.split(".")
    for part in head:
        obj = obj.setdefault(part, {})
    obj[last] = value


def dig(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def books_of(side: str | None = None, *, loans: bool = False) -> list[str]:
    if loans:
        return [b for b, s in BOOKS.items() if s.get("segment")]
    return [b for b, s in BOOKS.items() if side is None or s["side"] == side]


# ------------------------------------------------------------------ листы квартала

def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise BuildError(f"нет листа {path.name} ({path.parent.parent.name}/{path.parent.name}/)")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class Ctx:
    """Якорь, факты прежнего якоря, листы квартала, реестр документов и сверки."""

    def __init__(self, root: Path, anchor: Anchor, base: dict[str, dict]):
        self.root, self.a, self.base = root, anchor, base
        self.prev = Anchor(q_prev(anchor.period))
        self.D1, self.D0 = anchor.date, self.prev.date
        self.days = q_days(anchor.period)
        self.checks: list[tuple[str, bool, str]] = []
        self._sha: dict[str, str] = {}
        self.sheets = root / anchor.stage / "sheets"
        if not self.sheets.is_dir():
            raise BuildError(f"нет листа якоря {anchor.period}: нет каталога {anchor.stage}/sheets в папке передачи")
        if str(base["anchor"]["period"]) != self.prev.period:
            raise BuildError(f"база — факты {base['anchor']['period']}, а якорю {anchor.period} нужны факты прежнего "
                             f"квартала {self.prev.period} (--base)")
        self.check("база — факты прежнего квартала", True, f"{self.prev.period} ({self.D0})")
        a = anchor
        self.docs = {r["role"]: r for r in self.rows("documents.csv")}
        for role in ("fs", "sup", "pres"):
            if role not in self.docs:
                raise BuildError(f"documents.csv: нет документа роли {role}")
        fs = self.docs["fs"]["file"]
        self.notes: dict[tuple[str, str], tuple[float, str]] = {}
        for r in self.rows("ifrs_notes_balances.csv"):
            if r["doc"] == fs:
                self.verify(r["doc"], r.get("sha256"))
                self.notes[(r["metric"], r["period"])] = (float(r["value"]), r["page"])
        end = q_end(a.period)
        self.sup_name = SHEET_SUPPLEMENT.format(mm=f"{end.month:02d}", yy=f"{end.year % 100:02d}")
        self.sup: dict[tuple[str, str], tuple[float, str]] = {}
        for r in self.rows(self.sup_name):
            self.verify(r["doc"], r.get("sha256"))
            self.sup[(r["metric"], r["period"])] = (float(r["value"]), r["cell"])
        self.manual_name = SHEET_MANUAL.format(ytd=("fy" if a.quarter == 4 else a.tag_ytd) + str(a.year))
        self.man = {r["metric"]: (float(r["value"]), r["doc"], r["page"], r["note"]) for r in self.rows(self.manual_name)}
        self.forms = {(r["metric"], r["date"]): (float(r["value"]), r["source"])
                      for r in self.rows(SHEET_FORMS.format(k=a.quarter))}
        split = self.sheets / SHEET_SPLIT.format(k=a.quarter)
        if not split.exists():
            raise BuildError(f"нет листа {split.name} ({a.stage}/sheets/)")
        self.split = json.loads(split.read_text(encoding="utf-8"))
        self.books_rows = self.rows("books_balances.csv")
        self.hist_rows = self.rows("books_balances_history.csv")
        self.key = {r["period"]: r for r in self.rows("key_rate_quarterly.csv")}
        self.cap_inputs = {(r["metric"], r["period"]): r for r in self.rows("capital_inputs.csv")}
        self.texts = {r["node"]: r for r in self.rows("facts_notes.csv")}
        self.used_texts: set[str] = set()

    # --- листы и документы
    def rows(self, name: str) -> list[dict]:
        return read_csv(self.sheets / name)

    def sha(self, rel: str) -> str:
        if rel not in self._sha:
            path = self.root / rel
            if not path.is_file():
                raise BuildError(f"нет документа {rel} в папке передачи")
            self._sha[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return self._sha[rel]

    def verify(self, rel: str, sha: str | None) -> None:
        if sha and self.sha(rel) != sha:
            raise BuildError(f"{Path(rel).name}: sha256 файла {self.sha(rel)[:16]}… не совпал с листом {sha[:16]}…")

    def src(self, role_or_rel: str, place) -> str:
        rel = self.docs[role_or_rel]["file"] if role_or_rel in self.docs else role_or_rel
        return f"{Path(rel).name}, {page_words(str(place))}, sha256 {self.sha(rel)[:16]}"

    def check(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append((name, bool(ok), detail))

    # --- значения
    def nt(self, key: str, date: str | None = None) -> float:
        metric = NOTE_LINES.get(key, key)
        try:
            return self.notes[(metric, date or self.D1)][0]
        except KeyError:
            raise BuildError(f"ifrs_notes_balances.csv: нет строки {metric} на {date or self.D1} отчёта якоря") from None

    def nt_or0(self, key: str) -> float:
        metric = NOTE_LINES.get(key, key)
        return self.notes.get((metric, self.D1), (0.0,))[0]

    def nsrc(self, key: str) -> str:
        metric = NOTE_LINES.get(key, key)
        if (metric, self.D1) not in self.notes:
            raise BuildError(f"ifrs_notes_balances.csv: нет строки {metric} на {self.D1} отчёта якоря")
        return self.src("fs", self.notes[(metric, self.D1)][1])

    def sp(self, metric: str, per: str | None = None) -> float:
        try:
            return self.sup[(metric, per or self.D1)][0]
        except KeyError:
            raise BuildError(f"{self.sup_name}: нет строки {metric} за {per or self.D1}") from None

    def sup_cell(self, metric: str, per: str | None = None) -> str:
        if (metric, per or self.D1) not in self.sup:
            raise BuildError(f"{self.sup_name}: нет строки {metric} за {per or self.D1}")
        return self.sup[(metric, per or self.D1)][1]

    def ssrc(self, metric: str, per: str | None = None) -> str:
        return self.src("sup", self.sup_cell(metric, per))

    def g(self, metric: str) -> float:      # строка ОПУ квартала якоря
        return self.sp(metric, self.a.period)

    def gs(self, metric: str) -> str:
        return self.ssrc(metric, self.a.period)

    def man_v(self, metric: str) -> float:
        try:
            return self.man[metric][0]
        except KeyError:
            raise BuildError(f"{self.manual_name}: нет строки {metric}") from None

    def man_row(self, metric: str) -> tuple[float, str, str, str]:
        """Строка ручного листа: (значение, документ, страница или ячейка, записка)."""
        if metric not in self.man:
            raise BuildError(f"{self.manual_name}: нет строки {metric}")
        return self.man[metric]

    def msrc(self, metric: str) -> str:
        _, doc, page, _ = self.man_row(metric)
        return self.src(doc, page)

    def form(self, metric: str, date: str) -> tuple[float, str]:
        try:
            return self.forms[(metric, date)]
        except KeyError:
            raise BuildError(f"{SHEET_FORMS.format(k=self.a.quarter)}: нет строки {metric} на {date}") from None

    def key_row(self, period: str, field: str) -> float:
        row = self.key.get(period) or {}
        if not row.get(field):
            raise BuildError(f"key_rate_quarterly.csv: нет {field} за {period}")
        return float(row[field])

    def cap_in(self, metric: str, period: str) -> float:
        try:
            return float(self.cap_inputs[(metric, period)]["value"])
        except KeyError:
            raise BuildError(f"capital_inputs.csv: нет строки {metric} на {period}") from None

    def cap_in_src(self, metric: str, period: str) -> str:
        r = self.cap_inputs[(metric, period)]
        return self.src(r["doc"], r["page"])

    def text(self, key: str) -> str:
        """Записка узла квартала (facts_notes.csv): слова, которых правилом не вывести."""
        try:
            row = self.texts[key]
        except KeyError:
            raise BuildError(f"facts_notes.csv: нет записки {key} (квартал {self.a.period})") from None
        self.used_texts.add(key)
        return row["text"]

    def text_src(self, key: str) -> str | None:
        row = self.texts.get(key)
        if row is None:
            raise BuildError(f"facts_notes.csv: нет записки {key} (квартал {self.a.period})")
        self.used_texts.add(key)
        if not row.get("doc"):
            return None
        parts = [self.src(row["doc"], row["page"])]
        if row.get("extra"):
            parts.append(row["extra"])
        return "; ".join(parts)

    # --- лист книг
    def book_rows(self, rows: list[dict], book: str, kind: str = "component") -> list[dict]:
        return [r for r in rows if r["book"] == book and r["row_type"] == kind]

    def item(self, rows: list[dict], book: str, start: str) -> dict:
        for r in self.book_rows(rows, book):
            if r["item"].startswith(start):
                return r
        raise BuildError(f"лист книг: у книги {book} нет строки «{start}…»")

    def book_row(self, rows: list[dict], book: str) -> dict:
        for r in rows:
            if r["row_type"] == "book" and r["book"] == book:
                return r
        raise BuildError(f"лист книг: нет строки book {book}")


# ------------------------------------------------------------------ активы НПФ (вне книг)

class Npf:
    """Активы НПФ на дату якоря: факт годового отчёта на конец года; на промежуточную дату — оценка: обязательства НПФ по
    пенсионному страхованию × (активы / обязательства на конец прошлого года) × доля строки (правило листа книг)."""

    def __init__(self, c: Ctx):
        self.c = c
        a = c.a
        rows = c.rows("npf_assets_fy.csv")
        self.fact = {r["line"]: (float(r["value"]), r) for r in rows if r["date"] == c.D1}
        fy = [r for r in rows if r["date"] == a.prev_year_end]
        if not self.fact and not fy:
            raise BuildError(f"npf_assets_fy.csv: нет активов НПФ ни на {c.D1}, ни на {a.prev_year_end}")
        self.fy = {r["line"]: float(r["value"]) for r in fy}
        self.fy_row = fy[0] if fy else None
        self.liab_fy = next((float(r["value"]) for r in c.rows("insurance_liabilities.csv")
                             if r["metric"] == "pension" and r["date"] == a.prev_year_end), None)
        if not self.fact and self.liab_fy is None:
            raise BuildError(f"insurance_liabilities.csv: нет обязательств НПФ на {a.prev_year_end}")
        self.liab = c.man_v("pension_liab") if not self.fact else None

    def line(self, name: str) -> float:
        if self.fact:
            return self.fact[name][0]
        tot = sum(self.fy[k] for k in NPF_LINES)
        k = tot / self.liab_fy
        return round(self.liab * k * self.fy[name] / tot, 1)

    def note(self) -> str:
        c = self.c
        if self.fact:
            r = next(iter(self.fact.values()))[1]
            return f"активы НПФ на {d_ru(c.D1)} — факт: {Path(r['doc']).name}, {page_words(r['page'])}"
        tot = sum(self.fy[k] for k in NPF_LINES)
        _, doc, page, words = c.man_row("pension_liab")
        note = re.search(r"прим\. \d+", words)
        return (f"оценка активов НПФ на {d_ru(c.D1)}: обязательства НПФ по пенсионному страхованию {ruk(self.liab)} "
                f"({note.group(0) if note else 'прим.'}, {page_words(page)}) × отношение активов к обязательствам на "
                f"{d_ru(c.a.prev_year_end)} ({ruk(tot)} / {ruk(self.liab_fy)}) × доля строки; факт на "
                f"{d_ru(c.a.prev_year_end)} — {Path(self.fy_row['doc']).name}, {page_words(self.fy_row['page'])}")


# ------------------------------------------------------------------ balance.json

def cite_notes(c: Ctx, rows: list[dict], date: str) -> str:
    """Ссылка calc книги на примечания: номера и страницы отчёта якоря из колонки source листа книг."""
    notes, pages = [], []
    for r in rows:
        m = re.match(r"(прим\. \d+):", r["source"])
        p = re.search(re.escape(date) + r" — [^,;]+, с\. (\d+)", r["source"])
        if not (m and p):
            continue
        n = m.group(1).split()[1]
        if n not in notes:
            notes.append(n)
            pages.append(p.group(1))
    if not notes:
        raise BuildError(f"лист книг: у строк нет ссылки на примечание на {date}")
    return f"прим. {' и '.join(notes)}, с. {' и '.join(pages)}"


def cite_sup(c: Ctx, rows: list[dict]) -> str:
    """Ссылка calc книги на ячейки файла эмитента (колонка якоря — последняя в диапазоне колонок листа)."""
    sheet, cells = None, []
    for r in rows:
        m = re.search(r"лист «([^»]+)», строка (\d+) \(колонки \w+…(\w+)\)", r["source"])
        if not m:
            raise BuildError(f"лист книг: строка «{r['item']}» без ячейки файла эмитента")
        sheet = m.group(1)
        cells.append(m.group(3) + m.group(2))
    return f"файл эмитента {c.a.ytd_ru}, «{sheet}», {', '.join(cells)}"


def book_estimated(row: dict) -> bool:
    """Книга-оценка: в строке book листа — «оценки» внутри или класс «В»."""
    return "оценк" in row["class"] or row["class"].startswith("В")


def share_words(c: Ctx, share: float, row: dict, before: list[dict]) -> str:
    """Слова о доле текущих счетов: слайд презентации квартала и прежние значения."""
    vals = sorted({round(float(r["current_share"]) * 100) for r in before})
    now = round(share * 100)
    if len(vals) == 1:
        n = len(before)
        where = "прежней дате" if n == 1 else f"{COUNT_WORDS.get(n, str(n))} прежних датах"
        tail = f" против {vals[0]} % на {where}"
    elif vals:
        tail = " против " + ", ".join(f"{round(float(r['current_share']) * 100)} % на {d_ru(r['date'])}" for r in before)
    else:
        tail = ""
    return f"слайд {row['page']} презентации {c.a.ytd_ru}: {now} % на {d_ru(c.D1)}{tail}"


def balance_note(note: str, c: Ctx) -> str:
    """Заметка balance.json: строки баланса — из файла эмитента квартала; хвост — якорь квартала."""
    sup = Path(c.docs["sup"]["file"]).name
    note = re.sub(r"(строки баланса — из ).*?(, состав)", lambda m: f"{m.group(1)}файла эмитента {c.a.ytd_ru} ({sup}){m.group(2)}",
                  note, count=1)
    note = re.sub(r" \[якорь \d{4}Q[1-4]:[^\]]*\]$", "", note)
    return note + f" [якорь {c.a.period}: те же строки и правила книг на отчётности за {c.a.ytd_ru} — {c.a.stage}]"


def history_books(c: Ctx, date: str) -> dict:
    """Остатки девяти книг ЧПД на конец квартала date (вход весов решателя передачи средним окна): строка book листа
    истории книг; ликвидность — доходные размещения по строкам состава (решение B2)."""
    col = "bal_" + date
    sheet = f"sheets/books_balances_history.csv (якорь {c.a.period})"
    if not c.hist_rows or col not in c.hist_rows[0]:
        raise BuildError(f"books_balances_history.csv: нет колонки {col} — лист истории книг покрывает все концы кварталов "
                         "истории баланса")
    out = {}
    for b in BOOKS:
        if b == LIQUIDITY:
            parts = [float(c.item(c.hist_rows, b, s)[col]) for s in BOOKS[b]["rows"]]
            v = round(parts[0] + parts[1] + parts[2] - parts[3], 1)
            out[b] = {"v": v, "calc": (f"книга ликвидности — только доходные размещения ({DECISION_B2}): средства в банках "
                                       f"{ru(parts[0])} + обратное репо с юридическими лицами {ru(parts[1])} + обратное репо с "
                                       f"физическими лицами {ru(parts[2])} − средства НПФ в банках {ru(parts[3])}; лист {sheet}, "
                                       f"строки состава книги {LIQUIDITY}"), "estimated": True}
            continue
        row = c.book_row(c.hist_rows, b)
        out[b] = {"v": round(float(row[col]), 1), "calc": f"лист {sheet}: строка book {b} на {date} — сумма строк состава"}
        if book_estimated(row):
            out[b]["estimated"] = True
    return out


def prev_year_end(c: Ctx) -> dict:
    """Кредитные книги по сегментам на конец прошлого года (= прежний якорь, четвёртый квартал): остатки книг фактов
    прежнего якоря; обратное репо — строки ликвидности листа истории книг; в определении банка — остатки упр. отчёта
    прежнего якоря (`mgmt_quarterly.anchor_balances`)."""
    P, ab = c.base["balance"], c.base["mgmt_quarterly"]["anchor_balances"]
    col, on = "bal_" + c.D0, d_ru(c.D0)
    out = {"as_of": c.D0}
    for seg, start, kpi, words in (("corporate", "обратное репо с юридическими", "loans_corp_gross", "юридическим лицам"),
                                   ("retail", "обратное репо с физическими", "loans_retail_gross", "физическим лицам")):
        names = [b for b in books_of(loans=True) if BOOKS[b]["segment"] == seg]
        rr = float(c.item(c.hist_rows, LIQUIDITY, start)[col])
        what = (f"книга {names[0]} на {on} (тот же состав, без" if len(names) == 1 else
                f"книги {' + '.join(names)} на {on} (без")
        out[f"loans_{seg}"] = node(r1(sum(P["books"][b]["v"] for b in names)),
                                   calc=f"{what} обратного репо {ru(rr)}); в определении банка кредиты {words} — {ruk(ab[kpi]['v'])}")
    return out


def dividends_payable_value(c: Ctx) -> float:
    """Дивиденды к выплате на якоре: решения истории дивидендов с днём решения не позже якоря и сроком выплаты позже."""
    out = 0.0
    for h in c.base["dividends"].get("history") or []:
        decided, paid = str(h.get("decided_date") or ""), str(h.get("pay_date") or "")
        if decided and decided <= c.D1 < (paid or "9999"):
            pool = h.get("pool_declared") or h.get("pool_ordinary") or {}
            out += float(pool.get("v") or 0.0)
    return r1(out)


def build_balance(c: Ctx) -> tuple[dict, dict]:
    P = c.base["balance"]
    b = copy.deepcopy(P)
    D1, D0 = c.D1, c.D0
    b["as_of"] = D1
    b["note"] = balance_note(P["note"], c)
    npf = Npf(c)
    NPF_NOTE = npf.note()
    S = f"лист sheets/books_balances.csv (якорь {c.a.period}): "
    col = "bal_" + D1
    rows = c.books_rows
    # --- состав книг (таблица 1) против листа книг
    for bk, spec in BOOKS.items():
        have = [r["item"] for r in c.book_rows(rows, bk)]
        want = [c.item(rows, bk, s)["item"] for s in spec["rows"] + spec.get("moved", ())]
        ok = sorted(have) == sorted(want) and len(set(want)) == len(want)
        c.check(f"состав книг (таблица 1) = листу книг: {bk}", ok, f"{len(want)} строк" if ok else f"лист: {have}; таблица: {want}")
    comp = {bk: [c.item(rows, bk, s) for s in spec["rows"]] for bk, spec in BOOKS.items()}

    def val(r: dict) -> float:
        return float(r[col])

    books, calc = {}, {}
    for bk in ("corp_loans", "mortgage", "consumer_loans", "corp_funds", "wholesale"):
        rs = comp[bk]
        books[bk] = r1(sum(float(r["sign"] or 1) * val(r) for r in rs))
        cite = cite_notes(c, rs, D1) if BOOKS[bk]["cite"] == "notes" else cite_sup(c, rs)
        if BOOKS[bk].get("judgement"):
            cite += "; " + BOOKS[bk]["judgement"]
        calc[bk] = S + "; ".join(f"{r['item']} {ru(val(r))}" for r in rs) + f" ({cite})"
    rs = comp[SECURITIES]
    npf_tr, npf_inv = npf.line("trading"), npf.line("investments")
    npf_dfb, npf_cash = npf.line("dfb"), npf.line("cash")
    sec_lines = {k: (c.nt_or0(k) if k == "trading_debt_repo" else c.nt(k))
                 for k in ("trading_debt", "trading_debt_repo", "fvoci_debt", "fvoci_repo", "fvtpl_debt", "ac_debt", "ac_ecl",
                           "ac_repo", "ac_repo_ecl")}
    books[SECURITIES] = r1(sum(sec_lines.values()) - npf_tr - npf_inv)
    sheet_sec = [val(r) for r in rs]
    c.check("книга долговых бумаг: строки листа книг = примечаниям и оценке НПФ",
            all(abs(x - y) < 0.051 for x, y in zip(sheet_sec, list(sec_lines.values()) + [npf_tr, npf_inv])),
            ", ".join(ru(x) for x in sheet_sec))
    calc[SECURITIES] = S + "; ".join(f"{'− ' if float(r['sign'] or 1) < 0 else ''}{r['item']} {ru(val(r))}" for r in rs) \
        + f" ({cite_notes(c, rs, D1)})"
    revc, revr = c.nt("revrepo_corp"), c.nt("revrepo_retail")
    books[LIQUIDITY] = r1(c.sp("dfb_total") + revc + revr - npf_dfb)
    dep_ind = c.nt("dep_ind")
    shares_rows = [r for r in c.rows("funds_current_shares.csv") if r["segment"] == "retail"]
    share_row = next((r for r in shares_rows if r["date"] == D1), None)
    if share_row is None:
        raise BuildError(f"funds_current_shares.csv: нет доли текущих счетов физлиц на {D1}")
    share = float(share_row["current_share"])
    lo, hi = round(share - 0.005, 3), round(share + 0.005, 3)
    books[RETAIL_CURRENT] = round(dep_ind * share, 1)
    books[RETAIL_TERM] = r1(dep_ind - books[RETAIL_CURRENT])
    for bk in BOOKS:
        if bk == LIQUIDITY:
            continue
        row = c.book_row(rows, bk)
        c.check(f"книга {bk} = строке book листа книг", abs(books[bk] - float(row[col])) < 0.051,
                f"{ru(books[bk])} против {ru(float(row[col]))}")
    est_book = {bk: book_estimated(c.book_row(rows, bk)) for bk in BOOKS}
    for bk in ("corp_loans", "mortgage", "consumer_loans", SECURITIES):
        b["books"][bk] = est(books[bk], calc[bk]) if est_book[bk] else node(books[bk], calc=calc[bk])
    b["books"][LIQUIDITY] = est(books[LIQUIDITY], f"книга ликвидности — только доходные размещения ({DECISION_B2}): средства в "
                                f"банках {ru(c.sp('dfb_total'))} + обратное репо с юридическими лицами {ru(revc)} + обратное "
                                f"репо с физическими лицами {ru(revr)} − средства НПФ в банках {ru(npf_dfb)}; денежные средства "
                                f"{ru(c.sp('cash'))} и обязательные резервы {ru(c.sp('mandatory_reserves'))} — в прочих активах; "
                                f"{NPF_NOTE}")
    before = sorted((r for r in shares_rows if r["date"] < D1), key=lambda r: r["date"])
    b["books"][RETAIL_CURRENT] = est(books[RETAIL_CURRENT], S + f"средства физических лиц {ru(dep_ind)} × доля текущих счетов "
                                     f"{ru(share, 2)} ({share_words(c, share, share_row, before)})",
                                     rng=(round(dep_ind * lo, 1), round(dep_ind * hi, 1)))
    b["books"][RETAIL_TERM] = est(books[RETAIL_TERM], S + f"средства физических лиц {ru(dep_ind)} × (1 − {ru(share, 2)})",
                                  rng=(r1(dep_ind - round(dep_ind * hi, 1)), r1(dep_ind - round(dep_ind * lo, 1))))
    for bk in ("corp_funds", "wholesale"):
        b["books"][bk] = est(books[bk], calc[bk]) if est_book[bk] else node(books[bk], calc=calc[bk])
    ecl = [c.nt(m) for m, _ in ALLOWANCE]
    allowance = r1(-sum(ecl))
    b["allowance_ac"] = node(allowance, c.nsrc(ALLOWANCE[0][0]), "резерв по кредитам по амортизированной стоимости: "
                             + " + ".join(f"{w} {ru(-x)}" for (_, w), x in zip(ALLOWANCE, ecl)))
    fvoci_debt = r1(c.nt("fvoci_debt") - npf_inv)
    fvtpl_bonds = r1(sec_lines["trading_debt"] + sec_lines["trading_debt_repo"] + c.nt("fvtpl_debt") - npf_tr)
    s15 = c.nsrc("fvoci_debt")
    sec = b["securities"]
    sec["fvoci_debt"] = est(fvoci_debt, f"инвестиционные долговые бумаги через прочий совокупный доход {ru(c.nt('fvoci_debt'))} − "
                            f"инвестиционные бумаги НПФ {ru(npf_inv)} (все отнесены к этой категории — правило {RULES_FROM}); "
                            f"{NPF_NOTE}", s15, rng=(fvoci_debt, c.nt("fvoci_debt")))
    sec["fvoci_repo"] = node(c.nt("fvoci_repo"), s15)
    sec["ac"] = node(r1(c.nt("ac_debt") + c.nt("ac_ecl")), s15, f"долговые бумаги по амортизированной стоимости "
                     f"{ru(c.nt('ac_debt'))} за вычетом резерва {ru(-c.nt('ac_ecl'))}")
    sec["ac_repo"] = node(r1(c.nt("ac_repo") + c.nt("ac_repo_ecl")), s15, f"в залоге по репо {ru(c.nt('ac_repo'))} за вычетом "
                          f"резерва {ru(-c.nt('ac_repo_ecl'))}")
    sec["fvtpl_bonds"] = est(fvtpl_bonds, f"торговые долговые {ru(sec_lines['trading_debt'])} + в залоге по репо "
                             f"{ru(sec_lines['trading_debt_repo'])} + инвестиционные долговые через прибыль {ru(c.nt('fvtpl_debt'))} − "
                             f"торговые бумаги НПФ {ru(npf_tr)}; {NPF_NOTE}", s15)
    sec["npf_excluded"] = est(r1(npf_tr + npf_inv), f"бумаги НПФ вне книги (в прочих активах): торговые {ru(npf_tr)} + "
                              f"инвестиционные {ru(npf_inv)}; {NPF_NOTE}")
    teq, teq_repo = c.nt("trading_equity"), c.nt("trading_equity_repo")
    eq_other = r1(teq + teq_repo + c.nt("fvoci_equity") + c.nt("fvtpl_equity"))
    sec["equity_other"] = node(eq_other, s15, f"долевые бумаги (в книгу не входят — в прочих активах): торговые {ru(teq + teq_repo)} "
                               f"(с заложенными по репо {ru(teq_repo)}) + через прочий совокупный доход {ru(c.nt('fvoci_equity'))} + "
                               f"через прибыль {ru(c.nt('fvtpl_equity'))}")
    debt_total = r1(fvoci_debt + c.nt("fvoci_repo") + sec["ac"]["v"] + sec["ac_repo"]["v"] + fvtpl_bonds)
    c.check("книга долговых бумаг = частям по категориям", abs(debt_total - books[SECURITIES]) < 0.051,
            f"{ru(debt_total)} против {ru(books[SECURITIES])}")
    sec["debt_total"] = node(books[SECURITIES], calc="fvoci_debt + fvoci_repo + ac + ac_repo + fvtpl_bonds = книга securities")
    liq, Pl = b["liquidity"], P["liquidity"]
    liq["cash"] = node(c.sp("cash"), c.ssrc("cash"), Pl["cash"]["calc"])
    liq["mandatory_reserves"] = node(c.sp("mandatory_reserves"), c.ssrc("mandatory_reserves"), Pl["mandatory_reserves"]["calc"])
    liq["due_from_banks"] = node(c.sp("dfb_total"), c.ssrc("dfb_total"))
    liq["reverse_repo"] = node(r1(revc + revr), c.nsrc("revrepo_corp"), f"обратное репо в кредитах клиентам: юридические лица "
                               f"{ru(revc)} + физические лица {ru(revr)} (договор книг: в ликвидности)")
    liq["npf_excluded"] = est(r1(npf_dfb + npf_cash), f"средства НПФ в банках {ru(npf_dfb)} и деньги {ru(npf_cash)} — вне книги; "
                              f"{NPF_NOTE}")
    s19 = c.nsrc("dep_ind")
    f = b["funds"]
    f["retail_total"] = node(dep_ind, s19)
    f["retail_current"] = copy.deepcopy(b["books"][RETAIL_CURRENT])
    f["retail_term"] = copy.deepcopy(b["books"][RETAIL_TERM])
    f["corp_gov"] = node(c.nt("dep_gov"), s19)
    f["corp_other"] = node(c.nt("dep_corp_other"), s19)
    f["repo"] = node(c.nt("dep_repo"), s19)
    w = b["wholesale"]
    w["banks"] = node(c.sp("due_to_banks"), c.ssrc("due_to_banks"))
    w["banks_repo"] = node(c.nt("dtb_repo"), c.nsrc("dtb_repo"), "в том числе договоры репо в средствах банков")
    w["other_borrowed"] = node(c.sp("other_borrowed"), c.ssrc("other_borrowed"))
    w["central_banks"] = node(c.nt("ob_cb"), c.nsrc("ob_cb"), f"в том числе средства центральных банков (срочные депозиты "
                              f"{ru(c.man_v('cb_term'))} и репо {ru(c.man_v('cb_repo'))})")
    w["debt_issued"] = node(c.sp("debt_issued"), c.ssrc("debt_issued"))
    w["subordinated"] = node(c.sp("sub_debt"), c.ssrc("sub_debt"))
    assets_b, liabs_b = books_of("asset"), books_of("liability")
    iea = r1(sum(books[k] for k in assets_b))
    total_assets = c.sp("total_assets")
    cash_no_npf = r1(c.sp("cash") - npf_cash)
    other_assets = r1(total_assets - iea + allowance)
    b["other_assets"] = node(other_assets, calc=f"итог активов {ru(total_assets)} − Σ книг активов {ru(iea)} + резерв "
                             f"{ru(allowance)} (строки вне книг: долевые бумаги, производные, ассоциированные, группы выбытия, "
                             f"основные средства, недвижимость, гудвил и НМА, ОНА, прочие активы, активы НПФ, денежные средства "
                             f"без денег НПФ {ru(cash_no_npf)}, обязательные резервы {ru(c.sp('mandatory_reserves'))})")
    parts = {}
    for r in rows:
        if r["row_type"] == "outside_part" and r["book"] == OTHER_ASSETS:
            parts[r["item"]] = node(float(r[col]), calc=f"строка вне книг; лист sheets/books_balances.csv (якорь {c.a.period})")
    moved = [c.item(rows, LIQUIDITY, s) for s in BOOKS[LIQUIDITY]["moved"]]
    parts[moved[0]["item"] + " (без денег НПФ)"] = node(cash_no_npf, calc=f"строка баланса {ru(c.sp('cash'))} минус денежные "
                                                         f"средства НПФ {ru(npf_cash)} (они уже в строке «активы НПФ, вынесенные "
                                                         "из книг»); дохода не несут")
    parts[moved[1]["item"]] = node(c.sp("mandatory_reserves"), calc="строка баланса; дохода не несут")
    c.check("прочие активы = Σ частей", abs(sum(p["v"] for p in parts.values()) - other_assets) < 0.15,
            f"{ru(sum(p['v'] for p in parts.values()))} против {ru(other_assets)}")
    b["other_assets_parts"] = parts
    fx = {k: c.man_v(k) for k, _ in OTHER_ASSETS_FIXED}
    dta, gw, assoc = fx["dta"], fx["goodwill"], fx["associates"]
    intang = r1(sum(c.man_v(k) for k, _ in INTANGIBLES))
    ded_base = r1(dta + gw + intang)
    oaf = r1(dta + gw + assoc)
    p0 = P["other_assets_fixed_parts"]
    v0 = [p0[k]["v"] for k, _ in OTHER_ASSETS_FIXED]
    npf_all = r1(npf_tr + npf_inv + npf_dfb + npf_cash)
    b["other_assets_fixed"] = est(oaf, f"постоянные в рублях прочие активы ({DECISION_FIXED}; ключ книги "
                                  f"volumes.other_assets_fixed — число книги {ruk(P['other_assets_fixed']['v'])}, выведенное на ядре): "
                                  + " + ".join(f"{w_} {ru(fx[k])}" for k, w_ in OTHER_ASSETS_FIXED)
                                  + f" (на {d_ru(D0)}: {' + '.join(ru(v) for v in v0)} = {ruk(sum(v0))}; "
                                  f"{c.text('balance.other_assets_fixed')}). Нематериальные активы без гудвила {ru(intang)} и "
                                  f"активы НПФ {ru(npf_all)} растут с бизнесом — в растущей части прочих активов. Диапазон — ось "
                                  f"доли постоянных активов 0,4…0,8 в сумме «ОНА + гудвил + НМА» {ru(ded_base)}: доля × "
                                  f"{ru(ded_base)} + {ru(assoc)}", rng=(r1(0.4 * ded_base + assoc), r1(0.8 * ded_base + assoc)))
    b["other_assets_fixed_parts"] = {k: node(fx[k], c.msrc(k)) for k, _ in OTHER_ASSETS_FIXED}
    b["other_assets_growing_parts"] = {
        "intangibles": node(intang, c.msrc(INTANGIBLES[0][0]), "нематериальные активы без гудвила, остаточная стоимость (прим. 16): "
                            + " + ".join(f"{w_} {ru(c.man_v(k))}" for k, w_ in INTANGIBLES)),
        "npf_assets": est(npf_all, "оценка активов НПФ (без кредитов и прочих): " + NPF_NOTE)}
    fsd = round((dta + gw) / ded_base, 4)
    b["fixed_share_of_deductible"] = est(fsd, f"доля постоянных активов в сумме «ОНА + гудвил + НМА» по балансу МСФО на якоре: "
                                         f"({ru(dta)} + {ru(gw)}) / ({ru(dta)} + {ru(gw)} + {ru(intang)}) = {ru(fsd, 4)}; на "
                                         f"{d_ru(D0)} — {ru(P['fixed_share_of_deductible']['v'], 4)} (число узла и ключей книги; "
                                         f"правило — {DECISION_FIXED}; № 4, п. 3.3)", rng=(0.4, 0.8))
    b["total_assets"] = node(total_assets, c.ssrc("total_assets"))
    total_liab = c.sp("total_liab")
    liab_books = r1(sum(books[k] for k in liabs_b))
    payable = dividends_payable_value(c)
    other_liab = r1(total_liab - liab_books - payable)
    b["other_liabilities"] = node(other_liab, calc=f"итог обязательств {ru(total_liab)} − Σ книг пассивов {ru(liab_books)} − "
                                  f"дивиденды к выплате {ru(payable)}")
    b["other_liabilities_parts"] = {}
    for r in rows:
        if r["row_type"] == "outside_part" and r["book"] == OTHER_LIABILITIES:
            b["other_liabilities_parts"][r["item"]] = node(float(r[col]), calc=f"строка вне книг; лист sheets/books_balances.csv "
                                                                                f"(якорь {c.a.period})")
    b["dividends_payable"] = node(payable, c.text_src("balance.dividends_payable"), c.text("balance.dividends_payable"))
    b["dividends_payable_declared"] = []
    b["total_liabilities"] = node(total_liab, c.ssrc("total_liab"))
    e, Pe = b["equity"], P["equity"]
    bv = r1(c.sp("eq_shareholders") - c.sp("eq_perpetual"))
    for k in ("total", "shareholders", "at1", "nci"):
        e[k] = node(c.sp(EQUITY[k]), c.ssrc(EQUITY[k]), Pe[k]["calc"] if k in EQUITY_KEPT_CALC else None)
    e["bv_common"] = node(bv, calc=f"капитал акционеров {ru(c.sp('eq_shareholders'))} − бессрочные инструменты "
                          f"{ru(c.sp('eq_perpetual'))}" + ("; дивидендов к вычету на якоре нет" if not payable else ""))
    for k in ("share_capital", "share_premium", "treasury_cost", "other_funds", "retained_earnings"):
        e[k] = node(c.sp(EQUITY[k]), c.ssrc(EQUITY[k]), Pe[k]["calc"] if k in EQUITY_KEPT_CALC else None)
    e["tangible_common"] = node(r1(bv - c.sp("intangibles")), calc=f"bv_common − гудвил и НМА {ru(c.sp('intangibles'))} (справочно)")
    e["tangible_common_ex_dta"] = node(r1(bv - c.sp("intangibles") - dta), calc=f"bv_common − гудвил и НМА − отложенный налоговый "
                                       f"актив {ru(dta)} (справочно)")
    if c.a.year != c.prev.year:                       # новый год якоря: концы прошлого года — прежний якорь
        b["prev_year_end"] = prev_year_end(c)
    b["iea"] = est(iea, "процентные активы движка = Σ пяти книг активов (новый состав: ликвидность — доходные размещения); "
                   f"совпадает со знаменателем маржи банка {c.a.year} года (без денежных средств и обязательных резервов)")
    loans = r1(sum(books[k] for k in books_of(loans=True)))
    funds = r1(sum(books[k] for k in (RETAIL_CURRENT, RETAIL_TERM, "corp_funds")))
    gross_rep = r1(c.sp("loans_net") + allowance)
    b["history"][c.a.period] = {
        "date": D1,
        "bv_common": node(bv, c.ssrc("eq_shareholders"), f"капитал акционеров {ru(c.sp('eq_shareholders'))} − бессрочные "
                          f"инструменты {ru(c.sp('eq_perpetual'))}"),
        "equity_shareholders": node(c.sp("eq_shareholders"), c.ssrc("eq_shareholders")),
        "equity_total": node(c.sp("eq_total"), c.ssrc("eq_total")),
        "loans": node(loans, calc="кредитные книги " + " + ".join(books_of(loans=True)) + " (без обратного репо): "
                      + " + ".join(ru(books[k]) for k in books_of(loans=True)) + "; лист sheets/books_balances.csv"),
        "loans_ac_gross": node(loans, calc="= loans (кредитов по справедливой стоимости отдельной книгой нет)"),
        "loans_gross_reported": node(gross_rep, c.ssrc("loans_net"), f"кредиты и авансы клиентам после резерва "
                                     f"{ru(c.sp('loans_net'))} + резерв {ru(allowance)} (с обратным репо)"),
        "allowance_ac": node(allowance, calc="резерв по кредитам (прим. 14), величиной"),
        "funds": node(c.sp("customer_funds"), c.ssrc("customer_funds"), "средства клиентов (три книги)"),
        "iea": est(iea, "Σ пяти книг активов в новом составе (ликвидность — доходные размещения)"),
        "total_assets": node(total_assets, c.ssrc("total_assets")),
    }
    c.check("средства клиентов: Σ трёх книг = строке баланса", abs(funds - c.sp("customer_funds")) < 0.051,
            f"{ru(funds)} против {ru(c.sp('customer_funds'))}")
    # остатки книг на концы кварталов истории (вход весов решателя передачи средним окна)
    for row in b["history"].values():
        row["books"] = history_books(c, row["date"])
    anc = b["history"][c.a.period]["books"]
    c.check("остатки книг квартала якоря в истории = balance.books", all(abs(anc[k]["v"] - b["books"][k]["v"]) < 1e-9 for k in BOOKS),
            ", ".join(f"{k} {ru(anc[k]['v'])}" for k in BOOKS))
    assets = iea - allowance + other_assets
    claims = liab_books + other_liab + payable + bv + c.sp("eq_perpetual") + c.sp("eq_nci")
    c.check("баланс якоря: Σ книг активов − резерв + прочие активы = активы = пассивы и капитал",
            abs(assets - claims) < 0.15 and abs(assets - total_assets) < 0.15,
            f"активы {ru(assets)}, пассивы и капитал {ru(claims)}, итог {ru(total_assets)}")
    state = dict(books=books, allowance=allowance, iea=iea, bv=bv, gross_rep=gross_rep, payable=payable,
                 total_assets=total_assets, npf=npf, other_assets=other_assets, other_liab=other_liab)
    return b, state


# ------------------------------------------------------------------ nii_books.json

def carry_scale(interest: dict[str, float], nii: float, dia: float) -> tuple[float, float]:
    """Остаток ЧПД вне книг и множитель процентов книг активов: ставки якоря несут весь ЧПД (М§15.2 п. 4)."""
    income = sum(interest[b] for b in books_of("asset"))
    expense = sum(interest[b] for b in books_of("liability"))
    residual = nii - (income - expense - dia)
    return residual, 1.0 + residual / income


def build_nii_books(c: Ctx, st: dict) -> dict:
    pb = c.base["nii_books"]
    P = c.base["balance"]
    nb = copy.deepcopy(pb)
    a, books = c.a, st["books"]
    nb["as_of"], nb["period"] = c.D1, a.period
    nb["days"] = node(c.days, calc=f"дней в квартале {q_ru(a.period)} (act/365)")
    nb["rates_carry_residual"] = a.period >= RATES_CARRY_FROM
    split = c.split.get(a.tag_q)
    if not isinstance(split, dict) or set(split) != set(BOOKS):
        raise BuildError(f"{SHEET_SPLIT.format(k=a.quarter)}: нет процентов квартала по всем книгам (ключ {a.tag_q})")
    flagged = {k: c.texts.get(f"nii_books.books.{k}.interest_q", {}).get("flag") == "оценка" for k in BOOKS}
    n_est = sum(flagged.values())
    nb["note"] = (f"якорь {a.period} ({a.stage}): книга liquidity — только доходные размещения ({DECISION_B2}). Проценты по книгам "
                  f"у ВТБ не раскрыты — interest_q {COUNT_WORDS.get(n_est, str(n_est))} книг из {COUNT_WORDS.get(len(BOOKS), '')} "
                  f"— оценки правилом листа потока nii ({SPLIT_SCRIPT.format(k=a.quarter)}: формулы build_panel.py, сверены на "
                  f"{RULES_FROM} до 0,01). Ставки якоря несут весь ЧПД: остаток «ЧПД − (проценты активов − проценты пассивов − "
                  "взносы)» разнесён по книгам активов пропорционально их процентам (REANCHOR §3.6; rates_carry_residual)")
    interest = {k: r6(v) for k, v in split.items()}
    assets_b, liabs_b = books_of("asset"), books_of("liability")
    income = sum(interest[k] for k in assets_b)
    expense = sum(interest[k] for k in liabs_b)
    nii = c.g("nii")
    dia = -c.g("dia")
    residual = nii - (income - expense - dia)
    scale = 1.0 + residual / income if nb["rates_carry_residual"] else 1.0
    prev_bal = {k: pb["books"][k]["balance_close"]["v"] for k in BOOKS}
    c.check("остатки открытия книг = balance.books прежнего якоря",
            all(abs(prev_bal[k] - P["books"][k]["v"]) < 1e-9 for k in BOOKS), q_ru(c.prev.period))
    sheet = f"лист sheets/{SHEET_SPLIT_CSV.format(k=a.quarter)}"
    for k in BOOKS:
        close = books[k]
        avg = (prev_bal[k] + close) / 2
        carried = interest[k] * (scale if k in assets_b else 1.0)
        rate = r9(carried / avg * 365 / c.days)
        ent = nb["books"][k]
        ent["balance_open"] = node(prev_bal[k], calc=f"остаток книги на {d_ru(c.D0)} (balance.books.{k} фактов {q_ru(c.prev.period)})")
        ent["balance_close"] = node(close, calc=f"остаток книги на {d_ru(c.D1)} (balance.books.{k})")
        ent["balance_avg"] = node(r6(avg), calc="(balance_open + balance_close) / 2")
        flag = {"estimated": True} if flagged[k] else {}
        key = f"nii_books.books.{k}.interest_q"
        ent["interest_q"] = node(interest[k], c.text_src(key), f"{c.text(key)}; {sheet}", **flag)
        ent["rate_anchor"] = node(rate, calc="interest_q" + (" × (1 + остаток ЧПД / проценты активов) = × %.6f" % scale
                                                              if k in assets_b and nb["rates_carry_residual"] else "")
                                  + f" / balance_avg × 365/{c.days} (доля, act/365)", **flag)
    nb["interest_assets_q"] = node(r6(income), calc="Σ interest_q книг активов")
    nb["interest_liabilities_q"] = node(r6(expense), calc="Σ interest_q книг пассивов (величиной)")
    key = "nii_books.other_interest_net_q"
    nb["other_interest_net_q"] = node(r6(residual), c.text_src(key), c.text(key))
    nb["dia_q"] = node(dia, c.text_src(key), "платежи в рамках системы страхования вкладов за квартал, величиной")
    nb["nii_q"] = node(nii, c.gs("nii"))
    iea_avg = sum((prev_bal[k] + books[k]) / 2 for k in assets_b)
    nb["iea_avg"] = node(r6(iea_avg), calc="Σ balance_avg книг активов (три кредитные книги, долговые бумаги, доходная ликвидность)")
    nb["nim_eng_q"] = node(r9(nii / iea_avg * 365 / c.days), calc=f"nii_q × 365/{c.days} / iea_avg (ЧПМ базиса движка = "
                                                                   f"определение банка {a.year} года)")
    share_row = next(r for r in c.rows("funds_current_shares.csv") if r["segment"] == "retail" and r["date"] == c.D1)
    nb["current_share_anchor"] = est(r9(books[RETAIL_CURRENT] / (books[RETAIL_CURRENT] + books[RETAIL_TERM])),
                                     f"текущие счета физлиц / средства физлиц на якоре: слайд {share_row['page']} презентации "
                                     f"{a.ytd_ru} — {round(float(share_row['current_share']) * 100)} % (точность 1 п.п.)",
                                     c.src(share_row["doc"], share_row["page"]))
    key_rel = f"{a.stage}/sheets/key_rate_quarterly.csv"
    key_q = c.key_row(a.period, "key_avg_pct") / 100
    nb["key_avg_anchor_q"] = node(r9(key_q), f"key_rate_quarterly.csv, строка {a.period}, sha256 {c.sha(key_rel)[:16]}",
                                  f"средняя ключевая ставка Банка России за {q_ru(a.period)} по календарным дням ({c.days} дн.)")
    chk = income - expense - dia + residual - nii
    nb["check"] = node(round(chk, 6), calc="Σ активов − Σ пассивов − dia_q + other_interest_net_q − nii_q (допуск 0,1)")
    c.check("проценты книг − страхование вкладов + проценты вне книг = ЧПД", abs(chk) < 0.1 and abs(residual) < 0.1 * abs(nii),
            f"остаток вне книг {ru(residual, 3)} при ЧПД {ru(nii)}")
    st.update(interest=interest, residual=residual, scale=scale, prev_bal=prev_bal, iea_avg=iea_avg, nii=nii, key_q=key_q)
    return nb


# ------------------------------------------------------------------ pnl_quarterly.json

PRINTED_PROFIT = "напечатанное значение файла эмитента (0,1 млрд ₽); пометка оценки — по заданию дня отчёта (pnl.estimated)"


def build_pnl(c: Ctx, st: dict) -> dict:
    a = c.a
    pq = copy.deepcopy(c.base["pnl_quarterly"])
    pq["as_of"] = c.D1
    end = q_end(a.period)
    pq["note"] = (c.base["pnl_quarterly"]["note"] + f"; {q_ru(a.period)} — колонка {a.quarter}кв'{end.year % 100:02d} файла эмитента "
                  f"{a.ytd_ru} ({Path(c.docs['sup']['file']).name}; {c.text('pnl_quarterly.note')})")
    # колонки прежних кварталов года в файле эмитента — те же, что в фактах прежнего якоря
    same = []
    for p in a.year_quarters[:-1]:
        row0 = c.base["pnl_quarterly"]["quarters"].get(p, {})
        for k, m in (("nii", "nii"), ("ni_shareholders", "np_shareholders")):
            if (m, p) in c.sup and k in row0:
                same.append(abs(c.sp(m, p) - row0[k]["v"]) < 0.051)
    c.check("файл эмитента: прежние кварталы года = фактам прежнего якоря", all(same), f"{len(same)} строк")
    g, gs = c.g, c.gs
    ins = r1(sum(g(m) for m in PNL_INSURANCE))
    pbt = r1(g("pbt") + g("np_resale_subs"))
    misc = r1(pbt - (g("nii") + g("fees_net") + g("llp_debt_fa") + ins + 0.0 + g("opex_staff_admin")))
    paid_ytd = c.man_v(f"at1_paid_{a.tag_ytd}")
    paid_prev = float(c.base["capital"]["at1"]["coupon_paid_ytd"]["v"]) if a.quarter > 1 else 0.0
    coupon_q = r1(paid_ytd - paid_prev)
    other_prov = r1(sum(g(m) for m in PNL_OTHER_PROVISIONS))
    E = {"estimated": True}
    one_offs = []
    for r in c.rows("one_offs.csv"):
        if r["period"] == ifrs_q(a.period):
            one_offs.append({"component": r["component"], "item": r["item"],
                             "amount": node(float(r["value"]), c.src(r["doc"], r["page"]), r["note"])})
    row = {
        **{k: node(g(PNL_LINES[k]), gs(PNL_LINES[k])) for k in ("nii", "fees_net", "llp_debt_fa")},
        "insurance_net": node(ins, gs(PNL_INSURANCE[0]), f"выручка по страхованию {ru(g(PNL_INSURANCE[0]))} + расходы по "
                              f"страхованию {ru(g(PNL_INSURANCE[1]))} (форма Сбера: результат страховых услуг; результат "
                              "инвестирования активов НПФ и финансовые расходы — в misc_net)"),
        "misc_net": node(misc, calc=f"pbt − (nii + fees_net + llp_debt_fa + insurance_net + noncore_net + opex) = {ru(pbt)} − "
                         f"({ru(g('nii'))} + {ru(g('fees_net'))} + {ru(g('llp_debt_fa'))} + {ru(ins)} + 0 + "
                         f"{ru(g('opex_staff_admin'))}); внутри — {c.text('pnl.misc_net')}", **E),
        "noncore_net": node(0.0, calc="непрофильного блока нет: вся прибыль группы — прибыль движка", **E),
        "opex": node(g(PNL_LINES["opex"]), gs(PNL_LINES["opex"])),
        "pbt": node(pbt, gs("pbt"), f"прибыль до налогообложения {ru(g('pbt'))} + убыток после налога от дочерних компаний, "
                    f"приобретённых для перепродажи, {ru(g('np_resale_subs'))} — чтобы держалось ni = pbt + tax", **E),
        "tax": node(g("tax"), gs("tax"), PRINTED_PROFIT, **E),
        "ni": node(g("np"), gs("np"), PRINTED_PROFIT, **E),
        "ni_shareholders": node(g("np_shareholders"), gs("np_shareholders"), PRINTED_PROFIT, **E),
        "ni_nci": node(g("np_nci"), gs("np_nci"), PRINTED_PROFIT, **E),
        "dia": node(-g("dia"), gs("dia"), "величиной (в отчёте — со знаком минус); внутри nii"),
        "at1_coupon": node(coupon_q, c.msrc(f"at1_paid_{a.tag_ytd}"), "выплаты по бессрочным инструментам за квартал, величиной: "
                           + (f"{a.ytd_ru} {ru(paid_ytd)} − {c.prev.ytd_ru} {ru(paid_prev)}" if a.quarter > 1
                              else f"{a.ytd_ru} {ru(paid_ytd)}")),
        "ni_ordinary": node(r1(g("np_shareholders") - coupon_q), calc="ni_shareholders − at1_coupon: прибыль обыкновенных "
                            "акционеров (база прибыли на акцию)"),
        "key_avg": node(r6(st["key_q"]), calc=f"sheets/key_rate_quarterly.csv: средняя ключевая ставка Банка России за квартал по "
                        f"календарным дням ({c.days} дн.), проценты → доли"),
        "other_income_bank": node(r1(ins + misc - other_prov - g("np_resale_subs")), calc=(
            "«прочие операционные доходы» в определении банка = ЧОД до резервов − ЧПД − комиссии = insurance_net + misc_net − "
            f"прочие резервы {ru(other_prov)} − убыток перепродажи {ru(g('np_resale_subs'))}; сверка: файл эмитента, "
            f"{c.man_row(f'other_op_income_bank_{a.tag_q}')[2]} — {ru(c.man_v(f'other_op_income_bank_{a.tag_q}'))}")),
        "other_provisions": node(other_prov, gs(PNL_OTHER_PROVISIONS[0]), f"резервы по обязательствам кредитного характера и прочим "
                                 f"активам {ru(g(PNL_OTHER_PROVISIONS[0]))} + по искам {ru(g(PNL_OTHER_PROVISIONS[1]))} (внутри misc_net)"),
        "one_offs": one_offs,
        "reported": {k: node(g(m), gs(m)) for k, m in PNL_REPORTED.items()},
    }
    c.check(f"ОПУ {q_ru(a.period)}: pbt + tax = ni; ni_shareholders + ni_nci = ni",
            abs(row["pbt"]["v"] + row["tax"]["v"] - row["ni"]["v"]) < 0.051
            and abs(row["ni_shareholders"]["v"] + row["ni_nci"]["v"] - row["ni"]["v"]) < 0.051,
            f"pbt {ru(pbt)}, налог {ru(g('tax'))}, прибыль {ru(g('np'))}")
    c.check("прочие операционные доходы банка = файлу эмитента",
            abs(row["other_income_bank"]["v"] - c.man_v(f"other_op_income_bank_{a.tag_q}")) < 0.051,
            ru(row["other_income_bank"]["v"]))
    pq["quarters"][a.period] = row
    st.update(ins=ins, misc=misc, pbt=pbt, coupon_q=coupon_q)
    return pq


# ------------------------------------------------------------------ mgmt_quarterly.json

def build_mgmt(c: Ctx, st: dict) -> dict:
    a, g = c.a, c.g
    pm = c.base["mgmt_quarterly"]
    mq = copy.deepcopy(pm)
    mq["as_of"] = c.D1
    end = q_end(a.period)
    sheet = c.sup_cell("nim", a.period).split("!")[0]
    mq["note"] = pm["note"] + f"; {q_ru(a.period)} — файл эмитента {a.ytd_ru} ({sheet}, колонка {a.quarter}кв'{end.year % 100:02d})"
    pct_calc = "проценты документа → доли (напечатано с точностью 0,1 п.п.)"
    P = c.base["balance"]
    prev_eq_total = P["history"][c.prev.period]["equity_total"]["v"]
    eq_avg = (prev_eq_total + c.sp("eq_total")) / 2
    bv_prev = P["equity"]["bv_common"]["v"]
    gross0, gross1 = P["history"][c.prev.period]["loans_gross_reported"]["v"], st["gross_rep"]

    def inv_at(date: str) -> float:
        rs = [c.item(c.books_rows, SECURITIES, s) for s in ("инвестиционные долговые через прочий", "то же, в залоге",
                                                            "инвестиционные долговые через прибыль", "инвестиционные долговые по АС",
                                                            "инвестиционные долговые по АС, в залоге")]
        return sum(float(r["bal_" + date]) for r in rs)

    dfb0 = float(c.item(c.books_rows, LIQUIDITY, "средства в банках")["bal_" + c.D0])
    inv1 = c.nt("fvoci_debt") + c.nt("fvoci_repo") + c.nt("fvtpl_debt") + c.nt("ac_debt") + c.nt("ac_repo")
    i0, i1 = gross0 + dfb0 + inv_at(c.D0), gross1 + c.sp("dfb_total") + inv1
    oibp = g("pbt") - g("llp_debt_fa") - sum(g(m) for m in PNL_OTHER_PROVISIONS) - g("opex_staff_admin")
    nii = g("nii")
    rec = {"nim": nii * 4 / ((i0 + i1) / 2), "cor": -g("llp_debt_fa") * 4 / ((gross0 + gross1) / 2),
           "cir": -g("opex_staff_admin") / oibp}
    row = {x: node(c.sp(x, a.period), c.gs(x), pct_calc) for x in MGMT_PRINTED}
    row.update({
        "np": node(g("np"), c.gs("np"), "вся чистая прибыль группы — числитель ROE банка"),
        "np_shareholders": node(g("np_shareholders"), c.gs("np_shareholders")),
        "equity_total": node(c.sp("eq_total"), c.ssrc("eq_total"), "весь капитал — знаменатель ROE банка"),
        "roe_recalc": None,
        "roe_common": node(r6((g("np_shareholders") - st["coupon_q"]) * 4 / ((bv_prev + st["bv"]) / 2)),
                           calc="(прибыль акционеров − выплаты по бессрочным инструментам) × 4 / средний bv_common — не "
                                "сравнивается с ROE банка"),
        "cir_recalc": node(r6(rec["cir"]), calc=f"расходы / чистые операционные доходы до резервов (= {ru(-g('opex_staff_admin'))} "
                                                f"/ {ru(oibp)})"),
        "cor_recalc": node(r6(rec["cor"]), calc="резервы по долговым активам × 4 / средние валовые кредиты"),
        "nim_recalc": node(r6(rec["nim"]), calc="ЧПД × 4 / средние (валовые кредиты + средства в банках + инвестиционные долговые "
                                                "бумаги)"),
    })
    for k in MGMT_COPIED:
        row[k] = copy.deepcopy(pm["quarters"][c.prev.period][k])
    mq["quarters"][a.period] = row
    # ROE банка — годовой пересчёт по дням квартала (решение медленного круга книги 1.0): весь ряд истории
    eq = {p: q.get("equity_total", {}).get("v") for p, q in mq["quarters"].items()}
    for p, q in mq["quarters"].items():
        if "roe_recalc" not in q:
            continue
        e0 = eq.get(q_prev(p))
        if q.get("np", {}).get("v") is None or e0 is None or eq.get(p) is None:
            if q["roe_recalc"] is None:
                raise BuildError(f"mgmt_quarterly: ROE банка за {p} — нет капитала на начало квартала")
            continue
        x4 = r6(q["np"]["v"] * 4 / ((e0 + eq[p]) / 2))      # прежний ряд «× 4» (шесть знаков), пересчитанный на дни
        q["roe_recalc"] = node(r6(x4 * 365 / (4 * q_days(p))),
                               calc="вся прибыль × 365 / дни квартала / средний весь капитал (определение банка: годовой "
                                    "пересчёт по дням)")
    ab = mq["anchor_balances"]
    for k, m in MGMT_ANCHOR:
        ab[k] = node(c.man_v(m), c.msrc(m))
    for h in mq.get("history_gaps") or []:
        per = str(h.get("period") or "")
        if per.endswith("–" + c.prev.period):
            h["period"] = per[: -len(c.prev.period)] + a.period
    st.update(rec=rec, oibp=oibp)
    return mq


# ------------------------------------------------------------------ bridge_mgmt_ifrs.json

def build_bridge(c: Ctx, st: dict) -> dict:
    a, g = c.a, c.g
    pbr = c.base["bridge_mgmt_ifrs"]
    br = copy.deepcopy(pbr)
    br["as_of"] = c.D1
    br["window"] = [pbr["window"][0], a.period]
    books, prev_bal = st["books"], st["prev_bal"]
    loans_b = books_of(loans=True)
    loans_avg = sum((prev_bal[k] + books[k]) / 2 for k in loans_b)
    nii, iea_avg, ins, misc = st["nii"], st["iea_avg"], st["ins"], st["misc"]
    income = g("nii") + g("fees_net") + ins + misc
    eng = {"nim": nii / iea_avg * 365 / c.days, "cor": -g("llp_debt_fa") / loans_avg * 365 / c.days,
           "cir": -g("opex_staff_admin") / income}
    x4 = {"nim": nii * 4 / iea_avg, "cor": -g("llp_debt_fa") * 4 / loans_avg}
    eng_calc = {"nim": f"nii {ru(nii)} × 365/{c.days} / средние процентные активы движка {ru(iea_avg)}",
                "cor": f"−llp_debt_fa {ru(g('llp_debt_fa'))} × 365/{c.days} / средняя сумма кредитных книг {ru(loans_avg)}",
                "cir": f"−opex {ru(g('opex_staff_admin'))} / доходы движка {ru(income)}"}
    rec, kq, pq = st["rec"], q_ru(a.period), q_ru(c.prev.period)
    for x in ("cor", "nim", "cir"):
        blk = br[x]
        mgmt_v = c.sp(x, a.period)
        gap = eng[x] - mgmt_v
        line = {"period": a.period, "mgmt": node(mgmt_v, c.gs(x), "проценты документа → доли"),
                "engine": node(r6(eng[x]), calc=eng_calc[x]), "gap": node(r6(gap), calc="engine − mgmt"),
                "mgmt_recalc": node(r6(rec[x]), calc="пересчёт по определению банка из строк МСФО (концы квартала, база «× 4»)")}
        if x in x4:
            line["engine_x4"] = node(r6(x4[x]), calc="то же на базе «× 4» — без счёта дней")
            line["gap_x4"] = node(r6(x4[x] - mgmt_v), calc="engine_x4 − mgmt")
        blk["history"].append(line)
        n_old = int(pbr[x]["n"]["v"])
        old_v = pbr[x]["value"]["v"]
        own = pbr[x]["window"]
        if own[0] != pbr["window"][0] and q_parse(own[0]) == (c.prev.year, 1) and a.year != c.prev.year:
            n_old, own = 0, [a.period, a.period]        # окно ЧПМ — отчётные кварталы года якоря: новый год — заново
        new_v = (old_v * n_old + gap) / (n_old + 1)
        gaps = [h["gap"]["v"] for h in blk["history"] if own[0] <= h["period"] <= a.period]
        if x in BRIDGE_MEDIAN:
            med = statistics.median(gaps)
            blk["value"] = node(r6(med), calc=f"медиана gap по окну {own[0]}–{a.period} (правило {RULES_FROM} «медиана по окну»; "
                                              f"узел value_median_rule) — {DECISION_CIR_MEDIAN}; перенос дал {r6(new_v)} (прежнее "
                                              f"правило: ({ru(old_v, 6)} × {n_old} + {ru(gap, 6)}) / {n_old + 1})")
            blk["value_median_rule"] = node(r6(med), calc=f"медиана gap по окну {own[0]}–{a.period} (n = {len(gaps)}) — правило "
                                                          f"{RULES_FROM}, справочно")
        elif n_old == 0:
            blk["value"] = node(r6(new_v), calc=f"gap {kq}: окно значения — отчётные кварталы года якоря {own[0]}–{a.period} "
                                                "(n = 1) — REANCHOR §3.8")
        else:
            mean = sum(gaps) / len(gaps)
            blk["value"] = node(r6(new_v), calc=f"среднее gap по окну {own[0]}–{a.period} (n = {n_old + 1}): (значение {pq} × "
                                                f"{n_old} + gap {kq}) / {n_old + 1} — REANCHOR §3.8; прямое среднее ряда {ru(mean, 6)}")
        blk["window"] = [own[0], a.period]
        blk["n"] = node(n_old + 1, calc="кварталов в окне значения")
        sd_g = statistics.stdev(gaps) if len(gaps) > 1 else None
        sd_words = f"выборочное стандартное отклонение gap по окну {own[0]}–{a.period}"
        blk["sd"] = node(r6(sd_g), calc=sd_words) if sd_g is not None else na(sd_words + ": один квартал — не определено")
        six = [h["gap"]["v"] for h in blk["history"]][-6:]
        first6 = blk["history"][-6]["period"] if len(blk["history"]) >= 6 else blk["history"][0]["period"]
        blk["value_six_quarters"] = node(r6(sum(six) / len(six)), calc=f"среднее gap за шесть последних кварталов "
                                                                        f"{first6}–{a.period} (n = {len(six)})")
        c.check(f"мосты упр. ↔ движок: {x}", True, f"{ru(old_v * 100, 4)} → {ru(blk['value']['v'] * 100, 4)} п.п. (n = {n_old + 1})")
    br["direction"] = re.sub(r"(\d{4}Q[1-4])–" + re.escape(c.prev.period), lambda m: f"{m.group(1)}–{a.period}", pbr["direction"])
    br["direction"] = re.sub(r"; на якоре \d{4}Q[1-4] значения продлены[^;]*$", "", br["direction"])
    br["direction"] += (f"; на якоре {a.period} значения продлены закрытым кварталом по REANCHOR §3.8 (у C/I — средним от медианы "
                        f"{pq})")
    st.update(eng=eng)
    return br


# ------------------------------------------------------------------ capital.json

PREFERRED_GONE = "привилегированных акций после 29.04.2026 нет"
NOTE28 = "прим. 28"


def strip_tail(text: str, *marks: str) -> str:
    """Слова прежнего якоря без хвоста, который дописал прежний якорь (повторная сборка не удваивает хвост)."""
    for m in marks:
        text = text.split(m)[0]
    return text


def build_capital(c: Ctx, st: dict) -> dict:
    a = c.a
    pc = c.base["capital"]
    cap = copy.deepcopy(pc)
    cap["as_of"] = c.D1
    D1, nd = c.D1, c.a.next_day
    kq, ytd = q_ru(a.period), a.ytd_ru
    form_date = c.prev.next_day                          # последняя форма группы — на первое число после прежнего якоря
    b10, b11 = c.form("bank_n1_0", nd), c.form("bank_n1_1", nd)
    b07_0, b07_1 = c.form("bank_n1_0", form_date), c.form("bank_n1_1", form_date)
    g0, g1 = c.form("group_n20_0", c.D0), c.form("group_n20_1", c.D0)
    sp20, sp11 = g0[0] - b07_0[0], g1[0] - b07_1[0]
    n20_est, n11_est = r6(b10[0] + sp20), r6(b11[0] + sp11)
    if ("group_n20_0", D1) in c.forms:
        raise BuildError(f"форма 0409805 группы на {D1} есть в листе форм — правило нормативов по форме ещё не написано "
                         "(сейчас: напечатанные эмитентом, Р6)")
    printed = {k: r6(c.man_v(f"ifrs_{k}") / 100) for k in ("n20_0", "n20_1", "n20_2")}
    psrc = c.text_src("capital.printed_ratios")
    slide = re.search(r"слайд (\d+)", psrc or "")
    cap["note"] = (strip_tail(pc["note"], "; якорь ") + f"; якорь {a.period}: формы 0409805 на {d_ru(nd)} ещё нет — нормативы группы "
                   f"напечатанные эмитентом ({NOTE28} и слайд {slide.group(1) if slide else '?'}: Н20.0 {ru(printed['n20_0'] * 100)} %, "
                   f"Н20.1 {ru(printed['n20_1'] * 100)} %, Н20.2 {ru(printed['n20_2'] * 100)} %; округлено до 0,1 п.п.; "
                   f"{DECISION_PRINTED_RATIOS}), заменить формой 0409805; RWA для Н20.0 — {NOTE28} на {d_ru(D1)}; базовый капитал "
                   f"группы — последняя форма ({d_ru(c.D0)}, с пометкой оценки): на {D1[8:10]}.{D1[5:7]} не раскрыт")

    def printed_value(what: str, bank: tuple, spread: float, est_v: float) -> dict:
        """Норматив группы, напечатанный эмитентом (Р6); оценка §3.10 по формам — словами, снята."""
        return node(printed[what], psrc, f"{'Н20.0' if what == 'n20_0' else 'Н20.1'} банковской группы на {d_ru(nd)}, напечатанный "
                    f"эмитентом — {DECISION_PRINTED_RATIOS}; округлено до 0,1 п.п.; заменить формой 0409805 (reanchor.py "
                    f"--capital-form). Оценка §3.10 до решения: {ru(bank[0] * 100, 3)} + {ru(spread * 100, 3)} = "
                    f"{ru(est_v * 100, 3)} (норматив банка {bank[0]} + разность «группа − банк» на {c.D0} {r6(spread)}) — снята")

    kpi0, kpi1 = f"kpi_n20_0_{a.tag_next_month}", f"kpi_n20_1_{a.tag_next_month}"
    cell0 = c.man_row(kpi0)[2]
    pn = c.base["capital"]["n20_0"]
    cap["n20_0"] = {
        "basis": pn["basis"],
        "value": printed_value("n20_0", b10, sp20, n20_est),
        "as_of": D1, "estimated": False, "pre_dividend": st["payable"] > 0,
        "pre_dividend_note": c.text("capital.pre_dividend_note"),
        "min_with_buffers": copy.deepcopy(pn["min_with_buffers"]),
        "value_ifrs_note": node(c.man_v("ifrs_n20_0") / 100, c.msrc("ifrs_n20_0"), f"как напечатано в {NOTE28} (0,1 п.п.); то же — "
                                f"слайд и файл эмитента ({cell0} на {d_ru(nd)})"),
        "monthly": copy.deepcopy(pn["monthly"]) + [{"date": nd, "value": node(c.man_v(kpi0), c.msrc(kpi0),
                                                                                f"оперативные данные банка (файл эмитента {ytd}), "
                                                                                "0,1 п.п.")}],
    }
    p11 = pc["n1_1_bank"]
    cap["n1_1_bank"] = {
        "basis": p11["basis"],
        "value": printed_value("n20_1", b11, sp11, n11_est),
        "as_of": D1, "estimated": False,
        "value_ifrs_note": node(c.man_v("ifrs_n20_1") / 100, c.msrc("ifrs_n20_1"), f"как напечатано в {NOTE28} (0,1 п.п.); то же — "
                                "слайд"),
        "monthly": copy.deepcopy(p11.get("monthly") or []) + [{"date": nd, "value": node(c.man_v(kpi1), c.msrc(kpi1))}],
    }
    c.check("нормативы группы: напечатанные эмитентом = файлу эмитента на первое число после якоря",
            abs(c.man_v(kpi0) - printed["n20_0"]) < 1e-9 and abs(c.man_v(kpi1) - printed["n20_1"]) < 1e-9,
            f"Н20.0 {pct(printed['n20_0'], 1)}, Н20.1 {pct(printed['n20_1'], 1)}; оценка §3.10 — {pct(n20_est, 3)}, {pct(n11_est, 3)}")
    cap["n20_2"] = node(printed["n20_2"], psrc, f"напечатано эмитентом ({DECISION_PRINTED_RATIOS}), округлено до 0,1 п.п.; "
                        "заменить формой 0409805; ядро не читает", basis=pc["n20_2"]["basis"])
    cap["n1_1_bank_ras"] = node(r6(c.man_v("bank_n1_1") / 100), c.msrc("bank_n1_1"), f"{NOTE28} отчёта за {ytd}: Н1.1 банка "
                                f"{ru(c.man_v('bank_n1_1'))} % (как Н1.0 и Н1.2 — один документ на одну дату); форма 0409135 на "
                                f"{d_ru(nd)} ({ru(b11[0] * 100, 3)} %, ряд сервера) в папке передачи не сохранена",
                                basis="РСБУ банка (справочно)", as_of=nd)
    cap["n1_2_bank"] = node(r6(c.man_v("bank_n1_2") / 100), c.msrc("bank_n1_2"), basis="РСБУ банка (справочно)")
    cap["n1_0_bank"] = node(r6(c.man_v("bank_n1_0") / 100), c.msrc("bank_n1_0"), basis="РСБУ банка (справочно)")
    # уровни капитала группы — примечание 28 отчёта якоря (одна дата с нормативами); базовый — Н20.1 × активы для Н20.1
    rwa0, rwa1, rwa2 = (c.man_v(f"ifrs_rwa_n20_{i}") for i in range(3))
    tier1, supp, total = c.man_v("ifrs_tier1"), c.man_v("ifrs_supplementary"), c.man_v("ifrs_capital_total")
    base = r3(printed["n20_1"] * rwa1)
    add = r3(tier1 - base)
    n201 = f"{c.man_v('ifrs_n20_1'):g}"
    base_words = f"{NOTE28} отчёта за {ytd} (одна дата — {d_ru(D1)}): Н20.1 группы {n201} % × активы для Н20.1 {rud(rwa1)}"
    s28 = c.msrc("ifrs_tier1")
    bbc = dict(pc["bank_base_capital"])
    bbc.update(v=base, src=s28, calc=strip_tail(bbc["calc"], ": " + NOTE28, "; значение последней формы")
               + f": {base_words}; формы на якорь ещё нет", estimated=True)
    cap["bank_base_capital"] = bbc
    gc = cap["group_capital"]
    gc["total"] = node(total, c.msrc("ifrs_capital_total"), f"{NOTE28} отчёта за {ytd} (формы на якорь ещё нет)", estimated=True)
    gc["base"] = node(base, s28, f"{base_words}; базовый капитал отдельно не раскрыт — норматив напечатан с точностью 0,1 п.п. "
                      f"(±{ru(0.0005 * rwa1)} млрд ₽); заменить формой 0409805", estimated=True)
    gc["additional"] = node(add, s28, f"{NOTE28}: основной капитал {tier1} − базовый {base}; заменить формой 0409805", estimated=True)
    gc["supplementary"] = node(supp, c.msrc("ifrs_supplementary"), f"{NOTE28} отчёта за {ytd}", estimated=True)
    gc["tier1"] = node(tier1, s28, f"основной капитал, {NOTE28} отчёта за {ytd}")
    c.check("капитал группы: основной + дополнительный = итог (прим. 28)", abs(tier1 + supp - total) < 0.15,
            f"{ru(tier1)} + {ru(supp)} против {ru(total)}")
    bs, pbs = cap["basel"], pc["basel"]
    bs["as_of"] = D1
    cet1 = dict(pbs["cet1"])
    cet1.update(v=base, src=s28, calc=strip_tail(cet1["calc"], "; " + NOTE28, "; значение последней формы") + f"; {base_words}",
                estimated=True)
    bs["cet1"] = cet1
    bs["rwa"] = node(rwa0, c.msrc("ifrs_rwa_n20_0"), f"активы, взвешенные по риску, для Н20.0 на {d_ru(D1)} (раскрыты в {NOTE28} — "
                     f"правило {RULES_FROM}); при нормативах без оценки ({DECISION_PRINTED_RATIOS}) перенос калибрует плотности к ним")
    bs["rwa_n20_0"] = node(rwa0, c.msrc("ifrs_rwa_n20_0"))
    bs["rwa_n20_1"] = node(rwa1, c.msrc("ifrs_rwa_n20_1"))
    bs["rwa_n20_2"] = node(rwa2, c.msrc("ifrs_rwa_n20_2"))
    bs["cet1_ratio"] = node(r6(base / rwa0), calc=f"базовый капитал по {NOTE28} / активы для Н20.0 на {d_ru(D1)} (как пишет "
                            f"перенос: basel_cet1 / basel_rwa); Н20.1 напечатан — {ru(printed['n20_1'] * 100)} %", estimated=True)
    bs["cet1_to_rwa_n20_0"] = node(r6(base / rwa0), calc=f"базовый капитал по {NOTE28} / активы для Н20.0 на {d_ru(D1)} — "
                                   "справочно", estimated=True)
    bs["total_ratio"] = node(r6(total / rwa0), calc=f"капитал / активы для Н20.0 по {NOTE28} ({ruk(total)} / {ruk(rwa0)})")
    bs["rwa_to_assets"] = node(round(rwa0 / st["total_assets"], 4), calc="активы для Н20.0 / активы МСФО")
    t20 = pc["t2_recognized"]
    by_form = "f805" in str(t20.get("src") or "")
    cap["t2_recognized"] = node(supp, c.msrc("ifrs_supplementary"), f"слот ядра: дополнительный капитал группы целиком на "
                                f"{d_ru(D1)} по {NOTE28} (0,1 млрд ₽; на {d_ru(c.D0)}{' по форме' if by_form else ''} — "
                                f"{ru(t20['v'], 2)}); в МСФО субординированная задолженность {ru(c.sp('sub_debt'))}",
                                basis=t20["basis"], estimated=True)
    a1, pa1 = cap["at1"], pc["at1"]
    a1["amount"] = node(c.man_v("at1_total"), c.msrc("at1_total"))
    ra = dict(pa1["regulatory_amount"])
    ra.update(v=add, src=s28, calc=f"добавочный капитал группы по {NOTE28} на {d_ru(D1)}: основной − базовый (в МСФО — "
              f"{ru(c.man_v('at1_total'))})", estimated=True)
    a1["regulatory_amount"] = ra
    rub0 = c.cap_in("perp_rub", FLOATING_FROM)
    floating = r1(c.man_v("at1_rub") - rub0)
    fixed_part = r1(c.man_v("at1_total") - floating)
    rate_fixed = pa1["fixed_rate_implied"]["v"]
    key_end = c.key_row(a.period, "key_end_pct") / 100
    cash_coupon = r1(floating * (key_end + FLOATING_SPREAD) + fixed_part * rate_fixed)
    four = q_range(q_prev(q_prev(q_prev(a.period))), a.period)
    last3 = [pa1["by_quarter"][p]["v"] for p in four[:-1]]
    ltm = r1(sum(last3) + st["coupon_q"])
    m23 = re.search(r"прим\. \d+", c.man_row("at1_rub")[3])
    a1["coupon_annual_cash"] = est(cash_coupon, f"годовой купон на составе якоря {d_ru(D1)}: плавающая часть {ru(floating)} × "
                                   f"(ключевая {ru(key_end * 100, 2)} % + {round(FLOATING_SPREAD * 100)} %) + фиксированная часть "
                                   f"{ru(fixed_part)} × {ru(rate_fixed * 100, 2)} % (ставка — выведенная из выплат "
                                   f"{ytd_ru(RULES_FROM_PERIOD)}, число {RULES_FROM}); плавающая часть — рублёвые выпуски «ключевая "
                                   f"+ {round(FLOATING_SPREAD * 100)} %»: прирост рублёвых бессрочных с {d_ru(FLOATING_FROM)} "
                                   f"({ru(rub0)} → {ru(c.man_v('at1_rub'))}, {m23.group(0) if m23 else 'прим.'}, "
                                   f"{page_words(c.man_row('at1_rub')[2])}). Нижняя граница — факт четырёх кварталов "
                                   f"{q_ru(four[0])}–{q_ru(four[-1])}", rng=(ltm, pa1["coupon_annual_cash"]["range"][1]))
    a1["coupon_ltm"] = node(ltm, calc=f"факт: выплаты за {q_ru(four[0])}–{q_ru(four[-1])} = "
                            + " + ".join(ru(x) for x in last3 + [st["coupon_q"]]))
    paid_key = f"at1_paid_{a.tag_ytd}"
    a1["coupon_paid_ytd"] = node(c.man_v(paid_key), c.msrc(paid_key), f"выплачено за {ytd} — уже вычтено из bv_common якоря")
    a1["floating_base"] = est(floating, f"рублёвые бессрочные облигации со ставкой «ключевая + {round(FLOATING_SPREAD * 100)} %»: "
                              f"{ru(c.man_v('at1_rub'))} − {ru(rub0)}")
    a1["key_sensitivity"] = est(floating, "d(годовой купон) / d(ключевая ставка в долях) = плавающая часть")
    paid_prev = float(pa1["coupon_paid_ytd"]["v"]) if a.quarter > 1 else 0.0
    a1["by_quarter"][a.period] = node(st["coupon_q"], c.msrc(paid_key), f"{ytd} {ru(c.man_v(paid_key))} − {c.prev.ytd_ru} "
                                      f"{ru(paid_prev)}" if a.quarter > 1 else f"{ytd} {ru(c.man_v(paid_key))}")
    fx_keys = ("at1_lpn_fx", "at1_bonds_fx", "at1_bonds_fx2")
    a1["by_currency"] = {"rub": node(c.man_v("at1_rub"), c.msrc("at1_rub")),
                         "fx": node(r1(sum(c.man_v(k) for k in fx_keys)), calc=f"ноты участия в кредите {ru(c.man_v(fx_keys[0]))} "
                                    f"+ облигации {ru(c.man_v(fx_keys[1]))} + {ru(c.man_v(fx_keys[2]))} (прочие валюты)")}
    # фонды капитала по движению с конца прошлого года
    ye = a.prev_year_end
    q, y_ = a.tag_q, a.tag_ytd
    M = c.man_v
    fv_res = r1(pc["fvoci_reserve"]["v"] + M(f"oci_fvoci_debt_{q}") + M(f"oci_fvoci_reclass_{q}"))
    fund_ye = c.cap_in("fvoci_fund_total", ye)
    fv_res_mov = r1(fund_ye + M(f"oci_fvoci_debt_{y_}") + M(f"oci_fvoci_reclass_{y_}") + M(f"oci_fvoci_equity_{y_}")
                    + M(f"equity_fund_reclass_{y_}"))
    c.check("фонд переоценки бумаг: прежний якорь + квартал = конец года + нарастающий итог", abs(fv_res - fv_res_mov) < 0.051,
            f"{ru(fv_res)} против {ru(fv_res_mov)}")
    fund_row = c.cap_inputs[("fvoci_fund_total", ye)]
    pages = sorted({c.man_row(f"oci_fvoci_debt_{y_}")[2], c.man_row(f"equity_fund_reclass_{y_}")[2]}, key=int)
    cap["fvoci_reserve"] = node(fv_res, calc=(f"фонд переоценки долговых и долевых инвестиционных активов и хеджирования (после "
                                              f"налога) по движению: {ru(fund_ye)} на {d_ru(ye)} ({Path(fund_row['doc']).name}, "
                                              f"{page_words(fund_row['page'])}) + результат по долговым активам "
                                              f"{ru(M(f'oci_fvoci_debt_{y_}'))} + перенос в прибыль {ru(M(f'oci_fvoci_reclass_{y_}'))} + "
                                              f"результат по долевым {ru(M(f'oci_fvoci_equity_{y_}'))} + перенос фонда долевых при "
                                              f"выбытии {ru(M(f'equity_fund_reclass_{y_}'))} (отчёт за {ytd}, с. {', '.join(pages)}); за "
                                              f"{kq}: {ru(M(f'oci_fvoci_debt_{q}'))} + {ru(M(f'oci_fvoci_reclass_{q}'))}"),
                                estimated=True, basis="IFRS")
    ins_ye, bld_ye, fx_ye = (c.cap_in(m, ye) for m in ("insurance_fin_reserve", "revaluation_buildings_fund", "fx_translation_fund"))
    ins_res = r1(ins_ye + M(f"oci_npf_{y_}"))
    bld = r1(bld_ye + M(f"oci_buildings_{y_}") + M(f"buildings_transfer_{y_}"))
    fxr = r1(fx_ye + M(f"oci_fx_{y_}"))
    disp = M(f"subs_disposal_funds_{y_}")
    chk_funds = r1(fv_res + ins_res + bld + fxr + M(f"oci_assoc_{y_}") + disp)
    c.check("фонды капитала по движению = строке баланса «прочие фонды»", abs(chk_funds - c.sp("eq_other_funds")) < 0.15,
            f"{ru(chk_funds)} против {ru(c.sp('eq_other_funds'))}")
    cap["fvoci_reserve_check"] = node(c.sp("eq_other_funds"), c.ssrc("eq_other_funds"), (
        f"фонд бумаг {ru(fv_res)} + резерв страхования {ru(ins_res)} + переоценка зданий ({ru(bld_ye)} − "
        f"{ru(-M(f'oci_buildings_{y_}'))} − {ru(-M(f'buildings_transfer_{y_}'))}) + курсовые ({ru(fx_ye)} + {ru(M(f'oci_fx_{y_}'))}) + "
        f"доля в ассоциированных {ru(M(f'oci_assoc_{y_}'))} {'−' if disp < 0 else '+'} выбытие дочерних {ru(abs(disp))} = прочие "
        f"фонды (строка баланса {ru(c.sp('eq_other_funds'))})"), basis="IFRS")
    cap["insurance_fin_reserve"] = est(ins_res, f"финансовый резерв по договорам страхования: {ru(ins_ye)} на {d_ru(ye)} + "
                                       f"финансовые доходы НПФ в прочем совокупном доходе {ru(M(f'oci_npf_{y_}'))} за {ytd} — "
                                       "зеркало переоценки бумаг НПФ", basis="IFRS")
    cap["fvoci_reserve_net_of_insurance"] = est(r1(fv_res + ins_res), "справочно: фонд бумаг за вычетом зеркального резерва "
                                                "страхования", rng=(fv_res, r1(fv_res + ins_res)), basis="IFRS")
    curve = {}
    with open(c.root / CURVE_FILE, encoding="utf-8") as fh:
        for r in csv.reader(ln for ln in fh if not ln.startswith("#")):
            if r and r[0] == D1:
                curve[r[3]] = float(r[4])
    oc = cap["ofz_curve_anchor"]
    oc["as_of"] = D1
    for t in CURVE_NODES:
        key = "%.1f" % float(t)
        if key not in curve:
            raise BuildError(f"{CURVE_FILE}: нет кривой ОФЗ на {D1} (срок {t})")
        oc[t] = node(r6(curve[key] / 100), f"{Path(CURVE_FILE).name}, строка {D1}, sha256 {c.sha(CURVE_FILE)[:16]}",
                     f"кривая бескупонной доходности ОФЗ (MOEX ISS) на {d_ru(D1)}, проценты → доли")
    # history: строка квартала — с формой 0409805 группы на конец квартала (её на якоре нет — правило сборщика)
    return cap


# ------------------------------------------------------------------ shares.json

def build_shares(c: Ctx) -> dict:
    ps = c.base["shares"]
    sh = copy.deepcopy(ps)
    sh["as_of"] = c.D1
    s22 = c.msrc("shares_issued")
    raw = {k: c.man_v(f"shares_{k}") for k in ("issued", "treasury", "outstanding")}
    iss, tr, outst = (raw[k] / 1e6 for k in ("issued", "treasury", "outstanding"))
    c.check("акции: размещённые − у группы = в обращении", abs(raw["issued"] - raw["treasury"] - raw["outstanding"]) < 0.5,
            f"{shares_words(raw['issued'])} − {shares_words(raw['treasury'])} = {shares_words(raw['outstanding'])}")
    sh["issued_total"] = node(r6(iss), s22, c.text("shares.issued_total"))
    sh["issued_ordinary"] = node(r6(iss), s22, "все размещённые акции — обыкновенные")
    sh["issued_preferred"] = node(0.0, s22, PREFERRED_GONE)
    sh["treasury_ordinary"] = node(r6(tr), s22, f"обыкновенные акции, удерживаемые компаниями группы: {shares_words(raw['treasury'])} "
                                                f"(на {d_ru(c.D0)} — {shares_words(ps['treasury_ordinary']['v'] * 1e6)})")
    sh["outstanding_total"] = node(r6(outst), s22, f"в отчётности — {shares_words(raw['outstanding'])}")
    sh["outstanding_ordinary"] = node(r6(outst), s22, "= outstanding_total")
    sh.pop(f"weighted_avg_{ifrs_q(c.prev.period)}", None)
    sh[f"weighted_avg_{ifrs_q(c.a.period)}"] = node(r6(outst), s22, c.text("shares.weighted_avg"))
    return sh


# ------------------------------------------------------------------ dividends.json

def build_dividends(c: Ctx, pnl: dict) -> dict:
    dv = copy.deepcopy(c.base["dividends"])
    dv["as_of"] = c.D1
    for h in dv["history"]:
        if h.get("status") == "выплачен после якоря" and str(h.get("pay_date") or "9") <= c.D1:
            h["status"] = "выплачен"
    q = pnl["quarters"]
    ys = c.a.year_quarters
    sh = [q[p]["ni_shareholders"]["v"] for p in ys]
    ni = [q[p]["ni"]["v"] for p in ys]
    dv["years"][str(c.a.year)] = {
        "ni_shareholders": node(r1(sum(sh)), calc=f"прибыль акционеров с начала года по {q_ru(c.a.period)}: "
                                + " + ".join(ru(x) for x in sh)),
        "ni_group": node(r1(sum(ni)), calc="вся прибыль: " + " + ".join(ru(x) for x in ni)),
        "complete": c.a.quarter == 4, "through": c.a.period}

    def alive(r: dict) -> bool:                          # запись реестра — пока её экс-дата позже даты фактов
        ex = r.get("ex_date") or r.get("record_date")
        return ex is None or str(ex) > c.D1

    dv["register_seed"] = [r for r in dv.get("register_seed") or [] if alive(r)]
    dv["register_seed_note"] = c.text("dividends.register_seed_note")
    return dv


# ------------------------------------------------------------------ anchor.json, guidance.json, bridge_ras_ifrs.json

def build_anchor(c: Ctx) -> dict:
    a = c.a
    an = copy.deepcopy(c.base["anchor"])
    an["as_of"], an["period"] = c.D1, a.period
    span = f"{a.year} год" if a.quarter == 4 else f"{3 * a.quarter} месяцев {a.year} года"
    an["note"] = (f"якорь — отчётность МСФО группы за {span} (опубликована {d_ru(c.docs['fs']['published'])}); кандидат фактов "
                  f"перезаякоривания ({a.stage}); documents — реестр документов и листов, на которые ссылаются src узлов (путь — от "
                  "корня папки передачи)")
    have = {d["key"] for d in an["documents"]}
    for role in ("fs", "sup", "pres"):
        d = c.docs[role]
        if d["key"] not in have:
            an["documents"].append({"key": d["key"], "file": d["file"], "sha256": c.sha(d["file"]), "title": d["title"]})
    for d in an["documents"]:
        if d.get("file") == CURVE_FILE:
            d["sha256"] = c.sha(CURVE_FILE)
    for d in an["documents"]:
        if d.get("file") and (c.root / d["file"]).is_file():
            c.verify(d["file"], d["sha256"])
    return an


def build_guidance(c: Ctx) -> dict:
    gd = copy.deepcopy(c.base["guidance"])
    events = c.rows("guidance_events.csv")
    if events:
        gd["as_of"] = max(r["date"] for r in events)
        gd["note"] = c.base["guidance"]["note"] + "; " + c.text("guidance.note")
    for r in events:
        new_src = "; ".join(x for x in (c.src(r["doc"], r["page"]) if r.get("doc") else "", r.get("extra") or "") if x)
        if r["action"] == "confirm":
            it = gd["items"].get(r["key"])
            if it is None:
                raise BuildError(f"guidance_events.csv: подтверждён пункт {r['key']}, которого нет в гайденсе")
            confirm = (f"подтверждено {d_ru(r['date'])} без изменений ({new_src}); прежний источник — {it.get('src')} "
                       f"({it.get('date')})")
            it["src"] = new_src
            it["calc"] = f"{it['calc']}; {confirm}" if it.get("calc") else confirm
            it["date"], it["event"] = r["date"], r["event"]
        elif r["action"] == "add":
            item = {"v": float(r["value"]) if r.get("value") else None, "calc": r["calc"]}
            if new_src:
                item["src"] = new_src
            for k in ("kind", "text"):
                if r.get(k):
                    item[k] = r[k]
            item.update(date=r["date"], event=r["event"])
            for k in ("scope", "scope_note"):
                if r.get(k):
                    item[k] = r[k]
            gd["items"][r["key"]] = item
        else:
            raise BuildError(f"guidance_events.csv: действие {r['action']!r} — confirm или add")
    c.check("гайденс: события квартала", True, f"{len(events)} строк листа событий")
    return gd


def build_bridge_ras(c: Ctx) -> dict:
    br = copy.deepcopy(c.base["bridge_ras_ifrs"])
    br["as_of"] = c.D1
    return br


# ------------------------------------------------------------------ сборка, база, запись, сверка

def base_from_git(period: str) -> dict[str, dict] | None:
    """Факты на якоре period из истории git: последний коммит, где data/facts/anchor.json стоит на этом квартале."""
    try:
        revs = subprocess.run(["git", "log", "--format=%H", "--", "data/facts"], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return None
    for rev in revs:
        show = subprocess.run(["git", "show", f"{rev}:data/facts/anchor.json"], cwd=REPO, capture_output=True)
        if show.returncode or json.loads(show.stdout.decode("utf-8")).get("period") != period:
            continue
        out = {}
        for k in BUILT:
            blob = subprocess.run(["git", "show", f"{rev}:data/facts/{k}.json"], cwd=REPO, capture_output=True, check=True)
            out[k] = json.loads(blob.stdout.decode("utf-8"))
        print(f"база — факты {period} из истории git ({rev[:7]})")
        return out
    return None


def load_base(anchor: Anchor, base_dir: Path | None) -> dict[str, dict]:
    prev = q_prev(anchor.period)
    if base_dir is not None:
        base = {k: json.loads((base_dir / f"{k}.json").read_text(encoding="utf-8")) for k in BUILT}
        if str(base["anchor"]["period"]) != prev:
            raise BuildError(f"--base {base_dir}: факты на {base['anchor']['period']}, якорю {anchor.period} нужны факты {prev}")
        return base
    if (FACTS / "anchor.json").exists() and default_anchor() == prev:
        return {k: json.loads((FACTS / f"{k}.json").read_text(encoding="utf-8")) for k in BUILT}
    base = base_from_git(prev)
    if base is None:
        raise BuildError(f"нет фактов прежнего квартала {prev}: ни в data/facts, ни в истории git — задайте --base")
    return base


def build_ctx(root: Path, anchor: Anchor, base: dict[str, dict]) -> tuple[dict[str, dict], Ctx]:
    c = Ctx(root, anchor, base)
    bal, st = build_balance(c)
    nb = build_nii_books(c, st)
    pnl = build_pnl(c, st)
    mq = build_mgmt(c, st)
    files = {
        "balance": bal, "nii_books": nb, "pnl_quarterly": pnl, "capital": build_capital(c, st), "shares": build_shares(c),
        "dividends": build_dividends(c, pnl), "bridge_mgmt_ifrs": build_bridge(c, st), "bridge_ras_ifrs": build_bridge_ras(c),
        "mgmt_quarterly": mq, "guidance": build_guidance(c),
    }
    files["anchor"] = build_anchor(c)
    unused = sorted(set(c.texts) - c.used_texts)
    c.check("записки узлов квартала (facts_notes.csv) — все в деле", not unused, ", ".join(unused) or f"{len(c.used_texts)} записок")
    return {k: files[k] for k in BUILT}, c


def build(root: Path, anchor: Anchor, base: dict[str, dict]) -> tuple[dict[str, dict], list]:
    files, c = build_ctx(root, anchor, base)
    return files, c.checks


def write(files: dict[str, dict], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        with open(target / f"{name}.json", "w", encoding="utf-8", newline="\n") as f:
            f.write(dumps(data))


# ------------------------------------------------------------------ файл отчёта квартала (вход перезаякоривания)
#
# Формат — тот, что читает ops/tools/reanchor.py (`quarter-report/1`, docs/REANCHOR.md §2), с отличиями эмитента:
# годовой календарь дивидендов (`dividends_payable_year`, решения собрания — строками `dividend_decisions` с суммой на
# все категории акций: база объёма iea), слоты нормативов в смысле банковской группы и флаг оценки (`capital.estimated`,
# `capital.estimate`, `pnl.estimated`), раздел `shares` — размещённые, в обращении и экономически собственные акции.
# Поле `capital.t2` отчёт не несёт: слот `t2_recognized` ВТБ — дополнительный капитал группы целиком (с прибылью до
# аудита), а ключ книги `capital.n20.t2` — субординированный долг МСФО; перенос переписал бы ключ квартала якоря.

REPORT_PNL = ("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt", "tax", "ni", "ni_shareholders",
              "misc_net")
REPORT_TOP = ("schema", "period", "as_of", "source", "balance", "interest", "dia", "pnl", "capital", "market", "mgmt", "shares")
REPORT_T2 = False                # слот t2_recognized → capital.t2 отчёта (у ВТБ — нет: см. выше)
SHARES_REPORTED = ("issued_total", "outstanding_total", "economic_treasury", "issued_ordinary", "outstanding_ordinary")


def report_from_facts(files: dict[str, dict], *, source: str) -> dict:
    """Файл отчёта квартала из фактов якоря: остатки и проценты книг, строки ОПУ движка, капитал, рынок, упр. метрики."""
    bal, nb, cap, sh = files["balance"], files["nii_books"], files["capital"], files["shares"]
    period = str(files["anchor"]["period"])

    def need(n: dict, where: str) -> float:
        if not isinstance(n, dict) or n.get("v") is None:
            raise BuildError(f"отчёт квартала из фактов: нет числа {where}")
        return float(n["v"])

    row = files["pnl_quarterly"]["quarters"][period]
    pnl: dict = {k: need(row[k], f"pnl_quarterly.{period}.{k}") for k in REPORT_PNL}
    if (row.get("oci_fvoci") or {}).get("v") is not None:
        pnl["oci_fvoci"] = float(row["oci_fvoci"]["v"])
    if row["ni_shareholders"].get("estimated"):
        pnl["estimated"] = True
    mrow = files["mgmt_quarterly"]["quarters"][period]
    mgmt = {}
    for x in ("nim", "cor", "cir"):
        n = mrow.get(x + "_exact") if (mrow.get(x + "_exact") or {}).get("v") is not None else mrow.get(x)
        if x != "cir" or (n or {}).get("v") is not None:
            mgmt[x] = need(n, f"mgmt_quarterly.{period}.{x}")
    capital = {"n20_0": need(cap["n20_0"]["value"], "capital.n20_0.value"),
               "n20_pre_dividend": bool(cap["n20_0"]["pre_dividend"]),
               "n1_1_bank": need(cap["n1_1_bank"]["value"], "capital.n1_1_bank.value"),
               "basel_cet1": need(cap["basel"]["cet1"], "capital.basel.cet1"),
               "basel_rwa": need(cap["basel"]["rwa"], "capital.basel.rwa"),
               "bank_base_capital": need(cap["bank_base_capital"], "capital.bank_base_capital"),
               "estimated": bool(cap["n20_0"].get("estimated"))}
    if REPORT_T2:
        capital["t2"] = need(cap["t2_recognized"], "capital.t2_recognized")
    if capital["estimated"]:
        capital["estimate"] = {slot: {k: (v["v"] if isinstance(v, dict) else v) for k, v in cap[slot]["estimate"].items()}
                               for slot in ("n20_0", "n1_1_bank")}
    balance = {
        "books": {b: need(bal["books"][b], f"balance.books.{b}") for b in BOOKS},
        # кредиты по справедливой стоимости — внутри книги corp_loans, отдельного узла и части ядра нет: справка 0
        "loans_fvtpl": float((bal.get("loans_fvtpl") or {}).get("v") or 0.0),
        "fvoci": r6(need(bal["securities"]["fvoci_debt"], "balance.securities.fvoci_debt")
                    + need(bal["securities"]["fvoci_repo"], "balance.securities.fvoci_repo")),
        "fvtpl_bonds": need(bal["securities"]["fvtpl_bonds"], "balance.securities.fvtpl_bonds"),
        "allowance": need(bal["allowance_ac"], "balance.allowance_ac"),
        "other_assets": need(bal["other_assets"], "balance.other_assets"),
        "other_assets_fixed": need(bal["other_assets_fixed"], "balance.other_assets_fixed"),
        "other_liabilities": need(bal["other_liabilities"], "balance.other_liabilities"),
        "dividends_payable": need(bal["dividends_payable"], "balance.dividends_payable"),
    }
    if bal.get("dividends_payable_declared"):          # квартальный календарь: объявлено и не выплачено — по периодам
        balance["dividends_payable_declared"] = [{"period": x["period"], "amount": need(x["amount"], "balance.dividends_payable_declared")}
                                                 for x in bal["dividends_payable_declared"]]
    elif bal.get("dividends_payable_year") is not None:   # годовой календарь: год прибыли объявленного дивиденда
        balance["dividends_payable_year"] = int(bal["dividends_payable_year"])
    balance.update({
        "bv_common": need(bal["equity"]["bv_common"], "balance.equity.bv_common"),
        "fvoci_reserve": need(cap["fvoci_reserve"], "capital.fvoci_reserve"),
        "at1": need(bal["equity"]["at1"], "balance.equity.at1"), "nci": need(bal["equity"]["nci"], "balance.equity.nci"),
    })
    report = {"schema": REPORT_SCHEMA, "period": period, "as_of": str(files["anchor"]["as_of"])}
    m = re.search(r"опубликована (\d\d)\.(\d\d)\.(\d{4})", str(files["anchor"].get("note") or ""))
    if m and f"{m.group(3)}-{m.group(2)}-{m.group(1)}" > report["as_of"]:   # дата публикации — дата оценки кандидата
        report["published"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    report.update({
        "source": source,
        "balance": balance,
        "interest": {b: need(nb["books"][b]["interest_q"], f"nii_books.books.{b}.interest_q") for b in BOOKS},
        "dia": need(nb["dia_q"], "nii_books.dia_q"),
        "pnl": pnl,
        "capital": capital,
        "market": {"ofz_curve": {t: need(cap["ofz_curve_anchor"][t], f"capital.ofz_curve_anchor.{t}") for t in CURVE_NODES},
                   "key_avg": need(nb["key_avg_anchor_q"], "nii_books.key_avg_anchor_q")},
        "mgmt": mgmt,
        "shares": {k: need(sh[k], f"shares.{k}") for k in SHARES_REPORTED},
        "dividend_decisions": report_decisions(files),
    })
    check_report(report)
    return report


def report_decisions(files: dict[str, dict]) -> list[dict]:
    """Решения собраний о дивиденде, принятые в квартале якоря (позже конца прошлого квартала и не позже якоря), —
    раздел `dividend_decisions`: квартал прибыли, DPS, день решения, даты реестра и выплаты, суммы."""
    period, as_of = str(files["anchor"]["period"]), str(files["anchor"]["as_of"])
    opened = q_end(q_prev(period)).isoformat()
    out = []
    for h in files["dividends"].get("history") or []:
        if not opened < str(h.get("decided_date") or "") <= as_of:
            continue
        row = {"period": h["period"], "dps": float(h["dps"]["v"]), "decided_date": h["decided_date"]}
        for key in ("record_date", "pay_date"):
            if h.get(key):
                row[key] = h[key]
        for key in ("pool_declared", "pool_all_classes"):
            if (h.get(key) or {}).get("v") is not None:
                row[key] = float(h[key]["v"])
        out.append(row)
    return out


def check_report(report: dict) -> None:
    """Состав и тождества файла отчёта: недостающий ключ или несходящийся баланс — отказ."""
    problems = [f"нет {k}" for k in REPORT_TOP if k not in report]
    if not problems:
        b, p = report["balance"], report["pnl"]
        problems += [f"нет balance.books.{x}" for x in BOOKS if x not in b["books"]]
        problems += [f"нет interest.{x}" for x in BOOKS if x not in report["interest"]]
        problems += [f"нет pnl.{x}" for x in REPORT_PNL if x not in p]
        if not problems:
            assets = sum(b["books"][x] for x in books_of("asset")) - b["allowance"] + b["other_assets"]
            claims = (sum(b["books"][x] for x in books_of("liability")) + b["other_liabilities"] + b["dividends_payable"]
                      + b["bv_common"] + b["at1"] + b["nci"])
            if abs(assets - claims) > 0.5:
                problems.append(f"баланс не сходится: активы {assets:.3f}, обязательства и капитал {claims:.3f}")
            lines = sum(p[k] for k in ("nii", "llp_debt_fa", "fees_net", "insurance_net", "noncore_net", "opex", "misc_net"))
            if abs(lines - p["pbt"]) > 1e-4 or abs(p["pbt"] + p["tax"] - p["ni"]) > 1e-4:
                problems.append("ОПУ не сходится: сумма строк против pbt или pbt + tax против ni")
            declared = b.get("dividends_payable_declared") or []
            if sum(x["amount"] for x in declared) > b["dividends_payable"] + 1e-9:
                problems.append("объявленные дивиденды больше остатка к выплате")
            if b["dividends_payable"] > 1e-9 and not declared and b.get("dividends_payable_year") is None:
                problems.append("дивиденды к выплате без года прибыли (dividends_payable_year)")
        if not isinstance(report["capital"].get("n20_pre_dividend"), bool):
            problems.append("capital.n20_pre_dividend — true или false")
    if problems:
        raise BuildError("отчёт квартала: " + "; ".join(problems))


def write_report(files: dict[str, dict], path: Path, *, source: str) -> None:
    report = report_from_facts(files, source=source)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(report))
    print(f"записан отчёт квартала {report['period']} ({REPORT_SCHEMA}): {path}")


# ------------------------------------------------------------------ режим --expected: отчёт квартала → факты
#
# Факты следующего квартала из фактов якоря и файла отчёта квартала — того, что пишет `reanchor.py --expected`
# (ожидание модели). Независимая от `reanchor.py` сборка тех же правил переноса (docs/MODEL.md §15.2): ставки якоря
# несут весь ЧПД (без надбавки за субординацию отчёта); упр. факт квартала входит в историю мостов, их значения
# продлеваются закрытым кварталом в ряду значения; решения собрания закрываемого квартала (годовой календарь, база
# объёма iea) становятся строками истории дивидендов; строка истории баланса нового квартала несёт остатки книг;
# строки, которых модель не ведёт, — `null` с причиной.

EXPECTED_TOP = (("period", "balance", "interest", "dia", "pnl", "capital", "market", "mgmt"),
                ("schema", "as_of", "published", "source", "note", "shares", "dividend_decisions"))
EXPECTED_SECTIONS = {
    "balance": (("books", "loans_fvtpl", "fvoci", "fvtpl_bonds", "allowance", "other_assets", "other_liabilities",
                 "dividends_payable", "bv_common", "fvoci_reserve"),
                ("dividends_payable_year", "dividends_payable_declared", "other_assets_fixed", "at1", "nci")),
    "pnl": (("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt", "tax", "ni", "ni_shareholders"),
            ("misc_net", "oci_fvoci", "other_equity_movements", "estimated", "t2_premium")),
    "capital": (("n20_0", "n20_pre_dividend", "n1_1_bank", "basel_cet1", "basel_rwa", "bank_base_capital"),
                ("t2", "estimated", "estimate")),
    "market": (("ofz_curve", "key_avg"), ("price_index",)),
    "mgmt": (("nim", "cor"), ("cir",)),
    "shares": ((), ("issued_total", "issued_ordinary", "issued_preferred", "outstanding_total", "outstanding_ordinary",
                    "outstanding_preferred", "economic_treasury")),
}
MGMT_WORDS = {"nim": "чистая процентная маржа", "cor": "стоимость риска", "cir": "отношение расходов к доходам"}
EXPECTED_SUM = ("nii", "llp_debt_fa", "fees_net", "insurance_net", "noncore_net", "opex", "misc_net")   # = pbt
SERIES_TOL = 1e-6               # ряд значения моста: |среднее по окну − value| не больше этого (как в reanchor.py)


def check_report_shape(report: dict) -> None:
    """Состав файла отчёта: незнакомый или недостающий ключ — отказ (опечатка не должна пройти молча)."""
    if not isinstance(report, dict):
        raise BuildError("отчёт квартала: ожидается словарь JSON")
    if report.get("schema", REPORT_SCHEMA) != REPORT_SCHEMA:
        raise BuildError(f"отчёт квартала: schema {report.get('schema')!r}, нужна {REPORT_SCHEMA!r} (docs/REANCHOR.md)")
    required, optional = EXPECTED_TOP
    problems = [f"нет {k}" for k in required if k not in report]
    problems += [f"незнакомый ключ {k}" for k in report if k not in required + optional]
    for name, (req, opt) in EXPECTED_SECTIONS.items():
        section = report.get(name)
        if section is None:
            continue
        if not isinstance(section, dict):
            problems.append(f"{name} — не словарь")
            continue
        problems += [f"нет {name}.{k}" for k in req if k not in section]
        problems += [f"незнакомый ключ {name}.{k}" for k in section if k not in req + opt]
    for where, block in (("balance.books", (report.get("balance") or {}).get("books")), ("interest", report.get("interest"))):
        if isinstance(block, dict):
            problems += [f"нет {where}.{b}" for b in BOOKS if b not in block]
            problems += [f"незнакомая книга {where}.{b}" for b in block if b not in BOOKS]
        elif block is not None:
            problems.append(f"{where} — не словарь по книгам")
    curve = (report.get("market") or {}).get("ofz_curve")
    if isinstance(curve, dict):
        problems += [f"нет market.ofz_curve.{t}" for t in CURVE_NODES if t not in curve]
    if problems:
        raise BuildError("отчёт квартала: " + "; ".join(problems))
    if not isinstance(report["capital"]["n20_pre_dividend"], bool):
        raise BuildError("отчёт квартала: capital.n20_pre_dividend — true или false")
    if (report["capital"].get("estimated") is True) != ("estimate" in report["capital"]):
        raise BuildError("отчёт квартала: capital.estimate — блок оценки есть тогда и только тогда, когда estimated: true")


def bridge_series(block: dict) -> str:
    """Ряд значения моста (М§4.6, REANCHOR §3.8): тот ряд истории блока (`gap` — act/365, `gap_x4` — база «× 4»), чьё
    среднее по окну значения равно значению; если таких нет или их два — `gap_x4`, если он есть в истории, иначе `gap`."""
    rows = block.get("history") or []
    have = {k for r in rows for k, v in r.items() if isinstance(v, dict) and "v" in v}
    old = "gap_x4" if "gap_x4" in have else "gap"
    window, value = block.get("window"), (block.get("value") or {}).get("v")
    if value is None or not (isinstance(window, list) and len(window) == 2):
        return old
    fit = []
    for name in ("gap", "gap_x4"):
        vals = [(r.get(name) or {}).get("v") for r in rows if window[0] <= str(r.get("period")) <= window[1]]
        if name in have and vals and all(isinstance(v, (int, float)) for v in vals) \
                and abs(sum(vals) / len(vals) - float(value)) <= SERIES_TOL:
            fit.append(name)
    return fit[0] if len(fit) == 1 else old


def expected_facts(prev: dict[str, dict], report: dict, *, name: str, sha: str) -> tuple[dict[str, dict], list]:
    """Факты нового якоря (файлы сборщика) из фактов прежнего якоря `prev` и отчёта следующего квартала `report`.
    Возвращает (файлы, сверки). Чистая функция: вход не меняет."""
    checks: list[tuple[str, bool, str]] = []
    check_report_shape(report)
    old, new = Anchor(str(prev["anchor"]["period"])), Anchor(str(report["period"]))
    if new.period != q_next(old.period):
        raise BuildError(f"отчёт квартала — за {new.period}, факты стоят на {old.period}: нужен отчёт следующего "
                         f"квартала ({q_next(old.period)})")
    if "as_of" in report and str(report["as_of"]) != new.date:
        raise BuildError(f"отчёт квартала: as_of {report['as_of']} — не конец квартала {new.period} ({new.date})")

    def has(path: str) -> bool:
        try:
            return dig(report, path) is not None
        except KeyError:
            return False

    def num(path: str) -> float:
        x = dig(report, path)
        if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or abs(x) == float("inf"):
            raise BuildError(f"отчёт квартала: {path} — не число ({x!r})")
        return float(x)

    def ref(path: str) -> str:
        return f"{name}, {path}, sha256 {sha[:16]}"

    def en(path: str, what: str, *, value: float | None = None, **extra) -> dict:
        """Узел из отчёта квартала — с точностью файла отчёта (девять знаков): число — ожидание модели, не отчётность."""
        return node(r9(num(path) if value is None else value), src=ref(path), calc=f"отчёт квартала: {what}", **extra)

    def calc(v: float, how: str, **extra) -> dict:
        return node(r9(v), calc=f"отчёт квартала: {how}", **extra)

    def kept(n: dict, **extra) -> dict:
        """Величина, которую отчёт квартала не называет, а модель не двигает: значение прежнего якоря."""
        if n.get("v") is None:
            return dict(n)
        return node(n["v"], calc=f"как на {d_ru(old.date)}: отчёт квартала величину не называет", **extra)

    def none(why: str, **extra) -> dict:
        return na(f"нет данных: отчёт квартала строку не несёт — {why}", **extra)

    def nulls(tree: dict, why: str) -> dict:
        """Узлы поддерева — null с причиной (прежнее число под новой датой было бы ложью)."""
        out = {}
        for k, v in tree.items():
            if isinstance(v, dict) and "v" in v:
                out[k] = none(why)
            elif isinstance(v, dict):
                out[k] = nulls(v, why)
            else:
                out[k] = v
        return out

    out = {k: copy.deepcopy(prev[k]) for k in BUILT}
    d, days = new.date, q_days(new.period)
    on, kq = d_ru(d), q_ru(new.period)
    assets_b, liabs_b, loans_b = books_of("asset"), books_of("liability"), books_of(loans=True)

    # ---------------- balance.json
    pb, bal = prev["balance"], out["balance"]
    bal["as_of"] = d
    bal["note"] = (f"ЯКОРЬ ИЗ ОТЧЁТА КВАРТАЛА {new.period} (сухой прогон перезаякоривания): остатки — из файла «{name}»; разбивок "
                   f"строк модель не ведёт; история по {old.period} — факты")
    book = {b: num(f"balance.books.{b}") for b in BOOKS}
    for b in BOOKS:
        bal["books"][b] = en(f"balance.books.{b}", f"остаток книги «{BOOKS[b]['name']}» на {on}")
    sec, psec = bal["securities"], pb["securities"]
    fv = num("balance.fvoci")
    f_old = [float(psec["fvoci_debt"]["v"]), float(psec["fvoci_repo"]["v"])]
    sec["fvoci_debt"] = node(r9(fv * f_old[0] / sum(f_old)), src=ref("balance.fvoci"),
                             calc=f"отчёт квартала: долговые бумаги FVOCI на {on} — долей строки на {d_ru(old.date)}")
    sec["fvoci_repo"] = node(r9(fv - sec["fvoci_debt"]["v"]), src=ref("balance.fvoci"),
                             calc=f"отчёт квартала: долговые бумаги FVOCI в залоге по репо на {on} — остаток до balance.fvoci")
    sec["fvtpl_bonds"] = en("balance.fvtpl_bonds", f"облигации по справедливой стоимости через прибыль на {on}")
    rest = book[SECURITIES] - fv - sec["fvtpl_bonds"]["v"]
    ac_old = [float(psec["ac"]["v"]), float(psec["ac_repo"]["v"])]
    if rest < -0.05:
        raise BuildError("отчёт квартала: части книги долговых бумаг, заданные отдельно, больше её остатка")
    sec["ac"] = calc(rest * ac_old[0] / sum(ac_old), "бумаги по амортизированной стоимости — остаток книги долей строки на "
                     f"{d_ru(old.date)}")
    sec["ac_repo"] = calc(rest - sec["ac"]["v"], "то же в залоге по репо — остаток")
    sec["npf_excluded"] = none("бумаги НПФ вне книги модель не ведёт")
    sec["equity_other"] = none("долевые бумаги модель отдельно не ведёт")
    sec["debt_total"] = calc(book[SECURITIES], "= книга securities")
    bal["liquidity"] = nulls(pb["liquidity"], "разбивку прочих активов и книги ликвидности модель не ведёт")
    f = bal["funds"]
    f.update(nulls(pb["funds"], "разбивку средств юрлиц модель не ведёт"))
    f["retail_total"] = calc(book[RETAIL_CURRENT] + book[RETAIL_TERM], "текущие счета + срочные средства физлиц")
    f["retail_current"] = dict(bal["books"][RETAIL_CURRENT])
    f["retail_term"] = dict(bal["books"][RETAIL_TERM])
    bal["wholesale"] = nulls(pb["wholesale"], "разбивку оптового фондирования модель не ведёт")
    bal["allowance_ac"] = en("balance.allowance", f"резерв по кредитам на {on} (величиной)")
    bal["other_assets"] = en("balance.other_assets", f"прочие активы на {on}")
    bal["other_assets_parts"] = {k: none("разбивку прочих активов модель не ведёт") for k in pb["other_assets_parts"]}
    fixed0 = pb["other_assets_fixed"]
    bal["other_assets_fixed"] = (en("balance.other_assets_fixed", f"постоянные прочие активы на {on}")
                                 if has("balance.other_assets_fixed") else kept(fixed0))
    share = bal["other_assets_fixed"]["v"] / fixed0["v"] if fixed0["v"] else 0.0
    bal["other_assets_fixed_parts"] = {k: calc(v["v"] * share, f"часть постоянных прочих активов — долей на {d_ru(old.date)}")
                                       for k, v in pb["other_assets_fixed_parts"].items()}
    bal["other_assets_growing_parts"] = {k: none("растущую часть прочих активов модель по строкам не ведёт")
                                         for k in pb["other_assets_growing_parts"]}
    bal["fixed_share_of_deductible"] = kept(pb["fixed_share_of_deductible"])
    bal["other_liabilities"] = en("balance.other_liabilities", f"прочие обязательства на {on} (без дивидендов к выплате)")
    bal["other_liabilities_parts"] = {k: none("разбивку прочих обязательств модель не ведёт") for k in pb["other_liabilities_parts"]}
    bal["dividends_payable"] = en("balance.dividends_payable", f"дивиденды к выплате на {on}")
    if has("balance.dividends_payable_year"):
        bal["dividends_payable_year"] = int(dig(report, "balance.dividends_payable_year"))
    declared = dig(report, "balance.dividends_payable_declared") if has("balance.dividends_payable_declared") else []
    bal["dividends_payable_declared"] = [
        {"period": str(x["period"]), "amount": node(r6(float(x["amount"])), src=ref("balance.dividends_payable_declared"),
                                                     calc=f"отчёт квартала: объявлено и не выплачено на {on}")}
        for x in declared]
    eq, peq = bal["equity"], pb["equity"]
    for k in ("at1", "nci"):
        eq[k] = en(f"balance.{k}", f"{k} на {on}") if has(f"balance.{k}") else kept(peq[k])
    eq["bv_common"] = en("balance.bv_common", f"капитал обыкновенных акционеров на {on}")
    bv, at1, nci = eq["bv_common"]["v"], eq["at1"]["v"], eq["nci"]["v"]
    eq["total"] = calc(bv + at1 + nci, "bv_common + at1 + nci")
    eq["shareholders"] = calc(bv + at1, "bv_common + at1")
    for k in ("share_capital", "share_premium", "treasury_cost", "other_funds", "retained_earnings", "tangible_common",
              "tangible_common_ex_dta"):
        if k in eq:
            eq[k] = none("компонент капитала модель отдельно не ведёт")
    al, oa = bal["allowance_ac"]["v"], bal["other_assets"]["v"]
    sum_a, sum_l = sum(book[b] for b in assets_b), sum(book[b] for b in liabs_b)
    total_a = sum_a - al + oa
    total_l = sum_l + bal["other_liabilities"]["v"] + bal["dividends_payable"]["v"]
    bal["total_assets"] = calc(total_a, "Σ книг активов − резерв + прочие активы")
    bal["total_liabilities"] = calc(total_l, "Σ книг пассивов + прочие обязательства + дивиденды к выплате")
    checks.append(("отчёт квартала: активы = обязательства + капитал", abs(total_a - (total_l + eq["total"]["v"])) < 0.05,
                   f"активы {ru(total_a)}, обязательства и капитал {ru(total_l + eq['total']['v'])}"))
    listed = sum(x["amount"]["v"] for x in bal["dividends_payable_declared"])
    checks.append(("отчёт квартала: объявленные и не выплаченные дивиденды — часть остатка к выплате; постоянные прочие активы — "
                   "часть прочих", listed <= bal["dividends_payable"]["v"] + 1e-6 and 0 <= bal["other_assets_fixed"]["v"] <= oa,
                   f"по периодам {ru(listed, 3)} из {ru(bal['dividends_payable']['v'], 3)}; постоянные прочие активы "
                   f"{ru(bal['other_assets_fixed']['v'])} из {ru(oa)}"))
    if new.year != old.year:                           # новый год якоря: концы прошлого года — прежний якорь
        ends = {}
        for seg in ("corporate", "retail"):
            names = [b for b in loans_b if BOOKS[b]["segment"] == seg]
            ends[f"loans_{seg}"] = node(r6(sum(float(pb["books"][b]["v"]) for b in names)),
                                        calc=f"кредитные книги сегмента на {d_ru(old.date)}: balance.json фактов {old.period}")
        bal["prev_year_end"] = {"as_of": old.date, **ends}
    loans, funds = sum(book[b] for b in loans_b), sum(book[b] for b in (RETAIL_CURRENT, RETAIL_TERM, "corp_funds"))
    bal["iea"] = calc(sum_a, "процентные активы движка: Σ пяти книг активов")
    hist_books = lambda src_books, how: {b: node(r9(float(src_books[b])), calc=how) for b in BOOKS}   # noqa: E731
    if old.period not in bal["history"]:              # конец прежнего якоря уходит в историю
        bal["history"][old.period] = {
            "date": old.date, "bv_common": node(float(peq["bv_common"]["v"]), calc=f"факты {old.period}"),
            "loans": node(r6(sum(float(pb["books"][b]["v"]) for b in loans_b)), calc=f"факты {old.period}"),
            "iea": node(r6(sum(float(pb["books"][b]["v"]) for b in assets_b)), calc=f"факты {old.period}")}
    if "books" not in bal["history"][old.period]:
        bal["history"][old.period]["books"] = hist_books({b: pb["books"][b]["v"] for b in BOOKS},
                                                         f"balance.books прежнего якоря {old.period}")
    bal["history"][new.period] = {
        "date": d, "bv_common": calc(bv, "balance.equity.bv_common"),
        "equity_shareholders": calc(bv + at1, "bv_common + at1"), "equity_total": calc(bv + at1 + nci, "bv_common + at1 + nci"),
        "loans": calc(loans, "сумма кредитных книг"),
        "loans_ac_gross": calc(loans, "= loans: отдельной книги кредитов по справедливой стоимости нет"),
        "loans_gross_reported": none("кредиты в отчётном виде (с обратным репо) модель не ведёт"),
        "allowance_ac": calc(al, "balance.allowance_ac"),
        "funds": calc(funds, "средства клиентов: текущие счета и срочные средства физлиц + средства юрлиц"),
        "iea": calc(sum_a, "balance.iea"), "total_assets": calc(total_a, "balance.total_assets"),
        "books": hist_books(book, f"отчёт квартала: balance.books на {on}"),
    }

    # ---------------- nii_books.json: ставки якоря несут весь ЧПД
    nb = out["nii_books"]
    nb.update(as_of=d, period=new.period, days=node(days, calc=f"дней в квартале {kq} (act/365)"), rates_carry_residual=True)
    nb["note"] = (f"ЯКОРЬ ИЗ ОТЧЁТА КВАРТАЛА {new.period}: проценты книг — из файла «{name}»; ставки якоря несут весь ЧПД (остаток "
                  "вне книг разнесён по книгам активов, REANCHOR §3.6)")
    interest = {b: abs(num(f"interest.{b}")) for b in BOOKS}
    nii, dia = num("pnl.nii"), abs(num("dia"))
    # надбавка за субординацию (`pnl.t2_premium` ожидаемого отчёта — ряд клетки со своим знаком) — вне книг, её несёт ключ книги:
    # остаток «ЧПД − проценты книг» — без неё, тем же счётом, что у reanchor.py (nii + t2_premium − …); на ожидании модели он ноль
    t2p = num("pnl.t2_premium") if has("pnl.t2_premium") else 0.0
    residual, scale = carry_scale(interest, nii + t2p, dia)
    inc, exp = sum(interest[b] for b in assets_b), sum(interest[b] for b in liabs_b)
    checks.append(("отчёт квартала: проценты книг дают ЧПД отчёта (остаток вне книг — меньше 10 % ЧПД)",
                   abs(residual) < 0.10 * abs(nii), f"Σ книг − страхование вкладов {ru(nii - residual)}, ЧПД {ru(nii)}, "
                                                    f"остаток {ru(residual, 3)}"))
    for b in BOOKS:
        bo, bc = float(pb["books"][b]["v"]), book[b]
        avg = (bo + bc) / 2
        asset = b in assets_b
        how = (f"interest_q × (1 + остаток ЧПД {ru(residual, 3)} / Σ процентов книг активов {ru(inc)}) / balance_avg × 365/{days}: "
               "ставка книги активов несёт долю процентов вне книг") if asset else f"interest_q / balance_avg × 365/{days}"
        nb["books"][b] = {
            "balance_open": node(bo, calc=f"остаток книги на {d_ru(old.date)} (balance.books.{b} фактов {old.period})"),
            "balance_close": node(r9(bc), calc=f"остаток книги на {on} (balance.books.{b})"),
            "balance_avg": node(r9(avg), calc="(balance_open + balance_close) / 2"),
            "interest_q": en(f"interest.{b}", f"проценты книги за {kq} (величиной)", value=interest[b]),
            "rate_anchor": node(round(interest[b] * (scale if asset else 1.0) / avg * 365 / days, 9), src=ref(f"interest.{b}"),
                                calc=f"отчёт квартала: {how}"),
        }
    iea_avg = sum((float(pb["books"][b]["v"]) + book[b]) / 2 for b in assets_b)
    nb.update(
        interest_assets_q=calc(inc, "Σ interest_q книг активов"),
        interest_liabilities_q=calc(exp, "Σ interest_q книг пассивов (величиной)"),
        other_interest_net_q=calc(residual, "остаток: nii_q (без надбавки за субординацию) − (Σ процентов книг активов − Σ "
                                            "пассивов − dia_q); разнесён по ставкам книг активов (rates_carry_residual)"),
        dia_q=en("dia", f"расходы на страхование вкладов за {kq}, величиной", value=dia),
        nii_q=en("pnl.nii", f"ЧПД за {kq}"),
        iea_avg=calc(iea_avg, "Σ balance_avg книг активов"),
        nim_eng_q=node(round(nii * 365 / days / iea_avg, 9), calc=f"отчёт квартала: nii_q × 365/{days} / iea_avg (ЧПМ базиса движка)"),
        current_share_anchor=node(round(book[RETAIL_CURRENT] / (book[RETAIL_CURRENT] + book[RETAIL_TERM]), 9),
                                  calc="отчёт квартала: текущие счета физлиц / (текущие счета + срочные средства) на якоре"),
        key_avg_anchor_q=en("market.key_avg", f"средняя ключевая ставка за {kq}"),
        check=calc(inc - exp - dia + residual - (nii + t2p), "Σ активов − Σ пассивов − dia_q + other_interest_net_q − "
                                                            "(nii_q + надбавка за субординацию)"),
    )

    # ---------------- pnl_quarterly.json
    pq = out["pnl_quarterly"]
    pq["as_of"] = d
    last_row = prev["pnl_quarterly"]["quarters"][old.period]
    row = {k: none("строку отчёта модель отдельно не ведёт") for k, v in last_row.items() if isinstance(v, dict) and "v" in v}
    for k in EXPECTED_SECTIONS["pnl"][0]:
        row[k] = en(f"pnl.{k}", f"строка движка за {kq}")
    for k in ("oci_fvoci", "other_equity_movements"):
        if has(f"pnl.{k}"):
            row[k] = en(f"pnl.{k}", f"движение капитала за {kq}")
    lines = sum(row[k]["v"] for k in EXPECTED_SUM if k != "misc_net")
    row["misc_net"] = (en("pnl.misc_net", f"прочие строки за {kq}") if has("pnl.misc_net")
                       else calc(row["pbt"]["v"] - lines, "pbt − (nii + llp_debt_fa + fees_net + insurance_net + noncore_net + opex)"))
    p = {k: row[k]["v"] for k in EXPECTED_SECTIONS["pnl"][0] + ("misc_net",)}
    row["ni_nci"] = calc(p["ni"] - p["ni_shareholders"], "ni − ni_shareholders")
    row["dia"] = calc(dia, "nii_books.dia_q: расходы на страхование вкладов, величиной")
    row["at1_coupon"] = kept(last_row["at1_coupon"])
    row["key_avg"] = en("market.key_avg", f"средняя ключевая ставка за {kq}")
    if dig(report, "pnl").get("estimated") is True:    # прибыль квартала — напечатанное значение: точное придёт позже
        for k in ("ni_shareholders", "ni", "ni_nci", "pbt", "tax", "misc_net", "noncore_net"):
            row[k]["estimated"] = True
    pq["quarters"][new.period] = row
    s = sum(p[k] for k in EXPECTED_SUM)
    checks.append((f"отчёт квартала: прибыль до налога {kq} = сумме строк; прибыль = прибыль до налога + налог; расходы — "
                   "со знаком минус", abs(s - p["pbt"]) < 0.05 and abs(p["pbt"] + p["tax"] - p["ni"]) < 0.05 and p["opex"] < 0,
                   f"Σ строк {ru(s, 2)} против {ru(p['pbt'], 2)}; налог {ru(p['tax'], 2)}, прибыль {ru(p['ni'], 2)}"))

    # ---------------- capital.json
    cap0, cap = prev["capital"], out["capital"]
    cap["as_of"] = d
    estimated = dig(report, "capital").get("estimated") is True
    flag = {"estimated": True} if estimated else {}
    form = cap0["n20_0"]["basis"].split(":")[0]
    t2 = (en("capital.t2", f"регуляторные инструменты группы без прибыли на {on}", basis=form) if has("capital.t2")
          else kept(cap0["t2_recognized"], basis=form))
    cet1, rwa, base = num("capital.basel_cet1"), num("capital.basel_rwa"), num("capital.bank_base_capital")
    pre = bool(dig(report, "capital.n20_pre_dividend"))
    for slot, what in (("n20_0", "Н20.0"), ("n1_1_bank", "Н20.1")):
        block = {"basis": cap0[slot]["basis"], "value": en(f"capital.{slot}", f"{what} банковской группы на {on}", **flag),
                 "as_of": d, "estimated": estimated}
        if estimated:
            est_ = dig(report, f"capital.estimate.{slot}")
            block["estimate"] = {"bank_value": node(float(est_["bank_value"]), src=ref(f"capital.estimate.{slot}.bank_value"),
                                                    calc="норматив банка на дату якоря"),
                                 "spread": node(float(est_["spread"]), src=ref(f"capital.estimate.{slot}.spread"),
                                                calc="норматив группы − норматив банка на последнюю общую дату"),
                                 "spread_as_of": str(est_["spread_as_of"])}
        cap[slot] = block
    cap["n20_0"]["pre_dividend"] = pre
    cap["n20_0"]["pre_dividend_note"] = ("норматив — до вычета объявленных дивидендов из регуляторного капитала" if pre else
                                         "объявленных и не вычтенных из норматива дивидендов на якоре нет")
    for k in ("n20_2", "n1_1_bank_ras", "n1_2_bank", "n1_0_bank"):
        cap[k] = none("норматив вне слотов ядра модель не ведёт", basis=cap0[k].get("basis"))
    cap["bank_base_capital"] = en("capital.bank_base_capital", f"базовый капитал банковской группы на {on} (слот ядра)",
                                  basis=form, **flag)
    total = cet1 + t2["v"]
    cap["group_capital"] = {"basis": cap0["group_capital"]["basis"], "total": calc(total, "basel.cet1 + t2_recognized", **flag),
                            "base": calc(base, "bank_base_capital", **flag),
                            "additional": none("добавочный капитал группы модель отдельно не ведёт"),
                            "supplementary": calc(t2["v"], "t2_recognized", **flag),
                            "tier1": none("основной капитал группы модель отдельно не ведёт")}
    cap["basel"] = {"basis": cap0["basel"]["basis"], "as_of": d,
                    "cet1": en("capital.basel_cet1", f"капитал группы без регуляторных инструментов на {on}", **flag),
                    "rwa": en("capital.basel_rwa", f"активы, взвешенные по риску, на {on}", **flag),
                    **{k: none("активы для второго и третьего нормативов модель не ведёт") for k in ("rwa_n20_1", "rwa_n20_2")},
                    "rwa_n20_0": en("capital.basel_rwa", f"активы для Н20.0 на {on}", **flag),
                    "cet1_ratio": calc(cet1 / rwa, "basel.cet1 / basel.rwa", **flag),
                    "total_ratio": calc(total / rwa, "group_capital.total / basel.rwa", **flag),
                    "rwa_to_assets": calc(rwa / total_a, "basel.rwa / balance.total_assets")}
    cap["t2_recognized"] = t2
    cap["fvoci_reserve"] = en("balance.fvoci_reserve", "фонд переоценки бумаг после налога", basis="IFRS")
    for k in ("fvoci_reserve_check", "insurance_fin_reserve", "fvoci_reserve_net_of_insurance"):
        cap[k] = none("фонды капитала по строкам модель не ведёт", basis="IFRS")
    cap["ofz_curve_anchor"] = {"basis": "отчёт квартала (у ожидаемого отчёта — кривая миров слоя «свой взгляд»)", "as_of": d,
                               **{t: en(f"market.ofz_curve.{t}", f"бескупонная доходность ОФЗ {t} лет на {on}") for t in CURVE_NODES}}
    hist_row = {"period": new.period, "date": d,
                "n20_0": calc(cap["n20_0"]["value"]["v"], "capital.n20_0.value", basis=form, **flag),
                "n20_1": calc(cap["n1_1_bank"]["value"]["v"], "capital.n1_1_bank.value", basis=form, **flag),
                "n20_2": none("третий норматив группы модель не ведёт", basis=form),
                "capital_total": calc(total, "group_capital.total", basis=form, **flag),
                "capital_base": calc(base, "bank_base_capital", basis=form, **flag),
                "capital_additional": none("добавочный капитал группы модель не ведёт", basis=form),
                "capital_supplementary": calc(t2["v"], "t2_recognized", basis=form, **flag)}
    cap["history"] = [h for h in cap["history"] if h.get("period") != new.period] + [hist_row]
    checks.append(("отчёт квартала: вычеты якоря (капитал акционеров − капитал группы без инструментов) положительны",
                   0 < bv - cet1 < bv, ru(bv - cet1, 3)))

    # ---------------- shares.json
    out["shares"]["as_of"] = d
    for k in EXPECTED_SECTIONS["shares"][1]:
        if has(f"shares.{k}"):
            out["shares"][k] = en(f"shares.{k}", f"число акций на {on}, млн шт.")

    # ---------------- dividends.json: решения закрываемого квартала — строки истории (годовой календарь, база объёма iea)
    div = out["dividends"]
    div["as_of"] = d
    rows = {h["period"]: h for h in div["history"]}
    n_iss = float(out["shares"]["issued_total"]["v"])
    for i, x in enumerate(dig(report, "dividend_decisions") if has("dividend_decisions") else []):
        per, dps = str(x["period"]), float(x["dps"])
        where = f"dividend_decisions.{i}"
        if not old.date < str(x["decided_date"]) <= d:
            raise BuildError(f"отчёт квартала: {where}.decided_date {x['decided_date']} — решение закрываемого квартала: позже "
                             f"{d_ru(old.date)} и не позже {on}")
        h = rows.get(per)
        if h is None:
            h = {"year": q_parse(per)[0], "period": per}
            div["history"].append(h)
            rows[per] = h
        if h.get("dps") is None or abs(float(h["dps"]["v"]) - dps) > 1e-6:
            h["dps"] = node(dps, src=ref(f"{where}.dps"), calc="отчёт квартала: дивиденд на акцию, ₽")
            h["pool_declared"] = (node(r6(float(x["pool_declared"])), src=ref(f"{where}.pool_declared"),
                                       calc="отчёт квартала: сумма на все размещённые акции")
                                  if x.get("pool_declared") is not None else
                                  calc(dps * n_iss / 1000, "DPS × размещённые акции / 1000"))
        if x.get("pool_all_classes") is not None:     # сумма, вычтенная из bv_common: база объёма iea (М§4.7)
            h["pool_all_classes"] = node(r9(float(x["pool_all_classes"])), src=ref(f"{where}.pool_all_classes"),
                                         calc="отчёт квартала: сумма по всем категориям акций")
        h["decided_date"] = str(x["decided_date"])
        for k in ("record_date", "pay_date"):
            if x.get(k) is not None:
                h[k] = str(x[k])
    div["register_seed"] = [s_ for s_ in div.get("register_seed") or []
                            if not (s_.get("ex_date") or s_.get("record_date")) or str(s_.get("ex_date") or s_["record_date"]) > d]

    # ---------------- bridge_mgmt_ifrs.json и mgmt_quarterly.json
    br = out["bridge_mgmt_ifrs"]
    br["as_of"] = d
    l0 = sum(float(pb["books"][b]["v"]) for b in loans_b)
    i0 = sum(float(pb["books"][b]["v"]) for b in assets_b)
    income = sum(p[k] for k in ("nii", "fees_net", "insurance_net", "misc_net"))
    engine = {"cor": (-p["llp_debt_fa"] * 365 / days / ((l0 + loans) / 2),
                      f"−llp_debt_fa {ru(p['llp_debt_fa'], 3)} × 365/{days} / средняя сумма кредитных книг {ru((l0 + loans) / 2, 2)}"),
              "nim": (nii * 365 / days / ((i0 + sum_a) / 2),
                      f"nii {ru(nii, 3)} × 365/{days} / средние процентные активы движка {ru((i0 + sum_a) / 2)}"),
              "cir": (-p["opex"] / income, f"−opex {ru(p['opex'], 3)} / (nii + fees_net + insurance_net + misc_net) {ru(income, 3)}")}
    window = prev["bridge_mgmt_ifrs"].get("window")
    mgmt_nodes = {}
    for x_, (eng, how) in engine.items():
        block, pblock = br[x_], prev["bridge_mgmt_ifrs"][x_]
        if not has(f"mgmt.{x_}"):
            mgmt_nodes[x_] = calc(eng - float(pblock["value"]["v"]),
                                  f"упр. базис через мост: engine − bridge_mgmt_ifrs.{x_}.value фактов {old.period}")
            continue
        mg = en(f"mgmt.{x_}", f"упр. {MGMT_WORDS[x_]} за {kq}")
        mgmt_nodes[x_] = mg
        gap = eng - mg["v"]
        line = {"period": new.period, "mgmt": dict(mg), "engine": node(round(eng, 9), calc=how),
                "gap": node(round(gap, 9), calc="engine − mgmt")}
        have = {k for r in pblock.get("history") or [] for k in r}
        level = gap
        if "gap_x4" in have:                           # база «× 4» без ряби счёта дней
            eng4 = eng * 4 * days / 365
            line["engine_x4"] = node(round(eng4, 9), calc="engine × 4 вместо × 365/дни")
            line["gap_x4"] = node(round(eng4 - mg["v"], 9), calc="engine_x4 − mgmt")
            if bridge_series(pblock) == "gap_x4":
                level = eng4 - mg["v"]
        block["history"].append(line)
        own, value0 = pblock["window"], float(pblock["value"]["v"])
        n0 = int((pblock.get("n") or {}).get("v") or 0)
        yearly = (isinstance(window, list) and str(own[0]) != str(window[0]) and q_parse(str(own[0])) == (old.year, 1))
        if yearly and new.year != old.year:            # окно значения — отчётные кварталы года якоря
            block["window"], n1 = [new.period, new.period], 1
            block["value"] = node(round(level, 9), calc=f"уровень первого отчётного квартала года якоря {new.period} (n = 1)")
        else:
            block["window"], n1 = [own[0], new.period], n0 + 1
            block["value"] = node(round((value0 * n0 + level) / n1, 9),
                                  calc=f"среднее по окну {own[0]}–{new.period}: значение фактов {old.period} продлено кварталом "
                                       f"(n = {n1})")
        block["n"] = node(n1, calc="кварталов в окне")
        block["sd"] = none("разброс по окну считается из листов этапа 1")
        for k in ("value_six_quarters", "value_median_rule"):
            if k in block:
                block[k] = none("справочное значение моста — из листов этапа 1")
        checks.append((f"отчёт квартала: мост «{MGMT_WORDS[x_]}» упр. ↔ движок", True,
                       f"{ru(value0 * 100, 4)} → {ru(block['value']['v'] * 100, 4)} п.п. (n = {n1})"))
    if isinstance(window, list):
        br["window"] = [window[0], new.period]
    mq = out["mgmt_quarterly"]
    mq["as_of"] = d
    mrow = {k: none("управленческую метрику модель не ведёт") for k in prev["mgmt_quarterly"]["quarters"][old.period]}
    for x_ in ("nim", "cor", "cir"):
        mrow[x_] = dict(mgmt_nodes[x_])
    mq["quarters"][new.period] = mrow

    # ---------------- bridge_ras_ifrs.json, guidance.json: состав прежний
    out["bridge_ras_ifrs"]["as_of"] = d
    checks.append(("гайденс — как в фактах прежнего якоря", True,
                   f"год гайденса {out['guidance']['year']}" + ("" if int(out["guidance"]["year"]) == new.year else
                                                              f" при якоре {new.period}: гайденс нового года — из листов этапа 1")))

    # ---------------- anchor.json: отчёт — документ реестра
    an = out["anchor"]
    an.update(as_of=d, period=new.period,
              note=(f"ЯКОРЬ ИЗ ОТЧЁТА КВАРТАЛА (сухой прогон перезаякоривания, docs/MODEL.md §15.2): числа {new.period} — из файла "
                    f"«{name}» (у ожидаемого отчёта — ожидание модели, не отчётность); кварталы по {old.period} — факты. "
                    "В data/facts не кладётся"),
              expected={"period": new.period, "from_anchor": old.period, "report": name, "sha256": sha,
                        "source": "; ".join(str(report[k]) for k in ("source", "note") if report.get(k))})
    an["documents"] = an["documents"] + [{
        "key": f"quarter_report_{new.period}", "file": None, "sha256": sha, "url": None,
        "title": f"Отчёт квартала {new.period} (quarter-report/1) — вход сухого прогона перезаякоривания; не отчётность",
    }]
    return {k: out[k] for k in BUILT}, checks


def main_expected(a) -> int:
    """Режим --expected: факты следующего квартала из фактов якоря и отчёта квартала; только в --out."""
    source = a.facts or FACTS
    if a.out is None or a.out.resolve() == FACTS.resolve():
        print("ПРОВАЛ: --expected пишет только в --out, и это не data/facts (ожидание — не факт)", file=sys.stderr)
        return 1
    try:
        raw = a.expected.read_bytes()
        report = json.loads(raw.decode("utf-8"))
        prev = {k: json.loads((source / f"{k}.json").read_text(encoding="utf-8")) for k in BUILT}
        if a.anchor and isinstance(report, dict) and a.anchor != report.get("period"):
            raise BuildError(f"--anchor {a.anchor}, а отчёт квартала — за {report.get('period')}")
        files, checks = expected_facts(prev, report, name=a.expected.name, sha=hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"ПРОВАЛ: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    except BuildError as e:
        print(f"ПРОВАЛ сборки: {e}", file=sys.stderr)
        return 1
    print(f"якорь {files['anchor']['period']} ({files['anchor']['as_of']}) из фактов {prev['anchor']['period']} и {a.expected.name}")
    for name, ok, detail in checks:
        print(f"{'ок  ' if ok else 'СБОЙ'} {name}: {detail}")
    if any(not ok for _, ok, _ in checks):
        print("ПРОВАЛ: отчёт квартала не сошёлся — файлы не записаны", file=sys.stderr)
        return 1
    manual = {k: (source / f"{k}.json").read_text(encoding="utf-8") for k in MANUAL if (source / f"{k}.json").exists()}
    if a.check:
        diff = [k for k, v in files.items() if not (a.out / f"{k}.json").exists()
                or (a.out / f"{k}.json").read_bytes() != dumps(v).encode("utf-8")]
        if diff:
            print(f"РАСХОЖДЕНИЕ с {a.out}: " + ", ".join(f"{k}.json" for k in diff), file=sys.stderr)
            return 1
        print(f"ок: {len(files)} файлов совпали с {a.out}")
        return 0
    write(files, a.out)
    for k, body in manual.items():                     # календарь и аналоги ведутся вручную: копия прежних
        with open(a.out / f"{k}.json", "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
    print(f"записано: {len(files)} файлов в {a.out}" + (f"; скопированы без изменений: {', '.join(manual)}" if manual else ""))
    return 0


# ------------------------------------------------------------------ командная строка

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Факты ВТБ: факты прежнего якоря + листы квартала этапа 1 (папка передачи — "
                                             "BANK_HANDOFF_DIR)")
    ap.add_argument("--check", action="store_true", help="сверить с каталогом выхода, не писать")
    ap.add_argument("--out", type=Path, default=None, help="каталог для записи (по умолчанию data/facts)")
    ap.add_argument("--anchor", default=None, metavar="ПЕРИОД",
                    help="квартал якоря вида ГГГГQк (по умолчанию — period из data/facts/anchor.json); листы — "
                         "stage1/facts-<ПЕРИОД>/sheets папки передачи")
    ap.add_argument("--base", type=Path, default=None, metavar="КАТАЛОГ",
                    help="факты прежнего квартала (по умолчанию — data/facts, если они на прежнем квартале, иначе последний "
                         "коммит истории git, где data/facts стоят на нём)")
    ap.add_argument("--report", type=Path, default=None, metavar="ФАЙЛ",
                    help="записать файл отчёта квартала якоря (quarter-report/1) — вход reanchor.py --facts")
    ap.add_argument("--expected", type=Path, default=None, metavar="ФАЙЛ",
                    help="сухой прогон перезаякоривания: факты следующего квартала из фактов якоря и отчёта квартала "
                         "(quarter-report/1, его пишет reanchor.py --expected); пишет только в --out; папка передачи не нужна")
    ap.add_argument("--facts", type=Path, default=None, metavar="КАТАЛОГ",
                    help="с --report: готовый каталог фактов вместо сборки из папки передачи; с --expected: каталог фактов "
                         "прежнего якоря (по умолчанию data/facts)")
    a = ap.parse_args(argv)
    if a.expected is not None:
        return main_expected(a)
    try:
        if a.report is not None and a.facts is not None:
            files = {k: json.loads((a.facts / f"{k}.json").read_text(encoding="utf-8")) for k in BUILT}
            if a.anchor and a.anchor != files["anchor"]["period"]:
                raise BuildError(f"--anchor {a.anchor}, а факты в {a.facts.name} — на {files['anchor']['period']}")
            write_report(files, a.report, source=f"факты сборщика на якоре {files['anchor']['period']}")
            return 0
        root = os.environ.get("BANK_HANDOFF_DIR")
        if not root:
            print("ПРОВАЛ: BANK_HANDOFF_DIR не задан — нужна папка передачи с листами этапа 1", file=sys.stderr)
            return 1
        anchor = Anchor(a.anchor or default_anchor())
        if not (Path(root) / anchor.stage / "sheets").is_dir():
            raise BuildError(f"нет листа якоря {anchor.period}: нет каталога {anchor.stage}/sheets в папке передачи")
        base = load_base(anchor, a.base)
        files, checks = build(Path(root), anchor, base)
    except (OSError, ValueError, KeyError) as e:
        print(f"ПРОВАЛ: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    except BuildError as e:
        print(f"ПРОВАЛ сборки: {e}", file=sys.stderr)
        return 1
    print(f"якорь {anchor.period} ({anchor.date})")
    for name, ok, detail in checks:
        print(f"{'ок  ' if ok else 'СБОЙ'} {name}: {detail}")
    if any(not ok for _, ok, _ in checks):
        print("ПРОВАЛ: сверки не сошлись — файлы не записаны", file=sys.stderr)
        return 1
    target = a.out or FACTS
    if a.check:
        diff = [k for k, v in files.items() if not (target / f"{k}.json").exists()
                or (target / f"{k}.json").read_bytes() != dumps(v).encode("utf-8")]
        if diff:
            print(f"РАСХОЖДЕНИЕ с {target}: " + ", ".join(f"{k}.json" for k in diff), file=sys.stderr)
            return 1
        print(f"ок: {len(files)} файлов совпали с {target}")
    else:
        write(files, target)
        print(f"записано: {len(files)} файлов в {target}")
    if a.report is not None:
        try:
            write_report(files, a.report, source=f"листы этапа 1, якорь {anchor.period}")
        except BuildError as e:
            print(f"ПРОВАЛ сборки: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
