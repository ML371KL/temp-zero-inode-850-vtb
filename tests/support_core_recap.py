"""Проверки докапитализации и пола стоимости клетки (М§4.14, §6.5–§6.6, §7, §8.2, §10, §14; строки М§18).

Фикстура — форма образца `tests/fixtures/core` (годовой календарь дивидендов, рост задан) с подменами
`tests/fixtures/core_recap/overrides.json`: порог политики снят, запас менеджмента поднят так, что в части
клеток капитала не хватает и при нулевом дивиденде, докапитализация включена. Общий числовой пример —
`tests/fixtures/core_recap/example.json` (приложение D методики): его сверяют ядро и контрольная модель.

Каждая проверка — тождество или закрытая формула, выведенная из книги, фактов и рядов клетки независимо от
кода ядра: недостаток решения пересчитывается по рядам сетки без взносов (она и есть пробный проход первого
решения), оценка — по рядам дивидендов и взносов, пол — по оценкам клеток. Те же функции зовут тесты
`tests/test_core_recap.py` и мутационный набор `tests/mutations.py`.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from model import uncertainty as U
from model.book import Book, book_from_dict
from model.book_schema import BookError
from model.capital import RECAP_RESIDUAL_SHARE, shortfall, worst_point
from model.checks import check_gates, check_invariants, gap_runs
from model.grid import (DividendRecord, GridRun, LiveInputs, floor_value, live_from_book, price_from_v0,
                        run_grid)
from model.levels import floor_node, recap_node
from model.valuation import share_path, shares_value, terminal, value_cell
from model.worlds import Discount
from tests.support_core import book_with, fixture_book, fixture_dict, fixture_facts, fixture_run

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RECAP = ROOT / "tests" / "fixtures" / "core_recap"
OVERRIDES: dict[str, Any] = json.loads((FIXTURE_RECAP / "overrides.json").read_text(encoding="utf-8"))["overrides"]
EXAMPLE: dict[str, Any] = json.loads((FIXTURE_RECAP / "example.json").read_text(encoding="utf-8"))
RECAP = "capital.recapitalization"
FLOOR = "valuation.cell_floor"
HUGE = 1e9                                   # порог выше любого недостатка: механизм включён, взносов нет
EXAMPLE_TOL = 1e-9                           # допуск примера приложения D (М§17)
PCT = 100.0                                  # нормативы и требования примера записаны в процентах
# Варианты фикстуры (подмены поверх `OVERRIDES`): связывает Н20.1; собрание в четвёртом квартале — последнем
# квартале сетки; балансирующие активы без веса риска; разовый убыток кризиса глубже пола до первого собрания и
# убыток, который без взноса роняет норматив ниже пола годом позже; ступень требования, которую без взноса не пройти.
N11_BINDS = {"capital.mgmt_buffer.n1_1": 0.05}
AGM_LAST = {"dividends.calendar": {"agm_quarter": 4, "reg_deduction_quarter": 4, "payment_quarter": 4,
                                   "checkpoints": [4]}}
LATE_STEP = {"capital.reg_scenarios.strict.sifi": {"2026": 0.005, "2027": 0.0075, "2028": 0.01, "2029": 0.015,
                                                   "2030": 0.02, "2031": 0.025, "2035": 0.025, "2036": 0.06}}
NO_RISK_WEIGHT = {"capital.rwa.density.securities": 0.0, "capital.rwa.density.liquidity": 0.0}
DEEP_LOSS = {"regimes.crisis.one_off_loss.amount": -5000.0}
LOSS = {"regimes.crisis.one_off_loss.amount": -3000.0}
BIG_BUFFER = {"capital.mgmt_buffer.n20_0": 0.06, "capital.mgmt_buffer.n1_1": 0.047}
FLOOR_HIGH = 6000.0                          # пол, ниже которого стоит часть клеток фикстуры, млрд ₽


def close(a: float, b: float, rel: float = 1e-9, abs_: float = 1e-9) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


# ------------------------------------------------------------------ книги и сетки фикстуры


def changes_of(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Подмены книги фикстуры: `OVERRIDES` и добавочные; путь внутри объекта докапитализации меняет его поле."""
    out = json.loads(json.dumps(OVERRIDES))
    for path, value in (extra or {}).items():
        if path.startswith(RECAP + "."):
            out[RECAP][path[len(RECAP) + 1:]] = value
        else:
            out[path] = value
    return out


def book_of(extra: Mapping[str, Any] | None = None) -> Book:
    """Книга фикстуры докапитализации с добавочными подменами."""
    return fixture_book().with_overrides(changes_of(extra), create=True)


_GRIDS: dict[str, GridRun] = {}


def grid_of(extra: Mapping[str, Any] | None = None, live: LiveInputs | None = None, *, summary: bool = False
            ) -> GridRun:
    """Сетка книги фикстуры с подменами (одна на набор подмен: проверки читают её, не меняя)."""
    if live is not None:
        return run_grid(book_of(extra), fixture_facts(), live, summary=summary)
    key = json.dumps([extra or {}, summary], sort_keys=True, ensure_ascii=False)
    if key not in _GRIDS:
        _GRIDS[key] = run_grid(book_of(extra), fixture_facts(), summary=summary)
    return _GRIDS[key]


def without_recap(extra: Mapping[str, Any] | None = None) -> GridRun:
    """Сетка той же книги с порогом выше любого недостатка: механизм включён, взносов нет. Её ряды до второго
    квартала собрания — пробный проход первого решения о взносе (принятый дивиденд, без взноса)."""
    return grid_of({**(extra or {}), f"{RECAP}.min_amount": HUGE})


def live_at(v, register: tuple = ()) -> LiveInputs:
    prices = {str(t): float(x) for t, x in fixture_book().get("meta.market_price").items()}
    return LiveInputs(valuation_date=v, prices=prices, price_dates={t: v for t in prices}, register=register)


def record(run: GridRun, dps: float, days_after_agm: int = 20) -> DividendRecord:
    """Объявленная запись реестра за год якоря с экс-датой после конца первого квартала собрания сетки."""
    tl = run.ctx.timeline
    ex = tl.end(first_agm(run)) + timedelta(days=days_after_agm)
    return DividendRecord(year=tl.anchor_year, dps=dps, status="declared", record_date=ex,
                          last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=ex + timedelta(days=14),
                          sources=("проверка",))


def first_agm(run: GridRun) -> int:
    """Первый квартал собрания сетки."""
    tl, agm = run.ctx.timeline, run.ctx.prep.policy.agm_quarter
    return next(q for q in range(1, tl.Q + 1) if tl.h(q) == agm)


def row_at(c: Any, q: int) -> dict[str, float]:
    """Строка квартала клетки для формулы недостатка."""
    return {k: c.quarters[k][q] for k in ("n20", "n11", "n11_star", "dpreg", "rwa", "req20", "req11")}


def trial_shortfall(plain_cell: Any, q_a: int, last: int) -> tuple[float, int, str]:
    """Недостаток окна решения q_A … last по рядам сетки без взносов (М§4.14.1 п. 3) — своей формулой: отчётные
    нормативы против требований М§4.12, в последней точке — без дивидендов, не вычтенных из регуляторного
    капитала. → (S, точка c*, норматив j*)."""
    q_ = plain_cell.quarters
    best = None
    for c in range(q_a, last + 1):
        pending = q_["dpreg"][c] / q_["rwa"][c] if c == last else 0.0
        s20 = (q_["req20"][c] - (q_["n20"][c] - pending)) * q_["rwa"][c]
        s11 = (q_["req11"][c] - (q_["n11"][c] - pending)) * q_["rwa"][c]
        for s, norm in ((s20, "n20"), (s11, "n11")):
            if best is None or s > best[0] + 1e-9:
                best = (s, c, norm)
    return best


# ------------------------------------------------------------------ выключатель и схема


def cells_equal(a: GridRun, b: GridRun, *, rows: bool = True) -> None:
    """Клетки двух сеток равны бит в бит: оценка, капитал, флаги, DPS и общие ряды по кварталам и годам."""
    assert (a.low, a.high, a.point) == (b.low, b.high, b.point), (a.point, b.point)
    for x, y in zip(a.cells, b.cells):
        assert (x.v_ri, x.v_ddm, x.bv_v, x.x_t, x.tv_ri, x.flags) == (y.v_ri, y.v_ddm, y.bv_v, y.x_t, y.tv_ri, y.flags), \
            x.label
        assert dict(x.dps) == dict(y.dps), x.label
        if rows:
            for k in set(x.quarters) & set(y.quarters):
                assert x.quarters[k] == y.quarters[k], (x.label, k)
            for k in set(x.annual) & set(y.annual):
                assert x.annual[k] == y.annual[k], (x.label, k)


