"""История рядов `data/indicators/seed/`: у каждого числа источник, импорт идемпотентен, сборка воспроизводима."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from indicators import collect, config, periods, release_watch, seed
from indicators.store import Store
from tests.support_ind import use_fixtures, use_form_settings, use_issuer

SKIPPED = (1, 3, 6, 9, 12)           # месяцы без своего релиза: отдельной книги эмитент за них не печатает
NOT_BUILT = ("form101", "form102")   # истории форм 0409101 и 0409102 у этой копии нет: моста к отчётности группы нет


@pytest.mark.tact
def test_every_seed_number_has_a_source():
    present = [n for n in seed.SEED_FILES if n not in NOT_BUILT]
    for name in present:
        assert config.load_seed(name) is not None and config.load_seed(name).get("source"), name
    assert all(config.load_seed(n) is None for n in NOT_BUILT)
    spec = release_watch.monthly(config.sources())
    monthly = config.load_seed("monthly_release")
    assert monthly["prefix"] == spec.prefix and monthly["basis"] == spec.basis == "ifrs"
    books = 0
    for m, entry in monthly["months"].items():
        _, number = periods.parse_month(m)
        own = entry["release_date"] is not None
        books += own
        if own:
            # месяц своей книги: день релиза — после конца месяца, главная метрика — из книги
            assert number not in SKIPPED and entry["release_date"] > periods.month_end(m).isoformat(), m
            assert spec.main in entry["values"] and "at" not in entry["values"][spec.main], m
            assert ("np_m" in entry["values"]) == (number != 2), m             # за два месяца — только нарастающий итог
        for metric, node in entry["values"].items():
            assert metric in spec.metrics and node["src"], (m, metric)
            if own and "at" not in node:
                assert "sha256" in node["src"], (m, metric)                    # число книги — с хэшем файла
            else:
                assert node["at"] > periods.month_end(m).isoformat(), (m, metric)   # свой день известности
            if metric in release_watch.SHARE_METRICS:
                assert -0.1 < node["v"] < 2.5, (m, metric)                     # доли, не проценты
            if node.get("derived"):
                assert "разность" in node["src"], (m, metric)
    assert books >= 25 and max(monthly["months"]) >= "2026M08"
    quarter_end = monthly["months"]["2026M06"]["values"]
    assert quarter_end["np_m"]["derived"] and "derived" not in quarter_end["np_ytd"]   # итог — из отчёта, месяц — разность
    assert "nim_m" not in quarter_end                                           # уровень месяца без релиза не вывести
    ifrs = config.load_seed("ifrs_quarters")["quarters"]
    for q, e in ifrs.items():
        periods.parse_quarter(q)
        assert e["value"]["src"] and "sha256" in e["value"]["src"] and 0 < e["value"]["v"] < 400, q
        assert e["report_date"]["v"] > periods.quarter_end(q).isoformat() and e["report_date"]["src"], q
    # нарастающий итог конца квартала в месячном ряду — сумма кварталов года по отчёту этого квартала
    assert quarter_end["np_ytd"]["v"] == pytest.approx(ifrs["2026Q1"]["value"]["v"] + ifrs["2026Q2"]["value"]["v"], abs=0.5)
    for q, e in config.load_seed("mgmt_quarters")["quarters"].items():
        assert set(e) == {"nim", "cor"} and all(n["src"] for n in e.values()), q
        assert all(-0.02 <= n["v"] < 0.2 for n in e.values()), q               # доли, не проценты
    for name, keys in (("form135", {"n1_0", "n1_1", "n1_2"}), ("form123", {"capital_total", "capital_base"})):
        rows = config.load_seed(name)["months"]
        assert keys <= set(rows[max(rows)]) and periods.form_month(rows[max(rows)]["form_date"]) == max(rows), name
        assert all(r["sha256"] for r in rows.values()), name
    group = config.load_seed("group_forms")["quarters"]
    for q, e in group.items():
        periods.parse_quarter(q)
        assert 0.05 < e["f805"]["n20_0"] < 0.3 and e["f805"]["capital_total"] > e["f805"]["capital_base"], q
        assert e["f805"]["n20_1"] < e["f805"]["n20_0"] and e["f805"]["sha256"], q
    consensus = config.load_seed("consensus")["quarters"]
    assert consensus and all(e["src"] and e["at"] < ifrs[q]["report_date"]["v"] for q, e in consensus.items())
    guidance = config.load_seed("guidance")["items"]
    assert set(guidance) == {"net_profit", "nim", "cor"} and guidance["net_profit"]["unit"] == "RUB bn"
    for item, body in guidance.items():
        for year, rows in body["years"].items():
            assert rows == sorted(rows, key=lambda r: r["date"]) and all(r["src"] and r["date"][:4] == year for r in rows)
            assert all(r["v"] is None or (r["v"] > 50 if item == "net_profit" else 0 < r["v"] < 0.1) for r in rows), item
    assert any(r["v"] is None for rows in guidance["cor"]["years"].values() for r in rows)   # граница — не точка
    shares = config.load_seed("shares")["rows"]
    assert [r["date"] for r in shares] == sorted(r["date"] for r in shares) and all(r["src"] and r["v"] > 1e9 for r in shares)
    prices = config.load_seed("prices")
    rows = [row.split(";") for row in prices["rows"]]
    assert prices["columns"] == ["date", "close", "volume"] and len(rows) > 500
    assert all(len(r) == 3 and 10 < float(r[1]) < 1000 and int(r[2]) >= 0 for r in rows)   # закрытия — в нынешних акциях
    dividends = config.load_seed("dividends")["years"]
    assert all(e["dps"]["v"] > 0 and e["dps"]["src"] for e in dividends.values())
    assert all((e["record_date"] is None) or e["decided_date"] for e in dividends.values())


@pytest.mark.tact
def test_import_of_the_repository_history_dates_knowledge(monkeypatch, tmp_path):
    """История репозитория в рядах: момент точки — день, когда число стало известно; импорт идемпотентен."""
    use_issuer(monkeypatch, tmp_path)
    store = Store(tmp_path / "seeded")
    touched = seed.import_to_store(store)
    counts = {sid: len(store.load(sid).points) for sid in touched}
    seed.import_to_store(store)
    assert {sid: len(store.load(sid).points) for sid in touched} == counts
    assert {"ifrs.release.np_ytd", "ifrs.release.np_m", "ifrs.release.nim_m", "ifrs.release.loans_gross", "actual.ni_q",
            "actual.nim_q", "actual.cor_q", "consensus.ni_q", "guidance.net_profit", "guidance.nim", "guidance.cor",
            "cbr.f135.n1_0", "cbr.f123.capital_total", "cbr.f805.n20_0", "iss.issue_size.VTBR",
            "iss.close.VTBR"} <= set(touched)
    assert not [sid for sid in touched if sid.startswith(("cbr.f101.", "cbr.f102.", "ops.release.", "ras.release."))]
    monthly = config.load_seed("monthly_release")["months"]
    profit = store.load("ifrs.release.np_m")
    assert profit.first_seen("2026M08")[:10] == monthly["2026M08"]["release_date"]       # момент — день релиза
    assert profit.meta["basis"] == "ifrs" and profit.meta["unit"] == "RUB bn"
    assert store.load("ifrs.release.nim_m").meta["unit"] == "share"
    # месяц без своего релиза известен со дня отчёта МСФО; пометка «получен разностью» доходит до ряда
    report = config.load_seed("ifrs_quarters")["quarters"]["2026Q2"]["report_date"]["v"]
    assert profit.first_seen("2026M06")[:10] == report and profit.point_as_of("2026M06").note == release_watch.DERIVED_NOTE
    assert profit.value_as_of("2026M06", "2026-07-01") is None                            # до отчёта месяц неизвестен
    assert store.load("actual.ni_q").first_seen("2026Q2")[:10] == report
    assert store.load("actual.ni_q").meta["basis"] == "ifrs"                              # базис цели — подпись книги
    # гайденс года — винтажами по датам; граница без точки — «нет значения»
    guidance = store.load("guidance.net_profit")
    assert guidance.value_as_of("2024", "2024-03-01") == 435.0 and guidance.value_as_of("2024", "2024-08-01") == 550.0
    assert guidance.value_as_of("2024", "2024-02-01") is None
    cor = store.load("guidance.cor")
    assert cor.value_as_of("2024", "2024-03-01") == 0.01 and cor.value_as_of("2024", "2024-08-01") is None
    count = store.load("iss.issue_size.VTBR")
    assert count.value_as_of("2024-07-15") == 5369933893.0 and count.latest().value > 1e10
    n20 = store.load("cbr.f805.n20_0")
    last_q = max(n20.history())
    assert n20.first_seen(last_q)[:10] > periods.quarter_end(last_q).isoformat() and n20.meta["unit"] == "share"


@pytest.mark.tact
def test_form101_history_follows_the_facts_definition(monkeypatch, tmp_path):
    """История формы 101 идёт в ряды, только если построена под определение процентных активов фактов."""
    use_fixtures(monkeypatch, tmp_path)
    data = config.load_seed("form101")
    assert not seed.form101_fits(data)                               # у пробных фактов определение своё
    assert "cbr.f101.iea" not in seed.import_to_store(Store(tmp_path / "other"))
    store = Store(tmp_path / "mark")
    assert collect.ensure_seed(store) and not collect.ensure_seed(store)
    assert store.load("cbr.f101.iea") is None
    same = {"iea": {"codes": data["codes"], "codes_required": data["codes_required"]}}
    monkeypatch.setattr(config, "bridge_ras_ifrs", lambda facts_dir=None: same)
    assert seed.form101_fits(data) and not seed.form101_fits(None)
    assert collect.ensure_seed(store)                                # определение сменилось — история перечитана
    assert set(store.load("cbr.f101.iea").history()) == set(data["months"])
    assert not collect.ensure_seed(store)


@pytest.mark.tact
@pytest.mark.parametrize("form", [False, True], ids=["repository", "sample-form"])
def test_seed_holds_no_raw_broker_answers(monkeypatch, form):
    """В истории нет сырых ответов брокера и имён полей его ответа: только ряды с источником."""
    if form:
        use_form_settings(monkeypatch)
    assert sorted(config.SEED_DIR.glob("*.json"))
    for path in sorted(config.SEED_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"dividendNet|recordDate|lastBuyDate|paymentDate|instrumentUid|targetPrice", text), path.name
        assert "invest-public-api" not in text, path.name


@pytest.mark.tact
def test_import_is_idempotent_and_dates_knowledge(monkeypatch, tmp_path):
    """Форма образца (месячный релиз остатков, формы 0409101 и 0409102): тот же импорт на её истории."""
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "seeded")
    touched = seed.import_to_store(store)
    counts = {sid: len(store.load(sid).points) for sid in touched}
    seed.import_to_store(store)
    assert {sid: len(store.load(sid).points) for sid in touched} == counts
    assert {"ops.release.loans_gross", "ops.release.np_ytd", "actual.ni_q", "actual.nim_q", "actual.cor_q",
            "cbr.f102.ni_ytd", "cbr.f102.nii_ytd", "cbr.f135.n1_0", "cbr.f123.capital_total", "cbr.f805.n20_0",
            "cbr.f803.ni_ytd"} <= set(touched)
    monthly = config.load_seed("monthly_release")["months"]
    m = max(monthly)
    loans = store.load("ops.release.loans_gross")
    assert loans.first_seen(m)[:10] == monthly[m]["release_date"]            # момент — день релиза
    assert loans.meta["unit"] == "RUB bn" and store.load("ops.release.clients_total").meta["unit"] == "mn"
    assert store.load("ops.release.n1_0").meta["unit"] == "share"
    act = store.load("actual.ni_q")
    q = max(config.load_seed("ifrs_quarters")["quarters"])
    assert act.first_seen(q)[:10] == config.load_seed("ifrs_quarters")["quarters"][q]["report_date"]["v"]
    assert act.meta["basis"] == "mgmt"                                       # базис цели — подпись книги
    f102 = store.load("cbr.f102.ni_ytd")
    last = max(f102.history())
    assert f102.first_seen(last)[:10] > config.load_seed("form102")["months"][last]["form_date"]   # выкладка — позже даты формы
    n20 = store.load("cbr.f805.n20_0")
    last_q = max(n20.history())
    assert n20.first_seen(last_q)[:10] > periods.quarter_end(last_q).isoformat() and n20.meta["unit"] == "share"


@pytest.mark.archive
def test_seed_rebuild_matches_committed_files():
    root = os.environ.get("BANK_HANDOFF_DIR")
    if not root:
        pytest.skip("нужна папка передачи (BANK_HANDOFF_DIR)")
    built = seed.build_all(Path(root), tuple(n for n in seed.SEED_FILES if config.load_seed(n) is not None))
    assert built
    for name, obj in built.items():
        assert (config.SEED_DIR / f"{name}.json").read_text(encoding="utf-8") == seed.dump(obj), name
