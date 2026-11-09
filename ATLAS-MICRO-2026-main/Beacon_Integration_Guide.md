# ATLAS 替换 Compass 接入 Beacon 操作指南

## 概述

本文档指导你在**不修改 Beacon 原有架构**的前提下，将 ATLAS（3D-DRAM 周期级仿真器）替换 Compass 作为 DSE 后端。替换后：
- `--simulator compass` 仍可用原 Compass
- `--simulator atlas` 使用 ATLAS
- 输出格式与原有 `EvaluationResult` 兼容，Agent 可继续分析

---

## 修改清单（总览）

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `chiplet_tuner/core/search_space.py` | 修改 | 替换搜索空间为 ATLAS 原语 |
| 2 | `chiplet_tuner/simulators/atlas_simulator.py` | **新建** | ATLAS 适配器（核心） |
| 3 | `chiplet_tuner/simulators/run_atlas.py` | **新建** | 命令行包装脚本 |
| 4 | `chiplet_tuner/simulators/__init__.py` | 修改 | 导出新类 |
| 5 | `chiplet_tuner/simulators/atlas_config.py` | **新建** | workload 配置模板 |
| 6 | `chiplet_tuner/cli.py` | 修改 | 添加 `--simulator atlas` 分支 |
| 7 | `chiplet_tuner/tools/analysis_tools.py` | 修改 | 适配 ATLAS 无 mc 明细 |
| 8 | `chiplet_tuner/pipeline/langgraph_tuner.py` | 修改（可选） | 目标函数 mc 默认 1.0 |

---

## 第 1 步：修改搜索空间

**文件：** `chiplet_tuner/core/search_space.py`

**为什么：** 原搜索空间搜索 Compass 的参数（`compute_units` / `nop_bw` 等）。ATLAS 的硬件参数不同：核心是 `mac_num`（MAC 数）、`vec_num`（向量单元数）、`buffer_size`（SRAM KB）、`buffer_read_bw` / `buffer_write_bw`（Byte/cycle）、`core_num`（核心数）、`frequency`（MHz）、`dram_config_path`（Ramulator 配置路径）。需要替换为 ATLAS 原语。

### 1.1 修改候选值（第 8–28 行）

**修改前（第 8–10 行）：**
```python
COMPUTE_UNIT_CANDIDATES = [1024, 4096, 16384]
BUFFER_SIZE_CANDIDATES = [2048, 8192, 32768]
CHIPLET_TYPE_CANDIDATES = ["ws", "os"]
```

**修改后：**
```python
# ATLAS 搜索空间候选值
MAC_NUM_CANDIDATES = [2048, 4096, 8192, 16384]
VEC_NUM_CANDIDATES = [128, 256, 512, 1024]
BUFFER_SIZE_CANDIDATES = [1024, 2048, 3072, 4096]       # KB
BUFFER_BW_CANDIDATES = [4096, 8192, 16384]               # Byte/cycle
CORE_NUM_CANDIDATES = [4, 8, 16, 32]
FREQUENCY_CANDIDATES = [500, 1000, 1500]                 # MHz
```

### 1.2 删除 Chiplet 类型和布局（第 12–28 行）

**修改前（第 12–28 行）：**
```python
DEFAULT_ARRAY_SHAPES: List[Tuple[int, int]] = [
    (1, 1),
    (2, 1),
    ...
]
MACS_BY_COMPUTE_UNITS: Dict[int, Dict[str, str]] = {
    1024: {"ws": "[4,4,8,8]", "os": "[4,4,8,8]"},
    ...
}
```

**修改后：** 整体删除 `DEFAULT_ARRAY_SHAPES` 和 `MACS_BY_COMPUTE_UNITS`。

> 注意：`DEFAULT_ARRAY_SHAPES` 被多个工具函数引用（`array_shape_candidates`、`step_array_shape` 等），需要谨慎处理。保留这些函数但让它们返回空列表，DSE 流程中不会调用它们。

### 1.3 修改系统参数搜索空间（第 38–43 行）

**修改前：**
```python
SYSTEM_PARAM_SEARCH_SPACE = {
    "dram_bw": [16, 32, 64, 128, 256],
    "nop_bw": [32, 64, 128, 256, 512],
    "micro_batch": TASK_MICRO_BATCH_OPTIONS["decode"],
    "tensor_parall": [4, 8, 16, 32, 64],
}
```

