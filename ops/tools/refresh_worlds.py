"""Миры семейства в книге банка: проверка канона (--check) и кандидат на новую запись.

Миры ставок — общая запись семейства 850 (`worlds_source.json`, побайтово) и её
рецепт (`worlds_inputs.yaml`, `worlds_recipe.py`, `WORLDS-RECIPE.md`); их
пересобирает книга-источник семейства после опорного заседания ЦБ, а книга банка
принимает новую запись новой версией (DESIGN §3.3, `data/assumptions/README.md`,
шаг 2). Этот инструмент — две вещи.

  python -B ops/tools/refresh_worlds.py --check
      строгая проверка канона (CI): рецепт на входах книги воспроизводит
      worlds_source.json целиком; sha256 и asof записи = worlds.source.* шаблона;
      сборка build_assumptions.py воспроизводит машинную книгу бит в бит; ближние
      ключи спредов книг ЧПД воспроизводятся правилом листа calib-nii на ключевой
      мира-опоры H записи (near_keys_diffs; та же сверка, что у перевода).

  python -B ops/tools/refresh_worlds.py --record КАТАЛОГ --out КАТАЛОГ [--median [--draws N]]
      кандидат на новую запись семейства: КАТАЛОГ записи — worlds_source.json
      (+ worlds_source.csv, worlds_inputs.yaml, если входы менялись). Проверяет, что
      рецепт воспроизводит новую запись, собирает книгу-кандидат (шаблон с новыми
      worlds.source.{sha256, record_asof, curve_date} и meta.curve_as_of) и
      считает ядро на книге и на кандидате (цена, дата и реестр книги). У банка
      ближние ключи спредов книг стоят на ключевой мира-опоры H: инструмент
      сверяет их на кандидате с правилом листа calib-nii и ОТКАЗЫВАЕТ (код 1),
      если они не держатся, — кандидат на прежних ключах смещён (ВТБ, анализ
      27.10.2026: точка +9,4 ₽ без пересчёта против +2,5 ₽ с ним); ключи
      пересчитывает лист, вносит новая версия книги.
      Пишет ТОЛЬКО в --out: assumptions_template.candidate.yaml,
      assumptions.candidate.yaml/.json и CANDIDATE.md (что меняется в записи,
      строки шаблона, точка и слои «книга → кандидат», черновик строки журнала).

Чего НЕ делает: не пишет в data/assumptions/ (каталог внутри книги как --out
отвергается), не публикует, не выбирает якоря и веса миров — это книга-источник
семейства и новая версия книги с подписью.

Коды: 0 — канон держится / кандидат собран; 1 — канон не держится или негодные
входы (нет файлов, рецепт не воспроизводит запись, ближние ключи книги не держатся
правилом на ключевой мира-опоры записи); 2 — кандидат не собрался (сборка книги
или ядро на нём падают).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BOOK = ROOT / "data" / "assumptions"
RECORD = "worlds_source.json"
RECORD_CSV = "worlds_source.csv"
INPUTS = "worlds_inputs.yaml"
TEMPLATE = "assumptions_template.yaml"
# Лист вывода книги: его счёт ближних ключей спредов книг (правило листа calib-nii, вход nii_books.near_rule) — тот же, которым
# перевод (ops/tools/rederive.py, шаг misc) сверяет ключи книги перед подбором
DERIVE_SHEET = BOOK / "evidence" / "path" / "derive_on_engine.py"
NEAR_KEYS_REMEDY = ("ближние ключи стоят на ключевой мира-опоры H записи миров: при новой записи их пересчитывает лист calib-nii "
                    "(stage1/calib-nii/r2/near_keys_worlds.py папки передачи; запись — evidence/path/inputs/vtb_r2_inputs.json, "
                    "включая путь бэктеста) и вносит в шаблон новая версия книги; кандидат на прежних ключах смещён "
                    "(docs/PORTING.md, пересборка миров 1.7)")

OK, BAD_INPUT, NOT_BUILT = 0, 1, 2


class Refused(Exception):
    """Негодные входы или канон не держится — код 1."""


class NotBuilt(Exception):
    """Кандидат не собрался — код 2."""


def _module(path: Path, name: str):
    """Модуль книги по пути (рецепт и сборщик живут в data/assumptions/, не в пакете)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe_diffs(recipe, inputs: dict, record: dict) -> list[str]:
    """Различия записи и рецепта на входах; пусто — воспроизведено.

    Режим `forward_bei` против записи без блока `m_inflation` — переходная сверка
    рецепта (N и H бит в бит, мир M печатается); иначе — строго целиком.
    """
    rebuilt = recipe.build_worlds(inputs)
    source = (inputs.get("m_inflation") or {}).get("source", "judgement")
    if source == "forward_bei" and "m_inflation" not in record:
        bad, _ = recipe.check_nh(record, rebuilt)
        return bad
    return recipe.compare(record, rebuilt)


