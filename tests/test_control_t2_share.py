# -*- coding: utf-8 -*-
"""Контрольная модель, седьмой проход ядра (docs/MODEL.md §4.11, §4.14, §7, §17): дополнительный капитал держит долю
RWA своей клетки — ключ capital.n20.t2_share {enabled, from}.

* Пример приложения K методики (машинная копия tests/fixtures/core_pass7/example.json): контрольная модель подставляет
  входы примера в свои рабочие функции — правило ключа, долю клетки, T2 квартала, счёт норматива годовой ветви и
  квартального прохода, оценку клетки с терминалом, решение о взносе, строки моста — и получает его числа до 1e-9
  (М§17): K.1 — доли и путь T2 двух клеток, строки конца сетки с ключом и в рублёвой записи; K.2 — слагаемые X_T, κ_20
  блока постоянных частей, терминал при λ_F = 1 и 0 с ключом, без поправки κ и в рублёвой записи, капитал и
  инструменты бизнеса за T; K.3 — второй порядок взноса; K.4 — мост; K.6 — сдвиг оси; K.7 — случаи схемы (отказы —
  точно). Перенос якоря (K.5) исполняет инструмент перезаякоривания, не контрольная модель.
* Свойства своего счёта на фикстурах формы образца (tests/fixtures/core — годовая ветвь) и формы панели
  (tests/fixtures/core_t — квартальный проход капитала, ограничение роста, множитель плотности режима) с ключом,
  подставленным тестом: без ключа и при enabled: false — прежние числа бит в бит; доля клетки — значение траектории в
  квартале q_χ − 1 к RWA клетки на его конце (у квартала внутри года — по квартальному профилю RWA; у квартального
  прохода — RWA записанного шага, и при урезанном росте); с q_χ ряд T2 — доля на RWA строки, K20 и K11 пересчитываются
  тестом по рядам клетки, слагаемое доли в Н20.0 — χ_c; пробный проход дивиденда, идущий через q_χ − 1, задаёт долю
  своими RWA; на книге без выплаты RWA, K11 и Н20.1 — бит в бит книги без ключа, K20 и X_T больше ровно на
  χ_c × RWA − T2; κ_20 блока постоянных частей меньше ровно на χ_c, κ_11 прежний; взнос несёт T2 по доле.
* Контрольные случаи сверх сетки книги (М§17): from = first_period — доля якоря у всех клеток; траектория, записанная
  поквартально по RWA модальной клетки, — в этой клетке нормативы книги с ключом и без него совпадают.
* Сверка с ядром (метка ci_only; ядро импортируется только в момент теста) — прежние строки в прежних допусках М§17.

Числа подмен — входы тестов, а не допущения.
"""

from __future__ import annotations

import copy
import importlib
import json

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
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass7" / "example.json"
EXAMPLE_TOL = 1e-9          # пример приложения K: формулы без шага, одно определение (М§17)
EXACT = 1e-12               # своё свойство: те же действия над теми же числами
put, with_keys, close, key = tcd.put, tcd.with_keys, tcd.close, tcd.key
values_of, rows_of = tcd.values_of, tcd.rows_of
NO_PAYOUT = tcd.NO_PAYOUT
SHARE = cm.T2_SHARE
# Ключи форм (входы теста): квартал перед ключом — конец года (как у книги 0.5), квартал внутри года, первый прогнозный.
KEY_YEAR_END = {"enabled": True, "from": "2029Q1"}
KEY_MID = {"enabled": True, "from": "2028Q3"}
KEY_FIRST = {"enabled": True, "from": "2026Q3"}
KEY_T = {"enabled": True, "from": "2027Q4"}         # core_t: квартал перед ключом 2027К3 — рост урезан, множитель режима
OFF = {"enabled": False, "from": "2029Q1"}
# Постоянные части и λ_F = 0 на форме образца — как в tests/test_control_fixed_parts.py (входы теста).
FIXED_LAM0 = {cm.FIXED_GROWTH: 0.0, "volumes.other_assets_fixed": 1200.0,
              "capital.rwa.density." + cm.OAF_DENSITY: 0.8}
# Форма с нехваткой капитала, докапитализацией в четвёртом квартале и окном в один квартал (входы теста).
SHORT_Q4 = {**tcd.SHORT, "capital.recapitalization": {**tcd.SHORT["capital.recapitalization"],
                                                      "decision_quarter": cm.QY, "lookahead_quarters": 1}}
LEFT_SHARE = tcd.LEFT_SHARE


def with_share(book: dict, spec) -> dict:
    return put(book, SHARE, copy.deepcopy(spec))


# ============================================================================ пример приложения K


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


K_S = "example"
K_W, K_R = "W", "r"


def k_book(inp: dict, *, spec=None, traj=None, req=(0.10, 0.08)) -> dict:
    """Книга примера K из тех ключей, которые читают правило ключа и счёт норматива: якорь и границы сетки, вычеты
    якоря, признание фонда, инструменты (траектория по кварталам примера), поправки, путь вычета сценария (ноль, в
    квартале конца сетки — число примера), требования K.2 (10 % и 8 %). spec — ключ доли инструментов (None — нет)."""
    cap, pers = inp["capital"], inp["periods"]
    traj = inp["trajectory"] if traj is None else traj
    last = inp["quarter_Q"]["B"]
    dpp20 = {p: (last["dpp20"] if p == pers[-1] else 0.0) for p in pers}
    dpp11 = {p: (last["dpp11"] if p == pers[-1] else 0.0) for p in pers}
    book = {"meta": {"anchor_period": pers[0], "first_period": pers[1], "last_period": pers[-1]},
            "capital": {
                "n20": {"deductions_anchor": cap["ded20_0"], "fvoci_recognition": cap["fvoci_recognition"],
                        "gap_pp": cap["gap20"], "t2": dict(zip(pers, traj))},
                "n11": {"deductions_anchor": cap["ded11_0"], "gap_pp": cap["gap11"], "audit_cutoffs": [1, 2, 3, 4]},
                "minimum": {"n20_0": req[0], "n1_1": req[1]}, "mgmt_buffer": {"n20_0": 0.0, "n1_1": 0.0},
                "reg_scenarios": {"ids": [K_S], K_S: {"conservation": 0.0, "sifi": 0.0, "ccyb": 0.0,
                                                       "deduction_pp": {"n20_0": dpp20, "n1_1": dpp11}}}},
            "dividends": {"policy": {"threshold": 0.0}}}
    if spec is not None:
        book["capital"]["n20"]["t2_share"] = copy.deepcopy(spec)
    return book


def k_ctx(book: dict, inp: dict) -> dict:
    """Контекст счёта норматива на книге примера: квартал ключа — рабочей функцией правила ключа."""
    anchor = cm.c_per_parse(book["meta"]["anchor_period"])
    return {"B": book, "A": {"AT1": inp["capital"]["at1"]}, "rwa0": inp["capital"]["rwa0"],
            "ded": cm.c_deduction_parts(book), "rub": None, "anchor": anchor,
            "t2_from": cm.c_t2_share_rule(book, anchor)}


def k_specs(inp: dict) -> tuple[dict, dict]:
    return {"enabled": True, "from": inp["from"]}, {"enabled": False, "from": inp["from"]}


def k_chi(ctx: dict, inp: dict, rwa: list) -> float:
    """Доля клетки рабочей функцией: значение траектории в квартале q_χ − 1 к RWA клетки в нём."""
    y, h = cm.c_qper(ctx["anchor"], ctx["t2_from"] - 1)
    return cm.c_t2_share_of(ctx, y, h, rwa[ctx["t2_from"] - 1])


