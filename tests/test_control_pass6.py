# -*- coding: utf-8 -*-
"""Контрольная модель, шестой проход (docs/MODEL.md §4.6, §4.7, §17): структура нормировки сегментной CoR по ключу
credit.segment_relative.corporate_share_ref и база объёма iea квартала фактов в определении клетки.

* Пример приложения I.1 методики (машинная копия tests/fixtures/core_pass6/example.json, узел volume_base): рабочая
  функция базы объёма квартала фактов (c_fact_volume_base) на узлах ожидаемого отчёта — окончательном конце, капитале,
  решённом дивиденде, взносе — даёт A примера до 1e-9; без добора опта это та же A, что средние процентные активы
  квартала клетки (полусумма начала и предварительного конца — правило М§4.10 своим счётом теста), с добором — разности
  примера; рост объёма через год — рабочей функцией роста объёма (c_volume_growth). I.1b — A_x фактов ВТБ на якоре
  2К2026 по узлам фактов.
* Свойства своего счёта на фикстуре формы образца (tests/fixtures/core — годовая ветвь) со связями 0,5 и базой iea, двумя
  концами истории сверх её, решением собрания в окне базы и сегментной схемой rel = {0,7; 1,8} (подставляет тест): A_x
  фактов фикстуры — формулой М§4.7 по узлам фактов; рост объёма периодов на кварталах фактов; без связей, при базах
  loans и funds и без ключа структуры — прежние числа; отказы; резервы клетки мира N — путь режима × rel / Σ w × rel ×
  средние кредиты АС сегмента × d/365 на структуре ключа (и на границе 1) и без ключа — на долях якоря.
* Мутации контрольной модели (правка исходного текста в памяти теста): база без ΔE, ключ структуры не читается, доля
  физлиц — та же доля ключа — каждую роняют тесты без ядра.
* Сверка с ядром (метка ci_only; ядро импортируется только в момент теста) — прежние строки в прежних допусках М§17.

Перенос якоря, строку «механика», норму клетки механики, продление моста и перенос плотности постоянной части
контрольная модель не исполняет (М§17): это правила инструмента перезаякоривания.

Числа подмен — входы тестов, а не допущения.
"""

from __future__ import annotations

import copy
import json
import math
import types
from pathlib import Path

import pytest

try:
    from tests import independent_model as cm
    from tests import test_control_deductions as tcd
    from tests import test_control_model as tcm
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_deductions as tcd               # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]

FIXTURE = cm.ROOT / "tests" / "fixtures" / "core"
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass6" / "example.json"
EXAMPLE_TOL = 1e-9          # пример приложения I: формулы без шага, одно определение (М§17)
EXACT = 1e-12               # своё свойство: те же действия над теми же числами
put, with_keys, values_of = tcd.put, tcd.with_keys, tcd.values_of
IEA = cm.LINK_BASES[-1]
LINKS = ("fees.volume_link", "opex.volume_link", "other.insurance_volume_link")
REL = {"corporate": 0.7, "retail": 1.8}                 # сегментная схема формы проверки (вход теста)
SEG_KEY = 0.66              # доля юрлиц ключа структуры: дальше 0,05 от доли якоря фикстуры (вход теста)
# Два конца истории сверх фикстуры и базы loans, funds на всех концах до якоря (входы теста; млрд ₽).
HISTORY_MORE = {
    "2025Q2": {"date": "2025-06-30", "bv_common": 7620.0, "loans_ac_gross": 45150.0, "iea": 65480.0,
               "total_assets": 67350.0, "loans": 49600.0, "funds": 46300.0},
    "2025Q3": {"date": "2025-09-30", "bv_common": 7985.0, "loans_ac_gross": 45900.0, "iea": 66130.0,
               "total_assets": 68050.0, "loans": 50300.0, "funds": 47100.0},
}
HISTORY_BASES = {"2025Q4": {"loans": 51000.0, "funds": 48900.0}, "2026Q1": {"loans": 51800.0, "funds": 48400.0}}
# Решение собрания за год до якоря — в квартале якоря (x = 0): сумма всех категорий и на обыкновенные (входы теста).
DECISION = {"period": "2025Q4", "decided_date": "2026-06-26", "pool_all_classes": 850.2, "pool_declared": 812.5}


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def close(got, want, what: str, tol: float = EXAMPLE_TOL) -> None:
    assert got == pytest.approx(want, rel=tol, abs=tol), (what, got, want)


# ============================================================================ формы проверки


@pytest.fixture(scope="module")
def inputs():
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8")), cm.c_facts_bundle(FIXTURE / "facts")


