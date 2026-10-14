"""Четвёртый проход ядра — аналитические тесты (строки М§18 «печать, сверка и инструменты четвёртого прохода»):
узел числа гейта `capital.capital_gap` (М§3.4), разброс цены по осям сетки — правило образца и последовательное
(ключ `checks.grid_variance`, М§3.4, прил. A № 22), печать DPS при оборванных путях акций и делители строк, делитель
DPS нау-каста (М§6.6, §14.5), норма доли терминала при закрытом квартале взноса (М§6.4), гейт знака стресса и клетка
нулевой вероятности (М§3.4, §14.2), тройки клеток в контракте (П§7 п. 8), схема ключей доли вычета якоря (М§4.11,
прил. A № 21), ноль без знака (П§0.3), счётчики сводки контрольной модели (П§7 п. 15; М§17).

Проверки — `tests/support_core_pass4.py` (те же функции зовёт мутационный набор `tests/mutations.py`); пример —
приложение G методики (`tests/fixtures/core_pass4/example.json`). В такт сервера (метка `tact`) входит сжатый набор;
быстрые выпуски идут в CI.
"""

from __future__ import annotations

import pytest

from tests import support_core_pass4 as S

tact = pytest.mark.tact                  # быстрые тесты ядра на фикстуре — в такте сервера


# ------------------------------------------------------------------ узел числа гейта (М§3.4)


def test_capital_gap_node_counts_cells_like_the_gate():
    S.check_capital_gap_node_counts_like_the_gate()


# ------------------------------------------------------------------ разброс цены по осям сетки (М§3.4)


@tact
def test_example_g1_both_rules_of_the_spread():
    S.check_example_g1()


@tact
def test_sequential_rule_on_the_grid_and_the_independent_table():
    S.check_variance_rules_on_the_grid()


def test_variance_node_follows_the_key_of_the_book_and_the_contract_names_it():
    S.check_variance_node_by_the_key()


# ------------------------------------------------------------------ печать DPS и делители (М§6.6)


@tact
def test_example_g2_dps_rows_and_divisors():
    S.check_example_g2()


def test_dps_rows_with_broken_share_paths():
    S.check_dps_rows_with_broken_paths()


def test_dps_fields_only_with_recapitalization():
    S.check_dps_fields_only_with_recapitalization()


@tact
def test_policy_dps_denominator_carries_the_adjustment_and_contributions():
    S.check_policy_dps_denominator()


def test_nowcast_dps_is_on_the_divisor_of_the_policy_row():
    S.check_nowcast_divisor()


# ------------------------------------------------------------------ непойманные мутации второй проверки


@tact
def test_terminal_share_after_a_closed_contribution_quarter():
    S.check_terminal_share_after_a_closed_contribution()


def test_stress_sign_gate_skips_zero_probability_cells():
    S.check_stress_sign_and_zero_probability_cells()


def test_contract_checks_cell_triples_one_by_one():
    S.check_cell_triples_in_the_contract()


# ------------------------------------------------------------------ схема, печать, сводка


@tact
def test_schema_refuses_null_and_words_at_both_share_keys():
    S.check_schema_of_the_share_keys()


def test_zero_is_stored_without_sign():
    S.check_zero_without_sign()


@tact
def test_counters_of_the_control_summary():
    S.check_control_summary_counters()