def k_row(ctx: dict, inp: dict, line: dict, at: tuple, share, *, quarterly: bool = False, rwa=None, bv=None) -> dict:
    """Строка квартала рабочей функцией счёта норматива: годовой ветви (_c_capital) или квартального прохода
    (_c_quarter_capital). Неаудированная прибыль — прибыль квартала строки (отсечка аудита в каждом квартале)."""
    y, h = at
    rwa = line["rwa"] if rwa is None else rwa
    bv = line["bv"] if bv is None else bv
    profit = {(y, h): line["e"]}
    if quarterly:
        cap = cm._c_quarter_capital(ctx, K_S, y, h, line["reserve"], profit, share)(bv, line["dpreg"], rwa)
    else:
        cap = cm._c_capital(ctx, K_S, y, h, bv, line["dpreg"], line["reserve"], rwa, profit, share)
    f = ctx["B"]["capital"]["n20"]["fvoci_recognition"]
    a20, a11 = cap["n20"] - cap["k20"] / rwa, cap["n11"] - cap["k11"] / rwa
    return {**cap, "rwa": rwa, "dpreg": line["dpreg"], "bv": bv, "bvreg": bv + line["dpreg"] - (1.0 - f) * line["reserve"],
            "a20": a20, "a11": a11, "share_term": cap["n20"] - (cap["k20"] - cap["t2"]) / rwa - a20}


@pytest.mark.tact
def test_appendix_k1_share_and_path():
    """K.1: правило ключа даёт q_χ = 3; доля клетки A — 12 / 1200 = 1 %, клетки B — 12 / 1500 = 0,8 %; путь T2 с ключом —
    траектория до q_χ − 1 и доля на RWA клетки с q_χ, включая последний квартал сетки; в рублёвой записи
    (enabled: false и без ключа) — траектория во всех кварталах; на пути клетки A ключ и траектория совпадают."""
    doc = example()["share"]
    inp = doc["inputs"]
    on, off = k_specs(inp)
    keyed, record, bare = k_ctx(k_book(inp, spec=on), inp), k_ctx(k_book(inp, spec=off), inp), k_ctx(k_book(inp), inp)
    assert keyed["t2_from"] == inp["q_chi"] and record["t2_from"] is None and bare["t2_from"] is None
    for name in ("A", "B"):
        rwa, want = inp["rwa"][name], doc["path"][name]
        assert rwa == want["rwa"]
        chi = k_chi(keyed, inp, rwa)
        close(chi, want["chi"], f"{name}: χ")
        for k, per in enumerate(inp["periods"]):
            y, h = cm.c_per_parse(per)
            t2 = cm.c_t2_at(keyed, y, h, rwa[k], chi)
            close(t2, want["t2_key"][k], f"{name} {per}: T2 с ключом")
            close(t2 / rwa[k], want["share_key"][k], f"{name} {per}: доля с ключом")
            for ctx in (record, bare):
                rec = cm.c_t2_at(ctx, y, h, rwa[k], chi)
                close(rec, want["t2_record"][k], f"{name} {per}: T2 рублями")
                close(rec / rwa[k], want["share_record"][k], f"{name} {per}: доля рублями")
            if k < inp["q_chi"]:
                assert t2 == cm.c_t2_at(record, y, h, rwa[k], chi)        # до квартала ключа — траектория бит в бит
                assert cm.c_t2_at(keyed, y, h, rwa[k], None) == t2         # доля там не читается
            else:
                with pytest.raises(cm.ControlInputError, match="не задана"):
                    cm.c_t2_at(keyed, y, h, rwa[k], None)
    assert doc["path"]["A"]["t2_key"] == doc["path"]["A"]["t2_record"]


@pytest.mark.tact
@pytest.mark.parametrize("quarterly", [False, True], ids=["годовая ветвь", "квартальный проход"])
def test_appendix_k1_rows(quarterly):
    """K.1: строки 2028К4 клеток A и B с ключом и в рублёвой записи рабочими функциями счёта норматива — BVreg, вычеты,
    T2, K20, K11, поправки, Н20.0, Н20.1 и Н20.1 с прибылью периода; слагаемое доли N20 − (K20 − T2) / RWA − A_20 — χ_c;
    Н20.0 клетки B с ключом выше на χ_B − T2_Q / RWA_Q, Н20.1 — тот же (инструменты в K11 не входят)."""
    doc = example()["share"]
    inp = doc["inputs"]
    on, off = k_specs(inp)
    keyed, record = k_ctx(k_book(inp, spec=on), inp), k_ctx(k_book(inp, spec=off), inp)
    at = cm.c_per_parse(inp["periods"][-1])
    for name in ("A", "B"):
        line, want = inp["quarter_Q"][name], doc["rows_Q"][name]
        chi = k_chi(keyed, inp, inp["rwa"][name])
        rows = {"key": k_row(keyed, inp, line, at, chi, quarterly=quarterly),
                "record": k_row(record, inp, line, at, None, quarterly=quarterly)}
        for which, row in rows.items():
            for field, value in want[which].items():
                close(row[field], value, f"{name}.{which}.{field}")
        close(rows["key"]["share_term"], chi, f"{name}: слагаемое доли — χ_c")
        close(rows["key"]["n20"] - rows["record"]["n20"], want["n20_key_minus_record"], f"{name}: разность Н20.0")
        close(want["formula"], chi - rows["record"]["t2"] / line["rwa"], f"{name}: χ − T2 / RWA")
        for field in ("k11", "n11", "n11_star", "ded20", "ded11"):
            assert rows["key"][field] == rows["record"][field], (name, field)


def k2_value(t: dict, src: dict, rwa0: float, row: dict, lam, *, keyed: bool, q_chi: int) -> dict:
    """Синтетическая клетка K.2 — рабочей функцией оценки клетки (_c_value_cell) на контексте из входов примера: одна
    строка конца сетки (2028К4) — строка K.1 клетки B рабочей функцией счёта норматива; дата оценки — начало
    квартала, плата за капитал квартала из k_T. Блок постоянных частей — из контекста рабочей функцией: F_A, R_F,
    постоянные вычеты C_j и растущие части Dgrow_j / RWA_0 — входы примера. keyed: False — контекст без ключа (рублёвая
    запись; у строки ключа — «без поправки κ»: весь T2 конца сетки остаётся у бизнеса)."""
    k_q = (1.0 + t["k_t"]) ** (1.0 / cm.QY) - 1.0
    y, h = 2028, cm.QY
    book = {"valuation": {"terminal": {"excess_capital_multiple": t["multiple"], "fade": t["fade"],
                                       "real_growth": t["real_growth"]}},
            "worlds": {K_W: {"lt_inflation": t["lt_inflation"]}}, "pnl": {"nci_share": t["nci"]},
            "volumes": {"liquid_min_share": t["min_share"], "securities_share_of_liquid": 0.5},
            "tax": {"statutory": t["tau_stat"]},
            "capital": {"n20": {"gap_pp": row["gap20"]}, "n11": {"gap_pp": row["gap11"]},
                        "reg_scenarios": {K_S: {"deduction_pp": {"n20_0": row["dpp20"], "n1_1": row["dpp11"]}}}}}
    ded = {cm.NORM_TOTAL: {"share": None, "fix": src["c20"], "grow": src["dgrow20_over_rwa0"] * rwa0},
           cm.NORM_BASE: {"share": None, "fix": src["c11"], "grow": src["dgrow11_over_rwa0"] * rwa0}}
    ctx = {"B": book, "A": {"BV": t["bv_q"], "cpn_quarter": 1, "cpn_annual": t["coupon"]},
           "clock": {"p0": 0, "pos": 0.0, "t_start": {0: 0.0}, "tau_end": {0: 1.0 / cm.QY}},
           "periods": [{"year": y, "quarters": [h], "n": 1}],
           "disc": {K_W: lambda tau: (1.0 + k_q) ** (-cm.QY * tau)}, "recap": None, "lam_f": lam,
           "oaf": src["f_a"], "dens_oaf": src["r_f"] / src["f_a"], "oaf_path": None, "rwa_mult": {}, "ded": ded,
           "rub": None, "rwa0": rwa0, "anchor": (2027, cm.QY), "t2_from": q_chi if keyed else None}
    assets = 1000.0                       # балансирующие активы: запас над минимумом m × активы — вход примера
    liquid = t["headroom"] + t["min_share"] * assets
    last = {"ci_q": [0.0], "ci": 0.0, "div_list": [], "rec_list": [], "bv": t["bv_q"], "n20": row["n20"],
            "n11_star": row["n11_star"], "dpreg": 0.0, "rwa": row["rwa"], "req20": row["req20"], "req11": row["req11"],
            "securities": liquid / 2.0, "liquidity": liquid / 2.0, "assets": assets, "wholesale_extra": t["wt"],
            "y_sec_end": t["y_bal"], "y_liq_end": t["y_bal"], "c_wh_end": t["c_wh"], "pbt": t["pbt_l"],
            "tau_eff": t["tau"], "dn_q": [1.0], "xf_q": [1.0], "t2s": row.get("t2s")}
    return cm._c_value_cell(ctx, {"world": K_W, "regime": K_R, "scenario": K_S}, [last], {})


