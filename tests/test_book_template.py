# -*- coding: utf-8 -*-
"""Книга Банка ВТБ: шаблон разбирается, сборка воспроизводит машинную книгу, все пути прил. A MODEL и договора
ключей есть и не null там, где ядро их читает, схема ядра принимает форму книги; вероятности, оси полосы и строки
обратного расчёта согласованы со значениями книги; решения ведущего ВТБ (notes/LEAD-DECISIONS-*.md папки передачи,
пересказ — шапка и комментарии шаблона) и правила формы банка (годовой календарь дивидендов, докапитализация и пол
клетки, слои капитала долей RWA своей клетки, премии траекториями, оси-связки, числа «выведено на ядре» — запись листа
вывода) — числами книги. Тест писался под книгу образца (Т-Технологии) и переписан под книгу ВТБ 0.8: инварианты любой
книги оставлены, утверждения только об образце заменены аналогом ВТБ.
Быстрые — метка `tact` (такт сервера); тесты `docs` такт не гоняет. Суждения, которые проверяются прогоном ядра, —
`tests/test_book_core.py`."""
from __future__ import annotations

import json
import re
from string import Formatter

import pytest
import yaml

try:
    from tests import support_book as S
except ImportError:                      # прогон без pytest.ini (pythonpath = .) и без tests/__init__.py
    import support_book as S

pytestmark = pytest.mark.tact

MARKS = ("  #{{WORLDS}}", "#{{WORLDS_BANK}}", "#{{OVERLAY_SHA256}}")
VERSION = "0.8"
RESULTS = S.BOOK_DIR / "results.json"
DERIVE_OUT = S.EVIDENCE / "path" / "out"                     # запись листа вывода на ядре (derive_on_engine.py)
NII_SHEET = S.EVIDENCE / "path" / "inputs" / "vtb_r2_inputs.json"   # запись листа calib-nii: ближние ключи спредов книг
# Оси, которые из полосы не выводятся никогда (MODEL §10): односторонние рисковые — по путям ключей
NEVER_OFF_BAND = ("tax.statutory", "tax.one_off.prob", "regimes.crisis.one_off_loss.amount")
CREDIT_BOOKS = ("corp_loans", "mortgage", "consumer_loans")
BOOKS = CREDIT_BOOKS + ("securities", "liquidity", "retail_current", "retail_term", "corp_funds", "wholesale")
# Ключи квартального календаря дивидендов: в годовом режиме ядро их не читает (MODEL §5.7)
CALENDAR_QUARTERLY = tuple(f"dividends.calendar.{k}" for k in ("decision_lag_quarters", "reg_deduction_lag_quarters",
                                                                  "payment_lag_quarters", "checkpoints_ahead"))
# Ключи формы банка ВТБ (договор ключей фазы 3, решения ведущего № 1, разделы A и B1; № 6, п. 2.1; № 8, п. 1.2;
# № 9, п. 1): годовой календарь, рост задан спросом (ограничение ростом капитала выключено), докапитализация и пол
# клетки, слои капитала долей RWA своей клетки, надбавка T2, распределения акционеру за концом сетки. «*» — любой хвост.
FORM_PATHS = (
    "meta.schema", "meta.labels.*", "nii.books.<b>.name", "valuation.shares_basis", "valuation.share_count_adj",
    "dividends.policy.history_test", "dividends.policy.shortfall_rule", "dividends.policy.divisor",
    "dividends.calendar.{frequency,agm_quarter,reg_deduction_quarter,payment_quarter,checkpoints}",
    "fees.volume_link", "opex.volume_link",
    "volumes.link_base", "volumes.loan_share_drift.{corporate,mortgage,retail_other}.*",
    "volumes.funds_share_drift.{retail,corporate}.*", "volumes.other_assets_fixed", "volumes.other_assets_fixed_change.*",
    "capital.rwa.density.other_assets_fixed", "capital.growth_constraint.enabled",
    "capital.recapitalization.{enabled,price_discount,decision_quarter,lookahead_quarters,min_amount}", "valuation.cell_floor",
    "capital.n20.t2_share.{enabled,from}", "capital.n20.t2_premium.{enabled,spread,base}",
    "capital.at1_share.{enabled,from,spread,base}", "capital.at1_coupon.{enabled,fixed,floating,spread}",
    "capital.{n20,n11}.deductions_fixed_share", "valuation.terminal.{other_movements,fixed_growth_share}",
    "checks.guidance_items", "checks.cir_lt.{target,tolerance,from_year,scope}", "checks.wholesale_share",
    "checks.mix_ratio_tolerance", "checks.manual_overdue_days.capital_form", "checks.funds_cost_to_key.{max,from_year}",
    "checks.volume_sign.tol", "checks.stress_sign.{loss_step,tol}",
    "valuation.sensitivities.buffer_pp",
)
# Подписи книги и поля подстановки каждой (договор ключей, раздел 1.3); у прочих подписей полей нет
LABEL_FIELDS = {
    "capital.anchor_src": {"date"}, "capital.anchor_src_estimated": {"date"}, "dividends.ladder_condition": {"threshold"},
    "dividends.pay_event": {"year", "period", "label"}, "register.flag_detail": {"gaps"},
    "register.gap_item": {"year", "period", "label", "decision_quarter", "end"}, "register.alert": {"detail"},
    "register.recommended_item": {"year", "period", "label", "dps"}, "register.rejected_item": {"year", "period", "label", "reason"},
    "register.overdue_item": {"year", "period", "label", "date"}, "register.record_words": {"year", "period", "label"},
    "register.collector_alarm": {"year", "period", "label", "end", "detail"},
    "gates.nim_anchor": {"value", "reported"},
    "periods.1": {"year"}, "periods.2": {"year"}, "periods.3": {"year"}, "periods.4": {"year"},
}
LABEL_GROUPS = {
    "capital": {"n20", "n11", "n11_observed", "n1_0", "n1_2", "n20_short", "n11_short", "anchor_src", "anchor_src_estimated",
                "observed_source"},
    "capital_bridge": {"dividend_accrual", "profit", "oci_other", "rwa_growth", "deductions", "other"},
    "dividends": {"ladder_condition", "ladder_residual_title", "ladder_residual_condition", "pay_event"},
    "register": {"flag_title", "flag_detail", "gap_item", "alert", "recommended_item", "rejected_item", "note", "overdue_item",
                 "record_words", "collector_alarm"},
    "flags": {"ras_mismatch"}, "gates": {"nim_anchor"}, "nowcast": {"targets", "ops_note", "absent"},
    "nextreport": {"fact_note", "guidance_note"},
    "terms": {"lt_level", "profit_short", "cir", "roe_lt"}, "corridors": {"guidance_gap"}, "periods": {"1", "2", "3", "4"},
    "basis": {"profit", "roe", "roe_issuer", "divisor", "dividend_issued", "dividend_outstanding"}, "peers": {"subject_basis"},
    "control": {"lines", "books"}, "rule_price": {"unconstrained"},
}
CONTROL_LINES = {"nii", "llp", "fvc", "fees", "opex", "misc", "noncore", "pbt", "ni_sh", "ci", "div", "bv", "rwa", "n20", "n11"}
# Ключи, которые выводит лист вывода на ядре, но которые пометки «на ядре» не несут: пороги гейтов — сторожа, их
# ставит сборщик рукой с причиной в комментарии (решение ведущего № 2, п. 7.7); лист их только сверяет с правилом
GATE_KEYS = "checks."


