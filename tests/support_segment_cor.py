# -*- coding: utf-8 -*-
"""Сегментная CoR и перенос якоря (М§4.6, §15.2 п. 3; docs/REANCHOR.md §3.3): проверки для тестов и мутационного
набора.

Общая CoR клетки равна пути режима на **структуре нормировки** сегментной CoR: без ключа книги
`credit.segment_relative.corporate_share_ref` это доли сегментов в кредитах АС якоря (правило образца), с ключом —
доля юрлиц ключа и остаток до единицы у физлиц. Перенос якоря пишет в книгу-кандидата долю прежнего якоря: клетка,
перезаякоренная на своём пути, сохраняет резервы каждого квартала, а с ними — стоимость.

Каждая проверка — закрытая формула из книги, фактов и рядов клетки, независимая от кода ядра: резервы клетки мира N
(κ-добавка в базовом мире — ноль; наблюдений A-P2u у фикстуры нет — отклонения δ ≡ 0) в квартале q —
`CoR_r,q × Σ_b rel_σ(b) × Ē^АС_b,q / Σ_σ w_σ rel_σ × d_q/365`, где CoR_r,q — путь режима книги через аддитивный мост
фактов, Ē^АС_b,q — средний остаток кредитной книги без кредитов по СС, w — структура нормировки; доли якоря — по
остаткам кредитных книг клетки на якоре (q = 0) за вычетом кредитов по СС. Фикстура — форма образца
`tests/fixtures/core` с сегментной схемой rel = {юрлица 0,7; физлица 1,8} (как у книги ВТБ), подставленной тестом.
Те же функции зовут `tests/test_reanchor_mechanics.py` и мутационный набор `tests/mutations.py`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from model.book import book_from_dict
from model.book_schema import BookError, read_paths
from model.grid import run_grid
from model.paths import Trajectory
from model.timeline import parse_period
from tests.support_core import book_with, fixture_facts

KEY = "credit.segment_relative.corporate_share_ref"
REL = {"corporate": 0.7, "retail": 1.8}
SEG = {"enabled": True, **REL}
SHARE = 0.4                                  # доля юрлиц ключа: далеко от доли якоря фикстуры (≈ 0,58)
CELLS = (("N", "norm", "schedule"), ("N", "crisis", "strict"))   # мир N — κ-добавки нет; режим с шоком и без
TOL = 1e-12                                  # относительный допуск тождества резервов


def close(a: float, b: float, rel: float = TOL, abs_: float = 1e-12) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def seg_dict(share: Any = None, *, enabled: bool = True) -> dict:
    """Словарь книги фикстуры с сегментной схемой; `share` — ключ структуры нормировки (None — без ключа)."""
    spec = {**SEG, "enabled": enabled}
    if share is not None:
        spec["corporate_share_ref"] = share
    return book_with({"credit.segment_relative": spec})


@lru_cache(maxsize=None)
def seg_book(share: float | None = None):
    return book_from_dict(seg_dict(share), facts=fixture_facts())


@lru_cache(maxsize=None)
def seg_run(share: float | None = None):
    return run_grid(seg_book(share), fixture_facts())


def _loan_books(books: Mapping[str, Any]) -> dict[str, str]:
    """Кредитная книга → её сегмент (`cor_segment`)."""
    return {b: str(spec["cor_segment"]) for b, spec in books.items() if spec.get("cor_segment")}


def _fv_book(books: Mapping[str, Any]) -> str | None:
    """Книга с долей кредитов по СС (ключ `fv_share`)."""
    return next((b for b, spec in books.items() if spec.get("fv_share") is not None), None)


def anchor_share(cell: Any, books: Mapping[str, Any]) -> float:
    """Доля юрлиц в кредитах АС якоря — по остаткам кредитных книг клетки на якоре (q = 0) без кредитов по СС."""
    fv = _fv_book(books)
    w = {"corporate": 0.0, "retail": 0.0}
    for b, seg in _loan_books(books).items():
        w[seg] += float(cell.books[b]["balance"][0]) - (float(cell.quarters["loans_fv"][0]) if b == fv else 0.0)
    return w["corporate"] / (w["corporate"] + w["retail"])


def expected_llp(book: Any, run: Any, key: tuple[str, str, str], share: float) -> list[float]:
    """Резервы клетки мира N по кварталам q = 1…Q на структуре нормировки с долей юрлиц `share` (М§4.6)."""
    facts = run.ctx.facts
    assert key[0] == "N" and str(facts.plain("bridge_mgmt_ifrs", "cor.method")) == "additive"
    assert book.get("regimes.cor_basis") == "mgmt" and not book.get("joint.regime_update.observations")
    bridge = float(facts.need("bridge_mgmt_ifrs", "cor.value"))
    cell, tl, books = run.cell(*key), run.ctx.timeline, book.get("nii.books")
    path = Trajectory(book.get(f"regimes.{key[1]}.cor"))
    norm = share * REL["corporate"] + (1.0 - share) * REL["retail"]
    fv = _fv_book(books)
    out = []
    for q in range(1, tl.Q + 1):
        cor = path.value(*parse_period(tl.period(q))) + bridge
        weighted = sum(REL[seg] * (float(cell.books[b]["avg"][q])
                                   - (float(cell.quarters["loans_fv_avg"][q]) if b == fv else 0.0))
                       for b, seg in _loan_books(books).items())
        out.append(cor * weighted / norm * tl.d(q) / 365)
    return out


def _same_llp(book: Any, run: Any, share: float) -> None:
    for key in CELLS:
        got = [float(x) for x in run.cell(*key).quarters["llp"][1:]]
        want = expected_llp(book, run, key, share)
        bad = [(q, g, w) for q, (g, w) in enumerate(zip(got, want), start=1) if not close(g, w)]
        assert not bad, (key, share, bad[:3])


def check_llp_on_the_structure_of_the_key() -> None:
    """С ключом: резервы клетки — путь × Σ rel × Ē^АС / (s × rel_юл + (1 − s) × rel_фл) × d/365 (М§4.6), в том числе
    на границе s = 1; доля ключа далеко от доли якоря — ключ меняет резервы."""
    for share in (SHARE, 1.0):
        _same_llp(seg_book(share), seg_run(share), share)
    a, b = seg_run(SHARE).cell(*CELLS[0]), seg_run(None).cell(*CELLS[0])
    assert abs(a.quarters["llp"][1] / b.quarters["llp"][1] - 1) > 1e-3


def check_llp_without_the_key_is_on_the_anchor() -> None:
    """Без ключа — правило образца: структура нормировки — доли якоря (по остаткам клетки на якоре)."""
    book, run = seg_book(None), seg_run(None)
    share = anchor_share(run.cell(*CELLS[0]), book.get("nii.books"))
    assert 0.0 < share < 1.0 and abs(share - SHARE) > 0.1
    _same_llp(book, run, share)


def check_schema_of_the_key() -> None:
    """Ключ — доля в [0; 1] (0 и 1 допустимы), число; `null` при включённой схеме, слово `anchor`, строка, булево —
    отказ с путём ключа. При выключенной схеме ключ не читается (может быть `null`), при включённой — читается."""
    def refused(share: Any, enabled: bool = True) -> str | None:
        try:
            book_from_dict(seg_dict(share, enabled=enabled), facts=fixture_facts())
        except BookError as exc:
            return str(exc)
        return None

    for bad in (1.2, -0.1, "anchor", "0.5", True):
        text = refused(bad)
        assert text is not None and KEY in text, (bad, text)
    data = seg_dict(0.5)
    data["credit"]["segment_relative"]["corporate_share_ref"] = None
    try:
        book_from_dict(data, facts=fixture_facts())
        raise AssertionError("null у ключа при включённой схеме принят")
    except BookError as exc:
        assert KEY in str(exc), str(exc)
    for ok in (0.0, 1.0, 0.5):
        assert refused(ok) is None, ok
    data = seg_dict(0.5, enabled=False)
    data["credit"]["segment_relative"].update(corporate=None, retail=None, corporate_share_ref=None)
    try:
        book_from_dict(data, facts=fixture_facts())
    except BookError as exc:
        raise AssertionError(f"null у ключа при выключенной схеме отклонён: {exc}") from exc
    assert KEY not in read_paths(data)
    assert KEY in read_paths(seg_dict(0.5))
