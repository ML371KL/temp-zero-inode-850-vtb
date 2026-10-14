# -*- coding: utf-8 -*-
"""Перезаякоривание книги с долями вычета якоря, постоянными в рублях (`ops/tools/reanchor.py`, М§4.11, §15.2
пп. 3 и 10; строки «Перезаякоривание» и «Мутации доли вычета якоря» М§18).

Перенос сохраняет суммы в рублях: постоянная часть вычета каждого норматива — прежняя, доля и концы её оси
переписаны на вычет нового якоря. Проверки — тождества, выведенные из книги, фактов и рядов клетки независимо от
кода инструмента: норматив кандидата в каждом квартале пересчитывается по его рядам ФОРМУЛОЙ ПРЕЖНЕЙ КНИГИ
(прежние части вычета якоря, прежняя поправка) — клетка, перезаякоренная на своём пути, несёт ту же функцию
норматива при любом разделе слагаемого якоря между вычетом и поправкой (свойство 7 М§4.11). Фикстура — форма
образца `tests/fixtures/core` с ключами доли и осью-связкой, подставленными тестом; числа — числа фикстуры.

Мутации инструмента (`TOOL_MUTATIONS`) — правка исходного текста инструмента: модуль собирается из текста с одной
заменой, и каждую замену роняет проверка этого файла (мутационный набор `tests/mutations.py` правит только
`model/`).
"""
from __future__ import annotations

import copy
import json
import sys
import types
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from model.book import book_from_dict
from model.grid import run_grid
from model.paths import path_value
from tests.support_core import fixture_book, fixture_dict, fixture_facts
from tests.test_reanchor import R

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "ops" / "tools" / "reanchor.py"
tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

S20, S11 = "capital.n20.deductions_fixed_share", "capital.n11.deductions_fixed_share"
D20, D11 = "capital.n20.deductions_anchor", "capital.n11.deductions_anchor"
G20, G11 = "capital.n20.gap_pp", "capital.n11.gap_pp"
ETA = (0.6, 0.35)                            # доли проверок: разные у двух нормативов и не половина
LOW, HIGH = {S20: 0.4, S11: 0.2}, {S20: 0.8, S11: 0.5}
AXIS = "доля вычета якоря, постоянная в рублях"
CELLS = (("N", "soft", "schedule"), ("H", "downturn", "upper"), ("M", "crisis", "strict"))
EXAMPLE = json.loads((ROOT / "tests" / "fixtures" / "core_pass3" / "example.json").read_text(encoding="utf-8"))
EXAMPLE_TOL = 1e-9                           # допуск примера приложения F (М§17)
NORM_TOL = 1e-12                             # норматив кандидата против формулы прежней книги на его же рядах: разность
#                                              одна во всех кварталах (поправка кандидата добирает остаток калибровки)
OFFSET_TOL = 1e-6                            # сама разность — остаток записи плотностей RWA шестью знаками
PATH_TOL = 1e-8                              # путь норматива двух кандидатов одной клетки
SUM_TOL = 1e-8                               # млрд ₽: сумма в рублях после переноса (доля записана 12 знаками)


def _axes(*extra: dict) -> list[dict]:
    return copy.deepcopy(fixture_dict()["valuation"]["uncertainty"]["axes"]) + [copy.deepcopy(a) for a in extra]


BUNDLE = {"name": AXIS, "kind": "bundle", "paths": [S20, S11], "low": LOW, "high": HIGH, "dist": "triangular"}


@lru_cache(maxsize=None)
def keyed_book():
    """Книга фикстуры с долями вычета якоря и осью-связкой по обоим ключам доли (М§10, правило 6)."""
    return fixture_book().with_overrides({S20: ETA[0], S11: ETA[1], "valuation.uncertainty.axes": _axes(BUNDLE)},
                                         create=True)


def _scene(book: Any, facts: Any) -> SimpleNamespace:
    first = str(book.get("meta.first_period"))
    v = R.period_end(first) + timedelta(days=2)
    live = R.live_at(book, facts, v)
    plus, run_plus, obs = R.expected_run(book, facts, live)
    return SimpleNamespace(book=book, facts=facts, v=v, run_plus=run_plus, obs=obs, period=first,
                           hist=R.history_run(book, run_plus))


@lru_cache(maxsize=None)
def scene() -> SimpleNamespace:
    """Сухой прогон книги с долями: прежняя книга на дате оценки и она же с ожидаемым наблюдением."""
    return _scene(keyed_book(), fixture_facts())


@lru_cache(maxsize=None)
def t_scene() -> SimpleNamespace:
    """То же на фикстуре формы панели `tests/fixtures/core_t`: квартальный календарь дивидендов, вычеты якоря —
    словом `anchor`, рост по капиталу (навёрстывание — ноль: память о разрыве факты якоря не несут)."""
    from tests.support_core_t import put, t_dict, t_facts

    data = t_dict()
    put(data, "capital.growth_constraint.catch_up_rate", 0.0)
    data["capital"]["n20"]["deductions_fixed_share"] = ETA[0]
    data["capital"]["n11"]["deductions_fixed_share"] = ETA[1]
    return _scene(book_from_dict(data, facts=t_facts()), t_facts())


def _carried(tool: Any, key: tuple, change: Callable[[dict], None] | None = None,
             s: SimpleNamespace | None = None) -> SimpleNamespace:
    """Клетка `key`, перезаякоренная на своём пути инструментом `tool`; `change` правит её отчёт (сдвиг слагаемого
    якоря); `s` — сухой прогон книги (без него — фикстуры формы образца). → кандидат, клетка кандидата и клетка
    прежней книги."""
    s = scene() if s is None else s
    report = tool._cell_report(s.run_plus, {key: 1.0})
    if change is not None:
        change(report)
    cand = tool.reanchor(s.book, s.facts, report, valuation_date=s.v, cell=key, base_run=s.hist,
                         observation=s.obs)
    new = run_grid(cand.book, cand.facts, tool.live_at(cand.book, cand.facts, s.v))
    return SimpleNamespace(cand=cand, run=new, cell=new.cell(*key), old=s.run_plus.cell(*key), report=report, s=s)