def check_off_is_the_sample() -> None:
    """Без объекта и при `enabled: false` расчёт прежний бит в бит; при включённом механизме и пороге выше
    любого недостатка ряды клетки — тоже бит в бит, оценка — бит в бит при d = 0, а при d > 0 ниже ровно на цену
    размывания отрицательных распределений терминала (свойство 1 М§4.14.5; М§7)."""
    base = fixture_run()
    facts = fixture_facts()
    absent = run_grid(book_from_dict(book_with({}, drop=(RECAP,)), facts=facts), facts)
    cells_equal(base, absent)
    off = {RECAP: {"enabled": False, "price_discount": 0.3, "lookahead_quarters": 8, "min_amount": 0.0}}
    cells_equal(base, run_grid(fixture_book().with_overrides(off, create=True), facts))
    assert all(not any(c.quarters["rec"][1:]) and not c.recaps and c.shares is None and c.pvd == 0.0
               for c in absent.cells)
    assert absent.cell_floor is None and all(L.floor_adj == 0.0 and L.pvd == 0.0 for L in absent.layers.values())
    # включённый механизм без взносов: при d = 0 — те же числа, что при выключателе false на той же книге
    switched_off = grid_of({f"{RECAP}.enabled": False})
    quiet = without_recap({f"{RECAP}.price_discount": 0.0})
    assert all(not any(c.quarters["rec"][1:]) for c in quiet.cells)
    assert any(r.shortfall > 0 for c in quiet.cells for r in c.recaps)      # недостаток есть, порог его не пускает
    cells_equal(quiet, switched_off)
    assert all(c.shares is not None and c.shares.stake[-1] == 1.0 for c in quiet.cells)
    # при d > 0 ряды те же, а оценка ниже на цену размывания отрицательных распределений терминала
    priced = without_recap()
    d = OVERRIDES[RECAP]["price_discount"]
    paid = 0
    for c, plain in zip(priced.cells, switched_off.cells):
        for k in plain.quarters:
            assert c.quarters[k] == plain.quarters[k], (c.label, k)
        negative = max(-plain.x_t, 0.0) + max(-(plain.tv_ddm - plain.x_t), 0.0)
        assert close(c.dc_t, d / (1 - d) * negative) and (c.x_t, c.tv_ddm) == (plain.x_t, plain.tv_ddm)
        assert close(c.v_ri, plain.v_ri - priced.ctx.discounts[c.world].dfq[-1] * c.dc_t), c.label
        if negative == 0:
            assert (c.v_ri, c.v_ddm) == (plain.v_ri, plain.v_ddm)
        paid += negative > 0
    assert paid >= 3, paid
    # подмена одного пути выключателя — в обе стороны
    back = book_of({f"{RECAP}.enabled": False}).with_overrides({f"{RECAP}.enabled": True})
    cells_equal(grid_of(), run_grid(back, facts))


def _refused(data: dict, *fragments: str) -> None:
    try:
        book_from_dict(data, facts=fixture_facts())
    except BookError as exc:
        for fr in fragments:
            assert fr in str(exc), (fr, str(exc)[:600])
        return
    raise AssertionError(f"книга принята, ожидался отказ: {fragments}")


def recap_dict(extra: Mapping[str, Any] | None = None, drop: tuple[str, ...] = ()) -> dict:
    """Словарь книги фикстуры докапитализации (для проверок схемы)."""
    return book_with(changes_of(extra), drop=drop)


def check_schema_refusals() -> None:
    """Отказы схемы (М§4.14, прил. A № 19): квартальный календарь, включённое ограничение роста, порог политики
    выше пола с запасом, нет поля при включённом механизме, поле вне границ при любом выключателе, пол ниже нуля."""
    book_from_dict(recap_dict(), facts=fixture_facts())                 # книга фикстуры принята
    _refused(recap_dict({"dividends.calendar.frequency": "quarterly"}), f"{RECAP}.enabled", "годовом календаре")
    growth = {"enabled": True, "order": "dividend_first", "min_growth_scale": 0.0, "lookahead_quarters": 4,
              "glide_pp_per_quarter": 0.0025, "catch_up_rate": 0.5, "tol": 1e-6}
    _refused(recap_dict({"capital.growth_constraint": growth}), f"{RECAP}.enabled", "ограничение роста")
    book_from_dict(recap_dict({"capital.growth_constraint": {**growth, "enabled": False}}), facts=fixture_facts())
    # порог политики выше пола сценария с запасом: наименьший пол с запасом — в первом году сетки
    data = fixture_dict()
    low = (data["capital"]["minimum"]["n20_0"] + OVERRIDES["capital.mgmt_buffer.n20_0"]
           + min(sum(_year_value(data["capital"]["reg_scenarios"][s][k], y) for k in ("conservation", "sifi", "ccyb"))
                 for s in data["capital"]["reg_scenarios"]["ids"] for y in range(2026, 2037)))
    _refused(recap_dict({"dividends.policy.threshold": low + 1e-6}), "dividends.policy.threshold", "порог политики")
    book_from_dict(recap_dict({"dividends.policy.threshold": low}), facts=fixture_facts())
    book_from_dict(recap_dict({"dividends.policy.threshold": low + 1e-6, f"{RECAP}.enabled": False}),
                   facts=fixture_facts())                               # выключено — порог политики не судится
    for field in ("price_discount", "lookahead_quarters", "min_amount"):
        _refused(recap_dict(drop=(f"{RECAP}.{field}",)), f"{RECAP}.{field}", "нет ключа")
        book_from_dict(recap_dict({f"{RECAP}.enabled": False}, drop=(f"{RECAP}.{field}",)), facts=fixture_facts())
    for field, bad in (("price_discount", 1.0), ("price_discount", -0.01), ("lookahead_quarters", 9),
                       ("lookahead_quarters", 2.5), ("lookahead_quarters", -1), ("min_amount", -1.0)):
        for enabled in (True, False):
            _refused(recap_dict({f"{RECAP}.{field}": bad, f"{RECAP}.enabled": enabled}), f"{RECAP}.{field}")
    _refused(recap_dict({FLOOR: -1.0}), FLOOR)
    book_from_dict(recap_dict({FLOOR: 0.0}), facts=fixture_facts())


def _year_value(traj: Any, year: int) -> float:
    from model.paths import Trajectory
    return Trajectory(traj).year_value(year)


# ------------------------------------------------------------------ решение о взносе (М§4.14.1, §4.14.3)


def _first_decisions(extra: Mapping[str, Any] | None = None, live: LiveInputs | None = None):
    """Клетки сетки со взносами и сетки без взносов и первое решение о взносе каждой клетки."""
    run = grid_of(extra, live)
    plain = grid_of({**(extra or {}), f"{RECAP}.min_amount": HUGE}, live)
    return run, [(c, p, c.recaps[0]) for c, p in zip(run.cells, plain.cells)]


def check_decision_is_the_trial_shortfall() -> None:
    """Взнос равен недостатку, пересчитанному по рядам пробного прохода: отчётные нормативы во всех точках окна, в
    последней точке — без дивиденда, объявленного, но не вычтенного к концу окна; недостаток не выше порога взноса
    не даёт. Сетка без взносов до второго квартала собрания и есть пробный проход первого решения."""
    made = n11 = held = 0
    for extra in (None, N11_BINDS):
        run, rows = _first_decisions(extra)
        rule = run.ctx.prep.recap
        for c, plain, dec in rows:
            assert dec.q == first_agm(run) and dec.last == dec.q + rule.lookahead and len(dec.points) == rule.lookahead + 1
            s, point, norm = trial_shortfall(plain, dec.q, dec.last)
            assert close(dec.shortfall, s, rel=1e-12), (c.label, dec.shortfall, s)
            assert (dec.point, dec.norm) == (point, norm), (c.label, dec.point, dec.norm, point, norm)
            want = s if s > rule.min_amount else 0.0
            assert close(dec.rec, want, rel=1e-12) and c.quarters["rec"][dec.q] == dec.rec, c.label
            assert sum(1 for q in range(1, dec.q) if c.quarters["rec"][q]) == 0
            made += dec.rec > 0
            held += 0 < s <= rule.min_amount
            # норматив точки — отчётный: там, где связывает Н20.1, в нём нет неаудированной прибыли
            if dec.rec > 0 and norm == "n11" and plain.quarters["e_unaudited"][point] > 0:
                star = (plain.quarters["req11"][point] - plain.quarters["n11_star"][point]) * plain.quarters["rwa"][point]
                assert star < dec.rec - 1.0, (c.label, star, dec.rec)
                n11 += 1
    assert made >= 20 and n11 >= 3, (made, n11)
    # недостаток не выше порога: решение есть, взноса нет
    run, rows = _first_decisions({f"{RECAP}.min_amount": 200.0})
    below = [dec for _, _, dec in rows if 0 < dec.shortfall <= 200.0]
    assert below and all(dec.rec == 0.0 for dec in below), len(below)
    # нулевой порог пускает и малый недостаток
    run, rows = _first_decisions({f"{RECAP}.min_amount": 0.0})
    assert all(dec.rec == max(dec.shortfall, 0.0) for _, _, dec in rows)


