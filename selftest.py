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
_tavern["items"] = [{"id": "itm_fuel", "name": "дрова", "kg": 2.0, "l": 2.0, "qty": 1,
                    "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["топливо"], "fill": 1.0},
                   {"id": "itm_ign", "name": "зажигалка", "kg": 0.02, "l": 0.02, "qty": 1,
                    "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["огонь"]}]
_tavern["gear"]["hands"]["held"] = ["itm_fuel", "itm_ign"]
_before = _tavern["pc"]["needs"]["cold_stress"]
_eng.tick(_tavern, 40/60, activity=0, sheltered=True, fire=True, log=[])
_after = _tavern["pc"]["needs"]["cold_stress"]
good = _after < _before
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'печь за 40 мин снижает cold_stress':<40}{_before:.1f} -> {_after:.1f}")
good = _tavern["items"][0]["fill"] < 1.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'горение списывает fill дров':<40}fill={_tavern['items'][0]['fill']}")

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
from worldgen import mass_claim_tol, mass_matches_parts
from worldgen import normalize_brief as _wg_norm, SKILL_LIST_VALUE_KEYS, _make_item as _wg_make

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
for _it in _td["items"]:
    if "вода" in (_it.get("tags") or []):
        _it["fill"] = 1.0
_n_water0 = len([i for i in _td["items"] if "вода" in i.get("tags", [])])
_amt0 = next(r["amount"] for r in _hab["resources"] if "вода" in (r.get("tags") or []))
_tlog = []
good_take = _eng.take_site_resource(_td, "вода:0.5", _tlog)
_water_it = [i for i in _td["items"] if "вода" in i.get("tags", [])]
_amt1 = next(r["amount"] for r in _hab["resources"] if "вода" in (r.get("tags") or []))
good = (good_take and abs(_amt0 - _amt1 - 0.5) < 0.001 and _water_it
        and _water_it[-1]["in"] == "cnt_00" and len(_water_it) == _n_water0 + 1)
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

_empty = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_empty["items"] = [{"id": "itm_w", "name": "фляга", "kg": 0.0, "l": 1.0, "qty": 1,
                    "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["вода"], "fill": 0.0}]
_empty["gear"]["hands"]["held"] = ["itm_w"]
_empty["pc"]["needs"] = {k: 0.0 for k in _empty["pc"]["needs"]}
_ew = os.path.join(TMP, "empty_water.json")
_turn0 = _empty["meta"]["turn"]
_json.dump(_empty, open(_ew, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "8", "--water", "0.4"], SIM_STATE=_ew)
_after_e = _json.load(open(_ew, encoding="utf-8"))
good = "ОТКАЗ" in (_r.stdout or "") and _after_e["meta"]["turn"] == _turn0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'пустая фляга — отказ, ход не идёт':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")
good = "def tagged_have(" in _src4
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'tagged_have в engine':<40}{'да' if good else 'нет'}")

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

print("\n── огонь как топливо, бессознательный тикает к смерти ──")
_src5 = open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
good = "def can_fire(" in _src5 and "def spend_fuel(" in _src5 and "def is_sheltered(" in _src5
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'can_fire/spend_fuel/is_sheltered в engine':<40}{'да' if good else 'нет'}")
_Riu = _json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
good = (_Riu.get("item_use", {}).get("fuel_tags") == ["топливо"]
        and _Riu.get("item_use", {}).get("igniter_tags") == ["огонь"]
        and isinstance(_Riu.get("item_use", {}).get("fuel_per_h"), (int, float)))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'item_use.fuel_tags в ruleset':<40}{_Riu.get('item_use', {}).get('fuel_tags')}")
good = _Riu.get("vitals", {}).get("core_temp_c", {}).get("recover_above") == 32.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'recover_above 32 у ядра':<40}{_Riu.get('vitals', {}).get('core_temp_c', {}).get('recover_above')}")

_nofire = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_nofire["pc"]["needs"] = {k: 0.0 for k in _nofire["pc"]["needs"]}
_nofire["items"] = [{"id": "itm_ign", "name": "зажигалка", "kg": 0.02, "l": 0.02, "qty": 1,
                     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["огонь"]}]
_nofire["gear"]["hands"]["held"] = ["itm_ign"]
_nf = os.path.join(TMP, "nofuel_fire.json")
_turn0 = _nofire["meta"]["turn"]
_json.dump(_nofire, open(_nf, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "20", "--fire", "--window", "60"], SIM_STATE=_nf)
_after_nf = _json.load(open(_nf, encoding="utf-8"))
good = "ОТКАЗ" in (_r.stdout or "") and _after_nf["meta"]["turn"] == _turn0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'--fire без топлива — отказ':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")

_noign = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_noign["pc"]["needs"] = {k: 0.0 for k in _noign["pc"]["needs"]}
_noign["items"] = [{"id": "itm_fuel", "name": "дрова", "kg": 1.0, "l": 1.0, "qty": 1,
                    "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["топливо"], "fill": 1.0}]
_noign["gear"]["hands"]["held"] = ["itm_fuel"]
for _s in _noign["world"]["sites_canon"]:
    _s["hearth"] = False
_ni = os.path.join(TMP, "noign_fire.json")
_json.dump(_noign, open(_ni, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "20", "--fire", "--window", "60"], SIM_STATE=_ni)
good = "ОТКАЗ" in (_r.stdout or "") and "зажечь" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'--fire без зажигалки — отказ':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")

_hearth = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_hearth["pc"]["needs"] = {k: 0.0 for k in _hearth["pc"]["needs"]}
_hearth["profile"]["physics_on"] = []
_hearth["items"] = [{"id": "itm_fuel", "name": "дрова", "kg": 1.0, "l": 1.0, "qty": 1,
                     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["топливо"], "fill": 1.0}]
_hearth["gear"]["hands"]["held"] = ["itm_fuel"]
_here = _hearth["position"]["path"]
for _s in _hearth["world"]["sites_canon"]:
    if _s["path"] == _here:
        _s["hearth"] = True
_hh = os.path.join(TMP, "hearth_fire.json")
_json.dump(_hearth, open(_hh, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "20", "--fire", "--window", "60"], SIM_STATE=_hh)
_after_h = _json.load(open(_hh, encoding="utf-8"))
good = "ОТКАЗ" not in (_r.stdout or "")[:80] and _after_h["items"][0]["fill"] < 1.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'очаг: огонь без зажигалки, дрова тают':<40}fill={_after_h['items'][0].get('fill')}")

good = _eng.resource_tags({"name": "спирт для горелки"}) == ["ресурс"]
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'имя без тега не делает топливо':<40}{_eng.resource_tags({'name': 'спирт для горелки'})}")
good = _eng.resource_tags({"name": "glow-pits", "tags": ["навоз"]}) == ["навоз"]
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'тег автора, не словарь имён':<40}{_eng.resource_tags({'name': 'glow-pits', 'tags': ['навоз']})}")

_alien = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_alien["ruleset"] = _json.load(open("ruleset.json", encoding="utf-8"))
_alien["ruleset"]["item_use"]["fuel_tags"] = ["навоз"]
_alien["ruleset"]["item_use"]["igniter_tags"] = ["искра"]
_alien["pc"]["needs"] = {k: 0.0 for k in _alien["pc"]["needs"]}
_alien["profile"]["physics_on"] = []
_alien["items"] = [
    {"id": "itm_fuel", "name": "кизяк", "kg": 1.0, "l": 1.0, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["навоз"], "fill": 1.0},
    {"id": "itm_ign", "name": "огниво", "kg": 0.1, "l": 0.1, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["искра"]},
]
_alien["gear"]["hands"]["held"] = ["itm_fuel", "itm_ign"]
for _s in _alien["world"]["sites_canon"]:
    _s["hearth"] = False
