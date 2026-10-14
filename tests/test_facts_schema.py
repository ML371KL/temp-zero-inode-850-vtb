"""Факты: схема узлов и происхождение каждого числа (data/facts/SCHEMA.md).

Каждое число — узел {v, src|calc}; null — с причиной; src ссылается на документ реестра
(anchor.json → documents или sources ручного файла) по префиксу sha256; базисы помечены;
поля, которые читает ядро (методика, приложение B), на месте и не null; нет следов
частной машины в публичных файлах. Факты — Банка ВТБ (тикер VTBR) на якоре 2К2026: девять книг
договора фазы 3, годовой календарь дивидендов, упр. метрики только напечатанные (точных банк не публикует).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tact          # быстрые (≈1 с): схема и провенанс идут в такте сервера

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
BUILT = ("anchor", "balance", "nii_books", "pnl_quarterly", "capital", "shares", "dividends",
         "bridge_mgmt_ifrs", "bridge_ras_ifrs", "mgmt_quarterly", "guidance")
MANUAL = ("calendar", "peers")
ALL = BUILT + MANUAL
BASES = {"IFRS", "RAS", "mgmt", "mgmt↔IFRS", "RAS→IFRS", "mixed"}
# голые числа вне узлов: год (`year`, год дивиденда к выплате годового календаря) и коэффициент консолидации строки
# дивиденда (SCHEMA.md §1)
BARE_NUMBER_KEYS = {"year", "split_factor", "dividends_payable_year"}
# числовые поля внутри узла: допуск точечного гайденса; у оценочного узла — границы оценки `range: [низ, верх]`
NODE_NUMBER_KEYS = {"tol"}
NODE_RANGE_KEY = "range"
# девять книг договора фазы 3 (книга `nii.books`): три кредитные, бумаги, доходная ликвидность; четыре пассивные
BOOKS = ("corp_loans", "mortgage", "consumer_loans", "securities", "liquidity",
         "retail_current", "retail_term", "corp_funds", "wholesale")
ASSET_BOOKS, LOAN_BOOKS, LIABILITY_BOOKS = BOOKS[:5], BOOKS[:3], BOOKS[5:]
SHA_RE = re.compile(r"sha256 ([0-9a-f]{16})")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STUB = "ЗАГЛУШКА"                     # файл в форме схемы без чисел: собирается позже (слово стоит в его описании)


def load(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def has_text(x) -> bool:
    return isinstance(x, str) and any(ch.isalnum() for ch in x)


def walk(obj, path=""):
    """(путь, значение, ключ) для всех значений дерева."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield p, v, k
            yield from walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}.{i}"
            yield p, v, None
            yield from walk(v, p)


def nodes(obj):
    for p, v, _ in walk(obj):
        if isinstance(v, dict) and "v" in v:
            yield p, v


