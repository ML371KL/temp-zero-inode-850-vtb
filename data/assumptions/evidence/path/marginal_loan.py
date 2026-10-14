# -*- coding: utf-8 -*-
"""Предельная единица роста книги ВТБ: рубль корпоративного кредита НА ПРЕДЕЛЬНОЙ ЕДИНИЦЕ САМОЙ МОДЕЛИ (проверка, ключей не пишет).

Норма — решение ведущего № 3, раздел 4 (та же): отдача предельного корпоративного кредита — не ниже 5 % и не выше 30 % в каждом
мире, около нейтрального в мире H (±5 п.п. к стоимости капитала). Ключи к норме не подбираются. Базис — решение ведущего № 4,
п. 3.7 (рекомендация проверяющего находки B-3 третьего круга): рубль кредита несёт то, что ядро к нему привязывает, фондируется
балансирующей статьёй ядра, капитал — по нормативу, связывающему в модальном пути (сейчас Н20.0, весь — базовый: бессрочные —
константа якоря, дополнительный капитал — замороженная траектория, на рост сверх пути не отвечают).

СВОЙСТВО МЕХАНИКИ (словами листа): ядро привязывает к КРЕДИТАМ, а не к средствам клиентов, прочие активы (растущая часть: деньги
и обязательные резервы, активы НПФ, НМА, основные средства — volumes.other_assets_to_loans, без дохода, со своей плотностью RWA),
прочие обязательства (volumes.other_liabilities_to_loans, без цены) и резерв (credit.allowance_ratio). Поэтому рубль кредита тянет
за собой бездоходные активы и капитал под них, а рубль средств клиентов кладётся в бумаги с малым RWA и стоит как средний: отсюда
асимметрия проб сетки «только кредиты −5,9 ₽ / только средства +5,4 ₽» (третий круг; решение № 4, п. 3.7). Ошибка ли привязка
резервов к кредитам — отдельное суждение с осью, не повод двигать ключи к норме.

Предельная единица (стационар мира: долгосрочные ставки книг — решение передачи ядра; модальный режим и сценарий), на рубль кредита:
    прочие активы  oa = other_assets_to_loans          (дохода нет; плотность RWA other_assets)
    прочие обяз.   ol = other_liabilities_to_loans     (цены нет)
    резерв         al = allowance_ratio                (уменьшает чистые активы)
    ликвидность    Δla = −(1 − al + oa − ol − k)       (балансирующая статья ядра: бумаги и доходная ликвидность в доле книги;
                                                         у минимума ликвидности — доп. опт; в модальных клетках доп. опта нет)
    RWA            ΔRWA = dn × [ω_кредит + oa × ω_прочие + Δla × (s × ω_бумаги + (1 − s) × ω_ликв)]
    капитал        k = r × ΔRWA,  r = требование Н20.0 сценария + путь вычета сценария (п.п. RWA) + растущая часть вычета якоря / RWA якоря
    до налога      = доходность кредита − стоимость риска юрлиц + Δla × доходность балансирующей смеси
    отдача         = до налога × (1 − налог) × (1 − доля меньшинства) / k
Сверочная строка — разность ядра в модальной клетке мира при премии роста кредитов юрлиц +1 п.п. в год (годы окна сверки):
Δ прибыли акционеров года сверки / (r × Δ RWA, среднее концов кварталов года); аналитика обязана совпасть с ней до 1 п.п.
(расхождение — связи комиссий и расходов с объёмом и путь ставок, которых аналитика не несёт). Рядом — ответ сетки на ту же
премию (точка и миры, ₽).

Справочно (прежние чтения, решение № 4, п. 3.7): «на базовом капитале со слоями по своей цене» (решение № 2, п. 7.6: бессрочные —
ключевая + 5 п.п., дополнительный капитал — цена опта; экономика банка, который выпускает бессрочные и субординированные инструменты
под рост, — модель так не умеет) и «на весь капитал норматива без связок баланса»; обе — на фондировании ядра и на оптовом.

Запуск из корня репозитория:
  python -B data/assumptions/evidence/path/marginal_loan.py [--book КНИГА] [--facts КАТАЛОГ] [--out ФАЙЛ] [--no-write]
Код выхода: 0 — посчитано; 2 — ядро ещё не исполняет ветви книги; 1 — отказ книги или фактов.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOAN_BOOK = "corp_loans"
LOAN_PREMIUM = "volumes.loan_share_drift.corporate"
SANITY = (0.05, 0.30)                     # решение № 3, раздел 4: не ниже 5 % и не выше 30 % в каждом мире
SCHEDULE = "schedule"
AT1_LAYER = 0.015                         # слой добавочного капитала, доля RWA: минимум основного капитала 6,0 % против базового 4,5 % [Ф: 220-И, п. 2.2]
AT1_SPREAD = 0.05                         # предельная цена бессрочного инструмента к ключевой: «ключевая + 5 %» — три рублёвых выпуска 2-го квартала
#                                           2026 года на 121,0 млрд ₽ [Ф: лист calib-capital/r2, раздел 6; sheets/at1_coupon_bridge_r2.csv]
NEUTRAL_WORLD = "H"                       # норма: около нейтрального в мире H (решения № 2, п. 7.6; № 3, раздел 4)
NEUTRAL_BAND = 0.05                       # ±5 п.п. от стоимости капитала
PROBE_YEARS = ("2027", "2028", "2029", "2030", "2031")   # годы премии сверочной строки (рост сверх пути — годы окна и схода)
PROBE_STEP = 0.01                         # +1 п.п. в год к премии роста кредитов юрлиц
CHECK_YEAR = 2034                         # год сверки: стационар ставок миров, после лет премии
MATCH_TOL = 0.01                          # аналитика совпадает с разностью ядра до 1 п.п. (решение № 4, п. 3.7)


class NeedCore(RuntimeError):
    """Ядро не готово: нет ветви, ряда клетки или функции."""


def repo_root() -> Path:
    root = HERE
    while not (root / "model" / "book.py").exists():
        if root.parent == root:
            raise NeedCore("не найден каталог model/ выше листа — запуск из дерева репозитория")
        root = root.parent
    return root


def pc(x: float, n: int = 1) -> str:
    return f"{100 * float(x):.{n}f}"


def compute(book_path: Path | None, facts_dir: Path | None) -> dict:
    root = repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from model.book import load_book, load_facts
    except ImportError as exc:
        raise NeedCore(f"ядро ещё не исполняет ветви книги: {exc}") from exc
    facts = load_facts(facts_dir)
    book = load_book(book_path, facts=facts)
    return compute_on(book, facts)


def _premium_traj(book, step: float) -> dict:
    """Траектория премии роста кредитов юрлиц +`step` в годы сверки (остальные ключи — книги)."""
    from model.paths import Trajectory
    have = book.get(LOAN_PREMIUM)
    tr = Trajectory(have)
    traj = {k: v for k, v in have.items()}
    for y in PROBE_YEARS:
        traj[y] = round(float(tr.year_value(int(y))) + step, 6)
    return traj


def compute_on(book, facts) -> dict:
    """То же на загруженной книге (с подменами в памяти — пробные счёты концов осей)."""
    from model.book import anchor_facts
    from model.cell import run_cell
    from model.grid import make_context, modal_cell, point_probabilities, run_grid
    from model.live import live_from_book
    from model.paths import Trajectory
    ctx = make_context(book, facts)
    tr, tl, prep = ctx.transmission, ctx.timeline, ctx.prep
    af = anchor_facts(facts, book.get("nii.books"))
    books = book.get("nii.books")
    last = tl.last_year
    lt = lambda b: Trajectory(books[b]["spread"]).value(last, 4)  # noqa: E731
    sec_share = float(prep.sec_share)
    dens = book.get("capital.rwa.density")
    d_loan, d_oa, d_sec, d_liq = (float(dens[k]) for k in (LOAN_BOOK, "other_assets", "securities", "liquidity"))
    d_bal = sec_share * d_sec + (1 - sec_share) * d_liq
    dn = float(prep.dn[tl.Q])
    oa, ol, al = float(prep.oa_ratio), float(prep.ol_ratio), float(prep.allowance_ratio)
    tau = Trajectory(book.get("tax.statutory")).value(last, 4) + float(book.get("tax.effective_gap"))
    nci = float(book.get("pnl.nci_share"))
    _, regime, scenario = modal_cell(book, ctx.posterior)
    cor_mgmt = Trajectory(book.get(f"regimes.{regime}.cor")).value(last, 4)
    cor_eng = float(ctx.bridge.to_engine_cor(cor_mgmt))
    seg = book.get("credit.segment_relative")
    loans = {b: af.balances[b] for b, spec in books.items() if spec.get("cor_segment")}
    rel = {b: float(seg[books[b]["cor_segment"]]) for b in loans}
    norm = sum(loans[b] * rel[b] for b in loans) / sum(loans.values())
    cor_loan = cor_eng * rel[LOAN_BOOK] / norm if seg.get("enabled") else cor_eng
    keep = (1 - tau) * (1 - nci)
    cap = prep.cap
    grow_rate = (cap.parts.grow20 if cap.parts is not None else cap.ded20_0) / cap.rwa0     # растущая часть вычета якоря к RWA якоря
    cells = {w: run_cell(ctx, w, regime, scenario) for w in book.get("worlds.ids")}
    first = next(iter(cells))
    ends = {s: run_cell(ctx, first, regime, s).quarters for s in dict.fromkeys((scenario, SCHEDULE))}
    floors = {s: float(q["req20"][tl.Q]) for s, q in ends.items()}
    floors11 = {s: float(q["req11"][tl.Q]) for s, q in ends.items()}
    ded_pp = {s: Trajectory(book.get(f"capital.reg_scenarios.{s}.deduction_pp.n20_0")).value(last, 4) for s in floors}
    rate = {s: floors[s] + ded_pp[s] - float(cap.gap20) + grow_rate for s in floors}     # капитал на рубль RWA, связывающий Н20.0
    # сверочная строка: разность ядра в модальной клетке мира при премии роста кредитов юрлиц +1 п.п. в годы сверки
    probe_book = book.with_overrides({LOAN_PREMIUM: _premium_traj(book, PROBE_STEP)}, create=True)
    ctx_p = make_context(probe_book, facts)
    qs = tl.quarters_of_year(CHECK_YEAR)
    ends_q = [qs[0] - 1] + qs
    table, flat, model_returns = {}, [], []
    for w, cell in cells.items():
        key = float(tr.key_lt[w])
        y_loan = key + float(tr.lt_spread[LOAN_BOOK][w])
        r_wh = key + lt("wholesale")
        r_core = sec_share * (key + lt("securities")) + (1 - sec_share) * (key + lt("liquidity"))
        row = {"year": "стационар", "world": w, "key_lt": key, "loan_yield": y_loan, "loan_spread_to_key": float(tr.lt_spread[LOAN_BOOK][w]),
               "funding_wholesale": r_wh, "funding_core": r_core, "cor_loan": cor_loan, "cost_of_equity": float(cell.k_t)}
        # предельная единица модели (решение № 4, п. 3.7)
        for s in floors:
            r = rate[s]
            b_need = 1.0 - al + oa - ol
            d_rwa = dn * (d_loan + oa * d_oa - d_bal * b_need) / (1.0 - dn * d_bal * r)
            k = r * d_rwa
            la = -(b_need - k)
            pre = y_loan - cor_loan + la * r_core
            ret = pre * keep / k
            tail = "" if s == scenario else f"_{s}"
            row[f"return_model{tail}"] = ret
            if s == scenario:
                parts = {"loan_margin": (y_loan - cor_loan - (1.0 - k) * r_core) * keep / k,          # кредит минус балансирующая смесь на (1 − k)
                         "other_assets": -oa * r_core * keep / k, "other_liabilities": ol * r_core * keep / k, "allowance": al * r_core * keep / k}
                row.update(capital_per_ruble_model=k, rwa_per_ruble_model=d_rwa, liquid_per_ruble=la, capital_rate=r, pre_tax_model=pre,
                           model_parts=parts)
            flat.append(ret)
        model_returns.append(row["return_model"])
        # разность ядра: та же клетка при премии +1 п.п.
        base_q, probe_q = cell.quarters, run_cell(ctx_p, w, regime, scenario).quarters
        d_ni = sum(float(probe_q["ni_sh"][i]) - float(base_q["ni_sh"][i]) for i in qs)
        d_rwa_avg = sum(float(probe_q["rwa"][i]) - float(base_q["rwa"][i]) for i in ends_q) / len(ends_q)
        d_bv_avg = sum(float(probe_q["bv"][i]) - float(base_q["bv"][i]) for i in ends_q) / len(ends_q)
        d_loans = (float(probe_q["loans"][qs[-1]]) - float(base_q["loans"][qs[-1]]))
        row["core_difference"] = {"year": CHECK_YEAR, "d_ni_sh": d_ni, "d_rwa_avg": d_rwa_avg, "d_bv_avg": d_bv_avg, "d_loans_end": d_loans,
                                  "return": d_ni / (rate[scenario] * d_rwa_avg) if d_rwa_avg else None,
                                  "return_on_bv": d_ni / d_bv_avg if d_bv_avg else None}
        row["match"] = None if row["core_difference"]["return"] is None else row["return_model"] - row["core_difference"]["return"]
        # прежние чтения (справочно): на весь капитал без связок баланса и на базовом капитале со слоями по своей цене
        c_at1 = key + AT1_SPREAD
        for s, req in floors.items():
            k = d_loan * req
            k_base = d_loan * floors11[s]
            k_at1 = d_loan * min(AT1_LAYER, req - floors11[s])
            k_t2 = k - k_base - k_at1
            tail = "" if s == scenario else f"_{s}"
            for name, r_f in (("wholesale", r_wh), ("core", r_core)):
                ret = (y_loan - cor_loan - (1 - k) * r_f) * keep / k
                row[f"return_{name}{tail}"] = ret
                base = ((y_loan - cor_loan - (1 - k) * r_f - k_t2 * r_wh) * keep - k_at1 * c_at1) / k_base
                row[f"return_{name}_base{tail}"] = base
                flat += [ret, base]
        row.update(capital_norm=floors[scenario], capital_per_ruble=d_loan * floors[scenario], base_norm=floors11[scenario],
                   base_per_ruble=d_loan * floors11[scenario], at1_rate=c_at1, t2_rate=r_wh)
        table[w] = [row]
    # ответ сетки на ту же премию (справочно): точка и миры, ₽
    live = live_from_book(book, facts)
    g0, g1 = run_grid(book, facts, live), run_grid(probe_book, facts, live_from_book(probe_book, facts))
    P = point_probabilities(g0)
    price1 = {c.key: g1.cell_price(c) for c in g1.cells}
    grid_by_world = {w: sum(P[c.key] * (price1[c.key] - g0.cell_price(c)) for c in g0.cells if c.world == w)
                     / sum(P[c.key] for c in g0.cells if c.world == w) for w in book.get("worlds.ids")}
    n = table[NEUTRAL_WORLD][0]
    return {"book": {"version": str(book.get("meta.version")), "date": str(book.get("meta.date"))},
            "inputs": {"loan_book": LOAN_BOOK, "regime": regime, "scenario": scenario, "capital_norms": floors, "base_norms": floors11,
                       "capital_rate": rate, "deduction_pp": ded_pp, "deduction_anchor_growing_rate": grow_rate,
                       "at1_layer": AT1_LAYER, "at1_spread": AT1_SPREAD, "rwa_density": d_loan,
                       "links": {"other_assets_to_loans": oa, "other_assets_density": d_oa, "other_liabilities_to_loans": ol, "allowance_ratio": al,
                                 "balancing_density": d_bal, "density_index": dn},
                       "cor_mgmt": cor_mgmt, "cor_engine": cor_eng, "cor_loan": cor_loan, "tax": tau, "nci_share": nci,
                       "securities_share_of_liquid": sec_share,
                       "lt_spreads": {b: lt(b) for b in ("wholesale", "securities", "liquidity")},
                       "probe": {"path": LOAN_PREMIUM, "years": list(PROBE_YEARS), "step": PROBE_STEP, "check_year": CHECK_YEAR, "match_tol": MATCH_TOL}},
            "marginal": {"corporate_loan": table},
            "grid_probe": {"point": g1.point - g0.point, "by_world": grid_by_world},
            "neutral": {"world": NEUTRAL_WORLD, "band": NEUTRAL_BAND,
                        "model": n["return_model"] - n["cost_of_equity"], "return_model": n["return_model"],
                        "core_difference": n["core_difference"]["return"],
                        "wholesale": n["return_wholesale_base"] - n["cost_of_equity"], "core": n["return_core_base"] - n["cost_of_equity"],
                        "return_wholesale": n["return_wholesale_base"], "return_core": n["return_core_base"],
                        "cost_of_equity": n["cost_of_equity"]},
            "sanity": {"model_min": min(model_returns), "model_max": max(model_returns), "segment_low": SANITY[0], "segment_high": SANITY[1],
                       "all_min": min(flat), "all_max": max(flat)}}


def report(res: dict) -> str:
    i = res["inputs"]
    ln = i["links"]
    lines = [f"книга {res['book']['version']} от {res['book']['date']}: рубль кредита юрлицам на предельной единице модели, стационар мира",
             f"  входы: стоимость риска юрлиц {pc(i['cor_loan'], 2)} % (режим {i['regime']}: {pc(i['cor_mgmt'], 2)} % в определении банка → движок "
             f"{pc(i['cor_engine'], 3)} %); налог {pc(i['tax'])} %; доля меньшинства {pc(i['nci_share'])} %; плотность RWA книги {i['rwa_density']:.4f}",
             f"  связки ядра на рубль кредита: прочие активы {ln['other_assets_to_loans']:.4f} (плотность {ln['other_assets_density']:.4f}, дохода нет); "
             f"прочие обязательства {ln['other_liabilities_to_loans']:.4f} (цены нет); резерв {ln['allowance_ratio']:.4f}; балансирующая смесь — плотность "
             f"{ln['balancing_density']:.4f}; индекс дрейфа плотности {ln['density_index']:.4f}",
             "  книги долгосрочно: опт — ключевая " + f"{100 * i['lt_spreads']['wholesale']:+.2f} п.п.; бумаги {100 * i['lt_spreads']['securities']:+.2f}; "
             f"ликвидность {100 * i['lt_spreads']['liquidity']:+.2f}; доля бумаг в ликвидных {i['securities_share_of_liquid']:.3f}",
             "  капитал на рубль RWA (Н20.0 связывает): " + ", ".join(f"{s} {pc(v, 2)} % (требование {pc(i['capital_norms'][s], 2)} + путь вычета "
                                                                     f"{pc(i['deduction_pp'][s], 2)} + растущий вычет якоря {pc(i['deduction_anchor_growing_rate'], 2)})"
                                                                     for s, v in i["capital_rate"].items()),
             "  НА ПРЕДЕЛЬНОЙ ЕДИНИЦЕ МОДЕЛИ (норма решения № 3, раздел 4; базис — решение № 4, п. 3.7)",
             f"  мир  ключевая  кредит (спред)   ядро: цена    капитал/руб   ОТДАЧА   стоимость капитала   отдача − стоимость   разность ядра {i['probe']['check_year']} "
             f"(премия +{pc(i['probe']['step'], 0)} п.п. {i['probe']['years'][0]}–{i['probe']['years'][-1]})   аналитика − ядро"]
    for w, rows in res["marginal"]["corporate_loan"].items():
        r = rows[0]
        cd = r["core_difference"]
        lines.append(f"  {w}    {pc(r['key_lt'], 2):>6}    {pc(r['loan_yield'], 2):>6} ({100 * r['loan_spread_to_key']:+.2f})    {pc(r['funding_core'], 2):>6}      "
                     f"{r['capital_per_ruble_model']:.4f}      {pc(r['return_model']):>5} %      {pc(r['cost_of_equity']):>5} %          "
                     f"{100 * (r['return_model'] - r['cost_of_equity']):+.1f} п.п.          {pc(cd['return']):>5} % (на ΔBV {pc(cd['return_on_bv'])} %)          "
                     f"{100 * r['match']:+.1f} п.п.")
    for w, rows in res["marginal"]["corporate_loan"].items():
        p = rows[0]["model_parts"]
        lines.append(f"     {w}: отдача по частям, п.п.: кредит против балансирующей смеси {100 * p['loan_margin']:+.1f}; прочие активы {100 * p['other_assets']:+.1f}; "
                     f"прочие обязательства {100 * p['other_liabilities']:+.1f}; резерв {100 * p['allowance']:+.1f}")
    n = res["neutral"]
    lines.append(f"  норма: мир {n['world']} на предельной единице модели — {100 * n['model']:+.1f} п.п. к стоимости капитала при норме ±{pc(n['band'], 0)} п.п. — "
                 + ("внутри" if abs(n["model"]) <= n["band"] else "ВНЕ НОРМЫ") + " (ключи к норме не подбираются)")
    g = res["grid_probe"]
    lines.append(f"  ответ сетки на ту же премию (справочно): точка {g['point']:+.2f} ₽; миры " + ", ".join(f"{w} {v:+.2f}" for w, v in g["by_world"].items()) + " ₽")
    lines.append("  справочно — прежние чтения (решение № 4, п. 3.7): на базовом капитале со слоями по своей цене (опт / ядро) и на весь капитал без связок баланса:")
    for w, rows in res["marginal"]["corporate_loan"].items():
        r = rows[0]
        lines.append(f"  {w}    базовый: {pc(r['return_wholesale_base']):>5} / {pc(r['return_core_base']):>5} %    весь капитал: {pc(r['return_wholesale']):>5} / "
                     f"{pc(r['return_core']):>5} %    стоимость капитала {pc(r['cost_of_equity']):>5} %")
    s = res["sanity"]
    ok = s["model_min"] >= s["segment_low"] and s["model_max"] <= s["segment_high"]
    lines.append(f"  норма: отдачи на предельной единице модели по мирам {pc(s['model_min'])}…{pc(s['model_max'])} % при норме {pc(s['segment_low'], 0)}…"
                 f"{pc(s['segment_high'], 0)} % — " + ("внутри" if ok else "ВНЕ НОРМЫ: признак ошибки калибровки")
                 + f"; все отдачи листа (обе нормы капитала, все чтения) — {pc(s['all_min'])}…{pc(s['all_max'])} % (справочно)")
    lines.append("  свойство механики: прочие активы (деньги, обязательные резервы и др.) и прочие обязательства привязаны к кредитам, а не к средствам "
                 "клиентов — рубль кредита тянет за собой бездоходные активы и капитал под них, рубль средств кладётся в бумаги с малым RWA")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="предельная единица роста: рубль корпоративного кредита на предельной единице модели")
    ap.add_argument("--book", type=Path, default=None)
    ap.add_argument("--facts", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    try:
        res = compute(a.book, a.facts)
    except NeedCore as exc:
        print(str(exc))
        return 2
    except Exception as exc:
        print(f"ОТКАЗ листа ({type(exc).__name__}): {exc}")
        return 1
    text = report(res)
    print(text, end="")
    if not a.no_write:
        target = a.out or HERE / "out" / "marginal_loan_out.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        if a.out is None:
            (HERE / "out" / "marginal_loan_out.txt").write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