def check_pending_dividend_in_the_last_point_only() -> None:
    """Объявленный, но не вычтенный к концу окна дивиденд входит в недостаток последней точки и не входит в
    недостаток прочих. По календарю книги квартал вычета лежит в окне или раньше него — это нижняя граница окна
    (М§4.14); за концом окна вычет остаётся у записи реестра с поздней отсечкой. Здесь запись объявлена в квартал
    собрания, а её отсечка — через три квартала. Окно L = 1: квартал после собрания — последняя точка, дивиденд
    из её норматива вычтен; окно L = 2: тот же квартал — не последняя точка, его норматив — отчётный, с
    дивидендом в регуляторном капитале."""
    tl = grid_of().ctx.timeline
    live = live_at(tl.end(1), (record(grid_of(), 40.0, days_after_agm=200),))
    with_div = differs = 0
    for lookahead in (1, 2):
        run, rows = _first_decisions({f"{RECAP}.lookahead_quarters": lookahead, f"{RECAP}.min_amount": 0.0}, live)
        for c, plain, dec in rows:
            s, point, norm = trial_shortfall(plain, dec.q, dec.last)
            assert close(dec.shortfall, s, rel=1e-12) and (dec.point, dec.norm) == (point, norm), (c.label, lookahead)
            q_ = plain.quarters
            mid = dec.q + 1
            pending = q_["dpreg"][mid]
            assert pending > 0 and q_["dpreg"][dec.q] == pending and q_["dpreg"][dec.q + 3] == 0.0, c.label
            with_div += 1
            reported = max((q_["req20"][mid] - q_["n20"][mid]) * q_["rwa"][mid],
                           (q_["req11"][mid] - q_["n11"][mid]) * q_["rwa"][mid])
            at = next(p for p in dec.points if p.q == mid)
            if lookahead == 1:                      # последняя точка: дивиденд вычтен
                assert dec.last == mid and close(at.s, reported + pending, rel=1e-12), c.label
            else:                                   # не последняя: отчётный норматив
                assert dec.last == mid + 1 and close(at.s, reported, rel=1e-12), c.label
                differs += reported + pending > dec.shortfall + 1.0     # иное правило дало бы другой взнос
    assert with_div >= 10 and differs >= 3, (with_div, differs)


def check_step_of_the_next_year() -> None:
    """Ступень требования на расстоянии не больше L кварталов закрывается взносом в квартал собрания до ступени;
    при меньшем L — взносом следующего года (свойство 5 М§4.14.5)."""
    seen, late = grid_of(), grid_of({f"{RECAP}.lookahead_quarters": 2})
    key = ("M", "downturn", "upper")
    a, b = seen.cell(*key), late.cell(*key)
    q_a = first_agm(seen)
    step = q_a + 3
    assert a.quarters["req20"][step] > a.quarters["req20"][step - 1] + 0.005        # ступень — в первом квартале года
    da, db = a.recaps[0], b.recaps[0]
    assert da.rec > 0 and da.point == step and db.last == step - 1 and db.rec < da.rec - 100.0
    gap = lambda c, q: (c.quarters["req20"][q] - c.quarters["n20"][q]) * c.quarters["rwa"][q]  # noqa: E731
    assert gap(a, step) <= RECAP_RESIDUAL_SHARE * da.rec                 # окно видело ступень: она закрыта
    assert gap(b, step) > 100.0                                          # окно короче: в квартал ступени — разрыв
    nxt = b.recaps[1]
    assert nxt.q == q_a + 4 and nxt.rec > 100.0                          # его закрывает решение следующего года
    assert gap(b, nxt.q) <= RECAP_RESIDUAL_SHARE * nxt.rec


def check_shock_year_and_register() -> None:
    """В год шока дивиденд отменён, взнос сделан; у записи реестра недостаток считается после её дивиденда."""
    run = grid_of()
    crisis = [c for c in run.cells if c.regime == "crisis"]
    hit = [c for c in crisis if c.recaps[0].rec > 0]
    assert hit and all(c.recaps[0].div_source == "crisis_skip" and c.recaps[0].div == 0.0 for c in crisis)
    assert all("recapitalization" in c.flags and "crisis_skip" in c.flags for c in hit)
    # запись реестра: дивиденд — сумма записи без проверок, недостаток после него целиком закрывает взнос
    tl = run.ctx.timeline
    live = live_at(tl.end(1), (record(run, 40.0),))
    reg, rows = _first_decisions(None, live)
    small = grid_of(live=live_at(tl.end(1), (record(run, 20.0),)))
    n_out = reg.ctx.prep.af.n_out
    bigger = 0
    for (c, plain, dec), less in zip(rows, small.cells):
        assert dec.div_source == "register" and close(dec.div, 40.0 * n_out / 1000) and dec.div_model == 0.0
        s, point, norm = trial_shortfall(plain, dec.q, dec.last)
        assert close(dec.shortfall, s, rel=1e-12), c.label
        assert close(dec.rec, s if s > reg.ctx.prep.recap.min_amount else 0.0, rel=1e-12), c.label
        assert dec.rec >= less.recaps[0].rec
        bigger += dec.rec > less.recaps[0].rec + 100.0      # больше объявленный дивиденд — больше взнос
        assert "recap_with_dividend" not in c.flags or any(r.rec > 0 and r.div_model > 0 for r in c.recaps)
    assert bigger >= 10, bigger


def check_last_quarter_and_the_cut_window() -> None:
    """Квартал собрания — последний квартал сетки: взноса нет, недостаток несёт X_T терминала; окно дальше конца
    сетки обрезано (свойство 7 М§4.14.5, М§4.14.3)."""
    run = grid_of()
    tl = run.ctx.timeline
    for c in run.cells:
        last = c.recaps[-1]
        assert last.q + run.ctx.prep.recap.lookahead > tl.Q and last.last == tl.Q, c.label
        assert [p.q for p in last.points] == list(range(last.q, tl.Q + 1))
    # собрание в четвёртом квартале: последний квартал сетки — квартал собрания; окно L = 0 ступени 2036 года не видит
    extra = {**AGM_LAST, **LATE_STEP, f"{RECAP}.lookahead_quarters": 0}
    end = grid_of(extra)
    assert end.ctx.prep.policy.agm_quarter == tl.h(tl.Q)
    carried = 0
    for c in end.cells:
        assert all(r.q < tl.Q for r in c.recaps) and c.quarters["rec"][tl.Q] == 0.0, c.label
        if c.scenario == "strict":
            assert c.x_t < -100.0, (c.label, c.x_t)     # недостаток конца сетки — в терминале, по цене размещения
            assert c.dc_t > 0 and close(c.dc_t, 0.1 / 0.9 * (max(-c.x_t, 0.0) + max(-c.p_t, 0.0)))
            carried += 1
    assert carried == 12


# ------------------------------------------------------------------ шаг квартала (М§4.14.2)


def check_step_with_the_contribution() -> None:
    """Тождество капитала с взносом; взнос вне совокупного дохода и неаудированной прибыли; совокупный доход
    квартала взноса от взноса не зависит; ЧПД следующего квартала выше на доход денег взноса; K20 и K11 выше
    пробных на взнос за вычетом прироста вычетов; тождество баланса (свойства 2, 3 и 9 М§4.14.5)."""
    run, rows = _first_decisions()
    fired = [f.name for f in check_invariants(run) if f.fired]
    assert not fired, fired
    p, tl = run.ctx.prep, run.ctx.timeline
    earned = 0
    for c, plain, dec in rows:
        a, b = c.quarters, plain.quarters
        for q in range(1, tl.Q + 1):
            want = a["bv"][q - 1] + a["ci"][q] - a["div"][q] + a["rec"][q]
            assert close(a["bv"][q], want, rel=1e-12), (c.label, q)
        if not dec.rec > 0:
            continue
        q = dec.q
        # квартал взноса: поток тот же бит в бит — деньги приходят в конце квартала
        for k in ("ci", "ni_sh", "nii", "pbt", "oci", "e_unaudited", "iea_avg", "div", "dpreg", "dp", "pay"):
            assert a[k][q] == b[k][q], (c.label, k)
        assert close(a["bv"][q] - b["bv"][q], dec.rec, rel=1e-12)
        d20, d11 = a["ded20"][q] - b["ded20"][q], a["ded11"][q] - b["ded11"][q]
        assert d20 > 0 and d11 > 0
        assert close(a["k20"][q] - b["k20"][q], dec.rec - d20, rel=1e-12), c.label
        assert close(a["k11"][q] - b["k11"][q], dec.rec - d11, rel=1e-12), c.label
        assert close(a["assets"][q], a["liabilities_equity"][q]) and a["assets"][q] > b["assets"][q]
        # следующий квартал: деньги взноса лежат в балансирующих активах в долях бумаг и ликвидности
        nxt = q + 1
        if a["wholesale_extra"][q] or b["wholesale_extra"][q] or a["wholesale_extra"][nxt] or b["wholesale_extra"][nxt]:
            continue                                # минимум ликвидности связывает: взнос гасит добор опта
        dt = tl.d(nxt) / 365
        y_bal = (p.sec_share * c.books["securities"]["rate"][nxt]
                 + (1 - p.sec_share) * c.books["liquidity"]["rate"][nxt])
        overlay = b["overlay"][nxt] / (b["iea_avg"][nxt] * dt)
        assert close(a["nii"][nxt] - b["nii"][nxt], (y_bal + overlay) * dec.rec * dt, rel=1e-9), c.label
        earned += 1
    assert earned >= 10, earned


