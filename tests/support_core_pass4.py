"""Проверки четвёртого прохода ядра (строки «Аналитические тесты печати, сверки и инструментов четвёртого прохода»
и «Мутации четвёртого прохода» М§18): узел числа гейта `capital.capital_gap`, разброс цены по осям сетки (правило
образца и последовательное, ключ `checks.grid_variance`), печать DPS при оборванных путях акций и делители строк,
делитель DPS нау-каста; непойманные мутации второй проверки — норма доли терминала при закрытом квартале взноса,
гейт знака стресса и клетка нулевой вероятности, тройки клеток в контракте, знаменатель DPS политики; схема ключей
доли вычета якоря (`null`, слово `anchor` у каждого ключа), ноль без знака в выпуске, счётчики сводки контрольной
модели.

Фикстуры — формы образца `tests/fixtures/core` (с четвёртым сценарием — `tests/support_core_pass2.py`, с
докапитализацией — `tests/support_core_recap.py`) с подменами теста; общий пример — приложение G методики,
машинная копия `tests/fixtures/core_pass4/example.json`. Каждая проверка — тождество или закрытая формула,
выведенная из книги, фактов и рядов клеток независимо от кода ядра: доли разброса — своим счётом условных средних и
остатка, обрыв пути — по кварталу обрыва пути акций, делители — по числу акций клетки перед собранием. Те же
функции зовут тесты `tests/test_core_pass4.py` и мутационный набор `tests/mutations.py`.
"""

from __future__ import annotations

import copy
import json
import math
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from model.book import book_from_dict
from model.book_schema import BookError
from model.cell import own_year_dps
from model.grid import point_probabilities, run_grid, stress_sign_test
from model.levels import dps_split, point_path, recap_node
from model.timeline import period_str
from tests import support_core_pass2 as S2
from tests import support_core_recap as RC
from tests.support_core import fixture_book, fixture_dict, fixture_facts

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE: dict[str, Any] = json.loads((ROOT / "tests" / "fixtures" / "core_pass4" / "example.json")
                                     .read_text(encoding="utf-8"))
TOL = 1e-9                                   # допуск примера приложения G (М§17)
KEY = "checks.grid_variance"
SEQ = {KEY: "sequential"}
S20, S11 = "capital.n20.deductions_fixed_share", "capital.n11.deductions_fixed_share"
# разрыв к полу и в клетках нулевой вероятности кризиса; норматив смеси при таком убытке отстоит от ожидания нормативов
# клеток дальше обычного допуска сверки — допуск ключом книги (П§7 п. 10)
LOSS = {"regimes.crisis.one_off_loss.amount": -5000.0, "checks.mix_ratio_tolerance": 0.005}
# фикстура печати DPS: решение о взносе в 4-м квартале, окно 1, поправка делителя 0,25 и убыток кризиса, обрывающий
# путь акций трёх клеток мира M (М§6.6)
# (таблица сценариев фикстуры разная по режимам: правило разброса цены — ключом книги, М§3.4)
DPS_BOOK = {**S2.keyed(4, 1), **RC.DEEP_LOSS, "valuation.share_count_adj": 0.25, **SEQ}


def close(a: float, b: float, rel: float = 1e-9, abs_: float = 1e-9) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def _cells_of(table: Mapping[str, Any]) -> dict[tuple[str, str, str], float]:
    return {tuple(k.split("/")): float(v) for k, v in table.items()}


# ====================================================================== узел числа гейта (М§3.4)


@lru_cache(maxsize=None)
def _gap_release():
    """Выпуск книги с четвёртым сценарием (вес только в кризисе) и убытком кризиса: разрыв к полу стоит и в клетках
    нулевой вероятности режима кризиса."""
    return S2.fast_release(S2.four_scenarios_book({**LOSS, **SEQ}, own=True))


