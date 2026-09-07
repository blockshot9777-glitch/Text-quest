#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ИГРА — локальное окно поверх движка.

Запуск:  python3 play.py       затем открыть http://127.0.0.1:8765

Зависимостей нет, только стандартная библиотека. Рядом должен лежать sim.py.

Что здесь важно архитектурно:
  · состояние живёт в файле и НИКОГДА не попадает в браузер — только проза;
  · на ход делается два вызова модели: разбор намерения (низкая температура,
    строгий JSON) и проза (высокая температура, по уже переведённым симптомам);
  · модель не видит ни одной шкалы — значит, не может их проболтать
    и не может подогнать механику под красивый текст.
"""
import json, os, sys, io, re, time, urllib.request, urllib.error, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim  # движок одним файлом

STATE_PATH = os.path.join(HERE, "play_state.json")
CONF_PATH = os.path.join(HERE, "play_config.json")
sim.STATE = STATE_PATH

# ─────────────────────────── ПРОВАЙДЕРЫ МОДЕЛЕЙ ───────────────────────────

PROVIDERS = {
    "ollama":    {"url": "http://127.0.0.1:11434/api/chat",   "needs_key": False},
    "openai":    {"url": "https://api.openai.com/v1/chat/completions", "needs_key": True},
    "local":     {"url": "http://127.0.0.1:1234/v1/chat/completions",  "needs_key": False},
    "anthropic": {"url": "https://api.anthropic.com/v1/messages",      "needs_key": True},
}


# JSON Schema замысла: ловит те формы, на которых Qwen3.5 9B сжигал 3 попытки.
# LM Studio /v1/chat/completions требует name + strict внутри json_schema.
BRIEF_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "physics_on": {
            "type": "array",
            "items": {"type": "string", "enum": list(sim.PHYSICS_ON)},  # публичное имя бандла; не переименовывать в сборке
        },
        "skills": {
            "type": "object",
            "additionalProperties": {"type": "number"},
        },
        "sites": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "exits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "properties": {
                                "difficulty": {"type": "number"},
                            },
                        },
                    },
                },
            },
        },
        "npcs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "disposition": {"type": "number", "minimum": -100, "maximum": 100},
                },
            },
        },
        "factions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "power": {"type": "number"},
                    "disposition": {"type": "number", "minimum": -100, "maximum": 100},
                    "stance_to_pc": {"type": "number", "minimum": -100, "maximum": 100},
                },
            },
        },
    },
}


def brief_response_format():
    """response_format для OpenAI-совместимых (LM Studio). strict — требование сервера."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "world_brief",
            "strict": True,
            "schema": BRIEF_SCHEMA,
        },
    }


def llm(cfg, system, user, temperature=0.2, max_tokens=1400, response_format=None):
    """Единый вызов для всех провайдеров. Возвращает строку ответа."""
    prov = cfg.get("provider", "ollama")
    url = cfg.get("url") or PROVIDERS[prov]["url"]
    model = cfg.get("model", "llama3.1")
    key = cfg.get("api_key", "")
    headers = {"Content-Type": "application/json"}

    if prov == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                "system": system, "messages": [{"role": "user", "content": user}]}
    elif prov == "ollama":
        body = {"model": model, "stream": False, "options": {"temperature": temperature},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
    else:  # openai-совместимые: OpenAI, LM Studio, llama.cpp, vLLM
        if key: headers["Authorization"] = f"Bearer {key}"
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if response_format:
            body["response_format"] = response_format

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=cfg.get("timeout", 180)) as r:
        data = json.loads(r.read().decode("utf-8"))

    if prov == "anthropic":
        return "".join(b.get("text", "") for b in data.get("content", []))
    if prov == "ollama":
        return data.get("message", {}).get("content", "")
    return data["choices"][0]["message"]["content"]


def json_from(text):
    """Модели любят обрамлять JSON болтовнёй и заборчиками. Достаём объект."""
    t = re.sub(r"```(?:json)?", "", text).strip()
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1: raise ValueError("в ответе нет JSON:\n" + text[:400])
    return json.loads(t[i:j+1])


# ─────────────────────────── ПРОМПТЫ ───────────────────────────

