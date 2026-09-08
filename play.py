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


# JSON Schema замысла. required заставляет LM Studio требовать ключи, не только типы.
# additionalProperties: true — свободный текст (desc_true, truths, chain[].canon) не в схеме.
#
# Прямые x["k"] без .get() — дыра в required → KeyError после валидного JSON.
# Живой список уровней: python schema_required.py [--check]. Кортежи ниже —
# то, что схема реально шлёт в LM Studio; сверка с AST не даёт им разойтись.
# carryover/loadout — после .get / `in`.
# disposition/power/stance_to_pc — `if k in` / .get, не KeyError.
# resources/structures/objects — .get; объекты ещё и строки без name.
# EXIT_REQUIRED = AST KeyError (to) ∪ validate-mandatory (travel_min, difficulty).
# Живой Qwen: опциональное числовое поле переименовывается (travel_min_min,
# difficulty_hard, «travel_min »). Не .get: validate требует ключ; схема
# заставляет LM Studio назвать его точно. schema_required --check лишний
# required не считает дырой — travel_min в AST нет (`if f not in e`).
BRIEF_EXPAND_DIRECT = (
    "seed", "setting", "ladder", "ladder_root", "physics_on",
    "start_path", "start_local", "chain", "sites",
)
BRIEF_EXPAND_GUARDED = ("carryover", "loadout")
BRIEF_REQUIRED = (
    "seed", "setting", "tech_ceiling", "ladder", "ladder_root", "physics_on",
    "start_path", "start_local", "chain", "skills", "sites", "npcs",
    "factions", "clocks", "truths",
)
SITE_REQUIRED = ("path", "name", "exits")
SITE_EXIT_ALIASES = (
    "exits_list", "exits_from_here", "exits_to", "exits_from", "exits_from_site",
)  # отказ, не синоним; имена с живых прогонов Qwen3.5 9B
EXIT_REQUIRED = ("to", "travel_min", "difficulty")
EXIT_FIELD_ALIASES = {
    "travel_min": ("travel_min_min", "travel_min_"),
    "difficulty": ("difficulty_hard", "difficulty_", "diff"),
}
CLOCK_REQUIRED = ("name", "filled", "max", "period_h", "payoff")
CLOCK_GUARDED = ("on_complete",)
# Как в worldgen.validate; путь площадки сюда не кладут — для площадки site+env.
CLOCK_PATH_ROOTS = (
    "pc", "world", "time", "envelope", "meta", "position", "profile", "calendar",
)
NPC_REQUIRED = ("id", "path")
FACTION_REQUIRED = ("id", "name")
BRIEF_FIELD_HINTS = {
    "seed": "число",
    "setting": "строка — мир одной фразой",
    "tech_ceiling": "primitive|preindustrial|industrial|spacefaring",
    "ladder": "список строк уровней от корня к мелкому",
    "ladder_root": "строка, корень пути",
    "physics_on": "список строк из фиксированного enum (холод, голод, …)",
    "start_path": "полный путь через /, первый сегмент = ladder_root, равен path одной площадки. Не |",
    "start_local": "строка — где именно стоит персонаж",
    "chain": "список узлов [{path, scale, canon, ...}] от корня до региона",
    "skills": "объект {имя: число}, например {\"survival\": 45} — не список",
    "sites": "массив [{path, name, exits, ...}]. Не sites_canon.",
    "exits": "массив [{to, travel_min, difficulty, ...}]. Не exits_list / exits_from_here / exits_to.",
    "to": "строка — путь площадки назначения",
    "travel_min": "число минут перехода, ключ ровно travel_min",
    "difficulty": "число сложности перехода, ключ ровно difficulty, не «легко»",
    "npcs": "массив [{id, path, name, ...}]",
    "factions": "массив [{id, name, ...}]",
    "clocks": "массив [{name, filled, max, period_h, payoff, ...}]",
    "truths": "массив строк — скрытые истины",
}

BRIEF_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "required": list(BRIEF_REQUIRED),
    "properties": {
        "seed": {"type": "number"},
        "setting": {"type": "string"},
        "tech_ceiling": {"type": "string"},
        "ladder": {"type": "array", "items": {"type": "string"}},
        "ladder_root": {"type": "string"},
        "start_path": {"type": "string"},
        "start_local": {"type": "string"},
        "chain": {"type": "array"},
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
                "required": list(SITE_REQUIRED),
                "properties": {
                    "path": {"type": "string"},
                    "name": {"type": "string"},
                    "exits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": list(EXIT_REQUIRED),
                            "properties": {
                                "to": {"type": "string"},
                                "difficulty": {"type": "number"},
                                "travel_min": {"type": "number"},
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
                "required": list(NPC_REQUIRED),
                "properties": {
                    "id": {"type": "string"},
                    "path": {"type": "string"},
                    "disposition": {"type": "number", "minimum": -100, "maximum": 100},
                },
            },
        },
        "factions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": list(FACTION_REQUIRED),
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "power": {"type": "number"},
                    "disposition": {"type": "number", "minimum": -100, "maximum": 100},
                    "stance_to_pc": {"type": "number", "minimum": -100, "maximum": 100},
                },
            },
        },
        "clocks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": list(CLOCK_REQUIRED),
                "properties": {
                    "name": {"type": "string"},
                    "filled": {"type": "number"},
                    "max": {"type": "number"},
                    "period_h": {"type": "number"},
                    "payoff": {"type": "string"},
                },
            },
        },
        "truths": {"type": "array", "items": {"type": "string"}},
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


