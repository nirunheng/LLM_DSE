#!/usr/bin/env python3
"""最忠实的 ATLAS 单次运行：输入芯片YAML + 算子YAML + 张量摆放YAML，输出延迟/能耗。

用法:
    python3 run_atlas_once.py <chip.yaml> <operator.yaml> <data.yaml> [log_path] [--json]
"""
import sys
import json
import atlasim


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    if len(args) < 3:
        print(__doc__)
        return 2

    chip_cfg, op_yaml, data_yaml = args[0], args[1], args[2]
    log_path = args[3] if len(args) > 3 else "/tmp/atlas_run.log"

    chip = atlasim.Chip(chip_cfg, op_yaml, data_yaml, log_path)
    perf = chip.simulate()

    e = perf.e2e_stats
    freq_mhz = perf.chip_frequency
    cycle_s = 1.0 / (freq_mhz * 1e6)
    result = {
        "chip_config": chip_cfg,
        "operator_yaml": op_yaml,
        "placement_yaml": data_yaml,
        "frequency_MHz": freq_mhz,
        "core_num": len(perf.core_stats),
        "e2e_cycles": e.e2e_cycles,
        "latency_s": e.e2e_cycles * cycle_s,
        "e2e_energy_J": e.e2e_energy,
        "matrix_cycles": e.matrix_cycles,
        "vector_cycles": e.vector_cycles,
        "buffer_cycles": e.buffer_cycles,
        "dram_cycles": e.dram_cycles,
        "noc_cycles": e.noc_cycles,
        "energy_breakdown_J": {
            "controller": e.controller_energy,
            "matrix": e.matrix_energy,
            "vector": e.vector_energy,
            "buffer": e.buffer_energy,
            "dram": e.dram_energy,
            "noc": e.noc_energy,
        },
        "flop_count": e.flop_count,
        "memory_access_bytes": e.memory_access_bytes,
        "arithmetic_intensity": e.arithmetic_intensity(),
        "matrix_util": e.matrix_util(),
        "dram_util": e.dram_util(),
        "noc_util": e.noc_util(),
        "compute_non_overlap_ratio": e.compute_non_overlap_ratio(),
        "matrix_bubble_on_chip_cycles": e.matrix_bubble_on_chip_cycles,
        "matrix_bubble_dram_cycles": e.matrix_bubble_dram_cycles,
        "num_operators": len(perf.operator_stats),
        "operator_names": [name for name, _ in perf.operator_stats],
    }

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"e2e_cycles      = {result['e2e_cycles']}")
        print(f"latency_s       = {result['latency_s']:.6e}")
        print(f"e2e_energy_J    = {result['e2e_energy_J']:.6e}")
        print(f"matrix_util     = {result['matrix_util']:.4f}")
        print(f"dram_util       = {result['dram_util']:.4f}")
        print(f"log             = {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
