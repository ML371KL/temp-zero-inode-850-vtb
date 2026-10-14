# -*- coding: utf-8 -*-
"""Шестой проход у инструмента перезаякоривания (`ops/tools/reanchor.py`; М§4.6, §4.7, §8.2, §15.2; REANCHOR §3.3,
§3.8, §3.9, §4, §6, §8; строки «Аналитические тесты шестого прохода» и «Мутации шестого прохода» М§18).

* **База объёма `iea` закрытого квартала** (М§4.7): клетка, перезаякоренная на своём пути, — A_0 кандидата равно ĪEA_1
  клетки прежней книги (точность записи фактов: относительная 1e-9) — у годового календаря без решения в квартале, у
  годового календаря в квартале собрания (решение отчёта — строка истории дивидендов с суммой всех категорий) и у
  квартального (решение клетки — с суммой, вычтенной из капитала); строка «механика» тех же клеток — в десятой доле
  допуска; цепочка «якорь 3К → якорь 4К» книги без взноса — все клетки в десятой доле допуска (`ci_only`). В квартале
  собрания годовой книги отчёт без решения при объявленном дивиденде — отказ.
* **Норма клетки** (М§15.2, прил. I.2): r_c = ΔV / max(|V|, BV_v − C_v); у клетки не ниже капитала — прежняя
  относительная разность бит в бит; вердикт и худшая клетка — по |r_c|.
* **Ряд значения моста** (М§4.6): ряд истории, чьё среднее по окну значения равно значению; форма Т — `gap_x4` ЧПМ и
  `gap` CoR (прежнее правило бит в бит); значение — среднее `gap` при наличии `gap_x4` — мост CoR на ожидаемом отчёте не
  меняется; медиана и «оба ряда» — прежнее правило с названным блоком.
* **Плотность постоянной части** (М§15.2 п. 3, прил. I.3): ω_oaf′ = (ω_oaf L + ω_Δ Δ_1) / (L + Δ_1) — RWA постоянной
  части прежние; частные случаи; концы осей; у клетки на своём пути RWA кандидата идут за прежними одним множителем.
* **Пол клетки с объявленным дивидендом** (М§8.2): строка цены на прежних стоимостях клеток — сам прогон при D_pend > 0.
* **Дрейф структуры нормировки** (REANCHOR §6): предупреждение при |w′ − ключ| > 0,01 и только тогда.

Мутации инструмента (`TOOL_MUTATIONS`) — правка исходного текста (`mutant_tool` файла `tests/test_reanchor_shares.py`):
каждую роняет проверка этого файла. Фикстура — форма образца `tests/fixtures/core` (связи и база `iea` — проверкой
`tests/support_core_pass6.py`) и форма Т `tests/fixtures/core_t`; даты — от периодов книги, не от «сегодня».
"""
from __future__ import annotations

import copy
import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from model.book import Facts, book_from_dict
from model.grid import DividendRecord, LiveInputs, make_context, run_grid
from tests import support_core_pass6 as S6
from tests import support_segment_cor as SG
from tests.support_core import fixture_book, fixture_dict, fixture_facts
from tests.test_reanchor import R
from tests.test_reanchor_shares import TOOL, mutant_tool

ROOT = Path(__file__).resolve().parents[1]
tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

EXAMPLE = json.loads((ROOT / "tests" / "fixtures" / "core_pass6" / "example.json").read_text(encoding="utf-8"))
CELLS = (("N", "norm", "schedule"), ("M", "crisis", "strict"))   # выше капитала и ниже его (фикстура)
BASE_REL = 1e-9          # A_0 кандидата к ĪEA_1: относительная точность записи фактов (книги — шесть знаков)
EX_TOL = 1e-9            # пример приложения I
TENTH = R.MECHANICS_TOL / 10
FLOOR = 6000.0           # млрд ₽: пол клетки фикстуры — часть клеток на полу
PRICE_TOL = 1e-9
SPREAD = 1e-5            # RWA кандидата / RWA прежней книги по кварталам: разброс — остаток записи плотностей шестью
#                          знаками (≈ 3e-6); без переноса плотности постоянной части — 1,5e-4
ANCHOR_RWA = 1e-6        # то же в квартале нового якоря: якорь откалиброван к RWA отчёта
FIXED_DENSITY, CHANGE_DENSITY = "capital.rwa.density.other_assets_fixed", "capital.rwa.density.other_assets_fixed_change"
LEVEL, CHANGE = "volumes.other_assets_fixed", "volumes.other_assets_fixed_change"


def scene_of(tool: Any, book: Any, facts: Any) -> SimpleNamespace:
    """Сухой прогон инструментом `tool`: прежняя книга с ожидаемым наблюдением, база сравнения, ожидаемый отчёт."""
    v = tool.period_end(str(book.get("meta.first_period"))) + timedelta(days=2)
    live = tool.live_at(book, facts, v)
    plus, run_plus, obs = tool.expected_run(book, facts, live)
    return SimpleNamespace(book=book, facts=facts, v=v, run_plus=run_plus, obs=obs,
                           hist=tool.history_run(book, run_plus),
                           expected=tool.expected_report(book, facts, run=run_plus))


