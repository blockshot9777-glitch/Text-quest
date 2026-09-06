#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор и валидатор состояний мира. Убирает ручной JSON и ловит ошибки схемы."""
import json, argparse, sys, math
try:
    import edc
except ImportError:
    edc = None

# ─────────── БИБЛИОТЕКА ПРЕДМЕТОВ: кг, литры, теги ───────────
ERA_RANK = {"primitive":0,"preindustrial":1,"industrial":2,"spacefaring":3,
            "interstellar":4,"modern_carryover":99}

# имя: (кг, л, теги, минимальная эпоха местного происхождения)
ITEMS = {
 "нож":(0.20,0.30,["резак","оружие"],"primitive"),
 "нож поясной":(0.18,0.25,["резак"],"primitive"),
 "топор":(1.10,2.00,["рубка","оружие"],"primitive"),
 "кресало":(0.09,0.08,["огонь"],"primitive"),
 "огниво":(0.10,0.10,["огонь"],"primitive"),
 "спички":(0.02,0.05,["огонь"],"industrial"),
 "верёвка 40 м":(3.20,6.00,["альпинизм"],"primitive"),
 "верёвка 10 м":(0.85,1.60,["альпинизм"],"primitive"),
 "мешок с водой 0.5 л":(0.52,0.55,["вода"],"primitive"),
 "фляга 1 л":(1.10,1.10,["вода"],"preindustrial"),
 "котелок":(0.40,1.50,["готовка"],"primitive"),
 "сухари":(1.40,2.50,["еда"],"primitive"),
 "суточный паёк":(0.50,0.90,["еда"],"industrial"),
 "мешок холщовый":(0.30,0.50,["тара"],"primitive"),
 "лапти":(0.35,1.50,["обувь"],"primitive"),
 "одеяло шерстяное":(1.60,6.00,["сон","тепло"],"primitive"),
 "спальник":(1.20,8.00,["сон"],"industrial"),
 "свеча":(0.08,0.12,["свет"],"preindustrial"),
 "фонарь":(0.25,0.40,["свет"],"industrial"),
 "лопата малая":(0.90,1.80,["копать"],"preindustrial"),
 "пила складная":(0.35,0.60,["рубка"],"industrial"),
 "безмен":(0.15,0.20,["измерение"],"preindustrial"),
 "компас":(0.05,0.06,["навигация"],"preindustrial"),
 "часы":(0.05,0.04,["время"],"industrial"),
 "бинокль":(0.70,1.00,["наблюдение"],"industrial"),
 "термометр":(0.03,0.03,["измерение"],"industrial"),
 "аптечка":(0.70,2.00,["медицина"],"industrial"),
 "мультитул":(0.24,0.25,["ремонт"],"industrial"),
 "изолента":(0.12,0.20,["ремонт"],"industrial"),
 "дозиметр":(0.30,0.35,["измерение"],"spacefaring"),
 "комбинезон":(1.10,3.00,["одежда"],"spacefaring"),
 "жетон на шнурке":(0.02,0.01,["надпись"],"industrial"),
 "кислородная маска":(0.60,1.20,["дыхание"],"spacefaring"),
 "патрон скруббера":(0.80,1.50,["дыхание"],"spacefaring"),
 # предметы игрока «из своего времени» — не местного происхождения ни в одном сеттинге
 "смартфон":(0.21,0.12,["стекло","улика"],"modern_carryover"),
 "повербанк 20000":(0.42,0.28,["металл","улика"],"modern_carryover"),
 "солнечная панель складная":(0.33,0.55,["улика","энергия"],"modern_carryover"),
 "кабель":(0.04,0.05,[],"modern_carryover"),
}