**修改后：**
```python
SYSTEM_PARAM_SEARCH_SPACE = {
    "dram_config_path": [
        "configs/architecture/dram/cloud/cloud_0.25TBps.yaml",
        "configs/architecture/dram/cloud/cloud_0.5TBps.yaml",
        "configs/architecture/dram/cloud/cloud_1TBps.yaml",
        "configs/architecture/dram/cloud/cloud_2TBps.yaml",
        "configs/architecture/dram/cloud/cloud_4TBps.yaml",
    ],
    # power / area 固定不搜索，保留占位
}
```

### 1.4 修改 `DEFAULT_HARDWARE_SEARCH_SPACE`（第 45–82 行）

**修改前（第 45–82 行）：**
```python
DEFAULT_HARDWARE_SEARCH_SPACE: Dict[str, Any] = {
    "design_space_kind": "explicit_count_per_chiplet",
    "compute_scale": None,
    "array_shapes": [list(shape) for shape in DEFAULT_ARRAY_SHAPES],
    "num_chiplet_candidates": [h * w for h, w in DEFAULT_ARRAY_SHAPES],
    "compute_unit_candidates": COMPUTE_UNIT_CANDIDATES,
    "buffer_size_candidates": BUFFER_SIZE_CANDIDATES,
    "chiplet_type_candidates": CHIPLET_TYPE_CANDIDATES,
    "macs_by_compute_units": MACS_BY_COMPUTE_UNITS,
    "system_params": SYSTEM_PARAM_SEARCH_SPACE,
    "tunable_categories": {
        "chiplet_count": {
            "parameters": ["num_chiplets"],
            "description": "...",
        },
        "per_chiplet_architecture": {
            "parameters": ["compute_units", "buffer_size", "chiplet_type"],
            "description": "...",
        },
        "system_params": {
            "parameters": ["dram_bw", "nop_bw", "micro_batch", "tensor_parall"],
        },
    },
    "dram_bw": SYSTEM_PARAM_SEARCH_SPACE["dram_bw"],
    "nop_bw": SYSTEM_PARAM_SEARCH_SPACE["nop_bw"],
    "micro_batch": SYSTEM_PARAM_SEARCH_SPACE["micro_batch"],
    "tensor_parall": SYSTEM_PARAM_SEARCH_SPACE["tensor_parall"],
    "compute_units": COMPUTE_UNIT_CANDIDATES,
    "buffer_size": BUFFER_SIZE_CANDIDATES,
    "type": CHIPLET_TYPE_CANDIDATES,
}
```

**修改后：**
```python
DEFAULT_HARDWARE_SEARCH_SPACE: Dict[str, Any] = {
    "design_space_kind": "atlas_chip_yaml",
    "compute_scale": None,
    "array_shapes": [],
    "num_chiplet_candidates": [],
    "mac_num_candidates": MAC_NUM_CANDIDATES,
    "vec_num_candidates": VEC_NUM_CANDIDATES,
    "buffer_size_candidates": BUFFER_SIZE_CANDIDATES,
    "buffer_bw_candidates": BUFFER_BW_CANDIDATES,
    "core_num_candidates": CORE_NUM_CANDIDATES,
    "frequency_candidates": FREQUENCY_CANDIDATES,
    "system_params": SYSTEM_PARAM_SEARCH_SPACE,
    "tunable_categories": {
        "compute": {
            "parameters": ["mac_num", "vec_num", "frequency"],
            "description": "Core compute resources: MAC count, vector unit count, frequency",
        },
        "memory": {
            "parameters": ["buffer_size", "buffer_read_bw", "buffer_write_bw"],
            "description": "Per-core SRAM: capacity (KB), read/write bandwidth (Byte/cycle)",
        },
        "core_count": {
            "parameters": ["core_num"],
            "description": "Number of cores in the chip",
        },
        "dram": {
            "parameters": ["dram_config_path"],
            "description": "DRAM Ramulator configuration file path",
        },
    },
    # 向后兼容别名（供工具函数使用）
    "mac_num": MAC_NUM_CANDIDATES,
    "vec_num": VEC_NUM_CANDIDATES,
    "buffer_size": BUFFER_SIZE_CANDIDATES,
    "buffer_read_bw": BUFFER_BW_CANDIDATES,
    "buffer_write_bw": BUFFER_BW_CANDIDATES,
    "core_num": CORE_NUM_CANDIDATES,
    "frequency": FREQUENCY_CANDIDATES,
}
```

