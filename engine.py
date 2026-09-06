#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ядро текстового симулятора. Считает всё, что модель считать не умеет."""
import json, math, hashlib, argparse, os, sys, copy
try:
    import society
except ImportError:
    society = None

STATE = os.environ.get("SIM_STATE", "state.json")
RULES_PATH = os.environ.get("SIM_RULES", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ruleset.json"))
_RULES = None

def rules(S=None):
    """Набор правил: встроенный в состояние либо внешний файл.
    Механика его не знает — только читает. Подменил файл — сменил вид, эпоху, жанр."""
    global _RULES
    if S is not None and isinstance(S.get("ruleset"), dict): return S["ruleset"]
    if _RULES is None:
        _RULES = json.load(open(RULES_PATH, encoding="utf-8"))
    return _RULES

def dig(S, path, default=None):
    cur = S
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur: return default
        cur = cur[part]
    return cur

def _cmp(val, op, ref, tol=0.0):
    if val is None: return False
    try:
        if op == "==": return val == ref
        if op == "!=": return abs(val - ref) > tol if isinstance(val,(int,float)) else val != ref
        if op == ">":  return val > ref
        if op == "<":  return val < ref
        if op == ">=": return val >= ref
        if op == "<=": return val <= ref
        if op == "in": return val in ref
    except TypeError: return False
    return False

def band_text(value, bands, direction="above"):
    out = None
    if direction == "above":
        for thr, txt in bands:
            if value >= thr: out = txt
    else:
        for thr, txt in bands:
            if value <= thr: out = txt
    return out


# ─────────────────────────── ФИЗИКА ───────────────────────────

def pressure_atm(z, p0=1.0, H=8400.0):
    if z < 0:      return p0 * math.exp(-z / H)
    if z <= 11000: return p0 * (1 - 2.2558e-5 * z) ** 5.2559
    return p0 * 0.2234 * math.exp(-(z - 11000) / 6342)

def po2_kpa(z, o2=0.209, p0=1.0, H=8400.0):
    return o2 * pressure_atm(z, p0, H) * 101.3

def temp_at(z, t_surf, lapse=6.5, geo=25.0):
    return max(-56.0, t_surf - lapse * z / 1000) if z >= 0 else t_surf + geo * abs(z) / 1000

def windchill(T, wind_ms):
    v = wind_ms * 3.6
    if v < 5: return T
    k = v ** 0.16
    return 13.12 + 0.6215 * T - 11.37 * k + 0.3965 * T * k

def cold_rate(T_wc, clo, activity, S=None):
    """activity: 0 покой, 1 ходьба, 2 тяжёлая работа. Коэффициенты — из cold_model."""
    cm = rules(S).get("cold_model", {})
    comfort = cm.get("comfort_base_c", 21)
    dT = (comfort - cm.get("clo_coeff", 8) * clo - cm.get("activity_coeff", 10) * activity) - T_wc
    return dT / cm.get("gain_divisor", 2) if dT > 0 else cm.get("recovery_per_h", -5.0)

def core_temp(cs):
    return 37 - 9 * max(0.0, cs - 30) / 70

def surface_temp(S, t_h):
    c = S["world"]["climate"]
    hod = t_h % S["calendar"]["day_hours"]
    mean, amp = (c["t_min"] + c["t_max"]) / 2, (c["t_max"] - c["t_min"]) / 2
    return mean + amp * math.cos(2 * math.pi * (hod - 15) / S["calendar"]["day_hours"])

def light_at(S, t_h):
    hod = t_h % S["calendar"]["day_hours"]
    sr, ss = S["world"]["climate"]["sunrise"], S["world"]["climate"]["sunset"]
    if sr - 0.7 <= hod < sr:      return "рассвет"
    if sr <= hod < ss - 0.7:      return "день"
    if ss - 0.7 <= hod < ss:      return "сумерки"
    return "темнота"

# ─────────────────────────── СНАРЯЖЕНИЕ ───────────────────────────

def clo_total(S):
    wet_pen = rules(S).get("cold_model", {}).get("wet_penalty", 0.67)
    return sum(w["clo"] * (1 - wet_pen * w.get("wet", 0.0)) for w in S["gear"]["worn"])

def wet_step(S, hours, sheltered=False, fire=False):
    wetting = S["time"]["weather"] in ("морось", "дождь", "мокрый снег") and not sheltered
    for w in S["gear"]["worn"]:
        if w.get("waterproof"): continue
        cur = w.get("wet", 0.0)
        if wetting:   w["wet"] = min(1.0, cur + 0.5 * hours)
        elif fire:    w["wet"] = max(0.0, cur - 0.4 * hours)
        elif sheltered: w["wet"] = max(0.0, cur - 0.1 * hours)

def load_state(S):
    M = sum(i["kg"] * i.get("qty", 1) for i in S["items"])
    M += sum(c.get("kg", 0) for c in S["gear"]["containers"])
    Mw = sum(w["kg"] for w in S["gear"]["worn"])
    ratio = (M + 0.5 * Mw) * S["world"]["gravity_g"] / S["pc"]["carry_base_kg"]
    return M, Mw, ratio

def load_penalty(r):
    if r < 0.3:  return 0, 1.0
    if r < 0.6:  return 0, 1.5
    if r < 0.9:  return -15, 2.5
    if r < 1.2:  return -30, 3.5
    return -60, 5.0

def access_time(S, item):
    cont = {c["id"]: c for c in S["gear"]["containers"]}
    c = cont.get(item["in"])
    if not c: return 999
    base = c["access_s"]
    return base if c.get("rigid") else base + 10 * item.get("depth", 0)

def available(S, window_s):
    out = []
    for it in S["items"]:
        t = access_time(S, it)
        if t <= window_s: out.append((it["name"], t))
    return sorted(out, key=lambda x: x[1])

# ─────────────────────────── БРОСКИ ───────────────────────────

def d100(seed, turn, idx):
    return int(hashlib.sha256(f"{seed}|{turn}|{idx}".encode()).hexdigest(), 16) % 100 + 1


def condition_factor(S):
    """Множители из набора правил — ни одного поля, специфичного для человека."""
    f, notes = 1.0, []
    for m in rules(S).get("condition_modifiers", []):
        if _cmp(dig(S, m["path"]), m["op"], m["value"], m.get("tol", 0.0)):
            f *= m["factor"]; notes.append(f"{m['name']} ×{m['factor']}")
    for w in S["pc"].get("wounds", []):
        k = 1 - w.get("penalty", 0) / 100.0
        if k < 1: f *= k; notes.append(f"{w['name']} ×{k:.2f}")
    r = load_state(S)[2]
    for thr, _txt, factor, _mult in rules(S).get("load_bands", []):
        if r >= thr and factor: f *= factor; notes.append(f"ноша ×{factor}")
    return f, notes

def consequence(S, domain, idx, severity="ПРОВАЛ"):
    """Тексты последствий — из набора правил, не из кода."""
    cons = rules(S).get("consequences") or {}
    tab = cons.get(domain) or cons.get("движение") or []
    if not tab:
        return None
    pick = d100(S["meta"]["seed"], S["meta"]["turn"], 900 + idx) % len(tab)
    txt = tab[pick]
    if severity.startswith("КАТАСТРОФА"): txt = "СИЛЬНО: " + txt
    return txt

def check(S, skill, difficulty, label, idx, adv=0, domain="движение", lethal=False):
    """adv: ситуационное преимущество, вычитается из сложности (упор, инструмент, свет)."""
    base = S["pc"]["skills"].get(skill, 30)
    f, notes = condition_factor(S)
    raw = (base - (difficulty - adv)) * f
    target = int(max(5, min(95, round(raw))))

    key = f"{label}|{target}"
    prev = S["pc"].setdefault("attempts", {})
    if key in prev:
        r = prev[key]["roll"]
        return {"label": label, "skill": skill, "base": base, "factor": round(f, 3),
                "notes": notes, "difficulty": difficulty, "adv": adv, "raw": round(raw, 1),
                "target": target, "roll": r, "outcome": prev[key]["outcome"],
                "consequence": prev[key].get("consequence"),
                "repeat": "ПОВТОР без изменения условий — тот же исход, бросок не делается"}

    if raw < 5:
        out, r = "ПРОВАЛ (без броска: невозможно в таком состоянии)", None
    else:
        r = d100(S["meta"]["seed"], S["meta"]["turn"], idx)
        if r >= 96:            out = "КАТАСТРОФА"
        elif r <= 5:           out = "УСПЕХ (пол)"
        elif r <= target / 5:  out = "КРИТИЧЕСКИЙ УСПЕХ"
        elif r <= target:      out = "УСПЕХ"
        elif r <= target + 20: out = "УСПЕХ ЦЕНОЙ"
        else:                  out = "ПРОВАЛ"
        if out == "КАТАСТРОФА" and not lethal:
            out = "КАТАСТРОФА (не смертельная: действие не смертельно)"
    cons = consequence(S, domain, idx, out) if ("ПРОВАЛ" in out or "ЦЕНОЙ" in out or "КАТАСТРОФА" in out) else None
    prev[key] = {"roll": r, "outcome": out, "consequence": cons}
    return {"label": label, "skill": skill, "base": base, "factor": round(f, 3), "notes": notes,
            "difficulty": difficulty, "adv": adv, "raw": round(raw, 1), "target": target,
            "roll": r, "outcome": out, "consequence": cons, "repeat": None}

def opposed(S, a_skill, b_name, b_target, label, idx):
    a = check(S, a_skill, 0, label, idx, domain="борьба")
    rb = d100(S["meta"]["seed"], S["meta"]["turn"], idx + 500)
    ma = (a["target"] - a["roll"]) if a["roll"] else -99
    mb = b_target - rb
    return {"label": label, "pc": a, "npc": {"name": b_name, "target": b_target, "roll": rb},
            "margin_pc": ma, "margin_npc": mb,
            "winner": "игрок" if ma > mb else ("противник" if mb > ma else "ничья"),
            "delta": abs(ma - mb)}

def wound_from(delta, armor=0):
    d = max(0, delta - armor)
    if d <= 10:  return ("ушиб", "капиллярное", 0.5, 5)
    if d <= 30:  return ("рана", "венозное", 2.0, 15)
    if d <= 50:  return ("тяжёлая рана", "венозное", 4.0, 30)
    return ("проникающая рана", "артериальное", 1200.0, 60)

# ─────────────────────────── ТИК ───────────────────────────

def site_of(S, path=None):
    path = path or S["position"]["path"]
    for st in S["world"]["sites_canon"]:
        if st["path"] == path: return st
    return {}

def recompute_env(S, sheltered=False, fire=False):
    w = S["world"]; z = S["position"]["z_m"]; e = S["envelope"]
    site = site_of(S)
    ov = site.get("env", {})

    # свет: естественный цикл либо режим отсека
    if S["calendar"].get("natural_light", True):
        S["time"]["light"] = light_at(S, S["time"]["t_h"])
        ts = surface_temp(S, S["time"]["t_h"])
        e["ambient_c"] = round(temp_at(z, ts, w["lapse_c_per_km"], w["geotherm_c_per_km"]), 1)
    else:
        S["time"]["light"] = ov.get("light", "аварийное освещение")
        e["ambient_c"] = round(ov.get("ambient_c", e["ambient_c"]), 1)

    # укрытие и огонь — флаги хода, не погода. Не затирать envelope.wind_ms:
    # это уличный ветер; иначе следующий look без флагов остался бы «в штиле».
    if fire:
        bonus = rules(S).get("cold_model", {}).get("fire_bonus_c", 0)
        e["ambient_c"] = round(e["ambient_c"] + bonus, 1)
    wind_ms = 0.0 if sheltered else e.get("wind_ms", 0)
    e["windchill_c"] = round(windchill(e["ambient_c"], wind_ms), 1)

    # герметичная среда: параметры отсека, а не высоты
    if ov:
        for k in ("pressure_atm", "po2_kpa", "pco2_kpa", "dose_rate_msv_h", "breathable"):
            if k in ov: e[k] = ov[k]
        if not e.get("breathable", True):
            e["ttl_min"] = round(ov.get("air_reserve_min", 0), 1)
        else:
            e["ttl_min"] = None
        return e
    if "гипоксия" in S["profile"]["physics_on"] or "давление" in S["profile"]["physics_on"]:
        e["pressure_atm"] = round(pressure_atm(z, w["atmosphere"]["p0_atm"], w["atmosphere"]["scale_height_m"]), 3)
        e["po2_kpa"] = round(po2_kpa(z, w["atmosphere"]["o2_frac"], w["atmosphere"]["p0_atm"], w["atmosphere"]["scale_height_m"]), 1)
    else:
        e["pressure_atm"], e["po2_kpa"] = 1.0, 21.2
    return e

def tick(S, hours, activity=1, sheltered=False, fire=False, sleeping=False,
         water=0.0, food=0.0, log=None):
    """Дробит время по часам и считает среду ВНУТРИ действия."""
    log = log if log is not None else []
    rem, n, mult = hours, S["pc"]["needs"], load_penalty(load_state(S)[2])[1]
    while rem > 1e-6:
        h = min(1.0, rem); rem -= h
        S["time"]["t_h"] += h
        recompute_env(S, sheltered, fire)
        wet_step(S, h, sheltered, fire)
        if "холод" in S["profile"].get("physics_on", []) and "cold_stress" in n:
            clo = clo_total(S)
            cr = cold_rate(S["envelope"]["windchill_c"], clo, activity, S)
            n["cold_stress"] = max(0.0, min(100.0, n["cold_stress"] + cr * h))
        R = rules(S); ND = R.get("needs", {}); hi = R.get("scales", {}).get("max", 100)
        for key, spec in ND.items():
            if key == "cold_stress" or key not in n: continue
            if key == "fatigue" and sleeping:
                n[key] = max(0.0, n[key] - spec.get("recover_per_h", 12) * h); continue
            base = spec.get("rate_per_h", 0.0)
            if activity >= 2 or mult > 1.0:
                base = max(base, spec.get("under_load", base))
            if key == "fatigue": base *= mult
            n[key] = max(0.0, min(float(hi), n[key] + base * h - spec.get("decay_per_h", 0.0) * h))
        if not S["calendar"].get("natural_light", True):
            S["pc"].setdefault("circadian_drift_h", 0.0)
            S["pc"]["circadian_drift_h"] += 0.03 * h        # ~0.7 ч за сутки
        site = site_of(S)
        if "углекислота" in S["profile"]["physics_on"] and site.get("env"):
            rate = site["env"].get("pco2_rise_kpa_h", 0.0)
            if rate:
                site["env"]["pco2_kpa"] = round(site["env"].get("pco2_kpa", 0.04) + rate * h, 3)
                S["envelope"]["pco2_kpa"] = site["env"]["pco2_kpa"]
        v = S["pc"]["vitals"]
        WM = R.get("wound_model", {})
        H = R.get("healing", {})
        bt, it_ = WM.get("bleed_target"), WM.get("infection_target")
        pen_day = H.get("penalty_per_day", 0.0)
        inf_heal = H.get("infection_per_h", 0.0)
        kept, any_treated = [], False
        for w in S["pc"].get("wounds", []):
            if w.get("treated"):
                any_treated = True
                if pen_day:
                    w["penalty"] = max(0.0, w.get("penalty", 0) - pen_day * h / 24.0)
                if w.get("penalty", 0) > 0:
                    kept.append(w)
                else:
                    log.append(f"[рана] {w['name']} затянулась.")
            else:
                if bt and bt in v and w.get("bleed_pct_h"):
                    v[bt] = min(100.0, v[bt] + w["bleed_pct_h"] * h)
                if it_ and it_ in v and w.get("dirty"):
                    v[it_] = min(100.0, v[it_] + WM.get("infection_per_h", 2.0) * h)
                kept.append(w)
        S["pc"]["wounds"] = kept
        if any_treated and it_ and it_ in v and inf_heal:
            v[it_] = max(0.0, v[it_] - inf_heal * h)
        if "core_temp_c" not in v or "cold_stress" not in n:
            d = death_check(S)
            if d: log.append(f"[{fmt_time(S)}] ПРЕРВАНО: {d}"); return log
            continue
        tgt = core_temp(n["cold_stress"])
        cur = v["core_temp_c"]
        step = 0.5 * h                       # тело не меняет температуру мгновенно
        v["core_temp_c"] = round(cur + max(-step, min(step, tgt - cur)), 2)
        d = death_check(S)
        if d:
            log.append(f"[{fmt_time(S)}] ПРЕРВАНО: {d}")
            return log
    # 2.5 л/сутки ≈ 36 единиц/сутки -> 1 л = 14.4 единицы; 2500 ккал/сутки ≈ 7.2 ед -> 1000 ккал = 2.9
    R = rules(S)
    def _replenish(amount, kind):
        """Находит потребность по тому, ЧЕМ она восполняется, а не по имени поля.
        Работает для любого вида: воду пьёт человек, заряд берёт механоид."""
        if not amount: return
        for key, spec in R.get("needs", {}).items():
            if spec.get("recovers_by") == kind and key in n:
                upp = spec.get("unit_per_point")
                n[key] = max(0.0, n[key] - (amount / upp if upp else amount))
                return
    _replenish(water, "вода")
    _replenish(food, "еда")
    npc_step(S, log, hours*60)
    if society is not None:
        society.society_step(S, log, hours, rules(S))
    weather_step(S, log)
    tick_clocks(S, log)
    return log

def death_check(S):
    """Все смертельные и предсмертные пороги — из набора правил.
    Ни одного поля, завязанного конкретно на человека."""
    n, v, e = S["pc"]["needs"], S["pc"]["vitals"], S["envelope"]
    R = rules(S)

    if e.get("ttl_min") is not None and e["ttl_min"] <= 0:
        S["status"] = "dead"; return "нечем дышать"

    for key, spec in R.get("environment", {}).items():
        val = e.get(key)
        if val is None: continue
        lo, hi = spec.get("lethal_below"), spec.get("lethal_above")
        if (lo is not None and val <= lo) or (hi is not None and val >= hi):
            S["status"] = "dead"; return spec.get("lethal_note", f"смертельный уровень: {key}")

    for key, spec in R.get("vitals", {}).items():
        val = v.get(key)
        if val is None: continue
        at = spec.get("lethal_at")
        if at is not None and val >= at:
            S["status"] = "dead"; return spec.get("lethal_note", key)
        lo, hi = spec.get("lethal_low"), spec.get("lethal_high")
        if (lo is not None and val <= lo) or (hi is not None and val >= hi):
            S["status"] = "dead"; return spec.get("lethal_note", f"смертельный уровень: {key}")

    for key, spec in R.get("needs", {}).items():
        if n.get(key, 0) >= R.get("scales", {}).get("max", 100) and spec.get("at_max"):
            S["status"] = "dead"; return spec["at_max"]

    for key, spec in R.get("vitals", {}).items():
        val = v.get(key)
        if val is None: continue
        u_lo, u_hi = spec.get("unconscious_below"), spec.get("unconscious_above")
        if S["status"] == "alive" and ((u_lo is not None and val <= u_lo) or
                                       (u_hi is not None and val >= u_hi)):
            S["status"] = "unconscious"; return None
    return None

def npc_step(S, log, minutes):
    """Часть 5 целиком: канал -> цель -> ресурс -> действие -> след.
    Каждый NPC на площадке игрока или по соседству либо замечает игрока,
    либо продвигает свою цель — расходует ресурс и оставляет след в мире,
    а не просто существует на бумаге."""
    here = S["position"]["path"]
    neigh = set()
    for st in S["world"]["sites_canon"]:
        if st["path"] == here:
            neigh = {e["to"] for e in st["exits"]}

    for npc in S["world"]["npcs"]:
        if not npc.get("alive", True): continue
        near = npc["path"] == here or npc["path"] in neigh or here in npc["path"]

        if near and npc["path"] == here:
            if not any(k.get("source") == "видел лично" for k in npc["knows_about_pc"]):
                npc["knows_about_pc"].append({"turn": S["meta"]["turn"], "source": "видел лично",
                                              "fact": "чужак на площадке"})
                log.append(f"[NPC] {npc['name']} замечает тебя лично.")
        elif near and npc["path"] in neigh and minutes >= 4:
            if not any(k.get("source","").startswith("услышал") for k in npc["knows_about_pc"]):
                npc["knows_about_pc"].append({"turn": S["meta"]["turn"], "source": "услышал шум рядом",
                                              "fact": "что-то происходит поблизости"})
                log.append(f"[NPC] {npc['name']} слышит шум со стороны твоей площадки.")

        pid = int(hashlib.sha256(npc["id"].encode()).hexdigest(), 16)
        period = 6
        last = npc.get("_last_acted_period", int(S["time"]["t_h"] // period) - 1)
        cur_period = int(S["time"]["t_h"] // period)
        periods_due = max(0, min(8, cur_period - last))
        for pnum in range(last + 1, last + 1 + periods_due):
            r = d100(S["meta"]["seed"], pnum, pid % 9973)
            res = npc.get("resources", [])
            if r <= 55 and res:
                spent = res[d100(S["meta"]["seed"], pnum, pid % 7919) % len(res)]
                log.append(f"[NPC] {npc['name']} продвигает свою цель ({npc.get('goal','?')}), тратит: {spent}.")
            elif r <= 80:
                cands = [e["to"] for st in S["world"]["sites_canon"] if st["path"] == npc["path"]
                         for e in st["exits"]]
                if cands:
                    dest = cands[d100(S["meta"]["seed"], pnum, pid % 5003) % len(cands)]
                    log.append(f"[NPC] {npc['name']} перемещается: {npc['path']} -> {dest}.")
                    npc["path"] = dest
        npc["_last_acted_period"] = cur_period

WEATHER_CHAIN = {
 "ясно":        {"ясно":0.55,"переменная облачность":0.35,"морось":0.10},
 "переменная облачность": {"ясно":0.30,"переменная облачность":0.40,"морось":0.20,"дождь":0.10},
 "морось":      {"морось":0.35,"дождь":0.25,"переменная облачность":0.30,"ясно":0.10},
 "дождь":       {"дождь":0.40,"морось":0.30,"переменная облачность":0.30},
 "низовая метель": {"низовая метель":0.50,"снегопад":0.30,"переменная облачность":0.20},
 "снегопад":    {"снегопад":0.45,"низовая метель":0.25,"переменная облачность":0.30},
}

def weather_step(S, log):
    """Погода — цепь Маркова, не застывшая строка. Тикает раз в ~6 часов."""
    chain = rules(S).get("weather_chain", WEATHER_CHAIN)
    cur = S["time"].get("weather")
    period = 6
    if int(S["time"]["t_h"] // period) == S["time"].get("_weather_period", -1) or cur not in chain:
        return
    S["time"]["_weather_period"] = int(S["time"]["t_h"] // period)
    opts = list(chain[cur].items())
    r = d100(S["meta"]["seed"], S["meta"]["turn"], 8000 + int(S["time"]["t_h"])) / 100.0
    acc = 0.0
    for name, p in opts:
        acc += p
        if r <= acc:
            if name != cur:
                S["time"]["weather"] = name
                log.append(f"[погода] меняется на «{name}».")
            return
    S["time"]["weather"] = opts[-1][0]

def tick_clocks(S, log):
    for c in S["clocks"]:
        k = int((S["time"]["t_h"] - c["last_tick_h"]) // c["period_h"])
        if k > 0:
            c["last_tick_h"] += k * c["period_h"]
            before = c["filled"]
            c["filled"] = min(c["max"], c["filled"] + k)
            if c["filled"] >= c["max"] and before < c["max"]:
                log.append(f"[СЧЁТЧИК СРАБОТАЛ] {c['name']}: {c['payoff']}")
            elif c["filled"] != before:
                log.append(f"[счётчик] {c['name']} {c['filled']}/{c['max']}" +
                           ("" if c.get("hidden") else " (игрок может заметить)"))

# ─────────────────────────── СИМПТОМЫ ───────────────────────────

def band(v, table):
    out = None
    for thr, txt in table:
        if v >= thr: out = txt
    return out

def symptoms(S):
    """Пороги и тексты — целиком из набора правил. Кода-специфики нет."""
    R = rules(S); out = []
    for key, spec in R.get("needs", {}).items():
        v = S["pc"]["needs"].get(key)
        if v is None: continue
        t = band_text(v, spec.get("bands", []))
        if t: out.append(t)
    for key, spec in R.get("vitals", {}).items():
        v = S["pc"]["vitals"].get(key)
        if v is None or not spec.get("bands"): continue
        t = band_text(v, spec["bands"])
        if t: out.append(t)
    for key, spec in R.get("environment", {}).items():
        v = S["envelope"].get(key)
        if v is None or not spec.get("bands"): continue
        t = band_text(v, spec["bands"], spec.get("direction", "above"))
        if t: out.append(t)
    lb = R.get("load_bands", [])
    if lb:
        t = band_text(load_state(S)[2], [(a, b) for a, b, _, _ in lb])
        if t: out.append(t)
    if S["pc"].get("circadian_drift_h", 0) > 6:
        out.append("сон и явь путаются: не понять, утро сейчас или ночь")
    for w in S["pc"].get("wounds", []):
        out.append(f"рана: {w['name']}" + (" (перевязана)" if w.get("treated") else ""))
    return out or ["ничего не беспокоит"]


# ─────────────────────────── ВЫВОД ───────────────────────────

def fmt_time(S):
    c, t = S["calendar"], S["time"]["t_h"]
    d = int(t // c["day_hours"]); hod = t % c["day_hours"]
    return f"{c['start_date']}+{d}д {int(hod):02d}:{int((hod%1)*60):02d}"

def report(S, rolls=None, log=None, window=None):
    e = S["envelope"]; M, Mw, r = load_state(S)
    L = ["="*64, f"СЛУЖЕБНЫЙ ОТЧЁТ  ход {S['meta']['turn']}  {fmt_time(S)}  [{S['time']['light']}]",
         "="*64,
         f"место: {S['position']['local']}  z={S['position']['z_m']} м  статус: {S['status']}",
         (f"среда: {e.get('ambient_c','—')} °C, ветрохолод {e.get('windchill_c','—')} °C, {S['time']['weather']}"
          + ("  ·  " + "  ".join(f"{k}={e[k]}" for k in
             ("pressure_atm","po2_kpa","pco2_kpa","dose_rate_msv_h") if k in e)
             if any(k in e for k in ("pressure_atm","po2_kpa","pco2_kpa","dose_rate_msv_h")) else "")
          + (f"  ВОЗДУХА {e['ttl_min']} мин" if e.get("ttl_min") is not None else "")),
         (f"одежда: clo {clo_total(S):.2f} (сухая {sum(w['clo'] for w in S['gear']['worn']):.2f}), "
          f"мокрая доля {max((w.get('wet',0) for w in S['gear']['worn']), default=0):.0%}"
          if S["gear"]["worn"] else "одежды нет"),
         f"ноша: {M:.1f} кг + надето {Mw:.1f} кг -> ratio {r:.2f}",
         "-"*64, "ШКАЛЫ (игроку не показывать):",
         "  " + "  ".join(f"{k}={v:.0f}" for k, v in S["pc"]["needs"].items()),
         "  " + "  ".join(f"{k}={v:.4g}" if isinstance(v,(int,float)) else f"{k}={v}"
                            for k, v in S["pc"]["vitals"].items()),
         "-"*64, "СИМПТОМЫ (это и есть материал для прозы):"]
    L += [f"  • {s}" for s in symptoms(S)]
    for a, act in ((("покой",0), ("идти",1), ("работать",2))
                   if "холод" in S["profile"].get("physics_on", []) else ()):
        cr = cold_rate(e["windchill_c"], clo_total(S), act, S)
        cs_now = S["pc"]["needs"].get("cold_stress")
        if cs_now is None: continue
        left = (100 - cs_now) / cr if cr > 0 else None
        L.append(f"  прогноз холода [{a}]: {cr:+.1f}/ч" + (f", предел через {left:.0f} ч" if left else ", безопасно"))
    if window is not None:
        L += ["-"*64, f"ДОСТУПНО в окне {window} с:"]
        av = available(S, window)
        L += [f"  {n} ({t} с)" for n, t in av] or ["  ничего, только руки"]
        L.append("  в руках: " + ", ".join(item_name(S, i) for i in S["gear"]["hands"]["held"]) or "  руки пусты")
    if rolls:
        L += ["-"*64, "БРОСКИ:"]
        for c in rolls:
            adv = f"+преим.{c['adv']}" if c.get("adv") else ""
            L.append(f"  [{c['label']}] ({c['base']}−{c['difficulty']}{adv})×{c['factor']} "
                     f"= сырая {c['raw']} -> цель {c['target']}, бросок {c['roll']} -> {c['outcome']}")
            if c["notes"]: L.append(f"      условия: {', '.join(c['notes'])}")
            if c.get("consequence"): L.append(f"      ПОСЛЕДСТВИЕ: {c['consequence']}")
            if c.get("repeat"):      L.append(f"      {c['repeat']}")
    if log:
        L += ["-"*64, "СОБЫТИЯ МИРА:"] + [f"  {x}" for x in log]
    L.append("="*64)
    return "\n".join(L)

def item_name(S, iid):
    for i in S["items"]:
        if i["id"] == iid: return i["name"]
    return iid

# ─────────────────────────── CLI ───────────────────────────

def load():  return json.load(open(STATE, encoding="utf-8"))
def save(S): json.dump(S, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("look");  p.add_argument("--window", type=int, default=None)
    p = sub.add_parser("act")
    p.add_argument("--minutes", type=float, required=True)
    p.add_argument("--activity", type=int, default=1)
    p.add_argument("--sheltered", action="store_true")
    p.add_argument("--fire", action="store_true")
    p.add_argument("--sleeping", action="store_true")
    p.add_argument("--water", type=float, default=0)
    p.add_argument("--food", type=float, default=0)
    p.add_argument("--window", type=int, default=None)
    p.add_argument("--check", action="append", default=[],
                   help="навык:сложность:метка[:преимущество][:домен][:lethal]")
    p.add_argument("--take", action="append", default=[], help="id предмета -> в руки")
    p.add_argument("--stow", action="append", default=[], help="id:контейнер")
    p.add_argument("--local", default=None, help="описание позиции БЕЗ смены площадки")
    p.add_argument("--to", default=None, help="полный путь новой площадки — обязателен при переходе")
    p.add_argument("--z", type=float, default=None)
    p = sub.add_parser("treat")
    p.add_argument("--wound", type=int, default=0, help="индекс раны, по умолчанию первая")
    p.add_argument("--supplies", type=int, default=0, help="преимущество от аптечки/чистой воды")
    p = sub.add_parser("compact"); p.add_argument("--keep", type=int, default=40)
    p = sub.add_parser("snapshot"); p.add_argument("--tag", default=None)
    p = sub.add_parser("restore");  p.add_argument("--file", required=True)
    p = sub.add_parser("fight")
    p.add_argument("--skill", default="combat")
    p.add_argument("--foe", action="append", required=True,
                   help="имя:цель[:броня[:время_доступа_к_оружию_сек]] — можно указать несколько раз")
    a = ap.parse_args()
    S = load()

    if a.cmd == "treat":
        S["meta"]["turn"] += 1; recompute_env(S)
        ws = S["pc"]["wounds"]
        if not ws:
            print("нечего обрабатывать: ран нет"); return
        w = ws[min(a.wound, len(ws)-1)]
        diff = int(w.get("penalty", 10) / 2)   # перевязать проще, чем терпеть саму рану
        c = check(S, "medicine", diff, f"обработка: {w['name']}", 1, adv=a.supplies, domain="точная")
        L = []
        if "УСПЕХ" in c["outcome"]:
            w["treated"] = True; w["bleed_pct_h"] = 0.0
            if "ЦЕНОЙ" in c["outcome"]:
                w["penalty"] = w.get("penalty", 0) + 5
                L.append(f"кровь остановлена, но сделано грубо: рана мешает сильнее (−{w['penalty']:.0f})")
            else:
                L.append(f"кровотечение остановлено, рана перевязана")
        else:
            w["dirty"] = True
            L.append("обработать не вышло, рана загрязнена сильнее")
            if "КАТАСТРОФА" in c["outcome"]:
                w["bleed_pct_h"] = w.get("bleed_pct_h", 1.0) * 2
                L.append("сорвал корку — кровотечение усилилось вдвое")
        log = tick(S, 10/60, activity=0)
        print(report(S, rolls=[c], log=L+log, window=30)); save(S); return

    if a.cmd == "compact":
        import copy as _c
        before_n = {"log": len(S.get("log", [])),
                    "sites": len(S["world"]["sites_canon"]),
                    "attempts": len(S["pc"].get("attempts", {}))}
        # 1. старый лог сворачивается в сводки по 20 записей, свежие остаются дословно
        lg = S.get("log", [])
        if len(lg) > a.keep:
            old, keep = lg[:-a.keep], lg[-a.keep:]
            digests = []
            for i in range(0, len(old), 20):
                chunk = old[i:i+20]
                digests.append({"turn": chunk[0].get("turn", 0), "kind": "сводка",
                                "fact": f"[{len(chunk)} событий, ходы {chunk[0].get('turn','?')}–{chunk[-1].get('turn','?')}] "
                                        + "; ".join(c["fact"][:60] for c in chunk[:4]) + " …"})
            S["log"] = digests + keep
        # 2. нетронутые площадки выбрасываются — восстановятся тем же сидом
        here = S["position"]["path"]
        neigh = {e["to"] for st in S["world"]["sites_canon"] if st["path"] == here for e in st["exits"]}
        S["world"]["sites_canon"] = [st for st in S["world"]["sites_canon"]
                                     if st.get("touched") or st["path"] == here or st["path"] in neigh]
        # 3. записи о попытках старше 50 ходов не нужны — условия давно изменились
        S["pc"]["attempts"] = {}
        after_n = {"log": len(S["log"]), "sites": len(S["world"]["sites_canon"]), "attempts": 0}
        save(S)
        print("уплотнение канона:")
        for k in before_n:
            print(f"  {k:<10}{before_n[k]:>5} -> {after_n[k]:>5}")
        print("нетронутые площадки удалены — восстановятся тем же сидом при возврате")
        return

    if a.cmd == "snapshot":
        import time as _t
        tag = a.tag or _t.strftime("%Y%m%d_%H%M%S")
        path = STATE.replace(".json", f".snap_{tag}.json")
        json.dump(S, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"снимок сохранён: {path} (ход {S['meta']['turn']}, статус {S['status']})"); return

    if a.cmd == "restore":
        S2 = json.load(open(a.file, encoding="utf-8"))
        save(S2)
        print(f"состояние восстановлено из {a.file}: ход {S2['meta']['turn']}, статус {S2['status']}"); return

    if a.cmd == "look":
        recompute_env(S); print(report(S, window=a.window)); save(S); return

    if a.cmd == "fight":
        S["meta"]["turn"] += 1; recompute_env(S)
        foes = []
        for spec in a.foe:
            parts = spec.split(":")
            foes.append({"name": parts[0], "target": int(parts[1]),
                         "armor": int(parts[2]) if len(parts) > 2 else 0,
                         "access_s": int(parts[3]) if len(parts) > 3 else 0})
        my_access = min([access_time(S, i) for i in S["items"]
                         if i["id"] in S["gear"]["hands"]["held"]] or [0])
        L = [f"инициатива: у тебя {my_access} с до оружия"]
        order = sorted(foes, key=lambda f: f["access_s"])
        for f in order:
            lead = my_access - f["access_s"]
            L.append(f"  {f['name']}: {f['access_s']} с -> "
                     + (f"опережает тебя на {lead} с" if lead > 0
                        else f"ты опережаешь на {-lead} с" if lead < 0 else "одновременно"))
        # обмены: каждый противник по очереди, не более трёх обменов
        for ex in range(1, 4):
            alive_foes = [f for f in foes if not f.get("down")]
            if not alive_foes: break
            L.append(f"— обмен {ex} —")
            for k, f in enumerate(alive_foes):
                o = opposed(S, a.skill, f["name"], f["target"], f"схватка/{f['name']}", ex*10 + k)
                if o["winner"] == "противник":
                    nm, bl, pct, pen = wound_from(o["delta"], 0)
                    S["pc"]["wounds"].append({"name": f"{nm} от {f['name']}", "bleed_pct_h": pct,
                                              "penalty": pen, "dirty": True})
                    L.append(f"  {f['name']} достаёт тебя: {nm}, {bl}, {pct}%/ч, штраф −{pen}")
                elif o["winner"] == "игрок":
                    nm, bl, pct, pen = wound_from(o["delta"], f["armor"])
                    L.append(f"  ты достаёшь {f['name']}: {nm}, {bl}")
                    if o["delta"] - f["armor"] > 30: f["down"] = True; L.append(f"  {f['name']} выведен из боя")
                else:
                    L.append(f"  с {f['name']} разошлись, оба в мыле")
            # раны, полученные в этой же схватке, сразу ухудшают следующий обмен
            tick(S, 3/3600, activity=2, log=L)
            if S["status"] != "alive":
                L.append(f"  схватка окончена: {S['status']}"); break
            WM = rules(S).get("wound_model", {})
            bt = WM.get("bleed_target")
            break_at = WM.get("fight_break_at", 25)
            if bt and S["pc"]["vitals"].get(bt, 0) >= break_at:
                L.append("  " + WM.get("fight_break_note",
                                       "потери слишком велики — ты выходишь из схватки")); break
            pen_sum = sum(w.get("penalty", 0) for w in S["pc"]["wounds"])
            if pen_sum >= 60:
                L.append("  ты больше не можешь драться"); break
        print(report(S, log=L, window=3)); save(S); return

    if a.minutes < 0:
        print("ОТКАЗ: время не идёт назад. Длительность действия не может быть отрицательной."); return
    R0 = rules(S)
    lim = R0.get("resolution", {}).get("max_checks_per_turn", 2)
    if len(a.check) > lim:
        print(f"ОТКАЗ: {len(a.check)} проверок за ход при лимите {lim}. "
              f"Ход слишком крупный — разбей его на несколько."); return
    S["meta"]["turn"] += 1
    if a.to:
        paths = {x["path"] for x in S["world"]["sites_canon"]}
        if a.to not in paths:
            print(f"ОТКАЗ: площадки '{a.to}' нет в sites_canon. "
                  f"Сначала сгенерируй её (см. Часть 6/7 ядра), потом переходи."); return
        S["position"]["path"] = a.to
        S["position"]["local"] = a.to.split("/")[-1]
    if a.local: S["position"]["local"] = a.local
    if a.z is not None: S["position"]["z_m"] = a.z
    log = tick(S, a.minutes/60, a.activity, a.sheltered, a.fire, a.sleeping, a.water, a.food)
    rolls = []
    for i, spec in enumerate(a.check, start=1):
        f = spec.split(":")
        rolls.append(check(S, f[0], int(f[1]), f[2], i,
                           adv=int(f[3]) if len(f) > 3 and f[3] else 0,
                           domain=f[4] if len(f) > 4 and f[4] else "движение",
                           lethal=(len(f) > 5 and f[5] == "lethal")))
    for iid in a.take:
        for it in S["items"]:
            if it["id"] == iid:
                if len(S["gear"]["hands"]["held"]) >= S["gear"]["hands"]["slots"]:
                    log.append(f"[ОТКАЗ] руки заняты, {it['name']} не взять"); break
                it["in"] = "cnt_00"; S["gear"]["hands"]["held"].append(iid)
                log.append(f"в руки: {it['name']}")
    for spec in a.stow:
        iid, cid = spec.split(":")
        cont = {c["id"]: c for c in S["gear"]["containers"]}[cid]
        it = next(x for x in S["items"] if x["id"] == iid)
        inside = [x for x in S["items"] if x["in"] == cid]
        vol = sum(x["l"] * x.get("qty", 1) for x in inside) + it["l"]
        mas = sum(x["kg"] * x.get("qty", 1) for x in inside) + it["kg"]
        cap_l, cap_kg = cont.get("cap_l"), cont.get("cap_kg")
        if cap_l and vol > cap_l * (1.3 if not cont.get("rigid") else 1.0):
            log.append(f"[ОТКАЗ] {it['name']} не влезает в {cont['name']} по объёму ({vol:.1f}>{cap_l})")
        elif cap_kg and mas > cap_kg:
            log.append(f"[ОТКАЗ] {it['name']} перегружает {cont['name']} ({mas:.1f}>{cap_kg} кг)")
        else:
            it["in"] = cid; it["depth"] = len(inside)
            if iid in S["gear"]["hands"]["held"]: S["gear"]["hands"]["held"].remove(iid)
            log.append(f"убрано: {it['name']} -> {cont['name']}")
    print(report(S, rolls=rolls, log=log, window=a.window)); save(S)

if __name__ == "__main__":
    main()