def _old_norms(c: SimpleNamespace) -> list[tuple[int, float, float, float, float]]:
    """Нормативы клетки кандидата, пересчитанные по её рядам ФОРМУЛОЙ ПРЕЖНЕЙ КНИГИ: части вычета якоря, RWA якоря
    и поправки — прежней книги; капитал, DPreg, фонд, инструменты, неаудированная прибыль, RWA и вычет сценария —
    кандидата. → [(квартал, Н20.0 по формуле, Н20.0 кандидата, Н20.1 по формуле, Н20.1 кандидата)]. Кандидат
    несёт ту же функцию норматива с точностью до постоянной: его поправка откалибрована к нормативу отчёта на
    якоре и добирает остаток записи плотностей RWA и вычета — `same_ratio_function`."""
    old, new = c.s.book, c.cand.book
    ded20_0, ded11_0 = float(old.get(D20)), float(old.get(D11))
    rwa0 = float(c.old.quarters["rwa"][0])
    f = float(old.get("capital.n20.fvoci_recognition"))
    at1 = c.run.ctx.prep.af.at1
    tl = c.run.ctx.timeline
    q_ = c.cell.quarters
    scenario = c.cell.scenario
    out = []
    for q in range(tl.Q + 1):
        rwa = q_["rwa"][q]
        d20 = (1 - ETA[0]) * ded20_0 * rwa / rwa0 + ETA[0] * ded20_0
        d11 = (1 - ETA[1]) * ded11_0 * rwa / rwa0 + ETA[1] * ded11_0
        bvreg = q_["bv"][q] + q_["dpreg"][q] - (1 - f) * q_["reserve"][q]
        t2 = path_value(new.get("capital.n20.t2"), tl.period(q))
        dpp = {n: path_value(new.get(f"capital.reg_scenarios.{scenario}.deduction_pp.{n}"), tl.period(q))
               for n in ("n20_0", "n1_1")}
        n20 = (bvreg - d20 + at1 + t2) / rwa + float(old.get(G20)) - dpp["n20_0"]
        e = q_["e_unaudited"][q]
        if e is None or q_["n11"][q] is None:       # якорь без раскрытой прибыли периода: Н20.1 не считается
            continue
        n11 = (bvreg - max(e, 0.0) - d11) / rwa + float(old.get(G11)) - dpp["n1_1"]
        out.append((q, n20, q_["n20"][q], n11, q_["n11"][q]))
    return out


def same_ratio_function(c: SimpleNamespace, where: Any) -> None:
    """Норматив кандидата в каждом квартале равен формуле прежней книги на его же рядах с точностью до одной
    постоянной (остаток калибровки поправки к нормативу отчёта): разность не меняется по кварталам. Доля,
    перенесённая не суммой, меняет её с ростом RWA — на `η × (Ded_0′ − Ded_0) × (1 / RWA_0′ − 1 / RWA_q)`."""
    rows = _old_norms(c)
    base20, base11 = rows[0][2] - rows[0][1], rows[0][4] - rows[0][3]
    assert abs(base20) < OFFSET_TOL and abs(base11) < OFFSET_TOL, (where, base20, base11)
    for q, n20, got20, n11, got11 in rows:
        assert abs((got20 - n20) - base20) < NORM_TOL, (where, q, got20 - n20, base20)
        assert abs((got11 - n11) - base11) < NORM_TOL, (where, q, got11 - n11, base11)
    assert c.cell.quarters["rwa"][-1] > 1.5 * c.cell.quarters["rwa"][0]      # RWA клетки растут: проверка не пуста


def _sums(c: SimpleNamespace) -> dict[str, tuple[float, float]]:
    """Постоянная в рублях часть вычета: (прежняя книга, кандидат) по ключам доли — как их читает ядро."""
    old, new = c.s.book, c.cand.book
    return {share: (float(old.get(share)) * float(old.get(ded)), float(new.get(share)) * float(new.get(ded)))
            for share, ded in ((S20, D20), (S11, D11))}


# ------------------------------------------------------------------ проверки (их же зовут мутации инструмента)


