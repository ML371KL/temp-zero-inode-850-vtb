# -*- coding: utf-8 -*-
"""Команда перевывода книги `ops/tools/rederive.py`: точечная запись выведенных чисел в шаблон, остановки и сухой
прогон. Лист вывода здесь не запускается (минуты): на его месте — запись вывода, лежащая в дереве, и её правленые
копии («подменённый расчёт»); быстрые числа (сетка и полоса) эти тесты не считают. Что команда на книге дерева не
меняет ни одного числа, держит запись вывода дерева: описание рядом с листом, шаблон и запись обязаны сходиться.
В рабочую копию тесты не пишут: запуск с записью идёт только на копии книги и фактов во временном каталоге, на самом
дереве — только сухой прогон."""
from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import re
import shutil
import sys
import types
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "data" / "assumptions"
SHEET_DIR = BOOK / "evidence" / "path"
TODAY = dt.date(2031, 2, 3)                      # дата пометки в тестах: в шаблоне её быть не может
BOOK_VERSION = "0.8"                             # книга, на которой проверены решения ведущего (новая версия — пересмотр)
TRACKED = ("assumptions_template.yaml", "assumptions.yaml", "assumptions.json", "evidence/path/out/derive_out.json",
           "evidence/path/out/derive_out.txt", "evidence/path/out/derive_start.json")


