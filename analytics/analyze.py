#!/usr/bin/env python3
"""
AlgebraBridge telemetry benchmarking.

Reads interaction logs exported by the app (JSON or Events CSV) or collected by
the Express server (server/data/telemetry.jsonl) and reports:

  * step_accuracy                 valid steps / attempted steps
  * latency_per_step_ms           time between consecutive steps (first from render)
  * error_classification          counts of each procedural error type
  * scaffolding_dependency_score  share of steps made on the visual scale

…per attempt, per learner, and broken down by the scaffolding level that was
active when each step was taken (the key check that performance holds as
support fades).

Metric definitions mirror src/telemetry/metrics.ts. Standard library only.

Usage:
    python3 analytics/analyze.py export.json [more files...] [--out summary.csv] [--json]
"""
import argparse
import csv
import json
import statistics
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

ERROR_TYPES = [
    "asymmetric_operation",
    "sign_error",
    "incorrect_division",
    "arithmetic_error",
    "invalid_transformation",
]
INT_FIELDS = ("t", "scaffoldLevel", "latencyFromRenderMs", "latencySincePrevMs")
BOOL_FIELDS = ("valid", "productive")


# --------------------------------------------------------------------------- #
# Loading                                                                      #
# --------------------------------------------------------------------------- #

def _coerce(e):
    """Normalise types so CSV rows look like JSON events."""
    out = {k: v for k, v in e.items() if v not in ("", None)}
    for k in INT_FIELDS:
        if k in out:
            try:
                out[k] = int(float(out[k]))
            except (TypeError, ValueError):
                del out[k]
    for k in BOOL_FIELDS:
        if k in out and isinstance(out[k], str):
            out[k] = out[k].strip().lower() == "true"
    return out


