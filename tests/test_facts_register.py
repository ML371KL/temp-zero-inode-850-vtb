"""Дивиденды по годам: история решений, стартовый реестр, источники (data/facts/dividends.json).

Годовой календарь ВТБ: одна строка истории на решение годового собрания, ключ — год прибыли (период строки —
4-й квартал года); всё «на акцию» — в нынешних акциях после консолидации 5000:1 (11.07.2024), значение
документа — рядом. Источник объявленного дивиденда — документ эмитента (отчёт об итогах голосования собрания);
брокерский календарь — только сверка, словами. Закрыт ли год прибыли до якоря, решает дата решения строки истории
(правило закрытого периода), поэтому период и дата решения обязательны в каждой строке. Стартовый реестр — решения с
экс-датой позже якоря: при годовом календаре запись несёт год без квартала.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tact

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
KINDS = ("manual", "news")
SOURCE_RE = re.compile(r"^(manual|news): \S")
SHA_RE = re.compile(r"sha256 ([0-9a-f]{16})")
PERIOD_RE = re.compile(r"^\d{4}Q4$")
RECORD_AFTER_DECISION = (10, 20)     # дней от решения собрания до даты реестра (закон об АО, ст. 42 п. 5)
FIRST_ANCHOR = "2026Q2"
# Имена полей и методов ответов брокерского API и пути к образцам ответов: в данных и документах о фактах их нет.
# Слова собраны из частей: сам тест — не «имя поля» для общего теста гигиены.
API_WORDS = tuple(a + b for a, b in (
    ("dividend", "Net"), ("record", "Date"), ("lastBuy", "Date"), ("payment", "Date"), ("declared", "Date"),
    ("close", "Price"), ("yield", "Value"), ("Get", "Dividends"), ("Get", "AssetReports"), ("Get", "LastPrices"),
    ("Get", "ForecastBy"), ("Instruments", "Service"), ("tinvest_", "samples"), ("invest-public", "-api")))
PUBLIC_TEXTS = [FACTS / "SCHEMA.md", ROOT / "docs" / "FACTS.md"]


def load(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def day(x: str) -> dt.date:
    return dt.date.fromisoformat(x)


def kinds(sources: list[str]) -> set[str]:
    return {s.split(":", 1)[0] for s in sources}


def records() -> list[tuple[str, dict]]:
    d = load("dividends")
    return [(f"history.{r['year']}", r) for r in d["history"]] + [(f"register_seed.{r['year']}", r) for r in d["register_seed"]]


def consolidations() -> list[tuple[str, float]]:
    return [(a["date"], float(a["factor"]["v"])) for a in load("shares")["corporate_actions"] if a["kind"] == "split"]


def issued_on(day_: str) -> float:
    """Размещённые акции на день (млн шт., в нынешних акциях): после последнего проведённого события не позже дня."""
    acts = [a for a in load("shares")["corporate_actions"] if a["date"] <= day_ and a["kind"] in ("issue", "split")]
    return float(acts[-1]["shares_after"]["v"])


# ------------------------------------------------------------------ формат строки истории

def test_history_is_one_row_per_decision_keyed_by_the_profit_year():
    h = load("dividends")["history"]
    years = [r["year"] for r in h]
    assert years == sorted(set(years)), "годы решений повторяются или идут не по порядку"
    for r in h:
        assert PERIOD_RE.match(r["period"]) and r["period"] == f"{r['year']}Q4", r["year"]
        assert r["label"] == f"за {r['year']} год", f"{r['year']}: слова решения"
        assert r["settlement"] == "T+1" and r["decided_by"], r["year"]
        for k in ("recommended_date", "decided_date", "record_date", "last_buy_date", "ex_date", "pay_date", "pay_deadline_others"):
            day(r[k])
        assert r["dps"]["v"] > 0 and r["pool_declared"]["v"] > 0
    before = load("dividends")["history_before"]
    assert [r["year"] for r in before] == sorted(r["year"] for r in before) and max(r["year"] for r in before) < min(years)
    if load("anchor")["period"] == FIRST_ANCHOR:
        got = [(r["year"], r["dps"]["v"]) for r in h]
        assert got == [(2024, 25.58), (2025, 9.71)], "решения ГОСА 30.06.2025 и 30.06.2026"
        assert [r["dps"]["v"] for r in before if r["year"] >= 2021] == [0.0, 0.0, 0.0], "за 2021–2023 годы не выплачивались"


def test_per_share_values_are_in_todays_shares_with_the_document_value_alongside():
    """Решение до консолидации: dps — в нынешних акциях, dps_as_declared — как в документе, split_factor —
    коэффициент консолидации (0,0002), dps = dps_as_declared / split_factor; решение после консолидации —
    коэффициент 1, значение документа то же."""
    cons = consolidations()
    assert cons == [("2024-07-11", 0.0002)], "консолидация 5000:1"
    d = load("dividends")
    for r in d["history"] + d["history_before"]:
        if r["dps"]["v"] == 0.0:                      # без выплаты (2021–2023 годы) пересчитывать нечего
            assert r["dps_as_declared"]["v"] == 0.0, r["year"]
            continue
        when = r.get("decided_date") or r["record_date"]
        want = 1.0
        for date_, factor in cons:
            if when < date_:
                want *= factor
        assert r["split_factor"] == pytest.approx(want), r["year"]
        assert r["dps"]["v"] == pytest.approx(r["dps_as_declared"]["v"] / want, rel=1e-6, abs=1e-9), r["year"]


def test_pool_is_dps_times_issued_shares_of_the_decision_day():
    """Сумма решения на обыкновенные акции — DPS × все размещённые обыкновенные акции на день решения (делитель
    политики), а не акции в обращении; на все категории — с привилегированными (до их конвертации 29.04.2026)."""
    for r in load("dividends")["history"]:
        n = issued_on(r["decided_date"])
        assert abs(r["pool_declared"]["v"] - r["dps"]["v"] * n / 1000) < 0.001, r["year"]
        assert r["pool_all_classes"]["v"] >= r["pool_declared"]["v"] - 1e-9, r["year"]
    if load("anchor")["period"] == FIRST_ANCHOR:
        last = load("dividends")["history"][-1]
        assert abs(last["pool_declared"]["v"] - 125.529) < 0.001          # 125 528 611 905,49 ₽ — решение ГОСА 30.06.2026
        n_out = load("shares")["outstanding_total"]["v"]
        assert abs(last["dps"]["v"] * n_out / 1000 - 124.754) < 0.001, "отток — на акции в обращении"
        first = load("dividends")["history"][0]
        assert (first["pool_declared"]["v"], first["pool_all_classes"]["v"]) == (137.363, 275.75)


def test_decided_date_and_record_date_rule():
    """Дата реестра — через 10–20 дней после решения; экс-дата — день реестра (T+1); последний день покупки — торговый
    день перед ним; срок выплаты номинальным держателям — 10 рабочих дней (12–18 календарных)."""
    for where, r in records():
        decided, record = day(r["decided_date"]), day(r["record_date"])
        assert RECORD_AFTER_DECISION[0] <= (record - decided).days <= RECORD_AFTER_DECISION[1], where
        assert r["ex_date"] == r["record_date"], f"{where}: экс-дата ≠ дате реестра"
        buy = day(r["last_buy_date"])
        assert 0 < (record - buy).days <= 5 and buy.weekday() < 5, f"{where}: последний день покупки"
        assert 12 <= (day(r["pay_date"]) - record).days <= 18, f"{where}: срок выплаты"
        assert day(r["recommended_date"]) < decided, f"{where}: рекомендация совета — до решения"
        assert decided > dt.date(int(r["year"]), 12, 31), f"{where}: решение раньше конца года прибыли"


def test_sources_have_kind_and_document():
    """Источник решения — строка «вид: …» с документом реестра; документ эмитента (отчёт об итогах голосования)
    есть у каждой строки; новость о решении, если есть, — с датой и адресом. Запись реестра со статусом «объявлен»
    подтверждена двумя видами источников (правило годности записи); выплаченная — документом эмитента."""
    reg = {d["sha256"][:16]: d for d in load("anchor")["documents"]}
    for where, r in records():
        assert r["sources"], where
        for s in r["sources"]:
            assert SOURCE_RE.match(s), f"{where}: источник без вида: {s[:60]}"
            shas = SHA_RE.findall(s)
            assert shas and all(x in reg for x in shas), f"{where}: sha256 источника нет в реестре"
        assert "manual" in kinds(r["sources"]) and kinds(r["sources"]) <= set(KINDS), where
        news = [s for s in r["sources"] if s.startswith("news:")]
        assert all(re.search(r"\d\d\.\d\d\.\d{4}", s) and "http" in s for s in news), f"{where}: новость — с датой и адресом"
        manual = [s for s in r["sources"] if s.startswith("manual:")]
        assert all("документ эмитента" in s for s in manual), where
        if r.get("status") == "declared":
            assert kinds(r["sources"]) == set(KINDS), f"{where}: объявленная запись — два вида источников"


def test_dividend_numbers_come_from_the_decision_of_the_meeting():
    """DPS и сумма решения — из документа собрания, принявшего решение (отчёт об итогах голосования того дня)."""
    reg = {d["sha256"][:16]: d for d in load("anchor")["documents"]}
    for r in load("dividends")["history"]:
        for k in ("dps", "pool_declared"):
            keys = [reg[s]["key"] for s in SHA_RE.findall(r[k]["src"])]
            assert any(key.startswith("GM_") and r["decided_date"] in key for key in keys), f"{r['year']}.{k}: {keys}"


# ------------------------------------------------------------------ стартовый реестр и закрытый период

def closed_through() -> str:
    """Последний закрытый период прибыли: самая поздняя строка истории с решением не позже даты фактов."""
    a = load("anchor")["as_of"]
    return max(r["period"] for r in load("dividends")["history"] if r["decided_date"] <= a)


def test_register_seed_records():
    """Стартовый реестр — решения с экс-датой позже якоря; поля записи — те же, что у строки истории; статус —
    «выплачен», если срок выплаты наступил к дню снимка. Годовой календарь: запись — без квартала (год прибыли), и
    решение, объявленное до якоря и выплаченное после, — дивиденд к выплате на якоре (тот же год)."""
    d, a = load("dividends"), load("anchor")
    hist = {r["year"]: r for r in d["history"]}
    want = [r["year"] for r in d["history"] if r["ex_date"] > a["as_of"]]
    assert [r["year"] for r in d["register_seed"]] == want, "стартовый реестр — решения с экс-датой позже якоря"
    for r in d["register_seed"]:
        h = hist[r["year"]]
        assert "period" not in r, f"{r['year']}: при годовом календаре запись закрывает год без квартала"
        for k in ("label", "dps", "decided_date", "recommended_date", "record_date", "last_buy_date", "ex_date", "pay_date", "sources"):
            assert r[k] == h[k], f"{r['year']}.{k}: запись реестра расходится со строкой истории"
        assert r["status"] == ("paid" if r["pay_date"] <= d["snapshot"] else "declared"), r["year"]
        if r["decided_date"] <= a["as_of"]:
            assert r["year"] == load("balance")["dividends_payable_year"], f"{r['year']}: объявлено до якоря — к выплате на якоре"
    if a["period"] == FIRST_ANCHOR:
        got = [(r["year"], r["dps"]["v"], r["status"], r["record_date"]) for r in d["register_seed"]]
        assert got == [(2025, 9.71, "paid", "2026-07-20")]
        assert closed_through() == "2025Q4", "собрание 30.06.2026 — в день якоря"


def test_closed_years_carry_a_history_row():
    """Годовая сумма DPS — строка истории закрытого года: у каждого года от первой строки до последнего закрытого есть
    строка; годы без выплаты (до первой строки) — в `history_before` с нулём."""
    d = load("dividends")
    years = [r["year"] for r in d["history"]]
    last = int(closed_through()[:4])
    assert years == list(range(years[0], last + 1)), "нет строки истории за закрытый год"
    before = [r["year"] for r in d["history_before"]]
    assert before[-1] == years[0] - 1


def test_policy_floor_and_the_payout_of_complete_years():
    """Политика 2016 года: не менее 25 % всей чистой прибыли группы по МСФО за год (базы — вся прибыль, не прибыль
    акционеров); потолка, порога достаточности и срока нет — null с причиной; доля выплаты года — все дивиденды года
    к всей прибыли; у полных лет истории минимум политики выполнен."""
    d = load("dividends")
    pol = d["policy"]
    assert pol["payout_min"]["v"] == 0.25 and "sha256" in pol["payout_min"]["src"] and pol["base"] == "ifrs_ni_group"
    assert pol["cap"]["v"] is None and "потолка" in pol["cap"]["calc"]
    assert pol["threshold"]["v"] is None and "порог" in pol["threshold"]["calc"]
    assert pol["valid_until"]["v"] is None and "не ограничен" in pol["valid_until"]["calc"]
    assert pol["frequency"] == "annual" and pol["approved"] == "2016-01-29"
    complete = {y: rec for y, rec in d["years"].items() if rec["complete"]}
    assert complete, "нет ни одного завершённого года"
    for r in d["history"]:
        rec = d["years"].get(str(r["year"]))
        if rec is None or not rec["complete"]:
            continue
        assert r["ni_group"]["v"] == rec["ni_group"]["v"] and r["ni_shareholders"]["v"] == rec["ni_shareholders"]["v"]
        payout = r["pool_all_classes"]["v"] / rec["ni_group"]["v"]
        assert abs(payout - r["payout_of_ni_group"]["v"]) < 0.001, r["year"]
        assert payout >= pol["payout_min"]["v"] - 1e-9, f"{r['year']}: выплата {payout:.4f} ниже минимума политики"
    if load("anchor")["period"] == FIRST_ANCHOR:
        assert {r["year"]: r["payout_of_ni_group"]["v"] for r in d["history"]} == {2024: 0.5, 2025: 0.25}
        assert d["years"]["2026"]["complete"] is False and d["years"]["2026"]["through"] == FIRST_ANCHOR


# ------------------------------------------------------------------ брокерский календарь — только сверка

def test_no_broker_api_fields_or_sample_paths_in_facts_and_their_documents():
    bad = []
    for path in sorted(FACTS.glob("*.json")) + [p for p in PUBLIC_TEXTS if p.exists()]:
        text = path.read_text(encoding="utf-8")
        bad += [f"{path.name}: {w}" for w in API_WORDS if w in text]
    assert not bad, "имена полей и методов брокерского API в фактах: " + ", ".join(bad)
    d = load("dividends")
    assert "брокерск" in d["broker_check"] and "календар" in d["broker_check"], "о брокерском календаре — словами"
    assert "10 рабочих дней" in d["dates_rule"] and "T+1" in d["dates_rule"]
    for s in load("calendar")["sources"]:
        assert "T-Invest" not in s["title"] and "брокер" not in s["title"].lower(), f"календарь: источник {s['key']} — брокерский календарь"


def test_core_accepts_the_seed_records():
    """Правила годности записи реестра ядра (дата реестра после решения, экс-дата, последний день покупки, два
    источника у объявленного дивиденда) принимают записи стартового реестра как есть."""
    live = pytest.importorskip("model.live")
    check = getattr(live, "check_register", None)
    if check is None:
        pytest.skip("в ядре нет check_register")
    rows = []
    for rec in load("dividends")["register_seed"]:
        rows.append({k: (x.get("v") if isinstance(x, dict) and "v" in x else x) for k, x in rec.items()})
    params = inspect.signature(check).parameters
    ok, bad = check(rows, **({"price": 60.0} if "price" in params else {}))
    assert not bad, f"ядро отвергло записи стартового реестра: {[(b.get('year'), b.get('reason')) for b in bad]}"
    assert len(ok) == len(rows)