def check_binding_ratio_and_the_residual() -> None:
    """При нулевых плотностях балансирующих активов норматив связывающей точки квартала взноса равен требованию;
    с весом риска остаток недостатка равен весу риска денег взноса с ростом вычетов и лежит в допуске инварианта
    (свойства 3 и 4 М§4.14.5; окно L = 0 — точка одна, квартал собрания: вычет дивиденда — в квартал собрания,
    и нижняя граница окна — ноль, М§4.14)."""
    window = {f"{RECAP}.lookahead_quarters": 0, f"{RECAP}.min_amount": 0.0,
              "dividends.calendar.reg_deduction_quarter": 2}
    flat = grid_of({**NO_RISK_WEIGHT, **window})
    exact = 0
    for c in flat.cells:
        for dec in c.recaps:
            if dec.rec > 0:
                row = row_at(c, dec.q)
                n = row[dec.norm] - row["dpreg"] / row["rwa"]
                assert abs(n - row["req20" if dec.norm == "n20" else "req11"]) < 1e-12, (c.label, dec.q)
                assert abs(dec.residual) < 1e-6
                exact += 1
    assert exact >= 20, exact
    run, rows = _first_decisions({**DEEP_LOSS, **window})       # убыток до первого собрания: взнос — в его квартал
    p, book = run.ctx.prep, run.ctx.book
    weight = p.sec_share * float(book.get("capital.rwa.density.securities")) \
        + (1 - p.sec_share) * float(book.get("capital.rwa.density.liquidity"))
    checked = repaid = 0
    for c, plain, dec in rows:
        if not dec.rec > 0:
            continue
        q, a, b = dec.q, c.quarters, plain.quarters
        # деньги взноса сначала гасят добор опта (минимум ликвидности связывал), остальное — в балансирующие активы
        paid_off = b["wholesale_extra"][q] - a["wholesale_extra"][q]
        assert 0 <= paid_off <= dec.rec and close(b["wholesale"][q] - a["wholesale"][q], paid_off)
        d_la = (a["securities"][q] + a["liquidity"][q]) - (b["securities"][q] + b["liquidity"][q])
        assert close(d_la, dec.rec - paid_off), c.label
        repaid += paid_off > 0
        d_rwa = a["rwa"][q] - b["rwa"][q]
        assert close(d_rwa, weight * p.dn[q] * d_la, rel=1e-9), c.label          # вес риска денег взноса
        sc = p.scenarios[c.scenario]
        rho = {"n20": a["req20"][q] - p.cap.gap20 + sc.ded_pp20[q] + p.cap.ded20_0 / p.cap.rwa0,
               "n11": a["req11"][q] - p.cap.gap11 + sc.ded_pp11[q] + p.cap.ded11_0 / p.cap.rwa0}
        left = max(next(pt for pt in dec.points if pt.q == q).s20 - dec.rec + rho["n20"] * d_rwa,
                   next(pt for pt in dec.points if pt.q == q).s11 - dec.rec + rho["n11"] * d_rwa)
        assert close(dec.residual, left, rel=1e-9, abs_=1e-6), (c.label, dec.residual, left)
        assert 0 < dec.residual <= RECAP_RESIDUAL_SHARE * dec.rec
        checked += 1
    assert checked >= 6 and repaid >= 3, (checked, repaid)
    # инвариант: остаток — проценты взноса; в рублях он много больше доли единицы — допуск меряется долей взноса
    for grid in (run, grid_of()):
        left = [(r.residual, r.rec) for c in grid.cells for r in c.recaps if r.rec > 0]
        assert left and all(res <= RECAP_RESIDUAL_SHARE * rec for res, rec in left)
        finding = next(f for f in check_invariants(grid) if f.name == "recap_covers_gap")
        assert not finding.fired and close(finding.detail["worst"], max(res / rec for res, rec in left))
    assert max(r.residual for c in run.cells for r in c.recaps if r.rec > 0) > 10.0
    assert all(f.name != "recap_covers_gap" for f in check_invariants(fixture_run()))


# ------------------------------------------------------------------ оценка (М§6.5, §7)


def _terminal_of(c: Any) -> SimpleNamespace:
    return SimpleNamespace(tv_ddm=c.tv_ddm, dc_t=c.dc_t)


def _contributions(run: GridRun, c: Any) -> tuple[float, float, float]:
    """(C_v, Σ Rec_q × DF_v(τ_q) открытых кварталов, DF_v(τ_Q) × отрицательные распределения терминала) клетки —
    по её рядам и дисконту мира."""
    q0, dfq = run.ctx.clock.q0, run.ctx.discounts[c.world].dfq
    rec = c.quarters["rec"]
    closed = sum(rec[q] for q in range(1, q0))
    open_ = sum(rec[q] * dfq[q] for q in range(q0, len(rec)))
    return closed, open_, dfq[-1] * (max(-c.x_t, 0.0) + max(-(c.tv_ddm - c.x_t), 0.0))


def check_valuation_with_contributions() -> None:
    """DDM = RI в каждой клетке при d > 0 и d = 0; оценка при d = 0 — чистые распределения по справедливой цене;
    разность оценок при двух d равна разности цен размывания; рост d не повышает оценку ни в одной клетке и не
    меняет клетку без взносов; ряды клетки от d не зависят; при X_T ≥ 0 и ROE'_T ≥ g_T цена размывания терминала
    — ноль (М§6.5, §7; свойство 8 М§4.14.5)."""
    # собрание в последнем квартале сетки и ступень последнего года: в жёстком сценарии — недостаток на её конце
    extra = {**AGM_LAST, **LATE_STEP, f"{RECAP}.lookahead_quarters": 0}
    runs = {d: grid_of({**extra, f"{RECAP}.price_discount": d}) for d in (0.0, 0.1, 0.25)}
    tol = float(runs[0.0].ctx.book.get("checks.ddm_ri_tol"))
    q0 = runs[0.0].ctx.clock.q0
    moved = fixed = negative = 0
    for cells in zip(*(runs[d].cells for d in (0.0, 0.1, 0.25))):
        zero = cells[0]
        dfq = runs[0.0].ctx.discounts[zero.world].dfq
        for c in cells:
            assert abs(c.v_ddm - c.v_ri) <= tol * abs(c.v_ri), (c.label, c.v_ddm, c.v_ri)
            for k in zero.quarters:                 # проход клеток дисконта размещения не читает
                assert c.quarters[k] == zero.quarters[k], (c.label, k)
            assert (c.x_t, c.tv_ri, c.tv_ddm, c.bv_v) == (zero.x_t, zero.tv_ri, zero.tv_ddm, zero.bv_v)
        # d = 0: чистые распределения по справедливой цене — дивиденды минус взносы и терминал как есть
        q_ = zero.quarters
        fair = (sum(((q_["div"][q] or 0.0) - q_["rec"][q]) * dfq[q] for q in range(q0, len(dfq)))
                + dfq[-1] * zero.tv_ddm)
        assert close(zero.v_ddm, fair) and zero.pvd == 0.0 and zero.dc_t == 0.0, zero.label
        closed, open_, term = _contributions(runs[0.0], zero)
        base = closed + open_ + term
        for d, c in zip((0.1, 0.25), cells[1:]):
            k = d / (1 - d)
            assert close(c.v_ri, zero.v_ri - k * base), (c.label, d)             # цена размывания — вся разность
            assert close(c.pvd, k * base) and c.v_ri <= zero.v_ri + 1e-9
            assert close(c.pv_rec, closed + open_) and close(c.pv_rec_terminal, term)
            if zero.x_t >= 0 and zero.roe_t >= zero.g_t:
                assert c.dc_t == 0.0, c.label
            else:
                assert close(c.dc_t, k * (max(-zero.x_t, 0.0) + max(-(zero.tv_ddm - zero.x_t), 0.0)))
                negative += 1
        assert cells[2].v_ri <= cells[1].v_ri + 1e-9
        if base > 0:
            moved += 1
        else:
            assert cells[0].v_ri == cells[1].v_ri == cells[2].v_ri, zero.label
            fixed += 1
    assert moved >= 12 and negative >= 12, (moved, fixed, negative)
    # клетка без взносов и без отрицательных распределений терминала от дисконта не зависит
    a, b = grid_of(), grid_of({f"{RECAP}.price_discount": 0.25})
    still = [(x, y) for x, y in zip(a.cells, b.cells) if "recapitalization" not in x.flags and x.x_t >= 0
             and x.roe_t >= x.g_t]
    assert len(still) >= 5 and all(x.v_ri == y.v_ri and x.v_ddm == y.v_ddm for x, y in still)
    # лёгкая клетка сводки считает ту же оценку, что полная: путь акций на оценку не влияет
    light = grid_of(summary=True)
    assert all(x.v_ri == y.v_ri and x.pvd == y.pvd and x.flags == y.flags for x, y in zip(a.cells, light.cells))


