# -*- coding: utf-8 -*-
"""Сборщик фактов в сухом прогоне перезаякоривания: режим `build_facts.py --expected` и файл отчёта квартала.

`--expected` строит факты следующего квартала из фактов якоря и отчёта квартала (`quarter-report/1`) — вторая,
независимая от `ops/tools/reanchor.py` сборка тех же правил переноса (М§15.2): ядро обязано прочесть из обеих
одно состояние якоря (`reanchor.py --compare-facts`). Быстрые тесты (`tact`) — без книги и без прогона сетки, на
отчёте, собранном из закоммиченных фактов и перенесённом на следующий квартал: состав и тождества новых фактов, ставки
якоря несут весь ЧПД, строка истории баланса несёт остатки книг, решение собрания (годовой календарь) — строкой истории
дивидендов, пометка оценки нормативов, отказы. С настоящей книгой (`ci_only`): рабочие факты кандидата
`reanchor.facts_after` на том же отчёте дают ядру то же состояние (без сетки); три квартала подряд с прогоном сетки
(якорь на четвёртом квартале, смена года якоря, квартал собрания) — одно состояние и одна точка.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from model.book import Facts, anchor_facts, canonical_json
from model.grid import run_grid
from tests.support_core import real_book_or_skip
from tests.test_reanchor import R, scene_of

tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
BUILDER = ROOT / "ops" / "tools" / "build_facts.py"


def _builder():
    spec = importlib.util.spec_from_file_location("build_facts_for_reanchor", BUILDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


B = _builder()


def committed() -> dict[str, dict]:
    return {k: json.loads((FACTS / f"{k}.json").read_text(encoding="utf-8")) for k in B.BUILT}


def next_report(decision: bool = False) -> dict:
    """Отчёт квартала якоря из закоммиченных фактов, перенесённый на следующий квартал: числа те же, период и дата —
    следующие, решений нет. `decision` — решение собрания в закрываемом квартале (годовой календарь: за год прибыли,
    с суммой на все категории акций — базой объёма iea) и дивиденд к выплате на конец квартала."""
    facts = committed()
    report = B.report_from_facts(facts, source="тест: факты якоря как отчёт следующего квартала")
    period = B.q_next(report["period"])
    end = B.q_end(period)
    report.update(period=period, as_of=end.isoformat(), dividend_decisions=[])
    report.pop("published", None)
    if decision:
        year = int(period[:4])
        report["dividend_decisions"] = [{"period": f"{year - 1}Q4", "dps": 5.0, "decided_date": end.replace(day=15).isoformat(),
                                         "record_date": B.q_end(B.q_next(period)).replace(day=10).isoformat(),
                                         "pool_all_classes": 64.6}]
        b = report["balance"]
        b.update(dividends_payable=64.6, other_liabilities=b["other_liabilities"] - 64.6, dividends_payable_year=year - 1)
        report["capital"]["n20_pre_dividend"] = True
    return report


def as_facts(files: dict[str, dict]) -> Facts:
    full = {**{k: json.loads((FACTS / f"{k}.json").read_text(encoding="utf-8")) for k in B.MANUAL}, **files}
    return Facts(root=Path("expected"), files=full, digest=hashlib.sha256(canonical_json(full)).hexdigest())


# ------------------------------------------------------------------ без прогона сетки (такт)


@tact
def test_the_quarter_report_names_decisions_of_the_quarter_and_fixed_other_assets():
    """Файл отчёта квартала из фактов якоря называет решения собраний, принятые в квартале якоря (периодом, с днём
    решения и датами), и постоянную часть прочих активов; состав читает `reanchor.py`."""
    facts = committed()
    report = B.report_from_facts(facts, source="тест")
    period, as_of = facts["anchor"]["period"], facts["anchor"]["as_of"]
    opened = B.q_end(B.q_prev(period)).isoformat()
    want = [h["period"] for h in facts["dividends"]["history"] if opened < h["decided_date"] <= as_of]
    assert [d["period"] for d in report["dividend_decisions"]] == want
    for d in report["dividend_decisions"]:
        assert set(d) <= set(R.DECISION_REQUIRED + R.DECISION_OPTIONAL) and set(R.DECISION_REQUIRED) <= set(d)
        assert opened < d["decided_date"] <= as_of
    assert report["balance"]["other_assets_fixed"] == facts["balance"]["other_assets_fixed"]["v"]
    assert set(report) - set(R.TOP_REQUIRED) <= set(R.TOP_OPTIONAL)
    for name, (required, optional) in R.SECTIONS.items():
        assert set(required) <= set(report[name]) <= set(required + optional), name
    B.check_report_shape(report)


@tact
def test_expected_facts_of_the_next_quarter_keep_the_identities():
    """Факты следующего квартала из фактов якоря и отчёта квартала: якорь, прямые книги, тождество баланса, ставки
    якоря несут весь ЧПД, квартал добавлен в истории (с остатками книг), окна мостов продлены. Вход не меняется."""
    prev, report = committed(), next_report()
    before = copy.deepcopy(prev)
    files, checks = B.expected_facts(prev, report, name="report.json", sha="ab" * 32)
    assert prev == before and all(ok for _, ok, _ in checks), [c for c in checks if not c[1]]
    period = report["period"]
    assert files["anchor"]["period"] == period and files["anchor"]["expected"]["from_anchor"] == prev["anchor"]["period"]
    assert tuple(files) == B.BUILT
    bal, nb = files["balance"], files["nii_books"]
    assert {b: bal["books"][b]["v"] for b in B.BOOKS} == report["balance"]["books"]
    assets = sum(bal["books"][b]["v"] for b in B.books_of("asset")) - bal["allowance_ac"]["v"] + bal["other_assets"]["v"]
    assert bal["total_assets"]["v"] == pytest.approx(assets) == pytest.approx(
        bal["total_liabilities"]["v"] + bal["equity"]["total"]["v"], abs=0.2)
    assert bal["securities"]["fvoci_debt"]["v"] + bal["securities"]["fvoci_repo"]["v"] == pytest.approx(report["balance"]["fvoci"])
    assert sum(bal["securities"][k]["v"] for k in ("fvoci_debt", "fvoci_repo", "ac", "ac_repo", "fvtpl_bonds")) == \
        pytest.approx(report["balance"]["books"]["securities"], abs=1e-5)
    assert set(bal["history"]) - set(prev["balance"]["history"]) == {period}
    row = bal["history"][period]
    assert row["loans"]["v"] == pytest.approx(sum(report["balance"]["books"][b] for b in B.books_of(loans=True)))
    assert row["loans_ac_gross"]["v"] == row["loans"]["v"] and row["funds"]["v"] > 0
    assert row["iea"]["v"] == pytest.approx(sum(report["balance"]["books"][b] for b in B.books_of("asset")))
    assert {b: row["books"][b]["v"] for b in B.BOOKS} == pytest.approx(report["balance"]["books"]), "остатки книг на конец квартала"
    assert all("books" in r for r in bal["history"].values())
    # ставки якоря несут весь ЧПД
    assert nb["rates_carry_residual"] is True and nb["period"] == period
    days = nb["days"]["v"]
    carried = sum((1 if b in B.books_of("asset") else -1) * nb["books"][b]["rate_anchor"]["v"] * nb["books"][b]["balance_avg"]["v"]
                  for b in B.BOOKS) * days / 365 - nb["dia_q"]["v"]
    assert carried == pytest.approx(report["pnl"]["nii"], abs=1e-4)
    assert nb["other_interest_net_q"]["v"] == pytest.approx(
        report["pnl"]["nii"] - (nb["interest_assets_q"]["v"] - nb["interest_liabilities_q"]["v"] - nb["dia_q"]["v"]), abs=1e-5)
    # ОПУ, капитал, мосты
    q = files["pnl_quarterly"]["quarters"][period]
    assert q["ni_shareholders"]["v"] == report["pnl"]["ni_shareholders"] and q["ni_nci"]["v"] == pytest.approx(
        report["pnl"]["ni"] - report["pnl"]["ni_shareholders"])
    cap = files["capital"]
    assert cap["n20_0"]["value"]["v"] == report["capital"]["n20_0"] and cap["n20_0"]["estimated"] is False
    assert cap["history"][-1]["period"] == period
    assert cap["t2_recognized"]["v"] == prev["capital"]["t2_recognized"]["v"], "отчёт без capital.t2 — слот прежний"
    br = files["bridge_mgmt_ifrs"]
    for x in ("cor", "nim", "cir"):
        assert br[x]["history"][-1]["period"] == period and br[x]["window"][1] == period
        assert br[x]["n"]["v"] == prev["bridge_mgmt_ifrs"][x]["n"]["v"] + 1
    assert {"engine_x4", "gap_x4"} <= set(br["nim"]["history"][-1]) and "gap_x4" not in br["cir"]["history"][-1]
    # дивиденды: годовой календарь, решений в квартале нет
    assert files["dividends"]["history"] == prev["dividends"]["history"] and bal["dividends_payable_declared"] == []


@tact
def test_expected_facts_carry_estimates_decisions_and_refuse_a_wrong_report():
    prev, report = committed(), next_report(decision=True)
    estimate = {slot: {"bank_value": report["capital"][slot] - 0.003, "spread": 0.003, "spread_as_of": prev["anchor"]["as_of"]}
                for slot in ("n20_0", "n1_1_bank")}
    rep = copy.deepcopy(report)
    rep["capital"].update(estimated=True, estimate=estimate)
    rep["pnl"]["estimated"] = True
    files, checks = B.expected_facts(prev, rep, name="report.json", sha="cd" * 32)
    assert all(ok for _, ok, _ in checks)
    cap = files["capital"]
    for slot in ("n20_0", "n1_1_bank"):
        assert cap[slot]["estimated"] is True and cap[slot]["value"]["estimated"] is True
        assert cap[slot]["estimate"]["bank_value"]["v"] == estimate[slot]["bank_value"]
    assert cap["n20_0"]["pre_dividend"] is True
    assert files["pnl_quarterly"]["quarters"][rep["period"]]["ni_shareholders"]["estimated"] is True
    (decision,) = rep["dividend_decisions"]
    history = {h["period"]: h for h in files["dividends"]["history"]}
    row = history[decision["period"]]
    assert row["decided_date"] == decision["decided_date"] and row["dps"]["v"] == decision["dps"]
    assert row["pool_all_classes"]["v"] == decision["pool_all_classes"], "сумма, вычтенная из капитала, — база объёма iea"
    assert files["balance"]["dividends_payable_year"] == int(decision["period"][:4])
    for change, fragment in ((lambda x: x.update(period=prev["anchor"]["period"]), "следующего"),
                             (lambda x: x.update(extra=1), "незнакомый ключ extra"),
                             (lambda x: x["balance"]["books"].pop("mortgage"), "balance.books.mortgage"),
                             (lambda x: x["capital"].pop("estimate"), "capital.estimate"),
                             (lambda x: x.update(as_of=prev["anchor"]["as_of"]), "не конец квартала"),
                             (lambda x: x["dividend_decisions"][0].update(decided_date=prev["anchor"]["as_of"]), "позже")):
        bad = copy.deepcopy(rep)
        change(bad)
        with pytest.raises(B.BuildError) as exc:
            B.expected_facts(prev, bad, name="report.json", sha="cd" * 32)
        assert fragment in str(exc.value), str(exc.value)
    unbalanced = copy.deepcopy(report)
    unbalanced["balance"]["other_assets"] += 10
    assert not all(ok for _, ok, _ in B.expected_facts(prev, unbalanced, name="report.json", sha="cd" * 32)[1])


@tact
def test_rates_carry_the_residual_from_the_first_reanchored_quarter():
    """Параметр сборщика: с первого якоря после книги ставки книг активов несут и проценты вне книг — то же правило,
    что у `reanchor.py`; надбавка за субординацию отчёта — вне книг, остатка не меняет."""
    anchor = json.loads((FACTS / "anchor.json").read_text(encoding="utf-8"))["period"]
    nb = json.loads((FACTS / "nii_books.json").read_text(encoding="utf-8"))
    assert (nb["rates_carry_residual"] is True) == (anchor >= B.RATES_CARRY_FROM)
    interest = {b: (10.0 if b in B.books_of("asset") else 4.0) for b in B.BOOKS}
    income, expense = 10.0 * len(B.books_of("asset")), 4.0 * len(B.books_of("liability"))
    residual, scale = B.carry_scale(interest, income - expense - 1.0 + 2.0, 1.0)
    assert residual == pytest.approx(2.0) and scale == pytest.approx(1 + 2.0 / income)
    prev, report = committed(), next_report()
    rep = copy.deepcopy(report)
    rep["pnl"]["t2_premium"] = 1.5
    plain = B.expected_facts(prev, report, name="r.json", sha="ab" * 32)[0]["nii_books"]
    with_premium = B.expected_facts(prev, rep, name="r.json", sha="ab" * 32)[0]["nii_books"]
    assert with_premium["other_interest_net_q"]["v"] == pytest.approx(plain["other_interest_net_q"]["v"] + 1.5)


@tact
def test_the_expected_mode_writes_only_outside_the_canon(tmp_path):
    """`--expected ФАЙЛ --out КАТАЛОГ`: файлы сборщика и копии ручных файлов; без --out или в data/facts — отказ;
    папка передачи не нужна; повтор с `--check` — совпадение."""
    report = tmp_path / "report.json"
    report.write_text(json.dumps(next_report(), ensure_ascii=False), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "BANK_HANDOFF_DIR"} | {"PYTHONIOENCODING": "utf-8"}
    run = lambda *a: subprocess.run([sys.executable, "-B", str(BUILDER), *a], cwd=ROOT, env=env, capture_output=True,   # noqa: E731
                                    text=True, encoding="utf-8")
    for args in (("--expected", str(report)), ("--expected", str(report), "--out", str(FACTS))):
        res = run(*args)
        assert res.returncode == 1 and "только в --out" in res.stderr
    out = tmp_path / "facts"
    res = run("--expected", str(report), "--out", str(out))
    assert res.returncode == 0, res.stderr[-1500:]
    assert sorted(p.stem for p in out.glob("*.json")) == sorted(B.BUILT + B.MANUAL)
    assert all(b"\r\n" not in p.read_bytes() for p in out.glob("*.json"))
    assert json.loads((out / "calendar.json").read_text(encoding="utf-8")) == json.loads(
        (FACTS / "calendar.json").read_text(encoding="utf-8"))
    assert run("--expected", str(report), "--out", str(out), "--check").returncode == 0
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({**next_report(), "period": "1999Q4"}), encoding="utf-8")
    res = run("--expected", str(wrong), "--out", str(out))
    assert res.returncode == 1 and "ПРОВАЛ" in res.stderr


# ------------------------------------------------------------------ с настоящей книгой (CI)


@ci_only
@pytest.mark.parametrize("decision", (False, True))
def test_the_collector_and_the_tool_read_one_anchor_without_the_grid(decision):
    """Настоящая книга, отчёт из фактов якоря на следующем квартале (с решением собрания и без): факты
    `build_facts.py --expected` и рабочие факты кандидата `reanchor.facts_after` — одно состояние якоря для ядра
    (сверка `compare_facts` пуста); ядро читает факты сборщика."""
    book, facts = real_book_or_skip()
    prev = {k: copy.deepcopy(facts.files[k]) for k in B.BUILT}
    report = next_report(decision)
    files, checks = B.expected_facts(prev, report, name="report.json", sha="ef" * 32)
    assert all(ok for _, ok, _ in checks), [c for c in checks if not c[1]]
    canon = as_facts(files)
    assert R.compare_facts(book, R.facts_after(book, facts, report), canon) == []
    af = anchor_facts(canon, book.get("nii.books"))
    assert af.period == report["period"] and af.bv == report["balance"]["bv_common"]


@ci_only
def test_the_collector_and_the_tool_give_the_core_one_anchor_three_quarters_in_a_row():
    """Настоящая книга, три ожидаемых отчёта подряд: факты `build_facts.py --expected` и рабочие факты кандидата
    `reanchor.py` — одно состояние якоря (сверка `--compare-facts` пуста) и одна точка на книге-кандидате. Второй
    шаг — смена года якоря (концы прошлого года, окно моста ЧПМ), третий — квартал собрания (годовой календарь:
    решение — строкой истории дивидендов с суммой на все категории акций)."""
    book, facts = real_book_or_skip()
    prev = {k: copy.deepcopy(facts.files[k]) for k in B.BUILT}
    seen_decision, seen_year = False, False
    for _ in range(3):
        s = scene_of(book, facts)
        files, checks = B.expected_facts(prev, s.expected, name="expected.json", sha="ef" * 32)
        assert all(ok for _, ok, _ in checks), [c for c in checks if not c[1]]
        canon = as_facts(files)
        assert R.compare_facts(s.book, s.cand.facts, canon) == [], s.period
        run = run_grid(s.cand.book, canon, R.live_at(s.cand.book, canon, s.v))
        assert run.point == pytest.approx(s.run_e.point, abs=1e-4), s.period
        decided = {d["period"] for d in s.expected.get("dividend_decisions") or []}
        seen_decision |= bool(decided) and decided <= {h["period"] for h in files["dividends"]["history"]}
        seen_year |= bool(s.cand.derived["year_shift"])
        if s.cand.derived["year_shift"]:
            assert files["balance"]["prev_year_end"]["as_of"] == prev["anchor"]["as_of"]
            assert files["bridge_mgmt_ifrs"]["nim"]["window"] == [s.period, s.period]
        book, facts, prev = s.cand.book, s.cand.facts, files
    assert seen_decision and seen_year, "цепочка прошла смену года якоря и решение собрания"
