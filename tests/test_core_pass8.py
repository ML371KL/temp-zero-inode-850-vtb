"""Восьмой проход ядра — аналитические тесты (строка М§18 «Аналитические тесты восьмого прохода»): добавочный капитал
держит долю RWA своей клетки (`capital.at1_share`, М§4.9–§4.11, свойства 20–27), надбавка за субординацию
дополнительного капитала (`capital.n20.t2_premium`, М§4.4, §4.11, свойства 28–31), прочие движения капитала за концом
сетки (`valuation.terminal.other_movements`, М§7); схема — прил. A № 31–33.

Проверки — `tests/support_core_pass8.py` (те же функции зовёт мутационный набор `tests/mutations.py`, мутации с
M600); фикстуры — формы образца `tests/fixtures/core`, докапитализации и полной формы Т с ключами, подставленными
тестом; числовой пример — приложение L методики (`tests/fixtures/core_pass8/example.json`). Перенос якоря —
`tests/test_reanchor_pass8.py`.
"""

from __future__ import annotations

import pytest

from tests import support_core_pass8 as S

tact = pytest.mark.tact                  # быстрые тесты ядра на фикстуре — в такте сервера


# ------------------------------------------------------------------ без ключей и выключатели


@tact
def test_without_the_keys_and_switched_off_the_sample_bit_for_bit():
    S.check_off_is_the_sample()


@tact
def test_anchor_row_does_not_depend_on_the_keys():
    S.check_anchor_row_does_not_depend_on_the_keys()


# ------------------------------------------------------------------ доля AT1, неподвижная точка, купон


@tact
def test_at1_holds_the_share_of_own_rwa_from_the_key_quarter():
    S.check_share_and_path()


@tact
def test_fixed_point_of_rwa_and_the_balance_with_at1_on_the_liabilities():
    S.check_fixed_point_and_balance()


@tact
def test_coupon_of_new_issues_at_the_key_rate_of_own_world():
    S.check_coupon_rows()


def test_dividend_bases_carry_the_coupon_above_the_base():
    S.check_dividend_base_carries_the_new_coupon()
    S.check_quarter_base_carries_the_new_coupon()


def test_on_the_quiet_book_the_key_quarter_flows_are_the_book_without_the_key():
    S.check_quiet_book()


# ------------------------------------------------------------------ проходы


def test_dividend_trial_pass_carries_its_own_share():
    S.check_dividend_trial_carries_its_own_share()


def test_recap_trial_pass_and_the_second_order():
    S.check_recap_trial_and_second_order()


def test_growth_constraint_share_of_the_recorded_step():
    S.check_growth_constraint_share_of_the_recorded_step()


# ------------------------------------------------------------------ надбавка за субординацию


@tact
def test_premium_on_t2_above_the_base_in_interest_expense():
    S.check_premium_rows()


# ------------------------------------------------------------------ терминал, мост, схема, пример


def test_terminal_rows_kappa_and_ddm_equals_ri():
    S.check_terminal()


@tact
def test_other_movements_beyond_the_grid():
    S.check_other_movements()


def test_bridge_other_row_carries_the_change_of_at1():
    S.check_bridge_carries_the_change_of_at1()


@tact
def test_schema_of_the_keys():
    S.check_schema()


@tact
def test_example_l():
    S.check_example_l()
