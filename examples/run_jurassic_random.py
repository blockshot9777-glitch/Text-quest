#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Осмысленный прогон попаданца в поздней юре. Длина — аргумент (по умолчанию 100).

Не RNG из четырёх равных слотов: один ход — одно действие по нужде.
Не выдумывает зажигалку, очаг, бой и материал, которого нет в данных.
Бой в набор не входит (черновик на 41-м — дыра сценария).
take сначала наполняет предмет с тем же тегом и fill<1.
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
    for e in engine.site_exits(st):
        if e.get("to") in paths and str(e["to"]).endswith("/peschera"):
            return e
    for e in engine.site_exits(st):
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
    for e in engine.site_exits(st):
        if e.get("to") not in paths:
            continue
        dest = next((x for x in sites if x["path"] == e["to"]), None)
        if dest and site_has_tag(dest, tag):
            return e
    for e in engine.site_exits(st):
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


def object_with_parts(st):
    for o in engine.site_objects(st):
        if o.get("parts"):
            return o
    return None


def shelter_argv(S, minutes, sleeping=False, activity=0):
    argv = ["act", "--minutes", str(minutes), "--activity", str(activity), "--window", "60"]
    if engine.is_sheltered(S):
        argv.append("--sheltered")
    if sleeping:
        argv.append("--sleeping")
    if engine.can_fire(S, 60):
        argv.append("--fire")
    return argv


def hands_have_slot(S):
    h = S["gear"]["hands"]
    return len(h.get("held") or []) < int(h.get("slots") or 2)


def bag_can_hold(S, it):
    bag = next((c for c in S["gear"]["containers"] if c.get("id") != "cnt_00"), None)
    if not bag or not it:
        return False, None
    inside = [x for x in S["items"] if x.get("in") == bag["id"]]
    vol = sum((x.get("l") or 0) * x.get("qty", 1) for x in inside) + (it.get("l") or 0)
    mas = sum((x.get("kg") or 0) * x.get("qty", 1) for x in inside) + (it.get("kg") or 0)
    cap_l, cap_kg = bag.get("cap_l"), bag.get("cap_kg")
    if cap_l and vol > cap_l * (1.3 if not bag.get("rigid") else 1.0):
        return False, None
    if cap_kg and mas > cap_kg:
        return False, None
    return True, bag


def can_refill(S, tag):
    return bool(tag and engine.fillable_items(S, [tag]))


def stow_empty_tagged(S, tags):
    """Убрать пустую тару с рук, если сумка примет — чтобы взять другой ресурс."""
    tags = set(tags or [])
    if not tags:
        return None
    for iid in S["gear"]["hands"].get("held") or []:
        it = next((x for x in S["items"] if x.get("id") == iid), None)
        if not it:
            continue
        if not (tags & set(it.get("tags") or [])):
            continue
        fill = it.get("fill")
        if fill is None or fill > 1e-9:
            continue
        ok, bag = bag_can_hold(S, it)
        if not ok:
            continue
        return {"label": "Убрать пустую тару с рук", "kind": "укладка",
                "argv": ["act", "--minutes", "2", "--activity", "0",
                         "--stow", f"{iid}:{bag['id']}", "--window", "30"]}
    return None


def try_build_shelter(S, st):
    """Собрать укрытие только из объекта с parts в данных. Состав не выдумывается."""
    tags = engine.structure_role_tags(S, "shelter_tags")
    if not tags or not engine.structure_use(S).get("hours_per_l"):
        return None
    if engine.is_sheltered(S) or engine.structure_has_any_tag(st, tags):
        return None
    obj = object_with_parts(st)
    if not obj:
        return None
    tech = S.get("profile", {}).get("tech_ceiling", "industrial")
    try:
        it = engine._assemble_parts(S, "заслон", obj["parts"], tags, tech)
    except (KeyError, ValueError):
        return None
    hours = engine.build_hours(S, it.get("l") or 0)
    if hours is None:
        return None
    why = engine.build_refuse(S, "заслон", [], tags, obj["name"], hours * 60 + 1, None)
    if why:
        return None
    return {"label": f"Сложить заслон из «{obj['name']}»", "kind": "сборка",
            "argv": ["act", "--minutes", str(int(hours * 60) + 1), "--activity", "2",
                     "--build", "заслон", "--from-object", obj["name"],
                     "--build-tag", tags[0], "--window", "60"]}