def check_function(tool: Any) -> None:
    """`carry_fixed_shares` на словаре книги: доля — `η × вычет прежнего якоря / вычет нового`, сумма в рублях
    прежняя у каждого норматива своя; концы связки и оси-сдвига идут своим множителем; книга без ключей не
    трогается; отказы называют путь: сумма больше вычета нового якоря, вычет не больше нуля, конец оси вне [0; 1],
    одна ось-число на двух долях. Сумма «ровно весь вычет» переживает округление записи вычета."""
    old = SimpleNamespace(get=lambda path: {D20: 600.0, D11: 660.0}[path])
    shift = {"name": "сдвиг доли Н20.1", "kind": "shift", "paths": [S11], "low": -0.1, "high": 0.2,
             "dist": "triangular"}

    def book(**changes: Any) -> dict:
        X = copy.deepcopy(dict(keyed_book().source))
        X["valuation"]["uncertainty"]["axes"] = _axes(BUNDLE, shift)
        for path, value in changes.items():
            node = X
            *head, last = path.split(".")
            for part in head:
                node = node[part]
            node[last] = value
        return X

    X, derived = book(), {}
    tool.carry_fixed_shares(X, old, {D20: 630.0, D11: 600.0}, derived)
    cap = X["capital"]
    f20, f11 = 600.0 / 630.0, 660.0 / 600.0
    assert cap["n20"]["deductions_fixed_share"] == pytest.approx(ETA[0] * f20, abs=1e-11)
    assert cap["n11"]["deductions_fixed_share"] == pytest.approx(ETA[1] * f11, abs=1e-11)
    assert cap["n20"]["deductions_fixed_share"] * 630.0 == pytest.approx(ETA[0] * 600.0, abs=SUM_TOL)
    assert cap["n11"]["deductions_fixed_share"] * 600.0 == pytest.approx(ETA[1] * 660.0, abs=SUM_TOL)
    bundle, moved = X["valuation"]["uncertainty"]["axes"][-2:]
    for end, was in (("low", LOW), ("high", HIGH)):
        assert bundle[end][S20] == pytest.approx(was[S20] * f20, abs=1e-11), end
        assert bundle[end][S11] == pytest.approx(was[S11] * f11, abs=1e-11), end
        assert bundle[end][S20] * 630.0 == pytest.approx(was[S20] * 600.0, abs=SUM_TOL)     # сумма на конце оси
    assert moved["low"] == pytest.approx(-0.1 * f11, abs=1e-11) and moved["high"] == pytest.approx(0.2 * f11, abs=1e-11)
    rows = derived["fixed_shares"]
    assert rows[S20] == {"was": ETA[0], "now": cap["n20"]["deductions_fixed_share"], "amount": pytest.approx(360.0),
                         "deduction_was": 600.0, "deduction_now": 630.0}
    assert rows[S11]["amount"] == pytest.approx(231.0) and rows[S11]["deduction_now"] == 600.0
    line = tool.fixed_share_line(derived)
    assert "360.000 млрд ₽" in line and "231.000 млрд ₽" in line and S20 in line and S11 in line
    book_from_dict(X, facts=fixture_facts())                                 # кандидат проходит схему
    # книга без ключей: шага нет
    plain, derived = copy.deepcopy(dict(fixture_book().source)), {}
    before = copy.deepcopy(plain)
    tool.carry_fixed_shares(plain, old, {D20: 630.0, D11: 600.0}, derived)
    assert plain == before and "fixed_shares" not in derived and tool.fixed_share_line(derived) is None
    # отказы
    for deductions, fragments in (({D20: 300.0, D11: 600.0}, (S20, "вне [0; 1]", "360.000")),
                                  ({D20: 630.0, D11: 200.0}, (S11, "вне [0; 1]", "231.000")),
                                  ({D20: -5.0, D11: 600.0}, (S20, "не больше нуля")),
                                  ({D20: 630.0, D11: 0.0}, (S11, "не больше нуля")),
                                  ({D20: 470.0, D11: 600.0}, (AXIS, S20, "конец оси", "вне [0; 1]")),   # 0,8 × 600 / 470
                                  # доля 0,35 × 660 / 347 = 0,666 и конец связки 0,951 — в границах, а доля с
                                  # приращением оси-сдвига 0,2 × 660 / 347 — 1,046
                                  ({D20: 630.0, D11: 347.0}, ("сдвиг доли Н20.1", S11, "конец оси"))):
        with pytest.raises(tool.ReportError) as err:
            tool.carry_fixed_shares(book(), old, deductions, {})
        for fragment in fragments:
            assert fragment in str(err.value), (fragment, str(err.value))
    both = {"name": "обе доли одним числом", "kind": "value", "paths": [S20, S11], "low": 0.2, "high": 0.5,
            "dist": "triangular"}
    X = book()
    X["valuation"]["uncertainty"]["axes"] = _axes(both)
    with pytest.raises(tool.ReportError, match="разделить ось"):
        tool.carry_fixed_shares(X, old, {D20: 630.0, D11: 600.0}, {})
    # доля 1 на своём пути: вычет кандидата записан с округлением — сумма «весь вычет» остаётся долей 1
    X = book(**{S20: 1.0, S11: 0.0})
    X["valuation"]["uncertainty"]["axes"] = _axes()
    tool.carry_fixed_shares(X, old, {D20: 599.9996, D11: -3.0}, {})
    assert X["capital"]["n20"]["deductions_fixed_share"] == 1.0 and X["capital"]["n11"]["deductions_fixed_share"] == 0.0
    with pytest.raises(tool.ReportError, match="вне \\[0; 1\\]"):
        tool.carry_fixed_shares(book(**{S20: 1.0}), old, {D20: 599.99, D11: 660.0}, {})
    # ключи доли идут за центром связкой: правило переноса конца названо
    assert S20 in tool.BUNDLE_CARRIED and S11 in tool.BUNDLE_CARRIED
    assert "сумма в рублях прежняя" in tool.reason(S20) and "сумма в рублях прежняя" in tool.reason(S11)


def check_cell_on_its_own_path(tool: Any, cells: tuple = CELLS) -> None:
    """Клетка, перезаякоренная на своём пути: постоянная в рублях часть вычета каждого норматива — прежняя; норматив
    кандидата в каждом квартале равен формуле прежней книги на его рядах; при прежнем разделе слагаемого якоря
    (отчёт клетки) совпадают и сами вычеты; концы оси-связки несут прежние суммы; стоимость клетки сохранена."""
    s = scene()
    for key in cells:
        c = _carried(tool, key)
        for share, (was, now) in _sums(c).items():
            assert was > 100.0 and now == pytest.approx(was, abs=SUM_TOL), (key, share, was, now)
        rows = c.cand.derived["fixed_shares"]
        assert set(rows) == {S20, S11}
        for share, ded in ((S20, D20), (S11, D11)):
            assert rows[share]["was"] == float(s.book.get(share)) and rows[share]["now"] == float(c.cand.book.get(share))
            assert rows[share]["deduction_was"] == float(s.book.get(ded))
            assert rows[share]["deduction_now"] == pytest.approx(float(c.cand.book.get(ded)), abs=1e-9)
            assert rows[share]["now"] < rows[share]["was"] - 1e-3          # вычет вырос — доля той же суммы меньше
        same_ratio_function(c, key)
        # прежний раздел слагаемого якоря: вычет кандидата — прежняя формула на его RWA (запись вычета — 0,001)
        rwa0 = float(c.old.quarters["rwa"][0])
        tl = c.run.ctx.timeline
        for q in range(tl.Q + 1):
            rwa = c.cell.quarters["rwa"][q]
            for name, ded, eta in (("ded20", D20, ETA[0]), ("ded11", D11, ETA[1])):
                want = float(s.book.get(ded)) * ((1 - eta) * rwa / rwa0 + eta)
                assert c.cell.quarters[name][q] == pytest.approx(want, abs=5e-3), (key, q, name)
        axis = next(a for a in c.cand.data["valuation"]["uncertainty"]["axes"] if a["name"] == AXIS)
        for end, was in (("low", LOW), ("high", HIGH)):
            for share, ded in ((S20, D20), (S11, D11)):
                assert axis[end][share] * float(c.cand.book.get(ded)) == pytest.approx(
                    was[share] * float(s.book.get(ded)), abs=SUM_TOL), (key, end, share)
        assert abs(c.cell.v_ri / s.hist.cell(*key).v_ri - 1) <= R.MECHANICS_TOL / 10, key
        reasons = {tool.dotted(p): tool.reason(tool.dotted(p)) for p, _, _ in c.cand.changes}
        assert "сумма в рублях прежняя" in reasons[S20] and "сумма в рублях прежняя" in reasons[S11]


