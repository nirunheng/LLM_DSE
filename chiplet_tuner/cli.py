from __future__ import annotations

import argparse
import os
import shlex
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from chiplet_tuner.agents.layer_level import LayerLevelAgent
from chiplet_tuner.agents.model_level import ModelLevelAgent
from chiplet_tuner.agents.solution import SolutionGenerationAgent
from chiplet_tuner.core.io import read_json
from chiplet_tuner.core.progress import ProgressReporter
from chiplet_tuner.core.schemas import LLMConfig
from chiplet_tuner.core.search_space import make_hardware_search_space
from chiplet_tuner.llm.clients import create_llm_client
from chiplet_tuner.pipeline.langgraph_tuner import LangGraphTuner
from chiplet_tuner.rag.embeddings import create_embedding_model
from chiplet_tuner.rag.vector_store import HistoryVectorStore
from chiplet_tuner.simulators.base import GenericFileEvaluationAdapter, SimulatorAdapter
from chiplet_tuner.simulators.compass import CompassSimulatorAdapter
from chiplet_tuner.simulators.atlas_simulator import AtlasSimulatorAdapter
from chiplet_tuner.simulators.compass_config import (
    COMPASS_DATASETS,
    COMPASS_SCALE_MODEL_INFO,
    COMPASS_WORKLOAD_REQ_INFO,
    write_compass_config_pair,
    write_compass_initial_hardware,
)
from chiplet_tuner.tools.analysis_tools import AnalysisToolbox
from chiplet_tuner.core.search_space import(
    ATLAS_DEFAULT_HARDWARE_SEARCH_SPACE,
    make_hardware_search_space
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPASS_ROOT = ROOT / "Compass"


class _RawShell:
    def __init__(self, text: str) -> None:
        self.text = text


_RESUME_COMMAND_FLAGS = {"--resume"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM/RAG multi-agent chiplet architecture tuner")
    parser.add_argument(
        "--hardware",
        default=None,
        help=(
            "Initial hardware JSON. If omitted with --workload/--compute-scale, "
            "a BO-style initial hardware file is generated under --output-dir; otherwise required."
        ),
    )
    parser.add_argument("--output-dir", default=str(ROOT / "runs" / time.strftime("%Y%m%d_%H%M%S")))
    parser.add_argument(
        "--history-db",
        default=None,
        help=(
            "Optional SQLite RAG history database. If omitted, the run uses "
            "<output-dir>/history_vector_store.sqlite."
        ),
    )
    parser.add_argument("--embedding-model", default="hashing")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--task-type",
        default="prefill",
        help="Task type used to choose micro_batch candidates when --workload is not used.",
    )
    parser.add_argument(
        "--workload",
        choices=sorted(COMPASS_WORKLOAD_REQ_INFO),
        help=(
            "Generate Compass configs for this workload, matching Compass/exp.py. "
            "Overrides --task-type for the hardware search space."
        ),
    )
    parser.add_argument(
        "--dataset",
        choices=sorted(COMPASS_DATASETS),
        required=False,
        help="Required with --workload. Token-length dataset prefix under Compass/config, aligned with Compass/exp.py.",
    )
    parser.add_argument(
        "--compute-scale",
        default=None,
        choices=sorted(COMPASS_SCALE_MODEL_INFO),
        help="Compass model scale preset for generated model_info.",
    )
    parser.add_argument(
        "--initial-chip-size",
        type=int,
        default=None,
        choices=[0, 1, 2],
        help=(
            "Deprecated compatibility alias. If compute/buffer are omitted, maps 0/1/2 to "
            "the matching compute_units and buffer_size tier."
        ),
    )
    parser.add_argument(
        "--initial-num-chiplets",
        type=int,
        default=None,
        choices=[1, 2, 4, 8, 16, 32, 64, 128, 256],
        help="Initial total chiplet count. If omitted, the middle legal count is used and chip_y/chip_x are derived.",
    )
    parser.add_argument(
        "--initial-compute-units",
        type=int,
        default=None,
        choices=[1024, 4096, 16384],
        help="Initial per-chiplet compute_units. If omitted, the middle legal tier is used.",
    )
    parser.add_argument(
        "--initial-buffer-size",
        type=int,
        default=None,
        choices=[2048, 8192, 32768],
        help="Initial per-chiplet buffer_size. If omitted, the middle legal tier is used.",
    )
    parser.add_argument("--initial-chiplet-type", default="ws", choices=["ws", "os"])

    parser.add_argument(
        "--llm-config",
        default=None,
        help=(
            "Optional JSON file with LLM profiles like "
            "{profile_name: {key/api_key, model, base_url/url}}. "
            "If omitted, the mock LLM is used."
        ),
    )
    parser.add_argument(
        "--llm-profile",
        default=None,
        help="Profile name to select from --llm-config when the config file contains multiple LLM profiles.",
    )
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-temperature", type=float, default=0.2)
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=None,
        help="Optional output token cap. If omitted, max_tokens is not sent to the LLM API.",
    )

    parser.add_argument("--simulator", default="compass", choices=["compass", "generic-files", "atlas"])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--from-existing", help="Analyze an existing simulator run directory.")
    mode.add_argument("--iterations", type=int, help="Run iterative simulator tuning for N iterations.")

    parser.add_argument("--compass-root", default=str(DEFAULT_COMPASS_ROOT))
    parser.add_argument("--search-config", default=str(DEFAULT_COMPASS_ROOT / "config" / "search_config_example.json"))
    parser.add_argument("--exec-config", default=str(DEFAULT_COMPASS_ROOT / "config" / "exec_config_example.json"))

    #这里添加atlas参数
    parser.add_argument("--atlas-root", default=str(ROOT / "ATLAS-MICRO-2026-main"))
    parser.add_argument("--atlas-model", default="opt_66b",
                        choices=["opt_66b", "opt_6.7b", "llama3_8b", "llama3_70b"])
    parser.add_argument("--atlas-system-yaml", default=None,
                        help="Path to a system YAML for ATLAS. If omitted, a default one is generated")

    parser.add_argument("--metrics-file", help="Generic file adapter metrics CSV/JSON.")
    parser.add_argument("--latency-detail", help="Generic file adapter normalized latency detail JSON.")
    parser.add_argument("--energy-detail", help="Generic file adapter normalized energy detail JSON.")
    parser.add_argument("--mc-detail", help="Generic file adapter monetary cost detail JSON.")
    parser.add_argument("--import-history-jsonl", help="Optional JSONL file of historical cases to import before running.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted LangGraph tuning run from --output-dir/langgraph_checkpoints.sqlite.",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Optional LangGraph checkpoint thread id. Defaults to the absolute --output-dir path.",
    )
    return parser


