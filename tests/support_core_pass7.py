"""Проверки седьмого прохода ядра (строки М§18 «Аналитические тесты седьмого прохода»): доля инструментов в RWA своей
клетки (`capital.n20.t2_share`, М§4.11, свойства 13–19, §4.14.1, §7, прил. A № 30, пример — приложение K).

Фикстуры — формы образца `tests/fixtures/core` (траектория инструментов `TRAJ` с ростом и ключ подставляет тест),
докапитализации (`tests/support_core_recap.py`) и полная фикстура формы Т (`core_t`: квартальный календарь, рост по
капиталу, множитель плотности режима); общий числовой пример — приложение K методики
(`tests/fixtures/core_pass7/example.json`). Каждая проверка — тождество или закрытая формула, выведенная из книги и
рядов клетки независимо от кода ядра: доля χ_c — значение траектории книги (своим чтением `path_value`) в квартале
q_χ − 1, делённое на RWA той же клетки в этом квартале (ряд клетки); K20 и K11 — по рядам клетки; слагаемое доли —
по поправке и пути вычета книги. Те же функции зовут тесты `tests/test_core_pass7.py` и мутационный набор
`tests/mutations.py`.

«Тихая» книга (`QUIET`, как в пятом проходе) — путь капитала от нормативов не зависит: доля выплаты и выплата избытка
— ноль, замыкания выключены. На ней RWA, K11 и Н20.1 книг с ключом и без него совпадают бит в бит, и разность K20 —
ровно разность T2.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from model.book import book_from_dict
from model.book_schema import KEYS, BookError, validate
from model.capital import CapitalConst, ratios
from model.checks import check_invariants
from model.grid import GridRun, run_grid, run_paths
from model.paths import path_value
from model.valuation import terminal
from tests import support_core_pass5 as S5
from tests import support_core_recap as R
from tests.support_core import fixture_dict, fixture_facts
from tests.support_core_recap import close

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE: dict[str, Any] = json.loads((ROOT / "tests" / "fixtures" / "core_pass7" / "example.json")
                                     .read_text(encoding="utf-8"))
TOL = 1e-9                                   # допуск примера приложения K (М§17)
KEY = "capital.n20.t2_share"
T2 = "capital.n20.t2"
G20, G11 = "capital.n20.gap_pp", "capital.n11.gap_pp"
# Траектория инструментов фикстуры с ростом: ключ квартала якоря явно — факт фикстуры (М§4.11), ключи лет —
# интерполяция; у формы Т — своя, от её факта
TRAJ: dict[str, Any] = {"2026Q2": 500.3, "2027": 530.0, "2029": 600.0, "LT": 700.0, "LT_from": 2033}
TRAJ_T: dict[str, Any] = {"2026Q2": 123.0, "2027": 135.0, "2029": 160.0, "LT": 190.0, "LT_from": 2033}
FROM = "2029Q1"                              # квартал ключа фикстуры: q_χ = 11, доля — конца 2028К4
ON = {"enabled": True, "from": FROM}
QUIET = S5.QUIET
SHIFT = 30.0                                 # сдвиг траектории проверки свойства 18, млрд ₽


def key(when: str = FROM, enabled: bool = True) -> dict[str, Any]:
    return {KEY: {"enabled": enabled, "from": when}}


def grid(changes: Mapping[str, Any] | None = None) -> GridRun:
    """Сетка книги фикстуры формы образца с траекторией `TRAJ` и подменами."""
    return S5.grid({T2: TRAJ, **(changes or {})})


def first_period(run: GridRun) -> str:
    return str(run.ctx.book.get("meta.first_period"))


def q_chi(run: GridRun) -> int:
    """q_χ — квартал ключа книги прогона (своим чтением книги)."""
    return run.ctx.timeline.index(str(run.ctx.book.get(f"{KEY}.from")))


def traj(run: GridRun, q: int) -> float:
    """Значение траектории инструментов книги в квартале q (М§0.4) — читателем путей, не рядом ядра."""
    return path_value(run.ctx.book.get(T2), run.ctx.timeline.period(q))


def chi_of(run: GridRun, c: Any) -> float:
    """χ_c = T2_(q_χ − 1) / RWA_c,(q_χ − 1): значение траектории книги и RWA клетки (ряд) в квартале q_χ − 1."""
    q = q_chi(run) - 1
    return traj(run, q) / c.quarters["rwa"][q]


def a20(run: GridRun, c: Any, q: int) -> float:
    """A_20,q — поправка «норматив − расчёт» минус путь вычета сценария клетки в п.п. (по книге)."""
    book = run.ctx.book
    return float(book.get(G20)) - path_value(book.get(f"capital.reg_scenarios.{c.scenario}.deduction_pp.n20_0"),
                                             run.ctx.timeline.period(q))


def bvreg(run: GridRun, c: Any, q: int) -> float:
    f = float(run.ctx.book.get("capital.n20.fvoci_recognition"))
    return c.quarters["bv"][q] + c.quarters["dpreg"][q] - (1 - f) * c.quarters["reserve"][q]


# ------------------------------------------------------------------ без ключа и выключатель (М§0.1, §4.11)


def check_off_is_the_sample() -> None:
    """Без ключа и при `enabled: false` (с полем `from` и без него) расчёт прежний бит в бит — на фикстуре формы
    образца, докапитализации и полной форме Т; ряд T2 книги без ключа — значение траектории в каждом квартале; подмена
    одного пути `capital.n20.t2_share.enabled` считается в обе стороны."""
    base = grid()
    for off in (key(enabled=False), {KEY: {"enabled": False}}, key(first_period(base), enabled=False)):
        R.cells_equal(base, grid(off))
        assert all(a.tv_ddm == b.tv_ddm and a.decisions == b.decisions for a, b in zip(base.cells, grid(off).cells))
    tl = base.ctx.timeline
    for c in base.cells:
        assert all(c.quarters["t2"][q] == traj(base, q) for q in range(tl.Q + 1)), c.label
    recap, recap_off = R.grid_of(), R.grid_of(key(enabled=False))
    R.cells_equal(recap, recap_off)
    assert all(a.recaps == b.recaps for a, b in zip(recap.cells, recap_off.cells))
    R.cells_equal(S5.t_grid(), S5.t_grid(key(enabled=False)))
    # подмена одного пути выключателя — в обе стороны
    facts = fixture_facts()
    on = S5.book_of({T2: TRAJ, **key()})
    off = S5.book_of({T2: TRAJ, **key(enabled=False)})
    R.cells_equal(base, run_grid(on.with_overrides({f"{KEY}.enabled": False}), facts))
    R.cells_equal(grid(key()), run_grid(off.with_overrides({f"{KEY}.enabled": True}), facts))
    keyed = grid(key())
    assert any(a.quarters["n20"] != b.quarters["n20"] for a, b in zip(base.cells, keyed.cells))


# ------------------------------------------------------------------ доля и путь (М§4.11, свойства 13, 14, 17)


def check_share_rows(run: GridRun) -> set[float]:
    """Свойства 13 и 14 на сетке с ключом: в каждом квартале каждой клетки с q ≥ q_χ ряд T2 равен `χ_c × RWA_q`
    (χ_c — значение траектории в q_χ − 1, делённое на RWA клетки в q_χ − 1), при q < q_χ — значению траектории;
    K20 по рядам клетки с этим T2 и K11 без T2 — её ряды; слагаемое `N20 − (K20 − T2) / RWA − A_20` — χ_c во всех
    кварталах с q_χ, включая последний квартал сетки. → множество долей клеток."""
    tl, book = run.ctx.timeline, run.ctx.book
    qc = q_chi(run)
    at1 = run.ctx.prep.af.at1
    shares = set()
    for c in run.cells:
        q_ = c.quarters
        chi = chi_of(run, c)
        shares.add(chi)
        for q in range(tl.Q + 1):
            t2 = traj(run, q) if q < qc else chi * q_["rwa"][q]
            assert close(q_["t2"][q], t2, rel=1e-12, abs_=1e-9), (c.label, tl.period(q), q_["t2"][q], t2)
            br = bvreg(run, c, q)
            assert close(q_["k20"][q], br - q_["ded20"][q] + at1 + t2, rel=1e-12, abs_=1e-8), (c.label, q)
            e = q_["e_unaudited"][q]
            if e is not None and q_["k11"][q] is not None:
                assert close(q_["k11"][q], br - max(e, 0.0) - q_["ded11"][q], rel=1e-12, abs_=1e-8), (c.label, q)
            if q >= qc:
                term = q_["n20"][q] - (q_["k20"][q] - q_["t2"][q]) / q_["rwa"][q] - a20(run, c, q)
                assert abs(term - chi) < 1e-12, (c.label, tl.period(q), term, chi)
        assert book.get(f"{KEY}.enabled") is True
    return shares


def check_share_and_path() -> None:
    """Доля и путь T2 (свойства 13, 14) на фикстуре формы образца, докапитализации и полной форме Т; у клеток разных
    миров и режимов — свои доли; при `from` = `first_period` доля одна у всех клеток — `T2_0 / RWA_0` (свойство 17);
    в клетке режима с множителем плотности доля — по RWA с множителем."""
    shares = check_share_rows(grid(key()))
    assert len(shares) >= 6, len(shares)
    run = grid(key(first_period(grid())))
    shares = check_share_rows(run)
    anchor = traj(run, 0) / run.cells[0].quarters["rwa"][0]
    assert all(abs(s - anchor) < 1e-15 for s in shares), (shares, anchor)
    assert traj(run, 1) != traj(run, 0)
    check_share_rows(R.grid_of({T2: TRAJ, **key(FROM)}))
    t = t_keyed()
    check_share_rows(t)
    mult = t.ctx.prep.regimes["crisis"].rwa_mult
    assert mult is not None and mult[q_chi(t) - 1] != 1.0


def check_anchor_row_does_not_depend_on_the_key() -> None:
    """Строка якоря от ключа не зависит (М§4.11, «Якорь»): все ряды квартала якоря — прежние, T2 — значение
    траектории."""
    base, keyed = grid(), grid(key(first_period(grid())))
    for a, b in zip(base.cells, keyed.cells):
        for name, row in a.quarters.items():
            assert row[0] == b.quarters[name][0], (a.label, name)
        assert b.quarters["t2"][0] == traj(base, 0)


# ------------------------------------------------------------------ тихая книга (свойства 15, 16, 18)


def check_quiet_book() -> None:
    """Свойство 15: на книге, у которой путь капитала от нормативов не зависит, RWA, K11, Н20.1 и Н20.1 с прибылью
    периода — бит в бит книги без ключа, K20 больше на `χ_c × RWA_q − T2_q`, избыток терминала — на
    `excess_capital_multiple × (χ_c × RWA_Q − T2_Q)` в клетках, где на T связывает Н20.0."""
    base, keyed = grid(QUIET), grid({**QUIET, **key()})
    tl = keyed.ctx.timeline
    qc, Q = q_chi(keyed), tl.Q
    m = float(keyed.ctx.book.get("valuation.terminal.excess_capital_multiple"))
    binding = 0
    for a, b in zip(base.cells, keyed.cells):
        for name in ("rwa", "k11", "n11", "n11_star", "bv", "ded20", "ded11", "dpreg"):
            assert a.quarters[name] == b.quarters[name], (a.label, name)
        chi = chi_of(keyed, b)
        for q in range(tl.Q + 1):
            want = (chi * b.quarters["rwa"][q] - traj(keyed, q)) if q >= qc else 0.0
            assert close(b.quarters["k20"][q] - a.quarters["k20"][q], want, rel=1e-9, abs_=1e-8), (a.label, q)

        def binds(c: Any) -> bool:
            q_ = c.quarters
            pend = q_["dpreg"][Q] / q_["rwa"][Q]
            return (q_["n20"][Q] - pend - q_["req20"][Q]) <= (c.n11_star - pend - q_["req11"][Q])

        if binds(a) and binds(b):
            want = m * (chi * b.quarters["rwa"][Q] - traj(keyed, Q))
            assert close(b.x_t - a.x_t, want, rel=1e-9, abs_=1e-7), (a.label, b.x_t - a.x_t, want)
            binding += 1
    assert binding >= 10, binding


def _record(run: GridRun, c: Any) -> dict[str, float]:
    """Траектория, записанная поквартально по ряду T2 клетки c (свойство 16): ключи кварталов до года last_period,
    год last_period — ключом года (квартальные ключи в нём запрещены, М§0.4)."""
    tl = run.ctx.timeline
    out: dict[str, Any] = {}
    last = [c.quarters["t2"][q] for q in range(tl.Q + 1) if tl.year(q) == tl.last_year]
    for q in range(tl.Q + 1):
        if tl.year(q) < tl.last_year:
            out[tl.period(q)] = c.quarters["t2"][q]
    out[str(tl.last_year)] = sum(last) / len(last)
    out["LT"] = out[str(tl.last_year)]
    return out


def check_record_on_one_cell() -> None:
    """Свойство 16: траектория, записанная по RWA одной клетки c*, `T2_q = χ_c* × RWA_c*,q`, даёт в этой клетке
    нормативы ключа (1e-12), а в клетке c — нормативы ниже нормативов ключа на `χ_c − T2_q / RWA_c,q` (выше, если её
    RWA растут медленнее); сравниваются кварталы до года last_period (в нём запись — ключ года)."""
    keyed = grid({**QUIET, **key()})
    tl, qc = keyed.ctx.timeline, q_chi(keyed)
    star = keyed.cell("H", "norm", "schedule")
    record = grid({**QUIET, T2: _record(keyed, star)})
    lower = higher = 0
    for a, b in zip(keyed.cells, record.cells):
        assert a.quarters["rwa"] == b.quarters["rwa"], a.label
        chi = chi_of(keyed, a)
        for q in range(qc, tl.Q + 1):
            if tl.year(q) == tl.last_year:
                break
            want = b.quarters["t2"][q] / b.quarters["rwa"][q] - chi
            got = b.quarters["n20"][q] - a.quarters["n20"][q]
            assert abs(got - want) < 1e-12, (a.label, tl.period(q), got, want)
            if a.key == star.key:
                assert abs(got) < 1e-12, (tl.period(q), got)
            lower += want < -1e-6
            higher += want > 1e-6
    assert lower and higher, (lower, higher)


def check_shift_moves_the_share() -> None:
    """Свойство 18: сдвиг траектории на Δ двигает долю клетки на `Δ / RWA_c,(q_χ − 1)` (на тихой книге RWA те же), и
    Н20.0 конца сетки — на то же число; без ключа — на `Δ / RWA_Q`."""
    moved = {k: (v if k == "LT_from" else v + SHIFT) for k, v in TRAJ.items()}
    a, b = grid({**QUIET, **key()}), grid({**QUIET, **key(), T2: moved})
    qc, Q = q_chi(a), a.ctx.timeline.Q
    for x, y in zip(a.cells, b.cells):
        rwa = x.quarters["rwa"][qc - 1]
        assert y.quarters["rwa"] == x.quarters["rwa"]
        assert close(chi_of(b, y) - chi_of(a, x), SHIFT / rwa, rel=1e-10, abs_=1e-15), x.label
        assert close(y.quarters["n20"][Q] - x.quarters["n20"][Q], SHIFT / rwa, rel=1e-8, abs_=1e-13), x.label
    p, r = grid(QUIET), grid({**QUIET, T2: moved})
    for x, y in zip(p.cells, r.cells):
        assert close(y.quarters["n20"][Q] - x.quarters["n20"][Q], SHIFT / x.quarters["rwa"][Q], rel=1e-8, abs_=1e-13)


# ------------------------------------------------------------------ проходы: пробные и запись шага (М§4.11)


def _checkpoints(run: GridRun, q_a: int, year: int) -> list[int]:
    """Точки проверки пробного прохода дивиденда года прибыли `year` (М§5.3 п. 1): кварталы политики года Y + 1 не
    раньше квартала решения, не дальше конца сетки (нет ни одной — последний квартал прохода)."""
    tl, pol = run.ctx.timeline, run.ctx.prep.policy
    cps = sorted(tl.index(f"{year + 1}Q{h}") for h in pol.checkpoints)
    cps = [c for c in cps if c >= q_a]
    return [c for c in cps if c <= tl.Q] or [min(max(cps) if cps else tl.Q, tl.Q)]


def check_dividend_trial_carries_its_own_share() -> None:
    """Пробный проход дивиденда — прогноз клетки, правило доли в нём то же (М§4.11): на книге с нулевой выплатой
    нормативы и RWA пробного прохода в точках проверки равны строкам окончательного прохода бит в бит — и в проходе,
    который идёт через квартал q_χ − 1 и задаёт долю своими RWA, и в проходах, которые несут её состоянием."""
    import model.cell as MC

    seen: list[tuple[int, int, list]] = []
    orig = MC._Cell.trial

    def trial(self, st, q_a, year):
        out = orig(self, st, q_a, year)
        seen.append((q_a, year, out, self.world, self.regime, self.scenario))
        return out

    MC._Cell.trial = trial
    try:
        when = "2028Q4"                      # собрание 2028К2, точки 2028К3 (= q_χ − 1) и 2028К4 (= q_χ)
        run = run_grid(S5.book_of({T2: TRAJ, **QUIET, **key(when)}), fixture_facts())
    finally:
        MC._Cell.trial = orig
    qc = run.ctx.timeline.index(when)
    through = after = 0
    for q_a, year, points, *cell in seen:
        c = run.cell(*cell)
        for q, pt in zip(_checkpoints(run, q_a, year), points):
            assert pt.rwa == c.quarters["rwa"][q] and pt.n20 == c.quarters["n20"][q], (cell, q, pt.n20)
            assert pt.n11 == c.quarters["n11"][q], (cell, q)
            if q >= qc:
                through += q_a <= qc - 1
                after += q_a > qc - 1
    assert through >= 20 and after >= 36, (through, after)


def check_recap_trial_and_second_order() -> None:
    """Пробный проход взноса, идущий через квартал q_χ − 1, задаёт долю своими RWA: первое решение воспроизводится по
    сетке без взносов (свойство 11 §4.14.5). В квартале взноса с q_χ K20 окончательного расчёта выше пробного на
    `Rec − (Ded′ − Ded) + χ_c × (RWA′ − RWA)`, K11 — на `Rec − (Ded′11 − Ded11)`; остаток — в допуске
    `recap_covers_gap` (свойства 3 и 4 §4.14.5, второй порядок §4.14.1)."""
    plain0 = R.grid_of()
    q_r = R.first_agm(plain0)
    when = plain0.ctx.timeline.period(q_r + 1)          # q_χ − 1 = квартал решения: окно пробного прохода — через него
    run, rows = R._first_decisions({T2: TRAJ, **key(when)})
    made = 0
    for c, plain, dec in rows:
        s, point, norm = R.trial_shortfall(plain, dec.q, dec.last)
        assert close(dec.shortfall, s, rel=1e-12), (c.label, dec.shortfall, s)
        assert (dec.point, dec.norm) == (point, norm), c.label
        made += dec.rec > 0
    assert made >= 10, made
    run, rows = R._first_decisions({T2: TRAJ, **key(first_period(plain0))})
    fired = [f.name for f in check_invariants(run) if f.fired]
    assert not fired, fired
    checked = 0
    for c, plain, dec in rows:
        if not dec.rec > 0:
            continue
        q, a, b = dec.q, c.quarters, plain.quarters
        chi = traj(run, 0) / a["rwa"][0]
        d20, d11 = a["ded20"][q] - b["ded20"][q], a["ded11"][q] - b["ded11"][q]
        d_rwa = a["rwa"][q] - b["rwa"][q]
        assert d_rwa >= 0 and close(a["t2"][q] - b["t2"][q], chi * d_rwa, rel=1e-9, abs_=1e-9)
        assert close(a["k20"][q] - b["k20"][q], dec.rec - d20 + chi * d_rwa, rel=1e-12, abs_=1e-8), c.label
        assert close(a["k11"][q] - b["k11"][q], dec.rec - d11, rel=1e-12, abs_=1e-8), c.label
        assert dec.residual <= R.RECAP_RESIDUAL_SHARE * dec.rec
        checked += 1
    assert checked >= 10, checked


def t_keyed() -> GridRun:
    """Полная фикстура формы Т с ключом: квартал q_χ − 1 — квартал с урезанным ростом и решением модели в клетке
    режима с множителем плотности (оценки «только нормативы» в нём есть, и рост урезан)."""
    base = S5.t_grid({T2: TRAJ_T})
    tl = base.ctx.timeline
    for c in base.cells:
        if c.regime != "crisis":
            continue
        for q in range(2, tl.Q):
            if (c.quarters["lam"][q] < 1.0 and c.quarters["div_model"][q]
                    and base.ctx.prep.regimes["crisis"].rwa_mult[q] != 1.0):
                return S5.t_grid({T2: TRAJ_T, **key(tl.period(q + 1))})
    raise AssertionError("в фикстуре Т нет квартала с урезанным ростом и решением модели")


def check_growth_constraint_share_of_the_recorded_step() -> None:
    """Рост по капиталу (фикстура Т): доля состояния — T2 / RWA записанного шага квартала q_χ − 1 (урезанного), а не
    оценки «только нормативы»; с q_χ норматив связывающего — на требовании с глиссадой в допуске решателя."""
    run = t_keyed()
    check_share_rows(run)
    qc, gr = q_chi(run), run.ctx.prep.growth
    cut = [c for c in run.cells if c.quarters["lam"][qc - 1] < 1.0]
    assert cut, "квартал q_χ − 1 без урезанного роста"
    unsolved = {(c.key, per) for c in run.cells for per, _ in c.solver}
    hit = 0
    for c in run.cells:
        q_ = c.quarters
        for q in range(qc, run.ctx.timeline.Q + 1):
            if gr.lam_min < q_["lam"][q] < 1.0 and (c.key, run.ctx.timeline.period(q)) not in unsolved:
                gap = min(q_["n20"][q] - q_["req20_glide"][q], q_["n11_star"][q] - q_["req11_glide"][q])
                assert abs(gap) <= gr.tol + 1e-12, (c.label, q, gap)
                hit += 1
    assert hit >= 1, hit


# ------------------------------------------------------------------ терминал (§7, свойство 19)


def check_terminal_block() -> None:
    """Свойство 19: в блоке постоянных частей терминала κ_20 меньше, чем без ключа, ровно на χ_c, κ_11 прежний; при
    связывающем на T Н20.1 блок от ключа не зависит; DDM = RI в каждой клетке при λ_F = 0 и 1."""
    parts = {**QUIET, **S5.PARTS}
    base, keyed = grid({**parts, S5.LAM: 0.0}), grid({**parts, S5.LAM: 0.0, **key()})
    pa, pk = run_paths(base.ctx), run_paths(keyed.ctx)
    for c, x, y in zip(keyed.cells, pa, pk):
        chi = chi_of(keyed, c)
        assert close(x.fixed["kappa20"] - y.fixed["kappa20"], chi, rel=1e-12, abs_=1e-15), (c.label, chi)
        assert x.fixed["kappa11"] == y.fixed["kappa11"], c.label
    tight = {**parts, **S5.N11_TIGHT, S5.LAM: 0.0}
    b11, k11 = grid(tight), grid({**tight, **key()})
    same = 0
    for a, b in zip(b11.cells, k11.cells):
        if a.terminal_fixed["binding"] == "n11" and b.terminal_fixed["binding"] == "n11":
            assert a.terminal_fixed == b.terminal_fixed and a.x_t == b.x_t, a.label
            same += 1
    assert same >= 10, same
    for lam in (0.0, 1.0):
        run = grid({**S5.PARTS, S5.LAM: lam, **key()})
        for c in run.cells:
            assert close(c.v_ddm, c.v_ri, rel=1e-11, abs_=1e-7), (c.label, lam)


def check_neutral_asset_with_the_key() -> None:
    """Нейтральность бездоходного актива с весом риска 0 при λ_F = 0 (§7) держится и с ключом: актив RWA не трогает,
    доля клеток та же, оценка клетки — та же, что без актива (отн. 1e-9)."""
    facts = S5._asset_facts(S5.ASSET)
    asset = {S5.LEVEL: S5.ASSET, S5.W_FIXED: 0.0, **S5.rub(flat=S5.ASSET)}
    extra = {**S5.NO_LIQUIDITY_MINIMUM, S5.LAM: 0.0, T2: TRAJ, **key()}
    plain, held = S5.grid(extra), S5.grid({**asset, **extra}, facts=facts, tag="asset")
    for x, y in zip(plain.cells, held.cells):
        assert all(close(u, v, rel=1e-12) for u, v in zip(x.quarters["t2"], y.quarters["t2"])), x.label
        assert close(y.v_ri, x.v_ri, rel=1e-9, abs_=1e-9), (x.label, y.v_ri - x.v_ri)


# ------------------------------------------------------------------ мост (М§4.11, PAYLOAD §2)


def check_bridge_carries_the_change_of_t2() -> None:
    """Мост Н20.0 выпуска: тождество `start + Σ долей = end` держится; строка «прочее» несёт изменение T2 — у книги с
    ключом от `first_period` её сумма больше, чем без ключа, на `E[T2_e](ключ) − E[T2_e](траектория)`, прочие строки
    прежние (до конца периода моста решений о дивиденде у фикстуры нет; тихая книга контракт выпуска не проходит —
    тест истории выплат)."""
    from tests.support_core2 import contract
    from tests.support_core_pass3 import _release

    out = {}
    for name, changes in (("base", {}), ("key", key(first_period(grid())))):
        book = S5.book_of({T2: TRAJ, **changes})
        rel, data = _release(book)
        assert not contract(data), contract(data)[:5]
        bridge = data["capital"]["bridge"]
        assert close(bridge["start"] + sum(r["pp"] for r in bridge["rows"]), bridge["end"], abs_=1e-9)
        run = rel.run
        qe = run.ctx.timeline.index(bridge["to"])
        an, neu = run.layers["analytical"].prob, run.layers["macro_neutral"].prob
        mix = {k: run.lam * an[k] + (1 - run.lam) * neu[k] for k in an}
        t2e = sum(mix[c.key] * c.quarters["t2"][qe] for c in run.cells)
        other = next(r for r in bridge["rows"] if r["key"] == "other")["amount"]
        out[name] = (t2e, other, {r["key"]: r["amount"] for r in bridge["rows"]})
    (t_b, o_b, rows_b), (t_k, o_k, rows_k) = out["base"], out["key"]
    assert abs(t_k - t_b) > 1.0
    assert close(o_k - o_b, t_k - t_b, abs_=0.011), (o_k - o_b, t_k - t_b)        # суммы выпуска — 2 знака
    assert all(rows_b[k] == rows_k[k] for k in rows_b if k not in ("other",)), (rows_b, rows_k)


# ------------------------------------------------------------------ схема (прил. A № 30)


def _validated(node: Any) -> str | None:
    """Отказ схемы книги фикстуры с узлом `capital.n20.t2_share` (None — годна)."""
    data = copy.deepcopy(fixture_dict())
    if node is not None:
        data["capital"]["n20"]["t2_share"] = node
    try:
        validate(data)
    except BookError as exc:
        return str(exc)
    return None


def _map(period: str, ex: Mapping[str, Any], fx_anchor: str) -> str:
    """Квартал примера K.7 на сетке фикстуры: то же положение относительно якоря (квартал вне сетки — вне сетки)."""
    if not isinstance(period, str) or "Q" not in period:
        return period
    def ix(p: str) -> int:
        return int(p[:4]) * 4 + int(p[-1])
    n = ix(fx_anchor) + ix(period) - ix(ex["anchor"])
    last_ex, last_fx = ix(ex["last_period"]), ix(str(fixture_dict()["meta"]["last_period"]))
    if ix(period) > last_ex:
        n = last_fx + ix(period) - last_ex
    return f"{(n - 1) // 4}Q{(n - 1) % 4 + 1}"


def check_schema_of_the_share() -> None:
    """Ограничение № 30 (прил. A): случаи примера K.7 на сетке фикстуры — `from` вне [first_period; last_period] (и
    квартал якоря), не квартал, `enabled: true` без `from`, `enabled` не булево, нет `enabled`, лишнее поле — отказ;
    `enabled: false` без `from` и с годным `from` — годен; ключи схемы — в закрытом перечне."""
    assert {f"{KEY}.enabled", f"{KEY}.from"} <= set(KEYS)
    fx_anchor = str(fixture_dict()["meta"]["anchor_period"])
    for case in EXAMPLE["schema"]:
        node = copy.deepcopy(case["spec"])
        if isinstance(node, dict) and "from" in node:
            node["from"] = _map(node["from"], case, fx_anchor)
        err = _validated(node)
        if case["result"].startswith("годен"):
            assert err is None, (case, err)
        else:
            assert err is not None and "t2_share" in err, (case, node)
    last = str(fixture_dict()["meta"]["last_period"])
    assert _validated({"enabled": True, "from": last}) is None
    for bad in ({"enabled": True, "from": FROM, "share": 0.01}, {"enabled": None, "from": FROM},
                {"enabled": False, "from": "2040Q1"}, {"enabled": True, "from": None}, 0.01, "2029Q1"):
        err = _validated(bad)
        assert err is not None and "t2_share" in err, bad


# ------------------------------------------------------------------ пример приложения K


def _const(c: Mapping[str, float]) -> CapitalConst:
    return CapitalConst(ded20_0=c["ded20_0"], ded11_0=c["ded11_0"], rwa0=c["rwa0"],
                        fvoci_recognition=c["fvoci_recognition"], gap20=c["gap20"], gap11=c["gap11"], at1=c["at1"],
                        audit_cutoffs=(3, 4), buffer20=0.0, buffer11=0.0)


def _terminal(src: Mapping[str, float], tin: Mapping[str, float], blk: Mapping[str, float], lam: float) -> Any:
    return terminal(n20=src["n20"], req20=tin["req20"], n11_star=src["n11_star"], req11=tin["req11"], rwa=tin["rwa"],
                    bv_q=tin["bv_q"], pbt_last_year=tin["pbt_l"], y_balancing=tin["y_bal"], c_wholesale=tin["c_wh"],
                    headroom=tin["headroom"], tau_eff=tin["tau"], nci_share=tin["nci"], coupon_annual=tin["coupon"],
                    tau_stat=tin["tau_stat"], lt_inflation=tin["lt_inflation"], real_growth=tin["real_growth"],
                    fade=tin["fade"], multiple=tin["multiple"], k_t=tin["k_t"], min_share=tin["min_share"],
                    wholesale_extra=tin["wt"], fixed=blk, lam_f=lam)


def check_example_k() -> None:
    """Пример приложения K (K.1–K.4, K.6, K.7) до 1e-9 (М§17): доля и путь T2 клеток, строки норматива конца сетки
    функцией ядра `model.capital.ratios`, слагаемое доли; X_T, κ_20 и терминал при λ_F = 1 и 0 функцией ядра
    `model.valuation.terminal` (κ_20 ключа — κ без ключа минус χ, как в `model.cell.fixed_block`); второй порядок
    взноса; тождество моста; сдвиг оси; случаи схемы — `check_schema_of_the_share`."""
    sh = EXAMPLE["share"]
    const = _const(sh["inputs"]["capital"])
    q_c = sh["inputs"]["q_chi"]
    traj_k = sh["inputs"]["trajectory"]
    for cell in ("A", "B"):
        path = sh["path"][cell]
        chi = traj_k[q_c - 1] / path["rwa"][q_c - 1]
        assert abs(chi - path["chi"]) < TOL
        for q, rwa in enumerate(path["rwa"]):
            t2 = traj_k[q] if q < q_c else chi * rwa
            assert abs(t2 - path["t2_key"][q]) < TOL and abs(t2 / rwa - path["share_key"][q]) < TOL, (cell, q)
            assert abs(traj_k[q] / rwa - path["share_record"][q]) < TOL
        qin = sh["inputs"]["quarter_Q"][cell]
        for name in ("key", "record"):
            want = sh["rows_Q"][cell][name]
            got = ratios(const, bv=qin["bv"], dpreg=qin["dpreg"], reserve=qin["reserve"], unaudited=qin["e"],
                         t2=want["t2"], rwa=qin["rwa"], ded_pp20=qin["dpp20"], ded_pp11=qin["dpp11"])
            for f in ("k20", "k11", "n20", "n11", "n11_star", "ded20", "ded11"):
                assert abs(getattr(got, f) - want[f]) < TOL, (cell, name, f)
            term = got.n20 - (got.k20 - want["t2"]) / qin["rwa"] - want["a20"]
            assert abs(term - want["share_term"]) < TOL, (cell, name)
        assert abs(sh["rows_Q"][cell]["n20_key_minus_record"] - (path["chi"] - traj_k[-1] / path["rwa"][-1])) < TOL
    # K.2: терминал и блок постоянных частей
    term = EXAMPLE["terminal"]
    tin, blocks = term["inputs"]["terminal"], term["inputs"]["blocks"]
    chi = term["inputs"]["chi"]
    assert abs(blocks["key"]["kappa20"] - (blocks["record"]["kappa20"] - chi)) < TOL
    assert blocks["key"]["kappa11"] == blocks["record"]["kappa11"]
    rows = sh["rows_Q"]["B"]
    for name in ("record", "key", "key_no_kappa"):
        src = rows["record"] if name == "record" else rows["key"]
        for lam in ("1", "0"):
            want = term["cases"][name][lam]
            got = _terminal(src, tin, blocks[name], float(lam))
            for f in ("x_t", "bv_star", "tv_ri", "tv_ddm", "p_t"):
                assert abs(getattr(got, f) - want[f]) < TOL, (name, lam, f)
            if lam == "0":
                for f, w in (("f_k", want["block"]["f_k"]), ("i_f", want["block"]["i_f"]),
                             ("business_capital", want["business_capital"])):
                    assert abs(got.fixed[f] - w) < TOL, (name, f)
    # K.3: второй порядок взноса — функцией норматива ядра на окончательной строке
    rc = EXAMPLE["recap"]
    qin = sh["inputs"]["quarter_Q"]["B"]
    w = rc["inputs"]["w_balancing"]
    rwa1 = qin["rwa"] + rc["d_rwa"]
    assert abs(rwa1 - qin["rwa"] - w * rc["rec"]) < TOL
    fin = ratios(const, bv=qin["bv"] + rc["rec"], dpreg=qin["dpreg"], reserve=qin["reserve"], unaudited=qin["e"],
                 t2=chi * rwa1, rwa=rwa1, ded_pp20=qin["dpp20"], ded_pp11=qin["dpp11"])
    assert abs(fin.n20 - rc["n20_final"]) < TOL and abs(fin.k20 - rows["key"]["k20"] - rc["k20_final_minus_trial"]) < TOL
    rho = rc["inputs"]["req20"] - const.gap20 + qin["dpp20"]
    second = w * (rho + const.ded20_0 / const.rwa0 - chi) * rc["rec"] / rwa1
    assert abs((fin.n20 - rc["inputs"]["req20"]) + second) < 1e-12 + TOL
    assert abs(rc["n20_final_minus_req"] + second) < TOL
    # K.4: тождество моста
    for name, row in EXAMPLE["bridge"]["by_record"].items():
        total = row["profit_pp"] + row["deductions_pp"] + row["rwa_growth_pp"] + row["other_pp"]
        assert abs(row["start"] + total - row["end"]) < TOL, name
        t2_end = rows["key" if name == "key" else "record"]["t2"]
        assert abs(row["other_amount"] - (t2_end - EXAMPLE["bridge"]["inputs"]["anchor"]["t2"])) < TOL, name
    # K.6: сдвиг оси
    ax = EXAMPLE["axis"]
    rwa_b = sh["path"]["B"]["rwa"]
    moved = [v + ax["delta"] for v in traj_k]
    chi6 = moved[q_c - 1] / rwa_b[q_c - 1]
    assert abs(chi6 - ax["chi"]) < TOL
    assert all(abs((moved[q] if q < q_c else chi6 * rwa_b[q]) - ax["t2_key"][q]) < TOL for q in range(len(rwa_b)))
    assert abs(ax["n20_shift_Q_key"] - ax["delta"] / rwa_b[q_c - 1]) < TOL
    assert abs(ax["n20_shift_Q_record"] - ax["delta"] / rwa_b[-1]) < TOL
    check_schema_of_the_share()