def check_capital_gap_node_counts_like_the_gate() -> None:
    """Узел `capital.capital_gap` считает клетки, как гейт (М§3.4, П§7 п. 10): число клеток с разрывом, их перечень и
    первый квартал — по клеткам положительной вероятности хотя бы в одном слое; масса — одно число с гейтом.
    Контракт отказывает выпуску, где узел и гейт расходятся."""
    from model import payload as P
    from tests.support_core2 import contract

    rel, d = _gap_release()
    run = rel.run
    live = [c for c in run.cells if any(L.prob[c.key] > 0 for L in run.layers.values())]
    dead_gap = [c for c in run.cells if c not in live and "capital_gap" in c.flags]
    flagged = [c for c in live if "capital_gap" in c.flags]
    assert len(dead_gap) >= 2 and len(flagged) >= 6, (len(dead_gap), len(flagged))
    node = d["capital"]["capital_gap"]
    gate = next(g for g in d["checks"]["gates"] if g["name"] == "capital_gap")
    assert node["cells"] == len(flagged) == gate["cells"], (node["cells"], len(flagged), gate["cells"])
    assert node["cell_list"] == [c.label for c in flagged][:P.CELL_LIST_MAX] == gate["cell_list"]
    assert not {c.label for c in dead_gap} & set(node["cell_list"])
    assert node["first_period"] == min(c.gap_period for c in flagged)
    mass = sum(run.layers["analytical"].prob[c.key] for c in flagged)
    assert close(node["mass"], mass, abs_=1e-6) and close(node["mass"], gate["mass"], abs_=1e-6)
    assert not contract(d), contract(d)[:5]
    for change in ({"cells": node["cells"] + len(dead_gap)}, {"cell_list": node["cell_list"][1:]},
                   {"mass": node["mass"] + 0.01}):
        broken = copy.deepcopy(d)
        broken["capital"]["capital_gap"].update(change)
        assert any("capital.capital_gap" in x and "гейт" in x for x in P._capital_problems(broken)), change


# ====================================================================== разброс цены по осям сетки (М§3.4)


def _own_shares(prob: Mapping, price: Mapping, rule: str) -> dict[str, float]:
    """Доли разброса своим счётом (не код ядра): условные средние осей; сценарий — главным эффектом (`main`) или
    сверх режима (`seq`, g(s) = Σ_r P(r | s) (E[f | r, s] − E[f | r])); остаток — 1 − Σ долей; при `seq` рядом —
    остаток прямым счётом Σ P ρ² / D (ключ `rest`)."""
    keys = [k for k in price]
    mu = sum(prob[k] * price[k] for k in keys)
    var = sum(prob[k] * (price[k] - mu) ** 2 for k in keys)

    def cond(idx: int) -> dict[str, float]:
        out = {}
        for v in {k[idx] for k in keys}:
            w = sum(prob[k] for k in keys if k[idx] == v)
            if w > 0:
                out[v] = sum(prob[k] * price[k] for k in keys if k[idx] == v) / w
        return out

    a, b = cond(0), cond(1)
    pw = {v: sum(prob[k] for k in keys if k[0] == v) for v in a}
    pr = {v: sum(prob[k] for k in keys if k[1] == v) for v in b}
    d_w = sum(pw[v] * (a[v] - mu) ** 2 for v in a)
    d_r = sum(pr[v] * (b[v] - mu) ** 2 for v in b)
    scen = {k[2] for k in keys}
    ps = {s: sum(prob[k] for k in keys if k[2] == s) for s in scen}
    if rule == "main":
        c = cond(2)
        d_s = sum(ps[s] * (c[s] - mu) ** 2 for s in c)
        g = {}
    else:
        g = {}
        for s in scen:
            if ps[s] <= 0:
                continue
            total = 0.0
            for r in b:
                prs = sum(prob[k] for k in keys if k[1] == r and k[2] == s)
                if prs > 0:
                    m_rs = sum(prob[k] * price[k] for k in keys if k[1] == r and k[2] == s) / prs
                    total += prs / ps[s] * (m_rs - b[r])
            g[s] = total
        d_s = sum(ps[s] * g[s] ** 2 for s in g)
    out = {"world": d_w / var, "regime": d_r / var, "scenario": d_s / var}
    out["interaction"] = 1.0 - sum(out.values())
    if rule == "seq":
        rho = sum(prob[k] * (price[k] - mu - (a[k[0]] - mu) - (b[k[1]] - mu) - g[k[2]]) ** 2
                  for k in keys if prob[k] > 0)
        out["rest"] = rho / var
    return out


def check_example_g1() -> None:
    """Пример приложения G.1: доли обоих правил на сетке со сценарием одного режима и на той же сетке с таблицей,
    одной во всех режимах (тогда правила совпадают) — до 1e-9; остаток последовательного правила равен Σ P ρ² / D."""
    from model import payload as P

    ex = EXAMPLE["spread"]
    price = _cells_of(ex["price"])
    for name in ("dependent", "independent"):
        node = ex[name]
        prob = _cells_of(node["probabilities"])
        main, seq = P.main_effect_shares(prob, price), P.variance_shares(prob, price)
        for k, v in node["main_effects"].items():
            assert abs(main[k] - v) < TOL, (name, "main", k, main[k], v)
        for k, v in node["sequential"].items():
            assert abs(seq[k] - v) < TOL, (name, "seq", k, seq[k], v)
        assert abs(seq["interaction"] - node["var_rest_sequential"] / node["variance"]) < TOL
        own = _own_shares(prob, price, "seq")
        assert abs(own["rest"] - seq["interaction"]) < TOL and all(0 <= seq[k] <= 1 for k in seq), name
    assert P.main_effect_shares(_cells_of(ex["dependent"]["probabilities"]), price)["interaction"] < -0.3
    # нулевая дисперсия: доли осей — ноль, остаток — единица у обоих правил
    flat = {k: 0.0 for k in price}
    prob = _cells_of(ex["dependent"]["probabilities"])
    for fn in (P.main_effect_shares, P.variance_shares):
        assert fn(prob, flat) == {"world": 0.0, "regime": 0.0, "scenario": 0.0, "interaction": 1.0}