def create_simulator(args: argparse.Namespace, output_dir: Path) -> Optional[SimulatorAdapter]:
    if args.iterations is None:
        return None
    # 在这里定义了硬件搜索空间，make_hardwar_search_space被作为参数传给CompassSimulatorAdapter
    if args.simulator == "compass":
        search_space = make_hardware_search_space(
        task_type=args.task_type,
        compute_scale=args.compute_scale,
    )
        return CompassSimulatorAdapter(
            compass_root=Path(args.compass_root),
            search_config_path=Path(args.search_config),
            exec_config_path=Path(args.exec_config),
            output_root=output_dir,
            search_space=search_space,
        )

    # 增加atlas仿真分支
    elif args.simulator == "atlas":
        wrapper_script = Path(__file__).resolve().parent / "simulators" / "run_atlas.py"
        search_space = ATLAS_DEFAULT_HARDWARE_SEARCH_SPACE
        return AtlasSimulatorAdapter(
            atlas_root=Path(args.atlas_root),
            output_root=output_dir,
            wrapper_script=wrapper_script,
            model_preset=args.atlas_model,
            system_yaml_path=Path(args.atlas_system_yaml) if args.atlas_system_yaml else None,
            search_space=search_space
        )
    raise ValueError("generic-files supports analysis of existing runs, not iterative evaluation.")


