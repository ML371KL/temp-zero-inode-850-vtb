# -*- coding: utf-8 -*-
"""Контрольная модель, девятый проход ядра (docs/MODEL.md §4.8, §4.9, §5.2, §5.7.3, §7, §17): разрыв налога по правилу
(tax.structure {enabled, bond_rate, bond_scale, other_pp, coupon_deductible}) и купон добавочного капитала якоря по ставке
своего мира (capital.at1_coupon {enabled, fixed, floating, spread}).

* Пример приложения M методики (машинная копия tests/fixtures/core_pass9/example.json): контрольная модель подставляет
  входы примера в свои рабочие функции — правила ключей, налог квартала по правилу, экономию купона, маржинальную ставку,
  купон якоря квартала купона и года T + 1, купон сверх базы, базу дивиденда, оценку клетки с терминалом, ставку
  балансирующих статей после налога и блок постоянных частей — и получает его числа до 1e-9 (М§17): M.1 — налог четырёх
  кварталов (убыточный и квартал купона) и рядом без ключа, M.2 — купон якоря (квартал купона, год якоря, терминал), M.3 —
  база дивиденда и тождество свойства 35, M.4 — терминал (избыток, недостаток, убыток года L, I_F в обеих ветвях), M.5 —
  сверка якоря на фактах ВТБ, M.6 — случаи схемы (точно).
* Свойства своего счёта на фикстурах формы образца (tests/fixtures/core — годовая ветвь; AT1 якоря 150, купон 9,7 в
  четвёртом квартале, база дивиденда вычитает купон) и формы панели (tests/fixtures/core_t — квартальный проход капитала;
  AT1 якоря и купон подставляет тест) с ключами, подставленными тестом: без ключей и при enabled: false — прежние числа
  бит в бит; налог каждого квартала профиля — правилом по рядам строки, налог года — сумма кварталов, при прибыли во всех
  кварталах — правило на годовых строках; в убыточном квартале — без прочих разниц, непрерывно в нуле; ряд ставки —
  маржинальная; CI и база дивиденда вычитают купон целиком; купон якоря — по средней ключевой своего мира за четыре
  квартала купона (кварталы не позже якоря — ключевая квартала якоря), за T — по ключевой последнего квартала сетки;
  терминал — строками М§7 (обе ветви избытка, блок постоянных частей ставками после налога в обеих ветвях y_m).
* Контрольные случаи сверх сетки книги (М§17): bond_scale: 0, постоянный other_pp и coupon_deductible: false — налог —
  доля PBT; путь мира с ключевой, меняющейся в последнем году сетки, — купон года T + 1 по ставке квартала Q; floating: 0 с
  fixed, равным слоту, — бит в бит книги без ключа купона.
* Сверка с ядром (метка ci_only; ядро импортируется только в момент теста) — прежние строки в прежних допусках М§17 и
  годовой налог клетки: в допуске строк ОПУ между моделями и до 1e-6 правилом на строках ядра.

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
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass9" / "example.json"
EXAMPLE_TOL = 1e-9          # пример приложения M: формулы без шага, одно определение (М§17)
EXACT = 1e-12               # своё свойство: те же действия над теми же числами
CORE_TAX_TOL = 1e-6         # налог года ядра правилом на его же строках (М§17)
put, with_keys, close, key = tcd.put, tcd.with_keys, tcd.close, tcd.key
values_of, rows_of = tcd.values_of, tcd.rows_of
NO_PAYOUT = tcd.NO_PAYOUT
TAX, AT1C, GAP = cm.TAX_STRUCTURE, cm.AT1_COUPON, cm.TAX_GAP
AT1, T2P, OM = cm.AT1_SHARE, cm.T2_PREMIUM, cm.OM_TERMINAL
# Ключи форм (входы теста).
K1 = {"enabled": True, "bond_rate": 0.2, "bond_scale": 1.2, "other_pp": 0.02, "coupon_deductible": True}
K1_ZERO = {"enabled": True, "bond_rate": 0.2, "bond_scale": 0.0, "other_pp": -0.007, "coupon_deductible": False}
K2 = {"enabled": True, "fixed": 4.0, "floating": 40.0, "spread": 0.05}
OFF9 = {TAX: {"enabled": False}, AT1C: {"enabled": False}}
OFF9_FULL = {TAX: {**K1, "enabled": False}, AT1C: {**K2, "enabled": False}}
OFF9_NULL = {TAX: {"enabled": False, "bond_rate": None, "bond_scale": None, "other_pp": None, "coupon_deductible": None},
             AT1C: {"enabled": False, "fixed": None, "floating": None, "spread": None}}
AT1_MID = {"enabled": True, "from": "2028Q3", "spread": 0.04, "base": "anchor"}         # ключ восьмого прохода
K8_ALL = {AT1: AT1_MID, T2P: {"enabled": True, "spread": 0.025, "base": "anchor"}, OM: "flat_rub",
          "equity.other_movements": {"LT": -2.0}}
# Постоянные части и λ_F = 0 на форме образца — как в tests/test_control_fixed_parts.py (входы теста).
FIXED_LAM0 = {cm.FIXED_GROWTH: 0.0, "volumes.other_assets_fixed": 1200.0,
              "capital.rwa.density." + cm.OAF_DENSITY: 0.8}
SHORT_BUFFER = {"dividends.policy.threshold": 0.0, "capital.mgmt_buffer.n20_0": 0.03, "capital.mgmt_buffer.n1_1": 0.03}
BIG_LOSS = {"regimes.crisis.one_off_loss.amount": -2000.0}      # квартал убытка в клетках кризиса (вход теста)
# путь ключевой мира H с ключевой квартала якоря (2026H1 — полугодие квартала якоря 2026К2), отличной от первого
# прогнозного, и с ключевой, меняющейся в последнем году сетки (2036H2 на 0,5 п.п. ниже 2036H1): k̄ года якоря и купон года
# T + 1 различают правило и его мутации; у траектории мира — ключи полугодий (схема ядра). Сдвиг в последнем году — малый:
# скачок ключевой на п.п. внутри последнего года годовой шаг в терминале не воспроизводит (docs/CONTROL-MODEL.md §8)
KEY_MOVES = {"2026H1": 0.16, "2036H2": 0.10}


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def tax_rule_of(fields: dict) -> dict:
    """Правило ключа tax.structure рабочей функцией на книге примера."""
    return cm.c_tax_structure_rule({"tax": {"structure": {"enabled": True, **fields}}})


def coupon_rule_of(fields: dict) -> dict:
    return cm.c_at1_coupon_rule({"capital": {"at1_coupon": {"enabled": True, **fields}}})


# ============================================================================ пример приложения M


@pytest.mark.tact
def test_appendix_m1_tax_of_the_quarter():
    """M.1: налог квартала — τ_stat × PBT + o × max(PBT, 0) − (τ_stat − τ_b) × ζ × IIS − δ_c × τ_stat × CPN: 22,2; 27,36;
    −15,28 (убыток — без o, льгота остаётся рублями; при PBT = ±ε налог → −5,28 с обеих сторон); 18,408767 в квартале
    купона (экономия 13,871233); ряд ставки — 0,27 при прибыли, 0,25 при убытке; разрыв квартала — правило книги
    дословно; CI — NI_sh минус купон целиком; без ключа — (τ + gap) × PBT и купон × (1 − τ) в CI; год — суммы."""
    doc = example()["M1"]
    inp = doc["inputs"]
    rule = tax_rule_of({"bond_rate": inp["bond_rate"], "bond_scale": inp["bond_scale"], "other_pp": inp["other_pp"],
                        "coupon_deductible": inp["coupon_deductible"]})
    tau, nci, gap = inp["tau_stat"], inp["nci_share"], inp["effective_gap_off"]
    year = {"tax": 0.0, "ni_sh": 0.0, "ci": 0.0, "ni_sh_off": 0.0, "ci_off": 0.0, "pbt": 0.0}
    for q, want in doc["quarters"].items():
        pbt, iis, cpn = inp["pbt"][q], inp["iis"][q], inp["coupon"][q]
        saving = cm.c_tax_coupon(rule, tau, cpn)
        tax = cm.c_tax_rule(rule, tau, pbt, iis, saving)
        ni_sh = (pbt - tax) * (1.0 - nci)
        ci = ni_sh - cpn * (1.0 - 0.0)                  # τ_cpn = 0: купон целиком
        close(saving, want["tax_coupon"], f"q{q}: экономия купона")
        close(tax, want["tax"], f"q{q}: налог")
        close(cm.c_tax_marginal(rule, tau, pbt), want["tau_eff"], f"q{q}: ряд ставки")
        close(pbt - tax, want["ni"], f"q{q}: NI")
        close(ni_sh, want["ni_sh"], f"q{q}: NI_sh")
        close(ci, want["ci"], f"q{q}: CI")
        tax_off = (tau + gap) * pbt
        ni_off = (pbt - tax_off) * (1.0 - nci)
        close(tax_off, want["tax_off"], f"q{q}: налог без ключа")
        close(ni_off, want["ni_sh_off"], f"q{q}: NI_sh без ключа")
        close(ni_off - cpn * (1.0 - tau), want["ci_off"], f"q{q}: CI без ключа")
        if pbt > 0.0:
            close(tax / pbt, want["etr"], f"q{q}: ставка квартала")
            rule_gap = (-(tau - rule["bond_rate"]) * rule["bond_scale"] * iis / pbt - tau * cpn / pbt + rule["other_pp"])
            close(tax / pbt - tau, rule_gap, f"q{q}: разрыв — правило книги")
            close(rule_gap, want["gap_rule"], f"q{q}: разрыв правила")
        for name, value in (("tax", tax), ("ni_sh", ni_sh), ("ci", ci), ("ni_sh_off", ni_off),
                            ("ci_off", ni_off - cpn * (1.0 - tau)), ("pbt", pbt)):
            year[name] += value
    for name in ("tax", "ni_sh", "ci", "ni_sh_off", "ci_off", "pbt"):
        close(year[name], doc["year"][name], f"год: {name}")
    close(year["tax"] / year["pbt"], doc["year"]["etr"], "год: ставка")
    # непрерывность в нуле: квартал 3 (IIS 88) при PBT = ±ε
    eps = 1e-9
    up, down = (cm.c_tax_rule(rule, tau, x, inp["iis"]["3"], 0.0) for x in (eps, -eps))
    assert abs(up - down) <= 1e-9 and up == pytest.approx(-(tau - rule["bond_rate"]) * rule["bond_scale"] * 88.0, abs=1e-8)
    close(up, -5.28, "PBT → 0: налог −5,28", 1e-8)


@pytest.mark.tact
def test_appendix_m2_anchor_coupon_by_the_key_of_its_world():
    """M.2: k̄_4 = 0,145, купон якоря квартала купона 51,2, купон сверх базы 4,284932, ряд coupon 55,484932; кварталов 1–3 —
    ноль; год якоря (якорь 2027К2, купон в 2027К4): кварталы не позже якоря — ключевая квартала якоря, k̄ = 0,1425, купон
    50,8; терминал — ключевая квартала Q: 48,8 (средняя года дала бы 51,2), CPN_T+1 = 69,2; без ключа — слот при любой
    ключевой; floating: 0 и fixed = слоту — слот."""
    doc = example()["M2"]
    inp = doc["inputs"]
    rule = coupon_rule_of({"fixed": inp["fixed"], "floating": inp["floating"], "spread": inp["spread"]})
    anchor = (2026, 4)
    quarters = {k: cm.c_qper(anchor, int(k)) for k in inp["key"]}
    path = {f"{y}Q{q}": inp["key"][k] for k, (y, q) in quarters.items()}
    keys = [inp["key"][str(k)] for k in range(1, 5)]
    ctx = {"A": {"cpn_quarter": inp["coupon_quarter"], "cpn_annual": None}, "at1c": rule, "anchor": anchor,
           "B": {"worlds": {"W": {"key_rate": path}}}, "wv": {"W": [{"key_rate": keys}]}}
    y4, q4 = quarters["4"]
    close(cm.c_coupon_kbar(ctx, "W", y4, q4), doc["kbar_q4"], "k̄ квартала купона")
    close(cm.c_anchor_coupon(ctx, "W", y4, q4), doc["coupon_anchor_q4"], "купон якоря квартала купона")
    for k in ("1", "2", "3"):
        assert cm.c_anchor_coupon(ctx, "W", *quarters[k]) == 0.0, k
    new = cm.c_at1_coupon_new(inp["key"]["4"] + inp["at1_spread"], 100.0 + inp["at1_over_base_q3"], 100.0,
                              inp["days"]["4"])
    close(new, doc["coupon_new_q4"], "купон сверх базы")
    close(cm.c_anchor_coupon(ctx, "W", y4, q4) + new, doc["coupon_q4"], "ряд coupon")
    # год якоря: якорь 2027К2 (ключевая 0,15), купон 2027К4 = q 2
    case = inp["anchor_year_case"]
    anchor_y = (2027, 2)
    path_y = {f"{y}Q{q}": v for (y, q), v in ((cm.c_qper(anchor_y, int(k)), v) for k, v in case["key"].items())}
    ctx_y = {**ctx, "anchor": anchor_y, "B": {"worlds": {"W": {"key_rate": path_y}}}}
    yc, qc = cm.c_qper(anchor_y, case["coupon_q"])
    close(cm.c_coupon_kbar(ctx_y, "W", yc, qc), doc["anchor_year_kbar"], "k̄ года якоря")
    close(cm.c_anchor_coupon(ctx_y, "W", yc, qc), doc["anchor_year_coupon"], "купон года якоря")
    # терминал: ключевая последнего квартала сетки, не средняя года
    t1 = cm.c_anchor_coupon_t1(ctx, "W")
    close(t1, doc["coupon_anchor_T1"], "купон якоря T + 1")
    assert abs(cm.c_at1_coupon_formula(rule, sum(keys) / len(keys)) - t1) > 1.0
    close(t1 + (inp["key"]["4"] + inp["at1_spread"]) * inp["at1_over_base_Q"], doc["coupon_T1"], "CPN_T+1")
    # без ключа — слот; floating 0 и fixed = слоту — тот же слот
    slot = 51.0
    bare = {**ctx, "at1c": None, "A": {"cpn_quarter": 4, "cpn_annual": slot}}
    assert cm.c_anchor_coupon(bare, "W", y4, q4) == slot and cm.c_anchor_coupon_t1(bare, "W") == slot
    flat = {**ctx, "at1c": coupon_rule_of({"fixed": slot, "floating": 0.0, "spread": inp["spread"]})}
    assert cm.c_anchor_coupon(flat, "W", y4, q4) == slot and cm.c_anchor_coupon_t1(flat, "W") == slot


def m3_ctx(rule, coupon_rule=None) -> dict:
    doc = example()
    inp = doc["M2"]["inputs"]
    path = {f"{y}Q{q}": v for (y, q), v in ((cm.c_qper((2026, 4), int(k)), v) for k, v in inp["key"].items())}
    book = {"dividends": {"policy": {"base_window_quarters": cm.QY, "deduct_at1_after_tax": True}},
            "tax": {"statutory": doc["M1"]["inputs"]["tau_stat"]}, "worlds": {"W": {"key_rate": path}}}
    return {"B": book, "A": {"cpn_quarter": cm.QY, "cpn_annual": doc["M2"]["coupon_anchor_q4"]}, "anchor": (2026, 4),
            "tax": rule, "at1c": coupon_rule}


@pytest.mark.tact
def test_appendix_m3_dividend_base():
    """M.3: база дивиденда (deduct_at1_after_tax: true) рабочей функцией базы решения — с ключом Σ NI_sh − CPN_Y =
    198,460740 (купон целиком: экономия уже в NI_sh), без ключа Σ NI_sh − CPN_Y × (1 − τ) = 201,586301; тождество свойства
    35 — база без экономии в прибыли минус τ × CPN_Y × nci; купон якоря ключом купона (51,2 по ключевой мира) — та же база."""
    doc = example()
    m1, m2, m3 = doc["M1"], doc["M2"], doc["M3"]
    inp = m1["inputs"]
    rule = tax_rule_of({k: inp[k] for k in ("bond_rate", "bond_scale", "other_pp", "coupon_deductible")})
    tau, nci = inp["tau_stat"], inp["nci_share"]
    quarters = {int(q): cm.c_qper((2026, 4), int(q)) for q in m1["quarters"]}
    k_last = max(quarters)
    for ctx, ni_field, cpn_tau, want in ((m3_ctx(rule), "ni_sh", 0.0, m3["base_k1"]),
                                         (m3_ctx(None), "ni_sh_off", tau, m3["base_off"]),
                                         (m3_ctx(rule, coupon_rule_of({k: m2["inputs"][k] for k in
                                                                       ("fixed", "floating", "spread")})),
                                          "ni_sh", 0.0, m3["base_k1"])):
        ni_all = {quarters[int(q)]: v[ni_field] for q, v in m1["quarters"].items()}
        new = {quarters[k_last]: m2["coupon_new_q4"] * (1.0 - cpn_tau)}       # купон сверх базы после τ_cpn
        base = cm.c_div_base(ctx, ni_all, k_last, new, "W") * cm.QY
        close(base, want, f"база дивиденда ({ni_field}, ключ купона {ctx['at1c'] is not None})")
    cpn = m3["coupon_year"]
    without_saving = m1["year"]["ni_sh"] - tau * cpn * (1.0 - nci)
    close(without_saving - cpn * (1.0 - tau) - tau * cpn * nci, m3["base_k1_identity"], "тождество свойства 35")
    close(m3["base_k1_identity"], m3["base_k1"], "тождество — та же база")


def m4_value(case: dict, inp: dict, keyed: bool) -> dict:
    """Синтетическая клетка M.4 — рабочей функцией оценки клетки (_c_value_cell): одна строка конца сетки (2027К4) с
    избытком X_T (x20 = (N20 − req20) × RWA, множитель 1), запасом H*_Q (минимум ликвидности — ноль: H* = бумаги +
    ликвидность), добором опта WT_Q, PBT_L и IIS_L примера; купон года T + 1 — 69,2 ключами купона и доли AT1 (M.2)."""
    m2 = example()["M2"]["inputs"]
    tax = example()["M1"]["inputs"]
    rule = tax_rule_of({k: tax[k] for k in ("bond_rate", "bond_scale", "other_pp", "coupon_deductible")})
    k_t = 0.15
    book = {"valuation": {"terminal": {"excess_capital_multiple": 1.0, "fade": 0.5, "real_growth": 0.0}},
            "worlds": {"W": {"lt_inflation": inp["g_t"]}}, "pnl": {"nci_share": tax["nci_share"]},
            "volumes": {"liquid_min_share": 0.0, "securities_share_of_liquid": inp["sec"]},
            "tax": {"statutory": tax["tau_stat"]}}
    base = 100.0
    ctx = {"B": book, "A": {"BV": 500.0, "cpn_quarter": cm.QY, "cpn_annual": None, "AT1": base},
           "clock": {"p0": 0, "pos": 0.0, "t_start": {0: 0.0}, "tau_end": {0: 1.0 / cm.QY}},
           "periods": [{"year": 2027, "quarters": [cm.QY], "n": 1}],
           "disc": {"W": lambda tau: (1.0 + k_t) ** (-tau)}, "recap": None, "lam_f": None, "t2p": None, "om": None,
           "at1": {"from": 1, "spread": m2["at1_spread"], "base": base},
           "at1c": coupon_rule_of({k: m2[k] for k in ("fixed", "floating", "spread")}),
           "tax": rule if keyed else None, "wv": {"W": [{"key_rate": [m2["key"]["4"]]}]}}
    rwa = 1000.0
    last = {"ci_q": [0.0], "ci": 0.0, "div_list": [], "rec_list": [], "bv": 500.0, "dpreg": 0.0, "rwa": rwa,
            "req20": 0.1, "req11": 0.05, "n20": 0.1 + case["x_t"] / rwa, "n11_star": 1.0,
            "securities": inp["sec"] * case["h_star"], "liquidity": (1.0 - inp["sec"]) * case["h_star"],
            "assets": 1000.0, "wholesale_extra": case["wt"], "y_sec_end": inp["y_sec"], "y_liq_end": inp["y_liq"],
            "c_wh_end": inp["c_wholesale"], "pbt": case["pbt_l"], "iis": inp["iis_l"], "tau_stat": tax["tau_stat"],
            "tau_eff": (cm.c_tax_marginal(rule, tax["tau_stat"], case["pbt_l"]) if keyed
                        else tax["tau_stat"] + tax["effective_gap_off"]),
            "key_q": [m2["key"]["4"]], "at1": base + m2["at1_over_base_Q"], "a1s": None}
    return cm._c_value_cell(ctx, {"world": "W", "regime": "r", "scenario": "s"}, [last], {})


@pytest.mark.tact
def test_appendix_m4_terminal():
    """M.4: терминал по правилу рабочей функцией оценки клетки — избыток (A_X 30, Y_X 6,42, IIS_T+1 347,28, налог 74,6098,
    NI 325,82169, CI 256,62169), недостаток (A_X −15, деньги сверх добора опта ложатся в бумаги — льгота растёт), убыток
    года L (o не действует, льгота и экономия остаются рублями); без ключа — прежняя строка с τ_eff и купоном × (1 − τ);
    I_F — ставкой после налога в обеих ветвях y_m (0,08826 и 0,1095), без ключа — y_m × (1 − τ_eff)."""
    doc = example()["M4"]
    inp = doc["inputs"]
    for name in ("excess", "shortfall", "loss"):
        want = doc[name]
        on, off = m4_value(want, inp, True), m4_value(want, inp, False)
        close(on["x_t"], want["x_t"], f"{name}: X_T")
        close(on["h_star"], want["h_star"], f"{name}: H*")
        close(on["y_x"], want["y_x"], f"{name}: Y_X")
        close(on["cpn_t1"], inp["coupon_T1"], f"{name}: CPN_T+1")
        t = on["terminal_tax"]
        for mine, theirs in (("a_x", "a_x"), ("pbt_x", "pbt_x"), ("iis_t1", "iis_t1"), ("tax_t1", "tax_t1")):
            close(t[mine], want[theirs], f"{name}: {theirs}")
        close(on["ni_t1"], want["ni_t1"], f"{name}: NI_T+1")
        close(on["ci_t1"], want["ci_t1"], f"{name}: CI_T+1")
        assert "terminal_tax" not in off
        close(off["ni_t1"], want["ni_t1_off"], f"{name}: NI_T+1 без ключа")
        close(off["ci_t1"], want["ci_t1_off"], f"{name}: CI_T+1 без ключа")
        assert abs(on["v_ddm"] - on["v_ri"]) <= 1e-9 * max(1.0, abs(on["v_ri"])), name
    tax = example()["M1"]["inputs"]
    rule = tax_rule_of({k: tax[k] for k in ("bond_rate", "bond_scale", "other_pp", "coupon_deductible")})
    tau, nci = tax["tau_stat"], tax["nci_share"]
    block = {"binding": cm.NORM_TOTAL, "c": {cm.NORM_TOTAL: 0.0}, "kappa": {cm.NORM_TOTAL: 0.0}, "r_f": 0.0,
             "f_a": inp["d_f"]}
    y_bal = inp["sec"] * inp["y_sec"] + (1.0 - inp["sec"]) * inp["y_liq"]
    for name, wt, y_m in (("i_f_balancing", 0.0, y_bal), ("i_f_wholesale", 1.0, inp["c_wholesale"])):
        want = doc[name]
        y_tau = cm.c_terminal_y_after_tax(rule, tau, wt, inp["c_wholesale"], inp["sec"], inp["y_sec"], inp["y_liq"])
        close(y_tau, want["y_after_tax"], f"{name}: y^τ_m")
        blk = cm.c_terminal_fixed_block(block, 0.0, y_m, 0.0, nci, after_tax=y_tau)
        close(blk["i_f"], want["i_f"], f"{name}: I_F")
        close(blk["y_m_after_tax"], y_tau, f"{name}: ставка после налога в узле")
        old = cm.c_terminal_fixed_block(block, 0.0, y_m, tau + tax["effective_gap_off"], nci)
        close(old["i_f"], want["i_f_off"], f"{name}: I_F без ключа")
        assert "y_m_after_tax" not in old


@pytest.mark.tact
def test_appendix_m5_anchor_check_on_the_facts():
    """M.5: правило на фактах ВТБ — 2К2026 с ζ = 177,2 / 145,46 = 1,2182: разрыв −8,51 п.п. против факта −8,42; с ζ = 1 —
    −7,08; 6М2026 (доход по облигациям сверки 356 — строки целиком, ζ = 1): −6,13 против структурного −6,33 (факт −5,51
    минус непризнанный актив); o под ζ = 1 на окне 6М2026 — 0,74 п.п."""
    doc = example()["M5"]
    inp = doc["inputs"]
    q2, h1, tau = inp["q2"], inp["h1"], inp["tau_stat"]
    zeta = q2["ifrs_lines"] / q2["iis_core"]
    close(zeta, doc["zeta"], "ζ")
    for scale, field in ((zeta, "q2_gap_rule"), (1.0, "q2_gap_rule_zeta1")):
        rule = tax_rule_of({"bond_rate": inp["bond_rate"], "bond_scale": scale, "other_pp": inp["other_pp"],
                            "coupon_deductible": True})
        tax = cm.c_tax_rule(rule, tau, q2["pbt"], q2["iis_core"], cm.c_tax_coupon(rule, tau, q2["coupon"]))
        close(tax / q2["pbt"] - tau, doc[field], field)
    close(q2["tax"] / q2["pbt"] - tau, doc["q2_gap_fact"], "факт 2К2026")
    rule1 = tax_rule_of({"bond_rate": inp["bond_rate"], "bond_scale": 1.0, "other_pp": inp["other_pp"],
                         "coupon_deductible": True})
    tax = cm.c_tax_rule(rule1, tau, h1["pbt"], h1["bond_income"], cm.c_tax_coupon(rule1, tau, h1["coupon"]))
    close(tax / h1["pbt"] - tau, doc["h1_gap_rule"], "правило 6М2026")
    close(h1["tax"] / h1["pbt"] - tau, doc["h1_gap_fact"], "факт 6М2026")
    close(h1["tax"] / h1["pbt"] - tau - h1["dta"], doc["h1_gap_fact_structural"], "структурный 6М2026")
    close(-(tau - inp["bond_rate"]) * h1["bond_income"] / h1["pbt"], doc["h1_bond_pp"], "облигации 6М2026")
    close(-tau * h1["coupon"] / h1["pbt"], doc["h1_coupon_pp"], "купон 6М2026")
    o1 = inp["other_pp"] - (tau - inp["bond_rate"]) * (h1["bond_income"] - 2.0 * q2["iis_core"]) / h1["pbt"]
    close(o1, doc["o_core_zeta1"], "o под ζ = 1")


def schema_book(extra: dict, axes=None, variants=None) -> dict:
    book = {"tax": {"statutory": 0.25, "effective_gap": -0.05}, "capital": {}}
    for dotted, value in extra.items():
        book = put(book, dotted, value)
    if axes is not None:
        book = put(book, "valuation.uncertainty.axes", axes)
    if variants is not None:
        book = put(book, "valuation.reference_variants", variants)
    return book


def schema_ok(book: dict) -> bool:
    try:
        cm.c_tax_structure_rule(book)
        cm.c_at1_coupon_rule(book)
    except cm.ControlInputError:
        return False
    return True


@pytest.mark.tact
def test_appendix_m6_schema_cases():
    """M.6 (прил. A № 34–35) — точно: годные и негодные ключи примера; ключ включён и ось на tax.effective_gap — отказ (и в
    off_band_axes); подмена варианта на нём без tax.structure.enabled: false — отказ, с ним (путём или объектом) — годна;
    ключ выключен — ось на числе разрыва годна; при включённом ключе число разрыва может быть null."""
    doc = example()["M6"]
    for case in doc["valid"]:
        assert schema_ok(schema_book(case)), case
    for case in doc["invalid"]:
        case = dict(case)
        axis_on = case.pop("axis_on", None)
        axes = [{"name": "разрыв", "kind": "value", "paths": [axis_on], "low": -0.08, "high": -0.03}] if axis_on else None
        assert not schema_ok(schema_book(case, axes=axes)), case
    on = {TAX: {**K1}}
    gap_axis = [{"name": "разрыв", "kind": "value", "paths": [GAP], "low": -0.08, "high": -0.03}]
    assert not schema_ok(put(schema_book(on), "valuation.uncertainty.off_band_axes", gap_axis))
    assert schema_ok(schema_book({TAX: {"enabled": False, **{k: v for k, v in K1.items() if k != "enabled"}}},
                                 axes=gap_axis))
    assert schema_ok(schema_book(on, axes=[{"name": "o", "kind": "value", "paths": [TAX + ".other_pp"]}]))
    for variant, ok in (({"id": "a", "overrides": {GAP: -0.07}}, False),
                        ({"id": "b", "overrides": {TAX + ".enabled": False, GAP: -0.0334}}, True),
                        ({"id": "c", "overrides": {TAX: {"enabled": False}, GAP: -0.0334}}, True),
                        ({"id": "d", "overrides": {TAX + ".enabled": True, GAP: -0.0334}}, False),
                        ({"id": "e", "overrides": {TAX + ".other_pp": 0.03}}, True)):
        assert schema_ok(schema_book(on, variants=[variant])) is ok, variant
    assert schema_ok(put(schema_book(on), GAP, None))
    # поля вне формы и формат: число разрыва без ключа, выключатель — строго булево
    for bad in ({TAX: {"enabled": True, **{k: v for k, v in K1.items() if k != "enabled"}, "rate": 0.2}},
                {TAX: {**K1, "bond_rate": "0.2"}}, {TAX: {**K1, "other_pp": True}}, {TAX: {**K1, "bond_scale": None}},
                {TAX: {**K1, "coupon_deductible": 1}}, {TAX: [K1]}, {TAX: {"enabled": 1}},
                {AT1C: {**K2, "spread": None}}, {AT1C: {**K2, "fixed": -0.1}}, {AT1C: {"enabled": False, "floating": -5}},
                {AT1C: {"enabled": False, "spread": "0.05"}}, {AT1C: {**K2, "cap": 1}}):
        assert not schema_ok(schema_book(bad)), bad


# ============================================================================ свойства на форме образца (годовая ветвь)


@pytest.fixture(scope="module")
def inputs():
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8")), cm.c_facts_bundle(FIXTURE / "facts")


@pytest.fixture(scope="module")
def plain(inputs):
    return cm.c_control_run(*inputs)


@pytest.fixture(scope="module")
def taxed(inputs):
    """Ключ налога и ключ доли добавочного капитала восьмого прохода: купон клетки — якоря и сверх базы."""
    book, facts = inputs
    return cm.c_control_run(with_keys(book, {TAX: K1, AT1: AT1_MID}), facts)


@pytest.fixture(scope="module")
def both(inputs):
    """Оба ключа девятого прохода, ключ доли добавочного капитала и путь ключевой мира H с ключом полугодия квартала якоря."""
    book, facts = inputs
    return cm.c_control_run(with_keys(book, {TAX: K1, AT1C: K2, AT1: AT1_MID,
                                             "worlds.H.key_rate": {**book["worlds"]["H"]["key_rate"], **KEY_MOVES}}),
                            facts)


def tax_by_hand(rule: dict, tau: float, pbt: float, iis: float, coupon: float) -> float:
    """Налог правилом М§4.8 своей арифметикой теста."""
    other = rule["other_pp"] * pbt if pbt > 0.0 else 0.0
    saving = tau * coupon if rule["deductible"] else 0.0
    return tau * pbt + other - (tau - rule["bond_rate"]) * rule["bond_scale"] * iis - saving


def assert_tax_rows(res: dict, *, need_loss: bool = False) -> dict:
    """Свойство 32 по рядам строк: налог кварталов профиля — правилом, год — сумма, при прибыли во всех кварталах —
    правило на годовых строках; IIS — ставка книги бумаг между началом и концом периода на среднем остатке бумаг;
    купон — якоря в квартале купона и сверх базы; ряд ставки — маржинальная; NI, CI (купон целиком) и тождество капитала."""
    ctx = res["ctx"]
    B, A, rule = ctx["B"], ctx["A"], ctx["tax"]
    nci = cm.c_bnum(B, "pnl.nci_share")
    ssl = cm.c_bnum(B, "volumes.securities_share_of_liquid")
    seen = {"rows": 0, "loss_quarters": 0, "coupon_quarters": 0}
    for c in res["cells"]:
        bv_prev, y_prev = A["BV"], A["rate0"][cm.SECURITIES]
        for p, r in zip(ctx["periods"], c["rows"]):
            taus = [cm.c_traj_at(cm.c_bget(B, "tax.statutory"), p["year"], q) for q in p["quarters"]]
            for j, q in enumerate(p["quarters"]):
                cpn = (r["cpn_anchor"] if "cpn_anchor" in r else r["cpn"]) if q == A["cpn_quarter"] else 0.0
                want_cpn = cpn + (r["cpn_new_q"][j] if "cpn_new_q" in r else 0.0)
                assert r["coupon_q"][j] == pytest.approx(want_cpn, rel=EXACT, abs=1e-12), (key(c), p["year"], q)
                want = tax_by_hand(rule, taus[j], r["pbt_q"][j], r["iis_q"][j], r["coupon_q"][j])
                assert r["tax_q"][j] == pytest.approx(want, rel=EXACT, abs=1e-9), (key(c), p["year"], q)
                assert r["tau_eff_q"][j] == taus[j] + (rule["other_pp"] if r["pbt_q"][j] > 0.0 else 0.0)
                assert r["tax_coupon_q"][j] == pytest.approx(taus[j] * r["coupon_q"][j] if rule["deductible"] else 0.0,
                                                             rel=EXACT, abs=1e-12)
                seen["loss_quarters"] += r["pbt_q"][j] <= 0.0
                seen["coupon_quarters"] += r["coupon_q"][j] > 0.0
            assert r["tax"] == pytest.approx(sum(r["tax_q"]), rel=EXACT, abs=1e-9)
            assert r["pbt"] == pytest.approx(sum(r["pbt_q"]), rel=1e-12, abs=1e-9)
            assert r["iis"] == pytest.approx(sum(r["iis_q"]), rel=1e-12)
            # IIS — ставка книги бумаг на средний остаток бумаг периода: ставка между началом и концом периода
            rate = r["iis"] / (ssl * r["la_avg"] * sum(r["days_q"]) / cm.DAYS_BASE)
            lo, hi = sorted((y_prev, r["y_sec_end"]))
            assert lo - 1e-12 <= rate <= hi + 1e-12, (key(c), p["year"], rate, lo, hi)
            if min(r["pbt_q"]) > 0.0 and len(set(taus)) == 1:
                whole = tax_by_hand(rule, taus[0], r["pbt"], r["iis"], sum(r["coupon_q"]))
                assert r["tax"] == pytest.approx(whole, rel=1e-10), (key(c), p["year"])
            assert r["tau_eff"] == pytest.approx(sum(taus) / len(taus) + (rule["other_pp"] if r["pbt"] > 0.0 else 0.0),
                                                 rel=EXACT)
            assert r["tau_cpn"] == 0.0 and r["tax_coupon"] == pytest.approx(sum(r["tax_coupon_q"]), rel=EXACT, abs=1e-12)
            assert r["ni"] == pytest.approx(r["pbt"] - r["tax"] - r["ot"], rel=EXACT, abs=1e-9)
            assert r["ni_sh"] == pytest.approx(r["ni"] * (1.0 - nci), rel=EXACT, abs=1e-9)
            assert sum(r["ni_q"].values()) == pytest.approx(r["ni_sh"], rel=1e-10, abs=1e-9)
            assert r["ci"] == pytest.approx(r["ni_sh"] - r["cpn"] + r["oci"] + r["om"], rel=EXACT, abs=1e-9)
            assert r["cpn_net"] == pytest.approx(r["cpn"], rel=EXACT, abs=1e-12)
            assert r["bv"] == pytest.approx(bv_prev + r["ci"] - r["div"] + r.get("rec", 0.0), rel=1e-12)
            bv_prev, y_prev = r["bv"], r["y_sec_end"]
            seen["rows"] += 1
    assert seen["rows"] and seen["coupon_quarters"]
    if need_loss:
        assert seen["loss_quarters"], "вход теста: квартал с убытком в клетках кризиса"
    return seen


@pytest.mark.tact
def test_off_and_absent_keys_are_the_sample_branch(inputs, plain):
    """Без ключей и при enabled: false (с полями, без полей, с null в полях) — ряды, оценка и точка формы образца бит в бит;
    узла девятого прохода нет; полей ключа у строк нет; ключ купона с floating: 0 и fixed, равным слоту, — бит в бит
    (свойство 40); ключ налога с null в числе разрыва — тот же счёт, что с числом (число не читается)."""
    book, facts = inputs
    ctx = plain["ctx"]
    assert ctx["tax"] is None and ctx["at1c"] is None and "pass9" not in plain
    fields = ("tax", "ni", "ni_sh", "ci", "cpn", "cpn_net", "tau_eff", "bv")
    for keys in (OFF9, OFF9_FULL, OFF9_NULL):
        same = cm.c_control_run(with_keys(book, keys), facts)
        assert values_of(same) == values_of(plain), keys
        assert rows_of(same, fields) == rows_of(plain, fields)
        assert "pass9" not in same and all("iis" not in r and "cpn_anchor" not in r for c in same["cells"]
                                           for r in c["rows"])
    slot = ctx["A"]["cpn_annual"]
    flat = cm.c_control_run(put(book, AT1C, {**K2, "fixed": slot, "floating": 0.0}), facts)
    assert values_of(flat) == values_of(plain)
    assert [c["cpn_t1"] for c in flat["cells"]] == [slot] * len(flat["cells"])
    assert flat["ctx"]["A"]["cpn_annual"] is None                       # сумма слота с ключом не читается
    with_gap = cm.c_control_run(put(book, TAX, K1), facts)
    without_gap = cm.c_control_run(put(put(book, TAX, K1), GAP, None), facts)
    assert values_of(with_gap) == values_of(without_gap)


@pytest.mark.tact
def test_bad_keys_fail_loudly(inputs):
    """Прил. A № 34–35 на книге формы: отказы схемы — громко; ось на числе разрыва при включённом ключе — отказ, при
    выключенном — годна; null в сумме слота фактов с ключом купона — годен (не читается), без ключа — отказ."""
    book, facts = inputs
    for path, bad in ((TAX, {"enabled": True}), (TAX, {**K1, "bond_scale": -0.1}), (TAX, {**K1, "bond_rate": None}),
                      (TAX, {**K1, "coupon_deductible": "true"}), (TAX, {"enabled": None}), (TAX, 0.02),
                      (AT1C, {"enabled": True, "fixed": 1.0, "floating": 1.0}), (AT1C, {**K2, "floating": -1.0}),
                      (AT1C, {"enabled": False, "fixed": -1.0}), (AT1C, {"enabled": "false"})):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(put(book, path, bad), facts)
    axes = list(book["valuation"]["uncertainty"]["axes"]) + [
        {"name": "разрыв", "kind": "value", "paths": [GAP], "low": -0.03, "high": 0.0, "dist": "triangular"}]
    with_axis = put(book, "valuation.uncertainty.axes", axes)
    with pytest.raises(cm.ControlInputError, match="№ 34"):
        cm.c_control_context(put(with_axis, TAX, K1), facts)
    cm.c_control_context(put(with_axis, TAX, {**K1, "enabled": False}), facts)
    nulled = copy.deepcopy(facts)
    nulled["capital"]["at1"]["coupon_annual"] = {"v": None, "calc": "нераскрыто (вход теста)"}
    cm.c_control_context(put(book, AT1C, K2), nulled)
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(book, nulled)


# вне такта сервера: прогоны формы с ключами
def test_tax_rows_follow_the_rule(taxed, both):
    """Свойство 32 (с купоном сверх базы ключа доли AT1 и с ключом купона): налог каждого квартала профиля каждой клетки —
    правилом по её рядам, ряд ставки — маржинальная, τ_cpn = 0, CI — NI_sh минус купон целиком, тождество капитала с ним;
    DDM = RI."""
    for res in (taxed, both):
        assert_tax_rows(res)
        for c in res["cells"]:
            assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"])), key(c)


# вне такта сервера: прогон формы с крупным убытком кризиса
def test_loss_quarter_has_no_other_differences(inputs):
    """Свойство 34: в квартале с убытком (разовый убыток кризиса увеличен — вход теста) налог — τ × PBT − (τ − τ_b) × ζ ×
    IIS − TS, без o; ряд ставки — законная; налог непрерывен в нуле: при PBT = ±ε разность налогов — к нулю."""
    book, facts = inputs
    res = cm.c_control_run(with_keys(book, {TAX: K1, **BIG_LOSS}), facts)
    seen = assert_tax_rows(res, need_loss=True)
    rule = res["ctx"]["tax"]
    for c in res["cells"]:
        for r in c["rows"]:
            for j, pbt in enumerate(r["pbt_q"]):
                if pbt <= 0.0:
                    tau = r["tau_eff_q"][j]
                    no_other = tau * pbt - (tau - rule["bond_rate"]) * rule["bond_scale"] * r["iis_q"][j] - r[
                        "tax_coupon_q"][j]
                    assert r["tax_q"][j] == pytest.approx(no_other, rel=EXACT, abs=1e-9)
                    up, down = (cm.c_tax_rule(rule, tau, x, r["iis_q"][j], r["tax_coupon_q"][j]) for x in (1e-9, -1e-9))
                    assert abs(up - down) <= 1e-9
    assert seen["loss_quarters"]


# вне такта сервера: прогон формы с ключом
def test_zero_relief_and_flat_other_is_a_share_of_profit(inputs):
    """Свойство 33 (контрольный случай сверх сетки): bond_scale: 0, other_pp — число, coupon_deductible: false — налог
    квартала с PBT > 0 — (τ + o) × PBT, экономии купона нет, CI — NI_sh минус купон целиком."""
    book, facts = inputs
    res = cm.c_control_run(put(book, TAX, K1_ZERO), facts)
    assert_tax_rows(res)
    o = K1_ZERO["other_pp"]
    for c in res["cells"]:
        for p, r in zip(res["ctx"]["periods"], c["rows"]):
            assert r["tax_coupon"] == 0.0
            for j, q in enumerate(p["quarters"]):
                if r["pbt_q"][j] > 0.0:
                    tau = cm.c_traj_at(cm.c_bget(res["ctx"]["B"], "tax.statutory"), p["year"], q)
                    assert r["tax_q"][j] == pytest.approx((tau + o) * r["pbt_q"][j], rel=EXACT)


@pytest.mark.tact
def test_other_pp_shift_moves_tax_by_delta_profit():
    """Свойство 38: сдвиг other_pp на Δ меняет налог квартала ровно на Δ × max(PBT, 0) — при прибыли и при убытке."""
    rule = tax_rule_of({k: v for k, v in K1.items() if k != "enabled"})
    moved = {**rule, "other_pp": rule["other_pp"] + 0.013}
    for pbt in (250.0, 3.0, 0.0, -40.0):
        diff = cm.c_tax_rule(moved, 0.25, pbt, 90.0, 4.0) - cm.c_tax_rule(rule, 0.25, pbt, 90.0, 4.0)
        assert diff == pytest.approx(0.013 * max(pbt, 0.0), abs=1e-12), pbt


# вне такта сервера: прогоны формы с ключами
def test_dividend_base_takes_the_whole_coupon(inputs, taxed, both):
    """Свойства 35, 42 (годовая ветвь, deduct_at1_after_tax: true): с ключом налога база решения — Σ NI_sh года прибыли минус
    купон года целиком (якоря и сверх базы); с ключом купона купон якоря года — его формула по ключевой мира клетки; без
    ключа налога, с ключом купона — купон якоря × (1 − τ)."""
    book, facts = inputs
    couponed = cm.c_control_run(with_keys(book, {AT1C: K2}), facts)
    seen = 0
    for res, whole in ((taxed, True), (both, True), (couponed, False)):
        ctx = res["ctx"]
        B, A = ctx["B"], ctx["A"]
        assert cm.c_bget(B, "dividends.policy.deduct_at1_after_tax") is True
        for c in res["cells"][::5]:
            for year, d in c["decisions"].items():
                if d.get("kind") not in ("policy", "crisis_skip") or "base" not in d:
                    continue
                i = next((i for i, p in enumerate(ctx["periods"]) if p["year"] == year and p["n"] == cm.QY), None)
                if i is None:
                    continue
                r = c["rows"][i]
                ni = sum(v for (yy, _), v in r["ni_q"].items() if yy == year)
                anchor = r["cpn_anchor"] if "cpn_anchor" in r else r["cpn"]
                if ctx["at1c"] is not None:
                    want_a = coupon_by_hand(ctx, c["world"], year, A["cpn_quarter"])
                    assert anchor == pytest.approx(want_a, rel=EXACT), (key(c), year)
                tau = cm.c_traj_at(cm.c_bget(B, "tax.statutory"), year, A["cpn_quarter"])
                new = sum(r.get("cpn_new_q", [0.0]))
                want = ni - anchor - new if whole else ni - anchor * (1.0 - tau) - r.get("cpn_new_net", 0.0)
                assert d["base"] == pytest.approx(want, rel=1e-12), (key(c), year)
                seen += 1
    assert seen


def coupon_by_hand(ctx: dict, world: str, y: int, q: int) -> float:
    """Купон якоря квартала купона (М§4.9) своей арифметикой теста: ключевая мира — значение пути книги в квартале,
    кварталы не позже якоря — квартала якоря."""
    rule, anchor = ctx["at1c"], ctx["anchor"]
    path = cm.c_bget(ctx["B"], f"worlds.{world}.key_rate")
    k = cm.c_qidx(anchor, y, q)
    keys = [cm.c_traj_at(path, *cm.c_qper(anchor, max(k - j, 0))) for j in range(cm.QY)]
    return rule["fixed"] + rule["floating"] * (sum(keys) / cm.QY + rule["spread"])


# вне такта сервера: прогоны формы с ключом купона
def test_anchor_coupon_follows_the_key_of_its_world(inputs, both):
    """Свойства 39, 41, 43: купон якоря в квартале купона каждой клетки — Cfix + Cflt × (k̄ + s) по пути ключевой своего мира
    (у мира H с ключом полугодия квартала якоря — k̄ года якоря с ключевой квартала якоря), в остальных — ноль; ряд coupon — он плюс
    купон сверх базы; купон года T + 1 — по ключевой последнего квартала сетки (путь мира H меняется в 2036 году) плюс
    c_α,Q × ΔAT1_Q; подмена пути ключевой одного мира меняет купон только клеток этого мира."""
    book, facts = inputs
    ctx = both["ctx"]
    A, rule = ctx["A"], ctx["at1c"]
    for c in both["cells"]:
        for p, r in zip(ctx["periods"], c["rows"]):
            want = coupon_by_hand(ctx, c["world"], p["year"], A["cpn_quarter"]) if A["cpn_quarter"] in p["quarters"] else 0.0
            assert r["cpn_anchor"] == pytest.approx(want, rel=EXACT, abs=1e-12), (key(c), p["year"])
            assert r["cpn"] == pytest.approx(r["cpn_anchor"] + sum(r["cpn_new_q"]), rel=EXACT)
        last = c["rows"][-1]
        path = cm.c_bget(ctx["B"], f"worlds.{c['world']}.key_rate")
        y_l = ctx["periods"][-1]["year"]
        key_q = cm.c_traj_at(path, y_l, ctx["periods"][-1]["quarters"][-1])
        assert c["cpn_anchor_t1"] == pytest.approx(rule["fixed"] + rule["floating"] * (key_q + rule["spread"]), rel=EXACT)
        assert c["cpn_t1"] == pytest.approx(c["cpn_anchor_t1"] + (key_q + ctx["at1"]["spread"])
                                            * (last["at1"] - ctx["at1"]["base"]), rel=EXACT)
        if c["world"] == "H":
            mean_l = cm.c_traj_mean(path, y_l, ctx["periods"][-1]["quarters"])
            assert abs(mean_l - key_q) > 0.001, "вход теста: ключевая мира H меняется в последнем году"
    # год якоря у мира H: кварталы не позже якоря — ключевая квартала якоря (2026Q2), а не первого прогнозного
    h = next(c for c in both["cells"] if c["world"] == "H")
    first = ctx["periods"][0]
    path = cm.c_bget(ctx["B"], "worlds.H.key_rate")
    k_first = cm.c_traj_at(path, *cm.c_qper(ctx["anchor"], 1))
    assert abs(cm.c_traj_at(path, *ctx["anchor"]) - k_first) > 0.01
    assert h["rows"][0]["cpn_anchor"] == pytest.approx(coupon_by_hand(ctx, "H", first["year"], A["cpn_quarter"]), rel=EXACT)
    # подмена пути ключевой одного мира меняет купон только у его клеток
    moved = cm.c_control_run(with_keys(book, {AT1C: K2, "worlds.N.key_rate": {"LT": 0.21}}), facts)
    still = cm.c_control_run(put(book, AT1C, K2), facts)
    for a, b in zip(still["cells"], moved["cells"]):
        same = [r["cpn_anchor"] for r in a["rows"]] == [r["cpn_anchor"] for r in b["rows"]]
        assert same is (a["world"] != "N"), key(a)


# вне такта сервера: прогоны формы с ключами
def test_terminal_lines_follow_the_rule(inputs, both):
    """М§7, свойство 37: NI_T+1 — правилом по рядам конца сетки (PBT_L, IIS_L, Y_X, A_X той же частью избытка, CPN_T+1) при
    X_T > 0 и X_T ≤ 0, CI_T+1 — с купоном целиком; блок постоянных частей (λ_F = 0) — ставкой после налога y^τ_m в обеих
    ветвях y_m (ветвь опта — подменой минимума ликвидности); DDM = RI."""
    book, facts = inputs
    runs = {"both": both,
            "short": cm.c_control_run(with_keys(book, {TAX: K1, AT1C: K2, **SHORT_BUFFER}), facts),
            "lam0": cm.c_control_run(with_keys(book, {TAX: K1, **FIXED_LAM0}), facts),
            "lam0-wholesale": cm.c_control_run(with_keys(book, {TAX: K1, **FIXED_LAM0,
                                                                "volumes.liquid_min_share": 0.3}), facts)}
    signs, branches = set(), set()
    for name, res in runs.items():
        ctx = res["ctx"]
        B, rule = ctx["B"], ctx["tax"]
        nci, ssl = cm.c_bnum(B, "pnl.nci_share"), cm.c_bnum(B, "volumes.securities_share_of_liquid")
        for c in res["cells"]:
            last = c["rows"][-1]
            tau = last["tau_stat"]
            x, g = c["x_t"], c["g_t"]
            a_x = min(x, c["h_star"]) if x > 0.0 else -max(0.0, -x - c["wt"])
            pbt_x = last["pbt"] * (1.0 + g) - c["y_x"]
            iis_t1 = last["iis"] * (1.0 + g) - ssl * last["y_sec_end"] * a_x
            cpn = c.get("cpn_t1", ctx["A"]["cpn_annual"])
            tax = tax_by_hand(rule, tau, pbt_x, iis_t1, cpn)
            t = c["terminal_tax"]
            for field, want in (("a_x", a_x), ("pbt_x", pbt_x), ("iis_t1", iis_t1), ("tax_t1", tax)):
                assert t[field] == pytest.approx(want, rel=EXACT, abs=1e-9), (name, key(c), field)
            assert c["ni_t1"] == pytest.approx((pbt_x - tax) * (1.0 - nci), rel=EXACT)
            assert c["ci_t1"] == pytest.approx(c["ni_t1"] - cpn, rel=EXACT)
            assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"])), (name, key(c))
            signs.add(x > 0.0)
            if "terminal_fixed" in c:
                node = c["terminal_fixed"]
                keep = 1.0 - tau - rule["other_pp"]
                if c["wt"] > 0.0:
                    y_tau = last["c_wh_end"] * keep
                else:
                    y_tau = (ssl * last["y_sec_end"] * (keep + (tau - rule["bond_rate"]) * rule["bond_scale"])
                             + (1.0 - ssl) * last["y_liq_end"] * keep)
                assert node["y_m_after_tax"] == pytest.approx(y_tau, rel=EXACT)
                assert node["i_f"] == pytest.approx(-y_tau * node["d_f"] * (1.0 - nci), rel=EXACT)
                branches.add(c["wt"] > 0.0)
    assert signs == {True, False}, "вход теста: избыток и недостаток капитала на T"
    assert branches == {True, False}, "вход теста: обе ветви y_m блока постоянных частей"


@pytest.mark.tact
def test_roe_equivalent_reads_the_marginal_rate(plain, inputs):
    """М§4.5: ROE-эквивалент передачи у книги с ключом — по ставке τ_stat,L + o (книгой, без клеток)."""
    book, facts = inputs
    ctx = cm.c_control_context(put(book, TAX, K1), facts)
    B = plain["ctx"]["B"]
    yl, ql = cm.c_per_parse(cm.c_bget(B, "meta.last_period"))
    tau = cm.c_traj_at(cm.c_bget(B, "tax.statutory"), yl, ql)
    ratio = (1.0 - tau - K1["other_pp"]) / (1.0 - tau - cm.c_bnum(B, GAP))
    assert ctx["tr"]["roe_equiv"] == pytest.approx(plain["transmission"]["roe_equiv"] * ratio, rel=EXACT)


# ============================================================================ квартальный проход (форма панели)

AT1_T, CPN_T = 60.0, 6.0          # AT1 якоря формы панели и купон (у фикстуры — 0): вход теста
K2_T = {"enabled": True, "fixed": 1.0, "floating": 25.0, "spread": 0.05}


def facts_t_with_at1() -> dict:
    facts = cm.c_facts_bundle(FIXTURE_T / "facts")
    facts["balance"]["equity"]["at1"] = {"v": AT1_T, "calc": "вход теста"}
    facts["capital"]["at1"]["coupon_annual"] = {"v": CPN_T, "calc": "вход теста"}
    return facts


def book_t_keys() -> dict:
    book = json.loads((FIXTURE_T / "book.json").read_text(encoding="utf-8"))
    return with_keys(book, {TAX: K1, AT1C: K2_T, "dividends.policy.deduct_at1_after_tax": True,
                            AT1: {"enabled": True, "from": "2027Q4", "spread": 0.04, "base": "anchor"}})


@pytest.fixture(scope="module")
def quarterly():
    facts = facts_t_with_at1()
    return book_t_keys(), facts, cm.c_control_run(book_t_keys(), facts)


# вне такта сервера: сетка формы панели с квартальным проходом — секунды
def test_quarterly_pass_with_the_pass9_keys(quarterly):
    """Квартальный проход (форма панели, AT1 якоря подставлен, база дивиденда вычитает купон): налог — правилом по рядам;
    проход кончает год на капитале годовой строки (Σ прибыли кварталов профиля — прибыль года); база решения за квартал
    прибыли — средняя окна (NI_sh квартала − купон квартала целиком); без ключей — бит в бит."""
    book, facts, res = quarterly
    assert_tax_rows(res)
    ctx = res["ctx"]
    A, B = ctx["A"], ctx["B"]
    window = int(cm.c_bget(B, "dividends.policy.base_window_quarters"))
    seen = 0
    for c in res["cells"]:
        ni_all, cpn_all = {}, {}
        for p, r in zip(ctx["periods"], c["rows"]):
            assert r["quarters"][-1]["bv"] == pytest.approx(r["bv"], rel=1e-8), (key(c), p["year"])
            for j, q in enumerate(p["quarters"]):
                ni_all[cm.c_qidx(ctx["anchor"], p["year"], q)] = r["ni_q"][(p["year"], q)]
                cpn_all[cm.c_qidx(ctx["anchor"], p["year"], q)] = r["coupon_q"][j]
        for r in c["rows"]:
            for rec in r["decisions_q"]:
                k = cm.c_qidx(ctx["anchor"], *cm.c_per_parse(rec["period"]))
                if k - window + 1 < 1 or rec.get("source") == "register":
                    continue
                want = sum(ni_all[x] - cpn_all[x] for x in range(k - window + 1, k + 1)) / window
                assert rec["base"] == pytest.approx(want, rel=1e-12, abs=1e-9), (key(c), rec["period"])
                seen += 1
    assert seen
    bare = json.loads((FIXTURE_T / "book.json").read_text(encoding="utf-8"))
    plain_t = cm.c_control_run(bare, cm.c_facts_bundle(FIXTURE_T / "facts"))
    off = cm.c_control_run(with_keys(bare, OFF9_FULL), cm.c_facts_bundle(FIXTURE_T / "facts"))
    assert values_of(off) == values_of(plain_t)


# ============================================================================ сверка с ядром (в момент теста)


def core_quarters(run, c: dict):
    return run.cell(c["world"], c["regime"], c["scenario"]).quarters


def tax_rows(run, ctl) -> list[str]:
    """Налог года клетки (М§17): у двух моделей — в допуске строк ОПУ (10 %, пол 2 % BV); у ядра — правилом на его же
    строках до 1e-6 (по кварталам ядра; на годовых строках — в годах с прибылью во всех кварталах)."""
    rule, bad = ctl["ctx"]["tax"], []
    qidx = tcm._quarter_index(ctl)
    B = ctl["ctx"]["B"]
    for c in ctl["cells"]:
        q = core_quarters(run, c)
        for name in ("tax", "pbt", "iis", "coupon"):
            if name not in q:
                return [f"у ядра нет ряда {name} (М§4.8)"]
        for p, r in zip(ctl["ctx"]["periods"], c["rows"]):
            ids = qidx[p["year"]]
            core_tax = sum(q["tax"][j] for j in ids)
            if abs(core_tax - r["tax"]) > max(tcm.TOL_LINE * abs(core_tax), tcm.TOL_SMALL_BV * abs(r["bv"])):
                bad.append(f"налог {p['year']} {key(c)}: ядро {core_tax:.4f}, контроль {r['tax']:.4f}")
            taus = [cm.c_traj_at(cm.c_bget(B, "tax.statutory"), p["year"], qq) for qq in p["quarters"]]
            by_rule = sum(cm.c_tax_rule(rule, t, q["pbt"][j], q["iis"][j], cm.c_tax_coupon(rule, t, q["coupon"][j]))
                          for t, j in zip(taus, ids))
            if abs(by_rule - core_tax) > CORE_TAX_TOL * max(1.0, abs(core_tax)):
                bad.append(f"налог ядра {p['year']} {key(c)} не по правилу на его строках: {core_tax} против {by_rule}")
            if min(q["pbt"][j] for j in ids) > 0.0 and len(set(taus)) == 1:
                whole = cm.c_tax_rule(rule, taus[0], sum(q["pbt"][j] for j in ids), sum(q["iis"][j] for j in ids),
                                      cm.c_tax_coupon(rule, taus[0], sum(q["coupon"][j] for j in ids)))
                if abs(whole - core_tax) > CORE_TAX_TOL * max(1.0, abs(core_tax)):
                    bad.append(f"налог ядра {p['year']} {key(c)} не по правилу на годовых строках: {core_tax} / {whole}")
    return bad


FORMS = {"k1": lambda book: put(book, TAX, K1),
         "k1-loss": lambda book: with_keys(book, {TAX: K1, **BIG_LOSS}),
         "k1-zero": lambda book: put(book, TAX, K1_ZERO),
         "k1-nodeduct": lambda book: put(book, TAX, {**K1, "coupon_deductible": False}),
         "k1-gap-null": lambda book: put(put(book, TAX, K1), GAP, None),
         "k1-at1share": lambda book: with_keys(book, {TAX: K1, AT1: AT1_MID}),
         "k1-lam0": lambda book: with_keys(book, {TAX: K1, **FIXED_LAM0}),
         "k1-short": lambda book: with_keys(book, {TAX: K1, **SHORT_BUFFER}),
         "k2": lambda book: put(book, AT1C, K2),
         "k2-key-moves": lambda book: with_keys(book, {AT1C: K2, "worlds.H.key_rate": {**book["worlds"]["H"]["key_rate"],
                                                                                        **KEY_MOVES}}),
         "k2-at1share": lambda book: with_keys(book, {AT1C: K2, AT1: AT1_MID}),
         "k2-flat-slot": lambda book: put(book, AT1C, {**K2, "fixed": 9.7, "floating": 0.0}),
         "k12": lambda book: with_keys(book, {TAX: K1, AT1C: K2}),
         "k12-all8": lambda book: with_keys(book, {TAX: K1, AT1C: K2, **K8_ALL}),
         "k12-all8-lam0": lambda book: with_keys(book, {TAX: K1, AT1C: K2, **K8_ALL, **FIXED_LAM0}),
         "off9": lambda book: with_keys(book, OFF9_FULL)}


@pytest.mark.ci_only
@pytest.mark.parametrize("form", list(FORMS))
def test_control_matches_core_with_the_pass9_keys(inputs, form):
    """Форма образца с ключами девятого прохода против ядра (чёрный ящик: запуск и поля результата) — прежние строки в
    прежних допусках М§17 и налог года клетки. Расхождение — находка, а не повод подогнать контрольную модель."""
    book, facts = inputs
    ready = FORMS[form](book)
    run = tcd._core_run(ready, FIXTURE / "facts")
    ctl = cm.c_control_run(ready, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    assert not tcm.exact_match(run, ctl), "V0 слоёв совпали с ядром до 1e-9 — общий код"
    if ctl["ctx"]["tax"] is not None:
        wrong = tax_rows(run, ctl)
        assert not wrong, chr(10).join(wrong[:20])


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
    """Фикстура core_t (квартальный календарь, рост ограничен капиталом) с AT1 якоря, ключами девятого прохода и долей AT1
    против ядра — в допусках М§17, налог года — в допуске и правилом на строках ядра."""
    book, facts, ctl = quarterly
    run = tcd._core_run(book, write_facts_t_with_at1(tmp_path))
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    wrong = tax_rows(run, ctl)
    assert not wrong, chr(10).join(wrong[:20])


@pytest.mark.ci_only
def test_pass9_keys_against_core_as_a_black_box(inputs, plain):
    """Ядро — чёрный ящик: enabled: false дают у ядра оценку книги без ключей, floating: 0 с fixed = слоту — тоже; каждый ключ
    двигает точку у двух моделей в одну сторону и на близкую величину; книги с ключами вне правил (№ 34–35) отвергают обе
    модели."""
    book, facts = inputs
    bare = tcd._core_run(book, FIXTURE / "facts")
    for keys in (OFF9, OFF9_FULL, {AT1C: {**K2, "fixed": 9.7, "floating": 0.0}}):
        run = tcd._core_run(with_keys(book, keys), FIXTURE / "facts")
        assert (run.point, run.low, run.high) == (bare.point, bare.low, bare.high), keys
    for ready in (put(book, TAX, K1), put(book, AT1C, K2), with_keys(book, {TAX: K1, AT1C: K2})):
        mine = cm.c_control_run(ready, facts)["point"] - plain["point"]
        theirs = tcd._core_run(ready, FIXTURE / "facts").point - bare.point
        assert mine * theirs > 0.0 and abs(mine - theirs) <= tcm.TOL_VALUE * abs(bare.point), (mine, theirs)
    book_mod = importlib.import_module("model.book")
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    axes = list(book["valuation"]["uncertainty"]["axes"]) + [
        {"name": "разрыв", "kind": "value", "paths": [GAP], "low": -0.03, "high": 0.0, "dist": "triangular"}]
    for bad in (put(book, TAX, {"enabled": True, "bond_rate": 0.2, "other_pp": 0.02, "coupon_deductible": True}),
                put(book, TAX, {**K1, "bond_scale": -1.0}), put(book, TAX, {**K1, "coupon_deductible": "yes"}),
                put(book, TAX, {"enabled": "true"}), put(book, TAX, {"enabled": False, "rate": 0.2}),
                put(book, AT1C, {"enabled": True, "fixed": 19.4, "spread": 0.05}),
                put(book, AT1C, {**K2, "floating": -1.0}),
                put(put(book, "valuation.uncertainty.axes", axes), TAX, K1)):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(bad, facts)
        with pytest.raises(Exception) as refused:
            book_mod.book_from_dict(bad, facts=core_facts)
        assert type(refused.value).__name__ == "BookError", refused.value
