#!/usr/bin/env python3
"""Quality-consistency audit across all battle-scenario YAML files.

Measures structural/quality dimensions per scenario and flags deviations and
known grading anti-patterns (see memory e2e-grading-harness lessons). This is a
measurement/linter for the human-review deliverable — NOT a battle runner.

Usage: python scripts/quality_audit.py [--json]
"""
import sys, glob, os, re, json, collections

DIR = os.path.join(os.path.dirname(__file__), "..", "contents", "battle-scenarios")
import yaml

# instruction sub-sections we expect in the gold structure
SECTION_PATS = {
    "상황": re.compile(r"###\s*상황"),
    "할일": re.compile(r"###\s*할\s*일"),
    "채점방법": re.compile(r"###\s*채점\s*방법"),
    "합격기준": re.compile(r"###\s*합격\s*기준"),
}

def track_of(fid):
    # group filename into a track key
    m = re.match(r"([a-z]+(?:-[a-z]+)*)-w\d+$", fid)
    if m: return m.group(1)
    return "legacy-misc"

def analyze_mission(m):
    instr = m.get("instruction", "") or ""
    secs = {k: bool(p.search(instr)) for k, p in SECTION_PATS.items()}
    v = m.get("verify", {}) or {}
    checks = v.get("checks", []) or []
    sem = v.get("semantic", {}) or {}
    # detect anti-pattern: generic suricata scan log_contains with no tag
    anti = []
    for c in checks:
        if not isinstance(c, dict): continue
        p = c.get("params", {}) or {}
        pat = str(p.get("pattern", ""))
        log = str(p.get("log", ""))
        ctype = c.get("type", "")
        if ctype == "log_contains" and log == "suricata" and pat.strip().lower() in ("scan", "nmap"):
            anti.append("generic-suricata-scan")
        if ctype == "log_contains" and pat and not re.search(r"\d|[A-Za-z]{4,}", pat):
            anti.append("weak-pattern")
    return {
        "order": m.get("order"),
        "assess_target": m.get("assess_target"),
        "target_vm": m.get("target_vm"),
        "points": m.get("points"),
        "instr_len": len(instr),
        "sections": secs,
        "sections_ok": all(secs.values()),
        "n_checks": len(checks),
        "has_semantic": bool(sem),
        "has_hint": bool(m.get("hint")),
        "verify_type": v.get("type"),
        "anti": anti,
    }

def analyze_file(path):
    fid = os.path.splitext(os.path.basename(path))[0]
    with open(path) as f:
        try:
            d = yaml.safe_load(f)
        except Exception as e:
            return {"id": fid, "error": f"YAML parse: {e}"}
    if not isinstance(d, dict):
        return {"id": fid, "error": "not a mapping"}
    red = d.get("red_missions", []) or []
    blue = d.get("blue_missions", []) or []
    rm = [analyze_mission(m) for m in red]
    bm = [analyze_mission(m) for m in blue]
    desc = d.get("description", "") or ""
    total_pts = sum((m.get("points") or 0) for m in red+blue)
    # marker presence: a per-week unique tag referenced in description
    has_tag = bool(re.search(r"태그\s*\*?\*?`?[a-z]{2,}\d{2}r\d", desc) or re.search(r"`[a-z]{2,}\d{2}r\d", desc))
    return {
        "id": fid,
        "track": track_of(fid),
        "category": d.get("category"),
        "difficulty": d.get("difficulty"),
        "time_limit": d.get("time_limit"),
        "battle_type": d.get("battle_type"),
        "title": d.get("title", ""),
        "desc_len": len(desc),
        "n_red": len(red), "n_blue": len(blue),
        "total_points": total_pts,
        "has_modes_doc": ("solo" in desc and "duel" in desc),
        "has_unique_tag_doc": has_tag,
        "red": rm, "blue": bm,
        "anti": sorted({a for m in rm+bm for a in m["anti"]}),
        "missing_sections": sum(0 if m["sections_ok"] else 1 for m in rm+bm),
        "missing_semantic": sum(0 if m["has_semantic"] else 1 for m in rm+bm),
    }

def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.yaml")))
    rows = [analyze_file(p) for p in files]
    rows = [r for r in rows if "error" not in r] + [r for r in rows if "error" in r]
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=2)); return

    by_track = collections.defaultdict(list)
    for r in rows:
        if "error" in r: continue
        by_track[r["track"]].append(r)

    print(f"=== {len(rows)} scenario files ===\n")
    print(f"{'track':18} {'n':>3} {'diff':22} {'mode':6} {'tlim':>5} {'red':>4} {'blue':>4} {'pts(min-max)':>14} {'tag%':>5} {'anti':>5} {'missSec':>7} {'missSem':>7}")
    for tr in sorted(by_track):
        g = by_track[tr]
        diffs = collections.Counter(r["difficulty"] for r in g)
        modes = collections.Counter(r["battle_type"] for r in g)
        tlims = sorted({r["time_limit"] for r in g})
        reds = sorted({r["n_red"] for r in g}); blues = sorted({r["n_blue"] for r in g})
        pts = [r["total_points"] for r in g]
        tagpct = round(100*sum(1 for r in g if r["has_unique_tag_doc"])/len(g))
        anti = sum(1 for r in g if r["anti"])
        missec = sum(r["missing_sections"] for r in g)
        missem = sum(r["missing_semantic"] for r in g)
        diff_s = ",".join(f"{k}:{v}" for k,v in diffs.items())
        mode_s = ",".join(f"{k}:{v}" for k,v in modes.items())
        print(f"{tr:18} {len(g):>3} {diff_s:22} {mode_s:6} {str(tlims):>5} {str(reds):>4} {str(blues):>4} {str(min(pts))+'-'+str(max(pts)):>14} {tagpct:>4}% {anti:>5} {missec:>7} {missem:>7}")

    print("\n=== Scenarios with anti-patterns (deprecated grading) ===")
    for r in rows:
        if r.get("anti"):
            print(f"  {r['id']:24} {r['anti']}")
    print("\n=== Scenarios missing instruction sections (상황/할일/채점방법/합격기준) ===")
    for r in rows:
        if "error" in r: continue
        if r["missing_sections"]:
            bad = [f"R{m['order']}" for m in r["red"] if not m["sections_ok"]] + \
                  [f"B{m['order']}" for m in r["blue"] if not m["sections_ok"]]
            print(f"  {r['id']:24} missing in {r['missing_sections']} missions: {bad}")
    print("\n=== Parse errors ===")
    for r in rows:
        if "error" in r: print(f"  {r['id']}: {r['error']}")

if __name__ == "__main__":
    main()
