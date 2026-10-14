# -*- coding: utf-8 -*-
"""Контрольная модель: доля вычета якоря, постоянная в рублях (docs/MODEL.md §4.11, §7, §17; ключи
capital.n20.deductions_fixed_share и capital.n11.deductions_fixed_share).

* Пример приложения F методики (машинная копия tests/fixtures/core_pass3/example.json, узел deductions):
  контрольная модель подставляет входы примера в свои рабочие функции — счёт норматива годовой ветви и квартального
  прохода, избыток капитала терминала, строки моста норматива — и получает его числа до 1e-9 (М§17): вычеты,
  капитал и нормативы строки якоря и строки квартала с долей, без ключей и при доле, равной единице; слагаемые
  X_T; строку вычетов моста. Перенос якоря контрольная модель не исполняет: доли после переноса — входы примера, по
  ним проверяется только формула вычета книги нового якоря.
* Свойства своего счёта на фикстурах формы образца (tests/fixtures/core — годовая ветвь; tests/fixtures/core_t —
  квартальный проход капитала и множитель плотности режима) с ключами, подставленными тестом: без ключей и при
  ключах, равных нулю, — прежние числа бит в бит; ряд вычета равен формуле от ряда RWA, капитал пересчитывается
  тестом по рядам клетки; якорь воспроизводит оба норматива при любой доле; при долях, равных единице, вычет
  постоянен; на книге, у которой путь капитала от нормативов не зависит, капитал, норматив и избыток терминала
  выше ровно на слагаемое доли; доля одного норматива не меняет другой; ниже якоря норматив с долей ниже; сдвиг
  вычета якоря вместе с поправкой и долей оставляет нормативы прежними; строка вычетов моста; капитал после
  взноса акционеров; отказы книги.
* Сверка с ядром (метка ci_only; ядро импортируется только в момент теста) — в допусках М§17: отдельной строки
  вычета в сверке нет, сверяются нормативы на конец года, X_T, дивиденд, взнос и оценка.

Числа подмен — входы тестов, а не допущения.
"""

from __future__ import annotations

import copy
import importlib
import json

import pytest

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]

FIXTURE = cm.ROOT / "tests" / "fixtures" / "core"
FIXTURE_T = cm.ROOT / "tests" / "fixtures" / "core_t"
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass3" / "example.json"
EXAMPLE_TOL = 1e-9          # пример приложения F: формулы без шага, одно определение (М§17)
EXACT = 1e-12               # своё свойство: те же действия над теми же числами
SHARE20, SHARE11 = cm.DED_SHARE[cm.NORM_TOTAL], cm.DED_SHARE[cm.NORM_BASE]
DED20, DED11 = cm.DED_ANCHOR[cm.NORM_TOTAL], cm.DED_ANCHOR[cm.NORM_BASE]
ETA20, ETA11 = 0.6, 0.35    # доли формы сверки: разные у двух нормативов и не 0,5 (вход теста)
ROW_KEYS = ("k20", "k11", "n20", "n11", "n11_star", "ded20", "ded11", "bv", "rwa", "div", "pbt", "ci")
# Книга, у которой путь капитала от нормативов не зависит (М§4.11, свойство 5): выплаты и выплаты избытка нет.
NO_PAYOUT = {"dividends.policy.payout": {"LT": 0.0}, "dividends.excess.epsilon": 0.0}
# Форма с нехваткой капитала и включённой докапитализацией — как в tests/test_control_recap.py (входы теста).
SHORT = {"dividends.policy.threshold": 0.0, "capital.mgmt_buffer.n20_0": 0.03, "capital.mgmt_buffer.n1_1": 0.03,
         "capital.recapitalization": {"enabled": True, "price_discount": 0.10, "lookahead_quarters": 3,
                                      "min_amount": 30.0},
         "valuation.cell_floor": 0.0}
LEFT_SHARE = 0.10           # остаток недостатка после взноса — не больше десятой доли взноса (М§14.1)
EXAMPLE_ANCHOR, EXAMPLE_NEXT = (2026, 2), (2026, 3)     # кварталы двух строк примера (номера — условные)
EXAMPLE_SCENARIO = "example"


def put(tree: dict, dotted: str, value) -> dict:
    """Копия дерева с подменой одного пути (промежуточные узлы создаются)."""
    out = copy.deepcopy(tree)
    cur = out
    *head, last = dotted.split(".")
    for part in head:
        cur = cur.setdefault(part, {})
    cur[last] = value
    return out


def with_keys(book: dict, keys: dict) -> dict:
    for dotted, value in keys.items():
        book = put(book, dotted, value)
    return book


def with_shares(book: dict, eta20, eta11) -> dict:
    return with_keys(book, {SHARE20: eta20, SHARE11: eta11})


def key(c: dict) -> tuple:
    return c["world"], c["regime"], c["scenario"]


def rows_of(res: dict, names=ROW_KEYS) -> list:
    return [[tuple(r[k] for k in names) for r in c["rows"]] for c in res["cells"]]


def values_of(res: dict) -> tuple:
    return ([(c["v_ri"], c["v_ddm"], c["x_t"], c["bv_v"]) for c in res["cells"]], rows_of(res),
            (res["point"], res["low"], res["high"]))


def close(got, want, what: str, tol: float = EXAMPLE_TOL) -> None:
    assert got == pytest.approx(want, rel=tol, abs=tol), (what, got, want)


# ============================================================================ пример приложения F


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))["deductions"]