def check_closed_quarter() -> None:
    """Взнос закрытого квартала вычтен из капитала на дату оценки, его цена размывания — без дисконта; DDM = RI;
    между E_qA − 1 и E_qA точка меняется на перекат, а не на взнос (М§6.5). Дивиденд квартала собрания объявлен
    записью реестра: на конце квартала он переходит из V0 в мост, и скачка от него нет."""
    run = grid_of()
    tl = run.ctx.timeline
    end = tl.end(first_agm(run))
    reg = (record(run, 40.0),)
    after = grid_of(live=live_at(end + timedelta(days=5), reg))
    q0 = after.ctx.clock.q0
    assert q0 == first_agm(run) + 1
    tol = float(after.ctx.book.get("checks.ddm_ri_tol"))
    closed = 0
    for c in after.cells:
        rec = c.quarters["rec"]
        c_v = sum(rec[q] for q in range(1, q0))
        assert c.c_v == c_v and abs(c.v_ddm - c.v_ri) <= tol * abs(c.v_ri), c.label
        e = after.ctx.clock.elapsed
        full = c.quarters["bv"][q0 - 1] + e * c.quarters["ci"][q0]
        assert close(c.bv_v, full - c_v, rel=1e-12), c.label           # капитал на нынешний делитель
        dfq = after.ctx.discounts[c.world].dfq
        k = 0.1 / 0.9
        want = k * (c_v + sum(rec[q] * dfq[q] for q in range(q0, len(rec)))) + dfq[-1] * c.dc_t
        assert close(c.pvd, want), c.label
        closed += c_v > 0
    assert closed >= 20
    assert not [f.name for f in check_invariants(after) if f.fired]
    pts = [grid_of(live=live_at(end + timedelta(days=d), reg)).point for d in (-1, 0, 1)]
    assert abs(pts[1] - pts[0]) < 1e-3 * pts[1] and abs(pts[2] - pts[1]) < 1e-3 * pts[1], pts
    mix = sum(after.layers["analytical"].prob[c.key] * c.recaps[0].rec for c in after.cells)
    assert mix * 1000 / after.divisor > 20 * abs(pts[1] - pts[0])      # взнос на акцию много больше переката


# ------------------------------------------------------------------ пол клетки (М§8.2, §10)


def check_floor_is_by_the_cell() -> None:
    """V0 слоя — сумма стоимостей клеток в цене; клетка выше пола не меняется; пол применён до смеси, до дисконта
    за управление; флаг `floored` — по условию V_c − D_pend < F; без ключа пола нет (М§8.2)."""
    bare, keyed = grid_of(), grid_of({FLOOR: FLOOR_HIGH})
    assert bare.cell_floor is None and keyed.cell_floor == FLOOR_HIGH and keyed.pending_dividend == 0.0
    g, n_div = keyed.governance, keyed.divisor
    assert g > 0
    below = [c for c in keyed.cells if c.v_ri < FLOOR_HIGH]
    assert 4 <= len(below) <= 30
    for c, plain in zip(keyed.cells, bare.cells):
        assert (c.v_ri, c.v_ddm, c.bv_v) == (plain.v_ri, plain.v_ddm, plain.bv_v)      # оценка клетки от пола не зависит
        assert ("floored" in c.flags) == (c.v_ri < FLOOR_HIGH) and c.flags - {"floored"} == plain.flags
        value = keyed.cell_value(c)
        assert value == (c.v_ri if c.v_ri >= FLOOR_HIGH else FLOOR_HIGH) and bare.cell_value(plain) == plain.v_ri
        assert close(keyed.cell_price(c), max(c.v_ri, FLOOR_HIGH) * (1 - g) * 1000 / n_div)     # дисконт — и на пол
    for name, layer in keyed.layers.items():
        prob = layer.prob
        v0 = sum(prob[c.key] * max(c.v_ri, FLOOR_HIGH) for c in keyed.cells)
        assert close(layer.v0, v0, rel=1e-12), name
        assert close(layer.price, price_from_v0(v0, keyed.bridge_amount, g, n_div)), name
        plain = bare.layers[name]
        adj = sum(prob[c.key] * (FLOOR_HIGH - c.v_ri) for c in below)
        assert close(layer.floor_adj, adj) and close(layer.v0 - plain.v0, adj) and adj > 0
        assert close(layer.floored_mass, sum(prob[c.key] for c in below))
        assert layer.v0 > max(plain.v0, FLOOR_HIGH) + 1.0            # «пол смеси» дал бы меньше: пол — до смеси
        assert close(layer.pb, layer.v0 / layer.bv_v) and layer.bv_v == plain.bv_v
        # разложение V0 слоя: капитал, остаточный доход, терминал, цена размывания, поправка пола
        assert close(layer.v0, layer.bv_v + layer.pv_ri_explicit + layer.pv_terminal - layer.pvd + layer.floor_adj)
        assert close(layer.pvd, sum(prob[c.key] * c.pvd for c in keyed.cells)) and layer.pvd > 0
    assert close(keyed.point, keyed.low + keyed.lam * (keyed.high - keyed.low)) and keyed.point > bare.point
    # пол ноль: меняются только клетки ниже нуля
    deep = grid_of(BIG_BUFFER)
    zero = grid_of({**BIG_BUFFER, FLOOR: 0.0})
    under = [c for c in deep.cells if c.v_ri < 0]
    assert under and [c.label for c in zero.cells if "floored" in c.flags] == [c.label for c in under]
    for name in zero.layers:
        lift = -sum(zero.layers[name].prob[c.key] * c.v_ri for c in under)
        assert close(zero.layers[name].v0 - deep.layers[name].v0, lift) and lift >= 0
    node = floor_node(keyed)
    assert floor_node(bare) is None and node["value"] == FLOOR_HIGH
    assert close(node["point_no_floor"], bare.point) and close(node["shift"], keyed.point - bare.point)
    assert close(node["layers"]["analytical"]["floor_adj"], keyed.layers["analytical"].floor_adj)
    # гейт P/B судит стоимость клетки в цене
    lo = min(c.v_ri / c.bv_v for c in keyed.cells)
    corridor = {w: [lo + 1e-6, 100.0] for w in keyed.ctx.book.get("worlds.ids")}
    pb = lambda run: next(f for f in check_gates(run) if f.name == "pb_by_world")  # noqa: E731
    assert pb(grid_of({"checks.pb_by_world": corridor})).fired
    assert not pb(grid_of({"checks.pb_by_world": corridor, FLOOR: FLOOR_HIGH})).fired


def check_floor_and_the_declared_dividend() -> None:
    """Объявленный дивиденд — вне пола: пол действует на стоимость без него, дивиденд прибавляется обратно. На
    конце квартала решения цена клетки на полу не скачет на дивиденд; скачок на экс-дату — прежний (М§8.2, §8.4)."""
    run = grid_of()
    tl = run.ctx.timeline
    end = tl.end(first_agm(run))
    rec = record(run, 40.0)
    top = max(c.v_ri for c in run.cells) * 2                # пол выше любой клетки: на полу стоят все
    before = grid_of({FLOOR: top}, live_at(end - timedelta(days=1), (rec,)))
    after = grid_of({FLOOR: top}, live_at(end, (rec,)))
    amount = 40.0 * run.ctx.prep.af.n_out / 1000
    assert close(before.pending_dividend, amount) and after.pending_dividend == 0.0 and close(after.bridge_amount, amount)
    assert all("floored" in c.flags for c in before.cells + after.cells)
    g, n_div = before.governance, before.divisor
    assert all(before.cell_value(c) == top + amount for c in before.cells)      # пол плюс объявленный дивиденд
    want = (top * (1 - g) + amount) * 1000 / n_div
    assert close(before.point, want, rel=1e-12) and close(after.point, want, rel=1e-12)
    # часть клеток на полу: экс-дата снимает ровно DPS × N_out / N_div
    v = rec.ex_date
    later = dataclasses.replace(rec, record_date=v + timedelta(days=1), ex_date=v + timedelta(days=1))
    pts = [grid_of({FLOOR: FLOOR_HIGH}, live_at(v, (r,))).point for r in (rec, later)]
    assert close(pts[0] - pts[1], -40.0 * run.ctx.prep.af.n_out / n_div, abs_=1e-6), pts


