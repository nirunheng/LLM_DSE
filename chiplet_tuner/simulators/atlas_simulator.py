"""
ATLAS SimulatorAdapter for Beacon integration.

Converts Beacon hardware dict → chip YAML → subprocess call to run_atlas.py
→ parses exec_res.csv and detail JSONs → returns EvaluationResult.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional, Dict

from chiplet_tuner.core.io import load_csv_first_row, write_json
from chiplet_tuner.core.search_space import DEFAULT_HARDWARE_SEARCH_SPACE, ATLAS_DEFAULT_HARDWARE_SEARCH_SPACE
from chiplet_tuner.simulators.base import SimulatorAdapter
from chiplet_tuner.core.schemas import EvaluationResult

class AtlasSimulatorAdapter(SimulatorAdapter):

    def __init__(
            self,
            atlas_root: Path,
            output_root: Path,
            wrapper_script: Path,
            model_preset: str = "opt_66b",
            system_yaml_path: Optional[Path] = None,
            search_space: Optional[Dict[str, Any]] = None
    ) -> None:
        self.atlas_root = atlas_root.resolve()
        self.output_root = output_root.resolve()
        self.wrapper_script = wrapper_script.resolve()
        self.model_preset = model_preset
        self.system_yaml_path = system_yaml_path
        self.search_space = search_space or ATLAS_DEFAULT_HARDWARE_SEARCH_SPACE

    def evaluate(self, hardware: Dict[str, Any], iteration: int) -> EvaluationResult:
        run_dir = self.output_root / f"iter_{iteration:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)

        # Write hardware JSON to run dir
        hardware_path = run_dir / "hardware.json"
        write_json(hardware_path, hardware)

        # System YAML: if provided externally, use it; otherwise let the wrapper generate one
        if self.system_yaml_path:
            system_yaml_arg = str(self.system_yaml_path)
        else:
            # Pass a placeholder path — the wrapper script will generate the system.yaml itself
            system_yaml_arg = str(run_dir / "system.yaml")

        # Build env with PYTHONPATH set to find chiplet_tuner and atlasim
        project_root = self.wrapper_script.resolve().parents[2]  # run_atlas.py -> simulators/ -> chiplet_tuner/ -> Beacon/
        atlas_lib = self.atlas_root / "simulator" / "build" / "lib"
        env = os.environ.copy()
        # PYTHONPATH needs both the beacon project root (for chiplet_tuner) and atlas lib (for atlasim)
        beacon_pkg = str(project_root)
        atlas_pylib = str(atlas_lib)
        pp_parts = [p for p in [atlas_pylib, beacon_pkg] if p]
        env["PYTHONPATH"] = ":".join(pp_parts) + ":" + env.get("PYTHONPATH", "")
        ld_parts = [p for p in [atlas_pylib] if p]
        env["LD_LIBRARY_PATH"] = ":".join(ld_parts) + ":" + env.get("LD_LIBRARY_PATH", "")

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
                cwd=project_root,
                stdout=f,
                stderr=f,
                check=True,
                env=env,
            )

        # Parse result (OUTSIDE the with block, after subprocess finishes)
        csv_path = run_dir / "exec_res.csv"
        if not csv_path.exists():
            raise RuntimeError(f"ATLAS simulation didn't produce {csv_path}; check {exec_log}")

        metrics = load_csv_first_row(csv_path)

        return EvaluationResult(
            run_dir=run_dir,
            hardware=hardware,
            metrics=metrics,
            detail_files={
                "latency": run_dir / "exec_latency_detail.json",
                "energy": run_dir / "exec_energy_detail.json",
                "monetary_cost" : run_dir / "monetary_cost_detail.json"
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