def own_path(tool: Any, s: SimpleNamespace, key: tuple, report: dict | None = None) -> SimpleNamespace:
    """Клетка `key`, перезаякоренная на своём пути: кандидат и A_0 его базы объёма против ĪEA_1 прежней клетки."""
    report = tool._cell_report(s.run_plus, {key: 1.0}) if report is None else report
    cand = tool.reanchor(s.book, s.facts, report, valuation_date=s.v, cell=key, base_run=s.hist, observation=s.obs)
    old = s.run_plus.cell(*key)
    return SimpleNamespace(cand=cand, report=report, old=old, a0=make_context(cand.book, cand.facts).prep.hist_vol[0],
                           iea1=float(old.quarters["iea_avg"][1]))


# ------------------------------------------------------------------ база объёма iea закрытого квартала (М§4.7)


@lru_cache(maxsize=None)
def iea_scene() -> SimpleNamespace:
    return scene_of(R, S6.link_book("iea"), S6.base_facts())


def agm_facts() -> Facts:
    """Факты проверки без объявленного на якоре дивиденда (сумма к выплате — в прочих обязательствах): у книги с
    собранием в третьем квартале решение за 2025 год принимают клетки в квартале 2026К3 — закрываемом."""
    return S6.facts_with(agm_facts_change)


def agm_facts_change(files: dict) -> None:
    bal = files["balance"]
    bal.pop("dividends_payable_year", None)
    bal["other_liabilities"]["v"] = float(bal["other_liabilities"]["v"]) + float(bal["dividends_payable"]["v"])
    bal["dividends_payable"]["v"] = 0.0


def agm_book(facts: Facts, base: str = "iea") -> Any:
    data = copy.deepcopy(fixture_dict())
    data["fees"]["volume_link"] = S6.LINK
    data["opex"]["volume_link"] = S6.LINK
    data["volumes"]["link_base"] = base
    data["dividends"]["calendar"].update(agm_quarter=3, reg_deduction_quarter=4, payment_quarter=4, checkpoints=[4])
    return book_from_dict(data, facts=facts)


@lru_cache(maxsize=None)
def agm_scene() -> SimpleNamespace:
    facts = agm_facts()
    return scene_of(R, agm_book(facts), facts)


def t_iea_scene_of(tool: Any) -> SimpleNamespace:
    """Форма Т (квартальный календарь, рост по капиталу без навёрстывания) со связями и базой `iea`: в закрываемом
    квартале 2026К3 — решение записи реестра за 2026К1."""
    from tests.support_core_t import put, t_dict, t_facts

    data = t_dict()
    put(data, "capital.growth_constraint.catch_up_rate", 0.0)
    for path, value in (("fees.volume_link", S6.LINK), ("opex.volume_link", S6.LINK), ("volumes.link_base", "iea")):
        put(data, path, value)
    return scene_of(tool, book_from_dict(data, facts=t_facts()), t_facts())


def check_closed_quarter_base(tool: Any) -> None:
    """Годовой календарь, квартал без решения: A_0 кандидата = ĪEA_1 клетки прежней книги, база прежних кварталов
    фактов кандидата — база прежней книги, сдвинутая на квартал; строка «механика» клеток — в десятой доле допуска."""
    s = iea_scene() if tool is R else scene_of(tool, S6.link_book("iea"), S6.base_facts())
    was = s.run_plus.ctx.prep.hist_vol
    for key in CELLS:
        c = own_path(tool, s, key)
        assert abs(c.a0 / c.iea1 - 1) <= BASE_REL, (key, c.a0, c.iea1)
        now = make_context(c.cand.book, c.cand.facts).prep.hist_vol
        for x in (-3, -2, -1):
            assert abs(now[x] / was[x + 1] - 1) <= BASE_REL, (key, x, now[x], was[x + 1])
    mech = tool.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=CELLS)
    assert mech["ok"] and abs(mech["worst"]["r"]) <= TENTH, mech["worst"]


def check_annual_decision_rows(tool: Any) -> None:
    """Годовой календарь в квартале собрания (REANCHOR §3.9): ожидаемый отчёт несёт решение клеток с суммой, вычтенной
    из капитала (`pool_all_classes` — Div клетки), перенос пишет его строкой истории дивидендов, и A_0 кандидата =
    ĪEA_1 клетки (Div_0 ≠ 0). Без связи с объёмом раздел не пишется."""
    s = agm_scene() if tool is R else scene_of(tool, agm_book(agm_facts()), agm_facts())
    (row,) = s.expected["dividend_decisions"]
    w = {k: p for k, p in tool._weights(s.run_plus, None).items() if p}
    total = sum(w.values())
    div = sum(p * s.run_plus.cell(*k).quarters["div"][1] for k, p in w.items()) / total
    assert row["period"] == "2025Q4" and row["decided_date"] == "2026-09-30"
    assert "pool_all_classes" in row and abs(row["pool_all_classes"] - div) <= 1e-6 and div > 100.0, (row, div)
    for key in CELLS:
        c = own_path(tool, s, key)
        div1 = float(c.old.quarters["div"][1])
        hist = [r for r in c.cand.facts.file("dividends")["history"] if r.get("decided_date") == "2026-09-30"]
        assert len(hist) == 1 and abs(hist[0]["pool_all_classes"]["v"] - div1) <= 1e-8, hist
        assert abs(c.a0 / c.iea1 - 1) <= BASE_REL, (key, c.a0, c.iea1, div1)
    mech = tool.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=CELLS)
    assert mech["ok"] and abs(mech["worst"]["r"]) <= TENTH, mech["worst"]
    plain = scene_of(tool, agm_book(agm_facts(), "loans").with_overrides(
        {"fees.volume_link": 0.0, "opex.volume_link": 0.0}), agm_facts())
    assert "dividend_decisions" not in plain.expected


