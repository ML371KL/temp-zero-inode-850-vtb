# -*- coding: utf-8 -*-
"""Контрольная модель, пятый проход ядра (docs/MODEL.md §4.3, §4.11, §7, §17): вычет сценария в рублях
(capital.reg_scenarios.<s>.deduction_rub), путь постоянной части прочих активов (volumes.other_assets_fixed_change и
вес риска приращения capital.rwa.density.other_assets_fixed_change), постоянные в рублях части за концом сетки
(valuation.terminal.fixed_growth_share, λ_F).

* Пример приложения H методики (машинная копия tests/fixtures/core_pass5/example.json): контрольная модель
  подставляет входы примера в свои рабочие функции — счёт норматива годовой ветви и квартального прохода, избыток
  капитала терминала, строки моста, RWA, читатель пути постоянной части, оценку клетки с терминалом — и получает его
  числа до 1e-9 (М§17). Перенос якоря контрольная модель не исполняет: по примеру проверяются только формулы на
  книгах после переноса (вычет, поправка — калибровкой, путь постоянной части от нового якоря).
* Свойства своего счёта на фикстурах формы образца (tests/fixtures/core — годовая ветвь) и формы панели
  (tests/fixtures/core_t — квартальный проход капитала) с ключами, подставленными тестом: без ключей, при рублях и
  приращениях, равных нулю, и при λ_F = 1 — прежние числа бит в бит; ряд вычета — формула с рублями сценария, капитал
  пересчитывается тестом по рядам клетки; на книге, у которой путь капитала от нормативов не зависит, рубли снижают
  капитал ровно на свою сумму, норматив — на сумму к RWA клетки; прочие активы и RWA — формулы М§4.3 и §4.11 с весом
  ω_Δ; деньги убывания — в балансирующих активах; DDM = RI при λ_F = 0; 0,5; 1; без постоянных частей оценка от λ_F не
  зависит; бездоходный актив, вычтенный из капитала один к одному, с весом риска 0 и оплаченный капиталом, при
  λ_F = 0 оценке нейтрален; отказы книги.
* Сверка с ядром (метка ci_only; ядро импортируется только в момент теста) — прежние строки в прежних допусках М§17.

Числа подмен — входы тестов, а не допущения.
"""

from __future__ import annotations

import copy
import json
import math

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
FIXTURE_T = cm.ROOT / "tests" / "fixtures" / "core_t"
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass5" / "example.json"
EXAMPLE_TOL = 1e-9          # пример приложения H: формулы без шага, одно определение (М§17)
EXACT = 1e-12               # своё свойство: те же действия над теми же числами
put, with_keys, with_shares, close, key = tcd.put, tcd.with_keys, tcd.with_shares, tcd.close, tcd.key
values_of, rows_of = tcd.values_of, tcd.rows_of
SHARE20, SHARE11 = tcd.SHARE20, tcd.SHARE11
ETA20, ETA11 = tcd.ETA20, tcd.ETA11
NO_PAYOUT = tcd.NO_PAYOUT
LAM = cm.FIXED_GROWTH
PATH = cm.OAF_CHANGE
DENS_FIXED = "capital.rwa.density." + cm.OAF_DENSITY
DENS_CHANGE = "capital.rwa.density." + cm.OAF_CHANGE_DENSITY
OAF = "volumes.other_assets_fixed"


def rub_path(scale: float) -> dict:
    """Траектория рублей сценария (вход теста): ноль в квартале якоря, накопление ключами лет и квартала, сход к LT."""
    return {"2026Q2": 0.0, "2027": 40.0 * scale, "2028Q3": 75.0 * scale, "2029": 120.0 * scale,
            "LT": 80.0 * scale, "LT_from": 2033}


def with_rub(book: dict, scales: dict | None = None) -> dict:
    """Книга с вычетом сценария в рублях у всех сценариев: у каждого свой масштаб, у второго норматива — 0,8 от Н20.0."""
    out = copy.deepcopy(book)
    ids = out["capital"]["reg_scenarios"]["ids"]
    scales = scales or {s: 1.0 + 0.5 * i for i, s in enumerate(ids)}
    for s in ids:
        out["capital"]["reg_scenarios"][s][cm.RUB_KEY] = {"n20_0": rub_path(scales[s]),
                                                          "n1_1": rub_path(0.8 * scales[s])}
    return out


def zero_rub(book: dict) -> dict:
    out = copy.deepcopy(book)
    for s in out["capital"]["reg_scenarios"]["ids"]:
        out["capital"]["reg_scenarios"][s][cm.RUB_KEY] = {"n20_0": 0.0, "n1_1": {"2027": 0, "LT": 0.0}}
    return out


# Путь постоянной части формы образца (вход теста): уровень, плотность постоянной части, ноль до 2027 года, ступень
# одиночным ключом квартала, затем ключи лет; вес приращения — ноль (вычитаемый из капитала актив).
CORE_FIXED = {OAF: 1200.0, DENS_FIXED: 0.8}
CORE_PATH = {"2027": 0.0, "2027Q3": -50.0, "2028": -150.0, "2029": -300.0, "2030": -450.0}


CREATE_PATH = {"2026": 0.0, "2028": 300.0, "2030": 600.0}    # путь создаёт постоянную часть с нуля (вход теста)
BOOK_PATH = object()        # путь по умолчанию — CORE_PATH (None — значение null ключа, вход отказа)


def with_path(book: dict, path=BOOK_PATH, weight=0.0, level=True) -> dict:
    keys = {PATH: CORE_PATH if path is BOOK_PATH else path}
    if level:
        keys.update(CORE_FIXED)
    if weight is not None:
        keys[DENS_CHANGE] = weight
    return with_keys(book, keys)


# ============================================================================ пример приложения H


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


G1_AT = {"anchor": (2026, 2), "quarter": (2026, 3), "other_cell": (2026, 3)}     # кварталы строк (номера условные)
G1_NEXT = (2026, 4)                                                             # квартал после нового якоря
G1_S = "example"


def g1_book(inp: dict, *, rub: bool = True, frozen: bool = False, ded=None, shares=None, gap=None) -> dict:
    """Книга примера H.1 из тех ключей, которые читает счёт норматива: вычеты якоря и доли, признание фонда,
    инструменты, поправки, пути вычета сценария по кварталам строк (п.п. и рубли), требования. frozen — прежняя
    форма книг: рубли записаны в п.п. делением на RWA модальной клетки, ключа рублей нет."""
    rows = {G1_AT["anchor"]: inp["anchor"], G1_AT["quarter"]: inp["quarter"], G1_NEXT: inp["reanchor"]["next"]}
    per = {f"{y}Q{h}": row for (y, h), row in rows.items()}
    dpp = {j: {p: row[f"dpp{j}"] + (row[f"rub{j}"] / inp["rwa_modal"] if frozen else 0.0) for p, row in per.items()}
           for j in ("20", "11")}
    ded = ded or (inp["ded20_0"], inp["ded11_0"])
    shares = shares or (inp["eta20"], inp["eta11"])
    gap = gap or (inp["gap20"], inp["gap11"])
    scen = {"conservation": 0.0, "sifi": 0.0, "ccyb": 0.0, "deduction_pp": {"n20_0": dpp["20"], "n1_1": dpp["11"]}}
    if rub and not frozen:
        scen[cm.RUB_KEY] = {"n20_0": {p: row["rub20"] for p, row in per.items()},
                            "n1_1": {p: row["rub11"] for p, row in per.items()}}
    return {"capital": {
        "n20": {"deductions_anchor": ded[0], "fvoci_recognition": inp["fvoci_recognition"], "gap_pp": gap[0],
                "deductions_fixed_share": shares[0], "t2": {p: row["t2"] for p, row in per.items()}},
        "n11": {"deductions_anchor": ded[1], "gap_pp": gap[1], "deductions_fixed_share": shares[1],
                "audit_cutoffs": [1, 2, 3, 4]},
        "minimum": {"n20_0": inp["req20"], "n1_1": inp["req11"]}, "mgmt_buffer": {"n20_0": 0.0, "n1_1": 0.0},
        "reg_scenarios": {"ids": [G1_S], G1_S: scen}},
        "dividends": {"policy": {"threshold": 0.0}}}


def g1_ctx(book: dict, rwa0: float, at1: float) -> dict:
    return {"B": book, "A": {"AT1": at1}, "rwa0": rwa0, "ded": cm.c_deduction_parts(book), "rub": cm.c_rub_rule(book)}


def g1_row(ctx: dict, inp: dict, line: dict, at: tuple, *, quarterly: bool = False, rwa=None) -> dict:
    """Строка примера рабочей функцией счёта норматива: годовой ветви (_c_capital) или квартального прохода
    (_c_quarter_capital). Неаудированная прибыль — прибыль квартала строки: отсечка аудита в каждом квартале."""
    y, h = at
    rwa = line["rwa"] if rwa is None else rwa
    profit = {(y, h): line["e"]}
    if quarterly:
        cap = cm._c_quarter_capital(ctx, G1_S, y, h, line["reserve"], profit)(line["bv"], line["dpreg"], rwa)
    else:
        cap = cm._c_capital(ctx, G1_S, y, h, line["bv"], line["dpreg"], line["reserve"], rwa, profit)
    return {**cap, "rwa": rwa, "dpreg": line["dpreg"],
            "bvreg": line["bv"] + line["dpreg"] - (1.0 - inp["fvoci_recognition"]) * line["reserve"],
            "dpp20": cap["n20"] - cap["k20"] / rwa - ctx["B"]["capital"]["n20"]["gap_pp"],
            "dpp11": cap["n11"] - cap["k11"] / rwa - ctx["B"]["capital"]["n11"]["gap_pp"]}


