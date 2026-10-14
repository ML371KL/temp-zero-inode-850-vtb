"""Месячные результаты в базисе цели: календарь с месяцами без релиза, дозор без формы 0409102, оценка квартала
по месяцам, веса из ретро, печатный горизонт по событию, месячная таблица и флаг числа акций выходов.

Настройки и история рядов — этой копии (`data/indicators/`); книга и факты — заглушка её эмитента
(`tests/fixtures/ind/issuer/`). Ряды для счёта тесты кладут сами (сочинённые числа) либо берут историю
репозитория — там, где проверяется она сама.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from indicators import calendar as cal
from indicators import (collect, config, iss, issuer_docs, journal, nowcast, nowcast_months, outputs, periods, record,
                        register, release_watch, retro, seed, tinvest)
from indicators.sources import OK, Context
from indicators.store import Point, Store
from tests.support_ind import FIX, FakeGetter, use_issuer

pytestmark = pytest.mark.tact  # быстрые тесты такта

PREFIX = "ifrs.release."
AT = "T07:00:00+00:00"


def _store(monkeypatch, tmp_path) -> Store:
    use_issuer(monkeypatch, tmp_path)
    return Store(tmp_path / "state")


def _ctx(store, today, getter=None) -> Context:
    return Context(store=store, today=today, company=config.company(), cfg=config.sources(), getter=getter or FakeGetter(),
                   peer_tickers=tuple(config.peer_tickers()))


def _put(store: Store, metric: str, rows: dict[str, tuple[float, str]], *, prefix: str = PREFIX) -> None:
    """Точки ряда: {период: (значение, день известности)}."""
    store.upsert(f"{prefix}{metric}", [Point(p, v, day + AT, "ok", "тест") for p, (v, day) in rows.items()],
                 unit="RUB bn", basis="ifrs")


def _history(store: Store) -> None:
    """Сочинённая история: кварталы с фактом, два напечатанных месяца в каждом, в первом квартале — сумма двух."""
    actual = {"2025Q1": (120.0, "2025-04-25"), "2025Q2": (150.0, "2025-07-30"), "2025Q3": (90.0, "2025-10-28"),
              "2025Q4": (160.0, "2026-02-25"), "2026Q1": (130.0, "2026-04-28"), "2026Q2": (100.0, "2026-07-28")}
    store.upsert("actual.ni_q", [Point(q, v, day + AT, "ok", "тест") for q, (v, day) in actual.items()], unit="RUB bn")
    for key, level in (("nim", 0.02), ("cor", 0.01)):
        store.upsert(f"actual.{key}_q", [Point(q, level + i / 1000.0, day + AT, "ok", "тест")
                                         for i, (q, (_, day)) in enumerate(actual.items())], unit="share")
    _put(store, "np_ytd", {"2025M02": (70.0, "2025-03-27"), "2026M02": (80.0, "2026-03-26"),
                           "2026M03": (130.0, "2026-04-28"), "2026M06": (230.0, "2026-07-28")})
    _put(store, "np_m", {"2025M04": (60.0, "2025-05-30"), "2025M05": (40.0, "2025-06-27"),
                         "2025M07": (20.0, "2025-08-29"), "2025M08": (30.0, "2025-09-26"),
                         "2025M10": (50.0, "2025-11-28"), "2025M11": (45.0, "2025-12-26"),
                         "2026M04": (30.0, "2026-05-28"), "2026M05": (35.0, "2026-06-26"), "2026M06": (35.0, "2026-07-28"),
                         "2026M07": (40.0, "2026-08-28"), "2026M08": (50.0, "2026-09-29")})
    for key, level in (("nim", 0.02), ("cor", 0.01)):
        _put(store, f"{key}_m", {"2026M04": (level, "2026-05-28"), "2026M05": (level + 0.002, "2026-06-26"),
                                 "2026M07": (level + 0.004, "2026-08-28"), "2026M08": (level + 0.006, "2026-09-29")})
        _put(store, f"{key}_ytd", {"2026M02": (level - 0.001, "2026-03-26")})


# ------------------------------------------------------------------ настройки копии

def test_settings_of_the_monthly_results():
    cfg = config.sources()
    spec = release_watch.monthly(cfg)
    assert (spec.prefix, spec.main, spec.doc_kind, spec.basis) == (PREFIX, "np_ytd", "ifrs_monthly", "ifrs")
    assert spec.wakes and spec.backfill and not spec.form102 and spec.table_form() == release_watch.TABLE_FLOWS
    assert spec.unit("np_m") == "RUB bn" and spec.unit("nim_m") == "share" == spec.unit("n20_0") == spec.unit("npl90")
    assert {"np", "nii", "fee", "prov", "opex", "pretax", "other", "opinc", "tax"} == set(release_watch._flows(spec))
    assert all(release_watch.metric_words(m) != m for m in spec.metrics), "метрика без слов: печаталась бы ключом"
    assert nowcast_months.enabled(cfg) and nowcast_months.pure_scoring(cfg)
    assert nowcast_months.print_rule(cfg) == (27, 2)
    assert nowcast_months.series_map(cfg)["ni_q"] == {"month": "np_m", "ytd": "np_ytd"}
    assert nowcast_months.guidance_rule("ni_q", cfg)["item"] == "net_profit"
    # без ключей — прежнее поведение: «РСБУ × мост», 30 дней, запись T-90 — нау-каст, таблица по началу имён рядов
    assert not nowcast_months.enabled({}) and not nowcast_months.pure_scoring({})
    assert nowcast_months.print_rule({}) == (30, None) and nowcast_months.guidance_rule("ni_q", {}) is None
    legacy = release_watch.monthly({})
    assert legacy.form102 and not legacy.backfill and legacy.basis == "ras" and legacy.table_form() == "flows"
    assert release_watch.monthly({"monthly": {"series_prefix": "x.release."}}).table_form() == release_watch.TABLE_STOCKS
    words = nowcast.equation_words()
    assert "МСФО" in words["equations"]["ni_q"] and "РСБУ" not in " ".join(
        [*words["equations"].values(), *words["no_estimate"].values(), words["no_sigma"]])


# ------------------------------------------------------------------ календарь

def test_months_without_a_release_are_not_waited_for(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    sched, events = config.sources()["schedule"], config.calendar_events()
    spec = cal.monthly_spec(sched)
    assert spec["kind"] == "ifrs_monthly" and spec["skip_months"] == (1, 3, 6, 9, 12) and spec["wakes_release"]
    assert [m for m in range(1, 13) if cal.has_release(periods.month(2026, m), spec)] == [2, 4, 5, 7, 8, 10, 11]
    assert cal.monthly_window("2026M10", sched) == (date(2026, 11, 22), date(2026, 11, 30))
    assert cal.monthly_window("2026M11", sched) == (date(2026, 12, 22), date(2026, 12, 31))
    assert cal.ifrs_window("2026Q3", sched) == (date(2026, 10, 24), date(2026, 10, 31))
    assert cal.ifrs_window("2026Q4", sched) == (date(2027, 2, 20), date(2027, 2, 26))
    _put(store, "np_ytd", {"2026M07": (265.0, "2026-08-28"), "2026M08": (315.0, "2026-09-29")})
    # в октябре ждать нечего: сентябрь — без релиза, август принят; ближайший месяц — октябрь, его окно — конец ноября
    nxt = cal.next_ras(date(2026, 10, 13), store=store, schedule=sched, facts_events=events)
    assert nxt == {"month": "2026M10", "release_date": "2026-11-22", "release_confirmed": False, "form102_date_est": None,
                   "form102_latest_est": None, "enters_via": "release", "date": "2026-11-22"}
    assert cal.next_ras(date(2026, 9, 5), store=store, schedule=sched, facts_events=events)["month"] == "2026M10"
    day = lambda d: cal.is_release_day(d, store=store, schedule=sched, facts_events=events)  # noqa: E731
    assert not day(date(2026, 10, 13)) and not day(date(2026, 10, 26))            # окно сентября не открывается
    assert day(date(2026, 10, 30)) and not day(date(2026, 10, 29))                # день отчёта МСФО — из фактов
    assert not day(date(2026, 11, 20)) and day(date(2026, 11, 23)) and day(date(2026, 11, 30))
    assert day(date(2026, 12, 7)) and not day(date(2026, 12, 8))                  # окно октября плюс семь дней опоздания
    _put(store, "np_ytd", {"2026M10": (400.0, "2026-11-27")})
    assert not day(date(2026, 11, 30))                                            # месяц принят — окно закрыто
    assert cal.next_ras(date(2026, 12, 1), store=store, schedule=sched, facts_events=events)["month"] == "2026M11"
    # события: месячные — только у месяцев с релизом; окна формы банка нет
    got = cal.events(date(2026, 10, 13), store=store, schedule=sched, facts_events=events)
    monthly = [e["covers"] for e in got if e["kind"] == "ifrs_monthly"]
    assert monthly[:3] == ["2026M10", "2026M11", "2027M02"] and not [e for e in got if e["kind"] == "form102"]
    assert next(e for e in got if e["kind"] == "ifrs_monthly")["title"] == "Месячные результаты по МСФО: октябрь 2026 года"
    assert next(e for e in got if e["kind"] == "ifrs")["date"] == "2026-10-30"


def test_the_bank_form_does_not_stand_for_the_month_of_the_group(monkeypatch, tmp_path):
    """Форма 0409102 банка (РСБУ) месяц группы по МСФО не заменяет: ни «месяц известен», ни подтверждение,
    ни сверка, ни плашка расхождения."""
    store = _store(monkeypatch, tmp_path)
    store.upsert("cbr.f102.ni_ytd", [Point("2026M09", 350.0, "2026-10-25" + AT, "ok", "тест"),
                                     Point("2026M10", 400.0, "2026-11-25" + AT, "ok", "тест")], unit="RUB bn")
    assert not cal.form102_counts() and cal.ras_known(store, "2026M10") is None
    _put(store, "np_ytd", {"2026M10": (300.0, "2026-11-27")})
    assert cal.ras_known(store, "2026M10") == "release"
    spec = release_watch.monthly(config.sources())
    assert release_watch.gather(_ctx(store, date(2026, 11, 28)), "2026M10", spec) == {}      # формы в кандидатах нет
    flag = release_watch.mismatch_flag(store, ["2026M10"], prefix=PREFIX, check_form=spec.form102)
    assert flag == {"raised": False, "detail": ""}
    assert release_watch.form102_rows(store, ["2026M10"], prefix=PREFIX, check_form=spec.form102) == []
    # прежнее поведение — по умолчанию: форма сверяется
    assert release_watch.mismatch_flag(store, ["2026M10"], prefix=PREFIX)["raised"]
    assert release_watch.form102_rows(store, ["2026M10"], prefix=PREFIX)[0]["ni"] == 50.0


# ------------------------------------------------------------------ дозор: месяцы без своего релиза

def test_a_month_without_a_release_is_filled_from_the_next_book(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    _put(store, "np_ytd", {"2026M02": (80.0, "2026-03-26")})
    _put(store, "loans_gross", {"2025M12": (24000.0, "2026-03-26")})
    numbers = {"np_ytd": 160.0, "np_m": 30.0, "nii_ytd": 260.0, "nii_m": 70.0, "loans_gross": 25200.0, "nim_m": 0.026}
    store.write_state(issuer_docs.CANDIDATES_FILE, {"ifrs_monthly:2026M04:abc": {
        "status": "ok", "method": "text", "kind": "ifrs_monthly", "month": "2026M04", "period": "2026M04",
        "url": "https://www.vtb.ru/media-files/a.xlsx", "sha256": "abc", "numbers": numbers,
        "comparative": {"2026M03": {"loans_gross": 25100.0, "n20_0": 10.7}, "2025M12": {"loans_gross": 99.0},
                        "2025M04": {"np_m": 24.0}, "2026M05": {"np_m": 1.0}}}})
    ctx = _ctx(store, date(2026, 5, 28))
    out = release_watch.watch(ctx, "2026M04")
    assert out["month_accepted"] and set(out["new"]) == set(numbers)
    filled = {tuple(x) for x in out["filled"]}
    assert {("2026M03", "np_ytd"), ("2026M03", "np_m"), ("2026M03", "nii_ytd"), ("2026M03", "loans_gross"),
            ("2026M03", "n20_0"), ("2025M04", "np_m")} == filled
    get = lambda metric, month: store.load(PREFIX + metric).value_as_of(month)  # noqa: E731
    assert get("np_ytd", "2026M03") == pytest.approx(130.0)             # итог − месяц
    assert get("np_m", "2026M03") == pytest.approx(50.0)                # разность соседних итогов: 130 − 80
    assert get("nii_ytd", "2026M03") == pytest.approx(190.0) and store.load(PREFIX + "nii_m").value_as_of("2026M03") is None
    assert get("loans_gross", "2026M03") == 25100.0 and get("n20_0", "2026M03") == pytest.approx(0.107)   # проценты → доля
    assert get("loans_gross", "2025M12") == 24000.0                     # принятое раньше не переписывается
    assert store.load(PREFIX + "np_m").point_as_of("2026M03").note == release_watch.DERIVED_NOTE
    assert store.load(PREFIX + "loans_gross").point_as_of("2026M03").source == "release:comparative"
    assert store.load(PREFIX + "np_m").value_as_of("2026M05") is None   # будущий месяц из столбцов сравнения не берётся
    again = release_watch.watch(ctx, "2026M04")
    assert again["new"] == [] and again["filled"] == [] and not again["month_accepted"]
    # без настройки заполнения — прежнее поведение: пишется только месяц релиза
    other = Store(tmp_path / "plain")
    other.write_state(issuer_docs.CANDIDATES_FILE, store.read_state(issuer_docs.CANDIDATES_FILE))
    cfg = {**config.sources(), "monthly": {**config.sources()["monthly"], "backfill": False}}
    plain = release_watch.watch(Context(store=other, today=date(2026, 5, 28), company=config.company(), cfg=cfg), "2026M04")
    assert plain["filled"] == [] and other.load(PREFIX + "np_ytd").value_as_of("2026M03") is None


def test_shares_of_a_workbook_are_fractions_as_they_stand(monkeypatch, tmp_path):
    """Книга эмитента несёт доли долями: отношение расходов к доходам 105 % в ней — 1,05, и правило таблицы PDF
    «число больше единицы — проценты» к книге не применяется — ни к числам месяца, ни к столбцам сравнения. У
    кандидата без пометки (таблица PDF) правило прежнее."""
    from tests.support_ind_book import monthly_book, synthetic_numbers

    store = _store(monkeypatch, tmp_path)
    numbers = {**synthetic_numbers("2026M08"), "cir_m": 1.05}
    got = issuer_docs.analyse(monthly_book("2026M08", numbers=numbers), "ifrs_monthly", config.sources()["issuer_docs"],
                              monthly_kind="ifrs_monthly")
    assert got["status"] == "ok" and got["share_unit"] == issuer_docs.SHARE_FRACTIONS
    assert got["numbers"]["cir_m"] == pytest.approx(1.05) and 0 < got["numbers"]["nim_m"] < 0.1
    comparative = {**got["comparative"], "2026M06": {**got["comparative"].get("2026M06", {}), "cir_ytd": 1.2}}
    store.write_state(issuer_docs.CANDIDATES_FILE, {"ifrs_monthly:2026M08:abc": {
        **got, "comparative": comparative, "kind": "ifrs_monthly", "month": "2026M08", "period": "2026M08",
        "url": "https://www.vtb.ru/media-files/a.xlsx", "sha256": "abc"}})
    ctx = _ctx(store, date(2026, 9, 29))
    assert release_watch.gather(ctx, "2026M08")["cir_m"][0]["value"] == pytest.approx(1.05)
    out = release_watch.watch(ctx, "2026M08")
    assert "cir_m" in out["new"] and ["2026M06", "cir_ytd"] in out["filled"]
    get = lambda metric, month: store.load(PREFIX + metric).value_as_of(month)  # noqa: E731
    assert get("cir_m", "2026M08") == pytest.approx(1.05) and get("cir_ytd", "2026M06") == pytest.approx(1.2)
    assert get("nim_m", "2026M08") == pytest.approx(numbers["nim_m"])
    # таблица PDF (кандидат без пометки долей): проценты переводятся в доли, как раньше
    other = Store(tmp_path / "pdf")
    other.write_state(issuer_docs.CANDIDATES_FILE, {"ifrs_monthly:2026M08:def": {
        "status": "ok", "method": "text", "kind": "ifrs_monthly", "month": "2026M08", "period": "2026M08",
        "url": "https://www.vtb.ru/media-files/a.pdf", "sha256": "def", "numbers": {"cir_m": 105.0, "nim_m": 2.6},
        "comparative": {"2026M06": {"n20_0": 10.7}}}})
    release_watch.watch(_ctx(other, date(2026, 9, 29)), "2026M08")
    assert other.load(PREFIX + "cir_m").value_as_of("2026M08") == pytest.approx(1.05)
    assert other.load(PREFIX + "nim_m").value_as_of("2026M08") == pytest.approx(0.026)
    assert other.load(PREFIX + "n20_0").value_as_of("2026M06") == pytest.approx(0.107)


def test_a_manual_year_to_date_of_a_quarter_end_gives_its_month(monkeypatch, tmp_path):
    """Нарастающий итог конца квартала из отчёта МСФО вносится руками в день отчёта: месяц — разность итогов."""
    store = _store(monkeypatch, tmp_path)
    _put(store, "np_ytd", {"2026M08": (315.0, "2026-09-29")})
    values = record.parse_pairs(["np_ytd=420,5", "nim_ytd=2,7%"], metrics=release_watch.monthly(config.sources()).metrics)
    assert values == {"np_ytd": 420.5, "nim_ytd": pytest.approx(0.027)}
    record.record_ras(store, "2026M09", values, "отчётность МСФО за 9 месяцев")
    out = release_watch.watch(_ctx(store, date(2026, 10, 30)), "2026M09")
    assert set(out["new"]) == {"np_ytd", "np_m", "nim_ytd"}
    assert store.load(PREFIX + "np_m").value_as_of("2026M09") == pytest.approx(105.5)
    assert store.load(PREFIX + "np_m").point_as_of("2026M09").status == "manual"


def _book(store: Store, month: str, numbers: dict[str, float]) -> None:
    """Книга эмитента за месяц среди кандидатов дозора (текстовый слой: принимается сама)."""
    cands = store.read_state(issuer_docs.CANDIDATES_FILE) or {}
    cands[f"ifrs_monthly:{month}:h{month}"] = {
        "status": "ok", "method": "text", "kind": "ifrs_monthly", "month": month, "period": month,
        "url": f"https://www.vtb.ru/media-files/{month}.xlsx", "sha256": f"h{month}", "numbers": numbers, "comparative": {}}
    store.write_state(issuer_docs.CANDIDATES_FILE, cands)


def test_a_manual_total_of_a_quarter_end_revised_by_the_next_book_is_a_message_not_a_refusal(monkeypatch, tmp_path):
    """Итог конца квартала внесён руками из отчёта, а первая книга следующего квартала печатает «итог − месяц»
    иначе (другой винтаж или округление) больше допуска тождества. Книга — документ эмитента — принимается, о
    расхождении говорит сообщение; внесённое руками остаётся; следующая книга поток апреля не выводит."""
    store = _store(monkeypatch, tmp_path)
    get = lambda metric, month: store.load(PREFIX + metric).value_as_of(month)  # noqa: E731
    _put(store, "np_ytd", {"2026M02": (80.0, "2026-03-26")})
    record.record_ras(store, "2026M03", {"np_ytd": 130.5}, "отчётность МСФО за 3 месяца")
    assert set(release_watch.watch(_ctx(store, date(2026, 4, 29)), "2026M03")["new"]) == {"np_ytd", "np_m"}
    _book(store, "2026M04", {"np_ytd": 160.0, "np_m": 30.0, "nii_ytd": 260.0, "nii_m": 70.0})     # по книге март — 130,0
    out = release_watch.watch(_ctx(store, date(2026, 5, 28)), "2026M04")
    assert out["month_accepted"] and out["complete"] and not out["identity_failures"] and not out["mismatches"]
    assert out["revisions"] == ["чистая прибыль: с начала года по 2026M03 внесено руками 130.5, "
                                "по книге 2026M04 — 130.0 (160.0 − 30.0)"]
    assert get("np_ytd", "2026M04") == 160.0 and get("np_m", "2026M04") == 30.0
    assert store.load(PREFIX + "np_ytd").point_as_of("2026M04").source == "release:pdf"
    held = store.load(PREFIX + "np_ytd").point_as_of("2026M03")
    assert (held.value, held.status) == (130.5, "manual")               # внесённое руками меняет только рука
    state = store.read_state("release_watch/2026M04.json")
    assert state["revisions"] == out["revisions"] and state["identity_flows"] == [] and not state["identity_failures"]
    res = release_watch.run(_ctx(store, date(2026, 5, 29)))
    assert [r for r in res.reasons if "пересмотрен" in r] == [
        "месячный релиз 2026M04: книга принята, итог прошлого месяца пересмотрен — " + out["revisions"][0]]
    assert not [r for r in res.reasons if "не равен" in r] and not res.retry
    # следующая книга: у апреля своя книга — разностью итогов его поток не выводится, напечатанное остаётся
    _book(store, "2026M05", {"np_ytd": 200.0, "np_m": 40.0})
    nxt = release_watch.watch(_ctx(store, date(2026, 6, 26)), "2026M05")
    assert nxt["month_accepted"] and nxt["filled"] == [] and not nxt["identity_failures"]
    assert get("np_m", "2026M04") == 30.0 and store.load(PREFIX + "np_m").point_as_of("2026M04").note == ""
    again = release_watch.watch(_ctx(store, date(2026, 6, 27)), "2026M04")
    assert not again["mismatches"] and not again["identity_failures"] and again["new"] == []
    # рука исправила итог марта — сообщение о пересмотре уходит
    record.record_ras(store, "2026M03", {"np_ytd": 130.0}, "отчётность МСФО за 3 месяца, уточнение")
    release_watch.watch(_ctx(store, date(2026, 6, 28)), "2026M03")
    assert release_watch.watch(_ctx(store, date(2026, 6, 28)), "2026M04")["revisions"] == []


def test_the_junction_rule_is_narrow(monkeypatch, tmp_path):
    """Пересмотром расхождение считается только на стыке «итог руками за месяц без релиза → документ эмитента».
    Итог прошлого месяца не от руки, прошлый месяц со своим релизом, числа месяца не из документа — отказ, как был."""
    # 1) итог марта пришёл не от руки (два согласных источника новостей): книга апреля прибыль не отдаёт
    store = _store(monkeypatch, tmp_path)
    _put(store, "np_ytd", {"2026M03": (130.5, "2026-04-29")})
    _book(store, "2026M04", {"np_ytd": 160.0, "np_m": 30.0})
    out = release_watch.watch(_ctx(store, date(2026, 5, 28)), "2026M04")
    assert out["identity_failures"] == ["чистая прибыль: с начала года 160.0 ≠ 130.5 + 30.0"] and out["revisions"] == []
    assert out["new"] == [] and not out["complete"]
    assert store.read_state("release_watch/2026M04.json")["identity_flows"] == ["np"]
    # 2) у прошлого месяца свой релиз (апрель → май): итог апреля руками, книга мая расходится — отказ
    other = Store(tmp_path / "second")
    record.record_ras(other, "2026M04", {"np_ytd": 160.5}, "поправка оператора")
    release_watch.watch(_ctx(other, date(2026, 5, 28)), "2026M04")
    _book(other, "2026M05", {"np_ytd": 200.0, "np_m": 40.0})
    out = release_watch.watch(_ctx(other, date(2026, 6, 26)), "2026M05")
    assert out["revisions"] == [] and len(out["identity_failures"]) == 1 and out["new"] == []
    # 3) настройки без месяцев без релиза (каждый месяц — свой релиз): стыка нет
    third = Store(tmp_path / "third")
    cfg = config.sources()
    cfg = {**cfg, "schedule": {**cfg["schedule"], "monthly": {**cfg["schedule"]["monthly"], "skip_months": []}}}
    record.record_ras(third, "2026M03", {"np_ytd": 130.5}, "отчётность")
    plain = lambda day: Context(store=third, today=day, company=config.company(), cfg=cfg, getter=FakeGetter())  # noqa: E731
    release_watch.watch(plain(date(2026, 4, 29)), "2026M03")
    _book(third, "2026M04", {"np_ytd": 160.0, "np_m": 30.0})
    out = release_watch.watch(plain(date(2026, 5, 28)), "2026M04")
    assert out["revisions"] == [] and len(out["identity_failures"]) == 1


def test_the_next_book_does_not_derive_a_month_that_has_its_own_release_or_a_failed_identity(monkeypatch, tmp_path):
    """Разностью итогов следующая книга выводит поток только месяцу без своего релиза. Месяц с релизом, чей поток в
    ряд не попал (тождество не сошлось, книга не прочитана), ждёт свою книгу или руку; месяц без релиза, за который
    тождество не сошлось, тоже не выводится."""
    store = _store(monkeypatch, tmp_path)
    get = lambda metric, month: store.load(PREFIX + metric).value_as_of(month)  # noqa: E731
    _put(store, "np_ytd", {"2026M03": (130.5, "2026-04-29")})               # итог марта не от руки
    _book(store, "2026M04", {"np_ytd": 160.0, "np_m": 30.0, "nii_ytd": 260.0, "nii_m": 70.0})
    assert release_watch.watch(_ctx(store, date(2026, 5, 28)), "2026M04")["identity_failures"]     # прибыль апреля не принята
    _book(store, "2026M05", {"np_ytd": 200.0, "np_m": 40.0, "nii_ytd": 330.0, "nii_m": 70.0})
    out = release_watch.watch(_ctx(store, date(2026, 6, 26)), "2026M05")
    assert set(out["new"]) == {"np_ytd", "np_m", "nii_ytd", "nii_m"} and out["filled"] == []
    assert get("np_ytd", "2026M04") is None and get("np_m", "2026M04") is None      # не 160,0 и не 29,5 «разностью»
    assert get("nii_ytd", "2026M04") == 260.0                                       # принятое из своей книги — на месте
    # июнь — без релиза: его поток выводит книга июля …
    _book(store, "2026M07", {"np_ytd": 290.0, "np_m": 50.0, "nii_ytd": 470.0, "nii_m": 60.0})
    out = release_watch.watch(_ctx(store, date(2026, 8, 28)), "2026M07")
    assert {tuple(x) for x in out["filled"]} == {("2026M06", "np_ytd"), ("2026M06", "np_m"), ("2026M06", "nii_ytd"),
                                                 ("2026M06", "nii_m")}
    assert get("np_ytd", "2026M06") == pytest.approx(240.0) and get("np_m", "2026M06") == pytest.approx(40.0)
    # … но не тогда, когда за июнь тождество не сошлось (документ за июнь пришёл и не прошёл его)
    other = Store(tmp_path / "second")
    _put(other, "np_ytd", {"2026M05": (200.0, "2026-06-26")})
    _put(other, "nii_ytd", {"2026M05": (330.0, "2026-06-26")})
    _book(other, "2026M06", {"np_ytd": 236.0, "np_m": 30.0})
    june = release_watch.watch(_ctx(other, date(2026, 7, 29)), "2026M06")
    assert june["identity_failures"] and other.read_state("release_watch/2026M06.json")["identity_flows"] == ["np"]
    _book(other, "2026M07", {"np_ytd": 290.0, "np_m": 50.0, "nii_ytd": 470.0, "nii_m": 60.0})
    out = release_watch.watch(_ctx(other, date(2026, 8, 28)), "2026M07")
    assert {tuple(x) for x in out["filled"]} == {("2026M06", "nii_ytd"), ("2026M06", "nii_m")}
    assert other.load(PREFIX + "np_ytd").value_as_of("2026M06") is None
    assert other.load(PREFIX + "np_m").value_as_of("2026M06") is None


def test_the_third_month_of_a_level_keeps_the_weight_of_two(monkeypatch, tmp_path):
    """σ оценки уровня при трёх известных месяцах в истории не измерена (третий месяц квартала книга не печатает):
    ручной ввод ЧПМ или стоимости риска за него берёт σ двух месяцев — вес оценки не обнуляется."""
    assert nowcast_months.measured_sigma({"0": None, "1": 0.004, "2": 0.002, "3": None}, 3) == 0.002
    assert nowcast_months.measured_sigma({"0": None, "1": 0.004, "2": 0.002, "3": 0.001}, 3) == 0.001
    assert nowcast_months.measured_sigma({"1": 0.004, "2": None, "3": None}, 3) == 0.004
    assert nowcast_months.measured_sigma({"0": None, "1": None}, 1) is None and nowcast_months.measured_sigma(None, 2) is None
    assert nowcast_months.measured_sigma({"0": 0.9, "1": 0.004}, 0) is None             # без месяцев оценки нет
    store = _store(monkeypatch, tmp_path)
    _history(store)
    today = date(2026, 9, 30)
    sigmas = {"nim": {"ras": {"0": None, "1": 0.004, "2": 0.002, "3": None}, "base": 0.006},
              "cor": {"ras": {"0": None, "1": 0.004, "2": 0.002, "3": None}, "base": 0.006},
              "ras": {"0": None, "1": 0.3, "2": 0.2, "3": 0.01}, "base": 0.3}
    two = nowcast_months.inputs(store, period="2026Q3", today=today, sigmas=sigmas)["targets"]
    assert two["nim_q"]["months_known"] == 2 and two["nim_q"]["sigma_ras"] == 0.002 and two["nim_q"]["w"] > 0.8
    _put(store, "nim_m", {"2026M09": (0.028, "2026-09-30")})
    _put(store, "cor_m", {"2026M09": (0.018, "2026-09-30")})
    three = nowcast_months.inputs(store, period="2026Q3", today=date(2026, 10, 1), sigmas=sigmas)["targets"]
    for key in ("nim_q", "cor_q"):
        assert three[key]["months_known"] == 3 and three[key]["sigma_ras"] == 0.002, key
        assert three[key]["w"] == pytest.approx(two[key]["w"]) and three[key]["std_error"] is not None, key
        assert len(three[key]["level_months"]) == 3
    assert three["nim_q"]["ras_estimate"] == pytest.approx((0.024 + 0.026 + 0.028) / 3)


# ------------------------------------------------------------------ оценка квартала по месяцам

def test_first_months_of_a_quarter_come_as_months_or_as_a_pooled_sum(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    _history(store)
    feeds = nowcast_months.feeds(store)
    flow, level = feeds["ni_q"], feeds["nim_q"]
    two = flow.first("2026Q3", "2026-10-13")
    assert (two["k"], two["value"], two["pooled"], two["known_at"][:10]) == (2, 90.0, False, "2026-09-29")
    assert flow.first("2026Q3", "2026-09-01")["k"] == 1 and flow.first("2026Q3", "2026-08-01") is None
    assert flow.exactly("2026Q3", 1, "2026-10-13")["value"] == 40.0 and flow.exactly("2026Q3", 3, "2026-10-13") is None
    # первый квартал: январь и февраль напечатаны одной суммой — нарастающим итогом февраля
    q1 = flow.first("2026Q1", "2026-04-01")
    assert (q1["k"], q1["value"], q1["pooled"]) == (2, 80.0, True)
    assert [r["value"] for r in q1["rows"]] == [None, 80.0] and q1["rows"][-1]["span"] == 2
    assert flow.exactly("2026Q1", 1, None) is None and flow.kth_day("2026Q1", 2) == "2026-03-26"
    assert flow.first("2026Q1", None)["k"] == 3                                   # итог марта: квартал известен целиком
    # второй квартал: месяцы порознь важнее итога; последний месяц — сам месяц, а нет его — разность итогов
    assert flow.first("2026Q2", "2026-06-30")["value"] == 65.0 and flow.last_month("2026Q2", None) == 35.0
    assert flow.last_month("2026Q1", None) == pytest.approx(50.0) and flow.last_month("2025Q3", None) is None
    # уровень: среднее месячных; в первом квартале — значение с начала года
    assert level.first("2026Q3", "2026-10-13")["value"] == pytest.approx(0.025)
    assert level.first("2026Q1", "2026-04-01")["value"] == pytest.approx(0.019) and level.first("2026Q2", "2026-05-30")["k"] == 1
    assert nowcast_months.flow_estimate(two, 120.0) == pytest.approx(130.0)       # м1 + м2 + треть ожидания
    assert nowcast_months.flow_estimate(flow.first("2026Q3", "2026-09-01"), 120.0) == pytest.approx(120.0)
    assert nowcast_months.flow_estimate(two, None) is None and nowcast_months.flow_estimate(None, 120.0) is None
    assert nowcast_months.flow_estimate(flow.first("2026Q1", None), None) == pytest.approx(130.0)


def test_quarter_estimate_by_months_and_the_weight(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    _history(store)
    sig = {"ras": {"0": None, "1": 0.3, "2": 0.2, "3": 0.01}, "base": 0.3,
           "nim": {"ras": {"1": 0.002, "2": 0.001}, "base": 0.004}, "cor": {"ras": {"2": 0.003}, "base": 0.004}}
    ras = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 13), bridge={}, sigmas=sig)
    assert ras["estimate"] == "months" and ras["months_known"] == 2
    assert [(m["month"], m["status"], m["ni"]) for m in ras["months"]] == [
        ("2026M07", "known", 40.0), ("2026M08", "known", 50.0), ("2026M09", "estimated", None)]
    t = ras["targets"]["ni_q"]
    assert (t["known_sum"], t["model_share"], t["bridge"], t["basis"]) == (90.0, pytest.approx(1 / 3), None, "ifrs")
    assert t["w"] == pytest.approx(0.09 / 0.13) and t["rel_std_error"] == pytest.approx((0.09 / 0.13) ** 0.5 * 0.2)
    out = nowcast.combine(ras, {"ni_q": 120.0, "nim_q_mgmt": 0.02, "cor_q_mgmt": 0.012})
    ni = out["ni_q"]
    assert ni["ras_estimate"] == pytest.approx(130.0) == ni["ras_bridged"] and ni["bridge"] is None
    assert ni["forecast"] == pytest.approx(120.0 + t["w"] * 10.0) and ni["deviation"] == pytest.approx(t["w"] * 10.0)
    assert ni["std_error"] == pytest.approx(abs(ni["forecast"]) * t["rel_std_error"]) and "МСФО" in ni["equation"]
    nim, cor = out["nim_q"], out["cor_q"]
    assert nim["ras_estimate"] == pytest.approx(0.025) and nim["w"] == pytest.approx(16 / 17)
    assert nim["forecast"] == pytest.approx(0.02 + 16 / 17 * 0.005) and nim["std_error"] == pytest.approx((16 / 17) ** 0.5 * 0.001)
    assert cor["ras_estimate"] == pytest.approx(0.015) and cor["w"] == pytest.approx(16 / 25) and cor["basis"] == "mgmt"
    # сборка выпуска достраивает оценку своим ожиданием: другое ожидание — другая оценка, вес тот же
    other = nowcast.combine(ras, {"ni_q": 150.0, "nim_q_mgmt": 0.02, "cor_q_mgmt": 0.012})["ni_q"]
    assert other["ras_estimate"] == pytest.approx(140.0) and other["w"] == ni["w"]
    # без ожидания модели оценки потока нет: недостающий месяц взять неоткуда
    assert nowcast.combine(ras, {})["ni_q"]["forecast"] is None
    # один месяц: вес по σ одного месяца; ни одного — прогноз равен ожиданию
    one = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 9, 1), bridge={}, sigmas=sig)
    assert one["months_known"] == 1 and one["targets"]["ni_q"]["w"] == pytest.approx(0.5)
    assert one["targets"]["cor_q"]["w"] == 0.0 and "σ ретро ещё не измерена" in one["targets"]["cor_q"]["equation"]
    none = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 8, 1), bridge={}, sigmas=sig)
    flat = nowcast.combine(none, {"ni_q": 120.0, "nim_q_mgmt": 0.02, "cor_q_mgmt": 0.012})
    assert none["months_known"] == 0 and all(v["forecast"] == v["expectation"] and v["w"] == 0.0 for v in flat.values())
    assert flat["ni_q"]["ras_estimate"] is None and "ещё нет" in flat["ni_q"]["equation"]
    # выпуск без нау-каста этого квартала: слова — оценки по месяцам, не моста РСБУ
    bare = nowcast.combine({"targets": {}}, {"ni_q": 120.0})
    assert bare["ni_q"]["forecast"] == 120.0 and "РСБУ" not in bare["ni_q"]["equation"]
    # замороженные дисперсии квартала важнее пересчитанных
    frozen = {"sigmas": {"ras": {"2": 0.3}, "base": 0.3}, "nim": {"sigmas": {"ras": {"2": 0.004}, "base": 0.004}}}
    held = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 13), bridge={}, sigmas=sig, frozen=frozen)
    assert held["targets"]["ni_q"]["w"] == pytest.approx(0.5) == held["targets"]["nim_q"]["w"]


def test_print_horizon_opens_by_the_second_month_or_by_days():
    report = date(2026, 10, 30)
    h = lambda d, k: nowcast.horizon_for(d, report, months_known=k)  # noqa: E731
    assert h(date(2026, 8, 1), 0) == "T-90" and h(date(2026, 7, 31), 0) is None   # 90 и 91 день
    assert h(date(2026, 9, 5), 1) == "T-90"                                       # один месяц печатный горизонт не открывает
    assert h(date(2026, 9, 29), 2) == "T-30"                                      # вышел второй месяц — за 31 день
    assert h(date(2026, 10, 2), 1) == "T-90" and h(date(2026, 10, 3), 1) == "T-30"   # 28 и 27 дней
    assert h(date(2026, 10, 30), 2) is None and h(date(2026, 10, 29), 0) == "T-30"
    # без настройки — прежние 30 дней и никакого события
    assert nowcast_months.horizon(date(2026, 9, 29), report, months_known=2, cfg={}) == "T-90"
    assert nowcast_months.horizon(date(2026, 9, 30), report, months_known=0, cfg={}) == "T-30"


def test_benchmarks_by_months_and_by_the_guidance_of_the_year(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    _history(store)
    h = nowcast.History.load(store)
    feed = nowcast_months.feeds(store)["ni_q"]
    marks = nowcast_months.month_marks(h, feed, "2026Q3", "2026-10-13")
    assert marks == {"m12_flat": pytest.approx(135.0), "m12_prev3": pytest.approx(125.0)}     # 90 × 1,5; 90 + июнь
    assert nowcast_months.month_marks(h, feed, "2026Q3", "2026-09-01") == {}                  # двух месяцев ещё нет
    assert nowcast_months.month_marks(h, feed, "2026Q1", "2026-04-01") == {"m12_flat": pytest.approx(120.0)}
    assert nowcast_months.guidance_marks(h, "2026Q3", "2026-10-13", 600.0) == {
        "guidance": 150.0, "guidance_rest": pytest.approx((600.0 - 230.0) / 2)}
    assert nowcast_months.guidance_marks(h, "2026Q1", "2026-03-01", 600.0) == {"guidance": 150.0, "guidance_rest": 150.0}
    assert nowcast_months.guidance_marks(h, "2026Q3", "2026-10-13", None) == {}
    ras = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 13), bridge={}, sigmas={})
    got = collect.target_benchmarks(store, "2026Q3", date(2026, 10, 13), ras, {"ni_q": 120.0, "nim_q_mgmt": 0.02})
    assert got["ni_q"]["guidance"] == 150.0 and got["ni_q"]["m12_flat"] == pytest.approx(135.0)   # гайденс — из фактов
    assert got["ni_q"]["prev_quarter"] == 100.0 and got["ni_q"]["model"] == 120.0 and "ras_bridge" not in got["ni_q"]
    assert got["nim_q"]["guidance"] == 0.03 and got["cor_q"]["guidance"] == 0.011 and "nim_q_f102" not in got
    for key in ("months", "m12_flat", "m12_prev3", "guidance_rest"):
        assert journal.BENCHMARK_TITLES[key] != key


def test_weights_come_from_the_retro_on_the_history(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    _history(store)
    today = date(2026, 10, 13)
    sig = retro.sigma_table(store, today=today)
    assert sig["estimate"] == "months" and sig["proxy"] == "prev_quarter" and sig["base_benchmark"] == "prev_quarter"
    # 2К2026 при двух месяцах: 30 + 35 + треть прошлого квартала (130) против факта 100
    errs = {"2025Q2": (100 + 120 / 3 - 150) / 150, "2025Q3": (50 + 150 / 3 - 90) / 90, "2025Q4": (95 + 90 / 3 - 160) / 160,
            "2026Q1": (80 + 160 / 3 - 130) / 130, "2026Q2": (65 + 130 / 3 - 100) / 100}
    assert sig["n"]["ras"]["2"] == 5 and sig["n"]["base"] == 5 and sig["quarters"] == sorted(errs)
    assert sig["ras"]["2"] == pytest.approx((sum(e * e for e in errs.values()) / 5) ** 0.5)
    base = [(120 - 150) / 150, (150 - 90) / 90, (90 - 160) / 160, (160 - 130) / 130, (130 - 100) / 100]
    assert sig["base"] == pytest.approx((sum(e * e for e in base) / 5) ** 0.5) and sig["ras"]["0"] is None
    assert sig["abs"]["base"] == pytest.approx((sum(x * x for x in (-30, 60, -70, 30, 30)) / 5) ** 0.5)
    levels = retro.ratio_sigma_table(store, bridge={}, today=today)
    assert set(levels) == {"nim", "cor"} and levels["nim"]["estimate"] == "months"
    assert levels["nim"]["n"]["ras"]["2"] == 2 and levels["nim"]["ras"]["2"] is not None       # 1К (с начала года) и 2К
    block = retro.retro(store, today=today)
    assert {"m12_flat", "m12_prev3", "prev_quarter"} <= set(block["rmse"]) and "ras_bridge" not in block["rmse"]
    assert set(block["rmse_abs"]) == set(block["rmse"]) and block["main"] == "model" and block["n"]["model"] == 0
    assert "m12_flat" not in block["by_horizon"]["T-90"]["rmse"]                  # на T-90 месяцев квартала ещё нет
    # печатный горизонт ретро — день, когда стал известен второй месяц (не раньше открытия квартала)
    h = nowcast.History.load(store)
    feed = nowcast_months.feeds(store)["ni_q"]
    assert nowcast_months.print_day(h, feed, "2025Q4", "2026-02-25") == "2025-12-26"
    assert nowcast_months.print_day(h, feed, "2026Q2", "2026-07-28") == "2026-06-26"
    assert nowcast_months.opening_day(h, "2026Q2", "2026-07-28") == "2026-04-29"


def test_the_repository_history_feeds_the_retro(monkeypatch, tmp_path):
    """История рядов репозитория: оценки по двум месяцам и наивные эталоны считаются, веса — в (0; 1)."""
    use_issuer(monkeypatch, tmp_path)
    store = Store(tmp_path / "seeded")
    seed.import_to_store(store)
    today = date(2026, 10, 13)
    sig = {**retro.sigma_table(store, today=today), **retro.ratio_sigma_table(store, bridge={}, today=today)}
    assert sig["n"]["ras"]["2"] >= 8 and sig["n"]["base"] >= 8 and sig["base_benchmark"] in nowcast_months.BASE_CANDIDATES
    for table in (sig, sig["nim"], sig["cor"]):
        w = nowcast.weight(table["base"], table["ras"]["2"])
        assert 0.0 < w < 1.0 and table["ras"]["2"] > 0 and table["base"] > 0
    assert sig["ras"]["2"] < sig["ras"]["1"]                       # второй месяц уточняет оценку
    block = retro.retro(store, today=today)
    assert block["n"]["m12_flat"] >= 12 and block["n"]["guidance"] >= 8 and block["n"]["consensus"] >= 8
    ras = nowcast.ras_inputs(store, period="2026Q3", today=today, bridge={})
    assert ras["months_known"] == 2 and ras["targets"]["ni_q"]["known_sum"] > 0 and 0 < ras["targets"]["nim_q"]["w"] < 1


# ------------------------------------------------------------------ запись журнала

def _nowcast(store, today, expectation):
    return collect.run_nowcast(store, today, journal=journal.Journal(store.root / "journal.sqlite"),
                               expectation=expectation, book_version="тест", to_mgmt_nim=lambda x: x)


def test_scoring_record_is_the_pure_model_and_print_record_carries_the_months(monkeypatch, tmp_path, capsys):
    store = _store(monkeypatch, tmp_path)
    monkeypatch.setattr(collect, "ensure_seed", lambda store: False)             # история — сочинённая, не репозитория
    _history(store)
    expectation = {"ni_q": 120.0, "nim_q_mgmt": 0.02, "cor_q_mgmt": 0.012}
    j = journal.Journal(store.root / "journal.sqlite")
    # 5 сентября: до отчёта 55 дней, известен один месяц — зачётный горизонт, запись — ожидание модели
    assert _nowcast(store, date(2026, 9, 5), expectation) == 0, capsys.readouterr().out
    row = j.forecast("ni_q", "2026Q3", "T-90")
    assert row["forecast"] == 120.0 and row["inputs"]["w"] == 0.0 and row["equation"] == collect.SCORING_PURE
    assert row["inputs"]["months_known"] == 1 and row["benchmarks"]["model"] == 120.0
    assert row["benchmarks"]["months"] == pytest.approx(40.0 + 80.0)              # сама оценка — эталоном рядом
    assert j.forecast("nim_q", "2026Q3", "T-90")["forecast"] == 0.02 and j.forecast("ni_q", "2026Q3", "T-30") is None
    live = store.read_state("nowcast.json")
    assert live["horizon"] == "T-90" and live["quarter"]["by_target"]["ni_q"]["w"] > 0   # живой нау-каст оценку несёт
    # 29 сентября: вышел второй месяц — печатный горизонт, запись несёт оценку по месяцам
    assert _nowcast(store, date(2026, 9, 29), expectation) == 0, capsys.readouterr().out
    row = j.forecast("ni_q", "2026Q3", "T-30")
    assert row["inputs"]["months_known"] == 2 and row["inputs"]["w"] > 0 and row["forecast"] != 120.0
    assert row["benchmarks"]["months"] == pytest.approx(130.0) and row["benchmarks"]["m12_flat"] == pytest.approx(135.0)
    assert row["benchmarks"]["guidance"] == 150.0 and "МСФО" in row["equation"]
    assert j.frozen("nim_q", "2026Q3", "sigmas") is not None and j.frozen("cor_q", "2026Q3", "sigmas") is not None
    assert j.forecast("ni_q", "2026Q3", "T-90")["forecast"] == 120.0              # запись зачётного горизонта окончательна


# ------------------------------------------------------------------ выходы для выпуска

def test_release_inputs_carry_the_flows_table_and_the_shares_flag(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    seed.import_to_store(store)
    today = date(2026, 10, 13)
    out = outputs.release_inputs(tickers=["VTBR"], peer_tickers=[], state_dir=state, today=today)
    assert out.months_basis == "ifrs" and out.ops_months == () and out.form102 == ()
    rows = {r["month"]: r for r in out.ras_months}
    assert len(rows) == 15 and max(rows) == "2026M08"
    last = rows["2026M08"]
    required = {"month", "ni", "ni_ytd", "nii", "fees", "llp", "opex", "cor", "roe", "loans_corporate", "loans_retail",
                "funds_retail", "funds_corporate", "n1_0", "n1_1", "source", "published_at"}
    assert required <= set(last) and {"nim", "n20_0", "n20_1", "n20_2"} <= set(last)
    assert last["ni"] > 0 and last["llp"] < 0 and last["n1_0"] is None and 0 < last["n20_0"] < 0.3 and 0 < last["nim"] < 0.1
    assert last["source"] == "seed" and last["published_at"][:10] == "2026-09-29" and "derived" not in last
    assert rows["2026M06"]["derived"] is True and rows["2026M06"]["ni"] is not None      # месяц получен разностью
    assert rows["2026M02"]["ni"] is None and rows["2026M02"]["ni_ytd"] > 0                # два месяца — одной суммой
    assert out.flags["ras_mismatch"] == {"raised": False, "detail": ""}
    assert out.ras_schedule["month"] == "2026M10" and out.ras_schedule["enters_via"] == "release"
    assert out.ras_schedule["form102_date_est"] is None
    # число акций по бирже (история рядов) против фактов заглушки: расхождение — флаг выходов
    flag = out.flags["shares_changed"]
    assert flag["raised"] and flag["facts_mln"] == 12900.0 and "на бирже" in flag["detail"] and "в фактах 12 900,0 млн" in flag["detail"]
    same = store.load("iss.issue_size.VTBR").latest().value / 1e6
    monkeypatch.setattr(config, "facts_file", lambda name, facts_dir=None: {"issued_ordinary": {"v": same}} if name == "shares" else None)
    assert outputs.shares_flag(outputs._Reader(store=store, today=today), "VTBR")["raised"] is False
    monkeypatch.setattr(config, "facts_file", lambda name, facts_dir=None: {})
    quiet = outputs.shares_flag(outputs._Reader(store=store, today=today), "VTBR")
    assert quiet["raised"] is False and "сверять не с чем" in quiet["detail"]
    assert outputs.shares_flag(outputs._Reader(store=Store(tmp_path / "empty"), today=today), "VTBR") is None
    # плитки настройки: коды единиц и базисов — из словаря выпуска, ряды месячных результатов есть в истории
    tiles = {t["id"]: t for t in out.tiles}
    assert tiles["m_np_m"]["status"] == "ok" and tiles["m_np_m"]["basis"] == "ifrs" and tiles["m_np_m"]["value"] > 0
    assert tiles["m_n20_0"]["basis"] == "regulatory" and tiles["f135_n1_0"]["status"] in ("ok", "stale")
    closes = out.price_history["VTBR"]
    assert len(closes) > 200 and closes[-1][0] <= today.isoformat()               # закрытия — из истории рядов


def test_iss_writes_the_share_count_only_by_the_setting(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    today = date(2026, 10, 26)
    res = iss.collect(_ctx(store, today))
    assert res.status == OK, res.reasons
    count = store.load("iss.issue_size.VTBR")
    assert count.latest().value == 12927766416.0 and count.meta["unit"] == "shares"
    assert store.load("iss.issue_size.SBER") is None                              # число акций аналога не нужно
    plain = Store(tmp_path / "plain")
    cfg = {**config.sources(), "iss": {"board": "TQBR"}}
    iss.collect(Context(store=plain, today=today, company=config.company(), cfg=cfg, getter=FakeGetter()))
    assert plain.load("iss.issue_size.VTBR") is None and plain.load("iss.price.VTBR") is not None
    # консолидация: коэффициент меньше единицы — закрытия до неё в нынешних акциях кратно выше
    rows = [{"date": "2024-07-08", "close": 0.02}, {"date": "2024-07-15", "close": 93.0}]
    assert [r["close"] for r in iss.split_adjust(rows, config.corporate_actions())] == [pytest.approx(100.0), 93.0]


# ------------------------------------------------------------------ гайденс и реестр

def test_guidance_of_the_year_profit_is_money_not_a_share(monkeypatch, tmp_path):
    store = _store(monkeypatch, tmp_path)
    assert record.money_guidance_items() == ("net_profit",) and "net_profit" in record.guidance_items()
    assert record.record_guidance(store, year=2027, item="net_profit", value="650", source="слова менеджмента") == 650.0
    assert store.load("guidance.net_profit").meta["unit"] == "RUB bn"
    assert record.record_guidance(store, year=2027, item="nim", value="3%", source="слова менеджмента") == pytest.approx(0.03)
    with pytest.raises(record.RecordError, match="доля больше"):
        record.record_guidance(store, year=2027, item="cor", value="1.1", source="слова менеджмента")
    assert nowcast.guidance_point(store, "net_profit", 2027, "9999-12-31") == 650.0     # запись — с момента ввода
    # факты: точка года и её пересмотр — что было известно на дату
    assert nowcast.guidance_point(store, "net_profit", 2026, "2026-10-13") == 600.0
    assert nowcast.guidance_point(store, "net_profit", 2026, "2026-05-01") == 625.0
    assert nowcast.guidance_point(store, "net_profit", 2026, "2026-01-15") is None


def test_the_register_is_annual_by_default(monkeypatch, tmp_path):
    """Годовой дивиденд — умолчание кода: ключ записи — год прибыли, запись брокера — год отсечки минус лаг."""
    store = _store(monkeypatch, tmp_path)
    cfg = config.sources()
    assert register.period_rule(cfg) == "annual" and "period_patterns" not in cfg["dividends"]
    assert register.broker_split_adjusted(cfg) and config.dividend_calendar()["frequency"] == "annual"
    payload = json.loads((FIX / "tinvest" / "dividends_T.json").read_text(encoding="utf-8"))      # синтетика формата ответа
    rows = tinvest.parse_dividends(payload)
    assert rows and all(r["period"] is None and r["year"] == int(r["record_date"][:4]) - 1 for r in rows)
    # тревога: собрание — во втором квартале; год с выплаченной записью стартового реестра фактов закрыт
    assert register.alarm_from_book([], date(2026, 10, 13)) is None
    text = register.alarm_from_book([], date(2027, 7, 5))
    assert text and "за 2026 год" in text and "2027-06-30" in text
    assert register.alarm_from_book([], date(2027, 6, 30)) is None                # срок ещё не прошёл
    rec = register.record_manual(store, year=2026, period=None, label=None, dps=12.0, status="declared",
                                 source="решение годового собрания", record_date="2027-07-12", decided_date="2027-06-30")
    assert rec["year"] == 2026 and rec["period"] is None
    assert collect.register_check(_ctx(store, date(2026, 10, 13))).status == OK