def create_existing_adapter(args: argparse.Namespace) -> GenericFileEvaluationAdapter:
    run_dir = Path(args.from_existing).resolve()
    search_space = make_hardware_search_space(
        task_type=args.task_type,
        compute_scale=args.compute_scale,
    )
    return GenericFileEvaluationAdapter(
        run_dir=run_dir,
        hardware_path=Path(args.hardware),
        metrics_path=Path(args.metrics_file).resolve() if args.metrics_file else None,
        latency_detail_path=Path(args.latency_detail).resolve() if args.latency_detail else None,
        energy_detail_path=Path(args.energy_detail).resolve() if args.energy_detail else None,
        mc_detail_path=Path(args.mc_detail).resolve() if args.mc_detail else None,
        search_space=search_space,
    )


def prepare_compass_inputs(args: argparse.Namespace, output_dir: Path) -> None:
    """Generate Compass-compatible config/hardware inputs when the user selects a workload."""

    if args.workload:
        if not args.compute_scale:
            raise ValueError("--workload requires --compute-scale so model_info is explicit.")
        if not args.dataset:
            raise ValueError("--workload requires --dataset so token-length inputs are explicit.")
        args.task_type = args.workload
        generated_dir = output_dir / "compass_inputs"
        generated_dir.mkdir(parents=True, exist_ok=True)
        args.search_config, args.exec_config = _write_generated_compass_configs(args, generated_dir)

    if args.hardware is None:
        if args.workload and args.compute_scale:
            args.hardware = _write_generated_initial_hardware(args, output_dir / "compass_inputs")
        else:
            raise ValueError("--hardware is required unless --workload and --compute-scale are provided.")


def _write_generated_compass_configs(args: argparse.Namespace, generated_dir: Path) -> tuple[str, str]:
    search_path, exec_path = write_compass_config_pair(
        compass_root=Path(args.compass_root),
        output_dir=generated_dir,
        workload=args.workload,
        dataset=args.dataset,
        compute_scale=args.compute_scale,
    )
    return str(search_path), str(exec_path)


def _write_generated_initial_hardware(args: argparse.Namespace, generated_dir: Path) -> str:
    hardware_path = write_compass_initial_hardware(
        output_dir=generated_dir,
        task_type=args.task_type,
        compute_scale=args.compute_scale,
        chip_size=args.initial_chip_size,
        num_chiplets=args.initial_num_chiplets,
        compute_units=args.initial_compute_units,
        buffer_size=args.initial_buffer_size,
        chiplet_type=args.initial_chiplet_type,
    )
    return str(hardware_path)


def resolve_llm_config(args: argparse.Namespace) -> LLMConfig:
    file_config = _read_llm_file_config(args.llm_config, args.llm_profile)
    api_key = args.llm_api_key or _first_present(file_config, ["api_key", "key", "token"])
    if not api_key:
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = args.llm_base_url or _first_present(file_config, ["base_url", "api_base", "url"])
    model = args.llm_model or _first_present(file_config, ["model", "llm_model"])
    if not any([args.llm_config, args.llm_model, args.llm_api_key, args.llm_base_url]):
        return LLMConfig(provider="mock")
    return LLMConfig(
        provider="openai-compatible",
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=float(_first_present(file_config, ["temperature"]) or args.llm_temperature),
        max_tokens=_optional_int(_first_present(file_config, ["max_tokens"]) or args.llm_max_tokens),
        timeout=float(_first_present(file_config, ["timeout"]) or LLMConfig.timeout),
        return_reasoning=_optional_bool(_first_present(file_config, ["return_reasoning"])),
    )


