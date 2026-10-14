# -*- coding: utf-8 -*-
"""Описание вывода на ядре для команды перевывода книги (`ops/tools/rederive.py`): куда в шаблоне книги ложится
каждое число листа `derive_on_engine.py`, по какому правилу оно выведено и в каких пределах оно разумно.

Правил шагов здесь нет — они в листе рядом. Здесь то, чего лист не знает: адрес числа в шаблоне, точность его записи,
коридор разумного и невязки правил, при которых запись останавливается. Команда берёт перечень шагов, их порядок,
ключи записи и коридоры ОТСЮДА и наизусть их не знает: у другой книги (другой эмитент, другие шаги) переписываются лист
и это описание, команда — нет.

Что описано:
  SHEET, STEPS, LINKED  лист вывода, перечень и порядок его шагов (берутся из листа, не повторяются);
  RECORD                файлы записи вывода рядом с листом;
  PHASES                как лист запускается: центр — один раз до сходимости; концы осей и корни справочных вариантов —
                        после центра, с его записанных чисел (ключ листа --start);
  WRITES                записи: шаг → адрес в шаблоне ← место числа в записи листа, правило словами, единица последнего
                        записанного знака, коридор разумного, несёт ли ключ пометку «ВЫВЕДЕНО НА ЯДРЕ» с датой;
  SAME                  суждения, которые лист держит своей константой: в шаблон не пишутся, обязаны совпасть с книгой;
  RESIDUALS             невязки правил на записанных числах: вывод сошёлся и попал в цель каждого правила;
  relations()           соотношения между выведенными числами (центр внутри своей оси, решатель решил цель на оси);
  DEADBAND_UNITS        зона сходимости повторного вывода у чисел, найденных итерацией, в единицах последнего знака;
  GATES, GATE_FACTS     начала адресов порогов гейтов — их команда сверяет с правилом листа, но не пишет — и поля окна
                        фактов, которые пишутся;
  MARGINAL              лист предельной экономики роста для блока приёмочных проверок;
  ACCEPTANCE            листы приёмочных проверок книги (сверка с фактами якоря, проверки до счёта оценки);
  REMINDERS             что после перевывода остаётся сделать руками (команда печатает списком).

Адрес — кортеж: строка — ключ словаря, число — номер в списке, словарь — отбор элемента списка по его полям
({"paths.0": "nii.phi_split"} — элемент, у которого paths[0] равен названному). Место числа в записи листа — такой же
кортеж либо функция от записи. Коридор — список (маска подключа, низ, верх, почему): первая подошедшая маска; у числа
(не траектории) подключ пуст; маска без низа и верха — «коридора нет» (число не выводится, а переносится).
"""
from __future__ import annotations

import derive_on_engine as sheet          # правила шагов и их константы — в листе: здесь они не повторяются

GATES = (("checks",),)                    # пороги и коридоры гейтов (ключи под `checks`): запись описания с таким адресом
#                                           команда СВЕРЯЕТ с правилом листа, но в шаблон не пишет — порог гейта, который
#                                           сам идёт за результатом, ничего не сторожит. Расхождение команда печатает
#                                           отдельным блоком, красным флагом и строкой листа решения; перенос — руками
GATE_FACTS = (("checks", "window_backtest"),)   # …кроме полей окна фактов: это факты окна, а не пороги по результату — пишутся
SHEET = "derive_on_engine.py"
RECORD = {"out": "out/derive_out.json", "print": "out/derive_out.txt", "start": "out/derive_start.json"}
STEPS = sheet.STEPS
LINKED = sheet.LINKED

# ------------------------------------------------------------------ как запускается лист
# Центр считается один раз: якорь, сверки, связанные шаги до сходимости, решатель на осях, коридоры гейтов. Концы осей,
# заданные результатом, и корни справочных вариантов стоят на его записанных числах — отдельной фазой после центра
# (лист получает --start с записью центра: его выведенные ключи становятся подменами).
PHASES = (
    {"name": "centre", "title": "центр: якорь, выпуск, «послабление», премии роста, связанные шаги до сходимости, коридоры гейтов",
     "steps": ("bridge", "anchor", "payout", "issue", "relief", "realized", "near_spreads", "loans", "near", "misc", "level", "splits", "funds", "t2",
               "deductions", "fees", "opex", "transmission", "corridors"), "after": None},
    {"name": "ends", "title": "концы осей и корни справочных вариантов на записанных числах центра",
     "steps": ("ends",), "after": "centre", "take": (("ends",),)},
)

DEADBAND_UNITS = 1.0                      # зона сходимости повторного вывода (поле записи `deadband`) — у чисел, найденных
#                                           итерацией (связанные шаги, поиск корня): порог сходимости листа (1e-4 в его
#                                           мере) оставляет у корней расходов и сдвига маржи дрожание до единицы последнего
#                                           знака. Поодиночке числа НЕ пропускаются: запись в шаблон точная, шаблон после неё
#                                           равен записи вывода во всех числах. Зона служит одному решению обо всём запуске:
#                                           книга уже несёт запись вывода, а повторный вывод отличается от неё только сдвигом
#                                           чисел центра в пределах зоны (и вызванным им сдвигом чисел после центра) — вывод
#                                           сошёлся, не пишется ничего (ops/tools/rederive.py, `settled`). Любое отличие сверх
#                                           этого — и пишется всё. У чисел без итерации (доли, окно фактов) зоны нет
ANCHOR_YEAR = "2026"

AXES = ("valuation", "uncertainty", "axes")
REVERSE = ("valuation", "reverse_dcf", "axes")
VARIANTS = ("valuation", "reference_variants")
PERIOD_KEYS = "2*"                        # ключи времени траектории: кварталы и годы
NOT_DERIVED = "число книги, не выводится"
PREMIUM_AXIS = {"paths.0": f"{sheet.PREMIUM_PATHS['retail']}.{next(iter(sheet.PREMIUM_SHAPE))}"}
GROWTH_AXIS = {"paths.0": f"{sheet.LOAN_PATHS['corporate']}.{sheet.FADE_YEARS[0]}"}     # ось-связка роста после лет окна


def _key(path: str) -> tuple:
    return ("keys", path)


_DENSITY = [("*", 0.0, 1.7, "плотность — RWA к остатку книги: выше 1,7 — вес риска больше наибольшего веса кредита с макронадбавкой; "
                            "ниже нуля — RWA книг листа капитала не вмещаются в RWA якоря: искать ошибку в остатках фактов")]
_NEAR = [("LT", 0.0, 0.0, "с года схода сдвига нет — правило шага"),
         ("LT_from", sheet.NEAR_LAST_YEAR + 1, sheet.NEAR_LAST_YEAR + 1, "год схода — год после последнего года сдвига"),
         (ANCHOR_YEAR + "*", -0.003, 0.003, "общий сдвиг маржи — остаток года якоря: дальше ±0,3 п.п. — больше ошибки бэктеста книг "
                                            "(0,25 п.п.): ближние ключи спредов не отвечают якорю — пересчитать их листом, а не подбирать сдвиг"),
         (PERIOD_KEYS, -0.006, 0.003, "год σ0: остаток года якоря (до ±0,3 п.п.) и встречная σ0 (вклад σ0 в маржу клетки, до 0,3 п.п.; решение "
                                      "№ 5, п. 3.5): дальше — σ0 решателя вне своей оси либо ближние ключи спредов не отвечают якорю")]
_LOANS = [("LT", 0.0, 0.0, "с года схода премии нет"),
          ("LT_from", sheet.PREMIUM_FADE_TO, sheet.PREMIUM_FADE_TO, "год схода премии — суждение листа"),
          (PERIOD_KEYS, -0.30, 0.10, "премия под темп окна (от −5 до +10 % в год) к росту сектора мира окна (0…33 % в год): дальше — "
                                     "надстройка миров даёт сектору рост вне записи семейства; искать ошибку в записи миров")]
_PREMIUM = [("LT", 0.0, 0.0, "после года формы премии нет"),
            ("LT_from", sheet.PREMIUM_FADE_TO, sheet.PREMIUM_FADE_TO, "год схода премии"),
            (sheet.NEAR_FACT_PERIOD, None, None, "ключ квартала с фактом остатков — " + NOT_DERIVED),
            (PERIOD_KEYS, -0.07, 0.0, "середина между фактами (−6,1 и −4,5 п.п. в год) и нуждой баланса: ниже фактов или выше нуля — "
                                      "нужда вышла за факты либо сменила знак: баланс клетки не сходится суждениями о росте")]
_DEDUCTION = [("LT_from", None, None, "год выхода на долгосрочное значение — последний год сетки: " + NOT_DERIVED),
              ("2026Q2", 0.0, 0.0, "квартал якоря: вычет сценария — ноль (якорь воспроизводит нормативы)"),
              ("*", -0.02, 0.06, "вычет сценария в п.п. RWA: растущая часть роста вычетов (до 2 п.п.) и регуляторный вычет сценария (до 0,6 п.п.) — "
                                 "от −2 до +6 п.п.: дальше — слагаемые пути заданы не в тех единицах")]
