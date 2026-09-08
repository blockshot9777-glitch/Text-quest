#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ядро текстового симулятора. Считает всё, что модель считать не умеет."""
import json, math, hashlib, argparse, os, sys, copy, random
try:
    import society
except ImportError:
    society = None
try:
    import matter
except ImportError:
    matter = None

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

def core_temp(cs, S=None):
    cm = rules(S).get("cold_model", {})
    base = cm.get("core_base_c", 37)
    start = cm.get("core_drop_start", 30)
    span = cm.get("core_drop_span", 70) or 70
    drop = cm.get("core_drop_c", 9)
    return base - drop * max(0.0, cs - start) / span

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

def _matter_fn(name):
    """В сборке matter.py влит в тот же модуль; отдельно — обычный импорт."""
    m = sys.modules.get("matter")
    if m is None:
        m = sys.modules[__name__]
    return getattr(m, name)

def next_item_id(S):
    n = 0
    for it in S.get("items") or []:
        iid = it.get("id") or ""
        if iid.startswith("itm_"):
            try:
                n = max(n, int(iid[4:]))
            except ValueError:
                pass
    return f"itm_{n+1:02d}"

def resource_tags(res):
    """Теги только из данных. Имя «кипяток» само по себе ничего не значит."""
    if res.get("tags"):
        return list(res["tags"])
    return ["ресурс"]


def use_tags(S, key):
    """Список тегов из item_use[key]. Пустой — глагол CLI к этому существу не привязан."""
    return list((rules(S).get("item_use") or {}).get(key) or [])

def find_site_resource(site, query):
    q = (query or "").strip().lower()
    if not q:
        return None, "пустой запрос"
    pool = list(site.get("resources") or [])
    hits = []
    for r in pool:
        names = (r.get("name") or "").lower()
        tags = [t.lower() for t in (r.get("tags") or [])]
        if q == names or q in names or q in tags:
            hits.append(r)
    # уникальные объекты, не дубли по двум условиям
    uniq, seen = [], set()
    for r in hits:
        k = id(r)
        if k not in seen:
            seen.add(k); uniq.append(r)
    if not uniq:
        return None, f"на площадке нет ресурса «{query}»"
    if len(uniq) > 1:
        return None, "несколько ресурсов подходят — уточни имя"
    return uniq[0], None

def item_from_resource(S, res, amount):
    """Порция ресурса — предмет из вещества, не строка в журнале."""
    make_item = _matter_fn("make_item")
    tech = S.get("profile", {}).get("tech_ceiling", "industrial")
    h = hashlib.sha256(f"{S['meta']['seed']}|{S['meta']['turn']}|{res.get('name')}|{amount}".encode()).digest()
    rng = random.Random(int.from_bytes(h[:8], "big"))
    tags = resource_tags(res)
    name = res.get("name") or "ресурс"
    side = max(1.0, (max(amount, 0.05) * 1000.0) ** (1.0 / 3.0))
    tagset = set(tags)
    if tagset & set(use_tags(S, "water_tags")):
        it = make_item(f"{name} ({amount:g})",
                       [("вода", "жидкость", side, side, side)],
                       tags=tags, tech_ceiling=tech, rng=rng, condition=1.0, packing=1.0)
        it["fill"] = 1.0
    elif tagset & set(use_tags(S, "food_tags")):
        it = make_item(f"{name} ({amount:g})",
                       [("мясо/еда", "сыпучее", side, side, side)],
                       tags=tags, tech_ceiling=tech, rng=rng, condition=1.0, packing=1.0)
        it["fill"] = 1.0
    else:
        it = make_item(f"{name} ({amount:g})",
                       [("дерево", "пластина", max(4.0, side), max(3.0, side * 0.6), 2.0)],
                       tags=tags, tech_ceiling=tech, rng=rng, condition=1.0)
        it["fill"] = 1.0
    it["id"] = next_item_id(S)
    it["qty"] = 1
    it["depth"] = 0
    return it

def place_new_item(S, it, log):
    hands = S["gear"]["hands"]
    if len(hands["held"]) < hands.get("slots", 2):
        it["in"] = "cnt_00"
        hands["held"].append(it["id"])
        S["items"].append(it)
        log.append(f"в руки: {it['name']}")
        return True
    conts = [c for c in S["gear"]["containers"] if c.get("id") != "cnt_00"]
    for c in conts:
        inside = [x for x in S["items"] if x["in"] == c["id"]]
        vol = sum(x["l"] * x.get("qty", 1) for x in inside) + it["l"]
        mas = sum(x["kg"] * x.get("qty", 1) for x in inside) + it["kg"]
        cap_l, cap_kg = c.get("cap_l"), c.get("cap_kg")
        if cap_l and vol > cap_l * (1.3 if not c.get("rigid") else 1.0):
            continue
        if cap_kg and mas > cap_kg:
            continue
        it["in"] = c["id"]
        it["depth"] = len(inside)
        S["items"].append(it)
        log.append(f"убрано: {it['name']} -> {c['name']}")
        return True
    log.append(f"[ОТКАЗ] некуда положить {it['name']}")
    return False

def item_fill(it):
    f = it.get("fill")
    return 1.0 if f is None else float(f)


def item_in_inventory(S, it):
    """Предмет в руках или таре персонажа, не бесхозный."""
    return access_time(S, it) < 999