def example_ctx(inp: dict, shares, *, ded20=None, gap20=None, rwa0=None) -> dict:
    """Контекст счёта норматива на входах примера F: книга из тех ключей, которые читает счёт норматива (вычеты
    якоря и их доли, признание фонда, инструменты, поправки, вычеты сценария по кварталам двух строк, требования),
    RWA якоря и бессрочные инструменты. shares — пара долей или None (книга без ключей)."""
    a, q = inp["anchor"], inp["quarter"]
    at = {f"{y}Q{h}": row for (y, h), row in ((EXAMPLE_ANCHOR, a), (EXAMPLE_NEXT, q))}
    book = {"capital": {
        "n20": {"deductions_anchor": inp["ded20_0"] if ded20 is None else ded20,
                "fvoci_recognition": inp["fvoci_recognition"], "gap_pp": inp["gap20"] if gap20 is None else gap20,
                "t2": {per: row["t2"] for per, row in at.items()}},
        "n11": {"deductions_anchor": inp["ded11_0"], "gap_pp": inp["gap11"], "audit_cutoffs": [1, 2, 3, 4]},
        "minimum": {"n20_0": inp["req20"], "n1_1": inp["req11"]},
        "mgmt_buffer": {"n20_0": 0.0, "n1_1": 0.0},
        "reg_scenarios": {"ids": [EXAMPLE_SCENARIO], EXAMPLE_SCENARIO: {
            "conservation": 0.0, "sifi": 0.0, "ccyb": 0.0,
            "deduction_pp": {"n20_0": {per: row["dpp20"] for per, row in at.items()},
                             "n1_1": {per: row["dpp11"] for per, row in at.items()}}}}},
        "dividends": {"policy": {"threshold": 0.0}}}
    if shares is not None:
        book["capital"]["n20"]["deductions_fixed_share"], book["capital"]["n11"]["deductions_fixed_share"] = shares
    return {"B": book, "A": {"AT1": inp["at1"]}, "rwa0": inp["rwa0"] if rwa0 is None else rwa0,
            "ded": cm.c_deduction_parts(book)}


def example_row(ctx: dict, inp: dict, which: str, *, quarterly: bool = False) -> dict:
    """Строка примера (anchor или quarter) рабочей функцией счёта норматива: годовой ветви (_c_capital) или
    квартального прохода (_c_quarter_capital). Неаудированная прибыль — прибыль квартала строки: отсечка аудита
    стоит в каждом квартале."""
    line = inp[which]
    y, h = EXAMPLE_ANCHOR if which == "anchor" else EXAMPLE_NEXT
    profit = {(y, h): line["e"]}
    if quarterly:
        cap = cm._c_quarter_capital(ctx, EXAMPLE_SCENARIO, y, h, line["reserve"], profit)(line["bv"], line["dpreg"],
                                                                                         line["rwa"])
    else:
        cap = cm._c_capital(ctx, EXAMPLE_SCENARIO, y, h, line["bv"], line["dpreg"], line["reserve"], line["rwa"],
                            profit)
    return {**cap, "rwa": line["rwa"], "dpreg": line["dpreg"],
            "bvreg": line["bv"] + line["dpreg"] - (1.0 - inp["fvoci_recognition"]) * line["reserve"]}


EXAMPLE_BOOKS = {"with_share": lambda inp: (inp["eta20"], inp["eta11"]), "without_keys": lambda inp: None,
                 "share_one": lambda inp: (1.0, 1.0)}


@pytest.mark.tact
@pytest.mark.parametrize("quarterly", [False, True], ids=["годовая ветвь", "квартальный проход"])
def test_appendix_f_rows(quarterly):
    """F.1: вычеты, капитал и нормативы строки якоря и строки квартала (RWA × 1,5) — с долей 0,6, без ключей и при
    доле, равной единице; строка якоря от доли не зависит; ключи, равные нулю, — строка без ключей бит в бит."""
    doc = example()
    inp = doc["inputs"]
    parts = example_ctx(inp, (inp["eta20"], inp["eta11"]))["ded"]
    for mine, theirs in (((cm.NORM_TOTAL, "fix"), "dfix20"), ((cm.NORM_TOTAL, "grow"), "dgrow20"),
                         ((cm.NORM_BASE, "fix"), "dfix11"), ((cm.NORM_BASE, "grow"), "dgrow11")):
        close(parts[mine[0]][mine[1]], doc["parts"][theirs], theirs)
    for name, shares in EXAMPLE_BOOKS.items():
        ctx = example_ctx(inp, shares(inp))
        for which in ("anchor", "quarter"):
            row = example_row(ctx, inp, which, quarterly=quarterly)
            for field, want in doc[name][which].items():
                close(row[field], want, f"{name}.{which}.{field}")
    # строка якоря: вычет равен ключу при любой доле
    for eta in (0.0, 0.25, inp["eta20"], 1.0):
        row = example_row(example_ctx(inp, (eta, eta)), inp, "anchor", quarterly=quarterly)
        close(row["ded20"], inp["ded20_0"], "якорь: Ded20", EXACT)
        close(row["ded11"], inp["ded11_0"], "якорь: Ded11", EXACT)
    # ключи, равные нулю, — строка книги без ключей бит в бит
    zero, bare = example_ctx(inp, (0.0, 0.0)), example_ctx(inp, None)
    assert zero["ded"] is not None and bare["ded"] is None
    for which in ("anchor", "quarter"):
        assert example_row(zero, inp, which, quarterly=quarterly) == example_row(bare, inp, which, quarterly=quarterly)
    # капитал выше, чем без ключей, на η × Ded_0 × (RWA / RWA_0 − 1), норматив — на η × Ded_0 × (1 / RWA_0 − 1 / RWA)
    shared = example_row(example_ctx(inp, (inp["eta20"], inp["eta11"])), inp, "quarter", quarterly=quarterly)
    plain = example_row(bare, inp, "quarter", quarterly=quarterly)
    rwa, rwa0 = inp["quarter"]["rwa"], inp["rwa0"]
    for cap, norm, eta, ded in (("k20", "n20", inp["eta20"], inp["ded20_0"]),
                                ("k11", "n11", inp["eta11"], inp["ded11_0"])):
        close(shared[cap] - plain[cap], eta * ded * (rwa / rwa0 - 1.0), f"{cap}: слагаемое доли")
        close(shared[norm] - plain[norm], eta * ded * (1.0 / rwa0 - 1.0 / rwa), f"{norm}: слагаемое доли")