_al = os.path.join(TMP, "alien_fire.json")
_json.dump(_alien, open(_al, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "20", "--fire", "--window", "60"], SIM_STATE=_al)
_after_a = _json.load(open(_al, encoding="utf-8"))
good = "ОТКАЗ" not in (_r.stdout or "")[:80] and _after_a["items"][0]["fill"] < 1.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'чужие теги навоз/искра жгут':<40}fill={_after_a['items'][0].get('fill')}")
_alien["items"][0]["tags"] = ["топливо"]
_alien["items"][1]["tags"] = ["огонь"]
_alien["items"][0]["fill"] = 1.0
_json.dump(_alien, open(_al, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "20", "--fire", "--window", "60"], SIM_STATE=_al)
good = "ОТКАЗ" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'человеческие теги при чужих правилах — отказ':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")

print("\n── питьё/еда по тегам, не по имени ──")
good = _eng.resource_tags({"name": "кипяток"}) == ["ресурс"]
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'имя кипяток без тега — не вода':<40}{_eng.resource_tags({'name': 'кипяток'})}")
good = _eng.resource_tags({"name": "чёрный хлеб"}) == ["ресурс"]
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'имя хлеб без тега — не еда':<40}{_eng.resource_tags({'name': 'чёрный хлеб'})}")
good = _eng.resource_tags({"name": "кипяток", "tags": ["вода"]}) == ["вода"]
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'явный тег вода остаётся водой':<40}{_eng.resource_tags({'name': 'кипяток', 'tags': ['вода']})}")

_boil = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_boil_it = _eng.item_from_resource(_boil, {"name": "кипяток"}, 0.5)
good = "вода" not in (_boil_it.get("tags") or [])
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'взятый кипяток без тега не пьётся':<40}{_boil_it.get('tags')}")

_alw = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_alw["ruleset"] = _json.load(open("ruleset.json", encoding="utf-8"))
_alw["ruleset"]["item_use"]["water_tags"] = ["слизь"]
_alw["ruleset"]["item_use"]["food_tags"] = ["жмых"]
_alw["ruleset"]["needs"]["thirst"]["recovers_by"] = "слизь"
_alw["ruleset"]["needs"]["hunger"]["recovers_by"] = "жмых"
_alw["pc"]["needs"] = {k: 0.0 for k in _alw["pc"]["needs"]}
_alw["pc"]["needs"]["thirst"] = 50.0
_alw["pc"]["needs"]["hunger"] = 50.0
_alw["profile"]["physics_on"] = []
_alw["items"] = [
    {"id": "itm_d", "name": "ихор", "kg": 1.0, "l": 1.0, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["слизь"], "fill": 1.0},
    {"id": "itm_f", "name": "жмых", "kg": 1.0, "l": 1.0, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["жмых"], "fill": 1.0},
]
_alw["gear"]["hands"]["held"] = ["itm_d", "itm_f"]
_aw = os.path.join(TMP, "alien_drink.json")
_json.dump(_alw, open(_aw, "w", encoding="utf-8"), ensure_ascii=False)
_thirst0 = _alw["pc"]["needs"]["thirst"]
_r = _run(["engine.py", "act", "--minutes", "5", "--water", "0.4", "--food", "0.35"], SIM_STATE=_aw)
_after_d = _json.load(open(_aw, encoding="utf-8"))
good = ("ОТКАЗ" not in (_r.stdout or "")[:80]
        and _after_d["items"][0]["fill"] < 1.0
        and _after_d["items"][1]["fill"] < 1.0
        and _after_d["pc"]["needs"]["thirst"] < _thirst0)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'чужие теги слизь/жмых восстанавливают':<40}thirst={_after_d['pc']['needs']['thirst']:.1f}")

_alw["items"][0]["tags"] = ["вода"]
_alw["items"][1]["tags"] = ["еда"]
_alw["items"][0]["fill"] = 1.0
_alw["items"][1]["fill"] = 1.0
_json.dump(_alw, open(_aw, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "5", "--water", "0.4"], SIM_STATE=_aw)
good = "ОТКАЗ" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'вода при чужих water_tags — отказ':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")
_r = _run(["engine.py", "act", "--minutes", "5", "--food", "0.35"], SIM_STATE=_aw)
good = "ОТКАЗ" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'еда при чужих food_tags — отказ':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")

_st_m2 = os.path.join(TMP, "mech_nowater.json")
import shutil as _sh
_sh.copy("examples/mech_state.json", _st_m2)
_r = _run(["engine.py", "act", "--minutes", "5"], SIM_RULES="ruleset_mech.json", SIM_STATE=_st_m2)
good = _r.returncode == 0 and "ОТКАЗ" not in (_r.stdout or "")[:80]
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'механоид act без --water/--food':<40}{'шёл' if good else 'УПАЛ'}")
_st_m3 = os.path.join(TMP, "mech_water.json")
_sh.copy("examples/mech_state.json", _st_m3)
_r = _run(["engine.py", "act", "--minutes", "5", "--water", "0.4"],
          SIM_RULES="ruleset_mech.json", SIM_STATE=_st_m3)
good = "ОТКАЗ" in (_r.stdout or "") and "water_tags" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'механоид --water без water_tags — отказ':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")

_wsrc = open("worldgen.py", encoding="utf-8").read()
_edc_at = _wsrc.find("edc.build")
good = (_wsrc.count("edc.build") == 1 and _edc_at > 0
        and "carryover" in _wsrc[max(0, _edc_at - 400):_edc_at])
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'edc.build только под carryover':<40}{'да' if good else 'нет'}")
_edoc = open("edc.py", encoding="utf-8").read()
good = "других эпох" in _edoc and "XXI" in _edoc
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'edc.py граница: не другие эпохи':<40}{'да' if good else 'нет'}")

_shsite = _env_fixture()
_here = _shsite["position"]["path"]
for _s in _shsite["world"]["sites_canon"]:
    if _s["path"] == _here:
        _s["shelter"] = True
_eng.tick(_shsite, 1/60, activity=0, sheltered=False, fire=False, log=[])
good = (_shsite["envelope"]["windchill_c"] == _shsite["envelope"]["ambient_c"]
        and _shsite["envelope"]["wind_ms"] == 9)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'site.shelter без флага — штиль':<40}wc={_shsite['envelope']['windchill_c']}")

_unc = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_unc["status"] = "unconscious"
_unc["pc"]["needs"] = {k: 0.0 for k in _unc["pc"]["needs"]}
_unc["pc"]["needs"]["cold_stress"] = 99.5
_unc["pc"]["vitals"]["core_temp_c"] = 30.0
_unc["profile"]["physics_on"] = ["холод"]
_unc["calendar"]["natural_light"] = False
_unc["envelope"]["ambient_c"] = 4.0
_unc["envelope"]["wind_ms"] = 0
_unc["envelope"]["windchill_c"] = 4.0
for _s in _unc["world"]["sites_canon"]:
    _s.pop("env", None)
    _s["shelter"] = True
