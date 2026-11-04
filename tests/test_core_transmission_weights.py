"""Веса книг решателя передачи ставки (М§4.5): ключ `nii.transmission.weights` — `anchor` (структура якоря) или `window`
(среднее с равным весом долей книг в процентных активах на концы четырёх кварталов по квартал якоря).

Независимая проверка правки ядра (книга ВТБ 1.1): веса окна тест считает сам — из JSON фактов, мимо функций ядра, —
и сверяет с ними веса, стационарную маржу миров, реализованную передачу и раскладку сжатия решателя; решение ядра на
весах окна сверяется с контрольной моделью (`tests/independent_model.py`, свой счёт весов); `anchor` — прежний счёт бит в
бит; отказы — нет конца квартала окна, нет книги, строка истории квартала якоря не равна остаткам якоря."""

from __future__ import annotations

import copy
import json

import pytest

from model.book import book_from_dict, load_facts
from model.book_schema import BookError, FactsError
from model.credit import bridge_from_facts
from model.nii import _Stationary, book_weights, solve_transmission, window_periods
from model.worlds import BASE_WORLD, MARKET_WORLD
from tests import independent_model as cm
from tests.support_core import real_book_or_skip

pytestmark = pytest.mark.tact

WEIGHTS = "nii.transmission.weights"


def _hand_weights(facts_dir, book, quarters):
    """Веса окна счётом теста: доли книг E_b,q / Σ книг активов_q по строкам balance.history JSON, среднее с равным весом;
    квартал якоря — balance.books."""
    bal = json.loads((facts_dir / "balance.json").read_text(encoding="utf-8"))
    books = book.get("nii.books")
    assets = [b for b, s in books.items() if s["side"] == "asset"]
    anchor = json.loads((facts_dir / "anchor.json").read_text(encoding="utf-8"))
    rows = []
    for q in quarters:
        node = bal["books"] if q == str(anchor["period"]) else bal["history"][q]["books"]
        e = {b: float(node[b]["v"]) for b in books}
        iea = sum(e[b] for b in assets)
        rows.append({b: e[b] / iea for b in books})
    return {b: sum(r[b] for r in rows) / len(rows) for b in books}


def _window(book):
    return book.with_overrides({WEIGHTS: "window"})


def _anchor(book):
    return book.with_overrides({WEIGHTS: "anchor"})


def test_window_periods_are_four_quarter_ends_through_the_anchor():
    assert window_periods("2026Q3") == ("2025Q4", "2026Q1", "2026Q2", "2026Q3")
    assert window_periods("2027Q1") == ("2026Q2", "2026Q3", "2026Q4", "2027Q1")
    assert window_periods("2026Q4", 1) == ("2026Q4",)


def test_window_weights_equal_the_hand_count_and_anchor_weights_are_the_anchor_shares():
    book, facts = real_book_or_skip()
    win = book_weights(_window(book), facts)
    assert win.mode == "window" and win.periods == ("2025Q4", "2026Q1", "2026Q2", "2026Q3")
    hand = _hand_weights(facts.root, book, win.periods)
    for b, v in hand.items():
        assert win.weights[b] == pytest.approx(v, rel=1e-15, abs=1e-16), b
    assert sum(win.weights[b] for b, s in book.get("nii.books").items() if s["side"] == "asset") == pytest.approx(1.0, abs=1e-15)
    anc = book_weights(_anchor(book), facts)
    assert anc.mode == "anchor" and anc.periods == ("2026Q3",)
    assert anc.weights == _hand_weights(facts.root, book, ("2026Q3",))
    # квартал якоря окна — те же доли, что веса якоря
    assert win.by_quarter["2026Q3"] == anc.weights
    # книга 1.0 записала веса окна во вход листа (решение Р13): пассивы / процентные активы 1,0234 против 1,0407 якоря
    liab = [b for b, s in book.get("nii.books").items() if s["side"] == "liability"]
    assert sum(win.weights[b] for b in liab) == pytest.approx(1.0234, abs=5e-5)
    assert sum(anc.weights[b] for b in liab) == pytest.approx(1.0407, abs=5e-5)


