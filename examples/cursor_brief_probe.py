#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Замыслы, написанные вручную знанием схемы — не live-вызов модели.

Не сравнивать с Qwen: это эталон «мир принимается», не прогон SYS_BRIEF.
Запуск: python examples/cursor_brief_probe.py
"""
import json, os, sys, traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import play

# Те же вводные, что examples/live_brief_probe.py. JSON пишет эта модель, не Qwen.


def _npc(i, name, path, goal, long_goal, faction, disp, sched, res):
    return {
        "id": f"npc_{i:02d}", "name": name, "path": path,
        "goal": goal, "long_goal": long_goal, "resources": res,
        "disposition": disp, "knows_about_pc": [], "alive": True,
        "schedule": sched, "faction": faction,
    }


def _fac(i, name, goal, power, stance):
    return {
        "id": f"fac_{i:02d}", "name": name, "goal": goal,
        "power": power, "stance_to_pc": stance, "relations": {},
    }


WW1 = "ww1/front/les/okop"
WW1_NOM = "ww1/front/les/noman"
WW1_TYL = "ww1/front/les/balka"

KYIV = "rus/dnepr/kiev/pechery"
KYIV_DVOR = "rus/dnepr/kiev/dvor"
KYIV_YAR = "rus/dnepr/kiev/yar"

SOCHI = "sochi/port/prichal"
SOCHI_UL = "sochi/port/ulitsa"
SOCHI_BOL = "sochi/port/boloto"

CAP = "descent/capsule/cabin"
CAP_HAT = "descent/capsule/hatch"
CAP_YAR = "descent/ground/yar"

SHIP = "drifter/hull/bridge"
SHIP_COR = "drifter/hull/corridor"
SHIP_LOCK = "drifter/hull/airlock"

BRIEFS = {
    "ww1_forest": {
        "seed": 20260908,
        "setting": "Арденны, ноябрь 1916: из прогулки по лесу — в окоп под артобстрелом.",
        "tech_ceiling": "industrial",
        "ladder": ["театр", "фронт", "участок", "укрытие"],
        "ladder_root": "ww1",
        "physics_on": ["холод", "голод", "жажда", "сон", "раны", "болезни", "нагрузка", "погода"],
        "start_path": WW1,
        "start_local": "на мокрой ступени окопа, над головой доски",
        "start_z": 180,
        "start_hour": 5.2,
        "weather": "мокрый снег",
        "ambient_c": 1,
        "wind_ms": 7,
        "climate": {"t_min": -4, "t_max": 6, "sunrise": 7.8, "sunset": 16.4, "note": "ноябрь"},
        "epoch": "ноябрь 1916",
        "start_date": "1916-11-12",
        "seasons": ["осень"],
        "needs": {"hunger": 35, "thirst": 40, "fatigue": 55, "cold_stress": 42, "stress": 70},
        "skills": {"survival": 38, "stealth": 40, "perception": 44, "medicine": 18, "combat": 22},
        "conditions": [],
        "carryover": {"context": "auto"},
        "chain": [
            {"path": "ww1", "scale": "театр", "laws": "обычная физика", "canon": "Западный фронт."},
            {"path": "ww1/front", "scale": "фронт", "laws": "обычная физика", "canon": "Позиционная война."},
        ],
        "sites": [
            {
                "path": WW1, "name": "Окоп у кромки леса", "z_m": 180,
                "desc_true": "Узкий ход сообщения, вода по щиколотку, запах хлора и глины.",
                "exits": [
                    {"to": WW1_NOM, "mode": "пешком", "travel_min": 8, "dz_m": 4, "difficulty": 55, "gate": "проволока"},
                    {"to": WW1_TYL, "mode": "пешком", "travel_min": 18, "dz_m": -12, "difficulty": 30, "gate": ""},
                ],
                "resources": [
                    {"name": "кипяток в котелке", "amount": 2, "tags": ["вода"]},
                    {"name": "сухари", "amount": 3, "tags": ["еда"]},
                    {"name": "щепки от накатника", "amount": 4, "tags": ["топливо"]},
                ],
                "hazards": ["сырость", "крысы"],
                "objects": [
                    {"name": "накатник", "parts": [["дерево", "стержень", 200, 12, 12], ["дерево", "пластина", 160, 30, 4]]},
                    "лужа с радужной плёнкой",
                ],
                "structures": [
                    {"name": "бруствер", "parts": [["глина", "пластина", 220, 80, 90], ["дерево", "стержень", 180, 10, 10]], "tags": ["укрытие"]},
                ],
                "shelter": True, "hearth": False, "touched": True,
                "env": {"ambient_c": 2, "wind_ms": 2},
            },
            {
                "path": WW1_NOM, "name": "Ничья земля", "z_m": 184,
                "desc_true": "Воронки, обрывки проволоки. Без хода по воронкам — на прицеле.",
                "exits": [
                    {"to": WW1, "mode": "пешком", "travel_min": 8, "dz_m": -4, "difficulty": 55, "gate": "проволока"},
                ],
                "resources": [],
                "hazards": ["снайпер", "осколки"],
                "objects": [
                    {"name": "проволочный забор", "parts": [["сталь", "сеть", 400, 80, 3]]},
                ],
                "structures": [],
                "shelter": False, "touched": True,
                "env": {"ambient_c": -1, "wind_ms": 11},
            },
            {
                "path": WW1_TYL, "name": "Балка за второй линией", "z_m": 168,
                "desc_true": "Глиняный ход к кухне. Дальше — батарея, её нет в стартовом каноне.",
                "exits": [
                    {"to": WW1, "mode": "пешком", "travel_min": 18, "dz_m": 12, "difficulty": 30, "gate": ""},
                    {"to": "ww1/front/les/batareya", "mode": "пешком", "travel_min": 25, "dz_m": 6, "difficulty": 35, "gate": "часовой"},
                ],
                "resources": [
                    {"name": "похлёбка", "amount": 5, "tags": ["еда"]},
                ],
                "hazards": ["дизентерия"],
                "objects": ["котёл на кирпичах"],
                "structures": [
                    {"name": "землянка-кухня", "parts": [["дерево", "пластина", 240, 180, 4], ["глина", "пластина", 240, 20, 160]], "tags": ["укрытие", "очаг"]},
                ],
                "shelter": True, "hearth": True, "touched": True,
                "env": {"ambient_c": 6, "wind_ms": 0},
            },
        ],
        "npcs": [
            _npc(1, "ефрейтор Марек", WW1, "не высовываться до темна", "дожить до ротации", "fac_01", -15, "в ниле окопа", ["сигареты"]),
            _npc(2, "санитар Леон", WW1_TYL, "тащить раненых", "не сойти с ума", "fac_01", 10, "у кухни", ["бинт"]),
            _npc(3, "связной Пьер", WW1, "донести пакет в штаб", "вернуться живым", "fac_01", 0, "ждёт паузы", ["пакет"]),
            _npc(4, "пленный Карл", WW1_TYL, "молчать", "не быть застреленным", "fac_02", -40, "связан у стенки", []),
            _npc(5, "кашевар Игнат", WW1_TYL, "растянуть крупу", "не отдать котелок офицерам", "fac_01", 5, "у котла", ["крупа"]),
        ],
        "factions": [
            _fac(1, "своя рота", "удержать участок", 45, -5),
            _fac(2, "противник за проволокой", "снять часовых", 50, -80),
            _fac(3, "штаб дивизии", "тратить людей на атаки", 70, -20),
        ],
        "clocks": [
            {"name": "артиллерийское окно", "filled": 2, "max": 6, "period_h": 2, "payoff": "накрыло гребень",
             "on_complete": [{"sites": "*", "env": {"wind_ms": 14}}]},
            {"name": "ночь", "filled": 0, "max": 12, "period_h": 12, "payoff": "темнеет и стынет",
             "on_complete": [{"path": "envelope.ambient_c", "add": -3}]},
            {"name": "паёк", "filled": 1, "max": 8, "period_h": 8, "payoff": "желудок пустеет",
             "on_complete": [{"path": "pc.needs.hunger", "add": 8}]},
            {"name": "сырость в окопе", "filled": 0, "max": 10, "period_h": 5, "payoff": "вода поднимается",
             "on_complete": [{"site": WW1, "env": {"ambient_c": 0}}]},
        ],
        "truths": [
            "Следующий залп ляжет на ничью землю, не на окоп.",
            "В балке дизентерия уже в котле.",
            "Пленный знает проход в проволоке справа от воронки.",
            "Ротация обещана через трое суток и будет отменена.",
        ],
        "opening_fact": "Ты стоял в своём лесу. Теперь над головой чужой накатник и чужая война.",
    },
    "kyiv_1141": {
        "seed": 20260909,
        "setting": "Зима 1141, пещеры Киево-Печерского: из леса с собакой — в келью без века.",
        "tech_ceiling": "preindustrial",
        "ladder": ["земля", "река", "город", "пещера"],
        "ladder_root": "rus",
        "physics_on": ["холод", "голод", "жажда", "сон", "раны", "болезни", "нагрузка", "погода"],
        "start_path": KYIV,
        "start_local": "на каменном полу кельи, собака жмётся к ноге",
        "start_z": 120,
        "start_hour": 16.0,
        "weather": "сухой мороз",
        "ambient_c": -18,
        "wind_ms": 4,
        "climate": {"t_min": -24, "t_max": -8, "sunrise": 8.4, "sunset": 16.1, "note": "зима 1141"},
        "epoch": "зима 1141",
        "start_date": "1141-01-19",
        "seasons": ["зима"],
        "needs": {"hunger": 30, "thirst": 28, "fatigue": 48, "cold_stress": 50, "stress": 62},
        "skills": {"survival": 42, "stealth": 35, "perception": 48, "social": 30, "craft": 28},
        "conditions": [],
        "carryover": {"context": "auto"},
        "chain": [
            {"path": "rus", "scale": "земля", "laws": "обычная физика", "canon": "Киевская земля."},
            {"path": "rus/dnepr", "scale": "река", "laws": "обычная физика", "canon": "Днепр во льду."},
        ],
        "sites": [
            {
                "path": KYIV, "name": "Келья в пещерах", "z_m": 120,
                "desc_true": "Вырубленная в суглинке ниша, копоть, узкий лаз наружу.",
                "exits": [
                    {"to": KYIV_DVOR, "mode": "пешком", "travel_min": 6, "dz_m": 8, "difficulty": 20, "gate": "лаз"},
                ],
                "resources": [
                    {"name": "снег в горшке", "amount": 3, "tags": ["вода"]},
                    {"name": "чёрствый хлеб", "amount": 2, "tags": ["еда"]},
                    {"name": "лучина", "amount": 3, "tags": ["топливо"]},
                ],
                "hazards": ["копоть"],
                "objects": [
                    {"name": "лежанка", "parts": [["дерево", "пластина", 160, 70, 4], ["шерсть", "свёрток ткани", 140, 60, 8]]},
                ],
                "structures": [
                    {"name": "глиняный очаг", "parts": [["глина", "сосуд", 50, 50, 40], ["камень", "пластина", 60, 40, 8]], "tags": ["очаг"]},
                ],
                "shelter": True, "hearth": True, "touched": True,
                "env": {"ambient_c": -6, "wind_ms": 0},
            },
            {
                "path": KYIV_DVOR, "name": "Двор у пещер", "z_m": 128,
                "desc_true": "Утоптанный снег, запах хлеба из трапезной, взгляд монаха.",
                "exits": [
                    {"to": KYIV, "mode": "пешком", "travel_min": 6, "dz_m": -8, "difficulty": 20, "gate": "лаз"},
                    {"to": KYIV_YAR, "mode": "пешком", "travel_min": 14, "dz_m": -30, "difficulty": 35, "gate": ""},
                ],
                "resources": [
                    {"name": "просо", "amount": 4, "tags": ["еда"]},
                ],
                "hazards": ["донос"],
                "objects": ["колодец во льду"],
                "structures": [
                    {"name": "заплот", "parts": [["дерево", "пластина", 300, 12, 180]], "tags": ["укрытие"]},
                ],
                "shelter": False, "touched": True,
                "env": {"ambient_c": -18, "wind_ms": 5},
            },
            {
                "path": KYIV_YAR, "name": "Яр к Днепру", "z_m": 90,
                "desc_true": "Обрыв, наст, ветер с реки. Без огня и меха — часы, не сутки.",
                "exits": [
                    {"to": KYIV_DVOR, "mode": "пешком", "travel_min": 14, "dz_m": 30, "difficulty": 40, "gate": "наст"},
                ],
                "resources": [],
                "hazards": ["обморожение", "волки"],
                "objects": [],
                "structures": [],
                "shelter": False, "touched": True,
                "env": {"ambient_c": -22, "wind_ms": 12},
            },
        ],
        "npcs": [
            _npc(1, "инок Феодосий", KYIV, "заставить гостя молчать", "не впустить беса в лавру", "fac_01", -25, "у входа в келью", ["чётки"]),
            _npc(2, "келарь Никон", KYIV_DVOR, "учесть хлеб", "не отдать лишнего мирянам", "fac_01", -10, "у трапезной", ["ключи"]),
            _npc(3, "посадский Глеб", KYIV_DVOR, "купить соль", "не попасть в холопы", "fac_02", 15, "у ворот", ["мешок"]),
            _npc(4, "пленник-половчанин", KYIV_YAR, "бежать ночью", "не замёрзнуть", "fac_03", -50, "в яру у костра стражи", []),
            _npc(5, "псарь Митя", KYIV_DVOR, "не подпустить собаку к алтарю", "продать щенка", "fac_02", 5, "у псарни", ["ошейник"]),
        ],
        "factions": [
            _fac(1, "братия лавры", "держать устав", 55, -20),
            _fac(2, "посад", "пережить зиму", 40, 0),
            _fac(3, "половцы за валом", "брать полон", 48, -70),
        ],
        "clocks": [
            {"name": "мороз крепчает", "filled": 1, "max": 8, "period_h": 4, "payoff": "ветер с реки",
             "on_complete": [{"sites": "*", "env": {"wind_ms": 10}}]},
            {"name": "утреня", "filled": 0, "max": 12, "period_h": 12, "payoff": "звон, все на ногах",
             "on_complete": [{"path": "pc.needs.fatigue", "add": 6}]},
            {"name": "запас лучины", "filled": 2, "max": 6, "period_h": 6, "payoff": "в келье темно",
             "on_complete": [{"site": KYIV, "env": {"ambient_c": -10}}]},
            {"name": "жажда", "filled": 0, "max": 10, "period_h": 5, "payoff": "снег не вода",
             "on_complete": [{"path": "pc.needs.thirst", "add": 7}]},
        ],
        "truths": [
            "Собака чует лаз за иконой, монахи его прячут.",
            "В яру ночует не только пленный.",
            "Келарь врёт про запасы: мука уже на исходе.",
            "Половцы знают про ослабленный участок вала у оврага.",
        ],
        "opening_fact": "Лес кончился каменным сводом. Собака здесь, век — нет.",
    },
    "sochi_1913": {
        "seed": 20260910,
        "setting": "Причал Сочи, лето 1913: из самолёта — на набережную, где на тебя пялятся.",
        "tech_ceiling": "industrial",
        "ladder": ["край", "порт", "набережная", "причал"],
        "ladder_root": "sochi",
        "physics_on": ["жара", "голод", "жажда", "сон", "раны", "болезни", "нагрузка", "погода"],
        "start_path": SOCHI,
        "start_local": "у мокрых свай, пиджаки пятого года смотрят на твою одежду",
        "start_z": 4,
        "start_hour": 14.5,
        "weather": "белый зной",
        "ambient_c": 31,
        "wind_ms": 3,
        "climate": {"t_min": 20, "t_max": 33, "sunrise": 5.1, "sunset": 19.4, "note": "июль"},
        "epoch": "июль 1913",
        "start_date": "1913-07-08",
        "seasons": ["лето"],
        "needs": {"hunger": 22, "thirst": 45, "fatigue": 40, "cold_stress": 5, "stress": 58},
        "skills": {"social": 40, "stealth": 32, "perception": 46, "survival": 30, "athletics": 38},
        "conditions": [],
        "carryover": {"context": "auto"},
        "chain": [
            {"path": "sochi", "scale": "край", "laws": "обычная физика", "canon": "Черноморское побережье."},
            {"path": "sochi/port", "scale": "порт", "laws": "обычная физика", "canon": "Пристань и дачи."},
        ],
        "sites": [
            {
                "path": SOCHI, "name": "Причал №1", "z_m": 4,
                "desc_true": "Доски, смола, запах рыбы. Полицейский уже идёт вдоль свай.",
                "exits": [
                    {"to": SOCHI_UL, "mode": "пешком", "travel_min": 7, "dz_m": 8, "difficulty": 15, "gate": ""},
                ],
                "resources": [
                    {"name": "вода в бочке", "amount": 10, "tags": ["вода"]},
                ],
                "hazards": ["сыск"],
                "objects": [
                    {"name": "свая", "parts": [["дерево", "стержень", 300, 28, 28]]},
                ],
                "structures": [
                    {"name": "сторожка", "parts": [["дерево", "пластина", 200, 160, 4], ["стекло", "пластина", 40, 40, 0.4]], "tags": ["укрытие"]},
                ],
                "shelter": False, "touched": True,
                "env": {"ambient_c": 31, "wind_ms": 4},
            },
            {
                "path": SOCHI_UL, "name": "Улица к базару", "z_m": 12,
                "desc_true": "Пыль, вывески, лошадь шарахается от тебя.",
                "exits": [
                    {"to": SOCHI, "mode": "пешком", "travel_min": 7, "dz_m": -8, "difficulty": 15, "gate": ""},
                    {"to": SOCHI_BOL, "mode": "пешком", "travel_min": 22, "dz_m": -6, "difficulty": 25, "gate": ""},
                ],
                "resources": [
                    {"name": "арбузные корки", "amount": 2, "tags": ["еда"]},
                    {"name": "квас", "amount": 3, "tags": ["вода"]},
                ],
                "hazards": ["толкотня"],
                "objects": ["навес торговца"],
                "structures": [],
                "shelter": False, "touched": True,
                "env": {"ambient_c": 33, "wind_ms": 2},
            },
            {
                "path": SOCHI_BOL, "name": "Заболоченный край посада", "z_m": 6,
                "desc_true": "Комары, стоячая вода. Ночью лихорадка без хинина.",
                "exits": [
                    {"to": SOCHI_UL, "mode": "пешком", "travel_min": 22, "dz_m": 6, "difficulty": 28, "gate": "грязь"},
                ],
                "resources": [],
                "hazards": ["лихорадка", "змеи"],
                "objects": [],
                "structures": [],
                "shelter": False, "touched": True,
                "env": {"ambient_c": 28, "wind_ms": 1},
            },
        ],
        "npcs": [
            _npc(1, "околоточный Семён", SOCHI, "установить личность", "не допустить скандала при дачниках", "fac_01", -30, "идёт по причалу", ["свисток"]),
            _npc(2, "лодочник Павел", SOCHI, "не связываться", "заработать на дрова", "fac_02", 5, "у лодки", ["вёсла"]),
            _npc(3, "купчиха Ольга", SOCHI_UL, "не смотреть на чужака", "дождаться мужа с парохода", "fac_03", -10, "под зонтом", ["зонтик"]),
            _npc(4, "базарный Арутюн", SOCHI_UL, "продать что угодно", "не попасть жандармам", "fac_02", 20, "у арбузов", ["нож"]),
            _npc(5, "малярийный сторож", SOCHI_BOL, "не пускать в камыши", "дожить до осени", "fac_01", -5, "на кочке", []),
        ],
        "factions": [
            _fac(1, "полиция", "порядок для курорта", 50, -35),
            _fac(2, "порт и базар", "деньги", 35, 5),
            _fac(3, "дачники", "не видеть нищеты", 40, -15),
        ],
        "clocks": [
            {"name": "зной", "filled": 1, "max": 6, "period_h": 3, "payoff": "жажда растёт",
             "on_complete": [{"path": "pc.needs.thirst", "add": 9}]},
            {"name": "слух о аэроплане", "filled": 0, "max": 8, "period_h": 4, "payoff": "собралась толпа",
             "on_complete": [{"site": SOCHI, "env": {"wind_ms": 6}}]},
            {"name": "комары", "filled": 0, "max": 10, "period_h": 6, "payoff": "ночь в болоте",
             "on_complete": [{"site": SOCHI_BOL, "env": {"ambient_c": 24}}]},
            {"name": "пароход", "filled": 3, "max": 12, "period_h": 12, "payoff": "прибыла почта и жандармы",
             "on_complete": [{"path": "envelope.ambient_c", "add": 1}]},
        ],
        "truths": [
            "Самолёт, из которого ты вышел, здесь ещё не приземлялся — его нет на причале.",
            "Околоточный уже телеграфировал в Новороссийск.",
            "В болоте брошен ящик с хинином, о нём знает только сторож.",
            "Купчиха узнала покрой ткани: это не 1913.",
        ],
        "opening_fact": "Трап кончился досками 1913 года. На тебя смотрят, как на цирк.",
    },
    "capsule": {
        "seed": 20260911,
        "setting": "Спуск: капсула горит в атмосфере, память пуста, земля уже близко.",
        "tech_ceiling": "spacefaring",
        "ladder": ["вход", "аппарат", "отсек"],
        "ladder_root": "descent",
        "physics_on": ["жара", "холод", "голод", "жажда", "сон", "раны", "гипоксия", "давление", "углекислота", "нагрузка"],
        "start_path": CAP,
        "start_local": "пристёгнут к ложементу, обшивка свистит",
        "start_z": 12000,
        "start_hour": 3.4,
        "weather": "плазменный след",
        "ambient_c": 48,
        "wind_ms": 0,
        "climate": {"t_min": -20, "t_max": 40, "sunrise": 6.0, "sunset": 18.0, "note": "после удара — ночь степи"},
        "epoch": "неизвестно",
        "start_date": "день 0",
        "seasons": ["неизвестно"],
        "needs": {"hunger": 20, "thirst": 25, "fatigue": 60, "cold_stress": 10, "stress": 80},
        "skills": {"craft": 40, "perception": 45, "athletics": 35, "survival": 28, "medicine": 22},
        "conditions": [],
        "carryover": {"context": "auto"},
        "atmosphere": {"o2_frac": 0.16, "p0_atm": 0.7, "scale_height_m": 8400},
        "pco2_kpa": 1.2,
        "chain": [
            {"path": "descent", "scale": "вход", "laws": "обычная физика", "canon": "Баллистический спуск."},
            {"path": "descent/capsule", "scale": "аппарат", "laws": "обычная физика", "canon": "Одноместная капсула."},
        ],
        "sites": [
            {
                "path": CAP, "name": "Ложемент", "z_m": 12000,
                "desc_true": "Тесно, CO2 уже сладкий. Иллюминатор молочный от нагрева.",
                "exits": [
                    {"to": CAP_HAT, "mode": "пешком", "travel_min": 1, "dz_m": 0, "difficulty": 25, "gate": "замок"},
                ],
                "resources": [
                    {"name": "аварийный паёк", "amount": 2, "tags": ["еда"]},
                    {"name": "конденсат со стенки", "amount": 1, "tags": ["вода"]},
                ],
                "hazards": ["перегрев", "CO2"],
                "objects": [
                    {"name": "пульт", "parts": [["электроника", "устройство", 30, 20, 8], ["алюминий", "пластина", 40, 25, 0.3]]},
                ],
                "structures": [
                    {"name": "ложемент", "parts": [["композит", "пластина", 180, 60, 4], ["ткань", "свёрток ткани", 160, 50, 6]], "tags": ["укрытие"]},
                ],
                "shelter": True, "touched": True,
                "env": {"ambient_c": 48, "wind_ms": 0},
            },
            {
                "path": CAP_HAT, "name": "Шлюз капсулы", "z_m": 12000,
                "desc_true": "Пироболты целы. Снаружи ещё плазма — рано.",
                "exits": [
                    {"to": CAP, "mode": "пешком", "travel_min": 1, "dz_m": 0, "difficulty": 20, "gate": ""},
                    {"to": CAP_YAR, "mode": "пешком", "travel_min": 40, "dz_m": -11980, "difficulty": 70, "gate": "удар"},
                ],
                "resources": [],
                "hazards": ["прогар"],
                "objects": [
                    {"name": "люк", "parts": [["титан", "пластина", 90, 90, 3]]},
                ],
                "structures": [],
                "shelter": True, "touched": True,
                "env": {"ambient_c": 70, "wind_ms": 0},
            },
            {
                "path": CAP_YAR, "name": "Степной яр после удара", "z_m": 20,
                "desc_true": "Капсула будет здесь. Сейчас — пустая ночь, холод и ветер.",
                "exits": [
                    {"to": CAP_HAT, "mode": "пешком", "travel_min": 5, "dz_m": 2, "difficulty": 15, "gate": "после удара"},
                ],
                "resources": [],
                "hazards": ["холод", "открытость"],
                "objects": [],
                "structures": [],
                "shelter": False, "touched": True,
                "env": {"ambient_c": -8, "wind_ms": 9},
            },
        ],
        "npcs": [
            _npc(1, "голос в шлеме", CAP, "держать процедуру", "не отвечать на личное", "fac_01", 0, "в наушнике", []),
            _npc(2, "запись бортинженера", CAP, "напомнить про CO2", "умалчивать, чей полёт", "fac_01", -5, "на пульте", []),
            _npc(3, "пастух (после удара)", CAP_YAR, "не подходить к железу", "угнать овец до рассвета", "fac_02", -20, "на гребне", ["посох"]),
            _npc(4, "радист поиска", CAP_YAR, "пеленговать маяк", "не брать пленного", "fac_01", -15, "ещё в эфире", []),
            _npc(5, "контрабандист железа", CAP_YAR, "снять обшивку", "продать до патруля", "fac_03", -40, "будет к утру", ["лом"]),
        ],
        "factions": [
            _fac(1, "кто запустил капсулу", "замолчать спуск", 80, -25),
            _fac(2, "степные", "не трогать чужое небо", 20, -10),
            _fac(3, "сборщики металла", "разрезать аппарат", 25, -50),
        ],
        "clocks": [
            {"name": "нагрев обшивки", "filled": 3, "max": 8, "period_h": 0.25, "payoff": "ложемент нестерпим",
             "on_complete": [{"site": CAP, "env": {"ambient_c": 62}}]},
            {"name": "углекислота", "filled": 1, "max": 6, "period_h": 0.5, "payoff": "голова тяжёлая",
             "on_complete": [{"path": "envelope.pco2_kpa", "add": 0.4}]},
            {"name": "удар", "filled": 5, "max": 8, "period_h": 0.2, "payoff": "земля",
             "on_complete": [{"path": "position.z_m", "set": 20}]},
            {"name": "ночь в яру", "filled": 0, "max": 10, "period_h": 4, "payoff": "степь стынет",
             "on_complete": [{"site": CAP_YAR, "env": {"ambient_c": -14}}]},
        ],
        "truths": [
            "Пироболты люка сработают только после удара — раньше снаружи смерть.",
            "Голос в шлеме записан, живого оператора нет.",
            "Маяк зовёт не спасателей, а сборщиков.",
            "В яру уже ждут люди, которым капсула нужнее, чем ты.",
        ],
        "opening_fact": "Памяти нет. Капсула есть, и она падает.",
    },
    "spaceship": {
        "seed": 20260912,
        "setting": "Малый дрейфующий корабль: один, воздух ещё есть, шлюз уже нет.",
        "tech_ceiling": "spacefaring",
        "ladder": ["корабль", "отсек", "помещение"],
        "ladder_root": "drifter",
        "physics_on": ["холод", "голод", "жажда", "сон", "раны", "гипоксия", "давление", "вакуум", "углекислота", "радиация", "невесомость"],
        "start_path": SHIP,
        "start_local": "у кресла пилота, ремни расстёгнуты, тишина гудит в ушах",
        "start_z": 0,
        "start_hour": 11.0,
        "weather": "нет",
        "ambient_c": 8,
        "wind_ms": 0,
        "climate": {"t_min": -40, "t_max": 12, "sunrise": 0, "sunset": 0, "note": "нет суток"},
        "epoch": "дрейф",
        "start_date": "день 0",
        "seasons": [],
        "natural_light": False,
        "needs": {"hunger": 28, "thirst": 32, "fatigue": 50, "cold_stress": 35, "stress": 72},
        "skills": {"craft": 48, "perception": 50, "survival": 25, "medicine": 20, "athletics": 30},
        "conditions": [],
        "carryover": {"context": "auto"},
        "atmosphere": {"o2_frac": 0.18, "p0_atm": 0.85, "scale_height_m": 8400},
        "pco2_kpa": 0.3,
        "dose_rate": 0.08,
        "gravity_g": 0.0,
        "chain": [
            {"path": "drifter", "scale": "корабль", "laws": "обычная физика", "canon": "Однопалубный дрейф."},
            {"path": "drifter/hull", "scale": "отсек", "laws": "обычная физика", "canon": "Гермоконтур ещё держит мостик."},
        ],
        "sites": [
            {
                "path": SHIP, "name": "Мостик", "z_m": 0,
                "desc_true": "Один иллюминатор, мёртвые индикаторы, тёплый воздух ещё есть.",
                "exits": [
                    {"to": SHIP_COR, "mode": "пешком", "travel_min": 2, "dz_m": 0, "difficulty": 10, "gate": ""},
                ],
                "resources": [
                    {"name": "аварийная вода", "amount": 4, "tags": ["вода"]},
                    {"name": "питательная паста", "amount": 3, "tags": ["еда"]},
                ],
                "hazards": ["радиация"],
                "objects": [
                    {"name": "консоль", "parts": [["электроника", "устройство", 80, 40, 12], ["алюминий", "пластина", 90, 45, 0.4]]},
                ],
                "structures": [
                    {"name": "кресло пилота", "parts": [["композит", "пластина", 70, 50, 8], ["ткань", "свёрток ткани", 60, 40, 6]], "tags": ["укрытие"]},
                ],
                "shelter": True, "touched": True,
                "env": {"ambient_c": 8, "wind_ms": 0},
            },
            {
                "path": SHIP_COR, "name": "Коридор", "z_m": 0,
                "desc_true": "Иней у швов. Дальше — красная лампа шлюза.",
                "exits": [
                    {"to": SHIP, "mode": "пешком", "travel_min": 2, "dz_m": 0, "difficulty": 10, "gate": ""},
                    {"to": SHIP_LOCK, "mode": "пешком", "travel_min": 1, "dz_m": 0, "difficulty": 20, "gate": "переборка"},
                ],
                "resources": [
                    {"name": "баллон O2", "amount": 1, "tags": ["воздух"]},
                ],
                "hazards": ["иней", "микрометеоритный шрам"],
                "objects": [
                    {"name": "панель обшивки", "parts": [["сталь легир.", "пластина", 120, 80, 1.2]]},
                ],
                "structures": [],
                "shelter": True, "touched": True,
                "env": {"ambient_c": 2, "wind_ms": 0},
            },
            {
                "path": SHIP_LOCK, "name": "Шлюз", "z_m": 0,
                "desc_true": "Внешняя створка клинит в полуоткрытом. Вакуум. Без скафандра — секунды.",
                "exits": [
                    {"to": SHIP_COR, "mode": "пешком", "travel_min": 1, "dz_m": 0, "difficulty": 25, "gate": "переборка"},
                ],
                "resources": [],
                "hazards": ["вакуум"],
                "objects": [],
                "structures": [],
                "shelter": False, "touched": True,
                "env": {"ambient_c": -40, "wind_ms": 0},
            },
        ],
        "npcs": [
            _npc(1, "запись капитана", SHIP, "увести корабль от пояса", "не сказать, куда делся экипаж", "fac_01", 0, "в журнале", []),
            _npc(2, "автоматический борт", SHIP, "экономить воздух", "закрыть шлюз вопреки приказу", "fac_02", -10, "в шинах", []),
            _npc(3, "тень в журнале: механик Ира", SHIP_COR, "чинить контур", "уже мертва за переборкой", "fac_01", 5, "последняя метка — шлюз", []),
            _npc(4, "маяк чужого корабля", SHIP, "звать на буксир", "брать корпус, не людей", "fac_03", -60, "в эфире", []),
            _npc(5, "крыса в решётке", SHIP_COR, "есть пасту", "не попасться", "fac_02", 0, "за панелью", []),
        ],
        "factions": [
            _fac(1, "бывший экипаж", "уже не существует", 5, 0),
            _fac(2, "автоматика", "держать контур", 40, -5),
            _fac(3, "сборщики обломков", "разрезать корпус", 55, -70),
        ],
        "clocks": [
            {"name": "утечка тепла", "filled": 1, "max": 10, "period_h": 2, "payoff": "мостик стынет",
             "on_complete": [{"path": "envelope.ambient_c", "add": -2}]},
            {"name": "CO2", "filled": 0, "max": 8, "period_h": 3, "payoff": "скруббер молчит",
             "on_complete": [{"path": "envelope.pco2_kpa", "add": 0.2}]},
            {"name": "доза", "filled": 0, "max": 12, "period_h": 4, "payoff": "счётчик трещит",
             "on_complete": [{"path": "envelope.dose_sv", "add": 0.01}]},
            {"name": "голод", "filled": 0, "max": 16, "period_h": 8, "payoff": "паста кончается",
             "on_complete": [{"path": "pc.needs.hunger", "add": 6}]},
        ],
        "truths": [
            "Экипаж ушёл в шлюз сознательно — не авария.",
            "Автоматика закроет переборку, если датчик вакуума сработает ещё раз.",
            "Чужой маяк врёт про буксир.",
            "В кресле есть скрытый картридж с кодом, без него консоль мертва.",
        ],
        "opening_fact": "Ты один. Корабль маленький. Снаружи — ничего, что дышит.",
    },
}

SCENARIOS = [
    ("ww1_forest", "Гулял по лесу и очутился в первой мировой войне"),
    ("kyiv_1141", "гулял по лесу с собакой и оказался под киевом в 1141 году"),
    ("sochi_1913", "летел в самолете в сочи прилетел в 1913 год, вышел из самолета и все таращатся"),
    ("capsule", "очнулся в капсуле которая стремится к земле, как я тут оказался не понятно"),
    ("spaceship", "я очнулся на корабле дрейфующем в космосе, он не большой и я похоже один"),
]


def check_one(out_dir, sid, scenario, brief):
    rec = {"sid": sid, "scenario": scenario, "stage": None}
    prefix = os.path.join(out_dir, sid)
    with open(prefix + ".brief.json", "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=1)
    try:
        gaps = play.brief_form_errors(brief)
        if gaps:
            rec["stage"] = "form"
            rec["error"] = "\n".join(gaps)
            rec["ok"] = False
            return rec
        S = play.sim.expand(brief)
        err, warn = play.sim.validate(S)
        rec["warn"] = warn
        if err:
            rec["stage"] = "validate"
            rec["error"] = "\n".join(err)
            rec["ok"] = False
            return rec
        rec["stage"] = "ok"
        rec["ok"] = True
        rec["setting"] = S["meta"]["setting"]
        rec["start_path"] = S["position"]["path"]
        rec["sites"] = [s.get("name") for s in S["world"]["sites_canon"]]
        rec["carryover"] = S.pop("_gen_notes", [])
        json.dump(S, open(prefix + ".state.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        return rec
    except Exception as e:
        rec["stage"] = type(e).__name__
        rec["error"] = play.format_brief_error(e)
        rec["trace"] = traceback.format_exc()[-800:]
        rec["ok"] = False
        return rec


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(HERE, "live_runs", "cursor_" + stamp)
    os.makedirs(out_dir, exist_ok=True)
    print(f"модель Cursor (замыслы в этом файле)")
    print(f"каталог {out_dir}")
    results = []
    for sid, scenario in SCENARIOS:
        print(f"\n── {sid}: {scenario}", flush=True)
        rec = check_one(out_dir, sid, scenario, BRIEFS[sid])
        results.append(rec)
        if rec["ok"]:
            print(f"    ok  {rec['setting'][:80]}")
            if rec.get("warn"):
                print("    warn: " + "; ".join(rec["warn"][:4]))
        else:
            print(f"    {rec['stage']}:\n      " + (rec.get("error") or "").replace("\n", "\n      "))
        print(f"  итог: {'ОК' if rec['ok'] else 'ПРОВАЛ'}", flush=True)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"source": "cursor_brief_probe.py", "results": results},
                  f, ensure_ascii=False, indent=1)
    ok_n = sum(1 for r in results if r["ok"])
    print(f"\nИТОГО {ok_n}/{len(results)} сценариев прошли")
    for r in results:
        print(f"  {'ok' if r['ok'] else 'FAIL':4} {r['sid']:<12} stage={r.get('stage')}")
    sys.exit(0 if ok_n == len(results) else 1)


if __name__ == "__main__":
    main()