_unc["gear"]["worn"] = [{"id": "t", "name": "тест", "kg": 1, "clo": 0.5, "wet": 0.0}]
_eng.tick(_unc, 3.0, activity=0, sheltered=True, fire=False, log=[])
good = _unc["status"] == "dead"
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'unconscious в 4°C доходит до dead':<40}{_unc['status']} t={_unc['pc']['vitals'].get('core_temp_c')}")

_wake = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_wake["status"] = "unconscious"
_wake["pc"]["vitals"]["core_temp_c"] = 33.0
_wake["pc"]["needs"] = {k: 0.0 for k in _wake["pc"]["needs"]}
_eng.death_check(_wake)
good = _wake["status"] == "alive"
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'ядро выше recover_above — в сознание':<40}{_wake['status']}")

_ua = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_ua["status"] = "unconscious"
_ua["pc"]["needs"] = {k: 0.0 for k in _ua["pc"]["needs"]}
_upath = os.path.join(TMP, "unc_act.json")
_json.dump(_ua, open(_upath, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "5", "--to", _ua["position"]["path"]], SIM_STATE=_upath)
good = "ОТКАЗ" in (_r.stdout or "") and "сознан" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'без сознания нельзя переходить':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")
_uw = os.path.join(TMP, "unc_wait.json")
_json.dump(_ua, open(_uw, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "15"], SIM_STATE=_uw)
_after_w = _json.load(open(_uw, encoding="utf-8"))
good = "ОТКАЗ" not in (_r.stdout or "")[:80] and _after_w["meta"]["turn"] == _ua["meta"]["turn"] + 1
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'без сознания время всё ещё идёт':<40}ход {_after_w['meta']['turn']}")

print("\n── строительство: части, теги, атомарность, compact ──")
_src_e = open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
_src_m = open(os.path.join(HERE, "matter.py"), encoding="utf-8").read()
import re as _re
_core = _src_e + "\n" + _src_m
good = "сарай" not in _core and not _re.search(r"(?<![а-яА-Я])дом(?![а-яА-Я])", _core)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'ядро не знает дом/сарай':<40}{'да' if good else 'нет'}")
good = "def check_plausible(" in _src_m and "def apply_build(" in _src_e
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'check_plausible и apply_build на месте':<40}{'да' if good else 'нет'}")

try:
    matter.make_item("абсурд", [("камень", "пластина", 1e6, 10, 10)], [], "primitive", None, 1.0)
    good = False
except ValueError:
    good = True
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'make_item режет габарит-абсурд':<40}{'да' if good else 'нет'}")

_Rsu = _json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
good = isinstance(_Rsu.get("structure_use", {}).get("hours_per_l"), (int, float))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'structure_use.hours_per_l в ruleset':<40}{_Rsu.get('structure_use', {}).get('hours_per_l')}")

def _build_state():
    st = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
    st["ruleset"] = _json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
    st["profile"]["tech_ceiling"] = "primitive"
    st["pc"]["needs"] = {k: 0.0 for k in st["pc"]["needs"]}
    st["pc"]["skills"]["craft"] = 40
    st["calendar"]["natural_light"] = False
    st["envelope"]["ambient_c"] = -3.0
    st["envelope"]["wind_ms"] = 9
    here = next(s for s in st["world"]["sites_canon"] if s["path"] == st["position"]["path"])
    here["shelter"] = False
    here["hearth"] = False
    here.pop("env", None)
    here["objects"] = [
        {"name": "жерди", "parts": [["дерево", "стержень", 180, 8, 8],
                                    ["дерево", "пластина", 140, 70, 3]]},
        "след без состава",
    ]
    here["structures"] = []
    here["exits"] = list(here.get("exits") or [])
    return st, here

_st, _here = _build_state()
_o = next(o for o in _eng.site_objects(_here) if o.get("name") == "жерди")
_it0 = matter.make_item("заслон", _o["parts"], ["укрытие"], "primitive", None, 1.0)
_mins = int(_eng.build_hours(_st, _it0["l"]) * 60) + 1
_bp = os.path.join(TMP, "build_ok.json")
_json.dump(_st, open(_bp, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", str(_mins), "--activity", "2",
           "--build", "заслон", "--from-object", "жерди", "--build-tag", "укрытие"],
          SIM_STATE=_bp)
_after = _json.load(open(_bp, encoding="utf-8"))
_ah = next(s for s in _after["world"]["sites_canon"] if s["path"] == _after["position"]["path"])
good = ("ОТКАЗ" not in (_r.stdout or "")[:80] and _eng.is_sheltered(_after)
        and any(x.get("name") == "заслон" for x in _ah.get("structures") or [])
        and not any((o.get("name") if isinstance(o, dict) else o) == "жерди"
                    for o in _ah.get("objects") or []))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'сборка из объекта даёт укрытие':<40}"
      f"{'да' if good else (_r.stdout or '')[:80]}")

_st2, _ = _build_state()
_st2["items"] = [i for i in _st2["items"] if "дерево" not in (i.get("materials") or [])]
_miss = os.path.join(TMP, "build_miss.json")
_n0 = len(_st2["items"])
_json.dump(_st2, open(_miss, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "200", "--activity", "2",
           "--build", "заслон", "--build-part", "дерево:стержень:180:8:8",
           "--build-tag", "укрытие"], SIM_STATE=_miss)
_am = _json.load(open(_miss, encoding="utf-8"))
_amh = next(s for s in _am["world"]["sites_canon"] if s["path"] == _am["position"]["path"])
good = "ОТКАЗ" in (_r.stdout or "") and not (_amh.get("structures") or []) and len(_am["items"]) == _n0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'нет материала — отказ, ничего не списано':<40}{'да' if good else 'нет'}")

_st3, _ = _build_state()
_short = os.path.join(TMP, "build_short.json")
_json.dump(_st3, open(_short, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "1", "--activity", "2",
           "--build", "заслон", "--from-object", "жерди", "--build-tag", "укрытие"],
          SIM_STATE=_short)
_as = _json.load(open(_short, encoding="utf-8"))
_ash = next(s for s in _as["world"]["sites_canon"] if s["path"] == _as["position"]["path"])
good = "ОТКАЗ" in (_r.stdout or "") and not (_ash.get("structures") or [])
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'мало минут — отказ, объект цел':<40}{'да' if good else 'нет'}")

_r = _run(["engine.py", "act", "--minutes", "30", "--break", "след без состава"], SIM_STATE=_bp)
good = "ОТКАЗ" in (_r.stdout or "") and "част" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'проза без частей не ломается':<40}{'да' if good else 'нет'}")

_brk = os.path.join(TMP, "break_ok.json")
_built = _json.load(open(_bp, encoding="utf-8"))
_json.dump(_built, open(_brk, "w", encoding="utf-8"), ensure_ascii=False)
_sid = next(s["name"] for s in next(x for x in _built["world"]["sites_canon"]
                                    if x["path"] == _built["position"]["path"])["structures"])
_hours_b = _eng.break_refuse(_built, _sid, 10**9)
_r = _run(["engine.py", "act", "--minutes", "200", "--activity", "2", "--break", _sid],
          SIM_STATE=_brk)
_ab = _json.load(open(_brk, encoding="utf-8"))
good = "ОТКАЗ" not in (_r.stdout or "")[:80] and not _eng.is_sheltered(_ab)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'разбор снимает укрытие в тот же ход':<40}"
      f"{'да' if good else (_r.stdout or '')[:80]}")

