# -*- coding: utf-8 -*-
"""Приёмочные проверки книги ВТБ на её собственных фактах (проверка, ключей не пишет): путь года якоря против месячных
фактов; проверки согласованности «маржа + прочие доходы» до счёта оценки (решения ведущего № 2, п. 1.6 и 7.8 — вердикт
разбора прочих доходов, stage1/calib-misc/REPORT-skeptic.md §7); путь клетки мира-опоры против бэктеста книг (проверка
1(г) в редакции решения № 2, п. 2); предельный корпоративный кредит на базовом капитале (решение № 2, п. 7.6); рост
портфеля и внешний капитал (проверка 1(д) в редакции решения № 3, пп. 3.4 и 6.1).

Строки:
  квартал с месячными фактами (июль и август × 1,5), смесь заголовка: ЧПД, комиссии, расходы, резервы, прочие доходы
       (определение банка), прибыль до налога, вся прибыль; вся прибыль года якоря против темпа известных месяцев;
  (а)  сумма «ЧПД + прочие» мира уровня не выше суммы окна L (маржа кварталов окна в знаменателе движка) с прочими
       доходами на нынешнем хвосте — ДВА чтения: по ключу (стационар на составе якоря) и по пути клеток мира уровня
       (последние годы сетки, собственный состав баланса клеток);
  (б)  та же сумма на ближнем пути смеси заголовка в следующем за якорем году — внутри окна C, в знаменателе окна
       разбора (с денежными средствами); второе полугодие года якоря несёт факт восьми месяцев и печатается справочно;
  1(а) маржа года после якоря (устав §5, п. 1(а)) — на режиме «нормализация» внутри окна C 2,6–3,2 % (решение ведущего № 6,
       п. 2.3: как стоимость риска того же года — смесь заголовка несёт год шока); смесь, модальная клетка и клетка условий
       окна печатаются рядом;
  (в)  доля прочих доходов в чистых операционных доходах последних лет сетки миров N и H — в пределах лет нормальной маржи;
  1(г) путь маржи клетки мира-опоры за восемь кварталов против пути бэктеста книг на составе якоря — отклонение не больше
       ошибки самого бэктеста;
  B14б предельный рубль корпоративного кредита на базовом капитале на фондировании ядра (норма решения № 3, раздел 4):
       в мире H — около нейтрального (±5 п.п. к стоимости капитала); в каждом мире — не ниже 5 % и не выше 30 %; отдача
       на оптовом фондировании печатается рядом, справочно;
  1(д) рост кредитов и RWA в годы условий окна (2027–2028) против фактов 2025–2026 годов и прогноза банка — В УСЛОВИЯХ
       ОКНА (решение № 3, п. 6.1: окно фактов роста — мир M без года шока): норма сверяется с клеткой «мир окна ×
       нормализация»; режим «нормализация» по мирам и смесь заголовка печатаются рядом, нормой не служат (смесь несёт
       год шока по построению); внешний капитал этих лет — внутри отрезка «арифметика листа capital r2 … слова
       менеджмента»; рост после 2028 года — суждение с ценой, а не факт: справочная строка.
«Прочие» в определении банка = «прочее» движка + страховая строка + резервы не по кредитам (числа разбора: в среднем
25 млрд ₽ в год, из них резервы 7; страховую строку клетки модель считает сама). Окно C разбора измерено в знаменателе
с денежными средствами: сумма ближнего пути приводится к нему отношением якоря. Пределы строк — константы листа с
источником; команда перевывода печатает строки и поднимает красный флаг у непройденной (числа книги при этом пишутся:
проверка судит суждения, а не подбор).

Запуск из корня репозитория:
  python -B data/assumptions/evidence/path/facts_check.py [--book КНИГА] [--facts КАТАЛОГ] [--out ФАЙЛ]
Код выхода: 0 — посчитано; 1 — отказ книги или фактов.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs" / "vtb_r2_inputs.json"
FACT_PERIOD = "2026Q3"
TOL = {"nii": 0.03, "fees": 0.03, "opex": 0.01, "llp": 0.25, "other": 0.25, "pbt": 0.15, "ni_q": 0.15, "ni_year": 0.10}
#       ЧПД и комиссии — знаменатель клетки к факту (3 %); расходы — уровень поставлен по фактам (1 %); резервы — пути режимов
#       второго полугодия 0,9–1,1 % при 0,8 и 1,0 % в июле и августе (25 %); прочие доходы — ключ года стоит темпом восьми
#       месяцев (195 в год в определении движка), два месяца строки с переоценкой разбросаны от −7 до +25 млрд ₽ (25 %);
#       прибыль до налога и прибыль квартала — разброс кварталов первого полугодия (±15 %); прибыль года — четыре
#       неизвестных месяца с сезоном расходов (±10 % к темпу известных месяцев)
NEAR_WINDOW_H1 = (0.025, 0.031)           # окно C только по 1-му полугодию: сумма «ЧПД + прочие» без результата 1К2026 и с ним (разбор,
#                                           §7 п. 3б) — справочно; строка (б) судится окном восьми месяцев (решение № 4, п. 3.6): window_c()
SHARE_WINDOW = (-0.11, 0.08)              # доля прочих в доходах лет нормальной маржи 2017–2021 (разбор, §7 п. 3в)
NIM_WINDOW = (0.026, 0.032)               # устав §5, п. 1(а): ближний путь печатает маржу 2,6–3,2 % (окно C); год после якоря судится на режиме
#                                           «нормализация», смесь заголовка — рядом (решение ведущего № 6, п. 2.3)
STATIONARY_YEARS = 4                      # последние годы сетки — стационар клетки
BACKTEST_QUARTERS = 8                     # проверка 1(г): первые восемь прогнозных кварталов (мера листа calib-nii/r2)
GROWTH_YEARS = (2027, 2028)               # проверка 1(д): годы условий окна фактов (решение № 3, п. 3.4)
WINDOW_WORLD, WINDOW_REGIME = "M", "norm"  # условия окна фактов роста 2025–8М2026: мир M без года шока (решение № 3, п. 6.1)
LATER_YEARS = (2029, 2030, 2031, 2032)    # рост после лет окна — суждение с ценой: печатается справочно, окном не судится
LOANS_WINDOW = (0.05, 0.07)               # рост кредитов за год: прогноз банка на 2026 год +5 % … факт года до якоря +7 %
#                                           [Ф: презентация 6М2026; баланс фактов 30.06.2025 → 30.06.2026: +6,7 %] (решение № 2, п. 7.5)
RWA_WINDOW = (-0.034, 0.07)               # рост RWA за год: факт первого полугодия 2026 года −1,7 % (в годовом выражении −3,4 %:
#                                           «кредитный манёвр») … рост кредитов за год +7 % [Ф: устав §1, окно C; решение № 2, п. 7.5]
RECAP_YEARS = (2027, 2028)                # годы ступеней требования 01.04.2027 и 01.04.2028
RECAP_SHEET = (142.0, 303.0)              # внешний капитал двух лет при росте книг 5 % в год: план банка … темп восьми месяцев
#                                           [Р: лист calib-capital/r2, раздел 8, sheets/recap_expected_r2.csv — ожидание по сценариям]
RECAP_WORDS = 700.0                       # слова менеджмента: «до 700 млрд ₽ в капитал в 2027–2028 годах» [вторично; решение № 1, A]
RECAP_WINDOW = (140.0, RECAP_WORDS)       # решение № 3, п. 3.4: внешний капитал 2027–2028 годов — внутри 140–700 млрд ₽


def window_c(facts, inputs: dict) -> dict:
    """Окно C устава (1К–2К + июль–август года якоря, решение ведущего № 4, п. 3.6): сумма «ЧПД + прочие (определение банка)» в
    знаменателе окна разбора (процентные активы с денежными средствами) — без разового результата 1К и с ним; середина — их
    среднее. Знаменатель окна за полугодие — 2 × ЧПД 1П / маржа 1П в нём (лист разбора); маржа восьми месяцев в нём — маржа 1П ×
    отношение печатной маржи восьми месяцев (кварталы весом трёх месяцев, месяцы — одного) к печатной марже 1П. Прочие доходы —
    годовой темп восьми месяцев в определении банка (лист разбора)."""
    w = inputs["window_c"]
    pnl = facts.file("pnl_quarterly")["quarters"]
    mq = facts.file("mgmt_quarterly")
    nii_h1 = sum(float(pnl[p]["nii"]["v"]) for p in w["h1_quarters"])
    iea_one = 2.0 * nii_h1 / float(w["nim_one_h1"])
    q_nim = [float(mq["quarters"][p]["nim"]) if not isinstance(mq["quarters"][p]["nim"], dict) else float(mq["quarters"][p]["nim"]["v"])
             for p in w["h1_quarters"]]
    m_nim = [float(m["nim_m"]["v"]) for m in mq["monthly"] if m["month"] in w["months"]]
    if len(m_nim) != len(w["months"]):
        raise RuntimeError(f"окно C: в фактах не все месяцы {w['months']}")
    print_h1 = sum(q_nim) / len(q_nim)
    print_all = (3.0 * sum(q_nim) + sum(m_nim)) / (3.0 * len(q_nim) + len(m_nim))
    nim_one = float(w["nim_one_h1"]) * print_all / print_h1
    other = w["other_annual_bank_def"]
    s = {k: nim_one + float(other[k]) / iea_one for k in ("without", "with", "apr_aug")}
    return {"low": s["without"], "high": s["with"], "mid": (s["without"] + s["with"]) / 2, "apr_aug": s["apr_aug"], "nim_one": nim_one,
            "iea_one": iea_one, "print_h1": print_h1, "print_8m": print_all, "other": dict(other)}


def window_sum(flows: dict, quarters: list[int], tl, wide: float, addback: float) -> float:
    """Сумма «ЧПД + прочие (определение банка)» за кварталы `quarters` к средним процентным активам с денежными средствами (знаменатель
    окна разбора), в год: (ЧПД + страховая строка + «прочее» движка + резервы не по кредитам) / (средние процентные активы × wide).
    `flows[name][q]` — ряды клетки или ожидание по клеткам (ЧПД nii, ins, misc, iea_avg)."""
    flow = sum(float(flows[n][i]) for i in quarters for n in ("nii", "ins", "misc")) + addback * len(quarters) / 4
    d = sum(tl.d(i) for i in quarters)
    iea = sum(float(flows["iea_avg"][i]) * tl.d(i) for i in quarters) / d
    return flow / (iea * wide) * 365.0 / d


def wide_of(facts, all_inputs: dict) -> float:
    """Знаменатель окна разбора к знаменателю движка на якоре: 1 + (деньги и обязательные резервы) / процентные активы."""
    iea0 = float(facts.need("balance", "iea"))
    cash = sum(float(facts.file("balance")["other_assets_parts"][name]["v"]) for name in all_inputs["capital"]["zero_weight_cash_parts"])
    return 1.0 + cash / iea0


def level_parts(cell, quarters: list[int], books: dict, anchor: dict, at1: float, nci: float, oa_fixed: float) -> dict:
    """Разложение маржи пути клетки за кварталы `quarters` (решение ведущего № 4, п. 3.5; рекомендация проверяющего находки B-1) —
    ставки книг пути, движок, без АСВ и общего сдвига:
      level   — уровень на составе якоря (остатки книг якоря при ставках пути);
      mix     — состав баланса: балансирующие доли, смесь кредитов и средств клиентов при доле платных пассивов якоря;
      free    — бесплатные пассивы (платные пассивы к процентным активам пути против якоря) с разбивкой: капитал (BV), постоянная часть
                прочих активов (OA_fixed — в рублях, разводняется ростом баланса), прочее (прочие обязательства, бессрочные, доля
                меньшинства, резерв, растущие прочие активы, дивиденд к выплате);
      path    — маржа пути по ставкам книг (level + mix + free); print — маржа клетки (с АСВ и общим сдвигом)."""
    assets = [b for b, s in books.items() if s["side"] == "asset"]
    liabs = [b for b, s in books.items() if s["side"] != "asset"]
    avg = {b: sum(float(cell.books[b]["avg"][i]) for i in quarters) / len(quarters) for b in assets + liabs}
    rate = {b: sum(float(cell.books[b]["rate"][i]) * float(cell.books[b]["avg"][i]) for i in quarters)
            / sum(float(cell.books[b]["avg"][i]) for i in quarters) for b in assets + liabs}
    iea0, ibl0 = sum(anchor[b] for b in assets), sum(anchor[b] for b in liabs)
    iea, ibl = sum(avg[b] for b in assets), sum(avg[b] for b in liabs)
    y0, c0 = sum(rate[b] * anchor[b] for b in assets) / iea0, sum(rate[b] * anchor[b] for b in liabs) / ibl0
    y1, c1 = sum(rate[b] * avg[b] for b in assets) / iea, sum(rate[b] * avg[b] for b in liabs) / ibl
    nim0 = y0 - c0 * ibl0 / iea0
    nim1 = y1 - c1 * ibl0 / iea0
    nim2 = y1 - c1 * ibl / iea
    q = cell.quarters
    ends = [quarters[0] - 1] + quarters
    stock = lambda name: sum(float(q[name][i]) for i in ends) / len(ends)  # noqa: E731
    iea_end = stock("iea")
    comp = {"capital": stock("bv") / iea_end, "fixed_assets": -oa_fixed / iea_end}
    comp["other"] = (stock("other_liabilities") + stock("dp") + at1 + nci + stock("allowance") - (stock("other_assets") - oa_fixed)) / iea_end
    q0 = {"capital": float(q["bv"][0]) / float(q["iea"][0]), "fixed_assets": -oa_fixed / float(q["iea"][0])}
    q0["other"] = (float(q["other_liabilities"][0]) + float(q["dp"][0]) + at1 + nci + float(q["allowance"][0])
                   - (float(q["other_assets"][0]) - oa_fixed)) / float(q["iea"][0])
    moves = {k: comp[k] - q0[k] for k in comp}
    total = sum(moves.values())
    free = nim2 - nim1
    split = {k: (free * v / total if abs(total) > 1e-12 else 0.0) for k, v in moves.items()}
    days = sum(float(q["nii"][i]) for i in quarters)
    iea_avg = sum(float(q["iea_avg"][i]) for i in quarters) / len(quarters)
    return {"level": nim0, "mix": nim1 - nim0, "free": free, "free_split": split, "path": nim2,
            "paid_to_iea": {"anchor": ibl0 / iea0, "path": ibl / iea}, "free_share_moves": moves,
            "print": days / iea_avg * 4.0 / len(quarters)}


def rows_of(book_path: Path | None, facts_dir: Path | None) -> dict:
    root = HERE
    while not (root / "model" / "book.py").exists():
        root = root.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from model import levels as L
    from model.book import load_book, load_facts
    from model.grid import modal_cell, point_probabilities, run_grid
    from model.live import live_from_book
    from model.paths import Trajectory

    facts = load_facts(facts_dir)
    book = load_book(book_path, facts=facts)
    all_inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    inputs = all_inputs["skeptic"]
    run = run_grid(book, facts, live_from_book(book, facts))
    ctx, tl = run.ctx, run.ctx.timeline
    prob = point_probabilities(run)
    year, qn = int(FACT_PERIOD[:4]), int(FACT_PERIOD[-1])
    want = {f"{year}-{m:02d}" for m in range(3 * qn - 2, 3 * qn + 1)}
    months = facts.file("mgmt_quarterly").get("monthly") or []
    known = [m for m in months if m["month"] in want]
    k = 3.0 / len(known)
    total = lambda name: sum(float(m[name]["v"]) for m in known) * k  # noqa: E731
    q = tl.index(FACT_PERIOD)
    ex = lambda name: float(L.expect(run, prob, name, q))  # noqa: E731
    diff, addback = float(inputs["bank_minus_engine"]), float(inputs["other_provisions_addback"])
    rows = []

    def add(name: str, value: float, low: float, high: float, words: str) -> None:
        rows.append({"name": name, "value": value, "low": low, "high": high, "ok": bool(low - 1e-12 <= value <= high + 1e-12), "words": words})

    def near(title: str, model: float, fact: float, tol: float, note: str = "") -> None:
        add(f"{title} {FACT_PERIOD} к фактам месяцев × {k:g}", model / fact, 1 - tol, 1 + tol,
            f"модель {model:.1f} при {fact:.1f} по фактам ({100 * (model / fact - 1):+.1f} %; допуск ±{100 * tol:.0f} %){note}")

    # ---- квартал с месячными фактами: все строки
    near("ЧПД", ex("nii"), total("nii_m"), TOL["nii"])
    near("комиссии", ex("fees"), total("nci_m"), TOL["fees"])
    near("расходы", abs(ex("opex")), -total("opex_m"), TOL["opex"])
    near("резервы", abs(ex("llp")), -total("provisions_m"), TOL["llp"])
    other_model = ex("ins") + ex("misc") + addback / 4
    near("прочие доходы (определение банка)", other_model, total("other_income_m"), TOL["other"],
         f"; модель — «прочее» движка {ex('misc'):.1f} + страховая строка {ex('ins'):.1f} + резервы не по кредитам {addback / 4:.1f}; ключ года стоит темпом "
         "восьми месяцев, июль–август идут выше него")
    pbt_fact = sum(total(n) for n in ("nii_m", "nci_m", "other_income_m", "provisions_m", "opex_m"))
    near("прибыль до налога", ex("pbt"), pbt_fact, TOL["pbt"],
         f"; факт — сумма строк месячной книги (ЧПД, комиссии, прочие доходы, резервы, расходы); налог по фактам {100 * (1 - total('net_profit_m') / pbt_fact):.1f} %, "
         f"в модели {100 * (1 - ex('ni') / ex('pbt')):.1f} %")
    near("вся прибыль", ex("ni"), total("net_profit_m"), TOL["ni_q"])
    # ---- прибыль года якоря против темпа известных месяцев
    last = max(months, key=lambda m: m["month"])
    n_months = int(last["month"][-2:])
    pace = float(last["net_profit_ytd"]["v"]) * 12 / n_months
    ni_year = float(L.year_flow(run, prob, "ni", year))
    add(f"вся прибыль {year} года к темпу {n_months} месяцев", ni_year / pace, 1 - TOL["ni_year"], 1 + TOL["ni_year"],
        f"модель {ni_year:.1f} при темпе {pace:.1f} ({float(last['net_profit_ytd']['v']):.1f} × 12 / {n_months}; {100 * (ni_year / pace - 1):+.1f} %; "
        f"допуск ±{100 * TOL['ni_year']:.0f} %); прибыль акционеров {float(L.year_flow(run, prob, 'ni_sh', year)):.1f}")
    # ---- (а) мир уровня: маржа + прочие (определение банка) против суммы окна L — по ключу и по пути клеток
    world = str(book.get("nii.transmission.level_world"))
    iea0 = float(facts.need("balance", "iea"))
    nss = float(ctx.bridge.to_mgmt_nim(float(ctx.transmission.nss[world])))
    misc_lt = Trajectory(book.get("other.misc_net_real")).value(tl.last_year, 4)
    cash = sum(float(facts.file("balance")["other_assets_parts"][name]["v"]) for name in all_inputs["capital"]["zero_weight_cash_parts"])
    wide = 1.0 + cash / iea0                 # знаменатель с денежными средствами и обязательными резервами к знаменателю движка (якорь)
    s_model = nss + (misc_lt + diff) / iea0
    l_nim = sum(inputs["window_l_nim_quarters"]) / len(inputs["window_l_nim_quarters"])
    tail = inputs["other_on_current_tail_bank_def"]
    lo, hi = (l_nim + float(x) / iea0 for x in tail)
    window_words = (f"при сумме окна L {100 * lo:.2f}…{100 * hi:.2f} % (маржа окна {100 * l_nim:.2f} % в знаменателе движка, собственный состав окна, + прочие "
                    f"{tail[0]:.0f}…{tail[1]:.0f})")
    add(f"(а) по ключу: «ЧПД + прочие» стационара мира {world} не выше суммы окна L на нынешнем хвосте", s_model, 0.0, lo,
        f"модель {100 * s_model:.2f} % процентных активов (маржа {100 * nss:.2f} % на составе якоря + прочие в определении банка {misc_lt + diff:.0f} млрд ₽) "
        + window_words)
    years = list(range(tl.last_year - STATIONARY_YEARS + 1, tl.last_year + 1))
    mass = sum(prob[c.key] for c in run.cells if c.world == world)
    of_world = {c.key: (prob[c.key] / mass if c.world == world else 0.0) for c in run.cells}
    qs = [i for y in years for i in tl.quarters_of_year(y)]
    days = sum(tl.d(i) for i in qs)
    iea_path = sum(float(L.expect(run, of_world, "iea_avg", i)) * tl.d(i) for i in qs) / days
    nii_path = sum(float(L.expect(run, of_world, "nii", i)) for i in qs) * 365.0 / days / iea_path
    other_path = (sum(float(L.expect(run, of_world, n, i)) for i in qs for n in ("ins", "misc")) + addback * len(qs) / 4) * 365.0 / days / iea_path
    # разложение уровня пути (решение ведущего № 4, п. 3.5): уровень на составе якоря; состав баланса; бесплатные пассивы (капитал /
    # постоянные активы / прочее) — ставки книг пути, движок; ожидание по клеткам с вероятностями мира
    nbooks = book.get("nii.books")
    bal_books = facts.file("balance")["books"]
    anchor_bal = {b: float(bal_books[b]["v"]) for b in nbooks}
    at1, nci_bal = float(ctx.prep.af.at1), float(ctx.prep.af.nci)
    oa_fixed = float(book.opt("volumes.other_assets_fixed", 0.0))

    def parts_of(prob_map: dict, quarters: list[int]) -> dict:
        acc: dict = {}
        mass = sum(prob_map.values())
        for c in run.cells:
            pw = prob_map.get(c.key, 0.0)
            if pw <= 0:
                continue
            pp = level_parts(c, quarters, nbooks, anchor_bal, at1, nci_bal, oa_fixed)
            for k in ("level", "mix", "free", "path", "print"):
                acc[k] = acc.get(k, 0.0) + pw * pp[k] / mass
            for k, v in pp["free_split"].items():
                acc.setdefault("free_split", {})[k] = acc.get("free_split", {}).get(k, 0.0) + pw * v / mass
        return acc

    dec = parts_of(of_world, qs)
    level_words = (f"уровень на составе якоря {100 * dec['level']:.2f} % + состав баланса {100 * dec['mix']:+.2f} + бесплатные пассивы "
                   f"{100 * dec['free']:+.2f} п.п. (капитал {100 * dec['free_split']['capital']:+.2f}, постоянные активы {100 * dec['free_split']['fixed_assets']:+.2f}, "
                   f"прочее {100 * dec['free_split']['other']:+.2f}) = {100 * dec['path']:.2f} % по ставкам книг; в печати клетки (с АСВ и общим сдвигом) "
                   f"{100 * dec['print']:.2f} %")
    add(f"(а) по пути клеток: «ЧПД + прочие» клеток мира {world} за {years[0]}–{years[-1]} годы не выше суммы окна L", nii_path + other_path, 0.0, lo,
        f"модель {100 * (nii_path + other_path):.2f} % средних процентных активов клеток (маржа пути {100 * nii_path:.2f} % + прочие {100 * other_path:.2f} %; "
        f"ожидание по клеткам мира {world}) " + window_words + f"; маржа пути выше ключа уровня на {100 * (nii_path - nss):+.2f} п.п. — разложение (решение "
        "№ 4, п. 3.5): " + level_words)
    add(f"(а) справочно: разложение уровня пути мира {world} за {years[0]}–{years[-1]} годы — уровень на составе якоря, состав баланса, бесплатные пассивы",
        dec["path"], -1.0, 1.0, level_words + "; уровень на составе якоря сторожат строки (а) по ключу и уровни слоя (решение № 3, п. 5.4)")
    by_world_dec = {}
    for w_ in book.get("worlds.ids"):
        m_ = sum(prob[c.key] for c in run.cells if c.world == w_)
        by_world_dec[w_] = parts_of({c.key: (prob[c.key] / m_ if c.world == w_ else 0.0) for c in run.cells}, qs)
    add(f"(а) справочно: разложение уровня пути по мирам за {years[0]}–{years[-1]} годы (уровень + состав + бесплатные пассивы)", 0.0, -1.0, 1.0,
        "; ".join(f"{w_} {100 * d['level']:.2f} {100 * d['mix']:+.2f} {100 * d['free']:+.2f} (капитал {100 * d['free_split']['capital']:+.2f}, постоянные "
                  f"активы {100 * d['free_split']['fixed_assets']:+.2f}) = {100 * d['path']:.2f} %" for w_, d in by_world_dec.items()))
    # сторож cir_lt: расходы к доходам слоя «рыночные ставки как есть» на составе якоря против пути (решение № 4, пп. 3.5 и 3.9)
    gate = L.cir_lt_value(run)
    layer = dict(run.layers["macro_neutral"].prob)
    cir_years = list(range(int(book.get("checks.cir_lt")["from_year"]), tl.last_year + 1))
    cir_q = [i for y in cir_years for i in tl.quarters_of_year(y)]
    opex_l = sum(layer[c.key] * abs(float(c.quarters["opex"][i])) for c in run.cells for i in cir_q)
    inc_l = sum(layer[c.key] * sum(float(c.quarters[n][i]) for n in ("nii", "fees", "ins", "misc", "fvr")) for c in run.cells for i in cir_q)
    shift = {"mix": 0.0, "free": 0.0}
    for c in run.cells:
        if layer.get(c.key, 0.0) <= 0:
            continue
        for y in cir_years:
            yq = tl.quarters_of_year(y)
            pp = level_parts(c, yq, nbooks, anchor_bal, at1, nci_bal, oa_fixed)
            iea_y = sum(float(c.quarters["iea_avg"][i]) for i in yq) / len(yq)
            shift["mix"] += layer[c.key] * pp["mix"] * iea_y
            shift["free"] += layer[c.key] * pp["free"] * iea_y
    cir_engine = opex_l / inc_l
    cir_anchor = opex_l / (inc_l - shift["mix"] - shift["free"])
    cir_no_free = opex_l / (inc_l - shift["free"])
    add(f"сторож cir_lt: расходы к доходам слоя «рыночные ставки как есть» за {cir_years[0]}–{cir_years[-1]} годы — на составе якоря против пути",
        float(gate["value"]) + (cir_anchor - cir_engine), float(gate["target"]) - float(gate["tolerance"]), float(gate["target"]) + float(gate["tolerance"]),
        f"гейт {100 * float(gate['value']):.1f} % (определение банка) при цели {100 * float(gate['target']):.0f} ± {100 * float(gate['tolerance']):.0f} п.п.; "
        f"без вклада бесплатных пассивов {100 * (float(gate['value']) + cir_no_free - cir_engine):.1f} %, на составе якоря (без вклада состава баланса и "
        f"бесплатных пассивов) {100 * (float(gate['value']) + cir_anchor - cir_engine):.1f} % — разложение причины (решение № 4, п. 3.5): цель стоит на "
        "составе якоря, путь несёт рост капитала и разводнение постоянных активов; сторож — рукой, цель не выводится")

    # ---- (б) ближний путь смеси заголовка: (ЧПД + страховая строка + прочее + разность определений) к средним процентным активам
    def near_sum(quarters: list[int]) -> float:
        flow = sum(float(L.expect(run, prob, n, i)) for i in quarters for n in ("nii", "ins", "misc")) + addback * len(quarters) / 4
        d = sum(tl.d(i) for i in quarters)
        iea = sum(float(L.expect(run, prob, "iea_avg", i)) * tl.d(i) for i in quarters) / d
        return flow / (iea * wide) * 365.0 / d

    s_h2 = near_sum([i for i in tl.quarters_of_year(year) if i >= 1])
    s_next = near_sum(tl.quarters_of_year(year + 1))
    win = window_c(facts, inputs)
    _, regime_b, scenario_b = modal_cell(book, ctx.posterior)
    cell_b = run.cell(WINDOW_WORLD, WINDOW_REGIME, scenario_b)
    s_cell = window_sum(cell_b.quarters, tl.quarters_of_year(year + 1), tl, wide, addback)
    add(f"(б) «ЧПД + прочие» ближнего пути, {year + 1} год, внутри окна C (1К–2К + июль–август {year} года)", s_next, win["low"], win["high"],
        f"смесь заголовка {100 * s_next:.2f} % процентных активов с денежными средствами (знаменатель окна разбора; в знаменателе движка "
        f"{100 * s_next * wide:.2f} %) при окне C {100 * win['low']:.2f}…{100 * win['high']:.2f} % (без разового результата 1К и с ним; середина "
        f"{100 * win['mid']:.3f} %, темп апреля–августа {100 * win['apr_aug']:.2f} %; окно только 1-го полугодия — {100 * NEAR_WINDOW_H1[0]:.1f}…"
        f"{100 * NEAR_WINDOW_H1[1]:.1f} %, справочно); клетка условий окна {cell_b.label} — {100 * s_cell:.3f} % (ближний ключ прочих доходов "
        f"выведен под середину окна: решение № 4, п. 3.6); справочно 2-е полугодие {year} года — {100 * s_h2:.2f} % ({100 * s_h2 * wide:.2f} % в "
        "знаменателе движка): несёт факт восьми месяцев, окном не судится")
    # ---- 1(а) маржа ближнего года (устав §5, п. 1(а): окно C 2,6–3,2 %) — судится на режиме «нормализация» (решение № 6, п. 2.3: как
    #      стоимость риска того же года — решения № 2, п. 3.4, и № 3, п. 6.1 — смесь заголовка несёт год шока); смесь заголовка, модальная
    #      клетка и клетка условий окна печатаются рядом, нормой не служат
    def cond(pred) -> dict:
        m_ = sum(prob[c.key] for c in run.cells if pred(c))
        return {c.key: (prob[c.key] / m_ if pred(c) and m_ else 0.0) for c in run.cells}

    def nim_of(prob_map: dict, quarters: list[int]) -> float:
        d = sum(tl.d(i) for i in quarters)
        nii = sum(float(L.expect(run, prob_map, "nii", i)) for i in quarters)
        iea = sum(float(L.expect(run, prob_map, "iea_avg", i)) * tl.d(i) for i in quarters) / d
        return float(ctx.bridge.to_mgmt_nim(nii * 365.0 / d / iea))

    q_next = tl.quarters_of_year(year + 1)
    m_key = modal_cell(book, ctx.posterior)
    nim_rows = {"norm": cond(lambda c: c.regime == WINDOW_REGIME), "mix": prob,
                "modal": {c.key: (1.0 if c.key == m_key else 0.0) for c in run.cells},
                "window_cell": cond(lambda c: c.world == WINDOW_WORLD and c.regime == WINDOW_REGIME)}
    nim_next = {name: nim_of(p, q_next) for name, p in nim_rows.items()}
    nim_q_mix = [nim_of(prob, [i]) for i in q_next]
    add(f"1(а) маржа {year + 1} года на режиме «нормализация» внутри окна C {100 * NIM_WINDOW[0]:.1f}–{100 * NIM_WINDOW[1]:.1f} % (устав §5, п. 1(а); "
        "решение № 6, п. 2.3)", nim_next["norm"], NIM_WINDOW[0], NIM_WINDOW[1],
        f"режим «нормализация» (все миры и сценарии, вероятности точки) {100 * nim_next['norm']:.2f} % (упр. базис); рядом, нормой не служат: смесь "
        f"заголовка {100 * nim_next['mix']:.2f} % (несёт год шока; по кварталам " + " / ".join(f"{100 * v:.2f}" for v in nim_q_mix)
        + f"), модальная клетка {'/'.join(m_key)} {100 * nim_next['modal']:.2f} %, клетка условий окна {WINDOW_WORLD} × «нормализация» "
        f"{100 * nim_next['window_cell']:.2f} %")
    # ---- (в) доля прочих в чистых операционных доходах последних лет сетки, миры N и H
    _, regime, scenario = modal_cell(book, ctx.posterior)
    for w in ("N", "H"):
        one = {c.key: (1.0 if c.key == (w, regime, scenario) else 0.0) for c in run.cells}
        other = sum(float(L.year_flow(run, one, n, y)) for y in years for n in ("ins", "misc")) + addback * len(years)
        income = other + sum(float(L.year_flow(run, one, n, y)) for y in years for n in ("nii", "fees"))
        add(f"(в) доля прочих в доходах стационара мира {w} ({years[0]}–{years[-1]})", other / income, SHARE_WINDOW[0], SHARE_WINDOW[1],
            f"{100 * other / income:.1f} % при {100 * SHARE_WINDOW[0]:.0f}…{100 * SHARE_WINDOW[1]:+.0f} % в годы нормальной маржи (клетка {w}/{regime}/{scenario})")
    # ---- 1(г) путь клетки мира-опоры против пути бэктеста книг — СУДИТСЯ НА СОСТАВЕ ЯКОРЯ, как строка (а) (решение № 5, п. 3.5): маржа клетки без
    #      вклада состава баланса и бесплатных пассивов (бэктест книг посчитан на составе якоря); рядом — путь клетки как есть и разложение средней
    #      разности: σ0 (маржа клетки минус маржа той же клетки без σ0 в ближних годах), состав, капитал, постоянные активы, прочее бесплатных
    #      пассивов (free_split.other), общий ближний сдвиг; остаток — уровень ставок книг на составе якоря и АСВ (слагаемые сходятся к средней)
    bt = all_inputs["backtest_path"]
    cell = run.cell(bt["world"], regime, scenario)
    periods = bt["periods"][:BACKTEST_QUARTERS]
    idx = [tl.index(p) for p in periods]
    path = [float(cell.quarters["nim"][i]) for i in idx]
    gaps = [m - b for m, b in zip(path, bt["nim"][:BACKTEST_QUARTERS])]
    rms_path = math.sqrt(sum(g * g for g in gaps) / len(gaps))
    qparts = [level_parts(cell, [i], nbooks, anchor_bal, at1, nci_bal, oa_fixed) for i in idx]
    from model.cell import run_cell
    from model.grid import make_context
    off = run_cell(make_context(book.with_overrides({"nii.sigma0_from": tl.last_year}), facts), bt["world"], regime, scenario)
    near_t = Trajectory(book.get("regimes.near_nim_shift"))
    parts = []
    for i, g, pp in zip(idx, gaps, qparts):
        y, k = tl.year(i), int(tl.period(i)[-1])
        row = {"gap": g, "sigma0": float(cell.quarters["nim"][i]) - float(off.quarters["nim"][i]), "mix": pp["mix"],
               "capital": pp["free_split"]["capital"], "fixed_assets": pp["free_split"]["fixed_assets"], "other": pp["free_split"]["other"],
               "shift": float(near_t.value(y, k))}
        row["rest"] = g - sum(row[n] for n in ("sigma0", "mix", "capital", "fixed_assets", "other", "shift"))
        parts.append(row)
    on_anchor = [r["gap"] - r["mix"] - r["capital"] - r["fixed_assets"] - r["other"] for r in parts]
    rms = math.sqrt(sum(g * g for g in on_anchor) / len(on_anchor))
    avg = {n: sum(r[n] for r in parts) / len(parts) for n in ("gap", "sigma0", "mix", "capital", "fixed_assets", "other", "shift", "rest")}
    add(f"1(г) путь маржи клетки мира-опоры {bt['world']} против пути бэктеста книг, {len(gaps)} кварталов, на составе якоря (RMS отклонения)", rms, 0.0,
        float(bt["rmse"]),
        f"RMS на составе якоря {100 * rms:.2f} п.п. (путь клетки без вклада состава баланса и бесплатных пассивов; бэктест — на составе якоря) при ошибке "
        f"бэктеста книг на фактической ключевой {100 * float(bt['rmse']):.2f} п.п. (лист: форма ядра на составе якоря — {100 * float(bt['sheet_core_form_rms']):.2f} "
        f"п.п.); путь клетки как есть — RMS {100 * rms_path:.2f}; по кварталам, клетка − бэктест (на составе якоря / как есть): "
        + ", ".join(f"{p} {100 * a:+.2f} / {100 * g:+.2f}" for p, a, g in zip(periods, on_anchor, gaps))
        + f"; разложение средней разности {100 * avg['gap']:+.3f} п.п. (решение № 5, п. 3.5): σ0 {100 * avg['sigma0']:+.3f}, состав баланса {100 * avg['mix']:+.3f}, "
        f"капитал {100 * avg['capital']:+.3f}, постоянные активы {100 * avg['fixed_assets']:+.3f}, прочее бесплатных пассивов {100 * avg['other']:+.3f}, "
        f"общий ближний сдвиг {100 * avg['shift']:+.3f}, остаток (уровень ставок книг на составе якоря и АСВ) {100 * avg['rest']:+.3f} — сумма "
        f"{100 * sum(avg[n] for n in ('sigma0', 'mix', 'capital', 'fixed_assets', 'other', 'shift', 'rest')):+.3f}; по кварталам σ0 / сдвиг: "
        + ", ".join(f"{p} {100 * r['sigma0']:+.2f} / {100 * r['shift']:+.2f}" for p, r in zip(periods, parts)))
    # ---- B14б: предельный корпоративный кредит на предельной единице модели (решение № 4, п. 3.7); сверочная строка — разность ядра
    import marginal_loan
    marginal = marginal_loan.compute(book_path, facts_dir)
    neutral = marginal["neutral"]
    add(f"B14б предельный кредит юрлицам в мире {neutral['world']} на предельной единице модели (норма): отдача минус стоимость капитала",
        neutral["model"], -neutral["band"], neutral["band"],
        f"{100 * neutral['return_model']:.1f} % при стоимости капитала {100 * neutral['cost_of_equity']:.1f} %: {100 * neutral['model']:+.1f} п.п. при норме "
        f"±{100 * neutral['band']:.0f} п.п. (рубль несёт прочие активы, прочие обязательства и резерв; фондируется балансирующей статьёй; капитал — Н20.0, "
        f"весь базовый); разность ядра — {100 * neutral['core_difference']:.1f} %; справочно прежние чтения: на базовом капитале со слоями на фондировании ядра "
        f"{100 * neutral['return_core']:.1f} % ({100 * neutral['core']:+.1f} п.п.), на оптовом {100 * neutral['return_wholesale']:.1f} %. Ключи к норме не подбираются")
    low, high = marginal["sanity"]["segment_low"], marginal["sanity"]["segment_high"]
    tol = float(marginal["inputs"]["probe"]["match_tol"])
    for w, table in marginal["marginal"]["corporate_loan"].items():
        r = table[0]
        add(f"B14б предельный кредит юрлицам в мире {w} на предельной единице модели: отдача в пределах нормы", r["return_model"], low, high,
            f"{100 * r['return_model']:.1f} % при норме {100 * low:.0f}…{100 * high:.0f} % (стоимость капитала мира {100 * r['cost_of_equity']:.1f} %; кредит — ключевая "
            f"{100 * r['loan_spread_to_key']:+.2f} п.п.; капитал на рубль кредита {r['capital_per_ruble_model']:.3f}); справочно прежние чтения — базовый капитал "
            f"со слоями {100 * r['return_core_base']:.1f} %, весь капитал без связок баланса {100 * r['return_core']:.1f} %")
        cd = r["core_difference"]
        add(f"B14б сверка: аналитика листа против разности ядра в модальной клетке мира {w} (премия кредитов юрлиц +1 п.п.)", r["match"], -tol, tol,
            f"аналитика {100 * r['return_model']:.1f} %, разность ядра {cd['year']} года {100 * cd['return']:.1f} % (Δ прибыли {cd['d_ni_sh']:.1f} / капитал "
            f"на ΔRWA {cd['d_rwa_avg']:.0f}; на ΔBV — {100 * cd['return_on_bv']:.1f} %): {100 * r['match']:+.2f} п.п. при допуске ±{100 * tol:.0f} п.п.")
    g = marginal["grid_probe"]
    add("B14б справочно: ответ сетки на премию кредитов юрлиц +1 п.п. в 2027–2031 годах, ₽", g["point"], -100.0, 100.0,
        f"точка {g['point']:+.2f} ₽; миры " + ", ".join(f"{w} {v:+.2f}" for w, v in g["by_world"].items())
        + " ₽; свойство механики: прочие активы (деньги, обязательные резервы) и прочие обязательства привязаны к кредитам, а не к средствам клиентов "
        "(отсюда «только кредиты −5,9 ₽ / только средства +5,4 ₽» третьего круга)")
    # ---- 1(д) рост кредитов и RWA в условиях окна (клетка «мир окна × нормализация»); смесь заголовка — рядом, справочно;
    #      внешний капитал лет ступеней требования
    end_of = lambda pr, name, y: float(L.quarter_end(run, pr, name, tl.quarters_of_year(y)[-1]))  # noqa: E731
    end = lambda name, y: end_of(prob, name, y)  # noqa: E731
    growth = lambda pr, name, y: end_of(pr, name, y) / end_of(pr, name, y - 1) - 1  # noqa: E731
    window_cell = (WINDOW_WORLD, WINDOW_REGIME, scenario)
    one_cell = {c.key: (1.0 if c.key == window_cell else 0.0) for c in run.cells}
    mass_norm = sum(prob[c.key] for c in run.cells if c.regime == WINDOW_REGIME)
    norm_all = {c.key: (prob[c.key] / mass_norm if c.regime == WINDOW_REGIME else 0.0) for c in run.cells}
    for name, title, window, source in (("loans", "кредитов", LOANS_WINDOW, "прогноз банка на 2026 год +5 % … факт года до якоря +7 %"),
                                        ("rwa", "RWA", RWA_WINDOW, "факт 1-го полугодия 2026 года −1,7 % (−3,4 % в год) … рост кредитов за год +7 %")):
        for y in GROWTH_YEARS:
            g = growth(one_cell, name, y)
            add(f"1(д) рост {title} в условиях окна (клетка {'/'.join(window_cell)}) за {y} год", g, window[0], window[1],
                f"{100 * g:+.1f} % ({end_of(one_cell, name, y - 1):.0f} → {end_of(one_cell, name, y):.0f} млрд ₽) при окне фактов "
                f"{100 * window[0]:+.1f}…{100 * window[1]:+.1f} % ({source}); справочно: режим «нормализация» по мирам "
                f"{100 * growth(norm_all, name, y):+.1f} %, смесь заголовка {100 * growth(prob, name, y):+.1f} % (несёт год шока — нормой не служит)")
    node = L.recap_node(run)
    if node is not None:
        idx = [node["years"].index(y) for y in RECAP_YEARS]
        mix = sum(float(node["mix"]["rec"][i]) for i in idx)
        modal = sum(float(node["modal_cell"]["rec"][i]) for i in idx)
        by_year = ", ".join(f"{y} — {float(node['mix']['rec'][i]):.0f}" for y, i in zip(RECAP_YEARS, idx))
        words = (f"взносы смеси заголовка {mix:.0f} млрд ₽ ({by_year}); модальная клетка {node['modal_cell']['cell']} — {modal:.0f}; сверх выпуска по 87 ₽ "
                 "(значение книги, не взнос модели)")
        add(f"1(д) внешний капитал {RECAP_YEARS[0]}–{RECAP_YEARS[-1]} годов внутри {RECAP_WINDOW[0]:.0f}–{RECAP_WINDOW[1]:.0f} млрд ₽", mix,
            RECAP_WINDOW[0], RECAP_WINDOW[1],
            words + f"; лист capital r2 при росте книг 5 % в год: {RECAP_SHEET[0]:.0f} (план банка по прибыли) … {RECAP_SHEET[1]:.0f} (темп восьми месяцев); "
            f"менеджмент: до {RECAP_WORDS:.0f} млрд ₽ в капитал за эти годы")
    later = ", ".join(f"{y}: кредиты {100 * (end('loans', y) / end('loans', y - 1) - 1):+.1f} %, RWA {100 * (end('rwa', y) / end('rwa', y - 1) - 1):+.1f} %"
                      for y in LATER_YEARS)
    g_last = end("loans", LATER_YEARS[-1]) / end("loans", LATER_YEARS[-1] - 1) - 1
    add(f"1(д) справочно: рост смеси заголовка после {GROWTH_YEARS[-1]} года (суждение с ценой, окном фактов не судится)", g_last, -1.0, 1.0,
        later + "; цена суждения — справочные варианты «рост кредитов выше / ниже на 1 п.п. в год на всём горизонте» и ось роста после "
        f"{GROWTH_YEARS[-1]} года")
    return {"book": {"version": str(book.get("meta.version")), "date": str(book.get("meta.date"))}, "fact_period": FACT_PERIOD,
            "months": [m["month"] for m in known], "rows": rows}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="приёмочные проверки книги на её фактах")
    ap.add_argument("--book", type=Path, default=None)
    ap.add_argument("--facts", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    try:
        res = rows_of(a.book, a.facts)
    except Exception as exc:
        print(f"ОТКАЗ листа ({type(exc).__name__}): {exc}")
        return 1
    for row in res["rows"]:
        print(f"{'ок ' if row['ok'] else 'НЕТ'}  {row['name']}: {row['words']}")
    if a.out is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