def _load():
    spec = importlib.util.spec_from_file_location("tool_rederive", ROOT / "ops" / "tools" / "rederive.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R = _load()


def committed_record() -> dict:
    return json.loads((SHEET_DIR / "out" / "derive_out.json").read_text(encoding="utf-8"))


def substituted(record: dict):
    """Подменённый расчёт: вместо запуска листа — готовая запись (все шаги описания)."""
    def sheet(tree, spec, book, work, *, serial, workers, say, centre_only=False):
        steps = list(spec.PHASES[0]["steps"]) if centre_only else list(spec.STEPS)
        got = {k: v for k, v in copy.deepcopy(record).items() if not centre_only or k not in ("ends", "need")}
        return got, [{"name": "centre" if centre_only else "all", "steps": steps, "seconds": 0.0,
                      "evaluations": record.get("evaluations")}], "печать подменённого расчёта\n"
    return sheet


def snapshot(book_dir: Path) -> dict[str, bytes]:
    return {name: (book_dir / name).read_bytes() for name in TRACKED}


OPEX_AXIS = "valuation.uncertainty.axes[paths.0=opex.real_growth.2027].low"
UNIT = 0.0001                                    # единица последнего записанного знака корней расходов и комиссий


def unit_moved(key: str) -> float:
    """Долгосрочный корень записи вывода дерева, сдвинутый ровно на единицу последнего знака."""
    return round(committed_record()["keys"][key]["LT"] - UNIT, 4)


def moved_record() -> dict:
    """Запись вывода с другими корнями расходов, другой траекторией дополнительного капитала, другим коридором гейта и
    другим концом оси уровня расходов — в коридорах описания."""
    record = committed_record()
    keys = record["keys"]
    for year in ("2027", "2028", "2029", "2030"):
        keys["opex.real_growth"][year] = -0.0125
    keys["opex.real_growth"]["LT"] = unit_moved("opex.real_growth")          # сдвиг в единицу знака: пишется вместе с ключом
    keys["capital.n20.t2"]["2029Q1"] = 350.3
    keys["fees.growth_vs_wages"]["LT"] = unit_moved("fees.growth_vs_wages")  # сдвиг в единицу знака: пишется, как любое отличие
    keys["checks.wholesale_share"] = [0.07, 0.24]         # порог гейта: сверяется с правилом листа, не пишется
    record["ends"]["opex_axis"]["low"] = -0.0111          # конец оси — шаг фазы после центра
    return record


@pytest.fixture()
def tree(tmp_path):
    """Копия книги и фактов дерева: команда пишет в неё, а не в рабочую копию."""
    root = tmp_path / "tree"
    keep = {"path"}                               # лист вывода со своими входами
    shutil.copytree(BOOK, root / "data" / "assumptions", ignore=lambda d, names: (
        {n for n in names if n not in keep and n != "README.md"} if Path(d) == BOOK / "evidence"
        else {n for n in names if n == "__pycache__"}))
    shutil.copytree(ROOT / "data" / "facts", root / "data" / "facts")
    return R.Tree(root=root)


# ------------------------------------------------------------ описание рядом с листом


def test_the_description_names_the_steps_of_the_sheet_and_a_corridor_for_every_number():
    """Описание не знает шагов сверх листа; фазы покрывают все шаги листа; у каждого числа записи вывода дерева есть
    коридор, и оно в нём лежит; запись вывода дерева на шаблоне дерева не меняет ни одного числа."""
    spec = R.load_spec(R.Tree())
    steps = set(spec.STEPS)
    assert {e["step"] for e in spec.WRITES + spec.SAME + spec.RESIDUALS} <= steps
    assert {s for p in spec.PHASES for s in p["steps"]} == steps
    assert [p["name"] for p in spec.PHASES if not p.get("after")] == ["centre"]
    assert all(p["after"] == "centre" and p["take"] for p in spec.PHASES if p.get("after"))
    text = R.read_text(R.Tree().template)
    record = committed_record()
    items, bad, notes = R.check_record(spec, record, yaml.safe_load(text), yaml.compose(text, Loader=yaml.SafeLoader),
                                       sorted(steps))
    assert bad == [] and all(line.startswith("ок") or "сходимость" in line for line in notes), (bad, notes)
    assert len(items) == len(spec.WRITES) and not any(item.rewrite or item.jitter for item in items)
    assert sum(len(item.leaves) for item in items) > 100, "траектории сверяются по каждому числу"
    assert {r["id"] for r in yaml.safe_load(text)["valuation"]["reference_variants"]} >= {
        "funds_premium_need", "fees_level_2026", "opex_q4_whole_series", "closure_growth_stops"}
    new_text, marks = R.patch(text, items, "03.02.2031")
    assert new_text == text and marks == []
    # у каждого ключа с датой вывода в шаблоне — запись описания с пометкой, и наоборот
    dated = len(re.findall(r"ВЫВЕДЕНО НА ЯДРЕ \d\d\.\d\d\.\d{4}", text))
    assert dated == sum(1 for e in spec.WRITES if e.get("mark")) and "ВЫВОДИТСЯ НА ЯДРЕ —" not in text
    assert all(R.has_mark(text, item) for item in items if item.entry.get("mark"))


def test_the_sheet_holds_the_rules_of_the_anchor_year_on_the_facts_of_the_tree():
    """Правила листа, которые считаются по фактам без ядра: квартал с месячными фактами — месяцы × 3 / число месяцев;
    расходы четвёртого квартала — среднее первых трёх × сезонное отношение; общий сдвиг гасится по долям и держит
    «ключ года = среднее кварталов»; премия средств — уровень по форме (уровень по последний год окна роста, затем
    линейный сход к году схода — как у премий роста кредитов); ближние ключи спредов листа равны книге."""
    spec = R.load_spec(R.Tree())
    sheet = spec.sheet
    from model.book import load_facts
    eng = types.SimpleNamespace(facts=load_facts(R.Tree().facts))
    fact = sheet.fact_quarter(eng, sheet.NEAR_FACT_PERIOD)
    months = [m for m in eng.facts.file("mgmt_quarterly")["monthly"] if m["month"] in fact["months"]]
    assert len(months) == 2 and fact["scale"] == 1.5
    assert fact["nii"] == pytest.approx(1.5 * sum(m["nii_m"]["v"] for m in months))
    assert fact["nim"] == pytest.approx(sum(m["nim_m"]["v"] for m in months) / 2)
    goals = sheet.opex_goals(eng)
    pnl = eng.facts.file("pnl_quarterly")["quarters"]
    first = [abs(pnl[f"2026Q{n}"]["opex"]["v"]) for n in (1, 2)]
    assert goals["q3"] == pytest.approx(fact["opex"]) and goals["mean_q1_q3"] == pytest.approx((sum(first) + fact["opex"]) / 3)
    assert goals["q4"] == pytest.approx(goals["mean_q1_q3"] * sheet.OPEX_Q4_RATIO)
    assert sheet.OPEX_Q4_AXIS[0] < sheet.OPEX_Q4_RATIO < sheet.OPEX_Q4_AXIS[1] and sheet.OPEX_Q4_WHOLE_SERIES < sheet.OPEX_Q4_AXIS[0]
    # ближний сдвиг по MODEL §3.2 (решение № 5, п. 3.5): в 1-м квартале года σ0 — d и встречная σ0, далее линейный сход к 2028 году
    sig = {"2027Q1": 0.002, "2027Q2": 0.0021, "2027Q3": 0.0022, "2027Q4": 0.0023}
    traj = sheet.near_traj(-0.001, sig)
    assert traj["2026Q3"] == traj["2026Q4"] == -0.001 and traj["2027Q1"] == pytest.approx(-0.003)
    assert [traj[f"2027Q{n}"] for n in (2, 3, 4)] == pytest.approx([0.75 * (-0.001 - 0.0021), 0.5 * (-0.001 - 0.0022), 0.25 * (-0.001 - 0.0023)])
    assert traj["2027"] == pytest.approx(sum(traj[f"2027Q{n}"] for n in (1, 2, 3, 4)) / 4) and (traj["LT"], traj["LT_from"]) == (0.0, 2028)
    old = sheet.near_traj(-0.001, sig, fade=sheet.NEAR_OLD_FADE)              # прежняя форма (вариант): 0,8d … 0,2d, встречной σ0 нет
    assert old["2027Q1"] == pytest.approx(-0.0008) and old["2027Q4"] == pytest.approx(-0.0002) and set(old) == set(traj)
    have = {"2026Q3": 0.2, "2026Q4": 0.0, "2027": 0.0, "2028": 0.0, "2029": 0.0, "LT": 0.0, "LT_from": 2030}
    assert sheet.premium_traj(have, -0.04) == {"2026Q3": 0.2, "2026Q4": -0.04, "2027": -0.04, "2028": -0.04, "2029": -0.03,
                                                "2030": -0.02, "2031": -0.01, "LT": 0.0, "LT_from": 2032}
    assert sheet.loan_premium_traj({"2027": 0.01, "2028": -0.04}) == {"2027": 0.01, "2028": -0.04, "2029": -0.03, "2030": -0.02,
                                                                    "2031": -0.01, "LT": 0.0, "LT_from": 2032}
    assert sheet.loan_premium_traj({"2027": 0.01, "2028": -0.04}, hold=1.0)["2031"] == -0.04
    # путь вычета сценария по природе слагаемых: сумма в рублях F и растущая часть G; на RWA якоря все слагаемые в п.п. дают
    # прежнюю траекторию книги (0,1 п.п. за квартал, вычет сценария и высвобождение с 2029 года); слагаемого выпуска по 87 ₽ нет
    # (решение № 4, п. 3.1: выпуск — притоком капитала, шаг issue)
    from model.book import load_book
    from model.grid import make_context
    facts = eng.facts
    tl = make_context(load_book(R.Tree().book_yaml, facts=facts), facts).timeline
    rwa0, eta = 24916.3, 0.6065
    f, g = sheet.deduction_fg(tl, eta=eta, rwa0=rwa0, scenario=0.003)
    q26, q28, q29 = tl.index("2026Q4"), tl.index("2028Q4"), tl.index("2029Q1")
    assert f[0] == g[0] == 0.0 and f[tl.index("2026Q3")] == pytest.approx(eta * 0.001 * rwa0) and g[tl.index("2026Q3")] == pytest.approx((1 - eta) * 0.001)
    assert f[q26] == pytest.approx(eta * 0.002 * rwa0) and f[q28] == pytest.approx(eta * 0.010 * rwa0)
    assert f[q29] == pytest.approx(f[q28] - 0.00085 * rwa0) and f[tl.Q] == pytest.approx(f[q28] - 0.0068 * rwa0)
    assert g[q28] == pytest.approx((1 - eta) * 0.010) and g[q29] == pytest.approx((1 - eta) * 0.010 + 0.003) and g[tl.Q] == g[q29]
    flat = [rwa0] * (tl.Q + 1)
    old_form = sheet.deduction_traj(tl, flat, *sheet.deduction_fg(tl, eta=eta, rwa0=rwa0, scenario=0.003, ruble=()))
    assert (old_form["2026Q2"], old_form["2026Q3"]) == (0.0, 0.001) and old_form["2028Q4"] == pytest.approx(0.010, abs=1e-6)
    assert old_form["2029Q1"] == pytest.approx(0.010 + 0.003 - 0.00085, abs=1e-6) and old_form["LT_from"] == 2036
    assert old_form["LT"] == old_form["2036"] == pytest.approx(0.010 + 0.003 - 0.0068, abs=1e-6)
    assert sheet.deduction_traj(tl, flat, f, g) == old_form, "на RWA якоря сумма в рублях и п.п. RWA — одна траектория"
    double = [rwa0] + [2 * rwa0] * tl.Q
    assert sheet.deduction_traj(tl, double, f, g)["2028Q4"] == pytest.approx(f[q28] / (2 * rwa0) + g[q28], abs=1e-6)
    assert "2036Q1" not in old_form and "2035Q4" in old_form and sheet.issue_volume(12927.766417, 0.288962) == 325.0
    # доля слагаемого роста вычетов в рублях: по умолчанию η; варианты состава — 1 (целиком в рублях) и 0 (целиком с RWA)
    f1, g1 = sheet.deduction_fg(tl, eta=eta, rwa0=rwa0, growth_share=1.0)
    f0, g0 = sheet.deduction_fg(tl, eta=eta, rwa0=rwa0, growth_share=0.0)
    assert f1[q28] == pytest.approx(0.010 * rwa0) and g1[q28] == pytest.approx(0.0) and f0[q28] == pytest.approx(0.0) and g0[q28] == pytest.approx(0.010)
    # приток квартала выпуска: доля денег × объём + распределения + возврат купона (решение № 4, п. 3.1)
    assert sheet.issue_inflow(325.0, 0.5, -6.25, 24.6) == 180.85 and sheet.issue_inflow(0.0, 0.5, -6.25, 24.6) == 18.35
    book = yaml.safe_load(R.read_text(R.Tree().template))["nii"]["books"]
    inputs = json.loads((SHEET_DIR / "inputs" / "vtb_r2_inputs.json").read_text(encoding="utf-8"))
    for name, row in inputs["nii_books"]["books"].items():
        assert all(book[name][k] == v for k, v in row.items()), name
    record = committed_record()
    assert record["near_spreads"]["same"] and record["funds"]["levels"]["retail"] == pytest.approx(
        (inputs["funds_premium"]["facts"]["retail"] + record["funds"]["need_level"]) / 2, abs=5e-5)


# ------------------------------------------------------------ точечная запись


def test_the_point_edit_keeps_every_comment_and_changes_only_the_planned_keys():
    """Правка шаблона — только места чисел: строки без выведенного ключа совпадают знак в знак, комментарии целы,
    разобранный шаблон отличается ровно намеченными ключами и ровно на намеченные значения; дата пометки обновлена
    у переписанного ключа и не тронута у остальных."""
    spec, text = R.load_spec(R.Tree()), R.read_text(R.Tree().template)
    record = moved_record()
    items, bad, _ = R.check_record(spec, record, yaml.safe_load(text), yaml.compose(text, Loader=yaml.SafeLoader),
                                   list(spec.STEPS))
    assert bad == []
    new_text, marks = R.patch(text, items, TODAY.strftime("%d.%m.%Y"))
    old, new = yaml.safe_load(text), yaml.safe_load(new_text)
    want = copy.deepcopy(old)
    want["opex"]["real_growth"].update({"2027": -0.0125, "2028": -0.0125, "2029": -0.0125, "2030": -0.0125,
                                        "LT": unit_moved("opex.real_growth")})
    want["capital"]["n20"]["t2"]["2029Q1"] = 350.3
    want["fees"]["growth_vs_wages"]["LT"] = unit_moved("fees.growth_vs_wages")   # единица последнего знака: число пишется, а не пропускается
    axis = next(ax for ax in want["valuation"]["uncertainty"]["axes"] if ax["paths"][0] == "opex.real_growth.2027")
    axis["low"] = -0.0111
    assert new == want and old["fees"]["growth_vs_wages"]["LT"] == round(unit_moved("fees.growth_vs_wages") + UNIT, 4)
    assert new["checks"]["wholesale_share"] == old["checks"]["wholesale_share"], "коридор гейта сверяется, но не пишется"
    assert [(item.where, item.new) for item in items if item.gap] == [("checks.wholesale_share", [0.07, 0.24])]
    before, after = text.splitlines(), new_text.splitlines()
    assert len(before) == len(after)
    touched = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    heads = sorted(before[i].split("#")[0].strip().split(":")[0] or "#" for i in touched)
    assert heads == ["#", "#", "#", "- {name", "growth_vs_wages", "real_growth", "t2"], heads   # четыре ключа и три строки
    comment = lambda line: line[line.index("#"):] if "#" in line else ""  # noqa: E731                      с пометкой
    dated = [i for i in touched if "НА ЯДРЕ" in before[i]]                # строка коридора гейта не тронута вовсе
    assert len(dated) == 3 and all("ВЫВЕДЕНО НА ЯДРЕ 03.02.2031" in after[i] for i in dated) and len(marks) == 3
    assert all(comment(before[i]) == comment(after[i]) for i in touched if i not in dated), "комментарии целы"
    assert new_text.count("ВЫВЕДЕНО НА ЯДРЕ 03.02.2031") == 3
    assert new_text.count("#") == text.count("#") and len(new_text) - len(text) < 40
    assert not any(item.jitter for item in items), "поодиночке числа не пропускаются: шаблон после записи равен записи вывода"
    assert R.record_gaps(spec, record, yaml.compose(new_text, Loader=yaml.SafeLoader), list(spec.STEPS)) == []


def test_numbers_are_written_the_way_the_template_writes_them():
    assert [R.number_text(v) for v in (1.0, 0.7, -0.0064, -0.009995, 123.182, 2030, -0.0, 0.048160000000000004)] == \
        ["1.0", "0.7", "-0.0064", "-0.009995", "123.182", "2030", "0.0", "0.04816"]
    assert R.flow_text({"2026Q3": -0.0064, "2026": 0.5, "LT": 0.0, "LT_from": 2030, "opex.volume_link": 0.3}) == \
        '{"2026Q3": -0.0064, "2026": 0.5, LT: 0.0, LT_from: 2030, opex.volume_link: 0.3}'
    assert yaml.safe_load(R.flow_text({"2026": 1.5, "no": 2.0})) == {"2026": 1.5, "no": 2.0}, "ключ читается строкой"
    with pytest.raises(R.Stopped):
        R.number_text("0.5")


def test_a_trajectory_with_other_keys_is_rewritten_whole_and_a_wrong_address_is_refused():
    text = ("a:\n  path: {\"2026\": 1.0, LT: 2.0}   # [Р] ВЫВОДИТСЯ НА ЯДРЕ — правило\n  rows:\n"
            "    - {id: x, low: 0.1}   # первый\n    - {id: y, low: 0.2}   # второй\n")
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    entry = {"step": "s", "address": ("a", "path"), "unit": 0.1, "rule": "правило", "mark": True,
             "corridor": [("*", 0.0, 9.0, "проба")]}
    item = R.plan_item(root, entry, {"2026": 1.0, "2027": 1.5, "LT": 2.0})
    assert item.rewrite and item.leaves[0].whole and R.corridor_breaks(item) == []
    row = R.plan_item(root, {"step": "s", "address": ("a", "rows", {"id": "y"}, "low"), "unit": 0.1, "rule": "конец",
                             "corridor": [("", 0.0, 1.0, "проба")]}, 0.3)
    new_text, marks = R.patch(text, [item, row], "03.02.2031")
    assert yaml.safe_load(new_text) == {"a": {"path": {"2026": 1.0, "2027": 1.5, "LT": 2.0},
                                              "rows": [{"id": "x", "low": 0.1}, {"id": "y", "low": 0.3}]}}
    assert "# [Р] ВЫВЕДЕНО НА ЯДРЕ 03.02.2031 — правило" in new_text and "# первый" in new_text and "# второй" in new_text
    assert len(marks) == 1
    for address in (("a", "nowhere"), ("a", "rows", {"id": "z"}, "low"), ("a", "rows", 7), ("a", "path", {"id": "x"})):
        with pytest.raises(R.Stopped):
            R.locate(root, address)
    with pytest.raises(R.Stopped, match="нет коридора"):
        R.corridor_breaks(R.plan_item(root, {**entry, "corridor": [("LT", 0.0, 9.0, "только LT")]}, {"2026": 1.0, "LT": 2.0}))


# ------------------------------------------------------------ остановки на подменённом расчёте


@pytest.mark.parametrize("spoil,words", [
    (lambda r: r["convergence"].update(converged=False), "сходимость связанных шагов"),
    (lambda r: r["keys"]["opex.real_growth"].update({"2027": 0.5}), "вне коридора"),
    (lambda r: r["keys"]["capital.n20.t2"].update({"2030Q1": 5000.0}), "вне коридора"),
    (lambda r: r["frozen_check"].update(opex_goal_year_1=0.0162), "расходы к средним активам слоя, первый год цели"),
    (lambda r: r["frozen_check"].update(t2_share_error=0.01), "доля дополнительного капитала"),
    (lambda r: r["frozen_check"].update(near_nii_ratio=1.05), "к ЧПД месячных фактов"),
    (lambda r: r["anchor"].update(n20_model=0.105), "Н20.0 якоря равен капиталу группы"),
    (lambda r: r["bridge"].update(nim=-0.0014), "мост маржи"),
    (lambda r: r["near_spreads"].update(same=False), "ближние ключи спредов книг"),
    (lambda r: r["splits"].update(floor_ok=False), "полы спреда кредитных книг"),
    (lambda r: r["transmission"].update(nim_axis=[0.03, 0.032]), "суждение записано в двух местах"),
    (lambda r: r["splits"].update(phi_split=0.9), "вне своей оси"),
    (lambda r: r["funds"]["levels"].update(retail=-0.09), "вне отрезка «факт — нужда»"),
    (lambda r: r["keys"]["volumes.funds_share_drift.retail"].update({"2027": 0.01}), "вне коридора"),
    (lambda r: r["ends"].pop("opex_axis"), "в записи листа нет узла"),
])
def test_the_command_stops_and_writes_nothing(spoil, words, tree, capsys):
    """Подбор не сошёлся, число вне коридора, невязка правила (уровни расходов, доля дополнительного капитала, ЧПД
    квартала фактов, якорь, мост маржи, ближние ключи спредов, полы спреда), суждение листа разошлось с книгой, центр
    вне своей оси, премия вне отрезка «факт — нужда», в записи нет узла — остановка с названной причиной; ни шаблон, ни
    книга, ни запись вывода не тронуты (запуск — с записью, на копии дерева)."""
    record = committed_record()
    spoil(record)
    before = snapshot(tree.book_dir)
    with pytest.raises(R.Stopped):
        R.run(tree=tree, quick=False, label="stop", sheet=substituted(record), today=TODAY)
    assert snapshot(tree.book_dir) == before
    printed = capsys.readouterr().out
    assert "ОСТАНОВКА — в шаблон не записано ничего" in printed and words in printed, printed[-1500:]
    saved = json.loads((tree.state / "stop.json").read_text(encoding="utf-8"))
    assert saved["exit_code"] == R.STOPPED and any(words in line for line in saved["derive"]["stopped"])


def test_the_command_line_answers_a_stop_with_code_one(tmp_path, monkeypatch, capsys):
    record = committed_record()
    record["convergence"]["converged"] = False
    monkeypatch.setattr(R, "run_sheet", substituted(record))
    assert R.main(["--dry-run", "--no-quick", "--label", "stop", "--dir", str(tmp_path / "runs")]) == R.STOPPED
    assert "ОСТАНОВКА" in capsys.readouterr().err
    assert R.main(["--show", "нет-такой", "--dir", str(tmp_path / "runs")]) == R.BAD_INPUT
    assert R.main(["--dry-run", "--no-quick", "--label", "latest", "--dir", str(tmp_path / "runs")]) == R.BAD_INPUT


# ------------------------------------------------------------ сухой прогон и запись


def test_the_dry_run_writes_nothing_into_the_tree(tmp_path, capsys):
    """Сухой прогон печатает, что изменилось бы, и собирает пробную книгу в каталоге запуска; дерево цело."""
    before = snapshot(BOOK)
    listing = sorted(p.relative_to(BOOK).as_posix() for p in BOOK.rglob("*") if "__pycache__" not in p.parts)
    code, now = R.run(dry_run=True, quick=False, label="dry", state=tmp_path / "runs", sheet=substituted(moved_record()),
                      today=TODAY)
    assert code == R.OK and now["wrote"] == [] and snapshot(BOOK) == before
    assert sorted(p.relative_to(BOOK).as_posix() for p in BOOK.rglob("*") if "__pycache__" not in p.parts) == listing
    printed = capsys.readouterr().out
    was = R.number_text(committed_record()["keys"]["opex.real_growth"]["2027"])
    assert "СУХОЙ ПРОГОН" in printed and f"{was} → -0.0125" in printed and "сухой прогон — файлы дерева не тронуты" in printed
    trial = yaml.safe_load((tmp_path / "runs" / "dry" / "after" / "assumptions.yaml").read_text(encoding="utf-8"))
    assert trial["opex"]["real_growth"]["2027"] == -0.0125 and trial["worlds"]["overlay"]["sha256"]
    saved = json.loads((tmp_path / "runs" / "dry.json").read_text(encoding="utf-8"))
    written = [c for c in saved["derive"]["changes"] if c["written"]]
    assert {c["key"] for c in written} == {"opex.real_growth", "capital.n20.t2", "fees.growth_vs_wages", OPEX_AXIS}
    assert [c["key"] for c in saved["derive"]["changes"] if not c["written"]] == []
    assert [(row["key"], row["sheet"]) for row in saved["derive"]["unwritten"]] == [("checks.wholesale_share", [0.07, 0.24])], (
        "порог гейта: сверен, не переписан, назван")
    assert trial["checks"]["wholesale_share"] == saved["derive"]["unwritten"][0]["book"] and len(saved["flags"]) == 1


def test_the_trial_of_the_centre_writes_nothing_and_leaves_the_axis_ends_alone(tree, capsys):
    """Пробный счёт решения: лист выводит только центр, книга — пробная (новый центр, прежние концы осей), дерево
    не тронуто даже без ключа сухого прогона; записи шагов, которых не было, в план не входят."""
    before = snapshot(tree.book_dir)
    code, now = R.run(tree=tree, centre_only=True, quick=False, label="trial", sheet=substituted(moved_record()), today=TODAY)
    assert code == R.OK and now["wrote"] == [] and now["mode"]["dry_run"] and snapshot(tree.book_dir) == before
    assert {c["key"] for c in now["derive"]["changes"] if c["written"]} == {"opex.real_growth", "capital.n20.t2", "fees.growth_vs_wages"}
    assert [row["key"] for row in now["derive"]["unwritten"]] == ["checks.wholesale_share"]
    assert "ends" not in now["derive"]["steps"] and "corridors" in now["derive"]["steps"]
    trial = yaml.safe_load((tree.state / "trial" / "after" / "assumptions.yaml").read_text(encoding="utf-8"))
    axis = next(ax for ax in trial["valuation"]["uncertainty"]["axes"] if ax["paths"][0] == "opex.real_growth.2027")
    assert trial["opex"]["real_growth"]["2027"] == -0.0125 and axis["low"] == committed_record()["ends"]["opex_axis"]["low"]
    assert "ПРОБНЫЙ СЧЁТ ЦЕНТРА" in capsys.readouterr().out
    for clash in ({"serial": True}, {"derive": False}):
        with pytest.raises(R.Refused):
            R.run(tree=tree, centre_only=True, quick=False, label="clash", sheet=substituted(moved_record()), **clash)


def test_on_the_book_of_the_tree_the_command_changes_nothing(tree, tmp_path, capsys):
    """Запись вывода дерева на шаблоне дерева: «изменений нет» — в сухом прогоне на самом дереве и при записи на
    его копии."""
    before, copied = snapshot(BOOK), snapshot(tree.book_dir)
    assert before == copied
    for where, dry in ((R.Tree(), True), (tree, False)):
        code, now = R.run(tree=where, dry_run=dry, quick=False, label=f"same-{dry}", state=tmp_path / "runs",
                          sheet=substituted(committed_record()), today=TODAY)
        assert code == R.OK and now["wrote"] == [] and now["derive"]["changes"] == []
        assert now["book"]["template_sha256"] == now["book"]["template_sha256_before"]
    assert snapshot(BOOK) == before and snapshot(tree.book_dir) == copied
    assert capsys.readouterr().out.count("изменений нет — все выведенные числа шаблона равны записи вывода") == 2


def test_the_write_rebuilds_the_book_and_the_record_and_the_second_run_changes_nothing(tree, tmp_path, capsys):
    """Запись: шаблон, машинная книга (схема пройдена) и запись вывода рядом с листом — одним запуском; повторный
    запуск с той же записью листа не меняет ничего; без подбора команда только пересобирает устаревшую книгу."""
    record = moved_record()
    before = snapshot(tree.book_dir)
    code, now = R.run(tree=tree, quick=False, label="write", sheet=substituted(record), today=TODAY)
    assert code == R.OK and set(now["wrote"]) == {"assumptions_template.yaml", "assumptions.yaml", "assumptions.json",
                                                   "evidence/path/out/derive_out.json", "evidence/path/out/derive_out.txt",
                                                   "evidence/path/out/derive_start.json"}
    after = snapshot(tree.book_dir)
    same = {name for name in TRACKED if after[name] == before[name]}
    assert same <= {"evidence/path/out/derive_start.json"}, (
        "старт вывода не меняется, только если запись дерева уже стоит на числах книги (последний запуск — «изменений нет»)")
    book = yaml.safe_load(after["assumptions.yaml"].decode("utf-8"))
    assert book["opex"]["real_growth"]["2030"] == -0.0125 and book["capital"]["n20"]["t2"]["2029Q1"] == 350.3
    assert json.loads(after["assumptions.json"].decode("utf-8")) == book
    assert json.loads(after["evidence/path/out/derive_out.json"].decode("utf-8")) == record
    start = json.loads(after["evidence/path/out/derive_start.json"].decode("utf-8"))
    assert start["keys"] == start["before"], "старт — числа до вывода"
    assert start["keys"]["opex.real_growth"]["2030"] == committed_record()["keys"]["opex.real_growth"]["2030"]
    assert set(start["keys"]) == set(record["keys"])
    assert b"\r" not in after["assumptions_template.yaml"] and not list(tree.book_dir.glob("*.rederive-tmp"))
    assert "ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ" in capsys.readouterr().out
    code, again = R.run(tree=tree, quick=False, label="again", sheet=substituted(record), today=TODAY)
    assert code == R.OK and again["wrote"] == [] and snapshot(tree.book_dir) == after
    assert again["derive"]["changes"] == [], "после записи шаблон равен записи вывода: повторный запуск отличий не находит"
    # шаблон поправили руками мимо сборки: без подбора команда пересобирает книгу и больше ничего не трогает
    text = R.read_text(tree.template).replace("erp: 0.0557", "erp: 0.0561")
    R.write_text(tree.template, text)
    code, plain = R.run(tree=tree, derive=False, quick=False, label="plain", today=TODAY)
    assert code == R.OK and plain["wrote"] == ["assumptions.yaml", "assumptions.json"] and plain["derive"] is None
    assert yaml.safe_load(tree.book_yaml.read_text(encoding="utf-8"))["valuation"]["erp"] == 0.0561
    assert R.read_text(tree.template) == text


def test_the_ratio_of_other_assets_to_loans_is_a_number_the_command_writes(tree):
    """Отношение растущих прочих активов к кредитам стоит в книге числом (его ведёт ось доли вычета якоря), и это число
    выводит лист и пишет команда, а не рука: число шаблона, поправленное руками, команда возвращает к записи вывода."""
    spec = R.load_spec(tree)
    entry = [e for e in spec.WRITES if tuple(e["address"]) == ("volumes", "other_assets_to_loans")]
    assert len(entry) == 1 and entry[0]["step"] == "anchor" and entry[0].get("mark")
    record = committed_record()
    want = record["keys"]["volumes.other_assets_to_loans"]
    anchor = record["anchor"]
    assert want == pytest.approx(anchor["other_growing"] / anchor["loans"], abs=5e-7) and anchor["other_growing"] == pytest.approx(
        anchor["other_assets"] - anchor["other_fixed"])
    text = R.read_text(tree.template)
    assert yaml.safe_load(text)["volumes"]["other_assets_to_loans"] == want and text.count(f"other_assets_to_loans: {R.number_text(want)}") == 1
    R.write_text(tree.template, text.replace(f"other_assets_to_loans: {R.number_text(want)}", "other_assets_to_loans: 0.2"))
    code, now = R.run(tree=tree, quick=False, label="ratio", sheet=substituted(record), today=TODAY)
    assert code == R.OK and "assumptions_template.yaml" in now["wrote"]
    assert [(c["key"], c["old"], c["new"]) for c in now["derive"]["changes"]] == [("volumes.other_assets_to_loans", 0.2, want)]
    assert yaml.safe_load(R.read_text(tree.template))["volumes"]["other_assets_to_loans"] == want


def test_the_keys_of_the_third_pass_stand_in_the_book_and_the_fourth_scenario_is_led_wherever_scenarios_are():
    """Книга 0.3 на ядре третьего прохода (решения ведущего № 3, разделы 2, 5.5 и 6): доли вычета якоря — одно число узла
    фактов, пишет его команда; ось доли — связка обеих сторон суждения с концами по счёту листа; решение о взносе — 4-й
    квартал, окно 1; сценарий «послабление» — четвёртый сценарий книги, и каждая ось и каждый справочный вариант, которые
    ведут ключи сценариев, ведут и его; концы связок выпуска по известной цене равны вариантам на тех же ключах; второе
    чтение высвобождения к концу года даёт то же число."""
    spec = R.load_spec(R.Tree())
    sheet = spec.sheet
    book = yaml.safe_load(R.read_text(R.Tree().template))
    record = committed_record()
    from model.book import load_book, load_facts
    from model.grid import make_context
    facts = load_facts(R.Tree().facts)
    # (а) доли вычета якоря: узел фактов, одно число на оба норматива; постоянные прочие активы — числом (путь связки)
    eta = float(facts.need("balance", "fixed_share_of_deductible"))
    cap = book["capital"]
    assert cap["n20"]["deductions_fixed_share"] == cap["n11"]["deductions_fixed_share"] == eta == record["anchor"]["fixed_share"]
    assert all(record["keys"][path] == eta for path in sheet.SHARE_PATHS)
    assert book["volumes"]["other_assets_fixed"] == float(facts.need("balance", "other_assets_fixed")) == record["keys"]["volumes.other_assets_fixed"]
    written = {tuple(e["address"]) for e in spec.WRITES if e["step"] == "anchor" and e.get("mark")}
    assert {tuple(path.split(".")) for path in sheet.SHARE_PATHS} | {("volumes", "other_assets_fixed")} <= written
    axes = book["valuation"]["uncertainty"]["axes"]
    share = next(a for a in axes if a["paths"][0] == sheet.SHARE_PATHS[0])
    six = sheet.SHARE_PATHS + sheet.SHARE_BALANCE_PATHS
    assert share["kind"] == "bundle" and tuple(share["paths"][:len(six)]) == six
    assert all(str(p).startswith(("capital.reg_scenarios.", sheet.FIXED_CHANGE + ".")) for p in share["paths"][len(six):]), \
        "ось η ведёт и ключи вычета (решение № 4, п. 3.3), и путь постоянной части (решение № 5, п. 3.1)"
    for end, level in zip(("low", "high"), sheet.SHARE_AXIS):
        assert share[end] == {**record["anchor"]["share_axis"][end], **record["deductions"]["share_axis"][end]}
        assert all(share[end][path] == level for path in sheet.SHARE_PATHS) and set(share[end]) == set(share["paths"])
        assert share[end]["volumes.other_assets_fixed"] == pytest.approx(
            level * sum(record["anchor"]["fixed_share_pool"].values()) + record["anchor"]["other_fixed"] - record["anchor"]["fixed_share_pool"]["fixed"], abs=0.05)
    assert "Рост растущей с RWA части вычетов" in book["meta"]["labels"]["capital_bridge"]["deductions"]
    # (б) решение о взносе: 4-й квартал, окно 1
    assert (cap["recapitalization"]["decision_quarter"], cap["recapitalization"]["lookahead_quarters"]) == (4, 1)
    # (в) четвёртый сценарий — в центре; где ведутся ключи сценариев, ведётся и он
    ids = cap["reg_scenarios"]["ids"]
    assert ids == ["schedule", "mid", "strict", "relief"] == list(spec._DED_SCENARIOS)
    table = book["joint"]["reg_prob_given_regime"]
    assert all(list(row) == ids and sum(row.values()) == pytest.approx(1.0) for row in table.values())
    assert (table["crisis"]["relief"], table["crisis"]["schedule"]) == (0.7, 0.0) and all(table[r]["relief"] == 0.0 for r in table if r != "crisis")
    # вычет «послабления» после возврата надбавок — смесь трёх сценариев той же долей возврата (решение № 5, п. 3.3); до 2029 года — как «по графику»
    from model.paths import Trajectory as _T
    rel, sch = (_T(cap["reg_scenarios"][s]["deduction_pp"]["n20_0"]) for s in ("relief", "schedule"))
    mix = 0.30 * 0.0 + 0.45 * 0.003 + 0.25 * 0.006
    assert all(rel.value(y, 4) == pytest.approx(sch.value(y, 4), abs=1e-9) for y in (2026, 2027, 2028, 2029))
    assert [rel.value(y, 4) - sch.value(y, 4) for y in (2030, 2031, 2032, 2033, 2036)] == pytest.approx([0.25 * mix, 0.5 * mix, 0.75 * mix, mix, mix], abs=6e-7)
    led = re.compile(r"capital\.reg_scenarios\.(\w+)\.deduction_pp\.")

    def scenarios_of(paths) -> dict:
        count: dict = {}
        for path in paths:
            m = led.match(str(path) + ".")
            if m:
                count[m.group(1)] = count.get(m.group(1), 0) + 1
        return count

    with_scenarios = 0
    for ax in axes:
        count = scenarios_of(ax["paths"])
        if count:
            with_scenarios += 1
            # у «послабления» свои ключи лет возврата вычета (решение № 5, п. 3.3): число путей — по ключам траектории сценария
            want = {s: len(sheet.DED_NORMS) * sum(1 for k in cap["reg_scenarios"][s]["deduction_pp"]["n20_0"] if k not in ("2026Q2", "LT_from"))
                    for s in ids}
            assert set(count) == set(ids) and count == want, ax["name"]
        if any(str(p).startswith("joint.reg_prob_given_regime") for p in ax["paths"]):
            assert list(ax["low"]) == ids == list(ax["high"]), ax["name"]
    assert with_scenarios == 2, "связки роста вычетов и доли вычета якоря (выпуск по 87 ₽ ключей вычета больше не несёт)"
    variants = {v["id"]: v for v in book["valuation"]["reference_variants"]}
    assert "crisis_relief" not in variants and variants["crisis_no_relief"]["overrides"] == {
        "joint.reg_prob_given_regime.crisis": {"schedule": 0.7, "mid": 0.25, "strict": 0.05, "relief": 0.0}}
    for vid, v in variants.items():
        count = scenarios_of(v["overrides"])
        if count:
            assert set(count) == set(ids) and set(count.values()) == {len(sheet.DED_NORMS)}, vid
            assert vid in sheet.DEDUCTION_VARIANTS, f"{vid}: траектории вычета варианта пишет лист"
        for path, value in v["overrides"].items():
            if path == "joint.reg_prob_given_regime":
                assert all(list(row) == ids for row in value.values()), vid
            elif path.startswith("joint.reg_prob_given_regime."):
                assert list(value) == ids, vid
    assert set(sheet.DEDUCTION_VARIANTS) <= set(variants) and "dta_release_by_quarter" in sheet.DEDUCTION_VARIANTS
    assert variants["recap_decision_agm_window_3"]["overrides"] == {"capital.recapitalization.decision_quarter": 2,
                                                                     "capital.recapitalization.lookahead_quarters": 3}
    assert variants["recap_lookahead_2"]["overrides"] == {"capital.recapitalization.lookahead_quarters": 2}
    # (г) выпуск по 87 ₽ одним местом (решение № 4, п. 3.1): связки осей ведут приток (и делитель — ось объёма), концы равны вариантам;
    #     ни один вариант выпуска не несёт ключей вычета
    volume = next(a for a in axes if a["paths"][0] == sheet.VOLUME_AXIS_PATH)
    stay = next(a for a in axes if a["paths"][0] == spec.STAY_AXIS["paths.0"])
    assert volume["kind"] == stay["kind"] == "bundle" and volume["paths"] == [sheet.VOLUME_AXIS_PATH, sheet.ISSUE_FLOW_PATH]
    assert stay["paths"] == [sheet.ISSUE_FLOW_PATH]
    for ax, pairs in ((volume, (("low", "issue_none"), ("high", "issue_max_stay_50"))), (stay, (("low", "issue_325_stay_0"), ("high", "issue_325_stay_100")))):
        for end, vid in pairs:
            over = variants[vid]["overrides"]
            assert not scenarios_of(over), f"{vid}: у выпуска нет ключей вычета"
            for path, value in ax[end].items():
                if path == sheet.VOLUME_AXIS_PATH:
                    assert over[path] == value, (vid, path)
                else:
                    assert over["equity.other_movements"]["2026Q4"] == value, (vid, path)
    # (д) второе чтение высвобождения: к концу года — то же число, внутри года — на доли годового шага меньше
    tl = make_context(load_book(R.Tree().book_yaml, facts=facts), facts).timeline
    rwa0 = 24916.3
    f, g = sheet.deduction_fg(tl, eta=eta, rwa0=rwa0)
    fq, gq = sheet.deduction_fg(tl, eta=eta, rwa0=rwa0, by_quarter=True)
    step = sheet.DTA_RELEASE_PER_YEAR * rwa0
    assert g == gq and all(fq[tl.index(f"{y}Q4")] == pytest.approx(f[tl.index(f"{y}Q4")]) for y in range(2026, 2037))
    assert all(fq[q] == pytest.approx(f[q]) for q in range(tl.index("2028Q4") + 1))
    assert [fq[tl.index(f"2030Q{n}")] - f[tl.index(f"2030Q{n}")] for n in (1, 2, 3)] == pytest.approx([0.75 * step, 0.5 * step, 0.25 * step])


def test_the_decisions_of_round_three_stand_in_book_04():
    """Книга 0.4 (решения ведущего № 4): выпуск по 87 ₽ одним местом — приток центра и вариантов одной формулой, ключи вычета без
    слагаемого выпуска; «послабление» после возврата надбавок — доля возврата × смесь трёх сценариев по годам, прежняя форма —
    вариант; ближний ключ прочих доходов — середина окна C восьми месяцев в клетке условий окна (ключ и концы оси — запись листа,
    варианты уровня несут тот же ключ); варианты решений № 4 на месте, «спред опта +1,5 п.п.» снят; заготовки под ключи пятого
    прохода больше нет — ключи в шаблоне."""
    spec = R.load_spec(R.Tree())
    sheet = spec.sheet
    book = yaml.safe_load(R.read_text(R.Tree().template))
    record = committed_record()
    assert book["meta"]["version"] == BOOK_VERSION
    variants = {v["id"]: v for v in book["valuation"]["reference_variants"]}
    # выпуск: приток центра = 0,5 × 325 − 6,25 + 24,6; варианты с притоком — перечень листа, приток — их формулой
    iss = record["issue"]
    assert book["equity"]["other_movements"]["2026Q4"] == iss["centre"] == 180.85 and iss["volume"] == 325.0
    for vid, cfg in sheet.FLOW_VARIANTS.items():
        assert variants[vid]["overrides"]["equity.other_movements"]["2026Q4"] == iss["variants"][vid]["inflow"], vid
        assert iss["variants"][vid]["stay"] == cfg.get("stay", sheet.ISSUE_STAY)
    carrying = {vid for vid, v in variants.items() if isinstance(v["overrides"].get("equity.other_movements"), dict)}
    assert carrying == set(sheet.FLOW_VARIANTS)
    assert iss["asset_at_price"]["per_share"] == pytest.approx(162.5 * 1000 / iss["divisor"], abs=1e-4)
    q, ded = "2026Q4", record["deductions"]
    sched = book["capital"]["reg_scenarios"]["schedule"]                 # слагаемого выпуска нет: рубли — только доля η роста вычетов
    assert sched["deduction_rub"]["n20_0"][q] == pytest.approx(ded["eta"] * 0.002 * ded["rwa_anchor"], abs=0.006), "слагаемого выпуска нет"
    assert sched["deduction_pp"]["n20_0"][q] == pytest.approx((1 - ded["eta"]) * 0.002, abs=6e-7)
    # «послабление»: доля возврата × смесь по годам
    from model.paths import Trajectory
    cap = book["capital"]["reg_scenarios"]
    w = book["joint"]["reg_prob_given_regime"]["norm"]
    for name, ret in sheet.RELIEF_RETURN.items():
        got = cap["relief"][name]
        for y in range(sheet.RELIEF_FROM, int(ret["LT_from"])):
            mix = sum(float(w[s]) * Trajectory(cap[s][name]).year_value(y) for s in sheet.RELIEF_MIX)
            assert got[str(y)] == pytest.approx(ret[str(y)] * mix, abs=1e-6), (name, y)
        assert got["LT"] == pytest.approx(sum(float(w[s]) * Trajectory(cap[s][name]).year_value(2036) for s in sheet.RELIEF_MIX), abs=1e-6)
        old = variants[sheet.RELIEF_VARIANT]["overrides"][f"capital.reg_scenarios.relief.{name}"]
        assert old["LT"] == pytest.approx(Trajectory(cap["schedule"][name]).year_value(2036), abs=1e-9), name
    assert cap["relief"]["sifi"]["LT"] == pytest.approx(0.01825) and cap["relief"]["ccyb"]["LT"] == pytest.approx(0.0085)
    # прочие доходы: ключ 2027 года — запись листа; сумма клетки на ключе — середина окна C; концы оси — края окна; варианты — тот же ключ
    mi = record["misc"]
    key = book["other"]["misc_net_real"][sheet.MISC_YEAR]
    assert key == mi["key"] and mi["sum_at_key"] == pytest.approx(mi["window"]["mid"], abs=5e-6)
    assert mi["window"]["low"] == pytest.approx(0.0267, abs=5e-4) and mi["window"]["high"] == pytest.approx(0.0312, abs=5e-4)
    first = f"{sheet.MISC_PATH}.{sheet.MISC_YEAR}"                     # ось — связка (решение № 6, п. 2.2): концы ключа 2027 года
    axis = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0] == first)
    assert (axis["low"][first], axis["high"][first]) == (mi["axis"]["low"], mi["axis"]["high"]) and axis["low"][first] < key < axis["high"][first]
    assert all(variants[vid]["overrides"][sheet.MISC_PATH][sheet.MISC_YEAR] == key for vid in sheet.MISC_VARIANTS)
    assert set(record["ends"]["misc_forks"]["forks"]) == set(sheet.MISC_FORKS)
    # варианты решений № 4
    assert "wholesale_spread_high" not in variants and "wholesale_spread_low" in variants
    assert variants["balancing_shares_last4"]["overrides"] == {"volumes.wholesale_to_funds": 0.177, "volumes.securities_share_of_liquid": 0.799}
    pair = variants["fees_opex_level_2026"]["overrides"]
    assert pair == {k: v for k, v in record["ends"]["fees_opex_level_anchor_year"]["overrides"].items()}
    assert {"ded_growth_all_rub", "ded_growth_all_rwa", sheet.RELIEF_VARIANT} <= set(variants)
    # заготовки под ключи пятого прохода больше нет: ключи — в шаблоне (тест ниже)
    assert "core5" not in record["deductions"] and not (SHEET_DIR / "out" / "core5_stub.json").exists()