# ─────────── БИБЛИОТЕКА КОНТЕЙНЕРОВ: время доступа, объём, масса ───────────
CONTAINERS = {
 "руки":              (0,   None, None, True,  0.00),
 "нагрудный карман":  (2,   0.40, 0.50, False, 0.00),
 "карман куртки":     (2,   1.50, 1.50, False, 0.00),
 "карман штанов":     (3,   1.00, 1.00, False, 0.00),
 "поясной подсумок":  (4,   2.50, 3.00, False, 0.15),
 "поясная сумка":     (6,   6.00, 5.00, False, 0.35),
 "боковой карман рюкзака":(15,1.50,1.50, False, 0.00),
 "рюкзак 35 л":       (40, 35.00,20.00, False, 1.10),
 "рюкзак 60 л":       (45, 60.00,30.00, False, 1.60),
 "заплечный мешок":   (30, 20.00,15.00, False, 0.40),
 "стенной шкафчик":   (25, 20.00,15.00, True,  0.00),
 "ящик":              (20, 40.00,40.00, True,  0.00),
 "привязано снаружи": (20,  None, None, True,  0.00),
 "дрейфует по отсеку":(10,  None, None, True,  0.00),
 "схрон":             (300, None, None, True,  0.00),
}

# ─────────── ОДЕЖДА: clo и масса ───────────
CLOTHES = {
 "футболка хлопковая":(0.15,0.10),"худи хлопковое":(0.65,0.70),"штаны хлопковые":(0.50,0.30),
 "кроссовки":(0.80,0.10),"свитер шерстяной":(0.60,1.00),"куртка брезентовая":(1.40,0.50),
 "тулуп":(3.20,2.20),"бельё криокапсулы":(0.30,0.60),"комбинезон рабочий":(1.10,0.90),
 "рубаха льняная":(0.30,0.35),"порты":(0.40,0.30),"онучи и лапти":(0.50,0.25),
 "парка зимняя":(1.80,2.00),"термобельё":(0.35,0.80),
}

def pressure_at(z, p0=1.0, H=8400.0):
    if z < 0:      return p0*math.exp(-z/H)
    if z <= 11000: return p0*(1-2.2558e-5*z)**5.2559
    return p0*0.2234*math.exp(-(z-11000)/6342)

DEFAULT_SKILLS = {"athletics":35,"stealth":30,"perception":40,"craft":30,
                  "medicine":20,"social":35,"survival":30,"combat":25}

import random as _random

def eligible_items(tech_ceiling, carryover_modern=False):
    lim = ERA_RANK[tech_ceiling]
    out = []
    for name, (kg, l, tags, era) in ITEMS.items():
        r = ERA_RANK[era]
        if r == 99:
            if carryover_modern: out.append(name)
        elif r <= lim:
            out.append(name)
    return sorted(out)

def random_loadout(seed, tech_ceiling, spec, carryover_modern=False):
    """Детерминированная случайная укладка. Тот же seed -> тот же набор, разные seed -> разный."""
    rng = _random.Random(f"{seed}|loadout")
    pool = spec.get("item_pool") or eligible_items(tech_ceiling, carryover_modern)
    always = spec.get("item_always", [])
    n_lo, n_hi = spec.get("n_items", [4, 7])
    n = rng.randint(n_lo, n_hi)
    rest = [x for x in pool if x not in always]
    rng.shuffle(rest)
    chosen = list(always) + rest[:max(0, n - len(always))]

    cpool = spec.get("container_pool", list(CONTAINERS.keys()))
    calways = spec.get("container_always", ["карман куртки"])
    cn_lo, cn_hi = spec.get("n_containers", [2, 3])
    cn = rng.randint(cn_lo, cn_hi)
    crest = [x for x in cpool if x not in calways]
    rng.shuffle(crest)
    containers = list(calways) + crest[:max(0, cn - len(calways))]

    wpool = spec.get("worn_pool", [])
    wn_lo, wn_hi = spec.get("n_worn", [len(wpool), len(wpool)])
    wn = min(len(wpool), rng.randint(wn_lo, wn_hi)) if wpool else 0
    wshuf = wpool[:]; rng.shuffle(wshuf)
    worn = wshuf[:wn]

    # раскладка: каждый предмет — в случайный контейнер, что вмещает; иначе не взят
    placement, notes = [], []
    loads = {c: [0.0, 0.0] for c in containers}  # [кг, л]
    cap = {}
    for cname in containers:
        acc, cl, ck, rigid, kg = CONTAINERS[cname]
        cap[cname] = (cl, ck, rigid)
    for name in chosen:
        if name not in ITEMS:
            notes.append(f"пропущен неизвестный предмет: {name}"); continue
        kg, l, tags, era = ITEMS[name]
        order = containers[:]; rng.shuffle(order)
        placed = False
        for cname in order:
            cl, ck, rigid = cap[cname]
            mult = 1.0 if rigid else 1.3
            nl, nk = loads[cname][1] + l, loads[cname][0] + kg
            if (cl is None or nl <= cl*mult) and (ck is None or nk <= ck):
                loads[cname][0], loads[cname][1] = nk, nl
                placement.append((name, cname)); placed = True; break
        if not placed:
            notes.append(f"не поместилось никуда, не взято: {name}")
    return containers, placement, worn, notes