def assert_row(row: dict, want: dict, what: str) -> None:
    for field, value in want.items():
        got = -row[field] if field in ("dpp20", "dpp11") else row[field]
        close(got, value, f"{what}.{field}")


@pytest.mark.tact
@pytest.mark.parametrize("quarterly", [False, True], ids=["годовая ветвь", "квартальный проход"])
def test_appendix_g1_rows(quarterly):
    """H.1: строки якоря, квартала и «другой клетки» (RWA 1800) с рублями сценария ключом и в замороженной записи
    (п.п. на RWA модальной клетки 1500); на RWA модальной клетки обе записи дают одни нормативы, в другой клетке
    замороженная запись ниже ключа на рубли × (1 / RWA_мод − 1 / RWA); рубли, равные нулю, — строка без ключа бит в бит."""
    doc = example()["deduction_rub"]
    inp = doc["inputs"]
    keyed = g1_ctx(g1_book(inp), inp["rwa0"], inp["at1"])
    frozen = g1_ctx(g1_book(inp, frozen=True), inp["rwa0"], inp["at1"])
    assert keyed["rub"] is not None and frozen["rub"] is None
    for name, ctx, frozen_name in (("anchor", keyed, None), ("quarter", keyed, "quarter_frozen"),
                                   ("other_cell", keyed, "other_cell_frozen")):
        line = inp[name]
        assert_row(g1_row(ctx, inp, line, G1_AT[name], quarterly=quarterly), doc[name], name)
        if frozen_name:
            assert_row(g1_row(frozen, inp, line, G1_AT[name], quarterly=quarterly), doc[frozen_name], frozen_name)
    # остаток замороженной формы в другой клетке — рубли × (1 / RWA_мод − 1 / RWA)
    mine = g1_row(keyed, inp, inp["other_cell"], G1_AT["other_cell"], quarterly=quarterly)
    old = g1_row(frozen, inp, inp["other_cell"], G1_AT["other_cell"], quarterly=quarterly)
    rub, rwa, rwa_mod = inp["other_cell"]["rub20"], inp["other_cell"]["rwa"], inp["rwa_modal"]
    for j in ("20", "11"):
        close(mine[f"n{j}"] - old[f"n{j}"], doc["frozen_residual"][f"n{j}"], f"остаток замороженной формы n{j}")
        close(mine[f"n{j}"] - old[f"n{j}"], rub * (1.0 / rwa_mod - 1.0 / rwa), f"остаток по формуле n{j}")
    close(rub / rwa_mod * rwa, doc["frozen_residual"]["rub_frozen_in_other_cell"], "замороженная запись вычитает 18")
    close(rub, doc["frozen_residual"]["rub_k1"], "ключ вычитает 15")
    # рубли, равные нулю (числом и траекторией), — строка книги без ключа бит в бит
    zero = g1_book(inp)
    zero["capital"]["reg_scenarios"][G1_S][cm.RUB_KEY] = {"n20_0": 0.0, "n1_1": {"2026": 0, "LT": 0.0}}
    bare = g1_ctx(g1_book(inp, rub=False), inp["rwa0"], inp["at1"])
    zctx = g1_ctx(zero, inp["rwa0"], inp["at1"])
    assert zctx["rub"] is not None and bare["rub"] is None
    for name in ("anchor", "quarter", "other_cell"):
        assert (g1_row(zctx, inp, inp[name], G1_AT[name], quarterly=quarterly)
                == g1_row(bare, inp, inp[name], G1_AT[name], quarterly=quarterly))
    # на том же пути капитала и RWA: K ниже на рубли, норматив — на рубли / RWA (М§4.11, «что делает»)
    plain = g1_row(bare, inp, inp["other_cell"], G1_AT["other_cell"], quarterly=quarterly)
    for j, cap, norm in (("20", "k20", "n20"), ("11", "k11", "n11")):
        r = inp["other_cell"][f"rub{j}"]
        close(mine[cap] - plain[cap], -r, f"{cap}: минус рубли", EXACT)
        close(mine[norm] - plain[norm], -r / rwa, f"{norm}: минус рубли / RWA", EXACT)
    close(mine["n11_star"] - plain["n11_star"], -inp["other_cell"]["rub11"] / rwa, "Н20.1 с прибылью периода несёт рубли")


def fixed_inputs_ctx(book: dict, rwa0: float, at: tuple, *, oaf=0.0, path=None, dens_oaf=0.0, mult=None) -> dict:
    """Контекст чтения постоянных частей конца сетки (c_terminal_fixed_inputs): последний квартал сетки — at."""
    ctx = {"B": book, "rwa0": rwa0, "ded": cm.c_deduction_parts(book), "rub": cm.c_rub_rule(book),
           "periods": [{"year": at[0], "quarters": [at[1]]}], "oaf": oaf, "dens_oaf": dens_oaf, "rwa_mult": {},
           "oaf_path": path}
    if mult is not None:
        ctx["rwa_mult"] = mult
    return ctx


@pytest.mark.tact
def test_appendix_g1_terminal_and_bridge():
    """H.1: слагаемые X_T строки квартала как конца сетки (рубли — в нормативах строки) и постоянные в рублях вычеты
    конца сетки C_20 = Dfix + рубли, C_11 так же (М§7); мост Н20.0 от якоря до строки квартала: строка вычетов несёт
    растущую часть и рубли сценария, тождество «начало + сумма долей = конец»."""
    doc = example()["deduction_rub"]
    inp = doc["inputs"]
    book = g1_book(inp)
    ctx = g1_ctx(book, inp["rwa0"], inp["at1"])
    first = g1_row(ctx, inp, inp["anchor"], G1_AT["anchor"])
    last = g1_row(ctx, inp, inp["quarter"], G1_AT["quarter"])
    excess = cm.c_terminal_excess(last, inp["excess_capital_multiple"])
    for field in ("n20_t", "n11_t", "x20", "x11", "x_t"):
        close(excess[field], doc["terminal"][field], f"terminal.{field}")
    got = cm.c_terminal_fixed_inputs(fixed_inputs_ctx(book, inp["rwa0"], G1_AT["quarter"]), {"scenario": G1_S,
                                     "regime": "r"}, {**last, "dn_q": [1.0], "xf_q": [1.0]}, excess)
    close(got["c"][cm.NORM_TOTAL], doc["terminal"]["c20"], "C_20")
    close(got["c"][cm.NORM_BASE], doc["terminal"]["c11"], "C_11")
    assert got["binding"] == cm.NORM_TOTAL and got["f_a"] == 0.0 and got["r_f"] == 0.0
    bridge = cm.c_bridge_lines([(1.0, first, last)])
    want = doc["bridge"]
    for value, field in ((bridge["start"], "start"), (bridge["end"], "end"),
                         (bridge["deductions"]["amount"], "deductions_amount"), (bridge["deductions"]["pp"], "deductions_pp"),
                         (bridge["rwa_growth"]["pp"], "rwa_growth_pp"), (bridge["rest"]["amount"], "other_amount"),
                         (bridge["rest"]["pp"], "other_pp")):
        close(value, want[field], f"bridge.{field}")
    parts = ctx["ded"][cm.NORM_TOTAL]
    growing = -parts["grow"] * (inp["quarter"]["rwa"] / inp["rwa0"] - 1.0)
    close(growing, want["deductions_growing"], "мост: растущая часть")
    close(-(inp["quarter"]["rub20"] - inp["anchor"]["rub20"]), want["deductions_rub"], "мост: рубли сценария")
    close(bridge["deductions"]["amount"], growing + want["deductions_rub"], "мост: сумма строки вычетов", EXACT)
    close(bridge["start"] + bridge["deductions"]["pp"] + bridge["rwa_growth"]["pp"] + bridge["rest"]["pp"],
          bridge["end"], "мост: тождество", EXACT)


