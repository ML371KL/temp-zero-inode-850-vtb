# -*- coding: utf-8 -*-
"""Перезаякоривание книги с путём постоянной части прочих активов и с вычетом сценария в рублях
(`ops/tools/reanchor.py`, М§4.3, §4.11, §15.2 п. 3; строки «Перезаякоривание» и «Мутации пятого прохода» М§18).

Путь постоянной части переносится от нового якоря: приращение квартала нового якоря — в число постоянной части,
траектория и концы осей на её путях — минус оно, конец оси на числе — плюс; постоянная часть каждого квартала
прежняя, якорное условие новой книги держится, при нулевом приращении книга не меняется. Вычет сценария в рублях
переносится как есть: нормативы клетки, перезаякоренной на своём пути, несут функцию норматива прежней книги (её
части вычета якоря, RWA якоря, поправка и рубли траектории) с точностью до одной постоянной. Проверки — тождества,
выведенные из книги и рядов клетки независимо от кода инструмента; числа — приложения H.2 и фикстуры формы образца.

Мутации инструмента (`TOOL_MUTATIONS`) — правка исходного текста инструмента (`mutant_tool` файла
`tests/test_reanchor_shares.py`): каждую замену роняет проверка этого файла.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from model.book import book_from_dict
from model.paths import Trajectory, path_value
from tests.support_core import fixture_dict, fixture_facts
from tests.test_reanchor import R
from tests.test_reanchor_shares import _carried, _scene, mutant_tool

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "ops" / "tools" / "reanchor.py"
tact = pytest.mark.tact

LEVEL, CHANGE = "volumes.other_assets_fixed", "volumes.other_assets_fixed_change"
W_FIXED, W_CHANGE = "capital.rwa.density.other_assets_fixed", "capital.rwa.density.other_assets_fixed_change"
S20, S11 = "capital.n20.deductions_fixed_share", "capital.n11.deductions_fixed_share"
D20, D11 = "capital.n20.deductions_anchor", "capital.n11.deductions_anchor"
G20, G11 = "capital.n20.gap_pp", "capital.n11.gap_pp"
EXAMPLE = json.loads((ROOT / "tests" / "fixtures" / "core_pass5" / "example.json").read_text(encoding="utf-8"))
ETA = (0.6, 0.35)
NORM_TOL = 1e-12                             # разность норматива кандидата и формулы прежней книги — одна по кварталам
OFFSET_TOL = 1e-6                            # сама разность — остаток записи плотностей RWA шестью знаками
LEVEL_TOL = 1e-9                             # млрд ₽: постоянная часть квартала (число и путь — 9 знаков)


def _get(tree: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        tree = tree[part]
    return tree


def _put(tree: dict, dotted: str, value: Any) -> None:
    *head, last = dotted.split(".")
    for part in head:
        tree = tree.setdefault(part, {})
    tree[last] = copy.deepcopy(value)


def _level_at(X: dict, anchor: str, period: str) -> float:
    """Постоянная часть прочих активов квартала по книге-словарю: число плюс приращение пути к якорю книги (М§4.3)."""
    t = Trajectory(_get(X, CHANGE))
    y, q = (int(period[:4]), int(period[-1]))
    ay, aq = (int(anchor[:4]), int(anchor[-1]))
    return float(_get(X, LEVEL)) + t.value(y, q) - t.value(ay, aq)


# ------------------------------------------------------------------ шаг инструмента на словаре книги (пример H.2)


def _g2_book(**changes: Any) -> dict:
    g2 = EXAMPLE["fixed_change"]["inputs"]
    X = copy.deepcopy(fixture_dict())
    _put(X, LEVEL, float(g2["oa_fixed"]))
    _put(X, CHANGE, {str(k): float(v) for k, v in g2["path"].items()})
    _put(X, W_FIXED, g2["density_oaf"])
    _put(X, W_CHANGE, g2["density_change"])
    axes = X["valuation"]["uncertainty"]["axes"]
    axes += [{"name": "путь 2030", "kind": "value", "paths": [f"{CHANGE}.2030"], "low": -60.0, "high": -20.0,
              "dist": "triangular"},
             {"name": "связка", "kind": "bundle", "paths": [LEVEL, f"{CHANGE}.2029"],
              "low": {LEVEL: 50.0, f"{CHANGE}.2029": -30.0}, "high": {LEVEL: 150.0, f"{CHANGE}.2029": -10.0},
              "dist": "triangular"},
             {"name": "сдвиг пути", "kind": "shift", "paths": [CHANGE], "low": -10.0, "high": 10.0, "dist": "triangular"},
             {"name": "уровень", "kind": "value", "paths": [LEVEL], "low": 80.0, "high": 120.0, "dist": "triangular"}]
    for path, value in changes.items():
        _put(X, path, value)
    return X


def _end_book(X: dict, end: dict) -> dict:
    """Книга-словарь на конце оси-связки: число и ключи траектории — значениями конца (М§10)."""
    out = copy.deepcopy(X)
    for path, value in end.items():
        if path == LEVEL:
            _put(out, LEVEL, value)
        elif path.startswith(CHANGE + "."):
            _get(out, CHANGE)[path[len(CHANGE) + 1:]] = value
    return out


def check_ends_keep_the_fixed_part(before: dict, after: dict, old_anchor: str, period: str, name: str) -> None:
    """Каждый конец связки `name`: постоянная часть каждого квартала после переноса прежняя (число конца + путь конца
    от якоря), в квартале нового якоря приращение конца — ноль (якорное условие на конце)."""
    was = next(a for a in before["valuation"]["uncertainty"]["axes"] if a["name"] == name)
    now = next(a for a in after["valuation"]["uncertainty"]["axes"] if a["name"] == name)
    for end in ("low", "high"):
        b, a = _end_book(before, was[end]), _end_book(after, now[end])
        assert abs(path_value(_get(a, CHANGE), period)) < LEVEL_TOL, (end, path_value(_get(a, CHANGE), period))
        for p in ("2029Q1", "2029Q4", "2030Q1", "2030Q2", "2031Q3", "2036Q4"):
            assert abs(_level_at(a, period, p) - _level_at(b, old_anchor, p)) < LEVEL_TOL, (end, p)


def check_carry(tool: Any) -> None:
    """`carry_fixed_change` (М§15.2 п. 3) на примере H.2: приращение квартала нового якоря −20 — в число (100 → 80),
    траектория — `{2028: 20; 2029: 0; 2030: −20}`; постоянная часть каждого квартала прежняя; концы оси-числа на
    элементе траектории — минус Δ_1, конец оси на числе — плюс Δ_1, концы оси-сдвига прежние; связка на числе и ключе
    2029 года — своим приращением квартала нового якоря (δ = −30 и −10: число конца + δ, путь − δ, ключи центра 2028 и
    2030 — в конец значением «ключ − δ»), постоянная часть каждого квартала на каждом конце прежняя; строка отчёта
    называет Δ_1; при Δ_1 = 0 центр не меняется (связка со своим приращением — переносится), без связки и без ключа
    книга не меняется; у слова `anchor` число не трогается, а без постоянной части в отчёте — предупреждение."""
    g2 = EXAMPLE["fixed_change"]
    old_anchor, period = g2["inputs"]["anchor"], g2["reanchor"]["new_anchor"]
    X, derived, warnings = _g2_book(), {}, []
    before = copy.deepcopy(X)
    tool.carry_fixed_change(X, old_anchor, period, {"balance": {}}, derived, warnings)
    assert _get(X, LEVEL) == g2["reanchor"]["oa_fixed"]
    assert _get(X, CHANGE) == {str(k): v for k, v in g2["reanchor"]["path"].items()}
    for row in g2["reanchor"]["rows"]:
        assert abs(_level_at(X, period, row["period"]) - row["oa_fixed_q_new"]) < LEVEL_TOL, row
        assert abs(_level_at(before, old_anchor, row["period"]) - row["oa_fixed_q_old"]) < LEVEL_TOL, row
    for p in ("2029Q1", "2029Q4", "2030Q2", "2031Q3", "2036Q4"):
        assert abs(_level_at(X, period, p) - _level_at(before, old_anchor, p)) < LEVEL_TOL, p
    assert abs(_level_at(X, period, period) - _get(X, LEVEL)) < LEVEL_TOL          # якорное условие новой книги
    elem, bundle, shift, level = X["valuation"]["uncertainty"]["axes"][-4:]
    assert (elem["low"], elem["high"]) == (-40.0, 0.0)
    assert bundle["paths"] == [LEVEL, f"{CHANGE}.2029", f"{CHANGE}.2028", f"{CHANGE}.2030"]
    assert bundle["low"] == {LEVEL: 20.0, f"{CHANGE}.2029": 0.0, f"{CHANGE}.2028": 30.0, f"{CHANGE}.2030": -10.0}
    assert bundle["high"] == {LEVEL: 140.0, f"{CHANGE}.2029": 0.0, f"{CHANGE}.2028": 10.0, f"{CHANGE}.2030": -30.0}
    check_ends_keep_the_fixed_part(before, X, old_anchor, period, "связка")
    assert (shift["low"], shift["high"]) == (-10.0, 10.0) and (level["low"], level["high"]) == (60.0, 100.0)
    assert derived["fixed_change"]["delta"] == -20.0 and not warnings
    line = tool.fixed_change_line(derived)
    assert "-20.000" in line and LEVEL in line and CHANGE in line and "δ -30.000" in line and "δ -10.000" in line
    # нулевое приращение квартала нового якоря: центр и оси вида value не меняются, связка со своим приращением —
    # переносится; без неё книга не меняется
    X0, d0 = _g2_book(**{CHANGE: {"2028": 0.0, "2029": 0.0, "2030": -40.0}}), {}
    same = copy.deepcopy(X0)
    tool.carry_fixed_change(X0, old_anchor, period, {"balance": {}}, d0, [])
    assert _get(X0, LEVEL) == _get(same, LEVEL) and _get(X0, CHANGE) == _get(same, CHANGE)
    assert [a for a in X0["valuation"]["uncertainty"]["axes"] if a["name"] != "связка"] \
        == [a for a in same["valuation"]["uncertainty"]["axes"] if a["name"] != "связка"]
    assert next(a for a in X0["valuation"]["uncertainty"]["axes"] if a["name"] == "связка")["low"][LEVEL] == 20.0
    check_ends_keep_the_fixed_part(same, X0, old_anchor, period, "связка")
    assert tool.fixed_change_line(d0).startswith("- концы осей-связок")
    X0, d0 = _g2_book(**{CHANGE: {"2028": 0.0, "2029": 0.0, "2030": -40.0}}), {}
    X0["valuation"]["uncertainty"]["axes"] = [a for a in X0["valuation"]["uncertainty"]["axes"] if a["name"] != "связка"]
    same = copy.deepcopy(X0)
    tool.carry_fixed_change(X0, old_anchor, period, {"balance": {}}, d0, [])
    assert X0 == same and tool.fixed_change_line(d0) is None
    # без ключа пути шага нет
    plain, dp = copy.deepcopy(fixture_dict()), {}
    kept = copy.deepcopy(plain)
    tool.carry_fixed_change(plain, old_anchor, period, {"balance": {}}, dp, [])
    assert plain == kept and "fixed_change" not in dp
    # слово anchor: число — в узле фактов отчёта; без него — предупреждение
    for report, warned in (({"balance": {}}, True), ({"balance": {"other_assets_fixed": 80.0}}, False)):
        Xa, wa = _g2_book(**{LEVEL: "anchor"}), []
        tool.carry_fixed_change(Xa, old_anchor, period, report, {}, wa)
        assert _get(Xa, LEVEL) == "anchor" and _get(Xa, CHANGE)["2029"] == 0.0
        assert bool(wa) is warned and (not wa or "balance.other_assets_fixed" in wa[0])


@tact
def test_carry_of_the_path_of_the_fixed_part():
    check_carry(R)


# ------------------------------------------------------------------ клетка на своём пути (фикстура формы образца)


def _book(rubles: bool):
    data = copy.deepcopy(fixture_dict())
    _put(data, LEVEL, 1200.0)
    _put(data, W_FIXED, 0.6)
    _put(data, W_CHANGE, 0.0)
    _put(data, CHANGE, {"2026Q2": 0.0, "2026Q3": -30.0, "2026Q4": -45.0, "2027": -60.0, "2029": -200.0,
                        "LT": -300.0, "LT_from": 2033})
    if rubles:
        _put(data, S20, ETA[0])
        _put(data, S11, ETA[1])
        for i, s in enumerate(data["capital"]["reg_scenarios"]["ids"]):
            data["capital"]["reg_scenarios"][s]["deduction_rub"] = {
                "n20_0": {"2026Q2": 0.0, "2026Q3": -30.0 + 5.0 * i, "2026Q4": -45.0, "2027": -60.0, "LT": -150.0,
                          "LT_from": 2033},
                "n1_1": {"2026Q2": 0.0, "2026Q3": 20.0, "2027": 40.0 - 10.0 * i, "LT": 90.0, "LT_from": 2033}}
    return book_from_dict(data, facts=fixture_facts())


@lru_cache(maxsize=None)
def scene(rubles: bool) -> SimpleNamespace:
    return _scene(_book(rubles), fixture_facts())


CELLS = (("N", "soft", "schedule"), ("M", "crisis", "strict"))


@pytest.mark.parametrize("key", CELLS, ids=lambda k: "/".join(k))
def test_a_cell_reanchored_on_its_own_path_keeps_the_fixed_part_and_the_ratio_function(key):
    """Клетка, перезаякоренная на своём пути (М§15.2 п. 3): постоянная часть прочих активов каждого квартала прежняя
    (число нового якоря — прежнее плюс приращение квартала нового якоря, путь — от нового якоря, кандидат проходит
    якорное условие), прочие активы клетки кандидата — ряд прежней клетки; рубли сценария перенесены как есть, и
    норматив кандидата в каждом квартале равен формуле прежней книги на его рядах с точностью до одной постоянной."""
    s = scene(True)
    c = _carried(R, key, s=s)
    old, new = s.book, c.cand.book
    period = c.cand.period
    delta = path_value(old.get(CHANGE), period) - path_value(old.get(CHANGE), str(old.get("meta.anchor_period")))
    assert delta == -30.0 and c.cand.derived["fixed_change"]["delta"] == delta
    assert float(new.get(LEVEL)) == 1200.0 + delta and path_value(new.get(CHANGE), period) == 0.0
    tl = c.run.ctx.timeline
    for q in range(tl.Q + 1):
        p = tl.period(q)
        was = 1200.0 + path_value(old.get(CHANGE), p)
        now = float(new.get(LEVEL)) + path_value(new.get(CHANGE), p) - path_value(new.get(CHANGE), tl.period(0))
        assert abs(now - was) < LEVEL_TOL, (p, now, was)
        assert abs(c.cell.quarters["other_assets"][q] / c.old.quarters["other_assets"][q + 1] - 1) < 1e-6, (key, p)
    for sc in old.get("capital.reg_scenarios.ids"):                  # рубли сценария — как есть
        assert new.get(f"capital.reg_scenarios.{sc}.deduction_rub") == old.get(f"capital.reg_scenarios.{sc}.deduction_rub")
    # функция норматива прежней книги на рядах кандидата (рубли — траектория по периодам)
    ded20_0, ded11_0 = float(old.get(D20)), float(old.get(D11))
    rwa0 = float(c.old.quarters["rwa"][0])
    f = float(old.get("capital.n20.fvoci_recognition"))
    at1 = c.run.ctx.prep.af.at1
    q_ = c.cell.quarters
    sc = c.cell.scenario
    node = old.get(f"capital.reg_scenarios.{sc}.deduction_rub")
    offs20, offs11 = [], []
    for q in range(tl.Q + 1):
        p = tl.period(q)
        rwa = q_["rwa"][q]
        d20 = (1 - ETA[0]) * ded20_0 * rwa / rwa0 + ETA[0] * ded20_0 + path_value(node["n20_0"], p)
        d11 = (1 - ETA[1]) * ded11_0 * rwa / rwa0 + ETA[1] * ded11_0 + path_value(node["n1_1"], p)
        bvreg = q_["bv"][q] + q_["dpreg"][q] - (1 - f) * q_["reserve"][q]
        dpp = {n: path_value(new.get(f"capital.reg_scenarios.{sc}.deduction_pp.{n}"), p) for n in ("n20_0", "n1_1")}
        t2 = path_value(new.get("capital.n20.t2"), p)
        offs20.append(q_["n20"][q] - ((bvreg - d20 + at1 + t2) / rwa + float(old.get(G20)) - dpp["n20_0"]))
        e = q_["e_unaudited"][q]
        if e is not None and q_["n11"][q] is not None:
            offs11.append(q_["n11"][q] - ((bvreg - max(e, 0.0) - d11) / rwa + float(old.get(G11)) - dpp["n1_1"]))
    for offs in (offs20, offs11):
        assert abs(offs[0]) < OFFSET_TOL, offs[0]
        assert max(abs(x - offs[0]) for x in offs) < NORM_TOL, max(abs(x - offs[0]) for x in offs)
    # гасит ли перенос рубли нового якоря: в поправке кандидата — Drub_1 / RWA_1 (и остаток записи)
    rub1 = path_value(node["n20_0"], period)
    assert abs(float(new.get(G20)) - float(old.get(G20)) - rub1 / c.old.quarters["rwa"][1]) < 5e-6


def test_a_book_without_the_step_refuses_loudly():
    """Без шага инструмента книга с ненулевым приращением квартала нового якоря не проходит якорное условие — отказ
    схемы, а не тихий сдвиг (М§15.2 п. 3)."""
    s = scene(False)
    tool = mutant_tool("    carry_fixed_change(X, old_anchor, period, report, derived, warnings)\n", "")
    with pytest.raises(Exception, match="квартале якоря"):
        _carried(tool, CELLS[0], s=s)


# ------------------------------------------------------------------ мутации инструмента


TOOL_MUTATIONS: tuple[tuple[str, str, str, str, Callable[[Any], None]], ...] = (
    ("F1", "приращение квартала нового якоря не перенесено в число постоянной части",
     "        now = _r(float(level or 0.0) + delta, FIXED_DIGITS)\n",
     "        now = _r(float(level or 0.0), FIXED_DIGITS)\n", check_carry),
    ("F2", "траектория приращений не сдвинута",
     "    move = lambda v: _r(float(v) - delta, FIXED_DIGITS)  # noqa: E731\n",
     "    move = lambda v: _r(float(v), FIXED_DIGITS)  # noqa: E731\n", check_carry),
    ("F3", "конец связки и оси на числе постоянной части не идёт за центром",
     "    up = lambda v: _r(float(v) + delta, FIXED_DIGITS)  # noqa: E731  (конец оси на числе постоянной части)\n",
     "    up = lambda v: _r(float(v), FIXED_DIGITS)  # noqa: E731  (конец оси на числе постоянной части)\n", check_carry),
    ("F4", "приращение — от нуля, а не от значения квартала прежнего якоря",
     "    delta = t.value(*parse_period(period)) - t.value(*parse_period(old_anchor))\n",
     "    delta = t.value(*parse_period(period))\n",
     lambda tool: check_carry_with_residual(tool)),
)


def check_carry_with_residual(tool: Any) -> None:
    """Приращение нового якоря — разность значений траектории в кварталах нового и прежнего якоря (ядро читает
    `v(q) − v(0)`): остаток записи в квартале прежнего якоря в пределах порога в число не уходит."""
    check_carry(tool)
    g2 = EXAMPLE["fixed_change"]
    X, d = _g2_book(**{CHANGE: {"2028": 5e-10, "2029": -20.0, "2030": -40.0}}), {}
    tool.carry_fixed_change(X, g2["inputs"]["anchor"], g2["reanchor"]["new_anchor"], {"balance": {}}, d, [])
    assert d["fixed_change"]["delta"] == -20.0 - 5e-10


@pytest.mark.parametrize("mutation", TOOL_MUTATIONS, ids=lambda m: m[0])
def test_every_mutation_of_the_tool_is_caught(mutation):
    ident, title, find, replace, check = mutation
    tool = mutant_tool(find, replace)
    try:
        check(tool)
    except AssertionError:
        return
    pytest.fail(f"мутация инструмента {ident} «{title}» не поймана")


@tact
def test_targets_of_the_tool_mutations_exist_and_the_genuine_tool_passes():
    source = TOOL.read_text(encoding="utf-8")
    for ident, _, find, _, _ in TOOL_MUTATIONS:
        assert source.count(find) == 1, ident
    check_carry_with_residual(R)
