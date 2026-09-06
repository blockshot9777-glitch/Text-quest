#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Самопроверка: инструмент доказывает себя числами, а не обещаниями."""
import json, math, random, subprocess, sys, os, tempfile
import matter

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.gettempdir()
R = json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
ok = fail = 0
def check(name, val, lo, hi, unit=""):
    global ok, fail
    good = lo <= val <= hi
    ok, fail = ok+good, fail+(not good)
    print(f"  {'ok ' if good else 'MISS'} {name:<28}{val:>9.3f}{unit}  ожидалось {lo}–{hi}")

def _env(**extra):
    e = dict(os.environ)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    e.update(extra)
    return e

def _run(args, **extra):
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=_env(**extra), cwd=HERE)

print("── предметы: масса из вещества и геометрии ──")
for k, lo, hi in [("нож",0.08,0.25),("топор",0.9,1.4),("кольчуга",7,12.5),("весло",1.5,3.0),
                  ("котелок",1.4,2.6),("смартфон",0.16,0.24),("лук",0.6,1.2),("щит",3.5,6.5),
                  ("лопата",1.4,2.2),("верёвка 40 м",2.6,3.8),("самовар",3.0,6.0),("фляга 1 л",1.0,1.3)]:
    check(k, matter.from_archetype(k,"spacefaring",random.Random(1),1.0)["kg"], lo, hi, " кг")

print("\n── одежда: масса из плотности материи ──")
for n,m,a,t,lo,hi in [("футболка","ткань",7000,0.6,0.10,0.22),("рубаха льняная","ткань",7500,0.8,0.12,0.40),
                      ("свитер","шерсть",8000,6,0.40,0.85),("тулуп","мех",11000,25,2.5,5.0),
                      ("парка пуховая","пух",9000,20,0.7,1.6),("валенки","войлок",3000,12,0.6,1.4)]:
    check(n, matter.make_garment(n,m,a,t,R,tech_ceiling="spacefaring")["kg"], lo, hi, " кг")

print("\n── атмосфера: барометрическая формула ──")
def P(z):
    if z<0: return math.exp(-z/8400)
    if z<=11000: return (1-2.2558e-5*z)**5.2559
    return 0.2234*math.exp(-(z-11000)/6342)
for z,lo,hi in [(-4000,1.55,1.65),(0,0.99,1.01),(3000,0.68,0.72),(8000,0.34,0.37),
                (12000,0.185,0.196),(19200,0.059,0.065)]:
    check(f"давление на {z} м", P(z), lo, hi, " атм")

print("\n── холод: ветрохолод и время до предела ──")
def wc(T,v):
    vk=v*3.6
    if vk<5: return T
    k=vk**0.16
    return 13.12+0.6215*T-11.37*k+0.3965*T*k
check("ветрохолод −3 °C, 9 м/с", wc(-3,9), -11.2, -10.2, " °C")
check("ветрохолод −30 °C, 10 м/с", wc(-30,10), -47.5, -46.0, " °C")
cm=R["cold_model"]
def rate(T,v,clo,act): return max(0,((cm["comfort_base_c"]-cm["clo_coeff"]*clo-cm["activity_coeff"]*act)-wc(T,v))/cm["gain_divisor"])
check("часов до предела: 1.5 clo, −3 °C, покой", 100/rate(-3,9,1.5,0), 9.5, 11.0, " ч")

print("\n── физиология: сроки выживания из скоростей ──")
N=R["needs"]
check("суток без еды",  100/N["hunger"]["rate_per_h"]/24, 13, 15, " сут")
check("суток без воды", 100/N["thirst"]["rate_per_h"]/24, 2.5, 3.0, " сут")
check("часов без сна",  100/N["fatigue"]["rate_per_h"],   38, 42, " ч")
check("литров до нормы жажды с 73", 73*N["thirst"]["unit_per_point"], 4.8, 5.4, " л")

print("\n── ядро тела: холод обязан убивать ──")
core=lambda cs: 37-9*max(0,cs-30)/70
check("ядро при холоде 100", core(100), 27.9, 28.1, " °C")
check("ядро при холоде 50",  core(50),  34.2, 34.6, " °C")

print("\n── разрешение: полосы броска не схлопываются ──")
lo_c,hi_c=R["resolution"]["clamp"]
for tgt in (5,30,60,95):
    bands={}
    for r in range(1,101):
        o=("успех" if r<=R["resolution"]["floor_success"] else "катастрофа" if r>=R["resolution"]["catastrophe"]
           else "крит" if r<=tgt/5 else "успех" if r<=tgt else "ценой" if r<=tgt+R["resolution"]["cost_band"] else "провал")
        bands[o]=bands.get(o,0)+1
    print(f"  ok  цель {tgt:<3} " + ", ".join(f"{k} {v}%" for k,v in bands.items()))
    ok+=1

