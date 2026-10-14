# -*- coding: utf-8 -*-
"""Перезаякоривание книги с ключами девятого прохода (`ops/tools/reanchor.py`, М§15.2 п. 3; REANCHOR §3.4): разрыв
налога по правилу (`tax.structure`) и купон якоря по ставке своего мира (`capital.at1_coupon`) — без правки
инструмента: у ключей нет состояния и слова `anchor`, кандидат несёт их как есть; налог и прибыль закрываемого квартала
ожидаемого отчёта — ряды клеток (с экономией купона и льготой облигаций); инвариант «факт = ожидание ⇒ механика ≈ 0»
держится на клетках книги с обоими ключами.
"""
from __future__ import annotations

from functools import lru_cache
from types import SimpleNamespace

import pytest

from tests import support_core_pass5 as S5
from tests import support_core_pass9 as S9
from tests.support_core import fixture_facts
from tests.test_reanchor import R, scene_of

tact = pytest.mark.tact
CELLS = (("H", "norm", "schedule"), ("M", "crisis", "strict"), ("N", "soft", "upper"))


@lru_cache(maxsize=None)
def scene(tax: bool = True) -> SimpleNamespace:
    """Сухой прогон книги фикстуры формы образца с ключом купона якоря и (при `tax`) ключом налога: прежняя книга, она
    же с ожидаемым наблюдением, кандидат на ожидаемом отчёте."""
    return scene_of(S5.book_of({**(S9.tax_key() if tax else {}), **S9.cpn_key(), **S9.NCI}), fixture_facts())


@tact
def test_the_keys_are_carried_as_they_are_and_a_cell_keeps_its_value():
    """Кандидат несёт ключи прежней книги как есть (шага инструмента нет); у кандидата налог — правилом в каждом
    квартале каждой клетки, купон якоря — формулой по ключевой своего мира (свойства 32, 39 на сетке кандидата); стоимость
    клетки, перезаякоренной на своём пути, та же: с ключом купона якоря — в десятой доле допуска инструмента, как у книги
    без ключей; с ключом налога — в допуске инструмента. Остаток «ЧПД − проценты книг» ожидаемого отчёта ставки нового
    якоря несут пропорционально процентному доходу книг активов (М§15.2 п. 4) — его доля в книге бумаг становится доходом
    IIS нового якоря и получает льготу облигаций; на фикстуре это до 5e-4 стоимости клетки (без ключа налога — 3e-5).
    Калибровку ζ на новом якоре (REANCHOR §3.4) ведёт книга."""
    for tax, tol in ((False, R.MECHANICS_TOL / 10), (True, R.MECHANICS_TOL)):
        s = scene(tax)
        old, new = s.book.data, s.cand.data
        assert new["capital"]["at1_coupon"] == old["capital"]["at1_coupon"]
        assert new["tax"].get("structure") == old["tax"].get("structure")
        S9.check_anchor_coupon_rows(s.run_e)
        if tax:
            seen = S9.check_tax_rows(s.run_e)
            assert seen["coupon"] >= 300, seen
        mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=CELLS)
        assert [r["key"] for r in mech["rows"]] == list(CELLS)
        assert mech["ok"] and abs(mech["worst"]["rel"]) <= tol, (tax, mech["worst"])