def _grid_prices(run: Any) -> tuple[dict, dict]:
    prob = run.layers["analytical"].prob
    return dict(prob), {c.key: run.cell_price(c) for c in run.cells}


@lru_cache(maxsize=None)
def _four_run(key: bool):
    return run_grid(S2.four_scenarios_book(SEQ if key else None, own=True), fixture_facts())


def check_variance_rules_on_the_grid() -> None:
    """Разброс цены на сетке (М§3.4): с ключом `sequential` — четыре доли в [0; 1], в сумме единица, остаток равен
    Σ P ρ² / D, пересчитанному тестом по ценам клеток; доли мира и режима — те же, что у правила образца; цена клетки
    нулевой вероятности доли не меняет; при таблице сценариев, одной во всех режимах, доли обоих правил равны
    (1e-12). Без ключа — правило образца (у книги с таблицей, разной по режимам, — не последовательное)."""
    from model import payload as P

    prob, price = _grid_prices(_four_run(True))
    seq, own = P.variance_shares(prob, price), _own_shares(prob, price, "seq")
    for k in ("world", "regime", "scenario", "interaction"):
        assert abs(seq[k] - own[k]) < 1e-9, (k, seq[k], own[k])
        assert -1e-12 <= seq[k] <= 1 + 1e-12, (k, seq[k])
    assert abs(seq["interaction"] - own["rest"]) < 1e-9 and abs(sum(seq.values()) - 1) < 1e-12
    main = _own_shares(prob, price, "main")
    assert abs(seq["world"] - main["world"]) < 1e-12 and abs(seq["regime"] - main["regime"]) < 1e-12
    assert main["interaction"] < 0 < seq["interaction"], (main, seq)        # сценарий одного режима
    dead = [c.key for c in S2._dead(_four_run(True))]
    moved = {k: (v + 1000.0 if k in dead else v) for k, v in price.items()}
    assert P.variance_shares(prob, moved) == seq
    # таблица одна во всех режимах: правила совпадают
    data = fixture_dict()
    row = data["joint"]["reg_prob_given_regime"]["soft"]
    for r in data["joint"]["reg_prob_given_regime"]:
        data["joint"]["reg_prob_given_regime"][r] = dict(row)
    run = run_grid(book_from_dict(data, facts=fixture_facts()), fixture_facts())
    prob, price = _grid_prices(run)
    a, b = P.main_effect_shares(prob, price), P.variance_shares(prob, price)
    assert all(abs(a[k] - b[k]) < 1e-12 for k in a), (a, b)


def check_variance_node_by_the_key() -> None:
    """Узел выпуска `variance` (М§3.4, П§2): с ключом — последовательное правило, поле `rule` и слова о сценарии
    сверх режима; без ключа — правило образца без поля `rule` (книга образца с таблицей, разной по режимам);
    контракт отказывает доле вне [0; 1] и называет ключ; негодное значение ключа — отказ схемы."""
    from model import payload as P

    for book, rule in ((fixture_book(), "main"), (fixture_book().with_overrides(SEQ, create=True), "seq")):
        run = run_grid(book, fixture_facts())
        prob, price = _grid_prices(run)
        own = _own_shares(prob, price, rule)
        x = SimpleNamespace(p_an=prob, run=run, book=book)
        node = P._variance(x)
        for k in ("world", "regime", "scenario", "interaction"):
            assert abs(node["price"][k] - own[k]) <= 1e-6, (rule, k, node["price"][k], own[k])
        assert ("rule" in node) == (rule == "seq") and node.get("rule", "sequential") == "sequential"
        if rule == "seq":
            assert "сверх режима" in node["method"]
    main, seq = (_own_shares(*_grid_prices(run_grid(fixture_book(), fixture_facts())), r) for r in ("main", "seq"))
    assert abs(main["scenario"] - seq["scenario"]) > 1e-4                  # таблица образца — разная по режимам
    _, d = S2.fast_release(fixture_book())
    assert not P._variance_problems(d)
    for bad in ({"interaction": -0.02}, {"scenario": 1.2}):
        broken = copy.deepcopy(d)
        broken["variance"]["price"].update(bad)
        text = P._variance_problems(broken)
        assert text and KEY in text[0] and "вне [0; 1]" in text[0], text
    data = fixture_dict()
    data["checks"]["grid_variance"] = "nested"
    try:
        book_from_dict(data, facts=fixture_facts())
    except BookError as exc:
        assert KEY in str(exc), str(exc)
    else:
        raise AssertionError("схема приняла checks.grid_variance = nested")