def test_the_keys_of_the_fifth_pass_stand_in_book_04():
    """Книга 0.4 на ядре пятого прохода (решение ведущего № 4, раздел 4 и пп. 3.2, 3.8; дополнения 5 и 6): рубли пути вычета —
    ключом deduction_rub у всех сценариев (одна траектория), п.п. — растущая часть и вычет сценария; высвобождение ОНА на балансе —
    путь постоянной части прочих активов теми же рублями в каждом квартале (чтение ядра); вес приращения 0; λ_F = 0 с осью 0…1 и
    вариантом λ_F = 1; правило разброса — последовательное; связки осей ведут обе части пути вычета; варианты несут то, что
    называет лист, и книга каждого варианта проходит схему."""
    spec = R.load_spec(R.Tree())
    sheet = spec.sheet
    book = yaml.safe_load(R.read_text(R.Tree().template))
    record = committed_record()
    from model.book import load_book, load_facts
    from model.book_results import variant_book
    from model.grid import make_context
    from model.paths import Trajectory
    facts = load_facts(R.Tree().facts)
    mbook = load_book(R.Tree().book_yaml, facts=facts)
    tl = make_context(mbook, facts).timeline
    ded, cap = record["deductions"], book["capital"]["reg_scenarios"]
    ids = cap["ids"]
    rub = cap[ids[0]]["deduction_rub"]["n20_0"]
    assert all(cap[s]["deduction_rub"][n] == rub == record["keys"][sheet.RUB_ROOT.format(s=s, n=n)] for s in ids for n in sheet.DED_NORMS)
    assert book["volumes"]["other_assets_fixed_change"] == record["keys"][sheet.FIXED_CHANGE] == ded["centre"]["change"]
    assert book["capital"]["rwa"]["density"]["other_assets_fixed_change"] == sheet.FIXED_CHANGE_DENSITY == 0.0
    assert book["valuation"]["terminal"]["fixed_growth_share"] == 0.0 and book["checks"]["grid_variance"] == "sequential"
    # чтение ядра в каждом квартале: рубли = η × рост × RWA якоря + высвобождение; п.п. = (1 − η) × рост + вычет сценария; баланс — те же
    # рубли: доля η роста вычетов (решение № 5, п. 3.1) и высвобождение (решение № 4, п. 3.2); год 2036 — ключом года
    eta, rwa0 = ded["eta"], ded["rwa_anchor"]
    change = Trajectory(book["volumes"]["other_assets_fixed_change"])
    for s in ids:
        e = sheet.ded_series(tl, eta=eta, rwa0=rwa0, scenario=sheet.scenario_of(mbook, tl, s))
        t_rub, t_pp = Trajectory(cap[s]["deduction_rub"]["n1_1"]), Trajectory(cap[s]["deduction_pp"]["n1_1"])
        for q in range(tl.Q + 1):
            y, k = tl.year(q), int(tl.period(q)[-1])
            assert t_rub.value(y, k) == pytest.approx(e["rub"][q], abs=0.006), (s, tl.period(q))
            assert t_pp.value(y, k) == pytest.approx(e["pp"][q], abs=6e-7), (s, tl.period(q))
            assert change.value(y, k) == pytest.approx(e["change"][q], abs=0.006), tl.period(q)
            assert e["change"][q] == pytest.approx(e["asset"][q] + e["release"][q]) and e["asset"][q] == pytest.approx(e["fixed"][q])
            assert t_rub.value(y, k) == pytest.approx(change.value(y, k), abs=0.011), "одна сумма на обе стороны: слагаемые (1) и (4)"
    assert e["release"][tl.index("2029Q1")] == pytest.approx(-0.00085 * rwa0) and e["release"][tl.Q] == pytest.approx(-8 * 0.00085 * rwa0)
    assert e["asset"][tl.index("2028Q4")] == pytest.approx(eta * 0.010 * rwa0)
    assert "2036Q1" not in rub and str(tl.last_year) in rub and change.value(tl.anchor_year, 2) == 0.0
    assert all(v["term1"] <= 0.011 and v["term4"] <= 0.011 for v in ded["both_sides"].values())
    assert ded["both_sides"]["centre"]["design1"] == 0.0 and ded["fixed_sum_ok"] and ded["anchor_zero_ok"]
    # оси: λ_F 0…1 в полосе; связки роста вычетов и доли η ведут обе части пути вычета всех сценариев и путь постоянной части (обе стороны)
    axes = book["valuation"]["uncertainty"]["axes"]
    lam = [a for a in axes if a["paths"] == ["valuation.terminal.fixed_growth_share"]]
    assert len(lam) == 1 and (lam[0]["kind"], lam[0]["low"], lam[0]["high"]) == ("value", 0.0, 1.0)
    for first in (sheet.SHARE_PATHS[0], spec.DED_AXIS["paths.0"]):
        ax = next(a for a in axes if a["paths"][0] == first)
        led = {(p.split(".")[2], p.split(".")[3]) for p in ax["paths"] if p.startswith("capital.reg_scenarios.")}
        assert led == {(s, part) for s in ids for part in ("deduction_pp", "deduction_rub")}, ax["name"]
        fixed = {p.rsplit(".", 1)[1] for p in ax["paths"] if p.startswith(sheet.FIXED_CHANGE + ".")}
        assert fixed == {str(k) for k in book["volumes"]["other_assets_fixed_change"] if k not in ("2026Q2", "LT_from")}, ax["name"]
    # варианты: что несут — перечень листа; книга каждого варианта проходит схему
    variants = {v["id"]: v for v in book["valuation"]["reference_variants"]}
    assert variants["terminal_fixed_share_1"]["overrides"] == {"valuation.terminal.fixed_growth_share": 1.0}
    for vid, cfg in sheet.DEDUCTION_VARIANTS.items():
        over = variants[vid]["overrides"]
        kinds = {"rub" if ".deduction_rub." in p else "pp" if ".deduction_pp." in p else "change" if p == sheet.FIXED_CHANGE else None for p in over}
        assert kinds - {None} == set(cfg["carries"]), vid
        assert all(over[p] == ded["variants"][vid][p] for p in ded["variants"][vid]), vid
    for v in mbook.get("valuation.reference_variants"):
        variant_book(mbook, v)                                   # отказ схемы — исключение
    # траектории листа: самая короткая, которую читатель ядра прочтёт как ряд (интерполяция лет и плоско назад)
    series = [0.0] * (tl.Q + 1)
    for q in range(tl.Q + 1):
        if tl.year(q) >= 2029:
            series[q] = -10.0 * (tl.year(q) - 2028)
    assert sheet.compact_traj(tl, series, 2) == {"2028": 0.0, str(tl.last_year): -80.0, "LT": -80.0, "LT_from": tl.last_year}