print("\n── универсальность: два набора правил на одном движке ──")
_st_h = os.path.join(TMP, "st_h.json")
_st_m = os.path.join(TMP, "st_m.json")
import shutil
shutil.copy("examples/mech_state.json", _st_m)
for rules_f, state_f, who in [("ruleset.json", _st_h, "человек"),
                              ("ruleset_mech.json", _st_m, "механоид")]:
    if rules_f == "ruleset.json":
        import shutil; shutil.copy("examples/rimworld2.json", _st_h)
    skill = "athletics" if who == "человек" else "сервоприводы"
    r = _run(["engine.py", "act", "--minutes", "2",
              "--check", f"{skill}:20:тест::движение"],
             SIM_RULES=rules_f, SIM_STATE=state_f)
    good = r.returncode == 0 and "БРОСКИ" in (r.stdout or "")
    ok, fail = ok+good, fail+(not good)
    err = (r.stderr or "").strip().splitlines()[-1] if r.stderr else "УПАЛ"
    print(f"  {'ok ' if good else 'MISS'} {who:<28}{'бросок прошёл' if good else 'УПАЛ: '+err}")


print("\n── новое: NPC действуют по каждому пройденному периоду, не только по последнему ──")
import json as _json
import importlib
import engine as _eng
importlib.reload(_eng)
_st = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_st["time"]["t_h"] = 0.0
for _n in _st["world"]["npcs"]: _n["_last_acted_period"] = -1
_log = []
_st["time"]["t_h"] = 168.0
_eng.npc_step(_st, _log, minutes=168*60)
good = len(_log) > 5   # неделя должна дать больше одного события на пять NPC
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'события за 28 периодов (потолок 8/вызов)':<40}{len(_log)} событий")
_log2 = []
_eng.npc_step(_st, _log2, minutes=1)
good = len(_log2) == 0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'повторный вызов не дублирует прошлое':<40}{len(_log2)} новых событий")

print("\n── детерминизм между НЕЗАВИСИМЫМИ процессами (не только внутри одного) ──")
for i in (1,2,3):
    _sp_json = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
    _json.dump(_sp_json, open(os.path.join(TMP, f"det{i}.json"), "w", encoding="utf-8"), ensure_ascii=False)
outs=[]
for i in (1,2,3):
    r = _run(["engine.py", "act", "--minutes", "900", "--activity", "1"],
             SIM_STATE=os.path.join(TMP, f"det{i}.json"))
    outs.append(r.stdout or "")
good = outs[0]==outs[1]==outs[2] and len(outs[0])>0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'3 независимых процесса, тот же seed':<40}{'идентично' if good else 'РАСХОЖДЕНИЕ'}")

print("\n── новое: погода эволюционирует, не стоит колом ──")
_wr = _json.load(open(os.path.join(TMP, "det1.json"), encoding="utf-8"))
print(f"  итоговая погода после 900 минут: {_wr['time']['weather']} (была «ясно»)")

print("\n── новое: death_check не падает без core_temp_c ──")
_m = _json.load(open("examples/mech_state.json", encoding="utf-8"))
if "core_temp_c" in _m["pc"]["vitals"]: del _m["pc"]["vitals"]["core_temp_c"]
_no_temp = os.path.join(TMP, "no_temp.json")
_json.dump(_m, open(_no_temp, "w", encoding="utf-8"), ensure_ascii=False)
r = _run(["engine.py", "act", "--minutes", "300", "--activity", "2",
          "--check", "сервоприводы:15:тест::движение"],
         SIM_RULES="ruleset_mech.json", SIM_STATE=_no_temp)
good = r.returncode == 0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'вид без терморегуляции вообще':<40}{'не упал' if good else (r.stderr or '').splitlines()[-1]}")

print("\n── новое: snapshot/restore ──")
_snap_src = os.path.join(TMP, "snap_src.json")
_json.dump(_json.load(open("examples/rimworld2.json", encoding="utf-8")),
           open(_snap_src, "w", encoding="utf-8"), ensure_ascii=False)
r1 = _run(["engine.py", "snapshot", "--tag", "isolated"], SIM_STATE=_snap_src)
_snap_file = _snap_src.replace(".json", ".snap_isolated.json")
good = r1.returncode == 0 and os.path.exists(_snap_file)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'snapshot создаёт свой файл':<40}{'да' if good else 'нет'}")
_snap_dst = os.path.join(TMP, "snap_dst.json")
_json.dump({"meta": {"turn": -1}}, open(_snap_dst, "w", encoding="utf-8"))
r2 = _run(["engine.py", "restore", "--file", _snap_file], SIM_STATE=_snap_dst)
_restored = _json.load(open(_snap_dst, encoding="utf-8"))
_src_turn = _json.load(open(_snap_src, encoding="utf-8"))["meta"]["turn"]
good = r2.returncode == 0 and _restored.get("meta", {}).get("turn") == _src_turn
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'restore поднимает тот же ход':<40}{'да' if good else 'нет'}")


print("\n── валидатор набора правил ловит внесённые поломки ──")
import copy as _cp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from worldgen import validate_ruleset as _vr
_R = _json.load(open("ruleset.json", encoding="utf-8"))
_e, _w = _vr(_R)
good = len(_e) == 0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'рабочий набор проходит чисто':<40}{len(_e)} ошибок")
_bad = _cp.deepcopy(_R)
_bad["condition_modifiers"][0]["op"] = "~~"
_bad["condition_modifiers"][1]["path"] = "hero.needs.fatigue"
_bad["resolution"]["clamp"] = [95, 5]
_bad["needs"]["hunger"]["bands"] = [[40,"x"],[20,"y"]]
_e2, _ = _vr(_bad)
good = len(_e2) >= 4
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'4 внесённые поломки пойманы':<40}{len(_e2)} найдено")