_RUB = [("LT_from", None, None, "год выхода на долгосрочное значение — последний год сетки: " + NOT_DERIVED),
        ("2026Q2", 0.0, 0.0, "квартал якоря: рублёвой части нет (якорь воспроизводит нормативы)"),
        ("*", -400.0, 400.0, "рублёвая часть пути вычета, млрд ₽: постоянная доля роста вычетов (до 2 п.п. × RWA якоря ≈ 500) минус высвобождение ОНА "
                             "(до 0,17 п.п. RWA якоря в год, ≈ 340 к 2036 году) — от −400 до +400: дальше — слагаемые заданы не в тех единицах")]
_FIXED_CHANGE = [("LT_from", None, None, "год выхода на долгосрочное значение — последний год сетки: " + NOT_DERIVED),
                 ("*", -600.0, 600.0, "приращение постоянной части прочих активов к якорю, млрд ₽: высвобождение ОНА (до −340 к 2036 году) и рост "
                                      "вычитаемых активов на балансе (развилка природы, до +250): дальше — не те единицы; сумма с постоянной частью ниже "
                                      "нуля — отказ схемы ядра (прил. A № 24)")]
_DED_ENDS = [("capital.reg_scenarios.*.deduction_pp.*", -0.02, 0.06, "как у пути вычета сценария в п.п."),
             ("capital.reg_scenarios.*.deduction_rub.*", -400.0, 400.0, "как у рублёвой части пути вычета"),
             (sheet.FIXED_CHANGE + ".*", -600.0, 600.0, "как у пути постоянной части прочих активов (связки ведут обе стороны — решение № 5, п. 3.1)")]
_DED_SCENARIOS = ("schedule", "mid", "strict", "relief")       # сценарии требования шаблона (ключ capital.reg_scenarios.ids)
STAY_AXIS = {"paths.0": sheet.ISSUE_FLOW_PATH}               # связка доли денег выпуска: приток квартала выпуска (решение № 4, п. 3.1)
VOLUME_AXIS = {"paths.0": sheet.VOLUME_AXIS_PATH}             # связка объёма выпуска по известной цене: делитель и приток
MISC_AXIS = {"paths.0": f"{sheet.MISC_PATH}.{sheet.MISC_YEAR}"}   # ось-связка ближнего ключа прочих доходов (ведёт и прямую 2028–2029)
MISC_LT_AXIS = {"paths.0": sheet.MISC_LT_PATH}                    # ось-связка долгосрочного уровня прочих доходов (ведёт и прямую 2028–2029)
MISC_LINE = ("2028", "2029")                                      # годы прямой прочих доходов книги (LT_from 2030; лист — misc_years)
_MISC_LINE_CORRIDOR = (-200.0, 400.0, "прямая прочих доходов от пары к пути без переходных частей 2027 года к LT (решение № 7, п. 2.4): между "
                                      "началом прямой и долгосрочным уровнем — дальше −200…+400 млрд ₽ в год пара или LT ушли из своих коридоров")
TRANSMISSION_AXIS = {"paths.0": sheet.TRANSMISSION_PATH}       # ось реализованной передачи (решение № 5, п. 3.4)
SHARE_AXIS = {"paths.0": sheet.SHARE_PATHS[0]}                # связка доли вычета якоря, постоянной в рублях (обе стороны суждения)
DED_AXIS = {"paths.0": sheet.DED_ROOT.format(s=_DED_SCENARIOS[0], n=sheet.DED_NORMS[0]) + "." + sheet.DED_GROWTH_QUARTERS[0]}
_CARRIED = {"pp": (sheet.DED_ROOT, 1e-6, _DEDUCTION), "rub": (sheet.RUB_ROOT, 0.01, _RUB)}     # траектории вариантов: корень, единица, коридор
_T2 = [("*", 300.0, 1100.0, "плоско на уровне якоря (339,1), далее доля RWA: ниже 300 или выше трёх уровней якоря — RWA модальной "
                            "клетки падает либо растёт быстрее 15 % в год восемь лет")]
_FEES = [("LT_from", None, None, "год выхода на долгосрочное значение — " + NOT_DERIVED),
         (ANCHOR_YEAR, None, None, "год якоря закрыт fees.growth_override: ключ не читается — " + NOT_DERIVED),
         ("*", -0.05, 0.05, "спред комиссий к формуле связи: дальше ±5 п.п. в год — уровень комиссий к активам уходит от уровня года "
                            "якоря больше чем на пятую часть за четыре года; искать ошибку в базе объёма")]
_ROOTS = [(ANCHOR_YEAR + "Q*", -0.10, 0.10, "корень квартала года якоря: дальше ±10 п.п. — факт месяцев расходится с формулой связи больше, "
                                           "чем сезонность; искать ошибку в фактах квартала"),
          ("LT", -0.01, 0.01, "после лет цели уровень расходов к активам держится: корень дальше ±1 п.п. в год — связь расходов с "
                              "объёмом и рост активов расходятся навсегда"),
          ("LT_from", None, None, "год выхода на долгосрочное значение — " + NOT_DERIVED),
          (PERIOD_KEYS, -0.03, 0.03, "корень группы лет: дальше ±3 п.п. в год — расходы года якоря стоят дальше 12 % от уровня устава "
                                     "либо активы клеток раздуты: искать причину в балансе, а не подбирать")]
_PAYOUT = [(ANCHOR_YEAR, 0.25, 0.27, "25 % всей прибыли ÷ (1 − доля меньшинства 0…7 %)"),
           ("LT", 0.50, 0.54, "50 % всей прибыли ÷ (1 − доля меньшинства 0…7 %)"),
           ("LT_from", None, None, "год цели — " + NOT_DERIVED)]
_SHIFT_DOWN = [("", -0.06, 0.0, "нижний конец оси уровня ниже центра — сдвиг корней не положителен; иначе центр вышел из своей оси")]
_SHIFT_UP = [("", 0.0, 0.06, "верхний конец оси уровня выше центра — сдвиг корней не отрицателен; иначе центр вышел из своей оси")]
_Q4_ROOT = [("", -0.15, 0.20, "корень 4-го квартала года якоря: сезонное отношение 1,14–1,50 даёт −15…+20 п.п. к формуле связи")]
_STOP = [("LT", None, None, NOT_DERIVED), ("LT_from", None, None, NOT_DERIVED), (ANCHOR_YEAR, None, None, "премия книги — " + NOT_DERIVED),
         (str(int(sheet.STOP_YEARS[-1]) + 1), None, None, "путь книги года после остановки — " + NOT_DERIVED),
         ("*", -0.30, 0.10, "премия под темп варианта (от −5 до +10 % в год) — темп к росту сектора: рост сектора 0…33 % в год")]

