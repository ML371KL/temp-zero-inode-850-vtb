# worlds_bank — банковская надстройка миров (A-M3, MODEL §3.1, прил. B)

`build_overlay.py` собирает `data/assumptions/worlds_bank.json` из листа надстройки этапа 1
(`inputs/bank_overlay_draft.yaml` — копия общей части листа, имена локальных папок заменены относительными путями; `--sync` обновляет
копию из `$BANK_HANDOFF_DIR`, `--check` — сверка). Хэш файла вписывает в книгу `build_assumptions.py`
(`worlds.overlay.sha256`); ядро сверяет файл с этим хэшем.

Рост сектора у банков семейства один, поэтому файл обязан совпасть с надстройкой семейства бит в бит (с миров 1.7, книга
0.9, — sha256 8611f015…; до них — 6fb82a41…) — скрипт предупреждает, если это не так. Лист этапа 1 несёт готовые пути по
мирам; скрипт их не пересчитывает, а проверяет: мир N — середины диапазонов базового сценария Банка России (с миров 1.7 —
среднесрочный прогноз 23.10.2026, с. 1, sha256 0e007c6d…; те же числа — табл. 3.2 итоговой ОНДКП 28.10.2026, PDF-с. 73;
до них — табл. 3.2 проекта ОНДКП 30.09.2026, sha256 3c3270ef…) и прогноза Банка России по балансам («Банковский
сектор. II кв. 2026», PDF-с. 20) для «прочей розницы» 2026–2027 годов; 2028–2029 — (население − w·ИЖК)/(1 − w),
w = 0,5806; миры H и M — реальный рост базы при инфляции своего мира (g_W = (1 + g_N)(1 + π_W)/(1 + π_N) − 1);
средства физлиц и бизнеса — денежная масса М2; годы 2026–2029, дальше ядро сводит рост к g_T мира к `volumes.lt_from`
(2033).

Надстройка миров 1.7 (книга 0.9):