@pytest.mark.tact
def test_appendix_g1_reanchored_book_keeps_the_ratios():
    """H.1, перенос якоря (исполняет инструмент, не контрольная модель): книга нового якоря с траекторией рублей как
    есть — вычеты якоря — разности капиталов строки, суммы Dfix прежние, поправки — калибровкой к нормативам строки
    (рабочей функцией нормы: новая строка якоря вычитает рубли ещё раз) — даёт в следующем квартале те же нормативы,
    что прежняя книга, и при RWA 2000, и при любом RWA (свойство 12, тождество М§4.11)."""
    doc = example()["deduction_rub"]
    inp, want = doc["inputs"], doc["reanchor"]
    old = g1_ctx(g1_book(inp), inp["rwa0"], inp["at1"])
    row = g1_row(old, inp, inp["quarter"], G1_AT["quarter"])
    line = inp["quarter"]
    ded20 = row["bvreg"] + inp["at1"] + line["t2"] - row["k20"]
    ded11 = row["bvreg"] - max(line["e"], 0.0) - row["k11"]
    close(ded20, want["ded20_0"], "вычет нового якоря Н20.0")
    close(ded11, want["ded11_0"], "вычет нового якоря Н20.1")
    fix20, fix11 = old["ded"][cm.NORM_TOTAL]["fix"], old["ded"][cm.NORM_BASE]["fix"]
    close(fix20, want["dfix20"], "Dfix Н20.0")
    close(fix11, want["dfix11"], "Dfix Н20.1")
    shares = (fix20 / ded20, fix11 / ded11)
    close(shares[0], want["eta20"], "новая доля Н20.0")
    close(shares[1], want["eta11"], "новая доля Н20.1")
    # калибровка поправки: строка нового якоря с нулевой поправкой — и разность до норматива строки
    raw = g1_ctx(g1_book(inp, ded=(ded20, ded11), shares=shares, gap=(0.0, 0.0)), line["rwa"], inp["at1"])
    at_new = g1_row(raw, inp, line, G1_AT["quarter"])
    gap = (row["n20"] - at_new["n20"], row["n11"] - at_new["n11"])
    close(gap[0], want["gap20"], "поправка нового якоря Н20.0")
    close(gap[1], want["gap11"], "поправка нового якоря Н20.1")
    close(gap[0] - inp["gap20"], want["rub_at_new_anchor"] / line["rwa"], "поправка выросла на рубли / RWA_1")
    new = g1_ctx(g1_book(inp, ded=(ded20, ded11), shares=shares, gap=gap), line["rwa"], inp["at1"])
    nxt = inp["reanchor"]["next"]
    for which, rwa in (("next", nxt["rwa"]), ("next_other_rwa", inp["reanchor"]["next_other_rwa"])):
        a = g1_row(old, inp, nxt, G1_NEXT, rwa=rwa)
        b = g1_row(new, inp, nxt, G1_NEXT, rwa=rwa)
        assert_row(a, want[which]["old"], f"{which}.old")
        assert_row(b, want[which]["new"], f"{which}.new")
    for rwa in (400.0, 1000.0, 1500.0, 2600.0, 9000.0):
        for quarterly in (False, True):
            a = g1_row(old, inp, nxt, G1_NEXT, rwa=rwa, quarterly=quarterly)
            b = g1_row(new, inp, nxt, G1_NEXT, rwa=rwa, quarterly=quarterly)
            for name in ("n20", "n11", "n11_star"):
                close(b[name], a[name], f"RWA {rwa}: {name}", EXACT)


def g2_ctx(inp: dict, *, path="book", weight="book", level=None, anchor=None) -> dict:
    """Контекст RWA примера H.2: плотности примера, постоянная часть, читатель пути рабочей функцией правила книги."""
    dens = {"other_assets": inp["density_oa"], "other_assets_fixed": inp["density_oaf"],
            "securities": inp["density_securities"], "liquidity": inp["density_liquidity"]}
    if weight == "book":
        dens[cm.OAF_CHANGE_DENSITY] = inp["density_change"]
    elif weight is not None:
        dens[cm.OAF_CHANGE_DENSITY] = weight
    book = {"capital": {"rwa": {"density": dens}}, "volumes": {}}
    if path is not None:
        book["volumes"]["other_assets_fixed_change"] = inp["path"] if path == "book" else path
    oaf = inp["oa_fixed"] if level is None else level
    at = cm.c_per_parse(anchor or inp["anchor"])
    q_last = cm.c_qidx(at, *cm.c_per_parse(inp["periods"][-1]))
    return {"dens": dens, "oaf": oaf, "dens_oaf": inp["density_oaf"], "rwa_mult": {},
            "books": {cm.SECURITIES: {}, cm.LIQUIDITY: {}}, "oaf_path": cm.c_oaf_path_rule(book, oaf, at, q_last)}


@pytest.mark.tact
def test_appendix_g2_fixed_part_of_other_assets():
    """H.2: прочие активы `отношение × кредиты + OA_fixed + ΔOA_q`, RWA прочих активов рабочей функцией RWA — при
    весе приращения 0 (ключ), без ключа плотности (ω_oaf) и без пути; деньги убывания при том же капитале — в
    балансирующих активах (+20 и их RWA +3); перенос якоря на 2029К1 — постоянная часть всех кварталов прежняя, в
    квартале нового якоря приращение — ноль; отказы — якорное условие и знак суммы."""
    doc = example()["fixed_change"]
    inp = doc["inputs"]
    keyed, default, bare = g2_ctx(inp), g2_ctx(inp, weight=None), g2_ctx(inp, path=None)
    assert keyed["oaf_path"]["density"] == inp["density_change"]
    assert default["oaf_path"]["density"] == inp["density_oaf"] and bare["oaf_path"] is None
    nothing = {cm.SECURITIES: 0.0, cm.LIQUIDITY: 0.0}
    for row, loans in zip(doc["rows"], inp["loans"]):
        y, q = cm.c_per_parse(row["period"])
        delta = cm.c_oaf_change(keyed, y, q)
        close(delta, row["delta"], f"{row['period']}: ΔOA")
        close(inp["oa_fixed"] + delta, row["oa_fixed_q"], f"{row['period']}: OA_fixed,q")
        oa = inp["oa_ratio"] * loans + inp["oa_fixed"] + delta
        plain = inp["oa_ratio"] * loans + inp["oa_fixed"]
        close(oa, row["oa"], f"{row['period']}: OA")
        close(plain, row["oa_without_key"], f"{row['period']}: OA без пути")
        close(cm._c_rwa_of(keyed, None, y, q, nothing, oa, 1.0, 1.0), row["rwa_oa"], "RWA прочих активов, ω_Δ = 0")
        close(cm._c_rwa_of(default, None, y, q, nothing, oa, 1.0, 1.0), row["rwa_oa_default_density"],
              "RWA прочих активов без ключа плотности")
        close(cm._c_rwa_of(bare, None, y, q, nothing, plain, 1.0, 1.0), row["rwa_oa_without_key"], "RWA без пути")
        # деньги убывания: при тех же пассивах и капитале балансирующие активы больше на −ΔOA, по долям бумаг
        la = -delta
        close(la, row["la_shift"], "сдвиг LA")
        money = {cm.SECURITIES: inp["securities_share"] * la, cm.LIQUIDITY: (1.0 - inp["securities_share"]) * la}
        close(cm._c_rwa_of(keyed, None, y, q, money, oa, 1.0, 1.0) - cm._c_rwa_of(keyed, None, y, q, nothing, oa, 1.0, 1.0),
              row["rwa_la_shift"], "RWA сдвига LA")
    close(doc["w_la"], inp["securities_share"] * inp["density_securities"]
          + (1.0 - inp["securities_share"]) * inp["density_liquidity"], "вес рубля LA")
    # перенос якоря: Δ_1 — в число, траектория минус Δ_1 (исполняет инструмент; здесь — формула на книге после него)
    re = doc["reanchor"]
    y1, q1 = cm.c_per_parse(re["new_anchor"])
    d1 = cm.c_oaf_change(keyed, y1, q1)
    close(inp["oa_fixed"] + d1, re["oa_fixed"], "постоянная часть нового якоря")
    shifted = {k: v - d1 for k, v in inp["path"].items()}
    assert {str(k): v for k, v in shifted.items()} == {str(k): v for k, v in re["path"].items()}
    moved = g2_ctx(inp, path=re["path"], level=re["oa_fixed"], anchor=re["new_anchor"])
    assert cm.c_oaf_change(moved, y1, q1) == 0.0                      # якорное условие новой книги
    for row in re["rows"]:
        y, q = cm.c_per_parse(row["period"])
        close(inp["oa_fixed"] + cm.c_oaf_change(keyed, y, q), row["oa_fixed_q_old"], "прежняя книга")
        close(re["oa_fixed"] + cm.c_oaf_change(moved, y, q), row["oa_fixed_q_new"], "книга нового якоря")
    for case in doc["refusals"]:
        with pytest.raises(cm.ControlInputError, match="якорное условие" if case["name"] == "no_anchor_zero"
                           else "знак суммы"):
            g2_ctx(inp, path=case["trajectory"])


G3_W, G3_R, G3_S = "W", "r", "s"


