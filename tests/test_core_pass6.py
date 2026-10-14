# -*- coding: utf-8 -*-
"""Шестой проход ядра (М§4.7, §18, прил. I): база объёма `iea` квартала фактов — в определении клетки; псевдонимы
модулей проверок мутационного набора. Проверки — `tests/support_core_pass6.py` (их же зовёт `tests/mutations.py`)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests import support_core_pass6 as S

ROOT = Path(__file__).resolve().parents[1]
tact = pytest.mark.tact


@tact
def test_base_of_a_quarter_of_facts_is_the_cell_definition():
    S.check_base_of_the_facts()


@tact
def test_refusals_of_the_base_of_facts():
    S.check_refusals()


@tact
def test_cell_quarter_and_facts_quarter_are_one_average():
    S.check_identity_on_the_cells()


@tact
def test_example_i1():
    S.check_example_i1()


@tact
def test_aliases_of_the_check_modules_do_not_repeat():
    """`tests/mutations.py::_checks()`: у каждого модуля проверок свой псевдоним — повтор затеняет прежний модуль, и его
    проверки на подлинном ядре падают `AttributeError` (раздел четвёртого прохода — `S4P`, образца Т — `S4`)."""
    tree = ast.parse((ROOT / "tests" / "mutations.py").read_text(encoding="utf-8"))
    checks = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_checks")
    seen: dict[str, str] = {}
    for node in ast.walk(checks):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname or alias.name
                module = f"{getattr(node, 'module', '') or ''}.{alias.name}"
                assert name not in seen or seen[name] == module, (name, seen[name], module)
                seen[name] = module
    assert seen.get("S4P") == "tests.support_core_pass4" and seen.get("S4") == "tests.support_core_t4"
