#!/usr/bin/env python3
"""Compare the latest run of each variant of a design side by side.

Usage: compare.py <design_dir>

Variants are the overlays in <design_dir>/variants/*.json; for each one the
most recent run tagged <variant>_* is used. The comparison is written to
<design_dir>/runs/compare.md (and printed to stdout).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from report import Run, find_run, fmt, parse_power, table  # noqa: E402


def metrics(run: Run):
    """Ordered (label, value) pairs for one run; None if not available."""
    st, m = run.stat or {}, run.m
    rows = [
        ("Run", run.path.name),
        ("Std cell library", run.cfg.get("STD_CELL_LIBRARY")),
        ("Clock period (ns)", run.cfg.get("CLOCK_PERIOD")),
        ("Cell count", m("design__instance__count")),
        ("Std-cell area (µm²)", fmt(st.get("std"))),
        ("  sequential (µm²)", fmt(st.get("seq"))),
        ("Macro count", st.get("macro_count")),
        ("Macro area (µm²)", fmt(st.get("macro"))),
        ("Total area (µm²)", fmt(st.get("total"))),
    ]
    if run.sta:
        rows += [("Worst setup slack (ns)", fmt(m("timing__setup__ws"))),
                 ("Setup TNS (ns)", fmt(m("timing__setup__tns"))),
                 ("Setup violations", m("timing__setup_vio__count"))]
        rows += [(f"  setup WS {c} (ns)", fmt(m("timing__setup__ws", c))) for c in run.corners]
        rows += [("Worst hold slack (ns)", fmt(m("timing__hold__ws"))),
                 ("Hold violations", m("timing__hold_vio__count")),
                 ("Max slew violations", m("design__max_slew_violation__count")),
                 ("Max cap violations", m("design__max_cap_violation__count"))]
        rows += [(f"Power {c} (mW)", fmt((parse_power(run.sta / c / "power.rpt")[1] or 0) * 1e3, 4))
                 for c in run.corners]
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("design", type=Path, help="design directory")
    args = ap.parse_args()

    variants = sorted(p.stem for p in (args.design / "variants").glob("*.json"))
    runs = {}
    for v in variants:
        try:
            runs[v] = Run(find_run(args.design, v))
        except SystemExit:
            print(f"warning: no runs for variant '{v}', skipping", file=sys.stderr)
    if not runs:
        sys.exit("error: no variant runs to compare")

    # Union of metric labels, in first-seen order (corners can differ).
    per_run = {v: dict(metrics(r)) for v, r in runs.items()}
    labels = list(dict.fromkeys(k for v in runs for k, _ in metrics(runs[v])))
    rows = [[k] + [("-" if per_run[v].get(k) is None else per_run[v][k]) for v in runs]
            for k in labels]

    design = next(iter(runs.values())).cfg["DESIGN_NAME"]
    text = "\n".join([
        f"# Variant comparison: `{design}`",
        "",
        table(["Metric"] + list(runs), rows),
        "",
    ])
    dest = args.design / "runs" / "compare.md"
    dest.write_text(text)
    print(text)
    print(f"Comparison written to {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
