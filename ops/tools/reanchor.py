# -*- coding: utf-8 -*-
"""Перезаякоривание книги на отчёт квартала: кандидат книги и фактов, «что сдвинулось», разложение скачка.

ЗАЧЕМ ФУНКЦИЯ, А НЕ РУЧНАЯ ПРАВКА (М§15.2). Книга стоит на одном квартале; отчёт МСФО закрывает
её первый прогнозный квартал, и якорь переходит на него. Всё, что помнит прошлое или привязано к
якорю, обязано переехать вместе с ним: иначе оценка сдвигается без единой новости (урок 850oa:
ручная процедура дала сотни рублей «механики»). Инструмент делает перенос одной функцией, а тесты
`tests/test_reanchor*.py` держат инвариант «факт = ожидание ⇒ механика ≈ 0»: клетка,
перезаякоренная на своём пути, сохраняет стоимость. Порядок работы и формулы — docs/REANCHOR.md.

Форму книги выбирают её ключи, форму фактов — узлы прежних фактов: годовой или квартальный календарь
дивидендов (`dividends.calendar.frequency`), остатки книг суммой строк или прямыми узлами
`balance.books.<b>`, постоянные прочие активы, ограничение роста капиталом, строки истории мостов.

Как запускать (из корня репозитория):
  python -B ops/tools/reanchor.py --expected ФАЙЛ.json
      ожидаемый отчёт закрываемого квартала — «факты = ожидание модели» (сухой прогон; не
      шаблон для настоящих чисел: в нём нет ни одного факта)
  python -B ops/tools/reanchor.py --facts ФАЙЛ.json --out КАТАЛОГ
      [--valuation-date ГГГГ-ММ-ДД] [--version В] [--band ПРОГОНОВ] [--no-cells]
      [--transmission keep|resolve] [--compare-facts КАТАЛОГ]
      [--book КНИГА] [--facts-dir КАТАЛОГ] [--template ШАБЛОН]
      кандидат книги и фактов на отчёте ФАЙЛ и разложение скачка на дате оценки
      (по умолчанию — `published` отчёта, иначе день после конца квартала)
  python -B ops/tools/reanchor.py --capital-form ФАЙЛ.json --out КАТАЛОГ
      [--valuation-date ГГГГ-ММ-ДД] [--version В] [--band ПРОГОНОВ] [--compare-facts КАТАЛОГ]
      замена оценки нормативов якоря фактом формы БЕЗ смены якоря: кандидат книги и фактов на том
      же квартале и сдвиг точки от замены (строка «факты» разложения между выпусками)
Файл настоящего отчёта пишет сборщик фактов из листов нового квартала, факты нового якоря из
ожидаемого отчёта — он же:
  python -B ops/tools/build_facts.py --anchor КВАРТАЛ --out КАТАЛОГ --report ФАЙЛ.json
  python -B ops/tools/build_facts.py --expected ФАЙЛ.json --out КАТАЛОГ

Что пишет — ТОЛЬКО в --out (по умолчанию var/reanchor/<квартал>/, у формы — var/reanchor/<квартал>-form/).
Внутри репозитория каталог кандидата — только под var/ (в git оттуда попадает один .gitkeep): любой
другой каталог рабочей копии (data/, model/, docs/, tests/, ops/, web/…) — отказ; вне репозитория —
куда угодно. В режиме `resolve` — только expected.json и REANCHOR.md.
  assumptions.yaml, assumptions.json   машинная книга-кандидат (без комментариев)
  assumptions_template.yaml            шаблон книги с теми же правками (комментарии сохранены)
  facts/*.json                         рабочие факты нового якоря из файла отчёта (узлы с пометкой
                                       `calc: reanchor…`; канон фактов с источниками и сверками
                                       собирает `build_facts.py`, сверка — `--compare-facts`)
  expected.json                        ожидаемый отчёт того же квартала
  REANCHOR.md                          производные величины, дивиденды по периодам, «что сдвинулось»,
                                       разложение скачка точки и медианы (в квартале шока — ещё строка
                                       «обучение» отчёта без шока, М§12; при росте, урезанном капиталом
                                       в части клеток, — абзац о росте; у книги с миром-опорой κ — строка
                                       «история до сетки»), проверки ядра на кандидате (инварианты,
                                       сработавшие гейты и флаги; числа гейтов-целей книги и уровни после
                                       фазы роста — до и после), предупреждения и ручные шаги
                                       у `--capital-form` REANCHOR.md — о замене оценки фактом формы: что
                                       заменено, что выведено заново, сдвиг точки, проверки ядра

ФАЙЛ ОТЧЁТА КВАРТАЛА (`quarter-report/1`; JSON; млрд ₽, млн шт., доли единицы; расходы — со знаком
минус, как в отчётности; ОПУ и проценты — за КВАРТАЛ, не нарастающим итогом). Незнакомый ключ — отказ.
  schema       "quarter-report/1" (необязательно)
  period       закрываемый квартал — РОВНО первый прогнозный квартал книги
  as_of, published, source, note      конец квартала (сверка), дата публикации (дата оценки
               кандидата), источник и примечание — необязательно
  balance      остатки на конец квартала (МСФО группы):
               books {книга ЧПД: остаток} — все книги `nii.books` (кредиты — валовые, кредиты по СС —
               внутри своей книги); loans_fvtpl (у книги без отдельной части по СС — справка); fvoci,
               fvtpl_bonds (долговые бумаги FVOCI с репо и облигации по СС через ОПУ); allowance
               (резерв по кредитам АС, величиной); other_assets, other_liabilities (без дивидендов к
               выплате); other_assets_fixed (постоянная в рублях часть прочих активов; нет — значение
               прежних фактов); dividends_payable; bv_common (капитал акционеров); fvoci_reserve
               (после налога); at1, nci — если изменились.
               Годовой календарь: dividends_payable_year (год прибыли; обязателен при сумме > 0).
               Квартальный календарь: dividends_payable_declared [{period, amount}] — объявленные и
               не выплаченные дивиденды по кварталам прибыли (нет поля — список пуст; остаток сверх
               списка — постоянное обязательство); dividends_payable_year не читается — предупреждение
  interest     {книга: проценты квартала по книге, величиной}; dia — взносы на страхование вкладов
  pnl          nii, fees_net, llp_debt_fa, insurance_net, noncore_net, opex, pbt, tax, ni,
               ni_shareholders; необязательно — misc_net (иначе остаток до pbt), oci_fvoci,
               other_equity_movements, estimated (прибыль квартала — напечатанное значение: строки
               прибыли фактов кандидата несут пометку оценки), t2_premium (надбавка за субординацию
               квартала, величиной: процентный расход вне книг — в остаток «ЧПД − проценты книг»,
               который несут ставки нового якоря, не входит; её пишет ожидаемый отчёт книги с ключом
               `capital.n20.t2_premium`, М§15.2 п. 3)
  capital      n20_0 и n20_pre_dividend (норматив до вычета объявленного дивиденда из
               регуляторного капитала?), n1_1_bank, basel_cet1, basel_rwa, bank_base_capital — слоты
               семейства, смысл — по книге (у панели с нормативами банковской группы: второй норматив
               группы, капитал группы без регуляторных инструментов, вменённые RWA, базовый капитал
               группы); необязательно — t2 (инструменты капитала), estimated и estimate
               {слот: {bank_value, spread, spread_as_of}} — нормативы стоят оценкой до выхода формы
  market       ofz_curve {1, 3, 5, 10} — бескупонная кривая на отчётную дату; key_avg — средняя
               ключевая квартала; price_index — индекс цен квартала (конец к началу), необязательно:
               без него — ожидаемый индекс миров книги
  mgmt         nim, cor — управленческие ЧПМ и стоимость риска квартала; cir — необязательно
  shares       issued_total, outstanding_total, economic_treasury, поля по категориям акций — если
               изменились
  dividend_decisions   квартальный календарь: [{period, dps, decided_date, record_date?, pay_date?,
               pool_declared?}] — решения собраний, принятые после прежней даты фактов и не позже
               конца закрываемого квартала; в ожидаемом отчёте — решения клеток этого квартала

ФАЙЛ ФОРМЫ (`capital-form/1`): period (якорь книги), n20_0, n1_1_bank, basel_cet1, basel_rwa,
bank_base_capital; необязательно — schema, as_of, published, source, note, t2, n20_pre_dividend.

ЧТО ПЕРЕНОСИТСЯ:
  meta         anchor_period, first_period, facts_date, valuation_date, version
  наблюдение   закрытый квартал → `joint.regime_update.observations` с замороженными ожиданиями
               режимов прежней книги (mu_cor, mu_nim); нау-каст того же квартала заменяется;
               наблюдения старше окна удаляются; μ оставшихся записей не пересчитываются — ни при
               следующих переносах, ни при смене года якоря (М§12); апостериорные в книгу не
               вписываются
  цены якоря   `noncore.result_real`, `other.misc_net_real` и их оси × индекс цен квартала (у года
               якоря первой строки индексируется только остаток года)
  anchor-ключи отношения, которые клетка держит постоянными, выводятся из новых фактов сами;
               линия доли текущих счетов (c_ref, key_ref) и базовое оптовое фондирование
               (`volumes.wholesale_to_funds`) замораживаются числами прежней книги — их состояние
               идёт с лагом, и вывод заново сдвинул бы само правило; структура нормировки
               сегментной CoR — доля юрлиц прежнего якоря ключом `credit.segment_relative.
               corporate_share_ref` (заданный ключ остаётся, М§4.6, REANCHOR §3.3)
  капитал      плотности RWA × общий множитель к RWA якоря; вычеты `deductions_anchor` — формулой
               книги на новых фактах (при квартальном календаре вычет второго норматива — с
               дивидендами очереди вычетов якоря, М§4.11); `gap_pp` — так, чтобы якорь воспроизводил
               оба норматива отчёта; ключ квартала якоря траектории `capital.n20.t2` — факт отчёта,
               если книга пишет этот ключ явно; доли вычета якоря, постоянные в рублях
               (`capital.n20.deductions_fixed_share`, `capital.n11.deductions_fixed_share`, М§4.11), —
               суммой: постоянная в рублях часть вычета прежняя, доля и концы её оси переписаны на
               вычет нового якоря; доля или конец оси вне [0; 1] — отказ с названным путём
  дивиденды    квартальный календарь: решения отчёта — строками истории дивидендов с днём решения
               (они закрывают свои кварталы прибыли на новом якоре); объявленное и не выплаченное —
               списком по периодам; записи реестра — в затравку нового якоря, пока их экс-дата впереди
               или их сумма стоит в списке. Годовой календарь: год объявленного дивиденда
  передача     режим `keep` (единственный в процедуре, М§15.2 п. 8): скаляры пути σ0_A, σ0_L, φ_A,
               φ_L прежней книги сохраняются, а цели A-N2, A-N3 и доли `nii.sigma0_split`,
               `nii.phi_split` пересчитываются на структуру нового якоря. `--transmission resolve`
               — только диагностика: цели прежние, ядро решает скаляры заново (скачок без новости
               целиком в строке «механика»); кандидат книги и фактов при этом не пишется
  уровень      у книги с ключом `nii.transmission.level_world` ключ цели ЧПМ — само суждение об уровне:
  маржи        стационарная маржа названного мира на составе баланса якоря. При сохранённых скалярах
               пути (спреды книг те же) ключ переписывается на состав баланса нового якоря — запись
               прежнего суждения, механика ≈ 0; прежнее и новое значение печатаются с разложением сдвига
               на маржу движка и мост. Гейт `checks.nim_stationary` в том же мире сверяет то же число:
               его цель идёт за ключом тем же сдвигом, и сам перенос якоря гейт не включает. Пересмотр
               уровня по новому окну фактов — решение новой версии книги, а не перенос
  ставки, ЧПМ  остаток процентного дохода (ближний сдвиг модели, прочие проценты отчёта) разнесён
               по книгам активов пропорционально их доходу — ставки якоря несут весь ЧПД; ключи
               спредов от ставок якоря выводятся заново; `regimes.near_nim_shift` — так, чтобы
               ожидаемый путь ЧПМ новой книги совпал с путём прежней на ожидаемом отчёте; ось по
               ключам ближнего пути получает ключи тех же лет новой траектории
  смена года   кризисные ключи (и множитель RWA режима) сдвигаются вместе с годом шока;
               `noncore.price_base_year`
  справочное   `valuation.next_report.period`
  оси          ось вида value по одному параметру — тем же пересчётом, что параметр. Ось-связка (вид bundle,
               М§10; концы — словари «путь → значение»): конец по пути, значение которого перенос пересчитал
               (цены якоря, плотности RWA, поправки нормативов, цели и доли передачи), идёт за центром тем же
               правилом; ключи словарей концов переименовываются вместе с годом шока; связка по пути,
               пересчитанному без правила для конца, и связка по ключам ближнего пути ЧПМ — отказ.
               Строки `valuation.reverse_dcf.refine_rows` (корень уточняется на полной полосе) названы
               ключами строк — путями осей обратного расчёта — и идут за ними; строка, ось которой
               снята, из перечня уходит с предупреждением
  история     у книги с миром-опорой κ-добавки (`credit.kappa_reference_world`) добавка к стоимости риска от
               реальной ставки закрываемого квартала у нового якоря равна нулю — до сетки реальная ставка у
               миров общая (М§4.6). Это свойство ядра, а не механика: кандидат и клетки на своём пути
               сверяются с прежней книгой без этой добавки, её цена — строка разложения «история до сетки»

ЧЕГО ПЕРЕНОС НЕ ТРОГАЕТ (суждения книги — называются в предупреждениях и ручных шагах):
  цели гейтов  цель и допуск `checks.cir_lt` и прочих гейтов-целей, `checks.nim_stationary` — кроме гейта в
               мире ключа уровня маржи (см. «уровень маржи»); число каждого на прежней книге и на кандидате
               печатается рядом с допуском, сдвиг маржи разложен на маржу движка и мост. У книги без ключа
               мира уровня ключ цели ЧПМ кандидата — запись прежних скаляров пути, а не вывод из цели
               стационарной маржи: порядок нового вывода — в предупреждении
  окно фактов  коридоры и поля `checks.window_backtest` (`cor`, `cir`, `nim`, `means`, `loans_share`) —
               запись окна прежней книги: упр. числа квартала отчёта печатаются рядом с краями окна,
               продлить ли окно и пересмотреть ли по нему уровни — решение новой версии книги
  выведенное  числа книги, выведенные на ядре: перечень — ключи шаблона книги с пометкой «ВЫВЕДЕНО НА
  на ядре      ЯДРЕ» (`derived_on_core`); названо, что из них перенос переписал на новый якорь
  варианты     подмены `valuation.reference_variants`: подмена по ключу, который перенос переписал
               (ключ уровня маржи, цель передачи, доли, ближний путь, ключи спредов от ставки якоря,
               поправки нормативов, ключи года шока), называется — значение остаётся записью на прежнем якоре
  премии       ключи премий роста к сектору и ось-связка по ним; ключ закрытого квартала называется

Коды возврата: 0 — сделано; 1 — отказ (отчёт не того квартала, негодные входы, календарь дивидендов
не представим фактами якоря, запись внутри репозитория вне var/, механика вне допуска) — причина в тексте.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.book import (BOOK_BALANCE_FIELDS, BOOK_PATH, FACTS_DIR, FVOCI_FIELDS,  # noqa: E402
                        FVTPL_BOND_FIELD, FV_LOANS_FIELD, LIQUIDITY, SECURITIES, Book, BookError,
                        Facts, FactsError, anchor_facts, book_from_dict, book_roles,
                        canonical_json, load_book, load_facts)
from model.capital import growth_rule, rwa_anchor, rwa_weights  # noqa: E402
from model.cell import IEA_BASE, SEGMENT_SHARE, link_base_of, segment_weights  # noqa: E402
from model.checks import check_gates, check_invariants  # noqa: E402
from model.credit import bridge_from_facts  # noqa: E402
from model.dividends import DECLARED, THOUSAND, closed_through, history_dps, is_quarterly  # noqa: E402
from model.grid import (GridRun, LiveInputs, floor_value, live_from_book, make_context,  # noqa: E402
                        regime_expectations, run_cell, run_grid)
from model.nii import solve_transmission  # noqa: E402
from model.paths import Trajectory, get_path, has_path  # noqa: E402
from model.timeline import (parse_period, period_str, quarter_days, quarter_end,  # noqa: E402
                            quarter_start, shift_quarter, to_date)
from model.valuation import cell_norm  # noqa: E402
from model.worlds import BASE_WORLD  # noqa: E402

SCHEMA = "quarter-report/1"
TEMPLATE = BOOK_PATH.parent / "assumptions_template.yaml"
DEFAULT_OUT = ROOT / "var" / "reanchor"
WRITABLE = "var"                             # единственный каталог рабочей копии, куда инструмент пишет
OBS = "joint.regime_update.observations"
ANALYTICAL, NEUTRAL = "analytical", "macro_neutral"

TOP_REQUIRED = ("period", "balance", "interest", "dia", "pnl", "capital", "market", "mgmt")
TOP_OPTIONAL = ("schema", "as_of", "published", "source", "note", "shares", "dividend_decisions")
SECTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "balance": (("books", "loans_fvtpl", "fvoci", "fvtpl_bonds", "allowance", "other_assets",
                 "other_liabilities", "dividends_payable", "bv_common", "fvoci_reserve"),
                ("dividends_payable_year", "dividends_payable_declared", "other_assets_fixed", "at1", "nci")),
    "pnl": (("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt", "tax",
             "ni", "ni_shareholders"),
            ("misc_net", "oci_fvoci", "other_equity_movements", "estimated", "t2_premium")),
    "capital": (("n20_0", "n20_pre_dividend", "n1_1_bank", "basel_cet1", "basel_rwa",
                 "bank_base_capital"), ("t2", "estimated", "estimate")),
    "market": (("ofz_curve", "key_avg"), ("price_index",)),
    "mgmt": (("nim", "cor"), ("cir",)),
    "shares": ((), ("issued_total", "issued_ordinary", "issued_preferred", "outstanding_total",
                    "outstanding_ordinary", "outstanding_preferred", "economic_treasury")),
}
NOT_NUMBERS = ("books", "ofz_curve", "n20_pre_dividend", "dividends_payable_year", "dividends_payable_declared",
               "estimated", "estimate")
CURVE_NODES = ("1", "3", "5", "10")
# Квартальный календарь дивидендов (М§5.7): решение собрания и сумма к выплате — по кварталу прибыли.
DECISION_REQUIRED = ("period", "dps", "decided_date")
DECISION_OPTIONAL = ("record_date", "pay_date", "pool_declared", "pool_all_classes")
# pool_all_classes — сумма по всем категориям акций, вычтенная из bv_common (без поля — pool_declared): её читает база
# объёма iea квартала фактов (М§4.7); у годовой книги с этой базой раздел читается только ради строки истории (§3.9)
DECLARED_KEYS = ("period", "amount")
# Слоты нормативов, которые отчёт может нести оценкой до выхода формы (М§3.3): слот отчёта → слот фактов.
ESTIMATE_SLOTS = {"n20_0": "n20_0", "n1_1_bank": "n1_1_bank"}
ESTIMATE_KEYS = ("bank_value", "spread", "spread_as_of")
CAPITAL_FORM = "capital-form/1"              # файл замены оценки нормативов фактом формы (без смены якоря)
CAPITAL_FORM_REQUIRED = ("period", "n20_0", "n1_1_bank", "basel_cet1", "basel_rwa", "bank_base_capital")
CAPITAL_FORM_OPTIONAL = ("schema", "as_of", "published", "source", "note", "t2", "n20_pre_dividend")
PNL_SUM = ("nii", "llp_debt_fa", "fees_net", "insurance_net", "noncore_net", "opex")   # + misc_net = pbt

# Допуски СВЕРОК файла отчёта и точности переноса — параметры проверки, не допущения модели.
BALANCE_CHECK = 5.0        # млрд ₽: активы против пассивов и капитала (округление строк отчёта)
PNL_CHECK = 0.5            # млрд ₽: pbt против суммы строк, ni против pbt + tax
RESIDUAL_SHARE = 0.10      # остаток «ЧПД − проценты книг» не больше этой доли ЧПД
BASIS_SANITY = 0.01        # упр. ЧПМ и CoR против величин движка через мост: 1 п.п.
MECHANICS_TOL = 0.001      # механика: стоимость клетки на своём пути — в пределах 0,1 % нормы клетки (М§15.2)
SEGMENT_DRIFT = 0.01       # доля юрлиц нового якоря дальше этого от ключа структуры нормировки — предупреждение (1 п.п.)
SERIES_TOL = 1e-6          # ряд значения моста: |среднее по окну значения − value| не больше этого (value — шесть знаков)
LEVEL_TOL = 1e-6           # ключ уровня маржи записан шестью знаками: стационарная маржа ядра равна ему с этой точностью
GAP_TOL = 1e-9             # якорь воспроизводит норматив отчёта с этой точностью
NEAR_TOL = 1e-6            # 0,0001 п.п. ЧПМ: хвост ближней калибровки меньше — не пишется
NEAR_RANGE = 2e-4          # разброс внутри года больше 0,02 п.п. — год пишется кварталами
SPREAD_RULE_TOL = 6e-6     # ключ спреда «от ставки якоря» в книге округлён до 5 знаков
SOLVE_STEP = 0.001         # шаг пробы целей A-N2 и A-N3 (решение аффинно — шаг не важен)
PASSES = 60                # не больше стольких проходов калибровки по прогону кандидата: проход доводит путь ЧПМ
#                            на квартал дальше там, где капитал связывает рост (ЧПД → капитал → рост → ЧПМ); обычно 3–12

# Реальные суммы книги в ценах якоря: индекс цен клетки стартует с единицы на якоре (М§4.7).
PRICE_INDEXED = ("noncore.result_real", "other.misc_net_real")
NONCORE = "noncore.result_real"
# anchor-ключи, состояние которых идёт с лагом: вывод заново сдвинул бы само правило.
FROZEN_ANCHORS = ("nii.retail_current_share.c_ref", "nii.retail_current_share.key_ref",
                  "volumes.wholesale_to_funds")
DEDUCTIONS = ("capital.n20.deductions_anchor", "capital.n11.deductions_anchor")
# Доли вычета якоря, постоянные в рублях (М§4.11): (ключ доли, ключ вычета якоря своего норматива). Переносятся
# суммой в рублях — доля переписывается на вычет нового якоря (М§15.2 п. 3).
FIXED_SHARES = (("capital.n20.deductions_fixed_share", DEDUCTIONS[0]),
                ("capital.n11.deductions_fixed_share", DEDUCTIONS[1]))
DEDUCTION_DIGITS = 3                         # вычет якоря в книге-кандидате записан с этим числом знаков, млрд ₽
SHARE_DIGITS = 12                            # доля и концы её оси — с этим числом знаков: сумма в рублях сохраняется
SHARE_BOUNDS = (0.0, 1.0)                    # границы доли: конец оси и край отрезка поиска на них остаются (М§15.2 п. 3)
BOUND_TOL = 1e-12                            # конец оси-сдвига «на границе»: доля плюс приращение — граница до 1e-12
RECAP_KEY = "capital.recapitalization"       # докапитализация (М§4.14): взнос закрываемого квартала — отказ (§3.16)
SHARE_ADJ = "valuation.share_count_adj"      # поправка делителя (акции объявленного выпуска, М§8.4)
# Путь постоянной части прочих активов (М§4.3, §15.2 п. 3; пятый проход): приращение квартала нового якоря — в число
# постоянной части, траектория и концы осей на её путях — минус оно (якорное условие нового якоря).
FIXED_LEVEL = "volumes.other_assets_fixed"
FIXED_CHANGE = "volumes.other_assets_fixed_change"
FIXED_DIGITS = 9                             # млрд ₽: число постоянной части и значения пути — с этим числом знаков
GAPS = (("capital.n20.gap_pp", "n20"), ("capital.n11.gap_pp", "n11"))
DENSITY = "capital.rwa.density"
FX = "capital.rwa.fx"
NIM_TARGET, T_TARGET = "nii.nim_lt_target_mgmt", "nii.transmission.target"
SPLIT, PHI_SPLIT = "nii.sigma0_split", "nii.phi_split"
TRANSMISSION_KEYS = (NIM_TARGET, T_TARGET, SPLIT, PHI_SPLIT)
SCALARS = ("σ0_A", "σ0_L", "φ_A", "φ_L")      # скаляры пути передачи ставки (М§4.5) — порядок `_sigmas`
KEEP, RESOLVE = "keep", "resolve"            # resolve — только диагностика (М§15.2 п. 8)
TRANSMISSION_MODES = (KEEP, RESOLVE)
NEAR = "regimes.near_nim_shift"
CRISIS_TRAJECTORIES = ("cor", "nim_shift", "loan_growth_adj", "rwa_density_mult")
T2 = "capital.n20.t2"                        # траектория инструментов капитала: ключ квартала якоря — факт (М§4.11)
T2_TOL = 1e-6                                # млрд ₽: ключ квартала якоря правится, если факт отчёта отличается
CATCH_UP = "capital.growth_constraint.catch_up_rate"
DIV_TOL = 1e-6                               # млрд ₽: сверки сумм дивидендов по периодам
BUNDLE = "bundle"                            # вид оси «связка» (М§10): концы — словари «путь → значение на конце»
# Корни путей, конец оси-связки по которым инструмент переносит вместе с центром; прочий путь связки, значение
# которого перенос якоря изменил, — отказ.
BUNDLE_CARRIED = (PRICE_INDEXED + (DENSITY,) + tuple(path for path, _ in GAPS) + TRANSMISSION_KEYS
                  + tuple(share for share, _ in FIXED_SHARES) + (FIXED_LEVEL, FIXED_CHANGE))
KAPPA_WORLD = "credit.kappa_reference_world"   # мир-опора κ-добавки (М§4.6): пути CoR режимов стоят в нём
LEVEL_WORLD = "nii.transmission.level_world"   # мир, стационарную маржу которого на составе якоря задаёт ключ цели
#                                                ЧПМ (М§4.5); нет ключа — мир-опора решателя передачи, как у образца
REFINE_ROWS = "valuation.reverse_dcf.refine_rows"   # строки обратного расчёта с уточнением корня на полной полосе
PREMIUM_FACTS = "valuation.reverse_dcf.premium_facts"   # ключи времени премий роста, названные книгой фактом
NIM_STATIONARY = "checks.nim_stationary"     # гейт стационарной маржи: {world, target, tolerance} — цель-суждение
GATE_TARGET = NIM_STATIONARY + ".target"     # у гейта в мире ключа уровня маржи — то же суждение, что ключ
CIR_LT = "checks.cir_lt"                     # гейт долгосрочного C/I: {target, tolerance, from_year, scope?}
MARKET_LAYER = "market_layer"                # область гейта C/I — слой «рыночные ставки как есть»
WINDOW_BACKTEST = "checks.window_backtest"   # включает узел уровней после фазы роста
WINDOW_CORRIDORS = (("cor", "CoR"), ("cir", "C/I"))   # коридоры гейта окна: наименьший и наибольший квартал окна
WINDOW_FIELDS = ("nim", "means", "loans_share")       # необязательные поля окна фактов: маржа, средние, доля кредитов
VARIANTS ="valuation.reference_variants"    # справочные варианты: [{id, title, overrides: {путь: значение}}]
WHOLESALE_SHARE = "checks.wholesale_share"   # коридор гейта доли оптового фондирования — по счёту ядра
PREMIUMS = ("volumes.funds_share_drift", "volumes.loan_share_drift")   # премии роста к сектору — суждения книги
# Пометка шаблона книги у ключа, выведенного на ядре (до вывода и после): перечень таких чисел — по самой книге.
DERIVED_MARKS = ("ВЫВЕДЕНО НА ЯДРЕ", "ВЫВОДИТСЯ НА ЯДРЕ")

REASONS = (
    ("meta.", "якорь переходит на закрытый квартал"),
    (OBS, "факт квартала — наблюдение A-P2u с замороженными ожиданиями режимов; окно"),
    ("noncore.result_real", "цены якоря: индекс цен закрытого квартала"),
    ("other.misc_net_real", "цены якоря: индекс цен закрытого квартала"),
    ("noncore.price_base_year", "год цен — год якоря"),
    ("nii.retail_current_share.", "линия доли текущих счетов заморожена числами прежней книги"),
    ("volumes.wholesale_to_funds", "базовое оптовое фондирование заморожено числом прежней книги"),
    (SEGMENT_SHARE, "структура нормировки сегментной CoR — доля юрлиц прежнего якоря: на ней общая CoR равна пути"),
    (DENSITY, "плотности RWA — общим множителем к RWA якоря"),
    (FX, "валютная доля RWA — на новом якоре (индекс курса стартует с единицы)"),
    ("capital.n20.deductions_anchor", "вычеты капитала — формулой книги на фактах якоря"),
    ("capital.n11.deductions_anchor", "вычеты капитала — формулой книги на фактах якоря"),
    ("capital.n20.deductions_fixed_share", "доля вычета якоря, постоянная в рублях: сумма в рублях прежняя, доля — "
                                           "на вычет нового якоря"),
    ("capital.n11.deductions_fixed_share", "доля вычета якоря, постоянная в рублях: сумма в рублях прежняя, доля — "
                                           "на вычет нового якоря"),
    (FIXED_CHANGE, "путь постоянной части прочих активов — от нового якоря: приращение квартала нового якоря — в число "
                   "постоянной части"),
    (FIXED_LEVEL, "приращение пути постоянной части в квартале нового якоря — в число постоянной части"),
    ("capital.n20.gap_pp", "якорь воспроизводит Н20.0 отчёта"),
    ("capital.n11.gap_pp", "якорь воспроизводит второй норматив отчёта"),
    (T2, "ключ квартала якоря траектории инструментов капитала — факт отчёта"),
    ("nii.books.", "ключи спреда от ставок якоря (М§4.4)"),
    (NEAR, "ближняя калибровка ЧПМ: уровень уже в ставках якоря"),
    (NIM_TARGET, "A-N2 на структуре нового якоря при прежних σ0_A и σ0_L"),
    (T_TARGET, "A-N3 на структуре нового якоря при прежних φ_A и φ_L"),
    (SPLIT, "доля сдвига σ0 на активах на структуре нового якоря при прежних σ0_A и σ0_L"),
    (PHI_SPLIT, "доля сжатия φ на активах на структуре нового якоря при прежних φ_A и φ_L"),
    ("nii.sigma0_from", "год начала σ0 — не раньше первого прогнозного года"),
    ("regimes.", "кризис: ключи сдвинуты вместе с годом шока"),
    ("checks.m_crisis_vs_cbr", "кризис: ключи сдвинуты вместе с годом шока"),
    (GATE_TARGET, "цель гейта — то же суждение, что ключ уровня маржи: записана на составе нового якоря вместе с ним"),
    (REFINE_ROWS, "строки с уточнением корня названы ключами строк: идут за путями осей обратного расчёта"),
    ("valuation.next_report.period", "новый открытый квартал"),
    ("valuation.", "ось — в единицах параметра и на его ключах: пересчитана вместе с ним"),
)

Path_ = tuple                                # звенья пути: ключ словаря или ("name", имя) у элемента списка


class ReportError(ValueError):
    """Отчёт квартала или входы не годятся для перезаякоривания — объяснение в тексте."""


@dataclass
class Reanchored:
    """Кандидат и всё, что о нём надо знать до переноса в канон."""

    data: dict                               # кандидат машинной книги (anchor-ключи — строкой)
    book: Book
    facts: Facts
    period: str
    derived: dict
    changes: list[tuple[Path_, Any, Any]]    # (путь звеньями, было, стало); печать — `dotted(путь)`
    warnings: list[str] = field(default_factory=list)
    near: Any = None                         # ближняя калибровка ЧПМ (траектория книги)


# ------------------------------------------------------------------ периоды и пути


def next_period(p: str) -> str:
    return period_str(*shift_quarter(*parse_period(p), 1))


def period_end(p: str) -> dt.date:
    return quarter_end(*parse_period(p))


def pindex(p: str) -> int:
    y, q = parse_period(p)
    return 4 * y + q


def _get(tree: Any, dotted_path: str, default: Any = None) -> Any:
    node = tree
    for part in dotted_path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return default
        node = node[part]
    return node


def _set(tree: dict, dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    node = tree
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _r(x: float, digits: int = 9) -> float:
    return round(float(x), digits)


def _rounded(tree: Any, digits: int = 9) -> Any:
    if isinstance(tree, Mapping):
        return {k: _rounded(v, digits) for k, v in tree.items()}
    if isinstance(tree, float):
        return round(tree, digits)
    return tree


def _plain(tree: Any) -> Any:
    """Дерево после JSON туда-обратно: ключи — строки, даты — строки."""
    return json.loads(json.dumps(tree, default=str))


def _sorted_traj(traj: Mapping) -> dict:
    """Ключи траектории по времени, `LT` и `LT_from` — в конце (как в книге)."""
    head = sorted((k for k in traj if str(k) not in ("LT", "LT_from")), key=lambda k: (int(str(k)[:4]), str(k)))
    return {**{k: traj[k] for k in head}, **{k: traj[k] for k in ("LT", "LT_from") if k in traj}}


# ------------------------------------------------------------------ файл отчёта


def read_report(path: Path) -> dict:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReportError(f"файл отчёта {path}: {exc}") from exc
    if not isinstance(report, dict):
        raise ReportError(f"файл отчёта {path}: ожидается объект JSON")
    return report


def _fraction(value: float, where: str, lo: float = -0.5, hi: float = 1.0) -> None:
    if not lo < value < hi:
        raise ReportError(f"отчёт: {where} = {value} — ожидается доля единицы (0,062 — это 6,2 %), "
                          "а не проценты")


def _check_shape(book: Book, facts: Facts, report: Mapping) -> None:
    unknown = sorted(set(report) - set(TOP_REQUIRED) - set(TOP_OPTIONAL))
    if unknown:
        raise ReportError(f"отчёт: незнакомые ключи {', '.join(unknown)} "
                          f"(известны: {', '.join(TOP_REQUIRED + TOP_OPTIONAL)})")
    missing = [k for k in TOP_REQUIRED if k not in report]
    if missing:
        raise ReportError(f"отчёт: нет обязательных ключей {', '.join(missing)}")
    if report.get("schema", SCHEMA) != SCHEMA:
        raise ReportError(f"отчёт: schema {report['schema']!r}, ожидается {SCHEMA!r}")
    period, first = str(report["period"]), str(book.get("meta.first_period"))
    try:
        parse_period(period)
    except BookError as exc:
        raise ReportError(f"отчёт: period — {exc}") from exc
    if period != first:
        raise ReportError(
            f"отчёт за {period}, а первый прогнозный квартал книги — {first}. Перезаякоривание "
            f"идёт по одному кварталу: сначала отчёт за {first}, потом следующий")
    if pindex(period) >= pindex(str(book.get("meta.last_period"))):
        raise ReportError(f"квартал {period} — последний прогнозный книги: горизонт кончился "
                          "(продление meta.last_period — решение книги)")
    if str(facts.plain("anchor", "period")) != str(book.get("meta.anchor_period")):
        raise ReportError(f"факты на якоре {facts.plain('anchor', 'period')}, книга — на "
                          f"{book.get('meta.anchor_period')}: книга и факты не пара")
    end = period_end(period)
    if "as_of" in report and str(report["as_of"]) != end.isoformat():
        raise ReportError(f"отчёт: as_of {report['as_of']} — не конец квартала {period} ({end})")
    if "published" in report:
        try:
            published = to_date(report["published"])
        except ValueError as exc:
            raise ReportError(f"отчёт: published {report['published']!r} — не дата") from exc
        if published <= end:
            raise ReportError(f"отчёт: published {published} не позже конца квартала {end}")
    for name, (required, optional) in SECTIONS.items():
        if name not in report:
            continue
        section = report[name]
        if not isinstance(section, Mapping):
            raise ReportError(f"отчёт: {name} — словарь")
        unknown = sorted(set(section) - set(required) - set(optional))
        if unknown:
            raise ReportError(f"отчёт: {name} — незнакомые ключи {', '.join(unknown)} "
                              f"(известны: {', '.join(required + optional)})")
        missing = [k for k in required if k not in section]
        if missing:
            raise ReportError(f"отчёт: {name} — нет ключей {', '.join(missing)}")
        for key, value in section.items():
            if key not in NOT_NUMBERS and not _num(value):
                raise ReportError(f"отчёт: {name}.{key} = {value!r} — ожидается число")
    names = tuple(book.get("nii.books"))
    for where, block in (("balance.books", report["balance"]["books"]), ("interest", report["interest"])):
        if not isinstance(block, Mapping) or set(block) != set(names):
            raise ReportError(f"отчёт: {where} — словарь по книгам {', '.join(names)} (все и только они)")
        for b, v in block.items():
            if not _num(v) or v < 0:
                raise ReportError(f"отчёт: {where}.{b} = {v!r} — ожидается неотрицательное число")
    if not _num(report["dia"]):
        raise ReportError(f"отчёт: dia = {report['dia']!r} — ожидается число")
    for where, flag in (("pnl.estimated", report["pnl"].get("estimated")),
                        ("capital.estimated", report["capital"].get("estimated"))):
        if flag is not None and not isinstance(flag, bool):
            raise ReportError(f"отчёт: {where} — true или false (значение стоит оценкой до выхода точного?)")
    _check_estimate(report["capital"])
    fixed = report["balance"].get("other_assets_fixed")
    if fixed is not None and not 0 <= fixed <= report["balance"]["other_assets"]:
        raise ReportError(f"отчёт: balance.other_assets_fixed = {fixed} — постоянная часть прочих активов: от нуля "
                          f"до balance.other_assets ({report['balance']['other_assets']})")
    held = (report.get("shares") or {}).get("economic_treasury")
    if held is not None and held < 0:
        raise ReportError(f"отчёт: shares.economic_treasury = {held} — число акций, не меньше нуля")


def _check_estimate(capital: Mapping) -> None:
    """Блок оценки нормативов есть тогда и только тогда, когда нормативы стоят оценкой (М§3.3)."""
    estimated, block = capital.get("estimated") is True, capital.get("estimate")
    if estimated != (block is not None):
        raise ReportError("отчёт: capital.estimate — блок оценки нормативов: он есть тогда и только тогда, когда "
                          "capital.estimated: true")
    if block is None:
        return
    if not isinstance(block, Mapping) or set(block) != set(ESTIMATE_SLOTS):
        raise ReportError(f"отчёт: capital.estimate — словарь по слотам {', '.join(ESTIMATE_SLOTS)} (все и только они)")
    for slot, spec in block.items():
        where = f"capital.estimate.{slot}"
        if not isinstance(spec, Mapping) or set(spec) != set(ESTIMATE_KEYS):
            raise ReportError(f"отчёт: {where} — ключи {', '.join(ESTIMATE_KEYS)} (все и только они)")
        for key in ESTIMATE_KEYS[:2]:
            if not _num(spec[key]):
                raise ReportError(f"отчёт: {where}.{key} = {spec[key]!r} — ожидается число")
            _fraction(float(spec[key]), f"{where}.{key}")
        _iso(spec["spread_as_of"], f"{where}.spread_as_of")


def _iso(value: Any, where: str) -> dt.date:
    try:
        return to_date(value)
    except (ValueError, TypeError) as exc:
        raise ReportError(f"отчёт: {where} = {value!r} — не дата ГГГГ-ММ-ДД") from exc


def _check_decisions(book: Book, report: Mapping) -> set[str]:
    """Решения собраний закрываемого квартала (`dividend_decisions`): строки {period, dps, decided_date, …}, день решения
    — позже прежней даты фактов и не позже конца квартала. Возвращает кварталы прибыли решений."""
    period = str(report["period"])
    end = period_end(period)
    old_date = to_date(book.get("meta.facts_date"))
    decisions = report.get("dividend_decisions") or []
    if not isinstance(decisions, list):
        raise ReportError("отчёт: dividend_decisions — список")
    closing: set[str] = set()
    for i, row in enumerate(decisions):
        where = f"dividend_decisions.{i}"
        if not isinstance(row, Mapping):
            raise ReportError(f"отчёт: {where} — словарь {{period, dps, decided_date}}")
        unknown = sorted(set(row) - set(DECISION_REQUIRED) - set(DECISION_OPTIONAL))
        missing = [k for k in DECISION_REQUIRED if k not in row]
        if unknown or missing:
            raise ReportError(f"отчёт: {where} — " + "; ".join(x for x in (
                f"незнакомые ключи {', '.join(unknown)}" if unknown else "",
                f"нет ключей {', '.join(missing)}" if missing else "") if x)
                + f" (известны: {', '.join(DECISION_REQUIRED + DECISION_OPTIONAL)})")
        try:
            y, q = parse_period(str(row["period"]))
        except BookError as exc:
            raise ReportError(f"отчёт: {where}.period — {exc}") from exc
        if pindex(str(row["period"])) > pindex(period):
            raise ReportError(f"отчёт: {where}.period {row['period']} — квартал прибыли позже закрываемого {period}")
        if str(row["period"]) in closing:
            raise ReportError(f"отчёт: {where}.period {row['period']} повторяется")
        closing.add(str(row["period"]))
        if not _num(row["dps"]) or row["dps"] < 0:
            raise ReportError(f"отчёт: {where}.dps = {row['dps']!r} — ₽ на акцию, не меньше нуля")
        for key in ("pool_declared", "pool_all_classes"):
            if key in row and (not _num(row[key]) or row[key] < 0):
                raise ReportError(f"отчёт: {where}.{key} = {row[key]!r} — млрд ₽, не меньше нуля")
        decided = _iso(row["decided_date"], f"{where}.decided_date")
        if not old_date < decided <= end:
            raise ReportError(
                f"отчёт: {where}.decided_date {decided} — решение собрания закрываемого квартала: позже прежней "
                f"даты фактов {old_date} и не позже конца квартала {end} (более раннее решение — сначала правка "
                "фактов прежнего якоря, более позднее — запись реестра нового)")
        for key in ("record_date", "pay_date"):
            if row.get(key) is not None and _iso(row[key], f"{where}.{key}") < decided:
                raise ReportError(f"отчёт: {where}.{key} {row[key]} раньше дня решения {decided}")
    return closing


def _decided_in(facts: Facts, start: dt.date, end: dt.date) -> bool:
    """В истории дивидендов фактов (`history`, `history_before`) есть строка с днём решения в [start; end]."""
    div = facts.file("dividends")
    for key in ("history", "history_before"):
        for row in div.get(key) or []:
            day = _fact(row.get("decided_date")) if isinstance(row, Mapping) else None
            if day and start <= to_date(day) <= end:
                return True
    return False


def _check_annual_decisions(book: Book, facts: Facts, report: Mapping) -> None:
    """Годовой календарь и база объёма `iea` (М§4.7, REANCHOR §3.9): решения собрания закрываемого квартала — строки
    истории дивидендов. В квартале собрания отчёт без `dividend_decisions` при объявленном дивиденде (`dividends_payable_year`
    — год до года квартала, сумма больше нуля) и без строки истории с днём решения в квартале — отказ: дивиденд квартала
    ядро берёт по дню решения, без строки база объёма закрытого квартала не определена."""
    _check_decisions(book, report)
    period = str(report["period"])
    year, h = parse_period(period)
    if h != int(book.get("dividends.calendar.agm_quarter")) or report.get("dividend_decisions"):
        return
    B = report["balance"]
    if B.get("dividends_payable_year") != year - 1 or float(B["dividends_payable"]) <= DIV_TOL:
        return
    if _decided_in(facts, quarter_start(year, h), period_end(period)):
        return
    raise ReportError(
        f"отчёт: {period} — квартал собрания, дивиденд за {year - 1} год объявлен (balance.dividends_payable "
        f"{float(B['dividends_payable']):g}), а решение собрания не названо: нет ни dividend_decisions, ни строки истории "
        "дивидендов с днём решения в квартале — база объёма закрытого квартала не определена (М§4.7, REANCHOR §3.9)")


def _check_dividends(book: Book, facts: Facts, report: Mapping) -> None:
    """Дивиденды по периодам (квартальный календарь, М§5.7): решения собраний закрываемого квартала и
    объявленное, но не выплаченное на его конец. Громкий отказ на всём, что ядро не примет."""
    period = str(report["period"])
    end = period_end(period)
    declared = report["balance"].get("dividends_payable_declared") or []
    if not isinstance(declared, list):
        raise ReportError("отчёт: dividend_decisions и balance.dividends_payable_declared — списки")
    closing = _check_decisions(book, report)
    known = {str(_fact(r.get("period"))) for r in facts.file("dividends").get("history") or []
             if _fact(r.get("decided_date")) and to_date(_fact(r["decided_date"])) <= end}
    seen: set[str] = set()
    total = 0.0
    for i, item in enumerate(declared):
        where = f"balance.dividends_payable_declared.{i}"
        if not isinstance(item, Mapping) or set(item) != set(DECLARED_KEYS):
            raise ReportError(f"отчёт: {where} — словарь {{period, amount}}")
        try:
            parse_period(str(item["period"]))
        except BookError as exc:
            raise ReportError(f"отчёт: {where}.period — {exc}") from exc
        if str(item["period"]) in seen:
            raise ReportError(f"отчёт: {where}.period {item['period']} повторяется")
        seen.add(str(item["period"]))
        if not _num(item["amount"]) or item["amount"] < 0:
            raise ReportError(f"отчёт: {where}.amount = {item['amount']!r} — млрд ₽, не меньше нуля")
        if str(item["period"]) not in closing | known:
            raise ReportError(
                f"отчёт: {where}.period {item['period']} — объявленный дивиденд без решения: нет ни строки "
                "dividend_decisions, ни строки истории дивидендов прежних фактов с днём решения не позже конца "
                "квартала")
        total += float(item["amount"])
    if total > report["balance"]["dividends_payable"] + DIV_TOL:
        raise ReportError(f"отчёт: сумма balance.dividends_payable_declared {total:g} больше остатка "
                          f"balance.dividends_payable {report['balance']['dividends_payable']:g}")


def _fact(x: Any) -> Any:
    """Значение поля фактов: узел {v, …} или голое значение."""
    return x.get("v") if isinstance(x, Mapping) and "v" in x else x


def check_report(book: Book, facts: Facts, report: Mapping) -> None:
    """Громкий отказ на всём, что ядро прочло бы молча не так."""
    _check_shape(book, facts, report)
    B, P, C, M, G = (report[k] for k in ("balance", "pnl", "capital", "market", "mgmt"))
    quarterly = is_quarterly(book)
    if quarterly:
        _check_dividends(book, facts, report)
    elif link_base_of(book) == IEA_BASE:     # годовой календарь и база объёма iea: решения — строками истории (§3.9)
        _check_annual_decisions(book, facts, report)
    if not isinstance(C["n20_pre_dividend"], bool):
        raise ReportError("отчёт: capital.n20_pre_dividend — true или false (норматив до вычета "
                          "объявленного дивиденда из регуляторного капитала?)")
    curve = M["ofz_curve"]
    if not isinstance(curve, Mapping) or set(map(str, curve)) != set(CURVE_NODES):
        raise ReportError(f"отчёт: market.ofz_curve — узлы {', '.join(CURVE_NODES)} лет")
    for node, v in curve.items():
        if not _num(v):
            raise ReportError(f"отчёт: market.ofz_curve.{node} = {v!r} — ожидается число")
        _fraction(float(v), f"market.ofz_curve.{node}", 0.0)
    for where, value in (("market.key_avg", M["key_avg"]), ("mgmt.nim", G["nim"]), ("mgmt.cor", G["cor"]),
                         ("capital.n20_0", C["n20_0"]), ("capital.n1_1_bank", C["n1_1_bank"])):
        _fraction(float(value), where)
    if "cir" in G:
        _fraction(float(G["cir"]), "mgmt.cir", 0.0)
    if "price_index" in M and not 0.8 < float(M["price_index"]) < 1.5:
        raise ReportError(f"отчёт: market.price_index = {M['price_index']} — индекс цен квартала "
                          "(конец к началу, около 1,015), а не темп")
    if B["dividends_payable"] < 0 or B["allowance"] < 0:
        raise ReportError("отчёт: balance.dividends_payable и balance.allowance — величинами (≥ 0)")
    year = B.get("dividends_payable_year")
    if not quarterly and B["dividends_payable"] > 0 and (isinstance(year, bool) or not isinstance(year, int)):
        raise ReportError("отчёт: balance.dividends_payable > 0 — нужен dividends_payable_year "
                          "(год прибыли объявленного дивиденда)")
    if P["opex"] >= 0:
        raise ReportError(f"отчёт: pnl.opex = {P['opex']} — расходы со знаком минус, как в отчётности")
    for key in ("basel_cet1", "basel_rwa", "bank_base_capital"):
        if C[key] <= 0:
            raise ReportError(f"отчёт: capital.{key} = {C[key]} — ожидается положительное число")
    # тождества
    books = book.get("nii.books")
    roles = book_roles(books)
    af = anchor_facts(facts, books)
    bal = B["books"]
    at1, nci = float(B.get("at1", af.at1)), float(B.get("nci", af.nci))
    assets = sum(bal[b] for b in roles.assets) - B["allowance"] + B["other_assets"]
    claims = (sum(bal[b] for b in roles.liabilities) + B["other_liabilities"] + B["dividends_payable"]
              + B["bv_common"] + at1 + nci)
    if abs(assets - claims) > BALANCE_CHECK:
        raise ReportError(
            f"отчёт: баланс не сходится — активы {assets:.1f} (книги активов − резерв + прочие активы) "
            f"против пассивов и капитала {claims:.1f} (пассивы + прочие + дивиденды к выплате + "
            f"капитал + AT1 + неконтролирующие): разница {assets - claims:+.1f} млрд ₽ "
            f"(допуск {BALANCE_CHECK})")
    if B["loans_fvtpl"] < 0 or B["loans_fvtpl"] > (bal[af.fv_book] if af.fv_book else sum(bal[b] for b in roles.loans)):
        raise ReportError("отчёт: balance.loans_fvtpl — кредиты по СС внутри своей книги"
                          + (f" ({af.fv_book})" if af.fv_book else "") + ", не больше её остатка")
    if B["fvoci"] < 0 or B["fvtpl_bonds"] < 0 or B["fvoci"] + B["fvtpl_bonds"] > bal[SECURITIES] + BALANCE_CHECK:
        raise ReportError("отчёт: balance.fvoci и balance.fvtpl_bonds — части книги долговых бумаг "
                          "(неотрицательные, в сумме не больше её остатка)")
    lines = sum(P[k] for k in PNL_SUM)
    if "misc_net" in P and abs(lines + P["misc_net"] - P["pbt"]) > PNL_CHECK:
        raise ReportError(
            f"отчёт: pbt {P['pbt']} ≠ сумме строк {lines + P['misc_net']:.2f} (nii + llp_debt_fa + "
            "fees_net + insurance_net + noncore_net + opex + misc_net) — расходы со знаком минус?")
    if abs(P["pbt"] + P["tax"] - P["ni"]) > PNL_CHECK:
        raise ReportError(f"отчёт: ni {P['ni']} ≠ pbt + tax = {P['pbt'] + P['tax']:.2f} "
                          "(налог — со знаком минус)")
    income = sum(report["interest"][b] for b in roles.assets)
    booked = income - sum(report["interest"][b] for b in roles.liabilities) - abs(float(report["dia"]))
    if not income or abs(P["nii"] - booked) > RESIDUAL_SHARE * abs(P["nii"]):
        raise ReportError(
            f"отчёт: проценты книг дают {booked:.1f}, а pnl.nii — {P['nii']}: остаток "
            f"{P['nii'] - booked:+.1f} больше {RESIDUAL_SHARE:.0%} ЧПД — проценты за квартал или "
            "нарастающим итогом? все ли книги?")
    # базис: величины движка из строк отчёта против управленческих через мост
    bridge = bridge_from_facts(facts)
    eng = engine_ratios(book, facts, report)
    for name, got, mgmt, back in (("ЧПМ", eng["nim"], G["nim"], bridge.to_mgmt_nim),
                                  ("CoR", eng["cor"], G["cor"], bridge.to_mgmt_cor)):
        if abs(back(got) - mgmt) > BASIS_SANITY:
            raise ReportError(
                f"отчёт: {name} движка из строк отчёта {got:.4%} через мост — {back(got):.4%} упр., "
                f"а mgmt — {mgmt:.4%}: расхождение больше {BASIS_SANITY * 100:.0f} п.п. — ОПУ за "
                "квартал или нарастающим итогом? доля или проценты?")


def engine_ratios(book: Book, facts: Facts, report: Mapping) -> dict[str, float]:
    """ЧПМ, CoR и C/I движка закрытого квартала из строк отчёта (М§0.3, §4.6; средние остатки —
    начало и конец квартала, как в фактах)."""
    books = book.get("nii.books")
    roles = book_roles(books)
    af = anchor_facts(facts, books)
    B, P = report["balance"], report["pnl"]
    days = quarter_days(*parse_period(str(report["period"])))
    bal = B["books"]
    iea_avg = sum(af.balances[b] + bal[b] for b in roles.assets) / 2
    # кредиты по СС вычитаются, только когда ядро ведёт их отдельной частью книги (М§4.6); иначе знаменатель CoR —
    # сумма кредитных книг, а balance.loans_fvtpl отчёта — справка
    fv = af.fv_loans + B["loans_fvtpl"] if af.fv_book else 0.0
    loans_avg = (sum(af.balances[b] + bal[b] for b in roles.loans) - fv) / 2
    misc = P["misc_net"] if "misc_net" in P else P["pbt"] - sum(P[k] for k in PNL_SUM)
    income = P["nii"] + P["fees_net"] + P["insurance_net"] + misc
    return {"nim": P["nii"] / iea_avg * 365 / days, "cor": -P["llp_debt_fa"] / loans_avg * 365 / days,
            "cir": -P["opex"] / income if income else float("nan"),
            "iea_avg": iea_avg, "loans_ac_avg": loans_avg, "misc_net": misc, "days": days}


# ------------------------------------------------------------------ факты нового якоря


def _node(value: Any, calc: str) -> dict:
    return {"v": value, "calc": calc}


def _put(tree: dict, dotted_path: str, value: Any, calc: str, touched: set[str]) -> None:
    _set(tree, dotted_path, _node(value, calc))
    touched.add(dotted_path)


def _spread_total(tree: dict, fields: Sequence[str], total: float, calc: str, touched: set[str]) -> None:
    """`total` по узлам `fields` — в пропорции прежнего якоря (`null` остаётся `null`)."""
    old = {f: _get(tree, f + ".v") for f in fields}
    live = [f for f in fields if old[f] is not None]
    base = sum(float(old[f]) for f in live)
    for f in fields:
        touched.add(f)
        if old[f] is not None:
            share = float(old[f]) / base if base else 1.0 / len(live)
            _set(tree, f, _node(_r(total * share, 6), calc + " (разбивка — в пропорции прежнего якоря)"))


def _null_untouched(tree: Any, touched: set[str], keep: Sequence[str], calc: str, prefix: str = "") -> None:
    """Узлы, которых отчёт не назвал, — `null`: прежнее число под новой датой было бы ложью."""
    if not isinstance(tree, dict):
        return
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if any(path == k or path.startswith(k + ".") for k in keep):
            continue
        if isinstance(value, dict) and "v" in value and ("src" in value or "calc" in value):
            if path not in touched:
                tree[key] = _node(None, calc)
        else:
            _null_untouched(value, touched, keep, calc, path)


def _add_period_row(holder: dict, key: str, period: str, row: dict) -> None:
    """Строка периода в словарь {период: строка} или список [{period, …}] — как лежит в файле."""
    rows = holder.get(key)
    if isinstance(rows, dict):
        rows[period] = row
    elif isinstance(rows, list):
        rows[:] = [r for r in rows if not (isinstance(r, dict) and r.get("period") == period)]
        rows.append({"period": period, **row})


def _node_keys(rows: Any) -> set[str]:
    """Ключи узлов, которые несут строки по периодам (словарь {период: строка} или список строк)."""
    items = rows.values() if isinstance(rows, dict) else rows or []
    return {k for r in items if isinstance(r, dict) for k, v in r.items() if isinstance(v, dict) and "v" in v}


def _shifted(old_day: Any, old_end: dt.date, end: dt.date) -> str:
    """Дата блока на новом якоре — с тем же сдвигом от конца квартала, что в прежнем файле (форма на 1-е число
    после квартала остаётся формой на 1-е число)."""
    try:
        gap = (to_date(old_day) - old_end).days
    except (ValueError, TypeError):
        gap = 0
    return (end + dt.timedelta(days=gap if 0 <= gap <= 31 else 0)).isoformat()


BRIDGE_SERIES = ("gap", "gap_x4")            # ряды разности истории моста: act/365 и база «× 4» (М§4.6)


def _history_items(rows: Any) -> list[tuple[str, Mapping]]:
    """(период, строка) истории блока: словарь {период: строка} или список строк с `period`."""
    if isinstance(rows, dict):
        return [(str(p), r) for p, r in rows.items() if isinstance(r, Mapping)]
    return [(str(r.get("period")), r) for r in rows or [] if isinstance(r, Mapping) and r.get("period")]


def value_series(block: Mapping, window: Sequence | None) -> tuple[str, str]:
    """Ряд значения моста (М§4.6, REANCHOR §3.8): ряд истории блока (`gap` — на счёте дней act/365, `gap_x4` — на базе
    «× 4»), чьё среднее по окну значения `window` равно значению блока с точностью записи, |среднее − value| ≤
    `SERIES_TOL`. Если условию отвечают оба ряда или ни один (значение — медиана или записано иначе) — прежнее
    правило: `gap_x4`, если он есть в истории, иначе `gap`. Возвращает ряд и правило словами."""
    rows = block.get("history")
    have = _node_keys(rows)
    old = "gap_x4" if "gap_x4" in have else "gap"
    value = _fact(block.get("value"))
    if not _num(value) or window is None:
        return old, "прежнее правило (нет значения или окна)"
    lo, hi = pindex(str(window[0])), pindex(str(window[1]))
    fit, means = [], {}
    for name in BRIDGE_SERIES:
        if name not in have:
            continue
        vals = [_fact(r.get(name)) for p, r in _history_items(rows) if lo <= pindex(p) <= hi]
        if not vals or not all(_num(v) for v in vals):
            continue
        mean = sum(float(v) for v in vals) / len(vals)
        means[name] = mean
        if abs(mean - float(value)) <= SERIES_TOL:
            fit.append(name)
    if len(fit) == 1:
        return fit[0], f"ряд значения: среднее {fit[0]} по окну {window[0]}–{window[1]} равно значению"
    got = ", ".join(f"среднее {k} {v:+.6f}" for k, v in means.items())
    return old, (f"прежнее правило: значению {float(value):+.6f} " + ("отвечают оба ряда" if fit else "не отвечает ни один ряд")
                 + (f" ({got})" if got else ""))


def facts_after(book: Book, facts: Facts, report: Mapping, *, update_bridge: bool = True,
                series_notes: dict | None = None) -> Facts:
    """Факты нового якоря из отчёта квартала: те же файлы, узлы якоря — из отчёта.

    Форма файлов — как лежит в прежних фактах: остатки книг прямыми узлами `balance.books.<b>` или суммой
    строк; строки истории (баланс, капитал, мосты) несут те же ключи, что прежние строки. Ставки якоря несут
    весь ЧПД: остаток `nii − (проценты книг − взносы АСВ)` разнесён по книгам активов пропорционально их
    процентному доходу (М§15.2 п. 4). Упр. факты квартала входят в историю моста упр. ↔ движок (отчётные
    кварталы года якоря ядро берёт оттуда, М§4.6); среднее моста продлевается закрытым кварталом при
    `update_bridge` — уровнем в ряду значения (`value_series`; ряд и правило по блокам — в `series_notes`). При
    квартальном календаре дивидендов решения закрываемого квартала становятся строками истории дивидендов,
    объявленное и не выплаченное — списком по периодам, записи реестра переходят в затравку нового якоря (М§15.2
    п. 9); у годовой книги с базой объёма `iea` решения отчёта — только строками истории (М§4.7, REANCHOR §3.9)."""
    period = str(report["period"])
    end = period_end(period)
    tag = f"reanchor: отчёт {period}" + (f" ({report['source']})" if report.get("source") else "")
    absent = f"reanchor: в отчёте {period} нет — пересобрать build_facts.py --anchor {period}"
    books = book.get("nii.books")
    roles = book_roles(books)
    old = anchor_facts(facts, books)
    old_period = str(facts.plain("anchor", "period"))
    old_end = period_end(old_period)
    quarterly = is_quarterly(book)
    files = copy.deepcopy(dict(facts.files))
    B, P, C, M, G = (report[k] for k in ("balance", "pnl", "capital", "market", "mgmt"))
    eng = engine_ratios(book, facts, report)
    days = int(eng["days"])
    at1, nci = float(B.get("at1", old.at1)), float(B.get("nci", old.nci))

    files["anchor"]["as_of"] = end.isoformat()
    files["anchor"]["period"] = period

    # --- баланс
    bal = files["balance"]
    touched: set[str] = set()
    bal["as_of"] = end.isoformat()
    direct = bal.get("books") if isinstance(bal.get("books"), dict) else None
    for name in roles.names:
        total = float(B["books"][name])
        if direct is not None and name in direct:
            _put(bal, f"books.{name}", total, tag, touched)
            continue
        fields = list(BOOK_BALANCE_FIELDS[name])
        if FV_LOANS_FIELD in fields:
            _put(bal, FV_LOANS_FIELD, float(B["loans_fvtpl"]), tag, touched)
            fields.remove(FV_LOANS_FIELD)
            total -= float(B["loans_fvtpl"])
        if name == SECURITIES:
            _spread_total(bal, list(FVOCI_FIELDS), float(B["fvoci"]), tag, touched)
            _put(bal, FVTPL_BOND_FIELD, float(B["fvtpl_bonds"]), tag, touched)
            fields = [f for f in fields if f not in FVOCI_FIELDS and f != FVTPL_BOND_FIELD]
            total -= float(B["fvoci"]) + float(B["fvtpl_bonds"])
        _spread_total(bal, fields, total, tag, touched)
    if direct is not None and SECURITIES in direct:
        # прямые книги: части книги долговых бумаг и кредиты по СС ядро и выпуск читают своими узлами
        _spread_total(bal, list(FVOCI_FIELDS), float(B["fvoci"]), tag, touched)
        _put(bal, FVTPL_BOND_FIELD, float(B["fvtpl_bonds"]), tag, touched)
    if FV_LOANS_FIELD not in touched and isinstance(bal.get(FV_LOANS_FIELD), dict):
        _put(bal, FV_LOANS_FIELD, float(B["loans_fvtpl"]), tag, touched)
    sign = -1.0 if (_get(bal, "allowance_ac.v") or 0.0) < 0 else 1.0     # знак — как в прежнем файле
    _put(bal, "allowance_ac", sign * float(B["allowance"]), tag, touched)
    for key, name in (("other_assets", "other_assets"), ("other_liabilities", "other_liabilities"),
                      ("dividends_payable", "dividends_payable"), ("equity.bv_common", "bv_common")):
        _put(bal, key, float(B[name]), tag, touched)
    _put(bal, "equity.at1", at1, tag, touched)
    _put(bal, "equity.nci", nci, tag, touched)
    if "other_assets_fixed" in B:
        _put(bal, "other_assets_fixed", float(B["other_assets_fixed"]), tag, touched)
    elif _get(bal, "other_assets_fixed.v") is not None:
        _put(bal, "other_assets_fixed", float(bal["other_assets_fixed"]["v"]),
             f"reanchor: в отчёте {period} нет — значение прежнего якоря {old_period}", touched)
    if quarterly:
        bal["dividends_payable_declared"] = [{"period": str(x["period"]), "amount": _node(float(x["amount"]), tag)}
                                             for x in B.get("dividends_payable_declared") or []]
    elif B.get("dividends_payable_year") is not None:
        bal["dividends_payable_year"] = int(B["dividends_payable_year"])
    loans = sum(float(B["books"][b]) for b in roles.loans)
    funds = sum(float(B["books"][b]) for b in roles.funds)
    iea = sum(float(B["books"][b]) for b in roles.assets)
    fv_part = float(B["loans_fvtpl"]) if old.fv_book else 0.0            # часть книги, которую ядро ведёт по СС
    assets = iea - float(B["allowance"]) + float(B["other_assets"])
    totals = {"equity.total": B["bv_common"] + at1 + nci, "equity.shareholders": B["bv_common"] + at1,
              "equity.fvoci_reserve": B["fvoci_reserve"], "loans_ac_gross.total": loans - B["loans_fvtpl"],
              "securities.debt_total": B["books"][SECURITIES], "liquidity.total": B["books"][LIQUIDITY],
              "total_assets": assets, "total_liabilities": assets - (B["bv_common"] + at1 + nci), "iea": iea}
    for key, value in totals.items():
        if isinstance(_get(bal, key), dict):
            _put(bal, key, _r(value, 6), tag, touched)
    if parse_period(period)[0] != parse_period(old_period)[0] and isinstance(bal.get("prev_year_end"), dict):
        prev = bal["prev_year_end"]            # новый год якоря: концы прошлого года — прежний якорь
        if "as_of" in prev:
            prev["as_of"] = old_end.isoformat()
        for seg in ("corporate", "retail"):
            total = sum(old.balances[b] for b in roles.loans if books[b]["cor_segment"] == seg)
            prev[f"loans_{seg}"] = _node(_r(total, 6), f"reanchor: книги сегмента на конец {old_period}")
    _null_untouched(bal, touched, ("history", "prev_year_end"), absent)
    rows = bal.get("history")
    carried = _node_keys(rows) & {"loans", "funds"}      # базы объёма: рост объёма г/г читает их с концов кварталов (М§4.7)
    listed = set(rows) if isinstance(rows, dict) else {r.get("period") for r in rows or [] if isinstance(r, dict)}
    if rows is not None and old_period not in listed:
        # конец прежнего якоря уходит в историю: по концам отчётных кварталов ядро взвешивает год якоря (М§4.6)
        was = f"reanchor: состояние прежнего якоря {old_period}"
        old_loans = sum(old.balances[b] for b in roles.loans)
        bases = {"loans": old_loans, "funds": sum(old.balances[b] for b in roles.funds)}
        _add_period_row(bal, "history", old_period, {
            "date": old_end.isoformat(),
            "loans_ac_gross": _node(_r(old_loans - old.fv_loans, 6), was),
            "bv_common": _node(float(old.bv), was),
            "iea": _node(_r(sum(old.balances[b] for b in roles.assets), 6), was),
            **{k: _node(_r(bases[k], 6), was) for k in sorted(carried)}})
    bases = {"loans": loans, "funds": funds}
    _add_period_row(bal, "history", period, {
        "date": end.isoformat(), "loans_ac_gross": _node(_r(loans - fv_part, 6), tag),
        "allowance_ac": _node(float(B["allowance"]), tag), "loans_fvtpl": _node(float(B["loans_fvtpl"]), tag),
        "bv_common": _node(float(B["bv_common"]), tag), "iea": _node(_r(iea, 6), tag),
        "total_assets": _node(_r(assets, 6), tag),
        **{k: _node(_r(bases[k], 6), tag) for k in sorted(carried)}})

    # --- книги ЧПД: ставки якоря несут весь ЧПД
    nb = files["nii_books"]
    nb["as_of"] = end.isoformat()
    if "period" in nb:
        nb["period"] = period
    if "rates_carry_residual" in nb:
        nb["rates_carry_residual"] = True
    touched = set()
    interest = {b: float(report["interest"][b]) for b in roles.names}
    income = sum(interest[b] for b in roles.assets)
    expense = sum(interest[b] for b in roles.liabilities)
    dia = abs(float(report["dia"]))
    # надбавка за субординацию отчёта (`pnl.t2_premium`, у ожидаемого отчёта книги с ключом надбавки) — процентный расход
    # вне книг: в остаток, который несут ставки нового якоря, она не входит — её продолжает ключ (М§15.2 п. 3)
    residual = float(P["nii"]) + float(P.get("t2_premium") or 0.0) - (income - expense - dia)
    scale = 1.0 + residual / income
    prefix = "books." if isinstance(nb.get("books"), dict) else ""
    for b in roles.names:
        avg = (old.balances[b] + float(B["books"][b])) / 2
        carried_interest = interest[b] * (scale if b in roles.assets else 1.0)
        entry = _get(nb, f"{prefix}{b}") or {}
        for key, value in (("balance_open", old.balances[b]), ("balance_close", float(B["books"][b])),
                           ("balance_avg", avg), ("interest_q", interest[b])):
            if key in entry:
                _put(nb, f"{prefix}{b}.{key}", _r(value, 6), tag, touched)
        _put(nb, f"{prefix}{b}.rate_anchor", _r(carried_interest / avg * 365 / days) if avg else 0.0,
             tag + ": проценты книги" + (" с долей остатка ЧПД" if b in roles.assets else "")
             + f" / средний остаток × 365/{days}", touched)
    retail = sum(float(B["books"][b]) for b in roles.retail)
    for key, value in (("dia_q", dia), ("nim_eng_q", eng["nim"]), ("key_avg_anchor_q", float(M["key_avg"])),
                       ("current_share_anchor", float(B["books"][roles.retail[0]]) / retail)):
        _put(nb, key, _r(value), tag, touched)
    for key, value in (("nii_q", float(P["nii"])), ("iea_avg", eng["iea_avg"]), ("days", days),
                       ("other_interest_net_q", residual),
                       ("interest_loans_q", sum(interest[b] for b in roles.loans)),
                       ("interest_assets_q", income), ("interest_liabilities_q", expense)):
        if isinstance(nb.get(key), dict):
            _put(nb, key, value if isinstance(value, int) else _r(value, 6), tag, touched)
    _null_untouched(nb, touched, (), absent)

    # --- ОПУ квартала
    pnl = files["pnl_quarterly"]
    pnl["as_of"] = end.isoformat()
    rows = pnl.get("quarters")
    last = (rows.get(old_period) if isinstance(rows, dict)
            else next((r for r in rows or [] if isinstance(r, dict) and r.get("period") == old_period), None)) or {}
    row = {k: _node(None, absent) for k, v in last.items() if isinstance(v, dict) and "v" in v}
    values = {k: float(P[k]) for k in SECTIONS["pnl"][0]}
    magnitude = (_get(last, "dia.v") or -1.0) > 0                        # знак взносов — как в прежнем файле
    values.update(misc_net=eng["misc_net"], key_avg=float(M["key_avg"]), dia=dia if magnitude else -dia)
    if "ni_nci" in last:
        values["ni_nci"] = float(P["ni"]) - float(P["ni_shareholders"])
    for key in ("oci_fvoci", "other_equity_movements"):
        if key in P:
            values[key] = float(P[key])
    for key, value in values.items():
        row[key] = _node(_r(value), tag)
    if P.get("estimated") is True:           # прибыль квартала — напечатанное значение: точное придёт позже
        for key in ("ni_shareholders", "ni", "ni_nci", "pbt", "tax", "misc_net", "noncore_net"):
            if key in row and row[key]["v"] is not None:
                row[key]["estimated"] = True
    _add_period_row(pnl, "quarters", period, row)

    # --- капитал и нормативы
    cap = files["capital"]
    cap["as_of"] = end.isoformat()
    touched = set()
    estimated = C.get("estimated") is True
    _put(cap, "basel.cet1", float(C["basel_cet1"]), tag, touched)
    _put(cap, "basel.rwa", float(C["basel_rwa"]), tag, touched)
    if isinstance(_get(cap, "basel.cet1_ratio"), dict):
        _put(cap, "basel.cet1_ratio", _r(C["basel_cet1"] / C["basel_rwa"], 6), tag, touched)
    _put(cap, "n20_0.value", float(C["n20_0"]), tag, touched)
    cap["n20_0"]["pre_dividend"] = bool(C["n20_pre_dividend"])
    cap["n20_0"].pop("pre_dividend_note", None)
    _put(cap, "n1_1_bank.value", float(C["n1_1_bank"]), tag, touched)
    _put(cap, "bank_base_capital", float(C["bank_base_capital"]), tag, touched)
    _put(cap, "fvoci_reserve", float(B["fvoci_reserve"]), tag, touched)
    if "t2" in C:
        _put(cap, "t2_recognized", float(C["t2"]), tag, touched)
    for node in CURVE_NODES:
        _put(cap, f"ofz_curve_anchor.{node}", float(M["ofz_curve"][node]), tag, touched)
    kept = ["at1", "history", "t2_recognized"]
    for slot, name in ESTIMATE_SLOTS.items():
        block = cap[name]
        if estimated:                        # норматив стоит оценкой до выхода формы (М§3.3)
            block["estimated"] = True
            block["value"]["estimated"] = True
            block["estimate"] = {k: (str(v) if k == ESTIMATE_KEYS[2] else _node(float(v), tag))
                                 for k, v in C["estimate"][slot].items()}
            kept.append(f"{name}.estimate")
        else:
            if "estimated" in block:
                block["estimated"] = False
            block.pop("estimate", None)
    if estimated:
        for path in ("basel.cet1", "basel.rwa", "basel.cet1_ratio", "bank_base_capital"):
            if isinstance(_get(cap, path), dict):
                _get(cap, path)["estimated"] = True
    for name in ("basel", "n20_0", "ofz_curve_anchor", "n1_1_bank"):
        if "as_of" in cap.get(name, {}):     # сдвиг даты блока от конца квартала — как в прежнем файле
            cap[name]["as_of"] = _shifted(cap[name]["as_of"], old_end, end)
    _null_untouched(cap, touched, tuple(kept), absent)
    t2_now = float(C["t2"]) if "t2" in C else old.t2
    known = {"n20_0": float(C["n20_0"]), "cet1": float(C["basel_cet1"]), "rwa": float(C["basel_rwa"]),
             "n1_1_bank": float(C["n1_1_bank"]), "n20_1": float(C["n1_1_bank"]),
             "capital_base": float(C["bank_base_capital"]), "capital_additional": t2_now,
             "capital_total": None if t2_now is None else float(C["basel_cet1"]) + t2_now,
             "rwa_imputed": float(C["basel_rwa"])}
    have = _node_keys(cap.get("history"))
    names = [k for k in known if k in have] or ["n20_0", "cet1", "rwa", "n1_1_bank"]
    line = {"date": end.isoformat(), **{k: _node(None if known[k] is None else _r(known[k]), tag) for k in names}}
    if estimated:
        for k in names:
            line[k]["estimated"] = True
    _add_period_row(cap, "history", period, line)

    # --- акции
    if "shares" in report:
        files["shares"]["as_of"] = end.isoformat()
        for key, value in report["shares"].items():
            files["shares"][key] = _node(float(value), tag)

    # --- дивиденды по периодам; у годовой книги с базой объёма iea — только строки истории решений (М§4.7, §3.9)
    if quarterly:
        _carry_dividends(files, book, old, report, tag)
    elif link_base_of(book) == IEA_BASE and report.get("dividend_decisions"):
        files["dividends"]["as_of"] = end.isoformat()
        _decision_rows(files["dividends"], old, report, tag, sort=False)

    # --- мост упр. ↔ МСФО: упр. факт закрытого квартала — в историю всегда (год якоря в упр. базисе
    #     собирается из отчётных кварталов, М§4.6); среднее по окну продлевается при `update_bridge`
    br = files["bridge_mgmt_ifrs"]
    br["as_of"] = end.isoformat()
    window = br.get("window")
    in_window = isinstance(window, list) and len(window) == 2
    count0 = pindex(old_period) - pindex(str(window[0])) + 1 if in_window else 0
    old_year, new_year = parse_period(old_period)[0], parse_period(period)[0]
    for x in ("cor", "nim", "cir"):
        if x not in G:
            continue
        block = br[x]
        additive = block["method"] == "additive"
        gap = eng[x] - float(G[x]) if additive else eng[x] / float(G[x])
        have = _node_keys(block.get("history"))
        line = {"mgmt": _node(float(G[x]), tag), "engine": _node(_r(eng[x]), tag),
                "gap": _node(_r(gap), "engine − mgmt" if additive else "engine / mgmt")}
        if "engine_books" in have:           # вариант на знаменателе движка: сумма кредитных книг — он же engine
            line["engine_books"] = _node(_r(eng[x]), tag)
            line["gap_books"] = _node(_r(gap), "engine_books − mgmt" if additive else "engine_books / mgmt")
        level_x4 = None
        if "gap_x4" in have:                 # база «× 4» без ряби счёта дней
            x4 = eng[x] * 4 * days / 365
            level_x4 = x4 - float(G[x]) if additive else x4 / float(G[x])
            line["engine_x4"] = _node(_r(x4), tag + ": × 4 вместо × 365/" + str(days))
            line["gap_x4"] = _node(_r(level_x4), "engine_x4 − mgmt" if additive else "engine_x4 / mgmt")
        own = block.get("window") if isinstance(block.get("window"), list) and len(block["window"]) == 2 else None
        # уровень закрытого квартала — в ряду значения: тот ряд истории, чьё среднее по окну значения равно value (М§4.6)
        series, rule = value_series(block, own if own is not None else window if in_window else None)
        level = level_x4 if series == "gap_x4" else gap      # разность, по которой продлевается value моста
        if series_notes is not None:
            series_notes[x] = {"series": series, "rule": rule}
        # окно значения — отчётные кварталы года якоря: начинается с первого квартала года и не совпадает с окном файла
        yearly = (own is not None and in_window and str(own[0]) != str(window[0])
                  and parse_period(str(own[0])) == (old_year, 1))
        count = int(_get(block, "n.v") or count0)
        if update_bridge and yearly and new_year != old_year:
            block["value"] = _node(_r(level), f"reanchor: окно значения — отчётные кварталы года якоря: {period} (n = 1)")
            block["window"] = [period, period]
            count = 0
        elif update_bridge and count:
            value = (float(block["value"]["v"]) * count + level) / (count + 1)
            block["value"] = _node(_r(value), f"reanchor: среднее по окну с {period} (n = {count + 1})")
            if own is not None:
                block["window"] = [own[0], period]
        if update_bridge and (count or yearly):
            if isinstance(block.get("n"), dict):
                block["n"] = _node(count + 1, "кварталов в окне")
            if isinstance(block.get("sd"), dict):
                block["sd"] = _node(None, absent)
            if isinstance(block.get("value_books"), dict):
                block["value_books"] = dict(block["value"])
            if isinstance(block.get("value_ac_only"), dict):
                block["value_ac_only"] = _node(None, absent)
        if isinstance(block.get("history"), list):
            _add_period_row(block, "history", period, line)
    if update_bridge and in_window:
        br["window"] = [window[0], period]

    # --- упр. метрики квартала
    mq = files.get("mgmt_quarterly")
    if isinstance(mq, dict) and isinstance(mq.get("quarters"), (dict, list)):
        mq["as_of"] = end.isoformat()
        _add_period_row(mq, "quarters", period, {k: _node(float(v), tag) for k, v in G.items()})

    return Facts(root=Path(f"reanchor-{period}"), files=files,
                 digest=hashlib.sha256(canonical_json(files)).hexdigest())


def _decision_rows(div: dict, old: Any, report: Mapping, tag: str, *, sort: bool = True) -> None:
    """Решения собраний закрываемого квартала (`dividend_decisions` отчёта) — строками истории дивидендов
    `dividends.json → history`: квартал прибыли, DPS, сумма на размещённые акции (`pool_declared`, без поля — DPS ×
    размещённые), сумма всех категорий акций (`pool_all_classes`, если отчёт её несёт: её читает база объёма `iea`,
    М§4.7), день решения и даты реестра. `sort` — строки истории по кварталам прибыли (у квартального календаря)."""
    history = div.setdefault("history", [])
    by_period = {str(_fact(r.get("period"))): r for r in history if isinstance(r, dict)}
    for d in report.get("dividend_decisions") or []:
        p, dps = str(d["period"]), float(d["dps"])
        pool = float(d["pool_declared"]) if "pool_declared" in d else dps * old.n_iss / THOUSAND
        row = by_period.get(p)
        if row is None:
            row = {"year": parse_period(p)[0], "period": p}
            history.append(row)
            by_period[p] = row
        same = history_dps(row) is not None and abs(history_dps(row) - dps) <= DIV_TOL
        if not same:                         # строка истории несёт решение отчёта; прежние источники — не о нём
            row["dps"] = _node(dps, tag)
            row["pool_declared"] = _node(_r(pool, 6), tag + ": DPS × размещённые акции" if "pool_declared" not in d else tag)
        elif not isinstance(row.get("pool_declared"), dict) or row["pool_declared"].get("v") is None:
            row["pool_declared"] = _node(_r(pool, 6), tag)
        if "pool_all_classes" in d:          # сумма, вычтенная из bv_common: база объёма iea квартала фактов (М§4.7)
            row["pool_all_classes"] = _node(_r(float(d["pool_all_classes"]), 9), tag)
        row["decided_date"] = str(d["decided_date"])
        for key in ("record_date", "pay_date"):
            if d.get(key) is not None:
                row[key] = str(d[key])
    if sort:
        history.sort(key=lambda r: pindex(str(_fact(r.get("period")))))


def _carry_dividends(files: dict, book: Book, old: Any, report: Mapping, tag: str) -> None:
    """Квартальный календарь (М§15.2 п. 9): решения собраний закрываемого квартала — строками истории
    дивидендов (они закрывают свои кварталы прибыли на новом якоре); записи реестра — в затравку нового
    якоря, пока их экс-дата впереди или их сумма стоит в списке «объявлено, не выплачено»."""
    period = str(report["period"])
    end = period_end(period)
    div = files["dividends"]
    div["as_of"] = end.isoformat()
    seed = [r for r in div.get("register_seed") or [] if isinstance(r, dict)]
    seeded = {str(_fact(r.get("period"))) for r in seed}
    _decision_rows(div, old, report, tag)
    for d in report.get("dividend_decisions") or []:
        p, dps = str(d["period"]), float(d["dps"])
        # решение с датой реестра позже нового якоря: дивиденд уже вычтен из капитала якоря, а акционеру ещё
        # причитается — запись реестра держит его в мосте до экс-даты (М§8.1)
        if d.get("record_date") is not None and to_date(d["record_date"]) > end and p not in seeded:
            seed.append({"year": parse_period(p)[0], "period": p, "dps": _node(dps, tag), "status": "declared",
                         "decided_date": str(d["decided_date"]), "record_date": str(d["record_date"]),
                         "ex_date": str(d["record_date"]),
                         **({"pay_date": str(d["pay_date"])} if d.get("pay_date") is not None else {}),
                         "sources": [f"manual: отчёт квартала {period}"]})
            seeded.add(p)
    unpaid = {str(x["period"]) for x in report["balance"].get("dividends_payable_declared") or []}

    def alive(rec: Mapping) -> bool:
        ex = _fact(rec.get("ex_date")) or _fact(rec.get("record_date"))
        return str(_fact(rec.get("period"))) in unpaid or ex is None or to_date(ex) > end

    if "register_seed" in div or seed:
        div["register_seed"] = [r for r in seed if alive(r)]


# ------------------------------------------------------------------ шаги переноса книги


def _scale_traj(traj: Any, factor: float) -> Any:
    if _num(traj):
        return _r(traj * factor, 6)
    return {k: (v if str(k) == "LT_from" else _r(float(v) * factor, 6)) for k, v in traj.items()}


def _explicit_from(traj: Mapping, year: int) -> dict:
    """Та же траектория с явными ключами лет от `year` до начала LT-уровня: правка ключа года
    не должна сдвигать соседние интерполированные годы."""
    t = Trajectory(traj)
    stop = max([int(k) for k in map(str, traj) if k.isdigit()] + [year])
    if "LT_from" in traj and "LT" in traj:
        stop = max(stop, int(traj["LT_from"]) - 1)
    out = dict(traj)
    for y in range(year, stop + 1):
        out.setdefault(str(y), _r(t.year_value(y)))
    return _sorted_traj(out)


def _axis_lists(X: dict) -> list[tuple[str, list, tuple[str, ...]]]:
    V = X["valuation"]
    return [("valuation.uncertainty.axes", V["uncertainty"].get("axes") or [], ("low", "high")),
            ("valuation.uncertainty.off_band_axes", V["uncertainty"].get("off_band_axes") or [], ("low", "high")),
            ("valuation.reverse_dcf.axes", V["reverse_dcf"].get("axes") or [], ("search", "range"))]


def _value_axes(X: dict, path: str) -> list[tuple[dict, tuple[str, ...]]]:
    """Оси вида value по одному параметру `path` (полоса, оси вне полосы, обратный расчёт)."""
    return [(axis, keys) for _, axes, keys in _axis_lists(X) for axis in axes
            if axis.get("kind") == "value" and [str(p) for p in axis.get("paths") or []] == [path]]


def _under(path: str, roots: Sequence[str]) -> bool:
    return any(path == r or path.startswith(r + ".") for r in roots)


def _move_axis(axis: dict, keys: Sequence[str], move) -> None:
    for key in keys:
        value = axis.get(key)
        if _num(value):
            axis[key] = move(value)
        elif isinstance(value, list) and value and all(_num(v) for v in value):
            axis[key] = [move(v) for v in value]


def _scale_axes(X: dict, roots: Sequence[str], factor: float) -> None:
    """Оси по параметрам `roots` — тем же множителем, что и сами параметры: диапазон суждения
    задан в единицах параметра. Ось, которая двигает их вместе с другими, одним множителем не
    перевести — отказ. Ось-связка сюда не входит: её концы заданы по путям и идут за своим центром
    (`_bundle_centers`, `_follow_centers`)."""
    for where, axes, keys in _axis_lists(X):
        for axis in axes:
            if axis.get("kind") == BUNDLE:
                continue
            paths = [str(p) for p in axis.get("paths") or []]
            hit = [p for p in paths if _under(p, roots)]
            if not hit:
                continue
            if len(hit) != len(paths):
                raise ReportError(
                    f"{where} «{axis.get('name')}»: ось двигает {', '.join(paths)} — пересчитываемые "
                    f"({', '.join(hit)}) вместе с другими; разделить ось (решение книги)")
            _move_axis(axis, keys, lambda v: _r(v * factor, 6))


def _remap_axes(X: dict, path: str, was: float, now: float, slope: float = 1.0,
                bounds: tuple[float, float] | None = None) -> None:
    """Ось вида value по одному параметру — тем же пересчётом, что и параметр: значение оси v
    переходит в `now + slope × (v − was)` (сдвиг при slope = 1). `bounds` — область определения:
    конец оси, стоящий на её границе, остаётся на границе, прочие из неё не выходят."""
    def move(v: float) -> float:
        if bounds is not None and v in bounds:
            return v
        v = _r(now + slope * (v - was))
        return v if bounds is None else min(bounds[1], max(bounds[0], v))
    for axis, keys in _value_axes(X, path):
        _move_axis(axis, keys, move)
    _move_bundle_ends(X, path, move)


def _leaf(tree: Any, dotted_path: str) -> Any:
    """Значение книги по точечному пути оси (ключ траектории — строкой или числом); нет пути — None."""
    return get_path(tree, dotted_path) if has_path(tree, dotted_path) else None


def _bundles(X: dict) -> list[tuple[str, dict, tuple[str, ...]]]:
    """Оси-связки книги (вид `bundle`, М§10): (где, ось, ключи концов)."""
    return [(where, axis, keys) for where, axes, keys in _axis_lists(X) for axis in axes if axis.get("kind") == BUNDLE]


def _move_bundle_ends(X: dict, path: str, move) -> None:
    """Концы осей-связок по пути `path` — правилом `move` (тем же, что у оси вида `value` по этому пути)."""
    for _, axis, keys in _bundles(X):
        for key in keys:
            ends = axis.get(key)
            if isinstance(ends, dict) and _num(ends.get(path)):
                ends[path] = move(ends[path])


def _bundle_centers(X: dict, roots: Sequence[str]) -> dict[str, Any]:
    """Центры осей-связок по путям под `roots` — значения книги ДО пересчёта: {путь: значение}. Связка применяется
    приращением к значению книги (М§10), поэтому её конец идёт за центром — `_follow_centers`."""
    return {p: _leaf(X, p) for _, axis, _ in _bundles(X) for p in map(str, axis.get("paths") or []) if _under(p, roots)}


def _follow_centers(X: dict, centers: Mapping[str, Any], slope: float, digits: int = 6) -> None:
    """Концы осей-связок после пересчёта центров: конец v пути переходит в `стало + slope × (v − было)` — то же
    правило, что у оси вида `value`; у чистого множителя это `v × slope`, у суммы года якоря, закрытой остатком
    к факту, — сдвиг вместе с центром и множитель на отклонение от него."""
    for path, was in centers.items():
        now = _leaf(X, path)
        if not _num(was) or not _num(now):
            raise ReportError(f"ось-связка: путь {path} после пересчёта — не число ({was!r} → {now!r}); концы оси "
                              "перенести нечем (решение книги)")
        _move_bundle_ends(X, path, lambda v, was=was, now=now: _r(now + slope * (v - was), digits))


def check_bundles(X: dict, old: Mapping, renamed: Mapping[str, str] | None = None) -> None:
    """Сторож осей-связок: путь связки, значение которого перенос якоря изменил, обязан иметь правило переноса
    конца (`BUNDLE_CARRIED`); иначе центр ушёл бы, а концы остались — молча. `renamed` — ключи, переименованные
    вместе с годом шока: {прежний путь: новый}."""
    back = {new: was for was, new in (renamed or {}).items()}
    for where, axis, _ in _bundles(X):
        for path in map(str, axis.get("paths") or []):
            if _under(path, BUNDLE_CARRIED):
                continue
            was, now = _leaf(old, back.get(path, path)), _leaf(X, path)
            if was != now:
                raise ReportError(
                    f"{where} «{axis.get('name')}»: ось-связка двигает {path}, а перенос якоря его пересчитал "
                    f"({_fmt(was)} → {_fmt(now)}): правила переноса конца оси по этому пути нет — концы задаёт книга "
                    "(решение книги: снять путь с оси или задать концы на новом якоре)")


def reindex_prices(X: dict, facts: Facts, period: str, factor: float) -> None:
    """Реальные суммы книги — из цен прежнего якоря в цены нового (М§15.2 п. 2).

    Сумма непрофильного результата года якоря закрывается остатком к факту (М§0.3): индексируется
    только остаток года, `S' = F + (S − F) × индекс`, F — факт отчётных кварталов прежней книги."""
    year = parse_period(period)[0]
    reported = 0.0
    centers = _bundle_centers(X, PRICE_INDEXED)
    for per, row in facts.periods("pnl_quarterly").items():
        if parse_period(per)[0] == year and pindex(per) < pindex(period):
            value = _get(row, "noncore_net.v")
            if value is None:
                raise ReportError(f"факты: pnl_quarterly.{per}.noncore_net — null, а год якоря "
                                  "непрофильного результата закрывается остатком к факту (М§0.3)")
            reported += float(value)
    for path in PRICE_INDEXED:
        traj = _get(X, path)
        if path == NONCORE and reported:
            if not isinstance(traj, Mapping):
                raise ReportError(f"{NONCORE} — скаляр, а год якоря закрывается остатком к факту: "
                                  "нужна траектория с ключом года якоря (решение книги)")
            traj = _explicit_from(traj, year)
            scaled = _scale_traj(traj, factor)
            scaled[str(year)] = _r(reported + (float(traj[str(year)]) - reported) * factor, 6)
            _set(X, path, scaled)
        else:
            _set(X, path, _scale_traj(traj, factor))
    _scale_axes(X, PRICE_INDEXED, factor)
    _follow_centers(X, centers, factor)


def freeze_anchors(X: dict, book: Book) -> None:
    for path in FROZEN_ANCHORS:
        if _get(X, path) == "anchor":
            _set(X, path, _r(book.anchors[path]))


def carry_segment_mix(X: dict, book: Book, old_af: Any, new_af: Any) -> dict[str, Any] | None:
    """Сегментная CoR (М§4.6): общая CoR клетки равна пути режима на структуре нормировки — без ключа
    `credit.segment_relative.corporate_share_ref` это доли сегментов в кредитах АС якоря. Перенос якоря её не сдвигает
    (М§15.2 п. 3, REANCHOR §3.3): ключ, которого нет, получает долю юрлиц прежнего якоря, заданный ключ остаётся. Иначе
    нормировка на структуре нового якоря умножала бы CoR каждого квартала каждой клетки на отношение Σ w × rel двух
    структур — без единой новости. Возвращает долю юрлиц ключа кандидата и доли прежнего и нового якоря; выключенная
    сегментная схема — None."""
    if not book.get("credit.segment_relative.enabled"):
        return None
    books = book.get("nii.books")
    roles = book_roles(books)
    was = segment_weights(books, roles, old_af)["corporate"]
    now = segment_weights(books, roles, new_af)["corporate"]
    key = book.opt(SEGMENT_SHARE)
    if key is None:
        _set(X, SEGMENT_SHARE, _r(was, SHARE_DIGITS))
    share = float(_get(X, SEGMENT_SHARE))
    rel = {s: book.opt(f"credit.segment_relative.{s}") for s in ("corporate", "retail")}
    # общая CoR на структуре нового якоря к пути: Σ w′ × rel / Σ w_ключ × rel (М§4.6)
    ratio = None if not all(_num(v) for v in rel.values()) else (
        (now * rel["corporate"] + (1 - now) * rel["retail"]) / (share * rel["corporate"] + (1 - share) * rel["retail"]))
    return {"share": share, "old_anchor": was, "new_anchor": now, "written": key is None, "ratio": ratio}


def segment_drift_note(mix: Mapping | None) -> str | None:
    """Предупреждение о дрейфе структуры нормировки сегментной CoR (М§15.2 п. 3, REANCHOR §6): ключ остаётся долей
    первого перенесённого якоря, а структура кредитов дрейфует. Когда доля юрлиц нового якоря отходит от ключа дальше
    `SEGMENT_DRIFT`, — обе доли и отношение общей CoR на структуре нового якоря к пути; ключ инструмент не меняет. Иначе
    — None."""
    if not mix:
        return None
    if abs(mix["new_anchor"] - mix["share"]) <= SEGMENT_DRIFT:
        return None
    return (f"структура нормировки сегментной CoR: доля юрлиц в кредитах АС нового якоря {mix['new_anchor']:.6f} отходит "
            f"от ключа `{SEGMENT_SHARE}` {mix['share']:.6f} на {abs(mix['new_anchor'] - mix['share']) * 100:.2f} п.п. "
            f"(порог {SEGMENT_DRIFT * 100:g} п.п.)"
            + ("" if mix.get("ratio") is None else f"; общая CoR на структуре нового якоря — {mix['ratio']:.4f} пути "
               "(Σ w′ × rel / Σ w_ключ × rel)")
            + ". Ключ перенос не меняет: пересмотр структуры вместе с путями режимов — решение книги (М§4.6, §15.2 п. 3)")


def segment_mix_line(d: Mapping) -> str | None:
    """Строка отчёта о структуре нормировки сегментной CoR: ключ кандидата рядом с долями двух якорей."""
    mix = d.get("segment_mix")
    if not mix:
        return None
    return (f"- сегментная CoR: структура нормировки — доля юрлиц в кредитах АС {mix['share']:.6f} (`{SEGMENT_SHARE}`, "
            + ("записана долей прежнего якоря" if mix["written"] else "ключ прежней книги")
            + f"); доля юрлиц прежнего якоря {mix['old_anchor']:.6f}, нового {mix['new_anchor']:.6f} — на структуре "
            "нового якоря общая CoR каждого квартала сдвинулась бы без единой новости")


def carry_fx(X: dict, factor: float) -> None:
    """Валютная доля RWA на новом якоре: индекс курса стартует с единицы (М§4.11), поэтому доля
    пересчитывается на достигнутый курс — тогда путь RWA тот же."""
    if not _get(X, f"{FX}.enabled"):
        return
    share, abroad = float(_get(X, f"{FX}.share")), float(_get(X, f"{FX}.foreign_inflation"))
    rate = factor / (1.0 + abroad) ** 0.25
    _set(X, f"{FX}.share", _r(share * rate / (1.0 - share + share * rate)))


def spread_rule(data: Mapping, rates: Mapping[str, float], name: str) -> tuple[int, float] | None:
    """Ключ спреда года первого прогнозного квартала по правилу «от ставки якоря» (М§4.4):
    ставка якоря − β × опора мира-эталона в первом прогнозном квартале; `None` — у книги такого
    ключа нет."""
    spec = data["nii"]["books"][name]
    spread = spec["spread"]
    year, quarter = parse_period(str(data["meta"]["first_period"]))
    if not isinstance(spread, Mapping) or str(year) not in spread:
        return None
    world = data["worlds"][data["nii"]["transmission"]["reference_world"]]
    ref = Trajectory(world["key_rate" if spec["ref"] == "key" else spec["ref"]]).value(year, quarter)
    beta = float(spec["beta"]) if spec["side"] == "liability" else 1.0
    return year, rates[name] - beta * ref


def rederive_spreads(X: dict, old: Book, old_rates: Mapping[str, float], rates: Mapping[str, float]) -> list[str]:
    """Ключи спредов от ставок якоря — заново, тем же правилом, что в прежней книге (М§4.4).

    Ключ правится, только если прежняя книга правилу следовала; ключ следующего года остаётся
    серединой до калибровки, если был ею."""
    moved = []
    for name, spec in X["nii"]["books"].items():
        was = spread_rule(old.source, old_rates, name)
        now = spread_rule(X, rates, name)
        if was is None or now is None:
            continue
        old_spread = old.source["nii"]["books"][name]["spread"]
        y_old, rule_old = was
        if abs(float(old_spread[str(y_old)]) - rule_old) > SPREAD_RULE_TOL:
            continue
        year, rule = now
        spread = dict(spec["spread"])
        if abs(rule - float(spread[str(year)])) <= SPREAD_RULE_TOL:
            continue                             # ставка якоря та же — ключ книги остаётся как есть
        old_t = Trajectory(old_spread)
        middle = (str(y_old + 1) in old_spread and abs(
            float(old_spread[str(y_old + 1)])
            - (float(old_spread[str(y_old)]) + old_t.year_value(y_old + 2)) / 2) <= SPREAD_RULE_TOL)
        spread[str(year)] = _r(rule, 6)
        if middle:
            spread[str(year + 1)] = _r((spread[str(year)] + old_t.year_value(year + 2)) / 2, 6)
        spec["spread"] = _sorted_traj(spread)
        moved.append(name)
    return moved


def _shift_key(key: Any, years: int) -> str:
    key = str(key)
    return key if key in ("LT", "LT_from") else f"{int(key[:4]) + years}{key[4:]}"


def _shift_traj(traj: Any, years: int, last_year: int, where: str) -> Any:
    if not isinstance(traj, Mapping):
        return traj
    out = {}
    for k, v in traj.items():
        if str(k) == "LT_from":
            if int(v) + years > last_year:
                raise ReportError(f"{where}.LT_from {v} + {years} — позже года last_period {last_year}: "
                                  "кризисная траектория не помещается в горизонт (решение книги)")
            out[k] = int(v) + years
        else:
            out[_shift_key(k, years)] = v
    return out


def shift_crisis(X: dict, years: int) -> dict[str, str]:
    """Смена года якоря: год шока сдвигается вместе с ним, ключи кризисных траекторий — на
    столько же лет (М§15.2 п. 6). `shock_year_offset` сохраняется. Пути осей по этим ключам переименовываются
    вместе с ними; у оси-связки — и ключи словарей её концов. Возвращает {прежний путь: новый}."""
    if not years:
        return {}
    last_year = parse_period(str(X["meta"]["last_period"]))[0]
    renamed: dict[str, str] = {}
    for r in X["regimes"]["ids"]:
        spec = X["regimes"][r]
        if "shock_year_offset" not in spec:
            continue
        for name in CRISIS_TRAJECTORIES + ("loan_growth_override",):
            if isinstance(spec.get(name), Mapping):
                for k in spec[name]:
                    renamed[f"regimes.{r}.{name}.{k}"] = f"regimes.{r}.{name}.{_shift_key(k, years)}"
                spec[name] = _shift_traj(spec[name], years, last_year, f"regimes.{r}.{name}")
        if isinstance(spec.get("one_off_loss"), Mapping):
            y, q = parse_period(str(spec["one_off_loss"]["period"]))
            spec["one_off_loss"] = {**spec["one_off_loss"], "period": period_str(y + years, q)}
    for _, axes, keys in _axis_lists(X):
        for axis in axes:
            axis["paths"] = [renamed.get(str(p), p) for p in axis.get("paths") or []]
            if axis.get("kind") == BUNDLE:           # концы связки — словари по путям оси: ключи идут за путями
                for key in keys:
                    if isinstance(axis.get(key), Mapping):
                        axis[key] = {renamed.get(str(p), p): v for p, v in axis[key].items()}
    table = _get(X, "checks.m_crisis_vs_cbr.loan_growth")
    if isinstance(table, Mapping):
        X["checks"]["m_crisis_vs_cbr"]["loan_growth"] = {_shift_key(k, years): v for k, v in table.items()}
    return renamed


def near_trajectory(old: Any, periods: Sequence[str], values: Sequence[float], last_year: int,
                    detail_from: int = 0) -> dict:
    """Ближняя калибровка ЧПМ траекторией книги: кварталы — по год после якоря включительно и
    дальше, пока значения внутри года заметно расходятся; затем — ключи лет со средним года,
    пока хвост заметен (в последнем году сетки — только ключ года, М§0.4: там остаток уровня в
    ставках и калибровка гасят друг друга, и терминал читает LT-уровни); `LT` — прежний.
    `detail_from` — год, по который кварталы пишутся в любом случае: год, записанный кварталами на
    прошлом проходе калибровки, остаётся записанным кварталами (иначе запись прыгает между двумя
    видами и проходы не сходятся)."""
    lt = float(old.get("LT", 0.0)) if isinstance(old, Mapping) else float(old)
    by_year: dict[int, list[tuple[int, float]]] = {}
    for p, v in zip(periods, values):
        y, q = parse_period(p)
        by_year.setdefault(y, []).append((q, v))
    detail = parse_period(periods[0])[0] + 1
    for y in sorted(by_year):
        vals = [v for _, v in by_year[y]]
        if y == detail + 1 and max(vals) - min(vals) > NEAR_RANGE:
            detail = y
    detail = min(max(detail, detail_from), last_year - 1)
    out: dict[str, float] = {}
    for y in sorted(by_year):
        if y > detail:
            break
        for q, v in by_year[y]:
            out[period_str(y, q)] = _r(v, 7)
        if len(by_year[y]) == 4:
            out[str(y)] = sum(out[period_str(y, q)] for q in (1, 2, 3, 4)) / 4
    means = {y: sum(v for _, v in qs) / len(qs) for y, qs in by_year.items() if detail < y <= last_year}
    tail = [y for y in means if abs(means[y] - lt) >= NEAR_TOL]
    for y in sorted(means):
        if tail and y <= max(tail):
            out[str(y)] = _r(means[y], 7)
    out["LT"] = lt
    return out


def set_near(X: dict, traj: Any, warnings: list[str] | None = None) -> None:
    """Ближняя калибровка ЧПМ — в книгу, вместе с осями по её ключам. Траектория пишется заново (кварталы,
    затем годы), и ось, которая сдвигает её ключи нескольких лет, получает ключи тех же лет новой траектории:
    ключ закрытого квартала из путей уходит, год, записанный теперь кварталами, входит всеми своими ключами.
    Ось, у которой не осталось ни одного ключа (все её годы закрыты), снимается — с предупреждением."""
    _set(X, NEAR, traj)
    keys = [str(k) for k in traj if str(k) not in ("LT", "LT_from")] if isinstance(traj, Mapping) else []
    prefix = NEAR + "."
    for where, axes, _ in _axis_lists(X):
        for axis in list(axes):
            paths = [str(p) for p in axis.get("paths") or []]
            mine = [p for p in paths if p.startswith(prefix)]
            if not mine:
                continue
            if axis.get("kind") == BUNDLE:
                raise ReportError(
                    f"{where} «{axis.get('name')}»: ось-связка двигает ключи ближнего пути ЧПМ ({', '.join(mine)}), а "
                    "перенос якоря пишет траекторию заново — другими ключами; концы оси для новых ключей инструмент "
                    "придумать не может (решение книги: ось вида shift или концы на новом якоре)")
            years = {p[len(prefix):][:4] for p in mine}
            fresh = [prefix + k for k in keys if k[:4] in years]
            if set(fresh) == set(mine):
                continue
            rest = [p for p in paths if not p.startswith(prefix)]
            if fresh or rest:
                axis["paths"] = rest + fresh
            else:
                axes.remove(axis)
                if warnings is not None:
                    warnings.append(f"{where} «{axis.get('name')}»: все ключи ближнего пути ЧПМ, которые двигала ось, "
                                    "закрыты отчётами — ось снята (решение книги: нужна ли ось на новых ключах)")


def _reference_form(tree: Mapping) -> dict:
    """Копия книги в записи образца: без ключа мира уровня (`nii.transmission.level_world`) ключ цели ЧПМ задаёт
    уровень мира-опоры решателя передачи (М§4.5). У книги без этого ключа — просто копия."""
    Y = copy.deepcopy(dict(tree))
    Y["nii"]["transmission"].pop(LEVEL_WORLD.rsplit(".", 1)[-1], None)
    return Y


def _sigmas(tr: Any) -> tuple[float, float, float, float]:
    """Скаляры пути передачи ставки (М§4.5) — σ0_A, σ0_L, φ_A, φ_L: всё, что клетка несёт из решения
    `solve_transmission` в ставки своих кварталов и терминала."""
    return float(tr.sigma0), float(tr.sigma0_liab), float(tr.phi_assets), float(tr.phi_liab)


def keep_transmission(X: dict, new_facts: Facts, old: GridRun) -> dict[str, tuple[float, float, float]]:
    """Режим `keep` (М§15.2 п. 8). Цели A-N2, A-N3 и доли `nii.sigma0_split`, `nii.phi_split` — числа
    «на структуре якоря» (М§4.5): при переносе якоря они пересчитываются на новую структуру так,
    чтобы скаляры пути σ0_A, σ0_L, φ_A, φ_L остались прежними.

    Иначе ядро решило бы те же цели на сдвинувшихся весах книг и сдвинуло бы спреды всего пути
    и терминала — без единой новости. Решение — по самой функции ядра `solve_transmission`, без
    её внутренностей: σ0_A и σ0_L аффинны по цели A-N2, объём сжатия φ — по цели A-N3, а
    `φ_A = p × φ`, `φ_L = (1 − p) × φ × A/L` (A/L — отношение весов книг с `phi` на структуре
    якоря; читается из наклонов φ_L и φ по цели). Оси целей пересчитываются тем же правилом —
    концу оси отвечают те же скаляры, что в прежней книге; оси долей сдвигаются вместе с центром
    (конец на границе 0 или 1 остаётся на ней). Возвращает {ключ: (было, стало, наклон пересчёта оси)}.

    Ключ мира уровня (`nii.transmission.level_world`): ключ цели ЧПМ книги — не уровень мира-опоры решателя, а
    стационарная маржа названного мира на составе баланса якоря, уровень мира-опоры ядро находит сам. Скаляры
    сохраняются тем же решением в записи образца (книга без ключа мира уровня, цель — уровень мира-опоры:
    там σ0 от цели A-N3 не зависят, и решение идёт в два шага), а ключ книги на новом якоре — стационарная маржа
    мира уровня при этих скалярах: то же суждение на составе баланса нового якоря. Оси по ключу и по цели A-N3
    пересчитываются в единицах ключа книги: вдоль оси A-N3 неподвижен ключ, а не уровень мира-опоры."""
    bridge = bridge_from_facts(new_facts)
    was = old.ctx.transmission
    level = _get(X, LEVEL_WORLD)                         # None — ключ цели стоит в мире-опоре решателя (образец)
    key0, star0 = float(_get(X, NIM_TARGET)), float(_get(X, T_TARGET))
    s0, p0 = float(_get(X, SPLIT)), float(_get(X, PHI_SPLIT))
    # проба цели в записи образца — уровень мира-опоры решателя прежней книги (у образца — сам ключ)
    t0 = key0 if level is None else old.ctx.bridge.to_mgmt_nim(float(was.nss[was.reference_world]))

    def solve(target: float, t_star: float, split: float, phi_split: float) -> Any:
        Y = _reference_form(X)
        for path, value in zip(TRANSMISSION_KEYS, (target, t_star, split, phi_split)):
            _set(Y, path, value)
        return solve_transmission(book_from_dict(Y, facts=new_facts), new_facts, bridge)

    def solve_old(path: str | None) -> Any:              # прежняя структура; `path` — цель, сдвинутая на шаг
        if level is None:
            probe = old.ctx.book.with_overrides({path: float(old.ctx.book.get(path)) + SOLVE_STEP})
        else:
            Y = _reference_form(old.ctx.book.source or old.ctx.book.data)
            _set(Y, NIM_TARGET, t0)
            if path is not None:
                _set(Y, path, float(_get(Y, path)) + SOLVE_STEP)
            probe = book_from_dict(Y, facts=old.ctx.facts)
        return solve_transmission(probe, old.ctx.facts, old.ctx.bridge)

    want_a, want_l, want_pa, want_pl = _sigmas(was)
    base = was if level is None else solve_old(None)     # прежнее решение в записи образца — база наклонов
    if max(abs(x - y) for x, y in zip(_sigmas(base), _sigmas(was))) > GAP_TOL:
        raise ReportError(
            f"передача ставки: прежняя книга в записи образца (без `{LEVEL_WORLD}`, цель — уровень мира-опоры "
            f"решателя {was.reference_world}) даёт скаляры пути {_fmt(list(_sigmas(base)))}, а сама книга — "
            f"{_fmt(list(_sigmas(was)))}: ключ мира уровня ядро читает не как стационарную маржу этого мира (М§4.5)")

    # --- σ0_A, σ0_L: цель A-N2 и доля сдвига
    a0, l0, _, _ = _sigmas(solve(t0, star0, s0, p0))
    a1, l1, _, _ = _sigmas(solve(t0 + SOLVE_STEP, star0, s0, p0))
    da, dl = (a1 - a0) / SOLVE_STEP, (l1 - l0) / SOLVE_STEP
    if (s0 > 0 and not da) or (s0 < 1 and not dl):
        raise ReportError("передача ставки: σ0 не зависит от цели A-N2 — нет книг с lt_shift?")
    old_target = solve_old(NIM_TARGET)
    (old_a, old_l, _, _), (base_a, base_l, _, _) = _sigmas(old_target), _sigmas(base)
    da_old, dl_old = (old_a - base_a) / SOLVE_STEP, (old_l - base_l) / SOLVE_STEP
    if s0 >= 1.0:                                        # весь сдвиг — на активах
        target, split, slope = t0 + (want_a - a0) / da, s0, da_old / da
    elif s0 <= 0.0:                                      # весь сдвиг — на пассивах
        target, split, slope = t0 + (want_l - l0) / dl, s0, dl_old / dl
    else:
        root = t0 - a0 / da                              # цель, при которой сдвиг нулевой
        g1, h1 = da / s0, dl / (1.0 - s0)
        target = root + want_a / g1 + want_l / h1
        split = want_a / (g1 * (target - root)) if target != root else s0
        slope = da_old / g1 + dl_old / h1
    split = _r(min(1.0, max(0.0, split)), 6)
    if level is None:                                    # у книги с миром уровня округляется ключ книги, не проба
        target = _r(target, 6)

    # --- φ_A, φ_L: цель A-N3 и доля сжатия
    tr0, tr1 = solve(target, star0, split, p0), solve(target, star0 + SOLVE_STEP, split, p0)
    dphi = float(tr1.phi) - float(tr0.phi)
    if not dphi:
        raise ReportError("передача ставки: φ не зависит от цели A-N3 — нет книг с phi?")
    if p0 < 1.0:
        ratio = (float(tr1.phi_liab) - float(tr0.phi_liab)) / ((1.0 - p0) * dphi)    # A/L новой структуры
        if not ratio:
            raise ReportError("передача ставки: φ_L не зависит от цели A-N3 — нет пассивов с phi?")
        want_phi = want_pa + want_pl / ratio
    else:                                                # всё сжатие — в спредах кредитных книг
        want_phi = want_pa
    phi_split = want_pa / want_phi if 0.0 < p0 < 1.0 and want_phi else p0
    phi_split = _r(min(1.0, max(0.0, phi_split)), 6)
    t_star = _r(star0 + (want_phi - float(tr0.phi)) * SOLVE_STEP / dphi, 6)
    old_star = solve_old(T_TARGET)
    dphi_old = float(old_star.phi) - float(base.phi)
    key = target

    if level is not None:                                # ключ книги — стационарная маржа мира уровня при этих скалярах
        def margin(tr: Any, br: Any) -> float:
            return br.to_mgmt_nim(float(tr.nss[level]))

        at = solve(target, t_star, split, phi_split)
        by_target = solve(target + SOLVE_STEP, t_star, split, phi_split)
        by_star = solve(target, t_star + SOLVE_STEP, split, phi_split)
        gain = margin(by_target, bridge) - margin(at, bridge)            # ключ книги на шаг уровня мира-опоры
        gain_old = margin(old_target, old.ctx.bridge) - margin(base, old.ctx.bridge)
        if not gain or not gain_old:
            raise ReportError(f"передача ставки: стационарная маржа мира {level} не зависит от уровня мира-опоры "
                              f"решателя — ключ `{NIM_TARGET}` в мире `{LEVEL_WORLD}` не определён")
        key = _r(margin(at, bridge), 6)
        slope *= gain / gain_old
        # вдоль оси A-N3 неподвижен ключ книги: уровень мира-опоры идёт за целью так, чтобы ключ остался на месте
        dphi = float(by_star.phi) - float(at.phi) - (float(by_target.phi) - float(at.phi)) * (
            margin(by_star, bridge) - margin(at, bridge)) / gain
        dphi_old -= (float(old_target.phi) - float(base.phi)) * (
            margin(old_star, old.ctx.bridge) - margin(base, old.ctx.bridge)) / gain_old
        if not dphi:
            raise ReportError("передача ставки: при неподвижном ключе уровня маржи φ не зависит от цели A-N3")
    slope_star = dphi_old / dphi
    if float(was.phi):                                   # конец оси: обе части сжатия — в той же пропорции
        slope_star *= want_phi / float(was.phi)

    out = {}
    for path, before, now, k, bounds in ((NIM_TARGET, key0, key, slope, None),
                                         (T_TARGET, star0, t_star, slope_star, None),
                                         (SPLIT, s0, split, 1.0, (0.0, 1.0)),
                                         (PHI_SPLIT, p0, phi_split, 1.0, (0.0, 1.0))):
        _set(X, path, now)
        _remap_axes(X, path, before, now, k, bounds)
        out[path] = (before, now, k)
    return out


def carry_level_gate(X: dict, kept: Mapping[str, tuple]) -> tuple[float, float] | None:
    """Гейт `checks.nim_stationary` в мире ключа уровня маржи (`nii.transmission.level_world`) сверяет то же
    число, что задаёт ключ цели ЧПМ, — тождество: его цель — вторая запись того же суждения и идёт за ключом тем
    же сдвигом (гейт, молчавший на прежней книге, молчит и на кандидате). Возвращает (было, стало). Гейт в
    другом мире, книга без гейта и книга без ключа мира уровня — None: цель гейта — отдельное суждение."""
    gate, level = _get(X, NIM_STATIONARY), _get(X, LEVEL_WORLD)
    if gate is None or level is None or str(gate["world"]) != str(level):
        return None
    before, (was, now, _) = float(gate["target"]), kept[NIM_TARGET]
    after = _r(before + (now - was), 6)
    _set(X, GATE_TARGET, after)
    return before, after


def _row_keys(X: Mapping) -> list[tuple[Any, str]]:
    """Оси обратного расчёта книги с ключами их строк (ключ строки — путь оси, как его пишет ядро)."""
    from model.uncertainty import axis_key
    return [(axis, axis_key(axis)) for axis in _get(X, "valuation.reverse_dcf.axes") or []]


def carry_refine_rows(X: dict, rows: Sequence[Any] | None, before: Sequence[tuple[Any, str]],
                      warnings: list[str] | None = None) -> None:
    """Строки обратного расчёта, корень которых уточняется на полной полосе (`valuation.reverse_dcf.refine_rows`),
    названы ключами строк — путями осей. Перенос переименовывает пути осей (ключи года шока, ключи ближнего пути
    ЧПМ) и может снять ось: строка перечня идёт за своей осью, строка снятой оси из перечня уходит — с
    предупреждением. `rows` — перечень прежней книги (None — ключа нет), `before` — оси кандидата с ключами строк
    прежней книги (`_row_keys` сразу после копии книги). Имя, которого среди строк прежней книги не было,
    остаётся как есть: его судит схема книги."""
    if rows is None:
        return
    now = {id(axis): key for axis, key in _row_keys(X)}
    renamed = {key: now.get(id(axis)) for axis, key in before}
    out: list[str] = []
    gone: list[str] = []
    for row in map(str, rows):
        new = renamed.get(row, row)
        if new is None:
            gone.append(row)
        elif new not in out:
            out.append(new)
    if out != [str(r) for r in _get(X, REFINE_ROWS) or []]:
        _set(X, REFINE_ROWS, out)
    if gone and warnings is not None:
        warnings.append(f"{REFINE_ROWS}: строки {', '.join(gone)} сняты — их осей обратного расчёта у кандидата нет; "
                        "какие строки уточнять на полной полосе — решение книги")


# ------------------------------------------------------------------ наблюдение A-P2u


def _drop_observation(book: Book, period: str) -> Book:
    obs = [o for o in book.get(OBS) or [] if str(o["period"]) != period]
    if len(obs) == len(book.get(OBS) or []):
        return book
    return book.with_overrides({OBS: obs})


def expected_observation(book: Book, facts: Facts, live: LiveInputs | None = None, *,
                         without: Sequence[str] = ()) -> dict:
    """Наблюдение первого прогнозного квартала, равное ожиданию модели (М§13): прогноз фильтра
    A-P2u в упр. базисе; нау-каст этого квартала из книги снимается. `without` — режимы, которые в
    ожидание не входят (отчёт «без шока»: ожидание прочих режимов с их вероятностями, в сумме 1)."""
    from model.nextreport import model_expectation
    period = str(book.get("meta.first_period"))
    exp = model_expectation(_drop_observation(book, period), facts, period, live=live)
    cor, nim = exp["cor_q_mgmt"], exp["nim_q_mgmt"]
    if without:
        rows = [r for r in exp["by_regime"] if r["regime"] not in without]
        total = sum(r["posterior"] for r in rows)
        if not total:
            raise ReportError(f"ожидание без режимов {', '.join(without)}: прочих режимов с вероятностью нет")
        cor = sum(r["posterior"] * r["cor_q_mgmt"] for r in rows) / total
        nim = sum(r["posterior"] * r["nim_q_mgmt"] for r in rows) / total
    return {"period": period, "cor": _r(cor, 12), "nim": _r(nim, 12), "se_cor": 0.0, "se_nim": 0.0,
            "basis": "mgmt"}


def shock_regimes(run: GridRun) -> list[str]:
    """Режимы, у которых первый прогнозный квартал книги лежит в году шока (М§3.2): в этом квартале
    прогноз наблюдения двугорбый — шок либо случился, либо нет."""
    year = run.ctx.timeline.year(1)
    return [r for r, rp in run.ctx.prep.regimes.items() if rp.shock_year is not None and rp.shock_year == year]


def with_observation(book: Book, obs: Mapping) -> Book:
    """Прежняя книга с наблюдением её первого прогнозного квартала (A⁺, М§15.2)."""
    base = _drop_observation(book, str(obs["period"]))
    return base.with_overrides({OBS: list(base.get(OBS) or []) + [dict(obs)]})


def frozen_expectations(book: Book, facts: Facts) -> dict[str, dict[str, float]]:
    """Ожидания режимов прежней книги на её первый прогнозный квартал, упр. базис (М§12)."""
    period = str(book.get("meta.first_period"))
    ctx = make_context(_drop_observation(book, period), facts)
    q = ctx.timeline.index(period)
    mu = ctx.expectations if ctx.expectations and int(ctx.expectations.get("until", 0)) >= q \
        else regime_expectations(ctx, q)
    br = ctx.bridge
    return {"mu_cor": {r: _r(br.to_mgmt_cor(mu["cor"][r][q]), 12) for r in book.get("regimes.ids")},
            "mu_nim": {r: _r(br.to_mgmt_nim(mu["nim"][r][q]), 12) for r in book.get("regimes.ids")}}


def carry_observation(X: dict, book: Book, facts: Facts, obs: Mapping) -> dict:
    """Факт квартала считается один раз: наблюдение с замороженными μ (М§15.2 п. 1)."""
    period = str(obs["period"])
    ru = X["joint"]["regime_update"]
    kept = [o for o in ru.get("observations") or [] if str(o["period"]) != period]
    record = {**{k: obs[k] for k in ("period", "cor", "nim", "se_cor", "se_nim", "basis")},
              **frozen_expectations(book, facts)}
    for x in ("cor", "nim"):
        if record[x] is None:
            record.pop(f"mu_{x}")
    kept.append(record)
    kept.sort(key=lambda o: pindex(str(o["period"])))
    window = ru.get("window_obs")
    ru["observations"] = kept[-int(window):] if window else kept
    return record


# ------------------------------------------------------------------ перезаякоривание


def valuation_day(valuation_date: Any, report: Mapping) -> dt.date:
    """Дата оценки кандидата: заданная, иначе `published` отчёта, иначе день после конца квартала."""
    end = period_end(str(report["period"]))
    try:
        day = to_date(valuation_date or report.get("published") or (end + dt.timedelta(days=1)))
    except ValueError as exc:
        raise ReportError(f"дата оценки {valuation_date!r} — не дата ГГГГ-ММ-ДД") from exc
    if day < end:
        raise ReportError(f"дата оценки {day} раньше конца квартала {end}")
    return day


def _weights(run: GridRun, cell: Sequence[str] | None) -> dict[tuple[str, str, str], float]:
    if cell is not None:
        return {tuple(cell): 1.0}
    return dict(run.layers[ANALYTICAL].prob)


def _mean(run: GridRun, weights: Mapping, name: str, q: int) -> float:
    return sum(w * float(run.cell(*key).quarters[name][q]) for key, w in weights.items() if w)


def _anchor_row(run: GridRun, weights: Mapping, name: str) -> float:
    """Норматив якоря модели: строка q = 0 зависит только от сценария капитала."""
    by_scenario: dict[str, float] = {}
    for (_, _, s), w in weights.items():
        by_scenario[s] = by_scenario.get(s, 0.0) + w
    return sum(w * float(next(c for c in run.cells if c.scenario == s).quarters[name][0])
               for s, w in by_scenario.items() if w)


def carry_t2(X: dict, old_anchor: str, period: str, fact: Any, derived: dict, warnings: list[str]) -> None:
    """Траектория инструментов капитала `capital.n20.t2` (М§4.11): книга, которая пишет ключ квартала якоря
    явно, получает ключ квартала нового якоря, равный факту отчёта, — иначе строка якоря не воспроизвела бы
    норматив. Остальные ключи траектории — суждение книги: инструмент их не трогает и называет это."""
    traj = _get(X, T2)
    if fact is None or not _anchor_key(X, T2, old_anchor):
        return
    now = Trajectory(traj).value(*parse_period(period))
    if abs(float(fact) - now) <= T2_TOL:
        return
    _set(X, T2, _sorted_traj({**traj, period: _r(float(fact), 6)}))
    derived["t2_anchor"] = (now, float(fact))
    warnings.append(f"{T2}: ключ квартала якоря {period} — факт отчёта {float(fact):g} (траектория книги давала "
                    f"{now:g}); остальные ключи траектории — суждение книги (инструменты растут с RWA): пересмотреть")


T2_SHARE = "capital.n20.t2_share"            # доля инструментов в RWA своей клетки: квартал ключа {enabled, from} (М§4.11)


def carry_t2_share(X: dict, period: str, first_new: str, derived: dict, warnings: list[str]) -> None:
    """Доля инструментов в RWA своей клетки (`capital.n20.t2_share`, М§4.11) переносится по положению квартала ключа
    относительно нового якоря (М§15.2 п. 3): пока новый якорь раньше квартала ключа, ключ — как есть (при новом якоре
    в квартале q_χ − 1 квартал ключа становится новым `first_period`); квартал ключа, ушедший в историю (`from` ≤
    новый `anchor_period`), переписывается на новый `first_period` — доля нового якоря `T2′_0 / RWA′_0` (иначе отказ
    схемы, прил. A № 30). Переписывается при любом `enabled`: границы квартала схема проверяет всегда. Траектория
    `capital.n20.t2` с квартала ключа не читается и не правится. Без ключа шага нет."""
    node = _get(X, T2_SHARE)
    if not isinstance(node, Mapping) or "from" not in node:
        return
    was = str(node["from"])
    now = first_new if pindex(was) <= pindex(period) else was
    derived["t2_share"] = {"enabled": node.get("enabled"), "from": (was, now)}
    if now != was:
        _set(X, f"{T2_SHARE}.from", now)
        warnings.append(f"{T2_SHARE}.from: квартал ключа {was} ушёл в историю (новый якорь {period}) — переписан на новый "
                        f"first_period {now}: клетка держит долю нового якоря T2′_0 / RWA′_0 (М§4.11, §15.2 п. 3)")


def t2_share_cells(run: GridRun, weights: Mapping[tuple, float], when: str) -> float | None:
    """Доля инструментов клеток прежней книги χ_c (М§4.11) под весами `weights`: T2 / RWA конца квартала q_χ − 1
    (при q_χ = 1 — доля якоря), `when` — квартал ключа прежней книги. Для печати рядом с долей нового якоря."""
    tl = run.ctx.timeline
    q = tl.index(when) - 1
    total = sum(weights.values())
    if not total or q < 0:
        return None
    return sum(w * float(run.cell(*k).quarters["t2"][q]) / float(run.cell(*k).quarters["rwa"][q])
               for k, w in weights.items() if w) / total


def t2_share_line(d: Mapping, cand: Any = None) -> str | None:
    """Строка отчёта о переносе доли инструментов: квартал ключа до и после, доля нового якоря `T2′_0 / RWA′_0`
    (значение траектории кандидата в квартале нового якоря к RWA якоря его фактов) и доля клеток прежней книги."""
    row = d.get("t2_share")
    if not row:
        return None
    was, now = row["from"]
    anchor = None
    if cand is not None:
        rwa0 = anchor_facts(cand.facts, cand.book.get("nii.books")).basel_rwa
        if rwa0:
            anchor = Trajectory(cand.book.get(T2)).value(*parse_period(cand.period)) / float(rwa0)
    shares = "".join(f"; {name} {_pct(x, 4)}" for x, name in ((anchor, "доля нового якоря T2′_0 / RWA′_0"),
                                                              (row.get("cells"), "доля клеток прежней книги χ_c"))
                     if x is not None)
    return (f"- доля инструментов в RWA своей клетки `{T2_SHARE}` (enabled: {row['enabled']}): квартал ключа {was} → "
            f"{now}" + (" (ушёл в историю — переписан на новый first_period)" if now != was else " (как есть)") + shares)


AT1_SHARE = "capital.at1_share"              # доля добавочного капитала в RWA своей клетки {enabled, from, spread, base}
T2_PREMIUM = "capital.n20.t2_premium"        # надбавка за субординацию дополнительного капитала {enabled, spread, base}
ANCHOR_WORD = "anchor"


def carry_at1_share(X: dict, period: str, first_new: str, at1_0: float, derived: dict, warnings: list[str]) -> None:
    """Доля добавочного капитала в RWA своей клетки (`capital.at1_share`, М§4.11, §15.2 п. 3). Квартал ключа — по
    положению относительно нового якоря, как у доли инструментов (`carry_t2_share`): ушедший в историю (`from` ≤ новый
    `anchor_period`) переписывается на новый `first_period` (иначе отказ схемы, прил. A № 31), при любом `enabled`.
    База — суммой: слово `anchor` записывается числом факта AT1_0 прежнего якоря (`at1_0`), число остаётся; слот купона
    якоря фактов (`at1.coupon_annual`) — купон базы, его шаг не трогает. Без ключа шага нет."""
    node = _get(X, AT1_SHARE)
    if not isinstance(node, Mapping):
        return
    row: dict[str, Any] = {"enabled": node.get("enabled")}
    if "from" in node:
        was = str(node["from"])
        to = first_new if pindex(was) <= pindex(period) else was      # ушедший в историю — новый first_period
        row["from"] = (was, to)
        if to != was:
            _set(X, f"{AT1_SHARE}.from", to)
            warnings.append(f"{AT1_SHARE}.from: квартал ключа {was} ушёл в историю (новый якорь {period}) — переписан на "
                            f"новый first_period {to}: клетка держит долю нового якоря AT1′_0 / RWA′_0 (М§4.11, §15.2 п. 3)")
    if "base" in node:
        base = node["base"]
        row["base"] = (base, at1_0 if base == ANCHOR_WORD else base)
        if base == ANCHOR_WORD:
            _set(X, f"{AT1_SHARE}.base", float(at1_0))
            warnings.append(f"{AT1_SHARE}.base: слово anchor записано числом факта AT1_0 прежнего якоря {at1_0:g} млрд ₽ — "
                            "база купона якоря переносится суммой; пересмотр базы под купон фактического отчёта — "
                            "решение книги (М§15.2 п. 3)")
    derived["at1_share"] = row


def carry_t2_premium(X: dict, t2_0: float, derived: dict, warnings: list[str]) -> None:
    """Надбавка за субординацию дополнительного капитала (`capital.n20.t2_premium`, М§4.11, §15.2 п. 3): база — суммой,
    слово `anchor` записывается числом значения траектории `capital.n20.t2` в квартале прежнего якоря (`t2_0`), число
    остаётся. Без ключа шага нет."""
    node = _get(X, T2_PREMIUM)
    if not isinstance(node, Mapping) or "base" not in node:
        return
    base = node["base"]
    derived["t2_premium"] = {"enabled": node.get("enabled"), "base": (base, t2_0 if base == ANCHOR_WORD else base)}
    if base == ANCHOR_WORD:
        _set(X, f"{T2_PREMIUM}.base", float(t2_0))
        warnings.append(f"{T2_PREMIUM}.base: слово anchor записано числом T2_0 прежнего якоря {t2_0:g} млрд ₽ — на своём "
                        "пути надбавка продолжается на прежнюю сумму сверх базы (М§15.2 п. 3)")


def at1_share_lines(d: Mapping, at1_new: float | None = None) -> list[str]:
    """Строки отчёта о переносе ключей восьмого прохода: квартал ключа доли добавочного капитала до и после, база и
    сумма сверх неё на новом якоре (`at1_new` — AT1 фактов кандидата); база надбавки за субординацию."""
    out = []
    row = d.get("at1_share")
    if row:
        text = f"- доля добавочного капитала в RWA своей клетки `{AT1_SHARE}` (enabled: {row['enabled']})"
        if "from" in row:
            was, now = row["from"]
            text += f": квартал ключа {was} → {now}" + (" (ушёл в историю — переписан на новый first_period)"
                                                       if now != was else " (как есть)")
        if "base" in row:
            was, now = row["base"]
            text += f"; база {was} → {float(now):g} млрд ₽"
            if at1_new is not None:
                text += f", AT1 нового якоря {at1_new:.3f}, сверх базы {at1_new - float(now):.3f}"
        out.append(text)
    row = d.get("t2_premium")
    if row:
        was, now = row["base"]
        out.append(f"- надбавка за субординацию `{T2_PREMIUM}` (enabled: {row['enabled']}): база {was} → "
                   f"{float(now):g} млрд ₽")
    return out


ESTIMATED_LEVELS =("basel_cet1", "basel_rwa", "bank_base_capital", "t2")


def estimated_levels(book: Book, facts: Facts, report: Mapping, base_run: GridRun,
                     weights: Mapping[tuple, float]) -> tuple[dict, dict[str, tuple[Any, float]]]:
    """Отчёт с оценкой нормативов (`capital.estimated`, М§3.3): оценка есть только у двух нормативов, а уровни —
    капитал группы и вменённые RWA — на дату якоря ещё не раскрыты; отчёт несёт на их месте уровни последней
    формы. Калибровать плотности RWA к RWA прошлого квартала нельзя: якорь получил бы уровень RWA на квартал
    роста ниже, и каждый рубль роста портфеля стоил бы капитала меньше — без единой новости. Поэтому уровни
    якоря считаются по оценке нормативов на RWA модели:

        RWA    = Σ плотность книги × остаток нового якоря × ожидаемый дрейф плотности за квартал
        K20    = (Н20.0 − поправка + вычет сценария) × RWA;   капитал без инструментов = K20 + (1 − f) × R − AT1 − T2
        K11    = (второй норматив − поправка + вычет сценария) × RWA                       (базовый капитал)

    T2 — значение траектории книги в квартале якоря, а у книги с ключом доли инструментов, чей квартал ключа —
    закрываемый (`from` = `first_period`), — доля якоря на RWA оценки `T2_0 × RWA / RWA_0` (М§15.2 п. 10); ожидаемый
    дрейф — отношение RWA клеток прежней книги к RWA по её плотностям на остатках тех же клеток в закрываемом квартале. Поправки при этом остаются прежними,
    нормативы якоря равны оценке. Возвращает отчёт с расчётными уровнями и {слот: (значение отчёта, расчёт)}."""
    from dataclasses import replace
    roles = book_roles(book.get("nii.books"))
    B, C = report["balance"], report["capital"]
    prep, tl = base_run.ctx.prep, base_run.ctx.timeline
    old = anchor_facts(facts, book.get("nii.books"))
    total = sum(weights.values())
    p = {tuple(k): v / total for k, v in weights.items() if v}
    plain = prep.rwa_w                           # плотности прежней книги
    # путь постоянной части (М§4.3, §15.2 п. 10): приращение закрываемого квартала — с его весом ω_Δ, как в клетке
    delta1 = None if prep.oa_delta is None else prep.oa_delta[1]
    drift = 0.0
    for key, share in p.items():
        c = base_run.cell(*key)
        bal = {b: float(c.books[b]["balance"][1]) for b in roles.names}
        base = plain.rwa({b: bal[b] for b in roles.loans}, bal[SECURITIES], bal[LIQUIDITY],
                         float(c.quarters["other_assets"][1]), 1.0, 1.0, delta1)
        drift += share * float(c.quarters["rwa"][1]) / base
    if delta1 is None:
        fixed = float(B["other_assets_fixed"]) if "other_assets_fixed" in B else plain.oa_fixed
        w = replace(plain, oa_fixed=fixed) if plain.oa_fixed else plain
        rwa = drift * w.rwa({b: float(B["books"][b]) for b in roles.loans}, float(B["books"][SECURITIES]),
                            float(B["books"][LIQUIDITY]), float(B["other_assets"]), 1.0, 1.0)
    else:                                        # постоянная часть отчёта — уровень прежней книги плюс приращение
        fixed = float(B["other_assets_fixed"]) if "other_assets_fixed" in B else plain.oa_fixed + delta1
        rwa = drift * plain.rwa({b: float(B["books"][b]) for b in roles.loans}, float(B["books"][SECURITIES]),
                                float(B["books"][LIQUIDITY]), float(B["other_assets"]), 1.0, 1.0,
                                fixed - plain.oa_fixed)
    by_scenario: dict[str, float] = {}
    for (_, _, s), share in p.items():
        by_scenario[s] = by_scenario.get(s, 0.0) + share
    dpp20 = sum(v * prep.scenarios[s].ded_pp20[1] for s, v in by_scenario.items())
    dpp11 = sum(v * prep.scenarios[s].ded_pp11[1] for s, v in by_scenario.items())
    t2 = float(prep.t2[1]) if prep.t2_from != 1 else float(prep.t2[0]) * rwa / prep.rwa0   # доля якоря на RWA оценки
    f = float(book.get("capital.n20.fvoci_recognition"))
    at1 = float(B.get("at1", old.at1))
    k20 = (float(C["n20_0"]) - float(book.get("capital.n20.gap_pp")) + dpp20) * rwa
    k11 = (float(C["n1_1_bank"]) - float(book.get("capital.n11.gap_pp")) + dpp11) * rwa
    levels = {"basel_rwa": rwa, "basel_cet1": k20 + (1 - f) * float(B["fvoci_reserve"]) - at1 - t2,
              "bank_base_capital": k11, "t2": t2}
    out = copy.deepcopy(dict(report))
    moved = {k: (C.get(k), _r(v, 6)) for k, v in levels.items()}
    out["capital"].update({k: v for k, (_, v) in moved.items()})
    return out, moved


def pending_deduction(book: Book, facts: Facts) -> float:
    """DPreg якоря при квартальном календаре (М§4.11, §5.7.4): суммы списка «объявлено, не выплачено», вычет
    которых из регуляторного капитала ещё впереди, — так, как их ставит в очередь ядро."""
    if not is_quarterly(book):
        return 0.0
    calendar = make_context(book, facts).prep.calendar
    return sum(amount for _, reg_q, amount in calendar.payable if reg_q >= 1)


def _share_axes(X: dict, share: str) -> list[tuple[str, dict, tuple[str, ...]]]:
    """Оси книги, которые двигают ключ доли `share`: (где, ось, ключи концов)."""
    return [(where, axis, keys) for where, axes, keys in _axis_lists(X) for axis in axes
            if share in [str(p) for p in axis.get("paths") or []]]


def _carry_end(v: float, factor: float) -> float:
    """Конец оси доли вычета якоря или край отрезка поиска строки обратного расчёта (значение доли) — суммой в
    рублях: тем же множителем, что центр; стоящий ровно на границе 0 или 1 остаётся на ней — граница говорит о доле
    («постоянной части нет», «весь вычет постоянен»), а не о сумме в рублях (М§15.2 п. 3, как у осей долей передачи
    ставки)."""
    if v in SHARE_BOUNDS:
        return v
    return _r(v * factor, SHARE_DIGITS)


def _on_bound(value: float) -> float | None:
    """Граница доли, на которой стоит значение (с допуском записи `BOUND_TOL`), или None."""
    return next((b for b in SHARE_BOUNDS if abs(value - b) <= BOUND_TOL), None)


def _carry_step(v: float, eta: float, fresh: float, factor: float) -> float:
    """Конец оси-сдвига по доле — приращение: в книгу ложится доля плюс приращение. Конец, стоящий на границе
    (доля плюс приращение — ровно 0 или 1), остаётся на ней: новое приращение — граница минус новая доля; прочие
    — тем же множителем (сумма в рублях на конце прежняя)."""
    bound = _on_bound(eta + v)
    if bound is not None:
        return _r(bound - fresh, SHARE_DIGITS)
    return _r(v * factor, SHARE_DIGITS)


def _share_ends(axis: dict, keys: Sequence[str], share: str, eta: float) -> list[float]:
    """Концы оси (или края отрезка поиска) по доле `share` значениями доли: у связки — её значение на конце, у
    оси-числа — сам конец, у оси-сдвига — доля плюс приращение."""
    if axis.get("kind") == BUNDLE:
        return [float(axis[k][share]) for k in keys if isinstance(axis.get(k), dict) and _num(axis[k].get(share))]
    vals = [float(v) for k in keys for v in (axis.get(k) if isinstance(axis.get(k), list) else [axis.get(k)])
            if _num(v)]
    return [eta + v for v in vals] if axis.get("kind") == "shift" else vals


def carry_fixed_shares(X: dict, old: Book, deductions: Mapping[str, float], derived: dict) -> None:
    """Доли вычета якоря, постоянные в рублях (М§4.11), переносятся суммой (М§15.2 п. 3): постоянная в рублях
    часть вычета каждого норматива остаётся прежней, доля переписывается на вычет нового якоря —
    `η_j′ = η_j × Ded_j,0 / Ded_j,0′`, то есть `Dfix_j′ = Dfix_j`. `deductions` — вычеты якоря кандидата, какими их
    прочтёт ядро (число книги или значение слова `anchor`); вычеты прежней книги — так же, из `old`. Тогда
    нормативы клетки, перезаякоренной на своём пути, — прежние во всех кварталах при любом разделе слагаемого
    якоря между вычетом и поправкой (свойство 7 М§4.11). Конец оси на пути доли идёт за центром тем же
    множителем: сумма в рублях на конце оси прежняя (у оси-сдвига конец — приращение доли, множитель тот же).
    **Граница остаётся границей:** конец оси и край отрезка поиска, стоящие ровно на 0 или 1, остаются на ней
    (`_carry_end`, `_carry_step`); центр доли границей не считается. Доля 0 остаётся нулём и при вычете нового
    якоря не больше нуля (концы осей на границе — тоже на месте). Новая доля больше нуля или конец оси внутри
    (0; 1), ушедшие за [0; 1] (постоянная сумма больше вычета нового якоря или вычет нового якоря не больше нуля),
    — отказ с названным путём: пересмотр доли — решение книги. У книги без ключей доли шага нет."""
    carried: dict[str, dict[str, float]] = {}
    # Вычет кандидата записан с округлением: сумма «ровно весь вычет» (доля 1 на своём пути) из-за последнего знака
    # записи отказом не становится — превышение в пределах половины шага записи читается как доля 1.
    half_step = 0.5 * 10 ** -DEDUCTION_DIGITS
    for share, ded in FIXED_SHARES:
        eta = _get(X, share)
        if eta is None:
            continue
        was, now = float(old.get(ded)), float(deductions[ded])
        amount = float(eta) * was
        axes = _share_axes(X, share)
        if not now > 0:
            # переносить долей нечего: доля 0 остаётся нулём, концы осей на границе — на ней; внутри (0; 1) — отказ
            inner = [v for _, axis, keys in axes for v in _share_ends(axis, keys, share, float(eta))
                     if _on_bound(v) is None]
            if float(eta) == 0 and not inner:
                continue                         # постоянной части нет: ноль остаётся нулём
            raise ReportError(
                f"{share}: вычет нового якоря {ded} = {now:.3f} млрд ₽ не больше нуля — постоянную в рублях часть "
                f"{amount:.3f} млрд ₽ (доля {float(eta):g}"
                + (f", концы оси внутри (0; 1): {', '.join(f'{v:.6f}' for v in inner)}" if inner else "")
                + ") долей вычета не записать; пересмотр доли — решение книги (М§15.2 п. 3)")
        factor = was / now
        fresh = float(eta) * factor
        if 1.0 < fresh and amount <= now + half_step:
            fresh = 1.0
        if not 0.0 <= fresh <= 1.0:
            raise ReportError(
                f"{share}: постоянная в рублях часть вычета {amount:.3f} млрд ₽ (доля {float(eta):g} вычета прежнего "
                f"якоря {was:.3f}) — вне вычета нового якоря {now:.3f} млрд ₽: новая доля {fresh:.6f} вне [0; 1]; "
                "пересмотр доли — решение книги (М§15.2 п. 3)")
        fresh = _r(fresh, SHARE_DIGITS)
        _set(X, share, fresh)
        for where, axis, keys in axes:
            paths = [str(p) for p in axis.get("paths") or []]
            name, kind = axis.get("name"), axis.get("kind")
            if kind == BUNDLE:
                ends = [axis[key] for key in keys if isinstance(axis.get(key), dict) and _num(axis[key].get(share))]
                for table in ends:
                    table[share] = _carry_end(float(table[share]), factor)
                moved = [float(table[share]) for table in ends]
            else:
                if len(paths) != 1:
                    raise ReportError(
                        f"{where} «{name}»: ось двигает {', '.join(paths)} одним числом, а доля вычета якоря {share} "
                        "переносится своим множителем — разделить ось или задать связку (решение книги)")
                if kind == "shift":              # конец оси-сдвига — приращение: в книгу ложится доля плюс приращение
                    _move_axis(axis, keys, lambda v, factor=factor, eta=float(eta), fresh=fresh:
                               _carry_step(v, eta, fresh, factor))
                else:
                    _move_axis(axis, keys, lambda v, factor=factor: _carry_end(v, factor))
                moved = _share_ends(axis, keys, share, fresh)
            out = [v for v in moved if not -1e-12 <= v <= 1.0 + 1e-12]
            if out:
                raise ReportError(
                    f"{where} «{name}»: конец оси на пути {share} после переноса суммы в рублях — "
                    f"{', '.join(f'{v:.6f}' for v in out)}, вне [0; 1] (вычет якоря {was:.3f} → {now:.3f} млрд ₽): "
                    "пересмотр доли и её оси — решение книги (М§15.2 п. 3)")
        carried[share] = {"was": float(eta), "now": fresh, "amount": amount, "deduction_was": was,
                          "deduction_now": now}
    if carried:
        derived["fixed_shares"] = carried


def fixed_share_line(d: Mapping) -> str | None:
    """Строка отчёта о долях вычета якоря, постоянных в рублях: обе суммы в рублях рядом с новыми долями."""
    carried = d.get("fixed_shares")
    if not carried:
        return None
    return ("- доли вычета якоря, постоянные в рублях, перенесены суммой (сумма в рублях прежняя, доля — на вычет "
            "нового якоря): " + "; ".join(
                f"`{share}` {row['was']:.6g} → {row['now']:.6g} — сумма {row['amount']:.3f} млрд ₽ при вычете якоря "
                f"{row['deduction_was']:.3f} → {row['deduction_now']:.3f}" for share, row in carried.items()))


def carry_fixed_change(X: dict, old_anchor: str, period: str, report: Mapping, derived: dict,
                       warnings: list[str]) -> None:
    """Путь постоянной части прочих активов (`volumes.other_assets_fixed_change`, М§4.3) переносится от нового якоря
    (М§15.2 п. 3): приращение квартала нового якоря `Δ_1 = v(новый якорь) − v(прежний якорь)` переходит в число
    постоянной части (`volumes.other_assets_fixed′ = volumes.other_assets_fixed + Δ_1`; у слова `anchor` — узел
    фактов отчёта, в котором оно уже есть), а из каждого значения траектории (ключи квартала, полугодия, года и `LT`;
    `LT_from` — прежний) вычитается `Δ_1`: постоянная часть каждого квартала прежняя, в квартале нового якоря
    приращение — ноль (якорное условие). Концы осей вида `value` на путях траектории — тем же вычитанием (у оси-сдвига
    конец — приращение, он прежний), конец оси на числе постоянной части — тем же прибавлением. Концы осей-связок и
    подмены справочных вариантов, которые ведут путь или число, — тем же правилом со СВОИМ приращением квартала нового
    якоря (`carry_fixed_ends`). При `Δ_1 = 0` центр не меняется (концы со своим приращением — переносятся). Без ключа
    пути шага нет."""
    traj = _get(X, FIXED_CHANGE)
    if traj is None:
        return
    t = Trajectory(traj)
    delta = t.value(*parse_period(period)) - t.value(*parse_period(old_anchor))
    level = _get(X, FIXED_LEVEL)
    row: dict[str, Any] = {"delta": delta, "was": level, "now": level}
    derived["fixed_change"] = row
    ends = fixed_ends(X, old_anchor, period)         # свои приращения концов — по траектории центра ДО переноса
    center = copy.deepcopy(traj)
    for where, axes, keys in _axis_lists(X):         # ось value на ключе пути со своим приращением — отказ
        for axis in axes:
            paths = [str(p) for p in axis.get("paths") or []]
            if axis.get("kind") == "value" and len(paths) == 1 and _under(paths[0], (FIXED_CHANGE,)):
                _value_axis_increments(axis, keys, paths[0], center, old_anchor, period, delta, where)
    if delta == 0:
        row["ends"] = carry_fixed_ends(X, ends, center, level, delta, period, warnings)
        return
    if level == "anchor":
        row["in_report"] = "other_assets_fixed" in report["balance"]     # число нового якоря — в узле фактов отчёта
        if "other_assets_fixed" not in report["balance"]:
            warnings.append(
                f"{FIXED_LEVEL}: книга выводит постоянную часть словом anchor, а отчёт не несёт "
                f"balance.other_assets_fixed — приращение пути в квартале нового якоря {delta:.3f} млрд ₽ в узел фактов "
                "не вошло (взято значение прежних фактов); внести постоянную часть нового якоря в отчёт (М§15.2 п. 3)")
    else:
        now = _r(float(level or 0.0) + delta, FIXED_DIGITS)
        _set(X, FIXED_LEVEL, now)
        row["now"] = now
    move = lambda v: _r(float(v) - delta, FIXED_DIGITS)  # noqa: E731
    if _num(traj):
        _set(X, FIXED_CHANGE, move(traj))
    else:
        _set(X, FIXED_CHANGE, {k: (v if str(k) == "LT_from" else move(v)) for k, v in traj.items()})
    up = lambda v: _r(float(v) + delta, FIXED_DIGITS)  # noqa: E731  (конец оси на числе постоянной части)
    for _, axes, keys in _axis_lists(X):
        for axis in axes:
            paths = [str(p) for p in axis.get("paths") or []]
            kind = axis.get("kind")
            for p in paths:
                rule = move if _under(p, (FIXED_CHANGE,)) else up if p == FIXED_LEVEL and level != "anchor" else None
                if rule is None or kind != "value" or paths != [p]:
                    continue                    # связки — своим приращением (`carry_fixed_ends`), сдвиг — прежний
                _move_axis(axis, keys, rule)
    row["ends"] = carry_fixed_ends(X, ends, center, level, delta, period, warnings)
    row["path_now"] = copy.deepcopy(_get(X, FIXED_CHANGE))


END_TOL = 1e-9          # млрд ₽: своё приращение конца «равно» приращению центра; траектория конца — в допуске записи
FIXED_DENSITIES = ("capital.rwa.density.other_assets_fixed", "capital.rwa.density.other_assets_fixed_change")


def _on_fixed_path(path: str) -> bool:
    """Путь числа постоянной части прочих активов или её траектории (ключом или целиком)."""
    return path == FIXED_LEVEL or _under(path, (FIXED_CHANGE,))


def _fixed_subs(table: Mapping) -> list[str]:
    """Подмены семейства постоянной части в словаре конца связки или подмен варианта: число, траектория (ключом или
    целиком) и обе плотности — в порядке словаря."""
    return [str(p) for p in table if _on_fixed_path(str(p)) or str(p) in FIXED_DENSITIES]


def _traj_key(path: str) -> str:
    return path[len(FIXED_CHANGE) + 1:]


def _composed(center: Any, table: Mapping, subs: Sequence[str]) -> Any:
    """Траектория пути постоянной части у конца связки или варианта: центр книги с подменами конца (ключ траектории —
    заменой ключа, путь целиком — заменой траектории), как её собирают схема и ядро."""
    tj = copy.deepcopy(center)
    for p in subs:
        if p == FIXED_CHANGE:
            tj = copy.deepcopy(table[p])
        elif _under(p, (FIXED_CHANGE,)) and isinstance(tj, Mapping):
            key = _traj_key(p)
            tj = {**{k: v for k, v in tj.items() if str(k) != key}, key: table[p]}
    return tj


def _increment(traj: Any, old_anchor: str, period: str) -> float:
    """Приращение квартала нового якоря: разность значений траектории в кварталах нового и прежнего якоря."""
    t = Trajectory(traj)
    return t.value(*parse_period(period)) - t.value(*parse_period(old_anchor))


def _value_axis_increments(axis: dict, keys: Sequence[str], path: str, center: Any, old_anchor: str, period: str,
                           delta: float, where: str) -> None:
    """Ось вида `value` на ключе пути постоянной части: её конец переносится вычитанием `Δ_1` только тогда, когда
    своё приращение квартала нового якоря у конца — то же `Δ_1` (ключ не задаёт значение квартала нового якоря).
    Иначе концу нужно своё число постоянной части, а ось одного пути его не несёт — отказ с причиной."""
    for key in keys:
        raw = axis.get(key)
        for v in (raw if isinstance(raw, list) else [raw]):
            if not _num(v):
                continue
            own = _increment(_composed(center, {path: v}, [path]), old_anchor, period)
            if abs(own - delta) > END_TOL:
                raise ReportError(
                    f"{where} «{axis.get('name')}»: ось вида value на `{path}` — конец {_fmt(v)} несёт своё приращение "
                    f"пути постоянной части в квартале нового якоря {period} ({own:.3f} млрд ₽ при Δ_1 = {delta:.3f}): "
                    "его перенос двигает и число постоянной части, а ось одного пути его не несёт (решение книги: "
                    "ось-связка с `volumes.other_assets_fixed` или концы на новом якоре, М§15.2 п. 3)")


def fixed_ends(X: dict, old_anchor: str, period: str) -> list[dict[str, Any]]:
    """Концы осей-связок и подмены справочных вариантов, которые ведут путь постоянной части прочих активов или её
    число (М§10, §14.5, §15.2 п. 3). У каждого конца — своя траектория (центр книги с подменами конца) и своё
    приращение квартала нового якоря `δ = v_конца(новый якорь) − v_конца(прежний якорь)`. Считается ДО переноса
    центра: группа — связка (оба конца) или вариант."""
    center = _get(X, FIXED_CHANGE)
    groups: list[dict[str, Any]] = []

    def end(table: dict, key: str | None) -> dict[str, Any]:
        subs = _fixed_subs(table)
        traj = _composed(center, table, subs)
        return {"key": key, "table": table, "subs": subs, "traj": traj,
                "delta": _increment(traj, old_anchor, period)}

    for where, axis, keys in _bundles(X):
        if any(_on_fixed_path(str(p)) for p in axis.get("paths") or []):
            groups.append({"kind": BUNDLE, "name": f"{where} «{axis.get('name')}»", "axis": axis,
                           "ends": [end(axis[k], k) for k in keys if isinstance(axis.get(k), dict)]})
    for variant in _get(X, VARIANTS) or []:
        ov = variant.get("overrides") if isinstance(variant, Mapping) else None
        if isinstance(ov, dict) and any(_on_fixed_path(str(p)) for p in ov):
            groups.append({"kind": "variant", "name": f"вариант «{variant.get('id')}»", "id": str(variant.get("id")),
                           "ends": [end(ov, None)]})
    return groups


def carry_fixed_ends(X: dict, groups: list[dict[str, Any]], center: Any, level: Any, delta: float, period: str,
                     warnings: list[str]) -> list[dict[str, Any]]:
    """Концы осей-связок и подмены справочных вариантов на пути постоянной части (`fixed_ends`) — тем же правилом, что
    центр, со СВОИМ приращением δ квартала нового якоря (М§15.2 п. 3): число конца `+ δ`, каждое значение его
    траектории `− δ`. Постоянная часть каждого квартала на конце прежняя, в квартале нового якоря приращение конца —
    ноль (якорное условие на каждом конце). Конец без своего числа при `δ ≠ Δ_1` получает число `L + δ` (L — число
    прежней книги; у связки — путь `volumes.other_assets_fixed` на обоих концах). Ключи центра, которых конец не несёт,
    сдвинуты вместе с центром на `Δ_1`; если от этого траектория конца в квартале сетки расходится со своей `v − δ`, они
    входят в конец со значениями `ключ − δ` (у связки — путями оси). Число словом `anchor` своего числа концу не даёт:
    связка — отказ, вариант остаётся записью на прежнем якоре (предупреждение, ручной шаг). Плотность ω_oaf концов —
    `carry_fixed_density` со своими L и δ. Возвращает перенесённое по группам (для отчёта и плотности)."""
    last = str(_get(X, "meta.last_period"))
    grid = [period_str(*shift_quarter(*parse_period(period), i)) for i in range(pindex(last) - pindex(period) + 1)]
    now_center = _get(X, FIXED_CHANGE)
    out = []
    for g in groups:
        ends = g["ends"]
        lone = [e for e in ends if FIXED_LEVEL not in e["subs"] and abs(e["delta"] - delta) > END_TOL]
        word = [e for e in ends if FIXED_LEVEL in e["subs"] and not _num(e["table"][FIXED_LEVEL])
                and abs(e["delta"] - delta) > END_TOL]
        if (lone and not (level is None or _num(level))) or word:
            text = (f"{g['name']}: своё приращение пути постоянной части в квартале нового якоря {period} — "
                    + ", ".join(f"{e['delta']:.3f}" for e in ends) + f" млрд ₽ при Δ_1 = {delta:.3f}, а число "
                    "постоянной части — словом anchor: своего числа концу не дать")
            if g["kind"] == BUNDLE:
                raise ReportError(f"ось-связка {text} (решение книги: число постоянной части числом или концы на новом "
                                  "якоре, М§15.2 п. 3)")
            warnings.append(f"справочный {text} — подмены остались записью на прежнем якоре: пересчитать на новом "
                            "якоре (решение книги, М§15.2 п. 3)")
            out.append({**g, "skipped": True})
            continue
        base = 0.0 if level is None or not _num(level) else float(level)
        rows = []
        for e in ends:
            d, tab = e["delta"], e["table"]
            own = FIXED_LEVEL in e["subs"]
            e["L"] = float(tab[FIXED_LEVEL]) if own and _num(tab[FIXED_LEVEL]) else (
                None if level == "anchor" else base)
            row = {"key": e["key"], "delta": d, "level": None}
            if own and _num(tab[FIXED_LEVEL]):
                row["level"] = (tab[FIXED_LEVEL], _r(float(tab[FIXED_LEVEL]) + d, FIXED_DIGITS))
            for p in e["subs"]:
                if d == 0:
                    break
                if p == FIXED_CHANGE:
                    tab[p] = (_r(float(tab[p]) - d, FIXED_DIGITS) if _num(tab[p]) else
                              {k: (v if str(k) == "LT_from" else _r(float(v) - d, FIXED_DIGITS)) for k, v in tab[p].items()})
                elif _under(p, (FIXED_CHANGE,)):
                    tab[p] = _r(float(tab[p]) - d, FIXED_DIGITS)
                elif p == FIXED_LEVEL and _num(tab[p]):
                    tab[p] = row["level"][1]
            rows.append(row)
        added: list[str] = []
        if lone:                                 # своё число концу: L + δ (у связки — на обоих концах)
            added.append(FIXED_LEVEL)
            for e, row in zip(ends, rows):
                e["table"][FIXED_LEVEL] = _r(e["L"] + e["delta"], FIXED_DIGITS)
                row["level"] = (None, e["table"][FIXED_LEVEL])
        if isinstance(center, Mapping) and not any(FIXED_CHANGE in e["subs"] for e in ends):
            off = False
            for e in ends:                       # траектория конца после переноса против своей `v − δ`
                after, was = Trajectory(_composed(now_center, e["table"], e["subs"])), Trajectory(e["traj"])
                off = off or any(abs(after.value(*parse_period(q)) - (was.value(*parse_period(q)) - e["delta"]))
                                 > END_TOL for q in grid)
            if off:                              # ключи центра, которых конец не несёт, — в конец: ключ − δ
                carried = {_traj_key(p) for e in ends for p in e["subs"] if _under(p, (FIXED_CHANGE,))}
                for k, v in center.items():
                    if str(k) == "LT_from" or str(k) in carried or not _num(v):
                        continue
                    path = f"{FIXED_CHANGE}.{k}"
                    added.append(path)
                    for e in ends:
                        e["table"][path] = _r(float(v) - e["delta"], FIXED_DIGITS)
        for e in ends:
            e["subs"] = _fixed_subs(e["table"])
        if added and g["kind"] == BUNDLE:
            g["axis"]["paths"] = list(g["axis"].get("paths") or []) + added
        out.append({**g, "rows": rows, "added": added})
    return out


def fixed_change_line(d: Mapping) -> str | None:
    """Строка отчёта о переносе пути постоянной части прочих активов: приращение нового якоря и число; плотность
    постоянной части — прежняя и перенесённая (М§15.2 п. 3)."""
    row = d.get("fixed_change")
    if not row:
        return None
    ends = fixed_ends_text(row)
    if not row["delta"]:
        return None if ends is None else "- " + ends
    dens = row.get("density")
    return (f"- путь постоянной части прочих активов перенесён от нового якоря: приращение квартала нового якоря "
            f"Δ_1 = {row['delta']:.3f} млрд ₽ — в число `{FIXED_LEVEL}` {_fmt(row['was'])} → {_fmt(row['now'])}, "
            f"траектория `{FIXED_CHANGE}` — минус Δ_1"
            + (f"; плотность постоянной части `{FIXED_DENSITY}` ω_oaf {_fmt(dens['was'])} → ω_oaf′ {_fmt(dens['now'])} "
               f"(вес приращения ω_Δ {_fmt(dens['omega_delta'])}, ушедшего в число; до общего множителя плотностей)"
               if dens else "")
            + ("; " + ends if ends else ""))


def fixed_ends_text(row: Mapping) -> str | None:
    """Концы связок и подмены вариантов на пути постоянной части, перенесённые своим приращением δ (М§15.2 п. 3): δ
    конца, число конца было → стало, плотность ω_oaf конца (до общего множителя) и пути, которые конец получил."""
    parts = []
    for g in row.get("ends") or []:
        if g.get("skipped"):
            parts.append(f"{g['name']} — не перенесён (число словом anchor; ручной шаг)")
            continue
        if not any(r["delta"] for r in g["rows"]) and not g["added"]:
            continue
        ends = []
        for r, e in zip(g["rows"], g["ends"]):
            lv, dens = r["level"], e.get("density")
            ends.append((f".{r['key']} " if r["key"] else "") + f"δ {r['delta']:.3f}"
                        + (f", число {_fmt(lv[0]) if lv[0] is not None else '— (центр)'} → {_fmt(lv[1])}" if lv else "")
                        + (f", ω_oaf {_fmt(dens[0]) if dens[0] is not None else '— (центр)'} → {_fmt(dens[1])}"
                           if dens else ""))
        parts.append(f"{g['name']}: " + "; ".join(ends)
                     + (" (добавлены пути: " + ", ".join(f"`{p}`" for p in g["added"]) + ")" if g["added"] else ""))
    if not parts:
        return None
    return ("концы осей-связок и подмены справочных вариантов на пути постоянной части — тем же правилом со своим "
            "приращением δ квартала нового якоря (число конца + δ, путь − δ, ω_oaf — своими L и δ): " + " | ".join(parts))


def carried_variants(derived: Mapping) -> list[str]:
    """Идентификаторы справочных вариантов, перенесённых на пути постоянной части своим приращением."""
    return [g["id"] for g in (derived.get("fixed_change") or {}).get("ends") or []
            if g["kind"] != BUNDLE and not g.get("skipped")]


def check_fixed_variants(cand: Book, derived: Mapping) -> None:
    """Книга каждого перенесённого справочного варианта на пути постоянной части проходит схему ядра на новом якоре
    (якорное условие, знак суммы — М§4.3, прил. A № 24): иначе таблицы книги упали бы на варианте позже и не здесь."""
    ids = set(carried_variants(derived))
    for spec in cand.opt(VARIANTS) or []:
        if str(spec.get("id")) in ids:
            try:
                cand.with_overrides(dict(spec["overrides"]), create=True)
            except BookError as exc:
                raise ReportError(f"справочный вариант «{spec.get('id')}» после переноса пути постоянной части не "
                                  f"проходит схему ядра: {exc}") from None


FIXED_DENSITY = f"{DENSITY}.other_assets_fixed"              # ω_oaf — плотность постоянной части прочих активов
CHANGE_DENSITY = f"{DENSITY}.other_assets_fixed_change"      # ω_Δ — плотность приращения (без ключа — ω_oaf)
DENSITY_DIGITS = 12                                          # ω_oaf′ — с этим числом знаков (дальше — общий множитель)


def carried_density(w_fixed: float, w_change: float, level: float, delta: float) -> float:
    """ω_oaf′ = (ω_oaf × L + ω_Δ × Δ_1) / (L + Δ_1) (М§15.2 п. 3): приращение Δ_1, ушедшее в число постоянной части,
    весило ω_Δ, а число весит ω_oaf — плотность нового числа средняя двух частей, и RWA постоянной части каждого
    квартала прежние. При L + Δ_1 = 0 постоянной части нет — плотность прежняя; при L = 0 — ω_Δ."""
    if level + delta == 0:
        return w_fixed
    if level == 0:
        return w_change
    return (w_fixed * level + w_change * delta) / (level + delta)


def carry_fixed_density(X: dict, derived: dict, warnings: list[str], level_value: float | None = None) -> None:
    """Плотность постоянной части прочих активов переносится вместе с числом (М§15.2 п. 3, REANCHOR §3.3) — до общего
    множителя плотностей (`calibrate_capital`): на своём пути множитель тогда — только индекс плотности, курса и
    множитель режима. `level_value` — L прежней книги, когда число стоит словом `anchor` (узел фактов прежнего якоря).
    Центр и оси на ω_oaf — `_carry_center_density`; концы связок и подмены вариантов, которые ведут путь или число, —
    той же формулой со своими L и δ (`carry_end_densities`). Без пути шага нет."""
    row = derived.get("fixed_change")
    if not row:
        return
    dens = X["capital"]["rwa"]["density"]
    w_fixed, w_change = dens.get("other_assets_fixed"), dens.get("other_assets_fixed_change")
    _carry_center_density(X, derived, warnings, level_value)
    carry_end_densities(X, row, w_fixed, w_change, level_value, warnings)


def carry_end_densities(X: dict, row: Mapping, w_fixed: Any, w_change: Any, level_value: float | None,
                        warnings: list[str]) -> None:
    """Плотность постоянной части на концах связок и в подменах вариантов, которые ведут путь или число (М§15.2 п. 3):
    `ω′ = (ω × L + ω_Δ × δ) / (L + δ)` со своими L и δ конца; ω и ω_Δ — свои на конце, иначе прежней книги (без ключа
    ω_Δ вес приращения — ω: плотность прежняя). Конец без своей ω_oaf получает её (у связки — путь на обоих концах),
    когда своё ω′ расходится с перенесённой плотностью центра. До общего множителя плотностей: связки идут за ним
    концами, варианты — `calibrate_capital`. Число словом `anchor` без узла отчёта — плотности концов прежние."""
    if w_change is None and not any(FIXED_DENSITIES[1] in e["subs"] for g in row.get("ends") or [] for e in g["ends"]):
        return                                   # вес приращения — ω_oaf у всех концов: плотности прежние
    center_now = X["capital"]["rwa"]["density"].get("other_assets_fixed")
    for g in row.get("ends") or []:
        if g.get("skipped"):
            continue
        targets = []
        for e in g["ends"]:
            tab = e["table"]
            w = tab.get(FIXED_DENSITY, w_fixed) if FIXED_DENSITY in e["subs"] else w_fixed
            wd = tab.get(CHANGE_DENSITY) if CHANGE_DENSITY in e["subs"] else w_change
            big_l = e["L"] if e["L"] is not None else (
                level_value if row["was"] == "anchor" and row.get("in_report") else None)
            if not _num(w) or big_l is None:
                targets = []
                break
            now = float(w) if wd is None else _r(carried_density(float(w), float(wd), big_l, e["delta"]), DENSITY_DIGITS)
            if now < 0:
                raise ReportError(f"{g['name']}: плотность постоянной части конца после переноса якоря {now:.6f} < 0 — "
                                  f"своё приращение δ = {e['delta']:.3f} млрд ₽ весило ω_Δ больше всего числа конца "
                                  "(М§15.2 п. 3); плотности пересмотреть (решение книги)")
            targets.append(now)
        if not targets:
            continue
        own = [FIXED_DENSITY in e["subs"] for e in g["ends"]]
        if not any(own) and all(_num(center_now) and abs(t - float(center_now)) <= 1e-12 for t in targets):
            continue                             # конец весит как центр: своей плотности не нужно
        for e, now, has in zip(g["ends"], targets, own):
            was = e["table"].get(FIXED_DENSITY) if has else None
            e["table"][FIXED_DENSITY] = now
            e["density"] = (was, now)
        if not all(own):
            g["added"].append(FIXED_DENSITY)
            for e in g["ends"]:
                e["subs"] = _fixed_subs(e["table"])
            if g["kind"] == BUNDLE:
                g["axis"]["paths"] = list(g["axis"].get("paths") or []) + [FIXED_DENSITY]


def _carry_center_density(X: dict, derived: dict, warnings: list[str], level_value: float | None = None) -> None:
    """Центр и оси на ω_oaf (шестой проход): ω_oaf′ = (ω_oaf L + ω_Δ Δ_1) / (L + Δ_1). Конец оси-значения и связки на
    ω_oaf, которая не ведёт путь и число, — той же формулой со своим значением; ось на ω_Δ при Δ_1 ≠ 0 одним числом не
    переносится — предупреждение с путём. При Δ_1 = 0 шага нет."""
    row = derived.get("fixed_change")
    if not row or not row["delta"]:
        return
    delta = float(row["delta"])
    level = level_value if row["was"] == "anchor" else float(row["was"] or 0.0)
    if level is None or (row["was"] == "anchor" and not row.get("in_report")):
        return                               # число нового якоря отчёт не назвал (предупреждение уже есть)
    dens = X["capital"]["rwa"]["density"]
    w_change = dens.get("other_assets_fixed_change")
    if w_change is None:                     # без ключа ω_Δ вес приращения — ω_oaf: плотность прежняя
        return
    w_fixed = dens.get("other_assets_fixed")
    if w_fixed is None:                      # постоянной части у прежней книги не было: L = 0, плотность — ω_Δ
        if level or not level + delta:
            return
        w_fixed = w_change
        warnings.append(f"{FIXED_DENSITY}: постоянная часть нового якоря {level + delta:.3f} млрд ₽ создана путём; её "
                        "плотность записана плотностью приращения (решение книги)")
    move = lambda w: _r(carried_density(float(w), float(w_change), level, delta), DENSITY_DIGITS)  # noqa: E731
    now = move(w_fixed)
    if now < 0:
        raise ReportError(f"{FIXED_DENSITY}: плотность постоянной части после переноса якоря {now:.6f} < 0 — приращение "
                          f"Δ_1 = {delta:.3f} млрд ₽ весило ω_Δ = {float(w_change):g} больше всего числа (М§15.2 п. 3); "
                          "плотности пересмотреть (решение книги)")
    row["density"] = {"was": dens.get("other_assets_fixed"), "now": now, "omega_delta": float(w_change)}
    dens["other_assets_fixed"] = now
    for _, axes, keys in _axis_lists(X):
        for axis in axes:
            paths = [str(p) for p in axis.get("paths") or []]
            kind = axis.get("kind")
            if kind == BUNDLE and any(_on_fixed_path(p) for p in paths):
                continue                         # связка на пути или числе — своими L и δ (`carry_end_densities`)
            if CHANGE_DENSITY in paths:
                warnings.append(f"ось «{axis.get('name', '?')}» по `{CHANGE_DENSITY}`: плотность приращения при Δ_1 = "
                                f"{delta:.3f} млрд ₽ одним числом не переносится (её конец двигал бы и вес части, ушедшей в "
                                "число) — пересчитать ось на новом якоре (решение книги, М§15.2 п. 3)")
            if FIXED_DENSITY not in paths:
                continue
            if kind == BUNDLE:
                for key in keys:
                    ends = axis.get(key)
                    if isinstance(ends, dict) and _num(ends.get(FIXED_DENSITY)):
                        ends[FIXED_DENSITY] = move(ends[FIXED_DENSITY])
            elif kind == "value" and paths == [FIXED_DENSITY]:
                _move_axis(axis, keys, move)
            else:
                warnings.append(f"ось «{axis.get('name', '?')}» по `{FIXED_DENSITY}` вида {kind}: конец не перенесён "
                                "формулой плотности постоянной части — пересчитать (решение книги, М§15.2 п. 3)")


def calibrate_capital(X: dict, new_facts: Facts, rwa_fact: float, derived: dict, warnings: list[str],
                      numbers: bool = False, old: Book | None = None) -> float:
    """Калибровки капитала к якорю (М§15.2 п. 3): вычеты — формулой книги на фактах якоря, плотности RWA и их
    оси — общим множителем к RWA якоря. Возвращает множитель плотностей. `numbers` — записать вычеты числами и
    там, где книга выводит их словом `anchor` (оценка нормативов: уровни капитала якоря — расчёт, не факт).
    `old` — прежняя книга: по её вычетам якоря доли вычета, постоянные в рублях, переписываются на вычеты нового
    якоря с прежней суммой в рублях (`carry_fixed_shares`).

    При квартальном календаре BVreg якоря несёт DPreg очереди вычетов якоря (М§4.11): вычет Н20.1 считается с
    ним — формула книги берёт вместо него весь остаток дивидендов к выплате при признаке `pre_dividend` и ноль
    без него. Разница стоит в поправке «норматив − расчёт» и на путь норматива не влияет: вычет идёт за RWA."""
    books = _get(X, "nii.books")
    probe_data = copy.deepcopy(X)
    for path in DEDUCTIONS:
        _set(probe_data, path, "anchor")
    probe = book_from_dict(probe_data, facts=new_facts)
    af = anchor_facts(new_facts, books)
    values = {path: float(probe.anchors[path]) for path in DEDUCTIONS}
    if is_quarterly(probe):
        queue = pending_deduction(probe, new_facts)
        values[DEDUCTIONS[1]] += queue - (af.dividends_payable if af.n20_pre_dividend else 0.0)
        derived["dpreg_anchor"] = queue
        if queue > DIV_TOL and not af.n20_pre_dividend:
            warnings.append(
                f"на якоре в очереди вычетов из регуляторного капитала стоят объявленные дивиденды {queue:.3f} млрд ₽ "
                "(вычет впереди по датам записи реестра или карте лагов книги), а отчёт помечает норматив как "
                "посчитанный после вычета (capital.n20_pre_dividend: false): модель вычтет их ещё раз в квартале "
                "вычета — проверить дату реестра записи или карту лагов (решение книги)")
    for path in DEDUCTIONS:
        if _get(X, path) != "anchor":
            _set(X, path, _r(values[path], DEDUCTION_DIGITS))
        elif numbers:                        # уровни капитала якоря — расчёт по оценке: канон фактов несёт на их месте
            _set(X, path, _r(values[path], DEDUCTION_DIGITS))   # уровни прошлой формы, и слово anchor вывело бы вычеты из них
            warnings.append(f"{path}: книга выводила вычет словом anchor; на время оценки нормативов он записан числом "
                            f"{values[path]:.3f} — вернуть anchor после замены оценки фактом формы (решение книги)")
    if old is not None:                      # вычеты кандидата — какими их прочтёт ядро: число или слово anchor
        carry_fixed_shares(X, old, {path: float(probe.anchors[path]) if _get(X, path) == "anchor"
                                    else float(_get(X, path)) for path in DEDUCTIONS}, derived)
    k_rwa = rwa_fact / rwa_anchor(rwa_weights(probe, book_roles(books)), af)
    centers = _bundle_centers(X, (DENSITY,))
    X["capital"]["rwa"]["density"] = {k: _r(float(v) * k_rwa, 6) for k, v in X["capital"]["rwa"]["density"].items()}
    _scale_axes(X, (DENSITY,), k_rwa)
    _follow_centers(X, centers, k_rwa)
    for variant in _get(X, VARIANTS) or []:  # подмены плотностей постоянной части у вариантов на её пути — как концы
        ov = variant.get("overrides") if isinstance(variant, Mapping) else None
        if isinstance(ov, dict) and any(_on_fixed_path(str(p)) for p in ov):
            for path in FIXED_DENSITIES:
                if _num(ov.get(path)):
                    ov[path] = _r(float(ov[path]) * k_rwa, 6)
    derived.update(rwa_factor=k_rwa, deductions={path: _get(X, path) for path in DEDUCTIONS})
    return k_rwa


def dividend_carry(old: GridRun, new: GridRun) -> dict[str, Any]:
    """Дивиденды по периодам при переносе якоря (раздел REANCHOR.md, М§15.2 п. 9): последний закрытый квартал
    прибыли до и после, строки истории, закрывшие кварталы, очередь «объявлено, не выплачено» с кварталами
    выплаты и вычета из регуляторного капитала, записи реестра — перешедшие в затравку и выпавшие из неё."""
    tl0, tl1 = old.ctx.timeline, new.ctx.timeline
    c0, c1 = old.ctx.prep.calendar, new.ctx.prep.calendar
    day0, day1 = (to_date(r.ctx.book.get("meta.facts_date")) for r in (old, new))
    f0, f1 = old.ctx.facts.file("dividends"), new.ctx.facts.file("dividends")
    closed = []
    for row in f1.get("history") or []:
        decided = _fact(row.get("decided_date"))
        if decided and day0 < to_date(decided) <= day1:
            closed.append({"period": str(_fact(row.get("period"))), "dps": history_dps(row), "decided_date": str(decided)})
    queue = []
    items = new.ctx.facts.file("balance").get("dividends_payable_declared") or []
    for item, (pay_q, reg_q, amount) in zip(items, c1.payable):
        queue.append({"period": str(_fact(item.get("period"))), "amount": amount, "pay": tl1.period(pay_q),
                      "reg": tl1.period(reg_q) if reg_q >= 1 else None})
    seeds = [{str(_fact(r.get("period"))) for r in f.get("register_seed") or []} for f in (f0, f1)]
    return {"p_last": (tl0.period(c0.p_last), tl1.period(c1.p_last)), "closed": closed, "queue": queue,
            "payable": new.ctx.prep.af.dividends_payable,
            "seed": sorted(seeds[1], key=pindex), "dropped": sorted(seeds[0] - seeds[1], key=pindex),
            "added": sorted(seeds[1] - seeds[0], key=pindex)}


@dataclass(frozen=True)
class CellRun:
    """Прогон одной клетки на общем контексте книги: всё, что перезаякоривание клетки на своём пути читает из
    прогона кандидата (контекст, строка якоря сценария, ряды клетки), — без остальных клеток сетки."""

    ctx: Any
    cells: tuple
    layers: Mapping[str, Any] = field(default_factory=dict)   # слои прогона, из которого взяты клетки (вероятности)

    def cell(self, world: str, regime: str, scenario: str) -> Any:
        for c in self.cells:
            if c.key == (world, regime, scenario):
                return c
        raise KeyError((world, regime, scenario))


def refuse_closed_contribution(run: Any) -> None:
    """Взнос акционеров закрываемого квартала (М§15.2 п. 13, REANCHOR §3.16). Правило переноса через квартал решения
    о взносе — ожидаемый отчёт с капиталом и числом акций по пути клетки, поправка делителя числом акций, строка
    «механика» на делителе каждой книги — инструмент пока не исполняет. Поэтому, если закрываемый квартал (первый
    прогнозный квартал прежней книги `run`) — квартал решения о взносе и хотя бы в одной клетке взнос в нём больше
    нуля, перенос — и на ожидаемом, и на фактическом отчёте — останавливается с причиной: иначе капитал нового
    якоря нёс бы взнос, а число акций было бы прежним, и «механика» молча показала бы взнос как стоимость.
    Квартал решения без взносов во всех клетках и прочие кварталы проходят общими правилами."""
    rule = run.ctx.prep.recap
    tl = run.ctx.timeline
    if rule is None or tl.Q < 1 or tl.h(1) != rule.quarter:
        return
    paid = [c for c in run.cells if (c.quarters["rec"][1] or 0.0) > 0]
    if not paid:
        return
    prob = (getattr(run, "layers", None) or {}).get("analytical")
    mass = None if prob is None else sum(prob.prob[c.key] for c in paid)
    amounts = [float(c.quarters["rec"][1]) for c in paid]
    raise ReportError(
        f"закрываемый квартал {tl.period(1)} — квартал решения о взносе акционеров ({RECAP_KEY}.decision_quarter = "
        f"{rule.quarter}), и взнос в нём стоит в {len(paid)} клетках из {len(run.cells)}"
        + ("" if mass is None else f" (масса в слое «свой взгляд» {mass:.3f})")
        + f", от {min(amounts):.1f} до {max(amounts):.1f} млрд ₽: ожидаемый отчёт обязан нести капитал и число "
        "акций по пути клетки — инструмент этого не умеет; перенос остановлен, чтобы капитал со взносом не делился "
        "на прежнее число акций (М§15.2 п. 13, docs/REANCHOR.md §3.16). Клетки: "
        + ", ".join(c.label for c in paid[:10]) + (" …" if len(paid) > 10 else ""))


def shares_note(book: Book, facts: Facts, report: Mapping) -> str | None:
    """Ручной шаг (REANCHOR §3.16): отчёт с изменившимся числом размещённых акций у книги с ненулевой поправкой
    делителя `valuation.share_count_adj` — если объявленный выпуск размещён, его акции уже в фактах нового якоря, и
    поправку вместе с притоком `equity.other_movements` пересматривает книга (иначе акции выпуска стояли бы в
    делителе дважды). Иначе — None."""
    adj = book.opt(SHARE_ADJ)
    got = (report.get("shares") or {}).get("issued_total")
    if not adj or got is None or "shares" not in facts.files:
        return None
    was = facts.file("shares").get("issued_total")
    was = _fact(was) if was is not None else None
    if was is None or abs(float(got) - float(was)) <= 1e-9:
        return None
    return (f"число размещённых акций в отчёте {float(got):.3f} млн шт. против {float(was):.3f} у прежнего якоря, а "
            f"книга несёт поправку делителя {SHARE_ADJ} = {adj}: если объявленный выпуск размещён, его акции уже в "
            "фактах нового якоря — пересмотреть поправку и приток equity.other_movements (решение книги), иначе акции "
            "выпуска встанут в делитель дважды (docs/REANCHOR.md §3.16)")


def candidate_run(data: Mapping, facts: Facts, cell: Sequence[str] | None) -> Any:
    """Прогон кандидата `data` на фактах нового якоря: вся сетка, а у клетки на своём пути — она одна (клетки
    сетки независимы при общем контексте: числа клетки те же, что в полном прогоне)."""
    book = book_from_dict(data, facts=facts)
    if cell is None:
        return run_grid(book, facts)
    ctx = make_context(book, facts)
    return CellRun(ctx=ctx, cells=(run_cell(ctx, *cell),))


def reanchor(book: Book, facts: Facts, report: Mapping, *, valuation_date: Any = None,
             version: str | None = None, near: Any = None, cell: Sequence[str] | None = None,
             base_run: GridRun | None = None, observation: Mapping | None = None,
             observe: bool = True, update_bridge: bool | None = None,
             transmission: str = KEEP, marked: Sequence[str] | None = None) -> Reanchored:
    """Книга и факты-кандидат на отчёте `report` (формат — шапка модуля).

    `near` — готовая ближняя калибровка ЧПМ (у фактического отчёта — та, что выведена на
    ожидаемом); без неё калибровка выводится здесь: ожидаемый путь ЧПМ кандидата совпадает с
    путём `base_run` (прежняя книга с наблюдением отчёта) — по слою «свой взгляд» или по клетке
    `cell` (перезаякоривание клетки на своём пути). `observation` — наблюдение A-P2u вместо
    упр. ЧПМ и CoR отчёта (у клетки на своём пути — то же, что у прежней книги);
    `observe=False` — без наблюдения. `transmission`: `keep` — скаляры пути σ0_A, σ0_L, φ_A, φ_L
    прежней книги сохраняются, цели A-N2, A-N3 и обе доли пересчитываются на структуру нового
    якоря (режим процедуры, М§15.2 п. 8); `resolve` — только диагностика: цели и доли не
    трогаются, ядро решает скаляры заново на новой структуре. `marked` — ключи книги, выведенные на ядре
    (`derived_on_core` по шаблону книги): перечень в ручных шагах — по самой книге.
    """
    if transmission not in TRANSMISSION_MODES:
        raise ReportError(f"transmission {transmission!r}: известны {', '.join(TRANSMISSION_MODES)}")
    check_report(book, facts, report)
    period = str(report["period"])
    first_new = next_period(period)
    end = period_end(period)
    old_anchor = str(book.get("meta.anchor_period"))
    year_shift = parse_period(period)[0] - parse_period(old_anchor)[0]
    warnings: list[str] = []
    derived: dict[str, Any] = {"year_shift": year_shift, "transmission_mode": transmission}
    X = copy.deepcopy(dict(book.source))
    M = X["meta"]
    row_keys, refine = _row_keys(X), copy.deepcopy(_get(X, REFINE_ROWS))   # строки обратного расчёта прежней книги

    # --- дата оценки и meta
    vdate = valuation_day(valuation_date, report)
    M.update(anchor_period=period, first_period=first_new, facts_date=end.isoformat(),
             valuation_date=vdate.isoformat(), version=version or f"{M['version']}+{period}")
    # доля инструментов в RWA своей клетки: квартал ключа, ушедший в историю, — новый first_period (М§15.2 п. 3)
    carry_t2_share(X, period, first_new, derived, warnings)
    # доля добавочного капитала и надбавка за субординацию: квартал ключа — так же, базы — суммой (М§15.2 п. 3)
    old_books = book.get("nii.books")
    carry_at1_share(X, period, first_new, float(anchor_facts(facts, old_books).at1), derived, warnings)
    carry_t2_premium(X, Trajectory(book.get(T2)).value(*parse_period(old_anchor)), derived, warnings)

    # --- наблюдение закрытого квартала
    obs = dict(observation) if observation is not None else {
        "period": period, "cor": float(report["mgmt"]["cor"]), "nim": float(report["mgmt"]["nim"]),
        "se_cor": 0.0, "se_nim": 0.0, "basis": "mgmt"}
    if observe:
        replaced = [o for o in book.get(OBS) or [] if str(o["period"]) == period]
        if replaced:
            warnings.append(f"наблюдение {period} прежней книги ({replaced[0]}) заменено фактом отчёта")
        derived["observation"] = carry_observation(X, book, facts, obs)

    # --- прежняя книга с тем же наблюдением: путь, с которым сверяется кандидат
    if base_run is None:
        base_run = run_grid(with_observation(book, obs) if observe else book, facts)
    if base_run.ctx.timeline.index(period) != 1:
        raise ReportError("base_run — не прогон прежней книги: квартал отчёта у него не первый прогнозный")
    refuse_closed_contribution(base_run)             # взнос закрываемого квартала — отказ (М§15.2 п. 13, §3.16)
    kappa_note = lost_kappa(book, base_run)
    base_run = history_run(book, base_run, cell)     # путь прежней книги, каким его увидит новый якорь (М§4.6)
    weights = _weights(base_run, cell)
    if derived.get("t2_share"):                      # доля клеток прежней книги — рядом с долей нового якоря
        derived["t2_share"]["cells"] = t2_share_cells(base_run, weights, derived["t2_share"]["from"][0])

    # --- цены якоря
    if "price_index" in report["market"]:
        factor = float(report["market"]["price_index"])
    else:
        factor = sum(float(book.get(f"joint.world_prob.{w}")) * base_run.ctx.worlds[w].price_index[1]
                     for w in book.get("worlds.ids"))
        derived["price_index_source"] = "ожидаемый индекс миров книги"
    derived["price_index"] = factor
    reindex_prices(X, facts, period, factor)
    carry_fx(X, factor)
    if year_shift:
        X["noncore"]["price_base_year"] = int(X["noncore"]["price_base_year"]) + year_shift

    # --- anchor-ключи с лагом — числами прежней книги
    freeze_anchors(X, book)
    derived["frozen"] = {k: _get(X, k) for k in FROZEN_ANCHORS}

    # --- смена года якоря, справочные ключи
    renamed = shift_crisis(X, year_shift)
    carry_refine_rows(X, refine, row_keys)
    if year_shift:
        warnings.append(
            f"год якоря сменился ({parse_period(old_anchor)[0]} → {parse_period(period)[0]}): кризисные "
            "ключи сдвинуты вместе с годом шока — режим «перезаряжен», и строки «механика» и «выпуклость» "
            "ненулевые по определению стационарных режимов (М§3.2). Замороженные μ наблюдений окна не "
            "пересчитываются (М§12): наблюдение закрытого квартала судится против ожидания прежней книги — "
            "с шоком, и несостоявшийся шок остаётся свидетельством против перезаряженного режима, пока запись "
            "не выйдет из окна; снизу — пол вероятности режима. Сдвиг точки на ожидаемом отчёте (строки "
            "«обучение», «механика» и «выпуклость» сухого прогона) и строка «обучение» отчёта без шока — в "
            "журнал версии книги. Гайденс нового "
            "года (volumes.guidance_year, guidance_growth, fees.growth_override) — решение книги")
    first_year = parse_period(first_new)[0]
    if int(X["nii"]["sigma0_from"]) < first_year:
        X["nii"]["sigma0_from"] = first_year
    if "next_report" in X["valuation"]:
        X["valuation"]["next_report"]["period"] = first_new

    # --- оценка нормативов до выхода формы: уровни капитала и RWA якоря — расчётом по оценке, не уровнями прошлой формы
    if report["capital"].get("estimated") is True:
        report, derived["estimated_levels"] = estimated_levels(book, facts, report, base_run, weights)
        warnings.append(
            "уровни капитала и RWA якоря посчитаны по оценке нормативов на RWA модели (плотности × остатки нового якоря "
            "× ожидаемый дрейф): " + "; ".join(
                f"{k} {'—' if a is None else format(float(a), '.3f')} → {b:.3f}" for k, (a, b) in derived["estimated_levels"].items())
            + " — значения отчёта на этих слотах (уровни последней формы) в калибровку не входят; факт придёт с формой")

    # --- факты нового якоря
    quarterly = is_quarterly(book)
    new_facts = facts_after(book, facts, report,
                            update_bridge=(cell is None) if update_bridge is None else update_bridge,
                            series_notes=derived.setdefault("bridge_series", {}))
    books = book.get("nii.books")
    old_af, new_af = anchor_facts(facts, books), anchor_facts(new_facts, books)
    if quarterly and report["balance"].get("dividends_payable_year") is not None:
        warnings.append("balance.dividends_payable_year отчёта не прочитан: у книги квартальный календарь дивидендов — "
                        "объявленное и не выплаченное несёт список balance.dividends_payable_declared по периодам")
    iea_rows = link_base_of(book) == IEA_BASE           # годовая книга с базой iea читает решения ради строк истории
    if not quarterly and ((report.get("dividend_decisions") and not iea_rows)
                          or report["balance"].get("dividends_payable_declared")):
        warnings.append("dividend_decisions и balance.dividends_payable_declared отчёта не прочитаны: у книги годовой "
                        "календарь дивидендов — год объявленного дивиденда несёт balance.dividends_payable_year"
                        if not iea_rows else
                        "balance.dividends_payable_declared отчёта не прочитан: у книги годовой календарь дивидендов — год "
                        "объявленного дивиденда несёт balance.dividends_payable_year (решения собрания dividend_decisions "
                        "записаны строками истории дивидендов: база объёма iea, М§4.7)")
    if not quarterly and iea_rows and report.get("dividend_decisions"):
        derived["decision_rows"] = [{k: d.get(k) for k in ("period", "dps", "decided_date", "pool_all_classes")}
                                    for d in report["dividend_decisions"]]
    if new_af.estimated:
        warnings.append(
            "нормативы якоря стоят оценкой до выхода формы (capital.estimated): вычеты и поправки «норматив − расчёт» "
            "выведены на оценке; когда форма выйдет — замена оценки фактом без смены якоря: "
            "`reanchor.py --capital-form ФАЙЛ` на кандидате, перенесённом в канон (docs/REANCHOR.md)")
    if report["pnl"].get("estimated") is True:
        warnings.append("прибыль квартала стоит напечатанным значением (pnl.estimated): строки прибыли фактов кандидата "
                        "несут пометку оценки; точные значения — правкой фактов без смены якоря (docs/REANCHOR.md)")

    # --- ключи спредов от ставок якоря
    derived["spread_books"] = rederive_spreads(X, book, old_af.rates, new_af.rates)

    # --- сегментная CoR: структура нормировки — прежней книги (М§4.6, §15.2 п. 3)
    derived["segment_mix"] = carry_segment_mix(X, book, old_af, new_af)
    drift = segment_drift_note(derived["segment_mix"])
    if drift:                                        # дрейф структуры кредитов от ключа (REANCHOR §6)
        warnings.append(drift)

    # --- инструменты капитала: книга, которая пишет ключ квартала якоря явно, получает ключ нового якоря — факт
    carry_t2(X, old_anchor, period, report["capital"].get("t2"), derived, warnings)

    # --- путь постоянной части прочих активов: приращение нового якоря — в число, путь — от нового якоря (М§15.2 п. 3)
    carry_fixed_change(X, old_anchor, period, report, derived, warnings)
    # плотность постоянной части — вместе с числом и до общего множителя плотностей (М§15.2 п. 3)
    oaf_facts = _fact(facts.file("balance").get("other_assets_fixed"))
    carry_fixed_density(X, derived, warnings, level_value=float(oaf_facts) if _num(oaf_facts) else None)

    # --- капитал: вычеты формулой книги, плотности RWA — общим множителем к RWA якоря
    calibrate_capital(X, new_facts, float(report["capital"]["basel_rwa"]), derived, warnings,
                      numbers="estimated_levels" in derived, old=book)

    # --- передача ставки: скаляры пути прежней книги на структуре нового якоря
    kept_axes = {path: [{k: copy.deepcopy(axis[k]) for k in keys if k in axis}
                        for axis, keys in _value_axes(X, path)] for path in TRANSMISSION_KEYS}
    derived["transmission"] = keep_transmission(X, new_facts, base_run)
    level_gate = carry_level_gate(X, derived["transmission"])
    check_bundles(X, book.source, renamed)

    # --- поправки «норматив − расчёт» и ближняя калибровка ЧПМ: по прогону кандидата
    periods = [period_str(*shift_quarter(*parse_period(first_new), i))
               for i in range(pindex(str(M["last_period"])) - pindex(first_new) + 1)]
    last_year = parse_period(str(M["last_period"]))[0]
    target = [_mean(base_run, weights, "nim", q + 1) for q in range(1, len(periods) + 1)]
    fact = {"n20": float(report["capital"]["n20_0"]), "n11": float(report["capital"]["n1_1_bank"])}
    if near is not None:
        set_near(X, copy.deepcopy(near), warnings)
        carry_refine_rows(X, refine, row_keys)
    old_near = book.source["regimes"]["near_nim_shift"]
    moved, detail = 0.0, 0
    for step in range(PASSES):               # повторы добирают второй порядок (ЧПД → капитал → баланс → ЧПМ)
        run = candidate_run(X, new_facts, cell)
        moved = 0.0
        for path, name in GAPS:
            delta = fact[name] - _anchor_row(run, weights, name)
            if abs(delta) > GAP_TOL:
                value = float(_get(X, path))
                _set(X, path, _r(value + delta, 12))
                _remap_axes(X, path, value, value + delta)
                moved = max(moved, abs(delta))
        if near is None:
            got = [_mean(run, weights, "nim", q) for q in range(1, len(periods) + 1)]
            before = X["regimes"]["near_nim_shift"]
            t_near = Trajectory(before)
            values = [t_near.value(*parse_period(p)) - (g - t) for p, g, t in zip(periods, got, target)]
            after = near_trajectory(old_near if step == 0 else before, periods, values, last_year, detail)
            detail = max([detail] + [parse_period(k)[0] for k in after if "Q" in k])
            set_near(X, after, warnings if step == 0 else None)
            carry_refine_rows(X, refine, row_keys)
            was = before if isinstance(before, Mapping) else {}
            moved = max([moved] + [abs(float(after.get(k, 0.0)) - float(was.get(k, 0.0)))
                                   for k in set(after) | set(was)])
            moved = moved if step else 1.0   # первый проход — от прежней траектории: всегда повторить
        if moved < NEAR_TOL / 2:
            break
    else:
        warnings.append(f"калибровка к якорю не сошлась за {PASSES} проходов (последний сдвиг ключа {moved:.2e}): "
                        "ожидаемый путь ЧПМ кандидата совпадает с путём прежней книги не во всех кварталах — остаток "
                        "печатается в производных величинах, эффект — в строке «механика»")
    carry_refine_rows(X, refine, row_keys, warnings)
    cand = book_from_dict(X, facts=new_facts)
    check_fixed_variants(cand, derived)
    run = candidate_run(X, new_facts, cell)
    if near is None:
        got = [_mean(run, weights, "nim", q) for q in range(1, len(periods) + 1)]
        derived["nim_path"] = {"periods": periods, "old": target, "new": got,
                               "residual": max(abs(g - t) for g, t in zip(got, target))}
    if transmission == RESOLVE:              # диагностика: цели, доли и их оси — прежней книги, скаляры решает ядро
        for path in TRANSMISSION_KEYS:
            _set(X, path, _get(book.source, path))
            for (axis, _), before in zip(_value_axes(X, path), kept_axes[path]):
                axis.update(before)
        if level_gate:
            _set(X, GATE_TARGET, level_gate[0])
        cand = book_from_dict(X, facts=new_facts)
        run = candidate_run(X, new_facts, cell)
    eng = engine_ratios(book, facts, report)
    bridges = bridge_from_facts(facts), bridge_from_facts(new_facts)
    derived.update(
        gaps={path: _get(X, path) for path, _ in GAPS},
        anchor_row={name: _anchor_row(run, weights, name) for _, name in GAPS},
        engine={k: eng[k] for k in ("nim", "cor", "cir")}, mgmt=dict(report["mgmt"]),
        bridge_old={x: getattr(bridges[0], f"{x}_value") for x in ("cor", "nim", "cir")},
        bridge_new={x: getattr(bridges[1], f"{x}_value") for x in ("cor", "nim", "cir")},
        posterior=dict(run.ctx.posterior),
        sigmas={"old": _sigmas(base_run.ctx.transmission), "new": _sigmas(run.ctx.transmission)},
        phi_weights={"old": dict(base_run.ctx.transmission.phi_weights),
                     "new": dict(run.ctx.transmission.phi_weights)},
        regime_floor=regime_floor(book, run.ctx.posterior))
    if "cir" not in report["mgmt"]:
        warnings.append("в отчёте нет mgmt.cir: история моста C/I останется без закрытого квартала, и годовой "
                        "C/I года якоря в упр. базисе (гейт guidance_gap, выпуск) на фактах кандидата не "
                        "соберётся (М§4.6) — внести C/I презентации")
    if quarterly:
        derived["dividends"] = dividend_carry(base_run, run)
    rule = growth_rule(book)
    if rule is not None and rule.catch_up > 0:
        warnings.append(
            f"навёрстывание роста включено ({CATCH_UP} = {rule.catch_up:g}): клетка помнит разрыв с потенциальным "
            "путём кредитных книг, а факты якоря — нет. Потенциальный путь стартует с факта нового якоря (М§4.13.1), "
            "и у клеток, где рост был урезан до якоря, перенос стирает разрыв: их строка «механика» не ноль")
    if kappa_note:
        warnings.append(kappa_note)
    derived["level"] = level_shift(base_run.ctx, run.ctx, gate=None if transmission == RESOLVE else level_gate)
    if derived["level"]:
        warnings.append(level_note(derived["level"]))
    derived["stationary"] = stationary_shift(base_run.ctx, run.ctx)
    if derived["stationary"] and not (derived["level"] and derived["level"]["world"] == derived["stationary"]["world"]):
        warnings.append(stationary_note(derived["stationary"], level=derived["level"]))
    changes = diff(dict(book.source), X)
    warnings += manual_steps(book, X, marked=marked, changes=changes, first_new=first_new, report=report,
                             carried=carried_variants(derived))
    note = shares_note(book, facts, report)
    if note:                                         # акции объявленного выпуска (REANCHOR §3.16)
        warnings.append(note)
    return Reanchored(data=X, book=cand, facts=new_facts, period=period, derived=derived,
                      changes=changes, warnings=warnings,
                      near=copy.deepcopy(X["regimes"]["near_nim_shift"]))


def regime_floor(book: Book, posterior: Mapping[str, float]) -> dict[str, Any]:
    """Пол вероятности режима (М§12): `floor_share` × базовая; режимы, стоящие на полу после наблюдений."""
    share = float(book.get("joint.regime_update.floor_share"))
    floors = {r: share * float(p) for r, p in book.get("joint.regime_prob").items()}
    on_floor = [r for r in floors if share and float(posterior[r]) <= floors[r] + GAP_TOL]
    return {"share": share, "floors": floors, "on_floor": on_floor}


def lost_kappa_adds(book: Book, run: Any) -> dict[str, float]:
    """κ-добавка к CoR квартала 1 + L от реальной ставки закрываемого квартала по мирам (ненулевые) — та, которую
    ядро после переноса якоря считает нулём: до сетки реальная ставка у миров общая (М§4.6). Мир-опора — ключ
    книги `credit.kappa_reference_world`: добавка κ × разность реальных ставок мира и мира-опоры любого знака; нет
    ключа — базовый мир и только превышение над ним."""
    kappa, lag = float(book.get("credit.kappa")), int(book.get("credit.real_rate_lag_q"))
    worlds = run.ctx.worlds
    named = book.opt(KAPPA_WORLD)
    ref = BASE_WORLD if named is None else str(named)
    if not kappa or ref not in worlds or 1 + lag > run.ctx.timeline.Q:
        return {}
    level = worlds[ref].real_key[1]
    adds = {w: kappa * ((p.real_key[1] - level) if named is not None else max(0.0, p.real_key[1] - level))
            for w, p in worlds.items()}
    return {w: v for w, v in adds.items() if v}


def lost_kappa(book: Book, run: GridRun) -> str | None:
    """κ-добавка квартала, уходящего в историю: после переноса якоря ядро считает её нулём (М§4.6: до сетки
    реальная ставка у миров общая) — это не переносится, только называется. У книги с миром-опорой добавка
    любого знака и стоит в разложении отдельной строкой (`history_run`)."""
    adds = lost_kappa_adds(book, run)
    if not adds:
        return None
    period = run.ctx.timeline.period(1 + int(book.get("credit.real_rate_lag_q")))
    parts = ", ".join(f"{w}: {v * 100:+.2f} п.п." for w, v in adds.items())
    if book.opt(KAPPA_WORLD) is None:
        return (f"κ-добавка к CoR в {period} от реальной ставки закрытого квартала "
                f"теряется при переносе якоря ({parts}): ядро считает добавку до сетки нулём (М§4.6) — "
                "эффект в строке «механика»")
    return (f"κ-добавка к CoR в {period} от реальной ставки закрытого квартала (к миру-опоре {book.get(KAPPA_WORLD)}; "
            f"{parts}) после переноса якоря равна нулю: до сетки реальная ставка у миров общая (М§4.6). Это свойство "
            "ядра, а не механика переноса: в разложении — отдельная строка «история до сетки», клетка на своём пути "
            "сверяется с прежней книгой без этой добавки, и в допуск механики она не входит")


def history_run(book: Book, run: Any, cell: Sequence[str] | None = None) -> Any:
    """Путь прежней книги, каким его увидит новый якорь: история до сетки у миров общая (М§4.6), и κ-добавка от
    реальной ставки закрываемого квартала у книги с миром-опорой (`credit.kappa_reference_world`) после переноса
    равна нулю. Возвращает прогон без этой добавки — клетки миров, где она была, пересчитаны на контексте, в
    котором реальная ставка закрываемого квартала у них — как у мира-опоры; остальное то же. С ним сверяется
    кандидат: иначе ближняя калибровка ЧПМ подгоняла бы путь кандидата под путь, которого у него быть не может
    (добавка меняет прибыль, капитал и рост следующих кварталов). Нет ключа или добавки — тот же прогон.
    `cell` — нужна одна клетка (перезаякоривание клетки на своём пути)."""
    if book.opt(KAPPA_WORLD) is None:
        return run
    adds = lost_kappa_adds(book, run)
    if not adds:
        return run
    ctx = run.ctx
    level = ctx.worlds[str(book.get(KAPPA_WORLD))].real_key[1]
    worlds = dict(ctx.worlds)
    for w in adds:
        series = list(worlds[w].real_key)
        series[1] = level
        worlds[w] = replace(worlds[w], real_key=tuple(series))
    flat = replace(ctx, worlds=worlds)
    keys = [tuple(cell)] if cell is not None else [c.key for c in run.cells]
    cells = tuple(run_cell(flat, *key) if key[0] in adds else run.cell(*key) for key in keys)
    return CellRun(ctx=flat, cells=cells, layers=getattr(run, "layers", {}))


def stationary_margin(ctx: Any) -> dict[str, Any] | None:
    """Число гейта `nim_stationary` на контексте прогона (М§14.2): стационарная маржа решателя передачи на
    составе баланса якоря в мире ключа книги — в базисе движка и, мостом, в упр. базисе. Нет ключа — None."""
    cfg = ctx.book.opt(NIM_STATIONARY)
    if cfg is None:
        return None
    world = str(cfg["world"])
    engine = float(ctx.transmission.nss[world])
    return {"world": world, "engine": engine, "value": ctx.bridge.to_mgmt_nim(engine),
            "target": float(cfg["target"]), "tolerance": float(cfg["tolerance"])}


def stationary_shift(old_ctx: Any, new_ctx: Any) -> dict[str, Any] | None:
    """Стационарная маржа гейта `nim_stationary` на прежнем якоре и на новом: скаляры пути при переносе
    сохранены, поэтому сдвиг — состав баланса нового якоря (маржа движка) и мост упр. ↔ движок."""
    was, now = stationary_margin(old_ctx), stationary_margin(new_ctx)
    if was is None or now is None:
        return None
    return {**now, "before": was["value"], "d_engine": now["engine"] - was["engine"],
            "d_bridge": (now["value"] - was["value"]) - (now["engine"] - was["engine"]),
            "fired": abs(now["value"] - now["target"]) > now["tolerance"]}


def _pp(x: float, digits: int = 3) -> str:
    return f"{x * 100:+.{digits}f} п.п.".replace(".", ",", 1)


def level_shift(old_ctx: Any, new_ctx: Any, gate: tuple[float, float] | None = None) -> dict[str, Any] | None:
    """Ключ уровня маржи у книги с ключом мира уровня (`nii.transmission.level_world`) на прежнем якоре и на
    новом: ключ книги (`key`), стационарная маржа мира уровня по счёту ядра на обоих контекстах (`value` — по
    определению ключа равна ему), её сдвиг — маржа движка (состав баланса при сохранённых скалярах пути) и мост
    упр. ↔ движок, и уровень мира-опоры решателя (`reference`), который ядро находит под ключ. `gate` — цель
    гейта стационарной маржи в том же мире, перенесённая вместе с ключом: (было, стало). Нет ключа — None."""
    world = new_ctx.book.opt(LEVEL_WORLD)
    if world is None:
        return None
    world, was, now = str(world), old_ctx.transmission, new_ctx.transmission
    ref = str(now.reference_world)
    engine = float(was.nss[world]), float(now.nss[world])
    value = old_ctx.bridge.to_mgmt_nim(engine[0]), new_ctx.bridge.to_mgmt_nim(engine[1])
    return {"world": world, "key": (float(old_ctx.book.get(NIM_TARGET)), float(new_ctx.book.get(NIM_TARGET))),
            "value": value, "d_engine": engine[1] - engine[0],
            "d_bridge": (value[1] - value[0]) - (engine[1] - engine[0]), "reference_world": ref,
            "reference": (old_ctx.bridge.to_mgmt_nim(float(was.nss[ref])),
                          new_ctx.bridge.to_mgmt_nim(float(now.nss[ref]))),
            "gate": gate}


def level_note(lv: Mapping[str, Any]) -> str:
    """Слова о ключе уровня маржи после переноса: он переписан на состав баланса нового якоря — это запись
    прежнего суждения, а не пересмотр уровня; пересмотр по новому окну фактов — решение новой версии книги."""
    (k0, k1), (v0, v1), (r0, r1) = lv["key"], lv["value"], lv["reference"]
    text = (f"{NIM_TARGET} — уровень маржи: стационарная маржа мира {lv['world']} на составе баланса якоря, упр. "
            f"(`{LEVEL_WORLD}`). ")
    if k1 == k0:
        text += (f"Ключ оставлен числом прежней книги ({_pct(k0, 3)}): скаляры пути ядро решило под него заново на "
                 "составе баланса нового якоря. ")
    else:
        text += ("Перенос якоря сохранил скаляры пути (спреды книг те же) и переписал ключ на состав баланса нового "
                 f"якоря: {_pct(k0, 3)} → {_pct(k1, 3)}; сдвиг {_pp(v1 - v0)} = маржа движка {_pp(lv['d_engine'])} "
                 f"(состав баланса) и мост упр. ↔ движок {_pp(lv['d_bridge'])}; уровень мира-опоры решателя "
                 f"{lv['reference_world']} — {_pct(r0, 3)} → {_pct(r1, 3)}. Новое число — запись прежнего суждения, а не "
                 "новый уровень: оси по ключу перенесены тем же правилом, оценку оно не сдвигает (строка «механика»). ")
    text += ("Пересмотр уровня по новому окну фактов (закрытый квартал стал его фактом) — решение новой версии книги: "
             "ключ задаётся заново правилом книги, сдвиг точки от него — строка «суждения книги» журнала версии, не "
             "механика")
    if lv.get("gate"):
        text += (f". Гейт `{NIM_STATIONARY}` стоит в том же мире и сверяет то же число: его цель записана вместе с "
                 f"ключом ({_pct(lv['gate'][0], 3)} → {_pct(lv['gate'][1], 3)}) — разницу между целью и ключом перенос "
                 "якоря не меняет, и сам по себе гейт от него не срабатывает")
    if abs(v1 - k1) > LEVEL_TOL:
        text += (f". ВНИМАНИЕ: стационарная маржа мира {lv['world']} на кандидате по счёту ядра — {_pct(v1, 4)}, а "
                 f"ключ — {_pct(k1, 4)}: запись ключа не воспроизводится, кандидата в канон не переносить")
    return text


def stationary_note(st: Mapping[str, Any], level: Mapping[str, Any] | None = None) -> str:
    """Предупреждение и порядок действий по гейту стационарной маржи: цель — суждение книги, ключ цели ЧПМ после
    переноса — запись прежних скаляров пути, а не вывод из цели. `level` — книга несёт ключ мира уровня маржи, а
    гейт стоит в другом мире: его цель — отдельное суждение, из неё ключ не выводится."""
    head = (f"{NIM_STATIONARY}: стационарная маржа мира {st['world']} на составе баланса нового якоря — "
            f"{_pct(st['value'], 3)} упр. при цели {_pct(st['target'], 2)} ± {_pp(st['tolerance'], 2)[1:]} "
            f"(на прежнем якоре {_pct(st['before'], 3)}): сдвиг {_pp(st['value'] - st['before'])} = маржа движка {_pp(st['d_engine'])} "
            f"(состав баланса при сохранённых скалярах пути) и мост упр. ↔ движок {_pp(st['d_bridge'])}"
            + (" — гейт на кандидате срабатывает" if st["fired"] else " — в допуске"))
    if level is not None:
        return (head + f". Цель гейта — отдельное суждение книги о марже мира {st['world']}: инструмент её не трогает. "
                f"Уровень маржи книга задаёт ключом `{NIM_TARGET}` в мире {level['world']}, и он переписан на состав "
                "баланса нового якоря; что делать с целью этого гейта на новом якоре — решение книги, сработавшему "
                "гейту нужно объяснение")
    return (head
            + f". Цель гейта — суждение книги о марже на составе якоря: инструмент её не трогает. Ключ `{NIM_TARGET}` "
            "у кандидата — запись прежних скаляров пути на новой структуре (режим keep), а не новый вывод из цели. "
            "Порядок: (1) цель на составе нового якоря — правилом книги от фактов окна; (2) ключ выводится на ядре "
            "заново листом книги — решением передачи под эту цель, за ним — числа, которые от него зависят, в порядке "
            "листа; (3) сдвиг точки от нового ключа — строка «суждения книги» журнала версии, не механика. Пока шаги "
            "1–2 не сделаны, сработавшему гейту нужно объяснение")


def derived_on_core(template: str) -> list[str]:
    """Ключи книги, выведенные на ядре, — по самой книге: ключи блочных словарей шаблона, в комментарии которых
    (на строке ключа или на строках-продолжениях сразу под ней) стоит пометка `DERIVED_MARKS`. Комментарий с
    первой колонки — легенда или заголовок раздела; комментарий, который начинается не правее имени ключа, —
    заголовок следующего ключа: ни тот, ни другой ключу не принадлежат."""
    lines = template.splitlines()
    keys: list[tuple[int, int, str]] = []        # (строка ключа, колонка конца его имени, путь)

    def walk(node: yaml.Node | None, prefix: str) -> None:
        if not isinstance(node, yaml.MappingNode) or node.flow_style:
            return
        for key, value in node.value:
            path = f"{prefix}.{key.value}" if prefix else str(key.value)
            keys.append((key.start_mark.line, key.end_mark.column, path))
            walk(value, path)

    walk(yaml.compose(template), "")
    keys.sort()
    out: list[str] = []
    for i, line in enumerate(lines):
        head, sep, comment = line.partition("#")
        if not sep or not any(mark in comment for mark in DERIVED_MARKS) or line.startswith("#"):
            continue
        owner = max((key for key in keys if key[0] <= i), default=None)
        if owner is None:
            continue
        at, end, path = owner
        if at != i:                              # строка-продолжение: только комментарии между ней и ключом
            between = lines[at + 1:i + 1]
            if head.strip() or len(head) <= end or not all(x.strip().startswith("#") for x in between):
                continue
        if path not in out:
            out.append(path)
    return out


def _axes_on(X: dict, roots: Sequence[str]) -> list[dict]:
    """Оси книги (полоса, оси вне полосы, обратный расчёт), которые двигают хотя бы один путь под `roots`."""
    return [axis for _, axes, _ in _axis_lists(X) for axis in axes
            if any(_under(str(p), roots) for p in axis.get("paths") or [])]


def derived_note(book: Book, X: dict, marked: Sequence[str] | None, changes: Sequence[tuple]) -> str | None:
    """Ручной шаг о числах книги, выведенных на ядре. Перечень — по книге: ключи шаблона с пометкой (`marked`);
    без шаблона — общими словами. Называет, что из перечня перенос переписал на новый якорь (это запись, не
    вывод), оси по этим ключам и коридор гейта оптового фондирования, если книга его несёт."""
    if not marked and growth_rule(book) is None:
        return None
    tail = ("Правилом книги перенос якоря их не выводит: пересмотр — решение книги, тогда вывод повторяется листом "
            "книги в его порядке (README каталога книги), а сдвиг точки — строка «суждения книги»")
    corridor = (f"; коридор `{WHOLESALE_SHARE}` посчитан на сетке прежней книги" if _get(X, WHOLESALE_SHARE) is not None
                else "")
    if not marked:
        return ("числа книги, выведенные на ядре (ключи шаблона книги с пометкой «" + DERIVED_MARKS[0] + "»; перечень и "
                "порядок вывода — README каталога книги), остаются числами прежней книги или её записью на новом якоре"
                + corridor + ". " + tail)
    moved = sorted({key for key in marked for path, _, _ in changes if _under(dotted(path), (key,))}, key=list(marked).index)
    axes = [f"«{a.get('name')}»" for a in _axes_on(X, marked)]
    return ("числа книги, выведенные на ядре (в шаблоне — пометка «" + DERIVED_MARKS[0] + "»): "
            + ", ".join(f"`{k}`" for k in marked)
            + ("; оси по этим ключам (их концы выведены или заданы вместе с ключом): " + ", ".join(dict.fromkeys(axes))
               if axes else "") + corridor + ". "
            + ("Из них перенос якоря переписал на новый якорь " + ", ".join(f"`{k}`" for k in moved)
               + " (таблица «что сдвинулось»: запись прежнего числа на новом якоре, не новый вывод); остальные — "
               "числа прежней книги. " if moved else "Перенос якоря их не трогает. ") + tail)


def variant_note(X: dict, changes: Sequence[tuple], carried: Sequence[str] = ()) -> str | None:
    """Справочные варианты (`valuation.reference_variants`): подмена, которая ложится на ключ, переписанный
    переносом якоря, осталась записью на прежнем якоре — инструмент подмены не трогает, только называет. Исключение —
    варианты `carried` на пути постоянной части прочих активов: их число, путь и плотности постоянной части перенесены
    своим приращением (`carry_fixed_ends`), прочие их подмены — по общему правилу."""
    moved = [dotted(path) for path, _, _ in changes]
    hit = []
    for variant in _get(X, VARIANTS) or []:
        own = str(variant.get("id")) in carried
        paths = [str(p) for p in (variant.get("overrides") or {})
                 if not (own and (_on_fixed_path(str(p)) or str(p) in FIXED_DENSITIES))
                 and any(d == str(p) or d.startswith(f"{p}.") or str(p).startswith(d + ".") for d in moved)]
        if paths:
            hit.append(f"«{variant.get('id')}» — " + ", ".join(f"`{p}`" for p in paths))
    if not hit:
        return None
    return (f"справочные варианты (`{VARIANTS}`): подмены ложатся на ключи, которые перенос якоря переписал, — "
            + "; ".join(hit) + ". Значения подмен остались записью на прежнем якоре (на смене года якоря — и на прежних "
            "ключах года шока): инструмент их не трогает; пересчитать на новом якоре (решение книги) — иначе таблица "
            "«Цена правил и развилок» сравнит записи разных якорей")


def premium_note(X: dict, first_old: str, first_new: str) -> str | None:
    """Ключи премии роста к сектору и ось-связка по ним (суждение книги): перенос не трогает ни ключи, ни концы оси —
    называет ключ года, который книга задаёт по фактам закрытых месяцев, год, ставший первым прогнозным, и ключи
    закрытого квартала (книга, которая пишет год якоря кварталами): новая книга их не читает."""
    axes = [a for a in _axes_on(X, PREMIUMS) if a.get("kind") == BUNDLE]
    closed = sorted(f"{root}.{part}.{first_old}" for root in PREMIUMS if isinstance(_get(X, root), Mapping)
                    for part, traj in _get(X, root).items()
                    if isinstance(traj, Mapping) and first_old in map(str, traj))
    if not axes and not closed:
        return None
    year_old, year_new = parse_period(first_old)[0], parse_period(first_new)[0]
    named = {str(p) for p in _get(X, PREMIUM_FACTS) or []}
    quarters = ("" if not closed else
                f". Ключи закрытого квартала ({', '.join(closed)}) новая книга не читает — снять"
                + (f" (вместе с их записями в `{PREMIUM_FACTS}`)" if named & set(closed) else "")
                + "; ключи оставшихся кварталов года — по правилу книги от фактов закрытых месяцев")
    if not axes:
        return "премия роста к сектору — суждение книги: перенос якоря её ключи не трогает" + quarters
    on_axis = sorted({str(p) for a in axes for p in a.get("paths") or [] if str(p).rsplit(".", 1)[-1] == str(year_new)})
    names = ", ".join(f"«{a.get('name')}»" for a in axes)
    text = (f"премия роста к сектору и её ось-связка {names} — суждение книги: перенос якоря не трогает ни ключи премии, "
            "ни концы оси. ")
    if year_new == year_old:
        return text + (f"Ключ {year_new} года после отчёта действует только на оставшиеся кварталы года; если книга "
                       "задаёт его по фактам закрытых месяцев — пересмотреть по её правилу") + quarters
    return text + (f"Первым прогнозным стал {year_new} год"
                   + (f", и его ключи стоят на оси ({', '.join(on_axis)}): оставить ли их на оси и задать ли ключ года по "
                      "фактам закрытых месяцев — решение книги" if on_axis else
                      ": задать ли его ключ по фактам закрытых месяцев — решение книги")) + quarters


def _pair(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(_num(v) for v in value)


def window_note(X: Mapping, report: Mapping | None = None) -> str | None:
    """Окно фактов книги (`checks.window_backtest`): коридоры гейта и необязательные поля окна (маржа, средние,
    доля кредитов окна) — запись окна прежней книги. Перенос их не трогает: называет поля и ставит рядом с краями
    окна упр. числа квартала отчёта (`report`) — продлить ли окно и пересмотреть ли по нему уровни, решает новая
    версия книги. Долю кредитов якоря ядро считает само — в узле уровней кандидата она уже нового якоря."""
    cfg = _get(X, WINDOW_BACKTEST)
    if not isinstance(cfg, Mapping):
        return None
    fields = [name for name in tuple(key for key, _ in WINDOW_CORRIDORS) + WINDOW_FIELDS if name in cfg]
    text = (f"окно фактов (`{WINDOW_BACKTEST}`: {', '.join(fields)}) — запись окна прежней книги: перенос якоря её не "
            "трогает. ")
    mgmt = (report or {}).get("mgmt") or {}
    seen = []
    for key, title in (("nim", "ЧПМ"),) + WINDOW_CORRIDORS:
        pair, fact = cfg.get(key), mgmt.get(key)
        if not _pair(pair) or not _num(fact):
            continue
        low, high = sorted(map(float, pair))
        where = ("ниже наименьшего квартала окна" if fact < low else
                 "выше наибольшего квартала окна" if fact > high else "внутри окна")
        seen.append(f"{title} {_pct(float(fact))} — {where} ({_pct(low)}…{_pct(high)})")
    if seen:
        text += f"Квартал отчёта {report.get('period')}, упр.: " + "; ".join(seen) + ". "
    return text + ("Продлить ли окно на закрытый квартал — и тогда пересчитать его коридоры и поля, а по новому окну "
                   "пересмотреть уровни книги — решение новой версии книги, не перенос")


def manual_steps(book: Book, X: dict, *, marked: Sequence[str] | None = None, changes: Sequence[tuple] = (),
                 first_new: str | None = None, report: Mapping | None = None, carried: Sequence[str] = ()) -> list[str]:
    """Что инструмент сознательно НЕ делает — суждения книги и работа других инструментов. `marked` — ключи книги,
    выведенные на ядре (по шаблону книги), `changes` — что перенос изменил, `first_new` — новый первый
    прогнозный квартал, `report` — отчёт квартала (его упр. числа ставятся рядом с окном фактов книги), `carried` —
    справочные варианты, перенесённые на пути постоянной части своим приращением."""
    out = []
    for path, _ in GAPS:
        old, new = float(book.get(path)), float(_get(X, path))
        if abs(new - old) > 0.0005:
            out.append(f"{path}: {old:+.4f} → {new:+.4f} — якорь воспроизводит норматив отчёта; ось "
                       "сдвинута вместе с центром, ширину пересмотреть (решение книги)")
    out.append(f"{SPLIT}, {PHI_SPLIT}: центры и оси — правило листов книги на структуре якоря (evidence/nii): "
               "пересчитать на новом якоре; дисконт за управление — неподвижная точка на новой медиане (решения "
               "книги, в разложении выпусков — строка «суждения книги»)")
    note = derived_note(book, X, marked, changes)
    if note:
        out.append(note)
    if _get(X, f"{CIR_LT}.scope") == MARKET_LAYER:
        out.append(f"{CIR_LT}: цель C/I сверяется по слою «рыночные ставки как есть» (`scope: {MARKET_LAYER}`), и корни "
                   "`opex.real_growth` выведены под неё по всей сетке; перенос якоря корни не трогает — число гейта на "
                   "кандидате стоит в таблице целей, вывод корней заново — лист книги (решение книги)")
    for note in (window_note(X, report), variant_note(X, changes, carried),
                 premium_note(X, str(book.get("meta.first_period")), first_new or str(_get(X, "meta.first_period")))):
        if note:
            out.append(note)
    if is_quarterly(book):
        out.append("дивиденды: отчётную прибыль акционеров по годам для теста потолка политики (dividends.years) и "
                   "слова решений строк истории инструмент не двигает — их несёт канон фактов; события календаря "
                   "фактов следующего квартала (отчёт, решение о дивиденде, выход формы) — руками")
    out.append("миры и кривые — на прежней дате (meta.curve_as_of): пересборка миров — отдельной версией "
               "книги вместе с семейством")
    out.append("meta.market_price и meta.date — прежней книги: обновить вместе с датой оценки")
    out.append("valuation.next_report.cor_values, nim_values — сетки «что даст отчёт» вокруг ожидания "
               "нового открытого квартала: пересмотреть")
    out.append("факты: канон пересобирает `ops/tools/build_facts.py` (`--anchor` из листов квартала, "
               "`--expected` из ожидаемого отчёта) с источниками и сверками; сверка с фактами кандидата — "
               "`--compare-facts`")
    out.append("объяснения гейтов (gate_explanations.yaml), results.json и run_output.txt, закреплённые "
               "числа тестов книги и документов — на новой книге (MANUAL §10.4)")
    return out


# ------------------------------------------------------------------ дифф


def diff(a: Any, b: Any, prefix: Path_ = ()) -> list[tuple[Path_, Any, Any]]:
    """Все листья, которые изменились: (путь звеньями, было, стало)."""
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        out = []
        for key in list(a) + [k for k in b if k not in a]:
            path = prefix + (str(key),)
            if key not in b:
                out.append((path, a[key], None))
            elif key not in a:
                out.append((path, None, b[key]))
            else:
                out += diff(a[key], b[key], path)
        return out
    for tag in ("name", "id"):               # элементы списка с именем (оси) или идентификатором (справочные варианты)
        if isinstance(a, list) and isinstance(b, list) and a \
                and all(isinstance(x, Mapping) and tag in x for x in a) \
                and (tag == "name" or len({str(x[tag]) for x in a}) == len(a)) \
                and [x[tag] for x in a] == [y.get(tag) if isinstance(y, Mapping) else None for y in b]:
            out = []
            for x, y in zip(a, b):
                out += diff(x, y, prefix + ((tag, x[tag]),))
            return out
    return [] if a == b else [(prefix, a, b)]


def dotted(path: Path_) -> str:
    out = ""
    for part in path:
        out += f"[{part[1]}]" if isinstance(part, tuple) else (f".{part}" if out else part)
    return out


def reason(path: str, derived: Mapping | None = None) -> str:
    """Почему ключ сдвинулся — для таблицы «что сдвинулось». `derived` — производные величины кандидата: у плотности
    постоянной части, перенесённой вместе с числом (М§15.2 п. 3), — своя причина."""
    if path == FIXED_DENSITY and ((derived or {}).get("fixed_change") or {}).get("density"):
        return ("плотность постоянной части — вместе с числом: вес приращения, ушедшего в число (М§15.2 п. 3), затем "
                "общий множитель к RWA якоря")
    if path.startswith(VARIANTS):
        return ("справочный вариант на пути постоянной части прочих активов — тем же правилом со своим приращением "
                "квартала нового якоря (число + δ, путь − δ, ω_oaf своими L и δ, затем общий множитель плотностей)")
    if path.startswith("valuation.") and f".{FIXED_LEVEL}" in path:
        return ("конец оси-связки на пути постоянной части прочих активов — своим приращением квартала нового якоря "
                "(число конца + δ, путь − δ)")
    return next((text for prefix, text in REASONS if path.startswith(prefix)), "")


# ------------------------------------------------------------------ ожидаемый отчёт


def _cell_report(run: GridRun, weights: Mapping[tuple, float]) -> dict:
    """Отчёт за первый прогнозный квартал прежней книги: состояние клеток `weights` на конец
    квартала (одна клетка — её путь; слой — ожидание, отношения — отношением ожиданий).

    Ближний сдвиг ЧПМ (слагаемое Ov, М§4.4) разнесён по книгам активов пропорционально их
    процентному доходу — как в настоящей отчётности, где процентный доход разложен без остатка."""
    ctx = run.ctx
    book, tl, prep = ctx.book, ctx.timeline, ctx.prep
    af, roles = prep.af, prep.roles
    total = sum(weights.values())
    w = {tuple(k): v / total for k, v in weights.items() if v}
    cells = {k: run.cell(*k) for k in w}
    year_days = tl.d(1) / 365

    def avg(name: str) -> float:
        return sum(p * float(cells[k].quarters[name][1]) for k, p in w.items())

    balances = {b: sum(p * float(cells[k].books[b]["balance"][1]) for k, p in w.items()) for b in roles.names}
    interest = {b: sum(p * float(cells[k].books[b]["rate"][1]) * float(cells[k].books[b]["avg"][1]) * year_days
                       for k, p in w.items()) for b in roles.names}
    carried = 1.0 + avg("overlay") / sum(interest[b] for b in roles.assets)
    for b in roles.assets:
        interest[b] *= carried
    pbt = avg("pbt")
    lines = {"nii": avg("nii"), "fees_net": avg("fees"), "llp_debt_fa": -avg("llp"),
             "insurance_net": avg("ins"), "noncore_net": avg("noncore"), "opex": -avg("opex")}
    misc = pbt - sum(lines.values())
    dp, dpreg = avg("dp"), avg("dpreg")
    quarterly = prep.calendar is not None
    year, by_period, annual_decisions = None, None, None
    if quarterly:                            # решения и суммы к выплате — по кварталам прибыли (М§15.2 п. 9)
        by_period = _dividends_by_period(run, w, dp, dpreg)
    else:
        if dpreg and abs(dpreg - dp) > 1e-6 * max(1.0, dp):
            raise ReportError("ожидаемый отчёт: дивиденд, не вычтенный из регуляторного капитала, не равен "
                              "дивидендам к выплате на конец квартала — календарь книги не представим фактами якоря")
        declared = [dec.year for k in w for dec in cells[k].decisions
                    if tl.index(period_str(dec.year + 1, prep.policy.agm_quarter)) == 1]
        year = declared[0] if declared else af.dividends_payable_year
        if declared and prep.link_base == IEA_BASE:     # решение собрания — строкой истории: база объёма iea (§3.9)
            annual_decisions = _annual_decisions(run, w, cells, declared[0])
    by_world: dict[str, float] = {}
    for (world, _, _), p in w.items():
        by_world[world] = by_world.get(world, 0.0) + p

    def world_avg(series) -> float:
        return sum(p * series(ctx.worlds[x]) for x, p in by_world.items())

    def over_ratio(name: str, capital: str) -> float:    # норматив − капитал / RWA: поправка и вычеты сценария
        return sum(p * (float(cells[k].quarters[name][1])
                        - float(cells[k].quarters[capital][1]) / float(cells[k].quarters["rwa"][1]))
                   for k, p in w.items())

    rwa, k11 = avg("rwa"), avg("k11")
    br = ctx.bridge
    who = f"клетка {'/'.join(next(iter(w)))}" if len(w) == 1 else "слой «свой взгляд»"
    balance = {
        "books": balances, "loans_fvtpl": avg("loans_fv"),
        "fvoci": float(book.get("oci.fvoci_share")) * balances[SECURITIES],
        "fvtpl_bonds": float(book.get("oci.fvtpl_bond_share")) * balances[SECURITIES],
        "allowance": avg("allowance"), "other_assets": avg("other_assets"),
        "other_liabilities": avg("other_liabilities"), "dividends_payable": dp,
        # добавочный капитал конца квартала: факт якоря; у книги с ключом его доли — AT1 клеток (М§15.2 п. 3)
        "bv_common": avg("bv"), "fvoci_reserve": avg("reserve"),
        "at1": af.at1 if prep.at1_from is None else avg("at1"), "nci": af.nci,
    }
    if year is not None:
        balance["dividends_payable_year"] = int(year)
    capital = {"n20_0": avg("k20") / rwa + over_ratio("n20", "k20"), "n20_pre_dividend": dpreg > DIV_TOL,
               "n1_1_bank": k11 / rwa + over_ratio("n11", "k11"),
               "basel_cet1": avg("bv") - avg("ded20"), "basel_rwa": rwa, "bank_base_capital": k11}
    extra: dict[str, Any] = {}
    if by_period is not None:
        balance["dividends_payable_declared"] = by_period["declared"]
        extra["dividend_decisions"] = by_period["decisions"]
    elif annual_decisions:
        extra["dividend_decisions"] = annual_decisions
    if prep.oa_fixed or prep.oa_delta is not None:   # постоянная в рублях часть прочих активов клетка несёт числом
        # (М§4.3); у книги с путём постоянной части — с приращением закрываемого квартала
        balance["other_assets_fixed"] = prep.oa_fixed + (0.0 if prep.oa_delta is None else prep.oa_delta[1])
    if _anchor_key(book.source or book.data, T2, tl.anchor):
        capital["t2"] = prep.t2[1] if prep.t2_from is None else avg("t2")   # инструменты конца квартала: траектория;
        #                                     у книги с ключом доли — T2 клеток (χ_c × RWA_c,1 с квартала ключа, М§15.2 п. 3)
    premium = {}
    if prep.t2p_spread is not None:          # надбавка за субординацию квартала — процентный расход вне книг (М§15.2 п. 3)
        premium["t2_premium"] = avg("t2_premium")
    return _rounded({
        "schema": SCHEMA, "period": tl.period(1), "as_of": tl.end(1).isoformat(),
        "note": (f"синтетический отчёт: ожидание модели книги {book.get('meta.version')} ({who}) — "
                 "сухой прогон, не факты"),
        "balance": balance, "interest": interest, "dia": avg("dia"),
        "pnl": {**lines, "misc_net": misc, "pbt": pbt, "tax": -(avg("tax") + avg("ot")), "ni": avg("ni"),
                "ni_shareholders": avg("ni_sh"), "oci_fvoci": avg("oci"), "other_equity_movements": avg("om"),
                **premium},
        "capital": capital,
        "market": {"ofz_curve": {n: world_avg(lambda x, n=n: x.ofz[f"ofz_{n}y"][1]) for n in CURVE_NODES},
                   "key_avg": avg("key"), "price_index": world_avg(lambda x: x.price_index[1])},
        "mgmt": {"nim": br.to_mgmt_nim(avg("nim")), "cor": br.to_mgmt_cor(avg("cor")),
                 "cir": br.to_mgmt_cir(avg("opex") / (avg("nii") + avg("fees") + avg("ins") + misc))},
        **extra,
    }, 9)


def _annual_decisions(run: GridRun, w: Mapping[tuple, float], cells: Mapping[tuple, Any], year: int) -> list[dict]:
    """Годовой календарь, база объёма `iea` (М§4.7, REANCHOR §3.9): решение собрания закрываемого квартала за год `year`
    — строкой раздела `dividend_decisions`, как его несёт файл отчёта: квартал прибыли — четвёртый квартал года, DPS —
    ожидание клеток `w`, `pool_all_classes` — ожидание суммы, вычтенной из капитала (Div клетки); день решения — запись
    реестра, иначе конец квартала."""
    ctx = run.ctx
    tl = ctx.timeline
    got = [(p, next(d for d in cells[k].decisions if d.year == year)) for k, p in w.items()
           if any(d.year == year for d in cells[k].decisions)]
    if not got:
        return []
    end, facts_date = tl.end(1), to_date(ctx.book.get("meta.facts_date"))
    rec = next((r for r in ctx.live.register if r.status in DECLARED and r.year == year), None)
    day = rec.decided_date if rec is not None and rec.decided_date is not None else None
    row = {"period": period_str(year, 4), "dps": sum(p * d.dps for p, d in got),
           "decided_date": (day if day is not None and facts_date < day <= end else end).isoformat(),
           "pool_all_classes": sum(p * d.div for p, d in got)}
    if rec is not None:
        for key, value in (("record_date", rec.record_date), ("pay_date", rec.pay_date)):
            if value is not None and value >= to_date(row["decided_date"]):
                row[key] = value.isoformat()
    return [row]


def _anchor_key(data: Mapping, path: str, period: str) -> bool:
    """Траектория книги пишет ключ квартала `period` явно (правило «ключ квартала якоря — факт», М§4.11)."""
    traj = _get(data, path)
    return isinstance(traj, Mapping) and period in {str(k) for k in traj}


def _dividends_by_period(run: GridRun, w: Mapping[tuple, float], dp: float, dpreg: float) -> dict[str, list]:
    """Квартальный календарь: решения клеток `w` в закрываемом квартале и объявленное, но не выплаченное на его
    конец — так, как их несёт файл отчёта (М§15.2 п. 9). Запись реестра даёт решению свой день, даты реестра и
    выплаты; решение модели датируется концом квартала. Состояние, которого факты якоря не выражают, — отказ:
    вычет из регуляторного капитала после выплаты; решение за квартал прибыли, оставившее открытым более ранний."""
    ctx = run.ctx
    prep, tl = ctx.prep, ctx.timeline
    cal, n_out = prep.calendar, prep.policy.n_out
    end = tl.end(1)
    facts_date = to_date(ctx.book.get("meta.facts_date"))
    records = {str(r.period): r for r in ctx.live.register if r.status in DECLARED and r.period}
    unpaid: dict[str, float] = {}
    pending, problems = 0.0, []
    items = ctx.facts.file("balance").get("dividends_payable_declared") or []
    for item, (pay_q, reg_q, amount) in zip(items, cal.payable):   # объявлено до прежнего якоря (тот же порядок)
        p = str(_fact(item.get("period")))
        if pay_q > 1:
            unpaid[p] = unpaid.get(p, 0.0) + amount
        if reg_q > 1:
            pending += amount
            if pay_q <= 1:
                problems.append(f"{p}: выплата в закрываемом квартале, вычет из регуляторного капитала — позже")
    decisions = []
    due = cal.by_q.get(1, ())
    for o in due:
        got = [(p, next(d for d in run.cell(*k).decisions if d.q == 1 and d.period == o.period)) for k, p in w.items()]
        div, dps = sum(p * d.div for p, d in got), sum(p * d.dps for p, d in got)
        rec = records.get(o.period)
        day = rec.decided_date if rec is not None and rec.decided_date is not None else None
        row = {"period": o.period, "dps": dps,
               "decided_date": (day if day is not None and facts_date < day <= end else end).isoformat()}
        if prep.link_base == IEA_BASE:      # сумма, вычтенная из капитала: база объёма iea квартала фактов (М§4.7)
            row["pool_all_classes"] = div
        if rec is not None:
            for key, value in (("record_date", rec.record_date), ("pay_date", rec.pay_date)):
                if value is not None:
                    row[key] = value.isoformat()
        decisions.append(row)
        if o.q_pay > 1 and div > DIV_TOL:
            unpaid[o.period] = unpaid.get(o.period, 0.0) + div
        if o.q_reg > 1 and div > DIV_TOL:
            pending += div
            if o.q_pay <= 1:
                problems.append(f"{o.period}: выплата в квартале решения, вычет из регуляторного капитала — позже")
    if due:
        last = max(o.idx for o in due)
        late = [o.period for o in cal.open if o.idx < last and o.q > 1]
        if late:
            problems.append(f"решение за {tl.period(last)} принято раньше решения за {', '.join(late)}: строка "
                            "истории закрыла бы и более ранний квартал прибыли")
    if abs(pending - dpreg) > DIV_TOL * max(1.0, abs(dpreg)):
        problems.append(f"дивиденды в регуляторном капитале {dpreg:g} не равны объявленным с вычетом впереди {pending:g}")
    if sum(unpaid.values()) > dp + DIV_TOL:
        problems.append(f"объявлено и не выплачено {sum(unpaid.values()):g} — больше дивидендов к выплате {dp:g}")
    if problems:
        raise ReportError("ожидаемый отчёт: календарь дивидендов книги не представим фактами якоря — "
                          + "; ".join(problems) + " (решение книги: payment_lag_quarters не меньше "
                          "reg_deduction_lag_quarters; даты записи реестра)")
    order = sorted(unpaid, key=pindex)
    return {"decisions": decisions, "declared": [{"period": p, "amount": unpaid[p]} for p in order]}


def expected_run(book: Book, facts: Facts, live: LiveInputs | None = None, *,
                 observe: bool = True) -> tuple[Book, GridRun, dict | None]:
    """Прежняя книга с наблюдением, равным ожиданию модели (A⁺), её прогон и само наблюдение."""
    if not observe:
        return book, run_grid(book, facts, live), None
    obs = expected_observation(book, facts, live)
    plus = with_observation(book, obs)
    return plus, run_grid(plus, facts, live), obs


def expected_report(book: Book, facts: Facts, *, cell: Sequence[str] | None = None,
                    run: GridRun | None = None, observe: bool = True) -> dict:
    """Синтетический отчёт за первый прогнозный квартал = ожидание модели (М§15.2).

    `cell` — путь одной клетки (точная проверка механики, без неравенства Йенсена); иначе —
    ожидание слоя «свой взгляд». `run` — готовый прогон прежней книги с ожидаемым наблюдением."""
    if run is None:
        _, run, _ = expected_run(book, facts, observe=observe)
    return _cell_report(run, _weights(run, cell))


# ------------------------------------------------------------------ разложение скачка


def live_at(book: Book, facts: Facts, valuation_date: dt.date) -> LiveInputs:
    """Живые входы книги на дате оценки `valuation_date`: цены и реестр — книжные."""
    live = live_from_book(book, facts)
    return LiveInputs(valuation_date=valuation_date, prices=live.prices,
                      price_dates={t: valuation_date for t in live.prices}, register=live.register)


def headline(run: GridRun) -> dict:
    """Низ, точка при λ и верх (₽) и V0 слоёв (млрд ₽) при значениях книги."""
    return {"low": run.low, "point": run.point, "high": run.high,
            "v0": {name: layer.v0 for name, layer in run.layers.items()}}


def _priced(run_plus: GridRun, values: Mapping[tuple, float]) -> dict:
    """Низ, точка и верх (₽) и V0 слоёв (млрд ₽) при стоимостях клеток `values` и вероятностях прогона `run_plus`:
    цена линейна по V0 (М§8.2), делитель «на акцию» — книги (М§8.4). У книги с полом клетки (`valuation.cell_floor`,
    М§8.2) клетка входит в V0 стоимостью в цене — не ниже пола при объявленном дивиденде прогона, как в слоях самого
    прогона: иначе строка «механика» несла бы отрицательные стоимости клеток на полу и при неизменных клетках."""
    n_div = (getattr(run_plus, "divisor", 0.0) or getattr(run_plus, "shares_out", 0.0)
             or run_plus.ctx.prep.af.n_out)
    per_v0 = (1.0 - run_plus.governance) * 1000.0 / n_div
    floor = getattr(run_plus, "cell_floor", None)
    if floor is not None:                    # стоимость клетки в цене V^F (М§8.2) — то же правило, что у слоёв
        values = {k: floor_value(float(v), run_plus.pending_dividend, floor) for k, v in values.items()}
    price, v0 = {}, {}
    for name, layer in run_plus.layers.items():
        v0[name] = sum(p * values[k] for k, p in layer.prob.items())
        price[name] = layer.price + (v0[name] - layer.v0) * per_v0
    low, high = price[NEUTRAL], price[ANALYTICAL]
    return {"low": low, "high": high, "point": low + run_plus.lam * (high - low), "v0": v0}


def cell_mechanics(book: Book, facts: Facts, run_plus: GridRun, obs: Mapping | None,
                   valuation_date: dt.date, *, cells: Sequence[Sequence[str]] | None = None,
                   transmission: str = KEEP, history: Any = None) -> dict:
    """Строка «механика» (М§15.2): каждая клетка перезаякорена на своём пути.

    Отчёт клетки — её состояние на конец закрытого квартала; наблюдение и вероятности — как у
    прежней книги с ожидаемым наблюдением. Возвращает строки по клеткам и точку слоёв. При
    смене года якоря клетки режима с годом шока «перезаряжены» (М§3.2) — их путь другой по
    определению, и в допуск они не входят. База сравнения клетки — путь прежней книги, каким его увидит новый
    якорь (`history_run`; `history` — готовый): у книги с миром-опорой κ он не несёт добавку от реальной ставки
    закрываемого квартала. Строка клетки несёт обе величины — `history` (прежняя книга без этой добавки к прежней
    книге) и `rel` (клетка на своём пути к базе); допуск — по `rel`. Без мира-опоры база — сама прежняя книга."""
    keys = [tuple(k) for k in cells] if cells is not None else [c.key for c in run_plus.cells]
    hist = history if history is not None else history_run(book, run_plus)
    tl = run_plus.ctx.timeline
    rearmed = {r for r in book.get("regimes.ids")
               if tl.year(1) != tl.anchor_year and "shock_year_offset" in book.source["regimes"][r]}
    rows = []
    for key in keys:
        old, base = run_plus.cell(*key), hist.cell(*key)
        cand = reanchor(book, facts, _cell_report(run_plus, {key: 1.0}), valuation_date=valuation_date,
                        cell=key, base_run=hist, observation=obs, observe=obs is not None,
                        transmission=transmission)
        new = run_grid(cand.book, cand.facts, live_at(cand.book, cand.facts, valuation_date)).cell(*key)
        # капитал клетки на дату оценки — с деньгами закрытых взносов (`bv_v` клетки книги со взносами — уже без них)
        rows.append({"cell": old.label, "key": key, "old": old.v_ri, "base": base.v_ri, "new": new.v_ri,
                     **mechanics_row(base.v_ri, new.v_ri, base.bv_v + base.c_v, base.c_v),
                     "bv_v": base.bv_v, "c_v": base.c_v, "history": base.v_ri / old.v_ri - 1,
                     "rearmed": key[1] in rearmed})
    kept = [r for r in rows if not r["rearmed"]] or rows
    worst, ok = mechanics_verdict(kept)
    out = {"rows": rows, "worst": worst, "tolerance": MECHANICS_TOL, "ok": ok,
           "rearmed": sorted(rearmed), "history": hist is not run_plus}
    if cells is None:                        # точка: те же вероятности, цена линейна по V0 (М§8.2)
        out["headline"] = _priced(run_plus, {r["key"]: r["new"] for r in rows})
    return out


def mechanics_row(v_base: float, v_new: float, bv_v: float, c_v: float = 0.0) -> dict[str, float]:
    """Механика клетки (М§15.2, REANCHOR §4): разность к стоимости клетки базы (прежняя мера `rel`), норма клетки
    M_c = max(|V_c(A⁰)|, BV_v,c − C_v,c) — функция нормы ядра, та же, что у невязки DDM = RI (М§6.4), и
    r_c = (V_c(O) − V_c(A⁰)) / M_c. `bv_v` — капитал клетки на дату оценки с деньгами закрытых взносов, `c_v` — их
    сумма (у книги без взносов — ноль). У клетки со стоимостью не ниже капитала r_c — прежняя относительная разность
    бит в бит (V / M = ±1)."""
    rel = v_new / v_base - 1
    norm = cell_norm(v_base, bv_v - c_v)
    return {"dv": v_new - v_base, "rel": rel, "norm": norm, "r": rel * (v_base / norm)}


def mechanics_verdict(rows: Sequence[Mapping]) -> tuple[Mapping, bool]:
    """Худшая клетка строки «механика» — по |r_c| — и вердикт: |r_c| ≤ `MECHANICS_TOL` (М§15.2)."""
    worst = max(rows, key=lambda r: abs(r["r"]))
    return worst, abs(worst["r"]) <= MECHANICS_TOL


def band_stats(book: Book, facts: Facts, live: LiveInputs, draws: int) -> dict:
    """Медиана и полоса 80 % печатаемого заголовка на `draws` прогонах (те же точки гиперкуба
    у каждой книги — сравнение парное)."""
    from model.uncertainty import band
    b = band(book, facts, live, draws=draws)
    st = b.stats(b.lam)
    main = str(book.get("meta.company.main_ticker"))
    return {"p10": st["p10"], "median": st["median"], "p90": st["p90"],
            "p_below": b.p_below(b.lam, float(live.prices[main]))}


MARGIN_TARGETS = ("nim_stationary", "nim_lt")  # гейты целей маржи: упр. число = маржа движка через мост


def target_levels(run: GridRun, findings: Sequence[Any]) -> dict[str, dict[str, Any]]:
    """Числа гейтов-целей книги на прогоне (М§14.2): гейт, который сверяет своё число с целью-суждением, несёт
    число, цель и допуск (`nim_stationary`, `cir_lt`, `nim_lt` — какие есть у книги). У целей маржи рядом —
    маржа движка: по ней сдвиг упр. числа раскладывается на путь и мост упр. ↔ движок."""
    out: dict[str, dict[str, Any]] = {}
    bridge = run.ctx.bridge
    for f in findings:
        d = f.detail or {}
        value = d.get("value", d.get("mean"))
        if f.kind != "gate" or not (_num(value) and _num(d.get("target")) and _num(d.get("tolerance"))):
            continue
        row = {"value": float(value), "target": float(d["target"]), "tolerance": float(d["tolerance"]),
               "fired": bool(f.fired), "message": f.message}
        if f.name in MARGIN_TARGETS:
            row["engine"] = bridge.to_engine_nim(float(value))
        out[f.name] = row
    return out


def level_node(run: GridRun) -> dict[str, Any] | None:
    """Узел уровней после фазы роста (ключ книги `checks.window_backtest`, М§14.5): ЧПМ, CoR, C/I в упр. базисе
    и доля кредитов в процентных активах — модальной клетки, слоёв и смеси заголовка. Нет ключа — None."""
    if run.ctx.book.opt(WINDOW_BACKTEST) is None:
        return None
    from model.levels import levels
    return levels(run)


def core_checks(run: GridRun, today: dt.date) -> dict[str, Any]:
    """Инварианты и гейты ядра на прогоне (М§14.1–§14.2): нарушенные инварианты и сработавшие гейты
    с массой; числа гейтов-целей книги (`targets`) и узел уровней после фазы роста (`levels`) — сработал гейт
    или нет. Отказ ядра (нет факта, без которого проверка не считается) — причиной в `error`."""
    try:
        broken = [(f.name, f.message) for f in check_invariants(run) if f.fired]
        every = check_gates(run, today=today)
        found = [f for f in every if f.fired]
        gates = {f.name: (f.mass, f.message) for f in found if f.kind == "gate"}
        flags = {f.name: f.message for f in found if f.kind == "flag"}
        targets, levels = target_levels(run, every), level_node(run)
    except (BookError, FactsError) as exc:
        return {"error": str(exc), "invariants": [], "gates": {}, "flags": {}, "targets": {}, "levels": None}
    return {"error": None, "invariants": broken, "gates": gates, "flags": flags, "targets": targets, "levels": levels}


LEVEL_COLUMNS = (("nim", "ЧПМ", 2), ("cor", "CoR", 2), ("cir", "C/I", 1),
                 ("loans_share", "доля кредитов в проц. активах", 1))       # (ключ узла уровней, графа, знаков)


WINDOW_WORDS = {"min": "наименьший", "max": "наибольший", "mean": "среднее", "window": "окно", "anchor": "якорь"}


def _window_cell(value: Any, digits: int, was: Any = None) -> str:
    """Ячейка строки окна фактов узла уровней (подузел `window`, М§14.6): {min, max, mean} — наименьший…наибольший
    квартал окна и среднее окна; доля кредитов — окна (поле книги) и якоря (состояние якоря прогона: у кандидата
    она новая — `was` несёт прежнюю); нет величины — «—»."""
    if not isinstance(value, Mapping):
        return "—"
    if _num(value.get("min")) and _num(value.get("max")):
        text = f"{_pct(float(value['min']), digits)}…{_pct(float(value['max']), digits)}"
        return text + (f", среднее {_pct(float(value['mean']), digits)}" if _num(value.get("mean")) else "")
    before = was if isinstance(was, Mapping) else {}
    return ", ".join(
        f"{WINDOW_WORDS.get(str(k), k)} "
        + (f"{_pct(float(before[k]), digits)} → " if _num(before.get(k)) and float(before[k]) != float(v) else "")
        + _pct(float(v), digits) for k, v in value.items() if _num(v)) or "—"


def target_lines(was: Mapping[str, Any], now: Mapping[str, Any], before: str = "прежняя книга") -> list[str]:
    """Раздел «Цели книги и уровни после фазы роста» отчёта кандидата: число каждого гейта-цели до и после
    рядом с целью и допуском (сработал гейт или нет), разложение сдвига маржи на путь и мост, узел уровней."""
    lines: list[str] = []
    rows = now.get("targets") or {}
    if rows:
        lines += ["", "Цели книги, которые сверяют её гейты (цель и допуск — суждение книги: инструмент их не трогает; "
                  "число печатается, сработал гейт или нет; цель гейта стационарной маржи в мире ключа уровня маржи — "
                  "то же суждение, что ключ, и идёт за ним: «было → стало»):", "",
                  f"| гейт | {before} | кандидат | цель ± допуск | до границы допуска |", "|---|---|---|---|---|"]
        for name, a in rows.items():
            b = (was.get("targets") or {}).get(name)
            room = a["tolerance"] - abs(a["value"] - a["target"])
            moved = b is not None and abs(b["target"] - a["target"]) > LEVEL_TOL / 2
            lines.append(f"| `{name}` | {_pct(b['value'], 3) if b else '—'} | {_pct(a['value'], 3)} | "
                         + (f"{_pct(b['target'], 3)} → {_pct(a['target'], 3)}" if moved else _pct(a["target"], 2))
                         + f" ± {_pp(a['tolerance'], 2)[1:]} | "
                         + (f"{_pp(room)[1:]}" if room >= 0 else f"вне допуска на {_pp(-room)[1:]}") + " |")
        for name, a in rows.items():
            b = (was.get("targets") or {}).get(name)
            if b is None or "engine" not in a or "engine" not in b:
                continue
            total, engine = a["value"] - b["value"], a["engine"] - b["engine"]
            lines += ["", f"Сдвиг числа `{name}`: {_pp(total)}, из них маржа движка {_pp(engine)}, мост упр. ↔ движок "
                      f"{_pp(total - engine)}; " + (
                          "маржа движка здесь — состав баланса нового якоря при сохранённых скалярах пути."
                          if name == "nim_stationary" else
                          "маржа движка модальной клетки — обучение наблюдением и её путь на отчёте, одном на все "
                          "клетки: клетка стартует со среднего состояния слоя, а ближняя калибровка ЧПМ выравнивает "
                          "только ожидание слоя.")]
    a, b = now.get("levels"), was.get("levels")
    if a:
        lines += ["", f"Уровни после фазы роста, упр. базис, среднее за {a['from_year']}–{a['to_year']} годы "
                  f"({before} → кандидат); модальная клетка — {a['cell']}:", "",
                  "| | " + " | ".join(title for _, title, _ in LEVEL_COLUMNS) + " |",
                  "|---|" + "---|" * len(LEVEL_COLUMNS)]
        for key in a["order"]:
            new, old = a["rows"][key], ((b or {}).get("rows") or {}).get(key) or {}
            cells = []
            for name, _, digits in LEVEL_COLUMNS:
                x, y = old.get(name), new.get(name)
                cells.append("—" if y is None else (f"{_pct(x, digits)} → " if x is not None else "") + _pct(y, digits))
            lines.append(f"| {new.get('title', key)} | " + " | ".join(cells) + " |")
        window = a.get("window")
        if isinstance(window, Mapping):          # окно фактов — поля книги: у кандидата те же; доля кредитов якоря — новая
            old = (b or {}).get("window") or {}
            lines.append("| Окно фактов книги: наименьший…наибольший квартал | " + " | ".join(
                _window_cell(window.get(name), digits, old.get(name)) for name, _, digits in LEVEL_COLUMNS) + " |")
    return lines


def attribution(book: Book, facts: Facts, report: Mapping, *, valuation_date: Any = None,
                version: str | None = None, band_draws: int | None = None, cells: bool = True,
                transmission: str = KEEP, observe: bool = True, marked: Sequence[str] | None = None) -> dict:
    """Кандидат на отчёте `report` и разложение скачка на одной дате оценки (М§15.2):

    обучение    A⁺ − A  прежняя книга с наблюдением, равным ожиданию модели, минус она же без него;
    история     A⁰ − A⁺ (только у книги с миром-опорой κ) та же книга без κ-добавки от реальной ставки закрываемого
                квартала: до сетки реальная ставка у миров общая, и у нового якоря этой добавки нет (М§4.6);
    механика    O − A⁰  каждая клетка перезаякорена на своём пути — должна быть ≈ 0 (A⁰ = A⁺ без мира-опоры);
    выпуклость  E − O   кандидат на ожидаемом отчёте: один отчёт на все клетки (неравенство Йенсена);
    сюрприз     F − E   кандидат на отчёте `report` с той же ближней калибровкой ЧПМ.

    Всегда — точка при значениях книги; медиана полосы — при `band_draws` (одни точки гиперкуба
    на каждой книге; у медианы механика и выпуклость — одной строкой E − A⁺). `checks` — инварианты
    и гейты ядра на прежней книге и на кандидате (дата оценки — та же). `marked` — ключи книги, выведенные на
    ядре (`derived_on_core`): перечень в ручных шагах кандидата."""
    check_report(book, facts, report)
    vdate = valuation_day(valuation_date, report)
    live = live_at(book, facts, vdate)
    run_a = run_grid(book, facts, live)
    plus, run_plus, obs = expected_run(book, facts, live, observe=observe)
    expected = _cell_report(run_plus, _weights(run_plus, None))
    common = dict(valuation_date=vdate, version=version, base_run=run_plus, observe=observe,
                  transmission=transmission)
    cand_e = reanchor(book, facts, expected, **common)
    cand_f = reanchor(book, facts, report, near=cand_e.near, marked=marked, **common)
    live_e, live_f = live_at(cand_e.book, cand_e.facts, vdate), live_at(cand_f.book, cand_f.facts, vdate)
    run_e, run_f = run_grid(cand_e.book, cand_e.facts, live_e), run_grid(cand_f.book, cand_f.facts, live_f)
    out: dict[str, Any] = {
        "valuation_date": vdate, "observation": obs, "expected": expected, "candidate": cand_f,
        "candidate_expected": cand_e, "transmission": transmission, "band_draws": band_draws,
        "posterior": {"book": dict(run_a.ctx.posterior), "expected": dict(run_plus.ctx.posterior),
                      "candidate": dict(run_f.ctx.posterior)},
        "steps": {"rolled": headline(run_a), "learning": headline(run_plus),
                  "expected": headline(run_e), "candidate": headline(run_f)},
        "print_step": float(book.get("valuation.headline.print_step")),
        "checks": {"book": core_checks(run_a, vdate), "candidate": core_checks(run_f, vdate)},
        "growth": growth_spread(run_plus),
    }
    shocked = shock_regimes(run_a) if observe else []
    if shocked:                              # квартал шока: ожидаемый отчёт — среднее двугорбого прогноза (М§12)
        calm = expected_observation(book, facts, live, without=shocked)
        run_calm = run_grid(with_observation(book, calm), facts, live)
        by_regime = {r["regime"]: r for r in _regime_rows(book, facts, live)}
        out["no_shock"] = {"regimes": shocked, "observation": calm, "headline": headline(run_calm),
                           "posterior": dict(run_calm.ctx.posterior),
                           "shock_cor": {r: by_regime[r]["cor_q_mgmt"] for r in shocked},
                           "shock_probability": sum(by_regime[r]["posterior"] for r in shocked)}
    hist = history_run(book, run_plus)
    if hist is not run_plus:                 # κ-добавка закрытого квартала, которой у нового якоря нет (М§4.6)
        out["steps"]["history"] = _priced(run_plus, {c.key: hist.cell(*c.key).v_ri for c in run_plus.cells})
        out["history"] = {"adds": lost_kappa_adds(book, run_plus), "world": str(book.get(KAPPA_WORLD)),
                          "period": run_plus.ctx.timeline.period(1 + int(book.get("credit.real_rate_lag_q")))}
    if cells:
        out["mechanics"] = cell_mechanics(book, facts, run_plus, obs, vdate, transmission=transmission,
                                          history=hist)
        out["steps"]["mechanics"] = out["mechanics"]["headline"]
    if band_draws:
        for key, (b, f, lv) in {"rolled": (book, facts, live), "learning": (plus, facts, live),
                                "expected": (cand_e.book, cand_e.facts, live_e),
                                "candidate": (cand_f.book, cand_f.facts, live_f)}.items():
            out["steps"][key]["band"] = band_stats(b, f, lv, band_draws)
    return out


def growth_spread(run: GridRun) -> dict[str, Any] | None:
    """Доля прироста кредитных книг λ в закрываемом квартале по клеткам (М§4.13): наименьшая, наибольшая и масса
    клеток слоя «свой взгляд», где рост урезан капиталом. Рост не ограничен капиталом — None. Отчёт один на все
    клетки и несёт среднее их остатков: при разных λ это часть строки «выпуклость»."""
    if run.ctx.prep.growth is None:
        return None
    prob = run.layers[ANALYTICAL].prob
    lam = {c.key: float(c.quarters["lam"][1]) for c in run.cells}
    cut = [k for k, v in lam.items() if v < 1.0 - 1e-9]
    return {"min": min(lam.values()), "max": max(lam.values()), "cells": len(cut),
            "mass": sum(prob[k] for k in cut), "catch_up": run.ctx.prep.growth.catch_up}


def _regime_rows(book: Book, facts: Facts, live: LiveInputs) -> list[dict]:
    """Прогноз фильтра на первый прогнозный квартал по режимам (упр. базис) и их вероятности."""
    from model.nextreport import model_expectation
    period = str(book.get("meta.first_period"))
    return model_expectation(_drop_observation(book, period), facts, period, live=live)["by_regime"]


def is_dry_run(result: Mapping) -> bool:
    """Отчёт — сам ожидаемый отчёт (сухой прогон): факты обоих кандидатов совпадают."""
    return result["candidate"].facts.digest == result["candidate_expected"].facts.digest


# ------------------------------------------------------------------ REANCHOR.md


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{k}: {_fmt(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    return str(value)


def _mass(gate: tuple | None) -> str:
    """Масса сработавшего гейта для таблицы проверок: «—» — не сработал."""
    if gate is None:
        return "—"
    return "сработал" if gate[0] is None else f"{gate[0]:.4f}"


def _pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:.{digits}f} %".replace(".", ",")


STEP_TITLES = (
    ("rolled", "прежняя книга на дате оценки (без отчёта)"),
    ("learning", "+ наблюдение, равное ожиданию модели (обучение)"),
    ("history", "− κ-добавка закрытого квартала (история до сетки — общая для миров)"),
    ("mechanics", "каждая клетка — на своём пути (механика, ≈ 0)"),
    ("expected", "кандидат на ожидаемом отчёте (выпуклость)"),
    ("candidate", "кандидат на отчёте (сюрприз факта)"),
)
BAND_TITLES = (
    ("rolled", "прежняя книга (без отчёта)"),
    ("learning", "+ ожидаемое наблюдение (обучение)"),
    ("expected", "кандидат на ожидаемом отчёте (механика и выпуклость, ≈ 0)"),
    ("candidate", "кандидат на отчёте (сюрприз факта)"),
)


def mech_shift(steps: Mapping) -> dict[str, Any] | None:
    """Сдвиг строки «механика» (М§15.2): точка и V0 слоёв к базе сравнения — к строке «история до сетки», если она
    есть, иначе к прежней книге с ожидаемым наблюдением; рядом — доли цены и V0 слоя. Строки нет — None."""
    if "mechanics" not in steps:
        return None
    base, now = steps.get("history") or steps["learning"], steps["mechanics"]
    v0 = {k: now["v0"][k] - base["v0"][k] for k in base["v0"]}
    return {"point": now["point"] - base["point"], "point_rel": now["point"] / base["point"] - 1 if base["point"] else 0.0,
            "v0": v0, "v0_rel": {k: v0[k] / abs(base["v0"][k]) if base["v0"][k] else 0.0 for k in v0}}


def report_text(book: Book, result: Mapping) -> str:
    """REANCHOR.md: производные величины, «что сдвинулось», разложение скачка, ручные шаги."""
    cand: Reanchored = result["candidate"]
    X, d = cand.data, cand.derived
    M = X["meta"]
    lines = [f"# Перезаякоривание книги {book.get('meta.version')} на отчёт {cand.period}", ""]
    mech = result.get("mechanics")
    diagnosis = result["transmission"] == RESOLVE
    if mech and not mech["ok"]:
        w = mech["worst"]
        lines += [f"**ОТКАЗ: механика вне допуска** — клетка {w['cell']} на своём пути меняет стоимость на "
                  f"{_pct(w['r'], 3)} нормы клетки ({w['dv']:+.3f} млрд ₽ при норме {w['norm']:.1f}; к стоимости "
                  f"{_pct(w['rel'], 3)}; допуск {_pct(mech['tolerance'], 1)} нормы): "
                  + ("скаляры пути передачи ставки решены заново — это и есть сдвиг без новости, который снимает "
                     "режим `keep`." if diagnosis else
                     "какое-то правило, помнящее прошлое, не перенесено. Кандидат записан для разбора, "
                     "в канон не переносить."), ""]
    if diagnosis:
        lines += ["**ДИАГНОСТИКА: режим `resolve`.** Цели A-N2, A-N3 и доли оставлены числами прежней книги, "
                  "скаляры пути решены заново на структуре нового якоря — их сдвиг целиком в строке «механика». "
                  "Кандидат книги и фактов не записан: в процедуре перезаякоривания режим один — `keep` "
                  "(М§15.2 п. 8).", ""]
    lines += [f"Кандидат: версия {M['version']}, якорь {M['anchor_period']} (факты на {M['facts_date']}), "
              f"первый прогнозный квартал {M['first_period']}, дата оценки {M['valuation_date']}. "
              f"Передача ставки: `{result['transmission']}`.", ""]
    if is_dry_run(result):
        lines += ["Отчёт — ожидаемый (сухой прогон): фактов в нём нет, строка «сюрприз факта» — ноль.", ""]

    eng, mg = d["engine"], d["mgmt"]
    lines += ["## Производные величины", "",
              f"- квартал {cand.period}: ЧПМ движка {_pct(eng['nim'], 3)} (упр. {_pct(mg['nim'], 3)}), "
              f"CoR движка {_pct(eng['cor'], 3)} (упр. {_pct(mg['cor'], 3)}), C/I движка {_pct(eng['cir'], 2)}"]
    if result.get("observation"):
        exp = result["observation"]
        lines.append(f"- ожидание модели на квартал (упр.): ЧПМ {_pct(exp['nim'], 3)}, CoR {_pct(exp['cor'], 3)}")
    if d.get("observation"):
        obs, post = d["observation"], result["posterior"]
        lines.append("- наблюдение A-P2u с замороженными ожиданиями режимов: CoR " + _fmt(obs.get("mu_cor"))
                     + "; ЧПМ " + _fmt(obs.get("mu_nim")))
        lines.append("- вероятности режимов: книга " + _fmt(post["book"]) + " → после ожидаемого наблюдения "
                     + _fmt(post["expected"]) + " → кандидат " + _fmt(post["candidate"]))
        fl = d["regime_floor"]
        lines.append(f"- пол вероятности режима ({fl['share']:g} × базовая): " + _fmt(fl["floors"]) + "; на полу у "
                     "кандидата: " + (", ".join(fl["on_floor"]) or "нет")
                     + " — ниже пола вероятности после наблюдений не опускаются; его действие — в строке «обучение»")
    lines.append(f"- индекс цен квартала {d['price_index']:.6f}"
                 + (f" ({d['price_index_source']})" if d.get("price_index_source") else "")
                 + " — множитель реальных сумм книги и их осей")
    lines.append(f"- множитель плотностей RWA к RWA якоря {d['rwa_factor']:.6f}; вычеты: "
                 + ", ".join(f"`{k}` {_fmt(float(v)) if _num(v) else v}" for k, v in d["deductions"].items()))
    if fixed_share_line(d):
        lines.append(fixed_share_line(d))
    if fixed_change_line(d):
        lines.append(fixed_change_line(d))
    first = str(book.opt("meta.labels.capital.n20_short", "Н20.0"))
    second = str(book.opt("meta.labels.capital.n11_observed", "Н1.1")).split(",")[0]
    lines.append("- поправки «норматив − расчёт»: " + ", ".join(f"`{k}` {float(v):+.6f}" for k, v in d["gaps"].items())
                 + f"; якорь модели: {first} {_pct(d['anchor_row']['n20'], 3)}, {second} {_pct(d['anchor_row']['n11'], 3)}"
                 + (f"; в регуляторном капитале якоря — объявленные дивиденды с вычетом впереди {d['dpreg_anchor']:.3f} млрд ₽"
                    if d.get("dpreg_anchor") else ""))
    if anchor_facts(cand.facts, book.get("nii.books")).estimated:
        lines.append("- **нормативы якоря — оценка до выхода формы** (`capital.estimated`): вычеты и поправки выведены на "
                     "оценке; уровни капитала и RWA якоря — расчётом по ней на RWA модели"
                     + (": " + ", ".join(f"`{k}` {b:.3f}" for k, (_, b) in d["estimated_levels"].items())
                        if d.get("estimated_levels") else "")
                     + "; замена оценки фактом — `--capital-form` без смены якоря")
    if d.get("t2_anchor"):
        lines.append(f"- инструменты капитала: ключ квартала якоря `{T2}` — факт отчёта {d['t2_anchor'][1]:.3f} млрд ₽ "
                     f"(траектория книги давала {d['t2_anchor'][0]:.3f})")
    if t2_share_line(d):
        lines.append(t2_share_line(d, cand))
    if d.get("at1_share") or d.get("t2_premium"):
        lines.extend(at1_share_lines(d, None if cand is None else float(anchor_facts(
            cand.facts, cand.book.get("nii.books")).at1)))
    kept = "; ".join(f"`{k}` {a:.6f} → {b:.6f}" for k, (a, b, _) in d["transmission"].items())
    sig, omega = d["sigmas"], d["phi_weights"]
    lines.append(f"- передача ставки, скаляры пути {', '.join(SCALARS)}: прежняя книга " + _fmt(list(sig["old"]))
                 + ", кандидат " + _fmt(list(sig["new"])) + "; цели и доли на структуре нового якоря при прежних "
                 "скалярах: " + kept
                 + (" — в режиме `resolve` цели и доли оставлены прежними, скаляры решены заново"
                    if d["transmission_mode"] == RESOLVE else ""))
    lv = d.get("level")
    if lv:
        lines.append(f"- уровень маржи — ключ `{NIM_TARGET}`, стационарная маржа мира {lv['world']} на составе баланса "
                     f"якоря (упр.): прежняя книга {_pct(lv['key'][0], 3)} → кандидат {_pct(lv['key'][1], 3)}; по счёту "
                     f"ядра {_pct(lv['value'][0], 3)} → {_pct(lv['value'][1], 3)}, из сдвига маржа движка "
                     f"{_pp(lv['d_engine'])}, мост упр. ↔ движок {_pp(lv['d_bridge'])}; уровень мира-опоры решателя "
                     f"{lv['reference_world']} {_pct(lv['reference'][0], 3)} → {_pct(lv['reference'][1], 3)}"
                     + (f"; цель гейта `{NIM_STATIONARY}` в том же мире {_pct(lv['gate'][0], 3)} → "
                        f"{_pct(lv['gate'][1], 3)}" if lv.get("gate") else "")
                     + (" — ключ оставлен числом прежней книги, скаляры пути решены под него заново"
                        if lv["key"][0] == lv["key"][1] else
                        " — запись прежнего суждения на новом якоре, не пересмотр уровня"))
    if omega["old"]:
        drift = max(abs(omega["new"][b] - omega["old"][b]) for b in omega["old"])
        lines.append("- доли кредитных книг ω в разности опорных ставок X (добавка к стоимости пассивов) — со "
                     "структуры нового якоря: " + ", ".join(
                         f"{b} {omega['old'][b]:.4f} → {omega['new'][b]:.4f}" for b in omega["old"])
                     + f"; наибольший сдвиг {drift * 100:.3f} п.п. — скаляром не сохраняется, эффект в строке "
                     "«механика»")
    if segment_mix_line(d):
        lines.append(segment_mix_line(d))
    series = d.get("bridge_series") or {}
    lines.append("- мост упр. ↔ МСФО: " + ", ".join(
        f"{x} {d['bridge_old'][x]:+.6f} → {d['bridge_new'][x]:+.6f}" for x in ("cor", "nim", "cir"))
        + ("; уровень закрытого квартала (М§4.6): " + "; ".join(
            f"{x} — `{v['series']}`, {v['rule']}" for x, v in series.items()) if series else ""))
    if d.get("decision_rows"):
        lines.append("- решения собрания закрываемого квартала — строками истории дивидендов (годовой календарь, база "
                     "объёма iea, М§4.7): " + "; ".join(
                         f"{r['period']} DPS {_fmt(r['dps'])}, решение {r['decided_date']}"
                         + (f", сумма всех категорий {_fmt(r['pool_all_classes'])}" if r.get("pool_all_classes") is not None
                            else "") for r in d["decision_rows"]))
    lines.append("- заморожены числами прежней книги: "
                 + ", ".join(f"`{k}` = {_fmt(v)}" for k, v in d["frozen"].items()))
    if d.get("spread_books"):
        lines.append("- ключи спреда от ставок якоря выведены заново у книг: " + ", ".join(d["spread_books"]))
    path = result["candidate_expected"].derived.get("nim_path")
    if path:
        lines.append("- ближняя калибровка ЧПМ выведена на ожидаемом отчёте: наибольшее расхождение ожидаемого "
                     f"пути ЧПМ с прежней книгой {path['residual'] * 1e4:.2f} б.п. "
                     f"(кварталы {path['periods'][0]}…{path['periods'][-1]})")

    lines += dividend_lines(d.get("dividends"))
    lines += ["", "## Что сдвинулось в книге", "", "| путь | было | стало | почему |", "|---|---|---|---|"]
    lines += [f"| `{dotted(p)}` | {_fmt(a)} | {_fmt(b)} | {reason(dotted(p), d)} |" for p, a, b in cand.changes]

    steps = result["steps"]
    lines += ["", f"## Разложение скачка на {result['valuation_date']}: точка при значениях книги", "",
              "Низ — слой «рыночные ставки как есть», верх — «свой взгляд», точка — при λ книги; V0 — млрд ₽.", "",
              "| шаг | низ, ₽ | точка, ₽ | верх, ₽ | V0 свой взгляд | V0 рыночные ставки |",
              "|---|---|---|---|---|---|"]
    prev = None
    for key, title in STEP_TITLES:
        if key not in steps:
            continue
        if key == "expected" and "mechanics" not in steps:
            title = "кандидат на ожидаемом отчёте (механика и выпуклость, ≈ 0)"
        h = steps[key]
        now = [h["low"], h["point"], h["high"], h["v0"][ANALYTICAL], h["v0"][NEUTRAL]]
        if prev is None:
            lines.append(f"| {title} | " + " | ".join(f"{x:.2f}" for x in now[:3])
                         + " | " + " | ".join(f"{x:.1f}" for x in now[3:]) + " |")
        else:
            lines.append(f"| {title} | " + " | ".join(f"{x:.2f} ({x - y:+.2f})" for x, y in zip(now[:3], prev[:3]))
                         + " | " + " | ".join(f"{x:.1f} ({x - y:+.1f})" for x, y in zip(now[3:], prev[3:])) + " |")
        prev = now
    if "mechanics" not in steps:
        lines += ["", "Клетки на своём пути не считались (`--no-cells`): механика и выпуклость — одной строкой, "
                  "допуск механики не проверен."]
    gone = result.get("history")
    if gone:
        lines += ["", f"**История до сетки.** Пути стоимости риска режимов стоят в мире {gone['world']}; в прочих мирах к ним "
                  "идёт κ-добавка от реальной ставки с лагом. Реальная ставка закрываемого квартала давала в "
                  f"{gone['period']} добавку " + ", ".join(f"{w}: {v * 100:+.2f} п.п." for w, v in gone["adds"].items())
                  + "; у нового якоря этот квартал — история, общая для миров, и добавки нет (М§4.6). Строка «история до "
                  "сетки» — цена этого свойства ядра; клетки на своём пути и кандидат сверяются с прежней книгой уже без "
                  "добавки, в допуск механики строка не входит."]
    growth = result.get("growth")
    if growth and growth["cells"]:
        lines += ["", f"**Рост, ограниченный капиталом.** В закрываемом квартале доля прироста кредитных книг по клеткам — от "
                  f"{growth['min']:.2f} до {growth['max']:.2f}; рост урезан в {growth['cells']} клетках с массой "
                  f"{_pct(growth['mass'], 1)} слоя «свой взгляд». Отчёт один на все клетки и несёт среднее их остатков: "
                  "клетка, чей рост был урезан сильнее среднего, стартует с большего портфеля, и наоборот — это часть "
                  "строки «выпуклость», в строку «механика» не входит."
                  + ("" if not growth["catch_up"] else " Навёрстывание включено: разрыв с потенциальным путём при переносе "
                     "якоря стирается, и строка «механика» урезанных клеток не ноль.")]
    calm = result.get("no_shock")
    if calm:
        exp, a, plus, h = result["observation"], steps["rolled"], steps["learning"], calm["headline"]
        names = ", ".join(calm["regimes"])
        lines += ["", f"**Квартал шока режима {names}.** Закрываемый квартал лежит в году шока прежней книги: прогноз "
                  "наблюдения двугорбый — шок либо случился, либо нет. Ожидаемый отчёт несёт долю шока (CoR "
                  f"{_pct(exp['cor'], 3)} — смесь, в которой с вероятностью {_pct(calm['shock_probability'], 1)} "
                  "стоит CoR " + ", ".join(_pct(v, 2) for v in calm["shock_cor"].values()) + "): такого числа не ждёт "
                  "ни один режим, и «отчётом без новостей» он не является — фильтр читает его как стресс (М§12). "
                  f"Отчёт без шока — ожидание прочих режимов, CoR {_pct(calm['observation']['cor'], 3)}, ЧПМ "
                  f"{_pct(calm['observation']['nim'], 3)}: строка «обучение» — {h['point'] - a['point']:+.2f} ₽ точки "
                  f"(на ожидаемом отчёте {plus['point'] - a['point']:+.2f} ₽), вероятности режимов "
                  + _fmt(calm["posterior"]) + ". В журнал версии книги — оба числа."]
    if mech:
        worst = sorted(mech["rows"], key=lambda r: -abs(r["r"]))[:5]
        w = mech["worst"]
        below = sum(1 for r in mech["rows"] if abs(r["base"]) < r["norm"])
        lines += ["", "### Механика по клеткам", "",
                  f"Клеток {len(mech['rows'])}; наибольшее изменение стоимости клетки на своём пути — "
                  f"{_pct(w['r'], 4)} нормы клетки max(|V|, BV_v − C_v) ({w['cell']}: ΔV {w['dv']:+.4f} млрд ₽, "
                  f"капитал {w['bv_v']:.1f}, к стоимости {_pct(w['rel'], 4)}); допуск {_pct(mech['tolerance'], 1)} — "
                  + ("выполнен." if mech["ok"] else "НАРУШЕН.") + " Допуск — доля нормы клетки (М§15.2)."
                  + f" Клеток со стоимостью ниже капитала (норма — капитал): {below} из {len(mech['rows'])}."]
        head = mech_shift(steps)
        if head:
            lines.append(f"Строка «механика» рядом с вердиктом (М§15.2: V0 слоя — не больше 0,1 % V0 слоя, точка — не "
                         f"больше 0,1 % цены; код возврата судит клетки): точка {head['point']:+.4f} ₽ "
                         f"({_pct(head['point_rel'], 4)} цены), V0 «свой взгляд» {head['v0'][ANALYTICAL]:+.2f} млрд ₽ "
                         f"({_pct(head['v0_rel'][ANALYTICAL], 4)}), V0 «рыночные ставки» {head['v0'][NEUTRAL]:+.2f} млрд ₽ "
                         f"({_pct(head['v0_rel'][NEUTRAL], 4)}).")
        if mech["rearmed"]:
            lines.append(f"Год якоря сменился: клетки режима {', '.join(mech['rearmed'])} «перезаряжены» (год шока "
                         "сдвинут, М§3.2) — их путь другой по определению, в допуск они не входят.")
        if mech.get("history"):
            top = max(mech["rows"], key=lambda r: abs(r["history"]))
            lines.append("База сравнения — прежняя книга без κ-добавки закрытого квартала (история до сетки): сама добавка "
                         f"меняет стоимость клетки не больше чем на {_pct(abs(top['history']), 4)} ({top['cell']}) и в "
                         "допуск не входит.")
            lines += ["", "| клетка | V прежняя, млрд ₽ | без κ-добавки закрытого квартала | V на своём пути | "
                      "капитал BV_v | изменение к базе | к норме клетки |", "|---|---|---|---|---|---|---|"]
            lines += [f"| {r['cell']}{' (перезаряжена)' if r['rearmed'] else ''} | {r['old']:.1f} | {r['base']:.1f} "
                      f"({_pct(r['history'], 4)}) | {r['new']:.1f} | {r['bv_v']:.1f} | {_pct(r['rel'], 4)} | "
                      f"{_pct(r['r'], 4)} |" for r in worst]
        else:
            lines += ["", "| клетка | V прежняя, млрд ₽ | V на своём пути | капитал BV_v | к стоимости | к норме клетки |",
                      "|---|---|---|---|---|---|"]
            lines += [f"| {r['cell']}{' (перезаряжена)' if r['rearmed'] else ''} | {r['old']:.1f} | {r['new']:.1f} | "
                      f"{r['bv_v']:.1f} | {_pct(r['rel'], 4)} | {_pct(r['r'], 4)} |" for r in worst]

    lines += ["", "## Заголовок — медиана полосы", ""]
    if result.get("band_draws"):
        lines += [f"{result['band_draws']} прогонов на книгу, одни точки гиперкуба (сравнение парное); шаг печати "
                  f"{result['print_step']:g} ₽. У медианы механика и выпуклость — одной строкой"
                  + (" (в ней же — снятая κ-добавка закрытого квартала: у точки она стоит отдельной строкой)."
                     if result.get("history") else "."), "",
                  "| шаг | P10 | медиана | P90 | P(центр < рынка) |", "|---|---|---|---|---|"]
        before = None
        for key, title in BAND_TITLES:
            b = steps[key]["band"]
            if before is None:
                lines.append(f"| {title} | {b['p10']:.1f} | {b['median']:.1f} | {b['p90']:.1f} | {b['p_below']:.1%} |")
            else:
                lines.append(f"| {title} | " + " | ".join(
                    f"{b[k]:.1f} ({b[k] - before[k]:+.1f})" for k in ("p10", "median", "p90"))
                    + f" | {b['p_below']:.1%} ({(b['p_below'] - before['p_below']) * 100:+.1f} п.п.) |")
            before = b
    else:
        lines.append("Не считалась: разложение печатаемого заголовка — ключом `--band ПРОГОНОВ` (четыре полосы).")
    checks = result.get("checks")
    if checks:
        was, now = checks["book"], checks["candidate"]
        lines += ["", "## Проверки ядра на кандидате", ""]
        if now["error"]:
            lines.append(f"**Проверки не посчитаны:** {now['error']}")
        else:
            lines.append("Инварианты: " + ("выполнены все." if not now["invariants"] else "НАРУШЕНЫ — " + "; ".join(
                f"`{name}`: {message}" for name, message in now["invariants"])))
            names = list(dict.fromkeys(list(was["gates"]) + list(now["gates"])))
            if names:
                lines += ["", "Сработавшие гейты (масса — вероятность клеток, где условие нарушено: слоя «свой взгляд», у "
                          "гейта знака стресса — под вероятностями точки, у гейтов уровня книги — 1); каждому на "
                          "новой книге нужно действующее объяснение — `gate_explanations.yaml`, решение книги:", "",
                          "| гейт | прежняя книга | кандидат | сообщение на кандидате |", "|---|---|---|---|"]
                lines += [f"| `{n}` | {_mass(was['gates'].get(n))} | {_mass(now['gates'].get(n))} | "
                          f"{now['gates'][n][1] if n in now['gates'] else 'не сработал'} |" for n in names]
            else:
                lines.append("Сработавших гейтов нет.")
            if now.get("flags"):
                lines += ["", "Флаги ядра на кандидате (плашка, сборку не блокируют): "
                          + "; ".join(f"`{n}` — {m}" for n, m in now["flags"].items())]
            lines += target_lines(was, now)
            if was["error"]:
                lines += ["", f"На прежней книге проверки не посчитаны: {was['error']}"]
    if result.get("facts_check") is not None:
        lines += ["", "## Сверка фактов кандидата с пересобранными фактами", ""]
        if result["facts_check"]:
            lines += ["| поле якоря | кандидат | пересобранные факты |", "|---|---|---|"]
            lines += [f"| `{k}` | {_fmt(a)} | {_fmt(b)} |" for k, a, b in result["facts_check"]]
        else:
            lines.append("Расхождений нет: ядро читает из обоих наборов одно и то же состояние якоря.")
    lines += ["", "## Предупреждения и ручные шаги", ""] + [f"- {w}" for w in cand.warnings]
    lines += ["", "Механика ≈ 0 — инвариант `tests/test_reanchor*.py` (М§15.2): клетка на своём пути сохраняет "
              "стоимость в пределах 0,1 %. Строка «выпуклость» — неравенство Йенсена: отчёт один на все клетки, "
              "а слой «рыночные ставки как есть» ждал путь своего мира.", ""]
    return "\n".join(lines)


def dividend_lines(div: Mapping | None) -> list[str]:
    """Раздел «Дивиденды по периодам» (квартальный календарь, М§15.2 п. 9)."""
    if not div:
        return []
    was, now = div["p_last"]
    lines = ["", "## Дивиденды по периодам", "",
             f"Последний закрытый квартал прибыли: {was} → {now} — по самой поздней строке истории дивидендов с днём "
             "решения не позже даты фактов; дивиденд закрытого квартала уже вычтен из капитала якоря, в клетке его нет."]
    if div["closed"]:
        lines += ["", "Строки истории, закрывшие кварталы прибыли на новом якоре:", "",
                  "| квартал прибыли | DPS, ₽ | день решения |", "|---|---|---|"]
        lines += [f"| {r['period']} | {r['dps']:.4f} | {r['decided_date']} |" for r in div["closed"]]
    else:
        lines += ["", "Новых решений в закрытом квартале нет: закрытые кварталы прибыли те же."]
    listed = sum(r["amount"] for r in div["queue"])
    lines += ["", f"Объявлено и не выплачено на новом якоре: {listed:.3f} млрд ₽ из остатка «дивиденды к выплате» "
              f"{div['payable']:.3f}; остаток сверх списка — постоянное обязательство: не выплачивается и в регуляторный "
              "капитал не возвращается."]
    if div["queue"]:
        lines += ["", "| квартал прибыли | сумма, млрд ₽ | квартал выплаты | вычет из регуляторного капитала |", "|---|---|---|---|"]
        lines += [f"| {r['period']} | {r['amount']:.3f} | {r['pay']} | {r['reg'] or 'уже вычтен'} |" for r in div["queue"]]
    lines += ["", "Записи реестра в затравке нового якоря: " + (", ".join(div["seed"]) or "нет")
              + "; выпали (экс-дата не позже новой даты фактов): " + (", ".join(div["dropped"]) or "нет")
              + "; добавлены из решений отчёта: " + (", ".join(div["added"]) or "нет") + "."]
    return lines


# ------------------------------------------------------------------ шаблон книги


def _bare(text: str) -> bool:
    return bool(text) and text.isascii() and text.replace("_", "a").isalnum() and not text[0].isdigit() \
        and text.lower() not in ("null", "true", "false", "yes", "no", "on", "off")


def _flow(value: Any) -> str:
    """Значение в строку потока YAML (ключи-периоды в кавычках, как в шаблоне книги)."""
    if isinstance(value, Mapping):
        return "{" + ", ".join((str(k) if _bare(str(k)) else json.dumps(str(k), ensure_ascii=False))
                               + ": " + _flow(v) for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_flow(v) for v in value) + "]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and "e" in repr(value) and "." not in repr(value):
        return repr(value).replace("e", ".0e", 1)   # YAML 1.1 (PyYAML) читает «2e-06» без точки строкой
    if isinstance(value, (int, float)):
        return repr(value)
    return str(value) if _bare(str(value)) else json.dumps(str(value), ensure_ascii=False)


def _span(node: yaml.Node) -> tuple[int, int]:
    """Границы узла в тексте; у блочной коллекции конец — конец последнего элемента (без хвоста
    из пустых строк и комментариев)."""
    if isinstance(node, yaml.ScalarNode) or getattr(node, "flow_style", False) or not node.value:
        return node.start_mark.index, node.end_mark.index
    last = node.value[-1]
    return node.start_mark.index, _span(last[1] if isinstance(last, tuple) else last)[1]


def _find(node: yaml.Node | None, path: Path_) -> yaml.Node | None:
    for part in path:
        if isinstance(part, tuple):
            if not isinstance(node, yaml.SequenceNode):
                return None
            node = next((item for item in node.value if isinstance(item, yaml.MappingNode) and any(
                k.value == part[0] and getattr(v, "value", None) == part[1] for k, v in item.value)), None)
        else:
            if not isinstance(node, yaml.MappingNode):
                return None
            node = next((v for k, v in node.value if str(k.value) == part), None)
        if node is None:
            return None
    return node


def _value_at(data: Any, path: Path_) -> Any:
    for part in path:
        if isinstance(part, tuple):
            data = next(x for x in data if isinstance(x, Mapping) and x.get(part[0]) == part[1])
        else:
            data = data[part]
    return data


def patch_template(text: str, cand: Reanchored) -> str:
    """Шаблон книги с правками кандидата: меняется только текст изменившихся значений,
    комментарии остаются. Результат сверяется с кандидатом целиком; расхождение — отказ."""
    root = yaml.compose(text)
    edits: dict[Path_, tuple[int, int, str]] = {}
    for path, _old, new in cand.changes:
        target = path
        node = _find(root, target)
        while node is None or new is None:           # ключ добавлен или убран — правится родитель
            target = target[:-1]
            if not target:
                raise ReportError(f"шаблон книги: нет узла для правки {dotted(path)}")
            node = _find(root, target)
            new = True
        edits[target] = (*_span(node), _flow(_value_at(cand.data, target)))
    out = text
    chosen = [p for p in edits if not any(p[:n] in edits for n in range(1, len(p)))]
    for path in sorted(chosen, key=lambda p: -edits[p][0]):
        start, stop, new_text = edits[path]
        out = out[:start] + new_text + out[stop:]
    got, want = _plain(yaml.safe_load(out)), _plain(cand.data)
    for w in want["worlds"].get("ids", []):          # блоки миров и надстройку вписывает сборка книги
        if w not in got["worlds"]:
            want["worlds"].pop(w, None)
    if "worlds_bank" not in got:
        want.pop("worlds_bank", None)
    if _get(got, "worlds.overlay.sha256") is None:
        want["worlds"]["overlay"]["sha256"] = None
    if got != want:
        raise ReportError("шаблон книги после правок не равен кандидату — правки шаблона переносятся "
                          "вручную по таблице «что сдвинулось»")
    return out


# ------------------------------------------------------------------ сверка фактов


def _beyond_anchor(book: Book, facts: Facts) -> dict[str, Any]:
    """Состояние, которое ядро читает из фактов сверх `anchor_facts`: постоянные прочие активы, экономически
    собственные акции, значения мостов, а при квартальном календаре — список «объявлено, не выплачено», строки
    истории дивидендов (квартал прибыли → DPS и день решения) и затравка реестра; при связи строк с объёмом —
    базы объёма пяти концов кварталов."""
    out: dict[str, Any] = {}
    bal, shares = facts.file("balance"), facts.file("shares")
    if isinstance(bal.get("other_assets_fixed"), Mapping):
        out["other_assets_fixed"] = _fact(bal["other_assets_fixed"])
    if isinstance(shares.get("economic_treasury"), Mapping):
        out["economic_treasury"] = _fact(shares["economic_treasury"])
    out["bridge"] = {x: facts.v("bridge_mgmt_ifrs", f"{x}.value") for x in ("cor", "nim", "cir")}
    if is_quarterly(book):
        out["dividends_payable_declared"] = {str(_fact(x.get("period"))): _fact(x.get("amount"))
                                             for x in bal.get("dividends_payable_declared") or []}
        div = facts.file("dividends")
        out["dividend_history"] = {str(_fact(r.get("period"))): {"dps": history_dps(r),
                                                                 "decided_date": str(_fact(r.get("decided_date")))}
                                   for r in div.get("history") or []}
        out["register_seed"] = {str(_fact(r.get("period"))): {"dps": _fact(r.get("dps")), "status": _fact(r.get("status"))}
                                for r in div.get("register_seed") or []}
    base = book.opt("volumes.link_base")
    if base and any(float(book.opt(p, 0.0)) for p in ("fees.volume_link", "other.insurance_volume_link", "opex.volume_link")):
        rows = facts.periods("balance", "history")
        last = sorted(rows, key=pindex)[-5:]
        out["volume_base"] = {p: _fact(rows[p].get(base)) for p in last}
    return out


def compare_facts(book: Book, candidate: Facts, other: Facts, tol: float = 1e-6) -> list[tuple[str, Any, Any]]:
    """Состояние якоря, которое ядро читает из фактов кандидата и из пересобранных фактов
    (`build_facts.py --anchor` или `--expected`): поля, разошедшиеся больше допуска."""
    books = book.get("nii.books")
    a, b = asdict(anchor_facts(candidate, books)), asdict(anchor_facts(other, books))
    a.update(_beyond_anchor(book, candidate))
    b.update(_beyond_anchor(book, other))
    if a.get("estimated") and b.get("estimated"):
        # нормативы — оценка до выхода формы: уровни капитала и RWA кандидат несёт расчётом по оценке, а сборщик —
        # значениями последней формы с пометкой оценки; сверяются нормативы, уровни придут с формой
        for key in ESTIMATED_LEVELS:
            a.pop(key, None)
            b.pop(key, None)
    out: list[tuple[str, Any, Any]] = []

    def walk(x: Any, y: Any, where: str) -> None:
        if isinstance(x, Mapping) and isinstance(y, Mapping):
            for k in sorted(set(x) | set(y), key=str):
                if where == "pnl" and (k not in x or k not in y):
                    continue                     # история ОПУ разной глубины — не состояние якоря
                walk(x.get(k), y.get(k), f"{where}.{k}" if where else str(k))
        elif _num(x) and _num(y):
            if abs(x - y) > tol * max(1.0, abs(x), abs(y)):
                out.append((where, x, y))
        elif x != y:
            out.append((where, x, y))

    walk(a, b, "")
    return out


# ------------------------------------------------------------------ замена оценки нормативов фактом формы


def read_form(path: Path) -> dict:
    form = read_report(path)
    return form


def check_form(book: Book, facts: Facts, form: Mapping) -> None:
    """Файл формы (`capital-form/1`): нормативы и капитал банковской группы на дату якоря книги."""
    unknown = sorted(set(form) - set(CAPITAL_FORM_REQUIRED) - set(CAPITAL_FORM_OPTIONAL))
    missing = [k for k in CAPITAL_FORM_REQUIRED if k not in form]
    if unknown or missing:
        raise ReportError("файл формы: " + "; ".join(x for x in (
            f"незнакомые ключи {', '.join(unknown)}" if unknown else "",
            f"нет ключей {', '.join(missing)}" if missing else "") if x)
            + f" (известны: {', '.join(CAPITAL_FORM_REQUIRED + CAPITAL_FORM_OPTIONAL)})")
    if form.get("schema", CAPITAL_FORM) != CAPITAL_FORM:
        raise ReportError(f"файл формы: schema {form['schema']!r}, ожидается {CAPITAL_FORM!r}")
    anchor = str(book.get("meta.anchor_period"))
    if str(form["period"]) != anchor or str(facts.plain("anchor", "period")) != anchor:
        raise ReportError(f"файл формы за {form['period']}, якорь книги — {anchor}, фактов — "
                          f"{facts.plain('anchor', 'period')}: замена оценки идёт на якоре книги, без его смены")
    if "as_of" in form and str(form["as_of"]) != period_end(anchor).isoformat():
        raise ReportError(f"файл формы: as_of {form['as_of']} — не конец квартала якоря {anchor}")
    for key in CAPITAL_FORM_REQUIRED[1:] + ("t2",):
        if key in form and not _num(form[key]):
            raise ReportError(f"файл формы: {key} = {form[key]!r} — ожидается число")
    for key in ("n20_0", "n1_1_bank"):
        _fraction(float(form[key]), key)
    for key in ("basel_cet1", "basel_rwa", "bank_base_capital"):
        if form[key] <= 0:
            raise ReportError(f"файл формы: {key} = {form[key]} — ожидается положительное число")
    if "n20_pre_dividend" in form and not isinstance(form["n20_pre_dividend"], bool):
        raise ReportError("файл формы: n20_pre_dividend — true или false")


def facts_with_form(facts: Facts, form: Mapping) -> Facts:
    """Факты того же якоря с нормативами и капиталом формы: оценка заменена фактом, пометки оценки сняты."""
    period = str(form["period"])
    tag = f"reanchor: форма на якорь {period}" + (f" ({form['source']})" if form.get("source") else "")
    files = copy.deepcopy(dict(facts.files))
    cap = files["capital"]
    values = {"n20_0.value": form["n20_0"], "n1_1_bank.value": form["n1_1_bank"], "basel.cet1": form["basel_cet1"],
              "basel.rwa": form["basel_rwa"], "bank_base_capital": form["bank_base_capital"]}
    if "t2" in form:
        values["t2_recognized"] = form["t2"]
    if isinstance(_get(cap, "basel.cet1_ratio"), dict):
        values["basel.cet1_ratio"] = _r(form["basel_cet1"] / form["basel_rwa"], 6)
    for path, value in values.items():
        _set(cap, path, _node(float(value), tag))
    for name in ESTIMATE_SLOTS.values():
        if "estimated" in cap[name]:
            cap[name]["estimated"] = False
        cap[name].pop("estimate", None)
    if "n20_pre_dividend" in form:
        cap["n20_0"]["pre_dividend"] = bool(form["n20_pre_dividend"])
        cap["n20_0"].pop("pre_dividend_note", None)
    t2 = form.get("t2", _get(cap, "t2_recognized.v"))
    known = {"n20_0": form["n20_0"], "cet1": form["basel_cet1"], "rwa": form["basel_rwa"], "n1_1_bank": form["n1_1_bank"],
             "n20_1": form["n1_1_bank"], "capital_base": form["bank_base_capital"], "capital_additional": t2,
             "capital_total": None if t2 is None else form["basel_cet1"] + t2, "rwa_imputed": form["basel_rwa"]}
    rows = cap.get("history")
    row = (rows.get(period) if isinstance(rows, dict)
           else next((r for r in rows or [] if isinstance(r, dict) and r.get("period") == period), None))
    if isinstance(row, dict):
        for key, value in known.items():
            if isinstance(row.get(key), dict) and value is not None:
                row[key] = _node(_r(float(value)), tag)
    return Facts(root=Path(f"capital-form-{period}"), files=files,
                 digest=hashlib.sha256(canonical_json(files)).hexdigest())


def replace_capital(book: Book, facts: Facts, form: Mapping, *, valuation_date: Any = None,
                    version: str | None = None) -> dict:
    """Замена оценки нормативов якоря фактом формы БЕЗ смены якоря (М§3.3, §15.2 п. 10): факты капитала —
    значения формы, пометка оценки снята; калибровки к якорю выводятся заново тем же правилом, что при
    переносе якоря, — вычеты формулой книги, плотности RWA общим множителем к RWA формы, ключ квартала якоря
    траектории инструментов капитала, поправки «норматив − расчёт». Ближняя калибровка ЧПМ, наблюдения и
    передача ставки не трогаются: квартал тот же. Возвращает кандидата и точку до и после на дате оценки —
    это строка «факты» разложения между выпусками (М§16), а не механика."""
    check_form(book, facts, form)
    anchor = str(book.get("meta.anchor_period"))
    try:
        vdate = to_date(valuation_date or book.get("meta.valuation_date"))
    except ValueError as exc:
        raise ReportError(f"дата оценки {valuation_date!r} — не дата ГГГГ-ММ-ДД") from exc
    warnings: list[str] = []
    derived: dict[str, Any] = {"was_estimated": list(anchor_facts(facts, book.get("nii.books")).estimated)}
    if not derived["was_estimated"]:
        warnings.append("нормативы якоря в фактах не помечены оценкой: файл формы заменяет факт фактом — проверить, "
                        "что это исправление, а не повторная замена")
    X = copy.deepcopy(dict(book.source))
    X["meta"].update(version=version or f"{X['meta']['version']}+form", valuation_date=vdate.isoformat())
    new_facts = facts_with_form(facts, form)
    if _get(X, T2) is not None and form.get("t2") is not None:
        traj = _get(X, T2)
        now = Trajectory(traj).value(*parse_period(anchor))
        if abs(float(form["t2"]) - now) > T2_TOL:
            if not isinstance(traj, Mapping):
                raise ReportError(f"{T2} — скаляр, а инструменты капитала формы {form['t2']} отличаются от него: нужна "
                                  "траектория с ключом квартала якоря (решение книги)")
            _set(X, T2, _sorted_traj({**traj, anchor: _r(float(form["t2"]), 6)}))
            derived["t2_anchor"] = (now, float(form["t2"]))
            warnings.append(f"{T2}: ключ квартала якоря {anchor} — факт формы {float(form['t2']):g} (было {now:g}); "
                            "остальные ключи траектории — суждение книги: пересмотреть")
    calibrate_capital(X, new_facts, float(form["basel_rwa"]), derived, warnings, old=book)
    check_bundles(X, book.source)
    fact = {"n20": float(form["n20_0"]), "n11": float(form["n1_1_bank"])}
    for _ in range(PASSES):
        run = run_grid(book_from_dict(X, facts=new_facts), new_facts)
        weights = _weights(run, None)
        moved = 0.0
        for path, name in GAPS:
            delta = fact[name] - _anchor_row(run, weights, name)
            if abs(delta) > GAP_TOL:
                value = float(_get(X, path))
                _set(X, path, _r(value + delta, 12))
                _remap_axes(X, path, value, value + delta)
                moved = max(moved, abs(delta))
        if moved <= GAP_TOL:
            break
    cand = book_from_dict(X, facts=new_facts)
    live_a, live_b = live_at(book, facts, vdate), live_at(cand, new_facts, vdate)
    run_a, run_b = run_grid(book, facts, live_a), run_grid(cand, new_facts, live_b)
    weights = _weights(run_b, None)
    derived.update(gaps={path: _get(X, path) for path, _ in GAPS},
                   anchor_row={name: _anchor_row(run_b, weights, name) for _, name in GAPS},
                   old_values={"n20": anchor_facts(facts, book.get("nii.books")).n20,
                               "n11": anchor_facts(facts, book.get("nii.books")).n11_bank})
    warnings += ["оси поправок нормативов сдвинуты вместе с центром: ширину пересмотреть (решение книги)",
                 "объяснения гейтов, результаты книги и закреплённые числа — на новой версии книги; в разложении "
                 "между выпусками замена оценки фактом — строка «факты» (М§16)",
                 "канон фактов пересобирает `ops/tools/build_facts.py` (форма — в листе формы группы папки передачи); "
                 "сверка с фактами кандидата — `--compare-facts`"]
    candidate = Reanchored(data=X, book=cand, facts=new_facts, period=anchor, derived=derived,
                           changes=diff(dict(book.source), X), warnings=warnings,
                           near=copy.deepcopy(X["regimes"]["near_nim_shift"]))
    return {"candidate": candidate, "valuation_date": vdate, "form": dict(form),
            "steps": {"book": headline(run_a), "candidate": headline(run_b)},
            "print_step": float(book.get("valuation.headline.print_step")),
            "checks": {"book": core_checks(run_a, vdate), "candidate": core_checks(run_b, vdate)}}


def form_text(book: Book, result: Mapping) -> str:
    """REANCHOR.md режима `--capital-form`: что заменено, что выведено заново, сдвиг точки от замены оценки фактом."""
    cand: Reanchored = result["candidate"]
    d, M, form = cand.derived, cand.data["meta"], result["form"]
    first = str(book.opt("meta.labels.capital.n20_short", "Н20.0"))
    second = str(book.opt("meta.labels.capital.n11_observed", "Н1.1")).split(",")[0]
    a, b = result["steps"]["book"], result["steps"]["candidate"]
    lines = [f"# Замена оценки нормативов фактом формы: книга {book.get('meta.version')}, якорь {cand.period}", "",
             f"Кандидат: версия {M['version']}, якорь прежний — {M['anchor_period']} (факты на {M['facts_date']}), дата "
             f"оценки {M['valuation_date']}. Перезаякоривания нет: квартал тот же, меняются факты капитала и калибровки "
             "к якорю.", "",
             "## Что заменено", "",
             f"- {first}: {_pct(d['old_values']['n20'], 3)} → {_pct(float(form['n20_0']), 3)}; {second}: "
             f"{_pct(d['old_values']['n11'], 3)} → {_pct(float(form['n1_1_bank']), 3)}"
             + (" (прежние значения — оценка: " + ", ".join(d["was_estimated"]) + ")" if d["was_estimated"] else ""),
             f"- множитель плотностей RWA к RWA формы {d['rwa_factor']:.6f}; вычеты: "
             + ", ".join(f"`{k}` {_fmt(float(v)) if _num(v) else v}" for k, v in d["deductions"].items()),
             "- поправки «норматив − расчёт»: " + ", ".join(f"`{k}` {float(v):+.6f}" for k, v in d["gaps"].items())
             + f"; якорь модели: {first} {_pct(d['anchor_row']['n20'], 3)}, {second} {_pct(d['anchor_row']['n11'], 3)}"]
    if fixed_share_line(d):
        lines.append(fixed_share_line(d))
    if d.get("t2_anchor"):
        lines.append(f"- инструменты капитала: ключ квартала якоря `{T2}` {d['t2_anchor'][0]:.3f} → {d['t2_anchor'][1]:.3f} млрд ₽")
    lines += ["", "## Что сдвинулось в книге", "", "| путь | было | стало | почему |", "|---|---|---|---|"]
    lines += [f"| `{dotted(p)}` | {_fmt(x)} | {_fmt(y)} | "
              f"{'новая версия книги на том же якоре' if dotted(p).startswith('meta.') else reason(dotted(p)) or 'замена оценки фактом формы'} |"
              for p, x, y in cand.changes]
    lines += ["", f"## Сдвиг точки на {result['valuation_date']} (строка «факты»)", "",
              "| | низ, ₽ | точка, ₽ | верх, ₽ |", "|---|---|---|---|",
              f"| книга на оценке нормативов | {a['low']:.2f} | {a['point']:.2f} | {a['high']:.2f} |",
              f"| кандидат на форме | {b['low']:.2f} ({b['low'] - a['low']:+.2f}) | {b['point']:.2f} "
              f"({b['point'] - a['point']:+.2f}) | {b['high']:.2f} ({b['high'] - a['high']:+.2f}) |"]
    band = result.get("band")
    if band:
        x, y = band
        lines += ["", f"Медиана полосы ({result['band_draws']} прогонов, одни точки гиперкуба): {x['median']:.1f} → "
                  f"{y['median']:.1f} ({y['median'] - x['median']:+.1f}); P10 {x['p10']:.1f} → {y['p10']:.1f}; "
                  f"P90 {x['p90']:.1f} → {y['p90']:.1f}."]
    was, now = result["checks"]["book"], result["checks"]["candidate"]
    lines += ["", "## Проверки ядра на кандидате", ""]
    if now["error"]:
        lines.append(f"**Проверки не посчитаны:** {now['error']}")
    else:
        lines.append("Инварианты: " + ("выполнены все." if not now["invariants"] else "НАРУШЕНЫ — " + "; ".join(
            f"`{name}`: {message}" for name, message in now["invariants"])))
        names = list(dict.fromkeys(list(was["gates"]) + list(now["gates"])))
        if names:
            lines += ["", "| гейт | книга на оценке | кандидат | сообщение на кандидате |", "|---|---|---|---|"]
            lines += [f"| `{n}` | {_mass(was['gates'].get(n))} | {_mass(now['gates'].get(n))} | "
                      f"{now['gates'][n][1] if n in now['gates'] else 'не сработал'} |" for n in names]
        if now.get("flags"):
            lines += ["", "Флаги ядра на кандидате: " + "; ".join(f"`{n}` — {m}" for n, m in now["flags"].items())]
        lines += target_lines(was, now, "книга на оценке")
    if result.get("facts_check") is not None:
        lines += ["", "## Сверка фактов кандидата с пересобранными фактами", ""]
        if result["facts_check"]:
            lines += ["| поле | кандидат | пересобранные факты |", "|---|---|---|"]
            lines += [f"| `{k}` | {_fmt(x)} | {_fmt(y)} |" for k, x, y in result["facts_check"]]
        else:
            lines.append("Расхождений нет: ядро читает из обоих наборов одно и то же состояние якоря.")
    lines += ["", "## Предупреждения и ручные шаги", ""] + [f"- {w}" for w in cand.warnings] + [""]
    return "\n".join(lines)


def write_form_candidate(out: Path, book: Book, result: Mapping, template: Path | None = None) -> None:
    """Кандидат книги и фактов после замены оценки фактом формы и REANCHOR.md о замене — в каталог `out`."""
    check_out(out)
    cand: Reanchored = result["candidate"]
    text = yaml.safe_dump(cand.data, allow_unicode=True, sort_keys=False, width=100000)
    if _plain(yaml.safe_load(text)) != _plain(cand.data):
        raise ReportError("кандидат не переживает YAML туда-обратно — отказ записи")
    patched = None
    if template is not None and Path(template).exists():
        try:
            patched = patch_template(Path(template).read_text(encoding="utf-8"), cand)
        except (ReportError, yaml.YAMLError, StopIteration) as exc:
            cand.warnings.append(f"шаблон книги не записан: {exc or 'узел шаблона не найден'}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "facts").mkdir(exist_ok=True)
    _write(out / "assumptions.yaml", text)
    _write(out / "assumptions.json", _json(cand.data))
    if patched is not None:
        _write(out / "assumptions_template.yaml", patched)
    for name, content in cand.facts.files.items():
        _write(out / "facts" / f"{name}.json", _json(content))
    _write(out / "REANCHOR.md", form_text(book, result))


# ------------------------------------------------------------------ запись и запуск


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def check_out(out: Path) -> None:
    """Внутри репозитория инструмент пишет только под `var/`: кандидат — не канон, а всё остальное
    дерево рабочей копии либо канон (`data/`, `model/`, `docs/`), либо уходит в git, CI и на
    витрину (`tests/`, `ops/`, `web/`…). Вне репозитория — без ограничений."""
    if _inside(out, ROOT) and not _inside(out, ROOT / WRITABLE):
        where = out.resolve().relative_to(ROOT.resolve()).parts
        raise ReportError(
            f"запись в {out} — внутри репозитория вне {WRITABLE}/ ({where[0] + '/' if where else 'корень'}): "
            "кандидата в канон переносят владельцы книги и фактов (docs/REANCHOR.md), инструмент туда не "
            f"пишет; каталог кандидата — под {WRITABLE}/ или вне рабочей копии")


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")


def _json(tree: Any) -> str:
    return json.dumps(tree, ensure_ascii=False, indent=1) + "\n"


def write_candidate(out: Path, book: Book, result: Mapping, template: Path | None = None) -> None:
    """Кандидат книги и фактов, ожидаемый отчёт и REANCHOR.md — в каталог `out`. В режиме `resolve`
    (диагностика) — только ожидаемый отчёт и REANCHOR.md: такого кандидата в канон не переносят."""
    check_out(out)
    cand: Reanchored = result["candidate"]
    if result["transmission"] == RESOLVE:
        out.mkdir(parents=True, exist_ok=True)
        _write(out / "expected.json", _json(result["expected"]))
        _write(out / "REANCHOR.md", report_text(book, result))
        return
    text = yaml.safe_dump(cand.data, allow_unicode=True, sort_keys=False, width=100000)
    if _plain(yaml.safe_load(text)) != _plain(cand.data):
        raise ReportError("кандидат не переживает YAML туда-обратно — отказ записи")
    patched = None
    if template is not None and Path(template).exists():
        try:
            patched = patch_template(Path(template).read_text(encoding="utf-8"), cand)
        except (ReportError, yaml.YAMLError, StopIteration) as exc:
            cand.warnings.append(f"шаблон книги не записан: {exc or 'узел шаблона не найден'}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "facts").mkdir(exist_ok=True)
    _write(out / "assumptions.yaml", text)
    _write(out / "assumptions.json", _json(cand.data))
    if patched is not None:
        _write(out / "assumptions_template.yaml", patched)
    for name, content in cand.facts.files.items():
        _write(out / "facts" / f"{name}.json", _json(content))
    _write(out / "expected.json", _json(result["expected"]))
    _write(out / "REANCHOR.md", report_text(book, result))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", type=Path, default=BOOK_PATH, help="машинная книга (по умолчанию — канон)")
    ap.add_argument("--facts-dir", type=Path, default=FACTS_DIR, help="факты прежнего якоря")
    ap.add_argument("--template", type=Path, default=TEMPLATE, help="шаблон книги для кандидата шаблона")
    ap.add_argument("--expected", type=Path, metavar="ФАЙЛ",
                    help="записать ожидаемый отчёт закрываемого квартала и выйти")
    ap.add_argument("--facts", type=Path, metavar="ФАЙЛ", help="файл отчёта квартала")
    ap.add_argument("--out", type=Path, help="каталог кандидата (по умолчанию var/reanchor/<квартал>/)")
    ap.add_argument("--valuation-date", help="дата оценки разложения и кандидата")
    ap.add_argument("--version", help="версия кандидата (по умолчанию «<версия>+<квартал>»)")
    ap.add_argument("--band", type=int, metavar="ПРОГОНОВ",
                    help="разложение печатаемой медианы на ПРОГОНОВ прогонах каждой из четырёх книг")
    ap.add_argument("--no-cells", action="store_true",
                    help="не считать строку «механика» по клеткам (быстрее; допуск механики не проверяется)")
    ap.add_argument("--transmission", choices=TRANSMISSION_MODES, default=KEEP,
                    help="keep (по умолчанию, режим процедуры) — скаляры пути σ0_A, σ0_L, φ_A, φ_L прежней книги, "
                         "цели A-N2, A-N3 и обе доли пересчитываются на структуру нового якоря; resolve — только "
                         "диагностика: цели прежние, скаляры решаются заново, кандидат не пишется")
    ap.add_argument("--compare-facts", type=Path, metavar="КАТАЛОГ",
                    help="сверить факты кандидата с пересобранными фактами нового якоря")
    ap.add_argument("--capital-form", type=Path, metavar="ФАЙЛ",
                    help="замена оценки нормативов якоря фактом формы БЕЗ смены якоря: файл capital-form/1 с нормативами "
                         "и капиталом группы на дату якоря; кандидат книги и фактов и REANCHOR.md о замене — в --out")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        facts = load_facts(args.facts_dir)
        book = load_book(args.book, facts=facts)
        if args.expected:
            check_out(args.expected)
            report = expected_report(book, facts)
            args.expected.parent.mkdir(parents=True, exist_ok=True)
            _write(args.expected, _json(report))
            print(f"ожидаемый отчёт за {report['period']} → {args.expected}")
            return 0
        if args.capital_form:
            form = read_form(args.capital_form)
            out = args.out or DEFAULT_OUT / f"{form.get('period', 'anchor')}-form"
            check_out(out)
            result = replace_capital(book, facts, form, valuation_date=args.valuation_date, version=args.version)
            if args.band:
                vdate, cand = result["valuation_date"], result["candidate"]
                result["band_draws"] = args.band
                result["band"] = (band_stats(book, facts, live_at(book, facts, vdate), args.band),
                                  band_stats(cand.book, cand.facts, live_at(cand.book, cand.facts, vdate), args.band))
            if args.compare_facts:
                result["facts_check"] = compare_facts(book, result["candidate"].facts, load_facts(args.compare_facts))
            write_form_candidate(out, book, result, args.template)
            print(form_text(book, result))
            return 0
        if not args.facts:
            ap.error("нужен --facts ФАЙЛ (или --expected ФАЙЛ, или --capital-form ФАЙЛ)")
        report = read_report(args.facts)
        out = args.out or DEFAULT_OUT / str(report.get("period", "report"))
        check_out(out)
        marked = None
        if args.template is not None and Path(args.template).exists():
            try:
                marked = derived_on_core(Path(args.template).read_text(encoding="utf-8"))
            except yaml.YAMLError:
                marked = None                # шаблон не читается: перечень — общими словами, о шаблоне скажет запись
        result = attribution(book, facts, report, valuation_date=args.valuation_date, version=args.version,
                             band_draws=args.band, cells=not args.no_cells, transmission=args.transmission,
                             marked=marked)
        if args.compare_facts:
            result["facts_check"] = compare_facts(book, result["candidate"].facts, load_facts(args.compare_facts))
        write_candidate(out, book, result, args.template)
    except (ReportError, BookError, FactsError) as exc:
        print(f"reanchor: {exc}", file=sys.stderr)
        return 1
    print(report_text(book, result))
    mech = result.get("mechanics")
    if mech and not mech["ok"]:
        print(f"reanchor: механика вне допуска ({mech['worst']['cell']}: {mech['worst']['r']:+.4%} нормы клетки, "
              f"{mech['worst']['rel']:+.4%} стоимости) — "
              + (f"диагностика режима resolve, в {out} — только REANCHOR.md" if args.transmission == RESOLVE
                 else f"кандидат в {out} только для разбора"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