def leaked_key(obj, canon, aliases=()):
    """Канона нет, но есть закрытый псевдоним или ключ с пробелами. Не синоним."""
    if not isinstance(obj, dict) or canon in obj:
        return None
    for a in aliases:
        if a in obj:
            return a
    for k in obj:
        if isinstance(k, str) and k.strip() == canon and k != canon:
            return k
    return None


def _fused_brief_key(k, where):
    """Слитый JSON в имени поля: «disposition):-20, ». Отказ, не разбор в disposition."""
    if not isinstance(k, str):
        return f"{where}: имя поля должно быть строкой"
    if ":" in k or "," in k:
        return (f"{where}: ключ «{k}» — имя поля, не слитый JSON. "
                "Пиши \"disposition\": -20 и \"alive\": true, не одно имя с двоеточием")
    if k != k.strip():
        return (f"{where}: ключ «{k}» с пробелом по краям — отказ, "
                f"не синоним «{k.strip()}»")
    return None


def _collect_fused_keys(obj, where, msgs):
    if isinstance(obj, dict):
        for k, v in obj.items():
            bad = _fused_brief_key(k, where)
            if bad:
                msgs.append(bad)
                continue
            _collect_fused_keys(v, f"{where}.{k}", msgs)
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            _collect_fused_keys(x, f"{where}[{i}]", msgs)


def _slash_path(p, where):
    """Иерархия площадок — через /. | не разделитель и не список корней счётчика."""
    if not isinstance(p, str) or not p:
        return None
    if "|" in p:
        return (f"{where} — сегменты пути через /, не |. "
                "Пример: gory/hrebet/stanciya. | не разделитель площадок.")
    return None


def _parts_form(parts, where):
    """Часть — список из 5–6 полей, размеры числа. Строка «доски» — отказ, не материал."""
    if not parts:
        return None
    if not isinstance(parts, list):
        return (f"{where}.parts — список кортежей [материал, форма, Д_см, Ш_см, В_см], "
                "не строка")
    for j, part in enumerate(parts):
        if isinstance(part, str):
            return (f"{where}.parts[{j}] — кортеж [материал, форма, Д_см, Ш_см, В_см], "
                    f"не строка «{part}»")
        if not isinstance(part, (list, tuple)):
            return f"{where}.parts[{j}] должен быть списком из 5 или 6 полей"
        if len(part) not in (5, 6):
            return f"{where}.parts[{j}]: нужно 5 или 6 полей, не {len(part)}"
        mat, form = part[0], part[1]
        if mat not in sim.MATERIALS:
            return (f"{where}.parts[{j}] материал «{mat}» не в таблице "
                    "(не синоним; имя должно совпасть с MATERIALS)")
        if form not in sim.FORMS:
            return (f"{where}.parts[{j}] форма «{form}» не в таблице "
                    "(не синоним; имя должно совпасть с FORMS)")
        for k, dim in enumerate(part[2:5], start=2):
            if isinstance(dim, bool) or not isinstance(dim, (int, float)):
                return f"{where}.parts[{j}][{k}] — число (см), не {dim!r}"
    return None


def _on_complete_form(fx, site_paths):
    """Две законные формы validate: site/sites+env или path+set/add. Иначе отказ."""
    if not isinstance(fx, dict):
        return ("должен быть объектом {site, env} / {sites, env} или {path, set} / {path, add}, "
                "не строкой")
    if fx.get("site") == "*":
        return "для всех площадок поле sites: \"*\", не site: \"*\""
    env_op = "env" in fx and ("site" in fx or "sites" in fx)
    has_set, has_add = "set" in fx, "add" in fx
    path_op = "path" in fx and (has_set or has_add) and not (has_set and has_add)
    mixed = ("path" in fx or has_set or has_add) and env_op
    if mixed or (path_op and ("site" in fx or "sites" in fx or "env" in fx)):
        return "не смешивай site/sites+env с path/set/add"
    roots = ", ".join(CLOCK_PATH_ROOTS)
    if env_op and not path_op:
        if not isinstance(fx.get("env"), dict):
            return "env должен быть объектом {поле: значение}, не строкой"
        canon = {p for p in site_paths if isinstance(p, str) and p}
        if "site" in fx:
            site = fx.get("site")
            if site != "*" and canon and site not in canon:
                return (f"площадка «{site}» нет в sites "
                        "(on_complete.site — path из замысла, не новое имя)")
        if "sites" in fx:
            sel = fx.get("sites")
            if sel != "*" and isinstance(sel, list) and canon:
                for pth in sel:
                    if pth not in canon:
                        return (f"площадка «{pth}» нет в sites "
                                "(on_complete.sites — path из замысла)")
            elif sel != "*" and not isinstance(sel, list):
                return "sites — \"*\" или список путей"
        return None
    if path_op and not env_op:
        pth = str(fx.get("path") or "")
        if "|" in pth:
            return ("path счётчика — корень.поле через точку "
                    f"(одно из: {roots}), не путь площадки и не |")
        root = pth.split(".")[0]
        if root not in CLOCK_PATH_ROOTS:
            return (f"path должен начинаться с одного из: {roots} "
                    "(точка: envelope.wind_ms; не путь площадки — для площадки site/sites+env)")
        return None
    return ("неизвестная операция — нужен site/sites+env или path+set/add "
            "(add на path — число, не {site, add:...})")