@pytest.fixture(scope="module")
def book() -> dict:
    return S.built_book()


@pytest.fixture(scope="module")
def template_text() -> str:
    return (S.BOOK_DIR / "assumptions_template.yaml").read_text(encoding="utf-8")


def switched_off(book: dict) -> set[str]:
    """Ключи, которые ядро не читает: под выключателями, ключи выключенного ограничения роста капиталом и ключи
    неактивного режима календаря дивидендов."""
    off = S.switched_off(book)
    if book["dividends"]["calendar"].get("frequency") != "quarterly":
        off.update(p for p in CALENDAR_QUARTERLY if S.has(book, p) and S.get(book, p) is None)
    gc = book["capital"]["growth_constraint"]
    if gc["enabled"] is False:
        off.update(f"capital.growth_constraint.{k}" for k in gc if k != "enabled")
    return off


def expand(token: str, book: dict) -> list[str]:
    """Шаблон пути → конкретные пути книги; незнакомая подстановка в угловых скобках — пусто (не путь книги)."""
    out = S._expand(token.replace(", ", ","), book)
    return [p for p in out if "<" not in p]


def applies(path: str, book: dict) -> bool:
    """Условные ключи книг ЧПД (пассивы, активы, кредиты, балансирующие); ключ доли кредитов по справедливой
    стоимости необязателен — у книг Т его нет."""
    if re.match(r"nii\.books\.[^.]+\.fv_share$", path):
        return S.has(book, path)
    return S._applies(path, book)


def form_paths(book: dict) -> list[str]:
    out = []
    for tok in FORM_PATHS:
        out += expand(tok, book)
    return out


# ------------------------------------------------------------------ шаблон и сборка
def test_the_template_parses_and_carries_one_of_each_build_mark(template_text):
    data = yaml.safe_load(template_text)
    assert data["meta"]["version"] == VERSION and data["meta"]["schema"] == "vtb-v1"
    lines = template_text.splitlines()
    assert sum(1 for ln in lines if ln == "  #{{WORLDS}}") == 1
    assert sum(1 for ln in lines if ln == "#{{WORLDS_BANK}}") == 1
    assert sum(1 for ln in lines if "#{{OVERLAY_SHA256}}" in ln) == 1
    assert set(data["worlds"]) == {"source", "build", "quarter_rule", "ids", "overlay"}   # миры вписывает сборка
    assert "worlds_bank" not in data
    assert not any("@@" in ln for ln in lines)


def test_the_build_reproduces_the_committed_machine_book():
    y, j, _ = S.build_module().render()
    assert (S.BOOK_DIR / "assumptions.yaml").read_text(encoding="utf-8") == y
    assert (S.BOOK_DIR / "assumptions.json").read_text(encoding="utf-8") == j


def test_the_build_is_deterministic_and_json_equals_yaml():
    m = S.build_module()
    y1, j1, b1 = m.render()
    y2, j2, b2 = m.render()
    assert (y1, j1) == (y2, j2)
    assert json.loads(j1) == yaml.safe_load(y1) == b1
    assert not any(ln.rstrip() in MARKS for ln in y1.splitlines())


def test_the_build_check_mode_exits_zero():
    done = S.run_script(S.BOOK_DIR / "build_assumptions.py", "--check")
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_core_schema_accepts_the_form_of_the_book(book):
    """Схема ядра принимает форму книги. Пока ядро собирается, ветвь, которую схема уже знает, а ядро ещё не исполняет,
    отказом не считается (`pending_ok`); незнакомый ключ, неверный тип и нарушение взаимных ограничений — отказ всегда.
    Когда ядро исполняет все ветви, проверка становится полной."""
    from model import book_schema

    try:
        book_schema.validate(book, pending_ok=True)
    except TypeError:                                    # ядро собрано: проверки одной формы больше нет
        book_schema.validate(book)


# ------------------------------------------------------------------ полнота ключей
def test_every_key_of_the_second_bank_form_is_in_the_book_and_not_null(book):
    """Ключи договора (квартальный календарь, делитель, связь с объёмом, премии траекториями, рост по капиталу, новые
    гейты, подписи) стоят в книге явно и не null: ось полосы и подмена пути требуют существующего ключа."""
    paths = form_paths(book)
    assert len(paths) > 45
    missing = [p for p in paths if "*" not in p and not S.has(book, p)]
    nulls = [p for p in paths if "*" not in p and S.has(book, p) and S.get(book, p) is None]
    assert missing == [] and nulls == []
    for p in (p for p in paths if "*" in p):
        assert S.get(book, p.split(".*")[0]), p


def app_a_optional(book: dict) -> set[str]:
    """Пути, которых в книге может не быть, по правилам самого прил. A: ключ с пометкой **[П]** (поведенческий ключ
    панели: в схеме необязателен — пометка стоит в той же части перечня, до точки с запятой) и путь над такими ключами;
    при годовом календаре дивидендов — ключи квартального режима («отсутствуют или равны null»)."""
    out = set()
    for clause in re.split(r";|\n\s*\n", S.app_a_text()):
        if "[П]" in clause:
            out.update(p for tok in re.findall(r"`([^`]+)`", clause) for p in _app_a_token(tok, book))
    out |= {p.rsplit(".", 1)[0] for p in out if "." in p}
    if book["dividends"]["calendar"].get("frequency") != "quarterly":
        out |= {p for p in S.app_a_paths(book) if p.startswith(CALENDAR_QUARTERLY + ("dividends.policy.base_window_quarters",))}
    return out


@pytest.mark.docs
def test_every_app_a_path_is_in_the_book_and_not_null(book):
    """Каждый путь прил. A — в книге и не null, кроме ключей, которые прил. A само называет необязательными (пометка
    **[П]**, ключи неактивного режима календаря) и ключей под выключателями."""
    paths = [p for tok in re.findall(r"`([^`]+)`", S.app_a_text())
             for p in _app_a_token(tok, book)]
    paths = list(dict.fromkeys(paths))
    assert len(paths) > 300
    off = switched_off(book)
    optional = app_a_optional(book)
    missing = [p for p in paths if "*" not in p and not S.has(book, p) and p not in optional]
    nulls = [p for p in paths if "*" not in p and S.has(book, p) and S.get(book, p) is None and p not in off]
    assert missing == [] and nulls == []
    for p in (p for p in paths if "*" in p):                      # словарь по годам — не пуст
        assert S.get(book, p.split(".*")[0]) is not None


def _app_a_token(tok: str, book: dict) -> list[str]:
    tok = tok.strip()
    if " " in tok.replace(", ", ",") or "." not in tok or tok.split(".")[0] not in S.TOP or "/" in tok:
        return []
    return [p for p in expand(tok, book) if applies(p, book)]


@pytest.mark.docs
def test_every_leaf_of_the_book_is_named_by_app_a_or_by_the_form(book):
    """Каждый лист книги назван приложением A методики либо перечнем ключей второй формы банка."""
    paths = [p for tok in re.findall(r"`([^`]+)`", S.app_a_text()) for p in _app_a_token(tok, book)] + form_paths(book)
    exact = [p for p in paths if "*" not in p]
    star = [p.split("*")[0] for p in paths if "*" in p]
    unnamed = [path for path, _ in S.leaves(book)
               if not any(path.split("[")[0] == p or path.split("[")[0].startswith(p + ".") for p in exact)
               and not any(path.startswith(s) for s in star)]
    assert unnamed == []