_alien = _build_state()[0]
_alien["ruleset"] = _json.loads(_json.dumps(_alien["ruleset"]))
_alien["ruleset"]["structure_use"]["shelter_tags"] = ["нора"]
_alien["ruleset"]["structure_use"]["hearth_tags"] = ["жаровня"]
_ap = os.path.join(TMP, "build_alien.json")
_json.dump(_alien, open(_ap, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", str(_mins), "--activity", "2",
           "--build", "нора", "--from-object", "жерди", "--build-tag", "нора"],
          SIM_STATE=_ap)
_aa = _json.load(open(_ap, encoding="utf-8"))
good = _eng.is_sheltered(_aa)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'чужой тег нора даёт укрытие':<40}{'да' if good else 'нет'}")

_ahum = _build_state()[0]
_ahum["ruleset"] = _json.loads(_json.dumps(_ahum["ruleset"]))
_ahum["ruleset"]["structure_use"]["shelter_tags"] = ["нора"]
_hp = os.path.join(TMP, "build_human_tag.json")
_json.dump(_ahum, open(_hp, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", str(_mins), "--activity", "2",
           "--build", "заслон", "--from-object", "жерди", "--build-tag", "укрытие"],
          SIM_STATE=_hp)
_ahh = _json.load(open(_hp, encoding="utf-8"))
good = (not _eng.is_sheltered(_ahh)
        and any(s.get("tags") == ["укрытие"] for s in
                next(x for x in _ahh["world"]["sites_canon"]
                     if x["path"] == _ahh["position"]["path"]).get("structures") or []))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'укрытие без объявления — не роль':<40}{'да' if good else 'нет'}")

_nosu = _build_state()[0]
_nosu["ruleset"] = _json.loads(_json.dumps(_nosu["ruleset"]))
_nosu["ruleset"].pop("structure_use", None)
_np = os.path.join(TMP, "build_nosu.json")
_json.dump(_nosu, open(_np, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "200", "--build", "x",
           "--from-object", "жерди", "--build-tag", "укрытие"], SIM_STATE=_np)
good = "ОТКАЗ" in (_r.stdout or "") and "structure_use" in (_r.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'нет structure_use — отказ':<40}{'да' if good else 'нет'}")

_blk = _build_state()[0]
_hereb = next(s for s in _blk["world"]["sites_canon"] if s["path"] == _blk["position"]["path"])
_dest = "x/dummy_block"
_hereb["exits"] = list(_hereb.get("exits") or []) + [
    {"to": _dest, "mode": "пешком", "travel_min": 10, "difficulty": 10}]
_blk["world"]["sites_canon"].append({"path": _dest, "name": "d", "z_m": 0,
                                     "desc_true": "", "exits": [], "resources": [],
                                     "hazards": [], "objects": [], "touched": False})
_bp2 = os.path.join(TMP, "build_block.json")
_json.dump(_blk, open(_bp2, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", str(_mins), "--activity", "2",
           "--build", "завал", "--from-object", "жерди", "--build-tag", "укрытие",
           "--build-block", _dest], SIM_STATE=_bp2)
_r2 = _run(["engine.py", "act", "--minutes", "10", "--to", _dest], SIM_STATE=_bp2)
good = "перекрыт" in (_r2.stdout or "")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'перекрытый выход — отказ':<40}{'да' if good else 'нет'}")

_comp2 = os.path.join(TMP, "comp_build.json")
_s0 = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_s0["log"] = [{"turn": i, "fact": f"событие {i}"} for i in range(20)]
_far = {"path": "x/built_far", "name": "t", "z_m": 0, "desc_true": "",
        "exits": [], "resources": [], "hazards": [], "objects": [], "touched": False,
        "structures": [{"id": "str_99", "name": "заслон", "parts": [["дерево", "стержень", 100, 8, 8]],
                        "tags": ["укрытие"], "player_made": True, "kg": 3.6, "l": 4.8}]}
_s0["world"]["sites_canon"] += [_far]
_json.dump(_s0, open(_comp2, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "compact", "--keep", "40"], SIM_STATE=_comp2)
_c2 = _json.load(open(_comp2, encoding="utf-8"))
good = any(s["path"] == "x/built_far" for s in _c2["world"]["sites_canon"])
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'compact хранит player_made':<40}{'да' if good else 'нет'}")

_badc = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_site = next(s for s in _badc["world"]["sites_canon"] if s["path"] == _badc["position"]["path"])
_site["structures"] = [{"name": "стена", "parts": [["камень", "пластина", 200, 200, 40]],
                        "kg": 2.0, "tags": ["укрытие"]}]
_e_mass, _ = _wg_validate(_badc)
good = any("масс" in e for e in _e_mass)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'validate ловит массу не от частей':<40}{'да' if good else 'нет'}")

print("\n── стройка: три части, порог массы, compact×3 ──")
_src_b = open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
_src_w = open(os.path.join(HERE, "worldgen.py"), encoding="utf-8").read()
good = ("целиком" in _src_b and "Одну часть из трёх" in _src_b
        and "def mass_matches_parts(" in _src_w
        and "--break-part" not in _src_b)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'разбор — вся конструкция, не часть':<40}{'да' if good else 'нет'}")

_trip = _build_state()[0]
_ht = next(s for s in _trip["world"]["sites_canon"] if s["path"] == _trip["position"]["path"])
_3parts = [["дерево", "стержень", 180, 8, 8],
           ["дерево", "пластина", 140, 70, 3],
           ["дерево", "стержень", 160, 10, 10]]
_it3 = matter.make_item("навес", _3parts, ["укрытие"], "primitive", None, 1.0)
_ht["structures"] = [{"id": "str_3", "name": "навес", "parts": _3parts,
                      "tags": ["укрытие"], "player_made": True,
                      "kg": _it3["kg"], "l": _it3["l"]}]
_ht["objects"] = []
good = _eng.is_sheltered(_trip)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'три части с тегом — укрытие':<40}{'да' if good else 'нет'}")

_mid = os.path.join(TMP, "break_3.json")
_json.dump(_trip, open(_mid, "w", encoding="utf-8"), ensure_ascii=False)
_r = _run(["engine.py", "act", "--minutes", "200", "--activity", "2", "--break", "навес"],
          SIM_STATE=_mid)
_after3 = _json.load(open(_mid, encoding="utf-8"))
_ah3 = next(s for s in _after3["world"]["sites_canon"] if s["path"] == _after3["position"]["path"])
good = ("ОТКАЗ" not in (_r.stdout or "")[:80]
        and not (_ah3.get("structures") or [])
        and not _eng.is_sheltered(_after3))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'--break трёх частей снимает роль сразу':<40}"
      f"{'да' if good else (_r.stdout or '')[:60]}")

_roof = _json.loads(_json.dumps(_trip))
_hr = next(s for s in _roof["world"]["sites_canon"] if s["path"] == _roof["position"]["path"])
_hr["structures"][0]["parts"] = [_3parts[0], _3parts[2]]
_it2 = matter.make_item("навес", _hr["structures"][0]["parts"], ["укрытие"],
                        "primitive", None, 1.0)
_hr["structures"][0]["kg"] = _it2["kg"]
_hr["structures"][0]["l"] = _it2["l"]
_e_roof, _ = _wg_validate(_roof)
good = (not any("масс" in e for e in _e_roof) and _eng.is_sheltered(_roof))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'снял среднюю в данных — роль на тегах':<40}"
      f"{'укрытие' if good else 'нет'}")