def near_keys_diffs(book_path: Path, facts_dir: Path | None = None) -> list[str]:
    """Ближние ключи спредов книг машинной книги `book_path` против правила листа calib-nii на ключевой мира-опоры ЭТОЙ книги
    (её записи миров); пусто — ключи держатся.

    Ключи лет ближнего пути (год якоря и следующий) и книга бумаг по кварталам — функцией листа вывода `near_rule_keys` (та же
    сверка, что у перевода перед подбором, допуск — его же); ключи полугодий и LT книг с ключом года — та же линия окна без
    остатка якоря (актив: s − (1 − a) × ключевая мира-опоры за полугодие; LT — на ключевой последнего квартала сетки; пассив —
    s, у опта LT — wholesale_lt), как их пишет лист calib-nii (blocks_r2.spread_traj)."""
    doe = _module(DERIVE_SHEET, "_refresh_derive_on_engine")
    eng = doe.Engine(book_path, facts_dir)
    rule = eng.inputs["nii_books"]["near_rule"]
    books = eng.value("nii.books")
    tol = float(doe.NEAR_RULE_TOL)
    want = doe.near_rule_keys(eng, float(rule["fade"][doe.MISC_YEAR]))
    book = eng.current()
    ctx = eng.make_context(book, eng.facts)
    tl = ctx.timeline
    key = ctx.worlds[str(book.get("nii.transmission.reference_world"))].key

    def half_key(p: str) -> float:
        y, h = int(p[:4]), int(p[5])
        qs = [q for q in tl.quarters_of_year(y) if q >= 1 and (int(tl.period(q)[5]) <= 2) == (h == 1)]
        return sum(float(key[q]) for q in qs) / len(qs)

    for b, c in rule["books"].items():
        a, s = float(c["a"]), float(c["s"])
        line = want.setdefault(b, {})
        for k in books[b]["spread"]:
            if k in line or k == "LT_from":
                continue
            if k == "LT":
                if c["side"] == "asset":
                    line[k] = s - (1.0 - a) * float(key[tl.Q])
                else:
                    line[k] = float(rule["wholesale_lt"]) if b == doe.MISC_WHOLESALE else s
            elif re.fullmatch(r"\d{4}H[12]", str(k)) and c["side"] == "asset":
                line[k] = s - (1.0 - a) * half_key(str(k))
    bad = []
    for b, keys in want.items():
        have = books.get(b, {}).get("spread", {})
        for k, v in keys.items():
            if k not in have:
                bad.append(f"{b}.{k}: в книге нет ключа (правило {v:.5f})")
            elif abs(v - float(have[k])) > tol:
                bad.append(f"{b}.{k}: книга {float(have[k]):.5f}, правило {v:.5f}")
    return bad