@pytest.mark.tact
def test_appendix_f_terminal_and_bridge():
    """F.2: слагаемые избытка капитала терминала (строка квартала — конец сетки) и мост Н20.0 от якоря до строки
    квартала — с долей, без ключей и при доле, равной единице; тождество моста «начало + сумма долей = конец»."""
    doc = example()
    inp = doc["inputs"]
    for name, shares in EXAMPLE_BOOKS.items():
        ctx = example_ctx(inp, shares(inp))
        first, last = example_row(ctx, inp, "anchor"), example_row(ctx, inp, "quarter")
        if name in doc["terminal"]:
            got = cm.c_terminal_excess(last, inp["excess_capital_multiple"])
            for field, want in doc["terminal"][name].items():
                close(got[field], want, f"terminal.{name}.{field}")
        bridge = cm.c_bridge_lines([(1.0, first, last)])
        want = doc["bridge"][name]
        for got, field in ((bridge["start"], "start"), (bridge["end"], "end"),
                           (bridge["deductions"]["amount"], "deductions_amount"),
                           (bridge["deductions"]["pp"], "deductions_pp"), (bridge["rwa_growth"]["pp"], "rwa_growth_pp"),
                           (bridge["rest"]["amount"], "rest_amount"), (bridge["rest"]["pp"], "rest_pp")):
            close(got, want[field], f"bridge.{name}.{field}")
        close(bridge["start"] + bridge["deductions"]["pp"] + bridge["rwa_growth"]["pp"] + bridge["rest"]["pp"],
              bridge["end"], f"bridge.{name}: тождество", EXACT)
        close(bridge["end"], last["n20"], f"bridge.{name}: конец — норматив строки", EXACT)
    # слагаемые X_T выше, чем без ключей, на η × Ded_0 × (RWA_Q / RWA_0 − 1)
    t = doc["terminal"]
    grow = inp["quarter"]["rwa"] / inp["rwa0"] - 1.0
    close(t["with_share"]["x20"] - t["without_keys"]["x20"], inp["eta20"] * inp["ded20_0"] * grow, "x20")
    close(t["with_share"]["x11"] - t["without_keys"]["x11"], inp["eta11"] * inp["ded11_0"] * grow, "x11")
    # избыток — меньшее из двух слагаемых и с множителем книги: в примере связывает Н20.0; при требовании Н20.1
    # на 1,5 п.п. выше связывает Н20.1 (вход теста)
    last = example_row(example_ctx(inp, (inp["eta20"], inp["eta11"])), inp, "quarter")
    tight = cm.c_terminal_excess({**last, "req11": last["req11"] + 0.015}, 0.5)
    close(tight["x11"], t["with_share"]["x11"] - 0.015 * inp["quarter"]["rwa"], "x11 при требовании выше")
    assert tight["x11"] < tight["x20"]
    close(tight["x_t"], 0.5 * tight["x11"], "X_T — меньшее слагаемое с множителем")
    close(cm.c_terminal_excess(last, 0.5)["x_t"], 0.5 * t["with_share"]["x_t"], "X_T с множителем")
    # при доле, равной единице, сумма строки вычетов — ровно ноль
    one = example_ctx(inp, (1.0, 1.0))
    assert cm.c_bridge_lines([(1.0, example_row(one, inp, "anchor"), example_row(one, inp, "quarter"))])[
        "deductions"]["amount"] == 0.0


@pytest.mark.tact
def test_appendix_f_deduction_of_the_reanchored_book():
    """F.2, перенос якоря: саму запись долей исполняет инструмент перезаякоривания, не контрольная модель. Здесь —
    только формула вычета на книгах примера после переноса (доли — входы примера): книга нового якоря с суммой в
    рублях, сохранённой переносом, даёт в следующем квартале тот же вычет, что прежняя книга; доля, оставленная
    прежним числом, — другой; запись со слагаемым якоря в поправке (свойство 7) — тот же путь норматива."""
    doc = example()
    inp, want = doc["inputs"], doc["reanchor"]
    old = example_ctx(inp, (inp["eta20"], inp["eta11"]))["ded"][cm.NORM_TOTAL]
    rwa1, rwa2 = inp["quarter"]["rwa"], want["rwa_next"]
    close(rwa2, rwa1 * inp["reanchor"]["rwa_next_ratio"], "RWA следующего квартала")
    ded1 = cm.c_deduction_at(old, rwa1 / inp["rwa0"])                    # вычет нового якоря — строка квартала
    close(old["fix"], want["fix20"], "сумма в рублях")
    close(cm.c_deduction_at(old, rwa2 / inp["rwa0"]), want["ded20_next_old_book"], "прежняя книга")

    def part(level: float, eta: float) -> dict:
        book = {"capital": {"n20": {"deductions_anchor": level, "deductions_fixed_share": eta},
                            "n11": {"deductions_anchor": level, "deductions_fixed_share": eta}}}
        return cm.c_deduction_parts(book)[cm.NORM_TOTAL]

    moved = part(ded1, want["eta20_new"])
    close(moved["fix"], old["fix"], "сумма в рублях после переноса")
    close(cm.c_deduction_at(moved, rwa2 / rwa1), want["ded20_next_new_book"], "книга нового якоря")
    kept = cm.c_deduction_at(part(ded1, inp["eta20"]), rwa2 / rwa1)
    close(kept, want["ded20_next_if_share_kept"], "доля прежним числом")
    close(kept - want["ded20_next_new_book"], want["mechanics_if_share_kept"], "механика при доле прежним числом")
    # другая запись того же якоря: слагаемое Δ стоит в поправке, а не в вычете; путь норматива — тот же
    alt = want["alt"]
    other = part(alt["ded20_anchor"], alt["eta20"])
    close(alt["ded20_anchor"], ded1 - alt["delta"], "вычет якоря другой записи")
    close(alt["gap20"], -alt["delta"] / rwa1, "поправка другой записи")
    close(other["fix"], old["fix"], "сумма в рублях другой записи")
    close(cm.c_deduction_at(other, rwa2 / rwa1), alt["ded20_next"], "вычет другой записи")
    close((want["ded20_next_new_book"] - alt["ded20_next"]) / rwa2 + alt["gap20"], 0.0, "путь норматива тот же")


# ============================================================================ свойства на форме образца


@pytest.fixture(scope="module")
def inputs():
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8")), cm.c_facts_bundle(FIXTURE / "facts")


@pytest.fixture(scope="module")
def plain(inputs):
    """Форма образца как есть: книга без ключей доли."""
    return cm.c_control_run(*inputs)