def expand(brief):
    """Разворачивает краткий замысел в полное состояние по схеме."""
    b = brief
    S = {
     "meta": {"seed": b["seed"], "turn": 0, "setting": b["setting"],
              "tech_ceiling": b.get("tech_ceiling","preindustrial"), "tone":"безжалостный реализм"},
     "profile": {"ladder": b["ladder"], "root": b["ladder_root"],
                 "z_ref": b.get("z_ref","уровень моря"), "z_unit": b.get("z_unit","м"),
                 "physics_on": b["physics_on"],
                 "physics_off": [x for x in ["холод","жара","голод","жажда","сон","раны","болезни",
                                             "гипоксия","давление","радиация","вакуум","углекислота",
                                             "невесомость","нагрузка","погода","сезоны","ветер"]
                                 if x not in b["physics_on"]],
                 "special_laws": b.get("special_laws",[])},
     "calendar": {"day_hours": b.get("day_hours",24), "year_days": b.get("year_days",365),
                  "seasons": b.get("seasons",[]), "epoch_label": b.get("epoch",""),
                  "start_date": b.get("start_date","день 0"),
                  "natural_light": b.get("natural_light",True)},
     "time": {"t_h": b.get("start_hour",8.0), "weather": b.get("weather","—"), "light":"день"},
     "position": {"path": b["start_path"], "z_m": b.get("start_z",0), "local": b["start_local"]},
     "pc": {"name": b.get("pc_name","игрок"), "posture":"стоит",
            "needs": {k: b.get("needs",{}).get(k,0) for k in
                      ("hunger","thirst","fatigue","cold_stress","stress")},
            "vitals": {"blood_loss_pct":0,"infection":0,
                       "core_temp_c": b.get("core_temp",36.6)},
            "skills": {**DEFAULT_SKILLS, **b.get("skills",{})},
            "wounds": [], "conditions": b.get("conditions",[]), "attempts": {},
            "body_mass_kg": b.get("mass",75), "carry_base_kg": b.get("carry_base",25.0)},
     "gear": {"hands":{"slots":2,"held":[]}, "worn":[], "containers":[], "lashed":[], "cache":[]},
     "items": [],
     "envelope": {"ambient_c": b.get("ambient_c",10.0), "wind_ms": b.get("wind_ms",0.0),
                  "windchill_c": b.get("ambient_c",10.0), "gravity_g": b.get("gravity_g",1.0),
                  "breathable":True, "ttl_min":None},
     "world": {"gravity_g": b.get("gravity_g",1.0),
               "lapse_c_per_km": b.get("lapse",6.5), "geotherm_c_per_km": b.get("geotherm",25),
               "atmosphere": b.get("atmosphere",{"o2_frac":0.209,"p0_atm":1.0,"scale_height_m":8400}),
               "climate": b.get("climate",{"t_min":5,"t_max":15,"sunrise":6.5,"sunset":18.5,"note":""}),
               "chain": b["chain"], "sites_canon": b["sites"],
               "npcs": b.get("npcs",[]), "factions": b.get("factions",[])},
     "clocks": [], "known": {"paths":[b["start_path"]],"npcs":[],"facts":[]},
     "hidden_truths": b.get("truths",[]),
     "log": [{"turn":0,"fact": b.get("opening_fact","Игра началась.")}],
     "status": "alive"}

    # envelope несёт только включённые подсистемы — пустое поле провоцирует упоминание
    on = set(b["physics_on"])
    if {"гипоксия","давление","вакуум"} & on:
        S["envelope"]["pressure_atm"] = 1.0
        S["envelope"]["po2_kpa"] = round(b.get("atmosphere",{}).get("o2_frac",0.209)*101.3*
                                         pressure_at(b.get("start_z",0)), 1)
    if "углекислота" in on: S["envelope"]["pco2_kpa"] = b.get("pco2_kpa", 0.04)
    if "радиация"   in on:
        S["envelope"]["dose_rate_msv_h"] = b.get("dose_rate", 0.0003)
        S["envelope"]["dose_sv"] = b.get("dose_sv", 0.0)

    _rand_notes = []
    if b.get("carryover"):          # попаданец: вещи наших дней, момент переноса случаен
        if edc is None: raise RuntimeError("нужен edc.py рядом с worldgen.py")
        spec = b["carryover"] if isinstance(b["carryover"], dict) else {}
        ctx, worn_o, cont_o, items_o, notes_o = edc.build(
            b["seed"], spec.get("context", "auto"), wet=spec.get("wet", 0.0))
        _rand_notes = [f"момент переноса: {ctx}"] + notes_o
        S["gear"]["worn"] = worn_o
        S["gear"]["containers"] = cont_o
        S["items"] = items_o
        S["pc"].setdefault("conditions", []).append(f"перенесён в момент: {ctx}")
        S["log"][0]["fact"] += f" Момент переноса: {ctx}."
        b = dict(b); b["worn"] = []; b["containers"] = []; b["items"] = []
        b["_carryover_done"] = True
    if "loadout" in b and not b.get("_carryover_done"):
        containers_l, placement_l, worn_l, _rand_notes = random_loadout(
            b["seed"], b.get("tech_ceiling","preindustrial"), b["loadout"],
            carryover_modern=b.get("carryover_modern", False))
        b = dict(b)
        b["containers"] = containers_l
        b["items"] = [(name, cname) for name, cname in placement_l]
        b["worn"] = worn_l

    for i, name in enumerate(b.get("worn",[]), 1):
        if name not in CLOTHES: raise KeyError(f"нет в библиотеке одежды: {name}")
        kg, clo = CLOTHES[name]
        S["gear"]["worn"].append({"id":f"wrn_{i:02d}","name":name,"kg":kg,"clo":clo,
                                  "layer":"—","wet": b.get("wet",0.0)})

    if b.get("_carryover_done"):
        cid_of = {}
    else:
        S["gear"]["containers"].append({"id":"cnt_00","name":"руки","mount":"тело",
                                        "access_s":0,"cap_l":None,"cap_kg":None,"rigid":True,"kg":0})
        cid_of = {"руки":"cnt_00"}
    for i, name in enumerate(b.get("containers",[]), 1):
        if name not in CONTAINERS: raise KeyError(f"нет в библиотеке контейнеров: {name}")
        acc, cl, ck, rigid, kg = CONTAINERS[name]
        cid = f"cnt_{i:02d}"; cid_of[name] = cid
        S["gear"]["containers"].append({"id":cid,"name":name,"mount":"тело","access_s":acc,
                                        "cap_l":cl,"cap_kg":ck,"rigid":rigid,"kg":kg})

    depth = {}
    for i, (name, where) in enumerate(b.get("items",[]), 1):
        if name not in ITEMS: raise KeyError(f"нет в библиотеке предметов: {name}")
        kg, l, tags, _era = ITEMS[name]
        cid = cid_of.get(where)
        if not cid: raise KeyError(f"предмет '{name}' положен в необъявленный контейнер '{where}'")
        d = depth.get(cid, 0); depth[cid] = d + 1
        S["items"].append({"id":f"itm_{i:02d}","name":name,"kg":kg,"l":l,"qty":1,
                           "in":cid,"depth":d,"condition":1.0,"tags":tags})

    for i, c in enumerate(b.get("clocks",[]), 1):
        clk = {"id":f"clk_{i:02d}","name":c["name"],"filled":c["filled"],
               "max":c["max"],"scale":c.get("scale","региональный"),
               "period_h":c["period_h"],"last_tick_h":S["time"]["t_h"],
               "hidden":c.get("hidden",True),"payoff":c["payoff"]}
        if c.get("on_complete"):
            clk["on_complete"] = json.loads(json.dumps(c["on_complete"]))
        S["clocks"].append(clk)
    S["_gen_notes"] = _rand_notes
    return S