WRITES = (
    # ---- anchor: вычеты и плотности — якорь воспроизводит RWA и оба норматива
    {"step": "anchor", "address": ("capital", "rwa", "density"), "source": _key("capital.rwa.density"), "unit": 1e-5, "mark": True,
     "rule": "RWA книг листа капитала к остаткам фактов; прочие активы — вес на часть, несущую риск; остаток округления — в корпоративную книгу; "
             "вес приращения постоянной части прочих активов — суждение листа (вычитаемый ОНА: 0, решение № 4, п. 3.2)",
     "corridor": _DENSITY},
    {"step": "anchor", "address": ("capital", "n20", "deductions_anchor"), "source": _key("capital.n20.deductions_anchor"), "unit": 0.001,
     "mark": True, "rule": "вычеты якоря — формулой на фактах: якорь воспроизводит капитал группы и Н20.0",
     "corridor": [("", 400.0, 800.0, "±200 млрд ₽ от формулы на фактах якоря (603,5): дальше — другой состав капитала группы или не тот узел фактов")]},
    {"step": "anchor", "address": ("capital", "n11", "gap_pp"), "source": _key("capital.n11.gap_pp"), "unit": 1e-6, "mark": True,
     "rule": "разность факта Н20.1 и норматива по счёту ядра на якоре",
     "corridor": [("", -0.002, 0.002, "разность больше 0,2 п.п. — базовый капитал якоря собран не из тех узлов фактов")]},
    {"step": "anchor", "address": ("volumes", "other_assets_to_loans"), "source": _key("volumes.other_assets_to_loans"), "unit": 1e-6, "mark": True,
     "rule": "растущая часть прочих активов якоря к кредитным книгам: (прочие активы − постоянная в рублях часть) / Σ кредитных книг",
     "corridor": [("", 0.05, 0.60, "растущие прочие активы — деньги и резервы, активы НПФ, НМА, основные средства: от двадцатой части до трёх пятых "
                                   "кредитных книг; дальше — не тот узел фактов постоянной части")]},
    {"step": "anchor", "address": ("volumes", "other_assets_fixed"), "source": _key("volumes.other_assets_fixed"), "unit": 0.1, "mark": True,
     "rule": "постоянные в рублях прочие активы — узел фактов (ОНА, гудвил, ассоциированные): числом книги — его ведёт ось доли вычета якоря",
     "corridor": [("", 400.0, 2100.0, "от одних ассоциированных (401) до всей суммы «ОНА + гудвил + НМА» с ними (2 061): дальше — не тот узел фактов")]},
    *({"step": "anchor", "address": tuple(path.split(".")), "source": _key(path), "unit": 1e-4, "mark": True,
       "rule": "доля вычета якоря, постоянная в рублях: узел фактов — доля ОНА и гудвила в сумме «ОНА + гудвил + НМА» по балансу МСФО на якоре",
       "corridor": [("", 0.4, 0.8, "доля внутри своей оси 0,4…0,8 (свидетельства 0,61–0,68): дальше — не тот узел фактов или сменился состав вычитаемых активов")]}
      for path in sheet.SHARE_PATHS),
    *({"step": "deductions", "address": AXES + (SHARE_AXIS, end),
       "source": (lambda record, end=end: {**record["anchor"]["share_axis"][end], **record["deductions"]["share_axis"][end]}), "unit": 1e-6,
       "deadband": DEADBAND_UNITS,
       "rule": f"ось доли вычета якоря, конец {end}: обе доли и сторона баланса (постоянные прочие активы, отношение растущих к кредитам, плотности) "
               "той же раскладкой прочих активов; ключи вычета сценариев (рубли и п.п.) — доля слагаемого роста вычетов та же (решение № 4, п. 3.3)",
       "corridor": [("capital.n*.deductions_fixed_share", 0.0, 1.0, "доля — от нуля до единицы (схема ядра)"),
                    *_DED_ENDS,
                    ("volumes.other_assets_fixed", 400.0, 2100.0, "постоянные прочие активы: от одних ассоциированных (401) до всей суммы «ОНА + гудвил + НМА» с ними (2 061)"),
                    ("volumes.other_assets_to_loans", 0.05, 0.60, "как у отношения растущих прочих активов к кредитам книги"),
                    ("capital.rwa.density.*", 0.0, 1.7, "как у плотностей книги")]}
      for end in ("low", "high")),
    # ---- payout: доля слота ядра
    {"step": "payout", "address": ("dividends", "policy", "payout"), "source": _key("dividends.policy.payout"), "unit": 1e-4, "mark": True,
     "rule": "доля политики от всей прибыли группы ÷ (1 − доля меньшинства): слот ядра — прибыль акционеров", "corridor": _PAYOUT},
    # ---- issue: выпуск по известной цене одним местом (решение № 4, п. 3.1)
    {"step": "issue", "address": tuple(sheet.ISSUE_FLOW.split(".")), "source": _key(sheet.ISSUE_FLOW), "unit": 0.01, "mark": True,
     "rule": "приток квартала выпуска = доля денег × объём + распределения квартала + возврат лишнего купона; прочие кварталы — числа книги",
     "corridor": [(sheet.ISSUE_FROM, -50.0, 700.0, "приток квартала выпуска: от распределений без выпуска до всего зарегистрированного выпуска "
                                                   "547,5 млрд ₽ с купоном — дальше не тот объём или не та доля денег"),
                  ("*", None, None, "распределения по указанию акционера — " + NOT_DERIVED)]},
    *({"step": "issue", "address": AXES + (VOLUME_AXIS, end), "source": ("issue", "volume_axis", end), "unit": 0.01,
       "rule": f"ось объёма выпуска по известной цене, конец {end}: делитель — число оси книги, приток — доля денег × объём той же формой, что центр",
       "corridor": [("valuation.*", 0.0, 1.0, "поправка делителя — число оси книги"),
                    ("equity.*", -50.0, 700.0, "приток квартала выпуска — как у центра")]}
      for end in ("low", "high")),
    *({"step": "issue", "address": AXES + (STAY_AXIS, end), "source": ("issue", "stay_axis", end), "unit": 0.01,
       "rule": f"ось доли денег выпуска, конец {end}: " + ("ни один рубль стоимости не создаёт (акции выпущены, деньги в оценку не входят)"
                                                          if end == "low" else "все деньги в банке и в капитале норматива"),
       "corridor": [("*", -50.0, 700.0, "приток квартала выпуска — как у центра")]}
      for end in ("low", "high")),
    *({"step": "issue", "address": VARIANTS + ({"id": vid}, "overrides", sheet.ISSUE_FLOW, sheet.ISSUE_FROM), "source": ("issue", "variants", vid, "inflow"),
       "unit": 0.01, "rule": f"справочный вариант {vid}: приток квартала выпуска той же формой (доля денег, объём, распределения и купон варианта)",
       "corridor": [("", -50.0, 700.0, "приток квартала выпуска — как у центра")]}
      for vid in sheet.FLOW_VARIANTS),
    # ---- relief: требование сценария «послабление» после возврата надбавок (решение № 4, п. 3.4)
    *({"step": "relief", "address": ("capital", "reg_scenarios", sheet.RELIEF_ID, w), "source": _key(f"capital.reg_scenarios.{sheet.RELIEF_ID}.{w}"),
       "unit": 1e-6, "mark": True,
       "rule": f"надбавка {w} сценария «послабление»: с {sheet.RELIEF_FROM} года — доля возврата × смесь трёх сценариев с вероятностями строки без кризиса",
       "corridor": [("LT_from", None, None, "год выхода на уровень — форма прецедента: " + NOT_DERIVED),
                    ("*", 0.0, 0.03, "надбавка — от нуля до 3 % RWA: дальше — смесь сценариев собрана не из тех ключей")]}
      for w in sheet.RELIEF_RETURN),
    *({"step": "relief", "address": VARIANTS + ({"id": sheet.RELIEF_VARIANT}, "overrides", f"capital.reg_scenarios.{sheet.RELIEF_ID}.{w}"),
       "source": ("relief", "variant", f"capital.reg_scenarios.{sheet.RELIEF_ID}.{w}"), "unit": 1e-6,
       "rule": f"справочный вариант {sheet.RELIEF_VARIANT}: надбавка {w} — та же доля возврата к сценарию «по графику» (прежняя форма)",
       "corridor": [("LT_from", None, None, NOT_DERIVED), ("*", 0.0, 0.03, "как у надбавки центра")]}
      for w in sheet.RELIEF_RETURN),
    # ---- realized: реализованная передача ключевой в маржу (решение № 5, п. 3.4)
    {"step": "realized", "address": tuple(sheet.TRANSMISSION_PATH.split(".")), "source": _key(sheet.TRANSMISSION_PATH), "unit": 1e-6, "mark": True,
     "rule": "реализованная передача — произведение середин двух суждений без округления: измеренная × (1 − доля книги без процентного дохода)",
     "corridor": [("", sheet.TRANSMISSION_AXIS[0], sheet.TRANSMISSION_AXIS[1], "центр внутри носителя произведения (−0,068…+0,022): дальше — "
                                                                             "сомножители записаны не теми числами")]},
    *({"step": "realized", "address": AXES + (TRANSMISSION_AXIS, end), "source": ("realized", "axis", end), "unit": 1e-5,
       "rule": f"ось реализованной передачи, конец {end}: {'P10' if end == 'low' else 'P90'} оси, как её разыгрывает движок (медиана у центра книги), "
               f"равен {'P10' if end == 'low' else 'P90'} произведения двух независимых треугольников (правило подбора — в шапке листа)",
       "corridor": [("", sheet.TRANSMISSION_AXIS[0], 0.0, "нижний конец — между краем носителя и нулём")] if end == "low"
       else [("", -0.02, sheet.TRANSMISSION_AXIS[1], "верхний конец — выше центра и не выше края носителя")]}
      for end in ("low", "high")),
    # ---- near: общий ближний сдвиг маржи по MODEL §3.2 (решение № 5, п. 3.5)
    {"step": "near", "address": ("regimes", "near_nim_shift"), "source": _key("regimes.near_nim_shift"), "unit": 1e-5, "deadband": DEADBAND_UNITS,
     "mark": True, "rule": "остаток года якоря: в квартале с месячными фактами клетка печатает маржу фактов; в 1-м квартале года σ0 — сдвиг и встречная "
                           "σ0 (ступень σ0 снята), линейный сход к году схода (MODEL §3.2)",
     "corridor": _NEAR},
    *({"step": "ends", "address": VARIANTS + ({"id": vid}, "overrides", "regimes.near_nim_shift"),
       "source": ("ends", "near_variants", "variants", vid, "trajectory"), "unit": 1e-5, "deadband": DEADBAND_UNITS,
       "rule": f"справочный вариант {vid}: ближний путь маржи прежней формы (d центра × 1 / 0,8 / 0,6 / 0,4 / 0,2, без встречной σ0)",
       "corridor": _NEAR}
      for vid, form in sheet.NEAR_VARIANTS.items() if form == "old_form"),
    *({"step": "ends", "address": VARIANTS + ({"id": vid}, "overrides", f"{sheet.MISC_PATH}.{sheet.MISC_YEAR}"),
       "source": ("ends", "near_variants", "variants", vid, "misc_key"), "unit": 0.1, "deadband": DEADBAND_UNITS,
       "rule": f"справочный вариант ближнего пути маржи {vid}: ключ прочих доходов {sheet.MISC_YEAR} года — пара к пути варианта (середина окна C в клетке "
               "условий окна, решение № 5, п. 3.5)",
       "corridor": [("", -200.0, 400.0, "как у ключа центра")]}
      for vid in sheet.NEAR_VARIANTS),
    *({"step": "ends", "address": VARIANTS + ({"id": vid}, "overrides", f"{sheet.MISC_PATH}.{y}"),
       "source": ("ends", "near_variants", "variants", vid, "misc_line", y), "unit": 0.1, "deadband": DEADBAND_UNITS,
       "rule": f"справочный вариант ближнего пути маржи {vid}: прочие доходы {y} года — прямая к LT от пары к пути варианта без всех его переходных "
               f"частей {sheet.MISC_YEAR} года (решение № 7, п. 2.4: ключ варианта минус его разность пар)",
       "corridor": [("", *_MISC_LINE_CORRIDOR)]}
      for vid in sheet.NEAR_VARIANTS for y in MISC_LINE),
    *({"step": "misc", "address": VARIANTS + ({"id": sheet.MISC_INHERITED}, "overrides", f"{sheet.MISC_PATH}.{y}"),
       "source": ("misc", "inherited", "overrides", f"{sheet.MISC_PATH}.{y}"), "unit": 0.1, "deadband": DEADBAND_UNITS,
       "rule": f"справочный вариант {sheet.MISC_INHERITED} (форма книги 0.6: пары к переходным частям наследуются): прочие доходы {y} года — прямая "
               "к LT от ключа центра минус одна пара к встречной σ0",
       "corridor": [("", *_MISC_LINE_CORRIDOR)]}
      for y in MISC_LINE),
    # ---- misc: ближний ключ прочих доходов — середина окна C в сумме «ЧПД + прочие» клетки условий окна (решение № 4, п. 3.6);
    #      2028–2029 — прямая к LT от пары к пути без всех переходных частей 2027 года (решение № 7, п. 2.4)
    {"step": "misc", "address": tuple(sheet.MISC_PATH.split(".")), "source": _key(sheet.MISC_PATH), "unit": 0.1, "deadband": DEADBAND_UNITS,
     "mark": True, "rule": f"ключ {sheet.MISC_YEAR} года: сумма «ЧПД + прочие» клетки условий окна в знаменателе окна разбора = середина окна C; "
                           f"{', '.join(MISC_LINE)} — прямая к LT от ключа минус разность пар (сумма пар к переходным частям пути ЧПД "
                           f"{sheet.MISC_YEAR} года: встречная σ0, сдвиг d, половина остатка якоря книг, остаток книги бумаг, сход опта); прочие "
                           "ключи — суждения книги",
     "corridor": [(sheet.MISC_YEAR, -200.0, 400.0, "ближний ключ прочих доходов: дальше −200…+400 млрд ₽ в год — маржа клетки условий окна ушла от "
                                                  "маржи окна больше чем на 0,6 п.п.; искать ошибку в пути маржи, а не подбирать"),
                  *((y, *_MISC_LINE_CORRIDOR) for y in MISC_LINE),
                  ("*", None, None, "уровень 2026 года (факт восьми месяцев) и долгосрочный уровень — суждения книги: " + NOT_DERIVED)]},
    *({"step": "misc", "address": AXES + (MISC_AXIS, end), "source": ("misc", "axis_bundle", end), "unit": 0.1, "deadband": DEADBAND_UNITS,
       "rule": f"ось-связка ближнего ключа прочих доходов, конец {end}: сумма клетки условий окна = " + ("окно C без разового результата 1К"
                                                                                                        if end == "low" else "окно C с разовым результатом 1К")
               + f"; ключи {', '.join(MISC_LINE)} — та же доля приращения, что у прямой (разность пар вдоль оси постоянна, решения № 6, п. 2.2 "
                 "и № 7, п. 2.4)",
       "corridor": [(f"{sheet.MISC_PATH}.{sheet.MISC_YEAR}", -400.0, 600.0, "конец оси — пара к марже: дальше ±0,9 п.п. суммы от окна"),
                    (f"{sheet.MISC_PATH}.20*", -400.0, 600.0, "ключ прямой на конце оси: доля приращения ключа")]}
      for end in ("low", "high")),
    *({"step": "misc", "address": AXES + (MISC_LT_AXIS, end), "source": ("misc", "lt_axis", end), "unit": 0.1, "deadband": DEADBAND_UNITS,
       "rule": f"ось-связка долгосрочного уровня прочих доходов, конец {end}: LT — суждение книги; ключи {', '.join(MISC_LINE)} — доля приращения LT "
               "у прямой (решение № 6, п. 2.2)",
       "corridor": [(sheet.MISC_LT_PATH, None, None, "долгосрочный уровень — суждение книги (решение № 2, п. 1.1): " + NOT_DERIVED),
                    (f"{sheet.MISC_PATH}.20*", -400.0, 600.0, "ключ прямой на конце оси LT: доля приращения LT")]}
      for end in ("low", "high")),
    *({"step": "misc", "address": VARIANTS + ({"id": vid}, "overrides", sheet.MISC_PATH, sheet.MISC_YEAR), "source": ("keys", sheet.MISC_PATH, sheet.MISC_YEAR),
       "unit": 0.1, "deadband": DEADBAND_UNITS, "rule": f"справочный вариант {vid}: ближний ключ прочих доходов — тот же, что у центра",
       "corridor": [("", -200.0, 400.0, "как у ключа центра")]}
      for vid in sheet.MISC_VARIANTS),
    *({"step": "misc", "address": VARIANTS + ({"id": vid}, "overrides", sheet.MISC_PATH, y), "source": ("misc", "variants", vid, y),
       "unit": 0.1, "deadband": DEADBAND_UNITS,
       "rule": f"справочный вариант {vid}: прочие доходы {y} года — прямая от того же начала, что у центра, к своему LT (решение № 7, п. 2.4)",
       "corridor": [("", -200.0, 500.0, "между началом прямой центра и LT варианта (до 400)")]}
      for vid in sheet.MISC_VARIANTS for y in MISC_LINE),
    # ---- loans: премии роста кредитов — уровень окна в мире окна
    *({"step": "loans", "address": tuple(path.split(".")), "source": _key(path), "unit": 1e-4, "mark": True,
       "rule": f"премия роста кредитов ({sector}): в годы окна книга мира окна растёт темпом окна; далее линейный сход к году схода",
       "corridor": _LOANS}
      for sector, path in sheet.LOAN_PATHS.items()),
    # ---- funds: премия роста средств клиентов и её ось
    *({"step": "funds", "address": tuple(path.split(".")), "source": _key(path), "unit": 1e-4, "deadband": DEADBAND_UNITS, "mark": True,
       "rule": f"середина между фактом сегмента ({seg}) и нуждой баланса; после лет окна — линейный сход к году схода", "corridor": _PREMIUM}
      for seg, path in sheet.PREMIUM_PATHS.items()),
    *({"step": "funds", "address": AXES + (GROWTH_AXIS, end), "source": ("funds", "growth_axis", end), "unit": 1e-4, "deadband": DEADBAND_UNITS,
       "rule": "ось роста после лет окна, конец " + ("low: премии последнего года окна и уровень премии средств клиентов держатся до года схода"
                                                    if end == "low" else "high: премии — ноль сразу после лет окна"),
       "corridor": [("*", -0.30, 0.10, "конец оси роста — премия последнего года окна либо ноль: коридор премий кредитов и средств клиентов")]}
      for end in ("low", "high")),
    *({"step": "funds", "address": AXES + (PREMIUM_AXIS, end), "source": ("funds", "axis", end), "unit": 1e-4, "deadband": DEADBAND_UNITS,
       "rule": f"ось премии средств клиентов, конец {end}: " + ("факты сегментов" if end == "low" else "нужда баланса"),
       "corridor": [("*", -0.08, 0.02, "конец оси премии — факт сегмента либо нужда баланса: дальше −8…+2 п.п. в год баланс клетки не сходится")]}
      for end in ("low", "high")),
    *({"step": "funds", "address": VARIANTS + ({"id": "funds_premium_need"}, "overrides", f"{path}.{k}"),
       "source": ("funds", "axis_full", "high", f"{path}.{k}"), "unit": 1e-4, "deadband": DEADBAND_UNITS,
       "rule": "справочный вариант: премия средств клиентов на уровне нужды баланса",
       "corridor": [("", -0.08, 0.02, "как у оси премии")]}
      for path in sheet.PREMIUM_PATHS.values() for k in sheet.PREMIUM_SHAPE),
    # ---- t2: дополнительный капитал
    {"step": "t2", "address": ("capital", "n20", "t2"), "source": _key("capital.n20.t2"), "unit": 0.1, "deadband": DEADBAND_UNITS, "mark": True,
     "rule": "плоско в рублях по квартал ступени, далее — доля RWA модальной клетки этого квартала (с ключом capital.n20.t2_share ядро "
             "траекторию с квартала ключа не читает — каждая клетка держит долю своих RWA; траектория — рубли модальной клетки, вариант t2_modal_rub)",
     "corridor": _T2},
    # ---- deductions: путь вычета сценария по природе слагаемых на ключах пятого прохода ядра (рубли — deduction_rub, п.п. — deduction_pp);
    #      путь постоянной части прочих активов теми же рублями высвобождения ОНА; ось роста вычетов; справочные варианты на тех же ключах
    *({"step": "deductions", "address": ("capital", "reg_scenarios", s, "deduction_pp", n), "source": _key(sheet.DED_ROOT.format(s=s, n=n)),
       "unit": 1e-6, "mark": True,
       "rule": f"путь вычета сценария {s} ({n}) в п.п. RWA: растущая часть роста вычетов (1 − η) и регуляторный вычет сценария", "corridor": _DEDUCTION}
      for s in _DED_SCENARIOS for n in sheet.DED_NORMS),
    *({"step": "deductions", "address": ("capital", "reg_scenarios", s, "deduction_rub", n), "source": _key(sheet.RUB_ROOT.format(s=s, n=n)),
       "unit": 0.01, "mark": True,
       "rule": f"вычет сценария {s} ({n}) в рублях: постоянная доля η роста вычетов × RWA якоря и высвобождение ОНА", "corridor": _RUB}
      for s in _DED_SCENARIOS for n in sheet.DED_NORMS),
    {"step": "deductions", "address": ("volumes", "other_assets_fixed_change"), "source": _key(sheet.FIXED_CHANGE), "unit": 0.01, "mark": True,
     "rule": "путь постоянной части прочих активов: высвобождение ОНА теми же рублями, что в рублёвой части пути вычета (решение № 4, п. 3.2)",
     "corridor": _FIXED_CHANGE},
    *({"step": "deductions", "address": AXES + (DED_AXIS, end), "source": ("deductions", "axis", end), "unit": 1e-6,
       "rule": f"ось роста вычетов, конец {end}: темп {rate * 400:g} п.п. в год той же формой (рубли и п.п.)", "corridor": _DED_ENDS}
      for end, rate in zip(("low", "high"), sheet.DED_GROWTH_AXIS)),
    *({"step": "deductions", "address": VARIANTS + ({"id": vid}, "overrides", root.format(s=s, n=n)),
       "source": ("deductions", "variants", vid, root.format(s=s, n=n)), "unit": unit,
       "rule": f"справочный вариант {vid}: {'рубли' if kind == 'rub' else 'п.п.'} пути вычета сценария {s} ({n}) той же формой", "corridor": corridor}
      for vid, cfg in sheet.DEDUCTION_VARIANTS.items() for kind, (root, unit, corridor) in _CARRIED.items() if kind in cfg["carries"]
      for s in _DED_SCENARIOS for n in sheet.DED_NORMS),
    *({"step": "deductions", "address": VARIANTS + ({"id": vid}, "overrides", sheet.FIXED_CHANGE),
       "source": ("deductions", "variants", vid, sheet.FIXED_CHANGE), "unit": 0.01,
       "rule": f"справочный вариант {vid}: путь постоянной части прочих активов той же формой (обе стороны суждения)", "corridor": _FIXED_CHANGE}
      for vid, cfg in sheet.DEDUCTION_VARIANTS.items() if "change" in cfg["carries"]),
    # ---- fees и opex: корни под уровни устава
    {"step": "fees", "address": ("fees", "growth_vs_wages"), "source": _key("fees.growth_vs_wages"), "unit": 1e-4, "deadband": DEADBAND_UNITS,
     "mark": True, "rule": "комиссии к средним активам слоя «рыночные ставки как есть»: уровень устава в году цели и в среднем после него",
     "corridor": _FEES},
    {"step": "opex", "address": ("opex", "real_growth"), "source": _key("opex.real_growth"), "unit": 1e-4, "deadband": DEADBAND_UNITS, "mark": True,
     "rule": "кварталы года якоря — уровни по фактам; годы цели и долгосрочный участок — расходы к средним активам слоя на уровне устава",
     "corridor": _ROOTS},
    # ---- corridors: коридоры гейтов по счёту ядра — команда их СВЕРЯЕТ с книгой, но не пишет (GATES); цель расходов к
    #      доходам (checks.cir_lt.target) — суждение устава и листа pnl, листом не выводится
    {"step": "corridors", "address": ("checks", "wholesale_share"), "source": _key("checks.wholesale_share"), "unit": 0.01,
     "rule": "коридор гейта: меньшее из доли якоря и наименьшей доли по клеткам минус запас — большее плюс запас",
     "corridor": [("0", 0.0, 0.30, "низ коридора — у доли якоря"),
                  ("1", 0.10, 0.40, "оптовое фондирование выше 40 % фондирования — искать разрыв между ростом кредитов и средств клиентов")]},
    *({"step": "corridors", "address": ("checks", "pb_by_world", w), "source": ("keys", "checks.pb_by_world", w), "unit": 0.05,
       "rule": f"коридор P/B клеток мира {w}: размах клеток центральной книги, наружу до 0,05; низ не ниже 0,05",
       "corridor": [("0", 0.05, 1.5, "низ: клетку у нуля и ниже гейт называет, а не прячет"),
                    ("1", 0.2, 2.5, "клетка дороже 2,5 капитала при ROE ниже стоимости капитала — ошибка оценки")]}
      for w in ("N", "H", "M")),
    {"step": "corridors", "address": ("checks", "terminal_share"), "source": _key("checks.terminal_share"), "unit": 0.05,
     "rule": "коридор доли терминала: размах клеток центральной книги с P/B не ниже нижней границы гейта P/B, наружу до 0,05",
     "corridor": [("0", 0.0, 1.0, "низ: доля терминала ниже нуля у клетки не у нуля — терминал разрушает стоимость"),
                  ("1", 0.5, 5.0, "доля терминала выше 5 у клетки с P/B не ниже 0,05 — явный участок съедает больше четырёх пятых терминала")]},
    {"step": "corridors", "address": ("checks", "roe_k_spread", "range"), "source": ("keys", "checks.roe_k_spread", "range"), "unit": 0.01,
     "rule": "ROE терминала минус стоимость капитала: размах клеток центральной книги, наружу до 0,01",
     "corridor": [("0", -0.25, 0.05, "доходность терминала ниже стоимости капитала больше чем на 25 п.п. — клетка не банк"),
                  ("1", -0.05, 0.15, "доходность терминала выше стоимости капитала больше чем на 15 п.п. — не угасла")]},
    {"step": "corridors", "address": ("checks", "roe_k_spread", "max_world_gap"), "source": ("keys", "checks.roe_k_spread", "max_world_gap"),
     "unit": 0.01, "rule": "разрыв средних миров мерой гейта roe_k_homogeneity (вероятности аналитического слоя по клеткам, которые судит гейт; "
                           "решение № 6, п. 2.4), вверх до 0,01",
     "corridor": [("", 0.0, 0.15, "разрыв миров больше 15 п.п. — передача ставки в доходность терминала не согласована")]},
    {"step": "corridors", "address": ("checks", "window_backtest", "loans_share"), "source": _key("checks.window_backtest.loans_share"),
     "unit": 1e-4, "mark": True, "rule": "окно фактов: доля кредитов в процентных активах, среднее концов кварталов окна",
     "corridor": [("", 0.6, 0.9, "доля кредитных книг в процентных активах банка — 73–78 %: дальше — не тот состав книг")]},
    # ---- ends: концы осей, заданные результатом
    {"step": "ends", "address": AXES + ({"paths.0": "opex.real_growth.2027"}, "low"), "source": ("ends", "opex_axis", "low"), "unit": 1e-4,
     "deadband": DEADBAND_UNITS, "rule": "ось уровня расходов: сдвиг корней под нижний конец оси расходов к активам", "corridor": _SHIFT_DOWN},
    {"step": "ends", "address": AXES + ({"paths.0": "opex.real_growth.2027"}, "high"), "source": ("ends", "opex_axis", "high"), "unit": 1e-4,
     "deadband": DEADBAND_UNITS, "rule": "ось уровня расходов: сдвиг корней под верхний конец оси расходов к активам", "corridor": _SHIFT_UP},
    *({"step": "ends", "address": AXES + ({"paths.0": "opex.real_growth.2026Q4"}, end), "source": ("ends", "opex_q4", end), "unit": 1e-4,
       "deadband": DEADBAND_UNITS, "rule": f"ось сезонного отношения расходов 4-го квартала, конец {end}: корень квартала", "corridor": _Q4_ROOT}
      for end in ("low", "high")),
    {"step": "ends", "address": AXES + ({"paths.0": "fees.growth_vs_wages.2027"}, "low"), "source": ("ends", "fees_axis", "low"), "unit": 1e-4,
     "deadband": DEADBAND_UNITS, "rule": "ось уровня комиссий: сдвиг корней под нижний конец оси", "corridor": _SHIFT_DOWN},
    {"step": "ends", "address": AXES + ({"paths.0": "fees.growth_vs_wages.2027"}, "high"), "source": ("ends", "fees_axis", "high"), "unit": 1e-4,
     "deadband": DEADBAND_UNITS, "rule": "ось уровня комиссий: сдвиг корней под верхний конец оси", "corridor": _SHIFT_UP},
    # ---- ends: корни справочных вариантов
    {"step": "ends", "address": VARIANTS + ({"id": "opex_q4_whole_series"}, "overrides", "opex.real_growth.2026Q4"),
     "source": ("ends", "opex_q4", "whole_series"), "unit": 1e-4, "deadband": DEADBAND_UNITS,
     "rule": "справочный вариант: корень 4-го квартала под сезонное отношение всего ряда", "corridor": _Q4_ROOT},
    *({"step": "ends", "address": VARIANTS + ({"id": "fees_level_2026"}, "overrides", f"fees.growth_vs_wages.{k}"),
       "source": ("ends", "fees_level_anchor_year", "overrides", f"fees.growth_vs_wages.{k}"), "unit": 1e-4, "deadband": DEADBAND_UNITS,
       "rule": "справочный вариант: корни спреда комиссий под уровень года якоря",
       "corridor": [("", -0.05, 0.05, "как у спреда комиссий книги")]}
      for k in sheet.FEES_KEYS + ("LT",)),
    *({"step": "ends", "address": VARIANTS + ({"id": "fees_opex_level_2026"}, "overrides", key),
       "source": ("ends", "fees_opex_level_anchor_year", "overrides", key), "unit": 1e-4, "deadband": DEADBAND_UNITS,
       "rule": "справочный вариант (пара): корни комиссий и расходов под их уровни года якоря к средним активам слоя (решение № 4, п. 3.9)",
       "corridor": [("", -0.05, 0.05, "как у корней спреда комиссий и групп лет расходов")]}
      for key in tuple(f"fees.growth_vs_wages.{k}" for k in sheet.FEES_KEYS + ("LT",))
      + tuple(f"opex.real_growth.{y}" for y in sheet.OPEX_GROUPS[0] + sheet.OPEX_GROUPS[1] + ("LT",))),
    *({"step": "ends", "address": VARIANTS + ({"id": f"{line}_link_{tag}"}, "overrides", key),
       "source": ("ends", "links", f"{line}_{tag}", "overrides", key), "unit": 1e-4, "deadband": DEADBAND_UNITS,
       "rule": f"справочный вариант связи с объёмом {sheet.LINK_ENDS[tag]} ({line}): корень под тот же уровень устава",
       "corridor": [("", -0.30, 0.40, "корень варианта связи: при связи 0,2 или 1,0 уровень держит корень в пределах сезонного корня квартала "
                                      "(−0,25…+0,35) — дальше поиск корня упёрся в край")]}
      for tag in sheet.LINK_ENDS
      for line, keys in (("fees", tuple(f"fees.growth_vs_wages.{k}" for k in sheet.FEES_KEYS + ("LT",))),
                         ("opex", tuple(f"opex.real_growth.{k}" for k in (sheet.NEAR_FACT_PERIOD[:4] + "Q3", sheet.NEAR_FACT_PERIOD[:4] + "Q4")
                                        + sheet.OPEX_GROUPS[0] + sheet.OPEX_GROUPS[1] + ("LT",))))
      for key in keys),
    *({"step": "ends", "address": VARIANTS + ({"id": vid}, "overrides", f"volumes.loan_share_drift.{sector}"),
       "source": ("ends", "growth", vid, "loans", f"volumes.loan_share_drift.{sector}"), "unit": 1e-4,
       "rule": f"справочный вариант роста {vid}: премия роста кредитов ({sector}) — темп варианта к росту сектора мира модальной клетки",
       "corridor": _STOP}
      for vid in sheet.GROWTH_VARIANTS for sector in sheet.LOAN_SECTORS),
    *({"step": "ends", "address": VARIANTS + ({"id": vid}, "overrides", f"{path}.{y}"),
       "source": ("ends", "growth", vid, "funds", f"{path}.{y}"), "unit": 1e-4,
       "rule": f"справочный вариант роста {vid}: премия средств клиентов — темп варианта к росту сектора мира модальной клетки",
       "corridor": [("", -0.30, 0.05, "премия средств клиентов под темп варианта (0…+5 % в год) при росте сектора 0…33 % в год")]}
      for vid in sheet.GROWTH_VARIANTS for path in sheet.PREMIUM_PATHS.values() for y in sheet.STOP_YEARS),
)

