# -*- coding: utf-8 -*-
"""Перезаякоривание: концы осей-связок и подмены справочных вариантов на пути постоянной части прочих активов
(`ops/tools/reanchor.py::fixed_ends`, `carry_fixed_ends`, `carry_end_densities`; М§4.3, §10, §14.5, §15.2 п. 3;
docs/REANCHOR.md §3.3, §3.13, §3.15).

Конец связки, которая ведёт путь `volumes.other_assets_fixed_change` или число `volumes.other_assets_fixed`, и подмена
справочного варианта на них переносятся тем же правилом, что центр, со СВОИМ приращением квартала нового якоря δ
(значение траектории конца в квартале нового якоря минус в квартале прежнего): число конца + δ, каждое значение его
траектории − δ, плотность ω_oaf — формулой шестого прохода со своими L и δ. Проверки — тождества, выведенные из книги
независимо от кода инструмента: на каждом конце и в каждом варианте постоянная часть каждого квартала сетки и её RWA
прежние (RWA — с точностью до общего множителя плотностей), в квартале нового якоря приращение — ноль, кандидат и
книги вариантов проходят схему ядра на новом якоре. Конец без своего числа получает его (у связки — путь на обоих
концах); ключи центра, которых конец не нёс, — значением «ключ − δ», когда без них траектория конца разошлась бы со
своей. Число словом `anchor` своего числа концу не даёт: связка — отказ, вариант — запись на прежнем якоре с
предупреждением. Ось вида `value` на ключе пути со своим приращением — отказ.

Фикстура — форма образца `tests/fixtures/core` с путём постоянной части (как `tests/test_reanchor_fixed_change.py`),
двумя связками (доля постоянной части — число, плотность и ключи; рост — только ключи) и вариантами. Настоящая книга —
строка теста `tests/test_reanchor.py::test_the_real_book_reanchors_on_its_expected_report` (`check_real_candidate`
этого файла) и цепочка «якорь 3К → якорь 4К» (`ci_only`): без взноса — механика в допуске, с решением о взносе в 4-м
квартале — отказ §3.16. Мутации инструмента (`TOOL_MUTATIONS`) — правка исходного текста (`mutant_tool` файла
`tests/test_reanchor_shares.py`): каждую роняет проверка этого файла.
"""
from __future__ import annotations

import copy
from functools import lru_cache
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from model.book import book_from_dict
from model.book_schema import validate
from model.paths import path_value
from tests.support_core import fixture_dict, fixture_facts, real_book_or_skip
from tests.test_reanchor import R
from tests.test_reanchor_shares import TOOL, _scene, mutant_tool

tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

LEVEL, CHANGE = "volumes.other_assets_fixed", "volumes.other_assets_fixed_change"
W_FIXED, W_CHANGE = "capital.rwa.density.other_assets_fixed", "capital.rwa.density.other_assets_fixed_change"
OLD, NEW, LAST = "2026Q2", "2026Q3", "2036Q4"
Q3, Q4, Y27 = (f"{CHANGE}.{k}" for k in ("2026Q3", "2026Q4", "2027"))
PATH = {"2026Q2": 0.0, "2026Q3": -30.0, "2026Q4": -45.0, "2027": -60.0, "2029": -200.0, "LT": -300.0, "LT_from": 2033}
SHARE = {"name": "доля постоянной части", "kind": "bundle", "dist": "triangular",
         "paths": [LEVEL, W_FIXED, Q3, Q4, Y27],
         "low": {LEVEL: 900.0, W_FIXED: 0.7, Q3: -20.0, Q4: -30.0, Y27: -40.0},
         "high": {LEVEL: 1500.0, W_FIXED: 0.5, Q3: -40.0, Q4: -60.0, Y27: -80.0}}
GROWTH = {"name": "рост пути", "kind": "bundle", "dist": "triangular", "paths": [Q3, Q4],
          "low": {Q3: 0.0, Q4: 0.0}, "high": {Q3: -60.0, Q4: -90.0}}
