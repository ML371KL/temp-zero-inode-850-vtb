"""Оценка квартала по напечатанным месяцам того же базиса, что цель (`sources.yaml → nowcast.estimate: months`).

Эмитент печатает месячные результаты в базисе своей квартальной отчётности: месяцы складываются в
квартал без моста. Уравнения без подогнанных коэффициентов (k — известных месяцев квартала):

* **T1 `ni_q`** (поток): оценка = сумма известных месяцев + (3 − k)/3 · ожидание модели. Сумма первых
  месяцев — сами месяцы релиза, а где отдельного месяца нет (первые два месяца года печатаются одной
  суммой) — разность нарастающих итогов. Ожидание модели подставляет тот, кто его считает
  (`nowcast.combine`: такт сборщиков и сборка выпуска — каждый своё).
* **T3 `nim_q`, T4 `cor_q`** (уровни): оценка = среднее напечатанных месячных значений; в первом квартале,
  когда месяцы порознь не напечатаны, — значение с начала года на последний известный месяц.
* прогноз = ожидание + w(k)·(оценка − ожидание), w(k) = σ²_база / (σ²_база + σ²_оценки(k)).

Какие ряды месячного релиза несут месяц и нарастающий итог цели — `nowcast.months` (без ключа —
`SERIES`); начало имён рядов — `monthly.series_prefix`.

**Веса** — из дисперсий, измеренных ретро-проверкой на истории рядов (`flow_sigmas`, `level_sigmas`), и
пересчитываются с каждым новым кварталом. Ожидания модели на прошлые даты нет, поэтому на его месте
стоит наивный эталон: в оценке T1 недостающие месяцы — доля прошлого квартала, σ_база — ошибка лучшего
наивного эталона горизонта T−90 (прошлый квартал, год назад, год назад × рост, гайденс года — если его
история есть в рядах). σ_оценки(k) меряется на знании дня, когда стал известен k-й месяц, и на тех же
кварталах, что σ_база. Это оценка сверху для ошибки модели: веса сдвинуты в пользу месяцев.

**Эталоны по месяцам** (`month_marks`, цель T1): `m12_flat` — два месяца × 1,5; `m12_prev3` — два месяца
плюс третий месяц прошлого квартала; сама оценка (`months`) — когда есть ожидание модели.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping

from indicators import config, journal, periods
from indicators.store import Series, Store

MONTHS = "months"                     # значение настройки `nowcast.estimate`
QUARTER_MONTHS = 3
QUARTERS_IN_YEAR = 4
SERIES: dict[str, dict[str, str]] = {
    "ni_q": {"month": "np_m", "ytd": "np_ytd"},
    "nim_q": {"month": "nim_m", "ytd": "nim_ytd"},
    "cor_q": {"month": "cor_m", "ytd": "cor_ytd"},
}
FLOW_TARGETS = frozenset({"ni_q"})    # цель-поток: месяцы складываются; прочие — уровни: месяцы усредняются
ACTUAL_OF = {"nim_q": "nim", "cor_q": "cor"}
PROXY = "prev_quarter"                # замена ожидания модели в ретро: прошлый отчётный квартал
FLAT_FACTOR = QUARTER_MONTHS / 2      # «два месяца × 1,5»
DEFAULT_PREFIX = "ras.release."
BRIDGE_SOURCE = "months"
MIN_BASE_QUARTERS = 4                 # эталон судится как база σ не меньше чем на стольких кварталах
SCORING_DAYS, PRINT_DAYS = 90, 30     # горизонты журнала по умолчанию (как `nowcast.HORIZON_START`)
# Наивные эталоны — кандидаты базы σ (эталоны по месяцам сюда не входят: они и есть оценка).
BASE_CANDIDATES = ("prev_quarter", "same_quarter_last_year", "yoy_growth", "guidance", "guidance_rest")


def settings(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Блок `sources.yaml → nowcast` (нет файла или блока — пусто)."""
    if cfg is None:
        try:
            cfg = config.sources()
        except config.ConfigError:
            return {}
    block = (cfg or {}).get("nowcast")
    return dict(block) if isinstance(block, Mapping) else {}


def enabled(cfg: Mapping[str, Any] | None = None) -> bool:
    """Оценка квартала — по месяцам базиса цели (`nowcast.estimate: months`); без ключа — «РСБУ × мост»."""
    return str(settings(cfg).get("estimate") or "") == MONTHS


