# Text-quest

Симулятор выживания в любом сеттинге. **Python считает физику и состояние**, модель только рассказывает сцену по симптомам. Зависимостей нет — нужен Python 3.

Игрок не видит ни одной шкалы, броска или поля JSON. Состояние живёт в файле, не в памяти модели.

Репозиторий: https://github.com/blockshot9777-glitch/Text-quest

## Быстрый старт

Игра в браузере (локальный сервер, два вызова LLM на ход):

```text
python play.py
```

Откроется http://127.0.0.1:8765. Выбрать провайдера (Ollama, LM Studio, OpenAI-совместимый, Anthropic), написать сеттинг свободным текстом, нажать «Начать игру».

Рядом должны лежать `play.py` и собранный `sim.py`. Подробности провайдеров — в [PLAY_README.md](PLAY_README.md).

Проверить, что движок живой:

```text
python audit.py
python selftest.py
python sim.py selftest
```

Ожидается ноль ошибок в `audit.py`, **141/141** в `selftest.py`, **21/21** в `sim.py selftest`, код выхода `0`.

## Как это устроено

1. Краткий замысел (`brief_*.json`) → `worldgen.py` собирает мир и валидирует его.
2. Ход считает `engine.py`: время, среда, нужды, броски, доступ к вещам, бой, лечение, общество.
3. Содержимое существа (голод, холод, симптомы, смерть, последствия провала) — только в `ruleset.json`. Тот же код крутит человека и механоида (`ruleset_mech.json`).
4. Случайность — `sha256(seed|ход|индекс)`, не `random` и не `hash()`.
5. Не больше двух проверок за ход. Переход на неизвестную площадку движок отвергает.

`sim.py` — склейка ядра для раздачи агенту. Руками его не править: после правок исходников `python build_bundle.py`.

## Команды движка

Состояние по умолчанию — файл рядом (`SIM_STATE` переопределяет путь).

```text
python sim.py new --brief examples/brief_1917.json --out state.json
python sim.py check --state state.json
python sim.py look --window 5
python sim.py act --minutes 40 --activity 1 --check "perception:20:осмотр::восприятие"
python sim.py act --minutes 8 --take-resource "вода:0.5"
python sim.py act --minutes 8 --water 0.4
python sim.py fight --foe "имя:45:10:0"
python sim.py treat --supplies 20
python sim.py snapshot --tag имя
python sim.py restore --file путь
python sim.py compact
```

При разработке те же команды есть у `engine.py` / `worldgen.py`. Инструкция для агента-рассказчика без окна — [AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md). Сборка одного файла — [BUNDLE_README.md](BUNDLE_README.md).

## Пример: попаданец в 1917

`examples/brief_1917.json` — Петроград, 23 февраля 1917, перенос «шёл с работы».

```text
python examples/run_1917_random.py
```

Сценарий каждый ход даёт 4 варианта и выбирает случайный. Лог: `examples/run_1917_log.json`. На seed `19170308` тепло у печи не бесплатное: нужны дрова (`топливо`) и очаг трактира (`hearth`) или зажигалка. `--sheltered` / `site.shelter` убирает ветер, `--fire` добавляет `cold_model.fire_bonus_c` и списывает `item_use.fuel_per_h`. Дальше RNG может выгнать чужака на Неву — смерть от мороза, не от дыры в укрытии.

Другие замыслы и миры: `examples/brief_*.json`, Новгород 1052, Кастор, «Римворлд». Дрейф малого корабля с амнезией: `python examples/run_drift_random.py` (seed `55020714`, по умолчанию 100 ходов) или `python examples/run_drift_random.py 1000`. Лог: `examples/run_drift_log.json`, сводка: `examples/run_drift_summary.json`. Счётчики CO₂ и тепла несут `on_complete`. Огонь на корабле — спирт с палубы и зажигалка из кармана, не флаг. Без сознания время идёт дальше, в летальном холоде это доходит до `dead`. Вода и автопилот пока без эффектов — незаполненный замысел. `--water` по пустой фляге — отказ.

## Карта репозитория

| Файл | Роль |
|---|---|
| `engine.py` | ход: время, среда, нужды, броски, бой, лечение |
| `worldgen.py` | генерация мира из brief + валидация |
| `matter.py` | масса / объём / clo из материала и формы |
| `edc.py` | вещи попаданца из нашего времени (только XXI век; другие эпохи — не этот модуль) |
| `society.py` | NPC, слухи, фракции, ресурсы площадок |
| `ruleset.json` | человек: шкалы, симптомы, cold_model, healing |
| `ruleset_mech.json` | то же ядро, другое существо |
| `play.py` | окно в браузере + оркестратор LLM |
| `sim.py` | собранный движок, не править руками |
| `build_bundle.py` | пересборка `sim.py` |
| `selftest.py` / `audit.py` | тесты и статическая ревизия |
| `text-quest-core.md` | запасной промпт, если код исполнять негде (точность ниже) |

После правки ядра:

```text
python audit.py
python selftest.py
python build_bundle.py
python sim.py selftest
```

Если менялся `ruleset.json`: `python worldgen.py checkrules --rules ruleset.json`.

Полная передача для разработки, архитектурные запреты и честный список дыр — [HANDOFF.md](HANDOFF.md).
