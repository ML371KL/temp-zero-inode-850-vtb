"""Сборщик фактов ВТБ без папки передачи: якорь — из аргумента, состав — таблицами начала файла, функции — общие.

Квартал якоря приходит аргументом `--anchor` (по умолчанию — `data/facts/anchor.json`); дата, каталог листов квартала,
нарастающий итог, суффиксы метрик ручного листа выводятся из него. В теле функций сборщика нет периодов и дат — они
живут в именованных параметрах начала файла (SCHEMA.md §3). Файл отчёта квартала — на закоммиченных фактах; сборка
из листов (папка передачи) — в tests/test_facts_archive.py.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

tact = pytest.mark.tact

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
BUILDER = ROOT / "ops" / "tools" / "build_facts.py"

# Периоды и даты в строках кода: 2026Q2, 2Q2026, 6M2026, FY2025, 2026-06-30, 30.06.2026.
PERIOD_RE = re.compile(r"(?<![\w.])(?:20\d\dQ[1-4]|[1-4]Q20\d\d|\d{1,2}M20\d\d|FY20\d\d|20\d\d-\d\d-\d\d|"
                       r"\d\d\.\d\d\.20\d\d)(?![\w])")
YEAR_RE = re.compile(r"(?<![\w.,/-])20[1-4]\d(?![\w,/-])")


def builder():
    spec = importlib.util.spec_from_file_location("build_facts_under_test", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


B = builder()


def facts() -> dict[str, dict]:
    return {k: json.loads((FACTS / f"{k}.json").read_text(encoding="utf-8")) for k in B.BUILT}


# ------------------------------------------------------------------ якорь и выводимое из него

@tact
def test_anchor_derivations():
    a = B.Anchor("2026Q3")
    assert (a.date, a.open_date, a.prev_year_end, a.next_day) == ("2026-09-30", "2026-06-30", "2025-12-31", "2026-10-01")
    assert (a.ytd, a.ytd_ru, a.year_quarters) == ("9M2026", "9М2026", ["2026Q1", "2026Q2", "2026Q3"])
    assert (a.stage, a.tag_q, a.tag_ytd, a.tag_next_month) == ("stage1/facts-2026Q3", "q3", "9m", "oct")
    q4 = B.Anchor("2026Q4")
    assert (q4.date, q4.ytd, q4.ytd_ru, q4.prev_year_end, q4.tag_next_month, len(q4.year_quarters)) == \
        ("2026-12-31", "FY2026", "12М2026", "2025-12-31", "jan", 4)
    q1 = B.Anchor("2027Q1")
    assert (q1.open_date, q1.ytd, q1.prev_year_end, q1.year_quarters) == ("2026-12-31", "3M2027", "2026-12-31", ["2027Q1"])
    assert B.q_prev("2027Q1") == "2026Q4" and B.q_next("2026Q4") == "2027Q1"
    assert B.q_days("2026Q2") == 91 and B.q_days("2026Q1") == 90 and B.q_days("2026Q3") == 92
    assert B.q_range("2025Q3", "2026Q2") == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert B.ifrs_q("2026Q2") == "2Q2026" and B.q_ru("2026Q2") == "2К2026" and B.ytd_ru("2026Q4") == "12М2026"
    with pytest.raises(B.BuildError):
        B.Anchor("2026-Q2")


@tact
def test_default_anchor_is_the_committed_one():
    assert B.default_anchor() == json.loads((FACTS / "anchor.json").read_text(encoding="utf-8"))["period"]


@tact
def test_builder_has_no_quarter_literals_outside_named_parameters():
    """В теле функций сборщика нет периодов, дат и лет: всё, что привязано к календарю, — именованный параметр начала
    файла или выводится из якоря (строки документации не в счёт)."""
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(fn, clean=False)
        for n in ast.walk(fn):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc:
                m = PERIOD_RE.search(n.value) or YEAR_RE.search(n.value)
                if m:
                    bad.append(f"{fn.name}:{n.lineno}: «{m.group(0)}»")
    assert not bad, "периоды и даты в теле функций: " + "; ".join(bad)


# ------------------------------------------------------------------ таблицы состава

BOOKS = ("corp_loans", "mortgage", "consumer_loans", "securities", "liquidity", "retail_current", "retail_term", "corp_funds",
         "wholesale")


@tact
def test_table_of_books_is_the_contract_set():
    assert tuple(B.BOOKS) == BOOKS
    assert B.books_of("asset") == list(BOOKS[:5]) and B.books_of("liability") == list(BOOKS[5:])
    assert B.books_of(loans=True) == list(BOOKS[:3])
    assert {b: B.BOOKS[b]["segment"] for b in B.books_of(loans=True)} == {"corp_loans": "corporate", "mortgage": "retail",
                                                                          "consumer_loans": "retail"}
    starts = [s for spec in B.BOOKS.values() for s in spec["rows"] + spec.get("moved", ())]
    for b, spec in B.BOOKS.items():
        assert spec["rows"] and spec["cite"] in ("notes", "sup", "b2", "share"), b
    assert len(B.BOOKS["liquidity"]["rows"]) == 4 and len(B.BOOKS["liquidity"]["moved"]) == 3, \
        "ликвидность — доходные размещения (решение B2): деньги, резервы и деньги НПФ — в прочих активах"
    assert len(starts) == len(set(starts)), "строка листа книг стоит в таблице дважды"


@tact
def test_table_of_pnl_and_other_assets():
    assert set(B.PNL_LINES) == {"nii", "fees_net", "llp_debt_fa", "opex"}
    assert set(B.PNL_REPORTED) == {"pbt", "tax", "np_after_tax", "np_resale_subs", "ni"}
    assert [k for k, _ in B.OTHER_ASSETS_FIXED] == ["dta", "goodwill", "associates"], "постоянная часть — решение ведущего № 3"
    assert B.BRIDGE_MEDIAN == ("cir",) and B.RATES_CARRY_FROM == "2026Q3"


@tact
def test_committed_facts_follow_the_tables():
    """Факты собраны теми же таблицами: порядок книг, строки ОПУ, части постоянных прочих активов."""
    f = facts()
    assert tuple(f["balance"]["books"]) == tuple(B.BOOKS) == tuple(f["nii_books"]["books"])
    assert tuple(f["balance"]["other_assets_fixed_parts"]) == tuple(k for k, _ in B.OTHER_ASSETS_FIXED)
    row = f["pnl_quarterly"]["quarters"][f["anchor"]["period"]]
    assert all(k in row for k in B.PNL_LINES) and tuple(row["reported"]) == tuple(B.PNL_REPORTED)
    hist = f["balance"]["history"]
    assert all(tuple(r["books"]) == tuple(B.BOOKS) for r in hist.values()), "остатки книг на концы кварталов истории"
    anchor = hist[f["anchor"]["period"]]["books"]
    assert {b: anchor[b]["v"] for b in BOOKS} == {b: f["balance"]["books"][b]["v"] for b in BOOKS}


# ------------------------------------------------------------------ мелкие правила

@tact
def test_small_helpers():
    assert B.page_words("6") == "с. 6" and B.page_words("13 и 15") == "с. 13 и 15" and B.page_words("22, 84") == "с. 22, 84"
    assert B.page_words("2.P&L!B12") == "2.P&L!B12" and B.page_words("слайд 11") == "слайд 11"
    assert B.ru(6272.1) == "6272,1" and B.ru(-0.5, 2) == "−0,50" and B.ruk(1408.2) == "1 408,2" and B.rud(25314.9) == "25 314.9"
    assert B.d_ru("2026-10-12") == "12.10.2026" and B.shares_words(12927766417) == "12 927 766 417"
    assert B.na("причина") == {"v": None, "calc": "причина"}
    assert B.est(1.0, "оценка", rng=(0.5, 2.0)) == {"v": 1.0, "calc": "оценка", "estimated": True, "range": [0.5, 2.0]}
    assert B.strip_tail("начало; якорь 2026Q3: хвост", "; якорь ") == "начало"
    with pytest.raises(B.BuildError):
        B.node(None, "документ")
    with pytest.raises(B.BuildError):
        B.node(1.0)


@tact
def test_bridge_value_series():
    """Ряд значения моста: тот ряд истории, чьё среднее по окну равно значению; иначе — «× 4», если он есть."""
    rows = [{"period": "2026Q1", "gap": {"v": 0.001}, "gap_x4": {"v": 0.003}},
            {"period": "2026Q2", "gap": {"v": 0.003}, "gap_x4": {"v": 0.005}}]
    block = {"window": ["2026Q1", "2026Q2"], "value": {"v": 0.002}, "history": rows}
    assert B.bridge_series(block) == "gap"
    assert B.bridge_series({**block, "value": {"v": 0.004}}) == "gap_x4"
    assert B.bridge_series({**block, "value": {"v": 0.0025}}) == "gap_x4", "медиана и прочее — прежнее правило"
    assert B.bridge_series({**block, "history": [{"period": "2026Q1", "gap": {"v": 0.001}}]}) == "gap"


# ------------------------------------------------------------------ файл отчёта квартала

@tact
def test_quarter_report_from_the_committed_facts():
    """Файл отчёта квартала для перезаякоривания: форма семейства с отличиями эмитента — годовой календарь
    (год прибыли объявленного дивиденда), слоты нормативов банковской группы и флаг оценки, акции одной категории,
    без поля capital.t2 (слот t2_recognized у ВТБ — не ключ книги)."""
    f = facts()
    r = B.report_from_facts(f, source="тест")
    assert r["schema"] == "quarter-report/1" and r["period"] == f["anchor"]["period"] and r["as_of"] == f["anchor"]["as_of"]
    assert tuple(r["balance"]["books"]) == BOOKS == tuple(r["interest"])
    assert r.get("published", "9") > r["as_of"]
    b = r["balance"]
    assert "dividends_payable_declared" not in b and b["dividends_payable_year"] == f["balance"]["dividends_payable_year"]
    assets = sum(b["books"][x] for x in BOOKS[:5]) - b["allowance"] + b["other_assets"]
    claims = sum(b["books"][x] for x in BOOKS[5:]) + b["other_liabilities"] + b["dividends_payable"] + b["bv_common"] + b["at1"] + b["nci"]
    assert abs(assets - claims) < 0.2 and abs(assets - f["balance"]["total_assets"]["v"]) < 0.2
    assert b["fvoci"] == pytest.approx(f["balance"]["securities"]["fvoci_debt"]["v"] + f["balance"]["securities"]["fvoci_repo"]["v"])
    assert b["other_assets_fixed"] == f["balance"]["other_assets_fixed"]["v"] and b["loans_fvtpl"] == 0.0
    p = r["pnl"]
    assert abs(sum(p[k] for k in ("nii", "llp_debt_fa", "fees_net", "insurance_net", "noncore_net", "opex", "misc_net")) - p["pbt"]) < 2e-6
    assert p.get("estimated") is True, "прибыль квартала — напечатанное значение файла эмитента"
    c = r["capital"]
    assert isinstance(c["n20_pre_dividend"], bool) and isinstance(c["estimated"], bool) and ("estimate" in c) == c["estimated"]
    assert c["n20_0"] == f["capital"]["n20_0"]["value"]["v"] and c["n1_1_bank"] == f["capital"]["n1_1_bank"]["value"]["v"]
    assert c["basel_cet1"] == f["capital"]["basel"]["cet1"]["v"] and "t2" not in c
    assert set(r["shares"]) == {"issued_total", "outstanding_total", "economic_treasury", "issued_ordinary", "outstanding_ordinary"}
    assert set(r["market"]["ofz_curve"]) == {"1", "3", "5", "10"} and r["market"]["key_avg"] == f["nii_books"]["key_avg_anchor_q"]["v"]
    m = f["mgmt_quarterly"]["quarters"][r["period"]]
    assert r["mgmt"] == {x: m[x]["v"] for x in ("nim", "cor", "cir")}
    assert abs(sum(r["interest"][x] for x in BOOKS[:5]) - sum(r["interest"][x] for x in BOOKS[5:]) - r["dia"]
               + f["nii_books"]["other_interest_net_q"]["v"] - p["nii"]) <= 0.15
    opened = B.q_end(B.q_prev(r["period"])).isoformat()
    want = [h["period"] for h in f["dividends"]["history"] if opened < h["decided_date"] <= r["as_of"]]
    assert [d["period"] for d in r["dividend_decisions"]] == want


@tact
def test_quarter_report_refuses_what_does_not_add_up():
    r = B.report_from_facts(facts(), source="тест")
    for change, why in ((lambda x: x["balance"].__setitem__("other_assets", x["balance"]["other_assets"] + 10), "баланс"),
                        (lambda x: x["pnl"].__setitem__("misc_net", x["pnl"]["misc_net"] + 1), "ОПУ"),
                        (lambda x: x["balance"]["books"].pop("mortgage"), "balance.books.mortgage"),
                        (lambda x: x.pop("shares"), "shares"),
                        (lambda x: x["balance"].__setitem__("dividends_payable_declared", [{"period": "2026Q1", "amount": 99.0}]),
                         "объявленные"),
                        (lambda x: (x["balance"].__setitem__("dividends_payable", 5.0), x["balance"].pop("dividends_payable_year"),
                                    x["balance"].__setitem__("other_liabilities", x["balance"]["other_liabilities"] - 5.0)),
                         "года прибыли")):
        bad = copy.deepcopy(r)
        change(bad)
        with pytest.raises(B.BuildError, match=why):
            B.check_report(bad)


@tact
def test_cli_report_from_ready_facts(tmp_path):
    """`--report ФАЙЛ --facts КАТАЛОГ` пишет отчёт квартала без папки передачи; чужой якорь — отказ."""
    out = tmp_path / "report.json"
    env = {k: v for k, v in os.environ.items() if k != "BANK_HANDOFF_DIR"} | {"PYTHONIOENCODING": "utf-8"}
    run = lambda *a: subprocess.run([sys.executable, "-B", str(BUILDER), *a], cwd=ROOT, env=env, capture_output=True,   # noqa: E731
                                    text=True, encoding="utf-8")
    res = run("--report", str(out), "--facts", str(FACTS))
    assert res.returncode == 0, res.stderr[-1500:]
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got == B.report_from_facts(facts(), source=got["source"]) and b"\r\n" not in out.read_bytes()
    res = run("--report", str(out), "--facts", str(FACTS), "--anchor", "2019Q1")
    assert res.returncode == 1 and "ПРОВАЛ" in res.stderr


@tact
def test_cli_without_handoff_dir_refuses(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "BANK_HANDOFF_DIR"}
    res = subprocess.run([sys.executable, "-B", str(BUILDER), "--out", str(tmp_path)], cwd=ROOT, env=env,
                         capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 1 and "BANK_HANDOFF_DIR" in res.stderr and not list(tmp_path.iterdir())


@tact
def test_cli_help_names_the_arguments():
    res = subprocess.run([sys.executable, "-B", str(BUILDER), "--help"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0
    for arg in ("--anchor", "--out", "--check", "--report", "--facts", "--base", "--expected"):
        assert arg in res.stdout, arg


@tact
def test_base_of_a_wrong_quarter_refuses(tmp_path):
    """База — факты прежнего квартала: каталог фактов другого квартала — отказ до чтения листов."""
    for k, body in facts().items():
        (tmp_path / f"{k}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    anchor = json.loads((FACTS / "anchor.json").read_text(encoding="utf-8"))["period"]
    with pytest.raises(B.BuildError, match="нужны факты"):
        B.load_base(B.Anchor(anchor), tmp_path)
    assert B.load_base(B.Anchor(B.q_next(anchor)), tmp_path)["anchor"]["period"] == anchor