def test_the_decisions_of_round_five_stand_in_book_05():
    """Книга 0.5 (решения ведущего № 5, раздел 3): рост вычетов — доля η и на балансе, «регуляторный счёт» — вариант (п. 3.1); вычет
    «послабления» после возврата — смесь долей возврата, прежняя форма — вариант (п. 3.3); реализованная передача — произведение середин,
    концы оси — по квантилям произведения так, как ось разыгрывает движок (п. 3.4); ближний сдвиг маржи снимает ступень σ0 и сходит к
    2028 году, приёмка ступени пройдена, ключ прочих 2027 года — пара, варианты ближнего пути — с ключом парой (п. 3.5)."""
    spec = R.load_spec(R.Tree())
    sheet = spec.sheet
    book = yaml.safe_load(R.read_text(R.Tree().template))
    record = committed_record()
    from model import uncertainty as U
    from model.book import load_book, load_facts
    from model.grid import make_context
    from model.paths import Trajectory
    facts = load_facts(R.Tree().facts)
    mbook = load_book(R.Tree().book_yaml, facts=facts)
    tl = make_context(mbook, facts).timeline
    variants = {v["id"]: v for v in book["valuation"]["reference_variants"]}
    # п. 3.1: путь постоянной части — те же рубли, что рублёвая часть пути вычета; вариант «регуляторный счёт» — только высвобождение
    rub = book["capital"]["reg_scenarios"]["schedule"]["deduction_rub"]["n20_0"]
    change = book["volumes"]["other_assets_fixed_change"]
    assert change == rub and change["2028Q4"] == pytest.approx(0.6065 * 0.010 * 24916.3, abs=0.006)
    assert "ded_growth_asset_eta" not in variants and {"ded_growth_regulatory", "ded_growth_asset_all"} <= set(variants)
    reg = Trajectory(variants["ded_growth_regulatory"]["overrides"][sheet.FIXED_CHANGE])
    e = sheet.ded_series(tl, eta=0.6065, rwa0=24916.3, asset_share=0.0)
    assert all(reg.value(tl.year(q), int(tl.period(q)[-1])) == pytest.approx(e["release"][q], abs=0.006) for q in range(tl.Q))
    # п. 3.3: «послабление» после возврата — вычет смесью; прежняя форма — вычет «по графику»
    old = variants[sheet.RELIEF_VARIANT]["overrides"]
    assert old["capital.reg_scenarios.relief.deduction_pp.n20_0"]["LT"] == book["capital"]["reg_scenarios"]["schedule"]["deduction_pp"]["n20_0"]["LT"]
    assert book["capital"]["reg_scenarios"]["relief"]["deduction_pp"]["n20_0"]["LT"] == pytest.approx(0.003935 + 0.00285, abs=6e-7)
    # п. 3.4: центр −0,0115; концы оси — квантили произведения, как ось разыгрывает движок
    rz = record["realized"]
    assert book["nii"]["transmission"]["target"] == rz["centre"] == -0.0115
    axis = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"] == [sheet.TRANSMISSION_PATH])
    assert (axis["low"], axis["high"]) == (rz["axis"]["low"], rz["axis"]["high"]) and axis["low"] < -0.0115 < axis["high"]
    for q in sheet.TRANSMISSION_QUANTILES:
        engine = U.axis_overrides(mbook, axis, U.tri_s(q))[sheet.TRANSMISSION_PATH]
        assert engine == pytest.approx(sheet.product_quantile(q), abs=5e-6), q
    assert sheet.product_quantile(0.1) == pytest.approx(-0.0265, abs=1e-4) and sheet.product_quantile(0.9) == pytest.approx(0.0007, abs=1e-4)
    rev = next(a for a in book["valuation"]["reverse_dcf"]["axes"] if a["paths"] == [sheet.TRANSMISSION_PATH])
    assert rev["range"] == list(sheet.TRANSMISSION_AXIS) == [-0.068, 0.022]
    assert {variants[v]["overrides"][sheet.TRANSMISSION_PATH] for v in ("transmission_sheet_m023", "transmission_zero_book_share_1",
                                                                         "transmission_low_m068", "transmission_high_p022")} == {-0.023, 0.0, -0.068, 0.022}
    # п. 3.5: ближний сдвиг — d и встречная σ0 в 2027К1, сход к 2028 году; ступень маржи не больше ступени книг; ключ прочих 2027 года — пара
    near, nr = book["regimes"]["near_nim_shift"], record["near"]
    sig = {q: round(v, 5) for q, v in nr["sigma0_part"].items()}
    assert near == sheet.near_traj(round(nr["d"], 5), sig) and near["2027Q1"] == pytest.approx(round(nr["d"], 5) - sig["2027Q1"])
    assert nr["step"]["ok"] and record["frozen_check"]["near_step_excess"] <= sheet.NEAR_STEP_TOL
    assert book["other"]["misc_net_real"][sheet.MISC_YEAR] == record["misc"]["key"] and record["misc"]["label"].startswith("пара к ближнему пути маржи")
    nv = record["ends"]["near_variants"]["variants"]
    for vid in sheet.NEAR_VARIANTS:
        assert variants[vid]["overrides"][f"{sheet.MISC_PATH}.{sheet.MISC_YEAR}"] == nv[vid]["misc_key"], vid
    assert variants["near_sigma0_step_kept"]["overrides"]["regimes.near_nim_shift"] == nv["near_sigma0_step_kept"]["trajectory"]