SYS_BRIEF = """Ты — генератор миров для безжалостного симулятора выживания.
По вводной игрока верни ТОЛЬКО JSON-замысел мира, без пояснений и заборчиков.

Обязательные поля:
 seed (число), setting (строка), tech_ceiling (primitive|preindustrial|industrial|spacefaring),
 ladder (список уровней от корня к мелкому), ladder_root (строка, корень пути),
 physics_on (список из: холод, жара, голод, жажда, сон, раны, болезни, гипоксия,
   давление, радиация, вакуум, углекислота, невесомость, нагрузка, погода),
 start_path (полный путь площадки), start_local (описание позиции), start_z (число),
 start_hour (число), weather, ambient_c, wind_ms,
 climate {t_min,t_max,sunrise,sunset,note}, epoch, start_date, seasons,
 needs {hunger,thirst,fatigue,cold_stress,stress} — числа 0..100,
 skills — необязательно, объект {имя: число} (athletics, stealth, …).
   Не список и не строки. Нормализатор ещё принимает список
   {name, value|level|score} или [{имя: число}]; rating/skill_level — отказ.
 conditions (список),
 chain — список узлов [{path,scale,canon,...}] от корня до региона,
 sites — 1-3 площадки [{path,name,z_m,desc_true,exits[{to,mode,travel_min,dz_m,difficulty,gate}],
   resources:[{name,amount,tags?}], hazards, objects, structures?, shelter?, hearth?, touched:true}].
   objects — строки (проза, не ломается) или {name, parts?, tags?}.
   parts — как make_item: [материал, форма, Д, Ш, В]. Без parts объект неразрушим.
   structures — уже стоящие конструкции с тем же составом; теги роли из structure_use,
   не имена «дом»/«сарай». player_made:true защищает площадку от compact.
   tags ресурса обязательны, если его можно взять и использовать.
   Имя само по себе ничего не значит: «кипяток» без тега — просто ресурс.
   Пример (подсказка автору, не словарь ядра; теги должны совпасть с item_use
   правил существа):
     resources: [
       {"name": "кипяток", "amount": 8, "tags": ["вода"]},
       {"name": "чёрный хлеб", "amount": 6, "tags": ["еда"]},
       {"name": "дрова у печи", "amount": 4, "tags": ["топливо"]}
     ]
     item_use человека: water_tags ["вода"], food_tags ["еда"],
       fuel_tags ["топливо"], igniter_tags ["огонь"], fuel_per_h 0.25
   Другое существо — другие теги. shelter:true — помещение (штиль без флага).
   hearth:true — очаг уже есть.
 npcs — 4-6 [{id,name,path,goal,long_goal,resources,disposition,knows_about_pc:[],alive:true,schedule,faction}],
 factions — 2-4 [{id,name,goal,power,stance_to_pc,relations:{}}],
 clocks — 3-5 [{name,filled,max,period_h,hidden,payoff, on_complete?, fired?}],
   on_complete — список операций при срабатывании (site/sites+env или path+set/add);
   sites:"*" — только площадки уже в sites_canon на момент срабатывания;
   add на одно поле у двух счётчиков складывается (не идемпотентен и не обязан быть);
   без on_complete payoff остаётся только строкой в журнале;
 truths — 4-6 строк (то, что верно, но игрок не знает),
 opening_fact (строка).

Если персонаж — человек нашего времени, попавший в другой мир, добавь
 "carryover": {"context": "auto"} и НЕ указывай worn/containers/items:
снаряжение сгенерируется само по моменту переноса.
Иначе укажи worn (список), containers (список), items (список пар [предмет, контейнер]).

ЖЁСТКО: никакого баланса под игрока. Минимум 1 площадка смертельна без подготовки.
Числа среды реальные. Лестница ровно нужной глубины — не тащи космос в осаду города."""