def with_history(facts: dict, decision: dict | None = DECISION) -> dict:
    """Факты фикстуры с двумя концами истории сверх её, базами loans и funds на концах до якоря и решением собрания
    за прошлый год в квартале якоря (строка истории дивидендов того же года)."""
    out = copy.deepcopy(facts)
    hist = out["balance"].setdefault("history", {})
    for per, rec in HISTORY_MORE.items():
        hist[per] = {k: (v if k == "date" else {"v": v, "calc": "вход теста"}) for k, v in rec.items()}
    for per, rec in HISTORY_BASES.items():
        for k, v in rec.items():
            hist[per][k] = {"v": v, "calc": "вход теста"}
    if decision is not None:
        year = int(decision["period"][:4])
        rows = out["dividends"]["history"]
        row = next(r for r in rows if r.get("year") == year)
        for k, v in decision.items():
            row[k] = {"v": v, "calc": "вход теста"} if k.startswith("pool") else v
    return out


def with_links(book: dict, base: str = IEA, link: float = 0.5) -> dict:
    return with_keys(book, {**{k: link for k in LINKS}, "volumes.link_base": base})


def with_segments(book: dict, share=None, *, enabled: bool = True) -> dict:
    """Сегментная схема rel = {0,7; 1,8}; share — ключ доли юрлиц структуры (None — ключа нет)."""
    seg = {"enabled": enabled, **REL}
    if share is not None:
        seg["corporate_share_ref"] = share
    return put(book, "credit.segment_relative", seg)


def form(book: dict, share=None) -> dict:
    """Форма проверки шестого прохода: связи 0,5 с базой iea и сегментная схема (с ключом структуры или без)."""
    return with_segments(with_links(book), share)


def scenario0(book: dict) -> str:
    return book["capital"]["reg_scenarios"]["ids"][0]


# ============================================================================ пример приложения I.1 (рабочие функции)


def _example_cell_iea(inp: dict, liquid_min: float, which: str) -> dict:
    """Конец квартала примера по правилу М§4.10 своим счётом теста: предварительный — при BV_(q−1) − Div, без дохода и
    взноса; окончательный — при BV_q. Балансирующие активы — остаток баланса, не ниже минимума ликвидности
    доля × небалансирующие активы / (1 − доля); недостающее — добор опта. IEA — кредиты, бумаги и ликвидность."""
    o, q = inp["open"], inp["quarter"]
    nba = q["loans"] - q["allowance"] + q["other_assets"]
    liab = q["funds"] + q["other_liabilities"] + q["div"]
    bv = o["bv"] - q["div"] if which == "preliminary" else o["bv"] + q["ci"] - q["div"] + q["rec"]
    free = liab + q["wholesale_base"] + bv - nba
    floor = liquid_min * nba / (1.0 - liquid_min)
    la = max(free, floor)
    return {"bv": bv, "la": la, "wholesale_extra": max(0.0, floor - free), "iea": q["loans"] + la, "la_min": floor}


def check_example(m) -> None:
    """Пример приложения I.1 до 1e-9 рабочей функцией базы объёма квартала фактов m.c_fact_volume_base; рост объёма
    через год — рабочей функцией роста объёма m.c_volume_growth на таблице квартала фактов; строка комиссий — М§4.7."""
    ex = example()["volume_base"]
    inp = ex["inputs"]
    o, q = inp["open"], inp["quarter"]
    iea0 = o["loans"] + o["securities"] + o["liquidity"]
    for name, case in ex["cases"].items():
        pre, fin = (_example_cell_iea(inp, case["liquid_min"], w) for w in ("preliminary", "final"))
        close(pre["la_min"], case["la_min"], f"{name}: минимум ликвидности")
        for which, end in (("preliminary", pre), ("final", fin)):
            for k in ("bv", "la", "wholesale_extra", "iea"):
                close(end[k], case[which][k], f"{name}: {which}.{k}")
        cell = (iea0 + pre["iea"]) / 2.0
        close(cell, case["cell_iea_avg"], f"{name}: ĪEA клетки")
        got = m.c_fact_volume_base(iea0, fin["iea"], o["bv"], fin["bv"], q["div"])
        close(got["delta_e"], case["delta_e"], f"{name}: ΔE")
        close(got["a"], case["facts_a"], f"{name}: A фактов (М§4.7)")
        close(got["a_ends"], case["facts_a_old_rule"], f"{name}: прежнее правило")
        close(got["a"] - cell, case["facts_minus_cell"], f"{name}: факты минус клетка")
        if name == "free":                                  # без добора опта — одна A у клетки и у фактов
            close(got["a"], cell, "без добора: A фактов = ĪEA клетки", EXACT)
        close(got["a_ends"] - got["a"], got["delta_e"] / 2.0, f"{name}: прежнее правило выше на ΔE / 2", EXACT)
        # рост объёма через год: квартал фактов — якорь условной книги, квартал того же номера — следующий год
        anchor = (2026, 2)                                  # номера условные: квартал примера — квартал якоря
        ctx = {"A": {"anchor": anchor}, "anchor": anchor, "iea_facts": {anchor: {"a": got["a"]}}}
        nxt = case["next_year"]["cell_iea_avg"]
        v = m.c_volume_growth(ctx, {"vend": {}}, IEA, anchor[0] + 1, (anchor[1],), nxt)
        close(v, case["next_year"]["v"], f"{name}: рост объёма через год")
        close(nxt / got["a_ends"] - 1.0, case["next_year"]["v_old_rule"], f"{name}: рост объёма по прежнему правилу")
        fees = inp["fees_q"] * (1.0 + inp["wage"] + inp["link"] * (v - inp["wage"]))
        close(fees, case["next_year"]["fees"], f"{name}: строка комиссий через год")