# ====================================================================== печать DPS и делители (М§6.6)


def check_example_g2() -> None:
    """Пример приложения G.2: DPS клеток и DPS политики — функцией ядра с делителями §6.6; строки смеси (DPS на
    нынешнюю акцию, масса оборванных, DPS по клеткам с путём, дивиденд оборванных) и делитель DPS нау-каста — до
    1e-9; тождество `DPS_mix = DPS_int × (1 − broken)`."""
    from model import payload as P

    ex = EXAMPLE["dps_print"]
    year, q_a = 2030, 4
    policy = SimpleNamespace(payouts=lambda y: (float(ex["payout"]),))
    af = SimpleNamespace(n_out=float(ex["n_out"]), n_iss=float(ex["n_iss"]))
    prep = SimpleNamespace(policy=policy, af=af, recap=object())
    cells, prob = [], {}
    for row in ex["cells"]:
        n = [float(ex["n_div"])] * (q_a - 1) + [None if row["n_before"] is None else float(row["n_before"])]
        shares = SimpleNamespace(n=n)
        dec = SimpleNamespace(year=year, base=float(row["base"]), div=float(row["div"]), source="model",
                              dps=float(row["div"]) * 1000 / float(ex["n_out"]))
        dps, dps_pol = own_year_dps(prep, shares, q_a, dec, float(ex["n_base"]))
        assert abs(dps - row["dps"]) < TOL and abs(dps_pol - row["dps_policy"]) < TOL, (row["cell"], dps, dps_pol)
        key = (row["cell"], "r", "s")
        prob[key] = float(row["p"])
        cells.append(SimpleNamespace(key=key, label=row["cell"], dps={year: dps}, dps_policy={year: dps_pol},
                                     decisions=(dec,), shares=shares))
    timeline = SimpleNamespace(index=lambda period: q_a)
    book = SimpleNamespace(get=lambda path: 2)
    run = SimpleNamespace(cells=cells, ctx=SimpleNamespace(timeline=timeline, book=book, prep=prep))
    mix = ex["mix"]
    got = dps_split(run, prob, year)
    assert abs(got["dps"] - mix["dps"]) < TOL and abs(got["broken"] - mix["broken_mass"]) < TOL
    assert abs(got["intact"] - mix["dps_intact"]) < TOL and abs(got["amount_broken"] - mix["broken_amount"]) < TOL
    assert abs(got["intact"] * (1 - got["broken"]) - got["dps"]) < TOL
    now = ex["nowcast"]
    x = SimpleNamespace(run=run, prep=prep, p_mix=prob, n_iss=af.n_iss, n_div=float(ex["n_div"]))
    n_bar = P.nowcast_divisor(x, year)
    assert abs(n_bar - now["shares_effective"]) < TOL, n_bar
    pay = float(ex["payout"])
    assert abs(pay * now["base_now"] * 1000 / n_bar - now["dps_now"]) < TOL
    assert abs(pay * now["base_mix"] * 1000 / n_bar - mix["dps_policy"]) < TOL
    assert abs(sum(prob[c.key] * c.dps_policy[year] for c in cells) - mix["dps_policy"]) < TOL


@lru_cache(maxsize=None)
def _dps_release():
    """Выпуск фикстуры печати DPS (`DPS_BOOK`): оборванные пути акций, поправка делителя, взносы."""
    return S2.fast_release(RC.book_of(DPS_BOOK))


def _broken(run: Any, c: Any, year: int) -> bool:
    """Путь акций клетки оборван к собранию года прибыли (своим счётом, М§6.6): решение модели, а квартал перед
    собранием — не раньше квартала обрыва пути."""
    dec = next(d for d in c.decisions if d.year == year)
    tl = run.ctx.timeline
    q_a = tl.index(period_str(year + 1, int(run.ctx.book.get("dividends.calendar.agm_quarter"))))
    return dec.source != "register" and c.shares.broken is not None and q_a - 1 >= c.shares.broken


