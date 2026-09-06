#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""30 ходов: попаданец, Петроград, февраль 1917. Вариант каждый ход — случайный."""
import json, os, sys, io, copy, random

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import worldgen
import engine

BRIEF = os.path.join(HERE, "brief_1917.json")
STATE = os.path.join(HERE, "state_1917.json")
LOG = os.path.join(HERE, "run_1917_log.json")
engine.STATE = STATE
engine._RULES = None


def take_spec(st, tag, amount):
    for r in st.get("resources") or []:
        if (r.get("amount") or 0) <= 0:
            continue
        if tag in (r.get("tags") or []) or tag in (r.get("name") or "").lower():
            return f"{r['name']}:{amount}"
    return None


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
        if line.startswith("СОБЫТИЯ МИРА") or "СОБЫТИЯ МИРА" in line:
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


def options(S, rng):
    if S.get("status") == "unconscious":
        wait = {"label": "Тело лежит. Время идёт.", "kind": "беспамятство",
                "argv": ["act", "--minutes", "60", "--activity", "0", "--window", "60"]}
        return [wait, wait, wait, wait]
    st = site(S)
    paths = {x["path"] for x in S["world"]["sites_canon"]}
    here = S["position"]["path"]
    indoor = bool(st.get("shelter"))
    opts = []

    opts.append({
        "label": "Осмотреться, не привлекая внимания",
        "kind": "осмотр",
        "argv": ["act", "--minutes", "15", "--activity", "1",
                 "--check", "perception:16:осмотр::восприятие", "--window", "60"]
                 + (["--sheltered"] if indoor else []),
    })

    rest = ["act", "--minutes", "40", "--activity", "0", "--window", "60"]
    if indoor:
        rest.append("--sheltered")
    if engine.can_fire(S, 60):
        rest.append("--fire")
    opts.append({"label": "Переждать в этом месте", "kind": "ожидание", "argv": rest})

    exits = [e for e in st.get("exits", []) if e.get("to") in paths]
    rng.shuffle(exits)
    if exits:
        e = exits[0]
        dest = next(x for x in S["world"]["sites_canon"] if x["path"] == e["to"])
        args = ["act", "--minutes", str(int(e.get("travel_min", 15))), "--activity", "1",
                "--to", e["to"], "--z", str(dest.get("z_m", S["position"]["z_m"])),
                "--check", f"athletics:{int(e.get('difficulty', 15))}:переход::{'движение'}",
                "--window", "60"]
        opts.append({"label": f"Идти: {dest.get('name')}", "kind": "переход", "argv": args})
    else:
        opts.append({
            "label": "Топтаться на месте, слушать улицу",
            "kind": "ожидание",
            "argv": ["act", "--minutes", "20", "--activity", "1",
                     "--check", "perception:20:слух::восприятие", "--window", "60"],
        })

    npcs = [n for n in S["world"]["npcs"] if n.get("alive", True) and n.get("path") == here]
    water_fill = engine.tagged_have(S, "вода")
    food_fill = engine.tagged_have(S, "еда")
    n, v = S["pc"]["needs"], S["pc"]["vitals"]
    wounds = S["pc"].get("wounds") or []

    fourth = None
    if wounds and not wounds[0].get("treated"):
        fourth = {"label": "Попытаться перевязать рану", "kind": "лечение", "argv": ["treat", "--supplies", "0"]}
    elif engine.fuel_have(S) <= 1e-9 and take_spec(st, "топливо", 1):
        fourth = {"label": "Набрать дров с площадки", "kind": "добыча",
                  "argv": ["act", "--minutes", "10", "--activity", "1",
                           "--take-resource", take_spec(st, "топливо", 1),
                           "--window", "30"] + (["--sheltered"] if indoor else [])}
    elif n.get("cold_stress", 0) >= 25 and engine.can_fire(S, 60):
        fire_rest = ["act", "--minutes", "40", "--activity", "0", "--window", "60", "--fire"]
        if indoor:
            fire_rest.append("--sheltered")
        fourth = {"label": "Кормить огонь и греться", "kind": "огонь", "argv": fire_rest}
    elif n.get("fatigue", 0) >= 70 and indoor:
        sleep = ["act", "--minutes", "180", "--activity", "0", "--sleeping", "--sheltered", "--window", "60"]
        if engine.can_fire(S, 60):
            sleep.append("--fire")
        fourth = {"label": "Попытаться уснуть", "kind": "сон", "argv": sleep}
    elif n.get("thirst", 0) >= 20 and water_fill > 1e-9:
        fourth = {"label": "Пить то, что с собой", "kind": "питьё",
                  "argv": ["act", "--minutes", "8", "--activity", "0", "--water", "0.4", "--sheltered", "--window", "30"]}
    elif n.get("thirst", 0) >= 20 and take_spec(st, "вода", 0.5):
        fourth = {"label": "Набрать воды из того, что есть на площадке", "kind": "добыча",
                  "argv": ["act", "--minutes", "8", "--activity", "1",
                           "--take-resource", take_spec(st, "вода", 0.5),
                           "--sheltered", "--window", "30"]}
    elif n.get("hunger", 0) >= 20 and food_fill > 1e-9:
        fourth = {"label": "Есть то, что с собой", "kind": "еда",
                  "argv": ["act", "--minutes", "15", "--activity", "0", "--food", "0.35", "--window", "30"]}
    elif n.get("hunger", 0) >= 20 and take_spec(st, "еда", 1):
        fourth = {"label": "Взять еду с площадки", "kind": "добыча",
                  "argv": ["act", "--minutes", "10", "--activity", "1",
                           "--take-resource", take_spec(st, "еда", 1), "--window", "30"]}
    elif npcs:
        foe = npcs[0]
        if foe.get("disposition", 0) <= -40 and st.get("name") == "Участок околоточных":
            fourth = {"label": f"Схватиться с {foe['name']}", "kind": "бой",
                      "argv": ["fight", "--skill", "combat", "--foe", f"{foe['name']}:40:8:2"]}
        else:
            talk = ["act", "--minutes", "20", "--activity", "0" if indoor else "1",
                    "--check", "social:22:разговор::социальное", "--window", "60"]
            if indoor:
                talk.append("--sheltered")
            fourth = {"label": f"Заговорить с {foe['name']}", "kind": "социальное", "argv": talk}
    if fourth is None:
        fourth = {"label": "Спрятаться, переждать чужие глаза", "kind": "скрытность",
                  "argv": ["act", "--minutes", "25", "--activity", "1",
                           "--check", "stealth:20:укрытие::движение", "--window", "20"]
                           + (["--sheltered"] if indoor else [])}
    opts.append(fourth)

    assert len(opts) == 4, len(opts)
    return opts


