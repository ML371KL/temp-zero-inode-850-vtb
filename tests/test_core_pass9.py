"""Девятый проход ядра — аналитические тесты (строка М§18 «Аналитические тесты девятого прохода»): разрыв налога по
правилу (`tax.structure`, М§4.8, §7, свойства 32–38) и купон добавочного капитала якоря по ставке своего мира
(`capital.at1_coupon`, М§4.9, §7, свойства 39–43); схема — прил. A № 34–35.

Проверки — `tests/support_core_pass9.py` (те же функции зовёт мутационный набор `tests/mutations.py`, мутации с
M700); фикстуры — формы образца `tests/fixtures/core`, докапитализации и полной формы Т с ключами, подставленными
тестом; числовой пример — приложение M методики (`tests/fixtures/core_pass9/example.json`).
"""

from __future__ import annotations

import pytest

from tests import support_core_pass9 as S

tact = pytest.mark.tact                  # быстрые тесты ядра на фикстуре — в такте сервера


# ------------------------------------------------------------------ без ключей и выключатели


@tact
def test_without_the_keys_and_switched_off_the_sample_bit_for_bit():
    S.check_off_is_the_sample()


# ------------------------------------------------------------------ налог по правилу


@tact
def test_tax_of_every_quarter_is_the_rule_of_the_book():
    S.check_tax_rule()


def test_coupon_saving_and_other_differences_on_the_quiet_book():
    S.check_quiet_differences()


def test_dividend_bases_deduct_the_whole_coupon_under_the_rule_and_read_the_key_coupon():
    S.check_dividend_bases()


def test_bridge_profit_row_and_the_nowcast_coupon_of_the_year():
    S.check_bridge_and_nowcast()


# ------------------------------------------------------------------ купон якоря


@tact
def test_anchor_coupon_floats_with_the_key_rate_of_own_world():
    S.check_anchor_coupon()


# ------------------------------------------------------------------ терминал, схема, пример


def test_terminal_rows_under_the_rule_and_the_coupon_of_the_year_after_the_grid():
    S.check_terminal()


@tact
def test_schema_of_the_keys():
    S.check_schema()


@tact
def test_example_m():
    S.check_example_m()
