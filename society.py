#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Слой общества: мир живёт сам, а не только вокруг игрока.

Раньше каждый NPC действовал в вакууме. Здесь они встречаются, обмениваются
слухами, ссорятся и мирятся; фракции воюют между собой; ресурсы на площадках
расходуются населением и восстанавливаются.

Всё детерминировано зерном: тот же seed — та же история мира.
"""
import hashlib


def _roll(seed, period, salt, mod=100):
    return int(hashlib.sha256(f"{seed}|{period}|{salt}".encode()).hexdigest(), 16) % mod + 1


def _pid(s):
    return int(hashlib.sha256(str(s).encode()).hexdigest(), 16)


def _soc(R):
    return R.get("society", {
        "rumor_delay_h": 30,
        "meeting_disposition_step": 5,
        "conflict_below": -50,
        "alliance_above": 50,
        "faction_period_h": 24,
        "npc_supply_per_period": 1.0,
    })


# ─────────── ВСТРЕЧИ NPC ДРУГ С ДРУГОМ ───────────

def npc_meetings(S, log, period, R):
    """Двое на одной площадке — это событие, а не совпадение.
    Обмениваются тем, что знают, и меняют отношение друг к другу."""
    cfg = _soc(R)
    by_path = {}
    for n in S["world"]["npcs"]:
        if n.get("alive", True):
            by_path.setdefault(n["path"], []).append(n)

    fac = {f["id"]: f for f in S["world"].get("factions", [])}

    for path, group in by_path.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                rel = faction_relation(S, a.get("faction"), b.get("faction"))

                # 1. слух об игроке передаётся тому, кто ещё не знает
                for src, dst in ((a, b), (b, a)):
                    if src.get("knows_about_pc") and not dst.get("knows_about_pc"):
                        dst.setdefault("knows_about_pc", []).append({
                            "turn": S["meta"]["turn"],
                            "source": f"рассказал {src['name']}",
                            "fact": "о чужаке говорят"})
                        log.append(f"[слух] {src['name']} рассказывает {dst['name']} о чужаке.")

                # 2. отношение сдвигается по линии фракций
                step = cfg["meeting_disposition_step"]
                if rel is not None and rel <= cfg["conflict_below"]:
                    r = _roll(S["meta"]["seed"], period, f"clash|{a['id']}|{b['id']}")
                    if r <= 30:
                        loser = a if r % 2 else b
                        winner = b if loser is a else a
                        loser["alive"] = False
                        log.append(f"[столкновение] {winner['name']} и {loser['name']} сошлись — "
                                   f"{loser['name']} убит.")
                        for f in S["world"].get("factions", []):
                            if f["id"] == loser.get("faction"):
                                f["power"] = max(0, f.get("power", 5) - 1)
                                log.append(f"[фракции] {f['name']} теряет человека, сила падает до {f['power']}.")
                    else:
                        log.append(f"[напряжение] {a['name']} и {b['name']} разошлись, не сцепившись.")
                        mover = a if r % 2 else b
                        cands = [e["to"] for st in S["world"]["sites_canon"]
                                 if st["path"] == mover["path"] for e in st["exits"]]
                        if cands:
                            mover["path"] = cands[r % len(cands)]
                elif rel is not None and rel >= cfg["alliance_above"]:
                    a["disposition"] = min(100, a.get("disposition", 0) + step // 2)
                    b["disposition"] = min(100, b.get("disposition", 0) + step // 2)


def faction_relation(S, fa, fb):
    """Отношение двух фракций. None, если хотя бы одна не задана."""
    if not fa or not fb or fa == fb:
        return None
    for f in S["world"].get("factions", []):
        if f["id"] == fa:
            return f.get("relations", {}).get(fb)
    return None


# ─────────── РАСХОЖДЕНИЕ СЛУХОВ ПО ФРАКЦИИ ───────────

def rumor_step(S, log, R):
    """Слух не мгновенен: он доходит до своих за отведённое время,
    и только к тем, кто состоит в той же фракции."""
    cfg = _soc(R)
    delay = cfg["rumor_delay_h"]
    now = S["time"]["t_h"]
    knowers = [n for n in S["world"]["npcs"]
               if n.get("alive", True) and n.get("knows_about_pc")]
    for k in knowers:
        first = min((x.get("turn", 0) for x in k["knows_about_pc"]), default=None)
        heard_at = k.get("_knew_at_h")
        if heard_at is None:
            k["_knew_at_h"] = now
            continue
        if now - heard_at < delay:
            continue
        for n in S["world"]["npcs"]:
            if n is k or not n.get("alive", True) or n.get("knows_about_pc"):
                continue
            same = n.get("faction") and n["faction"] == k.get("faction")
            rel = faction_relation(S, k.get("faction"), n.get("faction"))
            allied = rel is not None and rel >= cfg["alliance_above"] // 5   # дружественные тоже слышат
            if same:
                waited, how = delay, f"слух по своим ({k['name']})"
            elif allied:
                waited, how = delay * 3, f"слух через соседей ({k['name']})"   # дольше и не всегда
            else:
                continue
            if now - heard_at < waited:
                continue
            n["knows_about_pc"] = [{"turn": S["meta"]["turn"], "source": how,
                                    "fact": "о чужаке говорят"}]
            n["_knew_at_h"] = now
            log.append(f"[слух] о чужаке узнаёт {n['name']} — {how}.")


# ─────────── ФРАКЦИИ ЖИВУТ СВОЕЙ ЖИЗНЬЮ ───────────

def faction_step(S, log, period, R):
    """Фракции воюют, слабеют, усиливаются — независимо от игрока."""
    cfg = _soc(R)
    facs = S["world"].get("factions", [])
    if len(facs) < 2:
        return
    for i in range(len(facs)):
        for j in range(i + 1, len(facs)):
            A, B = facs[i], facs[j]
            rel = A.get("relations", {}).get(B["id"])
            if rel is None:
                continue
            r = _roll(S["meta"]["seed"], period, f"fac|{A['id']}|{B['id']}")
            if rel <= cfg["conflict_below"] and r <= 25:
                pa, pb = A.get("power", 5), B.get("power", 5)
                # шанс победы пропорционален силе: слабый может огрызнуться
                total = max(1, pa + pb)
                upset = _roll(S["meta"]["seed"], period, "upset|" + A["id"] + "|" + B["id"])
                strong, weak = (A, B) if (upset % total) < pa else (B, A)
                weak["power"] = max(0, weak.get("power", 5) - 1)
                strong["power"] = min(cfg.get("power_cap", 10), strong.get("power", 5) + (1 if r <= 8 else 0))
                log.append(f"[фракции] {strong['name']} теснит {weak['name']}: "
                           f"сила {weak['name']} падает до {weak['power']}.")
                A["relations"][B["id"]] = max(-100, rel - 5)
                B.setdefault("relations", {})[A["id"]] = max(-100, rel - 5)
                if weak["power"] == 0 and not weak.get("_broken"):
                    weak["_broken"] = True
                    log.append(f"[ФРАКЦИЯ СЛОМЛЕНА] {weak['name']} перестаёт существовать как сила. "
                               f"Её люди разбегаются, территория ничья.")
            elif rel >= cfg["alliance_above"] and r <= 15:
                A["power"] = min(10, A.get("power", 5) + 1)
                log.append(f"[фракции] {A['name']} и {B['name']} держатся вместе, "
                           f"{A['name']} крепнет.")


# ─────────── РЕСУРСЫ ПЛОЩАДОК ───────────

def resource_step(S, log, hours):
    """Население ест и пьёт. Ресурсы истощаются и восстанавливаются,
    даже там, где игрока нет и не было."""
    pop = {}
    for n in S["world"]["npcs"]:
        if n.get("alive", True):
            pop[n["path"]] = pop.get(n["path"], 0) + 1
    for st in S["world"]["sites_canon"]:
        for res in st.get("resources", []):
            amt = res.get("amount")
            if amt is None or amt >= 999:
                continue
            eaten = pop.get(st["path"], 0) * hours / 24.0
            regen = res.get("renew_per_day", 0) * hours / 24.0
            new = max(0.0, amt - eaten + regen)
            if abs(new - amt) > 0.01:
                res["amount"] = round(new, 2)
            if amt > 0 and new <= 0:
                log.append(f"[ресурс] «{res['name']}» на площадке {st['name']} исчерпан.")


# ─────────── ГЛАВНАЯ ТОЧКА ВХОДА ───────────

def society_step(S, log, hours, R):
    """Вызывается движком в каждом тике. Догоняет пропущенные периоды."""
    cfg = _soc(R)
    ph = cfg["faction_period_h"]
    cur = int(S["time"]["t_h"] // ph)
    last = S["world"].get("_society_period", cur - 1)
    due = max(0, min(6, cur - last))
    for p in range(last + 1, last + 1 + due):
        npc_meetings(S, log, p, R)
        faction_step(S, log, p, R)
    S["world"]["_society_period"] = cur
    rumor_step(S, log, R)
    resource_step(S, log, hours)
