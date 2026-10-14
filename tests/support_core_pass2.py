"""Проверки второго прохода ядра (строки М§18): квартал решения о взносе и нижняя граница окна, состав точек
инварианта, правило «при равенстве», DPS с поправкой делителя, норма клетки, срок избыточной доходности; общие
правила ядра — число клеток по перечням книги и клетка нулевой вероятности, допуск сверки заголовка, база
ожидания нау-каста, сводка контрольной модели своей книги, оси полосы на общем пути.

Фикстуры — формы образца `tests/fixtures/core` и `core_t` с подменами теста; фикстура докапитализации —
`tests/support_core_recap.py`; общий числовой пример — `tests/fixtures/core_recap/example_q4.json` (приложение E
методики). Каждая проверка — тождество или закрытая формула, выведенная из книги, фактов и рядов клетки независимо
от кода ядра: недостаток решения пересчитывается по рядам сетки без взносов и своим пробным проходом (шаги квартала
— ядра, порядок прохода и формула недостатка — теста). Те же функции зовут тесты `tests/test_core_pass2.py` и
мутационный набор `tests/mutations.py`.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import math
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Mapping

from model import uncertainty as U
from model.book import Book, book_from_dict
from model.book_schema import BookError, window_floor
from model.capital import RECAP_RESIDUAL_SHARE, RecapDecision, invariant_span, residual_points, shortfall, worst_point
from model.cell import _Cell, own_year_dps, recap_residuals
from model.checks import check_gates, check_invariants, ddm_ri_max
from model.grid import GridRun, cell_norm_of, judged_cells, live_from_book, point_probabilities, run_grid
from model.levels import recap_node
from model.reverse import excess_by_year
from model.valuation import cell_norm, share_path
from tests import support_core_recap as R
from tests.support_core import fixture_book, fixture_dict, fixture_facts, fixture_run
from tests.support_core_recap import FIXTURE_RECAP, FLOOR, HUGE, RECAP, close, grid_of

EXAMPLE_Q4: dict[str, Any] = json.loads((FIXTURE_RECAP / "example_q4.json").read_text(encoding="utf-8"))
TOL = 1e-9                                   # допуск примера приложения E (М§17)
PCT = 100.0
AGM, DEDUCTION = 2, 3                        # календарь фикстуры формы образца: собрание — 2-й квартал, вычет — 3-й
# запас менеджмента, при котором клетка и платит дивиденд, и привлекает взнос под ступень следующего года
MID_BUFFER = {"capital.mgmt_buffer.n20_0": 0.04, "capital.mgmt_buffer.n1_1": 0.027}
QUARTER = f"{RECAP}.decision_quarter"
LOOK = f"{RECAP}.lookahead_quarters"
AMOUNT = f"{RECAP}.min_amount"


def keyed(quarter: int | None, lookahead: int, **extra: Any) -> dict[str, Any]:
    """Подмены фикстуры докапитализации: квартал решения (None — без ключа), окно и добавочные поля."""
    out: dict[str, Any] = {LOOK: lookahead}
    if quarter is not None:
        out[QUARTER] = quarter
    out.update({k.replace("__", "."): v for k, v in extra.items()})
    return out


def plain_of(extra: Mapping[str, Any] | None = None, live: Any = None) -> GridRun:
    """Сетка той же книги с выключенным механизмом: путь клетки без взносов."""
    return grid_of({**(extra or {}), f"{RECAP}.enabled": False}, live)


def decision_quarters(run: GridRun) -> list[int]:
    """Кварталы решения о взносе сетки: номер в году — h_R, кроме последнего квартала сетки (М§4.14.1)."""
    tl, rule = run.ctx.timeline, run.ctx.prep.recap
    return [q for q in range(1, tl.Q) if tl.h(q) == rule.quarter]


# ------------------------------------------------------------------ квартал решения (М§4.14.1, §4.14.3)


def check_key_equal_to_the_agm_quarter() -> None:
    """Ключ `decision_quarter`, равный кварталу собрания, — ряды и оценка книги без ключа бит в бит (свойство 10
    М§4.14.5); узел таблиц несёт действующий квартал решения всегда."""
    bare, same = grid_of(), grid_of({QUARTER: AGM})
    R.cells_equal(bare, same)
    for a, b in zip(bare.cells, same.cells):
        assert a.recaps == b.recaps and a.shares == b.shares and a.terminal_share == b.terminal_share, a.label
    assert recap_node(bare)["decision_quarter"] == AGM == recap_node(same)["decision_quarter"]
    assert recap_node(grid_of(keyed(4, 1)))["decision_quarter"] == 4
    assert bare.ctx.prep.recap.span == 4 and grid_of(keyed(4, 1)).ctx.prep.recap.span == 2


def check_decisions_stand_in_the_decision_quarter() -> None:
    """Взносы стоят только в кварталах с номером h_R и не стоят в последнем квартале сетки; решение принимается
    в каждом таком квартале — и в году якоря, и в первом прогнозном квартале; называется годом Y(q_R) − 1; ключ
    доходит до прохода клеток (М§4.14.1, §4.14.3)."""
    for quarter, lookahead in ((1, 1), (3, 1), (4, 1), (None, 3)):
        run = grid_of(keyed(quarter, lookahead, **{AMOUNT.replace(".", "__"): 0.0}))
        tl, rule = run.ctx.timeline, run.ctx.prep.recap
        assert rule.quarter == (AGM if quarter is None else quarter)
        want = decision_quarters(run)
        assert want and all(tl.h(q) == rule.quarter for q in want) and tl.Q not in want
        made = 0
        for c in run.cells:
            assert [r.q for r in c.recaps] == want, (c.label, quarter)
            assert all(r.year == tl.year(r.q) - 1 and r.last == min(r.q + lookahead, tl.Q) for r in c.recaps)
            rec = c.quarters["rec"]
            assert all(rec[q] == 0.0 for q in range(1, tl.Q + 1) if q not in want) and rec[tl.Q] == 0.0, c.label
            assert all(rec[r.q] == r.rec for r in c.recaps)
            made += sum(1 for r in c.recaps if r.rec > 0)
        assert made >= 20, (quarter, made)
        if quarter == 3:                        # якорь — конец второго квартала: решение в первом прогнозном квартале
            assert want[0] == 1 and tl.year(1) == tl.anchor_year
        if quarter == 4:                        # решение в году якоря — второй прогнозный квартал
            assert want[0] == 2 and tl.year(2) == tl.anchor_year and want[-1] == tl.Q - 4
        if quarter == 1:
            assert want[0] == 3 and want[-1] == tl.Q - 3


def _own_shortfall(q_: Mapping[str, Any], q_r: int, last: int, skip: Mapping[int, float] | None = None
                   ) -> tuple[float, int, str]:
    """Недостаток окна q_R … last по рядам кварталов — своей формулой (М§4.14.1 п. 3): отчётные нормативы против
    требований, в последней точке — без дивидендов, не вычтенных из регуляторного капитала. `skip` — квартал →
    сумма, которую из DPreg этого квартала надо убрать: дивиденд нового решения, которого пробный проход не нёс.
    → (S, точка c*, норматив j*) по правилу «при равенстве»: самая ранняя точка в 1e-9 от наибольшего, Н20.0."""
    rows = []
    for c in range(q_r, last + 1):
        pending = (q_["dpreg"][c] - (skip or {}).get(c, 0.0)) / q_["rwa"][c] if c == last else 0.0
        rows.append((c, (q_["req20"][c] - (q_["n20"][c] - pending)) * q_["rwa"][c],
                     (q_["req11"][c] - (q_["n11"][c] - pending)) * q_["rwa"][c]))
    top = max(max(s20, s11) for _, s20, s11 in rows)
    c, s20, s11 = next(row for row in rows if max(row[1], row[2]) >= top - 1e-9)
    return top, c, "n20" if s20 >= s11 - 1e-9 else "n11"


def check_first_decision_by_the_plain_grid() -> None:
    """Первое решение воспроизводится по сетке книги с выключенным механизмом (свойство 11 М§4.14.5): до первого
    взноса путь клетки — путь той же клетки без механизма, и недостаток решения — недостаток шага 3 по её строкам
    в точках окна. Если последняя точка окна — квартал собрания после квартала решения, из DPreg её строки
    убирается дивиденд нового решения: пробный проход его не несёт — так проверяется правило «новых решений в
    окне нет». Случаи: решение в четвёртом квартале с окном 1 (обе точки — до собрания) и с окном 2 (последняя
    точка — собрание); решение в квартал собрания с окном 4 (последняя точка — следующее собрание); решение в
    первом квартале, до собрания, с окном 1 (последняя точка — собрание этого же года)."""
    for quarter, lookahead in ((4, 1), (4, 2), (None, 4), (1, 1), (3, 0)):
        extra = keyed(quarter, lookahead)
        run, plain = grid_of(extra), plain_of(extra)
        tl, rule = run.ctx.timeline, run.ctx.prep.recap
        agm = run.ctx.prep.policy.agm_quarter
        checked = made = removed = 0
        for c, p in zip(run.cells, plain.cells):
            for dec in c.recaps:
                last = min(dec.q + lookahead, tl.Q)
                later = [x for x in range(dec.q + 1, last + 1) if tl.h(x) == agm]   # собрание в окне после q_R
                assert all(x == last for x in later), (quarter, lookahead)       # случаи выбраны так
                skip = {x: p.quarters["div"][x] for x in later}
                removed += sum(1 for v in skip.values() if v > 0)
                s, point, norm = _own_shortfall(p.quarters, dec.q, last, skip)
                assert close(dec.shortfall, s, rel=1e-12), (c.label, quarter, lookahead, dec.q, dec.shortfall, s)
                assert (dec.last, dec.point, dec.norm) == (last, point, norm), (c.label, dec.q)
                assert [pt.q for pt in dec.points] == list(range(dec.q, last + 1))
                assert close(dec.rec, s if s > rule.min_amount else 0.0, rel=1e-12), c.label
                checked += 1
                if dec.rec > 0:                 # дальше путь клетки несёт взнос: сверяется только первое решение
                    # взнос — не прибыль: неаудированная прибыль квартала взноса та же, отчётный K11 выше на взнос
                    a, b, q = c.quarters, p.quarters, dec.q
                    assert a["e_unaudited"][q] == b["e_unaudited"][q] and a["ci"][q] == b["ci"][q], c.label
                    assert close(a["k11"][q] - b["k11"][q], dec.rec - (a["ded11"][q] - b["ded11"][q]), rel=1e-12), c.label
                    assert close(a["k20"][q] - b["k20"][q], dec.rec - (a["ded20"][q] - b["ded20"][q]), rel=1e-12), c.label
                    made += 1
                    break
        assert checked >= 36 and made >= (5 if lookahead == 0 else 15), (quarter, lookahead, checked, made)
        if (quarter, lookahead) in ((4, 2), (None, 4), (1, 1)):
            assert removed >= 10, (quarter, lookahead, removed)   # в окне был дивиденд нового решения


def _replay(run: GridRun, c: Any, dec: RecapDecision) -> tuple[float, int, str]:
    """Пробный проход решения `dec` клетки `c` — порядком теста (М§4.14.1 п. 2): состояние на конец q_R − 1 —
    проходом ядра; в квартале q_R — дивиденд, решённый в самом этом квартале (только при решении в квартал
    собрания), со своими кварталами вычета и выплаты; в остальных кварталах окна — шаг без новых решений; взноса
    нет. Недостаток — формулой теста."""
    ctx = run.ctx
    p, tl = ctx.prep, ctx.timeline
    pol = p.policy
    cell = _Cell(ctx, c.world, c.regime, c.scenario, shared={})
    _, decisions, st = cell.run(until=dec.q - 1)
    div = pay_q = reg_q = None
    if tl.h(dec.q) == pol.agm_quarter:          # решение о дивиденде этого же квартала — своим вызовом шагов 1–6
        _, upto, _ = _Cell(ctx, c.world, c.regime, c.scenario, shared={}).run(until=dec.q)
        if len(upto) > len(decisions):
            from model.timeline import period_str
            year = tl.year(dec.q) - 1
            div = upto[-1].div
            pay_q = max(dec.q, p.pay_q_by_year.get(year, tl.index(period_str(year + 1, pol.pay_quarter))))
            reg_q = max(dec.q, p.reg_q_by_year.get(year, tl.index(period_str(year + 1, pol.reg_quarter))))
    trial = st.clone()
    rows: dict[str, dict[int, float]] = {k: {} for k in ("n20", "n11", "dpreg", "rwa", "req20", "req11")}
    for x in range(dec.q, dec.last + 1):
        row = cell.step(trial, x, div, pay_q, reg_q) if x == dec.q and div is not None else cell.step(trial, x, 0.0)
        for k in rows:
            rows[k][x] = row[k]
    return _own_shortfall(rows, dec.q, dec.last)


def check_trial_pass_carries_no_new_decisions() -> None:
    """Пробный проход взноса — с принятыми дивидендами, без взноса и без новых решений в кварталах после q_R
    (М§4.14.1 п. 2): недостаток каждого из первых решений клетки равен недостатку пробного прохода, собранного
    тестом из шагов квартала с состояния на конец q_R − 1. Случаи: окно, в которое попал следующий квартал
    решения (решение в квартал собрания, L = 4 и L = 5; решение в первом квартале, L = 4 — последняя точка —
    ступень требования следующего года); решение между собранием и вычетом дивиденда (собрание — 2-й квартал,
    вычет — 4-й, решение — 3-й: принятый дивиденд стоит в очередях состояния); решение до собрания."""
    late = {"dividends.calendar": {"agm_quarter": 2, "reg_deduction_quarter": 4, "payment_quarter": 4,
                                   "checkpoints": [4]}}
    cells = (("N", "norm", "schedule"), ("H", "norm", "upper"), ("M", "downturn", "upper"), ("H", "downturn", "strict"),
             ("M", "crisis", "strict"), ("N", "soft", "schedule"))
    for extra in (keyed(None, 4, **{AMOUNT.replace(".", "__"): 0.0}), keyed(None, 5), keyed(1, 4), keyed(4, 2),
                  {**keyed(3, 1, **{AMOUNT.replace(".", "__"): 0.0}), **late}, keyed(1, 2)):
        run = grid_of(extra)
        seen = made = 0
        for key in cells:
            c = run.cell(*key)
            for dec in c.recaps[:4]:
                s, point, norm = _replay(run, c, dec)
                assert close(dec.shortfall, s, rel=1e-12), (extra, c.label, dec.q, dec.shortfall, s)
                assert (dec.point, dec.norm) == (point, norm), (extra, c.label, dec.q)
                seen += 1
                made += dec.rec > 0
        assert seen >= 20 and made >= 4, (extra, seen, made)


def check_decision_after_the_agm_sees_the_dividend() -> None:
    """Решение после собрания несёт принятый дивиденд (свойство 12 М§4.14.5): при h_R > h_A взнос первого решения
    после собрания у книги с выплатой больше, чем у книги с нулевой выплатой, на дивиденд этого года с точностью
    второго порядка — проценты на выплаченные деньги и их вес риска, — когда недостаток выше порога в обеих, а
    дивиденд к связывающей точке вычтен из регуляторного капитала. Решение до собрания от доли выплаты не зависит
    (свойство 13): ряды клетки до квартала собрания и взнос первого решения — бит в бит, а дивиденд собрания
    решается уже с деньгами взноса."""
    zero = {"dividends.policy.payout": {"LT": 0.0}, "dividends.excess.epsilon": 0.0}
    paid, none = grid_of({**keyed(4, 1), **MID_BUFFER}), grid_of({**keyed(4, 1), **MID_BUFFER, **zero})
    agm = R.first_agm(paid)
    q_r = next(q for q in decision_quarters(paid) if q > agm)
    seen = 0
    for a, b in zip(paid.cells, none.cells):
        assert all(d.div == 0.0 for d in b.decisions), b.label
        for k in ("bv", "rwa", "n20", "rec"):   # до первого собрания выплата политики на путь не влияет
            assert a.quarters[k][:agm] == b.quarters[k][:agm], (a.label, k)
        da, db = (next(r for r in c.recaps if r.q == q_r) for c in (a, b))
        div = a.quarters["div"][agm]
        if not div > 1.0 or not (da.rec > 0 and db.rec > 0):
            continue
        assert da.div == div and da.div_q == agm and a.quarters["dpreg"][q_r] == 0.0     # дивиденд уже вычтен
        assert abs((da.rec - db.rec) - div) <= 0.1 * div, (a.label, da.rec, db.rec, div)
        seen += 1
    assert seen >= 3, seen
    # решение до собрания: первый квартал, окно 1 — взнос первого решения от доли выплаты не зависит
    for extra in (keyed(1, 1), keyed(1, 0)):
        paid, none = grid_of({**extra, **R.BIG_BUFFER}), grid_of({**extra, **R.BIG_BUFFER, **zero})
        first = decision_quarters(paid)[0]
        assert first < R.first_agm(paid)
        made = richer = 0
        for a, b in zip(paid.cells, none.cells):
            da, db = a.recaps[0], b.recaps[0]
            assert da.q == db.q == first and (da.shortfall, da.rec, da.point, da.norm) == (
                db.shortfall, db.rec, db.point, db.norm), a.label
            assert (da.div, da.div_model, da.div_source, da.div_q) == (0.0, 0.0, None, None)
            for k in ("bv", "rwa", "n20", "n11", "rec"):
                assert a.quarters[k][:first + 1] == b.quarters[k][:first + 1], (a.label, k)
            made += da.rec > 0
            # собрание того же года решает о дивиденде уже с деньгами взноса: без взноса дивиденд не больше
            plain = plain_of({**extra, **R.BIG_BUFFER}).cell(*a.key)
            richer += a.quarters["div"][R.first_agm(paid)] > plain.quarters["div"][R.first_agm(paid)] + 1.0
            assert a.quarters["div"][R.first_agm(paid)] >= plain.quarters["div"][R.first_agm(paid)] - 1e-9, a.label
        assert made >= 10, (extra, made)
        if extra[LOOK] == 1:
            assert richer >= 3, richer


def check_dividend_does_not_count_on_the_contribution() -> None:
    """Пробный проход дивиденда не несёт взноса (свойство 14 М§4.14.5; М§5.3 п. 7): при решении о взносе после
    собрания дивиденд квартала собрания равен дивиденду той же клетки книги с выключенным механизмом, пока до
    этого собрания взносов не было, — и когда квартал решения о взносе стоит среди точек проверки дивиденда."""
    extra = keyed(4, 1)
    run, plain = grid_of(extra), plain_of(extra)
    assert 4 in run.ctx.prep.policy.checkpoints and run.ctx.prep.recap.quarter == 4
    agm = R.first_agm(run)
    same = bound = 0
    for c, p in zip(run.cells, plain.cells):
        assert len(c.recaps) == len(decision_quarters(run)), c.label      # решений о взносе — по одному на квартал решения
        if any(c.quarters["rec"][1:agm]):
            continue
        assert c.decisions[0] == p.decisions[0] and c.quarters["div"][agm] == p.quarters["div"][agm], c.label
        same += 1
        nxt = next(r for r in c.recaps if r.q > agm)
        bound += c.decisions[0].source == "model" and nxt.rec > 0       # дивиденд не вырос за счёт будущего взноса
    assert same >= 12 and bound >= 3, (same, bound)


def check_step_of_the_first_quarter() -> None:
    """Ступень требования первого квартала закрыта взносом четвёртого квартала предыдущего года при L = 1 и
    взносом через год при L = 0 (свойство 5 М§4.14.5): деньги приходят в конце квартала перед ступенью."""
    key = ("M", "downturn", "upper")
    seen, blind = grid_of(keyed(4, 1)).cell(*key), grid_of(keyed(4, 0)).cell(*key)
    step = R.first_agm(grid_of()) + 3           # первый квартал года после первого собрания: ступень пола
    assert seen.quarters["req20"][step] > seen.quarters["req20"][step - 1] + 0.005
    gap = lambda c, q: (c.quarters["req20"][q] - c.quarters["n20"][q]) * c.quarters["rwa"][q]  # noqa: E731
    da = next(r for r in seen.recaps if r.q == step - 1)
    assert da.rec > 100.0 and da.point == step and da.last == step
    assert gap(seen, step) <= RECAP_RESIDUAL_SHARE * da.rec          # окно видело ступень: она закрыта
    db = next(r for r in blind.recaps if r.q == step - 1)
    assert db.last == step - 1 and db.rec < da.rec - 100.0 and gap(blind, step) > 100.0
    nxt = next(r for r in blind.recaps if r.q == step + 3)
    assert nxt.rec > 100.0 and gap(blind, nxt.q) <= RECAP_RESIDUAL_SHARE * nxt.rec     # закрыта через год


def check_shock_year_and_the_last_year() -> None:
    """Год шока: решение квартала перед кварталом убытка несёт убыток в окне — взнос больше на убыток после
    налога с точностью второго порядка; окно, которое до убытка не доходит, его не видит. Последний год: при
    квартале решения, равном последнему кварталу сетки, последнее решение стоит за год до конца, а недостаток
    конца сетки несёт X_T по цене размещения (М§4.14.3)."""
    for lookahead in (1, 0):
        book, base, deep = (grid_of({**keyed(4, lookahead), **extra}) for extra in ({}, R.LOSS, R.DEEP_LOSS))
        tl, prep = base.ctx.timeline, base.ctx.prep
        q_loss = prep.regimes["crisis"].one_off_q
        q_r = q_loss - 1
        assert tl.h(q_r) == 4 and q_r in decision_quarters(base)
        step = R.DEEP_LOSS["regimes.crisis.one_off_loss.amount"] - R.LOSS["regimes.crisis.one_off_loss.amount"]
        hit = 0
        for o, a, b in zip(book.cells, base.cells, deep.cells):
            do, da, db = (next(r for r in c.recaps if r.q == q_r) for c in (o, a, b))
            if a.regime != "crisis" or lookahead == 0:      # убыток не в клетке или не в окне: решение то же
                assert (do.shortfall, do.rec) == (da.shortfall, da.rec) == (db.shortfall, db.rec), (a.label, lookahead)
                continue
            net = -step * (1 - a.quarters["tau_eff"][q_loss]) * (1 - prep.nci_share)
            for dec in (da, db):                # решение квартала перед убытком: связывает квартал убытка
                assert dec.point == q_loss and dec.rec > 0 and dec.div_source is None, a.label
            assert db.rec - da.rec > 0.5 * net, (a.label, db.rec - da.rec, net)
            if da.norm == db.norm == "n20":     # Н20.0 несёт убыток целиком: взнос больше на убыток после налога
                assert abs((db.rec - da.rec) - net) <= 0.1 * net, (a.label, db.rec - da.rec, net)
                hit += 1
        assert hit >= 3 or lookahead == 0, hit
    end = grid_of({**keyed(4, 0), **R.LATE_STEP})
    tl = end.ctx.timeline
    assert tl.h(tl.Q) == 4
    carried = 0
    for c in end.cells:
        assert c.recaps[-1].q == tl.Q - 4 and c.quarters["rec"][tl.Q] == 0.0, c.label
        if c.scenario == "strict":
            assert c.x_t < -100.0 and close(c.dc_t, 0.1 / 0.9 * (max(-c.x_t, 0.0) + max(-c.p_t, 0.0))), c.label
            carried += 1
    assert carried == 12


def check_closed_quarter_of_a_decision_outside_the_agm() -> None:
    """Взнос закрытого квартала вычтен из капитала на дату оценки, и между E_qR − 1 и E_qR точка меняется на
    перекат, а не на взнос — и когда квартал взноса не квартал собрания (М§6.5)."""
    extra = keyed(4, 1)
    run = grid_of(extra)
    tl = run.ctx.timeline
    q_r = next(q for q in decision_quarters(run) if sum(1 for c in run.cells if c.quarters["rec"][q] > 0) >= 6)
    end = tl.end(q_r)
    after = grid_of(extra, R.live_at(end + timedelta(days=5)))
    q0 = after.ctx.clock.q0
    assert q0 == q_r + 1 and tl.h(q_r) != run.ctx.prep.policy.agm_quarter
    tol = float(after.ctx.book.get("checks.ddm_ri_tol"))
    closed = 0
    for c in after.cells:
        rec = c.quarters["rec"]
        c_v = sum(rec[q] for q in range(1, q0))
        full = c.quarters["bv"][q0 - 1] + after.ctx.clock.elapsed * c.quarters["ci"][q0]
        assert c.c_v == c_v and close(c.bv_v, full - c_v, rel=1e-12), c.label
        assert abs(c.v_ddm - c.v_ri) <= tol * max(abs(c.v_ri), c.bv_v), c.label
        dfq = after.ctx.discounts[c.world].dfq
        want = 0.1 / 0.9 * (c_v + sum(rec[q] * dfq[q] for q in range(q0, len(rec)))) + dfq[-1] * c.dc_t
        assert close(c.pvd, want), c.label
        closed += rec[q_r] > 0
    assert closed >= 6, closed
    pts = [grid_of(extra, R.live_at(end + timedelta(days=d))).point for d in (-1, 0, 1)]
    assert abs(pts[1] - pts[0]) < 1e-3 * pts[1] and abs(pts[2] - pts[1]) < 1e-3 * pts[1], pts
    mix = sum(after.layers["analytical"].prob[c.key] * c.quarters["rec"][q_r] for c in after.cells)
    assert mix * 1000 / after.divisor > 20 * abs(pts[1] - pts[0])      # взнос на акцию много больше переката


# ------------------------------------------------------------------ нижняя граница окна (М§4.14, прил. A № 19)


def _calendar_dict(agm: int, deduction: int, quarter: int | None, lookahead: int, enabled: bool = True) -> dict:
    """Словарь книги фикстуры докапитализации с календарём случая и кварталом решения."""
    change = {"dividends.calendar": {"agm_quarter": agm, "reg_deduction_quarter": deduction,
                                     "payment_quarter": max(agm, deduction), "checkpoints": [4]},
              LOOK: lookahead, f"{RECAP}.enabled": enabled}
    if quarter is not None:
        change[QUARTER] = quarter
    return R.recap_dict(change)


def _accepted(data: dict, why: str) -> None:
    """Книга обязана пройти схему; отказ — нарушение утверждения с причиной."""
    try:
        book_from_dict(data, facts=fixture_facts())
    except BookError as exc:
        raise AssertionError(f"{why}: схема отказала — {str(exc)[:300]}") from exc


def check_window_floor() -> None:
    """Нижняя граница окна — отказ схемы ровно при `lookahead_quarters < L_min` по таблице случаев примера E и
    только при включённом механизме (свойство 15 М§4.14.5): `L_min = max(0, max(h_A, h_D) − h_R)` при h_R ≥ h_A и
    ноль при h_R < h_A; без ключа h_R = h_A. Поле вне границ — отказ при любом `enabled`."""
    facts = fixture_facts()
    assert EXAMPLE_Q4["lookahead_min"] == window_floor(*(int(EXAMPLE_Q4["input"][k]) for k in (
        "agm_quarter", "reg_deduction_quarter", "decision_quarter")))
    refused = 0
    for case in EXAMPLE_Q4["window_bounds"]:
        agm, ded, quarter = (int(case[k]) for k in ("agm_quarter", "reg_deduction_quarter", "decision_quarter"))
        low = int(case["lookahead_min"])
        assert window_floor(agm, ded, quarter) == low, case
        key = None if quarter == agm else quarter       # решение в квартал собрания — и без ключа
        for q_key in dict.fromkeys((key, quarter)):
            _accepted(_calendar_dict(agm, ded, q_key, low), "окно ровно на нижней границе")
            if low:
                R._refused(_calendar_dict(agm, ded, q_key, low - 1), LOOK, "нижней границы")
                _accepted(_calendar_dict(agm, ded, q_key, low - 1, enabled=False),
                          "окно короче границы при выключенном механизме")
                refused += 1
    assert refused >= 6
    # календарь фикстуры: решение в квартал собрания с окном 0 — отказ, решение в квартал вычета — принято
    R._refused(R.recap_dict({LOOK: 0}), LOOK, "нижней границы")
    book_from_dict(R.recap_dict({LOOK: 0, QUARTER: DEDUCTION}), facts=facts)
    book_from_dict(R.recap_dict({LOOK: 0, QUARTER: 1}), facts=facts)
    for bad in (0, 5, 2.5, "4"):
        for enabled in (True, False):
            R._refused(R.recap_dict({QUARTER: bad, f"{RECAP}.enabled": enabled}), QUARTER)


# ------------------------------------------------------------------ правило «при равенстве» и точки инварианта


def check_tie_rule() -> None:
    """Точка и норматив наибольшего недостатка — одним правилом «при равенстве» (М§4.14.1 п. 3), по случаям
    примера E: самая ранняя точка окна, у которой S_c ≥ S − 1e-9; Н20.0, если S_20 ≥ S_11 − 1e-9. Сам недостаток —
    наибольший как есть."""
    from model.capital import RecapPoint
    for case in EXAMPLE_Q4["tie_cases"]:
        points = [RecapPoint(q=i, s20=float(a), s11=float(b)) for i, (a, b) in enumerate(case["points"], 1)]
        gap, best, norm = worst_point(points)
        assert gap == max(max(p.s20, p.s11) for p in points) == float(case["shortfall"]), case
        assert (best.q, norm) == (int(case["point_index"]), case["norm"]), (case, best.q, norm)
    # третье решение примера: четыре равных по формуле недостатка — самая ранняя точка и Н20.0
    inp = EXAMPLE_Q4["input"]
    rows = []
    for c, vals in inp["trials"]["10"].items():
        n20, n11, dpreg, rwa, req20, req11 = map(float, vals)
        rows.append(shortfall({"n20": n20 / PCT, "n11": n11 / PCT, "dpreg": dpreg, "rwa": rwa, "req20": req20 / PCT,
                               "req11": req11 / PCT}, int(c), last=int(c) == 11))
    gap, best, norm = worst_point(rows)
    assert abs(gap - 4.2) < TOL and (best.q, norm) == (10, "n20")


def _example_decisions() -> dict[int, tuple]:
    """Решения о взносе примера E по нормативам его пробных проходов — формулой ядра."""
    inp = EXAMPLE_Q4["input"]
    out = {}
    for q_r, points in inp["trials"].items():
        q_r = int(q_r)
        last = min(q_r + int(inp["lookahead_quarters"]), int(inp["Q"]))
        rows = []
        for c in range(q_r, last + 1):
            n20, n11, dpreg, rwa, req20, req11 = map(float, points[str(c)])
            rows.append(shortfall({"n20": n20 / PCT, "n11": n11 / PCT, "dpreg": dpreg, "rwa": rwa,
                                   "req20": req20 / PCT, "req11": req11 / PCT}, c, last=c == last))
        gap, worst, norm = worst_point(rows)
        out[q_r] = (rows, gap, worst.q, norm, gap if gap > float(inp["min_amount"]) else 0.0, last)
    return out


def _final_rows(table: Mapping[str, Any]) -> list[dict]:
    """Строки окончательного расчёта примера (кварталы 1…) для пересчёта остатка недостатка."""
    rows: list[dict] = []
    for c in range(1, max(map(int, table)) + 1):
        if str(c) not in table:
            rows.append({})
            continue
        n20, n11, dpreg, rwa, req20, req11 = map(float, table[str(c)])
        rows.append({"n20": n20 / PCT, "n11": n11 / PCT, "dpreg": dpreg, "rwa": rwa, "req20": req20 / PCT,
                     "req11": req11 / PCT})
    return rows


def check_invariant_points() -> None:
    """Состав точек инварианта `recap_covers_gap` — часть его определения (М§14.1): кварталы окна от квартала
    решения до квартала перед ближайшим новым решением клетки, `q_R … min(c_max, q_R + δ − 1)`,
    `δ = min(4, ((h_A − h_R − 1) mod 4) + 1)` — по таблице случаев примера E. На строках окончательного расчёта
    примера остаток выше допуска в поздней точке инварианта — нарушение; тот же по величине остаток в квартале
    нового решения — нет."""
    for case in EXAMPLE_Q4["invariant_span"]:
        assert invariant_span(int(case["agm_quarter"]), int(case["decision_quarter"])) == int(case["next_decision_in"])
    inp = EXAMPLE_Q4["input"]
    span = invariant_span(int(inp["agm_quarter"]), int(inp["decision_quarter"]))
    assert span == EXAMPLE_Q4["next_decision_in"] == 2
    rows, gap, point, norm, rec, last = _example_decisions()[2]
    dec = RecapDecision(year=-1, q=2, last=last, points=tuple(rows), shortfall=gap, point=point, norm=norm, rec=rec,
                        div=0.0, div_model=0.0, div_source=None, span=span)
    want = EXAMPLE_Q4["residual"]
    assert list(residual_points(dec)) == want["decision_2"]["points_checked"] == [2, 3]
    assert list(residual_points(dataclasses.replace(dec, last=9))) == [2, 3]          # квартал собрания — вне точек
    assert list(residual_points(dataclasses.replace(dec, span=4, last=9))) == [2, 3, 4, 5]
    assert list(residual_points(dataclasses.replace(dec, span=4, last=3))) == [2, 3]  # окно короче — точки окна
    # остаток окончательного расчёта: точка 4 — квартал собрания с новым дивидендом — в инвариант не входит
    done = recap_residuals([dec], _final_rows(inp["final"]["2"]))[0]
    assert abs(done.residual - want["decision_2"]["residual"]) < TOL and done.residual <= RECAP_RESIDUAL_SHARE * rec
    assert abs(done.residual / rec - want["decision_2"]["share"]) < TOL
    outside = shortfall(_final_rows(inp["final"]["2"])[3], 4, last=False)
    assert abs(outside.s - want["point_outside"]["s"]) < TOL and outside.s > RECAP_RESIDUAL_SHARE * rec
    # построенный случай: остаток в поздней точке инварианта — нарушение (проверка одного квартала решения молчала бы)
    late = recap_residuals([dec], _final_rows(inp["final_late"]["2"]))[0]
    assert abs(late.residual - want["late"]["residual"]) < TOL and late.residual > RECAP_RESIDUAL_SHARE * rec
    assert abs(shortfall(_final_rows(inp["final_late"]["2"])[1], 2, last=False).s
               - want["late_if_decision_quarter_only"]["residual"]) < TOL
    # на фикстуре: число точек — по кварталу решения; остаток — наибольший по этим точкам
    for quarter, lookahead, points in ((4, 2, 2), (4, 1, 2), (None, 4, 4), (3, 4, 3), (1, 2, 1)):
        run = grid_of(keyed(quarter, lookahead))
        tl = run.ctx.timeline
        seen = 0
        for c in run.cells:
            q_ = c.quarters
            for dec in c.recaps:
                assert dec.span == points and len(residual_points(dec)) == min(points, dec.last - dec.q + 1)
                if not dec.rec > 0:
                    assert dec.residual is None
                    continue
                own = max(_own_shortfall(q_, x, x)[0] if x == dec.last else max(
                    (q_["req20"][x] - q_["n20"][x]) * q_["rwa"][x], (q_["req11"][x] - q_["n11"][x]) * q_["rwa"][x])
                    for x in range(dec.q, min(dec.last, dec.q + points - 1) + 1))
                assert close(dec.residual, own, rel=1e-12, abs_=1e-9), (c.label, dec.q, dec.residual, own)
                seen += 1
        assert seen >= 20, (quarter, seen)
        finding = next(f for f in check_invariants(run) if f.name == "recap_covers_gap")
        assert not finding.fired, (quarter, lookahead, finding.message)


def check_dividend_of_the_decision() -> None:
    """Дивиденд решения о взносе — дивиденд последнего решения клетки о дивиденде в кварталах q_R − 3 … q_R
    (М§4.14.1): по нему стоят флаг `recap_with_dividend` и сумма «дивиденд в пределах взноса»
    `Σ P × Σ min(дивиденд модели решения, Rec) × DF̃_qR`; у решения, перед которым решений о дивиденде не было, —
    ноль. Пример E: второе решение несёт дивиденд квартала 4."""
    want = {int(q): row for q, row in EXAMPLE_Q4["decisions"].items()}
    assert [q for q, row in want.items() if row["rec"] > 0 and row["dividend"] > 0] == EXAMPLE_Q4["recap_with_dividend"]
    df6 = 1.05 ** -6
    assert abs(min(want[6]["dividend"], want[6]["rec"]) * df6 - EXAMPLE_Q4["dividend_within_recap"]) < TOL
    for quarter, lookahead in ((4, 1), (3, 1), (1, 1), (None, 3)):
        run = grid_of(keyed(quarter, lookahead))
        tl, agm = run.ctx.timeline, run.ctx.prep.policy.agm_quarter
        prob = point_probabilities(run)
        flagged = total = 0.0
        linked = 0
        for c in run.cells:
            decided = {tl.year(q) - 1: q for q in range(1, tl.Q + 1) if tl.h(q) == agm}
            by_q = {decided[d.year]: d for d in c.decisions}
            within, flag = 0.0, False
            for dec in c.recaps:
                near = [q for q in by_q if dec.q - 3 <= q <= dec.q]
                if not near:
                    assert (dec.div, dec.div_model, dec.div_source, dec.div_q) == (0.0, 0.0, None, None), c.label
                    continue
                q_d = max(near)
                d = by_q[q_d]
                model = 0.0 if d.source == "register" else d.div
                assert (dec.div, dec.div_model, dec.div_source, dec.div_q) == (d.div, model, d.source, q_d), c.label
                linked += q_d != dec.q
                if dec.rec > 0:
                    within += min(model, dec.rec) * run.ctx.discounts[c.world].dfq[dec.q]
                    flag = flag or model > 0
            assert ("recap_with_dividend" in c.flags) == flag, (c.label, quarter)
            flagged += prob[c.key] * flag
            total += prob[c.key] * within
        node = recap_node(run)["layers"]["point"]
        assert close(node["dividend_within_recap"], total) and close(node["recap_with_dividend_mass"], flagged)
        if quarter is not None:                 # решение не в квартал собрания: дивиденд — другого квартала
            assert linked >= 36, (quarter, linked)
        if quarter in (4, None):                # окно видит ступень следующего года: клетка платит и привлекает
            assert flagged > 0.1 and total > 1.0, (quarter, flagged, total)


# ------------------------------------------------------------------ путь акций и DPS (М§6.6)


def check_dps_with_the_divisor_adjustment() -> None:
    """У книги с поправкой делителя акции поправки стоят в знаменателе DPS с первого решения модели:
    `N_out,q = N_out + (N_q − N_base)`; без поправки — прежняя строка; DPS решения записью реестра — число записи
    (М§6.6). Пример E — до 1e-9."""
    adj = 0.25
    for extra in ({}, {"valuation.share_count_adj": adj}):
        run = grid_of({**keyed(4, 1), **extra})
        p = run.ctx.prep
        n_base = run.divisor / (1 + adj) if extra else run.divisor
        assert close(n_base, p.af.n_out, rel=1e-12)
        before = after = 0
        for c in run.cells:
            assert c.n_base is not None and close(c.n_base, n_base, rel=1e-12)
            for d in c.decisions:
                q_a = next(q for q in range(1, run.ctx.timeline.Q + 1)
                           if run.ctx.timeline.h(q) == p.policy.agm_quarter and run.ctx.timeline.year(q) - 1 == d.year)
                n = c.shares.n[q_a - 1]
                if n is None:
                    assert c.dps[d.year] == 0.0
                    continue
                want = d.div * 1000 / (p.af.n_out + (n - n_base))
                assert close(c.dps[d.year], want, rel=1e-12), (c.label, d.year, c.dps[d.year], want)
                if n == run.divisor and d.div > 0:  # до первого взноса: знаменатель — акции якоря и акции поправки
                    assert close(c.dps[d.year], d.dps / (1 + adj) if extra else d.dps, rel=1e-12), c.label
                    before += 1
                elif d.div > 0:
                    assert c.dps[d.year] < d.dps
                    after += 1
        assert before >= 3 and after >= 30, (extra, before, after)
    # запись реестра: дивиденд объявлен на акцию — DPS решения равен числу записи и при поправке делителя
    # (убыток кризиса в окне первого решения: в клетках режима кризиса взнос модели — до первого собрания)
    change = {**keyed(4, 1), "valuation.share_count_adj": adj, **R.LOSS}
    run = grid_of(change)
    tl = run.ctx.timeline
    live = R.live_at(tl.end(1), (R.record(run, 40.0),))
    reg = grid_of(change, live)
    diluted = 0
    for c in reg.cells:
        first = c.decisions[0]
        assert first.source == "register" and c.dps[first.year] == 40.0 == first.dps, c.label
        diluted += c.shares.n[R.first_agm(reg) - 1] != reg.divisor     # перед собранием уже был взнос модели
    assert diluted >= 3
    # пример E: DPS на акции своего года с акциями поправки делителя в знаменателе
    inp, shares = EXAMPLE_Q4["input"], EXAMPLE_Q4["shares"]
    n_out, n_iss, n_base = (float(inp["shares"][k]) for k in ("n_out", "n_iss", "n_base"))
    n_div = EXAMPLE_Q4["n_div"]
    assert abs(n_base * (1 + float(inp["shares"]["share_count_adj"])) - n_div) < TOL
    disc, term, _ = _example_value(1)
    sp = share_path(q0=1, disc=disc, div=EXAMPLE_Q4["div"], rec=EXAMPLE_Q4["rec"], term=term,
                    discount=float(inp["price_discount"]), n_div=n_div)
    assert all(abs(a - b) < 1e-6 for a, b in zip(sp.n, shares["n"]))
    assert all(abs(a - b) < TOL for a, b in zip(sp.stake, shares["stake"]))
    policy = fixture_run().ctx.prep.policy
    prep = SimpleNamespace(policy=policy, af=SimpleNamespace(n_out=n_out, n_iss=n_iss))
    for q_a, dps in shares["dps"].items():
        div = EXAMPLE_Q4["div"][int(q_a)]
        dec = SimpleNamespace(year=2030, base=0.0, div=div, dps=div * 1000 / n_out, source="model")
        own, _ = own_year_dps(prep, sp, int(q_a), dec, n_base)
        assert abs(own - dps) < 1e-8, (q_a, own, dps)
        old, _ = own_year_dps(prep, sp, int(q_a), dec)          # без базы делителя — прежняя строка
        assert abs(old - shares["dps_without_divisor_adjustment"][q_a]) < 1e-8
        reg_dec = SimpleNamespace(year=2030, base=0.0, div=div, dps=17.5, source="register")
        assert own_year_dps(prep, sp, int(q_a), reg_dec, n_base)[0] == 17.5


def _example_value(q0: int, discount: float | None = None):
    """Терминал и оценка примера E функциями ядра: плоский дисконт k за квартал, дата оценки — конец q0 − 1."""
    from model.valuation import terminal, value_cell
    from model.worlds import Discount
    inp = EXAMPLE_Q4["input"]
    d = float(inp["price_discount"]) if discount is None else discount
    n = int(inp["Q"])
    k = float(inp["k_quarter"])
    dfq, kq = [1.0] * (n + 1), [0.0] * (n + 1)
    for q in range(q0, n + 1):
        dfq[q], kq[q] = (1 + k) ** (-(q - q0 + 1)), k
    k_t = (1 + k) ** 4 - 1
    disc = Discount(k=tuple(kq), k_t=k_t, dfq=tuple(dfq), curve=None, roll=0.0)
    t = inp["terminal"]
    term = terminal(
        n20=float(t["n20_t"]) / PCT, req20=float(t["req20"]) / PCT, n11_star=float(t["n11_t"]) / PCT,
        req11=float(t["req11"]) / PCT, rwa=float(t["rwa"]), bv_q=EXAMPLE_Q4["bv"][n],
        pbt_last_year=float(t["pbt_last_year"]), y_balancing=float(t["y_balancing"]),
        c_wholesale=float(t["c_wholesale"]), headroom=0.0, tau_eff=float(t["tau_eff"]),
        nci_share=float(t["nci_share"]), coupon_annual=float(t["coupon_annual"]), tau_stat=0.0,
        lt_inflation=float(t["g_t"]), real_growth=0.0, fade=float(t["fade"]),
        multiple=float(t["excess_capital_multiple"]), k_t=k_t, wholesale_extra=float(t["wholesale_extra"]), discount=d)
    val = value_cell(q0=q0, elapsed=0.0, disc=disc, bv=EXAMPLE_Q4["bv"], ci=EXAMPLE_Q4["ci"], div=EXAMPLE_Q4["div"],
                     term=term, rec=EXAMPLE_Q4["rec"], discount=d)
    return disc, term, val


def check_example_q4() -> None:
    """Пример приложения E воспроизводится функциями ядра до 1e-9: решения о взносе в четвёртом квартале с окном
    в один квартал, капитал, терминал, обе формы оценки, цена размывания, дата оценки после квартала взноса,
    доля нынешних акций; целые и названия — точно."""
    inp = EXAMPLE_Q4["input"]
    near = lambda a, b: abs(a - b) <= TOL  # noqa: E731
    n = int(inp["Q"])
    h = EXAMPLE_Q4["quarter_in_year"]
    quarters = [q for q in range(1, n) if h[q] == int(inp["decision_quarter"])]
    assert quarters == EXAMPLE_Q4["decision_quarters"] and h[n] == int(inp["decision_quarter"])
    assert EXAMPLE_Q4["skipped_last_quarter"] == [n]
    for q_r, (rows, gap, point, norm, rec, last) in _example_decisions().items():
        want = EXAMPLE_Q4["decisions"][str(q_r)]
        assert near(gap, want["shortfall"]) and (point, norm, last) == (want["point"], want["norm"], want["last"])
        assert near(rec, want["rec"]) and near(rec, EXAMPLE_Q4["rec"][q_r]), q_r
        for pt in rows:
            assert near(pt.s20, want["points"][str(pt.q)]["s20"]) and near(pt.s11, want["points"][str(pt.q)]["s11"])
    bv = float(inp["bv0"])
    for q in range(1, n + 1):
        bv += EXAMPLE_Q4["ci"][q] - EXAMPLE_Q4["div"][q] + EXAMPLE_Q4["rec"][q]
        assert near(bv, EXAMPLE_Q4["bv"][q]), q
    disc, term, val = _example_value(1)
    for key in ("x_t", "bv_star", "y_x", "ni_t1", "ci_t1", "tv_ri", "p_t", "tv_ddm", "dc_t", "g_t", "k_t"):
        assert near(getattr(term, key), EXAMPLE_Q4["terminal"][key]), key
    want = EXAMPLE_Q4["valuation"]
    assert near(val.v_ri, want["v_ri"]) and near(val.v_ddm, want["v_ddm"]) and near(val.v_ri, val.v_ddm)
    assert near(val.pvd, want["pvd"]) and near(val.c_v, want["c_v"]) and near(val.bv_v, want["bv_v_current"])
    assert near(val.pv_ri_explicit, want["pv_ri"]) and near(val.pv_terminal, want["pv_tv_ri"])
    assert near(val.v_ri * 1000 / EXAMPLE_Q4["n_div"], EXAMPLE_Q4["price"])
    _, term0, val0 = _example_value(1, 0.0)
    assert near(val0.v_ri, EXAMPLE_Q4["at_zero_discount"]["v_ri"]) and term0.dc_t == 0.0
    assert near(val0.v_ri - val.v_ri, want["pvd"])
    closed = EXAMPLE_Q4["closed_quarter"]["valuation"]
    _, _, late = _example_value(int(closed["q0"]))
    assert near(late.v_ri, closed["v_ri"]) and near(late.v_ddm, closed["v_ddm"]) and near(late.c_v, closed["c_v"])
    assert near(late.pvd, closed["pvd"]) and near(late.bv_v, closed["bv_v_current"])
    assert near(late.pv_tv_ddm, closed["pv_tv_ddm"]) and near(late.v_ri, EXAMPLE_Q4["closed_quarter"]["check_roll"])
    sp = share_path(q0=1, disc=disc, div=EXAMPLE_Q4["div"], rec=EXAMPLE_Q4["rec"], term=term,
                    discount=float(inp["price_discount"]), n_div=EXAMPLE_Q4["n_div"])
    assert sp.broken is None and near(late.v_ri, sp.w[2][1])     # стоимость акций до взноса = оценке на конец квартала
    for q, w in EXAMPLE_Q4["shares"]["w"].items():
        assert near(sp.w[int(q)][0], w["w"]) and near(sp.w[int(q)][1], w["pre_money"])


# ------------------------------------------------------------------ норма клетки (М§6.4, §14)


def _with_cell(run: GridRun, index: int, **change: Any) -> GridRun:
    """Сетка с одной подменённой клеткой (поля результата клетки) — для проверок на построенном случае."""
    cells = list(run.cells)
    cells[index] = dataclasses.replace(cells[index], **change)
    return dataclasses.replace(run, cells=tuple(cells))


def check_cell_norm() -> None:
    """Норма клетки (М§6.4): у книги с включённой докапитализацией невязка DDM = RI и доля терминала относятся к
    `max(|V|, BV_v − C_v)` — у клетки со стоимостью около нуля они конечны; в клетке со стоимостью не ниже
    капитала — прежние меры; у книги без докапитализации `ddm_ri_max` и доли терминала — прежние строки бит в
    бит, и у нуля относительная невязка по-прежнему неограниченна."""
    keyed_run, bare = grid_of(R.BIG_BUFFER), plain_of(R.BIG_BUFFER)
    tol = float(keyed_run.ctx.book.get("checks.ddm_ri_tol"))
    below = above = 0
    for c in keyed_run.cells:
        dfq = keyed_run.ctx.discounts[c.world].dfq
        norm = max(abs(c.v_ri), c.bv_v)
        assert cell_norm_of(keyed_run, c) == norm == cell_norm(c.v_ri, c.bv_v) and c.bv_v > 0
        pv = dfq[-1] * (c.tv_ddm - c.dc_t)
        assert close(c.pv_tv_ddm, pv, rel=1e-12) and close(c.terminal_share, pv / max(c.v_ddm, c.bv_v), rel=1e-12)
        assert math.isfinite(c.terminal_share) and abs(c.terminal_share) <= abs(pv) / c.bv_v + 1e-12
        if c.v_ddm >= c.bv_v:
            assert close(c.terminal_share, pv / c.v_ddm, rel=1e-12)       # мера образца
            above += 1
        else:
            below += 1
    assert below >= 6 and above >= 3 and any(c.v_ri < 0 for c in keyed_run.cells), (below, above)
    worst = max(abs(c.v_ddm - c.v_ri) / max(abs(c.v_ri), c.bv_v) for c in keyed_run.cells)
    assert ddm_ri_max(keyed_run) == worst and U.run_summary(keyed_run)["ddm_ri"] == worst
    for name, layer in keyed_run.layers.items():
        pv = sum(layer.prob[c.key] * c.pv_tv_ddm for c in keyed_run.cells)
        assert close(layer.terminal_share, pv / max(layer.v0, layer.bv_v), rel=1e-12), name
    # построенный случай: стоимость клетки у нуля, абсолютная невязка мала — инвариант выполнен
    near_zero = _with_cell(keyed_run, 0, v_ri=1e-3, v_ddm=1e-3 + 1e-5, bv_v=1000.0)
    assert 1e-5 / 1e-3 > tol > 1e-5 / 1000.0
    finding = next(f for f in check_invariants(near_zero) if f.name == "ddm_equals_ri")
    assert not finding.fired and ddm_ri_max(near_zero) < tol, finding.message
    broken = _with_cell(keyed_run, 0, v_ri=1e-3, v_ddm=1e-3 + 2 * tol * 1000.0, bv_v=1000.0)
    assert next(f for f in check_invariants(broken) if f.name == "ddm_equals_ri").fired
    # книга без докапитализации: прежние строки — и у нуля невязка относится к стоимости
    for c in bare.cells:
        dfq = bare.ctx.discounts[c.world].dfq
        assert c.terminal_share == dfq[-1] * c.tv_ddm / c.v_ddm and c.pv_tv_ddm is None, c.label
        assert cell_norm_of(bare, c) == abs(c.v_ri)
    assert any(abs(c.v_ri) < c.bv_v for c in bare.cells)
    old = max(abs(c.v_ddm - c.v_ri) / abs(c.v_ri) for c in bare.cells)
    assert ddm_ri_max(bare) == old and U.run_summary(bare)["ddm_ri"] == old
    assert next(f for f in check_invariants(bare) if f.name == "ddm_equals_ri").detail["worst"] == old
    for name, layer in bare.layers.items():
        tv = sum(layer.prob[c.key] * c.terminal_share * c.v_ddm for c in bare.cells)
        assert layer.terminal_share == tv / layer.v0, name
    same = _with_cell(bare, 0, v_ri=1e-3, v_ddm=1e-3 + 1e-5, bv_v=1000.0)
    assert next(f for f in check_invariants(same) if f.name == "ddm_equals_ri").fired


# ------------------------------------------------------------------ срок избыточной доходности (М§11.3)


def check_excess_years_row() -> None:
    """Строка «в цене — лет избыточной доходности» у книги с докапитализацией и с полом клетки (М§11.3):
    накопленная стоимость несёт цену размывания по годам взносов (взносы закрытых кварталов — с первой строки),
    DC_T и поправку пола — в строке терминала; последняя строка равна модельной стоимости сверх капитала смеси
    `Σ P × (V^F − (BV_v − C_v))`. Без ключей — прежние строки бит в бит."""
    for extra, live_days in (({FLOOR: R.FLOOR_HIGH}, None), (keyed(4, 1), None), ({FLOOR: 0.0, **keyed(4, 1)}, 5)):
        run = grid_of(extra)
        tl = run.ctx.timeline
        if live_days is not None:               # дата оценки после квартала первых взносов: взносы закрыты
            q_r = next(q for q in decision_quarters(run) if sum(1 for c in run.cells if c.quarters["rec"][q] > 0) >= 6)
            run = grid_of(extra, R.live_at(tl.end(q_r) + timedelta(days=live_days)))
        q0, d = run.ctx.clock.q0, run.ctx.prep.recap_discount
        prob = point_probabilities(run)
        rows = excess_by_year(run)
        k = d / (1 - d)
        total = -sum(prob[c.key] * k * c.c_v for c in run.cells)
        if live_days is not None:
            assert total < -1.0
        for i, year in enumerate(range(tl.year(q0), tl.last_year + 1)):
            qs = [q for q in tl.quarters_of_year(year) if q0 <= q <= tl.Q]
            for c in run.cells:
                dfq = run.ctx.discounts[c.world].dfq
                total += prob[c.key] * sum(c.pv_ri_q[q] - k * c.quarters["rec"][q] * dfq[q] for q in qs)
            assert rows[i]["year"] == year and close(rows[i]["pv_excess_cum"], total), (extra, year)
        top = sum(prob[c.key] * (run.cell_value(c) - c.bv_v) for c in run.cells)
        assert rows[-1]["year"] == tl.last_year + 1 and close(rows[-1]["pv_excess_cum"], top), (extra, rows[-1], top)
        # цена размывания и поправка пола — не ноль: без них последняя строка не сошлась бы
        dilution = sum(prob[c.key] * c.pvd for c in run.cells)
        floor_adj = sum(prob[c.key] * (run.cell_value(c) - c.v_ri) for c in run.cells)
        assert dilution > 1.0 and (floor_adj > 1.0 or FLOOR not in extra or extra[FLOOR] == 0.0), (dilution, floor_adj)
        bare = sum(prob[c.key] * (sum(c.pv_ri_q[q0:]) + c.pv_terminal) for c in run.cells)
        assert close(bare - dilution + floor_adj, top) and abs(bare - top) > 1.0
    base = fixture_run()                        # без ключей — прежние строки
    tl, q0 = base.ctx.timeline, base.ctx.clock.q0
    prob = point_probabilities(base)
    total, want = 0.0, []
    for year in range(tl.year(q0), tl.last_year + 1):
        qs = [q for q in tl.quarters_of_year(year) if q0 <= q <= tl.Q]
        total += sum(prob[c.key] * c.pv_ri_q[q] for c in base.cells for q in qs)
        want.append({"year": year, "pv_excess_cum": total})
    total += sum(prob[c.key] * c.pv_terminal for c in base.cells)
    want.append({"year": tl.last_year + 1, "pv_excess_cum": total})
    assert excess_by_year(base) == want


# ====================================================================== общие правила ядра (М§18)

RELIEF = "relief"                            # четвёртый сценарий требования фикстуры: вес — только в режиме кризиса
SHOCK = "crisis"


def four_scenarios_dict(extra: Mapping[str, Any] | None = None, *, own: bool = False) -> dict:
    """Словарь книги фикстуры формы образца с четвёртым сценарием требования (М§3.3, §3.4): вероятность ноль во
    всех режимах, кроме режима кризиса, где он вытесняет `schedule`. Без `own` его траектории — те же, что у
    `schedule` (смесь тогда обязана совпасть со смесью книги с тремя сценариями); с `own` — без надбавок в год
    шока (послабление регулятора)."""
    data = fixture_dict()
    sc = data["capital"]["reg_scenarios"]
    sc["ids"] = list(sc["ids"]) + [RELIEF]
    sc[RELIEF] = copy.deepcopy(sc["schedule"])
    sc[RELIEF]["name"] = "Послабление в кризис"
    if own:
        sc[RELIEF]["conservation"] = {"2026": 0.01, "2027": 0.0, "2028": 0.005, "2029": 0.015, "2030": 0.025}
    for regime, row in data["joint"]["reg_prob_given_regime"].items():
        row[RELIEF] = row["schedule"] if regime == SHOCK else 0.0
        if regime == SHOCK:
            row["schedule"] = 0.0
    for path, value in (extra or {}).items():
        node = data
        parts = path.split(".")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    return data


def four_scenarios_book(extra: Mapping[str, Any] | None = None, *, own: bool = False) -> Book:
    return book_from_dict(four_scenarios_dict(extra, own=own), facts=fixture_facts())


_FOUR: dict[bool, GridRun] = {}


def four_scenarios_run(own: bool = False) -> GridRun:
    if own not in _FOUR:
        _FOUR[own] = run_grid(four_scenarios_book(own=own), fixture_facts())
    return _FOUR[own]


def _dead(run: GridRun) -> list[Any]:
    """Клетки нулевой вероятности — ноль во всех трёх слоях (М§3.4)."""
    return [c for c in run.cells if all(layer.prob[c.key] == 0.0 for layer in run.layers.values())]


def check_cells_by_the_lists_of_the_book() -> None:
    """Число клеток сетки — произведение порядков перечней книги, в порядке перечней (М§3): книга с четвёртым
    сценарием требования считает 48 клеток. Клетки нулевой вероятности считаются, инварианты в них проверяются,
    их вес в смесях и массах — ноль: при сценарии с траекториями `schedule` слои, точка и гейты равны книге с
    тремя сценариями (М§3.4)."""
    base, run = fixture_run(), four_scenarios_run()
    book = run.ctx.book
    worlds, regimes, scen = (list(book.get(p)) for p in ("worlds.ids", "regimes.ids", "capital.reg_scenarios.ids"))
    assert len(scen) == 4 and len(run.cells) == len(worlds) * len(regimes) * len(scen) == 48
    assert [c.key for c in run.cells] == [(w, r, s) for w in worlds for r in regimes for s in scen]
    dead = _dead(run)
    assert sorted(c.key for c in dead) == sorted([(w, r, RELIEF) for w in worlds for r in regimes if r != SHOCK]
                                                 + [(w, SHOCK, "schedule") for w in worlds])
    assert len(dead) == 12 and len(judged_cells(run)) == 36 and judged_cells(base) == base.cells
    assert all(math.isfinite(c.v_ri) and c.quarters["bv"][-1] is not None and c.annual["ni_sh"] for c in dead)
    assert not [f.name for f in check_invariants(run) if f.fired]
    # сценарий с траекториями `schedule`: клетка сценария равна клетке `schedule` того же мира и режима
    for c in run.cells:
        twin = base.cell(c.world, c.regime, "schedule" if c.scenario == RELIEF else c.scenario)
        assert (c.v_ri, c.v_ddm, c.bv_v, c.flags) == (twin.v_ri, twin.v_ddm, twin.bv_v, twin.flags), c.label
    for name, layer in run.layers.items():
        old = base.layers[name]
        assert close(sum(layer.prob.values()), 1.0, abs_=1e-12) and all(layer.prob[c.key] == 0.0 for c in dead)
        for k in ("v0", "bv_v", "price", "pv_ri_explicit", "pv_terminal", "terminal_share", "roe_tc", "k_tc",
                  "capital_gap_mass", "p_roe_below_k", "p_price_below_market"):
            assert close(getattr(layer, k), getattr(old, k), rel=1e-12, abs_=1e-12), (name, k)
    assert close(run.point, base.point, rel=1e-12) and close(run.low, base.low, rel=1e-12)
    gates = {f.name: f for f in check_gates(run)}
    for f in check_gates(base):
        g = gates[f.name]
        assert (g.fired, len(g.cells)) == (f.fired, len(f.cells)), f.name
        assert g.mass is None or close(g.mass, f.mass, abs_=1e-12), f.name
        assert not {c.label for c in dead} & set(g.cells), f.name
    summary, old = U.run_summary(run), U.run_summary(base)
    assert all(close(summary[k], old[k], rel=1e-12, abs_=1e-12) for k in ("low", "high", "gap_mass", "negative_mass"))
    # сценарий со своими траекториями: клетки нулевой вероятности точку не двигают — она равна сумме по клеткам
    own = four_scenarios_run(own=True)
    relief, plan = own.cell("N", SHOCK, RELIEF), own.cell("N", SHOCK, "schedule")
    assert len(own.cells) == 48 and relief.quarters["floor20"] != plan.quarters["floor20"]
    shock = own.ctx.timeline.index("2027Q1")
    assert relief.quarters["floor20"][shock] < plan.quarters["floor20"][shock] - 0.005   # надбавка года шока снята
    for name, layer in own.layers.items():
        assert close(layer.v0, sum(layer.prob[c.key] * c.v_ri for c in judged_cells(own)), rel=1e-12), name
    assert not [f.name for f in check_invariants(own) if f.fired]


def check_zero_probability_cell() -> None:
    """Клетку нулевой вероятности гейт не судит, а инвариант проверяет (М§3.4, §14.1, §14.2): условие гейта,
    нарушенное только в такой клетке, гейт не поднимает, в число и в перечень его клеток она не входит — и
    срабатывает, как только то же условие нарушено в клетке положительной вероятности; нарушенное в ней
    тождество — нарушение инварианта. В квантиль по клеткам клетка нулевого веса не входит."""
    from model import payload as P
    run = four_scenarios_run()
    dead = _dead(run)[0]
    live = next(c for c in run.cells if c.world == dead.world and run.layers["analytical"].prob[c.key] > 0)
    at = lambda c: run.cells.index(c)  # noqa: E731
    gate = lambda r, name: next(f for f in check_gates(r) if f.name == name)  # noqa: E731
    assert not gate(run, "k_gt_g").fired and "capital_gap" not in dead.flags
    for name, change in (("k_gt_g", {"g_capped": True}), ("capital_gap", {"flags": dead.flags | {"capital_gap"},
                                                                         "gap_period": "2027Q1"}),
                         ("roe_gt_g", {"roe_t": dead.g_t - 0.01}), ("terminal_share", {"terminal_share": 9.0})):
        before = gate(run, name)
        quiet = gate(_with_cell(run, at(dead), **change), name)
        assert (quiet.fired, quiet.cells, quiet.mass) == (before.fired, before.cells, before.mass), name
        if name == "capital_gap":
            change = {"flags": live.flags | {"capital_gap"}, "gap_period": "2027Q1"}
        elif name == "roe_gt_g":
            change = {"roe_t": live.g_t - 0.01}
        loud = gate(_with_cell(run, at(live), **change), name)
        assert loud.fired and live.label in loud.cells and loud.mass > 0, name
    # инвариант — и в клетке нулевой вероятности: тождество капитала, баланса и DDM = RI
    bv = list(dead.quarters["bv"])
    bv[5] += 1.0
    broken = _with_cell(run, at(dead), quarters={**dead.quarters, "bv": tuple(bv)})
    found = next(f for f in check_invariants(broken) if f.name == "bv_identity")
    assert found.fired and any(dead.label in x for x in found.cells)
    off = _with_cell(run, at(dead), v_ddm=dead.v_ri * 1.5)
    assert next(f for f in check_invariants(off) if f.name == "ddm_equals_ri").fired
    # квантиль по клеткам: значение клетки нулевого веса не входит ни в какой хвост
    pairs = [(-50.0, 0.0), (1.0, 0.25), (2.0, 0.5), (3.0, 0.25), (500.0, 0.0)]
    assert P._Ctx.wquantile(None, pairs, 0.1) == 1.0 and P._Ctx.wquantile(None, pairs, 0.9) == 3.0
    assert P._Ctx.wquantile(None, pairs, 0.5) == 2.0 and P._Ctx.wquantile(None, [(7.0, 0.0)], 0.5) is None


def fast_release(book: Book, *, control: Any = "own", draws: int = 6):
    """Быстрый выпуск на книге формы образца с объяснёнными гейтами: (Release, payload). `control` — сводка
    контрольной модели: "own" — сводка фикстуры на книге теста, иначе — словарь, путь или None (файл дерева)."""
    from model import payload as P
    from tests.support_core2 import TODAY, control_fixture, explained

    facts = fixture_facts()
    run = run_grid(book, facts, live_from_book(book, facts))
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts,
                         explanations=explained(check_gates(run, today=TODAY)), notes=[], draws=draws,
                         control_model=control_fixture(book) if control == "own" else control)
    return rel, P.build_payload(rel)


def check_release_of_four_scenarios() -> None:
    """Быстрый выпуск книги с четвёртым сценарием требования собирается и проходит контракт: клеток — по одной
    на тройку перечней выпуска, сколько бы сценариев книга ни назвала; контракт отказывает при пропавшей и при
    лишней клетке и называет число клеток книги (П§7 п. 8)."""
    from model import payload as P
    from tests.support_core2 import contract

    # книга с клетками нулевой вероятности ставит правило разброса цены ключом (М§3.4): без него доля остатка
    # правила образца отрицательна, и контракт отказывает (`tests/support_core_pass4.py`)
    _, d = fast_release(four_scenarios_book({"checks.grid_variance": "sequential"}, own=True))
    assert not contract(d), contract(d)[:5]
    grid = d["grid"]
    assert grid["scenario_order"][-1] == RELIEF and len(grid["scenario_order"]) == 4 and len(grid["cells"]) == 48
    assert [(c["world"], c["regime"], c["scenario"]) for c in grid["cells"]] == [
        (w, r, s) for w in grid["world_order"] for r in grid["regime_order"] for s in grid["scenario_order"]]
    dead = [c for c in grid["cells"] if c["p_analytical"] == c["p_market_implied"] == c["p_neutral"] == 0.0]
    assert len(dead) == 12 and all(c["v"] is not None and c["annual"]["ni_sh"] for c in dead)
    assert set(d["capital"]["scenarios"]) == set(grid["scenario_order"])
    assert all(g["cells"] <= 36 and not {f"{c['world']}/{c['regime']}/{c['scenario']}" for c in dead}
               & set(g["cell_list"]) for g in d["checks"]["gates"])
    lost = copy.deepcopy(d)
    lost["grid"]["cells"] = lost["grid"]["cells"][:-1]
    extra = copy.deepcopy(d)
    extra["grid"]["cells"] = extra["grid"]["cells"] + [extra["grid"]["cells"][0]]
    for broken, got in ((lost, 47), (extra, 49)):
        text = [x for x in P._layer_problems(broken) if x.startswith("grid.cells: нужно")]
        assert text and "нужно 48 клеток" in text[0] and f"в выпуске {got}" in text[0], P._layer_problems(broken)[:3]
    assert not [x for x in P._layer_problems(d) if x.startswith("grid.cells: нужно")]
    # книга с тремя сценариями: то же правило называет 36
    _, three = fast_release(fixture_book())
    assert not contract(three) and len(three["grid"]["cells"]) == 36
    short = copy.deepcopy(three)
    short["grid"]["cells"] = short["grid"]["cells"][1:]
    assert any("нужно 36 клеток" in x for x in P._layer_problems(short))


def check_release_with_step_payouts_by_year() -> None:
    """Выпуск книги, у которой доля выплаты ступени политики — траектория по годам (схема её допускает, М§5.3),
    собирается: ступень печатается долей года якоря — как доля политики без ступеней; у ступени-числа — прежнее
    число (П§2 `dividends.policy.steps`, `ladder`)."""
    from tests.support_core2 import contract

    steps = [{"payout": {"2026": 0.25, "LT": 0.5, "LT_from": 2027}, "threshold": 0.125},
             {"payout": {"LT": 0.25}, "threshold": 0.0}]
    book = fixture_book().with_overrides({"dividends.policy.steps": steps})
    assert book.get("meta.anchor_period").startswith("2026")
    _, d = fast_release(book)
    assert not contract(d), contract(d)[:5]
    assert d["dividends"]["policy"]["steps"] == [{"payout": 0.25, "threshold": 0.125}, {"payout": 0.25, "threshold": 0.0}]
    first = d["dividends"]["ladder"][0]
    assert first["payout"] == 0.25 and "25" in first["title"] and "50" not in first["title"], first
    flat = fixture_book().with_overrides({"dividends.policy.steps": [{"payout": 0.5, "threshold": 0.125},
                                                                    {"payout": 0.25, "threshold": 0.0}]})
    _, d = fast_release(flat)
    assert d["dividends"]["policy"]["steps"] == [{"payout": 0.5, "threshold": 0.125}, {"payout": 0.25, "threshold": 0.0}]


# ------------------------------------------------------------------ допуск сверки заголовка (П§0.3, §7 п. 5)

LEVELS = ((1, 2), (2, 4), (4, 8), (8, 16), (16, 32), (32, 64), (64, 128), (128, 256), (256, 512), (512, 700))


def check_headline_tolerance() -> None:
    """Допуск сверки хранимого числа с пересчётом — половина шага хранения плюс запас счёта (П§0.3). Перебор всех
    ничьих в полкопейки на уровнях цены 1–700 ₽ — значений вида n/1000 с последней цифрой 5, построенных делением
    целого и арифметикой самой сверки (центр прогона `низ + λ × (верх − низ)` и квантиль типа 7 по прогонам с
    шагом 0,1 ₽): хранимое число сходится с пересчётом в допуске. С допуском ровно в половину шага тот же перебор
    находит отказы — 96 на уровне 8–16 ₽ и 896 на уровне 32–64 ₽ у значений, построенных делением целого, и ни
    одного на прочих уровнях: дефект закреплён числом. Число, отстоящее от пересчёта на шаг хранения, — отказ."""
    from model import payload as P

    step = P.PRECISION["price"]
    tol = P.stored_tolerance(step)
    assert tol == step / 2 + 1e-9 and step == 0.01
    ties = [n / 1000 for n in range(1005, 700000, 10)]
    assert len(ties) == 69900
    bare = {level: 0 for level in LEVELS}
    for x in ties:
        stored = P.R_PRICE(x)
        assert P._close(stored, x, tol), (x, stored, abs(stored - x))
        if abs(stored - x) > step / 2:          # без запаса счёта — отказ: ничья вышла за половину шага
            bare[next(level for level in LEVELS if level[0] <= x < level[1])] += 1
    assert bare[(8, 16)] == 96 and bare[(32, 64)] == 896 and sum(bare.values()) == 992, bare
    # те же ничьи — арифметикой сверки: центр прогона и квантиль типа 7 по прогонам с шагом 0,1 ₽
    made = over = 0
    for tenth in range(10, 7000):
        low = tenth / 10
        for lam, high in ((0.5, low + 0.1), (0.05, low + 0.1), (0.25, low + 0.2), (0.5, low + 0.3)):
            high = round(high, 1)
            centre = low + lam * (high - low)
            median = U.quantile(sorted([low, high]), 0.5)
            for value in (centre, median):
                stored = P.R_PRICE(value)
                assert P._close(stored, value, tol), (low, high, lam, value, stored)
                made += 1
                over += abs(stored - value) > step / 2
    assert made > 50000 and over > 50, (made, over)
    for x in (9.125, 60.125, 60.135, 350.005):
        stored = P.R_PRICE(x)
        far = stored + step if stored > x else stored - step        # соседнее хранимое число с дальней стороны
        assert not P._close(x + step, x, tol) and not P._close(x - step, x, tol) and not P._close(far, x, tol), x
    assert abs(P.R_PRICE(60.125) - 60.125) > step / 2          # пример П§0.3: 60,125 хранится как 60,12


def check_headline_is_verified_with_the_tolerance() -> None:
    """Сверка заголовка контракта держит ничью в полкопейки на уровне цены 32–64 ₽ (П§7 п. 5): выпуск, у которого
    квантили и среднее пересчитаны из прогонов и сохранены с шагом 0,01 ₽, проходит сверку; тот же выпуск с
    медианой, сдвинутой на шаг хранения, — отказ."""
    from model import payload as P

    _, d = fast_release(fixture_book())
    d = copy.deepcopy(d)
    h = d["fair_value"]["headline"]
    n = h["draws"]
    h["low_draws"] = [60.1 + 0.1 * (i % 3) for i in range(n)]
    h["high_draws"] = [round(v + 0.05, 2) for v in h["low_draws"]]
    main = d["meta"]["company"]["main_ticker"]
    price = d["market"]["prices"][main]["price"]
    levels = sorted(float(q) for q in h["quantiles"])
    step_print = float(h["print_step"])

    def row_at(lam: float) -> dict[str, Any]:
        centres = sorted(lo + lam * (hi - lo) for lo, hi in zip(h["low_draws"], h["high_draws"]))
        exact = {name: U.quantile(centres, q) for name, q in zip(U.QUANTILE_NAMES, levels)}
        exact["mean"] = sum(centres) / len(centres)
        return {"exact": exact, "stored": {k: P.R_PRICE(v) for k, v in exact.items()},
                "p_below": sum(1 for v in centres if v < price) / len(centres)}

    lam = float(h["own_macro_confidence"])
    top = row_at(lam)
    s, e = top["stored"], top["exact"]
    h.update(median=s["median"], mean=s["mean"], band80=[s["p10"], s["p90"]], band50=[s["p25"], s["p75"]],
             p_below_market=top["p_below"], printed_median=U.round_half_up(e["median"], step_print),
             printed_band80=[U.round_half_up(e["p10"], step_print), U.round_half_up(e["p90"], step_print)],
             printed_band50=[U.round_half_up(e["p25"], step_print), U.round_half_up(e["p75"], step_print)],
             ceiling_x_market=max(float(h["ceiling_x_market"]), 100.0 / price))
    ties = 0
    for r in h["by_lambda"]:
        got = row_at(float(r["lambda"]))
        r.update(**{k: got["stored"][k] for k in ("median", "mean", "p10", "p25", "p75", "p90")},
                 p_below_market=got["p_below"])
        ties += sum(1 for k, v in got["exact"].items() if abs(got["stored"][k] - v) > P.PRECISION["price"] / 2)
    assert ties > 0, "в построенном выпуске нет ничьей, вышедшей за половину шага"
    problems = [x for x in P._headline_problems(d) if "не воспроизводится" in x]
    assert not problems, problems[:3]
    moved = copy.deepcopy(d)
    moved["fair_value"]["headline"]["by_lambda"][3]["median"] += P.PRECISION["price"]
    assert any("не воспроизводится" in x for x in P._headline_problems(moved))


# ------------------------------------------------------------------ база ожидания нау-каста (М§13)

NI_TARGET = "valuation.next_report.ni_target"
TARGET_TITLE = "вся прибыль группы, с долей неконтролирующих акционеров"
MULTIPLIER = 1 / (1 - 0.034)


def target_book(multiplier: float = MULTIPLIER, title: str = TARGET_TITLE) -> Book:
    return fixture_book().with_overrides({NI_TARGET: {"multiplier": multiplier, "title": title}}, create=True)


def _year_of_the_nowcast(rel: Any, bridged: float | None) -> dict[str, Any]:
    """Узел года нау-каста выпуска при оценке квартала `bridged` (вес 1: прогноз равен ей); None — без оценки."""
    from model import payload as P

    nxt = dict(rel.next_report)
    ras = None if bridged is None else {"targets": {"ni_q": {"ras_bridged": bridged, "w": 1.0}}}
    ind = SimpleNamespace(nowcast={"period": nxt["period"], "ras": ras})
    out = P._nowcast(P._Ctx(dataclasses.replace(rel, indicators=ind)), nxt, {})
    return out


def check_ni_target() -> None:
    """База ожидания прибыли нау-каста (М§13): с ключом `valuation.next_report.ni_target` ожидание в базе цели
    равно прибыли движка, умноженной на множитель, — точно; прибыль движка, ЧПМ, CoR и прочие поля ожидания от
    ключа не зависят бит в бит; при прогнозе, равном ожиданию цели, прибыль года выпуска — прежняя, при
    отклонении Δ — больше на Δ / m; подпись базы доходит до выпуска. Без ключа — прежние числа и узлов нет.
    Множитель не больше нуля, объект без подписи и подпись с полем подстановки — отказ схемы."""
    from indicators import nowcast as N
    from model import nextreport as NR
    from model import payload as P
    from tests.support_core2 import contract

    facts = fixture_facts()
    plain, keyed_book = fixture_book(), target_book()
    assert NR.ni_target(plain) is None and NR.ni_target(keyed_book) == {"multiplier": MULTIPLIER, "title": TARGET_TITLE}
    period = NR.open_period(plain, facts)
    e0, e1 = NR.model_expectation(plain, facts, period), NR.model_expectation(keyed_book, facts, period)
    assert "ni_target_q" not in e0 and "ni_target" not in e0
    assert e1["ni_target_q"] == MULTIPLIER * e0["ni_q"] and e1["ni_target"] == NR.ni_target(keyed_book)
    assert {k: v for k, v in e1.items() if k not in ("ni_target_q", "ni_target")} == e0     # прибыль движка — та же
    assert N._expectation(e1, "ni_q") == e1["ni_target_q"] and N._expectation(e0, "ni_q") == e0["ni_q"]
    assert N._expectation(e1, "nim_q") == e0["nim_q_mgmt"] and N._expectation(e1, "cor_q") == e0["cor_q_mgmt"]
    rel0, d0 = fast_release(plain)
    rel1, d1 = fast_release(keyed_book)
    assert not contract(d0) and not contract(d1), (contract(d0)[:3], contract(d1)[:3])
    x0, x1 = d0["next_report"]["expectation"], d1["next_report"]["expectation"]
    assert "ni_target" not in x0 and "ni_target" not in d0["nowcast"]
    assert x1["ni"] == x0["ni"] and close(x1["ni_target"], MULTIPLIER * x1["ni"], rel=1e-8)
    assert {k: v for k, v in x1.items() if k != "ni_target"} == x0
    node = d1["nowcast"]["ni_target"]
    assert set(node) == {"multiplier", "title"} and node["title"] == TARGET_TITLE
    assert close(node["multiplier"], MULTIPLIER, rel=1e-8)
    q0, q1 = d0["nowcast"]["quarter"]["by_target"], d1["nowcast"]["quarter"]["by_target"]
    assert close(q1["ni_q"]["expectation"], MULTIPLIER * q0["ni_q"]["expectation"], rel=1e-8)
    assert q1["ni_q"]["forecast"] == q1["ni_q"]["expectation"] and q1["ni_q"]["deviation"] == 0
    assert q1["nim_q"] == q0["nim_q"] and q1["cor_q"] == q0["cor_q"]
    assert d1["nowcast"]["year"] == d0["nowcast"]["year"]          # прогноз равен ожиданию цели: год прежний
    assert d1["next_report"]["neutral"] == d0["next_report"]["neutral"]
    # отклонение нау-каста Δ в базе цели входит в прибыль года прибылью движка: Δ / m
    delta = 10.0
    base1 = _year_of_the_nowcast(rel1, None)["year"]["ni_quarter"]
    moved1 = _year_of_the_nowcast(rel1, e1["ni_target_q"] + delta)
    assert close(moved1["quarter"]["by_target"]["ni_q"]["deviation"], delta, abs_=1e-6)
    assert close(moved1["year"]["ni_quarter"] - base1, delta / MULTIPLIER, abs_=0.011), (moved1["year"], base1)
    assert close(moved1["year"]["ni_year"] - _year_of_the_nowcast(rel1, None)["year"]["ni_year"], delta / MULTIPLIER,
                 abs_=0.011)
    base0 = _year_of_the_nowcast(rel0, None)["year"]["ni_quarter"]
    moved0 = _year_of_the_nowcast(rel0, e0["ni_q"] + delta)
    assert close(moved0["year"]["ni_quarter"] - base0, delta, abs_=0.011) and base0 == base1
    assert abs(delta - delta / MULTIPLIER) > 0.3            # разница баз различима при точности хранения
    # другой множитель и другая подпись доходят до выпуска: множитель и подпись — ключи книги, не код
    other = target_book(2.0, "прибыль в другой базе")
    assert NR.model_expectation(other, facts, period)["ni_target_q"] == 2.0 * e0["ni_q"]
    _, d2 = fast_release(other)
    assert d2["nowcast"]["ni_target"] == {"multiplier": 2.0, "title": "прибыль в другой базе"}
    assert close(d2["next_report"]["expectation"]["ni_target"], 2.0 * x0["ni"], rel=1e-8) and not contract(d2)
    # контракт: ожидание в базе цели — прибыль движка на множитель
    bad = copy.deepcopy(d1)
    bad["next_report"]["expectation"]["ni_target"] = x1["ni"]
    assert any("ni_target" in x for x in P._ni_target_problems(bad)) and not P._ni_target_problems(d1)
    bad = copy.deepcopy(d1)
    bad["nowcast"]["ni_target"]["multiplier"] = 0.0
    assert P._ni_target_problems(bad)
    # схема (прил. A № 20)
    data = fixture_dict()
    for spec, fragment in (({"multiplier": 0.0, "title": TARGET_TITLE}, "multiplier"),
                           ({"multiplier": -1.0, "title": TARGET_TITLE}, "multiplier"),
                           ({"multiplier": "1.03", "title": TARGET_TITLE}, "multiplier"),
                           ({"multiplier": 1.03}, "title"), ({"title": TARGET_TITLE}, "multiplier"),
                           ({"multiplier": 1.03, "title": ""}, "title"),
                           ({"multiplier": 1.03, "title": "прибыль {group}"}, "title")):
        trial = copy.deepcopy(data)
        trial["valuation"]["next_report"]["ni_target"] = spec
        R._refused(trial, f"{NI_TARGET}.{fragment}")
    ok = copy.deepcopy(data)
    ok["valuation"]["next_report"]["ni_target"] = {"multiplier": 1.03, "title": TARGET_TITLE}
    book_from_dict(ok, facts=facts)


# ------------------------------------------------------------------ сводка контрольной модели (М§17, §14.3)


def check_control_summary() -> None:
    """Сводка сверки с контрольной моделью идёт в выпуск только своей версии книги и своей даты фактов (М§17):
    чужой версии, без версии или с другой датой фактов — узла нет и поднят флаг `control_model_mismatch` в конце
    списка флагов; сводка без даты фактов при своей версии идёт в выпуск без флага (форма образца); без файла —
    ни узла, ни флага. Контракт отказывает сводке чужой книги в выпуске и поднятому флагу при узле."""
    from model import payload as P
    from tests.support_core2 import CONTROL_FIXTURE, contract, control_fixture

    book = fixture_book()
    version, facts_date = str(book.get("meta.version")), str(book.get("meta.facts_date"))[:10]
    own = control_fixture(book)
    assert (own["book_version"], own["facts_date"]) == (version, facts_date)
    state = P.control_summary_state
    assert state(book, own) == (own, None) and state(book, None) == (None, None) and state(book, []) == (None, None)
    undated = {k: v for k, v in own.items() if k != "facts_date"}
    assert state(book, undated) == (undated, None)                       # форма образца: дата фактов не сверяется
    for summary, words in (({**own, "book_version": "1.0"}, "книга 1.0"),
                           ({k: v for k, v in own.items() if k != "book_version"}, "версии книги в сводке нет"),
                           ({**own, "facts_date": "2025-12-31"}, "факты на 2025-12-31"),
                           ({**undated, "book_version": "0.9"}, "книга 0.9")):
        node, why = state(book, summary)
        assert node is None and why is not None, summary.get("book_version")
        assert words in why and f"книга {version}" in why and facts_date in why and P.CONTROL_COMMAND in why, why
    assert json.loads(CONTROL_FIXTURE.read_text(encoding="utf-8")).get("book_version") is None
    assert state(book, json.loads(CONTROL_FIXTURE.read_text(encoding="utf-8")))[0] is None
    names = lambda d: [f["name"] for f in d["checks"]["flags"]]  # noqa: E731
    rel, d = fast_release(book)
    assert d["checks"]["control_model"]["book_version"] == version == d["meta"]["book_version"]
    assert d["checks"]["control_model"]["facts_date"] == facts_date == d["meta"]["facts_date"]
    assert P.CONTROL_FLAG not in names(d) and rel.control_mismatch is None and not contract(d)
    assert not [r for r in rel.remarks if "контрольной моделью" in r]
    rel, alien = fast_release(book, control={**own, "book_version": "1.0"})
    assert alien["checks"]["control_model"] is None and names(alien)[-1] == P.CONTROL_FLAG and not contract(alien)
    assert names(alien)[:len(P.FLAG_TITLES)] == list(P.FLAG_TITLES) == names(d)[:len(P.FLAG_TITLES)]
    flag = alien["checks"]["flags"][-1]
    assert flag["raised"] is True and flag["title"] == P.RAISED_FLAG_TITLES[P.CONTROL_FLAG]
    assert "книга 1.0" in flag["detail"] and f"книга {version}" in flag["detail"]
    assert any(P.CONTROL_COMMAND in r for r in rel.remarks)
    _, stale = fast_release(book, control={**own, "facts_date": "2026-03-31"})
    assert stale["checks"]["control_model"] is None and names(stale)[-1] == P.CONTROL_FLAG
    _, sample = fast_release(book, control=undated)
    assert sample["checks"]["control_model"] == undated and P.CONTROL_FLAG not in names(sample) and not contract(sample)
    _, absent = fast_release(book, control=FIXTURE_RECAP / "нет-такого-файла.json")
    assert absent["checks"]["control_model"] is None and P.CONTROL_FLAG not in names(absent) and not contract(absent)
    # контракт: сводка чужой книги или чужих фактов в выпуске — отказ; поднятый флаг при узле — отказ
    for change in ({"book_version": "1.0"}, {"facts_date": "2025-12-31"}):
        broken = copy.deepcopy(d)
        broken["checks"]["control_model"].update(change)
        assert any("checks.control_model" in x for x in P._control_origin_problems(broken)), change
    broken = copy.deepcopy(d)
    del broken["checks"]["control_model"]["book_version"]
    assert P._control_origin_problems(broken)
    broken = copy.deepcopy(d)
    broken["checks"]["flags"].append(copy.deepcopy(flag))
    assert any(P.CONTROL_FLAG in x for x in P._control_origin_problems(broken)) and not P._control_origin_problems(d)


# ------------------------------------------------------------------ оси полосы на общем пути (М§10)

TRAJ = "opex.real_growth"                    # траектория фикстуры под осью вида shift
ELEM = "opex.real_growth.2027"
TABLE = "joint.regime_prob"
NUM_A, NUM_B = "credit.kappa", "oci.fvoci_duration"


def _shift(paths: list[str], low: float, high: float, name: str = "сдвиг") -> dict:
    return {"name": name, "kind": "shift", "paths": paths, "low": low, "high": high, "dist": "triangular"}


def _bundle(ends: Mapping[str, tuple[float, float]], name: str = "связка") -> dict:
    return {"name": name, "kind": "bundle", "paths": list(ends), "low": {p: v[0] for p, v in ends.items()},
            "high": {p: v[1] for p, v in ends.items()}, "dist": "triangular"}


def _table(low: Mapping[str, float], high: Mapping[str, float], name: str = "доли") -> dict:
    return {"name": name, "kind": "dict", "paths": [TABLE], "low": dict(low), "high": dict(high), "dist": "triangular"}


def _old_draw_overrides(book: Book, axes: Any, s: Any) -> dict[str, Any]:
    """Подмены прогона полосы прежним порядком (образец): оси по порядку книги — значениями, связки — после них
    приращением к значению книги на пути, который сдвинула ось вида shift."""
    from model.paths import get_path, set_path
    ov: dict[str, Any] = {}
    bundles = []
    for ax, sj in zip(axes, s):
        if ax["kind"] == U.BUNDLE:
            bundles.append((ax, sj))
            continue
        ov.update(U.axis_overrides(book, ax, sj))
    for ax, sj in bundles:
        for path, value in U.axis_overrides(book, ax, sj).items():
            home = path if path in ov else U._containing(ov, path)
            if home is None:
                ov[path] = value
                continue
            step = value - float(book.get(path))
            if home == path:
                ov[path] = float(ov[path]) + step
            else:
                tail = path[len(home) + 1:]
                set_path(ov[home], tail, float(get_path(ov[home], tail)) + step)
    return ov


def check_axes_on_a_common_path_add_up() -> None:
    """Оси на общем пути (М§10): значение пути равно книге плюс сумма приращений всех осей на нём — две оси
    `shift` на одном пути, ось `shift` на траектории и ось `shift` на её элементе, две связки на общем пути (и
    вместе с осью `shift`); порядок осей в книге на результат не влияет; одна ось в нуле возвращает значение
    другой, все в нуле — книгу бит в бит. Прогон полосы на таких осях равен сетке книги, собранной руками."""
    book = fixture_book()
    base = {k: float(v) for k, v in book.get(TRAJ).items()}
    a, b = _shift([TRAJ], -0.005, 0.025, "первая"), _shift([TRAJ], -0.01, 0.04, "вторая")
    elem = _shift([ELEM], -0.02, 0.03, "элемент")
    sa, sb, se = 0.4, -0.7, 0.9
    da, db, de = sa * a["high"], abs(sb) * b["low"], se * elem["high"]
    got = U.draw_overrides(book, [a, b], (sa, sb))
    assert set(got) == {TRAJ} and set(got[TRAJ]) == set(base)
    for key, value in base.items():
        assert close(got[TRAJ][key], value + da + db, rel=1e-15, abs_=1e-15), key
        assert abs(got[TRAJ][key] - (value + db)) > 1e-3 and abs(got[TRAJ][key] - (value + da)) > 1e-3
    assert U.draw_overrides(book, [b, a], (sb, sa)) == got                     # порядок осей не важен
    assert U.draw_overrides(book, [a, b], (sa, 0.0)) == U.axis_overrides(book, a, sa)
    assert U.draw_overrides(book, [a, b], (0.0, sb)) == U.axis_overrides(book, b, sb)
    assert U.draw_book(book, [a, b], (0.0, 0.0)).data == book.data
    # траектория и её элемент: элемент несёт оба сдвига, прочие ключи — сдвиг траектории
    got = U.draw_overrides(book, [a, elem], (sa, se))
    assert set(got) == {TRAJ}
    for key, value in base.items():
        want = value + da + (de if key == "2027" else 0.0)
        assert close(got[TRAJ][key], want, rel=1e-15, abs_=1e-15), key
    assert abs(got[TRAJ]["2027"] - (base["2027"] + da)) > 1e-3 and abs(got[TRAJ]["2027"] - (base["2027"] + de)) > 1e-3
    assert U.draw_overrides(book, [elem, a], (se, sa)) == got
    assert U.draw_overrides(book, [a, elem], (sa, 0.0)) == U.axis_overrides(book, a, sa)
    three = U.draw_overrides(book, [elem, b, a], (se, sb, sa))
    assert close(three[TRAJ]["2027"], base["2027"] + da + db + de, rel=1e-15, abs_=1e-15)
    assert three == U.draw_overrides(book, [a, b, elem], (sa, sb, se))
    # две связки на общем пути, и вместе с осью shift на нём
    k0, d0 = float(book.get(NUM_A)), float(book.get(NUM_B))
    one = _bundle({NUM_A: (0.02, 0.09), ELEM: (0.0, 0.05)}, "первая связка")
    two = _bundle({NUM_A: (0.03, 0.11), NUM_B: (1.5, 3.0)}, "вторая связка")
    s1, s2 = -0.5, 0.8
    got = U.draw_overrides(book, [one, two], (s1, s2))
    step1, step2 = abs(s1) * (0.02 - k0), s2 * (0.11 - k0)
    assert close(got[NUM_A], k0 + step1 + step2, rel=1e-15) and abs(got[NUM_A] - (k0 + step2)) > 1e-3
    assert close(got[NUM_B], d0 + s2 * (3.0 - d0), rel=1e-15)
    assert close(got[ELEM], base["2027"] + abs(s1) * (0.0 - base["2027"]), rel=1e-15, abs_=1e-15)
    assert U.draw_overrides(book, [two, one], (s2, s1)) == got
    assert U.draw_overrides(book, [one, two], (s1, 0.0)) == {**U.axis_overrides(book, one, s1), NUM_B: d0}
    assert U.draw_overrides(book, [one, two], (0.0, s2)) == {**U.axis_overrides(book, two, s2), ELEM: base["2027"]}
    assert U.draw_overrides(book, [one, two], (0.0, 0.0)) == {NUM_A: k0, NUM_B: d0, ELEM: base["2027"]}
    mixed = U.draw_overrides(book, [one, a, two, elem], (s1, sa, s2, se))
    assert close(mixed[TRAJ]["2027"], base["2027"] + da + de + abs(s1) * (0.0 - base["2027"]), rel=1e-15, abs_=1e-15)
    assert close(mixed[NUM_A], got[NUM_A], rel=1e-15) and ELEM not in mixed
    assert mixed == U.draw_overrides(book, [elem, two, a, one], (se, s2, sa, s1))
    # прогон на осях на общем пути — сетка книги, собранной руками
    facts = fixture_facts()
    manual = dict(base)
    for key in manual:
        manual[key] = base[key] + da + db + (de if key == "2027" else 0.0)
    by_hand = book.with_overrides({TRAJ: {**book.get(TRAJ), **manual}})
    drawn = U.draw_book(book, [a, b, elem], (sa, sb, se))
    x, y = run_grid(drawn, facts), run_grid(by_hand, facts)
    assert close(x.point, y.point, rel=1e-12) and abs(x.point - fixture_run().point) > 0.5


def check_dict_axes_on_one_table() -> None:
    """Две оси-словаря на одной таблице (М§10): приращения складываются до нормировки, а нормировка одна —
    результат пересчитан по формуле; с одной осью — прежняя формула бит в бит. Концы осей здесь не в сумме 1:
    нормировка после каждой оси дала бы другое число."""
    book = fixture_book()
    base = {k: float(v) for k, v in book.get(TABLE).items()}
    one = _table({"soft": 0.20, "norm": 0.45, "downturn": 0.30, "crisis": 0.10},
                 {"soft": 0.10, "norm": 0.35, "downturn": 0.30, "crisis": 0.20}, "первая")
    two = _table({"soft": 0.15, "norm": 0.40, "downturn": 0.25, "crisis": 0.12},
                 {"soft": 0.15, "norm": 0.30, "downturn": 0.36, "crisis": 0.28}, "вторая")
    assert abs(sum(one["low"].values()) - 1) > 0.01 and abs(sum(two["high"].values()) - 1) > 0.01
    for s1, s2 in ((0.6, -0.9), (-1.0, 1.0), (0.3, 0.3)):
        e1, e2 = one["high" if s1 >= 0 else "low"], two["high" if s2 >= 0 else "low"]
        mix = {k: base[k] + abs(s1) * (e1[k] - base[k]) + abs(s2) * (e2[k] - base[k]) for k in base}
        want = {k: v / sum(mix.values()) for k, v in mix.items()}
        got = U.draw_overrides(book, [one, two], (s1, s2))
        assert set(got) == {TABLE} and all(close(got[TABLE][k], want[k], rel=1e-14) for k in base), (s1, s2)
        assert close(sum(got[TABLE].values()), 1.0, abs_=1e-14)
        swapped = U.draw_overrides(book, [two, one], (s2, s1))
        assert all(close(swapped[TABLE][k], want[k], rel=1e-14) for k in base)
        last_only = U.axis_overrides(book, two, s2)[TABLE]
        assert max(abs(got[TABLE][k] - last_only[k]) for k in base) > 1e-3       # вторая ось первую не затёрла
        step = U.axis_overrides(book, one, s1)[TABLE]                            # нормировка после первой оси
        chained = {k: step[k] + abs(s2) * (e2[k] - base[k]) for k in base}
        chained = {k: v / sum(chained.values()) for k, v in chained.items()}
        assert max(abs(got[TABLE][k] - chained[k]) for k in base) > 1e-4, (s1, s2)
    assert U.draw_overrides(book, [one, two], (0.6, 0.0))[TABLE] == U.axis_overrides(book, one, 0.6)[TABLE]
    assert U.draw_overrides(book, [one], (0.6,)) == U.axis_overrides(book, one, 0.6)
    assert U.mixed_table(base, [(one, -0.4)]) == U.axis_overrides(book, one, -0.4)[TABLE]
    zero = U.draw_overrides(book, [one, two], (0.0, 0.0))[TABLE]
    assert all(close(zero[k], base[k], rel=1e-15) for k in base)


def check_single_axes_are_the_former_overrides() -> None:
    """С одной осью на пути и на таблице подмены прогона — прежние бит в бит: на осях книг форм образца (в том
    числе со связкой на пути оси `shift`) подмены равны подменам прежнего порядка в каждой точке гиперкуба."""
    from tests.support_core_t4 import bundle_book

    books = [fixture_book(), bundle_book()]
    kinds: set[str] = set()
    for book in books:
        axes = list(book.get("valuation.uncertainty.axes"))
        kinds |= {str(a["kind"]) for a in axes}
        for s in U.draw_points(12, len(axes), 20261014) + [[0.0] * len(axes), [1.0] * len(axes), [-1.0] * len(axes)]:
            new, old = U.draw_overrides(book, axes, s), _old_draw_overrides(book, axes, s)
            assert new == old and list(new) == list(old), book.get("meta.version")
    assert {"value", "shift", "dict", "bundle"} <= kinds
    shared = [p for a in books[1].get("valuation.uncertainty.axes") if a["kind"] == "bundle" for p in a["paths"]
              if any(p == o or p.startswith(o + ".") for x in books[1].get("valuation.uncertainty.axes")
                     if x["kind"] == "shift" for o in x["paths"])]
    assert shared, "у книги формы образца нет связки на пути оси shift"


def _axes_book(*extra: dict, replace: bool = False) -> dict:
    data = fixture_dict()
    axes = data["valuation"]["uncertainty"]["axes"]
    data["valuation"]["uncertainty"]["axes"] = list(extra) if replace else axes + list(extra)
    return data


def check_common_path_refusals() -> None:
    """Где складывать нечего — отказ схемы, а не молчание (М§10, прил. A № 14): ось вида `value` на общем пути с
    любой другой осью — тот же путь, траектория над ним, элемент под ним; ось-словарь на общем пути с осью вида
    `shift`, `bundle` или `value`; отрицательная доля в худшем углу двух осей-словарей. Оси `shift` и связки
    делят путь в любом сочетании, оси-словари — таблицу. Прогон на осях мимо схемы — тот же отказ."""
    facts = fixture_facts()
    book = fixture_book()
    value = lambda path, lo, hi: {"name": "значение", "kind": "value", "paths": [path], "low": lo, "high": hi,  # noqa: E731
                                  "dist": "triangular"}
    # ось value: тот же путь (ось сдвига), траектория над ним, элемент под ним, другая ось value
    R._refused(_axes_book(_shift([NUM_A], -0.01, 0.01)), NUM_A, "вида value", "задаёт значение пути")
    R._refused(_axes_book(value(ELEM, 0.0, 0.05)), ELEM, "вида value", "вида shift")
    R._refused(_axes_book(value(NUM_A, 0.02, 0.09)), NUM_A, "вида value")
    R._refused(_axes_book(value("regimes.crisis.nim_shift.2027", -0.02, 0.0)), "nim_shift.2027", "вида value")
    R._refused(_axes_book(_shift(["regimes.crisis.nim_shift"], -0.01, 0.01)), "nim_shift", "вида value", "вида shift")
    # ось-словарь: элемент таблицы под осью value и под осью shift; связка — отказ правила связок
    R._refused(_axes_book(value("joint.world_prob.N", 0.2, 0.5)), "joint.world_prob", "вида dict", "вида value")
    R._refused(_axes_book(_shift(["joint.world_prob.N"], -0.05, 0.05)), "joint.world_prob", "вида dict", "вида shift")
    R._refused(_axes_book(_bundle({"joint.world_prob.N": (0.2, 0.5)})), "joint.world_prob.N", "вида dict")
    # худший угол двух осей-словарей: доля ниже нуля — отказ; каждая ось по отдельности допустима
    base = dict(book.get(TABLE))
    low1 = {**base, "crisis": 0.05, "norm": base["norm"] + 0.10}
    low2 = {**base, "crisis": 0.04, "norm": base["norm"] + 0.11}
    high = dict(base)
    one, two = _table(low1, high, "первая"), _table(low2, high, "вторая")
    spare = [a for a in fixture_dict()["valuation"]["uncertainty"]["axes"] if a["paths"] != [TABLE]]
    book_from_dict(_axes_book(*spare, one, replace=True), facts=facts)
    book_from_dict(_axes_book(*spare, two, replace=True), facts=facts)
    R._refused(_axes_book(*spare, one, two, replace=True), TABLE, "худшем углу", "crisis")
    mild = _table({**base, "crisis": 0.12, "norm": base["norm"] + 0.03}, high, "мягкая")
    book_from_dict(_axes_book(*spare, one, mild, replace=True), facts=facts)        # сумма приращений выше нуля
    # оси shift и связки делят путь: книга принята
    book_from_dict(_axes_book(_shift([TRAJ], -0.01, 0.01, "вторая ось сдвига"), _shift([ELEM], -0.01, 0.01)),
                   facts=facts)
    spare_k = [a for a in fixture_dict()["valuation"]["uncertainty"]["axes"] if a["paths"] not in ([NUM_A], [NUM_B])]
    two_bundles = _axes_book(*spare_k, _bundle({NUM_A: (0.02, 0.09), ELEM: (0.0, 0.05)}, "первая связка"),
                             _bundle({NUM_A: (0.03, 0.11), NUM_B: (1.5, 3.0)}, "вторая связка"), replace=True)
    try:
        book_from_dict(two_bundles, facts=facts)
    except BookError as exc:
        raise AssertionError(f"схема отказала двум связкам на общем пути: {str(exc)[:300]}") from exc
    # прогон на осях мимо схемы: ось value на общем пути и ось-словарь с осью иного вида — отказ, а не затирание
    for axes in ([value(NUM_A, 0.02, 0.09), _shift([NUM_A], -0.01, 0.01)],
                 [_shift([NUM_A], -0.01, 0.01), value(NUM_A, 0.02, 0.09)],
                 [_shift([TRAJ], -0.01, 0.01), value(ELEM, 0.0, 0.05)],
                 [value(ELEM, 0.0, 0.05), _shift([TRAJ], -0.01, 0.01)],
                 [value(NUM_A, 0.02, 0.09), value(NUM_A, 0.03, 0.08)],
                 [_table(base, base), _shift([TABLE + ".crisis"], -0.01, 0.01)],
                 [_table(base, base), _bundle({TABLE + ".crisis": (0.1, 0.2)})]):
        try:
            U.draw_overrides(book, axes, [0.5] * len(axes))
        except BookError as exc:
            assert "стоит и на оси" in str(exc), str(exc)
        else:
            raise AssertionError(f"подмены приняты: {[a['kind'] for a in axes]}")


def check_price_of_an_axis_on_a_common_path() -> None:
    """Цена ошибки суждения каждой из двух осей на общем пути считается при другой оси на книге (М§10): цена на
    конце оси — точка книги с подменами одной этой оси."""
    book = fixture_book()
    facts = fixture_facts()
    live = live_from_book(book, facts)
    a, b = _shift([TRAJ], -0.005, 0.025, "первая"), _shift([ELEM], -0.02, 0.03, "вторая")
    point, ends = U._axis_prices(book, facts, live, [a, b], 0.5, None)
    lam_point = lambda r: r.low + 0.5 * (r.high - r.low)  # noqa: E731
    assert close(point, lam_point(run_grid(book, facts, live)), rel=1e-12)
    for ax, (low, high) in zip((a, b), ends):
        for s, got in ((-1.0, low), (1.0, high)):
            alone = run_grid(book.with_overrides(U.axis_overrides(book, ax, s)), facts, live)
            assert close(got, lam_point(alone), rel=1e-12), (ax["name"], s)
    assert abs(ends[0][1] - point) > 0.5 and abs(ends[1][1] - point) > 0.01
