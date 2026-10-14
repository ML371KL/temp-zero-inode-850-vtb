"""Проверки пятого прохода ядра (строки М§18 «Аналитические тесты пятого прохода»): вычет сценария в рублях
(`capital.reg_scenarios.<s>.deduction_rub`, М§4.11, свойства 9–12, прил. A № 23), путь постоянной части прочих
активов (`volumes.other_assets_fixed_change` и плотность приращения `capital.rwa.density.other_assets_fixed_change`,
М§4.3, §4.10, §4.11, прил. A № 8, № 24) и терминал с постоянными в рублях частями
(`valuation.terminal.fixed_growth_share`, λ_F, М§6.4 п. 12, §7, прил. A № 25).

Фикстуры — формы образца `tests/fixtures/core` (ключи подставляет тест; книга с постоянной частью прочих активов
собирается заново, чтобы отношение прочих активов к кредитам вывелось от растущей части), фикстура докапитализации
(`tests/support_core_recap.py`) и полная фикстура формы Т (`core_t`); общий числовой пример — приложение H методики
(`tests/fixtures/core_pass5/example.json`). Каждая проверка — тождество или закрытая формула, выведенная из книги,
фактов и рядов клетки независимо от кода ядра: вычет — по ряду RWA клетки и траектории книги, капитал — по рядам
клетки, RWA — по остаткам книг и плотностям, блок терминала и его строки — по рядам конца сетки и терминалу книги с
λ_F = 1. Те же функции зовут тесты `tests/test_core_pass5.py` и мутационный набор `tests/mutations.py`.

«Тихая» книга (`QUIET`) — книга, у которой путь капитала от нормативов не зависит: доля выплаты и выплата избытка —
ноль, замыкания капитала выключены. На ней ряды капитала и RWA книг с ключом и без него совпадают, и разность
нормативов — ровно разность вычетов.
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from model.book import Book, Facts, book_from_dict
from model.book_schema import BookError, _fixed_change_problems, validate
from model.capital import CapitalConst, RwaWeights, deduction_parts, ratios
from model.checks import check_invariants
from model.grid import GridRun, path_inputs, path_key, run_grid, run_paths
from model.paths import path_value
from model.valuation import terminal, value_cell
from model.worlds import Discount
from tests import support_core_recap as R
from tests.support_core import fixture_dict, fixture_facts, fixture_run
from tests.support_core_recap import close

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE: dict[str, Any] = json.loads((ROOT / "tests" / "fixtures" / "core_pass5" / "example.json")
                                     .read_text(encoding="utf-8"))
TOL = 1e-9                                   # допуск примера приложения H (М§17)
S20, S11 = "capital.n20.deductions_fixed_share", "capital.n11.deductions_fixed_share"
D20, D11 = "capital.n20.deductions_anchor", "capital.n11.deductions_anchor"
G20, G11 = "capital.n20.gap_pp", "capital.n11.gap_pp"
LEVEL = "volumes.other_assets_fixed"
CHANGE = "volumes.other_assets_fixed_change"
W_FIXED = "capital.rwa.density.other_assets_fixed"
W_CHANGE = "capital.rwa.density.other_assets_fixed_change"
LAM = "valuation.terminal.fixed_growth_share"
FADE = "valuation.terminal.fade"
ETA = (0.6, 0.35)                            # доли вычета якоря: разные у двух нормативов и не половина
QUIET: dict[str, Any] = {"dividends.policy.payout": {"LT": 0.0}, "dividends.excess.epsilon": 0.0}
N11_TIGHT = {"capital.mgmt_buffer.n1_1": 0.06}               # на конце сетки связывает Н20.1
# Постоянная часть прочих активов фикстуры и её путь: убывание 60 млрд ₽ в 2027 году, до 300 к LT; вес уходящей
# части — ноль (вычитаемый из капитала актив), плотность постоянной части — 0,6.
FIXED: dict[str, Any] = {LEVEL: 1200.0, W_FIXED: 0.6, W_CHANGE: 0.0,
                         CHANGE: {"2026": 0.0, "2027": -60.0, "2029": -200.0, "LT": -300.0, "LT_from": 2033}}
# Множитель RWA режима без года шока, ниже единицы и на конце сетки: R_F несёт его (М§7)
SOFT_MULT = {"regimes.soft.rwa_density_mult": {"2026": 1.0, "2027": 0.97, "LT": 0.95, "LT_from": 2030}}
ASSET = 500.0                                # бездоходный актив проверки нейтральности, млрд ₽
# Минимум ликвидности считается от всех небалансирующих активов (М§4.10): бездоходный актив поднял бы и его — канал
# вне терминала; проверка нейтральности идёт без минимума (в клетках без добора опта он и так не действует)
NO_LIQUIDITY_MINIMUM = {"volumes.liquid_min_share": 0.0}


def scenarios() -> tuple[str, ...]:
    return tuple(fixture_dict()["capital"]["reg_scenarios"]["ids"])


def rub(scale: float = 1.0, *, flat: float | None = None) -> dict[str, Any]:
    """Вычет сценария в рублях по сценариям фикстуры: ноль в году якоря, у каждого сценария и норматива свой путь
    (разные у Н20.0 и Н20.1 и по сценариям); `flat` — одна сумма во всех кварталах (и в квартале якоря)."""
    out = {}
    for i, s in enumerate(scenarios()):
        if flat is not None:
            node = {"n20_0": flat, "n1_1": flat}
        else:
            node = {"n20_0": {"2026": 0.0, "2027": scale * (30.0 + 15.0 * i), "2029": scale * (90.0 + 20.0 * i),
                              "LT": scale * (150.0 + 30.0 * i), "LT_from": 2033},
                    "n1_1": {"2026": 0.0, "2027": scale * 20.0, "2029": scale * (60.0 - 10.0 * i),
                             "LT": scale * (100.0 + 5.0 * i), "LT_from": 2033}}
        out[f"capital.reg_scenarios.{s}.deduction_rub"] = node
    return out


def shares(eta20: float = ETA[0], eta11: float = ETA[1]) -> dict[str, float]:
    return {S20: eta20, S11: eta11}


def _put(data: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = data
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = copy.deepcopy(value)


def book_dict(changes: Mapping[str, Any] | None = None) -> dict:
    data = copy.deepcopy(fixture_dict())
    for dotted, value in (changes or {}).items():
        _put(data, dotted, value)
    return data


def book_of(changes: Mapping[str, Any] | None = None, facts: Facts | None = None) -> Book:
    """Книга фикстуры формы образца с подменами — собранная заново: ключи `anchor` выводятся на книге с подменами
    (отношение прочих активов к кредитам — от растущей части)."""
    return book_from_dict(book_dict(changes), facts=facts or fixture_facts())


_GRIDS: dict[str, GridRun] = {}


def grid(changes: Mapping[str, Any] | None = None, facts: Facts | None = None, tag: str = "") -> GridRun:
    """Сетка книги фикстуры с подменами (одна на набор подмен и факты: проверки читают её, не меняя)."""
    if not changes and facts is None:
        return fixture_run()
    key = tag + json.dumps(changes or {}, sort_keys=True, ensure_ascii=False)
    if key not in _GRIDS:
        f = facts or fixture_facts()
        _GRIDS[key] = run_grid(book_of(changes, f), f)
    return _GRIDS[key]


def t_grid(changes: Mapping[str, Any] | None = None) -> GridRun:
    """Сетка полной фикстуры формы Т (множитель плотности режима, рост по капиталу, квартальный календарь)."""
    from tests.support_core_t import book_live, put, t_dict, t_facts

    key = "t:" + json.dumps(changes or {}, sort_keys=True, ensure_ascii=False)
    if key not in _GRIDS:
        data = t_dict()
        for dotted, value in (changes or {}).items():
            if dotted.startswith("capital.reg_scenarios.<s>."):
                for s in data["capital"]["reg_scenarios"]["ids"]:
                    put(data, dotted.replace("<s>", s), copy.deepcopy(value))
            else:
                put(data, dotted, copy.deepcopy(value))
        book = book_from_dict(data, facts=t_facts())
        _GRIDS[key] = run_grid(book, t_facts(), book_live(book))
    return _GRIDS[key]


def anchor_parts(run: GridRun) -> tuple[float, float, float]:
    """(Ded20_0, Ded11_0, RWA_0) — ключи книги и RWA строки якоря."""
    book = run.ctx.book
    return float(book.get(D20)), float(book.get(D11)), float(run.cells[0].quarters["rwa"][0])


def drub(run: GridRun, scenario: str, slot: str, q: int) -> float:
    """Drub_j,s,q — значение траектории книги в квартале q (М§0.4); ключа нет — ноль."""
    node = run.ctx.book.opt(f"capital.reg_scenarios.{scenario}.deduction_rub")
    return 0.0 if node is None else path_value(node[slot], run.ctx.timeline.period(q))


def eta_of(run: GridRun) -> tuple[float, float]:
    book = run.ctx.book
    return float(book.opt(S20, 0.0)), float(book.opt(S11, 0.0))


# ------------------------------------------------------------------ без ключей и ключи-нули (М§4.3, §4.11, §7)


def check_zero_keys_are_the_book_without_keys() -> None:
    """Рубли сценария и приращения постоянной части, равные нулю, и λ_F = 1 — ряды и оценка книги без ключей бит в
    бит: на фикстуре формы образца, на фикстуре докапитализации и на полной фикстуре формы Т; λ_F = 1 и без ключа —
    те же числа и у книги с постоянными частями. Строка вычета с рублями, равными нулю, даёт биты прежней строки на
    любых входах."""
    zero = {**rub(flat=0.0), CHANGE: 0.0, W_FIXED: 0.6, LAM: 1.0}
    base, keyed = fixture_run(), grid(zero)
    p = keyed.ctx.prep
    assert p.oa_delta is not None and p.lam_f == 1.0 and all(sp.rub20 is not None for sp in p.scenarios.values())
    assert base.ctx.prep.oa_delta is None and base.ctx.prep.lam_f is None
    R.cells_equal(base, keyed)
    assert all(a.tv_ddm == b.tv_ddm and a.decisions == b.decisions for a, b in zip(base.cells, keyed.cells))
    assert {n: (L.v0, L.price) for n, L in base.layers.items()} == {n: (L.v0, L.price) for n, L in keyed.layers.items()}
    assert all(c.terminal_fixed is None for c in base.cells) and all(c.terminal_fixed is not None for c in keyed.cells)
    # λ_F = 1 и без ключа — у книги с постоянными частями обеих сторон
    parts = {**FIXED, **rub(), **shares()}
    R.cells_equal(grid(parts), grid({**parts, LAM: 1.0}))
    # фикстура докапитализации (взносы — те же) и полная форма Т (рост по капиталу)
    recap, recap_zero = R.grid_of(), R.grid_of({**rub(flat=0.0), CHANGE: 0.0, W_FIXED: 0.6, LAM: 1.0})
    R.cells_equal(recap, recap_zero)
    assert all(a.recaps == b.recaps for a, b in zip(recap.cells, recap_zero.cells))
    assert sum(1 for c in recap.cells for r in c.recaps if r.rec > 0) >= 20
    R.cells_equal(t_grid(), t_grid({"capital.reg_scenarios.<s>.deduction_rub": {"n20_0": 0.0, "n1_1": 0.0},
                                    CHANGE: 0.0, LAM: 1.0}))
    rnd = random.Random(855)
    for _ in range(2000):
        ded20, ded11 = rnd.uniform(-900.0, 1900.0), rnd.uniform(-900.0, 1900.0)
        kw = dict(rwa0=rnd.uniform(1e3, 9e4), fvoci_recognition=rnd.random(), gap20=rnd.uniform(-0.01, 0.01),
                  gap11=rnd.uniform(-0.01, 0.01), at1=rnd.uniform(0.0, 400.0), audit_cutoffs=(4,), buffer20=0.0,
                  buffer11=0.0)
        row = dict(bv=rnd.uniform(1e3, 2e4), dpreg=rnd.uniform(0.0, 500.0), reserve=rnd.uniform(-600.0, 200.0),
                   unaudited=rnd.uniform(-300.0, 900.0), t2=rnd.uniform(0.0, 700.0), rwa=rnd.uniform(5e2, 3e5),
                   ded_pp20=rnd.uniform(0.0, 0.02), ded_pp11=rnd.uniform(0.0, 0.02))
        for parts_ in (None, deduction_parts(ded20, ded11, rnd.random(), rnd.random())):
            c = CapitalConst(ded20_0=ded20, ded11_0=ded11, parts=parts_, **kw)
            assert ratios(c, **row) == ratios(c, rub20=0.0, rub11=0.0, **row), row


# ------------------------------------------------------------------ вычет сценария в рублях (М§4.11, свойства 9–12)


def _check_rub_formula(run: GridRun) -> int:
    """Ряд вычета каждой клетки — `Dgrow_j × RWA_q / RWA_0 + Dfix_j + Drub_j,s,q` по ряду RWA клетки, K20, K11 и
    нормативы, пересчитанные по рядам клетки, — её ряды; аддитивное слагаемое `N_j − K_j / RWA` — поправка минус путь
    в п.п. (рублей не несёт); Н20.1 с прибылью периода несёт рубли. → число кварталов с ненулевыми рублями."""
    book, tl, prep = run.ctx.book, run.ctx.timeline, run.ctx.prep
    ded20_0, ded11_0, rwa0 = anchor_parts(run)
    eta20, eta11 = eta_of(run)
    f = float(book.get("capital.n20.fvoci_recognition"))
    gap20, gap11 = float(book.get(G20)), float(book.get(G11))
    t2 = [path_value(book.get("capital.n20.t2"), tl.period(q)) for q in range(tl.Q + 1)]
    seen = 0
    for c in run.cells:
        q_ = c.quarters
        dpp = {n: book.get(f"capital.reg_scenarios.{c.scenario}.deduction_pp.{n}") for n in ("n20_0", "n1_1")}
        for q in range(tl.Q + 1):
            rwa = q_["rwa"][q]
            r20, r11 = drub(run, c.scenario, "n20_0", q), drub(run, c.scenario, "n1_1", q)
            want20 = (1 - eta20) * ded20_0 * rwa / rwa0 + eta20 * ded20_0 + r20
            want11 = (1 - eta11) * ded11_0 * rwa / rwa0 + eta11 * ded11_0 + r11
            assert close(q_["ded20"][q], want20, rel=1e-12, abs_=1e-9), (c.label, q, q_["ded20"][q], want20)
            assert close(q_["ded11"][q], want11, rel=1e-12, abs_=1e-9), (c.label, q, q_["ded11"][q], want11)
            bvreg = q_["bv"][q] + q_["dpreg"][q] - (1 - f) * q_["reserve"][q]
            k20 = bvreg - want20 + prep.af.at1 + t2[q]
            a20 = gap20 - path_value(dpp["n20_0"], tl.period(q))
            assert close(q_["k20"][q], k20, rel=1e-12, abs_=1e-9), (c.label, q)
            assert close(q_["n20"][q], k20 / rwa + a20, rel=1e-12, abs_=1e-14), (c.label, q)
            assert close(q_["n20"][q] - q_["k20"][q] / rwa, a20, abs_=1e-13), (c.label, q)
            seen += r20 != 0
            e = q_["e_unaudited"][q]
            if e is None or q_["k11"][q] is None:
                continue
            k11 = bvreg - max(e, 0.0) - want11
            a11 = gap11 - path_value(dpp["n1_1"], tl.period(q))
            assert close(q_["k11"][q], k11, rel=1e-12, abs_=1e-9), (c.label, q)
            assert close(q_["n11"][q] - q_["k11"][q] / rwa, a11, abs_=1e-13), (c.label, q)
            assert close(q_["n11_star"][q], (k11 + max(e, 0.0)) / rwa + a11, rel=1e-12, abs_=1e-14), (c.label, q)
    return seen


def check_rub_deduction_is_the_formula() -> None:
    """Свойство 9 М§4.11: в каждом квартале каждой клетки ряд вычета — формула по ряду RWA клетки с рублями своего
    сценария; K20 и K11, пересчитанные по рядам клетки, — её ряды; у сценариев с разными рублями — свои ряды. Книги:
    с долями вычета якоря и без них, докапитализация, полная форма Т (рост по капиталу, множитель режима)."""
    for run in (grid({**rub(), **shares()}), grid(rub()), grid({**QUIET, **rub(), **shares(0.25, 0.9)})):
        assert _check_rub_formula(run) >= 3 * 12 * 30
    _check_rub_formula(R.grid_of({**rub(), **shares()}))
    t = t_grid({"capital.reg_scenarios.<s>.deduction_rub": {"n20_0": {"2026": 0.0, "2027": 40.0, "LT": 90.0,
                                                                       "LT_from": 2031},
                                                            "n1_1": {"2026": 0.0, "2028": 25.0}}})
    assert _check_rub_formula(t) > 0
    # у сценариев с разными рублями — свои ряды вычета (при тех же RWA разность — ровно разность рублей)
    run = grid({**QUIET, **rub(), **shares()})
    tl, ids = run.ctx.timeline, scenarios()
    for w in run.ctx.book.get("worlds.ids"):
        for r in run.ctx.book.get("regimes.ids"):
            a, b = run.cell(w, r, ids[0]), run.cell(w, r, ids[2])
            assert a.quarters["rwa"] == b.quarters["rwa"]           # «тихая» книга: путь капитала от сценария не зависит
            for q in range(1, tl.Q + 1):
                diff = drub(run, ids[2], "n20_0", q) - drub(run, ids[0], "n20_0", q)
                assert close(b.quarters["ded20"][q] - a.quarters["ded20"][q], diff, abs_=1e-9), (w, r, q)
            assert b.quarters["ded20"][tl.Q] - a.quarters["ded20"][tl.Q] > 50.0


def _frozen_pp(base: Any, rub_q: list[float], rwa: tuple, tl: Any) -> dict[str, float]:
    """Запись пути в п.п. с рублями, поделёнными на ряд RWA: ключи кварталов до года `last_period` (в нём ключи
    квартала запрещены, М§0.4) и ключ года `last_period` — прежнее значение."""
    out = {}
    last_year = tl.year(tl.Q)
    for q in range(tl.Q + 1):
        if tl.year(q) == last_year:
            continue
        per = tl.period(q)
        out[per] = path_value(base, per) + rub_q[q] / rwa[q]
    out[str(last_year)] = path_value(base, tl.period(tl.Q))
    if isinstance(base, Mapping):                # ключи LT остаются: на них стоят оси книги (за сеткой не читаются)
        out.update({k: base[k] for k in ("LT", "LT_from") if k in base})
    return out


def check_rub_equals_the_record_on_own_rwa() -> None:
    """Свойство 10 М§4.11 на «тихой» книге: ключ и запись `deduction_pp + Drub / RWA_q` по ряду RWA самой клетки дают
    те же нормативы (1e-12), запись по RWA другой клетки — нормативы ниже ключа на `Drub × (1 / RWA_мод − 1 / RWA_q)`;
    Н20.1 с прибылью периода и слагаемые избытка терминала несут рубли — X_T = multiple × min_j (X⁰_j − Drub_j,s,Q)."""
    body = {**QUIET, **shares()}
    keyed, plain = grid({**body, **rub()}), grid(body)
    tl = keyed.ctx.timeline
    last_year = tl.year(tl.Q)
    multiple = float(keyed.ctx.book.get("valuation.terminal.excess_capital_multiple"))
    ids = scenarios()
    for c, base in zip(keyed.cells, plain.cells):
        assert c.quarters["rwa"] == base.quarters["rwa"] and c.quarters["bv"] == base.quarters["bv"], c.label
        for q in range(1, tl.Q + 1):
            r11 = drub(keyed, c.scenario, "n1_1", q)
            rwa = c.quarters["rwa"][q]
            assert close(c.quarters["n11_star"][q] - base.quarters["n11_star"][q], -r11 / rwa, abs_=1e-13)
        q_, b_ = c.quarters, base.quarters
        pend = b_["dpreg"][tl.Q] / b_["rwa"][tl.Q]
        x20 = (b_["n20"][tl.Q] - pend - b_["req20"][tl.Q]) * b_["rwa"][tl.Q] - drub(keyed, c.scenario, "n20_0", tl.Q)
        x11 = (b_["n11_star"][tl.Q] - pend - b_["req11"][tl.Q]) * b_["rwa"][tl.Q] - drub(keyed, c.scenario, "n1_1", tl.Q)
        assert close(c.x_t, multiple * min(x20, x11), rel=1e-9, abs_=1e-6), (c.label, c.x_t, x20, x11)
        assert c.x_t < base.x_t - 50.0
    for key, other in ((("N", "soft", ids[1]), ("M", "crisis", ids[1])), (("H", "norm", ids[2]), ("N", "soft", ids[2]))):
        c, mod = keyed.cell(*key), keyed.cell(*other)
        s = c.scenario
        node = keyed.ctx.book.get(f"capital.reg_scenarios.{s}.deduction_pp")
        out = {}
        for slot, rub_slot in (("n20_0", "n20_0"), ("n1_1", "n1_1")):
            rub_q = [drub(keyed, s, rub_slot, q) for q in range(tl.Q + 1)]
            out[f"own.{slot}"] = _frozen_pp(node[slot], rub_q, c.quarters["rwa"], tl)
            out[f"mod.{slot}"] = _frozen_pp(node[slot], rub_q, mod.quarters["rwa"], tl)
        own = grid({**body, f"capital.reg_scenarios.{s}.deduction_pp": {"n20_0": out["own.n20_0"],
                                                                        "n1_1": out["own.n1_1"]}})
        frozen = grid({**body, f"capital.reg_scenarios.{s}.deduction_pp": {"n20_0": out["mod.n20_0"],
                                                                           "n1_1": out["mod.n1_1"]}})
        a, b = own.cell(*key), frozen.cell(*key)
        assert a.quarters["rwa"] == c.quarters["rwa"] == b.quarters["rwa"]
        checked = 0
        for q in range(1, tl.Q + 1):
            if tl.year(q) == last_year:
                continue
            rwa, rwa_mod = c.quarters["rwa"][q], mod.quarters["rwa"][q]
            for name, slot in (("n20", "n20_0"), ("n11", "n1_1"), ("n11_star", "n1_1")):
                r = drub(keyed, s, slot, q)
                assert close(a.quarters[name][q], c.quarters[name][q], abs_=1e-12), (key, q, name)
                want = c.quarters[name][q] - r * (1 / rwa_mod - 1 / rwa)
                assert close(b.quarters[name][q], want, abs_=1e-12), (key, q, name)
            checked += drub(keyed, s, "n20_0", q) != 0 and abs(rwa_mod - rwa) > 1.0
        assert checked >= 20, (key, checked)


def check_bridge_row_of_deductions_carries_the_rubles() -> None:
    """Мост норматива выпуска (М§4.11, свойство 11): сумма строки вычетов — `−(E[Ded20_e] − Ded20_0)`, в ней изменение
    рублей сценария `−(E[Drub_e] − E[Drub_0])` рядом с ростом растущей части `−Dgrow_20 × (E[RWA_e] / RWA_0 − 1)`; доля
    — `сумма / E[RWA_e] + (A_e − A_0)` без рублей в A; тождество `start + Σ долей = end`. Ожидания — под вероятностями
    смеси заголовка, своим счётом теста."""
    from tests.support_core2 import contract
    from tests.support_core_pass3 import _release

    near = {f"capital.reg_scenarios.{s}.deduction_rub": {
        "n20_0": {"2026Q2": 0.0, "2026Q3": 15.0 + 10.0 * i, "2026Q4": 40.0 + 20.0 * i, "2027": 60.0, "LT": 100.0,
                  "LT_from": 2030},
        "n1_1": {"2026Q2": 0.0, "2026Q3": 10.0, "2026Q4": 30.0 - 5.0 * i, "LT": 80.0, "LT_from": 2030}}
        for i, s in enumerate(scenarios())}           # рубли — и в квартале конца моста (год даты оценки)
    for changes in ({**near, **shares()}, near):
        book = book_of(changes)
        rel, data = _release(book)
        assert not contract(data), contract(data)[:5]
        run, tl = rel.run, rel.run.ctx.timeline
        bridge = data["capital"]["bridge"]
        qe = tl.index(bridge["to"])
        an, neu = run.layers["analytical"].prob, run.layers["macro_neutral"].prob
        mix = {k: run.lam * an[k] + (1 - run.lam) * neu[k] for k in an}

        def mean(fn) -> float:
            return sum(mix[c.key] * fn(c) for c in run.cells)

        ded20_0, _, rwa0 = anchor_parts(run)
        eta20 = eta_of(run)[0]
        row = next(r for r in bridge["rows"] if r["key"] == "deductions")
        rub_e = mean(lambda c: drub(run, c.scenario, "n20_0", qe))
        rub_0 = mean(lambda c: drub(run, c.scenario, "n20_0", 0))
        rwa_e = mean(lambda c: c.quarters["rwa"][qe])
        amount = -(mean(lambda c: c.quarters["ded20"][qe]) - mean(lambda c: c.quarters["ded20"][0]))
        assert close(amount, -(1 - eta20) * ded20_0 * (rwa_e / rwa0 - 1) - (rub_e - rub_0), abs_=1e-6)
        assert close(row["amount"], amount, abs_=0.005 + 1e-9) and rub_e - rub_0 > 20.0      # сумма выпуска — 2 знака
        a_e = mean(lambda c: c.quarters["n20"][qe] - c.quarters["k20"][qe] / c.quarters["rwa"][qe])
        a_0 = mean(lambda c: c.quarters["n20"][0] - c.quarters["k20"][0] / c.quarters["rwa"][0])
        gap = float(book.get(G20))
        want_a = gap - mean(lambda c: path_value(book.get(f"capital.reg_scenarios.{c.scenario}.deduction_pp.n20_0"),
                                                 tl.period(qe)))
        assert close(a_e, want_a, abs_=1e-12)                 # A — поправка и путь в п.п.: рублей в нём нет
        assert close(row["pp"], amount / rwa_e + (a_e - a_0), abs_=2e-6)
        assert close(bridge["start"] + sum(r["pp"] for r in bridge["rows"]), bridge["end"], abs_=1e-9)


def reanchored_const(c: CapitalConst, row: Mapping[str, float], rub20: float, rub11: float) -> CapitalConst:
    """Книга после переноса якоря на строку `row` с траекторией рублей как есть (М§4.11, §15.2 п. 3): вычеты нового
    якоря — разности капиталов строки, суммы Dfix — прежние, RWA якоря — RWA строки, поправки — калибровкой к
    нормативам строки (строка нового якоря вычитает рубли квартала ещё раз)."""
    old = ratios(c, rub20=rub20, rub11=rub11, **row)
    bvreg = row["bv"] + row["dpreg"] - (1 - c.fvoci_recognition) * row["reserve"]
    ded20, ded11 = bvreg + c.at1 + row["t2"] - old.k20, bvreg - max(row["unaudited"], 0.0) - old.k11
    fix20, fix11 = c.parts.fix20, c.parts.fix11
    new = CapitalConst(ded20_0=ded20, ded11_0=ded11, rwa0=row["rwa"], fvoci_recognition=c.fvoci_recognition,
                       gap20=c.gap20, gap11=c.gap11, at1=c.at1, audit_cutoffs=c.audit_cutoffs, buffer20=0.0,
                       buffer11=0.0, parts=deduction_parts(ded20, ded11, fix20 / ded20, fix11 / ded11))
    probe = ratios(new, rub20=rub20, rub11=rub11, **row)
    return CapitalConst(**{**new.__dict__, "gap20": c.gap20 + (old.n20 - probe.n20),
                           "gap11": c.gap11 + (old.n11 - probe.n11)})


def check_reanchor_keeps_the_ratios() -> None:
    """Свойство 12 М§4.11: перенос якоря с траекторией рублей как есть сохраняет нормативы всех кварталов любой клетки
    — тождество `Ded′_j,q + (dpp − gap′_j) × RWA_q = Ded_j,q + (dpp − gap_j) × RWA_q` при любом RWA_q (и в клетке с
    другим RWA); поправка нового якоря выше на `Drub_j,s,1 / RWA_1`."""
    rnd = random.Random(851)
    for _ in range(300):
        ded20, ded11 = rnd.uniform(100.0, 1500.0), rnd.uniform(100.0, 1500.0)
        c = CapitalConst(ded20_0=ded20, ded11_0=ded11, rwa0=rnd.uniform(1e3, 5e4), fvoci_recognition=rnd.random(),
                         gap20=rnd.uniform(-0.01, 0.01), gap11=rnd.uniform(-0.01, 0.01), at1=rnd.uniform(0.0, 300.0),
                         audit_cutoffs=(4,), buffer20=0.0, buffer11=0.0,
                         parts=deduction_parts(ded20, ded11, rnd.random(), rnd.random()))
        row1 = dict(bv=rnd.uniform(5e3, 2e4), dpreg=rnd.uniform(0.0, 300.0), reserve=rnd.uniform(-500.0, 100.0),
                    unaudited=rnd.uniform(-100.0, 600.0), t2=rnd.uniform(0.0, 600.0), rwa=c.rwa0 * rnd.uniform(0.8, 1.6),
                    ded_pp20=rnd.uniform(0.0, 0.01), ded_pp11=rnd.uniform(0.0, 0.01))
        r1 = (rnd.uniform(-200.0, 400.0), rnd.uniform(-200.0, 400.0))
        new = reanchored_const(c, row1, *r1)
        assert close(new.gap20 - c.gap20, r1[0] / row1["rwa"], abs_=1e-12)
        assert close(new.gap11 - c.gap11, r1[1] / row1["rwa"], abs_=1e-12)
        assert close(new.parts.fix20, c.parts.fix20, rel=1e-12) and close(new.parts.fix11, c.parts.fix11, rel=1e-12)
        for _ in range(5):
            row = dict(row1, bv=rnd.uniform(5e3, 3e4), rwa=c.rwa0 * rnd.uniform(0.5, 3.0), unaudited=rnd.uniform(0, 500))
            rq = (rnd.uniform(-300.0, 500.0), rnd.uniform(-300.0, 500.0))
            a, b = ratios(c, rub20=rq[0], rub11=rq[1], **row), ratios(new, rub20=rq[0], rub11=rq[1], **row)
            for name in ("n20", "n11", "n11_star"):
                assert close(getattr(a, name), getattr(b, name), abs_=1e-12), (name, row)


def check_schema_of_the_rubles() -> None:
    """Ограничение № 23: объект у части сценариев, объект без одной траектории, лишний ключ, `null` — отказ; у всех
    сценариев с обеими траекториями — книга проходит."""
    ids = scenarios()
    full = rub()

    def refused(changes: Mapping[str, Any], *words: str) -> None:
        try:
            validate(book_dict(changes))
        except BookError as exc:
            assert all(w in str(exc) for w in words), (str(exc)[:400], words)
            return
        raise AssertionError(f"схема приняла {list(changes)}")

    validate(book_dict(full))
    refused({k: v for k, v in full.items() if ids[2] not in k}, f"capital.reg_scenarios.{ids[2]}.deduction_rub",
            "всех сценариев")
    one = dict(full)
    one[f"capital.reg_scenarios.{ids[0]}.deduction_rub"] = {"n20_0": 10.0}
    refused(one, "deduction_rub.n1_1", "нет ключа")
    extra = dict(full)
    extra[f"capital.reg_scenarios.{ids[1]}.deduction_rub"] = {"n20_0": 1.0, "n1_1": 1.0, "n11": 1.0}
    refused(extra, "незнакомый ключ")
    null = dict(full)
    null[f"capital.reg_scenarios.{ids[1]}.deduction_rub"] = {"n20_0": {"2027": None}, "n1_1": 0.0}
    refused(null, "null")
    refused({**full, f"capital.reg_scenarios.{ids[0]}.deduction_rub": None}, "null")


# ------------------------------------------------------------------ путь постоянной части прочих активов (М§4.3)


def _dn(run: GridRun, q: int) -> float:
    """Dn_q — дрейф плотности RWA по ключам книги (М§4.11), своим счётом."""
    book, tl = run.ctx.book, run.ctx.timeline
    rate, until = float(book.get("capital.rwa.density_drift_rate")), int(book.get("capital.rwa.density_drift_until"))
    out = 1.0
    for x in range(1, q + 1):
        if tl.year(x) <= until:
            out *= (1 + rate) ** 0.25
    return out


def delta_of(run: GridRun, q: int) -> float:
    traj = run.ctx.book.opt(CHANGE)
    if traj is None:
        return 0.0
    tl = run.ctx.timeline
    return path_value(traj, tl.period(q)) - path_value(traj, tl.period(0))


def _rwa_base(run: GridRun, c: Any, q: int) -> tuple[float, float]:
    """(база RWA квартала по остаткам книг клетки и плотностям книги с весом приращения ω_Δ, её часть постоянных
    прочих активов) — своим счётом (М§4.11)."""
    book = run.ctx.book
    dens = book.get("capital.rwa.density")
    level = float(book.opt(LEVEL, 0.0))
    delta = delta_of(run, q)
    w_fixed = float(dens.get("other_assets_fixed", 0.0))
    w_change = float(dens.get("other_assets_fixed_change", w_fixed))
    base = sum(float(dens[b]) * c.books[b]["balance"][q] for b in dens if b in c.books and b not in
               ("securities", "liquidity"))
    base += float(dens["securities"]) * c.quarters["securities"][q] + float(dens["liquidity"]) * c.quarters["liquidity"][q]
    fixed = w_fixed * level + w_change * delta
    base += float(dens["other_assets"]) * (c.quarters["other_assets"][q] - level - delta) + fixed
    return base, fixed


def check_fixed_change_rows() -> None:
    """Путь постоянной части (М§4.3, §4.11): в каждом квартале прочие активы клетки — `other_assets_to_loans × Σ
    кредитов + OA_fixed + ΔOA_q`, RWA, пересчитанные по остаткам книг клетки формулой с весом ω_Δ, — её ряд;
    без ключа плотности приращения — те же ряды, что с ключом, равным ω_oaf, бит в бит; тождество баланса держится."""
    keyed = grid(FIXED)
    no_key = grid({k: v for k, v in FIXED.items() if k != W_CHANGE})
    as_oaf = grid({**FIXED, W_CHANGE: FIXED[W_FIXED]})
    R.cells_equal(no_key, as_oaf)
    tl = keyed.ctx.timeline
    ratio = float(keyed.ctx.book.get("volumes.other_assets_to_loans"))
    for run in (keyed, no_key):
        moved = 0
        for c in run.cells:
            for q in range(tl.Q + 1):
                delta = delta_of(run, q)
                want = ratio * c.quarters["loans"][q] + FIXED[LEVEL] + delta
                if q:
                    assert close(c.quarters["other_assets"][q], want, rel=1e-12), (c.label, q)
                    assert close(c.quarters["assets"][q], c.quarters["liabilities_equity"][q], rel=1e-12), (c.label, q)
                base, _ = _rwa_base(run, c, q)
                assert close(c.quarters["rwa"][q], base * _dn(run, q), rel=1e-12), (c.label, q)
                moved += delta != 0
        assert moved >= 36 * 30
    # вес уходящей части — разный: при ω_Δ = 0 RWA выше, чем при ω_Δ = ω_oaf (часть уходит без веса)
    assert keyed.ctx.prep.rwa_w.oa_change == 0.0 and no_key.ctx.prep.rwa_w.oa_change == FIXED[W_FIXED]


def check_fixed_change_money_goes_to_balancing() -> None:
    """Деньги убывания постоянной части (М§4.3, §4.10): на книге, у которой путь капитала и кредиты от нормативов не
    зависят, нетто балансирующих статей (бумаги + ликвидность − опт) конца квартала выше, чем без пути, ровно на
    `−ΔOA_q` плюс разность капитала; средний остаток квартала получает приращение квартала наполовину."""
    keyed, zero = grid({**QUIET, **FIXED}), grid({**QUIET, **FIXED, CHANGE: 0.0})
    tl = keyed.ctx.timeline
    net = lambda c, q: c.quarters["securities"][q] + c.quarters["liquidity"][q] - c.quarters["wholesale"][q]  # noqa
    avg = lambda c, q: sum(c.books[b]["avg"][q] * s for b, s in (("securities", 1), ("liquidity", 1), ("wholesale", -1)))  # noqa
    for c, z in zip(keyed.cells, zero.cells):
        assert c.quarters["loans"] == z.quarters["loans"] and c.quarters["div"] == z.quarters["div"], c.label
        for q in range(1, tl.Q + 1):
            d_bv = c.quarters["bv"][q] - z.quarters["bv"][q]
            delta = delta_of(keyed, q)
            assert close(net(c, q) - net(z, q), d_bv - delta, rel=1e-11, abs_=1e-7), (c.label, q)
            d_bv0 = c.quarters["bv"][q - 1] - z.quarters["bv"][q - 1]
            want = d_bv0 - (delta_of(keyed, q - 1) + delta) / 2
            assert close(avg(c, q) - avg(z, q), want, rel=1e-11, abs_=1e-7), (c.label, q)
        assert c.quarters["bv"][tl.Q] > z.quarters["bv"][tl.Q]          # деньги убывания зарабатывают
    # деньги — при связанном минимуме ликвидности сначала гасится добор опта
    tight = {"volumes.liquid_min_share": 0.45}
    keyed, zero = grid({**QUIET, **FIXED, **tight}), grid({**QUIET, **FIXED, **tight, CHANGE: 0.0})
    hit = 0
    for c, z in zip(keyed.cells, zero.cells):
        for q in range(1, tl.Q + 1):
            if z.quarters["wholesale_extra"][q] > 0 and delta_of(keyed, q) < 0:
                hit += c.quarters["wholesale_extra"][q] < z.quarters["wholesale_extra"][q]
            assert close(net(c, q) - net(z, q), c.quarters["bv"][q] - z.quarters["bv"][q] - delta_of(keyed, q),
                         rel=1e-11, abs_=1e-7), (c.label, q)
    assert hit >= 36, hit


def check_schema_of_the_fixed_change() -> None:
    """Ограничения № 8 и № 24: путь, который начинается ключом года после якоря (правило 6 §0.4 читает его значение и
    в квартале якоря), — отказ якорного условия; ноль ключом года якоря — книга проходит, остаток записи в пределах
    порога — тоже; отрицательная постоянная часть — у книги и на конце оси (ось-число на элементе траектории, связка
    на уровне, ось-сдвиг) — отказ; путь без плотностей и отрицательная плотность приращения — отказ."""
    def refused(changes: Mapping[str, Any], *words: str) -> None:
        try:
            validate(book_dict(changes))
        except BookError as exc:
            assert all(w in str(exc) for w in words), (str(exc)[:500], words)
            return
        raise AssertionError(f"схема приняла {changes}")

    validate(book_dict(FIXED))
    validate(book_dict({**FIXED, CHANGE: {"2026": 4e-10, "2027": -60.0}}))
    refused({**FIXED, CHANGE: {"2027": -60.0, "2029": -200.0}}, "квартале якоря", CHANGE)
    refused({**FIXED, CHANGE: {"2026Q2": 0.5, "2027": -60.0}}, "квартале якоря")
    refused({**FIXED, CHANGE: {"2026": 0.0, "2027": -600.0, "2029": -1300.0}}, "< 0")
    refused({**FIXED, LEVEL: 0.0, CHANGE: {"2026": 0.0, "2027": -1.0}}, "< 0")
    axes = copy.deepcopy(fixture_dict()["valuation"]["uncertainty"]["axes"])
    value_axis = {"name": "путь", "kind": "value", "paths": [f"{CHANGE}.2029"], "low": -1300.0, "high": -100.0,
                  "dist": "triangular"}
    refused({**FIXED, "valuation.uncertainty.axes": axes + [value_axis]}, "axes[", "< 0")
    validate(book_dict({**FIXED, "valuation.uncertainty.axes": axes + [dict(value_axis, low=-1100.0)]}))
    bundle = {"name": "уровень", "kind": "bundle", "paths": [LEVEL, S20], "low": {LEVEL: 100.0, S20: 0.4},
              "high": {LEVEL: 1300.0, S20: 0.8}, "dist": "triangular"}
    refused({**FIXED, **shares(), "valuation.uncertainty.axes": axes + [bundle]}, "low", "< 0")
    shift = {"name": "сдвиг", "kind": "shift", "paths": [CHANGE], "low": -1000.0, "high": 50.0, "dist": "triangular"}
    refused({**FIXED, "valuation.uncertainty.axes": axes + [shift]}, "квартале якоря")
    refused({k: v for k, v in FIXED.items() if k not in (W_FIXED, W_CHANGE)} | {LEVEL: 0.0},
            "other_assets_fixed_change", "плотности")
    validate(book_dict({k: v for k, v in FIXED.items() if k != W_FIXED} | {LEVEL: 0.0,
                                                                          CHANGE: {"2026": 0.0, "2027": 50.0}}))
    refused({**FIXED, W_CHANGE: -0.1}, "other_assets_fixed_change", "≥ 0")


def check_fixed_change_is_an_input_of_the_pass() -> None:
    """Путь постоянной части и рубли сценария — входы прохода клеток (отпечаток меняется), доля λ_F — нет: смена
    λ_F пересчитывает только оценку (М§7)."""
    base = book_of({**FIXED, **rub()})
    key = lambda changes: path_key(path_inputs(run_grid(book_of(changes), fixture_facts()).ctx))  # noqa: E731
    k0 = key({**FIXED, **rub()})
    assert k0 == key({**FIXED, **rub(), LAM: 0.0}) == key({**FIXED, **rub(), LAM: 0.5})
    assert k0 != key({**FIXED, **rub(1.5)}) and k0 != key({**FIXED, **rub(), CHANGE: {"2026": 0.0, "2030": -9.0}})
    assert base.get(LEVEL) == FIXED[LEVEL]


# ------------------------------------------------------------------ терминал с постоянными частями (М§7)


PARTS: dict[str, Any] = {**FIXED, **rub(), **shares(), **SOFT_MULT}


def _bv_q(c: Any) -> float:
    return c.quarters["bv"][-1]


def check_terminal_rows_of_the_block() -> None:
    """Блок постоянных частей (М§7) по рядам конца сетки, своим счётом: F_A = OA_fixed + ΔOA_Q; R_F — часть RWA
    конца сетки, которую несут постоянные прочие активы (с весом ω_Δ у приращения, с множителем режима); C_j =
    Dfix_j + Drub_j,s,Q; κ_j = req_j,Q − (gap_j − dpp_j,s,Q) + Dgrow_j / RWA_0; связывающий норматив — тот, что задаёт
    X_T; y_m, I_F, B; строки ROE_T бизнеса, TV_RI и P_T при λ_F = 0 и 0,5 — по CI_T+1 и BV* книги с λ_F = 1;
    TV_DDM = BV_Q + TV_RI. Книги: Н20.0 связывает на T и Н20.1 связывает на T (C_11 и κ_11)."""
    bound = {"n20": 0, "n11": 0}
    for tight in ({}, N11_TIGHT):
        one = grid({**PARTS, **tight, LAM: 1.0})
        tl = one.ctx.timeline
        Q = tl.Q
        ded20_0, ded11_0, rwa0 = anchor_parts(one)
        eta20, eta11 = eta_of(one)
        book = one.ctx.book
        gap = {"n20": float(book.get(G20)), "n11": float(book.get(G11))}
        for lam in (0.0, 0.5):
            run = grid({**PARTS, **tight, LAM: lam})
            for c, c1 in zip(run.cells, one.cells):
                node, q_ = c.terminal_fixed, c.quarters
                assert node["lam_f"] == lam and c1.terminal_fixed["lam_f"] == 1.0
                assert close(node["f_a"], FIXED[LEVEL] + delta_of(run, Q), rel=1e-12), c.label
                base, fixed = _rwa_base(run, c, Q)
                assert close(node["r_f"], q_["rwa"][Q] * fixed / base, rel=1e-12), c.label
                pend = q_["dpreg"][Q] / q_["rwa"][Q]
                g20 = q_["n20"][Q] - pend - q_["req20"][Q]
                g11 = q_["n11_star"][Q] - pend - q_["req11"][Q]
                j = "n20" if g20 <= g11 else "n11"
                assert node["binding"] == j, c.label
                bound[j] += 1
                slot = "n20_0" if j == "n20" else "n1_1"
                eta, ded0 = (eta20, ded20_0) if j == "n20" else (eta11, ded11_0)
                assert close(node["c"], eta * ded0 + drub(run, c.scenario, slot, Q), rel=1e-12), c.label
                dpp = path_value(book.get(f"capital.reg_scenarios.{c.scenario}.deduction_pp.{slot}"), tl.period(Q))
                req = q_["req20"][Q] if j == "n20" else q_["req11"][Q]
                kappa = req - (gap[j] - dpp) + (1 - eta) * ded0 / rwa0
                assert close(node["kappa"], kappa, rel=1e-12), c.label
                f_k = node["c"] + kappa * node["r_f"]
                y_m = c.books["wholesale"]["rate"][Q] if q_["wholesale_extra"][Q] > 0 else \
                    (q_["securities"][Q] * c.books["securities"]["rate"][Q]
                     + q_["liquidity"][Q] * c.books["liquidity"]["rate"][Q]) / (q_["securities"][Q] + q_["liquidity"][Q])
                tau = q_["tau_eff"][Q]
                nci = float(book.get("pnl.nci_share"))
                i_f = -y_m * (node["f_a"] - f_k) * (1 - tau) * (1 - nci)
                assert close(node["f_k"], f_k, rel=1e-12) and close(node["d_f"], node["f_a"] - f_k, rel=1e-12, abs_=1e-9)
                assert close(node["i_f"], i_f, rel=1e-10, abs_=1e-9), (c.label, node["i_f"], i_f)
                # строки терминала — по CI_T+1 и BV* книги с λ_F = 1 (прохода λ_F не меняет)
                assert c.bv_star == c1.bv_star and c.x_t == c1.x_t and c.quarters["bv"] == c1.quarters["bv"]
                w = 1 - lam
                k, g = c.k_t, c.g_t
                ci = c1.roe_t_raw * c1.bv_star
                b = c1.bv_star - w * f_k
                assert close(node["business_capital"], b, rel=1e-12), c.label
                roe = (ci - w * (1 + g) * i_f) / b
                assert close(c.roe_t_raw, roe, rel=1e-11, abs_=1e-13), (c.label, c.roe_t_raw, roe)
                fade = float(book.get(FADE))
                x = roe - k
                roe_f = k + fade * max(x, 0.0) + min(x, 0.0)
                assert close(c.roe_t, roe_f, rel=1e-11, abs_=1e-13), c.label
                tv_ri = (roe_f - k) * b / (k - g) + w * (i_f - k * f_k) / k
                p_t = (roe_f - g) * b / (k - g) + w * i_f / k
                assert close(c.tv_ri, tv_ri, rel=1e-10, abs_=1e-6), (c.label, c.tv_ri, tv_ri)
                assert close(c.tv_ddm, c.x_t + p_t, rel=1e-10, abs_=1e-6), c.label
                assert close(c.tv_ddm - c.tv_ri, _bv_q(c), rel=1e-11, abs_=1e-6), c.label
    assert min(bound.values()) >= 36, bound
    mult = grid({**PARTS, LAM: 0.0}).cell("N", "soft", scenarios()[0])
    assert mult.terminal_fixed["r_f"] > 0 and mult.quarters["rwa"][-1] > 0


def check_ddm_equals_ri_at_any_share() -> None:
    """Равенство форм §6.4 п. 12: V_DDM = V_RI в каждой клетке при λ_F = 0; 0,5; 1 (и при угасании 0,5, и у фикстуры
    докапитализации) — инвариант `ddm_equals_ri` держится; TV_DDM − TV_RI = BV_Q."""
    for extra in ({}, {FADE: 0.5}):
        for lam in (0.0, 0.5, 1.0):
            run = grid({**PARTS, **extra, LAM: lam})
            for c in run.cells:
                assert close(c.v_ddm, c.v_ri, rel=1e-11, abs_=1e-7), (c.label, lam, c.v_ddm, c.v_ri)
                assert close(c.tv_ddm - c.tv_ri, _bv_q(c), rel=1e-11, abs_=1e-6), (c.label, lam)
            fired = [f.name for f in check_invariants(run) if f.fired]
            assert not fired, fired
    for lam in (0.0, 0.5):
        run = R.grid_of({**rub(), **shares(), LAM: lam})
        assert any(c.pvd > 0 for c in run.cells)
        for c in run.cells:
            assert close(c.v_ddm, c.v_ri, rel=1e-9, abs_=1e-6), (c.label, lam)


def check_no_fixed_parts_value_is_independent_of_the_share() -> None:
    """Без постоянных частей (F_A = R_F = C = 0) оценка от λ_F не зависит: клетки и слои — числа книги без ключа."""
    base = fixture_run()
    for lam in (0.0, 0.5):
        run = grid({LAM: lam})
        for a, b in zip(base.cells, run.cells):
            assert close(a.v_ri, b.v_ri, rel=1e-13, abs_=1e-9) and close(a.tv_ri, b.tv_ri, rel=1e-13, abs_=1e-9)
            assert b.terminal_fixed["f_k"] == 0 and b.terminal_fixed["business_capital"] == b.bv_star
        assert close(base.point, run.point, abs_=1e-9)


def _asset_facts(amount: float) -> Facts:
    """Факты фикстуры с бездоходным активом: прочие активы и капитал акционеров якоря больше на `amount`."""
    base = fixture_facts()
    files = copy.deepcopy(dict(base.files))
    files["balance"]["other_assets"]["v"] = float(files["balance"]["other_assets"]["v"]) + amount
    files["balance"]["equity"]["bv_common"]["v"] = float(files["balance"]["equity"]["bv_common"]["v"]) + amount
    return Facts(root=base.root, files=files, digest=f"{base.digest}+asset{amount}")


def check_neutral_asset() -> None:
    """Нейтральность §7: актив A без дохода, вычтенный из капитала один к одному (вычет сценария в рублях A во всех
    кварталах), с весом риска 0 и оплаченный капиталом (капитал якоря + A) — при λ_F = 0 оценка клетки та же, что без
    актива (отн. 1e-9); при λ_F = 1 разность — `DF_v(τ_Q) × A × (1 − φ × k_T / (k_T − g_T))`, φ — множитель угасания
    клетки (fade при положительном избытке, иначе 1); при 0,5 — половина (оценка линейна по λ_F в одной ветви).
    Минимум ликвидности книги проверки — ноль (`NO_LIQUIDITY_MINIMUM`): он считается от всех небалансирующих активов,
    и актив поднимал бы добор опта — канал прохода, а не терминала."""
    facts = _asset_facts(ASSET)
    asset = {LEVEL: ASSET, W_FIXED: 0.0, **rub(flat=ASSET)}
    for extra in (NO_LIQUIDITY_MINIMUM, {**NO_LIQUIDITY_MINIMUM, FADE: 0.5}):
        plain = {lam: grid({**extra, LAM: lam}) for lam in (0.0, 0.5, 1.0)}
        held = {lam: grid({**asset, **extra, LAM: lam}, facts=facts, tag="asset") for lam in (0.0, 0.5, 1.0)}
        same = above_k = 0
        for i, a in enumerate(plain[1.0].cells):
            branch = {run.cells[i].roe_t_raw > run.cells[i].k_t for run in (*plain.values(), *held.values())}
            for lam in (0.0, 0.5, 1.0):
                x, y = plain[lam].cells[i], held[lam].cells[i]
                assert all(close(u, v, abs_=1e-13) for u, v in zip(x.quarters["n20"], y.quarters["n20"])), x.label
                assert all(close(u, v, rel=1e-12) for u, v in zip(x.quarters["rwa"], y.quarters["rwa"])), x.label
                assert all(close(v - u, ASSET, abs_=1e-8) for u, v in zip(x.quarters["bv"], y.quarters["bv"]))
                if lam == 0.0:
                    assert close(y.v_ri, x.v_ri, rel=1e-9, abs_=1e-9), (x.label, y.v_ri - x.v_ri)
                    assert close(y.tv_ddm, x.tv_ddm, rel=1e-11, abs_=1e-7) and close(y.tv_ri, x.tv_ri - ASSET, abs_=1e-6)
                if len(branch) != 1:
                    continue                    # актив сдвинул клетку через k_T: ветвь угасания — другая
                df = plain[lam].ctx.discounts[x.world].dfq[plain[lam].ctx.timeline.Q]
                above = x.roe_t_raw > x.k_t
                phi = float(plain[lam].ctx.book.get(FADE)) if above else 1.0
                want = lam * df * ASSET * (1 - phi * x.k_t / (x.k_t - x.g_t))
                assert close(y.v_ri - x.v_ri, want, rel=1e-8, abs_=1e-9 * abs(x.v_ri)), (x.label, lam, y.v_ri - x.v_ri, want)
            same += len(branch) == 1
            above_k += len(branch) == 1 and a.roe_t_raw > a.k_t
        assert same >= 30 and above_k >= 5, (same, above_k)


def check_linearity_and_sides() -> None:
    """В клетке с одной ветвью угасания бизнеса оценка линейна по λ_F (V(0,5) — середина V(0) и V(1)); цена ключа
    (λ_F = 0 против 1) — сумма цен сторон капитала (F_A = R_F = 0) и баланса (C_j = 0) на том же проходе."""
    for extra in ({}, {FADE: 0.5}):
        runs = {lam: grid({**PARTS, **extra, LAM: lam}) for lam in (0.0, 0.5, 1.0)}
        lin = 0
        for c0, ch, c1 in zip(runs[0.0].cells, runs[0.5].cells, runs[1.0].cells):
            branch = {c.roe_t_raw > c.k_t for c in (c0, ch, c1)}
            if len(branch) == 1:
                assert close(ch.v_ri, (c0.v_ri + c1.v_ri) / 2, rel=1e-10, abs_=1e-7), c0.label
                lin += 1
        assert lin >= 30, lin
        run = runs[0.0]
        ctx = run.ctx
        paths = {(p.world, p.regime, p.scenario): p for p in run_paths(ctx)}
        p = ctx.prep
        summed = 0
        for c in run.cells:
            path = paths[c.key]
            disc = ctx.discounts[c.world]

            def tv(lam: float, fixed: Mapping[str, float]) -> Any:
                return terminal(**path.terminal, real_growth=p.real_growth, fade=p.fade, multiple=p.multiple,
                                k_t=disc.k_t, symmetric=p.fade_symmetric, fixed=fixed, lam_f=lam)

            blk = dict(path.fixed)
            sides = {"both": blk, "capital": {**blk, "f_a": 0.0, "r_f": 0.0}, "balance": {**blk, "c20": 0.0, "c11": 0.0}}
            ref = tv(1.0, blk)
            assert close(ref.tv_ri, runs[1.0].cell(*c.key).tv_ri, rel=1e-12, abs_=1e-9)
            got = {k: tv(0.0, b) for k, b in sides.items()}
            assert close(got["both"].tv_ri, c.tv_ri, rel=1e-12, abs_=1e-9)
            if len({t.roe_raw > t.k_t for t in (ref, *got.values())}) != 1:
                continue
            price = {k: t.tv_ri - ref.tv_ri for k, t in got.items()}
            assert close(price["both"], price["capital"] + price["balance"], rel=1e-9, abs_=1e-6), (c.label, price)
            summed += abs(price["capital"]) > 1.0 and abs(price["balance"]) > 1.0
        assert summed >= 20, summed


# ------------------------------------------------------------------ отказы и случаи терминала по входам (М§7)


def _sample_terminal(t: Mapping[str, float], **over: Any) -> dict[str, Any]:
    kw = dict(n20=t["n20"], req20=t["req20"], n11_star=t["n11_star"], req11=t["req11"], rwa=t["rwa"], bv_q=t["bv_q"],
              pbt_last_year=t["pbt_l"], y_balancing=t["y_bal"], c_wholesale=t["c_wh"], headroom=t["headroom"],
              tau_eff=t["tau"], nci_share=t["nci"], coupon_annual=t["coupon"], tau_stat=t["tau_stat"],
              lt_inflation=t["lt_inflation"], real_growth=t["real_growth"], fade=t["fade"], multiple=t["multiple"],
              k_t=t["k_t"], min_share=t["min_share"], wholesale_extra=t["wt"])
    kw.update(over)
    return kw


def check_binding_wholesale_and_refusal() -> None:
    """Связывающий на T норматив — тот, что задаёт X_T (при равенстве Н20.0): блок берёт C_11 и κ_11, когда связывает
    Н20.1; при доборе опта WT_Q > 0 — ставку опта, иначе смесь балансирующих; доход блока — после налога и доли
    неконтролирующих; B ≤ 0 — отказ с названием клетки."""
    g3 = EXAMPLE["terminal"]["inputs"]
    t, blk = g3["terminal"], g3["block"]
    for n20, req20, n11, req11, want in ((0.14, 0.13, 0.13, 0.115, "n20"), (0.14, 0.13, 0.12, 0.115, "n11"),
                                         (0.375, 0.25, 0.3125, 0.1875, "n20")):     # последний — равенство (точно)
        term = terminal(**_sample_terminal(t, n20=n20, req20=req20, n11_star=n11, req11=req11, pbt_last_year=160.0),
                        fixed=blk, lam_f=0.0)
        assert term.fixed["binding"] == want, (n20, n11, term.fixed)
        assert term.fixed["c"] == blk["c20" if want == "n20" else "c11"]
        assert term.fixed["kappa"] == blk["kappa20" if want == "n20" else "kappa11"]
    plain = terminal(**_sample_terminal(t, pbt_last_year=160.0), fixed=blk, lam_f=0.0)
    topped = terminal(**_sample_terminal(t, pbt_last_year=160.0, wholesale_extra=50.0), fixed=blk, lam_f=0.0)
    d_f = blk["f_a"] - (blk["c20"] + blk["kappa20"] * blk["r_f"])
    assert close(plain.fixed["i_f"], -t["y_bal"] * d_f * (1 - t["tau"]) * (1 - t["nci"]), rel=1e-12)
    assert close(topped.fixed["i_f"], -t["c_wh"] * d_f * (1 - t["tau"]) * (1 - t["nci"]), rel=1e-12)
    taxed = terminal(**_sample_terminal(t, pbt_last_year=160.0, nci_share=0.1, tau_eff=0.3), fixed=blk, lam_f=0.0)
    assert close(taxed.fixed["i_f"], -t["y_bal"] * d_f * 0.7 * 0.9, rel=1e-12)
    huge = dict(blk, c20=5000.0)
    try:
        terminal(**_sample_terminal(t, pbt_last_year=160.0), fixed=huge, lam_f=0.0, where="клетка N/soft/schedule")
    except BookError as exc:
        assert "клетка N/soft/schedule" in str(exc) and "B" in str(exc), str(exc)
    else:
        raise AssertionError("B ≤ 0 принят")
    one = terminal(**_sample_terminal(t, pbt_last_year=160.0), fixed=huge, lam_f=1.0)     # λ_F = 1: прежняя ветвь
    assert one.fixed["business_capital"] == one.bv_star


def check_schema_of_the_share() -> None:
    """Ограничение № 25: λ_F вне [0; 1] (и конец оси на её пути) — отказ; 0 и 1 — книга проходит; ключи — в схеме."""
    for lam in (0.0, 1.0, 0.5):
        validate(book_dict({LAM: lam}))
    for bad in (-0.01, 1.2):
        try:
            validate(book_dict({LAM: bad}))
        except BookError as exc:
            assert LAM in str(exc), str(exc)[:300]
        else:
            raise AssertionError(bad)
    axes = copy.deepcopy(fixture_dict()["valuation"]["uncertainty"]["axes"])
    axis = {"name": "λ_F", "kind": "value", "paths": [LAM], "low": 0.0, "high": 1.0, "dist": "triangular"}
    validate(book_dict({LAM: 0.0, "valuation.uncertainty.axes": axes + [axis]}))
    try:
        validate(book_dict({LAM: 0.0, "valuation.uncertainty.axes": axes + [dict(axis, high=1.5)]}))
    except BookError as exc:
        assert "конец оси" in str(exc)
    else:
        raise AssertionError("конец оси λ_F вне [0; 1] принят")


# ------------------------------------------------------------------ пример приложения H (М§17)


def _g1_row(q: Mapping[str, float], frozen: Mapping[str, float] | None = None) -> dict[str, float]:
    row = dict(bv=q["bv"], dpreg=q["dpreg"], reserve=q["reserve"], unaudited=q["e"], t2=q["t2"], rwa=q["rwa"],
               ded_pp20=q["dpp20"], ded_pp11=q["dpp11"])
    if frozen is not None:
        row.update(ded_pp20=frozen["dpp20"], ded_pp11=frozen["dpp11"])
    return row


def check_example_g() -> None:
    """Пример приложения H (H.1–H.3) — функциями ядра до 1e-9: строки вычета с рублями и замороженная запись,
    слагаемые X_T и C_j, строка вычетов моста, нормативы после переноса якоря; RWA прочих активов с весом
    приращения, сдвиг балансирующих активов и отказы пути; терминал и оценка синтетической клетки при λ_F = 1; 0,5;
    0 — с бездоходным активом и без, по сторонам."""
    ex = EXAMPLE["deduction_rub"]
    inp = ex["inputs"]
    parts = deduction_parts(inp["ded20_0"], inp["ded11_0"], inp["eta20"], inp["eta11"])
    c = CapitalConst(ded20_0=inp["ded20_0"], ded11_0=inp["ded11_0"], rwa0=inp["rwa0"],
                     fvoci_recognition=inp["fvoci_recognition"], gap20=inp["gap20"], gap11=inp["gap11"], at1=inp["at1"],
                     audit_cutoffs=(1, 2, 3, 4), buffer20=0.0, buffer11=0.0, parts=parts)
    for name, src in (("anchor", "anchor"), ("quarter", "quarter"), ("other_cell", "other_cell")):
        q = inp[src]
        got = ratios(c, rub20=q["rub20"], rub11=q["rub11"], **_g1_row(q))
        for f in ("ded20", "ded11", "k20", "k11", "n20", "n11", "n11_star"):
            assert close(getattr(got, f), ex[name][f], abs_=TOL), (name, f, getattr(got, f), ex[name][f])
        if name != "anchor":
            frozen = ratios(c, **_g1_row(q, ex[f"{name}_frozen"]))
            for f in ("ded20", "ded11", "k20", "k11", "n20", "n11", "n11_star"):
                assert close(getattr(frozen, f), ex[f"{name}_frozen"][f], abs_=TOL), (name, f)
    q = inp["quarter"]
    row = ratios(c, rub20=q["rub20"], rub11=q["rub11"], **_g1_row(q))
    pend = q["dpreg"] / q["rwa"]
    term = ex["terminal"]
    x20, x11 = (row.n20 - pend - inp["req20"]) * q["rwa"], (row.n11_star - pend - inp["req11"]) * q["rwa"]
    assert close(x20, term["x20"], abs_=TOL) and close(x11, term["x11"], abs_=TOL)
    assert close(min(x20, x11) * inp["excess_capital_multiple"], term["x_t"], abs_=TOL)
    assert close(parts.fix20 + q["rub20"], term["c20"], abs_=TOL) and close(parts.fix11 + q["rub11"], term["c11"], abs_=TOL)
    a0 = ratios(c, rub20=0.0, rub11=0.0, **_g1_row(inp["anchor"]))
    br = ex["bridge"]
    amount = -(row.ded20 - a0.ded20)
    assert close(amount, br["deductions_amount"], abs_=TOL)
    assert close(-parts.grow20 * (q["rwa"] / inp["rwa0"] - 1), br["deductions_growing"], abs_=TOL)
    a_e, a_0 = row.n20 - row.k20 / row.rwa, a0.n20 - a0.k20 / a0.rwa
    assert close(amount / q["rwa"] + (a_e - a_0), br["deductions_pp"], abs_=TOL)
    assert close(a0.k20 * (1 / q["rwa"] - 1 / inp["rwa0"]), br["rwa_growth_pp"], abs_=TOL)
    assert close((row.k20 - a0.k20) - amount, br["other_amount"], abs_=TOL)
    # перенос якоря на строку квартала с траекторией рублей как есть
    new = reanchored_const(c, _g1_row(q), q["rub20"], q["rub11"])
    ra = ex["reanchor"]
    for f, want in (("ded20_0", ra["ded20_0"]), ("ded11_0", ra["ded11_0"]), ("gap20", ra["gap20"]),
                    ("gap11", ra["gap11"])):
        assert close(getattr(new, f), want, abs_=TOL), (f, getattr(new, f), want)
    assert close(new.parts.fix20, ra["dfix20"], abs_=TOL) and close(new.parts.fix11, ra["dfix11"], abs_=TOL)
    nxt = inp["reanchor"]["next"]
    for label, rwa in (("next", nxt["rwa"]), ("next_other_rwa", inp["reanchor"]["next_other_rwa"])):
        q2 = dict(nxt, rwa=rwa)
        old, nw = (ratios(k, rub20=q2["rub20"], rub11=q2["rub11"], **_g1_row(q2)) for k in (c, new))
        for f in ("ded20", "ded11", "k20", "k11", "n20", "n11", "n11_star"):
            assert close(getattr(old, f), ra[label]["old"][f], abs_=TOL), (label, f)
            assert close(getattr(nw, f), ra[label]["new"][f], abs_=TOL), (label, f)
    # H.2
    g2 = EXAMPLE["fixed_change"]
    i2 = g2["inputs"]
    w = RwaWeights(loans={}, securities=i2["density_securities"], liquidity=i2["density_liquidity"],
                   other_assets=i2["density_oa"], oa_fixed=i2["oa_fixed"], other_assets_fixed=i2["density_oaf"],
                   oa_change=i2["density_change"])
    dflt = RwaWeights(**{**w.__dict__, "oa_change": i2["density_oaf"]})
    w_la = i2["securities_share"] * i2["density_securities"] + (1 - i2["securities_share"]) * i2["density_liquidity"]
    assert close(w_la, g2["w_la"], abs_=TOL)
    for r, loans in zip(g2["rows"], i2["loans"]):
        oa = i2["oa_ratio"] * loans + i2["oa_fixed"] + r["delta"]
        assert close(oa, r["oa"], abs_=TOL) and close(oa - r["delta"], r["oa_without_key"], abs_=TOL)
        assert close(w.rwa({}, 0.0, 0.0, oa, 1.0, 1.0, r["delta"]), r["rwa_oa"], abs_=TOL)
        assert close(dflt.rwa({}, 0.0, 0.0, oa, 1.0, 1.0, r["delta"]), r["rwa_oa_default_density"], abs_=TOL)
        assert close(w.rwa({}, 0.0, 0.0, r["oa_without_key"], 1.0, 1.0), r["rwa_oa_without_key"], abs_=TOL)
        assert close(-r["delta"], r["la_shift"], abs_=TOL) and close(-r["delta"] * w_la, r["rwa_la_shift"], abs_=TOL)
    path = {str(k): v for k, v in i2["path"].items()}
    assert _fixed_change_problems(i2["oa_fixed"], path, i2["anchor"], i2["periods"][-1], "путь") == []
    for case in g2["refusals"]:
        got = _fixed_change_problems(i2["oa_fixed"], {str(k): v for k, v in case["trajectory"].items()},
                                     i2["anchor"], i2["periods"][-1], "путь")
        assert got and case["result"] == "BookError", (case, got)
    # H.3
    g3 = EXAMPLE["terminal"]
    cell, t = g3["inputs"]["cell"], g3["inputs"]["terminal"]
    Q = len(cell["bv"]) - 1
    kq = cell["k_q"]
    disc = Discount(k=(0.0,) + (kq,) * Q, k_t=t["k_t"], dfq=tuple((1 + kq) ** -q for q in range(Q + 1)), curve=None,
                    roll=0.0)
    blk, A = g3["inputs"]["block"], g3["inputs"]["asset"]
    for case, cs in g3["cases"].items():
        for lam_key, x in cs["by_lam"].items():
            lam = float(lam_key)
            for which, add in (("base", 0.0), ("with_asset", A)):
                b = dict(blk, f_a=blk["f_a"] + add, c20=blk["c20"] + add, c11=blk["c11"] + add)
                term = terminal(**_sample_terminal(t, pbt_last_year=cs["pbt_l"], bv_q=t["bv_q"] + add), fixed=b,
                                lam_f=lam)
                want = x[which]["terminal"]
                for f, got in (("tv_ri", term.tv_ri), ("tv_ddm", term.tv_ddm), ("p_t", term.p_t),
                               ("roe", term.roe_raw), ("roe_faded", term.roe_t), ("business_capital",
                                                                                term.fixed["business_capital"])):
                    assert close(got, want[f], abs_=TOL), (case, lam_key, which, f, got, want[f])
                for f in ("f_k", "d_f", "i_f", "c", "kappa", "binding") if want["block"] is not None else ():
                    got, ref = term.fixed[f], want["block"][f]
                    assert got == ref if f == "binding" else close(got, ref, abs_=TOL), (case, lam_key, which, f)
                val = value_cell(q0=1, elapsed=0.0, disc=disc, bv=tuple(v + add for v in cell["bv"]),
                                 ci=tuple(cell["ci"]), div=tuple(cell["div"]), term=term)
                assert close(val.v_ri, x[which]["value"]["v_ri"], abs_=TOL), (case, lam_key, which)
                assert close(val.v_ddm, val.v_ri, abs_=1e-12 * max(1.0, abs(val.v_ri)))
            assert close(x["with_asset"]["value"]["v_ri"] - x["base"]["value"]["v_ri"], x["asset_effect"], abs_=TOL)
        for side, sv in cs["sides"].items():
            if side == "sum_of_sides_minus_both":
                continue
            b = dict(blk)
            if side == "capital":
                b.update(f_a=0.0, r_f=0.0)
            elif side == "balance":
                b.update(c20=0.0, c11=0.0)
            term = terminal(**_sample_terminal(t, pbt_last_year=cs["pbt_l"]), fixed=b, lam_f=0.0)
            assert close(term.tv_ri, sv["terminal"]["tv_ri"], abs_=TOL), (case, side)
            val = value_cell(q0=1, elapsed=0.0, disc=disc, bv=tuple(cell["bv"]), ci=tuple(cell["ci"]),
                             div=tuple(cell["div"]), term=term)
            assert close(val.v_ri, sv["value"]["v_ri"], abs_=TOL), (case, side)