VARIANTS = [
    {"id": "path_flat", "title": "путь без роста до 2029 года",
     "overrides": {CHANGE: {"2026Q2": 0.0, "2026Q3": 0.0, "2026Q4": 0.0, "2027": 0.0, "2029": -140.0, "LT": -240.0,
                            "LT_from": 2033}}},
    {"id": "path_double", "title": "рост пути вдвое",
     "overrides": {CHANGE: {"2026Q2": 0.0, "2026Q3": -60.0, "2026Q4": -90.0, "2027": -120.0, "2029": -260.0,
                            "LT": -360.0, "LT_from": 2033}}},
    {"id": "key_q3", "title": "ключ квартала нового якоря", "overrides": {Q3: -10.0}},
    {"id": "level_only", "title": "только число", "overrides": {LEVEL: 1000.0}},
    {"id": "level_density_key", "title": "число, плотность и ключ", "overrides": {LEVEL: 1000.0, W_FIXED: 0.8, Q3: -50.0}},
    {"id": "own_weight", "title": "свой вес приращения", "overrides": {W_CHANGE: 0.4, Q3: -20.0}},
    {"id": "density_only", "title": "только плотность", "overrides": {W_FIXED: 0.9}},
]
FIXED_TOL = 1e-9        # млрд ₽: постоянная часть квартала (число и путь — 9 знаков)
RWA_DICT_TOL = 1e-8     # млрд ₽: RWA постоянной части на словаре (плотность — 12 знаков)
RWA_SCENE_TOL = 2e-3    # то же у кандидата: плотности после общего множителя — 6 знаков (≈ 5e-7 × 1500)


def _get(tree: Any, dotted: str) -> Any:
    return R._get(tree, dotted)


def _book_dict(*, w_change: float | None = 0.0, level: Any = 1200.0, bundles: tuple = (SHARE, GROWTH),
               variants: list | None = None, axes: tuple = ()) -> dict:
    X = copy.deepcopy(fixture_dict())
    R._set(X, LEVEL, level)
    R._set(X, W_FIXED, 0.6)
    if w_change is not None:
        R._set(X, W_CHANGE, w_change)
    R._set(X, CHANGE, dict(PATH))
    X["valuation"]["uncertainty"]["axes"] += copy.deepcopy(list(bundles) + list(axes))
    X["valuation"]["reference_variants"] = copy.deepcopy(VARIANTS if variants is None else variants)
    return X


def _carry(tool: Any, X: dict, report: dict | None = None) -> tuple[dict, list[str]]:
    derived, warnings = {}, []
    tool.carry_fixed_change(X, OLD, NEW, report or {"balance": {}}, derived, warnings)
    tool.carry_fixed_density(X, derived, warnings)
    return derived, warnings


def _grid() -> list[str]:
    return [R.period_str(*R.shift_quarter(*R.parse_period(NEW), i)) for i in range(R.pindex(LAST) - R.pindex(NEW) + 1)]


def _state(X: dict, subs: dict, anchor: str, q: str) -> tuple[float, float]:
    """(постоянная часть, её RWA) квартала q у книги-словаря X с подменами конца или варианта (М§4.3, §4.11): число и
    плотности — подменой, траектория — центр с ключами подмены или подмена целиком; приращение — от квартала якоря."""
    level = float(subs.get(LEVEL, _get(X, LEVEL)))
    traj = copy.deepcopy(_get(X, CHANGE))
    for path, value in subs.items():
        if path == CHANGE:
            traj = copy.deepcopy(value)
        elif path.startswith(CHANGE + "."):
            traj[path[len(CHANGE) + 1:]] = value
    dens = X["capital"]["rwa"]["density"]
    w = float(subs.get(W_FIXED, dens["other_assets_fixed"]))
    wd = subs.get(W_CHANGE, dens.get("other_assets_fixed_change"))
    inc = path_value(traj, q) - path_value(traj, anchor)
    return level + inc, w * level + (w if wd is None else float(wd)) * inc


