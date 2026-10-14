# -*- coding: utf-8 -*-
"""Контрольная модель: чтение траекторий книги по правилам docs/MODEL.md §0.4 — буквально (М§17).

* Таблица случаев приложения F.3 методики (машинная копия tests/fixtures/core_pass3/example.json, узел
  trajectory_cases): читатель контрольной модели даёт её значения до 1e-12 и её отказы точно. Таблица — общий тест
  читателя ядра и читателя контрольной модели; здесь — только свой читатель.
* Свои случаи по тексту, которых в таблице нет: полный набор кварталов рядом с двумя полугодиями; полугодия рядом
  с неполным набором кварталов; ключ года рядом с полугодиями; LT_from у траектории без заданных лет; словарь без
  LT; ключ, который не читается ни одним правилом.
* Свойства на случайных траекториях: кварталы года без своих ключей читают одно значение; одиночный ключ действует
  только в своём квартале (полугодии); квартал раньше самого раннего ключа читает его значение; значение года —
  то, что читает квартал без своего ключа.
* Значение года (премия роста, доля выплаты, годовые суммы книги) считается по всей траектории: год, названный
  четырьмя кварталами, — заданный, одиночный ключ на значения других лет не влияет.
* Случай книги (М§4.11, §17): траектория инструментов капитала «одиночный ключ квартала якоря, затем ключи лет» на
  фикстуре формы образца — оставшиеся кварталы года якоря и годы до первого ключа года читают значение первого
  заданного года; сверка с ядром (метка ci_only; ядро импортируется только в момент теста) — нормативы на концы
  года якоря и следующего года в допуске М§17.

Числа случаев — входы тестов, а не допущения.
"""

from __future__ import annotations

import copy
import importlib
import json
import random

import pytest

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]

FIXTURE = cm.ROOT / "tests" / "fixtures" / "core"
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass3" / "example.json"
TABLE_TOL = 1e-12           # значения таблицы случаев: одни и те же действия над одними числами (М§17)
REFUSAL = "BookError"       # так в таблице записан отказ; у контрольной модели это ControlInputError
TABLE_SIZE = (19, 84)       # траекторий и чтений в таблице F.3 — чтобы таблица не похудела незаметно
T2 = "capital.n20.t2"
T2_STEP = 1.8               # во сколько раз траектория инструментов случая книги вырастает к концу сетки (вход)


def table() -> list[dict]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))["trajectory_cases"]


def read(traj, period: str):
    """Чтение квартала читателем контрольной модели; отказ — словом таблицы."""
    try:
        return cm.c_traj_at(traj, *cm.c_per_parse(period))
    except cm.ControlInputError:
        return REFUSAL


def put(tree: dict, dotted: str, value) -> dict:
    out = copy.deepcopy(tree)
    cur = out
    *head, last = dotted.split(".")
    for part in head:
        cur = cur.setdefault(part, {})
    cur[last] = value
    return out


# ============================================================================ таблица случаев F.3


@pytest.mark.tact
def test_table_of_cases_is_read_by_the_text():
    """Таблица случаев приложения F.3: каждое чтение — значение таблицы до 1e-12, каждый отказ — отказ."""
    cases = table()
    assert (len(cases), sum(len(c["values"]) for c in cases)) == TABLE_SIZE
    bad = []
    for case in cases:
        for period, want in case["values"].items():
            got = read(case["trajectory"], period)
            same = got == want if REFUSAL in (got, want) else abs(got - want) <= TABLE_TOL
            if not same:
                bad.append((case["name"], period, got, want))
    assert not bad, bad
    assert any(REFUSAL in c["values"].values() for c in cases), "в таблице нет ни одного отказа"