# Суждения, которые лист держит своей константой (оси уровня маржи, передачи и долей раскладки — сами суждения): запись
# их не трогает, расхождение с книгой — остановка: суждение записано в двух местах по-разному.
SAME = (
    *({"step": "transmission", "address": AXES + ({"paths.0": sheet.NIM_KEY}, end), "source": ("transmission", "nim_axis", i),
       "rule": f"ось уровня маржи — суждение книги: конец {end}"} for i, end in enumerate(("low", "high"))),
    {"step": "transmission", "address": REVERSE + ({"paths.0": sheet.NIM_KEY}, "range"), "source": ("transmission", "nim_axis"),
     "rule": "диапазон строки обратного расчёта — ось уровня маржи"},
    {"step": "realized", "address": REVERSE + ({"paths.0": "nii.transmission.target"}, "range"), "source": ("realized", "support"),
     "rule": "диапазон строки обратного расчёта — носитель реализованной передачи (−0,068…+0,022: измеренная на краях при доле книги 0)"},
    *({"step": "splits", "address": AXES + ({"paths.0": "nii.phi_split"}, end), "source": ("splits", "axis_phi", i),
       "rule": f"ось доли сжатия — число листа: конец {end}"} for i, end in enumerate(("low", "high"))),
    *({"step": "splits", "address": AXES + ({"paths.0": "nii.sigma0_split"}, end), "source": ("splits", "axis_sigma0", i),
       "rule": f"ось доли сдвига — число листа: конец {end}"} for i, end in enumerate(("low", "high"))),
)