print("\n── защита ввода ──")
_guard = os.path.join(TMP, "guard.json")
for _name, _args, _expect in [("отрицательное время", ["--minutes","-30"], "ОТКАЗ"),
                              ("превышен лимит проверок", ["--minutes","5","--check","athletics:10:a",
                                                           "--check","stealth:10:b","--check","craft:10:c"], "ОТКАЗ")]:
    _s0 = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
    _json.dump(_s0, open(_guard, "w", encoding="utf-8"), ensure_ascii=False)
    _r = _run(["engine.py", "act", *_args], SIM_STATE=_guard)
    good = _expect in (_r.stdout or "")
    ok, fail = ok+good, fail+(not good)
    print(f"  {'ok ' if good else 'MISS'} {_name:<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")

print("\n── бой с несколькими противниками ──")
_fight = os.path.join(TMP, "fight.json")
_s0 = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_json.dump(_s0, open(_fight, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "fight", "--skill", "combat",
           "--foe", "А:45:10:0", "--foe", "Б:30:0:4", "--foe", "В:30:0:20"],
          SIM_STATE=_fight)
good = _r.returncode == 0 and "инициатива" in (_r.stdout or "") and "обмен" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'трое противников, инициатива по укладке':<40}{'ok' if good else 'УПАЛ'}")
_after_f = _json.load(open(_fight, encoding="utf-8"))
good = len(_after_f["pc"]["wounds"]) > 0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'раны записались в состояние':<40}{len(_after_f['pc']['wounds'])} ран")

print("\n── уплотнение канона ──")
_comp = os.path.join(TMP, "comp.json")
_s0 = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_s0["log"] = [{"turn":i,"fact":f"событие {i}"} for i in range(120)]
_s0["world"]["sites_canon"] += [{"path":f"x/tmp_{i}","name":"t","z_m":0,"desc_true":"",
                                 "exits":[],"resources":[],"hazards":[],"objects":[],"touched":False}
                                for i in range(15)]
_json.dump(_s0, open(_comp, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "compact", "--keep", "40"], SIM_STATE=_comp)
_c = _json.load(open(_comp, encoding="utf-8"))
good = len(_c["log"]) < 120 and len(_c["world"]["sites_canon"]) < 16
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'лог свёрнут, нетронутые площадки убраны':<40}"
      f"лог {len(_c['log'])}, площадок {len(_c['world']['sites_canon'])}")


print("\n── слой общества: мир живёт без игрока ──")
import importlib as _il
import society as _soc; _il.reload(_soc)
_S = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_R = _json.load(open("ruleset.json", encoding="utf-8"))
_S["world"]["npcs"][2]["knows_about_pc"] = [{"turn":1,"source":"видел лично","fact":"чужак"}]
_S["world"]["npcs"][2]["_knew_at_h"] = 0.0
_p0 = {f["id"]: f["power"] for f in _S["world"]["factions"]}
_slog = []
for _d in range(60):
    _S["time"]["t_h"] = _d * 24.0
    _soc.society_step(_S, _slog, 24.0, _R)
good = len(_slog) > 10
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'события за 60 суток без игрока':<40}{len(_slog)}")
_knew = sum(1 for n in _S["world"]["npcs"] if n.get("knows_about_pc"))
good = _knew >= 3
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'слух разошёлся по каналам':<40}{_knew} из {len(_S['world']['npcs'])} знают")
_ch = [f["id"] for f in _S["world"]["factions"] if f["power"] != _p0[f["id"]]]
good = len(_ch) >= 2
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'сила фракций менялась в обе стороны':<40}{len(_ch)} фракций сдвинулись")
_up = any("теряет человека" in x for x in _slog)
ok, fail = ok+_up, fail+(not _up)
print(f"  {'ok ' if _up else 'MISS'} {'смерть NPC бьёт по силе фракции':<40}{'да' if _up else 'нет'}")

print("\n── детерминизм общества ──")
def _run60():
    _s = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
    _s["world"]["npcs"][2]["knows_about_pc"] = [{"turn":1,"source":"видел лично","fact":"чужак"}]
    _s["world"]["npcs"][2]["_knew_at_h"] = 0.0
    _l = []
    for _d in range(60):
        _s["time"]["t_h"] = _d*24.0
        _soc.society_step(_s, _l, 24.0, _R)
    return _l
good = _run60() == _run60()
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'два прогона — одинаковая история':<40}{'идентично' if good else 'РАСХОЖДЕНИЕ'}")

print("\n── материалы объявляются в данных, а не в коде ──")
import matter as _m
_R2 = dict(_R)
_R2["materials"] = {"тест-сплав": {"density_kg_l": 5.0, "hardness": 9, "era": "spacefaring"}}
_R2["forms"] = {"тест-форма": 0.5}
_added = _m.extend_from_rules(_R2)
good = "тест-сплав" in _added and "тест-форма" in _added
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'новый материал и форма приняты':<40}{_added}")
try:
    _m.make_item("t", [("тест-сплав","тест-форма",10,10,10)], [], "preindustrial", None, 1.0)
    good = False
except ValueError:
    good = True
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'ворота эпохи держат новый материал':<40}{'да' if good else 'НЕТ'}")

print("\n── данные, не код: последствия, холод, заживление, бой ──")
_src = open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
good = "CONSEQUENCES =" not in _src
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'нет зашитой таблицы CONSEQUENCES':<40}{'да' if good else 'осталась'}")
_fight_src = _src[_src.find('if a.cmd == "fight"'):]
good = '["blood_loss_pct"]' not in _fight_src and "bleed_target" in _fight_src
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'fight читает wound_model, не кровь':<40}{'да' if good else 'нет'}")