@pytest.mark.tact
def test_cases_of_the_text_beyond_the_table():
    """Случаи §0.4, которых нет в таблице: что считается полным набором, как читается LT без заданных лет, какие
    ключи не читаются."""
    # все четыре квартала и оба полугодия: значение года — среднее четырёх кварталов (полугодия — «когда названы
    # не все четыре»); соседний год интерполируется от него
    both = {"2027Q1": 1.0, "2027Q2": 3.0, "2027Q3": 5.0, "2027Q4": 7.0, "2027H1": 100.0, "2027H2": 200.0, "2029": 8.0}
    assert cm.c_traj_given_years(both) == {2027: 4.0, 2029: 8.0}
    assert read(both, "2028Q3") == 6.0 and read(both, "2027Q2") == 3.0
    # оба полугодия и один квартал: полный набор — полугодия, их среднее; квартал читается своим ключом
    halves = {"2027H1": 2.0, "2027H2": 6.0, "2027Q4": 60.0, "2029": 8.0}
    assert cm.c_traj_given_years(halves) == {2027: 4.0, 2029: 8.0}
    assert (read(halves, "2027Q3"), read(halves, "2027Q4"), read(halves, "2028Q1")) == (6.0, 60.0, 6.0)
    # ключ года рядом с полугодиями читается как написан
    written = {"2027H1": 2.0, "2027H2": 6.0, "2027": 5.0, "2029": 9.0}
    assert cm.c_traj_given_years(written) == {2027: 5.0, 2029: 9.0} and read(written, "2028Q1") == 7.0
    # самый ранний ключ — год с одиночным ключом квартала внутри: квартал раньше читает значение года
    inside = {"2027": 3.0, "2027Q3": 30.0, "2029": 5.0}
    assert (read(inside, "2026Q4"), read(inside, "2027Q3"), read(inside, "2027Q4"), read(inside, "2028Q2")) == (
        3.0, 30.0, 3.0, 4.0)
    # траектория без заданных лет: LT_from не читается — LT сразу за ключом
    lone = {"2026Q2": 5.0, "LT": 7.0, "LT_from": 2030}
    assert (read(lone, "2026Q1"), read(lone, "2026Q3"), read(lone, "2029Q4")) == (5.0, 7.0, 7.0)
    half = {"2026H2": 5.0, "LT": 7.0}
    assert (read(half, "2026Q1"), read(half, "2026Q4"), read(half, "2027Q1")) == (5.0, 5.0, 7.0)
    # LT_from не позже следующего года и раньше последнего заданного — LT сразу; последний заданный год читает ключ
    for start in (2020, 2027, 2028):
        early = {"2026": 1.0, "2027": 2.0, "LT": 9.0, "LT_from": start}
        assert (read(early, "2027Q4"), read(early, "2028Q1"), read(early, "2031Q2")) == (2.0, 9.0, 9.0)
    # без заданных лет и без LT — отказ; словарь из одного LT_from и пустой словарь — тоже
    for traj in ({"2026Q2": 5.0}, {"2026H1": 5.0, "2027Q1": 1.0, "2027Q2": 1.0, "2027Q3": 1.0}, {"LT_from": 2030}, {}):
        assert read(traj, "2030Q1") == REFUSAL, traj
    # ключ, не разбираемый ни одним правилом, — отказ при чтении любого квартала (М§17), и когда квартал назван
    # своим ключом
    for key in ("2027Q5", "2027Q0", "2027H3", "2027H0", "27", "2027M1", "год", "2027Q", "20270"):
        for period in ("2031Q1", "2026Q2"):
            assert read({"2026": 1.0, key: 2.0, "LT": 3.0}, period) == REFUSAL, (key, period)
    # не траектория
    for traj in (None, "anchor", [1.0, 2.0]):
        assert read(traj, "2030Q1") == REFUSAL
        with pytest.raises(cm.ControlInputError):
            cm.c_traj_year(traj, 2030)
    assert read(0.25, "2030Q1") == 0.25 and cm.c_traj_year(0.25, 2030) == 0.25