def brief_form_errors(brief):
    """Дыры формы до expand: нет ключа, утечка псевдонима. Не синоним и не физика."""
    if not isinstance(brief, dict):
        return ["замысел должен быть объектом JSON"]
    msgs = []
    _collect_fused_keys(brief, "замысел", msgs)
    leaked_sites = "sites_canon" in brief and "sites" not in brief
    if leaked_sites:
        msgs.append(
            "в твоём JSON нет обязательного поля sites, добавь его в формате: "
            "массив [{path, name, ...}]. Поле называется sites, не sites_canon — "
            "второе имя только внутри движка после генерации.")
    for k in BRIEF_REQUIRED:
        if k not in brief:
            if k == "sites" and leaked_sites:
                continue
            hint = BRIEF_FIELD_HINTS.get(k, "см. обязательные поля в инструкции")
            msgs.append(f"в твоём JSON нет обязательного поля {k}, добавь его в формате: {hint}")
    root, path = brief.get("ladder_root"), brief.get("start_path")
    bad = _slash_path(path, "start_path")
    if bad:
        msgs.append(bad)
    if isinstance(root, str) and isinstance(path, str) and root and path and "|" not in path:
        first = path.split("/")[0]
        if first != root:
            msgs.append(
                f"start_path должен начинаться с ladder_root «{root}», "
                f"сейчас первый сегмент «{first}»")
    site_paths = [s.get("path") for s in (brief.get("sites") or [])
                  if isinstance(s, dict)]
    if isinstance(path, str) and path and site_paths and path not in site_paths:
        msgs.append(
            f"start_path «{path}» должен совпадать с path одной площадки в sites")
    for i, s in enumerate(brief.get("sites") or []):
        if not isinstance(s, dict):
            continue
        bad = _slash_path(s.get("path"), f"sites[{i}].path")
        if bad:
            msgs.append(bad)
        leaked_exits = [a for a in SITE_EXIT_ALIASES if a in s]
        if leaked_exits and "exits" not in s:
            msgs.append(
                f"sites[{i}] нет поля exits, добавь его в формате: "
                "массив [{to, travel_min, difficulty, ...}]. "
                f"Поле называется exits, не {leaked_exits[0]}.")
        for k in SITE_REQUIRED:
            if k not in s:
                if k == "exits" and leaked_exits:
                    continue
                need = ", ".join(SITE_REQUIRED)
                msgs.append(f"sites[{i}] нет поля {k} (нужны {need})")
        for j, e in enumerate(s.get("exits") or []):
            if not isinstance(e, dict):
                continue
            need = ", ".join(EXIT_REQUIRED)
            for k in EXIT_REQUIRED:
                if k in e:
                    continue
                leak = leaked_key(e, k, EXIT_FIELD_ALIASES.get(k, ()))
                if leak:
                    msgs.append(
                        f"sites[{i}].exits[{j}] нет поля {k} (нужны {need}). "
                        f"Поле называется {k}, не «{leak}».")
                else:
                    msgs.append(f"sites[{i}].exits[{j}] нет поля {k} (нужны {need})")
            dest, here = e.get("to"), s.get("path")
            bad = _slash_path(dest, f"sites[{i}].exits[{j}].to")
            if bad:
                msgs.append(bad)
            if isinstance(dest, str) and isinstance(here, str) and dest and here:
                if dest.split("/")[-1] == here.split("/")[-1]:
                    msgs.append(
                        f"sites[{i}].exits[{j}] ведёт сам в себя "
                        "(to совпадает с path площадки)")
        for j, o in enumerate(s.get("objects") or []):
            if isinstance(o, dict) and o.get("parts"):
                bad = _parts_form(o.get("parts"), f"sites[{i}].objects[{j}]")
                if bad:
                    msgs.append(bad)
        for j, stc in enumerate(s.get("structures") or []):
            if isinstance(stc, str):
                msgs.append(
                    f"sites[{i}].structures[{j}] — объект с name, не строка "
                    "(строки допустимы только в objects)")
                continue
            if not isinstance(stc, dict) or not stc.get("name"):
                msgs.append(f"sites[{i}].structures[{j}] нет поля name")
                continue
            bad = _parts_form(stc.get("parts"), f"sites[{i}].structures[{j}]")
            if bad:
                msgs.append(bad)
    for i, n in enumerate(brief.get("npcs") or []):
        if not isinstance(n, dict):
            continue
        for k in NPC_REQUIRED:
            if k not in n:
                msgs.append(f"npcs[{i}] нет поля {k} (нужны id, path)")
    for i, f in enumerate(brief.get("factions") or []):
        if not isinstance(f, dict):
            continue
        for k in FACTION_REQUIRED:
            if k not in f:
                msgs.append(f"factions[{i}] нет поля {k} (нужны id, name)")
    for i, c in enumerate(brief.get("clocks") or []):
        if not isinstance(c, dict):
            continue
        for k in CLOCK_REQUIRED:
            if k not in c:
                need = ", ".join(CLOCK_REQUIRED)
                msgs.append(f"clocks[{i}] нет поля {k} (нужны {need})")
        oc = c.get("on_complete")
        if oc is None:
            continue
        if not isinstance(oc, list):
            msgs.append(f"clocks[{i}].on_complete должен быть списком объектов")
            continue
        for j, fx in enumerate(oc):
            bad = _on_complete_form(fx, site_paths)
            if bad:
                msgs.append(f"clocks[{i}].on_complete[{j}] {bad}")
    return msgs