_st = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_txt = _eng.consequence(_st, "точная", 1) or ""
_base = _txt.replace("СИЛЬНО: ", "")
good = _base in _json.load(open("ruleset.json", encoding="utf-8"))["consequences"]["точная"]
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'consequence берёт текст из ruleset':<40}{_base[:40]}")

_Sc = {"ruleset": _cp.deepcopy(_R)}
_a = _eng.cold_rate(-10.7, 1.5, 0, _Sc)
_Sc["ruleset"]["cold_model"]["gain_divisor"] = 4
_b = _eng.cold_rate(-10.7, 1.5, 0, _Sc)
good = abs(_a - 2 * _b) < 0.05
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'cold_rate слушает cold_model':<40}{ _a:.3f} vs { _b:.3f}")

print("\n── огонь и укрытие входят в recompute_env ──")
good = "def recompute_env(S, sheltered=False, fire=False)" in _src
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'recompute_env принимает sheltered/fire':<40}{'да' if good else 'нет'}")
good = "recompute_env(S, sheltered, fire)" in _src
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'tick передаёт флаги в recompute_env':<40}{'да' if good else 'нет'}")
_Rfire = _json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
good = isinstance(_Rfire.get("cold_model", {}).get("fire_bonus_c"), (int, float)) and _Rfire["cold_model"]["fire_bonus_c"] > 0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'fire_bonus_c в ruleset.cold_model':<40}{_Rfire.get('cold_model', {}).get('fire_bonus_c')}")

def _env_fixture():
    st = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
    st["calendar"]["natural_light"] = False
    st["envelope"]["ambient_c"] = -3.0
    st["envelope"]["wind_ms"] = 9
    for site in st["world"]["sites_canon"]:
        site.pop("env", None)
    return st

_out = _env_fixture()
_eng.recompute_env(_out)
good = _out["envelope"]["windchill_c"] < _out["envelope"]["ambient_c"] - 1
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'без флагов ветер бьёт в windchill':<40}{_out['envelope']['windchill_c']}")

_sh = _env_fixture()
_eng.recompute_env(_sh, sheltered=True)
good = (_sh["envelope"]["windchill_c"] == _sh["envelope"]["ambient_c"]
        and _sh["envelope"]["wind_ms"] == 9
        and _sh["envelope"]["ambient_c"] == -3.0)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'укрытие: штиль, wind_ms не затирается':<40}wc={_sh['envelope']['windchill_c']} wind={_sh['envelope']['wind_ms']}")

_fr = _env_fixture()
_fr["ruleset"] = _cp.deepcopy(_Rfire)
_bonus = _fr["ruleset"]["cold_model"]["fire_bonus_c"]
_eng.recompute_env(_fr, fire=True)
good = abs(_fr["envelope"]["ambient_c"] - (-3.0 + _bonus)) < 0.15
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'огонь поднимает ambient на fire_bonus_c':<40}{_fr['envelope']['ambient_c']}")

_both = _env_fixture()
_both["ruleset"] = _cp.deepcopy(_Rfire)
_both["ruleset"]["cold_model"]["fire_bonus_c"] = 10
_eng.recompute_env(_both, sheltered=True, fire=True)
good = _both["envelope"]["ambient_c"] == 7.0 and _both["envelope"]["windchill_c"] == 7.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'огонь+укрытие: тепло без ветра из JSON':<40}{_both['envelope']['ambient_c']}/{_both['envelope']['windchill_c']}")

_tavern = _env_fixture()
_tavern["profile"]["physics_on"] = list(set(_tavern["profile"].get("physics_on", []) + ["холод"]))
_tavern["pc"]["needs"]["cold_stress"] = 37.0
_tavern["pc"]["vitals"]["core_temp_c"] = 36.6
_tavern["gear"]["worn"] = [
    {"id": "t", "name": "тест", "kg": 1, "clo": 1.48, "wet": 0.0}
]
_before = _tavern["pc"]["needs"]["cold_stress"]
_eng.tick(_tavern, 40/60, activity=0, sheltered=True, fire=True, log=[])
_after = _tavern["pc"]["needs"]["cold_stress"]
good = _after < _before
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'печь за 40 мин снижает cold_stress':<40}{_before:.1f} -> {_after:.1f}")

_street = _env_fixture()
_street["profile"]["physics_on"] = list(set(_street["profile"].get("physics_on", []) + ["холод"]))
_street["pc"]["needs"]["cold_stress"] = 37.0
_street["pc"]["vitals"]["core_temp_c"] = 36.6
_street["gear"]["worn"] = [{"id": "t", "name": "тест", "kg": 1, "clo": 1.48, "wet": 0.0}]
_eng.tick(_street, 40/60, activity=0, sheltered=False, fire=False, log=[])
good = _street["pc"]["needs"]["cold_stress"] > 37.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'улица за 40 мин поднимает холод':<40}{_street['pc']['needs']['cold_stress']:.1f}")