@pytest.mark.tact
def test_appendix_k2_terminal():
    """K.2: слагаемые X_T клетки B конца сетки — 8,7 и 30,75 с ключом (связывает Н20.0), 6,3 в рублёвой записи; κ_20
    блока — 0,161 без ключа и 0,153 с ключом (на χ_B меньше), κ_11 = 0,1425 в обоих; терминал при λ_F = 1 и 0 с ключом,
    без поправки κ и в рублёвой записи рабочей функцией оценки клетки; при λ_F = 1 поправка κ ничего не меняет (блок не
    читается); за T бизнес при λ_F = 0 держит требование на своих RWA с инструментами ровно χ_B × (RWA − R_F), а без
    поправки κ — все инструменты конца сетки (доля 0,8660 %)."""
    doc = example()
    share, term = doc["share"], doc["terminal"]
    inp, t, src = share["inputs"], term["inputs"]["terminal"], term["inputs"]["block_source"]
    on, off = k_specs(inp)
    keyed, record = k_ctx(k_book(inp, spec=on), inp), k_ctx(k_book(inp, spec=off), inp)
    at = cm.c_per_parse(inp["periods"][-1])
    line = inp["quarter_Q"]["B"]
    chi = k_chi(keyed, inp, inp["rwa"]["B"])
    close(chi, term["inputs"]["chi"], "χ_B")
    extra = {"gap20": inp["capital"]["gap20"], "gap11": inp["capital"]["gap11"], "dpp20": line["dpp20"],
             "dpp11": line["dpp11"]}
    rows = {"key": {**k_row(keyed, inp, line, at, chi), **extra, "t2s": chi},
            "record": {**k_row(record, inp, line, at, None), **extra}}
    assert (rows["key"]["req20"], rows["key"]["req11"]) == (t["req20"], t["req11"])
    rwa0 = inp["capital"]["rwa0"]
    cases = {"record": ("record", False), "key": ("key", True), "key_no_kappa": ("key", False)}
    got = {}
    for case, (which, keyed_ctx) in cases.items():
        for lam_key, want in term["cases"][case].items():
            lam = float(lam_key)
            out = k2_value(t, src, rwa0, rows[which], None if lam == 1.0 else lam, keyed=keyed_ctx, q_chi=inp["q_chi"])
            got[(case, lam)] = out
            what = f"{case} λ_F={lam_key}"
            excess = cm.c_terminal_excess(rows[which], t["multiple"])
            close(excess["x20"], want["x20"], f"{what}: x20")
            close(excess["x11"], want["x11"], f"{what}: x11")
            for mine, theirs in (("x_t", "x_t"), ("bv_star", "bv_star"), ("g_t", "g"), ("y_x", "y_x"), ("ci_t1", "ci"),
                                 ("roe_t_raw", "roe"), ("roe_t", "roe_faded"), ("tv_ri", "tv_ri"), ("tv_ddm", "tv_ddm")):
                close(out[mine], want[theirs], f"{what}: {theirs}")
            close(out["tv_ddm"] - out["x_t"], want["p_t"], f"{what}: P_T")
            if want["block"] is None:
                assert "terminal_fixed" not in out, what
                continue
            node = out["terminal_fixed"]
            close(node["business_capital"], want["business_capital"], f"{what}: B")
            close(node["business_ci"], want["business_ci"], f"{what}: CI_B")
            assert node["binding"] == want["block"]["binding"], what
            for field in ("c", "kappa", "f_a", "r_f", "f_k", "y_m", "d_f", "i_f"):
                close(node[field], want["block"][field], f"{what}: блок {field}")
            close(node["kappa_all"][cm.NORM_BASE], term["inputs"]["kappa11"], f"{what}: κ_11")
    # κ_20 блока: ключ — ровно на χ_B меньше; κ_11 прежний
    k_key = got[("key", 0.0)]["terminal_fixed"]["kappa_all"]
    k_old = got[("key_no_kappa", 0.0)]["terminal_fixed"]["kappa_all"]
    close(k_key[cm.NORM_TOTAL], term["inputs"]["kappa20_key"], "κ_20 с ключом")
    close(k_old[cm.NORM_TOTAL], term["inputs"]["kappa20_without_key"], "κ_20 без ключа")
    assert k_old[cm.NORM_TOTAL] - k_key[cm.NORM_TOTAL] == pytest.approx(chi, abs=EXACT)
    assert k_key[cm.NORM_BASE] == k_old[cm.NORM_BASE]
    diffs = term["tv_ddm_differences"]
    for lam in (1.0, 0.0):
        close(got[("key", lam)]["tv_ddm"] - got[("record", lam)]["tv_ddm"], diffs["key_vs_record"][str(int(lam))],
              f"ключ против записи рублями, λ_F={lam}")
        close(got[("key", lam)]["tv_ddm"] - got[("key_no_kappa", lam)]["tv_ddm"], diffs["kappa_correction"][str(int(lam))],
              f"поправка κ, λ_F={lam}")
    assert got[("key", 1.0)]["tv_ddm"] == got[("key_no_kappa", 1.0)]["tv_ddm"]       # λ_F = 1: блок не читается
    # кто держит инструменты за T при λ_F = 0 (w = 1): бизнес — на требовании своих RWA с долей клетки
    row, x_t = rows["key"], got[("key", 0.0)]["x_t"]
    for case, want in (("key", term["business_at_T"]), ("key_no_kappa", term["business_at_T_without_kappa_correction"])):
        node = got[(case, 0.0)]["terminal_fixed"]
        bus_rwa = row["rwa"] - node["r_f"]
        block_t2 = chi * node["r_f"] if case == "key" else 0.0
        bus_t2 = row["t2"] - block_t2
        bus_k20 = (row["k20"] - x_t) - (node["f_k"] - node["c"] - src["dgrow20_over_rwa0"] * node["r_f"]) - block_t2
        close(bus_rwa, want["rwa"], f"{case}: RWA бизнеса")
        close(bus_t2, want["t2"], f"{case}: инструменты бизнеса")
        close(bus_k20, want["k20"], f"{case}: K20 бизнеса")
        close(bus_k20 / bus_rwa + row["a20"], want["n20"], f"{case}: бизнес на требовании")
        if case == "key":
            close(block_t2, want["t2_block"], "инструменты стоящей доли")
            close(bus_t2 / bus_rwa, chi, "доля бизнеса — χ_B")
        else:
            close(bus_t2 / bus_rwa, want["t2_share"], "без поправки κ: доля бизнеса выше ключа")