def format_brief_error(exc):
    """Самопочинка: модели — поле и формат, не сырой traceback."""
    if isinstance(exc, json.JSONDecodeError):
        return (f"JSON не разбирается ({exc.msg}). Ключи — имена без двоеточий "
                "и запятых; внутри строк не оставляй сырые управляющие символы.")
    if isinstance(exc, KeyError):
        key = exc.args[0] if exc.args else "?"
        hint = BRIEF_FIELD_HINTS.get(key) if isinstance(key, str) else None
        if hint:
            return f"в твоём JSON нет обязательного поля {key}, добавь его в формате: {hint}"
        return str(exc)[:500]
    return str(exc)[:500]


def _llm_text(prov, data):
    if prov == "anthropic":
        return "".join(b.get("text", "") for b in data.get("content", []))
    if prov == "ollama":
        return data.get("message", {}).get("content", "") or ""
    msg = ((data.get("choices") or [{}])[0].get("message") or {})
    return msg.get("content") or ""


def _llm_finish_reason(prov, data):
    """stop / length / …  length и max_tokens — обрыв по потолку, не ошибка формата."""
    if prov == "anthropic":
        r = data.get("stop_reason") or ""
        return "length" if r == "max_tokens" else r
    if prov == "ollama":
        r = data.get("done_reason") or ""
        return "length" if r in ("length", "max_tokens") else r
    r = ((data.get("choices") or [{}])[0].get("finish_reason") or "")
    return "length" if r == "max_tokens" else r


def llm(cfg, system, user, temperature=0.2, max_tokens=1400, response_format=None):
    """Единый вызов. Возвращает (текст, finish_reason). reason «length» — обрыв."""
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
        body = {"model": model, "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
    else:  # openai-совместимые: OpenAI, LM Studio, llama.cpp, vLLM
        if key: headers["Authorization"] = f"Bearer {key}"
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                "stream": False,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if response_format:
            body["response_format"] = response_format

    # Не stream: urlopen читает тело целиком. Зацикленную генерацию нельзя
    # оборвать раньше max_tokens — только распознать постфактум.
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=cfg.get("timeout", 180)) as r:
        data = json.loads(r.read().decode("utf-8"))
    return _llm_text(prov, data), _llm_finish_reason(prov, data)


def json_looks_truncated(text, finish_reason=None):
    """Обрыв по лимиту токенов — не JSONDecodeError. Схема тут ни при чём."""
    if (finish_reason or "") in ("length", "max_tokens"):
        return True
    t = re.sub(r"```(?:json)?", "", text or "").strip()
    return not t.endswith("}")


# Живой прогон (капсула, 8000 токенов): единица «" :", " ,"» ≈ 10 символов.
# Потолок 6 из постановки эту единицу не ловит — эмпирика с лога, не впрок.
DEGENERATE_LOOP_MIN_UNIT = 2
DEGENERATE_LOOP_MAX_UNIT = 12
DEGENERATE_LOOP_REPEAT = 30
DEGENERATE_LOOP_TAIL = 1500


def detect_degenerate_loop(text):
    """Хвост из одного короткого куска ≥N раз подряд — не нехватка места."""
    s = text or ""
    if len(s) > DEGENERATE_LOOP_TAIL:
        s = s[-DEGENERATE_LOOP_TAIL:]
    min_n = DEGENERATE_LOOP_MIN_UNIT
    max_n = DEGENERATE_LOOP_MAX_UNIT
    thr = DEGENERATE_LOOP_REPEAT
    if len(s) < min_n * thr:
        return False
    for n in range(min_n, max_n + 1):
        need = n * thr
        if len(s) < need:
            continue
        limit = len(s) - need + 1
        i = 0
        while i < limit:
            unit = s[i:i + n]
            if not unit.strip():
                i += 1
                continue
            if s[i:i + need] == unit * thr:
                return True
            i += 1
    return False


def brief_generation_fault(text, finish_reason=None):
    """loop важнее length: потолок токенов цикл не лечит."""
    if detect_degenerate_loop(text):
        return "loop"
    if json_looks_truncated(text, finish_reason):
        return "truncated"
    return None


BRIEF_MAX_TOKENS_LOCAL = 65000
BRIEF_MAX_TOKENS_CLOUD = 8000
BRIEF_MAX_TOKENS = BRIEF_MAX_TOKENS_LOCAL


def brief_max_tokens(cfg):
    """Локальный хост — 65000; облако — 8000 (деньги и потолок ответа API).

    Детект цикла не читает этот лимит: сработает на любом max_tokens.
    """
    cfg = cfg or {}
    prov = cfg.get("provider", "ollama")
    url = cfg.get("url") or (PROVIDERS.get(prov) or {}).get("url") or ""
    host = url.lower()
    if "127.0.0.1" in host or "localhost" in host:
        return BRIEF_MAX_TOKENS_LOCAL
    return BRIEF_MAX_TOKENS_CLOUD