# Невязки правил на записанных (округлённых) числах. `flag` — узел обязан быть истиной; иначе |значение − цель| не
# больше допуска. Цель — число либо место в записи листа.
RESIDUALS = (
    {"step": "bridge", "name": "мост маржи упр. ↔ движок около нуля", "value": ("bridge", "nim"), "target": 0.0, "tol": 5e-4,
     "why": "книга ликвидности — только доходные размещения: знаменатель движка равен знаменателю банка; мост больше 0,05 п.п. — "
            "в книгу вернулись деньги без дохода либо банк сменил определение маржи"},
    {"step": "anchor", "name": "RWA якоря равны факту", "value": ("anchor", "rwa_model"), "target": ("anchor", "rwa_fact"), "tol": 0.05,
     "why": "плотности записаны пятью-шестью знаками: до 0,05 млрд ₽"},
    {"step": "anchor", "name": "Н20.0 якоря равен капиталу группы к RWA", "value": ("anchor", "n20_model"), "target": ("anchor", "n20_group"),
     "tol": 5e-6, "why": "вычеты якоря записаны до млн ₽"},
    {"step": "anchor", "name": "Н20.1 якоря равен факту", "value": ("anchor", "n11_model"), "target": ("anchor", "n11_fact"), "tol": 1e-6,
     "why": "разность записана шестью знаками"},
    {"step": "anchor", "name": "постоянные прочие активы книги равны узлу фактов", "value": ("anchor", "other_fixed"),
     "target": ("anchor", "other_fixed_facts"), "tol": 1e-6,
     "why": "одно суждение — один раз: постоянная в рублях часть прочих активов записана в фактах (ОНА, гудвил, ассоциированные), книга читает узел"},
    {"step": "anchor", "name": "доля вычета якоря книги равна доле постоянных активов по балансу фактов", "value": ("anchor", "fixed_share"),
     "target": ("anchor", "fixed_share_formula"), "tol": 5e-5,
     "why": "одно суждение — один раз: узел фактов записан четырьмя знаками по примечаниям МСФО; расхождение — узел и части баланса фактов из разных отчётов"},
    {"step": "loans", "name": "премии роста кредитов читаются ядром по последний год схода", "flag": ("loans", "read_until_ok"),
     "why": "ядро читает премии по год volumes.share_drift_until включительно: ключи схода позже него не действуют"},
    {"step": "near_spreads", "name": "ближние ключи спредов книг равны записи листа (бэктест книг)", "flag": ("near_spreads", "same"),
     "why": "ключи — числа листа: правка их руками в шаблоне без пересчёта листом рвёт путь маржи с бэктестом"},
    {"step": "level", "name": "стационарная маржа мира уровня равна ключу цели", "flag": ("level", "ok"),
     "why": "ключ цели маржи — суждение: решатель передачи обязан его воспроизвести"},
    {"step": "splits", "name": "полы спреда кредитных книг держатся в центре", "flag": ("splits", "floor_ok"),
     "why": "доли раскладки — середины диапазонов листа: в центре спред кредитной книги к ключевой не ниже наблюдённого пола"},
    {"step": "splits", "name": "стоимость средств клиентов к ключевой не выше потолка", "flag": ("splits", "funds_cost_ok"),
     "why": "нижняя граница доли сжатия — наибольшая наблюдённая стоимость средств клиентов к ключевой"},
    {"step": "opex", "name": "сходимость связанных шагов", "flag": ("convergence", "converged"),
     "why": "порог и число кругов — листа; не сошлось — числа не пишутся"},
    {"step": "near", "name": f"маржа {sheet.NEAR_FACT_PERIOD} — маржа месячных фактов", "value": ("frozen_check", "near_nim"),
     "target": ("frozen_check", "near_nim_fact"), "tol": 2e-5, "why": "сдвиг записан пятью знаками: 0,002 п.п. маржи"},
    {"step": "near", "name": f"ЧПД {sheet.NEAR_FACT_PERIOD} к ЧПД месячных фактов", "value": ("frozen_check", "near_nii_ratio"), "target": 1.0,
     "tol": 0.03, "why": "маржа клетки стоит на фактах; ЧПД расходится с фактом на знаменатель: больше 3 % — процентные активы клетки "
                         "в первом квартале ушли от факта (скачок балансирующих книг)"},
    {"step": "funds", "name": "нужда баланса: кредиты к средствам клиентов как на якоре", "value": ("frozen_check", "funds_need_ratio"),
     "target": ("frozen_check", "funds_anchor_ratio"), "tol": 3e-4, "why": "уровень нужды записан четырьмя знаками"},
    {"step": "t2", "name": "доля дополнительного капитала в RWA клетки после года ступени", "value": ("frozen_check", "t2_share_error"),
     "target": 0.0, "tol": 5e-5, "why": "траектория записана до 0,1 млрд ₽: отклонение доли — до 0,005 п.п."},
    {"step": "misc", "name": f"сумма «ЧПД + прочие» {sheet.MISC_YEAR} года клетки условий окна на записанном ключе — середина окна C",
     "value": ("misc", "sum_at_key"), "target": ("misc", "window", "mid"), "tol": 5e-6,
     "why": "ключ записан до 0,1 млрд ₽: сумма — до 0,0005 п.п.; больше — ключ не решает правило"},
    {"step": "misc", "name": "прочие 2028–2029 годов на записанных ключах — прямая к LT от ключа 2027 года минус разность пар (решение № 7, п. 2.4)",
     "value": ("frozen_check", "misc_line_error"), "target": 0.0, "tol": sheet.MISC_LINE_TOL + 1e-9,
     "why": "ключи записаны до 0,1 млрд ₽: до 0,05; больше — прямая идёт не от пары к пути без переходных частей 2027 года"},
    {"step": "misc", "name": f"ЧПД {int(sheet.MISC_YEAR) + 1} года клетки условий окна в обеих формах пути (с переходными частями {sheet.MISC_YEAR} года "
                             "и без) совпадает до второго порядка",
     "value": ("misc", "nii_next_year", "difference"), "target": 0.0, "tol": sheet.MISC_NEXT_TOL,
     "why": f"с {int(sheet.MISC_YEAR) + 1}К1 переходных частей в пути ЧПД нет — разность только через баланс (до {sheet.MISC_NEXT_TOL:g} млрд ₽); "
            "больше — часть пути 2027 года перешла в ЧПД следующего года, и снимать её пару из прямой нельзя (решение № 7, п. 2.4)"},
    {"step": "deductions", "name": "путь вычета сценария в п.п. на записанных ключах (чтение ядра) равен формуле «растущая часть + вычет сценария»",
     "value": ("frozen_check", "deduction_pp_error"), "target": 0.0, "tol": 6e-7,
     "why": "траектория записана шестью знаками: до 5·10⁻⁷"},
    {"step": "deductions", "name": "рублёвая часть пути вычета на записанных ключах (чтение ядра) равна формуле «доля η роста × RWA якоря + высвобождение»",
     "value": ("frozen_check", "deduction_rub_error"), "target": 0.0, "tol": 0.006,
     "why": "траектория записана до 0,01 млрд ₽"},
    {"step": "deductions", "name": "путь постоянной части прочих активов на записанных ключах (чтение ядра) равен формуле «доля η роста × RWA якоря + высвобождение»",
     "value": ("frozen_check", "fixed_change_error"), "target": 0.0, "tol": 0.006,
     "why": "траектория записана до 0,01 млрд ₽"},
    {"step": "deductions", "name": "рост вычетов (слагаемое (1), доля η) — одна сумма на обеих сторонах в каждом квартале (решение № 5, п. 3.1)",
     "value": ("frozen_check", "both_sides_term1"), "target": 0.0, "tol": 0.011,
     "why": "обе траектории записаны до 0,01 млрд ₽: разность — не больше двух полуединиц знака"},
    {"step": "deductions", "name": "высвобождение ОНА (слагаемое (4)) — одна сумма на обеих сторонах в каждом квартале (решение № 4, п. 3.2)",
     "value": ("frozen_check", "both_sides_term4"), "target": 0.0, "tol": 0.011,
     "why": "обе траектории записаны до 0,01 млрд ₽: разность — не больше двух полуединиц знака"},
    {"step": "deductions", "name": "постоянная часть прочих активов с путём не меньше нуля — в центре, на концах осей-связок и у вариантов",
     "flag": ("deductions", "fixed_sum_ok"), "why": "схема ядра (прил. A № 24) отказывает книге и концу оси с отрицательной суммой"},
    {"step": "deductions", "name": "путь постоянной части — ноль в квартале якоря (якорное условие ядра) в центре и у вариантов",
     "flag": ("deductions", "anchor_zero_ok"), "why": "якорь воспроизводит баланс фактов: приращение к якорю в квартале якоря — ноль"},
    {"step": "realized", "name": "квантили оси реализованной передачи, как её разыгрывает движок, равны квантилям произведения (P10, P90)",
     "flag": ("realized", "engine_match_ok"), "why": "концы записаны пятью знаками: квантили — до 5·10⁻⁶ (решение № 5, п. 3.4)"},
    {"step": "near", "name": "ступень маржи модальной клетки 2027К1 − 2026К4 не больше ступени одних книг на ставках мира (MODEL §3.2)",
     "value": ("frozen_check", "near_step_excess"), "target": 0.0, "tol": sheet.NEAR_STEP_TOL,
     "why": "траектория снимает ступень σ0 на границе года якоря + 1 (решение № 5, п. 3.5); запас — второй порядок через баланс квартала"},
    *({"step": "opex", "name": f"расходы {q}-го квартала года якоря — уровень по фактам", "value": ("frozen_check", f"opex_q{q}"),
       "target": ("frozen_check", f"opex_q{q}_goal"), "tol": 0.05, "why": "корень записан четырьмя знаками: до 0,02 млрд ₽"} for q in (3, 4)),
    *({"step": "opex", "name": name, "value": ("frozen_check", node), "target": sheet.OPEX_TO_ASSETS, "tol": 2e-5,
       "why": "корни записаны четырьмя знаками: до 0,002 п.п. отношения"}
      for name, node in (("расходы к средним активам слоя, первый год цели", "opex_goal_year_1"),
                         ("расходы к средним активам слоя, второй год цели", "opex_goal_year_2"),
                         ("расходы к средним активам слоя, среднее лет гейта", "opex_lt"))),
    *({"step": "fees", "name": name, "value": ("frozen_check", node), "target": sheet.FEES_TO_ASSETS, "tol": 2e-5,
       "why": "спред записан четырьмя знаками: до 0,002 п.п. отношения"}
      for name, node in (("комиссии к средним активам слоя, год цели", "fees_goal_year"),
                         ("комиссии к средним активам слоя, среднее после года цели", "fees_lt"))),
    {"step": "transmission", "name": "мир уровня неподвижен на оси цели передачи", "flag": ("transmission", "level_world_fixed"),
     "why": "ось передачи несёт только различие маржи между мирами"},
)