def check_canon(book: Path = BOOK) -> tuple[list[str], list[str]]:
    """(нарушения, строки отчёта) канона миров книги."""
    problems, report = [], []
    for name in (RECORD, INPUTS, TEMPLATE, "worlds_recipe.py", "build_assumptions.py"):
        if not (book / name).exists():
            problems.append(f"нет {name} в каталоге книги")
    if problems:
        return problems, report
    recipe = _module(book / "worlds_recipe.py", "_book_worlds_recipe")
    inputs = yaml.safe_load((book / INPUTS).read_text(encoding="utf-8"))
    record = json.loads((book / RECORD).read_text(encoding="utf-8"))
    diffs = recipe_diffs(recipe, inputs, record)
    if diffs:
        problems.append(f"рецепт не воспроизводит {RECORD}: {len(diffs)} различий — " + "; ".join(diffs[:5]))
    else:
        report.append(f"рецепт воспроизводит {RECORD}: {len(record.get('rows', []))} строк")

    template = yaml.safe_load((book / TEMPLATE).read_text(encoding="utf-8")) or {}
    source = ((template.get("worlds") or {}).get("source") or {})
    sha = _sha(book / RECORD)
    if source.get("sha256") != sha:
        problems.append(f"sha256 {RECORD} {sha[:12]}… ≠ worlds.source.sha256 шаблона "
                        f"{str(source.get('sha256'))[:12]}…")
    elif record.get("asof") != source.get("record_asof"):
        problems.append(f"asof записи {record.get('asof')} ≠ worlds.source.record_asof {source.get('record_asof')}")
    else:
        report.append(f"запись {RECORD}: sha256 {sha[:12]}…, asof {record.get('asof')} — как в шаблоне")

    builder = _module(book / "build_assumptions.py", "_book_build_assumptions")
    try:
        text_yaml, text_json, machine = builder.render()
    except Exception as exc:  # noqa: BLE001 — BuildError и чужие отказы сборщика
        problems.append(f"сборка машинной книги отказала: {type(exc).__name__}: {exc}")
        return problems, report
    stale = [name for name, text in (("assumptions.yaml", text_yaml), ("assumptions.json", text_json))
             if not (book / name).exists() or (book / name).read_text(encoding="utf-8") != text]
    if stale:
        problems.append("машинная книга не воспроизводится сборкой: " + ", ".join(stale))
        return problems, report
    report.append(f"машинная книга воспроизводится сборкой (версия {machine['meta']['version']}, "
                  f"миры {', '.join(machine['worlds']['ids'])})")
    try:
        near = near_keys_diffs(book / "assumptions.yaml")
    except Exception as exc:  # noqa: BLE001 — отказ ядра или листа вывода
        problems.append(f"сверка ближних ключей спредов книг не выполнилась: {type(exc).__name__}: {exc}")
        return problems, report
    if near:
        problems.append(f"ближние ключи спредов книг не воспроизводятся правилом листа calib-nii на ключевой мира-опоры "
                        f"записи ({len(near)}): " + "; ".join(near[:6]) + " — " + NEAR_KEYS_REMEDY)
    else:
        report.append("ближние ключи спредов книг воспроизводятся правилом листа calib-nii на ключевой мира-опоры записи")
    return problems, report


# ------------------------------------------------------------------ кандидат

def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def candidate_template(text: str, *, sha: str, asof: str, curve_date: str | None) -> str:
    """Шаблон книги с новой записью: worlds.source.{sha256, record_asof, curve_date}, meta.curve_as_of."""
    block = re.search(r"^worlds:\n(?:[ \t]+.*\n|\n)*?[ \t]+source:.*\n((?:[ \t]{4,}.*\n)+)", text, re.M)
    if not block:
        raise Refused("в шаблоне нет блока worlds.source")
    body = block.group(1)
    new = re.sub(r'(sha256:\s*)"[0-9a-f]{64}"', rf'\g<1>"{sha}"', body, count=1)
    new = re.sub(r'(record_asof:\s*)"[^"]*"', rf'\g<1>"{asof}"', new, count=1)
    if curve_date:
        new = re.sub(r'(curve_date:\s*)"[^"]*"', rf'\g<1>"{curve_date}"', new, count=1)
    if new.count(sha) != 1 or f'"{asof}"' not in new:
        raise Refused("в блоке worlds.source шаблона нет строк sha256/record_asof в ожидаемом виде")
    out = text[:block.start(1)] + new + text[block.end(1):]
    if curve_date:
        out = re.sub(r'^(\s+curve_as_of:\s*)"[^"]*"', rf'\g<1>"{curve_date}"', out, count=1, flags=re.M)
    return out


def _core(machine: dict, facts) -> dict:
    """Точка и слои ядром на цене, дате и реестре книги."""
    from model.book import book_from_dict  # noqa: PLC0415
    from model.grid import run_grid  # noqa: PLC0415

    book = book_from_dict(machine, facts=facts)
    run = run_grid(book, facts)
    out = {"low": run.low, "point": run.point, "high": run.high}
    for name, layer in run.layers.items():
        out[f"v0_{name}"] = layer.v0
        out[f"pb_{name}"] = layer.pb
    return out


def _median(machine: dict, facts, draws: int | None) -> dict:
    from model.book import book_from_dict  # noqa: PLC0415
    from model.grid import live_from_book  # noqa: PLC0415
    from model.uncertainty import band  # noqa: PLC0415

    book = book_from_dict(machine, facts=facts)
    live = live_from_book(book, facts)
    head = band(book, facts, live, draws=draws).headline(
        float(book.get("joint.own_macro_confidence")), dict(live.prices), str(book.get("meta.company.main_ticker")))
    return {"median": float(head["median"]), "p10": float(head["band80"][0]), "p90": float(head["band80"][1])}