---

## 第 2 步：新建 ATLAS 配置模板

**新建文件：** `chiplet_tuner/simulators/atlas_config.py`

**为什么：** ATLAS 的 workload 需要 system YAML（指定芯片配置路径、并行度、互连、KV cache）和 model JSON。这个文件存放配置模板和生成函数，供 Adapter 和包装脚本使用。

```python
"""
ATLAS workload configuration templates.
These mirror the structure in ATLAS-MICRO-2026-main/configs/architecture/system/
and ATLAS-MICRO-2026-main/configs/models/.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# ---------------------------------------------------------------------------
# Built-in model presets
# ---------------------------------------------------------------------------

MODEL_PRESETS: Dict[str, Dict[str, Any]] = {
    "opt_66b": {
        "name": "opt_66b",
        "config_path": "configs/models/opt_66b.json",
        "element_size": 2,
        "batch_size": 8,
        "context_length": 4096,
    },
    "opt_6.7b": {
        "name": "opt_6.7b",
        "config_path": "configs/models/opt_6.7b.json",
        "element_size": 2,
        "batch_size": 8,
        "context_length": 2048,
    },
    "llama3_8b": {
        "name": "llama3_8b",
        "config_path": "configs/models/llama3_8b.json",
        "element_size": 2,
        "batch_size": 8,
        "context_length": 4096,
    },
    "llama3_70b": {
        "name": "llama3_70b",
        "config_path": "configs/models/llama3_70b.json",
        "element_size": 2,
        "batch_size": 4,
        "context_length": 4096,
    },
}


def resolve_model_preset(name: str, atlas_root: Path) -> Dict[str, Any]:
    """Resolve a model preset name to a dict with resolved paths."""
    if name not in MODEL_PRESETS:
        raise ValueError(f"Unknown model preset {name!r}; choices: {sorted(MODEL_PRESETS)}")
    info = copy.deepcopy(MODEL_PRESETS[name])
    model_path = (atlas_root / info["config_path"]).resolve()
    if not model_path.exists():
        raise FileNotFoundError(f"Model config not found: {model_path}")
    info["resolved_config_path"] = str(model_path)
    with open(model_path) as f:
        info["hf_config"] = json.load(f)
    return info


# ---------------------------------------------------------------------------
# Cloud system YAML template (used by the wrapper script)
# ---------------------------------------------------------------------------

def build_system_yaml(
    atlas_root: Path,
    chip_yaml_path: str,
    tp_size: int = 8,
    ep_size: int = 8,
    max_context_length: int = 524288,
    block_size: int = 256,
    interconnect_bandwidth: float = 450.0,
) -> Dict[str, Any]:
    """Build a cloud system YAML dict that references the given chip YAML."""
    return {
        "system": {
            "type": "cloud",
            "chip": {
                "config_path": str(Path(chip_yaml_path).resolve()),
            },
            "parallelism": {
                "tp_size": tp_size,
                "ep_size": ep_size,
                "tp_scope": "scale_up",
                "ep_scope": "scale_up",
            },
            "interconnect": {
                "scale_up_latency": 4e-7,
                "scale_up_bandwidth": interconnect_bandwidth,
                "scale_up_energy": 1.3,
                "scale_out_latency": 2e-6,
                "scale_out_bandwidth": 50,
                "scale_out_energy": 1.3,
            },
            "kv_cache": {
                "max_context_length": max_context_length,
                "block_size": block_size,
            },
        }
    }


# ---------------------------------------------------------------------------
# Hardware JSON → chip YAML conversion
# ---------------------------------------------------------------------------

_CHIP_DEFAULTS = {
    "noc": {
        "topology": "mesh",
        "config_path": "configs/architecture/noc/4x4_mesh",
        "flit_size": 64,
        "power": 1.5,
        "area": 1.5,
    },
}

_DEFAULT_DRAM_CONFIG = "configs/architecture/dram/cloud/cloud_1TBps.yaml"


def hardware_dict_to_chip_yaml(hardware: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Beacon hardware dict (ATLAS fields) into a chip YAML dict."""
    core = {
        "controller": {
            "power": hardware.get("controller_power", 1.0),
            "area": hardware.get("controller_area", 1.0),
        },
        "matrix": {
            "mac_num": int(hardware.get("mac_num", 8192)),
            "power": hardware.get("matrix_power", 1.1),
            "area": hardware.get("matrix_area", 1.1),
        },
        "vector": {
            "vec_num": int(hardware.get("vec_num", 512)),
            "power": hardware.get("vector_power", 1.2),
            "area": hardware.get("vector_area", 1.2),
        },
        "buffer": {
            "buffer_size": int(hardware.get("buffer_size", 3072)),
            "read_bw": float(hardware.get("buffer_read_bw", 8192)),
            "write_bw": float(hardware.get("buffer_write_bw", 8192)),
            "power": hardware.get("buffer_power", 1.3),
            "area": hardware.get("buffer_area", 1.3),
        },
    }

    # DRAM config path
    dram_path = hardware.get("dram_config_path", _DEFAULT_DRAM_CONFIG)

    chip = {
        "architecture": {
            "frequency": float(hardware.get("frequency", 1000)),
            "core_num": int(hardware.get("core_num", 16)),
            "core": core,
            "dram": {
                "config_path": dram_path,
                "power": hardware.get("dram_power", 1.4),
                "area": hardware.get("dram_area", 1.4),
            },
        }
    }

    # NoC (fixed, not searched)
    noc_defaults = copy.deepcopy(_CHIP_DEFAULTS["noc"])
    chip["architecture"]["noc"] = noc_defaults

    return chip
```