def resource_fill_cap(S, it, res_tags):
    """Ёмкость порции в единицах resources[].amount. Вода — литры; иначе исходный кг."""
    liquid = bool(set(res_tags or []) & set(use_tags(S, "water_tags")))
    if liquid:
        return float(it.get("l") or 0)
    fill = item_fill(it)
    kg = float(it.get("kg") or 0)
    if fill > 1e-9:
        return kg / fill
    return max(kg, float(it.get("l") or 0))


def fillable_items(S, res_tags):
    """Предметы в доступе с пересечением тегов ресурса и fill < 1. Не имена."""
    want = {t.lower() for t in (res_tags or []) if t}
    out = []
    if not want:
        return out
    for it in S.get("items") or []:
        if not item_in_inventory(S, it):
            continue
        have = {t.lower() for t in (it.get("tags") or [])}
        if not (have & want):
            continue
        fill = item_fill(it)
        if fill >= 1.0 - 1e-9:
            continue
        cap = resource_fill_cap(S, it, res_tags)
        if cap <= 1e-9:
            continue
        space = cap * (1.0 - fill)
        if space <= 1e-9:
            continue
        out.append((it, space, cap))
    out.sort(key=lambda row: access_time(S, row[0]))
    return out


def parse_take_spec(spec):
    name, amt_s = spec, "1"
    if ":" in spec:
        name, amt_s = spec.rsplit(":", 1)
    try:
        amount = float(amt_s)
    except ValueError:
        return None, 0.0, "количество ресурса должно быть числом"
    if amount <= 0:
        return None, 0.0, "взять можно только положительное количество"
    return name.strip(), amount, None


def take_plan(S, spec):
    """План без применения. vessels — (item, space, cap) или None (новый предмет)."""
    name, amount, err = parse_take_spec(spec)
    if err:
        return None, 0.0, None, err
    res, err = find_site_resource(site_of(S), name)
    if err:
        return None, 0.0, None, err
    have = res.get("amount") or 0
    tags = resource_tags(res)
    vessels = fillable_items(S, tags)
    if vessels:
        room = sum(space for _, space, _ in vessels)
        actual = min(amount, have, room)
        if actual <= 1e-9:
            return None, 0.0, None, f"«{res.get('name')}»: в таре с тегом нет места"
        return res, actual, vessels, None
    if amount > have + 1e-9:
        return None, 0.0, None, f"«{res.get('name')}»: нужно {amount:g}, есть {have:g}"
    return res, amount, None, None


def apply_fill_vessels(S, vessels, amount, res_tags, log):
    left = amount
    liquid = bool(set(res_tags or []) & set(use_tags(S, "water_tags")))
    for it, space, cap in vessels:
        if left <= 1e-9:
            break
        take = min(left, space)
        fill = item_fill(it)
        it["fill"] = round(fill + take / cap, 4)
        if liquid:
            it["kg"] = round(max(0.0, (it.get("kg") or 0) + take), 3)
        else:
            it["kg"] = round(cap * it["fill"], 3)
        left -= take
        log.append(f"[ресурс] наполнил «{it.get('name')}»")
    return left <= 1e-9


def take_site_resource(S, spec, log):
    """Списать resources[].amount: сначала тара с тем же тегом и fill<1, иначе новый предмет."""
    res, amount, vessels, err = take_plan(S, spec)
    if err:
        log.append(f"[ОТКАЗ] {err}")
        return False
    have = res.get("amount") or 0
    if vessels is not None:
        apply_fill_vessels(S, vessels, amount, resource_tags(res), log)
        res["amount"] = round(have - amount, 4)
        log.append(f"[ресурс] взял из «{res.get('name')}»")
        return True
    it = item_from_resource(S, res, amount)
    if not place_new_item(S, it, log):
        return False
    res["amount"] = round(have - amount, 4)
    log.append(f"[ресурс] взял из «{res.get('name')}»")
    return True

def tagged_have(S, tag):
    """Сколько запаса с тегом ещё можно выпить/съесть (ёмкость × fill × qty)."""
    liquid = tag in use_tags(S, "water_tags")
    total = 0.0
    for it in S.get("items") or []:
        if tag not in (it.get("tags") or []):
            continue
        cap = it.get("l") if liquid else (it.get("kg") or 0)
        if not cap:
            continue
        fill = it.get("fill")
        if fill is None:
            fill = 1.0
        total += cap * fill * it.get("qty", 1)
    return total

def tagged_have_any(S, tags):
    return sum(tagged_have(S, t) for t in tags)

def consume_tagged(S, tag, amount, log):
    """Списать fill с предметов по тегу. Возвращает фактически взятое количество."""
    if not amount or amount <= 0:
        return 0.0
    got = 0.0
    liquid = tag in use_tags(S, "water_tags")
    items = sorted(S["items"], key=lambda it: access_time(S, it))
    for it in items:
        if tag not in (it.get("tags") or []):
            continue
        cap = it.get("l") if liquid else (it.get("kg") or 0)
        if not cap:
            continue
        fill = it.get("fill")
        if fill is None:
            fill = 1.0
        have = cap * fill * it.get("qty", 1)
        if have <= 0:
            continue
        take = min(amount - got, have)
        remain = have - take
        denom = cap * it.get("qty", 1)
        it["fill"] = round(remain / denom, 4) if denom else 0.0
        it["kg"] = round(max(0.0, (it.get("kg") or 0) - take), 3)
        got += take
        log.append(f"[запас] {it['name']}")
        if got >= amount - 1e-9:
            break
    if got + 1e-9 < amount:
        log.append(f"[запас] {tag}: хватило {got:g} из {amount:g}")
    return got