def check_band_tail() -> None:
    """Хвост полосы: у книги с полом — масса клеток на полу и сдвиг «с полом минус без пола»; без ключа — прежняя
    мера при нулевом поле; сводка взносов прогона пересчитана по клеткам (М§10)."""
    facts = fixture_facts()
    draws = 6
    for extra in ({FLOOR: FLOOR_HIGH}, None):
        book = book_of(extra)
        live = live_from_book(book, facts)
        band = U.band(book, facts, live, draws=draws, workers=1)
        tail = band.tail(band.lam)
        rows = band.rows
        level = band.levels()
        centre = lambda lo, hi: sorted(r[lo] + band.lam * (r[hi] - r[lo]) for r in rows)  # noqa: E731
        printed = centre("low", "high")
        if extra:
            assert all(k in rows[0] for k in U.FLOOR_FIELDS)
            assert all(r["low_floor"] == r["low"] and r["high_floor"] == r["high"] for r in rows)
            bare = centre("low_nofloor", "high_nofloor")
            assert close(tail["floor_shift"]["low"], U.quantile(printed, level[0]) - U.quantile(bare, level[0]))
            assert close(tail["floor_shift"]["median"], U.quantile(printed, level[2]) - U.quantile(bare, level[2]))
            assert tail["floored"]["draws"] > 0 and tail["floor_shift"]["median"] > 0
            assert close(tail["floored"]["mass"], sum(r["floored_mass"] for r in rows) / draws)
        else:
            assert not any(k in rows[0] for k in U.FLOOR_FIELDS) and "floored" not in tail
            floored = centre("low_floor", "high_floor")
            assert close(tail["floor_shift"]["median"], U.quantile(floored, level[2]) - U.quantile(printed, level[2]))
            assert tail["floor_shift"]["median"] >= 0
        mix = lambda r, k: r[f"{k}_low"] + band.lam * (r[f"{k}_high"] - r[f"{k}_low"])  # noqa: E731
        assert close(tail["recap"]["pvr"], sum(mix(r, "pvr") for r in rows) / draws)
        assert close(tail["recap"]["pvrt"], sum(mix(r, "pvrt") for r in rows) / draws)
        assert close(tail["recap"]["mass"], sum(r["recap_mass"] for r in rows) / draws)
    assert "recap_mass" not in U.run_summary(fixture_run()) and "floored_mass" not in U.run_summary(fixture_run())
    # сводка прогона — по клеткам: масса под весами «свой взгляд», приведённые суммы — под весами своих слоёв
    run = grid_of()
    row = U.run_summary(run)
    lo, hi = run.layers["macro_neutral"].prob, run.layers["analytical"].prob
    assert abs(sum(hi[c.key] - lo[c.key] for c in run.cells if "recapitalization" in c.flags)) > 0.05
    assert close(row["recap_mass"], sum(hi[c.key] for c in run.cells if "recapitalization" in c.flags))
    for side, prob in (("low", lo), ("high", hi)):
        pvr = sum(prob[c.key] * sum(_contributions(run, c)[:2]) for c in run.cells)
        assert close(row[f"pvr_{side}"], pvr) and pvr > 0
        assert close(row[f"pvrt_{side}"], sum(prob[c.key] * _contributions(run, c)[2] for c in run.cells))
    undiscounted = sum(hi[c.key] * sum(c.quarters["rec"][1:]) for c in run.cells)
    assert row["pvr_high"] < undiscounted - 1.0


# ------------------------------------------------------------------ путь числа акций (М§6.6)


def check_share_path() -> None:
    """W_0 равно оценке клетки; стоимость на акцию через взнос не скачет; дивиденд квартала собрания — на акции
    до взноса этого квартала; обрыв пути при неположительной стоимости до взноса — доля ноль, DPS ноль; акции
    смеси — по ожидаемой доле (М§6.6)."""
    run = grid_of()
    p, q0 = run.ctx.prep, run.ctx.clock.q0
    d, n_div = p.recap_discount, run.divisor
    assert d == 0.1
    stepped = diluted = 0
    for c in run.cells:
        disc = run.ctx.discounts[c.world]
        div = [x or 0.0 for x in c.quarters["div"]]
        rec = [x or 0.0 for x in c.quarters["rec"]]
        kw = dict(q0=q0, disc=disc, div=div, rec=rec, term=_terminal_of(c), discount=d)
        assert close(shares_value(0, **kw), c.v_ddm), c.label
        sp = c.shares
        assert sp.n[0] == n_div and sp.stake[0] == 1.0
        for q in range(1, len(rec)):
            if rec[q] > 0 and sp.n[q] is not None:
                w = shares_value(q, **kw)
                old = w - rec[q] / (1 - d)
                assert close(sp.w[q][0], w) and close(sp.w[q][1], old) and old > 0
                assert close(w / sp.n[q], old / sp.n[q - 1], rel=1e-12), (c.label, q)      # цена акции не скачет
                assert close(sp.stake[q], n_div / sp.n[q], rel=1e-12) and sp.n[q] > sp.n[q - 1]
                stepped += 1
            elif sp.n[q] is not None:
                assert sp.n[q] == sp.n[q - 1] and sp.stake[q] == sp.stake[q - 1]
        years = list(c.years)
        for dec in c.decisions:
            q_a = next(r.q for r in c.recaps if r.year == dec.year)
            extra = sp.n[q_a - 1] - n_div
            want = dec.div * 1000 / (p.af.n_out + extra)
            assert close(c.dps[dec.year], want, rel=1e-12), (c.label, dec.year)
            if extra > 0 and dec.div > 0:
                assert c.dps[dec.year] < dec.dps and c.quarters["rec"][q_a] >= 0
                diluted += 1
            # доля выплаты года — от суммы дивиденда, а не от DPS на акции своего года
            i = years.index(dec.year)
            ni = c.annual["ni_sh"][i]
            assert close(c.annual["payout"][i], dec.dps * p.af.n_iss / 1000 / ni), (c.label, dec.year)
        for i, y in enumerate(years):
            end = run.ctx.timeline.quarters_of_year(y)[-1]
            assert c.annual["stake"][i] == sp.stake[end] and c.annual["shares"][i] == sp.n[end]
            assert close(c.annual["rec"][i], sum(rec[q] for q in run.ctx.timeline.quarters_of_year(y) if q >= 1))
    assert stepped >= 30 and diluted >= 30, (stepped, diluted)
    # дивиденд квартала собрания — на акции до взноса этого квартала
    c = run.cell("H", "norm", "upper")
    first = c.recaps[0]
    assert first.rec > 0 and first.div > 0 and c.dps[first.year] == c.decisions[0].dps
    # обрыв пути: стоимость акций до взноса не больше нуля
    deep = grid_of(BIG_BUFFER)
    broken = [c for c in deep.cells if c.shares.broken is not None]
    assert broken
    for c in broken:
        q = c.shares.broken
        assert c.shares.w[q][1] <= 0 and all(n is None for n in c.shares.n[q:]) and not any(c.shares.stake[q:])
        later = [dec.year for dec in c.decisions if next(r.q for r in c.recaps if r.year == dec.year) > q]
        assert later and all(c.dps[y] == 0.0 for y in later)
    # узел таблиц: акции смеси — число акций, отвечающее ожидаемой доле, а не ожидание числа акций
    node = recap_node(run)
    assert recap_node(fixture_run()) is None
    prob = {c.key: run.layers["macro_neutral"].prob[c.key] + run.lam * (run.layers["analytical"].prob[c.key]
                                                                         - run.layers["macro_neutral"].prob[c.key])
            for c in run.cells}
    i = len(node["years"]) - 1
    stake = sum(prob[c.key] * c.annual["stake"][i] for c in run.cells)
    mean_shares = sum(prob[c.key] * c.annual["shares"][i] for c in run.cells)
    assert close(node["mix"]["stake"][i], stake) and close(node["mix"]["shares"][i], n_div / stake)
    assert abs(n_div / stake - mean_shares) > 1.0
    assert close(node["mix"]["rec"][1], sum(prob[c.key] * c.annual["rec"][1] for c in run.cells))
    assert close(node["mix"]["mass"][1], sum(prob[c.key] for c in run.cells if c.annual["rec"][1] > 0))
    pt = node["layers"]["point"]
    assert close(pt["dilution"], sum(prob[c.key] * c.pvd for c in run.cells))
    assert close(pt["dilution_per_share"], pt["dilution"] * 1000 / n_div)
    within = sum(prob[c.key] * sum(min(r.div_model, r.rec) * run.ctx.discounts[c.world].dfq[r.q]
                                   for r in c.recaps if r.rec > 0) for c in run.cells)
    assert close(pt["dividend_within_recap"], within) and within > 0
    assert close(pt["recap_with_dividend_mass"], sum(prob[c.key] for c in run.cells if "recap_with_dividend" in c.flags))
    assert close(node["residual_max"], max(r.residual / r.rec for c in run.cells for r in c.recaps if r.rec > 0))


