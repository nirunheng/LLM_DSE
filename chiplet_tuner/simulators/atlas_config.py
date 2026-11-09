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
# Hardware JSON -> chip YAML conversion
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