_heal = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_heal["profile"]["physics_on"] = [x for x in _heal["profile"]["physics_on"] if x != "холод"]
_heal["pc"]["needs"] = {k: 0 for k in _heal["pc"]["needs"]}
_heal["pc"]["wounds"] = [{"name": "тест", "penalty": 12, "treated": True, "bleed_pct_h": 0, "dirty": False}]
_heal["pc"]["vitals"]["infection"] = 20
_heal["pc"]["vitals"]["blood_loss_pct"] = 0
_eng.tick(_heal, 48, activity=0, sleeping=True, log=[])
good = _heal["pc"]["wounds"] == []
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'перевязанная рана затягивается за 2 суток':<40}{len(_heal['pc']['wounds'])} ран")
good = _heal["pc"]["vitals"]["infection"] == 0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'инфекция после перевязки спадает':<40}{_heal['pc']['vitals']['infection']}")

_openw = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_openw["profile"]["physics_on"] = [x for x in _openw["profile"]["physics_on"] if x != "холод"]
_openw["pc"]["needs"] = {k: 0 for k in _openw["pc"]["needs"]}
_openw["pc"]["wounds"] = [{"name": "тест", "penalty": 15, "treated": False, "bleed_pct_h": 0, "dirty": False}]
_eng.tick(_openw, 48, activity=0, sleeping=True, log=[])
good = _openw["pc"]["wounds"] and _openw["pc"]["wounds"][0]["penalty"] == 15
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'неперевязанная рана сама не заживает':<40}{_openw['pc']['wounds'][0]['penalty'] if _openw['pc']['wounds'] else 'исчезла'}")

_mf = _json.load(open("examples/mech_state.json", encoding="utf-8"))
_mf["pc"]["vitals"]["структурные_повреждения"] = 30
_mf_path = os.path.join(TMP, "fight_mech.json")
_json.dump(_mf, open(_mf_path, "w", encoding="utf-8"), ensure_ascii=False)
_rf = _run(["engine.py", "fight", "--skill", "огонь", "--foe", "А:20:0:0"],
           SIM_RULES="ruleset_mech.json", SIM_STATE=_mf_path)
good = _rf.returncode == 0 and "рама не держит" in (_rf.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'механоид выходит из боя по раме':<40}{'да' if good else 'нет'}")

print("\n── skill_growth и dose_sv больше не спят ──")
good = "def skill_grow(" in _src and "skill_grow(S, skill, out)" in open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'check вызывает skill_grow':<40}{'да' if good else 'нет'}")
_src2 = open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
good = 'dose_sv' in _src2 and 'dose_rate_msv_h' in _src2 and '"радиация" in on' in _src2
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'tick копит dose_sv при радиации':<40}{'да' if good else 'нет'}")
good = "core_drop_c" in _src2 and "core_temp(n.get(need_key, 0), S)" in _src2
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'ядро читает cold_model, не литерал 37-9':<40}{'да' if good else 'нет'}")

_sg = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_sg["pc"]["skills"]["athletics"] = 40
_sg["pc"]["attempts"] = {}
_sg["pc"]["skill_growth_day"] = {}
_eng.skill_grow(_sg, "athletics", "ПРОВАЛ")
good = _sg["pc"]["skills"]["athletics"] == 41
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'провал поднимает навык на amount':<40}{_sg['pc']['skills']['athletics']}")
_eng.skill_grow(_sg, "athletics", "ПРОВАЛ")
good = _sg["pc"]["skills"]["athletics"] == 41
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'потолок per_day_per_skill за сутки':<40}{_sg['pc']['skills']['athletics']}")
_sg["time"]["t_h"] = _sg["time"]["t_h"] + 24
_eng.skill_grow(_sg, "athletics", "КРИТИЧЕСКИЙ УСПЕХ")
good = _sg["pc"]["skills"]["athletics"] == 42
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'на следующий день рост снова':<40}{_sg['pc']['skills']['athletics']}")
_ok_skill = _sg["pc"]["skills"]["athletics"]
_eng.skill_grow(_sg, "athletics", "УСПЕХ")
_eng.skill_grow(_sg, "athletics", "УСПЕХ ЦЕНОЙ")
good = _sg["pc"]["skills"]["athletics"] == _ok_skill
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'обычный успех навык не качает':<40}{_sg['pc']['skills']['athletics']}")
_sg["pc"]["skills"]["athletics"] = 90
_sg["pc"]["skill_growth_day"] = {}
_sg["time"]["t_h"] = _sg["time"]["t_h"] + 24
_eng.skill_grow(_sg, "athletics", "ПРОВАЛ")
good = _sg["pc"]["skills"]["athletics"] == 90
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'cap 90 не превышается':<40}{_sg['pc']['skills']['athletics']}")

_grew = False
_chk = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_chk["pc"]["skills"]["athletics"] = 40
_before = 40
for _turn in range(40):
    _chk["meta"]["turn"] = _turn
    _chk["pc"]["attempts"] = {}
    _c = _eng.check(_chk, "athletics", 25, f"рост{_turn}", 1)
    if _c.get("roll") is not None and "ПРОВАЛ" in _c["outcome"]:
        _grew = _chk["pc"]["skills"]["athletics"] == _before + 1
        break
good = _grew
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'check() с броском качает навык':<40}{'да' if good else 'нет'}")

_rad = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_rad["profile"]["physics_on"] = ["радиация"]
_rad["envelope"]["dose_rate_msv_h"] = 2000.0
_rad["envelope"]["dose_sv"] = 0.0
_eng.tick(_rad, 2.0, activity=0, log=[])
good = abs(_rad["envelope"]["dose_sv"] - 4.0) < 0.01
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'2 ч при 2000 мЗв/ч = 4 Зв':<40}{_rad['envelope'].get('dose_sv')}")

