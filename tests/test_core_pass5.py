"""Пятый проход ядра — аналитические тесты (строки М§18 «Аналитические тесты пятого прохода»): вычет сценария в
рублях (`capital.reg_scenarios.<s>.deduction_rub`, М§4.11, прил. A № 23), путь постоянной части прочих активов
(`volumes.other_assets_fixed_change`, плотность приращения `capital.rwa.density.other_assets_fixed_change`, М§4.3,
прил. A № 8, № 24) и терминал с постоянными в рублях частями (`valuation.terminal.fixed_growth_share`, М§7, прил. A
№ 25).

Проверки — `tests/support_core_pass5.py` (те же функции зовёт мутационный набор `tests/mutations.py`); фикстуры —
формы образца `tests/fixtures/core`, докапитализации и формы Т с ключами, подставленными тестом; числовой пример —
приложение H методики (`tests/fixtures/core_pass5/example.json`). В такт сервера (метка `tact`) входит сжатый набор.
"""

from __future__ import annotations

import pytest

from model.book_schema import KEYS
from tests import support_core_pass5 as S

tact = pytest.mark.tact                  # быстрые тесты ядра на фикстуре — в такте сервера


# ------------------------------------------------------------------ без ключей и ключи-нули


@tact
def test_zero_keys_and_unit_share_are_the_book_without_keys_bit_for_bit():
    S.check_zero_keys_are_the_book_without_keys()


@tact
def test_new_keys_of_the_fifth_pass_are_in_the_closed_schema():
    keys = set(KEYS)
    for key in ("capital.reg_scenarios.<s>.deduction_rub.n20_0", "capital.reg_scenarios.<s>.deduction_rub.n1_1",
                "volumes.other_assets_fixed_change", "capital.rwa.density.other_assets_fixed_change",
                "valuation.terminal.fixed_growth_share"):
        assert key in keys, key


# ------------------------------------------------------------------ вычет сценария в рублях (М§4.11)


@tact
def test_deduction_row_carries_the_rubles_of_the_scenario():
    S.check_rub_deduction_is_the_formula()


def test_rubles_and_the_record_on_own_rwa_give_the_same_ratios():
    S.check_rub_equals_the_record_on_own_rwa()


def test_bridge_row_of_deductions_carries_the_change_of_rubles():
    S.check_bridge_row_of_deductions_carries_the_rubles()


@tact
def test_reanchor_with_the_trajectory_as_is_keeps_the_ratios():
    S.check_reanchor_keeps_the_ratios()


@tact
def test_schema_of_the_rubles():
    S.check_schema_of_the_rubles()


# ------------------------------------------------------------------ путь постоянной части прочих активов (М§4.3)


@tact
def test_other_assets_and_rwa_carry_the_change_of_the_fixed_part():
    S.check_fixed_change_rows()


def test_money_of_the_fixed_part_goes_to_the_balancing_items():
    S.check_fixed_change_money_goes_to_balancing()


@tact
def test_schema_of_the_fixed_change():
    S.check_schema_of_the_fixed_change()


def test_rubles_and_the_fixed_change_are_inputs_of_the_pass_and_the_share_is_not():
    S.check_fixed_change_is_an_input_of_the_pass()


# ------------------------------------------------------------------ терминал с постоянными частями (М§7)


def test_terminal_rows_of_the_block_of_fixed_parts():
    S.check_terminal_rows_of_the_block()


def test_ddm_equals_ri_at_any_share():
    S.check_ddm_equals_ri_at_any_share()


@tact
def test_value_without_fixed_parts_does_not_depend_on_the_share():
    S.check_no_fixed_parts_value_is_independent_of_the_share()


def test_asset_without_income_fixed_in_rubles_is_neutral_at_share_zero():
    S.check_neutral_asset()


def test_value_is_linear_in_the_share_and_the_price_is_the_sum_of_the_sides():
    S.check_linearity_and_sides()


@tact
def test_binding_ratio_wholesale_rate_and_refusal_of_the_block():
    S.check_binding_wholesale_and_refusal()


@tact
def test_schema_of_the_share():
    S.check_schema_of_the_share()


# ------------------------------------------------------------------ пример приложения H


@tact
def test_example_of_appendix_g_is_reproduced():
    S.check_example_g()