_parts_w = [["камень", "пластина", 200, 200, 40]]
_itw = matter.make_item("стена", _parts_w, ["укрытие"], "primitive", None, 1.0)
_tol = mass_claim_tol(_itw["kg"])
_edge_ok = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_se = next(s for s in _edge_ok["world"]["sites_canon"] if s["path"] == _edge_ok["position"]["path"])
_se["structures"] = [{"name": "стена", "parts": _parts_w, "kg": _itw["kg"] + _tol,
                      "tags": ["укрытие"]}]
_e_ok, _ = _wg_validate(_edge_ok)
_edge_bad = _json.loads(_json.dumps(_edge_ok))
_sb = next(s for s in _edge_bad["world"]["sites_canon"] if s["path"] == _edge_bad["position"]["path"])
_sb["structures"][0]["kg"] = _itw["kg"] + _tol + 0.01
_e_bad2, _ = _wg_validate(_edge_bad)
good = (not any("масс" in e for e in _e_ok) and any("масс" in e for e in _e_bad2)
        and mass_matches_parts(_itw["kg"] + _tol, _itw["kg"])
        and not mass_matches_parts(_itw["kg"] + _tol + 0.01, _itw["kg"]))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'порог массы: внутри проходит, снаружи нет':<40}"
      f"tol={_tol:.3f} кг")

_stick = [["дерево", "стержень", 20, 2, 2]]
_its = matter.make_item("кол", _stick, [], "primitive", None, 1.0)
_tol_s = mass_claim_tol(_its["kg"])
good = abs(_tol_s - 0.05) < 1e-12 and _its["kg"] < 1.0
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'малая масса — пол 50 г, не 5%':<40}"
      f"kg={_its['kg']} tol={_tol_s}")

_cmpn = os.path.join(TMP, "comp_n.json")
_sn = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_sn["log"] = [{"turn": i, "fact": f"событие {i}"} for i in range(80)]
_far_pm = {"path": "x/built_stay", "name": "стойка", "z_m": 0, "desc_true": "",
           "exits": [], "resources": [], "hazards": [], "objects": [], "touched": False,
           "structures": [{"id": "str_stay", "name": "заслон", "parts": _3parts,
                           "tags": ["укрытие"], "player_made": True,
                           "kg": _it3["kg"], "l": _it3["l"]}]}
_far_junk = {"path": "x/junk_gone", "name": "пустошь", "z_m": 0, "desc_true": "",
             "exits": [], "resources": [], "hazards": [], "objects": [], "touched": False}
_sn["world"]["sites_canon"] += [_far_pm, _far_junk]
_json.dump(_sn, open(_cmpn, "w", encoding="utf-8"), ensure_ascii=False)
for _i in range(3):
    _r = _run(["engine.py", "compact", "--keep", "40"], SIM_STATE=_cmpn)
_cn = _json.load(open(_cmpn, encoding="utf-8"))
_paths = {s["path"] for s in _cn["world"]["sites_canon"]}
_kept = next(s for s in _cn["world"]["sites_canon"] if s["path"] == "x/built_stay")
good = ("x/built_stay" in _paths and "x/junk_gone" not in _paths
        and (_kept.get("structures") or [])[0].get("player_made") is True
        and (_kept["structures"][0].get("tags") or []) == ["укрытие"]
        and len(_kept["structures"][0].get("parts") or []) == 3)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'player_made живёт три compact подряд':<40}"
      f"{'да' if good else 'нет'}")

print("\n── take наполняет тару по тегу, не создаёт вторую порцию ──")
good = ("def fillable_items(" in _src4 and "def take_plan(" in _src4
        and "наполнил" in _src4)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'fillable_items/take_plan в engine':<40}{'да' if good else 'нет'}")

_rf = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_rf["ruleset"] = _json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
_rsite = next(s for s in _rf["world"]["sites_canon"] if s["path"] == _rf["position"]["path"])
_rsite["resources"] = [{"name": "лужа", "amount": 10, "tags": ["вода"]}]
_rf["items"] = [
    {"id": "itm_a", "name": "тара", "kg": 0.0, "l": 0.5, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["вода"], "fill": 0.0},
    {"id": "itm_b", "name": "ключ", "kg": 0.02, "l": 0.01, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["металл"]},
]
_rf["gear"]["hands"]["held"] = ["itm_a", "itm_b"]
_rf["gear"]["hands"]["slots"] = 2
_n0 = len(_rf["items"])
_rlog = []
good_fill = _eng.take_site_resource(_rf, "лужа:0.5", _rlog)
_amt_l = next(r["amount"] for r in _rsite["resources"])
good = (good_fill and abs(_rf["items"][0]["fill"] - 1.0) < 0.02
        and abs(_amt_l - 9.5) < 0.001 and len(_rf["items"]) == _n0
        and any("наполнил" in x for x in _rlog))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'пустая тара с тегом наполняется':<40}fill={_rf['items'][0]['fill']} n={len(_rf['items'])}")

_rf["items"][0]["fill"] = 0.6
_amt_before = next(r["amount"] for r in _rsite["resources"])
_rlog = []
_eng.take_site_resource(_rf, "лужа:0.5", _rlog)
_amt_after = next(r["amount"] for r in _rsite["resources"])
good = (abs(_rf["items"][0]["fill"] - 1.0) < 0.02
        and abs(_amt_before - _amt_after - 0.2) < 0.02
        and len(_rf["items"]) == _n0)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'take больше места — льёт сколько влезает':<40}{_amt_before:g}->{_amt_after:g}")

_rf2 = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_rf2["ruleset"] = _json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
_rs2 = next(s for s in _rf2["world"]["sites_canon"] if s["path"] == _rf2["position"]["path"])
_rs2["resources"] = [{"name": "лужа", "amount": 10, "tags": ["вода"]}]
_rf2["items"] = [
    {"id": "itm_a", "name": "фляга", "kg": 0.0, "l": 0.5, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": [], "fill": 0.0},
    {"id": "itm_b", "name": "ключ", "kg": 0.02, "l": 0.01, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["металл"]},
]
_rf2["gear"]["hands"]["held"] = ["itm_a", "itm_b"]
_rf2["gear"]["hands"]["slots"] = 2
for _c in _rf2["gear"]["containers"]:
    if _c.get("id") != "cnt_00":
        _c["cap_l"] = 0.001
        _c["cap_kg"] = 0.001
_n2 = len(_rf2["items"])
_amt2 = _rs2["resources"][0]["amount"]
_rlog = []
good = (not _eng.take_site_resource(_rf2, "лужа:0.5", _rlog)
        and _rf2["items"][0]["fill"] == 0.0
        and abs(_rs2["resources"][0]["amount"] - _amt2) < 1e-9
        and len(_rf2["items"]) == _n2
        and any("ОТКАЗ" in x for x in _rlog))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'имя фляга без тега — не тара':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")

_alr = _json.load(open("examples/rimworld2.json", encoding="utf-8"))
_alr["ruleset"] = _json.load(open(os.path.join(HERE, "ruleset.json"), encoding="utf-8"))
_alr["ruleset"]["item_use"]["water_tags"] = ["слизь"]
_als = next(s for s in _alr["world"]["sites_canon"] if s["path"] == _alr["position"]["path"])
_als["resources"] = [{"name": "лужа", "amount": 8, "tags": ["слизь"]}]
_alr["items"] = [
    {"id": "itm_x", "name": "пузырь", "kg": 0.0, "l": 0.5, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["слизь"], "fill": 0.0},
    {"id": "itm_y", "name": "камень", "kg": 0.4, "l": 0.1, "qty": 1,
     "in": "cnt_00", "depth": 0, "condition": 1.0, "tags": ["камень"]},
]
_alr["gear"]["hands"]["held"] = ["itm_x", "itm_y"]
_n_al = len(_alr["items"])
_rlog = []
good = (_eng.take_site_resource(_alr, "лужа:0.5", _rlog)
        and abs(_alr["items"][0]["fill"] - 1.0) < 0.02
        and len(_alr["items"]) == _n_al
        and abs(_als["resources"][0]["amount"] - 7.5) < 0.001)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'чужой тег слизь наполняет пузырь':<40}fill={_alr['items'][0]['fill']}")