def consume_tags(S, tags, amount, log):
    got = 0.0
    for tag in tags:
        if got >= amount - 1e-9:
            break
        got += consume_tagged(S, tag, amount - got, log)
    return got

def has_tags_accessible(S, tags, window_s=60):
    """Есть ли предмет с одним из тегов в окне доступа."""
    tags = [t for t in (tags or []) if t]
    if not tags:
        return False
    if window_s is None:
        window_s = 60
    for it in S.get("items") or []:
        if not any(t in (it.get("tags") or []) for t in tags):
            continue
        if access_time(S, it) <= window_s:
            return True
    return False

def structure_use(S):
    return (rules(S).get("structure_use") or {})


def structure_role_tags(S, key):
    return list(structure_use(S).get(key) or [])


def site_objects(st):
    """objects[]: строка (проза) или {name, parts?, tags?}."""
    out = []
    for o in (st.get("objects") or []):
        if isinstance(o, str):
            out.append({"name": o})
        elif isinstance(o, dict) and o.get("name"):
            out.append(o)
    return out


def find_site_object(st, name):
    q = (name or "").strip().lower()
    if not q:
        return None, None, "пустой объект"
    hits = []
    for i, o in enumerate(st.get("objects") or []):
        nm = o if isinstance(o, str) else o.get("name")
        if (nm or "").strip().lower() == q:
            hits.append(i)
    if not hits:
        return None, None, f"на площадке нет объекта «{name}»"
    if len(hits) > 1:
        return None, None, "несколько объектов с этим именем — уточни"
    i = hits[0]
    raw = st["objects"][i]
    return i, (raw if isinstance(raw, dict) else {"name": raw}), None


def structures_of(st):
    return list(st.get("structures") or [])


def structure_has_any_tag(st, tags):
    want = set(tags or [])
    if not want:
        return False
    for s in structures_of(st):
        if not isinstance(s, dict):
            continue
        if want & set(s.get("tags") or []):
            return True
    return False


def blocked_exit_paths(st):
    blocked = set()
    for s in structures_of(st):
        if not isinstance(s, dict):
            continue
        for p in s.get("block_exits") or []:
            if p:
                blocked.add(p)
    return blocked


def site_exits(st):
    blocked = blocked_exit_paths(st)
    return [e for e in (st.get("exits") or []) if e.get("to") not in blocked]


def site_has_hearth(S, st=None):
    st = st if st is not None else site_of(S)
    if st.get("hearth"):
        return True
    return structure_has_any_tag(st, structure_role_tags(S, "hearth_tags"))


def is_sheltered(S, flag=False):
    """Укрытие: флаг хода, поле площадки или конструкция с тегом из structure_use."""
    if flag:
        return True
    st = site_of(S)
    if st.get("shelter"):
        return True
    if structure_has_any_tag(st, structure_role_tags(S, "shelter_tags")):
        return True
    env = st.get("env") or {}
    return bool(env.get("shelter"))

def fuel_have(S):
    tags = (rules(S).get("item_use") or {}).get("fuel_tags") or []
    return sum(tagged_have(S, t) for t in tags)

def can_fire(S, window_s=60):
    """Можно ли жечь этот час: топливо в запасе и чем зажечь (или очаг площадки)."""
    iu = rules(S).get("item_use") or {}
    ft = iu.get("fuel_tags") or []
    if not ft:
        return True
    if fuel_have(S) <= 1e-9:
        return False
    if site_has_hearth(S):
        return True
    return has_tags_accessible(S, iu.get("igniter_tags") or [], window_s)

def spend_fuel(S, hours, log):
    """Списать кг топлива за часы горения. 0 — гореть нечем."""
    iu = rules(S).get("item_use") or {}
    tags = iu.get("fuel_tags") or []
    rate = iu.get("fuel_per_h")
    if not tags or not rate or hours <= 0:
        return 0.0
    need = float(rate) * hours
    got = 0.0
    for tag in tags:
        if got >= need - 1e-9:
            break
        got += consume_tagged(S, tag, need - got, log)
    return got

def fire_refuse(S, window_s=60):
    """Почему --fire сейчас невозможен, или None."""
    iu = rules(S).get("item_use") or {}
    ft = iu.get("fuel_tags") or []
    itags = iu.get("igniter_tags") or []
    if not ft:
        return None
    if fuel_have(S) <= 1e-9:
        shown = " / ".join(ft) or "горючее"
        return f"ОТКАЗ: нечем кормить огонь — нет запаса с тегом «{shown}»."
    if not site_has_hearth(S) and itags and not has_tags_accessible(S, itags, window_s):
        shown = " / ".join(itags) or "зажигатель"
        return f"ОТКАЗ: нечем зажечь — нет предмета с тегом «{shown}» в доступе."
    return None


def parse_part_spec(spec):
    bits = (spec or "").split(":")
    if len(bits) < 5:
        raise ValueError("часть: материал:форма:Д:Ш:В[:стенка_мм]")
    mat, form = bits[0].strip(), bits[1].strip()
    L, W, H = float(bits[2]), float(bits[3]), float(bits[4])
    if len(bits) >= 6:
        return [mat, form, L, W, H, float(bits[5])]
    return [mat, form, L, W, H]