# ─────────── ВАЛИДАТОР ───────────
def validate(S):
    err, warn = [], []
    lad = S["profile"]["ladder"]; root = S["profile"]["root"]

    p = S["position"]["path"].split("/")
    if p[0] != root: err.append(f"путь игрока начинается с '{p[0]}', а корень лестницы '{root}'")
    if len(p) > len(lad): err.append(f"путь игрока глубже лестницы ({len(p)} > {len(lad)})")
    if S["position"]["path"] not in [s["path"] for s in S["world"]["sites_canon"]]:
        err.append("площадка игрока отсутствует в sites_canon")

    cont = {c["id"]: c for c in S["gear"]["containers"]}
    for it in S["items"]:
        if it["in"] not in cont: err.append(f"{it['name']}: контейнер '{it['in']}' не объявлен")
    for cid, c in cont.items():
        ins = [x for x in S["items"] if x["in"] == cid]
        vol = sum(x["l"]*x.get("qty",1) for x in ins); mas = sum(x["kg"]*x.get("qty",1) for x in ins)
        lim = c.get("cap_l"); klim = c.get("cap_kg")
        if lim and vol > lim*(1.0 if c.get("rigid") else 1.3):
            err.append(f"{c['name']}: переполнен по объёму {vol:.1f} > {lim}")
        if klim and mas > klim:
            err.append(f"{c['name']}: перегружен {mas:.1f} > {klim} кг")

    h = S["gear"]["hands"]
    if len(h["held"]) > h["slots"]: err.append("в руках больше предметов, чем слотов")
    for iid in h["held"]:
        if not any(x["id"] == iid for x in S["items"]): err.append(f"в руках несуществующий {iid}")

    M = sum(i["kg"]*i.get("qty",1) for i in S["items"]) + sum(c.get("kg",0) for c in S["gear"]["containers"])
    Mw = sum(w["kg"] for w in S["gear"]["worn"])
    ratio = (M+0.5*Mw)*S["world"]["gravity_g"]/S["pc"]["carry_base_kg"]
    if ratio > 0.6: warn.append(f"стартовая загрузка {ratio:.2f} — генератор требует < 0.6")

    on = set(S["profile"]["physics_on"])
    if "холод" in on and sum(w["clo"] for w in S["gear"]["worn"]) == 0:
        warn.append("холод включён, а одежды нет — clo 0")
    for k, sub in (("po2_kpa","гипоксия"),("pressure_atm","давление"),
                   ("pco2_kpa","углекислота"),("dose_rate_msv_h","радиация")):
        if sub not in on and k in S["envelope"] and sub not in ("давление",):
            warn.append(f"'{sub}' выключена, но поле {k} в envelope присутствует")

    paths = {s["path"] for s in S["world"]["sites_canon"]}
    for s in S["world"]["sites_canon"]:
        for e in s["exits"]:
            if e["to"].split("/")[-1] == s["path"].split("/")[-1]:
                err.append(f"{s['name']}: выход ведёт сам в себя")
            for f in ("travel_min","difficulty"):
                if f not in e: err.append(f"{s['name']}: у выхода нет поля {f}")

    CLOCK_PATH_ROOTS = {"pc","world","time","envelope","meta","position","profile","calendar"}
    for c in S["clocks"]:
        for f in ("period_h","max","filled","payoff"):
            if f not in c: err.append(f"счётчик {c.get('name','?')}: нет поля {f}")
        if c.get("filled",0) > c.get("max",1): err.append(f"счётчик {c['name']}: filled > max")
        oc = c.get("on_complete")
        name = c.get("name", "?")
        if not oc:
            if c.get("payoff"):
                warn.append(f"счётчик {name}: payoff без on_complete — сработает только строкой в журнале")
            continue
        if not isinstance(oc, list):
            err.append(f"счётчик {name}: on_complete должен быть списком")
            continue
        for i, fx in enumerate(oc):
            if not isinstance(fx, dict):
                err.append(f"счётчик {name} on_complete[{i}]: не объект"); continue
            if "site" in fx and "sites" in fx:
                err.append(f"счётчик {name} on_complete[{i}]: укажите site или sites, не оба")
                continue
            env_op = "env" in fx and ("site" in fx or "sites" in fx)
            has_set, has_add = "set" in fx, "add" in fx
            path_op = "path" in fx and (has_set or has_add) and not (has_set and has_add)
            if env_op and not path_op:
                if not isinstance(fx.get("env"), dict):
                    err.append(f"счётчик {name} on_complete[{i}]: env должен быть объектом")
                    continue
                canon = {st.get("path") for st in S["world"]["sites_canon"]}
                if "site" in fx and fx["site"] not in canon:
                    err.append(f"счётчик {name} on_complete[{i}]: площадка {fx['site']} не в каноне")
                if "sites" in fx:
                    sel = fx["sites"]
                    if sel != "*" and not isinstance(sel, list):
                        err.append(f"счётчик {name} on_complete[{i}]: sites — '*' или список путей")
                    elif isinstance(sel, list):
                        for pth in sel:
                            if pth not in canon:
                                err.append(f"счётчик {name} on_complete[{i}]: площадка {pth} не в каноне")
            elif path_op and not env_op:
                root = str(fx.get("path","")).split(".")[0]
                if root not in CLOCK_PATH_ROOTS:
                    err.append(f"счётчик {name} on_complete[{i}]: путь должен начинаться с известного корня")
                if has_add and not isinstance(fx.get("add"), (int, float)):
                    err.append(f"счётчик {name} on_complete[{i}]: add должен быть числом")
            else:
                err.append(f"счётчик {name} on_complete[{i}]: неизвестная операция")
    if not S["clocks"]: warn.append("нет ни одного счётчика — мир не будет развиваться сам")
    if len(S["hidden_truths"]) < 3: warn.append("меньше трёх скрытых истин — разведка обесценится")
    if "холод" in on and not any(s.get("env") for s in S["world"]["sites_canon"]) \
       and not S["calendar"]["natural_light"]:
        warn.append("естественного света нет, но у площадок не задан env — среда не определится")
    return err, warn