def g3_value(inp: dict, lam, *, pbt: float, asset: float = 0.0, side: str = "both", recap=None,
             mult=None) -> dict:
    """Синтетическая клетка H.3 — рабочей функцией оценки клетки (_c_value_cell) на контексте из входов примера:
    один период из четырёх кварталов, дата оценки — начало первого квартала, плата за капитал квартала k_q. Блок
    постоянных частей читается рабочей функцией из контекста: постоянная часть прочих активов и её приращение конца
    сетки, плотности, доли и рубли сценария, поправки и п.п. сценария. Актив A — бездоходный, вычтенный один к
    одному (Dfix + A), с весом риска 0 (приращение пути с весом 0) и оплаченный капиталом (капитал + A).
    side: both — обе стороны; capital — без постоянных активов; balance — без постоянных вычетов. recap — правило
    докапитализации ({"d": дисконт}): терминал по цене размещения (М§7), взносов явного участка нет. mult —
    траектория множителя плотности режима клетки (М§4.11): R_F несёт его значение в последнем квартале сетки."""
    t, src, cell = inp["terminal"], inp["block_source"], inp["cell"]
    rwa0 = 1000.0
    book = {"valuation": {"terminal": {"excess_capital_multiple": t["multiple"], "fade": t["fade"],
                                       "real_growth": t["real_growth"]}},
            "worlds": {G3_W: {"lt_inflation": t["lt_inflation"]}}, "pnl": {"nci_share": t["nci"]},
            "volumes": {"liquid_min_share": t["min_share"], "securities_share_of_liquid": 0.5},
            "tax": {"statutory": t["tau_stat"]},
            "capital": {"n20": {"gap_pp": src["gap20"]}, "n11": {"gap_pp": src["gap11"]},
                        "reg_scenarios": {G3_S: {"deduction_pp": {"n20_0": src["dpp20_q"], "n1_1": src["dpp11_q"]}}}}}
    fixed_c = side != "balance"
    fixed_a = side != "capital"
    ded = {cm.NORM_TOTAL: {"share": None, "fix": (src["dfix20"] if fixed_c else 0.0) + asset,
                           "grow": src["dgrow20_over_rwa0"] * rwa0},
           cm.NORM_BASE: {"share": None, "fix": (src["dfix11"] if fixed_c else 0.0) + asset,
                          "grow": src["dgrow11_over_rwa0"] * rwa0}}
    rub = {G3_S: {cm.NORM_TOTAL: src["rub20_q"], cm.NORM_BASE: src["rub11_q"]}} if fixed_c else None
    path = {"traj": (src["delta_q"] if fixed_a else 0.0) + asset, "v0": 0.0, "density": src["density_change"],
            "memo": {}}
    n = len(cell["ci"]) - 1
    k_q = cell["k_q"]
    ctx = {"B": book, "A": {"BV": cell["bv"][0] + asset, "cpn_quarter": 1, "cpn_annual": t["coupon"]},
           "clock": {"p0": 0, "pos": 0.0, "t_start": {0: 0.0}, "tau_end": {0: n / cm.QY}},
           "periods": [{"year": 2036, "quarters": list(range(1, n + 1)), "n": n}],
           "disc": {G3_W: lambda tau: (1.0 + k_q) ** (-cm.QY * tau)}, "recap": recap, "lam_f": lam,
           "oaf": src["oa_fixed"] if fixed_a else 0.0, "dens_oaf": src["density_oaf"], "oaf_path": path,
           "rwa_mult": {} if mult is None else {G3_R: mult}, "ded": ded, "rub": rub, "rwa0": rwa0}
    assets = 1000.0                       # балансирующие активы: запас над минимумом m × активы — вход примера
    liquid = t["headroom"] + t["min_share"] * assets
    row = {"ci_q": cell["ci"][1:], "ci": sum(cell["ci"][1:]), "div_list": [(j, d) for j, d in enumerate(cell["div"][1:])],
           "rec_list": [], "bv": cell["bv"][-1] + asset, "n20": t["n20"], "n11_star": t["n11_star"], "dpreg": 0.0,
           "rwa": t["rwa"], "req20": t["req20"], "req11": t["req11"], "securities": liquid / 2.0,
           "liquidity": liquid / 2.0, "assets": assets, "wholesale_extra": t["wt"], "y_sec_end": t["y_bal"],
           "y_liq_end": t["y_bal"], "c_wh_end": t["c_wh"], "pbt": pbt, "tau_eff": t["tau"],
           "dn_q": [src["dn_x_m"]] * n, "xf_q": [1.0] * n}
    return cm._c_value_cell(ctx, {"world": G3_W, "regime": G3_R, "scenario": G3_S}, [row], {})


def g3_check(out: dict, want: dict, what: str) -> None:
    term, value = want["terminal"], want["value"]
    for mine, theirs in (("x_t", "x_t"), ("bv_star", "bv_star"), ("g_t", "g"), ("y_x", "y_x"), ("ci_t1", "ci"),
                         ("roe_t_raw", "roe"), ("roe_t", "roe_faded"), ("tv_ri", "tv_ri"), ("tv_ddm", "tv_ddm")):
        close(out[mine], term[theirs], f"{what}: {theirs}")
    close(out["tv_ddm"] - out["x_t"], term["p_t"], f"{what}: P_T")
    close(out["v_ri"], value["v_ri"], f"{what}: V_RI")
    close(out["v_ddm"], value["v_ddm"], f"{what}: V_DDM")
    close(out["df_l"], value["df_q"], f"{what}: DF_Q")
    close(out["df_l"] * out["tv_ri"], value["pv_terminal"], f"{what}: терминал в оценке")
    close(out["tv_ddm"], out["bv_star"] + out["x_t"] + out["tv_ri"], f"{what}: TV_DDM = BV_Q + TV_RI", EXACT)
    assert abs(out["v_ddm"] - out["v_ri"]) <= EXACT * abs(out["v_ri"]), what
    block = term["block"]
    if block is None:
        assert "terminal_fixed" not in out, what
        return
    node = out["terminal_fixed"]
    close(node["business_capital"], term["business_capital"], f"{what}: B")
    close(node["business_ci"], term["business_ci"], f"{what}: CI_B")
    assert node["lam_f"] == term["lam_f"] and node["binding"] == block["binding"], what
    for field in ("c", "kappa", "f_a", "r_f", "f_k", "y_m", "d_f", "i_f"):
        close(node[field], block[field], f"{what}: блок {field}")


@pytest.mark.tact
@pytest.mark.parametrize("case", ["below_k", "above_k"], ids=["ROE ниже k", "ROE выше k"])
def test_appendix_g3_terminal_of_the_synthetic_cell(case):
    """H.3: терминал и оценка синтетической клетки при λ_F = 1 (образец), 0,5 и 0 — с бездоходным активом и без него;
    блок постоянных частей (F_A, R_F, C, κ, F_K, D_F, I_F) читается из контекста рабочей функцией; λ_F = 0 — актив
    нейтрален точно; λ_F = 1 — вклад актива по формуле DF × A × (1 − φ k_T / (k_T − g_T)); при 0,5 — ровно середина;
    цена ключа — сумма цен сторон капитала и баланса; λ_F = 1 ключом — те же числа, что без ключа, бит в бит."""
    doc = example()["terminal"]
    inp, cases = doc["inputs"], doc["cases"][case]
    pbt, asset = cases["pbt_l"], inp["asset"]
    got = {}
    for lam_key, want in cases["by_lam"].items():
        lam = float(lam_key)
        lam_arg = None if lam == 1.0 else lam
        base = g3_value(inp, lam_arg, pbt=pbt)
        with_a = g3_value(inp, lam_arg, pbt=pbt, asset=asset)
        g3_check(base, want["base"], f"{case} λ_F={lam_key}")
        g3_check(with_a, want["with_asset"], f"{case} λ_F={lam_key} с активом")
        close(with_a["v_ri"] - base["v_ri"], want["asset_effect"], f"{case} λ_F={lam_key}: вклад актива")
        got[lam] = (base, with_a)
    assert got[0.0][1]["v_ri"] - got[0.0][0]["v_ri"] == pytest.approx(0.0, abs=1e-9)        # нейтральность
    k_t, g_t, df_q = got[1.0][0]["k_t"], got[1.0][0]["g_t"], got[1.0][0]["df_l"]
    phi = cases["fade_multiplier_lam1"]
    assert phi == (inp["terminal"]["fade"] if got[1.0][0]["roe_t_raw"] > k_t else 1.0)
    closed = df_q * asset * (1.0 - phi * k_t / (k_t - g_t))
    close(closed, cases["asset_effect_closed_form_lam1"], f"{case}: формула вклада при λ_F = 1")
    close(got[1.0][1]["v_ri"] - got[1.0][0]["v_ri"], closed, f"{case}: вклад актива при λ_F = 1")
    mid = (got[0.0][0]["v_ri"] + got[1.0][0]["v_ri"]) / 2.0
    close(got[0.5][0]["v_ri"] - mid, cases["linearity_gap"], f"{case}: линейность по λ_F")
    # λ_F = 1 ключом — прежние строки бит в бит; узел блока есть
    one = g3_value(inp, 1.0, pbt=pbt)
    assert "terminal_fixed" in one and one["terminal_fixed"]["lam_f"] == 1.0
    for field in ("v_ri", "v_ddm", "tv_ri", "tv_ddm", "roe_t", "roe_t_raw"):
        assert one[field] == got[1.0][0][field], field
    # стороны: капитал (без постоянных активов) и баланс (без постоянных вычетов); их сумма — цена обеих сторон
    sides = cases["sides"]
    price = {}
    for side in ("capital", "balance", "both"):
        out = g3_value(inp, 0.0, pbt=pbt, side=side)
        g3_check(out, sides[side], f"{case}: сторона {side}")
        price[side] = out["v_ri"] - got[1.0][0]["v_ri"]
        close(price[side], sides[side]["price_vs_sample"], f"{case}: цена стороны {side}")
    close(price["capital"] + price["balance"] - price["both"], sides["sum_of_sides_minus_both"],
          f"{case}: сумма сторон")


