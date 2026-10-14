# -*- coding: utf-8 -*-
"""Строка «механика» сухого прогона у книги формы ВТБ (`ops/tools/reanchor.py`, М§4.6, §8.2, §15.2 п. 3;
docs/REANCHOR.md §3.3, §4): сегментная CoR и пол стоимости клетки — режим с клетками.

**Сегментная CoR.** Общая CoR клетки равна пути режима на структуре нормировки — без ключа
`credit.segment_relative.corporate_share_ref` это доли сегментов в кредитах АС якоря. Пока перенос нормировал заново
на структуре нового якоря, CoR каждого квартала каждой клетки умножалась на отношение Σ w × rel двух структур: на
пробной книге ВТБ (rel 0,7 / 1,8, доля юрлиц 0,7255 → 0,7324 за третий квартал 2026 года) CoR движка после переноса
выше на 0,78 % своей величины (+0,7…0,8 б.п.), строка «механика» сухого прогона −0,28 ₽ точки, клетки — до −36 %
(флаг 2 четвёртого прохода ядра; `--no-cells` этого не видит). Перенос пишет в книгу-кандидата долю прежнего якоря;
заданный ключ оставляет. Проверки: клетка, перезаякоренная на своём пути, сохраняет стоимость (допуск — десятая доля
допуска методики, как у формы без сегментов); ключ кандидата — доля юрлиц прежнего якоря, посчитанная по остаткам
клетки на якоре независимо от кода инструмента; заданный ключ остаётся; у книги без сегментной схемы ключа нет.
Аналитические проверки ядра — `tests/support_segment_cor.py` (их же зовёт мутационный набор `tests/mutations.py`).

**Пол стоимости клетки** (`valuation.cell_floor`, М§8.2): в V0 слоя клетка входит стоимостью в цене — не ниже пола.
Строка «механика» переводит стоимости клеток на своём пути в цену прогона A⁺ (`_priced`); пока она складывала оценки
клеток как есть, у книги с полом строка несла отрицательные стоимости клеток на полу и при неизменных клетках: на
пробе Б ВТБ с докапитализацией и полом 0 — −1,00 ₽ точки и −8,7 млрд ₽ V0 «свой взгляд» без единой новости.
Проверка: на прежних стоимостях клеток строка цены — сама точка и V0 слоёв прогона.

Мутации инструмента (`TOOL_MUTATIONS`) — правка исходного текста инструмента, как в `tests/test_reanchor_shares.py`.
Фикстура — форма образца `tests/fixtures/core` с ключами, подставленными тестом. Даты — от периодов книги фикстуры,
не от «сегодня».
"""
from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from model.grid import run_grid
from tests import support_segment_cor as S
from tests.support_core import fixture_book, fixture_facts
from tests.test_reanchor import CELLS, R
from tests.test_reanchor_shares import TOOL, mutant_tool

tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

MIX_TOL = 1e-12                              # ключ кандидата против доли прежнего якоря (запись — 12 знаков)
MOVED = 1e-3                                 # доля юрлиц за закрываемый квартал фикстуры сдвигается больше этого
FLOOR = 6000.0                               # млрд ₽: пол клетки фикстуры выше стоимостей клеток кризиса и спада
#                                              мира M (≈ 3 100…5 600) — часть клеток на полу
PRICE_TOL = 1e-9                             # ₽ и млрд ₽: строка цены на прежних стоимостях — сам прогон


def scene_of(tool: Any, book: Any, facts: Any = None) -> SimpleNamespace:
    """Сухой прогон инструментом `tool`: прежняя книга с ожидаемым наблюдением, ожидаемый отчёт слоя."""
    facts = fixture_facts() if facts is None else facts
    v = tool.period_end(str(book.get("meta.first_period"))) + timedelta(days=2)
    live = tool.live_at(book, facts, v)
    plus, run_plus, obs = tool.expected_run(book, facts, live)
    return SimpleNamespace(book=book, facts=facts, v=v, run_plus=run_plus, obs=obs,
                           expected=tool.expected_report(book, facts, run=run_plus))


@lru_cache(maxsize=None)
def scene(share: float | None = None) -> SimpleNamespace:
    return scene_of(R, S.seg_book(share))


def candidate(tool: Any, s: SimpleNamespace) -> Any:
    return tool.reanchor(s.book, s.facts, s.expected, valuation_date=s.v, base_run=s.run_plus)


