# -*- coding: utf-8 -*-
"""Доказательные листы книги ВТБ в дереве: надстройка миров `evidence/worlds_bank/` (её сверяют
tests/test_book_worlds.py) и лист вывода на ядре `evidence/path/` (его запись с книгой сверяют
tests/test_book_template.py и tests/test_ops_rederive.py). Здесь — свойства листов, общие для любой книги: ни в одном
файле листов нет ответов брокерского API (файлом, таблицей или выпиской его полей); лист вывода отвечает за ядро, которое
встречает; лист предельной экономики роста считается на книге и фактах дерева и сходится со сверочной строкой ядра.
Метка `tact` — у сверок без запуска полного вывода.

Тест писался под книгу образца (Т-Технологии) с её листами evidence/{regulation, capital, pnl, nii, regimes, market,
governance} — копиями листов калибровки образца с его числами. Листы сняты вместе с тестами их воспроизведения, описи
малых входов и сверки с этапом 1 образца: у книги ВТБ листы калибровки — в папке передачи (stage1/calib-*), в дереве —
лист вывода на ядре. Сняты и тесты записи вывода на ядре в форме образца (её числа ВТБ сверяют
test_book_template.py::test_frozen_numbers_are_the_record_of_the_derivation и
test_ops_rederive.py::test_on_the_book_of_the_tree_the_command_changes_nothing) и листа двух оснований маржи квартала
после якоря (у книги ВТБ такого листа нет)."""
from __future__ import annotations

import json
import re

import pytest

try:
    from tests import support_book as S
except ImportError:                      # прогон без pytest.ini (pythonpath = .) и без tests/__init__.py
    import support_book as S

# Признаки сырого ответа брокерского API (конверт запроса, заголовки, поля): в листах их быть не должно.
# Строки собраны из частей: сам тест — не «сырой ответ» для общего теста гигиены репозитория
T_RAW_MARKERS = ("x-rate" + "limit", "headers_" + "kept", "instrument" + "Id", "dividend" + "Net",
                 "recommendation" + "Date", "target" + "Price", '"na' + 'no"')
T_ANSWER_WORDS = tuple(a + b for a, b in (("dividend", "Net"), ("record", "Date"), ("lastBuy", "Date"), ("payment", "Date"),
                                          ("declared", "Date"), ("Get", "Dividends"), ("Instruments", "Service"),
                                          ("tinvest_", "samples")))
T_TABLE_COLUMN = re.compile(r"^t_[a-z_]+$")
PATH_SHEET = S.EVIDENCE / "path" / "derive_on_engine.py"
MARGINAL_SHEET = S.EVIDENCE / "path" / "marginal_loan.py"           # предельная единица роста (решение № 4, п. 3.7)
AREAS = ("worlds_bank", "path")                                       # листы книги ВТБ в дереве


@pytest.mark.tact
def test_the_evidence_areas_are_the_sheets_of_the_book():
    """В каталоге листов — только листы книги ВТБ: надстройка миров и лист вывода на ядре, у каждого README."""
    areas = sorted(p.name for p in S.EVIDENCE.iterdir() if p.is_dir() and p.name != "__pycache__")
    assert areas == sorted(AREAS)
    assert all((S.EVIDENCE / a / "README.md").is_file() for a in AREAS)


@pytest.mark.tact
def test_evidence_carries_no_broker_api_answers():
    """Во входах, выходах, текстах и коде листов нет ответов брокерского API: ни файла ответа, ни имён его полей и
    методов, ни таблицы с колонками-полями ответа."""
    bad = []
    for p in S.EVIDENCE.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(S.EVIDENCE).as_posix()
        bad += [(rel, w) for w in T_RAW_MARKERS + T_ANSWER_WORDS if w in text]
        if p.suffix == ".csv":
            head = text.splitlines()[0].lstrip("﻿").split(",") if text else []
            bad += [(rel, c) for c in head if T_TABLE_COLUMN.match(c.strip())]
    assert bad == []


@pytest.mark.tact
def test_the_path_sheet_answers_for_the_core_it_meets():
    """Лист вывода на ядре: пока ядро не исполняет ветви книги — код 2 и слова «нужна волна»; на готовом ядре шаги
    моста и уровня маржи печатают ключ книги — суждение, которое лист читает и не меняет."""
    done = S.run_script(PATH_SHEET, "--steps", "bridge,level", "--no-write")
    assert done.returncode in (0, 2), done.stdout + done.stderr
    if done.returncode == 2:
        assert "нужна волна" in done.stdout and "ядр" in done.stdout
        return
    key = re.search(r"nii\.nim_lt_target_mgmt: ([0-9.]+)", done.stdout)
    assert key and float(key.group(1)) == pytest.approx(S.template()["nii"]["nim_lt_target_mgmt"], abs=1e-4), done.stdout


def test_the_marginal_loan_sheet_matches_the_core_difference(tmp_path):
    """Лист предельной экономики роста (решение ведущего № 4, п. 3.7) на книге и фактах дерева: рубль корпоративного
    кредита на предельной единице модели — по миру книги на стационаре; аналитика каждого мира совпадает со сверочной
    строкой — разностью ядра в модальной клетке мира при премии +1 п.п. — до допуска листа (1 п.п.); сводка листа —
    наименьшая и наибольшая отдачи миров, норма решения № 3, раздел 4 — 5…30 %. Записи в дерево лист не пишет."""
    out = tmp_path / "marginal_loan_out.json"
    done = S.run_script(MARGINAL_SHEET, "--out", str(out))
    if done.returncode == 2:
        pytest.skip("ядро ещё не исполняет ветви книги второй формы банка — лист ждёт")
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    got, book = json.loads(out.read_text(encoding="utf-8")), S.template()
    assert got["book"]["version"] == book["meta"]["version"]
    rows = got["marginal"]["corporate_loan"]
    assert set(rows) == set(book["worlds"]["ids"])
    sheet = S.load_module(MARGINAL_SHEET, "evidence_marginal_loan")
    returns = []
    for world, table in rows.items():
        [row] = [r for r in table if r["year"] == "стационар"]
        assert row["world"] == world
        assert abs(row["return_model"] - row["core_difference"]["return"]) <= sheet.MATCH_TOL, world
        assert row["match"] == pytest.approx(row["return_model"] - row["core_difference"]["return"], abs=1e-12)
        returns.append(row["return_model"])
    sanity = got["sanity"]
    assert (sanity["model_min"], sanity["model_max"]) == (min(returns), max(returns))
    assert (sanity["segment_low"], sanity["segment_high"]) == (0.05, 0.30)