@pytest.mark.tact
def test_appendix_i1_fact_quarter_is_the_cell_quarter():
    """Приложение I.1 (М§4.7): квартал фактов из узлов ожидаемого отчёта — та же A, что ĪEA квартала клетки, без
    добора опта; с добором на предварительном конце и на обоих концах — разности −5,669014 и −8,5 = −ΔE / 2 примера;
    прежнее правило (полусумма концов) — на ΔE / 2 выше; рост объёма и строка комиссий через год — числа примера."""
    check_example(cm)


def _vtb_example_facts(rows: list[dict], anchor_period: str) -> dict:
    """Узлы фактов из строк приложения I.1b: концы истории (iea, bv_common), конец якоря (сумма книг активов — одна
    книга, капитал якоря) и строка истории дивидендов с решением в квартале с суммой примера."""
    hist = {}
    for r in rows:
        y, q = cm.c_per_parse(r["period"])
        py, pq = (y - 1, cm.QY) if q == 1 else (y, q - 1)
        hist[f"{py}Q{pq}"] = {"iea": r["iea_prev"], "bv_common": r["bv_prev"]}
        hist[f"{y}Q{q}"] = {"iea": r["iea"], "bv_common": r["bv"]}
    last = rows[-1]
    divs = []
    for r in rows:
        if r["div"]:
            y, q = cm.c_per_parse(r["period"])
            divs.append({"period": f"{y - 1}Q4", "decided_date": cm.c_q_last_day(y, q).isoformat(),
                         "pool_all_classes": {"v": r["div"]}, "pool_declared": {"v": r["div"] / 2.0}})
    return {"anchor": cm.c_per_parse(anchor_period), "E0": {"assets": last["iea"]}, "BV": last["bv"],
            "history": hist, "div_history": divs, "div_history_before": []}


@pytest.mark.tact
def test_appendix_i1b_vtb_fact_quarters():
    """Приложение I.1b: A_x фактов ВТБ на якоре 2К2026 — до 1e-9 рабочей функцией таблицы кварталов фактов
    (c_iea_fact_quarters) на узлах, собранных из строк примера; сверка с фактами репозитория — следующий тест."""
    rows = example()["volume_base_vtb_facts"]["rows"]
    books = {"assets": {"side": cm.LOANS_SIDE}}
    table = cm.c_iea_fact_quarters(_vtb_example_facts(rows, rows[-1]["period"]), books)
    for r in rows:
        got = table[cm.c_per_parse(r["period"])]
        assert got["x"] == r["x"]
        for k_got, k_want in (("delta_e", "delta_e"), ("a", "a"), ("a_ends", "a_old_rule"), ("div", "div")):
            close(got[k_got], r[k_want], f"I.1b {r['period']}: {k_got}")
        close(got["a"] - got["a_ends"], r["diff"], f"I.1b {r['period']}: разность")


@pytest.mark.tact
@pytest.mark.xfail(strict=True, reason=(
    "пример I.1b методики (docs/MODEL.md, прил. I; машинная копия tests/fixtures/core_pass6/example.json) посчитан на "
    "фактах до правки второго круга 7c424ad («книга ликвидности без денег и резервов»): iea кварталов примера выше "
    "фактов репозитория на 1,7–2,0 трлн ₽ (2025Q2: 32 061,3 против 30 256,8) — пересчитать пример на нынешних фактах "
    "(поток ядра)"))
def test_appendix_i1b_matches_the_repository_facts():
    """Приложение I.1b на фактах репозитория — пока они стоят на якоре примера (после переноса якоря строки примера —
    история, и проверка пропускается с причиной)."""
    rows = example()["volume_base_vtb_facts"]["rows"]
    facts = cm.c_facts_bundle()
    if facts.get("anchor", {}).get("period") != rows[-1]["period"]:
        pytest.skip(f"факты репозитория — на якоре {facts.get('anchor', {}).get('period')}, пример I.1b — на якоре "
                    f"{rows[-1]['period']}")
    ctx = cm.c_control_context(cm.c_book_machine(), facts)
    if ctx["iea_facts"] is None:
        pytest.skip("у машинной книги нет связи с объёмом с базой iea — таблица кварталов фактов не читается")
    for r in rows:
        got = ctx["iea_facts"][cm.c_per_parse(r["period"])]
        for k_got, k_want in (("iea_prev", "iea_prev"), ("iea", "iea"), ("bv_prev", "bv_prev"), ("bv", "bv"),
                              ("div", "div"), ("delta_e", "delta_e"), ("a", "a")):
            close(got[k_got], r[k_want], f"I.1b по фактам репозитория {r['period']}: {k_got}")