def check_annual_refusal(tool: Any) -> None:
    """В квартале собрания годовой книги с базой `iea` отчёт без решения при объявленном дивиденде — отказ; строка
    истории с днём решения в квартале, раздел решений, сумма к выплате ноль или квартал не собрания — не отказ."""
    s = agm_scene()
    bare = copy.deepcopy(s.expected)
    bare.pop("dividend_decisions")
    assert bare["balance"]["dividends_payable_year"] == 2025 and bare["balance"]["dividends_payable"] > 0
    with pytest.raises(tool.ReportError, match="решение собрания не названо"):
        tool.check_report(s.book, s.facts, bare)
    tool.check_report(s.book, s.facts, s.expected)                     # с решением — принят
    dated = S6.facts_with(lambda f: (agm_facts_change(f), f["dividends"]["history_before"].append(
        {"year": 2025, "period": "2025Q4", "decided_date": "2026-08-15", "pool_all_classes": {"v": 1.0}})))
    tool._check_annual_decisions(agm_book(dated), dated, bare)        # решение уже в истории фактов
    zero = copy.deepcopy(bare)
    zero["balance"]["dividends_payable"] = 0.0
    tool._check_annual_decisions(s.book, s.facts, zero)
    other = agm_book(agm_facts()).with_overrides({"dividends.calendar.agm_quarter": 2,
                                                   "dividends.calendar.reg_deduction_quarter": 3,
                                                   "dividends.calendar.payment_quarter": 3,
                                                   "dividends.calendar.checkpoints": [3, 4]})
    tool._check_annual_decisions(other, s.facts, bare)


def check_quarterly_decision_sum(tool: Any) -> None:
    """Квартальный календарь (форма Т) с базой `iea`: решение клетки закрываемого квартала несёт сумму, вычтенную из
    капитала (`pool_all_classes` = Div клетки, а не DPS × размещённые), и A_0 кандидата = ĪEA_1."""
    s = t_iea_scene_of(tool)
    key = ("N", "soft", "schedule")
    c = own_path(tool, s, key)
    (dec,) = c.report["dividend_decisions"]
    div1 = float(c.old.quarters["div"][1])
    assert "pool_all_classes" in dec and abs(dec["pool_all_classes"] - div1) <= 1e-8 and div1 > 0, (dec, div1)
    assert abs(c.a0 / c.iea1 - 1) <= BASE_REL, (c.a0, c.iea1)


@tact
def test_the_closed_quarter_keeps_the_cell_base_of_volume():
    check_closed_quarter_base(R)


@tact
def test_the_decision_of_the_meeting_of_an_annual_book_becomes_a_history_row():
    check_annual_decision_rows(R)


@tact
def test_an_annual_book_without_the_decision_of_the_meeting_is_refused():
    check_annual_refusal(R)


@tact
def test_the_decision_of_a_quarterly_book_carries_the_sum_deducted_from_equity():
    check_quarterly_decision_sum(R)


@ci_only
def test_the_chain_third_to_fourth_quarter_of_a_book_without_contributions():
    """Цепочка «якорь 3К → якорь 4К» книги без взноса (М§15.2, REANCHOR §8): кандидат шага 3К на ожидаемом отчёте
    слоя, его ожидаемый отчёт и перенос — все клетки сетки на обоих шагах в десятой доле допуска по норме клетки (без
    правила базы М§4.7 худшая клетка — +0,033 % / +0,041 % нормы, с ним — около +0,001 %)."""
    s = iea_scene()
    first = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v)
    assert len(first["rows"]) == len(s.run_plus.cells) and abs(first["worst"]["r"]) <= TENTH, first["worst"]
    cand = R.reanchor(s.book, s.facts, s.expected, valuation_date=s.v, base_run=s.run_plus)
    s2 = scene_of(R, cand.book, cand.facts)
    assert str(s2.book.get("meta.first_period")) == "2026Q4"
    second = R.cell_mechanics(s2.book, s2.facts, s2.run_plus, s2.obs, s2.v)
    assert abs(second["worst"]["r"]) <= TENTH, second["worst"]
    step = float(s.book.get("valuation.headline.print_step"))
    for mech, sc in ((first, s), (second, s2)):
        assert abs(mech["headline"]["point"] - sc.run_plus.point) <= 0.01 * step