def check_dps_rows_with_broken_paths() -> None:
    """Строки DPS книги с докапитализацией (М§6.6, П§2): DPS — на нынешнюю акцию (оборванные — нулём); рядом масса
    оборванных под смесью заголовка, DPS по клеткам с путём и дивиденд оборванных на размещённые акции по фактам
    якоря; `p_zero` — с оборванными; тождество строк сторожит контракт; узел взносов — те же строки под смесью
    точки; поле `dps_basis` — `own_year`."""
    from model import payload as P
    from tests.support_core2 import contract

    rel, d = _dps_release()
    run = rel.run
    af = run.ctx.prep.af
    lam = run.lam
    p_mix = {k: lam * run.layers["analytical"].prob[k] + (1 - lam) * run.layers["macro_neutral"].prob[k]
             for k in run.layers["analytical"].prob}
    p_an = run.layers["analytical"].prob
    assert not contract(d), contract(d)[:5]
    assert d["dividends"]["dps_basis"] == "own_year"
    hits = paid = 0
    for row in d["dividends"]["model"]:
        y = row["year"]
        gone = [c for c in run.cells if _broken(run, c, y)]
        broken = sum(p_mix[c.key] for c in gone)
        intact = sum(p_mix[c.key] * c.dps[y] for c in run.cells if c not in gone) / (1 - broken)
        amount = sum(p_mix[c.key] * next(x.div for x in c.decisions if x.year == y) for c in gone) * af.n_iss / af.n_out
        assert abs(row["broken_mass"] - broken) <= 1e-6 and abs(row["dps_intact"] - intact) <= 1e-4, (y, row)
        assert abs(row["broken_amount"] - amount) <= 0.006, (y, row["broken_amount"], amount)
        assert all(c.dps[y] == 0.0 for c in gone)
        zero = sum(p_an[c.key] for c in run.cells if abs(c.dps[y]) < 1e-12)
        assert abs(row["p_zero"] - zero) <= 1e-6 and zero >= sum(p_an[c.key] for c in gone) - 1e-12
        got = dps_split(run, p_mix, y)
        assert close(got["broken"], broken, abs_=1e-12) and close(got["intact"], intact, rel=1e-12)
        assert close(got["amount_broken"], amount, rel=1e-12, abs_=1e-12)
        hits += broken > 0
        paid += amount > 0
    assert hits >= 5 and paid >= 3, (hits, paid)
    # узел взносов: те же строки под вероятностями смеси точки
    node = recap_node(run)
    pp = point_probabilities(run)
    for i, y in enumerate(node["years"]):
        if node["mix"]["dps"][i] is None:
            continue
        gone = [c for c in run.cells if _broken(run, c, y)]
        broken = sum(pp[c.key] for c in gone)
        assert close(node["mix"]["broken_mass"][i], broken, abs_=1e-12), y
        assert close(node["mix"]["dps_intact"][i] * (1 - broken), node["mix"]["dps"][i], rel=1e-9, abs_=1e-12), y
    # контракт: тождество строки и дивиденд оборванных не больше суммы года
    row = next(r for r in d["dividends"]["model"] if r["broken_mass"] > 0)
    broken = copy.deepcopy(d)
    target = next(r for r in broken["dividends"]["model"] if r["year"] == row["year"])
    target["dps_intact"] = round(target["dps_intact"] * 1.01 + 0.01, 4)
    assert any("dps_intact" in x for x in P._capital_problems(broken))
    broken = copy.deepcopy(d)
    broken["capital"]["recapitalization"]["mix"]["broken_mass"][2] = 0.5
    assert any("capital.recapitalization.mix" in x for x in P._capital_problems(broken))


def check_dps_fields_only_with_recapitalization() -> None:
    """У книги без включённой докапитализации полей печати обрыва нет: ни `dps_intact`, `broken_mass`,
    `broken_amount` в строках, ни `dps_basis`, ни делителя строки нау-каста; DPS нау-каста — на N_iss якоря
    (прежняя строка); узел пути смеси точки — без полей обрыва."""
    _, d = S2.fast_release(fixture_book())
    assert "dps_basis" not in d["dividends"]
    assert not any({"dps_intact", "broken_mass", "broken_amount"} & set(r) for r in d["dividends"]["model"])
    year = d["nowcast"]["year"]
    assert "shares_mln" not in year
    n_iss = float(fixture_facts().need("shares", "issued_total"))
    if year["base"] is not None:
        assert abs(year["dps"] - year["payout"] * max(0.0, year["base"]) * 1000 / n_iss) <= 2e-4
    plain = run_grid(fixture_book().with_overrides({"checks.point_path": True}, create=True), fixture_facts())
    keyed = RC.grid_of({**DPS_BOOK, "checks.point_path": True})
    assert "dps_intact" not in point_path(plain) and "broken_mass" not in point_path(plain)
    node = point_path(keyed)
    pp = point_probabilities(keyed)
    for i, y in enumerate(node["years"]):
        if node["dps"][i] is None:
            continue
        broken = sum(pp[c.key] for c in keyed.cells if _broken(keyed, c, y))
        assert close(node["broken_mass"][i], broken, abs_=1e-12), y
        assert close(node["dps_intact"][i] * (1 - broken), node["dps"][i], rel=1e-9, abs_=1e-12), y