# ============================================================================ база iea квартала фактов на форме образца


def _facts_table(A: dict, books: dict) -> dict:
    """A_x кварталов фактов x = −3…0 своим счётом теста по узлам фактов (М§4.7)."""
    y0, qa = A["anchor"]
    pos = y0 * cm.QY + qa - 1

    def per(x):
        y, r = divmod(pos + x, cm.QY)
        return y, r + 1

    def end(x, field):
        if x == 0:
            if field == "bv_common":
                return A["BV"]
            return sum(A["E0"][b] for b, sp in books.items() if sp["side"] == cm.LOANS_SIDE)
        y, q = per(x)
        return float(A["history"][f"{y}Q{q}"][field])

    out = {}
    for x in range(-3, 1):
        y, q = per(x)
        div = 0.0
        for rec in A["div_history"] + A["div_history_before"]:
            day = rec.get("decided_date")
            if day and cm.c_qidx_of_date(A["anchor"], cm._c_as_date(day)) == x:
                pool = rec.get("pool_all_classes", rec.get("pool_declared"))
                div += float(pool["v"] if isinstance(pool, dict) else pool)
        d_e = end(x, "bv_common") - end(x - 1, "bv_common") + div
        out[(y, q)] = {"div": div, "delta_e": d_e, "a": (end(x - 1, IEA) + end(x, IEA) - d_e) / 2.0}
    return out


def check_fixture_base(m, book: dict, facts: dict) -> None:
    """A_x фактов фикстуры — формулой М§4.7 своим счётом по узлам фактов; решение собрания в окне — с суммой всех
    категорий; рост объёма двух первых периодов — на этих A_x и на средних процентных активах шага клетки."""
    ready, fx = form(book), with_history(facts)
    ctx = m.c_control_context(ready, fx)
    want = _facts_table(ctx["A"], ctx["books"])
    assert sorted(ctx["iea_facts"]) == sorted(want)
    for k, w in want.items():
        for name in ("div", "delta_e", "a"):
            close(ctx["iea_facts"][k][name], w[name], f"A_x фикстуры {k}: {name}", EXACT)
    assert want[ctx["anchor"]]["div"] == DECISION["pool_all_classes"]
    rows = m.c_cell_annual(ctx, cm.W_LOW, cm.R_NORM, scenario0(ready))["rows"]
    p0, p1 = ctx["periods"][:2]
    prev0 = sum(want[(p0["year"] - 1, q)]["a"] for q in p0["quarters"])
    close(rows[0]["v_volume"], rows[0]["iea"] * p0["n"] / prev0 - 1.0, "рост объёма неполного года якоря", EXACT)
    prev1 = sum(want[(p1["year"] - 1, q)]["a"] if (p1["year"] - 1, q) <= ctx["anchor"] else rows[0]["iea"]
                for q in p1["quarters"])
    close(rows[1]["v_volume"], rows[1]["iea"] * p1["n"] / prev1 - 1.0, "рост объёма первого полного года", EXACT)


@pytest.mark.tact
def test_fact_quarters_of_the_sample_form(inputs):
    """М§4.7 на форме образца со связями 0,5 и базой iea: таблица кварталов фактов и рост объёма периодов на ней; сумма
    решения — pool_all_classes, без поля — pool_declared; решения вне окна не входят; строки комиссий периода — рост
    зарплат, спред и доля связи превышения роста объёма над ростом зарплат."""
    book, facts = inputs
    check_fixture_base(cm, book, facts)
    ctx = cm.c_control_context(form(book), with_history(facts))
    a0 = ctx["iea_facts"][ctx["anchor"]]
    # без pool_all_classes — pool_declared; решение вне окна базы — не входит
    only_declared = with_history(facts, {k: v for k, v in DECISION.items() if k != "pool_all_classes"})
    alt = cm.c_control_context(form(book), only_declared)["iea_facts"][ctx["anchor"]]
    assert alt["div"] == DECISION["pool_declared"]
    close(alt["a"] - a0["a"], (DECISION["pool_all_classes"] - DECISION["pool_declared"]) / 2.0, "сумма решения", EXACT)
    early = with_history(facts, {**DECISION, "decided_date": "2025-03-28"})            # x = −5: вне окна
    assert all(r["div"] == 0.0 for r in cm.c_control_context(form(book), early)["iea_facts"].values())
    # строки комиссий первого полного года (у года якоря формы — переопределение роста): рост к тому же кварталу —
    # зарплаты + спред + связь × (v − зарплаты); база квартала — факт до якоря, позже — квартал клетки
    B, A = ctx["B"], ctx["A"]
    cell = cm.c_cell_annual(ctx, cm.W_LOW, cm.R_NORM, scenario0(B))
    (r0, r1), (p0, p1) = cell["rows"][:2], ctx["periods"][:2]
    assert str(p1["year"]) not in {str(k) for k in (B["fees"].get("growth_override") or {})}
    wage = ctx["wv"][cm.W_LOW][1]["wage_growth"]
    for j, q in enumerate(p1["quarters"]):
        y = p1["year"] - 1
        base = (A["pnl"][f"{y}Q{q}"]["fees_net"] if (y, q) <= ctx["anchor"]
                else r0["fees_q"][p0["quarters"].index(q)])
        spread = cm.c_traj_at(cm.c_bget(B, "fees.growth_vs_wages"), p1["year"], q)
        want = 1.0 + wage[j] + spread + 0.5 * (r1["v_volume"] - wage[j])
        close(r1["fees_q"][j] / base, want, f"комиссии {p1['year']}Q{q}", EXACT)


