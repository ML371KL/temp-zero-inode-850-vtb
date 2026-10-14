"""Проверки девятого прохода ядра (строки М§18 «Аналитические тесты девятого прохода»): разрыв налога по правилу
(`tax.structure`, М§4.8, §7, свойства 32–38) и купон добавочного капитала якоря по ставке своего мира
(`capital.at1_coupon`, М§4.9, §7, свойства 39–43); схема — прил. A № 34–35; пример — приложение M.

Фикстуры — формы образца `tests/fixtures/core` (у неё AT1_0 = 150, купон якоря 9,7 в четвёртом квартале, база дивиденда
вычитает купон, разовый убыток режима crisis в 2027К1 даёт убыточный квартал; ключи подставляет тест), докапитализации
(`tests/support_core_recap.py`) и полная фикстура формы Т с добавочным капиталом (`support_core_pass8.t_grid`:
квартальный календарь, рост по капиталу); числовой пример — приложение M методики
(`tests/fixtures/core_pass9/example.json`). Каждая проверка — тождество или закрытая формула, выведенная из книги,
фактов и рядов клетки независимо от кода ядра: налог — правилом §4.8 по прибыли до налога, процентному доходу книги бумаг
(ставка и средний остаток книги клетки × дни квартала / 365) и ряду купона; законная ставка — траектория книги; купон
якоря — формулой §4.9 по пути ключевой мира прогона; терминал — строками §7 по рядам конца сетки. Те же функции зовут
тесты `tests/test_core_pass9.py` и мутационный набор `tests/mutations.py` (мутации с M700).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from model.book import LIQUIDITY as LIQ, SECURITIES as SEC, WHOLESALE as WH
from model.book_schema import KEYS, BookError, validate
from model.checks import check_invariants
from model.grid import GridRun, run_grid
from model.nextreport import model_expectation
from model.paths import Trajectory
from tests import support_core_pass5 as S5
from tests import support_core_pass8 as S8
from tests import support_core_recap as R
from tests.support_core import fixture_dict, fixture_facts
from tests.support_core_recap import close

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE: dict[str, Any] = json.loads((ROOT / "tests" / "fixtures" / "core_pass9" / "example.json")
                                     .read_text(encoding="utf-8"))
TOL = 1e-9                                   # допуск примера приложения M (М§17)
TAXK, CPNK, GAP = "tax.structure", "capital.at1_coupon", "tax.effective_gap"
RULE: dict[str, Any] = {"bond_rate": 0.2, "bond_scale": 1.2, "other_pp": 0.02, "coupon_deductible": True}
COUPON: dict[str, float] = {"fixed": 3.0, "floating": 40.0, "spread": 0.05}   # при ключевой 12 % — 9,8 (слот 9,7)
NCI = {"pnl.nci_share": 0.05}                # доля неконтролирующих: у фикстуры формы образца — ноль
QUIET = S5.QUIET
LIQ_TIGHT = {"volumes.liquid_min_share": 0.25}   # добор опта на конце сетки — в части клеток (ветвь опта y^τ_m)


def tax_key(enabled: bool = True, **kw: Any) -> dict:
    return {TAXK: {"enabled": enabled, **RULE, **kw}}


def cpn_key(enabled: bool = True, **kw: Any) -> dict:
    return {CPNK: {"enabled": enabled, **COUPON, **kw}}


def _key_path() -> dict:
    """Путь ключевой мира N с ключом квартала якоря (2026H1: 0,16 — ключевая якоря отличается от первого квартала
    прогноза) и ключевой, меняющейся в последнем году сетки (2036H2: 0,06 — ставка квартала Q не равна средней года)."""
    path = dict(fixture_dict()["worlds"]["N"]["key_rate"])
    path.update({"2026H1": 0.16, "2036H2": 0.06})
    return {"worlds.N.key_rate": path}


KEY_PATH = _key_path()
ALL_OFF = {**tax_key(False), **cpn_key(False)}


def grid(changes: Mapping[str, Any] | None = None) -> GridRun:
    """Сетка книги фикстуры формы образца с подменами (одна на набор подмен)."""
    return S5.grid(changes)


# ------------------------------------------------------------------ чтение книги, фактов и рядов своим счётом


def days(run: GridRun, q: int) -> int:
    tl = run.ctx.timeline
    return (tl.end(q) - tl.end(q - 1)).days


def tau_stat(run: GridRun, q: int) -> float:
    """Законная ставка года квартала q — среднее четырёх кварталов траектории `tax.statutory` книги (М§0.4)."""
    t = Trajectory(run.ctx.book.get("tax.statutory"))
    y = run.ctx.timeline.year(q)
    return sum(t.value(y, n) for n in (1, 2, 3, 4)) / 4


def rule_of(run: GridRun) -> tuple[float, float, float, bool]:
    """(τ_b, ζ, o, δ_c) — ключ `tax.structure` книги прогона."""
    node = run.ctx.book.get(TAXK)
    return (float(node["bond_rate"]), float(node["bond_scale"]), float(node["other_pp"]),
            node["coupon_deductible"] is True)


def keyed(run: GridRun, path: str) -> bool:
    node = run.ctx.book.opt(path)
    return isinstance(node, Mapping) and node.get("enabled") is True


def iis_of(run: GridRun, c: Any, q: int) -> float:
    """IIS_q — процентный доход книги бумаг клетки: ставка книги квартала × средний остаток × d_q / 365 (М§4.4, §4.8)."""
    book = c.books[SEC]
    return book["rate"][q] * book["avg"][q] * days(run, q) / 365


def kbar(run: GridRun, c: Any, q: int) -> float:
    """k̄_q — средняя ключевая мира клетки за четыре квартала, кончая кварталом q; кварталы не позже якоря — ключевая
    квартала якоря (М§4.9)."""
    key = run.ctx.worlds[c.world].key
    return sum(key[max(q - j, 0)] for j in range(4)) / 4


def coupon_rule(run: GridRun) -> tuple[float, float, float]:
    node = run.ctx.book.get(CPNK)
    return float(node["fixed"]), float(node["floating"]), float(node["spread"])


def anchor_coupon_want(run: GridRun, c: Any, q: int) -> float:
    """Годовой купон якоря квартала купона q: `Cfix + Cflt × (k̄_q + s_flt)` у книги с ключом, слот фактов без него."""
    if not keyed(run, CPNK):
        return S8.coupon_facts(run)[0]
    fixed, floating, spread = coupon_rule(run)
    return fixed + floating * (kbar(run, c, q) + spread)


def ni_sh_fact(run: GridRun, q: int) -> float:
    """ЧП акционерам квартала не позже якоря — факт `pnl_quarterly`."""
    per = run.ctx.timeline.period(q)
    return float(run.ctx.facts.file("pnl_quarterly")["quarters"][per]["ni_shareholders"]["v"])


# ------------------------------------------------------------------ без ключей и выключатели (М§0.1)


def check_off_is_the_sample() -> None:
    """Без ключей и при `enabled: false` (с полями и без них) расчёт прежний бит в бит — на фикстуре формы образца,
    докапитализации и полной форме Т; новые ряды книги без ключа: экономия купона в налоге — ноль, ставка купона в
    совокупном доходе — законная, IIS — доход книги бумаг; подмена одного пути `tax.structure.enabled` и
    `capital.at1_coupon.enabled` считается в обе стороны, и подмена одного ключа другой не трогает."""
    base = grid()
    for off in ({TAXK: {"enabled": False}}, tax_key(False), {CPNK: {"enabled": False}}, cpn_key(False), ALL_OFF):
        other = grid(off)
        R.cells_equal(base, other)
        assert all(a.tv_ddm == b.tv_ddm and a.decisions == b.decisions for a, b in zip(base.cells, other.cells))
    tl = base.ctx.timeline
    for c in base.cells:
        for q in range(1, tl.Q + 1):
            assert c.quarters["tax_coupon"][q] == 0.0, (c.label, q)
            assert c.quarters["tau_cpn"][q] == tau_stat(base, q), (c.label, q)
            assert close(c.quarters["iis"][q], iis_of(base, c, q), rel=1e-12, abs_=1e-12), (c.label, q)
    R.cells_equal(R.grid_of(), R.grid_of(ALL_OFF))
    R.cells_equal(S8.t_grid(), S8.t_grid(ALL_OFF))
    facts = fixture_facts()
    on = S5.book_of({**tax_key(), **cpn_key()})
    off = S5.book_of(ALL_OFF)
    R.cells_equal(grid(cpn_key()), run_grid(on.with_overrides({f"{TAXK}.enabled": False}), facts))
    R.cells_equal(grid(tax_key()), run_grid(on.with_overrides({f"{CPNK}.enabled": False}), facts))
    R.cells_equal(grid({**tax_key(), **cpn_key()}),
                  run_grid(off.with_overrides({f"{TAXK}.enabled": True, f"{CPNK}.enabled": True}), facts))
    assert any(a.quarters["tax"] != b.quarters["tax"] for a, b in zip(base.cells, grid(tax_key()).cells))
    assert any(a.quarters["coupon"] != b.quarters["coupon"] for a, b in zip(base.cells, grid(cpn_key()).cells))


# ------------------------------------------------------------------ налог по правилу (свойства 32–34, 38)


def check_tax_rows(run: GridRun) -> dict[str, int]:
    """Свойства 32 и 34: в каждом квартале каждой клетки налог — `τ_stat × PBT + o × max(PBT, 0) − (τ_stat − τ_b) × ζ ×
    IIS − δ_c × τ_stat × CPN` (IIS — ставка и средний остаток книги бумаг клетки, CPN — ряд купона), разрыв квартала с
    прибылью — правило книги дословно; ряды `iis`, `tax_coupon` (δ_c × τ_stat × CPN), `tau_eff` (τ_stat + o × [PBT > 0])
    и `tau_cpn` (0); ЧП и ЧП акционерам — строками §4.8; совокупный доход и тождество капитала — с купоном целиком;
    инварианты (`bv_identity` с τ_cpn) не срабатывают. → число убыточных кварталов, кварталов с экономией купона и с
    экономией купона сверх базы."""
    tl, book = run.ctx.timeline, run.ctx.book
    tb, zeta, o, ded = rule_of(run)
    nci = float(book.get("pnl.nci_share"))
    seen = {"loss": 0, "coupon": 0, "new": 0}
    for c in run.cells:
        q_ = c.quarters
        for q in range(1, tl.Q + 1):
            ts, pbt, cpn = tau_stat(run, q), q_["pbt"][q], q_["coupon"][q]
            iis = iis_of(run, c, q)
            where = (c.label, tl.period(q))
            assert close(q_["iis"][q], iis, rel=1e-12, abs_=1e-12), where
            saving = ts * cpn if ded else 0.0
            want = ts * pbt + o * max(pbt, 0.0) - (ts - tb) * zeta * iis - saving
            assert close(q_["tax"][q], want, rel=1e-12, abs_=1e-9), (*where, q_["tax"][q], want)
            assert close(q_["tax_coupon"][q], saving, rel=1e-12, abs_=1e-12), where
            assert abs(q_["tau_eff"][q] - (ts + (o if pbt > 0 else 0.0))) < 1e-15, (*where, q_["tau_eff"][q])
            assert q_["tau_cpn"][q] == 0.0, where
            if pbt > 0:
                gap = q_["tax"][q] / pbt - ts
                assert abs(gap - (o - (ts - tb) * zeta * iis / pbt - saving / pbt)) < 1e-12, where
            else:
                seen["loss"] += 1
            ni = pbt - q_["tax"][q] - q_["ot"][q]
            assert close(q_["ni"][q], ni, rel=1e-12, abs_=1e-9), where
            assert close(q_["ni_sh"][q], ni * (1 - nci), rel=1e-12, abs_=1e-9), where
            ci = q_["ni_sh"][q] - cpn + q_["oci"][q] + q_["om"][q]
            assert close(q_["ci"][q], ci, rel=1e-12, abs_=1e-9), where
            rhs = q_["bv"][q - 1] + ci - q_["div"][q] + (q_["rec"][q] or 0.0)
            assert close(q_["bv"][q], rhs, rel=1e-12), where
            seen["coupon"] += saving > 0
            seen["new"] += bool(q_["coupon_new"][q]) and saving > 0
    fired = [f.name for f in check_invariants(run) if f.fired]
    assert not fired, fired
    return seen


def check_tax_rule() -> None:
    """Правило налога (свойства 32–34) на фикстуре формы образца (убыточный квартал режима crisis, купон якоря), с ключом
    доли добавочного капитала (купон сверх базы — в экономии) и долей неконтролирующих, на докапитализации и полной
    форме Т (квартальный календарь, рост по капиталу); при `bond_scale: 0`, постоянном o и `coupon_deductible: false` налог
    — `(τ_stat + o) × PBT` в квартале с прибылью, совокупный доход — ЧП акционерам минус купон целиком; ставка ожидания
    модели (§13) — ряд `tau_eff`; налог непрерывен по PBT в нуле (излом, не скачок)."""
    from model.valuation import TaxRule, rule_tax

    seen = check_tax_rows(grid(tax_key()))
    assert seen["loss"] >= 9 and seen["coupon"] >= 300, seen
    seen = check_tax_rows(grid({**tax_key(), **S8.at1_key(base=0.0), **NCI}))
    assert seen["new"] >= 300, seen
    check_tax_rows(R.grid_of(tax_key()))
    seen = check_tax_rows(S8.t_grid({**tax_key(), **NCI}))
    assert seen["coupon"] >= 300, seen
    flat = grid(tax_key(bond_scale=0.0, other_pp=0.03, coupon_deductible=False))
    seen = check_tax_rows(flat)
    assert seen["coupon"] == 0 and seen["loss"] >= 9, seen
    tl = flat.ctx.timeline
    for c in flat.cells:
        q_ = c.quarters
        for q in range(1, tl.Q + 1):
            if q_["pbt"][q] > 0:
                assert close(q_["tax"][q], (tau_stat(flat, q) + 0.03) * q_["pbt"][q], rel=1e-12, abs_=1e-9)
            assert close(q_["ci"][q], q_["ni_sh"][q] - q_["coupon"][q] + q_["oci"][q] + q_["om"][q], rel=1e-12,
                         abs_=1e-9)
    # ROE-эквивалент передачи (М§4.5): множитель `IEA_0 / BV_0 × (1 − τ_eff,L)`, с ключом τ_eff,L = τ_stat,L + o
    base, run = grid(), grid(tax_key())
    ts_l = float(Trajectory(base.ctx.book.get("tax.statutory")).year_value(tl.last_year))
    ratio = run.ctx.transmission.roe_factor / base.ctx.transmission.roe_factor
    want = (1 - ts_l - RULE["other_pp"]) / (1 - ts_l - float(base.ctx.book.get(GAP)))
    assert abs(ratio - want) < 1e-12, (ratio, want)
    # ставка ожидания модели (М§13): ряд tau_eff под весами слоя — маржинальная ставка
    _, _, o, _ = rule_of(run)
    q = 1
    prob = run.layers["analytical"].prob
    want = sum(prob[c.key] * (tau_stat(run, q) + (o if c.quarters["pbt"][q] > 0 else 0.0)) for c in run.cells)
    got = model_expectation(run.ctx.book, run.ctx.facts, tl.period(q), run=run)["tau_eff"]
    assert abs(got - want) < 1e-15, (got, want)
    # непрерывность в нуле (М§4.8, «Убыток»)
    rule = TaxRule(bond_rate=0.2, bond_scale=1.2, other_pp=0.02, deductible=True)
    for eps in (1e-6, 1e-9):
        up, down = rule_tax(rule, 0.25, eps, 80.0, 10.0)[0], rule_tax(rule, 0.25, -eps, 80.0, 10.0)[0]
        assert abs(up - down) <= 0.27 * 2 * eps + 1e-12, (eps, up, down)
        assert abs(up - (-0.05 * 1.2 * 80.0 - 0.25 * 10.0)) < 1e-5


def check_quiet_differences() -> None:
    """На тихой книге с долей неконтролирующих: до первого квартала купона ряды книги с `coupon_deductible: true` и
    `false` — бит в бит, в квартале купона прибыль до налога та же, а ЧП акционерам больше ровно на `τ_stat × CPN ×
    (1 − nci)`; сдвиг `other_pp` на Δ меняет налог первого квартала ровно на `Δ × max(PBT, 0)` (свойство 38)."""
    plain = grid({**QUIET, **NCI, **tax_key(coupon_deductible=False)})
    ded = grid({**QUIET, **NCI, **tax_key()})
    tl = ded.ctx.timeline
    _, hc = S8.coupon_facts(ded)
    qc = next(q for q in range(1, tl.Q + 1) if tl.h(q) == hc)
    nci = float(ded.ctx.book.get("pnl.nci_share"))
    for a, b in zip(plain.cells, ded.cells):
        for name, row in a.quarters.items():
            assert row[:qc] == b.quarters[name][:qc], (a.label, name)
        assert a.quarters["pbt"][qc] == b.quarters["pbt"][qc], a.label
        diff = b.quarters["ni_sh"][qc] - a.quarters["ni_sh"][qc]
        assert close(diff, tau_stat(ded, qc) * b.quarters["coupon"][qc] * (1 - nci), rel=1e-12, abs_=1e-12), a.label
    delta = 0.01
    shifted = grid({**QUIET, **NCI, **tax_key(other_pp=RULE["other_pp"] + delta)})
    for a, b in zip(ded.cells, shifted.cells):
        pbt = a.quarters["pbt"][1]
        assert pbt == b.quarters["pbt"][1], a.label
        assert close(b.quarters["tax"][1] - a.quarters["tax"][1], delta * max(pbt, 0.0), rel=1e-12, abs_=1e-12)


# ------------------------------------------------------------------ базы дивиденда (свойство 35, М§5.2, §5.7.3)


def _year_decisions(run: GridRun):
    tl = run.ctx.timeline
    for c in run.cells:
        for dec in c.decisions:
            yield c, dec, tl.quarters_of_year(dec.year)


def check_dividend_bases() -> None:
    """База дивиденда года (`deduct_at1_after_tax: true` фикстуры): с ключом налога — `Σ ЧП акционерам − CPN_Y` (купон
    целиком: экономия уже в прибыли), и она равна базе без экономии в прибыли `Σ (NI_sh − TS × (1 − nci)) − CPN_Y × (1 −
    τ_stat)` минус `τ_stat × CPN_Y × nci` (свойство 35); с ключом купона якоря без ключа налога — `Σ ЧП акционерам −
    CPN_Y × (1 − τ_stat)`, где CPN_Y — купон формулы §4.9 (кварталы не позже якоря — ключевая квартала якоря) и купон
    сверх базы; в году якоря отчётные кварталы — факт. Квартальная база (фикстура Т с `deduct_at1_after_tax: true`) —
    среднее окна `ЧП акционерам − купон × (1 − τ_cpn)`, кварталы окна не позже якоря — факт и купон формулы с ключевой
    квартала якоря."""
    tl = grid().ctx.timeline
    for changes in ({**tax_key(), **NCI}, {**tax_key(), **cpn_key(), **S8.at1_key(base=0.0), **NCI}):
        run = grid(changes)
        nci = float(run.ctx.book.get("pnl.nci_share"))
        seen = 0
        for c, dec, qs in _year_decisions(run):
            if min(qs) < 1 or max(qs) > tl.Q:
                continue
            q_ = c.quarters
            ni, cpn = sum(q_["ni_sh"][q] for q in qs), sum(q_["coupon"][q] for q in qs)
            ts = tau_stat(run, qs[0])
            assert close(dec.base, ni - cpn, rel=1e-12, abs_=1e-9), (c.label, dec.year, dec.base, ni - cpn)
            alt = (ni - ts * cpn * (1 - nci)) - cpn * (1 - ts) - ts * cpn * nci
            assert close(dec.base, alt, rel=1e-12, abs_=1e-9), (c.label, dec.year)
            seen += 1
        assert seen >= 100, seen
    for changes in (cpn_key(), {**cpn_key(), **KEY_PATH, **S8.at1_key(base=0.0)}):
        run = grid(changes)
        _, hc = S8.coupon_facts(run)
        seen = anchor_year = 0
        for c, dec, qs in _year_decisions(run):
            if max(qs) > tl.Q:
                continue
            q_ = c.quarters
            ni = sum(q_["ni_sh"][q] if q >= 1 else ni_sh_fact(run, q) for q in qs)
            cpn = sum(anchor_coupon_want(run, c, q) for q in qs if tl.h(q) == hc)
            cpn += sum(q_["coupon_new"][q] for q in qs if q >= 1)
            want = ni - cpn * (1 - tau_stat(run, qs[-1]))
            assert close(dec.base, want, rel=1e-12, abs_=1e-9), (c.label, dec.year, dec.base, want)
            seen += 1
            anchor_year += min(qs) < 1
        assert seen >= 100 and anchor_year >= 36, (seen, anchor_year)
    # квартальный календарь (фикстура Т): база — среднее окна W
    for changes in ({**tax_key(), **NCI}, {**tax_key(), **cpn_key()}, cpn_key()):
        run = S8.t_grid({**changes, "dividends.policy.deduct_at1_after_tax": True})
        ttl, window = run.ctx.timeline, run.ctx.prep.policy.window
        _, hc = S8.coupon_facts(run)
        k1 = keyed(run, TAXK)
        seen = before = 0
        for c in run.cells:
            q_ = c.quarters
            for dec in c.decisions:
                if dec.source == "register" or getattr(dec, "period", None) is None:
                    continue
                idx = ttl.index(dec.period)
                total = 0.0
                for x in range(idx - window + 1, idx + 1):
                    ni = q_["ni_sh"][x] if x >= 1 else ni_sh_fact(run, x)
                    cpn = (anchor_coupon_want(run, c, x) if ttl.h(x) == hc else 0.0)
                    cpn += q_["coupon_new"][x] if x >= 1 else 0.0
                    total += ni - cpn * (1 - (0.0 if k1 else tau_stat(run, x)))
                assert close(dec.base, total / window, rel=1e-12, abs_=1e-9), (c.label, dec.period)
                seen += 1
                before += idx - window + 1 < 1
        assert seen >= 100 and before >= 36, (seen, before)


# ------------------------------------------------------------------ мост и нау-каст выпуска (свойство 36, PAYLOAD)


def check_bridge_and_nowcast() -> None:
    """Выпуск на фикстуре с ключами: мост Н20.0 — тождество `start + Σ долей = end`, строка прибыли — `Σ (NI_sh − CPN ×
    (1 − τ_cpn))` под весами смеси заголовка (τ_cpn — законная ставка, с ключом налога — ноль); купон года нау-каста —
    `CPN^A_Y × (1 − τ_cpn,Y)`, CPN^A_Y — слот или купон формулы §4.9 под смесью заголовка (свойство 42)."""
    from tests.support_core2 import contract
    from tests.support_core_pass3 import _release

    for changes in (tax_key(), {**cpn_key(), **KEY_PATH}, {**tax_key(), **cpn_key(), **KEY_PATH, **NCI}):
        book = S5.book_of(changes)
        rel, data = _release(book)
        assert not contract(data), contract(data)[:5]
        bridge = data["capital"]["bridge"]
        assert close(bridge["start"] + sum(r["pp"] for r in bridge["rows"]), bridge["end"], abs_=1e-9)
        run = rel.run
        tl = run.ctx.timeline
        an, neu = run.layers["analytical"].prob, run.layers["macro_neutral"].prob
        mix = {k: run.lam * an[k] + (1 - run.lam) * neu[k] for k in an}
        k1 = keyed(run, TAXK)
        qe = tl.index(bridge["to"])
        profit = sum(mix[c.key] * (c.quarters["ni_sh"][q] - c.quarters["coupon"][q]
                                   * (1 - (0.0 if k1 else tau_stat(run, q))))
                     for c in run.cells for q in range(1, qe + 1))
        row = next(r for r in bridge["rows"] if r["key"] == "profit")
        assert close(row["amount"], profit, abs_=0.006), (changes, row["amount"], profit)
        year = data["nowcast"]["year"]
        y = int(year["year"])
        _, hc = S8.coupon_facts(run)
        qc = tl.index(f"{y}Q{hc}")
        cpa = sum(mix[c.key] * anchor_coupon_want(run, c, qc) for c in run.cells)
        tau = 0.0 if k1 else float(Trajectory(run.ctx.book.get("tax.statutory")).year_value(y))
        assert close(year["at1_coupon_after_tax"], cpa * (1 - tau), abs_=0.006), (changes, year["at1_coupon_after_tax"])


# ------------------------------------------------------------------ купон якоря (свойства 39, 40, 43)


def check_anchor_coupon_rows(run: GridRun) -> dict[str, int]:
    """Свойство 39: в квартале купона каждой клетки купон якоря (ряд купона минус купон сверх базы) — `Cfix + Cflt ×
    (k̄_q + s_flt)` по пути ключевой своего мира, k̄ — четыре квартала, кончая кварталом купона, кварталы не позже якоря
    — ключевая квартала якоря; в остальных кварталах — ноль. → кварталы купона и кварталы купона года якоря."""
    tl = run.ctx.timeline
    _, hc = S8.coupon_facts(run)
    seen = {"coupon": 0, "anchor_year": 0}
    for c in run.cells:
        q_ = c.quarters
        for q in range(1, tl.Q + 1):
            anchor = q_["coupon"][q] - q_["coupon_new"][q]
            want = anchor_coupon_want(run, c, q) if tl.h(q) == hc else 0.0
            assert close(anchor, want, rel=1e-12, abs_=1e-12), (c.label, tl.period(q), anchor, want)
            if tl.h(q) == hc:
                seen["coupon"] += 1
                seen["anchor_year"] += q <= 3
    return seen


def check_anchor_coupon() -> None:
    """Купон якоря по ставке своего мира: ряды (свойство 39) с ключом доли AT1 и без него, с ключом налога, на пути с
    ключевой якоря, отличной от первого квартала прогноза; `floating: 0` и `fixed` = слоту — бит в бит книги без ключа, с
    ключом налога и без него (свойство 40); подмена пути ключевой мира-опоры меняет купон якоря только у клеток этого
    мира (свойство 43)."""
    for changes in (cpn_key(), {**cpn_key(), **S8.at1_key(base=0.0)}, {**cpn_key(), **tax_key()},
                    {**cpn_key(), **KEY_PATH}):
        seen = check_anchor_coupon_rows(grid(changes))
        assert seen["coupon"] >= 360 and seen["anchor_year"] >= 36, seen
    run = grid({**cpn_key(), **KEY_PATH})
    n = next(c for c in run.cells if c.world == "N")
    assert run.ctx.worlds["N"].key[0] != run.ctx.worlds["N"].key[1]
    assert kbar(run, n, 2) != sum(run.ctx.worlds["N"].key[max(2 - j, 1)] for j in range(4)) / 4
    slot, _ = S8.coupon_facts(grid())
    flat = cpn_key(fixed=slot, floating=0.0, spread=0.0)
    R.cells_equal(grid(), grid(flat))
    R.cells_equal(grid(tax_key()), grid({**tax_key(), **flat}))
    R.cells_equal(grid(S8.at1_key()), grid({**S8.at1_key(), **flat}))
    base = grid(cpn_key())
    ref = base.ctx.prep.reference_world
    path = {k: v + 0.01 for k, v in fixture_dict()["worlds"][ref]["key_rate"].items()}
    moved = grid({**cpn_key(), f"worlds.{ref}.key_rate": path})
    _, hc = S8.coupon_facts(base)
    tl = base.ctx.timeline
    changed = 0
    for a, b in zip(base.cells, moved.cells):
        for q in range(1, tl.Q + 1):
            if tl.h(q) != hc:
                continue
            x = a.quarters["coupon"][q] - a.quarters["coupon_new"][q]
            y = b.quarters["coupon"][q] - b.quarters["coupon_new"][q]
            if a.world == ref:
                changed += x != y
            else:
                assert x == y, (a.label, q)
    assert changed >= 100, changed


# ------------------------------------------------------------------ терминал (свойства 37, 41)


def check_terminal_rows(run: GridRun) -> dict[str, int]:
    """Свойство 37 (λ_F = 1): совокупный доход года T + 1 = ROE_T × BV* — строки §7 по рядам конца сетки: Y_X и A_X по
    избытку, запасу и добору опта конца сетки; `IIS_T+1 = IIS_L (1 + g_T) − sec × y_sec × A_X`; `PBT^x = (PBT_L + SP_L)(1 +
    g_T) − SP_T+1 − Y_X`; налог T + 1 правилом с купоном T + 1 (якоря — слот или `Cfix + Cflt × (key_W,Q + s_flt)`, сверх
    базы — `(key_Q + s_α) × ΔAT1_Q`); CI_T+1 — с купоном целиком. Без ключа налога — строка образца с τ_eff = τ_stat +
    разрыв и купон × (1 − τ_stat). → клетки с X_T > 0 и X_T ≤ 0."""
    tl, book = run.ctx.timeline, run.ctx.book
    Q, L = tl.Q, tl.year(tl.Q)
    nci = float(book.get("pnl.nci_share"))
    m = float(book.get("volumes.liquid_min_share"))
    sec = float(book.get("volumes.securities_share_of_liquid"))
    k1, k2 = keyed(run, TAXK), keyed(run, CPNK)
    a1, tp = keyed(run, S8.A1), keyed(run, S8.TP)
    slot, _ = S8.coupon_facts(run)
    seen = {"excess": 0, "short": 0}
    for c in run.cells:
        q_ = c.quarters
        qs = [q for q in range(1, Q + 1) if tl.year(q) == L]
        pbt_l = sum(q_["pbt"][q] for q in qs)
        sp_l = sum(q_["t2_premium"][q] for q in qs) if tp else 0.0
        sp_t1 = float(book.get(f"{S8.TP}.spread")) * (q_["t2"][Q] - S8.base_t2(run)) if tp else 0.0
        key_q = run.ctx.worlds[c.world].key[Q]
        new = (key_q + float(book.get(f"{S8.A1}.spread"))) * (q_["at1"][Q] - S8.base_alpha(run)) if a1 else 0.0
        if k2:
            fixed, floating, spread = coupon_rule(run)
            anchor = fixed + floating * (key_q + spread)
        else:
            anchor = slot
        cpn = anchor + new
        y_sec, y_liq, c_wh = (c.books[b]["rate"][Q] for b in (SEC, LIQ, WH))
        y_bal = sec * y_sec + (1 - sec) * y_liq
        x, wt, g = c.x_t, q_["wholesale_extra"][Q], c.g_t
        if x > 0:
            a_x = min(x, c.la_headroom / (1 - m))
            y_x = y_bal * a_x + c_wh * (x - a_x)
            seen["excess"] += 1
        else:
            a_x = -max(0.0, -x - wt)
            y_x = -(c_wh * min(-x, wt) + y_bal * max(0.0, -x - wt))
            seen["short"] += 1
        assert close(c.y_x, y_x, rel=1e-12, abs_=1e-9), (c.label, c.y_x, y_x)
        pbt_x = (pbt_l + sp_l) * (1 + g) - sp_t1 - y_x
        ts = tau_stat(run, Q)
        if k1:
            tb, zeta, o, ded = rule_of(run)
            iis_t1 = sum(iis_of(run, c, q) for q in qs) * (1 + g) - sec * y_sec * a_x
            tax = ts * pbt_x + o * max(pbt_x, 0.0) - (ts - tb) * zeta * iis_t1 - (ts * cpn if ded else 0.0)
            ci = (pbt_x - tax) * (1 - nci) - cpn
        else:
            ci = pbt_x * (1 - ts - float(book.get(GAP))) * (1 - nci) - cpn * (1 - ts)
        assert close(c.roe_t_raw * c.bv_star, ci, rel=1e-11, abs_=1e-8), (c.label, c.roe_t_raw * c.bv_star, ci)
    return seen


def check_terminal() -> None:
    """Терминал с ключами (свойства 37, 41): строки NI_T+1 и CI_T+1 при X_T > 0 и X_T ≤ 0 — с ключом налога, с ключами
    восьмого прохода и долей неконтролирующих; купон года T + 1 по ставке квартала Q на пути мира, у которого ключевая в
    последнем году сетки меняется (с ключом налога и без него); доход блока постоянных частей — ставками после налога
    y^τ_m в обеих ветвях (смесь и добор опта); DDM = RI в каждой клетке при λ_F = 0 и 1 со всеми ключами."""
    seen = check_terminal_rows(grid(tax_key()))
    assert seen["excess"] >= 20 and seen["short"] >= 3, seen
    check_terminal_rows(grid({**tax_key(), **cpn_key(), **S8.at1_key(), **S8.t2p_key(), S8.T2: S8.TRAJ_P, **NCI}))
    for changes in ({**cpn_key(), **KEY_PATH}, {**cpn_key(), **KEY_PATH, **tax_key()}):
        run = grid(changes)
        check_terminal_rows(run)
        key, Q = run.ctx.worlds["N"].key, run.ctx.timeline.Q
        assert key[Q] != sum(key[Q - j] for j in range(4)) / 4
    branches = {"mix": 0, "wholesale": 0}
    for extra in ({}, LIQ_TIGHT):
        run = grid({**S5.PARTS, S5.LAM: 0.0, **tax_key(), **NCI, **extra})
        tb, zeta, o, _ = rule_of(run)
        book, Q = run.ctx.book, run.ctx.timeline.Q
        nci = float(book.get("pnl.nci_share"))
        sec = float(book.get("volumes.securities_share_of_liquid"))
        ts = tau_stat(run, Q)
        keep = 1 - ts - o
        for c in run.cells:
            blk = c.terminal_fixed
            y_sec, y_liq, c_wh = (c.books[b]["rate"][Q] for b in (SEC, LIQ, WH))
            if c.quarters["wholesale_extra"][Q] > 0:
                y_tau = c_wh * keep
                branches["wholesale"] += 1
            else:
                y_tau = sec * y_sec * (keep + (ts - tb) * zeta) + (1 - sec) * y_liq * keep
                branches["mix"] += 1
            assert close(blk["i_f"], -y_tau * blk["d_f"] * (1 - nci), rel=1e-12, abs_=1e-12), (c.label, blk["i_f"])
    assert branches["mix"] >= 10 and branches["wholesale"] >= 10, branches
    for lam in (0.0, 1.0):
        run = grid({**S5.PARTS, S5.LAM: lam, S8.T2: S8.TRAJ_P, S8.OM: S8.OM_TRAJ, **S8.at1_key(), **S8.t2p_key(),
                    **S8.OM_KEY, **tax_key(), **cpn_key(), **NCI})
        for c in run.cells:
            assert close(c.v_ddm, c.v_ri, rel=1e-11, abs_=1e-7), (c.label, lam)


# ------------------------------------------------------------------ схема (прил. A № 34–35)


def _validated(changes: Mapping[str, Any]) -> str | None:
    """Отказ схемы книги фикстуры с подменами (None — годна)."""
    data = S5.book_dict(changes)
    try:
        validate(data)
    except BookError as exc:
        return str(exc)
    return None


GAP_AXIS = {"name": "Налог: разрыв", "kind": "value", "paths": [GAP], "low": -0.03, "high": 0.0,
            "dist": "triangular"}


def _with_axis(changes: Mapping[str, Any], axis: Mapping[str, Any], group: str = "axes") -> dict:
    axes = copy.deepcopy(fixture_dict()["valuation"]["uncertainty"].get(group) or [])
    return {**changes, f"valuation.uncertainty.{group}": axes + [dict(axis)]}


def check_schema() -> None:
    """Ограничения № 34–35 (прил. A, пример M.6): узлы годны без ключей; при `enabled: true` нет поля или `null` в поле —
    отказ; отрицательные `bond_scale`, `fixed`, `floating` — отказ при любом `enabled`; не числа, `coupon_deductible` не
    булево, `enabled` не булево, нет `enabled`, лишнее поле — отказ; `enabled: false` без полей — годен; с включённым
    ключом налога `tax.effective_gap` может быть `null` (без ключа — отказ), ось полосы (и вне полосы) на нём — отказ,
    подмена справочного варианта на нём — отказ, кроме варианта с `tax.structure.enabled: false`; ось на
    `tax.structure.other_pp` — годна; ключи — в закрытом перечне схемы."""
    assert {f"{TAXK}.{k}" for k in ("enabled", "bond_rate", "bond_scale", "other_pp", "coupon_deductible")} <= set(KEYS)
    assert {f"{CPNK}.{k}" for k in ("enabled", "fixed", "floating", "spread")} <= set(KEYS)
    on = tax_key()
    good = (on, tax_key(False), {TAXK: {"enabled": False}}, {TAXK: {"enabled": False, "bond_scale": None}},
            tax_key(bond_scale=0.0, other_pp=-0.01, coupon_deductible=False), {**on, GAP: None},
            cpn_key(), cpn_key(False), {CPNK: {"enabled": False}}, cpn_key(fixed=0.0, floating=0.0, spread=-0.01),
            _with_axis(on, {**GAP_AXIS, "paths": [f"{TAXK}.other_pp"], "low": 0.016, "high": 0.022}),
            _with_axis(tax_key(False), GAP_AXIS),
            {**on, "valuation.reference_variants": [
                {"id": "one_gap", "title": "Разрыв одним числом", "overrides": {f"{TAXK}.enabled": False, GAP: -0.03}},
                {"id": "no_ded", "title": "Купон не вычитается", "overrides": {f"{TAXK}.coupon_deductible": False}}]})
    for case in good:
        assert _validated(case) is None, (case, _validated(case))
    bad = (("bond_scale", {TAXK: {"enabled": True, "bond_rate": 0.2, "other_pp": 0.02, "coupon_deductible": True}}),
           ("bond_rate", {TAXK: {"enabled": True, "bond_scale": 1.0, "other_pp": 0.02, "coupon_deductible": True}}),
           ("other_pp", tax_key(other_pp=None)),
           ("coupon_deductible", {TAXK: {"enabled": True, "bond_rate": 0.2, "bond_scale": 1.0, "other_pp": 0.02}}),
           ("bond_scale", tax_key(bond_scale=-1.0)), ("bond_scale", tax_key(False, bond_scale=-0.5)),
           ("coupon_deductible", tax_key(coupon_deductible="yes")), ("bond_rate", tax_key(bond_rate="20%")),
           (TAXK, {TAXK: {"enabled": "true"}}), (TAXK, {TAXK: {"bond_rate": 0.2}}),
           ("rate", {TAXK: {"enabled": False, "rate": 0.2}}),
           (GAP, {GAP: None}),
           (GAP, _with_axis(on, GAP_AXIS)), (GAP, _with_axis(on, GAP_AXIS, "off_band_axes")),
           (GAP, {**on, "valuation.reference_variants": [
               {"id": "gap", "title": "Разрыв ниже", "overrides": {GAP: -0.03}}]}),
           ("floating", {CPNK: {"enabled": True, "fixed": 3.0, "spread": 0.05}}),
           ("fixed", {CPNK: {"enabled": True, "floating": 40.0, "spread": 0.05}}),
           ("spread", {CPNK: {"enabled": True, "fixed": 3.0, "floating": 40.0}}),
           ("floating", cpn_key(floating=-1.0)), ("fixed", cpn_key(False, fixed=-1.0)),
           ("spread", cpn_key(spread=None)), ("spread", cpn_key(spread="5%")),
           (CPNK, {CPNK: {"enabled": 1, **COUPON}}), ("share", {CPNK: {"enabled": False, "share": 0.5}}))
    for word, case in bad:
        err = _validated(case)
        assert err is not None and word in err, (case, err)


# ------------------------------------------------------------------ пример приложения M


def check_example_m() -> None:
    """Пример приложения M (M.1–M.5) до 1e-9 (М§17): налог квартала — функцией ядра `model.valuation.rule_tax` (квартал
    убытка, квартал купона, сравнение без ключа), купон якоря — `model.cell.anchor_coupon` и
    `terminal_anchor_coupon` (квартал купона, год якоря, терминал), база дивиденда и тождество свойства 35 — формулами
    текста, терминал (избыток, недостаток, убыток года L, I_F в обеих ветвях) — `model.valuation.terminal` и
    `fixed_parts`, сверка якоря на фактах ВТБ — формулами текста; схема — `check_schema`."""
    from model.cell import AnchorCoupon, anchor_coupon, terminal_anchor_coupon
    from model.valuation import TaxRule, fixed_parts, rule_tax, terminal

    # M.2: купон якоря
    m2 = EXAMPLE["M2"]
    i2 = m2["inputs"]
    rule_c = AnchorCoupon(fixed=i2["fixed"], floating=i2["floating"], spread=i2["spread"])
    key = [i2["key"][str(q)] for q in range(5)]
    assert abs(anchor_coupon(rule_c, key, 4) - m2["coupon_anchor_q4"]) < TOL
    assert abs(sum(key[1:5]) / 4 - m2["kbar_q4"]) < TOL
    new = (key[4] + i2["at1_spread"]) * i2["at1_over_base_q3"] * i2["days"]["4"] / 365
    assert abs(new - m2["coupon_new_q4"]) < TOL and abs(m2["coupon_anchor_q4"] + new - m2["coupon_q4"]) < TOL
    ay = i2["anchor_year_case"]
    key_a = [ay["key"][str(q)] for q in range(3)]
    assert abs(anchor_coupon(rule_c, key_a, ay["coupon_q"]) - m2["anchor_year_coupon"]) < TOL
    t1 = terminal_anchor_coupon(rule_c, key[4])
    assert abs(t1 - m2["coupon_anchor_T1"]) < TOL
    assert abs(t1 + (key[4] + i2["at1_spread"]) * i2["at1_over_base_Q"] - m2["coupon_T1"]) < TOL
    # M.1: налог квартала
    m1 = EXAMPLE["M1"]
    i1 = m1["inputs"]
    rule = TaxRule(bond_rate=i1["bond_rate"], bond_scale=i1["bond_scale"], other_pp=i1["other_pp"],
                   deductible=i1["coupon_deductible"])
    ts, nci = i1["tau_stat"], i1["nci_share"]
    year = {"tax": 0.0, "ni_sh": 0.0, "ci": 0.0}
    for q in ("1", "2", "3", "4"):
        want = m1["quarters"][q]
        pbt, cpn = i1["pbt"][q], i1["coupon"][q]
        tax, saving, tau_e = rule_tax(rule, ts, pbt, i1["iis"][q], cpn)
        ni_sh = (pbt - tax) * (1 - nci)
        for name, got in (("tax", tax), ("tax_coupon", saving), ("tau_eff", tau_e), ("ni", pbt - tax),
                          ("ni_sh", ni_sh), ("ci", ni_sh - cpn)):
            assert abs(got - want[name]) < TOL, (q, name, got, want[name])
        off = (ts + i1["effective_gap_off"]) * pbt
        assert abs(off - want["tax_off"]) < TOL
        assert abs((pbt - off) * (1 - nci) - cpn * (1 - ts) - want["ci_off"]) < TOL
        if pbt > 0:
            assert abs(tax / pbt - ts - want["gap"]) < TOL
        year["tax"] += tax
        year["ni_sh"] += ni_sh
        year["ci"] += ni_sh - cpn
    for name in ("tax", "ni_sh", "ci"):
        assert abs(year[name] - m1["year"][name]) < TOL, name
    # M.3: база дивиденда и мост
    m3 = EXAMPLE["M3"]
    cpn_y = m3["coupon_year"]
    assert abs(year["ni_sh"] - cpn_y - m3["base_k1"]) < TOL
    alt = (year["ni_sh"] - ts * cpn_y * (1 - nci)) - cpn_y * (1 - ts) - ts * cpn_y * nci
    assert abs(alt - m3["base_k1_identity"]) < TOL
    assert abs(m1["year"]["ni_sh_off"] - cpn_y * (1 - ts) - m3["base_off"]) < TOL
    assert abs(m3["bridge_profit_k1"] - m3["base_k1"]) < TOL and abs(m3["bridge_profit_off"] - m3["base_off"]) < TOL
    # M.4: терминал
    m4 = EXAMPLE["M4"]
    i4 = m4["inputs"]
    y_bal = i4["sec"] * i4["y_sec"] + (1 - i4["sec"]) * i4["y_liq"]
    for case in ("excess", "shortfall", "loss"):
        w = m4[case]
        args = dict(n20=0.1 + w["x_t"] / 1000.0, req20=0.1, n11_star=1.0, req11=0.0, rwa=1000.0, bv_q=1000.0,
                    pbt_last_year=w["pbt_l"], y_balancing=y_bal, c_wholesale=i4["c_wholesale"], headroom=w["h_star"],
                    nci_share=nci, coupon_annual=i4["coupon_T1"], tau_stat=ts, lt_inflation=i4["g_t"],
                    real_growth=0.0, fade=1.0, multiple=1.0, k_t=0.15, min_share=0.0, wholesale_extra=w["wt"])
        got = terminal(**args, tau_eff=float("nan"), tax_rule=rule, iis_l=i4["iis_l"], y_securities=i4["y_sec"],
                       y_liquidity=i4["y_liq"], sec_share=i4["sec"])
        assert abs(got.x_t - w["x_t"]) < TOL and abs(got.y_x - w["y_x"]) < TOL, (case, got.x_t, got.y_x)
        assert abs(got.ni_t1 - w["ni_t1"]) < TOL and abs(got.ci_t1 - w["ci_t1"]) < TOL, (case, got.ni_t1, got.ci_t1)
        off = terminal(**args, tau_eff=ts + i1["effective_gap_off"])
        assert abs(off.ni_t1 - w["ni_t1_off"]) < TOL and abs(off.ci_t1 - w["ci_t1_off"]) < TOL, case
        a_x = min(w["x_t"], w["h_star"]) if w["x_t"] > 0 else -max(0.0, -w["x_t"] - w["wt"])
        assert abs(a_x - w["a_x"]) < TOL
        assert abs(w["pbt_l"] * (1 + i4["g_t"]) - w["y_x"] - w["pbt_x"]) < TOL
        assert abs(i4["iis_l"] * (1 + i4["g_t"]) - i4["sec"] * i4["y_sec"] * a_x - w["iis_t1"]) < TOL
        tax = rule_tax(rule, ts, w["pbt_x"], w["iis_t1"], i4["coupon_T1"])[0]
        assert abs(tax - w["tax_t1"]) < TOL
    block = {"f_a": i4["d_f"], "r_f": 0.0, "c20": 0.0, "c11": 0.0, "kappa20": 0.0, "kappa11": 0.0}
    for name, wt in (("i_f_balancing", 0.0), ("i_f_wholesale", 1.0)):
        want = m4[name]
        common = dict(n20=0.2, req20=0.1, n11_star=0.2, req11=0.1, y_balancing=y_bal, c_wholesale=i4["c_wholesale"],
                      wholesale_extra=wt, nci_share=nci)
        got = fixed_parts(block, **common, tau_eff=float("nan"), tax_rule=rule, tau_stat=ts, y_securities=i4["y_sec"],
                          y_liquidity=i4["y_liq"], sec_share=i4["sec"])
        assert abs(got["d_f"] - i4["d_f"]) < TOL
        assert abs(got["i_f"] - want["i_f"]) < TOL, (name, got["i_f"])
        assert abs(-got["i_f"] / i4["d_f"] / (1 - nci) - want["y_after_tax"]) < TOL
        off = fixed_parts(block, **common, tau_eff=ts + i1["effective_gap_off"])
        assert abs(off["i_f"] - want["i_f_off"]) < TOL, name
    # M.5: сверка якоря на фактах ВТБ
    m5 = EXAMPLE["M5"]
    i5 = m5["inputs"]
    q2, h1 = i5["q2"], i5["h1"]
    tsv, tbv, ov = i5["tau_stat"], i5["bond_rate"], i5["other_pp"]
    zeta = q2["ifrs_lines"] / q2["iis_core"]
    assert abs(zeta - m5["zeta"]) < TOL
    assert abs(q2["tax"] / q2["pbt"] - tsv - m5["q2_gap_fact"]) < TOL
    for z, name in ((zeta, "q2_gap_rule"), (1.0, "q2_gap_rule_zeta1")):
        got = -(tsv - tbv) * z * q2["iis_core"] / q2["pbt"] - tsv * q2["coupon"] / q2["pbt"] + ov
        assert abs(got - m5[name]) < TOL, name
    bond = -(tsv - tbv) * h1["bond_income"] / h1["pbt"]
    cpn = -tsv * h1["coupon"] / h1["pbt"]
    assert abs(bond - m5["h1_bond_pp"]) < TOL and abs(cpn - m5["h1_coupon_pp"]) < TOL
    assert abs(bond + cpn + ov - m5["h1_gap_rule"]) < TOL
    assert abs(h1["tax"] / h1["pbt"] - tsv - m5["h1_gap_fact"]) < TOL
    assert abs(m5["h1_gap_fact"] - h1["dta"] - m5["h1_gap_fact_structural"]) < TOL
    assert abs(ov - 0.05 * (h1["bond_income"] - 2 * q2["iis_core"]) / h1["pbt"] - m5["o_core_zeta1"]) < TOL
    # M.6: схема
    for case in EXAMPLE["M6"]["valid"]:
        assert _validated(case) is None, case
    for case in EXAMPLE["M6"]["invalid"]:
        case = dict(case)
        axis = case.pop("axis_on", None)
        if axis is not None:
            case = _with_axis(case, {**GAP_AXIS, "paths": [axis]})
        assert _validated(case) is not None, case
    check_schema()