def _r(x: float) -> str:
    return f"{x:,.1f}".replace(",", " ").replace(".", ",")


def _signed(x: float) -> str:
    text = _r(abs(x))
    return text if not round(x, 1) else ("+" if x > 0 else "−") + text


def build_candidate(record_dir: Path, out: Path, *, book: Path = BOOK, facts_dir: Path | None = None,
                    median: bool = False, draws: int | None = None) -> dict:
    record_path = record_dir / RECORD
    if not record_path.exists():
        raise Refused(f"в каталоге записи нет {RECORD}")
    if _inside(out, book):
        raise Refused("--out внутри data/assumptions/: инструмент не пишет в книгу")
    new_record = json.loads(record_path.read_text(encoding="utf-8"))
    old_record = json.loads((book / RECORD).read_text(encoding="utf-8"))
    inputs_path = record_dir / INPUTS if (record_dir / INPUTS).exists() else book / INPUTS
    recipe_path = record_dir / "worlds_recipe.py" if (record_dir / "worlds_recipe.py").exists() \
        else book / "worlds_recipe.py"
    recipe = _module(recipe_path, "_candidate_worlds_recipe")
    inputs = yaml.safe_load(inputs_path.read_text(encoding="utf-8"))
    diffs = recipe_diffs(recipe, inputs, new_record)
    if diffs:
        raise Refused(f"рецепт ({recipe_path.name}, входы {inputs_path.parent.name}/{INPUTS}) не воспроизводит "
                      f"новую запись: {len(diffs)} различий — " + "; ".join(diffs[:5]))
    sha = _sha(record_path)
    curve_date = str((inputs.get("curve") or {}).get("date") or "") or None
    out.mkdir(parents=True, exist_ok=True)
    tmpl_text = candidate_template((book / TEMPLATE).read_text(encoding="utf-8"),
                                   sha=sha, asof=str(new_record.get("asof")), curve_date=curve_date)
    tmpl_path = out / "assumptions_template.candidate.yaml"
    tmpl_path.write_text(tmpl_text, encoding="utf-8", newline="\n")
    builder = _module(book / "build_assumptions.py", "_candidate_build_assumptions")
    builder.RECORD = record_path
    try:
        text_yaml, text_json, machine = builder.render(tmpl_path)
        builder_now = _module(book / "build_assumptions.py", "_current_build_assumptions")
        current = builder_now.render()[2]
    except Exception as exc:  # noqa: BLE001
        raise NotBuilt(f"книга-кандидат не собирается: {type(exc).__name__}: {exc}") from exc
    (out / "assumptions.candidate.yaml").write_text(text_yaml, encoding="utf-8", newline="\n")
    (out / "assumptions.candidate.json").write_text(text_json, encoding="utf-8", newline="\n")
    try:
        near = near_keys_diffs(out / "assumptions.candidate.yaml", facts_dir)
    except Exception as exc:  # noqa: BLE001 — отказ ядра или листа вывода на кандидате
        raise NotBuilt(f"сверка ближних ключей на кандидате не выполнилась: {type(exc).__name__}: {exc}") from exc
    if near:                                     # кандидат на прежних ключах смещён — не пишется (как отказ перевода)
        for name in ("assumptions_template.candidate.yaml", "assumptions.candidate.yaml", "assumptions.candidate.json"):
            (out / name).unlink(missing_ok=True)
        raise Refused(f"ближние ключи спредов книг не воспроизводятся правилом листа calib-nii на ключевой мира-опоры "
                      f"новой записи ({len(near)}): " + "; ".join(near[:6]) + " — " + NEAR_KEYS_REMEDY)
    for name in (RECORD, RECORD_CSV):
        if (record_dir / name).exists():
            shutil.copyfile(record_dir / name, out / name)
    try:
        from model.book import load_facts  # noqa: PLC0415

        facts = load_facts(facts_dir)
        before, after = _core(current, facts), _core(machine, facts)
        if median:
            before.update(_median(current, facts, draws))
            after.update(_median(machine, facts, draws))
    except Exception as exc:  # noqa: BLE001 — BookError, FactsError, отказ ядра
        raise NotBuilt(f"ядро не считает книгу или кандидат: {type(exc).__name__}: {exc}") from exc
    res = {"sha256": sha, "asof": new_record.get("asof"), "curve_date": curve_date,
           "record_changes": recipe.compare(old_record, new_record), "before": before, "after": after,
           "book_version": current["meta"]["version"]}
    (out / "CANDIDATE.md").write_text(report(res), encoding="utf-8", newline="\n")
    return res