def get(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


def anchor_period() -> str:
    return load("anchor")["period"]


def year_quarters(period: str) -> list[str]:
    return [f"{period[:4]}Q{k}" for k in range(1, int(period[-1]) + 1)]


def is_stub(data: dict) -> bool:
    return any(STUB in str(data.get(k) or "") for k in ("definition", "basis", "note"))


@pytest.mark.parametrize("name", ALL)
def test_file_present_and_parses(name):
    path = FACTS / f"{name}.json"
    assert path.exists(), f"нет {path.name}"
    raw = path.read_bytes()
    assert b"\r\n" not in raw, f"{name}.json: переводы строк CRLF"
    data = json.loads(raw.decode("utf-8"))
    assert DATE_RE.match(str(data.get("as_of", ""))), f"{name}.json: нет as_of YYYY-MM-DD"


def test_the_facts_are_of_one_issuer_and_one_anchor():
    """Все файлы сборщика — на одном якоре; эмитент — один тикер (следов чужих фактов в каталоге нет)."""
    a = load("anchor")
    assert re.fullmatch(r"\d{4}Q[1-4]", a["period"])
    for name in BUILT:
        if name != "guidance":                         # у гайденса as_of — день последнего подтверждения
            assert load(name)["as_of"] == a["as_of"], f"{name}.json: as_of не на якоре"
    assert load("guidance")["as_of"] > a["as_of"] or load("guidance")["year"] == int(a["period"][:4])
    assert list(load("shares")["by_ticker"]) == [load("peers")["subject_ticker"]] == ["VTBR"]
    assert tuple(load("balance")["books"]) == BOOKS == tuple(load("nii_books")["books"])
    extra = sorted(p.name for p in FACTS.iterdir() if p.name not in {f"{n}.json" for n in ALL} | {"SCHEMA.md"})
    assert not extra, f"в каталоге фактов лишнее: {extra}"


@pytest.mark.parametrize("name", BUILT + ("peers",))
def test_basis_declared(name):
    data = load(name)
    assert data.get("basis"), f"{name}.json: нет basis"
    if name == "peers":
        for b in data["banks"]:
            assert has_text(b.get("basis")), f"peers {b.get('ticker')}: нет basis"
        return
    assert data["basis"] in BASES, f"{name}.json: basis {data['basis']!r} вне {sorted(BASES)}"
    if data["basis"] == "mixed":
        # у каждого узла и блока верхнего уровня смешанного файла — свой basis; в списках — у каждого узла
        for k, v in data.items():
            if isinstance(v, dict):
                assert has_text(v.get("basis")), f"{name}.{k}: у блока/узла смешанного файла нет basis"
            elif isinstance(v, list):
                for i, row in enumerate(v):
                    for kk, n in row.items():
                        if isinstance(n, dict) and "v" in n:
                            assert has_text(n.get("basis")), f"{name}.{k}.{i}.{kk}: нет basis"


@pytest.mark.parametrize("name", ALL)
def test_every_number_is_a_node_with_provenance(name):
    data = load(name)
    bad = []
    node_paths = set()
    for p, v in nodes(data):
        node_paths.add(p)
        val = v["v"]
        if val is None:
            if not has_text(v.get("calc")):
                bad.append(f"{p}: null без причины в calc")
            continue
        if not is_num(val):
            bad.append(f"{p}: v не число ({val!r})")
        if not (has_text(v.get("src")) or has_text(v.get("calc"))):
            bad.append(f"{p}: число без src и calc")
        rng = v.get(NODE_RANGE_KEY)
        if rng is not None:
            ok = isinstance(rng, list) and len(rng) == 2 and all(is_num(x) for x in rng) and rng[0] <= rng[1]
            if not ok or not (rng[0] - 1e-9 <= val <= rng[1] + 1e-9):
                bad.append(f"{p}: границы оценки {rng!r} — пара чисел вокруг значения {val}")
    # голые числа вне узлов; внутри узла — только поля NODE_NUMBER_KEYS и границы оценки
    for p, v, key in walk(data):
        if is_num(v):
            parent, _, last = p.rpartition(".")
            if last == "v":
                continue
            if key in NODE_NUMBER_KEYS:
                owner = get(data, parent)
                if not (isinstance(owner, dict) and "v" in owner):
                    bad.append(f"{p}: поле {key} вне узла")
            elif key is None and parent.endswith("." + NODE_RANGE_KEY) and parent.rpartition(".")[0] in node_paths:
                continue
            elif key not in BARE_NUMBER_KEYS:
                bad.append(f"{p}: голое число {v} вне узла")
    assert not bad, "\n".join(bad[:30])


@pytest.mark.parametrize("name", ALL)
def test_nulls_carry_a_reason_and_are_not_zeros(name):
    """Нераскрытое — null с причиной словами; причина не подменяет источник и не пуста."""
    bad = [p for p, v in nodes(load(name)) if v["v"] is None and (len(str(v.get("calc") or "")) < 12 or v.get("src"))]
    assert not bad, f"{name}: null без содержательной причины или с источником: {bad[:10]}"


def registry(name: str) -> dict[str, dict]:
    docs = load(name)["sources"] if name in MANUAL else load("anchor")["documents"]
    return {d["sha256"][:16]: d for d in docs}


@pytest.mark.parametrize("name", ALL)
def test_src_resolves_to_registry(name):
    data = load(name)
    reg = registry(name)
    bad = []
    for p, v, key in walk(data):
        if key == "src" and isinstance(v, str):
            shas = SHA_RE.findall(v)
            if not shas:
                bad.append(f"{p}: в src нет sha256 документа")
            for s in shas:
                if s not in reg:
                    bad.append(f"{p}: sha256 {s} нет в реестре")
    assert not bad, "\n".join(bad[:30])


def test_every_registered_document_is_cited():
    """Реестр якоря — только документы, на которые ссылается хотя бы один узел (лишних записей нет)."""
    cited = set()
    for name in BUILT:
        cited |= set(SHA_RE.findall(json.dumps(load(name), ensure_ascii=False)))
    cited.add(load("dividends")["policy"]["sha256"][:16])
    unused = sorted(d["key"] for s, d in registry("anchor").items() if s not in cited)
    assert not unused, f"документы реестра без ссылок: {unused}"
    for name in MANUAL:
        text = json.dumps({k: v for k, v in load(name).items() if k != "sources"}, ensure_ascii=False)
        unused = sorted(d["key"] for s, d in registry(name).items() if s not in set(SHA_RE.findall(text)))
        assert not unused, f"{name}: источники без ссылок: {unused}"


def test_src_names_a_page_or_a_cell():
    """Источник числа отчётности — страница документа или адрес «Лист!Ячейка» (лист Databook эмитента называется
    по-русски и с номером: «2.P&L», «3.Баланс »); файл без места — только у листов этапа 1, форм Банка России и
    решений о дивидендах (там место названо словами)."""
    place = re.compile(r", (?:с\. \d|[^,;!]+![A-Z]+\d+|прим\. |форма \d{7}|решение \d\d\.\d\d\.\d{4}|[а-яё])")
    bad = []
    for name in ("balance", "nii_books", "pnl_quarterly", "mgmt_quarterly"):
        for p, v in nodes(load(name)):
            for part in (v.get("src") or "").split("; "):
                if part and not place.search(part):
                    bad.append(f"{name}.{p}: {part}")
    assert not bad, "\n".join(bad[:20])


# «расчёт: 9M2025 − 6M2025 = 25.8 − 19.1»: периоды нарастающих итогов и числа уменьшаемого и вычитаемого
DIFF_RE = re.compile(r"(\d[MМ]\d{4}|FY\d{4}|\dQ\d{4}) − (\d[MМ]\d{4}|FY\d{4}|\dQ\d{4}) = (\(?−?[\d ]+[.,]?\d*\)?) − "
                     r"(\(?−?[\d ]+[.,]?\d*\)?)")


def _num(x: str) -> float:
    return float(x.replace("−", "-").replace(" ", "").replace(",", ".").strip("()"))


def test_quarter_differences_state_the_formula():
    """Квартал-разность нарастающих итогов несёт формулу в calc: страница из src печатает уменьшаемое и вычитаемое, а
    не само число. У ВТБ отчёты за 6М печатают и колонку квартала, а отчёт об изменениях капитала за 9М и годовой
    отчёт — только нарастающий итог: 4-й квартал по годовому отчёту — всегда разность (calc называет итог 9М);
    формула с числами даёт значение узла."""
    marked, bad = 0, []
    fy = re.compile(r"FY\d{4}_ifrs_fs\.pdf")
    for period, row in load("pnl_quarterly")["quarters"].items():
        for p, v in nodes(row):
            if v["v"] is None:
                continue
            calc = v.get("calc") or ""
            m = DIFF_RE.search(calc)
            if period.endswith("Q4") and fy.search(v.get("src") or "") and not re.search(r"9[MМ]\d{4}", calc):
                bad.append(f"{period}.{p}: 4-й квартал по годовому отчёту без итога девяти месяцев в calc")
            if m:
                marked += 1
                a, b = _num(m.group(3)), _num(m.group(4))
                if abs(abs(a - b) - abs(v["v"])) > 0.051:
                    bad.append(f"{period}.{p}: {a} − {b} не даёт {v['v']}")
                if not SHA_RE.search(v.get("src") or ""):
                    bad.append(f"{period}.{p}: формула разности без отчёта-источника")
    assert not bad, "\n".join(bad[:20])
    assert marked >= 2, "в ряду ОПУ нет ни одного квартала-разности — проверьте признак"


@pytest.mark.parametrize("name", ("anchor", "calendar", "peers"))
def test_registry_entries(name):
    data = load(name)
    docs = data["documents"] if name == "anchor" else data["sources"]
    if name == "peers" and is_stub(data):
        assert docs == [] and data["banks"] == [], "заглушка аналогов — без строк и без источников"
        return
    assert docs
    keys, shas = set(), set()
    for d in docs:
        assert re.fullmatch(r"[0-9a-f]{64}", d["sha256"]), d
        assert has_text(d.get("title")), f"{d['key']}: нет заголовка"
        assert d["key"] not in keys, f"повтор ключа {d['key']}"
        keys.add(d["key"])
        assert d["sha256"][:16] not in shas, f"коллизия префикса sha256 {d['sha256'][:16]}"
        shas.add(d["sha256"][:16])
        f = d.get("file")
        if f is not None:
            assert not re.match(r"^([A-Za-z]:|/|\\)", f), f"{d['key']}: абсолютный путь"
            assert ".." not in f.split("/"), f"{d['key']}: путь с .."


@pytest.mark.docs                       # читает и data/facts/SCHEMA.md (коммит из одних *.md — docs.yml)
def test_no_private_traces():
    pats = {
        "абсолютный путь": re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|\\Users\\"),
        "почта": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
        "IPv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "токен": re.compile(r"(?i)(bearer\s+[a-z0-9._-]{10,}|token\s*[:=]\s*\S{10,}|t\.[A-Za-z0-9_-]{40,})"),
    }
    bad = []
    for path in sorted(FACTS.glob("*")):
        if path.suffix not in (".json", ".md"):
            continue
        text = path.read_text(encoding="utf-8")
        for what, rx in pats.items():
            m = rx.search(text)
            if m:
                bad.append(f"{path.name}: {what}: {m.group(0)[:40]}")
    assert not bad, "\n".join(bad)


# Поля, которые ядро требует числом (договор ключей фазы 3; `model.book.anchor_facts`, гейты гайденса книги):
# узел с числом.
CORE_NUMBERS = {
    "balance": [f"books.{b}" for b in BOOKS] + [
        "securities.fvoci_debt", "securities.fvoci_repo", "securities.fvtpl_bonds", "allowance_ac", "other_assets",
        "other_assets_fixed", "other_assets_fixed_parts.dta", "other_assets_fixed_parts.goodwill",
        "other_assets_fixed_parts.associates", "other_liabilities", "dividends_payable", "equity.bv_common", "equity.at1",
        "equity.nci", "equity.total", "prev_year_end.loans_corporate", "prev_year_end.loans_retail", "total_assets",
        "total_liabilities", "iea"],
    "nii_books": ["dia_q", "nii_q", "nim_eng_q", "current_share_anchor", "key_avg_anchor_q", "other_interest_net_q"]
    + [f"books.{b}.{f}" for b in BOOKS for f in ("balance_open", "balance_close", "balance_avg", "interest_q", "rate_anchor")],
    "capital": ["at1.amount", "at1.coupon_annual", "at1.coupon_quarter", "t2_recognized", "basel.cet1", "basel.rwa",
                "n20_0.value", "n1_1_bank.value", "n20_2", "fvoci_reserve", "bank_base_capital",
                "group_capital.total", "group_capital.base", "group_capital.additional", "group_capital.supplementary",
                "ofz_curve_anchor.1", "ofz_curve_anchor.3", "ofz_curve_anchor.5", "ofz_curve_anchor.10"],
    "shares": ["issued_total", "issued_ordinary", "treasury_ordinary", "outstanding_total", "outstanding_ordinary",
               "economic_treasury"],
    "bridge_mgmt_ifrs": ["cor.value", "nim.value", "cir.value", "cor.sd", "nim.sd", "cir.sd", "cor.n", "nim.n", "cir.n"],
    # пункты гайденса, которые читает книга (checks.guidance_items)
    "guidance": ["items.op_np_growth", "items.nim", "items.cor_max", "items.cir", "items.roe", "items.fee_growth",
                 "items.n20_0", "items.loan_growth_corporate", "items.loan_growth_retail"],
    "dividends": ["policy.payout_min"],
}
CORE_PLAIN = {
    "anchor": ["as_of", "period"],
    "balance": ["dividends_payable_year", "dividends_payable_declared", "prev_year_end.as_of", "history"],
    "capital": ["n20_0.as_of", "n20_0.pre_dividend", "n20_0.estimated", "n1_1_bank.as_of", "n1_1_bank.estimated", "history"],
    "bridge_mgmt_ifrs": ["window", "cor.method", "nim.method", "cir.method"],
    "bridge_ras_ifrs": ["quarters", "by_quarter"],
    "guidance": ["year", "as_of", "history"],
    "dividends": ["policy.cap", "policy.threshold", "policy.valid_until", "policy.frequency", "history", "years",
                  "register_seed"],
    "shares": ["corporate_actions", "by_ticker"],
}


@pytest.mark.parametrize("name", sorted(set(CORE_NUMBERS) | set(CORE_PLAIN)))
def test_core_fields_present(name):
    data = load(name)
    bad = []
    for path in CORE_NUMBERS.get(name, []):
        try:
            n = get(data, path)
        except (KeyError, IndexError, TypeError):
            bad.append(f"{name}.{path}: нет")
            continue
        if not (isinstance(n, dict) and "v" in n) or n["v"] is None:
            bad.append(f"{name}.{path}: не узел с числом")
    for path in CORE_PLAIN.get(name, []):
        try:
            get(data, path)
        except (KeyError, IndexError, TypeError):
            bad.append(f"{name}.{path}: нет поля")
    assert not bad, "\n".join(bad)


def test_nodes_of_the_annual_form_and_what_the_issuer_has_not():
    """Годовой календарь дивидендов (форма семейства, как у Сбера): год дивиденда к выплате — голым годом рядом с
    суммой; узлов, которых у ВТБ нет: блока непрофильного пакета в ОПУ (весь результат группы — прибыль движка),
    депозитарного блока акций и голосующих акций; цели ROE сверх года и ориентира DPS банк не называет."""
    b = load("balance")
    declared = b["dividends_payable_declared"]
    assert isinstance(b["dividends_payable_year"], int) and b["dividends_payable_year"] < int(anchor_period()[:4]) + 1
    assert [x["period"] for x in declared] == [f"{b['dividends_payable_year']}Q4"], "годовое решение — 4-м кварталом года"
    assert load("dividends")["policy"]["frequency"] == "annual"
    for p, row in load("pnl_quarterly")["quarters"].items():
        assert "investment_block" not in row, p
        assert row["noncore_net"]["v"] == 0.0 and "непрофильного" in row["noncore_net"]["calc"], p
    s = load("shares")
    assert "depositary_block" not in s and "voting" not in s
    for k in ("roe_target", "dps_growth"):
        n = load("guidance")["items"][k]
        assert n["v"] is None and "не раскрыто" in n["calc"], k


def test_pnl_quarters_cover_anchor_year_and_four_before():
    """Ядро читает строки ОПУ года якоря и четырёх кварталов до первого прогнозного; прибыль акционеров — с начала
    прошлого года (база дивиденда, гайденс). Ряд кварталов — без пропусков и кончается якорем."""
    q = load("pnl_quarterly")["quarters"]
    anchor = anchor_period()
    y, k = int(anchor[:4]), int(anchor[-1])
    need = []
    for _ in range(max(4, k) + 4):
        need.append(f"{y}Q{k}")
        y, k = (y - 1, 4) if k == 1 else (y, k - 1)
    fields = ("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt", "tax", "ni",
              "ni_shareholders", "misc_net", "ni_nci", "dia", "at1_coupon", "key_avg")
    bad = [f"{p}.{f}" for p in need for f in fields if p not in q or q[p][f]["v"] is None]
    assert not bad, "нет чисел ОПУ: " + ", ".join(bad)
    periods = list(q)
    assert periods == sorted(periods) and max(q) == anchor and min(q) <= min(need)
    for a, b in zip(periods, periods[1:]):
        ya, ka = int(a[:4]), int(a[-1])
        assert b == (f"{ya + 1}Q1" if ka == 4 else f"{ya}Q{ka + 1}"), f"пропуск в ряду ОПУ после {a}"


def test_pnl_file_declares_the_reported_basis():
    """Прибыль движка ВТБ — отчётная прибыль акционеров по МСФО (`profit_basis: reported`): строки отчётности —
    в `reported` (прибыль до налога, налог, прибыль после налога, убыток дочерних компаний для перепродажи, вся
    прибыль); годы — суммы строк Databook."""
    p = load("pnl_quarterly")
    assert p["basis"] == "IFRS" and p["profit_basis"] == "reported"
    for per, row in p["quarters"].items():
        assert set(row["reported"]) == {"pbt", "tax", "np_after_tax", "np_resale_subs", "ni"}, per
    assert sorted(p["years"]) == [str(y) for y in range(int(min(p["quarters"])[:4]), int(anchor_period()[:4]))]


def test_balance_history_covers_five_quarter_ends():
    """Якорь и четыре конца кварталов до него — числами (связь с объёмом, веса упр. метрик, годовые отношения)."""
    h = load("balance")["history"]
    p, need = anchor_period(), []
    for _ in range(5):
        need.append(p)
        y, k = int(p[:4]), int(p[-1])
        p = f"{y - 1}Q4" if k == 1 else f"{y}Q{k - 1}"
    for per in need:
        assert per in h, f"нет конца квартала {per}"
        for f in ("bv_common", "loans", "loans_ac_gross", "funds", "iea", "total_assets"):
            assert h[per][f]["v"] is not None, f"{per}.{f}"
        assert DATE_RE.match(h[per]["date"])


def test_bridge_window_matches_history():
    b = load("bridge_mgmt_ifrs")
    assert b["window"] == b["cor"]["window"] == b["cir"]["window"]
    for x in ("cor", "nim", "cir"):
        lo, hi = b[x]["window"]
        periods = [h["period"] for h in b[x]["history"]]
        assert lo in periods and hi in periods, f"{x}: окно вне истории"
        assert hi == anchor_period() and b[x]["method"] == "additive"
    assert b["nim"]["window"] == [year_quarters(anchor_period())[0], anchor_period()]


def test_bridge_history_carries_every_reported_quarter_of_the_anchor_year():
    """Год гайденса в упр. базисе собирается из упр. факта отчётных кварталов года якоря: история моста обязана
    нести каждый такой квартал числами — иначе ядро отказывает."""
    b = load("bridge_mgmt_ifrs")
    need = year_quarters(anchor_period())
    for x in ("cor", "nim", "cir"):
        rows = {h["period"]: h for h in b[x]["history"]}
        bad = [p for p in need if p not in rows or any(rows[p][f]["v"] is None for f in ("mgmt", "engine", "gap"))]
        assert not bad, f"{x}: в истории моста нет отчётных кварталов года якоря {bad}"


MGMT = ("nim", "cor", "cir", "roe")


def test_mgmt_quarters_carry_printed_values_and_the_recalculation():
    """Напечатанное в Databook — без суффикса (с точностью 0,1 п.п.); точных значений банк не публикует — узлов
    `_exact` нет; пересчёт по определению банка — `_recalc` рядом. Расходы к доходам воспроизводятся в каждом
    квартале с пересчётом, на якоре — все четыре метрики (расхождение — не больше округления печати)."""
    m = load("mgmt_quarterly")
    for p, row in m["quarters"].items():
        assert not [k for k in row if k.endswith("_exact")], p
        for k in MGMT + ("roa", "np", "np_shareholders", "cor_corp", "cor_retail"):
            assert k in row, f"{p}.{k}"
        for k in MGMT:                    # стоимость риска бывает отрицательной (роспуск резервов 4К2024)
            assert row[k]["v"] is not None and (abs(row[k]["v"]) if k == "cor" else row[k]["v"]) < 1, f"{p}.{k}"
            assert k == "cor" or row[k]["v"] > 0, f"{p}.{k}"
        rc = row.get("cir_recalc")
        if rc is not None and rc["v"] is not None:
            assert abs(row["cir"]["v"] - rc["v"]) <= 0.0005 + 1e-9, f"{p}: C/I печати и пересчёта"
    a = m["quarters"][anchor_period()]
    for k in MGMT:
        assert a[k + "_recalc"]["v"] is not None and abs(a[k]["v"] - a[k + "_recalc"]["v"]) <= 0.0005 + 1e-9, k
    assert sorted(m["quarters"]) == list(m["quarters"]) and min(m["quarters"]) == min(load("pnl_quarterly")["quarters"])
    q = load("pnl_quarterly")["quarters"]
    for p, row in m["quarters"].items():
        assert row["np"]["v"] == q[p]["ni"]["v"] and row["np_shareholders"]["v"] == q[p]["ni_shareholders"]["v"], p


def test_history_gaps_name_every_partly_empty_quarter():
    """`history_gaps` — провалы раскрытия отчётной истории: записи `{period, basis, reason}`; `period` — квартал или
    диапазон «ГГГГQn–ГГГГQn» по порядку; базис `mgmt` называет каждую пустую упр. метрику кварталов ряда (у ВТБ —
    стоимость риска по сегментам: только нарастающим итогом), базис `ifrs` — кварталы до первой формы 0409805 с
    нормативами группы (история капитала начинается следующим кварталом)."""
    m = load("mgmt_quarterly")
    words = {"cor_corp": "по сегментам", "cor_retail": "по сегментам"}
    named: dict[str, dict[str, str]] = {"mgmt": {}, "ifrs": {}}

    def span(lo: str, hi: str) -> list[str]:
        out, (y, k) = [], (int(lo[:4]), int(lo[-1]))
        while f"{y}Q{k}" <= hi:
            out.append(f"{y}Q{k}")
            y, k = (y + 1, 1) if k == 4 else (y, k + 1)
        return out

    for g in m["history_gaps"]:
        assert set(g) == {"period", "basis", "reason"} and g["basis"] in named and has_text(g["reason"]), g
        lo, _, hi = g["period"].partition("–")
        quarters = span(lo, hi or lo)
        assert quarters and not set(quarters) & set(named[g["basis"]]), f"диапазон {g['period']} пуст или пересекается"
        named[g["basis"]].update({p: g["reason"] for p in quarters})
    for p, row in m["quarters"].items():
        for k, w in words.items():
            if row[k]["v"] is None:
                assert p in named["mgmt"] and w in named["mgmt"][p], f"{p}: пустая {k} не названа"
    first_capital = min(h["period"] for h in load("capital")["history"])
    y, k = int(first_capital[:4]), int(first_capital[-1])
    before = f"{y - 1}Q4" if k == 1 else f"{y}Q{k - 1}"
    assert before in named["ifrs"] and first_capital not in named["ifrs"], "базис ifrs: кварталы до первой формы 0409805"


def test_mgmt_annual_nodes_have_a_source():
    m = load("mgmt_quarterly")
    anchor = anchor_period()
    last_full = int(anchor[:4]) - (0 if anchor.endswith("Q4") else 1)
    assert sorted(m["annual"]) == [str(y) for y in range(int(min(m["quarters"])[:4]), last_full + 1)]
    for y, rec in m["annual"].items():
        assert set(rec) == {"nim", "cor", "cir", "roe", "roa"}, y
        for f, n in rec.items():
            assert has_text(n.get("src")) if n["v"] is not None else has_text(n.get("calc")), f"annual.{y}.{f}"
            assert n["v"] is None or 0 < n["v"] < 1, f"annual.{y}.{f}: не доля"


def test_shares_and_ratios_are_fractions_or_millions():
    """Единицы: нормативы и ставки — доли (не проценты); акции — млн шт. (в нынешних акциях после консолидации 5000:1)."""
    cap, nb, sh = load("capital"), load("nii_books"), load("shares")
    for path in ("n20_0.value", "n1_1_bank.value", "n20_2"):
        assert 0.03 < get(cap, path)["v"] < 0.5, path
    for b in BOOKS:
        assert 0.0 < nb["books"][b]["rate_anchor"]["v"] < 0.6, b
    assert 1000 < sh["issued_total"]["v"] < 100000
    for p, row in load("pnl_quarterly")["quarters"].items():
        assert 0.0 < row["key_avg"]["v"] < 0.5, f"{p}: key_avg не доля"


def test_estimated_flags_are_booleans_and_explained():
    """Оценочный узел несёт estimated: true и слова о способе оценки; на якоре с вышедшими документами оценок нет."""
    for name in BUILT:
        for p, v in nodes(load(name)):
            if "estimated" in v:
                assert v["estimated"] is True and has_text(v.get("calc")), f"{name}.{p}"
    cap = load("capital")
    for slot in ("n20_0", "n1_1_bank"):
        assert isinstance(cap[slot]["estimated"], bool)
        assert ("estimate" in cap[slot]) == cap[slot]["estimated"], slot


def test_ras_bridges_are_blocks_or_a_declared_stub():
    """Мост РСБУ → МСФО у ВТБ не собран (формы 0409101/0409102 банка — вместе с индикаторами): файл — заглушка в
    форме схемы, и это сказано словами; собранный мост — ряды и блок ЧПД с числом."""
    r = load("bridge_ras_ifrs")
    if is_stub(r):
        assert r["quarters"] == [] and r["by_quarter"] == {} and has_text(r["note"])
        assert not [p for p, v in nodes(r) if v["v"] is not None], "у заглушки нет чисел"
        return
    assert r["cor"]["v"] is None and has_text(r["cor"]["calc"])
    for k in "1234":
        assert r["by_quarter"][k]["v"] is None and "нет данных" in r["by_quarter"][k]["calc"]
    assert r["nii"]["value"]["v"] is not None and r["iea"]["value"]["v"] is None

