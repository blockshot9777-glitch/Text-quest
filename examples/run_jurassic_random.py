#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Случайный прогон попаданца в поздней юре. Длина — аргумент (по умолчанию 100).

Решения, которые нельзя держать только в памяти чата:

- Бой не класть в один из четырёх равновероятных слотов. Первый черновик
  (seed тот же, слот «схватиться» удалён из файла) умер на 41-м от ран у
  гнезда — дыра сценария, не движка. У NPC — скрытность, не fight.
  Следующий сеттинг с другим seed иначе снова умрёт насилием раньше,
  чем проверит жажду, сон или счётчики.
- Сон смоделирован: у пещеры shelter=true, --sleeping не требует очага.
  Записанная смерть от fatigue 100 — не «отдохнуть было нельзя», а
  приоритет слотов: пустая фляга и thirst>=40 ставят «к воде» выше
  «к укрытию», и тело не возвращается ко второму сну.
- Огонь 0 при взятом сухостое — контракт (нет igniter, нет site.hearth),
  не сломанный матчинг тега. Класть ли розжиг в дикий замысел — баланс
  генерации / SYS_BRIEF, не физика ядра.
"""
import json, os, sys, io, copy, random

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import worldgen
import engine

BRIEF = os.path.join(HERE, "brief_jurassic.json")
STATE = os.path.join(HERE, "state_jurassic.json")
LOG = os.path.join(HERE, "run_jurassic_log.json")
SUMMARY = os.path.join(HERE, "run_jurassic_summary.json")
engine.STATE = STATE
engine._RULES = None


def take_spec(st, tag, amount):
    if not tag:
        return None
    for r in st.get("resources") or []:
        if (r.get("amount") or 0) <= 0:
            continue
        if tag in (r.get("tags") or []):
            return f"{r['name']}:{amount}"
    return None


def tag_query(S, key):
    tags = engine.use_tags(S, key)
    return tags[0] if tags else None


def run_argv(argv):
    buf, old = io.StringIO(), sys.stdout
    sys.argv = ["engine.py"] + argv
    sys.stdout = buf
    try:
        engine.main()
    except SystemExit:
        pass
    finally:
        sys.stdout = old
    return buf.getvalue()


def parse_rolls(text):
    out = []
    for line in text.splitlines():
        if "->" in line and "цель" in line:
            out.append(line.strip())
    return out


def parse_events(text):
    events = []
    grab = False
    for line in text.splitlines():
        if "СОБЫТИЯ МИРА" in line:
            grab = True
            continue
        if grab:
            if line.startswith("="):
                break
            s = line.strip()
            if s:
                events.append(s)
    return events


def site(S):
    return engine.site_of(S)


def toward_shelter(st, paths, sites):
    """Прямой выход в пещеру или один шаг к площадке, с которой в неё есть выход."""
    for e in st.get("exits") or []:
        if e.get("to") in paths and str(e["to"]).endswith("/peschera"):
            return e
    for e in st.get("exits") or []:
        if e.get("to") not in paths:
            continue
        dest = next((x for x in sites if x["path"] == e["to"]), None)
        if dest and any(str(x.get("to") or "").endswith("/peschera") for x in dest.get("exits") or []):
            return e
    return None


def site_has_tag(st, tag):
    return any(tag in (r.get("tags") or []) and (r.get("amount") or 0) > 0
               for r in st.get("resources") or [])


def toward_tag(st, paths, sites, tag):
    if site_has_tag(st, tag):
        return None
    for e in st.get("exits") or []:
        if e.get("to") not in paths:
            continue
        dest = next((x for x in sites if x["path"] == e["to"]), None)
        if dest and site_has_tag(dest, tag):
            return e
    for e in st.get("exits") or []:
        if e.get("to") not in paths:
            continue
        dest = next((x for x in sites if x["path"] == e["to"]), None)
        if not dest:
            continue
        if any(site_has_tag(nxt, tag) for nxt in sites if nxt["path"] in {x.get("to") for x in dest.get("exits") or []}):
            return e
    return None


def travel_argv(S, e):
    dest = next(x for x in S["world"]["sites_canon"] if x["path"] == e["to"])
    return ["act", "--minutes", str(int(e.get("travel_min", 15))), "--activity", "1",
            "--to", e["to"], "--z", str(dest.get("z_m", S["position"]["z_m"])),
            "--check", f"athletics:{int(e.get('difficulty', 15))}:переход::движение",
            "--window", "60"]


def options(S, rng):
    if S.get("status") == "unconscious":
        wait = {"label": "Тело лежит. Время идёт.", "kind": "беспамятство",
                "argv": ["act", "--minutes", "60", "--activity", "0", "--window", "60"]}
        return [wait, wait, wait, wait]
    st = site(S)
    paths = {x["path"] for x in S["world"]["sites_canon"]}
    here = S["position"]["path"]
    indoor = bool(st.get("shelter"))
    fatigue = S["pc"]["needs"].get("fatigue", 0)
    thirst = S["pc"]["needs"].get("thirst", 0)
    drink_tag = tag_query(S, "water_tags")
    water_here = bool(drink_tag and site_has_tag(st, drink_tag))
    water_fill = engine.tagged_have_any(S, engine.use_tags(S, "water_tags"))
    need_water = thirst >= 40 and water_fill <= 1e-9
    opts = []

    look = ["act", "--minutes", "15", "--activity", "1",
            "--check", "perception:16:осмотр::восприятие", "--window", "60"]
    if indoor:
        look.append("--sheltered")
    opts.append({"label": "Осмотреться, не привлекая того, что крупнее", "kind": "осмотр", "argv": look})

    rest = ["act", "--minutes", "40", "--activity", "0", "--window", "60"]
    if indoor:
        rest.append("--sheltered")
    if engine.can_fire(S, 60):
        rest.append("--fire")
    # Сон только здесь и в fourth, когда уже в пещере. Ядро --sleeping
    # очага не требует; у peschera shelter=true. Смерть от усталости на
    # поляне — не отсутствие этой ветки, а elif need_water ниже: жажда
    # перехватывает слот и не пускает к укрытию.
    if fatigue >= 65 and indoor:
        sleep = ["act", "--minutes", "180", "--activity", "0", "--sleeping",
                 "--sheltered", "--window", "60"]
        if engine.can_fire(S, 60):
            sleep.append("--fire")
        opts.append({"label": "Забиться вглубь и попытаться уснуть", "kind": "сон", "argv": sleep})
    elif need_water and not water_here and drink_tag:
        hop_w = toward_tag(st, paths, S["world"]["sites_canon"], drink_tag)
        if hop_w:
            dest = next(x for x in S["world"]["sites_canon"] if x["path"] == hop_w["to"])
            opts.append({"label": f"К воде: {dest.get('name')}", "kind": "переход",
                         "argv": travel_argv(S, hop_w)})
        else:
            opts.append({"label": "Переждать в этом месте", "kind": "ожидание", "argv": rest})
    elif fatigue >= 80 and not indoor:
        hop = toward_shelter(st, paths, S["world"]["sites_canon"])
        if hop:
            dest = next(x for x in S["world"]["sites_canon"] if x["path"] == hop["to"])
            opts.append({"label": f"К укрытию: {dest.get('name')}", "kind": "переход",
                         "argv": travel_argv(S, hop)})
        else:
            opts.append({"label": "Переждать в этом месте", "kind": "ожидание", "argv": rest})
    else:
        opts.append({"label": "Переждать в этом месте", "kind": "ожидание", "argv": rest})

    exits = [e for e in st.get("exits", []) if e.get("to") in paths]
    rng.shuffle(exits)
    hop = None
    if need_water and not water_here and drink_tag:
        hop = toward_tag(st, paths, S["world"]["sites_canon"], drink_tag)
        hop_label = "К воде"
    elif fatigue >= 80 and not indoor:
        hop = toward_shelter(st, paths, S["world"]["sites_canon"])
        hop_label = "К укрытию"
    if hop:
        dest = next(x for x in S["world"]["sites_canon"] if x["path"] == hop["to"])
        opts.append({"label": f"{hop_label}: {dest.get('name')}", "kind": "переход",
                     "argv": travel_argv(S, hop)})
    elif exits:
        e = exits[0]
        dest = next(x for x in S["world"]["sites_canon"] if x["path"] == e["to"])
        opts.append({"label": f"Идти: {dest.get('name')}", "kind": "переход",
                     "argv": travel_argv(S, e)})
    else:
        wait = ["act", "--minutes", "20", "--activity", "1",
                "--check", "perception:20:слух::восприятие", "--window", "60"]
        if indoor:
            wait.append("--sheltered")
        opts.append({"label": "Слушать чащу", "kind": "ожидание", "argv": wait})

    npcs = [n for n in S["world"]["npcs"] if n.get("alive", True) and n.get("path") == here]
    water_fill = engine.tagged_have_any(S, engine.use_tags(S, "water_tags"))
    food_fill = engine.tagged_have_any(S, engine.use_tags(S, "food_tags"))
    n = S["pc"]["needs"]
    wounds = S["pc"].get("wounds") or []
    hostiles = [x for x in npcs if x.get("disposition", 0) <= -40]

    fourth = None
    if wounds and not wounds[0].get("treated"):
        fourth = {"label": "Попытаться перевязать рану", "kind": "лечение",
                  "argv": ["treat", "--supplies", "0"]}
    elif engine.fuel_have(S) <= 1e-9 and take_spec(st, tag_query(S, "fuel_tags"), 1):
        take = ["act", "--minutes", "10", "--activity", "1",
                "--take-resource", take_spec(st, tag_query(S, "fuel_tags"), 1),
                "--window", "30"]
        if indoor:
            take.append("--sheltered")
        fourth = {"label": "Набрать сухостоя с площадки", "kind": "добыча", "argv": take}
    elif n.get("cold_stress", 0) >= 25 and engine.can_fire(S, 60):
        fire_rest = ["act", "--minutes", "40", "--activity", "0", "--window", "60", "--fire"]
        if indoor:
            fire_rest.append("--sheltered")
        fourth = {"label": "Зажечь то, что горит, и греться", "kind": "огонь", "argv": fire_rest}
    elif n.get("fatigue", 0) >= 65 and indoor:
        sleep = ["act", "--minutes", "180", "--activity", "0", "--sleeping",
                 "--sheltered", "--window", "60"]
        if engine.can_fire(S, 60):
            sleep.append("--fire")
        fourth = {"label": "Забиться вглубь и попытаться уснуть", "kind": "сон", "argv": sleep}
    elif n.get("thirst", 0) >= 20 and water_fill > 1e-9:
        drink = ["act", "--minutes", "8", "--activity", "0", "--water", "0.4", "--window", "30"]
        if indoor:
            drink.append("--sheltered")
        fourth = {"label": "Пить то, что с собой", "kind": "питьё", "argv": drink}
    elif n.get("thirst", 0) >= 20 and take_spec(st, tag_query(S, "water_tags"), 0.5):
        take = ["act", "--minutes", "8", "--activity", "1",
                "--take-resource", take_spec(st, tag_query(S, "water_tags"), 0.5),
                "--window", "30"]
        if indoor:
            take.append("--sheltered")
        fourth = {"label": "Набрать воды из того, что есть на площадке", "kind": "добыча", "argv": take}
    elif n.get("hunger", 0) >= 20 and food_fill > 1e-9:
        eat = ["act", "--minutes", "15", "--activity", "0", "--food", "0.35", "--window", "30"]
        if indoor:
            eat.append("--sheltered")
        fourth = {"label": "Есть то, что с собой", "kind": "еда", "argv": eat}
    elif n.get("hunger", 0) >= 20 and take_spec(st, tag_query(S, "food_tags"), 1):
        take = ["act", "--minutes", "10", "--activity", "1",
                "--take-resource", take_spec(st, tag_query(S, "food_tags"), 1),
                "--window", "30"]
        if indoor:
            take.append("--sheltered")
        fourth = {"label": "Срезать мясо с площадки", "kind": "добыча", "argv": take}
    elif hostiles:
        # Не fight: равный слот боя смещает любой seed к быстрой смерти
        # от ран. Правило постоянное, см. FEATURE_GUIDE §10.
        hide = ["act", "--minutes", "20", "--activity", "1",
                "--check", "stealth:24:уйти с глаз::движение", "--window", "15"]
        fourth = {"label": "Не схватываться: замереть и отползти", "kind": "скрытность", "argv": hide}
    if fourth is None:
        hide = ["act", "--minutes", "25", "--activity", "1",
                "--check", "stealth:22:укрытие::движение", "--window", "20"]
        if indoor:
            hide.append("--sheltered")
        fourth = {"label": "Замереть в заросли, не шуметь", "kind": "скрытность", "argv": hide}
    opts.append(fourth)
    assert len(opts) == 4, len(opts)
    return opts


def snapshot_pc(S):
    e = S.get("envelope") or {}
    env = {}
    for k in ("ambient_c", "windchill_c", "pressure_atm", "po2_kpa", "pco2_kpa",
              "dose_rate_msv_h", "dose_sv", "breathable", "wind_ms"):
        if k in e and e[k] is not None:
            v = e[k]
            env[k] = round(float(v), 4) if isinstance(v, (int, float)) else v
    return {
        "turn": S["meta"]["turn"],
        "t_h": round(S["time"]["t_h"], 2),
        "light": S["time"].get("light"),
        "weather": S["time"].get("weather"),
        "path": S["position"]["path"],
        "local": S["position"]["local"],
        "site": site(S).get("name"),
        "status": S.get("status"),
        "needs": {k: round(float(v), 2) for k, v in S["pc"]["needs"].items()},
        "vitals": {k: round(float(v), 3) if isinstance(v, (int, float)) else v
                   for k, v in S["pc"]["vitals"].items()},
        "envelope": env,
        "climate": dict(S["world"].get("climate") or {}),
        "skills": dict(S["pc"].get("skills") or {}),
        "symptoms": engine.symptoms(S),
        "wounds": copy.deepcopy(S["pc"].get("wounds", [])),
        "clocks": [{"name": c["name"], "filled": c["filled"], "max": c["max"],
                    "hidden": c.get("hidden"), "fired": bool(c.get("fired"))} for c in S["clocks"]],
        "npcs_here": [n["name"] for n in S["world"]["npcs"]
                      if n.get("alive", True) and n["path"] == S["position"]["path"]],
        "gear": [f"{i['name']} ({i.get('in')})" for i in S["items"]],
        "items": [{"name": i["name"], "tags": i.get("tags") or [], "fill": i.get("fill"),
                   "charge_pct": i.get("charge_pct"), "in": i.get("in")} for i in S["items"]],
        "site_resources": [{"name": r.get("name"), "amount": r.get("amount")}
                           for r in (site(S).get("resources") or [])],
        "carryover_ctx": next((c for c in S["pc"].get("conditions", []) if "перенесён" in c), None),
    }


def summarize(history):
    turns = history.get("turns") or []
    kinds, sites = {}, {}
    clocks_fired, takes, drinks, fires, fights, refuses = [], 0, 0, 0, 0, 0
    for rec in turns:
        kinds[rec["kind"]] = kinds.get(rec["kind"], 0) + 1
        sites[rec["after"]["site"]] = sites.get(rec["after"]["site"], 0) + 1
        if rec.get("refused"):
            refuses += 1
        if rec["kind"] == "добыча":
            takes += 1
        if rec["kind"] == "питьё":
            drinks += 1
        if rec["kind"] == "бой":
            fights += 1
        if rec["kind"] == "огонь" or "--fire" in (rec.get("argv") or []):
            fires += 1
        for ev in rec.get("events") or []:
            if "СЧЁТЧИК СРАБОТАЛ" in ev:
                clocks_fired.append({"n": rec["n"], "ev": ev})
    fin = history.get("final") or {}
    return {
        "turns_done": len(turns),
        "ended": history.get("ended"),
        "t_h": fin.get("t_h"),
        "status": fin.get("status"),
        "site": fin.get("site"),
        "needs": fin.get("needs"),
        "vitals": fin.get("vitals"),
        "envelope": fin.get("envelope"),
        "climate": fin.get("climate"),
        "kinds": kinds,
        "sites": sites,
        "take": takes,
        "drink": drinks,
        "fire": fires,
        "fight": fights,
        "refused": refuses,
        "clock_events": clocks_fired,
        "clocks": fin.get("clocks"),
        "items": fin.get("items"),
        "skills": fin.get("skills"),
        "carryover_ctx": fin.get("carryover_ctx"),
        "wounds": fin.get("wounds"),
    }


def main():
    turns_n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    brief = json.load(open(BRIEF, encoding="utf-8"))
    S0 = worldgen.expand(brief)
    err, warn = worldgen.validate(S0)
    notes = S0.pop("_gen_notes", [])
    if err:
        print("ОШИБКИ ГЕНЕРАЦИИ:")
        for e in err:
            print(" ", e)
        sys.exit(1)
    json.dump(S0, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rng = random.Random(brief["seed"])
    history = {
        "setting": brief["setting"],
        "seed": brief["seed"],
        "turns_planned": turns_n,
        "gen_notes": notes,
        "gen_warn": warn,
        "start": snapshot_pc(engine.load()),
        "turns": [],
        "ended": None,
    }
    width = max(2, len(str(turns_n)))
    for i in range(1, turns_n + 1):
        S = engine.load()
        if S.get("status") == "dead":
            history["ended"] = {"at_planned_turn": i, "status": S.get("status"), "reason": "уже мёртв до хода"}
            break
        opts = options(S, rng)
        pick = rng.randrange(4)
        chosen = opts[pick]
        report = run_argv(chosen["argv"])
        S2 = engine.load()
        refused = "ОТКАЗ" in report[:400]
        rec = {
            "n": i,
            "options": [o["label"] for o in opts],
            "picked": pick,
            "chosen": chosen["label"],
            "kind": chosen["kind"],
            "argv": chosen["argv"],
            "refused": refused,
            "rolls": parse_rolls(report),
            "events": parse_events(report),
            "after": snapshot_pc(S2),
        }
        history["turns"].append(rec)
        n = S2["pc"]["needs"]
        e = S2.get("envelope") or {}
        print(f"ход {i:0{width}d} [{chosen['kind']}] {chosen['label']} -> {S2.get('status')} "
              f"{S2['position']['path'].split('/')[-1]} "
              + ",".join(f"{k[0]}={v:.0f}" for k, v in n.items())
              + f" T={e.get('ambient_c', '—')} wc={e.get('windchill_c', '—')} "
              + f"wind={e.get('wind_ms', '—')} {S2['time'].get('weather')}")
        if S2.get("status") == "dead":
            history["ended"] = {"at_planned_turn": i, "status": S2.get("status")}
            break
    else:
        history["ended"] = {"at_planned_turn": turns_n, "status": engine.load().get("status"),
                            "reason": f"лимит {turns_n} ходов"}

    history["final"] = snapshot_pc(engine.load())
    history["summary"] = summarize(history)
    json.dump(history, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(history["summary"], open(SUMMARY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("записано:", LOG)
    print("сводка:", SUMMARY)
    print("состояние:", STATE)
    print("генерация:", notes)
    print("замечания:", warn)
    print("итог:", history["ended"])
    print("сводка:", json.dumps(history["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