def report(res: dict) -> str:
    rows = [("низ (рыночные ставки как есть), ₽", "low"), ("точка при λ книги, ₽", "point"),
            ("верх (свой взгляд), ₽", "high")]
    rows += [(f"V0 слоя {k[3:]}, млрд ₽", k) for k in res["before"] if k.startswith("v0_")]
    rows += [(f"P/B слоя {k[3:]}", k) for k in res["before"] if k.startswith("pb_")]
    rows += [(label, key) for label, key in (("медиана A-V9, ₽", "median"), ("P10, ₽", "p10"), ("P90, ₽", "p90"))
             if key in res["before"]]
    lines = [f"# Кандидат миров: запись {res['asof']} (кривая {res['curve_date'] or '—'})", "",
             f"Книга {res['book_version']} → кандидат с записью sha256 `{res['sha256']}`. Ядро — на цене, дате и "
             "реестре книги (живые входы не участвуют).", "",
             "## Ядро: книга → кандидат", "", "| что | книга | кандидат | сдвиг |", "|---|---:|---:|---:|"]
    for label, key in rows:
        b, a = res["before"][key], res["after"][key]
        if key.startswith("pb_"):
            lines.append(f"| {label} | {b:.3f} | {a:.3f} | {a - b:+.3f} |".replace(".", ","))
        else:
            lines.append(f"| {label} | {_r(b)} | {_r(a)} | {_signed(a - b)} |")
    changes = res["record_changes"]
    lines += ["", f"## Что меняется в записи ({len(changes)})", ""]
    lines += [f"- {c}" for c in changes[:80]] or ["- записи совпадают"]
    if len(changes) > 80:
        lines.append(f"- … ещё {len(changes) - 80}")
    lines += ["", "## Что сделать новой версией книги", "",
              f"1. Записать `{RECORD}` (+ `.csv`) побайтово в `data/assumptions/`; входы и рецепт — если менялись.",
              f"2. В шаблоне: `worlds.source.sha256: \"{res['sha256']}\"`, `record_asof: \"{res['asof']}\"`"
              + (f", `curve_date` и `meta.curve_as_of`: \"{res['curve_date']}\"" if res["curve_date"] else "")
              + " (готовый шаблон — `assumptions_template.candidate.yaml` рядом).",
              "3. `python -B data/assumptions/build_assumptions.py`, затем результаты книги, числа документов "
              "(`ops/tools/render_numbers.py`) и прогулка версий (`ops/tools/walk_book.py`).", "",
              "## Черновик строки журнала версий", "",
              f"- Миры семейства: запись {res['asof']} (sha256 {res['sha256'][:12]}…); точка "
              f"{_r(res['before']['point'])} → {_r(res['after']['point'])} ₽ ({_signed(res['after']['point'] - res['before']['point'])}).",
              ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="строгая проверка канона миров книги")
    ap.add_argument("--record", help="каталог новой записи семейства (worlds_source.json …)")
    ap.add_argument("--out", help="каталог кандидата (вне data/assumptions/)")
    ap.add_argument("--facts", help="каталог фактов (по умолчанию data/facts)")
    ap.add_argument("--median", action="store_true", help="ещё медиана полосы A-V9 на книге и кандидате")
    ap.add_argument("--draws", type=int, default=None, help="прогонов полосы для --median")
    args = ap.parse_args(argv)
    if args.check:
        problems, lines = check_canon()
        for line in lines:
            print(line)
        for problem in problems:
            print(f"КАНОН: {problem}", file=sys.stderr)
        return BAD_INPUT if problems else OK
    if not (args.record and args.out):
        ap.error("нужны --check или --record КАТАЛОГ --out КАТАЛОГ")
    try:
        res = build_candidate(Path(args.record), Path(args.out),
                              facts_dir=Path(args.facts) if args.facts else None,
                              median=args.median, draws=args.draws)
    except Refused as exc:
        print(f"НЕГОДНЫЕ ВХОДЫ: {exc}", file=sys.stderr)
        return BAD_INPUT
    except NotBuilt as exc:
        print(f"КАНДИДАТ НЕ СОБРАН: {exc}", file=sys.stderr)
        return NOT_BUILT
    print(f"кандидат записан: {args.out} (запись {res['asof']}, изменений в записи {len(res['record_changes'])}; "
          f"точка {_r(res['before']['point'])} → {_r(res['after']['point'])} ₽)")
    return OK


if __name__ == "__main__":
    sys.exit(main())
