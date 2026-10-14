"""Документы эмитента этой копии: перечень страницы результатов, вид и период по заголовку, месячная книга XLSX.

Настройки — репозитория (`data/indicators/sources.yaml`); книга и факты — заглушка эмитента
(`tests/fixtures/ind/issuer/`). Страница и книги собираются кодом теста в формате источника с сочинёнными
числами (`tests/support_ind_book.py`): файлов эмитента в репозитории нет.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from indicators import config, http, issuer_docs, periods, release_watch, xlsx_book
from indicators.sources import DEGRADED, FAILED, OK, Context
from indicators.store import Store
from tests.support_ind import FakeGetter, use_issuer
from tests.support_ind_book import (FILES, PAGE_URL, excel_serial, make_xlsx, monthly_book, results_page,
                                    synthetic_numbers)

pytestmark = pytest.mark.tact  # быстрые тесты такта

MONTHLY = "ifrs_monthly"
TODAY = date(2026, 9, 29)
T1 = "2026-09-29T07:05:00+00:00"
AUG, JUL = "rus-group-ifrs-as-of-31-august-2026.xlsx", "rus-group-ifrs-as-of-31-jule-2026.xlsx"
ENTRIES = [
    {"file": AUG, "title": "Финансовые результаты по МСФО за 8М 2026 года", "day": "2026-09-29"},
    {"file": JUL, "title": "Финансовые результаты по МСФО за 7М 2026 года", "day": "2026-08-28"},
    {"file": "rus-group-ifrs-as-of-30-june-2026.pdf", "title": "Финансовая отчетность по МСФО за 6М 2026 года",
     "day": "2026-07-28", "size": "2.18 Mб"},
    {"file": "presentation_ifrs_0626_rus.pdf", "title": "Презентация по результатам за 6М 2026 года",
     "day": "2026-07-28", "size": "2.49 Mб"},
    {"file": "financial_data_supplement_0626_rus.xlsx", "title": "Приложение к презентации", "day": "2026-07-28"},
    {"file": "call_transcript_0626_rus.pdf", "title": "Расшифровка звонка с аналитиками", "day": "2026-08-03"},
]


def _cfg() -> dict:
    return config.sources()["issuer_docs"]


def _ctx(store, getter, today=TODAY) -> Context:
    return Context(store=store, today=today, company=config.company(), cfg=config.sources(), getter=getter)


def _getter(entries=ENTRIES, books=None, moment=T1, extra=None) -> FakeGetter:
    # страница отдаётся по точному адресу: он входит в адрес каждого файла, подмена по части адреса его перехватила бы
    answers: dict = {name: body for name, body in (books or {}).items()}
    answers.update(extra or {})
    page = results_page(entries)

    class Getter(FakeGetter):
        def body_for(self, url, data, headers):
            if url.rstrip("/") == PAGE_URL.rstrip("/"):
                return page
            return super().body_for(url, data, headers)

    return Getter(answers, moment=moment)


def _started(store: Store) -> None:
    """Состояние не первого запуска: в индексе уже есть запись (история не скачивается только на первом)."""
    store.write_state(issuer_docs.INDEX_FILE, {"https://www.vtb.ru/media-files/old.pdf": {
        "first_seen": None, "note": issuer_docs.NOTE_BEFORE_START, "kind": None, "period": None}})


# ------------------------------------------------------------------ перечень страницы

def test_listing_is_read_by_the_address_and_the_text_of_the_link():
    rows = issuer_docs.press_rows(results_page(ENTRIES).decode("utf-8"), _cfg())
    assert [r["url"] for r in rows] == [f"https://www.vtb.ru{FILES}{e['file']}" for e in ENTRIES]
    assert rows[0] == {"date": "2026-09-29", "title": "Финансовые результаты по МСФО за 8М 2026 года",
                       "url": f"https://www.vtb.ru{FILES}{AUG}"}
    assert [r["date"] for r in rows] == [e["day"] for e in ENTRIES]            # день — из подписи «размер, дата»
    assert all("Пресс-релиз" not in r["title"] for r in rows)                   # ссылка на новость — не документ
    # ссылка без подписи остаётся записью без дня; чужой адрес и адрес с параметрами в перечень не идут
    page = ('<a href="/media-files/a/b.pdf"><div>Документ без подписи</div></a>'
            '<a href="/media-files/a/c.pdf?x=1">с параметром</a><a href="https://example.org/media-files/d.pdf">чужой</a>'
            '<a href="/ir/other/">раздел</a>')
    assert issuer_docs.press_rows(page, _cfg()) == [
        {"date": None, "title": "Документ без подписи", "url": "https://www.vtb.ru/media-files/a/b.pdf"}]
    # без настройки вёрстки — прежний разбор блоков-панелей: в этой странице их нет
    assert issuer_docs.press_rows(results_page(ENTRIES).decode("utf-8"), {"press_page": PAGE_URL}) == []


@pytest.mark.parametrize("title,kind,period", [
    ("Финансовые результаты по МСФО за 8М 2026 года", MONTHLY, "2026M08"),
    ("Финансовые результаты по МСФО за 2М 2026 года", MONTHLY, "2026M02"),
    ("Финансовая информация по МСФО за 11М 2024 года", MONTHLY, "2024M11"),
    ("Финансовая информация по МСФО за 10М 2023 года", MONTHLY, "2023M10"),
    ("Финансовая отчетность по МСФО за 6М 2026 года", "ifrs_statements", "2026Q2"),
    ("Финансовая информация по МСФО за 9М 2023 года", "ifrs_statements", "2023Q3"),
    ("Финансовая отчетность по МСФО за 3М 2025 года", "ifrs_statements", "2025Q1"),
    ("Финансовая отчетность по МСФО за 2025 год", "ifrs_statements", "2025Q4"),
    ("Финансовая информация по МСФО за 2022 год", "ifrs_statements", "2022Q4"),
    ("Презентация по результатам за 6М 2026 года", "ifrs_presentation", "2026Q2"),
    ("Презентация по результатам 9М 2024 года", "ifrs_presentation", "2024Q3"),
    ("Презентация по результатам 2023 года", "ifrs_presentation", "2023Q4"),
    ("Приложение к презентации", "databook", None),
    ("Расшифровка звонка с аналитиками", "call_transcript", None),
    ("Положение об организации обработки данных", None, None),
])
def test_kind_and_period_come_from_the_title(title, kind, period):
    """Месячная книга и отчётность квартала носят один заголовок: различает их число месяцев."""
    assert issuer_docs.classify(title, _cfg(), monthly_kind=MONTHLY) == {"kind": kind, "period": period}


def test_a_document_without_a_period_in_the_title_takes_the_quarter_before_its_day():
    assert issuer_docs.quarter_before("2026-07-28") == "2026Q2" and issuer_docs.quarter_before("2026-03-03") == "2025Q4"
    assert issuer_docs.quarter_before("2026-10-01") == "2026Q3" and issuer_docs.quarter_before("не день") is None


# ------------------------------------------------------------------ чтение XLSX

def test_xlsx_is_read_without_libraries():
    body = make_xlsx([("Первый", [["Метка", 1.5, None, "текст"], [None, 2]]), ("Второй лист", [[3.0]])], start_row=4)
    sheets = xlsx_book.read(body)
    assert [name for name, _ in sheets] == ["Первый", "Второй лист"]
    assert sheets[0][1] == {(4, 0): "Метка", (4, 1): 1.5, (4, 3): "текст", (5, 1): 2.0} and sheets[1][1] == {(4, 0): 3.0}
    assert xlsx_book.rows_of(sheets[0][1]) == [(4, {0: "Метка", 1: 1.5, 3: "текст"}), (5, {1: 2.0})]
    assert xlsx_book.is_xlsx(body) and not xlsx_book.is_xlsx(b"%PDF-1.7 ...") and not xlsx_book.is_xlsx(b"PK\x03\x04???")
    with pytest.raises(xlsx_book.BookError, match="не архив"):
        xlsx_book.read(b"%PDF-1.7")


def test_a_book_with_a_document_type_declaration_is_refused():
    """Часть с объявлением типа документа или сущностей не разбирается: файл — чужой ввод."""
    good = make_xlsx([("Лист", [["a", 1.0]])])
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(buf, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "xl/sharedStrings.xml":
                data = data.replace(b"?>", b'?><!DOCTYPE sst [<!ENTITY a "aaaa">]>', 1)
            dst.writestr(name, data)
    with pytest.raises(xlsx_book.BookError, match="объявляет тип документа"):
        xlsx_book.read(buf.getvalue())


def test_cell_values_and_headers():
    assert xlsx_book.number(" 2,6% ") == pytest.approx(0.026) and xlsx_book.number("-12,5") == -12.5
    assert xlsx_book.number("130 б.п.") is None and xlsx_book.number(True) is None and xlsx_book.number(3) == 3.0
    assert [xlsx_book.month_number(w) for w in ("август", "Авг", "апр.", "мая", "май", "итого")] == [8, 8, 4, 5, 5, None]
    assert xlsx_book.excel_day(excel_serial(date(2026, 8, 31))) == date(2026, 8, 31)
    assert xlsx_book.excel_day("31.08.2026") == date(2026, 8, 31) and xlsx_book.excel_day(0.105) is None
    assert xlsx_book.stock_month(date(2026, 9, 1)) == "2026M08" == xlsx_book.stock_month(date(2026, 8, 31))
    assert xlsx_book.clean("  Создание резервов\n  и прочие   резервы ") == "создание резервов и прочие резервы"


# ------------------------------------------------------------------ месячная книга

def test_monthly_book_gives_the_month_the_year_to_date_and_the_stocks():
    spec = _cfg()["monthly_book"]
    want = synthetic_numbers("2026M08")
    got = xlsx_book.parse_monthly(monthly_book("2026M08"), spec)
    assert got["period"] == "2026M08" and got["months_column"]
    assert set(got["numbers"]) <= set(config.sources()["monthly"]["metrics"])
    for metric in ("np_m", "np_ytd", "nii_m", "nii_ytd", "fee_m", "prov_m", "opex_ytd", "pretax_m", "tax_ytd",
                   "opinc_m", "other_ytd", "nim_m", "nim_ytd", "cor_m", "cor_ytd", "cir_m", "roe_ytd", "loans_gross",
                   "loans_ul", "loans_fl", "funds_total", "funds_ul", "funds_fl", "assets", "equity", "npl90",
                   "n20_0", "n20_1", "n20_2"):
        assert got["numbers"][metric] == pytest.approx(want[metric]), metric
    assert got["numbers"]["prov_m"] < 0 and got["numbers"]["opex_m"] < 0        # знак — как в книге
    assert 0 < got["numbers"]["nim_m"] < 0.1 and 0 < got["numbers"]["n20_0"] < 0.3   # доли, не проценты
    # столбцы сравнения: тот же месяц год назад, конец прошлого месяца, конец прошлого года
    assert set(got["comparative"]) == {"2025M08", "2026M07", "2025M12"}
    assert got["comparative"]["2025M08"]["np_m"] == pytest.approx(synthetic_numbers("2025M08")["np_m"])
    assert got["comparative"]["2026M07"]["loans_gross"] == pytest.approx(synthetic_numbers("2026M07")["loans_gross"])
    assert got["comparative"]["2026M07"]["n20_0"] == pytest.approx(synthetic_numbers("2026M07")["n20_0"])
    assert "np_m" not in got["comparative"]["2026M07"] and "loans_gross" not in got["comparative"]["2025M08"]


def test_the_book_for_two_months_carries_only_the_year_to_date():
    got = xlsx_book.parse_monthly(monthly_book("2026M02"), _cfg()["monthly_book"])
    assert got["period"] == "2026M02" and not got["months_column"]
    assert got["numbers"]["np_ytd"] == pytest.approx(synthetic_numbers("2026M02")["np_ytd"])
    assert not [k for k in got["numbers"] if k.endswith("_m")]                  # январь и февраль — одной суммой
    assert got["numbers"]["nim_ytd"] and got["numbers"]["loans_gross"] and "2025M12" in got["comparative"]


def test_the_first_format_of_the_book_is_read_too():
    """Ранний вид книги: «апрель'2023» и «4 мес'2023», без столбцов сравнения и без нормативов."""
    got = xlsx_book.parse_monthly(monthly_book("2023M04", first_format=True), _cfg()["monthly_book"])
    want = synthetic_numbers("2023M04")
    assert got["period"] == "2023M04" and got["comparative"] == {}
    assert (got["numbers"]["np_m"], got["numbers"]["np_ytd"]) == (pytest.approx(want["np_m"]), pytest.approx(want["np_ytd"]))
    assert "n20_0" not in got["numbers"] and got["numbers"]["npl90"] == pytest.approx(0.035)


def test_a_file_that_is_not_the_monthly_book_is_named():
    spec = _cfg()["monthly_book"]
    with pytest.raises(xlsx_book.BookError, match="нет листа потоков"):
        xlsx_book.parse_monthly(make_xlsx([("Сегменты", [["x", 1.0]])]), spec)
    with pytest.raises(xlsx_book.BookError, match="нарастающего итога"):
        xlsx_book.parse_monthly(make_xlsx([("Показатели P&L", [["Чистая прибыль", 1.0]])]), spec)
    cfg = dict(_cfg())
    out = issuer_docs.analyse(make_xlsx([("Сегменты", [["x", 1.0]])]), MONTHLY, cfg, monthly_kind=MONTHLY)
    assert out["status"] == "needs_manual" and "книга не разобрана" in out["detail"] and out["numbers"] == {}
    # книга другого вида (приложение к презентации) — запись без чисел
    assert issuer_docs.analyse(monthly_book("2026M08"), "databook", cfg, monthly_kind=MONTHLY) == {
        "status": "ok", "numbers": {}, "method": "text"}


# ------------------------------------------------------------------ сбор и дозор

def test_collect_takes_the_book_from_the_listing_and_the_watch_writes_the_series(monkeypatch, tmp_path):
    use_issuer(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    _started(store)
    pinned = []
    monkeypatch.setattr(http, "pin_trusted_root", lambda hosts: pinned.append(list(hosts)))
    statements = b"%PDF-1.7 synthetic statements"
    getter = _getter(books={AUG: monthly_book("2026M08"), JUL: monthly_book("2026M07"),
                            "june-2026.pdf": statements, "supplement_0626": make_xlsx([("Лист", [["x", 1.0]])])})
    ctx = _ctx(store, getter)
    res = issuer_docs.collect(ctx)
    assert res.status == OK, res.reasons
    assert pinned == [["www.vtb.ru"]]                                           # корень — хосту эмитента из настройки
    index = store.read_state(issuer_docs.INDEX_FILE)
    entry = index[f"https://www.vtb.ru{FILES}{AUG}"]
    assert (entry["kind"], entry["period"], entry["listed"], entry["first_seen"]) == (MONTHLY, "2026M08", "2026-09-29", T1)
    assert len(entry["versions"]) == 1 and len(entry["versions"][0]["sha256"]) == 64
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    by_kind: dict[str, list[dict]] = {}
    for cand in cands.values():
        by_kind.setdefault(cand["kind"], []).append(cand)
    book = next(c for c in by_kind[MONTHLY] if c["month"] == "2026M08")
    assert book["status"] == "ok" and book["method"] == "text" and book["book_period"] == "2026M08"
    assert book["numbers"]["np_m"] == pytest.approx(synthetic_numbers("2026M08")["np_m"])
    assert {c["month"] for c in by_kind[MONTHLY]} == {"2026M08", "2026M07"}
    # отчётность и приложение — в архив без разбора; презентация и расшифровка — запись «появился»
    assert [(c["period"], c["method"], c["status"]) for c in by_kind["ifrs_statements"]] == [("2026Q2", "archive", "ok")]
    assert [(c["period"], c["method"]) for c in by_kind["databook"]] == [("2026Q2", "archive")]   # квартал до дня записи
    assert [(c["period"], c["status"]) for c in by_kind["ifrs_presentation"]] == [("2026Q2", issuer_docs.LISTED)]
    assert [(c["period"], c["status"]) for c in by_kind["call_transcript"]] == [("2026Q2", issuer_docs.LISTED)]
    assert not any("/about/press/news/" in call["url"] for call in getter.calls)   # страницы новостей не запрашиваются
    assert store.raw_files("issuer_docs")                                         # файлы легли в защищённый архив
    # выпуск будят документы МСФО квартала; месячная книга — через дозор
    wake = issuer_docs.wake_candidates(cands, MONTHLY)
    assert wake and all(cands[k]["kind"].startswith("ifrs") and cands[k]["kind"] != MONTHLY for k in wake)
    assert {cands[k]["kind"] for k in issuer_docs.wake_candidates(cands)} >= {MONTHLY}      # без имени вида — прежнее правило

    rw = release_watch.run(ctx)
    assert rw.status == OK, rw.reasons
    months = {m["month"]: m for m in rw.data["months"]}
    assert months["2026M08"]["month_accepted"] and months["2026M07"]["month_accepted"]
    spec = release_watch.monthly(config.sources())
    assert spec.wakes and spec.basis == "ifrs" and not spec.form102 and spec.backfill
    profit = store.load("ifrs.release.np_m")
    assert profit.value_as_of("2026M08") == pytest.approx(synthetic_numbers("2026M08")["np_m"])
    assert profit.meta["basis"] == "ifrs" and profit.meta["unit"] == "RUB bn"
    assert store.load("ifrs.release.nim_m").meta["unit"] == "share" == store.load("ifrs.release.n20_0").meta["unit"]
    point = profit.point_as_of("2026M08")
    assert point.source == "release:pdf" and point.status == "ok"                 # документ эмитента принят сам
    # месяц без своего релиза (июнь): нарастающий итог — «итог − месяц» июльской книги; остатки — её столбец сравнения
    july = synthetic_numbers("2026M07")
    ytd = store.load("ifrs.release.np_ytd")
    assert ytd.value_as_of("2026M06") == pytest.approx(july["np_ytd"] - july["np_m"])
    assert ytd.point_as_of("2026M06").note == release_watch.DERIVED_NOTE
    assert store.load("ifrs.release.loans_gross").value_as_of("2026M06") == pytest.approx(
        synthetic_numbers("2026M06")["loans_gross"])
    assert store.load("ifrs.release.loans_gross").point_as_of("2026M06").source == "release:comparative"
    assert profit.value_as_of("2026M06") is None                                  # итога мая в рядах нет: месяц не вывести
    # повторный такт ничего не качает и не пишет заново
    calls = len(getter.calls)
    assert issuer_docs.collect(ctx).status == OK and len(getter.calls) == calls + 1          # только страница перечня
    again = release_watch.run(ctx)
    assert all(not m["new"] and not m["filled"] for m in again.data["months"])


def test_an_entry_of_the_listing_with_an_unknown_title_is_named_not_skipped(monkeypatch, tmp_path):
    """Перечень — страница одних документов результатов: запись, чей заголовок не подошёл ни под один вид (эмитент
    сменил формулу заголовка), называется причиной деградации каждый такт, пока запись стоит в перечне, — файл не
    качается, но и молча не пропадает. Запись старше окна первого запуска и запись, ушедшая из перечня, молчат."""
    use_issuer(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    odd = "ifrs-9m-2026.xlsx"
    listed = [{"file": odd, "title": "Итоги работы группы за 9 месяцев 2026 года", "day": "2026-10-12"},
              {"file": AUG, "title": "Финансовые результаты по МСФО за 8М 2026 года", "day": "2026-09-29"},
              {"file": "old-note.pdf", "title": "Сообщение о прошлом", "day": "2025-03-03"}]
    getter = _getter(entries=listed, books={AUG: monthly_book("2026M08"), odd: monthly_book("2026M08")})
    day = date(2026, 10, 14)
    ctx = _ctx(store, getter, today=day)
    res = issuer_docs.collect(ctx)
    assert res.status == DEGRADED and not res.retry
    assert res.reasons == ["запись перечня не распознана: «Итоги работы группы за 9 месяцев 2026 года» от 2026-10-12 — "
                           "заголовок не подошёл ни под один вид документа (issuer_docs.title_kinds)"]
    index = store.read_state(issuer_docs.INDEX_FILE)
    assert index[f"https://www.vtb.ru{FILES}{odd}"]["kind"] is None
    assert index[f"https://www.vtb.ru{FILES}old-note.pdf"]["note"] == issuer_docs.NOTE_BEFORE_START     # история молчит
    assert not any(c["url"].endswith(odd) for c in getter.calls), "файл без вида не качается"
    assert {c["month"] for c in store.read_state(issuer_docs.CANDIDATES_FILE).values()} == {"2026M08"}
    assert issuer_docs.collect(ctx).reasons == res.reasons                 # запись в перечне — причина стоит
    # заголовок стал читаться (настройка видов исправлена) либо запись ушла из перечня — причина уходит
    gone = _getter(entries=listed[1:], books={AUG: monthly_book("2026M08")})
    assert issuer_docs.collect(_ctx(store, gone, today=day)).status == OK


def test_the_first_run_downloads_only_fresh_documents(monkeypatch, tmp_path):
    use_issuer(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    getter = _getter(books={AUG: monthly_book("2026M08"), JUL: monthly_book("2026M07")})
    res = issuer_docs.collect(_ctx(store, getter))
    assert res.status == OK, res.reasons
    index = store.read_state(issuer_docs.INDEX_FILE)
    old = index[f"https://www.vtb.ru{FILES}rus-group-ifrs-as-of-30-june-2026.pdf"]
    assert old["note"] == issuer_docs.NOTE_BEFORE_START and old["first_seen"] is None      # старше окна первого запуска
    fetched = sorted(c["url"].rsplit("/", 1)[-1] for c in getter.calls if "/media-files/" in c["url"])
    assert fetched == sorted([AUG, JUL])            # книги двух последних месяцев; отчётность июля — уже история


def test_a_book_of_another_period_than_its_title_is_not_taken(monkeypatch, tmp_path):
    """Имена файлов неустойчивы, файлы перезаливают: числа книги не того периода в ряд месяца заголовка не идут."""
    use_issuer(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    _started(store)
    ctx = _ctx(store, _getter(entries=ENTRIES[:1], books={AUG: monthly_book("2026M07")}))
    res = issuer_docs.collect(ctx)
    assert res.status == DEGRADED and "период книги 2026M07 не совпал с периодом заголовка 2026M08" in " ".join(res.reasons)
    assert not res.retry                                                          # повтор сбора число не добудет
    cand = next(iter(store.read_state(issuer_docs.CANDIDATES_FILE).values()))
    assert cand["status"] == "needs_manual" and cand["numbers"] == {}
    release_watch.run(ctx)
    assert store.load("ifrs.release.np_ytd") is None


def test_a_reuploaded_book_is_a_new_vintage_and_a_changed_number_is_a_mismatch(monkeypatch, tmp_path):
    use_issuer(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    _started(store)
    first = _ctx(store, _getter(entries=ENTRIES[:1], books={AUG: monthly_book("2026M08")}))
    assert issuer_docs.collect(first).status == OK and release_watch.run(first).status == OK
    held = store.load("ifrs.release.np_m").value_as_of("2026M08")
    later = date(2026, 10, 7)
    second = _ctx(store, _getter(entries=ENTRIES[:1], books={AUG: monthly_book("2026M08", seed=3.0)},
                                 moment="2026-10-07T07:00:00+00:00"), today=later)
    assert issuer_docs.collect(second).status == OK
    entry = store.read_state(issuer_docs.INDEX_FILE)[f"https://www.vtb.ru{FILES}{AUG}"]
    assert len(entry["versions"]) == 2 and entry["first_seen"] == T1              # момент первого появления не меняется
    rw = release_watch.run(second)
    assert rw.status == DEGRADED and "источники разошлись" in " ".join(rw.reasons)
    assert store.load("ifrs.release.np_m").value_as_of("2026M08") == held         # принятое автомат не переписывает


def test_listing_failure_is_a_failed_irrecoverable_source(monkeypatch, tmp_path):
    use_issuer(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    dead = FakeGetter({"/ir/statements/results/": http.FetchError(PAGE_URL, None, "сеть")})
    res = issuer_docs.collect(_ctx(store, dead))
    assert res.status == FAILED and res.retry and "страница результатов эмитента" in res.detail
    empty = FakeGetter({"/ir/statements/results/": b"<html><body>no links here</body></html>"})
    res = issuer_docs.collect(_ctx(store, empty))
    assert res.status == FAILED and "страница результатов эмитента: в ответе нет ни одной записи списка" in res.reasons


def test_a_document_is_taken_only_from_the_hosts_of_the_setting(monkeypatch, tmp_path):
    use_issuer(monkeypatch, tmp_path)
    cfg = issuer_docs._settings(_ctx(Store(tmp_path / "state"), FakeGetter()))
    assert cfg["_hosts"] == ["www.vtb.ru"] and cfg["_monthly_kind"] == MONTHLY
    with pytest.raises(http.FetchError, match="не на хосте эмитента"):
        issuer_docs._fetch(_ctx(Store(tmp_path / "state"), FakeGetter()), "https://example.org/media-files/a.xlsx", cfg,
                           name="a.xlsx")


def test_periods_of_the_books_cover_two_to_eleven_months():
    """Книги выходят за 2, 4, 5, 7, 8, 10 и 11 месяцев: период — месяц с этим номером."""
    spec = _cfg()["monthly_book"]
    for m in (2, 4, 5, 7, 8, 10, 11):
        period = periods.month(2025, m)
        assert xlsx_book.parse_monthly(monthly_book(period), spec)["period"] == period
        title = f"Финансовые результаты по МСФО за {m}М 2025 года"
        assert issuer_docs.classify(title, _cfg(), monthly_kind=MONTHLY) == {"kind": MONTHLY, "period": period}