@pytest.fixture(scope="module")
def shared(inputs):
    """Форма образца с долями вычета якоря — разными у двух нормативов."""
    book, facts = inputs
    return cm.c_control_run(with_shares(book, ETA20, ETA11), facts)


@pytest.fixture(scope="module")
def flat(inputs):
    """Книга без выплаты (путь капитала от нормативов не зависит): без ключей и с долями."""
    book, facts = inputs
    still = with_keys(book, NO_PAYOUT)
    return cm.c_control_run(still, facts), cm.c_control_run(with_shares(still, ETA20, ETA11), facts)


@pytest.mark.tact
def test_no_keys_and_zero_shares_are_the_sample_branch(inputs, plain):
    """Без ключей — прежняя строка образца; ключи, равные нулю (числом и целым), — ряды, оценка и точка книги без
    ключей бит в бит; узла долей у книги без ключей нет, у книги с нулевыми ключами он есть."""
    book, facts = inputs
    assert plain["ctx"]["ded"] is None and "deduction_shares" not in plain
    for zero in (0.0, 0):
        same = cm.c_control_run(with_shares(book, zero, zero), facts)
        assert values_of(same) == values_of(plain)
        assert [c["anchor_capital"] for c in same["cells"]] == [c["anchor_capital"] for c in plain["cells"]]
        assert same["ctx"]["ded"] is not None and same["deduction_shares"]["parts"][cm.NORM_TOTAL]["fix"] == 0.0


@pytest.mark.tact
def test_null_share_key_is_refused(inputs):
    """М§4.11, §17, прил. A № 21 (находка 3 третьей проверки): ключ доли со значением null — отказ входа, а не «ключа
    нет»: у обоих ключей, у одного при числе у другого и у одного при отсутствии другого; «постоянной части нет»
    пишется нулём. Книга без обоих ключей — прежняя строка."""
    book, facts = inputs
    for pair in ((None, None), (None, 0.5), (0.5, None), (None, 0.0), (0.0, None)):
        with pytest.raises(cm.ControlInputError, match="null"):
            cm.c_control_context(with_shares(book, *pair), facts)
    for name in (SHARE20, SHARE11):
        with pytest.raises(cm.ControlInputError, match="null"):
            cm.c_control_context(put(book, name, None), facts)
    assert cm.c_control_context(book, facts)["ded"] is None
    assert cm.c_control_context(with_shares(book, 0.0, 0.0), facts)["ded"] is not None


@pytest.mark.tact
def test_bad_share_keys_fail_loudly(inputs):
    """Ограничение № 21 приложения A: ключ доли у одного норматива без ключа у другого и доля, которая не число
    от 0 до 1 включительно, — отказ книги; ноль и единица допустимы; слова anchor у ключа нет."""
    book, facts = inputs
    for name in (SHARE20, SHARE11):
        with pytest.raises(cm.ControlInputError, match="у одного норматива"):
            cm.c_control_context(put(book, name, 0.5), facts)
    for bad in (-0.01, 1.01, 2, -1, "0.5", True, False, float("nan"), float("inf"), [0.5], {"LT": 0.5}):
        for pair in ((bad, 0.5), (0.5, bad)):
            with pytest.raises(cm.ControlInputError, match="от 0 до 1"):
                cm.c_control_context(with_shares(book, *pair), facts)
    for pair in (("anchor", 0.5), (0.5, "anchor")):         # слова anchor у ключа доли нет: формулы вывода нет
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(with_shares(book, *pair), facts)
    for pair in ((0.0, 1.0), (1.0, 0.0), (1, 0), (0.5, 0.5)):
        assert cm.c_control_context(with_shares(book, *pair), facts)["ded"] is not None


@pytest.mark.tact
def test_deduction_row_follows_the_formula(shared, plain):
    """Свойства 1–2 (М§4.11): в каждой строке каждой клетки вычет каждого норматива равен
    Ded_0 × [(1 − η) × RWA / RWA_0 + η] по RWA строки, а K20 и K11, пересчитанные тестом по рядам клетки (капитал,
    объявленный и не вычтенный дивиденд, фонд, инструменты, неаудированная прибыль), совпадают с её рядами; в
    строке якоря вычет равен ключу, оба норматива — те же, что у книги без ключей; аддитивное слагаемое норматива
    N − K / RWA (поправка минус вычет сценария) от долей не зависит."""
    ctx = shared["ctx"]
    B, rwa0 = ctx["B"], ctx["rwa0"]
    d20, d11 = cm.c_bnum(B, DED20), cm.c_bnum(B, DED11)
    f = cm.c_bnum(B, "capital.n20.fvoci_recognition")
    y0, qa = ctx["anchor"]
    assert shared["deduction_shares"]["parts"][cm.NORM_TOTAL] == {"share": ETA20, "fix": ETA20 * d20,
                                                                  "grow": (1.0 - ETA20) * d20}
    for c, p in zip(shared["cells"], plain["cells"]):
        first = c["anchor_capital"]
        assert first["ded20"] == pytest.approx(d20, rel=EXACT) and first["ded11"] == pytest.approx(d11, rel=EXACT)
        for name in ("n20", "n11", "n11_star", "k20", "k11"):
            assert first[name] == pytest.approx(p["anchor_capital"][name], rel=EXACT, abs=EXACT)
        for period, r, base in zip(ctx["periods"], c["rows"], p["rows"]):
            grow = r["rwa"] / rwa0
            assert r["ded20"] == pytest.approx(d20 * ((1.0 - ETA20) * grow + ETA20), rel=EXACT)
            assert r["ded11"] == pytest.approx(d11 * ((1.0 - ETA11) * grow + ETA11), rel=EXACT)
            own = r["bv"] + r["dpreg"] - (1.0 - f) * r["R"]
            t2 = cm.c_traj_at(cm.c_bget(B, "capital.n20.t2"), period["year"], period["quarters"][-1])
            assert r["k20"] == pytest.approx(own - r["ded20"] + ctx["A"]["AT1"] + t2, rel=EXACT)
            assert r["k11"] == pytest.approx(own - max(r["e_unaudited"], 0.0) - r["ded11"], rel=EXACT)
            for norm, cap in (("n20", "k20"), ("n11", "k11")):
                assert r[norm] - r[cap] / r["rwa"] == pytest.approx(base[norm] - base[cap] / base["rwa"], abs=EXACT)
    # RWA формы образца растут: вычет с долей ниже вычета без ключей на конце сетки, норматив выше
    assert all(c["rows"][-1]["rwa"] > rwa0 and c["rows"][-1]["ded20"] < d20 * c["rows"][-1]["rwa"] / rwa0
               for c in shared["cells"])