def test_nulls_only_under_switched_off_keys(book):
    off = switched_off(book)
    nulls = {p for p, v in S.leaves(book) if v is None}
    assert nulls == off, sorted(nulls ^ off)
    # выключатели книги ВТБ: относительная стоимость риска сегментов включена (её ключи заполнены), валютная часть RWA
    # и переоценка облигаций через ОПУ — выключены
    assert {sw: S.get(book, sw) for sw in S.SWITCHES} == {"credit.segment_relative.enabled": True,
                                                         "capital.rwa.fx.enabled": False, "other.fvtpl_bond_reval": False}
    # решения ведущего № 1, разделы A, B1 и E: недостающий капитал добирается выпуском акций; рост задан спросом
    assert book["capital"]["recapitalization"]["enabled"] is True
    assert book["dividends"]["buyback"]["enabled"] is False
    assert book["capital"]["growth_constraint"]["enabled"] is False


# ------------------------------------------------------------------ согласованность значений
def test_probability_tables_sum_to_one(book):
    j = book["joint"]
    tables = [j["world_prob"], j["world_prob_market_implied"], j["regime_prob"], *j["reg_prob_given_regime"].values()]
    for axis in book["valuation"]["uncertainty"]["axes"]:
        if axis["kind"] == "dict":
            tables += [axis["low"], axis["high"]]
    for t in tables:
        assert abs(sum(t.values()) - 1) < 1e-4, t
    for t in tables[:3] + list(j["reg_prob_given_regime"].values()):
        assert abs(sum(t.values()) - 1) < 1e-12, t
    assert set(j["regime_prob"]) == set(book["regimes"]["ids"])
    assert set(j["world_prob"]) == set(book["worlds"]["ids"])
    assert all(set(t) == set(book["capital"]["reg_scenarios"]["ids"]) for t in j["reg_prob_given_regime"].values())


def test_governance_discount_is_the_sum_of_channels(book):
    g = book["valuation"]["governance"]
    assert abs(g["discount"] - sum(c["sign"] * c["value"] for c in g["components"])) < 1e-12
    # у книги ВТБ каналов дисконта за управление нет: дисконт ноль, оси нет, мост его не применяет
    assert g["components"] == [] and g["discount"] == 0.0 and book["bridge"]["governance_applies"] is False
    assert not any("valuation.governance.discount" in a["paths"] for a in book["valuation"]["uncertainty"]["axes"])


def test_uncertainty_axes_hold_the_book_value_inside_their_range(book):
    unc = book["valuation"]["uncertainty"]
    assert len(unc["axes"]) == 46 and unc["off_band_axes"] == []
    assert sum(1 for a in unc["axes"] if a["kind"] == "dict") == 3 and sum(1 for a in unc["axes"] if a["kind"] == "bundle") == 8
    names = [a["name"] for a in unc["axes"]]
    assert len(set(names)) == len(names)
    for a in unc["axes"] + unc["off_band_axes"]:
        assert a["dist"] == "triangular" and a["kind"] in ("value", "shift", "dict", "bundle")
        for p in a["paths"]:
            assert S.has(book, p) and S.get(book, p) is not None, (a["name"], p)
        if a["kind"] == "bundle":                                      # концы — словари ровно по путям; ведущий путь — между концами
            assert set(a["low"]) == set(a["high"]) == set(a["paths"]) and len(set(a["paths"])) == len(a["paths"]), a["name"]
            lead = a["paths"][0]
            assert a["low"][lead] < S.get(book, lead) < a["high"][lead], a["name"]
        if a["kind"] == "value":
            for p in a["paths"]:
                assert a["low"] <= S.get(book, p) <= a["high"], (a["name"], p)
        elif a["kind"] == "shift":
            assert a["low"] <= 0 <= a["high"], a["name"]


def test_reverse_dcf_axes_search_covers_range(book):
    rev = book["valuation"]["reverse_dcf"]
    # минимальный набор строк второго круга книги ВТБ: уровень маржи, передача ставки, CoR сквозь цикл (строки «смеси»
    # сценариев требования у книги нет — её механику ядра сверяет tests/test_core2_reverse.py на фикстуре образца)
    assert len(rev["axes"]) == 3 and rev["axis_follow"] == "both"         # ось идёт за проверяемым значением обоими концами
    assert rev["edge_refine_rub"] == book["valuation"]["headline"]["print_step"]   # решение у края диапазона — на полной полосе
    for a in rev["axes"]:
        assert a["kind"] in ("value", "shift", "mix")
        for p in a["paths"]:
            assert S.has(book, p), (a["name"], p)
        assert a["search"][0] <= a["range"][0] <= a["range"][1] <= a["search"][1], a["name"]
    assert [a["paths"][0] for a in rev["axes"]] == ["nii.nim_lt_target_mgmt", "nii.transmission.target", "regimes.soft.cor.LT"]
    assert rev["refine_rows"] == ["nii.nim_lt_target_mgmt"]
    band = {tuple(a["paths"]): a for a in book["valuation"]["uncertainty"]["axes"]}
    for a in rev["axes"]:
        b = band.get(tuple(a["paths"]))
        if b is None or a["kind"] == "mix" or b["kind"] == "bundle":    # связка строкой не бывает
            continue
        if a["paths"] == ["nii.transmission.target"]:
            # передача: диапазон строки — носитель измеренной передачи (края — варианты transmission_low_m068 и
            # transmission_high_p022), ось полосы — P10 и P90 произведения двух суждений (решение № 5, п. 3.4) — внутри него
            variants = {v["id"]: v["overrides"] for v in book["valuation"]["reference_variants"]}
            assert a["range"] == [variants["transmission_low_m068"]["nii.transmission.target"],
                                  variants["transmission_high_p022"]["nii.transmission.target"]]
            assert a["range"][0] < b["low"] < b["high"] < a["range"][1]
        else:                                                           # диапазон книги строки = ось полосы тех же путей
            assert a["range"] == [b["low"], b["high"]], a["name"]
    assert rev["bank_rows"] == ["implied_roe_through_cycle", "implied_cost_of_equity", "market_cap_minus_bv",
                                "book_value_per_share"]


def test_issuer_trajectories_end_on_lt_levels_by_the_last_year(book):
    last_year = int(book["meta"]["last_period"][:4])
    for path, v in S.leaves({k: book[k] for k in book if k not in ("worlds", "worlds_bank")}):
        if path.endswith(".LT_from"):
            assert int(v) <= last_year, path
        m = re.search(r"\.(\d{4})(Q\d|H\d)$", path)
        if m:
            assert int(m.group(1)) != last_year, path                 # ключ квартала/полугодия в году last_period запрещён


def test_year_keys_are_the_means_of_their_quarter_keys(book):
    """Ключ года при четырёх квартальных ключах — их среднее (MODEL §0.4): иначе ядро отказывает."""
    def walk(node, path=""):
        if isinstance(node, dict):
            quarters: dict[str, list[float]] = {}
            for k, v in node.items():
                m = re.fullmatch(r"(\d{4})Q[1-4]", str(k))
                if m and isinstance(v, (int, float)):
                    quarters.setdefault(m.group(1), []).append(float(v))
            for y, vals in quarters.items():
                if len(vals) == 4 and y in node:
                    assert abs(sum(vals) / 4 - node[y]) < 1e-9, (path, y)
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
    walk({k: book[k] for k in book if k not in ("worlds", "worlds_bank")})