def check_term_moved_into_the_gap(tool: Any, key: tuple = CELLS[1]) -> None:
    """Перенос со сдвигом слагаемого якоря из вычета в поправку: капитал группы отчёта выше на Δ при тех же
    нормативах — вычет нового якоря ниже на Δ, поправка ниже на Δ / RWA. Суммы в рублях прежние, норматив
    кандидата в каждом квартале — формула прежней книги на его рядах, а сами вычеты — другие (свойство 7 М§4.11)."""
    delta = {"basel_cet1": 150.0, "bank_base_capital": -90.0}

    def move(report: dict) -> None:
        for slot, d in delta.items():
            report["capital"][slot] += d

    plain, c = _carried(tool, key), _carried(tool, key, move)
    for share, (was, now) in _sums(c).items():
        assert now == pytest.approx(was, abs=SUM_TOL), (share, was, now)
    assert float(c.cand.book.get(D20)) == pytest.approx(float(plain.cand.book.get(D20)) - 150.0, abs=2e-3)
    assert float(c.cand.book.get(D11)) == pytest.approx(float(plain.cand.book.get(D11)) + 90.0, abs=2e-3)
    rwa1 = c.report["capital"]["basel_rwa"]
    assert float(c.cand.book.get(G20)) == pytest.approx(float(plain.cand.book.get(G20)) - 150.0 / rwa1, abs=1e-7)
    assert float(c.cand.book.get(G11)) == pytest.approx(float(plain.cand.book.get(G11)) + 90.0 / rwa1, abs=1e-7)
    assert float(c.cand.book.get(S20)) > float(plain.cand.book.get(S20)) + 0.05       # та же сумма — большая доля
    assert float(c.cand.book.get(S11)) < float(plain.cand.book.get(S11)) - 0.01
    last = c.run.ctx.timeline.Q
    assert c.cell.quarters["ded20"][last] < plain.cell.quarters["ded20"][last] - 100.0
    same_ratio_function(c, key)
    for name in ("n20", "n11"):                       # путь норматива — тот же, что без сдвига слагаемого
        for a, b in zip(c.cell.quarters[name], plain.cell.quarters[name]):
            assert a == pytest.approx(b, abs=PATH_TOL), name
    assert c.cell.v_ri == pytest.approx(plain.cell.v_ri, rel=1e-7)


def check_refusal_in_the_carry(tool: Any, key: tuple = CELLS[1]) -> None:
    """Постоянная сумма больше вычета нового якоря — отказ инструмента с названным путём доли: капитал группы
    отчёта выше настолько, что вычет нового якоря — половина прежнего (доля 0,6 стала бы 1,2)."""
    s = scene()
    half = 0.5 * float(s.book.get(D20))

    def move(report: dict) -> None:
        report["capital"]["basel_cet1"] += half

    with pytest.raises(tool.ReportError) as err:
        _carried(tool, key, move)
    text = str(err.value)                             # отказ — о самой доле, раньше отказа о конце её оси
    assert text.startswith(S20) and "новая доля" in text and "вне [0; 1]" in text and "решение книги" in text, text


def check_capital_form(tool: Any) -> None:
    """Замена оценки нормативов фактом формы (без смены якоря) суммы в рублях не меняет: вычеты выведены заново
    на капитале формы, доли и концы оси переписаны на них; отчёт о замене печатает обе суммы."""
    book, facts = keyed_book(), fixture_facts()
    form = {"schema": tool.CAPITAL_FORM, "period": str(book.get("meta.anchor_period")),
            "n20_0": facts.need("capital", "n20_0.value") - 0.002,
            "n1_1_bank": facts.need("capital", "n1_1_bank.value") + 0.001,
            "basel_cet1": facts.need("capital", "basel.cet1") + 40.0,
            "basel_rwa": facts.need("capital", "basel.rwa") * 1.01,
            "bank_base_capital": facts.need("capital", "bank_base_capital") - 25.0}
    result = tool.replace_capital(book, facts, form)
    new = result["candidate"]
    # вычеты — формулой книги на капитале формы (числа фикстуры записаны с округлением до 0,1)
    assert float(new.book.get(D20)) == pytest.approx(float(book.get(D20)) - 40.0, abs=0.1)
    assert float(new.book.get(D11)) == pytest.approx(float(book.get(D11)) + 25.0, abs=0.1)
    for share, ded in ((S20, D20), (S11, D11)):
        was = float(book.get(share)) * float(book.get(ded))
        assert float(new.book.get(share)) * float(new.book.get(ded)) == pytest.approx(was, abs=SUM_TOL), share
        assert new.derived["fixed_shares"][share]["amount"] == pytest.approx(was)
        assert float(new.book.get(share)) != float(book.get(share))
    axis = next(a for a in new.data["valuation"]["uncertainty"]["axes"] if a["name"] == AXIS)
    assert axis["high"][S20] * float(new.book.get(D20)) == pytest.approx(HIGH[S20] * float(book.get(D20)), abs=SUM_TOL)
    assert axis["low"][S11] * float(new.book.get(D11)) == pytest.approx(LOW[S11] * float(book.get(D11)), abs=SUM_TOL)
    assert new.derived["anchor_row"]["n20"] == pytest.approx(form["n20_0"], abs=1e-8)
    assert new.derived["anchor_row"]["n11"] == pytest.approx(form["n1_1_bank"], abs=1e-8)
    text = tool.form_text(book, result)
    assert "перенесены суммой" in text and S20 in text and S11 in text