def test_the_decisions_of_round_six_stand_in_book_06():
    """Книга 0.6 (решения ведущего № 6, раздел 2 и дополнение 4): ключ доли T2 своей клетки с 2029Q1, варианты T2 — с выключенным
    ключом, «рубли модальной клетки» — вариант (п. 2.1); прочие 2028–2029 — прямая к LT от ключа 2027 года минус разность пар, оси
    ключа 2027 года и LT — связки, ведущие прямую (в полосе — прямая от разыгранного ключа минус та же разность к разыгранному LT),
    варианты уровня — тем же правилом (п. 2.2); строка приёмки маржи 2027 года — на режиме «нормализация» (п. 2.3); разрыв миров сторожа
    roe_k_spread — мерой гейта roe_k_homogeneity (п. 2.4). В книге 0.7 разность пар — сумма пар ко ВСЕМ переходным частям пути ЧПД 2027
    года (решение № 7, п. 2.4; отдельный тест ниже), связки и правило полосы — прежние; развилки misc_near_d_pair_off больше нет."""
    spec = R.load_spec(R.Tree())
    sheet = spec.sheet
    book = yaml.safe_load(R.read_text(R.Tree().template))
    record = committed_record()
    from model import uncertainty as U
    from model.book import load_book, load_facts
    from model.checks import check_gates
    from model.grid import run_grid
    facts = load_facts(R.Tree().facts)
    mbook = load_book(R.Tree().book_yaml, facts=facts)
    variants = {v["id"]: v for v in book["valuation"]["reference_variants"]}
    # п. 2.1: ключ ядра; варианты T2 — с выключенным ключом; «рубли модальной клетки» — только выключатель
    assert book["capital"]["n20"]["t2_share"] == {"enabled": True, "from": "2029Q1"}
    for vid in ("t2_flat_rub", "t2_amortizing"):
        assert variants[vid]["overrides"]["capital.n20.t2_share.enabled"] is False, vid
    assert variants["t2_modal_rub"]["overrides"] == {"capital.n20.t2_share.enabled": False}
    # п. 2.2 (с разностью пар решения № 7, п. 2.4): прямая 2028–2029 от ключа 2027 года минус разность пар
    mi, misc = record["misc"], book["other"]["misc_net_real"]
    key, lt, lt_from = misc[sheet.MISC_YEAR], misc["LT"], misc["LT_from"]
    years = sheet.misc_years(lt_from)
    assert years == ("2028", "2029") and list(misc) == ["2026", "2027", "2028", "2029", "LT", "LT_from"]
    assert mi["sigma0_pair"] == pytest.approx(mi["roots"]["mid"] - mi["pair_without_sigma0"], abs=1e-12) and mi["sigma0_pair"] > 0
    line = sheet.misc_line(key - mi["pairs_delta"], lt, lt_from, nd=None)
    assert all(misc[y] == pytest.approx(line[y], abs=sheet.MISC_LINE_TOL) for y in years)
    assert record["frozen_check"]["misc_line_error"] <= sheet.MISC_LINE_TOL
    old = sheet.misc_line(key, lt, lt_from, nd=None)                      # прежнее чтение: прямая от самого ключа — выше
    assert all(misc[y] < old[y] for y in years)
    # оси ключа 2027 года и LT — связки на ключах прямой; приращения — доли прямой; в полосе — прямая от (разыгранный ключ − разность)
    axes = {a["paths"][0]: a for a in book["valuation"]["uncertainty"]["axes"]}
    k27, klt = f"{sheet.MISC_PATH}.{sheet.MISC_YEAR}", sheet.MISC_LT_PATH
    for first in (k27, klt):
        ax = axes[first]
        assert ax["kind"] == "bundle" and ax["paths"] == [first] + [f"{sheet.MISC_PATH}.{y}" for y in years], first
    for end in ("low", "high"):
        for y in years:
            w = sheet.misc_weight(y, lt_from)
            p = f"{sheet.MISC_PATH}.{y}"
            assert axes[k27][end][p] - misc[y] == pytest.approx((axes[k27][end][k27] - key) * (1 - w), abs=0.006), (end, y)
            assert axes[klt][end][p] - misc[y] == pytest.approx((axes[klt][end][klt] - lt) * w, abs=0.006), (end, y)
    band_axes = list(mbook.get("valuation.uncertainty.axes"))
    j27 = next(i for i, a in enumerate(band_axes) if a["paths"][0] == k27)
    jlt = next(i for i, a in enumerate(band_axes) if a["paths"][0] == klt)
    for s27, slt in ((0.7, -0.4), (-0.9, 0.25), (0.3, 1.0)):
        s = [0.0] * len(band_axes)
        s[j27], s[jlt] = s27, slt
        ov = U.draw_overrides(mbook, band_axes, s)
        drawn = {y: ov[f"{sheet.MISC_PATH}.{y}"] for y in years}
        want = sheet.misc_line(ov[k27] - mi["pairs_delta"], ov[klt], lt_from, nd=None)
        assert all(drawn[y] == pytest.approx(want[y], abs=0.06) for y in years), (s27, slt, drawn, want)
    # варианты уровня прочих доходов: тот же ключ, прямая от того же начала к своему LT
    for vid in sheet.MISC_VARIANTS:
        tr = variants[vid]["overrides"][sheet.MISC_PATH]
        want = sheet.misc_line(key - mi["pairs_delta"], tr["LT"], lt_from, nd=None)
        assert tr[sheet.MISC_YEAR] == key and all(tr[y] == pytest.approx(want[y], abs=sheet.MISC_LINE_TOL) for y in years), vid
    assert "misc_near_d_pair_off" not in variants and "misc_d_pair_off" not in record["ends"]
    # п. 2.4: правило листа — мера гейта roe_k_homogeneity
    run = run_grid(mbook, facts)
    gate = next(f for f in check_gates(run) if f.name == "roe_k_homogeneity")
    rk = record["corridors"]["roe_k_spread"]
    assert rk["world_gap"] == pytest.approx(gate.detail["gap"], abs=5e-5)
    assert all(rk["by_world"][w] == pytest.approx(v, abs=5e-5) for w, v in gate.detail["by_world"].items())
    assert book["checks"]["roe_k_spread"]["max_world_gap"] == rk["corridor"]["max_world_gap"] >= rk["world_gap"]
    assert not gate.fired or gate.cells, "сторож по мере гейта: разрыв миров гейт не роняет"
    # п. 2.3: строка приёмки маржи 2027 года — на режиме «нормализация» (окно C устава), смесь заголовка — рядом
    loader = importlib.util.spec_from_file_location("facts_check_r6", SHEET_DIR / "facts_check.py")
    fc = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(fc)
    rows = fc.rows_of(R.Tree().book_yaml, R.Tree().facts)["rows"]
    row = next(r for r in rows if r["name"].startswith(f"1(а) маржа {sheet.MISC_YEAR} года на режиме «нормализация»"))
    assert (row["low"], row["high"]) == fc.NIM_WINDOW == (0.026, 0.032) and row["ok"], row
    assert "смесь заголовка" in row["words"] and "модальная клетка" in row["words"]