@pytest.mark.tact
def test_appendix_k3_recap_carries_the_share():
    """K.3: ступень требования Н20.0 13 % — недостаток пробного прохода 54,3 = взнос (правило недостатка рабочей
    функцией); деньги взноса с весом 0,2 несут RWA + 10,86, вычет + 0,6516 и инструменты по доле + 0,08688: K20
    окончательного расчёта выше пробного на 53,73528, Н20.0 = 12,9058 % — ниже требования на
    w × (ρ_20 + Dgrow_20 / RWA_0 − χ_B) × Rec / RWA′ (без слагаемого доли — на 0,0983 п.п.)."""
    doc = example()
    inp, want = doc["share"]["inputs"], doc["recap"]
    on, _ = k_specs(inp)
    keyed = k_ctx(k_book(inp, spec=on), inp)
    at = cm.c_per_parse(inp["periods"][-1])
    line = inp["quarter_Q"]["B"]
    chi = k_chi(keyed, inp, inp["rwa"]["B"])
    trial = k_row(keyed, inp, line, at, chi)
    for field in ("rwa", "k20", "n20", "a20"):
        close(trial[field], want["inputs"]["trial"][field], f"пробный проход: {field}")
    req20 = want["inputs"]["req20"]
    point = {"q": inp["q_chi"] + 1, "n20": trial["n20"], "n11": trial["n11"], "dpreg": 0.0, "rwa": trial["rwa"],
             "req20": req20, "req11": trial["req11"]}
    made = cm.c_recap_shortfall([point], 0.0)
    close(made["rec"], want["rec"], "взнос — недостаток")
    assert made["norm"] == cm.NORM_TOTAL
    w = want["inputs"]["w_balancing"]
    d_rwa = w * made["rec"]
    close(d_rwa, want["d_rwa"], "прирост RWA")
    final = k_row(keyed, inp, line, at, chi, bv=line["bv"] + made["rec"], rwa=trial["rwa"] + d_rwa)
    close(final["ded20"] - trial["ded20"], want["d_ded20"], "прирост вычета")
    close(final["t2"] - trial["t2"], want["d_t2"], "инструменты по доле")
    close(final["t2"] - trial["t2"], chi * d_rwa, "χ_B × ΔRWA", EXACT)
    close(final["k20"] - trial["k20"], want["k20_final_minus_trial"], "K20: окончательный − пробный")
    close(final["k20"] - trial["k20"], made["rec"] - (final["ded20"] - trial["ded20"]) + chi * d_rwa,
          "свойство 3: Rec − ΔDed + χ_c × ΔRWA", EXACT)
    close(final["n20"], want["n20_final"], "Н20.0 окончательного расчёта")
    close(final["n20"] - req20, want["n20_final_minus_req"], "ниже требования")
    rho = req20 - inp["capital"]["gap20"] + line["dpp20"]
    grow = inp["capital"]["ded20_0"] / inp["capital"]["rwa0"]
    second = -w * (rho + grow - chi) * made["rec"] / final["rwa"]
    close(final["n20"] - req20, second, "второй порядок со слагаемым доли")
    close(-w * (rho + grow) * made["rec"] / final["rwa"], want["same_without_t2_share_term"], "без слагаемого доли")


@pytest.mark.tact
def test_appendix_k4_bridge():
    """K.4: мост Н20.0 клетки B от якоря до 2028К4 рабочей функцией строк моста: вычеты −66 (−3,2429 п.п. вместе с
    изменением аддитивного слагаемого), рост RWA −7,8571 п.п.; прочее контрольной модели — прибыль и изменение T2 одной
    суммой: 130 + 6,8 с ключом, 130 + 4,4 в рублёвой записи; тождество «начало + сумма долей = конец» в обеих."""
    doc = example()
    inp, br = doc["share"]["inputs"], doc["bridge"]
    on, off = k_specs(inp)
    anchor_line = {"rwa": br["inputs"]["anchor"]["rwa"], "bv": br["inputs"]["anchor"]["bvreg"], "dpreg": 0.0,
                   "reserve": 0.0, "e": 0.0}
    a0 = cm.c_per_parse(inp["periods"][0])
    at = cm.c_per_parse(inp["periods"][-1])
    line = inp["quarter_Q"]["B"]
    for which, spec in (("key", on), ("record", off)):
        ctx = k_ctx(k_book(inp, spec=spec), inp)
        chi = k_chi(ctx, inp, inp["rwa"]["B"]) if which == "key" else None
        first = k_row(ctx, inp, anchor_line, a0, None)
        last = k_row(ctx, inp, line, at, chi)
        close(first["k20"], br["inputs"]["k20_0"], f"{which}: K20 якоря")
        close(first["t2"], br["inputs"]["anchor"]["t2"], f"{which}: T2 якоря — траектория")
        got = cm.c_bridge_lines([(1.0, first, last)])
        want = br["by_record"][which]
        close(got["start"], want["start"], f"{which}: начало")
        close(got["end"], want["end"], f"{which}: конец")
        close(got["deductions"]["amount"], want["deductions_amount"], f"{which}: вычеты")
        close(got["deductions"]["pp"], want["deductions_pp"], f"{which}: вычеты, п.п.")
        close(got["rwa_growth"]["pp"], want["rwa_growth_pp"], f"{which}: рост RWA")
        close(got["rest"]["amount"], want["profit_amount"] + want["other_amount"], f"{which}: прочее с прибылью")
        close(got["rest"]["pp"], want["profit_pp"] + want["other_pp"], f"{which}: прочее с прибылью, п.п.")
        close(last["t2"] - first["t2"], want["other_amount"], f"{which}: изменение T2")
        close(got["start"] + got["deductions"]["pp"] + got["rwa_growth"]["pp"] + got["rest"]["pp"], got["end"],
              f"{which}: тождество", EXACT)


@pytest.mark.tact
def test_appendix_k6_axis_shift_moves_the_share():
    """K.6: сдвиг траектории на +3 — доля клетки B 15 / 1500 = 1 %, T2 клетки 13; 13; 15; 18; 21; Н20.0 конца сетки выше
    на 3 / 1500 = 0,2 п.п. с ключом и на 3 / 2100 в рублёвой записи (свойство 18: Δχ = Δ / RWA_c,(q_χ − 1))."""
    doc = example()
    inp, ax = doc["share"]["inputs"], doc["axis"]
    on, off = k_specs(inp)
    moved = [v + ax["delta"] for v in inp["trajectory"]]
    rwa = inp["rwa"]["B"]
    at = cm.c_per_parse(inp["periods"][-1])
    line = inp["quarter_Q"]["B"]
    shift = {}
    for which, spec in (("key", on), ("record", off)):
        base, ctx = k_ctx(k_book(inp, spec=spec), inp), k_ctx(k_book(inp, spec=spec, traj=moved), inp)
        chi0 = k_chi(base, inp, rwa) if which == "key" else None
        chi = k_chi(ctx, inp, rwa) if which == "key" else None
        path = [cm.c_t2_at(ctx, *cm.c_per_parse(p), rwa[k], chi) for k, p in enumerate(inp["periods"])]
        for k, value in enumerate(ax[f"t2_{which}"]):
            close(path[k], value, f"{which}: T2 {inp['periods'][k]}")
        if which == "key":
            close(chi, ax["chi"], "доля после сдвига")
            close(chi - chi0, ax["share_shift"], "сдвиг доли")
            close(chi - chi0, ax["delta"] / rwa[inp["q_chi"] - 1], "Δ / RWA_c,(q_χ − 1)")
        shift[which] = k_row(ctx, inp, line, at, chi)["n20"] - k_row(base, inp, line, at, chi0)["n20"]
    close(shift["key"], ax["n20_shift_Q_key"], "Н20.0 конца сетки с ключом")
    close(shift["record"], ax["n20_shift_Q_record"], "Н20.0 конца сетки рублями")


@pytest.mark.tact
def test_appendix_k7_schema_cases():
    """K.7 (прил. A № 30): правило ключа рабочей функцией на одиннадцати случаях таблицы — годен или отказ, точно;
    from = first_period — доля якоря 10 / 1000 = 1 % у всех клеток (состояние якоря)."""
    doc = example()
    inp = doc["share"]["inputs"]
    for case in doc["schema"]:
        book = k_book(inp, spec=case["spec"])
        book["meta"] = {"anchor_period": case["anchor"], "first_period": case["first_period"],
                        "last_period": case["last_period"]}
        anchor = cm.c_per_parse(case["anchor"])
        if case["result"].startswith("годен"):
            q_chi = cm.c_t2_share_rule(book, anchor)
            spec = case["spec"]
            assert (q_chi is None) == (spec is None or not spec["enabled"]), case
            if q_chi is not None:
                assert q_chi == cm.c_qidx(anchor, *cm.c_per_parse(spec["from"])), case
        else:
            with pytest.raises(cm.ControlInputError, match="t2_share"):
                cm.c_t2_share_rule(book, anchor)
    first = k_book(inp, spec={"enabled": True, "from": inp["periods"][1]})
    ctx = k_ctx(first, inp)
    assert ctx["t2_from"] == 1
    close(cm.c_t2_start_share(ctx), inp["trajectory"][0] / inp["capital"]["rwa0"], "доля якоря")
    # сверх таблицы: null у ключа и у полей, лишнее поле, from не строкой — отказ
    for bad in (None, {"enabled": None, "from": "2028Q3"}, {"enabled": True, "from": None},
                {"enabled": True, "from": "2028Q3", "until": "2028Q4"}, {"enabled": True, "from": 20283},
                {"enabled": True, "from": "2028q3"}, {"enabled": True, "from": "2028Q5"}, ["2028Q3"], True,
                {"enabled": 1, "from": "2028Q3"}):
        with pytest.raises(cm.ControlInputError, match="t2_share"):
            cm.c_t2_share_rule(put(k_book(inp), "capital.n20.t2_share", bad), (2027, cm.QY))