@pytest.mark.tact
def test_terminal_lines_refuse_business_capital_below_zero_and_keep_the_forms():
    """B ≤ 0 — отказ с названием клетки (М§7, «Условия»); при любом λ_F TV_DDM = BV_Q + TV_RI; связывающий на T
    Н20.1 — блок берёт C_11 и κ_11; при доборе опта на конце сетки маржинальная ставка блока — ставка опта."""
    block = {"lam_f": 0.0, "f_k": 900.0, "i_f": -20.0}
    with pytest.raises(cm.ControlInputError, match="клетка N/crisis/strict"):
        cm.c_terminal_lines(10.0, 800.0, 90.0, 0.17, 0.06, 0.5, block, where="N/crisis/strict")
    for lam in (0.0, 0.3, 0.5, 0.99, 1.0):
        for ci in (60.0, 200.0):
            out = cm.c_terminal_lines(25.0, 1000.0, ci, 0.17, 0.06, 0.5,
                                      {"lam_f": lam, "f_k": 120.0, "i_f": -9.0})
            close(out["tv_ddm"], 1000.0 + 25.0 + out["tv_ri"], f"λ_F {lam}: TV_DDM = BV_Q + TV_RI", EXACT)
    # блок: связывает Н20.1 — C_11 и κ_11; при доборе опта — ставка опта (через _c_value_cell — H.3 с подменами)
    doc = example()["terminal"]
    inp = copy.deepcopy(doc["inputs"])
    inp["terminal"]["req11"] = inp["terminal"]["n11_star"] - 0.005           # Н20.1: (13 − 12,5) % < (14 − 13) %
    out = g3_value(inp, 0.0, pbt=160.0)
    node = out["terminal_fixed"]
    assert node["binding"] == cm.NORM_BASE
    close(node["c"], inp["block_source"]["dfix11"] + inp["block_source"]["rub11_q"], "C_11")
    kappa11 = (inp["terminal"]["req11"] - (inp["block_source"]["gap11"] - inp["block_source"]["dpp11_q"])
               + inp["block_source"]["dgrow11_over_rwa0"])
    close(node["kappa"], kappa11, "κ_11")
    close(node["f_k"], node["c"] + kappa11 * node["r_f"], "F_K по Н20.1")
    inp = copy.deepcopy(doc["inputs"])
    inp["terminal"]["wt"] = 50.0
    out = g3_value(inp, 0.0, pbt=160.0)
    assert out["terminal_fixed"]["y_m"] == inp["terminal"]["c_wh"]
    close(out["terminal_fixed"]["i_f"], -inp["terminal"]["c_wh"] * out["terminal_fixed"]["d_f"]
          * (1.0 - inp["terminal"]["tau"]), "I_F по ставке опта")
    # R_F — RWA постоянных частей с множителем плотности режима последнего квартала сетки (М§7, §4.11)
    plain = g3_value(doc["inputs"], 0.0, pbt=160.0)["terminal_fixed"]
    relief = g3_value(doc["inputs"], 0.0, pbt=160.0, mult={"2035": 1.0, "2036Q4": 0.8, "LT": 0.9})["terminal_fixed"]
    close(relief["r_f"], 0.8 * plain["r_f"], "R_F с множителем режима")
    close(relief["f_k"], plain["c"] + plain["kappa"] * 0.8 * plain["r_f"], "F_K с множителем режима")
    # цена размывания терминала (М§7): P_T — выплата бизнеса и поток стоящей доли одной суммой; DDM = RI
    for lam in (0.0, 0.5, None):
        out = g3_value(doc["inputs"], lam, pbt=40.0, recap={"d": 0.2})
        p_t = out["tv_ddm"] - out["x_t"]
        assert p_t < 0.0, "вход теста: отрицательная капиталонейтральная выплата"
        close(out["p_t"], p_t, f"λ_F {lam}: P_T", EXACT)
        close(out["dc_t"], 0.2 / 0.8 * (max(-out["x_t"], 0.0) + max(-p_t, 0.0)), f"λ_F {lam}: DC_T", EXACT)
        assert abs(out["v_ddm"] - out["v_ri"]) <= EXACT * abs(out["v_ri"])


# ============================================================================ свойства на форме образца


@pytest.fixture(scope="module")
def inputs():
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8")), cm.c_facts_bundle(FIXTURE / "facts")


@pytest.fixture(scope="module")
def plain(inputs):
    return cm.c_control_run(*inputs)


@pytest.fixture(scope="module")
def keyed(inputs):
    """Форма образца со всеми ключами пятого прохода: доли вычета якоря, рубли сценария (свои у каждого сценария),
    путь постоянной части с весом приращения 0, λ_F = 0."""
    book, facts = inputs
    return cm.c_control_run(put(with_path(with_rub(with_shares(book, ETA20, ETA11))), LAM, 0.0), facts)


@pytest.mark.tact
def test_zero_keys_and_lambda_one_are_the_sample_branch(inputs, plain):
    """Без ключей — прежняя строка; рубли сценария, равные нулю, приращения постоянной части, равные нулю, и λ_F = 1
    вместе — ряды, оценка и точка книги без ключей бит в бит; узлы пятого прохода есть только у книги с ключами."""
    book, facts = inputs
    assert plain["ctx"]["rub"] is None and plain["ctx"]["oaf_path"] is None and plain["ctx"]["lam_f"] is None
    assert "fixed_parts" not in plain and all("terminal_fixed" not in c for c in plain["cells"])
    same = cm.c_control_run(put(with_keys(zero_rub(book), {PATH: 0.0, DENS_FIXED: 0.4}), LAM, 1.0), facts)
    assert values_of(same) == values_of(plain)
    assert [c["anchor_capital"] for c in same["cells"]] == [c["anchor_capital"] for c in plain["cells"]]
    assert "fixed_parts" in same and all(c["terminal_fixed"]["lam_f"] == 1.0 for c in same["cells"])


# вне такта сервера: свойство проверяется лишними прогонами сетки формы образца — они идут в CI
def test_each_zero_key_alone_is_the_sample_branch(inputs, plain):
    """Каждый ключ по отдельности: рубли сценария, равные нулю (числом и траекторией), приращения постоянной части,
    равные нулю (с весом приращения и без него, при нулевом уровне), λ_F = 1 числом и целым — ряды, оценка и точка
    книги без ключей бит в бит."""
    book, facts = inputs
    zeros = (zero_rub(book), with_path(book, path={"2026": 0.0, "LT": 0.0}, weight=0.3, level=False),
             with_keys(book, {PATH: 0.0, DENS_FIXED: 0.4}), put(book, LAM, 1.0), put(book, LAM, 1))
    for same_book in zeros:
        same = cm.c_control_run(same_book, facts)
        assert values_of(same) == values_of(plain)
        assert [c["anchor_capital"] for c in same["cells"]] == [c["anchor_capital"] for c in plain["cells"]]
        assert "fixed_parts" in same


@pytest.mark.tact
def test_bad_fifth_pass_keys_fail_loudly(inputs):
    """Ограничения № 8, 23–25 приложения A: рубли не у всех сценариев, объект без траектории или с лишним ключом,
    null в траектории; путь постоянной части без нуля в квартале якоря (и траектория, которая начинается ключом года
    после якоря), постоянная часть ниже нуля, вес приращения не число ≥ 0, путь без плотности; λ_F вне [0; 1] или не
    числом; null у ключа — отказ (М§0.1). Ноль и единица у λ_F допустимы."""
    book, facts = inputs
    ids = book["capital"]["reg_scenarios"]["ids"]
    some = put(book, f"capital.reg_scenarios.{ids[0]}.{cm.RUB_KEY}", {"n20_0": 1.0, "n1_1": 1.0})
    with pytest.raises(cm.ControlInputError, match="не у всех"):
        cm.c_control_context(some, facts)
    full = with_rub(book)
    for bad, word in (({"n20_0": 1.0}, "ровно"), ({"n20_0": 1.0, "n1_1": 1.0, "n2": 1.0}, "ровно"),
                      ({"n20_0": None, "n1_1": 1.0}, "null"), ({"n20_0": {"2027": None}, "n1_1": 1.0}, "null"),
                      ({"n20_0": "15", "n1_1": 1.0}, "не траектория"), (None, "ровно"), (5.0, "ровно")):
        with pytest.raises(cm.ControlInputError, match=word):
            cm.c_control_context(put(full, f"capital.reg_scenarios.{ids[-1]}.{cm.RUB_KEY}", bad), facts)
    for path, word in ((5.0, "якорное условие"), ({"2027": -10.0, "2028": -20.0}, "якорное условие"),
                       ({"2026Q2": 1e-6, "2028": -20.0}, "якорное условие"), ({"2026": 0.0, "2030": -1300.0}, "знак суммы"),
                       (None, "null"), ({"2026": 0.0, "2027": None}, "null")):
        with pytest.raises(cm.ControlInputError, match=word):
            cm.c_control_context(with_path(book, path=path), facts)
    assert cm.c_control_context(with_path(book, path={"2026Q2": 1e-10, "2028": -20.0}), facts)["oaf_path"] is not None
    for weight in (-0.1, "0.5", True, float("nan"), float("inf"), None):
        with pytest.raises(cm.ControlInputError, match="не число ≥ 0"):
            cm.c_control_context(with_path(book, weight=weight) if weight is not None
                                 else put(with_path(book), DENS_CHANGE, None), facts)
    with pytest.raises(cm.ControlInputError, match="не число ≥ 0"):        # ключ веса без пути — тоже (№ 24)
        cm.c_control_context(put(book, DENS_CHANGE, -0.1), facts)
    with pytest.raises(cm.ControlInputError, match="№ 8"):
        cm.c_control_context(with_path(book, weight=None, level=False), facts)
    created = with_path(book, path={"2026": 0.0, "2028": 30.0}, weight=0.0, level=False)    # путь создаёт часть с нуля
    assert cm.c_control_context(created, facts)["oaf_path"]["density"] == 0.0
    for lam in (-0.01, 1.01, "0.5", True, None, float("nan"), {"LT": 0.5}):
        with pytest.raises(cm.ControlInputError, match="fixed_growth_share"):
            cm.c_control_context(put(book, LAM, lam), facts)
    for lam in (0, 0.0, 0.5, 1, 1.0):
        assert cm.c_control_context(put(book, LAM, lam), facts)["lam_f"] == float(lam)