# вне такта сервера: свойство проверяется лишними прогонами сетки формы образца — они идут в CI
def test_share_adds_exactly_its_term_where_capital_ignores_the_ratios(flat):
    """Свойство 5: на книге без выплаты путь капитала и RWA от нормативов не зависит — капитал каждого норматива
    выше, чем без ключей, ровно на η × Ded_0 × (RWA / RWA_0 − 1), норматив — на η × Ded_0 × (1 / RWA_0 − 1 / RWA),
    а избыток капитала терминала — X_T = множитель × min_j [X⁰_j + η_j × Ded_j,0 × (RWA_Q / RWA_0 − 1)], где X⁰_j —
    слагаемые минимума той же книги без ключей."""
    bare, keyed = flat
    ctx = keyed["ctx"]
    B, rwa0 = ctx["B"], ctx["rwa0"]
    add = {"20": ETA20 * cm.c_bnum(B, DED20), "11": ETA11 * cm.c_bnum(B, DED11)}
    mult = cm.c_bnum(B, "valuation.terminal.excess_capital_multiple")
    for a, b in zip(bare["cells"], keyed["cells"]):
        for ra, rb in zip(a["rows"], b["rows"]):
            assert (ra["bv"], ra["rwa"], ra["div"], ra["pbt"]) == (rb["bv"], rb["rwa"], rb["div"], rb["pbt"])
            for j in ("20", "11"):
                assert rb[f"k{j}"] - ra[f"k{j}"] == pytest.approx(add[j] * (rb["rwa"] / rwa0 - 1.0), rel=1e-9, abs=1e-9)
                assert rb[f"n{j}"] - ra[f"n{j}"] == pytest.approx(add[j] * (1.0 / rwa0 - 1.0 / rb["rwa"]), abs=EXACT)
        last, grow = b["rows"][-1], b["rows"][-1]["rwa"] / rwa0 - 1.0
        base = cm.c_terminal_excess(a["rows"][-1], mult)
        terms = {j: base[f"x{j}"] + add[j] * grow for j in ("20", "11")}
        assert b["x_t"] == pytest.approx(mult * min(terms.values()), rel=1e-9, abs=1e-9)
        assert cm.c_terminal_excess(last, mult)["x_t"] == b["x_t"]
        assert a["rows"][-1]["bv"] == b["rows"][-1]["bv"] and b["x_t"] > a["x_t"] and b["v_ri"] != a["v_ri"]


# вне такта сервера: свойство проверяется лишними прогонами сетки формы образца — они идут в CI
def test_share_of_one_ratio_leaves_the_other_alone(inputs, flat):
    """Свойство 6: доля одного норматива не меняет ряды вычета, капитала и норматива другого (книга без выплаты:
    путь капитала общий)."""
    book, facts = inputs
    bare, _ = flat
    still = with_keys(book, NO_PAYOUT)
    only20 = cm.c_control_run(with_shares(still, ETA20, 0.0), facts)
    only11 = cm.c_control_run(with_shares(still, 0.0, ETA11), facts)
    assert rows_of(only20, ("ded11", "k11", "n11", "n11_star")) == rows_of(bare, ("ded11", "k11", "n11", "n11_star"))
    assert rows_of(only11, ("ded20", "k20", "n20")) == rows_of(bare, ("ded20", "k20", "n20"))
    assert rows_of(only20, ("ded20",)) != rows_of(bare, ("ded20",))
    assert rows_of(only11, ("ded11",)) != rows_of(bare, ("ded11",))
    # и у одной точки счёта норматива: постоянная часть Н20.1 — от вычета якоря Н20.1, не Н20.0
    parts = only11["ctx"]["ded"]
    assert parts[cm.NORM_BASE]["fix"] == ETA11 * cm.c_bnum(only11["ctx"]["B"], DED11)
    assert parts[cm.NORM_TOTAL] == {"share": 0.0, "fix": 0.0, "grow": cm.c_bnum(only11["ctx"]["B"], DED20)}


@pytest.mark.tact
def test_share_is_not_a_relief_below_the_anchor(shared, plain):
    """Свойство 8: в построенном квартале с RWA ниже якоря норматив книги с долей ниже норматива книги без ключей
    на том же пути — постоянный вычет не уменьшается вместе с RWA; выше якоря — наоборот; на якоре — равны."""
    ctx, base = shared["ctx"], plain["ctx"]
    y0, qa = ctx["anchor"]
    st = cm._c_start_state(ctx)
    scenario = shared["cells"][0]["scenario"]
    d20, d11 = cm.c_bnum(ctx["B"], DED20), cm.c_bnum(ctx["B"], DED11)
    for scale in (0.8, 0.95, 1.0, 1.3):
        rwa = scale * ctx["rwa0"]
        args = (scenario, y0, qa, ctx["A"]["BV"], 0.0, ctx["A"]["R0"], rwa, st["ni_q"])
        mine, theirs = cm._c_capital(ctx, *args), cm._c_capital(base, *args)
        for norm, eta, ded in (("n20", ETA20, d20), ("n11", ETA11, d11)):
            gap = mine[norm] - theirs[norm]
            assert gap == pytest.approx(eta * ded * (1.0 / ctx["rwa0"] - 1.0 / rwa), abs=EXACT)
            assert (gap < 0.0) if scale < 1.0 else (gap > 0.0) if scale > 1.0 else abs(gap) <= EXACT


