# -*- coding: utf-8 -*-
"""Контрольная модель: докапитализация и пол клетки (docs/MODEL.md §4.14, §6.5–§6.6, §7, §8.2, §17).

* Примеры приложений D и E методики (машинные копии tests/fixtures/core_recap/example.json и example_q4.json):
  контрольная модель подставляет входы примера в свои формулы — решение о взносе по точкам окна (в квартал
  собрания и в четвёртом квартале с окном в один квартал), точку и норматив по правилу «при равенстве», нижнюю
  границу окна, точки и остаток инварианта, оценку обеих форм с терминалом по цене размещения, пол клетки, путь
  акций и DPS с поправкой делителя в знаменателе — и получает его числа до 1e-9 (М§17: аналитический допуск);
  целые и названия — точно.
* Свойства своего счёта на фикстуре формы образца (tests/fixtures/core) с ключами, подставленными тестом:
  «ключа нет — прежняя ветвь» и выключатель в обе стороны; взнос равен недостатку окна, пересчитанному тестом;
  тождество капитала с взносом; взнос закрывает разрыв; год шока отменяет дивиденд, а не взнос; запись реестра;
  квартал собрания на конце сетки; окно, обрезанное концом сетки; окно в одну точку; DDM = RI при любом
  дисконте; оценка при нулевом дисконте выше на цену размывания; рост дисконта оценку не повышает; пол клетки —
  до смеси, до дисконта за управление и без объявленного дивиденда; путь акций и DPS на акции своего года;
  сводка взносов; отказы на ключах вне правил.
* Квартал решения о взносе — ключ книги (М§4.14.1): ключ, равный кварталу собрания, — числа книги без ключа;
  взносы стоят только в кварталах с номером ключа, в году якоря — тоже, в последнем квартале сетки — нет;
  решение после собрания несёт принятый дивиденд, решение до собрания от доли выплаты не зависит, дивиденд
  собрания на взнос не рассчитывает; ступень требования первого квартала закрыта взносом четвёртого; нижняя
  граница окна — отказ книги; норма клетки; книга с четвёртым сценарием требования нулевой вероятности.
* Сверка с ядром (метка ci_only; ядро импортируется только в момент теста) — в допусках М§17, строки взносов,
  цены размывания, пола и пути акций — tests/test_control_model.py (compare_with_core).

Числа подмен — входы тестов, а не допущения: запас менеджмента поднят, чтобы капитала не хватало.
"""

from __future__ import annotations

import copy
import datetime as dt
import importlib
import json
import math

import pytest

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]

FIXTURE = cm.ROOT / "tests" / "fixtures" / "core"
EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_recap" / "example.json"
EXAMPLE_Q4 = cm.ROOT / "tests" / "fixtures" / "core_recap" / "example_q4.json"   # приложение E: решение в 4-м квартале
EXAMPLE_TOL = 1e-9          # примеры приложений D и E: формулы без шага, одно определение (М§17)
PERCENT = 100.0             # нормативы и требования примера записаны в процентах
RECAP = "capital.recapitalization"
FLOOR = "valuation.cell_floor"
# Форма с нехваткой капитала: порог политики снят (условие формы М§4.14), запас менеджмента поднят.
SHORT = {"dividends.policy.threshold": 0.0, "capital.mgmt_buffer.n20_0": 0.03, "capital.mgmt_buffer.n1_1": 0.03}
RULE = {"enabled": True, "price_discount": 0.10, "lookahead_quarters": 3, "min_amount": 30.0}
NEVER = 1e9                 # порог выше любого недостатка: механизм включён, взносов нет
LEFT_SHARE = 0.10           # остаток недостатка после взноса — не больше десятой доли взноса (М§14.1)
AGM_LAST = {"agm_quarter": 4, "reg_deduction_quarter": 4, "payment_quarter": 4, "checkpoints": [4]}


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


def short_book(book: dict, floor=None, **rule) -> dict:
    """Книга формы образца с нехваткой капитала и включённой докапитализацией; rule — подмены полей объекта."""
    out = put(with_keys(book, SHORT), RECAP, {**RULE, **rule})
    return out if floor is None else put(out, FLOOR, floor)


@pytest.fixture(scope="module")
def inputs():
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8")), cm.c_facts_bundle(FIXTURE / "facts")


@pytest.fixture(scope="module")
def plain(inputs):
    """Форма с нехваткой капитала без объекта докапитализации — образец: разрыв копится до терминала."""
    book, facts = inputs
    return cm.c_control_run(with_keys(book, SHORT), facts)


@pytest.fixture(scope="module")
def short(inputs):
    book, facts = inputs
    return cm.c_control_run(short_book(book, floor=0.0), facts)


def _key(c: dict) -> tuple:
    return c["world"], c["regime"], c["scenario"]


def _rows(res: dict) -> list:
    return [(c["bv_v"], c["x_t"], [(r["bv"], r["rwa"], r["pbt"], r["ci"], r["div"], r["n20"], r["n11"]) for r in c["rows"]])
            for c in res["cells"]]


def _values(res: dict) -> list:
    return [(c["v_ri"], c["v_ddm"]) for c in res["cells"]], _rows(res), (res["point"], res["low"], res["high"])


# ============================================================================ пример приложения D