def decide(S):
    """Одно действие: что сейчас закрывает нужду из того, что есть. Без боя и выдумок."""
    if S.get("status") == "unconscious":
        return {"label": "Тело лежит. Время идёт.", "kind": "беспамятство",
                "argv": ["act", "--minutes", "60", "--activity", "0", "--window", "60"]}
    st = site(S)
    paths = {x["path"] for x in S["world"]["sites_canon"]}
    here = S["position"]["path"]
    indoor = engine.is_sheltered(S)
    n = S["pc"]["needs"]
    fatigue = n.get("fatigue", 0)
    thirst = n.get("thirst", 0)
    hunger = n.get("hunger", 0)
    drink_tag = tag_query(S, "water_tags")
    food_tag = tag_query(S, "food_tags")
    water_here = bool(drink_tag and site_has_tag(st, drink_tag))
    food_here = bool(food_tag and site_has_tag(st, food_tag))
    water_fill = engine.tagged_have_any(S, engine.use_tags(S, "water_tags"))
    food_fill = engine.tagged_have_any(S, engine.use_tags(S, "food_tags"))
    wounds = S["pc"].get("wounds") or []
    hostiles = [x for x in S["world"]["npcs"]
                if x.get("alive", True) and x.get("path") == here and x.get("disposition", 0) <= -40]

    if wounds and not wounds[0].get("treated"):
        return {"label": "Попытаться перевязать рану", "kind": "лечение",
                "argv": ["treat", "--supplies", "0"]}
    if hostiles:
        leave = None
        for e in engine.site_exits(st):
            if e.get("to") in paths and not str(e["to"]).endswith("/gnezdo"):
                leave = e
                break
        if leave:
            dest = next(x for x in S["world"]["sites_canon"] if x["path"] == leave["to"])
            return {"label": f"Уйти с глаз: {dest.get('name')}", "kind": "переход",
                    "argv": travel_argv(S, leave)}
        return {"label": "Не схватываться: замереть и отползти", "kind": "скрытность",
                "argv": ["act", "--minutes", "20", "--activity", "1",
                         "--check", "stealth:24:уйти с глаз::движение", "--window", "15"]}

    if thirst >= 22 and water_fill > 1e-9:
        return {"label": "Пить то, что с собой", "kind": "питьё",
                "argv": shelter_argv(S, 8) + ["--water", "0.4"]}
    if fatigue >= 65 and indoor:
        return {"label": "Спать в укрытии", "kind": "сон",
                "argv": shelter_argv(S, 180, sleeping=True)}
    if fatigue >= 70 and not indoor:
        built = try_build_shelter(S, st)
        if built:
            return built
        hop = toward_shelter(st, paths, S["world"]["sites_canon"])
        if hop:
            dest = next(x for x in S["world"]["sites_canon"] if x["path"] == hop["to"])
            return {"label": f"К укрытию: {dest.get('name')}", "kind": "переход",
                    "argv": travel_argv(S, hop)}
    water_spec = take_spec(st, drink_tag, 0.5)
    if thirst >= 22 and water_fill < 0.25 and water_spec and (can_refill(S, drink_tag) or hands_have_slot(S)):
        return {"label": "Набрать воды из того, что есть на площадке", "kind": "добыча",
                "argv": shelter_argv(S, 8, activity=1) + ["--take-resource", water_spec]}
    if not hands_have_slot(S) and not can_refill(S, drink_tag) and thirst >= 22:
        stow = stow_empty_tagged(S, engine.use_tags(S, "water_tags"))
        if stow:
            return stow

    if hunger >= 22 and food_fill > 1e-9:
        return {"label": "Есть то, что с собой", "kind": "еда",
                "argv": shelter_argv(S, 15) + ["--food", "0.35"]}
    food_spec = take_spec(st, food_tag, 1)
    if hunger >= 22 and food_spec and not hostiles and (can_refill(S, food_tag) or hands_have_slot(S)):
        return {"label": "Срезать мясо с площадки", "kind": "добыча",
                "argv": shelter_argv(S, 10, activity=1) + ["--take-resource", food_spec]}

    if thirst >= 40 and not water_here and drink_tag and water_fill <= 1e-9:
        hop = toward_tag(st, paths, S["world"]["sites_canon"], drink_tag)
        if hop:
            dest = next(x for x in S["world"]["sites_canon"] if x["path"] == hop["to"])
            return {"label": f"К воде: {dest.get('name')}", "kind": "переход",
                    "argv": travel_argv(S, hop)}

    if hunger >= 40 and not food_here and food_tag and food_fill <= 1e-9:
        hop = toward_tag(st, paths, S["world"]["sites_canon"], food_tag)
        dest_st = None
        if hop:
            dest_st = next(x for x in S["world"]["sites_canon"] if x["path"] == hop["to"])
        nest_here = any(n.get("alive", True) and n.get("path") == (hop or {}).get("to")
                        and n.get("disposition", 0) <= -40 for n in S["world"]["npcs"])
        if hop and dest_st and not nest_here:
            return {"label": f"К еде: {dest_st.get('name')}", "kind": "переход",
                    "argv": travel_argv(S, hop)}

    if n.get("cold_stress", 0) >= 25 and engine.can_fire(S, 60):
        return {"label": "Жечь то, что горит, и греться", "kind": "огонь",
                "argv": shelter_argv(S, 40)}

    if not indoor:
        built = try_build_shelter(S, st)
        if built and (fatigue >= 45 or S["time"].get("weather") in ("дождь", "морось", "мокрый снег")):
            return built

    return {"label": "Переждать в этом месте", "kind": "ожидание",
            "argv": shelter_argv(S, 40)}


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
    builds, breaks = 0, 0
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
        if rec["kind"] == "сборка":
            builds += 1
        if rec["kind"] == "разбор":
            breaks += 1
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
        "build": builds,
        "break": breaks,
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
        chosen = decide(S)
        pick = 0
        opts = [chosen]
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