def next_struct_id(S):
    n = 1
    ids = {s.get("id") for st in (S.get("world") or {}).get("sites_canon") or []
           for s in st.get("structures") or [] if isinstance(s, dict)}
    while f"str_{n:02d}" in ids:
        n += 1
    return f"str_{n:02d}"


def material_need_kg(parts, tech_ceiling="industrial"):
    """Сколько кг каждого материала нужно по тем же частям, что make_item."""
    make_item = _matter_fn("make_item")
    unpack_part = _matter_fn("unpack_part")
    part_solid_l = _matter_fn("part_solid_l")
    MATERIALS = _matter_fn("MATERIALS")
    need = {}
    for part in parts:
        mat, form, L, W, H, wall_mm = unpack_part(part)
        dens = MATERIALS[mat][0]
        solid, _ = part_solid_l(form, L, W, H, wall_mm)
        need[mat] = need.get(mat, 0.0) + solid * dens
    _ = make_item  # те же ворота эпохи проверит caller через make_item
    return need


def material_have(S, mat):
    tot = 0.0
    for it in S.get("items") or []:
        if mat not in (it.get("materials") or []):
            continue
        fill = 1.0 if it.get("fill") is None else float(it["fill"])
        tot += (it.get("kg") or 0) * fill * it.get("qty", 1)
    return tot


def consume_material(S, mat, amount, log):
    if not amount or amount <= 0:
        return 0.0
    got = 0.0
    for it in list(S.get("items") or []):
        if mat not in (it.get("materials") or []):
            continue
        fill = 1.0 if it.get("fill") is None else float(it["fill"])
        have = (it.get("kg") or 0) * fill * it.get("qty", 1)
        if have <= 1e-9:
            continue
        take = min(amount - got, have)
        remain = have - take
        it["kg"] = round(remain, 3)
        if remain <= 1e-6:
            iid = it.get("id")
            S["items"] = [x for x in S["items"] if x is not it]
            held = S["gear"]["hands"].get("held") or []
            if iid in held:
                held.remove(iid)
        got += take
        log.append(f"[материал] {it.get('name')}: −{take:g} кг {mat}")
        if got >= amount - 1e-9:
            break
    return got


def build_hours(S, volume_l):
    """Часы = объём × hours_per_l / (навык/ref × инструмент). Коэффициенты в ruleset."""
    su = structure_use(S)
    rate = su.get("hours_per_l")
    if not rate:
        return None
    skill_name = su.get("skill") or "craft"
    skills = (S.get("pc") or {}).get("skills") or {}
    skill = float(skills.get(skill_name, 1) or 1)
    ref = float(su.get("skill_ref") or 40) or 40.0
    tool = 1.0
    tt = su.get("tool_tags") or []
    if tt and has_tags_accessible(S, tt, 60):
        tool = float(su.get("tool_factor") or 1.0) or 1.0
    hours = float(volume_l) * float(rate) / (max(skill, 1.0) / ref * tool)
    lo = float(su.get("min_hours") or 0.1)
    hi = float(su.get("max_hours") or 48)
    return max(lo, min(hi, hours))


def _assemble_parts(S, name, parts, tags, tech):
    make_item = _matter_fn("make_item")
    h = hashlib.sha256(f"{S['meta']['seed']}|{S['meta']['turn']}|{name}".encode()).digest()
    rng = random.Random(int.from_bytes(h[:8], "big"))
    return make_item(name, parts, tags=tags, tech_ceiling=tech, rng=rng, condition=1.0)


def build_refuse(S, name, parts, tags, from_object, minutes, block_exits=None):
    """Почему сборка сейчас невозможна, или None. Ничего не меняет."""
    if not structure_use(S):
        return "ОТКАЗ: --build не к чему привязать — в наборе нет structure_use."
    if not (name or "").strip():
        return "ОТКАЗ: у конструкции нет имени."
    st = site_of(S)
    used_parts = list(parts or [])
    obj = None
    if from_object:
        _, obj, err = find_site_object(st, from_object)
        if err:
            return f"ОТКАЗ: {err}"
        if not used_parts:
            used_parts = list(obj.get("parts") or [])
        if not used_parts:
            return "ОТКАЗ: объект без частей — задай состав, проза не ломается и не строится."
    if not used_parts:
        return "ОТКАЗ: нет частей — конструкция без состава не собирается."
    tech = S.get("profile", {}).get("tech_ceiling", "industrial")
    try:
        it = _assemble_parts(S, name.strip(), used_parts, tags or [], tech)
    except (KeyError, ValueError) as e:
        return f"ОТКАЗ: {e}"
    hours = build_hours(S, it.get("l") or 0)
    if hours is None:
        return "ОТКАЗ: --build не к чему привязать — в structure_use нет hours_per_l."
    if minutes is None or minutes + 1e-9 < hours * 60:
        return (f"ОТКАЗ: на сборку нужно {hours * 60:.0f} мин, дано "
                f"{0 if minutes is None else minutes:g}. Частично не строится.")
    if not from_object:
        need = material_need_kg(used_parts, tech)
        for mat, kg in need.items():
            if material_have(S, mat) + 1e-9 < kg:
                return (f"ОТКАЗ: не хватает материала «{mat}»: нужно {kg:.3f} кг, "
                        f"есть {material_have(S, mat):.3f}. Ничего не списано.")
    if block_exits:
        known = {e.get("to") for e in (st.get("exits") or [])}
        for p in block_exits:
            if p not in known:
                return f"ОТКАЗ: выхода на «{p}» нет — перекрыть нечего."
    return None