# ------------------------------------------------------------------ норма клетки (М§15.2, прил. I.2)


def check_norm_cases(tool: Any) -> None:
    """Пример I.2 функциями вердикта инструмента (до 1e-9): норма, r_c, разность к V_c; у клетки выше капитала r_c —
    прежняя относительная разность бит в бит; сетки a–d — в допуске по норме (прежний вердикт — вне), с e или f — вне."""
    ex = EXAMPLE["mechanics_norm"]
    rows = {}
    for c in ex["cells"]:
        row = tool.mechanics_row(c["v_base"], c["v_own_path"], c["bv_v"], c["c_v"])
        assert abs(row["norm"] - c["norm"]) <= EX_TOL and abs(row["r"] - c["r"]) <= EX_TOL, (c["cell"], row)
        assert abs(row["rel"] - c["rel_to_v"]) <= EX_TOL and abs(row["dv"] - c["dv"]) <= EX_TOL, c["cell"]
        assert (abs(row["r"]) <= ex["tolerance"]) is c["ok"], c["cell"]
        rows[c["cell"]] = {**row, "cell": c["cell"]}
    a = rows["a"]
    assert a["r"] == a["rel"] and a["norm"] == 1700.0                  # выше капитала — прежняя мера бит в бит
    assert rows["d"]["rel"] < 0 < rows["d"]["r"]                        # знак разности к отрицательной V меняется
    for v in ex["verdicts"]:
        worst, ok = tool.mechanics_verdict([rows[x] for x in v["cells"]])
        assert worst["cell"] == v["worst"] and ok is v["ok"], v


@tact
def test_the_cell_norm_of_the_mechanics_line():
    check_norm_cases(R)


@tact
def test_cells_above_capital_keep_the_old_measure_in_the_mechanics_line():
    """На прогоне (фикстура со связями): у клетки, чья стоимость не ниже капитала, r_c — прежняя относительная разность
    бит в бит; у клетки ниже капитала |r_c| меньше; худшая — по |r_c|."""
    s = iea_scene()
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=CELLS)
    above, below = mech["rows"]
    assert abs(above["base"]) >= above["bv_v"] and above["r"] == above["rel"] and above["norm"] == abs(above["base"])
    assert abs(below["base"]) < below["bv_v"] and below["norm"] == below["bv_v"] and abs(below["r"]) < abs(below["rel"])
    assert mech["worst"] is max(mech["rows"], key=lambda r: abs(r["r"]))


# ------------------------------------------------------------------ ряд значения моста (М§4.6, REANCHOR §3.8)


def _n(v: Any) -> dict:
    return {"v": v, "calc": "проверка шестого прохода: ряд истории моста"}


def _rows(periods: list[str], gaps: list[float], ripple: float | None) -> list[dict]:
    out = []
    for i, (p, g) in enumerate(zip(periods, gaps)):
        row = {"period": p, "mgmt": _n(0.02), "engine": _n(0.02 + g), "gap": _n(g)}
        if ripple is not None:
            row["gap_x4"] = _n(g + ripple * (1 if i % 2 else -2))
        out.append(row)
    return out


PERIODS = ["2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"]
GAPS = [0.0010, 0.0016, 0.0013, 0.0019, 0.0027]   # среднее 0,0017, медиана 0,0016


def check_value_series(tool: Any) -> None:
    """Выбор ряда (`value_series`): форма Т — ЧПМ `gap_x4` (своё окно года якоря), CoR без `gap_x4` — `gap`; форма этой
    панели — среднее `gap` при наличии `gap_x4` — `gap`; значение-медиана и оба ряда равны — прежнее правило словами."""
    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
    x4 = _rows(PERIODS, GAPS, 3e-5)
    t_nim = {"value": {"v": mean([r["gap_x4"]["v"] for r in x4[3:]])}, "window": ["2026Q1", "2026Q2"], "history": x4}
    assert tool.value_series(t_nim, t_nim["window"])[0] == "gap_x4"
    t_cor = {"value": {"v": mean(GAPS)}, "history": _rows(PERIODS, GAPS, None)}
    assert tool.value_series(t_cor, ["2025Q2", "2026Q2"])[0] == "gap"
    vtb = {"value": {"v": mean(GAPS)}, "history": x4}
    series, rule = tool.value_series(vtb, ["2025Q2", "2026Q2"])
    assert series == "gap" and "ряд значения" in rule, rule
    median = {"value": {"v": sorted(GAPS)[2]}, "history": x4}
    series, rule = tool.value_series(median, ["2025Q2", "2026Q2"])
    assert series == "gap_x4" and "прежнее правило" in rule and "ни один" in rule, rule
    both = {"value": {"v": mean(GAPS)}, "history": _rows(PERIODS, GAPS, 0.0)}
    series, rule = tool.value_series(both, ["2025Q2", "2026Q2"])
    assert series == "gap_x4" and "оба" in rule, rule