| Мир | Кредиты бизнесу 2026 / 27 / 28 / 29 | Ипотека | Прочая розница | Средства (М2) |
|---|---|---|---|---|
| N | <!--~bank:worlds.N.credit_growth.corporate.2026 p1-->10,5<!--~--> / <!--~bank:worlds.N.credit_growth.corporate.2027 p1-->8,5<!--~--> / <!--~bank:worlds.N.credit_growth.corporate.2028 p1-->10,5<!--~--> / <!--~bank:worlds.N.credit_growth.corporate.2029 p1-->10,5<!--~--> % | <!--~bank:worlds.N.credit_growth.mortgage.2026 p1-->7,5<!--~--> / <!--~bank:worlds.N.credit_growth.mortgage.2027 p1-->7,5<!--~--> / <!--~bank:worlds.N.credit_growth.mortgage.2028 p1-->12,5<!--~--> / <!--~bank:worlds.N.credit_growth.mortgage.2029 p1-->12,5<!--~--> | <!--~bank:worlds.N.credit_growth.retail_other.2026 p1-->6,0<!--~--> / <!--~bank:worlds.N.credit_growth.retail_other.2027 p1-->5,5<!--~--> / <!--~bank:worlds.N.credit_growth.retail_other.2028 p1-->7,7<!--~--> / <!--~bank:worlds.N.credit_growth.retail_other.2029 p1-->7,7<!--~--> | <!--~bank:worlds.N.funds_growth.retail.2026 p1-->11,5<!--~--> / <!--~bank:worlds.N.funds_growth.retail.2027 p1-->7,5<!--~--> / <!--~bank:worlds.N.funds_growth.retail.2028 p1-->9,5<!--~--> / <!--~bank:worlds.N.funds_growth.retail.2029 p1-->9,5<!--~--> |
| H | <!--~bank:worlds.H.credit_growth.corporate.2026 p1-->10,5<!--~--> / <!--~bank:worlds.H.credit_growth.corporate.2027 p1-->10,2<!--~--> / <!--~bank:worlds.H.credit_growth.corporate.2028 p1-->13,4<!--~--> / <!--~bank:worlds.H.credit_growth.corporate.2029 p1-->13,2<!--~--> | <!--~bank:worlds.H.credit_growth.mortgage.2026 p1-->7,5<!--~--> / <!--~bank:worlds.H.credit_growth.mortgage.2027 p1-->9,2<!--~--> / <!--~bank:worlds.H.credit_growth.mortgage.2028 p1-->15,4<!--~--> / <!--~bank:worlds.H.credit_growth.mortgage.2029 p1-->15,3<!--~--> | <!--~bank:worlds.H.credit_growth.retail_other.2026 p1-->6,0<!--~--> / <!--~bank:worlds.H.credit_growth.retail_other.2027 p1-->7,2<!--~--> / <!--~bank:worlds.H.credit_growth.retail_other.2028 p1-->10,5<!--~--> / <!--~bank:worlds.H.credit_growth.retail_other.2029 p1-->10,4<!--~--> | <!--~bank:worlds.H.funds_growth.retail.2026 p1-->11,5<!--~--> / <!--~bank:worlds.H.funds_growth.retail.2027 p1-->9,2<!--~--> / <!--~bank:worlds.H.funds_growth.retail.2028 p1-->12,3<!--~--> / <!--~bank:worlds.H.funds_growth.retail.2029 p1-->12,2<!--~--> |
| M | <!--~bank:worlds.M.credit_growth.corporate.2026 p1-->10,5<!--~--> / <!--~bank:worlds.M.credit_growth.corporate.2027 p1-->8,5<!--~--> / <!--~bank:worlds.M.credit_growth.corporate.2028 p1-->13,7<!--~--> / <!--~bank:worlds.M.credit_growth.corporate.2029 p1-->16,9<!--~--> | <!--~bank:worlds.M.credit_growth.mortgage.2026 p1-->7,5<!--~--> / <!--~bank:worlds.M.credit_growth.mortgage.2027 p1-->7,5<!--~--> / <!--~bank:worlds.M.credit_growth.mortgage.2028 p1-->15,8<!--~--> / <!--~bank:worlds.M.credit_growth.mortgage.2029 p1-->19,0<!--~--> | <!--~bank:worlds.M.credit_growth.retail_other.2026 p1-->6,0<!--~--> / <!--~bank:worlds.M.credit_growth.retail_other.2027 p1-->5,5<!--~--> / <!--~bank:worlds.M.credit_growth.retail_other.2028 p1-->10,9<!--~--> / <!--~bank:worlds.M.credit_growth.retail_other.2029 p1-->14,0<!--~--> | <!--~bank:worlds.M.funds_growth.retail.2026 p1-->11,5<!--~--> / <!--~bank:worlds.M.funds_growth.retail.2027 p1-->7,5<!--~--> / <!--~bank:worlds.M.funds_growth.retail.2028 p1-->12,7<!--~--> / <!--~bank:worlds.M.funds_growth.retail.2029 p1-->15,9<!--~--> |

До неё (книга 0.8, проект ОНДКП 30.09.2026 и миры 1.4): кредиты бизнесу N 9,0 / 9,5 / 10,5 / 10,5 %, ипотека 8,0 / 9,5 /
12,5 / 12,5, М2 9,5 / 8,5 / 9,5 / 9,5; H 2027–2029 — кредиты бизнесу 10,9 / 12,7 / 12,3, M — 9,8 / 13,9 / 16,6.

Лист этапа 1 миров 1.7 — `stage1/worlds/bank_overlay_build_1_7.py` папки передачи: пути — надстройка семейства 1.7 как
есть (собрана сборщиком канона миров), мир N сверен с первичкой. Дата и текст рецепта надстройки (`source.as_of`,
`recipe`) — константы `AS_OF` и `RECIPE` сборщика.

Премии роста ВТБ к сектору в надстройку не входят — это ключи книги (`volumes.loan_share_drift`, `funds_share_drift`).
Копия листа несёт только общую часть (блоки `meta` и `sector`): блоки премий и истории панели-образца сняты при порте
ВТБ.
