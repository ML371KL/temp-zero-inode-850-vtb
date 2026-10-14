# -*- coding: utf-8 -*-
"""Сверка контрольной модели с ядром: правило строки «ступень политики у порога» (docs/MODEL.md §17, прил. G.3).

Политика из двух и более ступеней (dividends.policy.steps, годовой режим) разрывна по запасу: у порога ступени две
модели, чьи нормативы расходятся в своём допуске, выбирают разные ступени без ошибки счёта. Правило строки:

* распознание — по первому расхождению ступеней клетки (обе модели решили политикой): ступень
  j = min(j_ядро, j_контроль), запасы m = H_j − want_j, у порога — |m_ядро − m_контроль| ≤ 0,3 п.п. × RWA конца года
  решения (контрольной модели);
* каскад — строки клетки с года первого расхождения (дивиденд года, DPS, Н20.0 и Н20.1 на конец года, X_T и доход
  на избыток, взнос года) судятся с расширенным полом: к абсолютному полу строки добавляется размах ступеней
  G = max (want_первой − want_последней) по решениям контрольной модели с года расхождения до года строки;
* не прячет — строки до года расхождения обычные, стоимость клетки, слои и точка всегда в своих допусках, а
  стоимость клетки вне допуска снимает правило с клетки; строка вне расширенного пола — обычная строка вне допуска;
* печать — строка в расширенном допуске ok с полем tol_abs расширенного пола, сводка считает такие строки счётчиком
  n_step и называет клетки step_cells, в n_bad они не входят и all_ok не роняют, худшая — отдельной строкой со
  словами «ступень политики у порога».

Здесь: случаи приложения G.3 (машинная копия tests/fixtures/core_pass4/example.json, узел policy_step) — рабочими
функциями писателя сводки до 1e-9; писатель сводки на заглушке ядра (величины контрольной модели, решения ядра —
входы теста) на фикстуре формы образца с политикой из двух ступеней — каждое правило текста и построенный случай
настоящего расхождения у порога, которого правило не прячет. Ядро не нужно.

Числа подмен — входы тестов, а не допущения.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]

FIXTURE = cm.ROOT / "tests" / "fixtures" / "core"
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass4" / "example.json"
EXAMPLE_TOL = 1e-9          # пример приложения G: формулы без шага, одно определение (М§17)
EXACT = 1e-12
# Акции в обращении своего года строки DPS случая G.3 (млн шт.) — число из текста приложения G.3 (в машинной копии
# его нет: там стоит итог 13,629513 расширенного пола DPS).
G3_SHARES_OWN = 24464.693
# Политика из двух ступеней на фикстуре формы образца (вход теста): доля книги при её пороге и половина доли без
# порога — так у клеток с запасом между двумя желаемыми выплатами модели выбирают вторую ступень.
TWO_STEPS = [{"payout": {"LT": 0.5}, "threshold": 0.133}, {"payout": {"LT": 0.25}, "threshold": 0.0}]
HALF = 0.5                  # подмена строки — пол плюс половина размаха ступеней: вне обычного пола, в расширенном
OVER = 1.1                  # подмена строки — пол плюс 1,1 размаха: вне расширенного пола (настоящее расхождение)


# ============================================================================ приложение G.3


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))["policy_step"]


def close(got, want, what: str, tol: float = EXAMPLE_TOL) -> None:
    assert got == pytest.approx(want, rel=tol, abs=tol), (what, got, want)


@pytest.mark.tact
def test_appendix_g3_cases_on_the_summary_writer():
    """G.3: ступень проверки, запасы обеих моделей, их расстояние, τ = 0,3 п.п. × RWA, «у порога» и размах ступеней
    по четырём случаям (первое расхождение у порога, следующее решение — каскад, запасы далеко, ступень одна) — до
    1e-9, признаки — точно; расширенный пол строк первого случая (дивиденд 2034 года, DPS за 2033 год, Н20.0 на конец
    года после расхождения) и вердикты строк обычным и расширенным полом; стоимость клетки — в своём допуске."""
    doc = example()
    assert doc["tol_ratio"] == tcm.TOL_RATIO
    for case in doc["cases"]:
        got = tcm.step_case(case["core"], case["control"], case["rwa"], first=case["first_divergence"])
        assert got["step_checked"] == case["step_checked"], case["case"]
        assert got["steps_differ"] is case["steps_differ"], case["case"]
        assert got["at_threshold"] is case["at_threshold"], case["case"]
        for field in ("margin_core", "margin_control", "margin_distance", "tau", "step_gap"):
            close(got[field], case[field], f"{case['case']}.{field}")
    first = doc["cases"][0]
    gap = tcm.step_case(first["core"], first["control"], first["rwa"])["step_gap"]
    close(gap, doc["step_gap_first_case"], "размах ступеней первого случая")
    close(tcm.step_floor(tcm.TOL_RATIO, gap, 1.0 / first["rwa"]), doc["ratio_tolerance_after"], "Н20.0 после расхождения")
    scales = {"dividend_2034": 1.0, "dps_2033": 1000.0 / G3_SHARES_OWN}
    for row in doc["rows_first_case"]:
        close(tcm.step_floor(row["tol_abs_plain"], gap, scales[row["what"]]), row["tol_abs_step"], row["what"], 1e-7)
        diff_rel = row["control"] / row["core"] - 1.0
        close(row["diff"], row["control"] - row["core"], f"{row['what']}.diff")
        close(diff_rel, row["diff_rel"], f"{row['what']}.diff_rel")
        assert tcm.verdict(row["diff"], diff_rel, row["tol"], tcm.REL, row["tol_abs_plain"]) is row["ok_plain"]
        assert tcm.verdict(row["diff"], diff_rel, row["tol"], tcm.REL, row["tol_abs_step"]) is row["ok_step"]
    guard = doc["value_guard"]
    value = tcm._row("стоимость клетки", tcm.U_BN, guard["cell_value_core"], guard["cell_value_control"],
                     guard["tol_rel"], tcm.REL, group="cell")
    assert value["ok"] is guard["ok"]
    # τ — производная допуска норматива в рублях: без RWA порог был бы 0,003 млрд ₽ и случай первого расхождения
    # (запасы на 0,432 млрд ₽ друг от друга) судился бы как настоящее расхождение
    assert first["margin_distance"] > tcm.TOL_RATIO and first["at_threshold"]


# ============================================================================ писатель сводки на заглушке ядра


@pytest.fixture(scope="module")
def two_steps():
    """Фикстура формы образца с политикой из двух ступеней (годовая ветвь) — прогон контрольной модели."""
    book = json.loads((FIXTURE / "book.json").read_text(encoding="utf-8"))
    book["dividends"]["policy"]["steps"] = copy.deepcopy(TWO_STEPS)
    return cm.c_control_run(book, cm.c_facts_bundle(FIXTURE / "facts"))


@pytest.fixture(scope="module")
def one_step():
    """Та же фикстура как есть: политика из одной ступени."""
    book = json.loads((FIXTURE / "book.json").read_text(encoding="utf-8"))
    return cm.c_control_run(book, cm.c_facts_bundle(FIXTURE / "facts"))


def tag_of(c: dict) -> str:
    return "/".join((c["world"], c["regime"], c["scenario"]))


def core_decisions(c: dict) -> dict:
    """Решения ядра заглушки — решения контрольной модели клетки той же формы (поля Decision ядра: year — год
    прибыли, step, headroom и want по ступеням, source; period — None у годового режима)."""
    out = {}
    for yp, d in c["decisions"].items():
        source = {"policy": tcm.CORE_POLICY, "crisis_skip": "crisis_skip"}.get(d["kind"], "register")
        out[yp] = SimpleNamespace(year=yp, step=d.get("step", 0), headroom=tuple(d.get("headrooms") or ()),
                                  want=tuple(d.get("wants") or ()), source=source, period=None)
    return out


def stub(ctl: dict, decisions: bool = True):
    """Заглушка ядра: величины контрольной модели × 1/1,01 (все строки в допуске) и, если decisions, решения ядра о
    дивиденде со ступенями контрольной модели (расхождений ступеней нет)."""
    run = tcm._stub_core(ctl, 1.0 / 1.01, d_ratio=0.001)
    if decisions:
        for c in ctl["cells"]:
            run.cell(c["world"], c["regime"], c["scenario"]).decisions = tuple(core_decisions(c).values())
    return run


def pick_threshold_cell(ctl: dict) -> tuple[dict, int]:
    """Клетка и год прибыли, где контрольная модель первой ступени не дала, но была у её порога (запас первой ступени
    — меньше десятой доли τ), а до этого года клетка решала политикой первой ступенью; за годом — ещё два решения."""
    years = ctl["years"]
    for c in ctl["cells"]:
        before = []
        for yp, d in sorted(c["decisions"].items()):
            if d["kind"] != "policy" or len(d.get("wants") or ()) < 2:
                break
            rwa = c["rows"][years.index(yp + 1)]["rwa"]
            m = d["headrooms"][0] - d["wants"][0]
            if d["step"] == 1 and before and -m < 0.1 * tcm.TOL_RATIO * rwa and yp + 3 <= years[-1]:
                return c, yp
            if d["step"] != 0:
                break
            before.append(yp)
    raise AssertionError("на фикстуре нет клетки у порога первой ступени")


def diverge(run, c: dict, yp: int, distance: float, *, source: str = tcm.CORE_POLICY):
    """Ядро заглушки выбирает в году yp первую ступень, а контрольная модель — вторую: запас первой ступени ядра
    m_ядро = m_контроль + distance (у контрольной модели он отрицателен, у ядра — не меньше нуля)."""
    cell = run.cell(c["world"], c["regime"], c["scenario"])
    d = c["decisions"][yp]
    m = d["headrooms"][0] - d["wants"][0]
    assert m < 0.0 and m + distance >= 0.0
    theirs = {x.year: x for x in cell.decisions}
    head = list(d["headrooms"])
    head[0] = d["wants"][0] + m + distance
    theirs[yp] = SimpleNamespace(year=yp, step=0, headroom=tuple(head), want=tuple(d["wants"]), source=source,
                                 period=None)
    cell.decisions = tuple(theirs[k] for k in sorted(theirs))
    return cell


def gap_to(c: dict, first: int, last: int) -> float:
    """Размах ступеней по решениям контрольной модели с года прибыли first по last (пересчёт теста по тексту)."""
    return max(c["decisions"][y]["wants"][0] - c["decisions"][y]["wants"][-1] for y in range(first, last + 1))


def row_by(rows: list[dict], what: str) -> dict:
    found = [r for r in rows if r["what"] == what]
    assert len(found) == 1, what
    return found[0]


class Push:
    """Подмены строк ядра заглушки: строка ядра уводится от контрольной модели на «пол строки + доля × размах в
    единицах строки» — вне обычного допуска; пол берётся из строки сверки чистой заглушки."""

    def __init__(self, ctl: dict, c: dict, clean_rows: list[dict]):
        self.ctl, self.c, self.clean = ctl, c, clean_rows
        self.tag = tag_of(c)
        self.titles = tcm.line_titles(ctl["ctx"]["B"])
        self.qidx = tcm._quarter_index(ctl)

    def plain(self, what: str) -> float:
        r = row_by(self.clean, what)
        assert r["ok"]
        return r["tol"] if r["tol_kind"] == tcm.ABS else r["tol_abs"]

    def div(self, run, year: int, gap: float, share: float) -> tuple[str, float]:
        what = f"{self.titles['div']} {year}, клетка {self.tag}"
        shift = self.plain(what) + share * gap
        cell = run.cell(self.c["world"], self.c["regime"], self.c["scenario"])
        j = self.qidx[year][-1]
        mine = self.c["rows"][self.ctl["years"].index(year)]["div"]
        cell.quarters["div"][j] = mine + shift - sum(cell.quarters["div"][k] for k in self.qidx[year][:-1])
        return what, self.plain(what) + gap

    def dps(self, run, yp: int, gap: float, share: float) -> tuple[str, float]:
        what = f"DPS за {yp}, клетка {self.tag}"
        scale = 1000.0 / self.ctl["ctx"]["A"]["N_out"]
        shift = self.plain(what) + share * gap * scale
        run.cell(self.c["world"], self.c["regime"], self.c["scenario"]).dps[yp] = self.c["decisions"][yp]["dps"] + shift
        return what, self.plain(what) + gap * scale

    def ratio(self, run, line: str, year: int, gap: float, share: float) -> tuple[str, float]:
        what = f"{self.titles[line]} на конец {year}, клетка {self.tag}"
        r = self.c["rows"][self.ctl["years"].index(year)]
        shift = self.plain(what) + share * gap / r["rwa"]
        run.cell(self.c["world"], self.c["regime"], self.c["scenario"]).quarters[line][self.qidx[year][-1]] = r[line] - shift
        return what, self.plain(what) + gap / r["rwa"]

    def x_t(self, run, gap: float, share: float) -> tuple[str, float]:
        what = f"избыток капитала на терминале, клетка {self.tag}"
        shift = self.plain(what) + share * gap
        run.cell(self.c["world"], self.c["regime"], self.c["scenario"]).x_t = self.c["x_t"] + shift
        return what, self.plain(what) + gap


@pytest.fixture(scope="module")
def case(two_steps):
    """Клетка и год первого расхождения на фикстуре с двумя ступенями; строки чистой заглушки."""
    c, yp = pick_threshold_cell(two_steps)
    clean = tcm.compare_with_core(stub(two_steps), two_steps)
    assert all(r["ok"] for r in clean)
    return c, yp, clean


def pushed(two_steps, case, share: float = HALF, distance: float | None = None, *, value: float | None = None):
    """Заглушка с расхождением ступеней в году первого расхождения и подменёнными строками клетки: дивиденд года
    решения и года каскада, DPS года прибыли, Н20.0 и Н20.1 на конец года решения, X_T. Возвращает заглушку и
    {строка: ожидаемый расширенный пол}."""
    c, yp, clean = case
    run = stub(two_steps)
    rwa = c["rows"][two_steps["years"].index(yp + 1)]["rwa"]
    m = c["decisions"][yp]["headrooms"][0] - c["decisions"][yp]["wants"][0]
    cell = diverge(run, c, yp, -2.0 * m if distance is None else distance)
    assert distance is not None or 2.0 * -m <= tcm.TOL_RATIO * rwa
    p = Push(two_steps, c, clean)
    wide = dict([p.div(run, yp + 1, gap_to(c, yp, yp), share),            # год решения Y* + 1
                 p.div(run, yp + 2, gap_to(c, yp, yp + 1), share),        # каскад
                 p.dps(run, yp, gap_to(c, yp, yp), share),
                 p.ratio(run, "n20", yp + 1, gap_to(c, yp, yp), share),
                 p.ratio(run, "n11", yp + 1, gap_to(c, yp, yp), share),
                 p.x_t(run, gap_to(c, yp, max(c["decisions"])), share)])
    if value is not None:
        cell.v_ri = c["v_ri"] * value
    return run, wide


@pytest.mark.tact
def test_control_decisions_carry_every_step(two_steps, one_step):
    """М§17 п. 1: контрольная модель отдаёт в решениях запасы и желаемые выплаты всех ступеней (wants, headrooms), не
    только до выбранной; решение — прежнее: ступень — первая, чей запас не меньше желаемой выплаты, иначе последняя
    (выплата — меньшее из желаемой и запаса, не ниже нуля); want — желаемая выплата первой ступени, H — запас
    выбранной. Желаемые выплаты ступеней — доли ступеней от одной базы. Запись реестра ступеней не несёт."""
    shares = [s["payout"]["LT"] for s in TWO_STEPS]
    seen = 0
    for ctl, n in ((two_steps, len(TWO_STEPS)), (one_step, 1)):
        for c in ctl["cells"]:
            for d in c["decisions"].values():
                if d["kind"] == "register":
                    assert "wants" not in d
                    continue
                assert len(d["wants"]) == len(d["headrooms"]) == n
                passed = [j for j, (w, h) in enumerate(zip(d["wants"], d["headrooms"])) if h >= w]
                assert d["step"] == (passed[0] if passed else n - 1)
                assert d["want"] == d["wants"][0] and d["H"] == d["headrooms"][d["step"]]
                assert d["base_div"] == (d["wants"][d["step"]] if passed
                                         else max(0.0, min(d["wants"][-1], d["headrooms"][-1])))
                if n > 1 and d["wants"][0] > 0.0:
                    assert d["wants"][1] / d["wants"][0] == pytest.approx(shares[1] / shares[0], rel=EXACT)
                    seen += d["step"] == 0                  # запас и желаемая выплата ступени после выбранной
    assert seen


@pytest.mark.tact
def test_no_divergence_keeps_the_summary(two_steps, one_step):
    """Решения ядра с теми же ступенями — сводка та же, что без решений ядра: ни n_step, ни step_cells, ни строки
    правила (у прежних книг и фикстур сводка прежняя); у книги с одной ступенью — тоже."""
    for ctl in (two_steps, one_step):
        bare = tcm.checks_document(stub(ctl, decisions=False), ctl, as_of="2026-10-14", commit=None)
        full = tcm.checks_document(stub(ctl), ctl, as_of="2026-10-14", commit=None)
        assert full == bare and full["all_ok"] and "n_step" not in full and "step_cells" not in full
        assert not any(tcm.STEP_WORDS in r["what"] for r in full["rows"])
    assert all(len(d["wants"]) == 2 for c in two_steps["cells"] for d in c["decisions"].values() if d.get("wants"))
    assert all(len(d["wants"]) == 1 for c in one_step["cells"] for d in c["decisions"].values() if d.get("wants"))


@pytest.mark.tact
def test_first_divergence_at_the_threshold_widens_the_cell_rows(two_steps, case):
    """М§17 пп. 1, 2, 4: первое расхождение у порога — строки клетки с года расхождения (дивиденд года решения и года
    каскада, DPS, Н20.0 и Н20.1 на конец года, X_T), вне обычного допуска, — в расширенном: ok, tol_abs — обычный пол
    плюс размах ступеней G до года строки в единицах строки; n_step — их число, step_cells — клетка и год прибыли
    первого расхождения, n_bad = 0, all_ok; худшая из них — строкой сводки со словами «ступень политики у порога»."""
    c, yp, _ = case
    run, wide = pushed(two_steps, case)
    rows = tcm.compare_with_core(run, two_steps)
    for what, floor in wide.items():
        r = row_by(rows, what)
        assert r["ok"] and r.get("step") and r["tol_abs"] == pytest.approx(floor, rel=EXACT), (what, r)
        assert r["step_cell"] == tag_of(c) and r["step_year"] == yp
        assert not tcm.verdict(r["diff"], r["diff_rel"], r["tol"], r["tol_kind"], r["floor_plain"]), what
        tcm._assert_row_form(tcm._public(r))
    assert all(r["ok"] for r in rows)
    doc = tcm.checks_document(run, two_steps, as_of="2026-10-14", commit=None)
    assert doc["all_ok"] and doc["n_bad"] == 0 and doc["n_step"] == len(wide)
    assert doc["step_cells"] == [{"cell": tag_of(c), "year": yp}]
    assert doc["n_step"] <= doc["n_rows"] - doc["n_bad"]
    shown = [r for r in doc["rows"] if r["what"].startswith(tcm.STEP_WORDS)]
    assert len(shown) == 1 and shown[0]["ok"] and shown[0]["what"].split(": ", 1)[1] in wide
    for r in doc["rows"]:
        tcm._assert_row_form(r)
    json.dumps(doc, ensure_ascii=False)


@pytest.mark.tact
def test_rows_before_the_first_divergence_stay_plain(two_steps, case):
    """М§17 п. 3: строки до года первого расхождения — обычные: дивиденд года Y* (решение за прошлый год) и DPS за
    прошлый год прибыли с тем же сдвигом, что у строк каскада, вне допуска."""
    c, yp, clean = case
    run, _ = pushed(two_steps, case)
    p = Push(two_steps, c, clean)
    early = [p.div(run, yp, gap_to(c, yp, yp), HALF)[0], p.dps(run, yp - 1, gap_to(c, yp, yp), HALF)[0]]
    rows = tcm.compare_with_core(run, two_steps)
    for what in early:
        r = row_by(rows, what)
        assert not r["ok"] and not r.get("step"), what
    doc = tcm.checks_document(run, two_steps, as_of="2026-10-14", commit=None)
    assert not doc["all_ok"] and doc["n_bad"] == len(early)


@pytest.mark.tact
def test_far_margins_are_a_real_divergence(two_steps, case):
    """М§17 п. 1: запасы моделей дальше τ — настоящее расхождение: строки судятся обычными допусками, правила нет."""
    c, yp, _ = case
    rwa = c["rows"][two_steps["years"].index(yp + 1)]["rwa"]
    run, wide = pushed(two_steps, case, distance=1.5 * tcm.TOL_RATIO * rwa)
    rows = tcm.compare_with_core(run, two_steps)
    assert all(not row_by(rows, what)["ok"] for what in wide)
    doc = tcm.checks_document(run, two_steps, as_of="2026-10-14", commit=None)
    assert not doc["all_ok"] and doc["n_bad"] == len(wide) and "n_step" not in doc


@pytest.mark.tact
def test_cell_value_out_of_tolerance_lifts_the_rule(two_steps, case):
    """М§17 п. 3: стоимость клетки вне допуска — правило к клетке не применяется: все её строки судятся обычными
    допусками (строка стоимости клетки сама не расширяется никогда)."""
    run, wide = pushed(two_steps, case, value=1.2)
    rows = tcm.compare_with_core(run, two_steps)
    c, _, _ = case
    value = row_by(rows, f"стоимость клетки {tag_of(c)}")
    assert not value["ok"] and not value.get("step")
    assert all(not row_by(rows, what)["ok"] for what in wide)
    assert "n_step" not in tcm.checks_document(run, two_steps, as_of="2026-10-14", commit=None)


@pytest.mark.tact
def test_real_divergence_near_the_threshold_is_not_hidden(two_steps, case):
    """Построенный случай настоящего расхождения у порога: ступени разошлись у порога, но строки ядра ушли дальше
    обычного пола плюс размах ступеней (ошибка выплаты больше допуска) — строки вне допуска, all_ok падает, по правилу
    не проходит ни одна. Тот же сдвиг выплаты без расхождения ступеней — тоже вне допуска."""
    run, wide = pushed(two_steps, case, share=OVER)
    rows = tcm.compare_with_core(run, two_steps)
    for what in wide:
        r = row_by(rows, what)
        assert not r["ok"] and not r.get("step") and "step_cell" not in r, what
    doc = tcm.checks_document(run, two_steps, as_of="2026-10-14", commit=None)
    assert not doc["all_ok"] and doc["n_bad"] == len(wide) and "n_step" not in doc
    # ошибка выплаты без расхождения ступеней: сдвиг в половину размаха — вне допуска (правило не включается)
    c, yp, clean = case
    plain = stub(two_steps)
    p = Push(two_steps, c, clean)
    what = p.div(plain, yp + 1, gap_to(c, yp, yp), HALF)[0]
    assert not row_by(tcm.compare_with_core(plain, two_steps), what)["ok"]


@pytest.mark.tact
def test_first_divergence_is_the_earliest_policy_one(two_steps, case):
    """М§17 п. 1: первое расхождение — самое раннее, где обе модели решили политикой. Позднее расхождение с запасами
    далеко (каскад) порогом не судится; более раннее «расхождение» записью реестра или отменой кризисом — не
    расхождение."""
    c, yp, _ = case
    run, wide = pushed(two_steps, case)
    rwa = c["rows"][two_steps["years"].index(yp + 1)]["rwa"]
    far = 3.0 * tcm.TOL_RATIO * rwa
    cell = run.cell(c["world"], c["regime"], c["scenario"])
    theirs = {x.year: x for x in cell.decisions}
    later = yp + 1
    d = c["decisions"][later]
    theirs[later] = SimpleNamespace(year=later, step=1 - d["step"], headroom=tuple(h + far for h in d["headrooms"]),
                                    want=tuple(d["wants"]), source=tcm.CORE_POLICY, period=None)
    earlier = yp - 1
    d = c["decisions"][earlier]
    theirs[earlier] = SimpleNamespace(year=earlier, step=1 - d["step"], headroom=tuple(h - far for h in d["headrooms"]),
                                      want=tuple(d["wants"]), source="crisis_skip", period=None)
    cell.decisions = tuple(theirs[k] for k in sorted(theirs))
    rows = tcm.compare_with_core(run, two_steps)
    assert all(row_by(rows, what)["ok"] and row_by(rows, what)["step_year"] == yp for what in wide)
    # то же раннее расхождение решением политикой — первое расхождение с запасами далеко: правила нет
    theirs[earlier] = SimpleNamespace(**{**vars(theirs[earlier]), "source": tcm.CORE_POLICY})
    cell.decisions = tuple(theirs[k] for k in sorted(theirs))
    rows = tcm.compare_with_core(run, two_steps)
    assert all(not row_by(rows, what)["ok"] for what in wide)


@pytest.mark.tact
def test_steps_with_equal_wants_are_no_divergence(two_steps, case):
    """Разные номера ступеней при равных желаемых выплатах ступеней (база дивиденда не больше нуля — обе ступени
    желают ноль) — не расхождение ступеней: выплата скачком не меняется, капитал между моделями не переложен
    (толкование М§17 п. 1, docs/CONTROL-MODEL.md §7). Такой год перед годом Y* с запасами далеко правило не снимает;
    тот же год с разными желаемыми выплатами — первое расхождение, запасы далеко — правила нет."""
    c, yp, _ = case
    run, wide = pushed(two_steps, case)
    rwa = c["rows"][two_steps["years"].index(yp + 1)]["rwa"]
    far = 3.0 * tcm.TOL_RATIO * rwa
    cell = run.cell(c["world"], c["regime"], c["scenario"])
    theirs = {x.year: x for x in cell.decisions}
    earlier = yp - 1
    d = c["decisions"][earlier]
    saved = d["wants"]
    try:
        d["wants"] = [0.0] * len(saved)
        theirs[earlier] = SimpleNamespace(year=earlier, step=1 - d["step"], headroom=tuple(h - far for h in d["headrooms"]),
                                          want=tuple(d["wants"]), source=tcm.CORE_POLICY, period=None)
        cell.decisions = tuple(theirs[k] for k in sorted(theirs))
        rows = tcm.compare_with_core(run, two_steps)
        assert all(row_by(rows, what)["ok"] and row_by(rows, what)["step_year"] == yp for what in wide)
        d["wants"] = saved
        theirs[earlier] = SimpleNamespace(**{**vars(theirs[earlier]), "want": tuple(saved)})
        cell.decisions = tuple(theirs[k] for k in sorted(theirs))
        rows = tcm.compare_with_core(run, two_steps)
        assert all(not row_by(rows, what)["ok"] for what in wide)
    finally:
        d["wants"] = saved


@pytest.mark.tact
def test_one_step_and_quarterly_mode_have_no_rule(one_step, two_steps, case):
    """У книги с одной ступенью правила нет: ступень ядра, отличная от ступени контрольной модели, при одной желаемой
    выплате правило не включает; в квартальном режиме ступеней нет (М§5.7.1) — правило не применяется."""
    run = stub(one_step)
    c = next(x for x in one_step["cells"] if x["decisions"])
    cell = run.cell(c["world"], c["regime"], c["scenario"])
    cell.decisions = tuple(SimpleNamespace(**{**vars(x), "step": 1}) for x in cell.decisions)
    assert tcm.policy_step_rule(one_step, c, cell, tag_of(c), [], []) is None
    c2, yp, _ = case
    run2, _ = pushed(two_steps, case)
    quarterly = {**two_steps, "quarterly": True}
    assert tcm.policy_step_rule(quarterly, c2, run2.cell(c2["world"], c2["regime"], c2["scenario"]),
                                tag_of(c2), [], []) is None
    assert tcm.policy_step_rule(two_steps, c2, run2.cell(c2["world"], c2["regime"], c2["scenario"]),
                                tag_of(c2), [], [])["year"] == yp
