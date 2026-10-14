# -*- coding: utf-8 -*-
"""Перезаякоривание книги с ключами восьмого прохода (`ops/tools/reanchor.py`, М§15.2 п. 3; REANCHOR §3.4; строки
«Перезаякоривание» и «Мутации восьмого прохода» М§18; пример L.5).

Доля добавочного капитала (`capital.at1_share`): квартал ключа — по положению относительно нового якоря, как у доли
инструментов, (а) новый якорь раньше квартала q_α − 1 — как есть, (б) новый якорь — квартал q_α − 1 — как есть, квартал
ключа — новый `first_period`, (в) квартал ключа не позже нового якоря — переписан на новый `first_period`; база — суммой
(слово `anchor` — числом факта AT1_0 прежней книги), слот купона якоря не трогается; ожидаемый отчёт несёт AT1 клеток.
Надбавка за субординацию (`capital.n20.t2_premium`): база — суммой (anchor — числом T2_0 прежней книги); надбавка
ожидаемого отчёта — вне остатка «ЧПД − проценты книг», который несут ставки нового якоря. Прочие движения за T — без
правки. Проверки — тождества, выведенные из книги и рядов клетки независимо от кода инструмента: клетка, перезаякоренная
на своём пути, держит прежнюю долю, продолжает купон новых выпусков и надбавку прежней суммой.

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

from model.book import book_roles
from model.grid import run_grid
from model.paths import path_value
from tests import support_core_pass5 as S5
from tests import support_core_pass8 as S8
from tests.support_core import fixture_facts
from tests.test_reanchor import R
from tests.test_reanchor_shares import _carried, _scene, mutant_tool

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "ops" / "tools" / "reanchor.py"
tact = pytest.mark.tact

A1, TP, T2 = "capital.at1_share", "capital.n20.t2_premium", "capital.n20.t2"
EXAMPLE = json.loads((ROOT / "tests" / "fixtures" / "core_pass8" / "example.json").read_text(encoding="utf-8"))
SHARE_TOL = 1e-6                             # доля нового якоря против доли клетки: AT1 и RWA отчёта — 9 знаков, плотности
#                                              RWA кандидата — 6 знаков
CELL = ("H", "norm", "schedule")
T2_BASE = 450.0                              # база надбавки ниже T2_0 = 500,3: надбавка закрываемого квартала не ноль


def _book(when: str | None, *, premium: bool = True):
    changes: dict[str, Any] = {T2: S8.TRAJ_P}
    if when is not None:
        changes.update(S8.at1_key(when))
    if premium:
        changes.update(S8.t2p_key(base=T2_BASE if when is None else "anchor"))
    return S5.book_of(changes)


# ------------------------------------------------------------------ шаг инструмента на словаре книги (пример L.5)


def check_carry(tool: Any) -> None:
    """`carry_at1_share` на строках примера L.5: квартал ключа 2028Q3 при новом якоре 2028К1 и 2028К2 — как есть, при
    2028К3 — переписан на новый `first_period` 2028Q4 (при любом `enabled`); база `anchor` — числом факта AT1_0 прежней
    книги (20), число — как есть; без ключа шага нет. `carry_t2_premium`: база `anchor` — числом T2_0 прежней книги,
    число — как есть. Строки отчёта называют квартал до и после и базу."""
    at1_0 = EXAMPLE["at1"]["inputs"]["at1_0"]
    for row in EXAMPLE["reanchor"]["rows"]:
        for enabled in (True, False):
            for base in ("anchor", 20.0):
                X = {"capital": {"at1_share": {"enabled": enabled, "from": "2028Q3", "spread": 0.04, "base": base}}}
                derived, warnings = {}, []
                tool.carry_at1_share(X, row["new_anchor"], row["first_period"], at1_0, derived, warnings)
                node = X["capital"]["at1_share"]
                assert node["from"] == row["from"], (row, enabled)
                assert node["base"] == row["base"] and isinstance(node["base"], float), (row, base, node["base"])
                assert node["spread"] == 0.04 and node["enabled"] is enabled
                assert derived["at1_share"]["from"] == ("2028Q3", row["from"])
                assert derived["at1_share"]["base"] == (base, at1_0 if base == "anchor" else base)
                moved = row["from"] != "2028Q3"
                assert sum("at1_share.from" in w for w in warnings) == int(moved), (row, warnings)
                assert sum("at1_share.base" in w for w in warnings) == int(base == "anchor")
                line = tool.at1_share_lines(derived, row["at1_report"])[0]
                assert f"2028Q3 → {row['from']}" in line and A1 in line
                assert f"сверх базы {row['stock_above_base']:.3f}" in line, line
    for X in ({"capital": {}}, {"capital": {"n20": {}}}):
        kept, derived = copy.deepcopy(X), {}
        tool.carry_at1_share(X, "2028Q3", "2028Q4", at1_0, derived, [])
        tool.carry_t2_premium(X, 10.0, derived, [])
        assert X == kept and not derived and tool.at1_share_lines(derived) == []
    for base, want in (("anchor", 10.0), (7.5, 7.5)):
        X = {"capital": {"n20": {"t2_premium": {"enabled": True, "spread": 0.025, "base": base}}}}
        derived, warnings = {}, []
        tool.carry_t2_premium(X, 10.0, derived, warnings)
        assert X["capital"]["n20"]["t2_premium"]["base"] == want and len(warnings) == int(base == "anchor")
        assert derived["t2_premium"]["base"] == (base, want)
        assert TP in tool.at1_share_lines(derived)[0]


def check_report(tool: Any) -> None:
    """Ожидаемый отчёт клетки книги с ключом доли AT1 от `first_period` несёт AT1 клетки в квартале 1 (`α_c × RWA_c,1`,
    не факт прежнего якоря), без ключа — факт якоря; книга с ключом надбавки — надбавку квартала (`pnl.t2_premium`),
    без ключа поля нет."""
    facts = fixture_facts()
    for when, premium in (("2026Q3", True), (None, False)):
        run = run_grid(_book(when, premium=premium), facts)
        c = run.cell(*CELL)
        rep = tool._cell_report(run, {CELL: 1.0})
        at1_0 = S8.at1_0(run)
        if when is not None:
            assert abs(c.quarters["at1"][1] - at1_0) > 0.1
            assert abs(rep["balance"]["at1"] - c.quarters["at1"][1]) < 1e-8, rep["balance"]["at1"]
        else:
            assert rep["balance"]["at1"] == at1_0
        if premium:
            assert abs(rep["pnl"]["t2_premium"] - c.quarters["t2_premium"][1]) < 1e-9
        else:
            assert "t2_premium" not in rep["pnl"]


def check_residual(tool: Any) -> None:
    """Надбавка ожидаемого отчёта — вне остатка «ЧПД − проценты книг» (М§15.2 п. 3): у книги с ключом надбавки (база
    ниже T2_0 — надбавка квартала не ноль) ставки якоря книг активов кандидата — проценты книги отчёта на средний
    остаток × 365/дни без доли остатка (остаток — ноль до округления отчёта); с надбавкой в остатке ставки сдвинулись
    бы на её долю процентного дохода."""
    facts = fixture_facts()
    book = _book(None)
    run = run_grid(book, facts)
    rep = tool._cell_report(run, {CELL: 1.0})
    assert rep["pnl"]["t2_premium"] > 0.1
    new = tool.facts_after(book, facts, rep, update_bridge=False, series_notes={})
    roles = book_roles(book.get("nii.books"))
    tl = run.ctx.timeline
    days = (tl.end(1) - tl.end(0)).days
    old_bal = {b: run.cell(*CELL).books[b]["balance"][0] for b in roles.names}   # остатки якоря (факты)
    nb = new.files["nii_books"]
    checked = 0
    for b in roles.assets:
        node = (nb.get("books") or nb).get(b)
        if not isinstance(node, dict) or "rate_anchor" not in node:
            continue
        avg = (old_bal[b] + float(rep["balance"]["books"][b])) / 2
        want = float(rep["interest"][b]) / avg * 365 / days
        assert abs(float(node["rate_anchor"]["v"]) - want) < 2e-8, (b, node["rate_anchor"]["v"], want)
        checked += 1
    assert checked >= 3, checked


@tact
def test_carry_of_the_keys():
    check_carry(R)


@tact
def test_expected_report_carries_the_at1_of_the_cell_and_the_premium():
    check_report(R)


def test_premium_of_the_report_is_out_of_the_residual_carried_by_the_rates():
    check_residual(R)


# ------------------------------------------------------------------ клетка на своём пути: три положения квартала ключа


@lru_cache(maxsize=None)
def scene(when: str | None) -> SimpleNamespace:
    """Сухой прогон книги с ключами доли AT1 от `when` и надбавки (None — без доли AT1; надбавка — с базой-числом)."""
    return _scene(_book(when), fixture_facts())


@pytest.mark.parametrize("when, now, moved", (("2027Q1", "2027Q1", False), ("2026Q4", "2026Q4", False),
                                              ("2026Q3", "2026Q4", True)), ids=("a", "b", "c"))
def test_a_cell_reanchored_on_its_own_path_keeps_the_share_the_coupon_and_the_premium(when, now, moved):
    """Клетка, перезаякоренная на своём пути (М§15.2 п. 3, пример L.5): квартал ключа переписан только тогда, когда
    новый якорь не раньше его; база — числом AT1_0 прежней книги; доля клетки кандидата равна доле клетки прежней книги;
    ряд AT1 кандидата с квартала ключа — доля на его RWA; купон сверх базы и надбавка кандидата продолжают прежние
    (квартал 1 кандидата — квартал 2 прежней клетки); база надбавки — числом T2_0 прежней книги."""
    s = scene(when)
    c = _carried(R, CELL, s=s)
    node = c.cand.data["capital"]["at1_share"]
    old_run = s.run_plus
    at1_0 = S8.at1_0(old_run)
    assert node["from"] == now and node["base"] == at1_0
    assert c.cand.derived["at1_share"]["from"] == (when, now)
    assert any("at1_share.from" in w for w in c.cand.warnings) is moved
    assert c.cand.data["capital"]["n20"]["t2_premium"]["base"] == path_value(S8.TRAJ_P, old_run.ctx.timeline.period(0))
    old_tl, new_tl = old_run.ctx.timeline, c.run.ctx.timeline
    q_old, q_new = old_tl.index(when), new_tl.index(now)
    alpha_old = c.old.quarters["at1"][q_old - 1] / c.old.quarters["rwa"][q_old - 1]
    alpha_new = c.cell.quarters["at1"][q_new - 1] / c.cell.quarters["rwa"][q_new - 1]
    assert abs(alpha_new / alpha_old - 1) < SHARE_TOL, (alpha_new, alpha_old)
    for q in range(q_new, new_tl.Q + 1):
        assert abs(c.cell.quarters["at1"][q] - alpha_new * c.cell.quarters["rwa"][q]) < 1e-9
    # купон сверх базы и надбавка: квартал 1 кандидата — квартал 2 прежней клетки
    assert abs(c.cell.quarters["coupon_new"][1] - c.old.quarters["coupon_new"][2]) < 1e-6
    assert abs(c.cell.quarters["t2_premium"][1] - c.old.quarters["t2_premium"][2]) < 1e-9
    assert abs(c.cell.quarters["at1"][0] - c.old.quarters["at1"][1]) < 1e-8
    text = "\n".join(R.at1_share_lines(c.cand.derived, c.cell.quarters["at1"][0]))
    assert f"квартал ключа {when} → {now}" in text and "база anchor →" in text and TP in text


def test_a_book_without_the_step_refuses_loudly():
    """Без шага инструмента квартал ключа, ушедший в историю, остаётся раньше нового `first_period` — отказ схемы
    (прил. A № 31), а не тихий сдвиг доли."""
    tool = mutant_tool("        to = first_new if pindex(was) <= pindex(period) else was      # ушедший в историю — новый first_period\n",
                       "        to = was      # ушедший в историю — новый first_period\n")
    with pytest.raises(Exception, match="at1_share"):
        _carried(tool, CELL, s=scene("2026Q3"))


# ------------------------------------------------------------------ мутации инструмента


def check_all(tool: Any) -> None:
    check_carry(tool)
    check_report(tool)
    check_residual(tool)


TOOL_MUTATIONS: tuple[tuple[str, str, str, str, Callable[[Any], None]], ...] = (
    ("Y1", "квартал ключа доли AT1 не переписывается, когда новый якорь не раньше его",
     "        to = first_new if pindex(was) <= pindex(period) else was      # ушедший в историю — новый first_period\n",
     "        to = was      # ушедший в историю — новый first_period\n", check_all),
    ("Y2", "база доли AT1 `anchor` не записывается числом прежнего факта",
     "            _set(X, f\"{AT1_SHARE}.base\", float(at1_0))\n", "            pass\n", check_all),
    ("Y3", "ожидаемый отчёт несёт AT1 фактом прежнего якоря под ключом доли",
     '        "at1": af.at1 if prep.at1_from is None else avg("at1"), "nci": af.nci,\n',
     '        "at1": af.at1, "nci": af.nci,\n', check_all),
    ("Y4", "надбавка ожидаемого отчёта входит в остаток, который несут ставки нового якоря",
     '    residual = float(P["nii"]) + float(P.get("t2_premium") or 0.0) - (income - expense - dia)\n',
     '    residual = float(P["nii"]) - (income - expense - dia)\n', check_all),
    ("Y5", "база надбавки `anchor` не записывается числом прежнего T2_0",
     "        _set(X, f\"{T2_PREMIUM}.base\", float(t2_0))\n", "        pass\n", check_all),
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
