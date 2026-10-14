"""Оценка клетки: остаточный доход (печать) и дивидендная модель (инвариант), терминал (М§6–§7).

V_RI  = BV_v + Σ RI_q DF_v(τ_q) + DF_v(τ_Q) TV_RI,   RI_q = CI_q − k_q BV_(q−1) (q0: доля 1 − e);
V_DDM = Σ Div_q DF_v(τ_q) + DF_v(τ_Q) TV_DDM.
Равенство алгебраическое (телескопическая сумма) при совокупном ROE в RI,
k_q = DF_(q−1)/DF_q − 1, дивиденде в квартал ГОСА, делителе без собственных акций
и одном множителе времени терминала у обеих форм (М§6.4).

Взнос акционеров (докапитализация, М§4.14, §6.5): новые акции продаются с дисконтом d к справедливой цене после
выпуска, прежним акционерам взнос Rec стоит Rec / (1 − d). В DDM взнос — отрицательное распределение по цене
размещения, в RI — вычет цены размывания Rec × d / (1 − d); взносы кварталов, закрытых к дате оценки (C_v),
вычитаются из капитала на дату оценки, их цена размывания — без дисконта:
V_RI  = BV_v − C_v + Σ RI_q DF_v(τ_q) + DF_v(τ_Q) TV_RI − PVD;
V_DDM = Σ [Div_q − Rec_q / (1 − d)] DF_v(τ_q) − C_v / (1 − d) + DF_v(τ_Q) (TV_DDM − DC_T).
Отрицательные распределения терминала — недостаток капитала на T и отрицательная капиталонейтральная выплата —
по той же цене: DC_T = d / (1 − d) × [max(−X_T, 0) + max(−P_T, 0)], один вычет у обеих форм (М§7). Без рядов
взноса и при d = 0 — прежние строки. Путь числа акций клетки (`share_path`, М§6.6) — для печати: оценке он не
нужен.

Постоянные в рублях части за концом сетки (ключ `valuation.terminal.fixed_growth_share`, λ_F, М§7): доля λ_F
постоянных частей обеих сторон (постоянные прочие активы F_A с их RWA R_F; постоянные в рублях вычеты C_j) растёт с
бизнесом, как у образца, доля w = 1 − λ_F стоит в рублях вне бизнеса — без роста, удержания и угасания. Капитал под
постоянные части F_K = C_j* + κ_j* × R_F, их фондирование балансирующими статьями D_F = F_A − F_K, годовой доход
I_F = −y_m × D_F × (1 − τ) × (1 − nci); капитал бизнеса B = BV* − w × F_K, его доход CI_T+1 − w × (1 + g_T) × I_F;
TV_RI и P_T несут стоящую долю слагаемыми `w × (I_F − k_T × F_K) / k_T` и `w × I_F / k_T`. Без ключа и при λ_F = 1 —
прежние строки бит в бит.

Восьмой проход (М§7): купон года T + 1 у книги с ключом доли добавочного капитала — `CPN_ann + c_α,Q × ΔAT1_Q`;
надбавка за субординацию года L уходит из роста, год T + 1 несёт `π_T2 × (T2_Q − B_T2)`; прочие движения капитала
за концом сетки (ключ `valuation.terminal.other_movements: flat_rub`) — слагаемое `OM_ann / k_T` в TV_RI, P_T и TV_DDM,
`OM_ann = 4 × OM_LT` (значение `equity.other_movements` в году L + 1, М§0.4). Ключ прочих движений — параметр оценки:
проход клеток его не читает. Без ключей — прежние строки бит в бит.

Девятый проход (М§4.8, §7): у книги с ключом разрыва налога по правилу (`tax.structure`, `TaxRule`) налог — в рублях по
слагаемым, `Tax = (τ_stat + o × [PBT > 0]) × PBT − (τ_stat − τ_b) × ζ × IIS − δ_c × τ_stat × CPN` (`rule_tax` — одна
формула у квартала клетки и у года T + 1); строка NI_T+1 терминала заменяется налогом года T + 1 тем же правилом от
`PBT^x = (PBT_L + SP_L)(1 + g_T) − SP_T+1 − Y_X` и `IIS_T+1 = IIS_L (1 + g_T) − sec × y_sec × A_X` (A_X — часть избытка в
балансирующих активах, `excess_balancing`), CI_T+1 вычитает купон целиком (экономия — в налоге), доход блока постоянных
частей — ставкой после налога y^τ_m (`balancing_rate_after_tax`). Ставку τ_eff,L терминал с ключом не читает. Без ключа —
прежние строки бит в бит.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, NamedTuple, Sequence

from model.book_schema import BookError
from model.paths import Trajectory
from model.worlds import Discount

# Защита роста терминала: g_T не выше k_T − 1 б.п. (гейт k_gt_g, М§7).
G_BELOW_K = 0.0001
FADE_MODE = "valuation.terminal.fade_mode"   # вид угасания избыточной доходности терминала (М§7)
ONE_SIDED, SYMMETRIC = "one_sided", "symmetric"
FIXED_GROWTH = "valuation.terminal.fixed_growth_share"   # λ_F — доля постоянных частей, растущая за T (М§7)
N20, N11 = "n20", "n11"                      # связывающий на T норматив блока постоянных частей (М§7)
OTHER_MOVEMENTS = "valuation.terminal.other_movements"   # прочие движения капитала за концом сетки (М§7, прил. A № 33)
OM_NONE, OM_FLAT_RUB = "none", "flat_rub"
OM_MODES = (OM_NONE, OM_FLAT_RUB)
OM_PATH = "equity.other_movements"
TAX_STRUCTURE = "tax.structure"              # разрыв налога по правилу (М§4.8, прил. A № 34)


class TaxRule(NamedTuple):
    """Ключ разрыва налога по правилу `tax.structure` (М§4.8): ставка налога на процентный доход по облигациям τ_b,
    облагаемый по ней доход на рубль процентного дохода книги бумаг клетки ζ, прочие постоянные разницы o (доля
    прибыли до налога), вычет купона бессрочных из налоговой базы δ_c."""
    bond_rate: float
    bond_scale: float
    other_pp: float
    deductible: bool


def tax_structure(book) -> TaxRule | None:
    """Ключ `tax.structure` (М§4.8, прил. A № 34); ключа нет или `enabled: false` — None: разрыв — число
    `tax.effective_gap`, поведение образца. С ключом `tax.effective_gap` не читается."""
    node = book.opt(TAX_STRUCTURE)
    if not isinstance(node, Mapping) or node.get("enabled") is not True:
        return None
    return TaxRule(bond_rate=float(node["bond_rate"]), bond_scale=float(node["bond_scale"]),
                   other_pp=float(node["other_pp"]), deductible=node["coupon_deductible"] is True)


def rule_tax(rule: TaxRule, tau_stat: float, pbt: float, iis: float, coupon: float) -> tuple[float, float, float]:
    """Налог по правилу в рублях (М§4.8) — тройка (Tax, TS, τ_eff): `Tax = τ_eff × PBT − (τ_stat − τ_b) × ζ × IIS − TS`,
    маржинальная ставка `τ_eff = τ_stat + o × [PBT > 0]` (прочие постоянные разницы — доля положительной прибыли: при
    убытке их нет, налог непрерывен в нуле), налоговая экономия купона `TS = δ_c × τ_stat × CPN`. `iis` — процентный
    доход книги бумаг, `coupon` — купон бессрочных целиком (якоря и сверх базы)."""
    tau_e = tau_stat + (rule.other_pp if pbt > 0 else 0.0)
    saving = tau_stat * coupon if rule.deductible else 0.0
    tax = tau_e * pbt - (tau_stat - rule.bond_rate) * rule.bond_scale * iis - saving
    return tax, saving, tau_e


def excess_balancing(x_t: float, headroom: float, min_share: float = 0.0, wholesale_extra: float = 0.0) -> float:
    """A_X — часть избытка капитала на T, изъятая из балансирующих активов (X_T > 0) или положенная в них (X_T ≤ 0, со
    знаком минус) — та же, что в Y_X (`excess_income`, М§7): при избытке — до порога H* = HLA / (1 − m), при недостатке
    — сверх погашения добора опта WT."""
    if x_t > 0:
        return min(x_t, headroom / (1 - min_share))
    return -max(0.0, -x_t - wholesale_extra)


def balancing_rate_after_tax(rule: TaxRule, tau_stat: float, *, c_wholesale: float, wholesale_extra: float,
                             y_securities: float, y_liquidity: float, sec_share: float) -> float:
    """y^τ_m — маржинальная ставка балансирующих статей после налога по правилу (М§7, ключ `tax.structure`): опт при
    доборе опта WT_Q > 0 — `c_wholesale × (1 − τ_stat − o)`; иначе смесь, у которой бумаги несут льготу облигаций —
    `sec × y_sec × (1 − τ_stat − o + (τ_stat − τ_b) × ζ) + (1 − sec) × y_liq × (1 − τ_stat − o)`."""
    keep = 1 - tau_stat - rule.other_pp
    if wholesale_extra > 0:
        return c_wholesale * keep
    return (sec_share * y_securities * (keep + (tau_stat - rule.bond_rate) * rule.bond_scale)
            + (1 - sec_share) * y_liquidity * keep)


def terminal_other_movements(book, last_year: int) -> float:
    """OM_ann — прочие движения капитала за концом сетки в год (М§7): при `valuation.terminal.other_movements:
    flat_rub` — `4 × OM_LT`, OM_LT — значение траектории `equity.other_movements` в году L + 1 (М§0.4: при `LT` — `LT`,
    без него — значение последнего заданного года, у скаляра — само число); без ключа и при `none` — ноль (соглашение
    образца). Параметр оценки: проход клеток его не читает."""
    mode = book.opt(OTHER_MOVEMENTS, OM_NONE)
    if mode not in OM_MODES:
        raise BookError(f"{OTHER_MOVEMENTS} = {mode!r}: известны {', '.join(OM_MODES)} (М§7)")
    if mode == OM_NONE:
        return 0.0
    return 4 * Trajectory(book.get(OM_PATH)).year_value(last_year + 1)


def fixed_growth_share(book) -> float | None:
    """λ_F — доля постоянных в рублях частей, растущая за концом сетки (`valuation.terminal.fixed_growth_share`,
    М§7); ключа нет — None: соглашение образца, терминал растит весь баланс одним темпом."""
    value = book.opt(FIXED_GROWTH)
    return None if value is None else float(value)


def fixed_parts(fixed: Mapping[str, float], *, n20: float, req20: float, n11_star: float, req11: float,
                y_balancing: float, c_wholesale: float, wholesale_extra: float, tau_eff: float,
                nci_share: float, tax_rule: TaxRule | None = None, tau_stat: float = 0.0, y_securities: float = 0.0,
                y_liquidity: float = 0.0, sec_share: float = 0.0) -> dict[str, Any]:
    """Блок постоянных частей на конце сетки (М§7): связывающий на T норматив j* (Н20.0, если
    `N20ᵀ − req20 ≤ N11ᵀ − req11`; он задаёт X_T), капитал F_K = C_j* + κ_j* × R_F, фондирование D_F = F_A − F_K,
    маржинальная ставка балансирующих статей y_m (опт при доборе опта WT_Q > 0, иначе смесь) и годовой доход
    I_F = −y_m × D_F × (1 − τ_eff) × (1 − nci). `fixed` — выходы прохода клетки: f_a, r_f, c20, c11, kappa20,
    kappa11. У книги с ключом `tax.structure` (`tax_rule`) доход — ставкой после налога по правилу:
    I_F = −y^τ_m × D_F × (1 − nci) (`balancing_rate_after_tax`; τ_eff не читается)."""
    binding = N20 if (n20 - req20) <= (n11_star - req11) else N11
    c = fixed["c20"] if binding == N20 else fixed["c11"]
    kappa = fixed["kappa20"] if binding == N20 else fixed["kappa11"]
    f_k = c + kappa * fixed["r_f"]
    d_f = fixed["f_a"] - f_k
    y_m = c_wholesale if wholesale_extra > 0 else y_balancing
    i_f = -y_m * d_f * (1 - tau_eff) * (1 - nci_share)
    if tax_rule is not None:
        # разрыв налога по правилу (М§7): фондирование постоянных частей балансирующими статьями уносит и льготу бумаг
        y_tau = balancing_rate_after_tax(tax_rule, tau_stat, c_wholesale=c_wholesale, wholesale_extra=wholesale_extra,
                                         y_securities=y_securities, y_liquidity=y_liquidity, sec_share=sec_share)
        i_f = -y_tau * d_f * (1 - nci_share)
    return {"f_a": fixed["f_a"], "r_f": fixed["r_f"], "c": c, "kappa": kappa, "binding": binding, "f_k": f_k,
            "d_f": d_f, "i_f": i_f}


def fade_symmetric(book) -> bool:
    """Угасание терминала при любом знаке ROE_T − k_T — ключ книги `valuation.terminal.fade_mode: symmetric`;
    нет ключа или `one_sided` — одностороннее: угасает только положительный избыток (М§7)."""
    mode = book.opt(FADE_MODE, ONE_SIDED)
    if mode not in (ONE_SIDED, SYMMETRIC):
        raise BookError(f"{FADE_MODE} = {mode!r}: известны {ONE_SIDED}, {SYMMETRIC}")
    return mode == SYMMETRIC


@dataclass(frozen=True)
class Terminal:
    x_t: float                 # избыток капитала на T (млрд ₽; знак любой)
    bv_star: float             # BV* = BV_Q − X_T
    ni_t1: float               # ЧП акционерам терминального года
    ci_t1: float               # совокупный доход терминального года
    roe_raw: float             # ROE_T = CI_T+1 / BV*
    roe_t: float               # ROE'_T после угасания: одностороннего (fade — только при ROE_T > k_T) или,
    #                            при ключе книги, симметричного (fade — при любом знаке избытка)
    k_t: float
    g_t: float                 # после защиты
    g_capped: bool             # сработала защита g_T = k_T − 0,0001
    tv_ri: float
    tv_ddm: float
    y_x: float = 0.0           # доход на избыток, вычтенный из терминального года (млрд ₽)
    p_t: float = 0.0           # P_T — приведённая на T капиталонейтральная выплата (знак любой); TV_DDM = X_T + P_T
    dc_t: float = 0.0          # DC_T — цена размывания терминала (М§7); без дисконта размещения — ноль
    fixed: Mapping[str, Any] | None = None   # блок постоянных частей у книги с ключом λ_F (узел `terminal_fixed`
    #                                          таблиц книги: lam_f, f_a, r_f, c, kappa, binding, f_k, d_f, i_f,
    #                                          business_capital); без ключа — None. `roe_raw`, `roe_t` — бизнеса

    @property
    def negative(self) -> float:
        """Отрицательные распределения терминала — взносы акционеров на T: max(−X_T, 0) + max(−P_T, 0) (М§7)."""
        return max(-self.x_t, 0.0) + max(-self.p_t, 0.0)


def excess_income(x_t: float, y_balancing: float, c_wholesale: float, headroom: float,
                  min_share: float = 0.0, wholesale_extra: float = 0.0) -> float:
    """Y_X — доход на избыток капитала по маржинальной ставке балансирующих статей (М§7).

    Избыток (X_T > 0): пока минимум ликвидности не связывает — смесь бумаг и ликвидности, дальше — ставка
    опта. Порог — H* = HLA / (1 − m), а не сам запас HLA: изъятый капитал уменьшает и LA, и активы, от которых
    считается минимум (`min_share` — m). Недостаток (X_T ≤ 0) — зеркально: добавленный капитал сначала гасит
    добор опта WT (`wholesale_extra`, если минимум связывает), остальное ложится в балансирующие активы по смеси."""
    if x_t > 0:
        limit = headroom / (1 - min_share)
        within = min(x_t, limit)
        return y_balancing * within + c_wholesale * (x_t - within)
    repaid = min(-x_t, wholesale_extra)
    return -(c_wholesale * repaid + y_balancing * (-x_t - repaid))


def terminal(*, n20: float, req20: float, n11_star: float, req11: float, rwa: float, bv_q: float,
             pbt_last_year: float, y_balancing: float, c_wholesale: float, headroom: float,
             tau_eff: float, nci_share: float,
             coupon_annual: float, tau_stat: float, lt_inflation: float, real_growth: float,
             fade: float, multiple: float, k_t: float, min_share: float = 0.0,
             wholesale_extra: float = 0.0, symmetric: bool = False, discount: float = 0.0,
             fixed: Mapping[str, float] | None = None, lam_f: float | None = None, where: str = "",
             coupon_new: float | None = None, sp_l: float | None = None, sp_t1: float = 0.0,
             om_ann: float = 0.0, tax_rule: TaxRule | None = None, iis_l: float = 0.0, y_securities: float = 0.0,
             y_liquidity: float = 0.0, sec_share: float = 0.0) -> Terminal:
    """Терминал М§7: капиталонейтральная выплата, избыток капитала 1:1, одностороннее угасание через ROE_T.

    `y_balancing` — смесь доходностей бумаг и ликвидности на конце Q в их долях в LA, `c_wholesale` —
    ставка опта, `headroom` — запас HLA_Q балансирующих активов над минимумом ликвидности, `min_share` —
    доля минимума m (порог связывания — HLA / (1 − m)), `wholesale_extra` — добор опта WT_Q на конце Q.
    Угасание действует только на положительный избыток ROE_T − k_T: сходимость снизу не предполагается.
    `symmetric` (ключ книги `valuation.terminal.fade_mode: symmetric`) — угасание при любом знаке избытка:
    ROE'_T = k_T + fade × (ROE_T − k_T). `discount` — дисконт размещения d книги с включённой докапитализацией:
    отрицательные распределения терминала стоят прежним акционерам 1 / (1 − d) за рубль — цена размывания DC_T
    (её вычитает оценка у обеих форм); X_T, BV*, ROE_T, TV_RI и TV_DDM от него не зависят.

    `lam_f` — доля λ_F постоянных в рублях частей, растущая за концом сетки (М§7), `fixed` — постоянные части
    конца сетки из прохода клетки (`model.cell.fixed_block`): при λ_F < 1 доля 1 − λ_F стоит вне бизнеса, и строки
    от ROE_T до TV_DDM — строки блока; B ≤ 0 — отказ с названием клетки `where`. Без ключа (None) и при λ_F = 1 —
    прежние строки бит в бит (узел блока у книги с ключом печатается и при λ_F = 1).

    Восьмой проход (М§7), все три — None/ноль без ключа, прежние строки бит в бит: `coupon_new` — купон сверх базы года
    T + 1 у книги с ключом доли добавочного капитала, `c_α,Q × ΔAT1_Q` (CPN_T+1 = CPN_ann + coupon_new); `sp_l`,
    `sp_t1` — надбавка за субординацию года L (SP_L, в PBT_L) и года T + 1 (`π_T2 × (T2_Q − B_T2)`) у книги с ключом
    надбавки: NI_T+1 = [(PBT_L + SP_L)(1 + g_T) − SP_T+1 − Y_X](1 − τ)(1 − nci); `om_ann` — прочие движения капитала
    за концом сетки в год (OM_ann = 4 × OM_LT, ключ `valuation.terminal.other_movements: flat_rub`): слагаемое
    `OM_ann / k_T` в TV_RI, P_T и TV_DDM — вне роста, удержания, угасания и блока λ_F; DC_T — от нового P_T; X_T, BV*,
    ROE_T и ROE'_T его не читают.

    Девятый проход (М§7, §4.8), без ключа — None, прежние строки бит в бит: `tax_rule` — ключ разрыва налога по правилу;
    тогда налог года T + 1 — правилом в рублях от `PBT^x = (PBT_L + SP_L)(1 + g_T) − SP_T+1 − Y_X`, дохода книги бумаг
    `IIS_T+1 = IIS_L (1 + g_T) − sec × y_sec × A_X` (`iis_l` — IIS года L, `sec_share`, `y_securities` — доля и ставка
    бумаг конца сетки) и купона года T + 1; `NI_T+1 = (PBT^x − Tax_T+1)(1 − nci)`, `CI_T+1 = NI_T+1 − CPN_T+1` (экономия
    купона — в налоге рублями купона T + 1); доход блока постоянных частей — ставкой после налога (`y_liquidity`);
    `tau_eff` с ключом не читается."""
    x_t = multiple * min((n20 - req20) * rwa, (n11_star - req11) * rwa)
    bv_star = bv_q - x_t
    g = (1 + lt_inflation) * (1 + real_growth) - 1
    capped = g > k_t - G_BELOW_K
    if capped:
        g = k_t - G_BELOW_K
    y_x = excess_income(x_t, y_balancing, c_wholesale, headroom, min_share, wholesale_extra)
    if sp_l is None:
        ni_t1 = (pbt_last_year * (1 + g) - y_x) * (1 - tau_eff) * (1 - nci_share)
    else:
        # надбавка за субординацию (М§7): надбавка года L из роста уходит, год T + 1 несёт ставку на сумму сверх базы
        ni_t1 = ((pbt_last_year + sp_l) * (1 + g) - sp_t1 - y_x) * (1 - tau_eff) * (1 - nci_share)
    if coupon_new is not None:              # купон года T + 1 с купоном сверх базы (М§7): CPN_ann + c_α,Q × ΔAT1_Q
        coupon_annual = coupon_annual + coupon_new
    ci_t1 = ni_t1 - coupon_annual * (1 - tau_stat)
    if tax_rule is not None:
        # разрыв налога по правилу (М§7): строка NI_T+1 заменяется налогом года T + 1 в рублях; рубль избытка, изъятый
        # из бумаг, уносит свою льготу; экономия купона — рублями купона T + 1, купон в CI_T+1 — целиком
        pbt_x = (pbt_last_year + (sp_l or 0.0)) * (1 + g) - sp_t1 - y_x
        a_x = excess_balancing(x_t, headroom, min_share, wholesale_extra)
        iis_t1 = iis_l * (1 + g) - sec_share * y_securities * a_x
        tax_t1, _, _ = rule_tax(tax_rule, tau_stat, pbt_x, iis_t1, coupon_annual)
        ni_t1 = (pbt_x - tax_t1) * (1 - nci_share)
        ci_t1 = ni_t1 - coupon_annual
    block = None
    if lam_f is not None:
        block = fixed_parts(fixed, n20=n20, req20=req20, n11_star=n11_star, req11=req11, y_balancing=y_balancing,
                            c_wholesale=c_wholesale, wholesale_extra=wholesale_extra, tau_eff=tau_eff,
                            nci_share=nci_share, tax_rule=tax_rule, tau_stat=tau_stat, y_securities=y_securities,
                            y_liquidity=y_liquidity, sec_share=sec_share)
    if lam_f is None or lam_f == 1.0:
        roe_raw = ci_t1 / bv_star
        excess = roe_raw - k_t
        if symmetric:
            roe_t = k_t + fade * excess
        else:
            roe_t = k_t + fade * max(excess, 0.0) + min(excess, 0.0)
        tv_ri = (roe_t - k_t) * bv_star / (k_t - g)
        tv_ddm = x_t + (roe_t - g) * bv_star / (k_t - g)
        p_t = (roe_t - g) * bv_star / (k_t - g)
        node = None if block is None else {"lam_f": lam_f, **block, "business_capital": bv_star}
    else:
        # λ_F < 1 (М§7): доля w постоянных частей стоит в рублях вне бизнеса — капитал w × F_K, доход w × I_F в год,
        # без роста, удержания и угасания; бизнес — капитал B и доход CI_T+1 без дохода стоящей доли, который образец
        # вырастил на g_T; угасание — у бизнеса
        w = 1 - lam_f
        f_k, i_f = block["f_k"], block["i_f"]
        b = bv_star - w * f_k
        if not b > 0:
            raise BookError(f"{where}: капитал бизнеса терминала B = BV* − (1 − λ_F) × F_K = {bv_star:.6g} − {w:g} × "
                            f"{f_k:.6g} = {b:.6g} ≤ 0 — постоянные части больше капитала терминала: книга "
                            "несогласована (М§7)")
        ci_b = ci_t1 - w * (1 + g) * i_f
        roe_raw = ci_b / b
        excess = roe_raw - k_t
        if symmetric:
            roe_t = k_t + fade * excess
        else:
            roe_t = k_t + fade * max(excess, 0.0) + min(excess, 0.0)
        tv_ri = (roe_t - k_t) * b / (k_t - g) + w * (i_f - k_t * f_k) / k_t
        p_t = (roe_t - g) * b / (k_t - g) + w * i_f / k_t
        tv_ddm = x_t + p_t
        node = {"lam_f": lam_f, **block, "business_capital": b}
    if om_ann:
        # прочие движения капитала за концом сетки (М§7): постоянно в номинальных рублях, поток года — на конец года,
        # Σ OM_ann / (1 + k_T)^n = OM_ann / k_T; в RI — совокупный доход без капитала под ним: TV_DDM − TV_RI = BV_Q
        om_t = om_ann / k_t
        tv_ri = tv_ri + om_t
        p_t = p_t + om_t
        tv_ddm = tv_ddm + om_t
    # X_T и P_T не сальдируются: недостаток вносится на T, выплата идёт с года T + 1 (М§7)
    dc_t = dilution(max(-x_t, 0.0) + max(-p_t, 0.0), discount) if discount else 0.0
    return Terminal(x_t=x_t, bv_star=bv_star, ni_t1=ni_t1, ci_t1=ci_t1, roe_raw=roe_raw, roe_t=roe_t,
                    k_t=k_t, g_t=g, g_capped=capped, tv_ri=tv_ri, tv_ddm=tv_ddm, y_x=y_x, p_t=p_t, dc_t=dc_t,
                    fixed=node)


def dilution(amount: float, discount: float) -> float:
    """Цена размывания взноса `amount` (М§6.5): новые акции проданы с дисконтом d к справедливой цене после
    выпуска — за взнос отдана стоимость amount / (1 − d), разница сверх взноса — amount × d / (1 − d)."""
    return amount * discount / (1 - discount)


@dataclass(frozen=True)
class CellValue:
    bv_v: float
    v_ri: float
    v_ddm: float
    pv_ri_explicit: float      # Σ RI_q DF_v(τ_q)
    pv_terminal: float         # DF_v(τ_Q) TV_RI
    pv_div_explicit: float     # Σ Div_q DF_v(τ_q)
    terminal_share: float      # DF_v(τ_Q) TV_DDM / V_DDM; у книги с докапитализацией — с TV_DDM − DC_T и к норме
    #                            клетки max(V_DDM, BV_v − C_v) (М§6.4)
    ri: tuple[float, ...]      # RI_q, q = 0…Q (до q0 — 0)
    # докапитализация (М§6.5); без рядов взноса — нули, а `bv_v` — капитал на дату оценки как он есть
    c_v: float = 0.0           # C_v — взносы кварталов, закрытых к дате оценки; `bv_v` — уже без них
    pvd: float = 0.0           # PVD — приведённая цена размывания: закрытые кварталы, явный участок и терминал
    pv_rec: float = 0.0        # Σ Rec_q × DF̃_q — приведённая сумма взносов явного участка (закрытые — без дисконта)
    pv_rec_terminal: float = 0.0   # DF_v(τ_Q) × [max(−X_T, 0) + max(−P_T, 0)] — то же для терминала
    pv_tv_ddm: float | None = None     # DF_v(τ_Q) × (TV_DDM − DC_T) — числитель доли терминала (М§6.4); без рядов
    #                                    взноса — None


def cell_norm(value: float, capital: float) -> float:
    """M_c — норма клетки книги с включённой докапитализацией (М§6.4): стоимость, а там, где она ниже капитала на
    дату оценки на нынешний делитель (BV_v − C_v), — капитал. Цена размывания и недостаток капитала проводят
    стоимость клетки через ноль: отношение к ней там неограниченно при сколь угодно малой абсолютной ошибке."""
    return max(abs(value), capital)


def value_cell(*, q0: int, elapsed: float, disc: Discount, bv: Sequence[float], ci: Sequence[float],
               div: Sequence[float], term: Terminal, rec: Sequence[float] | None = None,
               discount: float = 0.0) -> CellValue:
    """RI и DDM по рядам клетки (индекс q = 0…Q; bv — на конец квартала после дивиденда). `rec` — ряд взносов
    акционеров книги с включённой докапитализацией, `discount` — её дисконт размещения d (М§6.5): тогда обе
    формы несут цену размывания, а капитал на дату оценки `bv_v` — на нынешний делитель, без взносов закрытых
    кварталов. Без ряда взносов — прежние формулы."""
    if rec is not None:
        return _value_with_recap(q0=q0, elapsed=elapsed, disc=disc, bv=bv, ci=ci, div=div, term=term, rec=rec,
                                 discount=discount)
    Q = len(bv) - 1
    e = elapsed
    bv_v = bv[q0 - 1] + e * ci[q0]
    dfq = disc.dfq
    ri = [0.0] * (Q + 1)
    k0 = 1 / dfq[q0] - 1
    ri[q0] = (1 - e) * ci[q0] - k0 * bv_v
    for q in range(q0 + 1, Q + 1):
        ri[q] = ci[q] - disc.k[q] * bv[q - 1]
    pv_ri = sum(ri[q] * dfq[q] for q in range(q0, Q + 1))
    pv_div = sum(div[q] * dfq[q] for q in range(q0, Q + 1))
    pv_term = dfq[Q] * term.tv_ri
    v_ri = bv_v + pv_ri + pv_term
    v_ddm = pv_div + dfq[Q] * term.tv_ddm
    share = dfq[Q] * term.tv_ddm / v_ddm if v_ddm else float("nan")
    return CellValue(bv_v=bv_v, v_ri=v_ri, v_ddm=v_ddm, pv_ri_explicit=pv_ri, pv_terminal=pv_term,
                     pv_div_explicit=pv_div, terminal_share=share, ri=tuple(ri))


def _value_with_recap(*, q0: int, elapsed: float, disc: Discount, bv: Sequence[float], ci: Sequence[float],
                      div: Sequence[float], term: Terminal, rec: Sequence[float], discount: float) -> CellValue:
    """Обе формы оценки со взносами акционеров (М§6.5). RI_q, плата за капитал и терминалы — формулы М§6.1–§6.2
    и §7 без изменений: BV_(q−1) в плате за капитал — капитал клетки вместе с принятыми взносами. Взносы
    кварталов до квартала даты оценки стоят на линейке в нуле: из капитала на дату оценки вычитаются номиналом,
    их цена размывания — без дисконта."""
    Q = len(bv) - 1
    e = elapsed
    d = discount
    bv_full = bv[q0 - 1] + e * ci[q0]           # BV_v: капитал клетки на дату оценки, с деньгами закрытых взносов
    dfq = disc.dfq
    ri = [0.0] * (Q + 1)
    k0 = 1 / dfq[q0] - 1
    ri[q0] = (1 - e) * ci[q0] - k0 * bv_full
    for q in range(q0 + 1, Q + 1):
        ri[q] = ci[q] - disc.k[q] * bv[q - 1]
    pv_ri = sum(ri[q] * dfq[q] for q in range(q0, Q + 1))
    pv_div = sum(div[q] * dfq[q] for q in range(q0, Q + 1))
    pv_term = dfq[Q] * term.tv_ri
    c_v = sum(rec[q] for q in range(1, q0))
    pv_rec_open = sum(rec[q] * dfq[q] for q in range(q0, Q + 1))
    pvd = dilution(c_v, d) + dilution(pv_rec_open, d) + dfq[Q] * term.dc_t
    v_ri = bv_full - c_v + pv_ri + pv_term - pvd
    tv_ddm = term.tv_ddm - term.dc_t            # терминал формы DDM в оценке — по цене размещения (М§7)
    v_ddm = pv_div - pv_rec_open / (1 - d) - c_v / (1 - d) + dfq[Q] * tv_ddm
    # доля терминала — к норме клетки (М§6.4): ниже капитала на дату оценки доля считается к капиталу
    norm = max(v_ddm, bv_full - c_v)
    share = dfq[Q] * tv_ddm / norm if norm else float("nan")
    return CellValue(bv_v=bv_full - c_v, v_ri=v_ri, v_ddm=v_ddm, pv_ri_explicit=pv_ri, pv_terminal=pv_term,
                     pv_div_explicit=pv_div, terminal_share=share, ri=tuple(ri), c_v=c_v, pvd=pvd,
                     pv_rec=c_v + pv_rec_open, pv_rec_terminal=dfq[Q] * term.negative, pv_tv_ddm=dfq[Q] * tv_ddm)


@dataclass(frozen=True)
class SharePath:
    """Путь числа акций клетки (М§6.6) — для печати; на оценку не влияет."""
    n: tuple[float | None, ...]            # N_q, млн шт., q = 0…Q; после обрыва пути значения нет
    stake: tuple[float, ...]               # s_q = N_div / N_q — доля нынешних акций; после обрыва пути — ноль
    w: Mapping[int, tuple[float, float]]   # квартал взноса → (W_q, W_q − Rec_q / (1 − d)): стоимость всех акций
    #                                        сразу после взноса и стоимость акций, существовавших до него
    broken: int | None                     # квартал обрыва пути; None — путь цел


def shares_value(q: int, *, q0: int, disc: Discount, div: Sequence[float], rec: Sequence[float], term: Terminal,
                 discount: float) -> float:
    """W_q — стоимость всех акций клетки сразу после взноса квартала q по её же будущим чистым распределениям
    (М§6.6): те же потоки и тот же дисконт, что в V_DDM; кварталы до квартала даты оценки стоят на линейке в
    нуле (`Discount.dfq` там — единица). W_0 = V_DDM."""
    Q = len(rec) - 1
    dfq = disc.dfq
    ahead = (sum(div[j] * dfq[j] for j in range(max(q + 1, q0), Q + 1))
             - sum(rec[j] / (1 - discount) * dfq[j] for j in range(q + 1, Q + 1))
             + dfq[Q] * (term.tv_ddm - term.dc_t))
    return ahead / dfq[q]


def share_path(*, q0: int, disc: Discount, div: Sequence[float], rec: Sequence[float], term: Terminal,
               discount: float, n_div: float) -> SharePath:
    """Путь делителя клетки (М§6.6): цена размещения — (1 − d) от стоимости акции после выпуска, поэтому
    N_q = N_(q−1) × W_q / (W_q − Rec_q / (1 − d)) в квартале взноса и N_q = N_(q−1) в прочих; N_0 = N_div. Если
    акции прежних акционеров в квартале взноса ничего не стоят (W_q − Rec_q / (1 − d) ≤ 0), по положительной
    цене выпуск не размещается — путь обрывается: с этого квартала доля ноль, числа акций нет."""
    Q = len(rec) - 1
    n: list[float | None] = [n_div]
    stake = [1.0]
    w: dict[int, tuple[float, float]] = {}
    broken = None
    for q in range(1, Q + 1):
        if broken is not None:
            n.append(None)
            stake.append(0.0)
            continue
        if not rec[q] > 0:
            n.append(n[-1])
            stake.append(stake[-1])
            continue
        after = shares_value(q, q0=q0, disc=disc, div=div, rec=rec, term=term, discount=discount)
        before = after - rec[q] / (1 - discount)
        w[q] = (after, before)
        if before <= 0:
            broken = q
            n.append(None)
            stake.append(0.0)
            continue
        n.append(n[-1] * after / before)
        stake.append(n_div / n[-1])
    return SharePath(n=tuple(n), stake=tuple(stake), w=w, broken=broken)
