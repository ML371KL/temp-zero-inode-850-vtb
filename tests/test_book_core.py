# -*- coding: utf-8 -*-
"""Книга против ядра: суждения книги ВТБ, которые проверяются только прогоном ядра (поток book; MODEL §3.2, §4.5, §12).

* Модальная клетка книги — мир H × «нормализация» × «средняя группа»: на ней выводятся ближний сдвиг и прочие доходы
  ближнего года (метка `tact`, без ядра: свойство вероятностей книги).
* Числа, выведенные на ядре, делают то, что говорит их правило, и ядро печатает запись вывода
  (`data/assumptions/evidence/path/out/derive_out.json`): ключ цели ЧПМ — стационарная маржа мира уровня на составе
  баланса якоря, уровень мира-опоры — число записи; ближний путь маржи модальной клетки — путь записи (квартал
  с месячными фактами — маржа фактов); ступень σ0 на границе 2026К4 → 2027К1 снята (решение ведущего № 5, п. 3.5).
  Если тесты КРАСНЫЕ на готовом ядре — `python -B ops/tools/rederive.py --dry-run` (лист вывода на ядре).
* Цепочка отчётов «без новостей» не вымывает хвостовые режимы ниже пола (приёмочный тест решения ведущего № 2, §8 п. 4).
Тест писался под книгу образца (Т-Технологии 1.0); утверждения только об образце (отток средств клиентов в своём
квартале, стоимость инструментов капитала в «прочем», рост услуг года якоря от факта, доля инструментов капитала в RWA
якоря, корни расходов под цель C/I) сняты: у книги ВТБ этих правил нет — корни расходов выводятся под цель расходов к
активам, гейт `cir_lt` — сторож рукой, инструменты капитала — плато в рублях до 2028К4 и доля RWA своей клетки
(`tests/test_book_template.py`, `tests/test_control_t2_share.py`). Пока ядро не исполняет ветви второй формы банка
(схема называет их словом «не реализовано»), тесты с прогоном пропускаются с названной причиной. Книга и факты — те,
что читает ядро (`data/assumptions/assumptions.yaml`, `data/facts/`).
"""
from __future__ import annotations

import json

import pytest

try:
    from tests import support_book as S
except ImportError:                      # прогон без pytest.ini (pythonpath = .) и без tests/__init__.py
    import support_book as S

RECORD = S.EVIDENCE / "path" / "out" / "derive_out.json"      # запись вывода на ядре
PATH_TOL = 1e-5                          # точность записи пути маржи (5 знаков доли)


def record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def book() -> dict:
    return S.built_book()


@pytest.fixture(scope="module")
def modal(book):
    """(контекст прогона, модальная клетка) ядра на книге и фактах дерева; пропуск, пока ядро не готово."""
    from model import book_schema

    pending = getattr(book_schema, "pending", None)
    left = pending(book) if pending else []
    if left:
        pytest.skip(f"ядро ещё не исполняет ветви книги второй формы банка ({len(left)}): {left[0]}")
    from model.book import load_book, load_facts
    from model.cell import run_cell
    from model.grid import make_context, modal_cell

    facts = load_facts()
    core_book = load_book(facts=facts)
    ctx = make_context(core_book, facts)
    return ctx, run_cell(ctx, *modal_cell(core_book, ctx.posterior))


@pytest.mark.tact
def test_the_modal_cell_of_the_book(book):
    """Модальная клетка (INTERFACES §4.6): мир с наибольшим весом слоя «свой взгляд», режим с наибольшей вероятностью,
    сценарий капитала с наибольшей вероятностью при этом режиме — без равенств, от порядка книги не зависит."""
    j = book["joint"]
    world = max(j["world_prob"], key=j["world_prob"].get)
    regime = max(j["regime_prob"], key=j["regime_prob"].get)
    scenario = max(j["reg_prob_given_regime"][regime], key=j["reg_prob_given_regime"][regime].get)
    assert (world, regime, scenario) == ("H", "norm", "mid")
    for table in (j["world_prob"], j["regime_prob"], j["reg_prob_given_regime"][regime]):
        top = sorted(table.values())[-2:]
        assert top[1] > top[0]
    assert world == book["nii"]["transmission"]["reference_world"]            # мир отсчёта спредов — тот же