---

## 第 3 步：新建命令行包装脚本

**新建文件：** `chiplet_tuner/simulators/run_atlas.py`

**为什么：** 你选择了"包成命令行脚本"。这个脚本接收硬件 JSON 路径和输出目录，调用 `atlasim.Chip` 完成仿真，输出与 Compass 兼容的 CSV 和 JSON 文件。

```python
#!/usr/bin/env python3
"""
ATLAS wrapper script for Beacon integration.

Usage:
    python run_atlas.py <chip_json> <system_yaml> <model_preset> <output_dir>

Outputs under <output_dir>:
    exec_res.csv            # latency,energy,edp,mc
    exec_latency_detail.json   # per-operator latency (simulated detail)
    exec_energy_detail.json    # per-operator energy (simulated detail)
"""

import csv
import json
import os
import sys
import time
from pathlib import Path


def main():
    if len(sys.argv) < 5:
        print(f"Usage: {sys.argv[0]} <chip_json> <system_yaml> <model_preset> <output_dir>",
              file=sys.stderr)
        sys.exit(1)

    chip_json_path = Path(sys.argv[1])
    system_yaml_path = Path(sys.argv[2])
    model_preset = sys.argv[3]
    output_dir = Path(sys.argv[4])

    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Resolve paths ----
    # Determine ATLAS root (the script lives in chiplet_tuner/simulators/, ATLAS is at project root/ATLAS-MICRO-2026-main/)
    script_dir = Path(__file__).resolve().parent
    beacon_root = script_dir.parents[1]
    atlas_root = beacon_root / "ATLAS-MICRO-2026-main"

    # ---- Resolve model preset ----
    from chiplet_tuner.simulators.atlas_config import resolve_model_preset, build_system_yaml
    model_info = resolve_model_preset(model_preset, atlas_root)

    # ---- Read chip JSON ----
    with open(chip_json_path) as f:
        chip_dict = json.load(f)

    # ---- Convert chip dict to YAML ----
    # If it's already an ATLAS-format dict with arch fields, use as-is after wrapping.
    # If it's a raw Beacon hardware dict, convert.
    import yaml
    if "architecture" in chip_dict:
        # Already full chip YAML structure
        chip_yaml_data = chip_dict
    else:
        from chiplet_tuner.simulators.atlas_config import hardware_dict_to_chip_yaml
        chip_yaml_data = hardware_dict_to_chip_yaml(chip_dict)

    # Write chip YAML to output dir
    chip_yaml_path = output_dir / "chip.yaml"
    with open(chip_yaml_path, "w") as f:
        yaml.dump(chip_yaml_data, f, default_flow_style=False)

    # ---- Build system YAML ----
    system_data = build_system_yaml(atlas_root, str(chip_yaml_path))
    system_yaml_out_path = output_dir / "system.yaml"
    with open(system_yaml_out_path, "w") as f:
        yaml.dump(system_data, f, default_flow_style=False)

    # ---- Run inference ----
    # Change to atlas root so relative config paths resolve
    original_cwd = os.getcwd()
    os.chdir(str(atlas_root))

    try:
        sys.path.insert(0, str(atlas_root))
        from frontend.hardware_parser import CloudSystemConfig
        from frontend.model_parser import ModelConfig, get_model_config_from_hf
        from frontend.auto.system import CloudSystem
        from frontend.util import generate_context_slot_mapping

        # Load system config from the YAML we just wrote
        with open(system_yaml_out_path) as f:
            yaml_data = yaml.load(f, Loader=yaml.FullLoader)
        cloud_config = CloudSystemConfig.from_yaml(yaml_data)

        # Load model config
        model_config = get_model_config_from_hf(
            model_info["name"],
            model_info["resolved_config_path"],
        )

        batch_size = model_info.get("batch_size", 8)
        context_length = model_info.get("context_length", 4096)
        context_length_list = [context_length] * batch_size
        element_size = model_info.get("element_size", 2)

        # Generate context slot mapping
        context_slot_mapping = generate_context_slot_mapping(
            cloud_config, context_length_list
        )

        # Create system and run inference
        cloud_system = CloudSystem(
            system_config=cloud_config,
            model_config=model_config,
            element_size=element_size,
        )

        intermediate_result_dir = str(output_dir / "simulation_artifacts")
        result = cloud_system.inference(
            context_length_list=context_length_list,
            context_slot_mapping=context_slot_mapping,
            intermediate_result_dir=intermediate_result_dir,
        )

        latency_s = result["latency"]                          # seconds
        energy_j = result["energy"]                            # Joules
        performance = result["intra_chip_computation_performance"]

        # Also get operator-level stats from the Performance object, if available
        # (This depends on how CloudSystem.inference() returns the data)
        # The result dict should contain per-operator timing; we'll write detail files.

    finally:
        os.chdir(original_cwd)

    # ---- Write exec_res.csv (Compass-compatible format) ----
    csv_path = output_dir / "exec_res.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["latency", "energy", "edp", "mc"])
        edp = latency_s * energy_j
        writer.writerow([f"{latency_s:.6f}", f"{energy_j:.6f}", f"{edp:.6e}", "1.0"])

    # ---- Write detail JSONs (simplified: single operator-level record) ----
    # ATLAS doesn't have layer-by-layer breakdown natively, so we create a
    # minimal detail file that the analysis tools can consume.
    latency_detail = {
        "core0": [
            {
                "batchID": 0,
                "layerID": 0,
                "layerName": "full_inference",
                "latencyBegin": 0,
                "latencyEnd": int(latency_s * 1e9),  # ns approximation
                "calcTime": int(latency_s * 0.7 * 1e9),  # rough split
                "nocTime": 0,
                "dramTime": int(latency_s * 0.3 * 1e9),
            }
        ]
    }
    energy_detail = {
        "core0": [
            {
                "batchID": 0,
                "layerID": 0,
                "layerName": "full_inference",
                "energy": energy_j,
                "calcEnergy": energy_j * 0.6,
                "ubufEnergy": energy_j * 0.1,
                "nocEnergy": energy_j * 0.1,
                "dramEnergy": energy_j * 0.2,
            }
        ]
    }

    with open(output_dir / "exec_latency_detail.json", "w") as f:
        json.dump(latency_detail, f, indent=2)
    with open(output_dir / "exec_energy_detail.json", "w") as f:
        json.dump(energy_detail, f, indent=2)

    print(f"ATLAS simulation completed: latency={latency_s:.6f}s, energy={energy_j:.6f}J")
    print(f"Output: {csv_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
```