def _prefix(cfg: Mapping[str, Any] | None = None) -> str:
    try:
        block = (cfg if cfg is not None else config.sources()).get("monthly") or {}
    except config.ConfigError:
        block = {}
    return str(block.get("series_prefix") or DEFAULT_PREFIX)


def series_map(cfg: Mapping[str, Any] | None = None) -> dict[str, dict[str, str]]:
    """Цель → {month, ytd}: метрики месячного релиза (`nowcast.months`, иначе `SERIES`)."""
    named = settings(cfg).get("months")
    out = {k: dict(v) for k, v in SERIES.items()}
    if isinstance(named, Mapping):
        for key, node in named.items():
            if key in out and isinstance(node, Mapping):
                out[key].update({k: str(v) for k, v in node.items() if k in ("month", "ytd") and v})
    return out


# ------------------------------------------------------------------ месяцы цели

@dataclass
class Feed:
    """Ряды месяца и нарастающего итога одной цели: что известно о первых месяцах квартала на дату."""

    month: Series | None
    ytd: Series | None
    additive: bool                    # поток (сумма месяцев) или уровень (среднее месяцев)

    @staticmethod
    def _get(series: Series | None, period: str, as_of: str | None) -> tuple[float, str] | None:
        """(значение последней версии, момент первого появления), известные на дату."""
        if series is None:
            return None
        p = series.point_as_of(period, as_of)
        if p is None or p.value is None:
            return None
        return p.value, series.first_seen(period) or p.fetched_at

    def month_value(self, m: str, as_of: str | None) -> tuple[float, str] | None:
        return self._get(self.month, m, as_of)

    def first(self, q: str, as_of: str | None, *, limit: int = QUARTER_MONTHS) -> dict[str, Any] | None:
        """Первые известные месяцы квартала (не больше `limit`): {k, value, known_at, pooled, rows}.

        `value` — сумма месяцев (поток) или их среднее (уровень). Месяцы порознь важнее; нарастающий итог
        берётся, когда он даёт больше месяцев: у потока — итог минус итог конца прошлого квартала (в первом
        квартале — сам итог), у уровня — значение с начала года, только в первом квартале. Ни одного
        месяца — None."""
        months = periods.quarter_months(q)[:max(0, limit)]
        _, n = periods.parse_quarter(q)
        single: list[tuple[float, str]] = []
        for m in months:
            got = self.month_value(m, as_of)
            if got is None:
                break
            single.append(got)
        pooled: tuple[int, float, str] | None = None
        for i in range(len(months) - 1, len(single) - 1, -1):
            end = self._get(self.ytd, months[i], as_of)
            if end is None:
                continue
            if self.additive:
                base = (0.0, "") if n == 1 else self._get(self.ytd, periods.shift_month(periods.quarter_months(q)[0], -1),
                                                           as_of)
                if base is None:
                    continue
                pooled = (i + 1, end[0] - base[0], max(end[1], base[1]))
            elif n == 1:
                pooled = (i + 1, end[0], end[1])
            else:
                continue
            break
        if pooled is not None:
            k, value, moment = pooled
            rows = [{"month": m, "status": "known", "value": value if j == k - 1 else None, "date_known": moment[:10],
                     "pooled": True} for j, m in enumerate(months[:k])]
            rows[-1]["span"] = k
            return {"k": k, "value": value, "known_at": moment, "pooled": True, "rows": rows}
        if not single:
            return None
        values = [v for v, _ in single]
        value = sum(values) if self.additive else sum(values) / len(values)
        rows = [{"month": m, "status": "known", "value": v, "date_known": at[:10]}
                for m, (v, at) in zip(months, single)]
        return {"k": len(single), "value": value, "known_at": max(at for _, at in single), "pooled": False,
                "rows": rows}

    def exactly(self, q: str, k: int, as_of: str | None) -> dict[str, Any] | None:
        """Ровно k первых месяцев квартала, известных на дату (ретро: оценка при k месяцах); иначе None."""
        got = self.first(q, as_of, limit=k) if k > 0 else None
        return got if got is not None and got["k"] == k else None

    def kth_day(self, q: str, k: int) -> str | None:
        """День, когда стали известны k первых месяцев квартала (первая печать); неизвестны — None."""
        got = self.exactly(q, k, None)
        return None if got is None else got["known_at"][:10]

    def last_month(self, q: str, as_of: str | None) -> float | None:
        """Значение последнего месяца квартала: сам месяц, а нет его — разность нарастающих итогов (поток)."""
        months = periods.quarter_months(q)
        got = self.month_value(months[-1], as_of)
        if got is not None:
            return got[0]
        if not self.additive:
            return None
        end, before = self._get(self.ytd, months[-1], as_of), self._get(self.ytd, months[-2], as_of)
        return None if end is None or before is None else end[0] - before[0]