def example(path=EXAMPLE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def example_points(doc: dict, q_r: int, window: int, table: str = "trials") -> list[dict]:
    """Точки пробного прохода решения квартала q_R — первые window + 1 строк таблицы входа (нормативы — доли).
    table — имя таблицы входа: пробные проходы (trials) или строки окончательного расчёта (final, final_late)."""
    lines = doc["input"][table][str(q_r)]
    out = []
    for q in sorted(lines, key=int)[:window + 1]:
        n20, n11, dpreg, rwa, req20, req11 = (float(x) for x in lines[q])
        out.append({"q": int(q), "n20": n20 / PERCENT, "n11": n11 / PERCENT, "dpreg": dpreg, "rwa": rwa,
                    "req20": req20 / PERCENT, "req11": req11 / PERCENT})
    return out


def example_decisions(doc: dict, window: int) -> dict[int, dict]:
    least = float(doc["input"]["min_amount"])
    return {int(q_r): cm.c_recap_shortfall(example_points(doc, int(q_r), window), least)
            for q_r in doc["input"]["trials"]}


def example_calendar(doc: dict) -> tuple[int, int, int, int]:
    """Календарь примера: номер в году первого квартала сетки, квартал собрания, квартал вычета и квартал решения
    о взносе (пример D: сетка с первого квартала, решение — в квартал собрания)."""
    inp = doc["input"]
    agm = int(inp["agm_quarter"])
    return (int(inp.get("first_quarter_in_year", 1)), agm, int(inp["reg_deduction_quarter"]),
            int(inp.get("decision_quarter", agm)))


def example_shares(doc: dict) -> dict:
    """Акции примера: в обращении, база делителя и делитель N_div = N_base × (1 + share_count_adj) (М§8.4)."""
    sh = doc["input"]["shares"]
    n_out = float(sh["n_out"])
    if "n_div" in sh:                                   # пример D: поправки делителя нет
        return {"N_out": n_out, "N_base": float(sh["n_div"]), "N_div": float(sh["n_div"])}
    return {"N_out": n_out, "N_base": float(sh["n_base"]),
            "N_div": float(sh["n_base"]) * (1.0 + float(sh["share_count_adj"]))}


def example_cell(doc: dict, recs: dict[int, float], *, cut: float, q0: int = 1, pbt=None, gov: float = 0.0):
    """Клетка примера на входах приложения D или E в форме контрольной модели: годовые строки (совокупный доход
    по кварталам, дивиденды и взносы с номерами кварталов внутри года, капитал конца года по тождеству М§4.9) —
    у примера E первый период — неполный год якоря; терминал — нормативы, требования и ставки конца сетки;
    дисконт плоский. Дивиденд — в квартал собрания, взнос — в квартал решения о взносе (у примера D — тот же
    квартал). Возвращает (контекст, клетка) с оценкой контрольной модели и путём акций."""
    inp, term = doc["input"], doc["input"]["terminal"]
    k = float(inp["k_quarter"])
    grid = int(inp["Q"])
    first_h, agm, held, asks = example_calendar(doc)
    ci = [float(x) for x in inp["ci"]]
    div = {int(q): float(v) for q, v in inp["div"].items()}
    shares = example_shares(doc)
    periods, start = [], 1
    while start <= grid:                                # периоды — календарные годы; первый может быть неполным
        h0 = (first_h - 1 + start - 1) % cm.QY + 1
        year = (first_h - 1 + start - 1) // cm.QY + (1 if first_h == 1 else 0)
        periods.append({"year": year, "quarters": tuple(range(h0, cm.QY + 1)), "n": cm.QY - h0 + 1,
                        "stub": h0 > 1, "label": str(year), "first": start})
        start += cm.QY - h0 + 1
    closed = q0 - 1
    first = max(i for i, p in enumerate(periods) if p["first"] - 1 <= closed)
    clock = {"p0": first, "pos": float(closed - (periods[first]["first"] - 1)),
             "t_start": {i: (p["first"] - 1 - closed) / cm.QY for i, p in enumerate(periods) if i >= first},
             "tau_end": {i: (p["first"] - 1 + p["n"] - closed) / cm.QY for i, p in enumerate(periods) if i >= first}}
    y_bal = float(term["y_balancing"])
    rows, decisions, recaps, bv = [], {}, {}, float(inp["bv0"])
    for p in periods:
        qs = list(range(p["first"], p["first"] + p["n"]))
        q_a = p["first"] + p["quarters"].index(agm) if agm in p["quarters"] else None
        q_r = p["first"] + p["quarters"].index(asks) if asks in p["quarters"] else None
        paid, taken = div.get(q_a, 0.0), recs.get(q_r, 0.0)
        bv = bv + sum(ci[q - 1] for q in qs) - paid + taken
        rows.append({"ci": sum(ci[q - 1] for q in qs), "ci_q": [ci[q - 1] for q in qs], "bv": bv,
                     "div_list": [(q_a - p["first"], paid)] if q_a in div else [],
                     "rec_list": [(q_r - p["first"], taken)] if taken else [], "rec": taken})
        if q_a in div:
            decisions[p["year"] - 1] = {"div": paid, "dps": paid * 1000.0 / shares["N_out"], "kind": "policy"}
        if q_r is not None and q_r < grid:              # последний квартал сетки решения не несёт
            last = decisions.get(cm.c_recap_dividend_year(p["year"], agm, asks))
            recaps[p["year"] - 1] = {"rec": taken, "q": q_r, "div": 0.0 if last is None else last["div"],
                                     "div_kind": None if last is None else last["kind"]}
    rows[-1].update(n20=float(term["n20_t"]) / PERCENT, n11_star=float(term["n11_t"]) / PERCENT, dpreg=0.0,
                    rwa=float(term["rwa"]), req20=float(term["req20"]) / PERCENT, req11=float(term["req11"]) / PERCENT,
                    securities=1.0, liquidity=1.0, assets=1.0, wholesale_extra=float(term["wholesale_extra"]),
                    y_sec_end=y_bal, y_liq_end=y_bal, c_wh_end=float(term["c_wholesale"]),
                    pbt=float(term["pbt_last_year"] if pbt is None else pbt), tau_eff=float(term["tau_eff"]))
    book = {"valuation": {"terminal": {"excess_capital_multiple": float(term["excess_capital_multiple"]),
                                       "fade": float(term["fade"]), "real_growth": float(term["g_t"])}},
            "worlds": {"W": {"lt_inflation": 0.0}}, "pnl": {"nci_share": float(term["nci_share"])},
            "volumes": {"liquid_min_share": 0.0, "securities_share_of_liquid": 0.5},
            "tax": {"statutory": float(term["tau_eff"])}, "dividends": {"calendar": {"agm_quarter": agm}}}
    ctx = {"B": book, "periods": periods, "clock": clock, "disc": {"W": lambda tau: (1.0 + k) ** (-cm.QY * tau)},
           "A": {"BV": float(inp["bv0"]), "cpn_annual": float(term["coupon_annual"]), "cpn_quarter": cm.QY, **shares},
           "recap": {"d": cut, "ahead": int(inp["lookahead_quarters"]), "least": float(inp["min_amount"]),
                     "quarter": asks, "agm": agm, "ahead_min": cm.c_recap_window_floor(agm, held, asks),
                     "span": cm.c_recap_span(agm, asks)}, "gov": gov}
    cell = {"world": "W", "regime": None, "scenario": None, "rows": rows, "decisions": decisions, "recaps": recaps}
    cell.update(cm._c_value_cell(ctx, cell, rows, decisions))
    cm._c_cell_shares(ctx, cell)
    return ctx, cell


def close(got, want, what: str) -> None:
    assert got == pytest.approx(want, rel=EXAMPLE_TOL, abs=EXAMPLE_TOL), (what, got, want)


def check_valuation(cell: dict, want: dict, terminal: dict, what: str) -> None:
    for mine, theirs in (("v_ri", "v_ri"), ("v_ddm", "v_ddm"), ("bv_v", "bv_v"), ("c_v", "c_v"),
                         ("bv_now", "bv_v_current"), ("pv_ri_explicit", "pv_ri"), ("pvd", "pvd"),
                         ("pvd_closed", "pvd_closed"), ("pvd_open", "pvd_explicit"), ("pvd_terminal", "pvd_terminal"),
                         ("pv_rec", "pv_rec"), ("pv_rec_terminal", "pv_rec_terminal")):
        close(cell[mine], want[theirs], f"{what}: {theirs}")
    close(cell["df_l"] * cell["tv_ri"], want["pv_tv_ri"], f"{what}: pv_tv_ri")
    close(cell["df_l"] * (cell["tv_ddm"] - cell["dc_t"]), want["pv_tv_ddm"], f"{what}: pv_tv_ddm")
    for mine, theirs in (("x_t", "x_t"), ("bv_star", "bv_star"), ("y_x", "y_x"), ("ni_t1", "ni_t1"),
                         ("ci_t1", "ci_t1"), ("roe_t_raw", "roe_t"), ("roe_t", "roe_t_faded"), ("k_t", "k_t"),
                         ("g_t", "g_t"), ("tv_ri", "tv_ri"), ("p_t", "p_t"), ("tv_ddm", "tv_ddm"), ("dc_t", "dc_t")):
        close(cell[mine], terminal[theirs], f"{what}: терминал {theirs}")


@pytest.mark.tact
def test_appendix_example_decisions():
    """Решения о взносе примера (D.2): недостаток по точкам окна L = 3 и при окне в одну точку — та же таблица,
    тот же порог; в последней точке окна объявленный, но не вычтенный дивиденд из норматива вычтен, в прочих —
    нет; при равенстве (с точностью счёта, 1e-9 млрд ₽) — более ранняя точка и Н20.0; недостаток не выше порога
    взноса не даёт."""
    doc = example()
    for window, want in ((int(doc["input"]["lookahead_quarters"]), doc["decisions"]), (0, doc["decisions_window_0"])):
        made = example_decisions(doc, window)
        assert sorted(made) == sorted(int(q) for q in want)
        for q_a, mine in made.items():
            theirs = want[str(q_a)]
            close(mine["shortfall"], theirs["shortfall"], f"S решения {q_a}")
            close(mine["rec"], theirs["rec"], f"взнос решения {q_a}")
            assert mine["point"] == theirs["point"] and mine["norm"] == theirs["norm"]
            assert [x["q"] for x in mine["points"]] == sorted(int(q) for q in theirs["points"])
            for x in mine["points"]:
                for name in ("s20", "s11", "s"):
                    close(x[name], theirs["points"][str(x["q"])][name], f"решение {q_a}, точка {x['q']}, {name}")
            worst = theirs["points"][str(theirs["point"])]
            if abs(worst["s20"] - worst["s11"]) <= EXAMPLE_TOL:     # равенство двух нормативов с точностью счёта —
                assert mine["norm"] == cm.NORM_TOTAL                # назван Н20.0, хотя в последних знаках они разные
    # недостаток третьего решения ниже порога — взноса нет; нулевой порог сделал бы из него взнос
    last = max(int(q) for q in doc["decisions"])
    assert example_decisions(doc, int(doc["input"]["lookahead_quarters"]))[last]["rec"] == 0.0
    free = cm.c_recap_shortfall(example_points(doc, last, int(doc["input"]["lookahead_quarters"])), 0.0)
    close(free["rec"], doc["decisions"][str(last)]["shortfall"], "взнос при нулевом пороге")
    # равенство — с точностью счёта: названа более ранняя точка и Н20.0, а недостаток — наибольший как есть
    flat = {"n20": 0.12, "n11": 0.08, "dpreg": 0.0, "rwa": 1000.0, "req20": 0.13, "req11": 0.09}
    tied = cm.c_recap_shortfall([{**flat, "q": 1}, {**flat, "q": 2, "req11": 0.09 + 5e-13}, {**flat, "q": 3}], 0.0)
    assert (tied["point"], tied["norm"]) == (1, cm.NORM_TOTAL)
    assert tied["shortfall"] == max(x["s"] for x in tied["points"]) > tied["points"][0]["s"]
    apart = cm.c_recap_shortfall([{**flat, "q": 1}, {**flat, "q": 2, "req11": 0.09 + 5e-11}], 0.0)
    assert (apart["point"], apart["norm"]) == (2, cm.NORM_BASE)


@pytest.mark.tact
def test_appendix_example_valuation_floor_and_shares():
    """Пример приложения D до 1e-9: капитал по тождеству с взносом (D.3), терминал по цене размещения (D.4),
    оценка обеих форм (D.5), путь акций и DPS на акции своего года (D.6), дата оценки после квартала взноса
    (D.7), вариант с отрицательной выплатой терминала, объявленным дивидендом и полом клетки (D.8)."""
    doc = example()
    inp = doc["input"]
    cut, floor = float(inp["price_discount"]), float(inp["cell_floor"])
    recs = {q: d["rec"] for q, d in example_decisions(doc, int(inp["lookahead_quarters"])).items()}
    for q, want in enumerate(doc["rec"]):
        close(recs.get(q, 0.0), want, f"взнос квартала {q}")
    ctx, cell = example_cell(doc, recs, cut=cut)
    for y, row in enumerate(cell["rows"]):
        close(row["bv"], doc["bv"][cm.QY * (y + 1)], f"капитал конца года {y + 1}")
    check_valuation(cell, doc["valuation"], doc["terminal"], "D.5")
    close(cell["v_ri"], cell["v_ddm"], "равенство форм")
    # цена слоя из одной клетки; пол не действует
    worth = cm.c_floor_value(cell["v_ri"], 0.0, floor)
    close(worth, doc["v_floored"], "V^F")
    close(cm.c_price_of(worth, 0.0, 0.0, ctx["A"]["N_div"], 0.0), doc["price"], "цена")
    # нулевой дисконт: оценка выше ровно на цену размывания
    _, fair = example_cell(doc, recs, cut=0.0)
    check_valuation(fair, {**doc["valuation"], "v_ri": doc["at_zero_discount"]["v_ri"],
                           "v_ddm": doc["at_zero_discount"]["v_ddm"], "pvd": 0.0, "pvd_open": 0.0, "pvd_explicit": 0.0,
                           "pvd_terminal": 0.0,
                           "pv_tv_ddm": doc["valuation"]["pv_tv_ddm"] + doc["valuation"]["pvd_terminal"]},
                    doc["at_zero_discount"]["terminal"], "d = 0")
    close(fair["v_ri"] - cell["v_ri"], doc["valuation"]["pvd"], "разность оценок = PVD")
    close(cell["v_plain"], fair["v_ri"], "оценка без цены размывания")
    # путь акций (D.6)
    shares = doc["shares"]
    for q, row in enumerate(cell["share_path"]):
        close(row["shares"], shares["n"][q], f"N_{q}")
        close(row["stake"], shares["stake"][q], f"s_{q}")
        if str(q) in shares["w"]:
            close(row["worth"], shares["w"][str(q)]["w"], f"W_{q}")
            close(row["pre_money"], shares["w"][str(q)]["pre_money"], f"W_{q} − Rec / (1 − d)")
    close(cell["share_path"][0]["worth"], cell["v_ddm"], "W_0 = V_DDM")
    for y in range(len(cell["rows"])):
        close(cell["stake"][y], shares["annual"]["stake"][y], f"доля на конец года {y + 1}")
        close(cell["shares"][y], shares["annual"]["shares"][y], f"делитель на конец года {y + 1}")
        q_a = cm.QY * y + int(inp["agm_quarter"])
        close(cell["decisions"][y]["dps"], shares["dps"][str(q_a)], f"DPS решения квартала {q_a}")
    # стоимость на акцию через взнос не скачет: W_q / N_q = (W_q − Rec_q / (1 − d)) / N_(q−1)
    for row in cell["share_path"][1:]:
        if row["worth"] is not None:
            close(row["worth"] / row["shares"], row["pre_money"] / row["before"], "стоимость на акцию через взнос")
    # дата оценки после квартала первого взноса (D.7)
    later = doc["closed_quarter"]
    _, moved = example_cell(doc, recs, cut=cut, q0=int(later["valuation"]["q0"]))
    check_valuation(moved, later["valuation"], doc["terminal"], "D.7")
    close(moved["v_ri"], later["check_roll"], "оценка на конец квартала взноса")
    first = min(q for q, v in recs.items() if v > 0.0)
    close(moved["v_ri"], cell["share_path"][first]["pre_money"], "она же — стоимость акций до взноса")
    # вариант D.8: отрицательная выплата терминала, объявленный дивиденд, пол клетки
    alt, var = doc["variant_b"], inp["variant_b"]
    pending, gov = float(var["d_pend"]), float(var["governance"])
    ctx_b, low = example_cell(doc, recs, cut=cut, pbt=float(var["pbt_last_year"]), gov=gov)
    check_valuation(low, alt["valuation"], alt["terminal"], "D.8")
    assert low["p_t"] < 0.0 and low["x_t"] < 0.0 and low["v_ri"] - pending < floor      # клетка на полу
    worth = cm.c_floor_value(low["v_ri"], pending, floor)
    close(worth, alt["v_floored"], "V^F варианта")
    close(cm.c_price_of(worth, 0.0, gov, ctx_b["A"]["N_div"], pending), alt["price"], "цена варианта")
    for q, row in enumerate(low["share_path"]):
        assert (row["shares"] is None) == (alt["shares"]["n"][q] is None)
        close(row["stake"], alt["shares"]["stake"][q], f"вариант: s_{q}")
    for y in range(len(low["rows"])):
        q_a = cm.QY * y + int(inp["agm_quarter"])
        close(low["decisions"][y]["dps"], alt["shares"]["dps"][str(q_a)], f"вариант: DPS решения квартала {q_a}")
        assert low["shares"][y] is None and low["stake"][y] == 0.0
    assert low["path_broken"] and not cell["path_broken"]


# ============================================================================ пример приложения E


def _gap_points(pairs) -> list[dict]:
    """Точки окна с заданными недостатками [S_20; S_11]: норматив −S при нулевом требовании и единичных RWA даёт
    недостаток S без погрешности счёта."""
    return [{"q": n + 1, "n20": -float(a), "n11": -float(b), "dpreg": 0.0, "rwa": 1.0, "req20": 0.0, "req11": 0.0}
            for n, (a, b) in enumerate(pairs)]


@pytest.mark.tact
def test_appendix_e_decisions_ties_bounds_and_span():
    """Пример приложения E (решение о взносе в четвёртом квартале, окно — один квартал): кварталы решения — в
    году якоря тоже, последний квартал сетки решения не несёт (E.2); решения по точкам окна — ступень требования
    первого квартала закрывает взнос четвёртого, недостаток не выше порога взноса не даёт (E.3); точка и
    норматив — одним правилом «при равенстве», буквально: пять случаев, среди них три близких недостатка, где
    обход «заменять, если больше на 1e-9» назвал бы другую точку; нижняя граница окна и число точек инварианта —
    по таблицам случаев. Целые и названия — точно, числа — до 1e-9."""
    doc = example(EXAMPLE_Q4)
    inp = doc["input"]
    first_h, agm, held, asks = example_calendar(doc)
    grid, window = int(inp["Q"]), int(inp["lookahead_quarters"])
    in_year = [None] + [(first_h - 1 + q - 1) % cm.QY + 1 for q in range(1, grid + 1)]
    assert in_year == doc["quarter_in_year"]
    assert [q for q in range(1, grid) if in_year[q] == asks] == doc["decision_quarters"]
    assert [grid] == doc["skipped_last_quarter"] and in_year[grid] == asks
    assert [q for q in range(1, grid + 1) if in_year[q] == agm] == doc["agm_quarters"]
    assert cm.c_recap_window_floor(agm, held, asks) == doc["lookahead_min"] <= window
    span = cm.c_recap_span(agm, asks)
    assert span == doc["next_decision_in"]
    made = example_decisions(doc, window)
    assert sorted(made) == doc["decision_quarters"]
    for q_r, mine in made.items():
        theirs = doc["decisions"][str(q_r)]
        close(mine["shortfall"], theirs["shortfall"], f"S решения {q_r}")
        close(mine["rec"], theirs["rec"], f"взнос решения {q_r}")
        assert (mine["point"], mine["norm"]) == (theirs["point"], theirs["norm"]), q_r
        assert [x["q"] for x in mine["points"]] == sorted(int(q) for q in theirs["points"])
        assert mine["points"][-1]["q"] == theirs["last"] == min(q_r + window, grid)
        for x in mine["points"]:
            for name in ("s20", "s11", "s"):
                close(x[name], theirs["points"][str(x["q"])][name], f"решение {q_r}, точка {x['q']}, {name}")
        assert cm.c_recap_check_points(q_r, theirs["last"], span) == theirs["invariant_points"]
    # первое решение стоит в году якоря, взнос — под ступень требования первого квартала следующего года
    first = made[min(made)]
    assert first["rec"] > 0.0 and first["point"] == min(made) + 1 and in_year[first["point"]] == 1
    # третье решение: четыре равных по формуле недостатка — самая ранняя точка и Н20.0; порог взноса не даёт
    last = made[max(made)]
    assert last["rec"] == 0.0 and 0.0 < last["shortfall"] <= float(inp["min_amount"])
    assert (last["point"], last["norm"]) == (max(made), cm.NORM_TOTAL)
    # правило «при равенстве» по случаям примера
    for n, case in enumerate(doc["tie_cases"]):
        got = cm.c_recap_shortfall(_gap_points(case["points"]), 0.0)
        close(got["shortfall"], case["shortfall"], f"случай равенства {n}: S")
        assert (got["point"], got["norm"]) == (case["point_index"], case["norm"]), (n, got["point"], got["norm"])
    # нижняя граница окна и число точек инварианта — таблицы случаев
    for case in doc["window_bounds"]:
        assert cm.c_recap_window_floor(case["agm_quarter"], case["reg_deduction_quarter"],
                                       case["decision_quarter"]) == case["lookahead_min"], case
    for case in doc["invariant_span"]:
        assert cm.c_recap_span(case["agm_quarter"], case["decision_quarter"]) == case["next_decision_in"], case
    assert {cm.c_recap_span(a, a) for a in range(1, cm.QY + 1)} == {cm.QY}     # решение в квартал собрания — год


@pytest.mark.tact
def test_appendix_e_valuation_shares_and_invariant():
    """Пример приложения E до 1e-9: капитал по тождеству с взносом четвёртого квартала (E.4), терминал — недостаток
    конца сетки по цене размещения, оценка обеих форм (E.5), дата оценки после квартала первого взноса — взнос не
    в квартал собрания скачка не даёт, путь акций и DPS на акции своего года с акциями поправки делителя в
    знаменателе (E.6), дивиденд решения о взносе — последнее решение о дивиденде в кварталах q_R − 3 … q_R и
    сумма «дивиденд в пределах взноса», остаток инварианта в его точках (E.7)."""
    doc = example(EXAMPLE_Q4)
    inp = doc["input"]
    cut, window = float(inp["price_discount"]), int(inp["lookahead_quarters"])
    made = example_decisions(doc, window)
    recs = {q: d["rec"] for q, d in made.items()}
    for q, want in enumerate(doc["rec"]):
        close(recs.get(q, 0.0), want, f"взнос квартала {q}")
    ctx, cell = example_cell(doc, recs, cut=cut)
    A, periods = ctx["A"], ctx["periods"]
    close(A["N_div"], doc["n_div"], "делитель")
    assert periods[0]["stub"] and [p["n"] for p in periods] == [2, 4, 4, 4]
    for p, row in zip(periods, cell["rows"]):
        close(row["bv"], doc["bv"][p["first"] + p["n"] - 1], f"капитал конца года {p['year']}")
    check_valuation(cell, doc["valuation"], doc["terminal"], "E.5")
    close(cell["v_ri"], cell["v_ddm"], "равенство форм")
    close(cm.c_price_of(cm.c_floor_value(cell["v_ri"], 0.0, float(inp["cell_floor"])), 0.0, 0.0, A["N_div"], 0.0),
          doc["price"], "цена")
    assert cell["x_t"] < 0.0 and cell["dc_t"] > 0.0     # недостаток конца сетки несёт терминал: решения в Q нет
    # нулевой дисконт: оценка выше ровно на цену размывания
    _, fair = example_cell(doc, recs, cut=0.0)
    check_valuation(fair, {**doc["valuation"], "v_ri": doc["at_zero_discount"]["v_ri"],
                           "v_ddm": doc["at_zero_discount"]["v_ddm"], "pvd": 0.0, "pvd_explicit": 0.0,
                           "pvd_terminal": 0.0,
                           "pv_tv_ddm": doc["valuation"]["pv_tv_ddm"] + doc["valuation"]["pvd_terminal"]},
                    doc["at_zero_discount"]["terminal"], "d = 0")
    close(fair["v_ri"] - cell["v_ri"], doc["valuation"]["pvd"], "разность оценок = PVD")
    # путь акций (E.6): акции клетки — акции якоря, акции поправки делителя и акции взносов
    shares = doc["shares"]
    for q, row in enumerate(cell["share_path"]):
        close(row["shares"], shares["n"][q], f"N_{q}")
        close(row["stake"], shares["stake"][q], f"s_{q}")
        close(A["N_out"] + (row["shares"] - A["N_base"]), shares["n_out"][q], f"акции в обращении клетки, квартал {q}")
        if str(q) in shares["w"]:
            close(row["worth"], shares["w"][str(q)]["w"], f"W_{q}")
            close(row["pre_money"], shares["w"][str(q)]["pre_money"], f"W_{q} − Rec / (1 − d)")
    close(cell["share_path"][0]["worth"], cell["v_ddm"], "W_0 = V_DDM")
    for y in range(len(periods)):
        close(cell["stake"][y], shares["annual"]["stake"][y], f"доля на конец года {periods[y]['year']}")
        close(cell["shares"][y], shares["annual"]["shares"][y], f"делитель на конец года {periods[y]['year']}")
        close(cell["rec_years"][y], shares["annual"]["rec"][y], f"взнос года {periods[y]['year']}")
    agm = int(inp["agm_quarter"])
    for p in periods:
        if agm not in p["quarters"]:
            continue
        q_a = p["first"] + p["quarters"].index(agm)
        dec = cell["decisions"][p["year"] - 1]
        close(dec["dps"], shares["dps"][str(q_a)], f"DPS решения квартала {q_a}")
        close(dec["dps_anchor_shares"], shares["dps_on_anchor_shares"][str(q_a)], f"DPS на акции якоря, квартал {q_a}")
        # прежней формулой — без акций поправки делителя в знаменателе — DPS был бы завышен
        before = cell["share_path"][q_a]["before"]
        old = dec["div"] * 1000.0 / (A["N_out"] + (before - A["N_div"]))
        close(old, shares["dps_without_divisor_adjustment"][str(q_a)], f"DPS прежней формулой, квартал {q_a}")
        assert dec["dps"] < old and dec["shares_out"] == pytest.approx(shares["n_out"][q_a - 1], rel=EXAMPLE_TOL)
    # дивиденд решения о взносе и сумма «дивиденд в пределах взноса»
    for q_r, theirs in doc["decisions"].items():
        mine = next(x for x in cell["recaps"].values() if x["q"] == int(q_r))
        close(mine["div"], theirs["dividend"], f"дивиденд решения о взносе квартала {q_r}")
        assert (mine["div_kind"] is None) == (theirs["dividend_quarter"] is None)
        assert [y for y, x in cell["recaps"].items() if x is mine] == [theirs["year"]]
    flagged = [x["q"] for x in cell["recaps"].values() if x["rec"] > 0.0 and x["div"] > 0.0]
    assert flagged == doc["recap_with_dividend"] and cell["recap_with_dividend"] and cell["recapitalization"]
    close(cell["div_within_recap"], doc["dividend_within_recap"], "дивиденд в пределах взноса")
    # дата оценки после квартала первого взноса: взнос четвёртого квартала скачка не даёт
    later = doc["closed_quarter"]
    _, moved = example_cell(doc, recs, cut=cut, q0=int(later["valuation"]["q0"]))
    check_valuation(moved, later["valuation"], doc["terminal"], "E.5, закрытый квартал")
    close(moved["v_ri"], later["check_roll"], "оценка на конец квартала взноса")
    first = min(q for q, v in recs.items() if v > 0.0)
    close(moved["v_ri"], cell["share_path"][first]["pre_money"], "она же — стоимость акций до взноса")
    close(moved["v_ri"], cell["v_ri"] * (1.0 + float(inp["k_quarter"])) ** first, "перекат по стоимости капитала")
    # инвариант «взнос закрывает разрыв» (E.7): остаток — в точках инварианта, квартал нового решения — вне их
    span, rest = ctx["recap"]["span"], doc["residual"]
    end = made[first]["points"][-1]["q"]
    checked = cm.c_recap_check_points(first, end, span)
    for name, table in (("decision_2", "final"), ("late", "final_late")):
        want = rest[name]
        assert checked == want["points_checked"]
        lines = [pt for pt in example_points(doc, first, grid_rows(doc, first, table), table) if pt["q"] in checked]
        left = cm.c_recap_shortfall(lines, 0.0, closing=checked[-1] == end)
        close(left["shortfall"], want["residual"], f"остаток недостатка ({name})")
        close(left["shortfall"] / recs[first], want["share"], f"его доля во взносе ({name})")
        assert (left["shortfall"] <= LEFT_SHARE * recs[first]) == want["ok"], name
        for x in left["points"]:
            for key in ("s20", "s11", "s"):
                close(x[key], want["points"][str(x["q"])][key], f"{name}, точка {x['q']}, {key}")
    assert rest["decision_2"]["ok"] and not rest["late"]["ok"]
    # точка квартала собрания: остаток выше допуска, но в инвариант она не входит — там дивиденд нового решения
    out = rest["point_outside"]
    assert out["point"] not in checked and out["point"] == first + span
    lone = [pt for pt in example_points(doc, first, grid_rows(doc, first, "final"), "final") if pt["q"] == out["point"]]
    beyond = cm.c_recap_shortfall(lone, 0.0, closing=False)
    close(beyond["shortfall"], out["s"], "недостаток в квартале нового решения")
    close(LEFT_SHARE * recs[first], out["limit"], "допуск инварианта")
    assert beyond["shortfall"] > LEFT_SHARE * recs[first] and lone[0]["dpreg"] > 0.0
    # проверка, которая смотрит один квартал решения, поздний остаток не видит — поэтому состав точек закреплён
    alone = rest["late_if_decision_quarter_only"]
    short_list = [pt for pt in example_points(doc, first, grid_rows(doc, first, "final_late"), "final_late")
                  if pt["q"] in alone["points_checked"]]
    close(cm.c_recap_shortfall(short_list, 0.0, closing=False)["shortfall"], alone["residual"], "один квартал решения")
    assert alone["ok"] and alone["points_checked"] != checked


def grid_rows(doc: dict, q_r: int, table: str) -> int:
    """Сколько строк в таблице входа примера для решения квартала q_R (все строки — «окно» длиной в их число)."""
    return len(doc["input"][table][str(q_r)])


# ============================================================================ «ключа нет — прежняя ветвь»


def test_no_object_and_switch_off_are_the_sample_branch(inputs, plain):
    """Без объекта, при enabled: false (прочие поля — числа и не читаются) и при включённом механизме с порогом
    выше любого недостатка расчёт совпадает бит в бит; подмена одного пути enabled считается в обе стороны; пол
    клетки без клеток ниже пола числа не меняет."""
    book, facts = inputs
    base = cm.c_control_run(book, facts)
    off = cm.c_control_run(put(book, RECAP, {**RULE, "enabled": False}), facts)
    assert _values(off) == _values(base) and "recapitalization" not in off and "cell_floor" not in off
    gone = copy.deepcopy(book)
    gone["capital"].pop("recapitalization")
    assert _values(cm.c_control_run(gone, facts)) == _values(base)
    # порог выше любого недостатка: ряды клеток — бит в бит; оценка — бит в бит при нулевом дисконте, а при
    # дисконте больше нуля ниже ровно на цену размывания терминала (недостаток, не закрытый взносами, копится
    # до конца сетки, и терминал взыскивает его по цене размещения, М§7)
    idle = cm.c_control_run(short_book(book, min_amount=NEVER, price_discount=0.0), facts)
    assert _values(idle) == _values(plain)
    assert all(not c["recapitalization"] and all(r["rec"] == 0.0 for r in c["rows"]) for c in idle["cells"])
    assert all(c["decisions"][y]["dps"] == p["decisions"][y]["dps"] for c, p in zip(idle["cells"], plain["cells"])
               for y in c["decisions"])
    priced = cm.c_control_run(short_book(book, min_amount=NEVER), facts)
    assert _rows(priced) == _rows(plain)
    for c, p in zip(priced["cells"], plain["cells"]):
        assert c["pv_rec"] == 0.0 and c["pvd"] == c["pvd_terminal"] == c["df_l"] * c["dc_t"]
        assert c["v_ri"] == pytest.approx(p["v_ri"] - c["pvd"], rel=1e-12, abs=1e-9)
        assert (c["dc_t"] > 0.0) == (c["x_t"] < 0.0 or c["p_t"] < 0.0)
    assert any(c["dc_t"] > 0.0 for c in priced["cells"]) and any(c["dc_t"] == 0.0 for c in priced["cells"])
    back = cm.c_control_run(put(short_book(book), RECAP + ".enabled", False), facts)
    assert _values(back) == _values(plain)
    floored = cm.c_control_run(put(with_keys(book, SHORT), FLOOR, 0.0), facts)
    assert all(c["v_ri"] > 0.0 and not c["floored"] for c in floored["cells"])
    assert _values(floored) == _values(plain) and floored["cell_floor"]["floored_mass"] == 0.0


@pytest.mark.tact
def test_bad_recap_keys_fail_loudly(inputs):
    """Отказы входа (М прил. A, ограничение № 19): квартальный календарь, включённое ограничение роста, порог
    политики выше пола с запасом, нет поля при enabled: true, поле вне границ — при любом enabled, пол клетки
    ниже нуля."""
    book, facts = inputs
    good = short_book(book)

    def refused(b):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(b, facts)

    cm.c_control_context(good, facts)
    refused(put(good, "dividends.calendar.frequency", cm.FREQ_QUARTERLY))
    refused(put(good, "capital.growth_constraint", {"enabled": True, "order": cm.ORDER_DIV_FIRST,
                                                    "min_growth_scale": 0.0, "lookahead_quarters": 8,
                                                    "glide_pp_per_quarter": 0.0025, "catch_up_rate": 0.25,
                                                    "tol": 0.0001}))
    refused(put(good, "dividends.policy.threshold", book["dividends"]["policy"]["threshold"]))
    for field in ("price_discount", "lookahead_quarters", "min_amount"):
        refused(put(good, f"{RECAP}.{field}", None))
    for field, values in (("price_discount", (-0.01, 1.0, True)), ("lookahead_quarters", (-1, 9, 2.5, True)),
                          ("min_amount", (-1.0,))):
        for value in values:
            refused(put(good, f"{RECAP}.{field}", value))
            refused(put(put(good, f"{RECAP}.{field}", value), f"{RECAP}.enabled", False))
    refused(put(good, f"{RECAP}.enabled", "yes"))
    refused(put(good, FLOOR, -1.0))
    assert cm.c_recap_rule(put(good, f"{RECAP}.lookahead_quarters", 2 * cm.QY))["ahead"] == 2 * cm.QY
    assert cm.c_recap_rule(book) is None and cm.c_cell_floor(book) is None
    # квартал решения о взносе: целое от 1 до 4, необязателен; вне границ — отказ при любом enabled
    for value in (0, 5, 2.0, "4", True):
        refused(put(good, f"{RECAP}.decision_quarter", value))
        refused(put(put(good, f"{RECAP}.decision_quarter", value), f"{RECAP}.enabled", False))
    agm = int(book["dividends"]["calendar"]["agm_quarter"])
    assert cm.c_recap_rule(good)["quarter"] == agm == cm.c_recap_rule(put(good, f"{RECAP}.decision_quarter", agm))["quarter"]
    # нижняя граница окна (ограничение № 19): отказ ровно при lookahead_quarters < L_min — по таблице случаев
    # примера E — и только при включённом механизме
    for case in example(EXAMPLE_Q4)["window_bounds"]:
        low = case["lookahead_min"]
        cal = {**book["dividends"]["calendar"], "agm_quarter": case["agm_quarter"],
               "reg_deduction_quarter": case["reg_deduction_quarter"]}
        shaped = put(put(good, "dividends.calendar", cal), f"{RECAP}.decision_quarter", case["decision_quarter"])
        rule = cm.c_recap_rule(put(shaped, f"{RECAP}.lookahead_quarters", low))
        assert (rule["ahead_min"], rule["quarter"], rule["agm"]) == (low, case["decision_quarter"], case["agm_quarter"])
        assert rule["span"] == cm.c_recap_span(case["agm_quarter"], case["decision_quarter"])
        if low:
            with pytest.raises(cm.ControlInputError, match="нижней границы"):
                cm.c_recap_rule(put(shaped, f"{RECAP}.lookahead_quarters", low - 1))
            off = put(put(shaped, f"{RECAP}.lookahead_quarters", low - 1), f"{RECAP}.enabled", False)
            assert cm.c_recap_rule(off) is None             # при выключенном механизме поле не читается


# ============================================================================ решение о взносе и шаг


@pytest.mark.tact
def test_recap_equals_the_window_shortfall(inputs, short):
    """Взнос равен недостатку окна, пересчитанному тестом по рядам пробного шага: отчётные нормативы во всех
    точках окна, в последней — без дивиденда, объявленного, но не вычтенного к её концу; недостаток не выше
    порога взноса не даёт; решение принимается в каждом квартале собрания сетки, кроме года якоря (якорь стоит
    на квартале собрания) и последнего квартала сетки."""
    ctx = short["ctx"]
    rule, agm = ctx["recap"], int(ctx["B"]["dividends"]["calendar"]["agm_quarter"])
    assert ctx["anchor"][1] == agm, "у формы образца якорь стоит на квартале собрания"
    seen = 0
    for c in short["cells"]:
        assert sorted(c["recaps"]) == [y - 1 for y in short["years"][1:]]
        bv0, rwa0, ni = ctx["A"]["BV"], ctx["rwa0"], dict(cm._c_start_state(ctx)["ni_q"])
        for i, (p, row) in enumerate(zip(ctx["periods"], c["rows"])):
            made = c["recaps"].get(p["year"] - 1)
            if made is not None:
                assert made["q"] == cm.c_qidx(ctx["anchor"], p["year"], agm)
                assert made["window_end"] == min(made["q"] + rule["ahead"], ctx["Q"])
                assert [x["q"] for x in made["points"]] == list(range(made["q"], made["window_end"] + 1))
                assert made["shortfall"] == max(x["s"] for x in made["points"])
                assert made["rec"] == (made["shortfall"] if made["shortfall"] > rule["least"] else 0.0) == row["rec"]
                assert made["div"] == row["div"]
                # точка квартала собрания: пробный шаг — тот же год без взноса; дивиденд объявлен, но не вычтен
                trial = row if not made["rec"] else None
                if trial is not None:
                    j = p["quarters"].index(agm)
                    bv = bv0 + sum(row["ci_q"][:j + 1]) - row["div"]
                    rwa = rwa0 * (row["rwa"] / rwa0) ** ((j + 1) / p["n"])
                    cap = cm._c_capital(ctx, c["scenario"], p["year"], agm, bv, row["dpreg_q"][j], row["R_q"][j], rwa,
                                        {**ni, **row["ni_q"]})
                    first = made["points"][0]
                    assert row["dpreg_q"][j] == row["div"]          # вычет — кварталом позже собрания
                    assert first["s20"] == pytest.approx((cap["req20"] - cap["n20"]) * rwa, rel=1e-12, abs=1e-9)
                    assert first["s11"] == pytest.approx((cap["req11"] - cap["n11"]) * rwa, rel=1e-12, abs=1e-9)
                    seen += 1
            bv0, rwa0, ni = row["bv"], row["rwa"], {**ni, **row["ni_q"]}
    assert seen
    amounts = [x["rec"] for c in short["cells"] for x in c["recaps"].values()]
    assert any(a > 0.0 for a in amounts) and any(a == 0.0 for a in amounts)
    assert all(a == 0.0 or a > rule["least"] for a in amounts)


@pytest.mark.tact
def test_capital_identity_with_the_recap(short, plain):
    """Тождество капитала BV = BV₋₁ + CI − Div + Rec; взнос — не доход: в совокупный доход, прибыль акционеров
    и неаудированную прибыль он не входит; деньги взноса лежат в балансе (тождество баланса); клетка без
    взносов равна клетке без объекта; DDM = RI в каждой клетке."""
    A = short["ctx"]["A"]
    untouched = 0
    for c, p in zip(short["cells"], plain["cells"]):
        bv = A["BV"]
        for r in c["rows"]:
            assert math.isclose(bv + r["ni_sh"] - r["cpn_net"] + r["oci"] + r["om"] - r["div"] + r["rec"], r["bv"],
                                rel_tol=1e-9)
            assert math.isclose(r["ci"], r["ni_sh"] - r["cpn_net"] + r["oci"] + r["om"], rel_tol=1e-9, abs_tol=1e-9)
            assert math.isclose(sum(r["ci_q"]), r["ci"], rel_tol=1e-9, abs_tol=1e-9)
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
            assert r["rec_list"] == ([(r["rec_list"][0][0], r["rec"])] if r["rec"] else [])
            bv = r["bv"]
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"]))
        if not c["recapitalization"]:
            assert [r["bv"] for r in c["rows"]] == [r["bv"] for r in p["rows"]]
            assert c["x_t"] == p["x_t"] and c["pv_rec"] == 0.0
            untouched += 1
            if c["dc_t"] == 0.0:                        # нет и отрицательных распределений терминала
                assert c["v_ri"] == p["v_ri"]
    assert 0 < untouched < len(short["cells"])


def test_recap_year_keeps_the_income_before_the_money_comes(inputs, short):
    """Взнос приходит в конце квартала собрания: до конца года его деньги лежат в балансирующих активах столько
    же, сколько доход этого квартала; год взноса зарабатывает на них меньше, чем год с тем же взносом в начале
    года, а следующий год — на весь взнос. Проверка — пересчётом шага клетки: строка года взноса при нулевом
    взносе отличается от строки с взносом только доходом на деньги и капиталом."""
    ctx = short["ctx"]
    cell = next(c for c in short["cells"] if c["recapitalization"])
    key = {"world": cell["world"], "regime": cell["regime"], "scenario": cell["scenario"]}
    year = next(y for y, x in sorted(cell["recaps"].items()) if x["rec"] > 0.0)
    made = cell["recaps"][year]
    st = cm._c_start_state(ctx)
    st["rwa"] = ctx["rwa0"]
    for i, p in enumerate(ctx["periods"]):
        if p["year"] == year + 1:
            break
        st, _ = cm._c_period(ctx, key, st, i, cell["rows"][i]["div"], rec=cell["rows"][i]["rec"])
    without = cm._c_period(ctx, key, st, i, made["div"])[1]
    with_it = cm._c_period(ctx, key, st, i, made["div"], rec=made["rec"])[1]
    assert with_it["bv"] == pytest.approx(cell["rows"][i]["bv"], rel=1e-12)
    j = with_it["rec_list"][0][0]
    n = ctx["periods"][i]["n"]
    gain = with_it["ci"] - without["ci"]
    assert with_it["bv"] - without["bv"] == pytest.approx(made["rec"] + gain, rel=1e-9)
    # доход на взнос за остаток года: не больше полной ставки балансирующих активов за (n − j − 1) кварталов
    rate = max(with_it["y_liq_end"], with_it["y_sec_end"], with_it["c_wh_end"])
    assert 0.0 < gain < rate * made["rec"] * (n - j - 1) / cm.QY
    assert with_it["shift_la"] - without["shift_la"] == pytest.approx(
        ((n - (j + 1)) / n - 0.5) * made["rec"] + sum(
            ((n - (q + 1)) / n - 0.5) * (a - b) for q, (a, b) in enumerate(zip(with_it["ci_q"], without["ci_q"]))),
        rel=1e-9)
    # K20 и K11 конца года выше на взнос и доход на него за вычетом прироста вычетов вместе с RWA
    for k in ("k20", "k11"):
        assert 0.0 < with_it[k] - without[k] <= made["rec"] + gain
    assert with_it["rwa"] > without["rwa"]              # деньги взноса несут вес риска


def test_recap_covers_the_gap(short):
    """Взнос закрывает разрыв: остаток недостатка после взноса в точках до следующего квартала собрания — не
    больше десятой доли взноса (М§14.1; у формы образца — проценты взноса, и знак обычно отрицательный: доход на
    взнос больше веса риска его денег); ступень требования в окне закрыта взносом до ступени."""
    ctx = short["ctx"]
    worst, seen = -math.inf, 0
    for c in short["cells"]:
        left = cm.c_recap_left(ctx, c)
        assert sorted(left) == sorted(y for y, x in c["recaps"].items() if x["rec"] > 0.0)
        for year, rest in left.items():
            made = c["recaps"][year]
            assert rest["left"] <= LEFT_SHARE * made["rec"], (_key(c), year, rest["left"], made["rec"])
            assert rest["left"] < made["shortfall"]
            worst = max(worst, rest["share"])
            seen += 1
    assert seen and worst > -1.0
    # ступень требования следующего года: связывающая точка первого решения — первый квартал следующего года
    stepped = [x for c in short["cells"] for x in c["recaps"].values()
               if x["rec"] > 0.0 and x["point"] == x["window_end"]]
    assert stepped


def test_shock_year_cancels_the_dividend_not_the_recap(short):
    """Год шока кризиса: решение модели о дивиденде отменено, решение о взносе принято обычным порядком;
    разовый убыток режима пробный шаг взноса видит."""
    shock = short["shock_year"]
    cells = [c for c in short["cells"] if c["regime"] == cm.R_CRISIS]
    hit = [c for c in cells if c["recaps"][shock - 1]["rec"] > 0.0]
    assert hit, "на форме с нехваткой капитала в год шока нет ни одного взноса"
    for c in cells:
        assert c["decisions"][shock - 1]["kind"] == "crisis_skip" and c["decisions"][shock - 1]["div"] == 0.0
        assert c["recaps"][shock - 1]["div"] == 0.0 and c["recaps"][shock - 1]["div_kind"] == "crisis_skip"
    for c in hit:
        row = c["rows"][short["years"].index(shock)]
        assert row["div"] == 0.0 and row["rec"] == c["recaps"][shock - 1]["rec"] and row["one_off"] < 0.0
        assert not any(x["rec"] > 0.0 and x["div"] > 0.0 for y, x in c["recaps"].items() if y == shock - 1)


def test_register_dividend_is_covered_by_the_recap(inputs, short):
    """Запись реестра: дивиденд — сумма записи без проверки запаса; недостаток после него целиком закрывает
    взнос — он больше взноса клетки без записи на разницу дивидендов (в пределах второго порядка)."""
    book, facts = inputs
    y0, agm_end = tcm._agm_end(book)
    cell = next(c for c in short["cells"] if c["recaps"][y0]["rec"] > 0.0 and c["decisions"][y0]["kind"] == "policy")
    dps = 2.0 * cell["decisions"][y0]["dps"]
    seeded = copy.deepcopy(facts)
    seeded["dividends"]["register_seed"] = [tcm._declared(y0, dps, agm_end)]
    ctx = cm.c_control_context(short_book(book, floor=0.0), seeded)
    again = cm.c_cell_annual(ctx, *_key(cell))
    made, before = again["recaps"][y0], cell["recaps"][y0]
    assert again["decisions"][y0]["kind"] == "register" and made["div_kind"] == "register"
    extra = made["div"] - before["div"]
    assert extra == pytest.approx(before["div"], rel=1e-9) and made["rec"] > before["rec"]
    assert made["rec"] - before["rec"] == pytest.approx(extra, rel=0.05)
    assert not again["recap_with_dividend"] or any(
        x["rec"] > 0.0 and x["div"] > 0.0 and x["div_kind"] == "policy" for x in again["recaps"].values())


def test_window_edges(inputs, short):
    """Края окна: окно дальше конца сетки обрезано, и последняя точка — конец сетки. Правило последней точки —
    дивиденд, объявленный, но не вычтенный к концу окна, из норматива последней точки вычтен — у записи реестра с
    отсечкой позже конца окна: недостаток последней точки выше недостатка по отчётному нормативу ровно на
    дивиденд записи. Окно L = 0 допустимо, когда нижняя граница окна — ноль (решение в четвёртом квартале:
    дивиденд года уже вычтен): одна точка — квартал решения, она же последняя, и ступень требования следующего
    квартала такое решение не видит; при решении в квартал собрания с вычетом кварталом позже окно L = 0 — отказ
    книги. Квартал собрания на конце сетки взноса не даёт — недостаток несёт избыток капитала терминала."""
    book, facts = inputs
    grid = short["ctx"]["Q"]
    wide = cm.c_control_run(short_book(book, lookahead_quarters=2 * cm.QY), facts)
    for c in wide["cells"]:
        ends = [x["window_end"] for _, x in sorted(c["recaps"].items())]
        assert ends[-1] == ends[-2] == grid and ends[0] < grid
        assert all(x["points"][-1]["q"] == x["window_end"] for x in c["recaps"].values())
    cal = book["dividends"]["calendar"]
    agm, held = int(cal["agm_quarter"]), int(cal["reg_deduction_quarter"])
    assert held == agm + 1, "вход теста: вычет дивиденда — кварталом позже собрания"
    # нижняя граница окна: решение в квартал собрания при окне короче расстояния до квартала вычета — отказ книги
    with pytest.raises(cm.ControlInputError, match="нижней границы"):
        cm.c_control_context(short_book(book, lookahead_quarters=0), facts)
    assert cm.c_recap_rule(short_book(book, lookahead_quarters=1))["ahead_min"] == 1
    # правило последней точки: запись реестра с отсечкой в четвёртом квартале, окно — до третьего
    y0, _ = tcm._agm_end(book)
    key = _key(next(c for c in short["cells"] if c["decisions"][y0]["kind"] == "policy" and c["decisions"][y0]["div"] > 0.0))
    dps = cm.c_cell_of(short, *key)["decisions"][y0]["dps"]
    seeded = copy.deepcopy(facts)
    seeded["dividends"]["register_seed"] = [tcm._dated_record(y0, dps, pay=(y0 + 1, cm.QY), reg=(y0 + 1, cm.QY))]
    ctx = cm.c_control_context(short_book(book, lookahead_quarters=1), seeded)
    cell = cm.c_cell_annual(ctx, *key)
    made = cell["recaps"][y0]
    i = [p["year"] for p in ctx["periods"]].index(y0 + 1)
    p, row = ctx["periods"][i], cell["rows"][i]
    assert made["div_kind"] == "register" and [x["q"] for x in made["points"]] == [made["q"], made["q"] + 1]
    assert not made["rec"], "вход теста: взноса нет, и строка года — пробный шаг"
    bv0, rwa0 = cell["rows"][i - 1]["bv"], cell["rows"][i - 1]["rwa"]
    ni = dict(cm._c_start_state(ctx)["ni_q"])
    for r in cell["rows"][:i + 1]:
        ni.update(r["ni_q"])
    for n, j in enumerate((p["quarters"].index(agm), p["quarters"].index(agm) + 1)):
        bv = bv0 + sum(row["ci_q"][:j + 1]) - row["div"]
        rwa = rwa0 * (row["rwa"] / rwa0) ** ((j + 1) / p["n"])
        cap = cm._c_capital(ctx, cell["scenario"], p["year"], p["quarters"][j], bv, row["dpreg_q"][j], row["R_q"][j],
                            rwa, ni)
        assert row["dpreg_q"][j] == made["div"] > 0.0              # до четвёртого квартала дивиденд не вычтен
        extra = made["div"] if n == 1 else 0.0                      # вычтен только в последней точке окна
        assert made["points"][n]["s20"] == pytest.approx((cap["req20"] - cap["n20"]) * rwa + extra, rel=1e-9, abs=1e-6)
        assert made["points"][n]["s11"] == pytest.approx((cap["req11"] - cap["n11"]) * rwa + extra, rel=1e-9, abs=1e-6)
    # окно L = 0 при решении в четвёртом квартале: одна точка, дивиденд года к ней уже вычтен
    one = cm.c_control_run(short_book(book, decision_quarter=cm.QY, lookahead_quarters=0), facts)
    assert one["recap_rule"]["ahead_min"] == 0
    ctx = one["ctx"]
    seen = 0
    for c in one["cells"]:
        bv0, rwa0, ni = ctx["A"]["BV"], ctx["rwa0"], dict(cm._c_start_state(ctx)["ni_q"])
        for p, row in zip(ctx["periods"], c["rows"]):
            x = c["recaps"].get(p["year"] - 1)
            if x is not None:
                assert len(x["points"]) == 1 and x["point"] == x["q"] == x["window_end"]
                if not x["rec"]:
                    j = p["quarters"].index(cm.QY)
                    bv = bv0 + sum(row["ci_q"][:j + 1]) - row["div"]
                    rwa = rwa0 * (row["rwa"] / rwa0) ** ((j + 1) / p["n"])
                    cap = cm._c_capital(ctx, c["scenario"], p["year"], cm.QY, bv, row["dpreg_q"][j], row["R_q"][j], rwa,
                                        {**ni, **row["ni_q"]})
                    assert row["dpreg_q"][j] == 0.0
                    assert x["points"][0]["s20"] == pytest.approx((cap["req20"] - cap["n20"]) * rwa, rel=1e-9, abs=1e-6)
                    seen += 1
            bv0, rwa0, ni = row["bv"], row["rwa"], {**ni, **row["ni_q"]}
    assert seen
    # ступень требования следующего года окно в один квартал собрания не видит: её закрывает первое решение
    # с окном, которое до неё доходит
    first = short["years"][1] - 1
    assert any(c["recaps"][first]["point"] > c["recaps"][first]["q"] and c["recaps"][first]["rec"] > 0.0
               for c in short["cells"])
    # собрание в четвёртом квартале: последний квартал сетки — квартал собрания, взноса в нём нет
    late_book = put(short_book(book), "dividends.calendar", dict(AGM_LAST))
    late_facts = copy.deepcopy(facts)
    late_facts["balance"]["dividends_payable_year"] = cm.c_per_parse(book["meta"]["anchor_period"])[0] - 2
    late = cm.c_control_run(late_book, late_facts)
    last_year = late["years"][-1]
    for c in late["cells"]:
        assert last_year - 1 not in c["recaps"] and c["rows"][-1]["rec"] == 0.0
        assert last_year - 1 in c["decisions"]                      # дивиденд последнего квартала сетки решён
        assert sorted(c["recaps"]) == [y - 1 for y in late["years"][:-1]]       # и в году якоря — в своём квартале
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"]))
        # недостаток последнего квартала сетки, если он есть, несёт избыток капитала терминала — по цене размещения
        assert (c["dc_t"] > 0.0) == (c["x_t"] < 0.0 or c["p_t"] < 0.0)
    assert any(x["rec"] > 0.0 for c in late["cells"] for x in c["recaps"].values())


# ============================================================================ квартал решения о взносе — ключ книги

FOURTH_QUARTER = {"decision_quarter": cm.QY, "lookahead_quarters": 1}   # решение — в 4-м квартале, окно — квартал
NO_PAYOUT = {"dividends.policy.payout": {"LT": 0.0}, "dividends.excess.epsilon": 0.0}    # книга без выплаты
LEAN_PAYOUT = 0.8           # доля выплаты второй книги сравнения — к доле книги (вход теста)
SECOND_ORDER = 0.0003       # точка следующего года у годового шага: второй порядок, доля RWA (десятая допуска М§17)
NEW_SCENARIO = "relief"     # имя четвёртого сценария требования, подставленного тестом


@pytest.fixture(scope="module")
def fourth(inputs):
    """Форма с нехваткой капитала: решение о взносе — в четвёртом квартале, окно — один квартал (М§4.14.1)."""
    book, facts = inputs
    return cm.c_control_run(short_book(book, floor=0.0, **FOURTH_QUARTER), facts)


def _gaps(pt: dict) -> tuple[float, float]:
    """Недостаток точки по отчётным нормативам, млрд ₽: (Н20.0, Н20.1)."""
    return (pt["req20"] - pt["n20"]) * pt["rwa"], (pt["req11"] - pt["n11"]) * pt["rwa"]


def test_decision_quarter_equal_to_the_agm_quarter_is_the_book_without_the_key(inputs, short):
    """Ключ decision_quarter, равный кварталу собрания, даёт числа книги без ключа бит в бит (М§4.14.5 п. 10):
    ряды клеток, решения о дивиденде и о взносе, оценка, путь акций, сводка взносов и узел пола."""
    book, facts = inputs
    agm = int(book["dividends"]["calendar"]["agm_quarter"])
    keyed = cm.c_control_run(short_book(book, floor=0.0, decision_quarter=agm), facts)
    assert _values(keyed) == _values(short)
    for a, b in zip(keyed["cells"], short["cells"]):
        assert a["recaps"] == b["recaps"] and a["decisions"] == b["decisions"]
        assert a["stake"] == b["stake"] and a["shares"] == b["shares"] and a["pvd"] == b["pvd"]
    assert keyed["recapitalization"] == short["recapitalization"] and keyed["cell_floor"] == short["cell_floor"]
    assert keyed["recap_rule"] == short["recap_rule"] and keyed["recap_rule"]["span"] == cm.QY


@pytest.mark.tact
def test_recaps_stand_in_the_decision_quarter(fourth, plain):
    """Решение в четвёртом квартале с окном в один квартал: взносы стоят только в четвёртых кварталах; решение
    принимается в каждом четвёртом квартале сетки — и в году якоря (якорь стоит на втором квартале: первое
    решение — второй прогнозный квартал), — кроме последнего квартала сетки; точки окна — квартал решения и
    первый квартал следующего года; взнос равен недостатку окна над порогом. Первое решение воспроизводится по
    сетке книги без механизма (М§4.14.5 п. 11): точка квартала решения — бит в бит (до первого взноса путь клетки
    тот же), точка следующего года — в пределах второго порядка годового шага (пробный шаг следующего года не
    несёт его решений; docs/CONTROL-MODEL.md §8)."""
    ctx = fourth["ctx"]
    rule, years, grid = ctx["recap"], fourth["years"], ctx["Q"]
    assert (rule["quarter"], rule["ahead"], rule["ahead_min"], rule["span"]) == (cm.QY, 1, 0, 2)
    assert ctx["anchor"][1] == rule["agm"] < rule["quarter"]
    stub = ctx["periods"][0]
    for c, bare in zip(fourth["cells"], plain["cells"]):
        assert sorted(c["recaps"]) == [y - 1 for y in years[:-1]]      # в году якоря решение есть, в последнем — нет
        for p, row in zip(ctx["periods"], c["rows"]):
            made = c["recaps"].get(p["year"] - 1)
            k_r = cm.c_qidx(ctx["anchor"], p["year"], cm.QY)
            assert row["rec_list"] == ([(p["quarters"].index(cm.QY), row["rec"])] if row["rec"] else [])
            if made is None:
                assert row["rec"] == 0.0 and k_r == grid              # последний квартал сетки решения не несёт
                continue
            assert made["q"] == k_r < grid and made["window_end"] == k_r + 1
            assert made["period"] == f"{p['year']}{cm.PART_LETTERS[0]}{cm.QY}"
            assert [x["q"] for x in made["points"]] == [k_r, k_r + 1]
            assert made["shortfall"] == max(x["s"] for x in made["points"])
            assert made["rec"] == (made["shortfall"] if made["shortfall"] > rule["least"] else 0.0) == row["rec"]
        first = c["recaps"][years[0] - 1]
        assert first["q"] == stub["quarters"].index(cm.QY) + 1 and (first["div"], first["div_kind"]) == (0.0, None)
        # первое решение — по строкам сетки книги без механизма
        row0, row1 = bare["rows"][0], bare["rows"][1]
        ni = {**cm._c_start_state(ctx)["ni_q"], **row0["ni_q"]}
        at = cm._c_year_point(ctx, c["scenario"], stub, row0, stub["quarters"].index(cm.QY), ctx["A"]["BV"],
                              ctx["rwa0"], ni)
        assert (first["points"][0]["s20"], first["points"][0]["s11"]) == _gaps(at)
        nxt = cm._c_year_point(ctx, c["scenario"], ctx["periods"][1], row1, 0, row0["bv"], row0["rwa"],
                               {**ni, **row1["ni_q"]})
        for mine, theirs in zip((first["points"][1]["s20"], first["points"][1]["s11"]), _gaps(nxt)):
            assert abs(mine - theirs) <= SECOND_ORDER * nxt["rwa"]
    amounts = [x["rec"] for c in fourth["cells"] for x in c["recaps"].values()]
    assert any(a > 0.0 for a in amounts) and any(a == 0.0 for a in amounts)
    # сводка взносов печатает квартал решения и нижнюю границу окна
    assert any(f"решение — {cm.QY}-й квартал" in line for line in cm.c_summary_lines(fourth))


def test_meeting_quarter_inside_the_window_carries_no_new_decision(inputs, plain):
    """Новых решений в кварталах пробного шага после квартала решения нет (М§4.14.1 шаг 2, §4.14.5 п. 11): при
    решении в четвёртом квартале с окном в два квартала последняя точка окна — квартал собрания следующего
    года, и пробный шаг его решения о дивиденде не несёт. Недостаток этой точки первого решения равен недостатку
    по строке сетки книги без механизма, из DPreg которой убран дивиденд нового решения (то есть по отчётному
    нормативу, без вычета последней точки), — в пределах второго порядка годового шага; с дивидендом нового
    решения, вычтенным по правилу последней точки, он был бы выше на этот дивиденд."""
    book, facts = inputs
    res = cm.c_control_run(short_book(book, floor=0.0, decision_quarter=cm.QY, lookahead_quarters=2), facts)
    ctx = res["ctx"]
    agm = ctx["recap"]["agm"]
    nxt = ctx["periods"][1]
    j_agm = nxt["quarters"].index(agm)
    told = 0
    for c, bare in zip(res["cells"], plain["cells"]):
        first = c["recaps"][res["years"][0] - 1]
        assert [x["q"] for x in first["points"]] == [first["q"], first["q"] + 1, first["q"] + 2]
        assert first["window_end"] == cm.c_qidx(ctx["anchor"], nxt["year"], agm)
        row0, row1 = bare["rows"][0], bare["rows"][1]
        ni = {**cm._c_start_state(ctx)["ni_q"], **row0["ni_q"], **row1["ni_q"]}
        at = cm._c_year_point(ctx, c["scenario"], nxt, row1, j_agm, row0["bv"], row0["rwa"], ni)
        edge = SECOND_ORDER * at["rwa"]
        for mine, theirs in zip((first["points"][2]["s20"], first["points"][2]["s11"]), _gaps(at)):
            assert abs(mine - theirs) <= edge, (_key(c), mine, theirs)
        if at["dpreg"] > 10.0 * edge:                   # собрание книги без механизма объявило дивиденд
            assert at["dpreg"] == row1["div"] == bare["decisions"][nxt["year"] - 1]["div"]
            assert abs(first["points"][2]["s20"] - (_gaps(at)[0] + at["dpreg"])) > edge
            told += 1
    assert told, "вход теста: ни в одной клетке собрание следующего года не объявило дивиденда"


def test_first_quarter_step_is_covered_by_the_fourth_quarter_recap(inputs, fourth):
    """Ступень требования первого квартала закрыта взносом четвёртого квартала предыдущего года при окне в один
    квартал: связывающая точка решения — первый квартал следующего года, деньги приходят в квартал перед
    ступенью, остаток недостатка в точках инварианта (оба квартала окна) — не больше десятой доли взноса. При
    окне L = 0 то же решение ступени не видит: взноса в этом году нет, и в первом квартале норматив ниже
    требования."""
    book, facts = inputs
    blind = cm.c_control_run(short_book(book, floor=0.0, decision_quarter=cm.QY, lookahead_quarters=0), facts)
    ctx, years = fourth["ctx"], fourth["years"]
    seen = 0
    for c, b in zip(fourth["cells"], blind["cells"]):
        left = cm.c_recap_left(ctx, c)
        assert sorted(left) == sorted(y for y, x in c["recaps"].items() if x["rec"] > 0.0)
        for year, made in c["recaps"].items():
            if not made["rec"] > 0.0:
                continue
            rest = left[year]
            assert [x["q"] for x in rest["points"]] == cm.c_recap_check_points(made["q"], made["window_end"], 2)
            assert rest["left"] <= LEFT_SHARE * made["rec"], (_key(c), year, rest["left"], made["rec"])
            i = years.index(year + 1)
            if not (made["point"] == made["q"] + 1 and made["points"][0]["s"] <= ctx["recap"]["least"]
                    and c["rows"][i + 1]["req20"] > c["rows"][i]["req20"]):
                continue
            # недостаток — только у ступени: решение с окном в ноль кварталов его не видит
            if b["recaps"][year]["points"][0]["s"] == made["points"][0]["s"]:
                assert b["recaps"][year]["rec"] == 0.0
                row, was = b["rows"][i + 1], b["rows"][i]
                ni = dict(cm._c_start_state(ctx)["ni_q"])
                for r in b["rows"][:i + 2]:
                    ni.update(r["ni_q"])
                gap = max(_gaps(cm._c_year_point(blind["ctx"], b["scenario"], ctx["periods"][i + 1], row, 0, was["bv"],
                                                 was["rwa"], ni)))
                assert gap > ctx["recap"]["least"]      # ступень пришла, а взноса нет: разрыв до решения через год
                seen += 1
    assert seen


def test_decision_after_the_meeting_carries_the_accepted_dividend(inputs, fourth, plain):
    """Решение после собрания видит принятый дивиденд (М§4.14.5 п. 12): две книги — с долей выплаты книги и с
    меньшей; там, где недостаток выше порога в обеих, взнос первого решения после собрания у книги с большей
    выплатой больше на разность дивидендов этого года с точностью второго порядка (к связывающей точке — первому
    кварталу следующего года — дивиденд уже вычтен из регуляторного капитала); у книги без выплаты дивиденд
    решения о взносе — ноль, и взнос не больше. Дивиденд собрания на взнос не рассчитывает (п. 14): пока до
    собрания взносов не было, он равен дивиденду клетки книги без механизма бит в бит. Дивиденд решения о
    взносе — решение собрания этого года."""
    book, facts = inputs
    ready = short_book(book, floor=0.0, **FOURTH_QUARTER)
    pay = book["dividends"]["policy"]["payout"]
    less = {k: (v if str(k) == "LT_from" else v * LEAN_PAYOUT) for k, v in pay.items()}
    lean_run = cm.c_control_run(put(ready, "dividends.policy.payout", less), facts)
    dry = cm.c_control_run(with_keys(ready, NO_PAYOUT), facts)
    y0, y1 = fourth["years"][0], fourth["years"][1]
    seen = same = 0
    for c, d, n, bare in zip(fourth["cells"], lean_run["cells"], dry["cells"], plain["cells"]):
        dec, small = c["decisions"][y1 - 1], d["decisions"][y1 - 1]
        if c["recaps"][y0 - 1]["rec"] == 0.0:
            assert dec["div"] == bare["decisions"][y1 - 1]["div"] and dec["kind"] == bare["decisions"][y1 - 1]["kind"]
            same += 1
        made, lean, none = c["recaps"][y1 - 1], d["recaps"][y1 - 1], n["recaps"][y1 - 1]
        assert (made["div"], made["div_kind"]) == (dec["div"], dec["kind"])
        assert n["decisions"][y1 - 1]["div"] == 0.0 == none["div"]
        quiet = c["recaps"][y0 - 1]["rec"] == 0.0 == d["recaps"][y0 - 1]["rec"] == n["recaps"][y0 - 1]["rec"]
        if quiet:
            assert none["rec"] <= lean["rec"] <= made["rec"]
        if quiet and made["rec"] > 0.0 and lean["rec"] > 0.0 and dec["div"] > small["div"] > 0.0:
            assert made["rec"] - lean["rec"] == pytest.approx(dec["div"] - small["div"], rel=0.05)
            seen += 1
    assert seen and same
    # флаг «взнос при дивиденде» меряет год: дивиденд — во втором квартале, взнос — в четвёртом
    assert any(c["recap_with_dividend"] for c in fourth["cells"])
    for c in fourth["cells"]:
        within = sum(min(x["div"], x["rec"]) for x in c["recaps"].values()
                     if x["rec"] > 0.0 and x["div"] > 0.0 and x["div_kind"] == "policy")
        assert (c["div_within_recap"] > 0.0) == (within > 0.0) and c["div_within_recap"] <= within


def test_decision_before_the_meeting_does_not_carry_this_years_dividend(inputs, plain):
    """Решение до собрания не несёт дивиденда этого года (М§4.14.5 п. 13): при решении в первом квартале и
    собрании во втором взнос первого решения от доли выплаты политики не зависит — бит в бит у книги с выплатой
    и без неё, — а дивиденд собрания того же года решается уже с деньгами взноса: запас капитала выше на взнос.
    Якорь стоит позже квартала решения года якоря — первое решение через год; дивиденд решения о взносе —
    решение собрания прошлого года; ближайшее новое решение клетки — в следующем квартале (δ = 1)."""
    book, facts = inputs
    early = {"decision_quarter": 1, "lookahead_quarters": 1}
    res = cm.c_control_run(short_book(book, floor=0.0, **early), facts)
    dry = cm.c_control_run(with_keys(short_book(book, floor=0.0, **early), NO_PAYOUT), facts)
    ctx = res["ctx"]
    assert (ctx["recap"]["ahead_min"], ctx["recap"]["span"]) == (0, 1) and ctx["recap"]["quarter"] < ctx["recap"]["agm"]
    y0, y1 = res["years"][0], res["years"][1]
    richer = 0
    for c, d, bare in zip(res["cells"], dry["cells"], plain["cells"]):
        assert sorted(c["recaps"]) == [y - 1 for y in res["years"][1:]]        # в году якоря первого квартала нет
        first, lean = c["recaps"][y1 - 1], d["recaps"][y1 - 1]
        assert first["rec"] == lean["rec"] and first["points"] == lean["points"]
        assert (first["div"], first["div_kind"]) == (0.0, None)
        dec, base = c["decisions"][y1 - 1], bare["decisions"][y1 - 1]
        if first["rec"] == 0.0:
            assert dec["div"] == base["div"]
        # первый взнос клетки: до него путь — путь книги без механизма, а собрание того же года решает о
        # дивиденде уже с деньгами взноса — запас капитала в точках проверки выше на взнос (до второго порядка)
        hit = next((y for y, x in sorted(c["recaps"].items()) if x["rec"] > 0.0), None)
        if hit is not None:
            i = res["years"].index(hit + 1)
            assert [r["bv"] for r in c["rows"][:i]] == [r["bv"] for r in bare["rows"][:i]]
            paid, alone = c["decisions"][hit], bare["decisions"][hit]
            if paid["kind"] == "policy" == alone["kind"]:
                assert paid["H"] - alone["H"] == pytest.approx(c["recaps"][hit]["rec"], rel=0.05)
                assert paid["div"] >= alone["div"]
                richer += 1
        later = c["recaps"][y1]
        assert (later["div"], later["div_kind"]) == (dec["div"], dec["kind"])
        row = c["rows"][res["years"].index(y1)]
        assert row["rec_list"] == ([(0, first["rec"])] if first["rec"] else []) and row["div"] == dec["div"]
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"]))
    assert richer
    for c in res["cells"]:                              # точка инварианта — один квартал решения
        for year, rest in cm.c_recap_left(ctx, c).items():
            assert [x["q"] for x in rest["points"]] == [c["recaps"][year]["q"]]


def test_decision_before_the_shock_quarter_sees_the_loss(inputs, fourth):
    """Год шока (М§4.14.3): разовый убыток режима кризиса — в первом квартале года шока, решение четвёртого
    квартала перед ним несёт убыток во второй точке окна — недостаток этой точки растёт на прирост убытка после
    налога, точка квартала решения не меняется. При убытке, которого капитал не выдерживает, клетка режима
    кризиса привлекает капитал заранее — в году якоря; дивиденд года шока отменён, взнос — нет."""
    book, facts = inputs
    shock = fourth["shock_year"]
    loss = book["regimes"][cm.R_CRISIS]["one_off_loss"]
    assert cm.c_per_parse(loss["period"]) == (shock, 1) and fourth["years"][0] == shock - 1
    more = 4.0 * abs(float(loss["amount"]))             # прирост убытка — вход теста
    deep_book = put(short_book(book, floor=0.0, **FOURTH_QUARTER), f"regimes.{cm.R_CRISIS}.one_off_loss.amount",
                    float(loss["amount"]) - more)
    deep = cm.c_control_run(deep_book, facts)
    nci = float(book["pnl"]["nci_share"])
    early = 0
    for c, was in zip(deep["cells"], fourth["cells"]):
        first, before = c["recaps"][shock - 2], was["recaps"][shock - 2]
        if c["regime"] != cm.R_CRISIS:
            assert first == before and c["rows"][0]["rec"] == was["rows"][0]["rec"]
            continue
        assert first["points"][0] == before["points"][0]
        hit = more * (1.0 - c["rows"][1]["tau_eff"]) * (1.0 - nci)
        assert first["points"][1]["s20"] - before["points"][1]["s20"] == pytest.approx(hit, rel=0.03)
        assert c["decisions"][shock - 1]["kind"] == "crisis_skip" and c["decisions"][shock - 1]["div"] == 0.0
        if first["rec"] > 0.0:
            assert first["point"] == first["q"] + 1 and c["rows"][0]["rec"] == first["rec"] and before["rec"] == 0.0
            early += 1
    assert early, "вход теста: убыток не создал недостатка в первом квартале года шока"


@pytest.mark.tact
def test_cell_norm_keeps_the_gap_finite_where_the_value_crosses_zero(inputs, short, plain):
    """Норма клетки (М§6.4): у книги с включённой докапитализацией невязка DDM = RI и доля терминала относятся к
    стоимости клетки, а там, где она ниже капитала на дату оценки на нынешний делитель, — к этому капиталу; в
    клетке со стоимостью не ниже капитала меры — прежние; у книги без докапитализации норма — сама стоимость, а
    доля терминала — прежняя строка бит в бит."""
    book, facts = inputs
    deep = cm.c_control_run(short_book(book, price_discount=0.95), facts)       # клетки со стоимостью ниже нуля
    below = above = 0
    for c in deep["cells"] + short["cells"]:
        own = c["bv_v"] - c["c_v"]
        assert c["norm"] == max(abs(c["v_ri"]), own) > 0.0
        assert cm.c_ddm_gap(c) == abs(c["v_ddm"] - c["v_ri"]) / c["norm"] <= 1e-9
        tail = c["df_l"] * (c["tv_ddm"] - c["dc_t"])
        assert c["terminal_share"] == pytest.approx(tail / max(c["v_ddm"], own), rel=1e-12)
        if c["v_ri"] >= own:
            assert c["norm"] == abs(c["v_ri"]) and c["terminal_share"] == pytest.approx(tail / c["v_ddm"], rel=1e-12)
            above += 1
        else:
            # стоимость ниже капитала: доля терминала — приведённая стоимость терминала в долях капитала
            assert c["norm"] >= own and c["terminal_share"] == pytest.approx(tail / own, rel=1e-12)
            below += 1
    assert below and above
    assert any(c["v_ri"] < 0.0 and c["norm"] == abs(c["v_ri"]) for c in deep["cells"])      # глубоко ниже нуля
    assert any(abs(c["v_ri"]) < c["bv_v"] - c["c_v"] == c["norm"] for c in deep["cells"])    # у нуля — капитал
    # клетка со стоимостью у нуля: невязка к стоимости неограниченна, к норме клетки — конечна
    thin = {"v_ri": 1e-7, "v_ddm": 2e-7, "norm": max(1e-7, 500.0)}
    assert cm.c_ddm_gap(thin) < 1e-9 < abs(thin["v_ddm"] / thin["v_ri"] - 1.0)
    for c in plain["cells"]:
        assert c["norm"] == abs(c["v_ri"]) and c["terminal_share"] == c["df_l"] * c["tv_ddm"] / c["v_ddm"]
        assert cm.c_ddm_gap(c) == abs(c["v_ddm"] - c["v_ri"]) / abs(c["v_ri"])


def with_fourth_scenario(book: dict, twin: str, only: str) -> dict:
    """Книга с четвёртым сценарием требования NEW_SCENARIO — копией сценария twin: вероятность — только в режиме
    only, где он вытесняет twin; в прочих режимах — ноль (М§3.3, §3.4)."""
    out = copy.deepcopy(book)
    scen = out["capital"]["reg_scenarios"]
    scen[NEW_SCENARIO] = copy.deepcopy(scen[twin])
    scen["ids"] = list(scen["ids"]) + [NEW_SCENARIO]
    for regime, row in out["joint"]["reg_prob_given_regime"].items():
        row[NEW_SCENARIO] = row[twin] if regime == only else 0.0
        if regime == only:
            row[twin] = 0.0
    return out


def test_fourth_scenario_of_zero_probability_is_counted(inputs, fourth):
    """Число клеток — по перечням книги (М§3, §17): книга с четвёртым сценарием требования, у которого вероятность
    ноль во всех режимах, кроме одного, считает клетку на каждую тройку перечней, в порядке перечней. Клетка
    нулевой вероятности считается наравне с прочими (ряды, решения о взносе, оценка, DDM = RI), её вес в смесях
    и массах — ноль. Четвёртый сценарий — копия вытесненного: клетки-копии равны клеткам образца бит в бит, и
    точка книги — прежняя. Гейт знака стресса клетку нулевой вероятности не судит: в его таблицах её нет, а
    пара сценариев входит в проверку, когда вероятность положительна у обеих клеток."""
    book, facts = inputs
    twin = book["capital"]["reg_scenarios"]["ids"][0]
    wide_book = with_fourth_scenario(short_book(book, floor=0.0, **FOURTH_QUARTER), twin, cm.R_CRISIS)
    wide = cm.c_control_run(wide_book, facts)
    B = wide["ctx"]["B"]
    worlds, regimes, scen = B["worlds"]["ids"], B["regimes"]["ids"], B["capital"]["reg_scenarios"]["ids"]
    assert len(scen) == len(book["capital"]["reg_scenarios"]["ids"]) + 1
    assert [_key(c) for c in wide["cells"]] == [(w, r, s) for w in worlds for r in regimes for s in scen]
    assert len(wide["cells"]) == len(worlds) * len(regimes) * len(scen) > len(fourth["cells"])
    live = cm.c_live_cells(wide)
    dead = [c for c in wide["cells"] if _key(c) not in live]
    assert {_key(c) for c in dead} == ({(w, r, NEW_SCENARIO) for w in worlds for r in regimes if r != cm.R_CRISIS}
                                       | {(w, cm.R_CRISIS, twin) for w in worlds})
    mass = cm.c_point_mass(wide)
    assert all(mass[_key(c)] == 0.0 for c in dead) and sum(mass.values()) == pytest.approx(1.0, abs=1e-12)
    for name, ly in wide["layers"].items():
        assert ly["prob_sum"] == pytest.approx(1.0, abs=1e-12), name
    for c in wide["cells"]:
        same = cm.c_cell_of(fourth, c["world"], c["regime"], twin if c["scenario"] == NEW_SCENARIO else c["scenario"])
        assert (c["v_ri"], c["v_ddm"], c["x_t"]) == (same["v_ri"], same["v_ddm"], same["x_t"])
        assert [r["rec"] for r in c["rows"]] == [r["rec"] for r in same["rows"]] and c["stake"] == same["stake"]
        assert cm.c_ddm_gap(c) <= 1e-9
    assert any(c["recapitalization"] for c in dead)     # и в клетке нулевой вероятности решения о взносе приняты
    for name in ("point", "low", "high"):
        assert wide[name] == pytest.approx(fourth[name], rel=1e-12)
    for mine, theirs in zip(wide["recapitalization"]["years"], fourth["recapitalization"]["years"]):
        assert mine["rec"] == pytest.approx(theirs["rec"], rel=1e-12, abs=1e-12)
        assert mine["rec_mass"] == pytest.approx(theirs["rec_mass"], abs=1e-12)
    assert wide["cell_floor"]["floored_mass"] == pytest.approx(fourth["cell_floor"]["floored_mass"], abs=1e-12)
    # гейт знака стресса: в таблицах — только клетки положительной вероятности
    gate_book = put(wide_book, "checks.stress_sign", {"loss_step": 50.0, "tol": 0.5})
    sign = cm.c_stress_sign(gate_book, facts, cm.c_control_run(gate_book, facts))
    judged = {(x["world"], x["regime"], x["scenario"]) for x in sign["loss"]["table"]}
    assert judged == {(w, cm.R_CRISIS, s) for w in worlds for s in scen} & live and judged
    pairs = sign["requirement"]["table"]
    assert all((x["world"], x["regime"], side) in live for x in pairs for side in (x["stricter"], x["looser"]))
    assert {x["regime"] for x in pairs} == set(regimes)
    assert all(mass[key] > 0.0 for key in live)


# ============================================================================ оценка


def test_discount_moves_only_the_valuation(inputs, short):
    """Дисконт размещения — параметр оценки: ряды клеток при разных d совпадают бит в бит; оценка линейна в
    1 / (1 − d): разность оценок при двух d равна разности цен размывания; оценка при d = 0 выше оценки книги
    ровно на цену размывания; рост d не повышает оценку ни в одной клетке и не меняет клетку без взносов и без
    отрицательных распределений терминала; DDM = RI при любом d."""
    book, facts = inputs
    fair = cm.c_control_run(short_book(book, floor=0.0, price_discount=0.0), facts)
    steep = cm.c_control_run(short_book(book, floor=0.0, price_discount=0.25), facts)
    assert _rows(fair) == _rows(short) == _rows(steep)
    moved = 0
    for a, b, c in zip(fair["cells"], short["cells"], steep["cells"]):
        assert a["pvd"] == 0.0 and a["dc_t"] == 0.0 and a["v_plain"] == a["v_ri"]
        assert b["v_plain"] == pytest.approx(a["v_ri"], rel=1e-12)
        assert a["v_ri"] - b["v_ri"] == pytest.approx(b["pvd"], rel=1e-9, abs=1e-9)
        assert b["v_ri"] - c["v_ri"] == pytest.approx(c["pvd"] - b["pvd"], rel=1e-9, abs=1e-9)
        assert a["pv_rec"] == b["pv_rec"] == c["pv_rec"] and a["pv_rec_terminal"] == b["pv_rec_terminal"]
        cut = short["ctx"]["recap"]["d"]
        assert b["pvd"] == pytest.approx(cut / (1.0 - cut) * (b["pv_rec"] + b["pv_rec_terminal"]), rel=1e-12, abs=1e-12)
        assert a["v_ri"] >= b["v_ri"] >= c["v_ri"]
        for x in (a, b, c):
            assert abs(x["v_ddm"] - x["v_ri"]) <= 1e-9 * max(1.0, abs(x["v_ri"]))
        if b["pv_rec"] == 0.0 and b["pv_rec_terminal"] == 0.0:
            assert a["v_ri"] == b["v_ri"] == c["v_ri"]
        else:
            assert a["v_ri"] > b["v_ri"] > c["v_ri"]
            moved += 1
        # терминал: при X_T ≥ 0 и ROE'_T ≥ g_T цена размывания терминала — ноль
        if b["x_t"] >= 0.0 and b["roe_t"] >= b["g_t"]:
            assert b["dc_t"] == 0.0 and b["pv_rec_terminal"] == 0.0
        assert b["tv_ddm"] == pytest.approx(b["x_t"] + b["p_t"], rel=1e-12)
    assert moved
    assert fair["point"] > short["point"] > steep["point"]


def test_recap_closed_before_the_valuation_date(inputs):
    """Взнос закрытого квартала: дата оценки на конце квартала взноса и днём позже — взнос вычтен из капитала
    на дату оценки (капитал на нынешний делитель — BV_v − C_v), его цена размывания — без дисконта; за день до
    конца квартала взнос ещё впереди. Взнос скачка не даёт: оценка клетки между E_qA − 1 и E_qA меняется на
    дивиденд, решённый в этом квартале (записи реестра нет — моста нет, М§8.1), и на перекат дня; DDM = RI
    держится."""
    book, facts = inputs
    ready = short_book(book, floor=0.0)
    base = cm.c_control_run(ready, facts)
    y0, agm_end = tcm._agm_end(book)
    runs = {off: cm.c_control_run(ready, facts, valuation_date=agm_end + dt.timedelta(days=off)) for off in (-1, 0, 1)}
    cut = base["ctx"]["recap"]["d"]
    seen = 0
    for i, c in enumerate(base["cells"]):
        rec = c["recaps"][y0]["rec"]
        before, at, after = (runs[off]["cells"][i] for off in (-1, 0, 1))
        for x in (before, at, after):
            assert abs(x["v_ddm"] - x["v_ri"]) <= 1e-9 * max(1.0, abs(x["v_ri"]))
            assert x["recaps"][y0]["rec"] == rec            # ряды клетки от даты оценки не зависят
        assert before["c_v"] == 0.0 and at["c_v"] == after["c_v"] == rec
        assert at["bv_now"] == pytest.approx(at["bv_v"] - rec, rel=1e-12)
        if rec:
            assert at["pvd_closed"] == pytest.approx(cut / (1.0 - cut) * rec, rel=1e-12)
            # деньги взноса уже в капитале клетки (рядом из капитала ушёл дивиденд этого квартала)
            assert at["bv_v"] - before["bv_v"] + c["recaps"][y0]["div"] > 0.5 * rec
            seen += 1
        # непрерывность: взнос скачка не даёт — оценка меняется на дивиденд квартала и на перекат дня
        div = c["recaps"][y0]["div"]
        assert abs(at["v_ri"] + div - before["v_ri"]) <= 0.002 * max(abs(before["v_ri"]), 0.01 * before["bv_v"])
        assert abs(after["v_ri"] - at["v_ri"]) <= 0.002 * max(abs(at["v_ri"]), 0.01 * at["bv_v"])
    assert seen


# ============================================================================ пол клетки


def test_floor_stands_under_the_cell_before_the_mix(inputs, plain):
    """Пол клетки: V0 слоя — сумма стоимостей клеток в цене; клетка выше пола не меняется; пол применён до смеси
    (слой с клетками ниже и выше пола дороже «пола смеси»); без ключа пола нет; масса клеток на полу и поправка
    пола слоя пересчитаны по клеткам; строка клетки и гейты терминала читают V_c."""
    book, facts = inputs
    # дисконт размещения у единицы делает клетки со взносами отрицательными, клетки без взносов не трогает
    deep = short_book(book, price_discount=0.95)
    bare = cm.c_control_run(deep, facts)
    low = cm.c_control_run(put(deep, FLOOR, 0.0), facts)
    high_floor = 2000.0
    high = cm.c_control_run(put(deep, FLOOR, high_floor), facts)
    assert "cell_floor" not in bare and all("v_floor" not in c for c in bare["cells"])
    assert [c["v_ri"] for c in bare["cells"]] == [c["v_ri"] for c in low["cells"]] == [c["v_ri"] for c in high["cells"]]
    under = [c for c in low["cells"] if c["v_ri"] < 0.0]
    assert under and len(under) < len(low["cells"])
    for res, floor in ((low, 0.0), (high, high_floor)):
        ctx = res["ctx"]
        pend = ctx["pending_amount"]
        for c in res["cells"]:
            assert c["v_floor"] == max(c["v_ri"] - pend, floor) + pend
            assert c["floored"] == (c["v_ri"] - pend < floor)
            assert c["price"] == cm.c_price_of(c["v_floor"], ctx["bridge_amount"], ctx["gov"], res["divisor"], pend)
            assert c["pb"] == pytest.approx(c["v_floor"] / c["bv_now"], rel=1e-12)
        weights = cm.c_layer_weights(ctx["B"])
        prs = ctx["B"]["joint"]["reg_prob_given_regime"]
        for name, ly in res["layers"].items():
            P = {_key(c): weights[name].get(c["world"], 0.0) * res["posterior"][c["regime"]]
                 * float(prs[c["regime"]][c["scenario"]]) for c in res["cells"]}
            assert ly["v0"] == pytest.approx(sum(P[_key(c)] * c["v_floor"] for c in res["cells"]), rel=1e-12)
            assert ly["floored_mass"] == pytest.approx(sum(P[_key(c)] for c in res["cells"] if c["floored"]), abs=1e-12)
            assert ly["floor_shift"] == pytest.approx(ly["v0"] - ly["v0_plain"], rel=1e-9, abs=1e-9) and ly["floor_shift"] >= 0.0
            assert ly["v0_plain"] == pytest.approx(bare["layers"][name]["v0"], rel=1e-12)
            if any(c["floored"] and P[_key(c)] > 0.0 for c in res["cells"]):
                assert ly["v0"] > max(ly["v0_plain"], floor)     # до смеси: «пол смеси» был бы ниже
    assert low["point"] > bare["point"] and high["point"] > low["point"]
    report = low["cell_floor"]
    assert report["floor"] == 0.0 and report["point_plain"] == pytest.approx(bare["point"], rel=1e-12)
    assert report["point_shift"] == pytest.approx(low["point"] - bare["point"], rel=1e-9)
    mass = cm.c_point_mass(low)
    assert report["floored_mass"] == pytest.approx(sum(mass[_key(c)] for c in low["cells"] if c["floored"]), abs=1e-12)
    # путь акций клетки на полу оборван или нет — на её оценку и на пол не влияет
    assert any(c["path_broken"] for c in low["cells"])
    assert all(c["v_ri"] == p["v_ri"] for c, p in zip(low["cells"], bare["cells"]))


def test_floor_keeps_the_declared_dividend_and_the_governance_order(inputs):
    """Пол действует на стоимость без объявленного, ещё не вычтенного клетками дивиденда, а дивиденд прибавляется
    обратно; дисконт за управление — после пола: цена клетки на полу равна объявленному дивиденду на акцию
    делителя (плюс мост), цена клетки выше пола — прежняя формула."""
    book, facts = inputs
    y0, agm_end = tcm._agm_end(book)
    dps = tcm._history_dps(facts)
    seeded = copy.deepcopy(facts)
    seeded["dividends"]["register_seed"] = [tcm._declared(y0, dps, agm_end)]
    deep = put(short_book(book, price_discount=0.95), FLOOR, 0.0)
    day = agm_end - dt.timedelta(days=10)                 # объявлено, клетками ещё не вычтено
    res = cm.c_control_run(deep, seeded, valuation_date=day)
    ctx = res["ctx"]
    pend = ctx["pending_amount"]
    assert pend == pytest.approx(dps * res["shares_out"] / 1000.0, rel=1e-12) and ctx["gov"] > 0.0
    under = [c for c in res["cells"] if c["floored"]]
    assert under and len(under) < len(res["cells"])
    for c in under:
        assert c["v_floor"] == pend
        assert c["price"] == pytest.approx((pend + ctx["bridge_amount"]) * 1000.0 / res["divisor"], rel=1e-12)
    for c in res["cells"]:
        if not c["floored"]:
            assert c["v_floor"] == pytest.approx(c["v_ri"], rel=1e-12)
            assert c["price"] == pytest.approx(((c["v_ri"] - pend) * (1.0 - ctx["gov"]) + pend + ctx["bridge_amount"])
                                               * 1000.0 / res["divisor"], rel=1e-12)


# ============================================================================ путь акций и сводка


@pytest.mark.tact
def test_share_path_and_dps_on_own_shares(short):
    """Путь акций клетки (М§6.6): W_0 равно оценке клетки; доля нынешних акций не растёт и падает только в
    квартале взноса; стоимость на акцию через взнос не скачет; дивиденд квартала собрания — на акции до взноса
    этого квартала; клетка без взносов держит долю 1 и прежний DPS; на оценку путь не влияет."""
    ctx = short["ctx"]
    n_div, n_out, cut = short["divisor"], short["shares_out"], ctx["recap"]["d"]
    agm = int(ctx["B"]["dividends"]["calendar"]["agm_quarter"])
    for c in short["cells"]:
        path = c["share_path"]
        assert path[0]["worth"] == pytest.approx(c["v_ddm"], rel=1e-9) and path[0]["stake"] == 1.0
        stakes = [x["stake"] for x in path]
        assert all(b <= a for a, b in zip(stakes, stakes[1:]))
        k = 0
        for i, (p, row) in enumerate(zip(ctx["periods"], c["rows"])):
            recs = dict(row["rec_list"])
            for j in range(p["n"]):
                k += 1
                x = path[k]
                if recs.get(j, 0.0) > 0.0:
                    assert x["pre_money"] == pytest.approx(x["worth"] - recs[j] / (1.0 - cut), rel=1e-12)
                    assert x["worth"] / x["shares"] == pytest.approx(x["pre_money"] / x["before"], rel=1e-12)
                    assert x["shares"] > x["before"]
                else:
                    assert x["shares"] == x["before"] and x["worth"] is None
            assert c["stake"][i] == path[k]["stake"] and c["shares"][i] == path[k]["shares"]
            dec = c["decisions"].get(p["year"] - 1)
            if dec is not None:
                before = path[k - p["n"] + p["quarters"].index(agm) + 1]["before"]
                assert dec["dps"] == pytest.approx(dec["div"] * 1000.0 / (n_out + before - n_div), rel=1e-12)
                assert dec["dps"] <= dec["dps_anchor_shares"] + 1e-12
        if not c["recapitalization"]:
            assert set(stakes) == {1.0} and all(d["dps"] == d["dps_anchor_shares"] for d in c["decisions"].values())
        else:
            assert c["stake"][-1] < 1.0 and c["shares"][-1] > n_div


@pytest.mark.tact
def test_divisor_adjustment_shares_stand_in_the_dps_denominator(inputs, short):
    """Знаменатель DPS на акции своего года (М§6.6): у книги с поправкой делителя valuation.share_count_adj акции
    поправки (N_div − N_base — объявленный выпуск с известной ценой) стоят в знаменателе с первого решения
    модели — акции в обращении клетки N_out + (N − N_base); на ряды, оценку и долю нынешних акций поправка не
    влияет. DPS решения записью реестра — число записи: на акции клетки он не делится, хотя акций клетки больше,
    чем акций якоря."""
    book, facts = inputs
    extra = 0.25                                        # поправка делителя — вход теста
    ready = put(short_book(book, floor=0.0), "valuation.share_count_adj", extra)
    wide = cm.c_control_run(ready, facts)
    A, was = wide["ctx"]["A"], short["ctx"]["A"]
    assert A["N_base"] == was["N_div"] == was["N_base"] and A["N_div"] == pytest.approx(A["N_base"] * (1.0 + extra))
    agm = int(book["dividends"]["calendar"]["agm_quarter"])
    lower = 0
    for c, b in zip(wide["cells"], short["cells"]):
        assert _rows({"cells": [c]}) == _rows({"cells": [b]}) and c["v_ri"] == b["v_ri"]
        assert c["stake"] == pytest.approx(b["stake"], rel=1e-12)
        k = 0
        for p, row in zip(wide["ctx"]["periods"], c["rows"]):
            dec = c["decisions"].get(p["year"] - 1)
            if dec is not None and dec["shares_out"] is not None:
                before = c["share_path"][k + p["quarters"].index(agm) + 1]["before"]
                assert dec["shares_out"] == pytest.approx(A["N_out"] + (before - A["N_base"]), rel=1e-12)
                assert dec["shares_out"] >= A["N_out"] + (A["N_div"] - A["N_base"]) - 1e-9
                assert dec["dps"] == pytest.approx(dec["div"] * 1000.0 / dec["shares_out"], rel=1e-12)
                same = b["decisions"][p["year"] - 1]
                assert dec["dps_anchor_shares"] == same["dps_anchor_shares"]
                if dec["div"] > 0.0:                    # без акций поправки в знаменателе DPS был бы выше
                    assert dec["dps"] < same["dps"] <= dec["dps_anchor_shares"] + 1e-12
                    lower += 1
            k += p["n"]
    assert lower
    # запись реестра: DPS — число записи
    y0, agm_end = tcm._agm_end(book)
    cell = next(c for c in wide["cells"] if c["decisions"][y0]["kind"] == "policy" and c["decisions"][y0]["div"] > 0.0)
    declared = 1.5 * cell["decisions"][y0]["dps_anchor_shares"]
    seeded = copy.deepcopy(facts)
    seeded["dividends"]["register_seed"] = [tcm._declared(y0, declared, agm_end)]
    again = cm.c_cell_annual(cm.c_control_context(ready, seeded), *_key(cell))
    dec = again["decisions"][y0]
    assert dec["kind"] == "register" and dec["dps"] == declared == dec["dps_register"]
    assert dec["div"] == pytest.approx(declared * A["N_out"] / 1000.0, rel=1e-12)
    assert dec["shares_out"] > A["N_out"] and dec["div"] * 1000.0 / dec["shares_out"] < declared


@pytest.mark.tact
def test_recap_summary_is_recomputed_from_the_cells(short):
    """Сводка взносов: ожидаемый взнос года, масса клеток со взносом и ожидаемая доля нынешних акций — под
    вероятностями смеси точки; акции смеси — по ожидаемой доле, а не ожиданием числа акций; приведённые суммы и
    цена размывания слоёв — суммы по клеткам; флаги клеток."""
    mass = cm.c_point_mass(short)
    summary = short["recapitalization"]
    assert [x["year"] for x in summary["years"]] == short["years"]
    for i, x in enumerate(summary["years"]):
        assert x["rec"] == pytest.approx(sum(mass[_key(c)] * c["rows"][i]["rec"] for c in short["cells"]), rel=1e-12)
        assert x["rec_mass"] == pytest.approx(sum(mass[_key(c)] for c in short["cells"] if c["rows"][i]["rec"] > 0.0),
                                              abs=1e-12)
        stake = sum(mass[_key(c)] * c["stake"][i] for c in short["cells"])
        assert x["stake"] == pytest.approx(stake, rel=1e-12) and x["shares"] == pytest.approx(short["divisor"] / stake)
        mean_shares = sum(mass[_key(c)] * c["shares"][i] for c in short["cells"])
        assert x["shares"] <= mean_shares + 1e-9            # число акций по ожидаемой доле не больше ожидания числа
    assert summary["years"][0]["rec"] == 0.0 and any(x["rec"] > 0.0 for x in summary["years"])
    assert summary["point"]["pvd"] == pytest.approx(sum(mass[_key(c)] * c["pvd"] for c in short["cells"]), rel=1e-12)
    assert summary["point"]["pvd_per_share"] == pytest.approx(summary["point"]["pvd"] * 1000.0 / short["divisor"])
    assert summary["point"]["recap_mass"] == pytest.approx(
        sum(mass[_key(c)] for c in short["cells"] if c["recapitalization"]), abs=1e-12)
    for name, ly in short["layers"].items():
        assert ly["pvd"] >= 0.0 and ly["pv_rec"] >= 0.0 and 0.0 <= ly["recap_mass"] <= 1.0
    for c in short["cells"]:
        made = c["recaps"].values()
        assert c["recapitalization"] == any(x["rec"] > 0.0 for x in made)
        assert c["recap_with_dividend"] == any(x["rec"] > 0.0 and x["div"] > 0.0 and x["div_kind"] == "policy"
                                               for x in made)
        assert c["rec_years"] == [r["rec"] for r in c["rows"]]
    assert any(c["recap_with_dividend"] for c in short["cells"])
    lines = cm.c_summary_lines(short)
    assert any(line.startswith("докапитализация:") for line in lines) and any(line.startswith("пол клетки") for line in lines)


# ============================================================================ строки сверки на заглушке ядра


RECAP_GROUPS = ("rec", "pv_rec", "pvd", "dc_t", "stake", "flag")
FLOOR_GROUPS = ("v_floor", "floor")


def _with_cell(res: dict, cell: dict, **ctx) -> dict:
    """Прогон с подменённой клеткой (и ключами контекста) — без копии остального."""
    cells = [cell if _key(c) == _key(cell) else c for c in res["cells"]]
    return {**res, "cells": cells, "ctx": {**res["ctx"], **ctx}}


@pytest.mark.tact
def test_recap_rows_of_the_reconciliation(short, plain):
    """Строки сверки взносов, пола и пути акций (М§17) на заглушке ядра из чисел контрольной модели: строки есть
    только у книги со своими ключами, несут допуск, по которому судятся; взнос, названный одной моделью,
    допустим только у порога; путь акций, оборванный у одной модели, — только у нуля; флаг, стоящий у одной
    модели, — только когда строки его величины в допусках."""
    rows = tcm.compare_with_core(tcm._stub_core(short, 1.0), short)
    assert all(r["ok"] for r in rows)
    assert set(RECAP_GROUPS + FLOOR_GROUPS) <= {r["group"] for r in rows}
    for r in rows:
        if r["group"] in RECAP_GROUPS + FLOOR_GROUPS:
            tcm._assert_row_form(tcm._public(r))
    base = tcm.compare_with_core(tcm._stub_core(plain, 1.0), plain)
    assert not set(RECAP_GROUPS + FLOOR_GROUPS + ("pre_money",)) & {r["group"] for r in base}
    # расхождение в деньгах на 2 %: строки взносов и цены размывания — в относительном допуске
    near = tcm.compare_with_core(tcm._stub_core(short, 1.02), short)
    assert all(r["ok"] for r in near if r["group"] in RECAP_GROUPS + FLOOR_GROUPS)
    far = tcm.compare_with_core(tcm._stub_core(short, 2.0), short)
    assert any(not r["ok"] for r in far if r["group"] == "rec")
    # --- взнос, названный одной моделью
    ctx = short["ctx"]
    cell = max((c for c in short["cells"] if c["recapitalization"]),
               key=lambda c: max(x["rec"] for x in c["recaps"].values()))
    tag = "/".join(_key(cell))
    year, made = max(cell["recaps"].items(), key=lambda kv: kv[1]["rec"])
    what = f"взнос акционеров {year + 1}, клетка {tag}"
    floor = tcm.TOL_RATIO * made["rwa_point"]
    assert made["rec"] > floor, "вход теста: взнос больше допуска строки"

    def judged(least: float, quiet: float, flag: bool = True):
        """Ядро-заглушка взноса этого года не назвало: её недостаток — quiet; порог книги — least."""
        ctl = _with_cell(short, cell, recap={**ctx["recap"], "least": least})
        stub = tcm._stub_core(ctl, 1.0)
        theirs = stub.cell(*_key(cell))
        theirs.quarters["rec"][made["q"]] = 0.0
        theirs.recaps = tuple(tcm.SimpleNamespace(year=x.year, shortfall=quiet if x.year == year else x.shortfall,
                                                  rec=0.0 if x.year == year else x.rec) for x in theirs.recaps)
        if not flag:
            theirs.flags = frozenset(theirs.flags - {tcm.FLAG_RECAP})
        return {r["what"]: r for r in tcm.compare_with_core(stub, ctl)}

    least = made["rec"] - 0.25 * floor                  # порог сразу под взносом контрольной модели
    hit = judged(least, least - 0.5 * floor)[what]
    assert hit["ok"] and hit["threshold"] and hit["tol_abs"] == pytest.approx(least + floor)
    assert hit["floor_plain"] == pytest.approx(floor) and hit["core"] == 0.0 and hit["control"] == made["rec"]
    tcm._assert_row_form(tcm._public(hit))
    miss = judged(least, least - 2.0 * floor)[what]     # недостаток ядра далеко от порога — взнос не «у порога»
    assert not miss["ok"] and not miss.get("threshold")
    away = judged(made["rec"] - 2.0 * floor, made["rec"] - 2.5 * floor)[what]      # взнос контроля далеко над порогом
    assert not away["ok"]
    # флаг «взнос» у одной модели: в допуске только вместе со строками взноса (клетка с единственным взносом)
    lone_cell = next(c for c in short["cells"] if sum(x["rec"] > 0.0 for x in c["recaps"].values()) == 1
                     and max(x["rec"] for x in c["recaps"].values()) > tcm.TOL_RATIO * max(
                         x["rwa_point"] for x in c["recaps"].values() if x["rec"] > 0.0))
    lone_year, lone_made = next((y, x) for y, x in lone_cell["recaps"].items() if x["rec"] > 0.0)
    lone_tag = "/".join(_key(lone_cell))
    lone_floor = tcm.TOL_RATIO * lone_made["rwa_point"]

    def flagged(quiet_gap: float):
        """Ядро-заглушка единственного взноса клетки не назвало и флага «взнос» не несёт."""
        least = lone_made["rec"] - 0.25 * lone_floor
        ctl = _with_cell(short, lone_cell, recap={**ctx["recap"], "least": least})
        stub = tcm._stub_core(ctl, 1.0)
        theirs = stub.cell(*_key(lone_cell))
        theirs.quarters["rec"][lone_made["q"]] = 0.0
        theirs.recaps = tuple(tcm.SimpleNamespace(year=x.year, shortfall=least - quiet_gap, rec=0.0)
                              for x in theirs.recaps if x.year == lone_year)
        theirs.flags = frozenset(theirs.flags - {tcm.FLAG_RECAP})
        return {r["what"]: r for r in tcm.compare_with_core(stub, ctl)}[f"флаг «взнос», клетка {lone_tag}"]

    lone = flagged(0.5 * lone_floor)
    assert lone["ok"] and (lone["core"], lone["control"], lone["tol"]) == (0.0, 1.0, 1.0)
    assert not flagged(2.0 * lone_floor)["ok"]
    # --- путь акций, оборванный у одной модели
    k = next(i for i, x in enumerate(cell["share_path"]) if x["worth"] is not None and i)
    i_year = next(i for i, p in enumerate(ctx["periods"]) if cm.c_qidx(ctx["anchor"], p["year"], p["quarters"][-1]) >= k)
    edge = tcm.STAKE_FLOOR_BV * abs(cell["bv_v"])
    paid = 2.0 * edge                                   # цена взноса прежним акционерам — вход теста

    def broken(mine_pre: float, core_pre: float):
        """У контрольной модели стоимость акций до взноса — mine_pre (путь цел), у ядра-заглушки — core_pre ≤ 0."""
        stake = mine_pre / (mine_pre + paid)
        path = [dict(x) for x in cell["share_path"]]
        path[k].update(pre_money=mine_pre, worth=mine_pre + paid)
        thin = {**cell, "share_path": path, "stake": [1.0] * i_year + [stake] * (len(cell["stake"]) - i_year)}
        ctl = _with_cell(short, thin)
        stub = tcm._stub_core(ctl, 1.0)
        theirs = stub.cell(*_key(cell))
        theirs.shares = tcm.SimpleNamespace(broken=k, w={k: (core_pre + paid, core_pre)})
        theirs.annual["stake"] = tuple([1.0] * i_year + [0.0] * (len(cell["stake"]) - i_year))
        out = tcm.compare_with_core(stub, ctl)
        return ([r for r in out if r["group"] == "pre_money"],
                [r for r in out if r["group"] == "stake" and r["what"].endswith(tag)], stake)

    edge_rows, stakes, stake = broken(0.6 * edge, -0.3 * edge)
    assert stake > tcm.TOL_STAKE, "вход теста: доля выше допуска строки"
    assert len(edge_rows) == 1 and edge_rows[0]["ok"] and all(r["ok"] for r in stakes)
    assert [bool(r.get("broken")) for r in stakes] == [False] * i_year + [True] * (len(stakes) - i_year)
    tcm._assert_row_form(tcm._public(stakes[-1]))
    edge_rows, stakes, _ = broken(0.6 * edge, -0.6 * edge)      # стоимости до взноса разошлись больше 0,5 % BV_v
    assert not edge_rows[0]["ok"] and not all(r["ok"] for r in stakes)


# ============================================================================ сверка с ядром (в момент теста)

CORE_FORM = cm.ROOT / "tests" / "fixtures" / "core_recap" / "overrides.json"     # вариант фикстуры потока ядра


def core_form_book(book: dict) -> dict:
    """Книга формы образца с подменами варианта потока ядра (нехватка капитала, докапитализация включена)."""
    if not CORE_FORM.exists():
        pytest.fail(f"нет варианта фикстуры {CORE_FORM.name}: сверять не на чем")
    return with_keys(book, json.loads(CORE_FORM.read_text(encoding="utf-8"))["overrides"])


def _core_run(book: dict, facts_dir):
    try:
        book_mod, grid_mod = importlib.import_module("model.book"), importlib.import_module("model.grid")
    except Exception as exc:
        pytest.fail(f"ядро не импортируется ({type(exc).__name__}: {exc})")
    try:
        facts = book_mod.load_facts(facts_dir)
        return grid_mod.run_grid(book_mod.book_from_dict(book, facts=facts), facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало форму с докапитализацией: {type(exc).__name__}: {str(exc)[:500]}")


def deep_loss_book(book: dict) -> dict:
    """Решение в четвёртом квартале и разовый убыток кризиса впятеро больше: клетки режима кризиса привлекают
    капитал в году якоря — в квартал перед кварталом убытка (вход сверки, не допущение)."""
    loss = float(book["regimes"][cm.R_CRISIS]["one_off_loss"]["amount"])
    return put(short_book(book, floor=0.0, **FOURTH_QUARTER), f"regimes.{cm.R_CRISIS}.one_off_loss.amount", 5.0 * loss)


def four_scenarios_book(book: dict) -> dict:
    """Книга с четвёртым сценарием требования нулевой вероятности во всех режимах, кроме режима кризиса, где он
    вытесняет первый сценарий перечня (М§17: 48 клеток считаются и сверяются)."""
    twin = book["capital"]["reg_scenarios"]["ids"][0]
    return with_fourth_scenario(short_book(book, floor=0.0, **FOURTH_QUARTER), twin, cm.R_CRISIS)


SHORT_FORMS = {"own": lambda book: short_book(book),
               "own-floor": lambda book: short_book(book, floor=0.0),
               "own-window4-fair": lambda book: short_book(book, lookahead_quarters=4, price_discount=0.0),
               "own-window8-nothreshold": lambda book: short_book(book, lookahead_quarters=8, min_amount=0.0, floor=0.0),
               "core-variant": core_form_book,
               "core-variant-floor": lambda book: put(core_form_book(book), FLOOR, 0.0),
               # квартал решения о взносе — ключ книги (М§4.14.1, §17): решение в четвёртом квартале с окном в
               # один квартал; окно, в которое попал квартал собрания после квартала решения; окно в одну точку;
               # решение в квартал вычета; решение раньше собрания; ключ, равный кварталу собрания
               "q4-window1": lambda book: short_book(book, **FOURTH_QUARTER),
               "q4-window1-floor": lambda book: short_book(book, floor=0.0, **FOURTH_QUARTER),
               "q4-window2-agm-inside": lambda book: short_book(book, floor=0.0, decision_quarter=cm.QY,
                                                               lookahead_quarters=2),
               "q4-window0": lambda book: short_book(book, floor=0.0, decision_quarter=cm.QY, lookahead_quarters=0),
               "q3-window2": lambda book: short_book(book, floor=0.0, decision_quarter=3, lookahead_quarters=2),
               "q1-window1-before-agm": lambda book: short_book(book, floor=0.0, decision_quarter=1,
                                                               lookahead_quarters=1),
               "key-equals-agm": lambda book: short_book(book, floor=0.0, decision_quarter=int(
                   book["dividends"]["calendar"]["agm_quarter"])),
               "q4-window1-deep-loss": deep_loss_book,
               "q4-window1-four-scenarios": four_scenarios_book}


@pytest.mark.ci_only
@pytest.mark.parametrize("form", list(SHORT_FORMS))
def test_control_matches_core_on_the_short_form(inputs, form):
    """Форма образца с нехваткой капитала и включённой докапитализацией против ядра — в допусках М§17: строки
    прежней сверки и строки взносов, цены размывания, терминала по цене размещения, пути акций, DPS на акции
    своего года и пола клетки. Формы — своя (запас менеджмента поднят на оба норматива; с полом и без, окно в
    четыре квартала при нулевом дисконте, окно в восемь кварталов при нулевом пороге), вариант фикстуры потока
    ядра и формы с ключом квартала решения о взносе: четвёртый квартал с окном в один квартал (с полом и без), с
    окном в два квартала (в окно попал квартал собрания после квартала решения) и с окном в одну точку; третий
    квартал (квартал вычета); первый квартал (решение раньше собрания); ключ, равный кварталу собрания; убыток
    кризиса, под который капитал привлекается в году якоря; книга с четвёртым сценарием требования нулевой
    вероятности (48 клеток). Расхождение — находка, а не повод подогнать контрольную модель."""
    book, facts = inputs
    ready = SHORT_FORMS[form](book)
    run = _core_run(ready, FIXTURE / "facts")
    ctl = cm.c_control_run(ready, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    groups = {r["group"] for r in rows}
    assert set(RECAP_GROUPS) <= groups
    assert (set(FLOOR_GROUPS) <= groups) == (ctl["ctx"]["floor"] is not None)
    assert any(r["group"] == "rec" and r["core"] and r["control"] for r in rows), "ни одного взноса у обеих моделей"
    assert not tcm.exact_match(run, ctl), "V0 слоёв совпали с ядром до 1e-9 — общий код"
    # взносы смеси точки по годам у двух моделей — в том же допуске, что строки клеток
    mass, qidx = cm.c_point_mass(ctl), tcm._quarter_index(ctl)
    for i, year in enumerate(ctl["years"]):
        core_v = sum(mass[(c.world, c.regime, c.scenario)] * sum(c.quarters["rec"][j] or 0.0 for j in qidx[year])
                     for c in run.cells)
        mine = ctl["recapitalization"]["years"][i]["rec"]
        assert abs(mine - core_v) <= max(tcm.TOL_LINE * abs(core_v), tcm.TOL_RATIO * ctl["cells"][0]["rows"][i]["rwa"])


@pytest.mark.ci_only
def test_decision_quarter_forms_against_core(inputs, fourth):
    """Квартал решения о взносе у двух моделей (ядро — чёрный ящик, поля результата): взносы ядра стоят только
    в кварталах с номером ключа и не стоят в последнем квартале сетки; первое решение — в году якоря; взносы
    смеси точки по годам сходятся в допуске строк клеток; ключ, равный кварталу собрания, у ядра даёт оценку
    книги без ключа; книгу с окном короче нижней границы отвергают обе модели; книга с четвёртым сценарием —
    клеток по перечням у обеих."""
    book, facts = inputs
    run = _core_run(short_book(book, floor=0.0, **FOURTH_QUARTER), FIXTURE / "facts")
    ctx, qidx = fourth["ctx"], tcm._quarter_index(fourth)
    fourths = {ids[p["quarters"].index(cm.QY)] for p, ids in zip(ctx["periods"], qidx.values())}
    for cc in run.cells:
        rec = cc.quarters["rec"]
        assert all(not (rec[k] or 0.0) for k in range(1, ctx["Q"] + 1) if k not in fourths), (cc.world, cc.regime)
        assert not (rec[ctx["Q"]] or 0.0)
    mass = cm.c_point_mass(fourth)
    for i, year in enumerate(fourth["years"]):
        core_v = sum(mass[(c.world, c.regime, c.scenario)] * sum(c.quarters["rec"][j] or 0.0 for j in qidx[year])
                     for c in run.cells)
        mine = fourth["recapitalization"]["years"][i]["rec"]
        assert abs(mine - core_v) <= max(tcm.TOL_LINE * abs(core_v), tcm.TOL_RATIO * fourth["cells"][0]["rows"][i]["rwa"])
    # ключ, равный кварталу собрания, — оценка книги без ключа и у ядра
    agm = int(book["dividends"]["calendar"]["agm_quarter"])
    keyed = _core_run(short_book(book, floor=0.0, decision_quarter=agm), FIXTURE / "facts")
    bare = _core_run(short_book(book, floor=0.0), FIXTURE / "facts")
    assert (keyed.point, keyed.low, keyed.high) == (bare.point, bare.low, bare.high)
    assert [c.v_ri for c in keyed.cells] == [c.v_ri for c in bare.cells]
    # окно короче нижней границы: отказ книги у обеих моделей
    book_mod = importlib.import_module("model.book")
    short_window = short_book(book, lookahead_quarters=0)
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(short_window, facts)
    with pytest.raises(Exception) as refused:
        book_mod.book_from_dict(short_window, facts=book_mod.load_facts(FIXTURE / "facts"))
    assert type(refused.value).__name__ == "BookError", refused.value
    # четвёртый сценарий: клетка на каждую тройку перечней у обеих моделей
    wide_book = four_scenarios_book(book)
    wide = _core_run(wide_book, FIXTURE / "facts")
    ctl = cm.c_control_run(wide_book, facts)
    assert [(c.world, c.regime, c.scenario) for c in wide.cells] == [_key(c) for c in ctl["cells"]]
    assert len(wide.cells) > len(run.cells)


@pytest.mark.ci_only
def test_switch_off_matches_core_on_the_short_form(inputs, plain):
    """Подмена capital.recapitalization.enabled: false — форма образца у обеих моделей: сверка в допусках, строк
    взносов нет."""
    book, _ = inputs
    ready = put(short_book(book), RECAP + ".enabled", False)
    run = _core_run(ready, FIXTURE / "facts")
    rows = tcm.compare_with_core(run, plain)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    assert not set(RECAP_GROUPS + FLOOR_GROUPS) & {r["group"] for r in rows}