@pytest.mark.tact
def test_share_step_of_the_annual_branch():
    """Доля, которую задаёт годовой шаг (М§4.11, §17): квартал q_χ − 1 в конце периода — RWA конца периода; внутри
    периода — квартальный профиль RWA (геометрически между началом и концом); у ветви с квартальным проходом — доля
    прохода из плана года; доля состояния сильнее; шаг, который кончается раньше q_χ − 1, долю не задаёт."""
    inp = example()["share"]["inputs"]
    book = k_book(inp, spec={"enabled": True, "from": "2028Q3"})
    ctx = k_ctx(book, inp)
    p = {"year": 2028, "quarters": (1, 2, 3, 4), "n": 4}
    st = {"rwa": 1000.0}
    mid = cm.c_t2_share_step(ctx, st, p, 2100.0)
    close(mid, 12.0 / (1000.0 * 2.1 ** 0.5), "внутри года — профиль RWA")
    assert cm.c_t2_share_step(ctx, st, p, 2100.0, {"t2s": 0.0123}) == 0.0123
    assert cm.c_t2_share_step(ctx, {**st, "t2s": 0.02}, p, 2100.0, {"t2s": 0.0123}) == 0.02
    end = k_ctx(k_book(inp, spec={"enabled": True, "from": "2028Q4"}), inp)        # q_χ − 1 = 2028К3
    p_end = {"year": 2028, "quarters": (1, 2, 3), "n": 3}
    assert cm.c_t2_share_step(end, st, p_end, 1800.0) == 13.2 / 1800.0
    assert cm.c_t2_share_step(ctx, st, {"year": 2027, "quarters": (4,), "n": 1}, 1000.0) is None
    assert cm.c_t2_share_step(k_ctx(k_book(inp), inp), st, p, 2100.0) is None


# ============================================================================ свойства на форме образца (годовая ветвь)


@pytest.fixture(scope="module")
def inputs():
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8")), cm.c_facts_bundle(FIXTURE / "facts")


@pytest.fixture(scope="module")
def plain(inputs):
    return cm.c_control_run(*inputs)


@pytest.fixture(scope="module")
def keyed(inputs):
    """Ключ с 2029К1: квартал перед ключом — конец года (как у книги 0.5)."""
    book, facts = inputs
    return cm.c_control_run(with_share(book, KEY_YEAR_END), facts)


@pytest.fixture(scope="module")
def keyed_mid(inputs):
    """Ключ с 2028К3: квартал перед ключом внутри года решения о дивиденде, точки проверки 3 и 4 — после ключа."""
    book, facts = inputs
    return cm.c_control_run(with_share(book, KEY_MID), facts)


def t2_traj(ctx: dict, y: int, h: int) -> float:
    return cm.c_traj_at(cm.c_bget(ctx["B"], cm.T2_TRAJ), y, h)


def set_share(ctx: dict, rows: list) -> float:
    """Доля клетки, пересчитанная тестом по рядам клетки: значение траектории в q_χ − 1 к RWA клетки на его конце —
    у конца года RWA строки, внутри года — геометрический путь RWA между концами соседних строк."""
    q_set = ctx["t2_from"] - 1
    y, h = cm.c_qper(ctx["anchor"], q_set)
    for i, p in enumerate(ctx["periods"]):
        if p["year"] != y:
            continue
        start = ctx["rwa0"] if i == 0 else rows[i - 1]["rwa"]
        j = list(p["quarters"]).index(h)
        rwa = rows[i]["rwa"] if j == p["n"] - 1 else start * (rows[i]["rwa"] / start) ** ((j + 1) / p["n"])
        return t2_traj(ctx, y, h) / rwa
    raise AssertionError("квартал перед ключом вне сетки")


@pytest.mark.tact
def test_off_and_absent_key_are_the_sample_branch(inputs, plain):
    """Без ключа и при enabled: false (с from и без него) — ряды, оценка и точка формы образца бит в бит; узла доли и
    поля доли в строках нет; ряд T2 — траектория в каждой строке."""
    book, facts = inputs
    assert plain["ctx"]["t2_from"] is None and "t2_share" not in plain
    for spec in (OFF, {"enabled": False}):
        same = cm.c_control_run(with_share(book, spec), facts)
        assert same["ctx"]["t2_from"] is None and "t2_share" not in same
        assert values_of(same) == values_of(plain)
        assert rows_of(same, ("t2", "k20", "n20")) == rows_of(plain, ("t2", "k20", "n20"))
        assert [c["anchor_capital"] for c in same["cells"]] == [c["anchor_capital"] for c in plain["cells"]]
    ctx = plain["ctx"]
    for c in plain["cells"]:
        assert all("t2s" not in r for r in c["rows"])
        for p, r in zip(ctx["periods"], c["rows"]):
            assert r["t2"] == t2_traj(ctx, p["year"], p["quarters"][-1])


@pytest.mark.tact
def test_bad_share_keys_fail_loudly(inputs):
    """Ограничение № 30 приложения A на форме образца: не объект или лишнее поле, enabled не булево (и нет enabled),
    enabled: true без from, from не квартал ГГГГQn или вне first_period…last_period (и при enabled: false), null — отказ
    книги; годные формы — считаются."""
    book, facts = inputs
    for bad in (None, True, "2029Q1", ["2029Q1"], {"enabled": True}, {"from": "2029Q1"},
                {"enabled": "yes", "from": "2029Q1"}, {"enabled": None, "from": "2029Q1"},
                {"enabled": True, "from": "2026Q2"}, {"enabled": True, "from": "2037Q1"},
                {"enabled": False, "from": "2026Q2"}, {"enabled": False, "from": "2029-1"},
                {"enabled": True, "from": None}, {"enabled": True, "from": "2029Q1", "extra": 1}):
        with pytest.raises(cm.ControlInputError, match="t2_share"):
            cm.c_control_context(with_share(book, bad), facts)
    # под выключенным выключателем null у from — «нераскрыто» (М§0.1), как у любого ключа под выключателем
    for good, q_chi in ((KEY_FIRST, 1), ({"enabled": True, "from": "2036Q4"}, 42), (KEY_YEAR_END, 11),
                        (OFF, None), ({"enabled": False}, None), ({"enabled": False, "from": None}, None)):
        assert cm.c_control_context(with_share(book, good), facts)["t2_from"] == q_chi


@pytest.mark.tact
def test_share_rows_follow_the_formula(keyed, keyed_mid, plain):
    """Свойства 13–14 (М§4.11) своим счётом: доля клетки — значение траектории в q_χ − 1 к RWA клетки на его конце (у
    ключа с 2029К1 — RWA конца 2028 года, у ключа с 2028К3 — квартальный профиль RWA 2028 года), своя у клеток разных
    миров и режимов; в строках конца года с q_χ ряд T2 — доля на RWA строки, раньше — траектория; K20 и K11,
    пересчитанные тестом по рядам клетки, совпадают с её рядами (K11 — без T2); слагаемое доли
    N20 − (K20 − T2) / RWA − A_20 — χ_c во всех строках с q_χ; строка якоря от ключа не зависит."""
    for res in (keyed, keyed_mid):
        ctx = res["ctx"]
        B, q_chi = ctx["B"], ctx["t2_from"]
        f = cm.c_bnum(B, "capital.n20.fvoci_recognition")
        assert res["t2_share"]["q_chi"] == q_chi
        shares = set()
        for c, p0 in zip(res["cells"], plain["cells"]):
            assert c["anchor_capital"] == p0["anchor_capital"]
            rows = c["rows"]
            chi = rows[-1]["t2s"]
            assert chi == pytest.approx(set_share(ctx, rows), rel=EXACT), key(c)
            shares.add(chi)
            for period, r in zip(ctx["periods"], rows):
                y, h = period["year"], period["quarters"][-1]
                k_end = cm.c_qidx(ctx["anchor"], y, h)
                if k_end >= q_chi:
                    assert r["t2s"] == chi and r["t2"] == chi * r["rwa"], (key(c), y)
                    a20 = cm.c_bnum(B, "capital.n20.gap_pp") - cm.c_traj_at(cm.c_bget(
                        B, f"capital.reg_scenarios.{c['scenario']}.deduction_pp.n20_0"), y, h)
                    assert r["n20"] - (r["k20"] - r["t2"]) / r["rwa"] - a20 == pytest.approx(chi, abs=EXACT)
                else:
                    # до квартала ключа — траектория; доля строки — та, что задал шаг (у года квартала q_χ − 1 — его)
                    assert r["t2"] == t2_traj(ctx, y, h), (key(c), y)
                    assert r["t2s"] == (chi if k_end >= q_chi - 1 else None), (key(c), y)
                own = r["bv"] + r["dpreg"] - (1.0 - f) * r["R"]
                assert r["k20"] == pytest.approx(own - r["ded20"] + ctx["A"]["AT1"] + r["t2"], rel=EXACT)
                assert r["k11"] == pytest.approx(own - max(r["e_unaudited"], 0.0) - r["ded11"], rel=EXACT)
        assert len(shares) > len(ctx["worlds"]), "у клеток разных миров и режимов — свои доли"
        node = res["t2_share"]
        assert node["share_min"] == min(shares) and node["share_max"] == max(shares)
        mass = cm.c_point_mass(res)
        assert node["share_point"] == pytest.approx(sum(mass[key(c)] * c["rows"][-1]["t2s"] for c in res["cells"]),
                                                    rel=EXACT)


