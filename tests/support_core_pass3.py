"""Проверки третьего прохода ядра (строки М§18): доля вычета якоря, постоянная в рублях (М§4.11, §4.14.5, §7,
прил. A № 21), и таблица случаев чтения траектории (М§0.4, прил. F.3).

Фикстуры — формы образца `tests/fixtures/core` (ключи доли подставляет тест) и `core_t` (множитель плотности
режима, рост по капиталу); фикстура докапитализации — `tests/support_core_recap.py`; общий числовой пример —
`tests/fixtures/core_pass3/example.json` (приложение F методики). Каждая проверка — тождество или закрытая
формула, выведенная из книги, фактов и рядов клетки независимо от кода ядра: вычет пересчитывается по ряду RWA
клетки, капитал — по её рядам (капитал акционеров, DPreg, фонд, инструменты, неаудированная прибыль), избыток
терминала — по строке конца сетки книги без ключей. Те же функции зовут тесты `tests/test_core_pass3.py` и
мутационный набор `tests/mutations.py`.

«Тихая» книга (`QUIET`) — книга, у которой путь капитала от нормативов не зависит: доля выплаты и выплата
избытка — ноль, замыкания капитала выключены. На ней ряды капитала и RWA книги с долей и книги без ключей
совпадают бит в бит, и разность нормативов — ровно разность вычетов.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from model.book import Book, book_from_dict
from model.book_schema import FIXED_SHARES, KEYS, BookError
from model.capital import (FIXED_SHARE11, FIXED_SHARE20, RECAP_RESIDUAL_SHARE, CapitalConst, deduction_parts,
                           fixed_shares, ratios)
from model.checks import check_gates, check_invariants
from model.grid import GridRun, live_from_book, run_grid
from model.paths import path_value
from model.valuation import terminal
from tests import support_core_recap as R
from tests.support_core import book_with, fixture_book, fixture_dict, fixture_facts, fixture_run
from tests.support_core_recap import RECAP, close

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE: dict[str, Any] = json.loads((ROOT / "tests" / "fixtures" / "core_pass3" / "example.json")
                                     .read_text(encoding="utf-8"))
TOL = 1e-9                                   # допуск примера приложения F (М§17)
TRAJ_TOL = 1e-12                             # допуск таблицы случаев чтения траектории (М§17)
S20, S11 = FIXED_SHARE20, FIXED_SHARE11
ETA = (0.6, 0.35)                            # доли проверок: разные у двух нормативов и не половина
D20, D11 = "capital.n20.deductions_anchor", "capital.n11.deductions_anchor"
G20, G11 = "capital.n20.gap_pp", "capital.n11.gap_pp"
QUIET: dict[str, Any] = {"dividends.policy.payout": {"LT": 0.0}, "dividends.excess.epsilon": 0.0}
FALLING_RWA = {"capital.rwa.density_drift_rate": -0.3}       # RWA первых лет ниже якоря (построенный случай)
N11_TIGHT = {"capital.mgmt_buffer.n1_1": 0.06}               # на конце сетки связывает Н20.1


def shares(eta20: float, eta11: float) -> dict[str, float]:
    return {S20: eta20, S11: eta11}


_GRIDS: dict[str, GridRun] = {}


def grid(extra: Mapping[str, Any] | None = None) -> GridRun:
    """Сетка книги фикстуры формы образца с подменами (ключи доли вводятся подменой; одна сетка на набор)."""
    if not extra:
        return fixture_run()
    key = json.dumps(extra, sort_keys=True, ensure_ascii=False)
    if key not in _GRIDS:
        _GRIDS[key] = run_grid(fixture_book().with_overrides(extra, create=True), fixture_facts())
    return _GRIDS[key]


def t_grid(eta: tuple[float, float] | None) -> GridRun:
    """Сетка полной книги фикстуры формы Т (множитель плотности режима, рост по капиталу, квартальный календарь);
    `eta` — доли вычета якоря, None — без ключей."""
    from tests.support_core_t import book_live, t_dict, t_facts

    key = f"t:{eta}"
    if key not in _GRIDS:
        data = t_dict()
        if eta is not None:
            data["capital"]["n20"]["deductions_fixed_share"] = eta[0]
            data["capital"]["n11"]["deductions_fixed_share"] = eta[1]
        book = book_from_dict(data, facts=t_facts())
        _GRIDS[key] = run_grid(book, t_facts(), book_live(book))
    return _GRIDS[key]


def anchor_deductions(run: GridRun) -> tuple[float, float, float]:
    """(Ded20_0, Ded11_0, RWA_0) — ключи книги и RWA строки якоря."""
    book = run.ctx.book
    return float(book.get(D20)), float(book.get(D11)), float(run.cells[0].quarters["rwa"][0])


def own_deduction(ded0: float, eta: float, rwa: float, rwa0: float) -> float:
    """Вычет квартала по формуле текста: `Ded_j,0 × [(1 − η_j) × RWA_q / RWA_0 + η_j]` (М§4.11)."""
    return ded0 * ((1 - eta) * rwa / rwa0 + eta)


def rows_equal(a: Any, b: Any, names: tuple[str, ...]) -> bool:
    return all(a.quarters[k] == b.quarters[k] for k in names)


# ------------------------------------------------------------------ без ключей и ключи, равные нулю (М§4.11)


def check_zero_shares_are_the_book_without_keys() -> None:
    """Ключи, равные нулю, — ряды и оценка книги без ключей бит в бит (свойство 3 М§4.11): на фикстуре формы
    образца, на фикстуре докапитализации (взносы — те же) и на полной книге формы Т (рост по капиталу). Строка
    вычета с нулевыми долями даёт те же биты, что прежняя строка, на любых входах — и при отрицательном вычете
    якоря; книга без ключей идёт без частей вычета (`parts is None`)."""
    import random

    base = fixture_run()
    assert base.ctx.prep.cap.parts is None and fixed_shares(base.ctx.book) is None
    for zero in (shares(0.0, 0.0), shares(0, 0)):                        # ноль числом и целым
        keyed = grid(zero)
        assert keyed.ctx.prep.cap.parts is not None
        R.cells_equal(base, keyed)
        assert all(a.x_t == b.x_t and a.decisions == b.decisions for a, b in zip(base.cells, keyed.cells))
        assert {n: (L.v0, L.price) for n, L in base.layers.items()} == \
               {n: (L.v0, L.price) for n, L in keyed.layers.items()}
    recap, recap_zero = R.grid_of(), R.grid_of(shares(0.0, 0.0))
    R.cells_equal(recap, recap_zero)
    assert all(a.recaps == b.recaps and a.shares == b.shares for a, b in zip(recap.cells, recap_zero.cells))
    assert sum(1 for c in recap.cells for r in c.recaps if r.rec > 0) >= 20
    R.cells_equal(t_grid(None), t_grid((0.0, 0.0)))
    rnd = random.Random(850)
    for _ in range(2000):
        ded20, ded11 = rnd.uniform(-900.0, 1900.0), rnd.uniform(-900.0, 1900.0)
        kw = dict(rwa0=rnd.uniform(1e3, 9e4), fvoci_recognition=rnd.random(), gap20=rnd.uniform(-0.01, 0.01),
                  gap11=rnd.uniform(-0.01, 0.01), at1=rnd.uniform(0.0, 400.0), audit_cutoffs=(4,), buffer20=0.0,
                  buffer11=0.0)
        row = dict(bv=rnd.uniform(1e3, 2e4), dpreg=rnd.uniform(0.0, 500.0), reserve=rnd.uniform(-600.0, 200.0),
                   unaudited=rnd.uniform(-300.0, 900.0), t2=rnd.uniform(0.0, 700.0), rwa=rnd.uniform(5e2, 3e5),
                   ded_pp20=rnd.uniform(0.0, 0.02), ded_pp11=rnd.uniform(0.0, 0.02))
        plain = ratios(CapitalConst(ded20_0=ded20, ded11_0=ded11, **kw), **row)
        zeroed = ratios(CapitalConst(ded20_0=ded20, ded11_0=ded11, parts=deduction_parts(ded20, ded11, 0.0, 0.0),
                                     **kw), **row)
        assert plain == zeroed, (ded20, ded11, row)


# ------------------------------------------------------------------ формула вычета (М§4.11, свойства 1, 2, 4)


def _check_formula(run: GridRun, eta: tuple[float, float]) -> int:
    """Ряды вычета каждой клетки равны формуле от её ряда RWA, а K20, K11 и нормативы, пересчитанные по рядам
    клетки с этим вычетом, совпадают с её рядами. → число проверенных кварталов с RWA ниже якоря."""
    book, tl, prep = run.ctx.book, run.ctx.timeline, run.ctx.prep
    ded20_0, ded11_0, rwa0 = anchor_deductions(run)
    f = float(book.get("capital.n20.fvoci_recognition"))
    gap20, gap11 = float(book.get(G20)), float(book.get(G11))
    t2 = [path_value(book.get("capital.n20.t2"), tl.period(q)) for q in range(tl.Q + 1)]
    below = 0
    for c in run.cells:
        q_ = c.quarters
        dpp = {name: book.get(f"capital.reg_scenarios.{c.scenario}.deduction_pp.{name}") for name in ("n20_0", "n1_1")}
        assert q_["rwa"][0] == rwa0, c.label
        for q in range(tl.Q + 1):
            rwa = q_["rwa"][q]
            want20, want11 = own_deduction(ded20_0, eta[0], rwa, rwa0), own_deduction(ded11_0, eta[1], rwa, rwa0)
            assert close(q_["ded20"][q], want20, rel=1e-12), (c.label, q, q_["ded20"][q], want20)
            assert close(q_["ded11"][q], want11, rel=1e-12), (c.label, q, q_["ded11"][q], want11)
            bvreg = q_["bv"][q] + q_["dpreg"][q] - (1 - f) * q_["reserve"][q]
            k20 = bvreg - want20 + prep.af.at1 + t2[q]
            assert close(q_["k20"][q], k20, rel=1e-12), (c.label, q)
            a20 = gap20 - path_value(dpp["n20_0"], tl.period(q))
            assert close(q_["n20"][q], k20 / rwa + a20, rel=1e-12, abs_=1e-14), (c.label, q)
            # аддитивное слагаемое норматива — поправка минус вычет сценария: долю оно не читает
            assert close(q_["n20"][q] - q_["k20"][q] / rwa, a20, abs_=1e-13), (c.label, q)
            below += rwa < rwa0
            e = q_["e_unaudited"][q]
            if e is None or q_["k11"][q] is None:
                continue                            # якорь без раскрытой прибыли периода: Н20.1 не считается
            k11 = bvreg - max(e, 0.0) - want11
            a11 = gap11 - path_value(dpp["n1_1"], tl.period(q))
            assert close(q_["k11"][q], k11, rel=1e-12), (c.label, q)
            assert close(q_["n11"][q], k11 / rwa + a11, rel=1e-12, abs_=1e-14), (c.label, q)
            assert close(q_["n11"][q] - q_["k11"][q] / rwa, a11, abs_=1e-13), (c.label, q)
            assert close(q_["n11_star"][q], (k11 + max(e, 0.0)) / rwa + a11, rel=1e-12, abs_=1e-14), (c.label, q)
    return below


def check_deduction_is_the_formula_of_the_rwa_row() -> None:
    """Свойство 1 М§4.11: в каждом квартале каждой клетки `Ded_j,q = Ded_j,0 × [(1 − η_j) × RWA_q / RWA_0 + η_j]`
    по ряду RWA клетки, а K20 и K11, пересчитанные тестом по рядам клетки с этим вычетом, совпадают с её рядами;
    аддитивное слагаемое норматива `N_j − K_j / RWA` — поправка минус вычет сценария при любых долях. Фикстуры:
    форма образца, докапитализация (деньги взноса несут вес риска) и полная книга формы Т — множитель плотности
    режима уводит RWA клеток кризиса ниже якоря, и растущая часть идёт за ним. Книга без ключей — та же формула
    при нулевых долях (прежняя строка)."""
    for run, eta in ((grid(shares(*ETA)), ETA), (R.grid_of(shares(*ETA)), ETA), (fixture_run(), (0.0, 0.0)),
                     (grid(shares(0.25, 0.9)), (0.25, 0.9))):
        _check_formula(run, eta)
        assert run.ctx.prep.cap.parts is not None or eta == (0.0, 0.0)
    assert _check_formula(t_grid(ETA), ETA) >= 9          # кварталы кризиса с RWA ниже якоря (множитель режима)
    assert _check_formula(t_grid(None), (0.0, 0.0)) >= 9
    # проверка не пуста: вычет с долей далеко и от суммы якоря, и от вычета, растущего целиком; вычет сценария не ноль
    run = grid(shares(*ETA))
    ded20_0, _, rwa0 = anchor_deductions(run)
    c, tl = run.cell("H", "norm", "upper"), run.ctx.timeline
    assert c.quarters["rwa"][tl.Q] > 1.5 * rwa0
    assert ded20_0 + 100.0 < c.quarters["ded20"][tl.Q] < ded20_0 * c.quarters["rwa"][tl.Q] / rwa0 - 100.0
    assert path_value(run.ctx.book.get("capital.reg_scenarios.upper.deduction_pp.n20_0"), tl.period(tl.Q)) > 0.001


def check_anchor_row_at_any_share() -> None:
    """Свойство 2 М§4.11: в квартале якоря вычет равен ключу при любой доле, а оба норматива — нормативы строки
    якоря книги без ключей и воспроизводят факты. Якорное условие от долей не зависит."""
    facts = fixture_facts()
    base = fixture_run()
    ded20_0, ded11_0, _ = anchor_deductions(base)
    for eta in ((0.0, 0.0), ETA, (0.25, 0.9), (1.0, 1.0)):
        run = grid(shares(*eta))
        for c, plain in zip(run.cells, base.cells):
            q_, p_ = c.quarters, plain.quarters
            assert close(q_["ded20"][0], ded20_0, rel=1e-13) and close(q_["ded11"][0], ded11_0, rel=1e-13), c.label
            for name in ("k20", "k11", "n20", "n11", "n11_star"):
                assert close(q_[name][0], p_[name][0], rel=1e-13, abs_=1e-15), (c.label, name, eta)
            assert abs(q_["n20"][0] - facts.need("capital", "n20_0.value")) < 5e-4
            assert abs(q_["n11"][0] - facts.need("capital", "n1_1_bank.value")) < 5e-4
    for eta in (None, ETA, (1.0, 1.0)):                    # форма Т: вычеты якоря — слово anchor
        run = t_grid(eta)
        t20, t11, _ = anchor_deductions(run)
        for c, plain in zip(run.cells, t_grid(None).cells):
            assert close(c.quarters["ded20"][0], t20, rel=1e-13) and close(c.quarters["ded11"][0], t11, rel=1e-13)
            assert close(c.quarters["n20"][0], plain.quarters["n20"][0], abs_=1e-15), c.label
            assert close(c.quarters["n11"][0], plain.quarters["n11"][0], abs_=1e-15), c.label


def check_share_one_keeps_the_deduction_constant() -> None:
    """Свойство 4 М§4.11: при долях, равных единице, вычет каждого норматива — сумма якоря во всех кварталах, и
    в клетке режима с множителем плотности (RWA ниже якоря), и в клетке со взносом (RWA выше на вес риска денег)."""
    run = t_grid((1.0, 1.0))
    ded20_0, ded11_0, rwa0 = anchor_deductions(run)
    dipped = 0
    for c in run.cells:
        assert all(v == ded20_0 for v in c.quarters["ded20"]) and all(v == ded11_0 for v in c.quarters["ded11"])
        dipped += min(c.quarters["rwa"]) < rwa0 - 1.0
    assert dipped >= 9, dipped
    assert run.ctx.book.get("regimes.crisis.rwa_density_mult") is not None
    for run in (grid(shares(1.0, 1.0)), R.grid_of(shares(1.0, 1.0))):
        ded20_0, ded11_0, _ = anchor_deductions(run)
        assert all(v == ded20_0 for c in run.cells for v in c.quarters["ded20"])
        assert all(v == ded11_0 for c in run.cells for v in c.quarters["ded11"])


# ------------------------------------------------------------------ на одном пути капитала (свойства 5, 6, 8)


def _terminal_terms(c: Any, q: int) -> tuple[float, float]:
    """Слагаемые минимума избытка терминала по строке конца сетки (М§7): `(N_jᵀ − req_j) × RWA`, нормативы — без
    дивидендов, ещё не вычтенных из регуляторного капитала; Н20.1 — с прибылью периода."""
    q_ = c.quarters
    rwa, pending = q_["rwa"][q], q_["dpreg"][q] / q_["rwa"][q]
    return ((q_["n20"][q] - pending - q_["req20"][q]) * rwa, (q_["n11_star"][q] - pending - q_["req11"][q]) * rwa)


def check_capital_is_higher_by_the_fixed_part() -> None:
    """Свойства 5 и 6 М§4.11 на «тихой» книге (выплата и выплата избытка — ноль, замыкания выключены): путь
    капитала и RWA от долей не зависит бит в бит; K_j выше, чем без ключей, ровно на
    `η_j × Ded_j,0 × (RWA_q / RWA_0 − 1)`, норматив — на `η_j × Ded_j,0 × (1 / RWA_0 − 1 / RWA_q)`; избыток
    терминала — `multiple × min_j [X⁰_j + η_j × Ded_j,0 × (RWA_Q / RWA_0 − 1)]` по слагаемым книги без ключей —
    и там, где связывает Н20.0, и там, где Н20.1; доля одного норматива не меняет ряды вычета, капитала и
    норматива другого."""
    bound = {"n20": 0, "n11": 0}
    for tight in ({}, N11_TIGHT):
        plain = grid({**QUIET, **tight})
        ded20_0, ded11_0, rwa0 = anchor_deductions(plain)
        tl = plain.ctx.timeline
        multiple = float(plain.ctx.book.get("valuation.terminal.excess_capital_multiple"))
        assert all(not any(c.quarters["div"][1:]) for c in plain.cells)          # выплаты нет: путь капитала задан
        for eta in (ETA, (1.0, 0.0), (0.0, 1.0), (0.1, 0.35), (0.6, 0.9)):
            keyed = grid({**QUIET, **tight, **shares(*eta)})
            add = (eta[0] * ded20_0, eta[1] * ded11_0)
            for c, base in zip(keyed.cells, plain.cells):
                assert rows_equal(c, base, ("bv", "rwa", "ci", "ni_sh", "div", "dpreg", "reserve", "e_unaudited",
                                            "req20", "req11")), c.label
                q_, b_ = c.quarters, base.quarters
                for q in range(1, tl.Q + 1):
                    grow, inv = q_["rwa"][q] / rwa0 - 1, 1 / rwa0 - 1 / q_["rwa"][q]
                    assert close(q_["k20"][q] - b_["k20"][q], add[0] * grow, rel=1e-9, abs_=1e-8), (c.label, q)
                    assert close(q_["k11"][q] - b_["k11"][q], add[1] * grow, rel=1e-9, abs_=1e-8), (c.label, q)
                    assert close(q_["n20"][q] - b_["n20"][q], add[0] * inv, abs_=1e-13), (c.label, q)
                    assert close(q_["n11"][q] - b_["n11"][q], add[1] * inv, abs_=1e-13), (c.label, q)
                    assert close(q_["n11_star"][q] - b_["n11_star"][q], add[1] * inv, abs_=1e-13), (c.label, q)
                x20, x11 = _terminal_terms(base, tl.Q)
                assert close(base.x_t, multiple * min(x20, x11), rel=1e-9, abs_=1e-6), base.label
                grow = b_["rwa"][tl.Q] / rwa0 - 1
                want = multiple * min(x20 + add[0] * grow, x11 + add[1] * grow)
                assert close(c.x_t, want, rel=1e-9, abs_=1e-6), (c.label, eta, c.x_t, want)
                assert grow > 0.5 and (c.x_t > base.x_t + 1.0 if min(eta) > 0 else c.x_t >= base.x_t - 1e-6)
                bound["n20" if x20 + add[0] * grow <= x11 + add[1] * grow else "n11"] += 1
        # доля одного норматива не меняет ряды другого (свойство 6): та же η_20 при другой η_11 и наоборот
        a, b, c_ = (grid({**QUIET, **tight, **shares(*eta)}) for eta in (ETA, (0.6, 0.9), (0.1, 0.35)))
        for x, y, z in zip(a.cells, b.cells, c_.cells):
            assert rows_equal(x, y, ("ded20", "k20", "n20")) and not rows_equal(x, y, ("ded11",)), x.label
            assert rows_equal(x, z, ("ded11", "k11", "n11", "n11_star")) and not rows_equal(x, z, ("ded20",)), x.label
    assert min(bound.values()) >= 36, bound


def check_share_is_not_a_relief() -> None:
    """Свойство 8 М§4.11 и знак: на одном пути капитала и RWA норматив книги с долей не ниже норматива книги без
    ключей, пока RWA не ниже якоря, и растёт с долей; в построенном квартале с RWA ниже якоря (отрицательный
    дрейф плотности) он НИЖЕ — постоянный вычет не уменьшается вместе с RWA. Оценка клетки с нехваткой капитала
    с ростом доли при растущих RWA не падает: на «тихой» книге — через избыток терминала, на фикстуре
    докапитализации — через меньшие взносы."""
    ladder = [grid(QUIET)] + [grid({**QUIET, **shares(e, e)}) for e in (0.3, 0.6, 1.0)]
    tl = ladder[0].ctx.timeline
    _, _, rwa0 = anchor_deductions(ladder[0])
    for cells in zip(*(run.cells for run in ladder)):
        for q in range(1, tl.Q + 1):
            assert cells[0].quarters["rwa"][q] > rwa0, (cells[0].label, q)          # RWA фикстуры растут
            for name in ("n20", "n11", "n11_star"):
                row = [c.quarters[name][q] for c in cells]
                assert all(b > a for a, b in zip(row, row[1:])), (cells[0].label, q, name, row)
        assert all(b.x_t > a.x_t for a, b in zip(cells, cells[1:])), cells[0].label
        assert all(b.v_ri >= a.v_ri for a, b in zip(cells, cells[1:])), cells[0].label
    # построенный случай: RWA падают ниже якоря — норматив с долей ниже, ровно на η × Ded_0 × (1/RWA_0 − 1/RWA_q)
    plain, keyed = grid({**QUIET, **FALLING_RWA}), grid({**QUIET, **FALLING_RWA, **shares(*ETA)})
    ded20_0, ded11_0, rwa0 = anchor_deductions(plain)
    lower = 0
    for c, base in zip(keyed.cells, plain.cells):
        assert rows_equal(c, base, ("bv", "rwa")), c.label
        for q in range(1, tl.Q + 1):
            rwa = c.quarters["rwa"][q]
            if not rwa < rwa0:
                continue
            for name, add in (("n20", ETA[0] * ded20_0), ("n11", ETA[1] * ded11_0)):
                diff = c.quarters[name][q] - base.quarters[name][q]
                assert diff < 0 and close(diff, add * (1 / rwa0 - 1 / rwa), abs_=1e-13), (c.label, q, name)
            assert c.quarters["ded20"][q] > base.quarters["ded20"][q]              # вычет не уменьшился с RWA
            lower += 1
    assert lower >= 36 * 8, lower
    # нехватка капитала: с ростом доли взносы и цена размывания не растут, оценка клетки не падает
    steps = [R.grid_of(shares(e, e)) for e in (0.0, 0.5, 1.0)]
    short = 0
    for cells in zip(*(run.cells for run in steps)):
        rec = [sum(r.rec for r in c.recaps) for c in cells]
        if not rec[0] > 0:
            continue
        short += 1
        assert rec[0] >= rec[1] >= rec[2] >= 0.0 and rec[0] > rec[2], (cells[0].label, rec)
        assert cells[0].v_ri <= cells[1].v_ri <= cells[2].v_ri and cells[0].v_ri < cells[2].v_ri, cells[0].label
        assert cells[0].pvd >= cells[1].pvd >= cells[2].pvd
    assert short >= 20 and steps[0].point < steps[1].point < steps[2].point, short


def check_anchor_deduction_and_gap_are_not_interchangeable() -> None:
    """Свойство 7 М§4.11. Сдвиг вычета якоря на Δ вместе с поправкой на Δ / RWA_0 и долей
    `η_j × Ded_j,0 / (Ded_j,0 + Δ)` (сумма в рублях прежняя) оставляет нормативы всех кварталов и оценку
    прежними; тот же сдвиг при прежней доле сдвигает норматив квартала на `η_j × Δ × (1 / RWA_0 − 1 / RWA_q)`.
    У книги без ключей сдвиг вычета вместе с поправкой путь норматива не меняет — раздел слагаемого якоря
    между вычетом и поправкой там безразличен."""
    delta = {"n20": 150.0, "n11": -80.0}
    for body in (QUIET, {}):
        keyed = grid({**body, **shares(*ETA)})
        ded20_0, ded11_0, rwa0 = anchor_deductions(keyed)
        gap20, gap11 = float(keyed.ctx.book.get(G20)), float(keyed.ctx.book.get(G11))
        moved = {D20: ded20_0 + delta["n20"], D11: ded11_0 + delta["n11"],
                 G20: gap20 + delta["n20"] / rwa0, G11: gap11 + delta["n11"] / rwa0}
        by_sum = grid({**body, **moved, S20: ETA[0] * ded20_0 / (ded20_0 + delta["n20"]),
                       S11: ETA[1] * ded11_0 / (ded11_0 + delta["n11"])})
        by_share = grid({**body, **moved, **shares(*ETA)})
        tl = keyed.ctx.timeline
        for c, same, other in zip(keyed.cells, by_sum.cells, by_share.cells):
            for q in range(tl.Q + 1):
                for name in ("n20", "n11", "n11_star"):
                    assert close(same.quarters[name][q], c.quarters[name][q], abs_=1e-12), (c.label, q, name)
            assert close(same.x_t, c.x_t, rel=1e-9, abs_=1e-6) and close(same.v_ri, c.v_ri, rel=1e-9, abs_=1e-6)
            assert not close(same.quarters["ded20"][tl.Q], c.quarters["ded20"][tl.Q], abs_=1.0)   # вычеты — другие
            if body:                               # на одном пути капитала: сдвиг норматива при прежней доле
                for q in range(1, tl.Q + 1):
                    inv = 1 / rwa0 - 1 / c.quarters["rwa"][q]
                    for name, eta, d in (("n20", ETA[0], delta["n20"]), ("n11", ETA[1], delta["n11"])):
                        diff = other.quarters[name][q] - c.quarters[name][q]
                        assert close(diff, eta * d * inv, abs_=1e-13), (c.label, q, name, diff)
                assert other.quarters["n20"][tl.Q] > c.quarters["n20"][tl.Q] + 1e-4      # Δ > 0: норматив выше
                assert other.quarters["n11"][tl.Q] < c.quarters["n11"][tl.Q] - 1e-5      # Δ < 0: ниже
        if not body:
            assert abs(by_share.point - keyed.point) > 0.05 and close(by_sum.point, keyed.point, abs_=1e-6)
    # без ключей вычет якоря и поправка взаимозаменяемы
    plain = grid(QUIET)
    ded20_0, ded11_0, rwa0 = anchor_deductions(plain)
    swapped = grid({**QUIET, D20: ded20_0 + 150.0, G20: float(plain.ctx.book.get(G20)) + 150.0 / rwa0})
    for c, same in zip(plain.cells, swapped.cells):
        assert all(close(a, b, abs_=1e-12) for a, b in zip(c.quarters["n20"], same.quarters["n20"])), c.label


# ------------------------------------------------------------------ мост норматива выпуска (М§4.11, П§2)


def _release(book: Book) -> tuple[Any, dict]:
    """Быстрый выпуск на книге фикстуры формы образца: гейты объяснены, слоя индикаторов нет."""
    from model import payload as P
    from tests.support_core2 import TODAY, control_fixture, explained

    facts = fixture_facts()
    run = run_grid(book, facts, live_from_book(book, facts))
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts,
                         explanations=explained(check_gates(run, today=TODAY)), notes=[], draws=4,
                         control_model=control_fixture(book))
    return rel, P.build_payload(rel)


def check_bridge_row_of_deductions() -> None:
    """Строка вычетов моста норматива выпуска читает ряд Ded20 клеток (М§4.11): сумма —
    `−(E[Ded20_e] − Ded20_0) = −Dgrow_20 × (E[RWA_e] / RWA_0 − 1)`, доля — `сумма / E[RWA_e] + (A_e − A_0)`;
    при η_20 = 1 сумма — ноль, в доле остаётся одно изменение аддитивного слагаемого; тождество
    `start + Σ долей = end` держится. Ожидания — под вероятностями смеси заголовка, своим счётом теста."""
    from model import payload as P
    from tests.support_core2 import contract

    moved = {}
    for eta in (None, ETA, (1.0, 0.0)):
        book = fixture_book() if eta is None else fixture_book().with_overrides(shares(*eta), create=True)
        rel, data = _release(book)
        assert not contract(data), contract(data)[:5]
        run, tl = rel.run, rel.run.ctx.timeline
        bridge = data["capital"]["bridge"]
        qe = tl.index(bridge["to"])
        an, neu = run.layers["analytical"].prob, run.layers["macro_neutral"].prob
        mix = {k: run.lam * an[k] + (1 - run.lam) * neu[k] for k in an}
        assert close(sum(mix.values()), 1.0)

        def mean(name: str, q: int) -> float:
            return sum(mix[c.key] * c.quarters[name][q] for c in run.cells)

        def additive(q: int) -> float:
            return sum(mix[c.key] * (c.quarters["n20"][q] - c.quarters["k20"][q] / c.quarters["rwa"][q])
                       for c in run.cells)

        ded20_0, _, rwa0 = anchor_deductions(run)
        share = 0.0 if eta is None else eta[0]
        amount = -(mean("ded20", qe) - ded20_0)
        assert close(amount, -(1 - share) * ded20_0 * (mean("rwa", qe) / rwa0 - 1), rel=1e-9, abs_=1e-9)
        rows = {r["key"]: r for r in bridge["rows"]}
        half = P.PRECISION["money"] / 2 + 1e-9
        assert abs(rows["deductions"]["amount"] - amount) <= half, (eta, rows["deductions"], amount)
        pp = amount / mean("rwa", qe) + (additive(qe) - additive(0))
        assert abs(rows["deductions"]["pp"] - pp) <= P.PRECISION["share"] / 2 + 1e-12, (eta, rows["deductions"], pp)
        growth = mean("k20", 0) * (1 / mean("rwa", qe) - 1 / rwa0)
        assert abs(rows["rwa_growth"]["pp"] - growth) <= P.PRECISION["share"] / 2 + 1e-12
        assert abs(bridge["start"] + sum(r["pp"] for r in bridge["rows"]) - bridge["end"]) < 1e-9
        assert abs(bridge["end"] - (mean("k20", qe) / mean("rwa", qe) + additive(qe))) <= P.PRECISION["share"]
        assert mean("rwa", qe) > rwa0 * 1.02                 # за период моста RWA выросли
        moved[eta] = rows["deductions"]["amount"]
    assert moved[(1.0, 0.0)] == 0.0 and moved[None] < moved[ETA] < -1.0, moved
    assert close(moved[ETA], (1 - ETA[0]) * moved[None], abs_=0.02)


# ------------------------------------------------------------------ докапитализация (М§4.14.2, §4.14.5, §14.1)


def check_recapitalization_with_shares() -> None:
    """Свойство 3 М§4.14.5 у книги с долями: в квартале взноса капитал окончательного расчёта выше пробного на
    `Rec − Dgrow_j × (RWA′ − RWA) / RWA_0` — за деньгами взноса растёт только растущая часть вычета; при долях,
    равных единице, — ровно на взнос при любых плотностях; остаток недостатка — закрытая формула с растущей
    частью, `S_j − Rec + (ρ_j + Dgrow_j / RWA_0) × ΔRWA`, в допуске инварианта `recap_covers_gap` (М§14.1)."""
    window = {f"{RECAP}.lookahead_quarters": 0, f"{RECAP}.min_amount": 0.0,
              "dividends.calendar.reg_deduction_quarter": 2}
    for eta in (ETA, (1.0, 1.0)):
        run, rows = R._first_decisions({**R.DEEP_LOSS, **window, **shares(*eta)})
        p = run.ctx.prep
        ded20_0, ded11_0, rwa0 = anchor_deductions(run)
        grow = ((1 - eta[0]) * ded20_0, (1 - eta[1]) * ded11_0)
        made = 0
        for c, plain, dec in rows:
            if not dec.rec > 0:
                continue
            q, a, b = dec.q, c.quarters, plain.quarters
            d_rwa = a["rwa"][q] - b["rwa"][q]
            assert d_rwa > 1.0 and close(a["bv"][q] - b["bv"][q], dec.rec, rel=1e-12), c.label
            assert close(a["ded20"][q] - b["ded20"][q], grow[0] * d_rwa / rwa0, rel=1e-9, abs_=1e-9), c.label
            assert close(a["ded11"][q] - b["ded11"][q], grow[1] * d_rwa / rwa0, rel=1e-9, abs_=1e-9), c.label
            assert close(a["k20"][q] - b["k20"][q], dec.rec - grow[0] * d_rwa / rwa0, rel=1e-11), c.label
            assert close(a["k11"][q] - b["k11"][q], dec.rec - grow[1] * d_rwa / rwa0, rel=1e-11), c.label
            if eta == (1.0, 1.0):                   # постоянная часть за деньгами взноса не растёт
                assert a["ded20"][q] == b["ded20"][q] == ded20_0 and a["ded11"][q] == b["ded11"][q] == ded11_0
                assert close(a["k20"][q] - b["k20"][q], dec.rec, rel=1e-12), c.label
                assert close(a["k11"][q] - b["k11"][q], dec.rec, rel=1e-12), c.label
            sc = p.scenarios[c.scenario]
            rho = {"n20": a["req20"][q] - p.cap.gap20 + sc.ded_pp20[q] + grow[0] / rwa0,
                   "n11": a["req11"][q] - p.cap.gap11 + sc.ded_pp11[q] + grow[1] / rwa0}
            point = next(pt for pt in dec.points if pt.q == q)
            left = max(point.s20 - dec.rec + rho["n20"] * d_rwa, point.s11 - dec.rec + rho["n11"] * d_rwa)
            assert close(dec.residual, left, rel=1e-9, abs_=1e-6), (c.label, dec.residual, left)
            assert 0 < dec.residual <= RECAP_RESIDUAL_SHARE * dec.rec
            made += 1
        assert made >= 6, made
        for g in (run, R.grid_of(shares(*eta))):
            finding = next(f for f in check_invariants(g) if f.name == "recap_covers_gap")
            assert not finding.fired, finding.message
            assert not [f.name for f in check_invariants(g) if f.fired]


# ------------------------------------------------------------------ схема (прил. A № 21)


def check_schema_of_the_shares() -> None:
    """Ограничение № 21 прил. A: доля — число от 0 до 1 включительно, ноль и единица допустимы; ключи задаются
    вместе — один без другого отказ с названным путём; слова `anchor` и `null` у ключа нет; конец оси на пути
    доли — в тех же границах. Ключи — в закрытой схеме и необязательны."""
    facts = fixture_facts()
    assert set(FIXED_SHARES.values()) == {S20, S11} and {S20, S11} <= set(KEYS)
    book_from_dict(fixture_dict(), facts=facts)                              # без ключей — принята
    for eta in ((0.0, 0.0), (1.0, 1.0), (0, 1), ETA):
        book = book_from_dict(book_with(shares(*eta)), facts=facts)
        assert fixed_shares(book) == (float(eta[0]), float(eta[1]))
    R._refused(book_with({S20: 0.5}), S11, "нет ключа", "задаются вместе")
    R._refused(book_with({S11: 0.0}), S20, "нет ключа", "задаются вместе")
    for bad in (-0.01, 1.01, 60.0):
        R._refused(book_with({S20: bad, S11: 0.5}), f"{S20} = {bad}", "от 0 до 1")
        R._refused(book_with({S20: 0.5, S11: bad}), f"{S11} = {bad}", "от 0 до 1")
    for bad in ("anchor", None, True, {"LT": 0.5}):
        R._refused(book_with({S20: bad, S11: 0.5}), S20)
    # оси: связка обеих долей (М§10, правило 6), ось значения и ось-сдвиг — конец оси в [0; 1]
    axes = fixture_dict()["valuation"]["uncertainty"]["axes"]
    n = len(axes)
    where = f"valuation.uncertainty.axes[{n}]"
    bundle = {"name": "доля вычета якоря, постоянная в рублях", "kind": "bundle", "paths": [S20, S11],
              "low": {S20: 0.4, S11: 0.2}, "high": {S20: 0.8, S11: 0.5}, "dist": "triangular"}
    keyed = {**shares(*ETA)}
    book_from_dict(book_with({**keyed, "valuation.uncertainty.axes": axes + [bundle]}), facts=facts)
    R._refused(book_with({**keyed, "valuation.uncertainty.axes": axes + [{**bundle, "high": {S20: 1.2, S11: 0.5}}]}),
               f"{where}.high.{S20} = 1.2", "конец оси")
    R._refused(book_with({**keyed, "valuation.uncertainty.axes": axes + [{**bundle, "low": {S20: 0.4, S11: -0.1}}]}),
               f"{where}.low.{S11} = -0.1", "конец оси")
    value = {"name": "доля вычета якоря Н20.0", "kind": "value", "paths": [S20], "low": 0.4, "high": 0.8,
             "dist": "triangular"}
    book_from_dict(book_with({**keyed, "valuation.uncertainty.axes": axes + [value]}), facts=facts)
    R._refused(book_with({**keyed, "valuation.uncertainty.axes": axes + [{**value, "high": 1.5}]}),
               f"{where}.high = 1.5")
    shift = {**value, "kind": "shift", "low": -ETA[0], "high": 1.0 - ETA[0]}
    book_from_dict(book_with({**keyed, "valuation.uncertainty.axes": axes + [shift]}), facts=facts)
    R._refused(book_with({**keyed, "valuation.uncertainty.axes": axes + [{**shift, "high": 0.5}]}),
               f"{where}.high", "со сдвигом")
    # ось на пути доли без ключа в книге — путь не найден
    R._refused(book_with({"valuation.uncertainty.axes": axes + [value]}), "не найден")


def check_axis_of_the_shares_moves_the_deduction() -> None:
    """Ключи — входы прохода клеток: подмена долей связкой оси меняет ряд вычета прогона по формуле от подменённых
    долей, а отпечаток входов прохода клеток различает книги с разными долями (хранилище проходов не вернёт
    чужой проход)."""
    from model.grid import make_context, path_inputs, path_key

    facts = fixture_facts()
    book = fixture_book().with_overrides(shares(*ETA), create=True)
    keys = {eta: path_key(path_inputs(make_context(fixture_book().with_overrides(shares(*eta), create=True), facts)))
            for eta in (ETA, (ETA[0], 0.9), (0.1, ETA[1]), (0.0, 0.0))}
    keys[None] = path_key(path_inputs(make_context(fixture_book(), facts)))
    assert len(set(keys.values())) == len(keys)
    low = run_grid(book.with_overrides({S20: 0.4, S11: 0.2}), facts)
    high = run_grid(book.with_overrides({S20: 0.8, S11: 0.5}), facts)
    _check_formula(low, (0.4, 0.2))
    _check_formula(high, (0.8, 0.5))
    assert low.point < grid(shares(*ETA)).point < high.point


# ------------------------------------------------------------------ пример приложения F (М§17, §18)


def _example_const(eta: tuple[float, float] | None) -> CapitalConst:
    inp = EXAMPLE["deductions"]["inputs"]
    parts = None if eta is None else deduction_parts(inp["ded20_0"], inp["ded11_0"], *eta)
    return CapitalConst(ded20_0=inp["ded20_0"], ded11_0=inp["ded11_0"], rwa0=inp["rwa0"],
                        fvoci_recognition=inp["fvoci_recognition"], gap20=inp["gap20"], gap11=inp["gap11"],
                        at1=inp["at1"], audit_cutoffs=(4,), buffer20=0.0, buffer11=0.0, parts=parts)


def _example_row(eta: tuple[float, float] | None, name: str) -> dict[str, float]:
    row = EXAMPLE["deductions"]["inputs"][name]
    r = ratios(_example_const(eta), bv=row["bv"], dpreg=row["dpreg"], reserve=row["reserve"], unaudited=row["e"],
               t2=row["t2"], rwa=row["rwa"], ded_pp20=row["dpp20"], ded_pp11=row["dpp11"])
    return {"rwa": r.rwa, "ded20": r.ded20, "ded11": r.ded11, "k20": r.k20, "k11": r.k11, "n20": r.n20,
            "n11": r.n11, "n11_star": r.n11_star}


def _example_bridge(eta: tuple[float, float] | None) -> dict:
    """Мост Н20.0 примера — функцией выпуска ядра на клетке из двух строк (якорь и квартал)."""
    from model import payload as P

    inp = EXAMPLE["deductions"]["inputs"]
    a, q = _example_row(eta, "anchor"), _example_row(eta, "quarter")
    rest = EXAMPLE["deductions"]["bridge"]["with_share"]["rest_amount"]
    series = {"k20": (a["k20"], q["k20"]), "rwa": (a["rwa"], q["rwa"]), "n20": (a["n20"], q["n20"]),
              "ded20": (a["ded20"], q["ded20"]), "dpreg": (inp["anchor"]["dpreg"], inp["quarter"]["dpreg"]),
              "ni_sh": (None, rest - inp["quarter"]["dpreg"]), "coupon": (None, 0.0), "tau_stat": (None, 0.0),
              "tau_cpn": (None, 0.0),             # ставка купона в строке прибыли моста (девятый проход, М§4.8)
              "oci": (None, 0.0), "om": (None, 0.0), "div": (None, 0.0)}
    cell = SimpleNamespace(key=("W", "r", "s"), quarters=series)

    class Ctx(P._Ctx):                              # контекст выпуска из одной клетки: формулы моста — ядра
        def __init__(self) -> None:
            self.run = SimpleNamespace(cells=[cell])
            self.p_mix = {cell.key: 1.0}
            self.tl = SimpleNamespace(Q=1, anchor="2026Q2", index=lambda period: 1, period=lambda i: "2026Q4")
            self.v = SimpleNamespace(year=2026)
            self.prep = SimpleNamespace(recap=None)
            self.book = SimpleNamespace(label=lambda key, **fields: key)

    return P._capital_bridge(Ctx())


def check_example_f() -> None:
    """Пример приложения F (F.1–F.2) до 1e-9: части вычета якоря; вычеты, капитал и нормативы строки якоря и
    строки квартала с долей, без ключей и при доле 1; слагаемые X_T; строка вычетов моста. Доля 0 — биты строки
    без ключей. Перенос якоря примера исполняет инструмент перезаякоривания, не ядро."""
    x = EXAMPLE["deductions"]
    inp = x["inputs"]
    eta = (inp["eta20"], inp["eta11"])
    parts = deduction_parts(inp["ded20_0"], inp["ded11_0"], *eta)
    for name, want in x["parts"].items():
        got = {"dfix20": parts.fix20, "dgrow20": parts.grow20, "dfix11": parts.fix11, "dgrow11": parts.grow11}[name]
        assert abs(got - want) < TOL, (name, got, want)
    f = inp["fvoci_recognition"]
    for label, shares_ in (("with_share", eta), ("without_keys", None), ("share_one", (1.0, 1.0))):
        for name in ("anchor", "quarter"):
            got, want, row = _example_row(shares_, name), x[label][name], inp[name]
            for k, v in got.items():
                assert abs(v - want[k]) < TOL, (label, name, k, v, want[k])
            assert abs(row["bv"] + row["dpreg"] - (1 - f) * row["reserve"] - want["bvreg"]) < TOL
    assert all(_example_row((0.0, 0.0), n) == _example_row(None, n) for n in ("anchor", "quarter"))
    # строка якоря от доли не зависит
    assert all(abs(_example_row(eta, "anchor")[k] - v) < TOL for k, v in _example_row(None, "anchor").items())
    # терминал: слагаемые минимума и X_T
    row = inp["quarter"]
    for label, shares_ in (("with_share", eta), ("without_keys", None)):
        got, want = _example_row(shares_, "quarter"), x["terminal"][label]
        n20_t, n11_t = got["n20"] - row["dpreg"] / row["rwa"], got["n11_star"] - row["dpreg"] / row["rwa"]
        assert abs(n20_t - want["n20_t"]) < TOL and abs(n11_t - want["n11_t"]) < TOL
        assert abs((n20_t - inp["req20"]) * row["rwa"] - want["x20"]) < TOL
        assert abs((n11_t - inp["req11"]) * row["rwa"] - want["x11"]) < TOL
        term = terminal(n20=n20_t, req20=inp["req20"], n11_star=n11_t, req11=inp["req11"], rwa=row["rwa"],
                        bv_q=row["bv"], pbt_last_year=40.0, y_balancing=0.1, c_wholesale=0.12, headroom=1e9,
                        tau_eff=0.2, nci_share=0.0, coupon_annual=0.0, tau_stat=0.2, lt_inflation=0.04,
                        real_growth=0.01, fade=1.0, multiple=inp["excess_capital_multiple"], k_t=0.15)
        assert abs(term.x_t - want["x_t"]) < TOL, (label, term.x_t)
    grow = row["rwa"] / inp["rwa0"] - 1
    plain, keyed = x["terminal"]["without_keys"], x["terminal"]["with_share"]
    assert abs(keyed["x20"] - plain["x20"] - eta[0] * inp["ded20_0"] * grow) < TOL
    assert abs(keyed["x11"] - plain["x11"] - eta[1] * inp["ded11_0"] * grow) < TOL
    # мост: строка вычетов, рост RWA, начало и конец; прочие строки — одной суммой
    for label, shares_ in (("with_share", eta), ("without_keys", None), ("share_one", (1.0, 1.0))):
        got, want = _example_bridge(shares_), x["bridge"][label]
        rows = {r["key"]: r for r in got["rows"]}
        assert abs(got["start"] - want["start"]) < TOL and abs(got["end"] - want["end"]) < TOL, (label, got)
        assert abs(rows["deductions"]["amount"] - want["deductions_amount"]) < TOL, (label, rows["deductions"])
        assert abs(rows["deductions"]["pp"] - want["deductions_pp"]) < TOL, (label, rows["deductions"])
        assert abs(rows["rwa_growth"]["pp"] - want["rwa_growth_pp"]) < TOL, (label, rows["rwa_growth"])
        rest = [r for k, r in rows.items() if k not in ("deductions", "rwa_growth")]
        assert abs(sum(r["amount"] for r in rest) - want["rest_amount"]) < TOL
        assert abs(sum(r["pp"] for r in rest) - want["rest_pp"]) < TOL
        assert abs(got["start"] + sum(r["pp"] for r in got["rows"]) - got["end"]) < TOL


# ------------------------------------------------------------------ чтение траекторий (М§0.4, прил. F.3)


def check_trajectory_cases() -> None:
    """Читатель траекторий ядра даёт значения и отказы таблицы случаев приложения F.3 — точно: значения до
    1e-12, отказы — `BookError`. Та же таблица — у читателя контрольной модели (М§17)."""
    cases = EXAMPLE["trajectory_cases"]
    read = 0
    for case in cases:
        for period, want in case["values"].items():
            try:
                got: Any = path_value(case["trajectory"], period)
            except BookError:
                got = "BookError"
            if isinstance(want, str) or isinstance(got, str):
                assert got == want, (case["name"], period, got, want)
            else:
                assert abs(got - want) <= TRAJ_TOL, (case["name"], period, got, want)
            read += 1
    assert len(cases) == 19 and read == 84, (len(cases), read)
    assert len({case["name"] for case in cases}) == len(cases)
    assert sum(1 for case in cases for want in case["values"].values() if want == "BookError") >= 1