@pytest.mark.tact
def test_old_rule_stays_for_loans_funds_and_without_links(inputs):
    """Правило базы iea квартала фактов — только у базы iea при ненулевой связи: без связей таблица не читается (и
    факты без bv_common не отказывают), числа формы — прежние бит в бит; у баз loans и funds рост объёма периода —
    прежняя годовая форма из концов истории (те же действия над теми же числами)."""
    book, facts = inputs
    plain = cm.c_control_run(book, facts)
    bare = copy.deepcopy(with_history(facts))
    for per in bare["balance"]["history"].values():
        per.pop("bv_common", None)
    for links in ({}, {k: 0.0 for k in LINKS}):
        quiet = with_keys(book, {**links, "volumes.link_base": IEA})
        assert cm.c_control_context(quiet, bare)["iea_facts"] is None
        assert values_of(cm.c_control_run(quiet, bare)) == values_of(plain)
    for base, field in ((cm.LINK_BASES[0], "loans"), (cm.LINK_BASES[1], "funds")):
        ctx = cm.c_control_context(with_links(book, base), bare)
        assert ctx["iea_facts"] is None
        row = cm.c_cell_annual(ctx, cm.W_LOW, cm.R_NORM, scenario0(book))["rows"][0]
        p0 = ctx["periods"][0]
        hist, E0 = ctx["A"]["history"], ctx["A"]["E0"]
        anchor_end = (sum(E0[b] for b in ctx["loans"]) if field == "loans"
                      else E0[cm.RETAIL_CURRENT] + E0[cm.RETAIL_TERM] + sum(E0[b] for b in ctx["biz"]))
        prev = 0.0
        for q in p0["quarters"]:
            y, pq = p0["year"] - 1, q - 1
            a = anchor_end if (y, pq) == ctx["anchor"] else float(hist[f"{y}Q{pq}"][field])
            b = anchor_end if (y, q) == ctx["anchor"] else float(hist[f"{y}Q{q}"][field])
            prev += (a + b) / 2.0
        path = row["loans_path"] if field == "loans" else [a + b for a, b in zip(row["fr_path"], row["cf_path"])]
        now = sum((a + b) / 2.0 for a, b in zip(path, path[1:]))
        assert row["v_volume"] == now / prev - 1.0, (base, row["v_volume"], now / prev - 1.0)


@pytest.mark.tact
def test_fact_base_refusals(inputs):
    """Отказы базы iea квартала фактов (М§4.7) — только при ненулевой связи и базе iea: нет bv_common на нужном конце
    (и на конце x = −4); решение собрания в окне без суммы; сумма без дня решения у строки с кварталом прибыли не
    раньше x = −11 (на x = −12 — не отказ; без суммы или с нулём — не отказ)."""
    book, facts = inputs
    ready, good = form(book), with_history(facts)
    assert cm.c_control_context(ready, good)["iea_facts"] is not None
    for per in ("2025Q2", "2026Q1"):
        bad = copy.deepcopy(good)
        bad["balance"]["history"][per].pop("bv_common")
        with pytest.raises(cm.ControlInputError, match="bv_common"):
            cm.c_control_context(ready, bad)
        assert cm.c_control_context(with_links(ready, cm.LINK_BASES[0]), bad)["iea_facts"] is None
    no_sum = copy.deepcopy(good)
    no_sum["dividends"]["history"].append({"year": 2026, "period": "2026Q1", "decided_date": "2026-05-20"})
    with pytest.raises(cm.ControlInputError, match="без суммы"):
        cm.c_control_context(ready, no_sum)
    for period, refused in (("2023Q3", True), ("2023Q2", False)):
        undated = copy.deepcopy(good)
        undated["dividends"]["history"].append({"year": 2023, "period": period, "pool_declared": {"v": 5.0}})
        if refused:
            with pytest.raises(cm.ControlInputError, match="без дня решения"):
                cm.c_control_context(ready, undated)
        else:
            assert cm.c_control_context(ready, undated)["iea_facts"] is not None
        before = copy.deepcopy(good)
        before["dividends"]["history_before"] = [{"year": 2023, "period": period, "pool_all_classes": {"v": 5.0}}]
        if refused:
            with pytest.raises(cm.ControlInputError, match="без дня решения"):
                cm.c_control_context(ready, before)
        else:
            assert cm.c_control_context(ready, before)["iea_facts"] is not None
    zero = copy.deepcopy(good)
    zero["dividends"]["history"].append({"year": 2025, "period": "2025Q2", "pool_declared": {"v": 0.0}})
    assert cm.c_control_context(ready, zero)["iea_facts"] is not None
    for quiet in (with_links(ready, cm.LINK_BASES[0]), with_keys(ready, {k: 0.0 for k in LINKS})):
        for bad in (no_sum,):
            assert cm.c_control_context(quiet, bad)["iea_facts"] is None


