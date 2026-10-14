"""Проверки восьмого прохода ядра (строки М§18 «Аналитические тесты восьмого прохода»): добавочный капитал держит долю
RWA своей клетки (`capital.at1_share`, М§4.9–§4.11, свойства 20–27), надбавка за субординацию дополнительного капитала
(`capital.n20.t2_premium`, М§4.4, §4.11, свойства 28–31), прочие движения капитала за концом сетки
(`valuation.terminal.other_movements`, М§7); схема — прил. A № 31–33; пример — приложение L.

Фикстуры — формы образца `tests/fixtures/core` (у неё AT1_0 = 150 и купон якоря 9,7 в четвёртом квартале, база
дивиденда вычитает купон; ключи подставляет тест), докапитализации (`tests/support_core_recap.py`) и полная фикстура
формы Т (`core_t`: квартальный календарь, рост по капиталу, множитель плотности режима); числовой пример — приложение L
методики (`tests/fixtures/core_pass8/example.json`). Каждая проверка — тождество или закрытая формула, выведенная из
книги, фактов и рядов клетки независимо от кода ядра: доля α_c — факт AT1_0 (файл фактов), делённый на RWA клетки в
квартале q_α − 1 (ряд); RWA — по остаткам книг клетки и плотностям книги; баланс, капитал, купон, надбавка — по рядам
клетки, ставкам миров и дням кварталов; терминал — строками М§7 по рядам конца сетки. Те же функции зовут тесты
`tests/test_core_pass8.py` и мутационный набор `tests/mutations.py` (мутации с M600).

«Тихая» книга (`QUIET`) — путь капитала от нормативов не зависит: доля выплаты и выплата избытка — ноль.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from model.book import book_from_dict
from model.book_schema import KEYS, BookError, validate
from model.capital import CapitalConst, RwaWeights, ratios
from model.checks import check_invariants
from model.grid import GridRun, path_inputs, path_key, run_grid, run_paths
from model.paths import Trajectory, path_value, shift_trajectory
from model.valuation import terminal
from tests import support_core_pass5 as S5
from tests import support_core_pass7 as S7
from tests import support_core_recap as R
from tests.support_core import fixture_dict, fixture_facts
from tests.support_core_recap import close

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE: dict[str, Any] = json.loads((ROOT / "tests" / "fixtures" / "core_pass8" / "example.json")
                                     .read_text(encoding="utf-8"))
TOL = 1e-9                                   # допуск примера приложения L (М§17)
A1, TP, OMK = "capital.at1_share", "capital.n20.t2_premium", "valuation.terminal.other_movements"
T2, OM = "capital.n20.t2", "equity.other_movements"
FROM = "2029Q1"                              # квартал ключа доли AT1 фикстуры: q_α = 11, доля — конца 2028К4
SPREAD, PI = 0.04, 0.025
QUIET = S5.QUIET
LIQ_TIGHT = {"volumes.liquid_min_share": 0.25}   # минимум ликвидности связывает в части кварталов с выпуском
# Траектория T2 с надбавкой: равна T2_0 до конца 2027 года, первый отход от базы — 2028К1 (свойство 31)
TRAJ_P: dict[str, Any] = {"2026Q2": 500.3, "2027": 500.3, "2028": 520.0, "LT": 600.0, "LT_from": 2031}
# Прочие движения: значение года last_period (2036) отличается от LT — терминал читает год L + 1, т. е. LT
OM_TRAJ: dict[str, Any] = {"2026": -1.0, "2036": -3.0, "LT": -5.0}
OM_SHIFT = -0.25                             # конец оси `shift` на траектории прочих движений (пример L.6)


def at1_key(when: str = FROM, *, enabled: bool = True, spread: float = SPREAD, base: Any = "anchor") -> dict:
    return {A1: {"enabled": enabled, "from": when, "spread": spread, "base": base}}


def t2p_key(*, enabled: bool = True, spread: float = PI, base: Any = "anchor") -> dict:
    return {TP: {"enabled": enabled, "spread": spread, "base": base}}


OM_KEY = {OMK: "flat_rub"}
ALL_OFF = {**at1_key(enabled=False), **t2p_key(enabled=False), OMK: "none"}


def grid(changes: Mapping[str, Any] | None = None) -> GridRun:
    """Сетка книги фикстуры формы образца с подменами (одна на набор подмен)."""
    return S5.grid(changes)


def first_period(run: GridRun | None = None) -> str:
    return str((run.ctx.book if run is not None else grid().ctx.book).get("meta.first_period"))


# ------------------------------------------------------------------ чтение книги и фактов своим счётом


def at1_0(run: GridRun) -> float:
    """AT1_0 — факт якоря (`facts/balance.json → equity.at1`)."""
    return float(run.ctx.facts.need("balance", "equity.at1"))


def nci_0(run: GridRun) -> float:
    return float(run.ctx.facts.need("balance", "equity.nci"))


def coupon_facts(run: GridRun) -> tuple[float, int]:
    return (float(run.ctx.facts.need("capital", "at1.coupon_annual")),
            int(run.ctx.facts.need("capital", "at1.coupon_quarter")))


def q_alpha(run: GridRun) -> int:
    return run.ctx.timeline.index(str(run.ctx.book.get(f"{A1}.from")))


def base_alpha(run: GridRun) -> float:
    b = run.ctx.book.get(f"{A1}.base")
    return at1_0(run) if b == "anchor" else float(b)


def base_t2(run: GridRun) -> float:
    b = run.ctx.book.get(f"{TP}.base")
    return path_value(run.ctx.book.get(T2), run.ctx.timeline.period(0)) if b == "anchor" else float(b)


def alpha_of(run: GridRun, c: Any) -> float:
    """α_c = AT1_0 / RWA_c,(q_α − 1): факт якоря и RWA клетки (ряд) в квартале q_α − 1."""
    return at1_0(run) / c.quarters["rwa"][q_alpha(run) - 1]


def days(run: GridRun, q: int) -> int:
    tl = run.ctx.timeline
    return (tl.end(q) - tl.end(q - 1)).days


def key_rate(run: GridRun, c: Any, q: int) -> float:
    """Ключевая ставка мира клетки в квартале q — путь мира прогона."""
    return run.ctx.worlds[c.world].key[q]


def regime_mult(run: GridRun, c: Any, q: int) -> float:
    traj = run.ctx.book.get(f"regimes.{c.regime}").get("rwa_density_mult")
    return 1.0 if traj is None else path_value(traj, run.ctx.timeline.period(q))


# ------------------------------------------------------------------ без ключей и выключатели (М§0.1)


def check_off_is_the_sample() -> None:
    """Без ключей, при `enabled: false` (с полями и без них), при `none` и при `spread: 0` у надбавки расчёт прежний
    бит в бит — на фикстуре формы образца, докапитализации и полной форме Т; ряды AT1 книги без ключа — факт якоря,
    купон сверх базы и надбавка — ноль; подмена одного пути `capital.at1_share.enabled` и
    `capital.n20.t2_premium.enabled` считается в обе стороны, и вариант одного слоя другой не трогает."""
    base = grid()
    for off in (at1_key(enabled=False), {A1: {"enabled": False}}, t2p_key(enabled=False), {TP: {"enabled": False}},
                {OMK: "none"}, ALL_OFF):
        R.cells_equal(base, grid(off))
        assert all(a.tv_ddm == b.tv_ddm and a.decisions == b.decisions for a, b in zip(base.cells, grid(off).cells))
    for c in base.cells:
        assert all(c.quarters["at1"][q] == at1_0(base) for q in range(base.ctx.timeline.Q + 1)), c.label
        assert all(c.quarters["coupon_new"][q] == 0.0 and c.quarters["t2_premium"][q] == 0.0
                   for q in range(1, base.ctx.timeline.Q + 1)), c.label
    R.cells_equal(grid({T2: S7.TRAJ}), grid({T2: S7.TRAJ, **t2p_key(spread=0.0)}))       # свойство 29: spread 0
    recap, recap_off = R.grid_of(), R.grid_of(ALL_OFF)
    R.cells_equal(recap, recap_off)
    assert all(a.recaps == b.recaps for a, b in zip(recap.cells, recap_off.cells))
    R.cells_equal(S5.t_grid(), S5.t_grid(ALL_OFF))
    R.cells_equal(t_grid(), t_grid(ALL_OFF))
    # подмена одного пути выключателя — в обе стороны; вариант одного слоя другой слой не трогает
    facts = fixture_facts()
    both = {**at1_key(), **t2p_key(), T2: S7.TRAJ}
    on = S5.book_of(both)
    off = S5.book_of({**at1_key(enabled=False), **t2p_key(enabled=False), T2: S7.TRAJ})
    R.cells_equal(grid({T2: S7.TRAJ, **t2p_key()}), run_grid(on.with_overrides({f"{A1}.enabled": False}), facts))
    R.cells_equal(grid({T2: S7.TRAJ, **at1_key()}), run_grid(on.with_overrides({f"{TP}.enabled": False}), facts))
    R.cells_equal(grid(both), run_grid(off.with_overrides({f"{A1}.enabled": True, f"{TP}.enabled": True}), facts))
    keyed = grid(at1_key())
    assert any(a.quarters["n20"] != b.quarters["n20"] for a, b in zip(base.cells, keyed.cells))
    assert any(a.quarters["nii"] != b.quarters["nii"] for a, b in zip(grid({T2: S7.TRAJ}).cells, grid(both).cells))


def check_anchor_row_does_not_depend_on_the_keys() -> None:
    """Строка якоря от ключей не зависит (М§4.11, «Якорь»): все ряды квартала якоря прежние, AT1 — факт якоря."""
    base, keyed = grid(), grid({**at1_key(first_period()), **t2p_key(), **OM_KEY, T2: S7.TRAJ})
    plain = grid({T2: S7.TRAJ})
    for a, b in zip(plain.cells, keyed.cells):
        for name, row in a.quarters.items():
            assert row[0] == b.quarters[name][0], (a.label, name)
        assert b.quarters["at1"][0] == at1_0(base)


# ------------------------------------------------------------------ доля AT1 и путь (свойства 20, 21, 24)


def check_share_rows(run: GridRun) -> set[float]:
    """Свойства 20 и 21 на сетке с ключом: в каждом квартале каждой клетки с q ≥ q_α ряд AT1 равен `α_c × RWA_q` (α_c —
    AT1_0, делённый на RWA клетки в q_α − 1), при q < q_α — AT1_0; K20 по рядам клетки с этим AT1 и K11 без AT1 — её ряды;
    слагаемое `N20 − (K20 − AT1) / RWA − A_20` — α_c во всех кварталах с q_α, включая последний. → доли клеток."""
    tl = run.ctx.timeline
    qa, a0 = q_alpha(run), at1_0(run)
    shares = set()
    for c in run.cells:
        q_ = c.quarters
        alpha = alpha_of(run, c)
        shares.add(alpha)
        for q in range(tl.Q + 1):
            want = a0 if q < qa else alpha * q_["rwa"][q]
            assert close(q_["at1"][q], want, rel=1e-12, abs_=1e-9), (c.label, tl.period(q), q_["at1"][q], want)
            br = S7.bvreg(run, c, q)
            assert close(q_["k20"][q], br - q_["ded20"][q] + q_["at1"][q] + q_["t2"][q], rel=1e-12, abs_=1e-8), \
                (c.label, q)
            e = q_["e_unaudited"][q]
            if e is not None and q_["k11"][q] is not None:
                assert close(q_["k11"][q], br - max(e, 0.0) - q_["ded11"][q], rel=1e-12, abs_=1e-8), (c.label, q)
            if q >= qa:
                term = q_["n20"][q] - (q_["k20"][q] - q_["at1"][q]) / q_["rwa"][q] - S7.a20(run, c, q)
                assert abs(term - alpha) < 1e-12, (c.label, tl.period(q), term, alpha)
    return shares


def check_share_and_path() -> None:
    """Доля и путь AT1 (свойства 20, 21) на фикстуре формы образца и докапитализации: у клеток разных миров и режимов —
    свои доли; при `from` = `first_period` доля одна у всех клеток — `AT1_0 / RWA_0` (свойство 24)."""
    shares = check_share_rows(grid(at1_key()))
    assert len(shares) >= 6, len(shares)
    run = grid(at1_key(first_period()))
    shares = check_share_rows(run)
    anchor = at1_0(run) / run.cells[0].quarters["rwa"][0]
    assert all(abs(s - anchor) < 1e-15 for s in shares), (shares, anchor)
    check_share_rows(R.grid_of(at1_key()))


# ------------------------------------------------------------------ неподвижная точка и баланс (свойство 22)


def _rwa_of_balance(run: GridRun, c: Any, q: int) -> float:
    """RWA квартала по остаткам окончательного баланса клетки (книги, бумаги, ликвидность, прочие активы, приращение
    постоянной части) и плотностям книги, с дрейфом плотности и множителем режима (М§4.11) — своим счётом."""
    assert run.ctx.book.get("capital.rwa.fx.enabled") is False
    base, _ = S5._rwa_base(run, c, q)
    return base * S5._dn(run, q) * regime_mult(run, c, q)


def check_fixed_point(run: GridRun) -> int:
    """Свойство 22: RWA квартала, пересчитанные по остаткам окончательного баланса клетки формулой §4.11, равны её ряду
    (1e-12); тождество баланса держится с AT1_q на стороне пассивов; добор опта — `max(0, LA_min − LA_x − I_q)`, где
    LA_x — балансирующие активы окончательного баланса при AT1_(q−1) до добора, I_q — выпуск квартала: в квартале со
    связанным минимумом добор меньше, чем без выпуска, ровно на I_q. → число кварталов со связанным минимумом и выпуском."""
    tl, book = run.ctx.timeline, run.ctx.book
    m = float(book.get("volumes.liquid_min_share"))
    nci = nci_0(run)
    bound = 0
    for c in run.cells:
        q_ = c.quarters
        for q in range(1, tl.Q + 1):
            assert close(q_["rwa"][q], _rwa_of_balance(run, c, q), rel=1e-12), (c.label, tl.period(q))
            assets = q_["loans"][q] - q_["allowance"][q] + q_["securities"][q] + q_["liquidity"][q] + q_["other_assets"][q]
            liab = (q_["funds"][q] + q_["wholesale"][q] + q_["other_liabilities"][q] + q_["dp"][q] + q_["bv"][q]
                    + q_["at1"][q] + nci)
            assert close(assets, liab, rel=1e-12), (c.label, tl.period(q), assets - liab)
            nonbal = q_["loans"][q] - q_["allowance"][q] + q_["other_assets"][q]
            wh_base = q_["wholesale"][q] - q_["wholesale_extra"][q]
            la_x = (q_["funds"][q] + q_["other_liabilities"][q] + q_["dp"][q] + q_["at1"][q - 1] + nci + wh_base
                    + q_["bv"][q] - nonbal)
            issue = q_["at1"][q] - q_["at1"][q - 1]
            la_min = m * nonbal / (1 - m)
            extra = max(0.0, la_min - la_x - issue)
            assert close(q_["wholesale_extra"][q], extra, rel=1e-9, abs_=1e-7), (c.label, tl.period(q))
            if extra > 1e-6 and issue > 1e-6:
                assert close(max(0.0, la_min - la_x) - q_["wholesale_extra"][q], issue, rel=1e-9, abs_=1e-7)
                bound += 1
    return bound


def check_fixed_point_and_balance() -> None:
    """Свойство 22 на книге фикстуры с ключом, где минимум ликвидности не связывает (ветвь A), и с подменой минимума,
    где он связывает в части кварталов с выпуском (ветвь B) — обе ветви закрытой формы."""
    assert check_fixed_point(grid(at1_key())) == 0
    tight = grid({**at1_key(), **LIQ_TIGHT})
    assert check_fixed_point(tight) >= 50
    check_share_rows(tight)
    mult = grid({**at1_key(first_period()), **LIQ_TIGHT, **S5.SOFT_MULT})
    assert check_fixed_point(mult) >= 50
    check_share_rows(mult)


# ------------------------------------------------------------------ купон (свойство 23) и база дивиденда


def check_coupon(run: GridRun) -> None:
    """Свойство 23: ряд купона — `CPN_ann × [h(q) = квартал купона] + (key_W,q + s_α) × (AT1_(q−1) − B_α) × d_q / 365`,
    ряд купона сверх базы — второе слагаемое; тождество капитала держится с ним."""
    tl = run.ctx.timeline
    cpn, h_cpn = coupon_facts(run)
    s, base = float(run.ctx.book.get(f"{A1}.spread")), base_alpha(run)
    for c in run.cells:
        q_ = c.quarters
        for q in range(1, tl.Q + 1):
            new = (key_rate(run, c, q) + s) * (q_["at1"][q - 1] - base) * days(run, q) / 365
            assert close(q_["coupon_new"][q], new, rel=1e-12, abs_=1e-12), (c.label, tl.period(q))
            want = (cpn if tl.h(q) == h_cpn else 0.0) + new
            assert close(q_["coupon"][q], want, rel=1e-12, abs_=1e-12), (c.label, tl.period(q))
            rhs = (q_["bv"][q - 1] + q_["ni_sh"][q] - q_["coupon"][q] * (1 - q_["tau_stat"][q]) + q_["oci"][q]
                   + q_["om"][q] - q_["div"][q] + (q_["rec"][q] or 0.0))
            assert close(q_["bv"][q], rhs, rel=1e-12), (c.label, tl.period(q))


def check_coupon_rows() -> None:
    """Купон на книге с ключом (база anchor: до q_α сверх базы — ноль) и с базой-числом B_α ≠ AT1_0 (купон сверх базы
    с первого квартала, `c_α,q × (AT1_0 − B_α) × d_q / 365`)."""
    run = grid(at1_key())
    check_coupon(run)
    qa = q_alpha(run)
    assert all(c.quarters["coupon_new"][q] == 0.0 for c in run.cells for q in range(1, qa + 1))
    assert any(c.quarters["coupon_new"][q] > 0.0 for c in run.cells for q in range(qa + 1, run.ctx.timeline.Q + 1))
    low = grid(at1_key(base=at1_0(run) - 40.0))
    check_coupon(low)
    assert all(c.quarters["coupon_new"][1] > 0.0 for c in low.cells)


def check_dividend_base_carries_the_new_coupon() -> None:
    """База дивиденда (М§5.2, `deduct_at1_after_tax: true` фикстуры): база решения года Y, все кварталы которого в сетке,
    — `Σ ЧП акционерам − Σ купон × (1 − τ_stat,Y)` по рядам клетки, где ряд купона — купон якоря и купон сверх базы;
    годы с купоном сверх базы в решениях есть."""
    run = grid(at1_key(base=0.0))
    tl = run.ctx.timeline
    assert run.ctx.book.get("dividends.policy.deduct_at1_after_tax") is True
    seen = 0
    for c in run.cells:
        q_ = c.quarters
        for dec in c.decisions:
            qs = tl.quarters_of_year(dec.year)
            if min(qs) < 1 or max(qs) > tl.Q:
                continue
            want = sum(q_["ni_sh"][q] - q_["coupon"][q] * (1 - q_["tau_stat"][q]) for q in qs)
            assert close(dec.base, want, rel=1e-12, abs_=1e-9), (c.label, dec.year, dec.base, want)
            seen += any(q_["coupon_new"][q] for q in qs)
    assert seen >= 36, seen


def check_quarter_base_carries_the_new_coupon() -> None:
    """База дивиденда квартального календаря (М§5.7.3, фикстура Т с `deduct_at1_after_tax: true`): база решения
    квартала прибыли — среднее окна W кварталов `ЧП акционерам − купон × (1 − τ_stat)` по рядам клетки (купон — с
    купоном сверх базы)."""
    run = t_grid({**at1_key(base=0.0), "dividends.policy.deduct_at1_after_tax": True})
    tl, window = run.ctx.timeline, run.ctx.prep.policy.window
    seen = 0
    for c in run.cells:
        q_ = c.quarters
        for dec in c.decisions:
            if dec.source == "register" or getattr(dec, "period", None) is None:
                continue
            idx = tl.index(dec.period)
            qs = range(idx - window + 1, idx + 1)
            if min(qs) < 1:
                continue
            want = sum(q_["ni_sh"][q] - q_["coupon"][q] * (1 - q_["tau_stat"][q]) for q in qs) / window
            assert close(dec.base, want, rel=1e-12, abs_=1e-9), (c.label, dec.period, dec.base, want)
            seen += any(q_["coupon_new"][q] for q in qs)
    assert seen >= 36, seen


# ------------------------------------------------------------------ тихая книга (свойство 25)


def check_quiet_book() -> None:
    """Свойство 25: на книге, у которой путь капитала от нормативов не зависит, до квартала q_α все ряды — бит в бит
    книги без ключа, а в квартале q_α ЧПД, прибыль и совокупный доход — бит в бит (выпуск — деньги конца квартала,
    купон сверх базы при базе anchor — ноль); при нулевых плотностях балансирующих активов RWA во всех кварталах — бит
    в бит книги без ключа."""
    base, keyed = grid(QUIET), grid({**QUIET, **at1_key()})
    qa = q_alpha(keyed)
    for a, b in zip(base.cells, keyed.cells):
        for name, row in a.quarters.items():
            assert row[:qa] == b.quarters[name][:qa], (a.label, name)
        for name in ("nii", "pbt", "ni_sh", "ci", "coupon", "int_income", "int_expense"):
            assert a.quarters[name][qa] == b.quarters[name][qa], (a.label, name)
        assert a.quarters["rwa"][qa] != b.quarters["rwa"][qa], a.label
    flat_base, flat_key = grid({**QUIET, **R.NO_RISK_WEIGHT}), grid({**QUIET, **R.NO_RISK_WEIGHT, **at1_key()})
    for a, b in zip(flat_base.cells, flat_key.cells):
        assert a.quarters["rwa"] == b.quarters["rwa"], a.label
        assert a.quarters["bv"] != b.quarters["bv"], a.label


# ------------------------------------------------------------------ проходы: пробные и запись шага


def check_dividend_trial_carries_its_own_share() -> None:
    """Пробный проход дивиденда — прогноз клетки, правило доли AT1 в нём то же (М§4.11): на книге с нулевой выплатой
    нормативы и RWA пробного прохода в точках проверки равны строкам окончательного прохода бит в бит — и в проходе,
    который идёт через квартал q_α − 1 и задаёт долю своими RWA (с выпуском и неподвижной точкой), и в проходах,
    которые несут её состоянием."""
    import model.cell as MC

    seen: list[tuple] = []
    orig = MC._Cell.trial

    def trial(self, st, q_a, year):
        out = orig(self, st, q_a, year)
        seen.append((q_a, year, out, self.world, self.regime, self.scenario))
        return out

    MC._Cell.trial = trial
    try:
        when = "2028Q4"                      # собрание 2028К2, точки 2028К3 (= q_α − 1) и 2028К4 (= q_α)
        run = run_grid(S5.book_of({**QUIET, **at1_key(when), **LIQ_TIGHT}), fixture_facts())
    finally:
        MC._Cell.trial = orig
    qa = run.ctx.timeline.index(when)
    through = after = 0
    for q_a, year, points, *cell in seen:
        c = run.cell(*cell)
        for q, pt in zip(S7._checkpoints(run, q_a, year), points):
            assert pt.rwa == c.quarters["rwa"][q] and pt.n20 == c.quarters["n20"][q], (cell, q, pt.n20)
            assert pt.n11 == c.quarters["n11"][q], (cell, q)
            if q >= qa:
                through += q_a <= qa - 1
                after += q_a > qa - 1
    assert through >= 20 and after >= 36, (through, after)


def check_recap_trial_and_second_order() -> None:
    """Пробный проход взноса, идущий через квартал q_α − 1, задаёт долю своими RWA: первое решение воспроизводится по
    сетке без взносов (свойство 11 §4.14.5). Свойство 27: в квартале взноса K20 окончательного расчёта выше пробного на
    `Rec − (Ded′ − Ded) + (χ_c + α_c) × (RWA′ − RWA)`, а `RWA′ − RWA = w × Rec / (1 − w × α_c)`, пока минимум
    ликвидности не связывает; K11 — на `Rec − (Ded′11 − Ded11)`; остаток — в допуске `recap_covers_gap`."""
    plain0 = R.grid_of()
    q_r = R.first_agm(plain0)
    when = plain0.ctx.timeline.period(q_r + 1)          # q_α − 1 = квартал решения: окно пробного прохода — через него
    run, rows = R._first_decisions(at1_key(when))
    made = 0
    for c, plain, dec in rows:
        s, point, norm = R.trial_shortfall(plain, dec.q, dec.last)
        assert close(dec.shortfall, s, rel=1e-12), (c.label, dec.shortfall, s)
        assert (dec.point, dec.norm) == (point, norm), c.label
        made += dec.rec > 0
    assert made >= 10, made
    first = first_period(plain0)
    run, rows = R._first_decisions({T2: S7.TRAJ, **S7.key(first), **at1_key(first)})
    fired = [f.name for f in check_invariants(run) if f.fired]
    assert not fired, fired
    book = run.ctx.book
    dens = book.get("capital.rwa.density")
    sec = float(book.get("volumes.securities_share_of_liquid"))
    w_bal = float(dens["securities"]) * sec + float(dens["liquidity"]) * (1 - sec)
    checked = 0
    for c, plain, dec in rows:
        if not dec.rec > 0:
            continue
        q, a, b = dec.q, c.quarters, plain.quarters
        if a["wholesale_extra"][q] or b["wholesale_extra"][q]:
            continue
        alpha = at1_0(run) / a["rwa"][0]
        chi = path_value(book.get(T2), run.ctx.timeline.period(0)) / a["rwa"][0]
        w = w_bal * S5._dn(run, q) * regime_mult(run, c, q)
        d_rwa = a["rwa"][q] - b["rwa"][q]
        assert close(d_rwa, w * dec.rec / (1 - w * alpha), rel=1e-9, abs_=1e-9), (c.label, d_rwa)
        assert close(a["at1"][q] - b["at1"][q], alpha * d_rwa, rel=1e-9, abs_=1e-9), c.label
        d20, d11 = a["ded20"][q] - b["ded20"][q], a["ded11"][q] - b["ded11"][q]
        assert close(a["k20"][q] - b["k20"][q], dec.rec - d20 + (chi + alpha) * d_rwa, rel=1e-12, abs_=1e-8), c.label
        assert close(a["k11"][q] - b["k11"][q], dec.rec - d11, rel=1e-12, abs_=1e-8), c.label
        assert dec.residual <= R.RECAP_RESIDUAL_SHARE * dec.rec
        checked += 1
    assert checked >= 10, checked


T_AT1, T_COUPON = 40.0, 3.0                  # добавочный капитал фикстуры Т (у неё AT1_0 = 0): из капитала акционеров
_T_GRIDS: dict[str, GridRun] = {}


def t_facts_at1() -> Any:
    """Факты полной фикстуры формы Т с добавочным капиталом: AT1_0 = 40 за счёт капитала акционеров (капитал группы и
    баланс якоря те же), купон якоря 3 в год. У фикстуры Т AT1_0 = 0, и доля α_c была бы нулём."""
    from model.book import Facts
    from tests.support_core_t import t_facts

    base = t_facts()
    files = copy.deepcopy(dict(base.files))
    eq = files["balance"]["equity"]
    eq["at1"]["v"] = float(eq["at1"]["v"]) + T_AT1
    eq["bv_common"]["v"] = float(eq["bv_common"]["v"]) - T_AT1
    files["capital"]["at1"]["coupon_annual"]["v"] = T_COUPON
    return Facts(root=base.root, files=files, digest=f"{base.digest}+at1{T_AT1}")


def t_grid(changes: Mapping[str, Any] | None = None) -> GridRun:
    """Сетка полной фикстуры формы Т с добавочным капиталом (`t_facts_at1`) и подменами книги."""
    from tests.support_core_t import book_live, put, t_dict

    key = json.dumps(changes or {}, sort_keys=True, ensure_ascii=False)
    if key not in _T_GRIDS:
        data = t_dict()
        for dotted, value in (changes or {}).items():
            put(data, dotted, copy.deepcopy(value))
        facts = t_facts_at1()
        book = book_from_dict(data, facts=facts)
        _T_GRIDS[key] = run_grid(book, facts, book_live(book))
    return _T_GRIDS[key]


def t_keyed(extra: Mapping[str, Any] | None = None) -> GridRun:
    """Полная фикстура формы Т (с добавочным капиталом) с ключом доли AT1: квартал q_α − 1 — квартал с урезанным ростом
    и решением модели в клетке режима с множителем плотности (оценки «только нормативы» в нём есть, и рост урезан)."""
    base = t_grid()
    tl = base.ctx.timeline
    for c in base.cells:
        if c.regime != "crisis":
            continue
        for q in range(2, tl.Q):
            if (c.quarters["lam"][q] < 1.0 and c.quarters["div_model"][q]
                    and base.ctx.prep.regimes["crisis"].rwa_mult[q] != 1.0):
                return t_grid({**at1_key(tl.period(q + 1)), **(extra or {})})
    raise AssertionError("в фикстуре Т нет квартала с урезанным ростом и решением модели")


def check_growth_constraint_share_of_the_recorded_step() -> None:
    """Рост по капиталу (фикстура Т): доля состояния — AT1_0 / RWA записанного шага квартала q_α − 1 (урезанного), а не
    оценки «только нормативы»; неподвижная точка и баланс держатся; с q_α норматив связывающего — на требовании с
    глиссадой в допуске решателя."""
    run = t_keyed()
    check_share_rows(run)
    qa, gr = q_alpha(run), run.ctx.prep.growth
    assert [c for c in run.cells if c.quarters["lam"][qa - 1] < 1.0], "квартал q_α − 1 без урезанного роста"
    unsolved = {(c.key, per) for c in run.cells for per, _ in c.solver}
    hit = 0
    for c in run.cells:
        q_ = c.quarters
        for q in range(qa, run.ctx.timeline.Q + 1):
            if gr.lam_min < q_["lam"][q] < 1.0 and (c.key, run.ctx.timeline.period(q)) not in unsolved:
                gap = min(q_["n20"][q] - q_["req20_glide"][q], q_["n11_star"][q] - q_["req11_glide"][q])
                assert abs(gap) <= gr.tol + 1e-12, (c.label, q, gap)
                hit += 1
    assert hit >= 1, hit


# ------------------------------------------------------------------ надбавка за субординацию (свойства 28, 29, 31)


def check_premium(run: GridRun) -> None:
    """Свойство 28: в каждом квартале каждой клетки ряд надбавки — `π_T2 × (T2_(q−1) − B_T2) × d_q / 365` по ряду T2
    клетки (база anchor — T2 строки якоря); процентные расходы клетки — проценты пассивов книг плюс надбавка; ЧПД —
    доход минус расход минус взносы АСВ плюс сдвиг; тождество отчёта о прибыли держится."""
    tl, prep = run.ctx.timeline, run.ctx.prep
    pi, base = float(run.ctx.book.get(f"{TP}.spread")), base_t2(run)
    liabilities = prep.roles.liabilities
    for c in run.cells:
        q_ = c.quarters
        for q in range(1, tl.Q + 1):
            d = days(run, q)
            sp = pi * (q_["t2"][q - 1] - base) * d / 365
            assert close(q_["t2_premium"][q], sp, rel=1e-12, abs_=1e-12), (c.label, tl.period(q))
            books = sum(c.books[b]["rate"][q] * c.books[b]["avg"][q] for b in liabilities) * d / 365
            assert close(q_["int_expense"][q], books + sp, rel=1e-12), (c.label, tl.period(q))
            assert close(q_["nii"][q], q_["int_income"][q] - q_["int_expense"][q] - q_["dia"][q] + q_["overlay"][q],
                         rel=1e-12, abs_=1e-9), (c.label, tl.period(q))
            pbt = (q_["nii"][q] - q_["llp"][q] - q_["fvc"][q] + q_["fees"][q] + q_["ins"][q] + q_["misc"][q]
                   + q_["fvr"][q] + q_["noncore"][q] - q_["opex"][q] + q_["one_off"][q])
            assert close(q_["pbt"][q], pbt, rel=1e-12, abs_=1e-9), (c.label, tl.period(q))


def check_premium_rows() -> None:
    """Надбавка по траектории T2 и по доле T2 своей клетки (свойство 28); база-число; свойство 31: до квартала, в
    котором T2 впервые отходит от базы (2028К1 траектории `TRAJ_P`), ряды — бит в бит книги без ключа."""
    plain, keyed = grid({T2: TRAJ_P}), grid({T2: TRAJ_P, **t2p_key()})
    check_premium(keyed)
    tl = keyed.ctx.timeline
    first = next(q for q in range(1, tl.Q + 1) if path_value(TRAJ_P, tl.period(q)) != path_value(TRAJ_P, tl.period(0)))
    assert tl.period(first) == "2028Q1"
    for a, b in zip(plain.cells, keyed.cells):
        for name, row in a.quarters.items():
            if name != "t2_premium":
                assert row[:first + 1] == b.quarters[name][:first + 1], (a.label, name)
        assert b.quarters["t2_premium"][first + 1] > 0.0 and a.quarters["nii"][first + 1] != b.quarters["nii"][first + 1]
    check_premium(grid({T2: S7.TRAJ, **S7.key(), **t2p_key()}))
    check_premium(grid({T2: TRAJ_P, **t2p_key(base=550.0)}))


# ------------------------------------------------------------------ терминал (свойства 26, 30; прочие движения)


def check_terminal_rows(run: GridRun) -> None:
    """Свойства 26 и 30 (λ_F = 1): совокупный доход года T + 1 = ROE_T × BV* — строки М§7 по рядам конца сетки:
    `[(PBT_L + SP_L)(1 + g_T) − π_T2 (T2_Q − B_T2) − Y_X](1 − τ_eff)(1 − nci) − (CPN_ann + (key_Q + s_α) ΔAT1_Q)(1 −
    τ_stat)`."""
    tl, book = run.ctx.timeline, run.ctx.book
    Q, L = tl.Q, tl.year(tl.Q)
    cpn, _ = coupon_facts(run)
    nci = float(book.get("pnl.nci_share"))
    keyed_a1 = book.opt(A1) is not None and book.get(f"{A1}.enabled") is True
    keyed_tp = book.opt(TP) is not None and book.get(f"{TP}.enabled") is True
    for c in run.cells:
        q_ = c.quarters
        qs = [q for q in range(1, Q + 1) if tl.year(q) == L]
        pbt_l = sum(q_["pbt"][q] for q in qs)
        sp_l = sum(q_["t2_premium"][q] for q in qs) if keyed_tp else 0.0
        sp_t1 = float(book.get(f"{TP}.spread")) * (q_["t2"][Q] - base_t2(run)) if keyed_tp else 0.0
        new = ((key_rate(run, c, Q) + float(book.get(f"{A1}.spread"))) * (q_["at1"][Q] - base_alpha(run))
               if keyed_a1 else 0.0)
        ni = ((pbt_l + sp_l) * (1 + c.g_t) - sp_t1 - c.y_x) * (1 - q_["tau_eff"][Q]) * (1 - nci)
        ci = ni - (cpn + new) * (1 - q_["tau_stat"][Q])
        assert close(c.roe_t_raw * c.bv_star, ci, rel=1e-11, abs_=1e-8), (c.label, c.roe_t_raw * c.bv_star, ci)


def check_terminal() -> None:
    """Терминал с ключами: строки NI_T+1 и CPN_T+1 (свойства 26, 30); κ_20 блока постоянных частей меньше, чем без ключа
    доли AT1, ровно на α_c, κ_11 прежний; DDM = RI в каждой клетке при λ_F = 0 и 1 со всеми тремя ключами."""
    check_terminal_rows(grid({T2: TRAJ_P, **at1_key(), **t2p_key()}))
    check_terminal_rows(grid({T2: S7.TRAJ, **S7.key(), **at1_key(base=100.0), **t2p_key(base=520.0)}))
    parts = {**QUIET, **S5.PARTS, S5.LAM: 0.0}
    base, keyed = grid(parts), grid({**parts, **at1_key()})
    for c, x, y in zip(keyed.cells, run_paths(base.ctx), run_paths(keyed.ctx)):
        alpha = alpha_of(keyed, c)
        assert close(x.fixed["kappa20"] - y.fixed["kappa20"], alpha, rel=1e-12, abs_=1e-15), (c.label, alpha)
        assert x.fixed["kappa11"] == y.fixed["kappa11"], c.label
    for lam in (0.0, 1.0):
        run = grid({**S5.PARTS, S5.LAM: lam, T2: TRAJ_P, OM: OM_TRAJ, **at1_key(), **t2p_key(), **OM_KEY})
        for c in run.cells:
            assert close(c.v_ddm, c.v_ri, rel=1e-11, abs_=1e-7), (c.label, lam)


def check_other_movements() -> None:
    """Прочие движения за концом сетки (М§7): с ключом `flat_rub` TV_RI, P_T и TV_DDM больше, чем при `none`, ровно на
    `OM_ann / k_T` (OM_ann = 4 × значение траектории в году L + 1 — LT, а не значение года L), X_T, BV*, ROE_T и ROE'_T
    — бит в бит, при λ_F = 0 и 1; проход клеток ключ не читает (отпечаток входов прохода тот же); ось `shift` на
    траектории двигает терминал ещё на `4 × Δ / k_T`; DC_T — от нового P_T."""
    om_ann = 4 * Trajectory(OM_TRAJ).year_value(grid().ctx.timeline.last_year + 1)
    assert om_ann == 4 * OM_TRAJ["LT"]
    for extra in ({}, {**S5.PARTS, S5.LAM: 0.0}):
        none, flat = grid({OM: OM_TRAJ, **extra}), grid({OM: OM_TRAJ, **extra, **OM_KEY})
        assert path_key(path_inputs(none.ctx)) == path_key(path_inputs(flat.ctx))
        for a, b in zip(none.cells, flat.cells):
            add = om_ann / a.k_t
            for f in ("tv_ri", "tv_ddm", "p_t"):
                assert close(getattr(b, f) - getattr(a, f), add, rel=1e-10, abs_=1e-9), (a.label, f)
            assert (a.x_t, a.bv_star, a.roe_t, a.roe_t_raw, a.g_t) == (b.x_t, b.bv_star, b.roe_t, b.roe_t_raw, b.g_t)
            assert a.quarters == b.quarters, a.label
            assert close(b.v_ddm, b.v_ri, rel=1e-11, abs_=1e-7), b.label
    moved = shift_trajectory(OM_TRAJ, OM_SHIFT)
    n0, f0 = grid({OM: OM_TRAJ}), grid({OM: OM_TRAJ, **OM_KEY})
    n1, f1 = grid({OM: moved}), grid({OM: moved, **OM_KEY})
    for a0, b0, a1, b1 in zip(n0.cells, f0.cells, n1.cells, f1.cells):
        got = (b1.tv_ri - a1.tv_ri) - (b0.tv_ri - a0.tv_ri)
        assert close(got, 4 * OM_SHIFT / a0.k_t, rel=1e-9, abs_=1e-9), (a0.label, got)
    # DC_T — от нового P_T: слагаемое прочих движений уводит выплату в минус, цена размывания её несёт
    t = EXAMPLE["terminal"]["inputs"]
    args = _terminal_args(t, t["n20"]["rubles"], None)
    plain = terminal(**args, discount=0.07)
    om = -2 * plain.p_t * plain.k_t
    with_om = terminal(**args, discount=0.07, om_ann=om)
    assert plain.p_t > 0 > with_om.p_t and plain.dc_t == 0.0
    assert close(with_om.p_t, plain.p_t + om / plain.k_t, rel=1e-12)
    assert close(with_om.dc_t, 0.07 / 0.93 * (max(-with_om.x_t, 0.0) + max(-with_om.p_t, 0.0)), rel=1e-12)


# ------------------------------------------------------------------ мост (PAYLOAD §2)


def check_bridge_carries_the_change_of_at1() -> None:
    """Мост Н20.0 выпуска: тождество `start + Σ долей = end` держится; строка «прочее» несёт изменение инструментов —
    `E[AT1_e] − AT1_0 + E[T2_e] − T2_0 − (1 − f)(E[R_e] − R_0)` под весами смеси заголовка (купон сверх базы — в строке
    прибыли), у книги с ключом доли AT1 от `first_period` изменение AT1 не ноль."""
    from tests.support_core2 import contract
    from tests.support_core_pass3 import _release

    for name, changes in (("base", {}), ("key", at1_key(first_period()))):
        book = S5.book_of(changes)
        rel, data = _release(book)
        assert not contract(data), contract(data)[:5]
        bridge = data["capital"]["bridge"]
        assert close(bridge["start"] + sum(r["pp"] for r in bridge["rows"]), bridge["end"], abs_=1e-9)
        run = rel.run
        qe = run.ctx.timeline.index(bridge["to"])
        an, neu = run.layers["analytical"].prob, run.layers["macro_neutral"].prob
        mix = {k: run.lam * an[k] + (1 - run.lam) * neu[k] for k in an}

        def e(row: str, q: int) -> float:
            return sum(mix[c.key] * c.quarters[row][q] for c in run.cells)

        f = float(book.get("capital.n20.fvoci_recognition"))
        want = (e("at1", qe) - at1_0(run)) + (e("t2", qe) - e("t2", 0)) - (1 - f) * (e("reserve", qe) - e("reserve", 0))
        other = next(r for r in bridge["rows"] if r["key"] == "other")["amount"]
        assert close(other, want, abs_=0.011), (name, other, want)
        if name == "key":
            assert e("at1", qe) - at1_0(run) > 1.0


# ------------------------------------------------------------------ схема (прил. A № 31–33)


def _validated(changes: Mapping[str, Any]) -> str | None:
    """Отказ схемы книги фикстуры с подменами (None — годна)."""
    data = S5.book_dict(changes)
    try:
        validate(data)
    except BookError as exc:
        return str(exc)
    return None


def check_schema() -> None:
    """Ограничения № 31–33 (прил. A, пример L.7 на сетке фикстуры): узлы годны без ключей; при `enabled: true` нет
    `from`/`spread`/`base` — отказ; `spread: null` при включённом — отказ; квартал ключа вне [first_period; last_period]
    — отказ при любом `enabled`; база меньше нуля или не число и не anchor — отказ при любом `enabled`; лишнее поле, нет
    `enabled`, `enabled` не булево — отказ; `enabled: false` без полей — годен; вид прочих движений вне перечня — отказ;
    при `flat_rub` траектория, которая не читается в году L + 1, — отказ; ключи — в закрытом перечне схемы."""
    assert {f"{A1}.{k}" for k in ("enabled", "from", "spread", "base")} <= set(KEYS)
    assert {f"{TP}.{k}" for k in ("enabled", "spread", "base")} <= set(KEYS) and OMK in KEYS
    fx = fixture_dict()["meta"]
    first, last, anchor = str(fx["first_period"]), str(fx["last_period"]), str(fx["anchor_period"])
    q3 = "2027Q1"
    good = ({A1: {"enabled": True, "from": q3, "spread": 0.04, "base": "anchor"}},
            {A1: {"enabled": True, "from": first, "spread": 0.04, "base": 20}},
            {A1: {"enabled": True, "from": last, "spread": 0.0, "base": 0}},
            {A1: {"enabled": False}}, {A1: {"enabled": False, "spread": None}},
            {TP: {"enabled": True, "spread": 0.025, "base": "anchor"}}, {TP: {"enabled": False}},
            {TP: {"enabled": True, "spread": -0.01, "base": 400.0}},
            {OMK: "flat_rub"}, {OMK: "none"}, {OMK: "flat_rub", OM: {"2027Q3": 1.0, "2028": 2.0}})
    for case in good:
        assert _validated(case) is None, (case, _validated(case))
    bad = ((A1, {A1: {"enabled": True, "from": q3, "spread": 0.04}}),
           (A1, {A1: {"enabled": True, "from": q3, "base": "anchor"}}),
           (A1, {A1: {"enabled": True, "spread": 0.04, "base": "anchor"}}),
           (A1, {A1: {"enabled": True, "from": q3, "spread": None, "base": "anchor"}}),
           (A1, {A1: {"enabled": True, "from": anchor, "spread": 0.04, "base": "anchor"}}),
           (A1, {A1: {"enabled": False, "from": "2040Q1", "spread": 0.04, "base": "anchor"}}),
           (A1, {A1: {"enabled": False, "from": q3, "spread": 0.04, "base": -1}}),
           (A1, {A1: {"enabled": True, "from": q3, "spread": 0.04, "base": "fact"}}),
           (A1, {A1: {"enabled": True, "from": q3, "spread": "4%", "base": "anchor"}}),
           (A1, {A1: {"enabled": True, "from": "2027-1", "spread": 0.04, "base": "anchor"}}),
           (A1, {A1: {"enabled": "yes", "from": q3, "spread": 0.04, "base": "anchor"}}),
           (A1, {A1: {"from": q3, "spread": 0.04, "base": "anchor"}}),
           (A1, {A1: {"enabled": True, "from": q3, "spread": 0.04, "base": "anchor", "share": 0.01}}),
           (TP, {TP: {"enabled": True, "base": "anchor"}}),
           (TP, {TP: {"enabled": True, "spread": 0.025}}),
           (TP, {TP: {"enabled": False, "spread": 0.025, "base": -5.0}}),
           (TP, {TP: {"enabled": True, "spread": None, "base": "anchor"}}),
           (TP, {TP: {"enabled": 1, "spread": 0.025, "base": "anchor"}}),
           ("other_movements", {OMK: "growing"}),
           ("other_movements", {OMK: "flat_rub", OM: {"2026Q3": 1.0}}))
    for word, case in bad:
        err = _validated(case)
        assert err is not None and word in err, (case, err)


# ------------------------------------------------------------------ пример приложения L


def _fake_cell(alpha: float, prev: float) -> tuple[SimpleNamespace, SimpleNamespace]:
    """Клетка примера L.1 для функции выпуска ядра: одна кредитная книга с плотностью 1 (G — её остаток), плотности
    бумаг и ликвидности — b, дрейф, валютный индекс и множитель — единицы."""
    b = EXAMPLE["at1"]["inputs"]["b"][1]
    p = SimpleNamespace(dn=[1.0] * 5, rwa_w=RwaWeights(loans={"L": 1.0}, securities=b, liquidity=b, other_assets=0.0),
                        sec_share=0.5, oa_delta=None)
    cell = SimpleNamespace(p=p, x=[1.0] * 5, rg=SimpleNamespace(rwa_mult=None), world="L", regime="r", scenario="s",
                           tl=SimpleNamespace(period=lambda q: EXAMPLE["periods"][q]))
    return cell, SimpleNamespace(a1s=alpha, at1=prev)


def _terminal_args(t: Mapping[str, Any], n20: float, block: Mapping[str, float] | None, lam: float | None = None
                   ) -> dict[str, Any]:
    return dict(n20=n20, req20=t["req20"], n11_star=t["n11_star"], req11=t["req11"], rwa=t["rwa"], bv_q=t["bv_q"],
                pbt_last_year=t["pbt_l"], y_balancing=t["y_bal"], c_wholesale=t["c_wh"], headroom=t["headroom"],
                tau_eff=t["tau"], nci_share=t["nci"], coupon_annual=t["coupon"], tau_stat=t["tau_stat"],
                lt_inflation=t["lt_inflation"], real_growth=t["real_growth"], fade=t["fade"], multiple=t["multiple"],
                k_t=t["k_t"], min_share=t["min_share"], wholesale_extra=t["wt"], fixed=block, lam_f=lam)


def check_example_l() -> None:
    """Пример приложения L (L.1–L.4, L.6) до 1e-9 (М§17): выпуск и неподвижная точка — функцией ядра
    `model.cell._Cell.at1_issue` (обе ветви, отказ при b × α ≥ 1), строки норматива конца сетки — `model.capital.ratios`,
    купон сверх базы и надбавка — формулами текста, терминал (пять записей × λ_F 1 и 0) — `model.valuation.terminal`,
    второй порядок взноса, ось прочих движений; схема — `check_schema`."""
    from model.cell import _Cell

    a1 = EXAMPLE["at1"]
    inp, key_path, rub = a1["inputs"], a1["path_key"], a1["path_rubles"]
    qa, alpha = inp["q_alpha"], key_path["alpha"]
    assert abs(inp["at1_0"] / key_path["rwa"][qa - 1] - alpha) < TOL
    at1 = inp["at1_0"]
    for q in range(1, 5):
        g, b, la_x, la_min = inp["g"][q], inp["b"][q], inp["la_x"][q], inp["la_min"][q]
        prev = at1
        if q >= qa:
            cell, st = _fake_cell(alpha, prev)
            at1 = _Cell.at1_issue(cell, st, q, {"L": g}, 0.0, la_x + 0.0, la_min)
        la = max(la_x + at1 - prev, la_min)
        rwa = g + b * la
        for name, got in (("at1", at1), ("rwa", rwa), ("la", la), ("wholesale_extra", max(0.0, la_min - la_x - at1 + prev)),
                          ("issue", at1 - prev)):
            assert abs(got - key_path[name][q]) < TOL, (q, name, got, key_path[name][q])
        if q >= qa:
            assert abs(at1 / rwa - alpha) < TOL
        la_r = max(la_x, la_min)
        assert abs(g + b * la_r - rub["rwa"][q]) < TOL and abs(la_r - rub["la"][q]) < TOL
    nfp = a1["mutation_no_fixed_point"]
    assert abs(alpha * nfp["rwa_without_issue"] - nfp["at1"]) < TOL
    cell, st = _fake_cell(5.0, inp["at1_0"])
    try:
        _Cell.at1_issue(cell, st, 3, {"L": 1.0}, 0.0, 10.0, 0.0)
    except BookError as exc:
        assert "b × α_c" in str(exc) and EXAMPLE["periods"][3] in str(exc)
    else:
        raise AssertionError("b × α ≥ 1 — без отказа")
    # купон сверх базы
    for q in range(1, 5):
        new = (inp["key"][q] + inp["spread"]) * (key_path["at1"][q - 1] - inp["base"]) * EXAMPLE["days"][q] / 365
        assert abs(new - a1["coupons"]["coupon_new"][q]) < TOL
        full = (inp["coupon_annual"] if q == 4 else 0.0) + new
        assert abs(full - a1["coupons"]["coupon"][q]) < TOL
    # строки норматива конца сетки
    cap = a1["capital"]
    const = CapitalConst(ded20_0=cap["ded20_0"], ded11_0=cap["ded20_0"], rwa0=inp["rwa_0"], fvoci_recognition=1.0,
                         gap20=cap["gap20"], gap11=0.0, at1=inp["at1_0"], audit_cutoffs=(3, 4), buffer20=0.0,
                         buffer11=0.0)
    for name, row in a1["rows_Q"].items():
        got = ratios(const, bv=cap["bvreg"], dpreg=0.0, reserve=0.0, unaudited=0.0, t2=cap["t2"], rwa=row["rwa"],
                     ded_pp20=cap["dpp20"], ded_pp11=0.0, at1=None if name == "rubles" else row["at1"])
        for f in ("ded20", "k20", "n20"):
            assert abs(getattr(got, f) - row[f]) < TOL, (name, f)
        assert abs(got.n20 - (got.k20 - row["at1"]) / row["rwa"] - (cap["gap20"] - cap["dpp20"]) - row["at1_term"]) < TOL
    # L.2: надбавка
    tp = EXAMPLE["t2_premium"]
    t2s = tp["inputs"]["t2"]
    sp = [None] + [tp["inputs"]["spread"] * (t2s[q - 1] - tp["inputs"]["base"]) * EXAMPLE["days"][q] / 365
                   for q in range(1, 5)]
    assert all(abs(sp[q] - tp["sp"][q]) < TOL for q in range(1, 5))
    assert abs(sum(sp[1:]) - tp["sp_L"]) < TOL
    assert abs(tp["inputs"]["spread"] * (t2s[-1] - tp["inputs"]["base"]) - tp["sp_T1"]) < TOL
    # L.3: терминал — пять записей × λ_F 1 и 0
    t = EXAMPLE["terminal"]["inputs"]
    blk = t["block"]
    new_cpn = (t["key_Q"] + t["spread"]) * (t["at1_key"] - t["base"])
    assert abs(t["at1_key"] - t["alpha"] * t["rwa"]) < TOL
    assert abs((t["k20_without_at1"] + t["at1_key"]) / t["rwa"] - 0.001 - t["n20"]["key"]) < TOL
    keys = {"sample": (False, False, False), "K1": (True, False, False), "K2": (False, True, False),
            "K3": (False, False, True), "K1K2K3": (True, True, True)}
    for name, (k1, k2, k3) in keys.items():
        for lam, label in ((1.0, "lam1"), (0.0, "lam0")):
            want = EXAMPLE["terminal"]["records"][name][label]
            kappa20 = blk["kappa20_sample"] - blk["chi"] - (t["alpha"] if k1 else 0.0)
            block = {"f_a": blk["f_a"], "r_f": blk["r_f"], "c20": blk["c20"], "c11": blk["c11"], "kappa20": kappa20,
                     "kappa11": blk["kappa11"]}
            args = _terminal_args(t, t["n20"]["key" if k1 else "rubles"], block, lam)
            got = terminal(**args, coupon_new=new_cpn if k1 else None, sp_l=t["sp_L"] if k2 else None,
                           sp_t1=t["sp_T1"] if k2 else 0.0, om_ann=4 * t["om_lt_quarter"] if k3 else 0.0)
            for f, w in (("x_t", want["x_t"]), ("bv_star", want["bv_star"]), ("ni_t1", want["ni"]),
                         ("ci_t1", want["ci"]), ("roe_raw", want["roe"]), ("roe_t", want["roe_faded"]),
                         ("p_t", want["p_t"]), ("tv_ri", want["tv_ri"]), ("tv_ddm", want["tv_ddm"]),
                         ("y_x", want["y_x"]), ("g_t", want["g"])):
                assert abs(getattr(got, f) - w) < TOL, (name, label, f, getattr(got, f), w)
            assert abs(got.tv_ddm - (t["bv_q"] + got.tv_ri)) < TOL
            assert abs(got.fixed["business_capital"] - want["business_capital"]) < TOL
            if lam == 0.0:
                for f in ("kappa", "f_k", "d_f", "i_f"):
                    assert abs(got.fixed[f] - want["block"][f]) < TOL, (name, f)
    # L.4: второй порядок взноса
    rc = EXAMPLE["recap"]
    ri = rc["inputs"]
    d_rwa = ri["b"] * ri["rec"] / (1 - ri["b"] * ri["alpha"])
    assert abs(d_rwa - rc["d_rwa"]) < TOL and abs(ri["b"] * ri["rec"] - rc["d_rwa_without_alpha"]) < TOL
    for f, v in (("d_ded20", ri["dgrow_over_rwa0"] * d_rwa), ("d_at1", ri["alpha"] * d_rwa), ("d_t2", ri["chi"] * d_rwa)):
        assert abs(v - rc[f]) < TOL, f
    assert abs(ri["rec"] - rc["d_ded20"] + rc["d_at1"] + rc["d_t2"] - rc["d_k20"]) < TOL
    # L.6: ось прочих движений
    assert abs(4 * OM_SHIFT / t["k_t"] - (-5.8873)) < 5e-5
    check_schema()