def test_the_rule_of_decision_seven_stands_in_book_07():
    """Книга 0.7 (решение ведущего № 7, п. 2.4): пара к переходной части пути ЧПД сходит вместе с ней. Начало прямой прочих 2028–2029 —
    пара к пути центра без всех переходных частей 2027 года: встречная σ0, сдвиг d 2027 года, половина остатка якоря каждой книги с ключом
    года, остаток книги бумаг (тем же счётом, что пишет её ключи: обращение лага), сход спреда опта. Лист печатает пары по частям (сумма —
    разность пар) и ЧПД 2028 года клетки окна в обеих формах (второй порядок); ключ 2027 года — пара к ближнему пути (окно C); варианты
    ближнего пути — тем же правилом; вариант «пары наследуются» — форма книги 0.6; счёт книг повторяет ключи книги."""
    spec = R.load_spec(R.Tree())
    sheet = spec.sheet
    book = yaml.safe_load(R.read_text(R.Tree().template))
    record = committed_record()
    variants = {v["id"]: v for v in book["valuation"]["reference_variants"]}
    assert book["meta"]["version"] == BOOK_VERSION
    mi, misc = record["misc"], book["other"]["misc_net_real"]
    key, lt, lt_from = misc[sheet.MISC_YEAR], misc["LT"], misc["LT_from"]
    years = sheet.misc_years(lt_from)
    # ключ 2027 года — пара к ближнему пути центра: окно C держится
    assert key == mi["key"] and mi["sum_at_key"] == pytest.approx(mi["window"]["mid"], abs=5e-6)
    # пары по частям: порядок снятия, сумма частей — разность пар, пара без частей — пара центра минус разность
    parts = [r["part"] for r in mi["pairs"]]
    books = list(book["nii"]["books"])
    assert parts == ["sigma0", "d"] + [b for b in books if b not in ("securities", "wholesale")] + ["securities", "wholesale"]
    assert sum(r["pair"] for r in mi["pairs"]) == pytest.approx(mi["pairs_delta"], abs=1e-9)
    assert mi["pair_bare"] == pytest.approx(mi["roots"]["mid"] - mi["pairs_delta"], abs=1e-9)
    by = {r["part"]: r for r in mi["pairs"]}
    assert by["sigma0"]["pair"] == mi["sigma0_pair"] > 0 and by["sigma0"]["after"] == mi["pair_without_sigma0"]
    assert by["retail_current"]["pair"] == 0.0 and by["retail_current"]["shift"] == {sheet.MISC_YEAR: 0.0}   # остатка нет — без счёта
    for b in ("d", "corp_loans", "liquidity", "retail_term", "corp_funds", "securities", "wholesale"):
        assert abs(by[b]["pair"]) > 1.0, b                                  # каждая существенная часть несёт свою пару
    # доли остатка книг с ключом года — половина остатка якоря входа (сверка с числом калибровки)
    rule = json.loads((SHEET_DIR / "inputs" / "vtb_r2_inputs.json").read_text(encoding="utf-8"))["nii_books"]["near_rule"]
    for b in ("corp_loans", "mortgage", "consumer_loans", "liquidity", "retail_term", "corp_funds"):
        assert by[b]["shift"][sheet.MISC_YEAR] == pytest.approx(rule["fade"][sheet.MISC_YEAR] * rule["books"][b]["residual"], abs=1e-12), b
    sec = by["securities"]["shift"]                  # бумаги: ключи 2027 года; отголосок обращения лага (лаг окна 0,92) — 2028 год, дальше < 10⁻⁶
    big = {k for k, v in sec.items() if abs(v) >= 1e-6}
    assert big <= {f"{y}Q{q}" for y in (2027, 2028) for q in range(1, 5)} and all(f"2027Q{q}" in big for q in range(1, 5))
    # прямая 2028–2029 — от ключа минус разность пар; на записанных ключах — невязка в точности записи
    line = sheet.misc_line(key - mi["pairs_delta"], lt, lt_from, nd=None)
    assert all(misc[y] == pytest.approx(line[y], abs=sheet.MISC_LINE_TOL) for y in years)
    assert record["frozen_check"]["misc_line_error"] <= sheet.MISC_LINE_TOL
    # сверка: ЧПД 2028 года в обеих формах совпадает до второго порядка; в 2027 году разность — сами переходные части
    nn, nt = mi["nii_next_year"], mi["nii_this_year"]
    assert nn["ok"] and abs(nn["difference"]) <= sheet.MISC_NEXT_TOL and nn["difference"] == pytest.approx(nn["centre"] - nn["bare"], abs=1e-9)
    assert abs(nt["bare"] - nt["centre"]) > 10 * abs(nn["difference"])
    # вариант «пары наследуются» (форма 0.6): минус одна пара к встречной σ0; развилки misc_near_d_pair_off нет
    inh = variants[sheet.MISC_INHERITED]["overrides"]
    assert inh == mi["inherited"]["overrides"] and "misc_near_d_pair_off" not in variants
    want = sheet.misc_line(key - mi["sigma0_pair"], lt, lt_from, nd=None)
    assert all(inh[f"{sheet.MISC_PATH}.{y}"] == pytest.approx(want[y], abs=sheet.MISC_LINE_TOL) for y in years)
    # варианты ближнего пути: ключ — пара к их пути; прямая — от ключа минус их разность пар (пара без их переходных частей); у формы
    # без встречной σ0 и с d года якоря путь без переходных частей тот же, что у центра
    nv = record["ends"]["near_variants"]["variants"]
    for vid in sheet.NEAR_VARIANTS:
        over, v = variants[vid]["overrides"], nv[vid]
        assert over[f"{sheet.MISC_PATH}.{sheet.MISC_YEAR}"] == v["misc_key"] and v["pairs_delta"] == pytest.approx(v["misc_root"] - v["pair_bare"], abs=1e-9)
        want = sheet.misc_line(v["misc_key"] - v["pairs_delta"], lt, lt_from, nd=None)
        assert all(over[f"{sheet.MISC_PATH}.{y}"] == v["misc_line"][y] == pytest.approx(want[y], abs=sheet.MISC_LINE_TOL) for y in years), vid
    assert nv["near_sigma0_step_kept"]["pair_bare"] == pytest.approx(mi["pair_bare"], abs=0.05)
    # счёт листа calib-nii повторяет ближние ключи книги (иначе лист отказывает); без остатка 2027 года меняются только названные ключи
    eng = sheet.Engine(None, None)
    on, off = sheet.near_rule_keys(eng, rule["fade"][sheet.MISC_YEAR]), sheet.near_rule_keys(eng, 0.0)
    spreads = book["nii"]["books"]
    assert all(abs(v - spreads[b]["spread"][k]) <= sheet.NEAR_RULE_TOL for b, keys in on.items() for k, v in keys.items())
    assert all(on[b][k] == off[b][k] for b in on for k in on[b] if not (k == sheet.MISC_YEAR or (b == "securities" and k[:4] >= sheet.MISC_YEAR)))
    eng.inputs["nii_books"]["near_rule"]["books"]["corp_loans"]["residual"] += 0.001       # не тот вход — отказ, а не тихий сдвиг
    with pytest.raises(RuntimeError, match="не воспроизводятся"):
        sheet.misc_parts(eng)


