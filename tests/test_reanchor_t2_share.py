# -*- coding: utf-8 -*-
"""Перезаякоривание книги с долей инструментов в RWA своей клетки (`capital.n20.t2_share`, `ops/tools/reanchor.py`,
М§4.11, §15.2 пп. 3 и 10; строки «Перезаякоривание» и «Мутации седьмого прохода» М§18; пример K.5).

Квартал ключа переносится по положению относительно нового якоря: (а) новый якорь раньше квартала q_χ − 1 — ключ как
есть; (б) новый якорь — квартал q_χ − 1 — ключ как есть, квартал ключа становится новым `first_period`; (в) квартал
ключа не позже нового якоря — переписан на новый `first_period`. Ожидаемый отчёт несёт T2 клетки (`χ_c × RWA_c,1` с
квартала ключа), а не значение траектории; оценка уровней до выхода формы — доля якоря на RWA оценки
`T2_0 × RWA / RWA_0`. Проверки — тождества, выведенные из книги и рядов клетки независимо от кода инструмента: доля
клетки, перезаякоренной на своём пути, — прежняя, и её Н20.0 — прежний путь во всех кварталах.

Мутации инструмента (`TOOL_MUTATIONS`) — правка исходного текста инструмента (`mutant_tool` файла
`tests/test_reanchor_shares.py`): каждую замену роняет проверка этого файла.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from model.grid import run_grid
from model.paths import path_value
from tests import support_core_pass5 as S5
from tests.support_core import fixture_facts
from tests.test_reanchor import R
from tests.test_reanchor_shares import _carried, _scene, mutant_tool

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "ops" / "tools" / "reanchor.py"
tact = pytest.mark.tact

KEY, T2 = "capital.n20.t2_share", "capital.n20.t2"
TRAJ = {"2026Q2": 500.3, "2027": 530.0, "2029": 600.0, "LT": 700.0, "LT_from": 2033}
EXAMPLE = json.loads((ROOT / "tests" / "fixtures" / "core_pass7" / "example.json").read_text(encoding="utf-8"))
SHARE_TOL = 1e-6                             # доля нового якоря против доли клетки: T2 и RWA отчёта — 9 знаков, плотности
#                                              RWA кандидата — 6 знаков
PATH_TOL = 1e-7                              # разность путей Н20.0 «кандидат − прежняя клетка» у книги с ключом и без него:
#                                              сам путь отличается и без ключа (округление DPS, остаток калибровки); ключ
#                                              добавляет только χ × остаток записи плотностей RWA (≈ 0,006 × 3e-6)
CELL = ("H", "norm", "schedule")


def _book(when: str, enabled: bool = True):
    return S5.book_of({T2: TRAJ, KEY: {"enabled": enabled, "from": when}})


# ------------------------------------------------------------------ шаг инструмента на словаре книги (пример K.5)


def check_carry(tool: Any) -> None:
    """`carry_t2_share` на кварталах примера K.5: при новом якоре 2028К1 и 2028К2 квартал ключа 2028Q3 — как есть, при
    2028К3 — переписан на новый `first_period` 2028Q4; выключенный ключ переписывается так же (границы квартала
    схема проверяет при любом `enabled`); без ключа и без поля `from` шага нет; строка отчёта называет квартал до и
    после."""
    for case in EXAMPLE["reanchor"]["cases"].values():
        for enabled in (True, False):
            X = {"capital": {"n20": {KEY.rsplit(".", 1)[1]: {"enabled": enabled, "from": "2028Q3"}}}}
            derived, warnings = {}, []
            tool.carry_t2_share(X, case["new_anchor"], case["new_first_period"], derived, warnings)
            assert X["capital"]["n20"]["t2_share"]["from"] == case["from_new"], (case, enabled)
            assert derived["t2_share"]["from"] == ("2028Q3", case["from_new"]), case
            assert bool(warnings) is case["from_moved"], (case, warnings)
            line = tool.t2_share_line(derived)
            assert f"2028Q3 → {case['from_new']}" in line and KEY in line
    for X in ({"capital": {"n20": {}}}, {"capital": {"n20": {"t2_share": {"enabled": False}}}}):
        kept, derived = copy.deepcopy(X), {}
        tool.carry_t2_share(X, "2028Q3", "2028Q4", derived, [])
        assert X == kept and "t2_share" not in derived and tool.t2_share_line(derived) is None


def check_report_and_levels(tool: Any) -> None:
    """Ожидаемый отчёт клетки книги с ключом от `first_period` несёт T2 клетки `χ_c × RWA_c,1` (у книги с ключом позже —
    значение траектории); оценка уровней до выхода формы (М§15.2 п. 10) — доля якоря на RWA оценки
    `T2_0 × RWA / RWA_0` (у книги с ключом позже — значение траектории)."""
    facts = fixture_facts()
    for when, keyed in (("2026Q3", True), ("2027Q1", False)):
        book = _book(when)
        run = run_grid(book, facts)
        tl = run.ctx.timeline
        c = run.cell(*CELL)
        t2_1, traj_1 = c.quarters["t2"][1], path_value(book.get(T2), tl.period(1))
        rep = tool._cell_report(run, {CELL: 1.0})
        if keyed:
            chi = path_value(book.get(T2), tl.period(0)) / c.quarters["rwa"][0]
            assert abs(t2_1 - chi * c.quarters["rwa"][1]) < 1e-9 and abs(t2_1 - traj_1) > 1.0
        assert abs(rep["capital"]["t2"] - (t2_1 if keyed else traj_1)) < 1e-8, (when, rep["capital"]["t2"])
        _, moved = tool.estimated_levels(book, facts, rep, run, {CELL: 1.0})
        rwa = moved["basel_rwa"][1]
        want = path_value(book.get(T2), tl.period(0)) * rwa / c.quarters["rwa"][0] if keyed else traj_1
        assert abs(moved["t2"][1] - want) < 2e-6, (when, moved["t2"], want)
        assert abs(rwa / c.quarters["rwa"][1] - 1) < 1e-6


@tact
def test_carry_of_the_key_quarter():
    check_carry(R)


@tact
def test_expected_report_and_estimated_levels_carry_the_t2_of_the_cell():
    check_report_and_levels(R)


# ------------------------------------------------------------------ клетка на своём пути: три положения квартала ключа


@lru_cache(maxsize=None)
def scene(when: str | None) -> SimpleNamespace:
    """Сухой прогон книги с ключом от `when` (None — та же книга без ключа)."""
    book = S5.book_of({T2: TRAJ}) if when is None else _book(when)
    return _scene(book, fixture_facts())


def _gaps(c: SimpleNamespace) -> list[float]:
    """Н20.0 клетки кандидата минус Н20.0 прежней клетки в том же квартале."""
    return [c.cell.quarters["n20"][q] - c.old.quarters["n20"][q + 1] for q in range(c.run.ctx.timeline.Q + 1)]


@lru_cache(maxsize=None)
def plain_gaps() -> tuple[float, ...]:
    return tuple(_gaps(_carried(R, CELL, s=scene(None))))


def _share(c: Any, q_chi: int) -> float:
    return c.quarters["t2"][q_chi - 1] / c.quarters["rwa"][q_chi - 1]


@pytest.mark.parametrize("when, now, moved", (("2027Q1", "2027Q1", False), ("2026Q4", "2026Q4", False),
                                              ("2026Q3", "2026Q4", True)), ids=("a", "b", "c"))
def test_a_cell_reanchored_on_its_own_path_keeps_the_share_and_the_ratio(when, now, moved):
    """Клетка, перезаякоренная на своём пути (М§15.2 п. 3, пример K.5): квартал ключа переписан только тогда, когда
    новый якорь не раньше его; доля клетки кандидата равна доле клетки прежней книги; ряд T2 кандидата с квартала ключа
    — доля на RWA кандидата; Н20.0 кандидата идёт по прежнему пути клетки так же, как у той же книги без ключа (разность
    путей — остаток округления DPS и калибровки — та же во всех кварталах до `PATH_TOL`)."""
    s = scene(when)
    c = _carried(R, CELL, s=s)
    assert c.cand.data["capital"]["n20"]["t2_share"]["from"] == now
    assert c.cand.derived["t2_share"]["from"] == (when, now)
    assert any("t2_share.from" in w for w in c.cand.warnings) is moved
    old_tl, new_tl = c.s.run_plus.ctx.timeline, c.run.ctx.timeline
    chi_old = _share(c.old, old_tl.index(when))
    q_new = new_tl.index(now)
    chi_new = _share(c.cell, q_new)
    assert abs(chi_new / chi_old - 1) < SHARE_TOL, (chi_new, chi_old)
    assert abs(c.cand.derived["t2_share"]["cells"] / chi_old - 1) < 1e-12
    for q in range(q_new, new_tl.Q + 1):
        assert abs(c.cell.quarters["t2"][q] - chi_new * c.cell.quarters["rwa"][q]) < 1e-9
    worst = max(abs(g - b) for g, b in zip(_gaps(c), plain_gaps()))
    assert worst < PATH_TOL, worst
    line = R.t2_share_line(c.cand.derived, c.cand)              # строка отчёта: квартал до и после, две доли
    assert f"квартал ключа {when} → {now}" in line and "доля нового якоря" in line and "доля клеток прежней" in line


def test_a_book_without_the_step_refuses_loudly():
    """Без шага инструмента квартал ключа, ушедший в историю, остаётся раньше нового `first_period` — отказ схемы
    (прил. A № 30), а не тихий сдвиг доли."""
    tool = mutant_tool("    now = first_new if pindex(was) <= pindex(period) else was\n", "    now = was\n")
    with pytest.raises(Exception, match="t2_share"):
        _carried(tool, CELL, s=scene("2026Q3"))


# ------------------------------------------------------------------ мутации инструмента


def check_all(tool: Any) -> None:
    check_carry(tool)
    check_report_and_levels(tool)


TOOL_MUTATIONS: tuple[tuple[str, str, str, str, Callable[[Any], None]], ...] = (
    ("X1", "квартал ключа не переписывается, когда новый якорь не раньше его",
     "    now = first_new if pindex(was) <= pindex(period) else was\n", "    now = was\n", check_all),
    ("X2", "квартал ключа переписывается и тогда, когда новый якорь раньше квартала перед ключом",
     "    now = first_new if pindex(was) <= pindex(period) else was\n", "    now = first_new\n", check_all),
    ("X3", "ожидаемый отчёт несёт T2 значением траектории под ключом",
     '        capital["t2"] = prep.t2[1] if prep.t2_from is None else avg("t2")',
     '        capital["t2"] = prep.t2[1]', check_all),
    ("X4", "оценка уровней до формы — T2 траектории под ключом",
     "    t2 = float(prep.t2[1]) if prep.t2_from != 1 else float(prep.t2[0]) * rwa / prep.rwa0",
     "    t2 = float(prep.t2[1])", check_all),
)


@pytest.mark.parametrize("mutation", TOOL_MUTATIONS, ids=lambda m: m[0])
def test_every_mutation_of_the_tool_is_caught(mutation):
    ident, title, find, replace, check = mutation
    tool = mutant_tool(find, replace)
    try:
        check(tool)
    except AssertionError:
        return
    pytest.fail(f"мутация инструмента {ident} «{title}» не поймана")


@tact
def test_targets_of_the_tool_mutations_exist():
    source = TOOL.read_text(encoding="utf-8")
    assert len({m[0] for m in TOOL_MUTATIONS}) == len(TOOL_MUTATIONS)
    for ident, _, find, _, _ in TOOL_MUTATIONS:
        assert source.count(find) == 1, ident