def _read_llm_file_config(path: Optional[str], profile: Optional[str]) -> Dict[str, Any]:
    if not path:
        if profile:
            raise ValueError("--llm-profile requires --llm-config.")
        return {}
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"--llm-config must point to a JSON object, got {type(payload).__name__}")
    if not _is_llm_profile_map(payload):
        raise ValueError(
            f"--llm-config must use the profile-map format: "
            f'{{"profile_name": {{"model": "...", "key": "...", "url": "..."}}}}. '
            "Flat LLM config files are no longer supported."
        )
    return _select_llm_profile(payload, profile, path)


_LLM_CONFIG_FIELD_NAMES = {
    "provider",
    "llm_provider",
    "api_key",
    "key",
    "token",
    "model",
    "llm_model",
    "base_url",
    "api_base",
    "url",
    "temperature",
    "max_tokens",
    "timeout",
    "return_reasoning",
}


def _is_llm_profile_map(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    if any(key in _LLM_CONFIG_FIELD_NAMES for key in payload):
        return False
    return all(isinstance(value, dict) for value in payload.values())


def _select_llm_profile(payload: Dict[str, Any], profile: Optional[str], path: str) -> Dict[str, Any]:
    available = sorted(str(key) for key in payload)
    if profile is None:
        if len(payload) == 1:
            selected_name = next(iter(payload))
        else:
            raise ValueError(
                f"{path} contains multiple LLM profiles; choose one with --llm-profile. "
                f"Available profiles: {', '.join(available)}"
            )
    else:
        selected_name = profile
        if selected_name not in payload:
            raise ValueError(
                f"LLM profile {selected_name!r} not found in {path}. "
                f"Available profiles: {', '.join(available)}"
            )
    selected = payload[selected_name]
    if not isinstance(selected, dict):
        raise ValueError(f"LLM profile {selected_name!r} in {path} must be a JSON object.")
    if "provider" in selected or "llm_provider" in selected:
        raise ValueError(
            f"LLM profile {selected_name!r} in {path} must not contain provider/llm_provider; "
            "only OpenAI-compatible chat-completions endpoints are supported."
        )
    return {**selected, "profile": selected_name}


def _first_present(payload: Dict[str, Any], keys: Sequence[str]) -> Optional[Any]:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(value)


def _optional_bool(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Expected boolean value, got {value!r}")


def write_resume_script(args: argparse.Namespace, output_dir: Path) -> Path:
    """Write a self-contained resume script for an iterative LangGraph run."""

    script_path = output_dir / "resume.sh"
    log_path = output_dir / "run.log"
    command_args = _resume_command_args(args, output_dir)
    command = _format_shell_command(["python3", "main.py", *command_args])
    content = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            "# Auto-generated by chiplet_tuner. Re-run this script to resume the same output directory.",
            f"project_root={shlex.quote(str(ROOT))}",
            f"output_dir={shlex.quote(str(output_dir))}",
            f"log_file={shlex.quote(str(log_path))}",
            "",
            'cd "$project_root"',
            "",
            "{",
            "  echo \"\"",
            "  echo \"===== RESUME $(date '+%Y-%m-%d %H:%M:%S') =====\"",
            _indent_shell_command(command, spaces=2),
            '} 2>&1 | tee -a "$log_file"',
            "",
        ]
    )
    script_path.write_text(content, encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def _resume_command_args(args: argparse.Namespace, output_dir: Path) -> list[Any]:
    if args.iterations is None:
        raise ValueError("Resume scripts are only supported for iterative tuning runs.")
    command_args: list[Any] = [
        "--iterations",
        str(args.iterations),
        "--output-dir",
        str(output_dir),
        "--history-db",
        str(args.history_db),
        "--embedding-model",
        str(args.embedding_model),
        "--top-k",
        str(args.top_k),
        "--task-type",
        str(args.task_type),
        "--simulator",
        str(args.simulator),
        "--compass-root",
        str(Path(args.compass_root).resolve()),
        "--search-config",
        str(Path(args.search_config).resolve()),
        "--exec-config",
        str(Path(args.exec_config).resolve()),
    ]
    _append_optional_arg(command_args, "--hardware", args.hardware, path=True)
    _append_optional_arg(command_args, "--workload", args.workload)
    _append_optional_arg(command_args, "--dataset", args.dataset)
    _append_optional_arg(command_args, "--compute-scale", args.compute_scale)
    _append_optional_arg(command_args, "--initial-chip-size", args.initial_chip_size)
    _append_optional_arg(command_args, "--initial-num-chiplets", args.initial_num_chiplets)
    _append_optional_arg(command_args, "--initial-compute-units", args.initial_compute_units)
    _append_optional_arg(command_args, "--initial-buffer-size", args.initial_buffer_size)
    _append_optional_arg(command_args, "--initial-chiplet-type", args.initial_chiplet_type)
    _append_optional_arg(command_args, "--llm-config", args.llm_config, path=True)
    _append_optional_arg(command_args, "--llm-profile", args.llm_profile)
    _append_optional_arg(command_args, "--llm-model", args.llm_model)
    _append_optional_arg(command_args, "--llm-base-url", args.llm_base_url)
    _append_optional_arg(command_args, "--llm-temperature", args.llm_temperature)
    _append_optional_arg(command_args, "--llm-max-tokens", args.llm_max_tokens)
    if args.llm_api_key:
        command_args.extend(["--llm-api-key", _RawShell('"${LLM_API_KEY:?Set LLM_API_KEY before running resume.sh}"')])
    _append_optional_arg(command_args, "--thread-id", args.thread_id)
    command_args.append("--resume")
    return command_args


def _append_optional_arg(
    command_args: list[Any],
    name: str,
    value: Any,
    path: bool = False,
) -> None:
    if value in (None, ""):
        return
    rendered = str(Path(value).resolve()) if path else str(value)
    command_args.extend([name, rendered])


def _format_shell_command(command_args: Sequence[Any]) -> str:
    if len(command_args) < 2:
        return " ".join(_shell_arg(arg) for arg in command_args)
    lines = [f"{_shell_arg(command_args[0])} {_shell_arg(command_args[1])} \\"]
    index = 2
    while index < len(command_args):
        token = command_args[index]
        if token in _RESUME_COMMAND_FLAGS or index == len(command_args) - 1:
            segment = [token]
            index += 1
        else:
            segment = [token, command_args[index + 1]]
            index += 2
        suffix = " \\" if index < len(command_args) else ""
        lines.append("  " + " ".join(_shell_arg(arg) for arg in segment) + suffix)
    return "\n".join(lines)


def _shell_arg(arg: Any) -> str:
    if isinstance(arg, _RawShell):
        return arg.text
    return shlex.quote(str(arg))


def _indent_shell_command(command: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in command.splitlines())


def format_compact_tuning_summary(summary: Dict[str, Any], output_dir: Path) -> str:
    best = summary.get("best", {}) if isinstance(summary.get("best"), dict) else {}
    best_metrics = best.get("metrics", {}) if isinstance(best.get("metrics"), dict) else {}
    retry_summary = summary.get("llm_retry_summary", {})
    if not isinstance(retry_summary, dict):
        retry_summary = {}
    checkpoint = summary.get("checkpoint", {})
    if not isinstance(checkpoint, dict):
        checkpoint = {}

    lines = [
        "Tuning completed.",
        f"output_dir: {output_dir}",
        f"full_summary_json: {output_dir / 'tuning_summary.json'}",
        f"metrics_table: {summary.get('metrics_table', output_dir / 'tuning_metrics_table.md')}",
        f"timing_summary_md: {summary.get('timing_summary_md', output_dir / 'timing_summary.md')}",
        f"best_hardware: {output_dir / 'best_hardware.json'}",
        f"resume_script: {output_dir / 'resume.sh'}",
        (
            "best: "
            f"iteration={best.get('iteration', 'N/A')}, "
            f"phase={best.get('phase', 'N/A')}, "
            f"objective={_format_summary_number(best.get('score', best_metrics.get('objective')))}, "
            f"latency={_format_summary_number(best_metrics.get('latency'))}, "
            f"energy={_format_summary_number(best_metrics.get('energy'))}, "
            f"mc={_format_summary_number(best_metrics.get('mc'))}"
        ),
        (
            "evaluated: "
            f"runs={summary.get('evaluated_runs', 'N/A')}, "
            f"designs={summary.get('evaluated_designs', 'N/A')}, "
            f"history_records={summary.get('history_records', 'N/A')}"
        ),
        (
            "llm_retries: "
            f"attempts={retry_summary.get('retry_attempt_count', 0)}, "
            f"exhausted={retry_summary.get('exhausted_count', 0)}"
        ),
    ]
    if checkpoint:
        lines.append(
            "checkpoint: "
            f"type={checkpoint.get('type', 'N/A')}, "
            f"path={checkpoint.get('path', 'N/A')}, "
            f"resumed={checkpoint.get('resumed', False)}"
        )
    return "\n".join(lines)


def _format_summary_number(value: Any) -> str:
    if value in (None, ""):
        return "N/A"
    try:
        return f"{float(value):.4g}"
    except (TypeError, ValueError):
        return str(value)


def build_tuner(
    args: argparse.Namespace,
    output_dir: Path,
    simulator: Optional[SimulatorAdapter],
    simulator_schema: dict,
) -> LangGraphTuner:
    embedding_model = create_embedding_model(args.embedding_model)
    history_store = HistoryVectorStore(args.history_db, embedding_model=embedding_model)
    if args.import_history_jsonl:
        imported = history_store.import_jsonl(args.import_history_jsonl)
        print(f"Imported {imported} historical cases into {args.history_db}")

    llm_config = resolve_llm_config(args)
    llm = create_llm_client(llm_config)
    if llm_config.provider != "mock":
        llm.trace_enabled = True
    toolbox = AnalysisToolbox()
    model_agent = ModelLevelAgent(llm=llm, toolbox=toolbox)
    layer_agent = LayerLevelAgent(llm=llm, toolbox=toolbox)
    solution_agent = SolutionGenerationAgent(
        llm=llm,
        store=history_store,
        toolbox=toolbox,
        simulator_schema=simulator_schema,
        top_k=args.top_k,
    )
    return LangGraphTuner(
        model_agent=model_agent,
        layer_agent=layer_agent,
        solution_agent=solution_agent,
        history_store=history_store,
        output_root=output_dir,
        simulator=simulator,
        progress=ProgressReporter(enabled=True, refresh_interval_s=30.0),
        resume=bool(args.resume),
        thread_id=args.thread_id,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.history_db is None:
        args.history_db = str(output_dir / "history_vector_store.sqlite")
    prepare_compass_inputs(args, output_dir)
    if args.iterations is not None:
        resume_script = output_dir / "resume.sh"
        if not args.resume or not resume_script.exists():
            write_resume_script(args, output_dir)

    if args.from_existing:
        adapter = create_existing_adapter(args)
        hardware = adapter.load_hardware()
        simulator_schema = adapter.schema()
        tuner = build_tuner(args, output_dir, simulator=None, simulator_schema=simulator_schema)
        evaluation = adapter.evaluate(hardware, iteration=0)
        analysis_dir = output_dir / f"existing_{evaluation.run_dir.name}"
        model_result, state, proposal = tuner.analyze_evaluation(evaluation, iteration=0, output_dir=analysis_dir)
        print(model_result.summary)
        print(f"Layer bottleneck state: {state.primary_impact}/{state.dominant_root_cause}")
        print(f"Proposed actions: {', '.join(proposal.actions)}")
        print(f"Agent trace: {model_result.generated_files['agent_trace_json']}")
        return 0

    simulator = create_simulator(args, output_dir)
    if simulator is None:
        raise ValueError("--iterations requires a simulator adapter.")
    tuner = build_tuner(args, output_dir, simulator=simulator, simulator_schema=simulator.schema())
    summary = tuner.tune(
        read_json(args.hardware),
        iterations=int(args.iterations),
    )
    print(format_compact_tuning_summary(summary, output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