# ------------------------------------------------------------------ гейт капитального разрыва (М§14.2)


def check_capital_gap_gate() -> None:
    """Гейт `capital_gap` молчит в клетке, где взнос закрыл разрыв, и срабатывает, где разрыв остался до квартала
    собрания; условие — по окончательному пути клетки (М§14.2)."""
    gate = lambda run: next(f for f in check_gates(run) if f.name == "capital_gap")  # noqa: E731
    open_, healed = grid_of({**LOSS, f"{RECAP}.enabled": False}), grid_of(LOSS)
    was = [c.label for c in open_.cells if "capital_gap" in c.flags]
    assert len(was) >= 6 and not [c.label for c in healed.cells if "capital_gap" in c.flags]
    assert gate(open_).fired and not gate(healed).fired
    assert all("recapitalization" in healed.cell(*label.split("/")).flags for label in was)
    assert "масса клеток со взносом" in gate(healed).message and "взнос" not in gate(open_).message
    deep = grid_of(DEEP_LOSS)
    q_a = first_agm(deep)
    cut = [c for c in deep.cells if "capital_gap" in c.flags]
    assert len(cut) >= 6 and gate(deep).fired
    for c in cut:
        runs = gap_runs(c)
        assert runs == [(q_a - 1, q_a - 1)], (c.label, runs)       # один квартал ниже пола — до первого собрания
        assert c.recaps[0].rec > 0 and "recapitalization" in c.flags
    assert f"взнос акционеров есть в {len(cut)} клет" in gate(deep).message
    assert "кварталов подряд ниже пола — 1" in gate(deep).message
    longer = grid_of({**DEEP_LOSS, f"{RECAP}.enabled": False})
    assert max(b - a + 1 for c in longer.cells for a, b in gap_runs(c)) > 4


# ------------------------------------------------------------------ пример приложения D


def example_decisions(lookahead: int) -> dict[int, tuple]:
    """Решения о взносе примера по нормативам его пробных проходов — формулой ядра `model.capital.shortfall`."""
    inp = EXAMPLE["input"]
    out = {}
    for q_a, points in inp["trials"].items():
        q_a = int(q_a)
        last = min(q_a + lookahead, int(inp["Q"]))
        rows = []
        for c in range(q_a, last + 1):
            n20, n11, dpreg, rwa, req20, req11 = map(float, points[str(c)])
            row = {"n20": n20 / PCT, "n11": n11 / PCT, "dpreg": dpreg, "rwa": rwa, "req20": req20 / PCT,
                   "req11": req11 / PCT}
            rows.append(shortfall(row, c, last=c == last))
        gap, worst, norm = worst_point(rows)
        out[q_a] = (rows, gap, worst.q, norm, gap if gap > float(inp["min_amount"]) else 0.0)
    return out


def example_value(q0: int, discount: float, pbt: float | None = None):
    """Терминал и оценка примера функциями ядра: плоский дисконт k за квартал, дата оценки — конец квартала q0 − 1."""
    inp = EXAMPLE["input"]
    n = int(inp["Q"])
    k = float(inp["k_quarter"])
    dfq = [1.0] * (n + 1)
    kq = [0.0] * (n + 1)
    for q in range(q0, n + 1):
        dfq[q], kq[q] = (1 + k) ** (-(q - q0 + 1)), k
    k_t = (1 + k) ** 4 - 1
    disc = Discount(k=tuple(kq), k_t=k_t, dfq=tuple(dfq), curve=None, roll=0.0)
    t = inp["terminal"]
    term = terminal(
        n20=float(t["n20_t"]) / PCT, req20=float(t["req20"]) / PCT, n11_star=float(t["n11_t"]) / PCT,
        req11=float(t["req11"]) / PCT, rwa=float(t["rwa"]), bv_q=EXAMPLE["bv"][n],
        pbt_last_year=float(t["pbt_last_year"]) if pbt is None else pbt, y_balancing=float(t["y_balancing"]),
        c_wholesale=float(t["c_wholesale"]), headroom=0.0, tau_eff=float(t["tau_eff"]),
        nci_share=float(t["nci_share"]), coupon_annual=float(t["coupon_annual"]), tau_stat=0.0,
        lt_inflation=float(t["g_t"]), real_growth=0.0, fade=float(t["fade"]),
        multiple=float(t["excess_capital_multiple"]), k_t=k_t, wholesale_extra=float(t["wholesale_extra"]),
        discount=discount)
    val = value_cell(q0=q0, elapsed=0.0, disc=disc, bv=EXAMPLE["bv"], ci=EXAMPLE["ci"], div=EXAMPLE["div"],
                     term=term, rec=EXAMPLE["rec"], discount=discount)
    return disc, term, val


def check_example() -> None:
    """Пример приложения D воспроизводится функциями ядра до 1e-9: решения о взносе (окна L = 3 и L = 0), капитал,
    терминал, обе формы оценки, цена размывания, дата оценки после квартала взноса, путь акций, вариант с
    отрицательной выплатой терминала, объявленным дивидендом и полом клетки."""
    inp = EXAMPLE["input"]
    near = lambda a, b: abs(a - b) <= EXAMPLE_TOL  # noqa: E731
    for lookahead, node in ((int(inp["lookahead_quarters"]), "decisions"), (0, "decisions_window_0")):
        for q_a, (rows, gap, point, norm, rec) in example_decisions(lookahead).items():
            want = EXAMPLE[node][str(q_a)]
            assert near(gap, want["shortfall"]) and (point, norm) == (want["point"], want["norm"]), (q_a, gap, norm)
            assert near(rec, want["rec"])
            for pt in rows:
                assert near(pt.s20, want["points"][str(pt.q)]["s20"]) and near(pt.s11, want["points"][str(pt.q)]["s11"])
            if node == "decisions":
                assert near(rec, EXAMPLE["rec"][q_a])
    n = int(inp["Q"])
    bv = float(inp["bv0"])
    for q in range(1, n + 1):                       # капитал: BV_q = BV_(q−1) + CI_q − Div_q + Rec_q
        bv += EXAMPLE["ci"][q] - EXAMPLE["div"][q] + EXAMPLE["rec"][q]
        assert near(bv, EXAMPLE["bv"][q]), q
    d = float(inp["price_discount"])
    disc, term, val = example_value(1, d)
    for key in ("x_t", "bv_star", "y_x", "ni_t1", "ci_t1", "tv_ri", "p_t", "tv_ddm", "dc_t", "g_t", "k_t"):
        assert near(getattr(term, key), EXAMPLE["terminal"][key]), key
    want = EXAMPLE["valuation"]
    assert near(val.v_ri, want["v_ri"]) and near(val.v_ddm, want["v_ddm"]) and near(val.v_ri, val.v_ddm)
    assert near(val.pvd, want["pvd"]) and near(val.pv_rec, want["pv_rec"]) and near(val.c_v, want["c_v"])
    assert near(val.pv_rec_terminal, want["pv_rec_terminal"]) and near(val.bv_v, want["bv_v_current"])
    assert near(val.pv_ri_explicit, want["pv_ri"]) and near(val.pv_terminal, want["pv_tv_ri"])
    assert near(val.pv_div_explicit, want["pv_div"])
    assert all(near(a, b) for a, b in zip(val.ri, want["ri"]))
    _, term0, val0 = example_value(1, 0.0)
    assert near(val0.v_ri, EXAMPLE["at_zero_discount"]["v_ri"]) and near(val0.v_ddm, val0.v_ri) and term0.dc_t == 0.0
    assert near(val0.v_ri - val.v_ri, want["pvd"])
    # путь акций
    n_div, n_out = float(inp["shares"]["n_div"]), float(inp["shares"]["n_out"])
    sp = share_path(q0=1, disc=disc, div=EXAMPLE["div"], rec=EXAMPLE["rec"], term=term, discount=d, n_div=n_div)
    shares = EXAMPLE["shares"]
    assert sp.broken is None
    assert all(near(a, b) for a, b in zip(sp.n, shares["n"])) and all(near(a, b) for a, b in zip(sp.stake, shares["stake"]))
    for q, w in shares["w"].items():
        assert near(sp.w[int(q)][0], w["w"]) and near(sp.w[int(q)][1], w["pre_money"])
    for q_a, dps in shares["dps"].items():
        assert near(EXAMPLE["div"][int(q_a)] * 1000 / (n_out + sp.n[int(q_a) - 1] - n_div), dps), q_a
    assert near(shares_value(0, q0=1, disc=disc, div=EXAMPLE["div"], rec=EXAMPLE["rec"], term=term, discount=d),
                val.v_ddm)
    # дата оценки после квартала первого взноса
    closed = EXAMPLE["closed_quarter"]["valuation"]
    _, _, late = example_value(int(closed["q0"]), d)
    assert near(late.v_ri, closed["v_ri"]) and near(late.v_ddm, closed["v_ddm"]) and near(late.c_v, closed["c_v"])
    assert near(late.pvd, closed["pvd"]) and near(late.bv_v, closed["bv_v_current"])
    assert near(late.v_ri, EXAMPLE["closed_quarter"]["check_roll"])
    assert near(late.v_ri, sp.w[2][1])              # она же — стоимость акций до взноса из пути акций
    # вариант: отрицательная выплата терминала, объявленный дивиденд, пол клетки
    var, vin = EXAMPLE["variant_b"], inp["variant_b"]
    disc_b, term_b, val_b = example_value(1, d, float(vin["pbt_last_year"]))
    for key in ("x_t", "tv_ri", "p_t", "tv_ddm", "dc_t"):
        assert near(getattr(term_b, key), var["terminal"][key]), key
    assert term_b.x_t < 0 and term_b.p_t < 0
    assert near(val_b.v_ri, var["valuation"]["v_ri"]) and near(val_b.v_ddm, val_b.v_ri)
    pend, g = float(vin["d_pend"]), float(vin["governance"])
    floored = floor_value(val_b.v_ri, pend, float(inp["cell_floor"]))
    assert near(floored, var["v_floored"]) and near(price_from_v0(floored, 0.0, g, n_div, pend), var["price"])
    sp_b = share_path(q0=1, disc=disc_b, div=EXAMPLE["div"], rec=EXAMPLE["rec"], term=term_b, discount=d, n_div=n_div)
    assert sp_b.broken == 2 and near(sp_b.w[2][1], var["shares"]["w"]["2"]["pre_money"])
    assert list(sp_b.stake) == var["shares"]["stake"]


