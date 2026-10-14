# -*- coding: utf-8 -*-
"""Шестой проход ядра (М§4.7, §18, прил. I): база объёма `iea` квартала фактов — в определении клетки. Проверки для
тестов (`tests/test_core_pass6.py`) и мутационного набора (`tests/mutations.py`, раздел p6_).

ĪEA клетки — полусумма начала квартала и **предварительного** конца: балансирующие книги на конце стоят при
BV_(q−1) − Div_q, без дохода квартала (М§4.10). Отчётные концы — окончательные, поэтому средний остаток квартала
фактов x = −3…0 — `A_x = (iea[x−1] + iea[x] − ΔE_x) / 2`, `ΔE_x = bv[x] − bv[x−1] + Div_x`: bv — `bv_common` истории
баланса (конец якоря — капитал якоря), Div_x — сумма `pool_all_classes` (без поля — `pool_declared`) строк истории
дивидендов (`history` и `history_before`) с днём решения в квартале x. Базы `loans` и `funds` — прежняя полусумма.

Каждая проверка — своим счётом по узлам фактов и рядам клетки, независимо от кода ядра. Фикстура — форма образца
`tests/fixtures/core` со связями комиссий и расходов 0,5 и базой `iea`, подставленными проверкой; факты — с двумя
концами истории сверх её (2025К2, 2025К3: `iea`, `bv_common`, `loans`), базой `loans` концов 2025К4, 2026К1 и тремя
решениями о дивидендах в `history_before` (в окне базы — с суммой всех категорий и без неё, вне окна — одно).
"""
from __future__ import annotations

import copy
import functools
import hashlib
import json
from datetime import date
from typing import Any, Callable

from model.book import Book, Facts, book_from_dict, canonical_json
from model.book_schema import FactsError
from model.grid import GridRun, run_grid
from model.timeline import make_timeline
from tests.support_core import ROOT, fixture_book, fixture_dict, fixture_facts

EXAMPLE = json.loads((ROOT / "tests" / "fixtures" / "core_pass6" / "example.json").read_text(encoding="utf-8"))
LINK = 0.5                                   # связи комиссий и расходов фикстуры проверки
TOL = 1e-9                                   # млрд ₽: формулы без шага (A_x, тождество, пример I.1)
EXTRA_ENDS = (("2025Q2", "2025-06-30", 66300.0, 7905.0, 45900.0),   # период, дата, iea, bv_common, loans
              ("2025Q3", "2025-09-30", 66650.0, 8102.0, 46300.0))
LOANS_ENDS = {"2025Q4": 46710.0, "2026Q1": 47754.2}
DECISIONS = (                                # решения о дивидендах: в окне (x = 0, x = −2) и вне его (x = −4)
    {"year": 2025, "period": "2025Q4", "decided_date": "2026-06-26", "pay_date": "2026-07-24",
     "pool_declared": {"v": 700.0}, "pool_all_classes": {"v": 720.0}},
    {"year": 2025, "period": "2025Q2", "decided_date": "2025-11-20", "pool_declared": {"v": 120.0}},
    {"year": 2024, "period": "2024Q4", "decided_date": "2025-06-20", "pool_all_classes": {"v": 650.0}},
)


def close(a: float, b: float, tol: float = TOL) -> bool:
    return abs(a - b) <= tol


def facts_with(change: Callable[[dict], None] | None = None) -> Facts:
    """Факты фикстуры с концами истории и решениями о дивидендах (шапка модуля); `change(files)` правит копию."""
    f = fixture_facts()
    files = copy.deepcopy(dict(f.files))
    hist = files["balance"]["history"]
    for period, day, iea, bv, loans in EXTRA_ENDS:
        hist[period] = {"date": day, "iea": {"v": iea}, "bv_common": {"v": bv}, "loans": {"v": loans}}
    for period, loans in LOANS_ENDS.items():
        hist[period]["loans"] = {"v": loans}
    files["dividends"]["history_before"] = copy.deepcopy(list(DECISIONS))
    if change is not None:
        change(files)
    return Facts(root=f.root, files=files, digest=hashlib.sha256(canonical_json(files)).hexdigest())


@functools.lru_cache(maxsize=None)
def base_facts() -> Facts:
    return facts_with()


def link_book(base: str = "iea", facts: Facts | None = None) -> Book:
    """Книга фикстуры со связями комиссий и расходов `LINK` и базой объёма `base`."""
    data = copy.deepcopy(fixture_dict())
    data["fees"]["volume_link"] = LINK
    data["opex"]["volume_link"] = LINK
    data["volumes"]["link_base"] = base
    return book_from_dict(data, facts=base_facts() if facts is None else facts)


@functools.lru_cache(maxsize=None)
def link_run(base: str = "iea") -> GridRun:
    return run_grid(link_book(base), base_facts())


# ------------------------------------------------------------------ свой счёт по узлам фактов


def _v(node: Any) -> Any:
    return node.get("v") if isinstance(node, dict) else node