def _bridge_facts(form: str) -> Facts:
    """Факты фикстуры проверки со своим мостом: `vtb` — значение CoR и ЧПМ — среднее `gap` при наличии `gap_x4`;
    `t` — ЧПМ — среднее `gap_x4` по окну года якоря, CoR — среднее `gap` без `gap_x4`."""
    def change(files: dict) -> None:
        br = files["bridge_mgmt_ifrs"]
        br["window"] = ["2025Q2", "2026Q2"]
        for x, base in (("cor", 0.0017), ("nim", -0.0041)):
            gaps = [base + g - 0.0016 for g in GAPS]
            block = br[x]
            if form == "t" and x == "nim":
                rows = _rows(PERIODS, gaps, 3e-5)
                block.update(history=rows, window=["2026Q1", "2026Q2"], n=_n(2),
                             value=_n(sum(r["gap_x4"]["v"] for r in rows[3:]) / 2))
            else:
                rows = _rows(PERIODS, gaps, None if form == "t" else 3e-5)
                block.update(history=rows, n=_n(5), value=_n(sum(gaps) / 5))
                block.pop("window", None)
    return S6.facts_with(change)


def check_bridge_carry(tool: Any) -> None:
    """Перенос моста (`facts_after`) на отчёте клетки на своём пути с продлением среднего: у фактов этой панели мост CoR
    не меняется (до 1e-9: `gap` квартала — сам мост), ряд — `gap`; у формы Т ЧПМ продлевается уровнем `gap_x4`, CoR —
    `gap` — то же, что прежнее правило, бит в бит; ряд и правило названы по блокам."""
    for form in ("vtb", "t"):
        facts = _bridge_facts(form)
        book = S6.link_book("iea", facts)
        s = scene_of(tool, book, facts)
        report = tool._cell_report(s.run_plus, {CELLS[0]: 1.0})
        notes: dict = {}
        new = tool.facts_after(book, facts, report, update_bridge=True, series_notes=notes)
        old_br, new_br = facts.file("bridge_mgmt_ifrs"), new.file("bridge_mgmt_ifrs")
        eng = tool.engine_ratios(book, facts, report)
        days = eng["days"]
        for x in ("cor", "nim"):
            n = int(old_br[x]["n"]["v"])
            gap = eng[x] - report["mgmt"][x]
            x4 = eng[x] * 4 * days / 365 - report["mgmt"][x]
            if form == "vtb":
                assert notes[x]["series"] == "gap", (x, notes[x])
                assert new_br[x]["value"]["v"] == round((old_br[x]["value"]["v"] * n + gap) / (n + 1), 9), x
            else:
                old_rule = x4 if any("gap_x4" in r for r in old_br[x]["history"]) else gap
                assert notes[x]["series"] == ("gap_x4" if x == "nim" else "gap"), (x, notes[x])
                assert new_br[x]["value"]["v"] == round((old_br[x]["value"]["v"] * n + old_rule) / (n + 1), 9), x
        if form == "vtb":
            assert abs(new_br["cor"]["value"]["v"] - old_br["cor"]["value"]["v"]) <= 1e-9


@tact
def test_the_value_series_of_the_bridge():
    check_value_series(R)


@tact
def test_the_bridge_is_carried_in_its_value_series():
    check_bridge_carry(R)


# ------------------------------------------------------------------ плотность постоянной части (М§15.2 п. 3, прил. I.3)