# вне такта сервера: свойство проверяется лишними прогонами сетки формы образца — они идут в CI
def test_shares_of_one_keep_the_deduction_flat(inputs, plain):
    """Свойство 4: при долях, равных единице, вычет каждого норматива — сумма якоря во всех строках всех клеток,
    бит в бит; строка вычетов моста несёт ноль рублей."""
    book, facts = inputs
    one = cm.c_control_run(with_shares(book, 1.0, 1.0), facts)
    d20, d11 = cm.c_bnum(one["ctx"]["B"], DED20), cm.c_bnum(one["ctx"]["B"], DED11)
    for c in one["cells"]:
        assert {r["ded20"] for r in c["rows"]} | {c["anchor_capital"]["ded20"]} == {d20}
        assert {r["ded11"] for r in c["rows"]} | {c["anchor_capital"]["ded11"]} == {d11}
    for year in one["years"]:
        assert cm.c_capital_bridge(one, year)["deductions"]["amount"] == pytest.approx(0.0, abs=1e-9)
    assert any(r["ded20"] > d20 for c in plain["cells"] for r in c["rows"])


def test_shares_of_one_keep_the_deduction_flat_under_the_regime_multiplier():
    """Свойство 4 на квартальном проходе капитала с множителем плотности режима (фикстура core_t): при долях,
    равных единице, вычет постоянен в каждом квартале каждой клетки — и в клетке режима, где множитель снижает RWA;
    с долями между нулём и единицей вычет квартала равен формуле от RWA квартала, а капитал квартала пересчитывается
    по нему."""
    book = json.loads((FIXTURE_T / "book.json").read_text(encoding="utf-8"))
    facts = cm.c_facts_bundle(FIXTURE_T / "facts")
    assert cm.c_is_quarterly(book) and any(book["regimes"][r].get("rwa_density_mult") for r in book["regimes"]["ids"])
    one = cm.c_control_run(with_shares(book, 1.0, 1.0), facts)
    d20, d11 = cm.c_bnum(one["ctx"]["B"], DED20), cm.c_bnum(one["ctx"]["B"], DED11)
    lower = 0
    for c in one["cells"]:
        for r in c["rows"]:
            assert {x["ded20"] for x in r["quarters"]} | {r["ded20"]} == {d20}
            assert {x["ded11"] for x in r["quarters"]} | {r["ded11"]} == {d11}
            lower += sum(x["rwa"] < one["ctx"]["rwa0"] for x in r["quarters"])
    assert lower, "вход теста: в клетках режима с множителем плотности есть кварталы с RWA ниже якоря"
    part = cm.c_control_run(with_shares(book, ETA20, ETA11), facts)
    rwa0 = part["ctx"]["rwa0"]
    for c in part["cells"]:
        for r in c["rows"]:
            for x in r["quarters"]:
                grow = x["rwa"] / rwa0
                assert x["ded20"] == pytest.approx(d20 * ((1.0 - ETA20) * grow + ETA20), rel=EXACT)
                assert x["ded11"] == pytest.approx(d11 * ((1.0 - ETA11) * grow + ETA11), rel=EXACT)
                # отчётные нормативы квартала — капитал с этим вычетом; аддитивное слагаемое общее у двух книг
                assert x["n20"] - x["k20"] / x["rwa"] == pytest.approx(
                    cm.c_bnum(part["ctx"]["B"], "capital.n20.gap_pp") - cm.c_traj_at(cm.c_bget(
                        part["ctx"]["B"], f"capital.reg_scenarios.{c['scenario']}.deduction_pp.n20_0"),
                        *cm.c_qper(part["ctx"]["anchor"], x["q"])), abs=EXACT)
    # ключи, равные нулю, — прежние числа и на квартальном проходе
    bare = cm.c_control_run(book, facts)
    zero = cm.c_control_run(with_shares(book, 0.0, 0.0), facts)
    assert values_of(zero) == values_of(bare)
    assert [[x["n20"] for r in c["rows"] for x in r["quarters"]] for c in zero["cells"]] == [
        [x["n20"] for r in c["rows"] for x in r["quarters"]] for c in bare["cells"]]


def shifted(book: dict, ctx: dict, delta: float, eta20, eta11) -> dict:
    """Книга, у которой слагаемое якоря Δ перенесено из вычета Н20.0 и Н20.1 в поправки: вычет якоря больше на Δ,
    поправка — на Δ / RWA_0; доли — заданные."""
    rwa0 = ctx["rwa0"]
    return with_keys(book, {DED20: cm.c_bnum(ctx["B"], DED20) + delta, DED11: cm.c_bnum(ctx["B"], DED11) + delta,
                            "capital.n20.gap_pp": cm.c_bnum(ctx["B"], "capital.n20.gap_pp") + delta / rwa0,
                            "capital.n11.gap_pp": cm.c_bnum(ctx["B"], "capital.n11.gap_pp") + delta / rwa0,
                            SHARE20: eta20, SHARE11: eta11})


# вне такта сервера: свойство проверяется лишними прогонами сетки формы образца — они идут в CI
@pytest.mark.parametrize("delta", [150.0, -90.0], ids=["вычет больше", "вычет меньше"])
def test_anchor_term_moves_between_deduction_and_adjustment_with_the_amount_kept(inputs, shared, delta):
    """Свойство 7: сдвиг вычета якоря на Δ вместе с поправкой на Δ / RWA_0 и долей η × Ded_0 / (Ded_0 + Δ) —
    сумма в рублях прежняя — оставляет нормативы, дивиденды и оценку прежними; тот же сдвиг при прежней доле
    сдвигает норматив строки на η × Δ × (1 / RWA_0 − 1 / RWA): суждением служит сумма в рублях, а не доля."""
    book, facts = inputs
    ctx = shared["ctx"]
    d20, d11 = cm.c_bnum(ctx["B"], DED20), cm.c_bnum(ctx["B"], DED11)
    kept = cm.c_control_run(shifted(book, ctx, delta, ETA20 * d20 / (d20 + delta), ETA11 * d11 / (d11 + delta)), facts)
    assert kept["ctx"]["ded"][cm.NORM_TOTAL]["fix"] == pytest.approx(ETA20 * d20, rel=EXACT)
    for a, b in zip(shared["cells"], kept["cells"]):
        for ra, rb in zip(a["rows"], b["rows"]):
            for name in ("n20", "n11", "n11_star"):
                assert rb[name] == pytest.approx(ra[name], abs=1e-11), (key(a), name)
            assert rb["div"] == pytest.approx(ra["div"], rel=1e-9, abs=1e-6)
        assert b["v_ri"] == pytest.approx(a["v_ri"], rel=1e-9)
    assert kept["point"] == pytest.approx(shared["point"], rel=1e-9)
    # прежняя доля на книге без выплаты (путь общий): норматив сдвинут на η × Δ × (1 / RWA_0 − 1 / RWA)
    still = with_keys(book, NO_PAYOUT)
    base = cm.c_control_run(with_shares(still, ETA20, ETA11), facts)
    same_share = cm.c_control_run(shifted(still, ctx, delta, ETA20, ETA11), facts)
    moved = 0.0
    for a, b in zip(base["cells"], same_share["cells"]):
        for ra, rb in zip(a["rows"], b["rows"]):
            assert rb["rwa"] == ra["rwa"]
            for name, eta in (("n20", ETA20), ("n11", ETA11)):
                want = eta * delta * (1.0 / ctx["rwa0"] - 1.0 / rb["rwa"])
                assert rb[name] - ra[name] == pytest.approx(want, abs=1e-11)
                moved = max(moved, abs(want))
    assert moved > 1e-4, "вход теста: сдвиг норматива различим"