def test_meta_company_and_prices(book):
    meta = book["meta"]
    c = meta["company"]
    assert c == {"name": "ВТБ", "tickers": ["VTBR"], "main_ticker": "VTBR", "share_classes": {"VTBR": "ordinary"},
                 "cbr_regnum": 1000, "fiscal_year_end": "12-31"}
    assert set(meta["market_price"]) == set(c["tickers"]) and meta["market_price"]["VTBR"] > 0
    for k in ("date", "facts_date", "valuation_date", "curve_as_of"):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta[k])
    assert meta["valuation_date"] == meta["date"] >= meta["facts_date"]
    assert (meta["facts_date"], meta["anchor_period"], meta["first_period"], meta["last_period"]) == \
        ("2026-06-30", "2026Q2", "2026Q3", "2036Q4")
    assert book["valuation"]["uncertainty"]["seed"] == int(meta["date"].replace("-", ""))    # зерно — дата книги
    assert "чистая прибыль, приходящаяся на акционеров банка" in meta["basis"]


# ------------------------------------------------------------------ решения ведущего числами книги
# Решения ведущего ВТБ — notes/LEAD-DECISIONS-1…9.md папки передачи; в дереве их пересказывают шапка и комментарии шаблона
# у ключей (метки «решение ведущего № …»). Здесь — числа, которые решения называют прямо; числа, выведенные на ядре по
# правилу решения, сверяет запись листа вывода (test_frozen_numbers_are_the_record_of_the_derivation).
def test_lead_decisions_on_probabilities_regimes_and_the_form_of_the_book(book):
    """Решения ведущего ВТБ № 1 (разделы A, B1, B5, E5), № 2 (п. 4.1), № 3 (п. 5.5) — числами книги: режимы и их
    вероятности, сценарии требования к капиталу с «послаблением» в кризисе, годовой календарь дивидендов с выплатой
    остатком над требованием, рост, заданный спросом, докапитализация с решением в 4-м квартале и пол клетки."""
    assert book["regimes"]["ids"] == ["soft", "norm", "downturn", "crisis"] and book["regimes"]["cor_basis"] == "mgmt"
    assert [book["regimes"][r]["name"] for r in book["regimes"]["ids"]] == \
        ["Мягкая посадка", "Нормализация", "Корпоративный спад", "Кризис"]
    assert book["joint"]["regime_prob"] == {"soft": 0.15, "norm": 0.40, "downturn": 0.30, "crisis": 0.15}   # B5
    scen = book["capital"]["reg_scenarios"]["ids"]
    assert scen == ["schedule", "mid", "strict", "relief"]                # «послабление» — четвёртый сценарий (сетка 48 клеток)
    for r in ("soft", "norm", "downturn"):                                 # устав §3: середина книг Сбера и Т; «послабления» нет
        assert book["joint"]["reg_prob_given_regime"][r] == {"schedule": 0.30, "mid": 0.45, "strict": 0.25, "relief": 0.0}
    # в кризисе «послабление» 0,70 — на месте «по графику» (масса переносится; решения № 2, п. 4.1 и № 3, п. 5.5)
    assert book["joint"]["reg_prob_given_regime"]["crisis"] == {"schedule": 0.0, "mid": 0.25, "strict": 0.05, "relief": 0.70}
    d = book["dividends"]
    assert d["calendar"] == {"frequency": "annual", "agm_quarter": 2, "reg_deduction_quarter": 3, "payment_quarter": 3,
                             "checkpoints": [3, 4]}
    assert (d["policy"]["shortfall_rule"], d["policy"]["divisor"], d["policy"]["history_test"]) == \
        ("residual_above_requirement", "issued", "none")
    assert d["policy"]["threshold"] == 0.0 and d["policy"]["steps"] == [] and d["policy"]["deduct_at1_after_tax"] is False
    assert d["crisis"] == {"skip_in_shock_year": True, "catch_up": False} and d["buyback"] == {"enabled": False}
    assert book["capital"]["growth_constraint"]["enabled"] is False
    rec = book["capital"]["recapitalization"]
    assert rec["enabled"] is True and (rec["decision_quarter"], rec["lookahead_quarters"]) == (4, 1)
    axes = {a["paths"][0]: a for a in book["valuation"]["uncertainty"]["axes"]}
    disc = axes["capital.recapitalization.price_discount"]
    assert disc["low"] <= rec["price_discount"] <= disc["high"]
    assert book["valuation"]["cell_floor"] == 0.0                         # ограниченная ответственность: клетка — max(V, 0)
    variants = {v["id"] for v in book["valuation"]["reference_variants"]}
    assert "recap_off_gap_at_end" in variants                             # форма Сбера — справочный вариант


def test_lead_decisions_on_margin_volumes_and_capital_are_in_the_book(book):
    """Решения ведущего ВТБ № 3 (разделы 3 и 4), № 4 (п. 3.3), № 5 (пп. 3.4–3.5), № 6 (п. 2.1), № 8 (п. 1.2), № 9 (п. 1)
    и B8 — числами книги: раскладка сжатия маржи, премии роста до 2031 года, доля вычетов якоря, постоянная в рублях, на
    обеих сторонах, реализованная передача, ближний сдвиг маржи с ходом к 2028 году, слои капитала долей RWA своей
    клетки, надбавка T2 и распределения акционеру за концом сетки."""
    nii = book["nii"]
    assert nii["phi_split"] == 0.38 and nii["transmission"]["target"] == -0.0115
    axes = {a["paths"][0]: a for a in book["valuation"]["uncertainty"]["axes"]}
    assert (axes["nii.phi_split"]["low"], axes["nii.phi_split"]["high"]) == (0.0, 0.76)
    v = book["volumes"]
    assert v["share_drift_until"] == 2031 and v["lt_from"] == 2033 and v["link_base"] == "iea"
    facts = json.loads((S.FACTS_DIR / "balance.json").read_text(encoding="utf-8"))
    share = facts["fixed_share_of_deductible"]["v"]                       # узел фактов — на обеих сторонах (№ 4, п. 3.3)
    assert book["capital"]["n20"]["deductions_fixed_share"] == book["capital"]["n11"]["deductions_fixed_share"] == share
    near = book["regimes"]["near_nim_shift"]                              # № 5, п. 3.5: ступень σ0 снята, сход к 2028 году
    assert near["LT"] == 0.0 and near["LT_from"] == 2028
    n20 = book["capital"]["n20"]
    assert n20["t2_share"] == {"enabled": True, "from": "2029Q1"}           # № 6, п. 2.1
    assert n20["t2_premium"] == {"enabled": True, "spread": 0.025, "base": "anchor"}   # № 8, п. 1.2
    at1 = book["capital"]["at1_share"]
    assert at1 == {"enabled": True, "from": book["meta"]["first_period"], "spread": 0.04, "base": "anchor"}   # № 8, п. 1.2; № 9, п. 1
    assert book["valuation"]["terminal"]["other_movements"] == "flat_rub"
    variants = {v["id"] for v in book["valuation"]["reference_variants"]}
    assert {"at1_anchor_rub", "at1_from_2029", "t2_premium_off", "om_terminal_none", "t2_flat_rub", "t2_amortizing",
            "t2_modal_rub"} <= variants
    assert book["checks"]["funds_cost_to_key"] == {"max": 0.76, "from_year": 2030}   # № 3, раздел 4: сторож рукой


def _derive_record() -> dict:
    return json.loads((DERIVE_OUT / "derive_out.json").read_text(encoding="utf-8"))