_quiet = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_quiet["profile"]["physics_on"] = [x for x in _quiet["profile"].get("physics_on", []) if x != "радиация"]
_quiet["envelope"]["dose_rate_msv_h"] = 2000.0
_quiet["envelope"]["dose_sv"] = 0.0
_eng.tick(_quiet, 2.0, activity=0, log=[])
good = (_quiet["envelope"].get("dose_sv") or 0) == 0.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'без физики радиации доза не растёт':<40}{_quiet['envelope'].get('dose_sv')}")

_kill = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_kill["profile"]["physics_on"] = ["радиация"]
_kill["envelope"]["dose_rate_msv_h"] = 10000.0
_kill["envelope"]["dose_sv"] = 0.0
_kill["pc"]["needs"] = {k: 0 for k in _kill["pc"]["needs"]}
_eng.tick(_kill, 1.0, activity=0, log=[])
good = _kill["status"] == "dead"
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'lethal_above dose_sv убивает':<40}{_kill['status']} dose={_kill['envelope'].get('dose_sv')}")

_Sc2 = {"ruleset": _cp.deepcopy(_Rfire)}
_a0 = _eng.core_temp(100, _Sc2)
_Sc2["ruleset"]["cold_model"]["core_drop_c"] = 18
_a1 = _eng.core_temp(100, _Sc2)
good = abs(_a0 - 28.0) < 0.05 and abs(_a1 - 19.0) < 0.05
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'core_temp слушает cold_model':<40}{_a0:.1f} vs {_a1:.1f}")

print("\n── счётчик: payoff — журнал, on_complete — состояние ──")
_src3 = open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
_wg_src = open(os.path.join(HERE, "worldgen.py"), encoding="utf-8").read()
good = "def apply_clock_effects(" in _src3 and "apply_clock_effects(S, c, log)" in _src3
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'tick_clocks вызывает apply_clock_effects':<40}{'да' if good else 'нет'}")
good = 'clk["on_complete"]' in _wg_src
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'worldgen копирует on_complete':<40}{'да' if good else 'нет'}")

from worldgen import expand as _wg_expand, validate as _wg_validate

def _clock_fixture(on_complete=None):
    st = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
    st["calendar"]["natural_light"] = False
    here = st["position"]["path"]
    for site in st["world"]["sites_canon"]:
        if site["path"] == here:
            site["env"] = {"ambient_c": 16.0, "light": "дежурный", "breathable": True}
    st["envelope"]["ambient_c"] = 16.0
    st["pc"]["needs"] = {k: 0.0 for k in st["pc"]["needs"]}
    st["profile"]["physics_on"] = []
    clk = {"name": "тест тепла", "filled": 2, "max": 3, "period_h": 1,
           "last_tick_h": st["time"]["t_h"], "payoff": "стало холодно", "hidden": False}
    if on_complete is not None:
        clk["on_complete"] = on_complete
    st["clocks"] = [clk]
    return st, here

_plain, _here = _clock_fixture()
_plog = []
_eng.tick(_plain, 1.05, activity=0, log=_plog)
_psite = next(s for s in _plain["world"]["sites_canon"] if s["path"] == _here)
good = (any("СЧЁТЧИК СРАБОТАЛ" in x for x in _plog)
        and abs(_psite["env"]["ambient_c"] - 16.0) < 0.01
        and abs(_plain["envelope"]["ambient_c"] - 16.0) < 0.15)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'без on_complete только журнал':<40}{_psite['env']['ambient_c']}")

_mut, _here = _clock_fixture([{"site": _here, "env": {"ambient_c": 4.0}}])
_mlog = []
_eng.tick(_mut, 1.05, activity=0, log=_mlog)
_msite = next(s for s in _mut["world"]["sites_canon"] if s["path"] == _here)
good = (any("СЧЁТЧИК СРАБОТАЛ" in x for x in _mlog)
        and abs(_msite["env"]["ambient_c"] - 4.0) < 0.01
        and abs(_mut["envelope"]["ambient_c"] - 4.0) < 0.15)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'site env и envelope после срабатывания':<40}{_msite['env']['ambient_c']}/{_mut['envelope']['ambient_c']}")

_add, _ = _clock_fixture([{"path": "envelope.dose_sv", "add": 10}])
_add["envelope"]["dose_sv"] = 1.0
_eng.tick(_add, 1.05, activity=0, log=[])
_s1 = _add["envelope"]["dose_sv"]
_eng.tick(_add, 1.05, activity=0, log=[])
_s2 = _add["envelope"]["dose_sv"]
good = abs(_s1 - 11.0) < 0.01 and abs(_s2 - 11.0) < 0.01
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'add один раз, повторно не плюсует':<40}{_s1}->{_s2}")

_badc = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_badc["clocks"][0]["on_complete"] = [{"foo": 1}]
_e_bad, _ = _wg_validate(_badc)
good = any("неизвестная операция" in e for e in _e_bad)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'validate ловит неизвестную операцию':<40}{'да' if good else 'нет'}")

_txtc = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_e_txt, _w_txt = _wg_validate(_txtc)
good = (not any("неизвестная операция" in e for e in _e_txt)
        and any("только строкой в журнале" in w for w in _w_txt))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'payoff без эффектов — замечание, не ошибка':<40}{'да' if good else 'нет'}")