# ─────────── ВАЛИДАТОР НАБОРА ПРАВИЛ ───────────
def validate_ruleset(R):
    """Опечатка в ruleset.json не должна проваливаться молча — она должна кричать."""
    err, warn = [], []
    OPS = {"==","!=",">","<",">=","<=","in"}
    ROOTS = {"pc","world","time","envelope","meta","position","profile","calendar"}

    for blk in ("needs","vitals","environment"):
        for key, spec in R.get(blk, {}).items():
            if not isinstance(spec, dict):
                err.append(f"{blk}.{key}: должно быть объектом"); continue
            bands = spec.get("bands", [])
            direction = spec.get("direction", "above")
            if bands:
                thr = [b[0] for b in bands]
                if any(not isinstance(b, list) or len(b) != 2 for b in bands):
                    err.append(f"{blk}.{key}.bands: каждый порог — пара [число, текст]")
                elif direction == "above" and thr != sorted(thr):
                    err.append(f"{blk}.{key}.bands: при direction=above пороги должны возрастать, сейчас {thr}")
                elif direction == "below" and thr != sorted(thr, reverse=True):
                    err.append(f"{blk}.{key}.bands: при direction=below пороги должны убывать, сейчас {thr}")
            if blk == "environment" and spec.get("direction") not in (None,"above","below"):
                err.append(f"environment.{key}.direction: только 'above' или 'below'")

    for i, m in enumerate(R.get("condition_modifiers", [])):
        for f in ("name","factor","path","op","value"):
            if f not in m: err.append(f"condition_modifiers[{i}]: нет поля {f}")
        if m.get("op") not in OPS: err.append(f"condition_modifiers[{i}]: неизвестная операция {m.get('op')}")
        f = m.get("factor")
        if not isinstance(f,(int,float)) or not (0 < f <= 2):
            err.append(f"condition_modifiers[{i}]: factor {f} вне разумного (0..2)")
        root = str(m.get("path","")).split(".")[0]
        if root and root not in ROOTS:
            err.append(f"condition_modifiers[{i}]: путь '{m['path']}' начинается с '{root}', такого корня в состоянии нет")

    res = R.get("resolution", {})
    cl = res.get("clamp")
    if not (isinstance(cl,list) and len(cl)==2 and 0 < cl[0] < cl[1] <= 100):
        err.append(f"resolution.clamp: должно быть [нижняя, верхняя] в 1..100, сейчас {cl}")
    if res.get("catastrophe",96) <= res.get("floor_success",5):
        err.append("resolution: порог катастрофы должен быть выше порога гарантированного успеха")
    if res.get("max_checks_per_turn",2) < 1:
        err.append("resolution.max_checks_per_turn должен быть не меньше 1")

    for i, b in enumerate(R.get("load_bands", [])):
        if not isinstance(b,list) or len(b)!=4:
            err.append(f"load_bands[{i}]: нужен формат [порог, текст, множитель, множитель_усталости]")
    thr=[b[0] for b in R.get("load_bands",[]) if isinstance(b,list) and b]
    if thr and thr!=sorted(thr): err.append("load_bands: пороги не по возрастанию")

    cm = R.get("cold_model", {})
    if cm and cm.get("gain_divisor", 1) == 0: err.append("cold_model.gain_divisor не может быть нулём")
    if cm and "fire_bonus_c" in cm and not isinstance(cm["fire_bonus_c"], (int, float)):
        err.append("cold_model.fire_bonus_c должен быть числом °C")

    if not R.get("needs"):   warn.append("нет ни одной потребности — существо ничего не будет чувствовать")
    if not R.get("skills"):  warn.append("нет списка навыков")
    if not R.get("consequences"): warn.append("нет таблицы последствий — провалы будут без последствий")
    for key, spec in R.get("needs", {}).items():
        if not spec.get("bands"): warn.append(f"needs.{key}: нет симптомов — игрок ничего не почувствует")
        if spec.get("rate_per_h") is None and not spec.get("driver"):
            warn.append(f"needs.{key}: ни скорости, ни драйвера — шкала не будет меняться")
    return err, warn

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("--brief", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("check"); p.add_argument("--state", required=True)
    p = sub.add_parser("checkrules"); p.add_argument("--rules", required=True)
    a = ap.parse_args()
    if a.cmd == "new":
        S = expand(json.load(open(a.brief, encoding="utf-8")))
        err, warn = validate(S)
        for e in err:  print("ОШИБКА:", e)
        for w in warn: print("замечание:", w)
        if err: print("\nсостояние не записано"); sys.exit(1)
        for note in S.pop("_gen_notes", []):
            print("рандом:", note)
        json.dump(S, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nготово: {a.out}  ({len(S['items'])} предметов, {len(S['clocks'])} счётчиков, "
              f"{len(S['world']['npcs'])} NPC, {len(S['hidden_truths'])} скрытых истин)")
    elif a.cmd == "checkrules":
        err, warn = validate_ruleset(json.load(open(a.rules, encoding="utf-8")))
        for e in err:  print("ОШИБКА:", e)
        for w in warn: print("замечание:", w)
        print("набор правил чист" if not err and not warn else f"\nошибок {len(err)}, замечаний {len(warn)}")
        sys.exit(1 if err else 0)
    else:
        err, warn = validate(json.load(open(a.state, encoding="utf-8")))
        for e in err:  print("ОШИБКА:", e)
        for w in warn: print("замечание:", w)
        print("чисто" if not err and not warn else f"\nошибок {len(err)}, замечаний {len(warn)}")
        sys.exit(1 if err else 0)

if __name__ == "__main__":
    main()