def _key(data: dict) -> Any:
    return data["credit"]["segment_relative"].get("corporate_share_ref")


# ------------------------------------------------------------------ проверки (подлинный инструмент и мутанты)


def check_cells_keep_their_value(tool: Any) -> None:
    """Каждая клетка CELLS, перезаякоренная на своём пути, сохраняет стоимость (М§15.2): CoR каждого квартала та же,
    что у прежней книги."""
    s = scene_of(tool, S.seg_book())
    mech = tool.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=CELLS)
    assert [r["key"] for r in mech["rows"]] == list(CELLS)
    assert mech["ok"] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 10, mech["worst"]


def check_the_candidate_carries_the_old_structure(tool: Any) -> None:
    """Ключ кандидата — доля юрлиц прежнего якоря (по остаткам клетки на якоре); доля нового якоря другая — иначе
    проверка ничего не различала бы; ядро кандидата нормирует на ключе; отчёт инструмента печатает обе доли."""
    s = scene()
    cand = candidate(tool, s)
    was = S.anchor_share(s.run_plus.cell(*CELLS[0]), s.book.get("nii.books"))
    assert _key(cand.data) == pytest.approx(was, abs=MIX_TOL)
    mix = cand.derived["segment_mix"]
    assert mix["written"] and mix["old_anchor"] == pytest.approx(was, abs=MIX_TOL)
    assert abs(mix["new_anchor"] - was) > MOVED, mix
    assert cand.book.get(S.KEY) == pytest.approx(was, abs=MIX_TOL)
    assert any(path == ("credit", "segment_relative", "corporate_share_ref") for path, _, _ in cand.changes)
    line = tool.segment_mix_line(cand.derived)
    assert line and S.KEY in line and f"{was:.6f}" in line and f"{mix['new_anchor']:.6f}" in line


def check_a_key_of_the_book_stays(tool: Any) -> None:
    """Книга, которая несёт ключ, переносится с тем же ключом: структура нормировки — суждение прежней книги."""
    s = scene(S.SHARE)
    cand = candidate(tool, s)
    assert _key(cand.data) == S.SHARE and not cand.derived["segment_mix"]["written"]
    assert not any(path[:2] == ("credit", "segment_relative") for path, _, _ in cand.changes)


def check_no_scheme_no_key(tool: Any) -> None:
    """У книги без сегментной схемы (форма образца) ключа нет, и строки отчёта тоже."""
    s = scene_of(tool, fixture_book())
    cand = candidate(tool, s)
    assert "corporate_share_ref" not in cand.data["credit"]["segment_relative"]
    assert cand.derived["segment_mix"] is None and tool.segment_mix_line(cand.derived) is None


@lru_cache(maxsize=None)
def floor_book() -> Any:
    return fixture_book().with_overrides({"valuation.cell_floor": FLOOR}, create=True)


def check_the_price_line_reads_the_floor(tool: Any) -> None:
    """У книги с полом клетки (М§8.2) строка цены инструмента на прежних стоимостях клеток — низ, точка, верх и V0
    слоёв самого прогона: клетки на полу входят стоимостью в цене, как в слоях."""
    run = run_grid(floor_book(), fixture_facts())
    floored = [c for c in run.cells if c.v_ri - run.pending_dividend < FLOOR]
    assert run.cell_floor == FLOOR and len(floored) >= 3, len(floored)
    got = tool._priced(run, {c.key: c.v_ri for c in run.cells})
    for name in ("low", "point", "high"):
        assert got[name] == pytest.approx(getattr(run, name), abs=PRICE_TOL), name
    for name, layer in run.layers.items():
        assert got["v0"][name] == pytest.approx(layer.v0, abs=PRICE_TOL), name


# ------------------------------------------------------------------ тесты


@tact
def test_cells_with_segment_cor_reanchored_on_their_own_paths_keep_their_value():
    check_cells_keep_their_value(R)


@tact
def test_the_candidate_carries_the_normalisation_of_the_old_anchor():
    check_the_candidate_carries_the_old_structure(R)


@tact
def test_a_book_with_the_key_keeps_it():
    check_a_key_of_the_book_stays(R)


@tact
def test_a_book_without_the_scheme_gets_no_key():
    check_no_scheme_no_key(R)


@tact
def test_reserves_on_the_structure_of_the_key():
    S.check_llp_on_the_structure_of_the_key()