def check_example_f(tool: Any) -> None:
    """Перенос якоря примера приложения F.2 до 1e-9: суммы в рублях прежние, новые доли — на вычеты нового якоря;
    вычет следующего квартала у прежней и у новой книги один; тот же якорь со слагаемым, перенесённым в
    поправку, — другая доля той же суммы и тот же путь норматива; доля, оставленная прежним числом, дала бы
    другой вычет."""
    x = EXAMPLE["deductions"]
    inp, want = x["inputs"], x["reanchor"]
    quarter = x["with_share"]["quarter"]
    old = SimpleNamespace(get=lambda path: {D20: inp["ded20_0"], D11: inp["ded11_0"]}[path])

    def carried(ded20: float, ded11: float) -> tuple[dict, dict]:
        X = copy.deepcopy(dict(fixture_book().source))
        X["capital"]["n20"]["deductions_fixed_share"] = inp["eta20"]
        X["capital"]["n11"]["deductions_fixed_share"] = inp["eta11"]
        derived: dict = {}
        tool.carry_fixed_shares(X, old, {D20: ded20, D11: ded11}, derived)
        return X["capital"], derived["fixed_shares"]

    cap, rows = carried(quarter["ded20"], quarter["ded11"])
    eta20, eta11 = cap["n20"]["deductions_fixed_share"], cap["n11"]["deductions_fixed_share"]
    assert abs(eta20 - want["eta20_new"]) < EXAMPLE_TOL and abs(eta11 - want["eta11_new"]) < EXAMPLE_TOL
    assert abs(rows[S20]["amount"] - want["fix20"]) < EXAMPLE_TOL and abs(rows[S11]["amount"] - want["fix11"]) < EXAMPLE_TOL
    ratio = inp["reanchor"]["rwa_next_ratio"]              # RWA следующего квартала к RWA нового якоря
    assert abs(quarter["rwa"] * ratio - want["rwa_next"]) < EXAMPLE_TOL
    old_book = inp["ded20_0"] * ((1 - inp["eta20"]) * want["rwa_next"] / inp["rwa0"] + inp["eta20"])
    new_book = quarter["ded20"] * ((1 - eta20) * ratio + eta20)
    assert abs(old_book - want["ded20_next_old_book"]) < EXAMPLE_TOL
    assert abs(new_book - want["ded20_next_new_book"]) < EXAMPLE_TOL and abs(new_book - old_book) < EXAMPLE_TOL
    kept = quarter["ded20"] * ((1 - inp["eta20"]) * ratio + inp["eta20"])
    assert abs(kept - want["ded20_next_if_share_kept"]) < EXAMPLE_TOL
    assert abs(kept - new_book - want["mechanics_if_share_kept"]) < EXAMPLE_TOL
    # тот же якорь, слагаемое Δ стоит не в вычете Н20.0, а в поправке
    alt = want["alt"]
    cap, _ = carried(alt["ded20_anchor"], quarter["ded11"])
    share = cap["n20"]["deductions_fixed_share"]
    assert abs(share - alt["eta20"]) < EXAMPLE_TOL
    moved = alt["ded20_anchor"] * ((1 - share) * ratio + share)
    assert abs(moved - alt["ded20_next"]) < EXAMPLE_TOL
    assert abs(alt["gap20"] - (inp["gap20"] - alt["delta"] / quarter["rwa"])) < EXAMPLE_TOL
    # путь норматива тот же: меньший вычет и меньшая поправка гасят друг друга
    assert abs((new_book - moved) / want["rwa_next"] + (alt["gap20"] - inp["gap20"])) < EXAMPLE_TOL


# ------------------------------------------------------------------ четвёртый проход (М§15.2 пп. 3, 13; REANCHOR §3.16)

EXAMPLE_G = json.loads((ROOT / "tests" / "fixtures" / "core_pass4" / "example.json").read_text(encoding="utf-8"))


def _boundary_book(center20: float, center11: float, axes: list[dict], reverse: list[dict] | None = None) -> dict:
    X = copy.deepcopy(dict(keyed_book().source))
    X["capital"]["n20"]["deductions_fixed_share"] = center20
    X["capital"]["n11"]["deductions_fixed_share"] = center11
    X["valuation"]["uncertainty"]["axes"] = _axes(*axes)
    X["valuation"]["reverse_dcf"]["axes"] = (copy.deepcopy(fixture_dict()["valuation"]["reverse_dcf"]["axes"])
                                             + [copy.deepcopy(a) for a in reverse or []])
    return X


def _carry_ok(tool: Any, X: dict, old: Any, deductions: dict, derived: dict) -> None:
    """Перенос, которому правило отказа не даёт: отказ инструмента здесь — нарушение правила (утверждение)."""
    try:
        tool.carry_fixed_shares(X, old, deductions, derived)
    except tool.ReportError as exc:
        raise AssertionError(f"отказ, которого правило М§15.2 п. 3 не даёт: {exc}") from exc