@pytest.mark.tact
def test_trial_step_of_the_dividend_sets_the_share_with_its_own_rwa(keyed_mid):
    """Пробный проход дивиденда идёт через квартал q_χ − 1 (2028К2; собрание — во втором квартале, точки проверки 3 и 4
    — после ключа): он задаёт долю своими RWA (без дивиденда этого года), и запас решения в точках проверки — с этой
    долей на RWA точки; окончательный шаг задаёт долю своими RWA (с дивидендом) — другую."""
    res = keyed_mid
    ctx = res["ctx"]
    y_set, h_set = cm.c_qper(ctx["anchor"], ctx["t2_from"] - 1)
    i = next(i for i, p in enumerate(ctx["periods"]) if p["year"] == y_set)
    p = ctx["periods"][i]
    seen = 0
    for c in res["cells"][:6]:
        ident = {"world": c["world"], "regime": c["regime"], "scenario": c["scenario"]}
        st = cm._c_start_state(ctx)
        st["rwa"] = ctx["rwa0"]
        for k in range(i):
            st, row = cm._c_period(ctx, ident, st, k, c["rows"][k]["div"])
            st["rwa"] = row["rwa"]
        assert st.get("t2s") is None
        trial = cm._c_period(ctx, ident, st, i, 0.0)[1]
        j = list(p["quarters"]).index(h_set)
        rwa_set = st["rwa"] * (trial["rwa"] / st["rwa"]) ** ((j + 1) / p["n"])
        assert trial["t2s"] == pytest.approx(t2_traj(ctx, y_set, h_set) / rwa_set, rel=EXACT)
        decision = c["decisions"].get(y_set - 1)
        if decision is None or decision.get("kind") != "policy" or c["rows"][i]["div"] == 0.0:
            continue
        assert trial["t2s"] != c["rows"][i]["t2s"]        # окончательный шаг (с дивидендом) — своими RWA
        buf20 = cm.c_bnum(ctx["B"], "capital.mgmt_buffer.n20_0")
        threshold = cm.c_bnum(ctx["B"], "dividends.policy.threshold")
        H = float("inf")
        for h in [int(x) for x in cm.c_bget(ctx["B"], "dividends.calendar.checkpoints")]:
            jj = list(p["quarters"]).index(h)
            rwa_h = st["rwa"] * (trial["rwa"] / st["rwa"]) ** ((jj + 1) / p["n"])
            bv_h = st["BV"] + sum(trial["ci_q"][:jj + 1])
            cap = cm._c_capital(ctx, c["scenario"], p["year"], h, bv_h, 0.0, trial["R_q"][jj], rwa_h,
                                {**st["ni_q"], **trial["ni_q"]}, trial["t2s"])
            assert cap["t2"] == trial["t2s"] * rwa_h
            H = min(H, (cap["n20"] - max(threshold, cap["floor20"] + buf20)) * rwa_h, (cap["n11"] - cap["req11"]) * rwa_h)
        assert decision["H"] == pytest.approx(H, rel=1e-12, abs=1e-9), key(c)
        seen += 1
    assert seen, "вход теста: решения модели в году квартала перед ключом"


@pytest.mark.tact
def test_first_period_key_gives_the_anchor_share_to_all_cells(inputs, plain):
    """Контрольный случай (М§17, свойство 17): from = first_period — доля якоря T2_0 / RWA_0, одна у всех клеток, во всех
    строках; строка якоря та же, что без ключа."""
    book, facts = inputs
    res = cm.c_control_run(with_share(book, KEY_FIRST), facts)
    ctx = res["ctx"]
    assert ctx["t2_from"] == 1
    anchor_share = t2_traj(ctx, *ctx["anchor"]) / ctx["rwa0"]
    assert res["t2_share"]["anchor_share"] == anchor_share
    for c, p0 in zip(res["cells"], plain["cells"]):
        assert c["anchor_capital"] == p0["anchor_capital"]
        assert {r["t2s"] for r in c["rows"]} == {anchor_share}
        assert all(r["t2"] == anchor_share * r["rwa"] for r in c["rows"])
    assert res["t2_share"]["share_min"] == res["t2_share"]["share_max"] == anchor_share


# вне такта сервера: свойство проверяется лишними прогонами сетки формы образца — они идут в CI
def test_share_adds_exactly_its_term_where_capital_ignores_the_ratios(inputs):
    """Свойство 15: на книге без выплаты путь капитала от нормативов не зависит — RWA, K11, Н20.1 и Н20.1 с прибылью
    периода бит в бит книги без ключа, K20 больше ровно на χ_c × RWA − T2, избыток терминала —
    множитель × min(x20 + χ_c × RWA_Q − T2_Q, x11)."""
    book, facts = inputs
    still = with_keys(book, NO_PAYOUT)
    bare = cm.c_control_run(still, facts)
    mult = cm.c_bnum(bare["ctx"]["B"], "valuation.terminal.excess_capital_multiple")
    for spec in (KEY_YEAR_END, KEY_MID):
        res = cm.c_control_run(with_share(still, spec), facts)
        ctx = res["ctx"]
        moved = 0.0
        for a, b in zip(bare["cells"], res["cells"]):
            chi = b["rows"][-1]["t2s"]
            for period, ra, rb in zip(ctx["periods"], a["rows"], b["rows"]):
                assert (ra["bv"], ra["rwa"], ra["div"], ra["k11"], ra["n11"], ra["n11_star"]) == (
                    rb["bv"], rb["rwa"], rb["div"], rb["k11"], rb["n11"], rb["n11_star"])
                k_end = cm.c_qidx(ctx["anchor"], period["year"], period["quarters"][-1])
                add = chi * rb["rwa"] - ra["t2"] if k_end >= ctx["t2_from"] else 0.0
                assert rb["k20"] - ra["k20"] == pytest.approx(add, abs=1e-9)
                moved = max(moved, abs(add))
            base = cm.c_terminal_excess(a["rows"][-1], mult)
            last = a["rows"][-1]
            x20 = base["x20"] + chi * last["rwa"] - last["t2"]
            assert b["x_t"] == pytest.approx(mult * min(x20, base["x11"]), rel=1e-9, abs=1e-9), key(a)
        assert moved > 1.0, "вход теста: доля и траектория расходятся"