@pytest.mark.tact
def test_bad_trajectory_is_refused_in_every_quarter():
    """М§17, «Входы, о которых говорит текст» (находка 8 третьей проверки): значение траектории не числом (null,
    строка, булево, список, словарь) у любого ключа, в том числе у LT и LT_from, и ключ, не разбираемый ни одним
    правилом §0.4, — отказ входа (ControlInputError, а не ошибка счёта) при чтении любого квартала, и тогда, когда
    читаемый квартал назван своим ключом; то же у значения года. Годная траектория после чужой негодной читается
    прежними числами (память разбора не путает траектории)."""
    good = {"2026Q2": 1.0, "2026": 2.0, "2027H1": 3.0, "2028": 4.0, "LT": 5.0, "LT_from": 2031}
    before = {p: read(good, p) for p in ("2026Q2", "2026Q3", "2027Q1", "2027Q4", "2029Q1", "2032Q4")}
    named_quarters = ("2026Q2", "2026Q3", "2027Q1", "2028Q4")
    for bad in (None, "1.0", True, False, [1.0], {"LT": 1.0}):
        for key in ("2026Q2", "2026", "2027H1", "2028", "LT", "LT_from"):
            traj = {**good, key: bad}
            for period in (*named_quarters, "2030Q1"):
                with pytest.raises(cm.ControlInputError):
                    cm.c_traj_at(traj, *cm.c_per_parse(period))
            with pytest.raises(cm.ControlInputError):
                cm.c_traj_year(traj, 2028)
    for key in ("2027Q5", "2027H3", "2027Q0"):
        traj = {**good, key: 6.0}
        for period in (*named_quarters, "2030Q1"):
            with pytest.raises(cm.ControlInputError):
                cm.c_traj_at(traj, *cm.c_per_parse(period))
        with pytest.raises(cm.ControlInputError):
            cm.c_traj_year(traj, 2028)
    # целый ключ года (YAML) и равные по значению целые и дробные числа — годная траектория
    assert read({2026: 1, "LT": 2}, "2026Q3") == 1.0 and read({"2026": 1.0, "LT": 2.0}, "2027Q1") == 2.0
    assert {p: read(good, p) for p in before} == before
    # траектория с теми же ключами и другими значениями читает свои значения: на единицу больше в каждом квартале
    twin = {k: (v if k == "LT_from" else v + 1.0) for k, v in good.items()}
    for p, v in before.items():
        assert read(twin, p) == pytest.approx(v + 1.0, abs=1e-12) and read(good, p) == v, p
    assert cm.c_traj_year(twin, 2029) == pytest.approx(cm.c_traj_year(good, 2029) + 1.0, abs=1e-12)


# ============================================================================ свойства на случайных траекториях


def random_trajectory(rng: random.Random) -> dict:
    """Траектория из ключей лет, кварталов и полугодий 2026–2031 годов, иногда с LT и LT_from (числа — случайные:
    совпадение двух чтений случайным образом невозможно)."""
    traj = {}
    for year in range(2026, 2032):
        kind = rng.random()
        if kind < 0.30:
            traj[str(year)] = rng.uniform(1.0, 9.0)
        if rng.random() < 0.35:
            for q in rng.sample(range(1, cm.QY + 1), rng.randint(1, cm.QY)):
                traj[f"{year}Q{q}"] = rng.uniform(1.0, 9.0)
        if rng.random() < 0.25:
            for h in rng.sample((1, 2), rng.randint(1, 2)):
                traj[f"{year}H{h}"] = rng.uniform(1.0, 9.0)
    if rng.random() < 0.6:
        traj["LT"] = rng.uniform(1.0, 9.0)
        if rng.random() < 0.5:
            traj["LT_from"] = rng.randint(2025, 2036)
    return traj


def named(traj: dict, year: int, q: int) -> bool:
    """Квартал назван ключом квартала, своего полугодия или года (правила 1–3)."""
    return any(key in traj for key in (f"{year}Q{q}", f"{year}H{(q + 1) // 2}", str(year)))


def first_quarter(traj: dict):
    """Квартал самого раннего ключа траектории: (год, квартал) или None."""
    spans = cm._c_time_keys(traj)
    return min((span[0], span[1]) for span in spans.values()) if spans else None


@pytest.mark.tact
def test_properties_of_the_reader_on_random_trajectories():
    """Свойства §0.4, которые не зависят от чисел: (а) квартал, названный ключом, читает ключ — квартала, иначе
    полугодия, иначе года; (б) кварталы года без своих ключей, стоящие не раньше самого раннего ключа, читают одно
    значение — значение года; (в) квартал раньше самого раннего ключа читает значение траектории в квартале этого
    ключа; (г) одиночный ключ, если он не самый ранний, действует только в своём квартале или полугодии: без него
    остальные чтения те же; (д) значение заданного года — ключ года, а без него среднее полного набора."""
    rng = random.Random(850)
    quarters = [(year, q) for year in range(2024, 2035) for q in range(1, cm.QY + 1)]
    seen = {"year_value": 0, "start": 0, "lone": 0, "refusal": 0, "given_by_parts": 0}
    for _ in range(400):
        traj = random_trajectory(rng)
        values = {yq: read(traj, f"{yq[0]}Q{yq[1]}") for yq in quarters}
        start = first_quarter(traj)
        given = cm.c_traj_given_years(traj)
        for (year, q), got in values.items():
            if named(traj, year, q):                                                    # (а)
                key = next(k for k in (f"{year}Q{q}", f"{year}H{(q + 1) // 2}", str(year)) if k in traj)
                assert got == traj[key]
            elif start is not None and (year, q) < start:                               # (в)
                assert got == values[start]
                seen["start"] += 1
            else:                                                                       # (б)
                try:
                    want = cm.c_traj_year(traj, year)
                except cm.ControlInputError:
                    want = REFUSAL
                assert got == want, (traj, year, q)
                seen["year_value" if want != REFUSAL else "refusal"] += 1
        for year, value in given.items():                                               # (д)
            if str(year) in traj:
                assert value == traj[str(year)]
                continue
            full = [traj.get(f"{year}Q{q}") for q in range(1, cm.QY + 1)]
            parts = full if None not in full else [traj[f"{year}H1"], traj[f"{year}H2"]]
            assert value == pytest.approx(sum(parts) / len(parts), rel=TABLE_TOL)
            seen["given_by_parts"] += 1
        for key, span in cm._c_time_keys(traj).items():                                 # (г)
            if span[0] in given or (span[0], span[1]) == start:
                continue
            bare = {k: v for k, v in traj.items() if k != key}
            for (year, q), got in values.items():
                if year == span[0] and span[1] <= q <= span[2]:
                    continue
                assert read(bare, f"{year}Q{q}") == got, (traj, key, year, q)
            seen["lone"] += 1
    assert all(seen.values()), seen


