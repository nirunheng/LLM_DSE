#!/usr/bin/env python3
"""把 ATLAS 单算子仿真的每核细节导出成 Compass 风格 JSON。

用法:
    python3 dump_atlas_report.py <chip.yaml> <operator.yaml> <data.yaml> <out_prefix>

输出:
    <out_prefix>_energy_detail.json   # {core0: [{layerID, layerName, energy, calcEnergy, ...}], ...}
    <out_prefix>_latency_detail.json  # {core0: [{layerID, layerName, latencyBegin, latencyEnd, ...}], ...}
    <out_prefix>_summary.json         # 全局汇总
"""
import json
import sys
from pathlib import Path

import atlasim


def stats_to_dict(s: "atlasim.Stats", freq_mhz: float) -> dict:
    cycle_s = 1.0 / (freq_mhz * 1e6)
    return {
        "e2e_cycles": s.e2e_cycles,
        "e2e_latency_s": s.e2e_cycles * cycle_s,
        "matrix_cycles": s.matrix_cycles,
        "vector_cycles": s.vector_cycles,
        "buffer_cycles": s.buffer_cycles,
        "dram_cycles": s.dram_cycles,
        "noc_cycles": s.noc_cycles,
        "e2e_energy_J": s.e2e_energy,
        "controller_energy_J": s.controller_energy,
        "matrix_energy_J": s.matrix_energy,
        "vector_energy_J": s.vector_energy,
        "buffer_energy_J": s.buffer_energy,
        "dram_energy_J": s.dram_energy,
        "noc_energy_J": s.noc_energy,
        "flop_count": s.flop_count,
        "memory_access_bytes": s.memory_access_bytes,
        "arithmetic_intensity": s.arithmetic_intensity(),
        "matrix_util": s.matrix_util(),
        "vector_util": s.vector_util(),
        "buffer_util": s.buffer_util(),
        "dram_util": s.dram_util(),
        "noc_util": s.noc_util(),
        "compute_non_overlap_ratio": s.compute_non_overlap_ratio(),
        "matrix_bubble_on_chip_cycles": s.matrix_bubble_on_chip_cycles,
        "matrix_bubble_dram_cycles": s.matrix_bubble_dram_cycles,
    }


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    chip_cfg, op_yaml, data_yaml, out_prefix = sys.argv[1:5]
    log_path = f"{out_prefix}.log"

    chip = atlasim.Chip(chip_cfg, op_yaml, data_yaml, log_path)
    perf = chip.simulate()

    freq_mhz = float(perf.chip_frequency)
    cycle_s = 1.0 / (freq_mhz * 1e6)

    # ---- 全局汇总 ----
    summary = {
        "chip_config": chip_cfg,
        "operator_yaml": op_yaml,
        "placement_yaml": data_yaml,
        "frequency_MHz": freq_mhz,
        "core_num": len(perf.core_stats),
        "e2e": stats_to_dict(perf.e2e_stats, freq_mhz),
        "operators": [name for name, _ in perf.operator_stats],
    }

    # ---- 每核聚合（所有算子累加）----
    energy_detail = {}
    latency_detail = {}
    for core_id, st in enumerate(perf.core_stats):
        d = stats_to_dict(st, freq_mhz)
        latency_detail[f"core{core_id}"] = [{
            "batchID": 0,
            "layerID": 0,
            "layerName": "ALL_OPERATORS",
            "latencyBegin": 0,
            "latencyEnd": int(round(d["e2e_latency_s"] * 1e9)),
            "calcTime": int(round(d["matrix_cycles"] * cycle_s * 1e9)),
            "nocTime": int(round(d["noc_cycles"] * cycle_s * 1e9)),
            "dramTime": int(round(d["dram_cycles"] * cycle_s * 1e9)),
            "matrix_util": d["matrix_util"],
            "dram_util": d["dram_util"],
            "flop_count": d["flop_count"],
            "arithmetic_intensity": d["arithmetic_intensity"],
        }]
        energy_detail[f"core{core_id}"] = [{
            "batchID": 0,
            "layerID": 0,
            "layerName": "ALL_OPERATORS",
            "energy": d["e2e_energy_J"],
            "calcEnergy": d["matrix_energy_J"] + d["vector_energy_J"],
            "matrixEnergy": d["matrix_energy_J"],
            "vectorEnergy": d["vector_energy_J"],
            "ubufEnergy": d["buffer_energy_J"],
            "nocEnergy": d["noc_energy_J"],
            "dramEnergy": d["dram_energy_J"],
            "controllerEnergy": d["controller_energy_J"],
        }]

    # ---- 每核每算子明细 ----
    per_core_per_op = {}
    for op_name, stats_list in perf.operator_stats_per_core:
        for core_id, st in enumerate(stats_list):
            d = stats_to_dict(st, freq_mhz)
            per_core_per_op.setdefault(f"core{core_id}", []).append({
                "operator": op_name,
                "latency_s": d["e2e_latency_s"],
                "energy_J": d["e2e_energy_J"],
                "matrix_cycles": d["matrix_cycles"],
                "dram_cycles": d["dram_cycles"],
                "flop_count": d["flop_count"],
                "matrix_util": d["matrix_util"],
                "dram_util": d["dram_util"],
            })

    out_prefix_path = Path(out_prefix)
    out_prefix_path.parent.mkdir(parents=True, exist_ok=True)
    with open(f"{out_prefix}_energy_detail.json", "w") as f:
        json.dump(energy_detail, f, indent=2)
    with open(f"{out_prefix}_latency_detail.json", "w") as f:
        json.dump(latency_detail, f, indent=2)
    with open(f"{out_prefix}_summary.json", "w") as f:
        json.dump({"summary": summary, "per_core_per_operator": per_core_per_op}, f, indent=2)

    print(f"latency_s    = {summary['e2e']['e2e_latency_s']:.6e}")
    print(f"energy_J     = {summary['e2e']['e2e_energy_J']:.6e}")
    print(f"cores        = {summary['core_num']}")
    print(f"operators    = {summary['operators']}")
    print(f"written      = {out_prefix}_{{energy_detail,latency_detail,summary}}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