def test_stationary_and_solver_stand_on_the_named_weights():
    """Стационарная маржа, реализованная передача, сжатие и его раскладка (A, L, ω) — на весах ключа: пересчёт теста по
    формулам М§4.5 на весах окна, посчитанных тестом, равен счёту ядра."""
    book, facts = real_book_or_skip()
    wb = _window(book)
    bridge = bridge_from_facts(facts)
    tr = solve_transmission(wb, facts, bridge)
    st = _Stationary(wb, facts)
    hand = _hand_weights(facts.root, book, tr.weights_periods)
    assert tr.weights_mode == "window" and dict(tr.weights) == pytest.approx(hand, rel=1e-15)
    # Nss тестом: тот же стационар, веса — счёт теста
    st_hand = _Stationary(wb, facts)
    st_hand.w = dict(hand)
    st_hand.l_r = sum(hand[b] for b in st_hand.roles.retail)
    ref = tr.reference_world
    for w in book.get("worlds.ids"):
        assert st.nss(w, 0.0, tr.sigma0, tr.phi, ref, tr.sigma0_liab) == pytest.approx(
            st_hand.nss(w, 0.0, tr.sigma0, tr.phi, ref, tr.sigma0_liab), abs=1e-15)
        assert tr.nss[w] == pytest.approx(st_hand.nss(w, 0.0, tr.sigma0, tr.phi, ref, tr.sigma0_liab), abs=1e-15)
    dkey = st.ref_lt[MARKET_WORLD]["key"] - st.ref_lt[BASE_WORLD]["key"]
    assert (tr.nss[MARKET_WORLD] - tr.nss[BASE_WORLD]) / dkey == pytest.approx(float(book.get("nii.transmission.target")), abs=1e-12)
    level = str(book.get("nii.transmission.level_world"))
    assert bridge.to_mgmt_nim(tr.nss[level]) == pytest.approx(float(book.get("nii.nim_lt_target_mgmt")), abs=1e-12)
    books = book.get("nii.books")
    phi_a = [b for b, s in books.items() if s["side"] == "asset" and s.get("phi")]
    phi_l = [b for b, s in books.items() if s["side"] == "liability" and s.get("phi")]
    a, l_ = sum(hand[b] for b in phi_a), sum(hand[b] for b in phi_l)
    p = float(book.get("nii.phi_split"))
    assert tr.phi_assets == pytest.approx(p * tr.phi, abs=1e-15)
    assert tr.phi_liab == pytest.approx((1 - p) * tr.phi * a / l_, rel=1e-13)
    for b in phi_a:
        assert tr.phi_weights[b] == pytest.approx(hand[b] / a, rel=1e-13), b
    # масштаб ROE-эквивалента — якорь при любых весах (печать): IEA_0 / BV_0 якоря
    from model.book import anchor_facts
    af = anchor_facts(facts, books)
    iea0 = sum(af.balances[b] for b in books if books[b]["side"] == "asset")
    assert st.iea0 == iea0 and st.bv0 == af.bv
    assert solve_transmission(_anchor(book), facts, bridge).roe_factor == tr.roe_factor


def test_level_key_is_the_book_1_0_judgment_on_window_weights():
    """Ключ уровня книги 1.1 — запись суждения книги 1.0 на средних весах окна (правило keep, REANCHOR §3.5): скаляры
    пути, которые книга 1.0 решает на весах якоря (ключ 2,9229 %, цель −0,030828 — запись Р13), дают на весах окна
    стационарную маржу мира N 3,0491 % (упр.) и передачу −0,0115 (Р13 мерил её полным φ)."""
    book, facts = real_book_or_skip()
    bridge = bridge_from_facts(facts)
    old = solve_transmission(_anchor(book).with_overrides({"nii.nim_lt_target_mgmt": 0.029229,
                                                           "nii.transmission.target": -0.030828}), facts, bridge)
    st = _Stationary(_window(book), facts)
    level = str(book.get("nii.transmission.level_world"))
    ref = old.reference_world
    key = bridge.to_mgmt_nim(st.nss(level, 0.0, old.sigma0, old.phi, ref, old.sigma0_liab))
    assert key == pytest.approx(0.0304907058, abs=1e-9) and round(key, 6) == float(book.get("nii.nim_lt_target_mgmt"))
    dkey = st.ref_lt[MARKET_WORLD]["key"] - st.ref_lt[BASE_WORLD]["key"]
    flat = (st.nss(MARKET_WORLD, 0.0, old.sigma0, old.phi, ref, old.sigma0_liab)
            - st.nss(BASE_WORLD, 0.0, old.sigma0, old.phi, ref, old.sigma0_liab)) / dkey
    assert flat == pytest.approx(-0.0115, abs=1e-6)
    new = solve_transmission(book, facts, bridge)
    assert new.phi == pytest.approx(old.phi, abs=1e-6) and new.phi_assets == pytest.approx(old.phi_assets, abs=1e-6)
    # φ_L = (1 − p)·φ·A/L — на весах окна (A/L 0,8924 против 0,8987 якоря): единственное, что двигает путь
    assert new.phi_liab / old.phi_liab == pytest.approx(0.99303, abs=5e-5)