def check_boundary_g4(tool: Any) -> None:
    """Пример приложения G.4 (М§15.2 п. 3): центр и концы осей внутри (0; 1) — суммой в рублях (до 1e-9); конец оси
    (числа, сдвига, связки) и край отрезка поиска строки обратного расчёта на границе 1 или 0 остаются на ней; конец
    внутри (0; 1), ушедший за 1, и центр 1 — отказ; доля 0 остаётся нулём, и при вычете нового якоря не больше
    нуля (концы осей на границе — на месте), а доля больше нуля или конец оси внутри (0; 1) тогда — отказ."""
    g = EXAMPLE_G["share_boundary"]
    was, now = g["deduction_old"], g["deduction_new"]
    old = SimpleNamespace(get=lambda path: {D20: was, D11: was}[path])
    cases = {c["name"]: c for c in g["cases"]}
    want = lambda name: cases[name]["now"]  # noqa: E731
    value20 = {"name": "доля Н20.0", "kind": "value", "paths": [S20], "low": 0.4, "high": 0.8, "dist": "triangular"}
    value11 = {"name": "доля Н20.1 до границ", "kind": "value", "paths": [S11], "low": 0.0, "high": 1.0,
               "dist": "triangular"}
    search = {"name": "доля вычета Н20.0", "kind": "value", "paths": [S20], "search": [0.0, 1.0],
              "range": [0.4, 0.8], "unit": "%"}
    X, derived = _boundary_book(0.6065, 0.6065, [value20, value11], [search]), {}
    _carry_ok(tool, X, old, {D20: now, D11: now}, derived)
    assert abs(X["capital"]["n20"]["deductions_fixed_share"] - want("центр 0,6065")) < EXAMPLE_TOL
    a20, a11 = X["valuation"]["uncertainty"]["axes"][-2:]
    assert abs(a20["low"] - want("нижний конец оси 0,4")) < EXAMPLE_TOL
    assert abs(a20["high"] - want("верхний конец оси 0,8")) < EXAMPLE_TOL
    assert a11["high"] == want("конец оси на границе 1") == 1.0 and a11["low"] == want("конец оси на границе 0") == 0.0
    row = X["valuation"]["reverse_dcf"]["axes"][-1]
    assert row["search"] == [0.0, want("край отрезка поиска 1")] == [0.0, 1.0], row["search"]
    assert abs(row["range"][0] - want("нижний конец оси 0,4")) < EXAMPLE_TOL
    assert abs(row["range"][1] - want("верхний конец оси 0,8")) < EXAMPLE_TOL
    assert abs(g["multiplier"] - was / now) < EXAMPLE_TOL
    # связка и ось-сдвиг: конец на границе — на ней; сдвиг — доля плюс приращение
    bundle = {"name": AXIS, "kind": "bundle", "paths": [S20, S11], "low": {S20: 0.0, S11: 0.2},
              "high": {S20: 1.0, S11: 0.5}, "dist": "triangular"}
    shift = {"name": "сдвиг доли Н20.1", "kind": "shift", "paths": [S11], "low": -0.6065, "high": 0.2,
             "dist": "triangular"}
    X = _boundary_book(0.6065, 0.6065, [bundle, shift])
    _carry_ok(tool, X, old, {D20: now, D11: now}, {})
    b, s = X["valuation"]["uncertainty"]["axes"][-2:]
    fresh = X["capital"]["n11"]["deductions_fixed_share"]
    assert (b["low"][S20], b["high"][S20]) == (0.0, 1.0)
    assert abs(b["high"][S11] - 0.5 * was / now) < EXAMPLE_TOL
    assert abs(fresh + s["low"]) < 1e-12 and abs(s["high"] - 0.2 * was / now) < EXAMPLE_TOL
    # отказы: конец внутри (0; 1), ушедший за 1; центр на границе 1 (сумма больше вычета нового якоря)
    for center, axes, name, fragment in ((0.6065, [{**value20, "high": cases["конец оси 0,9999"]["was"]}],
                                          "конец оси 0,9999", "конец оси"),
                                         (cases["центр на границе 1"]["was"], [], "центр на границе 1", "новая доля")):
        assert cases[name]["now"] is None
        with pytest.raises(tool.ReportError) as err:
            tool.carry_fixed_shares(_boundary_book(center, 0.6065, axes), old, {D20: now, D11: now}, {})
        assert S20 in str(err.value) and fragment in str(err.value), str(err.value)
    # доля 0 — ноль; и при вычете нового якоря не больше нуля
    X = _boundary_book(cases["центр 0"]["was"], 0.6065, [value11])
    _carry_ok(tool, X, old, {D20: now, D11: now}, {})
    assert X["capital"]["n20"]["deductions_fixed_share"] == want("центр 0") == 0.0
    edge = {**value11, "name": "доля Н20.0 до границ", "paths": [S20]}
    X = _boundary_book(0.0, 0.6065, [edge])
    _carry_ok(tool, X, old, {D20: -1.0, D11: now}, {})
    axis = X["valuation"]["uncertainty"]["axes"][-1]
    assert X["capital"]["n20"]["deductions_fixed_share"] == 0.0 and (axis["low"], axis["high"]) == (0.0, 1.0)
    for center, axes in ((0.6065, []), (0.0, [value20])):
        with pytest.raises(tool.ReportError, match="не больше нуля"):
            tool.carry_fixed_shares(_boundary_book(center, 0.6065, axes), old, {D20: 0.0, D11: now}, {})


def _recap_step(tool: Any, book: Any, facts: Any) -> Any:
    """Шаг цепочки ожидаемых отчётов: прежняя книга на дате оценки после своего первого квартала, её ожидаемый
    отчёт и перенос на него."""
    first = str(book.get("meta.first_period"))
    v = tool.period_end(first) + timedelta(days=2)
    _, run_plus, obs = tool.expected_run(book, facts, tool.live_at(book, facts, v))
    report = tool.expected_report(book, facts, run=run_plus)
    return tool.reanchor(book, facts, report, valuation_date=v, base_run=run_plus, observation=obs), report