def feeds(store: Store, cfg: Mapping[str, Any] | None = None) -> dict[str, Feed]:
    """Ряды месяцев трёх целей из хранилища."""
    prefix = _prefix(cfg)
    out = {}
    for key, names in series_map(cfg).items():
        out[key] = Feed(month=store.load(f"{prefix}{names['month']}"), ytd=store.load(f"{prefix}{names['ytd']}"),
                        additive=key in FLOW_TARGETS)
    return out


def flow_estimate(known: Mapping[str, Any] | None, rest: float | None) -> float | None:
    """Оценка потока квартала: сумма k известных месяцев + (3 − k)/3 · `rest` (ожидание или его замена)."""
    if known is None:
        return None
    share = (QUARTER_MONTHS - known["k"]) / QUARTER_MONTHS
    if share <= 0:
        return known["value"]
    return None if rest is None else known["value"] + share * rest


# ------------------------------------------------------------------ горизонты

def print_rule(cfg: Mapping[str, Any] | None = None) -> tuple[int, int | None]:
    """Печатный горизонт (`nowcast.print_horizon`): (дней до отчёта, сколько месяцев квартала его открывают).
    Без ключа — 30 дней и никакого события."""
    node = settings(cfg).get("print_horizon")
    if not isinstance(node, Mapping):
        return PRINT_DAYS, None
    need = node.get("months_known")
    return int(node.get("days", PRINT_DAYS)), None if need is None else int(need)


def pure_scoring(cfg: Mapping[str, Any] | None = None) -> bool:
    """Запись зачётного горизонта — ожидание модели без оценки по месяцам (`nowcast.scoring: model`)."""
    return str(settings(cfg).get("scoring") or "") == journal.MODEL_BENCHMARK


def horizon(today: date, report: date, *, months_known: int = 0, cfg: Mapping[str, Any] | None = None) -> str | None:
    """Горизонт записи журнала. Печатный открывается за `days` дней до отчёта либо раньше — событием «известно
    `months_known` месяцев квартала»; до него (от 90 дней) идёт зачётный."""
    days = (report - today).days
    if not 0 < days <= SCORING_DAYS:
        return None
    limit, need = print_rule(cfg)
    if days <= limit or (need is not None and months_known >= need):
        return journal.PRINT_HORIZON
    return journal.SCORING_HORIZON


def print_day(h: Any, feed: Feed, q: str, report: str, cfg: Mapping[str, Any] | None = None) -> str:
    """День печатного горизонта в ретро: отчёт минус `days`, либо раньше — день, когда стали известны нужные
    месяцы квартала; не раньше открытия квартала (выход отчёта за прошлый квартал) и 90 дней до отчёта."""
    limit, need = print_rule(cfg)
    day = (date.fromisoformat(report) - timedelta(days=limit)).isoformat()
    opened = opening_day(h, q, report)
    if need is not None:
        event = feed.kth_day(q, need)
        if event is not None:
            day = min(day, max(event, opened))
    return max(day, opened)


def opening_day(h: Any, q: str, report: str) -> str:
    """Первый день квартала в журнале: 90 дней до отчёта, но не раньше выхода отчёта за прошлый квартал."""
    day = (date.fromisoformat(report) - timedelta(days=SCORING_DAYS)).isoformat()
    opened = h.report_date(periods.shift_quarter(q, -1))
    return max(day, opened) if opened else day


# ------------------------------------------------------------------ гайденс года