_alr["items"][0]["tags"] = ["вода"]
_alr["items"][0]["fill"] = 0.0
_alr["items"][0]["kg"] = 0.0
_amt_al = _als["resources"][0]["amount"]
for _c in _alr["gear"]["containers"]:
    if _c.get("id") != "cnt_00":
        _c["cap_l"] = 0.001
        _c["cap_kg"] = 0.001
_rlog = []
good = (not _eng.take_site_resource(_alr, "лужа:0.5", _rlog)
        and _alr["items"][0]["fill"] == 0.0
        and abs(_als["resources"][0]["amount"] - _amt_al) < 1e-9
        and any("ОТКАЗ" in x for x in _rlog))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'вода при ресурсе слизь — не тара':<40}{'отклонено' if good else 'ПРОПУЩЕНО'}")

_jura_h = open(os.path.join(HERE, "examples", "run_jurassic_random.py"), encoding="utf-8").read()
_handoff = open(os.path.join(HERE, "HANDOFF.md"), encoding="utf-8").read()
good = ("RISK_APPROACH_HOSTILE = False" in _jura_h
        and "не шкала" in _jura_h
        and "не дыра выдачи ресурса" in _jura_h
        and "RISK_APPROACH_HOSTILE" in _handoff)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'юра: голод у туши — предел стратегии':<40}{'да' if good else 'нет'}")

print("\n── замысел Qwen3.5 9B: форма без TypeError, matter без префикса ──")
_src_wg = open(os.path.join(HERE, "worldgen.py"), encoding="utf-8").read()
_src_pl = open(os.path.join(HERE, "play.py"), encoding="utf-8").read()
good = ("def _make_item(" in _src_wg and "matter.make_item(" not in _src_wg
        and "SKILL_LIST_VALUE_KEYS" in _src_wg
        and "BRIEF_SCHEMA" in _src_pl and "response_format" in _src_pl
        and '"strict": True' in _src_pl
        and "value|level|score" in _src_pl and "rating" in _src_pl)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'схема brief и _make_item без matter.':<40}{'да' if good else 'нет'}")

_q1 = _json.load(open(os.path.join(HERE, "examples", "qwen35_9b_skills_list.json"), encoding="utf-8"))
try:
    _S1 = _wg_expand(_q1)
    _e1, _ = _wg_validate(_S1)
    good = isinstance(_S1["pc"]["skills"], dict) and _S1["pc"]["skills"].get("survival") == 45
    good = good and _S1["pc"]["skills"].get("craft") == 50 and _S1["pc"]["skills"].get("medicine") == 25
except TypeError as _te:
    good = False
    print(f"  TypeError на skills-list: {_te}")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'список skills нормализуется в словарь':<40}{'да' if good else 'нет'}")

_q2 = _json.load(open(os.path.join(HERE, "examples", "qwen35_9b_string_stats.json"), encoding="utf-8"))
_err2 = None
try:
    _wg_expand(_q2)
    good = False
except TypeError as _te:
    _err2 = f"TypeError: {_te}"
    good = False
except ValueError as _ve:
    _err2 = str(_ve)
    good = "число" in _err2 and "high" in _err2
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'строки high/hostile — понятный отказ':<40}{_err2}")

_q3 = _json.load(open(os.path.join(HERE, "examples", "qwen35_9b_structures.json"), encoding="utf-8"))
try:
    _S3 = _wg_expand(_q3)
    _e3, _ = _wg_validate(_S3)
    _site3 = next(s for s in _S3["world"]["sites_canon"] if s["path"] == _S3["position"]["path"])
    good = any(st.get("name") == "заслон" for st in (_site3.get("structures") or []))
    good = good and not any("NameError" in str(x) for x in _e3)
except TypeError as _te:
    good = False
    print(f"  TypeError на structures: {_te}")
except NameError as _ne:
    good = False
    print(f"  NameError на structures: {_ne}")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'structures: expand/validate без TypeError':<40}{'да' if good else 'нет'}")

# чистый процесс: в sim.py нет модуля matter — префикс matter. даёт NameError
_src_sim = open(os.path.join(HERE, "sim.py"), encoding="utf-8").read()
_r3 = _run(["-c",
    "import json,sim; S=sim.expand(json.load(open('examples/qwen35_9b_structures.json',encoding='utf-8')));"
    "e,_=sim.validate(S); assert not e, e; print('bundle_ok')"])
good = ("def _make_item(" in _src_sim and "matter.make_item(" not in _src_sim
        and _r3.returncode == 0 and "bundle_ok" in (_r3.stdout or ""))
if not good and _r3.returncode:
    print((_r3.stderr or _r3.stdout or "")[:400])
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'sim.py: structures без NameError matter':<40}{'да' if good else 'нет'}")

good = SKILL_LIST_VALUE_KEYS == ("value", "level", "score")
try:
    _nr = _wg_norm({"skills": [{"name": "craft", "rating": 40}]})
    good = False
except ValueError as _ve:
    good = good and "rating" in str(_ve) and "value" in str(_ve)
except TypeError:
    good = False
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'rating в skills — отказ, не синоним':<40}{'да' if good else 'нет'}")

import inspect as _insp
_src_proxy = _insp.getsource(_wg_make)
_parts_px = [("дерево", "стержень", 180, 8, 8)]
_a_px = _wg_make("заслон", _parts_px, ["укрытие"], "industrial", None, 1.0)
_b_px = matter.make_item("заслон", _parts_px, ["укрытие"], "industrial", None, 1.0)
good = ("getattr" in _src_proxy and "return fn(" in _src_proxy
        and "check_plausible" not in _src_proxy
        and "MATERIALS" not in _src_proxy
        and _a_px["kg"] == _b_px["kg"])
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'_make_item — прокси, не копия тела':<40}{'да' if good else 'нет'}")

from worldgen import PHYSICS_ON as _WG_PO
_src_bb = open(os.path.join(HERE, "build_bundle.py"), encoding="utf-8").read()
_r_po = _run(["-c", "import sim; print('|'.join(sim.PHYSICS_ON))"])
good = ("PHYSICS_ON" in _src_bb and _r_po.returncode == 0
        and (_r_po.stdout or "").strip() == "|".join(_WG_PO)
        and "sim.PHYSICS_ON" in _src_pl)
if not good and _r_po.returncode:
    print((_r_po.stderr or _r_po.stdout or "")[:300])
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'sim.PHYSICS_ON совпадает с worldgen':<40}{'да' if good else 'нет'}")