def check_policy_dps_denominator() -> None:
    """Знаменатель DPS политики (М§6.6, W11): на фикстуре с поправкой делителя и взносами DPS политики решения
    квартала собрания — `пул × 1000 / (N_iss + (N_(q_A − 1) − N_base))`, пул — доля первой ступени × max(0, база);
    при оборванном к собранию пути — ноль."""
    run = RC.grid_of(DPS_BOOK)
    p = run.ctx.prep
    tl = run.ctx.timeline
    agm = int(run.ctx.book.get("dividends.calendar.agm_quarter"))
    n_base = run.divisor / 1.25
    checked = diluted = 0
    for c in run.cells:
        for dec in c.decisions:
            q_a = tl.index(period_str(dec.year + 1, agm))
            n = c.shares.n[q_a - 1]
            pool = p.policy.payouts(dec.year)[0] * max(0.0, dec.base)
            want = 0.0 if n is None else pool * 1000 / (p.af.n_iss + (n - n_base))
            assert close(c.dps_policy[dec.year], want, rel=1e-12, abs_=1e-12), (c.label, dec.year)
            checked += 1
            diluted += n is not None and n > run.divisor * (1 + 1e-9)
    assert checked >= 300 and diluted >= 30, (checked, diluted)


def check_nowcast_divisor() -> None:
    """Делитель DPS нау-каста (М§6.6): `N̄_iss,Y = 1000 × Σ P·пул / Σ P·DPS политики` под смесью заголовка — своим
    счётом; при базе нау-каста, равной базе смеси, DPS нау-каста равен `dps_model` строки; узел выпуска делит DPS,
    ширину и доходность на этот делитель и печатает его (`shares_mln`)."""
    from model import payload as P

    rel, d = _dps_release()
    x = P._Ctx(rel)
    run = rel.run
    year = d["nowcast"]["year"]
    y = year["year"]
    pay = x.prep.policy.payouts(y)[0]
    decs = {c.key: next(dd for dd in c.decisions if dd.year == y) for c in run.cells}
    num = sum(x.p_mix[c.key] * pay * max(0.0, decs[c.key].base) for c in run.cells)
    den = sum(x.p_mix[c.key] * c.dps_policy[y] for c in run.cells)
    n_bar = 1000 * num / den
    assert close(P.nowcast_divisor(x, y), n_bar, rel=1e-12)
    assert n_bar > x.n_iss * 1.2, (n_bar, x.n_iss)                         # акции поправки и взносов
    base_mix = sum(x.p_mix[c.key] * decs[c.key].base for c in run.cells)
    assert all(decs[c.key].base >= 0 for c in run.cells)
    assert close(pay * base_mix * 1000 / P.nowcast_divisor(x, y), den, rel=1e-12)
    assert "shares_mln" in year and abs(year["shares_mln"] - n_bar) <= 1e-3, year
    if year["base"] is not None:
        assert abs(year["dps"] - year["payout"] * max(0.0, year["base"]) * 1000 / n_bar) <= 2e-4
        assert year["dps"] < year["payout"] * max(0.0, year["base"]) * 1000 / x.n_iss / 1.2
        price = d["market"]["price"]
        assert abs(year["yield"][d["meta"]["company"]["main_ticker"]] - year["dps"] / price) <= 2e-6


# ====================================================================== норма доли терминала (М§6.4, W3)


def check_terminal_share_after_a_closed_contribution() -> None:
    """Дата оценки после квартала взноса (М§6.4): доля терминала клетки — `DF_v(τ_Q) × (TV_DDM − DC_T) /
    max(V_DDM, BV_v − C_v)`, слоя — `Σ P × DF_v(τ_Q)(TV_DDM − DC_T) / max(V0_L, Σ P (BV_v − C_v))`; капитал на дату
    оценки и взносы закрытых кварталов — по рядам клетки. У клетки ниже капитала норма — капитал без закрытых
    взносов."""
    run = RC.grid_of(RC.BIG_BUFFER)
    tl = run.ctx.timeline
    end = tl.end(RC.first_agm(run))
    after = RC.grid_of(RC.BIG_BUFFER, live=RC.live_at(end + timedelta(days=5), (RC.record(run, 40.0),)))
    q0, e = after.ctx.clock.q0, after.ctx.clock.elapsed
    below = 0
    norms = {}
    for c in after.cells:
        rec = c.quarters["rec"]
        c_v = sum(rec[q] for q in range(1, q0))
        capital = c.quarters["bv"][q0 - 1] + e * c.quarters["ci"][q0] - c_v
        dfq = after.ctx.discounts[c.world].dfq
        tv = dfq[-1] * (c.tv_ddm - c.dc_t)
        norm = max(c.v_ddm, capital)
        assert close(c.terminal_share, tv / norm, rel=1e-12), (c.label, c.terminal_share, tv / norm)
        norms[c.key] = (tv, capital)
        below += c_v > 0 and c.v_ddm < capital
    assert below >= 5, below
    for name, layer in after.layers.items():
        prob = layer.prob
        tv = sum(prob[k] * v[0] for k, v in norms.items())
        capital = sum(prob[k] * v[1] for k, v in norms.items())
        assert close(layer.terminal_share, tv / max(layer.v0, capital), rel=1e-12), name
    assert any(layer.v0 < sum(layer.prob[k] * v[1] for k, v in norms.items()) for layer in after.layers.values())


