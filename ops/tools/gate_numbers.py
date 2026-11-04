# -*- coding: utf-8 -*-
"""Числа объяснений гейтов книги ВТБ, которых нет полем в таблицах: составы клеток гейтов и их величины на сетке книги
(тот же счёт, что у гейтов ядра: `model.checks`, `model.grid.run_grid`).

    python -B ops/tools/gate_numbers.py [--out data/assumptions/gate_numbers.json]

Слова объяснений — шаблон `data/assumptions/gate_explanations.tpl` (пишет ведущий); файл объяснений из шаблона пишет
команда приёма миров (`ops/tools/adopt_worlds.py`, шаг `gate-texts`), числа — метками из этого выхода, таблиц книги
(`results.json`) и машинной книги. Ядро (`model/`) не трогается: функции ядра на книге дерева. Вероятности клеток —
слой «Свой макро-взгляд».
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "assumptions" / "gate_numbers.json"


def span(xs) -> list[float]:
    xs = [x for x in xs if x is not None]
    return [min(xs), max(xs)] if xs else []


def numbers() -> dict:
    os.environ.setdefault("BANK_WORKERS", "2")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from model import checks as K
    from model.book import load_book, load_facts
    from model.grid import run_grid
    from model.live import live_from_book

    F = load_facts()
    B = load_book(None, facts=F)
    g = run_grid(B, F, live_from_book(B, F))
    prob = g.layers["analytical"].prob
    cells = {c.label: c for c in g.cells}
    p = {c.label: prob[c.key] for c in g.cells}
    fired = {f.name: f for f in K.check_gates(g) if f.kind == "gate" and f.fired}
    out: dict = {"book_version": str(B.get("meta.version")), "gates": {k: sorted(f.cells) for k, f in fired.items()}}
    shock = int(str(B.get("regimes.crisis.one_off_loss.period"))[:4])
    if "roe_range" in fired:
        bad = sorted(fired["roe_range"].cells)
        i = cells[bad[0]].years.index(shock)
        same = [lab for lab, c in cells.items() if lab not in bad and all(
            getattr(c, a) == getattr(cells[bad[0]], a) for a in ("world", "regime")) and p[lab] > 0]
        out["roe_range"] = {"cells": bad, "year": shock, "roe": span(cells[x].annual["roe"][i] for x in bad),
                            "ni": span(cells[x].annual["ni_sh"][i] for x in bad),
                            "others": sorted(same), "others_roe": span(cells[x].annual["roe"][i] for x in same),
                            "others_ni": span(cells[x].annual["ni_sh"][i] for x in same)}
    if "terminal_share" in fired:
        bad = sorted(fired["terminal_share"].cells)
        rest = [lab for lab in cells if lab not in bad and p[lab] > 0]
        out["terminal_share"] = {"cells": bad, "share": span(cells[x].terminal_share for x in bad),
                                 "others": len(rest), "others_share": span(cells[x].terminal_share for x in rest)}
    if "cir_lt" in fired:
        d = fired["cir_lt"].detail
        out["cir_lt"] = {"mean": d["mean"], "target": d["target"], "tolerance": d["tolerance"], "modal": d["modal"],
                         "below_corridor": d["target"] - d["tolerance"] - d["mean"]}
    if "stress_sign" in fired:
        d = fired["stress_sign"].detail
        out["stress_sign"] = {"max_excess": d.get("max_excess"), "count": len(fired["stress_sign"].cells)}
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    n = numbers()
    a.out.write_text(json.dumps(n, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"ИТОГ: числа объяснений гейтов книги {n['book_version']} — {a.out.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