BRIEF_TRUNCATED_USER = "мир получился слишком подробным, пробую снова компактнее"
BRIEF_TRUNCATED_RETRY = (
    "твой прошлый ответ был обрублен по лимиту длины — "
    "сократи количество сайтов до 1-2 и меньше объектов на каждый"
)
BRIEF_LOOP_USER = "генерация зациклилась на битом JSON, пробую снова"
BRIEF_LOOP_RETRY = (
    "предыдущий ответ содержал повреждённый JSON-ключ и зациклился на повторении — "
    "начни заново, внимательно проверяя кавычки и скобки"
)
BRIEF_TIMEOUT_USER = "модель не ответила вовремя, пробую снова"
BRIEF_TIMEOUT_RETRY = (
    "предыдущий вызов оборвался по времени — верни компактный JSON: "
    "1–3 площадки, короткие path; ladder_root равен первому сегменту start_path "
    "теми же символами"
)
BRIEF_HTTP_USER = "сервер модели отклонил запрос, пробую снова"
BRIEF_HTTP_RETRY = (
    "предыдущий вызов вернул ошибку HTTP — верни тот же JSON-замысел, "
    "без пояснений и заборчиков"
)


def brief_transport_messages(exc):
    """Timeout / HTTP / сеть — повтор попытки, не traceback. Не форма замысла."""
    if isinstance(exc, TimeoutError):
        return BRIEF_TIMEOUT_RETRY, BRIEF_TIMEOUT_USER, "timeout"
    if isinstance(exc, urllib.error.HTTPError):
        return BRIEF_HTTP_RETRY, BRIEF_HTTP_USER, "http"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            return BRIEF_TIMEOUT_RETRY, BRIEF_TIMEOUT_USER, "timeout"
        if "timed out" in str(exc).lower() or "timed out" in str(reason).lower():
            return BRIEF_TIMEOUT_RETRY, BRIEF_TIMEOUT_USER, "timeout"
        return BRIEF_HTTP_RETRY, BRIEF_HTTP_USER, "http"
    return None


def json_from(text):
    """Модели любят обрамлять JSON болтовнёй и заборчиками. Достаём объект."""
    t = re.sub(r"```(?:json)?", "", text).strip()
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1: raise ValueError("в ответе нет JSON:\n" + text[:400])
    return json.loads(t[i:j+1])


def _need_number(val, where):
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"{where}: нужно число, не {val!r}")
    return val


# Исчерпывающие ключи объекта проверки. навык / rating — отказ, не синоним.
INTENT_CHECK_KEYS = ("skill", "difficulty", "label", "adv", "domain")
INTENT_CHECK_REQUIRED = ("skill", "difficulty", "label")


def _intent_skills(S):
    return list((S.get("pc") or {}).get("skills") or {})


def _intent_exits(S):
    site = sim.site_of(S)
    return [e["to"] for e in sim.site_exits(site)]


def _intent_domains(S):
    return list((sim.rules(S).get("consequences") or {}).keys())


def _intent_max_checks(S):
    return int((sim.rules(S).get("resolution") or {}).get("max_checks_per_turn", 2))


def mech_schema(S):
    """Схема разбора хода из текущего S. Не константа: навыки и выходы разные."""
    skills = _intent_skills(S)
    exits = _intent_exits(S)
    domains = _intent_domains(S)
    check_item = {
        "type": "object",
        "additionalProperties": False,
        "required": list(INTENT_CHECK_REQUIRED),
        "properties": {
            "skill": {"type": "string", "enum": skills} if skills else {"type": "string"},
            "difficulty": {"type": "number", "minimum": 0, "maximum": 60},
            "label": {"type": "string"},
            "adv": {"type": "number", "minimum": 0, "maximum": 25},
            "domain": {"type": "string", "enum": domains} if domains else {"type": "string"},
        },
    }
    props = {
        "impossible": {"type": "string"},
        "minutes": {"type": "number", "minimum": 0},
        "activity": {"type": "integer", "enum": [0, 1, 2]},
        "checks": {
            "type": "array",
            "maxItems": _intent_max_checks(S),
            "items": check_item,
        },
        "window": {"type": "number", "minimum": 0},
        "water": {"type": "number", "minimum": 0},
        "food": {"type": "number", "minimum": 0},
        "sheltered": {"type": "boolean"},
        "fire": {"type": "boolean"},
        "sleeping": {"type": "boolean"},
        "local": {"type": "string"},
    }
    if exits:
        props["to"] = {"type": "string", "enum": exits}
    return {"type": "object", "additionalProperties": True, "properties": props}