# ====================================================================== гейт знака стресса (М§3.4, §14.2; W5, W10)


# допуск гейта знака стресса фикстуры, млрд ₽: у фикстуры без ограничения роста строгий сценарий копит капитал и
# зарабатывает больше мягкого на десятки–сотни млрд ₽ — построенные нарушения ниже стоят вдвое дальше допуска
SIGN_TOL = 1000.0


@lru_cache(maxsize=None)
def _sign_book():
    return S2.four_scenarios_book({"checks.stress_sign": {"loss_step": 10.0, "tol": SIGN_TOL}, **SEQ}, own=True)


def check_stress_sign_and_zero_probability_cells() -> None:
    """Гейт знака стресса судит клетки положительной вероятности (М§3.4, §14.2): пара сценариев «мир × режим», где
    у одной клетки вероятность ноль, в часть (б) не входит — при положительной вероятности обеих клеток то же
    нарушение поднимает гейт; клетка нулевой вероятности режима шока, где стоимость растёт с убытком, часть (а) не
    поднимает — клетка положительной вероятности поднимает."""
    book, facts = _sign_book(), fixture_facts()
    run = run_grid(book, facts)
    base = stress_sign_test(book, facts, run=run)
    assert base["ok"], base
    at = lambda c: run.cells.index(c)  # noqa: E731
    last = run.ctx.timeline.Q
    req = {s: run.ctx.prep.scenarios[s].req20[last] for s in book.get("capital.reg_scenarios.ids")}
    live_of = lambda c: any(L.prob[c.key] > 0 for L in run.layers.values())  # noqa: E731
    # (б): клетка нулевой вероятности — более мягкий сценарий пары с прибылью ниже строгого
    dead = next(c for c in run.cells if not live_of(c) and c.regime != S2.SHOCK
                and any(req[s] > req[c.scenario] + 1e-9 for s in req))
    strict = next(s for s in req if req[s] > req[dead.scenario] + 1e-9)
    ni = list(dead.annual["ni_sh"])
    ni[-1] = run.cell(dead.world, dead.regime, strict).annual["ni_sh"][-1] - 2 * SIGN_TOL
    quiet = stress_sign_test(book, facts, run=S2._with_cell(run, at(dead), annual={**dead.annual, "ni_sh": tuple(ni)}))
    assert quiet["ok"] and not quiet["requirement"]["cells"], quiet["requirement"]
    looser = next(s for s in req if req[strict] > req[s] + 1e-9 and live_of(run.cell(dead.world, dead.regime, s)))
    twin = run.cell(dead.world, dead.regime, looser)
    ni = list(twin.annual["ni_sh"])
    ni[-1] = run.cell(dead.world, dead.regime, strict).annual["ni_sh"][-1] - 2 * SIGN_TOL
    loud = stress_sign_test(book, facts, run=S2._with_cell(run, at(twin), annual={**twin.annual, "ni_sh": tuple(ni)}))
    assert not loud["ok"] and any(x["looser"] == looser and x["stricter"] == strict
                                  for x in loud["requirement"]["cells"]), loud["requirement"]
    # (а): клетка нулевой вероятности режима шока — стоимость клетки занижена: с убытком она «растёт»
    dead = next(c for c in run.cells if not live_of(c) and c.regime == S2.SHOCK)
    quiet = stress_sign_test(book, facts, run=S2._with_cell(run, at(dead), v_ri=dead.v_ri - 2 * SIGN_TOL))
    assert quiet["ok"] and not quiet["loss"]["cells"], quiet["loss"]
    alive = next(c for c in run.cells if live_of(c) and c.regime == S2.SHOCK)
    loud = stress_sign_test(book, facts, run=S2._with_cell(run, at(alive), v_ri=alive.v_ri - 2 * SIGN_TOL))
    assert not loud["ok"] and [x["scenario"] for x in loud["loss"]["cells"]] == [alive.scenario], loud["loss"]