def _get(tree: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        tree = tree[part]
    return tree


def _put(tree: dict, dotted: str, value: Any) -> None:
    *head, last = dotted.split(".")
    for part in head:
        tree = tree.setdefault(part, {})
    tree[last] = copy.deepcopy(value)


def _i3_book(level: float, path: dict, w_fixed: float | None, w_change: float | None) -> dict:
    X = copy.deepcopy(fixture_dict())
    _put(X, LEVEL, level)
    _put(X, CHANGE, path)
    dens = X["capital"]["rwa"]["density"]
    dens.pop("other_assets_fixed", None)
    if w_fixed is not None:
        dens["other_assets_fixed"] = w_fixed
    if w_change is not None:
        dens["other_assets_fixed_change"] = w_change
    X["valuation"]["uncertainty"]["axes"] += [
        {"name": "плотность постоянной части", "kind": "value", "paths": [FIXED_DENSITY], "low": 0.4, "high": 0.6,
         "dist": "triangular"},
        {"name": "плотность приращения", "kind": "value", "paths": [CHANGE_DENSITY], "low": 0.0, "high": 0.3,
         "dist": "triangular"}]
    return X


def _fixed_rwa(X: dict, anchor: str, year: int) -> float:
    """RWA постоянной части года по книге-словарю (М§4.11): ω_oaf × число + ω_Δ × (путь(год) − путь(якорь))."""
    from model.paths import Trajectory

    dens = X["capital"]["rwa"]["density"]
    t = Trajectory(_get(X, CHANGE))
    w_change = dens.get("other_assets_fixed_change", dens.get("other_assets_fixed"))
    delta = t.value(year, 4) - t.value(int(anchor[:4]), int(anchor[-1]))
    return dens["other_assets_fixed"] * float(_get(X, LEVEL)) + w_change * delta


def _carry(tool: Any, X: dict, anchor: str, period: str) -> tuple[dict, list[str]]:
    derived, warnings = {}, []
    tool.carry_fixed_change(X, anchor, period, {"balance": {}}, derived, warnings)
    tool.carry_fixed_density(X, derived, warnings)
    return derived, warnings


def check_density_example(tool: Any) -> None:
    """Пример I.3 и частные случаи (до 1e-9): ω_oaf′ = 0,625, RWA постоянной части 2029 и 2030 годов — 50, как у
    прежней книги (с прежней плотностью — 40); с ω_Δ = 0,2 — та же сохранность RWA; без ключа ω_Δ и при Δ_1 = 0 —
    прежняя плотность; L = 0 — ω_Δ; L + Δ_1 = 0 — прежняя; конец оси на ω_oaf — той же формулой; ось на ω_Δ —
    предупреждение."""
    ex = EXAMPLE["fixed_part_density"]
    inp = ex["inputs"]
    g2 = json.loads((ROOT / "tests" / "fixtures" / "core_pass5" / "example.json").read_text(encoding="utf-8"))["fixed_change"]
    anchor, period = g2["inputs"]["anchor"], g2["reanchor"]["new_anchor"]
    path = {str(k): float(v) for k, v in g2["inputs"]["path"].items()}
    for w_change in (inp["omega_delta"], 0.2):
        X = _i3_book(inp["other_assets_fixed"], path, inp["omega_oaf"], w_change)
        before = copy.deepcopy(X)
        derived, warnings = _carry(tool, X, anchor, period)
        want = (inp["omega_oaf"] * inp["other_assets_fixed"] + w_change * inp["delta_1"]) / ex["other_assets_fixed_new"]
        got = X["capital"]["rwa"]["density"]["other_assets_fixed"]
        assert abs(got - want) <= EX_TOL and derived["fixed_change"]["density"]["now"] == got, (w_change, got)
        if w_change == inp["omega_delta"]:
            assert abs(got - ex["omega_oaf_new"]) <= EX_TOL
        for year, rwa in ex["rwa_fixed"].items():
            new, old = _fixed_rwa(X, period, int(year)), _fixed_rwa(before, anchor, int(year))
            assert abs(new - old) <= EX_TOL, (w_change, year, new, old)
            if w_change == inp["omega_delta"]:
                assert abs(new - rwa["new_book"]) <= EX_TOL and abs(old - rwa["old_book"]) <= EX_TOL
        axis = next(a for a in X["valuation"]["uncertainty"]["axes"] if a["paths"] == [FIXED_DENSITY])
        for end, value in (("low", 0.4), ("high", 0.6)):
            moved = (value * inp["other_assets_fixed"] + w_change * inp["delta_1"]) / ex["other_assets_fixed_new"]
            assert abs(axis[end] - moved) <= EX_TOL, (end, axis[end], moved)
        assert any(CHANGE_DENSITY in w for w in warnings), warnings
        assert tool.fixed_change_line(derived) and "ω_oaf′" in tool.fixed_change_line(derived)
    # без ключа ω_Δ — прежняя плотность
    X = _i3_book(inp["other_assets_fixed"], path, inp["omega_oaf"], None)
    _carry(tool, X, anchor, period)
    assert X["capital"]["rwa"]["density"]["other_assets_fixed"] == ex["special"]["no_delta_density_key"]
    # Δ_1 = 0 — книга не меняется
    X = _i3_book(inp["other_assets_fixed"], {"2028": 0.0, "2029": 0.0, "2030": -40.0}, inp["omega_oaf"], 0.2)
    same = copy.deepcopy(X)
    _carry(tool, X, anchor, period)
    assert X == same
    # L = 0 — плотность приращения; плотности постоянной части у прежней книги не было
    X = _i3_book(0.0, {"2028": 0.0, "2029": 30.0, "2030": 30.0}, None, inp["omega_delta"])
    _, warnings = _carry(tool, X, anchor, period)
    assert X["capital"]["rwa"]["density"]["other_assets_fixed"] == ex["special"]["from_zero"]
    assert any("создана путём" in w for w in warnings)
    # L + Δ_1 = 0 — постоянной части нет: плотность прежняя
    X = _i3_book(20.0, {"2028": 0.0, "2029": -20.0, "2030": -20.0}, inp["omega_oaf"], 0.2)
    _carry(tool, X, anchor, period)
    assert X["capital"]["rwa"]["density"]["other_assets_fixed"] == inp["omega_oaf"]


def _fixed_scene() -> Any:
    from tests.test_reanchor_fixed_change import _book
    from tests.test_reanchor_shares import _scene

    return _scene(_book(False), fixture_facts())


def check_density_on_the_own_path(tool: Any) -> None:
    """Клетка на своём пути у книги с путём постоянной части (Δ_1 = −30, ω_oaf 0,6, ω_Δ 0): RWA кандидата в каждом
    квартале — RWA прежней клетки следующего квартала одним множителем (разброс — запись плотностей шестью знаками), в
    квартале нового якоря — RWA отчёта."""
    from tests.test_reanchor_shares import _carried

    s = _fixed_scene()
    for key in (("N", "soft", "schedule"), ("M", "crisis", "strict")):
        c = _carried(tool, key, s=s)
        ratios = [c.cell.quarters["rwa"][q] / c.old.quarters["rwa"][q + 1] for q in range(c.run.ctx.timeline.Q)]
        assert abs(ratios[0] - 1) <= ANCHOR_RWA, (key, ratios[0])
        assert max(ratios) - min(ratios) <= SPREAD, (key, max(ratios) - min(ratios))
        dens = c.cand.derived["fixed_change"]["density"]
        assert dens["was"] == 0.6 and abs(dens["now"] - 0.6 * 1200 / 1170) <= 1e-12, dens


@tact
def test_the_density_of_the_fixed_part_moves_with_its_number():
    check_density_example(R)


@tact
def test_rwa_of_a_cell_on_its_own_path_follow_the_old_book():
    check_density_on_the_own_path(R)


# ------------------------------------------------------------------ пол клетки с объявленным дивидендом (М§8.2)


def check_floor_with_a_pending_dividend(tool: Any) -> None:
    """У книги с полом клетки и объявленным дивидендом прогона (D_pend > 0: запись реестра за 2026 год, решение — в
    квартале собрания 2027 года, экс-дата позже даты оценки) строка цены инструмента на прежних стоимостях клеток — сам
    прогон: низ, точка, верх и V0 слоёв."""
    book = fixture_book().with_overrides({"valuation.cell_floor": FLOOR}, create=True)
    v = date.fromisoformat(str(book.get("meta.valuation_date")))
    prices = {str(t): float(p) for t, p in book.get("meta.market_price").items()}
    rec = DividendRecord(year=2026, dps=20.0, status="declared", record_date=v + timedelta(days=30),
                         last_buy_date=v + timedelta(days=28), ex_date=v + timedelta(days=29),
                         pay_date=v + timedelta(days=40), sources=("manual",))
    run = run_grid(book, fixture_facts(), LiveInputs(valuation_date=v, prices=prices,
                                                     price_dates={t: v for t in prices}, register=(rec,)))
    assert run.pending_dividend > 0 and run.cell_floor == FLOOR, run.pending_dividend
    floored = [c for c in run.cells if c.v_ri - run.pending_dividend < FLOOR]
    assert len(floored) >= 3, len(floored)
    got = tool._priced(run, {c.key: c.v_ri for c in run.cells})
    for name in ("low", "point", "high"):
        assert got[name] == pytest.approx(getattr(run, name), abs=PRICE_TOL), name
    for name, layer in run.layers.items():
        assert got["v0"][name] == pytest.approx(layer.v0, abs=PRICE_TOL), name


@tact
def test_the_price_line_with_a_floor_and_a_pending_dividend_is_the_run_itself():
    check_floor_with_a_pending_dividend(R)


# ------------------------------------------------------------------ дрейф структуры нормировки (REANCHOR §6)


def check_drift_warning(tool: Any) -> None:
    """Предупреждение о дрейфе — при |доля юрлиц нового якоря − ключ| > 0,01 (ключ 0,4 против доли ≈ 0,58): обе доли и
    отношение общей CoR к пути; без ключа (ключ — доля прежнего якоря, сдвиг за квартал ≈ 0,1 п.п.) — нет."""
    for share, warned in ((SG.SHARE, True), (None, False)):
        s = scene_of(tool, SG.seg_book(share), fixture_facts())
        cand = tool.reanchor(s.book, s.facts, s.expected, valuation_date=s.v, base_run=s.run_plus)
        mix = cand.derived["segment_mix"]
        notes = [w for w in cand.warnings if w.startswith("структура нормировки сегментной CoR")]
        assert bool(notes) is warned, (share, mix, notes)
        if warned:
            rel = SG.REL
            ratio = ((mix["new_anchor"] * rel["corporate"] + (1 - mix["new_anchor"]) * rel["retail"])
                     / (share * rel["corporate"] + (1 - share) * rel["retail"]))
            assert abs(mix["ratio"] - ratio) <= 1e-12
            assert f"{mix['new_anchor']:.6f}" in notes[0] and f"{share:.6f}" in notes[0] and f"{ratio:.4f}" in notes[0]
        else:
            assert abs(mix["new_anchor"] - mix["share"]) <= tool.SEGMENT_DRIFT


@tact
def test_the_drift_of_the_normalisation_structure_is_named():
    check_drift_warning(R)


# ------------------------------------------------------------------ мутации инструмента (М§18)

DENSITY_CALL = ("    carry_fixed_density(X, derived, warnings, level_value=float(oaf_facts) if _num(oaf_facts) else None)\n"
                "\n    # --- капитал: вычеты формулой книги, плотности RWA — общим множителем к RWA якоря\n")
CALIBRATE = ("    calibrate_capital(X, new_facts, float(report[\"capital\"][\"basel_rwa\"]), derived, warnings,\n"
             "                      numbers=\"estimated_levels\" in derived, old=book)\n")
TOOL_MUTATIONS: tuple[tuple[str, str, str, str, Callable[[Any], None]], ...] = (
    ("T61", "норма клетки механики — |V| без пола капиталом",
     "    norm = cell_norm(v_base, bv_v - c_v)\n", "    norm = abs(v_base)\n", check_norm_cases),
    ("T62", "пол нормы — BV_v без вычета C_v",
     "    norm = cell_norm(v_base, bv_v - c_v)\n", "    norm = cell_norm(v_base, bv_v)\n", check_norm_cases),
    ("T63", "вердикт и худшая клетка — по относительной разности к V",
     '    worst = max(rows, key=lambda r: abs(r["r"]))\n    return worst, abs(worst["r"]) <= MECHANICS_TOL\n',
     '    worst = max(rows, key=lambda r: abs(r["rel"]))\n    return worst, abs(worst["rel"]) <= MECHANICS_TOL\n',
     check_norm_cases),
    ("T64", "ряд значения моста — всегда gap_x4 при его наличии (прежнее правило)",
     "    if len(fit) == 1:\n", "    if False:\n", check_value_series),
    ("T65", "ряд значения выбран по медиане окна",
     "        mean = sum(float(v) for v in vals) / len(vals)\n",
     "        mean = sorted(float(v) for v in vals)[len(vals) // 2]\n", check_value_series),
    ("T66", "плотность постоянной части не переносится (прежняя ω_oaf)",
     '    dens["other_assets_fixed"] = now\n', '    dens["other_assets_fixed"] = w_fixed\n', check_density_example),
    ("T67", "ω_oaf′ без веса приращения Δ_1",
     "    return (w_fixed * level + w_change * delta) / (level + delta)\n",
     "    return w_fixed * level / (level + delta)\n", check_density_example),
    ("T68", "множитель плотностей посчитан до переноса плотности постоянной части",
     DENSITY_CALL + CALIBRATE,
     "    # --- капитал: вычеты формулой книги, плотности RWA — общим множителем к RWA якоря\n" + CALIBRATE
     + "    carry_fixed_density(X, derived, warnings, level_value=float(oaf_facts) if _num(oaf_facts) else None)\n",
     check_density_on_the_own_path),
    ("T69", "предупреждение о дрейфе структуры не печатается",
     '    if abs(mix["new_anchor"] - mix["share"]) <= SEGMENT_DRIFT:\n', "    if True:\n", check_drift_warning),
    ("T70", "предупреждение о дрейфе структуры печатается всегда",
     '    if abs(mix["new_anchor"] - mix["share"]) <= SEGMENT_DRIFT:\n', "    if False:\n", check_drift_warning),
    ("T71", "решение собрания годового календаря не пишется строкой истории дивидендов",
     '    elif link_base_of(book) == IEA_BASE and report.get("dividend_decisions"):\n', "    elif False:\n",
     check_annual_decision_rows),
    ("T72", "ожидаемый отчёт годовой книги — без суммы, вычтенной из капитала (сумма — DPS × размещённые)",
     '           "pool_all_classes": sum(p * d.div for p, d in got)}\n', "           }\n", check_annual_decision_rows),
    ("T73", "решение квартальной книги с базой iea — без суммы, вычтенной из капитала",
     '            row["pool_all_classes"] = div\n', "            pass\n", check_quarterly_decision_sum),
    ("T74", "годовая книга в квартале собрания без решения не отказывает",
     "    if _decided_in(facts, quarter_start(year, h), period_end(period)):\n", "    if True:\n",
     check_annual_refusal),
    ("T75", "строка цены «механики» — пол без объявленного дивиденда прогона",
     "        values = {k: floor_value(float(v), run_plus.pending_dividend, floor) for k, v in values.items()}\n",
     "        values = {k: floor_value(float(v), 0.0, floor) for k, v in values.items()}\n",
     check_floor_with_a_pending_dividend),
)


@pytest.mark.parametrize("mutation", TOOL_MUTATIONS, ids=lambda m: m[0])
def test_every_mutation_of_the_sixth_pass_tool_is_caught(mutation):
    """Каждую ошибку шестого прохода инструмента роняет проверка этого файла; подлинный инструмент её проходит."""
    ident, title, find, replace, check = mutation
    tool = mutant_tool(find, replace)
    try:
        check(tool)
    except (AssertionError, pytest.fail.Exception):
        return
    pytest.fail(f"мутация инструмента {ident} «{title}» не поймана")


@tact
def test_targets_of_the_sixth_pass_tool_mutations_exist():
    source = TOOL.read_text(encoding="utf-8")
    assert len({m[0] for m in TOOL_MUTATIONS}) == len(TOOL_MUTATIONS)
    for ident, _, find, _, _ in TOOL_MUTATIONS:
        assert source.count(find) == 1, ident