def test_frozen_numbers_are_the_record_of_the_derivation(book):
    """Замороженные числа шаблона — запись вывода на ядре (`evidence/path/out/derive_out.json`, команда
    `ops/tools/rederive.py`): ключи записи равны ключам книги; запись начата со значений `derive_start.json` и сошлась;
    ключ цели ЧПМ — само суждение (стационарная маржа мира уровня равна ему); ближние ключи спредов книг лист сверил с
    записью листа calib-nii; поле доли кредитов окна гейта сверки с окном — запись."""
    record = _derive_record()
    first = json.loads((DERIVE_OUT / "derive_start.json").read_text(encoding="utf-8"))
    start, before = first["keys"], first["before"]
    keys = record["keys"]
    assert set(keys) == set(start) == set(before) and keys
    conv = record["convergence"]
    assert conv["converged"] and conv["rounds"][-1]["max_relative_change"] < conv["tol"]
    assert record["frozen_check"]["nim_stationary_ok"]
    level = record["level"]
    assert "nii.nim_lt_target_mgmt" not in keys and level["key"] == book["nii"]["nim_lt_target_mgmt"]
    assert level["world"] == book["nii"]["transmission"]["level_world"] and level["ok"]
    assert level["stationary"] == pytest.approx(level["key"], abs=1e-9)
    assert record["near_spreads"]["same"] and record["near_spreads"]["diff"] == []
    for dotted, value in keys.items():
        node = book
        for part in dotted.split("."):
            node = node[part]
        if isinstance(value, dict):             # ключи года — средние кварталов: в шаблоне записаны девятью знаками
            assert set(node) == set(value) and all(node[k] == pytest.approx(value[k], abs=1e-9) for k in value), dotted
        else:
            assert node == value, dotted


def template_line(lines: list[str], dotted: str) -> int | None:
    """Номер строки ключа `dotted` в шаблоне (блочный YAML: путь — по отступам); у ключа внутри строчного словаря —
    строка ближайшего предка, записанного блоком."""
    parts, stack, best = dotted.split("."), [], (0, None)
    for i, ln in enumerate(lines):
        s = ln.lstrip(" ")
        m = re.match(r'"?([A-Za-z0-9_]+)"?\s*:', s)
        if not m or s.startswith("#"):
            continue
        ind = len(ln) - len(s)
        while stack and stack[-1][0] >= ind:
            stack.pop()
        stack.append((ind, m.group(1)))
        path = [k for _, k in stack]
        if path == parts[:len(path)] and len(path) > best[0]:
            best = (len(path), i)
            if len(path) == len(parts):
                break
    return best[1]


def test_numbers_derived_on_the_engine_are_marked_in_the_template(template_text):
    """Числа, которые выводит лист вывода на ядре (ключи записи `derive_out.json`: доли и пути вычетов, путь постоянной
    части, выплата, приток выпуска, премии роста, ближний сдвиг, прочие доходы, корни расходов и услуг, инструменты
    капитала), несут в комментарии ключа (его строка и строки-продолжения под ней) пометку «ВЫВОДИТСЯ НА ЯДРЕ» (до
    вывода) или «ВЫВЕДЕНО НА ЯДРЕ» (после): число без
    пометки — число, которое при следующей версии книги забудут вывести заново. Пороги гейтов — сторожа (ставятся
    рукой). Ключ цели ЧПМ пометки не несёт: у книги с миром уровня он — само суждение."""
    lines = template_text.splitlines()
    key_line = next(i for i, ln in enumerate(lines) if ln.strip().startswith("nim_lt_target_mgmt:"))
    assert "НА ЯДРЕ" not in "\n".join(lines[key_line:key_line + 9])
    unmarked = []
    for dotted in _derive_record()["keys"]:
        if dotted.startswith(GATE_KEYS):
            continue
        at = template_line(lines, dotted)
        assert at is not None, dotted
        end = at + 1                                     # комментарий ключа — его строка и строки-продолжения под ней
        while end < len(lines) and lines[end].lstrip().startswith("#"):
            end += 1
        near = "\n".join(lines[at:end])
        if not re.search(r"ВЫВОДИТСЯ НА ЯДРЕ|ВЫВЕДЕНО НА ЯДРЕ", near):
            unmarked.append(dotted)
    assert unmarked == []


def test_crisis_keys_lie_in_the_shock_year(book):
    """Год шока = год якоря + `shock_year_offset`; квартальный профиль CoR кризиса, период разового убытка, первый
    год `loan_growth_override` и минимум множителя RWA лежат в году шока (иначе ядро отказывает `BookError`)."""
    crisis = book["regimes"]["crisis"]
    off = crisis["shock_year_offset"]
    assert isinstance(off, int) and not isinstance(off, bool) and off >= 1
    shock = int(book["meta"]["anchor_period"][:4]) + off
    assert crisis["one_off_loss"]["period"][:4] == str(shock)
    quarters = sorted(k for k in crisis["cor"] if "Q" in str(k))
    assert quarters == [f"{shock}Q{k}" for k in (1, 2, 3, 4)]
    assert min(int(y) for y in crisis["loan_growth_override"]) == shock
    assert "rwa_density_mult" not in book["regimes"]["norm"]
    if "rwa_density_mult" not in crisis:            # у книги ВТБ множителя плотности RWA кризиса нет
        return
    mult = crisis["rwa_density_mult"]
    assert mult[str(shock)] == min(v for k, v in mult.items() if k != "LT_from") and mult[str(shock - 1)] == 1.0
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0].startswith("regimes.crisis.rwa_density_mult"))
    assert ax["paths"] == [f"regimes.crisis.rwa_density_mult.{shock}"] and ax["kind"] == "value" and ax["high"] == 1.0


def test_books_flags_and_spread_floors_are_consistent(book):
    """Девять книг: подпись у каждой; балансирующие книги сдвига σ0 и сжатия φ не несут; у обеих книг средств
    физлиц флаги одинаковы; сжатие и сдвиг несут одни и те же книги; полы спреда и плотности RWA — по трём кредитным
    книгам; доли σ0 и φ лежат внутри своих осей. Полы — в пределах ±20 п.п.: у книги ВТБ пол кредитов юрлиц и ипотеки
    к ключевой ниже нуля (у образца все полы были неотрицательны)."""
    nii = book["nii"]
    books = nii["books"]
    assert list(books) == list(BOOKS)
    assert all(isinstance(v["name"], str) and v["name"].strip() for v in books.values())
    assert books["wholesale"]["name"] == "Оптовое фондирование" and not any("fv_share" in v for v in books.values())
    loans = [b for b, v in books.items() if "sector" in v]
    assert loans == list(CREDIT_BOOKS)
    assert [b for b, v in books.items() if v.get("balancing")] == ["securities", "liquidity", "wholesale"]
    assert not any(v["lt_shift"] or v["phi"] for v in books.values() if v.get("balancing"))
    assert books["retail_current"]["lt_shift"] is books["retail_term"]["lt_shift"]
    assert books["retail_current"]["phi"] is books["retail_term"]["phi"]
    assert {b for b, v in books.items() if v["phi"]} == {b for b, v in books.items() if v["lt_shift"]}
    assert [(books[b]["sector"], books[b]["cor_segment"]) for b in loans] == \
        [("corporate", "corporate"), ("mortgage", "retail"), ("retail_other", "retail")]
    for key in ("sigma0_split", "phi_split"):
        ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"] == [f"nii.{key}"])
        assert ax["kind"] == "value" and 0.0 <= ax["low"] <= nii[key] <= ax["high"] <= 1.0
    floors = book["checks"]["lt_spread_floor"]
    assert set(floors) == set(loans) and all(isinstance(v, float) and -0.20 < v < 0.20 for v in floors.values())
    dens = book["capital"]["rwa"]["density"]
    assert set(dens) == set(loans) | {"securities", "liquidity", "other_assets", "other_assets_fixed", "other_assets_fixed_change"}
    assert set(book["meta"]["labels"]["control"]["books"]) == set(loans)