def _anchor_value(X: dict, subs: dict, anchor: str) -> float:
    traj = copy.deepcopy(_get(X, CHANGE))
    for path, value in subs.items():
        if path == CHANGE:
            traj = copy.deepcopy(value)
        elif path.startswith(CHANGE + "."):
            traj[path[len(CHANGE) + 1:]] = value
    return path_value(traj, anchor)


def _on_path(paths: Any) -> bool:
    return any(p == LEVEL or p.startswith(CHANGE) for p in paths)


def _carriers(X: dict) -> dict[str, dict]:
    """Концы связок и варианты на пути постоянной части или её числе: {имя: подмены}. Вариант только на плотности
    (не на пути) — суждение книги на прежнем якоре: его называет ручной шаг, как любую подмену переписанного ключа."""
    out = {}
    for axis in X["valuation"]["uncertainty"]["axes"]:
        if axis.get("kind") == "bundle" and _on_path(axis["paths"]):
            out[f"{axis['name']}.low"], out[f"{axis['name']}.high"] = axis["low"], axis["high"]
    for v in X["valuation"].get("reference_variants") or []:
        if _on_path(v["overrides"]):
            out[f"вариант {v['id']}"] = v["overrides"]
    return out


def check_kept(before: dict, after: dict, k: float = 1.0, rwa_tol: float = RWA_DICT_TOL,
               old: str = OLD, new: str = NEW) -> None:
    """Центр, каждый конец связки и каждый вариант: в квартале нового якоря приращение — ноль; постоянная часть каждого
    квартала сетки прежняя, её RWA — прежняя, умноженная на общий множитель плотностей k."""
    was, now = _carriers(before), _carriers(after)
    assert set(was) == set(now)
    for name, subs in [("центр", None)] + list(now.items()):
        a, b = ({}, {}) if subs is None else (was[name], subs)
        assert abs(_anchor_value(after, b, new)) < FIXED_TOL, (name, _anchor_value(after, b, new))
        for q in _grid():
            (l0, r0), (l1, r1) = _state(before, a, old, q), _state(after, b, new, q)
            assert abs(l1 - l0) < FIXED_TOL, (name, q, l0, l1)
            assert abs(r1 - k * r0) < rwa_tol, (name, q, r0, r1)


def _on_new_anchor(X: dict) -> dict:
    Y = copy.deepcopy(X)
    Y["meta"].update(anchor_period=NEW, first_period=R.next_period(NEW))
    return Y


def check_schema(X: dict) -> None:
    """Книга-словарь на новом якоре и книга каждого варианта проходят схему ядра (якорное условие на каждом конце)."""
    Y = _on_new_anchor(X)
    validate(Y)
    for v in Y["valuation"]["reference_variants"]:
        Z = copy.deepcopy(Y)
        for path, value in v["overrides"].items():
            R._set(Z, path, copy.deepcopy(value))
        validate(Z)


# ------------------------------------------------------------------ шаг инструмента на словаре книги


