#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""100 ходов: попаданец с амнезией на дрейфующем малом корабле. Вариант каждый ход — случайный."""
import json, os, sys, io, copy, random

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import worldgen
import engine

BRIEF = os.path.join(HERE, "brief_drift.json")
STATE = os.path.join(HERE, "state_drift.json")
LOG = os.path.join(HERE, "run_drift_log.json")
engine.STATE = STATE
engine._RULES = None


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


def options(S, rng):
    st = site(S)
    paths = {x["path"] for x in S["world"]["sites_canon"]}
    here = S["position"]["path"]
    indoor = True
    opts = []

    look = ["act", "--minutes", "15", "--activity", "1",
            "--check", "perception:16:осмотр::восприятие", "--window", "60", "--sheltered"]
    opts.append({"label": "Осмотреться, держась за скобу", "kind": "осмотр", "argv": look})

    rest = ["act", "--minutes", "40", "--activity", "0", "--window", "60", "--sheltered"]
    opts.append({"label": "Переждать в этом отсеке", "kind": "ожидание", "argv": rest})

    exits = [e for e in st.get("exits", []) if e.get("to") in paths]
    rng.shuffle(exits)
    if exits:
        e = exits[0]
        dest = next(x for x in S["world"]["sites_canon"] if x["path"] == e["to"])
        args = ["act", "--minutes", str(int(e.get("travel_min", 8))), "--activity", "1",
                "--to", e["to"], "--z", str(dest.get("z_m", S["position"]["z_m"])),
                "--check", f"athletics:{int(e.get('difficulty', 15))}:переход::движение",
                "--window", "60", "--sheltered"]
        opts.append({"label": f"Лезть: {dest.get('name')}", "kind": "переход", "argv": args})
    else:
        opts.append({
            "label": "Держаться за скобу и слушать корпус",
            "kind": "ожидание",
            "argv": ["act", "--minutes", "20", "--activity", "1",
                     "--check", "perception:18:слух::восприятие", "--window", "60", "--sheltered"],
        })

    n, v = S["pc"]["needs"], S["pc"]["vitals"]
    wounds = S["pc"].get("wounds") or []
    water = [i for i in S["items"] if "вода" in i.get("tags", [])]
    food = [i for i in S["items"] if "еда" in i.get("tags", [])]
    name = st.get("name")

    fourth = None
    if wounds and not wounds[0].get("treated"):
        fourth = {"label": "Попытаться перевязать рану", "kind": "лечение",
                  "argv": ["treat", "--supplies", "0"]}
    elif n.get("fatigue", 0) >= 70:
        fourth = {"label": "Пристегнуться к койке и попытаться уснуть", "kind": "сон",
                  "argv": ["act", "--minutes", "180", "--activity", "0", "--sleeping",
                           "--sheltered", "--window", "60"]}
    elif water and n.get("thirst", 0) >= 20:
        fourth = {"label": "Пить то, что с собой", "kind": "питьё",
                  "argv": ["act", "--minutes", "8", "--activity", "0", "--water", "0.4",
                           "--sheltered", "--window", "30"]}
    elif food and n.get("hunger", 0) >= 20:
        fourth = {"label": "Есть то, что с собой", "kind": "еда",
                  "argv": ["act", "--minutes", "15", "--activity", "0", "--food", "0.35",
                           "--sheltered", "--window", "30"]}
    elif name in ("Рубка", "Машинный"):
        fourth = {"label": "Ковыряться в неподписанной панели", "kind": "ремонт",
                  "argv": ["act", "--minutes", "25", "--activity", "1",
                           "--check", "craft:24:панель::точная", "--window", "40", "--sheltered"]}
    if fourth is None:
        fourth = {"label": "Закрепиться у поручня, переждать кувырок", "kind": "удержание",
                  "argv": ["act", "--minutes", "20", "--activity", "1",
                           "--check", "athletics:16:поручень::движение", "--window", "20",
                           "--sheltered"]}
    opts.append(fourth)
    assert len(opts) == 4, len(opts)
    return opts


def snapshot_pc(S):
    e = S.get("envelope") or {}
    env = {}
    for k in ("ambient_c", "windchill_c", "pressure_atm", "po2_kpa", "pco2_kpa",
              "dose_rate_msv_h", "dose_sv", "breathable"):
        if k in e and e[k] is not None:
            v = e[k]
            env[k] = round(float(v), 4) if isinstance(v, (int, float)) else v
    return {
        "turn": S["meta"]["turn"],
        "t_h": round(S["time"]["t_h"], 2),
        "light": S["time"].get("light"),
        "path": S["position"]["path"],
        "local": S["position"]["local"],
        "site": site(S).get("name"),
        "status": S["status"],
        "needs": {k: round(float(v), 2) for k, v in S["pc"]["needs"].items()},
        "vitals": {k: round(float(v), 3) if isinstance(v, (int, float)) else v
                   for k, v in S["pc"]["vitals"].items()},
        "envelope": env,
        "skills": dict(S["pc"].get("skills") or {}),
        "symptoms": engine.symptoms(S),
        "wounds": copy.deepcopy(S["pc"].get("wounds", [])),
        "clocks": [{"name": c["name"], "filled": c["filled"], "max": c["max"],
                    "hidden": c.get("hidden")} for c in S["clocks"]],
        "gear": [f"{i['name']} ({i.get('in')})" for i in S["items"]],
        "carryover_ctx": next((c for c in S["pc"].get("conditions", []) if "перенесён" in c or "амнезия" in c), None),
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
    for i in range(1, 101):
        S = engine.load()
        if S.get("status") != "alive":
            history["ended"] = {"at_planned_turn": i, "status": S.get("status"), "reason": "уже не alive до хода"}
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
        print(f"ход {i:02d} [{chosen['kind']}] {chosen['label']} -> {S2.get('status')} "
              f"{S2['position']['path'].split('/')[-1]} "
              + ",".join(f"{k[0]}={v:.0f}" for k, v in n.items())
              + f" pO2={e.get('po2_kpa', '—')} pCO2={e.get('pco2_kpa', '—')} "
              + f"T={e.get('ambient_c', '—')} dose={e.get('dose_sv', 0)}")
        if S2.get("status") != "alive":
            history["ended"] = {"at_planned_turn": i, "status": S2.get("status")}
            break
    else:
        history["ended"] = {"at_planned_turn": 100, "status": engine.load().get("status"), "reason": "лимит 100 ходов"}

    history["final"] = snapshot_pc(engine.load())
    json.dump(history, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("записано:", LOG)
    print("состояние:", STATE)
    print("генерация:", notes)
    print("замечания:", warn)
    print("итог:", history["ended"])


if __name__ == "__main__":
    main()