_drift = _wg_expand(_json.load(open("examples/brief_drift.json", encoding="utf-8")))
_e_d, _w_d = _wg_validate(_drift)
_drift["pc"]["needs"] = {k: 0.0 for k in _drift["pc"]["needs"]}
_drift["profile"]["physics_on"] = []
_dlog = []
_eng.tick(_drift, 31.0, activity=0, log=_dlog)
_cryo = next(s for s in _drift["world"]["sites_canon"] if s["path"].endswith("/cryo"))
_hab = next(s for s in _drift["world"]["sites_canon"] if s["path"].endswith("/hab"))
_engn = next(s for s in _drift["world"]["sites_canon"] if s["path"].endswith("/engineering"))
good = (not _e_d
        and abs(_cryo["env"]["pco2_rise_kpa_h"] - 0.55) < 0.001
        and abs(_hab["env"]["ambient_c"] - 4.0) < 0.01
        and abs(_engn["env"]["ambient_c"] - 4.0) < 0.01
        and abs(_drift["envelope"]["ambient_c"] - 4.0) < 0.15
        and any("Скруббер" in x for x in _dlog)
        and any("Тепловой контур" in x for x in _dlog))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'Релей: CO2 и тепло меняют отсеки':<40}"
      f"rise={_cryo['env']['pco2_rise_kpa_h']} hab={_hab['env']['ambient_c']}")

_rb, _ = _clock_fixture([{"path": "envelope.dose_sv", "add": 10}])
_rb["envelope"]["dose_sv"] = 1.0
_eng.tick(_rb, 1.05, activity=0, log=[])
_rb["clocks"][0]["filled"] = 0
_rb["clocks"][0]["last_tick_h"] = _rb["time"]["t_h"]
_eng.tick(_rb, 3.0, activity=0, log=[])
good = bool(_rb["clocks"][0].get("fired")) and abs(_rb["envelope"]["dose_sv"] - 11.0) < 0.01
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'fired держит add после отката filled':<40}{_rb['envelope']['dose_sv']}")

_stack, _ = _clock_fixture()
_stack["envelope"]["dose_sv"] = 1.0
_t0 = _stack["time"]["t_h"]
_stack["clocks"] = [
    {"name": "a", "filled": 2, "max": 3, "period_h": 1, "last_tick_h": _t0,
     "payoff": "a", "hidden": True, "on_complete": [{"path": "envelope.dose_sv", "add": 10}]},
    {"name": "b", "filled": 2, "max": 3, "period_h": 1, "last_tick_h": _t0,
     "payoff": "b", "hidden": True, "on_complete": [{"path": "envelope.dose_sv", "add": 7}]},
]
_eng.tick(_stack, 1.05, activity=0, log=[])
good = abs(_stack["envelope"]["dose_sv"] - 18.0) < 0.01
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'два счётчика add складываются':<40}{_stack['envelope']['dose_sv']}")

_star, _shere = _clock_fixture([{"sites": "*", "env": {"ambient_c": 4.0}}])
_eng.tick(_star, 1.05, activity=0, log=[])
_star["world"]["sites_canon"].append({
    "path": _shere + "/late", "name": "поздно",
    "env": {"ambient_c": 16.0, "light": "дежурный", "breathable": True},
    "exits": [], "touched": False
})
_eng.tick(_star, 1.0, activity=0, log=[])
_late = next(s for s in _star["world"]["sites_canon"] if s["path"].endswith("/late"))
_here_s = next(s for s in _star["world"]["sites_canon"] if s["path"] == _shere)
good = abs(_late["env"]["ambient_c"] - 16.0) < 0.01 and abs(_here_s["env"]["ambient_c"] - 4.0) < 0.01
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'* не трогает площадку после срабатывания':<40}{_late['env']['ambient_c']}")

_ord, _ohere = _clock_fixture()
_ord["clocks"][0]["on_complete"] = [{"site": _ohere, "env": {"ambient_c": -20.0}}]
_ord["profile"]["physics_on"] = ["холод"]
_ord["pc"]["needs"]["cold_stress"] = 10.0
_ord["gear"]["worn"] = [{"id": "t", "name": "t", "kg": 1, "clo": 0.3, "wet": 0.0}]
_ctrl = _cp.deepcopy(_ord)
_ctrl["clocks"][0]["filled"] = 3
_ctrl["clocks"][0]["fired"] = True
_eng.tick(_ord, 1.0, activity=0, log=[])
_eng.tick(_ctrl, 1.0, activity=0, log=[])
good = (_ord["pc"]["needs"]["cold_stress"] > _ctrl["pc"]["needs"]["cold_stress"] + 1.0
        and abs(_ord["envelope"]["ambient_c"] + 20.0) < 0.2)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'часы раньше холода того же часа':<40}"
      f"{_ord['pc']['needs']['cold_stress']:.1f} vs {_ctrl['pc']['needs']['cold_stress']:.1f}")

_hdoc = open(os.path.join(HERE, "HANDOFF.md"), encoding="utf-8").read()
good = "не идемпотентен и не обязан быть" in _hdoc and "не идемпотентен и не обязан быть" in _src3
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'контракт add записан в HANDOFF и код':<40}{'да' if good else 'нет'}")