# ====================================================================== контракт, схема, печать


def check_cell_triples_in_the_contract() -> None:
    """Контракт сверяет тройки клеток поштучно (П§7 п. 8, W6): выпуск, где одна тройка заменена другой при том же
    числе клеток (повтор и пропуск), — отказ с числом клеток книги."""
    from model import payload as P

    _, d = S2.fast_release(fixture_book())
    assert not [x for x in P._layer_problems(d) if x.startswith("grid.cells: нужно")]
    twin = copy.deepcopy(d)
    cells = twin["grid"]["cells"]
    for k in ("world", "regime", "scenario"):
        cells[5][k] = cells[4][k]
    text = [x for x in P._layer_problems(twin) if x.startswith("grid.cells: нужно")]
    assert text and "нужно 36 клеток" in text[0] and "в выпуске 36" in text[0], P._layer_problems(twin)[:3]


def check_schema_of_the_share_keys() -> None:
    """Ключи доли вычета якоря (М§4.11, прил. A № 21): `null` у любого из двух ключей — отказ «null», и у обоих;
    слово `anchor`, булево, словарь, строка — отказ у каждого из двух ключей; ноль и единица допустимы."""
    def refused(a: Any, b: Any) -> str | None:
        data = fixture_dict()
        data["capital"]["n20"]["deductions_fixed_share"] = a
        data["capital"]["n11"]["deductions_fixed_share"] = b
        try:
            book_from_dict(data, facts=fixture_facts())
        except BookError as exc:
            return str(exc)
        return None

    for a, b, path in ((None, 0.5, S20), (0.5, None, S11), (None, None, S20), (None, None, S11)):
        text = refused(a, b)
        assert text is not None and f"{path}: null" in text, (a, b, text)
    for bad in ("anchor", True, {"x": 1}, "0.5"):
        for a, b, path in ((bad, 0.5, S20), (0.5, bad, S11)):
            text = refused(a, b)
            assert text is not None and path in text, (a, b, text)
    for a, b in ((0.0, 1.0), (1.0, 0.0), (0.6065, 0.6065)):
        assert refused(a, b) is None, (a, b)


def _signed_zeros(node: Any, path: str = "$") -> list[str]:
    if isinstance(node, Mapping):
        return [p for k, v in node.items() for p in _signed_zeros(v, f"{path}.{k}")]
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in _signed_zeros(v, f"{path}[{i}]")]
    return [path] if isinstance(node, float) and node == 0.0 and math.copysign(1.0, node) < 0 else []


def check_zero_without_sign() -> None:
    """Ноль хранится без знака (П§0.3, находка 7): при долях вычета якоря, равных единице, сумма строки вычетов моста
    норматива — `0.0`, и во всём выпуске нет `-0.0`."""
    from model import payload as P

    _, d = S2.fast_release(fixture_book().with_overrides({S20: 1.0, S11: 1.0}, create=True))
    row = next(r for r in d["capital"]["bridge"]["rows"] if r["key"] == "deductions")
    assert row["amount"] == 0.0 and math.copysign(1.0, row["amount"]) > 0, row
    assert not _signed_zeros(d), _signed_zeros(d)[:5]
    assert math.copysign(1.0, P.rnd(-1e-12, 0.01)) > 0 and P.rnd(-0.004, 0.01) == 0.0


def check_control_summary_counters() -> None:
    """Счётчики сводки контрольной модели (П§7 п. 15; М§17): строк по правилу «ступень политики у порога» не больше
    строк в допуске, при них названы клетки и годы первого расхождения; сводка без этих полей — прежняя форма."""
    from model import payload as P

    rows = [{"what": "x", "unit": "bn", "core": 1.0, "control": 1.0, "diff": 0.0, "diff_rel": 0.0, "tol": 0.1,
             "tol_kind": "rel", "ok": True}]
    base = {"as_of": "2026-10-02", "commit": None, "rows": rows, "n_rows": 10, "n_bad": 2, "all_ok": False}
    assert not P._control_summary_problems(base)
    cell = [{"cell": "H/soft/strict", "year": 2033}]
    assert not P._control_summary_problems({**base, "n_step": 8, "step_cells": cell})
    for bad, words in (({"n_step": 9, "step_cells": cell}, "n_step"), ({"n_step": 3}, "step_cells"),
                       ({"n_step": 3, "step_cells": []}, "step_cells"), ({"n_step": -1, "step_cells": cell}, "n_step"),
                       ({"n_step": 1, "step_cells": [{"cell": "H/soft/strict", "year": "2033"}]}, "step_cells")):
        text = P._control_summary_problems({**base, **bad})
        assert text and words in text[0], (bad, text)
