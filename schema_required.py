#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Вывод required схемы brief из AST worldgen, не из памяти о живых прогонах.

Живой прогон ловил поля по одному (physics_on → sites → skills → chain →
start_local → exits). Здесь ключ обязателен на том уровне, где код читает
x["k"] без .get и без `if k in` / `if x.get(k)`.

Ограничения черновика, которые здесь закрыты:
  · .get по всему файлу не вычитается из корня — иначе physics_on/sites
    пропадают (normalize делает .get, expand читает b["…"] напрямую);
  · привязка переменной цикла живёт только в теле цикла — иначе c часов
    слипается с c контейнеров;
  · STATE_TO_BRIEF только тождество expand (sites_canon = b["sites"]).
    items/worn/containers собираются заново, это не поля замысла;
  · x["k"] внутри `if x.get("k")` / `if "k" in x` не обязателен;
  · то же, если в том же цикле есть x.get("k") (после `if not get: continue`).

Второй класс — код не упадёт (.get с дефолтом), но игра без поля пустая.
Его автоматически не вывести: SEMANTIC_REQUIRED ведётся руками.

Третий класс — validate требует ключ (`if f not in e`), это не KeyError,
AST не выведет travel_min/difficulty. В схему кладём руками (EXIT_REQUIRED).
--check: лишний required не дыра; дыра — код читает, схема не требует.
"""
import ast, json, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILES = (os.path.join(HERE, "worldgen.py"),)

# expand(): "sites_canon": b["sites"] — чтения validate по sites_canon
# это требования к brief.sites[]. Не items/worn/containers: их expand строит.
STATE_TO_BRIEF = {
    ("S", "world", "sites_canon"): ("sites",),
}

INDEX_NAMES = frozenset({"i", "j", "k", "idx"})

# Код читает через .get, но без ключа замысел бессмыслен. Не выводится из AST.
SEMANTIC_REQUIRED = {
    (): ["skills", "clocks", "npcs", "factions", "truths", "tech_ceiling"],
}


def unwrap_iter(node):
    if node is None:
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id == "enumerate" and node.args:
        return unwrap_iter(node.args[0])
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and node.values:
        return unwrap_iter(node.values[0])
    return node


def parse_source(node):
    """Имя корня и цепочка ключей: b['sites'] → ('b', ('sites',))."""
    node = unwrap_iter(node)
    if node is None:
        return None, None
    if isinstance(node, ast.Name):
        return node.id, ()
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
            and isinstance(node.slice.value, str):
        base, keys = parse_source(node.value)
        if base is None:
            return None, None
        return base, keys + (node.slice.value,)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "get" and node.args \
            and isinstance(node.args[0], ast.Constant) \
            and isinstance(node.args[0].value, str):
        base, keys = parse_source(node.func.value)
        if base is None:
            return None, None
        return base, keys + (node.args[0].value,)
    return None, None


def loop_vars(target):
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple):
        names = [el.id for el in target.elts if isinstance(el, ast.Name)]
        if names and names[0] in INDEX_NAMES:
            names = names[1:]
        return names
    return []


def loop_path(iter_node, bindings):
    base, keys = parse_source(iter_node)
    if base is None:
        return None
    full = (base,) + keys
    if full in STATE_TO_BRIEF:
        return STATE_TO_BRIEF[full]
    if base in bindings:
        return bindings[base] + keys
    return None


def _const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_guards(test):
    """Какие var["k"] охраняет условие if."""
    out = defaultdict(set)
    if isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute) \
            and test.func.attr == "get" and isinstance(test.func.value, ast.Name) \
            and test.args:
        k = _const_str(test.args[0])
        if k is not None:
            out[test.func.value.id].add(k)
    elif isinstance(test, ast.Compare) and any(isinstance(op, ast.In) for op in test.ops):
        k = _const_str(test.left)
        if k is not None and test.comparators \
                and isinstance(test.comparators[0], ast.Name):
            out[test.comparators[0].id].add(k)
    elif isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        for v in test.values:
            for var, keys in extract_guards(v).items():
                out[var] |= keys
    return out


def merge_guarded(base, extra):
    out = {k: set(v) for k, v in base.items()}
    for var, keys in extra.items():
        out.setdefault(var, set()).update(keys)
    return out


def analyze(path, roots=("b",)):
    tree = ast.parse(open(path, encoding="utf-8").read())
    result = defaultdict(set)
    root_bind = {name: () for name in roots}

    def record_read(node, bindings, guarded):
        if not isinstance(node.ctx, ast.Load):
            return
        if not isinstance(node.slice, ast.Constant) or not isinstance(node.slice.value, str):
            return
        if not isinstance(node.value, ast.Name):
            return
        var, key = node.value.id, node.slice.value
        if key in guarded.get(var, ()):
            return
        if var in bindings:
            result[bindings[var]].add(key)

    def gets_on(stmts, var):
        keys = set()
        for stmt in stmts:
            for n in ast.walk(stmt):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr == "get" and isinstance(n.func.value, ast.Name) \
                        and n.func.value.id == var and n.args:
                    k = _const_str(n.args[0])
                    if k is not None:
                        keys.add(k)
        return keys

    def visit_comp(node, elts, bindings, guarded):
        cur = bindings
        cur_g = guarded
        for gen in node.generators:
            visit(gen.iter, cur, cur_g)
            path = loop_path(gen.iter, cur)
            inner = dict(cur)
            inner_g = cur_g
            if path is not None:
                for name in loop_vars(gen.target):
                    inner[name] = path
                    inner_g = merge_guarded(inner_g, {name: gets_on(list(gen.ifs), name)})
            for iff in gen.ifs:
                visit(iff, inner, inner_g)
            cur, cur_g = inner, inner_g
        for elt in elts:
            visit(elt, cur, cur_g)

    def visit(node, bindings, guarded):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return
        if isinstance(node, ast.If):
            inner_g = merge_guarded(guarded, extract_guards(node.test))
            visit(node.test, bindings, inner_g)
            for stmt in node.body:
                visit(stmt, bindings, inner_g)
            for stmt in node.orelse:
                visit(stmt, bindings, guarded)
            return
        if isinstance(node, ast.For):
            visit(node.iter, bindings, guarded)
            path = loop_path(node.iter, bindings)
            inner_b = dict(bindings)
            inner_g = guarded
            if path is not None:
                for name in loop_vars(node.target):
                    inner_b[name] = path
                    inner_g = merge_guarded(inner_g, {name: gets_on(node.body, name)})
            for stmt in node.body:
                visit(stmt, inner_b, inner_g)
            for stmt in node.orelse:
                visit(stmt, bindings, guarded)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            visit_comp(node, [node.elt], bindings, guarded)
            return
        if isinstance(node, ast.DictComp):
            visit_comp(node, [node.key, node.value], bindings, guarded)
            return
        if isinstance(node, ast.Subscript):
            record_read(node, bindings, guarded)
        for child in ast.iter_child_nodes(node):
            visit(child, bindings, guarded)

    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for stmt in fn.body:
                visit(stmt, root_bind, {})
    return {k: sorted(v) for k, v in result.items() if v}


def to_required(paths):
    res = {}
    for path, keys in paths.items():
        loc = "brief (корень)" if not path else " -> ".join(path) + ".items"
        res[loc] = keys
    return res


def schema_required(files=None):
    files = files or DEFAULT_FILES
    merged = defaultdict(set)
    for f in files:
        for path, keys in analyze(f).items():
            merged[path] |= set(keys)
    for path, keys in SEMANTIC_REQUIRED.items():
        merged[path] |= set(keys)
    return {k: sorted(v) for k, v in merged.items()}


def node_at(schema, path):
    node = schema
    for key in path:
        node = (node.get("properties") or {}).get(key, {})
        node = node.get("items", node)
    return node


def check_against(schema, files=None):
    """Дыры: код читает напрямую, схема не требует. Лишние required не дыра."""
    need = schema_required(files)
    holes = []
    for path, keys in sorted(need.items()):
        have = set(node_at(schema, path).get("required") or [])
        miss = sorted(set(keys) - have)
        if miss:
            loc = "brief (корень)" if not path else " -> ".join(path) + ".items"
            holes.append((loc, miss))
    return holes


if __name__ == "__main__":
    os.chdir(HERE)
    if sys.argv[1:2] == ["--check"]:
        import play
        holes = check_against(play.BRIEF_SCHEMA)
        if not holes:
            print("схема совпадает с кодом: дыр нет")
            sys.exit(0)
        print("ДЫРЫ В required (код читает, схема не требует):\n")
        for loc, miss in holes:
            print(f"  {loc}\n    {json.dumps(miss, ensure_ascii=False)}\n")
        sys.exit(1)
    files = sys.argv[1:] or list(DEFAULT_FILES)
    merged = defaultdict(set)
    for f in files:
        for path, keys in analyze(f).items():
            merged[path] |= set(keys)
    print("REQUIRED, выведенный из кода (не из догадок):\n")
    shown = {k: sorted(v) for k, v in merged.items()}
    for loc, keys in sorted(to_required(shown).items()):
        print(f"  {loc}")
        print(f"    {json.dumps(keys, ensure_ascii=False)}\n")