def mech_response_format(S):
    """response_format для openai/local. Схема собирается из S, не из константы."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "turn_intent",
            "strict": True,
            "schema": mech_schema(S),
        },
    }


def _check_from_string(raw, skills, domains):
    """Одна закрытая сериализация: навык:сложность:метка[:adv][:domain][:lethal]."""
    parts = raw.split(":")
    if len(parts) < 3:
        raise ValueError(
            "checks: строка «навык:сложность:метка[:adv][:domain][:lethal]», "
            f"не {raw!r}")
    extra = parts[6:] if len(parts) > 6 else []
    if extra:
        raise ValueError(f"checks: лишние поля в строке {raw!r}")
    if len(parts) > 5 and parts[5] not in ("", "lethal"):
        raise ValueError(f"checks: шестое поле только lethal, не {parts[5]!r}")
    skill = parts[0]
    if skill not in skills:
        raise ValueError(f"checks: навыка «{skill}» нет у этого существа")
    try:
        diff = json.loads(parts[1])
    except json.JSONDecodeError:
        raise ValueError(f"checks «{skill}»: difficulty нужно число, не {parts[1]!r}")
    diff = _need_number(diff, f"checks «{skill}»: difficulty")
    if not 0 <= diff <= 60:
        raise ValueError(f"checks «{skill}»: difficulty {diff} вне 0…60")
    label = parts[2]
    adv = 0
    if len(parts) > 3 and parts[3] != "":
        try:
            adv = json.loads(parts[3])
        except json.JSONDecodeError:
            raise ValueError(f"checks «{skill}»: adv нужно число, не {parts[3]!r}")
        adv = _need_number(adv, f"checks «{skill}»: adv")
        if not 0 <= adv <= 25:
            raise ValueError(f"checks «{skill}»: adv {adv} вне 0…25")
    domain = parts[4] if len(parts) > 4 and parts[4] else None
    if domain is not None and domains and domain not in domains:
        raise ValueError(f"checks: домен «{domain}» не из consequences")
    out = {"skill": skill, "difficulty": diff, "label": label, "adv": adv}
    if domain:
        out["domain"] = domain
    if len(parts) > 5 and parts[5] == "lethal":
        out["lethal"] = True
    return out


def _check_from_object(item, skills, domains):
    unknown = sorted(set(item) - set(INTENT_CHECK_KEYS))
    if unknown:
        raise ValueError(f"checks: неизвестные ключи {unknown}, не {INTENT_CHECK_KEYS}")
    for k in INTENT_CHECK_REQUIRED:
        if k not in item:
            raise ValueError(f"checks: нет поля {k}")
    skill = item["skill"]
    if not isinstance(skill, str) or skill not in skills:
        raise ValueError(f"checks: навыка «{skill}» нет у этого существа")
    diff = _need_number(item["difficulty"], f"checks «{skill}»: difficulty")
    if not 0 <= diff <= 60:
        raise ValueError(f"checks «{skill}»: difficulty {diff} вне 0…60")
    if not isinstance(item["label"], str):
        raise ValueError(f"checks «{skill}»: label должна быть строкой")
    out = {"skill": skill, "difficulty": diff, "label": item["label"]}
    if "adv" in item:
        adv = _need_number(item["adv"], f"checks «{skill}»: adv")
        if not 0 <= adv <= 25:
            raise ValueError(f"checks «{skill}»: adv {adv} вне 0…25")
        out["adv"] = adv
    if "domain" in item:
        domain = item["domain"]
        if not isinstance(domain, str):
            raise ValueError(f"checks «{skill}»: domain должна быть строкой")
        if domains and domain not in domains:
            raise ValueError(f"checks: домен «{domain}» не из consequences")
        out["domain"] = domain
    return out


def normalize_check(item, S):
    """Канон — объект. Строка «a:b:c» — вторая закрытая форма. Иных нет."""
    skills = _intent_skills(S)
    domains = _intent_domains(S)
    if isinstance(item, str):
        return _check_from_string(item, skills, domains)
    if isinstance(item, dict):
        return _check_from_object(item, skills, domains)
    raise ValueError(f"checks: объект или строка, не {item!r}")


def _cli_num(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def check_to_cli(c):
    """Объект проверки → argv --check. Движок и split(':') не меняем."""
    bits = [c["skill"], _cli_num(c["difficulty"]), c.get("label") or "",
            "" if not c.get("adv") else _cli_num(c["adv"]),
            c.get("domain") or ""]
    if c.get("lethal"):
        bits.append("lethal")
    return ":".join(bits)


def normalize_intent(mech, S):
    """Форма намерения → канон, или понятный отказ. Не чинит вход молча.

    minutes < 0 — ValueError, не max(0, …): обёртка не отменяет отказ движка.
    Верх minutes — физика хода, не схема: потолок абсурда не вводится впрок.
    """
    if not isinstance(mech, dict):
        raise ValueError("намерение должно быть объектом JSON")
    m = json.loads(json.dumps(mech))
    if m.get("impossible") is not None:
        if not isinstance(m["impossible"], str):
            raise ValueError("impossible должен быть строкой")
        return {"impossible": m["impossible"]}
    if "minutes" in m:
        minutes = _need_number(m["minutes"], "minutes")
        if minutes < 0:
            raise ValueError(f"minutes: нужно ≥ 0, не {minutes!r}")
        m["minutes"] = minutes
    if "activity" in m:
        act = _need_number(m["activity"], "activity")
        if act not in (0, 1, 2):
            raise ValueError(f"activity: 0, 1 или 2, не {act!r}")
        m["activity"] = int(act)
    if "window" in m:
        w = _need_number(m["window"], "window")
        if w < 0:
            raise ValueError(f"window: нужно ≥ 0, не {w!r}")
        m["window"] = w
    for k in ("water", "food"):
        if k in m:
            v = _need_number(m[k], k)
            if v < 0:
                raise ValueError(f"{k}: нужно ≥ 0, не {v!r}")
            m[k] = v
    if "to" in m and m["to"]:
        exits = _intent_exits(S)
        if m["to"] not in exits:
            raise ValueError(f"to: «{m['to']}» нет среди выходов этой площадки")
    if "checks" in m:
        if not isinstance(m["checks"], list):
            raise ValueError("checks должен быть списком")
        lim = _intent_max_checks(S)
        if len(m["checks"]) > lim:
            raise ValueError(f"checks: {len(m['checks'])} при лимите {lim}")
        m["checks"] = [normalize_check(c, S) for c in m["checks"]]
    return m


# ─────────────────────────── ПРОМПТЫ ───────────────────────────

SYS_BRIEF = """Ты — генератор миров для безжалостного симулятора выживания.
По вводной игрока верни ТОЛЬКО JSON-замысел мира, без пояснений и заборчиков.