---

## 第 4 步：新建 ATLAS 适配器

**新建文件：** `chiplet_tuner/simulators/atlas_simulator.py`

**为什么：** 这是适配器的核心，继承 `SimulatorAdapter`，实现 `evaluate()` 和 `schema()`。

```python
"""
ATLAS SimulatorAdapter for Beacon integration.

Converts Beacon hardware dict → chip YAML → subprocess call to run_atlas.py
→ parses exec_res.csv and detail JSONs → returns EvaluationResult.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from chiplet_tuner.core.io import load_csv_first_row, read_json, write_json
from chiplet_tuner.core.search_space import DEFAULT_HARDWARE_SEARCH_SPACE
from chiplet_tuner.core.schemas import EvaluationResult
from chiplet_tuner.simulators.base import SimulatorAdapter


class AtlasSimulatorAdapter(SimulatorAdapter):
    """Adapter that calls ATLAS via its wrapper script."""

    def __init__(
        self,
        atlas_root: Path,
        output_root: Path,
        wrapper_script: Path,
        model_preset: str = "opt_66b",
        system_yaml_path: Optional[Path] = None,
        search_space: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.atlas_root = atlas_root.resolve()
        self.output_root = output_root.resolve()
        self.wrapper_script = wrapper_script.resolve()
        self.model_preset = model_preset
        self.system_yaml_path = system_yaml_path
        self.search_space = search_space or DEFAULT_HARDWARE_SEARCH_SPACE

    def evaluate(self, hardware: Dict[str, Any], iteration: int) -> EvaluationResult:
        run_dir = self.output_root / f"iter_{iteration:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)

        # Write hardware JSON to run dir
        hardware_path = run_dir / "hardware.json"
        write_json(hardware_path, hardware)

        # Also write system YAML if provided
        system_yaml_arg = ""
        if self.system_yaml_path:
            system_yaml_arg = str(self.system_yaml_path.resolve())
        else:
            # Generate a default system.yaml next to the hardware
            system_yaml_arg = str(run_dir / "system.yaml")
            from chiplet_tuner.simulators.atlas_config import build_system_yaml
            import yaml
            sys_data = build_system_yaml(self.atlas_root, str(hardware_path))
            with open(system_yaml_arg, "w") as f:
                yaml.dump(sys_data, f, default_flow_style=False)

        # Run the wrapper
        exec_log = run_dir / "atlas_exec.log"
        with exec_log.open("w", encoding="utf-8") as f:
            subprocess.run(
                [
                    "python3",
                    str(self.wrapper_script),
                    str(hardware_path),
                    system_yaml_arg,
                    self.model_preset,
                    str(run_dir),
                ],
                cwd=self.atlas_root,
                stdout=f,
                stderr=f,
                check=True,
            )

        # Parse results
        csv_path = run_dir / "exec_res.csv"
        if not csv_path.exists():
            raise RuntimeError(f"ATLAS simulation did not produce {csv_path}; check {exec_log}")

        metrics = load_csv_first_row(csv_path)

        return EvaluationResult(
            run_dir=run_dir,
            hardware=hardware,
            metrics=metrics,
            detail_files={
                "latency": run_dir / "exec_latency_detail.json",
                "energy": run_dir / "exec_energy_detail.json",
            },
            raw_files={
                "hardware": hardware_path,
                "exec_csv": csv_path,
                "exec_log": exec_log,
            },
        )

    def schema(self) -> Dict[str, Any]:
        return {
            "adapter": "atlas",
            "design_space_kind": "atlas_chip_yaml",
            "required_hardware_fields": [
                "mac_num",
                "vec_num",
                "buffer_size",
                "buffer_read_bw",
                "buffer_write_bw",
                "core_num",
                "frequency",
                "dram_config_path",
            ],
            "tunable_hardware_fields": {
                "compute": ["mac_num", "vec_num", "frequency"],
                "memory": ["buffer_size", "buffer_read_bw", "buffer_write_bw"],
                "core_count": ["core_num"],
                "dram": ["dram_config_path"],
            },
            "derived_hardware_fields": [],
            "search_space": self.search_space,
            "detail_schema": {
                "latency": "Single-record JSON approximating e2e latency",
                "energy": "Single-record JSON approximating e2e energy",
            },
        }
```