COMPANION = "companion_probe.yaml"
COMPANION_SPEC = '''

# пробный спутник теста: траектория дополнительного капитала — тем же шагом и коридором, что запись шаблона
COMPANIONS = ({"file": "companion_probe.yaml", "title": "пробный спутник теста",
               "writes": ({"step": "t2", "address": ("block", "capital.n20.t2"), "source": ("keys", "capital.n20.t2"), "unit": 0.1,
                           "deadband": DEADBAND_UNITS, "rule": "спутник теста: дополнительный капитал", "corridor": _T2},)},)
'''


def test_the_keys_of_the_eighth_pass_stand_in_book_07():
    """Ключи восьмого прохода (решения ведущего № 7, пп. 2.1–2.3 и № 8, п. 1.2) в книге 0.8: доля AT1 своей клетки по ставке
    ключевой + 4 п.п. (ось 3…5 п.п.) — с первого прогнозного квартала (книга 0.8, решение № 9, п. 1.1: корзина полна сейчас;
    форма книги 0.7 «с 2029Q1» — вариант at1_from_2029), купон бессрочных якоря — фиксированная часть и плавающая по ключевой
    своего мира (книга 0.8, решение № 8, п. 2.2; одно число на все миры — вариант at1_coupon_slot); надбавка за субординацию
    T2 2,5 п.п. (ось 2…3 п.п.), базы — anchor; распределения по указанию акционера за концом сетки — flat_rub; развилки «AT1
    рублями якоря», «без надбавки T2», «распределения кончаются в 2036 году» — варианты с выключенным ключом; ось распределений
    (сдвиг траектории) и варианты распределений двигают и терминал: OM_ann = 4 × LT разыгранной траектории. Ключи — суждения
    шаблона: лист их не выводит, команда не пишет."""
    from model import uncertainty as U
    from model.book import load_book, load_facts
    from model.valuation import terminal_other_movements
    book = yaml.safe_load(R.read_text(R.Tree().template))
    machine = yaml.safe_load(R.read_text(R.Tree().book_yaml))
    assert book["capital"]["at1_share"] == {"enabled": True, "from": book["meta"]["first_period"], "spread": 0.04,
                                            "base": "anchor"}
    assert book["capital"]["at1_coupon"]["enabled"] is True
    assert book["capital"]["n20"]["t2_premium"] == {"enabled": True, "spread": 0.025, "base": "anchor"}
    assert book["valuation"]["terminal"]["other_movements"] == "flat_rub"
    for path in ("capital.at1_share", "capital.at1_coupon", "capital.n20.t2_premium", "valuation.terminal.other_movements"):
        node_t, node_m = book, machine
        for part in path.split("."):
            node_t, node_m = node_t[part], node_m[part]
        assert node_t == node_m, path                                      # машинная книга несёт те же ключи
    axes = {a["paths"][0]: a for a in book["valuation"]["uncertainty"]["axes"]}
    assert {k: axes["capital.at1_share.spread"][k] for k in ("kind", "paths", "low", "high")} == {
        "kind": "value", "paths": ["capital.at1_share.spread"], "low": 0.03, "high": 0.05}
    assert {k: axes["capital.n20.t2_premium.spread"][k] for k in ("kind", "paths", "low", "high")} == {
        "kind": "value", "paths": ["capital.n20.t2_premium.spread"], "low": 0.02, "high": 0.03}
    variants = {v["id"]: v for v in book["valuation"]["reference_variants"]}
    assert variants["at1_anchor_rub"]["overrides"] == {"capital.at1_share.enabled": False}
    assert variants["at1_from_2029"]["overrides"] == {"capital.at1_share.from": "2029Q1"}            # форма книги 0.7
    assert variants["at1_coupon_slot"]["overrides"] == {"capital.at1_coupon.enabled": False}
    assert variants["t2_premium_off"]["overrides"] == {"capital.n20.t2_premium.enabled": False}
    assert variants["om_terminal_none"]["overrides"] == {"valuation.terminal.other_movements": "none"}
    rec = committed_record()
    keys = set(rec["keys"]) | {k.split("[")[0] for k in rec["keys"]}
    assert not any(k.startswith(("capital.at1_share", "capital.n20.t2_premium", "valuation.terminal.other_movements")) for k in keys)
    # оси и варианты распределений двигают и терминал
    facts = load_facts(R.Tree().facts)
    mbook = load_book(R.Tree().book_yaml, facts=facts)
    last = int(str(mbook.get("meta.last_period"))[:4])
    om = axes["equity.other_movements"]
    assert om["kind"] == "shift" and om["paths"] == ["equity.other_movements"]
    lt = float(mbook.get("equity.other_movements")["LT"])
    assert terminal_other_movements(mbook, last) == pytest.approx(4 * lt)
    for s in (-1.0, -0.5, 1.0):
        shifted = U.trial_book(mbook, U.axis_overrides(mbook, om, s))
        want = 4 * (lt + (om["high"] if s > 0 else -om["low"]) * s)
        assert terminal_other_movements(shifted, last) == pytest.approx(want), s
    for vid, want in (("shareholder_distributions_0", 0.0), ("shareholder_distributions_50", -50.0)):
        assert terminal_other_movements(U.trial_book(mbook, variants[vid]["overrides"]), last) == pytest.approx(want), vid
    assert terminal_other_movements(U.trial_book(mbook, variants["om_terminal_none"]["overrides"]), last) == 0.0
    # сторож доли терминала — правило листа (перенесён рукой, слова — о ключах восьмого прохода)
    assert book["checks"]["terminal_share"] == rec["corridors"]["terminal_share"]["corridor"]


def with_companion(tree) -> Path:
    """Пробный файл-спутник в копии дерева: узел с числами записи вывода, комментарии, узел по ссылке YAML; запись о нём —
    в описании вывода копии."""
    path = tree.book_dir / COMPANION
    t2 = committed_record()["keys"]["capital.n20.t2"]
    R.write_text(path, "\n".join(("# спутник теста: шапка", "block: &block", "  capital.n20.t2: " + R.flow_text(t2) + "   # комментарий у ключа",
                                  "# строка между узлами", "overrides:", "  <<: [*block]", "")))
    spec_path = tree.sheet_dir / "derive_spec.py"
    R.write_text(spec_path, R.read_text(spec_path) + COMPANION_SPEC)
    return path


def test_the_companion_of_the_template_is_written_by_the_same_command(tree, tmp_path, capsys):
    """Файл-спутник шаблона (описание, `COMPANIONS`): выведенные числа пишутся в него тем же запуском и тем же точечным
    способом — комментарии целы, меняются ровно намеченные числа (и узел, собранный из спутника ссылкой YAML); сухой
    прогон кладёт спутник в рабочий каталог запуска и дерево не трогает; повторный запуск не меняет ничего; число вне
    коридора останавливает весь запуск. У книги дерева спутников нет (подмены, ждавшие ядра, — в шаблоне): механика
    проверяется на пробном спутнике копии дерева."""
    assert tuple(R.load_spec(R.Tree()).COMPANIONS) == () and not (BOOK / "pass3_overrides.yaml").exists()
    path = with_companion(tree)
    name, text = COMPANION, R.read_text(path)
    record = committed_record()
    t2 = record["keys"]["capital.n20.t2"]
    assert yaml.safe_load(text)["block"]["capital.n20.t2"] == t2, "спутник копии равен записи вывода"
    moved = round(t2["2030Q1"] + 0.3, 1)
    t2["2030Q1"] = moved
    code, now = R.run(tree=tree, dry_run=True, quick=False, label="dry", state=tmp_path / "runs", sheet=substituted(record), today=TODAY)
    assert code == R.OK and now["wrote"] == [] and R.read_text(path) == text
    trial = yaml.safe_load((tmp_path / "runs" / "dry" / "after" / name).read_text(encoding="utf-8"))
    assert trial["block"]["capital.n20.t2"]["2030Q1"] == moved
    assert now["derive"]["companions"] == [{"file": name, "changed": True, "keys": ["block.capital.n20.t2"]}]
    code, now = R.run(tree=tree, quick=False, label="write", sheet=substituted(record), today=TODAY)
    assert code == R.OK and {name, "assumptions_template.yaml"} <= set(now["wrote"]), "то же число стоит и в шаблоне"
    assert yaml.safe_load(R.read_text(tree.template))["capital"]["n20"]["t2"]["2030Q1"] == moved
    after = R.read_text(path)
    old, new = yaml.safe_load(text), yaml.safe_load(after)
    assert new["block"]["capital.n20.t2"]["2030Q1"] == moved
    assert new["overrides"]["capital.n20.t2"]["2030Q1"] == moved, "узел по ссылке YAML — тот же"
    old["block"]["capital.n20.t2"]["2030Q1"] = moved
    old["overrides"]["capital.n20.t2"]["2030Q1"] = moved
    assert new == old and len(after.splitlines()) == len(text.splitlines())
    assert [a for a, b in zip(text.splitlines(), after.splitlines()) if a != b and a.lstrip().startswith("#")] == [], "комментарии целы"
    assert after.count("# комментарий у ключа") == 1 and after.splitlines()[0] == "# спутник теста: шапка"
    assert f"файл-спутник {name}: ключей 1, чисел 1" in capsys.readouterr().out
    code, again = R.run(tree=tree, quick=False, label="again", sheet=substituted(record), today=TODAY)
    assert code == R.OK and again["wrote"] == [] and R.read_text(path) == after
    t2["2031Q2"] = 5000.0
    with pytest.raises(R.Stopped, match="файл-спутник"):
        R.run(tree=tree, quick=False, label="corridor", sheet=substituted(record), today=TODAY)
    assert R.read_text(path) == after
    path.unlink()                                   # спутник назван в описании, а файла нет — остановка
    with pytest.raises(R.Stopped, match="нет файла рядом с шаблоном"):
        R.run(tree=tree, quick=False, label="missing", sheet=substituted(committed_record()), today=TODAY)