def snapshot_pc(S):
    return {
        "turn": S["meta"]["turn"],
        "t_h": round(S["time"]["t_h"], 2),
        "light": S["time"].get("light"),
        "weather": S["time"].get("weather"),
        "path": S["position"]["path"],
        "local": S["position"]["local"],
        "site": site(S).get("name"),
        "status": S["status"],
        "needs": {k: round(float(v), 2) for k, v in S["pc"]["needs"].items()},
        "vitals": {k: round(float(v), 3) if isinstance(v, (int, float)) else v
                   for k, v in S["pc"]["vitals"].items()},
        "symptoms": engine.symptoms(S),
        "wounds": copy.deepcopy(S["pc"].get("wounds", [])),
        "clocks": [{"name": c["name"], "filled": c["filled"], "max": c["max"]} for c in S["clocks"]],
        "npcs_here": [n["name"] for n in S["world"]["npcs"]
                      if n.get("alive", True) and n["path"] == S["position"]["path"]],
        "gear": [f"{i['name']} ({i.get('in')})" for i in S["items"]],
        "carryover_ctx": next((c for c in S["pc"].get("conditions", []) if "перенесён" in c), None),
    }


def main():
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
        "gen_notes": notes,
        "gen_warn": warn,
        "start": snapshot_pc(engine.load()),
        "turns": [],
        "ended": None,
    }
    for i in range(1, 31):
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
        print(f"ход {i:02d} [{chosen['kind']}] {chosen['label']} -> {S2.get('status')} "
              f"{S2['position']['path'].split('/')[-1]} needs "
              + ",".join(f"{k[0]}={v:.0f}" for k, v in S2["pc"]["needs"].items()))
        if S2.get("status") == "dead":
            history["ended"] = {"at_planned_turn": i, "status": S2.get("status")}
            break
    else:
        history["ended"] = {"at_planned_turn": 30, "status": engine.load().get("status"), "reason": "лимит 30 ходов"}

    history["final"] = snapshot_pc(engine.load())
    json.dump(history, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("записано:", LOG)
    print("состояние:", STATE)
    print("генерация:", notes)
    print("замечания:", warn)
    print("итог:", history["ended"])


if __name__ == "__main__":
    main()