def apply_build(S, name, parts, tags, from_object, block_exits, log, player_made=True):
    """Списать материалы или объект и повесить конструкцию. Только после build_refuse is None."""
    st = site_of(S)
    used_parts = list(parts or [])
    if from_object:
        idx, obj, _ = find_site_object(st, from_object)
        if not used_parts:
            used_parts = list(obj.get("parts") or [])
        st["objects"].pop(idx)
        log.append(f"[сборка] объект «{from_object}» стал частями")
    tech = S.get("profile", {}).get("tech_ceiling", "industrial")
    it = _assemble_parts(S, name.strip(), used_parts, tags or [], tech)
    if not from_object:
        for mat, kg in material_need_kg(used_parts, tech).items():
            consume_material(S, mat, kg, log)
    struct = {
        "id": next_struct_id(S),
        "name": name.strip(),
        "parts": [list(p) for p in used_parts],
        "tags": list(tags or []),
        "kg": it["kg"],
        "l": it["l"],
        "materials": list(it.get("materials") or []),
        "player_made": bool(player_made),
        "block_exits": list(block_exits or []),
        "on_break": [],
    }
    st.setdefault("structures", []).append(struct)
    st["touched"] = True
    log.append(f"[сборка] {struct['name']} ({struct['kg']} кг, {struct['l']} л)")
    return struct


def reveal_refuse(S, name, parts, minutes):
    if not structure_use(S):
        return "ОТКАЗ: --reveal не к чему привязать — в наборе нет structure_use."
    st = site_of(S)
    _, obj, err = find_site_object(st, name)
    if err:
        return f"ОТКАЗ: {err}"
    used = list(parts or []) or list(obj.get("parts") or [])
    if not used:
        return "ОТКАЗ: проза без частей остаётся неразрушимой — задай состав."
    return build_refuse(S, name, used, obj.get("tags") or [], name, minutes, None)


def apply_reveal(S, name, parts, log):
    st = site_of(S)
    _, obj, _ = find_site_object(st, name)
    used = list(parts or []) or list(obj.get("parts") or [])
    return apply_build(S, name, used, obj.get("tags") or [], name, None, log, player_made=False)


def find_structure(st, name):
    q = (name or "").strip().lower()
    if not q:
        return None, "пустое имя"
    hits = [s for s in structures_of(st) if isinstance(s, dict) and
            ((s.get("id") or "").lower() == q
             or (s.get("name") or "").lower() == q)]
    if not hits:
        return None, f"конструкции «{name}» нет"
    if len(hits) > 1:
        return None, "несколько конструкций подходят — уточни id"
    return hits[0], None


def break_refuse(S, name, minutes):
    if not structure_use(S):
        return "ОТКАЗ: --break не к чему привязать — в наборе нет structure_use."
    st = site_of(S)
    struct, err = find_structure(st, name)
    if err:
        _, obj, oerr = find_site_object(st, name)
        if obj is not None and not oerr:
            if not (obj.get("parts") or []):
                return "ОТКАЗ: объект без частей — сначала состав (--reveal), проза не ломается."
            return "ОТКАЗ: это ещё проза/объект — сначала --reveal, потом --break."
        return f"ОТКАЗ: {err}"
    if not (struct.get("parts") or []):
        return "ОТКАЗ: у конструкции нет частей — ломать нечего."
    hours = build_hours(S, struct.get("l") or 0)
    if hours is None:
        return "ОТКАЗ: --break не к чему привязать — в structure_use нет hours_per_l."
    wreck = max(float(structure_use(S).get("min_hours") or 0.1), hours * 0.35)
    if minutes is None or minutes + 1e-9 < wreck * 60:
        return (f"ОТКАЗ: на разбор нужно {wreck * 60:.0f} мин, дано "
                f"{0 if minutes is None else minutes:g}. Частично не ломается.")
    return None


def apply_break(S, name, log):
    """Снять конструкцию целиком. Роль (укрытие/очаг) висит на тегах
    конструкции, не на «крыше» или «стене». Одну часть из трёх снять
    нельзя — такой команды нет. on_break сливается в состояние; укрытие
    пересчитается в том же тике.
    """
    st = site_of(S)
    struct, _ = find_structure(st, name)
    st["structures"] = [s for s in structures_of(st) if s is not struct]
    st["touched"] = True
    if struct.get("on_break"):
        apply_clock_effects(S, {"name": struct.get("name"), "on_complete": struct["on_break"]},
                            log, tag="разбор")
    if struct.get("hazard"):
        hz = st.setdefault("hazards", [])
        if struct["hazard"] not in hz:
            hz.append(struct["hazard"])
        log.append(f"[разбор] опасность: {struct['hazard']}")
    log.append(f"[разбор] {struct.get('name')} снят")
    return struct


def site_kept_after_compact(st, here, neigh):
    """Площадку с player_made не выбрасывать. Повторный compact не снимает флаг."""
    if st.get("touched") or st.get("path") == here or st.get("path") in neigh:
        return True
    return any(isinstance(s, dict) and s.get("player_made") for s in structures_of(st))


