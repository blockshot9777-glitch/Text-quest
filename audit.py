#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ревизор кода. Ловит класс ошибок, который трижды проскочил мимо глаз:
дубли функций после неудачной замены, мёртвые константы, жёстко зашитые
человеческие поля, молчаливые провалы.

Запускать перед каждым коммитом и после каждой правки движка.
"""
import ast, sys, os, json, re

FILES = ["engine.py", "worldgen.py", "matter.py", "edc.py", "society.py"]
HERE = os.path.dirname(os.path.abspath(__file__))
errors, warns = [], []

def E(msg): errors.append(msg)
def W(msg): warns.append(msg)

# ─────────── 1. ДУБЛИ ФУНКЦИЙ ───────────
# Именно так трижды выживал старый код: replace() тихо не сработал,
# новая функция добавилась, старая осталась и перехватывала вызов.
for f in FILES:
    p = os.path.join(HERE, f)
    if not os.path.exists(p): continue
    tree = ast.parse(open(p, encoding="utf-8").read())
    seen = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in seen:
                E(f"{f}: функция '{node.name}' объявлена дважды (строки {seen[node.name]} и {node.lineno}) "
                  f"— поздняя перекрывает раннюю, почти наверняка остаток неудачной замены")
            seen[node.name] = node.lineno
        if isinstance(node, ast.ClassDef):
            seen[node.name] = node.lineno

# ─────────── 2. МЁРТВЫЕ КОНСТАНТЫ ВЕРХНЕГО УРОВНЯ ───────────
for f in FILES:
    p = os.path.join(HERE, f)
    if not os.path.exists(p): continue
    src = open(p, encoding="utf-8").read()
    tree = ast.parse(src)
    assigned = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper() and len(t.id) > 2:
                    assigned[t.id] = node.lineno
    for name, line in assigned.items():
        uses = len(re.findall(rf"\b{re.escape(name)}\b", src))
        if uses <= 1:
            W(f"{f}:{line} константа {name} нигде не используется — мёртвый код после миграции на данные")

# ─────────── 3. ЖЁСТКО ЗАШИТЫЕ ЧЕЛОВЕЧЕСКИЕ ПОЛЯ ───────────
# Движок обязан работать с любым существом: поля берутся из ruleset, не из кода.
HUMAN_FIELDS = ["hunger", "thirst", "fatigue", "cold_stress", "stress",
                "blood_loss_pct", "infection", "core_temp_c"]
eng = os.path.join(HERE, "engine.py")
if os.path.exists(eng):
    src = open(eng, encoding="utf-8").read()
    for i, line in enumerate(src.split("\n"), 1):
        s = line.strip()
        if s.startswith("#") or '"""' in s: continue
        for fld in HUMAN_FIELDS:
            # допустимо: спец-обработка холода, помеченная явной проверкой профиля
            if f'["{fld}"]' in line and "physics_on" not in line and ".get(" not in line:
                if fld in ("cold_stress", "core_temp_c") and (
                        'in n' in line or 'in v' in line or 'холод' in line):
                    continue
                W(f"engine.py:{i} прямое обращение к человеческому полю '{fld}' — "
                  f"сломается на другом виде существа")

# ─────────── 4. НЕДЕТЕРМИНИРОВАННЫЕ ИСТОЧНИКИ СЛУЧАЙНОСТИ ───────────
for f in FILES:
    p = os.path.join(HERE, f)
    if not os.path.exists(p): continue
    for i, line in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
        if re.search(r"(?<![\w.])hash\s*\(", line) and "hashlib" not in line:
            E(f"{f}:{i} встроенный hash() — рандомизирован между процессами, "
              f"ломает воспроизводимость по seed. Нужен hashlib.sha256")
        if "random.random()" in line and "Random(" not in line:
            W(f"{f}:{i} глобальный random без зерна — недетерминированно")
        if re.search(r"\btime\.time\(\)|datetime\.now\(\)", line) and "snapshot" not in line:
            W(f"{f}:{i} системное время в логике — недетерминированно")

# ─────────── 5. СОГЛАСОВАННОСТЬ RULESET И КОДА ───────────
def check_ruleset(path):
    if not os.path.exists(path): return
    R = json.load(open(path, encoding="utf-8"))
    name = os.path.basename(path)
    for block in ("needs", "vitals", "environment"):
        for key, spec in R.get(block, {}).items():
            bands = spec.get("bands")
            direction = spec.get("direction", "above")
            if bands:
                thr = [b[0] for b in bands]
                if direction == "below":
                    thr = thr[::-1]   # для direction=below пороги обязаны убывать — это правильно
                if thr != sorted(thr):
                    E(f"{name}: {block}.{key}.bands не отсортированы по возрастанию — "
                      f"band_text вернёт неверную полосу")
                if len(set(thr)) != len(thr):
                    E(f"{name}: {block}.{key}.bands содержат дублирующиеся пороги")
    for m in R.get("condition_modifiers", []):
        for req in ("name", "factor", "path", "op", "value"):
            if req not in m:
                E(f"{name}: модификатор {m.get('name','?')} без обязательного поля '{req}'")
        if m.get("op") not in ("==","!=",">","<",">=","<=","in"):
            E(f"{name}: модификатор {m.get('name','?')} — неизвестная операция '{m.get('op')}'")
        if isinstance(m.get("factor"), (int, float)) and not (0 < m["factor"] <= 2):
            W(f"{name}: модификатор {m['name']} имеет подозрительный множитель {m['factor']}")
    res = R.get("resolution", {})
    if res:
        lo, hi = res.get("clamp", [5, 95])
        if not (0 < lo < hi <= 100):
            E(f"{name}: resolution.clamp = [{lo},{hi}] бессмысленен")
        if res.get("catastrophe", 96) <= hi:
            W(f"{name}: порог катастрофы {res.get('catastrophe')} не выше верхнего клэмпа {hi} "
              f"— катастрофа будет перекрывать успех у мастеров")
    if not R.get("needs"):
        E(f"{name}: нет ни одной потребности — существо ничего не будет чувствовать")

for rf in ("ruleset.json", "ruleset_mech.json"):
    check_ruleset(os.path.join(HERE, rf))

# ─────────── 6. ЛОВУШКА МОЛЧАЛИВОГО ПРОВАЛА ───────────
for f in FILES:
    p = os.path.join(HERE, f)
    if not os.path.exists(p): continue
    src = open(p, encoding="utf-8").read()
    for i, line in enumerate(src.split("\n"), 1):
        if re.search(r"except\s*:", line) or "except Exception: pass" in line:
            W(f"{f}:{i} голый except — скроет настоящую ошибку")

# ─────────── 7. BRIEF_SCHEMA required vs прямые чтения worldgen ───────────
sys.path.insert(0, HERE)
import schema_required, play as _play_schema
for loc, miss in schema_required.check_against(_play_schema.BRIEF_SCHEMA):
    E(f"BRIEF_SCHEMA {loc}: код читает {miss}, в required нет — "
      f"следующий живой прогон поймает KeyError")

# ─────────── ВЫВОД ───────────
print("═" * 62)
print("РЕВИЗИЯ КОДА")
print("═" * 62)
if errors:
    print(f"\nОШИБКИ ({len(errors)}):")
    for e in errors: print(f"  ✗ {e}")
if warns:
    print(f"\nЗАМЕЧАНИЯ ({len(warns)}):")
    for w in warns: print(f"  · {w}")
if not errors and not warns:
    print("\nчисто")
print(f"\nитого: ошибок {len(errors)}, замечаний {len(warns)}")
sys.exit(1 if errors else 0)