@pytest.mark.tact
def test_bridge_deduction_line_carries_the_growing_part(shared, plain):
    """Мост Н20.0 смеси точки (М§4.11): сумма строки вычетов равна −(E[Ded20_e] − Ded20_0) и
    −Dgrow_20 × (E[RWA_e] / RWA_0 − 1); у книги без ключей — −Ded20_0 × (E[RWA_e] / RWA_0 − 1); тождество «начало +
    сумма долей = конец»; начало — норматив якоря, конец — норматив смеси в определении движка."""
    for res, grow_part in ((shared, shared["ctx"]["ded"][cm.NORM_TOTAL]["grow"]),
                           (plain, cm.c_bnum(plain["ctx"]["B"], DED20))):
        ctx, mass = res["ctx"], cm.c_point_mass(res)
        assert sum(mass.values()) == pytest.approx(1.0, rel=1e-9)
        for i, year in enumerate(res["years"]):
            br = cm.c_capital_bridge(res, year)
            ded = sum(mass[key(c)] * c["rows"][i]["ded20"] for c in res["cells"])
            rwa = sum(mass[key(c)] * c["rows"][i]["rwa"] for c in res["cells"])
            k20 = sum(mass[key(c)] * c["rows"][i]["k20"] for c in res["cells"])
            add = sum(mass[key(c)] * (c["rows"][i]["n20"] - c["rows"][i]["k20"] / c["rows"][i]["rwa"])
                      for c in res["cells"])
            first = res["cells"][0]["anchor_capital"]
            assert br["deductions"]["amount"] == pytest.approx(-(ded - first["ded20"]), rel=1e-9, abs=1e-9)
            assert br["deductions"]["amount"] == pytest.approx(-grow_part * (rwa / ctx["rwa0"] - 1.0), rel=1e-9,
                                                               abs=1e-9)
            assert br["end"] == pytest.approx(k20 / rwa + add, rel=EXACT)
            assert br["start"] + br["deductions"]["pp"] + br["rwa_growth"]["pp"] + br["rest"]["pp"] == pytest.approx(
                br["end"], abs=EXACT)
            assert br["rwa_growth"]["pp"] == pytest.approx(first["k20"] * (1.0 / rwa - 1.0 / ctx["rwa0"]), rel=1e-9)
        start = sum(mass[key(c)] * c["anchor_capital"]["n20"] for c in res["cells"])
        assert cm.c_capital_bridge(res)["start"] == pytest.approx(start, abs=EXACT)
        assert cm.c_capital_bridge(res)["year"] == ctx["periods"][ctx["clock"]["p0"]]["year"]
    assert shared["deduction_shares"]["bridge"] == cm.c_capital_bridge(shared)
    last = shared["years"][-1]
    assert abs(cm.c_capital_bridge(shared, last)["deductions"]["amount"]) < abs(
        cm.c_capital_bridge(plain, last)["deductions"]["amount"])


# вне такта сервера: свойство проверяется лишними прогонами сетки формы образца — они идут в CI
def test_recap_money_grows_only_the_growing_part(inputs):
    """Докапитализация у книги с долями (М§4.14.2, §4.14.5, свойство 3): деньги взноса несут вес риска, и за ними
    растёт только растущая часть вычета — капитал норматива в году взноса выше, чем у того же шага без взноса, на
    прирост собственных средств BV + DPreg − (1 − признание) × R за вычетом Dgrow_j × (RWA′ − RWA) / RWA_0; при
    долях, равных единице, — ровно на прирост собственных средств; остаток недостатка после взноса — в допуске
    инварианта «взнос закрывает разрыв»."""
    book, facts = inputs
    short = with_keys(book, SHORT)
    keep = 1.0 - float(book["capital"]["n20"]["fvoci_recognition"])
    seen = 0
    for eta20, eta11 in ((ETA20, ETA11), (1.0, 1.0)):
        res = cm.c_control_run(with_shares(short, eta20, eta11), facts)
        ctx = res["ctx"]
        grow = {"k20": ctx["ded"][cm.NORM_TOTAL]["grow"], "k11": ctx["ded"][cm.NORM_BASE]["grow"]}
        for cell in res["cells"]:
            for year, rest in cm.c_recap_left(ctx, cell).items():
                assert rest["left"] <= LEFT_SHARE * cell["recaps"][year]["rec"], (key(cell), year)
            if not cell["recapitalization"]:
                continue
            ident = {"world": cell["world"], "regime": cell["regime"], "scenario": cell["scenario"]}
            year = next(y for y, x in sorted(cell["recaps"].items()) if x["rec"] > 0.0)
            made = cell["recaps"][year]
            st = cm._c_start_state(ctx)
            st["rwa"] = ctx["rwa0"]
            for i, p in enumerate(ctx["periods"]):
                if p["year"] == year + 1:
                    break
                st, _ = cm._c_period(ctx, ident, st, i, cell["rows"][i]["div"], rec=cell["rows"][i]["rec"])
            without = cm._c_period(ctx, ident, st, i, made["div"])[1]
            with_it = cm._c_period(ctx, ident, st, i, made["div"], rec=made["rec"])[1]
            assert with_it["rwa"] > without["rwa"]         # деньги взноса несут вес риска
            more_rwa = (with_it["rwa"] - without["rwa"]) / ctx["rwa0"]
            more_own = ((with_it["bv"] + with_it["dpreg"] - keep * with_it["R"])
                        - (without["bv"] + without["dpreg"] - keep * without["R"]))
            assert more_own == pytest.approx(made["rec"], rel=0.05)     # взнос и доход на него за остаток года
            for name in ("k20", "k11"):
                # неаудированная прибыль конца года у двух шагов разная (доход на взнос) — сравнивается капитал с ней
                held = (max(with_it["e_unaudited"], 0.0) - max(without["e_unaudited"], 0.0)) if name == "k11" else 0.0
                got = with_it[name] - without[name] + held
                assert got == pytest.approx(more_own - grow[name] * more_rwa, rel=1e-9, abs=1e-9)
                if eta20 == 1.0:
                    assert grow[name] == 0.0 and got == pytest.approx(more_own, rel=1e-9)
                else:
                    assert got < more_own
            seen += 1
    assert seen