def _quarter(day: str, anchor: str) -> int:
    """x даты на линейке якоря `anchor` (ГГГГQn): квартал даты минус квартал якоря."""
    d = date.fromisoformat(day)
    ay, aq = int(anchor[:4]), int(anchor[-1])
    return (d.year * 4 + (d.month - 1) // 3 + 1) - (ay * 4 + aq)


def own_base(facts: Facts, iea_anchor: float, anchor: str) -> dict[int, float]:
    """A_x, x = −3…0, по §4.7 своим счётом: концы `iea` и `bv_common` истории баланса, капитал якоря и сумма книг
    активов якоря `iea_anchor`, решения истории дивидендов по дню решения."""
    files = facts.files
    hist = files["balance"]["history"]
    ay, aq = int(anchor[:4]), int(anchor[-1])

    def period(x: int) -> str:
        idx = ay * 4 + (aq - 1) + x
        return f"{idx // 4}Q{idx % 4 + 1}"

    iea = {x: float(_v(hist[period(x)]["iea"])) for x in range(-4, 0)}
    iea[0] = iea_anchor
    bv = {x: float(_v(hist[period(x)]["bv_common"])) for x in range(-4, 0)}
    bv[0] = float(_v(files["balance"]["equity"]["bv_common"]))
    div = {x: 0.0 for x in range(-3, 1)}
    for key in ("history", "history_before"):
        for row in files["dividends"].get(key) or []:
            day = _v(row.get("decided_date"))
            if not day:
                continue
            x = _quarter(str(day), anchor)
            if -3 <= x <= 0:
                amount = _v(row.get("pool_all_classes"))
                div[x] += float(amount if amount is not None else _v(row["pool_declared"]))
    return {x: (iea[x - 1] + iea[x] - (bv[x] - bv[x - 1] + div[x])) / 2 for x in range(-3, 1)}


def check_base_of_the_facts() -> None:
    """A_x квартала фактов при базе `iea` — формулой §4.7 своим счётом (решение собрания в окне — суммой всех категорий,
    без неё — суммой на размещённые акции, день решения — квартал; конец якоря — капитал якоря); базы `loans` —
    прежняя полусумма концов; книга без связей базу не читает."""
    run = link_run("iea")
    anchor = str(run.ctx.book.get("meta.anchor_period"))
    cell = run.cells[0]
    want = own_base(base_facts(), float(cell.quarters["iea"][0]), anchor)
    got = run.ctx.prep.hist_vol
    assert sorted(got) == [-3, -2, -1, 0] and run.ctx.prep.link_base == "iea"
    bad = {x: (got[x], want[x]) for x in want if not close(got[x], want[x])}
    assert not bad, bad
    # решения в окне в счёте участвуют: без них A_0 выше на Div_0 / 2 = 360, A_−2 — на 60
    plain = own_base(facts_with(lambda f: f["dividends"].update(history_before=[])), float(cell.quarters["iea"][0]),
                     anchor)
    assert close(plain[0] - want[0], 360.0) and close(plain[-2] - want[-2], 60.0)
    loans = link_run("loans")
    hist = base_facts().files["balance"]["history"]
    ends = {-4: hist["2025Q2"]["loans"]["v"], -3: hist["2025Q3"]["loans"]["v"], -2: hist["2025Q4"]["loans"]["v"],
            -1: hist["2026Q1"]["loans"]["v"], 0: float(loans.cells[0].quarters["loans"][0])}
    assert loans.ctx.prep.link_base == "loans"
    for x in range(-3, 1):
        assert loans.ctx.prep.hist_vol[x] == (ends[x - 1] + ends[x]) / 2, (x, loans.ctx.prep.hist_vol)
    free = run_grid(fixture_book(), fixture_facts())
    assert free.ctx.prep.link_base == "" and not free.ctx.prep.hist_vol


def check_refusals() -> None:
    """Отказ `FactsError` при базе `iea` и ненулевой связи: нет `bv_common` на нужном конце; решение в окне без суммы;
    сумма больше нуля без дня решения у строки с кварталом прибыли не раньше x = −11 (раньше — принимается). База
    `loans` правила не читает."""
    def refused(change: Callable[[dict], None], base: str = "iea") -> str | None:
        facts = facts_with(change)
        try:
            run_grid(link_book(base, facts), facts)
        except FactsError as exc:
            return str(exc)
        return None

    text = refused(lambda f: f["balance"]["history"]["2025Q2"].pop("bv_common"))
    assert text and "bv_common" in text and "2025Q2" in text, text
    assert refused(lambda f: f["balance"]["history"]["2025Q2"].pop("bv_common"), "loans") is None

    def unpriced(f: dict) -> None:
        for k in ("pool_declared", "pool_all_classes"):
            f["dividends"]["history_before"][0].pop(k)

    text = refused(unpriced)
    assert text and "без суммы" in text and "2026Q2" in text, text

    def undated(period: str) -> Callable[[dict], None]:
        return lambda f: f["dividends"]["history_before"].append(
            {"year": int(period[:4]), "period": period, "pool_declared": {"v": 50.0}})

    text = refused(undated("2023Q3"))                     # x = −11 относительно якоря 2026Q2
    assert text and "decided_date" in text and "2023Q3" in text, text
    assert refused(undated("2023Q2")) is None             # x = −12: решение не могло прийтись на окно базы
    assert refused(lambda f: f["dividends"]["history_before"].append(
        {"year": 2025, "period": "2025Q4", "pool_declared": {"v": 0.0}})) is None   # сумма ноль — не отказ


def check_identity_on_the_cells() -> None:
    """Квартал клетки и тот же квартал фактом — одна A (М§4.7, §4.10): на рядах всех клеток
    `(iea[q−1] + iea[q] − (bv[q] − bv[q−1] + div[q])) / 2 = ĪEA_q`, где минимум ликвидности не связывает ни на одном
    конце (до 1e-9); где связывает — на окончательном конце (добор опта) или на предварительном (`LA_оконч − добор −
    ΔE` ниже минимума `доля × (кредиты − резерв + прочие активы) / (1 − доля)`) — разность в [−ΔE / 2; 0]."""
    run = link_run("iea")
    share = float(run.ctx.book.get("volumes.liquid_min_share"))
    free = binding = 0
    for c in run.cells:
        Q = c.quarters
        for q in range(1, len(Q["iea"])):
            de = Q["bv"][q] - Q["bv"][q - 1] + Q["div"][q]
            diff = (Q["iea"][q - 1] + Q["iea"][q] - de) / 2 - Q["iea_avg"][q]
            la = Q["securities"][q] + Q["liquidity"][q]
            minimum = share * (Q["loans"][q] - Q["allowance"][q] + Q["other_assets"][q]) / (1 - share)
            top_up = Q["wholesale_extra"][q]
            if top_up > TOL or la - top_up - de < minimum - TOL:
                binding += 1
                assert -de / 2 - TOL <= diff <= TOL, (c.label, q, diff, de)
            else:
                free += 1
                assert abs(diff) <= TOL, (c.label, q, diff)
    assert free > 0, (free, binding)


def check_example_i1() -> None:
    """Пример приложения I.1 (до 1e-9): A квартала фактов функцией ядра (`_volume_history` с ΔE из `equity_growth`) — по
    отчётным концам, капиталу и решённому дивиденду; без добора опта она равна ĪEA клетки, с добором — ниже на то, что
    съел минимум; клетка — своим счётом §4.10 по входам примера; строки следующего года — формулой §4.7."""
    from model.cell import _volume_history, equity_growth

    ex = EXAMPLE["volume_base"]
    inp, q = ex["inputs"]["open"], ex["inputs"]["quarter"]
    iea0 = inp["loans"] + inp["securities"] + inp["liquidity"]
    tl = make_timeline(fixture_book())
    for name, case in ex["cases"].items():
        s = case["liquid_min"]
        nonbal = q["loans"] - q["allowance"] + q["other_assets"]
        fixed = q["funds"] + q["other_liabilities"] + q["div"]          # дивиденд — к выплате позже: в обязательствах
        minimum = s * nonbal / (1 - s)
        assert close(minimum, case["la_min"]), name
        ends = {}
        for end, bv in (("preliminary", inp["bv"] - q["div"]), ("final", inp["bv"] + q["ci"] - q["div"] + q["rec"])):
            raw = fixed + q["wholesale_base"] + bv - nonbal
            la = max(raw, minimum)
            ends[end] = q["loans"] + la
            want = case[end]
            assert close(bv, want["bv"]) and close(la, want["la"]) and close(la - raw, want["wholesale_extra"]), (name, end)
            assert close(ends[end], want["iea"]), (name, end)
        assert close((iea0 + ends["preliminary"]) / 2, case["cell_iea_avg"]), name
        hist = {x: {"iea": iea0, "bv": inp["bv"]} for x in range(-4, 0)}
        growth = equity_growth(hist, case["final"]["bv"], {-3: 0.0, -2: 0.0, -1: 0.0, 0: q["div"]}, tl)
        assert close(growth[0], case["delta_e"]), name
        got = _volume_history("iea", hist, ends["final"], tl, growth)
        assert close(got[0], case["facts_a"]), (name, got[0])
        assert close(_volume_history("iea", hist, ends["final"], tl)[0], case["facts_a_old_rule"]), name
        assert close(got[0] - case["cell_iea_avg"], case["facts_minus_cell"]), name
        nxt, wage, link = ex["inputs"]["next_year_iea_avg"], ex["inputs"]["wage"], ex["inputs"]["link"]
        for a, v_key, f_key in ((got[0], "v", "fees"), (case["facts_a_old_rule"], "v_old_rule", "fees_old_rule")):
            v = nxt / a - 1
            assert close(v, case["next_year"][v_key]), name
            assert close(ex["inputs"]["fees_q"] * (1 + wage + link * (v - wage)), case["next_year"][f_key]), name
    assert close(ex["cases"]["free"]["facts_minus_cell"], 0.0)
    assert close(ex["cases"]["binding_both"]["facts_minus_cell"], -ex["cases"]["binding_both"]["delta_e"] / 2)
