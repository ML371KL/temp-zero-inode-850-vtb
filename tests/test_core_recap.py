"""Докапитализация и пол стоимости клетки — аналитические тесты (М§4.14, §6.5–§6.6, §7, §8.2, §10, §14; §18).

Фикстура — форма образца `tests/fixtures/core` с подменами `tests/fixtures/core_recap/overrides.json` (годовой
календарь дивидендов, рост задан, капитала в части клеток не хватает и при нулевом дивиденде); общий числовой
пример — `tests/fixtures/core_recap/example.json` (приложение D методики). Проверки — тождества и закрытые
формулы, выведенные из книги, фактов и рядов клетки независимо от кода ядра (`tests/support_core_recap.py`; те
же проверки зовёт мутационный набор). Без своих ключей книги механики нет: расчёт прежний бит в бит.
В такт сервера (метка `tact`) входит сжатый набор — выключатель и схема, решение о взносе, шаг квартала, оценка,
пол и пример; остальное идёт в CI: краевые случаи решения, путь акций, гейт, хвост полосы и узлы таблиц и выпуска
(быстрые выпуски и таблицы книги на полосе — секунды, не доли секунды).
"""

from __future__ import annotations

import pytest

from model.book_schema import KEYS, SWITCHES
from model.capital import RECAP_RESIDUAL_SHARE, recap_rule
from model.checks import INVARIANTS, RECAP_INVARIANT, check_invariants
from model.grid import path_inputs, path_keys
from tests import support_core_recap as R
from tests.support_core import fixture_book, fixture_run

tact = pytest.mark.tact                  # быстрые тесты ядра на фикстуре — в такте сервера


# ------------------------------------------------------------------ выключатель и схема


@tact
def test_without_the_keys_the_calculation_is_the_sample_bit_for_bit():
    R.check_off_is_the_sample()


@tact
def test_schema_refuses_the_quarterly_calendar_the_growth_constraint_and_fields_out_of_bounds():
    R.check_schema_refusals()


@tact
def test_new_keys_are_in_the_closed_schema():
    keys = set(KEYS)
    for key in ("capital.recapitalization.enabled", "capital.recapitalization.price_discount",
                "capital.recapitalization.lookahead_quarters", "capital.recapitalization.min_amount",
                "capital.recapitalization.decision_quarter", "valuation.cell_floor"):
        assert key in keys, key
    assert set(SWITCHES["capital.recapitalization.enabled"]) == {
        f"capital.recapitalization.{k}" for k in ("price_discount", "lookahead_quarters", "min_amount",
                                                  "decision_quarter")}
    assert recap_rule(fixture_book()) is None and fixture_run().ctx.prep.recap is None
    rule = recap_rule(R.book_of())
    # без ключа квартал решения — квартал собрания, точки инварианта — до следующего собрания (М§4.14.1, §14.1)
    assert (rule.lookahead, rule.min_amount, rule.quarter, rule.span) == (3, 20.0, 2, 4)


def test_price_discount_and_cell_floor_are_not_inputs_of_the_cell_pass():
    """Дисконт размещения и пол клетки — параметры оценки и цены: отпечаток входов прохода клеток от них не
    зависит; окно решения и порог — входы прохода (М§4.14, §6.5)."""
    keys = lambda extra: path_keys(path_inputs(R.grid_of(extra).ctx))  # noqa: E731
    base = keys(None)
    assert keys({f"{R.RECAP}.price_discount": 0.25}) == base
    assert keys({R.FLOOR: 0.0}) == base
    assert keys({f"{R.RECAP}.lookahead_quarters": 2}) != base
    assert keys({f"{R.RECAP}.min_amount": 200.0}) != base
    assert keys({f"{R.RECAP}.decision_quarter": 4}) != base          # квартал решения — вход прохода клеток
    assert keys({f"{R.RECAP}.decision_quarter": 2}) == base          # ключ, равный кварталу собрания, — тот же проход
    assert keys({f"{R.RECAP}.enabled": False}) != base


@tact
def test_the_invariant_is_listed_only_for_a_book_with_recapitalization():
    assert RECAP_INVARIANT not in INVARIANTS and RECAP_RESIDUAL_SHARE == pytest.approx(0.1)
    assert RECAP_INVARIANT not in [f.name for f in check_invariants(fixture_run())]
    names = [f.name for f in check_invariants(R.grid_of())]
    assert names.index(RECAP_INVARIANT) == names.index("ddm_equals_ri") + 1
    assert [n for n in names if n != RECAP_INVARIANT] == list(INVARIANTS)


# ------------------------------------------------------------------ решение о взносе


@tact
def test_contribution_equals_the_shortfall_of_the_trial_pass():
    R.check_decision_is_the_trial_shortfall()


def test_declared_dividend_is_deducted_in_the_last_point_of_the_window_only():
    R.check_pending_dividend_in_the_last_point_only()


def test_requirement_step_inside_the_window_is_covered_before_the_step():
    R.check_step_of_the_next_year()


def test_shock_year_cancels_the_dividend_not_the_contribution_and_register_dividend_comes_first():
    R.check_shock_year_and_register()


def test_no_contribution_in_the_last_quarter_of_the_grid_and_the_window_is_cut_by_its_end():
    R.check_last_quarter_and_the_cut_window()


# ------------------------------------------------------------------ шаг квартала


@tact
def test_capital_identity_and_the_contribution_outside_comprehensive_income():
    R.check_step_with_the_contribution()


def test_binding_ratio_equals_the_requirement_and_the_residual_is_the_risk_weight_of_the_money():
    R.check_binding_ratio_and_the_residual()


# ------------------------------------------------------------------ оценка


@tact
def test_ddm_equals_ri_and_the_discount_never_raises_the_value():
    R.check_valuation_with_contributions()


def test_contribution_of_a_closed_quarter_is_taken_out_of_the_capital_at_the_valuation_date():
    R.check_closed_quarter()


# ------------------------------------------------------------------ пол клетки


@tact
def test_floor_is_applied_to_the_cell_before_the_mix_and_before_the_governance_discount():
    R.check_floor_is_by_the_cell()


def test_declared_dividend_is_outside_the_floor():
    R.check_floor_and_the_declared_dividend()


def test_band_tail_names_the_floor_and_the_contributions():
    R.check_band_tail()


# ------------------------------------------------------------------ путь акций, гейт, узлы, пример


def test_share_path_of_the_cell():
    R.check_share_path()


def test_capital_gap_gate_is_silent_where_the_contribution_closed_the_gap():
    R.check_capital_gap_gate()


def test_tables_and_release_carry_the_nodes_only_with_their_keys():
    R.check_nodes_only_with_keys(tables=True)


@tact
def test_example_of_appendix_d_is_reproduced():
    R.check_example()