def check_ends(tool: Any) -> None:
    """Связки и варианты фикстуры при Δ_1 = −30 (ω_Δ = 0 и 0,2): своё приращение конца (доля — δ −20 / −40, рост —
    0 / −60, ключ квартала — −10, путь целиком — 0 / −60, число — −30), число конца + δ, путь − δ; связка роста без
    числа получает число и ключи центра на обоих концах, вариант на ключе — число и ключи; плотность — своими L и δ;
    постоянная часть и её RWA каждого квартала прежние на каждом конце; книга на новом якоре и варианты проходят схему;
    прежняя книга без шага — нет."""
    for w_change in (0.0, 0.2):
        X = _book_dict(w_change=w_change)
        validate(X)
        before = copy.deepcopy(X)
        with pytest.raises(Exception, match="квартале якоря"):
            validate(_on_new_anchor(before))
        derived, warnings = _carry(tool, X)
        assert not warnings, warnings
        check_kept(before, X)
        check_schema(X)
        share, growth = X["valuation"]["uncertainty"]["axes"][-2:]
        # ключи 2029 и LT центр сдвинул на Δ_1, а концу доли нужен свой δ: они входят в связку (и ключ 2026Q2)
        assert share["paths"] == SHARE["paths"] + [f"{CHANGE}.{k}" for k in ("2026Q2", "2029", "LT")]
        assert share["low"][LEVEL] == 880.0 and share["low"][Q3] == 0.0 and share["low"][Q4] == -10.0
        assert share["high"][LEVEL] == 1460.0 and share["high"][Y27] == -40.0
        assert (share["low"][f"{CHANGE}.2029"], share["high"][f"{CHANGE}.LT"]) == (-180.0, -260.0)
        want = (0.7 * 900.0 + w_change * -20.0) / 880.0
        assert abs(share["low"][W_FIXED] - want) <= 1e-12, (share["low"][W_FIXED], want)
        assert growth["paths"][:3] == [Q3, Q4, LEVEL] and growth["paths"][-1] == W_FIXED
        assert set(growth["paths"]) == {Q3, Q4, LEVEL, W_FIXED} | {f"{CHANGE}.{k}" for k in ("2026Q2", "2027", "2029", "LT")}
        assert (growth["low"][LEVEL], growth["high"][LEVEL]) == (1200.0, 1140.0)
        assert growth["low"][f"{CHANGE}.2029"] == -200.0 and growth["high"][f"{CHANGE}.2029"] == -140.0
        ov = {v["id"]: v["overrides"] for v in X["valuation"]["reference_variants"]}
        assert ov["key_q3"][LEVEL] == 1190.0 and ov["key_q3"][Q3] == 0.0 and ov["key_q3"][f"{CHANGE}.2027"] == -50.0
        assert ov["level_only"][LEVEL] == 970.0 and W_FIXED in ov["level_only"]
        assert ov["path_flat"][LEVEL] == 1200.0 and ov["path_flat"][CHANGE]["2029"] == -140.0
        assert LEVEL not in ov["own_weight"] or ov["own_weight"][LEVEL] == 1180.0
        assert ov["density_only"] == {W_FIXED: 0.9}                       # вариант не на пути — не трогается
        assert derived["fixed_change"]["delta"] == -30.0
        assert tool.carried_variants(derived) == [v["id"] for v in VARIANTS if v["id"] != "density_only"]
        line = tool.fixed_change_line(derived)
        assert "δ -20.000" in line and "«рост пути»" in line and "«key_q3»" in line
    # прежняя книга и шаг с нулевым Δ_1 у связки и варианта со своим приращением: центр прежний, концы — перенесены
    X = _book_dict(bundles=(GROWTH,), variants=[VARIANTS[2]])
    X["volumes"]["other_assets_fixed_change"] = {"2026Q2": 0.0, "2026Q3": 0.0, "2026Q4": -45.0, "2027": -60.0,
                                                 "2029": -200.0, "LT": -300.0, "LT_from": 2033}
    before = copy.deepcopy(X)
    derived, _ = _carry(tool, X)
    assert derived["fixed_change"]["delta"] == 0.0 and _get(X, CHANGE) == _get(before, CHANGE)
    assert _get(X, LEVEL) == 1200.0 and X["valuation"]["uncertainty"]["axes"][-1]["high"][LEVEL] == 1140.0
    check_kept(before, X)
    check_schema(X)