# ============================================================================ структура нормировки сегментной CoR


def anchor_shares(ctx: dict) -> dict:
    """Доли сегментов в кредитах АС якоря своим счётом теста (правило образца, М§4.6)."""
    A, books, fv = ctx["A"], ctx["books"], ctx["fv"]
    ac = dict.fromkeys(cm.SEGMENTS, 0.0)
    for b, sp in books.items():
        if sp.get("sector"):
            ac[sp["cor_segment"]] += A["E0"][b] * (1.0 - fv.get(b, 0.0))
    tot = sum(ac.values())
    return {sg: v / tot for sg, v in ac.items()}


def check_reserves(m, book: dict, facts: dict, share, *, inner: bool = True) -> None:
    """Резервы клетки мира N в каждом периоде (М§4.6): CoR периода × Σ_σ rel_σ / Σ w × rel × средние кредиты АС
    сегмента × d/365, w — доля юрлиц ключа и остаток у физлиц (без ключа — доли якоря своим счётом теста); на
    структуре нормировки общая CoR равна пути: Σ w × множитель сегмента = 1. inner=False — только строки клетки
    (резервы и множители сегментов), без узла структуры контекста."""
    ready = form(book, share)
    ctx = m.c_control_context(ready, with_history(facts))
    w = anchor_shares(ctx) if share is None else {"corporate": share, "retail": 1.0 - share}
    norm = sum(w[sg] * REL[sg] for sg in cm.SEGMENTS)
    mult = {sg: REL[sg] / norm for sg in cm.SEGMENTS}
    for sg in cm.SEGMENTS if inner else ():
        close(ctx["seg_w"][sg], w[sg], f"структура нормировки {sg} (ключ {share})", EXACT)
    assert abs(sum(w[sg] * mult[sg] for sg in cm.SEGMENTS) - 1.0) <= EXACT
    for p, row in zip(ctx["periods"], m.c_cell_annual(ctx, cm.W_LOW, cm.R_NORM, scenario0(ready))["rows"]):
        for sg in cm.SEGMENTS:
            close(row["seg_rel"][sg], mult[sg], f"{p['year']}: множитель сегмента {sg} (ключ {share})", EXACT)
        close(sum(row["ac_avg_seg"].values()), row["loans_ac_avg"], f"{p['year']}: кредиты АС", EXACT)
        want = row["cor"] * sum(mult[sg] * row["ac_avg_seg"][sg] for sg in cm.SEGMENTS) * p["days"] / cm.DAYS_BASE
        close(row["llp"], want, f"{p['year']}: резервы (ключ {share})", EXACT)


@pytest.mark.tact
@pytest.mark.parametrize("share", [SEG_KEY, 1.0, 0.0, None], ids=["ключ", "граница 1", "граница 0", "без ключа"])
def test_reserves_on_the_structure_of_the_key(inputs, share):
    """М§4.6, §17: резервы клетки мира N на структуре ключа corporate_share_ref (и на границах 1 и 0) и без ключа — на
    долях якоря; ключ доли юрлиц формы проверки отстоит от доли якоря больше чем на 0,05."""
    book, facts = inputs
    ctx = cm.c_control_context(form(book), with_history(facts))
    assert abs(anchor_shares(ctx)["corporate"] - SEG_KEY) > 0.05
    check_reserves(cm, book, facts, share)