@pytest.mark.tact
def test_kappa_of_the_fixed_block_is_lower_by_the_share(inputs):
    """Свойство 19: у книги с постоянными частями и λ_F = 0 κ_20 блока меньше, чем по формуле без ключа на той же
    строке, ровно на χ_c, κ_11 прежний; при связывающем на T Н20.1 блок от ключа не зависит; DDM = RI в каждой клетке."""
    book, facts = inputs
    res = cm.c_control_run(with_share(with_keys(book, FIXED_LAM0), KEY_YEAR_END), facts)
    ctx = res["ctx"]
    bare_ctx = {**ctx, "t2_from": None}
    for c in res["cells"]:
        last = c["rows"][-1]
        excess = cm.c_terminal_excess(last, cm.c_bnum(ctx["B"], "valuation.terminal.excess_capital_multiple"))
        mine = cm.c_terminal_fixed_inputs(ctx, c, last, excess)
        old = cm.c_terminal_fixed_inputs(bare_ctx, c, last, excess)
        assert old["kappa"][cm.NORM_TOTAL] - mine["kappa"][cm.NORM_TOTAL] == pytest.approx(last["t2s"], abs=EXACT)
        assert mine["kappa"][cm.NORM_BASE] == old["kappa"][cm.NORM_BASE]
        node = c["terminal_fixed"]
        assert node["kappa_all"] == mine["kappa"]
        if node["binding"] == cm.NORM_BASE:
            assert node["f_k"] == old["c"][cm.NORM_BASE] + old["kappa"][cm.NORM_BASE] * old["r_f"]
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"])), key(c)
    assert any(c["terminal_fixed"]["binding"] == cm.NORM_TOTAL for c in res["cells"])


def modal_trajectory(res: dict) -> dict:
    """Траектория, записанная поквартально по RWA модальной клетки прогона с ключом: ключ квартала якоря и ключи лет до
    квартала ключа — значения прежней траектории; кварталы с q_χ — χ_мод × RWA клетки (концы лет — RWA строки,
    кварталы внутри года — квартальный профиль RWA годовой ветви)."""
    ctx = res["ctx"]
    modal = cm.c_cell_of(res, *res["central"]["cell"])
    chi = modal["rows"][-1]["t2s"]
    traj = {f"{ctx['anchor'][0]}Q{ctx['anchor'][1]}": t2_traj(ctx, *ctx["anchor"])}
    for i, p in enumerate(ctx["periods"]):
        start = ctx["rwa0"] if i == 0 else modal["rows"][i - 1]["rwa"]
        end = modal["rows"][i]["rwa"]
        for j, h in enumerate(p["quarters"]):
            if cm.c_qidx(ctx["anchor"], p["year"], h) < ctx["t2_from"]:
                traj[str(p["year"])] = t2_traj(ctx, p["year"], h)
                continue
            rwa = end if j == p["n"] - 1 else start * (end / start) ** ((j + 1) / p["n"])
            traj[f"{p['year']}Q{h}"] = chi * rwa
    return traj


# вне такта сервера: свойство проверяется лишними прогонами сетки формы образца — они идут в CI
def test_trajectory_written_on_the_modal_cell_gives_its_ratios(inputs, keyed):
    """Контрольный случай (М§17, свойство 16): книга без ключа с траекторией, записанной поквартально по RWA модальной
    клетки книги с ключом. На книге без выплаты (путь капитала от нормативов не зависит) нормативы модальной клетки — те
    же, что с ключом (1e-12), а в любой клетке Н20.0 книги с ключом выше записи рублями ровно на χ_c − T2_q / RWA_c,q
    (ниже — где RWA клетки растут медленнее модальной). На книге с выплатой модальная клетка совпадает до тысячных
    долей п.п.: пробный проход дивиденда несёт RWA без дивиденда года, а запись рублями — RWA окончательного шага."""
    book, facts = inputs
    still = with_keys(book, NO_PAYOUT)
    on = cm.c_control_run(with_share(still, KEY_YEAR_END), facts)
    written = cm.c_control_run(put(still, cm.T2_TRAJ, modal_trajectory(on)), facts)
    ctx = on["ctx"]
    signs = set()
    for a, b in zip(on["cells"], written["cells"]):
        chi = a["rows"][-1]["t2s"]
        for period, ra, rb in zip(ctx["periods"], a["rows"], b["rows"]):
            assert ra["rwa"] == rb["rwa"] and ra["k11"] == rb["k11"]
            if cm.c_qidx(ctx["anchor"], period["year"], period["quarters"][-1]) < ctx["t2_from"]:
                assert ra["n20"] == rb["n20"]
                continue
            gap = chi - rb["t2"] / rb["rwa"]
            assert ra["n20"] - rb["n20"] == pytest.approx(gap, abs=EXACT), key(a)
            if key(a) == tuple(on["central"]["cell"]):
                assert abs(ra["n20"] - rb["n20"]) <= EXACT
            elif abs(gap) > 1e-6:
                signs.add(gap > 0.0)
    assert signs == {True, False}, "вход теста: клетки с более быстрым и более медленным ростом RWA"
    # книга с выплатой: модальная клетка — до тысячных долей п.п. (допуск Н20.0 сверки — 0,3 п.п.)
    paid = cm.c_control_run(put(book, cm.T2_TRAJ, modal_trajectory(keyed)), facts)
    modal, same = (cm.c_cell_of(r, *keyed["central"]["cell"]) for r in (keyed, paid))
    gap = max(abs(a["n20"] - b["n20"]) for a, b in zip(modal["rows"], same["rows"]))
    assert gap <= 1e-4, gap
    assert same["v_ri"] == pytest.approx(modal["v_ri"], rel=1e-4)
    # вне модальной клетки запись рублями даёт другие нормативы и стоимость (норматив, который связывает, выплата
    # возвращает к требованию — разность стоит в дивиденде и в оценке)
    other = max(abs(a["rows"][-1]["n20"] - b["rows"][-1]["n20"]) for a, b in zip(keyed["cells"], paid["cells"]))
    worth = max(abs(a["v_ri"] / b["v_ri"] - 1.0) for a, b in zip(keyed["cells"], paid["cells"]))
    assert other > 10 * gap and worth > 1e-3, (other, worth)


# вне такта сервера: прогоны формы с нехваткой капитала — они идут в CI
def test_recap_money_carries_the_share(inputs):
    """Взнос у книги с ключом (М§4.14.1, §4.14.5, свойство 3): в году решения после квартала ключа K20 окончательного
    шага выше, чем у того же шага без взноса, на прирост собственных средств за вычетом прироста вычета плюс
    χ_c × (RWA′ − RWA); K11 — без слагаемого доли; остаток недостатка после взноса — в допуске инварианта."""
    book, facts = inputs
    res = cm.c_control_run(with_share(with_keys(book, SHORT_Q4), {"enabled": True, "from": "2027Q1"}), facts)
    ctx = res["ctx"]
    y_set = cm.c_qper(ctx["anchor"], ctx["t2_from"] - 1)[0]
    keep = 1.0 - cm.c_bnum(ctx["B"], "capital.n20.fvoci_recognition")
    seen = 0
    for cell in res["cells"]:
        for year, made in cell["recaps"].items():
            if made["rec"] > 0.0:
                assert made["left"]["left"] <= LEFT_SHARE * made["rec"], (key(cell), year)
        # решение называется годом Y = год квартала решения − 1: год решения — после года квартала перед ключом
        done = [y for y, x in sorted(cell["recaps"].items()) if x["rec"] > 0.0 and y + 1 > y_set]
        if not done:
            continue
        year = done[0]
        made = cell["recaps"][year]
        ident = {"world": cell["world"], "regime": cell["regime"], "scenario": cell["scenario"]}
        st = cm._c_start_state(ctx)
        st["rwa"] = ctx["rwa0"]
        for i, p in enumerate(ctx["periods"]):
            if p["year"] == year + 1:
                break
            st, row = cm._c_period(ctx, ident, st, i, cell["rows"][i]["div"], rec=cell["rows"][i]["rec"])
            st["rwa"] = row["rwa"]
        assert st["t2s"] is not None                 # доля задана концом года якоря — до года решения
        without = cm._c_period(ctx, ident, st, i, made["div"])[1]
        with_it = cm._c_period(ctx, ident, st, i, made["div"], rec=made["rec"])[1]
        assert with_it["t2s"] == without["t2s"] == st["t2s"]
        more_own = ((with_it["bv"] + with_it["dpreg"] - keep * with_it["R"])
                    - (without["bv"] + without["dpreg"] - keep * without["R"]))
        more_ded = with_it["ded20"] - without["ded20"]
        d_rwa = with_it["rwa"] - without["rwa"]
        assert d_rwa > 0.0
        assert with_it["k20"] - without["k20"] == pytest.approx(more_own - more_ded + st["t2s"] * d_rwa, rel=1e-9,
                                                                abs=1e-9)
        held = max(with_it["e_unaudited"], 0.0) - max(without["e_unaudited"], 0.0)
        assert with_it["k11"] - without["k11"] + held == pytest.approx(
            more_own - (with_it["ded11"] - without["ded11"]), rel=1e-9, abs=1e-9)
        seen += 1
    assert seen