def guidance_rule(target: str, cfg: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Правило эталона «гайденс» цели (`nowcast.guidance.<цель>`: `item` — пункт гайденса года, `unit`)."""
    node = (settings(cfg).get("guidance") or {}).get(target) if isinstance(settings(cfg).get("guidance"), Mapping) \
        else None
    return dict(node) if isinstance(node, Mapping) and node.get("item") else None


def guidance_marks(h: Any, q: str, as_of: str, year_value: float | None) -> dict[str, float]:
    """Эталоны T1 из гайденса прибыли года: `guidance` — четверть года; `guidance_rest` — гайденс минус
    отчитанные кварталы года, на оставшиеся кварталы (нужны факты всех прошлых кварталов года)."""
    if year_value is None:
        return {}
    out = {"guidance": year_value / QUARTERS_IN_YEAR}
    year, n = periods.parse_quarter(q)
    done = [h.quarter_ifrs(periods.quarter(year, i), as_of) for i in range(1, n)]
    if all(v is not None for v in done):
        out["guidance_rest"] = (year_value - sum(done)) / (QUARTERS_IN_YEAR - len(done))
    return out


# ------------------------------------------------------------------ эталоны по месяцам

def month_marks(h: Any, feed: Feed, q: str, as_of: str) -> dict[str, float]:
    """Наивные эталоны T1 по двум первым месяцам квартала, известным на дату: `m12_flat`, `m12_prev3`."""
    two = feed.exactly(q, 2, as_of)
    if two is None:
        return {}
    out = {"m12_flat": two["value"] * FLAT_FACTOR}
    third = feed.last_month(periods.shift_quarter(q, -1), as_of)
    if third is not None:
        out["m12_prev3"] = two["value"] + third
    return out


# ------------------------------------------------------------------ σ и веса

def _rmse(xs: list[float]) -> float | None:
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else None


def _best_base(errors: Mapping[str, Mapping[str, float]]) -> tuple[str | None, dict[str, float]]:
    """Лучший наивный эталон базы: наименьшая RMSE среди эталонов не меньше чем с `MIN_BASE_QUARTERS`
    кварталами (нет таких — среди всех); при равенстве — по порядку `BASE_CANDIDATES`."""
    scored = [(name, errs) for name in BASE_CANDIDATES for errs in [errors.get(name) or {}] if errs]
    if not scored:
        return None, {}
    long = [x for x in scored if len(x[1]) >= MIN_BASE_QUARTERS] or scored
    name, errs = min(long, key=lambda x: _rmse(list(x[1].values())))
    return name, dict(errs)


def _guidance_year(store: Store, item: str, year: int, as_of: str) -> float | None:
    from indicators import nowcast  # noqa: PLC0415 — nowcast импортирует этот модуль

    return nowcast.guidance_point(store, item, year, as_of)


def flow_sigmas(store: Store, *, today: date | None = None, cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """σ_оценки(k), k = 1…3, и σ_база цели-потока (относительные ошибки) — для веса w и ошибки года.

    Квартал истории с фактом (`actual.ni_q`, момент — выход отчёта): оценка при k месяцах — на знании дня,
    когда стал известен k-й месяц (не раньше открытия квартала и не позже отчёта), недостающие месяцы —
    доля прошлого квартала (`PROXY`). База — лучший наивный эталон на дату T−90; σ_оценки — на кварталах
    базы. Нет истории — σ пусты, w = 0."""
    from indicators import nowcast, retro  # noqa: PLC0415 — эти модули импортируют этот

    today = today or date.today()
    h = nowcast.History.load(store)
    feed = feeds(store, cfg)["ni_q"]
    rule = guidance_rule("ni_q", cfg)
    base_err: dict[str, dict[str, float]] = {}
    base_abs: dict[str, dict[str, float]] = {}
    est_err: dict[int, dict[str, float]] = {k: {} for k in range(1, QUARTER_MONTHS + 1)}
    est_abs: dict[int, dict[str, float]] = {k: {} for k in range(1, QUARTER_MONTHS + 1)}
    for q in sorted(h.ifrs):
        report = h.report_date(q)
        if report is None or report > today.isoformat():
            continue
        actual = h.ifrs[q][1]
        if not actual:
            continue
        opened = opening_day(h, q, report)
        marks = retro.naive_marks(h, q, opened)
        if rule is not None:
            marks.update(guidance_marks(h, q, opened, _guidance_year(store, str(rule["item"]),
                                                                     periods.parse_quarter(q)[0], opened)))
        for name, value in marks.items():
            base_err.setdefault(name, {})[q] = (value - actual) / actual
            base_abs.setdefault(name, {})[q] = value - actual
        for k in est_err:
            day = feed.kth_day(q, k)
            if day is None:
                continue
            day = max(min(day, report), opened)
            known = feed.exactly(q, k, day)
            last = h.latest_ifrs_quarter(q, day)
            estimate = flow_estimate(known, None if last is None else h.quarter_ifrs(last, day))
            if estimate is not None:
                est_err[k][q] = (estimate - actual) / actual
                est_abs[k][q] = estimate - actual
    name, base = _best_base(base_err)
    common = set(base) if base else None
    pick = lambda errs: [v for q, v in errs.items() if common is None or q in common]  # noqa: E731
    return {"ras": {"0": None, **{str(k): _rmse(pick(est_err[k])) for k in est_err}},
            "base": _rmse(list(base.values())),
            "n": {"ras": {"0": 0, **{str(k): len(pick(est_err[k])) for k in est_err}}, "base": len(base)},
            # те же ошибки в единицах цели (млрд ₽) — для чтения рядом с эталонами ретро-проверки
            "abs": {"base": _rmse(list((base_abs.get(name) or {}).values())),
                    **{str(k): _rmse(pick(est_abs[k])) for k in est_abs}},
            "base_benchmark": name, "proxy": PROXY, "estimate": MONTHS, "quarters": sorted(base)}


def level_sigmas(store: Store, *, today: date | None = None, cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """σ_оценки(k) и σ_база целей-уровней (абсолютные ошибки, доли): `{"nim": {…}, "cor": {…}}`.

    Оценка — среднее месячных значений на знании дня k-го месяца; база — лучший из эталонов «прошлый
    квартал», «год назад» и точки гайденса года на дату T−90."""
    from indicators import nowcast  # noqa: PLC0415 — nowcast импортирует этот модуль

    today = today or date.today()
    h = nowcast.History.load(store)
    all_feeds = feeds(store, cfg)
    out: dict[str, Any] = {}
    for target, key in ACTUAL_OF.items():
        feed = all_feeds[target]
        base_err: dict[str, dict[str, float]] = {}
        est_err: dict[int, dict[str, float]] = {k: {} for k in range(1, QUARTER_MONTHS + 1)}
        for q, (moment, actual) in sorted(h.mgmt.get(key, {}).items()):
            report = moment[:10]
            if report > today.isoformat():
                continue
            opened = opening_day(h, q, report)
            for name, value in level_marks(h, store, key, q, opened).items():
                base_err.setdefault(name, {})[q] = value - actual
            for k in est_err:
                day = feed.kth_day(q, k)
                if day is None:
                    continue
                known = feed.exactly(q, k, max(min(day, report), opened))
                if known is not None:
                    est_err[k][q] = known["value"] - actual
        name, base = _best_base(base_err)
        common = set(base) if base else None
        pick = lambda errs: [v for q, v in errs.items() if common is None or q in common]  # noqa: E731
        out[key] = {"ras": {"0": None, **{str(k): _rmse(pick(est_err[k])) for k in est_err}},
                    "base": _rmse(list(base.values())),
                    "n": {"ras": {"0": 0, **{str(k): len(pick(est_err[k])) for k in est_err}}, "base": len(base)},
                    "unit": "share (абсолютная ошибка)", "base_benchmark": name, "estimate": MONTHS,
                    "quarters": sorted(base)}
    return out


def level_marks(h: Any, store: Store, key: str, q: str, as_of: str) -> dict[str, float]:
    """Наивные эталоны уровня (ЧПМ, стоимость риска) на дату: прошлый квартал, год назад, точка гайденса года."""
    out: dict[str, float] = {}
    prev = h.mgmt_quarter(key, periods.shift_quarter(q, -1), as_of)
    if prev is not None:
        out["prev_quarter"] = prev
    ly = h.mgmt_quarter(key, periods.shift_quarter(q, -4), as_of)
    if ly is not None:
        out["same_quarter_last_year"] = ly
    point = _guidance_year(store, key, periods.parse_quarter(q)[0], as_of)
    if point is not None:
        out["guidance"] = point
    return out


def measured_sigma(table: Mapping[str, Any] | None, k: int) -> float | None:
    """σ оценки уровня при `k` известных месяцах. Если при таком числе месяцев она не измерена (в истории нет
    кварталов, где к отчёту известны все три месяца: третий месяц квартала эмитент отдельно не печатает, он
    приходит ручным вводом) — σ ближайшего меньшего измеренного числа месяцев: среднее по большему числу
    месяцев квартала не грубее. Иначе ручной ввод третьего месяца обнулял бы вес оценки."""
    table = table or {}
    for j in range(int(k), 0, -1):
        value = table.get(str(j))
        if value is not None:
            return value
    return None


# ------------------------------------------------------------------ входы нау-каста

def inputs(store: Store, *, period: str, today: date, sigmas: Mapping[str, Any] | None = None,
           frozen: Mapping[str, Any] | None = None, targets: Any = None,
           cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Месяцы квартала, оценки по месяцам, w и ошибки трёх целей — без ожидания модели (вид — как у
    `nowcast.ras_inputs`). Цель-поток несёт `known_sum` и `model_share`: оценку квартала достраивает
    `nowcast.combine`, у которого есть ожидание. Моста нет (`bridge: null`): базис месяцев и цели один."""
    from indicators import nowcast  # noqa: PLC0415 — nowcast импортирует этот модуль

    frozen = dict(frozen or {})
    as_of = today.isoformat()
    if sigmas is None and not frozen.get("sigmas"):
        sigmas = {**flow_sigmas(store, today=today, cfg=cfg), **level_sigmas(store, today=today, cfg=cfg)}
    sigmas = dict(sigmas or {})
    all_feeds = feeds(store, cfg)
    labels = journal.targets(targets)
    words = nowcast.equation_words()
    by_key: dict[str, Any] = {}
    # T1: сумма известных месяцев; недостающие — долей ожидания модели (в `combine`)
    known = all_feeds["ni_q"].first(period, as_of)
    sig = frozen.get("sigmas") or sigmas
    k = known["k"] if known else 0
    s_est, s_base = (sig.get("ras") or {}).get(str(k)), sig.get("base")
    w = nowcast.weight(s_base, s_est) if known else 0.0
    by_key["ni_q"] = {
        "ras_estimate": None, "bridge": None, "bridge_source": BRIDGE_SOURCE if known else None,
        "bridge_quarters": [], "ras_bridged": None,
        "known_sum": known["value"] if known else None,
        "model_share": (QUARTER_MONTHS - k) / QUARTER_MONTHS if known else None,
        "w": w, "sigma_ras": s_est, "sigma_base": s_base,
        "rel_std_error": math.sqrt(w) * s_est if known and s_est is not None and s_base is not None else None,
        "months_known": k, "basis": labels["ni_q"]["basis"], "estimate": MONTHS,
        "equation": (words["equations"]["ni_q"] + ("; " + words["no_sigma"] if w == 0.0 else "")) if known
        else words["no_estimate"]["ni_q"]}
    extra = nowcast._release_months(store, period, as_of)
    rows = {r["month"]: r for r in (known["rows"] if known else [])}
    months = []
    for m in periods.quarter_months(period):
        r = rows.get(m)
        row = {"month": m, "status": "known" if r else "estimated", "source": "release" if r else "model",
               "date_known": r["date_known"] if r else None, "ni": r["value"] if r else None}
        if r and r.get("pooled"):
            row["pooled"] = True
        if r and r.get("span"):
            row["span"] = r["span"]
        row.update(extra.get(m, {"nii": None, "llp": None}))
        months.append(row)
    # T3, T4: среднее месячных значений
    for target, key in ACTUAL_OF.items():
        got = all_feeds[target].first(period, as_of)
        fz = dict(frozen.get(key) or {})
        tsig = fz.get("sigmas") or sigmas.get(key) or {}
        kk = got["k"] if got else 0
        e, b = measured_sigma(tsig.get("ras"), kk), tsig.get("base")
        ww = nowcast.weight(b, e) if got else 0.0
        by_key[target] = {
            "ras_estimate": got["value"] if got else None, "bridge": None,
            "bridge_source": BRIDGE_SOURCE if got else None, "ras_bridged": got["value"] if got else None,
            "w": ww, "sigma_ras": e, "sigma_base": b,
            "std_error": math.sqrt(ww) * e if got and e is not None and b is not None else None,
            "rel_std_error": None, "months_known": kk, "basis": labels[target]["basis"], "estimate": MONTHS,
            "level_months": [{"month": r["month"], "value": r["value"]} for r in (got["rows"] if got else [])],
            "equation": (words["equations"][target] + ("; " + words["no_sigma"] if ww == 0.0 else "")) if got
            else words["no_estimate"][target]}
    return {"period": period, "as_of": as_of, "months": months, "months_known": k, "targets": by_key,
            "profile": {}, "profile_base": None, "sigmas": sig, "equation": words["equations"]["ni_q"],
            "version": nowcast.VERSION, "estimate": MONTHS}