@pytest.mark.tact
def test_structure_key_rules(inputs):
    """Ключ структуры нормировки: число от 0 до 1 включительно (ноль, единица и целые допустимы); вне [0; 1], не
    числом и null при включённой схеме — отказ (М§0.1, §4.6); при выключенной схеме ключ не читается — числа формы
    прежние бит в бит; без ключа — доли якоря, ключ, равный доле якоря, — те же числа до 1e-12."""
    book, facts = inputs
    for bad in (-0.01, 1.01, "0.5", True, None, float("nan"), float("inf"), {"LT": 0.5}, [0.5]):
        with pytest.raises(cm.ControlInputError, match="corporate_share_ref"):
            cm.c_control_context(with_segments(book, bad) if bad is not None
                                 else put(with_segments(book), cm.SEG_SHARE, None), facts)
    for ok in (0, 1, 0.0, 1.0, 0.5):
        assert cm.c_control_context(with_segments(book, ok), facts)["seg_w"]["corporate"] == float(ok)
    plain = cm.c_control_run(book, facts)
    off = with_segments(book, enabled=False)
    for junk in (None, "x", 7.0):
        assert values_of(cm.c_control_run(put(off, cm.SEG_SHARE, junk), facts)) == values_of(plain)
    assert cm.c_control_context(off, facts)["seg_w"] is None
    bare = cm.c_control_run(with_segments(book), facts)
    same = cm.c_control_run(with_segments(book, anchor_shares(bare["ctx"])["corporate"]), facts)
    for c0, c1 in zip(bare["cells"], same["cells"]):
        assert c1["v_ri"] == pytest.approx(c0["v_ri"], rel=EXACT, abs=EXACT)
    assert same["point"] == pytest.approx(bare["point"], rel=EXACT)
    moved = cm.c_control_run(with_segments(book, SEG_KEY), facts)
    assert moved["point"] != pytest.approx(bare["point"], rel=1e-6)


# ============================================================================ мутации контрольной модели


MUTANTS = {
    "база без ΔE": ('"a": (iea_prev + iea_end - delta_e) / 2.0', '"a": (iea_prev + iea_end) / 2.0',
                    {"example", "fixture_base"}),
    "ключ структуры не читается": ("    if _c_key_given(B, SEG_SHARE):\n", "    if False:\n",
                                   {"reserves_key", "reserves_edge", "reserves_key_rows"}),
    "доля физлиц — та же доля ключа": ("SEGMENTS[1]: 1.0 - float(share)", "SEGMENTS[1]: float(share)",
                                       {"reserves_key", "reserves_edge", "reserves_key_rows"}),
}


def _mutant(old: str, new: str):
    """Копия контрольной модели с одной правкой исходного текста (модуль в памяти теста)."""
    src = Path(cm.__file__).read_text(encoding="utf-8")
    assert src.count(old) == 1, f"место мутации не единственно или исчезло: {old!r}"
    mod = types.ModuleType("independent_model_mutant")
    mod.__file__ = cm.__file__
    exec(compile(src.replace(old, new), cm.__file__, "exec"), mod.__dict__)     # noqa: S102 — правка текста теста
    return mod


def _checks(book: dict, facts: dict) -> dict:
    return {"example": lambda m: check_example(m),
            "fixture_base": lambda m: check_fixture_base(m, book, facts),
            "reserves_key": lambda m: check_reserves(m, book, facts, SEG_KEY),
            "reserves_edge": lambda m: check_reserves(m, book, facts, 1.0),
            "reserves_key_rows": lambda m: check_reserves(m, book, facts, SEG_KEY, inner=False),
            "reserves_anchor": lambda m: check_reserves(m, book, facts, None)}


@pytest.mark.tact
def test_control_mutations_fall_on_tests_without_core(inputs):
    """Мутации шестого прохода контрольной модели (CONTROL-MODEL §6): подлинная модель проходит все проверки, каждая
    мутация роняет свои проверки без ядра — пример I.1 и база фактов фикстуры, резервы на структуре ключа."""
    book, facts = inputs
    checks = _checks(book, facts)
    for name, fn in checks.items():
        fn(cm)
    for name, (old, new, must) in MUTANTS.items():
        mod = _mutant(old, new)
        fallen = set()
        for check, fn in checks.items():
            try:
                fn(mod)
            except AssertionError:
                fallen.add(check)
        assert must <= fallen, f"мутация «{name}» не роняет {sorted(must - fallen)} (упали: {sorted(fallen)})"


# ============================================================================ сверка с ядром (в момент теста)