def test_the_key_of_the_margin_is_the_stationary_margin_of_the_window_world(modal, book):
    """Ключ цели ЧПМ — само суждение: стационарная маржа мира уровня на составе баланса якоря равна ключу, гейта
    стационарной маржи у книги нет; уровень мира-опоры передачи решатель находит сам — то число, что печатает запись
    вывода на ядре; маржа, которую печатает модальная клетка после фазы роста, — результат: кредит вытесняет ликвидные
    активы, и она выше суждения."""
    from model.grid import year_mgmt
    from model.levels import level_nim, stationary_nim

    ctx, cell = modal
    key = book["nii"]["nim_lt_target_mgmt"]
    node = level_nim(ctx)
    assert stationary_nim(ctx) is None and "nim_stationary" not in book["checks"]
    assert node["world"] == book["nii"]["transmission"]["level_world"] and node["value"] == pytest.approx(key, abs=1e-9), node
    assert node["reference_world"] == book["nii"]["transmission"]["reference_world"] != node["world"]
    level = record()["level"]
    assert level["key"] == key and level["world"] == node["world"]
    assert node["reference_value"] == pytest.approx(level["stationary_by_world"][node["reference_world"]], abs=1e-6)
    values = [year_mgmt(ctx, "nim", y, cell.annual["nim"][i], lambda name, q: cell.quarters[name][q])
              for i, y in enumerate(cell.years) if y >= book["checks"]["window_backtest"]["from_year"]]
    assert sum(values) / len(values) > key


def test_the_near_path_of_the_anchor_year_is_the_path_of_the_record(modal):
    """Ближний путь маржи (решение ведущего № 5, п. 3.5): упр. ЧПМ модальной клетки в кварталах ближнего сдвига — путь
    записи вывода на ядре (клетка записи — модальная); в квартале с месячными фактами — маржа фактов (допуск — точность
    записи)."""
    ctx, cell = modal
    near, tl = record()["near"], ctx.timeline
    assert near["cell"] == "/".join((cell.world, cell.regime, cell.scenario))
    got = {tl.period(q): ctx.bridge.to_mgmt_nim(float(cell.quarters["nim"][q])) for q in range(1, tl.Q + 1)
           if tl.period(q) in near["path"]}
    assert set(got) == set(near["path"])
    assert got == pytest.approx(near["path"], abs=PATH_TOL), {k: round(100 * v, 3) for k, v in got.items()}
    assert got[near["fact_period"]] == pytest.approx(near["fact_nim"], abs=PATH_TOL)


def test_the_near_nim_shift_takes_the_sigma0_step_away(modal):
    """Ступень σ0 на границе 2026К4 → 2027К1 снята (решение ведущего № 5, п. 3.5): ступень маржи модальной клетки —
    та, что печатает запись вывода, и не больше ступени одних книг на ставках мира (приёмка записи)."""
    ctx, cell = modal
    step, tl = record()["near"]["step"], ctx.timeline
    a, b = (ctx.bridge.to_mgmt_nim(float(cell.quarters["nim"][tl.index(p)])) for p in step["quarters"])
    assert b - a == pytest.approx(step["cell"], abs=1e-6) and step["ok"] is True


def test_the_no_news_chain_stops_at_the_floor(modal, book):
    """Приёмочный тест книги (решение ведущего № 2, §8 п. 4): цепочка восьми отчётов «факт = ожидание» не опускает
    вероятность ни одного режима ниже пола — доли `floor_share` базовой вероятности; сумма вероятностей — единица."""
    from model.book import load_book, load_facts
    from model.grid import run_grid
    from model.live import live_from_book
    from model.nextreport import model_expectation, open_period, with_observation

    facts = load_facts()
    b = load_book(facts=facts)
    live = live_from_book(b, facts)
    share, prior = book["joint"]["regime_update"]["floor_share"], book["joint"]["regime_prob"]
    for _ in range(8):
        period = open_period(b, facts)
        e = model_expectation(b, facts, period, live=live, run=run_grid(b, facts, live))
        b = with_observation(b, period, cor=e["cor_q_mgmt"], nim=e["nim_q_mgmt"])
        post = dict(run_grid(b, facts, live).ctx.posterior)
        assert abs(sum(post.values()) - 1) < 1e-9
        assert all(post[r] >= share * prior[r] - 1e-12 for r in prior), post