def test_rub_deduction_row_follows_the_formula(keyed, plain):
    """Свойство 9 (М§4.11): в каждой строке каждой клетки вычет каждого норматива равен
    Ded_0 × [(1 − η) × RWA / RWA_0 + η] + Drub_s(квартал строки), а K20 и K11, пересчитанные тестом по рядам клетки,
    совпадают с её рядами; аддитивное слагаемое N − K / RWA рублей не несёт; у сценариев с разными рублями — свои
    ряды; в строке якоря вычет — ключ плюс рубли квартала якоря (у книги — ноль)."""
    ctx = keyed["ctx"]
    B, rwa0 = ctx["B"], ctx["rwa0"]
    d20, d11 = cm.c_bnum(B, tcd.DED20), cm.c_bnum(B, tcd.DED11)
    f = cm.c_bnum(B, "capital.n20.fvoci_recognition")
    seen = set()
    for c, p in zip(keyed["cells"], plain["cells"]):
        s = c["scenario"]
        first = c["anchor_capital"]
        y0, qa = ctx["anchor"]
        r20, r11 = cm.c_rub_at(ctx, s, y0, qa)
        assert (r20, r11) == (0.0, 0.0)
        close(first["ded20"], d20, "якорь: Ded20", EXACT)
        for period, r, base in zip(ctx["periods"], c["rows"], p["rows"]):
            y, h = period["year"], period["quarters"][-1]
            r20, r11 = cm.c_rub_at(ctx, s, y, h)
            assert r20 == cm.c_traj_at(B["capital"]["reg_scenarios"][s][cm.RUB_KEY]["n20_0"], y, h)
            grow = r["rwa"] / rwa0
            close(r["ded20"], d20 * ((1.0 - ETA20) * grow + ETA20) + r20, "Ded20", EXACT)
            close(r["ded11"], d11 * ((1.0 - ETA11) * grow + ETA11) + r11, "Ded11", EXACT)
            own = r["bv"] + r["dpreg"] - (1.0 - f) * r["R"]
            t2 = cm.c_traj_at(cm.c_bget(B, "capital.n20.t2"), y, h)
            close(r["k20"], own - r["ded20"] + ctx["A"]["AT1"] + t2, "K20", EXACT)
            close(r["k11"], own - max(r["e_unaudited"], 0.0) - r["ded11"], "K11", EXACT)
            for norm, cap in (("n20", "k20"), ("n11", "k11")):
                assert r[norm] - r[cap] / r["rwa"] == pytest.approx(base[norm] - base[cap] / base["rwa"], abs=EXACT)
            seen.add((s, round(r20, 9)))
    assert len({s for s, _ in seen}) == len(ctx["B"]["capital"]["reg_scenarios"]["ids"])
    assert len({x for _, x in seen}) > len(ctx["periods"])          # у сценариев разные рубли


def test_rubles_lower_capital_by_their_sum_where_capital_ignores_the_ratios(inputs):
    """Свойство 10 (М§4.11): на книге без выплаты путь капитала и RWA от нормативов не зависит — K каждого норматива
    ниже, чем без рублей, ровно на рубли сценария строки, норматив — на рубли / RWA клетки (то же, что запись
    deduction_pp + Drub / RWA по ряду RWA самой клетки), а запись на RWA другой клетки RWA_мод даёт норматив ниже
    ключа на Drub × (1 / RWA_мод − 1 / RWA); слагаемые X_T ниже на рубли конца сетки; Н20.1 с прибылью периода несёт
    рубли."""
    book, facts = inputs
    still = with_shares(with_keys(book, NO_PAYOUT), ETA20, ETA11)
    bare, keyed = cm.c_control_run(still, facts), cm.c_control_run(with_rub(still), facts)
    ctx = keyed["ctx"]
    mult = cm.c_bnum(ctx["B"], "valuation.terminal.excess_capital_multiple")
    modal = cm.c_cell_of(bare, *bare["central"]["cell"])
    moved = 0.0
    for a, b in zip(bare["cells"], keyed["cells"]):
        for i, (period, ra, rb) in enumerate(zip(ctx["periods"], a["rows"], b["rows"])):
            assert (ra["bv"], ra["rwa"], ra["div"]) == (rb["bv"], rb["rwa"], rb["div"])
            r20, r11 = cm.c_rub_at(ctx, b["scenario"], period["year"], period["quarters"][-1])
            close(rb["k20"] - ra["k20"], -r20, "K20 ниже на рубли", 1e-9)
            close(rb["k11"] - ra["k11"], -r11, "K11 ниже на рубли", 1e-9)
            close(rb["n20"] - ra["n20"], -r20 / rb["rwa"], "Н20.0: рубли / RWA клетки", EXACT)
            close(rb["n11_star"] - ra["n11_star"], -r11 / rb["rwa"], "Н20.1 с прибылью периода", EXACT)
            frozen = ra["n20"] - r20 / modal["rows"][i]["rwa"]           # запись на RWA модальной клетки
            close(frozen - rb["n20"], -r20 * (1.0 / modal["rows"][i]["rwa"] - 1.0 / rb["rwa"]), "остаток записи", EXACT)
            moved = max(moved, abs(frozen - rb["n20"]))
        last, base = cm.c_terminal_excess(b["rows"][-1], mult), cm.c_terminal_excess(a["rows"][-1], mult)
        y, h = ctx["periods"][-1]["year"], ctx["periods"][-1]["quarters"][-1]
        r20, r11 = cm.c_rub_at(ctx, b["scenario"], y, h)
        close(last["x20"] - base["x20"], -r20, "x20 ниже на рубли конца сетки", 1e-9)
        close(last["x11"] - base["x11"], -r11, "x11 ниже на рубли конца сетки", 1e-9)
    assert moved > 1e-5, "вход теста: RWA клеток расходятся с модальной"


@pytest.mark.tact
def test_bridge_deduction_line_carries_the_rubles(keyed):
    """Свойство 11: сумма строки вычетов моста Н20.0 смеси — −(E[Ded20_e] − Ded20_0) и
    −Dgrow_20 × (E[RWA_e] / RWA_0 − 1) − (E[Drub_e] − E[Drub_0]); тождество «начало + сумма долей = конец»."""
    ctx, mass = keyed["ctx"], cm.c_point_mass(keyed)
    grow = ctx["ded"][cm.NORM_TOTAL]["grow"]
    y0, qa = ctx["anchor"]
    rub0 = sum(mass[key(c)] * cm.c_rub_at(ctx, c["scenario"], y0, qa)[0] for c in keyed["cells"])
    for i, (year, period) in enumerate(zip(keyed["years"], ctx["periods"])):
        br = cm.c_capital_bridge(keyed, year)
        rwa = sum(mass[key(c)] * c["rows"][i]["rwa"] for c in keyed["cells"])
        rub = sum(mass[key(c)] * cm.c_rub_at(ctx, c["scenario"], year, period["quarters"][-1])[0]
                  for c in keyed["cells"])
        close(br["deductions"]["amount"], -grow * (rwa / ctx["rwa0"] - 1.0) - (rub - rub0), f"мост {year}", 1e-9)
        close(br["start"] + br["deductions"]["pp"] + br["rwa_growth"]["pp"] + br["rest"]["pp"], br["end"],
              f"мост {year}: тождество", EXACT)
    assert keyed["fixed_parts"]["bridge"] == cm.c_capital_bridge(keyed)