---

## 第 5 步：修改 `__init__.py`

**文件：** `chiplet_tuner/simulators/__init__.py`

**为什么：** 导出新类，让 `from chiplet_tuner.simulators.atlas_simulator import AtlasSimulatorAdapter` 可用。

```python
# 追加到现有导入之后
from chiplet_tuner.simulators.atlas_simulator import AtlasSimulatorAdapter
```

---

## 第 6 步：修改 `cli.py`

**文件：** `chiplet_tuner/cli.py`

**为什么：** 添加 `--simulator atlas` 选项，并在 `create_simulator()` 中实例化 `AtlasSimulatorAdapter`。

### 6.1 修改第 22 行（导入）

**修改前：**
```python
from chiplet_tuner.simulators.compass import CompassSimulatorAdapter
```

**修改后：**
```python
from chiplet_tuner.simulators.compass import CompassSimulatorAdapter
from chiplet_tuner.simulators.atlas_simulator import AtlasSimulatorAdapter
```

### 6.2 修改第 149 行（simulator 选项）

**修改前：**
```python
parser.add_argument("--simulator", default="compass", choices=["compass", "generic-files"])
```

**修改后：**
```python
parser.add_argument("--simulator", default="compass", choices=["compass", "generic-files", "atlas"])
```

### 6.3 添加 ATLAS 参数（第 154–156 行之后）

