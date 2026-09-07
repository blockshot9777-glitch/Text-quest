#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборщик: превращает пять модулей и набор правил в ОДИН самодостаточный файл.

Зачем: агенту проще положить рядом один sim.py, чем шесть файлов с импортами.
Внешних зависимостей нет — только стандартная библиотека Python 3.
"""
import json, re, io, os


TOOLS = """

# ══════════════ инструменты сборки: генерация, проверка, самотест ══════════════

def _bundle_tools(a):
    if a.cmd == "new":
        S = expand(json.load(open(a.brief, encoding="utf-8")))
        err, warn = validate(S)
        for e in err:  print("ОШИБКА:", e)
        for w in warn: print("замечание:", w)
        if err:
            print("состояние не записано"); sys.exit(1)
        for note in S.pop("_gen_notes", []): print("рандом:", note)
        json.dump(S, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("готово: %s (%d предметов, %d счётчиков, %d NPC, %d скрытых истин)" %
              (a.out, len(S["items"]), len(S["clocks"]), len(S["world"]["npcs"]), len(S["hidden_truths"])))
        return
    if a.cmd == "check":
        err, warn = validate(json.load(open(a.state, encoding="utf-8")))
        for e in err:  print("ОШИБКА:", e)
        for w in warn: print("замечание:", w)
        print("чисто" if not err and not warn else "ошибок %d, замечаний %d" % (len(err), len(warn)))
        sys.exit(1 if err else 0)
    if a.cmd == "checkrules":
        R = json.load(open(a.rules, encoding="utf-8")) if a.rules else rules()
        err, warn = validate_ruleset(R)
        for e in err:  print("ОШИБКА:", e)
        for w in warn: print("замечание:", w)
        print("набор правил чист" if not err and not warn else "ошибок %d, замечаний %d" % (len(err), len(warn)))
        sys.exit(1 if err else 0)
    if a.cmd == "selftest":
        _bundle_selftest()


def _bundle_selftest():
    ok = 0; fail = 0
    R = rules()
    def chk(name, val, lo, hi, unit=""):
        nonlocal ok, fail
        good = lo <= val <= hi
        ok += good; fail += (not good)
        print("  %s %-30s%9.3f%s  ожидалось %s-%s" % ("ok " if good else "MISS", name, val, unit, lo, hi))

    print("-- предметы: масса из вещества и геометрии --")
    for k, lo, hi in [("нож",0.08,0.25),("топор",0.9,1.4),("кольчуга",7,12.5),("котелок",1.4,2.6),
                      ("смартфон",0.16,0.24),("верёвка 40 м",2.6,3.8),("фляга 1 л",1.0,1.3)]:
        chk(k, from_archetype(k, "spacefaring", random.Random(1), 1.0)["kg"], lo, hi, " кг")

    print("-- одежда: масса из плотности материи --")
    for n,m,ar,t,lo,hi in [("футболка","ткань",7000,0.6,0.10,0.22),("свитер","шерсть",8000,6,0.40,0.85),
                           ("тулуп","мех",11000,25,2.5,5.0),("парка пуховая","пух",9000,20,0.7,1.6)]:
        chk(n, make_garment(n,m,ar,t,R,tech_ceiling="spacefaring")["kg"], lo, hi, " кг")

    print("-- атмосфера --")
    for z,lo,hi in [(-4000,1.55,1.65),(0,0.99,1.01),(3000,0.68,0.72),(8000,0.34,0.37),(19200,0.059,0.065)]:
        chk("давление на %d м" % z, pressure_atm(z), lo, hi, " атм")

    print("-- холод --")
    chk("ветрохолод -3 C, 9 м/с", windchill(-3,9), -11.2, -10.2, " C")
    chk("ядро при холоде 100", core_temp(100), 27.9, 28.1, " C")

    print("-- физиология --")
    N = R["needs"]
    chk("суток без еды", 100/N["hunger"]["rate_per_h"]/24, 13, 15, " сут")
    chk("суток без воды", 100/N["thirst"]["rate_per_h"]/24, 2.5, 3.0, " сут")

    print("-- набор правил --")
    e, w = validate_ruleset(R)
    good = not e
    ok += good; fail += (not good)
    print("  %s встроенный набор чист: %d ошибок" % ("ok " if good else "MISS", len(e)))

    print("=" * 58)
    print("ИТОГО пройдено %d, провалено %d" % (ok, fail))
    sys.exit(1 if fail else 0)
"""

# Имена верхнего уровня, которые после склейки читает play.py / обёртки.
# Не переименовывать и не прятать: PHYSICS_ON, make_item, expand, validate.
# play.py берёт enum physics_on из sim.PHYSICS_ON, не из worldgen.py.
ORDER = ["matter.py", "edc.py", "society.py", "worldgen.py", "engine.py"]

HEADER = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СИМУЛЯТОР — единый файл. Собран автоматически, править здесь не нужно.

Запуск:
  python3 sim.py selftest                      проверка сборки числами
  python3 sim.py new --brief brief.json        создать мир из замысла
  python3 sim.py check --state state.json      проверить мир
  python3 sim.py checkrules                    проверить набор правил
  python3 sim.py look --window 5               осмотреться без траты времени
  python3 sim.py act --minutes 40 --activity 1 --check "perception:20:осмотр::восприятие"
  python3 sim.py fight --foe "имя:45:10:0" --foe "второй:30:0:4"
  python3 sim.py treat --supplies 20           обработать рану
  python3 sim.py compact                       уплотнить канон
  python3 sim.py snapshot --tag имя            сохранить / restore --file путь

Состояние по умолчанию: state.json (или переменная окружения SIM_STATE).
Набор правил встроен; внешний файл можно подать через SIM_RULES.
"""
import json, math, hashlib, argparse, os, sys, copy, random

'''

STRIP_IMPORT = re.compile(r'^\s*(import|from)\s+(json|math|hashlib|argparse|os|sys|copy|random|matter|edc|society|worldgen|engine)\b.*$', re.M)
STRIP_TRY_IMPORT = re.compile(r'^try:\n\s+import (society|edc|matter)\n(except ImportError:\n\s+\1 = None\n)?', re.M)
STRIP_MAIN = re.compile(r'\nif __name__ == ["\']__main__["\']:.*\Z', re.S)


def strip_module(src, keep_main=False):
    src = STRIP_TRY_IMPORT.sub('', src)
    src = STRIP_IMPORT.sub('', src)
    if not keep_main:
        src = STRIP_MAIN.sub('\n', src)
    return src.strip() + "\n"


def build(outfile="sim.py", rules_file="ruleset.json"):
    parts = [HEADER]

    rules = json.load(open(rules_file, encoding="utf-8"))
    parts.append("# ─── ВСТРОЕННЫЙ НАБОР ПРАВИЛ (подменяется через SIM_RULES) ───\n")
    parts.append("EMBEDDED_RULES = " + json.dumps(rules, ensure_ascii=False, indent=1) + "\n\n")

    for i, f in enumerate(ORDER):
        src = open(f, encoding="utf-8").read()
        keep = (f == "engine.py")
        body = strip_module(src, keep_main=keep)
        parts.append(f"\n# {'═'*70}\n# из {f}\n# {'═'*70}\n\n")
        parts.append(body)

    out = "".join(parts)

    # движок читал правила из файла — теперь сначала встроенные
    out = out.replace(
        'RULES_PATH = os.environ.get("SIM_RULES", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ruleset.json"))',
        'RULES_PATH = os.environ.get("SIM_RULES")')
    out = out.replace(
        '''    if _RULES is None:
        _RULES = json.load(open(RULES_PATH, encoding="utf-8"))
    return _RULES''',
        '''    if _RULES is None:
        _RULES = json.load(open(RULES_PATH, encoding="utf-8")) if RULES_PATH else copy.deepcopy(EMBEDDED_RULES)
        extend_from_rules(_RULES)          # материалы и формы из данных
    return _RULES''')

    # society вызывается напрямую, без модуля
    out = out.replace("    if society is not None:\n        society.society_step(S, log, hours, rules(S))",
                      "    society_step(S, log, hours, rules(S))")
    # worldgen обращался к edc как к модулю
    out = out.replace("if edc is None: raise RuntimeError(\"нужен edc.py рядом с worldgen.py\")", "pass")
    out = out.replace("ctx, worn_o, cont_o, items_o, notes_o = edc.build(", "ctx, worn_o, cont_o, items_o, notes_o = build_edc(")
    out = out.replace("\ndef build(seed, context=None, wet=0.0):", "\ndef build_edc(seed, context=None, wet=0.0):")
    # worldgen.main -> переименовать; подкоманды инструментов зарегистрировать в общем разборе
    out = out.replace(chr(10)+'def main():', chr(10)+'def _main_worldgen():', 1)
    reg = ('    sub = ap.add_subparsers(dest="cmd", required=True)' + chr(10) +
           '    _p = sub.add_parser("new");        _p.add_argument("--brief", required=True); _p.add_argument("--out", required=True)' + chr(10) +
           '    _p = sub.add_parser("check");      _p.add_argument("--state", required=True)' + chr(10) +
           '    _p = sub.add_parser("checkrules"); _p.add_argument("--rules", default=None)' + chr(10) +
           '    _p = sub.add_parser("selftest")')
    _k = '    sub = ap.add_subparsers(dest="cmd", required=True)'
    _pos = out.rfind(_k)                      # нужен ПОСЛЕДНИЙ (в engine.main), а не первый
    assert _pos != -1, 'не найден разбор аргументов'
    out = out[:_pos] + reg + out[_pos+len(_k):]
    out = out.replace('    a = ap.parse_args()' + chr(10) + '    S = load()',
                      '    a = ap.parse_args()' + chr(10) +
                      '    if a.cmd in ("new", "check", "checkrules", "selftest"):' + chr(10) +
                      '        return _bundle_tools(a)' + chr(10) + '    S = load()', 1)
    _m = out.rfind('if __name__ ==')            # инструменты обязаны идти ДО точки входа
    out = out[:_m] + TOOLS + chr(10) + out[_m:] if _m != -1 else out + TOOLS

    with io.open(outfile, "w", encoding="utf-8") as fh:
        fh.write(out)
    return outfile, len(out.splitlines())


if __name__ == "__main__":
    name, n = build()
    print(f"собрано: {name}, {n} строк, внешних зависимостей нет")