@pytest.mark.tact
def test_fixed_path_enters_other_assets_and_rwa(keyed):
    """Путь постоянной части (М§4.3, §4.11): в каждой строке прочие активы — отношение × кредиты + OA_fixed + ΔOA,
    а RWA, пересчитанные тестом по рядам строки (книги, бумаги, ликвидность, растущая часть прочих активов, уровень
    якоря с ω_oaf, приращение с ω_Δ, дрейф, валютный индекс), — её ряду; приращение — значение траектории квартала
    конца года минус значение квартала якоря; тождество баланса держится."""
    ctx = keyed["ctx"]
    B = ctx["B"]
    dens = B["capital"]["rwa"]["density"]
    r_oa = cm.c_bnum(B, "volumes.other_assets_to_loans")
    oaf, w_d = ctx["oaf"], ctx["oaf_path"]["density"]
    assert oaf == CORE_FIXED[OAF] and w_d == 0.0
    y0, qa = ctx["anchor"]
    v0 = cm.c_traj_at(CORE_PATH, y0, qa)
    assert v0 == 0.0
    steps = set()
    for c in keyed["cells"]:
        for period, r in zip(ctx["periods"], c["rows"]):
            y, h = period["year"], period["quarters"][-1]
            delta = cm.c_traj_at(CORE_PATH, y, h) - v0
            assert r["oaf_change"] == delta and r["oaf_ends"][-1] == delta
            close(r["oa"], r_oa * r["loans"] + oaf + delta, "OA", EXACT)
            base = sum(float(dens[b]) * x for b, x in r["books_end"].items())
            base += float(dens[cm.SECURITIES]) * r["securities"] + float(dens[cm.LIQUIDITY]) * r["liquidity"]
            base += (float(dens["other_assets"]) * (r["oa"] - oaf - delta) + CORE_FIXED[DENS_FIXED] * oaf
                     + w_d * delta)
            mult = ctx["rwa_mult"].get(c["regime"])
            scale = r["dn_q"][-1] * r["xf_q"][-1] * (cm.c_traj_at(mult, y, h) if mult is not None else 1.0)
            close(r["rwa"], base * scale, "RWA", 1e-11)
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
            steps.add(delta)
    assert len(steps) > 3


def test_density_of_the_change_defaults_to_the_fixed_density(inputs):
    """Без ключа плотности приращения — те же ряды, что с ключом, равным ω_oaf, бит в бит; при весе 0 RWA ниже, чем
    при весе ω_oaf, на ω_oaf × |ΔOA| × множители (уходящая часть больше не весит)."""
    book, facts = inputs
    default = cm.c_control_run(with_path(book, weight=None), facts)
    same = cm.c_control_run(with_path(book, weight=CORE_FIXED[DENS_FIXED]), facts)
    assert values_of(default) == values_of(same)
    assert default["ctx"]["oaf_path"]["density"] == CORE_FIXED[DENS_FIXED]


def test_released_money_goes_to_the_balancing_assets(inputs):
    """Деньги убывания (М§4.3, §4.10): на книге без выплаты (путь капитала от нормативов не зависит; годовая ветвь —
    кредиты от нормативов не зависят) балансирующие активы конца года выше, чем у книги с той же постоянной частью без
    пути, на −ΔOA плюс разность капитала (доход на эти деньги), пока минимум ликвидности не связывает; кривизна LA
    несёт поправку времени — среднее квартальных трапеций пути приращения вместо полусуммы начала и конца."""
    book, facts = inputs
    still = with_keys(book, {**NO_PAYOUT, **CORE_FIXED})
    bare = cm.c_control_run(still, facts)
    moved = cm.c_control_run(with_path(still, level=False), facts)
    seen = 0
    for a, b in zip(bare["cells"], moved["cells"]):
        for ra, rb in zip(a["rows"], b["rows"]):
            assert ra["loans"] == rb["loans"]
            # средний остаток небалансирующих активов года несёт то же среднее пути (минимум ликвидности, когда
            # он связывает на обоих концах года, считается от него)
            close(rb["assets_nb_avg"] - ra["assets_nb_avg"], cm._c_path_mean(rb["oaf_ends"]),
                  "средние небалансирующие активы", 1e-9)
            if ra["wholesale_extra"] or rb["wholesale_extra"]:
                continue
            la_a, la_b = ra["securities"] + ra["liquidity"], rb["securities"] + rb["liquidity"]
            # точность — фиксированной точки балансирующих статей (1e-11 доли BV)
            close(la_b - la_a, -rb["oaf_change"] + (rb["bv"] - ra["bv"]), "LA: −ΔOA + ΔBV", 1e-6)
            ends = rb["oaf_ends"]
            want = -(cm._c_path_mean(ends) - (ends[0] + ends[-1]) / 2.0)
            close(rb["curve_la"] - ra["curve_la"], want, "кривизна LA: время денег убывания", 1e-9)
            if rb["oaf_change"]:
                assert rb["bv"] > ra["bv"]               # деньги приносят доход балансирующих активов
                seen += 1
    assert seen


def test_quarter_pass_carries_the_path_and_the_rubles():
    """Квартальный проход (фикстура core_t: квартальный календарь, рост ограничен капиталом, множитель плотности
    режима, постоянные прочие активы якоря с плотностью 0) с рублями сценария и путём постоянной части: каждый квартал
    вычитает рубли своего квартала (вычет — формула), проход кончает год на тех же RWA и нормативах, что годовая строка
    с приращением конца года; DDM = RI в каждой клетке при λ_F = 0; нулевые ключи — прежние числа бит в бит."""
    book = json.loads((FIXTURE_T / "book.json").read_text(encoding="utf-8"))
    facts = cm.c_facts_bundle(FIXTURE_T / "facts")
    path = {"2026": 0.0, "2027Q2": -10.0, "2028": -40.0, "2029": -80.0, "LT": -120.0, "LT_from": 2032}
    ready = put(with_keys(with_rub(with_shares(book, ETA20, ETA11), {"schedule": 0.3, "mid": 0.4, "strict": 0.5}),
                          {PATH: path, DENS_CHANGE: 0.0}), LAM, 0.0)
    res = cm.c_control_run(ready, facts)
    ctx = res["ctx"]
    d20, d11 = cm.c_bnum(ctx["B"], tcd.DED20), cm.c_bnum(ctx["B"], tcd.DED11)
    for c in res["cells"]:
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"]))
        for r in c["rows"]:
            for x in r["quarters"]:
                y, h = cm.c_qper(ctx["anchor"], x["q"])
                r20, r11 = cm.c_rub_at(ctx, c["scenario"], y, h)
                grow = x["rwa"] / ctx["rwa0"]
                close(x["ded20"], d20 * ((1.0 - ETA20) * grow + ETA20) + r20, "квартал: Ded20", EXACT)
                close(x["ded11"], d11 * ((1.0 - ETA11) * grow + ETA11) + r11, "квартал: Ded11", EXACT)
            last = r["quarters"][-1]
            assert math.isclose(last["rwa"], r["rwa"], rel_tol=1e-8)
            assert abs(last["n20"] - r["n20"]) <= 1e-8 and abs(last["n11"] - r["n11"]) <= 1e-8
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
    assert any(r["oaf_change"] for c in res["cells"] for r in c["rows"])
    # нулевые ключи на квартальном проходе — прежние числа
    bare = cm.c_control_run(book, facts)
    zero = cm.c_control_run(put(with_keys(zero_rub(book), {PATH: {"2026": 0.0, "LT": 0.0}, DENS_CHANGE: 0.0}), LAM, 1.0),
                            facts)
    assert values_of(zero) == values_of(bare)


# вне такта сервера: лишние прогоны сетки формы образца — в CI
def test_ddm_equals_ri_for_every_share_of_growth(inputs, keyed):
    """Условие 12 М§6.4: при λ_F = 0; 0,5; 1 DDM = RI в каждой клетке; ряды клеток от λ_F не зависят (проход клеток
    его не читает); узел блока у каждой клетки; ROE терминала строки — бизнеса (без стоящей доли)."""
    book, facts = inputs
    base = put(with_path(with_rub(with_shares(book, ETA20, ETA11))), LAM, 0.5)
    half = cm.c_control_run(base, facts)
    one = cm.c_control_run(put(base, LAM, 1.0), facts)
    for res in (keyed, half, one):
        for c in res["cells"]:
            assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"])), key(c)
            node = c["terminal_fixed"]
            close(c["roe_t_raw"], node["business_ci"] / node["business_capital"], "ROE_T бизнеса", EXACT)
            close(node["business_capital"], c["bv_star"] - (1.0 - node["lam_f"]) * node["f_k"], "B", EXACT)
    assert rows_of(keyed) == rows_of(half) == rows_of(one)
    moved = [abs(a["v_ri"] - b["v_ri"]) for a, b in zip(keyed["cells"], one["cells"])]
    assert max(moved) > 1.0, "вход теста: λ_F двигает оценку"


