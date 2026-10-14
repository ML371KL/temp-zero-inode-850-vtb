"""Квартальный проход клетки (мир × режим × регуляторный сценарий) в порядке М§4.2.

В квартале q: (1) в квартал ГОСА — решение о дивиденде (пробный проход с состояния
на конец q − 1); (2) ставки мира и пути режима и сценария; (3) объёмы небалансирующих
статей; (4) ставки книг; (5) предварительный баланс при BV_(q−1) − Div_q и DP_q;
(6) строки ОПУ; (7) капитал — OCI, купон AT1, прочие движения, BV_q; (8) окончательный
баланс при BV_q; (9) RWA и нормативы. Затем терминал (М§7) и оценка RI/DDM (М§6).

Сдвиг ЧПМ в ЧПД — ближний (`regimes.near_nim_shift`, общий для клеток) + сдвиг режима +
отклонение A-P2u (М§4.4). «Прочее» ОПУ — годовая сумма × индекс цен × доля квартала
(`other.misc_quarter_shares`, М§4.7) — и в году якоря: остатком год не закрывается, сумма
года — выход (М§0.3); остатком закрывается только непрофильный результат. Кредитная
переоценка кредитов по СС (FVC) — отклонение CoR клетки от пути режима-опоры
`credit.fv_loans_ref` на средних кредитах по СС, внутри шага; опора — путь книги до
розыгрыша осей (`Book.base`, М§4.6). Сжатие φ: доля `nii.phi_split` — в спредах кредитных
книг (φ_A), остаток — добавкой φ_L × X_W,q к стоимости пассивов с `phi` (М§4.4). Доход на
избыток капитала терминала — по маржинальной ставке балансирующих статей (М§7). Предварительный
проход (`preliminary_paths`) — клетка без отклонений A-P2u до заданного квартала: ожидания
режимов μ (М§12). Ключи второй формы банка (все необязательны; нет ключа — прежняя строка кода): премия роста
траекториями по секторам (`volumes.loan_share_drift`, `funds_share_drift`), постоянные прочие активы
(`volumes.other_assets_fixed`), связь комиссий, страхования и расходов с ростом объёма (`*.volume_link`,
`volumes.link_base`, М§4.7), множитель RWA режима (`regimes.<r>.rwa_density_mult`, М§4.11), путь постоянной части
прочих активов (`volumes.other_assets_fixed_change`: приращение квартала к якорю — в прочих активах и в RWA с весом
ω_Δ, деньги убывания — в балансирующих статьях, М§4.3), вычет сценария в рублях
(`capital.reg_scenarios.<s>.deduction_rub` — в вычете квартала без множителя RWA, М§4.11). Постоянные части конца
сетки (`fixed_block`) проход отдаёт терминалу книги с ключом λ_F (`valuation.terminal.fixed_growth_share`, М§7);
саму долю проход не читает. Доля инструментов в RWA своей клетки (`capital.n20.t2_share`, М§4.11): с квартала ключа
q_χ T2 клетки — χ_c × RWA шага; χ_c — часть состояния (`State.t2s`), её задаёт записанный шаг квартала q_χ − 1 (у
пробного прохода — свой), оценка «только нормативы» её не задаёт; κ_20 блока постоянных частей — на χ_c меньше.

Восьмой проход (ключи книги, без ключа — прежние строки бит в бит). Доля добавочного капитала в RWA своей клетки
(`capital.at1_share`, М§4.9–§4.11): с квартала ключа q_α AT1 клетки — α_c × RWA_q (`State.a1s`, её задаёт записанный
шаг квартала q_α − 1); AT1 — строка пассивов: в предварительном балансе AT1_(q−1), выпуск квартала — деньги конца
квартала в балансирующих активах, RWA квартала — неподвижная точка в закрытой форме (`_Cell.at1_issue`, М§4.10);
купон сверх базы `(key_W,q + s_α) × (AT1_(q−1) − B_α) × d/365` — в совокупном доходе после налога и в базе дивиденда
при `deduct_at1_after_tax`; AT1 — в K20, не в K11; κ_20 блока постоянных частей — ещё на α_c меньше; купон года T + 1 —
с купоном сверх базы конца сетки. Надбавка за субординацию дополнительного капитала (`capital.n20.t2_premium`, М§4.4,
§4.11): `π_T2 × (T2_c,(q−1) − B_T2) × d/365` — процентным расходом в ЧПД; в терминале — надбавка года L и ставка на
сумму сверх базы конца сетки. Ряды клетки `at1`, `coupon_new`, `t2_premium` — внутренние.

Девятый проход (ключи книги, без ключа — прежние строки бит в бит). Купон бессрочных квартала CPN_q считается до налога
(М§4.2 п. 6). Купон якоря по ставке своего мира (`capital.at1_coupon`, М§4.9): в квартале купона —
`Cfix + Cflt × (k̄_q + s_flt)`, k̄_q — средняя ключевая своего мира за четыре квартала, кончая кварталом купона
(кварталы не позже якоря — ключевая квартала якоря; `anchor_coupon`), сумма слота фактов не читается; купон года T + 1 —
по ключевой квартала Q. Разрыв налога по правилу (`tax.structure`, М§4.8): налог квартала — в рублях
(`model.valuation.rule_tax`) от прибыли до налога, процентного дохода книги бумаг клетки IIS_q и купона квартала;
`tax.effective_gap` не читается; ряд `tau_eff` — маржинальная ставка, купон в совокупном доходе и в базах дивиденда —
целиком (`tau_cpn` = 0: экономия — в налоге); без ключа `tau_cpn` — законная ставка. Ряды `iis`, `tax_coupon`, `tau_cpn`.

Квартальный календарь дивидендов (`dividends.calendar.frequency: quarterly`, М§5.7): в квартале клетки от нуля
до двух решений — записи реестра и решения модели за открытые кварталы прибыли (`Prepared.calendar`). Запас
капитала под решения модели — оценка шага этого же квартала на копии состояния, без записи и без решений модели
(`_Cell.quarter_room`: одна точка, пробных проходов вперёд нет); квартал считается один раз с суммой дивидендов,
у каждого решения свои кварталы выплаты и вычета из регуляторного капитала. Терминал не раздаёт как избыток
дивиденды, уже вычтенные из BV, но ещё стоящие в регуляторном капитале (М§7). Без ключа — годовой проход.

Рост, ограниченный капиталом (`capital.growth_constraint`, М§4.13; только при квартальном календаре): дивиденд и
доля прироста кредитных книг λ квартала определяются вместе, оценками шага на копии состояния
(`_Cell.evaluate`). Требование — с глиссадой к известным ступеням (`capital.glide_path`), Н20.1 ограничения — с
прибылью периода. λ* — закрытая формула по двум оценкам (полный рост и наименьший), проверочная полная оценка и не
больше одного шага секущей; при λ* = 1 и запасе — навёрстывание разрыва с потенциальным путём, раньше выплаты
избытка. Принятая оценка и есть запись шага (`_Cell.run_constrained`). Объекта нет или он выключен — рост задан.

Докапитализация (`capital.recapitalization`, М§4.14; только при годовом календаре и без ограничения роста): в
квартал решения о взносе — квартал годового собрания, а при ключе книги `decision_quarter` квартал с этим номером
в году — клетка принимает решение о взносе акционеров (`_Cell.decide_recap`; в квартал собрания — вслед за
решением о дивиденде): пробный проход с уже принятыми дивидендами, без взноса и без новых решений в кварталах
после квартала решения, по точкам окна; недостаток капитала к требованию по отчётным нормативам, взнос —
недостаток выше порога. Пробный проход дивиденда решений о взносе не принимает. Взнос приходит в конце квартала: в
предварительный баланс и в совокупный доход не входит, в капитал, окончательный баланс и оба базиса норматива —
входит (`_Cell.step(rec=…)`); зарабатывает со следующего квартала. Цена размещения — в оценке (`value_path`,
`model.valuation`), путь числа акций — у полной клетки (М§6.5–§6.6). Объекта нет или он выключен — взносов нет.

Книжные величины, общие для всех клеток прогона, готовит `prepare` (один раз на
прогон); клетка читает их из контекста `RunContext` (model/grid.py).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from operator import methodcaller
from typing import TYPE_CHECKING, Any, Mapping, NamedTuple, Sequence

from model.book import AnchorFacts, BookRoles, SECURITIES, LIQUIDITY, WHOLESALE, anchor_facts, book_roles
from model.book_schema import BookError, FactsError
from model.capital import (YEAR_QUARTERS, CapitalConst, GrowthRule, RecapDecision, RecapRule, RwaWeights,
                           ScenarioPath, after_audit_start, capital_const, density_index, fixed_change, fx_index,
                           glide_path, growth_rule, n11_audited, price_discount, ratios, recap_rule, regime_rwa_mult,
                           residual_points, rwa_anchor, rwa_weights, scenario_path, shortfall, worst_point)
from model.credit import Bridge, fvc_amount, kappa_addon, kappa_world, regime_cor_engine
from model.dividends import (THOUSAND, Checkpoint, Decision, Policy, QuarterCalendar, base_of_year, decide,
                             decide_quarter, headroom, make_policy, pool_policy, quarter_bases, quarter_calendar,
                             record_key, register_dps)
from model.nii import current_share_target, spread_paths
from model.paths import Trajectory
from model.timeline import DAYS_IN_YEAR, QUARTER_YEARS, Timeline, parse_period, period_str, to_date
from model.valuation import (SharePath, TaxRule, fade_symmetric, fixed_growth_share, rule_tax, share_path,
                             tax_structure, terminal, terminal_other_movements, value_cell)
from model.worlds import BASE_WORLD, Discount, WorldPath

if TYPE_CHECKING:
    from model.book import Book, Facts
    from model.grid import RunContext
    from model.nii import Transmission

# Строки кварталов CellResult.quarters (индекс q = 0…Q; q = 0 — якорь по фактам).
QUARTER_FIELDS = (
    "bv", "ni_sh", "ni", "pbt", "nii", "llp", "fvc", "fees", "opex", "ins", "misc", "noncore", "fvr",
    "one_off", "tax", "ot", "oci", "coupon", "om", "ci", "div", "dp", "dpreg", "pay", "reserve",
    "rwa", "k20", "k11", "n20", "n11", "ded20", "ded11", "e_unaudited", "req20", "req11", "floor20",
    "floor11", "loans", "loans_ac", "loans_fv", "funds", "funds_retail", "iea", "iea_avg",
    "loans_ac_avg", "loans_fv_avg", "assets", "liabilities_equity", "securities", "liquidity", "wholesale",
    "wholesale_extra", "other_assets", "other_liabilities", "allowance", "current_share",
    "nim", "cor", "cir", "roe_q", "k_q", "key", "tau_stat", "tau_eff", "int_income", "int_expense",
    "dia", "overlay",
    "div_model",                           # часть div, решённая моделью, а не записью реестра (М§5.7.5)
    # рост, ограниченный капиталом (М§4.13.3); при выключенном механизме — λ = 1, требование без глиссады
    "lam", "loans_potential", "catch_up", "req20_glide", "req11_glide",
    "n11_star",                            # Н20.1 с прибылью периода (М§4.11)
    "rec",                                 # взнос акционеров в конце квартала (М§4.14); без докапитализации — ноль
    "t2",                                  # T2 в K20 (М§4.11): траектория, с квартала ключа доли — χ_c × RWA (внутренний)
    # восьмой проход (внутренние): AT1 конца квартала (факт якоря; с квартала ключа доли — α_c × RWA, М§4.11), купон
    # сверх базы квартала (часть ряда `coupon`, М§4.9), надбавка за субординацию T2 квартала (в ЧПД, М§4.4)
    "at1", "coupon_new", "t2_premium",
    # девятый проход: процентный доход книги бумаг клетки IIS_q (М§4.8), налоговая экономия купона бессрочных TS_q (у
    # книги с ключом `tax.structure`; без него — ноль), налоговая ставка купона в совокупном доходе τ_cpn (без ключа —
    # законная, с ключом — ноль: экономия — в налоге)
    "iis", "tax_coupon", "tau_cpn",
)
# Ряды-базы «к тому же кварталу», которые шаг пишет в клетку: оценка шага на копии состояния их снимает. `cpn_new` —
# купон сверх базы квартала (база дивиденда, М§5.2, §5.7.3): только у книги с ключом доли добавочного капитала.
STEP_FLOWS = ("fees", "opex", "ins", "ni_sh", "vol", "cpn_new")
CPN_NEW = STEP_FLOWS[-1]
# Годовые ряды роста кредитных книг CellResult.growth (по годам клетки, М§4.13.3).
GROWTH_FIELDS = ("potential", "actual", "cut_share", "catch_up", "lam_min")
# Годовые ряды клетки у книги с включённой докапитализацией (М§4.14.4): взнос, принятый в календарном году,
# доля нынешних акций и путь делителя клетки на конец года (М§6.6).
RECAP_FIELDS = ("rec", "stake", "shares")
RECAP_FLAG, RECAP_DIVIDEND_FLAG = "recapitalization", "recap_with_dividend"   # флаги клетки (М§4.14.4)
FUNDS_SIDE = "funds"                         # ключ памяти оценок шага: сторона средств клиентов квартала
CALENDAR = "calendar"                        # ключ общего прогона: годы и номера кварталов сетки
PAYOUT = "payout"                            # ключ общего прогона: доля выплаты политики по годам прибыли
ANCHOR = "anchor"                            # ключ общего прогона: строка якоря сценария капитала
SLOPE_TOL = 1e-9                             # млрд ₽: урезание роста норматив не поправляет — делить не на что
LAM_TOL = 1e-12                              # λ* < 1 − допуск — прирост квартала урезан (флаг growth_cut)
NAMED_LITERALS = {
    1e-9: "SLOPE_TOL: порог наклона условия роста по доле прироста, млрд ₽ (М§4.13.2 п. 3)",
    1e-12: "LAM_TOL: допуск признака «рост урезан» (М§4.13.3)",
}


# ------------------------------------------------------------------ подготовка прогона


@dataclass(frozen=True)
class RegimePath:
    regime: str
    cor_engine: tuple[float, ...]          # путь CoR режима в базисе движка (без κ и δ)
    nim_shift: tuple[float, ...]           # сдвиг ЧПМ режима (без ближнего сдвига)
    loan_adj: Mapping[int, float]          # год → поправка к росту кредита
    override: Mapping[int, float]          # год → абсолютный рост (кризис)
    one_off_q: int | None
    one_off_amount: float
    shock_year: int | None                 # год шока = год якоря + shock_year_offset (М§3.2); нет ключа — None
    rwa_mult: tuple[float, ...] | None = None   # M_r,q — множитель RWA режима (М§4.11); нет ключа — None


@dataclass(frozen=True)
class Prepared:
    """Книжные величины прогона, общие для клеток сетки."""
    timeline: Timeline
    roles: BookRoles
    books: Mapping[str, Mapping[str, Any]]
    af: AnchorFacts
    spreads: Mapping[str, tuple[float, ...]]
    phi: float                             # φ — сжатие целиком
    reference_world: str
    regimes: Mapping[str, RegimePath]
    scenarios: Mapping[str, ScenarioPath]
    dn: tuple[float, ...]
    rwa_w: RwaWeights
    cap: CapitalConst
    policy: Policy
    anchor_year: int
    guidance_year: int
    guidance_growth: Mapping[str, float]
    loan_share_drift: float
    funds_share_drift: float
    drift_until: int
    liquid_min: float
    sec_share: float
    wh_to_funds: float
    oa_ratio: float
    ol_ratio: float
    allowance_ratio: float
    fv_share: float
    fv_book: str | None
    c_ref: float
    psi: float
    key_ref: float
    c_bounds: tuple[float, float]
    c_rho: float
    dia: float
    fees_gvw: tuple[float, ...]
    fees_override: Mapping[int, float]     # год → рост (год якоря — рост остатка года gF_rest)
    opex_real: tuple[float, ...]
    ins_gvw: tuple[float, ...]
    noncore_q: Mapping[int, float]         # год → сумма в цены якоря на квартал (год якоря — остаток)
    misc_q: Mapping[tuple[int, int], float]   # (год, квартал) → «прочее» квартала в ценах якоря (М§4.7)
    tau_stat: Mapping[int, float]
    tax_gap: float
    ot_q: int | None
    ot_amount: float
    other_movements: tuple[float, ...]
    t2: tuple[float, ...]
    nci_share: float
    fv_factor: float
    kappa: float
    lag: int
    segment_rel: Mapping[str, float] | None
    coupon_annual: float
    coupon_quarter: int
    hist: Mapping[str, Mapping[int, float]]   # fees, opex (C > 0), ins, ni_sh по q ≤ 0
    hist_bal: Mapping[int, Mapping[str, float]]   # концы кварталов до якоря: bv, loans_ac, iea (balance.history)
    fvoci_duration: float
    fvoci_maturity: float
    fvoci_share: float
    fvoci_tenor: str
    y_tenor0: float
    fvr_on: bool
    fvtpl_share: float
    fvtpl_duration: float
    real_growth: float
    fade: float
    multiple: float
    register: Mapping[Any, float]          # ключ записи реестра → объявленный DPS: год прибыли, а при
    #                                        квартальном календаре — квартал прибыли (то же у двух полей ниже)
    reg_q_by_year: Mapping[Any, int]       # ключ записи → квартал вычета из рег. капитала (реестр)
    pay_q_by_year: Mapping[Any, int]
    rwa0: float
    anchor_state: Mapping[str, float]
    near: tuple[float, ...] = ()           # ближний сдвиг ЧПМ по q = 0…Q (М§3.2)
    misc_shares: Mapping[int, float] = field(default_factory=dict)   # доля квартала h в годовой сумме
    fv_ref: str = ""                       # режим-опора FVC (credit.fv_loans_ref, М§4.6)
    fv_ref_cor: tuple[float, ...] = ()     # путь опоры FVC в базисе движка — по книге до розыгрыша (Book.base)
    phi_assets: float = 0.0                # φ_A — сжатие спредов активов с phi
    phi_liab: float = 0.0                  # φ_L — добавка к стоимости пассивов с phi на единицу X_W,q
    phi_weights: Mapping[str, float] = field(default_factory=dict)   # ω_b книг Φ_A в X_W,q (М§4.4)
    # вторая форма банка (ключи необязательны)
    loan_drift: Mapping[str, Mapping[int, float]] | None = None    # сектор → год → премия роста кредитов (словарь книги)
    funds_drift: Mapping[str, Mapping[int, float]] | None = None   # сегмент → год → премия роста средств клиентов
    funds_drift_q: Mapping[str, Mapping[tuple[int, int], float]] = field(default_factory=dict)
    #                                            сегмент → (год, квартал) → премия квартала: только у траектории с
    #                                            ключами квартала или полугодия (М§4.3); пусто — значение года
    oa_fixed: float = 0.0                  # OA_fixed — прочие активы, постоянные в рублях (М§4.3)
    link_fees: float = 0.0                 # связи с ростом объёма (М§4.7): комиссии,
    link_ins: float = 0.0                  # страхование,
    link_opex: float = 0.0                 # расходы
    link_base: str = ""                    # база объёма (loans | funds | iea); пусто — связей нет
    hist_vol: Mapping[int, float] = field(default_factory=dict)   # A_x, x ≤ 0 — средний остаток базы (факты)
    calendar: QuarterCalendar | None = None    # квартальный календарь дивидендов (М§5.7); None — годовой
    growth: GrowthRule | None = None           # ограничение роста капиталом (М§4.13); None — рост задан
    glide: Mapping[str, tuple[tuple[float, ...], tuple[float, ...]]] = field(default_factory=dict)
    #                                            сценарий → (req*_20, req*_11): требование с глиссадой по q = 0…Q
    kappa_world: str | None = None             # мир-опора κ-добавки (`credit.kappa_reference_world`, М§4.6); None —
    #                                            базовый мир, добавка только вверх
    fade_symmetric: bool = False               # угасание терминала при любом знаке ROE_T − k_T (М§7); False — одностороннее
    t2_from: int | None = None                 # q_χ — квартал ключа доли инструментов (`capital.n20.t2_share`, М§4.11):
    #                                            с него T2 клетки — χ_c × RWA_q; None — ключа нет или enabled: false
    recap: RecapRule | None = None             # докапитализация (М§4.14): квартал решения, окно и порог; None —
    #                                            взносов нет
    recap_discount: float = 0.0                # d — дисконт размещения (М§6.5): параметр оценки, проход его не читает
    oa_delta: tuple[float, ...] | None = None  # ΔOA_q — приращение постоянной части прочих активов к якорю по её пути
    #                                            (`volumes.other_assets_fixed_change`, М§4.3), q = 0…Q; None — пути нет
    lam_f: float | None = None                 # λ_F — доля постоянных частей, растущая за концом сетки (М§7):
    #                                            параметр оценки, проход его не читает; None — ключа нет
    segment_w: Mapping[str, float] | None = None   # структура нормировки сегментной CoR — доли сегментов в кредитах
    #                                            АС, на которых общая CoR равна пути (М§4.6); None — схема выключена
    # восьмой проход (М§4.4, §4.9–§4.11, §7): ключи книги; без ключа — None и нули, прежние строки
    at1_from: int | None = None                # q_α — квартал ключа доли добавочного капитала (`capital.at1_share`): с
    #                                            него AT1 клетки — α_c × RWA_q; None — ключа нет или enabled: false
    at1_spread: float = 0.0                    # s_α — надбавка купона новых выпусков к ключевой ставке мира
    at1_base: float = 0.0                      # B_α — сумма, которую несёт купон якоря (млрд ₽; `anchor` — AT1_0)
    t2p_spread: float | None = None            # π_T2 — надбавка за субординацию к ставке опта (`capital.n20.t2_premium`);
    #                                            None — ключа нет или enabled: false
    t2p_base: float = 0.0                      # B_T2 — база надбавки (млрд ₽; `anchor` — значение траектории T2_0)
    om_ann: float = 0.0                        # OM_ann — прочие движения капитала за концом сетки в год
    #                                            (`valuation.terminal.other_movements`, М§7): параметр оценки, проход
    #                                            его не читает; без ключа и при `none` — ноль
    # девятый проход (М§4.8, §4.9, §7): ключи книги; без ключа — None, прежние строки
    tax_rule: TaxRule | None = None            # разрыв налога по правилу (`tax.structure`); с ним `tax_gap` — «не число»:
    #                                            `tax.effective_gap` не читается
    cpn_rule: AnchorCoupon | None = None       # купон якоря по ставке своего мира (`capital.at1_coupon`); с ним
    #                                            `coupon_annual` — «не число»: сумма слота фактов не читается


SEGMENT_SHARE = "credit.segment_relative.corporate_share_ref"   # доля юрлиц структуры нормировки (М§4.6); нет — якорь


def segment_weights(books: Mapping[str, Any], roles: BookRoles, af: AnchorFacts,
                    share: float | None = None) -> dict[str, float]:
    """Структура нормировки сегментной CoR (М§4.6): доли сегментов в кредитах АС, на которых общая CoR клетки равна
    пути режима. `share` — ключ книги `credit.segment_relative.corporate_share_ref` (доля юрлиц; у физлиц — остаток
    до единицы): его пишет перенос якоря долей прежнего якоря (М§15.2 п. 3). Без ключа — доли якоря `af` (правило
    образца)."""
    if share is not None:
        return {"corporate": float(share), "retail": 1.0 - float(share)}
    w_ac = {"corporate": 0.0, "retail": 0.0}
    for b in roles.loans:
        w_ac[books[b]["cor_segment"]] += af.balances[b] - (af.fv_loans if b == af.fv_book else 0.0)
    tot = sum(w_ac.values())
    return {s: w_ac[s] / tot for s in w_ac}


def _series(traj: Any, tl: Timeline) -> tuple[float, ...]:
    t = Trajectory(traj)
    return tuple(t.value(*parse_period(tl.period(q))) for q in range(tl.Q + 1))


def t2_share_from(book: "Book", tl: Timeline) -> int | None:
    """q_χ — квартал ключа доли инструментов в RWA своей клетки (`capital.n20.t2_share`, М§4.11): с него T2 клетки —
    χ_c × RWA_c,q. Ключа нет или `enabled: false` — None: траектория во всех кварталах (поведение образца)."""
    node = book.opt("capital.n20.t2_share")
    if not isinstance(node, Mapping) or node.get("enabled") is not True:
        return None
    return tl.index(str(node["from"]))


AT1_SHARE = "capital.at1_share"              # доля добавочного капитала в RWA своей клетки (М§4.11, прил. A № 31)
T2_PREMIUM = "capital.n20.t2_premium"        # надбавка за субординацию дополнительного капитала (М§4.11, прил. A № 32)
ANCHOR_BASE = "anchor"                       # база ключа — факт якоря


def at1_share(book: "Book", tl: Timeline, at1_0: float) -> tuple[int, float, float] | None:
    """(q_α, s_α, B_α) — ключ доли добавочного капитала в RWA своей клетки (`capital.at1_share`, М§4.9–§4.11): с
    квартала q_α AT1 клетки — α_c × RWA_c,q; купон сверх базы — по ставке `key_W,q + s_α` на AT1 сверх B_α (`anchor` —
    факт якоря `at1_0`). Ключа нет или `enabled: false` — None: AT1 — факт якоря, купон — купон якоря (образец)."""
    node = book.opt(AT1_SHARE)
    if not isinstance(node, Mapping) or node.get("enabled") is not True:
        return None
    base = node["base"]
    return (tl.index(str(node["from"])), float(node["spread"]),
            at1_0 if base == ANCHOR_BASE else float(base))


def t2_premium(book: "Book", t2_0: float) -> tuple[float, float] | None:
    """(π_T2, B_T2) — ключ надбавки за субординацию дополнительного капитала (`capital.n20.t2_premium`, М§4.4, §4.11):
    надбавка к ставке опта на T2 клетки сверх базы (`anchor` — значение траектории `capital.n20.t2` в квартале якоря
    `t2_0`). Ключа нет или `enabled: false` — None: надбавки нет (образец)."""
    node = book.opt(T2_PREMIUM)
    if not isinstance(node, Mapping) or node.get("enabled") is not True:
        return None
    base = node["base"]
    return float(node["spread"]), t2_0 if base == ANCHOR_BASE else float(base)


AT1_COUPON = "capital.at1_coupon"            # купон якоря по ставке своего мира (М§4.9, прил. A № 35)


class AnchorCoupon(NamedTuple):
    """Ключ купона добавочного капитала якоря по ставке своего мира `capital.at1_coupon` (М§4.9): годовой купон выпусков
    с постоянной ставкой Cfix, сумма плавающих выпусков Cflt и их средний спред к ключевой s_flt (взвешенный суммами)."""
    fixed: float
    floating: float
    spread: float


def at1_coupon(book: "Book") -> AnchorCoupon | None:
    """Ключ купона якоря по ставке своего мира (`capital.at1_coupon`, М§4.9); ключа нет или `enabled: false` — None:
    купон якоря — слот фактов `at1.coupon_annual` (поведение образца). С ключом сумма слота не читается."""
    node = book.opt(AT1_COUPON)
    if not isinstance(node, Mapping) or node.get("enabled") is not True:
        return None
    return AnchorCoupon(fixed=float(node["fixed"]), floating=float(node["floating"]), spread=float(node["spread"]))


def anchor_coupon(rule: AnchorCoupon, key: Sequence[float], q: int) -> float:
    """Купон якоря квартала купона q (М§4.9): `Cfix + Cflt × (k̄_q + s_flt)`, k̄_q — средняя ключевая своего мира `key`
    (по q = 0…Q) за четыре квартала, которые кончаются кварталом q; кварталы не позже якоря берут ключевую квартала
    якоря key_W,0 (за концом сетки — ключевую квартала Q)."""
    last = len(key) - 1
    kbar = sum(key[min(max(q - j, 0), last)] for j in range(YEAR_QUARTERS)) / YEAR_QUARTERS
    return rule.fixed + rule.floating * (kbar + rule.spread)


def terminal_anchor_coupon(rule: AnchorCoupon, key_q: float) -> float:
    """Купон якоря года T + 1 (М§7, §4.9): `Cfix + Cflt × (key_W,Q + s_flt)` — ставка последнего квартала сетки."""
    return rule.fixed + rule.floating * (key_q + rule.spread)


def _drift(value: Any, years: range) -> tuple[float, dict[str, dict[int, float]] | None]:
    """Премия роста к сектору (М§4.3): число — одна на все книги (прежняя форма); словарь — траектория на
    ключ набора, значение года — `year_value`."""
    if isinstance(value, Mapping):
        return 0.0, {str(k): {y: Trajectory(v).year_value(y) for y in years} for k, v in value.items()}
    return float(value), None


def _drift_quarters(value: Any) -> dict[str, dict[tuple[int, int], float]]:
    """Премия роста средств клиентов, заданная ключом квартала или полугодия (М§4.3): сегмент → (год, номер
    квартала) → значение траектории в этом квартале (правило М§0.4: ключ квартала, затем ключ полугодия).
    Кварталы без своего ключа и траектории без таких ключей сюда не входят — их премию задаёт значение года,
    как у образца: число и словарь с ключами лет читаются прежней строкой."""
    out: dict[str, dict[tuple[int, int], float]] = {}
    if not isinstance(value, Mapping):
        return out
    for name, traj in value.items():
        t = Trajectory(traj)
        keyed = set(t.quarters) | {(y, n) for y, h in t.halves for n in ((1, 2) if h == 1 else (3, 4))}
        if keyed:
            out[str(name)] = {(y, n): t.value(y, n) for y, n in sorted(keyed)}
    return out


LINK_BASES = ("loans", "funds", "iea")       # volumes.link_base — он же узел конца квартала в balance.history
IEA_BASE = LINK_BASES[2]                     # база, у которой квартал фактов — в определении клетки (М§4.7)
VOLUME_LINKS = (("fees", "fees.volume_link"), ("ins", "other.insurance_volume_link"), ("opex", "opex.volume_link"))
DIVIDEND_HORIZON = -11                       # строка истории дивидендов с суммой без дня решения и кварталом прибыли
#                                              не раньше этого квартала (решение могло прийтись на окно базы) — отказ


def volume_links(book: "Book") -> dict[str, float]:
    """Связи комиссий, страхования и расходов с ростом объёма (М§4.7); нет ключа — ноль."""
    return {k: float(book.opt(path, 0.0)) for k, path in VOLUME_LINKS}


def link_base_of(book: "Book") -> str:
    """База объёма, которую читает ядро (М§4.7): `volumes.link_base` (умолчание — кредиты), когда хотя бы одна связь
    не ноль; без связей — пусто (база не читается)."""
    if not any(volume_links(book).values()):
        return ""
    return str(book.opt("volumes.link_base", LINK_BASES[0]))


def _profit_quarter(row: Mapping[str, Any], tl: Timeline) -> int | None:
    """Квартал прибыли строки истории дивидендов на линейке сетки: `period`, без него — четвёртый квартал `year`."""
    period = _plain_node(row.get("period"))
    if period:
        return tl.index(str(period))
    year = _plain_node(row.get("year"))
    return None if year is None else tl.index(period_str(int(year), 4))


def _plain_node(x: Any) -> Any:
    return x.get("v") if isinstance(x, Mapping) else x


def decided_dividends(facts: "Facts", tl: Timeline) -> dict[int, float]:
    """Div_x, x = −3…0 (М§4.7): дивиденды, решённые в квартале x, — сумма `pool_all_classes` (без поля —
    `pool_declared`) строк `dividends.history` и `dividends.history_before` с `decided_date` в квартале x: всех
    категорий акций, вычтенные из `bv_common` при решении. Отказ `FactsError`: строка с решением в окне без суммы;
    строка с суммой больше нуля без дня решения, чей квартал прибыли не раньше x = −11 (`DIVIDEND_HORIZON`) или не
    назван."""
    out = {x: 0.0 for x in range(-3, 1)}
    file = facts.file("dividends")
    for key in ("history", "history_before"):
        for i, row in enumerate(file.get(key) or []):
            if not isinstance(row, Mapping):
                continue
            where = f"dividends.{key}.{i}"
            amount = _plain_node(row.get("pool_all_classes"))
            if amount is None:
                amount = _plain_node(row.get("pool_declared"))
            day = _plain_node(row.get("decided_date"))
            if day is None:
                if amount is not None and float(amount) > 0:
                    profit = _profit_quarter(row, tl)
                    if profit is None or profit >= DIVIDEND_HORIZON:
                        raise FactsError(
                            f"{where}: сумма {float(amount):g} без дня решения (decided_date)"
                            + ("" if profit is None else f", квартал прибыли {tl.period(profit)}")
                            + " — решение могло прийтись на окно базы объёма iea, прирост капитала квартала фактов не "
                            "определён (М§4.7)")
                continue
            try:
                x = tl.q_of_date(to_date(day))
            except (TypeError, ValueError) as exc:
                raise FactsError(f"{where}.decided_date = {day!r}: {exc}") from None
            if not -3 <= x <= 0:
                continue
            if amount is None:
                raise FactsError(f"{where}: решение {day} в квартале {tl.period(x)} без суммы (pool_all_classes и "
                                 "pool_declared не заданы) — прирост капитала квартала фактов не определён (М§4.7)")
            out[x] += float(amount)
    return out


def equity_growth(hist_bal: Mapping[int, Mapping[str, float]], anchor_bv: float, dividends: Mapping[int, float],
                  tl: Timeline) -> dict[int, float]:
    """ΔE_x = bv[x] − bv[x−1] + Div_x, x = −3…0 (М§4.7): прирост капитала акционеров обыкновенных квартала фактов
    до дивидендов — `bv_common` истории баланса (x ≤ −1) и капитал якоря (x = 0). Нет конца — FactsError."""
    bv = {0: anchor_bv}
    for x in range(-4, 0):
        value = hist_bal.get(x, {}).get("bv")
        if value is None:
            raise FactsError(f"balance.history: нет bv_common на конец {tl.period(x)} — база объёма iea квартала фактов "
                             "не определена (связь с объёмом, М§4.7)")
        bv[x] = value
    return {x: bv[x] - bv[x - 1] + dividends[x] for x in range(-3, 1)}


def _volume_history(base: str, hist_bal: Mapping[int, Mapping[str, float]], anchor_end: float,
                    tl: Timeline, growth: Mapping[int, float] | None = None) -> dict[int, float]:
    """A_x, x = −3…0: средний остаток базы объёма за квартал до сетки — полусумма концов кварталов фактов
    (`balance.history`; конец якоря — остатки якоря). Нет конца — FactsError (М§4.7). `growth` — ΔE_x базы `iea`:
    квартал фактов в определении клетки, полусумма концов минус половина прироста капитала до дивидендов (конец
    балансирующих книг у клетки — предварительный, §4.10)."""
    ends = {0: anchor_end}
    for x in range(-4, 0):
        value = hist_bal.get(x, {}).get(base)
        if value is None:
            raise FactsError(f"balance.history: нет {base} на конец {tl.period(x)} — рост объёма г/г не определён "
                             "(связь с объёмом, М§4.7)")
        ends[x] = value
    if growth is None:
        return {x: (ends[x - 1] + ends[x]) / 2 for x in range(-3, 1)}
    return {x: (ends[x - 1] + ends[x] - growth[x]) / 2 for x in range(-3, 1)}


def _year_sum_table(traj: Any, years: range) -> dict[int, float]:
    t = Trajectory(traj)
    return {y: sum(t.value(y, n) for n in (1, 2, 3, 4)) / 4 for y in years}


def prepare(book: "Book", facts: "Facts", timeline: Timeline, bridge: Bridge,
            transmission: "Transmission", register: tuple = ()) -> Prepared:
    books = book.get("nii.books")
    roles = book_roles(books)
    af = anchor_facts(facts, books)
    tl = timeline
    ay = tl.anchor_year
    years = range(ay - 1, tl.last_year + 1)
    if int(book.get("noncore.price_base_year")) != ay:
        raise BookError("noncore.price_base_year: цены книги — цены года якоря (М§4.7)")
    spreads = spread_paths(book, tl, transmission.sigma0, transmission.sigma0_liab)
    regimes = {}
    for r in book.get("regimes.ids"):
        spec = book.get(f"regimes.{r}")
        adj = Trajectory(spec["loan_growth_adj"])
        one = spec.get("one_off_loss")
        one_q = tl.index(one["period"]) if one else None
        offset = spec.get("shock_year_offset")
        regimes[r] = RegimePath(
            regime=r, cor_engine=regime_cor_engine(book, bridge, r, tl),
            nim_shift=_series(spec["nim_shift"], tl),
            loan_adj={y: adj.year_value(y) for y in years},
            override={int(k): float(v) for k, v in (spec.get("loan_growth_override") or {}).items()},
            one_off_q=one_q if one_q is not None and 1 <= one_q <= tl.Q else None,
            one_off_amount=float(one["amount"]) if one else 0.0,
            shock_year=None if offset is None else ay + int(offset),
            rwa_mult=regime_rwa_mult(book, r, tl))
    scenarios = {s: scenario_path(book, s, tl) for s in book.get("capital.reg_scenarios.ids")}
    rw = rwa_weights(book, roles)
    rwa0 = rwa_anchor(rw, af)
    cap = capital_const(book, af, rwa0)
    policy = make_policy(book, af.n_iss, af.n_out)
    quarterly = policy.rule is not None
    calendar = None
    if quarterly:                           # открытые кварталы прибыли по кварталам клетки, состояние якоря (М§5.7)
        calendar = quarter_calendar(policy, facts, tl, register, to_date(book.get("meta.facts_date")),
                                    af.dividends_payable)
    # История по кварталам до якоря (q ≤ 0): база «к тому же кварталу» и прибыль.
    hist: dict[str, dict[int, float]] = {"fees": {}, "opex": {}, "ins": {}, "ni_sh": {}, "noncore": {},
                                         "misc": {}, "llp": {}, "nii": {}, "pbt": {}, "tax": {}, "ni": {}}
    for per, row in af.pnl.items():
        q = tl.index(per)
        if q > 0:
            continue
        for name, key, sign in (("fees", "fees_net", 1), ("opex", "opex", -1), ("ins", "insurance_net", 1),
                                ("ni_sh", "ni_shareholders", 1), ("noncore", "noncore_net", 1),
                                ("misc", "misc_net", 1), ("llp", "llp_debt_fa", -1), ("nii", "nii", 1),
                                ("pbt", "pbt", 1), ("tax", "tax", -1), ("ni", "ni", 1)):
            if row.get(key) is not None:
                hist[name][q] = sign * row[key]
    # Концы кварталов до якоря (годовые отношения года якоря — средние пяти концов, М§0.3).
    hist_bal: dict[int, dict[str, float]] = {}
    bal_hist = facts.file("balance").get("history")
    if isinstance(bal_hist, list):          # запись INTERFACES §3.2: [{period, …}]; словарь по периодам — тоже
        bal_hist = {str(r["period"]): r for r in bal_hist if isinstance(r, Mapping) and "period" in r}
    if isinstance(bal_hist, Mapping):
        for per, row in bal_hist.items():
            q = tl.index(str(per))
            if q >= 0 or not isinstance(row, Mapping):
                continue
            vals = {}
            for key, name in (("bv_common", "bv"), ("loans_ac_gross", "loans_ac"), ("iea", "iea"),
                              ("loans", "loans"), ("funds", "funds")):
                node = row.get(key)
                if isinstance(node, Mapping) and node.get("v") is not None:
                    vals[name] = float(node["v"])
            hist_bal[q] = vals
    # Год якоря: факт отчётных кварталов и остаток года (М§0.3).
    fact_qs = [q for q in tl.quarters_of_year(ay) if q <= 0]
    rest_qs = [q for q in tl.quarters_of_year(ay) if q >= 1]

    def need_hist(name: str, qs: list[int]) -> float:
        missing = [tl.period(q) for q in qs if q not in hist[name]]
        if missing:
            raise FactsError(f"факты pnl_quarterly: нет {name} за {', '.join(missing)} (М§0.3)")
        return sum(hist[name][q] for q in qs)

    for q in range(1, 5):
        for name in ("fees", "opex", "ins"):
            if q - 4 not in hist[name]:
                raise FactsError(f"факты pnl_quarterly: нет {name} за {tl.period(q - 4)} "
                                "(база «к тому же кварталу», М§0.3)")
    fees_override = {int(k): float(v) for k, v in book.get("fees.growth_override").items()}
    if ay in fees_override and rest_qs:
        prev = need_hist("fees", tl.quarters_of_year(ay - 1))
        fact = need_hist("fees", fact_qs)
        base = sum(hist["fees"][q - 4] for q in rest_qs)
        fees_override[ay] = (prev * (1 + fees_override[ay]) - fact) / base - 1
    noncore_tab = _year_sum_table(book.get("noncore.result_real"), years)
    misc_tab = _year_sum_table(book.get("other.misc_net_real"), years)
    noncore_q = {y: v / 4 for y, v in noncore_tab.items()}
    shares = {h: float(book.get(f"other.misc_quarter_shares.{h}")) for h in (1, 2, 3, 4)}
    misc_q = {(y, h): v * shares[h] for y, v in misc_tab.items() for h in (1, 2, 3, 4)}
    if rest_qs:             # остатком года закрывается только непрофильный результат (М§0.3)
        noncore_q[ay] = (noncore_tab[ay] - need_hist("noncore", fact_qs)) / len(rest_qs)
    stat = Trajectory(book.get("tax.statutory"))
    tau_stat = {y: sum(stat.value(y, n) for n in (1, 2, 3, 4)) / 4 for y in years}
    if calendar is not None:                # окно базы первого открытого квартала прибыли уходит раньше якоря
        for y in range(tl.year(calendar.p_last + 2 - policy.window), years[0]):
            tau_stat[y] = sum(stat.value(y, n) for n in (1, 2, 3, 4)) / 4
    ot = book.get("tax.one_off")
    ot_q = tl.index(period_str(int(ot["year"]), 1))
    seg = seg_w = None
    if book.get("credit.segment_relative.enabled"):
        seg = {"corporate": float(book.get("credit.segment_relative.corporate")),
               "retail": float(book.get("credit.segment_relative.retail"))}
        seg_w = segment_weights(books, roles, af, book.opt(SEGMENT_SHARE))
    tenor = str(book.get("oci.fvoci_tenor"))
    node = tenor.split("_")[1].rstrip("y")
    fv_book = af.fv_book
    fv_share = float(books[fv_book]["fv_share"]) if fv_book and "fv_share" in books[fv_book] else 0.0
    reg_q, pay_q = {}, {}
    for rec in register:
        if getattr(rec, "status", None) not in ("declared", "paid"):
            continue
        if rec.record_date is not None:
            reg_q[record_key(rec, quarterly)] = tl.q_of_date(rec.record_date)
        if rec.pay_date is not None:
            pay_q[record_key(rec, quarterly)] = tl.q_of_date(rec.pay_date)
    anchor_state = {"loans": sum(af.balances[b] for b in roles.loans), "rwa0": rwa0}
    fvr_on = bool(book.get("other.fvtpl_bond_reval"))
    fv_ref = str(book.get("credit.fv_loans_ref"))
    if fv_ref not in regimes:
        raise BookError(f"credit.fv_loans_ref = {fv_ref!r}: нет такого режима (М§4.6)")
    ref_book = book if book.base is None else book.base      # опора FVC — путь нормы книги до розыгрыша (М§4.6)
    fv_ref_cor = regime_cor_engine(ref_book, bridge, fv_ref, tl)
    loan_d, loan_drift = _drift(book.get("volumes.loan_share_drift"), years)
    funds_d, funds_drift = _drift(book.get("volumes.funds_share_drift"), years)
    funds_drift_q = _drift_quarters(book.get("volumes.funds_share_drift"))
    growth = growth_rule(book)
    if growth is not None and calendar is None:
        raise BookError("capital.growth_constraint.enabled: рост по капиталу — только при квартальном календаре "
                        "дивидендов (М§4.13)")
    recap = recap_rule(book)
    if recap is not None and (calendar is not None or growth is not None):
        raise BookError("capital.recapitalization.enabled: докапитализация — только при годовом календаре "
                        "дивидендов и выключенном ограничении роста (М§4.14)")
    glide = {} if growth is None else {
        s: (glide_path(sp.req20, growth.lookahead, growth.glide), glide_path(sp.req11, growth.lookahead, growth.glide))
        for s, sp in scenarios.items()}
    t2_path = _series(book.get("capital.n20.t2"), tl)
    a1 = at1_share(book, tl, af.at1)             # доля добавочного капитала (М§4.11); None — ключа нет
    t2p = t2_premium(book, t2_path[0])           # надбавка за субординацию (М§4.11); None — ключа нет
    tax_rule = tax_structure(book)               # разрыв налога по правилу (М§4.8); None — число tax.effective_gap
    cpn_rule = at1_coupon(book)                  # купон якоря по ставке своего мира (М§4.9); None — слот фактов
    links = volume_links(book)
    link_base, hist_vol = "", {}
    if any(links.values()):                 # база объёма читается, когда хотя бы одна связь не ноль (М§4.7)
        link_base = str(book.opt("volumes.link_base", LINK_BASES[0]))
        anchor_end = {"loans": anchor_state["loans"], "funds": sum(af.balances[b] for b in roles.funds),
                      "iea": sum(af.balances[b] for b in roles.assets)}[link_base]
        delta_e = None
        if link_base == IEA_BASE:           # квартал фактов — в определении клетки: минус половина ΔE_x (М§4.7)
            delta_e = equity_growth(hist_bal, af.bv, decided_dividends(facts, tl), tl)
        hist_vol = _volume_history(link_base, hist_bal, anchor_end, tl, delta_e)
    return Prepared(
        timeline=tl, roles=roles, books=books, af=af, spreads=spreads, phi=transmission.phi,
        reference_world=transmission.reference_world or str(book.get("nii.transmission.reference_world")),
        regimes=regimes, scenarios=scenarios, dn=density_index(book, tl), rwa_w=rw, cap=cap,
        policy=policy, anchor_year=ay, guidance_year=int(book.get("volumes.guidance_year")),
        guidance_growth={k: float(v) for k, v in book.get("volumes.guidance_growth").items()},
        loan_share_drift=loan_d, funds_share_drift=funds_d, loan_drift=loan_drift, funds_drift=funds_drift,
        funds_drift_q=funds_drift_q,
        oa_fixed=float(book.opt("volumes.other_assets_fixed", 0.0)),
        link_fees=links["fees"], link_ins=links["ins"], link_opex=links["opex"], link_base=link_base,
        hist_vol=hist_vol,
        drift_until=int(book.get("volumes.share_drift_until")),
        liquid_min=float(book.get("volumes.liquid_min_share")),
        sec_share=float(book.get("volumes.securities_share_of_liquid")),
        wh_to_funds=float(book.get("volumes.wholesale_to_funds")),
        oa_ratio=float(book.get("volumes.other_assets_to_loans")),
        ol_ratio=float(book.get("volumes.other_liabilities_to_loans")),
        allowance_ratio=float(book.get("credit.allowance_ratio")),
        fv_share=fv_share, fv_book=fv_book,
        c_ref=float(book.get("nii.retail_current_share.c_ref")),
        psi=float(book.get("nii.retail_current_share.psi")),
        key_ref=float(book.get("nii.retail_current_share.key_ref")),
        c_bounds=tuple(float(x) for x in book.get("nii.retail_current_share.bounds")),
        c_rho=float(book.get("nii.retail_current_share.rho")),
        dia=float(book.get("nii.dia_rate")),
        fees_gvw=_series(book.get("fees.growth_vs_wages"), tl),
        fees_override=fees_override,
        opex_real=_series(book.get("opex.real_growth"), tl),
        ins_gvw=_series(book.get("other.insurance_growth_vs_wages"), tl),
        noncore_q=noncore_q, misc_q=misc_q, tau_stat=tau_stat,
        # с ключом разрыва налога по правилу число разрыва не читается (М§0.1, прил. A № 34): «не число»
        tax_gap=float(book.get("tax.effective_gap")) if tax_rule is None else float("nan"),
        tax_rule=tax_rule, cpn_rule=cpn_rule,
        ot_q=ot_q if 1 <= ot_q <= tl.Q else None,
        ot_amount=float(ot["prob"]) * float(ot["amount"]),
        other_movements=_series(book.get("equity.other_movements"), tl),
        t2=t2_path, t2_from=t2_share_from(book, tl),
        at1_from=None if a1 is None else a1[0], at1_spread=0.0 if a1 is None else a1[1],
        at1_base=0.0 if a1 is None else a1[2],
        t2p_spread=None if t2p is None else t2p[0], t2p_base=0.0 if t2p is None else t2p[1],
        om_ann=terminal_other_movements(book, tl.last_year),
        nci_share=float(book.get("pnl.nci_share")),
        fv_factor=float(book.get("credit.fv_loans_factor")),
        kappa=float(book.get("credit.kappa")), lag=int(book.get("credit.real_rate_lag_q")),
        # с ключом купона якоря сумма слота фактов не читается (М§0.1, прил. A № 35): «не число»; квартал слота — читается
        segment_rel=seg, coupon_annual=af.coupon_annual if cpn_rule is None else float("nan"),
        coupon_quarter=af.coupon_quarter,
        hist={k: dict(v) for k, v in hist.items()}, hist_bal=hist_bal,
        fvoci_duration=float(book.get("oci.fvoci_duration")),
        fvoci_maturity=float(book.get("oci.fvoci_maturity")),
        fvoci_share=float(book.get("oci.fvoci_share")), fvoci_tenor=tenor,
        y_tenor0=af.ofz_anchor[node], fvr_on=fvr_on,
        fvtpl_share=float(book.get("oci.fvtpl_bond_share")),
        fvtpl_duration=float(book.get("oci.fvtpl_bond_duration")) if fvr_on else 0.0,
        real_growth=float(book.get("valuation.terminal.real_growth")),
        fade=float(book.get("valuation.terminal.fade")),
        multiple=float(book.get("valuation.terminal.excess_capital_multiple")),
        register=register_dps(register, quarterly), reg_q_by_year=reg_q, pay_q_by_year=pay_q, calendar=calendar,
        growth=growth, glide=glide, kappa_world=kappa_world(book), fade_symmetric=fade_symmetric(book),
        recap=recap, recap_discount=price_discount(book), segment_w=seg_w,
        oa_delta=fixed_change(book, tl), lam_f=fixed_growth_share(book),
        rwa0=rwa0, anchor_state=anchor_state,
        near=_series(book.get("regimes.near_nim_shift"), tl), misc_shares=shares,
        fv_ref=fv_ref, fv_ref_cor=fv_ref_cor, phi_assets=transmission.phi_assets,
        phi_liab=transmission.phi_liab, phi_weights=dict(transmission.phi_weights),
    )


# ------------------------------------------------------------------ состояние


class State:
    """Состояние клетки на конец квартала (копируется для пробного прохода)."""

    __slots__ = ("E", "rate", "FR", "c", "AL", "OA", "OL", "DP", "BV", "R", "D", "pay", "reg",
                 "guid", "wh_extra", "q", "t2s", "a1s", "at1", "t2l")

    def clone(self) -> "State":
        s = State.__new__(State)
        s.E, s.rate = dict(self.E), dict(self.rate)
        s.FR, s.c, s.AL, s.OA, s.OL = self.FR, self.c, self.AL, self.OA, self.OL
        s.DP, s.BV, s.R, s.D = self.DP, self.BV, self.R, self.D
        s.pay, s.reg = dict(self.pay), list(self.reg)
        s.guid, s.wh_extra, s.q = dict(self.guid), self.wh_extra, self.q
        s.t2s = self.t2s                    # χ_c — доля инструментов клетки (М§4.11); до квартала q_χ − 1 — None
        # α_c — доля добавочного капитала клетки (до квартала q_α − 1 — None); AT1 и T2 конца квартала (М§4.9–§4.11)
        s.a1s, s.at1, s.t2l = self.a1s, self.at1, self.t2l
        return s


def initial_state(p: Prepared) -> State:
    af, roles = p.af, p.roles
    s = State.__new__(State)
    s.E = {b: af.balances[b] for b in roles.names}
    s.rate = {b: af.rates[b] for b in roles.names}
    s.FR = sum(af.balances[b] for b in roles.retail)
    s.c = af.balances[roles.retail[0]] / s.FR
    s.AL, s.OA, s.OL = af.allowance, af.other_assets, af.other_liabilities
    s.DP, s.BV, s.R, s.D = af.dividends_payable, af.bv, af.fvoci_reserve, 0.0
    s.pay, s.reg, s.guid, s.wh_extra, s.q = {}, [], {}, 0.0, 0
    # доля инструментов (М§4.11): при q_χ = 1 её задаёт якорь — T2_0 / RWA_0, одна у всех клеток; иначе — записанный
    # шаг квартала q_χ − 1 (`_Cell.step`)
    s.t2s = p.t2[0] / p.rwa0 if p.t2_from == 1 else None
    # доля добавочного капитала (М§4.11): при q_α = 1 — доля якоря AT1_0 / RWA_0, одна у всех клеток; иначе — записанный
    # шаг квартала q_α − 1. AT1 и T2 конца квартала якоря — база выпуска, купона сверх базы и надбавки (М§4.9–§4.11)
    s.a1s = af.at1 / p.rwa0 if p.at1_from == 1 else None
    s.at1, s.t2l = af.at1, p.t2[0]
    tl, pol = p.timeline, p.policy
    if p.calendar is not None:
        # квартальный календарь (М§5.7.4): в очереди — только объявленная часть остатка; остальное —
        # постоянное обязательство: не выплачивается и в регуляторный капитал не возвращается
        for pq, rq, amount in p.calendar.payable:
            s.pay[pq] = s.pay.get(pq, 0.0) + amount
            if rq >= 1:
                s.reg.append((0, rq, amount))
        return s
    if af.dividends_payable and af.dividends_payable_year is not None:
        y = af.dividends_payable_year
        pq = p.pay_q_by_year.get(y, tl.index(period_str(y + 1, pol.pay_quarter)))
        rq = p.reg_q_by_year.get(y, tl.index(period_str(y + 1, pol.reg_quarter)))
        s.pay[max(1, pq)] = s.pay.get(max(1, pq), 0.0) + af.dividends_payable
        if rq >= 1:
            s.reg.append((0, rq, af.dividends_payable))
    return s


def dpreg_at(reg: list, q: int) -> float:
    """DPreg на конец q: решено к кварталу q включительно, не вычтено из регуляторного капитала до квартала
    вычета (М§4.11). Шаг держит в очереди состояния только то, что ещё не вычтено (квартал вычета позже
    квартала шага): вычтенное в сумму уже не входит."""
    return sum([a for (dq, rq, a) in reg if dq <= q < rq])


# ------------------------------------------------------------------ результат клетки


@dataclass(frozen=True)
class CellResult:
    world: str
    regime: str
    scenario: str
    quarters: Mapping[str, tuple[float | None, ...]]   # ряды по кварталам 0..Q
    annual: Mapping[str, tuple[float | None, ...]]     # по годам якоря … last_period
    dps: Mapping[int, float]               # год прибыли → DPS (₽, не округлён)
    v_ri: float
    v_ddm: float
    bv_v: float
    x_t: float
    roe_t: float
    k_t: float
    g_t: float
    tv_ri: float
    terminal_share: float
    n20_min: float
    n11_min: float
    gap_period: str | None
    flags: frozenset[str]
    # сверх договора INTERFACES §4.3 (только добавление)
    years: tuple[int, ...] = ()
    tv_ddm: float = 0.0
    pv_ri_explicit: float = 0.0
    pv_terminal: float = 0.0
    roe_t_raw: float = 0.0
    g_capped: bool = False
    bv_star: float = 0.0
    decisions: tuple[Decision, ...] = ()
    dps_policy: Mapping[int, float] = field(default_factory=dict)
    ci_q0: float = 0.0
    n11_star: float = 0.0
    real_rate: float = 0.0
    y_x: float = 0.0                       # доход на избыток, вычтенный из терминального года (М§7)
    la_headroom: float = 0.0               # HLA_Q — запас балансирующих активов над минимумом на конце Q
    books: Mapping[str, Mapping[str, tuple[float | None, ...]]] = field(default_factory=dict)
    # книга → {"rate": ставка квартала, "avg": средний остаток, "balance": остаток на конец} по q = 0…Q
    # квартальный календарь дивидендов (М§5.7.5); при годовом — пусто
    dps_q: Mapping[str, float] = field(default_factory=dict)          # квартал прибыли → DPS решения клетки
    dps_policy_q: Mapping[str, float] = field(default_factory=dict)   # квартал прибыли → пул политики / N_iss
    # рост кредитных книг по годам клетки (`GROWTH_FIELDS`, М§4.13.3): потенциальный и фактический рост суммы
    # кредитных книг за год, доля урезанного на конец года, навёрстанное за год, наименьшая λ* года
    growth: Mapping[str, tuple[float | None, ...]] = field(default_factory=dict)
    solver: tuple[tuple[str, float], ...] = ()     # кварталы флага growth_solver: (период, невязка норматива)
    pv_ri_q: tuple[float, ...] = ()        # RI_q × DF_v(τ_q) по q = 0…Q (до квартала даты оценки — 0), млрд ₽
    # докапитализация (М§4.14, §6.5–§6.6); у книги без неё — нули и пусто. `bv_v` у книги с докапитализацией —
    # капитал на дату оценки на нынешний делитель: без взносов кварталов, закрытых к дате оценки (`c_v`)
    c_v: float = 0.0                       # C_v — взносы кварталов, закрытых к дате оценки
    pvd: float = 0.0                       # PVD — приведённая цена размывания клетки (уже вычтена из v_ri и v_ddm)
    p_t: float = 0.0                       # P_T — приведённая на T капиталонейтральная выплата (М§7)
    dc_t: float = 0.0                      # DC_T — цена размывания терминала
    pv_rec: float = 0.0                    # приведённая сумма взносов явного участка (закрытые кварталы — без дисконта)
    pv_rec_terminal: float = 0.0           # приведённая сумма отрицательных распределений терминала
    recaps: tuple[RecapDecision, ...] = ()     # решения о взносе по кварталам решения; у лёгкой клетки — пусто
    pv_tv_ddm: float | None = None         # DF_v(τ_Q) × (TV_DDM − DC_T) — приведённый терминал формы DDM у книги с
    #                                        докапитализацией (доля терминала слоя, М§6.4); без неё — None
    n_base: float | None = None            # N_base — база делителя (М§8.4) у полной клетки книги с докапитализацией
    shares: SharePath | None = None        # путь числа акций клетки (М§6.6); только у полной клетки
    terminal_fixed: Mapping[str, Any] | None = None   # блок постоянных частей терминала у книги с ключом λ_F (М§7):
    #                                                   lam_f, f_a, r_f, c, kappa, binding, f_k, d_f, i_f,
    #                                                   business_capital; без ключа — None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.world, self.regime, self.scenario)

    @property
    def label(self) -> str:
        return f"{self.world}/{self.regime}/{self.scenario}"


# ------------------------------------------------------------------ квартальный проход


def growth_share(g_min: float, g_full: float, lam_min: float) -> float:
    """λ*_j — доля прироста, при которой невязка условия роста норматива j равна нулю (М§4.13.2 п. 3): по двум
    оценкам шага, при наименьшей доле (`g_min`) и при полном росте (`g_full`); условие почти аффинно по доле.
    Норматив не связывает (`g_full ≥ 0`) или урезание роста его не поправляет — единица."""
    if g_full >= 0 or g_min - g_full <= SLOPE_TOL:
        return 1.0
    return lam_min + (1 - lam_min) * g_min / (g_min - g_full)


class _Cell:
    """Одна клетка: ряды мира, режима и сценария + шаг квартала."""

    def __init__(self, ctx: "RunContext", world: str, regime: str, scenario: str, *,
                 preliminary: bool = False, shared: dict | None = None):
        """`shared` — общее для клеток одного прогона (словарь вызывающего, один на прогон): годы и номера
        кварталов сетки; по миру — κ-добавка (к миру-опоре книги), разность опорных ставок X_W,q и ставки книг по кварталам (от
        режима, сценария, объёмов и дивидендов они не зависят); по миру и режиму — потенциальные множители роста
        кредитных книг. Без него клетка считает всё сама."""
        p: Prepared = ctx.prep
        self.p, self.tl = p, p.timeline
        self.w: WorldPath = ctx.worlds[world]
        self.wh: WorldPath = ctx.worlds[p.reference_world]
        self.rg: RegimePath = p.regimes[regime]
        self.sc: ScenarioPath = p.scenarios[scenario]
        self.world, self.regime, self.scenario = world, regime, scenario
        Q = self.tl.Q
        dev = ctx.deviations.get(regime, {}) if not preliminary else {}
        zero = tuple([0.0] * (Q + 1))
        self.d_cor = dev.get("cor", zero)
        self.d_nim = dev.get("nim", zero)
        near = p.near or zero
        self.nim_shift = tuple(near[q] + self.rg.nim_shift[q] for q in range(Q + 1))
        if shared is None:
            shared = {}
        of_world = shared.get(world)
        if of_world is None:
            # κ-добавка — к миру-опоре книги (любого знака); нет ключа — к базовому миру, только вверх (М§4.6)
            kap = kappa_addon(p.kappa, p.lag, self.w.real_key, ctx.worlds[p.kappa_world or BASE_WORLD].real_key, Q,
                              signed=p.kappa_world is not None)
            # X_W,q — разность опорных ставок кредитных книг Φ_A мира и мира H, взвешенная долями якоря (М§4.4)
            refs = [(wt, self.w.ref(p.books[b]["ref"]), self.wh.ref(p.books[b]["ref"]))
                    for b, wt in p.phi_weights.items()]
            x_w = tuple(sum(wt * (rw[q] - rh[q]) for wt, rw, rh in refs) for q in range(Q + 1))
            of_world = shared[world] = (kap, x_w, {})       # третье — ставки книг по кварталам (`evaluate`)
        kap, self.x_w, self.rates = of_world
        self.cor = tuple(self.rg.cor_engine[q] + kap[q] + self.d_cor[q] for q in range(Q + 1))
        self.kappa = kap
        self.cor_ref = p.fv_ref_cor                         # путь режима-опоры книги до розыгрыша, без κ и δ
        fx = getattr(ctx, "fx", None)                       # входы прохода (`PathInputs`) несут индекс готовым
        self.x = fx[world] if fx is not None else fx_index(ctx.book, self.w.cpi, Q)
        # CoR сегментов: при выключенной сегментной схеме — общая CoR (М§4.6). Нормировка — на структуре
        # `segment_w` (доли якоря или ключ книги, `segment_weights`): на ней общая CoR равна пути.
        if p.segment_rel is not None:
            w_ac = p.segment_w
            norm = sum(w_ac[s] * p.segment_rel[s] for s in w_ac)
            self.seg_mult = {s: p.segment_rel[s] / norm for s in w_ac}
        else:
            self.seg_mult = None
        calendar = shared.get(CALENDAR)
        if calendar is None:
            calendar = shared[CALENDAR] = ({q: self.tl.year(q) for q in range(-8, Q + 1)},
                                           {q: self.tl.h(q) for q in range(-8, Q + 1)})
        self.years, self.hs = calendar
        self.flows: dict[str, dict[int, float]] = {k: dict(v) for k, v in p.hist.items()}
        if p.link_base:
            self.flows["vol"] = dict(p.hist_vol)           # A_x — средний остаток базы объёма по кварталам
        if p.at1_from is not None:
            self.flows[CPN_NEW] = {}                       # купон сверх базы по кварталам сетки (М§4.9; до якоря — ноль)
        # требование с глиссадой req* (М§4.13.1); без ограничения роста — требование сценария
        self.req20g, self.req11g = p.glide[scenario] if p.growth is not None else (self.sc.req20, self.sc.req11)
        self.payout: dict[int, float] = shared.setdefault(PAYOUT, {})   # год прибыли → доля выплаты политики
        # год → книга → потенциальный множитель квартала: один у клеток мира и режима
        self.factors: dict[int, dict[str, float]] = shared.setdefault((world, regime), {})
        # `self.rates` (выше): квартал → ставки книг — одни у клеток мира и у всех оценок шага квартала
        self.unsolved: list[tuple[str, float]] = []         # кварталы, где доля прироста не сошлась в допуске
        self.recaps: list[RecapDecision] = []               # решения о взносе акционеров по кварталам решения (М§4.14)
        self.agm: dict[int, int] = {}                       # год прибыли → квартал решения о дивиденде (годовой календарь)

    # ------------------------------------------------------------ рост объёмов
    def loan_growth(self, b: str, year: int) -> float:
        p, rg = self.p, self.rg
        if year in rg.override:
            return rg.override[year]
        sector = p.books[b]["sector"]
        g = self.w.credit_growth[sector][year]
        if p.loan_drift is not None:
            d = p.loan_drift[sector][year] if year <= p.drift_until else 0.0
        else:
            d = p.loan_share_drift if year <= p.drift_until else 0.0
        return (1 + g) * (1 + d) - 1 + rg.loan_adj.get(year, 0.0)

    def funds_growth(self, sector: str, year: int, quarter: int | None = None) -> float:
        """Годовой темп средств сегмента в квартале года: рост сектора мира с премией. Премия — значение года
        траектории; у квартала, заданного ключом квартала или полугодия, — значение этого ключа (М§4.3)."""
        p = self.p
        g = self.w.funds_growth[sector][year]
        if p.funds_drift is not None:
            d = p.funds_drift[sector][year] if year <= p.drift_until else 0.0
            keyed = p.funds_drift_q.get(sector)
            if keyed and year <= p.drift_until:
                d = keyed.get((year, quarter), d)
        else:
            d = p.funds_share_drift if year <= p.drift_until else 0.0
        return (1 + g) * (1 + d) - 1

    def growth_factors(self, year: int) -> dict[str, float]:
        """Потенциальный множитель квартала кредитных книг года: 1 + m_b = (1 + g_b,Y)^0,25 (М§4.13.1)."""
        fac = self.factors.get(year)
        if fac is None:
            fac = self.factors[year] = {b: (1 + self.loan_growth(b, year)) ** QUARTER_YEARS
                                        for b in self.p.roles.loans}
        return fac

    def guidance_multipliers(self, st: State, q: int) -> dict[str, float]:
        """Год гайденса: сегменты растут одним квартальным множителем к цели года (М§4.3)."""
        p, tl = self.p, self.tl
        year = self.years[q]
        qs = [x for x in tl.quarters_of_year(year) if x >= 1]
        n = len(qs)
        out = {}
        for seg in ("corporate", "retail"):
            books = [b for b in p.roles.loans if p.books[b]["cor_segment"] == seg]
            start = sum(st.E[b] for b in books)
            base_end = p.af.prev_year_end[seg] if year == p.anchor_year else start
            target = base_end * (1 + p.guidance_growth[seg])
            out[seg] = (target / start) ** (1 / n)
        return out

    # ------------------------------------------------------------ выпуск добавочного капитала (М§4.10)
    def at1_issue(self, st: State, q: int, E: Mapping[str, float], OA: float, la_x: float, la_min: float) -> float:
        """AT1_q клетки в квартале q ≥ q_α у книги с ключом доли добавочного капитала (М§4.10, §4.11): деньги выпуска
        `I_q = AT1_q − AT1_(q−1)` приходят в конце квартала в балансирующие активы (при связанном минимуме ликвидности
        сначала гасят добор опта), а RWA квартала несут их вес — AT1_q = α_c × RWA_q, где RWA_q — решение уравнения
        `RWA = G + b × max(LA_x + α_c × RWA − AT1_(q−1), LA_min)`. G — RWA без балансирующих активов, b — RWA на рубль
        балансирующих активов (оба с дрейфом плотности, валютным индексом и множителем режима), `la_x` — балансирующие
        активы окончательного баланса при AT1_(q−1) до добора опта, `la_min` — минимум ликвидности в рублях LA.
        Закрытая форма: R_A = [G + b × (LA_x − AT1_(q−1))] / (1 − b × α_c), если минимум при ней не связывает; иначе
        RWA = G + b × LA_min. Решение единственно при b × α_c < 1; иначе книга несогласована — отказ."""
        p = self.p
        alpha, prev = st.a1s, st.at1
        f = p.dn[q] * self.x[q] * (1.0 if self.rg.rwa_mult is None else self.rg.rwa_mult[q])
        g = p.rwa_w.rwa(E, 0.0, 0.0, OA, p.dn[q], self.x[q], None if p.oa_delta is None else p.oa_delta[q])
        if self.rg.rwa_mult is not None:
            g *= self.rg.rwa_mult[q]
        b = (p.rwa_w.securities * p.sec_share + p.rwa_w.liquidity * (1 - p.sec_share)) * f
        if not b * alpha < 1:
            raise BookError(f"клетка {self.world}/{self.regime}/{self.scenario}, {self.tl.period(q)}: RWA на рубль "
                            f"балансирующих активов b = {b:.6g} при доле добавочного капитала α_c = {alpha:.6g} — "
                            f"b × α_c = {b * alpha:.6g} ≥ 1, выпуск по доле RWA не имеет решения: книга несогласована "
                            "(М§4.10, прил. A № 31)")
        rwa = (g + b * (la_x - prev)) / (1 - b * alpha)            # ветвь A: минимум ликвидности не связывает
        if la_x + alpha * rwa - prev < la_min:
            rwa = g + b * la_min                                    # ветвь B: выпуск гасит добор опта, LA_q = LA_min
        return alpha * rwa

    # ------------------------------------------------------------ шаг квартала
    def step(self, st: State, q: int, div_decl: float, pay_q: int | None = None,
             reg_q: int | None = None, parts: tuple | None = None, lam: float | None = None,
             top_up: Mapping[str, float] | None = None,
             rates: Mapping[str, float] | None = None, memo: dict | None = None,
             light: bool = False, rec: float = 0.0) -> dict[str, float]:
        """Шаг квартала q. `div_decl` — уменьшение BV дивидендами квартала; `parts` — решения квартала
        (сумма, квартал выплаты, квартал вычета из регуляторного капитала) при квартальном календаре:
        `div_decl` — их сумма, у каждого решения свои кварталы (М§5.7.4 п. 6). `lam` — доля потенциального
        прироста кредитных книг при ограничении роста капиталом, `top_up` — навёрстывание по книгам, млрд ₽
        (М§4.13.1); без `lam` рост задан. `rates` — ставки книг квартала, уже посчитанные другой оценкой шага
        этого же квартала (от объёмов и дивидендов они не зависят); без них считаются здесь. `memo` — память
        оценок шага этого квартала с одного и того же состояния (её ведёт `quarter_constrained`): объёмы и
        строки ОПУ, которые от дивидендов не зависят, считаются один раз на долю прироста и навёрстывание,
        сторона средств клиентов — один раз на квартал; без неё всё считается здесь. `light` — вернуть только
        нормативы и RWA квартала (и ставки книг), без записи шага и перехода состояния: так считаются оценки,
        по которым меряется запас капитала. `rec` — взнос акционеров в конце квартала (М§4.14.2): в
        предварительный баланс, средние остатки и совокупный доход квартала не входит; в капитал, окончательный
        баланс и оба базиса норматива — входит."""
        p, tl, w = self.p, self.tl, self.w
        books, roles = p.books, p.roles
        year, h = self.years[q], self.hs[q]
        d = tl.days[q - 1]
        dt = d / DAYS_IN_YEAR
        key = w.key[q]
        wage = w.wage[q]
        # 2. объёмы небалансирующих статей
        E0 = st.E
        slot = same = None                      # ключ памяти оценки и её запись (тот же квартал, та же доля)
        if memo is not None and lam is not None and year != p.guidance_year and p.link_base != "iea":
            slot = (lam, id(top_up)) if top_up else lam
            same = memo.get(slot)
        if same is None:
            E = dict(E0)
            if year == p.guidance_year:
                if not st.guid or st.guid.get("_year") != year:
                    st.guid = dict(self.guidance_multipliers(st, q))
                    st.guid["_year"] = year
                for b in roles.loans:
                    E[b] = E0[b] * st.guid[books[b]["cor_segment"]]
            elif lam is not None:
                # доля λ — одна на все кредитные книги с положительным потенциальным приростом; книга без него
                # идёт по потенциальному пути при любой λ (М§4.13.1)
                fac = self.growth_factors(year)
                for b in roles.loans:
                    E[b] = E0[b] * fac[b] if lam == 1.0 or fac[b] <= 1.0 else E0[b] * (1 + lam * (fac[b] - 1))
                if top_up:
                    for b, add in top_up.items():
                        E[b] += add
            else:
                for b in roles.loans:
                    E[b] = E0[b] * (1 + self.loan_growth(b, year)) ** QUARTER_YEARS
            side = memo.get(FUNDS_SIDE) if slot is not None else None
            if side is None:
                n_q = parse_period(tl.period(q))[1] if p.funds_drift_q else None
                FR = st.FR * (1 + self.funds_growth("retail", year, n_q)) ** QUARTER_YEARS
                gc = (1 + self.funds_growth("corporate", year, n_q)) ** QUARTER_YEARS
                for b in roles.corp_funds:
                    E[b] = E0[b] * gc
                c_star = current_share_target(key, p.c_ref, p.psi, p.key_ref, p.c_bounds)
                c = st.c + p.c_rho * (c_star - st.c)
                rc, rt = roles.retail
                E[rc], E[rt] = c * FR, (1 - c) * FR
                funds = FR + sum([E[b] for b in roles.corp_funds])
                wh_base = p.wh_to_funds * funds
                if slot is not None:
                    memo[FUNDS_SIDE] = (FR, c, funds, wh_base, {b: E[b] for b in roles.funds})
            else:
                FR, c, funds, wh_base, books_side = side
                E.update(books_side)
            loans = sum([E[b] for b in roles.loans])
            fv = E[p.fv_book] * p.fv_share if p.fv_book else 0.0
            loans_ac = loans - fv
            OA, OL, AL = p.oa_ratio * loans, p.ol_ratio * loans, p.allowance_ratio * loans_ac
            if p.oa_fixed:
                OA += p.oa_fixed                    # постоянная часть не растёт с кредитами (М§4.3)
            if p.oa_delta is not None:
                # приращение постоянной части к якорю по её пути (М§4.3): сумма в рублях, с кредитами не растёт;
                # деньги убывания — в балансирующих статьях (небалансирующих активов меньше, §4.10)
                OA += p.oa_delta[q]
        else:
            (_, E, FR, c, loans, fv, loans_ac, funds, wh_base, OA, OL, AL, avg, fv_avg, ac_avg, llp, fvc, vol,
             fees, opex, ins) = same
            E, avg = dict(E), dict(avg)
        # 3. ставки книг
        if rates is not None:
            rate = rates
        else:
            rate = dict(st.rate)
            phi, phi_l = p.phi_assets, p.phi_liab
            for b in roles.names:
                spec = books[b]
                ref = w.ref(spec["ref"])[q]
                s = p.spreads[b][q]
                rho = float(spec["rho"])
                if spec["side"] == "asset":
                    if spec.get("phi"):
                        s -= phi * (ref - self.wh.ref(spec["ref"])[q])
                    rate[b] = st.rate[b] + rho * (ref + s - st.rate[b])
                else:
                    if phi_l and spec.get("phi"):
                        s += phi_l * self.x_w[q]
                    rate[b] = st.rate[b] + rho * (float(spec["beta"]) * ref + s - st.rate[b])
        # 4. предварительный баланс при BV_(q−1); выплата объявленного в том же квартале — сразу
        pay = st.pay.get(q, 0.0)
        if parts is not None:
            pay += sum(a for a, part_pay, _ in parts if part_pay == q)
        else:
            pq = (pay_q if pay_q is not None else q) if div_decl else None
            if div_decl and pq == q:
                pay += div_decl
        DP = st.DP + div_decl - pay
        nonbal_assets = loans - AL + OA
        # добавочный капитал в предварительном балансе — AT1_(q−1): выпуск квартала приходит в конце квартала (М§4.10);
        # без ключа его доли — факт якоря во всех кварталах
        fixed_liab = funds + OL + DP + st.at1 + p.af.nci
        la_min = p.liquid_min * nonbal_assets / (1 - p.liquid_min)
        la_pre = fixed_liab + wh_base + (st.BV - div_decl) - nonbal_assets
        extra_pre = max(0.0, la_min - la_pre)
        la_pre += extra_pre
        sec_pre = p.sec_share * la_pre
        liq_pre = la_pre - sec_pre
        wh_pre = wh_base + extra_pre
        # 5. ОПУ
        if same is None:
            avg = {}
            for b in roles.names:
                avg[b] = (E0[b] + E[b]) / 2
            kept_avg = dict(avg) if slot is not None else None
        avg[SECURITIES] = (E0[SECURITIES] + sec_pre) / 2
        avg[LIQUIDITY] = (E0[LIQUIDITY] + liq_pre) / 2
        avg[WHOLESALE] = (E0[WHOLESALE] + wh_pre) / 2
        income = sum(rate[b] * avg[b] for b in roles.assets) * dt
        expense = sum([rate[b] * avg[b] for b in roles.liabilities]) * dt
        sp = 0.0
        if p.t2p_spread is not None:
            # надбавка за субординацию (М§4.4, §4.11): сверх ставки опта на T2 клетки конца прошлого квартала выше базы —
            # процентный расход вне книг (в ЧПД и в процентных расходах клетки, не в ставках книг)
            sp = p.t2p_spread * (st.t2l - p.t2p_base) * dt
            expense = expense + sp
        fr_avg = (st.FR + FR) / 2
        dia = p.dia * fr_avg * dt
        iea_avg = sum([avg[b] for b in roles.assets])
        ov = (self.nim_shift[q] + self.d_nim[q]) * iea_avg * dt
        nii = income - expense - dia + ov
        flows = self.flows
        if same is None:
            fv0 = E0[p.fv_book] * p.fv_share if p.fv_book else 0.0
            fv_avg = (fv0 + fv) / 2
            ac_avg = sum([avg[b] for b in roles.loans]) - fv_avg
            cor = self.cor[q]
            if self.seg_mult is None:
                llp = cor * ac_avg * dt
                cor_corp, ref_corp = cor, self.cor_ref[q]
            else:
                llp = 0.0
                for b in roles.loans:
                    seg = books[b]["cor_segment"]
                    part = avg[b] - (fv_avg if b == p.fv_book else 0.0)
                    llp += cor * self.seg_mult[seg] * part * dt
                cor_corp = cor * self.seg_mult["corporate"]
                ref_corp = self.cor_ref[q] * self.seg_mult["corporate"]
            fvc = fvc_amount(p.fv_factor, cor_corp, ref_corp, fv_avg, dt)
            gvw = p.fees_override.get(year)
            g_fees = gvw if gvw is not None else wage + p.fees_gvw[q]
            vol = None
            if p.link_base:
                # рост объёма г/г: средний остаток базы квартала к тому же кварталу прошлого года (М§4.7)
                if p.link_base == "iea":
                    vol = iea_avg
                elif p.link_base == "funds":
                    vol = (st.FR + sum(E0[b] for b in roles.corp_funds) + funds) / 2
                else:
                    vol = (sum(E0[b] for b in roles.loans) + loans) / 2
                flows["vol"][q] = vol
                v_ex = vol / flows["vol"][q - 4] - 1 - wage      # превышение роста объёма над ростом зарплат
                if gvw is None and p.link_fees:
                    g_fees += p.link_fees * v_ex
            fees = flows["fees"][q - 4] * (1 + g_fees)
            if p.link_opex:
                opex = flows["opex"][q - 4] * (1 + wage + p.link_opex * v_ex) * (1 + p.opex_real[q])
            else:
                opex = flows["opex"][q - 4] * (1 + wage) * (1 + p.opex_real[q])
            if p.link_ins:
                ins = flows["ins"][q - 4] * (1 + wage + p.ins_gvw[q] + p.link_ins * v_ex)
            else:
                ins = flows["ins"][q - 4] * (1 + wage + p.ins_gvw[q])
            if slot is not None:
                # балансирующие книги в записи — ещё как до шага: их остатки и средние у каждой оценки свои
                memo[slot] = (top_up, dict(E), FR, c, loans, fv, loans_ac, funds, wh_base, OA, OL, AL, kept_avg,
                              fv_avg, ac_avg, llp, fvc, vol, fees, opex, ins)
        elif vol is not None:
            flows["vol"][q] = vol
        idx = w.price_index[q]
        noncore = p.noncore_q[year] * idx
        misc = p.misc_q[(year, h)] * idx
        tenor = w.ofz[p.fvoci_tenor]
        dy = tenor[q] - (tenor[q - 1] if q > 1 else p.y_tenor0)
        fvr = -p.fvtpl_duration * dy * p.fvtpl_share * avg[SECURITIES] if p.fvr_on else 0.0
        one_off = self.rg.one_off_amount if q == self.rg.one_off_q else 0.0
        pbt = nii - llp - fvc + fees + ins + misc + fvr + noncore - opex + one_off
        tau_s = p.tau_stat[year]
        # купон бессрочных инструментов квартала — до налога: правило налога у книги с ключом его читает (М§4.2 п. 6);
        # круга нет — купон читает ключевую мира, AT1 конца прошлого квартала и слот или ключ купона якоря
        cpn = self.anchor_cpn(q) if h == p.coupon_quarter else 0.0
        cpn_new = 0.0
        if p.at1_from is not None:
            # купон сверх базы (М§4.9): ставка новых выпусков своего мира на AT1 конца прошлого квартала сверх базы
            cpn_new = (key + p.at1_spread) * (st.at1 - p.at1_base) * dt
            cpn = cpn + cpn_new
        iis = rate[SECURITIES] * avg[SECURITIES] * dt      # процентный доход книги бумаг клетки IIS_q (М§4.8)
        if p.tax_rule is None:
            tau_e = tau_s + p.tax_gap
            tax = tau_e * pbt
            saving, tau_c = 0.0, tau_s                       # экономия купона — законной ставкой в CI (образец)
        else:
            # разрыв налога по правилу (М§4.8): налог в рублях, ряд tau_eff — маржинальная ставка; экономия купона —
            # в налоге, купон в CI — целиком
            tax, saving, tau_e = rule_tax(p.tax_rule, tau_s, pbt, iis, cpn)
            tau_c = 0.0
        ot = p.ot_amount if q == p.ot_q else 0.0
        ni = pbt - tax - ot
        ni_sh = ni * (1 - p.nci_share)
        # 6. капитал
        fvoci_avg = p.fvoci_share * avg[SECURITIES]
        R = st.R * (1 - QUARTER_YEARS / p.fvoci_maturity) - p.fvoci_duration * dy * fvoci_avg * (1 - tau_s)
        oci = R - st.R
        om = p.other_movements[q]
        ci = ni_sh - cpn * (1 - tau_c) + oci + om
        BV = st.BV + ci - div_decl
        if rec:                                 # взнос акционеров — деньги конца квартала, не доход (М§4.9, §4.14.2)
            BV += rec
        # 7. окончательный баланс при BV_q
        la = fixed_liab + wh_base + BV - nonbal_assets
        at1 = st.at1
        if p.at1_from is not None and q >= p.at1_from:
            # выпуск добавочного капитала (М§4.10): AT1_q = α_c × RWA_q, деньги — в балансирующих активах конца квартала
            at1 = self.at1_issue(st, q, E, OA, la, la_min)
            la += at1 - st.at1
        extra = max(0.0, la_min - la)
        la += extra
        E[SECURITIES] = p.sec_share * la
        E[LIQUIDITY] = la - E[SECURITIES]
        E[WHOLESALE] = wh_base + extra
        assets = loans - AL + E[SECURITIES] + E[LIQUIDITY] + OA
        liab_eq = funds + E[WHOLESALE] + OL + DP + BV + at1 + p.af.nci
        # 8. RWA и нормативы
        reg = st.reg
        if parts is not None:
            reg = reg + [(q, part_reg, a) for a, _, part_reg in parts if a]
        elif div_decl:
            reg = reg + [(q, reg_q if reg_q is not None else q, div_decl)]
        dpreg = dpreg_at(reg, q)
        back = after_audit_start(h, p.cap.audit_cutoffs)
        flows["ni_sh"][q] = ni_sh
        e_unaud = sum([flows["ni_sh"][q - j] for j in range(back + 1)])
        rwa = p.rwa_w.rwa(E, E[SECURITIES], E[LIQUIDITY], OA, p.dn[q], self.x[q],
                          None if p.oa_delta is None else p.oa_delta[q])   # кредитные книги — из E; приращение — ω_Δ
        if self.rg.rwa_mult is not None:
            rwa *= self.rg.rwa_mult[q]          # множитель режима — на всех RWA клетки (М§4.11)
        sc = self.sc
        # T2 (М§4.11): траектория; у книги с ключом доли инструментов с квартала q_χ — доля клетки на RWA этого шага
        t2 = p.t2[q] if p.t2_from is None or q < p.t2_from else st.t2s * rwa
        rt_ = ratios(p.cap, bv=BV, dpreg=dpreg, reserve=R, unaudited=e_unaud, t2=t2, rwa=rwa,
                     ded_pp20=sc.ded_pp20[q], ded_pp11=sc.ded_pp11[q], at1=at1,
                     rub20=None if sc.rub20 is None else sc.rub20[q], rub11=None if sc.rub11 is None else sc.rub11[q])
        if light:
            return {"n20": rt_.n20, "n11": rt_.n11, "n11_star": rt_.n11_star, "rwa": rwa, "_rate": rate}
        # запись и переход
        flows["fees"][q], flows["opex"][q], flows["ins"][q] = fees, opex, ins
        st.E, st.rate, st.FR, st.c = E, rate, FR, c
        st.AL, st.OA, st.OL, st.DP, st.BV, st.R = AL, OA, OL, DP, BV, R
        st.reg, st.wh_extra, st.q = [entry for entry in reg if entry[1] > q], extra, q
        if p.t2_from is not None and q == p.t2_from - 1:
            st.t2s = t2 / rwa                   # χ_c задаёт записанный шаг квартала q_χ − 1 своими RWA (М§4.11)
        st.at1, st.t2l = at1, t2                # AT1 и T2 конца квартала: база выпуска, купона и надбавки следующего
        if p.at1_from is not None:
            flows[CPN_NEW][q] = cpn_new         # купон сверх базы квартала — база дивиденда (М§5.2, §5.7.3)
            if q == p.at1_from - 1:
                st.a1s = at1 / rwa              # α_c задаёт записанный шаг квартала q_α − 1 своими RWA (М§4.11)
        if parts is not None:
            for a, part_pay, _ in parts:
                if a and part_pay != q:
                    st.pay[part_pay] = st.pay.get(part_pay, 0.0) + a
        elif div_decl and pq != q:
            st.pay[pq] = st.pay.get(pq, 0.0) + div_decl
        income_base = nii + fees + ins + misc + fvr
        return {
            "bv": BV, "ni_sh": ni_sh, "ni": ni, "pbt": pbt, "nii": nii, "llp": llp, "fvc": fvc,
            "fees": fees, "opex": opex, "ins": ins, "misc": misc, "noncore": noncore, "fvr": fvr,
            "one_off": one_off, "tax": tax, "ot": ot, "oci": oci, "coupon": cpn, "om": om, "ci": ci,
            "div": div_decl, "dp": DP, "dpreg": dpreg, "pay": pay, "reserve": R,
            "rwa": rwa, "k20": rt_.k20, "k11": rt_.k11, "n20": rt_.n20, "n11": rt_.n11,
            "ded20": rt_.ded20, "ded11": rt_.ded11, "e_unaudited": e_unaud,
            "req20": self.sc.req20[q], "req11": self.sc.req11[q], "floor20": self.sc.floor20[q],
            "floor11": self.sc.floor11[q], "loans": loans, "loans_ac": loans_ac, "loans_fv": fv,
            "funds": funds, "funds_retail": FR, "iea": sum([E[b] for b in roles.assets]),
            "iea_avg": iea_avg, "loans_ac_avg": ac_avg, "loans_fv_avg": fv_avg, "assets": assets,
            "liabilities_equity": liab_eq, "securities": E[SECURITIES], "liquidity": E[LIQUIDITY],
            "wholesale": E[WHOLESALE], "wholesale_extra": extra, "other_assets": OA,
            "other_liabilities": OL, "allowance": AL, "current_share": c,
            "nim": nii / iea_avg / dt, "cor": llp / ac_avg / dt,
            "cir": opex / income_base if income_base else float("nan"),
            "roe_q": ci / st_bv_prev if (st_bv_prev := BV - ci + div_decl - rec) else float("nan"),
            "k_q": 0.0, "key": key, "tau_stat": tau_s, "tau_eff": tau_e,
            "int_income": income, "int_expense": expense, "dia": dia, "overlay": ov,
            "la_headroom": max(0.0, la - p.liquid_min * assets),
            "_rate": rate, "_avg": avg, "_bal": E,
            "n11_star": rt_.n11_star,
            "lam": 1.0 if lam is None else lam, "catch_up": sum(top_up.values()) if top_up else 0.0,
            "loans_potential": loans, "req20_glide": self.req20g[q], "req11_glide": self.req11g[q],
            "rec": rec, "t2": t2, "at1": at1, "coupon_new": cpn_new, "t2_premium": sp,
            "iis": iis, "tax_coupon": saving, "tau_cpn": tau_c,
        }

    # ------------------------------------------------------------ купон якоря и его налоговая ставка (М§4.8, §4.9)
    def anchor_cpn(self, q: int) -> float:
        """Годовой купон якоря в квартале купона q (М§4.9): слот фактов; у книги с ключом `capital.at1_coupon` — его
        формула по ключевой своего мира (кварталы не позже якоря — ключевая квартала якоря)."""
        p = self.p
        if p.cpn_rule is None:
            return p.coupon_annual
        return anchor_coupon(p.cpn_rule, self.w.key, q)

    def tau_cpn(self, year: int) -> float:
        """τ_cpn,Y — налоговая ставка купона бессрочных в совокупном доходе и в базах дивиденда (М§4.9, §5.2, §5.7.3):
        законная ставка года; у книги с ключом `tax.structure` — ноль (экономия купона — в налоге, М§4.8)."""
        return self.p.tau_stat[year] if self.p.tax_rule is None else 0.0

    # ------------------------------------------------------------ год Y: решение о дивиденде
    def year_base(self, year: int) -> float:
        p, tl = self.p, self.tl
        qs = tl.quarters_of_year(year)
        ni = 0.0
        for q in qs:
            if q not in self.flows["ni_sh"]:
                raise FactsError(f"нет ЧП акционерам за {tl.period(q)} для базы выплаты {year}")
            ni += self.flows["ni_sh"][q]
        cpn = sum(self.anchor_cpn(q) for q in qs if self.hs.get(q, tl.h(q)) == p.coupon_quarter)
        if CPN_NEW in self.flows:               # купон сверх базы кварталов года (М§5.2: CPN_Y = Σ CPN_q; до якоря — ноль)
            cpn += sum(self.flows[CPN_NEW].get(q, 0.0) for q in qs)
        return base_of_year(ni, cpn, self.tau_cpn(year), p.policy.deduct_at1_after_tax)

    def trial(self, st: State, q_a: int, year: int) -> list[Checkpoint]:
        """Пробный проход q_A … последняя точка проверки с Div_Y = 0 (М§5.3 п. 1)."""
        p, tl = self.p, self.tl
        pay_year = year + 1
        cps = [tl.index(period_str(pay_year, h)) for h in p.policy.checkpoints]
        cps = sorted(c for c in cps if c >= q_a)
        last = min(max(cps) if cps else tl.Q, tl.Q)
        cps = [c for c in cps if c <= tl.Q] or [last]
        trial_state = st.clone()
        saved = {k: dict(v) for k, v in self.flows.items() if k in STEP_FLOWS}
        out = []
        for qq in range(q_a, last + 1):
            row = self.step(trial_state, qq, 0.0)
            if qq in cps:
                out.append(Checkpoint(n20=row["n20"], n11=row["n11"], rwa=row["rwa"],
                                      floor20=row["floor20"], req11=row["req11"]))
        for k, v in saved.items():
            self.flows[k] = v
        return out

    # ------------------------------------------------------------ год Y: решение о взносе акционеров (М§4.14)
    def decide_recap(self, st: State, q_r: int, div_decl: float, pay_q: int | None, reg_q: int | None,
                     last_div: tuple[int, float, float, str | None] | None) -> float:
        """Решение о взносе акционеров в квартал решения q_R (М§4.14.1 пп. 2–4). Пробный проход с состояния на
        конец q_R − 1 по точкам окна q_R … min(q_R + L, Q), без взноса. Принятые дивиденды идут в нём со своими
        кварталами выплаты и вычета, как в окончательном расчёте: стоящие в очередях состояния — в своих
        кварталах; решённый в самом квартале q_R (решение в квартал собрания) — `div_decl` в квартале q_R. В
        кварталах после q_R новых решений нет — ни о дивиденде, ни о взносе: и когда в окно попал квартал
        собрания, и когда в него попал следующий квартал решения о взносе. Недостаток точки —
        `model.capital.shortfall`; взнос — наибольший недостаток окна, если он выше порога. `last_div` — последнее
        решение клетки о дивиденде (квартал, сумма, часть модели, источник): запись решения о взносе несёт его,
        если оно принято в кварталах q_R − 3 … q_R (дивиденд решения о взносе). Состояние и ряды клетки проход не
        меняет; запись решения — в `self.recaps`."""
        rule, tl = self.p.recap, self.tl
        last = min(q_r + rule.lookahead, tl.Q)
        trial_state = st.clone()
        saved = {k: dict(v) for k, v in self.flows.items() if k in STEP_FLOWS}
        points = []
        for c in range(q_r, last + 1):
            if c == q_r:
                row = self.step(trial_state, c, div_decl, pay_q, reg_q)
            else:
                row = self.step(trial_state, c, 0.0)
            points.append(shortfall(row, c, last=c == last))
        for k, v in saved.items():
            self.flows[k] = v
        gap, worst, norm = worst_point(points)
        rec = gap if gap > rule.min_amount else 0.0
        linked = last_div if last_div is not None and last_div[0] > q_r - YEAR_QUARTERS else None
        div_q, div, by_model, source = linked if linked is not None else (None, 0.0, 0.0, None)
        self.recaps.append(RecapDecision(
            year=self.years[q_r] - 1, q=q_r, last=last, points=tuple(points), shortfall=gap, point=worst.q,
            norm=norm, rec=rec, div=div, div_model=by_model, div_source=source, span=rule.span, div_q=div_q))
        return rec

    # ------------------------------------------------------------ квартальный календарь (М§5.7)
    def quarter_base(self, idx: int) -> float:
        """База дивиденда за квартал прибыли с номером `idx`: средняя по окну W последних кварталов прибыли
        акционеров (за вычетом купона бессрочных инструментов после налога, если политика его вычитает);
        кварталы не позже якоря — факт, позже — ряд клетки (М§5.7.3)."""
        p, tl = self.p, self.tl
        pol, ni = p.policy, self.flows["ni_sh"]
        window = range(idx - pol.window + 1, idx + 1)
        total = 0.0
        for x in window:
            if x not in ni:
                raise FactsError(f"нет прибыли акционеров за {tl.period(x)} для базы дивиденда за "
                                 f"{tl.period(idx)} (М§5.7.3)")
            total += ni[x]
            if pol.deduct_at1_after_tax and tl.h(x) == p.coupon_quarter:
                total -= self.anchor_cpn(x) * (1 - self.tau_cpn(tl.year(x)))
            if pol.deduct_at1_after_tax and x in self.flows.get(CPN_NEW, ()):
                total -= self.flows[CPN_NEW][x] * (1 - self.tau_cpn(tl.year(x)))   # купон сверх базы (М§5.7.3)
        return total / len(window)

    def probe(self, st: State, q: int, parts: tuple = ()) -> dict[str, float]:
        """Оценка шага квартала q на копии состояния, без записи (приём пробного прохода): состояние и ряды
        клетки остаются как до оценки. `parts` — дивиденды квартала, с которыми считается оценка."""
        row = self.step(st.clone(), q, sum(a for a, _, _ in parts), parts=parts)
        for name in STEP_FLOWS:
            if name in self.flows:
                self.flows[name].pop(q, None)
        return row

    def quarter_room(self, st: State, q: int, reg_parts: tuple) -> tuple[float, float]:
        """Запас капитала квартала q под решения модели без ограничения роста (М§5.7.4 п. 4) — пара
        (H_ref, H_fin): оценка шага с записями реестра и без решений модели, одна точка — конец квартала,
        отчётные нормативы против требований; без ограничения роста оба запаса равны. При ограничении роста
        запасы меряет `quarter_constrained` (М§4.13.2): по требованию с глиссадой и Н20.1 с прибылью периода."""
        p = self.p
        row = self.probe(st, q, reg_parts)
        point = Checkpoint(n20=row["n20"], n11=row["n11"], rwa=row["rwa"], floor20=row["floor20"],
                           req11=row["req11"])
        room = headroom((point,), p.policy.steps[0].threshold, p.cap.buffer20)
        return room, room

    def run_quarterly(self, last: int) -> tuple[list[dict], list[Decision], State]:
        """Проход при квартальном календаре (М§5.7.4): в квартале q — записи реестра и решения модели за
        открытые кварталы прибыли с этим кварталом решения; квартал считается один раз с суммой дивидендов."""
        p = self.p
        pol, cal = p.policy, p.calendar
        st = initial_state(p)
        rows: list[dict] = []
        decisions: list[Decision] = []
        shock_year = self.rg.shock_year
        for q in range(1, last + 1):
            due = cal.by_q.get(q)
            if not due:
                row = self.step(st, q, 0.0)
                row["div_model"] = 0.0
                rows.append(row)
                continue
            shock = shock_year is not None and self.years[q] == shock_year
            bases = [self.quarter_base(o.idx) for o in due]
            room = final = float("inf")
            if any(o.dps is None for o in due) and not (shock and pol.skip_in_shock):
                reg_parts = tuple((o.dps * pol.n_out / THOUSAND, o.q_pay, o.q_reg) for o in due if o.dps is not None)
                room, final = self.quarter_room(st, q, reg_parts)
            decs = decide_quarter(pol, q=q, due=due, bases=bases, headroom=room, headroom_final=final,
                                  deferred=st.D, shock=shock)
            st.D = decs[-1].deferred_after
            decisions.extend(decs)
            parts = tuple((d.div, o.q_pay, o.q_reg) for d, o in zip(decs, due))
            row = self.step(st, q, sum(d.div for d in decs), parts=parts)
            row["div_model"] = sum(d.div for d in decs if d.source != "register")
            rows.append(row)
        return rows, decisions, st

    # ------------------------------------------------------------ рост, ограниченный капиталом (М§4.13)
    def evaluate(self, st: State, q: int, parts: tuple, lam: float,
                 extra: Mapping[str, float] | None = None, *, memo: dict | None = None, light: bool = False
                 ) -> tuple[dict[str, float], State | None, dict[str, float] | None]:
        """Оценка шага Ш(λ, c, D) (М§4.13.1): расчёт квартала q на копии состояния, без записи, — кредитные
        книги при доле прироста `lam` и навёрстывании `extra`, дивиденды квартала — `parts`. Возвращает строку
        квартала, состояние после шага и значения рядов-баз квартала: принятую оценку записывает `accept`.
        `memo` — память оценок этого квартала с состояния `st` (`step`). `light` — оценка только ради запаса
        капитала: в строке — нормативы и RWA, состояния и рядов-баз нет (None); записью шага она не бывает."""
        # оценка «только нормативы» состояние не пишет (кроме множителей года гайденса) — копия ей не нужна
        after = st if light and self.years[q] != self.p.guidance_year else st.clone()
        rates = self.rates.get(q)               # ставки книг квартала — одни на все его оценки
        row = self.step(after, q, sum([a for a, _, _ in parts]), parts=parts, lam=lam, top_up=extra, rates=rates,
                        memo=memo, light=light)
        if rates is None:
            self.rates[q] = row["_rate"]
        if light:
            for name in STEP_FLOWS:
                if name in self.flows:
                    self.flows[name].pop(q, None)
            return row, None, None
        kept = {name: self.flows[name].pop(q) for name in STEP_FLOWS if name in self.flows}
        return row, after, kept

    def accept(self, q: int, kept: Mapping[str, float]) -> None:
        """Запись принятой оценки шага: её ряды-базы квартала становятся рядами клетки."""
        for name, value in kept.items():
            self.flows[name][q] = value

    def room(self, row: Mapping[str, float], q: int) -> tuple[float, float]:
        """Запасы ограничения роста по оценке шага, млрд ₽ (М§4.13.1): H_j = (N_j − req*_j,q) × RWA. N_20 —
        отчётный Н20.0; N_11 — Н20.1 с прибылью периода («пила» неаудированной прибыли в ограничение не входит);
        требование — с глиссадой."""
        rwa = row["rwa"]
        return (row["n20"] - self.req20g[q]) * rwa, (row["n11_star"] - self.req11g[q]) * rwa

    def checked(self, st: State, q: int, parts: tuple, lam: float, *, memo: dict | None = None
                ) -> tuple[tuple, tuple[float, float], int]:
        """Полная оценка шага при доле прироста `lam` (М§4.13.2 п. 4): оценка, отклонения нормативов от требования
        φ_j = N_j − req*_j,q и номер связывающего норматива (при равенстве — Н20.0)."""
        done = self.evaluate(st, q, parts, lam, memo=memo)
        row = done[0]
        gaps = (row["n20"] - self.req20g[q], row["n11_star"] - self.req11g[q])
        return done, gaps, 0 if gaps[0] <= gaps[1] else 1

    def quarter_constrained(self, st: State, q: int, star: Mapping[str, float]
                            ) -> tuple[dict[str, float], list[Decision], State]:
        """Квартал q при ограничении роста капиталом (М§4.13.2): дивиденд и доля прироста кредитных книг — вместе.
        `star` — уровни книг на потенциальном пути на конец q − 1. Возвращает строку квартала, решения и состояние
        на конец q; принятая оценка шага и есть его запись."""
        p, gr = self.p, self.p.growth
        pol, lam_min = p.policy, gr.lam_min
        due = p.calendar.by_q.get(q, ())
        in_shock = self.rg.shock_year == self.years[q]         # год шока отменяет решения модели квартала
        bases = [self.quarter_base(o.idx) for o in due]
        reg_parts = tuple((o.dps * pol.n_out / THOUSAND, o.q_pay, o.q_reg) for o in due if o.dps is not None)
        fac = self.growth_factors(self.years[q])
        can_cut = lam_min < 1.0 and any(f > 1.0 for f in fac.values())
        memo: dict = {}                         # память оценок шага квартала: все они — с состояния `st`
        modelled = any(o.dps is None for o in due) and not (in_shock and pol.skip_in_shock)
        # При решениях модели оценки без них нужны ради запаса капитала — считаются только нормативы; записью
        # шага такая оценка становится, лишь когда все решения модели — ноль, и тогда считается заново (п. 7).
        probe = modelled
        # 1. оценка при полном росте
        full = self.evaluate(st, q, reg_parts, 1.0, memo=memo, light=probe)
        h_full = self.room(full[0], q)
        # 2. базовый дивиденд — в пределах запаса своего порядка
        low = h_low = None
        if modelled and gr.dividend_first and can_cut:
            low = self.evaluate(st, q, reg_parts, lam_min, memo=memo, light=probe)
            h_low = self.room(low[0], q)
        h_ref = min(h_full) if h_low is None else min(h_low)
        first = quarter_bases(pol, due=due, bases=bases, headroom=h_ref, shock=in_shock, payout=self.payout).shares
        base_parts = tuple((d.base_div, o.q_pay, o.q_reg) for d, o in zip(first, due))
        # дивиденд решений модели, который снижает норматив уже в этом квартале (ι_p = 1)
        same_q = sum(d.base_div for d, o in zip(first, due) if d.source == "model" and o.q_reg == q)
        # 3. доля прироста — закрытая формула по двум оценкам
        g_full = (h_full[0] - same_q, h_full[1] - same_q)
        g_low = None
        lam = 1.0
        if can_cut and min(g_full) < 0:
            if low is None:
                low = self.evaluate(st, q, reg_parts, lam_min, memo=memo, light=probe)
                h_low = self.room(low[0], q)
            g_low = (h_low[0] - same_q, h_low[1] - same_q)
            lam = min(1.0, max(lam_min, min(growth_share(g_low[j], g_full[j], lam_min) for j in (0, 1))))
        # 4. проверка полной оценкой и не больше одного шага секущей по связывающему нормативу
        done = h_fin = None
        if lam_min < lam < 1.0:
            done, gaps, j = self.checked(st, q, base_parts, lam, memo=memo)
            if abs(gaps[j]) > gr.tol:
                r = gaps[j] * done[0]["rwa"]
                end, g_end = (lam_min, g_low[j]) if r < 0 else (1.0, g_full[j])
                if g_end * r < 0:
                    lam = min(1.0, max(lam_min, lam - r * (end - lam) / (g_end - r)))
                    done, gaps, j = self.checked(st, q, base_parts, lam, memo=memo)
                if abs(gaps[j]) > gr.tol:
                    self.unsolved.append((self.tl.period(q), gaps[j]))
            h_fin = min(gaps[i] * done[0]["rwa"] + same_q for i in (0, 1))
        elif lam < 1.0:
            h_fin = min(h_low)                  # λ* = λ_min: проверки нет, норматив может остаться ниже требования
        # 5. навёрстывание — при полном росте и запасе, раньше выплаты избытка
        plain, extra = full, None               # оценка без решений модели при итоговых объёмах
        if lam == 1.0 and min(g_full) >= 0 and gr.catch_up > 0:
            want = {b: gr.catch_up * QUARTER_YEARS * (star[b] - st.E[b]) * fac[b] for b in p.roles.loans
                    if star[b] > st.E[b]}
            if want:
                more = self.evaluate(st, q, reg_parts, 1.0, want, memo=memo, light=probe)
                h_more = self.room(more[0], q)
                g_more = (h_more[0] - same_q, h_more[1] - same_q)
                if min(g_more) >= 0:
                    plain, extra = more, want
                else:
                    theta = min(g_full[j] / (g_full[j] - g_more[j]) for j in (0, 1) if g_more[j] < 0)
                    theta = min(1.0, max(0.0, theta))
                    if theta > 0:
                        part = {b: theta * add for b, add in want.items()}
                        check = self.evaluate(st, q, reg_parts, 1.0, part, memo=memo, light=probe)
                        if min(self.room(check[0], q)) - same_q >= -gr.tol * check[0]["rwa"]:
                            plain, extra = check, part
        # 6. догоняющая выплата и избыток — после навёрстывания и только при неурезанном росте
        if lam == 1.0:
            h_fin = min(self.room(plain[0], q))
        decs = decide_quarter(pol, q=q, due=due, bases=bases, headroom=h_ref, headroom_final=h_fin,
                              payout=self.payout,
                              deferred=st.D, shock=in_shock, growth_cut=lam < 1.0)
        # 7. запись шага: принятая оценка при итоговых объёмах и дивидендах
        if done is None:
            if all(d.div == 0.0 for d in decs if d.source != "register"):
                done = plain if lam == 1.0 else low
                if done[1] is None:             # считались только нормативы — запись шага при тех же объёмах
                    done = self.evaluate(st, q, reg_parts, lam, extra, memo=memo)
            else:
                done = self.evaluate(st, q, tuple((d.div, o.q_pay, o.q_reg) for d, o in zip(decs, due)), lam, extra,
                                     memo=memo)
        row, after, kept = done
        self.accept(q, kept)
        if decs:
            after.D = decs[-1].deferred_after
        row["lam"] = lam
        row["div_model"] = sum(d.div for d in decs if d.source != "register")
        return row, decs, after

    def run_constrained(self, last: int) -> tuple[list[dict], list[Decision], State]:
        """Проход при ограничении роста капиталом (М§4.13): квартал за кварталом — `quarter_constrained`; рядом
        ведётся потенциальный путь кредитных книг E*_b (рост без ограничения)."""
        loans = self.p.roles.loans
        st = initial_state(self.p)
        star = {b: st.E[b] for b in loans}
        rows: list[dict] = []
        decisions: list[Decision] = []
        for q in range(1, last + 1):
            row, decs, st = self.quarter_constrained(st, q, star)
            fac = self.growth_factors(self.years[q])
            star = {b: star[b] * fac[b] for b in loans}
            row["loans_potential"] = sum(star.values())
            decisions.extend(decs)
            rows.append(row)
        return rows, decisions, st

    def run(self, until: int | None = None) -> tuple[list[dict], list[Decision], State]:
        p, tl = self.p, self.tl
        if p.growth is not None:
            return self.run_constrained(tl.Q if until is None else min(tl.Q, until))
        if p.calendar is not None:
            return self.run_quarterly(tl.Q if until is None else min(tl.Q, until))
        st = initial_state(p)
        rows: list[dict] = []
        decisions: list[Decision] = []
        pol = p.policy
        paid_year = p.af.dividends_payable_year
        last = tl.Q if until is None else min(tl.Q, until)
        last_div = None                         # последнее решение клетки о дивиденде: (квартал, сумма, часть
        #                                         модели, источник) — его несёт запись решения о взносе (М§4.14.1)
        for q in range(1, last + 1):
            div_decl, pay_q, reg_q, by_model = 0.0, None, None, 0.0
            source = None
            agm = self.hs[q] == pol.agm_quarter
            if agm:
                year = self.years[q] - 1
                if year >= p.anchor_year - 1 and year != paid_year:
                    base = self.year_base(year)
                    declared = p.register.get(year)
                    shock = self.rg.shock_year is not None and year + 1 == self.rg.shock_year
                    points: list[Checkpoint] = []
                    if declared is None and not (shock and pol.skip_in_shock):
                        points = self.trial(st, q, year)
                    dec = decide(pol, year=year, base=base, points=points, buffer20=p.cap.buffer20,
                                 deferred=st.D, shock=shock, declared_dps=declared)
                    st.D = dec.deferred_after
                    decisions.append(dec)
                    div_decl = dec.div
                    by_model = 0.0 if dec.source == "register" else dec.div
                    pay_q = max(q, p.pay_q_by_year.get(year, tl.index(period_str(year + 1, pol.pay_quarter))))
                    reg_q = max(q, p.reg_q_by_year.get(year, tl.index(period_str(year + 1, pol.reg_quarter))))
                    source = dec.source
                    self.agm[year] = q
                    last_div = (q, div_decl, by_model, source)
            if p.recap is None:
                row = self.step(st, q, div_decl, pay_q, reg_q)
            else:
                # решение о взносе — в каждом квартале сетки с номером h_R (ключ `decision_quarter`; без ключа —
                # квартал собрания), кроме её последнего квартала: недостаток на конце сетки несёт терминал
                # (М§4.14.1, §4.14.3). В квартал собрания оно принимается вслед за решением о дивиденде
                rec = 0.0
                if self.hs[q] == p.recap.quarter and q < tl.Q:
                    rec = self.decide_recap(st, q, div_decl, pay_q, reg_q, last_div)
                row = self.step(st, q, div_decl, pay_q, reg_q, rec=rec)
            row["div_model"] = by_model
            rows.append(row)
        return rows, decisions, st


def anchor_row(p: Prepared, ctx: "RunContext", scenario: str) -> dict[str, float | None]:
    """Строка q = 0 (якорь): балансы и нормативы из фактов, потоки квартала якоря — факт ОПУ."""
    af, roles, tl = p.af, p.roles, p.timeline
    sc = p.scenarios[scenario]
    st = initial_state(p)
    loans = sum(af.balances[b] for b in roles.loans)
    loans_ac = loans - af.fv_loans
    dpreg = dpreg_at(st.reg, 0) if st.reg else 0.0
    ay, aq = parse_period(tl.anchor)
    back = after_audit_start(aq, p.cap.audit_cutoffs)
    try:
        e0 = sum(p.hist["ni_sh"][-j] for j in range(back + 1))
    except KeyError:
        e0 = None
    x0 = 1.0
    rwa0 = p.rwa_w.rwa({b: af.balances[b] for b in roles.loans}, af.balances[SECURITIES],
                       af.balances[LIQUIDITY], af.other_assets, p.dn[0], x0)
    rt_ = ratios(p.cap, bv=af.bv, dpreg=dpreg, reserve=af.fvoci_reserve, unaudited=e0 or 0.0,
                 t2=p.t2[0], rwa=rwa0, ded_pp20=sc.ded_pp20[0], ded_pp11=sc.ded_pp11[0],
                 rub20=None if sc.rub20 is None else sc.rub20[0], rub11=None if sc.rub11 is None else sc.rub11[0])
    h = p.hist
    row: dict[str, float | None] = {k: None for k in QUARTER_FIELDS}
    row.update({
        "bv": af.bv, "reserve": af.fvoci_reserve, "dp": af.dividends_payable, "dpreg": dpreg,
        "rwa": rwa0, "k20": rt_.k20, "n20": rt_.n20, "ded20": rt_.ded20, "ded11": rt_.ded11,
        "k11": rt_.k11 if e0 is not None else None, "n11": rt_.n11 if e0 is not None else None,
        "e_unaudited": e0, "req20": sc.req20[0], "req11": sc.req11[0], "floor20": sc.floor20[0],
        "floor11": sc.floor11[0], "loans": loans, "loans_ac": loans_ac, "loans_fv": af.fv_loans,
        "funds": sum(af.balances[b] for b in roles.funds),
        "funds_retail": sum(af.balances[b] for b in roles.retail),
        "iea": sum(af.balances[b] for b in roles.assets), "securities": af.balances[SECURITIES],
        "liquidity": af.balances[LIQUIDITY], "wholesale": af.balances[WHOLESALE],
        "other_assets": af.other_assets, "other_liabilities": af.other_liabilities,
        "allowance": af.allowance, "current_share": st.c,
        "nii": h["nii"].get(0), "llp": h["llp"].get(0), "fees": h["fees"].get(0),
        "opex": h["opex"].get(0), "ins": h["ins"].get(0), "misc": h["misc"].get(0),
        "noncore": h["noncore"].get(0), "pbt": h["pbt"].get(0), "tax": h["tax"].get(0),
        "ni": h["ni"].get(0), "ni_sh": h["ni_sh"].get(0),
        # рост по капиталу (М§4.13.3): потенциальный путь начинается с якоря; требование — с глиссадой
        "loans_potential": loans,
        "req20_glide": p.glide[scenario][0][0] if p.growth is not None else sc.req20[0],
        "req11_glide": p.glide[scenario][1][0] if p.growth is not None else sc.req11[0],
        "n11_star": None if e0 is None else rt_.n11_star, "t2": p.t2[0],
        "at1": af.at1,                       # строка якоря — факт AT1_0 при любом ключе (М§4.11, «Якорь»)
    })
    return row


def shared_anchor_row(p: Prepared, ctx: Any, scenario: str, shared: dict | None) -> dict[str, float | None]:
    """Строка якоря сценария капитала — одна у клеток прогона (её только читают); без `shared` — своя."""
    if shared is None:
        return anchor_row(p, ctx, scenario)
    row = shared.get((ANCHOR, scenario))
    if row is None:
        row = shared[(ANCHOR, scenario)] = anchor_row(p, ctx, scenario)
    return row


def preliminary_paths(ctx: "RunContext", world: str, regime: str, scenario: str, until: int, *,
                      shared: dict | None = None) -> dict[str, tuple[float, ...]]:
    """CoR и ЧПМ движка клетки без отклонений A-P2u (δ ≡ 0) по q = 1…until (М§12, x⁰).

    Кварталы до `until` считаются так же, как в полном проходе (проход последовательный,
    пробный проход дивиденда смотрит вперёд сам), поэтому x⁰ не зависит от `until`. `shared` — общее клеток
    предварительного прохода (`_Cell`)."""
    cell = _Cell(ctx, world, regime, scenario, preliminary=True, shared=shared)
    rows, _, _ = cell.run(until=until)
    return {"cor": (0.0,) + tuple(r["cor"] for r in rows), "nim": (0.0,) + tuple(r["nim"] for r in rows)}


def terminal_inputs(p: Prepared, cell: _Cell, rows: list[dict]) -> tuple[dict[str, float], float]:
    """Входы терминала из прохода клетки (М§7) — всё, кроме дисконта и параметров терминала книги (рост,
    угасание, множитель избытка); рядом — Н20.1 с прибылью периода на конце сетки."""
    tl = p.timeline
    Q = tl.Q
    last = rows[-1]
    L = tl.year(Q)
    pbt_l = sum(r["pbt"] for q, r in zip(range(1, Q + 1), rows) if tl.year(q) == L)
    n11_star = n11_audited(last["k11"], last["e_unaudited"], last["rwa"], p.cap.gap11, cell.sc.ded_pp11[Q])
    y_bal = p.sec_share * last["_rate"][SECURITIES] + (1 - p.sec_share) * last["_rate"][LIQUIDITY]
    n20_t, n11_t = last["n20"], n11_star
    if last["dpreg"]:
        # дивиденды, решённые в последних кварталах сетки: из BV ушли, в регуляторном капитале ещё стоят —
        # без вычета терминал раздал бы их второй раз, как избыток (М§7)
        n20_t -= last["dpreg"] / last["rwa"]
        n11_t -= last["dpreg"] / last["rwa"]
    inputs = dict(n20=n20_t, req20=last["req20"], n11_star=n11_t, req11=last["req11"],
                  rwa=last["rwa"], bv_q=last["bv"], pbt_last_year=pbt_l, y_balancing=y_bal,
                  c_wholesale=last["_rate"][WHOLESALE], headroom=last["la_headroom"], tau_eff=last["tau_eff"],
                  nci_share=p.nci_share, coupon_annual=p.coupon_annual, tau_stat=last["tau_stat"],
                  lt_inflation=cell.w.lt_inflation, min_share=p.liquid_min,
                  wholesale_extra=last["wholesale_extra"])
    if p.at1_from is not None:
        # купон года T + 1 (М§7): CPN_ann + c_α,Q × ΔAT1_Q — ставка новых выпусков последнего квартала сетки на сумму
        # сверх базы конца сетки
        inputs["coupon_new"] = (last["key"] + p.at1_spread) * (last["at1"] - p.at1_base)
    if p.t2p_spread is not None:
        # надбавка за субординацию (М§7): года L (в PBT_L) и года T + 1 — та же ставка на сумму сверх базы конца сетки
        inputs["sp_l"] = sum(r["t2_premium"] for q, r in zip(range(1, Q + 1), rows) if tl.year(q) == L)
        inputs["sp_t1"] = p.t2p_spread * (last["t2"] - p.t2p_base)
    if p.cpn_rule is not None:
        # купон якоря года T + 1 по ставке своего мира (М§7, §4.9): ключевая последнего квартала сетки
        inputs["coupon_annual"] = terminal_anchor_coupon(p.cpn_rule, last["key"])
    if p.tax_rule is not None:
        # разрыв налога по правилу (М§7): налог года T + 1 — правилом в рублях от IIS года L, ставок бумаг и ликвидности
        # конца сетки и купона T + 1; ставка τ_eff,L терминалом не читается
        inputs.update(tax_rule=p.tax_rule, tau_eff=float("nan"),
                      iis_l=sum(r["iis"] for q, r in zip(range(1, Q + 1), rows) if tl.year(q) == L),
                      y_securities=last["_rate"][SECURITIES], y_liquidity=last["_rate"][LIQUIDITY],
                      sec_share=p.sec_share)
    return inputs, n11_star


def fixed_block(p: Prepared, cell: _Cell, rows: list[dict]) -> dict[str, float]:
    """Постоянные в рублях части конца сетки — входы блока терминала с долей λ_F (М§7), выходы прохода клетки:
    F_A = OA_fixed + ΔOA_Q — постоянные прочие активы (§4.3); R_F = (ω_oaf × OA_fixed + ω_Δ × ΔOA_Q) × Dn_Q × X_Q ×
    M_r,Q — их RWA (§4.11); C_j = Dfix_j + Drub_j,s,Q — постоянные в рублях вычеты норматива j (без ключей — нули);
    κ_j = req_j,Q − (gap_pp_j − deduction_pp_j,s,Q) + Dgrow_j / RWA_0 — капитал на рубль RWA норматива j (без ключей
    доли Dgrow_j = Ded_j,0). Связывающий норматив, ставку y_m и доход блока считает оценка (`model.valuation`):
    проход λ_F не читает, и блок у него один при любой доле."""
    Q = p.timeline.Q
    last = rows[-1]
    sc, cap, w = cell.sc, p.cap, p.rwa_w
    delta = 0.0 if p.oa_delta is None else p.oa_delta[Q]
    mult = 1.0 if cell.rg.rwa_mult is None else cell.rg.rwa_mult[Q]
    r_f = (w.other_assets_fixed * p.oa_fixed + w.oa_change * delta) * p.dn[Q] * cell.x[Q] * mult
    parts = cap.parts
    fix20, fix11 = (0.0, 0.0) if parts is None else (parts.fix20, parts.fix11)
    grow20, grow11 = (cap.ded20_0, cap.ded11_0) if parts is None else (parts.grow20, parts.grow11)
    rub20 = 0.0 if sc.rub20 is None else sc.rub20[Q]
    rub11 = 0.0 if sc.rub11 is None else sc.rub11[Q]
    # χ_20 — доля инструментов клетки у книги с ключом доли (М§4.11, §7): стоящая вне бизнеса доля несёт свой T2
    chi20 = 0.0 if p.t2_from is None else last["t2"] / last["rwa"]
    block = {"f_a": p.oa_fixed + delta, "r_f": r_f, "c20": fix20 + rub20, "c11": fix11 + rub11,
             "kappa20": last["req20"] - (cap.gap20 - sc.ded_pp20[Q]) + grow20 / cap.rwa0 - chi20,
             "kappa11": last["req11"] - (cap.gap11 - sc.ded_pp11[Q]) + grow11 / cap.rwa0}
    if p.at1_from is not None:
        # α_20 — доля добавочного капитала клетки у книги с ключом его доли (М§4.11, §7): κ_20 − χ_c − α_c; κ_11 прежний
        alpha20 = last["at1"] / last["rwa"]
        block["kappa20"] = block["kappa20"] - alpha20
    return block


def path_flags(p: Prepared, cell: _Cell, rows: list[dict], decisions: list[Decision]
               ) -> tuple[set[str], str | None]:
    """Флаги прохода клетки (от оценки не зависят) и квартал первого разрыва к полу норматива."""
    tl = p.timeline
    # нормативы после дивидендов, разрыв к полу
    gap = None
    for q, r in zip(range(1, tl.Q + 1), rows):
        if r["n20"] < r["floor20"] or r["n11"] < r["floor11"]:
            gap = tl.period(q)
            break
    flags = set()
    if gap is not None:
        flags.add("capital_gap")
    for dec in decisions:
        flags.update(dec.flags)
    if any(r["lam"] < 1 - LAM_TOL for r in rows):
        flags.add("growth_cut")
    if cell.unsolved:
        flags.add("growth_solver")
    if any(r.rec > 0 for r in cell.recaps):                 # хотя бы один взнос больше нуля (М§4.14.4)
        flags.add(RECAP_FLAG)
    if any(r.rec > 0 and r.div_model > 0 for r in cell.recaps):     # у решения со взносом — дивиденд модели (М§4.14.1)
        flags.add(RECAP_DIVIDEND_FLAG)
    return flags, gap


def recap_residuals(recaps: list[RecapDecision], rows: list[dict]) -> tuple[RecapDecision, ...]:
    """Решения о взносе с остатком недостатка окончательного расчёта (инвариант `recap_covers_gap`, М§14.1): у
    решения со взносом — наибольший по точкам инварианта недостаток, пересчитанный по рядам окончательного
    прохода тем же правилом, что в решении (отчётные нормативы; в точке c_max — без дивидендов, не вычтенных к
    концу окна). `rows` — строки кварталов 1…Q."""
    out = []
    for r in recaps:
        if r.rec > 0:
            worst = max(shortfall(rows[c - 1], c, last=c == r.last).s for c in residual_points(r))
            r = dataclasses.replace(r, residual=worst)
        out.append(r)
    return tuple(out)


def value_path(ctx: "RunContext", world: str, inputs: Mapping[str, float], bv: tuple, ci: tuple, div: tuple,
               rec: tuple | None = None, fixed: Mapping[str, float] | None = None, where: str = ""):
    """Терминал и оценка клетки по её проходу (М§6–§7): дисконт мира, рост, угасание и множитель избытка — из
    контекста прогона, остальное — из прохода. Одна функция у полной клетки и у лёгкой клетки сводки. `rec` — ряд
    взносов акционеров прохода книги с включённой докапитализацией: тогда обе формы и терминал несут цену
    размещения — дисконт d книги (М§6.5, §7); без него — прежние формулы. `fixed` — постоянные части конца сетки
    (`fixed_block`): их читает терминал книги с ключом λ_F (М§7); `where` — название клетки для отказа."""
    p, disc = ctx.prep, ctx.discounts[world]
    term = terminal(**inputs, real_growth=p.real_growth, fade=p.fade, multiple=p.multiple, k_t=disc.k_t,
                    fixed=fixed, lam_f=p.lam_f, where=where,
                    symmetric=p.fade_symmetric, discount=p.recap_discount, om_ann=p.om_ann)
    val = value_cell(q0=ctx.clock.q0, elapsed=ctx.clock.elapsed, disc=disc, bv=bv, ci=ci, div=div,
                     term=term, rec=rec, discount=p.recap_discount)
    return term, val


# Ряды кварталов, которых хватает лёгкой клетке: оценке — BV, мосту — дивиденды, годовым рядам роста — кредиты.
SUMMARY_FIELDS = ("bv", "div_model", "loans", "loans_potential", "catch_up", "lam")


@dataclass(frozen=True)
class CellPath:
    """Проход клетки, сжатый до входов оценки (М§6–§7) и сводки прогона полосы (М§10). От дисконта, угасания
    избыточной доходности и множителя избытка капитала терминала, весов миров, вероятностей, даты оценки и
    дисконта за управление проход не зависит: пока входы прохода те же (`model.grid.path_keys`), он считается
    один раз, а оценка — заново. Реальный рост терминала проход читает — путями миров (рост кредита сходится к
    росту терминала мира)."""
    world: str
    regime: str
    scenario: str
    bv: tuple[float, ...]                  # BV на конец квартала, q = 0…Q
    ci: tuple[float, ...]                  # совокупный доход квартала (q = 0 — ноль)
    div: tuple[float, ...]                 # уменьшение BV дивидендами (q = 0 — ноль)
    div_model: tuple[float | None, ...]    # часть дивиденда, решённая моделью (q = 0 — None)
    terminal: Mapping[str, float]          # входы терминала из прохода (`terminal_inputs`)
    n11_star: float
    n20_min: float
    n11_min: float
    gap_period: str | None
    flags: frozenset[str]                  # флаги прохода; `roe_below_k` добавляет оценка
    cut_share: tuple[float | None, ...]    # доля урезанного роста по годам клетки (М§4.13.3)
    solver: tuple[tuple[str, float], ...] = ()
    rec: tuple[float, ...] | None = None   # взнос акционеров в конце квартала (q = 0 — ноль); без докапитализации — None
    fixed: Mapping[str, float] | None = None   # постоянные части конца сетки (`fixed_block`, М§7): их читает
    #                                            только терминал книги с ключом λ_F


def cell_path(ctx: Any, world: str, regime: str, scenario: str, *, shared: dict | None = None) -> CellPath:
    """Проход клетки (W, r, s) для сводки прогона. `ctx` — входы прохода (`model.grid.PathInputs`) или контекст
    прогона: проход читает только подготовку, пути миров, отклонения A-P2u и валютный индекс. `shared` — общее
    клеток прогона (`_Cell`)."""
    p = ctx.prep
    cell = _Cell(ctx, world, regime, scenario, shared=shared)
    rows, decisions, _ = cell.run()
    full = [shared_anchor_row(p, ctx, scenario, shared)] + rows
    quarters = {k: tuple(map(methodcaller("get", k), full)) for k in SUMMARY_FIELDS}
    inputs, n11_star = terminal_inputs(p, cell, rows)
    flags, gap = path_flags(p, cell, rows, decisions)
    years = tuple(range(p.anchor_year, p.timeline.last_year + 1))
    return CellPath(
        world=world, regime=regime, scenario=scenario, bv=quarters["bv"],
        ci=(0.0,) + tuple(r["ci"] for r in rows), div=(0.0,) + tuple(r["div"] for r in rows),
        div_model=quarters["div_model"], terminal=inputs, n11_star=n11_star,
        n20_min=min(r["n20"] for r in rows), n11_min=min(r["n11"] for r in rows), gap_period=gap,
        flags=frozenset(flags), cut_share=growth_rows(p, quarters, years)["cut_share"],
        solver=tuple(cell.unsolved),
        rec=None if p.recap is None else (0.0,) + tuple(r["rec"] for r in rows),
        fixed=fixed_block(p, cell, rows))


def summary_cell(ctx: "RunContext", path: CellPath) -> CellResult:
    """Лёгкая клетка — оценка готового прохода в контексте прогона: стоимость, терминал, флаги и то из рядов,
    что читают слои, мост и сводка прогона (`model.uncertainty.run_summary`). Рядов по кварталам и годам,
    книг и решений у неё нет — полную клетку считает `run_cell`."""
    term, val = value_path(ctx, path.world, path.terminal, path.bv, path.ci, path.div, path.rec, path.fixed,
                           where=f"клетка {path.world}/{path.regime}/{path.scenario}")
    flags = set(path.flags)
    if term.roe_t < term.k_t:
        flags.add("roe_below_k")
    quarters = {"bv": path.bv, "div": (None,) + path.div[1:], "div_model": path.div_model}
    if path.rec is not None:
        quarters["rec"] = (None,) + path.rec[1:]
    return CellResult(
        world=path.world, regime=path.regime, scenario=path.scenario,
        quarters=quarters, annual={}, dps={},
        v_ri=val.v_ri, v_ddm=val.v_ddm, bv_v=val.bv_v, x_t=term.x_t, roe_t=term.roe_t, k_t=term.k_t,
        g_t=term.g_t, tv_ri=term.tv_ri, terminal_share=val.terminal_share,
        n20_min=path.n20_min, n11_min=path.n11_min, gap_period=path.gap_period, flags=frozenset(flags),
        tv_ddm=term.tv_ddm, pv_ri_explicit=val.pv_ri_explicit, pv_terminal=val.pv_terminal,
        roe_t_raw=term.roe_raw, g_capped=term.g_capped, bv_star=term.bv_star, n11_star=path.n11_star,
        y_x=term.y_x, la_headroom=path.terminal["headroom"],
        growth={"cut_share": path.cut_share}, solver=path.solver,
        c_v=val.c_v, pvd=val.pvd, p_t=term.p_t, dc_t=term.dc_t, pv_rec=val.pv_rec,
        pv_rec_terminal=val.pv_rec_terminal, pv_tv_ddm=val.pv_tv_ddm, terminal_fixed=term.fixed)


def run_cell(ctx: "RunContext", world: str, regime: str, scenario: str, *, summary: bool = False,
             shared: dict | None = None) -> CellResult:
    """Клетка (W, r, s): квартальный проход, терминал, RI и DDM (М§4–§7). `summary` — лёгкая клетка для сводки
    прогона полосы (`summary_cell`): те же проход и оценка, без рядов по кварталам и годам. `shared` — общее
    клеток прогона (`_Cell`)."""
    if summary:
        return summary_cell(ctx, cell_path(ctx, world, regime, scenario, shared=shared))
    p = ctx.prep
    cell = _Cell(ctx, world, regime, scenario, shared=shared)
    rows, decisions, st = cell.run()
    disc: Discount = ctx.discounts[world]
    row0 = shared_anchor_row(p, ctx, scenario, shared)
    full = [row0] + rows
    quarters = {k: tuple(map(methodcaller("get", k), full)) for k in QUARTER_FIELDS}
    quarters["k_q"] = tuple(disc.k)
    books = {b: {"rate": (p.af.rates[b],) + tuple(r["_rate"][b] for r in rows),
                 "avg": (None,) + tuple(r["_avg"][b] for r in rows),
                 "balance": (p.af.balances[b],) + tuple(r["_bal"][b] for r in rows)}
             for b in p.roles.names}
    # терминал (М§7)
    last = rows[-1]
    inputs, n11_star = terminal_inputs(p, cell, rows)
    bv = quarters["bv"]
    ci = (0.0,) + tuple(r["ci"] for r in rows)
    div = (0.0,) + tuple(r["div"] for r in rows)
    rec = None if p.recap is None else (0.0,) + tuple(r["rec"] for r in rows)
    term, val = value_path(ctx, world, inputs, bv, ci, div, rec, fixed_block(p, cell, rows),
                           where=f"клетка {world}/{regime}/{scenario}")
    n20s = [r["n20"] for r in rows]
    n11s = [r["n11"] for r in rows]
    flags, gap = path_flags(p, cell, rows, decisions)
    if term.roe_t < term.k_t:
        flags.add("roe_below_k")
    cal = p.calendar
    if cal is None:
        dps = {dec.year: dec.dps for dec in decisions}
        dps_pol = {dec.year: pool_policy(p.policy, dec.year, dec.base) * 1000 / p.af.n_iss for dec in decisions}
        dps_q, dps_pol_q = {}, {}
    else:
        # по кварталам прибыли — решения клетки; по годам — сумма четырёх кварталов: открытые — решения,
        # закрытые — строки истории дивидендов (М§5.7.5)
        dps_q = {dec.period: dec.dps for dec in decisions}
        dps_pol_q = {dec.period: pool_policy(p.policy, dec.year, dec.base) * 1000 / p.af.n_iss for dec in decisions}
        dps = {y: cal.closed_dps[y] + sum(dps_q[per] for per in cal.year_periods[y]) for y in cal.years}
        dps_pol = {y: cal.closed_dps[y] + sum(dps_pol_q[per] for per in cal.year_periods[y]) for y in cal.years}
    recaps, shares, paid, n_base = (), None, None, None
    if rec is not None:
        # путь числа акций клетки — для печати (М§6.6): DPS решения — на акции, существующие перед взносом его
        # квартала (акции якоря, акции поправки делителя и акции прежних взносов); доля выплаты года — от суммы
        # дивиденда (DPS на акции якоря, `paid`)
        recaps = recap_residuals(cell.recaps, rows)
        n_div, n_base = _divisors(ctx)
        shares = share_path(q0=ctx.clock.q0, disc=disc, div=div, rec=rec, term=term, discount=p.recap_discount,
                            n_div=n_div)
        paid, dps, dps_pol = dps, {}, {}
        for dec in decisions:
            dps[dec.year], dps_pol[dec.year] = own_year_dps(p, shares, cell.agm[dec.year], dec, n_base)
    annual, years = annual_rows(p, quarters, dps, paid)
    if rec is not None:
        annual.update(recap_rows(p, quarters, shares, years))
    return CellResult(
        world=world, regime=regime, scenario=scenario, quarters=quarters, annual=annual, dps=dps,
        v_ri=val.v_ri, v_ddm=val.v_ddm, bv_v=val.bv_v, x_t=term.x_t, roe_t=term.roe_t, k_t=term.k_t,
        g_t=term.g_t, tv_ri=term.tv_ri, terminal_share=val.terminal_share,
        n20_min=min(n20s), n11_min=min(n11s), gap_period=gap, flags=frozenset(flags),
        years=years, tv_ddm=term.tv_ddm, pv_ri_explicit=val.pv_ri_explicit, pv_terminal=val.pv_terminal,
        roe_t_raw=term.roe_raw, g_capped=term.g_capped, bv_star=term.bv_star,
        decisions=tuple(decisions), dps_policy=dps_pol, ci_q0=ci[ctx.clock.q0], n11_star=n11_star,
        y_x=term.y_x, la_headroom=last["la_headroom"],
        real_rate=float(ctx.book.get(f"worlds.{world}.zero_curve.LT")) - cell.w.lt_inflation,
        books=books, dps_q=dps_q, dps_policy_q=dps_pol_q,
        growth=growth_rows(p, quarters, years), solver=tuple(cell.unsolved),
        pv_ri_q=tuple(r * d for r, d in zip(val.ri, disc.dfq)),
        c_v=val.c_v, pvd=val.pvd, p_t=term.p_t, dc_t=term.dc_t, pv_rec=val.pv_rec,
        pv_rec_terminal=val.pv_rec_terminal, recaps=recaps, shares=shares, pv_tv_ddm=val.pv_tv_ddm, n_base=n_base,
        terminal_fixed=term.fixed,
    )


def _divisors(ctx: "RunContext") -> tuple[float, float]:
    """(N_div, N_base) прогона (М§8.4): делитель «на акцию», с которого начинается путь числа акций клетки, и его
    база — без поправки `valuation.share_count_adj`."""
    from model.grid import divisor, divisor_base    # здесь, а не в начале модуля: `model.grid` читает этот модуль
    return divisor(ctx.book, ctx.facts, ctx.prep.af), divisor_base(ctx.book, ctx.facts, ctx.prep.af)


def own_year_dps(p: Prepared, shares: SharePath, q_a: int, dec: Decision, n_base: float | None = None
                 ) -> tuple[float, float]:
    """DPS решения квартала q_A на акции своего года (М§6.6) — пара (DPS на акцию в обращении, DPS политики на
    размещённую акцию): дивиденд квартала собрания достаётся акциям, существовавшим до взноса этого квартала.
    Акции клетки — акции якоря, акции поправки делителя и акции взносов: их больше, чем на якоре, на
    N_(q_A − 1) − N_base (`n_base` — база делителя; без неё — N_div: книга без поправки делителя). Решение записью
    реестра — DPS записи: дивиденд объявлен на акцию. Пул политики и отношение N_out / N_iss — по фактам якоря.
    Пока взносов не было и поправки нет — числа решения как есть; при оборванном пути DPS решения модели — ноль."""
    n_before = shares.n[q_a - 1]
    pool = pool_policy(p.policy, dec.year, dec.base)
    if n_before is None:
        return (dec.dps if dec.source == "register" else 0.0), 0.0
    extra = n_before - (shares.n[0] if n_base is None else n_base)
    if not extra:
        return dec.dps, pool * THOUSAND / p.af.n_iss
    own = dec.dps if dec.source == "register" else dec.div * THOUSAND / (p.af.n_out + extra)
    return own, pool * THOUSAND / (p.af.n_iss + extra)


def recap_rows(p: Prepared, quarters: Mapping[str, tuple], shares: SharePath, years: tuple[int, ...]
               ) -> dict[str, tuple[float | None, ...]]:
    """Годовые ряды клетки книги с включённой докапитализацией (`RECAP_FIELDS`, М§4.14.4): взнос, принятый в
    календарном году (сумма кварталов сетки года), доля нынешних акций и делитель клетки на конец года (М§6.6;
    год без конца на сетке — без значения; после обрыва пути доля — ноль, числа акций нет)."""
    tl = p.timeline
    out: dict[str, list[float | None]] = {k: [] for k in RECAP_FIELDS}
    for y in years:
        qs = tl.quarters_of_year(y)
        out["rec"].append(sum(quarters["rec"][q] for q in qs if 1 <= q <= tl.Q))
        end = qs[-1]
        inside = 0 <= end <= tl.Q
        out["stake"].append(shares.stake[end] if inside else None)
        out["shares"].append(shares.n[end] if inside else None)
    return {k: tuple(v) for k, v in out.items()}


def growth_rows(p: Prepared, quarters: Mapping[str, tuple], years: tuple[int, ...]
                ) -> dict[str, tuple[float | None, ...]]:
    """Годовые ряды роста кредитных книг клетки (М§4.13.3): потенциальный и фактический рост суммы кредитных
    книг конца года к концу прошлого; доля урезанного роста на конец года; навёрстанное за год; наименьшая за
    год доля прироста. Знаменатель года якоря — факт конца прошлого года (`balance.history`); нет узла — роста
    года якоря нет."""
    tl = p.timeline
    loans, potential = quarters["loans"], quarters["loans_potential"]
    out: dict[str, list[float | None]] = {k: [] for k in GROWTH_FIELDS}
    for y in years:
        qs = tl.quarters_of_year(y)
        end, prev = qs[-1], qs[0] - 1
        inside = [q for q in qs if 1 <= q <= tl.Q]
        if end > tl.Q or not inside:            # год без конца на сетке или без кварталов сетки — значений нет
            for k in GROWTH_FIELDS:
                out[k].append(None)
            continue
        if prev >= 0:
            base, base_potential = loans[prev], potential[prev]
        else:
            base = base_potential = p.hist_bal.get(prev, {}).get("loans")
        out["potential"].append(None if base_potential is None else potential[end] / base_potential - 1)
        out["actual"].append(None if base is None else loans[end] / base - 1)
        out["cut_share"].append(1 - loans[end] / potential[end])
        out["catch_up"].append(sum(quarters["catch_up"][q] for q in inside))
        out["lam_min"].append(min(quarters["lam"][q] for q in inside))
    return {k: tuple(v) for k, v in out.items()}


def annual_rows(p: Prepared, quarters: Mapping[str, tuple], dps: Mapping[int, float],
                paid: Mapping[int, float] | None = None
                ) -> tuple[dict[str, tuple[float | None, ...]], tuple[int, ...]]:
    """Годовые ряды клетки (П§2 grid.cells[].annual): год якоря — факт отчётных кварталов + клетка.

    Годовые отношения — сумма кварталов к среднему пяти концов кварталов года (М§0.3);
    концы до якоря — `balance.history` фактов (если конца нет — среднее доступных). `paid` — DPS по годам
    прибыли на акции якоря у книги с включённой докапитализацией: доля выплаты года считается от суммы
    дивиденда, а не от DPS на акции своего года (М§6.6); без него — от `dps`.
    """
    tl = p.timeline
    years = tuple(range(p.anchor_year, tl.last_year + 1))
    out: dict[str, list[float | None]] = {k: [] for k in ("ni_sh", "roe", "cor", "nim", "cir", "n20",
                                                          "n11", "dps", "payout")}
    hist = p.hist
    Q = tl.Q

    def flow(name: str, q: int) -> float | None:
        if q >= 1:
            return quarters[name][q]
        return hist.get(name, {}).get(q)

    for y in years:
        qs = tl.quarters_of_year(y)
        ends = [q for q in [qs[0] - 1] + qs if q <= Q]

        def total(name: str) -> float | None:
            vals = [flow(name, q) for q in qs]
            return None if any(v is None for v in vals) else sum(vals)

        def mean_end(name: str) -> float | None:
            vals = []
            for q in ends:
                v = quarters[name][q] if q >= 0 else p.hist_bal.get(q, {}).get(name)
                if v is not None:
                    vals.append(v)
            return sum(vals) / len(vals) if vals else None

        ni = total("ni_sh")
        bv_avg = mean_end("bv")
        out["ni_sh"].append(ni)
        out["roe"].append(None if ni is None or not bv_avg else ni / bv_avg)
        llp, ac = total("llp"), mean_end("loans_ac")
        out["cor"].append(None if llp is None or not ac else llp / ac)
        nii, iea = total("nii"), mean_end("iea")
        out["nim"].append(None if nii is None or not iea else nii / iea)
        parts = [total(k) for k in ("nii", "fees", "ins", "misc")]
        opex = total("opex")
        if opex is None or any(v is None for v in parts):
            out["cir"].append(None)
        else:
            fvr = sum(quarters["fvr"][q] or 0.0 for q in qs if q >= 1)
            out["cir"].append(opex / (sum(parts) + fvr))
        last_q = qs[-1]
        out["n20"].append(quarters["n20"][last_q] if 0 <= last_q <= Q else None)
        out["n11"].append(quarters["n11"][last_q] if 0 <= last_q <= Q else None)
        d = dps.get(y)
        out["dps"].append(d)
        if paid is not None:
            d = paid.get(y)
        out["payout"].append(None if d is None or not ni else d * p.af.n_iss / 1000 / ni)
    return {k: tuple(v) for k, v in out.items()}, years
