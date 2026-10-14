# -*- coding: utf-8 -*-
"""Независимая контрольная модель панели — ГОДОВАЯ, с квартальным проходом капитала (docs/MODEL.md §17).

Написана только по тексту docs/MODEL.md, книге (data/assumptions/) и фактам (data/facts/);
каталог ядра не импортируется и не читается (tests/test_control_independence.py). Шаг —
год: неполный год якоря — один период (доля года = оставшиеся кварталы / 4), далее годы до
года last_period, терминал М§7 в годовой форме. Две ветви — по ключам книги: без квартального
календаря дивидендов и без ограничения роста — годовая ветвь образца (решение раз в год); с ними —
годовые строки ОПУ и квартальный проход капитала внутри года (остатки кредитных книг, RWA, нормативы,
требование с глиссадой, решения о дивиденде, доля прироста и навёрстывание — по кварталам). У книги с
включённой докапитализацией (М§4.14) годовая ветвь в квартал решения о взносе — квартал собрания, а при ключе
capital.recapitalization.decision_quarter квартал с этим номером в году — принимает решение о взносе акционеров
своим пробным проходом, оценка идёт в формах М§6.5 с терминалом по цене размещения; у книги с ключом пола
клетки (М§8.2) клетка входит в смесь слоя не ниже пола. Клеток — сколько троек в перечнях книги (миры × режимы ×
сценарии требования, М§3); клетка нулевой вероятности считается наравне с прочими. У книги с ключами доли вычета
якоря, постоянной в рублях (capital.n20.deductions_fixed_share и capital.n11.deductions_fixed_share, М§4.11), вычет
каждого норматива — растущая с RWA часть и постоянная сумма якоря: одной функцией всюду, где считается норматив,
в обеих ветвях. Траектории книги читаются по правилам М§0.4 буквально (значение года, заданный год, одиночный
ключ, начало траектории). Пятый проход (М§4.3, §4.11, §7) — своим счётом в обеих ветвях: вычет сценария в рублях
(capital.reg_scenarios.<s>.deduction_rub) прибавляется к вычету норматива без множителя RWA всюду, где считается
норматив; путь постоянной части прочих активов (volumes.other_assets_fixed_change, вес риска приращения
capital.rwa.density.other_assets_fixed_change) стоит в прочих активах и RWA, деньги убывания — в балансирующих
статьях; доля λ_F (valuation.terminal.fixed_growth_share) делит постоянные части обеих сторон на T на растущую с
бизнесом и стоящую в рублях. Седьмой проход (М§4.11, §7) — своим счётом в обеих ветвях: у книги с ключом доли
инструментов (capital.n20.t2_share) клетка с квартала ключа держит дополнительный капитал долей своих RWA, которую
задаёт её шаг квартала перед ключом, — всюду, где считается Н20.0, и в блоке постоянных частей терминала. Восьмой
проход (М§4.4, §4.9–§4.11, §7) — своим счётом в обеих ветвях: у книги с ключом capital.at1_share клетка с квартала ключа
держит добавочный капитал долей своих RWA (строка пассивов, деньги выпуска — в балансирующих активах с конца своего
квартала, RWA — неподвижная точка М§4.10 в закрытой форме), купон сверх базы — по ставке новых выпусков своего мира
после налога; у книги с ключом capital.n20.t2_premium T2 сверх базы несёт надбавку к ставке опта в ЧПД; у книги с
ключом valuation.terminal.other_movements: flat_rub прочие движения капитала продолжаются за концом сетки слагаемым
OM_ann / k_T. Девятый проход (М§4.8, §4.9, §5.2, §7) — своим счётом в обеих ветвях: у книги с ключом tax.structure налог —
правилом в рублях (законная ставка, прочие постоянные разницы с положительной прибыли, льгота дохода книги бумаг своей
клетки, экономия купона бессрочных — в налоге) на квартальном профиле годовой строки, купон в совокупном доходе и в базе
дивиденда — целиком, терминал — тем же правилом; у книги с ключом capital.at1_coupon купон якоря — фиксированная часть и
плавающая сумма по средней ключевой своего мира за четыре квартала купона, за T — по ключевой последнего квартала сетки.
Что считается иначе, чем в ядре, и почему совпадение ожидается только в допусках — docs/CONTROL-MODEL.md.

Чисел книги и фактов в коде нет: только имена ключей и структурные константы (кварталов в
году, дней в году по act/365, млрд → млн, технические допуски итераций).

Запуск:
    python -B tests/independent_model.py                      сводка на машинной книге и фактах
    python -B tests/independent_model.py --json out.json      то же + полный результат в JSON
    python -B tests/independent_model.py --gates              то же + числа гейтов знака, печатаемая маржа и уровни
                                                              после фазы роста (М§14.2)
    python -B tests/independent_model.py --draft --worlds-lt N=<доля>,H=<доля> [--facts DIR]
        шаблон книги (assumptions_template.yaml) + миры из worlds_source.json и надстройка
        worlds_bank.json (узел LT кривой миров N и H — правило сборки семейства, передаётся явно;
        M — правило рецепта)
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import math
import sys
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOK_DIR = ROOT / "data" / "assumptions"
BOOK_YAML = BOOK_DIR / "assumptions.yaml"
DRAFT_YAML = BOOK_DIR / "assumptions.draft.yaml"
TEMPLATE_YAML = BOOK_DIR / "assumptions_template.yaml"
WORLDS_SOURCE = BOOK_DIR / "worlds_source.json"
WORLDS_BANK = BOOK_DIR / "worlds_bank.json"
FACTS_DIR = ROOT / "data" / "facts"

LAYERS = ("analytical", "market_implied", "macro_neutral")
LAYER_OWN, LAYER_MARKET = LAYERS[0], LAYERS[-1]     # слои «свой взгляд» и «рыночные ставки как есть» (М§9)
# Миры из текста методики: реализованная передача — разность M и N (М§4.5); κ-добавка к CoR без ключа
# книги — относительно мира N и только вверх, с ключом credit.kappa_reference_world — относительно
# названного им мира-опоры, с любым знаком (М§4.6).
W_LOW = "N"
W_MKT = "M"
SCOPE_MARKET = "market_layer"       # checks.cir_lt.scope: цель C/I сверяется со слоем «рыночные ставки как есть»
SCOPE_MODAL = "modal_cell"          # явное имя умолчания: модальная клетка, как без ключа scope
FADE_SYMMETRIC = "symmetric"        # valuation.terminal.fade_mode справочного варианта таблиц книги (М§7)
MIX_MODAL, MIX_POINT = "modal", "point"     # смеси узла уровней сверх слоёв: модальная клетка и смесь точки
R_NORM = "norm"             # режим, к которому относится цель A-N2 и кредитная маржа стационара (М§4.5)
R_CRISIS = "crisis"         # режим с годом шока, разовым убытком и отменой выплаты (М§3.2, §5.3)
QY = 4                      # кварталов в году
DAYS_BASE = 365.0           # act/365 (М§0.3)
LOANS_SIDE = "asset"
RETAIL_CURRENT = "retail_current"   # книги ФЛ, доля которых — функция ключевой (М§4.3)
RETAIL_TERM = "retail_term"
CORP_LOANS = "corp_loans"           # таблица состава книг образца (ветвь его фактов, М§17)
SECURITIES = "securities"
LIQUIDITY = "liquidity"
WHOLESALE = "wholesale"
CORP_FUNDS = "corp_funds"
FIT_ITER = 60               # итераций фиксированной точки балансирующих статей, деления отрезка и года
FIT_TOL = 1e-11
PLAN_TOL = 1e-9             # сходимость квартального плана года (доли остатка книги; млрд ₽ дивиденда)
FREQ_QUARTERLY = "quarterly"        # dividends.calendar.frequency (М§5.1)
ORDER_DIV_FIRST = "dividend_first"  # capital.growth_constraint.order (М§4.13)
ORDER_GROWTH_FIRST = "growth_first"
BASIS_ISSUED = "issued"             # valuation.shares_basis (М§8.4)
HIST_EXACT, HIST_CAP, HIST_NONE = "exact", "cap", "none"   # dividends.policy.history_test (М§5.2)
LINK_BASES = ("loans", "funds", "iea")                      # volumes.link_base (М§4.7)
LOAN_SECTORS = ("corporate", "mortgage", "retail_other")    # ключи словаря премии роста кредитов (М§4.3)
FUND_SEGMENTS = ("retail", "corporate")                     # ключи словаря премии средств клиентов
NORM_TOTAL, NORM_BASE = "n20", "n11"    # нормативы решения о взносе акционеров: Н20.0 и отчётный Н20.1 (М§4.14.1)
REQ_OF = {NORM_TOTAL: "req20", NORM_BASE: "req11"}          # требование М§4.12 к каждому из них
DED_ANCHOR = {NORM_TOTAL: "capital.n20.deductions_anchor",  # вычет якоря норматива Ded_j,0 (М§4.11)
              NORM_BASE: "capital.n11.deductions_anchor"}
DED_SHARE = {NORM_TOTAL: "capital.n20.deductions_fixed_share",      # доля вычета якоря, постоянная в рублях, η_j
             NORM_BASE: "capital.n11.deductions_fixed_share"}
TIE_TOL = 1e-9              # точность счёта правила «при равенстве» решения о взносе, млрд ₽ (М§4.14.1 п. 3)
# Пятый проход (М§4.3, §4.11, §7): вычет сценария в рублях, путь постоянной части прочих активов, постоянные части
# терминала.
RUB_KEY = "deduction_rub"                                   # capital.reg_scenarios.<s>.deduction_rub — Drub_j,s,q
RUB_SLOT = {NORM_TOTAL: "n20_0", NORM_BASE: "n1_1"}         # траектории объекта — по одной на норматив
OAF_CHANGE = "volumes.other_assets_fixed_change"            # приращения постоянной части прочих активов ΔOA_q
OAF_DENSITY = "other_assets_fixed"                          # capital.rwa.density.<…> — плотность постоянной части ω_oaf
OAF_CHANGE_DENSITY = "other_assets_fixed_change"            # capital.rwa.density.<…> — вес риска приращения ω_Δ
ANCHOR_ZERO = 1e-9          # якорное условие пути постоянной части: |значение квартала якоря| ≤ 1e-9 млрд ₽ (№ 24)
FIXED_GROWTH = "valuation.terminal.fixed_growth_share"      # λ_F — доля постоянных частей, растущая за T
# Шестой проход (М§4.6, §4.7): структура нормировки сегментной CoR и база объёма iea квартала фактов.
SEGMENTS = ("corporate", "retail")                          # сегменты CoR (nii.books.<b>.cor_segment, М§4.6)
SEG_SHARE = "credit.segment_relative.corporate_share_ref"   # доля юрлиц структуры нормировки; у физлиц — остаток
DIV_POOLS = ("pool_all_classes", "pool_declared")           # сумма решения, вычтенная из bv_common: первое заданное поле
UNDATED_FROM = -11          # отказ базы iea: сумма без дня решения у строки с кварталом прибыли не раньше x = −11 (М§4.7)
# Седьмой проход (М§4.11, §7): дополнительный капитал держит долю RWA своей клетки.
T2_TRAJ = "capital.n20.t2"                                  # траектория инструментов капитала T2_q, млрд ₽
T2_SHARE = "capital.n20.t2_share"                           # ключ доли инструментов {enabled, from} (прил. A № 30)
T2_SHARE_FIELDS = ("enabled", "from")
# Восьмой проход (М§4.4, §4.9–§4.11, §7): добавочный капитал держит долю RWA своей клетки, надбавка за субординацию
# дополнительного капитала, прочие движения капитала за концом сетки.
AT1_SHARE = "capital.at1_share"                             # ключ доли добавочного капитала {enabled, from, spread, base} (№ 31)
AT1_SHARE_FIELDS = ("enabled", "from", "spread", "base")
T2_PREMIUM = "capital.n20.t2_premium"                       # надбавка за субординацию T2 {enabled, spread, base} (№ 32)
T2_PREMIUM_FIELDS = ("enabled", "spread", "base")
BASE_ANCHOR = "anchor"                                      # база ключа — сумма якоря (AT1_0; T2 траектории в квартале якоря)
OM_TERMINAL = "valuation.terminal.other_movements"          # прочие движения капитала за концом сетки (№ 33)
OM_KINDS = ("none", "flat_rub")                             # без ключа — none (соглашение образца: ноль)
OM_TRAJ = "equity.other_movements"                          # траектория прочих движений, млрд ₽ за квартал (М§4.9)
# Девятый проход (М§4.8, §4.9, §7): разрыв налога по правилу, купон добавочного капитала якоря по ставке своего мира.
TAX_STRUCTURE = "tax.structure"                             # {enabled, bond_rate, bond_scale, other_pp, coupon_deductible} (№ 34)
TAX_STRUCTURE_FIELDS = ("enabled", "bond_rate", "bond_scale", "other_pp", "coupon_deductible")
TAX_GAP = "tax.effective_gap"                               # число разрыва образца; с включённым ключом структуры не читается
AT1_COUPON = "capital.at1_coupon"                           # купон якоря {enabled, fixed, floating, spread} (№ 35)
AT1_COUPON_FIELDS = ("enabled", "fixed", "floating", "spread")
AXES_LISTS = ("valuation.uncertainty.axes", "valuation.uncertainty.off_band_axes")   # оси полосы: путь — в paths
VARIANTS_LIST = "valuation.reference_variants"              # справочные варианты: путь — в overrides


class ControlInputError(ValueError):
    """Книга или факты не дают того, что нужно контрольной модели (громкий отказ)."""


class ControlUnsupported(ValueError):
    """Ветка методики, которую контрольная модель не поддерживает. На настоящей книге — провал теста, не
    пропуск (М§17): отказ остаётся только у модулей, выключенных самой методикой (М§0.6)."""


# ============================================================================ ввод: книга

def _c_read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def c_book_machine(path: Path | None = None) -> dict:
    """Машинная книга data/assumptions/assumptions.yaml (миры и надстройка уже внутри)."""
    p = Path(path) if path else BOOK_YAML
    if not p.exists():
        raise ControlInputError(f"нет машинной книги {p.name}")
    return _c_read_yaml(p)


def c_book_from_draft(draft: Path | None = None, *, worlds_source: Path | None = None,
                    overlay: Path | None = None, curve_lt: dict | None = None) -> dict:
    """Шаблон книги (по умолчанию assumptions_template.yaml, иначе черновик) + блоки worlds.<W> и
    worlds_bank.<W> по таблице М§3.1 — независимая сборка машинной книги.

    Узел LT бескупонной кривой: M — правило рецепта (ОФЗ 10 лет последнего полугодия, до 0,1
    п.п.), N и H — правило сборки семейства (передаётся явно, в коде чисел нет). Строки-метки
    шаблона — комментарии YAML, поэтому шаблон читается как книга без миров.
    """
    src_book = Path(draft) if draft else (TEMPLATE_YAML if TEMPLATE_YAML.exists() else DRAFT_YAML)
    book = _c_read_yaml(src_book)
    src = json.loads(Path(worlds_source or WORLDS_SOURCE).read_text(encoding="utf-8"))
    ovl = json.loads(Path(overlay or WORLDS_BANK).read_text(encoding="utf-8"))
    curve_lt = dict(curve_lt or {})
    fields = {"key_rate": "key_avg", "cpi": "cpi_yoy_avg", "wage_growth": "nominal_wage_yoy",
              "ofz_1y": "ofz_1y", "ofz_3y": "ofz_3y", "ofz_5y": "ofz_5y", "ofz_10y": "ofz_10y",
              "real_key": "real_key_fwd12m"}
    pct = 100.0
    for w in book["worlds"]["ids"]:
        rows = [r for r in src["rows"] if r["world"] == w]
        blk = {"name": w}
        for key, col in fields.items():
            blk[key] = {r["period"]: r[col] / pct for r in rows}
        curve = {str(k): v / pct for k, v in src["fair_zero_curve_today"][w].items()}
        if w not in curve_lt:
            if w != W_MKT:
                raise ControlInputError(f"узел LT кривой мира {w}: передайте --worlds-lt")
            curve_lt[w] = round(rows[-1]["ofz_10y"], 1) / pct
        curve["LT"] = float(curve_lt[w])
        blk["zero_curve"] = curve
        blk["lt_inflation"] = src["lt_inflation"][w] / pct
        book["worlds"][w] = blk
    book["worlds_bank"] = {w: ovl["worlds"][w] for w in book["worlds"]["ids"]}
    return book


def c_bget(book: dict, dotted: str):
    """Значение книги по точечному пути; нет ключа — громкий отказ."""
    cur = book
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, dict) and part.isdigit() and int(part) in cur:
            cur = cur[int(part)]
        else:
            raise ControlInputError(f"в книге нет ключа {dotted}")
    return cur


def c_bnum(book: dict, dotted: str) -> float:
    v = c_bget(book, dotted)
    if v is None or isinstance(v, (dict, list, str, bool)):
        raise ControlInputError(f"ключ книги {dotted} — не число: {v!r}")
    return float(v)


def c_bopt(book: dict, dotted: str, default=None):
    """Необязательный (поведенческий) ключ книги: нет ключа или null — умолчание (М§0.6: «ключа нет»)."""
    cur = book
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return default if cur is None else cur


def _c_key_present(book: dict, dotted: str) -> bool:
    """Ключ стоит в книге — с любым значением, и с null тоже. У ключей, для которых null — отказ, а не «ключа нет»
    (доля вычета якоря, М§4.11, §17), присутствие и значение читаются раздельно."""
    cur = book
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def c_is_quarterly(book: dict) -> bool:
    """Квартальный календарь дивидендов (М§5.7); без ключа frequency — годовой режим образца."""
    return c_bopt(book, "dividends.calendar.frequency") == FREQ_QUARTERLY


def c_growth_rule(book: dict):
    """Параметры ограничения роста капиталом (М§4.13) или None: объекта нет либо enabled: false."""
    gc = c_bopt(book, "capital.growth_constraint")
    if not isinstance(gc, dict) or not gc.get("enabled"):
        return None
    for key in ("order", "min_growth_scale", "lookahead_quarters", "glide_pp_per_quarter", "catch_up_rate", "tol"):
        if gc.get(key) is None:
            raise ControlInputError(f"capital.growth_constraint.{key}: нет поля при enabled: true (М§4.13)")
    if gc["order"] not in (ORDER_DIV_FIRST, ORDER_GROWTH_FIRST):
        raise ControlInputError("capital.growth_constraint.order — не dividend_first и не growth_first")
    lam_min, cu = float(gc["min_growth_scale"]), float(gc["catch_up_rate"])
    if not (0.0 <= lam_min <= 1.0 and 0.0 <= cu <= 1.0 and float(gc["glide_pp_per_quarter"]) >= 0.0
            and float(gc["tol"]) > 0.0 and int(gc["lookahead_quarters"]) >= 0):
        raise ControlInputError("capital.growth_constraint: поле вне границ (М§4.13)")
    if not c_is_quarterly(book):
        raise ControlInputError("ограничение роста требует квартального календаря дивидендов (М§4.13)")
    if int(c_bnum(book, "volumes.guidance_year")) >= c_per_parse(c_bget(book, "meta.first_period"))[0]:
        raise ControlInputError("ограничение роста при годе гайденса внутри сетки (М§4.3)")
    return {"order": gc["order"], "lam_min": lam_min, "ahead": int(gc["lookahead_quarters"]),
            "glide": float(gc["glide_pp_per_quarter"]), "catch_up": cu, "tol": float(gc["tol"])}


def _c_plain_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def c_recap_window_floor(meets: int, deducts: int, asks: int) -> int:
    """Нижняя граница окна решения о взносе L_min (М§4.14): последняя точка окна не стоит раньше квартала, в
    котором последний уже решённый дивиденд вычитается из регуляторного капитала. meets, deducts, asks — номера в
    году квартала собрания, квартала вычета и квартала решения о взносе. Вычет — не раньше квартала собрания
    (М§5.4). Решение раньше собрания этого года: последний решённый дивиденд — прошлого года, он уже вычтен, и
    граница — ноль. Иначе граница — расстояние от квартала решения до квартала вычета дивиденда этого года, пока
    тот впереди; решение в квартал вычета или позже — ноль."""
    held = max(meets, deducts)                          # квартал, с конца которого дивиденд года вычтен
    return held - asks if meets <= asks < held else 0


def c_recap_span(meets: int, asks: int) -> int:
    """δ — число кварталов от квартала решения о взносе до ближайшего квартала с новым решением клетки, о
    дивиденде или о взносе (М§14.1): min(4, ((h_A − h_R − 1) mod 4) + 1). Своими словами: ближайшее собрание после
    квартала решения стоит через (h_A − h_R) mod 4 кварталов; ноль значит, что собрание этого года — в самом
    квартале решения и уже прошло, а до следующего решения — год. Точки инварианта «взнос закрывает разрыв» —
    кварталы q_R … q_R + δ − 1 в пределах окна."""
    ahead = (meets - asks) % QY
    return ahead if ahead else QY


def c_recap_check_points(asked: int, window_end: int, span: int) -> list[int]:
    """Точки инварианта «взнос закрывает разрыв» (М§14.1) — кварталы сетки q_R … min(c_max, q_R + δ − 1): от
    квартала решения asked до квартала перед ближайшим новым решением клетки, в пределах окна решения. Квартал
    нового решения и точки после него в инвариант не входят: в окончательном расчёте там стоит решение —
    дивиденд собрания или следующий взнос, — которого пробный проход не нёс."""
    return list(range(asked, min(window_end, asked + span - 1) + 1))


def c_recap_dividend_year(year: int, meets: int, asks: int) -> int:
    """Год прибыли дивиденда решения о взносе (М§4.14.1): дивиденд последнего решения о дивиденде в кварталах
    q_R − 3 … q_R. year — календарный год квартала решения о взносе. Решение в квартал собрания или позже —
    собрание этого года (дивиденд за год year − 1); решение раньше собрания — собрание прошлого года (дивиденд
    за год year − 2). Решения, которого клетка не принимала (до сетки), нет — дивиденд ноль."""
    return year - 1 if asks >= meets else year - 2


def c_recap_rule(book: dict):
    """Параметры докапитализации (М§4.14) или None: объекта capital.recapitalization нет либо enabled: false —
    взносов нет, клетка считается как у образца. Границы полей проверяются всегда, когда поле есть: дисконт
    размещения — число из [0; 1), окно — целое от 0 до 8, порог — число не меньше нуля, квартал решения — целое
    от 1 до 4. При enabled: true обязательны три поля (квартал решения необязателен: без ключа это квартал
    годового собрания) и условия формы: календарь дивидендов годовой, ограничение роста выключено, порог
    политики не выше пола сценария с запасом менеджмента ни в одном квартале сетки ни одного сценария (иначе
    клетка выпускала бы акции ради порога выплаты), окно не короче нижней границы L_min. Правило несёт квартал
    решения quarter (h_R), квартал собрания agm (h_A), границу окна ahead_min и число точек инварианта span."""
    rc = c_bopt(book, "capital.recapitalization")
    if rc is None:
        return None
    where = "capital.recapitalization"
    if not isinstance(rc, dict) or not isinstance(rc.get("enabled"), bool):
        raise ControlInputError(f"{where}.enabled — булево (М§4.14)")
    cut, ahead, least = rc.get("price_discount"), rc.get("lookahead_quarters"), rc.get("min_amount")
    asks = rc.get("decision_quarter")
    if asks is not None and not (isinstance(asks, int) and not isinstance(asks, bool) and 1 <= asks <= QY):
        raise ControlInputError(f"{where}.decision_quarter — не целое от 1 до 4 (М§4.14)")
    if cut is not None and not (_c_plain_number(cut) and 0.0 <= cut < 1.0):
        raise ControlInputError(f"{where}.price_discount вне [0; 1) (М§4.14)")
    if ahead is not None and not (isinstance(ahead, int) and not isinstance(ahead, bool) and 0 <= ahead <= 2 * QY):
        raise ControlInputError(f"{where}.lookahead_quarters — не целое от 0 до 8 (М§4.14)")
    if least is not None and not (_c_plain_number(least) and least >= 0.0):
        raise ControlInputError(f"{where}.min_amount меньше нуля или не число (М§4.14)")
    if not rc["enabled"]:
        return None
    if cut is None or ahead is None or least is None:
        raise ControlInputError(f"{where}: при enabled: true нужны price_discount, lookahead_quarters и min_amount")
    if c_is_quarterly(book):
        raise ControlInputError("докапитализация — только при годовом календаре дивидендов (М§4.14)")
    grow = c_bopt(book, "capital.growth_constraint")
    if isinstance(grow, dict) and grow.get("enabled"):
        raise ControlInputError("докапитализация и ограничение роста капиталом вместе не включаются (М§4.14)")
    goal = c_bnum(book, "dividends.policy.threshold")
    spare = c_bnum(book, "capital.mgmt_buffer.n20_0")
    anchor = c_per_parse(c_bget(book, "meta.anchor_period"))
    for s in c_bget(book, "capital.reg_scenarios.ids"):
        for k in range(1, c_qidx(anchor, *c_per_parse(c_bget(book, "meta.last_period"))) + 1):
            yy, qq = c_qper(anchor, k)
            if goal > _c_floor(book, s, "n20_0", yy, qq) + spare:
                raise ControlInputError(f"докапитализация: порог политики dividends.policy.threshold выше пола сценария "
                                        f"{s} с запасом менеджмента в {yy}Q{qq} (М§4.14)")
    meets = int(c_bnum(book, "dividends.calendar.agm_quarter"))
    deducts = int(c_bnum(book, "dividends.calendar.reg_deduction_quarter"))
    when = meets if asks is None else int(asks)         # без ключа — квартал годового собрания
    low = c_recap_window_floor(meets, deducts, when)
    if int(ahead) < low:
        raise ControlInputError(f"докапитализация: окно lookahead_quarters = {ahead} короче нижней границы {low} — "
                                f"последняя точка окна стоит раньше квартала вычета уже решённого дивиденда из "
                                f"регуляторного капитала (собрание — {meets}-й квартал, вычет — {deducts}-й, решение "
                                f"о взносе — {when}-й; М§4.14)")
    return {"d": float(cut), "ahead": int(ahead), "least": float(least), "quarter": when, "agm": meets,
            "ahead_min": low, "span": c_recap_span(meets, when)}


def c_cell_floor(book: dict):
    """Пол стоимости клетки в цене (ключ valuation.cell_floor, млрд ₽, М§8.2) или None: без ключа пола нет.
    Значение ниже нуля — отказ входа."""
    low = c_bopt(book, "valuation.cell_floor")
    if low is None:
        return None
    if not _c_plain_number(low) or low < 0.0:
        raise ControlInputError("valuation.cell_floor — число не меньше нуля (М§8.2)")
    return float(low)


# ============================================================================ ввод: факты

def c_facts_bundle(root: Path | None = None) -> dict:
    """Все data/facts/*.json как словари {имя файла: содержимое}."""
    d = Path(root) if root else FACTS_DIR
    files = sorted(d.glob("*.json")) if d.exists() else []
    if not files:
        raise ControlInputError(f"нет фактов в {d}")
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in files}


def _c_dig(tree, dotted: str):
    cur = tree
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise ControlInputError(f"нет узла {dotted}")
    return cur


def c_fval(facts: dict, file: str, dotted: str, *, null_ok: bool = False):
    """Значение узла факта {v, src|calc}; null — отказ (null ≠ 0), если не разрешено явно."""
    if file not in facts:
        raise ControlInputError(f"нет файла фактов {file}.json")
    node = _c_dig(facts[file], dotted)
    val = node.get("v") if isinstance(node, dict) and "v" in node else node
    if val is None:
        if null_ok:
            return None
        raise ControlInputError(f"null в узле {file}:{dotted}")
    return val


def c_fnum(facts: dict, file: str, dotted: str) -> float:
    return float(c_fval(facts, file, dotted))


def _c_quarter_rows(pnl: dict) -> dict[str, dict]:
    """Кварталы pnl_quarterly.json в виде {период: {строка: узел}} (допускаются формы
    «словарь периодов» и «список записей с полем period»)."""
    for key in ("quarters", "periods", "rows", "data"):
        if key in pnl:
            body = pnl[key]
            break
    else:
        body = {k: v for k, v in pnl.items() if isinstance(k, str) and "Q" in k and k[:4].isdigit()}
    if isinstance(body, list):
        return {str(r["period"]): r for r in body}
    return {str(k): v for k, v in body.items()}


def _c_nodeval(node):
    if isinstance(node, dict):
        return node.get("v")
    return node


# ============================================================================ время

def c_per_parse(p: str) -> tuple[int, int]:
    """«2026Q3» → (2026, 3)."""
    y, q = str(p).upper().split("Q")
    return int(y), int(q)


def c_q_first_day(y: int, q: int) -> dt.date:
    return dt.date(y, 3 * (q - 1) + 1, 1)


def c_q_last_day(y: int, q: int) -> dt.date:
    ny, nq = (y + 1, 1) if q == QY else (y, q + 1)
    return c_q_first_day(ny, nq) - dt.timedelta(days=1)


def c_q_len(y: int, q: int) -> int:
    return (c_q_last_day(y, q) - c_q_first_day(y, q)).days + 1


def _c_as_date(x) -> dt.date:
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x))


def c_annual_periods(book: dict) -> list[dict]:
    """Периоды годовой модели: остаток года якоря (если он есть) и полные годы до last_period."""
    y0, qa = c_per_parse(c_bget(book, "meta.anchor_period"))
    yl, ql = c_per_parse(c_bget(book, "meta.last_period"))
    if ql != QY:
        raise ControlUnsupported("last_period должен кончать год (терминал — с года после него)")
    fy, fq = c_per_parse(c_bget(book, "meta.first_period"))
    nxt = (y0 + 1, 1) if qa == QY else (y0, qa + 1)
    if (fy, fq) != nxt:
        raise ControlInputError("first_period — не квартал после якоря")
    out = []
    if qa < QY:
        out.append({"year": y0, "quarters": tuple(range(qa + 1, QY + 1)), "stub": True})
    for y in range(y0 + 1, yl + 1):
        out.append({"year": y, "quarters": tuple(range(1, QY + 1)), "stub": False})
    for p in out:
        y = p["year"]
        p["n"] = len(p["quarters"])
        p["days"] = sum(c_q_len(y, q) for q in p["quarters"])
        p["start"] = c_q_first_day(y, p["quarters"][0])
        p["end"] = c_q_last_day(y, p["quarters"][-1])
        p["label"] = str(y)
    return out


# ============================================================================ траектории (М§0.4)

def _c_time_keys(traj: dict) -> dict[str, tuple[int, int, int]]:
    """Ключи времени траектории → (год, первый квартал, последний квартал). Ключ, который не читается ни как
    год, ни как квартал 1…4, ни как полугодие 1…2, — отказ (М§0.4, запреты)."""
    out = {}
    for k in traj:
        s = str(k)
        if s in ("LT", "LT_from"):
            continue
        if len(s) == 4 and s.isdigit():
            out[s] = (int(s), 1, QY)
            continue
        try:
            if "Q" in s:
                y, q = c_per_parse(s)
                span = (y, q, q)
            else:
                y, h = s.split("H")
                span = (int(y), 2 * int(h) - 1, 2 * int(h))
        except ValueError:
            span = None
        if span is None or not 1 <= span[1] <= span[2] <= QY:
            raise ControlInputError(f"ключ траектории не разбирается: {s}")
        out[s] = span
    return out


def _c_traj_own_key(t: dict, y: int, q: int):
    """Правила 1–3 М§0.4: точный ключ квартала, иначе ключ полугодия, содержащего квартал, иначе ключ года; None —
    квартал ни одним из трёх ключей не назван."""
    for key in (f"{y}Q{q}", f"{y}H{1 if q <= 2 else 2}", str(y)):
        if key in t:
            return float(t[key])
    return None


def c_traj_given_years(t: dict, spans: dict | None = None) -> dict[int, float]:
    """Заданные годы траектории и их значения (М§0.4). Заданный год — год с ключом года (значение — ключ, как он
    написан, и тогда, когда рядом стоят ключи кварталов), а без него — год, у которого названы все четыре ключа
    квартала (значение — среднее четырёх кварталов) или, когда названы не все четыре, оба ключа полугодия (их
    среднее). Полугодие вместе с двумя кварталами другого полугодия полным набором не считается; одиночный ключ
    квартала или полугодия свой год заданным не делает. spans — уже разобранные ключи времени этой траектории."""
    given = {}
    if spans is None:
        t = {str(k): v for k, v in t.items()}
        spans = _c_time_keys(t)
    for year in {span[0] for span in spans.values()}:
        if str(year) in t:
            given[year] = float(t[str(year)])
            continue
        for names in ([f"{year}Q{j}" for j in range(1, QY + 1)], [f"{year}H{j}" for j in (1, 2)]):
            if all(name in t for name in names):
                given[year] = sum(float(t[name]) for name in names) / len(names)
                break
    return given


def c_traj_year_rule(given: dict, lt, lt_from, y: int) -> float:
    """Значение года y по правилам 4–6 М§0.4 — по годам, от заданных лет given: заданный год — его значение; год
    между заданными — линейная интерполяция между ближайшими заданными; год после последнего заданного — линейный
    сход от его значения к LT к году LT_from (LT без LT_from или с LT_from не позже следующего года — сразу, с
    LT_from и далее — LT; без LT — значение последнего заданного года навсегда); год до первого заданного —
    значение первого заданного года (плоско назад)."""
    if y in given:
        return given[y]
    first, last = min(given), max(given)
    if y < first:
        return given[first]                                         # правило 6
    if y > last:                                                    # правило 5
        if lt is None:
            return given[last]
        if lt_from is None or y >= int(lt_from):
            return float(lt)
        return given[last] + (float(lt) - given[last]) * (y - last) / (int(lt_from) - last)
    lo = max(v for v in given if v < y)                             # правило 4
    hi = min(v for v in given if v > y)
    return given[lo] + (given[hi] - given[lo]) * (y - lo) / (hi - lo)


_TRAJ_PARSED: dict = {}        # разбор траектории-словаря по её парам (ключ, значение): ключи времени и заданные годы;
                               # память — на прогон (c_control_context её очищает)


def _c_traj_dict(traj: dict) -> tuple[dict, dict, dict]:
    """Траектория-словарь, проверенная целиком (М§0.4, §17): (t — ключи строками, spans — разобранные ключи
    времени, given — заданные годы). Негодная траектория — отказ входа при её чтении в любом квартале, и тогда,
    когда читаемый квартал назван своим ключом: значение не числом (null, строка, булево, список, словарь) у любого
    ключа, в том числе у LT и LT_from, и ключ, который не читается ни одним правилом М§0.4 (`2027Q5`, `2027H3`).
    Значения проверяются при каждом чтении; разбор ключей и заданные годы зависят только от пар траектории и
    запоминаются по ним (в память попадает только проверенная траектория)."""
    t = {str(k): v for k, v in traj.items()}
    for k, v in t.items():
        if not _c_plain_number(v):
            raise ControlInputError(f"значение траектории не числом: {k}: {v!r} (М§0.4, §17)")
    memo = tuple(traj.items())
    hit = _TRAJ_PARSED.get(memo)
    if hit is None:
        spans = _c_time_keys(t)
        hit = (spans, c_traj_given_years(t, spans))
        _TRAJ_PARSED[memo] = hit
    return t, hit[0], hit[1]


def c_traj_at(traj, y: int, q: int) -> float:
    """Значение траектории книги в квартале (y, q) по правилам М§0.4 — буквально.

    Правила 1–3: ключ квартала, иначе ключ своего полугодия, иначе ключ года. Квартал, которому они не ответили,
    читает значение года по правилам 4–6 (они считаются по годам: все такие кварталы года получают одно значение,
    а одиночный ключ квартала или полугодия на него не влияет), с одним исключением — началом траектории: квартал
    раньше квартала самого раннего ключа (ключ квартала стоит в нём самом, ключ полугодия — в первом квартале
    полугодия, год — в своём первом квартале) получает значение траектории в этом квартале, прочитанное правилами
    1–3. Траектория без заданных лет читает LT (LT_from при этом не читается), а без него — отказ. Негодная
    траектория (ключ вне правил, значение не числом) — отказ при чтении любого квартала (М§17)."""
    if traj is None:
        raise ControlInputError("null в траектории")
    if isinstance(traj, (int, float)) and not isinstance(traj, bool):
        return float(traj)
    if not isinstance(traj, dict):
        raise ControlInputError(f"траектория не словарь: {traj!r}")
    t, spans, given = _c_traj_dict(traj)
    own = _c_traj_own_key(t, y, q)
    if own is not None:
        return own
    if spans:
        start = min((span[0], span[1]) for span in spans.values())     # квартал самого раннего ключа
        if (y, q) < start:
            return _c_traj_own_key(t, *start)                           # начало траектории
    return _c_traj_year_of(t, given, y)


def _c_traj_year_of(t: dict, given: dict, y: int) -> float:
    """Значение года y траектории-словаря t с заданными годами given: правила 4–6 по заданным годам; без заданных
    лет — LT, без него — отказ (М§0.4)."""
    lt = t.get("LT")
    if not given:
        if lt is None:
            raise ControlInputError("траектория без заданных лет и без LT: квартал не читается (М§0.4)")
        return float(lt)
    return c_traj_year_rule(given, lt, t.get("LT_from"), y)


def c_traj_year(traj, y: int) -> float:
    """Значение года траектории (М§0.4) — то, что книга задаёт на год y целиком: у заданного года — ключ года, а
    без него среднее четырёх кварталов или двух полугодий; у прочих лет — правила 4–6 по заданным годам (одиночный
    ключ квартала или полугодия на значение года не влияет); у траектории без заданных лет — LT, без него — отказ;
    число — оно само. Так читаются величины, которые методика берёт по году: премия роста (М§4.3), доля выплаты и
    её отклонение по году прибыли (М§5.2), годовые суммы книги (М§0.3). Начало траектории (значение самого раннего
    ключа в кварталах до него) — правило кварталов; на значение года оно не действует. Негодная траектория —
    отказ (М§17), как у чтения квартала."""
    if traj is None:
        raise ControlInputError("null в траектории")
    if isinstance(traj, (int, float)) and not isinstance(traj, bool):
        return float(traj)
    if not isinstance(traj, dict):
        raise ControlInputError(f"траектория не словарь: {traj!r}")
    t, _, given = _c_traj_dict(traj)
    return _c_traj_year_of(t, given, y)


def c_traj_mean(traj, y: int, quarters) -> float:
    """Среднее траектории по кварталам периода (год или остаток года якоря)."""
    return sum(c_traj_at(traj, y, q) for q in quarters) / len(quarters)


def c_spread_at(ctx: dict, b: str, y: int, q: int) -> float:
    """Спред книги в квартале: s_b(q) = путь + σ_b × [lt_shift] × [Y(q) ≥ nii.sigma0_from] (М§4.4),
    σ_b = +σ0_A у активов и −σ0_L у пассивов (М§4.5).

    Сдвиг прибавляется к значению пути во всех кварталах с года sigma0_from, а не к ключу LT:
    ближний участок (до sigma0_from) держит калибровку к ставкам якоря."""
    sp = ctx["B"]["nii"]["books"][b]
    s = c_traj_at(sp["spread"], y, q)
    if sp.get("lt_shift") and y >= ctx["sigma0_from"]:
        s += ctx["tr"]["sigma0"] if sp["side"] == LOANS_SIDE else -ctx["tr"]["sigma0_liab"]
    return s


# ============================================================================ кривая и дисконт (М§0.5)

def _c_curve_nodes(curve: dict) -> tuple[list[tuple[float, float]], float]:
    nodes = sorted((float(k), float(v)) for k, v in curve.items() if str(k) != "LT")
    return nodes, float(curve["LT"])


def c_zero_at(curve: dict, t: float) -> float:
    """Бескупонная ставка мира на срок t (годовое начисление)."""
    nodes, lt = _c_curve_nodes(curve)
    if t <= nodes[0][0]:
        return nodes[0][1]
    for (t1, z1), (t2, z2) in zip(nodes, nodes[1:]):
        if t <= t2:
            return z1 + (z2 - z1) * (t - t1) / (t2 - t1)
    tn, zn = nodes[-1]
    return ((1.0 + zn) ** tn * (1.0 + lt) ** (t - tn)) ** (1.0 / t) - 1.0


def c_df_world(curve: dict, add: float, t: float) -> float:
    """DF_W(t) = (1 + z(t) + β_E·ERP)^(−t)."""
    if t == 0.0:
        return 1.0
    return (1.0 + c_zero_at(curve, t) + add) ** (-t)


class CDisc:
    """Дисконт от даты оценки с перекатом по форвардам: DF_v(τ) = DF(Δ + τ) / DF(Δ)."""

    def __init__(self, curve: dict, add: float, shift: float):
        self.curve, self.add, self.shift = curve, add, shift
        self.base = c_df_world(curve, add, shift)

    def __call__(self, tau: float) -> float:
        return c_df_world(self.curve, self.add, self.shift + tau) / self.base


# ============================================================================ якорь из фактов

def _c_sum_nodes(facts: dict, file: str, base: str, parts: list[str], notes: list) -> float:
    """Сумма узлов; null-узел — «отдельно не раскрыт, входит в соседний» (записывается в notes)."""
    total = 0.0
    for part in parts:
        v = c_fval(facts, file, f"{base}.{part}", null_ok=True)
        if v is None:
            notes.append(f"{file}:{base}.{part} = null (не раскрыто отдельно) — не суммируется")
            continue
        total += float(v)
    return total


def _c_book_rate(facts: dict, b: str) -> float:
    nb = facts.get("nii_books")
    if nb is None:
        raise ControlInputError("нет файла фактов nii_books.json")
    for root in (nb.get("books", {}), nb):
        if isinstance(root, dict) and b in root:
            return float(c_fval({"x": root}, "x", f"{b}.rate_anchor"))
    raise ControlInputError(f"нет ставки якоря книги {b} (nii_books.json)")


def _c_nb_node(facts: dict, name: str) -> float:
    nb = facts["nii_books"]
    for root in (nb, nb.get("anchor", {}), nb.get("totals", {})):
        if isinstance(root, dict) and name in root:
            return float(c_fval({"x": root}, "x", name))
    raise ControlInputError(f"нет узла nii_books.{name}")


PNL_LINES = ("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt",
             "tax", "ni", "ni_shareholders", "misc_net")


def c_anchor_state(book: dict, facts: dict) -> dict:
    """Стартовое состояние якоря (М§4.1, прил. B) в единицах модели, с источником — фактами."""
    notes: list[str] = []
    bal = "balance"

    def c_lg(k):
        return c_fnum(facts, bal, f"loans_ac_gross.{k}")

    books = c_bget(book, "nii.books")
    for role in (SECURITIES, LIQUIDITY, WHOLESALE, RETAIL_CURRENT, RETAIL_TERM):
        if role not in books:
            raise ControlInputError(f"в nii.books нет книги роли {role} (М§4.1)")
    direct = isinstance(facts.get(bal, {}).get("books"), dict)
    if direct:
        # остатки якоря — прямыми узлами balance.books.<b> при любом составе книг (М§4.1 п. 2)
        E0 = {b: c_fnum(facts, bal, f"books.{b}") for b in books}
        fv_loans = None
        if any("fv_share" in sp for sp in books.values()):
            raise ControlInputError("fv_share у книги с остатками прямыми узлами: формулы вывода нет (М§4.1 п. 6)")
    else:
        # таблица состава книг образца — ветвь для его фактов (М§17)
        fv_loans = c_fnum(facts, bal, "loans_fvtpl")
        E0 = {
            CORP_LOANS: c_lg("commercial") + c_lg("project") + fv_loans,
            "mortgage": c_lg("mortgage_market"),
            "mortgage_sub": c_lg("mortgage_subsidized"),
            "retail_loans": c_lg("consumer") + c_lg("cards") + c_lg("auto"),
            SECURITIES: _c_sum_nodes(facts, bal, "securities",
                                   ["fvoci_debt", "fvoci_repo", "ac", "ac_repo", "fvtpl_bonds"], notes),
            LIQUIDITY: _c_sum_nodes(facts, bal, "liquidity",
                                  ["cash", "cbr", "due_from_banks", "reverse_repo"], notes),
            RETAIL_CURRENT: c_fnum(facts, bal, "funds.retail_current"),
            RETAIL_TERM: c_fnum(facts, bal, "funds.retail_term"),
            CORP_FUNDS: c_fnum(facts, bal, "funds.corp_current") + c_fnum(facts, bal, "funds.corp_term"),
            WHOLESALE: _c_sum_nodes(facts, bal, "wholesale",
                                  ["banks", "issued_debt", "subordinated", "repo_cbr"], notes),
        }
        for b in books:
            if b not in E0:
                raise ControlInputError(f"книга {b}: нет узла balance.books.{b}, а таблица состава книг "
                                        f"образца её не знает (М§4.1 п. 2, прил. B)")
    A = {"E0": E0, "notes": notes, "fv_loans": fv_loans, "direct_books": direct}
    A["rate0"] = {b: _c_book_rate(facts, b) for b in books}
    A["AL"] = abs(c_fnum(facts, bal, "allowance_ac"))
    A["OA"] = c_fnum(facts, bal, "other_assets")
    A["OL"] = c_fnum(facts, bal, "other_liabilities")
    A["DP"] = c_fnum(facts, bal, "dividends_payable")
    A["DP_year"] = _c_nodeval(facts[bal].get("dividends_payable_year"))          # признак годового режима (М§5.4)
    A["DP_declared"] = [{"period": str(_c_nodeval(it["period"])), "amount": float(_c_nodeval(it["amount"]))}
                        for it in (facts[bal].get("dividends_payable_declared") or [])]
    oaf = facts[bal].get("other_assets_fixed")
    A["OA_fixed_fact"] = None if oaf is None else _c_nodeval(oaf)
    A["history"] = {str(per): {k: _c_nodeval(v) for k, v in rec.items()}
                    for per, rec in (facts[bal].get("history") or {}).items() if isinstance(rec, dict)}
    A["BV"] = c_fnum(facts, bal, "equity.bv_common")
    A["AT1"] = c_fnum(facts, bal, "equity.at1")
    A["NCI"] = c_fnum(facts, bal, "equity.nci")
    A["prev_corp"] = c_fnum(facts, bal, "prev_year_end.loans_corporate")
    A["prev_retail"] = c_fnum(facts, bal, "prev_year_end.loans_retail")
    A["fvoci_debt"] = (c_fnum(facts, bal, "securities.fvoci_debt")
                       + (c_fval(facts, bal, "securities.fvoci_repo", null_ok=True) or 0.0))
    A["fvtpl_bonds"] = c_fval(facts, bal, "securities.fvtpl_bonds", null_ok=True)
    # доля текущих счетов якоря: узел факта, а при null — из остатков книг средств физлиц (прил. B)
    share0 = _c_nb_opt(facts, "current_share_anchor")
    A["current_share"] = (float(share0) if share0 is not None
                          else E0[RETAIL_CURRENT] / (E0[RETAIL_CURRENT] + E0[RETAIL_TERM]))
    A["key_ref"] = _c_nb_node(facts, "key_avg_anchor_q")
    cap = "capital"
    # сумма слота купона якоря (М§4.9): у книги с включённым ключом capital.at1_coupon не читается (М§0.1) — None, квартал
    # слота читается по-прежнему
    at1c = c_bopt(book, AT1_COUPON)
    A["cpn_annual"] = (None if isinstance(at1c, dict) and at1c.get("enabled") is True
                       else c_fnum(facts, cap, "at1.coupon_annual"))
    A["cpn_quarter"] = int(c_fnum(facts, cap, "at1.coupon_quarter"))
    A["R0"] = c_fnum(facts, cap, "fvoci_reserve")
    A["curve0"] = {str(k): c_fnum(facts, cap, f"ofz_curve_anchor.{k}")
                   for k in _c_dig(facts[cap], "ofz_curve_anchor") if str(k)[:1].isdigit()}
    A["n20_fact"] = c_fnum(facts, cap, "n20_0.value")
    A["n11_fact"] = c_fnum(facts, cap, "n1_1_bank.value")
    A["rwa_basel"] = c_fnum(facts, cap, "basel.rwa")
    A["group_cet1"] = _c_nodeval(facts[cap].get("basel", {}).get("cet1"))
    A["base_capital"] = _c_nodeval(facts[cap].get("bank_base_capital"))
    sh = "shares"
    A["N_iss"] = c_fnum(facts, sh, "issued_total")
    A["N_out"] = c_fnum(facts, sh, "outstanding_total")
    A["N_div"] = c_divisor(book, facts, A["N_iss"], A["N_out"])
    A["N_base"] = c_divisor_base(book, facts, A["N_iss"], A["N_out"])
    A["bridge"] = {x: (str(c_fval(facts, "bridge_mgmt_ifrs", f"{x}.method")),
                       float(c_fval(facts, "bridge_mgmt_ifrs", f"{x}.value"))) for x in ("cor", "nim")}
    if isinstance(facts.get("bridge_mgmt_ifrs", {}).get("cir"), dict):
        # мост C/I нужен только уровням после фазы роста (ключи checks.window_backtest и checks.cir_lt)
        A["bridge"]["cir"] = (str(c_fval(facts, "bridge_mgmt_ifrs", "cir.method")),
                              float(c_fval(facts, "bridge_mgmt_ifrs", "cir.value")))
    rows = _c_quarter_rows(facts["pnl_quarterly"])
    A["pnl"] = {per: {line: _c_nodeval(rec[line]) for line in PNL_LINES if line in rec}
                for per, rec in rows.items()}
    dv = facts.get("dividends", {})
    A["div_history"] = dv.get("history", [])
    A["div_history_before"] = dv.get("history_before") or []     # решения до окна истории (база iea, М§4.7)
    A["register"] = dv.get("register_seed", [])
    A["div_years"] = dv.get("years") or {}
    A["facts_date"] = _c_as_date(c_bget(book, "meta.facts_date"))
    A["anchor"] = c_per_parse(c_bget(book, "meta.anchor_period"))
    return A


def c_divisor_base(book: dict, facts: dict, n_iss: float, n_out: float) -> float:
    """База делителя N_base (М§8.4): акции в обращении (без ключа) или размещённые за вычетом экономически
    собственных. Делитель — N_div = N_base × (1 + share_count_adj); разность N_div − N_base — акции поправки
    делителя: на дату фактов их нет в акциях в обращении, но книга считает их существующими (М§6.6)."""
    basis = c_bopt(book, "valuation.shares_basis")
    n_base = n_out
    if basis == BASIS_ISSUED:
        if len(c_bget(book, "meta.company.tickers")) != 1:
            raise ControlInputError("valuation.shares_basis: issued при двух и более тикерах (М§8.4)")
        node = facts.get("shares", {}).get("economic_treasury")
        n_base = n_iss - float(_c_nodeval(node) or 0.0)
    elif basis not in (None, "outstanding"):
        raise ControlInputError(f"valuation.shares_basis: {basis!r}")
    return n_base


def c_divisor(book: dict, facts: dict, n_iss: float, n_out: float) -> float:
    """Делитель «на акцию» N_div (М§8.4): база — акции в обращении (без ключа) или размещённые за вычетом
    экономически собственных; множитель (1 + share_count_adj) — только при ключе."""
    n_div = c_divisor_base(book, facts, n_iss, n_out)
    adj = c_bopt(book, "valuation.share_count_adj")
    if adj is not None:
        if not -0.5 < float(adj) < 0.5:
            raise ControlInputError("valuation.share_count_adj вне (−0,5; 0,5) (М§8.4)")
        n_div = n_div * (1.0 + float(adj))
    if n_div <= 0.0:
        raise ControlInputError("делитель N_div не положителен (М§8.4)")
    return n_div


def _c_nb_opt(facts: dict, name: str):
    """Узел nii_books.<name>, допускающий null (None — «считается из книг», прил. B)."""
    nb = facts.get("nii_books") or {}
    for root in (nb, nb.get("anchor", {}), nb.get("totals", {})):
        if isinstance(root, dict) and name in root:
            return _c_nodeval(root[name])
    return None


def c_fv_books(books: dict) -> list[str]:
    """Кредитные книги с долей кредитов по справедливой стоимости (ключ fv_share, М§4.6)."""
    return [b for b, sp in books.items() if sp.get("sector") and "fv_share" in sp]


def c_client_funds(books: dict) -> list[str]:
    """Небалансирующие пассивы, кроме пары средств физлиц, — средства клиентов-бизнеса (М§4.1 п. 1)."""
    return [b for b, sp in books.items()
            if sp["side"] != LOANS_SIDE and b not in (RETAIL_CURRENT, RETAIL_TERM, WHOLESALE)]


def c_unaudited_anchor(book: dict, A: dict):
    """E_0 — неаудированная прибыль на якоре по календарю аудитов (М§4.11); None — нет фактов кварталов."""
    cut = [int(c) for c in c_bget(book, "capital.n11.audit_cutoffs")]
    total = 0.0
    for yq in _c_unaudited_quarters(cut, *A["anchor"]):
        rec = A["pnl"].get(f"{yq[0]}Q{yq[1]}")
        if rec is None or rec.get("ni_shareholders") is None:
            return None
        total += float(rec["ni_shareholders"])
    return total


def c_resolve_anchor_keys(book: dict, A: dict) -> tuple[dict, dict]:
    """Книга с числами вместо "anchor" (формулы — прил. A М) и таблица выведенных значений."""
    B = copy.deepcopy(book)
    E0 = A["E0"]
    books = B["nii"]["books"]
    loans = [b for b, spec in books.items() if spec.get("sector")]
    sum_loans = sum(E0[b] for b in loans)
    loans_ac = sum_loans - A["fv_loans"] if A["fv_loans"] is not None else sum_loans
    biz = c_client_funds(books)
    if biz == [CORP_FUNDS]:
        funds = E0[RETAIL_CURRENT] + E0[RETAIL_TERM] + E0[CORP_FUNDS]
    else:
        funds = E0[RETAIL_CURRENT] + E0[RETAIL_TERM] + sum(E0[b] for b in biz)
    la = E0[SECURITIES] + E0[LIQUIDITY]
    # постоянные прочие активы (М§4.3): число книги или узел фактов; без ключа — 0, и формула образца
    oaf_key = c_bopt(B, "volumes.other_assets_fixed")
    if oaf_key == "anchor":
        if A["OA_fixed_fact"] is None:
            raise ControlInputError("volumes.other_assets_fixed: anchor без узла balance.other_assets_fixed")
        oaf = float(A["OA_fixed_fact"])
    else:
        oaf = float(oaf_key or 0.0)
    if oaf < 0.0 or oaf > A["OA"]:
        raise ControlInputError("постоянные прочие активы вне [0; прочие активы якоря] (М§4.3)")
    A["OA_fixed"] = oaf
    formulas = {
        "credit.allowance_ratio": A["AL"] / loans_ac,
        "nii.retail_current_share.c_ref": A["current_share"],
        "nii.retail_current_share.key_ref": A["key_ref"],
        "volumes.wholesale_to_funds": E0[WHOLESALE] / funds,
        "volumes.securities_share_of_liquid": E0[SECURITIES] / la,
        "volumes.other_assets_fixed": oaf,
        "volumes.other_assets_to_loans": (A["OA"] - oaf) / sum_loans if oaf else A["OA"] / sum_loans,
        "volumes.other_liabilities_to_loans": A["OL"] / sum_loans,
        "oci.fvoci_share": A["fvoci_debt"] / E0[SECURITIES],
        "oci.fvtpl_bond_share": (A["fvtpl_bonds"] or 0.0) / E0[SECURITIES],
    }
    for b in c_fv_books(books):
        if A["fv_loans"] is not None:
            formulas[f"nii.books.{b}.fv_share"] = A["fv_loans"] / E0[b]
    # вычеты капитала якоря словом anchor (М§4.11, прил. A): Ded20_0 = BV − капитал группы без
    # регуляторных инструментов; Ded11_0 = BVreg − max(E_0, 0) − базовый капитал группы
    if c_bget(B, "capital.n20.deductions_anchor") == "anchor":
        if A["group_cet1"] is None:
            raise ControlInputError("capital.n20.deductions_anchor: anchor без узла capital.basel.cet1")
        formulas["capital.n20.deductions_anchor"] = A["BV"] - float(A["group_cet1"])
    if c_bget(B, "capital.n11.deductions_anchor") == "anchor":
        e0 = c_unaudited_anchor(B, A)
        if A["base_capital"] is None or e0 is None:
            raise ControlInputError("capital.n11.deductions_anchor: anchor без базового капитала группы "
                                    "или прибыли неаудированного периода якоря")
        bvreg0 = A["BV"] + c_dpreg_anchor(B, A) - (1.0 - c_bnum(B, "capital.n20.fvoci_recognition")) * A["R0"]
        formulas["capital.n11.deductions_anchor"] = bvreg0 - max(e0, 0.0) - float(A["base_capital"])
    derived = {}

    def c_walk(node, prefix):
        if isinstance(node, dict):
            for k, v in node.items():
                path = f"{prefix}.{k}" if prefix else str(k)
                if v == "anchor":
                    if path == "nii.transmission.weights":
                        continue                                # веса — структура якоря (М§4.5)
                    if path.startswith("meta.labels."):
                        continue                                # подпись, не ключ вывода
                    if path in (f"{AT1_SHARE}.base", f"{T2_PREMIUM}.base"):
                        continue                                # слово базы читает правило своего ключа (М§4.11)
                    if path not in formulas:
                        raise ControlInputError(f"anchor-ключ без формулы: {path}")
                    node[k] = formulas[path]
                    derived[path] = formulas[path]
                else:
                    c_walk(v, path)

    c_walk(B, "")
    return B, derived


# ============================================================================ мост упр. ↔ движок (М§4.6)

def c_to_engine(A: dict, x: str, v: float) -> float:
    method, b = A["bridge"][x]
    if method == "additive":
        return v + b
    if method == "ratio":
        return v * b
    raise ControlInputError(f"метод моста {method}")


def c_to_mgmt(A: dict, x: str, v: float) -> float:
    if x not in A["bridge"]:
        raise ControlInputError(f"в фактах нет моста упр. ↔ движок для {x} (М§4.6)")
    method, b = A["bridge"][x]
    return v - b if method == "additive" else v / b


# ============================================================================ миры

def c_world_quarter(book: dict, w: str, field: str, y: int, q: int) -> float:
    return c_traj_at(c_bget(book, f"worlds.{w}.{field}"), y, q)


def c_ref_field(ref: str) -> str:
    return "key_rate" if ref == "key" else ref


def c_kappa_world(book: dict):
    """Мир-опора κ (ключ книги credit.kappa_reference_world): мир, в котором стоят уровни CoR режимов. Нет
    ключа — None: добавка образца, относительно мира N и только вверх."""
    ref = c_bopt(book, "credit.kappa_reference_world")
    if ref is not None and ref not in c_bget(book, "worlds.ids"):
        raise ControlInputError(f"credit.kappa_reference_world: {ref!r} — не мир из worlds.ids (М§4.6)")
    return ref


def c_kappa_spread(book: dict, w: str, y: int, q: int) -> float:
    """Разность реальных ставок квартала (y, q), на которую умножается κ в мире w (М§4.6). С миром-опорой —
    rr_w − rr_опоры с любым знаком: в мире-опоре ноль, в мире с меньшей реальной ставкой добавка
    отрицательна. Без ключа — max(0, rr_w − rr_N)."""
    rr = c_world_quarter(book, w, "real_key", y, q)
    ref = c_kappa_world(book)
    if ref is None:
        return max(0.0, rr - c_world_quarter(book, W_LOW, "real_key", y, q))
    return rr - c_world_quarter(book, ref, "real_key", y, q)


def c_g_terminal(book: dict, w: str) -> float:
    """g_T мира до защиты k_T − 0,0001 (М§7)."""
    return ((1.0 + c_bnum(book, f"worlds.{w}.lt_inflation"))
            * (1.0 + c_bnum(book, "valuation.terminal.real_growth")) - 1.0)


def c_overlay_growth(book: dict, w: str, group: str, name: str, y: int) -> float:
    """Рост надстройки миров года y; после последнего года — линейный сход к g_T к lt_from (М§4.3)."""
    table = {int(k): float(v) for k, v in c_bget(book, f"worlds_bank.{w}.{group}.{name}").items()}
    if y in table:
        return table[y]
    first, last = min(table), max(table)
    if y < first:
        return table[first]
    gt = c_g_terminal(book, w)
    lt_from = int(c_bnum(book, "volumes.lt_from"))
    if y >= lt_from:
        return gt
    return table[last] + (gt - table[last]) * (y - last) / (lt_from - last)


# ============================================================================ передача ставки (М§4.5)

def c_transmission_ctl(book: dict, A: dict) -> dict:
    """σ0_A, σ0_L, φ, φ_A, φ_L, target_eng, T_real, T(W), пары, эффективные LT-спреды кредитных книг и
    кредитная маржа миров — замкнутое решение по стационарному ЧПМ (М§4.5). Сдвиг Δ0 делит
    nii.sigma0_split, сжатие φ — nii.phi_split: объём сжатия мира φ × C_W один при любой доле, доля p
    снимается со спредов кредитных книг Φ_A, остаток — добавка к стоимости пассивов Φ_L. Ключ цели
    (target_eng) — стационарный ЧПМ мира nii.transmission.level_world (nss_level); без ключа — мира-опоры."""
    books = c_bget(book, "nii.books")
    E0 = A["E0"]
    iea = sum(E0[b] for b, s in books.items() if s["side"] == LOANS_SIDE)
    yl, ql = c_per_parse(c_bget(book, "meta.last_period"))
    ref_w = c_bget(book, "nii.transmission.reference_world")

    def c_ref_lt(w, ref):
        return c_world_quarter(book, w, c_ref_field(ref), yl, ql)

    def c_s_lt(b):
        return c_traj_at(books[b]["spread"], yl, ql)

    c_ref = c_bnum(book, "nii.retail_current_share.c_ref")
    k_ref = c_bnum(book, "nii.retail_current_share.key_ref")
    psi = c_bnum(book, "nii.retail_current_share.psi")
    lo, hi = (float(x) for x in c_bget(book, "nii.retail_current_share.bounds"))
    dia = c_bnum(book, "nii.dia_rate")
    l_r = (E0[RETAIL_CURRENT] + E0[RETAIL_TERM]) / iea

    def c_cstar(key):
        return min(hi, max(lo, c_ref - psi * (key - k_ref)))

    def c_cost_lt(b, base, sl):
        # стоимость пассива в стационаре: β × опора + s^LT − σ0_L × [lt_shift]
        sp = books[b]
        return float(sp["beta"]) * base + c_s_lt(b) - (sl if sp.get("lt_shift") else 0.0)

    def c_nss(w, d, sa, sl, ph):
        key = c_ref_lt(w, "key") + d
        tot = 0.0
        for b, sp in books.items():
            wgt = E0[b] / iea
            r_w = c_ref_lt(w, sp["ref"]) + d
            if sp["side"] == LOANS_SIDE:
                val = r_w + c_s_lt(b) + (sa if sp.get("lt_shift") else 0.0)
                if sp.get("phi"):
                    val -= ph * (r_w - c_ref_lt(ref_w, sp["ref"]))
                tot += wgt * val
            elif b not in (RETAIL_CURRENT, RETAIL_TERM):
                tot -= wgt * c_cost_lt(b, r_w, sl)
        c = c_cstar(key)
        tot -= l_r * (c * c_cost_lt(RETAIL_CURRENT, key, sl) + (1.0 - c) * c_cost_lt(RETAIL_TERM, key, sl))
        tot -= dia * l_r
        return tot

    target = c_to_engine(A, "nim", c_bnum(book, "nii.nim_lt_target_mgmt"))
    split = c_bnum(book, "nii.sigma0_split")
    if not 0.0 <= split <= 1.0:
        raise ControlInputError("nii.sigma0_split вне [0; 1] (М прил. A)")
    # Δ0 — нужный сдвиг стационарного ЧПМ мира H (там сжатие φ равно нулю); долю split несут активы с
    # lt_shift, остаток — пассивы с lt_shift. Вес пассива в стационаре мира H: у средств ФЛ —
    # l_R × c*(key_H^LT) (текущие) и l_R × (1 − c*(key_H^LT)) (срочные), у прочих — l_b.
    base_ref = c_nss(ref_w, 0.0, 0.0, 0.0, 0.0)
    w_assets = sum(E0[b] / iea for b, s in books.items() if s["side"] == LOANS_SIDE and s.get("lt_shift"))
    c_h = c_cstar(c_ref_lt(ref_w, "key"))
    w_liab = 0.0
    for b, s in books.items():
        if s["side"] == LOANS_SIDE or not s.get("lt_shift"):
            continue
        w_liab += l_r * c_h if b == RETAIL_CURRENT else l_r * (1.0 - c_h) if b == RETAIL_TERM else E0[b] / iea
    if split > 0.0 and w_assets == 0.0:
        raise ControlInputError("nii.sigma0_split > 0 без актива с lt_shift (М§4.5)")
    if split < 1.0 and w_liab == 0.0:
        raise ControlInputError("nii.sigma0_split < 1 без пассива с lt_shift (М§4.5)")
    dk = c_ref_lt(W_MKT, "key") - c_ref_lt(W_LOW, "key")
    if dk == 0.0:
        raise ControlInputError("передача не определена: key_M^LT = key_N^LT")
    dphi = sum(E0[b] / iea * (c_ref_lt(W_MKT, s["ref"]) - c_ref_lt(W_LOW, s["ref"]))
               for b, s in books.items() if s["side"] == LOANS_SIDE and s.get("phi")) / dk
    if dphi == 0.0:
        raise ControlInputError("передача не определена: D = 0")
    t_star = c_bnum(book, "nii.transmission.target")

    def c_shifts(d0):
        # сдвиги спредов и сжатие при сдвиге Δ0 стационарного ЧПМ мира-опоры: (σ0_A, σ0_L, T при φ = 0, φ)
        sa = split * d0 / w_assets if split > 0.0 else 0.0
        sl = (1.0 - split) * d0 / w_liab if split < 1.0 else 0.0
        flat = (c_nss(W_MKT, 0.0, sa, sl, 0.0) - c_nss(W_LOW, 0.0, sa, sl, 0.0)) / dk
        return sa, sl, flat, (flat - t_star) / dphi

    # Чей уровень задаёт ключ цели (nii.transmission.level_world): без ключа — мира-опоры, и Δ0 — прямая
    # разность. С ключом ключ цели — стационарный ЧПМ названного мира на составе якоря: он линеен по Δ0
    # (σ0 и φ линейны по Δ0 и входят слагаемыми), поэтому Δ0 — из значения при Δ0 = 0 и отклика на единицу.
    level_w = c_bopt(book, "nii.transmission.level_world")
    if level_w is not None and level_w not in c_bget(book, "worlds.ids"):
        raise ControlInputError(f"nii.transmission.level_world: {level_w!r} — не мир из worlds.ids (М§4.5)")
    if level_w is None or level_w == ref_w:
        delta0 = target - base_ref
    else:
        def c_level(d0):
            sa, sl, _, ph = c_shifts(d0)
            return c_nss(level_w, 0.0, sa, sl, ph)

        at_zero = c_level(0.0)
        unit = c_level(1.0) - at_zero
        if unit == 0.0:
            raise ControlInputError(f"стационарный ЧПМ мира {level_w} не зависит от сдвига спредов (М§4.5)")
        delta0 = (target - at_zero) / unit
    sigma0, sigma0_l, t0, phi = c_shifts(delta0)
    t_real = (c_nss(W_MKT, 0.0, sigma0, sigma0_l, phi) - c_nss(W_LOW, 0.0, sigma0, sigma0_l, phi)) / dk
    h = c_bnum(book, "nii.transmission.fd_step")
    ids = list(c_bget(book, "worlds.ids"))
    t_loc = {w: (c_nss(w, h, sigma0, sigma0_l, phi) - c_nss(w, -h, sigma0, sigma0_l, phi)) / (2.0 * h)
             for w in ids}
    # Парные передачи соседних по key^LT миров (М§4.5): равные key^LT — пара не определена (None).
    key_lt = {w: c_ref_lt(w, "key") for w in ids}
    nss0 = {w: c_nss(w, 0.0, sigma0, sigma0_l, phi) for w in ids}
    # Раскладка сжатия (М§4.5): φ_A = p × φ — спреды кредитных книг Φ_A; φ_L = (1 − p) × φ × A / L —
    # добавка к стоимости пассивов Φ_L на единицу X_W = Σ ω_b × (ref_b,W − ref_b,H), ω_b = a_b / A.
    # Флаг phi у обеих книг средств ФЛ обязан совпадать: их веса в стационаре зависят от мира.
    p_split = c_bnum(book, "nii.phi_split")
    if not 0.0 <= p_split <= 1.0:
        raise ControlInputError("nii.phi_split вне [0; 1] (М прил. A)")
    if bool(books[RETAIL_CURRENT].get("phi")) != bool(books[RETAIL_TERM].get("phi")):
        raise ControlInputError("флаг phi у книг средств ФЛ разный (М§4.5)")
    phi_a_w = {b: E0[b] / iea for b, s in books.items() if s["side"] == LOANS_SIDE and s.get("phi")}
    a_sum = sum(phi_a_w.values())
    l_sum = sum(E0[b] / iea for b, s in books.items() if s["side"] != LOANS_SIDE and s.get("phi"))
    if p_split > 0.0 and a_sum == 0.0:
        raise ControlInputError("nii.phi_split > 0 без актива с phi (М§4.5)")
    if p_split < 1.0 and l_sum == 0.0:
        raise ControlInputError("nii.phi_split < 1 без пассива с phi (М§4.5)")
    phi_a = p_split * phi
    phi_l = (1.0 - p_split) * phi * a_sum / l_sum if p_split < 1.0 else 0.0
    omega = {b: v / a_sum for b, v in phi_a_w.items()}
    x_lt = {w: sum(omega[b] * (c_ref_lt(w, books[b]["ref"]) - c_ref_lt(ref_w, books[b]["ref"])) for b in omega)
            for w in ids}
    # Эффективный LT-спред кредитной книги к её опоре в стационаре мира (М§4.5, гейт lt_spread_floor):
    # s_eff = s^LT + σ0_A × [lt_shift] − φ_A × [b ∈ Φ_A] × (ref_W^LT − ref_H^LT)
    lt_spread = {}
    for b, s in books.items():
        if not s.get("sector"):
            continue
        lt_spread[b] = {w: (c_s_lt(b) + (sigma0 if s.get("lt_shift") else 0.0)
                            - (phi_a * (c_ref_lt(w, s["ref"]) - c_ref_lt(ref_w, s["ref"])) if s.get("phi") else 0.0))
                        for w in ids}

    def c_nss_books(w):
        # стационарный ЧПМ «по книгам»: сжатие — долями φ_A (спреды Φ_A) и φ_L × X_W (стоимость Φ_L);
        # обязан совпасть с Nss(W, 0), где сжатие — одним слагаемым φ × C_W
        key = c_ref_lt(w, "key")
        c = c_cstar(key)
        tot = 0.0
        for b, sp in books.items():
            r_w = c_ref_lt(w, sp["ref"])
            if sp["side"] == LOANS_SIDE:
                val = r_w + c_s_lt(b) + (sigma0 if sp.get("lt_shift") else 0.0)
                if sp.get("phi"):
                    val -= phi_a * (r_w - c_ref_lt(ref_w, sp["ref"]))
                tot += E0[b] / iea * val
                continue
            wgt = l_r * c if b == RETAIL_CURRENT else l_r * (1.0 - c) if b == RETAIL_TERM else E0[b] / iea
            tot -= wgt * (c_cost_lt(b, r_w, sigma0_l) + (phi_l * x_lt[w] if sp.get("phi") else 0.0))
        return tot - dia * l_r

    # Кредитная маржа стационара мира (М§4.5): доходность кредитного портфеля − CoR режима norm с
    # κ-добавкой мира − смесь балансирующих активов (бумаги и ликвидность в долях LA)
    credit = [b for b, s in books.items() if s.get("sector")]
    cor_norm = c_traj_at(c_bget(book, f"regimes.{R_NORM}.cor"), yl, ql)
    if c_bget(book, "regimes.cor_basis") == "mgmt":
        cor_norm = c_to_engine(A, "cor", cor_norm)
    kap = c_bnum(book, "credit.kappa")
    sec = c_bnum(book, "volumes.securities_share_of_liquid")
    margin = {}
    for w in ids:
        yld = (sum(E0[b] * (c_ref_lt(w, books[b]["ref"]) + lt_spread[b][w]) for b in credit)
               / sum(E0[b] for b in credit))
        risk = cor_norm + kap * c_kappa_spread(book, w, yl, ql)
        bal = (sec * (c_ref_lt(w, books[SECURITIES]["ref"]) + c_s_lt(SECURITIES))
               + (1.0 - sec) * (c_ref_lt(w, books[LIQUIDITY]["ref"]) + c_s_lt(LIQUIDITY)))
        margin[w] = yld - risk - bal
    order = sorted(ids, key=lambda w: key_lt[w])
    pairs = {}
    for w1, w2 in zip(order, order[1:]):
        dkk = key_lt[w2] - key_lt[w1]
        pairs[f"{w1}_{w2}"] = None if dkk == 0.0 else (nss0[w2] - nss0[w1]) / dkk
    # ROE-эквивалент: T × IEA_0/BV_0 × (1 − τ_eff года last_period) — п.п. ROE на 1 п.п. ключевой; у книги с ключом
    # tax.structure τ_eff,L — маржинальная ставка τ_stat,L + o (М§4.5, §4.8): число разрыва не читается
    tax_rule = c_tax_structure_rule(book)
    tau_l = c_traj_at(c_bget(book, "tax.statutory"), yl, ql) + (c_bnum(book, "tax.effective_gap") if tax_rule is None
                                                                 else tax_rule["other_pp"])
    scale = iea / A["BV"] * (1.0 - tau_l)
    return {"sigma0": sigma0, "sigma0_liab": sigma0_l, "split": split, "delta0": delta0,
            "w_assets": w_assets, "w_liab": w_liab, "lt_spread": lt_spread,
            "phi": phi, "phi_split": p_split, "phi_assets": phi_a, "phi_liab": phi_l, "phi_weights": omega,
            "phi_a_sum": a_sum, "phi_l_sum": l_sum, "x_lt": x_lt, "loan_margin": margin,
            "nss_books": {w: c_nss_books(w) for w in ids},
            "target_eng": target, "t_real": t_real, "t_local": t_loc,
            "level_world": level_w or ref_w, "nss_level": nss0[level_w or ref_w],
            "nss_ref": nss0[ref_w], "nss": nss0, "key_lt": key_lt, "iea0": iea,
            "d_phi": dphi, "t_real_phi0": t0, "pairs": pairs, "roe_equiv": t_star * scale,
            "roe_equiv_pairs": {k: None if v is None else v * scale for k, v in pairs.items()}}


# ============================================================================ контекст прогона

def _c_pos(x: dt.date, anchor: tuple[int, int]) -> float:
    """Положение даты на линейке кварталов сетки (М§0.2) — одна функция для даты оценки и даты
    кривой, по конвенции «конец дня»: внутри квартала q — (q − 1) + (x − S_q)/d_q, на конце
    квартала pos(E_q) = q (квартал закрыт, как у S_(q+1)). q — номер квартала сетки: первый
    прогнозный — 1, раньше сетки — q ≤ 0."""
    y0, qa = anchor
    y, q = x.year, (x.month - 1) // 3 + 1
    qi = (y - y0) * QY + (q - qa)
    if x == c_q_last_day(y, q):
        return float(qi)
    return (qi - 1) + (x - c_q_first_day(y, q)).days / c_q_len(y, q)


def _c_clock(B: dict, periods: list[dict], v: dt.date) -> dict:
    """Дата оценки на годовой линейке (М§0.2): период p0 с v и число прошедших в нём кварталов
    pos (целые — закрытые, дробь — доля дней квартала q0); e = pos/n; начала периодов в годах от v
    по линейке 0,25 года на квартал."""
    facts_date = _c_as_date(c_bget(B, "meta.facts_date"))
    if v < facts_date:
        raise ControlInputError("дата оценки раньше даты фактов")
    anchor = c_per_parse(c_bget(B, "meta.anchor_period"))
    pos_abs = 0.0 if v == facts_date else _c_pos(v, anchor)
    first, p0 = 0.0, None
    for i, p in enumerate(periods):
        if first <= pos_abs < first + p["n"]:
            p0, pos = i, pos_abs - first
            break
        first += p["n"]
    if p0 is None:
        raise ControlInputError("дата оценки вне сетки (v ≥ E_Q)")
    t_start, t = {}, -pos / QY
    for i in range(p0, len(periods)):
        t_start[i] = t
        t += periods[i]["n"] / QY
    return {"v": v, "p0": p0, "pos": pos, "e": pos / periods[p0]["n"], "pos_abs": pos_abs,
            "t_start": t_start, "tau_end": {i: t_start[i] + periods[i]["n"] / QY for i in t_start}}


def _c_kappa_gap(B: dict, w: str, y: int, q: int, lag: int) -> float:
    """Разность реальных ставок κ-добавки квартала q − L (М§4.6): относительно мира-опоры книги с любым
    знаком, без ключа опоры — max(0, rr_W − rr_N); история до сетки — ноль (она у миров общая)."""
    y0, qa = c_per_parse(c_bget(B, "meta.anchor_period"))
    idx = (y - y0) * QY + (q - qa) - lag                # номер квартала сетки q − L
    if idx < 1:
        return 0.0                                      # история до сетки: rr одинакова во всех мирах
    yy, qq = y0 + (qa + idx - 1) // QY, (qa + idx - 1) % QY + 1
    return c_kappa_spread(B, w, yy, qq)


def _c_world_period(B: dict, w: str, p: dict, lag: int) -> dict:
    """Ряды мира за период по кварталам и κ-разрыв с лагом."""
    y, qs = p["year"], p["quarters"]
    out = {}
    for f in ("key_rate", "ofz_1y", "ofz_3y", "ofz_5y", "ofz_10y", "cpi", "wage_growth", "real_key"):
        out[f] = [c_world_quarter(B, w, f, y, q) for q in qs]
    out["kappa_gaps"] = [_c_kappa_gap(B, w, y, q, lag) for q in qs]
    return out


def c_control_context(book: dict, facts: dict, *, valuation_date=None, base_book: dict | None = None) -> dict:
    """Всё общее для клеток сетки: якорь, выведенные ключи, передача, миры, дисконт, A-P2u.

    base_book — книга до подмен (М§4.6): по ней берётся путь режима-опоры FVC, который не сдвигается
    вместе с осями и чувствительностями; без неё книга — сама себе база. Память разбора траекторий — на прогон:
    здесь она очищается (на числа не влияет)."""
    _TRAJ_PARSED.clear()
    A = c_anchor_state(book, facts)
    B, derived = c_resolve_anchor_keys(book, A)
    B0 = B if base_book is None else c_resolve_anchor_keys(base_book, A)[0]
    if c_bget(B, "dividends.buyback.enabled"):
        raise ControlUnsupported("байбэк включён — модуль не реализован (М§0.6)")
    recap, cell_floor = c_recap_rule(B), c_cell_floor(B)
    ded_parts = c_deduction_parts(B)                    # доли вычета якоря, постоянные в рублях (М§4.11); None — нет
    if c_bopt(B, "valuation.terminal.fade_mode") == FADE_SYMMETRIC:
        # симметричное угасание — правило справочного варианта таблиц книги, а не точки книги (М§7, §17)
        raise ControlUnsupported("симметричное угасание (valuation.terminal.fade_mode) — справочный вариант: "
                                 "контрольная модель считает точку книги с односторонним угасанием")
    periods = c_annual_periods(B)
    y0, qa = c_per_parse(c_bget(B, "meta.anchor_period"))
    quarterly = c_is_quarterly(B)
    growth = c_growth_rule(B)
    tr = c_transmission_ctl(B, A)
    books = B["nii"]["books"]
    s0_from = int(c_bnum(B, "nii.sigma0_from"))
    if not periods[0]["year"] <= s0_from <= periods[-1]["year"]:
        raise ControlInputError("nii.sigma0_from вне годов first_period…last_period (М прил. A)")
    shares = {int(h): float(v) for h, v in c_bget(B, "other.misc_quarter_shares").items()}
    if sorted(shares) != list(range(1, QY + 1)) or abs(sum(shares.values()) - 1.0) > 1e-9:
        raise ControlInputError("other.misc_quarter_shares: нужны доли кварталов 1…4 с суммой 1 (М§4.7)")
    v = _c_as_date(valuation_date or c_bget(B, "meta.valuation_date"))
    clock = _c_clock(B, periods, v)
    lag = int(c_bnum(B, "credit.real_rate_lag_q"))
    worlds = list(c_bget(B, "worlds.ids"))
    wv = {w: [_c_world_period(B, w, p, lag) for p in periods] for w in worlds}
    add = c_bnum(B, "valuation.beta_e") * c_bnum(B, "valuation.erp")
    ca = _c_as_date(c_bget(B, "meta.curve_as_of"))
    # перекат (М§0.2): Δ = 0,25 × (pos(v) − pos(curve_as_of)) по линейке кварталов
    shift = (0.25 * (clock["pos_abs"] - _c_pos(ca, (y0, qa)))
             if (c_bget(B, "valuation.roll_along_forwards") and ca < v) else 0.0)
    disc = {w: CDisc(c_bget(B, f"worlds.{w}.zero_curve"), add, shift) for w in worlds}
    dens = c_bget(B, "capital.rwa.density")
    oaf = A["OA_fixed"]
    dens_oaf = 0.0
    if oaf:
        if dens.get("other_assets_fixed") is None:
            raise ControlInputError("постоянные прочие активы без плотности capital.rwa.density.other_assets_fixed")
        dens_oaf = float(dens["other_assets_fixed"])
        if dens_oaf < 0.0:
            raise ControlInputError("capital.rwa.density.other_assets_fixed отрицательна (М§4.11)")
    mults = {}
    for rid in c_bget(B, "regimes.ids"):
        mult = c_bopt(B, f"regimes.{rid}.rwa_density_mult")
        if mult is not None:
            vals = [mult] if not isinstance(mult, dict) else [v for k, v in mult.items() if str(k) != "LT_from"]
            if any(float(v) <= 0.0 for v in vals):
                raise ControlInputError(f"regimes.{rid}.rwa_density_mult: значение ≤ 0 (М§4.11)")
            mults[rid] = mult
    links = tuple(float(c_bopt(B, key, 0.0)) for key in ("fees.volume_link", "other.insurance_volume_link",
                                                        "opex.volume_link"))
    if any(not 0.0 <= x <= 1.0 for x in links):
        raise ControlInputError("связь с объёмом вне [0; 1] (М§4.7)")
    link_base = c_bopt(B, "volumes.link_base", LINK_BASES[0])
    if any(links) and link_base not in LINK_BASES:
        raise ControlInputError(f"volumes.link_base: {link_base!r} (М§4.7)")
    loans_ids = [b for b, sp in books.items() if sp.get("sector")]
    fv_of = {b: c_bnum(B, f"nii.books.{b}.fv_share") for b in c_fv_books(books)}
    # шестой проход (М§4.6, §4.7): структура нормировки сегментной CoR; средние остатки базы iea кварталов фактов —
    # только у книги со связью с объёмом и базой iea (без связей база не читается, у баз loans и funds правило прежнее)
    seg_w = c_segment_structure(B, A, books, fv_of)
    iea_facts = c_iea_fact_quarters(A, books) if any(links) and link_base == LINK_BASES[-1] else None
    # пятый проход (М§4.3, §4.11, §7): путь постоянной части прочих активов, вычет сценария в рублях, доля λ_F
    q_last = c_qidx((y0, qa), *c_per_parse(c_bget(B, "meta.last_period")))
    oaf_path = c_oaf_path_rule(B, oaf, (y0, qa), q_last)
    geo = {"books": books, "dens": dens, "oaf": oaf, "dens_oaf": dens_oaf, "rwa_mult": mults, "oaf_path": oaf_path}
    rwa0 = _c_rwa_of(geo, None, y0, qa, A["E0"], A["OA"], 1.0, 1.0)
    gov = sum(float(c["sign"]) * float(c["value"]) for c in c_bget(B, "valuation.governance.components"))
    fv_ref = c_bget(B, "credit.fv_loans_ref")
    if fv_ref not in c_bget(B, "regimes.ids"):
        raise ControlInputError("credit.fv_loans_ref — не режим из regimes.ids (М§4.6)")
    ctx = {"A": A, "B": B, "derived": derived, "periods": periods, "tr": tr, "sigma0_from": s0_from,
           "misc_shares": shares, "clock": clock, "wv": wv, "disc": disc, "rwa0": rwa0, "worlds": worlds,
           "gov": c_bnum(B, "valuation.governance.discount"), "gov_sum": gov, "fv_ref": fv_ref, "B0": B0,
           "shock_year": c_shock_year(B),
           "posterior": dict(c_bget(B, "joint.regime_prob")), "dev": {}, "mu": {}, "anchor": (y0, qa),
           "quarterly": quarterly, "growth": growth, "links": links, "link_base": link_base,
           "loans": loans_ids, "biz": c_client_funds(books), "glide_memo": {},
           "recap": recap, "floor": cell_floor, "ded": ded_parts, "rub": c_rub_rule(B),
           "lam_f": c_fixed_growth_rule(B),
           # седьмой проход (М§4.11): квартал ключа доли инструментов q_χ; None — ключа нет или выключен
           "t2_from": c_t2_share_rule(B, (y0, qa)),
           # восьмой проход (М§4.4, §4.9–§4.11, §7): доля добавочного капитала, надбавка за субординацию T2, прочие
           # движения за концом сетки; None — ключа нет, он выключен или прочие движения терминала — ноль (none)
           "at1": c_at1_share_rule(B, (y0, qa), A["AT1"]), "t2p": c_t2_premium_rule(B, (y0, qa)),
           "om": c_om_terminal_rule(B, periods[-1]["year"]),
           # девятый проход (М§4.8, §4.9, §7): разрыв налога по правилу и купон якоря по ставке своего мира; None — ключа
           # нет или он выключен (число разрыва и слот купона фактов — строки образца)
           "tax": c_tax_structure_rule(B), "at1c": c_at1_coupon_rule(B),
           "fv": fv_of, "seg_w": seg_w, "iea_facts": iea_facts,
           "Q": q_last, **geo}
    if quarterly:
        if c_bopt(B, "dividends.policy.steps"):
            raise ControlInputError("непустой dividends.policy.steps в квартальном режиме (М§5.7.1)")
        ctx["divcal"] = c_div_calendar(B, A)
    ctx["bridge_amount"] = c_bridge_register(ctx)
    ctx["pending_amount"] = c_pending_register(ctx)
    c_regime_update_ctl(ctx)
    return ctx


def c_shock_year(B: dict) -> int:
    """Год шока кризиса = год якоря + regimes.crisis.shock_year_offset (М§3.2). Кризисные ключи
    привязаны к нему: квартальный профиль CoR, период разового убытка и первый год
    loan_growth_override обязаны лежать в году шока — иначе громкий отказ."""
    off = c_bget(B, "regimes.crisis.shock_year_offset")
    if isinstance(off, bool) or not isinstance(off, int) or off < 1:
        raise ControlInputError("regimes.crisis.shock_year_offset — целое ≥ 1 (М прил. A)")
    shock = c_per_parse(c_bget(B, "meta.anchor_period"))[0] + off
    cor = c_bget(B, "regimes.crisis.cor")
    if isinstance(cor, dict):
        for k, (ky, q1, q2) in _c_time_keys({str(k): v for k, v in cor.items()}).items():
            if q1 == q2 and ky != shock:
                raise ControlInputError(f"regimes.crisis.cor: квартальный ключ {k} вне года шока {shock}")
    if c_per_parse(c_bget(B, "regimes.crisis.one_off_loss.period"))[0] != shock:
        raise ControlInputError(f"regimes.crisis.one_off_loss.period вне года шока {shock}")
    over = c_bget(B, "regimes.crisis.loan_growth_override") or {}
    if over and min(int(k) for k in over) != shock:
        raise ControlInputError(f"regimes.crisis.loan_growth_override: первый год — не год шока {shock}")
    return shock


# ============================================================================ помощники клетки

def _c_fact_q(A: dict, line: str, y: int, q: int):
    rec = A["pnl"].get(f"{y}Q{q}")
    return None if rec is None else rec.get(line)


def _c_need_fact_q(A: dict, line: str, y: int, q: int) -> float:
    v = _c_fact_q(A, line, y, q)
    if v is None:
        raise ControlInputError(f"нет факта pnl_quarterly {y}Q{q}.{line}")
    return float(v)


def _c_fact_line(A: dict, line: str, y: int, q: int) -> float:
    """Факт строки в знаке движка: расходы — положительным числом (в отчётности — со знаком минус)."""
    v = _c_need_fact_q(A, line, y, q)
    return abs(v) if line == "opex" else v


def _c_floor(B: dict, s: str, which: str, y: int, q: int) -> float:
    base = c_bnum(B, f"capital.minimum.{which}")
    return base + sum(c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.{k}"), y, q)
                      for k in ("conservation", "sifi", "ccyb"))


def _c_partial(rho: float, n: int) -> tuple[float, float]:
    """Годовая агрегация подстройки ρ за n кварталов: (доля к цели на конец, средняя доля)."""
    lag = 1.0 - rho
    return 1.0 - lag ** n, 1.0 - sum(lag ** j for j in range(1, n + 1)) / n


def _c_path_mean(points: list[float]) -> float:
    """Средний остаток периода по остаткам на концах кварталов: среднее квартальных трапеций."""
    return sum((a + b) / 2.0 for a, b in zip(points, points[1:])) / (len(points) - 1)


def _c_geo_path(start: float, end: float, n: int) -> list[float]:
    """Остатки на концах кварталов периода при одном квартальном множителе (М§4.3): статья растёт от
    начала к концу периода геометрически — замкнутая форма, без прохода по кварталам клетки."""
    if start <= 0.0 or end <= 0.0:
        return [start + (end - start) * j / n for j in range(n + 1)]
    g = (end / start) ** (1.0 / n)
    return [start * g ** j for j in range(n + 1)]


def _c_unaudited_quarters(cutoffs: list[int], y: int, h: int) -> list[tuple[int, int]]:
    """Кварталы неаудированной прибыли на конец квартала (y, h) (М§4.11)."""
    yy, hh = y, h
    out = []
    while True:
        out.append((yy, hh))
        yy, hh = (yy - 1, QY) if hh == 1 else (yy, hh - 1)
        if hh in cutoffs:
            return out
        if len(out) > QY * 2:
            return out


# ============================================================================ клетка: один период

def _c_period(ctx: dict, cell: dict, st: dict, i: int, div: float, plan: dict | None = None,
              rec: float = 0.0) -> tuple[dict, dict]:
    """Годовой шаг клетки (порядок М§4.2 в годовом приближении). Возвращает (состояние, строка).

    plan — квартальный план года ветви с квартальным проходом капитала (М§17): пути кредитных книг по
    концам кварталов (loans; None — потенциальный прирост целиком) и решения о дивиденде года с кварталами
    решения, вычета и выплаты (divs). Без плана — годовая ветвь образца: одно решение div в квартал собрания.

    rec — взнос акционеров решения этого периода (М§4.14.2; только годовая ветвь книги с включённой
    докапитализацией): деньги приходят в конце квартала решения о взносе — квартала собрания, а при ключе
    decision_quarter квартала с этим номером в году, — капитал конца периода выше на взнос, в совокупный доход и
    в прибыль кварталов он не входит, а в среднем остатке балансирующих активов стоит по времени прихода, как
    доход своего квартала: со следующего квартала."""
    B, A, p = ctx["B"], ctx["A"], ctx["periods"][i]
    w, r, s = cell["world"], cell["regime"], cell["scenario"]
    y, qs, n = p["year"], p["quarters"], p["n"]
    frac, dfac = n / QY, p["days"] / DAYS_BASE
    wd = ctx["wv"][w][i]
    ref_w = c_bget(B, "nii.transmission.reference_world")
    wh = ctx["wv"][ref_w][i]
    books = B["nii"]["books"]
    y0, qa = ctx["anchor"]
    loans = [b for b, sp in books.items() if sp.get("sector")]
    biz, fv, oaf = ctx["biz"], ctx["fv"], ctx["oaf"]
    E, Ynew, row = dict(st["E"]), dict(st["y"]), {}

    def c_fv_part(vals):
        return sum(fv[b] * vals[b] for b in fv)

    # --- объёмы (М§4.3)
    gy = int(c_bnum(B, "volumes.guidance_year"))
    over = c_bget(B, "regimes.crisis.loan_growth_override") if r == R_CRISIS else {}
    over = {int(k): float(v) for k, v in (over or {}).items()}
    drift_until = int(c_bnum(B, "volumes.share_drift_until"))
    m_q = {}                                            # потенциальный прирост книги за квартал (М§4.13.1)
    for b in loans:
        sp = books[b]
        if y == gy:
            seg = sp["cor_segment"]
            if p["stub"]:
                start_seg = sum(st["E"][x] for x in loans if books[x]["cor_segment"] == seg)
                prev = A["prev_corp"] if seg == "corporate" else A["prev_retail"]
                mult = prev * (1.0 + c_bnum(B, f"volumes.guidance_growth.{seg}")) / start_seg
            else:
                mult = 1.0 + c_bnum(B, f"volumes.guidance_growth.{seg}")
            E[b] = st["E"][b] * mult
            m_q[b] = mult ** (1.0 / n) - 1.0
            continue
        if y in over:
            g = over[y]
        else:
            G = c_overlay_growth(B, w, "credit_growth", sp["sector"], y)
            d = c_premium(B, "volumes.loan_share_drift", LOAN_SECTORS, sp["sector"], y) if y <= drift_until else 0.0
            g = (1.0 + G) * (1.0 + d) - 1.0 + c_traj_mean(c_bget(B, f"regimes.{r}.loan_growth_adj"), y, qs)
        E[b] = st["E"][b] * (1.0 + g) ** frac
        m_q[b] = (1.0 + g) ** (1.0 / QY) - 1.0
    paths = plan.get("loans") if plan is not None else None
    if paths is not None:
        for b in loans:
            E[b] = paths[b][-1]
    fd = c_premium(B, "volumes.funds_share_drift", FUND_SEGMENTS, "retail", y, qs) if y <= drift_until else 0.0
    fd_c = c_premium(B, "volumes.funds_share_drift", FUND_SEGMENTS, "corporate", y, qs) if y <= drift_until else 0.0
    fr0 = st["E"][RETAIL_CURRENT] + st["E"][RETAIL_TERM]
    g_r = (1.0 + c_overlay_growth(B, w, "funds_growth", "retail", y)) * (1.0 + fd) - 1.0
    g_c = (1.0 + c_overlay_growth(B, w, "funds_growth", "corporate", y)) * (1.0 + fd_c) - 1.0
    fr1 = fr0 * (1.0 + g_r) ** frac
    for b in biz:
        E[b] = st["E"][b] * (1.0 + g_c) ** frac
    cf0, cf1 = sum(st["E"][b] for b in biz), sum(E[b] for b in biz)
    rcs = "nii.retail_current_share"
    lo, hi = (float(x) for x in c_bget(B, f"{rcs}.bounds"))
    share_target = sum(min(hi, max(lo, c_bnum(B, f"{rcs}.c_ref") - c_bnum(B, f"{rcs}.psi")
                                 * (k - c_bnum(B, f"{rcs}.key_ref")))) for k in wd["key_rate"]) / n
    rho_c = c_bnum(B, f"{rcs}.rho")
    c1 = st["c"] + _c_partial(rho_c, n)[0] * (share_target - st["c"])
    E[RETAIL_CURRENT], E[RETAIL_TERM] = c1 * fr1, (1.0 - c1) * fr1
    sum_loans = sum(E[b] for b in loans)
    loans_ac = sum_loans - c_fv_part(E) if fv else sum_loans
    wtf = c_bnum(B, "volumes.wholesale_to_funds")
    r_oa, r_ol = c_bnum(B, "volumes.other_assets_to_loans"), c_bnum(B, "volumes.other_liabilities_to_loans")
    r_al = c_bnum(B, "credit.allowance_ratio")
    wh_base = wtf * (fr1 + cf1)
    OA = r_oa * sum_loans
    if oaf:
        OA = OA + oaf                                   # постоянные прочие активы не растут (М§4.3)
    OL = r_ol * sum_loans
    AL = r_al * loans_ac
    # Средние остатки периода (М§0.3): небалансирующие статьи растут внутри периода одним квартальным
    # множителем, поэтому средний остаток — замкнутая сумма квартальных трапеций геометрического пути
    # (не полусумма начала и конца: та завышает средний остаток растущей статьи). Доля текущих счетов —
    # замкнутая подстройка к средней цели периода.
    fr_path = _c_geo_path(fr0, fr1, n)
    c_path = [st["c"] + (1.0 - (1.0 - rho_c) ** j) * (share_target - st["c"]) for j in range(n + 1)]
    # пути по концам кварталов периода: кредитные книги — план квартального прохода или геометрический
    # путь; средства клиентов-бизнеса — геометрический
    lpath = {b: (paths[b] if paths is not None else _c_geo_path(st["E"][b], E[b], n)) for b in loans}
    bpath = {b: _c_geo_path(st["E"][b], E[b], n) for b in biz}
    avg_nb = {b: _c_path_mean(lpath[b]) for b in loans}
    for b in biz:
        avg_nb[b] = _c_path_mean(bpath[b])
    avg_nb[RETAIL_CURRENT] = _c_path_mean([c * f for c, f in zip(c_path, fr_path)])
    avg_nb[RETAIL_TERM] = _c_path_mean([(1.0 - c) * f for c, f in zip(c_path, fr_path)])
    fr_avg = _c_path_mean(fr_path)
    cf_avg = sum(avg_nb[b] for b in biz)
    funds_avg = fr_avg + cf_avg
    loans_avg = sum(avg_nb[b] for b in loans)
    loans_ac_avg = loans_avg - c_fv_part(avg_nb) if fv else loans_avg
    funds0 = fr0 + cf0
    loans0 = sum(st["E"][b] for b in loans)
    ac_start = loans0 - c_fv_part(st["E"]) if fv else loans0
    # поправка среднего балансирующих активов на кривизну небалансирующих статей: LA = пассивы без
    # балансирующих + капитал − прочие активы, а полусумма начала и конца у растущих статей — не среднее
    curve_la = ((1.0 + wtf) * (funds_avg - (funds0 + fr1 + cf1) / 2.0)
                + (r_ol - r_oa - 1.0) * (loans_avg - (loans0 + sum_loans) / 2.0)
                + r_al * (loans_ac_avg - (ac_start + loans_ac) / 2.0))
    extra0 = max(0.0, st["E"][WHOLESALE] - wtf * funds0)             # добор опта на начало периода
    la0 = st["E"][SECURITIES] + st["E"][LIQUIDITY]
    assets_nb_avg = (1.0 + r_oa) * loans_avg - r_al * loans_ac_avg
    if oaf:
        assets_nb_avg = assets_nb_avg + oaf
    oaf_ends = None
    if ctx.get("oaf_path") is not None:
        # Путь постоянной части прочих активов (М§4.3): приращение к якорю на концах кварталов периода — от конца
        # прошлого периода (номер 0) до конца этого. Прочие активы конца периода несут приращение его последнего
        # квартала; деньги убывания при тех же пассивах и капитале ложатся в балансирующие активы (М§4.10).
        # Время в среднем остатке: предварительный баланс квартала уже несёт приращение квартала, и средний остаток
        # балансирующих статей квартала получает его наполовину — то есть средний остаток периода — среднее
        # квартальных трапеций пути приращения, а не полусумма начала и конца (поправка — в кривизне LA).
        k0 = c_qidx(ctx["anchor"], y, qs[0]) - 1
        oaf_ends = [c_oaf_change(ctx, *c_qper(ctx["anchor"], k0 + j)) for j in range(n + 1)]
        OA = OA + oaf_ends[-1]
        oaf_mean = _c_path_mean(oaf_ends)
        curve_la = curve_la - (oaf_mean - (oaf_ends[0] + oaf_ends[-1]) / 2.0)
        assets_nb_avg = assets_nb_avg + oaf_mean
    cf_path = [sum(bpath[b][j] for b in biz) for j in range(n + 1)]
    loans_path = [sum(lpath[b][j] for b in loans) for j in range(n + 1)]
    # концы кварталов кредитов по амортизированной стоимости — знаменатель годовой CoR (М§0.3)
    ac_path = [sum(lpath[b][j] * ((1.0 - fv[b]) if b in fv else 1.0) for b in loans) for j in range(n + 1)]

    # --- ставки книг (М§4.4): средняя за период и на конец. Сжатие φ — двумя скалярами пути: φ_A снимает
    # спред кредитных книг Φ_A, φ_L × X_W,q удорожает пассивы Φ_L; X_W,q — разность опорных ставок книг
    # Φ_A мира и мира H с долями ω_b якоря (от текущего остатка кредитов добавка не зависит)
    phi_a, phi_l, omega = ctx["tr"]["phi_assets"], ctx["tr"]["phi_liab"], ctx["tr"]["phi_weights"]
    x_w = [sum(om * (wd[c_ref_field(books[b]["ref"])][j] - wh[c_ref_field(books[b]["ref"])][j])
               for b, om in omega.items()) for j in range(n)]
    ybar, y_q = {}, {}
    for b, sp in books.items():
        ref = c_ref_field(sp["ref"])
        tgt = []
        for j, q in enumerate(qs):
            rv = wd[ref][j]
            sv = c_spread_at(ctx, b, y, q)
            if sp["side"] == LOANS_SIDE:
                if sp.get("phi"):
                    sv -= phi_a * (rv - wh[ref][j])
                tgt.append(rv + sv)
            else:
                tgt.append(float(sp["beta"]) * rv + sv + (phi_l * x_w[j] if sp.get("phi") else 0.0))
        T = sum(tgt) / n
        k_end, k_avg = _c_partial(float(sp["rho"]), n)
        Ynew[b] = st["y"][b] + k_end * (T - st["y"][b])
        ybar[b] = st["y"][b] + k_avg * (T - st["y"][b])
        # ставка квартала j периода — та же замкнутая подстройка к средней цели (среднее по j = ybar)
        y_q[b] = [st["y"][b] + (1.0 - (1.0 - float(sp["rho"])) ** (j + 1)) * (T - st["y"][b]) for j in range(n)]

    # --- строки, не зависящие от балансирующих статей
    days_q = [c_q_len(y, q) for q in qs]
    kap = c_bnum(B, "credit.kappa")
    dev = ctx["dev"].get(r, {})
    # CoR клетки по кварталам (М§4.6): путь режима через мост + κ-добавка мира + отклонение A-P2u;
    # за период — среднее по дням (резервы начисляются по дням, М§0.3)
    cor_prof = [c_cor_path_engine(ctx, r, y, q) + kap * wd["kappa_gaps"][j] + _c_dev_at(dev.get("cor"), y, q)
                for j, q in enumerate(qs)]
    cor_c = sum(c * d for c, d in zip(cor_prof, days_q)) / p["days"]
    d_nim = sum(_c_dev_at(dev.get("nim"), y, q) for q in qs) / n
    near = c_traj_mean(c_bget(B, "regimes.near_nim_shift"), y, qs)        # ближний сдвиг ЧПМ (М§3.2)
    seg_rel = dict.fromkeys(SEGMENTS, 1.0)
    seg_w = ctx["seg_w"] if "seg_w" in ctx else c_segment_structure(B, A, books, fv)
    if seg_w is not None:
        # CoR_σ = CoR × rel_σ / Σ w × rel (М§4.6): на структуре нормировки w общая CoR равна пути режима
        norm = sum(seg_w[sg] * c_bnum(B, f"credit.segment_relative.{sg}") for sg in SEGMENTS)
        seg_rel = {sg: c_bnum(B, f"credit.segment_relative.{sg}") / norm for sg in SEGMENTS}
    seg_cor = {sg: cor_c * seg_rel[sg] for sg in seg_rel}
    llp = 0.0
    for b in loans:
        share = (1.0 - fv[b]) if b in fv else 1.0
        llp += seg_cor[books[b]["cor_segment"]] * share * avg_nb[b] * dfac
    # средние кредиты по амортизированной стоимости периода по сегментам — знаменатели строки резервов (печать, тесты)
    ac_avg_seg = {sg: sum(((1.0 - fv[b]) if b in fv else 1.0) * avg_nb[b] for b in loans
                          if books[b]["cor_segment"] == sg) for sg in seg_rel}
    # Кредитная переоценка кредитов по СС сверх опоры (М§4.6): FVC_q = f × (CoR_corporate,q − CoR_ref,q)
    # × Ē^СС_q × d_q/365. CoR_ref — путь режима-опоры книги до розыгрыша (книга-опора контекста) через
    # мост с той же сегментной поправкой, без κ-добавки и отклонения A-P2u (они — в CoR клетки и потому
    # действуют и на кредиты по СС); сдвиг путей CoR всех режимов опору не двигает.
    # Отклонение от опоры меняет величину и знак внутри года (профиль кризиса, затухание δ), поэтому
    # строка считается по кварталам: кредиты по СС растут внутри периода одним квартальным множителем.
    ref_prof = [c_cor_ref_engine(ctx, y, q) for q in qs]
    f_fv = c_bnum(B, "credit.fv_loans_factor")
    fv_avg_q, fvc_q = [0.0] * n, [0.0] * n              # у книги без fv_share строка FVC — ноль (М§4.6)
    for b, fvs in fv.items():
        ss0, ss1 = fvs * st["E"][b], fvs * E[b]
        ss_g = (ss1 / ss0) ** (1.0 / n) if ss0 > 0.0 and ss1 > 0.0 else 1.0
        rel_b = seg_rel[books[b]["cor_segment"]]
        for j in range(n):
            avg_j = ss0 * ss_g ** j * (1.0 + ss_g) / 2.0                     # средние кредиты по СС квартала
            fv_avg_q[j] = fv_avg_q[j] + avg_j
            fvc_q[j] = fvc_q[j] + (f_fv * rel_b * (cor_prof[j] - ref_prof[j])
                                   * avg_j * days_q[j] / DAYS_BASE)
    fvc = sum(fvc_q)
    # ЧКД, расходы, страхование — г/г к тому же кварталу (М§0.3, §4.7): база — факт или квартал
    # прошлого года клетки; кварталы года хранятся в состоянии (сезонность переносится из истории)
    wage = wd["wage_growth"]
    ov = {int(k): float(v) for k, v in (c_bget(B, "fees.growth_override") or {}).items()}
    fees_b = _c_yoy_quarters(ctx, st, "fees_net", y, qs)
    opex_b = _c_yoy_quarters(ctx, st, "opex", y, qs)
    ins_b = _c_yoy_quarters(ctx, st, "insurance_net", y, qs)
    link_f, link_i, link_c = ctx["links"]
    link_on = bool(link_f or link_i or link_c)
    rg = c_bget(B, "opex.real_growth")
    igw = c_bget(B, "other.insurance_growth_vs_wages")

    def c_volume_lines(v):
        """Комиссии, расходы и страхование кварталов периода (М§4.7). v — рост объёма периода (годовая
        форма связи с объёмом); None — связи нулевые, формулы образца."""
        if y in ov and y == y0 and p["stub"]:
            # рост за год в году якоря: оставшиеся кварталы достраивают год до цели одним темпом
            full_prev = sum(_c_fact_line(A, "fees_net", y - 1, q) for q in range(1, QY + 1))
            done = sum(_c_fact_line(A, "fees_net", y, q) for q in range(1, qa + 1))
            g_rest = (full_prev * (1.0 + ov[y]) - done) / sum(fees_b) - 1.0
            f_q = [x * (1.0 + g_rest) for x in fees_b]
        elif y in ov:
            f_q = [x * (1.0 + ov[y]) for x in fees_b]
        elif v is None or not link_f:
            gvw = c_bget(B, "fees.growth_vs_wages")
            f_q = [fees_b[j] * (1.0 + wage[j] + c_traj_at(gvw, y, q)) for j, q in enumerate(qs)]
        else:
            gvw = c_bget(B, "fees.growth_vs_wages")
            f_q = [fees_b[j] * (1.0 + wage[j] + c_traj_at(gvw, y, q) + link_f * (v - wage[j]))
                   for j, q in enumerate(qs)]
        if v is None or not link_c:
            o_q = [x * (1.0 + wage[j]) * (1.0 + c_traj_at(rg, y, qs[j])) for j, x in enumerate(opex_b)]
        else:
            o_q = [x * (1.0 + wage[j] + link_c * (v - wage[j])) * (1.0 + c_traj_at(rg, y, qs[j]))
                   for j, x in enumerate(opex_b)]
        if v is None or not link_i:
            i_q = [x * (1.0 + wage[j] + c_traj_at(igw, y, qs[j])) for j, x in enumerate(ins_b)]
        else:
            i_q = [x * (1.0 + wage[j] + c_traj_at(igw, y, qs[j]) + link_i * (v - wage[j]))
                   for j, x in enumerate(ins_b)]
        return f_q, o_q, i_q

    # рост объёма периода v (М§4.7) — годовая форма: сумма средних остатков базы кварталов периода к
    # сумме тех же кварталов прошлого года; база iea считается в цикле баланса (зависит от LA)
    link_base = ctx["link_base"]
    funds_path = [a + b for a, b in zip(fr_path, cf_path)]
    v_now = None
    if link_on and link_base != LINK_BASES[-1]:
        ends = loans_path if link_base == LINK_BASES[0] else funds_path
        v_now = c_volume_growth(ctx, st, link_base, y, qs, sum((a + b) / 2.0 for a, b in zip(ends, ends[1:])))
    fees_q, opex_q, ins_q = c_volume_lines(v_now)
    fees, opex, ins = sum(fees_q), sum(opex_q), sum(ins_q)
    idx, I = [], st["I"]
    for j in range(n):
        I *= (1.0 + wd["cpi"][j]) ** (1.0 / QY)
        idx.append(I)
    # Годовые суммы книги (М§0.3, §4.7): квартал = год × доля квартала × индекс цен мира; у «прочего» —
    # доли other.misc_quarter_shares, у непрофильного — 1/4. В году якоря правила разные:
    # непрофильный результат закрывает год остатком (книга − факт отчётных кварталов, поровну на
    # оставшиеся кварталы); «прочее» остатком не закрывается — уровень книги × доля квартала, как в
    # любом году, сумма года — выход модели
    m_sh = ctx["misc_shares"]
    even = {h: 1.0 / QY for h in range(1, QY + 1)}
    nc_q = _c_book_quarters(ctx, p, idx, "noncore.result_real", even, residual_of="noncore_net")
    ms_q = _c_book_quarters(ctx, p, idx, "other.misc_net_real", m_sh)
    noncore, misc = sum(nc_q), sum(ms_q)
    one = 0.0
    if r == R_CRISIS:
        ol = c_bget(B, "regimes.crisis.one_off_loss")
        oy, oq = c_per_parse(ol["period"])
        if oy == y and oq in qs:
            one = float(ol["amount"])
    tau_stat = [c_traj_at(c_bget(B, "tax.statutory"), y, q) for q in qs]
    # девятый проход (М§4.8): у книги с ключом tax.structure налог — правилом в рублях по кварталам профиля годовой строки,
    # число разрыва не читается, купон в совокупном доходе — целиком (τ_cpn = 0); без ключа — строка образца
    tax_rule = ctx.get("tax")
    tau_eff = sum(tau_stat) / n + c_bnum(B, "tax.effective_gap") if tax_rule is None else None
    ot = 0.0
    if int(c_bnum(B, "tax.one_off.year")) == y and 1 in qs:
        ot = c_bnum(B, "tax.one_off.prob") * c_bnum(B, "tax.one_off.amount")
    nci = c_bnum(B, "pnl.nci_share")
    tenor = c_bget(B, "oci.fvoci_tenor")
    y_end = wd[tenor][-1]
    y_prev = st["y_tenor"]
    M, D = c_bnum(B, "oci.fvoci_maturity"), c_bnum(B, "oci.fvoci_duration")
    pull = 1.0 - 0.25 / M
    # переоценка FVOCI по кварталам смены полугодия мира, с подтягиванием к номиналу до конца периода
    path_y = [y_prev] + list(wd[tenor])
    reval = sum((path_y[j + 1] - path_y[j]) * pull ** (n - 1 - j) for j in range(n))
    fvos = c_bnum(B, "oci.fvoci_share")
    # купон якоря квартала купона (М§4.9): слот фактов, у книги с ключом capital.at1_coupon — формула по ключевой своего мира
    cpn = c_anchor_coupon(ctx, w, y, A["cpn_quarter"]) if A["cpn_quarter"] in qs else 0.0
    cpn_tau = c_traj_at(c_bget(B, "tax.statutory"), y, A["cpn_quarter"]) if cpn else 0.0
    # налоговая ставка купона в совокупном доходе τ_cpn (М§4.9): законная, у книги с ключом tax.structure — 0 (экономия — в
    # налоге, §4.8)
    cpn_tau_ci = cpn_tau if tax_rule is None else 0.0
    tau_cpn_q = tau_stat if tax_rule is None else [0.0] * n
    om = sum(c_traj_at(c_bget(B, "equity.other_movements"), y, q) for q in qs)
    nim_shift = c_traj_mean(c_bget(B, f"regimes.{r}.nim_shift"), y, qs)
    fvr_on = bool(c_bget(B, "other.fvtpl_bond_reval"))
    hq = qs[-1]
    paid_shift, dp_end, dpreg, left = 0.0, 0.0, 0.0, []
    dpreg_q = None                                      # DPreg на концах кварталов периода — у годовой ветви
    if plan is None:
        dpreg_q = [0.0] * n
        agm = int(c_bnum(B, "dividends.calendar.agm_quarter"))
        pay_q = int(c_bnum(B, "dividends.calendar.payment_quarter"))
        reg_q = int(c_bnum(B, "dividends.calendar.reg_deduction_quarter"))
        declared_here = agm in qs       # и в неполном году якоря: решение — в своём квартале (М§17)
        # Дивиденды к выплате (М§5.4): каждая объявленная сумма несёт свои кварталы выплаты и вычета из
        # регуляторного капитала — по датам записи реестра (declared | paid), без записи или без даты в
        # ней — по календарю книги. Просроченная выплата (квартал записи раньше периода) уходит в первом
        # квартале.
        items = [dict(it) for it in st["pay"]]
        if declared_here and div:
            items.append({"amt": div, **_c_dividend_dates(ctx, y - 1)})
        div_list = [(qs.index(agm), div)] if (declared_here and div) else []
    else:
        # квартальный режим (М§5.7): очереди выплат и вычетов — номерами кварталов сетки; постоянная часть
        # остатка «дивиденды к выплате» якоря не выплачивается и в регуляторный капитал не возвращается
        items = []
        k_first = c_qidx(ctx["anchor"], y, qs[0])
        k_last = k_first + n - 1
        dp_end = st["dp_perm"]
        by_quarter = [0.0] * n
        for it in plan["divs"]:
            by_quarter[it["dec"] - k_first] += it["amt"]
        div = sum(by_quarter)
        div_list = [(j, amt) for j, amt in enumerate(by_quarter) if amt]
        for it in [dict(x) for x in st["dq"]] + [dict(x) for x in plan["divs"]]:
            if it["pay"] <= k_last:
                j_pay = max(it["pay"], k_first) - k_first
                paid_shift += ((n - (j_pay + 1) + 0.5) / n - 0.5) * it["amt"]
            else:
                dp_end += it["amt"]
            if it["reg"] > k_last:
                dpreg += it["amt"]
            if it["pay"] > k_last or it["reg"] > k_last:
                left.append(it)
    # Время капитальных потоков в среднем остатке балансирующих статей (М§4.2 шаг 5, §4.10):
    # предварительный баланс квартала — при BV_(q−1) − Div_q и DP_q, поэтому доход квартала j входит в
    # активы со следующего квартала — вес (n − j)/n (доход внутри года неравномерен: сезонность
    # расходов и комиссий, профиль CoR, — поэтому вес берётся по квартальному профилю дохода, а не
    # (n − 1)/(2n) равномерного); объявление дивиденда ликвидность не меняет, а выплата уменьшает её
    # уже на конец своего квартала — вес (n − j_выплаты + ½)/n. Оба — вместо ½ у полусуммы начала и конца.
    w_ci = [(n - (j + 1)) / n - 0.5 for j in range(n)]
    for it in items:
        when = it["pay"]
        if when is None:
            q_pay = pay_q if pay_q in qs else None
        elif when < (y, qs[0]):
            q_pay = qs[0]
        else:
            q_pay = when[1] if (when[0] == y and when[1] in qs) else None
        if q_pay is None:
            left.append(it)
            dp_end += it["amt"]
        else:
            paid_shift += ((n - (qs.index(q_pay) + 1) + 0.5) / n - 0.5) * it["amt"]
        # DPreg: + Div на конец квартала ГОСА, 0 с конца квартала отсечки (М§4.11, §5.4)
        reg = it["reg"] if it["reg"] is not None else (it["agm_year"], reg_q)
        if (it["agm_year"], agm) <= (y, hq) < reg:
            dpreg += it["amt"]
        for j, q in enumerate(qs):
            if (it["agm_year"], agm) <= (y, q) < reg:
                dpreg_q[j] += it["amt"]
    at1, ncib = A["AT1"], A["NCI"]
    m_liq = c_bnum(B, "volumes.liquid_min_share")
    ssl = c_bnum(B, "volumes.securities_share_of_liquid")
    dia = c_bnum(B, "nii.dia_rate")

    def c_grow_w(base, start, end):
        g = end / start if start > 0.0 and end > 0.0 else 1.0
        w = [b_ * g ** ((j + 0.5) / n) for j, b_ in enumerate(base)]
        tot = sum(w)
        return [x / tot for x in w] if tot else [d / p["days"] for d in days_q]

    if paths is None:
        w_cr = c_grow_w([c * d for c, d in zip(cor_prof, days_q)], sum(st["E"][b] for b in loans), sum_loans)
    else:
        # путь кредитов задан планом: вес квартала — CoR × дни × средний остаток кредитов квартала
        w_cr = [c * d * (a + b) / 2.0 for c, d, a, b in zip(cor_prof, days_q, loans_path, loans_path[1:])]
        tot_cr = sum(w_cr)
        w_cr = [x / tot_cr for x in w_cr] if tot_cr else [d / p["days"] for d in days_q]

    # взнос акционеров (М§4.14.2): в конце квартала решения о взносе; до конца периода деньги лежат в
    # балансирующих активах столько же, сколько доход этого квартала, — вес (n − j)/n вместо ½ у полусуммы
    # начала и конца
    rec_list, rec_shift = [], 0.0
    if rec:
        asks = ctx["recap"]["quarter"] if (plan is None and ctx.get("recap") is not None) else None
        if asks not in qs:
            raise ControlInputError("взнос акционеров вне квартала решения о взносе годовой ветви (М§4.14)")
        rec_list = [(qs.index(asks), rec)]
        rec_shift = w_ci[qs.index(asks)] * rec

    # --- RWA конца периода (М§4.11): дрейф плотности, валютный индекс — от баланса не зависят
    dens = c_bget(B, "capital.rwa.density")
    dn = st["Dn"] * ((1.0 + c_bnum(B, "capital.rwa.density_drift_rate")) ** frac
                     if y <= int(c_bnum(B, "capital.rwa.density_drift_until")) else 1.0)
    fxp, xf, xf_q = st["fxp"], 1.0, [1.0] * n
    if c_bget(B, "capital.rwa.fx.enabled"):
        fx, pistar = c_bnum(B, "capital.rwa.fx.share"), c_bnum(B, "capital.rwa.fx.foreign_inflation")
        for j in range(n):
            fxp *= ((1.0 + wd["cpi"][j]) / (1.0 + pistar)) ** (1.0 / QY)
            xf_q[j] = 1.0 - fx + fx * fxp
        xf = 1.0 - fx + fx * fxp

    # --- восьмой проход (М§4.4, §4.9–§4.11): добавочный капитал по доле RWA клетки и надбавка за субординацию T2.
    # Добавочный капитал конца периода с квартала ключа — α_c × RWA конца, а RWA несут вес риска балансирующих активов
    # с деньгами выпуска: уравнение неподвижной точки М§4.10 на балансе конца периода (c_at1_fixed_point). Внутри
    # периода AT1 кварталов — доля на квартальный профиль RWA (геометрически между началом и концом периода; у ветви с
    # квартальным проходом — AT1 кварталов прохода из плана), выпуск квартала — деньги конца квартала: в среднем
    # остатке балансирующих активов по времени прихода, как взнос. Купон сверх базы и надбавка — по кварталам периода
    # на остаток конца прошлого квартала.
    at1r, t2p = ctx.get("at1"), ctx.get("t2p")
    keyed8 = at1r is not None or t2p is not None
    k_first = c_qidx(ctx["anchor"], y, qs[0])
    where = f"клетка {w}/{r}/{s}, {p['label'] if 'label' in p else y}"
    if keyed8:
        g_end, b_end = c_rwa_parts(ctx, r, y, hq, E, OA, dn, xf)
        rs = st["rwa"]

        def c_rwa_profile(re: float, j: int) -> float:
            """RWA конца квартала j периода: геометрически между началом и концом периода, как у точек проверки."""
            return re if j == n - 1 else rs * (re / rs) ** ((j + 1) / n)
    at1_on, a1s, a1_mid, j_set = False, None, None, None
    if at1r is not None:
        at1_start = st["at1"]
        at1_on = k_first + n - 1 >= at1r["from"]            # в периоде есть кварталы с q ≥ q_α
        j_set = at1r["from"] - 1 - k_first                  # номер квартала q_α − 1 в периоде
        a1s = st.get("a1s")
        if a1s is None and plan is not None and plan.get("a1s") is not None:
            a1s = plan["a1s"]                               # доля, заданная кварталом прохода этого года
        if a1s is None and at1_on:
            if not 0 <= j_set < n - 1:
                raise ControlInputError(f"{where}: доля добавочного капитала к кварталу ключа не задана (М§4.11)")
            a1_mid = j_set                                  # квартал q_α − 1 внутри периода: доля — профилем RWA шага
        plan_at1 = plan.get("at1_q") if plan is not None else None
        rate_q = [kr + at1r["spread"] for kr in wd["key_rate"]]      # c_α,q = key_W,q + s_α (М§4.9)
    if t2p is not None:
        q_chi = ctx.get("t2_from")
        t2_traj = c_bget(B, T2_TRAJ)
        if q_chi is not None and k_first - 1 >= q_chi:
            t2_start = st["t2s"] * st["rwa"]                # T2 конца прошлого периода — доля на его RWA
        else:
            t2_start = c_traj_at(t2_traj, *c_qper(ctx["anchor"], k_first - 1))
        plan_t2 = plan.get("t2_q") if plan is not None else None

    # --- балансирующие статьи и ОПУ: фиксированная точка по BV на конец (М§4.10 в годовом виде)
    bv_end = st["BV"] + st.get("ci_guess", 0.0) - div
    if rec:
        bv_end = bv_end + rec
    ci = st.get("ci_guess", 0.0)
    ci_q = [ci / n] * n
    asset_books = [b for b, sp in books.items() if sp["side"] == LOANS_SIDE]
    one_at = c_per_parse(c_bget(B, "regimes.crisis.one_off_loss.period")) if one else None
    om_q = [c_traj_at(c_bget(B, "equity.other_movements"), y, q) for q in qs]
    ov_q = [c_traj_at(c_bget(B, "regimes.near_nim_shift"), y, q) + c_traj_at(c_bget(B, f"regimes.{r}.nim_shift"), y, q)
            + _c_dev_at(dev.get("nim"), y, q) for q in qs]              # сдвиги ЧПМ квартала (М§4.4)
    v_iea = None                                        # рост объёма периода у базы iea — в цикле баланса
    at1_end, a1_now = at1, None
    for _ in range(FIT_ITER):
        if at1_on:
            # М§4.10: добавочный капитал конца периода — доля RWA, RWA несут его деньги; закрытая форма, две ветви
            assets_nb = sum_loans - AL + OA
            la_min = m_liq * assets_nb / (1.0 - m_liq)
            la_free = (fr1 + cf1 + wh_base + OL + dp_end + ncib) + bv_end - assets_nb
            if a1_mid is None:
                fp = c_at1_fixed_point(g_end, b_end, la_free, la_min, a1s, where)
            else:
                # квартал q_α − 1 внутри периода: доля — AT1_0 к RWA этого квартала по профилю шага, а RWA конца
                # периода зависят от доли; простая итерация (наклон — b × AT1 / RWA, много меньше единицы)
                guess = g_end + b_end * max(la_free + at1, la_min)
                for _ in range(FIT_ITER):
                    a1_now = c_at1_share_of(ctx, c_rwa_profile(guess, a1_mid))
                    fp = c_at1_fixed_point(g_end, b_end, la_free, la_min, a1_now, where)
                    if abs(fp["rwa"] - guess) <= FIT_TOL * fp["rwa"]:
                        break
                    guess = fp["rwa"]
            at1_end, la, extra = fp["at1"], fp["la"], fp["extra"]
        else:
            liab_nb = fr1 + cf1 + wh_base + OL + dp_end + at1 + ncib
            assets_nb = sum_loans - AL + OA
            la = liab_nb + bv_end - assets_nb
            la_min = m_liq * assets_nb / (1.0 - m_liq)
            extra = max(0.0, la_min - la)
            la = max(la, la_min)
        E[SECURITIES], E[LIQUIDITY], E[WHOLESALE] = ssl * la, (1.0 - ssl) * la, wh_base + extra
        if keyed8:
            re_now = fp["rwa"] if at1_on else g_end + b_end * la       # RWA конца периода этого оборота
        if at1r is not None:
            # AT1 на концах кварталов периода, выпуск квартала и купон сверх базы на остаток конца прошлого квартала
            alpha = a1s if a1_mid is None else a1_now
            at1_q = []
            for j in range(n):
                if k_first + j < at1r["from"]:
                    at1_q.append(at1)
                elif j == n - 1:
                    at1_q.append(at1_end)
                elif plan_at1 is not None:
                    at1_q.append(plan_at1[j])
                else:
                    at1_q.append(alpha * c_rwa_profile(re_now, j))
            at1_prev = [at1_start] + at1_q[:-1]
            issue = [a - b_ for a, b_ in zip(at1_q, at1_prev)]
            cpn_new_q = [c_at1_coupon_new(rate_q[j], at1_prev[j], at1r["base"], days_q[j]) for j in range(n)]
            cpn_new_net_q = [x * (1.0 - tau_cpn_q[j]) for j, x in enumerate(cpn_new_q)]
        if t2p is not None:
            # T2 клетки на концах кварталов периода (траектория до q_χ, доля на профиль RWA с него; у ветви с
            # квартальным проходом — T2 кварталов прохода) и надбавка на остаток конца прошлого квартала (М§4.4)
            chi_now = c_t2_share_step(ctx, st, p, re_now, plan) if q_chi is not None else None
            t2_prev = [t2_start]
            for j in range(n - 1):
                if plan_t2 is not None:
                    t2_prev.append(plan_t2[j])
                elif q_chi is None or k_first + j < q_chi:
                    t2_prev.append(c_traj_at(t2_traj, y, qs[j]))
                else:
                    t2_prev.append(chi_now * c_rwa_profile(re_now, j))
            sp_q = [c_t2_premium_q(t2p["spread"], t2_prev[j], t2p["base"], days_q[j]) for j in range(n)]
            sp = sum(sp_q)
        avg = dict(avg_nb)
        shift_la = sum(w * c for w, c in zip(w_ci, ci_q)) - paid_shift + curve_la
        if rec:
            shift_la = shift_la + rec_shift
        if at1_on:
            # выпуск квартала — деньги конца квартала: в среднем остатке по времени прихода, как взнос (М§4.10)
            shift_la = shift_la + sum(wq * x for wq, x in zip(w_ci, issue))
        la_avg = (la0 + la) / 2.0 + shift_la
        extra_avg = (extra0 + extra) / 2.0
        if extra0 > 0.0 and extra > 0.0:
            # минимум ликвидности связывает на обоих концах периода: LA стоит на минимуме весь период, а
            # время капитальных потоков и кривизну несёт добор опта (он — разность минимума и свободной LA)
            la_avg = m_liq / (1.0 - m_liq) * assets_nb_avg
            extra_avg = la_avg - ((la0 - extra0 + la - extra) / 2.0 + shift_la)
        avg[SECURITIES], avg[LIQUIDITY] = ssl * la_avg, (1.0 - ssl) * la_avg
        avg[WHOLESALE] = wtf * funds_avg + extra_avg
        iea = sum(avg[b] for b in asset_books)
        if link_on and v_now is None:
            # база объёма — средние процентные активы шага (М§4.7)
            v_iea = c_volume_growth(ctx, st, link_base, y, qs, iea * n)
            fees_q, opex_q, ins_q = c_volume_lines(v_iea)
            fees, opex, ins = sum(fees_q), sum(opex_q), sum(ins_q)
        inc = sum(ybar[b] * avg[b] for b in asset_books) * dfac
        exp_ = sum(ybar[b] * avg[b] for b in books if b not in asset_books) * dfac
        dia_amt = dia * fr_avg * dfac
        ovl = (near + nim_shift + d_nim) * iea * dfac      # ближний сдвиг + сдвиг режима + A-P2u (М§4.4)
        if t2p is None:
            nii = inc - exp_ - dia_amt + ovl
        else:
            nii = inc - exp_ - dia_amt - sp + ovl          # надбавка за субординацию — процентный расход (М§4.4)
        fvr = 0.0
        if fvr_on:
            fvr = -(c_bnum(B, "oci.fvtpl_bond_duration") * (y_end - y_prev)
                    * c_bnum(B, "oci.fvtpl_bond_share") * avg[SECURITIES])
        pbt = nii - llp - fvc + fees + ins + misc + fvr + noncore - opex + one
        # ЧПМ квартала внутри периода (ожидание A-P2u, М§12, и профиль ЧПД): ставки квартала y_q при
        # структуре баланса периода; сдвиги ЧПМ (ближний, режима, отклонение A-P2u) — квартала
        nim_q = []
        for j, q in enumerate(qs):
            d_rate = sum((y_q[b][j] - ybar[b]) * avg[b] * (1.0 if b in asset_books else -1.0) for b in books) / iea
            nim_q.append(nii / iea / dfac + d_rate + ov_q[j] - (near + nim_shift + d_nim))
        # профиль прибыли внутри периода (для времени капитальных потоков, E_q, точек проверки и
        # капитала на дату оценки): ЧКД, расходы, страхование, «прочее» и непрофильный — свои кварталы;
        # ЧПД — по дням × ЧПМ квартала × рост процентных активов внутри периода (геометрически от начала
        # к концу), резервы — по CoR квартала × дни × рост кредитов, FVC — свои кварталы, FVR — по дням;
        # разовый убыток и купон AT1 — в своих кварталах; фонд FVOCI — квартальной рекурсией М§4.9 на
        # среднем портфеле периода (OCI квартала — его приращение)
        w_nii = c_grow_w([d * m for d, m in zip(days_q, nim_q)] if min(nim_q) > 0.0 else days_q,
                         sum(st["E"][b] for b in asset_books), sum(E[b] for b in asset_books))
        pbt_q = []
        for j, q in enumerate(qs):
            # ЧПД квартала: проценты книг — профилем ЧПМ, надбавка за субординацию — в своём квартале
            nii_j = nii * w_nii[j] if t2p is None else (nii + sp) * w_nii[j] - sp_q[j]
            pbt_q.append(nii_j + fvr * days_q[j] / p["days"] - llp * w_cr[j] - fvc_q[j]
                         + fees_q[j] + ins_q[j] + ms_q[j] + nc_q[j] - opex_q[j] + (one if one_at == (y, q) else 0.0))
        if tax_rule is None:
            tax = tau_eff * pbt
            tax_q = None
        else:
            # Разрыв налога по правилу (М§4.8): налог квартала профиля — в рублях по слагаемым; IIS — процентный доход
            # книги бумаг (ставка книги на средний остаток периода; профиль кварталов — ставка квартала × дни × рост
            # остатка бумаг внутри периода), купон — якоря в квартале купона и сверх базы по кварталам. Налог года —
            # сумма кварталов профиля: при прибыли во всех кварталах — правило на годовых строках; в году с убыточным
            # кварталом множитель max(PBT, 0) — кварталов профиля (своё упрощение, docs/CONTROL-MODEL.md)
            iis = ybar[SECURITIES] * avg[SECURITIES] * dfac
            w_iis = c_grow_w([y_q[SECURITIES][j] * days_q[j] for j in range(n)], st["E"][SECURITIES], E[SECURITIES])
            iis_q = [iis * x for x in w_iis]
            coupon_q = [(cpn if q == A["cpn_quarter"] else 0.0) + (cpn_new_q[j] if at1r is not None else 0.0)
                        for j, q in enumerate(qs)]
            ts_q = [c_tax_coupon(tax_rule, tau_stat[j], coupon_q[j]) for j in range(n)]
            tax_q = [c_tax_rule(tax_rule, tau_stat[j], pbt_q[j], iis_q[j], ts_q[j]) for j in range(n)]
            tax = sum(tax_q)
        ni = pbt - tax - ot
        ni_sh = ni * (1.0 - nci)
        r_end = st["R"] * pull ** n - D * reval * fvos * avg[SECURITIES] * (1.0 - sum(tau_stat) / n)
        oci = r_end - st["R"]
        if at1r is None:
            ci = ni_sh - cpn * (1.0 - cpn_tau_ci) + oci + om
        else:
            # купон сверх базы — после налога законной ставкой своего квартала, как купон якоря (М§4.9); у книги с ключом
            # tax.structure — целиком
            ci = ni_sh - cpn * (1.0 - cpn_tau_ci) - sum(cpn_new_net_q) + oci + om
        r_q, rr = [], st["R"]
        for j in range(n):
            rr = rr * pull - D * (path_y[j + 1] - path_y[j]) * fvos * avg[SECURITIES] * (1.0 - sum(tau_stat) / n)
            r_q.append(rr)
        oci_q = [r_q[0] - st["R"]] + [r_q[j] - r_q[j - 1] for j in range(1, n)]
        ni_q, ci_q = {}, []
        for j, q in enumerate(qs):
            if tax_q is None:
                ni_q[(y, q)] = (pbt_q[j] * (1.0 - tau_eff) - (ot if q == 1 else 0.0)) * (1.0 - nci)
            else:
                ni_q[(y, q)] = (pbt_q[j] - tax_q[j] - (ot if q == 1 else 0.0)) * (1.0 - nci)
            if at1r is None:
                ci_q.append(ni_q[(y, q)] - (cpn * (1.0 - cpn_tau_ci) if q == A["cpn_quarter"] else 0.0)
                            + oci_q[j] + om_q[j])
            else:
                ci_q.append(ni_q[(y, q)] - (cpn * (1.0 - cpn_tau_ci) if q == A["cpn_quarter"] else 0.0)
                            - cpn_new_net_q[j] + oci_q[j] + om_q[j])
        new_bv = st["BV"] + ci - div
        if rec:
            new_bv = new_bv + rec
        done = abs(new_bv - bv_end) <= FIT_TOL * max(1.0, abs(new_bv))
        bv_end = new_bv
        if done:
            break


    # --- RWA и нормативы (М§4.11–§4.12) на конец периода
    rwa = _c_rwa_of(ctx, r, y, hq, E, OA, dn, xf)
    drifting = y <= int(c_bnum(B, "capital.rwa.density_drift_until"))
    dn_q = [st["Dn"] * ((1.0 + c_bnum(B, "capital.rwa.density_drift_rate")) ** ((j + 1) / QY) if drifting else 1.0)
            for j in range(n)]
    # доля инструментов клетки (М§4.11, ключ capital.n20.t2_share): с квартала ключа T2 = χ_c × RWA; долю задаёт шаг
    # квартала q_χ − 1 своими RWA — и пробный, и окончательный (c_t2_share_step); без ключа — None, прежняя строка
    t2s = c_t2_share_step(ctx, st, p, rwa, plan)
    a1s_after = None
    if at1r is not None:
        # доля добавочного капитала после шага (М§4.11): заданная раньше; заданная кварталом q_α − 1 внутри периода —
        # профилем RWA шага (в цикле); квартал q_α − 1 в конце периода — RWA конца периода (AT1 там ещё факт якоря)
        a1s_after = a1s if a1s is not None else a1_now if a1_mid is not None else (
            c_at1_share_of(ctx, rwa) if j_set == n - 1 else None)
    cap = _c_capital(ctx, s, y, hq, bv_end, dpreg, r_end, rwa, {**st["ni_q"], **ni_q}, t2s,
                     at1_end if at1r is not None else None)
    if ctx.get("t2_from") is not None:
        row["t2s"] = t2s
    if tax_rule is not None:
        # ряд tau_eff у книги с ключом — маржинальная ставка τ_stat + o × [PBT > 0] годовой строки (М§4.8)
        tau_eff = c_tax_marginal(tax_rule, sum(tau_stat) / n, pbt)
    row.update(nii=nii, llp=llp, fvc=fvc, fees=fees, opex=opex, ins=ins, misc=misc, noncore=noncore,
               fvr=fvr, one_off=one, pbt=pbt, tax=tax, ot=ot, ni=ni, ni_sh=ni_sh, oci=oci,
               cpn=cpn, cpn_net=cpn * (1.0 - cpn_tau_ci), om=om, ci=ci, div=div, bv=bv_end, R=r_end, R_q=r_q,
               loans=sum_loans, loans_ac=loans_ac, iea=iea, iea_end=sum(E[b] for b in asset_books), funds=fr1 + cf1,
               securities=E[SECURITIES], liquidity=E[LIQUIDITY], wholesale=E[WHOLESALE],
               wholesale_extra=extra, oa=OA, ol=OL, al=AL, dp=dp_end, dpreg=dpreg, rwa=rwa,
               assets=sum_loans - AL + E[SECURITIES] + E[LIQUIDITY] + OA,
               liabilities=fr1 + cf1 + E[WHOLESALE] + OL + dp_end + bv_end + at1_end + ncib,
               nim=nii / iea / dfac, nim_books=(nii - ovl if t2p is None else nii + sp - ovl) / iea / dfac, nim_q=nim_q,
               cor=cor_c, cor_mgmt=(c_to_mgmt(A, "cor", cor_c) if c_bget(B, "regimes.cor_basis") == "mgmt"
                                    else cor_c),
               cir=opex / (nii + fees + ins + misc + fvr) if (nii + fees + ins + misc + fvr) else None,
               roe=ni_sh / ((st["BV"] + bv_end) / 2.0), y_liq_end=Ynew[LIQUIDITY],
               y_sec_end=Ynew[SECURITIES], c_wh_end=Ynew[WHOLESALE],
               tau_eff=tau_eff, share_target=share_target, c=c1, ni_q=ni_q, ci_q=ci_q, shift_la=shift_la,
               near=near, nim_shift=nim_shift, misc_q=ms_q, noncore_q=nc_q, fvc_q=fvc_q,
               cor_q=cor_prof, cor_ref_q=ref_prof, idx_q=idx, fv_avg_q=fv_avg_q, days_q=days_q,
               loans_ac_avg=loans_ac_avg, paid_shift=paid_shift, curve_la=curve_la, la_avg=la_avg,
               wholesale_avg=avg[WHOLESALE], assets_nb_avg=assets_nb_avg, funds_avg=funds_avg,
               x_q=x_w, rates_end=dict(Ynew), div_list=div_list, m_q=m_q, fr_path=fr_path, cf_path=cf_path,
               rec=rec, rec_list=rec_list, dpreg_q=dpreg_q,
               loans_path=loans_path, loans_ac_ends=ac_path, dn_q=dn_q, xf_q=xf_q,
               v_volume=v_now if v_iea is None else v_iea,
               books_end={b: E[b] for b in loans}, seg_rel=seg_rel, ac_avg_seg=ac_avg_seg,
               fees_q=fees_q, opex_q=opex_q, ins_q=ins_q, **cap)
    if oaf_ends is not None:
        row.update(oaf_change=oaf_ends[-1], oaf_ends=oaf_ends)      # путь постоянной части (М§4.3): ΔOA на концах кварталов
    if at1r is not None:
        # добавочный капитал (М§4.9–§4.11): AT1 конца периода и кварталов, выпуск кварталов, доля после шага; купон
        # строки — купон якоря и купон сверх базы (ряд coupon ядра — CPN целиком), ключевая мира кварталов — для c_α,Q
        row.update(at1=at1_end, at1_q=at1_q, at1_issue=issue, a1s=a1s_after, cpn_anchor=cpn,
                   cpn_new=sum(cpn_new_q), cpn_new_q=cpn_new_q, cpn_new_net=sum(cpn_new_net_q),
                   cpn_new_net_q=cpn_new_net_q,
                   cpn=cpn + sum(cpn_new_q), cpn_net=cpn * (1.0 - cpn_tau_ci) + sum(cpn_new_net_q),
                   key_q=list(wd["key_rate"]))
    if t2p is not None:
        # надбавка за субординацию (М§4.4): ряд кварталов и T2 конца прошлого квартала, на который она начислена
        row.update(sp=sp, sp_q=sp_q, t2_prev_q=t2_prev)
    if tax_rule is not None:
        # разрыв налога по правилу (М§4.8): процентный доход книги бумаг, налог, экономия купона и ставки кварталов профиля;
        # законная ставка года (средняя кварталов) — для терминала; τ_cpn = 0
        row.update(iis=iis, iis_q=iis_q, tax_q=tax_q, tax_coupon=sum(ts_q), tax_coupon_q=ts_q, coupon_q=coupon_q,
                   pbt_q=pbt_q, tau_stat=sum(tau_stat) / n, tau_cpn=0.0,
                   tau_eff_q=[c_tax_marginal(tax_rule, tau_stat[j], pbt_q[j]) for j in range(n)])
    if ctx.get("at1c") is not None:
        # купон якоря по ставке своего мира (М§4.9): купон квартала купона и ключевая мира кварталов периода
        row.update(cpn_anchor=cpn, key_q=list(wd["key_rate"]))
    qv = dict(st["qv"])
    for j, q in enumerate(qs):
        qv[("fees_net", y, q)], qv[("opex", y, q)], qv[("insurance_net", y, q)] = fees_q[j], opex_q[j], ins_q[j]
    nst = {"E": E, "y": Ynew, "c": c1, "BV": bv_end, "R": r_end, "pay": left, "Dn": dn,
           "fxp": fxp, "I": I, "y_tenor": y_end, "D": st["D"], "ci_guess": ci,
           "ni_q": {**st["ni_q"], **ni_q}, "qv": qv}
    if ctx.get("t2_from") is not None:
        nst["t2s"] = t2s
    if at1r is not None:
        nst.update(at1=at1_end, a1s=a1s_after,
                   cpn_q={**st["cpn_q"], **{(y, q): cpn_new_net_q[j] for j, q in enumerate(qs)}})
    if plan is not None:
        nst.update(pay=[], dq=left, dp_perm=st["dp_perm"], Epot=st["Epot"])
    if link_on:
        # концы кварталов базы объёма — для роста «к тому же кварталу прошлого года» (М§4.7)
        vend = dict(st.get("vend", {}))
        for j, q in enumerate(qs):
            vend[(y, q)] = {LINK_BASES[0]: loans_path[j + 1], LINK_BASES[1]: funds_path[j + 1],
                            LINK_BASES[-1]: iea}
        nst["vend"] = vend
    return nst, row


PART_LETTERS = ("Q", "H")                 # буквы части года в ключе времени траектории: квартал и полугодие


def c_premium(B: dict, key: str, names: tuple, name: str, y: int, quarters=None) -> float:
    """Премия роста года (М§4.3): число (одна на все книги — форма образца) или словарь траекторий с
    ключами ровно names; значение словаря — значение года траектории (М§0.4, c_traj_year). `quarters` — кварталы
    периода (их передаёт только премия средств клиентов): квартал, заданный в траектории ключом квартала или
    полугодия, читается этим ключом, квартал без такого ключа — значением года; премия периода — среднее его
    кварталов. Значение года считается по всей траектории: год, названный четырьмя кварталами или двумя
    полугодиями, — заданный, одиночные ключи на значения других лет не влияют."""
    val = c_bget(B, key)
    if isinstance(val, dict):
        if sorted(str(k) for k in val) != sorted(names):
            raise ControlInputError(f"{key}: ключи словаря — не ровно {', '.join(names)} (М§4.3)")
        traj = val[name]
        timed = isinstance(traj, dict) and quarters is not None and any(c_premium_keyed(traj, y, q) for q in quarters)
        if not timed:
            return c_traj_year(traj, y)
        year = c_traj_year(traj, y)
        return sum(c_traj_at(traj, y, q) if c_premium_keyed(traj, y, q) else year for q in quarters) / len(quarters)
    return c_bnum(B, key)


def c_premium_keyed(traj: dict, y: int, q: int) -> bool:
    """Квартал q года y задан в траектории ключом квартала или ключом своего полугодия."""
    names = {str(k) for k in traj}
    return f"{y}Q{q}" in names or f"{y}H{1 if q <= 2 else 2}" in names


def c_volume_growth(ctx: dict, st: dict, base: str, y: int, qs, now: float) -> float:
    """Рост объёма периода v (М§4.7) в годовой форме: now — сумма средних остатков базы по кварталам
    периода; делитель — та же сумма по тем же кварталам прошлого года (концы кварталов до якоря — факты
    balance.history, конец якоря — остатки якоря, позже — путь клетки). У базы iea квартал прошлого года после якоря —
    средние процентные активы шага того квартала, а квартал фактов (x ≤ 0) — в определении клетки: полусумма отчётных
    концов минус половина прироста капитала до дивидендов (c_iea_fact_quarters)."""
    A, anchor = ctx["A"], ctx["anchor"]
    last = LINK_BASES[-1]

    def c_end(yy, qq):
        if (yy, qq) > anchor:
            return st["vend"][(yy, qq)][base]
        if (yy, qq) == anchor:
            E0 = A["E0"]
            if base == LINK_BASES[0]:
                return sum(E0[b] for b in ctx["loans"])
            return E0[RETAIL_CURRENT] + E0[RETAIL_TERM] + sum(E0[b] for b in ctx["biz"])
        val = A["history"].get(f"{yy}Q{qq}", {}).get(base)
        if val is None:
            raise ControlInputError(f"нет конца квартала balance.history.{yy}Q{qq}.{base} для связи с объёмом (М§4.7)")
        return float(val)

    prev = 0.0
    for q in qs:
        yy, qq = y - 1, q
        if base == last:
            if (yy, qq) > anchor:
                prev += st["vend"][(yy, qq)][base]      # средние процентные активы шага того квартала
            else:
                prev += c_iea_fact_base(ctx, yy, qq)    # квартал фактов — в определении клетки
            continue
        py, pq = (yy - 1, QY) if qq == 1 else (yy, qq - 1)
        prev += (c_end(py, pq) + c_end(yy, qq)) / 2.0
    if prev <= 0.0:
        raise ControlInputError("база объёма прошлого года не положительна (М§4.7)")
    return now / prev - 1.0


def c_fact_volume_base(iea_prev: float, iea_end: float, bv_prev: float, bv_end: float, div: float) -> dict:
    """Средний остаток базы объёма iea квартала фактов x (М§4.7) — в определении клетки. Средние процентные активы
    клетки — полусумма начала квартала и предварительного конца, где балансирующие книги стоят при BV_(q−1) − Div_q,
    без совокупного дохода и взноса квартала; отчётные концы — окончательные, выше предварительного на прирост
    капитала до дивидендов ΔE_x = bv[x] − bv[x−1] + Div_x (пока минимум ликвидности не связывает). Поэтому
    A_x = (iea[x−1] + iea[x] − ΔE_x) / 2. Возвращает ΔE_x, A_x и прежнюю полусумму концов (справочно)."""
    delta_e = bv_end - bv_prev + div
    return {"delta_e": delta_e, "a": (iea_prev + iea_end - delta_e) / 2.0, "a_ends": (iea_prev + iea_end) / 2.0}


def c_div_pool(rec: dict):
    """Сумма строки истории дивидендов, вычтенная из bv_common при решении (М§4.7, прил. B): pool_all_classes —
    дивиденды всех категорий акций, без поля — pool_declared; None — не задано ни то, ни другое."""
    for field in DIV_POOLS:
        val = _c_nodeval(rec.get(field))
        if val is not None:
            return float(val)
    return None


def c_iea_fact_quarters(A: dict, books: dict) -> dict:
    """Средние остатки базы iea кварталов фактов x = −3…0 (М§4.7; квартал x = 0 — якорь): {(год, квартал): {x,
    iea_prev, iea, bv_prev, bv, div, delta_e, a, a_ends}}. Концы iea — balance.history (на якоре — сумма книг активов
    якоря, М§4.4), bv — history.bv_common (на якоре — balance.equity.bv_common); Div_x — сумма c_div_pool строк
    dividends.history и dividends.history_before с днём решения decided_date в квартале x.

    Отказы (громкие, М§4.7): нет конца iea или bv_common на нужном конце; строка с решением в квартале окна без суммы;
    строка с суммой больше нуля без дня решения, чей квартал прибыли (period, без него — четвёртый квартал года
    year) не раньше x = −11: решение по ней могло прийтись на окно базы."""
    anchor = A["anchor"]
    xs = range(-(QY - 1), 1)
    div = dict.fromkeys(xs, 0.0)
    for rec in list(A["div_history"]) + list(A["div_history_before"]):
        day = _c_nodeval(rec.get("decided_date"))
        amount = c_div_pool(rec)
        if day:
            x = c_qidx_of_date(anchor, _c_as_date(day))
            if x in div:
                if amount is None:
                    raise ControlInputError(f"строка dividends {rec.get('period') or rec.get('year')}: решение "
                                            f"{day} в окне базы объёма iea без суммы ({' и '.join(DIV_POOLS)} не "
                                            f"заданы) (М§4.7)")
                div[x] += amount
            continue
        if amount is None or amount <= 0.0:
            continue
        per = _c_nodeval(rec.get("period"))
        if per:
            k = c_qidx(anchor, *c_per_parse(per))
        elif rec.get("year") is not None:
            k = c_qidx(anchor, int(_c_nodeval(rec["year"])), QY)
        else:
            raise ControlInputError("строка dividends с суммой без дня решения и без квартала прибыли (М§4.7)")
        if k >= UNDATED_FROM:
            raise ControlInputError(f"строка dividends {per or rec.get('year')}: сумма {amount} без дня решения "
                                    f"decided_date — решение могло прийтись на окно базы объёма iea (М§4.7)")
    E0 = A["E0"]
    iea0 = sum(E0[b] for b, sp in books.items() if sp["side"] == LOANS_SIDE)

    def c_hist_end(x, field):
        if x == 0:
            return iea0 if field == LINK_BASES[-1] else A["BV"]
        yy, qq = c_qper(anchor, x)
        val = A["history"].get(f"{yy}Q{qq}", {}).get(field)
        if val is None:
            raise ControlInputError(f"нет конца квартала balance.history.{yy}Q{qq}.{field} для базы объёма iea "
                                    f"квартала фактов (М§4.7)")
        return float(val)

    out = {}
    for x in xs:
        ends = {f: (c_hist_end(x - 1, f), c_hist_end(x, f)) for f in (LINK_BASES[-1], "bv_common")}
        (iea_prev, iea_end), (bv_prev, bv_end) = ends[LINK_BASES[-1]], ends["bv_common"]
        base = c_fact_volume_base(iea_prev, iea_end, bv_prev, bv_end, div[x])
        out[c_qper(anchor, x)] = {"x": x, "iea_prev": iea_prev, "iea": iea_end, "bv_prev": bv_prev, "bv": bv_end,
                                  "div": div[x], **base}
    return out


def c_iea_fact_base(ctx: dict, y: int, q: int) -> float:
    """Средний остаток базы iea квартала фактов (y, q) — A_x по М§4.7 из таблицы контекста (c_iea_fact_quarters)."""
    table = ctx.get("iea_facts")
    if table is None:
        table = ctx["iea_facts"] = c_iea_fact_quarters(ctx["A"], ctx["books"])
    if (y, q) not in table:
        raise ControlInputError(f"квартал фактов {y}Q{q} вне окна базы объёма iea x = −3…0 (М§4.7)")
    return table[(y, q)]["a"]


def c_segment_structure(B: dict, A: dict, books: dict, fv: dict):
    """Структура нормировки сегментной CoR w (М§4.6): CoR_σ = CoR × rel_σ / Σ w × rel, и на структуре w общая CoR
    клетки равна пути режима. None — схема выключена (credit.segment_relative.enabled: false): CoR одна на все книги,
    ключ доли юрлиц не читается. С ключом credit.segment_relative.corporate_share_ref — доля юрлиц ключа и остаток до
    единицы у физлиц; без ключа — доли сегментов в кредитах по амортизированной стоимости якоря (правило образца).
    Ключ — число от 0 до 1 включительно; null при включённой схеме — отказ (М§0.1: нераскрытое значение, а не
    «ключа нет»), как и значение не числом или вне [0; 1]."""
    if not c_bget(B, "credit.segment_relative.enabled"):
        return None
    if _c_key_given(B, SEG_SHARE):
        share = c_bget(B, SEG_SHARE)
        if not _c_plain_number(share) or not 0.0 <= share <= 1.0:
            raise ControlInputError(f"{SEG_SHARE} — не число от 0 до 1 включительно: {share!r} (М§4.6)")
        return {SEGMENTS[0]: float(share), SEGMENTS[1]: 1.0 - float(share)}
    loans = [b for b, sp in books.items() if sp.get("sector")]
    ac0 = {sg: sum(A["E0"][b] * ((1.0 - fv[b]) if b in fv else 1.0) for b in loans
                   if books[b]["cor_segment"] == sg) for sg in SEGMENTS}
    tot = sum(ac0.values())
    return {sg: ac0[sg] / tot for sg in SEGMENTS}


def _c_rwa_of(ctx: dict, r, y: int, q: int, E: dict, OA: float, dn: float, xf: float) -> float:
    """RWA (М§4.11): плотности книг и прочих активов × дрейф плотности × валютный индекс × множитель
    режима. Постоянные прочие активы входят со своей плотностью; r = None — RWA_0 якоря (без множителя). У книги с
    путём постоянной части (М§4.3) OA несёт приращение квартала ΔOA_q: растущая часть — OA − OA_fixed − ΔOA_q с
    плотностью прочих активов, уровень якоря — с ω_oaf, приращение — со своим весом ω_Δ (без его ключа — ω_oaf)."""
    dens, oaf = ctx["dens"], ctx["oaf"]
    base = sum(float(dens[b]) * E[b] for b in ctx["books"] if b in dens)
    if ctx.get("oaf_path") is not None:
        d = c_oaf_change(ctx, y, q)
        base = (base + float(dens["other_assets"]) * (OA - oaf - d) + ctx["dens_oaf"] * oaf
                + ctx["oaf_path"]["density"] * d)
    elif oaf:
        base = base + float(dens["other_assets"]) * (OA - oaf) + ctx["dens_oaf"] * oaf
    else:
        base = base + float(dens["other_assets"]) * OA
    rwa = base * dn * xf
    mult = ctx["rwa_mult"].get(r) if r is not None else None
    if mult is not None:
        rwa = rwa * c_traj_at(mult, y, q)               # роспуск надбавок режима — на все RWA клетки
    return rwa


def c_qidx(anchor: tuple, y: int, q: int) -> int:
    """Номер квартала (y, q) на сетке: якорь — 0, первый прогнозный — 1 (М§0.2)."""
    return (y - anchor[0]) * QY + (q - anchor[1])


def c_qper(anchor: tuple, k: int) -> tuple[int, int]:
    """Квартал сетки с номером k → (год, квартал в году)."""
    pos = anchor[0] * QY + (anchor[1] - 1) + k
    return pos // QY, pos % QY + 1


def c_qidx_of_date(anchor: tuple, d: dt.date) -> int:
    """Номер календарного квартала сетки, содержащего дату (М§5.7.2)."""
    return c_qidx(anchor, d.year, (d.month - 1) // 3 + 1)


def _c_dev_at(dv, y: int, q: int) -> float:
    """Затухающее отклонение A-P2u в квартале (y, q): ρ^k × m — от последнего наблюдения окна не позже
    этого квартала, k — кварталов после него (М§12). Квартал раньше первого наблюдения окна — ноль;
    наблюдённый квартал несёт своё отклонение, даже если за ним в окне есть более позднее."""
    if not dv:
        return 0.0
    last = None
    for ys, qs, m in dv["trail"]:
        if (ys, qs) <= (y, q):
            last = (ys, qs, m)
    if last is None:
        return 0.0
    return dv["rho"] ** ((y - last[0]) * QY + (q - last[1])) * last[2]


def c_cor_path_engine(ctx: dict, r: str, y: int, q: int) -> float:
    """Путь CoR режима в квартале в базисе движка (мост при cor_basis: mgmt, М§3.2, §4.6)."""
    c = c_traj_at(c_bget(ctx["B"], f"regimes.{r}.cor"), y, q)
    return c_to_engine(ctx["A"], "cor", c) if c_bget(ctx["B"], "regimes.cor_basis") == "mgmt" else c


def c_cor_ref_engine(ctx: dict, y: int, q: int) -> float:
    """Опора FVC в квартале (М§4.6): путь режима credit.fv_loans_ref книги-опоры — до розыгрыша осей,
    чувствительностей и поисков — в базисе движка."""
    B0 = ctx["B0"]
    c = c_traj_at(c_bget(B0, f"regimes.{ctx['fv_ref']}.cor"), y, q)
    return c_to_engine(ctx["A"], "cor", c) if c_bget(B0, "regimes.cor_basis") == "mgmt" else c


def _c_yoy_quarters(ctx: dict, st: dict, line: str, y: int, qs) -> list[float]:
    """База «к тому же кварталу прошлого года» по кварталам периода (М§0.3): факт до якоря
    включительно, иначе квартал прошлого года клетки."""
    A = ctx["A"]
    y0, qa = ctx["anchor"]
    out = []
    for q in qs:
        if (y - 1, q) <= (y0, qa):
            out.append(_c_fact_line(A, line, y - 1, q))
        else:
            out.append(st["qv"][(line, y - 1, q)])
    return out


def _c_book_quarters(ctx: dict, p: dict, idx: list[float], key: str, shares: dict,
                     residual_of: str | None = None) -> list[float]:
    """Годовая сумма книги по кварталам периода (М§0.3, §4.7): год × доля квартала × индекс цен.
    residual_of — строка фактов, которой год якоря закрывается остатком (книга − факт отчётных
    кварталов, по долям оставшихся кварталов): так считается непрофильный результат. Без неё
    («прочее») оставшиеся кварталы года якоря — та же формула, что в прочие годы."""
    B, A = ctx["B"], ctx["A"]
    y, qs = p["year"], p["quarters"]
    yearly = c_traj_year(c_bget(B, key), y)
    if residual_of is None or not p["stub"]:
        return [yearly * shares[q] * idx[j] for j, q in enumerate(qs)]
    qa = ctx["anchor"][1]
    rest = yearly - sum(_c_fact_line(A, residual_of, y, q) for q in range(1, qa + 1))
    tot = sum(shares[q] for q in qs)
    if tot <= 0.0:
        raise ControlInputError(f"{key}: доли оставшихся кварталов года якоря в сумме 0 — остаток некуда разложить")
    return [rest * shares[q] / tot * idx[j] for j, q in enumerate(qs)]


def c_deduction_parts(B: dict):
    """Части вычета якоря каждого норматива у книги с ключами доли, постоянной в рублях (М§4.11):
    {норматив: {share — доля η_j, fix — постоянная в рублях часть Dfix_j = η_j × Ded_j,0, grow — растущая с RWA
    часть Dgrow_j = (1 − η_j) × Ded_j,0}}; Ded_j,0 — ключ вычета якоря своего норматива (число книги или значение
    слова anchor). None — ключей доли нет: вычет растёт с RWA целиком, прежней строкой образца. Доля — число от 0
    до 1 включительно, только числом; ключи задаются вместе — доля у одного норматива без доли у другого и доля вне
    границ — отказ книги (прил. A, № 21). Ключ со значением null — отказ, а не «ключа нет»: нераскрытое значение
    поведенческого ключа (М§4.11, §17, прил. A № 21); «постоянной части нет» пишется нулём. Доля одного норматива
    вычет другого не меняет."""
    present = {name: _c_key_present(B, key) for name, key in DED_SHARE.items()}
    if not any(present.values()):
        return None
    shares = {name: c_bopt(B, key) for name, key in DED_SHARE.items()}
    for name, eta in shares.items():
        if present[name] and eta is None:
            raise ControlInputError(f"{DED_SHARE[name]}: null у ключа доли вычета якоря — отказ: «постоянной части "
                                    f"нет» пишется нулём (М§4.11, §17, прил. A № 21)")
    parts = {}
    for name, eta in shares.items():
        if eta is None:
            raise ControlInputError(f"{DED_SHARE[name]}: доля вычета якоря задана у одного норматива и не задана у "
                                    f"другого (М§4.11, прил. A № 21)")
        if not _c_plain_number(eta) or not 0.0 <= eta <= 1.0:
            raise ControlInputError(f"{DED_SHARE[name]} — не число от 0 до 1 включительно (М§4.11)")
        level = c_bnum(B, DED_ANCHOR[name])
        parts[name] = {"share": float(eta), "fix": eta * level, "grow": (1.0 - eta) * level}
    return parts


def c_deduction_at(part: dict, growth: float) -> float:
    """Вычет норматива при RWA квартала или точки (М§4.11): Ded_j,q = Dgrow_j × RWA_q / RWA_0 + Dfix_j. growth —
    отношение RWA_q / RWA_0 по итоговым RWA клетки (с дрейфом плотности, валютным индексом и множителем режима):
    за ними идёт только растущая часть, постоянная на них не откликается. В квартале якоря отношение равно единице,
    и вычет равен ключу вычета якоря при любой доле."""
    return part["grow"] * growth + part["fix"]


def c_deductions(ctx: dict, rwa: float) -> tuple[float, float]:
    """Вычеты Ded20 и Ded11 при RWA квартала или точки (М§4.11). У книги с ключами доли вычета якоря, постоянной
    в рублях, — растущая часть за RWA и постоянная сумма якоря; без ключей — вычет якоря, растущий с RWA целиком
    (прежняя строка образца, без правки формул). Путь вычета сценария deduction_pp сюда не входит: он задан в долях
    RWA и вычитается из норматива после деления."""
    growth = rwa / ctx["rwa0"]
    parts = ctx.get("ded")
    if parts is None:
        B = ctx["B"]
        return c_bnum(B, DED_ANCHOR[NORM_TOTAL]) * growth, c_bnum(B, DED_ANCHOR[NORM_BASE]) * growth
    return c_deduction_at(parts[NORM_TOTAL], growth), c_deduction_at(parts[NORM_BASE], growth)


def _c_key_given(B: dict, dotted: str) -> bool:
    """Ключ стоит в книге — и тогда, когда его значение null (М§0.1: null в пути, который читается, — отказ,
    null ≠ 0); c_bopt этого не различает."""
    cur = B
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def _c_trajectory_or_fail(traj, where: str):
    """Траектория книги (М§0.4): число или словарь ключей времени; null — в ней самой или в её значении — отказ."""
    if traj is None or (isinstance(traj, dict) and any(v is None for v in traj.values())):
        raise ControlInputError(f"{where}: null в траектории (М§0.1, прил. A № 23)")
    if not (_c_plain_number(traj) or isinstance(traj, dict)):
        raise ControlInputError(f"{where}: не траектория — {traj!r} (М§0.4)")
    return traj


def c_rub_rule(B: dict):
    """Вычет сценария в рублях (М§4.11; ключи capital.reg_scenarios.<s>.deduction_rub.{n20_0, n1_1}): {сценарий:
    {норматив: траектория в млрд ₽}}; None — ключа нет ни у одного сценария (прежняя строка вычета). Объект задаётся
    у всех сценариев перечня или ни у одного и несёт ровно две траектории — n20_0 (Н20.0) и n1_1 (слот второго
    норматива); иначе, и при null в траектории, — отказ книги (прил. A № 23): сценарий без ключа молча вычитал бы
    ноль рублей. Знак сумм любой (отрицательная — высвобождение)."""
    ids = [str(s) for s in c_bget(B, "capital.reg_scenarios.ids")]
    given = [s for s in ids if _c_key_given(B, f"capital.reg_scenarios.{s}.{RUB_KEY}")]
    if not given:
        return None
    if len(given) != len(ids):
        raise ControlInputError(f"capital.reg_scenarios.<s>.{RUB_KEY}: задан у {given}, а не у всех сценариев {ids} "
                                f"(М§4.11, прил. A № 23)")
    out = {}
    for s in ids:
        obj = c_bget(B, f"capital.reg_scenarios.{s}.{RUB_KEY}")
        if not isinstance(obj, dict) or sorted(str(k) for k in obj) != sorted(RUB_SLOT.values()):
            raise ControlInputError(f"capital.reg_scenarios.{s}.{RUB_KEY}: нужен объект ровно с траекториями "
                                    f"{sorted(RUB_SLOT.values())} (прил. A № 23)")
        out[s] = {name: _c_trajectory_or_fail(obj[slot], f"capital.reg_scenarios.{s}.{RUB_KEY}.{slot}")
                  for name, slot in RUB_SLOT.items()}
    return out


def c_rub_at(ctx: dict, s: str, y: int, h: int) -> tuple[float, float]:
    """Рубли сценария s в вычетах Н20.0 и второго норматива в квартале (y, h) — значения траекторий книги своим
    читателем М§0.4 в квартале точки (М§4.11); у книги без ключа — нули (вызывающий их не прибавляет)."""
    rub = ctx.get("rub")
    if rub is None:
        return 0.0, 0.0
    memo = ctx.setdefault("rub_memo", {})
    k = (s, y, h)
    if k not in memo:
        memo[k] = (c_traj_at(rub[s][NORM_TOTAL], y, h), c_traj_at(rub[s][NORM_BASE], y, h))
    return memo[k]


def c_oaf_path_rule(B: dict, oaf: float, anchor: tuple, q_last: int):
    """Путь постоянной части прочих активов (М§4.3; ключ volumes.other_assets_fixed_change): {traj, v0 — значение
    траектории в квартале якоря, density — вес риска приращения ω_Δ}; None — ключа нет (ΔOA_q ≡ 0, прежняя строка).

    Отказы книги: якорное условие — |v(якорь)| > 1e-9 млрд ₽ (и траектория, которая начинается ключом года после
    якоря: квартал якоря читает начало траектории, М§0.4); знак суммы — OA_fixed + ΔOA_q < 0 хотя бы в одном квартале
    сетки; вес приращения — не число ≥ 0 (№ 24); пути без своей плотности и без плотности постоянной части (№ 8).
    Плотность приращения действует только при пути; без её ключа — плотность постоянной части ω_oaf. Путь читается
    при любом уровне volumes.other_assets_fixed, в том числе нулевом. null — отказ (М§0.1). Ключ веса приращения,
    который стоит в книге, проверяется и без пути: № 24 называет отрицательную плотность приращения отказом книги."""
    dens = c_bget(B, "capital.rwa.density")
    if OAF_CHANGE_DENSITY in dens:
        w = dens[OAF_CHANGE_DENSITY]
        if not _c_plain_number(w) or not 0.0 <= w < math.inf:
            raise ControlInputError(f"capital.rwa.density.{OAF_CHANGE_DENSITY} — не число ≥ 0 (М§4.3, прил. A № 24)")
    if not _c_key_given(B, OAF_CHANGE):
        return None
    traj = _c_trajectory_or_fail(c_bget(B, OAF_CHANGE), OAF_CHANGE)
    if OAF_CHANGE_DENSITY not in dens:
        if dens.get(OAF_DENSITY) is None:
            raise ControlInputError(f"{OAF_CHANGE}: нет ни плотности приращения capital.rwa.density."
                                    f"{OAF_CHANGE_DENSITY}, ни плотности постоянной части capital.rwa.density."
                                    f"{OAF_DENSITY} (прил. A № 8)")
        w = dens[OAF_DENSITY]
        if not _c_plain_number(w) or not 0.0 <= w < math.inf:
            raise ControlInputError(f"capital.rwa.density.{OAF_DENSITY} — не число ≥ 0 (М§4.11)")
    v0 = c_traj_at(traj, *anchor)
    if abs(v0) > ANCHOR_ZERO:
        raise ControlInputError(f"{OAF_CHANGE}: значение в квартале якоря {anchor[0]}Q{anchor[1]} — {v0}, а не ноль "
                                f"(якорное условие М§4.3, прил. A № 24)")
    for k in range(1, q_last + 1):
        y, q = c_qper(anchor, k)
        if oaf + (c_traj_at(traj, y, q) - v0) < 0.0:
            raise ControlInputError(f"{OAF_CHANGE}: постоянная часть прочих активов ниже нуля в {y}Q{q} "
                                    f"(знак суммы М§4.3, прил. A № 24)")
    return {"traj": traj, "v0": v0, "density": float(w), "memo": {}}


def c_oaf_change(ctx: dict, y: int, q: int) -> float:
    """Приращение постоянной части прочих активов к якорю на конец квартала (y, q): ΔOA_q = v(q) − v(якорь) (М§4.3);
    без пути — ноль. Сумма в рублях: не индексируется, с кредитами не растёт, процентов не несёт."""
    path = ctx.get("oaf_path")
    if path is None:
        return 0.0
    memo = path["memo"]
    if (y, q) not in memo:
        memo[(y, q)] = c_traj_at(path["traj"], y, q) - path["v0"]
    return memo[(y, q)]


def c_fixed_growth_rule(B: dict):
    """Доля постоянных в рублях частей, растущая за концом сетки, λ_F (М§7; valuation.terminal.fixed_growth_share):
    число от 0 до 1 включительно; None — ключа нет (соглашение образца). Иначе, и при null, — отказ (прил. A № 25)."""
    if not _c_key_given(B, FIXED_GROWTH):
        return None
    lam = c_bget(B, FIXED_GROWTH)
    if not _c_plain_number(lam) or not 0.0 <= lam <= 1.0:
        raise ControlInputError(f"{FIXED_GROWTH} — не число от 0 до 1 включительно: {lam!r} (М§7, прил. A № 25)")
    return float(lam)


def _c_quarter_word(x) -> bool:
    """Строка квартала ГГГГQn буквально: четыре цифры года, заглавная Q, номер квартала 1…4."""
    if not isinstance(x, str):
        return False
    year, sep, part = x.partition(PART_LETTERS[0])
    return (sep == PART_LETTERS[0] and len(year) == QY and all(ch in "0123456789" for ch in year)
            and part in {str(k) for k in range(1, QY + 1)})


def c_t2_share_rule(B: dict, anchor: tuple):
    """Доля инструментов в RWA своей клетки (М§4.11; ключ capital.n20.t2_share — объект {enabled, from}): номер на сетке
    квартала ключа q_χ (якорь — 0, первый прогнозный — 1), с которого T2 клетки — её доля χ_c на итоговые RWA; None —
    ключа нет или enabled: false (траектория во всех кварталах, прежняя строка).

    Отказы книги (прил. A № 30): не объект или поле сверх {enabled, from}; enabled не булево (и нет enabled); enabled:
    true без from; from — не квартал ГГГГQn или вне [meta.first_period; meta.last_period]. Поле from проверяется при
    любом enabled, когда оно есть; null у ключа и у enabled — отказ (М§0.1: null ≠ «ключа нет»), null у from — отказ
    при enabled: true, а под выключенным выключателем — «нераскрыто», как у любого ключа под ним (М§0.1)."""
    if not _c_key_given(B, T2_SHARE):
        return None
    obj = c_bget(B, T2_SHARE)
    if not isinstance(obj, dict) or not {str(k) for k in obj} <= set(T2_SHARE_FIELDS):
        raise ControlInputError(f"{T2_SHARE}: нужен объект {{enabled, from}} без лишних полей — {obj!r} (М§4.11, "
                                f"прил. A № 30)")
    on = obj.get("enabled")
    if not isinstance(on, bool):
        raise ControlInputError(f"{T2_SHARE}.enabled — не true | false: {on!r} (прил. A № 30)")
    if "from" in obj and (on or obj["from"] is not None):
        frm = obj["from"]
        if not _c_quarter_word(frm):
            raise ControlInputError(f"{T2_SHARE}.from — не квартал ГГГГQn: {frm!r} (прил. A № 30)")
        first, last = c_per_parse(c_bget(B, "meta.first_period")), c_per_parse(c_bget(B, "meta.last_period"))
        if not first <= c_per_parse(frm) <= last:
            raise ControlInputError(f"{T2_SHARE}.from = {frm} вне meta.first_period…meta.last_period "
                                    f"(прил. A № 30: доле нужен квартал q_χ − 1 не раньше якоря)")
    elif on:
        raise ControlInputError(f"{T2_SHARE}: enabled: true без from (прил. A № 30)")
    if not on:
        return None
    return c_qidx(anchor, *c_per_parse(obj["from"]))


def c_t2_at(ctx: dict, y: int, h: int, rwa: float, share) -> float:
    """Дополнительный капитал T2 в K20 квартала (y, h) при итоговых RWA квартала или точки (М§4.11): до квартала ключа
    q_χ и у книги без ключа — значение траектории capital.n20.t2 своим читателем М§0.4; с квартала q_χ — доля клетки
    χ_c (share) на эти RWA. С q_χ T2 идёт за RWA с постоянной долей, какие бы решения квартала (доля прироста,
    дивиденд, взнос) их ни меняли; траектория в этих кварталах не читается."""
    q_chi = ctx.get("t2_from")
    if q_chi is None or c_qidx(ctx["anchor"], y, h) < q_chi:
        return c_traj_at(c_bget(ctx["B"], T2_TRAJ), y, h)
    if share is None:
        raise ControlInputError(f"доля инструментов клетки к кварталу {y}Q{h} не задана: шаг квартала q_χ − 1 её не "
                                f"записал (М§4.11)")
    return share * rwa


def c_t2_share_of(ctx: dict, y: int, h: int, rwa: float) -> float:
    """Доля инструментов клетки χ_c = T2_(q_χ − 1) / RWA_c,(q_χ − 1) (М§4.11): значение траектории в квартале (y, h) =
    q_χ − 1 своим читателем М§0.4 к итоговым RWA клетки на его конце (с дрейфом плотности, валютным индексом и
    множителем режима — тем RWA, на которые делится норматив)."""
    return c_traj_at(c_bget(ctx["B"], T2_TRAJ), y, h) / rwa


def c_t2_start_share(ctx: dict):
    """Доля состояния якоря (М§4.11): при from = first_period (q_χ = 1) — доля якоря T2_0 / RWA_0, одна у всех клеток
    (RWA якоря без множителя режима, М§4.11); иначе долю задаст шаг квартала q_χ − 1 — None."""
    if ctx.get("t2_from") != 1:
        return None
    return c_t2_share_of(ctx, *ctx["anchor"], ctx["rwa0"])


def c_t2_share_step(ctx: dict, st: dict, p: dict, rwa_end: float, plan: dict | None = None):
    """Доля инструментов клетки после записанного годового шага периода p (М§4.11, §17): доля состояния, если она
    уже задана (без ключа — None); иначе, когда квартал q_χ − 1 лежит в периоде, — значение траектории в нём к RWA
    клетки на его конце: у последнего квартала периода — RWA конца периода, у иного — квартальный профиль RWA
    (геометрически между началом и концом периода, как RWA точек проверки дивиденда и окна решения о взносе), а у ветви
    с квартальным проходом — RWA этого квартала своего прохода (её несёт план года, plan["t2s"]). Каждый шаг —
    пробный и окончательный — задаёт долю своими RWA. Шаг, который кончается раньше q_χ − 1, долю не задаёт."""
    q_chi = ctx.get("t2_from")
    if q_chi is None:
        return None
    if st.get("t2s") is not None:
        return st["t2s"]
    y, qs, n = p["year"], p["quarters"], p["n"]
    j = q_chi - 1 - c_qidx(ctx["anchor"], y, qs[0])
    if not 0 <= j < n:
        return None
    if plan is not None and plan.get("t2s") is not None:
        return plan["t2s"]
    if j == n - 1:
        return c_t2_share_of(ctx, y, qs[j], rwa_end)
    rwa_start = st["rwa"]
    return c_t2_share_of(ctx, y, qs[j], rwa_start * (rwa_end / rwa_start) ** ((j + 1) / n))


# ---------------------------------------------------------------------------- восьмой проход (М§4.4, §4.9–§4.11, §7)

def _c_base_word_or_number(x) -> bool:
    """База ключа восьмого прохода (прил. A № 31, № 32): слово anchor или число не меньше нуля (млрд ₽)."""
    return x == BASE_ANCHOR or (_c_plain_number(x) and math.isfinite(x) and x >= 0.0)


def _c_switch_object(B: dict, key: str, fields: tuple, rule_no: str) -> dict:
    """Объект с выключателем (М§0.1): не объект или поле сверх fields, нет enabled или enabled не булево — отказ; при
    enabled: true каждое поле обязано стоять и не быть null (null под включённым выключателем — отказ, под
    выключенным — «нераскрыто»). Формат полей проверяет вызывающий — при любом enabled, когда поле есть."""
    obj = c_bget(B, key)
    if not isinstance(obj, dict) or not {str(k) for k in obj} <= set(fields):
        raise ControlInputError(f"{key}: нужен объект {{{', '.join(fields)}}} без лишних полей — {obj!r} (прил. A № {rule_no})")
    on = obj.get("enabled")
    if not isinstance(on, bool):
        raise ControlInputError(f"{key}.enabled — не true | false: {on!r} (прил. A № {rule_no})")
    if on:
        for name in fields[1:]:
            if obj.get(name) is None:
                raise ControlInputError(f"{key}: enabled: true без {name} (прил. A № {rule_no}; null — нераскрыто, М§0.1)")
    for name in fields[1:]:
        val = obj.get(name)
        if val is None:
            continue
        if name == "spread" and not (_c_plain_number(val) and math.isfinite(val)):
            raise ControlInputError(f"{key}.spread — не число: {val!r} (прил. A № {rule_no})")
        if name == "base" and not _c_base_word_or_number(val):
            raise ControlInputError(f"{key}.base — не число ≥ 0 и не {BASE_ANCHOR}: {val!r} (прил. A № {rule_no})")
    return obj


def c_at1_share_rule(B: dict, anchor: tuple, at1_0: float):
    """Доля добавочного капитала в RWA своей клетки (М§4.11; ключ capital.at1_share — объект {enabled, from, spread,
    base}): {from — номер квартала ключа q_α на сетке (якорь — 0), spread — s_α, надбавка купона новых выпусков к
    ключевой ставке мира, base — B_α, сумма, которую несёт купон якоря: число или факт якоря AT1_0 при слове anchor};
    None — ключа нет или enabled: false (добавочный капитал — факт якоря во всех кварталах, купон — купон якоря).

    Отказы книги (прил. A № 31): не объект или лишнее поле; нет enabled или не булево; enabled: true без любого из трёх
    полей (null — тоже); при любом enabled, когда поле есть: from — не квартал ГГГГQn или вне [meta.first_period;
    meta.last_period], spread — не число, base — не число и не anchor или число меньше нуля."""
    if not _c_key_given(B, AT1_SHARE):
        return None
    obj = _c_switch_object(B, AT1_SHARE, AT1_SHARE_FIELDS, "31")
    frm = obj.get("from")
    if frm is not None:
        if not _c_quarter_word(frm):
            raise ControlInputError(f"{AT1_SHARE}.from — не квартал ГГГГQn: {frm!r} (прил. A № 31)")
        first, last = c_per_parse(c_bget(B, "meta.first_period")), c_per_parse(c_bget(B, "meta.last_period"))
        if not first <= c_per_parse(frm) <= last:
            raise ControlInputError(f"{AT1_SHARE}.from = {frm} вне meta.first_period…meta.last_period (прил. A № 31)")
    if not obj["enabled"]:
        return None
    base = obj["base"]
    return {"from": c_qidx(anchor, *c_per_parse(frm)), "spread": float(obj["spread"]),
            "base": float(at1_0) if base == BASE_ANCHOR else float(base)}


def c_t2_premium_rule(B: dict, anchor: tuple):
    """Надбавка за субординацию дополнительного капитала (М§4.4, §4.11; ключ capital.n20.t2_premium — объект {enabled,
    spread, base}): {spread — π_T2, надбавка к ставке опта, base — B_T2: число или при слове anchor значение траектории
    capital.n20.t2 в квартале якоря T2_0}; None — ключа нет или enabled: false. Отказы книги (прил. A № 32): не объект
    или лишнее поле; нет enabled или не булево; enabled: true без spread или base; при любом enabled, когда поле есть:
    spread не число, base не число и не anchor или число меньше нуля. spread: 0 — ключ включён, надбавка — ноль."""
    if not _c_key_given(B, T2_PREMIUM):
        return None
    obj = _c_switch_object(B, T2_PREMIUM, T2_PREMIUM_FIELDS, "32")
    if not obj["enabled"]:
        return None
    base = obj["base"]
    return {"spread": float(obj["spread"]),
            "base": c_traj_at(c_bget(B, T2_TRAJ), *anchor) if base == BASE_ANCHOR else float(base)}


def c_om_terminal_rule(B: dict, last_year: int):
    """Прочие движения капитала за концом сетки (М§7; ключ valuation.terminal.other_movements ∈ {none, flat_rub}):
    {kind, om_lt — значение траектории equity.other_movements в году L + 1 своим читателем М§0.4 (значение года: при LT —
    LT, без LT — значение последнего заданного года, у скаляра — само число), om_ann = 4 × om_lt}; None — ключа нет или
    none (соглашение образца: ноль). Отказы книги (прил. A № 33): значение не из перечня; при flat_rub траектория не
    читается в году L + 1 (без заданных лет и без LT)."""
    if not _c_key_given(B, OM_TERMINAL):
        return None
    kind = c_bget(B, OM_TERMINAL)
    if not isinstance(kind, str) or kind not in OM_KINDS:
        raise ControlInputError(f"{OM_TERMINAL}: {kind!r} — не из {list(OM_KINDS)} (прил. A № 33)")
    if kind == OM_KINDS[0]:
        return None
    try:
        om_lt = c_traj_year(c_bget(B, OM_TRAJ), last_year + 1)
    except ControlInputError as exc:
        raise ControlInputError(f"{OM_TERMINAL}: {OM_TRAJ} не читается в году {last_year + 1} — {exc} (прил. A № 33)")
    return {"kind": kind, "om_lt": om_lt, "om_ann": QY * om_lt}


def c_at1_at(ctx: dict, y: int, h: int, rwa: float, share) -> float:
    """Добавочный капитал в K20 квартала (y, h) при итоговых RWA квартала или точки (М§4.11): до квартала ключа q_α и у
    книги без ключа — факт якоря AT1_0; с q_α — доля клетки α_c (share) на эти RWA."""
    rule = ctx.get("at1")
    if rule is None or c_qidx(ctx["anchor"], y, h) < rule["from"]:
        return ctx["A"]["AT1"]
    if share is None:
        raise ControlInputError(f"доля добавочного капитала клетки к кварталу {y}Q{h} не задана: шаг квартала q_α − 1 её "
                                f"не записал (М§4.11)")
    return share * rwa


def c_at1_share_of(ctx: dict, rwa: float) -> float:
    """Доля добавочного капитала клетки α_c = AT1_c,(q_α − 1) / RWA_c,(q_α − 1) = AT1_0 / RWA_c,(q_α − 1) (М§4.11): до
    квартала ключа клетка держит факт якоря; RWA — итоговые RWA клетки на конце квартала q_α − 1."""
    return ctx["A"]["AT1"] / rwa


def c_at1_start_share(ctx: dict):
    """Доля состояния якоря: при from = first_period (q_α = 1) — доля якоря AT1_0 / RWA_0, одна у всех клеток (RWA якоря
    без множителя режима); иначе долю задаст шаг квартала q_α − 1 — None."""
    rule = ctx.get("at1")
    if rule is None or rule["from"] != 1:
        return None
    return c_at1_share_of(ctx, ctx["rwa0"])


def c_at1_fixed_point(g: float, b: float, la_free: float, la_min: float, alpha: float, where: str = "") -> dict:
    """RWA квартала выпуска добавочного капитала — неподвижная точка (М§4.10):

        RWA = G + b × max(LA_free + α × RWA, LA_min),   AT1 = α × RWA

    G — RWA без балансирующих активов, b — RWA на рубль балансирующих активов, LA_free — балансирующие активы
    окончательного баланса без добавочного капитала (LA_x,q − AT1_(q−1) текста) до добора опта, LA_min — минимум
    ликвидности в рублях. Закрытая форма: ветвь A — R_A = (G + b × LA_free) / (1 − b × α), если LA_free + α × R_A ≥
    LA_min; иначе ветвь B — RWA = G + b × LA_min (выпуск гасит добор опта). Наклон правой части по RWA — не больше b × α;
    b × α ≥ 1 — отказ: решение не единственно, книга несогласована. Возвращает {rwa, at1, la — балансирующие активы с
    добавочным капиталом после добора, extra — добор опта, branch}."""
    if b * alpha >= 1.0:
        raise ControlInputError(f"{where}: b × α = {b * alpha} ≥ 1 — уравнение RWA квартала выпуска добавочного капитала "
                                f"не имеет единственного решения (М§4.10, прил. A № 31)")
    r_a = (g + b * la_free) / (1.0 - b * alpha)
    if la_free + alpha * r_a >= la_min:
        rwa, branch = r_a, "A"
    else:
        rwa, branch = g + b * la_min, "B"
    at1 = alpha * rwa
    la = la_free + at1
    return {"rwa": rwa, "at1": at1, "la": max(la, la_min), "extra": max(0.0, la_min - la), "branch": branch}


def c_at1_coupon_new(rate: float, at1_prev: float, base: float, days: float) -> float:
    """Купон сверх базы квартала (М§4.9): c_α,q × (AT1_c,(q−1) − B_α) × d_q / 365, c_α,q = key_W,q + s_α — до налога;
    знак любой (AT1 ниже базы — экономия по ставке новых выпусков)."""
    return rate * (at1_prev - base) * days / DAYS_BASE


def c_t2_premium_q(spread: float, t2_prev: float, base: float, days: float) -> float:
    """Надбавка за субординацию дополнительного капитала квартала (М§4.4): SP_q = π_T2 × (T2_c,(q−1) − B_T2) × d_q / 365 —
    процентный расход сверх ставки опта, до налога; знак любой."""
    return spread * (t2_prev - base) * days / DAYS_BASE


# ---------------------------------------------------------------------------- девятый проход (М§4.8, §4.9, §7)

def _c_finite(x) -> bool:
    return _c_plain_number(x) and math.isfinite(x)


def _c_gap_path_refused(B: dict) -> None:
    """При включённом ключе tax.structure число разрыва tax.effective_gap не читается (прил. A № 34): ось полосы на этом
    пути (valuation.uncertainty.axes и off_band_axes — путь в paths) молча дала бы ноль — отказ; подмена справочного
    варианта на нём (valuation.reference_variants — путь в overrides) — отказ, если тот же вариант не ставит
    tax.structure.enabled: false (путём ключа выключателя или объектом ключа)."""
    for where in AXES_LISTS:
        for ax in c_bopt(B, where) or []:
            paths = [str(x) for x in ((ax.get("paths") if isinstance(ax, dict) else None) or [])]
            if any(x == TAX_GAP or x.startswith(TAX_GAP + ".") for x in paths):
                name = ax.get("name") if isinstance(ax, dict) else ax
                raise ControlInputError(f"{TAX_STRUCTURE}: ось {name!r} ({where}) на {TAX_GAP} при включённом ключе — путь "
                                        f"не читается (прил. A № 34; ось — на {TAX_STRUCTURE}.other_pp, М§10 правило 11)")
    for var in c_bopt(B, VARIANTS_LIST) or []:
        over = (var.get("overrides") if isinstance(var, dict) else None) or {}
        if not any(str(k) == TAX_GAP or str(k).startswith(TAX_GAP + ".") for k in over):
            continue
        whole = over.get(TAX_STRUCTURE)
        off = over.get(f"{TAX_STRUCTURE}.enabled") is False or (isinstance(whole, dict) and whole.get("enabled") is False)
        if not off:
            raise ControlInputError(f"{TAX_STRUCTURE}: справочный вариант {var.get('id')!r} подменяет {TAX_GAP} при включённом "
                                    f"ключе без {TAX_STRUCTURE}.enabled: false в той же подмене (прил. A № 34)")


def c_tax_structure_rule(B: dict):
    """Разрыв налога по правилу (М§4.8; ключ tax.structure — объект {enabled, bond_rate, bond_scale, other_pp,
    coupon_deductible}): {bond_rate — τ_b, ставка налога на процентный доход по облигациям, bond_scale — ζ, облагаемый по τ_b
    доход на рубль процентного дохода книги бумаг клетки, other_pp — o, прочие постоянные разницы долей прибыли до налога,
    deductible — δ_c, вычитается ли купон бессрочных из налоговой базы}; None — ключа нет или enabled: false (налог —
    законная ставка плюс число разрыва tax.effective_gap, строка образца).

    Отказы книги (прил. A № 34): не объект или лишнее поле; нет enabled или не булево; enabled: true без любого из четырёх
    полей (null — тоже); при любом enabled, когда поле есть: bond_rate и other_pp — не числа, bond_scale — не число или
    меньше нуля, coupon_deductible — не булево; при enabled: true — ось или подмена справочного варианта на
    tax.effective_gap без tax.structure.enabled: false в том же варианте. Число разрыва при включённом ключе может быть
    null: его никто не читает."""
    if not _c_key_given(B, TAX_STRUCTURE):
        return None
    obj = _c_switch_object(B, TAX_STRUCTURE, TAX_STRUCTURE_FIELDS, "34")
    for name in ("bond_rate", "other_pp"):
        val = obj.get(name)
        if val is not None and not _c_finite(val):
            raise ControlInputError(f"{TAX_STRUCTURE}.{name} — не число: {val!r} (прил. A № 34)")
    val = obj.get("bond_scale")
    if val is not None and not (_c_finite(val) and val >= 0.0):
        raise ControlInputError(f"{TAX_STRUCTURE}.bond_scale — не число ≥ 0: {val!r} (прил. A № 34)")
    val = obj.get("coupon_deductible")
    if val is not None and not isinstance(val, bool):
        raise ControlInputError(f"{TAX_STRUCTURE}.coupon_deductible — не true | false: {val!r} (прил. A № 34)")
    if not obj["enabled"]:
        return None
    _c_gap_path_refused(B)
    return {"bond_rate": float(obj["bond_rate"]), "bond_scale": float(obj["bond_scale"]),
            "other_pp": float(obj["other_pp"]), "deductible": bool(obj["coupon_deductible"])}


def c_at1_coupon_rule(B: dict):
    """Купон добавочного капитала якоря по ставке своего мира (М§4.9; ключ capital.at1_coupon — объект {enabled, fixed,
    floating, spread}): {fixed — Cfix, годовой купон выпусков с постоянной ставкой, floating — Cflt, сумма плавающих
    выпусков, spread — s_flt, их взвешенный спред к ключевой}; None — ключа нет или enabled: false (купон якоря — слот
    фактов at1.coupon_annual). Семантика — денежный купон, как у слота. Отказы книги (прил. A № 35): не объект или лишнее
    поле; нет enabled или не булево; enabled: true без любого из трёх полей; при любом enabled, когда поле есть: fixed и
    floating — не числа или меньше нуля, spread — не число."""
    if not _c_key_given(B, AT1_COUPON):
        return None
    obj = _c_switch_object(B, AT1_COUPON, AT1_COUPON_FIELDS, "35")
    for name in ("fixed", "floating"):
        val = obj.get(name)
        if val is not None and not (_c_finite(val) and val >= 0.0):
            raise ControlInputError(f"{AT1_COUPON}.{name} — не число ≥ 0: {val!r} (прил. A № 35)")
    if not obj["enabled"]:
        return None
    return {"fixed": float(obj["fixed"]), "floating": float(obj["floating"]), "spread": float(obj["spread"])}


def c_at1_coupon_formula(rule: dict, rate: float) -> float:
    """Годовой купон якоря по составу выпусков (М§4.9): Cfix + Cflt × (ставка + s_flt); ставка — средняя ключевая периода
    купона (k̄) или, за T, ключевая последнего квартала сетки."""
    return rule["fixed"] + rule["floating"] * (rate + rule["spread"])


def c_key_of_quarter(ctx: dict, world: str, k: int) -> float:
    """Ключевая мира world в квартале сетки k (своим читателем траекторий); кварталы не позже якоря (k ≤ 0) — ключевая
    квартала якоря key_W,0 (М§4.9)."""
    return c_world_quarter(ctx["B"], world, "key_rate", *c_qper(ctx["anchor"], max(k, 0)))


def c_coupon_kbar(ctx: dict, world: str, y: int, q: int) -> float:
    """k̄ квартала купона (y, q) (М§4.9): средняя ключевая своего мира за четыре квартала, которые кончаются кварталом
    купона; кварталы не позже якоря — ключевая квартала якоря."""
    k = c_qidx(ctx["anchor"], y, q)
    return sum(c_key_of_quarter(ctx, world, k - j) for j in range(QY)) / QY


def c_anchor_coupon(ctx: dict, world, y: int, q: int) -> float:
    """Купон якоря CPN^A квартала (y, q) (М§4.9): в квартале купона h_c (at1.coupon_quarter) — слот фактов CPN_ann, у книги
    с ключом capital.at1_coupon — Cfix + Cflt × (k̄ + s_flt) по пути ключевой мира world (кварталы не позже якоря —
    ключевая квартала якоря, и у кварталов купона не позже якоря тоже); в остальных кварталах — ноль."""
    A = ctx["A"]
    if q != A["cpn_quarter"]:
        return 0.0
    rule = ctx.get("at1c")
    if rule is None:
        return A["cpn_annual"]
    return c_at1_coupon_formula(rule, c_coupon_kbar(ctx, world, y, q))


def c_anchor_coupon_t1(ctx: dict, world: str) -> float:
    """Купон якоря года T + 1 (М§7, §4.9): слот фактов, у книги с ключом capital.at1_coupon — Cfix + Cflt × (key_W,Q + s_flt),
    ключевая последнего квартала сетки, а не средняя года L."""
    rule = ctx.get("at1c")
    if rule is None:
        return ctx["A"]["cpn_annual"]
    return c_at1_coupon_formula(rule, ctx["wv"][world][-1]["key_rate"][-1])


def c_tax_coupon(rule: dict, tau_stat: float, coupon: float) -> float:
    """Налоговая экономия купона бессрочных TS = δ_c × τ_stat × CPN (М§4.8; ряд tax_coupon)."""
    return tau_stat * coupon if rule["deductible"] else 0.0


def c_tax_rule(rule: dict, tau_stat: float, pbt: float, iis: float, saving: float) -> float:
    """Налог по правилу в рублях (М§4.8): τ_stat × PBT + o × max(PBT, 0) − (τ_stat − τ_b) × ζ × IIS − TS. При убытке прочих
    разниц нет, льгота облигаций и экономия купона остаются рублями: налог непрерывен в нуле (излом, не скачок)."""
    return (tau_stat * pbt + rule["other_pp"] * max(pbt, 0.0)
            - (tau_stat - rule["bond_rate"]) * rule["bond_scale"] * iis - saving)


def c_tax_marginal(rule: dict, tau_stat: float, pbt: float) -> float:
    """Ряд tau_eff у книги с ключом (М§4.8): маржинальная ставка τ_stat + o × [PBT > 0]."""
    return tau_stat + (rule["other_pp"] if pbt > 0.0 else 0.0)


def c_terminal_y_after_tax(rule: dict, tau: float, wt: float, c_wh: float, sec: float, y_sec: float,
                           y_liq: float) -> float:
    """Ставка балансирующих статей после налога y^τ_m (М§7, блок постоянных частей у книги с ключом tax.structure): при
    доборе опта на конце сетки — c_wholesale,Q × (1 − τ − o), иначе бумаги — по своей ставке с льготой
    sec × y_sec × (1 − τ − o + (τ − τ_b) × ζ), ликвидность — (1 − sec) × y_liq × (1 − τ − o)."""
    keep = 1.0 - tau - rule["other_pp"]
    if wt > 0.0:
        return c_wh * keep
    return (sec * y_sec * (keep + (tau - rule["bond_rate"]) * rule["bond_scale"])
            + (1.0 - sec) * y_liq * keep)


def c_rwa_parts(ctx: dict, r, y: int, h: int, E: dict, OA: float, dn: float, xf: float) -> tuple[float, float]:
    """RWA конца квартала как аффинная функция балансирующих активов (М§4.10): G — RWA без бумаг и ликвидности, b — RWA
    на рубль балансирующих активов в их долях (securities_share_of_liquid) — той же функцией RWA, что у баланса. Наклон
    берётся по пробе размером с G (а не по рублю): разность двух близких больших чисел на рубле теряла бы точность."""
    ssl = c_bnum(ctx["B"], "volumes.securities_share_of_liquid")
    g = _c_rwa_of(ctx, r, y, h, {**E, SECURITIES: 0.0, LIQUIDITY: 0.0}, OA, dn, xf)
    probe = max(1.0, abs(g))
    full = _c_rwa_of(ctx, r, y, h, {**E, SECURITIES: ssl * probe, LIQUIDITY: (1.0 - ssl) * probe}, OA, dn, xf)
    return g, (full - g) / probe


def _c_capital(ctx: dict, s: str, y: int, h: int, bv: float, dpreg: float, R: float, rwa: float,
             ni_q: dict, t2s=None, at1=None) -> dict:
    """K20, K11, Н20.0 и второй норматив (слот n11: отчётный и с прибылью периода), требования и полы в
    квартале (y, h) (М§4.11–§4.12); вычеты Ded20 и Ded11 — c_deductions при RWA этого квартала, у книги с вычетом
    сценария в рублях — плюс рубли сценария s квартала, без множителя RWA (до деления на RWA). Инструменты T2 —
    c_t2_at: у книги с ключом доли инструментов с квартала ключа — доля клетки t2s на RWA точки (только в K20).
    Добавочный капитал at1 — AT1 точки (у книги с ключом доли добавочного капитала с квартала ключа — α_c × RWA точки,
    c_at1_at; без аргумента — факт якоря AT1_0), только в K20."""
    B = ctx["B"]
    f = c_bnum(B, "capital.n20.fvoci_recognition")
    bvreg = bv + dpreg - (1.0 - f) * R
    ded20, ded11 = c_deductions(ctx, rwa)
    if ctx.get("rub") is not None:
        rub20, rub11 = c_rub_at(ctx, s, y, h)
        ded20, ded11 = ded20 + rub20, ded11 + rub11
    t2 = c_t2_at(ctx, y, h, rwa, t2s)
    at1 = ctx["A"]["AT1"] if at1 is None else at1
    k20 = bvreg - ded20 + at1 + t2
    cut = [int(c) for c in c_bget(B, "capital.n11.audit_cutoffs")]
    e_q = _c_unaudited_quarters(cut, y, h)
    missing = [yq for yq in e_q if yq not in ni_q]
    if missing:
        raise ControlInputError(f"нет прибыли кварталов {missing} для E_q")
    e_un = sum(ni_q[yq] for yq in e_q)
    # из базового капитала исключается только прибыль неаудированного периода; убыток — уже в BV (М§4.11)
    e_out = e_un if e_un > 0.0 else 0.0
    k11 = bvreg - e_out - ded11
    dp20 = c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n20_0"), y, h)
    dp11 = c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n1_1"), y, h)
    n20 = k20 / rwa + c_bnum(B, "capital.n20.gap_pp") - dp20
    n11 = k11 / rwa + c_bnum(B, "capital.n11.gap_pp") - dp11
    n11_star = (k11 + e_out) / rwa + c_bnum(B, "capital.n11.gap_pp") - dp11
    fl20, fl11 = _c_floor(B, s, "n20_0", y, h), _c_floor(B, s, "n1_1", y, h)
    return {"k20": k20, "k11": k11, "n20": n20, "n11": n11, "n11_star": n11_star, "e_unaudited": e_un,
            "ded20": ded20, "ded11": ded11, "t2": t2, "at1": at1, "floor20": fl20, "floor11": fl11,
            "req20": max(c_bnum(B, "dividends.policy.threshold"), fl20 + c_bnum(B, "capital.mgmt_buffer.n20_0")),
            "req11": fl11 + c_bnum(B, "capital.mgmt_buffer.n1_1")}


def _c_start_state(ctx: dict) -> dict:
    A, B = ctx["A"], ctx["B"]
    tenor = c_bget(B, "oci.fvoci_tenor")
    node = tenor.split("_")[1].rstrip("y")
    ni_q = {}
    for per, rec in A["pnl"].items():
        if rec.get("ni_shareholders") is not None:
            ni_q[c_per_parse(per)] = float(rec["ni_shareholders"])
    fr = A["E0"][RETAIL_CURRENT] + A["E0"][RETAIL_TERM]
    # дивиденд, объявленный до даты фактов, уже вычтен из BV якоря; сумма к выплате — факт баланса,
    # кварталы выплаты и вычета — по записи реестра за этот год прибыли (ГОСА — в году якоря, не позже
    # якоря: иначе контекст отказал бы), иначе по календарю (М§5.4)
    start = {"E": dict(A["E0"]), "y": dict(A["rate0"]), "c": A["E0"][RETAIL_CURRENT] / fr,
             "BV": A["BV"], "R": A["R0"], "Dn": 1.0, "fxp": 1.0, "I": 1.0,
             "y_tenor": A["curve0"][node], "D": 0.0, "ni_q": ni_q, "qv": {}}
    if ctx.get("t2_from") is not None:
        start["t2s"] = c_t2_start_share(ctx)        # доля инструментов клетки (М§4.11): при q_χ = 1 — доля якоря
    if ctx.get("at1") is not None:
        # добавочный капитал клетки (М§4.11): на якоре — факт; доля — при q_α = 1 доля якоря, иначе её задаст шаг
        # квартала q_α − 1; купон сверх базы кварталов после налога — для базы дивиденда (М§5.2, §5.7.3)
        start.update(at1=A["AT1"], a1s=c_at1_start_share(ctx), cpn_q={})
    if ctx["quarterly"]:
        # состояние якоря квартального режима (М§5.7.4): объявленная часть остатка — в очередях выплат и
        # вычетов, остаток — постоянное обязательство; уровни потенциального пути — остатки якоря (М§4.13.1)
        cal = ctx["divcal"]
        start.update(pay=[], dq=[dict(it) for it in cal["queue0"]], dp_perm=cal["perm"],
                     Epot={b: A["E0"][b] for b in ctx["loans"]})
        return start
    profit_year = ctx["anchor"][0] - 1 if A["DP_year"] is None else int(A["DP_year"])
    start["pay"] = [{"amt": A["DP"], **_c_dividend_dates(ctx, profit_year)}] if A["DP"] else []
    return start


# ============================================================================ дивиденды (М§5) в годовом шаге

REGISTER_BINDING = ("declared", "paid")   # объявленное — обязательство; `recommended` — только плашка (М§15.1)


def _c_register_binding(ctx: dict) -> list[dict]:
    """Записи реестра с объявленным дивидендом (решение ГОСА принято: declared или уже paid)."""
    return [rec for rec in ctx["A"]["register"] if rec.get("status", "declared") in REGISTER_BINDING]


def _c_register_rec(ctx: dict, year: int):
    for rec in _c_register_binding(ctx):
        if int(_c_nodeval(rec.get("year"))) == year:
            return rec
    return None


def _c_register_dps(ctx: dict, year: int):
    rec = _c_register_rec(ctx, year)
    return None if rec is None else float(_c_nodeval(rec["dps"]))


def _c_dividend_dates(ctx: dict, profit_year: int) -> dict:
    """Кварталы выплаты и вычета из регуляторного капитала дивиденда за год прибыли (М§5.4): у
    объявленной записи реестра (declared | paid) даты записи сильнее календаря книги — выплата в
    квартале pay_date, вычет в квартале отсечки record_date; нет записи или даты — None (календарь)."""
    out = {"agm_year": profit_year + 1, "pay": None, "reg": None}
    rec = _c_register_rec(ctx, profit_year)
    if rec is None:
        return out
    for key, field in (("pay", "pay_date"), ("reg", "record_date")):
        val = _c_nodeval(rec.get(field))
        if val:
            d = _c_as_date(val)
            out[key] = (d.year, (d.month - 1) // 3 + 1)
    return out


def _c_decide(ctx: dict, cell: dict, st: dict, i: int, rec: float = 0.0) -> tuple[float, dict]:
    """Решение года прибыли Y = год периода − 1: пробный проход, запас H, ступени, кризис, реестр.

    rec — взнос акционеров, уже принятый в этом году до квартала собрания (книга с ключом квартала решения о
    взносе раньше собрания, М§4.14.1): его деньги стоят в капитале пробного прохода с конца своего квартала —
    собрание решает о дивиденде уже с ними. Взнос квартала собрания и более поздних кварталов пробный проход
    дивиденда не несёт: дивиденд — остаток над требованием без расчёта на будущий взнос (М§5.3 п. 7)."""
    B, A, p = ctx["B"], ctx["A"], ctx["periods"][i]
    yp = p["year"] - 1
    info = {"profit_year": yp}
    n_out, n_iss = A["N_out"], A["N_iss"]
    reg = _c_register_dps(ctx, yp)
    if reg is not None:
        info.update(kind="register", dps_register=reg)
        return reg * n_out / 1000.0, info
    if any((yp, q) not in st["ni_q"] for q in range(1, QY + 1)):
        raise ControlInputError(f"нет прибыли акционеров всех кварталов {yp} года для базы дивиденда (М§5.2)")
    ni_y = sum(v for (yy, _), v in st["ni_q"].items() if yy == yp)
    # купон якоря года прибыли (М§5.2): слот, у книги с ключом capital.at1_coupon — его формула по ключевой мира клетки
    # (квартал купона не позже якоря — с ключевой квартала якоря); после налога по τ_cpn — у книги с ключом
    # tax.structure купон целиком: экономия уже в NI_sh (М§4.8)
    tau_c = c_traj_at(c_bget(B, "tax.statutory"), yp, A["cpn_quarter"]) if ctx.get("tax") is None else 0.0
    base = ni_y - (c_anchor_coupon(ctx, cell["world"], yp, A["cpn_quarter"]) * (1.0 - tau_c)
                   if c_bget(B, "dividends.policy.deduct_at1_after_tax") else 0.0)
    if ctx.get("at1") is not None and c_bget(B, "dividends.policy.deduct_at1_after_tax"):
        # CPN_Y — купон якоря и купон сверх базы кварталов года прибыли, после налога (М§5.2; у кварталов не позже
        # якоря — ноль)
        base = base - sum(v for (yy, _), v in st["cpn_q"].items() if yy == yp)
    dev = c_traj_year(c_bget(B, "dividends.payout_deviation"), yp)
    steps = c_bget(B, "dividends.policy.steps") or [
        {"payout": c_traj_year(c_bget(B, "dividends.policy.payout"), yp),
         "threshold": c_bnum(B, "dividends.policy.threshold")}]
    trial = _c_period(ctx, cell, st, i, 0.0)[1] if not rec else _c_period(ctx, cell, st, i, 0.0, rec=rec)[1]
    cps = [int(c) for c in c_bget(B, "dividends.calendar.checkpoints")]
    y = p["year"]
    s = cell["scenario"]
    buf20 = c_bnum(B, "capital.mgmt_buffer.n20_0")
    hs = []
    for j, stp in enumerate(steps):
        # доля ступени — число или траектория по году прибыли, как policy.payout (М§5.1)
        share = (c_traj_year(stp["payout"], yp) if isinstance(stp["payout"], dict)
                 else float(stp["payout"]))
        pj = min(1.0, max(0.0, share + dev))
        want = pj * max(0.0, base) * n_out / n_iss
        H = float("inf")
        for h in cps:
            # состояние в точке проверки h года y пробного прохода: капитал — BV начала года + CI
            # кварталов по h (квартальный профиль периода), фонд FVOCI — квартальная рекурсия, RWA —
            # геометрически между началом и концом года
            if h not in p["quarters"]:
                raise ControlInputError(f"точка проверки {h} вне кварталов периода {p['label']} (М§5.3)")
            j_h = p["quarters"].index(h)
            bv_h = st["BV"] + sum(trial["ci_q"][:j_h + 1])
            if rec:
                bv_h = bv_h + sum(amt for jj, amt in trial["rec_list"] if jj <= j_h)
            r_h = trial["R_q"][j_h]
            rwa_h = st["rwa"] * (trial["rwa"] / st["rwa"]) ** ((j_h + 1) / p["n"])
            ni_q = {**st["ni_q"], **trial["ni_q"]}
            # инструменты точки (М§4.11): с квартала ключа — доля клетки пробного прохода на RWA точки; добавочный
            # капитал — так же своей долей
            cap = _c_capital(ctx, s, y, h, bv_h, 0.0, r_h, rwa_h, ni_q, trial.get("t2s"),
                             c_at1_at(ctx, y, h, rwa_h, trial.get("a1s")))
            req20 = max(float(stp["threshold"]), cap["floor20"] + buf20)
            H = min(H, (cap["n20"] - req20) * rwa_h, (cap["n11"] - cap["req11"]) * rwa_h)
        hs.append((want, H))
    # ступень — первая, чей запас не меньше желаемой выплаты (М§5.3 п. 3); запасы и желаемые выплаты считаются у
    # всех ступеней: их читает правило строки «ступень политики у порога» сверки (М§17), на решение они не влияют
    step = next((j for j, (want, H) in enumerate(hs) if H >= want), None)
    if step is not None:
        want, H = hs[step]
        base_div, H_used = want, H
    else:
        want, H = hs[-1]
        base_div, H_used, step = max(0.0, min(want, H)), H, len(steps) - 1
    want1 = hs[0][0]
    info.update(kind="policy", base=base, want=want1, H=H_used, step=step, base_div=base_div,
                wants=[w for w, _ in hs], headrooms=[h for _, h in hs])
    if (cell["regime"] == R_CRISIS and y == ctx["shock_year"]
            and c_bget(B, "dividends.crisis.skip_in_shock_year")):
        st["D"] += want1
        info.update(kind="crisis_skip")
        return 0.0, info
    catch = min(st["D"], max(0.0, H_used - base_div)) if c_bget(B, "dividends.crisis.catch_up") else 0.0
    eps = 0.0
    fy = int(c_bnum(B, "dividends.excess.from_profit_year"))
    if yp >= fy:
        # линейный ввод ε за ramp_years лет (М§5.3 п. 4): ε_Y = ε × min(1, (Y − from + 1)/ramp)
        ramp = int(c_bnum(B, "dividends.excess.ramp_years"))
        if ramp < 1:
            raise ControlInputError("dividends.excess.ramp_years — целое ≥ 1 (М прил. A)")
        eps = c_bnum(B, "dividends.excess.epsilon") * min(1.0, (yp - fy + 1) / ramp)
    exc = eps * max(0.0, H_used - base_div - catch)
    st["D"] -= catch
    info.update(catch=catch, excess=exc, eps=eps)
    return base_div + catch + exc, info


# ============================================================================ докапитализация (М§4.14) в годовом шаге

def c_recap_shortfall(points: list[dict], least: float, closing: bool = True) -> dict:
    """Недостаток окна и взнос решения (М§4.14.1, шаги 3–4) по точкам пробного прохода.

    Точка — {q, n20, n11, dpreg, rwa, req20, req11}: отчётные нормативы, дивиденды, объявленные, но ещё не
    вычтенные из регуляторного капитала, RWA и требования М§4.12 на конец квартала q. Точки идут в порядке окна;
    последняя — конец окна: только в ней норматив берётся без такого дивиденда (после окна вычет никто не
    проверит). Недостаток точки — больший из двух нормативов, недостаток окна S — наибольший по точкам как есть.
    Точка и норматив наибольшего недостатка — одним правилом «при равенстве», буквально: точка — самая ранняя
    точка окна, у которой недостаток не ниже S − 1e-9; норматив — Н20.0, если в этой точке его недостаток не
    ниже недостатка Н20.1 минус 1e-9, иначе Н20.1. Точка сравнивается с наибольшим недостатком окна, а не с
    текущим лучшим при обходе: при трёх близких недостатках обход «заменять, если больше на 1e-9» назвал бы
    другую точку. 1e-9 млрд ₽ — точность счёта: недостаток — разность двух близких долей, умноженная на RWA, и
    равные по формуле недостатки расходятся в последних знаках; допуск выбирает только, какую точку и какой
    норматив назвать, на взнос он не влияет. Взнос равен недостатку, если тот больше порога, иначе нулю; не
    округляется и между годами не сглаживается. closing: False — список кончается раньше конца окна (точки
    инварианта «взнос закрывает разрыв» идут только до квартала нового решения клетки): тогда и последняя точка
    списка стоит с отчётным нормативом."""
    if not points:
        raise ControlInputError("решение о взносе без точек окна (М§4.14.1)")
    table = []
    for pos, pt in enumerate(points):
        held = pt["dpreg"] / pt["rwa"] if closing and pos == len(points) - 1 else 0.0
        gaps = {name: (pt[REQ_OF[name]] - (pt[name] - held)) * pt["rwa"] for name in (NORM_TOTAL, NORM_BASE)}
        name = NORM_TOTAL if gaps[NORM_TOTAL] >= gaps[NORM_BASE] - TIE_TOL else NORM_BASE
        table.append({"q": pt["q"], "s20": gaps[NORM_TOTAL], "s11": gaps[NORM_BASE], "s": max(gaps.values()),
                      "norm": name, "rwa": pt["rwa"]})
    need = max(line["s"] for line in table)
    worst = next(line for line in table if line["s"] >= need - TIE_TOL)
    return {"shortfall": need, "point": worst["q"], "norm": worst["norm"], "rwa_point": worst["rwa"],
            "rec": need if need > least else 0.0, "points": table}


def _c_year_point(ctx: dict, s: str, p: dict, row: dict, j: int, bv0: float, rwa0: float, ni_q: dict) -> dict:
    """Точка окна на конец квартала j периода p по годовой строке row (так же, как точки проверки дивиденда,
    М§17): капитал — BV начала периода плюс совокупный доход кварталов по j из квартального профиля строки,
    минус дивиденды и плюс взносы, решённые не позже j; фонд FVOCI — квартальная рекурсия; RWA —
    геометрически между началом и концом периода; DPreg — объявленное, но не вычтенное к концу квартала;
    инструменты с квартала ключа доли — доля клетки строки на RWA точки (М§4.11)."""
    y, h = p["year"], p["quarters"][j]
    bv = (bv0 + sum(row["ci_q"][:j + 1]) - sum(a for jj, a in row["div_list"] if jj <= j)
          + sum(a for jj, a in row["rec_list"] if jj <= j))
    rwa = rwa0 * (row["rwa"] / rwa0) ** ((j + 1) / p["n"])
    held = row["dpreg_q"][j]
    cap = _c_capital(ctx, s, y, h, bv, held, row["R_q"][j], rwa, ni_q, row.get("t2s"),
                     c_at1_at(ctx, y, h, rwa, row.get("a1s")))
    return {"q": c_qidx(ctx["anchor"], y, h), "n20": cap["n20"], "n11": cap["n11"], "dpreg": held, "rwa": rwa,
            "req20": cap["req20"], "req11": cap["req11"], "floor20": cap["floor20"], "floor11": cap["floor11"],
            "bv": bv}


def _c_recap_window(ctx: dict, cell: dict, st: dict, i: int, first: tuple, k_from: int, k_to: int) -> list[dict]:
    """Точки окна решения — кварталы сетки k_from … k_to, начиная с периода i. first — (состояние, строка) шага
    периода i; когда окно уходит в следующий год, тот считается пробным шагом с конца предыдущего без новых
    решений — ни дивиденда, ни взноса, и тогда, когда в окно попал квартал собрания или следующий квартал
    решения о взносе (эти решения принадлежат своим кварталам и будут приняты там, с деньгами взноса в
    капитале); выплаты и вычеты дивидендов, уже стоящих в очереди, идут в своих кварталах."""
    start, (state, row), idx = st, first, i
    j = k_from - c_qidx(ctx["anchor"], ctx["periods"][i]["year"], ctx["periods"][i]["quarters"][0])
    points = []
    for _ in range(k_from, k_to + 1):
        if j == ctx["periods"][idx]["n"]:
            start = {**state, "rwa": row["rwa"]}
            idx, j = idx + 1, 0
            state, row = _c_period(ctx, cell, start, idx, 0.0)
        points.append(_c_year_point(ctx, cell["scenario"], ctx["periods"][idx], row, j, start["BV"], start["rwa"],
                                    {**start["ni_q"], **row["ni_q"]}))
        j += 1
    return points


def _c_recap_decide(ctx: dict, cell: dict, st: dict, i: int, div: float) -> tuple[float, dict, tuple]:
    """Решение о взносе акционеров в квартал решения q_R периода i (М§4.14.1): пробный шаг с дивидендом div,
    уже принятым в этом периоде к кварталу решения, и без взноса; точки — все кварталы окна от квартала решения
    до min(q_R + L, Q); недостаток — по отчётным нормативам, в последней точке — без дивиденда, объявленного, но
    не вычтенного к концу окна. div — дивиденд собрания этого года, когда оно не позже квартала решения; при
    решении раньше собрания — ноль: дивиденд этого года ещё не решён, и пробный шаг его не несёт. Дивиденды
    прошлых решений идут очередями состояния. Возвращает (взнос, запись решения, пробный шаг периода): при
    нулевом взносе пробный шаг с дивидендом периода и есть окончательный."""
    rule, p = ctx["recap"], ctx["periods"][i]
    asks = rule["quarter"]
    k_r = c_qidx(ctx["anchor"], p["year"], asks)
    k_max = min(k_r + rule["ahead"], ctx["Q"])
    trial = _c_period(ctx, cell, st, i, div)
    made = c_recap_shortfall(_c_recap_window(ctx, cell, st, i, trial, k_r, k_max), rule["least"])
    made.update(profit_year=p["year"] - 1, q=k_r, period=str(p["year"]) + PART_LETTERS[0] + str(asks),
                window_end=k_max)
    return made["rec"], made, trial


def _c_recap_rest(ctx: dict, cell: dict, st: dict, i: int, final: tuple, made: dict) -> dict:
    """Остаток недостатка после взноса решения made — справочная мера инварианта «взнос закрывает разрыв»
    (М§14.1): недостаток шага 3 М§4.14.1 на окончательном шаге периода i (final — его состояние и строка, с
    дивидендом и взносом) в точках инварианта q_R … min(c_max, q_R + δ − 1) — от квартала решения до квартала
    перед ближайшим новым решением клетки, о дивиденде или о взносе. Точки следующего года — по пробному шагу
    этого года с конца окончательного шага и без новых решений: до квартала нового решения окончательный путь
    клетки таких решений ещё не несёт, а годовая строка с ними разнесла бы их след (дивиденд собрания, вес риска
    денег следующего взноса) и на ранние кварталы года. Точки — тем же правилом, что в решении."""
    checked = c_recap_check_points(made["q"], made["window_end"], ctx["recap"]["span"])
    points = _c_recap_window(ctx, cell, st, i, final, checked[0], checked[-1])
    left = c_recap_shortfall(points, 0.0, closing=checked[-1] == made["window_end"])
    return {"left": left["shortfall"], "share": left["shortfall"] / made["rec"], "point": left["point"],
            "norm": left["norm"], "points": left["points"]}


def c_recap_left(ctx: dict, cell: dict) -> dict:
    """Остаток недостатка после взноса по решениям клетки — справочная мера инварианта «взнос закрывает разрыв»
    (М§14.1; считается в проходе клетки, _c_recap_rest): год прибыли решения со взносом больше нуля → {left —
    наибольший остаток в точках инварианта, share — его доля во взносе, point и norm — где он стоит, points —
    недостатки точек}."""
    return {year: made["left"] for year, made in cell["recaps"].items() if made["rec"] > 0.0}


# ============================================================================ клетка целиком: путь, RI/DDM, терминал

def _c_cell_path(ctx: dict, cell: dict, upto_year: int | None = None) -> dict:
    """Годовой путь клетки и решения о дивидендах (до года upto_year включительно, если задан)."""
    B, A = ctx["B"], ctx["A"]
    st = _c_start_state(ctx)
    y0, qa = ctx["anchor"]
    cap0 = _c_capital(ctx, cell["scenario"], y0, qa, A["BV"], A["DP"], A["R0"], ctx["rwa0"], st["ni_q"])
    st["rwa"] = ctx["rwa0"]
    rows, decisions = [], {}
    if ctx["quarterly"]:
        # квартальный календарь (М§5.7) и рост, ограниченный капиталом (М§4.13): квартальный проход внутри года
        cap0 = _c_capital(ctx, cell["scenario"], y0, qa, A["BV"], c_dpreg_anchor(B, A), A["R0"], ctx["rwa0"],
                          st["ni_q"])
        made = []
        for i, p in enumerate(ctx["periods"]):
            if upto_year is not None and p["year"] > upto_year:
                break
            st, row = _c_year_quarterly(ctx, cell, st, i)
            st["rwa"] = row["rwa"]
            made.extend(row["decisions_q"])
            rows.append(row)
        out = {"rows": rows, "decisions": decisions, "anchor_capital": cap0, "decisions_q": made}
        if upto_year is None:
            out["decisions"] = c_profit_years(ctx, made)
        _c_year_margin(ctx, rows)
        return out
    agm = int(c_bnum(B, "dividends.calendar.agm_quarter"))
    rule = ctx["recap"]
    asks = rule["quarter"] if rule is not None else None        # номер в году квартала решения о взносе (h_R)
    recaps = {}
    for i, p in enumerate(ctx["periods"]):
        if upto_year is not None and p["year"] > upto_year:
            break
        # решение о взносе — в каждом квартале сетки с номером h_R, кроме последнего квартала сетки (М§4.14.1):
        # и в году якоря, и в год шока (отменён только дивиденд), и при записи реестра, и когда дивиденд объявлен
        # до даты фактов и решения о нём клетка не принимает. Якорь на квартале решения — первое решение через год
        deciding = (rule is not None and asks in p["quarters"]
                    and c_qidx(ctx["anchor"], p["year"], asks) < ctx["Q"])
        rec, made, trial = 0.0, None, None
        if deciding and asks < agm:
            # решение раньше собрания этого года: принят только дивиденд прошлых лет (он идёт очередями
            # состояния); дивиденд этого года ещё не решён, и пробный шаг взноса его не несёт
            rec, made, _ = _c_recap_decide(ctx, cell, st, i, 0.0)
        div, kind = 0.0, None
        if agm in p["quarters"] and not (p["stub"] and A["DP_year"] is not None
                                         and int(A["DP_year"]) == p["year"] - 1):
            # и в неполном году якоря: собрание после якоря решает в своём квартале (М§17), если факты не
            # говорят, что дивиденд за этот год прибыли уже объявлен и вычтен из BV якоря (М§5.4). Взнос более
            # раннего квартала этого года стоит в капитале пробного прохода дивиденда; взноса своего и более
            # позднего квартала собрание не ждёт (М§5.3 п. 7)
            div, info = _c_decide(ctx, cell, st, i, rec)
            kind = info["kind"]
            decisions[p["year"] - 1] = {**info, "div": div, "dps": div * 1000.0 / A["N_out"]}
        if deciding and asks >= agm:
            # решение в квартал собрания (после решения о дивиденде) или позже него: дивиденд этого года принят
            rec, made, trial = _c_recap_decide(ctx, cell, st, i, div)
        if made is not None:
            # дивиденд решения о взносе (М§4.14.1): последнее решение клетки о дивиденде в кварталах q_R − 3 … q_R —
            # собрание этого года, когда оно не позже квартала решения, иначе собрание прошлого года; решений до
            # сетки клетка не принимала — у них дивиденд ноль
            last = decisions.get(c_recap_dividend_year(p["year"], agm, asks))
            made["div"], made["div_kind"] = (0.0, None) if last is None else (last["div"], last["kind"])
            recaps[p["year"] - 1] = made
        D_keep = st["D"]
        if trial is not None and not rec:
            st, row = trial                             # взноса нет: пробный шаг с дивидендом — окончательный
        else:
            before = st
            st, row = _c_period(ctx, cell, st, i, div, rec=rec)
            if rec:
                made["left"] = _c_recap_rest(ctx, cell, before, i, (st, row), made)
        st["D"] = D_keep
        st["rwa"] = row["rwa"]
        row["D"] = D_keep
        rows.append(row)
    _c_year_margin(ctx, rows)
    out = {"rows": rows, "decisions": decisions, "anchor_capital": cap0}
    if ctx["recap"] is not None:
        out["recaps"] = recaps
    return out


def _c_year_margin(ctx: dict, rows: list[dict]) -> None:
    """Годовые метрики движка по правилу печати (М§0.3): сумма года к среднему пяти концов кварталов — конец
    прошлого года и четыре конца года. ЧПМ — ЧПД к процентным активам, CoR — резервы к кредитам по
    амортизированной стоимости; C/I — расходы к доходу NII + F + INS + MISC + FVR (М§4.6). Концы кварталов —
    из квартального прохода капитала; у годовой ветви образца — геометрический путь между началом и концом
    года. Неполный год якоря значений не несёт (его годовая метрика смешивает факты отчётных кварталов,
    М§4.6)."""
    prev = ctx["tr"]["iea0"]
    for p, row in zip(ctx["periods"], rows):
        inner = ([x["iea"] for x in row["quarters"]] if "quarters" in row
                 else _c_geo_path(prev, row["iea_end"], p["n"])[1:])
        row["iea_ends"] = [prev] + inner
        row["income_cir"] = row["nii"] + row["fees"] + row["ins"] + row["misc"] + row["fvr"]
        row["nim_year"] = row["cor_year"] = row["cir_year"] = None
        if not p["stub"]:
            row["nim_year"] = row["nii"] / _c_ends_mean(row["iea_ends"])
            row["cor_year"] = row["llp"] / _c_ends_mean(row["loans_ac_ends"])
            row["cir_year"] = row["opex"] / row["income_cir"] if row["income_cir"] else None
        prev = row["iea_end"]


def _c_ends_mean(ends: list[float]) -> float:
    """Среднее концов кварталов года — знаменатель годового отношения (М§0.3)."""
    return sum(ends) / len(ends)


# ============================================================================ квартальный календарь дивидендов (М§5.7)

def c_div_calendar(B: dict, A: dict) -> dict:
    """Календарь квартального режима (М§5.7.2, §5.7.4), общий для клеток: правило закрытого квартала p_last
    по фактам, открытые кварталы прибыли с кварталами решения, вычета и выплаты (запись реестра сильнее
    карты лагов), состояние якоря — очереди объявленных дивидендов и постоянная часть остатка."""
    if "divcal" in A:
        return A["divcal"]
    anchor, facts_date = A["anchor"], A["facts_date"]
    cal = c_bget(B, "dividends.calendar")
    for key in ("decision_lag_quarters", "reg_deduction_lag_quarters", "payment_lag_quarters", "checkpoints_ahead"):
        if cal.get(key) is None:
            raise ControlInputError(f"dividends.calendar.{key}: нет ключа квартального режима (М§5.7.1)")
    if int(cal["checkpoints_ahead"]) != 0:
        raise ControlInputError("dividends.calendar.checkpoints_ahead: допустим только 0 (М§5.7.1)")
    lag_raw = cal["decision_lag_quarters"]
    if isinstance(lag_raw, dict):
        lags = {int(k): int(v) for k, v in lag_raw.items()}
        if sorted(lags) != list(range(1, QY + 1)):
            raise ControlInputError("dividends.calendar.decision_lag_quarters: ключи — не ровно 1…4 (М§5.7.1)")
    else:
        lags = {h: int(lag_raw) for h in range(1, QY + 1)}
    reg_lag, pay_lag = int(cal["reg_deduction_lag_quarters"]), int(cal["payment_lag_quarters"])
    if any(not 1 <= x <= QY for x in list(lags.values()) + [reg_lag, pay_lag]):
        raise ControlInputError("лаг календаря дивидендов вне 1…4 (М§5.7.1)")
    last_q = c_qidx(anchor, *c_per_parse(c_bget(B, "meta.last_period")))

    def c_day(rec, field):
        val = _c_nodeval(rec.get(field))
        return _c_as_date(val) if val else None

    def c_map(k):
        """Карта лагов квартала прибыли k: (квартал решения, вычета, выплаты)."""
        q_dec = k + lags[c_qper(anchor, k)[1]]
        return q_dec, max(q_dec, k + reg_lag), max(q_dec, k + pay_lag)

    # закрыт ли квартал прибыли до якоря, решает факт (М§5.7.2)
    closed, hist_dps = [], {}
    for rec in A["div_history"]:
        per = _c_nodeval(rec.get("period"))
        if not per:
            raise ControlInputError("строка dividends.history без квартала прибыли period (прил. B)")
        k = c_qidx(anchor, *c_per_parse(per))
        dps = _c_nodeval(rec.get("dps"))
        if dps is None:
            dps = _c_nodeval(rec.get("dps_ordinary"))
        hist_dps[k] = None if dps is None else float(dps)
        decided = c_day(rec, "decided_date")
        if decided is not None and decided <= facts_date:
            closed.append(k)
    if not closed:
        raise ControlInputError("в dividends.history нет решения не позже даты фактов: p_last не определён (М§5.7.2)")
    p_last = max(closed)
    register = {}
    for rec in A["register"]:
        if rec.get("status", "declared") not in REGISTER_BINDING:
            continue
        per = _c_nodeval(rec.get("period"))
        if not per:
            raise ControlInputError("запись реестра без квартала прибыли (М§5.7.6)")
        k = c_qidx(anchor, *c_per_parse(per))
        decided = c_day(rec, "decided_date")
        if k > p_last and decided is not None and decided <= facts_date:
            raise ControlInputError(f"запись реестра {per}: решение раньше даты фактов, а строки в истории "
                                    f"дивидендов нет (М§5.7.6)")
        q_dec, q_reg, q_pay = c_map(k)
        record, pay, ex = c_day(rec, "record_date"), c_day(rec, "pay_date"), c_day(rec, "ex_date")
        q_cell = max(1, q_dec, c_qidx_of_date(anchor, decided)) if decided is not None else max(1, q_dec)
        register[k] = {"p": k, "period": str(per), "dps": float(_c_nodeval(rec["dps"])), "q_cell": q_cell,
                       "R": c_qidx_of_date(anchor, record) if record is not None else q_reg,
                       "P": c_qidx_of_date(anchor, pay) if pay is not None else q_pay, "ex": ex}
    opened, by_q = {}, {}
    for k in range(p_last + 1, last_q):
        yy, hh = c_qper(anchor, k)
        q_dec, q_reg, q_pay = c_map(k)
        rec = register.get(k)
        q_cell = rec["q_cell"] if rec is not None else max(1, q_dec)
        if q_cell > last_q:
            continue                                    # решение остаётся терминалу (М§7)
        ent = {"p": k, "period": f"{yy}Q{hh}", "year": yy, "h": hh, "q_cell": q_cell,
               "q_reg": max(q_cell, rec["R"] if rec is not None else q_reg),
               "q_pay": max(q_cell, rec["P"] if rec is not None else q_pay),
               "dps_register": None if rec is None else rec["dps"]}
        opened[k] = ent
        by_q.setdefault(q_cell, []).append(ent)
    # состояние якоря: объявленные и не выплаченные дивиденды закрытых кварталов прибыли
    queue0, seen, total = [], set(), 0.0
    for it in A["DP_declared"]:
        k = c_qidx(anchor, *c_per_parse(it["period"]))
        if k > p_last:
            raise ControlInputError(f"balance.dividends_payable_declared: период {it['period']} не закрыт (М§5.7.4)")
        if k in seen:
            raise ControlInputError(f"balance.dividends_payable_declared: период {it['period']} повторяется")
        seen.add(k)
        rec = register.get(k)
        _, q_reg, q_pay = c_map(k)
        queue0.append({"amt": it["amount"], "dec": 0, "reg": rec["R"] if rec is not None else q_reg,
                       "pay": max(1, rec["P"] if rec is not None else q_pay)})
        total += it["amount"]
    if total > A["DP"] + 1e-9:
        raise ControlInputError("сумма balance.dividends_payable_declared больше остатка дивидендов к выплате")
    A["divcal"] = {"p_last": p_last, "open": opened, "by_q": by_q, "register": register, "queue0": queue0,
                   "perm": A["DP"] - total, "hist_dps": hist_dps, "last_q": last_q, "closed": sorted(closed)}
    return A["divcal"]


def c_dpreg_anchor(B: dict, A: dict) -> float:
    """DPreg на якоре (М§4.11): дивиденды, вычтенные из BV якоря, но ещё не вычтенные из регуляторного
    капитала. Квартальный режим — суммы очереди вычетов состояния якоря; годовой — остаток дивидендов к
    выплате (объявлен в квартал собрания, отсечка — позже якоря)."""
    if not c_is_quarterly(B):
        return A["DP"]
    return sum(it["amt"] for it in c_div_calendar(B, A)["queue0"] if it["reg"] >= 1)


def c_div_base(ctx: dict, ni_all: dict, k: int, cpn_new: dict | None = None, world: str | None = None) -> float:
    """База решения за квартал прибыли k (М§5.7.3): средняя базы W последних кварталов; прибыль квартала
    не позже якоря — факт, позже — ряд клетки; купон бессрочных инструментов — в квартале его выплаты. cpn_new —
    купон сверх базы кварталов после налога у книги с ключом доли добавочного капитала (М§4.9; кварталы не позже
    якоря — ноль): при deduct_at1_after_tax он вычитается так же, как купон якоря. world — мир клетки: у книги с ключом
    capital.at1_coupon купон якоря — его формула по ключевой этого мира (кварталы не позже якоря — с ключевой квартала
    якоря); у книги с ключом tax.structure купон вычитается целиком (τ_cpn = 0, М§4.8)."""
    B, A, anchor = ctx["B"], ctx["A"], ctx["anchor"]
    window = int(c_bopt(B, "dividends.policy.base_window_quarters", 1))
    if not 1 <= window <= 2 * QY:
        raise ControlInputError("dividends.policy.base_window_quarters вне 1…8 (М§5.7.1)")
    deduct = bool(c_bget(B, "dividends.policy.deduct_at1_after_tax"))
    total = 0.0
    for x in range(k - window + 1, k + 1):
        yq = c_qper(anchor, x)
        if yq not in ni_all:
            raise ControlInputError(f"нет прибыли акционеров квартала {yq[0]}Q{yq[1]} для базы дивиденда (М§5.7.3)")
        total += ni_all[yq]
        if deduct and yq[1] == A["cpn_quarter"]:
            tau_c = c_traj_at(c_bget(B, "tax.statutory"), yq[0], yq[1]) if ctx.get("tax") is None else 0.0
            total -= c_anchor_coupon(ctx, world, yq[0], yq[1]) * (1.0 - tau_c)
        if deduct and cpn_new is not None:
            total -= cpn_new.get(yq, 0.0)
    return total / window


def c_payout_share(B: dict, year: int) -> float:
    """Доля выплаты года прибыли (М§5.2): clip(payout + payout_deviation, 0, 1)."""
    return min(1.0, max(0.0, c_traj_year(c_bget(B, "dividends.policy.payout"), year)
                        + c_traj_year(c_bget(B, "dividends.payout_deviation"), year)))


def c_excess_share(B: dict, year: int) -> float:
    """ε года прибыли с линейным вводом (М§5.6)."""
    start = int(c_bnum(B, "dividends.excess.from_profit_year"))
    if year < start:
        return 0.0
    ramp = int(c_bnum(B, "dividends.excess.ramp_years"))
    if ramp < 1:
        raise ControlInputError("dividends.excess.ramp_years — целое ≥ 1 (М прил. A)")
    return c_bnum(B, "dividends.excess.epsilon") * min(1.0, (year - start + 1) / ramp)


def _c_req_glide(ctx: dict, s: str, k: int) -> tuple[float, float]:
    """Требования квартала k с глиссадой (М§4.13.1): req*_j = max по h = 0…H ( r_j,min(k+h, Q) − h × δ ).
    Без ограничения роста — требования без глиссады."""
    memo = ctx["glide_memo"]
    if (s, k) not in memo:
        B, rule = ctx["B"], ctx["growth"]
        ahead = rule["ahead"] if rule else 0
        step = rule["glide"] if rule else 0.0
        best20 = best11 = None
        for h in range(ahead + 1):
            yy, qq = c_qper(ctx["anchor"], min(k + h, ctx["Q"]))
            r20 = max(c_bnum(B, "dividends.policy.threshold"),
                      _c_floor(B, s, "n20_0", yy, qq) + c_bnum(B, "capital.mgmt_buffer.n20_0")) - h * step
            r11 = _c_floor(B, s, "n1_1", yy, qq) + c_bnum(B, "capital.mgmt_buffer.n1_1") - h * step
            best20 = r20 if best20 is None else max(best20, r20)
            best11 = r11 if best11 is None else max(best11, r11)
        memo[(s, k)] = (best20, best11)
    return memo[(s, k)]


def _c_bisect(fn, lo: float, hi: float) -> float:
    """Корень невозрастающей функции на отрезке делением пополам: fn(lo) ≥ 0 > fn(hi); возвращает
    наибольшую точку с fn ≥ 0 (в пределах сходимости)."""
    for _ in range(FIT_ITER):
        mid = (lo + hi) / 2.0
        if fn(mid) >= 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo <= PLAN_TOL:
            break
    return lo


def _c_quarter_capital(ctx: dict, s: str, y: int, h: int, R: float, ni_q: dict, t2s=None, a1s=None):
    """Нормативы конца квартала (y, h) как функция капитала, DPreg и RWA (М§4.11–§4.12): всё, что от них
    не зависит (инструменты, неаудированная прибыль, поправки, требования), считается один раз на квартал;
    вычеты идут за RWA пробы — растущая часть вычета якоря, а у книги с ключами доли ещё и постоянная в рублях
    сумма (c_deductions); рубли сценария квартала (М§4.11) — одна сумма на все пробы. У книги с ключом доли
    инструментов с квартала ключа и инструменты идут за RWA пробы — доля клетки t2s на них (М§4.11: T2 следует за
    RWA с постоянной долей при любой доле прироста, дивиденде и взносе); у книги с ключом доли добавочного капитала с
    квартала ключа добавочный капитал — доля клетки a1s на RWA пробы (на балансе пробы — та же сумма, RWA пробы —
    неподвижная точка М§4.10). Возвращает функцию (bv, dpreg, rwa) → нормативы и требования."""
    B = ctx["B"]
    keep = (1.0 - c_bnum(B, "capital.n20.fvoci_recognition")) * R
    q_chi = ctx.get("t2_from")
    per_rwa = None                                  # доля инструментов пробы: None — T2 одна сумма на квартал
    at1_rule = ctx.get("at1")
    at1_per = None                                  # доля добавочного капитала пробы: None — AT1 факт якоря
    if at1_rule is not None and c_qidx(ctx["anchor"], y, h) >= at1_rule["from"]:
        at1_per = a1s
        if at1_per is None:
            raise ControlInputError(f"доля добавочного капитала клетки к кварталу {y}Q{h} не задана (М§4.11)")
    at1_fix = 0.0 if at1_per is not None else ctx["A"]["AT1"]
    if q_chi is not None and c_qidx(ctx["anchor"], y, h) >= q_chi:
        per_rwa = t2s
        if per_rwa is None:
            raise ControlInputError(f"доля инструментов клетки к кварталу {y}Q{h} не задана (М§4.11)")
        t2_sum = None
        extra20 = at1_fix
    else:
        t2_sum = c_traj_at(c_bget(B, T2_TRAJ), y, h)
        extra20 = at1_fix + t2_sum
    cut = [int(c) for c in c_bget(B, "capital.n11.audit_cutoffs")]
    e_q = _c_unaudited_quarters(cut, y, h)
    if any(yq not in ni_q for yq in e_q):
        raise ControlInputError(f"нет прибыли кварталов для E_q на {y}Q{h}")
    e_un = sum(ni_q[yq] for yq in e_q)
    e_out = e_un if e_un > 0.0 else 0.0
    adj20 = c_bnum(B, "capital.n20.gap_pp") - c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n20_0"), y, h)
    adj11 = c_bnum(B, "capital.n11.gap_pp") - c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n1_1"), y, h)
    fl20, fl11 = _c_floor(B, s, "n20_0", y, h), _c_floor(B, s, "n1_1", y, h)
    req20 = max(c_bnum(B, "dividends.policy.threshold"), fl20 + c_bnum(B, "capital.mgmt_buffer.n20_0"))
    req11 = fl11 + c_bnum(B, "capital.mgmt_buffer.n1_1")
    rub = c_rub_at(ctx, s, y, h) if ctx.get("rub") is not None else None     # вычет сценария в рублях (М§4.11)

    def c_ratios(bv: float, dpreg: float, rwa: float) -> dict:
        bvreg = bv + dpreg - keep
        ded20, ded11 = c_deductions(ctx, rwa)
        if rub is not None:
            ded20, ded11 = ded20 + rub[0], ded11 + rub[1]
        if per_rwa is None:
            k20 = bvreg - ded20 + extra20
            t2 = t2_sum
        else:
            t2 = per_rwa * rwa
            k20 = bvreg - ded20 + extra20 + t2
        if at1_per is None:
            at1 = at1_fix
        else:
            at1 = at1_per * rwa
            k20 = k20 + at1
        k11 = bvreg - e_out - ded11
        return {"k20": k20, "k11": k11, "n20": k20 / rwa + adj20, "n11": k11 / rwa + adj11,
                "n11_star": (k11 + e_out) / rwa + adj11, "e_unaudited": e_un, "ded20": ded20, "ded11": ded11,
                "t2": t2, "at1": at1, "floor20": fl20, "floor11": fl11, "req20": req20, "req11": req11}

    return c_ratios


def _c_capital_pass(ctx: dict, cell: dict, st: dict, i: int, row: dict) -> tuple[dict, dict]:
    """Квартальный проход капитала внутри года (М§17; порядок М§5.7.4 и §4.13.2).

    По кварталам года: остатки кредитных книг, баланс и RWA на конец квартала, нормативы, требование с
    глиссадой, решения о дивиденде, доля прироста λ и навёрстывание. Совокупный доход и прибыль кварталов
    — профиль годовой строки row (её ОПУ посчитаны годовым шагом при прежнем плане года). Долю λ и долю
    навёрстывания θ контрольная модель ищет делением отрезка пополам по невязке условия роста, а не
    закрытой формулой с шагом секущей. Возвращает новый план года и выходы кварталов."""
    B, A, p = ctx["B"], ctx["A"], ctx["periods"][i]
    r, s = cell["regime"], cell["scenario"]
    y, qs, n = p["year"], p["quarters"], p["n"]
    loans, fv, oaf, rule, cal = ctx["loans"], ctx["fv"], ctx["oaf"], ctx["growth"], ctx["divcal"]
    k_first = c_qidx(ctx["anchor"], y, qs[0])
    ni_all = {**st["ni_q"], **row["ni_q"]}
    m = row["m_q"]
    n_out, n_iss = A["N_out"], A["N_iss"]
    wtf = c_bnum(B, "volumes.wholesale_to_funds")
    r_oa, r_ol = c_bnum(B, "volumes.other_assets_to_loans"), c_bnum(B, "volumes.other_liabilities_to_loans")
    r_al = c_bnum(B, "credit.allowance_ratio")
    m_liq = c_bnum(B, "volumes.liquid_min_share")
    ssl = c_bnum(B, "volumes.securities_share_of_liquid")
    outside = A["AT1"] + A["NCI"]
    skip_year = (r == R_CRISIS and y == ctx["shock_year"] and bool(c_bget(B, "dividends.crisis.skip_in_shock_year")))
    catch_on = bool(c_bget(B, "dividends.crisis.catch_up"))
    can_cut = rule is not None and rule["lam_min"] < 1.0 and any(m[b] > 0.0 for b in loans)
    E_prev, E_pot = {b: st["E"][b] for b in loans}, dict(st["Epot"])
    bv_prev, deferred, queue = st["BV"], st["D"], [dict(it) for it in st["dq"]]
    paths = {b: [st["E"][b]] for b in loans}
    year_divs, records, quarters = [], [], []
    # доля инструментов клетки (М§4.11): состояние начала года; квартал q_χ − 1 этого года задаёт её RWA своего
    # записанного шага (не оценки «только нормативы» и не проб доли прироста)
    q_chi, t2s, t2s_here = ctx.get("t2_from"), st.get("t2s"), None
    # доля добавочного капитала клетки (М§4.11): так же — состояние начала года, квартал q_α − 1 задаёт её RWA своего
    # записанного шага; с квартала ключа AT1 конца квартала — доля на RWA, а RWA — неподвижная точка (М§4.10)
    at1r = ctx.get("at1")
    a1s, a1s_here = st.get("a1s"), None
    cpn_all = None
    if at1r is not None:
        cpn_all = {**st["cpn_q"], **{(y, q_): row["cpn_new_net_q"][jj] for jj, q_ in enumerate(qs)}}
    for j, q in enumerate(qs):
        k = k_first + j
        for b in loans:
            E_pot[b] = E_pot[b] * (1.0 + m[b])
        todo = sorted(cal["by_q"].get(k, []), key=lambda e: e["p"])
        fixed = [{"amt": e["dps_register"] * n_out / 1000.0, "dec": k, "reg": e["q_reg"], "pay": e["q_pay"],
                  "p": e["p"]} for e in todo if e["dps_register"] is not None]
        own, calc_of = [], {}             # решения самой клетки (без записи реестра)
        for e in todo:
            base = c_div_base(ctx, ni_all, e["p"], cpn_all, cell["world"])
            pool = c_payout_share(B, e["year"]) * max(0.0, base)
            calc_of[e["p"]] = {"ent": e, "base": base, "pool": pool, "want": pool * n_out / n_iss}
            if e["dps_register"] is None:
                own.append(calc_of[e["p"]])
        live = [] if skip_year else own
        want_sum = sum(x["want"] for x in live)
        req20_g, req11_g = _c_req_glide(ctx, s, k)
        ratios = _c_quarter_capital(ctx, s, y, q, row["R_q"][j], ni_all, t2s, a1s)
        funds = row["fr_path"][j + 1] + row["cf_path"][j + 1]
        liab_fixed = funds + wtf * funds + outside
        oaf_q = oaf + row["oaf_ends"][j + 1] if "oaf_ends" in row else oaf    # с приращением пути квартала (М§4.3)
        at1_live = at1r is not None and k >= at1r["from"]
        if at1_live:
            liab_free = funds + wtf * funds + A["NCI"]       # пассивы без добавочного капитала: он — решение точки

        def c_quarter_end(lam, extra_loans, model_divs):
            """Конец квартала на копии состояния: кредитные книги при доле прироста lam и добавке
            навёрстывания, дивиденды квартала — записи реестра и model_divs."""
            Eq = {b: E_prev[b] * (1.0 + (lam if m[b] > 0.0 else 1.0) * m[b]) + extra_loans.get(b, 0.0)
                  for b in loans}
            total = sum(Eq.values())
            ac = total - sum(fv[b] * Eq[b] for b in fv) if fv else total
            decided = fixed + model_divs
            bv = bv_prev + row["ci_q"][j] - sum(d["amt"] for d in decided)
            dp, dpreg = st["dp_perm"], 0.0
            for it in queue + decided:
                if it["pay"] > k:
                    dp += it["amt"]
                if it["reg"] > k:
                    dpreg += it["amt"]
            oa = r_oa * total + oaf_q
            assets_nb = total - r_al * ac + oa
            if at1_live:
                # М§4.10: AT1 конца квартала — доля RWA, RWA несут деньги выпуска (закрытая форма, две ветви)
                g, b_ = c_rwa_parts(ctx, r, y, q, Eq, oa, row["dn_q"][j], row["xf_q"][j])
                la = c_at1_fixed_point(g, b_, liab_free + r_ol * total + dp + bv - assets_nb,
                                       m_liq * assets_nb / (1.0 - m_liq), a1s,
                                       f"клетка {cell['world']}/{r}/{s}, {y}Q{q}")["la"]
            else:
                la = liab_fixed + r_ol * total + dp + bv - assets_nb
                la = max(la, m_liq * assets_nb / (1.0 - m_liq))
            bal = dict(Eq)
            bal[SECURITIES], bal[LIQUIDITY] = ssl * la, (1.0 - ssl) * la
            rwa = _c_rwa_of(ctx, r, y, q, bal, oa, row["dn_q"][j], row["xf_q"][j])
            cp = ratios(bv, dpreg, rwa)
            if rule is None:
                # без ограничения роста запас — по отчётным нормативам и требованию без глиссады (М§5.7.4)
                room = ((cp["n20"] - cp["req20"]) * rwa, (cp["n11"] - cp["req11"]) * rwa)
            else:
                room = ((cp["n20"] - req20_g) * rwa, (cp["n11_star"] - req11_g) * rwa)
            return {"E": Eq, "loans": total, "bv": bv, "dp": dp, "dpreg": dpreg, "rwa": rwa, "cap": cp,
                    "room": room, "iea": total + la}

        full = c_quarter_end(1.0, {}, [])
        lam, add, final = 1.0, {}, full
        if rule is None:
            h_ref = min(full["room"])
        else:
            low = c_quarter_end(rule["lam_min"], {}, []) if can_cut else full
            h_ref = min(low["room"]) if rule["order"] == ORDER_DIV_FIRST else min(full["room"])
        div_base = min(want_sum, max(0.0, h_ref)) if want_sum else 0.0
        if rule is not None:
            # ι: часть базового дивиденда, чей вычет из регуляторного капитала приходится на этот квартал
            same_q = sum(div_base * x["want"] / want_sum for x in live if x["ent"]["q_reg"] == k) if want_sum else 0.0
            g_full = [h - same_q for h in full["room"]]
            g_low = [h - same_q for h in low["room"]]
            if can_cut and min(g_full) < 0.0:
                shares = []
                for a in range(len(g_full)):
                    if g_full[a] >= 0.0 or g_low[a] - g_full[a] <= PLAN_TOL:
                        shares.append(1.0)              # норматив не нарушен или урезание его не поправляет
                    elif g_low[a] <= 0.0:
                        shares.append(rule["lam_min"])
                    else:
                        shares.append(_c_bisect(lambda x, a=a: c_quarter_end(x, {}, [])["room"][a] - same_q,
                                                rule["lam_min"], 1.0))
                lam = min(shares)
                final = full if lam == 1.0 else low if lam == rule["lam_min"] else c_quarter_end(lam, {}, [])
            if lam == 1.0 and min(g_full) >= 0.0 and rule["catch_up"] > 0.0:
                # навёрстывание роста (М§4.13.2 п. 5): доля κ/4 разрыва с потенциальным путём, общей долей θ
                gap = {b: max(0.0, E_pot[b] - full["E"][b]) for b in loans}
                if any(v > 0.0 for v in gap.values()):
                    whole = {b: rule["catch_up"] / QY * gap[b] for b in loans}
                    tried = c_quarter_end(1.0, whole, [])
                    if min(tried["room"]) - same_q >= 0.0:
                        add, final = whole, tried
                    else:
                        theta = _c_bisect(lambda x: min(c_quarter_end(
                            1.0, {b: x * whole[b] for b in loans}, [])["room"]) - same_q, 0.0, 1.0)
                        add = {b: theta * whole[b] for b in loans}
                        final = c_quarter_end(1.0, add, [])
        h_fin = min(final["room"])
        cut = bool(live) and div_base < want_sum - 1e-9
        # догоняющая выплата и избыток — раз в год, в решении за четвёртый квартал прибыли, при λ* = 1
        catch = excess = 0.0
        top = [x for x in live if x["ent"]["h"] == QY]
        if top and lam == 1.0:
            if catch_on:
                catch = min(deferred, max(0.0, h_fin - div_base))
            excess = c_excess_share(B, top[0]["ent"]["year"]) * max(0.0, h_fin - div_base - catch)
        model_divs = []
        for e in todo:
            calc = calc_of[e["p"]]
            rec = {"period": e["period"], "year": e["year"], "h": e["h"], "q": k, "base": calc["base"],
                   "want": calc["want"], "headroom": h_ref, "headroom_final": h_fin, "base_div": 0.0,
                   "catch": 0.0, "excess": 0.0, "cut": False, "lam": lam,
                   "dps_policy": calc["pool"] * 1000.0 / n_iss, "deferred_before": deferred}
            if e["dps_register"] is not None:
                rec.update(source="register", div=e["dps_register"] * n_out / 1000.0)
                rec["base_div"] = rec["div"]
            elif skip_year:
                rec.update(source="crisis_skip", div=0.0)
                if catch_on:
                    deferred += calc["want"]
            else:
                rec["base_div"] = div_base * calc["want"] / want_sum if want_sum else 0.0
                if e["h"] == QY:
                    rec.update(catch=catch, excess=excess)
                    deferred -= catch
                rec.update(source="policy", cut=cut, div=rec["base_div"] + rec["catch"] + rec["excess"])
                if rec["div"]:
                    model_divs.append({"amt": rec["div"], "dec": k, "reg": e["q_reg"], "pay": e["q_pay"], "p": e["p"]})
            rec.update(dps=rec["div"] * 1000.0 / n_out, deferred_after=deferred)
            records.append(rec)
        end = c_quarter_end(lam, add, model_divs)
        cp = end["cap"]
        if q_chi is not None and k == q_chi - 1:
            t2s = t2s_here = c_t2_share_of(ctx, y, q, end["rwa"])     # записанный шаг квартала q_χ − 1 (М§4.11)
        if at1r is not None and k == at1r["from"] - 1:
            a1s = a1s_here = c_at1_share_of(ctx, end["rwa"])         # записанный шаг квартала q_α − 1 (М§4.11)
        E_prev, bv_prev = end["E"], end["bv"]
        decided = fixed + model_divs
        year_divs.extend(decided)
        queue = [it for it in queue + decided if it["pay"] > k or it["reg"] > k]
        for b in loans:
            paths[b].append(end["E"][b])
        quarters.append({"q": k, "lam": lam, "loans": end["loans"], "loans_potential": sum(E_pot.values()),
                         "catch_up": sum(add.values()), "div_model": sum(d["amt"] for d in model_divs),
                         "div": sum(d["amt"] for d in decided), "bv": end["bv"], "rwa": end["rwa"],
                         "n20": cp["n20"], "n11": cp["n11"], "n11_star": cp["n11_star"],
                         "k20": cp["k20"], "k11": cp["k11"], "ded20": cp["ded20"], "ded11": cp["ded11"],
                         "t2": cp["t2"], "at1": cp["at1"],
                         "req20": cp["req20"], "req11": cp["req11"], "req20_glide": req20_g,
                         "req11_glide": req11_g, "dp": end["dp"], "dpreg": end["dpreg"],
                         "headroom": h_ref, "headroom_final": h_fin, "iea": end["iea"]})
    plan = {"loans": paths, "divs": year_divs}
    info = {"quarters": quarters, "records": records, "deferred": deferred, "Epot": E_pot}
    if q_chi is not None:
        # доля после года — в состояние; доля, заданная кварталом этого года, — в план: годовая строка следующего
        # оборота берёт её для своих кварталов с q_χ (конец года — тот же, что у прохода)
        plan["t2s"], info["t2s"] = t2s_here, t2s
    if at1r is not None:
        # доля добавочного капитала и AT1 кварталов прохода — в план: годовая строка берёт их для купона сверх базы и
        # времени денег выпуска в среднем остатке (М§4.9, §4.10)
        plan["a1s"], info["a1s"] = a1s_here, a1s
        plan["at1_q"] = [x["at1"] for x in quarters]
    if ctx.get("t2p") is not None:
        plan["t2_q"] = [x["t2"] for x in quarters]          # T2 кварталов прохода — база надбавки следующего квартала
    return plan, info


def _c_plan_gap(old: dict, new: dict) -> float:
    """Наибольшее расхождение двух планов года: остатки кредитных книг — долей, дивиденды — млрд ₽."""
    if old["loans"] is None or len(old["divs"]) != len(new["divs"]):
        return float("inf")
    gap = 0.0
    for b, path in new["loans"].items():
        for a, c in zip(old["loans"][b], path):
            gap = max(gap, abs(c - a) / max(abs(c), 1.0))
    for a, c in zip(old["divs"], new["divs"]):
        if (a["dec"], a["reg"], a["pay"]) != (c["dec"], c["reg"], c["pay"]):
            return float("inf")
        gap = max(gap, abs(c["amt"] - a["amt"]))
    if new.get("t2s") is not None:
        # доля инструментов, заданная кварталом этого года (М§4.11): годовая строка берёт её из плана — план сошёлся,
        # когда сошлась и она (иначе конец года строки нёс бы долю прохода прошлого оборота)
        if old.get("t2s") is None:
            return float("inf")
        gap = max(gap, abs(new["t2s"] - old["t2s"]) / abs(new["t2s"]))
    if new.get("a1s") is not None:
        # доля добавочного капитала, заданная кварталом этого года (М§4.11) — как доля инструментов
        if old.get("a1s") is None:
            return float("inf")
        gap = max(gap, abs(new["a1s"] - old["a1s"]) / (abs(new["a1s"]) or 1.0))     # у панели без AT1 доля — ноль
    for name in ("at1_q", "t2_q"):
        # AT1 и T2 кварталов прохода: годовая строка берёт их для купона сверх базы, надбавки и среднего остатка
        if new.get(name) is not None:
            if old.get(name) is None:
                return float("inf")
            gap = max(gap, max(abs(c - a) / max(abs(c), 1.0) for a, c in zip(old[name], new[name])))
    return gap


def _c_year_quarterly(ctx: dict, cell: dict, st: dict, i: int) -> tuple[dict, dict]:
    """Год ветви с квартальным проходом капитала (М§17): годовые строки ОПУ при плане года (пути кредитных
    книг и решения о дивиденде по кварталам) и квартальный проход, который этот план пересчитывает на
    профиле прибыли годовой строки, — до совпадения плана. Возвращает (состояние, строка)."""
    p = ctx["periods"][i]
    plan = {"loans": None, "divs": []}
    for turn in range(FIT_ITER):
        nst, row = _c_period(ctx, cell, st, i, 0.0, plan)
        new_plan, info = _c_capital_pass(ctx, cell, st, i, row)
        gap = _c_plan_gap(plan, new_plan)
        if gap <= PLAN_TOL:
            break
        if turn >= FIT_ITER // 2 and plan["loans"] is not None and math.isfinite(gap):
            # медленная сходимость: полшага к новому плану
            for b, path in new_plan["loans"].items():
                new_plan["loans"][b] = [(a + c) / 2.0 for a, c in zip(plan["loans"][b], path)]
        plan = new_plan
    qr = info["quarters"]
    A, y = ctx["A"], p["year"]
    pot_end, act_end = qr[-1]["loans_potential"], qr[-1]["loans"]
    if i == 0:
        # за год якоря знаменатель роста — факт конца прошлого года (М§4.13.3)
        prev = A["history"].get(f"{y - 1}Q{QY}", {}).get(LINK_BASES[0]) if p["stub"] else sum(st["Epot"].values())
        pot_prev = act_prev = None if prev is None else float(prev)
    else:
        pot_prev, act_prev = sum(st["Epot"].values()), sum(st["E"][b] for b in ctx["loans"])
    row.update(quarters=qr, decisions_q=info["records"], plan_gap=gap, plan_turns=turn + 1,
               lam_q=[x["lam"] for x in qr], lam_min=min(x["lam"] for x in qr),
               catch_up=sum(x["catch_up"] for x in qr), div_model=sum(x["div_model"] for x in qr),
               loans_potential=pot_end, cut_share=1.0 - act_end / pot_end,
               growth_potential=None if pot_prev is None else pot_end / pot_prev - 1.0,
               growth_actual=None if act_prev is None else act_end / act_prev - 1.0,
               req20_glide=qr[-1]["req20_glide"], req11_glide=qr[-1]["req11_glide"],
               potential_end=dict(info["Epot"]), D=info["deferred"])
    nst["Epot"], nst["D"] = info["Epot"], info["deferred"]
    if "t2s" in info:
        nst["t2s"] = info["t2s"]            # доля инструментов клетки — та, что задал квартальный проход (М§4.11)
    if "a1s" in info:
        nst["a1s"] = info["a1s"]            # доля добавочного капитала клетки — та, что задал квартальный проход
    return nst, row


def c_profit_years(ctx: dict, made: list[dict]) -> dict:
    """Дивиденд и DPS по годам прибыли (М§5.7.5): сумма четырёх кварталов прибыли года — открытый квартал
    по решению клетки, закрытый — по строке истории. Закрытый квартал без своей строки, покрытый строкой
    истории более позднего квартала (решение «за девять месяцев» — одна строка, период — последний из
    кварталов), даёт ноль: его дивиденд — в той строке. Строка без числа DPS — отказ (null ≠ 0). Год входит,
    если хотя бы один его квартал открыт и ни одно его решение не лежит за сеткой."""
    A, cal, anchor = ctx["A"], ctx["divcal"], ctx["anchor"]
    by_p = {c_qidx(anchor, *c_per_parse(d["period"])): d for d in made}
    out = {}
    for year in sorted({e["year"] for e in cal["open"].values()}):
        ks = [c_qidx(anchor, year, h) for h in range(1, QY + 1)]
        if any(k > cal["p_last"] and k not in cal["open"] for k in ks):
            continue
        parts, dps, div, policy = {}, 0.0, 0.0, 0.0
        for k in ks:
            per = f"{year}Q{c_qper(anchor, k)[1]}"
            if k in by_p:
                parts[per] = by_p[k]
                dps += by_p[k]["dps"]
                div += by_p[k]["div"]
                policy += by_p[k]["dps_policy"]
            else:
                if k in cal["hist_dps"]:
                    hist = cal["hist_dps"][k]
                    if hist is None:
                        raise ControlInputError(f"строка dividends.history закрытого квартала {per} без DPS (М§5.7.5)")
                elif any(later > k for later in cal["closed"]):
                    hist = 0.0                          # покрыт строкой истории более позднего квартала
                else:
                    raise ControlInputError(f"нет строки dividends.history закрытого квартала {per} (М§5.7.5)")
                dps += hist
                policy += hist
                div += hist * A["N_out"] / 1000.0
        last_q = max((d["q"] for d in parts.values()), default=0)
        out[year] = {"kind": "quarterly", "div": div, "dps": dps, "dps_policy": policy, "quarters": parts,
                     "decision_year": c_qper(anchor, last_q)[0],
                     "cut": any(d["cut"] for d in parts.values())}
    return out


def c_cell_annual(ctx: dict, world: str, regime: str, scenario: str) -> dict:
    """Клетка (W, r, s): годовой путь, дивиденды, V_RI и V_DDM (М§6), терминал (М§7)."""
    cell = {"world": world, "regime": regime, "scenario": scenario}
    path = _c_cell_path(ctx, cell)
    out = {**cell, **path, "years": [p["year"] for p in ctx["periods"]]}
    out.update(_c_value_cell(ctx, cell, path["rows"], path["decisions"]))
    if ctx["recap"] is not None:
        _c_cell_shares(ctx, out)
    return out


def c_terminal_excess(last: dict, mult: float) -> dict:
    """Избыток капитала терминала X_T (М§7) по строке конца сетки last: нормативы терминала N20ᵀ и N11ᵀ — Н20.0
    и Н20.1 с прибылью периода без дивидендов, вычтенных из BV, но ещё не из регуляторного капитала; слагаемые
    минимума x20 = (N20ᵀ − req20) × RWA_Q и x11 = (N11ᵀ − req11) × RWA_Q; X_T = множитель × меньшее из них. Доля
    вычета якоря, постоянная в рублях (М§4.11), и вычет сценария в рублях входят сюда одним путём — через нормативы
    строки: её вычеты уже посчитаны с ними. Как они растут за концом сетки, задаёт доля λ_F (c_terminal_lines; без
    ключа — растут целиком, как у образца). Доля инструментов клетки (ключ capital.n20.t2_share, М§4.11, §7) входит
    так же — через Н20.0 строки: в нём T2_Q = χ_c × RWA_Q, а не значение траектории в квартале Q."""
    n20_t, n11_t = last["n20"], last["n11_star"]
    if last["dpreg"]:
        n20_t, n11_t = n20_t - last["dpreg"] / last["rwa"], n11_t - last["dpreg"] / last["rwa"]
    x20, x11 = (n20_t - last["req20"]) * last["rwa"], (n11_t - last["req11"]) * last["rwa"]
    return {"n20_t": n20_t, "n11_t": n11_t, "x20": x20, "x11": x11, "x_t": mult * min(x20, x11)}


def c_terminal_fixed_inputs(ctx: dict, cell: dict, last: dict, excess: dict) -> dict:
    """Постоянные в рублях части конца сетки (М§7, ключ λ_F) — своими величинами конца года L клетки:

        F_A = OA_fixed + ΔOA_Q                                  постоянные прочие активы (М§4.3)
        R_F = (ω_oaf × OA_fixed + ω_Δ × ΔOA_Q) × Dn_Q × X_Q × M_r,Q их RWA (М§4.11)
        C_j = Dfix_j + Drub_j,s,Q                               постоянные в рублях вычеты норматива j (нули без ключей)
        κ_j = req_j,Q − (gap_pp_j − deduction_pp_j,s,Q) + Dgrow_j / RWA_0 − χ_j     капитал на рубль RWA норматива j
        j*  = Н20.0, если N20ᵀ − req20 ≤ N11ᵀ − req11, иначе Н20.1   норматив, который связывает на T (задаёт X_T)

    Dgrow_j — растущая часть вычета якоря (без ключей доли — весь вычет якоря); χ_20 — доля инструментов клетки у
    книги с ключом capital.n20.t2_share (доля строки конца сетки), иначе ноль, χ_11 = 0; нормативы терминала — из
    c_terminal_excess той же строки (без невычтенных дивидендов)."""
    B = ctx["B"]
    period = ctx["periods"][-1]
    yl, hl = period["year"], period["quarters"][-1]
    s = cell["scenario"]
    d_q = c_oaf_change(ctx, yl, hl)
    path = ctx.get("oaf_path")
    scale = last["dn_q"][-1] * last["xf_q"][-1]
    mult = ctx["rwa_mult"].get(cell["regime"])
    if mult is not None:
        scale = scale * c_traj_at(mult, yl, hl)
    r_f = (ctx["dens_oaf"] * ctx["oaf"] + (path["density"] * d_q if path is not None else 0.0)) * scale
    rub = c_rub_at(ctx, s, yl, hl)
    parts = ctx.get("ded")
    c, kappa = {}, {}
    for pos, name in enumerate((NORM_TOTAL, NORM_BASE)):
        fix = parts[name]["fix"] if parts is not None else 0.0
        grow = parts[name]["grow"] if parts is not None else c_bnum(B, DED_ANCHOR[name])
        c[name] = fix + rub[pos]
        add = (c_bnum(B, f"capital.{name}.gap_pp")
               - c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.{RUB_SLOT[name]}"), yl, hl))
        kappa[name] = last[REQ_OF[name]] - add + grow / ctx["rwa0"]
    if ctx.get("t2_from") is not None:
        # доля инструментов клетки (М§4.11, §7): стоящая вне бизнеса доля постоянных частей несёт свои инструменты по
        # той же доле — капитал на рубль её RWA по Н20.0 меньше на χ_c; по Н20.1 инструментов нет, κ_11 прежний
        kappa[NORM_TOTAL] = kappa[NORM_TOTAL] - last["t2s"]
    if ctx.get("at1") is not None:
        # доля добавочного капитала клетки (М§4.11, §7): стоящая вне бизнеса доля несёт свой AT1 по той же доле —
        # κ_20 − χ_c − α_c; по Н20.1 добавочного капитала нет, κ_11 прежний
        kappa[NORM_TOTAL] = kappa[NORM_TOTAL] - last["a1s"]
    binding =(NORM_TOTAL if excess["n20_t"] - last["req20"] <= excess["n11_t"] - last["req11"] else NORM_BASE)
    return {"f_a": ctx["oaf"] + d_q, "r_f": r_f, "c": c, "kappa": kappa, "binding": binding}


def c_terminal_fixed_block(inp: dict, lam_f: float, y_m: float, tau: float, nci: float,
                           after_tax: float | None = None) -> dict:
    """Блок постоянных частей обеих сторон на T (М§7): капитал, который они держат, F_K = C_j* + κ_j* × R_F; их
    фондирование балансирующими статьями D_F = F_A − F_K (знак любой); годовой доход I_F = −y_m × D_F × (1 − τ) ×
    (1 − nci) — своего дохода у постоянных частей нет (при D_F < 0 — доход капитала, который держит вычет без актива
    под ним). y_m — маржинальная ставка балансирующих статей на конце Q. after_tax — у книги с ключом tax.structure
    ставка после налога y^τ_m (c_terminal_y_after_tax): I_F = −y^τ_m × D_F × (1 − nci), τ не читается."""
    j = inp["binding"]
    f_k = inp["c"][j] + inp["kappa"][j] * inp["r_f"]
    d_f = inp["f_a"] - f_k
    i_f = -y_m * d_f * (1.0 - tau) * (1.0 - nci) if after_tax is None else -after_tax * d_f * (1.0 - nci)
    out = {"lam_f": lam_f, "f_a": inp["f_a"], "r_f": inp["r_f"], "c": inp["c"][j], "kappa": inp["kappa"][j],
           "binding": j, "f_k": f_k, "d_f": d_f, "i_f": i_f, "y_m": y_m,
           "c_all": dict(inp["c"]), "kappa_all": dict(inp["kappa"])}
    if after_tax is not None:
        out["y_m_after_tax"] = after_tax
    return out


def c_terminal_lines(x_t: float, bv_star: float, ci_t1: float, k_t: float, g_t: float, fade: float,
                     fixed: dict | None = None, *, where: str = "", om_ann: float | None = None) -> dict:
    """Строки терминала от ROE_T до TV_DDM (М§7), угасание одностороннее. Без блока постоянных частей и при λ_F = 1 —
    прежние строки образца (те же действия над теми же числами):

        ROE_T = CI_T+1 / BV*,  TV_RI = (ROE'_T − k_T) × BV* / (k_T − g_T),  P_T = (ROE'_T − g_T) × BV* / (k_T − g_T)

    С блоком и λ_F < 1 (w = 1 − λ_F — доля постоянных частей, которая стоит в рублях вне бизнеса: без роста, без
    удержания капитала под рост и без угасания; доля λ_F остаётся в бизнесе):

        B = BV* − w × F_K,   CI_B = CI_T+1 − w × (1 + g_T) × I_F,   ROE_T = CI_B / B → ROE'_T
        TV_RI = (ROE'_T − k_T) × B / (k_T − g_T) + w × (I_F − k_T × F_K) / k_T
        P_T   = (ROE'_T − g_T) × B / (k_T − g_T) + w × I_F / k_T

    TV_DDM = X_T + P_T = BV_Q + TV_RI при любом λ_F. ROE_T и ROE'_T строки — бизнеса, без стоящей доли. B ≤ 0 — отказ
    книги с названием клетки (постоянные части больше капитала терминала).

    om_ann — прочие движения капитала за год за концом сетки у книги с ключом valuation.terminal.other_movements:
    flat_rub (М§7): слагаемое OM_ann / k_T в TV_RI и P_T (и через P_T — в TV_DDM) — постоянно в номинальных рублях, без
    роста, без удержания капитала под рост, вне угасания и вне блока постоянных частей; ROE_T его не читает. None —
    ключа нет или none: прежние строки."""
    out = _c_terminal_core(x_t, bv_star, ci_t1, k_t, g_t, fade, fixed, where)
    if om_ann is not None:
        om_term = om_ann / k_t
        out.update(tv_ri=out["tv_ri"] + om_term, p_t=out["p_t"] + om_term, tv_ddm=x_t + (out["p_t"] + om_term),
                   om_term=om_term)
    return out


def _c_terminal_core(x_t: float, bv_star: float, ci_t1: float, k_t: float, g_t: float, fade: float,
                     fixed: dict | None, where: str) -> dict:
    """Строки терминала без слагаемого прочих движений (c_terminal_lines)."""
    w = 0.0 if fixed is None else 1.0 - fixed["lam_f"]
    if w == 0.0:
        roe_raw = ci_t1 / bv_star
        roe = k_t + fade * max(roe_raw - k_t, 0.0) + min(roe_raw - k_t, 0.0)
        p_t = (roe - g_t) * bv_star / (k_t - g_t)
        return {"roe_t_raw": roe_raw, "roe_t": roe, "tv_ri": (roe - k_t) * bv_star / (k_t - g_t), "p_t": p_t,
                "tv_ddm": x_t + p_t, "business_capital": bv_star, "business_ci": ci_t1}
    f_k, i_f = fixed["f_k"], fixed["i_f"]
    biz = bv_star - w * f_k
    if not biz > 0.0:
        raise ControlInputError(f"клетка {where}: капитал бизнеса терминала B = BV* − (1 − λ_F) × F_K = {biz} ≤ 0 — "
                                f"постоянные части больше капитала терминала (М§7)")
    ci_b = ci_t1 - w * (1.0 + g_t) * i_f
    roe_raw = ci_b / biz
    roe = k_t + fade * max(roe_raw - k_t, 0.0) + min(roe_raw - k_t, 0.0)
    p_t = (roe - g_t) * biz / (k_t - g_t) + w * i_f / k_t
    return {"roe_t_raw": roe_raw, "roe_t": roe,
            "tv_ri": (roe - k_t) * biz / (k_t - g_t) + w * (i_f - k_t * f_k) / k_t, "p_t": p_t,
            "tv_ddm": x_t + p_t, "business_capital": biz, "business_ci": ci_b}


def _c_value_cell(ctx: dict, cell: dict, rows: list[dict], decisions: dict) -> dict:
    B, A = ctx["B"], ctx["A"]
    ck, periods = ctx["clock"], ctx["periods"]
    df = ctx["disc"][cell["world"]]
    p0 = ck["p0"]
    bv_prev = A["BV"] if p0 == 0 else rows[p0 - 1]["bv"]
    r0 = rows[p0]
    # капитал на дату оценки (М§6.1): закрытые кварталы периода p0 целиком и доля e_q квартала q0 —
    # по квартальному профилю CI; дивиденд — вычтен, если конец квартала решения не позже v (М§0.2)
    whole = int(ck["pos"])
    ci_to_v = sum(r0["ci_q"][:whole]) + ((ck["pos"] - whole) * r0["ci_q"][whole] if whole < len(r0["ci_q"]) else 0.0)
    bv_v = bv_prev + ci_to_v - sum(amt for j, amt in r0["div_list"] if ck["t_start"][p0] + 0.25 * (j + 1) <= 0.0)
    # Взносы акционеров (М§6.5; только у книги с включённой докапитализацией — иначе списки взносов пусты и
    # строки ниже ничего не меняют). cut — дисконт размещения d; c_v — взносы кварталов, закрытых к дате
    # оценки: их деньги уже в капитале клетки, а акции за них — у акционеров, которых на дату фактов не было;
    # pv_rec — взносы открытых кварталов, приведённые к дате оценки.
    rule = ctx["recap"]
    cut = rule["d"] if rule is not None else 0.0
    c_v, pv_rec = 0.0, 0.0
    if rule is not None:
        here = sum(amt for j, amt in r0["rec_list"] if ck["t_start"][p0] + 0.25 * (j + 1) <= 0.0)
        c_v = sum(amt for i in range(p0) for _, amt in rows[i]["rec_list"]) + here
        bv_v = bv_v + here
    v_ri, v_ddm, pv_ri = bv_v, 0.0, 0.0
    for i in range(p0, len(periods)):
        row = rows[i]
        te = ck["tau_end"][i]
        d_end = df(te)
        corr = 0.0
        for j, div in row["div_list"]:
            # дивиденд датируется концом квартала решения; решений в году — от нуля до нескольких (М§6.3)
            ta = ck["t_start"][i] + 0.25 * (j + 1)
            if ta > 0.0:
                v_ddm += div * df(ta)
                corr += div * (df(ta) / d_end - 1.0)
        for j, amt in row["rec_list"]:
            # взнос — отрицательное распределение по цене размещения в конце своего квартала; годовой
            # остаточный доход несёт поправку на дату взноса так же, как на дату дивиденда, с обратным знаком
            ta = ck["t_start"][i] + 0.25 * (j + 1)
            if ta > 0.0:
                v_ddm -= amt / (1.0 - cut) * df(ta)
                corr -= amt * (df(ta) / d_end - 1.0)
                pv_rec += amt * df(ta)
        if i == p0:
            k = 1.0 / d_end - 1.0
            ri = row["ci"] - ci_to_v - k * bv_v + corr
        else:
            k = df(ck["tau_end"][i - 1]) / d_end - 1.0
            ri = row["ci"] - k * rows[i - 1]["bv"] + corr
        row["k"], row["ri"] = k, ri
        pv_ri += ri * d_end
    last = rows[-1]
    tl = ck["tau_end"][len(periods) - 1]
    yl = periods[-1]["year"]
    excess = c_terminal_excess(last, c_bnum(B, "valuation.terminal.excess_capital_multiple"))
    x_t = excess["x_t"]
    bv_star = last["bv"] - x_t
    k_t = df(tl) / df(tl + 1.0) - 1.0
    g_raw = c_g_terminal(B, cell["world"])
    g_t = min(g_raw, k_t - 0.0001)
    nci = c_bnum(B, "pnl.nci_share")
    # Доход на избыток — по маржинальной ставке балансирующих статей (М§7). Избыток: пока минимум
    # ликвидности не связывает — смесь доходностей бумаг и ликвидности на конце Q в их долях в LA,
    # дальше — ставка опта. Порог — не запас HLA, а H* = HLA / (1 − m): изъятый капитал уменьшает и LA, и
    # активы, от которых считается минимум. Недостаток — зеркально: добавленный капитал сначала гасит
    # добор опта WT (если минимум связывает), остальное ложится в балансирующие активы по смеси.
    m_liq = c_bnum(B, "volumes.liquid_min_share")
    hla = max(0.0, last["securities"] + last["liquidity"] - m_liq * last["assets"])
    h_star = hla / (1.0 - m_liq)
    wt = max(0.0, last["wholesale_extra"])
    sec = c_bnum(B, "volumes.securities_share_of_liquid")
    y_bal = sec * last["y_sec_end"] + (1.0 - sec) * last["y_liq_end"]
    if x_t > 0.0:
        y_x = y_bal * min(x_t, h_star) + last["c_wh_end"] * max(0.0, x_t - h_star)
    else:
        y_x = -(last["c_wh_end"] * min(-x_t, wt) + y_bal * max(0.0, -x_t - wt))
    t2p, at1r, om = ctx.get("t2p"), ctx.get("at1"), ctx.get("om")
    tax_rule = ctx.get("tax")
    # купон года T + 1 (М§7): купон якоря (слот; у книги с ключом capital.at1_coupon — Cfix + Cflt × (key_W,Q + s_flt))
    # плюс c_α,Q × ΔAT1_Q у книги с ключом доли добавочного капитала, c_α,Q = key_W,Q + s_α — ставка новых выпусков
    # последнего квартала сетки, ΔAT1_Q = AT1_Q − B_α
    cpn_a_t1 = c_anchor_coupon_t1(ctx, cell["world"])
    if at1r is None:
        cpn_t1 = cpn_a_t1
    else:
        cpn_t1 = cpn_a_t1 + (last["key_q"][-1] + at1r["spread"]) * (last["at1"] - at1r["base"])
    sp_t1 = None
    if t2p is not None:
        # надбавка за субординацию (М§7, §4.11): надбавка года L из роста уходит, год T + 1 несёт ту же ставку на сумму
        # сверх базы конца сетки, SP_T+1 = π_T2 × (T2_Q − B_T2)
        sp_t1 = t2p["spread"] * (last["t2"] - t2p["base"])
    term_tax = None
    if tax_rule is None:
        if t2p is None:
            ni_t1 = (last["pbt"] * (1.0 + g_t) - y_x) * (1.0 - last["tau_eff"]) * (1.0 - nci)
        else:
            ni_t1 = ((last["pbt"] + last["sp"]) * (1.0 + g_t) - sp_t1 - y_x) * (1.0 - last["tau_eff"]) * (1.0 - nci)
    else:
        # разрыв налога по правилу (М§7, §4.8): налог года T + 1 — правилом в рублях от рядов конца сетки; льгота — от
        # дохода бумаг года L, выросшего с бизнесом, без бумажной части дохода на избыток A_X (та же часть избытка, что в
        # Y_X); экономия — рублями купона года T + 1
        if t2p is None:
            pbt_x = last["pbt"] * (1.0 + g_t) - y_x
        else:
            pbt_x = (last["pbt"] + last["sp"]) * (1.0 + g_t) - sp_t1 - y_x
        a_x = min(x_t, h_star) if x_t > 0.0 else -max(0.0, -x_t - wt)
        iis_t1 = last["iis"] * (1.0 + g_t) - sec * last["y_sec_end"] * a_x
        tau_l = last["tau_stat"]
        tax_t1 = c_tax_rule(tax_rule, tau_l, pbt_x, iis_t1, c_tax_coupon(tax_rule, tau_l, cpn_t1))
        ni_t1 = (pbt_x - tax_t1) * (1.0 - nci)
        term_tax = {"pbt_x": pbt_x, "a_x": a_x, "iis_t1": iis_t1, "tax_t1": tax_t1, "tau_stat_l": tau_l}
    tau_stat_l = c_traj_at(c_bget(B, "tax.statutory"), yl, A["cpn_quarter"])
    # CI_T+1 (М§7): купон после налога по τ_cpn,L — законная ставка; у книги с ключом tax.structure — купон целиком
    ci_t1 = ni_t1 - cpn_t1 * (1.0 - (tau_stat_l if tax_rule is None else 0.0))
    fade = c_bnum(B, "valuation.terminal.fade")
    fixed = None
    if ctx.get("lam_f") is not None:
        # постоянные в рублях части за концом сетки (М§7, ключ λ_F): блок обеих сторон на величинах конца года L;
        # маржинальная ставка балансирующих статей — опт при доборе опта на конце года, иначе смесь
        y_m = last["c_wh_end"] if wt > 0.0 else y_bal
        if tax_rule is None:
            fixed = c_terminal_fixed_block(c_terminal_fixed_inputs(ctx, cell, last, excess), ctx["lam_f"], y_m,
                                           last["tau_eff"], nci)
        else:
            # у книги с ключом tax.structure — ставкой после налога y^τ_m: бумаги по своей ставке с льготой (М§7)
            y_tau = c_terminal_y_after_tax(tax_rule, last["tau_stat"], wt, last["c_wh_end"], sec, last["y_sec_end"],
                                           last["y_liq_end"])
            fixed = c_terminal_fixed_block(c_terminal_fixed_inputs(ctx, cell, last, excess), ctx["lam_f"], y_m,
                                           0.0, nci, after_tax=y_tau)
    term = c_terminal_lines(x_t, bv_star, ci_t1, k_t, g_t, fade, fixed,
                            where="/".join(str(cell.get(k)) for k in ("world", "regime", "scenario")),
                            om_ann=None if om is None else om["om_ann"])
    roe_t_raw, roe_t, tv_ri, tv_ddm = term["roe_t_raw"], term["roe_t"], term["tv_ri"], term["tv_ddm"]
    d_l = df(tl)
    v_ri = bv_v + pv_ri + d_l * tv_ri
    v_ddm += d_l * tv_ddm
    out = {"bv_v": bv_v, "v_ri": v_ri, "v_ddm": v_ddm, "pv_ri_explicit": pv_ri,
           "x_t": x_t, "hla": hla, "h_star": h_star, "wt": wt, "y_bal": y_bal, "y_x": y_x, "bv_star": bv_star,
           "k_t": k_t, "g_t": g_t, "g_t_capped": g_raw > k_t - 0.0001,
           "roe_t_raw": roe_t_raw, "roe_t": roe_t, "ni_t1": ni_t1, "ci_t1": ci_t1,
           "tv_ri": tv_ri, "tv_ddm": tv_ddm, "terminal_share": d_l * tv_ddm / v_ddm if v_ddm else None,
           "tau_l": tl, "df_l": d_l}
    if fixed is not None:
        # узел блока постоянных частей терминала (М§7): только у книги с ключом λ_F
        out["terminal_fixed"] = {**fixed, "business_capital": term["business_capital"],
                                 "business_ci": term["business_ci"]}
    if at1r is not None or ctx.get("at1c") is not None:
        out["cpn_t1"] = cpn_t1                          # купон года T + 1 (М§7)
    if ctx.get("at1c") is not None:
        out["cpn_anchor_t1"] = cpn_a_t1                 # его купон якоря по ключевой последнего квартала сетки (М§4.9)
    if term_tax is not None:
        out["terminal_tax"] = term_tax                  # строки налога года T + 1 по правилу (М§7, §4.8)
    if t2p is not None:
        out["sp_t1"] = sp_t1                            # надбавка года T + 1 (М§7)
    if om is not None:
        out["om_term"] = term["om_term"]                # прочие движения за концом сетки OM_ann / k_T (М§7)
    if rule is None:
        # норма клетки у книги без докапитализации — сама стоимость (М§6.4): прежняя мера невязки DDM = RI
        out["norm"] = abs(v_ri)
        return out
    # Отрицательные распределения терминала — по цене размещения (М§7): недостаток капитала на T и
    # отрицательная капиталонейтральная выплата — взносы акционеров; они не сальдируются (недостаток вносится
    # на T, выплата идёт с года T + 1), вычет DC_T — один у обеих форм. Оценка — формы М§6.5: взносы закрытых
    # кварталов вычтены из капитала на дату оценки, их цена размывания — без дисконта.
    p_t = term["p_t"]          # у книги с λ_F < 1 — выплата бизнеса и поток стоящей доли одной суммой (М§7)
    need_t = max(-x_t, 0.0) + max(-p_t, 0.0)
    dc_t = cut / (1.0 - cut) * need_t
    pvd_closed, pvd_open, pvd_t = cut / (1.0 - cut) * c_v, cut / (1.0 - cut) * pv_rec, d_l * dc_t
    pvd = pvd_closed + pvd_open + pvd_t
    v_ri = bv_v - c_v + pv_ri + d_l * tv_ri - pvd
    v_ddm = v_ddm - c_v / (1.0 - cut) - d_l * dc_t
    # Норма клетки (М§6.4): цена размывания и недостаток капитала проводят стоимость клетки через ноль, и
    # отношение к ней теряет смысл. Невязка DDM = RI и доля терминала относятся к стоимости, а там, где она ниже
    # капитала на дату оценки на нынешний делитель BV_v − C_v, — к этому капиталу. В клетке со стоимостью не ниже
    # капитала обе меры совпадают с мерами книги без докапитализации.
    own = bv_v - c_v
    share_base = max(v_ddm, own)
    out.update(v_ri=v_ri, v_ddm=v_ddm, v_plain=v_ri + pvd, c_v=c_v, bv_now=own, p_t=p_t, dc_t=dc_t,
               pvd=pvd, pvd_closed=pvd_closed, pvd_open=pvd_open, pvd_terminal=pvd_t,
               pv_rec=c_v + pv_rec, pv_rec_terminal=d_l * need_t, norm=max(abs(v_ri), own),
               terminal_share=d_l * (tv_ddm - dc_t) / share_base if share_base > 0.0 else None)
    return out


def c_ddm_gap(cell: dict) -> float:
    """Относительная невязка V_DDM = V_RI клетки (М§6.4, §14.1): |V_DDM − V_RI| к норме клетки. У книги без
    докапитализации норма — |V_RI| (прежняя мера), у книги с включённой докапитализацией —
    max(|V_RI|, BV_v − C_v): у клетки со стоимостью около нуля невязка остаётся конечной."""
    gap = abs(cell["v_ddm"] - cell["v_ri"])
    if not cell["norm"]:
        return 0.0 if gap == 0.0 else math.inf
    return gap / cell["norm"]


def c_share_path(flows: list[dict], tail: float, cut: float, n_div: float) -> list[dict]:
    """Путь числа акций клетки (М§6.6) — для печати, на оценку не влияет.

    flows — кварталы сетки по порядку: {div, rec, df}; div — дивиденд квартала, если квартал открыт на дату
    оценки (иначе ноль: он не входит ни в один поток клетки), rec — взнос, df — DF̃: дисконт от даты оценки, у
    закрытого квартала — единица. tail — приведённый терминал формы DDM за вычетом цены размывания терминала.
    В квартале со взносом W — стоимость всех акций сразу после взноса по будущим чистым распределениям клетки;
    новые акции продаются по (1 − d) от стоимости акции после выпуска, поэтому делитель растёт в
    W / (W − Rec / (1 − d)) раз. Если стоимость акций до взноса не положительна, путь оборван: с этого квартала
    доля нынешних акций — ноль, числа акций нет. Строка квартала: акции до взноса квартала и после него, доля
    нынешних акций, W и стоимость до взноса (в кварталах без взноса — None). Нулевая строка — дата фактов: W_0
    равно оценке клетки в форме DDM."""
    ahead, after = tail, [0.0] * len(flows)
    for q in range(len(flows) - 1, -1, -1):
        after[q] = ahead                                # чистые распределения кварталов позже q и терминал
        ahead += (flows[q]["div"] - flows[q]["rec"] / (1.0 - cut)) * flows[q]["df"]
    out, shares = [{"before": n_div, "shares": n_div, "stake": 1.0, "worth": ahead, "pre_money": ahead}], n_div
    for q, f in enumerate(flows):
        before, worth, old = shares, None, None
        if f["rec"] > 0.0 and shares is not None:
            worth = after[q] / f["df"]
            old = worth - f["rec"] / (1.0 - cut)
            shares = shares * worth / old if old > 0.0 else None
        out.append({"before": before, "shares": shares, "stake": 0.0 if shares is None else n_div / shares,
                    "worth": worth, "pre_money": old})
    return out


def _c_cell_shares(ctx: dict, cell: dict) -> None:
    """Путь числа акций клетки по её годовым строкам и DPS на акции своего года (М§6.6): дивиденд решения
    модели квартала собрания — на акции в обращении клетки, существующие перед взносом этого квартала,
    N_out + (N − N_base): акции якоря, акции поправки делителя (N_div − N_base — объявленный выпуск с известной
    ценой: дивиденд будущих решений они получают наравне с прочими) и акции взносов; при оборванном к этому
    кварталу пути — ноль. DPS решения записью реестра — число записи: дивиденд объявлен на акцию. Годовые ряды —
    доля нынешних акций и делитель клетки на конец года; флаги — «взнос» (хотя бы один взнос больше нуля) и
    «взнос при дивиденде решения модели»; сумма «дивиденд в пределах взноса» — по решениям со взносом:
    меньшее из дивиденда модели решения и взноса, с дисконтом квартала взноса (у закрытого — единица, М§14.5)."""
    A, ck, periods, rule = ctx["A"], ctx["clock"], ctx["periods"], ctx["recap"]
    df = ctx["disc"][cell["world"]]
    flows, ends, at = [], [], {}
    for i, (p, row) in enumerate(zip(periods, cell["rows"])):
        divs, recs = dict(row["div_list"]), dict(row["rec_list"])
        for j in range(p["n"]):
            ta = ck["t_start"][i] + 0.25 * (j + 1) if i >= ck["p0"] else 0.0
            live = i >= ck["p0"] and ta > 0.0
            flows.append({"div": divs.get(j, 0.0) if live else 0.0, "rec": recs.get(j, 0.0),
                          "df": df(ta) if live else 1.0})
            at[(i, j)] = len(flows)                     # строка пути квартала: нулевая строка — дата фактов
        ends.append(len(flows))
    path = c_share_path(flows, cell["df_l"] * (cell["tv_ddm"] - cell["dc_t"]), rule["d"], A["N_div"])
    cell["stake"] = [path[k]["stake"] for k in ends]
    cell["shares"] = [path[k]["shares"] for k in ends]
    cell["share_path"] = path
    agm = int(c_bnum(ctx["B"], "dividends.calendar.agm_quarter"))
    base = A.get("N_base", A["N_div"])                  # без поправки делителя N_base = N_div — прежняя строка
    for i, p in enumerate(periods):
        dec = cell["decisions"].get(p["year"] - 1)
        if dec is None or agm not in p["quarters"]:
            continue
        before = path[at[(i, p["quarters"].index(agm))]]["before"]
        dec["dps_anchor_shares"] = dec["dps"]
        dec["shares_out"] = None if before is None else A["N_out"] + (before - base)
        if dec.get("dps_register") is not None:
            dec["dps"] = dec["dps_register"]            # запись реестра: число записи, на акции клетки не делится
        else:
            dec["dps"] = 0.0 if before is None else dec["div"] * 1000.0 / dec["shares_out"]
    made = cell["recaps"].values()
    cell["rec_years"] = [row["rec"] for row in cell["rows"]]
    cell["recapitalization"] = any(x["rec"] > 0.0 for x in made)
    cell["recap_with_dividend"] = any(x["rec"] > 0.0 and x["div"] > 0.0 and x["div_kind"] == "policy" for x in made)
    cell["div_within_recap"] = sum(min(x["div"], x["rec"]) * flows[x["q"] - 1]["df"] for x in made
                                   if x["rec"] > 0.0 and x["div"] > 0.0 and x["div_kind"] == "policy")
    cell["path_broken"] = any(x["shares"] is None for x in path)


# ============================================================================ мост до цены (М§8.1)

def _c_register_amounts(ctx: dict) -> list[tuple[float, dt.date, dt.date | None]]:
    """Объявленные дивиденды реестра: (сумма DPS × N_out / 1000, дата вычета из BV модели, экс-дата).
    Вычет из BV модели — дата фактов (дивиденд вычтен в якоре) или конец квартала ГОСА клетки (М§8.1)."""
    B, A = ctx["B"], ctx["A"]
    facts_date = _c_as_date(c_bget(B, "meta.facts_date"))
    out = []
    if ctx["quarterly"]:
        # строка на запись — на квартал прибыли (М§8.1): вычет из BV модели — дата фактов у закрытого
        # квартала, иначе конец квартала клетки q_cell(period)
        cal = ctx["divcal"]
        for k, rec in sorted(cal["register"].items()):
            cell_end = c_q_last_day(*c_qper(ctx["anchor"], rec["q_cell"]))
            out.append((rec["dps"] * A["N_out"] / 1000.0, facts_date if k <= cal["p_last"] else cell_end, rec["ex"]))
        return out
    agm = int(c_bnum(B, "dividends.calendar.agm_quarter"))
    for rec in _c_register_binding(ctx):
        agm_end = c_q_last_day(int(_c_nodeval(rec["year"])) + 1, agm)
        ex = rec.get("ex_date")
        out.append((float(_c_nodeval(rec["dps"])) * A["N_out"] / 1000.0,
                    facts_date if agm_end <= facts_date else agm_end,
                    _c_as_date(_c_nodeval(ex)) if ex else None))
    return out


def c_bridge_register(ctx: dict) -> float:
    """B(v): объявленные дивиденды реестра от модельного вычета из BV до экс-даты, млрд ₽."""
    v = ctx["clock"]["v"]
    return sum(amount * ((1.0 if deduct <= v else 0.0) - (1.0 if ex is not None and ex <= v else 0.0))
               for amount, deduct, ex in _c_register_amounts(ctx))


def c_pending_register(ctx: dict) -> float:
    """D_pend (М§8.2): объявленные дивиденды, которые клетки ещё не вычли из BV (v раньше вычета) —
    они внутри V0 и дисконта за управление не несут; номинал, как в мосте, млрд ₽."""
    v = ctx["clock"]["v"]
    return sum(amount for amount, deduct, _ in _c_register_amounts(ctx) if v < deduct)


# ============================================================================ A-P2u (М§12)

def _c_qindex(y: int, q: int) -> int:
    return y * QY + (q - 1)


def c_expectations_ctl(ctx: dict, quarters) -> dict:
    """Ожидания режимов μ_x,r(q) (М§12): среднее слоя «свой взгляд» (веса миров × P(s | r)) по
    клеткам режима без отклонений A-P2u. CoR — путь режима через мост плюс κ-добавка мира
    (поквартально, точно); ЧПМ — ЧПМ движка клетки с ближним сдвигом и сдвигом режима из
    предварительного прохода клеток до года последнего квартала (годовой шаг: ЧПМ квартала внутри
    периода — ставки квартала при структуре баланса периода). Ключ результата — (x, r, год, квартал)."""
    B = ctx["B"]
    quarters = sorted({(int(y), int(q)) for y, q in quarters})
    where = {p["year"]: p["quarters"] for p in ctx["periods"]}
    for y, q in quarters:
        if q not in where.get(y, ()):
            raise ControlInputError(f"наблюдение A-P2u {y}Q{q} вне прогнозных кварталов сетки")
    pw = {w: float(c_bget(B, "joint.world_prob").get(w, 0.0)) for w in ctx["worlds"]}
    prs = c_bget(B, "joint.reg_prob_given_regime")
    regimes, scen = list(c_bget(B, "regimes.ids")), list(c_bget(B, "capital.reg_scenarios.ids"))
    lag, kap = int(c_bnum(B, "credit.real_rate_lag_q")), c_bnum(B, "credit.kappa")
    saved, ctx["dev"] = ctx["dev"], {}                  # предварительный проход — без отклонений (δ ≡ 0)
    try:
        nim0 = {}
        for w in (w for w in ctx["worlds"] if pw[w]):
            for r in regimes:
                for s in scen:
                    rows = _c_cell_path(ctx, {"world": w, "regime": r, "scenario": s},
                                        upto_year=quarters[-1][0])["rows"]
                    for p, row in zip(ctx["periods"], rows):
                        for j, q in enumerate(p["quarters"]):
                            nim0[(w, r, s, p["year"], q)] = row["nim_q"][j]
    finally:
        ctx["dev"] = saved
    mu = {}
    for y, q in quarters:
        for r in regimes:
            mu[("cor", r, y, q)] = sum(pw[w] * (c_cor_path_engine(ctx, r, y, q) + kap * _c_kappa_gap(B, w, y, q, lag))
                                       for w in pw if pw[w])
            mu[("nim", r, y, q)] = sum(pw[w] * float(prs[r][s]) * nim0[(w, r, s, y, q)]
                                       for w in pw if pw[w] for s in scen)
    return mu


def _c_frozen_mu(ctx: dict, o: dict) -> dict:
    """Замороженные ожидания режимов наблюдения квартала не позже якоря (М§12): словари mu_cor,
    mu_nim {режим: μ} в базисе записи — через тот же мост, что и само наблюдение. Нет μ наблюдённой
    величины — громкий отказ."""
    A = ctx["A"]
    y, q = c_per_parse(o["period"])
    out = {}
    for x in ("cor", "nim"):
        if o.get(x) is None:
            continue
        table = o.get(f"mu_{x}")
        for r in c_bget(ctx["B"], "regimes.ids"):
            if not isinstance(table, dict) or table.get(r) is None:
                raise ControlInputError(f"наблюдение A-P2u {o['period']} (квартал не позже якоря) без mu_{x}.{r}")
            val = float(table[r])
            out[(x, r, y, q)] = c_to_engine(A, x, val) if o.get("basis", "engine") == "mgmt" else val
    return out


def c_regime_update_ctl(ctx: dict) -> None:
    """Вероятности режимов после квартальных наблюдений CoR и ЧПМ и затухающие отклонения (М§12).
    Априорные стационарны, память — окно: фильтр стартует с базовых вероятностей книги и пустого
    состояния и проходит только последние joint.regime_update.window_obs наблюдений."""
    B, A = ctx["B"], ctx["A"]
    ru = "joint.regime_update"
    window = c_bget(B, f"{ru}.window_obs")
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ControlInputError("joint.regime_update.window_obs — целое ≥ 1 (М прил. A)")
    floor_share = c_bnum(B, f"{ru}.floor_share")
    if not 0.0 <= floor_share <= 1.0:
        raise ControlInputError("joint.regime_update.floor_share вне [0; 1] (М прил. A)")
    obs = sorted(c_bget(B, f"{ru}.observations") or [], key=lambda o: c_per_parse(o["period"]))[-window:]
    prior = {r: float(v) for r, v in c_bget(B, "joint.regime_prob").items()}
    ctx["posterior"], ctx["dev"], ctx["mu"], ctx["updates"] = dict(prior), {}, {}, []
    if not obs:
        return
    # ожидания режимов: прогнозные кварталы — предварительный проход клеток; кварталы не позже якоря —
    # замороженные μ записи (их пишет перезаякоривание)
    ahead = [c_per_parse(o["period"]) for o in obs if c_per_parse(o["period"]) > ctx["anchor"]]
    mus = c_expectations_ctl(ctx, ahead) if ahead else {}
    for o in obs:
        if c_per_parse(o["period"]) <= ctx["anchor"]:
            mus.update(_c_frozen_mu(ctx, o))
    ctx["mu"] = mus
    sig = {x: c_bnum(B, f"{ru}.observables.{x}.sigma_pp") for x in ("cor", "nim")}
    rho = {x: c_bnum(B, f"{ru}.observables.{x}.rho_q") for x in ("cor", "nim")}
    cap = c_bnum(B, f"{ru}.max_shift_pp")
    floors = {r: floor_share * prior[r] for r in prior}
    state = {(x, r): None for x in ("cor", "nim") for r in prior}
    trail = {key: [] for key in state}
    post = dict(prior)
    for o in obs:
        y, q = c_per_parse(o["period"])
        qi = _c_qindex(y, q)
        like = {r: 1.0 for r in prior}
        for x in ("cor", "nim"):
            val = o.get(x)
            if val is None:
                continue
            val = float(val)
            if o.get("basis", "engine") == "mgmt":
                val = c_to_engine(A, x, val)
            se = float(o.get(f"se_{x}") or 0.0)
            for r in prior:
                dev = val - mus[(x, r, y, q)]
                prev = state[(x, r)]
                if prev is None:
                    k, err, P = 0, dev, sig[x] ** 2
                    m_prev = 0.0
                else:
                    k = qi - prev["qi"]
                    rk = rho[x] ** k
                    err = dev - rk * prev["m"]
                    P = sig[x] ** 2 * (1.0 - rho[x] ** (2 * k)) + rho[x] ** (2 * k) * prev["v"]
                    m_prev = rk * prev["m"]
                like[r] *= math.exp(-0.5 * err * err / (P + se * se))
                if se == 0.0:
                    m_new, v_new = dev, 0.0
                else:
                    wk = P / (P + se * se)
                    m_new, v_new = m_prev + wk * err, (1.0 - wk) * P
                state[(x, r)] = {"qi": qi, "m": m_new, "v": v_new, "y": y, "q": q}
                trail[(x, r)].append((y, q, m_new))
        tot = sum(post[r] * like[r] for r in post)
        raw = {r: post[r] * like[r] / tot for r in post}
        clipped = {r: post[r] + max(-cap, min(cap, raw[r] - post[r])) for r in post}
        z = sum(clipped.values())
        clipped = {r: c / z for r, c in clipped.items()}
        worst = max(abs(clipped[r] - post[r]) for r in post)
        if worst > cap + 1e-12:
            clipped = {r: post[r] + cap / worst * (clipped[r] - post[r]) for r in post}
        post = c_floor_probabilities(clipped, floors)       # пол — вслед за пределом сдвига
        ctx["updates"].append({"period": o["period"], "posterior": dict(post)})
    ctx["posterior"] = post
    for r in prior:
        ctx["dev"][r] = {}
        for x in ("cor", "nim"):
            stt = state[(x, r)]
            if stt is not None:
                ctx["dev"][r][x] = {"y": stt["y"], "q": stt["q"], "rho": rho[x], "m": stt["m"],
                                    "trail": trail[(x, r)]}


def c_floor_probabilities(prob: dict, floors: dict) -> dict:
    """Пол вероятности режима (М§12): режим ниже своего пола ставится на пол, остальные умножаются на
    общий множитель так, чтобы сумма была 1; если после этого ещё какой-то режим оказался ниже пола —
    он тоже ставится на пол, и шаг повторяется (режимов конечное число, сумма полов ≤ 1)."""
    out = dict(prob)
    pinned: set = set()
    while True:
        low = {r for r in out if r not in pinned and out[r] < floors[r]}
        if not low:
            return out
        pinned |= low
        free = [r for r in out if r not in pinned]
        room = 1.0 - sum(floors[r] for r in pinned)
        mass = sum(prob[r] for r in free)
        for r in pinned:
            out[r] = floors[r]
        for r in free:
            out[r] = prob[r] * room / mass if mass > 0.0 else 0.0


# ============================================================================ сетка, слои, точка (М§3, §8–§9)

def c_layer_weights(B: dict) -> dict[str, dict[str, float]]:
    return {"analytical": {w: float(v) for w, v in c_bget(B, "joint.world_prob").items()},
            "market_implied": {w: float(v) for w, v in c_bget(B, "joint.world_prob_market_implied").items()},
            "macro_neutral": {c_bget(B, "joint.macro_neutral_world"): 1.0}}


def c_price_of(v0: float, bridge: float, gov: float, n_div: float, pending: float = 0.0) -> float:
    """Цена (М§8.2): дисконт за управление — к V0 без объявленного дивиденда: ни мост B(v), ни
    сумма D_pend (объявлено, но ещё не вычтено из BV модели) дисконта не несут. Делится на N_div
    (М§8.4); суммы моста и D_pend — на акции в обращении, их делитель не трогает."""
    own = v0 - pending
    if own > 0.0:
        return (own * (1.0 - gov) + pending + bridge) * 1000.0 / n_div
    return (v0 + bridge) * 1000.0 / n_div


def c_floor_value(v: float, pending: float, low: float) -> float:
    """Стоимость клетки в цене (М§8.2): V^F = max(V − D_pend, F) + D_pend. Пол действует на стоимость без
    объявленного, но ещё не вычтенного клетками дивиденда: он — обязательство, и акционер получит его и в
    исходе, где остальное ничего не стоит."""
    return max(v - pending, low) + pending


def c_cell_worth(cell: dict) -> float:
    """Что клетка весит в смеси и в цене (М§8.2): у книги с ключом пола — V^F_c, иначе оценка клетки V_c."""
    return cell["v_floor"] if "v_floor" in cell else cell["v_ri"]


def c_control_run(book: dict | None = None, facts: dict | None = None, *, valuation_date=None,
                  base_book: dict | None = None) -> dict:
    """Вся контрольная модель: передача, клетки, слои, низ/верх/точка при центральных значениях. Клетка — на
    каждую тройку перечней книги worlds.ids × regimes.ids × capital.reg_scenarios.ids, сколько бы сценариев
    требования та ни назвала (М§3), и клетка нулевой вероятности — тоже: её вес в смесях и массах — ноль."""
    book = book if book is not None else c_book_machine()
    facts = facts if facts is not None else c_facts_bundle()
    ctx = c_control_context(book, facts, valuation_date=valuation_date, base_book=base_book)
    B, A = ctx["B"], ctx["A"]
    if c_bget(B, "dividends.policy.base") != "ifrs_ni_shareholders":
        raise ControlUnsupported("база дивиденда кроме ifrs_ni_shareholders не реализована")
    worlds = ctx["worlds"]
    regimes = list(c_bget(B, "regimes.ids"))
    scen = list(c_bget(B, "capital.reg_scenarios.ids"))
    cells = [c_cell_annual(ctx, w, r, s) for w in worlds for r in regimes for s in scen]
    recap, floor = ctx["recap"], ctx["floor"]
    if floor is not None:
        # пол стоимости клетки (М§8.2): по клетке, до смеси слоя, до дисконта за управление и моста
        for c in cells:
            c["v_floor"] = c_floor_value(c["v_ri"], ctx["pending_amount"], floor)
            c["floored"] = c["v_ri"] - ctx["pending_amount"] < floor
    lw = c_layer_weights(B)
    prs = c_bget(B, "joint.reg_prob_given_regime")
    layers = {}
    for name in LAYERS:
        P = {}
        for c in cells:
            P[(c["world"], c["regime"], c["scenario"])] = (
                lw[name].get(c["world"], 0.0) * ctx["posterior"][c["regime"]]
                * float(prs[c["regime"]][c["scenario"]]))
        if floor is None:
            v0 = sum(P[(c["world"], c["regime"], c["scenario"])] * c["v_ri"] for c in cells)
        else:
            v0 = sum(P[(c["world"], c["regime"], c["scenario"])] * c["v_floor"] for c in cells)
        if recap is None:
            bv = sum(P[(c["world"], c["regime"], c["scenario"])] * c["bv_v"] for c in cells)
        else:
            # капитал на дату оценки на нынешний делитель — без взносов закрытых кварталов (М§6.5, §8.3)
            bv = sum(P[(c["world"], c["regime"], c["scenario"])] * c["bv_now"] for c in cells)
        layers[name] = {"prob_sum": sum(P.values()), "v0": v0, "bv_v": bv,
                        "price": c_price_of(v0, ctx["bridge_amount"], ctx["gov"], A["N_div"],
                                            ctx["pending_amount"]),
                        "bv_per_share": bv * 1000.0 / A["N_div"],
                        "pb": v0 / bv if bv else None}
        if floor is not None:
            layers[name].update(c_floor_summary(cells, P))
        if recap is not None:
            layers[name].update(c_recap_totals(cells, P))
    lam = c_bnum(B, "joint.own_macro_confidence")
    low, high = layers["macro_neutral"]["price"], layers["analytical"]["price"]
    for c in cells:
        if floor is None and recap is None:
            c["price"] = c_price_of(c["v_ri"], ctx["bridge_amount"], ctx["gov"], A["N_div"], ctx["pending_amount"])
            c["pb"] = c["v_ri"] / c["bv_v"]
        else:
            c["price"] = c_price_of(c_cell_worth(c), ctx["bridge_amount"], ctx["gov"], A["N_div"],
                                    ctx["pending_amount"])
            c["pb"] = c_cell_worth(c) / c.get("bv_now", c["bv_v"])
    res = {"ctx": ctx, "transmission": ctx["tr"], "cells": cells, "layers": layers,
            "low": low, "high": high, "lam": lam, "point": low + lam * (high - low),
            "bridge_amount": ctx["bridge_amount"], "pending_amount": ctx["pending_amount"],
            "governance": ctx["gov"], "shock_year": ctx["shock_year"],
            "posterior": ctx["posterior"], "derived": ctx["derived"],
            "shares_out": A["N_out"], "divisor": A["N_div"], "quarterly": ctx["quarterly"],
            "growth_rule": ctx["growth"], "history_test": c_history_kind(B),
            "dps_history": c_dps_history_ctl(B, facts),
            "years": [p["year"] for p in ctx["periods"]]}
    res["central"] = c_central_cell(res)
    if recap is not None:
        res["recap_rule"] = dict(recap)
        res["recapitalization"] = c_recap_summary(res)
    if floor is not None:
        res["cell_floor"] = c_floor_report(res)
    if ctx["ded"] is not None:
        res["deduction_shares"] = c_deduction_report(res)
    if ctx["rub"] is not None or ctx["oaf_path"] is not None or ctx["lam_f"] is not None:
        res["fixed_parts"] = c_fixed_report(res)
    if ctx["t2_from"] is not None:
        res["t2_share"] = c_t2_report(res)
    if ctx["at1"] is not None or ctx["t2p"] is not None or ctx["om"] is not None:
        res["pass8"] = c_pass8_report(res)
    if ctx["tax"] is not None or ctx["at1c"] is not None:
        res["pass9"] = c_pass9_report(res)
    return res


def c_pass8_report(res: dict) -> dict:
    """Узел восьмого прохода (М§4.4, §4.9–§4.11, §7; только у книги с ключами): у доли добавочного капитала — квартал
    ключа, доля якоря AT1_0 / RWA_0, доли клеток (наименьшая, наибольшая, под вероятностями смеси точки), AT1 конца сетки
    и купон года T + 1 под смесью точки, доля центральной клетки; у надбавки — надбавка последнего года и года T + 1 под
    смесью точки; у прочих движений — OM_LT, OM_ann и слагаемое OM_ann / k_T под смесью точки."""
    ctx, weight = res["ctx"], c_point_mass(res)
    key = lambda c: (c["world"], c["regime"], c["scenario"])                            # noqa: E731
    out = {}
    if ctx["at1"] is not None:
        rule = ctx["at1"]
        yf, hf = c_qper(ctx["anchor"], rule["from"])
        shares = {"/".join(key(c)): c["rows"][-1]["a1s"] for c in res["cells"]}
        out["at1"] = {"from": f"{yf}Q{hf}", "q_alpha": rule["from"], "spread": rule["spread"], "base": rule["base"],
                      "anchor_share": c_at1_share_of(ctx, ctx["rwa0"]), "cells": shares,
                      "share_min": min(shares.values()), "share_max": max(shares.values()),
                      "share_point": sum(weight[key(c)] * c["rows"][-1]["a1s"] for c in res["cells"]),
                      "at1_end_point": sum(weight[key(c)] * c["rows"][-1]["at1"] for c in res["cells"]),
                      "coupon_t1_point": sum(weight[key(c)] * c["cpn_t1"] for c in res["cells"]),
                      "coupon_new_last_point": sum(weight[key(c)] * c["rows"][-1]["cpn_new"] for c in res["cells"]),
                      "modal_share": c_cell_of(res, *res["central"]["cell"])["rows"][-1]["a1s"]}
    if ctx["t2p"] is not None:
        out["t2_premium"] = {"spread": ctx["t2p"]["spread"], "base": ctx["t2p"]["base"],
                             "sp_last_point": sum(weight[key(c)] * c["rows"][-1]["sp"] for c in res["cells"]),
                             "sp_t1_point": sum(weight[key(c)] * c["sp_t1"] for c in res["cells"])}
    if ctx["om"] is not None:
        out["other_movements"] = {**ctx["om"],
                                  "om_term_point": sum(weight[key(c)] * c["om_term"] for c in res["cells"])}
    return out


def c_pass9_report(res: dict) -> dict:
    """Узел девятого прохода (М§4.8, §4.9, §7; только у книги с ключами): у разрыва налога по правилу — поля ключа,
    эффективная ставка года Σ налога / Σ PBT по мирам (веса режимов и сценариев прогона, как у цены мира) и под смесью
    точки, экономия купона и процентный доход книги бумаг года под смесью точки, налог года T + 1 под смесью точки; у купона
    якоря по ставке своего мира — поля ключа, купон якоря года по мирам (он зависит только от пути ключевой мира) и купон
    якоря года T + 1 по мирам."""
    ctx, weight = res["ctx"], c_point_mass(res)
    key = lambda c: (c["world"], c["regime"], c["scenario"])                            # noqa: E731
    prs = c_bget(ctx["B"], "joint.reg_prob_given_regime")
    inside = {key(c): res["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]]) for c in res["cells"]}
    years, out = res["years"], {}

    def c_ratio(cells, mass, i):
        tax = sum(mass[key(c)] * c["rows"][i]["tax"] for c in cells)
        pbt = sum(mass[key(c)] * c["rows"][i]["pbt"] for c in cells)
        return tax / pbt if pbt else None

    if ctx["tax"] is not None:
        out["tax"] = {**ctx["tax"],
                      "etr_point": {y: c_ratio(res["cells"], weight, i) for i, y in enumerate(years)},
                      "etr_by_world": {w: {y: c_ratio([c for c in res["cells"] if c["world"] == w], inside, i)
                                           for i, y in enumerate(years)} for w in ctx["worlds"]},
                      "saving_point": {y: sum(weight[key(c)] * c["rows"][i]["tax_coupon"] for c in res["cells"])
                                       for i, y in enumerate(years)},
                      "iis_point": {y: sum(weight[key(c)] * c["rows"][i]["iis"] for c in res["cells"])
                                    for i, y in enumerate(years)},
                      "tax_t1_point": sum(weight[key(c)] * c["terminal_tax"]["tax_t1"] for c in res["cells"]),
                      "pbt_t1_point": sum(weight[key(c)] * c["terminal_tax"]["pbt_x"] for c in res["cells"])}
    if ctx["at1c"] is not None:
        first = {}
        for c in res["cells"]:
            first.setdefault(c["world"], c)
        out["at1_coupon"] = {**ctx["at1c"],
                             "coupon_by_world": {w: {y: c["rows"][i]["cpn_anchor"] for i, y in enumerate(years)}
                                                 for w, c in first.items()},
                             "coupon_t1_by_world": {w: c["cpn_anchor_t1"] for w, c in first.items()},
                             "coupon_t1_point": sum(weight[key(c)] * c["cpn_anchor_t1"] for c in res["cells"])}
    return out


def c_t2_report(res: dict) -> dict:
    """Узел седьмого прохода (М§4.11, §7; только у книги с включённым ключом capital.n20.t2_share): квартал ключа и его
    номер q_χ, доля якоря T2_0 / RWA_0, доли клеток χ_c — по клеткам, наименьшая, наибольшая и под вероятностями смеси
    точки; инструменты конца сетки T2_Q под смесью точки против значения траектории в последнем квартале сетки; у
    центральной клетки — её доля и доля, которую держала бы траектория на её RWA конца сетки."""
    ctx, weight = res["ctx"], c_point_mass(res)
    key = lambda c: (c["world"], c["regime"], c["scenario"])                            # noqa: E731
    q_chi = ctx["t2_from"]
    yf, hf = c_qper(ctx["anchor"], q_chi)
    period = ctx["periods"][-1]
    traj_end = c_traj_at(c_bget(ctx["B"], T2_TRAJ), period["year"], period["quarters"][-1])
    shares = {"/".join(key(c)): c["rows"][-1]["t2s"] for c in res["cells"]}
    modal = c_cell_of(res, *res["central"]["cell"])
    return {"from": f"{yf}Q{hf}", "q_chi": q_chi, "anchor_share": c_t2_share_of(ctx, *ctx["anchor"], ctx["rwa0"]),
            "cells": shares, "share_min": min(shares.values()), "share_max": max(shares.values()),
            "share_point": sum(weight[key(c)] * c["rows"][-1]["t2s"] for c in res["cells"]),
            "t2_end_point": sum(weight[key(c)] * c["rows"][-1]["t2"] for c in res["cells"]),
            "t2_trajectory_end": traj_end, "modal": res["central"]["label"],
            "modal_share": modal["rows"][-1]["t2s"], "modal_t2_end": modal["rows"][-1]["t2"],
            "modal_trajectory_share_end": traj_end / modal["rows"][-1]["rwa"]}


def c_fixed_report(res: dict) -> dict:
    """Узел пятого прохода (М§4.3, §4.11, §7; только у книги с ключами): под вероятностями смеси точки — рубли
    сценария в вычетах на конце сетки, постоянная часть прочих активов конца сетки и её приращение к якорю; у книги с
    ключом λ_F — ожидание блока постоянных частей терминала (F_A, R_F, C, F_K, D_F, I_F, y_m) и массы клеток: где
    связывает Н20.0, где бизнес без стоящей доли выше k_T, где на конце сетки есть добор опта. Мост Н20.0 смеси до
    конца года даты оценки — у книги с рублями сценария (в строке вычетов — их изменение от якоря)."""
    ctx, weight = res["ctx"], c_point_mass(res)
    period = ctx["periods"][-1]
    yl, hl = period["year"], period["quarters"][-1]
    key = lambda c: (c["world"], c["regime"], c["scenario"])                            # noqa: E731
    out = {"year": yl}
    if ctx["rub"] is not None:
        out["rub_end"] = {name: sum(weight[key(c)] * c_rub_at(ctx, c["scenario"], yl, hl)[pos] for c in res["cells"])
                          for pos, name in enumerate((NORM_TOTAL, NORM_BASE))}
        out["bridge"] = c_capital_bridge(res)
    if ctx["oaf_path"] is not None:
        d_q = c_oaf_change(ctx, yl, hl)
        out.update(oaf_anchor=ctx["oaf"], oaf_change_end=d_q, oaf_end=ctx["oaf"] + d_q,
                   oaf_change_density=ctx["oaf_path"]["density"])
    if ctx["lam_f"] is not None:
        node = {"lam_f": ctx["lam_f"]}
        for field in ("f_a", "r_f", "c", "f_k", "d_f", "i_f", "y_m", "business_capital"):
            node[field] = sum(weight[key(c)] * c["terminal_fixed"][field] for c in res["cells"])
        node["binding_n20_mass"] = sum(weight[key(c)] for c in res["cells"]
                                       if c["terminal_fixed"]["binding"] == NORM_TOTAL)
        node["business_above_k_mass"] = sum(weight[key(c)] for c in res["cells"] if c["roe_t_raw"] > c["k_t"])
        node["wholesale_mass"] = sum(weight[key(c)] for c in res["cells"] if c["wt"] > 0.0)
        out["terminal"] = node
    return out


def c_floor_summary(cells: list[dict], P: dict) -> dict:
    """Пол клетки в слое (М§8.2): масса клеток на полу (V_c − D_pend < F) под весами слоя и поправка пола
    Φ_L = Σ P_L(c) × (V^F_c − V_c) ≥ 0 — строка разложения V0 слоя."""
    key = lambda c: (c["world"], c["regime"], c["scenario"])                            # noqa: E731
    return {"floored_mass": sum(P[key(c)] for c in cells if c["floored"]),
            "floor_shift": sum(P[key(c)] * (c["v_floor"] - c["v_ri"]) for c in cells),
            "v0_plain": sum(P[key(c)] * c["v_ri"] for c in cells)}


def c_recap_totals(cells: list[dict], P: dict) -> dict:
    """Взносы акционеров под весами P (М§10, §14.5): приведённые суммы взносов явного участка и терминала (PVR,
    PVRT), цена размывания Σ P(c) × PVD_c, приведённая сумма «дивиденд в пределах взноса», масса клеток со
    взносом, со взносом при дивиденде решения модели и с оборванным путём акций."""
    key = lambda c: (c["world"], c["regime"], c["scenario"])                            # noqa: E731
    return {"pv_rec": sum(P[key(c)] * c["pv_rec"] for c in cells),
            "pv_rec_terminal": sum(P[key(c)] * c["pv_rec_terminal"] for c in cells),
            "pvd": sum(P[key(c)] * c["pvd"] for c in cells),
            "div_within_recap": sum(P[key(c)] * c["div_within_recap"] for c in cells),
            "recap_mass": sum(P[key(c)] for c in cells if c["recapitalization"]),
            "recap_with_dividend_mass": sum(P[key(c)] for c in cells if c["recap_with_dividend"]),
            "path_broken_mass": sum(P[key(c)] for c in cells if c["path_broken"])}


def c_recap_summary(res: dict) -> dict:
    """Сводка взносов акционеров прогона (М§14.5): по годам сетки под вероятностями смеси точки и рядом —
    модальная клетка: ожидаемый взнос года, масса клеток со взносом в этом году, ожидаемая доля нынешних акций
    и акции смеси на конец года, DPS смеси на акции своего года (М§6.6); по смеси точки — приведённые суммы
    взносов и цена размывания в млрд ₽ и на акцию делителя (до дисконта за управление и пола)."""
    cells, weight, n_div = res["cells"], c_point_mass(res), res["divisor"]
    modal = c_cell_of(res, *res["central"]["cell"])
    key = lambda c: (c["world"], c["regime"], c["scenario"])                            # noqa: E731
    years = []
    for i, y in enumerate(res["years"]):
        stake = sum(weight[key(c)] * c["stake"][i] for c in cells)
        dps = [(weight[key(c)], c["decisions"].get(y - 1)) for c in cells]
        years.append({"year": y, "rec": sum(weight[key(c)] * c["rows"][i]["rec"] for c in cells),
                      "rec_mass": sum(weight[key(c)] for c in cells if c["rows"][i]["rec"] > 0.0),
                      "stake": stake, "shares": n_div / stake if stake > 0.0 else None,
                      "dps": sum(k * d["dps"] for k, d in dps if d is not None) if any(d for _, d in dps) else None,
                      "modal_rec": modal["rows"][i]["rec"], "modal_stake": modal["stake"][i],
                      "modal_shares": modal["shares"][i]})
    point = c_recap_totals(cells, weight)
    point["pvd_per_share"] = point["pvd"] * 1000.0 / n_div
    return {"years": years, "point": point, "modal": res["central"]["label"]}


def c_floor_report(res: dict) -> dict:
    """Узел пола клетки (М§14.5): значение пола, масса клеток на полу и поправка пола под вероятностями смеси
    точки, точка без пола и сдвиг точки от пола в рублях на акцию."""
    ctx, layers = res["ctx"], res["layers"]
    plain = {name: c_price_of(layers[name]["v0_plain"], ctx["bridge_amount"], ctx["gov"], res["divisor"],
                              ctx["pending_amount"]) for name in (LAYER_MARKET, LAYER_OWN)}
    point_plain = plain[LAYER_MARKET] + res["lam"] * (plain[LAYER_OWN] - plain[LAYER_MARKET])
    out = c_floor_summary(res["cells"], c_point_mass(res))
    out.update(floor=ctx["floor"], point_plain=point_plain, point_shift=res["point"] - point_plain)
    return out


def c_bridge_lines(pairs: list) -> dict:
    """Мост норматива Н20.0 смеси от якоря до конца периода (М§4.11; строки моста выпуска): строка вычетов,
    строка роста RWA и всё прочее одной суммой. pairs — тройки (вероятность клетки, строка якоря, строка конца
    периода); строка — {k20, rwa, ded20, n20}. Норматив смеси — E[K20] / E[RWA] + A, где A — ожидание аддитивного
    слагаемого клеток N20 − K20 / RWA (поправка минус вычет сценария) под теми же вероятностями.

        вычеты:   сумма = −(E[Ded20_e] − Ded20_0),   доля = сумма / E[RWA_e] + (A_e − A_0)
        рост RWA: доля = K20_0 × (1 / E[RWA_e] − 1 / RWA_0)
        прочее:   сумма = E[K20_e] − K20_0 − сумма строки вычетов,   доля = сумма / E[RWA_e]

    Тождество: начало + сумма долей = конец. У книги с долей вычета якоря, постоянной в рублях, в строке вычетов
    стоит прирост одной растущей части, −Dgrow_20 × (E[RWA_e] / RWA_0 − 1): постоянная часть за период не меняется;
    при доле, равной единице, сумма строки — ноль, и в её доле остаётся одно изменение A."""
    mass = sum(item[0] for item in pairs)
    if mass <= 0.0:
        raise ControlInputError("мост норматива: вероятности клеток смеси в сумме не положительны")

    def c_mean(side: int, field) -> float:
        return sum(item[0] * field(item[side]) for item in pairs) / mass

    edges = {}
    for side, name in ((1, "start"), (2, "end")):
        edges[name] = {"k20": c_mean(side, lambda row: row["k20"]), "rwa": c_mean(side, lambda row: row["rwa"]),
                       "ded20": c_mean(side, lambda row: row["ded20"]),
                       "add": c_mean(side, lambda row: row["n20"] - row["k20"] / row["rwa"])}
    a, b = edges["start"], edges["end"]
    taken = -(b["ded20"] - a["ded20"])
    rest = b["k20"] - a["k20"] - taken
    return {"start": a["k20"] / a["rwa"] + a["add"], "end": b["k20"] / b["rwa"] + b["add"],
            "deductions": {"amount": taken, "pp": taken / b["rwa"] + (b["add"] - a["add"])},
            "rwa_growth": {"pp": a["k20"] * (1.0 / b["rwa"] - 1.0 / a["rwa"])},
            "rest": {"amount": rest, "pp": rest / b["rwa"]}, "rwa_start": a["rwa"], "rwa_end": b["rwa"]}


def c_capital_bridge(res: dict, year: int | None = None) -> dict:
    """Мост Н20.0 смеси точки от якоря до конца года year (без него — года даты оценки) по своим строкам клеток:
    строка вычетов, строка роста RWA и прочее одной суммой (c_bridge_lines). Справочно: выпуск контрольная модель не
    собирает, строки моста с ядром не сверяются (М§17) — по ним проверяются свойства строки вычетов у книги с
    долей вычета якоря."""
    ctx, weight = res["ctx"], c_point_mass(res)
    if year is None:
        year = ctx["periods"][ctx["clock"]["p0"]]["year"]
    i = res["years"].index(year)
    pairs = []
    for c in res["cells"]:
        first, last = c["anchor_capital"], c["rows"][i]
        pairs.append((weight[(c["world"], c["regime"], c["scenario"])],
                      {"k20": first["k20"], "rwa": ctx["rwa0"], "ded20": first["ded20"], "n20": first["n20"]},
                      {"k20": last["k20"], "rwa": last["rwa"], "ded20": last["ded20"], "n20": last["n20"]}))
    return {"year": year, **c_bridge_lines(pairs)}


def c_deduction_report(res: dict) -> dict:
    """Узел долей вычета якоря, постоянных в рублях (М§4.11; только у книги с ключами): по каждому нормативу —
    доля, постоянная в рублях и растущая с RWA части вычета якоря; мост Н20.0 смеси точки до конца года даты оценки
    со строкой вычетов (в ней — прирост одной растущей части)."""
    parts = res["ctx"]["ded"]
    return {"parts": {name: dict(part) for name, part in parts.items()}, "bridge": c_capital_bridge(res)}


def c_central_cell(res: dict) -> dict:
    """Центральная клетка книги — правилом, не литералом (INTERFACES §4.6): мир с наибольшим весом слоя
    «свой взгляд», режим с наибольшей вероятностью после A-P2u, сценарий капитала с наибольшей
    P(s | r) у этого режима; при равенстве — первый по порядку книги."""
    B = res["ctx"]["B"]
    pw = c_bget(B, "joint.world_prob")

    def c_first_max(ids, weight):
        best = ids[0]
        for x in ids[1:]:
            if weight(x) > weight(best):
                best = x
        return best

    w = c_first_max(list(c_bget(B, "worlds.ids")), lambda x: float(pw.get(x, 0.0)))
    r = c_first_max(list(c_bget(B, "regimes.ids")), lambda x: res["posterior"][x])
    prs = c_bget(B, "joint.reg_prob_given_regime")[r]
    sc = c_first_max(list(c_bget(B, "capital.reg_scenarios.ids")), lambda x: float(prs[x]))
    return {"cell": (w, r, sc), "label": "/".join((w, r, sc)), "scenario_weight": float(prs[sc]),
            "probability": float(pw[w]) * res["posterior"][r] * float(prs[sc])}


def c_cell_of(res: dict, world: str, regime: str, scenario: str) -> dict:
    for c in res["cells"]:
        if (c["world"], c["regime"], c["scenario"]) == (world, regime, scenario):
            return c
    raise KeyError((world, regime, scenario))


# ============================================================================ гейты знака и печатаемая маржа (М§4.5, §14.2)

def c_world_price(res: dict, world: str) -> float:
    """Цена мира (М§8.2): оценка при P(W) = 1 с вероятностями режимов и сценариев прогона — той же формулой,
    что цена слоя, на делителе N_div (М§8.4)."""
    ctx = res["ctx"]
    prs = c_bget(ctx["B"], "joint.reg_prob_given_regime")
    v0 = sum(res["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]]) * c_cell_worth(c)
             for c in res["cells"] if c["world"] == world)
    return c_price_of(v0, ctx["bridge_amount"], ctx["gov"], ctx["A"]["N_div"], ctx["pending_amount"])


def c_point_mass(res: dict) -> dict:
    """Вероятность клетки в точке (М§9): точка — смесь низа и верха с весом λ, поэтому вес мира —
    (1 − λ) × вес слоя «рыночные ставки как есть» + λ × вес слоя «свой взгляд»; режим и сценарий — как в слоях."""
    B = res["ctx"]["B"]
    weights = c_layer_weights(B)
    low, high = weights["macro_neutral"], weights["analytical"]
    prs = c_bget(B, "joint.reg_prob_given_regime")
    lam = res["lam"]
    out = {}
    for c in res["cells"]:
        world = (1.0 - lam) * low.get(c["world"], 0.0) + lam * high.get(c["world"], 0.0)
        out[(c["world"], c["regime"], c["scenario"])] = (world * res["posterior"][c["regime"]]
                                                         * float(prs[c["regime"]][c["scenario"]]))
    return out


def c_live_cells(res: dict) -> set:
    """Клетки положительной вероятности (М§3.4): вероятность клетки больше нуля хотя бы в одном из трёх слоёв.
    Клетка нулевой вероятности — сценарий требования, которому книга даёт вес только в одном режиме, и
    сценарий, вытесненный им в этом режиме, — считается и сверяется наравне с прочими, но гейты её не судят."""
    B = res["ctx"]["B"]
    weights = c_layer_weights(B)
    prs = c_bget(B, "joint.reg_prob_given_regime")
    return {(c["world"], c["regime"], c["scenario"]) for c in res["cells"]
            if any(weights[name].get(c["world"], 0.0) * res["posterior"][c["regime"]]
                   * float(prs[c["regime"]][c["scenario"]]) > 0.0 for name in LAYERS)}


def c_volume_sign(book: dict, facts: dict, res: dict | None = None, *, valuation_date=None) -> dict:
    """Числа гейта знака объёмных эффектов (М§4.5): сдвиг точки и цен миров при снятии остановки кредита в
    кризисе (loan_growth_override пуст) и поправок роста режимов (loan_growth_adj = 0). У книги с включённым
    ограничением роста обе стороны сравнения считаются при выключенном ограничении. res — готовый прогон
    этой книги: он служит базой, когда выключать нечего. У книги с ключом checks.volume_sign: {tol} (₽ на
    акцию) результат несёт допуск и условие гейта: ok ложно при сдвиге точки ниже −tol или сдвиге цены мира M
    ниже сдвига цены мира H больше чем на tol; без ключа гейта нет — только числа."""
    spec = c_bopt(book, "checks.volume_sign")
    tol = None
    if spec is not None:
        if not isinstance(spec, dict) or spec.get("tol") is None or float(spec["tol"]) < 0.0:
            raise ControlInputError("checks.volume_sign: нужен tol ≥ 0")
        tol = float(spec["tol"])
    base_book = copy.deepcopy(book)
    rule = c_bopt(base_book, "capital.growth_constraint")
    off = isinstance(rule, dict) and bool(rule.get("enabled"))
    if off:
        rule["enabled"] = False
    free_book = copy.deepcopy(base_book)
    free_book["regimes"][R_CRISIS]["loan_growth_override"] = {}
    for r in c_bget(free_book, "regimes.ids"):
        free_book["regimes"][r]["loan_growth_adj"] = 0.0
    if res is None or off:
        when = valuation_date if res is None else res["ctx"]["clock"]["v"]
        base = c_control_run(base_book, facts, valuation_date=when)
    else:
        base = res
    free = c_control_run(free_book, facts, valuation_date=base["ctx"]["clock"]["v"])
    ref_w = c_bget(base["ctx"]["B"], "nii.transmission.reference_world")
    d_point = free["point"] - base["point"]
    d_world = {w: c_world_price(free, w) - c_world_price(base, w) for w in base["ctx"]["worlds"]}
    ok = None if tol is None else not (d_point < -tol or d_world[W_MKT] < d_world[ref_w] - tol)
    return {"point": base["point"], "point_free": free["point"], "d_point": d_point, "d_world": d_world,
            "market_world": W_MKT, "reference_world": ref_w, "growth_constraint_off": off, "tol": tol, "ok": ok}


def c_stress_sign(book: dict, facts: dict, res: dict | None = None, *, valuation_date=None, tables=None):
    """Гейт знака стресса (ключ книги checks.stress_sign: {loss_step, tol}, оба — млрд ₽; нет ключа — None).

    (а) Убыток: сетка с разовым убытком режима шока, уменьшенным на loss_step (убыток больше); клетка режима
    шока нарушает, если её стоимость выше стоимости книги больше чем на tol. (б) Требование: в каждой паре
    «мир × режим» — по всем режимам, включая режим шока, — сценарий капитала с более высоким требованием Н20.0
    последнего года сетки нарушает, если его операционная прибыль акционеров последнего года выше, чем у
    сценария с более низким требованием, больше чем на tol. Считается на книге как она есть, с её правилом
    роста. Масса — вероятности точки нарушивших клеток (у пары — клетка более строгого сценария); наибольшее
    превышение — наибольший прирост стоимости или прибыли среди нарушений. В table — числа всех клеток и пар,
    которые гейт судит, не только нарушивших; tables — пара готовых таблиц (их числа от порога не зависят).
    Клетку нулевой вероятности гейт не судит (М§3.4, §14.2): в части (а) её нет, в части (б) пара входит в
    проверку, когда вероятность положительна у обеих клеток."""
    spec = c_bopt(book, "checks.stress_sign")
    if spec is None:
        return None
    if not isinstance(spec, dict) or spec.get("loss_step") is None or spec.get("tol") is None:
        raise ControlInputError("checks.stress_sign: нужны loss_step и tol")
    step, tol = float(spec["loss_step"]), float(spec["tol"])
    if step <= 0.0 or tol < 0.0:
        raise ControlInputError("checks.stress_sign: loss_step > 0 и tol ≥ 0")
    if res is None:
        res = c_control_run(book, facts, valuation_date=valuation_date)
    by_loss, by_req = tables if tables is not None else _c_stress_tables(book, facts, res, step)
    bad_loss = [x for x in by_loss if x["dv"] > tol]
    bad_req = [x for x in by_req if x["d_profit"] > tol]
    cells = ({(x["world"], x["regime"], x["scenario"]) for x in bad_loss}
             | {(x["world"], x["regime"], x["stricter"]) for x in bad_req})
    weight = c_point_mass(res)
    excess = [x["dv"] for x in bad_loss] + [x["d_profit"] for x in bad_req]
    return {"loss": {"step": step, "cells": bad_loss, "table": by_loss},
            "requirement": {"cells": bad_req, "table": by_req}, "tol": tol,
            "mass": sum(weight[key] for key in cells), "max_excess": max(excess) if excess else 0.0,
            "worlds": [w for w in res["ctx"]["worlds"] if any(key[0] == w for key in cells)], "ok": not cells}


def _c_stress_tables(book: dict, facts: dict, res: dict, step: float) -> tuple[list, list]:
    """Числа гейта знака стресса: прирост стоимости каждой клетки режима шока при разовом убытке, увеличенном
    на step (пересчёт клеток режима шока на книге с подменой одного ключа), и разность прибыли последнего
    года в каждой паре сценариев с разным требованием Н20.0 последнего года во всех режимах каждого мира — по
    прогону книги res. Клетки нулевой вероятности в таблицы не входят: гейт их не судит (М§3.4)."""
    ctx = res["ctx"]
    scen = list(c_bget(ctx["B"], "capital.reg_scenarios.ids"))
    live = c_live_cells(res)
    hit = copy.deepcopy(book)
    loss = hit["regimes"][R_CRISIS]["one_off_loss"]
    loss["amount"] = float(loss["amount"]) - step
    ctx_hit = c_control_context(hit, facts, valuation_date=ctx["clock"]["v"])
    by_loss = []
    for w in ctx["worlds"]:
        for s in scen:
            if (w, R_CRISIS, s) not in live:
                continue
            dv = c_cell_annual(ctx_hit, w, R_CRISIS, s)["v_ri"] - c_cell_of(res, w, R_CRISIS, s)["v_ri"]
            by_loss.append({"world": w, "regime": R_CRISIS, "scenario": s, "dv": dv})
    by_req = []
    for w in ctx["worlds"]:
        for r in c_bget(ctx["B"], "regimes.ids"):
            last = {s: c_cell_of(res, w, r, s)["rows"][-1] for s in scen if (w, r, s) in live}
            for upper in last:
                for lower in last:
                    if last[upper]["req20"] > last[lower]["req20"]:
                        by_req.append({"world": w, "regime": r, "stricter": upper, "looser": lower,
                                       "d_profit": last[upper]["ni_sh"] - last[lower]["ni_sh"]})
    return by_loss, by_req


def c_printed_margin(res: dict):
    """Печатаемая маржа после фазы роста (ключ книги checks.nim_lt: {target, tolerance, from_year}; нет ключа —
    None): среднее годовых ЧПМ упр. базиса модальной клетки за годы from_year … последний год сетки. Годовая
    ЧПМ — ЧПД года к среднему пяти концов кварталов процентных активов (М§0.3), в упр. базис — через мост."""
    ctx = res["ctx"]
    spec = c_bopt(ctx["B"], "checks.nim_lt")
    if spec is None:
        return None
    if not isinstance(spec, dict) or any(spec.get(k) is None for k in ("target", "tolerance", "from_year")):
        raise ControlInputError("checks.nim_lt: нужны target, tolerance и from_year")
    start = int(spec["from_year"])
    cell = c_cell_of(res, *res["central"]["cell"])
    by_year = {y: c_to_mgmt(ctx["A"], "nim", row["nim_year"]) for y, row in zip(res["years"], cell["rows"])
               if y >= start and row["nim_year"] is not None}
    if not by_year:
        raise ControlInputError("checks.nim_lt.from_year: на сетке нет полного года не раньше него")
    value = sum(by_year.values()) / len(by_year)
    target, tolerance = float(spec["target"]), float(spec["tolerance"])
    return {"cell": res["central"]["label"], "from_year": start, "target": target, "tolerance": tolerance,
            "value": value, "by_year": by_year, "ok": abs(value - target) <= tolerance}


# ============================================================================ уровни после фазы роста

def c_mix_weights(res: dict) -> dict[str, dict]:
    """Веса клеток четырёх смесей узла уровней: модальная клетка (вес 1), слой «свой взгляд», смесь точки и
    слой «рыночные ставки как есть». Вес клетки в слое — вес мира слоя × вероятность режима после A-P2u ×
    P(s | r) (М§3.4, §9); в смеси точки — λ-смесь двух слоёв."""
    B = res["ctx"]["B"]
    worlds = c_layer_weights(B)
    prs = c_bget(B, "joint.reg_prob_given_regime")

    def c_layer(name):
        return {(c["world"], c["regime"], c["scenario"]): (worlds[name].get(c["world"], 0.0)
                                                           * res["posterior"][c["regime"]]
                                                           * float(prs[c["regime"]][c["scenario"]]))
                for c in res["cells"]}

    return {MIX_MODAL: {tuple(res["central"]["cell"]): 1.0}, LAYER_OWN: c_layer(LAYER_OWN),
            MIX_POINT: c_point_mass(res), LAYER_MARKET: c_layer(LAYER_MARKET)}


def c_year_levels(res: dict, weight: dict) -> dict[int, dict]:
    """Годовые ЧПМ, CoR и C/I смеси клеток с весами weight, упр. базис: год → {nim, cor, cir}.

    Метрика смеси — отношение ожидаемых агрегатов: ожидание числителя к ожиданию знаменателя, а не ожидание
    отношений клеток. Числители — годовые суммы ЧПД, резервов и расходов; знаменатели ЧПМ и CoR — среднее
    пяти концов кварталов процентных активов и кредитов по амортизированной стоимости (М§0.3), знаменатель
    C/I — доход NII + F + INS + MISC + FVR (М§4.6). В упр. базис — через мост. Неполный год якоря значения не
    несёт. У смеси из одной клетки это годовые метрики самой клетки."""
    ctx = res["ctx"]
    A = ctx["A"]
    out = {}
    for i, p in enumerate(ctx["periods"]):
        if p["stub"]:
            continue
        tot = dict.fromkeys(("nii", "iea", "llp", "loans", "opex", "income"), 0.0)
        for c in res["cells"]:
            k = weight.get((c["world"], c["regime"], c["scenario"]), 0.0)
            if not k:
                continue
            row = c["rows"][i]
            tot["nii"] += k * row["nii"]
            tot["iea"] += k * _c_ends_mean(row["iea_ends"])
            tot["llp"] += k * row["llp"]
            tot["loans"] += k * _c_ends_mean(row["loans_ac_ends"])
            tot["opex"] += k * row["opex"]
            tot["income"] += k * row["income_cir"]
        if not (tot["iea"] and tot["loans"] and tot["income"]):
            raise ControlInputError(f"уровни года {p['year']}: у смеси нет веса или знаменатель — ноль")
        out[p["year"]] = {"nim": c_to_mgmt(A, "nim", tot["nii"] / tot["iea"]),
                          "cor": c_to_mgmt(A, "cor", tot["llp"] / tot["loans"]),
                          "cir": c_to_mgmt(A, "cir", tot["opex"] / tot["income"])}
    return out


def c_levels(res: dict, from_year: int | None = None):
    """Уровни после фазы роста: простые средние годовых упр. ЧПМ, CoR и C/I за годы from_year … последний год
    сетки — для модальной клетки, слоя «свой взгляд», смеси точки и слоя «рыночные ставки как есть».
    from_year — аргумент или ключ книги checks.window_backtest.from_year; нет ни того, ни другого — None.
    → {from_year, years, mixes: {смесь: {nim, cor, cir, by_year}}}."""
    if from_year is None:
        spec = c_bopt(res["ctx"]["B"], "checks.window_backtest")
        if spec is None:
            return None
        if not isinstance(spec, dict) or spec.get("from_year") is None:
            raise ControlInputError("checks.window_backtest: нужен from_year")
        from_year = spec["from_year"]
    start = int(from_year)
    mixes, years = {}, []
    for name, weight in c_mix_weights(res).items():
        by_year = {y: v for y, v in c_year_levels(res, weight).items() if y >= start}
        if not by_year:
            raise ControlInputError("уровни после фазы роста: на сетке нет полного года не раньше from_year")
        years = sorted(by_year)
        mixes[name] = {x: sum(v[x] for v in by_year.values()) / len(by_year) for x in ("nim", "cor", "cir")}
        mixes[name]["by_year"] = by_year
    return {"from_year": start, "years": years, "mixes": mixes}


def c_window_backtest(res: dict):
    """Гейт сверки с окном фактов (ключ книги checks.window_backtest: {from_year, cor: [низ, верх], cir: [низ,
    верх]}; нет ключа — None): уровни CoR и C/I слоя «рыночные ставки как есть» — средние за годы from_year …
    последний год сетки — внутри коридоров книги, края включены. Маржа гейтом не сверяется: она печатается."""
    spec = c_bopt(res["ctx"]["B"], "checks.window_backtest")
    if spec is None:
        return None
    lanes = {}
    for x in ("cor", "cir"):
        lane = spec.get(x) if isinstance(spec, dict) else None
        if not isinstance(lane, (list, tuple)) or len(lane) != 2 or float(lane[0]) > float(lane[1]):
            raise ControlInputError(f"checks.window_backtest.{x}: нужен коридор [низ, верх]")
        lanes[x] = (float(lane[0]), float(lane[1]))
    levels = c_levels(res)
    layer = levels["mixes"][LAYER_MARKET]
    bad = [x for x, (lo, hi) in lanes.items() if not lo <= layer[x] <= hi]
    return {"from_year": levels["from_year"], "years": levels["years"], "layer": LAYER_MARKET,
            "cor": layer["cor"], "cir": layer["cir"], "nim": layer["nim"], "cor_range": lanes["cor"],
            "cir_range": lanes["cir"], "outside": bad, "ok": not bad}


def c_cir_level(res: dict):
    """Уровень C/I, с которым сверяется цель книги (ключ checks.cir_lt: {target, tolerance, from_year} и
    необязательный scope; нет ключа — None): среднее годовых упр. C/I за годы from_year … последний год сетки.
    Без scope (или scope: modal_cell) — модальная клетка, как у образца; scope: market_layer — слой «рыночные
    ставки как есть», отношение ожидаемых агрегатов."""
    spec = c_bopt(res["ctx"]["B"], "checks.cir_lt")
    if spec is None:
        return None
    if not isinstance(spec, dict) or any(spec.get(k) is None for k in ("target", "tolerance", "from_year")):
        raise ControlInputError("checks.cir_lt: нужны target, tolerance и from_year")
    scope = spec.get("scope")
    if scope not in (None, SCOPE_MODAL, SCOPE_MARKET):
        raise ControlInputError(f"checks.cir_lt.scope: {scope!r}")
    mix = LAYER_MARKET if scope == SCOPE_MARKET else MIX_MODAL
    start = int(spec["from_year"])
    by_year = {y: v["cir"] for y, v in c_year_levels(res, c_mix_weights(res)[mix]).items() if y >= start}
    if not by_year:
        raise ControlInputError("checks.cir_lt.from_year: на сетке нет полного года не раньше него")
    value = sum(by_year.values()) / len(by_year)
    target, tolerance = float(spec["target"]), float(spec["tolerance"])
    return {"scope": scope, "mix": mix, "cell": res["central"]["label"] if mix == MIX_MODAL else None,
            "from_year": start, "target": target, "tolerance": tolerance, "value": value, "by_year": by_year,
            "ok": abs(value - target) <= tolerance}


# ============================================================================ DPS истории (М§5.2, прил. C)

def c_history_kind(B: dict) -> str:
    """Вид теста истории выплат (М§5.2): exact без ключа, cap — потолок политики, none — выключен."""
    kind = c_bopt(B, "dividends.policy.history_test", HIST_EXACT)
    if kind not in (HIST_EXACT, HIST_CAP, HIST_NONE):
        raise ControlInputError(f"dividends.policy.history_test: {kind!r} (М§5.2)")
    return kind


def c_cap_history_ctl(B: dict, facts: dict) -> list[dict]:
    """Тест истории вида cap (М§5.2): по годам фактов dividends.years — сумма объявленных пулов решений
    года против потолка политики × отчётная прибыль акционеров; неполный год — диагностика (ok = None)."""
    cap = c_bopt(B, "dividends.policy.cap")
    if cap is None or not 0.0 < float(cap) <= 1.0:
        raise ControlInputError("dividends.policy.cap: нужен потолок в (0; 1] при тесте истории cap (М§5.2)")
    dv = facts.get("dividends", {})
    out = []
    for year, node in sorted((dv.get("years") or {}).items(), key=lambda kv: int(kv[0])):
        ni = _c_nodeval(node.get("ni_shareholders"))
        if ni is None:
            raise ControlInputError(f"dividends.years.{year}.ni_shareholders: null (М§5.2)")
        pool = 0.0
        for rec in dv.get("history", []):
            if int(_c_nodeval(rec.get("year"))) != int(year):
                continue
            part = _c_nodeval(rec.get("pool_declared"))
            if part is None:
                raise ControlInputError(f"строка dividends.history {rec.get('period')} без pool_declared (М§5.2)")
            pool += float(part)
        complete = bool(_c_nodeval(node.get("complete")))
        limit = float(cap) * float(ni)
        out.append({"year": int(year), "pool": pool, "ni_shareholders": float(ni),
                    "share": pool / float(ni) if float(ni) else None, "cap": float(cap), "limit": limit,
                    "complete": complete, "ok": (pool <= limit + 1e-9) if complete else None})
    return out


def c_dps_history_ctl(B: dict, facts: dict) -> list[dict]:
    """Тест истории выплат вида книги (М§5.2). exact — формула пула на фактах истории в точной десятичной
    арифметике, округление книги; cap — строки теста потолка; none — пусто."""
    kind = c_history_kind(B)
    if kind == HIST_CAP:
        return c_cap_history_ctl(B, facts)
    if kind == HIST_NONE:
        return []
    mode = c_bget(B, "dividends.policy.dps_rounding")
    n_iss = Decimal(str(c_fnum(facts, "shares", "issued_total")))
    out = []
    for rec in facts.get("dividends", {}).get("history", []):
        vals = {k: _c_nodeval(rec.get(k)) for k in ("year", "ni_shareholders", "at1_coupon",
                                                 "tax_statutory", "dps_ordinary")}
        if any(vals[k] is None for k in ("ni_shareholders", "at1_coupon", "tax_statutory")):
            continue
        year = int(vals["year"])
        payout = Decimal(str(c_traj_year(c_bget(B, "dividends.policy.payout"), year)))
        base = (Decimal(str(vals["ni_shareholders"]))
                - Decimal(str(vals["at1_coupon"])) * (Decimal(1) - Decimal(str(vals["tax_statutory"]))))
        exact = payout * base * Decimal(1000) / n_iss
        rnd = ROUND_CEILING if mode == "ceil_kopeck" else ROUND_HALF_UP
        dps = exact.quantize(Decimal("0.01"), rounding=rnd)
        declared = vals["dps_ordinary"]
        out.append({"year": year, "exact": float(exact), "dps": float(dps),
                    "declared": None if declared is None else float(declared),
                    "ok": declared is not None and dps == Decimal(str(declared)).quantize(Decimal("0.01"))})
    return out


# ============================================================================ печать сводки

def _c_fmt(x, nd=1):
    return "—" if x is None else f"{x:,.{nd}f}".replace(",", " ")


def c_summary_lines(res: dict, central=None) -> list[str]:
    ctx = res["ctx"]
    rule = central is None
    central = tuple(res["central"]["cell"] if rule else central)
    A = ctx["A"]
    tr = res["transmission"]
    branch = ("годовая, квартальный проход капитала" + (", рост ограничен капиталом" if ctx["growth"] else "")
              if ctx["quarterly"] else "годовая")
    L = [f"Контрольная модель ({branch}), книга " + str(c_bget(ctx["B"], "meta.version")),
         f"дата оценки {ctx['clock']['v']}, период p0 = {ctx['periods'][ctx['clock']['p0']]['label']}, "
         f"e = {ctx['clock']['e']:.4f}",
         f"передача: σ0_A = {tr['sigma0']:.6f}, σ0_L = {tr['sigma0_liab']:.6f} (доля активов {tr['split']}, "
         f"к спредам с {ctx['sigma0_from']}), φ = {tr['phi']:.6f}, "
         f"T_real = {tr['t_real']:.6f}, target_eng = {tr['target_eng']:.6f}, T(W) = "
         + ", ".join(f"{w} {v:.4f}" for w, v in tr["t_local"].items()),
         f"раскладка сжатия: доля кредитных книг {tr['phi_split']}, φ_A = {tr['phi_assets']:.6f}, "
         f"φ_L = {tr['phi_liab']:.6f}; кредитная маржа стационара: "
         + ", ".join(f"{w} {v:.4f}" for w, v in tr["loan_margin"].items()),
         "эффективные LT-спреды: " + "; ".join(
             f"{b}: " + ", ".join(f"{w} {v:.4f}" for w, v in ws.items()) for b, ws in tr["lt_spread"].items()),
         "пары: " + ", ".join(f"{k} {'—' if v is None else f'{v:.6f}'}" for k, v in tr["pairs"].items())
         + f"; ROE-эквивалент T* = {tr['roe_equiv']:.4f}, пар: "
         + ", ".join(f"{k} {'—' if v is None else f'{v:.4f}'}" for k, v in tr["roe_equiv_pairs"].items()),
         f"RWA_0 модели = {_c_fmt(ctx['rwa0'])} (Базель {_c_fmt(A['rwa_basel'])})",
         f"вероятности режимов: " + ", ".join(f"{r} {p:.4f}" for r, p in res["posterior"].items()),
         f"мост B(v) = {_c_fmt(res['bridge_amount'], 2)}, D_pend = {_c_fmt(res['pending_amount'], 2)}, "
         f"дисконт за управление = {res['governance']:.4f}, год шока кризиса {res['shock_year']}"]
    for name in LAYERS:
        ly = res["layers"][name]
        L.append(f"слой {name}: V0 = {_c_fmt(ly['v0'])}, BV_v = {_c_fmt(ly['bv_v'])}, P/B = {ly['pb']:.3f}, "
                 f"цена = {ly['price']:.2f} ₽")
    L.append(f"низ = {res['low']:.2f} ₽, верх = {res['high']:.2f} ₽, λ = {res['lam']}, "
             f"точка = {res['point']:.2f} ₽")
    c = c_cell_of(res, *central)
    cap0 = c["anchor_capital"]
    L.append(f"якорь: Н20.0 модели {cap0['n20']:.4f} (факт {A['n20_fact']:.4f}), "
             f"второй норматив модели {cap0['n11']:.4f} (факт слота n1_1_bank {A['n11_fact']:.4f})")
    if rule:
        L.append(f"центральная клетка по правилу: {res['central']['label']}, вероятность в слое «свой взгляд» "
                 f"{res['central']['probability']:.4f}, вес сценария {res['central']['scenario_weight']:.2f}")
    L.append(f"клетка {'/'.join(central)}: V = {_c_fmt(c['v_ri'])}, V_DDM = {_c_fmt(c['v_ddm'])}, BV_v = {_c_fmt(c['bv_v'])}, "
             f"X_T = {_c_fmt(c['x_t'])}, запас LA над минимумом = {_c_fmt(c['hla'])} (порог связывания "
             f"{_c_fmt(c['h_star'])}), доход на избыток = "
             f"{_c_fmt(c['y_x'])} (ставка смеси {c['y_bal']:.4f}), ROE'_T = {c['roe_t']:.4f}, "
             f"k_T = {c['k_t']:.4f}, g_T = {c['g_t']:.4f}, "
             f"TV_RI = {_c_fmt(c['tv_ri'])}, доля терминала = {c['terminal_share']:.3f}")
    head = ["год", "ЧПД", "резервы", "FVC", "ЧКД", "расходы", "непроф.", "прочее", "PBT", "ЧП акц.", "CI", "BV",
            "RWA", "Н20.0", "Н20.1", "ЧПМ", "CoR", "ROE", "DPS за год"]
    L.append(" | ".join(head))
    for p, row in zip(ctx["periods"], c["rows"]):
        dec = c["decisions"].get(p["year"])
        L.append(" | ".join([p["label"] + ("*" if p["stub"] else ""), _c_fmt(row["nii"]), _c_fmt(row["llp"]),
                             _c_fmt(row["fvc"]),
                             _c_fmt(row["fees"]), _c_fmt(row["opex"]), _c_fmt(row["noncore"]), _c_fmt(row["misc"]),
                             _c_fmt(row["pbt"]), _c_fmt(row["ni_sh"]), _c_fmt(row["ci"]), _c_fmt(row["bv"]),
                             _c_fmt(row["rwa"]), f"{row['n20']:.4f}", f"{row['n11']:.4f}",
                             f"{row['nim']:.4f}", f"{row['cor']:.4f}", f"{row['roe']:.4f}",
                             "—" if dec is None else f"{dec['dps']:.2f}"]))
    if ctx["quarterly"]:
        L.append("год | рост кредитных книг: потенциальный | фактический | доля урезанного | min λ | "
                 "навёрстывание | треб. Н20.0 с глиссадой | Н20.1 с глиссадой | дивиденд модели")
        for p, row in zip(ctx["periods"], c["rows"]):
            L.append(" | ".join([p["label"] + ("*" if p["stub"] else ""),
                                 "—" if row["growth_potential"] is None else f"{row['growth_potential']:.4f}",
                                 "—" if row["growth_actual"] is None else f"{row['growth_actual']:.4f}",
                                 f"{row['cut_share']:.4f}", f"{row['lam_min']:.4f}", _c_fmt(row["catch_up"]),
                                 f"{row['req20_glide']:.4f}", f"{row['req11_glide']:.4f}", _c_fmt(row["div_model"], 2)]))
        L.append("DPS кварталов прибыли: " + ", ".join(
            f"{d['period']} {d['dps']:.2f} ({d['source']})" for d in c["decisions_q"]))
    if "recapitalization" in res:
        # у книги с включённой докапитализацией стоимость клетки проходит через ноль: невязка — к норме клетки
        L.append("клетки (V_RI, млрд ₽; цена ₽; |V_DDM − V_RI| к норме клетки max(|V_RI|, BV_v − C_v)):")
    else:
        L.append("клетки (V_RI, млрд ₽; цена ₽; |V_DDM/V_RI − 1|):")
    for cc in res["cells"]:
        gap = c_ddm_gap(cc) if "recapitalization" in res else abs(cc["v_ddm"] / cc["v_ri"] - 1)
        L.append(f"  {cc['world']} {cc['regime']:<8} {cc['scenario']:<8} V = {_c_fmt(cc['v_ri'])} "
                 f"цена {cc['price']:.1f} P/B {cc['pb']:.3f} ROE'_T {cc['roe_t']:.4f} k_T {cc['k_t']:.4f} "
                 f"X_T {_c_fmt(cc['x_t'])} ddm {gap:.1e}")
    for h in res["dps_history"]:
        if res["history_test"] == HIST_CAP:
            verdict = "диагностика (год неполный)" if h["ok"] is None else "ok" if h["ok"] else "ПРЕВЫШЕНИЕ"
            L.append(f"потолок выплат {h['year']}: объявлено {_c_fmt(h['pool'], 3)}, отчётная прибыль акционеров "
                     f"{_c_fmt(h['ni_shareholders'], 3)}, доля {h['share']:.4f} при потолке {h['cap']}, {verdict}")
            continue
        L.append(f"DPS истории {h['year']}: формула {h['dps']:.2f} (точно {h['exact']:.5f}), "
                 f"объявлен {h['declared']}, {'ok' if h['ok'] else 'РАСХОЖДЕНИЕ'}")
    if res["divisor"] != res["shares_out"]:
        L.append(f"делитель N_div = {_c_fmt(res['divisor'], 3)} млн шт. (в обращении {_c_fmt(res['shares_out'], 3)})")
    if "recapitalization" in res:
        rule, summary = res["recap_rule"], res["recapitalization"]
        L.append(f"докапитализация: дисконт размещения {rule['d']}, решение — {rule['quarter']}-й квартал года "
                 f"(собрание — {rule['agm']}-й), окно {rule['ahead']} кв. при нижней границе {rule['ahead_min']}, порог "
                 f"{_c_fmt(rule['least'])} млрд ₽; смесь точки — приведённая сумма взносов "
                 f"{_c_fmt(summary['point']['pv_rec'])} + терминал {_c_fmt(summary['point']['pv_rec_terminal'])} млрд ₽, "
                 f"цена размывания {_c_fmt(summary['point']['pvd'])} млрд ₽ ({summary['point']['pvd_per_share']:.2f} ₽ "
                 f"на акцию), масса клеток со взносом {summary['point']['recap_mass']:.4f}")
        L.append("год | взнос смеси точки, млрд ₽ | масса клеток со взносом | доля нынешних акций | DPS смеси на "
                 f"акции своего года | взнос клетки {summary['modal']} | её доля нынешних акций")
        for x in summary["years"]:
            L.append(" | ".join([str(x["year"]), _c_fmt(x["rec"]), f"{x['rec_mass']:.4f}", f"{x['stake']:.4f}",
                                 "—" if x["dps"] is None else f"{x['dps']:.2f}", _c_fmt(x["modal_rec"]),
                                 f"{x['modal_stake']:.4f}"]))
    if "cell_floor" in res:
        fl = res["cell_floor"]
        L.append(f"пол клетки {_c_fmt(fl['floor'])} млрд ₽: масса клеток на полу в смеси точки {fl['floored_mass']:.4f}, "
                 f"поправка пола {_c_fmt(fl['floor_shift'])} млрд ₽, точка без пола {fl['point_plain']:.2f} ₽ "
                 f"(сдвиг от пола {fl['point_shift']:+.2f} ₽)")
    if "deduction_shares" in res:
        node = res["deduction_shares"]
        br = node["bridge"]
        L.append("доля вычета якоря, постоянная в рублях: " + "; ".join(
            f"{DED_SHARE[name]} = {part['share']} (постоянная часть {_c_fmt(part['fix'])}, растущая "
            f"{_c_fmt(part['grow'])} млрд ₽)" for name, part in node["parts"].items()))
        L.append(f"мост Н20.0 смеси точки до конца {br['year']} года: начало {br['start']:.4f}, вычеты "
                 f"{_c_fmt(br['deductions']['amount'])} млрд ₽ ({br['deductions']['pp']:+.4f}), рост RWA "
                 f"{br['rwa_growth']['pp']:+.4f}, прочее {_c_fmt(br['rest']['amount'])} млрд ₽ "
                 f"({br['rest']['pp']:+.4f}), конец {br['end']:.4f}")
    if "fixed_parts" in res:
        node = res["fixed_parts"]
        if "rub_end" in node:
            L.append(f"вычет сценария в рублях на конце сетки (смесь точки), млрд ₽: Н20.0 "
                     f"{_c_fmt(node['rub_end'][NORM_TOTAL])}, второй норматив {_c_fmt(node['rub_end'][NORM_BASE])}; "
                     f"мост Н20.0 до конца {node['bridge']['year']} года: вычеты "
                     f"{_c_fmt(node['bridge']['deductions']['amount'])} млрд ₽ ({node['bridge']['deductions']['pp']:+.4f})")
        if "oaf_end" in node:
            L.append(f"постоянная часть прочих активов: якорь {_c_fmt(node['oaf_anchor'])}, конец сетки "
                     f"{_c_fmt(node['oaf_end'])} млрд ₽ (приращение {_c_fmt(node['oaf_change_end'])}, вес риска "
                     f"приращения {node['oaf_change_density']})")
        if "terminal" in node:
            t = node["terminal"]
            L.append(f"постоянные части за концом сетки, λ_F = {t['lam_f']} (смесь точки): F_A {_c_fmt(t['f_a'])}, "
                     f"R_F {_c_fmt(t['r_f'])}, C {_c_fmt(t['c'])}, F_K {_c_fmt(t['f_k'])}, D_F {_c_fmt(t['d_f'])}, "
                     f"I_F {_c_fmt(t['i_f'])} млрд ₽ в год при y_m {t['y_m']:.4f}; капитал бизнеса "
                     f"{_c_fmt(t['business_capital'])}; масса: связывает Н20.0 {t['binding_n20_mass']:.3f}, бизнес выше "
                     f"k_T {t['business_above_k_mass']:.3f}, добор опта {t['wholesale_mass']:.3f}")
    if ctx.get("seg_w") is not None:
        B = ctx["B"]
        rel = {sg: c_bnum(B, f"credit.segment_relative.{sg}") for sg in SEGMENTS}
        L.append(f"структура нормировки сегментной CoR ({'ключ ' + SEG_SHARE if _c_key_given(B, SEG_SHARE) else 'доли якоря'}"
                 f"): " + ", ".join(f"{sg} {ctx['seg_w'][sg]:.6f} (rel {rel[sg]})" for sg in SEGMENTS)
                 + f"; Σ w × rel = {sum(ctx['seg_w'][sg] * rel[sg] for sg in SEGMENTS):.6f}")
    if ctx.get("iea_facts"):
        L.append("база объёма iea кварталов фактов (М§4.7; полусумма концов − ΔE / 2): " + "; ".join(
            f"{y}Q{q} {_c_fmt(v['a'])} (ΔE {_c_fmt(v['delta_e'])}, Div {_c_fmt(v['div'], 3)}; полусумма "
            f"{_c_fmt(v['a_ends'])})" for (y, q), v in sorted(ctx["iea_facts"].items())))
    if "t2_share" in res:
        t = res["t2_share"]
        L.append(f"доля инструментов в RWA своей клетки с {t['from']} (q_χ = {t['q_chi']}): доли клеток "
                 f"{t['share_min']:.5f}…{t['share_max']:.5f}, под смесью точки {t['share_point']:.5f} (доля якоря "
                 f"{t['anchor_share']:.5f}); клетка {t['modal']} — {t['modal_share']:.5f}, траектория на её RWA конца сетки "
                 f"держала бы {t['modal_trajectory_share_end']:.5f}; T2 конца сетки под смесью точки "
                 f"{_c_fmt(t['t2_end_point'])} млрд ₽ против траектории {_c_fmt(t['t2_trajectory_end'])}")
    node = res.get("pass8", {})
    if "at1" in node:
        t = node["at1"]
        L.append(f"добавочный капитал в доле RWA своей клетки с {t['from']} (q_α = {t['q_alpha']}): доли клеток "
                 f"{t['share_min']:.5f}…{t['share_max']:.5f}, под смесью точки {t['share_point']:.5f} (доля якоря "
                 f"{t['anchor_share']:.5f}); AT1 конца сетки под смесью точки {_c_fmt(t['at1_end_point'])} млрд ₽ (база "
                 f"{_c_fmt(t['base'])}); купон сверх базы последнего года {_c_fmt(t['coupon_new_last_point'], 2)}, купон "
                 f"года T + 1 {_c_fmt(t['coupon_t1_point'], 2)} млрд ₽ (надбавка новых выпусков {t['spread']})")
    if "t2_premium" in node:
        t = node["t2_premium"]
        L.append(f"надбавка за субординацию T2 {t['spread']} сверх базы {_c_fmt(t['base'])} млрд ₽: последний год "
                 f"{_c_fmt(t['sp_last_point'], 2)}, год T + 1 {_c_fmt(t['sp_t1_point'], 2)} млрд ₽ (смесь точки)")
    if "other_movements" in node:
        t = node["other_movements"]
        L.append(f"прочие движения капитала за концом сетки ({t['kind']}): OM_LT {_c_fmt(t['om_lt'], 2)} за квартал, "
                 f"OM_ann {_c_fmt(t['om_ann'], 2)} в год, OM_ann / k_T под смесью точки {_c_fmt(t['om_term_point'], 2)} млрд ₽")
    node = res.get("pass9", {})
    if "tax" in node:
        t = node["tax"]
        ys = [y for y in res["years"] if t["etr_point"].get(y) is not None]
        pick = [ys[0], ys[min(1, len(ys) - 1)], ys[min(3, len(ys) - 1)], ys[-1]] if ys else []
        L.append(f"налог по правилу (τ_b {t['bond_rate']}, ζ {t['bond_scale']}, o {t['other_pp']}, купон "
                 f"{'вычитается' if t['deductible'] else 'не вычитается'}): эффективная ставка под смесью точки "
                 + ", ".join(f"{y} {t['etr_point'][y]:.2%}" for y in pick) + "; по мирам "
                 + "; ".join(f"{w} " + "/".join(f"{v[y]:.1%}" if v.get(y) is not None else "—" for y in pick)
                             for w, v in t["etr_by_world"].items())
                 + f"; экономия купона последнего года {_c_fmt(t['saving_point'][res['years'][-1]], 2)}, налог года T + 1 "
                 f"{_c_fmt(t['tax_t1_point'])} млрд ₽ (смесь точки)")
    if "at1_coupon" in node:
        t = node["at1_coupon"]
        y_show = [y for y in res["years"] if any(v.get(y) for v in t["coupon_by_world"].values())]
        L.append(f"купон якоря по ставке своего мира ({_c_fmt(t['fixed'], 2)} + {_c_fmt(t['floating'], 1)} × (k̄ + "
                 f"{t['spread']})): по мирам "
                 + "; ".join(f"{w} " + "/".join(_c_fmt(v[y], 1) for y in y_show[:3]) for w, v in t["coupon_by_world"].items())
                 + f" ({'/'.join(str(y) for y in y_show[:3])}); год T + 1 "
                 + ", ".join(f"{w} {_c_fmt(v, 1)}" for w, v in t["coupon_t1_by_world"].items())
                 + f", под смесью точки {_c_fmt(t['coupon_t1_point'], 2)} млрд ₽")
    return L


def c_gate_lines(book: dict, facts: dict, res: dict) -> list[str]:
    """Числа гейтов знака, печатаемая маржа и уровни после фазы роста строками сводки (ключ --gates): два-три
    прогона сетки сверх основного; уровни считаются по клеткам основного прогона."""
    sign = c_volume_sign(book, facts, res)
    L = ["знак объёмных эффектов" + (" (обе стороны — без ограничения роста)" if sign["growth_constraint_off"] else "")
         + f": точка {sign['point']:.2f} → {sign['point_free']:.2f} ₽, сдвиг {sign['d_point']:+.2f} ₽; миры: "
         + ", ".join(f"{w} {d:+.2f}" for w, d in sign["d_world"].items())
         + ("; ключа checks.volume_sign в книге нет — гейта нет" if sign["ok"] is None
            else f"; допуск {sign['tol']} ₽, условие гейта {'выполнено' if sign['ok'] else 'нарушено'}")]
    stress = c_stress_sign(book, facts, res)
    if stress is None:
        L.append("знак стресса: ключа checks.stress_sign в книге нет — гейта нет")
    else:
        L.append(f"знак стресса (убыток больше на {_c_fmt(stress['loss']['step'])} млрд ₽, допуск {stress['tol']} млрд ₽): "
                 f"клеток с ростом стоимости {len(stress['loss']['cells'])} из {len(stress['loss']['table'])}, "
                 f"пар сценариев с ростом прибыли {len(stress['requirement']['cells'])} из "
                 f"{len(stress['requirement']['table'])}; масса {stress['mass']:.4f}, наибольшее превышение "
                 f"{_c_fmt(stress['max_excess'], 2)} млрд ₽" + ("" if stress["ok"] else "; миры: " + ", ".join(stress["worlds"])))
        for x in stress["loss"]["cells"]:
            L.append(f"  убыток: {x['world']}/{x['regime']}/{x['scenario']} стоимость {x['dv']:+.2f} млрд ₽")
        for x in stress["requirement"]["cells"]:
            L.append(f"  требование: {x['world']}/{x['regime']} {x['stricter']} против {x['looser']} "
                     f"прибыль {x['d_profit']:+.2f} млрд ₽")
    margin = c_printed_margin(res)
    if margin is not None:
        L.append(f"печатаемая маржа после фазы роста, клетка {margin['cell']}, с {margin['from_year']} года: "
                 f"{margin['value']:.4f} при цели {margin['target']} ± {margin['tolerance']}")
    window = c_window_backtest(res)
    if window is not None:
        names = {MIX_MODAL: "модальная клетка", LAYER_OWN: "слой «свой взгляд»", MIX_POINT: "смесь точки",
                 LAYER_MARKET: "слой «рыночные ставки как есть»"}
        for mix, lv in c_levels(res)["mixes"].items():
            L.append(f"уровни с {window['from_year']} года, {names[mix]}: ЧПМ {lv['nim']:.4f}, CoR {lv['cor']:.4f}, "
                     f"C/I {lv['cir']:.4f}")
        L.append(f"сверка с окном фактов, слой «рыночные ставки как есть»: CoR {window['cor']:.4f} в коридоре "
                 f"{window['cor_range'][0]}…{window['cor_range'][1]}, C/I {window['cir']:.4f} в коридоре "
                 f"{window['cir_range'][0]}…{window['cir_range'][1]} — "
                 + ("выполнено" if window["ok"] else "нарушено: " + ", ".join(window["outside"])))
    level = c_cir_level(res)
    if level is not None:
        where = "слой «рыночные ставки как есть»" if level["cell"] is None else f"клетка {level['cell']}"
        L.append(f"уровень C/I для цели книги, {where}, с {level['from_year']} года: {level['value']:.4f} при цели "
                 f"{level['target']} ± {level['tolerance']}")
    return L


def _c_jsonable(x):
    if isinstance(x, dict):
        return {str(k): _c_jsonable(v) for k, v in x.items() if k != "ctx"}
    if isinstance(x, (list, tuple)):
        return [_c_jsonable(v) for v in x]
    if isinstance(x, (dt.date,)):
        return x.isoformat()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def c_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Контрольная модель: годовая, с квартальным проходом капитала (М§17)")
    ap.add_argument("--book", help="машинная книга (по умолчанию data/assumptions/assumptions.yaml)")
    ap.add_argument("--draft", action="store_true", help="шаблон книги + миры и надстройка (своя сборка)")
    ap.add_argument("--worlds-lt", default="", help="узел LT кривой миров для --draft: N=<доля>,H=<доля>")
    ap.add_argument("--facts", help="каталог фактов (по умолчанию data/facts)")
    ap.add_argument("--date", help="дата оценки YYYY-MM-DD (по умолчанию — книги)")
    ap.add_argument("--json", help="записать полный результат в JSON")
    ap.add_argument("--gates", action="store_true", help="числа гейтов знака, печатаемая маржа и уровни после фазы роста (ещё два-три прогона)")
    a = ap.parse_args(argv)
    if a.draft:
        lt = {k: float(v) for k, v in (kv.split("=") for kv in a.worlds_lt.split(",") if kv)}
        book = c_book_from_draft(curve_lt=lt)
    else:
        book = c_book_machine(Path(a.book) if a.book else None)
    facts = c_facts_bundle(Path(a.facts) if a.facts else None)
    res = c_control_run(book, facts, valuation_date=a.date)
    for line in c_summary_lines(res) + (c_gate_lines(book, facts, res) if a.gates else []):
        print(line)
    if a.json:
        Path(a.json).write_bytes(json.dumps(_c_jsonable(res), ensure_ascii=False, indent=1).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(c_cli())