SYS_MECH = """Ты — разборщик намерений для симулятора. Верни ТОЛЬКО JSON, без пояснений.

Поля:
 minutes  — сколько реально займёт действие (осмотреться 2, обыскать 40,
            развести костёр 20, переход — по travel_min выхода, сон 480)
 activity — 0 покой, 1 ходьба/обычное, 2 тяжёлая работа
 checks   — список до ДВУХ строк вида "навык:сложность:метка:преимущество:домен"
            домены: движение, точная, восприятие, среда, социальное, борьба
            сложность 0-60, преимущество 0-25 (инструмент, упор, свет)
            если исход не под вопросом — пустой список
 to       — полный путь площадки, если игрок переходит (только из списка выходов!)
 local    — краткое новое описание позиции, если сместился в пределах площадки
 take_resource — строка "имя:количество", взять из resources текущей площадки
            (только то, что есть в ресурсы_площадки). Сначала наполняет предмет
            в доступе с тем же тегом и fill<1; новый предмет — если такой тары нет.
            Не выдумывай отдельную команду «наполнить».
 build    — имя конструкции. Нужны parts (или from_object с parts в данных).
            Не выдумывай материал, которого нет в руках и не объект площадки.
            tags — из теги_укрытия / теги_очага обстановки, не слово «дом».
 parts    — список "материал:форма:Д:Ш:В". Движок считает массу; абсурд — отказ.
 from_object — имя из объекты_площадки. Проза без parts — отказ, не сочиняй состав.
 break    — имя или id конструкции из конструкции_площадки. Меняет укрытие/выход сразу.
 reveal   — перевести объект с parts в конструкцию. Без parts — отказ.
 water, food  — сколько списать с предметов, чьи теги в теги_питья / теги_еды обстановки
            (синонимы CLI, не зашитые слова «вода»/«еда»). Нет тегов в правилах — не ставь.
            без запаса (fill=0 или нет предмета) движок откажет, нужду не тронет
 sheltered, fire, sleeping — true/false
            fire=true только если в обстановке топливо_с_собой и чем_зажечь (или очаг).
            Теги горючего и зажигателя — поля обстановки, не угадывай дрова и зажигалку.
            без сознания — только ждать (minutes), без to/check/take/water/food/fire/build
 window   — секунды доступного времени: схватка 2, падение 2, обвал 5, обычно 60

Если действие физически невозможно — верни {"impossible": "почему"}."""

SYS_PROSE = """Ты — рассказчик безжалостного симулятора выживания.

ЗАПРЕЩЕНО НАСТРОГО:
 · любые числа состояния, шкалы, проценты, проверки, броски, сложности;
 · слова: ход, бросок, проверка, навык, успех, провал, катастрофа, вариант,
   инвентарь, счётчик, статус, очки;
 · спасать игрока от последствий, подкидывать нужный предмет;
 · упоминать предмет, которого нет в списке доступного, даже как упущенный шанс.

Тебе дают СИМПТОМЫ — это и есть материал. Переводи их в ощущения тела, не в
диагнозы. Если сказано «дрожь прекратилась, пришло тепло» — пиши облегчение
и покой, а не тревогу: тело врёт, и так задумано.

Формат ответа — строго JSON:
{"prose": "150-250 слов сцены и последствий",
 "options": ["намерение 1","намерение 2","намерение 3","намерение 4"]}

Варианты — намерения человека, БЕЗ пометок цены, риска и шансов.
Каждый ведёт к структурно разному исходу. Безопасного может не быть."""


# ─────────────────────────── ХОД ───────────────────────────

