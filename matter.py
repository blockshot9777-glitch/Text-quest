#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Вещество вместо каталога.

Перечислить все предметы мира невозможно. Материалов — конечное число.
Поэтому предмет описывается формой, размерами и материалом, а масса,
объём, прочность и поведение ВЫЧИСЛЯЮТСЯ.

Библиотека перестаёт быть белым списком и становится кэшем: новая вещь
собирается по требованию и замораживается в канон, как площадка.
"""
import math, random

# ─────────── МАТЕРИАЛЫ ───────────
# плотность кг/л · твёрдость 0-10 · горючесть 0-1 · теплопроводность отн. ·
# впитывает воду · минимальная эпоха
MATERIALS = {
 "дерево":      (0.60, 3, 0.9, 0.15, 0.35, "primitive"),
 "дерево твёрдое":(0.78,4, 0.8, 0.17, 0.25, "primitive"),
 "кость":       (1.80, 4, 0.3, 0.20, 0.10, "primitive"),
 "рог":         (1.30, 4, 0.4, 0.18, 0.10, "primitive"),
 "кожа":        (0.90, 2, 0.6, 0.10, 0.45, "primitive"),
 "ткань":       (0.40, 1, 0.9, 0.08, 0.90, "primitive"),
 "шерсть":      (0.30, 1, 0.8, 0.05, 0.85, "primitive"),
 "камень":      (2.60, 6, 0.0, 1.00, 0.02, "primitive"),
 "глина":       (1.90, 2, 0.0, 0.60, 0.30, "primitive"),
 "керамика":    (2.30, 6, 0.0, 0.90, 0.02, "primitive"),
 "верёвка растит.":(0.85,2,0.9, 0.08, 0.80, "primitive"),
 "медь":        (8.96, 3, 0.0, 9.00, 0.00, "preindustrial"),
 "бронза":      (8.80, 5, 0.0, 3.00, 0.00, "preindustrial"),
 "железо":      (7.60, 5, 0.0, 3.00, 0.00, "preindustrial"),
 "сталь":       (7.85, 7, 0.0, 3.00, 0.00, "preindustrial"),
 "свинец":      (11.3, 1, 0.0, 1.60, 0.00, "preindustrial"),
 "серебро":     (10.5, 3, 0.0, 9.70, 0.00, "preindustrial"),
 "золото":      (19.3, 3, 0.0, 9.20, 0.00, "preindustrial"),
 "стекло":      (2.50, 6, 0.0, 0.35, 0.00, "preindustrial"),
 "бумага":      (0.80, 1, 1.0, 0.08, 0.95, "preindustrial"),
 "сталь легир.":(7.90, 8, 0.0, 2.20, 0.00, "industrial"),
 "алюминий":    (2.70, 3, 0.0, 8.60, 0.00, "industrial"),
 "пластик":     (1.05, 3, 0.7, 0.09, 0.00, "industrial"),
 "резина":      (1.20, 2, 0.8, 0.06, 0.00, "industrial"),
 "электроника": (2.00, 2, 0.4, 1.20, 0.00, "industrial"),
 "литий-ионный":(2.40, 1, 0.9, 0.60, 0.00, "industrial"),
 "титан":       (4.50, 8, 0.0, 0.90, 0.00, "spacefaring"),
 "композит":    (1.60, 7, 0.3, 0.20, 0.00, "spacefaring"),
 "вода":        (1.00, 0, 0.0, 0.25, 1.00, "primitive"),
 "лёд":         (0.92, 2, 0.0, 0.90, 1.00, "primitive"),
 "зерно":       (0.78, 0, 0.6, 0.05, 0.60, "primitive"),
 "мясо/еда":    (1.02, 0, 0.3, 0.15, 0.70, "primitive"),
 "мех":         (0.90, 1, 0.7, 0.04, 0.60, "primitive"),
 "пух":         (0.90, 0, 0.8, 0.02, 0.75, "primitive"),
 "войлок":      (0.30, 1, 0.8, 0.05, 0.85, "primitive"),
 "синтетика":   (1.35, 2, 0.7, 0.07, 0.05, "industrial"),
 "аэрогель":    (0.15, 1, 0.0, 0.01, 0.00, "spacefaring"),
}

# ПУХЛОСТЬ: какая доля объёма ткани — собственно волокно, остальное воздух.
# Без этого вязаный свитер выходит втрое тяжелее настоящего.
LOFT = {"ткань":0.42,"шерсть":0.38,"войлок":0.55,"мех":0.16,"пух":0.055,
        "синтетика":0.30,"кожа":0.92,"аэрогель":0.60,"верёвка растит.":0.79}

ERA_RANK = {"primitive":0,"preindustrial":1,"industrial":2,"spacefaring":3,"interstellar":4}

# ─────────── ФОРМЫ: какая доля габарита действительно занята веществом ───────────
FORMS = {
 "клинок":       0.85,   # плоское лезвие, почти сплошное
 "пластина":     0.90,
 "стержень":     0.75,   # рукоять, древко, палка
 "обух":         0.55,   # топорное полотно с проушиной
 "сосуд":        None,   # считается по толщине стенки, а не долей объёма
 "мех/бурдюк":   None,
 "шнур":         0.79,   # круглое сечение внутри габаритного квадрата
 "свёрток ткани":0.55,
 "плетение":     0.35,   # кольчуга, корзина — плотное переплетение
 "сеть":         0.03,   # почти сплошные дырки
 "устройство":   0.95,   # плотная слоистая начинка, пустот почти нет
 "сыпучее":      0.95,   # содержимое насыпано плотно
 "жидкость":     1.00,
}

def extend_from_rules(rules):
    """Материалы и формы можно объявлять в наборе правил — код не нужно трогать.
    Закрывает последнюю жёстко зашитую таблицу: экзотика сеттинга живёт в данных."""
    added = []
    for name, spec in (rules.get("materials") or {}).items():
        if name in MATERIALS: continue
        MATERIALS[name] = (spec["density_kg_l"], spec.get("hardness", 3),
                           spec.get("flammability", 0.0), spec.get("thermal", 1.0),
                           spec.get("soaks", 0.0), spec.get("era", "primitive"))
        if "loft" in spec: LOFT[name] = spec["loft"]
        added.append(name)
    for name, fill in (rules.get("forms") or {}).items():
        if name not in FORMS:
            FORMS[name] = fill; added.append(name)
    for era, rank in (rules.get("era_rank") or {}).items():
        ERA_RANK.setdefault(era, rank)
    return added


def volume_l(l_cm, w_cm, h_cm):
    """Габаритный объём в литрах."""
    return l_cm * w_cm * h_cm / 1000.0

# Габарит одной части: не молекула и не материк. Ловит опечатку модели, не вкус.
DIM_MIN_CM = 0.01
DIM_MAX_CM = 50000.0


def unpack_part(part):
    """Часть — кортеж или список из 5 или 6 полей (стенка_мм у полой формы)."""
    part = list(part)
    if len(part) == 6:
        mat, form, L, W, H, wall_mm = part
    elif len(part) == 5:
        mat, form, L, W, H = part
        wall_mm = None
    else:
        raise ValueError(f"часть: нужно 5 или 6 полей, не {len(part)}")
    return mat, form, float(L), float(W), float(H), wall_mm


def part_solid_l(form, L, W, H, wall_mm=None):
    v = volume_l(L, W, H)
    fill = FORMS[form]
    if fill is None:
        t_cm = (wall_mm or 1.5) / 10.0
        area = 2 * (L * W + L * H + W * H)
        return area * t_cm / 1000.0, v
    return v * fill, v


def check_plausible(name, parts, kg, gross_l):
    """Грубая проверка абсурда: плотность и габарит vs вещество, не каталог вещей.

    Ловит «2 кг из сорока тонн камня» и нож на 100 кг в спичечном объёме.
    Не знает имён построек — только вещество, форма и размер.
    """
    if not parts:
        raise ValueError(f"{name}: нет частей")
    dens_list, solid_l = [], 0.0
    for part in parts:
        mat, form, L, W, H, wall_mm = unpack_part(part)
        if mat not in MATERIALS:
            raise KeyError(f"нет материала: {mat}")
        if form not in FORMS:
            raise KeyError(f"нет формы: {form}")
        if min(L, W, H) < DIM_MIN_CM:
            raise ValueError(f"{name}: размер {min(L, W, H):g} см меньше {DIM_MIN_CM:g}")
        if max(L, W, H) > DIM_MAX_CM:
            raise ValueError(f"{name}: габарит {max(L, W, H):g} см вне разумного")
        dens_list.append(MATERIALS[mat][0])
        solid, _ = part_solid_l(form, L, W, H, wall_mm)
        solid_l += solid
    if kg <= 0:
        raise ValueError(f"{name}: масса {kg} кг — абсурд")
    if solid_l > 1e-12:
        dens_m = kg / solid_l
        lo, hi = min(dens_list) * 0.2, max(dens_list) * 5.0
        if dens_m < lo or dens_m > hi:
            raise ValueError(
                f"{name}: плотность вещества {dens_m:.4g} кг/л вне {lo:.4g}–{hi:.4g}")
    if gross_l > 1e-9:
        bulk = kg / gross_l
        if bulk > max(dens_list) * 5.0:
            raise ValueError(
                f"{name}: масса {kg:g} кг в {gross_l:g} л плотнее вещества")
        if bulk < 1e-4:
            raise ValueError(
                f"{name}: масса {kg:g} кг в {gross_l:g} л — пустота, не конструкция")


def make_item(name, parts, tags=None, tech_ceiling="industrial", rng=None,
              condition=None, packing=0.75):
    """parts: [(материал, форма, длина_см, ширина_см, высота_см), ...]

    Масса складывается по частям. Внешний объём — сумма габаритов частей,
    ужатая коэффициентом укладки (вещь компактнее суммы своих коробок).
    """
    rng = rng or random.Random(name)
    lim = ERA_RANK[tech_ceiling]
    kg, gross, props, mats = 0.0, 0.0, [], []
    if not parts:
        raise ValueError(f"{name}: нет частей")
    for part in parts:
        mat, form, L, W, H, wall_mm = unpack_part(part)
        if mat not in MATERIALS: raise KeyError(f"нет материала: {mat}")
        if form not in FORMS:    raise KeyError(f"нет формы: {form}")
        dens, hard, burn, cond_t, soak, era = MATERIALS[mat]
        if ERA_RANK[era] > lim:
            raise ValueError(f"{name}: материал '{mat}' невозможен при tech_ceiling={tech_ceiling}")
        solid, v = part_solid_l(form, L, W, H, wall_mm)
        kg += solid * dens
        gross += v
        mats.append(mat); props.append((hard, burn, cond_t, soak))

    check_plausible(name, parts, kg, gross)
    l = round(gross * packing, 3)
    hard = max(p[0] for p in props)
    burn = round(sum(p[1] for p in props) / len(props), 2)
    soak = round(sum(p[3] for p in props) / len(props), 2)
    it = {"name": name, "kg": round(kg, 3), "l": l,
          "materials": sorted(set(mats)), "tags": tags or [],
          "hardness": hard, "flammability": burn, "soaks": soak,
          "condition": condition if condition is not None else round(rng.uniform(0.5, 1.0), 2),
          "parts": [list(p) for p in parts]}
    return it

# ─────────── АРХЕТИПЫ: не каталог, а примеры сборки ───────────
# Всё остальное собирается тем же способом на лету, когда понадобится.
ARCHETYPES = {
 "нож":        ([("сталь","клинок",14,2.6,0.30),("дерево","стержень",11,3,2)], ["резак","оружие"], "preindustrial"),
 "топор":      ([("сталь","обух",14,7,2.2),("дерево","стержень",50,3.5,2.5)], ["рубка","оружие"], "preindustrial"),
 "кольчуга":   ([("железо","плетение",70,55,1.2)], ["броня"], "preindustrial"),
 "весло":      ([("дерево","стержень",180,5,3.5),("дерево","пластина",45,15,1.5)], ["гребля"], "primitive"),
 "жернов":     ([("камень","пластина",40,40,12)], ["помол"], "primitive"),
 "самовар":    ([("медь","сосуд",35,28,28,0.8)], ["готовка","вода"], "preindustrial"),
 "котелок":    ([("железо","сосуд",18,18,14,1.5)], ["готовка"], "preindustrial"),
 "фляга 1 л":  ([("алюминий","сосуд",22,10,7,0.7),("вода","жидкость",10,10,10)], ["вода"], "industrial"),
 "смартфон":   ([("электроника","устройство",15,7.5,0.85)], ["стекло","улика","свет"], "industrial"),
 "скафандр":   ([("композит","свёрток ткани",180,55,4),("титан","пластина",40,30,0.4)], ["вакуум","защита"], "spacefaring"),
 "лук":        ([("дерево твёрдое","стержень",160,4,2.5),("верёвка растит.","стержень",150,0.4,0.4)], ["оружие"], "primitive"),
 "щит":        ([("дерево","пластина",80,70,1.6),("железо","пластина",12,12,0.3)], ["броня"], "primitive"),
 "мешок зерна":([("ткань","свёрток ткани",60,40,25),("зерно","сыпучее",55,35,22)], ["еда","тара"], "primitive"),
 "бурдюк":     ([("кожа","мех/бурдюк",45,30,20,2.5),("вода","жидкость",13,13,13)], ["вода"], "primitive"),
 "лопата":     ([("сталь","пластина",30,20,0.25),("дерево","стержень",110,4,3)], ["копать"], "preindustrial"),
 "верёвка 40 м":([("верёвка растит.","шнур",4000,1.1,1.1)], ["альпинизм"], "primitive"),
}

def from_archetype(key, tech_ceiling="industrial", rng=None, condition=None):
    parts, tags, era = ARCHETYPES[key]
    return make_item(key, parts, tags, tech_ceiling, rng, condition)

def make_garment(name, material, area_cm2, thickness_mm, rules,
                covers=None, waterproof=False, tech_ceiling="industrial", rng=None):
    """Одежда выводится из вещества и геометрии: масса из плотности,
    теплота из толщины. Никакой таблицы одежды не нужно."""
    if material not in MATERIALS: raise KeyError(f"нет материала: {material}")
    dens, hard, burn, condt, soak, era = MATERIALS[material]
    if ERA_RANK[era] > ERA_RANK[tech_ceiling]:
        raise ValueError(f"{name}: '{material}' невозможен при tech_ceiling={tech_ceiling}")
    vol_l = area_cm2 * (thickness_mm/10.0) / 1000.0
    bulk = rules.get("fabrics", {}).get("bulk_kg_l", {}).get(material)
    kg = round(vol_l * (bulk if bulk is not None else dens * LOFT.get(material, 1.0)), 3)
    ins = rules["insulation"]
    k = ins["k"].get(material, 1.0)
    clo = round(thickness_mm / ins["mm_per_clo"] * k, 2)
    return {"name": name, "kg": kg, "clo": clo, "layer": covers or "—", "wet": 0.0,
            "material": material, "waterproof": waterproof, "soaks": soak}

def make_container(name, mount, closure, cap_l, cap_kg, rules,
                   own_kg=0.0, rigid=False, parent=None):
    """Время доступа выводится из точки крепления и застёжки.
    Средневековая поясная калита и современная поясная сумка считаются одинаково."""
    m = rules["mounts"]; c = rules["closures"]
    if mount not in m:   raise KeyError(f"нет точки крепления: {mount}")
    if closure not in c: raise KeyError(f"нет типа застёжки: {closure}")
    return {"name": name, "mount": mount, "closure": closure,
            "access_s": m[mount] + c[closure], "cap_l": cap_l, "cap_kg": cap_kg,
            "rigid": rigid, "kg": own_kg, "parent": parent}

def try_build(key, tech_ceiling="industrial", rng=None):
    """Есть архетип — берём. Нет — предмет собирается вызывающей стороной
    из материалов и форм. Каталог здесь — кэш, а не белый список."""
    if key in ARCHETYPES:
        return from_archetype(key, tech_ceiling, rng)
    return None


if __name__ == "__main__":
    print(f"{'предмет':<16}{'кг':>8}{'л':>7}  материалы")
    print("-"*58)
    for k in ARCHETYPES:
        try:
            it = from_archetype(k, "spacefaring", random.Random(1), condition=1.0)
            print(f"{it['name']:<16}{it['kg']:>8.2f}{it['l']:>7.2f}  {', '.join(it['materials'])}")
        except ValueError as e:
            print(f"{k:<16}  невозможен: {e}")