**在 `--exec-config` 参数之后添加：**
```python
    parser.add_argument("--atlas-root", default=str(ROOT / "ATLAS-MICRO-2026-main"))
    parser.add_argument("--atlas-model", default="opt_66b",
                        choices=["opt_66b", "opt_6.7b", "llama3_8b", "llama3_70b"])
    parser.add_argument("--atlas-system-yaml", default=None,
                        help="Path to a system YAML for ATLAS. If omitted, a default one is generated.")
```

### 6.4 修改 `create_simulator()`（第 176–192 行）

**修改前：**
```python
def create_simulator(args: argparse.Namespace, output_dir: Path) -> Optional[SimulatorAdapter]:
    if args.iterations is None:
        return None
    search_space = make_hardware_search_space(
        task_type=args.task_type,
        compute_scale=args.compute_scale,
    )
    if args.simulator == "compass":
        return CompassSimulatorAdapter(
            compass_root=Path(args.compass_root),
            search_config_path=Path(args.search_config),
            exec_config_path=Path(args.exec_config),
            output_root=output_dir,
            search_space=search_space,
        )
    raise ValueError("generic-files supports analysis of existing runs, not iterative evaluation.")
```

**修改后：**
```python
def create_simulator(args: argparse.Namespace, output_dir: Path) -> Optional[SimulatorAdapter]:
    if args.iterations is None:
        return None
    search_space = make_hardware_search_space(
        task_type=args.task_type,
        compute_scale=args.compute_scale,
    )
    if args.simulator == "compass":
        return CompassSimulatorAdapter(
            compass_root=Path(args.compass_root),
            search_config_path=Path(args.search_config),
            exec_config_path=Path(args.exec_config),
            output_root=output_dir,
            search_space=search_space,
        )
    if args.simulator == "atlas":
        wrapper_script = Path(__file__).resolve().parent / "simulators" / "run_atlas.py"
        return AtlasSimulatorAdapter(
            atlas_root=Path(args.atlas_root),
            output_root=output_dir,
            wrapper_script=wrapper_script,
            model_preset=args.atlas_model,
            system_yaml_path=Path(args.atlas_system_yaml) if args.atlas_system_yaml else None,
            search_space=search_space,
        )
    raise ValueError("generic-files supports analysis of existing runs, not iterative evaluation.")
```

---

## 第 7 步：修改分析工具（兼容无 mc 明细）

**文件：** `chiplet_tuner/tools/analysis_tools.py`

**为什么：** 现有分析工具会读取 `detail_files["monetary_cost"]`。ATLAS 不生成 mc 明细，需要让工具在 mc 明细不存在时跳过，而不是报错。

### 7.1 查找引用 `monetary_cost` 的位置

搜索 `"monetary_cost"` 在 `analysis_tools.py` 中出现的行。典型的处理方式是在读取前检查文件是否存在。