def check_word_and_value_axis(tool: Any) -> None:
    """Число словом `anchor`: связка, концу которой нужно своё число, — отказ с причиной; вариант — предупреждение, его
    подмены прежние, в перечне перенесённых его нет. Ось вида `value` на ключе квартала нового якоря (своё приращение
    конца ≠ Δ_1) — отказ; на ключе, который значение квартала нового якоря не задаёт, — прежнее правило (минус Δ_1)."""
    X = _book_dict(level="anchor", bundles=(GROWTH,), variants=[])
    with pytest.raises(tool.ReportError, match="словом anchor"):
        _carry(tool, X, {"balance": {"other_assets_fixed": 1170.0}})
    X = _book_dict(level="anchor", bundles=(), variants=[VARIANTS[2]])
    before = copy.deepcopy(X)
    derived, warnings = _carry(tool, X, {"balance": {"other_assets_fixed": 1170.0}})
    assert X["valuation"]["reference_variants"] == before["valuation"]["reference_variants"]
    assert any("key_q3" in w and "словом anchor" in w for w in warnings), warnings
    assert tool.carried_variants(derived) == [] and "не перенесён" in tool.fixed_change_line(derived)
    on_q3 = {"name": "ключ квартала", "kind": "value", "paths": [Q3], "low": -40.0, "high": -20.0, "dist": "triangular"}
    with pytest.raises(tool.ReportError, match="ось вида value"):
        _carry(tool, _book_dict(bundles=(), variants=[], axes=(on_q3,)))
    flat = _book_dict(bundles=(), variants=[], axes=({**on_q3, "low": -20.0, "high": 20.0},))
    flat["volumes"]["other_assets_fixed_change"]["2026Q3"] = 0.0          # Δ_1 = 0, а конец оси — своё приращение
    with pytest.raises(tool.ReportError, match="ось вида value"):
        _carry(tool, flat)
    on_q4 = {**on_q3, "name": "ключ 4К", "paths": [Q4], "low": -60.0, "high": -30.0}
    X = _book_dict(bundles=(), variants=[], axes=(on_q4,))
    _carry(tool, X)
    assert (X["valuation"]["uncertainty"]["axes"][-1]["low"], X["valuation"]["uncertainty"]["axes"][-1]["high"]) \
        == (-30.0, 0.0)


def check_variant_densities_follow_the_factor(tool: Any) -> None:
    """Подмены плотностей постоянной части у вариантов на её пути идут за общим множителем плотностей (как концы
    осей); вариант не на пути — прежний."""
    X = _book_dict(bundles=(), variants=[VARIANTS[4], VARIANTS[5], VARIANTS[6]])
    k = tool.calibrate_capital(X, fixture_facts(), 1.2e4, {}, [])
    ov = {v["id"]: v["overrides"] for v in X["valuation"]["reference_variants"]}
    assert abs(k - 1) > 1e-3
    assert ov["level_density_key"][W_FIXED] == round(0.8 * k, 6) and ov["own_weight"][W_CHANGE] == round(0.4 * k, 6)
    assert ov["density_only"][W_FIXED] == 0.9
    assert X["capital"]["rwa"]["density"]["other_assets_fixed"] == round(0.6 * k, 6)


@tact
def test_the_ends_of_bundles_and_the_variants_on_the_path_carry_their_own_increment():
    check_ends(R)


@tact
def test_a_word_anchor_and_a_value_axis_on_the_anchor_key_are_named():
    check_word_and_value_axis(R)


@tact
def test_densities_of_the_variants_on_the_path_follow_the_factor():
    check_variant_densities_follow_the_factor(R)


# ------------------------------------------------------------------ кандидат на ожидаемом отчёте (фикстура)


@lru_cache(maxsize=None)
def fixture_scene() -> SimpleNamespace:
    book = book_from_dict(_book_dict(w_change=0.2), facts=fixture_facts())
    s = _scene(book, fixture_facts())
    s.expected = R.expected_report(book, s.facts, run=s.run_plus)
    return s


