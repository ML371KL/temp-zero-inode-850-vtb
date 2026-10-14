"""Второй проход ядра — аналитические тесты (строки М§18): квартал решения о взносе, нижняя граница окна, состав
точек инварианта, правило «при равенстве», DPS с поправкой делителя, норма клетки, срок избыточной доходности;
общие правила ядра — число клеток по перечням книги и клетка нулевой вероятности, допуск сверки заголовка, база
ожидания нау-каста, сводка контрольной модели своей книги, оси полосы на общем пути.

Проверки — `tests/support_core_pass2.py` (те же функции зовёт мутационный набор `tests/mutations.py`); фикстуры —
формы образца `tests/fixtures/core` и `core_t` с подменами теста, числовой пример — приложение E методики
(`tests/fixtures/core_recap/example_q4.json`). В такт сервера (метка `tact`) входит сжатый набор; быстрые выпуски
и проверки на нескольких сетках идут в CI.
"""

from __future__ import annotations

import pytest

from model.book_schema import KEYS
from tests import support_core_pass2 as S

tact = pytest.mark.tact                  # быстрые тесты ядра на фикстуре — в такте сервера


# ------------------------------------------------------------------ квартал решения о взносе (М§4.14)


@tact
def test_decision_quarter_key_equal_to_the_agm_quarter_is_the_book_without_the_key():
    S.check_key_equal_to_the_agm_quarter()


@tact
def test_contributions_stand_only_in_the_decision_quarter():
    S.check_decisions_stand_in_the_decision_quarter()


def test_first_decision_is_reproduced_by_the_grid_without_contributions():
    S.check_first_decision_by_the_plain_grid()


def test_trial_pass_of_the_contribution_carries_no_new_decisions():
    S.check_trial_pass_carries_no_new_decisions()


def test_decision_after_the_agm_sees_the_dividend_and_before_it_does_not():
    S.check_decision_after_the_agm_sees_the_dividend()


def test_dividend_decision_does_not_count_on_the_contribution():
    S.check_dividend_does_not_count_on_the_contribution()


def test_step_of_the_first_quarter_is_covered_by_the_fourth_quarter_contribution():
    S.check_step_of_the_first_quarter()


def test_shock_year_and_the_last_year_of_the_grid():
    S.check_shock_year_and_the_last_year()


def test_closed_quarter_of_a_contribution_outside_the_agm_quarter():
    S.check_closed_quarter_of_a_decision_outside_the_agm()


@tact
def test_window_floor_refuses_exactly_below_the_bound_and_only_when_enabled():
    S.check_window_floor()


@tact
def test_tie_rule_of_the_worst_point():
    S.check_tie_rule()


@tact
def test_points_of_the_invariant_are_a_part_of_its_definition():
    S.check_invariant_points()


def test_dividend_of_the_contribution_decision():
    S.check_dividend_of_the_decision()


def test_dps_carries_the_shares_of_the_divisor_adjustment():
    S.check_dps_with_the_divisor_adjustment()


@tact
def test_example_of_appendix_e_is_reproduced():
    S.check_example_q4()


@tact
def test_cell_norm_of_a_book_with_recapitalization():
    S.check_cell_norm()


def test_excess_return_years_row_carries_dilution_and_the_floor():
    S.check_excess_years_row()


@tact
def test_new_keys_of_the_second_pass_are_in_the_closed_schema():
    keys = set(KEYS)
    for key in ("capital.recapitalization.decision_quarter", "valuation.next_report.ni_target.multiplier",
                "valuation.next_report.ni_target.title"):
        assert key in keys, key


# ------------------------------------------------------------------ число клеток (М§3, §3.4)


@tact
def test_number_of_cells_is_the_product_of_the_lists_of_the_book():
    S.check_cells_by_the_lists_of_the_book()


@tact
def test_zero_probability_cell_is_checked_by_invariants_and_not_judged_by_gates():
    S.check_zero_probability_cell()


def test_release_of_a_book_with_four_scenarios_passes_the_contract():
    S.check_release_of_four_scenarios()


def test_release_of_a_book_with_step_payouts_by_year_is_built():
    S.check_release_with_step_payouts_by_year()


# ------------------------------------------------------------------ допуск сверки заголовка (П§0.3, §7 п. 5)


@tact
def test_headline_tolerance_over_all_half_kopeck_ties_from_1_to_700_roubles():
    S.check_headline_tolerance()


def test_headline_check_of_the_contract_holds_a_tie_on_the_32_64_level():
    S.check_headline_is_verified_with_the_tolerance()


# ------------------------------------------------------------------ база ожидания нау-каста (М§13)


def test_expectation_base_of_the_nowcast():
    S.check_ni_target()


# ------------------------------------------------------------------ сводка контрольной модели (М§17)


def test_control_summary_goes_to_the_release_only_for_its_own_book_and_facts():
    S.check_control_summary()


# Тест данных о сводке в дереве (М§17, §18) — один: `tests/test_control_model.py::
# test_checks_file_names_its_book_and_facts` (при отсутствии файла — пропуск с причиной; сводка без даты фактов —
# красный тест). Унаследованная сводка книги Т из дерева убрана в четвёртом проходе; тесты правила сводки строят свои
# сводки и от файла дерева не зависят.


# ------------------------------------------------------------------ оси полосы на общем пути (М§10)


@tact
def test_axes_on_a_common_path_add_up():
    S.check_axes_on_a_common_path_add_up()


@tact
def test_dict_axes_on_one_table_are_mixed_before_one_normalisation():
    S.check_dict_axes_on_one_table()


@tact
def test_single_axes_give_the_former_overrides_bit_for_bit():
    S.check_single_axes_are_the_former_overrides()


@tact
def test_schema_refuses_where_there_is_nothing_to_add():
    S.check_common_path_refusals()


def test_price_of_an_axis_on_a_common_path_is_taken_with_the_other_axis_on_the_book():
    S.check_price_of_an_axis_on_a_common_path()