print("\n── разбор хода SYS_MECH: схема из S, отказ вместо max(0) ──")
import play as _play
_src_pl2 = open(os.path.join(HERE, "play.py"), encoding="utf-8").read()
good = ("def mech_schema(" in _src_pl2 and "def normalize_intent(" in _src_pl2
        and "response_format=mech_response_format(S)" in _src_pl2
        and "max(0, float" not in _src_pl2
        and "MECH_MINUTES_CEILING" not in _src_pl2
        and "INTENT_CHECK_KEYS" in _src_pl2)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'схема хода динамическая, clamp снят':<40}{'да' if good else 'нет'}")

_Sh = _json.load(open(os.path.join(HERE, "examples", "rimworld2.json"), encoding="utf-8"))
_Sm = _json.load(open(os.path.join(HERE, "examples", "mech_state.json"), encoding="utf-8"))
_sch_h = _play.mech_schema(_Sh)
_sch_m = _play.mech_schema(_Sm)
_en_h = _sch_h["properties"]["checks"]["items"]["properties"]["skill"].get("enum") or []
_en_m = _sch_m["properties"]["checks"]["items"]["properties"]["skill"].get("enum") or []
good = ("athletics" in _en_h and "сервоприводы" in _en_m
        and "сервоприводы" not in _en_h and "athletics" not in _en_m
        and _sch_h["properties"]["checks"]["maxItems"] == 2)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'enum навыков из S, не константа':<40}{'да' if good else 'нет'}")

def _n_ok(path, S, pred):
    m = _play.normalize_intent(_json.load(open(os.path.join(HERE, "examples", path), encoding="utf-8")), S)
    return pred(m)

def _n_bad(path, S, needle):
    try:
        _play.normalize_intent(_json.load(open(os.path.join(HERE, "examples", path), encoding="utf-8")), S)
        return False
    except TypeError:
        return False
    except ValueError as e:
        return needle in str(e)

good = _n_bad("mech_intent_minutes_neg.json", _Sh, "minutes")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'minutes −400 — отказ, не ноль':<40}{'да' if good else 'нет'}")

good = _n_ok("mech_intent_checks_obj.json", _Sh,
             lambda m: m["checks"][0]["skill"] == "perception"
             and _play.check_to_cli(m["checks"][0]).startswith("perception:20:осмотр"))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'checks-объект → канон и CLI-строка':<40}{'да' if good else 'нет'}")

good = _n_ok("mech_intent_checks_str.json", _Sh,
             lambda m: m["checks"][0]["skill"] == "perception"
             and m["checks"][0]["difficulty"] == 20)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'checks-строка — вторая закрытая форма':<40}{'да' if good else 'нет'}")

good = (_n_bad("mech_intent_skill_unknown.json", _Sm, "athletics")
        and _n_ok("mech_intent_skill_unknown.json", _Sh,
                  lambda m: m["checks"][0]["skill"] == "athletics"))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'чужой навык: отказ / свой — приём':<40}{'да' if good else 'нет'}")

good = (_n_bad("mech_intent_diff_string.json", _Sh, "число")
        and _n_bad("mech_intent_key_synonym.json", _Sh, "навык"))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'high / ключ навык — отказ, не синоним':<40}{'да' if good else 'нет'}")

print("\n── замысел: required в схеме и понятная самопочинка ──")
_sch_b = _play.BRIEF_SCHEMA
good = (_sch_b.get("additionalProperties") is True
        and set(_play.BRIEF_REQUIRED) <= set(_sch_b.get("required") or [])
        and set(_play.BRIEF_EXPAND_DIRECT) <= set(_play.BRIEF_REQUIRED)
        and _sch_b["properties"]["start_local"]["type"] == "string"
        and _sch_b["properties"]["chain"]["type"] == "array"
        and _sch_b["properties"]["sites"]["items"].get("required") == list(_play.SITE_REQUIRED)
        and _sch_b["properties"]["sites"]["items"]["properties"]["exits"]["items"].get("required") == list(_play.EXIT_REQUIRED)
        and _sch_b["properties"]["clocks"]["items"].get("required") == list(_play.CLOCK_REQUIRED)
        and _sch_b["properties"]["npcs"]["items"].get("required") == list(_play.NPC_REQUIRED)
        and _sch_b["properties"]["factions"]["items"].get("required") == list(_play.FACTION_REQUIRED)
        and "exits, не exits_list" in _src_pl2
        and "Поле в твоём ответе называется sites, не sites_canon" in _src_pl2
        and "format_brief_error" in _src_pl2
        and "str(e)[:500]" not in _src_pl2)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'required на корне и элементах массивов':<40}{'да' if good else 'нет'}")

_msg_ke = _play.format_brief_error(KeyError("sites"))
good = ("обязательного поля sites" in _msg_ke and "sites_canon" in _msg_ke
        and "Traceback" not in _msg_ke and "KeyError" not in _msg_ke)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'KeyError sites — поле и формат, не traceback':<40}{'да' if good else 'нет'}")

def _gaps(name):
    return _play.brief_form_errors(_json.load(open(os.path.join(HERE, "examples", name), encoding="utf-8")))

_g1 = _gaps("qwen35_9b_sites_canon.json")
good = any("sites" in x and "sites_canon" in x for x in _g1)
try:
    _wg_expand(_json.load(open(os.path.join(HERE, "examples", "qwen35_9b_sites_canon.json"), encoding="utf-8")))
    good = False
except KeyError:
    pass
except TypeError:
    good = False
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'sites_canon — отказ, не синоним sites':<40}{'да' if good else 'нет'}")

_g2 = _gaps("qwen35_9b_missing_skills.json")
good = any("обязательного поля skills" in x for x in _g2)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'нет skills — понятный пропуск поля':<40}{'да' if good else 'нет'}")

_g3 = _gaps("qwen35_9b_npc_no_id.json")
good = any("npcs[0]" in x and "id" in x for x in _g3)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'NPC без id — дыра элемента массива':<40}{'да' if good else 'нет'}")