def check_candidate(tool: Any) -> None:
    """Кандидат на ожидаемом отчёте книги со связками и вариантами на пути: схема ядра его принимает (книга-кандидат и
    книги перенесённых вариантов); на каждом конце и в каждом варианте постоянная часть каждого квартала прежняя, RWA —
    прежняя, умноженная на множитель плотностей кандидата; «что сдвинулось» называет концы и варианты своей причиной."""
    s = fixture_scene()
    cand = tool.reanchor(s.book, s.facts, s.expected, valuation_date=s.v, base_run=s.run_plus)
    assert str(cand.book.get("meta.anchor_period")) == NEW
    check_kept(dict(s.book.source), cand.data, k=cand.derived["rwa_factor"], rwa_tol=RWA_SCENE_TOL)
    for v in cand.data["valuation"]["reference_variants"]:
        cand.book.with_overrides(dict(v["overrides"]), create=True)
    reasons = {tool.dotted(p): tool.reason(tool.dotted(p), cand.derived) for p, _, _ in cand.changes}
    assert any(p.startswith("valuation.reference_variants[key_q3]") and "своим приращением" in r
               for p, r in reasons.items()), reasons
    assert any("«рост пути»" not in p and "[рост пути]" in p and "своим приращением" in r
               for p, r in reasons.items() if p.endswith(LEVEL)), reasons
    named = [w for w in cand.warnings if w.startswith("справочные варианты")]
    assert not any("key_q3" in w for w in named) and any("«density_only»" in w for w in named), named


def test_the_candidate_with_bundles_and_variants_on_the_path_passes_the_schema():
    check_candidate(R)


def test_without_the_step_for_the_ends_the_candidate_is_refused_loudly():
    """Без переноса концов своим приращением кандидат не проходит якорное условие на концах — отказ схемы, а не
    тихий сдвиг (М§4.3, прил. A № 24)."""
    s = fixture_scene()
    tool = mutant_tool('    row["ends"] = carry_fixed_ends(X, ends, center, level, delta, period, warnings)\n    row["path_now"]',
                       '    row["path_now"]')
    with pytest.raises(Exception, match="квартале якоря"):
        tool.reanchor(s.book, s.facts, s.expected, valuation_date=s.v, base_run=s.run_plus)


# ------------------------------------------------------------------ настоящая книга (ci_only)


def check_real_candidate(book: Any, cand: Any) -> None:
    """Строка теста настоящей книги: концы связок и варианты на пути постоянной части перенесены своим приращением —
    постоянная часть и её RWA каждого квартала прежние (RWA — с множителем плотностей), книги вариантов проходят схему."""
    if book.opt(CHANGE) is None:
        return
    check_kept(dict(book.source), cand.data, k=cand.derived["rwa_factor"], rwa_tol=RWA_SCENE_TOL,
               old=str(book.get("meta.anchor_period")), new=str(cand.book.get("meta.anchor_period")))
    for v in cand.data["valuation"].get("reference_variants") or []:
        cand.book.with_overrides(dict(v["overrides"]), create=True)


def _dry_step(book: Any, facts: Any, cells: bool = True) -> SimpleNamespace:
    """Шаг сухого прогона (REANCHOR §1.1): ожидаемый отчёт первого прогнозного квартала, кандидат на нём и строка
    «механика» по клеткам (код 0 команды — механика в допуске)."""
    first = str(book.get("meta.first_period"))
    v = R.period_end(first) + R.dt.timedelta(days=2)
    _, run_plus, obs = R.expected_run(book, facts, R.live_at(book, facts, v))
    expected = R.expected_report(book, facts, run=run_plus)
    cand = R.reanchor(book, facts, expected, valuation_date=v, base_run=run_plus)
    mech = R.cell_mechanics(book, facts, run_plus, obs, v) if cells else None
    return SimpleNamespace(book=book, facts=facts, v=v, run_plus=run_plus, cand=cand, mech=mech, period=first)


@ci_only
def test_the_real_book_walks_third_to_fourth_quarter():
    """Цепочка «якорь 3К2026 → якорь 4К2026» настоящей книги (REANCHOR §1.1, §3.16): книга без взноса
    (`capital.recapitalization.enabled: false`) — оба шага в допуске механики по клеткам и точке, концы связок и
    варианты на пути постоянной части на обоих шагах перенесены своим приращением; книга как есть (решение о взносе в
    4-м квартале) — шаг 3К проходит, шаг 4К — отказ с причиной §3.16."""
    book, facts = real_book_or_skip()
    if book.opt(CHANGE) is None:
        pytest.skip("книга без пути постоянной части")
    plain = book.with_overrides({"capital.recapitalization.enabled": False})
    first = _dry_step(plain, facts)
    assert first.mech["ok"], first.mech["worst"]
    check_real_candidate(plain, first.cand)
    second = _dry_step(first.cand.book, first.cand.facts)
    assert second.period == "2026Q4" and second.mech["ok"], second.mech["worst"]
    check_real_candidate(first.cand.book, second.cand)
    step = _dry_step(book, facts, cells=False)
    with pytest.raises(R.ReportError, match="квартал решения о взносе"):
        _dry_step(step.cand.book, step.cand.facts, cells=False)