def test_a_book_that_fails_the_schema_is_not_written(tree, capsys):
    """Выведенные числа, с которыми книга не проходит схему (ключ года — не среднее кварталов), в дерево не попадают."""
    record = committed_record()
    record["keys"]["regimes.near_nim_shift"]["2027Q1"] = -0.0025
    before = snapshot(tree.book_dir)
    with pytest.raises(R.Stopped, match="не проходит схему"):
        R.run(tree=tree, quick=False, label="schema", sheet=substituted(record), today=TODAY)
    assert snapshot(tree.book_dir) == before


# ------------------------------------------------------------ фазы листа

FAKE_SHEET = '''# -*- coding: utf-8 -*-
import argparse, json, os, sys
from pathlib import Path
ap = argparse.ArgumentParser()
for name in ("--book", "--facts", "--steps", "--out", "--start"):
    ap.add_argument(name)
a = ap.parse_args()
steps = a.steps.split(",")
mode = os.environ.get("FAKE_SHEET_MODE", "")
if mode == "not-ready":
    print("ядро ещё не исполняет ветви книги")
    sys.exit(2)
if mode == "fail" and "ends" in steps:
    print("ОТКАЗ вывода: корня нет")
    sys.exit(1)
out = {"evaluations": {"cells": len(steps), "grids": 10 * len(steps)}}
if a.start:
    out["keys"] = json.loads(Path(a.start).read_text(encoding="utf-8"))["keys"]
    if mode == "drift" and "ends" in steps:
        out["keys"] = {"x": 2.0}
else:
    out.update(keys={"x": 1.0}, splits={"axis_phi": [0.0, 1.0], "phi_split": 0.5}, convergence={"converged": True})
if "ends" in steps:
    out.update(ends={"window": [1, 2]}, splits={"axis_phi": [0.3, 1.0]})
if "need" in steps:
    out["need"] = {"level": 0.05}
print("шаги:", a.steps)
Path(a.out).write_text(json.dumps(out), encoding="utf-8")
'''


@pytest.fixture()
def fake(tmp_path):
    tree = R.Tree(root=tmp_path / "tree")
    tree.sheet_dir.mkdir(parents=True)
    tree.facts.mkdir(parents=True)
    (tree.sheet_dir / "fake_sheet.py").write_text(FAKE_SHEET, encoding="utf-8")
    spec = types.SimpleNamespace(SHEET="fake_sheet.py", STEPS=("centre_a", "centre_b", "ends", "need"), PHASES=(
        {"name": "centre", "title": "центр", "steps": ("centre_a", "centre_b"), "after": None},
        {"name": "ends", "title": "концы", "steps": ("ends",), "after": "centre", "take": (("ends",), ("splits", "axis_phi"))},
        {"name": "need", "title": "проверка", "steps": ("need",), "after": "centre", "take": (("need",),)}))
    work = tmp_path / "work"
    work.mkdir()
    return tree, spec, work


def test_the_phases_of_the_sheet_fold_into_the_record_of_one_run(fake, monkeypatch):
    """Фазы после центра стартуют с его записи; в общую запись идут названные узлы фаз, счёт прогонов складывается;
    один запуск со всеми шагами — одна фаза."""
    tree, spec, work = fake
    said: list[str] = []
    record, phases, printed = R.run_sheet(tree, spec, work / "book.yaml", work, serial=False, workers=2, say=said.append)
    assert record == {"keys": {"x": 1.0}, "splits": {"axis_phi": [0.3, 1.0], "phi_split": 0.5}, "convergence": {"converged": True},
                      "ends": {"window": [1, 2]}, "need": {"level": 0.05}, "evaluations": {"cells": 4, "grids": 40}}
    assert [p["name"] for p in phases] == ["centre", "ends", "need"] and all(p["seconds"] >= 0 for p in phases)
    assert "— фаза ends: концы —" in printed and "шаги: need" in printed
    one, phases, printed = R.run_sheet(tree, spec, work / "book.yaml", work, serial=True, workers=2, say=said.append)
    assert [p["name"] for p in phases] == ["all"] and one["need"] == {"level": 0.05} and "шаги: centre_a,centre_b,ends,need" in printed
    centre, phases, printed = R.run_sheet(tree, spec, work / "book.yaml", work, serial=False, workers=2, say=said.append,
                                          centre_only=True)
    assert [p["name"] for p in phases] == ["centre"] and "ends" not in centre and centre["splits"]["axis_phi"] == [0.0, 1.0]
    assert centre["evaluations"] == {"cells": 2, "grids": 20} and "ends" not in printed


@pytest.mark.parametrize("mode,error,words", [("drift", "Stopped", "её ключи не равны ключам центра"),
                                               ("fail", "Stopped", "корня нет"), ("not-ready", "Refused", "ядро ещё не")])
def test_a_phase_that_recomputes_the_centre_or_fails_stops_the_command(fake, monkeypatch, mode, error, words):
    tree, spec, work = fake
    monkeypatch.setenv("FAKE_SHEET_MODE", mode)
    with pytest.raises(getattr(R, error), match=words):
        R.run_sheet(tree, spec, work / "book.yaml", work, serial=False, workers=2, say=lambda line: None)


# ------------------------------------------------------------ итог и лист решения


def test_the_tables_of_the_book_serve_as_the_first_baseline_and_the_brief_has_the_four_sections(tmp_path):
    """Без прошлого запуска мерка — таблицы книги; блок листа решения несёт разделы 2, 2а, 3 и 4 шаблона семейства;
    сравнение двух запусков печатает разности."""
    tables = R.results_as_run(R.Tree())
    results = json.loads((BOOK / "results.json").read_text(encoding="utf-8"))
    assert tables["quick"]["headline"]["point"] == results["headline"]["point"]
    assert R.baseline(R.Tree(), tmp_path / "нет", None, "x")["label"] == tables["label"]
    # таблицы другой версии книги меркой по умолчанию не служат; названные явно — берутся
    version = tables["quick"]["book_version"]
    assert R.baseline(R.Tree(), tmp_path / "нет", None, "x", version=version)["label"] == tables["label"]
    assert R.baseline(R.Tree(), tmp_path / "нет", None, "x", version=f"не-{version}") is None
    assert R.baseline(R.Tree(), tmp_path / "нет", R.RESULTS, "x", version=f"не-{version}")["label"] == tables["label"]
    now = copy.deepcopy(tables)
    now.update(label="проба", flags=[], derive={"ran": True, "changes": [{"key": "opex.real_growth", "written": True}]},
               marginal={"title": "проба", "anchor": {"model_min": 0.34, "model_max": 0.35, "segment_low": 0.34, "segment_high": 0.36,
                                                      "ok": True},
                         "rows": {"M": [{"year": 2036, "value": 0.02, "segment_basis": 0.14, "hurdle": 0.22}]}})
    now["quick"]["headline"].update(point=320.0, median=305.0, median_error=1.5, point_to_market=0.18, median_to_market=0.12)
    now["quick"]["order"] = {"fair_pb": 1.1, "market_pb": 0.9, "roe_tc": 0.2, "k_tc": 0.19,
                             "years": {"2026": {"roe": 0.27, "eps": 77.0, "pe_point": 4.2, "pe_median": 4.0, "pe_market": 3.5}}}
    text = R.brief(now, tables)
    for head in ("## 2. Заголовок", "## 2а. Пробные счёты этого круга", "## 3. Приёмочные проверки чисел", "## 4. Развилки с ценой"):
        assert head in text, head
    assert "305,00 / 320,00 ₽" in text and "| Уровни в условиях окна фактов |" in text and "| Предельная экономика роста |" in text
    assert text.count("\n| ") > 15 and "opex.real_growth" in text
    rows = {title: (old, new) for title, old, new, _ in R.compare_rows(now, tables)}
    assert rows["точка, ₽"] == (results["headline"]["point"], 320.0) and rows["медиана, ₽"][1] == 305.0
    said: list[str] = []
    R.print_compare(now, tables, said.append)
    R.print_acceptance(now, said.append)
    printed = "\n".join(said)
    assert "БЫЛО → СТАЛО против «таблицы книги (results.json)»" in printed and "ПРЕДВАРИТЕЛЬНО" in printed
    assert "(а) уровни в условиях окна фактов" in printed and "(ж) гейты: сработало" in printed
    (tmp_path / "runs").mkdir()
    for run in (dict(tables, label="first", finished="2031-02-03T10:00:00"), dict(now, label="second", finished="2031-02-03T11:00:00")):
        (tmp_path / "runs" / f"{run['label']}.json").write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    assert R.latest_run(tmp_path / "runs")["label"] == "second" and R.latest_run(tmp_path / "runs", but="second")["label"] == "first"
    assert R.show(tmp_path / "runs", R.Tree(), "second", "first", said.append) == R.OK
    assert "БЫЛО → СТАЛО против «first»" in "\n".join(said)


# ------------------------------------------------------------ листы приёмки и слова описания

ACCEPTANCE_SHEET = '''# -*- coding: utf-8 -*-
import argparse, json, os, sys
from pathlib import Path
ap = argparse.ArgumentParser()
for name in ("--book", "--facts", "--out"):
    ap.add_argument(name)
a = ap.parse_args()
if os.environ.get("FAKE_SHEET_MODE") == "fail":
    print("ОТКАЗ листа: нет фактов")
    sys.exit(1)
rows = [{"name": "строка в пределах", "value": 1.0, "low": 0.9, "high": 1.1, "ok": True, "words": "модель 1,0 при факте 1,0"},
        {"name": "строка вне пределов", "value": 1.3, "low": 0.9, "high": 1.1, "ok": False, "words": "модель 1,3 при факте 1,0"}]
Path(a.out).write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
'''


def test_the_acceptance_sheets_of_the_description_are_run_printed_and_flagged(fake, monkeypatch):
    """Лист приёмочных проверок книги из описания: его строки печатаются блоком, непройденная строка и отказавший
    лист — красные флаги; слова листа предельной экономики берутся из описания, без них — слова команды."""
    tree, spec, work = fake
    (tree.sheet_dir / "accept.py").write_text(ACCEPTANCE_SHEET, encoding="utf-8")
    spec.ACCEPTANCE = ({"sheet": "accept.py", "title": "проверки пробы"},)
    blocks = R.acceptance_numbers(tree, spec, work / "book.yaml", work)
    assert [b["title"] for b in blocks] == ["проверки пробы"] and [r["ok"] for r in blocks[0]["rows"]] == [True, False]
    tables = R.results_as_run(R.Tree())
    now = dict(copy.deepcopy(tables), label="проба", acceptance=blocks, flags=[],
               marginal={"title": "проба", "anchor": {"model_min": 0.04, "model_max": 0.35, "segment_low": 0.0, "segment_high": 0.3, "ok": False},
                         "rows": {"M": [{"year": "стационар", "value": 0.05, "segment_basis": 0.11, "hurdle": 0.22}]},
                         "words": {"second": "на фондировании ядра", "anchor_words": ("все отдачи листа", "при коридоре разумного", "внутри", "ВНЕ КОРИДОРА"),
                                   "verdict": ("окупает", "НЕ окупает"), "tail": "стационар"}})
    flags = R.flags_of(now)
    assert any("проверка книги не пройдена — строка вне пределов" in f for f in flags) and not any("строка в пределах" in f for f in flags)
    assert any("все отдачи листа" in f and "ВНЕ КОРИДОРА" in f for f in flags)
    said: list[str] = []
    R.print_acceptance(now, said.append)
    printed = "\n".join(said)
    assert "(з) проверки книги — проверки пробы:" in printed and "НЕТ  строка вне пределов: модель 1,3 при факте 1,0" in printed
    assert "(на фондировании ядра 11,0 %)" in printed and "стационар НЕ окупает" in printed and "базис сегмента" not in printed
    assert "| Проверки книги: проверки пробы | строк 2 |" in R.brief(now, tables) and "НЕ пройдены — строка вне пределов" in R.brief(now, tables)
    monkeypatch.setenv("FAKE_SHEET_MODE", "fail")
    failed = R.acceptance_numbers(tree, spec, work / "book.yaml", work)
    assert failed[0]["rows"] == [] and "нет фактов" in " ".join(failed[0]["error"])
    assert any("не отработал" in f for f in R.flags_of(dict(now, acceptance=failed, marginal=None)))
    spec.ACCEPTANCE = ()
    assert R.acceptance_numbers(tree, spec, work / "book.yaml", work) == []