def scene_context(S):
    """То, что модель имеет право знать. Никаких шкал."""
    site = sim.site_of(S)
    exits = [{"to": e["to"], "mode": e.get("mode"), "travel_min": e.get("travel_min"),
              "difficulty": e.get("difficulty"), "gate": e.get("gate")}
             for e in sim.site_exits(site)]
    su = sim.rules(S).get("structure_use") or {}
    objs = [{"name": o.get("name"), "есть_части": bool(o.get("parts"))}
            for o in sim.site_objects(site)]
    structs = [{"id": s.get("id"), "name": s.get("name"), "tags": s.get("tags") or []}
               for s in sim.structures_of(site)]
    avail = sim.available(S, 60)
    res = [{"name": r.get("name"), "есть": (r.get("amount") or 0) > 0}
           for r in (site.get("resources") or [])]
    iu = sim.rules(S).get("item_use") or {}
    ign = iu.get("igniter_tags") or []
    fuel_tags = iu.get("fuel_tags") or []
    drink_tags = iu.get("water_tags") or []
    eat_tags = iu.get("food_tags") or []
    return {
        "место": S["position"]["local"],
        "площадка": site.get("name", ""),
        "путь": S["position"]["path"],
        "выходы": exits,
        "ресурсы_площадки": res,
        "под_рукой": [n for n, _ in avail],
        "в_руках": [sim.item_name(S, i) for i in S["gear"]["hands"]["held"]],
        "теги_зажигателя": ign,
        "теги_горючего": fuel_tags,
        "теги_питья": drink_tags,
        "теги_еды": eat_tags,
        "теги_укрытия": su.get("shelter_tags") or [],
        "теги_очага": su.get("hearth_tags") or [],
        "объекты_площадки": objs,
        "конструкции_площадки": structs,
        "чем_зажечь": sim.has_tags_accessible(S, ign, 60) or sim.site_has_hearth(S, site),
        "топливо_с_собой": sim.fuel_have(S) > 0,
        "очаг": sim.site_has_hearth(S, site),
        "есть_укрытие": sim.is_sheltered(S),
        "погода": S["time"].get("weather"),
        "свет": S["time"].get("light"),
        "известные_факты": S["known"].get("facts", [])[-6:],
        "навыки": list(S["pc"]["skills"].keys()),
    }


def play_turn(cfg, intent):
    S = sim.load()
    if S.get("status") == "dead":
        return {"prose": "Игра окончена.", "options": [], "dead": True}

    ctx = scene_context(S)
    mech_raw = llm(cfg, SYS_MECH,
                   "Обстановка:\n" + json.dumps(ctx, ensure_ascii=False, indent=1) +
                   f"\n\nИгрок хочет: {intent}", temperature=0.15, max_tokens=600)
    m = json_from(mech_raw)
    if m.get("impossible"):
        return {"prose": m["impossible"], "options": [], "impossible": True}

    args = ["act", "--minutes", str(max(0, float(m.get("minutes", 5)))),
            "--activity", str(int(m.get("activity", 1)))]
    for c in (m.get("checks") or [])[:2]:
        args += ["--check", c]
    if m.get("to"):    args += ["--to", m["to"]]
    if m.get("local"): args += ["--local", m["local"]]
    if m.get("take_resource"):
        args += ["--take-resource", str(m["take_resource"])]
    if m.get("build"):
        args += ["--build", str(m["build"])]
        for p in (m.get("parts") or []):
            args += ["--build-part", str(p)]
        for t in (m.get("tags") or []):
            args += ["--build-tag", str(t)]
        if m.get("from_object"):
            args += ["--from-object", str(m["from_object"])]
        for b in (m.get("block_exits") or []):
            args += ["--build-block", str(b)]
    if m.get("break"):
        args += ["--break", str(m["break"])]
    if m.get("reveal"):
        args += ["--reveal", str(m["reveal"])]
        for p in (m.get("parts") or []):
            args += ["--build-part", str(p)]
    if m.get("water"): args += ["--water", str(m["water"])]
    if m.get("food"):  args += ["--food", str(m["food"])]
    for f in ("sheltered", "fire", "sleeping"):
        if m.get(f): args.append("--" + f)
    args += ["--window", str(int(m.get("window", 60)))]

    report = run_engine(args)

    S = sim.load()
    payload = {
        "намерение": intent,
        "симптомы": sim.symptoms(S),
        "исходы_проверок": [{"что": m.group(1),
                             "итог": {"КРИТИЧЕСКИЙ УСПЕХ": "вышло лучше, чем рассчитывал",
                                      "УСПЕХ": "получилось",
                                      "УСПЕХ ЦЕНОЙ": "получилось, но что-то потеряно навсегда",
                                      "ПРОВАЛ": "не вышло, стало хуже",
                                      "КАТАСТРОФА": "вышло хуже, чем если бы не пробовал"}.get(
                                          m.group(2).split("(")[0].strip(), "не вышло")}
                            for m in re.finditer(r"\[(.+?)\][^\n]*?-> ([^\n]+)", report)],
        "последствия": re.findall(r"ПОСЛЕДСТВИЕ: (.+)", report),
        "события_мира": [x.strip() for x in re.findall(r"^\s{2}(\[.+)$", report, re.M)
                         if not re.search(r"цель \d|бросок \d|сырая", x)],
        "обстановка": scene_context(S),
        "мёртв": S.get("status") == "dead",
        "без_сознания": S.get("status") == "unconscious",
    }
    prose_raw = llm(cfg, SYS_PROSE, json.dumps(payload, ensure_ascii=False, indent=1),
                    temperature=0.9, max_tokens=1200)
    out = json_from(prose_raw)
    out["dead"] = payload["мёртв"]
    return out


