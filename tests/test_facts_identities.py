"""Факты: тождества и сверки сумм (data/facts/SCHEMA.md §5; договор ключей фазы 3).

Баланс якоря по девяти книгам; проценты книг = ЧПД; строки ОПУ движка и отчётные строки; три прибыли ВТБ (прибыль
акционеров — прибыль движка, вся прибыль группы — база дивиденда и ROE банка, прибыль обыкновенных акционеров);
капитал банковской группы по форме 0409805; акции и корпоративные события (консолидация 5000:1, конвертация
привилегированных акций, зарегистрированный выпуск по 87 ₽); мосты упр. ↔ движок; гайденс; календарь; аналоги.
Числа якоря 30.06.2026 названы по документам (Databook 6М2026, отчётность за 6М2026, расшифровка звонка 28.07.2026,
форма 0409805) и проверяются только на этом якоре; остальное — тождества, не зависящие от квартала.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import statistics
from pathlib import Path

import pytest

from tests.test_facts_schema import (ASSET_BOOKS, BOOKS, LIABILITY_BOOKS, LOAN_BOOKS, anchor_period, has_text, is_stub,
                                     year_quarters)

pytestmark = pytest.mark.tact          # быстрые (≈1 с): тождества фактов идут в такте сервера

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
FIRST_ANCHOR = "2026Q2"                # якорь первой книги ВТБ: числа документов проверяются только на нём


def load(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def v(node) -> float:
    assert isinstance(node, dict) and node.get("v") is not None, node
    return float(node["v"])


def q_end(p: str) -> dt.date:
    y, k = int(p[:4]), int(p[-1])
    return dt.date(y, 3 * k, 31 if k in (1, 4) else 30)


def q_prev(p: str) -> str:
    y, k = int(p[:4]), int(p[-1])
    return f"{y - 1}Q4" if k == 1 else f"{y}Q{k - 1}"


def q_days(p: str) -> int:
    return (q_end(p) - q_end(q_prev(p))).days


def on_first_anchor() -> bool:
    return anchor_period() == FIRST_ANCHOR


ROUND = 0.15                           # строки отчётности напечатаны с одним знаком: сумма нескольких строк — до 0,15


# ------------------------------------------------------------------ баланс

def test_balance_identity_by_books():
    b = load("balance")
    books = {k: v(n) for k, n in b["books"].items()}
    assets = sum(books[x] for x in ASSET_BOOKS) - v(b["allowance_ac"]) + v(b["other_assets"])
    assert abs(assets - v(b["total_assets"])) < 1e-6, "Σ книг активов − резерв + прочие активы ≠ активы"
    claims = (sum(books[x] for x in LIABILITY_BOOKS) + v(b["other_liabilities"]) + v(b["dividends_payable"])
              + v(b["equity"]["total"]))
    assert abs(claims - v(b["total_assets"])) < ROUND, "Σ книг пассивов + прочие обязательства + дивиденды + капитал ≠ активы"
    assert abs(v(b["total_liabilities"]) + v(b["equity"]["total"]) - v(b["total_assets"])) < ROUND
    if on_first_anchor():                          # Databook 6М2026, «3.Баланс »: итог активов B32, обязательств B46
        assert v(b["total_assets"]) == 38506.8 and v(b["total_liabilities"]) == 35685.5
        assert abs(sum(books[x] for x in LOAN_BOOKS) - 25083.5) < 1e-6
        assert abs(v(b["other_assets"]) - 7165.0) < 1e-6 and abs(v(b["other_liabilities"]) - 2579.2) < 1e-6


def test_other_assets_parts_and_the_fixed_part():
    """Прочие активы и обязательства — строками отчёта; постоянная часть прочих активов (не растёт с кредитами) —
    отложенный налоговый актив, гудвил и ассоциированные компании; обязательство по дивидендам на якоре сидит в строке
    «прочие обязательства» отчёта."""
    b = load("balance")
    parts = sum(v(n) for n in b["other_assets_parts"].values())
    assert abs(parts - v(b["other_assets"])) <= 0.35, "строки прочих активов не дают остаток баланса"
    fixed = b["other_assets_fixed_parts"]
    assert set(fixed) == {"dta", "goodwill", "associates"}
    assert abs(sum(v(n) for n in fixed.values()) - v(b["other_assets_fixed"])) < 1e-6
    assert 0 <= v(b["other_assets_fixed"]) <= v(b["other_assets"])
    by_line = {k: v(n) for k, n in b["other_assets_parts"].items()}
    assert v(fixed["dta"]) == by_line["отложенный налоговый актив"]
    assert v(fixed["associates"]) == by_line["ассоциированные компании и СП"]
    assert v(fixed["goodwill"]) < by_line["гудвил и нематериальные активы"]
    liab = sum(v(n) for n in b["other_liabilities_parts"].values())
    assert abs(liab - v(b["other_liabilities"]) - v(b["dividends_payable"])) <= 0.35


def test_books_equal_their_reference_nodes():
    """Книги — суммы своих строк: бумаги — пять категорий долговых бумаг без бумаг НПФ; ликвидность — только доходные
    размещения (средства в банках и обратное репо без средств НПФ; деньги и обязательные резервы — в прочих
    активах); средства клиентов — физлица долей текущих счетов, юрлица с репо; опт — банки, прочие заёмные,
    выпущенные бумаги и субординированный долг."""
    b = load("balance")
    books = {k: v(n) for k, n in b["books"].items()}
    sec, liq, funds, wh = b["securities"], b["liquidity"], b["funds"], b["wholesale"]
    assert abs(sum(v(sec[k]) for k in ("fvoci_debt", "fvoci_repo", "ac", "ac_repo", "fvtpl_bonds")) - books["securities"]) < 1e-6
    assert abs(v(sec["debt_total"]) - books["securities"]) < 1e-6
    npf_in_banks = float(re.search(r"средства НПФ в банках ([\d ]+,\d)", b["books"]["liquidity"]["calc"]).group(1)
                         .replace(" ", "").replace(",", "."))
    assert abs(v(liq["due_from_banks"]) + v(liq["reverse_repo"]) - npf_in_banks - books["liquidity"]) < 1e-6
    assert npf_in_banks <= v(liq["npf_excluded"])
    other = b["other_assets_parts"]
    assert "НЕ входит в книгу" in liq["cash"]["calc"] and "НЕ входит в книгу" in liq["mandatory_reserves"]["calc"]
    assert v(other["обязательные резервы в центральных банках"]) == v(liq["mandatory_reserves"])
    assert v(funds["retail_current"]) == books["retail_current"] and v(funds["retail_term"]) == books["retail_term"]
    assert abs(v(funds["retail_current"]) + v(funds["retail_term"]) - v(funds["retail_total"])) < 1e-6
    assert abs(v(funds["corp_gov"]) + v(funds["corp_other"]) + v(funds["repo"]) - books["corp_funds"]) < 1e-6
    assert abs(sum(v(wh[k]) for k in ("banks", "other_borrowed", "debt_issued", "subordinated")) - books["wholesale"]) < 1e-6
    assert abs(v(b["iea"]) - sum(books[x] for x in ASSET_BOOKS)) < 1e-6


def test_equity_components():
    """Капитал акционеров = строки капитала Databook; бессрочные инструменты — в капитале МСФО (купон мимо прибыли):
    капитал обыкновенных акционеров = капитал акционеров − бессрочные."""
    e = load("balance")["equity"]
    parts = ("share_capital", "share_premium", "treasury_cost", "other_funds", "retained_earnings", "at1")
    assert abs(sum(v(e[k]) for k in parts) - v(e["shareholders"])) <= 0.25
    assert abs(v(e["shareholders"]) - v(e["at1"]) - v(e["bv_common"])) < 1e-6
    assert abs(v(e["shareholders"]) + v(e["nci"]) - v(e["total"])) <= ROUND
    assert v(e["at1"]) == v(load("capital")["at1"]["amount"]) and v(e["at1"]) > 0
    assert v(e["treasury_cost"]) < 0
    if on_first_anchor():                          # Databook «3.Баланс »: B55, B51, B56, B57
        assert (v(e["shareholders"]), v(e["at1"]), v(e["nci"]), v(e["total"]), v(e["bv_common"])) == \
            (2770.2, 368.0, 51.1, 2821.3, 2402.2)


def test_dividends_payable_is_the_declared_annual_dividend():
    """Дивиденд года, объявленный собранием до якоря и не выплаченный к нему: сумма к выплате, год и список объявленных
    по периодам — одно решение; сумма = DPS × размещённые акции (с точностью печати)."""
    b, d = load("balance"), load("dividends")
    n = b["dividends_payable"]
    assert v(n) >= 0 and has_text(n.get("calc")) and has_text(n.get("src"))
    declared = b["dividends_payable_declared"]
    assert isinstance(declared, list)
    assert sum(v(x["amount"]) for x in declared) <= v(n) + 1e-9
    periods = [x["period"] for x in declared]
    assert len(periods) == len(set(periods)) and all(p <= anchor_period() for p in periods)
    as_of = load("anchor")["as_of"]
    open_rows = [h for h in d["history"] if h["decided_date"] <= as_of < h["pay_date"]]
    assert [h["year"] for h in open_rows] == [b["dividends_payable_year"]] * len(open_rows)
    for h in open_rows:
        assert abs(v(h["pool_declared"]) - v(n)) <= 0.05, "к выплате — сумма решения"
    if on_first_anchor():
        assert v(n) == 125.5 and b["dividends_payable_year"] == 2025 and periods == ["2025Q4"]
        assert abs(9.71 * v(load("shares")["issued_total"]) / 1000 - 125.529) < 0.001     # решение ГОСА 30.06.2026


def test_prev_year_end_loans_by_segment():
    b = load("balance")
    p = b["prev_year_end"]
    year_end = f"{int(anchor_period()[:4]) - 1}Q4"
    assert p["as_of"] == b["history"][year_end]["date"]
    assert abs(v(p["loans_corporate"]) + v(p["loans_retail"]) - v(b["history"][year_end]["loans"])) < 1e-6
    if on_first_anchor():
        assert abs(v(p["loans_corporate"]) - 17130.8) < 1e-6 and abs(v(p["loans_retail"]) - 7145.0) < 1e-6
        # в определении банка (с обратным репо 70,4 и 147,4) — 17 201,2 и 7 292,4: валовые кредиты отчёта на 31.12.2025
        assert abs(17201.2 + 7292.4 - v(b["history"][year_end]["loans_gross_reported"])) < 1e-6


def test_balance_history():
    b = load("balance")
    h = b["history"]
    a = h[anchor_period()]
    books = {k: v(n) for k, n in b["books"].items()}
    assert a["date"] == b["as_of"]
    assert abs(v(a["loans"]) - sum(books[x] for x in LOAN_BOOKS)) < 1e-6
    assert abs(v(a["funds"]) - books["retail_current"] - books["retail_term"] - books["corp_funds"]) < 1e-6
    assert abs(v(a["iea"]) - v(b["iea"])) < 1e-6 and v(a["bv_common"]) == v(b["equity"]["bv_common"])
    assert v(a["total_assets"]) == v(b["total_assets"]) and v(a["allowance_ac"]) == v(b["allowance_ac"])
    assert v(a["equity_total"]) == v(b["equity"]["total"]) and v(a["equity_shareholders"]) == v(b["equity"]["shareholders"])
    # валовые кредиты отчёта несут обратное репо, которое книги держат в ликвидности
    assert abs(v(a["loans_gross_reported"]) - v(a["loans"]) - v(b["liquidity"]["reverse_repo"])) < 1e-6
    for p, row in h.items():
        assert row["date"] == q_end(p).isoformat(), p
        assert v(row["loans_ac_gross"]) == v(row["loans"]), f"{p}: отдельной книги кредитов по СС нет"
        assert v(row["loans"]) <= v(row["loans_gross_reported"]), p
        assert v(row["loans"]) < v(row["iea"]) < v(row["total_assets"]), p
        assert 0 < v(row["bv_common"]) < v(row["equity_shareholders"]) < v(row["equity_total"]) < v(row["funds"]), p


# ------------------------------------------------------------------ книги ЧПД

def test_nii_books_close_equals_balance():
    b, nb = load("balance"), load("nii_books")
    assert nb["period"] == anchor_period() and nb["as_of"] == b["as_of"]
    assert v(nb["days"]) == q_days(anchor_period())
    prev = b["history"][q_prev(anchor_period())]
    opened = 0.0
    for name in BOOKS:
        row = nb["books"][name]
        assert v(row["balance_close"]) == v(b["books"][name]), name
        # средний остаток — полусумма концов (у книг физлиц концы — округлённые доли одного остатка: до 0,05)
        assert abs(v(row["balance_avg"]) - (v(row["balance_open"]) + v(row["balance_close"])) / 2) < 0.05, name
        opened += v(row["balance_open"]) if name in LOAN_BOOKS else 0.0
    assert abs(opened - v(prev["loans"])) < 1e-6, "остатки кредитных книг на начало квартала ≠ истории баланса"


def test_nii_books_rates_and_total():
    nb = load("nii_books")
    days = v(nb["days"])
    inc = exp = iea = 0.0
    for name in BOOKS:
        row = nb["books"][name]
        assert v(row["interest_q"]) > 0, f"{name}: проценты — величиной"
        # ставка = проценты / средний остаток × 365 / дни — с точностью записи процентов (0,01 млрд ₽)
        tol = 0.005 / v(row["balance_avg"]) * 365 / days + 2e-6
        assert abs(v(row["rate_anchor"]) - v(row["interest_q"]) / v(row["balance_avg"]) * 365 / days) < tol, name
        if name in ASSET_BOOKS:
            inc += v(row["interest_q"])
            iea += v(row["balance_avg"])
        else:
            exp += v(row["interest_q"])
    assert abs(inc - v(nb["interest_assets_q"])) < 1e-6 and abs(exp - v(nb["interest_liabilities_q"])) < 1e-6
    total = inc - exp - v(nb["dia_q"]) + v(nb["other_interest_net_q"])
    assert abs(total - v(nb["nii_q"])) <= ROUND, f"проценты книг {total:.3f} ≠ ЧПД {v(nb['nii_q'])}"
    assert abs(v(nb["iea_avg"]) - iea) < 1e-6
    assert abs(v(nb["nim_eng_q"]) - v(nb["nii_q"]) * 365 / days / iea) < 2e-6
    assert nb["rates_carry_residual"] is False
    q = load("pnl_quarterly")["quarters"][anchor_period()]
    assert v(nb["nii_q"]) == v(q["nii"]) and v(nb["dia_q"]) == v(q["dia"])
    b = load("balance")["books"]
    assert abs(v(nb["current_share_anchor"]) - v(b["retail_current"]) / (v(b["retail_current"]) + v(b["retail_term"]))) < 5e-6
    if on_first_anchor():                          # ЧПД 208,8 и страхование вкладов 19,4 — Databook «2.P&L» B12, B11
        assert (round(inc, 1), round(exp, 1), v(nb["dia_q"]), v(nb["other_interest_net_q"]), v(nb["nii_q"])) == \
            (1115.7, 883.7, 19.4, -3.8, 208.8), "1 115,7 − 883,7 − 19,4 − 3,8 = 208,8"
        assert abs(v(nb["nim_eng_q"]) - 0.025889) < 6e-7 and v(nb["current_share_anchor"]) == 0.26


def test_key_average_of_the_anchor_quarter():
    nb, q = load("nii_books"), load("pnl_quarterly")["quarters"]
    assert v(nb["key_avg_anchor_q"]) == v(q[anchor_period()]["key_avg"])
    assert "sha256" in nb["key_avg_anchor_q"]["src"]
    if on_first_anchor():                          # средняя ключевая 2К2026 по календарным дням — 14,6181 %
        assert abs(v(nb["key_avg_anchor_q"]) - 0.146181) < 1e-6


# ------------------------------------------------------------------ ОПУ: отчётный базис и три прибыли

LINES = ("nii", "llp_debt_fa", "fees_net", "insurance_net", "noncore_net", "opex", "misc_net")


def test_pnl_identities():
    """Тождества ОПУ в каждом квартале ряда: прибыль до налога движка — сумма семи строк (прочее — остаток), вся
    прибыль = прибыль до налога + налог; прибыль акционеров = вся прибыль − неконтрольные доли; отчётные строки —
    прибыль до налога отчёта плюс убыток дочерних компаний для перепродажи (после налога) = прибыль до налога движка;
    прибыль обыкновенных акционеров = прибыль акционеров − выплаты по бессрочным инструментам."""
    for p, r in load("pnl_quarterly")["quarters"].items():
        assert abs(sum(v(r[k]) for k in LINES) - v(r["pbt"])) < 2e-6, f"{p}: pbt ≠ сумме семи строк"
        assert abs(v(r["pbt"]) + v(r["tax"]) - v(r["ni"])) < ROUND, f"{p}: ni ≠ pbt + tax"
        assert abs(v(r["ni"]) - v(r["ni_nci"]) - v(r["ni_shareholders"])) < ROUND, f"{p}: ni_shareholders ≠ ni − ni_nci"
        rep = r["reported"]
        assert abs(v(rep["pbt"]) + v(rep["np_resale_subs"]) - v(r["pbt"])) < 2e-6, f"{p}: pbt движка ≠ отчёт + перепродажа"
        assert v(rep["tax"]) == v(r["tax"]) and v(rep["ni"]) == v(r["ni"]), p
        assert abs(v(rep["pbt"]) + v(rep["tax"]) - v(rep["np_after_tax"])) < ROUND, p
        assert abs(v(rep["np_after_tax"]) + v(rep["np_resale_subs"]) - v(rep["ni"])) < ROUND, p
        assert v(r["noncore_net"]) == 0.0, f"{p}: непрофильного блока у ВТБ нет"
        assert v(r["opex"]) < 0 and v(r["dia"]) > 0 and v(r["nii"]) > 0 and v(rep["np_resale_subs"]) <= 0, f"{p}: знаки"
        if r["at1_coupon"]["v"] is not None:
            assert v(r["at1_coupon"]) > 0 and abs(v(r["ni_shareholders"]) - v(r["at1_coupon"]) - v(r["ni_ordinary"])) < 2e-6, p


def test_years_are_sums_of_their_quarters():
    """Годы ОПУ — колонки Databook: сумма четырёх кварталов равна году по каждой строке (с точностью печати)."""
    p = load("pnl_quarterly")
    q = p["quarters"]
    for y, rec in p["years"].items():
        quarters = [f"{y}Q{k}" for k in range(1, 5)]
        assert all(x in q for x in quarters), y
        for f in ("nii", "fees_net", "llp_debt_fa", "opex", "tax", "ni", "ni_shareholders", "ni_nci"):
            s = sum(v(q[x][f]) for x in quarters)
            assert abs(s - v(rec[f])) <= 0.25, f"{y}.{f}: Σ кварталов {s:.2f} ≠ {v(rec[f])}"
        assert abs(sum(v(q[x]["reported"]["pbt"]) for x in quarters) - v(rec["pbt_reported"])) <= 0.25, y


def test_three_profits_on_the_anchor():
    """Три прибыли ВТБ: прибыль движка — прибыль акционеров банка по МСФО (строка отчёта); вся прибыль группы —
    база дивидендной политики и числитель ROE банка; прибыль обыкновенных акционеров — за вычетом выплат по
    бессрочным инструментам (купон мимо прибыли). Упр. ряд повторяет те же строки; суммы года и полугодия — строки
    Databook и отчёта."""
    q = load("pnl_quarterly")["quarters"]
    a = q[anchor_period()]
    m = load("mgmt_quarterly")["quarters"][anchor_period()]
    assert v(a["ni_shareholders"]) == v(m["np_shareholders"]) and v(a["ni"]) == v(m["np"])
    assert "P&L!" in a["ni_shareholders"]["src"] and a["ni_shareholders"].get("estimated") is not True
    if on_first_anchor():                          # Databook «2.P&L»: B46, B49, B50, B52, B53; отчёт за 6М2026, с. 20
        assert (v(a["ni_shareholders"]), v(a["ni"]), v(a["ni_nci"]), v(a["tax"])) == (88.1, 92.6, 4.5, -18.4)
        assert (v(a["reported"]["pbt"]), v(a["reported"]["np_resale_subs"])) == (111.3, -0.3) and abs(v(a["pbt"]) - 111.0) < 1e-9
        assert v(a["at1_coupon"]) == 10.8 and abs(v(a["ni_ordinary"]) - 77.3) < 1e-9
        assert abs(sum(v(q[f"2025Q{k}"]["ni_shareholders"]) for k in range(1, 5)) - 483.7) <= 0.001
        assert abs(sum(v(q[f"2025Q{k}"]["ni"]) for k in range(1, 5)) - 502.1) <= 0.001
        assert abs(sum(v(q[p]["ni_shareholders"]) for p in ("2026Q1", "2026Q2")) - 216.1) <= 0.001
        assert abs(sum(v(q[p]["ni"]) for p in ("2026Q1", "2026Q2")) - 225.2) <= 0.001


def test_profit_of_the_dividend_years():
    """Годы проверки политики: прибыль акционеров и вся прибыль группы (база политики) — суммы кварталов ряда
    (неполный год — по якорь); источник полного года — строка Databook."""
    d, q = load("dividends"), load("pnl_quarterly")["quarters"]
    for y, rec in d["years"].items():
        quarters = [p for p in q if p.startswith(y)]
        for f, row in (("ni_shareholders", "ni_shareholders"), ("ni_group", "ni")):
            s = sum(v(q[p][row]) for p in quarters)
            assert abs(s - v(rec[f])) <= 0.2, f"{y}.{f}: Σ кварталов {s:.3f}"
        if rec["complete"]:
            assert len(quarters) == 4 and "databook" in rec["ni_group"]["src"], y
        else:
            assert rec["through"] == anchor_period() and quarters[-1] == anchor_period(), y
    if on_first_anchor():
        got = {y: (v(r["ni_shareholders"]), v(r["ni_group"])) for y, r in d["years"].items()}
        assert got == {"2024": (535.3, 551.4), "2025": (483.7, 502.1), "2026": (216.1, 225.2)}


# ------------------------------------------------------------------ капитал

def test_capital_slots_of_the_banking_group():
    """Слоты ядра — капитал банковской группы по форме 0409805: базовый (CET1 ядра) + добавочный + дополнительный (T2
    ядра) = собственные средства; три знаменателя раскрыты, нормативы воспроизводятся делением; Н20.0 якоря — до
    вычета дивиденда, объявленного до якоря и выплаченного после."""
    c, b = load("capital"), load("balance")
    g = c["group_capital"]
    assert abs(v(g["base"]) + v(g["additional"]) + v(g["supplementary"]) - v(g["total"])) <= 0.002
    assert abs(v(g["base"]) + v(g["additional"]) - v(g["tier1"])) <= 0.002
    assert v(c["bank_base_capital"]) == v(g["base"]) == v(c["basel"]["cet1"]) and v(c["t2_recognized"]) == v(g["supplementary"])
    bs = c["basel"]
    assert v(bs["rwa"]) == v(bs["rwa_n20_0"])
    assert abs(v(g["total"]) / v(bs["rwa_n20_0"]) - v(c["n20_0"]["value"])) < 5e-5
    assert abs(v(g["base"]) / v(bs["rwa_n20_1"]) - v(c["n1_1_bank"]["value"])) < 5e-5
    assert abs(v(g["tier1"]) / v(bs["rwa_n20_2"]) - v(c["n20_2"])) < 5e-5
    assert abs(v(bs["total_ratio"]) - v(g["total"]) / v(bs["rwa"])) < 1e-6
    assert abs(v(c["at1"]["regulatory_amount"]) - v(g["additional"])) < 1e-9
    assert v(c["at1"]["amount"]) == v(b["equity"]["at1"]) and v(c["at1"]["coupon_quarter"]) == 4
    assert c["at1"]["coupon_annual"].get("estimated") is True and has_text(c["at1"]["coupon_annual"]["calc"])
    assert c["n20_0"]["as_of"] == c["as_of"] == b["as_of"]
    assert c["n20_0"]["pre_dividend"] is (v(b["dividends_payable"]) > 0) and has_text(c["n20_0"]["pre_dividend_note"])
    assert v(c["n1_1_bank"]["value"]) < v(c["n20_2"]) < v(c["n20_0"]["value"])
    last = c["history"][-1]
    assert last["period"] == anchor_period() and v(last["n20_0"]) == v(c["n20_0"]["value"]) and v(last["n20_1"]) == v(c["n1_1_bank"]["value"])
    assert [h["period"] for h in c["history"]] == sorted(h["period"] for h in c["history"])
    for h in c["history"]:
        assert abs(v(h["capital_base"]) + v(h["capital_additional"]) + v(h["capital_supplementary"]) - v(h["capital_total"])) <= 0.002, h["period"]
    if on_first_anchor():                          # форма 0409805 на 01.07.2026; отчётность за 6М2026, прим. 28 (с. 43)
        assert (v(c["n20_0"]["value"]), v(c["n1_1_bank"]["value"]), v(c["n20_2"])) == (0.1066, 0.0726, 0.087)
        assert (v(g["total"]), v(g["base"]), v(g["additional"]), v(g["supplementary"])) == (2656.343, 1800.333, 362.75, 493.26)
        assert (v(bs["rwa_n20_0"]), v(bs["rwa_n20_1"]), v(bs["rwa_n20_2"])) == (24916.3, 24791.0, 24863.7)
        prev = {h["period"]: h for h in c["history"]}["2025Q4"]      # та же примечание, колонка 31.12.2025
        assert round(v(prev["capital_total"]), 1) == 2495.4 and round(v(prev["capital_supplementary"]), 1) == 550.9
        assert round(v(prev["capital_base"]) + v(prev["capital_additional"]), 1) == 1944.5
        assert c["n20_0"]["estimated"] is False and c["n1_1_bank"]["estimated"] is False


def test_perpetual_instruments_and_their_coupon():
    """Бессрочные инструменты (AT1 в капитале МСФО): по валютам в сумме — остаток; выплаты по кварталам — те же, что в
    строке ОПУ; выплачено с начала года и за четыре квартала — суммы кварталов."""
    a, q = load("capital")["at1"], load("pnl_quarterly")["quarters"]
    assert abs(v(a["by_currency"]["rub"]) + v(a["by_currency"]["fx"]) - v(a["amount"])) < 1e-6
    for p, n in a["by_quarter"].items():
        assert v(n) == v(q[p]["at1_coupon"]), p
    last4, ytd = [], year_quarters(anchor_period())
    p = anchor_period()
    for _ in range(4):
        last4.append(p)
        p = q_prev(p)
    assert abs(sum(v(a["by_quarter"][x]) for x in last4) - v(a["coupon_ltm"])) < 1e-6
    assert abs(sum(v(a["by_quarter"][x]) for x in ytd) - v(a["coupon_paid_ytd"])) < 1e-6
    if on_first_anchor():                          # отчётность за 6М2026: с. 20 (18,6 за 6М) и с. 31 (рублёвые 263,0)
        assert (v(a["amount"]), v(a["by_currency"]["rub"]), v(a["coupon_paid_ytd"]), v(a["coupon_ltm"])) == (368.0, 263.0, 18.6, 37.1)


def test_curve_and_the_revaluation_reserve():
    c = load("capital")
    curve = [v(c["ofz_curve_anchor"][t]) for t in ("1", "3", "5", "10")]
    assert all(0.02 < x < 0.4 for x in curve) and c["ofz_curve_anchor"]["as_of"] == c["as_of"]
    assert c["fvoci_reserve"].get("estimated") is True and has_text(c["fvoci_reserve"]["calc"])
    assert abs(v(c["fvoci_reserve"]) + v(c["insurance_fin_reserve"]) - v(c["fvoci_reserve_net_of_insurance"])) <= 0.05
    assert v(c["fvoci_reserve_check"]) == v(load("balance")["equity"]["other_funds"]), "сверка фонда — строка «прочие фонды»"


# ------------------------------------------------------------------ акции

def test_shares_arithmetic():
    """Акции одной категории после конвертации привилегированных 29.04.2026: размещённые − у компаний группы = в
    обращении; экономически собственных сверх них нет."""
    s = load("shares")
    assert abs(v(s["issued_total"]) - v(s["treasury_ordinary"]) - v(s["outstanding_total"])) < 1e-6
    assert v(s["issued_ordinary"]) == v(s["issued_total"]) and v(s["outstanding_ordinary"]) == v(s["outstanding_total"])
    assert v(s["issued_preferred"]) == 0.0 and s["outstanding_preferred"]["v"] is None
    assert v(s["economic_treasury"]) == 0.0 and has_text(s["economic_treasury"]["calc"])
    assert s["by_ticker"] == {"VTBR": {"class": "ordinary"}}
    if on_first_anchor():                          # отчётность за 6М2026, прим. 23 (с. 31): 12 927 766 417 и 79 783 634
        assert (v(s["issued_total"]), v(s["treasury_ordinary"]), v(s["outstanding_total"])) == (12927.766417, 79.783634, 12847.982783)
        assert v(s["par_value"]) == 50.0


def test_corporate_actions_carry_the_consolidation_the_conversion_and_the_registered_issue():
    """Корпоративные события по порядку: выпуски увеличивают число акций и идут цепочкой (до = после прежнего);
    консолидация 5000:1 — одна, коэффициент 0,0002 узлом; конвертация привилегированных акций — последний выпуск, он
    даёт нынешнее число акций; зарегистрированный и не размещённый выпуск — событие, число акций не меняет
    (подписка до 6 292 651 866 акций по 87 ₽ — `pending_issue`)."""
    s = load("shares")
    acts = s["corporate_actions"]
    assert [a["date"] for a in acts] == sorted(a["date"] for a in acts)
    assert {a["kind"] for a in acts} <= {"split", "issue", "buyback_program", "deal", "event"}
    for a in acts:
        assert has_text(a["title"]) and "sha256" in a["src"], a["date"]
    for x, y in zip(acts, acts[1:]):
        assert abs(v(y["shares_before"]) - v(x["shares_after"])) < 1e-6, f"{y['date']}: цепочка числа акций"
    splits = [a for a in acts if a["kind"] == "split"]
    assert len(splits) == 1
    sp = splits[0]
    assert v(sp["factor"]) == 0.0002 and sp["date"] == "2024-07-11" and sp["first_trade_date"] == "2024-07-15"
    assert abs(v(sp["shares_before_as_reported"]) * v(sp["factor"]) / 1e6 - v(sp["shares_before"])) < 1e-6
    issues = [a for a in acts if a["kind"] == "issue"]
    assert all(v(a["shares_after"]) > v(a["shares_before"]) for a in issues)
    assert v(issues[-1]["shares_after"]) == v(s["issued_total"]), "последний выпуск даёт нынешнее число акций"
    conv = issues[-1]
    assert conv["date"] == "2026-04-29" and v(conv["amount"]) == 0.0 and "привилегированных" in conv["title"]
    events = [a for a in acts if a["kind"] == "event" and a["date"] > load("anchor")["as_of"]]
    pend = s["pending_issue"]
    assert len(events) == 1 and v(events[0]["shares_after"]) == v(events[0]["shares_before"]) == v(s["issued_total"])
    assert v(events[0]["price"]) == v(pend["price"]) and events[0]["date"] == pend["registered"]
    assert abs(v(pend["max_shares"]) * v(pend["price"]) / 1000 - v(pend["max_amount"])) < 0.01
    if on_first_anchor():                          # решение о конвертации: 6 307 348 134 новых обыкновенных акций
        assert abs(v(conv["shares_after"]) - v(conv["shares_before"]) - 6307.348134) < 1e-6
        assert (v(pend["max_shares"]), v(pend["price"])) == (6292.651866, 87.0) and pend["registered"] == "2026-07-17"


# ------------------------------------------------------------------ мосты

def test_bridge_values_are_window_statistics():
    """Значение моста — названная в calc статистика разностей по своему окну (среднее; у C/I — медиана: разовое
    восстановление резервов 3К2025 искажает среднее); разброс — выборочное стандартное отклонение по кварталам,
    названным в его calc; разность — движок минус упр."""
    b = load("bridge_mgmt_ifrs")
    span = re.compile(r"(\d{4}Q[1-4])–(\d{4}Q[1-4])")
    for x in ("cor", "nim", "cir"):
        lo, hi = b[x]["window"]
        gaps = [v(h["gap"]) for h in b[x]["history"] if lo <= h["period"] <= hi]
        assert len(gaps) == v(b[x]["n"]), x
        stat = statistics.median if "медиана" in b[x]["value"]["calc"] else statistics.fmean
        assert abs(stat(gaps) - v(b[x]["value"])) < 2e-6, x
        m = span.search(b[x]["sd"]["calc"])
        slo, shi = m.groups() if m else (lo, hi)
        sd = [v(h["gap"]) for h in b[x]["history"] if slo <= h["period"] <= shi]
        assert abs(statistics.stdev(sd) - v(b[x]["sd"])) < 2e-6, x
        for h in b[x]["history"]:
            assert abs(v(h["engine"]) - v(h["mgmt"]) - v(h["gap"])) < 2e-6, f"{x} {h['period']}"
            if "gap_x4" in h:
                assert abs(v(h["engine_x4"]) - v(h["mgmt"]) - v(h["gap_x4"])) < 2e-6, f"{x} {h['period']}"
    assert len([h for h in b["nim"]["history"] if b["nim"]["window"][0] <= h["period"]]) == len(year_quarters(anchor_period()))
    if on_first_anchor():
        assert (v(b["cor"]["value"]), v(b["nim"]["value"]), v(b["cir"]["value"])) == (-0.00073, 0.0001, 0.004873)
        assert v(b["cor"]["n"]) == v(b["cir"]["n"]) == 6 and b["cor"]["window"] == ["2025Q1", "2026Q2"]


def test_bridge_gate_reads_a_small_drift_on_the_anchor():
    """Гейт дрейфа моста сравнивает последнюю разность истории со значением моста: на якоре дрейф меньше порогов
    книги (0,2 п.п. для CoR, 0,3 п.п. для ЧПМ)."""
    b = load("bridge_mgmt_ifrs")
    for x, limit in (("cor", 0.002), ("nim", 0.003)):
        last = b[x]["history"][-1]
        assert last["period"] == anchor_period()
        assert abs(v(last["gap"]) - v(b[x]["value"])) < limit, x


def test_bridge_engine_definitions():
    """Значения движка в истории моста воспроизводятся из строк ОПУ и истории баланса: CoR — резервы по долговым
    активам к средней сумме трёх кредитных книг; ЧПМ — ЧПД к средним процентным активам движка (пять книг активов);
    C/I — расходы к доходам до резервов (ЧПД, комиссии, страхование, прочее)."""
    b, q, h = load("bridge_mgmt_ifrs"), load("pnl_quarterly")["quarters"], load("balance")["history"]
    for row in b["cir"]["history"]:
        p = row["period"]
        income = sum(v(q[p][k]) for k in ("nii", "fees_net", "insurance_net", "misc_net", "noncore_net"))
        assert abs(-v(q[p]["opex"]) / income - v(row["engine"])) < 2e-6, f"cir {p}"
    checked = 0
    for row in b["cor"]["history"]:
        p = row["period"]
        if p in h and q_prev(p) in h:
            avg = (v(h[p]["loans"]) + v(h[q_prev(p)]["loans"])) / 2
            assert abs(-v(q[p]["llp_debt_fa"]) * 365 / q_days(p) / avg - v(row["engine"])) < 2e-6, f"cor {p}"
            assert abs(-v(q[p]["llp_debt_fa"]) * 4 / avg - v(row["engine_x4"])) < 2e-6, f"cor x4 {p}"
            checked += 1
    for row in b["nim"]["history"]:
        p = row["period"]
        if p in h and q_prev(p) in h:
            avg = (v(h[p]["iea"]) + v(h[q_prev(p)]["iea"])) / 2
            assert abs(v(q[p]["nii"]) * 365 / q_days(p) / avg - v(row["engine"])) < 2e-6, f"nim {p}"
            assert abs(v(q[p]["nii"]) * 4 / avg - v(row["engine_x4"])) < 2e-6, f"nim x4 {p}"
            checked += 1
    assert checked >= 2 * len(year_quarters(anchor_period())), "отчётные кварталы года якоря проверены"
    a = anchor_period()
    assert abs(v(b["nim"]["history"][-1]["engine"]) - v(load("nii_books")["nim_eng_q"])) < 2e-6, f"ЧПМ движка {a}"


def test_bridge_history_uses_the_printed_management_values():
    """В истории моста — упр. значения, как их печатает Databook (точных значений банк не публикует); пересчёт по
    определению банка — рядом, тот же, что в упр. ряду."""
    b, m = load("bridge_mgmt_ifrs"), load("mgmt_quarterly")["quarters"]
    for x in ("cor", "nim", "cir"):
        for h in b[x]["history"]:
            row = m[h["period"]]
            assert v(h["mgmt"]) == v(row[x]), f"{x} {h['period']}"
            assert v(h["mgmt_recalc"]) == v(row[x + "_recalc"]), f"{x} {h['period']}"


def test_bridge_ras_nii():
    """Мост РСБУ → МСФО у ВТБ — заглушка до сборки индикаторов (формы 0409101/0409102 банка); собранный мост ЧПД —
    отношение МСФО к РСБУ прошлого квартала."""
    r, q = load("bridge_ras_ifrs"), load("pnl_quarterly")["quarters"]
    if is_stub(r):
        assert "nii" not in r and r["quarters"] == [], "заглушка без рядов"
        return
    n = r["nii"]
    assert n["method"] == "prev_quarter" and n["window"] == [anchor_period(), anchor_period()]
    for row in n["quarters"]:
        assert v(row["ifrs"]) == v(q[row["period"]]["nii"])
        assert abs(v(row["ifrs"]) / v(row["ras"]) - v(row["ratio"])) < 2e-6
    assert n["quarters"][-1]["period"] == anchor_period() and v(n["value"]) == v(n["quarters"][-1]["ratio"])


# ------------------------------------------------------------------ гайденс

def test_guidance_items():
    """Прогноз банка на год якоря: у пункта с числом — вид (точка, нижняя или верхняя граница), группа, слова
    документа, событие и день; точка с допуском несёт `tol`; рост прибыли — к всей прибыли группы прошлого года
    (база — сумма кварталов ряда); чего банк не называет — null «не раскрыто»; пересмотры — раньше действующего пункта."""
    g, q = load("guidance"), load("pnl_quarterly")["quarters"]
    year = g["year"]
    assert year == int(anchor_period()[:4])
    it = g["items"]
    for k, n in it.items():
        if n["v"] is None:
            assert "не раскрыто" in n["calc"], k
            continue
        assert n["kind"] in ("point", "min", "max") and n["scope"] == "group" and has_text(n["text"]) and has_text(n["event"]), k
        assert dt.date.fromisoformat(n["date"]) <= dt.date.fromisoformat(g["as_of"]), k
        assert "tol" not in n or (n["kind"] == "point" and n["tol"] > 0), k
    base = sum(v(q[f"{year - 1}Q{k}"]["ni"]) for k in range(1, 5))
    assert abs(v(it["net_profit"]) / base - 1 - v(it["op_np_growth"])) < 5e-4
    assert f"{base:.1f}" in it["op_np_growth"]["calc"] or f"{base:.1f}".replace(".", ",") in it["op_np_growth"]["calc"]
    assert abs(it["net_profit"]["tol"] / base - it["op_np_growth"]["tol"]) < 1e-3, "допуск роста — допуск прибыли к базе"
    keys = {h["key"] for h in g["history"]}
    assert keys <= set(it)
    assert [h["date"] for h in g["history"]] == sorted(h["date"] for h in g["history"])
    for h in g["history"]:
        assert h["date"] < it[h["key"]]["date"] and has_text(h["event"]), h["key"]
    if on_first_anchor():                          # звонок 28.07.2026 (с. 2–5), слайд 14 презентации
        assert g["as_of"] == "2026-07-28"
        got = {k: v(it[k]) for k in ("net_profit", "roe", "nim", "cor_max", "cir", "n20_0", "key_rate_year_end")}
        assert got == {"net_profit": 600.0, "roe": 0.2, "nim": 0.03, "cor_max": 0.011, "cir": 0.4, "n20_0": 0.105,
                       "key_rate_year_end": 0.135}
        hist = {h["key"]: h["value"] for h in g["history"]}
        assert (v(hist["net_profit"]), hist["net_profit"]["tol"]) == (625.0, 25.0), "прогноз 25.02.2026: 600–650"
        assert (v(hist["roe"]), hist["roe"]["tol"]) == (0.22, 0.01) and v(hist["key_rate_year_end"]) == 0.12


# ------------------------------------------------------------------ календарь

KINDS = {"ifrs", "databook", "dividend_decision", "record", "form805", "ops_release", "ifrs_monthly", "cbr_rate",
         "cbr_forecast", "call_option", "deal", "regulation"}


def test_calendar_events():
    c = load("calendar")
    ids = [e["id"] for e in c["events"]]
    assert len(ids) == len(set(ids))
    assert [e["date"] for e in c["events"]] == sorted(e["date"] for e in c["events"])
    for e in c["events"]:
        assert e["kind"] in KINDS, e["id"]
        assert has_text(e["title"]) and "sha256" in e["src"], e["id"]
        assert isinstance(e["confirmed"], bool) and e["precision"] in ("day", "window"), e["id"]
        if e.get("estimated") or e["precision"] == "window":
            assert e.get("estimated") is True and e["confirmed"] is False and e["precision"] == "window", e["id"]
            assert e["earliest"] <= e["date"] <= e["latest"], e["id"]
        else:
            assert "earliest" not in e and "latest" not in e, e["id"]
        if e["kind"] in ("ifrs", "databook", "dividend_decision", "record", "form805"):
            assert e["covers"] and len(e["covers"]) == 6 and e["covers"][4] == "Q", e["id"]
        elif e["kind"] in ("ops_release", "ifrs_monthly"):
            assert e["covers"][4] == "M", e["id"]
        else:
            assert e["covers"] is None, e["id"]
        if e["kind"] == "deal":
            assert e["in_book"] is False
        else:
            assert "in_book" not in e


def test_calendar_carries_the_events_the_book_waits_for():
    """Календарь на 12 месяцев вперёд: МСФО за каждый квартал, который закроется в горизонте; форма 0409805 за первый
    прогнозный квартал; заседания Банка России; рекомендация и собрание по дивиденду за год якоря (годовой календарь);
    размещение зарегистрированного выпуска — сделка вне книги."""
    c = load("calendar")
    by_id = {e["id"]: e for e in c["events"]}
    kinds = {k: [e for e in c["events"] if e["kind"] == k] for k in KINDS}
    nxt = anchor_period()
    y, k = int(nxt[:4]), int(nxt[-1])
    nxt = f"{y + 1}Q1" if k == 4 else f"{y}Q{k + 1}"
    closing = [e for e in kinds["ifrs"] if e["covers"] == nxt]
    assert len(closing) == 1, "МСФО, закрывающее первый прогнозный квартал"
    covered = sorted(e["covers"] for e in kinds["ifrs"])
    assert covered[0] == nxt and len(covered) >= 4 and len(set(covered)) == len(covered)
    assert [e for e in kinds["form805"] if e["covers"] == nxt], "форма 0409805 за первый прогнозный квартал"
    seed = load("dividends")["register_seed"]
    for r in seed:
        if r["status"] == "declared":
            rec = [e for e in kinds["record"] if e["covers"] == f"{r['year']}Q4"]
            assert len(rec) == 1 and rec[0]["date"] == r["record_date"] and rec[0]["confirmed"], r["year"]
    assert len(kinds["cbr_rate"]) + len(kinds["cbr_forecast"]) >= 8
    year = anchor_period()[:4]
    assert len([e for e in kinds["dividend_decision"] if e["covers"] == f"{year}Q4"]) >= 2, "рекомендация и собрание за год"
    assert len(kinds["deal"]) == 1
    last = max(dt.date.fromisoformat(e["date"]) for e in c["events"])
    assert (last - dt.date.fromisoformat(c["as_of"])).days >= 365, "календарь — не меньше чем на 12 месяцев вперёд"
    if on_first_anchor():
        ifrs = by_id["ifrs-2026Q3"]
        assert ifrs["date"] == "2026-10-30" and ifrs["confirmed"] is True, "календарь инвестора банка"
        assert by_id["ifrs-2026Q4"]["estimated"] is True and by_id["ifrs-2026Q4"]["covers"] == "2026Q4"
        assert by_id["cbr-2026-10-23"]["kind"] == "cbr_forecast" and by_id["cbr-2026-12-18"]["kind"] == "cbr_rate"
        spo = by_id["spo-2026"]
        assert spo["kind"] == "deal" and spo["in_book"] is False and (spo["earliest"], spo["latest"]) == ("2026-10-20", "2026-11-30")
        assert [e["date"] for e in kinds["regulation"] if e["date"] >= "2027-01-01"] == ["2027-01-01", "2027-04-01", "2028-01-01"]


def test_form805_windows_follow_the_observed_lag():
    """Форма 0409805 за квартал появляется между 41-м и 73-м днём после квартала; годовая — позже (окно шире: от
    41-го дня, кончается не раньше 92-го)."""
    for e in load("calendar")["events"]:
        if e["kind"] == "form805":
            end = q_end(e["covers"])
            lo, hi = ((dt.date.fromisoformat(e[k]) - end).days for k in ("earliest", "latest"))
            if e["covers"].endswith("Q4"):
                assert lo >= 41 and hi >= 92, e["id"]
            else:
                assert (lo, hi) == (41, 73), e["id"]


@pytest.mark.deadline
def test_calendar_is_ahead_of_today():
    """Срок записи данных: закрывающее МСФО первого прогнозного квартала ещё впереди или книга уже перезаякорена."""
    c = load("calendar")
    today = dt.date.today()
    ahead = [e for e in c["events"] if dt.date.fromisoformat(e.get("latest") or e["date"]) >= today]
    assert len(ahead) >= 6, "календарь событий исчерпан — продлить"


# ------------------------------------------------------------------ аналоги

def test_peers():
    """Таблица аналогов: эмитента в ней нет (его строку собирает выпуск), ROE — прибыль к среднему капиталу. У ВТБ
    таблица не собрана: файл — заглушка, и это сказано словами (собрать до первого выпуска)."""
    p = load("peers")
    tickers = [b["ticker"] for b in p["banks"]]
    assert p["subject_ticker"] == "VTBR" and "VTBR" not in tickers
    if is_stub(p):
        assert tickers == [] and has_text(p["note"])
        return
    assert "SBER" in tickers and len(tickers) == len(set(tickers)) >= 4
    for b in p["banks"]:
        for k in ("bv", "ni_ltm", "shares_outstanding", "dps_ltm"):
            assert v(b[k]) > 0, f"{b['ticker']}.{k}"
        assert 0.03 < v(b["capital_ratio"]["value"]) < 0.4 and has_text(b["capital_ratio"]["name"]), b["ticker"]
        roe = v(b["ni_ltm"]) / ((v(b["bv"]) + v(b["bv_prev"])) / 2)
        assert abs(roe - v(b["roe_ltm"])) < 0.002, f"{b['ticker']}: ROE"
        assert v(b["shares_outstanding"]) <= v(b["shares_issued"]) + 1e-6, b["ticker"]
        assert has_text(b["name"]) and has_text(b["basis"]) and "sha256" in b["src"]
