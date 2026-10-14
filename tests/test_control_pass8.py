# -*- coding: utf-8 -*-
"""Контрольная модель, восьмой проход ядра (docs/MODEL.md §4.4, §4.9–§4.11, §5.2, §5.7.3, §7, §17): добавочный капитал
держит долю RWA своей клетки (capital.at1_share {enabled, from, spread, base}), надбавка за субординацию дополнительного
капитала (capital.n20.t2_premium {enabled, spread, base}), прочие движения капитала за концом сетки
(valuation.terminal.other_movements ∈ {none, flat_rub}).

* Пример приложения L методики (машинная копия tests/fixtures/core_pass8/example.json): контрольная модель подставляет
  входы примера в свои рабочие функции — правила ключей, неподвижную точку RWA квартала выпуска, купон сверх базы,
  надбавку квартала, счёт норматива годовой ветви и квартального прохода, оценку клетки с терминалом — и получает его
  числа до 1e-9 (М§17): L.1 — доля, путь AT1 и RWA с ключом и рублями якоря (обе ветви минимума ликвидности), мутация
  «без неподвижной точки», купон, строки конца сетки; L.2 — надбавка; L.3 — терминал (пять записей × два значения λ_F);
  L.4 — второй порядок взноса; L.6 — ось прочих движений; L.7 — случаи схемы (точно). Перенос якоря (L.5) исполняет
  инструмент перезаякоривания, не контрольная модель.
* Свойства своего счёта на фикстурах формы образца (tests/fixtures/core — годовая ветвь; AT1 якоря и купон — не ноль) и
  формы панели (tests/fixtures/core_t — квартальный проход капитала; AT1 якоря подставляет тест) с ключами,
  подставленными тестом: без ключей, при enabled: false, при none и при spread: 0 — прежние числа бит в бит; доля клетки
  — AT1_0 к RWA клетки на конце квартала q_α − 1; с q_α ряд AT1 — доля на RWA строки, K20 и K11 пересчитываются тестом,
  RWA строки — формулой §4.11 по остаткам её баланса, тождества баланса и капитала держатся; купон сверх базы и
  надбавка — формулой по кварталам; при нулевых плотностях балансирующих активов RWA бит в бит книги без ключа; κ_20
  блока постоянных частей ниже на α_c; терминал — строки §7; база дивиденда вычитает купон сверх базы.
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
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass8" / "example.json"
EXAMPLE_TOL = 1e-9          # пример приложения L: формулы без шага, одно определение (М§17)
EXACT = 1e-12               # своё свойство: те же действия над теми же числами
put, with_keys, close, key = tcd.put, tcd.with_keys, tcd.close, tcd.key
values_of, rows_of = tcd.values_of, tcd.rows_of
NO_PAYOUT = tcd.NO_PAYOUT
LEFT_SHARE = tcd.LEFT_SHARE
AT1, T2P, OM = cm.AT1_SHARE, cm.T2_PREMIUM, cm.OM_TERMINAL
# Ключи форм (входы теста): квартал перед ключом — конец года (как у книги 0.6), внутри года (собрание — во втором
# квартале, точки проверки 3 и 4 — после ключа), первый прогнозный квартал; база — словом и числом ниже факта якоря.
K1_YEAR_END = {"enabled": True, "from": "2029Q1", "spread": 0.04, "base": "anchor"}
K1_MID = {"enabled": True, "from": "2028Q3", "spread": 0.04, "base": "anchor"}
K1_FIRST = {"enabled": True, "from": "2026Q3", "spread": 0.04, "base": "anchor"}
K1_BASE_100 = {"enabled": True, "from": "2029Q1", "spread": 0.04, "base": 100.0}
K2 = {"enabled": True, "spread": 0.025, "base": "anchor"}
T2_SHARE_MID = {"enabled": True, "from": "2028Q3"}
TRAJ_STEPS = {"2026Q2": 500.3, "2027": 520.0, "2028": 560.0, "2029": 600.0, "2031": 680.0, "LT": 700.0, "LT_from": 2034}
# T2 стоит на уровне якоря до конца 2027 года и растёт с 2028 года (свойство 31: до отхода от базы — бит в бит)
TRAJ_FLAT_THEN_UP = {"2026Q2": 500.3, "2027": 500.3, "2028": 560.0, "2031": 680.0, "LT": 700.0, "LT_from": 2034}
ROW_FIELDS = ("nii", "pbt", "ni_sh", "ci", "bv", "rwa", "k20", "k11", "n20", "n11", "div", "securities", "wholesale")
OM_PATH = {"LT": -2.0}                                   # прочие движения формы: −2 млрд ₽ за квартал (вход теста)
OFF_KEYS = {AT1: {"enabled": False}, T2P: {"enabled": False}, OM: "none"}
OFF_FULL = {AT1: {"enabled": False, "from": "2029Q1", "spread": 0.04, "base": "anchor"},
            T2P: {"enabled": False, "spread": 0.025, "base": "anchor"}, OM: "none"}
# Постоянные части и λ_F = 0 на форме образца — как в tests/test_control_fixed_parts.py (входы теста).
FIXED_LAM0 = {cm.FIXED_GROWTH: 0.0, "volumes.other_assets_fixed": 1200.0,
              "capital.rwa.density." + cm.OAF_DENSITY: 0.8}
SHORT_Q4 = {**tcd.SHORT, "capital.recapitalization": {**tcd.SHORT["capital.recapitalization"],
                                                      "decision_quarter": cm.QY, "lookahead_quarters": 1}}
ZERO_LA_DENSITY = {"capital.rwa.density.securities": 0.0, "capital.rwa.density.liquidity": 0.0}


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


# ============================================================================ пример приложения L

L_S = "example"
L_W, L_R = "W", "r"


def l_book(doc: dict, *, at1=None, t2p=None, om=None, om_path=None, req=(0.11, 0.08), dpp=(0.001, 0.0015),
           t2_zero: bool = False) -> dict:
    """Книга примера L из ключей, которые читают правила ключей и счёт норматива: якорь 2027К4 и сетка 2028 года, вычет
    якоря Н20.0 — 60 (L.1), признание фонда 1 (BVreg = BV + DPreg), поправки — ноль, путь вычета сценария Н20.0 — 0,1 п.п.
    (A_20 = −0,001 — L.1, L.3), траектория T2 — T2 клетки B (L.2; у строк L.1 — ноль: t2_zero), прочие движения — −0,5
    за квартал (L.3)."""
    pers = doc["periods"]
    t2 = [0.0] * len(pers) if t2_zero else doc["t2_premium"]["inputs"]["t2"]
    book = {"meta": {"anchor_period": pers[0], "first_period": pers[1], "last_period": pers[-1]},
            "capital": {
                "n20": {"deductions_anchor": doc["at1"]["capital"]["ded20_0"], "fvoci_recognition": 1.0,
                        "gap_pp": 0.0, "t2": dict(zip(pers, t2))},
                "n11": {"deductions_anchor": 0.0, "gap_pp": 0.0, "audit_cutoffs": [1, 2, 3, 4]},
                "minimum": {"n20_0": req[0], "n1_1": req[1]}, "mgmt_buffer": {"n20_0": 0.0, "n1_1": 0.0},
                "reg_scenarios": {"ids": [L_S], L_S: {"conservation": 0.0, "sifi": 0.0, "ccyb": 0.0,
                                                       "deduction_pp": {"n20_0": dpp[0], "n1_1": dpp[1]}}}},
            "equity": {"other_movements": {"LT": doc["terminal"]["inputs"]["om_lt_quarter"]} if om_path is None
                       else om_path},
            "dividends": {"policy": {"threshold": 0.0}}}
    if at1 is not None:
        book["capital"]["at1_share"] = copy.deepcopy(at1)
    if t2p is not None:
        book["capital"]["n20"]["t2_premium"] = copy.deepcopy(t2p)
    if om is not None:
        book["valuation"] = {"terminal": {"other_movements": om}}
    return book


def l_ctx(book: dict, doc: dict, at1_0: float | None = None) -> dict:
    """Контекст счёта норматива на книге примера: ключи — рабочими функциями правил."""
    anchor = cm.c_per_parse(book["meta"]["anchor_period"])
    at1_0 = doc["at1"]["inputs"]["at1_0"] if at1_0 is None else at1_0
    return {"B": book, "A": {"AT1": at1_0}, "rwa0": doc["at1"]["inputs"]["rwa_0"], "ded": cm.c_deduction_parts(book),
            "rub": None, "anchor": anchor, "t2_from": None, "at1": cm.c_at1_share_rule(book, anchor, at1_0),
            "t2p": cm.c_t2_premium_rule(book, anchor), "om": cm.c_om_terminal_rule(book, anchor[0] + 1)}


def l1_path(doc: dict, keyed: bool) -> dict:
    """Путь L.1 рабочими функциями: до квартала ключа — факт якоря, RWA = G + b × max(LA_x, LA_min); квартал q_α − 1
    задаёт долю c_at1_share_of; с q_α — неподвижная точка c_at1_fixed_point на LA без добавочного капитала."""
    inp = doc["at1"]["inputs"]
    ctx = l_ctx(l_book(doc, at1={"enabled": True, "from": inp["from"], "spread": inp["spread"], "base": "anchor"},
                       t2_zero=True), doc)
    q_alpha = ctx["at1"]["from"] if keyed else None
    at1, rwa, la, extra, issue, branch = [inp["at1_0"]], [inp["rwa_0"]], [None], [None], [0.0], [None]
    alpha = None
    for k in range(1, len(doc["periods"])):
        g, b, la_x, la_min = inp["g"][k], inp["b"][k], inp["la_x"][k], inp["la_min"][k]
        if q_alpha is None or k < q_alpha:
            here = max(la_x, la_min)
            rwa.append(g + b * here)
            la.append(here)
            extra.append(max(0.0, la_min - la_x))
            at1.append(at1[-1])
            branch.append("до ключа")
        else:
            fp = cm.c_at1_fixed_point(g, b, la_x - at1[-1], la_min, alpha, "L.1")
            rwa.append(fp["rwa"])
            la.append(fp["la"])
            extra.append(fp["extra"])
            at1.append(fp["at1"])
            branch.append(fp["branch"])
        issue.append(at1[-1] - at1[-2])
        if q_alpha is not None and k == q_alpha - 1:
            alpha = cm.c_at1_share_of(ctx, rwa[-1])
    return {"ctx": ctx, "alpha": alpha, "at1": at1, "rwa": rwa, "la": la, "wholesale_extra": extra, "issue": issue,
            "branch": branch, "share": [a / r for a, r in zip(at1, rwa)]}


@pytest.mark.tact
def test_appendix_l1_share_fixed_point_and_coupon():
    """L.1: правило ключа даёт q_α = 3, базу anchor — факт якоря 20; доля клетки — 20 / 1250 = 1,6 % (RWA конца 2028К2);
    путь с ключом: 2028К3 — ветвь A (минимум не связывает), 2028К4 — ветвь B (выпуск гасит добор опта 5 → 2,9273); путь
    рублями якоря — прежний; в обоих кварталах RWA = G + b × LA окончательного баланса; мутация «без неподвижной точки»
    даёт AT1 22,272 и долю 1,59948 %, а не α_c; купон сверх базы — ноль до 2028К4, там 0,068941 (+ купон якоря 3)."""
    doc = example()
    inp, want = doc["at1"]["inputs"], doc["at1"]
    for keyed, name in ((True, "path_key"), (False, "path_rubles")):
        got = l1_path(doc, keyed)
        if keyed:
            assert got["ctx"]["at1"]["from"] == inp["q_alpha"]
            assert got["ctx"]["at1"]["base"] == inp["base"] == inp["at1_0"]
            close(got["alpha"], want[name]["alpha"], "α_c")
        for field in ("at1", "rwa", "la", "wholesale_extra", "issue", "share"):
            for k, value in enumerate(want[name][field]):
                if value is None:
                    continue
                close(got[field][k], value, f"{name}.{field}[{k}]")
        for k in range(1, len(doc["periods"])):
            label = want[name]["branch"][k]
            assert got["branch"][k] == (label[:1] if label[:1] in ("A", "B") else "до ключа"), (name, k, label)
            # RWA = G + b × LA окончательного баланса (М§4.10): неподвижная точка решена, а не пропущена
            close(got["rwa"][k], inp["g"][k] + inp["b"][k] * got["la"][k], f"{name}: RWA = G + b × LA [{k}]")
    # мутация «без неподвижной точки»: AT1 — доля RWA баланса без выпуска квартала
    mut, alpha = want["mutation_no_fixed_point"], want["path_key"]["alpha"]
    k = inp["q_alpha"]
    rwa_without = inp["g"][k] + inp["b"][k] * max(inp["la_x"][k], inp["la_min"][k])
    at1_wrong = alpha * rwa_without
    rwa_final = inp["g"][k] + inp["b"][k] * (inp["la_x"][k] + at1_wrong - inp["at1_0"])
    close(rwa_without, mut["rwa_without_issue"], "мутация: RWA без выпуска")
    close(at1_wrong, mut["at1"], "мутация: AT1")
    close(rwa_final, mut["rwa_final_balance"], "мутация: RWA окончательного баланса")
    close(at1_wrong / rwa_final, mut["share"], "мутация: доля не α_c")
    assert abs(at1_wrong / rwa_final - alpha) > 1e-6
    # купон сверх базы — на остаток конца прошлого квартала по ставке своего мира (М§4.9)
    path = want["path_key"]["at1"]
    for k in range(1, len(doc["periods"])):
        new = cm.c_at1_coupon_new(inp["key"][k] + inp["spread"], path[k - 1], inp["base"], doc["days"][k])
        close(new, want["coupons"]["coupon_new"][k], f"купон сверх базы [{k}]")
        anchor = inp["coupon_annual"] if k == len(doc["periods"]) - 1 else 0.0          # купон якоря — в 4-м квартале
        close(anchor + new, want["coupons"]["coupon"][k], f"купон целиком [{k}]")
    # b × α ≥ 1 — отказ: решение не единственно
    with pytest.raises(cm.ControlInputError, match="b × α"):
        cm.c_at1_fixed_point(1000.0, 0.5, 200.0, 100.0, 2.0, "проба")


@pytest.mark.tact
@pytest.mark.parametrize("quarterly", [False, True], ids=["годовая ветвь", "квартальный проход"])
def test_appendix_l1_rows(quarterly):
    """L.1: строка 2028К4 с ключом и рублями якоря рабочими функциями счёта норматива — RWA, Ded20, AT1, K20, Н20.0 и
    слагаемое AT1: N20 − (K20 − AT1) / RWA − A_20 = α_c с ключом (1,6 %) и AT1_0 / RWA_Q рублями якоря (1,3141 %)."""
    doc = example()
    want, cap = doc["at1"]["rows_Q"], doc["at1"]["capital"]
    path = l1_path(doc, True)
    at = cm.c_per_parse(doc["periods"][-1])
    for which, ctx, share in (("key", path["ctx"], path["alpha"]),
                              ("rubles", l_ctx(l_book(doc, t2_zero=True), doc), None)):
        rwa = want[which]["rwa"]
        profit = {at: 0.0}
        if quarterly:
            got = cm._c_quarter_capital(ctx, L_S, *at, 0.0, profit, None, share)(cap["bvreg"], 0.0, rwa)
        else:
            at1 = cm.c_at1_at(ctx, *at, rwa, share)
            got = cm._c_capital(ctx, L_S, *at, cap["bvreg"], 0.0, 0.0, rwa, profit, None, at1)
        a20 = got["n20"] - got["k20"] / rwa
        close(a20, -cap["dpp20"], f"{which}: A_20")
        for field in ("ded20", "at1", "k20", "n20"):
            close(got[field], want[which][field], f"{which}.{field}")
        close(got["n20"] - (got["k20"] - got["at1"]) / rwa - a20, want[which]["at1_term"], f"{which}: слагаемое AT1")
        if which == "key":
            close(want[which]["at1_term"], path["alpha"], "слагаемое AT1 — α_c")
    # до квартала ключа AT1 — факт якоря, и доля там не читается
    ctx = path["ctx"]
    assert cm.c_at1_at(ctx, 2028, 2, 1250.0, None) == doc["at1"]["inputs"]["at1_0"]
    with pytest.raises(cm.ControlInputError, match="не задана"):
        cm.c_at1_at(ctx, 2028, 3, 1300.0, None)


@pytest.mark.tact
def test_appendix_l2_premium():
    """L.2: надбавка — на T2 конца прошлого квартала сверх базы anchor (10 — траектория в квартале якоря): 0; 0; 0,012603;
    0,027726; надбавка года — 0,040329; год T + 1 — 0,025 × (16,8 − 10) = 0,17."""
    doc = example()
    inp, want = doc["t2_premium"]["inputs"], doc["t2_premium"]
    ctx = l_ctx(l_book(doc, t2p={"enabled": True, "spread": inp["spread"], "base": "anchor"}), doc)
    rule = ctx["t2p"]
    assert rule["base"] == inp["base"] == inp["t2"][0]
    sp = [None] + [cm.c_t2_premium_q(rule["spread"], inp["t2"][k - 1], rule["base"], doc["days"][k])
                   for k in range(1, len(doc["periods"]))]
    for k, value in enumerate(want["sp"]):
        if value is not None:
            close(sp[k], value, f"надбавка [{k}]")
    close(sum(sp[1:]), want["sp_L"], "надбавка года")
    close(rule["spread"] * (inp["t2"][-1] - rule["base"]), want["sp_T1"], "надбавка года T + 1")
    # база числом
    number = l_ctx(l_book(doc, t2p={"enabled": True, "spread": inp["spread"], "base": 12.0}), doc)["t2p"]
    assert number["base"] == 12.0


def l3_value(doc: dict, record: str, lam) -> dict:
    """Синтетическая клетка L.3 — рабочей функцией оценки клетки (_c_value_cell) на контексте из входов примера: одна
    строка конца сетки (2028К4) с нормативами терминала примера; ключи — рабочими функциями правил на книге примера
    (record: sample, K1, K2, K3, K1K2K3); доля инструментов клетки B — 0,8 % (её ключ стоит во всех записях)."""
    t = doc["terminal"]["inputs"]
    blk = t["block"]
    with_k1, with_k2, with_k3 = (record in ("K1", "K1K2K3"), record in ("K2", "K1K2K3"), record in ("K3", "K1K2K3"))
    k_q = (1.0 + t["k_t"]) ** (1.0 / cm.QY) - 1.0
    y, h = 2028, cm.QY
    book = l_book(doc, at1={"enabled": True, "from": doc["periods"][1], "spread": t["spread"], "base": t["base"]}
                  if with_k1 else None,
                  t2p={"enabled": True, "spread": doc["t2_premium"]["inputs"]["spread"], "base": "anchor"}
                  if with_k2 else None, om="flat_rub" if with_k3 else None, req=(t["req20"], t["req11"]))
    book.update({"worlds": {L_W: {"lt_inflation": t["lt_inflation"]}}, "pnl": {"nci_share": t["nci"]},
                 "volumes": {"liquid_min_share": t["min_share"], "securities_share_of_liquid": 0.5},
                 "tax": {"statutory": t["tau_stat"]}})
    book.setdefault("valuation", {}).setdefault("terminal", {}).update(
        {"excess_capital_multiple": t["multiple"], "fade": t["fade"], "real_growth": t["real_growth"]})
    base = l_ctx(book, doc, at1_0=t["base"])
    rwa0 = doc["at1"]["inputs"]["rwa_0"]
    ded = {cm.NORM_TOTAL: {"share": None, "fix": blk["c20"], "grow": doc["at1"]["capital"]["ded20_0"]},
           cm.NORM_BASE: {"share": None, "fix": blk["c11"], "grow": doc["at1"]["capital"]["ded20_0"]}}
    ctx = {**base, "A": {"BV": t["bv_q"], "cpn_quarter": 1, "cpn_annual": t["coupon"], "AT1": t["base"]},
           "clock": {"p0": 0, "pos": 0.0, "t_start": {0: 0.0}, "tau_end": {0: 1.0 / cm.QY}},
           "periods": [{"year": y, "quarters": [h], "n": 1}],
           "disc": {L_W: lambda tau: (1.0 + k_q) ** (-cm.QY * tau)}, "recap": None, "lam_f": lam,
           "oaf": blk["f_a"], "dens_oaf": blk["r_f"] / blk["f_a"], "oaf_path": None, "rwa_mult": {}, "ded": ded,
           "rwa0": rwa0, "t2_from": 1}
    assets = 1000.0                       # балансирующие активы: запас над минимумом m × активы — вход примера
    liquid = t["headroom"] + t["min_share"] * assets
    at1_q = t["alpha"] * t["rwa"] if with_k1 else t["base"]
    last = {"ci_q": [0.0], "ci": 0.0, "div_list": [], "rec_list": [], "bv": t["bv_q"],
            "n20": t["n20"]["key" if with_k1 else "rubles"], "n11_star": t["n11_star"], "dpreg": 0.0, "rwa": t["rwa"],
            "req20": t["req20"], "req11": t["req11"], "securities": liquid / 2.0, "liquidity": liquid / 2.0,
            "assets": assets, "wholesale_extra": t["wt"], "y_sec_end": t["y_bal"], "y_liq_end": t["y_bal"],
            "c_wh_end": t["c_wh"], "pbt": t["pbt_l"], "tau_eff": t["tau"], "dn_q": [1.0], "xf_q": [1.0],
            "t2s": blk["chi"], "a1s": t["alpha"] if with_k1 else None, "at1": at1_q, "key_q": [t["key_Q"]],
            "sp": t["sp_L"], "t2": doc["t2_premium"]["inputs"]["t2"][-1]}
    return cm._c_value_cell(ctx, {"world": L_W, "regime": L_R, "scenario": L_S}, [last], {})


@pytest.mark.tact
def test_appendix_l3_terminal():
    """L.3: терминал клетки B конца сетки — пять записей (образец, доля AT1, надбавка, прочие движения, все три) при λ_F = 1
    и 0 рабочей функцией оценки клетки: X_T, BV*, g, Y_X, NI_T+1, купон года T + 1, CI_T+1, OM_ann / k_T, капитал и
    доход бизнеса, ROE_T, ROE'_T, P_T, TV_RI, TV_DDM и блок постоянных частей (κ_20 0,163 → 0,147 с долей AT1);
    прочие движения сдвигают TV_RI, P_T и TV_DDM ровно на OM_ann / k_T при любом λ_F, X_T, BV* и ROE — нет; DDM = RI."""
    doc = example()
    t = doc["terminal"]["inputs"]
    got = {}
    for record, lams in doc["terminal"]["records"].items():
        for lam_key, want in lams.items():
            lam = None if lam_key == "lam1" else 0.0
            out = l3_value(doc, record, lam)
            got[(record, lam_key)] = out
            what = f"{record} {lam_key}"
            row = {"n20": t["n20"]["key" if record in ("K1", "K1K2K3") else "rubles"], "n11_star": t["n11_star"],
                   "dpreg": 0.0, "rwa": t["rwa"], "req20": t["req20"], "req11": t["req11"]}
            excess = cm.c_terminal_excess(row, t["multiple"])
            close(excess["x20"], want["x20"], f"{what}: x20")
            close(excess["x11"], want["x11"], f"{what}: x11")
            for mine, theirs in (("x_t", "x_t"), ("bv_star", "bv_star"), ("g_t", "g"), ("y_x", "y_x"), ("ni_t1", "ni"),
                                 ("ci_t1", "ci"), ("roe_t_raw", "roe"), ("roe_t", "roe_faded"), ("tv_ri", "tv_ri"),
                                 ("tv_ddm", "tv_ddm")):
                close(out[mine], want[theirs], f"{what}: {theirs}")
            close(out.get("cpn_t1", t["coupon"]), want["coupon_t1"], f"{what}: купон года T + 1")
            close(out.get("om_term", 0.0), want["om_term"], f"{what}: OM_ann / k_T")
            close(out["tv_ddm"] - out["x_t"], want["p_t"], f"{what}: P_T")
            close(out["tv_ddm"], t["bv_q"] + out["tv_ri"], f"{what}: TV_DDM = BV_Q + TV_RI")
            if want["block"] is None:
                assert "terminal_fixed" not in out, what
                close(out["bv_star"], want["business_capital"], f"{what}: капитал бизнеса")
                continue
            node = out["terminal_fixed"]
            close(node["business_capital"], want["business_capital"], f"{what}: B")
            close(node["business_ci"], want["business_ci"], f"{what}: CI_B")
            assert node["binding"] == want["block"]["binding"], what
            for field in ("kappa", "f_k", "d_f", "i_f"):
                close(node[field], want["block"][field], f"{what}: блок {field}")
            close(node["kappa_all"][cm.NORM_BASE], t["block"]["kappa11"], f"{what}: κ_11")
    # прочие движения: ровно OM_ann / k_T при любом λ_F; X_T, BV*, ROE — те же
    om = got[("K3", "lam1")]["om_term"]
    for lam_key in ("lam1", "lam0"):
        a, b = got[("sample", lam_key)], got[("K3", lam_key)]
        for field in ("tv_ri", "tv_ddm"):
            assert b[field] - a[field] == pytest.approx(om, abs=EXACT), (lam_key, field)
        for field in ("x_t", "bv_star", "roe_t_raw", "roe_t", "ci_t1"):
            assert a[field] == b[field], (lam_key, field)
    # κ_20 с ключом доли AT1 — ровно на α_c ниже, κ_11 прежний
    k_s, k_1 = (got[(r, "lam0")]["terminal_fixed"]["kappa_all"] for r in ("sample", "K1"))
    assert k_s[cm.NORM_TOTAL] - k_1[cm.NORM_TOTAL] == pytest.approx(t["alpha"], abs=EXACT)
    assert k_s[cm.NORM_BASE] == k_1[cm.NORM_BASE]
    close(k_s[cm.NORM_TOTAL], t["block"]["kappa20_sample"] - t["block"]["chi"], "κ_20 образца (с χ_c)")


@pytest.mark.tact
def test_appendix_l4_recap_second_order():
    """L.4: деньги взноса и выпуск AT1 за их RWA — неподвижная точка рабочей функцией: RWA′ − RWA = b × Rec / (1 − b × α)
    = 10,8949 (без доли AT1 — 10,86); вычет + 0,6537, AT1 + 0,1743, T2 + 0,0872; K20 окончательного расчёта выше пробного
    на 53,9078 = Rec − ΔDed + (χ_c + α_c) × ΔRWA (счёт норматива годовой ветви)."""
    doc = example()
    inp, want = doc["recap"]["inputs"], doc["recap"]
    g, la_free, la_min = 1500.0, 300.0, 100.0          # минимум ликвидности не связывает (вход теста)
    trial = cm.c_at1_fixed_point(g, inp["b"], la_free, la_min, inp["alpha"])
    final = cm.c_at1_fixed_point(g, inp["b"], la_free + inp["rec"], la_min, inp["alpha"])
    d_rwa = final["rwa"] - trial["rwa"]
    close(d_rwa, want["d_rwa"], "ΔRWA")
    close(d_rwa, inp["b"] * inp["rec"] / (1.0 - inp["b"] * inp["alpha"]), "b × Rec / (1 − b × α)", EXACT)
    close(cm.c_at1_fixed_point(g, inp["b"], la_free + inp["rec"], la_min, 0.0)["rwa"]
          - cm.c_at1_fixed_point(g, inp["b"], la_free, la_min, 0.0)["rwa"], want["d_rwa_without_alpha"], "без доли AT1")
    close(final["at1"] - trial["at1"], want["d_at1"], "ΔAT1")
    # строки норматива: вычет растёт с RWA (Dgrow / RWA_0 = 0,06), T2 и AT1 — по долям
    book = l_book(doc)
    book["capital"]["n20"]["deductions_anchor"] = inp["dgrow_over_rwa0"] * doc["at1"]["inputs"]["rwa_0"]
    ctx = {**l_ctx(book, doc), "t2_from": 1}
    at = cm.c_per_parse(doc["periods"][-1])
    rows = {}
    for name, fp, bv in (("trial", trial, 200.0), ("final", final, 200.0 + inp["rec"])):
        rows[name] = cm._c_capital(ctx, L_S, *at, bv, 0.0, 0.0, fp["rwa"], {at: 0.0}, inp["chi"], fp["at1"])
    close(rows["final"]["ded20"] - rows["trial"]["ded20"], want["d_ded20"], "ΔDed20")
    close(rows["final"]["t2"] - rows["trial"]["t2"], want["d_t2"], "ΔT2")
    close(rows["final"]["k20"] - rows["trial"]["k20"], want["d_k20"], "ΔK20")
    close(rows["final"]["k20"] - rows["trial"]["k20"],
          inp["rec"] - (rows["final"]["ded20"] - rows["trial"]["ded20"]) + (inp["chi"] + inp["alpha"]) * d_rwa,
          "Rec − ΔDed + (χ + α) × ΔRWA", EXACT)


@pytest.mark.tact
def test_appendix_l6_axis_of_other_movements():
    """L.6: ось вида shift на траектории прочих движений с концом −0,25 за квартал двигает OM_LT вместе с явными годами: с
    ключом flat_rub TV_RI, P_T и TV_DDM клетки L.3 сдвигаются на 4 × (−0,25) / k_T = −5,8873; без ключа — нет."""
    doc = example()
    t = doc["terminal"]["inputs"]
    delta = -0.25
    shifted = {"LT": t["om_lt_quarter"] + delta}
    base_rule = cm.c_om_terminal_rule(l_book(doc, om="flat_rub"), 2028)
    moved_rule = cm.c_om_terminal_rule(l_book(doc, om="flat_rub", om_path=shifted), 2028)
    close(base_rule["om_ann"], cm.QY * t["om_lt_quarter"], "OM_ann")
    args = (12.7, 317.3, 30.5296, t["k_t"], 0.0608, t["fade"])
    a = cm.c_terminal_lines(*args, om_ann=base_rule["om_ann"])
    b = cm.c_terminal_lines(*args, om_ann=moved_rule["om_ann"])
    for field in ("tv_ri", "p_t", "tv_ddm"):
        close(b[field] - a[field], cm.QY * delta / t["k_t"], f"сдвиг {field}")
        close(b[field] - a[field], -5.8873, f"сдвиг {field} — число текста", 1e-4)
    assert cm.c_om_terminal_rule(l_book(doc, om_path=shifted), 2028) is None          # без ключа — ноль
    assert cm.c_terminal_lines(*args) == cm.c_terminal_lines(*args, om_ann=None)


SCHEMA_L7 = [
    (AT1, None, "годен"),
    (AT1, {"enabled": True, "from": "2028Q3", "spread": 0.04, "base": "anchor"}, "годен"),
    (AT1, {"enabled": True, "from": "2028Q1", "spread": 0.04, "base": 20}, "годен"),
    (AT1, {"enabled": True, "from": "2028Q3", "spread": 0.04}, "отказ"),
    (AT1, {"enabled": True, "from": "2028Q3", "spread": None, "base": "anchor"}, "отказ"),
    (AT1, {"enabled": True, "from": "2027Q4", "spread": 0.04, "base": "anchor"}, "отказ"),
    (AT1, {"enabled": False}, "годен"),
    (AT1, {"enabled": False, "from": "2028Q3", "spread": 0.04, "base": -1}, "отказ"),
    (T2P, {"enabled": True, "spread": 0.025, "base": "anchor"}, "годен"),
    (T2P, {"enabled": True, "base": "anchor"}, "отказ"),
    (T2P, {"enabled": False}, "годен"),
    (OM, "flat_rub", "годен"),
    (OM, "growing", "отказ"),
]


def l7_rule(book: dict, path: str):
    anchor = cm.c_per_parse(book["meta"]["anchor_period"])
    if path == AT1:
        return cm.c_at1_share_rule(book, anchor, 20.0)
    if path == T2P:
        return cm.c_t2_premium_rule(book, anchor)
    return cm.c_om_terminal_rule(book, 2028)


@pytest.mark.tact
def test_appendix_l7_schema_cases():
    """L.7 (прил. A № 31–33): правила ключей рабочими функциями на тринадцати случаях таблицы — годен или отказ, точно;
    сверх таблицы — null у ключа и у enabled, лишнее поле, from не строкой и не буквально ГГГГQn, spread булево или
    строкой, база строкой, кроме anchor, null у spread под включённым ключом, вид прочих движений не строкой; null у
    полей под выключенным ключом — годен (М§0.1); flat_rub без читаемого значения года L + 1 — отказ."""
    doc = example()
    for path, spec, verdict in SCHEMA_L7:
        book = l_book(doc) if spec is None else put(l_book(doc), path, spec)
        if verdict == "годен":
            got = l7_rule(book, path)
            on = spec is not None and (spec == "flat_rub" if path == OM else spec["enabled"])
            assert (got is not None) == on, (path, spec)
        else:
            with pytest.raises(cm.ControlInputError, match=path.split(".")[-1]):
                l7_rule(book, path)
    rule = l7_rule(put(l_book(doc), AT1, {"enabled": True, "from": "2028Q1", "spread": 0.04, "base": 20}), AT1)
    assert rule == {"from": 1, "spread": 0.04, "base": 20.0}
    first = {**l_ctx(put(l_book(doc), AT1, {"enabled": True, "from": "2028Q1", "spread": 0.04, "base": 20}), doc)}
    close(cm.c_at1_start_share(first), 20.0 / 1000.0, "доля якоря 20 / 1000")
    for path, bad in ((AT1, None), (AT1, {"enabled": None, "from": "2028Q3", "spread": 0.04, "base": "anchor"}),
                      (AT1, {"enabled": True, "from": "2028Q3", "spread": 0.04, "base": "anchor", "until": 1}),
                      (AT1, {"enabled": True, "from": 20283, "spread": 0.04, "base": "anchor"}),
                      (AT1, {"enabled": True, "from": "2028q3", "spread": 0.04, "base": "anchor"}),
                      (AT1, {"enabled": True, "from": "2029Q1", "spread": 0.04, "base": "anchor"}),
                      (AT1, {"enabled": True, "from": "2028Q3", "spread": True, "base": "anchor"}),
                      (AT1, {"enabled": True, "from": "2028Q3", "spread": "0.04", "base": "anchor"}),
                      (AT1, {"enabled": True, "from": "2028Q3", "spread": 0.04, "base": "якорь"}),
                      (AT1, {"enabled": True, "from": "2028Q3", "spread": 0.04, "base": None}),
                      (AT1, {"enabled": False, "from": "2028-3"}), (AT1, ["2028Q3"]),
                      (T2P, None), (T2P, {"enabled": True, "spread": 0.025, "base": -0.1}),
                      (T2P, {"enabled": "yes", "spread": 0.025, "base": "anchor"}),
                      (T2P, {"enabled": True, "spread": 0.025, "base": "anchor", "from": "2028Q3"}),
                      (T2P, {"spread": 0.025, "base": "anchor"}), (OM, None), (OM, True), (OM, ["flat_rub"])):
        with pytest.raises(cm.ControlInputError, match=path.split(".")[-1]):
            l7_rule(put(l_book(doc), path, bad), path)
    for path, good in ((AT1, {"enabled": False, "from": None, "spread": None, "base": None}),
                       (T2P, {"enabled": False, "spread": None, "base": None}), (OM, "none")):
        assert l7_rule(put(l_book(doc), path, good), path) is None
    assert cm.c_t2_premium_rule(put(l_book(doc), T2P, {"enabled": True, "spread": 0, "base": 0}),
                                (2027, 4)) == {"spread": 0.0, "base": 0.0}
    with pytest.raises(cm.ControlInputError, match="other_movements"):
        cm.c_om_terminal_rule(l_book(doc, om="flat_rub", om_path={"2028Q4": 1.0, "LT_from": 2030}), 2028)


@pytest.mark.tact
def test_om_value_of_the_year_after_the_grid():
    """М§0.4, §7: OM_LT — значение года L + 1 своим читателем: при LT — LT (и при ключе года L, отличном от LT); без LT —
    значение последнего заданного года; у скаляра — само число; OM_ann = 4 × OM_LT."""
    doc = example()
    for path, want in (({"LT": -0.5}, -0.5), ({"2028": -3.0, "LT": -0.5}, -0.5), ({"2027": -1.0, "2028": -3.0}, -3.0),
                       (-0.75, -0.75), ({"2028Q4": -9.0, "2028": -2.0, "LT": -1.0}, -1.0)):
        rule = cm.c_om_terminal_rule(l_book(doc, om="flat_rub", om_path=path), 2028)
        assert rule["om_lt"] == want and rule["om_ann"] == cm.QY * want, path


# ============================================================================ свойства на форме образца (годовая ветвь)


@pytest.fixture(scope="module")
def inputs():
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8")), cm.c_facts_bundle(FIXTURE / "facts")


@pytest.fixture(scope="module")
def plain(inputs):
    return cm.c_control_run(*inputs)


@pytest.fixture(scope="module")
def keyed(inputs):
    """Ключ доли добавочного капитала с 2029К1: квартал перед ключом — конец года (как у книги 0.6)."""
    book, facts = inputs
    return cm.c_control_run(put(book, AT1, K1_YEAR_END), facts)


@pytest.fixture(scope="module")
def keyed_mid(inputs):
    """Ключ с 2028К3: квартал перед ключом внутри года решения о дивиденде, точки проверки 3 и 4 — после ключа."""
    book, facts = inputs
    return cm.c_control_run(put(book, AT1, K1_MID), facts)


def a20_of(ctx: dict, s: str, y: int, h: int) -> float:
    B = ctx["B"]
    return cm.c_bnum(B, "capital.n20.gap_pp") - cm.c_traj_at(
        cm.c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n20_0"), y, h)


def rwa_by_formula(ctx: dict, c: dict, i: int) -> float:
    """RWA строки формулой §4.11 по остаткам её окончательного баланса (кредитные книги, бумаги, ликвидность, прочие
    активы) — тест пересчитывает сам."""
    r = c["rows"][i]
    E = {**r["books_end"], cm.SECURITIES: r["securities"], cm.LIQUIDITY: r["liquidity"]}
    p = ctx["periods"][i]
    dn = r["dn_q"][-1] if i else r["dn_q"][-1]
    return cm._c_rwa_of(ctx, c["regime"], p["year"], p["quarters"][-1], E, r["oa"], dn, r["xf_q"][-1])


def set_alpha(ctx: dict, rows: list) -> float:
    """Доля клетки, пересчитанная тестом: AT1_0 к RWA клетки на конце квартала q_α − 1 — у конца года RWA строки, внутри
    года — геометрический путь RWA между концами соседних строк."""
    q_set = ctx["at1"]["from"] - 1
    y, h = cm.c_qper(ctx["anchor"], q_set)
    for i, p in enumerate(ctx["periods"]):
        if p["year"] != y:
            continue
        start = ctx["rwa0"] if i == 0 else rows[i - 1]["rwa"]
        j = list(p["quarters"]).index(h)
        rwa = rows[i]["rwa"] if j == p["n"] - 1 else start * (rows[i]["rwa"] / start) ** ((j + 1) / p["n"])
        return ctx["A"]["AT1"] / rwa
    raise AssertionError("квартал перед ключом вне сетки")


@pytest.mark.tact
def test_off_and_absent_keys_are_the_sample_branch(inputs, plain):
    """Без ключей, при enabled: false (с полями и без, база словом), при none и при spread: 0 у надбавки — ряды, оценка и
    точка формы образца бит в бит; узла восьмого прохода нет (кроме spread: 0 — ключ включён); ряд AT1 — факт якоря."""
    book, facts = inputs
    ctx = plain["ctx"]
    assert ctx["at1"] is None and ctx["t2p"] is None and ctx["om"] is None and "pass8" not in plain
    for keys in (OFF_KEYS, OFF_FULL, {T2P: {**K2, "spread": 0.0}}):
        same = cm.c_control_run(with_keys(book, keys), facts)
        assert values_of(same) == values_of(plain), keys
        assert rows_of(same, ("at1", "k20", "n20", "nii", "ci", "rwa")) == rows_of(plain, ("at1", "k20", "n20", "nii",
                                                                                               "ci", "rwa"))
        assert [c["anchor_capital"] for c in same["cells"]] == [c["anchor_capital"] for c in plain["cells"]]
    for c in plain["cells"]:
        assert all(r["at1"] == ctx["A"]["AT1"] for r in c["rows"])
        assert all("a1s" not in r and "sp" not in r for r in c["rows"])


@pytest.mark.tact
def test_bad_keys_fail_loudly(inputs):
    """Ограничения № 31–33 приложения A на форме образца: отказ книги; годные формы — считаются."""
    book, facts = inputs
    for path, bad in ((AT1, {"enabled": True, "from": "2029Q1", "spread": 0.04}),
                      (AT1, {"enabled": True, "from": "2026Q2", "spread": 0.04, "base": "anchor"}),
                      (AT1, {"enabled": True, "from": "2037Q1", "spread": 0.04, "base": "anchor"}),
                      (AT1, {"enabled": False, "from": "2029Q1", "spread": 0.04, "base": -5.0}),
                      (T2P, {"enabled": True, "spread": "2.5%", "base": "anchor"}),
                      (OM, "indexed")):
        with pytest.raises(cm.ControlInputError, match=path.split(".")[-1]):
            cm.c_control_context(put(book, path, bad), facts)
    for path, good, check in ((AT1, K1_FIRST, lambda c: c["at1"]["from"] == 1),
                              (AT1, {**K1_YEAR_END, "from": "2036Q4"}, lambda c: c["at1"]["from"] == 42),
                              (AT1, K1_BASE_100, lambda c: c["at1"]["base"] == 100.0),
                              (AT1, K1_YEAR_END, lambda c: c["at1"]["base"] == c["A"]["AT1"]),
                              (T2P, K2, lambda c: c["t2p"]["base"] == cm.c_traj_at(cm.c_bget(c["B"], cm.T2_TRAJ), 2026, 2)),
                              (OM, "flat_rub", lambda c: c["om"]["om_lt"] == 0.0)):
        assert check(cm.c_control_context(put(book, path, good), facts)), (path, good)


@pytest.mark.tact
def test_at1_rows_follow_the_formula(keyed, keyed_mid, plain):
    """Свойства 20–23 (М§4.11, §4.10, §4.9) своим счётом: доля клетки — AT1_0 к RWA клетки на конце квартала q_α − 1 (у
    ключа с 2029К1 — RWA конца 2028 года, у ключа с 2028К3 — профиль RWA 2028 года), своя у клеток разных миров и
    режимов; с q_α ряд AT1 — доля на RWA строки (1e-12), раньше — факт якоря; K20 и K11, пересчитанные тестом по рядам
    клетки, совпадают с её рядами (K11 — без AT1); слагаемое N20 − (K20 − AT1) / RWA − A_20 — α_c; RWA строки,
    пересчитанные формулой §4.11 по остаткам её баланса, равны ряду (1e-12) — неподвижная точка решена; тождества баланса
    (AT1 — на стороне пассивов) и капитала держатся; купон сверх базы кварталов — (key + s_α) × (AT1_(q−1) − B_α) × d / 365
    по пути AT1 строки; строка якоря от ключа не зависит."""
    for res in (keyed, keyed_mid):
        ctx = res["ctx"]
        B, rule, at1_0 = ctx["B"], ctx["at1"], ctx["A"]["AT1"]
        f = cm.c_bnum(B, "capital.n20.fvoci_recognition")
        shares = set()
        for c, p0 in zip(res["cells"], plain["cells"]):
            assert c["anchor_capital"] == p0["anchor_capital"]
            rows = c["rows"]
            alpha = rows[-1]["a1s"]
            assert alpha == pytest.approx(set_alpha(ctx, rows), rel=EXACT), key(c)
            shares.add(alpha)
            prev_at1, prev_bv = at1_0, ctx["A"]["BV"]
            for i, (period, r) in enumerate(zip(ctx["periods"], rows)):
                y, h = period["year"], period["quarters"][-1]
                k_end = cm.c_qidx(ctx["anchor"], y, h)
                if k_end >= rule["from"]:
                    assert r["a1s"] == alpha
                    assert r["at1"] == pytest.approx(alpha * r["rwa"], rel=EXACT), (key(c), y)
                    assert r["n20"] - (r["k20"] - r["at1"]) / r["rwa"] - a20_of(ctx, c["scenario"], y, h) == \
                        pytest.approx(alpha, abs=EXACT)
                else:
                    assert r["at1"] == at1_0 and all(x == at1_0 for x in r["at1_q"]), (key(c), y)
                own = r["bv"] + r["dpreg"] - (1.0 - f) * r["R"]
                assert r["k20"] == pytest.approx(own - r["ded20"] + r["at1"] + r["t2"], rel=EXACT)
                assert r["k11"] == pytest.approx(own - max(r["e_unaudited"], 0.0) - r["ded11"], rel=EXACT)
                assert rwa_by_formula(ctx, c, i) == pytest.approx(r["rwa"], rel=EXACT), (key(c), y)
                assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
                assert prev_bv + r["ni_sh"] - r["cpn_net"] + r["oci"] + r["om"] - r["div"] == pytest.approx(
                    r["bv"], rel=1e-12)
                path = [prev_at1] + r["at1_q"]
                for j, q in enumerate(period["quarters"]):
                    want = (r["key_q"][j] + rule["spread"]) * (path[j] - rule["base"]) * cm.c_q_len(y, q) / cm.DAYS_BASE
                    assert r["cpn_new_q"][j] == pytest.approx(want, rel=EXACT, abs=1e-12), (key(c), y, q)
                    if cm.c_qidx(ctx["anchor"], y, q) >= rule["from"] and j < period["n"] - 1:
                        start = ctx["rwa0"] if i == 0 else rows[i - 1]["rwa"]
                        rwa_j = start * (r["rwa"] / start) ** ((j + 1) / period["n"])
                        assert r["at1_q"][j] == pytest.approx(alpha * rwa_j, rel=1e-9)
                assert sum(r["at1_issue"]) == pytest.approx(r["at1"] - prev_at1, abs=1e-9)
                # купон сверх базы — после налога законной ставкой квартала, в совокупном доходе (М§4.9)
                tau = [cm.c_traj_at(cm.c_bget(B, "tax.statutory"), y, q) for q in period["quarters"]]
                assert r["cpn_new_net"] == pytest.approx(sum(x * (1.0 - t) for x, t in zip(r["cpn_new_q"], tau)),
                                                         rel=EXACT, abs=1e-12)
                cpn_tau = cm.c_traj_at(cm.c_bget(B, "tax.statutory"), y, ctx["A"]["cpn_quarter"])
                assert r["ci"] == pytest.approx(r["ni_sh"] - r["cpn_anchor"] * (1.0 - cpn_tau) - r["cpn_new_net"]
                                                + r["oci"] + r["om"], rel=EXACT, abs=1e-9)
                # выпуск — деньги конца своего квартала: в среднем остатке балансирующих активов по времени прихода
                n = period["n"]
                w_ci = [(n - (j + 1)) / n - 0.5 for j in range(n)]
                own_shift = sum(a * b for a, b in zip(w_ci, r["ci_q"])) - r["paid_shift"] + r["curve_la"]
                issue_shift = sum(a * b for a, b in zip(w_ci, r["at1_issue"]))
                assert r["shift_la"] - own_shift == pytest.approx(issue_shift, abs=1e-6 * abs(r["securities"])), \
                    (key(c), y)
                prev_at1, prev_bv = r["at1"], r["bv"]
        assert len(shares) > len(ctx["worlds"]), "у клеток разных миров и режимов — свои доли"
        node = res["pass8"]["at1"]
        assert node["share_min"] == min(shares) and node["share_max"] == max(shares)


@pytest.mark.tact
def test_trial_step_of_the_dividend_sets_the_share_with_its_own_rwa(keyed_mid):
    """Пробный проход дивиденда идёт через квартал q_α − 1 (2028К2): он задаёт долю своими RWA (без дивиденда года), и
    запас решения в точках проверки 3 и 4 — с AT1 этой доли на RWA точки; окончательный шаг задаёт долю своими RWA."""
    res = keyed_mid
    ctx = res["ctx"]
    y_set, h_set = cm.c_qper(ctx["anchor"], ctx["at1"]["from"] - 1)
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
        assert st.get("a1s") is None
        trial = cm._c_period(ctx, ident, st, i, 0.0)[1]
        j = list(p["quarters"]).index(h_set)
        rwa_set = st["rwa"] * (trial["rwa"] / st["rwa"]) ** ((j + 1) / p["n"])
        assert trial["a1s"] == pytest.approx(ctx["A"]["AT1"] / rwa_set, rel=1e-12)
        decision = c["decisions"].get(y_set - 1)
        if decision is None or decision.get("kind") != "policy" or c["rows"][i]["div"] == 0.0:
            continue
        assert trial["a1s"] != c["rows"][i]["a1s"]        # окончательный шаг (с дивидендом) — своими RWA
        buf20 = cm.c_bnum(ctx["B"], "capital.mgmt_buffer.n20_0")
        threshold = cm.c_bnum(ctx["B"], "dividends.policy.threshold")
        H = float("inf")
        for h in [int(x) for x in cm.c_bget(ctx["B"], "dividends.calendar.checkpoints")]:
            jj = list(p["quarters"]).index(h)
            rwa_h = st["rwa"] * (trial["rwa"] / st["rwa"]) ** ((jj + 1) / p["n"])
            bv_h = st["BV"] + sum(trial["ci_q"][:jj + 1])
            cap = cm._c_capital(ctx, c["scenario"], p["year"], h, bv_h, 0.0, trial["R_q"][jj], rwa_h,
                                {**st["ni_q"], **trial["ni_q"]}, None, trial["a1s"] * rwa_h)
            H = min(H, (cap["n20"] - max(threshold, cap["floor20"] + buf20)) * rwa_h, (cap["n11"] - cap["req11"]) * rwa_h)
        assert decision["H"] == pytest.approx(H, rel=1e-12, abs=1e-9), key(c)
        seen += 1
    assert seen, "вход теста: решения модели в году квартала перед ключом"


# вне такта сервера: лишние прогоны сетки формы образца — они идут в CI
def test_first_period_key_and_base_number(inputs, plain):
    """Контрольные случаи (М§17, свойство 24): from = first_period — доля якоря AT1_0 / RWA_0 у всех клеток во всех строках;
    база числом ниже факта якоря — купон сверх базы с первого квартала, c_α,q × (AT1_0 − B_α) × d_q / 365, до квартала ключа."""
    book, facts = inputs
    res = cm.c_control_run(put(book, AT1, K1_FIRST), facts)
    ctx = res["ctx"]
    anchor_share = ctx["A"]["AT1"] / ctx["rwa0"]
    assert res["pass8"]["at1"]["anchor_share"] == anchor_share
    for c, p0 in zip(res["cells"], plain["cells"]):
        assert c["anchor_capital"] == p0["anchor_capital"]
        assert {r["a1s"] for r in c["rows"]} == {anchor_share}
        assert all(r["at1"] == pytest.approx(anchor_share * r["rwa"], rel=EXACT) for r in c["rows"])
    based = cm.c_control_run(put(book, AT1, K1_BASE_100), facts)
    ctx = based["ctx"]
    for c in based["cells"][:6]:
        for period, r in zip(ctx["periods"], c["rows"]):
            for j, q in enumerate(period["quarters"]):
                if cm.c_qidx(ctx["anchor"], period["year"], q) <= ctx["at1"]["from"]:
                    want = ((r["key_q"][j] + K1_BASE_100["spread"]) * (ctx["A"]["AT1"] - K1_BASE_100["base"])
                            * cm.c_q_len(period["year"], q) / cm.DAYS_BASE)
                    assert r["cpn_new_q"][j] == pytest.approx(want, rel=EXACT) and want > 0.0


# вне такта сервера: лишние прогоны сетки формы образца — они идут в CI
def test_zero_densities_of_balancing_assets_keep_rwa(inputs):
    """Свойство 25 (вторая часть): при нулевых плотностях бумаг и ликвидности на книге без выплаты RWA всех строк — бит в
    бит книги без ключа (выпуск ложится в активы без веса риска), вычеты и T2 — тоже; K20 выше на прирост собственных
    средств (купон сверх базы, доход денег выпуска) плюс α_c × RWA − AT1_0."""
    book, facts = inputs
    still = with_keys(with_keys(book, NO_PAYOUT), ZERO_LA_DENSITY)
    bare = cm.c_control_run(still, facts)
    res = cm.c_control_run(put(still, AT1, K1_MID), facts)
    ctx = res["ctx"]
    keep = 1.0 - cm.c_bnum(ctx["B"], "capital.n20.fvoci_recognition")
    grew = 0.0
    for a, b in zip(bare["cells"], res["cells"]):
        for period, ra, rb in zip(ctx["periods"], a["rows"], b["rows"]):
            assert ra["rwa"] == rb["rwa"], (key(a), period["year"])
            assert ra["ded20"] == rb["ded20"] and ra["t2"] == rb["t2"]
            if cm.c_qidx(ctx["anchor"], period["year"], period["quarters"][-1]) >= ctx["at1"]["from"]:
                assert rb["at1"] == pytest.approx(rb["a1s"] * rb["rwa"], rel=EXACT)
                own = [r["bv"] + r["dpreg"] - keep * r["R"] for r in (ra, rb)]
                assert rb["k20"] - ra["k20"] == pytest.approx(own[1] - own[0] + rb["at1"] - ra["at1"], rel=1e-9,
                                                              abs=1e-9)
                grew = max(grew, rb["at1"] - ra["at1"])
            else:
                assert rb["at1"] == ra["at1"] == ctx["A"]["AT1"]
    assert grew > 1.0, "вход теста: AT1 по доле отходит от факта якоря"


# вне такта сервера: прогоны формы с ключами
def test_terminal_lines_of_the_three_keys(inputs):
    """М§7, свойства 26 и 30: купон года T + 1 — CPN_ann + (key_Q + s_α) × (AT1_Q − B_α); NI_T+1 —
    [(PBT_L + SP_L)(1 + g) − π × (T2_Q − B_T2) − Y_X](1 − τ)(1 − nci); CI_T+1 = NI_T+1 − CPN_T+1 (1 − τ_stat); с ключом
    flat_rub TV_RI и TV_DDM выше, чем при none, ровно на OM_ann / k_T, X_T, BV*, ROE_T — бит в бит; DDM = RI."""
    book, facts = inputs
    base = with_keys(put(put(book, cm.T2_TRAJ, TRAJ_STEPS), "equity.other_movements", OM_PATH),
                     {AT1: K1_MID, T2P: K2})
    off = cm.c_control_run(base, facts)
    on = cm.c_control_run(put(base, OM, "flat_rub"), facts)
    ctx = on["ctx"]
    B, A = ctx["B"], ctx["A"]
    assert ctx["om"]["om_lt"] == OM_PATH["LT"] and ctx["om"]["om_ann"] == cm.QY * OM_PATH["LT"]
    nci = cm.c_bnum(B, "pnl.nci_share")
    yl = ctx["periods"][-1]["year"]
    tau = cm.c_traj_at(cm.c_bget(B, "tax.statutory"), yl, A["cpn_quarter"])
    for a, b in zip(off["cells"], on["cells"]):
        last = b["rows"][-1]
        cpn = A["cpn_annual"] + (last["key_q"][-1] + ctx["at1"]["spread"]) * (last["at1"] - ctx["at1"]["base"])
        assert b["cpn_t1"] == pytest.approx(cpn, rel=EXACT)
        sp_t1 = ctx["t2p"]["spread"] * (last["t2"] - ctx["t2p"]["base"])
        ni = ((last["pbt"] + last["sp"]) * (1.0 + b["g_t"]) - sp_t1 - b["y_x"]) * (1.0 - last["tau_eff"]) * (1.0 - nci)
        assert b["ni_t1"] == pytest.approx(ni, rel=EXACT) and b["sp_t1"] == pytest.approx(sp_t1, rel=EXACT)
        assert b["ci_t1"] == pytest.approx(ni - cpn * (1.0 - tau), rel=EXACT)
        om = ctx["om"]["om_ann"] / b["k_t"]
        assert b["om_term"] == pytest.approx(om, rel=EXACT) and "om_term" not in a
        assert b["tv_ri"] - a["tv_ri"] == pytest.approx(om, rel=1e-9) and b["tv_ddm"] - a["tv_ddm"] == pytest.approx(
            om, rel=1e-9)
        for field in ("x_t", "bv_star", "roe_t_raw", "roe_t", "ci_t1", "ni_t1"):
            assert a[field] == b[field], (key(a), field)
        assert abs(b["v_ddm"] - b["v_ri"]) <= 1e-9 * max(1.0, abs(b["v_ri"])), key(b)
    assert on["point"] < off["point"]


# вне такта сервера: прогоны формы с нехваткой капитала
def test_dilution_cost_of_the_terminal_reads_the_new_payout(inputs):
    """М§7, §6.5: DC_T — от нового P_T: у книги с докапитализацией и ключом flat_rub отрицательные распределения за концом
    сетки (здесь прочие движения только за T: явные годы — ноль) делают P_T < 0, и цена размывания терминала —
    d / (1 − d) × [max(−X_T, 0) + max(−P_T, 0)] с этим P_T; ряды клеток от ключа не зависят."""
    book, facts = inputs
    path = {"2026": 0.0, "2036": 0.0, "LT": -500.0, "LT_from": 2036}      # вход теста: только за концом сетки
    base = put(with_keys(book, SHORT_Q4), "equity.other_movements", path)
    off = cm.c_control_run(base, facts)
    on = cm.c_control_run(put(base, OM, "flat_rub"), facts)
    d = on["ctx"]["recap"]["d"]
    flipped = 0
    for a, b in zip(off["cells"], on["cells"]):
        assert [r["bv"] for r in a["rows"]] == [r["bv"] for r in b["rows"]]
        p_t = b["tv_ddm"] - b["x_t"]
        assert b["p_t"] == pytest.approx(p_t, rel=EXACT)
        assert b["dc_t"] == pytest.approx(d / (1.0 - d) * (max(-b["x_t"], 0.0) + max(-p_t, 0.0)), rel=1e-12, abs=1e-9)
        flipped += p_t < 0.0 <= a["p_t"]
        assert abs(b["v_ddm"] - b["v_ri"]) <= 1e-9 * max(1.0, abs(b["v_ri"]), b["norm"]), key(b)
    assert flipped, "вход теста: прочие движения за T делают выплату терминала отрицательной"


# вне такта сервера: прогоны формы с ключом надбавки
def test_premium_rows_follow_the_formula(inputs, plain):
    """Свойства 28, 29, 31: ряд надбавки — π × (T2_(q−1) − B_T2) × d / 365 по T2 клетки на концах кварталов (траектория до
    q_χ, доля на профиль RWA с него) — с ключом доли инструментов и без него; ЧПД ниже на надбавку относительно процентов
    книг; тождество прибыли держится; до года, в котором T2 впервые отходит от базы, строки — бит в бит книги без ключа."""
    book, facts = inputs
    stepped = put(book, cm.T2_TRAJ, TRAJ_FLAT_THEN_UP)
    bare = cm.c_control_run(stepped, facts)
    for t2_share in (None, T2_SHARE_MID):
        ready = put(stepped, T2P, K2) if t2_share is None else put(put(stepped, T2P, K2), cm.T2_SHARE, t2_share)
        res = cm.c_control_run(ready, facts)
        ctx = res["ctx"]
        rule, traj, q_chi = ctx["t2p"], cm.c_bget(ctx["B"], cm.T2_TRAJ), ctx["t2_from"]
        assert rule["base"] == TRAJ_FLAT_THEN_UP["2026Q2"]
        for c in res["cells"][::5]:
            rows = c["rows"]
            prev_t2 = rule["base"]
            for i, (period, r) in enumerate(zip(ctx["periods"], rows)):
                y = period["year"]
                start = ctx["rwa0"] if i == 0 else rows[i - 1]["rwa"]
                ends = []
                for j, q in enumerate(period["quarters"]):
                    k = cm.c_qidx(ctx["anchor"], y, q)
                    if q_chi is None or k < q_chi:
                        ends.append(cm.c_traj_at(traj, y, q))
                    else:
                        rwa_j = r["rwa"] if j == period["n"] - 1 else start * (r["rwa"] / start) ** ((j + 1) / period["n"])
                        ends.append(r["t2s"] * rwa_j)
                path = [prev_t2] + ends
                for j, q in enumerate(period["quarters"]):
                    want = rule["spread"] * (path[j] - rule["base"]) * cm.c_q_len(y, q) / cm.DAYS_BASE
                    assert r["sp_q"][j] == pytest.approx(want, rel=1e-9, abs=1e-12), (key(c), y, q)
                assert r["sp"] == pytest.approx(sum(r["sp_q"]), rel=EXACT)
                assert r["pbt"] - r["tax"] - r["ot"] == pytest.approx(r["ni"], rel=EXACT)
                assert sum(r["ni_q"].values()) == pytest.approx(r["ni_sh"], rel=1e-9)
                prev_t2 = r["t2"]
        if t2_share is None:
            # до квартала, в котором T2 впервые отходит от базы (2028К1: 560 против 500,3; надбавка — со второго
            # квартала 2028 года), строки — бит в бит книги без ключа: 2026 и 2027 годы; ЧПД 2028 года ниже на надбавку
            # вместе с её следом в капитале и балансе
            for a, b in zip(bare["cells"], res["cells"]):
                for i in (0, 1):
                    assert tuple(a["rows"][i][f] for f in ROW_FIELDS) == tuple(b["rows"][i][f] for f in ROW_FIELDS)
                    assert b["rows"][i]["sp"] == 0.0
                assert b["rows"][2]["sp"] > 0.0 and b["rows"][2]["nii"] < a["rows"][2]["nii"]
                # надбавка — процентный расход до налога: ЧПД и прибыль до налога ниже на неё (второй порядок — доход
                # на капитал, который она уменьшила внутри года)
                for field in ("nii", "pbt"):
                    gap = b["rows"][2][field] - a["rows"][2][field]
                    assert abs(gap + b["rows"][2]["sp"]) <= 0.1 * b["rows"][2]["sp"], (key(a), field, gap)
                assert b["v_ri"] < a["v_ri"], key(a)


# вне такта сервера: прогоны формы с постоянными частями
def test_kappa_of_the_fixed_block_is_lower_by_alpha(inputs):
    """Свойство 26 (М§7): у книги с постоянными частями и λ_F = 0 κ_20 блока меньше формулы без ключа на той же строке
    ровно на α_c, с обоими ключами долей — на χ_c + α_c; κ_11 прежний; DDM = RI в каждой клетке."""
    book, facts = inputs
    for keys in ({AT1: K1_YEAR_END}, {AT1: K1_YEAR_END, cm.T2_SHARE: T2_SHARE_MID}):
        res = cm.c_control_run(with_keys(with_keys(book, FIXED_LAM0), keys), facts)
        ctx = res["ctx"]
        bare_ctx = {**ctx, "at1": None, "t2_from": None}
        for c in res["cells"]:
            last = c["rows"][-1]
            excess = cm.c_terminal_excess(last, cm.c_bnum(ctx["B"], "valuation.terminal.excess_capital_multiple"))
            mine = cm.c_terminal_fixed_inputs(ctx, c, last, excess)
            old = cm.c_terminal_fixed_inputs(bare_ctx, c, last, excess)
            both = last["a1s"] + (last["t2s"] if ctx["t2_from"] is not None else 0.0)
            assert old["kappa"][cm.NORM_TOTAL] - mine["kappa"][cm.NORM_TOTAL] == pytest.approx(both, abs=EXACT)
            assert mine["kappa"][cm.NORM_BASE] == old["kappa"][cm.NORM_BASE]
            assert c["terminal_fixed"]["kappa_all"] == mine["kappa"]
            assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"])), key(c)


# вне такта сервера: лишние прогоны сетки формы образца — они идут в CI
def test_dividend_base_deducts_the_coupon_above_base(inputs, plain):
    """М§5.2: у формы с deduct_at1_after_tax: true база решения о дивиденде вычитает купон сверх базы года прибыли после
    налога, как купон якоря; при deduct_at1_after_tax: false — не вычитает."""
    book, facts = inputs
    res = cm.c_control_run(put(book, AT1, K1_BASE_100), facts)
    ctx = res["ctx"]
    assert cm.c_bget(ctx["B"], "dividends.policy.deduct_at1_after_tax") is True
    seen = 0
    for c in res["cells"][:4]:
        for year, d in c["decisions"].items():
            if d.get("kind") not in ("policy", "crisis_skip") or "base" not in d:
                continue
            i = next(i for i, p in enumerate(ctx["periods"]) if p["year"] == year)
            r = c["rows"][i]
            ni = sum(v for (yy, _), v in r["ni_q"].items() if yy == year) if ctx["periods"][i]["n"] == cm.QY else None
            if ni is None:
                continue
            tau = cm.c_traj_at(cm.c_bget(ctx["B"], "tax.statutory"), year, ctx["A"]["cpn_quarter"])
            want = ni - ctx["A"]["cpn_annual"] * (1.0 - tau) - r["cpn_new_net"]
            assert d["base"] == pytest.approx(want, rel=1e-12), (key(c), year)
            assert r["cpn_new_net"] > 0.0
            seen += 1
    assert seen
    loose = cm.c_control_run(put(put(book, AT1, K1_BASE_100), "dividends.policy.deduct_at1_after_tax", False), facts)
    d0 = loose["cells"][0]["decisions"]
    y = sorted(y for y, d in d0.items() if d.get("kind") == "policy")[1]
    i = next(i for i, p in enumerate(loose["ctx"]["periods"]) if p["year"] == y)
    assert d0[y]["base"] == pytest.approx(sum(v for (yy, _), v in loose["cells"][0]["rows"][i]["ni_q"].items()
                                              if yy == y), rel=1e-12)


# вне такта сервера: прогоны формы с нехваткой капитала
def test_recap_money_carries_the_at1_share(inputs):
    """Взнос у книги с ключом (М§4.14.1, §4.14.5 п. 3): в году решения после квартала ключа K20 окончательного шага выше,
    чем у того же шага без взноса, на прирост собственных средств за вычетом прироста вычета плюс α_c × (RWA′ − RWA); K11
    — без слагаемого доли; остаток недостатка после взноса — в допуске инварианта."""
    book, facts = inputs
    res = cm.c_control_run(put(with_keys(book, SHORT_Q4), AT1, {**K1_YEAR_END, "from": "2027Q1"}), facts)
    ctx = res["ctx"]
    y_set = cm.c_qper(ctx["anchor"], ctx["at1"]["from"] - 1)[0]
    keep = 1.0 - cm.c_bnum(ctx["B"], "capital.n20.fvoci_recognition")
    seen = 0
    for cell in res["cells"]:
        for year, made in cell["recaps"].items():
            if made["rec"] > 0.0:
                assert made["left"]["left"] <= LEFT_SHARE * made["rec"], (key(cell), year)
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
        assert st["a1s"] is not None
        without = cm._c_period(ctx, ident, st, i, made["div"])[1]
        with_it = cm._c_period(ctx, ident, st, i, made["div"], rec=made["rec"])[1]
        more_own = ((with_it["bv"] + with_it["dpreg"] - keep * with_it["R"])
                    - (without["bv"] + without["dpreg"] - keep * without["R"]))
        d_rwa = with_it["rwa"] - without["rwa"]
        assert d_rwa > 0.0
        assert with_it["k20"] - without["k20"] == pytest.approx(
            more_own - (with_it["ded20"] - without["ded20"]) + st["a1s"] * d_rwa, rel=1e-9, abs=1e-9)
        held = max(with_it["e_unaudited"], 0.0) - max(without["e_unaudited"], 0.0)
        assert with_it["k11"] - without["k11"] + held == pytest.approx(
            more_own - (with_it["ded11"] - without["ded11"]), rel=1e-9, abs=1e-9)
        seen += 1
    assert seen


# ============================================================================ квартальный проход (форма панели)

AT1_T = 60.0                # AT1 якоря формы панели (у фикстуры — 0): вход теста
CPN_T = 6.0                 # купон якоря, млрд ₽ в год
K1_T = {"enabled": True, "from": "2027Q4", "spread": 0.04, "base": "anchor"}


def facts_t_with_at1() -> dict:
    facts = cm.c_facts_bundle(FIXTURE_T / "facts")
    facts["balance"]["equity"]["at1"] = {"v": AT1_T, "calc": "вход теста"}
    facts["capital"]["at1"]["coupon_annual"] = {"v": CPN_T, "calc": "вход теста"}
    return facts


@pytest.fixture(scope="module")
def quarterly():
    book = json.loads((FIXTURE_T / "book.json").read_text(encoding="utf-8"))
    facts = facts_t_with_at1()
    keys = {AT1: K1_T, T2P: K2, cm.T2_SHARE: {"enabled": True, "from": "2027Q4"}}
    return book, facts, cm.c_control_run(with_keys(book, keys), facts)


# вне такта сервера: сетка формы панели с квартальным проходом — секунды
def test_quarterly_pass_holds_the_at1_share(quarterly):
    """Квартальный проход (форма панели, AT1 якоря подставлен): доля клетки — AT1_0 к RWA записанного шага квартала
    2027К3; в каждом квартале с q_α ряд AT1 — доля на RWA квартала (1e-12), раньше — факт якоря; проход кончает год на
    тех же капитале, RWA, AT1 и нормативе, что годовая строка (1e-8); тождества годовых строк держатся; надбавка —
    формулой по T2 кварталов прохода."""
    book, facts, res = quarterly
    ctx = res["ctx"]
    rule = ctx["at1"]
    q_alpha = rule["from"]
    for c in res["cells"]:
        alpha = c["rows"][-1]["a1s"]
        xs = [x for r in c["rows"] for x in r["quarters"]]
        before = next(x for x in xs if x["q"] == q_alpha - 1)
        assert alpha == AT1_T / before["rwa"], key(c)
        for x in xs:
            if x["q"] >= q_alpha:
                assert x["at1"] == pytest.approx(alpha * x["rwa"], rel=EXACT), (key(c), x["q"])
            else:
                assert x["at1"] == AT1_T
        prev_t2, prev_at1 = ctx["t2p"]["base"], AT1_T
        for r in c["rows"]:
            # купон сверх базы — по AT1 кварталов прохода (план года), на остаток конца прошлого квартала
            at1_path = [prev_at1] + [x["at1"] for x in r["quarters"]]
            for j, x in enumerate(r["quarters"]):
                y, q = cm.c_qper(ctx["anchor"], x["q"])
                want = (r["key_q"][j] + rule["spread"]) * (at1_path[j] - rule["base"]) * cm.c_q_len(y, q) / cm.DAYS_BASE
                assert r["cpn_new_q"][j] == pytest.approx(want, rel=1e-6, abs=1e-9), (key(c), x["q"])
            prev_at1 = r["quarters"][-1]["at1"]
            last = r["quarters"][-1]
            assert last["rwa"] == pytest.approx(r["rwa"], rel=1e-8)
            assert last["at1"] == pytest.approx(r["at1"], rel=1e-8)
            assert abs(last["n20"] - r["n20"]) <= 1e-8 and abs(last["n11"] - r["n11"]) <= 1e-8
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
            ends = [prev_t2] + [x["t2"] for x in r["quarters"]]
            for j, x in enumerate(r["quarters"]):
                y, q = cm.c_qper(ctx["anchor"], x["q"])
                want = ctx["t2p"]["spread"] * (ends[j] - ctx["t2p"]["base"]) * cm.c_q_len(y, q) / cm.DAYS_BASE
                assert r["sp_q"][j] == pytest.approx(want, rel=1e-6, abs=1e-9), (key(c), x["q"])
            prev_t2 = r["quarters"][-1]["t2"]


# вне такта сервера: две сетки формы панели
def test_quarterly_off_keys_are_the_sample_branch(quarterly):
    """Квартальный проход: enabled: false и none — ряды кварталов, оценка и точка формы панели бит в бит книги без ключей."""
    book, facts, _ = quarterly
    bare = cm.c_control_run(book, facts)
    off = cm.c_control_run(with_keys(book, OFF_FULL), facts)
    assert values_of(off) == values_of(bare)
    assert [[x["n20"] for r in c["rows"] for x in r["quarters"]] for c in off["cells"]] == [
        [x["n20"] for r in c["rows"] for x in r["quarters"]] for c in bare["cells"]]


# ============================================================================ сверка с ядром (в момент теста)


FORMS = {"k1-2029Q1": lambda book: put(book, AT1, K1_YEAR_END),
         "k1-2028Q3": lambda book: put(book, AT1, K1_MID),
         "k1-first": lambda book: put(book, AT1, K1_FIRST),
         "k1-last-quarter": lambda book: put(book, AT1, {**K1_YEAR_END, "from": "2036Q4"}),
         "k1-base-100": lambda book: put(book, AT1, K1_BASE_100),
         "k1-spread-0": lambda book: put(book, AT1, {**K1_MID, "spread": 0.0}),
         "k1-no-payout": lambda book: put(with_keys(book, NO_PAYOUT), AT1, K1_MID),
         "k1-lam0": lambda book: put(with_keys(book, FIXED_LAM0), AT1, K1_YEAR_END),
         "k1-t2share": lambda book: with_keys(book, {AT1: K1_MID, cm.T2_SHARE: T2_SHARE_MID}),
         "k1-recap-q4": lambda book: put(with_keys(book, SHORT_Q4), AT1, {**K1_YEAR_END, "from": "2027Q1"}),
         "k2-trajectory": lambda book: put(put(book, cm.T2_TRAJ, TRAJ_STEPS), T2P, K2),
         "k2-t2share": lambda book: with_keys(book, {T2P: K2, cm.T2_SHARE: T2_SHARE_MID}),
         "k2-base-number": lambda book: put(put(book, cm.T2_TRAJ, TRAJ_STEPS), T2P, {**K2, "base": 450.0}),
         "k3": lambda book: put(put(book, "equity.other_movements", OM_PATH), OM, "flat_rub"),
         "k3-lam0": lambda book: with_keys(put(book, "equity.other_movements", OM_PATH), {**FIXED_LAM0, OM: "flat_rub"}),
         "all": lambda book: with_keys(put(put(book, cm.T2_TRAJ, TRAJ_STEPS), "equity.other_movements", OM_PATH),
                                       {AT1: K1_MID, T2P: K2, OM: "flat_rub", cm.T2_SHARE: T2_SHARE_MID}),
         "all-recap-lam0": lambda book: with_keys(put(book, "equity.other_movements", OM_PATH),
                                                  {**SHORT_Q4, **FIXED_LAM0, AT1: {**K1_YEAR_END, "from": "2027Q1"},
                                                   T2P: K2, OM: "flat_rub", cm.T2_SHARE: T2_SHARE_MID}),
         "off": lambda book: with_keys(book, OFF_FULL)}


@pytest.mark.ci_only
@pytest.mark.parametrize("form", list(FORMS))
def test_control_matches_core_with_the_pass8_keys(inputs, form):
    """Форма образца с ключами восьмого прохода против ядра (чёрный ящик: запуск и поля результата) — прежние строки в
    прежних допусках М§17. Расхождение — находка, а не повод подогнать контрольную модель."""
    book, facts = inputs
    ready = FORMS[form](book)
    run = tcd._core_run(ready, FIXTURE / "facts")
    ctl = cm.c_control_run(ready, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    assert not tcm.exact_match(run, ctl), "V0 слоёв совпали с ядром до 1e-9 — общий код"


def write_facts_t_with_at1(where) -> object:
    """Каталог фактов формы панели с AT1 якоря и купоном — копия фикстуры с подменой двух узлов (вход ядру)."""
    import shutil
    target = where / "facts"
    shutil.copytree(FIXTURE_T / "facts", target)
    for name, dotted, value in (("balance.json", ("equity", "at1"), AT1_T), ("capital.json", ("at1", "coupon_annual"), CPN_T)):
        path = target / name
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc[dotted[0]][dotted[1]] = {"v": value, "calc": "вход теста"}
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return target


@pytest.mark.ci_only
def test_control_matches_core_on_the_quarterly_form(quarterly, tmp_path):
    """Фикстура core_t (квартальный календарь, рост ограничен капиталом, множитель плотности режима) с AT1 якоря и
    ключами против ядра — в допусках М§17."""
    book, facts, ctl = quarterly
    ready = with_keys(book, {AT1: K1_T, T2P: K2, cm.T2_SHARE: {"enabled": True, "from": "2027Q4"}})
    run = tcd._core_run(ready, write_facts_t_with_at1(tmp_path))
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)


@pytest.mark.ci_only
def test_pass8_keys_against_core_as_a_black_box(inputs, plain):
    """Ядро — чёрный ящик: enabled: false и none дают у ядра оценку книги без ключей; каждый ключ двигает точку у двух
    моделей в одну сторону и на близкую величину; книги с ключами вне правил (№ 31–33) отвергают обе модели."""
    book, facts = inputs
    bare = tcd._core_run(book, FIXTURE / "facts")
    for keys in (OFF_KEYS, OFF_FULL):
        run = tcd._core_run(with_keys(book, keys), FIXTURE / "facts")
        assert (run.point, run.low, run.high) == (bare.point, bare.low, bare.high)
    stepped, moved = put(book, cm.T2_TRAJ, TRAJ_STEPS), put(book, "equity.other_movements", OM_PATH)
    for ready, base in ((put(book, AT1, K1_MID), book), (put(stepped, T2P, K2), stepped),
                        (put(moved, OM, "flat_rub"), moved)):
        mine = cm.c_control_run(ready, facts)["point"] - cm.c_control_run(base, facts)["point"]
        theirs = tcd._core_run(ready, FIXTURE / "facts").point - tcd._core_run(base, FIXTURE / "facts").point
        assert mine * theirs > 0.0 and abs(mine - theirs) <= tcm.TOL_VALUE * abs(bare.point), (mine, theirs)
    book_mod = importlib.import_module("model.book")
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    for path, bad in ((AT1, {"enabled": True, "from": "2029Q1", "spread": 0.04}),
                      (AT1, {"enabled": True, "from": "2026Q2", "spread": 0.04, "base": "anchor"}),
                      (AT1, {"enabled": False, "from": "2029Q1", "spread": 0.04, "base": -1.0}),
                      (AT1, {"enabled": True, "from": "2029Q1", "spread": None, "base": "anchor"}),
                      (T2P, {"enabled": True, "base": "anchor"}), (T2P, {"enabled": "yes", "spread": 0.02, "base": 0}),
                      (OM, "growing")):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(put(book, path, bad), facts)
        with pytest.raises(Exception) as refused:
            book_mod.book_from_dict(put(book, path, bad), facts=core_facts)
        assert type(refused.value).__name__ == "BookError", (path, bad, refused.value)
