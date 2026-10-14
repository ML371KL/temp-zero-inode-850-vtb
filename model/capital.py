"""RWA, нормативы из BV с аддитивными вычетами, требования и полы (М§3.3, §4.11–§4.12).

K20 = BV + DPreg − (1 − f)·R − Ded20 + AT1 + T2;  K11 = BV + DPreg − (1 − f)·R − max(E, 0) − Ded11;
Ded_q = Ded_0 × RWA_q / RWA_0 (вычеты растут с бизнесом; дивиденд и прибыль входят
один к одному). У книги с ключами доли вычета якоря, постоянной в рублях (`capital.n20.deductions_fixed_share`,
`capital.n11.deductions_fixed_share`; η_20, η_11), вычет каждого норматива — растущая часть и постоянная:
Ded_j,q = (1 − η_j) × Ded_j,0 × RWA_q / RWA_0 + η_j × Ded_j,0 (`deduction_parts`, `ratios`); путь вычета сценария
`deduction_pp` доли не читает; без ключей — прежняя строка (М§4.11). Вычет сценария в рублях
(`capital.reg_scenarios.<s>.deduction_rub.{n20_0, n1_1}`, Drub_j,s,q) прибавляется к вычету квартала своего
норматива без множителя RWA, до деления на RWA; без ключа слагаемого нет — прежняя строка. Из базового капитала
исключается только неаудированная ПРИБЫЛЬ: убыток неаудированного периода уменьшает его сразу, вместе с BV. Н20.1
группы — через прокси Н1.1 банка. Пол = минимум + надбавки сценария года; требование Н20.0 = max(порог
политики; пол + буфер). Постоянные прочие активы (`volumes.other_assets_fixed`) входят в RWA со своей
плотностью `capital.rwa.density.other_assets_fixed`; приращение постоянной части к якорю по её пути
(`volumes.other_assets_fixed_change`, ΔOA_q) — с весом `capital.rwa.density.other_assets_fixed_change` (ω_Δ; без
ключа — плотность постоянной части); множитель RWA режима (`regimes.<r>.rwa_density_mult`, роспуск
макронадбавок) стоит на всех RWA клетки (М§4.3, §4.11).

Докапитализация (`capital.recapitalization`, М§4.14): правило книги (`recap_rule` — квартал решения, окно и порог; дисконт
размещения — параметр оценки, `price_discount`) и недостаток капитала к требованию в точках окна решения
(`shortfall`): отчётные нормативы против требований М§4.12, в последней точке окна — без дивидендов,
объявленных, но ещё не вычтенных из регуляторного капитала. Объекта нет или он выключен — правила нет.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, NamedTuple, Sequence

from model.book import SECURITIES, LIQUIDITY, AnchorFacts, BookRoles
from model.book_schema import BookError, window_floor  # noqa: F401 — нижняя граница окна — рядом с правилом
from model.paths import Trajectory
from model.timeline import QUARTER_YEARS, Timeline, parse_period

if TYPE_CHECKING:
    from model.book import Book

OTHER_ASSETS = "other_assets"
OTHER_ASSETS_FIXED = "other_assets_fixed"
OTHER_ASSETS_FIXED_CHANGE = "other_assets_fixed_change"     # ω_Δ — плотность приращения постоянной части (М§4.11)
FIXED_CHANGE = "volumes.other_assets_fixed_change"          # путь постоянной части прочих активов (М§4.3)
DEDUCTION_RUB = "deduction_rub"                             # вычет сценария в рублях (М§4.11)


@dataclass(frozen=True)
class ScenarioPath:
    """Полы, требования и вычеты сценария s по кварталам q = 0…Q."""
    scenario: str
    floor20: tuple[float, ...]
    floor11: tuple[float, ...]
    req20: tuple[float, ...]
    req11: tuple[float, ...]
    ded_pp20: tuple[float, ...]
    ded_pp11: tuple[float, ...]
    conservation: tuple[float, ...]
    sifi: tuple[float, ...]
    ccyb: tuple[float, ...]
    # вычет сценария в рублях Drub_j,s,q, млрд ₽ (М§4.11): по кварталам q = 0…Q; ключа нет — None (слагаемого нет)
    rub20: tuple[float, ...] | None = None
    rub11: tuple[float, ...] | None = None

    def req20_at(self, q: int, threshold: float, buffer20: float) -> float:
        """Требование Н20.0 при пороге ступени политики (М§5.3 п. 2)."""
        return max(threshold, self.floor20[q] + buffer20)


def _series(traj, timeline: Timeline) -> tuple[float, ...]:
    t = Trajectory(traj)
    return tuple(t.value(*parse_period(timeline.period(q))) for q in range(timeline.Q + 1))


def scenario_path(book: "Book", scenario: str, timeline: Timeline) -> ScenarioPath:
    base = f"capital.reg_scenarios.{scenario}"
    cons = _series(book.get(f"{base}.conservation"), timeline)
    sifi = _series(book.get(f"{base}.sifi"), timeline)
    ccyb = _series(book.get(f"{base}.ccyb"), timeline)
    d20 = _series(book.get(f"{base}.deduction_pp.n20_0"), timeline)
    d11 = _series(book.get(f"{base}.deduction_pp.n1_1"), timeline)
    rub = book.opt(f"{base}.{DEDUCTION_RUB}")       # вычет в рублях (М§4.11): у всех сценариев или ни у одного
    r20 = None if rub is None else _series(rub["n20_0"], timeline)
    r11 = None if rub is None else _series(rub["n1_1"], timeline)
    m20 = float(book.get("capital.minimum.n20_0"))
    m11 = float(book.get("capital.minimum.n1_1"))
    b20 = float(book.get("capital.mgmt_buffer.n20_0"))
    b11 = float(book.get("capital.mgmt_buffer.n1_1"))
    thr = float(book.get("dividends.policy.threshold"))
    add = [cons[q] + sifi[q] + ccyb[q] for q in range(timeline.Q + 1)]
    floor20 = tuple(m20 + a for a in add)
    floor11 = tuple(m11 + a for a in add)
    return ScenarioPath(scenario=scenario, floor20=floor20, floor11=floor11,
                        req20=tuple(max(thr, f + b20) for f in floor20),
                        req11=tuple(f + b11 for f in floor11),
                        ded_pp20=d20, ded_pp11=d11, conservation=cons, sifi=sifi, ccyb=ccyb, rub20=r20, rub11=r11)


def density_index(book: "Book", timeline: Timeline) -> tuple[float, ...]:
    """Dn_q: рост плотности RWA до `density_drift_until` включительно (М§4.11)."""
    rate = float(book.get("capital.rwa.density_drift_rate"))
    until = int(book.get("capital.rwa.density_drift_until"))
    out = [1.0]
    for q in range(1, timeline.Q + 1):
        out.append(out[-1] * ((1 + rate) ** QUARTER_YEARS if timeline.year(q) <= until else 1.0))
    return tuple(out)


def fx_index(book: "Book", cpi: Sequence[float], Q: int) -> tuple[float, ...]:
    """X_q валютной части RWA по относительному ППС; выключено — X ≡ 1."""
    if not book.get("capital.rwa.fx.enabled"):
        return tuple([1.0] * (Q + 1))
    share = float(book.get("capital.rwa.fx.share"))
    pi = float(book.get("capital.rwa.fx.foreign_inflation"))
    out, cum = [1.0], 1.0
    for q in range(1, Q + 1):
        cum *= ((1 + cpi[q]) / (1 + pi)) ** QUARTER_YEARS
        out.append(1 - share + share * cum)
    return tuple(out)


@dataclass(frozen=True)
class RwaWeights:
    loans: Mapping[str, float]             # кредитная книга → плотность
    securities: float
    liquidity: float
    other_assets: float
    oa_fixed: float = 0.0                  # OA_fixed — постоянная часть прочих активов, млрд ₽ (М§4.3)
    other_assets_fixed: float = 0.0        # её плотность ω_oaf; читается только при OA_fixed ≠ 0 (или как
    #                                        умолчание ω_Δ у пути постоянной части)
    oa_change: float = 0.0                 # ω_Δ — плотность приращения постоянной части по её пути (М§4.3, §4.11);
    #                                        читается только при пути (`delta` в `rwa`)

    def rwa(self, loans: Mapping[str, float], securities: float, liquidity: float,
            other_assets: float, dn: float, x: float, delta: float | None = None) -> float:
        """База RWA × дрейф плотности × валютный индекс; `other_assets` — прочие активы целиком. `loans` —
        остатки по книгам: читаются только кредитные (прочие ключи словаря не мешают). `delta` — приращение
        постоянной части к якорю ΔOA_q у книги с путём постоянной части (М§4.3): растущая часть — прочие активы
        без постоянной части квартала `OA_fixed + ΔOA_q`, приращение — с весом ω_Δ (М§4.11); без пути (None) —
        прежняя строка."""
        base = sum([self.loans[b] * loans[b] for b in self.loans])
        base += self.securities * securities + self.liquidity * liquidity
        if delta is not None:
            base += (self.other_assets * (other_assets - self.oa_fixed - delta)
                     + self.other_assets_fixed * self.oa_fixed + self.oa_change * delta)
        elif self.oa_fixed:
            base += self.other_assets * (other_assets - self.oa_fixed) + self.other_assets_fixed * self.oa_fixed
        else:
            base += self.other_assets * other_assets
        return base * dn * x


def rwa_weights(book: "Book", roles: BookRoles) -> RwaWeights:
    """Плотности RWA книги (М§4.11). Плотность постоянных прочих активов ω_oaf читается при OA_fixed ≠ 0, а у
    книги с путём постоянной части — и как умолчание плотности приращения ω_Δ; ω_Δ — только при пути."""
    dens = book.get("capital.rwa.density")
    oa_fixed = float(book.opt("volumes.other_assets_fixed", 0.0))
    path = book.opt(FIXED_CHANGE) is not None
    own = dens.get(OTHER_ASSETS_FIXED_CHANGE) if path else None
    if (oa_fixed or (path and own is None)) and OTHER_ASSETS_FIXED not in dens:
        raise BookError("capital.rwa.density.other_assets_fixed: нет плотности постоянных прочих активов (М§4.11)")
    w_fixed = float(dens[OTHER_ASSETS_FIXED]) if oa_fixed or (path and OTHER_ASSETS_FIXED in dens) else 0.0
    return RwaWeights(loans={b: float(dens[b]) for b in roles.loans},
                      securities=float(dens[SECURITIES]), liquidity=float(dens[LIQUIDITY]),
                      other_assets=float(dens[OTHER_ASSETS]), oa_fixed=oa_fixed,
                      other_assets_fixed=w_fixed,
                      oa_change=(w_fixed if own is None else float(own)) if path else 0.0)


def fixed_change(book: "Book", timeline: Timeline) -> tuple[float, ...] | None:
    """ΔOA_q — приращение постоянной части прочих активов к якорю по кварталам q = 0…Q (`volumes.other_assets_fixed_change`,
    М§4.3): траектория §0.4 в млрд ₽, приращение — от значения квартала якоря, `v(q) − v(0)`: остаток записи в
    пределах порога якорного условия на путь не влияет, а при нуле в квартале якоря разность — само значение бит в
    бит. Якорное условие и знак суммы держит схема книги (`model.book_schema`, прил. A № 24) — у книги и на концах
    осей. Ключа нет — None."""
    traj = book.opt(FIXED_CHANGE)
    if traj is None:
        return None
    v = _series(traj, timeline)
    return tuple(x - v[0] for x in v)


def regime_rwa_mult(book: "Book", regime: str, timeline: Timeline) -> tuple[float, ...] | None:
    """M_r,q — множитель RWA клеток режима по кварталам q = 0…Q (М§4.11); ключа у режима нет — None
    (множителя нет). В квартале якоря множитель не применяется: RWA_0 — факт."""
    traj = book.get(f"regimes.{regime}").get("rwa_density_mult")
    if traj is None:
        return None
    series = _series(traj, timeline)
    if min(series) <= 0:
        raise BookError(f"regimes.{regime}.rwa_density_mult: множитель RWA — больше нуля (М§4.11)")
    return series


def rwa_anchor(weights: RwaWeights, af: AnchorFacts) -> float:
    """RWA_0 модели: плотности × книги якоря (калиброваны к RWA по Базелю)."""
    return weights.rwa({b: af.balances[b] for b in weights.loans}, af.balances[SECURITIES],
                       af.balances[LIQUIDITY], af.other_assets, 1.0, 1.0)


FIXED_SHARE20 = "capital.n20.deductions_fixed_share"       # η_20 — доля вычета якоря Н20.0, постоянная в рублях
FIXED_SHARE11 = "capital.n11.deductions_fixed_share"       # η_11 — то же у Н20.1 (слот n11)


class DeductionParts(NamedTuple):
    """Части вычета якоря у книги с ключами доли (М§4.11), млрд ₽: растущая с RWA `Dgrow_j = (1 − η_j) × Ded_j,0`
    и постоянная в рублях `Dfix_j = η_j × Ded_j,0` — у каждого норматива от своего вычета якоря и своей доли."""
    grow20: float
    fix20: float
    grow11: float
    fix11: float


def fixed_shares(book: "Book") -> tuple[float, float] | None:
    """η_20 и η_11 — доли вычета якоря, постоянные в рублях (М§4.11). Ключей нет — None: вычет растёт с RWA
    целиком, прежней строкой образца. Ключи задаются вместе — один без другого не проходит схему (прил. A № 21)."""
    eta20, eta11 = book.opt(FIXED_SHARE20), book.opt(FIXED_SHARE11)
    if eta20 is None or eta11 is None:
        return None
    return float(eta20), float(eta11)


def deduction_parts(ded20_0: float, ded11_0: float, eta20: float, eta11: float) -> DeductionParts:
    """Раздел вычета якоря каждого норматива на растущую и постоянную части (М§4.11). При η = 0 растущая часть —
    весь вычет якоря, постоянная — ноль: `1 × Ded_0` и `0 × Ded_0` точны, и строка вычета `ratios` даёт биты
    книги без ключей; при η = 1 растущая часть — ноль, вычет — сумма якоря во всех кварталах."""
    grow20 = (1 - eta20) * ded20_0
    fix20 = eta20 * ded20_0
    grow11 = (1 - eta11) * ded11_0
    fix11 = eta11 * ded11_0
    return DeductionParts(grow20=grow20, fix20=fix20, grow11=grow11, fix11=fix11)


@dataclass(frozen=True)
class CapitalConst:
    """Постоянные книги для нормативов (М§4.11)."""
    ded20_0: float
    ded11_0: float
    rwa0: float
    fvoci_recognition: float
    gap20: float
    gap11: float
    at1: float
    audit_cutoffs: tuple[int, ...]
    buffer20: float
    buffer11: float
    parts: DeductionParts | None = None    # части вычета якоря у книги с ключами доли; None — ключей нет


def capital_const(book: "Book", af: AnchorFacts, rwa0: float) -> CapitalConst:
    ded20_0 = float(book.get("capital.n20.deductions_anchor"))
    ded11_0 = float(book.get("capital.n11.deductions_anchor"))
    shares = fixed_shares(book)
    return CapitalConst(
        ded20_0=ded20_0,
        ded11_0=ded11_0,
        rwa0=rwa0,
        fvoci_recognition=float(book.get("capital.n20.fvoci_recognition")),
        gap20=float(book.get("capital.n20.gap_pp")),
        gap11=float(book.get("capital.n11.gap_pp")),
        at1=af.at1,
        audit_cutoffs=tuple(int(x) for x in book.get("capital.n11.audit_cutoffs")),
        buffer20=float(book.get("capital.mgmt_buffer.n20_0")),
        buffer11=float(book.get("capital.mgmt_buffer.n1_1")),
        parts=None if shares is None else deduction_parts(ded20_0, ded11_0, *shares),
    )


class Ratios(NamedTuple):                  # кортеж, а не класс данных: создаётся на каждой оценке шага
    rwa: float
    k20: float
    k11: float
    n20: float
    n11: float
    ded20: float
    ded11: float
    n11_star: float = 0.0                  # Н20.1 с прибылью периода (N11*, М§4.11)


def ratios(c: CapitalConst, *, bv: float, dpreg: float, reserve: float, unaudited: float,
           t2: float, rwa: float, ded_pp20: float, ded_pp11: float,
           rub20: float | None = None, rub11: float | None = None, at1: float | None = None) -> Ratios:
    """K20, K11, Н20.0 и Н20.1 (прокси Н1.1) на конец квартала (М§4.11); рядом с отчётным Н20.1 — Н20.1 с
    прибылью периода (N11*): он входит в ограничение роста капиталом (М§4.13).

    `unaudited` — E_q, результат неаудированного периода (знак любой). Из K11 исключается только
    прибыль, max(E_q, 0): убыток уже уменьшил BV и в базовый капитал не возвращается.

    Вычеты: без ключей доли — вычет якоря растёт с RWA целиком (строка образца); с ключами — растущая часть идёт
    за итоговыми RWA квартала, постоянная стоит суммой якоря (М§4.11). Путь вычета сценария `ded_pp` — в долях
    RWA, после деления, и долю не читает. `rub20`, `rub11` — вычет сценария в рублях квартала Drub_j,s,q (М§4.11):
    прибавляется к вычету своего норматива без множителя RWA, до деления; None — ключа нет, прежняя строка. `at1` —
    добавочный капитал AT1_q конца квартала в K20 (у книги с ключом доли добавочного капитала `capital.at1_share` — доля
    клетки на её RWA, М§4.11); None — факт якоря `c.at1`, прежняя строка. В K11 добавочного капитала нет."""
    parts = c.parts
    if parts is None:
        ded20 = c.ded20_0 * rwa / c.rwa0
        ded11 = c.ded11_0 * rwa / c.rwa0
    else:
        ded20 = parts.grow20 * rwa / c.rwa0 + parts.fix20
        ded11 = parts.grow11 * rwa / c.rwa0 + parts.fix11
    if rub20 is not None:                  # вычет сценария в рублях — к вычету квартала, без множителя RWA
        ded20 = ded20 + rub20
        ded11 = ded11 + rub11
    bvreg = bv + dpreg - (1 - c.fvoci_recognition) * reserve
    k20 = bvreg - ded20 + (c.at1 if at1 is None else at1) + t2
    k11 = bvreg - max(unaudited, 0.0) - ded11
    return Ratios(rwa=rwa, k20=k20, k11=k11, n20=k20 / rwa + c.gap20 - ded_pp20,
                  n11=k11 / rwa + c.gap11 - ded_pp11, ded20=ded20, ded11=ded11,
                  n11_star=n11_audited(k11, unaudited, rwa, c.gap11, ded_pp11))


def n11_audited(k11: float, unaudited: float, rwa: float, gap11: float, ded_pp11: float) -> float:
    """N11* — Н20.1 с прибылью периода в базовом капитале (E = 0, как после аудита; М§7): в K11
    возвращается ровно то, что из него исключено, — max(E, 0); убыток в нём уже учтён."""
    return (k11 + max(unaudited, 0.0)) / rwa + gap11 - ded_pp11


# ------------------------------------------------------------------ рост, ограниченный капиталом (М§4.13)

GROWTH = "capital.growth_constraint"
DIVIDEND_FIRST, GROWTH_FIRST = "dividend_first", "growth_first"


@dataclass(frozen=True)
class GrowthRule:
    """Параметры ограничения роста кредитных книг капиталом (`capital.growth_constraint`, М§4.13)."""
    order: str                             # что уступает первым: dividend_first — рост, growth_first — дивиденд
    lam_min: float                         # λ_min — нижняя граница доли потенциального прироста
    lookahead: int                         # H — на сколько кварталов вперёд видны ступени требования
    glide: float                           # δ — сколько требования набирается за квартал перед ступенью
    catch_up: float                        # κ_g — доля разрыва с потенциальным путём, навёрстываемая за год
    tol: float                             # допуск равенства норматива требованию

    @property
    def dividend_first(self) -> bool:
        return self.order == DIVIDEND_FIRST


def growth_rule(book: "Book") -> GrowthRule | None:
    """Правило ограничения роста книги; объекта нет или он выключен — None (рост задан, М§4.3)."""
    spec = book.opt(GROWTH)
    if not spec or spec.get("enabled") is not True:
        return None
    return GrowthRule(order=str(spec["order"]), lam_min=float(spec["min_growth_scale"]),
                      lookahead=int(spec["lookahead_quarters"]), glide=float(spec["glide_pp_per_quarter"]),
                      catch_up=float(spec["catch_up_rate"]), tol=float(spec["tol"]))


def glide_path(req: Sequence[float], lookahead: int, glide: float) -> tuple[float, ...]:
    """Требование с глиссадой (М§4.13.1): req*_q = max по h = 0…H (r_min(q+h, Q) − h × δ) — известная ступень
    требования набирается заранее, по δ за квартал; на конце сетки req* равно требованию."""
    last = len(req) - 1
    return tuple(max(req[min(q + h, last)] - h * glide for h in range(lookahead + 1)) for q in range(last + 1))


def after_audit_start(quarter: int, cutoffs: Sequence[int]) -> int:
    """Номер первого квартала года, прибыль с которого ещё не аудирована на конец `quarter`.

    E_q = Σ NI по кварталам после последнего квартала-отсечки, строго
    предшествующего q, по q включительно; возвращается сдвиг назад (0 — только q).
    """
    back = 0
    h = quarter
    while True:
        h = 4 if h == 1 else h - 1
        if h in cutoffs:
            return back
        back += 1
        if back > 3:
            return back


# ------------------------------------------------------------------ докапитализация (М§4.14)

RECAP = "capital.recapitalization"
AGM_QUARTER = "dividends.calendar.agm_quarter"      # h_A — квартал годового собрания (годовой календарь)
N20, N11 = "n20", "n11"                      # имена нормативов в записи решения о взносе
YEAR_QUARTERS = 4                            # кварталов в году: решение о взносе — раз в год
# Допуск инварианта «взнос закрывает разрыв» (М§14.1) — число ядра, не книги: остаток недостатка после взноса —
# не больше десятой доли взноса. Взнос равен недостатку пробного прохода; неучтённый первый порядок — вес риска
# денег взноса и рост вычетов с RWA, `w × (ρ + Dgrow / RWA_0)` взноса, где Dgrow — растущая часть вычета якоря (без
# ключей доли — весь вычет, с долей — меньше: остаток только уменьшается, М§4.11): при плотности балансирующих
# активов до 0,5 и требовании с вычетами до 0,2 это не больше 0,1. Ошибка механизма оставляет остаток порядка
# самого взноса.
RECAP_RESIDUAL_SHARE = 0.1
TIE_TOL = 1e-9                               # млрд ₽: «при равенстве» недостатков точек и нормативов — с точностью счёта
NAMED_LITERALS = {
    0.1: "RECAP_RESIDUAL_SHARE: допуск инварианта recap_covers_gap — доля взноса (М§14.1)",
    1e-9: "TIE_TOL: равенство недостатков в выборе точки и норматива решения о взносе, млрд ₽ (М§4.14.1 п. 3)",
}


@dataclass(frozen=True)
class RecapRule:
    """Параметры решения о взносе акционеров (`capital.recapitalization`, М§4.14), которые читает проход клеток.
    Дисконта размещения здесь нет: он — параметр оценки (`price_discount`), проход клеток его не читает."""
    lookahead: int                         # L — окно решения, кварталов после квартала решения
    min_amount: float                      # порог: недостаток не больше порога взносом не закрывается, млрд ₽
    quarter: int = 0                       # h_R — номер в году квартала решения о взносе (ключ `decision_quarter`;
    #                                        без ключа — квартал годового собрания h_A)
    span: int = YEAR_QUARTERS              # δ — кварталов от квартала решения до ближайшего нового решения клетки


def decision_quarter(book: "Book", spec: Mapping) -> int:
    """h_R — номер в году квартала решения о взносе (М§4.14.1): ключ `decision_quarter` объекта докапитализации,
    а без ключа — квартал годового собрания `dividends.calendar.agm_quarter`."""
    own = spec.get("decision_quarter")
    return int((book.opt(AGM_QUARTER) or 0) if own is None else own)


def invariant_span(agm_quarter: int, quarter: int) -> int:
    """δ — расстояние от квартала решения о взносе до ближайшего квартала с новым решением клетки, о дивиденде или
    о взносе (М§14.1): `min(4, ((h_A − h_R − 1) mod 4) + 1)`. Решение в квартал собрания — год (следующие взнос и
    собрание), иное — до ближайшего квартала собрания."""
    return min(YEAR_QUARTERS, (agm_quarter - quarter - 1) % YEAR_QUARTERS + 1)


def recap_rule(book: "Book") -> RecapRule | None:
    """Правило докапитализации книги; объекта нет или он выключен — None (взносов нет, М§4.14)."""
    spec = book.opt(RECAP)
    if not spec or spec.get("enabled") is not True:
        return None
    quarter = decision_quarter(book, spec)
    return RecapRule(lookahead=int(spec["lookahead_quarters"]), min_amount=float(spec["min_amount"]),
                     quarter=quarter, span=invariant_span(int(book.opt(AGM_QUARTER) or 0), quarter))


def price_discount(book: "Book") -> float:
    """d — дисконт цены размещения к справедливой цене акции после выпуска (М§6.5). У книги без включённой
    докапитализации — ноль: поле объекта при выключателе `false` не читается, формулы оценки — прежние."""
    spec = book.opt(RECAP)
    if not spec or spec.get("enabled") is not True:
        return 0.0
    return float(spec["price_discount"])


class RecapPoint(NamedTuple):
    """Точка окна решения о взносе: недостаток капитала к требованию по двум нормативам, млрд ₽ (знак любой)."""
    q: int
    s20: float
    s11: float

    @property
    def s(self) -> float:
        return max(self.s20, self.s11)


def shortfall(row: Mapping[str, float], q: int, *, last: bool) -> RecapPoint:
    """Недостаток капитала в точке окна (М§4.14.1 п. 3) по строке квартала: S_j = (req_j − Ñ_j) × RWA. Норматив —
    отчётный (Н20.1 — без неаудированной прибыли); в последней точке окна (`last`) из него вычтены дивиденды,
    объявленные, но ещё не вычтенные из регуляторного капитала: после окна их вычет никто не проверит."""
    rwa = row["rwa"]
    n20, n11 = row["n20"], row["n11"]
    if last:
        n20 -= row["dpreg"] / rwa
        n11 -= row["dpreg"] / rwa
    return RecapPoint(q=q, s20=(row["req20"] - n20) * rwa, s11=(row["req11"] - n11) * rwa)


@dataclass(frozen=True)
class RecapDecision:
    """Решение о взносе акционеров в квартал решения q_R (М§4.14.1, §4.14.4)."""
    year: int                              # год Y = Y(q_R) − 1 — год прибыли, дивиденд за который решает собрание
    #                                        того же календарного года
    q: int                                 # квартал решения q_R
    last: int                              # c_max — последняя точка окна
    points: tuple[RecapPoint, ...]         # недостаток по точкам окна q_R … c_max (пробный проход)
    shortfall: float                       # S — наибольший недостаток окна, млрд ₽ (знак любой)
    point: int                             # c* — точка наибольшего недостатка
    norm: str                              # j* — норматив наибольшего недостатка (n20 | n11)
    rec: float                             # Rec_Y: S при S > порога, иначе 0
    div: float                             # дивиденд решения о взносе: последнее решение клетки о дивиденде в
    #                                        кварталах q_R − 3 … q_R (уменьшение BV); решения не было — ноль
    div_model: float                       # его часть, решённая моделью, а не записью реестра
    div_source: str | None                 # источник этого решения о дивиденде; None — решения не было
    residual: float | None = None          # наибольший остаток недостатка в точках инварианта после окончательного
    #                                        расчёта, млрд ₽ (М§14.1); считается у решения со взносом
    span: int = YEAR_QUARTERS              # δ — кварталов до ближайшего нового решения клетки (точки инварианта)
    div_q: int | None = None               # квартал решения о дивиденде, чей дивиденд несёт запись; None — не было


def residual_points(decision: RecapDecision) -> range:
    """Точки инварианта «взнос закрывает разрыв» (М§14.1): кварталы окна от квартала решения до квартала перед
    ближайшим новым решением клетки — `q_R … min(c_max, q_R + δ − 1)`. В квартале нового решения (дивиденд
    собрания или следующий взнос) стоит решение, которого пробный проход не нёс: к взносу его остаток не относится."""
    return range(decision.q, min(decision.last, decision.q + decision.span - 1) + 1)


def worst_point(points: Sequence[RecapPoint]) -> tuple[float, RecapPoint, str]:
    """Наибольший недостаток окна S, его точка c* и норматив j* (М§4.14.1 п. 3); при равенстве — более ранняя
    точка и Н20.0. Равенство — с точностью счёта (`TIE_TOL`): недостаток — разность двух близких чисел, умноженная
    на RWA, и равные по формуле недостатки расходятся в последних знаках; на сам недостаток S допуск не влияет."""
    worst = max(point.s for point in points)
    best = next(point for point in points if point.s >= worst - TIE_TOL)
    return worst, best, N20 if best.s20 >= best.s11 - TIE_TOL else N11
