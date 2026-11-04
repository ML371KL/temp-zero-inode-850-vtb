# -*- coding: utf-8 -*-
"""Правила книги ВТБ для чисел, зависящих от миров (ops/tools/worlds_rules.py): на записи миров книги каждое правило даёт
шаблон бит в бит; запись листа calib-nii во входе листа вывода (ключи книг, путь бэктеста мира H) — тем же счётом.

ЗАЧЕМ. Команда приёма миров (ops/tools/adopt_worlds.py) пересчитывает только то, что названо в манифесте, и пишет
выход правил в шаблон. Правило, которое на своей записи не воспроизводит шаблон, при следующей версии миров запишет
не то число: красный тест здесь — до приёма, а не после."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "tools"))
import adopt_worlds as A  # noqa: E402
import worlds_rules as R  # noqa: E402

MANIFEST = A.load_manifest(ROOT)
RULES = [s for s in A.walk_steps(MANIFEST["steps"]) if s["kind"] == "rule"]


@pytest.fixture(scope="module")
def ctx():
    state = A.read_state(ROOT)
    return A.RuleContext(tree=ROOT, entry=None, version=state["version"], manifest=MANIFEST)


@pytest.fixture(scope="module")
def book():
    return yaml.safe_load((ROOT / MANIFEST["template"]).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inputs():
    return json.loads((ROOT / R.INPUTS).read_text(encoding="utf-8"))


@pytest.mark.parametrize("step", RULES, ids=[s["id"] for s in RULES])
def test_the_rule_gives_the_template_on_the_record_of_the_book(step, ctx):
    bad, n = [], 0
    for target in A.call_rule(ROOT, step, ctx):
        path = ROOT / target["file"]
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) if target.get("values") else None
        for k, want in (target.get("values") or {}).items():
            n += 1
            have = A.get(doc, A._path(k))
            if not (A.same(have, want) and type(have) is type(want)):
                bad.append((A._dotted(A._path(k)), have, want))
        bad += [("текст", p[0][:80], p[1][:80]) for p in target.get("replace") or [] if p[0] != p[1]]
    assert not bad, bad[:10]
    assert n, step["id"]


def test_the_rules_cover_what_the_inventory_names(ctx, book):
    """Ключи, зависящие от миров (опись книги, раздел 2): все ключи спредов девяти книг (у книг с ключами лет — годы,
    полугодия и LT; у бумаг — кварталы и LT), лаг бумаг, вариант лага окна, веса миров, версия — пишут правила."""
    written = set()
    for step in RULES:
        for target in A.call_rule(ROOT, step, ctx):
            written |= {A._dotted(A._path(k)) for k in (target.get("values") or {})}
    for b, spec in book["nii"]["books"].items():
        assert {f"nii.books.{b}.spread.{k}" for k in spec["spread"] if k != "LT_from"} <= written, b
    j = R.variant_index(book, R.LAG_VARIANT)
    var = book["valuation"]["reference_variants"][j]["overrides"]
    assert {f"valuation.reference_variants.{j}.overrides.nii.books.securities.spread.{k}"
            for k in var["nii.books.securities.spread"] if k != "LT_from"} <= written
    for key in ("nii.books.securities.rho", f"valuation.reference_variants.{j}.overrides.nii.books.securities.rho",
                "joint.world_prob.N", "meta.version"):
        assert key in written, key


def test_the_sheet_record_in_the_derive_inputs_is_the_rule(book, inputs):
    """Запись листа calib-nii во входе листа вывода: ключи и лаги книг = шаблону (их сверяет шаг near_spreads листа
    вывода), путь бэктеста мира H = правилу на записи книги (строка 1(г) листа приёмки судит по нему)."""
    record = json.loads((ROOT / "data/assumptions/worlds_source.json").read_bytes().decode("utf-8"))
    assert R.sheet_record(book, inputs) == inputs["nii_books"]["books"]
    assert R.backtest_nim(ROOT, record, book, inputs) == inputs["backtest_path"]["nim"]


def test_the_lag_rule_and_its_band(book, inputs):
    """Лаг книги бумаг — минимум RMS «форма ядра − бэктест» в мирах N и M на сетке 0,04…1,00; ключи кварталов —
    обращение лага на пути мира H (путь книги в мире H = бэктест до округления ключей); полоса оси — в сетке и
    содержит лаг правила."""
    record = json.loads((ROOT / "data/assumptions/worlds_source.json").read_bytes().decode("utf-8"))
    sec = R.near_keys(ROOT, record, book, inputs)["securities"]
    assert sec["rho"] == book["nii"]["books"]["securities"]["rho"]
    lo, hi = sec["band"]
    assert lo <= sec["rho"] <= hi and lo in R.LAG_GRID and hi in R.LAG_GRID


def test_the_version_rule_bumps_only_a_released_version(ctx, book, monkeypatch):
    """Номер версии: младший разряд + 1, только если книга с этим номером выпущена на другой записи миров; строка 1
    шапки шаблона несёт тот же номер."""
    cur = str(book["meta"]["version"])
    monkeypatch.setattr(R, "released_record", lambda root, v: "0" * 64)
    head, _, minor = cur.rpartition(".")
    out = R.book_version(ctx)[0]
    assert out["values"][("meta", "version")] == f"{head}.{int(minor) + 1}"
    assert out["replace"] and out["replace"][0][1].endswith(f"версия {head}.{int(minor) + 1} (")
    monkeypatch.setattr(R, "released_record", lambda root, v: book["worlds"]["source"]["sha256"])
    assert R.book_version(ctx)[0]["values"][("meta", "version")] == cur
    monkeypatch.setattr(R, "released_record", lambda root, v: None)
    assert R.book_version(ctx)[0]["values"][("meta", "version")] == cur


def test_gate_masses_keep_two_significant_digits():
    assert [R.mass2(x) for x in (0.047939896, 0.020811, 0.2095249, 0.02973, 0.64054, 1.0)] == \
        [0.048, 0.021, 0.21, 0.03, 0.64, 1.0]