# ------------------------------------------------------------------ мутации инструмента


TOOL_MUTATIONS: tuple[tuple[str, str, str, str, Callable[[Any], None]], ...] = (
    ("E1", "конец связки и вариант перенесены приращением центра, а не своим",
     '            d, tab = e["delta"], e["table"]\n', '            d, tab = delta, e["table"]\n', check_ends),
    ("E2", "конец без своего числа его не получает",
     "        if lone:                                 # своё число концу: L + δ (у связки — на обоих концах)\n",
     "        if False:\n", check_ends),
    ("E3", "ключи центра, которых конец не несёт, в конец не входят",
     "            if off:                              # ключи центра, которых конец не несёт, — в конец: ключ − δ\n",
     "            if False:\n", check_ends),
    ("E4", "плотность концов — приращением центра, а не своим",
     '            now = float(w) if wd is None else _r(carried_density(float(w), float(wd), big_l, e["delta"]), '
     'DENSITY_DIGITS)\n',
     '            now = float(w) if wd is None else _r(carried_density(float(w), float(wd), big_l, row["delta"]), '
     'DENSITY_DIGITS)\n', check_ends),
    ("E5", "конец без своей плотности её не получает",
     "        if not any(own) and all(_num(center_now) and abs(t - float(center_now)) <= 1e-12 for t in targets):\n",
     "        if not any(own):\n", check_ends),
    ("E6", "варианты на пути не переносятся",
     "        if isinstance(ov, dict) and any(_on_fixed_path(str(p)) for p in ov):\n            groups.append(",
     "        if False:\n            groups.append(", check_ends),
    ("E7", "число словом anchor у связки — без отказа",
     '                raise ReportError(f"ось-связка {text} (решение книги: число постоянной части числом или концы на новом "\n',
     '                print(f"ось-связка {text} (решение книги: число постоянной части числом или концы на новом "\n',
     check_word_and_value_axis),
    ("E8", "ось вида value на ключе квартала нового якоря — без отказа",
     "            if abs(own - delta) > END_TOL:\n                raise ReportError(\n",
     "            if False:\n                raise ReportError(\n", check_word_and_value_axis),
    ("E9", "подмены плотностей вариантов на пути не идут за общим множителем",
     "                    ov[path] = _r(float(ov[path]) * k_rwa, 6)\n", "                    ov[path] = _r(float(ov[path]), 6)\n",
     check_variant_densities_follow_the_factor),
)


@pytest.mark.parametrize("mutation", TOOL_MUTATIONS, ids=lambda m: m[0])
def test_every_mutation_of_the_carry_of_the_ends_is_caught(mutation):
    """Каждую ошибку переноса концов и вариантов роняет проверка этого файла; подлинный инструмент её проходит."""
    ident, title, find, replace, check = mutation
    tool = mutant_tool(find, replace)
    try:
        check(tool)
    except (AssertionError, pytest.fail.Exception):
        return
    pytest.fail(f"мутация инструмента {ident} «{title}» не поймана")


@tact
def test_targets_of_the_carry_of_the_ends_mutations_exist():
    source = TOOL.read_text(encoding="utf-8")
    assert len({m[0] for m in TOOL_MUTATIONS}) == len(TOOL_MUTATIONS)
    for ident, _, find, _, _ in TOOL_MUTATIONS:
        assert source.count(find) == 1, ident