def run_engine(argv):
    """Вызов движка внутри процесса, с перехватом его отчёта."""
    buf, old = io.StringIO(), sys.stdout
    sys.argv = ["sim.py"] + argv
    sys.stdout = buf
    try:
        sim.main()
    except SystemExit:
        pass
    finally:
        sys.stdout = old
    return buf.getvalue()


def new_game(cfg, scenario):
    """Свободный текст сценария -> замысел -> валидация -> мир. С самопочинкой."""
    errors = ""
    for attempt in range(3):
        raw = llm(cfg, SYS_BRIEF,
                  f"Вводная игрока: {scenario}\nseed = {int(time.time()) % 10**7}" +
                  (f"\n\nПрошлая попытка не прошла проверку:\n{errors}\nИсправь." if errors else ""),
                  temperature=0.7, max_tokens=4000,
                  response_format=brief_response_format())
        try:
            brief = json_from(raw)
            S = sim.expand(brief)
            err, warn = sim.validate(S)
            if err:
                errors = "\n".join(err); continue
            notes = S.pop("_gen_notes", [])
            json.dump(S, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return {"ok": True, "notes": notes, "warn": warn,
                    "setting": S["meta"]["setting"], "attempt": attempt + 1}
        except Exception as e:
            errors = str(e)[:500]
    return {"ok": False, "error": errors}


# ─────────────────────────── ОКНО ───────────────────────────

PAGE = """<!doctype html><html lang=ru><meta charset=utf-8>
<title>Симулятор</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0d0e10;color:#d6d3cd;font:16px/1.65 Georgia,serif;
     display:flex;justify-content:center}
.wrap{width:min(760px,94vw);padding:28px 0 80px}
h1{font:600 15px/1 system-ui;letter-spacing:.14em;text-transform:uppercase;
   color:#6d6a64;margin:0 0 22px}
.panel{background:#131417;border:1px solid #23252a;border-radius:6px;padding:18px;margin-bottom:20px}
label{display:block;font:500 12px/1 system-ui;letter-spacing:.08em;text-transform:uppercase;
      color:#6d6a64;margin:12px 0 6px}
input,select,textarea{width:100%;background:#0d0e10;border:1px solid #2a2d33;color:#d6d3cd;
      border-radius:4px;padding:9px 11px;font:15px/1.4 Georgia,serif}
textarea{min-height:74px;resize:vertical}
.row{display:flex;gap:12px}.row>*{flex:1}
button{background:#1d2026;border:1px solid #333740;color:#d6d3cd;border-radius:4px;
       padding:11px 16px;font:15px/1.3 Georgia,serif;cursor:pointer;text-align:left;width:100%}
button:hover:not(:disabled){background:#262a32;border-color:#454a55}
button:disabled{opacity:.4;cursor:default}
.go{background:#2f3a2c;border-color:#455040;text-align:center;font-weight:600}
.scene{white-space:pre-wrap;margin:0 0 26px;padding-bottom:22px;border-bottom:1px solid #1c1e22}
.scene:last-of-type{border:0}
.opts{display:flex;flex-direction:column;gap:9px;margin-top:6px}
.opts button{display:flex;gap:11px}
.n{color:#5f6b57;font-weight:600;flex:0 0 auto}
.free{display:flex;gap:9px;margin-top:14px}.free input{flex:1}.free button{width:auto;padding:11px 20px}
.hint{color:#6d6a64;font:13px/1.5 system-ui;margin-top:10px}
.err{color:#b56b5e}
.wait{color:#6d6a64;font-style:italic}
</style>
<div class=wrap>
<h1>Симулятор</h1>

<div class=panel id=setup>
  <div class=row>
    <div><label>Провайдер</label>
      <select id=provider>
        <option value=ollama>Ollama (локально)</option>
        <option value=local>LM Studio / llama.cpp (локально)</option>
        <option value=openai>OpenAI-совместимый</option>
        <option value=anthropic>Anthropic</option>
      </select></div>
    <div><label>Модель</label><input id=model value=llama3.1></div>
  </div>
  <label>Ключ API (для локальных не нужен)</label><input id=key type=password placeholder="">
  <label>Свой адрес (необязательно)</label><input id=url placeholder="переопределить URL">
  <label>Сценарий</label>
  <textarea id=scenario placeholder="Например: попаданец в 1052 год, окраины Новгорода, при мне только то, что было в карманах"></textarea>
  <div class=hint>Мир, люди, счётчики и снаряжение сгенерируются и пройдут проверку. Если замысел не сойдётся — попыток три.</div>
  <div style=margin-top:16px><button class=go id=start>Начать игру</button></div>
  <div class=hint id=status></div>
</div>

<div id=game></div>
<div class=panel id=actions style=display:none>
  <div class=opts id=opts></div>
  <div class=free><input id=freetext placeholder="или своё действие"><button id=send>→</button></div>
</div>
</div>

<script>
const $=s=>document.querySelector(s), game=$('#game');
const cfg=()=>({provider:$('#provider').value,model:$('#model').value,
                api_key:$('#key').value,url:$('#url').value||null});

function addScene(text){const d=document.createElement('div');d.className='scene';d.textContent=text;
  game.appendChild(d);d.scrollIntoView({behavior:'smooth',block:'start'});}
function setOpts(list,dead){
  const box=$('#opts');box.innerHTML='';
  $('#actions').style.display=dead?'none':'block';
  (list||[]).forEach((t,i)=>{const b=document.createElement('button');
    b.innerHTML='<span class=n>'+(i+1)+'</span><span>'+t+'</span>';
    b.onclick=()=>turn(t);box.appendChild(b);});
}
function busy(on){document.querySelectorAll('#opts button,#send').forEach(b=>b.disabled=on);
  if(on){const d=document.createElement('div');d.className='scene wait';d.id='wait';
    d.textContent='…';game.appendChild(d);}else{const w=$('#wait');if(w)w.remove();}}

async function post(path,body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)});return r.json();}

$('#start').onclick=async()=>{
  const sc=$('#scenario').value.trim();
  if(!sc){$('#status').textContent='Опиши сценарий.';return;}
  $('#start').disabled=true;$('#status').textContent='Мир собирается и проходит проверку…';
  const r=await post('/api/new',{cfg:cfg(),scenario:sc});
  if(!r.ok){$('#status').innerHTML='<span class=err>Не вышло: '+(r.error||'')+'</span>';
    $('#start').disabled=false;return;}
  $('#setup').style.display='none';
  if(r.notes&&r.notes.length)addScene(r.notes.join('\\n'));
  turn('осмотреться');
};

async function turn(intent){
  busy(true);
  const r=await post('/api/turn',{cfg:cfg(),intent:intent});
  busy(false);
  if(r.error){addScene('Сбой: '+r.error);setOpts([]);return;}
  addScene(r.prose||'');
  setOpts(r.options,r.dead);
}
$('#send').onclick=()=>{const v=$('#freetext').value.trim();if(v){$('#freetext').value='';turn(v);}};
$('#freetext').addEventListener('keydown',e=>{if(e.key==='Enter')$('#send').click();});
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, json.dumps({"error": "плохой запрос"}))
        cfg = data.get("cfg", {})
        try:
            if self.path == "/api/new":
                res = new_game(cfg, data.get("scenario", ""))
            elif self.path == "/api/turn":
                res = play_turn(cfg, data.get("intent", ""))
            else:
                return self._send(404, "{}")
            self._send(200, json.dumps(res, ensure_ascii=False))
        except urllib.error.URLError as e:
            self._send(200, json.dumps({"error": f"модель недоступна: {e}"}, ensure_ascii=False))
        except Exception as e:
            self._send(200, json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))


def main():
    port = int(os.environ.get("PLAY_PORT", 8765))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"окно игры: {url}   (Ctrl+C чтобы закрыть)")
    try:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    except Exception:
        pass
    srv.serve_forever()


if __name__ == "__main__":
    main()