def relations(record: dict, template: dict) -> list[str]:
    """Соотношения между выведенными числами записи листа (`template` — шаблон книги до записи); каждое нарушение —
    строка. Узла записи нет (шаг не запускался) — его соотношения не проверяются."""
    bad = []
    keys, ends = record.get("keys") or {}, record.get("ends") or {}
    rz = record.get("realized")
    if rz is not None and not rz["axis"]["low"] < rz["centre"] < rz["axis"]["high"]:
        bad.append(f"центр реализованной передачи {rz['centre']} не внутри концов оси {rz['axis']['low']}…{rz['axis']['high']}")
    tr = record.get("transmission")
    if tr is not None:
        target = tr["rows"]["centre"]["target"]
        if not tr["axis"][0] <= target <= tr["axis"][1]:
            bad.append(f"цель передачи {target} вне своей оси {tr['axis'][0]}…{tr['axis'][1]}")
        level = tr["rows"]["centre"]["nim_key"]
        if not tr["nim_axis"][0] <= level <= tr["nim_axis"][1]:
            bad.append(f"ключ уровня маржи {level} вне своей оси {tr['nim_axis'][0]}…{tr['nim_axis'][1]}")
        unsolved = [name for name, row in tr["rows"].items() if not row["solved"]]
        if unsolved:
            bad.append("решатель передачи не решил цель: " + ", ".join(unsolved))
    sp = record.get("splits")
    if sp is not None:
        for name, axis in (("phi_split", "axis_phi"), ("sigma0_split", "axis_sigma0")):
            if not sp[axis][0] <= sp[name] <= sp[axis][1]:
                bad.append(f"доля {name} {sp[name]} вне своей оси {sp[axis][0]}…{sp[axis][1]}")
    mi = record.get("misc")
    if mi is not None and not mi["axis"]["low"] <= mi["key"] <= mi["axis"]["high"]:
        bad.append(f"ближний ключ прочих доходов {mi['key']} вне своей оси {mi['axis']['low']}…{mi['axis']['high']}")
    iss = record.get("issue")
    if iss is not None:
        want = round(iss["stay"] * iss["volume"] + iss["distributions"] + iss["coupon_return"], 2)
        if abs(iss["centre"] - want) > 1e-9:
            bad.append(f"приток квартала выпуска {iss['centre']} не равен доле денег × объём + поправкам потока {want}")
        lo, hi = iss["stay_axis"]["low"][sheet.ISSUE_FLOW_PATH], iss["stay_axis"]["high"][sheet.ISSUE_FLOW_PATH]
        if not lo <= iss["centre"] <= hi:
            bad.append(f"приток центра {iss['centre']} вне оси доли денег {lo}…{hi}")
    fu = record.get("funds")
    if fu is not None:
        for seg, level in fu["levels"].items():
            lo, hi = sorted((float(fu["facts"][seg]), float(fu["need_level"])))
            if not lo - 1e-9 <= level <= hi + 1e-9:
                bad.append(f"премия средств клиентов ({seg}) {level} вне отрезка «факт — нужда» {lo}…{hi}")
    wh = keys.get("checks.wholesale_share")
    if wh is not None and not wh[0] < wh[1]:
        bad.append(f"коридор доли оптового фондирования пуст: {wh}")
    for w, pair in (keys.get("checks.pb_by_world") or {}).items():
        if not pair[0] < pair[1]:
            bad.append(f"коридор P/B мира {w} пуст: {pair}")
    q4 = ends.get("opex_q4")
    if q4 is not None and not q4["low"] <= q4["high"]:
        bad.append(f"ось сезонного отношения расходов: низ {q4['low']} выше верха {q4['high']}")
    centre_q4 = (template.get("opex") or {}).get("real_growth", {}).get(ANCHOR_YEAR + "Q4")
    centre_q4 = (keys.get("opex.real_growth") or {}).get(ANCHOR_YEAR + "Q4", centre_q4)
    if q4 is not None and centre_q4 is not None and not q4["low"] - 1e-4 <= centre_q4 <= q4["high"] + 1e-4:
        bad.append(f"корень 4-го квартала {centre_q4} вне своей оси {q4['low']}…{q4['high']}")
    return bad


