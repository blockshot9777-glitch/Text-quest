#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Живой прогон замысла против LM Studio тем же путём, что play.new_game.

Не часть бандла. Сырые ответы в examples/live_runs/ (gitignore).
Запуск: python examples/live_brief_probe.py
"""
import json, os, sys, time, traceback, urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import play

SCENARIOS = [
    ("ww1_forest", "Гулял по лесу и очутился в первой мировой войне"),
    ("kyiv_1141", "гулял по лесу с собакой и оказался под киевом в 1141 году"),
    ("sochi_1913", "летел в самолете в сочи прилетел в 1913 год, вышел из самолета и все таращатся"),
    ("capsule", "очнулся в капсуле которая стремится к земле, как я тут оказался не понятно"),
    ("spaceship", "я очнулся на корабле дрейфующем в космосе, он не большой и я похоже один"),
]

CFG = {
    "provider": "local",
    "url": "http://127.0.0.1:1234/v1/chat/completions",
    "model": "qwen/qwen3.5-9b",
    "timeout": 400,
}


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def probe_one(out_dir, sid, scenario, cfg):
    errors = ""
    user_error = ""
    attempts = []
    for n in range(3):
        t0 = time.time()
        print(f"  попытка {n+1}/3 …", flush=True)
        try:
            raw, reason = play.llm(
                cfg, play.SYS_BRIEF,
                f"Вводная игрока: {scenario}\nseed = {int(time.time()) % 10**7}"
                + (f"\n\nПрошлая попытка не прошла проверку:\n{errors}\nИсправь." if errors else ""),
                temperature=0.7, max_tokens=play.brief_max_tokens(cfg),
                response_format=play.brief_response_format())
        except (TimeoutError, urllib.error.URLError) as e:
            elapsed = round(time.time() - t0, 1)
            pair = play.brief_transport_messages(e)
            if not pair:
                raise
            errors, user_error, kind = pair
            rec = {"attempt": n + 1, "elapsed_s": elapsed, "finish_reason": None,
                   "raw_chars": 0, "fault": kind, "stage": kind,
                   "error": user_error}
            attempts.append(rec)
            print(f"    {kind}, {elapsed}s", flush=True)
            continue
        elapsed = round(time.time() - t0, 1)
        rec = {"attempt": n + 1, "elapsed_s": elapsed, "finish_reason": reason,
               "raw_chars": len(raw or ""), "fault": None, "stage": None}
        prefix = os.path.join(out_dir, f"{sid}_a{n+1}")
        _write(prefix + ".raw.txt", raw or "")
        fault = play.brief_generation_fault(raw, reason)
        rec["fault"] = fault
        if fault == "loop":
            errors = play.BRIEF_LOOP_RETRY
            user_error = play.BRIEF_LOOP_USER
            rec["stage"] = "loop"
            rec["error"] = user_error
            attempts.append(rec)
            print(f"    loop, {elapsed}s, {rec['raw_chars']} символов", flush=True)
            continue
        if fault == "truncated":
            errors = play.BRIEF_TRUNCATED_RETRY
            user_error = play.BRIEF_TRUNCATED_USER
            rec["stage"] = "truncated"
            rec["error"] = user_error
            attempts.append(rec)
            print(f"    truncated, {elapsed}s, reason={reason}", flush=True)
            continue
        try:
            brief = play.json_from(raw)
            _write(prefix + ".brief.json",
                   json.dumps(brief, ensure_ascii=False, indent=1))
            gaps = play.brief_form_errors(brief)
            if gaps:
                errors = "\n".join(gaps)
                user_error = errors
                rec["stage"] = "form"
                rec["error"] = errors
                attempts.append(rec)
                print(f"    form, {elapsed}s:\n      " + errors.replace("\n", "\n      "),
                      flush=True)
                continue
            S = play.sim.expand(brief)
            err, warn = play.sim.validate(S)
            rec["warn"] = warn
            if err:
                errors = "\n".join(err)
                user_error = errors
                rec["stage"] = "validate"
                rec["error"] = errors
                attempts.append(rec)
                print(f"    validate, {elapsed}s:\n      " + errors.replace("\n", "\n      "),
                      flush=True)
                continue
            rec["stage"] = "ok"
            rec["setting"] = S["meta"]["setting"]
            rec["start_path"] = S["position"]["path"]
            rec["sites"] = [s.get("name") for s in S["world"]["sites_canon"]]
            json.dump(S, open(prefix + ".state.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            attempts.append(rec)
            print(f"    ok, {elapsed}s, {rec['setting'][:80]}", flush=True)
            return {"ok": True, "sid": sid, "scenario": scenario,
                    "attempt": n + 1, "attempts": attempts, "warn": warn,
                    "setting": rec["setting"]}
        except Exception as e:
            errors = play.format_brief_error(e)
            user_error = errors
            rec["stage"] = type(e).__name__
            rec["error"] = errors
            rec["trace"] = traceback.format_exc()[-800:]
            attempts.append(rec)
            print(f"    {rec['stage']}, {elapsed}s: {errors[:300]}", flush=True)
    return {"ok": False, "sid": sid, "scenario": scenario,
            "attempt": 3, "attempts": attempts, "error": user_error or errors}


def main():
    names = sys.argv[1:]
    todo = SCENARIOS
    if names:
        todo = [x for x in SCENARIOS if x[0] in names]
        if not todo:
            print("нет сценариев:", names)
            sys.exit(2)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(HERE, "live_runs", stamp)
    os.makedirs(out_dir, exist_ok=True)
    cfg = dict(CFG)
    print(f"модель {cfg['model']}  url {cfg['url']}")
    print(f"max_tokens={play.brief_max_tokens(cfg)}  каталог {out_dir}")
    results = []
    for sid, scenario in todo:
        print(f"\n── {sid}: {scenario}", flush=True)
        res = probe_one(out_dir, sid, scenario, cfg)
        results.append(res)
        print(f"  итог: {'ОК' if res['ok'] else 'ПРОВАЛ'}  попытка {res['attempt']}",
              flush=True)
    summary = {"cfg": cfg, "max_tokens": play.brief_max_tokens(cfg), "results": results}
    _write(os.path.join(out_dir, "summary.json"),
           json.dumps(summary, ensure_ascii=False, indent=1))
    ok_n = sum(1 for r in results if r["ok"])
    print(f"\nИТОГО {ok_n}/{len(results)} сценариев прошли")
    for r in results:
        mark = "ok" if r["ok"] else "FAIL"
        last = (r.get("attempts") or [{}])[-1]
        print(f"  {mark:4} {r['sid']:<12} stage={last.get('stage')} "
              f"попыток={r['attempt']}")
    sys.exit(0 if ok_n == len(results) else 1)


if __name__ == "__main__":
    main()