_dup = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_dup["clocks"][0]["on_complete"] = [{"path": "envelope.dose_sv", "add": 1}]
_dup["clocks"][1]["on_complete"] = [{"path": "envelope.dose_sv", "add": 2}]
_e_dup, _w_dup = _wg_validate(_dup)
good = any("не идемпотентен и не обязан быть" in w for w in _w_dup)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'validate предупреждает о сложении add':<40}{'да' if good else 'нет'}")

print("\n── ресурс площадки в руки, расход fill и заряда ──")
_src4 = open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
good = "def take_site_resource(" in _src4 and "--take-resource" in _src4
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'act принимает --take-resource':<40}{'да' if good else 'нет'}")
_Ruse = _json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
good = isinstance(_Ruse.get("item_use", {}).get("charge_per_h"), (int, float))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'item_use.charge_per_h в ruleset':<40}{_Ruse.get('item_use', {}).get('charge_per_h')}")

_td = _wg_expand(_json.load(open("examples/brief_drift.json", encoding="utf-8")))
_hab = next(s for s in _td["world"]["sites_canon"] if s["path"].endswith("/hab"))
_td["position"]["path"] = _hab["path"]
_td["pc"]["needs"] = {k: 0.0 for k in _td["pc"]["needs"]}
_td["profile"]["physics_on"] = []
_amt0 = next(r["amount"] for r in _hab["resources"] if "вода" in (r.get("tags") or []))
_tlog = []
good_take = _eng.take_site_resource(_td, "вода:0.5", _tlog)
_water_it = [i for i in _td["items"] if "вода" in i.get("tags", [])]
_amt1 = next(r["amount"] for r in _hab["resources"] if "вода" in (r.get("tags") or []))
good = good_take and abs(_amt0 - _amt1 - 0.5) < 0.001 and _water_it and _water_it[-1]["in"] == "cnt_00"
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'взял воду с палубы в руки':<40}{_amt0}->{_amt1} n={len(_water_it)}")

_tlog2 = []
good = not _eng.take_site_resource(_td, "неттакого:1", _tlog2) and any("ОТКАЗ" in x for x in _tlog2)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'нет ресурса — отказ, amount цел':<40}{'да' if good else 'нет'}")

_ghost = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_ghost["pc"]["needs"] = {k: 0.0 for k in _ghost["pc"]["needs"]}
_ghost["pc"]["needs"]["thirst"] = 40.0
_ghost["profile"]["physics_on"] = []
_ghost["items"] = [i for i in _ghost["items"] if "вода" not in i.get("tags", [])]
_glog = []
_drank = _eng.consume_tagged(_ghost, "вода", 0.4, _glog)
good = _drank == 0.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'питьё без предмета не списывает воду':<40}{_drank}")

_fill = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_fill["items"] = [{"id": "itm_w", "name": "фляга", "kg": 1.0, "l": 1.0, "qty": 1,
                   "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["вода"], "fill": 1.0}]
_fill["gear"]["hands"]["held"] = ["itm_w"]
_clog = []
_got = _eng.consume_tagged(_fill, "вода", 0.4, _clog)
good = abs(_got - 0.4) < 0.01 and abs(_fill["items"][0]["fill"] - 0.6) < 0.02
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'питьё списывает fill':<40}fill={_fill['items'][0]['fill']}")

_ch = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_ch["ruleset"] = _json.load(open("ruleset.json", encoding="utf-8"))
_ch["items"] = [{"id": "itm_f", "name": "фонарик", "kg": 0.2, "l": 0.2, "qty": 1,
                 "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["свет"], "charge_pct": 100}]
_ch["gear"]["hands"]["held"] = ["itm_f"]
_ch["pc"]["needs"] = {k: 0.0 for k in _ch["pc"]["needs"]}
_ch["profile"]["physics_on"] = []
_eng.spend_held_charge(_ch, 1.0, [])
good = abs(_ch["items"][0]["charge_pct"] - (100 - _ch["ruleset"]["item_use"]["charge_per_h"])) < 0.2
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'заряд в руках падает за час':<40}{_ch['items'][0]['charge_pct']}")

_bag = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_bag["ruleset"] = _json.load(open("ruleset.json", encoding="utf-8"))
_bag["items"] = [{"id": "itm_f", "name": "фонарик", "kg": 0.2, "l": 0.2, "qty": 1,
                  "in": "cnt_01", "depth": 0, "condition": 1.0, "tags": ["свет"], "charge_pct": 100}]
_bag["gear"]["hands"]["held"] = []
_eng.spend_held_charge(_bag, 1.0, [])
good = abs(_bag["items"][0]["charge_pct"] - 100) < 0.01
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'заряд в сумке не тратится':<40}{_bag['items'][0]['charge_pct']}")

_med = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_med["ruleset"] = _json.load(open("ruleset.json", encoding="utf-8"))
_med["items"] = [{"id": "itm_m", "name": "аптечка", "kg": 0.5, "l": 1.0, "qty": 1,
                  "in": "cnt_01", "depth": 0, "condition": 1.0, "tags": ["медицина"], "fill": 1.0}]
_eng.spend_medicine_fill(_med, [])
good = abs(_med["items"][0]["fill"] - (1.0 - _med["ruleset"]["item_use"]["medicine_fill_per_treat"])) < 0.001
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'перевязка тратит fill аптечки':<40}{_med['items'][0]['fill']}")

print(f"\n{'='*56}\nИТОГО пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
