"""Седьмой проход ядра — аналитические тесты (строка М§18 «Аналитические тесты седьмого прохода»): доля инструментов в
RWA своей клетки (`capital.n20.t2_share`, М§4.11, свойства 13–19, §4.14.1, §7, прил. A № 30).

Проверки — `tests/support_core_pass7.py` (те же функции зовёт мутационный набор `tests/mutations.py`, мутации
M500–M515); фикстуры — формы образца `tests/fixtures/core`, докапитализации и полной формы Т с траекторией и ключом,
подставленными тестом; числовой пример — приложение K методики (`tests/fixtures/core_pass7/example.json`). Перенос
якоря — `tests/test_reanchor_t2_share.py`.
"""

from __future__ import annotations

import pytest

from tests import support_core_pass7 as S

tact = pytest.mark.tact                  # быстрые тесты ядра на фикстуре — в такте сервера


# ------------------------------------------------------------------ без ключа и выключатель


@tact
def test_without_the_key_and_switched_off_the_sample_bit_for_bit():
    S.check_off_is_the_sample()


@tact
def test_anchor_row_does_not_depend_on_the_key():
    S.check_anchor_row_does_not_depend_on_the_key()


# ------------------------------------------------------------------ доля и путь (свойства 13, 14, 17)


@tact
def test_t2_holds_the_share_of_own_rwa_from_the_key_quarter():
    S.check_share_and_path()


# ------------------------------------------------------------------ тихая книга (свойства 15, 16, 18)


def test_on_the_quiet_book_only_k20_and_n20_move():
    S.check_quiet_book()


def test_record_on_one_cell_is_the_key_there_and_lower_where_rwa_grow_faster():
    S.check_record_on_one_cell()


def test_shift_of_the_trajectory_moves_the_share():
    S.check_shift_moves_the_share()


# ------------------------------------------------------------------ проходы


def test_dividend_trial_pass_carries_its_own_share():
    S.check_dividend_trial_carries_its_own_share()


def test_recap_trial_pass_and_the_second_order():
    S.check_recap_trial_and_second_order()


def test_growth_constraint_share_of_the_recorded_step():
    S.check_growth_constraint_share_of_the_recorded_step()


# ------------------------------------------------------------------ терминал, мост, схема, пример


def test_terminal_block_kappa_and_neutrality():
    S.check_terminal_block()
    S.check_neutral_asset_with_the_key()


def test_bridge_other_row_carries_the_change_of_t2():
    S.check_bridge_carries_the_change_of_t2()


@tact
def test_schema_of_the_share():
    S.check_schema_of_the_share()


@tact
def test_example_k():
    S.check_example_k()