def spend_held_charge(S, hours, log):
    rate = (rules(S).get("item_use") or {}).get("charge_per_h")
    if not rate or hours <= 0:
        return
    held = set(S["gear"]["hands"].get("held") or [])
    for it in S["items"]:
        if "charge_pct" not in it or it.get("id") not in held:
            continue
        before = it["charge_pct"]
        it["charge_pct"] = max(0.0, round(before - rate * hours, 2))
        if before > 0 and it["charge_pct"] <= 0:
            log.append(f"[заряд] {it['name']} сел.")

def spend_medicine_fill(S, log):
    frac = (rules(S).get("item_use") or {}).get("medicine_fill_per_treat", 0.0)
    if not frac:
        return
    for it in S["items"]:
        if "медицина" not in (it.get("tags") or []):
            continue
        if "fill" not in it:
            it["fill"] = 1.0
        it["fill"] = max(0.0, round(it["fill"] - frac, 3))
        log.append(f"[запас] {it['name']}")
        return

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
    if r is not None:
        skill_grow(S, skill, out)
    return {"label": label, "skill": skill, "base": base, "factor": round(f, 3), "notes": notes,
            "difficulty": difficulty, "adv": adv, "raw": round(raw, 1), "target": target,
            "roll": r, "outcome": out, "consequence": cons, "repeat": None}