# ============================================================================ квартальный проход (форма панели)


@pytest.fixture(scope="module")
def quarterly():
    book = json.loads((FIXTURE_T / "book.json").read_text(encoding="utf-8"))
    facts = cm.c_facts_bundle(FIXTURE_T / "facts")
    return book, facts, cm.c_control_run(with_share(book, KEY_T), facts)


# вне такта сервера: сетка формы панели с квартальным проходом — секунды
def test_quarterly_pass_holds_the_share_of_the_recorded_step(quarterly):
    """Квартальный проход (форма панели): доля клетки — значение траектории в 2027К3 к RWA записанного шага этого
    квартала (с долей прироста λ, дивидендами и множителем плотности режима), и там, где рост урезан, — а не к RWA
    оценки «только нормативы»; в каждом квартале с q_χ ряд T2 — доля на RWA квартала, раньше — траектория; проход
    кончает год на тех же капитале, RWA и нормативе, что годовая строка; норматив связывающего при урезанном росте — на
    требовании с глиссадой в допуске tol."""
    book, facts, res = quarterly
    ctx = res["ctx"]
    q_chi = ctx["t2_from"]
    y_set, h_set = cm.c_qper(ctx["anchor"], q_chi - 1)
    rule = res["growth_rule"]
    tol = rule["tol"]
    cut_cells = 0
    for c in res["cells"]:
        chi = c["rows"][-1]["t2s"]
        xs = [x for r in c["rows"] for x in r["quarters"]]
        before = next(x for x in xs if x["q"] == q_chi - 1)
        assert chi == t2_traj(ctx, y_set, h_set) / before["rwa"], key(c)
        if rule["lam_min"] < before["lam"] < 1.0:
            # записанный шаг — урезанный рост: связывающий норматив на требовании с глиссадой (не оценка λ = 1)
            cut_cells += 1
            gaps = (before["n20"] - before["req20_glide"], before["n11_star"] - before["req11_glide"])
            assert min(gaps) >= -tol and min(abs(g) for g in gaps) <= tol, key(c)
        for x in xs:
            y, h = cm.c_qper(ctx["anchor"], x["q"])
            if x["q"] >= q_chi:
                assert x["t2"] == chi * x["rwa"], (key(c), x["q"])
            else:
                assert x["t2"] == t2_traj(ctx, y, h), (key(c), x["q"])
        for r in c["rows"]:
            last = r["quarters"][-1]
            assert last["rwa"] == pytest.approx(r["rwa"], rel=1e-8)
            assert abs(last["n20"] - r["n20"]) <= 1e-8 and abs(last["n11"] - r["n11"]) <= 1e-8
            if r.get("t2s") is not None:
                assert r["t2s"] == pytest.approx(chi, rel=1e-8) and r["t2"] == r["t2s"] * r["rwa"]
    assert cut_cells, "вход теста: рост урезан в квартале перед ключом"


# вне такта сервера: две сетки формы панели
def test_quarterly_off_key_is_the_sample_branch(quarterly):
    """Квартальный проход: enabled: false — ряды кварталов, оценка и точка формы панели бит в бит книги без ключа."""
    book, facts, _ = quarterly
    bare = cm.c_control_run(book, facts)
    off = cm.c_control_run(with_share(book, OFF), facts)
    assert values_of(off) == values_of(bare)
    assert [[x["n20"] for r in c["rows"] for x in r["quarters"]] for c in off["cells"]] == [
        [x["n20"] for r in c["rows"] for x in r["quarters"]] for c in bare["cells"]]


# ============================================================================ сверка с ядром (в момент теста)


TRAJ_STEPS = {"2026Q2": 500.3, "2027": 520.0, "2028": 560.0, "2029": 600.0, "2031": 680.0, "LT": 700.0, "LT_from": 2034}
FORMS = {"key-2029Q1": lambda book: with_share(book, KEY_YEAR_END),
         "key-2028Q3": lambda book: with_share(book, KEY_MID),
         "key-first": lambda book: with_share(book, KEY_FIRST),
         "key-last-quarter": lambda book: with_share(book, {"enabled": True, "from": "2036Q4"}),
         "key-trajectory": lambda book: with_share(put(book, cm.T2_TRAJ, TRAJ_STEPS), KEY_MID),
         "key-no-payout": lambda book: with_share(with_keys(book, NO_PAYOUT), KEY_MID),
         "key-lam0": lambda book: with_share(with_keys(book, FIXED_LAM0), KEY_YEAR_END),
         "key-recap-q4": lambda book: with_share(with_keys(book, SHORT_Q4), {"enabled": True, "from": "2027Q1"}),
         "key-recap-q4-2029": lambda book: with_share(with_keys(book, SHORT_Q4), KEY_YEAR_END),
         "off": lambda book: with_share(book, OFF)}


@pytest.mark.ci_only
@pytest.mark.parametrize("form", list(FORMS))
def test_control_matches_core_with_the_t2_share(inputs, form):
    """Форма образца с ключом доли инструментов против ядра (чёрный ящик: запуск и поля результата) — прежние строки в
    прежних допусках М§17: квартал перед ключом в конце года и внутри года, первый и последний квартал сетки,
    траектория с ростом, книга без выплаты, λ_F = 0, нехватка капитала с докапитализацией в четвёртом квартале,
    выключенный ключ. Расхождение — находка, а не повод подогнать контрольную модель."""
    book, facts = inputs
    ready = FORMS[form](book)
    run = tcd._core_run(ready, FIXTURE / "facts")
    ctl = cm.c_control_run(ready, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    assert not tcm.exact_match(run, ctl), "V0 слоёв совпали с ядром до 1e-9 — общий код"


@pytest.mark.ci_only
def test_control_matches_core_with_the_t2_share_on_the_quarterly_form(quarterly):
    """Фикстура core_t (квартальный календарь, рост ограничен капиталом, множитель плотности режима) с ключом против
    ядра — в допусках М§17."""
    book, facts, ctl = quarterly
    ready = with_share(book, KEY_T)
    run = tcd._core_run(ready, FIXTURE_T / "facts")
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)


@pytest.mark.ci_only
def test_t2_share_against_core_as_a_black_box(inputs, plain, keyed):
    """Ядро — чёрный ящик: enabled: false (с from и без него) даёт у ядра оценку книги без ключа; ключ двигает точку у двух
    моделей в одну сторону и на близкую величину; книги с ключом вне правил (№ 30) отвергают обе модели."""
    book, facts = inputs
    bare = tcd._core_run(book, FIXTURE / "facts")
    for spec in (OFF, {"enabled": False}):
        run = tcd._core_run(with_share(book, spec), FIXTURE / "facts")
        assert (run.point, run.low, run.high) == (bare.point, bare.low, bare.high)
        assert [c.v_ri for c in run.cells] == [c.v_ri for c in bare.cells]
    mine = keyed["point"] - plain["point"]
    theirs = tcd._core_run(with_share(book, KEY_YEAR_END), FIXTURE / "facts").point - bare.point
    assert mine * theirs > 0.0 and abs(mine - theirs) <= tcm.TOL_VALUE * abs(bare.point), (mine, theirs)
    book_mod = importlib.import_module("model.book")
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    for bad in ({"enabled": True}, {"from": "2029Q1"}, {"enabled": "yes", "from": "2029Q1"},
                {"enabled": True, "from": "2026Q2"}, {"enabled": True, "from": "2037Q1"},
                {"enabled": False, "from": "2029-1"}, {"enabled": True, "from": "2029Q1", "extra": 1}, None):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(with_share(book, bad), facts)
        with pytest.raises(Exception) as refused:
            book_mod.book_from_dict(with_share(book, bad), facts=core_facts)
        assert type(refused.value).__name__ == "BookError", (bad, refused.value)