# ============================================================================ сверка с ядром (в момент теста)


def _core_run(book: dict, facts_dir):
    try:
        book_mod, grid_mod = importlib.import_module("model.book"), importlib.import_module("model.grid")
    except Exception as exc:
        pytest.fail(f"ядро не импортируется ({type(exc).__name__}: {exc})")
    try:
        facts = book_mod.load_facts(facts_dir)
        return grid_mod.run_grid(book_mod.book_from_dict(book, facts=facts), facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу с долями вычета якоря: {type(exc).__name__}: {str(exc)[:500]}")


FORMS = {"shares-0.6-0.35": lambda book: with_shares(book, ETA20, ETA11),
         "shares-0.6-0.6": lambda book: with_shares(book, ETA20, ETA20),
         "shares-one": lambda book: with_shares(book, 1.0, 1.0),
         "shares-zero": lambda book: with_shares(book, 0.0, 0.0),
         "only-n20": lambda book: with_shares(book, ETA20, 0.0),
         "only-n11": lambda book: with_shares(book, 0.0, ETA20),
         "no-payout": lambda book: with_shares(with_keys(book, NO_PAYOUT), ETA20, ETA11),
         "recap": lambda book: with_shares(with_keys(book, SHORT), ETA20, ETA11),
         "recap-q4-window1": lambda book: with_shares(put(with_keys(book, SHORT), "capital.recapitalization", {
             **SHORT["capital.recapitalization"], "decision_quarter": cm.QY, "lookahead_quarters": 1}), ETA20, ETA20),
         "recap-shares-one": lambda book: with_shares(with_keys(book, SHORT), 1.0, 1.0)}


@pytest.mark.ci_only
@pytest.mark.parametrize("form", list(FORMS))
def test_control_matches_core_with_the_fixed_share(inputs, form):
    """Форма образца с долями вычета якоря против ядра (чёрный ящик: запуск и поля результата) — в допусках М§17:
    доли разные и равные у двух нормативов, единица, ноль, доля у одного норматива, книга без выплаты, форма с
    нехваткой капитала и докапитализацией (решение в квартал собрания и в четвёртом квартале). Расхождение —
    находка, а не повод подогнать контрольную модель."""
    book, facts = inputs
    ready = FORMS[form](book)
    run = _core_run(ready, FIXTURE / "facts")
    ctl = cm.c_control_run(ready, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    assert not tcm.exact_match(run, ctl), "V0 слоёв совпали с ядром до 1e-9 — общий код"
    if "recap" in form:
        assert any(r["group"] == "rec" and r["core"] and r["control"] for r in rows), "ни одного взноса у обеих моделей"


@pytest.mark.ci_only
def test_fixed_share_forms_against_core_as_a_black_box(inputs, plain, shared):
    """Ядро — чёрный ящик: ключи, равные нулю, дают у ядра оценку книги без ключей; доля сдвигает точку у двух
    моделей в одну сторону и на близкую величину; книгу с одним ключом и с долей вне границ отвергают обе."""
    book, facts = inputs
    bare = _core_run(book, FIXTURE / "facts")
    zero = _core_run(with_shares(book, 0.0, 0.0), FIXTURE / "facts")
    assert (zero.point, zero.low, zero.high) == (bare.point, bare.low, bare.high)
    assert [c.v_ri for c in zero.cells] == [c.v_ri for c in bare.cells]
    keyed = _core_run(with_shares(book, ETA20, ETA11), FIXTURE / "facts")
    mine, theirs = shared["point"] - plain["point"], keyed.point - bare.point
    assert mine * theirs > 0.0 and abs(mine - theirs) <= tcm.TOL_VALUE * abs(bare.point)
    book_mod = importlib.import_module("model.book")
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    for bad in (put(book, SHARE20, 0.5), put(book, SHARE11, 0.5), with_shares(book, 1.5, 0.5),
                with_shares(book, 0.5, -0.1)):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(bad, facts)
        with pytest.raises(Exception) as refused:
            book_mod.book_from_dict(bad, facts=core_facts)
        assert type(refused.value).__name__ == "BookError", refused.value


@pytest.mark.ci_only
@pytest.mark.parametrize("pair", [(ETA20, ETA11), (1.0, 1.0)], ids=["доли", "единица"])
def test_control_matches_core_with_the_fixed_share_on_the_quarterly_form(pair):
    """Фикстура core_t (квартальный календарь, рост ограничен капиталом, множитель плотности режима) с долями
    против ядра — в допусках М§17."""
    book = with_shares(json.loads((FIXTURE_T / "book.json").read_text(encoding="utf-8")), *pair)
    run = _core_run(book, FIXTURE_T / "facts")
    ctl = cm.c_control_run(book, cm.c_facts_bundle(FIXTURE_T / "facts"))
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
