"""Третий проход ядра — аналитические тесты (строки М§18): доля вычета якоря, постоянная в рублях (ключи
`capital.n20.deductions_fixed_share` и `capital.n11.deductions_fixed_share`, М§4.11, §4.14.5, §7, прил. A № 21),
и чтение траекторий по таблице случаев (М§0.4, прил. F.3).

Проверки — `tests/support_core_pass3.py` (те же функции зовёт мутационный набор `tests/mutations.py`); фикстуры —
формы образца `tests/fixtures/core` и `core_t` с ключами, подставленными тестом; числовой пример — приложение F
методики (`tests/fixtures/core_pass3/example.json`). В такт сервера (метка `tact`) входит сжатый набор; быстрые
выпуски и проверки на нескольких сетках идут в CI.
"""

from __future__ import annotations

import pytest

from model.book_schema import KEYS
from tests import support_core_pass3 as S

tact = pytest.mark.tact                  # быстрые тесты ядра на фикстуре — в такте сервера


# ------------------------------------------------------------------ доля вычета якоря (М§4.11)


@tact
def test_zero_shares_are_the_book_without_keys_bit_for_bit():
    S.check_zero_shares_are_the_book_without_keys()


@tact
def test_deduction_row_is_the_formula_of_the_rwa_row_of_the_cell():
    S.check_deduction_is_the_formula_of_the_rwa_row()


@tact
def test_anchor_row_reproduces_both_ratios_at_any_share():
    S.check_anchor_row_at_any_share()


@tact
def test_share_one_keeps_the_deduction_at_the_anchor_amount():
    S.check_share_one_keeps_the_deduction_constant()


def test_capital_ratio_and_terminal_excess_are_higher_by_the_fixed_part():
    S.check_capital_is_higher_by_the_fixed_part()


def test_share_is_not_a_relief_and_the_value_of_a_short_cell_does_not_fall():
    S.check_share_is_not_a_relief()


def test_anchor_deduction_is_not_interchangeable_with_the_gap():
    S.check_anchor_deduction_and_gap_are_not_interchangeable()


def test_bridge_row_of_deductions_carries_the_growing_part_only():
    S.check_bridge_row_of_deductions()


def test_recapitalization_of_a_book_with_shares():
    S.check_recapitalization_with_shares()


@tact
def test_schema_refuses_a_share_out_of_bounds_and_a_single_key():
    S.check_schema_of_the_shares()


def test_shares_are_inputs_of_the_cell_pass():
    S.check_axis_of_the_shares_moves_the_deduction()


@tact
def test_new_keys_of_the_third_pass_are_in_the_closed_schema():
    keys = set(KEYS)
    for key in ("capital.n20.deductions_fixed_share", "capital.n11.deductions_fixed_share"):
        assert key in keys, key


# ------------------------------------------------------------------ пример приложения F и чтение траекторий


@tact
def test_example_of_appendix_f_is_reproduced():
    S.check_example_f()


@tact
def test_trajectory_reader_gives_the_table_of_cases():
    S.check_trajectory_cases()