def _write_facts(facts: dict, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, tree in facts.items():
        (folder / f"{name}.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    return folder


FORMS = {"iea-key": lambda book: form(book, SEG_KEY),
         "iea-key-zero": lambda book: form(book, 0.0),
         "iea-anchor-shares": lambda book: form(book),
         "iea-no-segments": lambda book: with_links(book),
         "key-only": lambda book: with_segments(book, SEG_KEY)}
# Граница 1 (вся структура — юрлица; CoR физлиц — × rel_retail / rel_corporate): у клеток спада мира M ROE'_T стоит в
# 0,05…0,16 п.п. над g_T, TV_DDM = BV_Q × (ROE'_T − g_T) / (k_T − g_T) — 0,2…1,4 % BV_Q, и строка TV (3 %) различает
# 0,004…0,008 п.п. ROE'_T — меньше допуска самой ROE'_T (0,3 п.п.) в 40–75 раз. Эти формы сверяются отдельным тестом:
# строки TV вне 3 % допустимы только в пределах производной допуска ROE'_T (TOL_RATIO × BV_Q / (k_T − g_T)) и только
# при V_c и ROE'_T клетки в допуске; прочие строки — без исключений (находка отчёта шестого прохода).
EDGE_FORMS = {"iea-key-edge": lambda book: form(book, 1.0),
              "key-edge-only": lambda book: with_segments(book, 1.0)}


def _reconcile(book: dict, facts: dict, folder: Path):
    run = tcd._core_run(book, _write_facts(facts, folder))
    ctl = cm.c_control_run(book, facts)
    rows = tcm.compare_with_core(run, ctl)
    assert not tcm.exact_match(run, ctl), "V0 слоёв совпали с ядром до 1e-9 — общий код"
    return run, ctl, rows


@pytest.mark.ci_only
@pytest.mark.parametrize("name", list(FORMS))
def test_control_matches_core_with_sixth_pass_forms(inputs, tmp_path, name):
    """Форма образца со связями 0,5 и базой iea, двумя концами истории сверх её, решением собрания в окне и сегментной
    схемой (ключ структуры, граница 0, без ключа; ключ без связей) против ядра — прежние строки в прежних допусках М§17.
    Расхождение — находка, а не повод подогнать контрольную модель."""
    book, facts = inputs
    _, _, rows = _reconcile(FORMS[name](book), with_history(facts), tmp_path / "facts")
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)


TV_ROW = "терминальная стоимость с капиталом, клетка "


@pytest.mark.ci_only
@pytest.mark.parametrize("name", list(EDGE_FORMS))
def test_control_matches_core_on_the_structure_edge(inputs, tmp_path, name):
    """Граница 1 ключа структуры против ядра: все строки в допусках М§17, кроме строк TV клеток, где TV_DDM мала против
    капитала (ROE'_T у g_T), — у них разность не больше производной допуска ROE'_T, TOL_RATIO × BV_Q / (k_T − g_T),
    а V_c и ROE'_T клетки в допуске (комментарий у EDGE_FORMS)."""
    book, facts = inputs
    _, ctl, rows = _reconcile(EDGE_FORMS[name](book), with_history(facts), tmp_path / "facts")
    by_what = {r["what"]: r for r in rows}
    left = []
    for r in rows:
        if r["ok"]:
            continue
        if not r["what"].startswith(TV_ROW):
            left.append(r)
            continue
        label = r["what"][len(TV_ROW):]
        cell = cm.c_cell_of(ctl, *label.split("/"))
        floor = tcm.TOL_RATIO * cell["rows"][-1]["bv"] / (cell["k_t"] - cell["g_t"])
        near = abs(cell["roe_t"] - cell["g_t"]) <= tcm.TOL_RATIO
        own = [by_what.get(f"стоимость клетки {label}"), by_what.get(f"ROE терминала, клетка {label}")]
        if not (near and abs(r["diff"]) <= floor and all(x is not None and x["ok"] for x in own)):
            left.append(r)
    assert not left, f"вне допусков М§17: {len(left)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(left)


@pytest.mark.ci_only
def test_structure_key_against_core_as_a_black_box(inputs, tmp_path):
    """Ядро — чёрный ящик: ключ структуры, равный доле якоря, оставляет у ядра точку книги без ключа (до 1e-9); ключ
    0,66 двигает точку у двух моделей в одну сторону и на близкую величину; книги с ключом вне [0; 1] и null при
    включённой схеме отвергают обе модели."""
    import importlib

    book, facts = inputs
    folder = FIXTURE / "facts"
    bare = tcd._core_run(with_segments(book), folder)
    plain_ctl = cm.c_control_run(with_segments(book), facts)
    share = anchor_shares(plain_ctl["ctx"])["corporate"]
    same = tcd._core_run(with_segments(book, share), folder)
    assert same.point == pytest.approx(bare.point, rel=1e-9)
    mine = cm.c_control_run(with_segments(book, SEG_KEY), facts)["point"] - plain_ctl["point"]
    theirs = tcd._core_run(with_segments(book, SEG_KEY), folder).point - bare.point
    assert mine * theirs > 0.0 and abs(mine - theirs) <= tcm.TOL_VALUE * abs(bare.point), (mine, theirs)
    book_mod = importlib.import_module("model.book")
    core_facts = book_mod.load_facts(folder)
    for bad in (with_segments(book, 1.5), with_segments(book, -0.2), put(with_segments(book), cm.SEG_SHARE, None)):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(bad, facts)
        with pytest.raises(Exception) as refused:
            book_mod.book_from_dict(bad, facts=core_facts)
        assert type(refused.value).__name__ == "BookError", refused.value