@tact
def test_reserves_without_the_key_are_on_the_anchor():
    S.check_llp_without_the_key_is_on_the_anchor()


@tact
def test_schema_of_the_key():
    S.check_schema_of_the_key()


@tact
def test_the_price_line_of_a_book_with_a_cell_floor_is_the_run_itself():
    check_the_price_line_reads_the_floor(R)


@ci_only
def test_the_mechanics_line_of_a_book_with_a_cell_floor_stays():
    """Сухой прогон книги с полом клетки, все клетки: строка «механика» — в сотой доле шага печати (клетки на своём
    пути сохраняют стоимость, клетки на полу входят в цену полом)."""
    s = scene_of(R, floor_book())
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v)
    step = float(s.book.get("valuation.headline.print_step"))
    assert mech["ok"] and abs(mech["headline"]["point"] - s.run_plus.point) <= 0.01 * step, (
        mech["headline"]["point"], s.run_plus.point)


@ci_only
def test_every_cell_with_segment_cor_keeps_its_value_and_the_point_stays():
    """Все клетки сетки и точка строки «механика» (М§15.2): допуск — десятая доля допуска методики; точка — сотая
    шага печати."""
    s = scene()
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v)
    assert len(mech["rows"]) == len(s.run_plus.cells) and mech["ok"]
    assert abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 10, mech["worst"]
    step = float(s.book.get("valuation.headline.print_step"))
    assert abs(mech["headline"]["point"] - s.run_plus.point) <= 0.01 * step


@ci_only
def test_a_second_carry_keeps_the_structure_of_the_first_anchor():
    """Цепочка из двух переносов: второй кандидат несёт ту же долю — прежнего якоря первой книги."""
    first = candidate(R, scene())
    second = candidate(R, scene_of(R, first.book, first.facts))
    assert _key(second.data) == _key(first.data) and not second.derived["segment_mix"]["written"]
    assert run_grid(second.book, second.facts).ctx.prep.segment_w["corporate"] == _key(first.data)


# ------------------------------------------------------------------ мутации инструмента (М§18)

CARRY = '    derived["segment_mix"] = carry_segment_mix(X, book, old_af, new_af)\n'
TOOL_MUTATIONS: tuple[tuple[str, str, str, str, Callable[[Any], None]], ...] = (
    ("TS1", "структура нормировки не переносится (ядро кандидата нормирует на новом якоре)",
     CARRY, '    derived["segment_mix"] = None\n', check_cells_keep_their_value),
    ("TS2", "ключ записан долей нового якоря",
     "        _set(X, SEGMENT_SHARE, _r(was, SHARE_DIGITS))\n", "        _set(X, SEGMENT_SHARE, _r(now, SHARE_DIGITS))\n",
     check_cells_keep_their_value),
    ("TS3", "заданный ключ книги переписан долей якоря",
     "    if key is None:\n        _set(X, SEGMENT_SHARE,", "    if True:\n        _set(X, SEGMENT_SHARE,",
     check_a_key_of_the_book_stays),
    ("TS4", "ключ пишется и книге без сегментной схемы",
     '    if not book.get("credit.segment_relative.enabled"):\n        return None\n', "",
     check_no_scheme_no_key),
    ("TS5", "строка цены складывает оценки клеток без пола (клетки на полу — отрицательными стоимостями)",
     "    if floor is not None:                    # стоимость клетки в цене V^F (М§8.2) — то же правило, что у слоёв\n",
     "    if False:\n", check_the_price_line_reads_the_floor),
)


@pytest.mark.parametrize("mutation", TOOL_MUTATIONS, ids=lambda m: m[0])
def test_every_mutation_of_the_mechanics_line_is_caught(mutation):
    """Каждую ошибку переноса структуры нормировки и строки цены роняет проверка этого файла; подлинный инструмент ту
    же проверку проходит (тесты выше)."""
    ident, title, find, replace, check = mutation
    tool = mutant_tool(find, replace)
    try:
        check(tool)
    except (AssertionError, pytest.fail.Exception):
        return
    pytest.fail(f"мутация инструмента {ident} «{title}» не поймана")


@tact
def test_targets_of_the_mechanics_line_mutations_exist():
    source = TOOL.read_text(encoding="utf-8")
    assert len({m[0] for m in TOOL_MUTATIONS}) == len(TOOL_MUTATIONS)
    for ident, _, find, _, _ in TOOL_MUTATIONS:
        assert source.count(find) == 1, ident
