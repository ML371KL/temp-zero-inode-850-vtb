# -*- coding: utf-8 -*-
"""Шаги приёма миров книги Банка ВТБ, которые не сводятся к числу правила: запись листа во входе, вывод на ядре, сторожа,
таблицы, контрольная модель, прогулка, журнал версии, календарь, быстрые числа (их зовёт манифест
data/assumptions/worlds_dependents.yaml; команда — ops/tools/adopt_worlds.py).

  python -B ops/tools/worlds_steps.py sheet-record [--check]
      запись листа calib-nii во входе листа вывода `evidence/path/inputs/vtb_r2_inputs.json`: `nii_books.books` — ключи
      и лаги книг шаблона (шаг near_spreads листа вывода сверяет шаблон с ней), `backtest_path.nim` — путь бэктеста мира H
      правилом (ops/tools/worlds_rules.py:backtest_nim);
  python -B ops/tools/worlds_steps.py lag-band
      сторож оси лага книги бумаг: полоса правила лага (RMS ≤ 1,25 × минимума) на записи книги и на записи прежней
      версии миров; ось книги — суждение (команда её не пишет): сдвинулась полоса правила — ФЛАГ;
  python -B ops/tools/worlds_steps.py derive
      вывод на ядре — команда книги ops/tools/rederive.py (лист evidence/path/derive_on_engine.py как есть: шаги, шаг
      realized цели передачи, сверки; `--no-quick`, процессы — BANK_WORKERS): пишет шаблон, машинную книгу и запись
      листа; повтор на той же книге — «изменений нет». Пороги гейтов, которые правило листа даёт другими, — ФЛАГ (их
      переносит ведущий);
  python -B ops/tools/worlds_steps.py tables [--force]
      таблицы книги (model.book_results), если отпечаток книги (`reference_variants_book` таблиц) или её версия не
      совпадают с книгой; иначе — «пересчёт не нужен»;
  python -B ops/tools/worlds_steps.py control
      контрольная модель (`tests.test_control_model --write`); строк вне допуска больше, чем до приёма, — код 1; строки
      те же — файл не трогается (метка дня и коммита счёта остаются прежними);
  python -B ops/tools/worlds_steps.py walk
      прогулка версий от прошлой выпущенной книги (тег `book-<версия>`) к книге дерева: файл шагов — из блока `walk`
      манифеста, печать — out/walk_<было>_to_<стало>.txt; обе проверки прогулки обязаны сказать «ДА»;
  python -B ops/tools/worlds_steps.py changes
      журнал версии книги `data/assumptions/V<версия>-CHANGES.md`: ключи шаблона «было → стало» против прошлой
      выпущенной книги и строки прогулки (проза разделов — человеку);
  python -B ops/tools/worlds_steps.py calendar
      дата отказа сборки по мирам (заседание Банка России с прогнозом после даты кривой + срок книги) — есть ли она в
      календаре MANUAL §10.9 (нет — ФЛАГ: строку правит человек);
  python -B ops/tools/worlds_steps.py quick --out ФАЙЛ [--draws 500]
      быстрые числа книги дерева (формат model-kit: point, median, low, high, print, worlds, runs, seed).

Строки вывода «ИТОГ: …» команда приёма кладёт в отчёт шага, «ФЛАГ: …» — в красные флаги.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import worlds_rules as R  # noqa: E402

BOOK = ROOT / "data" / "assumptions"
OUT = BOOK / "evidence" / "path" / "out"
MANIFEST = BOOK / "worlds_dependents.yaml"
INPUTS = ROOT / R.INPUTS
PY = sys.executable


def say(line: str) -> None:
    print(line, flush=True)


def env() -> dict:
    return dict(os.environ, PYTHONIOENCODING="utf-8")


def record() -> dict:
    return json.loads((BOOK / "worlds_source.json").read_bytes().decode("utf-8"))


def template() -> dict:
    return yaml.safe_load((BOOK / "assumptions_template.yaml").read_text(encoding="utf-8"))


def same_version() -> bool:
    v, f = os.environ.get("WORLDS_VERSION"), os.environ.get("WORLDS_FROM_VERSION")
    return bool(v) and v == f


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def ru(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}".replace(".", ",").replace("-", "−")


# ----------------------------------------------------------------------------------------------- запись листа во входе
def cmd_sheet_record(a) -> int:
    book = template()
    old = INPUTS.read_bytes()
    doc = json.loads(old.decode("utf-8"))
    doc["nii_books"]["books"] = R.sheet_record(book, doc)
    nim = R.backtest_nim(ROOT, record(), book, doc)
    doc["backtest_path"]["nim"] = nim
    new = dump(doc).encode("utf-8")
    if new == old:
        say(f"ИТОГ: запись листа во входе (ключи книг, путь бэктеста мира H {ru(100 * nim[0], 3)} … {ru(100 * nim[-1], 3)} %) — "
            "как в дереве")
        return 0
    if a.check:
        say("РАСХОЖДЕНИЕ: запись листа во входе vtb_r2_inputs.json не равна ключам шаблона или пути бэктеста правила")
        return 1
    INPUTS.write_bytes(new)
    say(f"ИТОГ: запись листа во входе переписана: ключи книг шаблона, путь бэктеста мира H {ru(100 * nim[0], 3)} … "
        f"{ru(100 * nim[-1], 3)} %")
    return 0


# ----------------------------------------------------------------------------------------------- сторож оси лага
def source_record(version: str) -> dict | None:
    src = os.environ.get("WORLDS_SOURCE_DIR")
    p = Path(src) / "versions" / version / "record" / "worlds_source.json" if src else None
    return json.loads(p.read_bytes().decode("utf-8")) if p and p.exists() else None


def cmd_lag_band(a) -> int:
    book = template()
    inp = json.loads(INPUTS.read_text(encoding="utf-8"))
    now = R.near_keys(ROOT, record(), book, inp)["securities"]
    ax = book["valuation"]["uncertainty"]["axes"][R.axis_index(book, [f"nii.books.{R.SECURITIES}.rho"])]
    words = (f"ось лага книги бумаг {ax['low']}–{ax['high']} (суждение книги), полоса правила {now['band'][0]}–{now['band'][1]}, "
             f"лаг правила {now['rho']}")
    prev_v = os.environ.get("WORLDS_FROM_VERSION")
    prev_rec = source_record(prev_v) if prev_v and not same_version() else None
    if prev_rec is not None:
        was = R.near_keys(ROOT, prev_rec, book, inp)["securities"]
        if tuple(was["band"]) != tuple(now["band"]):
            say(f"ФЛАГ: полоса правила лага книги бумаг сдвинулась {was['band'][0]}–{was['band'][1]} → {now['band'][0]}–"
                f"{now['band'][1]} (миры {prev_v} → {os.environ.get('WORLDS_VERSION')}); {words} — перенос оси решает ведущий")
            return 0
    say(f"ИТОГ: {words}" + ("" if prev_rec is None else " — полоса не сдвинулась"))
    return 0


# ----------------------------------------------------------------------------------------------- вывод на ядре
def cmd_derive(a) -> int:
    base = "adopt-" + re.sub(r"[^\w.\-]", "_", os.environ.get("WORLDS_VERSION") or "local")
    label, n = base, 1
    while (ROOT / "var" / "rederive" / f"{label}.json").exists():     # круг цикла — своя запись запуска (флаги кругов целы)
        n += 1
        label = f"{base}-{n}"
    workers = os.environ.get("BANK_WORKERS") or "2"
    p = subprocess.run([PY, "-B", "ops/tools/rederive.py", "--no-quick", "--workers", workers, "--label", label], cwd=ROOT,
                       env=env(), capture_output=True, text=True, encoding="utf-8", errors="replace")
    run_path = ROOT / "var" / "rederive" / f"{label}.json"
    if p.returncode != 0:
        say("\n".join((p.stdout + p.stderr).strip().splitlines()[-15:]))
        return 1
    run = json.loads(run_path.read_text(encoding="utf-8"))
    d = run.get("derive") or {}
    if d.get("stopped"):
        say("перевывод остановлен: " + "; ".join(d["stopped"])[:600])
        return 1
    written = [c for c in d.get("changes") or [] if c.get("written")]
    rounds = " → ".join(f"{r['max_relative_change']:.2e}" for r in (d.get("convergence") or {}).get("rounds", []))
    for row in d.get("unwritten") or []:
        say(f"ФЛАГ: порог гейта {row['key']}: в книге {row['book']}, правило листа даёт {row['sheet']} — не переписан "
            "(пороги гейтов команда сверяет, но не пишет; перенос — решение ведущего)")
    say(f"ИТОГ: вывод на ядре (rederive.py, запуск {label}): " + (f"записано чисел {len(written)} в {len({c['key'] for c in written})} "
        f"ключах" if written else "изменений нет") + f"; круги связанных шагов {rounds or '—'}; записано: "
        + (", ".join(run.get("wrote") or []) or "ничего"))
    return 0


# ----------------------------------------------------------------------------------------------- таблицы и контроль
def cmd_tables(a) -> int:
    sys.path.insert(0, str(ROOT))
    from model.book import load_book, load_facts  # noqa: PLC0415
    book = load_book(facts=load_facts())
    res_path = BOOK / "results.json"
    res = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {}
    ver = str(book.get("meta.version"))
    if not a.force and res.get("reference_variants_book") == book.digest and str(res.get("book_version")) == ver:
        say(f"ИТОГ: таблицы посчитаны на этой книге (отпечаток {book.digest[:12]}…, версия {ver}) — пересчёт не нужен")
        return 0
    p = subprocess.run([PY, "-B", "-m", "model.book_results"], cwd=ROOT, env=env(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        say((p.stdout + p.stderr).strip()[-2000:])
        return 1
    h = json.loads(res_path.read_text(encoding="utf-8"))["headline"]
    say(f"ИТОГ: таблицы книги {ver}: медиана {h['median']:.2f} (печать {h.get('printed_median')}), точка {h['point']:.2f}, "
        f"низ {h['low']:.2f}, верх {h['high']:.2f}")
    return 0


def cmd_control(a) -> int:
    path = ROOT / "data" / "checks" / "control_model.json"
    old = path.read_bytes() if path.exists() else None
    prev = json.loads(old.decode("utf-8")) if old is not None else None
    p = subprocess.run([PY, "-B", "-m", "tests.test_control_model", "--write"], cwd=ROOT, env=env(), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if not path.exists() or p.returncode not in (0, 1):     # --write: 1 — есть строки вне допуска (сводка записана)
        say((p.stdout + p.stderr).strip()[-2000:])
        return 1
    new = json.loads(path.read_text(encoding="utf-8"))
    was_bad = int(prev.get("n_bad") or 0) if prev else 0
    if int(new.get("n_bad") or 0) > was_bad:
        say(f"ФЛАГ: контрольная модель — вне допуска {new.get('n_bad')} строк из {new.get('n_rows')} (до приёма — {was_bad})")
        return 1
    stamp = ("as_of", "commit")
    if prev is not None and {k: v for k, v in prev.items() if k not in stamp} == {k: v for k, v in new.items() if k not in stamp}:
        path.write_bytes(old)
        say(f"ИТОГ: контрольная модель — те же {new['n_rows']} строк, вне допуска {new.get('n_bad')} (как до приёма; файл не тронут)")
        return 0
    say(f"ИТОГ: контрольная модель — {new['n_rows']} строк, вне допуска {new.get('n_bad')} (до приёма {was_bad}; записано)")
    return 0


# ----------------------------------------------------------------------------------------------- прогулка и журнал
def released() -> list[str]:
    p = subprocess.run(["git", "-C", str(ROOT), "tag", "--list", "book-*"], capture_output=True, text=True)
    vs = [t[5:] for t in p.stdout.split() if re.fullmatch(r"book-\d+\.\d+", t)]
    return sorted(vs, key=lambda s: tuple(int(x) for x in s.split(".")))


def previous_book(ver: str) -> str:
    key = tuple(int(x) for x in ver.split("."))
    older = [v for v in released() if tuple(int(x) for x in v.split(".")) < key]
    if not older:
        raise SystemExit(f"нет выпущенной книги раньше {ver} (теги book-*)")
    return older[-1]


def at_tag(ver: str, rel: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"refs/tags/book-{ver}:{rel}"], capture_output=True,
                          check=True).stdout


def walk_ctx(book: dict, ver: str, prev: str) -> dict:
    idx = json.loads((Path(os.environ["WORLDS_SOURCE_DIR"]) / "versions.json").read_text(encoding="utf-8")) \
        if os.environ.get("WORLDS_SOURCE_DIR") else None
    state = json.loads((BOOK / "worlds_state.json").read_text(encoding="utf-8"))
    entry = (idx or {}).get("versions", {}).get(state["version"]) or {}
    label = (entry.get("labels") or {}).get("walk_step") or f"миры ставок {state['version']}"
    return {"label": label[:1].upper() + label[1:], "short": (entry.get("labels") or {}).get("short", state["version"]),
            "version": state["version"], "book": ver, "prev": prev,
            "cbr_decision_ru": R.ru_date(entry["cbr_decision"]) if entry.get("cbr_decision") else "—"}


def fill(text: str, ctx: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(ctx[m.group(1)]), text)


def cmd_walk(a) -> int:
    w = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["walk"]
    book = template()
    ver = str(book["meta"]["version"])
    prev = previous_book(ver)
    ctx = walk_ctx(book, ver, prev)
    lines = [fill(w["head"], ctx)]
    for s in w["steps"]:
        lines.append(f"- name: {json.dumps(fill(s['name'], ctx), ensure_ascii=False)}")
        lines.append(f"  from_end: [{', '.join(s['from_end'])}]")
    steps = ROOT / fill(w["file"], ctx)
    steps.parent.mkdir(parents=True, exist_ok=True)
    steps.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    tmp = ROOT / "var" / "adopt"
    tmp.mkdir(parents=True, exist_ok=True)
    start = tmp / f"book-{prev}.yaml"
    start.write_bytes(at_tag(prev, "data/assumptions/assumptions.yaml"))
    p = subprocess.run([PY, "-B", "ops/tools/walk_book.py", "--start", str(start), "--end", "data/assumptions/assumptions.yaml",
                        "--steps", steps.relative_to(ROOT).as_posix()], cwd=ROOT, env=env(), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = ROOT / fill(w["out"], ctx)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(p.stdout, encoding="utf-8", newline="\n")
    if p.returncode != 0:
        say((p.stdout + p.stderr).strip()[-1500:])
        return 1
    say(f"ИТОГ: прогулка {prev} → {ver}: {len(w['steps'])} шагов, обе проверки «ДА» (печать — {out.relative_to(ROOT).as_posix()})")
    return 0


def flat(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flat(v, f"{prefix}{k}."))
    else:
        out[prefix[:-1]] = d
    return out


def cmd_changes(a) -> int:
    book = template()
    ver = str(book["meta"]["version"])
    prev = previous_book(ver)
    old = yaml.safe_load(at_tag(prev, "data/assumptions/assumptions_template.yaml").decode("utf-8"))
    fo, fn = flat(old), flat(book)
    keys = sorted(k for k in set(fo) | set(fn) if fo.get(k) != fn.get(k))
    ctx = walk_ctx(book, ver, prev)
    walk_txt = ROOT / fill(yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["walk"]["out"], ctx)

    def cell(x):
        s = json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x
        return (s if len(s) <= 80 else s[:77] + "…").replace("|", "/")
    lines = [f"# Книга {ver}: {ctx['label'].lower()} — журнал версии", "",
             f"Книга {prev} → {ver}: приём миров {ctx['version']} командой `ops/tools/adopt_worlds.py` (манифест "
             f"`worlds_dependents.yaml`, отчёт — `var/adopt/{ctx['version']}/report.json`). Якорь, факты, дата книги, цена, "
             f"суждения и зерно полосы — прежние; меняются миры и числа, зависящие от них, по правилам книги (ближние ключи "
             f"спредов и лаг бумаг — правило листа calib-nii, числа на ядре — `ops/tools/rederive.py`).", "",
             "## Прогулка версий", "", "```", walk_txt.read_text(encoding="utf-8").rstrip("\n") if walk_txt.exists() else "—",
             "```", "", f"## Ключи шаблона «было → стало» ({len(keys)})", "", "| ключ | было | стало |", "|---|---|---|"]
    lines += [f"| `{k}` | {cell(fo.get(k, '—'))} | {cell(fn.get(k, '—'))} |" for k in keys]
    path = BOOK / f"V{ver}-CHANGES.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    say(f"ИТОГ: журнал версии {path.name}: {len(keys)} ключей шаблона; проза разделов, шапка шаблона и решения — просмотреть "
        "ведущему")
    say(f"ФЛАГ: тесты решений tests/test_ops_rederive.py закреплены на книге {prev} (BOOK_VERSION — «новая версия — пересмотр»): "
        f"книга {ver} требует пересмотра решений ведущим")
    return 0


def cmd_calendar(a) -> int:
    """Календарь ближайших отказов сборки (MANUAL §10.9): дата отказа по мирам — первое заседание Банка России с
    прогнозом после даты кривой книги + срок `worlds_after_cbr` + 1 день (как `tests/test_ops_docs.py`). Дата есть в
    таблице календаря — ИТОГ; нет — ФЛАГ (строку и абзац правит человек: текст строки — проза)."""
    book = yaml.safe_load((BOOK / "assumptions.yaml").read_text(encoding="utf-8"))
    days = book["checks"]["manual_overdue_days"]
    curve = dt.date.fromisoformat(str(book["worlds"]["source"]["curve_date"]))
    events = json.loads((ROOT / "data" / "facts" / "calendar.json").read_text(encoding="utf-8"))["events"]

    def start(e: dict) -> dt.date:
        return dt.date.fromisoformat(str(e["latest"] if e.get("estimated") is True else e["date"]))
    meetings = sorted(start(e) for e in events if e.get("kind") == "cbr_forecast" and start(e) > curve)
    if not meetings:
        say("ФЛАГ: в календаре фактов нет заседания Банка России с прогнозом после даты кривой миров")
        return 0
    day = (meetings[0] + dt.timedelta(days=int(days["worlds_after_cbr"]) + 1)).strftime("%d.%m.%Y")
    text = (ROOT / "docs" / "MANUAL.md").read_text(encoding="utf-8")
    block = text.split("**Календарь ближайших отказов сборки**", 1)[1].split("**Проверка на любую дату**", 1)[0]
    if f"| {day} | миры" in block:
        say(f"ИТОГ: календарь отказов сборки: миры — {day} (заседание {meetings[0].strftime('%d.%m.%Y')}), строка на месте")
    else:
        say(f"ФЛАГ: календарь отказов сборки MANUAL §10.9 и строка DECISIONS: первый день отказа по мирам — {day} "
            f"(заседание {meetings[0].strftime('%d.%m.%Y')}, кривая {curve.strftime('%d.%m.%Y')}) — строки нет, поправить")
    return 0


# ----------------------------------------------------------------------------------------------- быстрые числа
def cmd_quick(a) -> int:
    sys.path.insert(0, str(ROOT))
    from model.book import load_book, load_facts  # noqa: PLC0415
    from model.grid import live_from_book, run_grid, world_layer  # noqa: PLC0415
    from model.uncertainty import band  # noqa: PLC0415
    facts = load_facts()
    book = load_book(facts=facts)
    run = run_grid(book, facts)
    live = live_from_book(book, facts)
    b = band(book, facts, live, draws=a.draws)
    head = b.headline(float(book.get("joint.own_macro_confidence")), dict(live.prices), str(book.get("meta.company.main_ticker")))
    out = {"point": round(run.point, 3), "median": round(float(head["median"]), 3), "low": round(run.low, 3),
           "high": round(run.high, 3), "print": head.get("printed_median"),
           "worlds": {w: round(world_layer(run, w)["price"], 3) for w in book.get("worlds.ids")},
           "runs": b.draws, "seed": b.seed, "book_version": str(book.get("meta.version"))}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(dump(out), encoding="utf-8")
    say(f"ИТОГ: быстрые числа ({b.draws} прогонов): медиана {out['median']}, точка {out['point']}")
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sheet-record")
    p.add_argument("--check", action="store_true")
    sub.add_parser("lag-band")
    sub.add_parser("derive")
    p = sub.add_parser("tables")
    p.add_argument("--force", action="store_true")
    sub.add_parser("control")
    sub.add_parser("walk")
    sub.add_parser("changes")
    sub.add_parser("calendar")
    p = sub.add_parser("quick")
    p.add_argument("--out", required=True)
    p.add_argument("--draws", type=int, default=500)
    a = ap.parse_args(argv)
    return globals()[f"cmd_{a.cmd.replace('-', '_')}"](a)


if __name__ == "__main__":
    sys.exit(main())