# ------------------------------------------------------------------ узлы таблиц книги и выпуска (М§14.5)


def release_of(extra: Mapping[str, Any] | None = None, *, keyed: bool = True, draws: int = 6) -> dict:
    """Быстрый выпуск на книге фикстуры докапитализации с подменами (`keyed=False` — на книге фикстуры формы
    образца, без ключей): гейты объяснены, слоя индикаторов нет."""
    from model import payload as P
    from tests.support_core2 import control_fixture, TODAY, explained

    book, facts = (book_of(extra) if keyed else fixture_book()), fixture_facts()
    run = run_grid(book, facts, live_from_book(book, facts))
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts,
                         explanations=explained(check_gates(run, today=TODAY)), notes=[], draws=draws,
                         control_model=control_fixture(book))
    return P.build_payload(rel)


def check_nodes_only_with_keys(tables: bool = False) -> None:
    """Узлы взносов и пола появляются только при своих ключах: в таблицах книги и в выпуске; контракт выпуска
    книги с ключами выполнен — разложение V0 слоя и водопад несут цену размывания и поправку пола (М§14.5, П§2).
    `tables` — собрать и сами таблицы книги (быстрая полоса): это делает тест, мутационный набор сверяет строки."""
    from model import book_results as BR
    from model import payload as P
    from tests.support_core2 import contract

    plain, recap, both = release_of(keyed=False), release_of(), release_of({FLOOR: FLOOR_HIGH})
    for d in (plain, recap, both):
        assert not contract(d), contract(d)[:5]
        assert all(i["ok"] for i in d["checks"]["invariants"]), [i for i in d["checks"]["invariants"] if not i["ok"]]
    names = lambda d: [i["name"] for i in d["checks"]["invariants"]]  # noqa: E731
    assert names(plain) == list(P.ORDER_INVARIANTS) and "recap_covers_gap" not in names(plain)
    assert names(recap) == list(P.invariant_order(True)) and names(recap).index("recap_covers_gap") == 5
    # без ключей — ни узлов, ни строк, ни полей
    assert "recapitalization" not in plain["capital"] and "cell_floor" not in plain["fair_value"]
    assert all("dilution" not in L and "floor_adj" not in L for L in plain["layers"].values())
    assert [r["key"] for r in plain["layers"]["headline_mix"]["waterfall"]] == [
        "bv_v", "pv_ri_explicit", "pv_terminal", "v0", "governance", "bridge", "equity"]
    assert all("v_floor" not in c and "pvd" not in c for c in plain["grid"]["cells"])
    assert "recapitalization" not in [r["key"] for r in plain["capital"]["bridge"]["rows"]]
    flags = lambda d: {f for c in d["grid"]["cells"] for f in c["flags"]}  # noqa: E731
    assert not flags(plain) & {"recapitalization", "recap_with_dividend", "floored"}
    # докапитализация без пола
    assert "recapitalization" in recap["capital"] and "cell_floor" not in recap["fair_value"]
    assert {"recapitalization", "recap_with_dividend"} <= flags(recap) and "floored" not in flags(recap)
    assert [r["key"] for r in recap["layers"]["headline_mix"]["waterfall"]][3:5] == ["dilution", "v0"]
    assert "recapitalization" in [r["key"] for r in recap["capital"]["bridge"]["rows"]]
    run = grid_of()
    node, got = recap_node(run), recap["capital"]["recapitalization"]
    assert got["years"] == node["years"] and got["modal_cell"]["cell"] == node["modal_cell"]["cell"]
    assert all(close(a, b, abs_=0.01) for a, b in zip(got["mix"]["rec"], node["mix"]["rec"]))
    assert close(got["layers"]["point"]["dilution"], node["layers"]["point"]["dilution"], abs_=0.01)
    for name in ("analytical", "market_implied", "macro_neutral"):
        L = recap["layers"][name]
        assert close(L["dilution"], run.layers[name].pvd, abs_=0.01) and L["dilution"] > 0
        assert close(L["v0"], L["bv_v"] + L["pv_ri_explicit"] + L["pv_terminal"] - L["dilution"], abs_=0.05)
    # докапитализация и пол
    floor = both["fair_value"]["cell_floor"]
    keyed = grid_of({FLOOR: FLOOR_HIGH})
    assert floor["value"] == FLOOR_HIGH and "floored" in flags(both)
    assert close(floor["shift"], keyed.point - run.point, abs_=0.011) and floor["band"]["draws"] > 0
    rows = {r["key"]: r["amount"] for r in both["layers"]["headline_mix"]["waterfall"]}
    assert rows["cell_floor"] > 0 > rows["dilution"]
    assert close(rows["bv_v"] + rows["pv_ri_explicit"] + rows["pv_terminal"] + rows["dilution"] + rows["cell_floor"],
                 rows["v0"], abs_=0.05)
    for c, cell in zip(both["grid"]["cells"], keyed.cells):
        assert close(c["v_floor"], max(cell.v_ri, FLOOR_HIGH), abs_=0.01) and close(c["v"], cell.v_ri, abs_=0.01)
        assert close(c["pb"], max(cell.v_ri, FLOOR_HIGH) / cell.bv_v, abs_=1e-4)
    # таблицы книги: поля строк слоя и клетки — только при ключах
    base = fixture_run()
    assert BR._layer(base.layers["analytical"], base).keys() == BR._layer(base.layers["analytical"]).keys()
    assert BR._cell_extra(base, base.cells[0]) == {}
    row = BR._layer(keyed.layers["analytical"], keyed)
    assert (row["pvd"], row["floor_adj"], row["floored_mass"]) == (
        keyed.layers["analytical"].pvd, keyed.layers["analytical"].floor_adj, keyed.layers["analytical"].floored_mass)
    cell = keyed.cells[-1]
    assert BR._cell_extra(keyed, cell) == {"pvd": cell.pvd, "c_v": cell.c_v, "pv_rec": cell.pv_rec,
                                           "pv_rec_terminal": cell.pv_rec_terminal, "dc_t": cell.dc_t,
                                           "v_floor": keyed.cell_value(cell)}
    assert set(BR._cell_extra(run, run.cells[0])) == {"pvd", "c_v", "pv_rec", "pv_rec_terminal", "dc_t"}
    if tables:                                  # и сами таблицы: узлы и слова сводки
        book = book_of({FLOOR: FLOOR_HIGH})
        res = BR.book_results(book, fixture_facts(), slow=False)
        assert {"recapitalization", "cell_floor"} <= set(res) and "pvd" in res["layers"]["analytical"]
        assert all("v_floor" in c and "pvd" in c for c in res["cells"])
        text = BR.render_run_output(json.loads(json.dumps(res, default=BR._default)), book)
        assert "ВЗНОСЫ АКЦИОНЕРОВ" in text and "ПОЛ КЛЕТКИ" in text and "recap_covers_gap" in text
        res = BR.book_results(fixture_book(), fixture_facts(), slow=False)
        assert not {"recapitalization", "cell_floor"} & set(res)
        assert "recap_covers_gap" not in [c["name"] for c in res["checks"]]