@pytest.mark.tact
def test_year_value_is_read_from_the_whole_trajectory():
    """Значение года (М§0.4): заданный год — ключ или среднее; год между заданными — интерполяция, и год, названный
    четырьмя кварталами, в ней участвует; одиночный ключ на значение своего и соседних лет не влияет; начало
    траектории — правило кварталов, на значение года оно не действует."""
    traj = {"2026Q3": 50.0, "2027Q1": 2.0, "2027Q2": 4.0, "2027Q3": 6.0, "2027Q4": 8.0, "2029": 9.0, "2030Q2": 70.0,
            "LT": 1.0, "LT_from": 2033}
    assert cm.c_traj_given_years(traj) == {2027: 5.0, 2029: 9.0}
    want = {2025: 5.0, 2026: 5.0, 2027: 5.0, 2028: 7.0, 2029: 9.0, 2030: 7.0, 2031: 5.0, 2032: 3.0, 2033: 1.0,
            2040: 1.0}
    assert {year: cm.c_traj_year(traj, year) for year in want} == want
    # квартал раньше самого раннего ключа читает его значение, а значение того же года — значение первого
    # заданного года: одиночный ключ 2026К3 год заданным не делает
    assert (read(traj, "2026Q1"), read(traj, "2026Q3"), read(traj, "2026Q4")) == (50.0, 50.0, 5.0)
    # премия роста (М§4.3): значение года; у средств клиентов квартал со своим ключом читает ключ
    names = cm.FUND_SEGMENTS
    book = {"volumes": {"funds_share_drift": {name: traj for name in names}}}
    key = "volumes.funds_share_drift"
    assert cm.c_premium(book, key, names, names[0], 2028) == 7.0
    assert cm.c_premium(book, key, names, names[0], 2028, quarters=(1, 2, 3, 4)) == 7.0
    assert cm.c_premium(book, key, names, names[0], 2030, quarters=(1, 2, 3, 4)) == pytest.approx((3 * 7.0 + 70.0) / 4)
    assert cm.c_premium(book, key, names, names[0], 2026, quarters=(3, 4)) == pytest.approx((50.0 + 5.0) / 2)
    assert cm.c_premium(book, key, names, names[0], 2027, quarters=(1, 2, 3, 4)) == 5.0
    # то же без ключей кварталов 2027 года: год не задан, 2028-й читает значение первого заданного года
    bare = {k: v for k, v in traj.items() if not k.startswith("2027")}
    book = {"volumes": {"funds_share_drift": {name: bare for name in names}}}
    assert cm.c_premium(book, key, names, names[0], 2028, quarters=(1, 2, 3, 4)) == 9.0
    # одиночный ключ квартала в году между заданными: квартал читает ключ, остальные — значение года, в котором год,
    # названный четырьмя кварталами, участвует как заданный (выборка «только ключи лет» дала бы 9 вместо 7)
    keyed = {**traj, "2028Q2": 40.0}
    book = {"volumes": {"funds_share_drift": {name: keyed for name in names}}}
    assert cm.c_traj_year(keyed, 2028) == 7.0
    assert cm.c_premium(book, key, names, names[0], 2028, quarters=(1, 2, 3, 4)) == pytest.approx((3 * 7.0 + 40.0) / 4)
    assert cm.c_premium(book, key, names, names[0], 2028) == 7.0       # премия кредитов — всегда значение года


# ============================================================================ случай книги: инструменты капитала