# Единица оси для печати (MODEL §10, PAYLOAD §0.2): код и правило по ПУТЯМ оси, не по словам имени
AXIS_UNITS = {"pct", "pp", "share", "number", "years", "bn"}       # коды выпуска (model.book_schema.UNIT_CODES)
YEARS_PATHS = ("oci.fvoci_duration", "oci.fvoci_maturity")
PP_MARKS = ("_pp", "nim_shift", "mgmt_buffer", "spread")
BN_PATHS = ("regimes.crisis.one_off_loss.amount", "capital.n20.t2", "noncore.result_real", "other.misc_net_real",
            "equity.other_movements", "volumes.other_assets_fixed", "volumes.other_assets_fixed_change")


def is_money(path: str) -> bool:
    """Путь денежного ключа (млрд ₽): по началу пути и вычеты сценария в рублях."""
    return any(path == p or path.startswith(p + ".") for p in BN_PATHS) or ".deduction_rub." in path


def test_scalar_axes_carry_the_unit_of_their_paths(book):
    """У каждой скалярной оси — поле `unit` из кодов выпуска; у оси-словаря его нет. Сдвиг доли (вид `shift` на долях,
    пути с `_pp`, сдвиг ЧПМ режима, запас, спред) — `pp`; срок — `years`; суммы в млрд ₽ — `bn` по путям денежных ключей;
    коэффициент больше единицы процентом не печатается. У оси-связки единица — единица её числа: ведущий денежный путь —
    `bn`, `bn` — только у связки с денежным путём; правила долей — по ведущему пути, концы долей — по путям не в рублях."""
    for a in book["valuation"]["uncertainty"]["axes"]:
        if a["kind"] == "dict":
            assert "unit" not in a, a["name"]
            continue
        unit, paths = a.get("unit"), a["paths"]
        assert unit in AXIS_UNITS, (a["name"], unit)
        money = any(is_money(p) for p in paths)
        if a["kind"] == "bundle":
            assert unit != "bn" or money, a["name"]
            assert not is_money(paths[0]) or unit == "bn", a["name"]
            money, paths = unit == "bn", paths[:1]
        assert (unit == "bn") == money, a["name"]
        if not money and (a["kind"] == "shift" or any(m in p for p in paths for m in PP_MARKS)):
            assert unit == "pp", a["name"]
        assert (unit == "years") == any(p in YEARS_PATHS for p in paths), a["name"]
        if unit in ("pct", "pp", "share"):
            ends = [v for e in ("low", "high")
                    for p, v in (a[e].items() if a["kind"] == "bundle" else [(paths[0], a[e])]) if not is_money(p)]
            assert max(abs(v) for v in ends) <= 1.0, a["name"]


def test_the_regime_floor_is_a_share_of_the_base_probability(book):
    ru = book["joint"]["regime_update"]
    share, prior = ru["floor_share"], book["joint"]["regime_prob"]
    assert isinstance(share, float) and 0.0 < share < 1.0 and ru["window_obs"] == 4 and ru["max_shift_pp"] == 0.05
    floors = {r: share * p for r, p in prior.items()}
    assert abs(sum(floors.values()) - share) < 1e-12
    assert floors["soft"] == pytest.approx(0.0495) and floors["crisis"] == pytest.approx(0.0495)
    assert all(floors[r] < prior[r] for r in prior)


def off_band_report(book: dict, rows: list, point: float) -> dict:
    """Три условия оси вне полосы (MODEL §10) по строкам цены ошибки суждения: (1) ожидаемая доля размах² / Σ размах²
    меньше 1 %; (2) |сдвиг положения оси| < print_step / 10; (3) |Σ сдвигов по осям вне полосы| ≤ print_step / 10.
    Сдвиг положения — (цена_high + цена_low − 2 × точка) / 6. Возвращает {имя оси или «Σ»: [что нарушено]}."""
    limit = book["valuation"]["headline"]["print_step"] / 10
    by_name = {r["name"]: r for r in rows}
    total = sum(r["swing"] ** 2 for r in rows if r.get("swing") is not None)
    bad, shifts = {}, 0.0
    for a in book["valuation"]["uncertainty"]["off_band_axes"]:
        r = by_name.get(a["name"])
        if r is None:
            bad[a["name"]] = ["нет строки цены ошибки суждения — нужен прогон ядра на этой книге"]
            continue
        shift = (r["price_high"] + r["price_low"] - 2 * point) / 6
        shifts += shift
        why = []
        if not r["swing"] ** 2 / total < 0.01:
            why.append("доля размаха не меньше 1 %")
        if not abs(shift) < limit:
            why.append(f"сдвиг положения {shift:+.2f} ₽")
        if a["kind"] == "dict" or any(p.startswith(NEVER_OFF_BAND) for p in a["paths"]):
            why.append("ось-словарь или односторонняя рисковая ось")
        if why:
            bad[a["name"]] = why
    if abs(shifts) > limit:
        bad["Σ"] = [f"сумма сдвигов положения {shifts:+.2f} ₽ больше {limit} ₽"]
    return bad


def test_off_band_axes_meet_the_three_conditions(book):
    """Ось вне полосы допустима только при трёх условиях MODEL §10 (у книги ВТБ 0.8 список пуст — все оси в полосе).
    Проверка — по `results.json`; с непустым списком результаты обязаны быть этой книги."""
    off = book["valuation"]["uncertainty"]["off_band_axes"]
    names = {a["name"] for a in book["valuation"]["uncertainty"]["axes"]}
    assert not [a["name"] for a in off if a["name"] in names]
    if not off:
        return
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert res["book_version"] == book["meta"]["version"], "оси вне полосы проверяются по результатам этой книги"
    assert off_band_report(book, res["judgements"], res["headline"]["point"]) == {}


def test_the_off_band_rule_catches_an_asymmetric_and_a_wide_axis(book):
    """Правило на заглушке: узкая симметричная ось проходит; асимметричная, широкая, налоговая и сумма сдвигов — нет.
    Строки заглушки посчитаны на шаг печати 5 ₽ — у заглушки свой шаг (у книги ВТБ шаг 1 ₽, правило от книги не зависит)."""
    step = 5.0
    point = 400.0

    def row(name, lo, hi):
        return {"name": name, "price_low": lo, "price_high": hi, "swing": abs(hi - lo)}

    def variant(axes):
        b = {"valuation": {"headline": {"print_step": step}, "uncertainty": {"off_band_axes": axes}}}
        return off_band_report(b, rows, point)

    rows = [row("главная", 300.0, 520.0), row("узкая", 399.0, 401.0), row("асимметричная", 400.0, 400.0 - step),
            row("широкая", 370.0, 430.0), row("налог", 400.0, 399.5), row("ещё узкая", 399.6, 400.2),
            row("вниз 1", 400.0, 398.2), row("вниз 2", 400.0, 398.4)]
    ax = {n: {"name": n, "kind": "value", "paths": ["x.y"]}
          for n in ("узкая", "асимметричная", "широкая", "ещё узкая", "вниз 1", "вниз 2")}
    ax["налог"] = {"name": "налог", "kind": "shift", "paths": ["tax.statutory"]}
    assert variant([ax["узкая"], ax["ещё узкая"]]) == {}
    assert list(variant([ax["асимметричная"]])) == ["асимметричная", "Σ"]
    assert list(variant([ax["широкая"]])) == ["широкая"]
    assert list(variant([ax["налог"]])) == ["налог"]
    assert list(variant([ax["вниз 1"], ax["вниз 2"]])) == ["Σ"]
    assert "нет строки" in variant([{"name": "новая", "kind": "value", "paths": ["x.y"]}])["новая"][0]