def load_events(path):
    p = Path(path)
    if p.suffix == ".csv":
        with p.open(newline="", encoding="utf-8") as f:
            return [_coerce(r) for r in csv.DictReader(f)]
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".jsonl":
        return [_coerce(json.loads(line)) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("events", [])
    return [_coerce(e) for e in data]


def dedupe(events):
    seen = OrderedDict()
    for e in events:
        seen.setdefault(e.get("id") or id(e), e)
    return sorted(seen.values(), key=lambda e: e.get("t", 0))


# --------------------------------------------------------------------------- #
# Metrics                                                                      #
# --------------------------------------------------------------------------- #

def is_step(e):
    return e.get("type") == "step" and e.get("reason") != "no_change"


def summarize_attempt(evs):
    start = next((e for e in evs if e.get("type") == "problem_start"), evs[0])
    steps = [e for e in evs if is_step(e)]
    valid = [s for s in steps if s.get("valid")]
    visual = [s for s in steps if s.get("source") == "visual"]
    latencies = [s.get("latencySincePrevMs", 0) for s in steps]
    errors = Counter(s["errorType"] for s in steps if s.get("errorType"))
    n = len(steps)
    return {
        "attemptId": evs[0].get("attemptId"),
        "learnerId": evs[0].get("learnerId"),
        "problemId": evs[0].get("problemId"),
        "equation": start.get("before", evs[0].get("problemId")),
        "solved": any(e.get("type") == "problem_complete" for e in evs),
        "durationMs": evs[-1].get("t", 0) - start.get("t", 0),
        "steps": n,
        "validSteps": len(valid),
        "step_accuracy": len(valid) / n if n else 0.0,
        "latency_per_step_ms": statistics.mean(latencies) if latencies else 0.0,
        "first_step_latency_ms": steps[0].get("latencyFromRenderMs") if steps else None,
        "scaffolding_dependency_score": len(visual) / n if n else 0.0,
        "hints": sum(1 for e in evs if e.get("type") == "hint"),
        "peeks": sum(1 for e in evs if e.get("type") == "peek"),
        "imbalanceEvents": sum(1 for e in evs if e.get("type") == "imbalance"),
        "levelStart": start.get("scaffoldLevel"),
        "levelEnd": evs[-1].get("scaffoldLevel"),
        **{"err_" + k: errors.get(k, 0) for k in ERROR_TYPES},
    }


def group_by(items, key):
    out = defaultdict(list)
    for it in items:
        out[it.get(key)].append(it)
    return out


def step_stats(steps):
    n = len(steps)
    lat = [s.get("latencySincePrevMs", 0) for s in steps]
    return {
        "steps": n,
        "accuracy": (sum(1 for s in steps if s.get("valid")) / n) if n else 0.0,
        "median_latency_ms": statistics.median(lat) if lat else 0.0,
        "mean_latency_ms": statistics.mean(lat) if lat else 0.0,
    }


def learner_report(events):
    steps = [e for e in events if is_step(e)]
    # Teacher overrides are not evidence about the learner, so they are excluded.
    changes = [e for e in events if e.get("type") == "scaffold_change" and e.get("reason") != "manual override"]
    fades = sum(1 for c in changes if _arrow(c)[1] > _arrow(c)[0])
    reinflations = sum(1 for c in changes if _arrow(c)[1] < _arrow(c)[0])
    errors = Counter(s["errorType"] for s in steps if s.get("errorType"))
    visual = sum(1 for s in steps if s.get("source") == "visual")
    return {
        **step_stats(steps),
        "dependency": visual / len(steps) if steps else 0.0,
        "fades": fades,
        "reinflations": reinflations,
        "errors": dict(errors),
        "by_level": {lvl: step_stats(ss) for lvl, ss in sorted(group_by(steps, "scaffoldLevel").items(), key=lambda kv: kv[0] or 0)},
        "by_source": {src: step_stats(ss) for src, ss in sorted(group_by(steps, "source").items(), key=lambda kv: kv[0] or "")},
    }


def _arrow(change):
    try:
        a, b = str(change.get("detail", "0->0")).split("->")
        return int(a), int(b)
    except ValueError:
        return 0, 0


# --------------------------------------------------------------------------- #
# Output                                                                       #
# --------------------------------------------------------------------------- #

def pct(x):
    return "{:5.1f}%".format(100 * x)


def print_report(events, attempts):
    print("=" * 72)
    print("AlgebraBridge telemetry report")
    print("  events: {}   attempts: {}   learners: {}".format(
        len(events), len(attempts), len({a['learnerId'] for a in attempts})))
    print("=" * 72)

    overall = learner_report(events)
    _print_block("ALL LEARNERS", overall, attempts)
    for learner, evs in sorted(group_by(events, "learnerId").items()):
        _print_block("Learner " + str(learner), learner_report(evs), [a for a in attempts if a["learnerId"] == learner])


def _print_block(title, r, attempts):
    solved = sum(1 for a in attempts if a["solved"])
    print("\n" + title)
    print("-" * len(title))
    print("  attempts solved           {}/{}".format(solved, len(attempts)))
    print("  step accuracy             {}  ({} steps)".format(pct(r["accuracy"]), r["steps"]))
    print("  latency/step  median      {:8.0f} ms   mean {:8.0f} ms".format(r["median_latency_ms"], r["mean_latency_ms"]))
    print("  scaffolding dependency    {:.2f}".format(r["dependency"]))
    print("  fades / re-inflations     {} / {}".format(r["fades"], r["reinflations"]))
    if r["errors"]:
        print("  errors:")
        for k in ERROR_TYPES:
            if r["errors"].get(k):
                print("    {:<26}{:>4}".format(k, r["errors"][k]))
    if r["by_level"]:
        print("  by scaffolding level at time of step:")
        print("    level   steps   accuracy   median latency")
        for lvl, s in r["by_level"].items():
            print("    L{:<6}{:>5}   {}   {:>10.0f} ms".format(lvl, s["steps"], pct(s["accuracy"]), s["median_latency_ms"]))
    if r["by_source"]:
        print("  by input channel:")
        for src, s in r["by_source"].items():
            print("    {:<18}{:>5} steps  {} accuracy".format(src, s["steps"], pct(s["accuracy"])))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help=".json export, events .csv, or server .jsonl")
    ap.add_argument("--out", help="write per-attempt summary CSV here")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON instead of the text report")
    args = ap.parse_args(argv)

    events = dedupe([e for f in args.files for e in load_events(f)])
    if not events:
        print("No events found.", file=sys.stderr)
        return 1
    attempts = [summarize_attempt(evs) for evs in group_by(events, "attemptId").values()]

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(attempts[0].keys()))
            w.writeheader()
            w.writerows(attempts)
        print("Wrote {} attempt rows to {}".format(len(attempts), args.out), file=sys.stderr)

    if args.json:
        json.dump({
            "overall": learner_report(events),
            "learners": {str(k): learner_report(v) for k, v in group_by(events, "learnerId").items()},
            "attempts": attempts,
        }, sys.stdout, indent=2, default=str)
        print()
    else:
        print_report(events, attempts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