Замысел полный: сценарий и играбельный мир. Не урезай поля «под модель».
Ключи JSON — идентификаторы без двоеточий и запятых внутри имени.
Числа — JSON-числа: "disposition": -20, "alive": true. Не ключ «disposition:-20».

Обязательные поля:
 seed (число), setting (строка), tech_ceiling (primitive|preindustrial|industrial|spacefaring),
 ladder (список уровней от корня к мелкому), ladder_root (строго первый сегмент start_path, те же символы, не «лес» vs «les»),
 physics_on (список из: холод, жара, голод, жажда, сон, раны, болезни, гипоксия,
   давление, радиация, вакуум, углекислота, невесомость, нагрузка, погода),
 start_path (путь через /; первый сегмент = ladder_root; равен path ОДНОЙ площадки в sites).
   Пример: "gory/hrebet/stanciya/apparatnaya". Не | как разделитель площадок.
 start_local, start_z, start_hour, weather, ambient_c, wind_ms,
 climate {t_min,t_max,sunrise,sunset,note}, epoch, start_date, seasons,
 needs {hunger,thirst,fatigue,cold_stress,stress} — числа 0..100,
 skills — объект {имя: число} (athletics, stealth, survival, …). Не список.
   Нормализатор ещё принимает список {name, value|level|score}; rating — отказ.
 conditions (список, можно пустой),
 chain — [{path, scale, canon}] от корня. canon — текст уровня, не имя массива площадок.
 sites — 1–3 площадки. Поле в твоём ответе называется sites, не sites_canon.
   [{path,name,z_m,desc_true,exits[{to,mode,travel_min,dz_m,difficulty,gate}],
   resources:[{name,amount,tags}], hazards, objects, touched:true}].
   Выходы площадки — поле exits, не exits_list и не exits_from_here.
   Не exits_to, не exits_from, не exits_from_site.
   У выхода ключи to, travel_min, difficulty — числа. Не travel_min_min,
   не difficulty_hard, не diff, не «легко», не ключ с пробелом.
   to не совпадает с path этой же площадки.
   objects — строки (проза) или {name, parts?, tags?}.
   parts если есть — только [["дерево","пластина",140,70,3]], не «земля»/«песок»/«брус»/«плита».
   Без parts объект не ломается. С parts — ломается по matter.
   resources с тегами, если взять можно: вода/еда/топливо (подсказка автору, не словарь ядра).
   shelter:true — помещение. hearth:true — очаг уже есть.
 npcs — 2–4 [{id,name,path,goal,disposition (число −100..100),alive:true,knows_about_pc:[],resources:[]}],
 factions — 2–3 [{id,name,goal,power,stance_to_pc,relations:{}}],
 clocks — 1–3 [{name,filled,max,period_h,payoff,on_complete}].
   on_complete — список {site, env} / {sites, env} или {path, set} / {path, add}.
   env — объект полей среды, не строка. path счётчика — одно из pc, world, time,
   envelope, meta, position, profile, calendar и поле через точку (envelope.wind_ms).
   Не путь площадки; для площадки — site/sites+env. Без on_complete счётчик только журнал.
 truths — 3–5 строк,
 opening_fact (строка),
 carryover: {"context":"auto"} если человек нашего времени попал в другой мир
   (тогда НЕ указывай worn/containers/items).