def test_the_near_nim_shift_covers_the_near_path_only(book):
    """Ближний сдвиг ЧПМ (решение ведущего ВТБ № 5, п. 3.5): квартальные ключи — от первого прогнозного квартала до
    конца 2027 года (ступень σ0 на границе 2026К4 → 2027К1 снята, сход линейно к 2028 году), ключ года при четырёх
    квартальных — их среднее, с 2028 года — 0. Оси полосы у сдвига нет (он выведен на ядре; варианты no_near_shift и
    near_sigma0_step_kept)."""
    near = book["regimes"]["near_nim_shift"]
    first = book["meta"]["first_period"]
    q_keys = sorted(k for k in near if "Q" in k)
    y0 = int(first[:4])
    expected = [f"{y0}Q{k}" for k in range(int(first[5]), 5)] + [f"{y}Q{k}" for y in range(y0 + 1, 2028) for k in (1, 2, 3, 4)]
    assert q_keys == expected
    for y in sorted({k[:4] for k in q_keys}):
        qs = [near[k] for k in q_keys if k.startswith(y)]
        if len(qs) == 4:
            assert near[y] == pytest.approx(sum(qs) / len(qs), abs=1e-9), y
    assert near["LT"] == 0.0 and near["LT_from"] == 2028 and S.year_value({k: v for k, v in near.items() if "Q" not in k}, 2029) == 0.0
    assert not any(a["paths"][0].startswith("regimes.near_nim_shift") for a in book["valuation"]["uncertainty"]["axes"])
    variants = {v["id"]: v["overrides"] for v in book["valuation"]["reference_variants"]}
    assert set(variants["no_near_shift"]["regimes.near_nim_shift"]) == set(near)   # все ключи словаря на месте
    assert all(book["regimes"][r]["nim_shift"]["2026"] == 0.0 for r in book["regimes"]["ids"])


def test_value_axes_on_year_keys_do_not_meet_quarter_keys(book):
    """Ось `value` на ключе года траектории с квартальными ключами этого года — отказ ядра (MODEL §0.4); ось `shift`
    на таком году обязана двигать ключ года и все его квартальные ключи вместе (иначе ключ года перестаёт быть средним)."""
    unc = book["valuation"]["uncertainty"]
    for a in unc["axes"] + unc["off_band_axes"]:
        for p in a["paths"]:
            head, _, key = p.rpartition(".")
            if not (key.isdigit() and S.has(book, head) and isinstance(S.get(book, head), dict)):
                continue
            quarters = [f"{head}.{k}" for k in S.get(book, head) if str(k).startswith(key + "Q")]
            if a["kind"] == "value":
                assert not quarters, (a["name"], p)
            elif quarters:
                assert set(quarters) <= set(a["paths"]), (a["name"], p)


def test_the_capital_instruments_trajectory_is_quarterly_and_ends_flat(book):
    """Инструменты капитала (решение ведущего ВТБ B8; № 2, п. 4.6; № 6, п. 2.1): срочные субординированные инструменты
    без прибыли — 339,1 млрд ₽ МСФО якоря (слот фактов t2_recognized шире: дополнительный капитал формы 0409805 с
    прибылью до аудита) — плоско по 4К2028 (ключи квартала якоря и 2028 года), с 1К2029 — доля RWA конца 2028 года
    (квартальные ключи до года перед последним, на модальной клетке; при ключе t2_share ядро читает их только по 4К2028);
    последний год — ключом года, равным LT; путь не убывает; оси полосы нет (варианты t2_flat_rub, t2_amortizing,
    t2_modal_rub)."""
    t2 = book["capital"]["n20"]["t2"]
    anchor, last = book["meta"]["anchor_period"], int(book["meta"]["last_period"][:4])
    share_from = book["capital"]["n20"]["t2_share"]["from"]
    y_from = int(share_from[:4])
    q_keys = [k for k in t2 if "Q" in k]
    assert q_keys == [anchor] + [f"{y}Q{k}" for y in range(y_from, last) for k in (1, 2, 3, 4)]
    fact = json.loads((S.FACTS_DIR / "capital.json").read_text(encoding="utf-8"))["t2_recognized"]
    assert t2[anchor] == t2[str(y_from - 1)] == 339.1 and "339,1" in fact["calc"] and fact["v"] > t2[anchor]
    assert share_from == f"{y_from}Q1"
    assert t2[str(last)] == t2["LT"] and "LT_from" not in t2
    vals = [t2[k] for k in q_keys] + [t2["LT"]]
    assert all(b >= a for a, b in zip(vals, vals[1:]))
    assert not any(a["paths"] == ["capital.n20.t2"] for a in book["valuation"]["uncertainty"]["axes"])


def test_premiums_are_trajectories_by_sector_and_end_by_the_drift_year(book):
    """Премии роста (MODEL §4.3): у кредитов — ровно три группы сектора, у средств — два сегмента; после
    `share_drift_until` премия равна нулю и при сдвинутой оси: оси-связки кредитов и средств клиентов не трогают ни LT,
    ни ключи после `share_drift_until`, ни ключ первого прогнозного квартала премии средств (он — факт: остатки августа
    2026 года). Рост кредитов года якоря у ВТБ задан прогнозом банка на 2026 год (механизм гайденса роста включён), премии
    кредитов — с 2027 года (решение ведущего № 3, раздел 3)."""
    v = book["volumes"]
    assert list(v["loan_share_drift"]) == ["corporate", "mortgage", "retail_other"]
    assert list(v["funds_share_drift"]) == ["retail", "corporate"]
    for traj in list(v["loan_share_drift"].values()) + list(v["funds_share_drift"].values()):
        assert traj["LT"] == 0.0 and traj["LT_from"] == v["share_drift_until"] + 1
    y0 = int(book["meta"]["first_period"][:4])
    assert all(min(int(k[:4]) for k in traj if k[:1] == "2") == y0 + 1 for traj in v["loan_share_drift"].values())
    axes = {a["paths"][0]: a for a in book["valuation"]["uncertainty"]["axes"]}
    loans = axes["volumes.loan_share_drift.corporate.2029"]
    funds = axes["volumes.funds_share_drift.retail.2026Q4"]
    facts = book["valuation"]["reverse_dcf"]["premium_facts"]
    for ax in (loans, funds):
        assert ax["kind"] == "bundle" and all(p.rsplit(".", 1)[1][:1] == "2" for p in ax["paths"]), ax["name"]
        assert all(int(p.rsplit(".", 1)[1][:4]) <= v["share_drift_until"] for p in ax["paths"]) and not set(facts) & set(ax["paths"])
    assert facts == [f"volumes.funds_share_drift.{s}.{book['meta']['first_period']}" for s in ("retail", "corporate")]
    assert v["guidance_year"] == y0 and set(v["guidance_growth"]) == {"corporate", "retail"}