def _recap_book(min_amount: float | None = None, adj: float | None = None) -> Any:
    """Книга фикстуры докапитализации с решением о взносе в 4-м квартале и окном 1; запас менеджмента — такой, что
    в клетках кризиса взнос стоит уже в первом квартале решения (2026К4)."""
    from tests import support_core_pass2 as S2
    from tests import support_core_recap as RC

    extra = {**S2.keyed(4, 1), **S2.MID_BUFFER}
    if min_amount is not None:
        extra[f"{RC.RECAP}.min_amount"] = min_amount
    if adj is not None:
        extra["valuation.share_count_adj"] = adj
    return RC.book_of(extra)


def check_closed_contribution_refused(tool: Any) -> None:
    """Взнос закрываемого квартала (М§15.2 п. 13, REANCHOR §3.16): цепочка ожидаемых отчётов на фикстуре с решением
    о взносе в 4-м квартале — закрытие квартала без решения (2026К3) проходит; закрытие квартала решения со взносом
    хотя бы в одной клетке (2026К4) — отказ с кварталом, числом и массой клеток и ссылкой на правило; закрытие
    квартала решения без взносов (порог выше любого недостатка) проходит."""
    facts = fixture_facts()
    first, _ = _recap_step(tool, _recap_book(), facts)
    assert first.period.endswith("Q3")
    paid = [c for c in run_grid(first.book, first.facts).cells if c.quarters["rec"][1] > 0]
    assert paid, "у кандидата нет взноса в квартале решения — проверка ничего не проверяет"
    with pytest.raises(tool.ReportError) as err:
        _recap_step(tool, first.book, first.facts)
    text = str(err.value)
    for fragment in ("2026Q4", f"{len(paid)} клетках", "масса", "М§15.2 п. 13", "§3.16", paid[0].label):
        assert fragment in text, (fragment, text)
    quiet, _ = _recap_step(tool, _recap_book(min_amount=RC_HUGE), facts)
    assert not any(c.quarters["rec"][1] > 0 for c in run_grid(quiet.book, quiet.facts).cells)
    second, _ = _recap_step(tool, quiet.book, quiet.facts)
    assert second.period.endswith("Q4")


RC_HUGE = 1e9                                # порог взноса выше любого недостатка: механизм включён, взносов нет


def check_shares_warning(tool: Any) -> None:
    """Отчёт с изменившимся числом размещённых акций у книги с поправкой делителя — предупреждение в ручных шагах
    (REANCHOR §3.16); без поправки или без изменения — нет."""
    facts = fixture_facts()
    for adj, more, warned in ((0.25, 500.0, True), (0.25, 0.0, False), (None, 500.0, False)):
        book = _recap_book(min_amount=RC_HUGE, adj=adj)
        first = str(book.get("meta.first_period"))
        v = tool.period_end(first) + timedelta(days=2)
        _, run_plus, obs = tool.expected_run(book, facts, tool.live_at(book, facts, v))
        report = tool.expected_report(book, facts, run=run_plus)
        issued = float(facts.need("shares", "issued_total"))
        report["shares"] = {"issued_total": issued + more,
                            "outstanding_total": float(facts.need("shares", "outstanding_total")) + more}
        cand = tool.reanchor(book, facts, report, valuation_date=v, base_run=run_plus, observation=obs)
        notes = [w for w in cand.warnings if "valuation.share_count_adj" in w and "размещённых акций" in w]
        assert bool(notes) == warned, (adj, more, notes)


# ------------------------------------------------------------------ тесты


@tact
def test_shares_are_carried_by_the_amount_in_roubles_and_refusals_name_the_path():
    check_function(R)


@tact
def test_example_of_appendix_f_is_reproduced_by_the_carry():
    check_example_f(R)


@tact
def test_a_cell_with_shares_reanchored_on_its_own_path_keeps_the_ratio_function():
    check_cell_on_its_own_path(R, CELLS[1:2])


@ci_only
def test_cells_with_shares_reanchored_on_their_own_paths_keep_the_ratio_function():
    check_cell_on_its_own_path(R)


@ci_only
def test_cells_of_the_quarterly_form_with_shares_keep_the_ratio_function():
    """Форма панели: вычеты якоря — словом `anchor` (инструмент читает вычет нового якоря так, как его выведет
    ядро), квартальный календарь дивидендов, рост по капиталу, множитель плотности режима. Суммы в рублях
    прежние, функция норматива кандидата — прежней книги, стоимость клетки сохранена."""
    s = t_scene()
    for key in (("N", "soft", "schedule"), ("H", "downturn", "strict"), ("M", "crisis", "strict")):
        c = _carried(R, key, s=s)
        assert c.cand.data["capital"]["n20"]["deductions_anchor"] == "anchor"
        for share, (was, now) in _sums(c).items():
            assert was > 10.0 and now == pytest.approx(was, abs=SUM_TOL), (key, share, was, now)
        same_ratio_function(c, key)
        assert abs(c.cell.v_ri / s.hist.cell(*key).v_ri - 1) <= R.MECHANICS_TOL / 10, key


@tact
def test_a_term_of_the_anchor_moved_into_the_gap_leaves_the_ratios():
    check_term_moved_into_the_gap(R)


@tact
def test_a_fixed_amount_above_the_new_deduction_is_refused_by_the_tool():
    check_refusal_in_the_carry(R)


@tact
def test_the_capital_form_keeps_the_amounts_in_roubles():
    check_capital_form(R)


@tact
def test_example_g4_a_boundary_of_the_share_stays_a_boundary():
    check_boundary_g4(R)


def test_a_contribution_in_the_closed_decision_quarter_is_refused():
    check_closed_contribution_refused(R)


def test_a_report_with_new_issued_shares_warns_a_book_with_the_divisor_adjustment():
    check_shares_warning(R)


@ci_only
def test_the_dry_run_of_a_book_with_shares_prints_the_amounts(tmp_path):
    """Сухой прогон книги с долями: «факт = ожидание ⇒ механика ≈ 0» во всех клетках, отчёт инструмента печатает
    обе суммы в рублях рядом с новыми долями."""
    s = scene()
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v)
    assert len(mech["rows"]) == len(s.run_plus.cells) and mech["ok"]
    assert abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 10, mech["worst"]
    expected = R.expected_report(s.book, s.facts, run=s.run_plus)
    result = R.attribution(s.book, s.facts, expected, valuation_date=s.v, cells=False)
    text = R.report_text(s.book, result)
    assert "перенесены суммой" in text and S20 in text and S11 in text


