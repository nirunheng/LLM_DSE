#!/usr/bin/env python3
"""从 Beacon/Compass 的 DSE run 目录中提取每轮硬件结构 + 逐算子/逐core 指标。

用法:
    python3 extract_dse_report.py <run_dir> [--iter N] [--out DIR]
"""
import argparse
import json
from pathlib import Path


def load(p):
    p = Path(p)
    if not p.exists():
        return None
    return json.load(open(p, encoding="utf-8"))


def hardware_summary(hw):
    chips = hw.get("chiplets", [])
    def uniq(key):
        vals = {}
        for c in chips:
            vals[str(c.get(key))] = vals.get(str(c.get(key)), 0) + 1
        return vals
    return {
        "num_chiplets": hw.get("num_chiplets"),
        "chip_x": hw.get("chip_x"), "chip_y": hw.get("chip_y"),
        "compute_units": uniq("compute_units"),
        "buffer_size": uniq("buffer_size"),
        "chiplet_type": uniq("type"),
        "macs": uniq("macs"),
        "dram_bw": hw.get("dram_bw"), "nop_bw": hw.get("nop_bw"),
        "micro_batch": hw.get("micro_batch"),
        "tensor_parall": hw.get("tensor_parall"),
    }


def iter_metrics(run_dir, it):
    """优先用 tuning_metrics.json 里的 iteration_metrics（含 mc/objective）。"""
    tm = load(run_dir / "tuning_metrics.json") or {}
    for row in tm.get("rows", []):
        if int(row.get("iteration", -1)) == it:
            return row
    # 回退：解析 exec_res.csv 第一行
    csv = run_dir / f"iter_{it:03d}" / "exec_res.csv"
    if csv.exists():
        lines = csv.read_text().strip().splitlines()
        head, first = lines[0].split(","), lines[1].split(",")
        return dict(zip(head, [float(x) for x in first if x != ""]))
    return {}


def per_core_stats(run_dir, it):
    d = run_dir / f"iter_{it:03d}"
    lat = load(d / "exec_latency_detail.json")
    en = load(d / "exec_energy_detail.json")
    if lat is None:
        return []
    out = []
    for core in sorted(lat, key=lambda c: int("".join(ch for ch in c if ch.isdigit()))):
        entries_l = lat[core]
        entries_e = (en or {}).get(core, [])
        out.append({
            "core": core,
            "busy_span": max(e["latencyEnd"] for e in entries_l),
            "num_layers": len(entries_l),
            "calc_time": sum(e.get("calcTime", 0) for e in entries_l),
            "noc_time": sum(e.get("nocTime", 0) for e in entries_l),
            "dram_time": sum(e.get("dramTime", 0) for e in entries_l),
            "energy": sum(e.get("energy", 0) for e in entries_e),
            "calc_energy": sum(e.get("calcEnergy", 0) for e in entries_e),
            "noc_energy": sum(e.get("nocEnergy", 0) for e in entries_e),
            "dram_energy": sum(e.get("dramEnergy", 0) for e in entries_e),
            "ubuf_energy": sum(e.get("ubufEnergy", 0) for e in entries_e),
        })
    return out


def per_layer_table(run_dir, it):
    p = run_dir / f"iter_{it:03d}" / "analysis" / "layer_loads.json"
    d = load(p)
    if not d:
        return None, None
    return d.get("layer_loads", []), d.get("metrics", {})


def per_group_table(run_dir, it):
    p = run_dir / f"iter_{it:03d}" / "analysis" / "operator_group_summary.json"
    return load(p)


def area_costs(run_dir, it):
    return load(run_dir / f"iter_{it:03d}" / "exec_mc_detail.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--iter", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    iters = sorted({int(p.name.split("_")[1]) for p in run_dir.glob("iter_*")
                    if p.name.split("_")[1].isdigit()})
    if args.iter is not None:
        iters = [args.iter]

    report = {"run_dir": str(run_dir), "iterations": []}
    for it in iters:
        d = run_dir / f"iter_{it:03d}"
        entry = {
            "iteration": it,
            "hardware": hardware_summary(load(d / "hardware.json") or {}),
            "metrics": iter_metrics(run_dir, it),
            "area_and_cost": area_costs(run_dir, it),
            "per_core": per_core_stats(run_dir, it),
        }
        layers, base = per_layer_table(run_dir, it)
        if layers is not None:
            entry["layer_analysis_base"] = base
            entry["top_layers_by_energy"] = sorted(
                layers, key=lambda x: -x.get("energy", 0))[:10]
            entry["top_layers_by_latency"] = sorted(
                layers, key=lambda x: -x.get("latency_sum", 0))[:10]
        entry["operator_groups"] = per_group_table(run_dir, it)
        entry["has_layer_analysis"] = layers is not None
        report["iterations"].append(entry)

    text = json.dumps(report, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