def test_anchor_mode_is_the_previous_count_bit_for_bit():
    """`anchor` — прежний счёт: доли якоря E_b,0 / IEA_0, решение то же, что у книги без ключа."""
    book, facts = real_book_or_skip()
    bridge = bridge_from_facts(facts)
    a = solve_transmission(_anchor(book), facts, bridge)
    data = copy.deepcopy(dict(book.source or book.data))
    data["nii"]["transmission"]["weights"] = "anchor"
    st = _Stationary(_anchor(book), facts)
    from model.book import anchor_facts
    af = anchor_facts(facts, book.get("nii.books"))
    iea = sum(af.balances[b] for b in st.roles.assets)
    assert st.w == {b: af.balances[b] / iea for b in st.roles.names}
    assert a.weights_mode == "anchor" and a.weights_periods == ("2026Q3",)
    b = solve_transmission(book_from_dict(data, facts=facts), facts, bridge)
    assert (a.sigma0, a.sigma0_liab, a.phi, a.phi_liab, a.t_real) == (b.sigma0, b.sigma0_liab, b.phi, b.phi_liab, b.t_real)


def test_core_and_control_model_solve_the_window_alike():
    """Решение ядра на весах окна против контрольной модели (свой счёт весов из фактов и свой решатель)."""
    book, facts = real_book_or_skip()
    wb = _window(book)
    tr = solve_transmission(wb, facts, bridge_from_facts(facts))
    B = cm.c_book_machine()
    B["nii"]["transmission"]["weights"] = "window"
    F = cm.c_facts_bundle()
    A = cm.c_anchor_state(B, F)
    Bk, _ = cm.c_resolve_anchor_keys(B, A)
    ctl = cm.c_transmission_ctl(Bk, A)
    assert ctl["weights_quarters"] == list(tr.weights_periods)
    for b, v in tr.weights.items():
        assert ctl["weights"][b] == pytest.approx(v, rel=1e-14), b
    for name, got in (("sigma0", tr.sigma0), ("sigma0_liab", tr.sigma0_liab), ("phi", tr.phi), ("phi_assets", tr.phi_assets),
                      ("phi_liab", tr.phi_liab), ("t_real", tr.t_real), ("target_eng", tr.target_eng)):
        assert ctl[name] == pytest.approx(got, rel=1e-9, abs=1e-12), name
    for w, v in tr.nss.items():
        assert ctl["nss"][w] == pytest.approx(v, abs=1e-12), w
    for b, v in tr.phi_weights.items():
        assert ctl["phi_weights"][b] == pytest.approx(v, rel=1e-12), b
    for w, v in tr.loan_margin.items():
        assert ctl["loan_margin"][w] == pytest.approx(v, abs=1e-12), w


def test_window_refuses_without_quarter_ends_and_with_a_wrong_anchor_row(tmp_path):
    book, facts = real_book_or_skip()
    src = facts.root
    for case in ("missing_quarter", "missing_book", "anchor_row"):
        d = tmp_path / case
        d.mkdir()
        for f in src.glob("*.json"):
            (d / f.name).write_bytes(f.read_bytes())
        bal = json.loads((d / "balance.json").read_text(encoding="utf-8"))
        if case == "missing_quarter":
            del bal["history"]["2026Q1"]["books"]
        elif case == "missing_book":
            del bal["history"]["2025Q4"]["books"]["wholesale"]
        else:
            bal["history"]["2026Q3"]["books"]["corp_loans"]["v"] += 1.0
        (d / "balance.json").write_text(json.dumps(bal, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        f2 = load_facts(d)
        with pytest.raises(FactsError, match="balance.history"):
            book_weights(_window(book), f2)
        book_weights(_anchor(book), f2)                         # веса якоря строк истории не читают


def test_schema_knows_two_weights():
    book, _ = real_book_or_skip()
    with pytest.raises(BookError):
        book.with_overrides({WEIGHTS: "mean"})