# вне такта сервера: лишние прогоны сетки формы образца — в CI
def test_lambda_does_nothing_without_fixed_parts(inputs, plain):
    """Без постоянных частей (нет постоянных прочих активов, долей вычета и рублей) блок — нули, и оценка от λ_F не
    зависит бит в бит."""
    book, facts = inputs
    for lam in (0.0, 0.5):
        res = cm.c_control_run(put(book, LAM, lam), facts)
        assert values_of(res) == values_of(plain)
        assert all(c["terminal_fixed"]["f_k"] == 0.0 and c["terminal_fixed"]["i_f"] == 0.0 for c in res["cells"])


def with_dead_asset(book: dict, facts: dict, amount: float) -> tuple[dict, dict]:
    """Бездоходный актив A в клетке формы образца: вычтен из капитала один к одному (вычеты якоря + A, вся сумма —
    постоянная в рублях: доля η = A / (Ded_0 + A)), вес риска 0 (постоянная часть прочих активов с плотностью 0),
    оплачен капиталом (капитал и прочие активы якоря + A, совокупный доход тот же). Вход теста."""
    facts = copy.deepcopy(facts)
    for node in ("equity.bv_common", "other_assets"):
        cur = facts["balance"]
        *head, last = node.split(".")
        for part in head:
            cur = cur[part]
        if isinstance(cur[last], dict):
            cur[last]["v"] = float(cur[last]["v"]) + amount
        else:
            cur[last] = float(cur[last]) + amount
    d20, d11 = book["capital"]["n20"]["deductions_anchor"], book["capital"]["n11"]["deductions_anchor"]
    out = with_keys(book, {OAF: amount, DENS_FIXED: 0.0,
                           tcd.DED20: d20 + amount, tcd.DED11: d11 + amount,
                           SHARE20: amount / (d20 + amount), SHARE11: amount / (d11 + amount)})
    return out, facts


@pytest.mark.parametrize("amount", [300.0, 800.0])
def test_dead_asset_is_neutral_when_fixed_parts_stand_in_rubles(inputs, amount):
    """Контрольный случай нейтральности (М§7, §17): клетка с бездоходным активом A, вычтенным из капитала один к
    одному, с весом риска 0 и оплаченным капиталом, при λ_F = 0 — оценка той же клетки без актива (сверх допуска V_c:
    ≤ 1e-9 отн., пока минимум ликвидности не связывает); при λ_F = 1 разность — DF_v(τ_Q) × A × (1 − φ × k_T /
    (k_T − g_T)), φ — угасание при положительном избытке, иначе 1."""
    book, facts = inputs
    dead_book, dead_facts = with_dead_asset(book, facts, amount)
    for lam in (0.0, 1.0):
        base = cm.c_control_run(put(book, LAM, lam), facts)
        dead = cm.c_control_run(put(dead_book, LAM, lam), dead_facts)
        fade = cm.c_bnum(base["ctx"]["B"], "valuation.terminal.fade")
        judged = 0
        for a, b in zip(base["cells"], dead["cells"]):
            for ra, rb in zip(a["rows"], b["rows"]):
                assert rb["bv"] == pytest.approx(ra["bv"] + amount, rel=1e-12)
                assert rb["n20"] == pytest.approx(ra["n20"], abs=1e-12) and rb["rwa"] == pytest.approx(ra["rwa"], rel=1e-12)
            if lam == 0.0:
                assert b["v_ri"] == pytest.approx(a["v_ri"], rel=1e-9), key(a)
                judged += 1
            elif (a["roe_t_raw"] > a["k_t"]) == (b["roe_t_raw"] > b["k_t"]):
                # формула — внутри одной ветви угасания (клетка у самого k_T меняет ветвь от актива — не судится)
                phi = fade if a["roe_t_raw"] > a["k_t"] else 1.0
                want = a["df_l"] * amount * (1.0 - phi * a["k_t"] / (a["k_t"] - a["g_t"]))
                assert b["v_ri"] - a["v_ri"] == pytest.approx(want, rel=1e-6, abs=1e-6), key(a)
                judged += 1
        assert judged >= len(base["cells"]) - 2
        if lam == 0.0:
            assert dead["point"] == pytest.approx(base["point"], rel=1e-9)


# ============================================================================ сверка с ядром (в момент теста)


FORMS = {"rub": lambda book: with_rub(book),
         "rub-shares": lambda book: with_rub(with_shares(book, ETA20, ETA11)),
         "rub-no-payout": lambda book: with_rub(with_shares(with_keys(book, NO_PAYOUT), ETA20, ETA11)),
         "rub-zero": lambda book: zero_rub(book),
         "path": lambda book: with_path(book),
         "path-default-density": lambda book: with_path(book, weight=None),
         "path-from-zero": lambda book: with_path(book, path=CREATE_PATH, weight=0.5, level=False),
         "lam-0": lambda book: put(with_path(with_rub(with_shares(book, ETA20, ETA11))), LAM, 0.0),
         "lam-half": lambda book: put(with_path(with_rub(with_shares(book, ETA20, ETA11))), LAM, 0.5),
         "lam-1": lambda book: put(with_path(with_rub(with_shares(book, ETA20, ETA11))), LAM, 1.0),
         "lam-0-no-fixed": lambda book: put(book, LAM, 0.0),
         "recap-all": lambda book: put(with_path(with_rub(with_shares(with_keys(book, tcd.SHORT), ETA20, ETA11))),
                                       LAM, 0.0)}


@pytest.mark.ci_only
@pytest.mark.parametrize("form", list(FORMS))
def test_control_matches_core_with_fifth_pass_keys(inputs, form):
    """Форма образца с ключами пятого прохода против ядра (чёрный ящик: запуск и поля результата) — прежние строки
    в прежних допусках М§17. Расхождение — находка, а не повод подогнать контрольную модель."""
    book, facts = inputs
    ready = FORMS[form](book)
    run = tcd._core_run(ready, FIXTURE / "facts")
    ctl = cm.c_control_run(ready, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    assert not tcm.exact_match(run, ctl), "V0 слоёв совпали с ядром до 1e-9 — общий код"


@pytest.mark.ci_only
def test_control_matches_core_with_fifth_pass_keys_on_the_quarterly_form():
    """Фикстура core_t (квартальный календарь, рост ограничен капиталом, множитель плотности режима) с рублями
    сценария, путём постоянной части и λ_F = 0 против ядра — в допусках М§17."""
    book = json.loads((FIXTURE_T / "book.json").read_text(encoding="utf-8"))
    path = {"2026": 0.0, "2027Q2": -10.0, "2028": -40.0, "2029": -80.0, "LT": -120.0, "LT_from": 2032}
    ready = put(with_keys(with_rub(with_shares(book, ETA20, ETA11), {"schedule": 0.3, "mid": 0.4, "strict": 0.5}),
                          {PATH: path, DENS_CHANGE: 0.0}), LAM, 0.0)
    run = tcd._core_run(ready, FIXTURE_T / "facts")
    ctl = cm.c_control_run(ready, cm.c_facts_bundle(FIXTURE_T / "facts"))
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)


@pytest.mark.ci_only
def test_fifth_pass_keys_against_core_as_a_black_box(inputs, plain):
    """Ядро — чёрный ящик: рубли и приращения, равные нулю, и λ_F = 1 дают у ядра оценку книги без ключей; рубли, путь
    и λ_F двигают точку у двух моделей в одну сторону и на близкую величину; книги с ключами вне правил (№ 23–25)
    отвергают обе модели."""
    import importlib

    book, facts = inputs
    bare = tcd._core_run(book, FIXTURE / "facts")
    for same in (zero_rub(book), with_path(book, path={"2026": 0.0, "LT": 0.0}, weight=0.3, level=False),
                 put(book, LAM, 1.0)):
        run = tcd._core_run(same, FIXTURE / "facts")
        assert (run.point, run.low, run.high) == (bare.point, bare.low, bare.high)
        assert [c.v_ri for c in run.cells] == [c.v_ri for c in bare.cells]
    for form in ("rub-shares", "path", "lam-0"):
        ready = FORMS[form](book)
        mine = cm.c_control_run(ready, facts)["point"] - plain["point"]
        theirs = tcd._core_run(ready, FIXTURE / "facts").point - bare.point
        assert mine * theirs > 0.0 and abs(mine - theirs) <= tcm.TOL_VALUE * abs(bare.point), (form, mine, theirs)
    book_mod = importlib.import_module("model.book")
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    ids = book["capital"]["reg_scenarios"]["ids"]
    for bad in (put(book, f"capital.reg_scenarios.{ids[0]}.{cm.RUB_KEY}", {"n20_0": 1.0, "n1_1": 1.0}),
                put(with_rub(book), f"capital.reg_scenarios.{ids[0]}.{cm.RUB_KEY}", {"n20_0": 1.0}),
                with_path(book, path={"2027": -10.0, "2028": -20.0}), with_path(book, path={"2026": 0.0, "2030": -1300.0}),
                with_path(book, weight=-0.1), put(book, LAM, 1.5), put(book, LAM, -0.5)):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(bad, facts)
        with pytest.raises(Exception) as refused:
            book_mod.book_from_dict(bad, facts=core_facts)
        assert type(refused.value).__name__ == "BookError", refused.value