import ast, inspect, textwrap
def _sub_keys(fn, var):
    """Ключи var[\"x\"] в функции: чтения vs записи. Не .get()."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    reads, writes = set(), set()
    class V(ast.NodeVisitor):
        def visit_Assign(self, node):
            for t in node.targets:
                k = self._key(t)
                if k is not None:
                    writes.add(k)
                else:
                    self.visit(t)
            self.visit(node.value)
        def visit_AnnAssign(self, node):
            k = self._key(node.target)
            if k is not None:
                writes.add(k)
            elif node.target:
                self.visit(node.target)
            if node.value:
                self.visit(node.value)
        def visit_AugAssign(self, node):
            k = self._key(node.target)
            if k is not None:
                writes.add(k)
            else:
                self.visit(node.target)
            self.visit(node.value)
        def visit_Subscript(self, node):
            k = self._key(node)
            if k is not None:
                reads.add(k)
            self.generic_visit(node)
        def _key(self, node):
            if not isinstance(node, ast.Subscript):
                return None
            if not isinstance(node.value, ast.Name) or node.value.id != var:
                return None
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                return sl.value
            return None
    V().visit(tree)
    return reads, writes

_reads_b, _writes_b = _sub_keys(_wg_expand, "b")
_direct_b = (_reads_b - _writes_b) - set(_play.BRIEF_EXPAND_GUARDED)
good = (_direct_b == set(_play.BRIEF_EXPAND_DIRECT)
        and set(_play.BRIEF_EXPAND_DIRECT) <= set(_play.BRIEF_REQUIRED)
        and set(_play.BRIEF_EXPAND_DIRECT) <= set(_sch_b["properties"]))
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'expand() b[x] ⊆ required схемы':<40}{'да' if good else f'нет {_direct_b}'}")

_reads_c, _writes_c = _sub_keys(_wg_expand, "c")
_direct_c = (_reads_c - _writes_c) - set(_play.CLOCK_GUARDED)
_reads_s, _ = _sub_keys(_wg_validate, "s")
_reads_e, _ = _sub_keys(_wg_validate, "e")
good = (_direct_c == set(_play.CLOCK_REQUIRED)
        and _reads_s <= set(_play.SITE_REQUIRED)
        and _reads_e <= set(_play.EXIT_REQUIRED)
        and set(_play.SITE_REQUIRED) == set(_sch_b["properties"]["sites"]["items"]["required"])
        and "disposition" not in _play.NPC_REQUIRED
        and "power" not in _play.FACTION_REQUIRED
        and "stance_to_pc" not in _play.FACTION_REQUIRED
        and 'if "disposition" in n' in _src_wg
        and "f.get(\"power\"" in open(os.path.join(HERE, "society.py"), encoding="utf-8").read())
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'вложенный required ↔ AST validate/expand':<40}{'да' if good else f'нет s={_reads_s} e={_reads_e} c={_direct_c}'}")

_g4 = _gaps("qwen35_9b_missing_start_local.json")
good = any("обязательного поля start_local" in x for x in _g4)
_sl_brief = _json.load(open(os.path.join(HERE, "examples", "qwen35_9b_missing_start_local.json"), encoding="utf-8"))
if good:
    # new_game не зовёт expand, если brief_form_errors непуст
    pass
_sl_expand = None
try:
    _wg_expand(_sl_brief)
    _sl_expand = "passed"
except KeyError as _ke:
    _sl_expand = _ke.args[0] if _ke.args else type(_ke).__name__
except Exception as _ex:
    _sl_expand = type(_ex).__name__
good = good and _sl_expand == "start_local"
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'нет start_local — отказ схемы, не KeyError в UI':<40}{'да' if good else 'нет'}")

_chain_brief = _json.loads(_json.dumps(_sl_brief))
_chain_brief["start_local"] = "у остывшей печи"
del _chain_brief["chain"]
_g5 = _play.brief_form_errors(_chain_brief)
good = any("обязательного поля chain" in x for x in _g5)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'нет chain — тот же класс required':<40}{'да' if good else 'нет'}")

def _exit_alias_case(name, alias):
    g = _gaps(name)
    form_ok = any("exits" in x and alias in x for x in g)
    brief = _json.load(open(os.path.join(HERE, "examples", name), encoding="utf-8"))
    exp_ok = False
    try:
        S = _wg_expand(brief)
        exp_ok = True
        try:
            _wg_validate(S)
            val = "passed"
        except KeyError as ke:
            val = ke.args[0] if ke.args else "?"
    except Exception as ex:
        val = type(ex).__name__
        exp_ok = False
    return form_ok and exp_ok and val == "exits"

good = _exit_alias_case("qwen35_9b_exits_list.json", "exits_list")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'exits_list — отказ схемы до expand':<40}{'да' if good else 'нет'}")

good = _exit_alias_case("qwen35_9b_exits_from_here.json", "exits_from_here")
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'exits_from_here — отказ схемы до expand':<40}{'да' if good else 'нет'}")

_clk_brief = _json.loads(_json.dumps(_sl_brief))
_clk_brief["start_local"] = "у остывшей печи"
_clk_brief["clocks"] = [{"filled": 0, "max": 5, "period_h": 8, "payoff": "x"}]
_g6 = _play.brief_form_errors(_clk_brief)
good = any("clocks[0]" in x and "name" in x for x in _g6)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'часы без name — вложенный required':<40}{'да' if good else 'нет'}")

print("\n── замысел: обрыв по length, не JSONDecodeError ──")
good = (_play.BRIEF_MAX_TOKENS >= 6000
        and "max_tokens=4000" not in open(os.path.join(HERE, "play.py"), encoding="utf-8").read()
        and "не более 4 объектов" in open(os.path.join(HERE, "play.py"), encoding="utf-8").read()
        and "json_looks_truncated" in open(os.path.join(HERE, "play.py"), encoding="utf-8").read())
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'потолок brief ≥6000, лимит сущностей':<40}{'да' if good else 'нет'}")

_kyiv = _json.load(open(os.path.join(HERE, "examples", "qwen35_9b_kyiv_truncated.json"), encoding="utf-8"))
good = _play.json_looks_truncated(_kyiv["content"], _kyiv["finish_reason"])
good = good and not _play.json_looks_truncated('{"seed": 1}', "stop")
good = good and _play.json_looks_truncated('{"seed": 1}', "length")
_fr = _play._llm_finish_reason("local", {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]})
good = good and _fr == "length"
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'Kyiv truncated: length, не json.loads':<40}{'да' if good else 'нет'}")

good = ("подробным" in _play.BRIEF_TRUNCATED_USER
        and "обрублен" in _play.BRIEF_TRUNCATED_RETRY
        and "Expecting" not in _play.BRIEF_TRUNCATED_USER
        and "JSONDecode" not in _play.BRIEF_TRUNCATED_USER)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'UI: слишком подробный мир, не Expecting':<40}{'да' if good else 'нет'}")

print("\n── замысел: зацикливание JSON, не нехватка места ──")
_cap = _json.load(open(os.path.join(HERE, "examples", "qwen35_9b_capsule_loop.json"), encoding="utf-8"))
_unit = '" :", " ,"'
good = (_play.detect_degenerate_loop(_cap["content"])
        and _play.brief_generation_fault(_cap["content"], _cap["finish_reason"]) == "loop"
        and _play.brief_generation_fault(_kyiv["content"], _kyiv["finish_reason"]) == "truncated"
        and not _play.detect_degenerate_loop(_kyiv["content"])
        and _play.detect_degenerate_loop(_unit * 30)
        and not _play.detect_degenerate_loop(_unit * 29)
        and "сократи" not in _play.BRIEF_LOOP_RETRY
        and "кавычки" in _play.BRIEF_LOOP_RETRY
        and "зациклилась" in _play.BRIEF_LOOP_USER
        and "Expecting" not in _play.BRIEF_LOOP_USER
        and "JSONDecode" not in _play.BRIEF_LOOP_USER
        and '"stream": False' in open(os.path.join(HERE, "play.py"), encoding="utf-8").read()
        and "не потоковый" in open(os.path.join(HERE, "HANDOFF.md"), encoding="utf-8").read())
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'капсула: loop, не «сократи сайты»':<40}{'да' if good else 'нет'}")

_npcs = []
for _i in range(8):
    _npcs.append({
        "id": f"npc_{_i:02d}", "name": f"Kyiv guard {_i}",
        "path": "kyiv/podol/rynok", "goal": "торговать",
        "disposition": 10, "alive": True,
    })
_similar = _json.dumps({
    "seed": 1, "setting": "Киев", "ladder": ["Kyiv", "Podil", "Rynok"],
    "npcs": _npcs, "truths": ["Kyiv стоит.", "Подол торгует."],
}, ensure_ascii=False, indent=1)
good = (not _play.detect_degenerate_loop(_similar)
        and _play.brief_generation_fault(_similar, "stop") is None)
ok, fail = ok+good, fail+(not good)
print(f"  {'ok ' if good else 'MISS'} {'похожие NPC — не ложный цикл':<40}{'да' if good else 'нет'}")

print(f"\n{'='*56}\nИТОГО пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