Каркас (полный; скопируй структуру, смени текст; ladder_root = первый сегмент start_path = path стартовой площадки):
{"seed":1,"setting":"окоп, 1916","tech_ceiling":"industrial",
 "ladder":["ww1","front","okop"],"ladder_root":"ww1",
 "physics_on":["холод","голод","жажда","сон","раны","нагрузка","погода"],
 "start_path":"ww1/front/okop","start_local":"на ступени окопа","start_z":180,"start_hour":6,
 "weather":"мокрый снег","ambient_c":1,"wind_ms":7,
 "climate":{"t_min":-4,"t_max":6,"sunrise":8,"sunset":16,"note":"ноябрь"},
 "epoch":"1916","start_date":"1916-11-12","seasons":["осень"],
 "needs":{"hunger":30,"thirst":35,"fatigue":50,"cold_stress":40,"stress":60},
 "skills":{"survival":40,"stealth":35,"perception":40},
 "conditions":[],
 "chain":[{"path":"ww1","scale":"театр","canon":"Западный фронт."}],
 "sites":[{"path":"ww1/front/okop","name":"Окоп","z_m":180,"desc_true":"Вода по щиколотку.",
   "exits":[{"to":"ww1/front/noman","mode":"пешком","travel_min":8,"dz_m":4,"difficulty":50,"gate":"проволока"}],
   "resources":[{"name":"кипяток","amount":2,"tags":["вода"]},{"name":"сухари","amount":3,"tags":["еда"]}],
   "hazards":["сырость"],
   "objects":["лужа",{"name":"накатник","parts":[["дерево","пластина",140,70,3]]}],
   "touched":true}],
 "npcs":[{"id":"npc_01","name":"ефрейтор","path":"ww1/front/okop","goal":"не высовываться",
   "disposition":-10,"alive":true,"knows_about_pc":[],"resources":[]}],
 "factions":[{"id":"fac_01","name":"рота","goal":"удержать участок","power":45,"stance_to_pc":-5,"relations":{}}],
 "clocks":[{"name":"ночь","filled":0,"max":12,"period_h":12,"payoff":"темнеет",
   "on_complete":[{"path":"time.light","set":"ночь"}]}],
 "truths":["Следующий залп ляжет мимо окопа.","В воде дизентерия.","Ротация отменена."],
 "opening_fact":"Лес кончился чужим окопом.","carryover":{"context":"auto"}}

ЖЁСТКО: никакого баланса под игрока. Минимум 1 выход ведёт туда, где без подготовки плохо.
Числа среды реальные. 1–3 площадки, на площадку не более 4 объектов. Богатая вводная — не весь город сразу."""

SYS_MECH = """Ты — разборщик намерений для симулятора. Верни ТОЛЬКО JSON, без пояснений.

Поля:
 minutes  — сколько реально займёт действие (осмотреться 2, обыскать 40,
            развести костёр 20, переход — по travel_min выхода, сон 480)
 activity — 0 покой, 1 ходьба/обычное, 2 тяжёлая работа
 checks   — список до ДВУХ объектов
            {skill, difficulty, label, adv?, domain?}
            skill — имя из поля «навыки» обстановки, не выдумка и не «навык»
            difficulty — число 0-60; adv — число 0-25 (инструмент, упор, свет)
            domain — из поля «домены» обстановки, не выдуманное слово
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
        "домены": _intent_domains(S),
    }


def play_turn(cfg, intent):
    S = sim.load()
    if S.get("status") == "dead":
        return {"prose": "Игра окончена.", "options": [], "dead": True}

    ctx = scene_context(S)
    mech_raw, _ = llm(cfg, SYS_MECH,
                   "Обстановка:\n" + json.dumps(ctx, ensure_ascii=False, indent=1) +
                   f"\n\nИгрок хочет: {intent}", temperature=0.15, max_tokens=600,
                   response_format=mech_response_format(S))
    try:
        m = normalize_intent(json_from(mech_raw), S)
    except ValueError as e:
        return {"prose": str(e), "options": [], "impossible": True}
    if m.get("impossible"):
        return {"prose": m["impossible"], "options": [], "impossible": True}

    args = ["act", "--minutes", str(m.get("minutes", 5)),
            "--activity", str(int(m.get("activity", 1)))]
    for c in (m.get("checks") or []):
        args += ["--check", check_to_cli(c)]
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
    prose_raw, _ = llm(cfg, SYS_PROSE, json.dumps(payload, ensure_ascii=False, indent=1),
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
    user_error = ""
    for attempt in range(3):
        try:
            raw, reason = llm(cfg, SYS_BRIEF,
                      f"Вводная игрока: {scenario}\nseed = {int(time.time()) % 10**7}" +
                      (f"\n\nПрошлая попытка не прошла проверку:\n{errors}\nИсправь." if errors else ""),
                      temperature=0.7, max_tokens=brief_max_tokens(cfg),
                      response_format=brief_response_format())
        except (TimeoutError, urllib.error.URLError) as e:
            pair = brief_transport_messages(e)
            if not pair:
                raise
            errors, user_error, _ = pair
            continue
        fault = brief_generation_fault(raw, reason)
        if fault == "loop":
            errors = BRIEF_LOOP_RETRY
            user_error = BRIEF_LOOP_USER
            continue
        if fault == "truncated":
            errors = BRIEF_TRUNCATED_RETRY
            user_error = BRIEF_TRUNCATED_USER
            continue
        try:
            brief = json_from(raw)
            gaps = brief_form_errors(brief)
            if gaps:
                errors = "\n".join(gaps); user_error = errors; continue
            S = sim.expand(brief)
            err, warn = sim.validate(S)
            if err:
                errors = "\n".join(err); user_error = errors; continue
            notes = S.pop("_gen_notes", [])
            json.dump(S, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return {"ok": True, "notes": notes, "warn": warn,
                    "setting": S["meta"]["setting"], "attempt": attempt + 1}
        except Exception as e:
            errors = format_brief_error(e)
            user_error = errors
    return {"ok": False, "error": user_error or errors}


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
