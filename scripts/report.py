#!/usr/bin/env python3
"""Generate human-readable Markdown reports for a LibreLane run.

Usage: report.py <design_dir | run_dir> [--variant VARIANT]

Given a design directory, the most recent run under <design_dir>/runs is used
(only runs tagged <VARIANT>_* if --variant is given).
One file per report is written to <run_dir>/reports/, mirroring Genus:

    qor.md     overall quality of results
    area.md    area breakdown (sequential / combinational)
    gates.md   instances and area per cell type
    timing.md  per-corner summary + critical setup/hold paths   (needs STA)
    power.md   power breakdown per corner                       (needs STA)
"""
import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------- helpers

def find_run(path: Path, variant=None) -> Path:
    if (path / "resolved.json").exists():
        return path
    runs = sorted(
        (path / "runs").glob(f"{variant}_*/resolved.json" if variant else "*/resolved.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not runs:
        sys.exit(f"error: no {variant + ' ' if variant else ''}runs found under {path}")
    return runs[-1].parent


def step_dir(run: Path, name: str):
    """Return the (last) step directory whose name ends with `name`."""
    dirs = sorted(d for d in run.iterdir() if d.is_dir() and d.name.endswith(name))
    return dirs[-1] if dirs else None


def table(headers, rows, align=None):
    """Markdown table with columns padded so every '|' lines up."""
    align = align or ["l"] + ["r"] * (len(headers) - 1)
    cells = [[str(c) for c in headers]] + [[str(c) for c in r] for r in rows]
    widths = [max(3, *(len(r[i]) for r in cells)) for i in range(len(headers))]

    def line(r):
        return "| " + " | ".join(
            c.rjust(w) if a == "r" else c.ljust(w) for c, w, a in zip(r, widths, align)
        ) + " |"

    sep = "| " + " | ".join(
        "-" * (w - 1) + ":" if a == "r" else ":" + "-" * (w - 1) for w, a in zip(widths, align)
    ) + " |"
    return "\n".join([line(cells[0]), sep] + [line(r) for r in cells[1:]])


def fmt(v, nd=3):
    if isinstance(v, (int, float)):
        return "inf" if v == float("inf") else f"{v:.{nd}f}"
    return str(v) if v is not None else "-"


def code(text):
    return "```\n" + text.rstrip() + "\n```"


# ---------------------------------------------------------------- parsers

def lib_for_corner(libs, corner):
    """Pick the Liberty files whose corner wildcard matches `corner`."""
    return next((v for k, v in (libs or {}).items()
                 if re.fullmatch(k.replace("*", ".*"), corner)), [])


def liberty_areas(cfg):
    """Cell name -> area, from the default corner's std-cell and macro Liberty files."""
    corner = cfg.get("DEFAULT_CORNER", "")
    libs = list(lib_for_corner(cfg.get("LIB"), corner))
    for macro in (cfg.get("MACROS") or {}).values():
        libs += lib_for_corner(macro.get("lib"), corner)
    areas = {}
    for lib in libs:
        chunks = re.split(r'^\s*cell\s*\(\s*"?([\w$]+)"?\s*\)\s*\{', Path(lib).read_text(), flags=re.M)
        for name, body in zip(chunks[1::2], chunks[2::2]):
            if m := re.search(r"^\s*area\s*:\s*([\d.]+)", body, re.M):
                areas[name] = float(m[1])
    return areas


def parse_stat(path: Path, cfg):
    """Parse Yosys stat.json: per-cell counts/areas, std-cell and macro area.

    stat.rpt prints large areas with 2-3 significant digits, so areas per cell
    type are computed as count x unit area from the Liberty files instead.
    Yosys leaves macros (black boxes) out of its area, so they are added here.
    """
    top = json.loads(path.read_text())["design"]
    areas = liberty_areas(cfg)
    macro_names = set(cfg.get("MACROS") or {})
    cells = [(name, n, n * areas[name] if name in areas else float("nan"))
             for name, n in top.get("num_cells_by_type", {}).items()]
    macros = [c for c in cells if c[0] in macro_names]
    std = top.get("area") or 0.0
    macro_area = sum(c[2] for c in macros)
    return {
        "cells": sorted(cells, key=lambda c: (-c[2], c[0])),
        "std": std,
        "seq": top.get("sequential_area"),
        "macro_count": sum(c[1] for c in macros),
        "macro": macro_area,
        "total": std + macro_area,
    }


def first_path(path: Path):
    """Return the first (worst) timing path of an OpenSTA report_checks file."""
    m = re.search(r"^Startpoint:.*?slack \((?:MET|VIOLATED)\)", path.read_text(), re.M | re.S)
    return m[0] if m else None


def parse_power(path: Path):
    """Return (table text, total watts) from an OpenSTA report_power file."""
    text = path.read_text()
    body = re.search(r"^Group.*?^\s+[\d.]+%.*?$", text, re.M | re.S)
    total = re.search(r"^Total\s+\S+\s+\S+\s+\S+\s+(\S+)", text, re.M)
    return (body[0] if body else text.strip()), (float(total[1]) if total else None)


# ---------------------------------------------------------------- reports

class Run:
    def __init__(self, path: Path):
        self.path = path
        self.cfg = json.loads((path / "resolved.json").read_text())
        mf = path / "final" / "metrics.json"
        self.metrics = json.loads(mf.read_text()) if mf.exists() else {}

        synth = step_dir(path, "yosys-synthesis")
        stat_file = synth / "reports" / "stat.json" if synth else None
        self.stat = parse_stat(stat_file, self.cfg) if stat_file and stat_file.exists() else None

        self.sta = step_dir(path, "openroad-staprepnr")
        self.corners = sorted(
            d.name for d in self.sta.iterdir() if d.is_dir() and (d / "max.rpt").exists()
        ) if self.sta else []
        self.typ = next((c for c in self.corners if "_tt_" in c), self.corners[0] if self.corners else None)

    def m(self, key, corner=None):
        return self.metrics.get(f"{key}__corner:{corner}" if corner else key)

    def worst_corner(self, key):
        vals = [(self.m(key, c), c) for c in self.corners if self.m(key, c) is not None]
        return min(vals)[1] if vals else None

    def header(self, title):
        period = self.cfg.get("CLOCK_PERIOD")
        return "\n".join([
            f"# {title}: `{self.cfg['DESIGN_NAME']}`",
            "",
            table(["Item", "Value"], [
                ["Run", self.path.name],
                ["PDK", self.cfg.get("PDK")],
                ["Std cell library", self.cfg.get("STD_CELL_LIBRARY")],
                ["Clock", f"{self.cfg.get('CLOCK_PORT')} @ {period} ns ({1000 / period:.1f} MHz)"
                 if period else "-"],
            ], ["l", "l"]),
            "",
        ])

    # -- individual reports -------------------------------------------------

    def qor(self):
        m = self.m
        rows = [
            ["Cell count", m("design__instance__count") or "-"],
        ]
        if self.stat:
            rows += [
                ["Std-cell area (µm²)", fmt(self.stat["std"])],
                ["Macro count", self.stat["macro_count"]],
                ["Macro area (µm²)", fmt(self.stat["macro"])],
                ["Total area (µm²)", fmt(self.stat["total"])],
            ]
        rows += [
            ["Inferred latches", m("design__inferred_latch__count")],
            ["Unmapped cells", m("design__instance_unmapped__count")],
            ["Lint errors", m("design__lint_error__count")],
            ["Lint warnings", m("design__lint_warning__count")],
        ]
        if self.sta:
            rows += [
                ["Worst setup slack (ns)", fmt(m("timing__setup__ws"))],
                ["Setup TNS (ns)", fmt(m("timing__setup__tns"))],
                ["Setup violations", m("timing__setup_vio__count")],
                ["Worst hold slack (ns)", fmt(m("timing__hold__ws"))],
                ["Hold TNS (ns)", fmt(m("timing__hold__tns"))],
                ["Hold violations", m("timing__hold_vio__count")],
                ["Max slew violations", m("design__max_slew_violation__count")],
                ["Max cap violations", m("design__max_cap_violation__count")],
                ["Max fanout violations", m("design__max_fanout_violation__count")],
            ]
            if self.typ:
                _, total = parse_power(self.sta / self.typ / "power.rpt")
                rows.append([f"Total power @ {self.typ} (mW)", fmt(total * 1e3, 4) if total else "-"])
        else:
            rows.append(["Timing / power", "not run (use `make sta`)"])
        rows = [[k, "-" if v is None else v] for k, v in rows]
        return self.header("QoR report") + "\n" + table(["Metric", "Value"], rows)

    def area(self):
        if not self.stat:
            return None
        st = self.stat
        total = st["total"]

        def row(name, a):
            return [name, f"{a:.3f}", f"{100 * a / total:.1f}%"]

        rows = []
        if st["seq"] is not None:
            rows += [row("Sequential", st["seq"]), row("Combinational", st["std"] - st["seq"])]
        rows += [row("Std cells", st["std"])]
        if st["macro_count"]:
            rows += [row(f"Macros ({st['macro_count']})", st["macro"])]
        rows += [row("Total", total)]
        return self.header("Area report") + "\n" + table(["Type", "Area (µm²)", "% area"], rows)

    def gates(self):
        if not self.stat:
            return None
        total = self.stat["total"]
        rows = [[name, n, f"{a:.3f}", f"{100 * a / total:.1f}%"] for name, n, a in self.stat["cells"]]
        rows.append(["Total", sum(c[1] for c in self.stat["cells"]), f"{total:.3f}", "100.0%"])
        return self.header("Gates report") + "\n" + table(
            ["Cell", "Instances", "Area (µm²)", "% area"], rows)

    def timing(self):
        if not self.sta:
            return None
        rows = [[
            c,
            fmt(self.m("timing__setup__ws", c)), fmt(self.m("timing__setup__tns", c)),
            self.m("timing__setup_vio__count", c),
            fmt(self.m("timing__hold__ws", c)), fmt(self.m("timing__hold__tns", c)),
            self.m("timing__hold_vio__count", c),
        ] for c in self.corners]
        out = [
            self.header("Timing report"),
            "Pre-PnR STA: ideal clocks, no wire parasitics. Slack/TNS in ns.",
            "",
            table(["Corner", "Setup WS", "Setup TNS", "Setup vio",
                   "Hold WS", "Hold TNS", "Hold vio"], rows),
        ]
        for kind, key, rpt in (("setup", "timing__setup__ws", "max.rpt"),
                               ("hold", "timing__hold__ws", "min.rpt")):
            c = self.worst_corner(key)
            p = first_path(self.sta / c / rpt) if c else None
            if p:
                out += ["", f"## Critical {kind} path (corner `{c}`)", "", code(p)]
        return "\n".join(out)

    def power(self):
        if not self.sta:
            return None
        order = [self.typ] + [c for c in self.corners if c != self.typ]
        rows, sections = [], []
        for c in order:
            body, total = parse_power(self.sta / c / "power.rpt")
            rows.append([c, fmt(total * 1e3, 4) if total else "-"])
            sections += ["", f"## Corner `{c}`", "", code(body)]
        return "\n".join([self.header("Power report"), table(["Corner", "Total (mW)"], rows)] + sections)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", type=Path, help="design directory or run directory")
    ap.add_argument("--variant", help="only consider runs of this variant")
    args = ap.parse_args()

    run = Run(find_run(args.path, args.variant))
    outdir = run.path / "reports"
    outdir.mkdir(exist_ok=True)

    for name in ("qor", "area", "gates", "timing", "power"):
        text = getattr(run, name)()
        dest = outdir / f"{name}.md"
        if text is None:
            dest.unlink(missing_ok=True)
            continue
        dest.write_text(text + "\n")
        print(f"wrote {dest}")

    print()
    print((outdir / "qor.md").read_text())


if __name__ == "__main__":
    main()