# Файлы-спутники шаблона: YAML рядом с шаблоном, куда команда пишет выведенные числа тем же точечным способом, что в шаблон
# (адрес — от корня файла; запись — {file, title, writes}). У книги 0.3 на ядре третьего прохода спутников нет: подмены, ждавшие
# ядра (pass3_overrides.yaml), перенесены в шаблон — сценарий «послабление» стоит четвёртым сценарием книги, связки осей выпуска
# по 87 ₽ — осями шаблона (записи шага deductions выше).
COMPANIONS = ()

# Лист предельной экономики роста (проверка, ключей не пишет): рубль корпоративного кредита НА ПРЕДЕЛЬНОЙ ЕДИНИЦЕ САМОЙ МОДЕЛИ
# (решение ведущего № 4, п. 3.7): рубль несёт то, что ядро к нему привязывает (прочие активы без дохода со своей плотностью,
# прочие обязательства, резерв), фондируется балансирующей статьёй ядра, капитал — по связывающему нормативу (Н20.0, весь базовый);
# сверочная строка — разность ядра в модальной клетке при премии +1 п.п. (лист приёмки). Норма решения № 3, раздел 4 — та же: не
# ниже 5 % и не выше 30 % в каждом мире; около нейтрального в мире H, ±5 п.п. Прежнее чтение (базовый капитал со слоями по своей
# цене, решение № 2, п. 7.6) печатается рядом, справочно.
MARGINAL = {
    "sheet": "marginal_loan.py",
    "table": ("marginal", "corporate_loan"),       # мир → строки
    "value": "return_model",                       # отдача на предельной единице модели — норма
    "segment_basis": "return_core_base",           # прежнее чтение: базовый капитал со слоями по своей цене, фондирование ядра (справочно)
    "hurdle": "cost_of_equity",
    "anchor": ("sanity",),                         # {model_min, model_max, segment_low, segment_high}: отдачи на предельной единице по мирам против нормы
    "anchor_slack": 0.0,
    "title": "рубль корпоративного кредита на предельной единице модели после налога (стационар мира; связки баланса ядра; капитал — Н20.0)",
    "second": "прежнее чтение — базовый капитал со слоями",   # слова второго числа строки
    "anchor_words": ("отдачи на предельной единице модели по мирам", "при норме (решение № 3, раздел 4: не ниже 5 % и не выше 30 % в каждом мире)",
                     "внутри", "ВНЕ НОРМЫ"),
    "verdict": ("окупает", "НЕ окупает"),
    "tail": "стационар",
}

