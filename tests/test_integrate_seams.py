"""Стыки потоков на данных репозитория: факты и книга этой копии против настроек слоя индикаторов.

Каждый поток проверяет свою зону на заглушках (индикаторы — на заглушке книги и фактов эмитента, факты и
книга — без слоя индикаторов). Здесь настоящие файлы читаются друг против друга: вид месячного события
в календаре фактов и в расписании сборщиков, пункт гайденса, который настройка нау-каста ищет в фактах,
цели нау-каста в подписях книги, узлы фактов, которые читает слой. Расходятся имена — календарь выпуска
получает два события на месяц, а эталон нау-каста молча пропадает: такое расхождение сборку не роняет,
поэтому его ловит тест. Чисел книги и фактов тест не называет; от «сегодня» не зависит.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from indicators import calendar as cal
from indicators import config, nowcast, nowcast_months, periods, release_watch
from indicators.store import Store

pytestmark = pytest.mark.tact  # быстрые тесты такта

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"


def _facts(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def _sources() -> dict:
    return yaml.safe_load((ROOT / "data" / "indicators" / "sources.yaml").read_text(encoding="utf-8"))


def _book() -> dict:
    return yaml.safe_load((ROOT / "data" / "assumptions" / "assumptions.yaml").read_text(encoding="utf-8"))


def _is_month(covers) -> bool:
    return isinstance(covers, str) and periods.is_month(covers)


def test_the_monthly_event_is_of_one_kind_in_the_facts_and_in_the_schedule():
    """Событие календаря фактов за месяц — того же вида, что ждёт расписание сборщиков, и только за месяц со
    своим релизом; оценочный день лежит в окне расписания (с днями опоздания дозора)."""
    schedule = _sources()["schedule"]
    spec = cal.monthly_spec(schedule)
    assert spec is not None, "месячное событие у этой копии включено"
    late = timedelta(days=int(schedule.get("late_days", 0)))
    monthly = [e for e in _facts("calendar")["events"] if _is_month(e.get("covers"))]
    assert monthly, "календарь фактов называет ближайшие месячные результаты"
    for e in monthly:
        assert e["kind"] == spec["kind"], f"{e['id']}: вид {e['kind']} — расписание ждёт {spec['kind']}"
        assert e["id"] == f"{spec['kind']}-{e['covers']}", e["id"]
        assert cal.has_release(e["covers"], spec), f"{e['id']}: за этот месяц своего релиза нет (skip_months)"
        lo, hi = cal.monthly_window(e["covers"], schedule)
        if e.get("estimated"):
            assert lo <= date.fromisoformat(e["date"]) <= hi + late, f"{e['id']}: оценка дня вне окна расписания {lo}…{hi}"
    covered = [e["covers"] for e in monthly]
    assert len(covered) == len(set(covered)), "одно событие на месяц"


def test_the_calendar_of_the_release_carries_one_monthly_event_per_month(tmp_path):
    """Календарь выпуска на пустом состоянии: у месяца одно событие, и оно — вида расписания; дата события,
    названного фактами, — дата фактов."""
    cfg = _sources()
    schedule, events = cfg["schedule"], _facts("calendar")["events"]
    spec = cal.monthly_spec(schedule)
    store = Store(tmp_path / "state")
    as_of = date.fromisoformat(_facts("calendar")["as_of"])
    by_facts = {e["covers"]: e["date"] for e in events if e.get("kind") == spec["kind"]}
    for today in (as_of, as_of + timedelta(days=45), as_of + timedelta(days=200)):
        got = cal.events(today, store=store, schedule=schedule, facts_events=events)
        monthly = [e for e in got if _is_month(e.get("covers"))]
        kinds = {e["kind"] for e in monthly}
        allowed = {spec["kind"]} | ({"form102"} if release_watch.monthly(cfg).form102 else set())
        assert kinds <= allowed, f"{today}: события за месяц видов {sorted(kinds)}"
        own = [e["covers"] for e in monthly if e["kind"] == spec["kind"]]
        assert len(own) == len(set(own)), f"{today}: два события на месяц — {sorted(m for m in own if own.count(m) > 1)}"
        for e in monthly:
            if e["kind"] == spec["kind"] and e["covers"] in by_facts:
                assert e["date"] == by_facts[e["covers"]], e["id"]
    for month, day in by_facts.items():
        rel = cal.monthly_release(month, store=store, schedule=schedule, facts_events=events)
        assert (rel["date"], rel["src"]) == (day, "facts/calendar.json"), month


def test_the_estimated_reports_of_the_facts_lie_in_the_windows_of_the_schedule():
    """Отчёт МСФО с оценочным днём в календаре фактов лежит в окне расписания (с днями опоздания): два источника
    одной даты не спорят. Объявленный эмитентом день окном не проверяется — он важнее окна."""
    schedule = _sources()["schedule"]
    late = timedelta(days=int(schedule.get("late_days", 0)))
    reports = [e for e in _facts("calendar")["events"] if e.get("kind") == cal.IFRS_KIND]
    assert reports, "календарь фактов называет отчёты МСФО"
    for e in reports:
        lo, hi = cal.ifrs_window(e["covers"], schedule)
        if e.get("estimated"):
            assert lo <= date.fromisoformat(e["date"]) <= hi + late, f"{e['id']}: оценка дня вне окна расписания {lo}…{hi}"


def test_the_guidance_items_of_the_nowcast_are_items_of_the_facts(tmp_path):
    """Пункт гайденса, названный настройкой нау-каста (`nowcast.guidance.<цель>.item`), есть в фактах под тем же
    именем, и эталон «гайденс» читает его число с пустого состояния."""
    cfg = _sources()
    guidance = _facts("guidance")
    store = Store(tmp_path / "state")
    rules = {key: nowcast_months.guidance_rule(key, cfg) for key in (cfg.get("nowcast") or {}).get("guidance") or {}}
    assert rules, "у нау-каста этой копии есть эталон «гайденс»"
    for key, rule in rules.items():
        node = guidance["items"].get(rule["item"])
        assert isinstance(node, dict), f"{key}: пункта {rule['item']} нет в facts/guidance.json (есть {sorted(guidance['items'])})"
        if node.get("kind") == "point" and node.get("v") is not None:
            got = nowcast.guidance_point(store, rule["item"], guidance["year"], "9999-12-31")
            assert got == pytest.approx(float(node["v"])), (key, rule["item"])
    revised = {h["key"] for h in guidance.get("history") or []}
    assert revised <= set(guidance["items"]) | {None}, f"пересмотры без пункта: {sorted(revised - set(guidance['items']))}"


def test_the_targets_of_the_nowcast_are_labelled_by_the_book():
    """Цели нау-каста настроек сборщиков подписаны книгой; базис подписи цели прибыли — базис месячных результатов,
    по которым она оценивается; подпись флага расхождения не называет сверку, которой у копии нет."""
    cfg, book = _sources(), _book()
    labels = book["meta"]["labels"]
    targets = labels["nowcast"]["targets"]
    spec = release_watch.monthly(cfg)
    wanted = set((cfg.get("nowcast") or {}).get("months") or {}) or set(targets)
    assert wanted <= set(targets), f"цели без подписи книги: {sorted(wanted - set(targets))}"
    for key in wanted:
        assert targets[key]["title"] and targets[key]["title_long"] and targets[key]["basis"], key
    if nowcast_months.enabled(cfg):
        assert targets["ni_q"]["basis"] == spec.basis, "цель прибыли оценивается по месяцам своего базиса"
    flag = labels["flags"]["ras_mismatch"]
    if not spec.form102:
        assert "0409102" not in flag, "сверки с формой банка у копии нет — подпись флага её не называет"
    if spec.basis != release_watch.DEFAULT_BASIS:
        assert "РСБУ" not in flag, "месячные результаты — не в базисе РСБУ банка"


def test_the_facts_carry_the_nodes_the_indicators_read():
    """Узлы фактов, которые читает слой индикаторов: число размещённых акций (сверка с рядом биржи), дробления
    и консолидации с коэффициентом, события решения о дивиденде и отчётов — в форме, которую слой разбирает."""
    shares = _facts("shares")
    assert isinstance(shares["issued_ordinary"]["v"], (int, float)) and shares["issued_ordinary"]["v"] > 0
    for action in config.corporate_actions(FACTS):
        if action.get("kind") == "split":
            factor = config.node_value(action.get("factor"))             # число или узел с числом
            assert isinstance(factor, (int, float)) and factor > 0, action.get("date")
            assert date.fromisoformat(str(action["date"])) and date.fromisoformat(str(action.get("first_trade_date") or action["date"]))
    named_splits = [a for a in config.corporate_actions(FACTS) if a.get("kind") == "split"]
    assert len(config.splits(FACTS)) == len(named_splits), "каждое дробление фактов слой читает с коэффициентом и днём"
    events = config.calendar_events(FACTS)
    kinds = set(_sources()["schedule"].get("watch_kinds") or ())
    named = {e["kind"] for e in events}
    assert kinds <= named, f"виды дозора без событий в календаре фактов: {sorted(kinds - named)}"
    for e in events:
        if e["kind"] in kinds:
            assert date.fromisoformat(e["date"]) and "covers" in e, e["id"]
