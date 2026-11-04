# -*- coding: utf-8 -*-
"""Правила книги Банка ВТБ для чисел, зависящих от миров ставок, — шаги `rule` манифеста приёма миров.

Каждая функция `f(ctx) -> [{"file", "values", "decimals", "replace"}]` (`ctx` — RuleContext команды
`ops/tools/adopt_worlds.py`: `ctx.root`, `ctx.record`, `ctx.overlay`, `ctx.yaml(rel)`, `ctx.version`,
`ctx.from_version`) считает числа книги по правилу из записи миров, фактов и входа листа вывода и не пишет сама: пишет
команда, точечно (`values` — адрес → число; адрес — кортеж: элементы списков номером), числа правил в комментариях —
заменой текста (`replace`). Сторож (`adopt_worlds.py --check`, `tests/test_worlds_rules.py`): на записи книги каждое
правило даёт шаблон.

  book_version   номер версии книги: младший разряд + 1, если версия с этим номером уже выпущена на другой записи миров
                 (тег `book-<версия>`); «версия …» строки 1 шапки шаблона;
  world_weights  веса миров A-P1 — вероятности записи; ось «Веса миров» вне диапазонов записи — стоп;
  spreads        ключи спредов девяти книг ЧПД — правило листа calib-nii/r2 в форме якоря 3К2026 (книга 1.0, решение
                 ведущего Р4): вход `evidence/path/inputs/vtb_r2_inputs.json` → `nii_books.near_rule` (a, s, остаток
                 якоря e; у ипотеки и потребкредитов — остаток 2К, исключение Р4 записано во входе), ключевая мира-опоры
                 H записи по кварталам. Книга с ключами лет — актив: s − (1 − a) × ключевая H (год якоря — его второе
                 полугодие, следующий год — среднее полугодий, дальше — полугодия) + доля остатка (1 / 0,5 / 0), LT — на
                 ключевой H последнего квартала сетки; пассив — s + доля остатка, у опта 2027 — середина s и LT; книга
                 бумаг — путь бэктеста мира H y ← y + ρ_окна (a × ключевая + s + доля × e − y) от ставки якоря, ключи
                 кварталов — обращение лага книги, лаг — наименьшее RMS «форма ядра − бэктест» в мирах N и M за восемь
                 кварталов на сетке 0,04…1,00; справочный вариант `securities_window_lag` — лаг окна и ключи линией на
                 остатке своего входа; 5 знаков;
  gate_masses    ожидаемые массы объяснений сработавших гейтов — массы таблиц книги (`results.json`), две значащие цифры.

Тем же счётом — запись листа во входе (`nii_books.books`, путь бэктеста `backtest_path.nim`): её пишет шаг `sheet-record`
(`ops/tools/worlds_steps.py`), функции — `sheet_record()` и `backtest_nim()` ниже.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

TEMPLATE = "data/assumptions/assumptions_template.yaml"
BUILDER = "data/assumptions/build_assumptions.py"
INPUTS = "data/assumptions/evidence/path/inputs/vtb_r2_inputs.json"
GATES = "data/assumptions/gate_explanations.yaml"
RESULTS = "data/assumptions/results.json"
FACTS_BOOKS = "data/facts/nii_books.json"
SECURITIES, WHOLESALE = "securities", "wholesale"
LAG_VARIANT = "securities_window_lag"
ASSETS = ("corp_loans", "mortgage", "consumer_loans", "securities", "liquidity")
LIABS = ("retail_current", "retail_term", "corp_funds", "wholesale")
SPREAD_DECIMALS = 5
LAG_GRID = tuple(round(0.02 * i, 2) for i in range(2, 51))     # 0,04 … 1,00
LAG_WORLDS = ("N", "M")                                         # лаг — ближе всего к бэктесту в мирах N и M
LAG_BAND = 1.25                                                 # полоса оси лага: RMS не больше 1,25 × минимума
BACKTEST_Q = 8                                                  # кварталов пути бэктеста и меры лага
ANCHOR_DAYS = 92                                                # дней квартала якоря 3К (ставка якоря листа)


class RuleError(Exception):
    """Шаблон или вход не в том виде, который правило знает."""


# ----------------------------------------------------------------------------------------------- общее
def r5(x: float) -> float:
    return round(x + 0.0, SPREAD_DECIMALS)


def ru_date(iso: str) -> str:
    return dt.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")


def template(ctx) -> dict:
    return ctx.yaml(TEMPLATE)


def text_of(ctx, rel: str) -> str:
    return (Path(ctx.root) / rel).read_text(encoding="utf-8")


def json_file(ctx, rel: str) -> Any:
    return json.loads((Path(ctx.root) / rel).read_text(encoding="utf-8"))


def one(text: str, pattern: str, flags: int = 0) -> re.Match:
    ms = list(re.finditer(pattern, text, flags))
    if len(ms) != 1:
        raise RuleError(f"в тексте {len(ms)} мест под правило (нужно одно): {pattern[:90]}")
    return ms[0]


def sub_groups(m: re.Match, values: list[str]) -> list[str]:
    """[было, стало]: совпадение `m` с группами, заменёнными на `values`."""
    s, base = m.group(0), m.start(0)
    out, at = [], 0
    for i, v in enumerate(values, 1):
        out.append(s[at:m.start(i) - base])
        out.append(v)
        at = m.end(i) - base
    out.append(s[at:])
    return [s, "".join(out)]


def axis_index(book: dict, paths: list[str]) -> int:
    hits = [i for i, a in enumerate(book["valuation"]["uncertainty"]["axes"]) if a["paths"] == paths]
    if len(hits) != 1:
        raise RuleError(f"осей с путями {paths}: {len(hits)}, нужна одна")
    return hits[0]


def variant_index(book: dict, vid: str) -> int:
    hits = [i for i, v in enumerate(book["valuation"]["reference_variants"]) if v["id"] == vid]
    if len(hits) != 1:
        raise RuleError(f"справочный вариант {vid}: {len(hits)}")
    return hits[0]


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------------------------------- версия книги
def released_record(root: Path, version: str) -> str | None:
    """sha256 записи миров книги выпуска `book-<версия>` (тег); тега нет — None."""
    p = subprocess.run(["git", "-C", str(root), "show", f"refs/tags/book-{version}:{TEMPLATE}"], capture_output=True)
    if p.returncode != 0:
        return None
    return str(((yaml.safe_load(p.stdout.decode("utf-8")) or {}).get("worlds") or {}).get("source", {}).get("sha256"))


def book_version(ctx) -> list[dict]:
    """Приём миров — новая версия книги: младший разряд + 1, если версия с номером шаблона уже выпущена на другой записи
    миров (тег `book-<версия>`). Иначе — номер шаблона (приём той же записи, повтор команды, книга до выпуска). Номер в
    строке 1 шапки шаблона («… ШАБЛОН машинной книги, версия X (…») — за ним; остальная проза шапки — человеку."""
    book = template(ctx)
    cur = str(book["meta"]["version"])
    rel = released_record(Path(ctx.root), cur)
    new = cur
    if rel is not None and rel != book["worlds"]["source"]["sha256"]:
        head, _, minor = cur.rpartition(".")
        new = f"{head}.{int(minor) + 1}"
    first = text_of(ctx, TEMPLATE).split("\n", 1)[0]
    m = one(first, r"ШАБЛОН машинной книги, версия (\S+) \(")
    if m.group(1) != cur:
        raise RuleError(f"строка 1 шаблона несёт версию {m.group(1)}, meta.version — {cur}")
    return [{"file": TEMPLATE, "values": {("meta", "version"): new}, "replace": [sub_groups(m, [new])] if new != cur else []}]


# ----------------------------------------------------------------------------------------------- веса миров
def world_weights(ctx) -> list[dict]:
    """Веса миров слоя «свой макро-взгляд» (A-P1) — вероятности записи миров; концы оси «Веса миров» — суждение книги:
    правило их не двигает, но вне диапазонов записи (`probability_ranges`) — стоп (решение ведущему)."""
    book = template(ctx)
    probs = ctx.record["probabilities"]
    ranges = ctx.record.get("probability_ranges") or {}
    ax = book["valuation"]["uncertainty"]["axes"][axis_index(book, ["joint.world_prob"])]
    out = [f"{end} {w} {v}" for end in ("low", "high") for w, v in ax[end].items()
           if w in ranges and not ranges[w][0] <= v <= ranges[w][1]]
    if out:
        raise RuleError(f"ось «Веса миров» вне диапазонов записи миров {ranges}: {out} — суждение ведущему")
    return [{"file": TEMPLATE, "values": {("joint", "world_prob", w): float(probs[w]) for w in book["joint"]["world_prob"]}}]


# ----------------------------------------------------------------------------------------------- ключевая мира по кварталам
def _half(period: str) -> str:
    return f"{period[:4]}H{1 if int(period[5]) <= 2 else 2}"


def _quarters(first: str, n: int) -> list[str]:
    y, q, out = int(first[:4]), int(first[5]), []
    for _ in range(n):
        out.append(f"{y}Q{q}")
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)
    return out


def world_keys(root: Path, record: dict, meta: dict) -> dict[str, dict[str, float]]:
    """Ключевая миров по полугодиям сетки — как её вписывает в машинную книгу сборщик (поле записи / 100, 5 знаков;
    квартал берёт значение своего полугодия)."""
    ba = _module(Path(root) / BUILDER, "worlds_rules_build_assumptions")
    blocks = ba.world_blocks(record, meta, ["N", "H", "M"])
    return {w: dict(blocks[w]["key_rate"]) for w in blocks}


class Paths:
    """Кварталы ключей книги бумаг (первый прогнозный … последний ключ квартала шаблона) и ключевая миров на них."""

    def __init__(self, root: Path, record: dict, book: dict):
        meta = book["meta"]
        sec = book["nii"]["books"][SECURITIES]["spread"]
        quarter_keys = [str(k) for k in sec if re.fullmatch(r"\d{4}Q[1-4]", str(k))]
        self.labels = _quarters(str(meta["first_period"]), len(quarter_keys))
        if quarter_keys != self.labels:
            raise RuleError(f"ключи кварталов книги бумаг {quarter_keys[:3]}… не идут подряд с первого прогнозного квартала")
        halves = world_keys(root, record, meta)
        self.key = {w: [halves[w][_half(p)] for p in self.labels] for w in halves}
        self.key_h = {}
        for p, k in zip(self.labels, self.key["H"]):
            self.key_h.setdefault(_half(p), k)
        for h, k in halves["H"].items():
            self.key_h.setdefault(h, k)
        self.key_lt = halves["H"][_half(str(meta["last_period"]))]
        self.y0 = int(str(meta["first_period"])[:4])


# ----------------------------------------------------------------------------------------------- спреды ЧПД
def year_traj(spec: dict, c: dict, fade: dict, wholesale_lt: float, paths: Paths, book_keys: dict, book: str) -> dict:
    """Ключи книги с ключами лет — `blocks_r2.spread_traj` листа calib-nii/r2 (якорь 3К: год якоря — первый прогнозный)."""
    a, s, e = float(c["a"]), float(c["s"]), float(c["residual"])
    y0, y1 = str(paths.y0), str(paths.y0 + 1)
    kh = paths.key_h
    out: dict[str, Any] = {}
    if c["side"] == "asset":
        line = lambda k: s - (1.0 - a) * k                                                    # noqa: E731
        out[y0] = r5(line(kh[f"{y0}H2"]) + float(fade[y0]) * e)
        out[y1] = r5(line((kh[f"{y1}H1"] + kh[f"{y1}H2"]) / 2) + float(fade[y1]) * e)
        if abs(1.0 - a) >= 1e-12:
            for k in book_keys:
                if re.fullmatch(r"\d{4}H[12]", str(k)):
                    out[str(k)] = r5(line(kh[str(k)]))
            out["LT"] = r5(line(paths.key_lt))
        else:
            out["LT"] = r5(s)
    else:
        lt = wholesale_lt if book == WHOLESALE else s
        out[y0] = r5(s + float(fade[y0]) * e)
        out[y1] = r5(((s + lt) / 2 if book == WHOLESALE else s) + float(fade[y1]) * e)
        out["LT"] = r5(lt)
    want = {str(k) for k in book_keys if k != "LT_from"}
    if set(out) != want:
        raise RuleError(f"книга {book}: ключи правила {sorted(out)} ≠ ключам шаблона {sorted(want)}")
    return out


def securities_lag(c: dict, fade: dict, paths: Paths, lt_from: Any) -> dict:
    """Книга бумаг: путь бэктеста миров, лаг по правилу, ключи кварталов обращением лага на пути мира H, полоса оси."""
    a, s, e = float(c["a"]), float(c["s"]), float(c["residual"])
    y0, rho_w = float(c["rate_anchor"]), float(c["rho_window"])
    labels, key = paths.labels, paths.key

    def window(kw: list[float]) -> list[float]:
        y, row = y0, []
        for p, k in zip(labels, kw):
            y = y + rho_w * (a * k + s + float(fade.get(p[:4], 0.0)) * e - y)
            row.append(y)
        return row
    rw = {w: window(key[w]) for w in key}
    lt = r5(s - (1.0 - a) * paths.key_lt)

    def keys(rho: float) -> dict:
        out, prev = {}, y0
        for i, p in enumerate(labels):
            out[p] = round(prev + (rw["H"][i] - prev) / rho - key["H"][i], SPREAD_DECIMALS)
            prev = rw["H"][i]
        return out

    def gap(rho: float) -> float:
        k, tot = keys(rho), 0.0
        for w in LAG_WORLDS:
            y = y0
            for i in range(BACKTEST_Q):
                y = y + rho * (key[w][i] + k[labels[i]] - y)
                tot += (y - rw[w][i]) ** 2
        return 100 * (tot / (len(LAG_WORLDS) * BACKTEST_Q)) ** 0.5
    fit = {r: gap(r) for r in LAG_GRID}
    rho = min(fit, key=fit.get)
    band = [r for r in LAG_GRID if fit[r] <= fit[rho] * LAG_BAND]
    spread = {**keys(rho), "LT": lt, "LT_from": lt_from}
    return {"rho": rho, "spread": spread, "band": (min(band), max(band)), "rms": fit[rho]}


def near_keys(root: Path, record: dict, book: dict, inputs: dict) -> dict:
    """Ключи спредов девяти книг, лаг бумаг, полоса оси лага и вариант лага окна по правилу (без записи)."""
    rule = inputs["nii_books"]["near_rule"]
    fade = {str(y): float(f) for y, f in rule["fade"].items()}
    paths = Paths(root, record, book)
    books = book["nii"]["books"]
    out: dict[str, Any] = {"books": {}}
    for b, c in rule["books"].items():
        if b == SECURITIES:
            continue
        out["books"][b] = year_traj(books[b], c, fade, float(rule["wholesale_lt"]), paths, books[b]["spread"], b)
    sec = securities_lag(rule["books"][SECURITIES], fade, paths, books[SECURITIES]["spread"]["LT_from"])
    out["securities"] = sec
    var = (rule.get("variants") or {}).get(LAG_VARIANT)
    if var is None:
        raise RuleError(f"во входе nii_books.near_rule нет variants.{LAG_VARIANT} (остаток якоря варианта)")
    j = variant_index(book, LAG_VARIANT)
    ov = book["valuation"]["reference_variants"][j]["overrides"]
    c = {**rule["books"][SECURITIES], "residual": float(var["residual"])}
    out["variant"] = {"index": j, "rho": float(rule["books"][SECURITIES]["rho_window"]),
                      "spread": year_traj({}, c, fade, 0.0, paths, ov[f"nii.books.{SECURITIES}.spread"], SECURITIES)}
    return out


def spreads(ctx) -> list[dict]:
    book = template(ctx)
    res = near_keys(Path(ctx.root), ctx.record, book, json_file(ctx, INPUTS))
    values: dict[tuple, Any] = {}
    for b, keys in res["books"].items():
        values.update({("nii", "books", b, "spread", k): v for k, v in keys.items()})
    sec = res["securities"]
    values[("nii", "books", SECURITIES, "rho")] = sec["rho"]
    values.update({("nii", "books", SECURITIES, "spread", k): v for k, v in sec["spread"].items() if k != "LT_from"})
    var = res["variant"]
    base = ("valuation", "reference_variants", var["index"], "overrides")
    values[base + (f"nii.books.{SECURITIES}.rho",)] = var["rho"]
    values.update({base + (f"nii.books.{SECURITIES}.spread", k): v for k, v in var["spread"].items()})
    return [{"file": TEMPLATE, "values": values, "decimals": {k: SPREAD_DECIMALS for k in values}}]


# ----------------------------------------------------------------------------------------------- запись листа во входе
def sheet_record(book: dict, inputs: dict) -> dict:
    """`nii_books.books` входа листа вывода — копия ключей и лагов книги (шаг near_spreads листа сверяет шаблон с ней)."""
    out = json.loads(json.dumps(inputs["nii_books"]["books"]))
    for b, rec in out.items():
        spec = book["nii"]["books"][b]
        for k in rec:
            if k not in ("rho", "spread", "beta"):
                raise RuleError(f"запись листа {b}: незнакомое поле {k}")
            rec[k] = json.loads(json.dumps(spec[k]))
    return out


def current_share_path(key: list[float], c0: float, c_ref: float, key_ref: float, psi: float, rho: float,
                       bounds: tuple[float, float]) -> list[float]:
    """Доля текущих счетов в средствах физлиц по кварталам (мостик c*(key) листа calib-nii/r2, r2lib)."""
    out, c = [], c0
    for k in key:
        c_star = min(bounds[1], max(bounds[0], c_ref - psi * (k - key_ref)))
        c = c + rho * (c_star - c)
        out.append(c)
    return out


def backtest_nim(root: Path, record: dict, book: dict, inputs: dict) -> list[float]:
    """Путь бэктеста книг в мире-опоре H (лист calib-nii/r2, backtest_q3.py): ставки книг в форме окна от ставок якоря
    (факты якоря: проценты квартала / средний остаток × 365/92) на ключевой мира H, маржа на составе якоря (остатки на
    конец квартала якоря, доля текущих счетов — мостик c*(key)), первые восемь прогнозных кварталов, 6 знаков."""
    rule = inputs["nii_books"]["near_rule"]
    own = inputs["backtest_path"]["rule"]                     # остатки якоря 3К и лаги окна всех книг (вход листа)
    facts = json.loads((Path(root) / FACTS_BOOKS).read_text(encoding="utf-8"))["books"]
    paths = Paths(root, record, book)
    kw = paths.key[str(inputs["backtest_path"]["world"])]
    yf = ANCHOR_DAYS / 365.0
    plain = {b: float(facts[b]["interest_q"]["v"]) / float(facts[b]["balance_avg"]["v"]) / yf for b in ASSETS + LIABS}
    bal = {b: float(facts[b]["balance_close"]["v"]) for b in ASSETS + LIABS}
    iea = sum(bal[b] for b in ASSETS)
    fade = {str(y): float(f) for y, f in rule["fade"].items()}
    wlt = float(rule["wholesale_lt"])
    rates = {}
    for b in ASSETS + LIABS:
        c = rule["books"][b]
        a, s, e, rho = float(c["a"]), float(c["s"]), float(own["residuals"][b]), float(own["rho_window"][b])
        y, row = plain[b], []
        for p, k in zip(paths.labels, kw):
            yr = int(p[:4])
            ss = s if b != WHOLESALE else (s if yr == paths.y0 else (s + wlt) / 2 if yr == paths.y0 + 1 else wlt)
            y = y + rho * (a * k + ss + fade.get(str(yr), 0.0) * e - y)
            row.append(y)
        rates[b] = row
    rcs = book["nii"]["retail_current_share"]
    fr = bal["retail_current"] + bal["retail_term"]
    cp = current_share_path(kw, float(rcs["c_ref"]), float(rcs["c_ref"]), float(rcs["key_ref"]), float(rcs["psi"]),
                            float(rcs["rho"]), tuple(rcs["bounds"]))
    dia = round(float(book["nii"]["dia_rate"]), 4)
    out = []
    for t in range(BACKTEST_Q):
        inc = sum(rates[b][t] * bal[b] for b in ASSETS)
        exp = rates["corp_funds"][t] * bal["corp_funds"] + rates[WHOLESALE][t] * bal[WHOLESALE] \
            + fr * (cp[t] * rates["retail_current"][t] + (1 - cp[t]) * rates["retail_term"][t])
        out.append(round((inc - exp - dia * fr) / iea, 6))
    return out


# ----------------------------------------------------------------------------------------------- гейты
def mass2(x: float) -> float:
    """Масса записи объяснения — две значащие цифры (0,04794 → 0,048; 0,6405 → 0,64; 1 → 1,0)."""
    return float(f"{float(x):.2g}")


def gate_masses(ctx) -> list[dict]:
    """Ожидаемая масса объяснения гейта = масса сработавшего гейта в таблицах книги, две значащие цифры (запись с
    коридором массы — суждение о дрейфе, её правило не трогает). Тексты объяснений — суждение."""
    res = json_file(ctx, RESULTS)
    fired = {c["name"]: c["mass"] for c in res["checks"] if c.get("fired") and c.get("kind") == "gate"}
    notes = ctx.yaml(GATES) or {}
    values = {(name, "expected_mass"): mass2(fired[name]) for name, e in notes.items()
              if isinstance(e, dict) and "expected_mass" in e and name in fired}
    return [{"file": GATES, "values": values}]