def book_case(book: dict) -> tuple[dict, float, float]:
    """Книга формы образца с траекторией инструментов капитала вида «одиночный ключ квартала якоря, затем ключи
    лет» (М§4.11): уровень якоря держится до третьего года сетки и растёт к её концу; LT — уровень конца."""
    level = float(book["capital"]["n20"]["t2"]["LT"])
    y0, qa = cm.c_per_parse(book["meta"]["anchor_period"])
    yl, _ = cm.c_per_parse(book["meta"]["last_period"])
    top = T2_STEP * level
    return put(book, T2, {f"{y0}Q{qa}": level, str(y0 + 2): level, str(yl): top, "LT": top}), level, top


@pytest.fixture(scope="module")
def inputs():
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8")), cm.c_facts_bundle(FIXTURE / "facts")


def test_lone_anchor_quarter_key_then_year_keys_on_the_sample_form(inputs):
    """Случай книги: одиночный ключ квартала якоря задаёт только строку якоря; оставшиеся кварталы года якоря и
    год до первого ключа года читают значение первого заданного года — не значение последнего ключа и не LT.
    Первые два периода клетки — те же, что у книги с постоянной траекторией, бит в бит; на конце сетки в капитале
    Н20.0 стоит уровень конца траектории."""
    book, facts = inputs
    stepped, level, top = book_case(book)
    assert stepped["dividends"]["calendar"].get("frequency") != cm.FREQ_QUARTERLY
    y0, qa = cm.c_per_parse(book["meta"]["anchor_period"])
    assert qa < cm.QY, "у формы образца год якоря неполный: в нём есть прогнозные кварталы"
    traj = stepped["capital"]["n20"]["t2"]
    for year, q in [(y0, h) for h in range(qa, cm.QY + 1)] + [(y0 + 1, h) for h in range(1, cm.QY + 1)] + [(y0 + 2, 1)]:
        assert cm.c_traj_at(traj, year, q) == level, (year, q)
    assert cm.c_traj_at(traj, y0 + 3, 1) > level and cm.c_traj_at(traj, y0 + 20, cm.QY) == top
    flat = cm.c_control_run(book, facts)
    run = cm.c_control_run(stepped, facts)
    for a, b in zip(flat["cells"], run["cells"]):
        assert a["anchor_capital"] == b["anchor_capital"]
        for i in (0, 1):
            names = ("k20", "n20", "k11", "n11", "bv", "rwa", "div")
            assert [a["rows"][i][k] for k in names] == [b["rows"][i][k] for k in names], (a["world"], a["regime"], i)
        # конец сетки: инструменты выше на прирост траектории
        last = b["rows"][-1]
        own = last["bv"] + last["dpreg"] - (1.0 - float(book["capital"]["n20"]["fvoci_recognition"])) * last["R"]
        assert last["k20"] == pytest.approx(own - last["ded20"] + run["ctx"]["A"]["AT1"] + top, rel=1e-12)


def _core_run(book: dict, facts_dir):
    try:
        book_mod, grid_mod = importlib.import_module("model.book"), importlib.import_module("model.grid")
    except Exception as exc:
        pytest.fail(f"ядро не импортируется ({type(exc).__name__}: {exc})")
    try:
        facts = book_mod.load_facts(facts_dir)
        return grid_mod.run_grid(book_mod.book_from_dict(book, facts=facts), facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу случая: {type(exc).__name__}: {str(exc)[:500]}")


@pytest.mark.ci_only
def test_lone_anchor_quarter_key_then_year_keys_against_core(inputs):
    """Тот же случай против ядра (чёрный ящик): все строки сверки в допусках М§17, и отдельно — Н20.0 на концы
    года якоря и следующего года: там прежний читатель контрольной модели брал значение последнего ключа."""
    book, facts = inputs
    stepped, level, top = book_case(book)
    run = _core_run(stepped, FIXTURE / "facts")
    ctl = cm.c_control_run(stepped, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    y0 = ctl["ctx"]["anchor"][0]
    title = tcm.line_titles(ctl["ctx"]["B"])["n20"]
    early = [r for r in rows if r["what"].startswith((f"{title} на конец {y0},", f"{title} на конец {y0 + 1},"))]
    assert len(early) == 2 * len(ctl["cells"]) and all(r["ok"] for r in early)
    # цена ошибки прежнего чтения в этих строках — выше допуска: случай различает два чтения
    rwa = max(c["rows"][1]["rwa"] for c in ctl["cells"])
    assert (top - level) / rwa > tcm.TOL_RATIO
