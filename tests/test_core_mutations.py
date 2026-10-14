"""Мутации ядра (М§18): каждую ошибку роняет аналитическая или инвариантная проверка.

Подлинное ядро проходит все проверки набора; каждый мутант (`tests/mutations.py`)
роняет хотя бы одну. Мутанты гоняются подпроцессами параллельно.

Запись исходов. С переменной окружения `BANK_MUTATION_RECORD` (путь файла; её ставит
`ops/tools/ptest.py`) тесты оставляют итог каждой проверки подлинного ядра и каждого
мутанта файлом — его читает `ops/tools/pmut.py`. Запись несёт отпечаток дерева на момент
прогона (ядро, набор мутаций, опоры и фикстуры проверок — функция инструмента). Вердикт
тестов от записи не зависит.
"""

from __future__ import annotations

import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.mutations import MUTATIONS, build_mutant, run_checks_in

RECORD_ENV = "BANK_MUTATION_RECORD"
RECORD_SCHEMA = "mutation-results/1"


def _fingerprint() -> str:
    """Отпечаток дерева в эту минуту — функцией инструмента записи (`ops/tools/pmut.py`)."""
    spec = importlib.util.spec_from_file_location(
        "tool_pmut_fingerprint", Path(__file__).resolve().parents[1] / "ops" / "tools" / "pmut.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.fingerprint()


def _record(key: str, value: dict) -> None:
    """Дописать в файл записи (`BANK_MUTATION_RECORD`) узел `key`; без переменной — ничего. Запись несёт
    отпечаток дерева на момент прогона: узлы, снятые на другом дереве (файл остался от прежнего прогона или
    дерево правили между узлами), не продолжаются — запись начинается заново."""
    path = os.environ.get(RECORD_ENV)
    if not path:
        return
    file = Path(path)
    now = _fingerprint()
    data = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    if data.get("fingerprint") != now:
        data = {"schema": RECORD_SCHEMA, "fingerprint": now}
    data[key] = value
    file.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def test_original_core_passes_all_mutation_checks():
    result = run_checks_in(None)
    _record("original", result)
    bad = {k: v for k, v in result.items() if v != "ok"}
    assert not bad, bad


def test_every_mutation_is_caught(tmp_path):
    def one(m):
        target = build_mutant(m, tmp_path / m.id)
        return m, run_checks_in(target)

    workers = max(1, min(8, (os.cpu_count() or 2) - 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, MUTATIONS))
    _record("mutants", {m.id: res for m, res in results})
    missed = []
    for m, res in results:
        caught = [k for k, v in res.items() if v != "ok" and not k.startswith("_")]
        if not caught:                    # падение подготовки мутанта — не «поймана проверкой»
            missed.append(f"{m.id} «{m.title}»: {res}")
    assert not missed, "не пойманы: " + "; ".join(missed)


@pytest.mark.parametrize("m", MUTATIONS, ids=lambda m: m.id)
def test_mutation_targets_exist(m):
    """Строка-цель каждой мутации есть в коде: иначе мутацию перенацеливают, а не удаляют."""
    root = Path(__file__).resolve().parents[1]
    assert m.find in (root / m.path).read_text(encoding="utf-8"), m.id