def skill_grow(S, skill, outcome):
    """Рост из ruleset.skill_growth: поле без вызова — ложь. Молча, без цифр игроку."""
    g = rules(S).get("skill_growth") or {}
    on = g.get("on") or []
    if not any(tag and tag in outcome for tag in on):
        return
    skills = S["pc"].setdefault("skills", {})
    default = rules(S).get("skill_default", 30)
    cur = skills.get(skill, default)
    cap = g.get("cap", 90)
    amount = int(g.get("amount", 1) or 0)
    per = g.get("per_day_per_skill", 1)
    if amount <= 0 or cur >= cap:
        return
    day_h = S["calendar"].get("day_hours", 24) or 24
    day = int(S["time"]["t_h"] // day_h)
    recs = S["pc"].setdefault("skill_growth_day", {})
    rec = recs.get(skill) or {"day": day, "gained": 0}
    if rec.get("day") != day:
        rec = {"day": day, "gained": 0}
    remain = max(0, per - rec.get("gained", 0))
    add = min(amount, remain, cap - cur)
    if add <= 0:
        recs[skill] = rec
        return
    skills[skill] = cur + add
    rec["gained"] = rec.get("gained", 0) + add
    rec["day"] = day
    recs[skill] = rec

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
    # иначе поля нет: пустое po2 при выключенной гипоксии — ложный warn validate
    return e

def tick(S, hours, activity=1, sheltered=False, fire=False, sleeping=False,
         water=0.0, food=0.0, log=None):
    """Дробит время по часам и считает среду ВНУТРИ действия."""
    log = log if log is not None else []
    rem, n, mult = hours, S["pc"]["needs"], load_penalty(load_state(S)[2])[1]
    def _status_tick(S, log):
        was = S.get("status")
        d = death_check(S)
        if was == "unconscious" and S.get("status") == "alive":
            log.append(f"[{fmt_time(S)}] пришёл в себя")
        return d
    while rem > 1e-6:
        h = min(1.0, rem); rem -= h
        S["time"]["t_h"] += h
        # Часы → среда → нужды этого часа. on_complete не читает уже
        # пересчитанный envelope («если было холоднее X»); исключению
        # нужен второй проход, не сдвиг этой строки.
        tick_clocks(S, log)
        sheltered = is_sheltered(S, sheltered)
        if fire:
            iu = rules(S).get("item_use") or {}
            if iu.get("fuel_tags"):
                if spend_fuel(S, h, log) <= 0:
                    fire = False
                    log.append("[огонь] топливо кончилось.")
        recompute_env(S, sheltered, fire)
        wet_step(S, h, sheltered, fire)
        R = rules(S)
        cm = R.get("cold_model", {})
        need_key = cm.get("need")
        on = S["profile"].get("physics_on", [])
        if "холод" in on and need_key and need_key in n:
            clo = clo_total(S)
            cr = cold_rate(S["envelope"].get("windchill_c", 0), clo, activity, S)
            n[need_key] = max(0.0, min(100.0, n[need_key] + cr * h))
        if "радиация" in on:
            e = S["envelope"]
            rate = e.get("dose_rate_msv_h") or 0
            e["dose_sv"] = round((e.get("dose_sv") or 0) + (rate / 1000.0) * h, 6)
        ND = R.get("needs", {}); hi = R.get("scales", {}).get("max", 100)
        for key, spec in ND.items():
            if key == need_key or key not in n: continue
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
        vital_key = cm.get("core_vital")
        if not vital_key or vital_key not in v or not need_key or need_key not in n:
            d = _status_tick(S, log)
            if d: log.append(f"[{fmt_time(S)}] ПРЕРВАНО: {d}"); return log
            continue
        tgt = core_temp(n.get(need_key, 0), S)
        cur = v.get(vital_key)
        step_h = (R.get("vitals", {}).get(vital_key) or {}).get("max_change_per_h", 0.5)
        step = step_h * h
        v[vital_key] = round(cur + max(-step, min(step, tgt - cur)), 2)
        d = _status_tick(S, log)
        if d:
            log.append(f"[{fmt_time(S)}] ПРЕРВАНО: {d}")
            return log
    # 2.5 л/сутки ≈ 36 единиц/сутки -> 1 л = 14.4 единицы; 2500 ккал/сутки ≈ 7.2 ед -> 1000 ккал = 2.9
    R = rules(S)
    def _replenish(amount, kind):
        """Находит потребность по тому, ЧЕМ она восполняется, а не по имени поля.
        Работает для любого вида: воду пьёт человек, заряд берёт механоид."""
        if not amount:
            return False
        for key, spec in R.get("needs", {}).items():
            if spec.get("recovers_by") == kind and key in n:
                upp = spec.get("unit_per_point")
                n[key] = max(0.0, n[key] - (amount / upp if upp else amount))
                return True
        return False
    if water:
        for kind in use_tags(S, "water_tags"):
            if _replenish(water, kind):
                break
    if food:
        for kind in use_tags(S, "food_tags"):
            if _replenish(food, kind):
                break
    npc_step(S, log, hours*60)
    if society is not None:
        society.society_step(S, log, hours, rules(S))
    weather_step(S, log)
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

    if S["status"] == "unconscious":
        for key, spec in R.get("vitals", {}).items():
            rec = spec.get("recover_above")
            val = v.get(key)
            if rec is not None and val is not None and val >= rec:
                S["status"] = "alive"
                break

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
        npc.setdefault("knows_about_pc", [])
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

CLOCK_PATH_ROOTS = ("pc", "world", "time", "envelope", "meta", "position", "profile", "calendar")

def _clock_target_sites(S, fx):
    canon = (S.get("world") or {}).get("sites_canon") or []
    if "site" in fx:
        return [st for st in canon if st.get("path") == fx["site"]]
    sel = fx.get("sites")
    if sel == "*":
        # Только площадки, уже лежащие в sites_canon и имеющие env.
        # Позже сгенерированные (и вернувшиеся после compact) не наследуют
        # прошедшее событие: игрок ту стадию просто не застал.
        return [st for st in canon if isinstance(st.get("env"), dict)]
    if isinstance(sel, list):
        want = set(sel)
        return [st for st in canon if st.get("path") in want]
    return []

def _clock_set_path(S, path, set_v=None, add_v=None):
    parts = [p for p in str(path).split(".") if p]
    if not parts or parts[0] not in CLOCK_PATH_ROOTS:
        return False
    cur = S
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return False
        cur = cur[p]
    k = parts[-1]
    if not isinstance(cur, dict):
        return False
    if add_v is not None:
        if k not in cur:
            return False
        try:
            cur[k] = (cur[k] or 0) + add_v
        except TypeError:
            return False
        return True
    cur[k] = set_v
    return True

def apply_clock_effects(S, clock, log, tag="счётчик"):
    """Мутации из on_complete (и тот же словарь у разбора конструкции).
    add не идемпотентен и не обязан быть: два счётчика на одно поле
    складываются — выбор автора данных, не пробел движка. set безопасен
    повтором. Повтор одного счётчика режет флаг fired в tick_clocks.
    Пересчёт envelope делает tick() после часов, со флагами sheltered/fire."""
    effects = clock.get("on_complete") or []
    if not effects:
        return
    for fx in effects:
        if not isinstance(fx, dict):
            log.append(f"[{tag}] {clock.get('name','?')}: пропуск кривой операции")
            continue
        env_op = "env" in fx and ("site" in fx or "sites" in fx)
        has_set, has_add = "set" in fx, "add" in fx
        path_op = "path" in fx and (has_set or has_add) and not (has_set and has_add)
        if env_op and not path_op:
            patch = fx.get("env")
            if not isinstance(patch, dict):
                log.append(f"[{tag}] {clock.get('name','?')}: env должен быть объектом")
                continue
            targets = _clock_target_sites(S, fx)
            if not targets:
                log.append(f"[{tag}] {clock.get('name','?')}: площадка не найдена")
                continue
            for st in targets:
                if not isinstance(st.get("env"), dict):
                    continue
                st["env"].update(patch)
                log.append(f"[{tag}] {clock.get('name','?')}: {st.get('path')} env {patch}")
        elif path_op and not env_op:
            ok = _clock_set_path(S, fx["path"], fx.get("set") if has_set else None,
                                 fx.get("add") if has_add else None)
            if ok:
                how = f"+={fx['add']}" if has_add else f"={fx['set']}"
                log.append(f"[{tag}] {clock.get('name','?')}: {fx['path']} {how}")
            else:
                log.append(f"[{tag}] {clock.get('name','?')}: путь {fx.get('path')} не найден")
        else:
            log.append(f"[{tag}] {clock.get('name','?')}: неизвестная операция")

def tick_clocks(S, log):
    for c in S["clocks"]:
        period = c.get("period_h") or 0
        if period <= 0:
            continue
        k = int((S["time"]["t_h"] - c["last_tick_h"]) // period)
        if k > 0:
            c["last_tick_h"] += k * period
            before = c["filled"]
            c["filled"] = min(c["max"], c["filled"] + k)
            if c["filled"] >= c["max"]:
                if c.get("fired"):
                    continue
                if before < c["max"]:
                    c["fired"] = True
                    log.append(f"[СЧЁТЧИК СРАБОТАЛ] {c['name']}: {c['payoff']}")
                    apply_clock_effects(S, c, log)
                else:
                    # Уже был на max без флага (старое сохранение) — не переигрывать.
                    c["fired"] = True
            elif c["filled"] != before and not c.get("fired"):
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
    p.add_argument("--water", type=float, default=0,
                   help="списать fill по item_use.water_tags (синоним CLI; без объявления — отказ)")
    p.add_argument("--food", type=float, default=0,
                   help="списать fill по item_use.food_tags (синоним CLI; без объявления — отказ)")
    p.add_argument("--take-resource", dest="take_resource", action="append", default=[],
                   help="имя:количество — наполнить предмет с тем же тегом (fill<1), иначе создать новый")
    p.add_argument("--build", default=None,
                   help="собрать конструкцию из частей (теги и материал, не тип постройки)")
    p.add_argument("--build-part", dest="build_part", action="append", default=[],
                   help="материал:форма:Д:Ш:В[:стенка_мм] — та же схема, что make_item")
    p.add_argument("--build-tag", dest="build_tag", action="append", default=[],
                   help="тег роли из structure_use (укрытие/очаг и любые чужие)")
    p.add_argument("--from-object", dest="from_object", default=None,
                   help="взять состав из objects[] площадки (проза без parts — отказ)")
    p.add_argument("--build-block", dest="build_block", action="append", default=[],
                   help="путь выхода, который конструкция перекрывает")
    p.add_argument("--break", dest="break_name", default=None,
                   help="снять конструкцию по имени или id; on_break меняет состояние")
    p.add_argument("--reveal", default=None,
                   help="перевести objects[] в конструкцию с частями, без роли")
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
            spend_medicine_fill(S, L)
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
                                     if site_kept_after_compact(st, here, neigh)]
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
    if S.get("status") == "dead":
        print("ОТКАЗ: мёртв."); return
    if S.get("status") == "unconscious":
        acting = bool(a.check or a.to or a.take or a.water or a.food or a.take_resource or a.fire
                      or a.build or a.break_name or a.reveal)
        if acting:
            print("ОТКАЗ: без сознания нельзя действовать. Тело всё ещё в этой среде."); return
    R0 = rules(S)
    lim = R0.get("resolution", {}).get("max_checks_per_turn", 2)
    if len(a.check) > lim:
        print(f"ОТКАЗ: {len(a.check)} проверок за ход при лимите {lim}. "
              f"Ход слишком крупный — разбей его на несколько."); return
    wt, ft = use_tags(S, "water_tags"), use_tags(S, "food_tags")
    if a.water:
        if not wt:
            print("ОТКАЗ: --water не к чему привязать — в item_use нет water_tags."); return
        if tagged_have_any(S, wt) <= 1e-9:
            print(f"ОТКАЗ: пить нечего — нет запаса с тегом «{' / '.join(wt)}»."); return
    if a.food:
        if not ft:
            print("ОТКАЗ: --food не к чему привязать — в item_use нет food_tags."); return
        if tagged_have_any(S, ft) <= 1e-9:
            print(f"ОТКАЗ: есть нечего — нет запаса с тегом «{' / '.join(ft)}»."); return
    if a.fire:
        why = fire_refuse(S, a.window)
        if why:
            print(why); return
    if sum(bool(x) for x in (a.build, a.break_name, a.reveal)) > 1:
        print("ОТКАЗ: сборка, разбор и reveal — по одному за ход, не пачкой."); return
    parts = []
    for spec in (a.build_part or []):
        try:
            parts.append(parse_part_spec(spec))
        except ValueError as e:
            print(f"ОТКАЗ: {e}"); return
    if a.build:
        why = build_refuse(S, a.build, parts, a.build_tag, a.from_object, a.minutes, a.build_block)
        if why:
            print(why); return
    if a.reveal:
        why = reveal_refuse(S, a.reveal, parts, a.minutes)
        if why:
            print(why); return
    if a.break_name:
        why = break_refuse(S, a.break_name, a.minutes)
        if why:
            print(why); return
    if a.to:
        paths = {x["path"] for x in S["world"]["sites_canon"]}
        if a.to not in paths:
            print(f"ОТКАЗ: площадки '{a.to}' нет в sites_canon. "
                  f"Сначала сгенерируй её (см. Часть 6/7 ядра), потом переходи."); return
        if a.to in blocked_exit_paths(site_of(S)):
            print(f"ОТКАЗ: выход на «{a.to}» перекрыт конструкцией."); return
    S["meta"]["turn"] += 1
    if a.to:
        S["position"]["path"] = a.to
        S["position"]["local"] = a.to.split("/")[-1]
    if a.local: S["position"]["local"] = a.local
    if a.z is not None: S["position"]["z_m"] = a.z
    log = []
    if a.build:
        apply_build(S, a.build, parts, a.build_tag, a.from_object, a.build_block, log)
    if a.reveal:
        apply_reveal(S, a.reveal, parts, log)
    if a.break_name:
        apply_break(S, a.break_name, log)
    for spec in (a.take_resource or []):
        take_site_resource(S, spec, log)
    water = consume_tags(S, wt, a.water, log) if a.water else 0.0
    food = consume_tags(S, ft, a.food, log) if a.food else 0.0
    log = tick(S, a.minutes/60, a.activity, a.sheltered, a.fire, a.sleeping, water, food, log)
    spend_held_charge(S, a.minutes/60, log)
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