**示例修改方式（在函数内部，具体行号取决于你代码中的实际位置）：**

如果某处代码类似：
```python
mc_detail = read_json(evaluation.detail_files.get("monetary_cost"))
```

改为：
```python
mc_detail_path = evaluation.detail_files.get("monetary_cost")
mc_detail = read_json(mc_detail_path) if mc_detail_path and mc_detail_path.exists() else {}
```

> **注意：** 这里需要你根据实际代码中的引用位置来修改。用 `grep -n "monetary_cost" chiplet_tuner/tools/analysis_tools.py` 找到所有出现的位置，对每个文件读取调用加上 `exists()` 检查。

---

## 第 8 步：修改目标函数（mc 默认 1.0）

**文件：** `chiplet_tuner/pipeline/langgraph_tuner.py`

**为什么：** ATLAS 不产生 mc 值，但 `_objective` 计算 `latency * energy * mc`。需要在 metrics 中 mc 不存在时给默认值 1.0。

### 8.1 修改 `_objective` 方法

搜索 `def _objective`，找到类似：

```python
def _objective(self, metrics: Dict[str, float]) -> float:
    return metrics.get("latency", 1) * metrics.get("energy", 1) * metrics.get("mc", 1)
```

确保第三个因子是 `metrics.get("mc", 1)`。如果原来是 `metrics["mc"]`，改成 `metrics.get("mc", 1)`。

### 8.2 修改 `_node_commit` 中获取 mc 的地方

同样，将任何 `metrics["mc"]` 改为 `metrics.get("mc", 1)`。

---

## 使用方式

完成上述修改后，你可以这样运行 ATLAS DSE：

```bash
python main.py \
  --simulator atlas \
  --iterations 5 \
  --atlas-model opt_66b \
  --output-dir runs/atlas_dse_test

# 也可以指定初始硬件 JSON
python main.py \
  --simulator atlas \
  --hardware my_chip.json \
  --atlas-model llama3_8b \
  --iterations 5 \
  --output-dir runs/atlas_dse_llama

# 还可以指定自定义 system YAML
python main.py \
  --simulator atlas \
  --atlas-model opt_66b \
  --atlas-system-yaml my_system.yaml \
  --iterations 5 \
  --output-dir runs/atlas_custom_system
```

原 Compass 仍可用：

```bash
python main.py \
  --simulator compass \
  --workload prefill \
  --dataset sharegpt \
  --compute-scale 64 \
  --iterations 3 \
  --output-dir runs/compass_test
```

---

## 验证

完成修改后，先跑一次 mock LLM 测试确保流程通：

```bash
python main.py \
  --simulator atlas \
  --iterations 1 \
  --atlas-model opt_66b \
  --output-dir runs/atlas_smoke_test
```

检查以下内容：
1. `runs/atlas_smoke_test/baseline/` 或 `iter_000/` 下是否有 `hardware.json`、`exec_res.csv`
2. `exec_res.csv` 的内容是否为 `latency,energy,edp,mc` 格式
3. 终端是否打印了 tuner summary，没有报错

---

## 附录：文件修改汇总

| 文件 | 操作 | 新增/修改的内容 |
|------|------|-----------------|
| `chiplet_tuner/core/search_space.py` | 修改 | 搜索空间候选值、DEFAULT_HARDWARE_SEARCH_SPACE |
| `chiplet_tuner/simulators/atlas_config.py` | **新建** | 模型预设、chip YAML 生成、system YAML 模板 |
| `chiplet_tuner/simulators/run_atlas.py` | **新建** | 命令行包装脚本，调用 ATLAS 全流程 |
| `chiplet_tuner/simulators/atlas_simulator.py` | **新建** | Adapter：evaluate() + schema() |
| `chiplet_tuner/simulators/__init__.py` | 修改 | 导入 AtlasSimulatorAdapter |
| `chiplet_tuner/cli.py` | 修改 | 添加 atlas 选项、参数、create_simulator 分支 |
| `chiplet_tuner/tools/analysis_tools.py` | 修改 | mc_detail 读取加 exists() 检查 |
| `chiplet_tuner/pipeline/langgraph_tuner.py` | 检查/修改 | metrics.get("mc", 1) |