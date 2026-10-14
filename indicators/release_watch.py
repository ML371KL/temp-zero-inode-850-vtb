"""Дозор месячного релиза эмитента: кандидаты чисел из разных видов источников и приём.

Что за релиз — настройка (`sources.yaml`): `monthly.metrics` — допустимые метрики, `monthly.series_prefix` —
начало имён рядов, `monthly.main_metric` — метрика, по которой месяц считается принятым,
`schedule.monthly.kind` — вид документа эмитента, `schedule.monthly.wakes_release` — будит ли принятый
месяц выпуск. Без настроек — релиз РСБУ банка: ряды `ras.release.*`, метрики `METRICS`, главный — `np_ytd`.

Виды источников: таблица PDF эмитента (`pdf`; `method: text` — текстовый слой, иначе распознавание),
текст Интерфакса (`interfax`), текст smart-lab (`smartlab`), посты каналов (`telegram:<канал>` — каждый
канал свой вид), издания, форма 0409102 ЦБ (`form102` — только прибыль и прибыль до налога), ручной
ввод (`manual`, `record-ras` — принимается сам).

Правила:

* **Текст новости — кандидат только своего месяца.** Релиз месяца M выходит в месяце M + 1: берутся
  тексты с днём публикации после конца M и не позже конца M + 1, чьё первое предложение с фразой
  периода называет M (`news.period_months`); числа — только из фраз, называющих этот месяц.
* **Таблица PDF с текстовым слоем принимается сама:** это документ эмитента, прочитанный без
  распознавания. Прочее число принимается, если его подтверждают два разных вида в пределах допуска
  (`release_watch.tolerance`); две группы по два вида и больше — расхождение.
* **Тождество «НМ = НМ прошлого месяца + месяц»** (для потоков, у которых в метриках есть и
  нарастающее, и месячное число): поток, не прошедший его, в ряд не пишется.
* **Стык «итог отчёта, внесённый руками → первая книга после месяца без релиза»** — не отказ, а
  пересмотр: итог месяца без своего релиза (конец квартала) оператор вносит из отчёта, а следующая
  книга эмитента печатает «итог − месяц» иначе (другой винтаж, другое округление). Документ эмитента
  с текстовым слоем принимается, расхождение уходит сообщением (`revisions`); внесённое руками число
  меняет только рука.
* **Принятое автоматически другое автоматическое не переписывает**: иное число — расхождение,
  меняет его только ручной ввод.

Расхождение прибыли релиза с формой 0409102 — плашка `ras_mismatch` (`mismatch_flag`). Релиз в другом
базисе, чем форма банка (группа по МСФО), с формой не сверяется и ею не подтверждается: настройка
`monthly.form102: false` убирает форму из кандидатов, из плашки и из таблицы сверки.

**Месяцы без своего релиза** (`monthly.backfill: true`). Эмитент, который печатает не каждый месяц, даёт
пропущенный месяц в следующей книге: нарастающий итог прошлого месяца — разность «итог − месяц» этой
книги (и тогда месяц без релиза — разность соседних итогов), остатки на конец прошлого месяца и
прошлого года — её столбцы сравнения (`comparative` кандидата). Так заполняется только то, чего в
ряду ещё нет; принятое раньше число эти строки не переписывают. Разностью итогов поток выводится
только месяцу без своего релиза (`calendar.has_release`): у месяца с релизом числа — из его книги, и
книга следующего месяца их не подменяет. Поток месяца, за который тождество не сошлось, тоже не
выводится: расхождение разбирает человек.

Принятое пишется в ряды `<prefix><метрика>` (период — месяц `2026M08`, момент — приём): деньги — млрд ₽,
проценты — доли, клиенты — млн. Состояние дня — `release_watch/<месяц>.json`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from indicators import calendar as cal
from indicators import cbr_forms, issuer_docs, news, periods
from indicators.sources import Context, Result
from indicators.store import Store, point

METRICS = ("np_ytd", "np_m", "nii_ytd", "nii_m", "fee_ytd", "fee_m", "prov_ytd", "prov_m", "opex_ytd",
           "opex_m", "pretax_ytd", "pretax_m", "roe_ytd", "roe_m", "cor_ytd", "cor_m", "cir_ytd",
           "loans_ul", "loans_fl", "funds_ul", "funds_fl", "cap_base", "cap_main", "cap_total",
           "n1_0", "n1_1", "n1_2")
SHARE_METRICS = frozenset({"roe_ytd", "roe_m", "cor_ytd", "cor_m", "cir_ytd", "n1_0", "n1_1", "n1_2",
                           "nim_ytd", "nim_m", "cir_m", "npl90", "n20_0", "n20_1", "n20_2"})
COUNT_PREFIX = "clients_"             # метрики-счётчики (млн клиентов): не деньги и не доли
FLOWS = ("np", "nii", "fee", "prov", "opex", "pretax", "other", "opinc", "tax")
STATE_DIR = "release_watch"
DEFAULT_PREFIX = "ras.release."
DEFAULT_MAIN = "np_ytd"
DEFAULT_BASIS = "ras"                 # базис рядов месячного релиза без настройки — РСБУ банка
TABLE_FLOWS, TABLE_STOCKS = "flows", "stocks"     # форма месячной таблицы выпуска (`monthly.table`)
MANUAL, CALC, HELD, PDF, TEXT, COMPARATIVE = "manual", "calc", "accepted", "pdf", "text", "comparative"
DERIVED_NOTE = "derived"              # пометка точки, которой в релизе нет: получена разностью итогов
# Ведущее значение группы — вид, повторяющий релиз (таблица, текст); форма 0409102 — подтверждение.
LEAD_ORDER = ("pdf", "interfax", "smartlab", "outlet")
# Метрики словами — для строк, которые печатает витрина (причины деградации, плашка `ras_mismatch`; П§0.2).
FLOW_WORDS = {"np": "чистая прибыль", "nii": "чистый процентный доход", "fee": "чистый комиссионный доход",
              "prov": "резервы", "opex": "операционные расходы", "pretax": "прибыль до налога",
              "other": "прочие операционные доходы", "opinc": "операционные доходы до резервов",
              "tax": "налог на прибыль"}
RATIO_WORDS = {"roe": "ROE", "cor": "стоимость риска", "cir": "CIR", "nim": "чистая процентная маржа"}
STOCK_WORDS = {"assets": "активы", "equity": "собственные средства", "npl90": "доля неработающих кредитов",
               "n20_0": "Н20.0", "n20_1": "Н20.1", "n20_2": "Н20.2",
               "loans_ul": "кредиты юрлицам", "loans_fl": "кредиты физлицам", "funds_ul": "средства юрлиц",
               "funds_fl": "средства физлиц", "cap_base": "базовый капитал", "cap_main": "основной капитал",
               "cap_total": "общий капитал", "n1_0": "Н1.0", "n1_1": "Н1.1", "n1_2": "Н1.2",
               "loans_gross": "кредитный портфель", "loans_retail": "кредиты физлицам",
               "loans_business": "кредиты бизнесу", "funds_total": "средства клиентов",
               "funds_retail": "средства физлиц", "funds_business": "средства бизнеса",
               "clients_total": "клиенты", "clients_active": "активные клиенты"}
SPAN_WORDS = {"ytd": "с начала года", "m": "за месяц"}


@dataclass(frozen=True)
class Monthly:
    """Настройки месячного релиза эмитента (шапка модуля)."""

    prefix: str = DEFAULT_PREFIX
    metrics: tuple[str, ...] = METRICS
    main: str = DEFAULT_MAIN
    doc_kind: str = issuer_docs.DEFAULT_MONTHLY_KIND
    wakes: bool = True
    basis: str = DEFAULT_BASIS        # код базиса рядов релиза (`monthly.basis`)
    form102: bool = True              # форма 0409102 подтверждает прибыль релиза и сверяется с ней
    backfill: bool = False            # месяцы без своего релиза заполняются из следующей книги
    table: str | None = None          # форма месячной таблицы выпуска; None — по началу имён рядов

    def series(self, metric: str) -> str:
        return f"{self.prefix}{metric}"

    def unit(self, metric: str) -> str:
        if metric in SHARE_METRICS:
            return "share"
        return "mn" if metric.startswith(COUNT_PREFIX) else "RUB bn"

    def table_form(self) -> str:
        """Форма месячной таблицы выпуска: настройка `monthly.table`, а без неё — прежнее правило: ряды с
        началом имён по умолчанию несёт таблица потоков, прочие — таблица остатков."""
        if self.table in (TABLE_FLOWS, TABLE_STOCKS):
            return self.table
        return TABLE_FLOWS if self.prefix == DEFAULT_PREFIX else TABLE_STOCKS


def monthly(cfg: Mapping[str, Any] | None) -> Monthly:
    """Настройки месячного релиза из `sources.yaml` (нет ключей — релиз РСБУ банка)."""
    cfg = cfg or {}
    block = cfg.get("monthly") or {}
    sched = (cfg.get("schedule") or {}).get("monthly")
    sched = sched if isinstance(sched, dict) else {}
    metrics = tuple(str(m) for m in block.get("metrics") or METRICS)
    main = str(block.get("main_metric") or (DEFAULT_MAIN if DEFAULT_MAIN in metrics else metrics[0]))
    table = block.get("table")
    return Monthly(prefix=str(block.get("series_prefix") or DEFAULT_PREFIX), metrics=metrics, main=main,
                   doc_kind=str(sched.get("kind") or issuer_docs.DEFAULT_MONTHLY_KIND),
                   wakes=bool(sched.get("wakes_release", True)),
                   basis=str(block.get("basis") or DEFAULT_BASIS), form102=bool(block.get("form102", True)),
                   backfill=bool(block.get("backfill", False)), table=None if table is None else str(table))


def metric_words(metric: str) -> str:
    """Метрика релиза словами: «np_ytd» → «чистая прибыль с начала года»."""
    head, _, span = metric.rpartition("_")
    words = FLOW_WORDS.get(head) or RATIO_WORDS.get(head)
    if words and span in SPAN_WORDS:
        return f"{words} {SPAN_WORDS[span]}"
    return STOCK_WORDS.get(metric, metric)


def series_id(metric: str, prefix: str = DEFAULT_PREFIX) -> str:
    return f"{prefix}{metric}"


def tolerance(metric: str, cfg: dict[str, Any]) -> float:
    tol = cfg.get("tolerance") or {}
    return float(tol.get("share" if metric in SHARE_METRICS else "money", 0.0005 if metric in SHARE_METRICS else 0.15))


def release_days(month: str) -> tuple[date, date]:
    """Когда выходит релиз месяца: после его конца и не позже конца следующего — (после, по)."""
    return periods.month_end(month), periods.month_end(periods.shift_month(month, 1))


def _share(metric: str, value: float, cand: Mapping[str, Any]) -> float:
    """Доля из документа эмитента. Таблица PDF печатает проценты: число больше единицы — проценты. Книга несёт
    доли долями (`share_unit` кандидата) — её число берётся как есть: отношение 105 % в книге — это 1,05."""
    if metric in SHARE_METRICS and value > 1 and cand.get("share_unit") != issuer_docs.SHARE_FRACTIONS:
        return round(value / 100.0, 10)
    return value


def gather(ctx: Context, month: str, spec: Monthly | None = None) -> dict[str, list[dict[str, Any]]]:
    """Кандидаты по метрикам: [{kind, value, ref}] из новостей, PDF, формы 102 (ручной ввод добавляет `watch`)."""
    spec = spec or monthly(ctx.cfg)
    cands: dict[str, list[dict[str, Any]]] = {}
    _, number = periods.parse_month(month)
    after, until = release_days(month)
    items = (ctx.store.read_state("news/items.json") or {}).get("items") or {}
    for url, item in items.items():
        day = news.published_day(item.get("published") or item.get("first_seen"))
        if day is None or not after < day <= until:
            continue                    # релиз месяца выходит в следующем месяце: текст другого дня — не о нём
        if item.get("topic") == "dividend":
            continue                    # новость о дивидендах — вход реестра, не месячного релиза
        kind = str(item.get("kind") or "outlet")
        text = item.get("text") or ""
        if not text or number not in news.period_months(text):
            continue                    # текст о другом месяце кандидатов не даёт
        found = news.extract_release_numbers(text, month=month)
        if kind.startswith("telegram"):
            for metric, got in news.extract_headline(text, month=month).items():
                found.setdefault(metric, got)
        for metric, (value, phrase) in found.items():
            if metric in spec.metrics:
                cands.setdefault(metric, []).append({"kind": kind, "value": value, "ref": url, "phrase": phrase})
    for cand in (ctx.store.read_state(issuer_docs.CANDIDATES_FILE) or {}).values():
        if cand.get("kind") != spec.doc_kind or cand.get("month") != month or cand.get("status") != "ok":
            continue
        for metric, value in (cand.get("numbers") or {}).items():
            if metric not in spec.metrics or value is None:
                continue
            value = _share(metric, value, cand)
            cands.setdefault(metric, []).append({"kind": PDF, "value": value, "ref": cand.get("url"),
                                                 "sha256": cand.get("sha256"),
                                                 "method": TEXT if cand.get("method") == TEXT else "ocr"})
    as_of = ctx.today.isoformat()
    for metric, sid in (("np_ytd", "cbr.f102.ni_ytd"), ("pretax_ytd", "cbr.f102.pretax_ytd")):
        if metric not in spec.metrics or not spec.form102:
            continue                    # релиз в другом базисе форма банка не подтверждает
        f = ctx.store.load(sid)
        v = None if f is None else f.value_as_of(month, as_of)
        if v is not None:
            cands.setdefault(metric, []).append({"kind": "form102", "value": round(v, 4), "ref": "cbr:0409102"})
    return cands


def _kinds(rows: list[dict]) -> set[str]:
    return {r["kind"] for r in rows}


def decide(cands: dict[str, list[dict[str, Any]]], cfg: dict[str, Any]) -> tuple[dict, dict]:
    """(принятые {метрика: {value, kinds}}, расхождения {метрика: [кандидаты]})."""
    accepted, mismatches = {}, {}
    for metric, rows in cands.items():
        manual = [r for r in rows if r["kind"] == MANUAL]
        if manual:
            accepted[metric] = {"value": manual[-1]["value"], "kinds": [MANUAL]}
            continue
        tol = tolerance(metric, cfg)
        text = [r for r in rows if r["kind"] == PDF and r.get("method") == TEXT]
        if text:
            # документ эмитента с текстовым слоем принимается сам; согласные виды — в подтверждение
            lead = text[-1]
            agree = {r["kind"] for r in rows if abs(r["value"] - lead["value"]) <= tol}
            accepted[metric] = {"value": lead["value"], "kinds": sorted(agree)}
            continue
        groups: list[list[dict]] = []
        for r in sorted(rows, key=lambda r: r["value"]):
            if groups and abs(r["value"] - groups[-1][0]["value"]) <= tol:
                groups[-1].append(r)
            else:
                groups.append([r])
        agreed = [g for g in groups if len(_kinds(g)) >= 2]
        if len(agreed) == 1:
            lead = min(agreed[0], key=lambda r: (r["kind"] == "form102",
                                                 LEAD_ORDER.index(r["kind"]) if r["kind"] in LEAD_ORDER
                                                 else len(LEAD_ORDER)))
            accepted[metric] = {"value": lead["value"], "kinds": sorted(_kinds(agreed[0]))}
        elif agreed or len(_kinds(rows)) >= 2:
            # ни одна группа не набрала двух видов — или набрали две разные: выбирать нечем
            mismatches[metric] = rows
    return accepted, mismatches


def _held(store: Store, metric: str, month: str, spec: Monthly) -> float | None:
    s = store.load(spec.series(metric))
    return None if s is None else s.value_as_of(month)


def _by_hand(acc: dict[str, Any]) -> bool:
    """Число внесено руками или выведено из внесённого руками."""
    return acc["kinds"] == [MANUAL] or bool(acc.get("manual"))


def _flows(spec: Monthly) -> tuple[str, ...]:
    """Потоки релиза, у которых в метриках есть и нарастающее, и месячное число."""
    return tuple(f for f in FLOWS if f"{f}_ytd" in spec.metrics and f"{f}_m" in spec.metrics)


def derive_month(store: Store, month: str, accepted: dict[str, dict], spec: Monthly | None = None) -> None:
    """Недостающая половина пары потока: в январе нарастающее и месяц — одно число; дальше месяц —
    разность нарастающих, если месяц не принят, а оба нарастающих известны."""
    spec = spec or Monthly()
    _, m = periods.parse_month(month)
    for flow in _flows(spec):
        ytd, mon = accepted.get(f"{flow}_ytd"), accepted.get(f"{flow}_m")
        if m == 1:
            src = ytd or mon
            if src is not None and (ytd is None or mon is None):
                accepted[f"{flow}_m" if mon is None else f"{flow}_ytd"] = {
                    "value": src["value"], "kinds": [CALC], "manual": _by_hand(src)}
            continue
        if mon is not None or ytd is None:
            continue
        prev = _held(store, f"{flow}_ytd", periods.shift_month(month, -1), spec)
        if prev is not None:
            accepted[f"{flow}_m"] = {"value": round(ytd["value"] - prev, 4), "kinds": [CALC],
                                     "manual": _by_hand(ytd)}


def identity_failures(store: Store, month: str, accepted: dict[str, dict], cfg: dict[str, Any],
                      spec: Monthly | None = None) -> dict[str, str]:
    """Тождество «НМ = НМ прошлого месяца + месяц» для потоков релиза (январь: НМ = месяц) → {поток: что не сошлось}."""
    spec = spec or Monthly()
    tol = float((cfg.get("tolerance") or {}).get("identity", 0.35))
    out: dict[str, str] = {}
    _, m = periods.parse_month(month)
    for flow in _flows(spec):
        ytd = accepted.get(f"{flow}_ytd", {}).get("value")
        mon = accepted.get(f"{flow}_m", {}).get("value")
        if ytd is None or mon is None:
            continue
        prev = 0.0 if m == 1 else _held(store, f"{flow}_ytd", periods.shift_month(month, -1), spec)
        if prev is not None and abs(prev + mon - ytd) > tol:
            out[flow] = f"{FLOW_WORDS[flow]}: с начала года {ytd} ≠ {prev} + {mon}"
    return out


def _calendar(ctx: Context) -> dict[str, Any] | None:
    """Настройка месячного события календаря (месяцы без своего релиза — её `skip_months`)."""
    return cal.monthly_spec(ctx.cfg.get("schedule") or {})


def junction_revisions(ctx: Context, month: str, accepted: dict[str, dict], failures: dict[str, str],
                       spec: Monthly) -> dict[str, str]:
    """Потоки, у которых несошедшееся тождество — пересмотр, а не отказ (шапка модуля) → {поток: сообщение}.

    Условия: у прошлого месяца нет своего релиза, его нарастающий итог в ряду внесён руками, а числа этого
    месяца — документ эмитента с текстовым слоем (не рука и не новости)."""
    prev = periods.shift_month(month, -1)
    if not failures or periods.parse_month(month)[1] == 1 or cal.has_release(prev, _calendar(ctx)):
        return {}
    out: dict[str, str] = {}
    for flow in failures:
        ytd, mon = accepted[f"{flow}_ytd"], accepted[f"{flow}_m"]
        if any(_by_hand(acc) or PDF not in acc["kinds"] for acc in (ytd, mon)):
            continue
        series = ctx.store.load(spec.series(f"{flow}_ytd"))
        held = None if series is None else series.point_as_of(prev)
        if held is None or held.status != MANUAL:
            continue
        out[flow] = (f"{FLOW_WORDS[flow]}: с начала года по {prev} внесено руками {held.value}, "
                     f"по книге {month} — {round(ytd['value'] - mon['value'], 4)} ({ytd['value']} − {mon['value']})")
    return out


def watch(ctx: Context, month: str) -> dict[str, Any]:
    """Один проход по месяцу: кандидаты → приём → ряды → состояние дня."""
    cfg = ctx.cfg.get("release_watch") or {}
    spec = monthly(ctx.cfg)
    name = f"{STATE_DIR}/{month}.json"
    state = ctx.store.read_state(name) or {"month": month, "accepted": {}, "first_candidate": None}
    manual = ctx.store.read_state(f"{STATE_DIR}/manual_{month}.json") or {}
    cands = gather(ctx, month, spec)
    for metric, value in manual.items():
        cands.setdefault(metric, []).append({"kind": MANUAL, "value": value["value"], "ref": value.get("source")})
    accepted, mismatches = decide(cands, cfg)
    derive_month(ctx.store, month, accepted, spec)
    failures = identity_failures(ctx.store, month, accepted, cfg, spec)
    revisions = junction_revisions(ctx, month, accepted, failures, spec)
    failures = {flow: text for flow, text in failures.items() if flow not in revisions}
    now = ctx.moment()
    known_before = _held(ctx.store, spec.main, month, spec) is not None
    new = []
    for metric, acc in accepted.items():
        by_hand = _by_hand(acc)
        held = _held(ctx.store, metric, month, spec)
        prev = state["accepted"].get(metric)
        if held is not None and not by_hand:
            # В ряду уже есть число месяца: автомат его подтверждает, но не переписывает.
            if abs(held - acc["value"]) <= tolerance(metric, cfg):
                if prev is None:
                    state["accepted"][metric] = {"value": held, "kinds": acc["kinds"], "at": now}
            elif acc["kinds"] != [CALC]:
                mismatches[metric] = [{"kind": HELD, "value": held, "ref": spec.series(metric)}] + cands.get(metric, [])
            continue
        flow, _, part = metric.rpartition("_")
        if not by_hand and part in ("ytd", "m") and flow in failures:
            continue                    # поток не прошёл тождество — в ряд не пишется
        if prev is not None and prev["kinds"] == acc["kinds"] and abs(prev["value"] - acc["value"]) <= 1e-9:
            continue
        ctx.store.upsert(spec.series(metric), [point(month, acc["value"], fetched_at=now,
                                                     status="manual" if by_hand else "ok",
                                                     source="release:" + "+".join(acc["kinds"]))],
                         unit=spec.unit(metric), basis=spec.basis, label=f"месячный релиз эмитента: {metric}")
        state["accepted"][metric] = {"value": acc["value"], "kinds": acc["kinds"], "at": now}
        new.append(metric)
    filled = backfill(ctx, month, spec, now) if spec.backfill else []
    if filled:
        state["filled"] = sorted(set(state.get("filled") or []) | {f"{p}:{m}" for p, m in filled})
    if cands and not state.get("first_candidate"):
        state["first_candidate"] = now
    state.update({"checked_at": now, "candidates": cands, "mismatches": mismatches,
                  "identity_failures": list(failures.values()), "identity_flows": sorted(failures),
                  "revisions": list(revisions.values())})
    ctx.store.write_state(name, state)
    return {"month": month, "new": new, "mismatches": sorted(mismatches),
            "identity_failures": list(failures.values()), "revisions": list(revisions.values()),
            "filled": [list(x) for x in filled],
            "complete": spec.main in state["accepted"],
            "month_accepted": spec.main in new and not known_before}


def _fill(ctx: Context, spec: Monthly, period: str, metric: str, value: float, now: str, kind: str) -> bool:
    """Точка месяца без своего релиза: пишется, только если в ряду за период ещё ничего нет."""
    if metric not in spec.metrics or _held(ctx.store, metric, period, spec) is not None:
        return False
    ctx.store.upsert(spec.series(metric), [point(period, value, fetched_at=now, status="ok", source=f"release:{kind}",
                                                 note=DERIVED_NOTE if kind == CALC else "")],
                     unit=spec.unit(metric), basis=spec.basis, label=f"месячный релиз эмитента: {metric}")
    return True


def backfill(ctx: Context, month: str, spec: Monthly, now: str) -> list[tuple[str, str]]:
    """Месяцы без своего релиза — из книги месяца `month` (шапка модуля) → [(период, метрика)] записанного.

    1. Поток, у которого в ряду есть и нарастающий итог, и месяц: нарастающий итог прошлого месяца =
       итог − месяц; месяц прошлого месяца = его итог − итог позапрошлого (январь — сам итог). Только
       если у прошлого месяца нет своего релиза и тождество за него по этому потоку не нарушено.
    2. Числа столбцов сравнения книги (`comparative` кандидата с текстом): остатки на конец прошлого
       месяца и прошлого года, тот же месяц год назад.
    Пишется только отсутствующее: принятое раньше число не переписывается."""
    out: list[tuple[str, str]] = []
    _, m = periods.parse_month(month)
    prev = periods.shift_month(month, -1)
    if m > 1 and not cal.has_release(prev, _calendar(ctx)):
        failed = set((ctx.store.read_state(f"{STATE_DIR}/{prev}.json") or {}).get("identity_flows") or ())
        for flow in _flows(spec):
            if flow in failed:
                continue                # тождество за прошлый месяц не сошлось: поток не выводится
            ytd, mon = _held(ctx.store, f"{flow}_ytd", month, spec), _held(ctx.store, f"{flow}_m", month, spec)
            if ytd is None or mon is None:
                continue
            if _fill(ctx, spec, prev, f"{flow}_ytd", round(ytd - mon, 4), now, CALC):
                out.append((prev, f"{flow}_ytd"))
            before = _held(ctx.store, f"{flow}_ytd", prev, spec)
            base = 0.0 if m == 2 else _held(ctx.store, f"{flow}_ytd", periods.shift_month(prev, -1), spec)
            if before is not None and base is not None \
                    and _fill(ctx, spec, prev, f"{flow}_m", round(before - base, 4), now, CALC):
                out.append((prev, f"{flow}_m"))
    for cand in (ctx.store.read_state(issuer_docs.CANDIDATES_FILE) or {}).values():
        if cand.get("kind") != spec.doc_kind or cand.get("month") != month or cand.get("status") != "ok" \
                or cand.get("method") != TEXT:
            continue
        for period, values in sorted((cand.get("comparative") or {}).items()):
            if not periods.is_month(period) or period >= month:
                continue
            for metric, value in sorted(values.items()):
                if value is None:
                    continue
                if _fill(ctx, spec, period, metric, _share(metric, value, cand), now, COMPARATIVE):
                    out.append((period, metric))
    return out


def pending_months(store: Store, today: date, lookback: int = 2) -> list[str]:
    """Месяцы окна дозора: последние `lookback` месяцев (проход дешёвый и идемпотентный —
    поздние источники дня релиза подтверждают метрики и после приёма главной)."""
    return [periods.shift_month(periods.month_of(today), -back) for back in range(lookback, 0, -1)]


def run(ctx: Context) -> Result:
    """Такт дозора: месяцы окна по очереди, старший первым (тождеству нужен прошлый месяц)."""
    res = Result(name="release_watch")
    for month in pending_months(ctx.store, ctx.today):
        out = watch(ctx, month)
        res.data.setdefault("months", []).append(out)
        if out["new"] or out.get("filled"):
            res.series += [monthly(ctx.cfg).series(m) for m in out["new"]]
            res.series += [monthly(ctx.cfg).series(m) for _, m in out.get("filled") or []]
        if out["mismatches"]:
            res.degrade(f"месячный релиз {month}: источники разошлись — "
                        f"{', '.join(map(metric_words, out['mismatches']))}")
        if out["identity_failures"]:
            res.degrade(f"месячный релиз {month}: нарастающий итог не равен прошлому месяцу плюс месяц — "
                        f"{'; '.join(out['identity_failures'])}")
        if out["revisions"]:
            res.degrade(f"месячный релиз {month}: книга принята, итог прошлого месяца пересмотрен — "
                        f"{'; '.join(out['revisions'])}", retry=False)
    return res


def mismatch_flag(store: Store, months: list[str], *, tolerance_bn: float = 0.15,
                  prefix: str = DEFAULT_PREFIX, check_form: bool = True) -> dict[str, Any]:
    """Флаг `ras_mismatch`: расхождение двух источников дня релиза или прибыли релиза с формой 0409102.
    `check_form=False` (`monthly.form102: false`) — релиз с формой не сверяется: остаётся расхождение
    источников дня релиза."""
    details = []
    rel = store.load(series_id("np_ytd", prefix))
    f102 = store.load("cbr.f102.ni_ytd") if check_form else None
    for m in months:
        st = store.read_state(f"{STATE_DIR}/{m}.json") or {}
        if st.get("mismatches"):
            details.append(f"{m}: источники дня релиза разошлись "
                           f"({', '.join(metric_words(k) for k in sorted(st['mismatches']))})")
        r = None if rel is None else rel.value_as_of(m)
        f = None if f102 is None else f102.value_as_of(m)
        if r is not None and f is not None and abs(r - f) > tolerance_bn:
            details.append(f"{m}: прибыль с начала года по релизу {r:.1f} против формы 0409102 {f:.1f} млрд ₽")
    return {"raised": bool(details), "detail": "; ".join(details)}


def release_month_profit(store: Store, month: str, prefix: str = DEFAULT_PREFIX) -> float | None:
    """Прибыль месяца по релизу: ряд `np_m`, а если его нет — разность нарастающих `np_ytd` соседних
    месяцев (январь — само значение; нет соседнего месяца — None)."""
    monthly_series = store.load(series_id("np_m", prefix))
    if monthly_series is not None:
        return monthly_series.value_as_of(month)
    ytd = store.load(series_id("np_ytd", prefix))
    if ytd is None:
        return None
    return cbr_forms.month_from_ytd(ytd.history()).get(month)


def form102_rows(store: Store, months: list[str], *, tolerance_bn: float = 0.15,
                 prefix: str = DEFAULT_PREFIX, check_form: bool = True) -> list[dict[str, Any]]:
    """П§2 `nowcast.form102`: прибыль месяца по форме 0409102 против релиза (млрд ₽). `check_form=False` —
    релиз с формой не сверяется: строк нет."""
    f = store.load("cbr.f102.ni_ytd") if check_form else None
    if f is None:
        return []
    by_form = cbr_forms.month_from_ytd(f.history())
    out = []
    for m in months:
        ni = by_form.get(m)
        if ni is None:
            continue
        rel = release_month_profit(store, m, prefix)
        seen = f.first_seen(m)
        diff = None if rel is None else round(ni - rel, 4)
        out.append({"month": m, "ni": round(ni, 4), "first_seen": seen, "release_ni": rel, "diff": diff,
                    "ok": None if diff is None else abs(diff) <= tolerance_bn})
    return out