# Листы приёмочных проверок книги (ключей не пишут): строки {name, value, low, high, ok, words} печатает команда.
ACCEPTANCE = (
    {"sheet": "facts_check.py", "title": "путь года якоря против фактов; проверки до счёта оценки (решения № 2, пп. 1.6, 7.8; строка (б) — окно C восьми "
                                         "месяцев, решение № 4, п. 3.6); маржа года после якоря 1(а) — на режиме «нормализация», смесь рядом (решение "
                                         "№ 6, п. 2.3); разложение уровня пути и сторож cir_lt (решение № 4, п. 3.5); путь клетки против "
                                         "бэктеста 1(г) — на составе якоря, с разложением σ0 / состав / капитал / постоянные активы / прочее / сдвиг (решение "
                                         "№ 5, п. 3.5); предельный кредит на предельной единице модели со сверкой разностью ядра (решение № 4, п. 3.7); рост "
                                         "портфеля и внешний капитал 1(д) (решение № 3, п. 3.4)"},
)

REMINDERS = (
    "слова комментариев шаблона у переписанных ключей несут числа прежнего вывода — сверить руками",
    "ближние ключи спредов книг команда не выводит: при новом якоре их пересчитывает лист calib-nii (near_path.py), запись — inputs/vtb_r2_inputs.json",
    "решение № 7, п. 2.4: снятие остатка якоря 2027 года из начала прямой прочих 2028–2029 стоит на числах калибровки calib-nii (вход "
    "nii_books.near_rule: a, s, остаток, у бумаг — ρ окна и ставка якоря); при новом якоре их пересчитывает лист calib-nii вместе с ближними "
    "ключами — иначе шаг misc отказывает (счёт листа обязан повторять ближние ключи книги)",
    "решение № 7, дополнение, п. 1: сверка ближних ключей книг (шаг misc) отказывает и при обновлении миров (опорное заседание Банка России "
    "23.10.2026): ближние ключи книг стоят на ключевой мира H записи миров — лист calib-nii пересчитывает их на новой ключевой мира H",
    "решение № 8, п. 1.2: ключи восьмого прохода capital.at1_share {enabled: true, from: 2029Q1, spread: 0.04, base: anchor}, "
    "capital.n20.t2_premium {enabled: true, spread: 0.025, base: anchor} и valuation.terminal.other_movements: flat_rub — суждения шаблона "
    "(листом не выводятся); оси spread — полоса; развилки — варианты at1_anchor_rub, t2_premium_off, om_terminal_none; «распределения "
    "индексируются» книгой не выражается — цену считать оценкой рядом с отчётом круга",
    "решение № 8, п. 1.4: до первого реального переноса якоря с ключами AT1 и T2 (30.10.2026) база AT1 и слот купона якоря решаются вместе "
    "по фактам нового якоря (база = AT1 нового якоря, слот — купон только на базу); надбавка T2 в реальных процентах — правило фактов "
    "(инструмент переносит базы числами 368,0 и 339,1 — на реальном отчёте их пересмотреть)",
    "справочные варианты выведенные числа центра не пересчитывают (кроме вариантов со словами «по счёту ядра»)",
    "пороги гейтов (ключи под checks) команда сверяет с правилом листа, но не пишет: это сторожа — их ставит сборщик рукой, с причиной "
    "в комментарии шаблона (решение ведущего № 2, п. 7.7)",
    "таблицы книги (model.book_results без --fast) и объяснения гейтов — после того как число устоялось",
    "ключи пятого прохода ядра: доля λ_F (valuation.terminal.fixed_growth_share) и правило разброса checks.grid_variance — суждения в шаблоне, "
    "листом не выводятся; рубли пути вычета, путь постоянной части прочих активов и вес приращения пишет команда (шаги deductions и anchor)",
    "развилки пути прочих доходов по мирам и чтение «вложение выпуска стоит своей цены» справочными вариантами книги не выражаются — цены в "
    "записи вывода (ends.misc_forks, issue.asset_at_price): перенести в лист решения руками",
    "решение № 5: использование ОНА после 2036 года — развилка руками (центр +0,52 ₽; миры +0,87 / +0,59 / +0,40; «полтемпа» +0,98…+1,05; ключа ядра "
    "нет — медленный круг); две оси реализованной передачи (измеренная и доля книги) и проверка ступени снизу в стороже nim_path_joint — правка ядра "
    "на медленном круге",
    "решение № 6: ключ ядра capital.n20.t2_share {enabled: true, from: 2029Q1} — суждение шаблона (листом не выводится); траекторию t2 после 2028 года "
    "ядро при ключе не читает (вариант t2_modal_rub — ключ выключен); варианты t2_flat_rub и t2_amortizing несут enabled: false. Сторож "
    "roe_k_spread.max_world_gap — по правилу листа на мере гейта roe_k_homogeneity (переносит сборщик рукой с причиной)",
)