def test_misc_quarter_shares_and_the_volume_links(book):
    shares = book["other"]["misc_quarter_shares"]
    assert list(shares) == ["1", "2", "3", "4"] and abs(sum(shares.values()) - 1.0) < 1e-9 and set(shares.values()) == {0.25}
    # у ВТБ страховой строки нет (ключа связи страховки с объёмом книга не несёт); рост комиссий 2026 года — ключом
    # с осью полосы (комиссии июля–августа 2026 года)
    assert (book["fees"]["volume_link"], book["opex"]["volume_link"]) == (0.5, 0.5) and "insurance_volume_link" not in book["other"]
    over = book["fees"]["growth_override"]
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"] == ["fees.growth_override.2026"])
    assert list(over) == ["2026"] and ax["low"] < over["2026"] < ax["high"] and book["other"]["fvtpl_bond_reval"] is False


def test_opex_roots_and_their_axis(book):
    """Корни реального роста расходов: один корень 2027–2030, один 2031–2032, LT с года `volumes.lt_from`; ось полосы
    сдвигает только корень 2027–2030; цель C/I живёт в коридоре гейта долгосрочного C/I."""
    og = book["opex"]["real_growth"]
    assert len({og[str(y)] for y in (2027, 2028, 2029, 2030)}) == 1 and og["2031"] == og["2032"]
    assert og["LT_from"] == book["volumes"]["lt_from"] == book["checks"]["cir_lt"]["from_year"]
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0].startswith("opex.real_growth"))
    assert ax["kind"] == "shift" and ax["paths"] == [f"opex.real_growth.{y}" for y in (2027, 2028, 2029, 2030)]
    assert book["checks"]["cir_lt"] == {"target": 0.42, "tolerance": 0.02, "from_year": 2033, "scope": "market_layer"}


def test_the_labels_are_complete_and_carry_only_known_fields(book):
    """Подписи книги (MODEL §0.6): все группы и ключи договора, непустые строки; поля подстановки — только названные у
    ключа; набор строк сводки контрольной модели — ровно пятнадцать. Слово долгосрочного уровня у ВТБ — «после фазы роста»
    («сквозь цикл» — слово общей формы, на панели его нет: tests/web/web_release_text.mjs); прибыль квартала нау-каста — МСФО (банк не публикует управленческую прибыль)."""
    labels = book["meta"]["labels"]
    assert set(labels) == set(LABEL_GROUPS)
    for group, keys in LABEL_GROUPS.items():
        assert set(labels[group]) == keys, group
    assert set(labels["control"]["lines"]) == CONTROL_LINES
    assert set(labels["nowcast"]["targets"]) == {"ni_q", "nim_q", "cor_q"}
    for t in labels["nowcast"]["targets"].values():
        assert set(t) == {"title", "basis", "title_long"}
    assert {k: t["basis"] for k, t in labels["nowcast"]["targets"].items()} == {"ni_q": "ifrs", "nim_q": "mgmt", "cor_q": "mgmt"}
    lt = labels["terms"]["lt_level"]
    count = 0
    for path, value in S.leaves(labels):
        if path.endswith(".basis"):
            continue
        count += 1
        assert isinstance(value, str) and value.strip(), path
        fields = {name for _, name, spec, conv in Formatter().parse(value) if name is not None}
        assert fields <= LABEL_FIELDS.get(path, set()), (path, fields)
        assert "сквозь цикл" not in value, path                  # одно слово долгосрочного уровня во всех подписях
    assert count >= 44
    assert lt == "после фазы роста" and labels["terms"]["roe_lt"] == f"ROE {lt}"
    assert labels["basis"]["divisor"] == "размещённые акции с поправкой на выпуск по 87 ₽"
    assert labels["capital"]["n20_short"] == "Н20.0" and labels["capital"]["n11_short"] == "Н20.1"


def test_guidance_items_and_gate_corridors_have_valid_forms(book):
    """Узлы гайденса: без повторов, у узла гейта есть слова, путь — узел гайденса фактов, базис — из кодов выпуска;
    коридоры гейтов — [мин < макс]; гейты формы банка."""
    ch = book["checks"]
    items = ch["guidance_items"]
    assert [i["key"] for i in items] == ["op_np_growth", "nim", "cor_max", "cir", "roe_target", "fee_growth", "n20_0",
                                         "loan_growth_corporate", "loan_growth_retail"]
    guidance = json.loads((S.FACTS_DIR / "guidance.json").read_text(encoding="utf-8"))
    for i in items:
        assert {"key", "path", "title", "basis", "gate"} <= set(i) <= {"key", "path", "title", "words", "basis", "gate"}
        assert i["path"].startswith("items.") and i["path"].split(".", 1)[1] in guidance["items"], i["key"]
        assert i["basis"] in ("mgmt", "ifrs", "regulatory"), i["key"]
        assert i["title"].strip() and (not i["gate"] or i["words"].strip())
    assert [i["gate"] for i in items] == [True, True, True, True, False, False, False, False, False]
    for key in ("roe_range", "cor_range", "nim_range", "cir_range", "terminal_share", "real_rate", "transmission_pairs", "wholesale_share"):
        lo, hi = ch[key]
        assert lo < hi, key
    assert ch["manual_overdue_days"] == {"ifrs_fact": 7, "worlds_after_cbr": 21, "dividend_register": 5, "capital_form": 7}
    anchor = _derive_record()["corridors"]["wholesale_share"]                    # доля опта на якоре — счёт листа вывода
    assert ch["wholesale_share"] == anchor["corridor"] and ch["wholesale_share"][0] < anchor["anchor"] < ch["wholesale_share"][1]
    assert ch["nim_range"][0] <= book["nii"]["nim_lt_target_mgmt"] <= ch["nim_range"][1]
    assert ch["cir_range"][0] < ch["cir_lt"]["target"] < ch["cir_range"][1]
    for k in ("nim_path_joint", "ni_jump"):
        assert isinstance(ch[k]["quarters"], int) and 1 <= ch[k]["quarters"] <= 42
    lo, hi = book["valuation"]["sensitivities"]["rank_window"]
    assert 0.0 < lo < 0.5 < hi < 1.0 and book["valuation"]["sensitivities"]["buffer_pp"] == 0.01


def test_near_spread_keys_are_the_record_of_the_nii_sheet(book):
    """Ближние ключи спредов книги ВТБ — из бэктеста (правило образца «ключ года якоря = ставка якоря − опора» у ВТБ
    снято, шапка блока ЧПД шаблона): спред — линия окна на ключевой мира-опоры H плюс остаток книги на якоре (2026 —
    весь, 2027 — половина, с 2028 года — ноль), у книги бумаг — обращение лага. Числа пишет лист calib-nii; книга несёт
    их запись `evidence/path/inputs/vtb_r2_inputs.json` — спред и лаг каждой книги равны записи, и лист вывода на ядре
    сверил их с той же записью."""
    sheet = json.loads(NII_SHEET.read_text(encoding="utf-8"))["nii_books"]["books"]
    assert set(sheet) == set(book["nii"]["books"])
    for b, spec in book["nii"]["books"].items():
        assert spec["spread"] == sheet[b]["spread"] and spec["rho"] == sheet[b]["rho"], b
    near = _derive_record()["near_spreads"]
    assert near["same"] and near["diff"] == [] and set(near["books"]) == set(book["nii"]["books"])