# ------------------------------------------------------------------ мутации инструмента (М§18)

CARRY_CALL = ('    calibrate_capital(X, new_facts, float(report["capital"]["basel_rwa"]), derived, warnings,\n'
              '                      numbers="estimated_levels" in derived, old=book)\n')
TOOL_MUTATIONS: tuple[tuple[str, str, str, str, Callable[[Any], None]], ...] = (
    ("T1", "доля перенесена прежним числом",
     "        fresh = float(eta) * factor\n", "        fresh = float(eta)\n", check_function),
    ("T2", "доля Н20.1 переписана по вычету Н20.0",
     "        was, now = float(old.get(ded)), float(deductions[ded])\n",
     "        was, now = float(old.get(DEDUCTIONS[0])), float(deductions[DEDUCTIONS[0]])\n", check_function),
    ("T3", "доля поделена на рост RWA вместо отношения вычетов якоря", CARRY_CALL,
     CARRY_CALL + "    for share, _ in FIXED_SHARES:\n"
                  "        _set(X, share, _r(float(book.get(share)) * _mean(base_run, weights, 'rwa', 0) / "
                  "_mean(base_run, weights, 'rwa', 1), SHARE_DIGITS))\n", check_term_moved_into_the_gap),
    ("T4", "конец оси-связки доли не идёт за центром",
     "                    table[share] = _carry_end(float(table[share]), factor)\n",
     "                    table[share] = float(table[share])\n", check_function),
    ("T5", "конец оси-сдвига доли не идёт за центром",
     "    return _r(v * factor, SHARE_DIGITS)\n\n\ndef _share_ends(",
     "    return v\n\n\ndef _share_ends(", check_function),
    ("T5b", "конец оси-числа доли не идёт за центром",
     "                    _move_axis(axis, keys, lambda v, factor=factor: _carry_end(v, factor))\n",
     "                    _move_axis(axis, keys, lambda v, factor=factor: v)\n", check_boundary_g4),
    ("T6", "доля нового якоря больше единицы принята",
     "        if not 0.0 <= fresh <= 1.0:\n", "        if False:\n", check_refusal_in_the_carry),
    ("T7", "множитель доли перевёрнут: вычет нового якоря к вычету прежнего",
     "        factor = was / now\n", "        factor = now / was\n", check_function),
    ("T8", "замена оценки нормативов фактом формы долю не переписывает",
     '    calibrate_capital(X, new_facts, float(form["basel_rwa"]), derived, warnings, old=book)\n',
     '    calibrate_capital(X, new_facts, float(form["basel_rwa"]), derived, warnings)\n', check_capital_form),
    ("T9", "перенос якоря долю не переписывает: прежняя книга до калибровки капитала не доходит", CARRY_CALL,
     CARRY_CALL.replace(", old=book", ""), check_cell_on_its_own_path),
    ("T10", "конец оси доли вне [0; 1] после переноса принят",
     "            out = [v for v in moved if not -1e-12 <= v <= 1.0 + 1e-12]\n", "            out = []\n",
     check_function),
    ("T11", "вычет нового якоря не больше нуля принят",
     "        if not now > 0:\n", "        if False:\n", check_function),
    # четвёртый проход (М§15.2 пп. 3, 13; REANCHOR §3.16)
    ("T12", "отказ при взносе в закрываемом квартале решения снят",
     "    refuse_closed_contribution(base_run)", "    pass", check_closed_contribution_refused),
    ("T13", "конец оси на границе 1 переносится множителем (граница не остаётся границей)",
     "    if v in SHARE_BOUNDS:\n        return v\n", "", check_boundary_g4),
    ("T14", "доля 0 при неположительном вычете нового якоря — отказ",
     "            if float(eta) == 0 and not inner:\n", "            if False:\n", check_boundary_g4),
    ("T15", "отчёт с изменившимся числом акций у книги с поправкой делителя — без предупреждения",
     "    if note:                                         # акции объявленного выпуска (REANCHOR §3.16)\n"
     "        warnings.append(note)\n", "", check_shares_warning),
)


def mutant_tool(find: str, replace: str) -> Any:
    """Модуль инструмента, собранный из его исходного текста с одной заменой."""
    source = TOOL.read_text(encoding="utf-8")
    assert source.count(find) == 1, f"строка-цель мутации инструмента не найдена или не одна: {find!r}"
    name = "tool_reanchor_mutant"
    module = types.ModuleType(name)
    module.__file__ = str(TOOL)
    sys.modules[name] = module               # классы данных инструмента ищут свой модуль по имени
    try:
        exec(compile(source.replace(find, replace, 1), str(TOOL), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("mutation", TOOL_MUTATIONS, ids=lambda m: m[0])
def test_every_mutation_of_the_tool_is_caught(mutation):
    """Каждую ошибку переноса долей роняет проверка этого файла — утверждением или отказом, которого подлинный
    инструмент не даёт; подлинный инструмент ту же проверку проходит (тесты выше)."""
    ident, title, find, replace, check = mutation
    tool = mutant_tool(find, replace)
    try:
        check(tool)
    except (AssertionError, pytest.fail.Exception):  # утверждение проверки или «отказа не было»
        return
    except ZeroDivisionError:                        # деление на вычет нового якоря, равный нулю, — только у T11
        assert ident == "T11", title
        return
    pytest.fail(f"мутация инструмента {ident} «{title}» не поймана")


@tact
def test_targets_of_the_tool_mutations_exist():
    source = TOOL.read_text(encoding="utf-8")
    assert len({m[0] for m in TOOL_MUTATIONS}) == len(TOOL_MUTATIONS)
    for ident, _, find, _, _ in TOOL_MUTATIONS:
        assert source.count(find) == 1, ident
