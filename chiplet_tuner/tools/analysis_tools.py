from __future__ import annotations

import html
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chiplet_tuner.core.io import read_json, write_csv, write_json
from chiplet_tuner.core.search_space import (
    DEFAULT_HARDWARE_SEARCH_SPACE,
    all_system_param_candidates,
    array_shape_candidates,
    buffer_size_candidates,
    chip_type_candidates,
    coerce_to_candidates,
    compute_unit_candidates,
    hardware_shape,
    materialize_hardware,
    normalize_hardware_to_design_space,
    step_array_shape,
    step_chiplet_resource,
)
from chiplet_tuner.core.schemas import EvaluationResult, LayerLoad, ToolResult, ToolSpec
from chiplet_tuner.core.utils import clamp_to_candidates, layer_group, operator_features
from chiplet_tuner.rag.vector_store import hardware_fingerprint


DEFAULT_LAYER_RANK_TOP_LAYERS = 8
MAX_LAYER_RANK_TOP_LAYERS = 12
DEFAULT_TOOL_TOP_ITEMS = 6
MAX_TOOL_TOP_ITEMS = 12
MAX_HISTORY_ITEMS = 20
MAX_INSPECT_LAYERS = 12


@dataclass
class ToolContext:
    """Shared context passed to toolbox calls from any agent."""

    output_dir: Path
    evaluation: Optional[EvaluationResult] = None
    model_analysis: Optional[Dict[str, Any]] = None
    bottleneck_state: Optional[Dict[str, Any]] = None
    current_hardware: Optional[Dict[str, Any]] = None
    retrieved_cases: List[Dict[str, Any]] = field(default_factory=list)
    simulator_schema: Optional[Dict[str, Any]] = None
    search_state: Optional[Dict[str, Any]] = None
    evaluation_bases: Dict[str, EvaluationResult] = field(default_factory=dict)
    active_base: Dict[str, Any] = field(default_factory=dict)
    artifact_references: List[Dict[str, Any]] = field(default_factory=list)


class AnalysisToolbox:
    """Shared tool collection callable by all agents."""

    def specs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="compare_search_states",
                description=(
                    "Compare current, previous, and best evaluated search states using a compact view. "
                    "The default compact view includes current/previous/best; call again with "
                    "include_history/history_limit when a short recent trajectory is needed."
                ),
                input_schema={
                    "requires_context": ["search_state"],
                    "detail_level": "summary|recent; default=summary. Summary omits full per-iteration bases.",
                    "include_history": "optional boolean; include compact recent evaluated iterations when true",
                    "history_limit": f"optional integer; recent iteration count, capped at {MAX_HISTORY_ITEMS}",
                    "include_hardware": (
                        "optional boolean; include compact hardware summaries with chiplet layout grids, "
                        "default=true"
                    ),
                },
            ),
            ToolSpec(
                name="select_analysis_base",
                description=(
                    "Select which evaluated hardware/evaluation should be the active analysis base for later tools. "
                    "Use source=current|previous|best or iteration=<integer>. The last selected base is used by "
                    "subsequent model/layer/solution analysis."
                ),
                input_schema={
                    "requires_context": ["evaluation_bases"],
                    "source": "current|previous|best, optional if iteration is provided",
                    "iteration": "optional evaluated iteration id, e.g. 0",
                    "reason": "brief reason for choosing this base",
                },
            ),
            ToolSpec(
                name="summarize_metrics",
                description="Summarize scalar evaluation metrics and compute objective=latency*energy*mc.",
                input_schema={"requires_context": ["evaluation"], "arguments": {}},
            ),
            ToolSpec(
                name="build_execution_timeline",
                description="Build execution timeline CSV/HTML and return critical-path and core-utilization summary.",
                input_schema={
                    "requires_context": ["evaluation"],
                    "include_sample_rows": "optional boolean; default=false. Use true only when a few concrete timeline rows are needed.",
                    "sample_limit": f"optional integer; capped at {MAX_TOOL_TOP_ITEMS}",
                },
            ),
            ToolSpec(
                name="aggregate_layer_loads",
                description=(
                    "Generate full per-layer load artifacts, but return only a parameter-controlled compact query. "
                    "Prefer summarize_layer_rank_views for model-level candidate discovery and inspect_layer_details "
                    "for selected layers."
                ),
                input_schema={
                    "requires_context": ["evaluation"],
                    "view": "summary|ranked|layers|groups; default=summary",
                    "rank_by": (
                        "latency_sum|energy|critical_end|compute|memory|communication|buffer; "
                        "dimension views use transparent timing/energy breakdown evidence"
                    ),
                    "top_layers": f"optional integer; capped at {MAX_TOOL_TOP_ITEMS}",
                    "layer_ids": "optional list of layer ids for view=layers",
                    "layer_names": "optional list of layer names for view=layers",
                    "groups": "optional list of operator groups for view=groups or ranked filtering",
                    "include_fields": (
                        "optional list: basic,shares,placement,timing,energy,energy_components,breakdown,"
                        "root_cause, or dimension aliases compute/memory/communication/buffer"
                    ),
                },
            ),
            ToolSpec(
                name="inspect_layer_details",
                description=(
                    "Inspect detailed timing, energy, core placement, and compute/memory/communication/buffer "
                    "evidence for specific candidate layers."
                ),
                input_schema={
                    "requires_context": ["evaluation"],
                    "layers": "list of objects with layer_id/layer_name, or use layer_ids/layer_names",
                    "layer_ids": "optional list of integer layer ids",
                    "layer_names": "optional list of layer names",
                    "max_layers": f"optional integer; capped at {MAX_INSPECT_LAYERS}",
                    "include_fields": (
                        "optional list: basic,shares,placement,timing,energy,energy_components,breakdown,"
                        "root_cause,features, or dimension aliases compute/memory/communication/buffer"
                    ),
                },
            ),
            ToolSpec(
                name="summarize_layer_rank_views",
                description=(
                    "Return independent candidate layer rankings by latency, energy, critical-path position, "
                    "compute, memory, communication, and buffer evidence. This tool does not decide the final bottleneck."
                ),
                input_schema={
                    "top_layers": (
                        "optional integer selected by the agent; number of candidate layers to keep per rank view. "
                        f"Use a small value, typically 4-8. If omitted, default={DEFAULT_LAYER_RANK_TOP_LAYERS}. "
                        f"Values above {MAX_LAYER_RANK_TOP_LAYERS} are capped by the tool."
                    ),
                    "requires_context": ["evaluation"],
                },
            ),
            ToolSpec(
                name="summarize_operator_groups",
                description="Aggregate layer loads by operator group such as attention, qkv_projection, ffn, and other.",
                input_schema={
                    "requires_context": ["evaluation"],
                    "sort_by": "latency_sum|energy|layers|occurrences; default=latency_sum",
                    "top_groups": f"optional integer; capped at {MAX_TOOL_TOP_ITEMS}",
                    "include_components": "optional boolean; include calc/noc/dram components, default=false",
                },
            ),
            ToolSpec(
                name="summarize_monetary_cost",
                description="Read monetary-cost detail and return total cost, component breakdown, and cost shares.",
                input_schema={
                    "requires_context": ["evaluation"],
                    "top_components": f"optional integer; capped at {MAX_TOOL_TOP_ITEMS}",
                },
            ),
            ToolSpec(
                name="summarize_hardware_config",
                description=(
                    "Summarize current hardware resources and explicit search-space position: "
                    "chiplet count, derived array shape, per-chiplet compute/storage/dataflow choices, chiplet layout, and "
                    "system parameters. This returns a compact summary by default; request include_full_hardware "
                    "only when exact simulator-order chiplet fields are necessary."
                ),
                input_schema={
                    "requires_context": ["current_hardware"],
                    "include_design_space": "optional boolean; include candidate design-space positions, default=true",
                    "include_full_hardware": (
                        "optional boolean; default=false. Return raw hardware JSON including the full chiplet list "
                        "when summary/layout grids are insufficient."
                    ),
                },
            ),
            ToolSpec(
                name="materialize_hardware_candidate",
                description=(
                    "Build a complete legal hardware candidate from high-level update intent. "
                    "Use this instead of manually editing derived hardware fields. The default response is a "
                    "compact summary plus a candidate artifact path; set include_full_hardware=true only when "
                    "the exact simulator JSON must be inspected."
                ),
                input_schema={
                    "requires_context": ["current_hardware", "simulator_schema"],
                    "num_chiplets": "optional integer total chiplet count; chip_y/chip_x are derived by the tool",
                    "compute_units": (
                        "optional scalar for homogeneous updates or per-chiplet list for heterogeneous updates, "
                        "legal values 1024/4096/16384"
                    ),
                    "buffer_size": (
                        "optional scalar for homogeneous updates or per-chiplet list for heterogeneous updates, "
                        "legal values 2048/8192/32768"
                    ),
                    "system_params": "optional object with dram_bw/nop_bw/micro_batch/tensor_parall",
                    "chiplet_type": "optional single chiplet type applied to all materialized chiplets",
                    "chiplet_types": "optional per-chiplet type list for heterogeneous ws/os layouts",
                    "chiplet_spec_strategy": "preserve_prefix|majority|uniform, used when chiplet count changes",
                    "chiplet_type_strategy": "preserve_prefix|majority|uniform, used when chiplet count changes",
                    "chiplet_type_fill": "required/recommended for uniform, e.g. ws or os",
                    "include_full_hardware": "optional boolean; default=false. Include raw updated hardware only when required.",
                },
            ),
            ToolSpec(
                name="modify_hardware_parameter",
                description=(
                    "Directly set one or more legal hardware parameters to target values chosen by the LLM, "
                    "then return a materialized hardware candidate. Use either single parameter/value or updates, "
                    "not both. The default response is compact; set include_full_hardware=true only when exact "
                    "simulator JSON is needed."
                ),
                input_schema={
                    "requires_context": ["current_hardware", "simulator_schema"],
                    "parameter": "optional single parameter name; mutually exclusive with updates",
                    "value": "optional target value for parameter; required when parameter is used",
                    "updates": (
                        "optional list of {parameter, value, scope, indices}; mutually exclusive with top-level "
                        "parameter/value/scope/indices. Parameters include "
                        "num_chiplets, compute_units, buffer_size, chiplet_type, "
                        "dram_bw, nop_bw, micro_batch, tensor_parall"
                    ),
                    "scope": "optional for per-chiplet fields: all|first|indices; use indices to test localized heterogeneous changes",
                    "indices": "optional chiplet indices for per-chiplet fields when scope=indices",
                    "chiplet_spec_strategy": "optional strategy for chiplet-count changes: preserve_prefix|majority|uniform",
                    "chiplet_type_strategy": "optional strategy for chiplet-count changes: preserve_prefix|majority|uniform",
                    "chiplet_type_fill": "optional type for uniform strategy",
                    "include_full_hardware": "optional boolean; default=false. Include raw updated hardware only when required.",
                },
            ),
            ToolSpec(
                name="step_hardware_parameter",
                description=(
                    "Apply one legal neighboring move to num_chiplets, per-chiplet resource/type, or a system parameter, "
                    "then return a materialized hardware candidate. Per-chiplet parameters require an explicit scope."
                ),
                input_schema={
                    "requires_context": ["current_hardware", "simulator_schema"],
                    "parameter": "num_chiplets|compute_units|buffer_size|chiplet_type|dram_bw|nop_bw|micro_batch|tensor_parall",
                    "direction": "integer step direction, usually 1 or -1",
                    "scope": "required for per-chiplet fields compute_units|buffer_size|chiplet_type: first|all",
                    "chiplet_spec_strategy": "optional strategy for num_chiplets moves: preserve_prefix|majority|uniform",
                    "chiplet_type_strategy": "optional strategy for num_chiplets moves: preserve_prefix|majority|uniform",
                    "chiplet_type_fill": "optional type for uniform strategy",
                    "include_full_hardware": "optional boolean; default=false. Include raw updated hardware only when required.",
                },
            ),
        ]

    def run(
        self,
        tool_name: str,
        context: ToolContext | EvaluationResult,
        output_dir: Optional[Path] = None,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        arguments = arguments or {}
        if isinstance(context, EvaluationResult):
            if output_dir is None:
                raise ValueError("output_dir is required when running toolbox with EvaluationResult.")
            context = ToolContext(
                output_dir=output_dir,
                evaluation=context,
                current_hardware=context.hardware,
                evaluation_bases={"current": context},
                active_base={
                    "source": "current",
                    "iteration": self._iteration_from_run_dir(context.run_dir),
                    "base_key": "current",
                },
            )
        if tool_name == "compare_search_states":
            return self.compare_search_states(context, arguments=arguments)
        if tool_name == "select_analysis_base":
            return self.select_analysis_base(context, arguments=arguments)
        if tool_name == "summarize_metrics":
            return self.summarize_metrics(context)
        if tool_name == "build_execution_timeline":
            return self.build_execution_timeline(context, arguments=arguments)
        if tool_name == "aggregate_layer_loads":
            return self.aggregate_layer_loads(context, arguments=arguments)
        if tool_name == "inspect_layer_details":
            return self.inspect_layer_details(
                context=context,
                layers=arguments.get("layers"),
                layer_ids=arguments.get("layer_ids"),
                layer_names=arguments.get("layer_names"),
                max_layers=arguments.get("max_layers"),
                include_fields=arguments.get("include_fields"),
            )
        if tool_name == "summarize_layer_rank_views":
            return self.summarize_layer_rank_views(
                context=context,
                top_layers=arguments.get("top_layers"),
            )
        if tool_name == "summarize_operator_groups":
            return self.summarize_operator_groups(context, arguments=arguments)
        if tool_name == "summarize_monetary_cost":
            return self.summarize_monetary_cost(context, arguments=arguments)
        if tool_name == "summarize_hardware_config":
            return self.summarize_hardware_config(context, arguments=arguments)
        if tool_name == "materialize_hardware_candidate":
            return self.materialize_hardware_candidate(context=context, update=arguments)
        if tool_name == "modify_hardware_parameter":
            return self.modify_hardware_parameter(context=context, arguments=arguments)
        if tool_name == "step_hardware_parameter":
            return self.step_hardware_parameter(context=context, arguments=arguments)
        raise ValueError(f"Unknown analysis tool: {tool_name}")

    def compare_search_states(self, context: ToolContext, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        arguments = arguments or {}
        if context.search_state is not None:
            state = context.search_state
        else:
            evaluation = self._require_evaluation(context)
            state = {
                "current": self._evaluation_base_record(
                    source="current",
                    iteration=self._iteration_from_run_dir(evaluation.run_dir),
                    evaluation=evaluation,
                    search_space=self._search_space(context),
                ),
                "available_bases": ["current"],
                "search_observation": {
                    "current_is_best": True,
                    "objective_change_convention": "(after - before) / before; negative means objective decreased and improved",
                    "last_change_improved_objective": None,
                    "suggested_base_choices": ["current"],
                },
            }
        payload = self._compact_search_state_payload(state, arguments)
        return ToolResult(name="compare_search_states", payload=payload)

    def select_analysis_base(self, context: ToolContext, arguments: Dict[str, Any]) -> ToolResult:
        key, source, iteration = self._resolve_base_key(arguments)
        if key not in context.evaluation_bases:
            available = sorted(context.evaluation_bases)
            raise ValueError(f"Unknown analysis base {key!r}; available bases are {available}")
        evaluation = context.evaluation_bases[key]
        search_space = self._search_space(context)
        selected = self._base_record_from_search_state(context, key) or self._evaluation_base_record(
            source=source,
            iteration=iteration,
            evaluation=evaluation,
            search_space=search_space,
        )
        selected = dict(selected)
        selected["selection_reason"] = str(arguments.get("reason", ""))
        selected["base_key"] = key
        selected_compact = self._compact_search_record(selected, include_hardware=False) or {}
        if selected.get("selection_reason"):
            selected_compact["selection_reason"] = selected["selection_reason"]
        context.evaluation = evaluation
        context.current_hardware = evaluation.hardware
        context.active_base = selected_compact
        return ToolResult(
            name="select_analysis_base",
            payload={
                "selected_base": selected_compact,
                "metrics": self._metrics_with_objective(evaluation.metrics),
                "hardware_summary_available": (
                    "compare_search_states includes compact hardware by default; call summarize_hardware_config "
                    "when this selected base needs detailed hardware or search-space position."
                ),
            },
        )

    def summarize_metrics(self, context: ToolContext) -> ToolResult:
        evaluation = self._require_evaluation(context)
        latency = self._required_metric(evaluation.metrics, "latency")
        energy = self._required_metric(evaluation.metrics, "energy")
        mc = self._required_metric(evaluation.metrics, "mc")
        return ToolResult(
            name="summarize_metrics",
            payload={
                "metrics": self._metrics_with_objective(evaluation.metrics),
                "objective": latency * energy * mc,
            },
        )

    def build_execution_timeline(self, context: ToolContext, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        arguments = arguments or {}
        evaluation = self._require_evaluation(context)
        stats_dir = self._analysis_dir(context)
        timeline_summary_path = stats_dir / "execution_timeline_summary.json"
        timeline_path = stats_dir / "execution_timeline.csv"
        timeline_html = stats_dir / "execution_timeline.html"
        generated_files = {
            "timeline_summary_json": str(timeline_summary_path),
            "timeline_csv": str(timeline_path),
            "timeline_html": str(timeline_html),
        }
        if timeline_summary_path.exists() and timeline_path.exists() and timeline_html.exists():
            cached = read_json(timeline_summary_path)
            self._record_artifact_reference(
                context,
                tool_name="build_execution_timeline",
                arguments={},
                generated_files=generated_files,
                reused=True,
            )
            return ToolResult(
                name="build_execution_timeline",
                payload=self._timeline_payload_for_llm(cached, arguments),
                generated_files=generated_files,
            )
        latency_detail = self._read_required_detail(evaluation, "latency")
        timeline_rows = self._build_timeline_rows(latency_detail)
        write_csv(
            timeline_path,
            timeline_rows,
            [
                "core",
                "batchID",
                "layerID",
                "layerName",
                "group",
                "latencyBegin",
                "latencyEnd",
                "duration",
                "calcTime",
                "nocTime",
                "dramTime",
            ],
        )
        timeline_html = self._write_timeline_html(stats_dir, timeline_rows)
        payload = {
            "timeline": self._summarize_timeline(timeline_rows),
            "sample_rows": timeline_rows[:20],
        }
        write_json(timeline_summary_path, payload)
        self._record_artifact_reference(
            context,
            tool_name="build_execution_timeline",
            arguments={},
            generated_files=generated_files,
            reused=False,
        )
        return ToolResult(
            name="build_execution_timeline",
            payload=self._timeline_payload_for_llm(payload, arguments),
            generated_files=generated_files,
        )

    def aggregate_layer_loads(self, context: ToolContext, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        arguments = arguments or {}
        evaluation = self._require_evaluation(context)
        stats_dir = self._analysis_dir(context)
        loads_path = stats_dir / "layer_loads.json"
        energy_path = stats_dir / "layer_energy_table.csv"
        generated_files = {
            "layer_loads_json": str(loads_path),
            "energy_table_csv": str(energy_path),
        }
        if loads_path.exists() and energy_path.exists():
            stored = read_json(loads_path)
            all_loads = stored.get("layer_loads", []) if isinstance(stored, dict) else []
            self._record_artifact_reference(
                context,
                tool_name="aggregate_layer_loads",
                arguments=arguments,
                generated_files=generated_files,
                reused=True,
            )
            payload = self._query_layer_loads_payload(all_loads, evaluation, arguments)
            return ToolResult(name="aggregate_layer_loads", payload=payload, generated_files=generated_files)
        all_loads = self._layer_loads(evaluation)
        write_csv(energy_path, all_loads, self._layer_table_fields())
        payload = {
            "metrics": self._metrics_with_objective(evaluation.metrics),
            "layer_count": len(all_loads),
            "layer_loads": all_loads,
            "aggregate_breakdown": self._summarize_breakdowns(all_loads),
        }
        write_json(loads_path, payload)
        self._record_artifact_reference(
            context,
            tool_name="aggregate_layer_loads",
            arguments=arguments,
            generated_files=generated_files,
            reused=False,
        )
        return ToolResult(
            name="aggregate_layer_loads",
            payload=self._query_layer_loads_payload(all_loads, evaluation, arguments),
            generated_files=generated_files,
        )

    def summarize_layer_rank_views(self, context: ToolContext, top_layers: Any = None) -> ToolResult:
        evaluation = self._require_evaluation(context)
        requested_top_layers, effective_top_layers = self._resolve_top_layers(top_layers)
        rank_views_path = self._analysis_dir(context) / f"layer_rank_views_top{effective_top_layers}.json"
        generated_files = {f"layer_rank_views_top{effective_top_layers}_json": str(rank_views_path)}
        arguments = {"top_layers": requested_top_layers, "effective_top_layers": effective_top_layers}
        if rank_views_path.exists():
            cached = read_json(rank_views_path)
            self._record_artifact_reference(
                context,
                tool_name="summarize_layer_rank_views",
                arguments=arguments,
                generated_files=generated_files,
                reused=True,
            )
            return ToolResult(
                name="summarize_layer_rank_views",
                payload={
                    "metrics": cached["metrics"],
                    "layer_count": cached.get("layer_count", 0),
                    "aggregate_breakdown": cached.get("aggregate_breakdown", {}),
                    "layer_rank_views": self._compact_rank_views(cached["layer_rank_views"]),
                    "rank_notes": cached["rank_notes"],
                },
                generated_files=generated_files,
            )
        all_loads = self._layer_loads(evaluation)
        rank_views = self._build_layer_rank_views(all_loads, top_layers=effective_top_layers)
        payload = {
            "metrics": self._metrics_with_objective(evaluation.metrics),
            "layer_count": len(all_loads),
            "aggregate_breakdown": self._summarize_breakdowns(all_loads),
            "layer_rank_views": self._compact_rank_views(rank_views),
            "rank_notes": {
                "no_single_bottleneck_metric": True,
                "agent_should_choose_bottleneck_objective": True,
                "available_views": sorted(rank_views),
                "requested_top_layers": requested_top_layers,
                "effective_top_layers": effective_top_layers,
                "top_layers_default": DEFAULT_LAYER_RANK_TOP_LAYERS,
                "top_layers_cap": MAX_LAYER_RANK_TOP_LAYERS,
            },
        }
        write_json(
            rank_views_path,
            payload,
        )
        self._record_artifact_reference(
            context,
            tool_name="summarize_layer_rank_views",
            arguments=arguments,
            generated_files=generated_files,
            reused=False,
        )
        return ToolResult(
            name="summarize_layer_rank_views",
            payload={**payload, "layer_rank_views": self._compact_rank_views(payload["layer_rank_views"])},
            generated_files=generated_files,
        )

    def _resolve_top_layers(self, value: Any) -> Tuple[int, int]:
        requested = DEFAULT_LAYER_RANK_TOP_LAYERS if value in (None, "") else int(value)
        if requested <= 0:
            raise ValueError(f"top_layers must be positive, got {requested}")
        return requested, min(requested, MAX_LAYER_RANK_TOP_LAYERS)

    def inspect_layer_details(
        self,
        context: ToolContext,
        layers: Any = None,
        layer_ids: Any = None,
        layer_names: Any = None,
        max_layers: Any = None,
        include_fields: Any = None,
    ) -> ToolResult:
        evaluation = self._require_evaluation(context)
        all_loads = self._layer_loads(evaluation)
        selected = self._select_layers(all_loads, layers=layers, layer_ids=layer_ids, layer_names=layer_names)
        if not selected:
            raise ValueError("inspect_layer_details requires at least one valid layer id or name.")
        requested_count = len(selected)
        limit = self._resolve_limit(max_layers, default=MAX_INSPECT_LAYERS, cap=MAX_INSPECT_LAYERS, name="max_layers")
        selected = selected[:limit]
        fields = self._normalize_layer_fields(include_fields, default={"basic", "shares", "placement", "timing", "energy", "breakdown", "root_cause"})
        arguments = self._layer_selection_arguments(selected)
        arguments["max_layers"] = limit
        arguments["include_fields"] = sorted(fields)
        detail_path = self._analysis_dir(context) / f"inspected_layer_details_{self._argument_signature(arguments)}.json"
        generated_files = {"inspected_layer_details_json": str(detail_path)}
        if detail_path.exists():
            payload = read_json(detail_path)
            self._record_artifact_reference(
                context,
                tool_name="inspect_layer_details",
                arguments=arguments,
                generated_files=generated_files,
                reused=True,
            )
            return ToolResult(name="inspect_layer_details", payload=payload, generated_files=generated_files)
        details = [self._layer_detail_record(layer, evaluation.metrics, include_fields=fields) for layer in selected]
        payload = {
            "metrics": self._metrics_with_objective(evaluation.metrics),
            "layers": details,
            "layer_count": len(details),
            "requested_layer_count": requested_count,
            "truncated": requested_count > len(details),
        }
        write_json(detail_path, payload)
        self._record_artifact_reference(
            context,
            tool_name="inspect_layer_details",
            arguments=arguments,
            generated_files=generated_files,
            reused=False,
        )
        return ToolResult(
            name="inspect_layer_details",
            payload=payload,
            generated_files=generated_files,
        )

    def summarize_operator_groups(self, context: ToolContext, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        arguments = arguments or {}
        evaluation = self._require_evaluation(context)
        stats_dir = self._analysis_dir(context)
        group_path = stats_dir / "operator_group_summary.csv"
        group_json_path = stats_dir / "operator_group_summary.json"
        generated_files = {
            "operator_group_csv": str(group_path),
            "operator_group_json": str(group_json_path),
        }
        if group_json_path.exists() and group_path.exists():
            stored = read_json(group_json_path)
            rows = stored.get("operator_groups", []) if isinstance(stored, dict) else []
            self._record_artifact_reference(
                context,
                tool_name="summarize_operator_groups",
                arguments=arguments,
                generated_files=generated_files,
                reused=True,
            )
            payload = self._operator_group_payload_for_llm(rows, arguments)
            return ToolResult(name="summarize_operator_groups", payload=payload, generated_files=generated_files)
        all_loads = self._layer_loads(evaluation)
        rows = self._summarize_operator_groups(all_loads)
        write_csv(
            group_path,
            rows,
            [
                "group",
                "layers",
                "occurrences",
                "latency_sum",
                "energy",
                "calc_time",
                "noc_time",
                "dram_time",
                "calc_energy",
                "ubuf_energy",
                "noc_energy",
                "dram_energy",
                "dominant_dimension",
            ],
        )
        payload = {"operator_groups": rows}
        write_json(group_json_path, payload)
        self._record_artifact_reference(
            context,
            tool_name="summarize_operator_groups",
            arguments=arguments,
            generated_files=generated_files,
            reused=False,
        )
        return ToolResult(
            name="summarize_operator_groups",
            payload=self._operator_group_payload_for_llm(rows, arguments),
            generated_files=generated_files,
        )

    def summarize_monetary_cost(self, context: ToolContext, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        arguments = arguments or {}
        evaluation = self._require_evaluation(context)

        monetary_cost_detail = self._read_required_detail(evaluation, "monetary_cost")
        if monetary_cost_detail is None:
            return 

        summary = self._summarize_monetary_cost(monetary_cost_detail, evaluation.metrics)
        return ToolResult(
            name="summarize_monetary_cost",
            payload={"monetary_cost": self._monetary_cost_payload_for_llm(summary, arguments)},
        )

    def summarize_hardware_config(self, context: ToolContext, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        arguments = arguments or {}
        hardware = self._require_hardware(context)
        search_space = (context.simulator_schema or {}).get("search_space", {}) or DEFAULT_HARDWARE_SEARCH_SPACE
        summary = self._summarize_hardware(hardware, search_space)
        if self._truthy(arguments.get("include_design_space"), default=True):
            summary["search_space_position"] = self._search_space_position(
                hardware,
                search_space,
            )
        payload: Dict[str, Any] = {"hardware": summary}
        if self._truthy(arguments.get("include_full_hardware"), default=False):
            payload["full_hardware"] = hardware
            payload["full_hardware_note"] = (
                "Chiplets are returned in simulator order. Interpret chiplet_layout.type_grid as a compact "
                "row-major view only when chip_x/chip_y match the simulator mapping convention."
            )
        return ToolResult(name="summarize_hardware_config", payload=payload)

    def materialize_hardware_candidate(self, context: ToolContext, update: Dict[str, Any]) -> ToolResult:
        hardware = self._require_hardware(context)
        search_space = self._search_space(context)
        proposed = self._candidate_update_to_hardware_payload(update)
        updated, validation_notes = normalize_hardware_to_design_space(
            proposed=proposed,
            current=hardware,
            search_space=search_space,
        )
        return self._hardware_candidate_result(
            context=context,
            tool_name="materialize_hardware_candidate",
            current=hardware,
            updated=updated,
            search_space=search_space,
            requested_update=update,
            validation_notes=validation_notes,
            include_full_hardware=self._truthy(update.get("include_full_hardware"), default=False),
        )

    def modify_hardware_parameter(self, context: ToolContext, arguments: Dict[str, Any]) -> ToolResult:
        hardware = self._require_hardware(context)
        search_space = self._search_space(context)
        updates = self._normalize_direct_updates(arguments)
        proposed: Dict[str, Any] = {}
        chiplet_types: Optional[List[Any]] = None
        compute_values: Optional[List[Any]] = None
        buffer_values: Optional[List[Any]] = None
        for key in [
            "chiplet_spec_strategy",
            "resource_strategy",
            "chiplet_type_strategy",
            "type_strategy",
            "chiplet_type_fill",
            "fill_chiplet_type",
            "uniform_chiplet_type",
        ]:
            if key in arguments:
                proposed[key] = arguments[key]
        if "chiplet_type" in arguments and arguments.get("chiplet_type_strategy") in {"uniform", "all", "set_all"}:
            proposed["chiplet_type_fill"] = arguments["chiplet_type"]

        for update in updates:
            parameter = str(update["parameter"]).strip()
            value = update["value"]
            for key in [
                "chiplet_spec_strategy",
                "resource_strategy",
                "chiplet_type_strategy",
                "type_strategy",
                "chiplet_type_fill",
                "fill_chiplet_type",
                "uniform_chiplet_type",
            ]:
                if key in update:
                    proposed[key] = update[key]
            if parameter in {"chiplet_type", "type", "chiplets.type"}:
                chiplet_types = self._apply_chiplet_type_value(
                    hardware=hardware,
                    current_types=chiplet_types,
                    value=value,
                    update=update,
                    search_space=search_space,
                )
            elif parameter in {"compute_units", "chiplets.compute_units"}:
                compute_values = self._apply_chiplet_field_value(
                    hardware=hardware,
                    current_values=compute_values,
                    field="compute_units",
                    value=value,
                    update=update,
                    search_space=search_space,
                )
            elif parameter in {"buffer_size", "chiplets.buffer_size"}:
                buffer_values = self._apply_chiplet_field_value(
                    hardware=hardware,
                    current_values=buffer_values,
                    field="buffer_size",
                    value=value,
                    update=update,
                    search_space=search_space,
                )
            elif parameter in {"chip_size", "chip_spec", "compute_spec"}:
                proposed[parameter] = value
            elif parameter in {"dram_bw", "nop_bw", "micro_batch", "tensor_parall"}:
                proposed[parameter] = value
            elif parameter in {"chip_x", "chip_y", "chip_shape", "shape", "array_shape"}:
                raise ValueError(
                    "modify_hardware_parameter accepts num_chiplets only; chip_y/chip_x/shape are derived fields."
                )
            elif parameter == "num_chiplets":
                proposed.update(self._shape_payload_for_update(parameter, value, {**hardware, **proposed}))
            else:
                raise ValueError(f"Unsupported hardware parameter for direct modification: {parameter}")

        if chiplet_types is not None:
            proposed["chiplet_types"] = chiplet_types
        if compute_values is not None:
            proposed["compute_units"] = compute_values
        if buffer_values is not None:
            proposed["buffer_size"] = buffer_values
        updated, validation_notes = normalize_hardware_to_design_space(
            proposed=proposed,
            current=hardware,
            search_space=search_space,
        )
        return self._hardware_candidate_result(
            context=context,
            tool_name="modify_hardware_parameter",
            current=hardware,
            updated=updated,
            search_space=search_space,
            requested_update={"updates": updates},
            validation_notes=validation_notes or ["candidate generated by modify_hardware_parameter"],
            include_full_hardware=self._truthy(arguments.get("include_full_hardware"), default=False),
        )

    def step_hardware_parameter(self, context: ToolContext, arguments: Dict[str, Any]) -> ToolResult:
        hardware = self._require_hardware(context)
        search_space = self._search_space(context)
        parameter = str(arguments.get("parameter", "")).strip()
        if not parameter:
            raise ValueError("step_hardware_parameter requires non-empty parameter.")
        direction = int(arguments.get("direction", 1))
        if direction == 0:
            raise ValueError("step_hardware_parameter direction must be non-zero.")

        if parameter in {"array_shape", "shape", "chip_shape"}:
            raise ValueError("step_hardware_parameter accepts num_chiplets only; chip_y/chip_x/shape are derived fields.")
        if parameter == "num_chiplets":
            shape = step_array_shape(hardware, search_space, 1 if direction > 0 else -1)
            updated = materialize_hardware(
                template=hardware,
                num_chiplets=shape["num_chiplets"],
                search_space=search_space,
                chiplet_spec_strategy=str(arguments.get("chiplet_spec_strategy", "preserve_prefix")),
                chiplet_type_strategy=str(arguments.get("chiplet_type_strategy", "preserve_prefix")),
                chiplet_type_fill=arguments.get("chiplet_type_fill", arguments.get("fill_chiplet_type")),
            )
        elif parameter in {"compute_units", "buffer_size"}:
            scope = self._require_step_scope(arguments, parameter)
            updated, _actions = step_chiplet_resource(
                hardware=hardware,
                search_space=search_space,
                field=parameter,
                direction=1 if direction > 0 else -1,
                scope=scope,
            )
        elif parameter in {"chiplet_type", "type"}:
            self._require_step_scope(arguments, "chiplet_type")
            updated = self._step_chiplet_type_candidate(hardware, search_space, direction, arguments)
        else:
            updated = self._step_system_param_candidate(hardware, search_space, parameter, direction)

        return self._hardware_candidate_result(
            context=context,
            tool_name="step_hardware_parameter",
            current=hardware,
            updated=updated,
            search_space=search_space,
            requested_update=arguments,
            validation_notes=["candidate generated by step_hardware_parameter"],
            include_full_hardware=self._truthy(arguments.get("include_full_hardware"), default=False),
        )

    def _search_space(self, context: ToolContext) -> Dict[str, Any]:
        return (context.simulator_schema or {}).get("search_space", {}) or DEFAULT_HARDWARE_SEARCH_SPACE

    def _candidate_update_to_hardware_payload(self, update: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(update, dict):
            raise ValueError("Hardware candidate update must be an object.")
        derived_shape_fields = {"shape", "array_shape", "chip_shape", "chip_y", "chip_x"}
        if derived_shape_fields & set(update):
            raise ValueError(
                "Hardware candidate updates must request num_chiplets only; chip_y/chip_x/shape are derived fields."
            )
        payload: Dict[str, Any] = {}
        for key in [
            "num_chiplets",
            "compute_units",
            "buffer_size",
            "per_chiplet_specs",
            "chiplet_specs",
            "chiplets",
            "chip_size",
            "chip_spec",
            "compute_spec",
            "chiplet_spec_strategy",
            "resource_strategy",
            "compute_unit_fill",
            "buffer_size_fill",
            "uniform_compute_units",
            "uniform_buffer_size",
        ]:
            if key in update:
                payload[key] = update[key]
        system_params = update.get("system_params")
        if isinstance(system_params, dict):
            payload.update(system_params)
        for key in ["dram_bw", "nop_bw", "micro_batch", "tensor_parall"]:
            if key in update:
                payload[key] = update[key]
        for key in [
            "chiplet_type_strategy",
            "type_strategy",
            "chiplet_type_fill",
            "fill_chiplet_type",
            "uniform_chiplet_type",
        ]:
            if key in update:
                payload[key] = update[key]
        if "chiplet_types" in update:
            payload["chiplet_types"] = update["chiplet_types"]
        elif "chiplet_type" in update:
            payload["chiplet_type"] = update["chiplet_type"]
        return payload

    def _normalize_direct_updates(self, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(arguments, dict):
            raise ValueError("modify_hardware_parameter arguments must be an object.")
        raw_updates = arguments.get("updates")
        single_update_keys = {"parameter", "value", "scope", "indices"}
        if raw_updates is not None and single_update_keys & set(arguments):
            raise ValueError(
                "modify_hardware_parameter accepts either top-level parameter/value/scope/indices or updates, not both."
            )
        if raw_updates is None:
            if "parameter" not in arguments or "value" not in arguments:
                raise ValueError("modify_hardware_parameter requires parameter/value or updates.")
            raw_updates = [arguments]
        if not isinstance(raw_updates, list) or not raw_updates:
            raise ValueError("modify_hardware_parameter updates must be a non-empty list.")
        updates: List[Dict[str, Any]] = []
        for item in raw_updates:
            if not isinstance(item, dict):
                raise ValueError(f"Each hardware update must be an object, got {item!r}")
            parameter = str(item.get("parameter", "")).strip()
            if not parameter:
                raise ValueError(f"Hardware update missing parameter: {item!r}")
            if "value" not in item:
                raise ValueError(f"Hardware update missing value: {item!r}")
            normalized = dict(item)
            normalized["parameter"] = parameter
            updates.append(normalized)
        return updates

    def _apply_chiplet_type_value(
        self,
        hardware: Dict[str, Any],
        current_types: Optional[List[Any]],
        value: Any,
        update: Dict[str, Any],
        search_space: Dict[str, Any],
    ) -> List[Any]:
        legal_types = chip_type_candidates(search_space)
        chip_type = str(value)
        if chip_type not in legal_types:
            raise ValueError(f"Invalid chiplet_type {chip_type!r}; legal values are {legal_types}")
        source_types = list(current_types or [chip.get("type") for chip in hardware.get("chiplets", []) if isinstance(chip, dict)])
        if not source_types:
            raise ValueError("Current hardware does not contain chiplet type information.")
        if "chiplet_type_scope" in update:
            raise ValueError("modify_hardware_parameter uses scope only; chiplet_type_scope is not accepted.")
        scope = str(update.get("scope", "all"))
        if scope == "all":
            return [chip_type for _ in source_types]
        if scope == "first":
            source_types[0] = chip_type
            return source_types
        if scope == "indices":
            indices = update.get("indices", [])
            if not isinstance(indices, list) or not indices:
                raise ValueError("chiplet_type update with scope=indices requires non-empty indices list.")
            for raw_idx in indices:
                idx = int(raw_idx)
                if idx < 0 or idx >= len(source_types):
                    raise ValueError(f"chiplet index {idx} out of range for {len(source_types)} chiplets")
                source_types[idx] = chip_type
            return source_types
        raise ValueError(f"Unsupported chiplet_type scope: {scope}")

    def _apply_chiplet_field_value(
        self,
        hardware: Dict[str, Any],
        current_values: Optional[List[Any]],
        field: str,
        value: Any,
        update: Dict[str, Any],
        search_space: Dict[str, Any],
    ) -> List[Any]:
        candidates = compute_unit_candidates(search_space) if field == "compute_units" else buffer_size_candidates(search_space)
        source_values = list(
            current_values
            or [chip.get(field) for chip in hardware.get("chiplets", []) if isinstance(chip, dict)]
        )
        if not source_values:
            raise ValueError(f"Current hardware does not contain {field} information.")
        coerced = coerce_to_candidates(value, None, candidates, key=field)
        scope = str(update.get("scope", "all"))
        if scope == "all":
            return [coerced for _ in source_values]
        if scope == "first":
            source_values[0] = coerced
            return source_values
        if scope == "indices":
            indices = update.get("indices", [])
            if not isinstance(indices, list) or not indices:
                raise ValueError(f"{field} update with scope=indices requires non-empty indices list.")
            for raw_idx in indices:
                idx = int(raw_idx)
                if idx < 0 or idx >= len(source_values):
                    raise ValueError(f"chiplet index {idx} out of range for {len(source_values)} chiplets")
                source_values[idx] = coerced
            return source_values
        raise ValueError(f"Unsupported {field} scope: {scope}")

    def _shape_payload_for_update(self, parameter: str, value: Any, hardware: Dict[str, Any]) -> Dict[str, Any]:
        if parameter == "num_chiplets":
            return {"num_chiplets": value}
        if parameter == "chip_x":
            return {"chip_x": value, "chip_y": hardware.get("chip_y")}
        if parameter == "chip_y":
            return {"chip_y": value, "chip_x": hardware.get("chip_x")}
        return {"shape": value}

    def _step_system_param_candidate(
        self,
        hardware: Dict[str, Any],
        search_space: Dict[str, Any],
        parameter: str,
        direction: int,
    ) -> Dict[str, Any]:
        candidates = all_system_param_candidates(search_space).get(parameter)
        if not candidates:
            raise ValueError(f"Unknown or non-system hardware parameter: {parameter}")
        if parameter not in hardware:
            raise ValueError(f"Current hardware does not contain system parameter: {parameter}")
        proposed = {parameter: clamp_to_candidates(int(hardware[parameter]), candidates, 1 if direction > 0 else -1)}
        updated, _notes = normalize_hardware_to_design_space(
            proposed=proposed,
            current=hardware,
            search_space=search_space,
        )
        return updated

    def _step_chiplet_type_candidate(
        self,
        hardware: Dict[str, Any],
        search_space: Dict[str, Any],
        direction: int,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidates = chip_type_candidates(search_space)
        if len(candidates) < 2:
            raise ValueError("chiplet_type step requires at least two legal chiplet types.")
        current_types = [chip.get("type") for chip in hardware.get("chiplets", []) if isinstance(chip, dict)]
        if not current_types:
            raise ValueError("Current hardware does not contain chiplet type information.")
        scope = self._require_step_scope(arguments, "chiplet_type")
        new_types = list(current_types)
        indices = range(len(new_types)) if scope == "all" else range(1)
        for idx in indices:
            old_type = str(new_types[idx])
            old_idx = candidates.index(old_type) if old_type in candidates else 0
            new_idx = max(0, min(len(candidates) - 1, old_idx + (1 if direction > 0 else -1)))
            new_types[idx] = candidates[new_idx]
        updated, _notes = normalize_hardware_to_design_space(
            proposed={"chiplet_types": new_types},
            current=hardware,
            search_space=search_space,
        )
        return updated

    def _require_step_scope(self, arguments: Dict[str, Any], parameter: str) -> str:
        if "chiplet_type_scope" in arguments:
            raise ValueError("step_hardware_parameter uses scope only; chiplet_type_scope is not accepted.")
        if "scope" not in arguments:
            raise ValueError(
                f"step_hardware_parameter requires explicit scope=first|all for per-chiplet parameter {parameter!r}."
            )
        scope = str(arguments.get("scope", "")).strip()
        if scope not in {"first", "all"}:
            raise ValueError(
                f"step_hardware_parameter scope for {parameter!r} must be 'first' or 'all', got {scope!r}."
            )
        return scope

    def _hardware_candidate_result(
        self,
        context: ToolContext,
        tool_name: str,
        current: Dict[str, Any],
        updated: Dict[str, Any],
        search_space: Dict[str, Any],
        requested_update: Dict[str, Any],
        validation_notes: List[str],
        include_full_hardware: bool,
    ) -> ToolResult:
        artifact_path = self._write_hardware_candidate_artifact(context, tool_name, updated)
        payload = self._hardware_candidate_payload(
            current=current,
            updated=updated,
            search_space=search_space,
            requested_update=requested_update,
            validation_notes=validation_notes,
            include_full_hardware=include_full_hardware,
        )
        payload["candidate_artifact"] = str(artifact_path)
        payload["full_hardware_note"] = (
            "The default candidate result is compact. Use include_full_hardware=true only when exact "
            "simulator-order chiplet JSON is needed; otherwise use updated_hardware_summary and actions."
        )
        return ToolResult(
            name=tool_name,
            payload=payload,
            generated_files={"hardware_candidate_json": str(artifact_path)},
        )

    def _write_hardware_candidate_artifact(
        self,
        context: ToolContext,
        tool_name: str,
        updated: Dict[str, Any],
    ) -> Path:
        candidates_dir = context.output_dir / "analysis" / "hardware_candidates"
        candidates_dir.mkdir(parents=True, exist_ok=True)
        fingerprint = hardware_fingerprint(updated)
        path = candidates_dir / f"{tool_name}_{fingerprint}.json"
        write_json(path, updated)
        return path

    def _hardware_candidate_payload(
        self,
        current: Dict[str, Any],
        updated: Dict[str, Any],
        search_space: Dict[str, Any],
        requested_update: Dict[str, Any],
        validation_notes: List[str],
        include_full_hardware: bool = False,
    ) -> Dict[str, Any]:
        payload = {
            "requested_update": requested_update,
            "updated_hardware_summary": self._summarize_hardware(updated, search_space),
            "actions": self._hardware_diff_actions(current, updated, search_space),
            "validation": validation_notes,
            "updated_hardware_fingerprint": hardware_fingerprint(updated),
            "search_space_position": self._search_space_position(updated, search_space),
            "full_hardware_included": include_full_hardware,
        }
        if include_full_hardware:
            payload["updated_hardware"] = updated
        return payload

    def _hardware_diff_actions(
        self,
        old: Dict[str, Any],
        new: Dict[str, Any],
        search_space: Dict[str, Any],
    ) -> List[str]:
        actions: List[str] = []
        for key in ["num_chiplets", "chip_x", "chip_y", "dram_bw", "nop_bw", "micro_batch", "tensor_parall"]:
            if old.get(key) != new.get(key):
                actions.append(f"{key}: {old.get(key)}->{new.get(key)}")
        old_chiplets = old.get("chiplets", [])
        new_chiplets = new.get("chiplets", [])
        if isinstance(old_chiplets, list) and isinstance(new_chiplets, list) and old_chiplets and new_chiplets:
            for key in ["type", "compute_units", "buffer_size", "macs"]:
                old_values = Counter(str(chip.get(key)) for chip in old_chiplets if isinstance(chip, dict))
                new_values = Counter(str(chip.get(key)) for chip in new_chiplets if isinstance(chip, dict))
                if old_values != new_values:
                    actions.append(f"chiplets.{key}: {dict(old_values)}->{dict(new_values)}")
        return actions

    def _require_evaluation(self, context: ToolContext) -> EvaluationResult:
        if context.evaluation is None:
            raise ValueError("This tool requires evaluation context.")
        return context.evaluation

    def _require_hardware(self, context: ToolContext) -> Dict[str, Any]:
        if context.current_hardware is not None:
            return context.current_hardware
        if context.evaluation is not None:
            return context.evaluation.hardware
        raise ValueError("This tool requires current_hardware context.")

    def _analysis_dir(self, context: ToolContext) -> Path:
        if context.evaluation is not None and context.active_base:
            stats_dir = context.evaluation.run_dir / "analysis"
        else:
            stats_dir = context.output_dir / "analysis"
        stats_dir.mkdir(parents=True, exist_ok=True)
        return stats_dir

    def _decision_analysis_dir(self, context: ToolContext) -> Path:
        stats_dir = context.output_dir / "analysis"
        stats_dir.mkdir(parents=True, exist_ok=True)
        return stats_dir

    def _record_artifact_reference(
        self,
        context: ToolContext,
        tool_name: str,
        arguments: Dict[str, Any],
        generated_files: Dict[str, str],
        reused: bool,
    ) -> None:
        record = {
            "tool": tool_name,
            "arguments": arguments,
            "base": context.active_base or self._active_base_from_evaluation(context),
            "evaluation_run_dir": str(context.evaluation.run_dir) if context.evaluation is not None else None,
            "files": generated_files,
            "reused": reused,
        }
        manifest_path = self._decision_analysis_dir(context) / "artifact_references.json"
        references: List[Dict[str, Any]] = []
        if manifest_path.exists():
            try:
                existing = read_json(manifest_path)
                raw_refs = existing.get("references", [])
                if isinstance(raw_refs, list):
                    references.extend(item for item in raw_refs if isinstance(item, dict))
            except Exception:
                references = []
        references.append(record)
        context.artifact_references = references
        write_json(
            manifest_path,
            {
                "references": references,
            },
        )

    def _active_base_from_evaluation(self, context: ToolContext) -> Dict[str, Any]:
        if context.evaluation is None:
            return {}
        return {
            "source": "current",
            "iteration": self._iteration_from_run_dir(context.evaluation.run_dir),
            "run_dir": str(context.evaluation.run_dir),
            "hardware_fingerprint": hardware_fingerprint(context.evaluation.hardware),
        }

    def _resolve_base_key(self, arguments: Dict[str, Any]) -> Tuple[str, str, Optional[int]]:
        if "iteration" in arguments and arguments.get("iteration") is not None:
            iteration = int(arguments["iteration"])
            return f"iter_{iteration:03d}", "iteration", iteration
        source = str(arguments.get("source", "current")).strip() or "current"
        if source not in {"current", "previous", "best"}:
            raise ValueError("select_analysis_base source must be current, previous, or best when iteration is omitted.")
        return source, source, None

    def _base_record_from_search_state(self, context: ToolContext, key: str) -> Optional[Dict[str, Any]]:
        state = context.search_state
        if not isinstance(state, dict):
            return None
        bases = state.get("bases", {})
        if isinstance(bases, dict) and isinstance(bases.get(key), dict):
            return bases[key]
        for candidate_key in ["current", "previous", "best"]:
            record = state.get(candidate_key)
            if isinstance(record, dict) and record.get("base_key") == key:
                return record
        return None

    def _evaluation_base_record(
        self,
        source: str,
        iteration: Optional[int],
        evaluation: EvaluationResult,
        search_space: Dict[str, Any],
    ) -> Dict[str, Any]:
        metrics = self._metrics_with_objective(evaluation.metrics)
        return {
            "source": source,
            "iteration": iteration,
            "base_key": f"iter_{iteration:03d}" if iteration is not None else source,
            "run_dir": str(evaluation.run_dir),
            "metrics": metrics,
            "objective": metrics["objective"],
            "hardware_fingerprint": hardware_fingerprint(evaluation.hardware),
            "hardware_summary": self._summarize_hardware(evaluation.hardware, search_space),
        }

    def _iteration_from_run_dir(self, run_dir: Path) -> Optional[int]:
        name = run_dir.name
        if name.startswith("iter_"):
            try:
                return int(name.split("_", 1)[1])
            except (IndexError, ValueError):
                return None
        return None

    def _layer_selection_arguments(self, selected: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "layers": [
                {
                    "layer_id": item.get("layer_id", item.get("layerID")),
                    "layer_name": item.get("layer_name", item.get("layerName")),
                }
                for item in selected
            ]
        }

    def _compact_search_state_payload(self, state: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
        include_hardware = self._truthy(arguments.get("include_hardware"), default=True)
        detail_level = str(arguments.get("detail_level", "summary")).strip() or "summary"
        include_history = self._truthy(arguments.get("include_history"), default=False) or detail_level == "recent"
        history_limit = self._resolve_limit(
            arguments.get("history_limit"),
            default=DEFAULT_TOOL_TOP_ITEMS,
            cap=MAX_HISTORY_ITEMS,
            name="history_limit",
        )
        bases = state.get("bases", {}) if isinstance(state.get("bases"), dict) else {}
        iteration_records = self._unique_iteration_records(bases)
        payload: Dict[str, Any] = {
            "current": self._compact_search_record(state.get("current"), include_hardware=include_hardware),
            "best": self._compact_search_record(state.get("best"), include_hardware=include_hardware),
            "previous": self._compact_search_record(state.get("previous"), include_hardware=include_hardware),
            "last_applied_change": self._compact_change_record(state.get("last_applied_change")),
            "search_observation": self._compact_search_observation(state.get("search_observation")),
            "selectable_sources": [name for name in ["current", "previous", "best"] if state.get(name)],
            "objective_change_convention": "(after - before) / before; negative means objective decreased and improved",
            "available_iteration_count": len(iteration_records),
        }
        if iteration_records:
            payload["available_iteration_range"] = {
                "first": iteration_records[0].get("iteration"),
                "last": iteration_records[-1].get("iteration"),
            }
        if include_history:
            payload["recent_iterations"] = [
                self._compact_search_record(record, include_hardware=include_hardware)
                for record in iteration_records[-history_limit:]
            ]
            payload["history_limit"] = history_limit
        return payload

    def _unique_iteration_records(self, bases: Dict[str, Any]) -> List[Dict[str, Any]]:
        by_iteration: Dict[int, Dict[str, Any]] = {}
        for record in bases.values():
            if not isinstance(record, dict):
                continue
            iteration = record.get("iteration")
            if iteration is None:
                continue
            by_iteration[int(iteration)] = record
        return [by_iteration[key] for key in sorted(by_iteration)]

    def _compact_search_record(self, record: Any, include_hardware: bool = True) -> Optional[Dict[str, Any]]:
        if not isinstance(record, dict):
            return None
        compact: Dict[str, Any] = {
            "source": record.get("source"),
            "base_key": record.get("base_key"),
            "iteration": record.get("iteration"),
            "metrics": self._compact_metrics(record.get("metrics", {})),
        }
        objective = record.get("objective")
        if objective is not None:
            compact["objective"] = objective
        if include_hardware and isinstance(record.get("hardware_summary"), dict):
            compact["hardware_summary"] = record["hardware_summary"]
        return {key: value for key, value in compact.items() if value is not None}

    def _compact_metrics(self, metrics: Any) -> Dict[str, Any]:
        if not isinstance(metrics, dict):
            return {}
        keep = ["latency", "energy", "mc", "objective", "edp"]
        return {key: metrics[key] for key in keep if key in metrics}

    def _compact_search_observation(self, observation: Any) -> Dict[str, Any]:
        if not isinstance(observation, dict):
            return {}
        keep = [
            "current_is_best",
            "best_iteration",
            "objective_change_vs_previous",
            "last_change_improved_objective",
            "suggested_base_choices",
        ]
        return {key: observation[key] for key in keep if key in observation}

    def _compact_change_record(self, change: Any) -> Dict[str, Any]:
        if not isinstance(change, dict):
            return {}
        keep = [
            "source_iteration",
            "target_iteration",
            "strategy",
            "actions",
            "objective_change_vs_previous",
            "objective_change_vs_initial",
            "objective",
            "previous_objective",
        ]
        compact = {key: change[key] for key in keep if key in change}
        if "solution" in change and isinstance(change["solution"], dict):
            solution = change["solution"]
            compact.setdefault("strategy", solution.get("strategy"))
            compact.setdefault("actions", solution.get("actions"))
        return {key: value for key, value in compact.items() if value not in (None, [], {})}

    def _timeline_payload_for_llm(self, payload: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
        include_rows = self._truthy(arguments.get("include_sample_rows"), default=False)
        sample_limit = self._resolve_limit(
            arguments.get("sample_limit"),
            default=DEFAULT_TOOL_TOP_ITEMS,
            cap=MAX_TOOL_TOP_ITEMS,
            name="sample_limit",
        )
        compact = {"timeline": payload.get("timeline", {})}
        if include_rows:
            rows = payload.get("sample_rows", [])
            compact["sample_rows"] = [
                self._compact_timeline_row(row)
                for row in rows[:sample_limit]
                if isinstance(row, dict)
            ]
            compact["sample_limit"] = sample_limit
        else:
            compact["sample_rows_available"] = len(payload.get("sample_rows", []) or [])
        return compact

    def _compact_timeline_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "core": row.get("core"),
            "batchID": row.get("batchID"),
            "layer_id": row.get("layerID"),
            "layer_name": row.get("layerName"),
            "group": row.get("group"),
            "begin": row.get("latencyBegin"),
            "end": row.get("latencyEnd"),
            "duration": row.get("duration"),
            "calc_time": row.get("calcTime"),
            "noc_time": row.get("nocTime"),
            "dram_time": row.get("dramTime"),
        }

    def _query_layer_loads_payload(
        self,
        all_loads: List[Dict[str, Any]],
        evaluation: EvaluationResult,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        metrics = self._metrics_with_objective(evaluation.metrics)
        groups = {str(item) for item in arguments.get("groups", []) if item is not None} if isinstance(arguments.get("groups"), list) else set()
        filtered = [layer for layer in all_loads if not groups or str(layer.get("group")) in groups]
        view = str(arguments.get("view", "") or "").strip()
        if not view:
            if arguments.get("layer_ids") or arguments.get("layer_names") or arguments.get("layers"):
                view = "layers"
            elif arguments.get("rank_by"):
                view = "ranked"
            elif groups:
                view = "groups"
            else:
                view = "summary"
        top_layers = self._resolve_limit(
            arguments.get("top_layers"),
            default=DEFAULT_TOOL_TOP_ITEMS,
            cap=MAX_TOOL_TOP_ITEMS,
            name="top_layers",
        )
        fields = self._normalize_layer_fields(
            arguments.get("include_fields"),
            default={"basic", "shares", "timing", "breakdown", "root_cause"},
        )
        base_payload: Dict[str, Any] = {
            "view": view,
            "metrics": metrics,
            "layer_count": len(all_loads),
            "filtered_layer_count": len(filtered),
            "aggregate_breakdown": self._summarize_breakdowns(filtered),
        }
        if view == "summary":
            summary_views = {}
            for rank_by in ["latency_sum", "energy", "critical_end"]:
                summary_views[rank_by] = self._rank_layers(filtered, rank_by, top_layers=3, metrics=metrics, fields=fields)
            base_payload["top_layers_by"] = summary_views
            base_payload["available_views"] = ["summary", "ranked", "layers", "groups"]
            return base_payload
        if view == "ranked":
            rank_by = str(arguments.get("rank_by", "latency_sum"))
            base_payload["rank_by"] = rank_by
            base_payload["top_layers"] = top_layers
            base_payload["ranked_layers"] = self._rank_layers(filtered, rank_by, top_layers=top_layers, metrics=metrics, fields=fields)
            return base_payload
        if view == "layers":
            selected = self._select_layers(
                filtered,
                layers=arguments.get("layers"),
                layer_ids=arguments.get("layer_ids"),
                layer_names=arguments.get("layer_names"),
            )
            selected = selected[:top_layers]
            base_payload["layers"] = [
                self._compact_layer_record(layer, metrics=metrics, include_fields=fields)
                for layer in selected
            ]
            base_payload["returned_layers"] = len(selected)
            return base_payload
        if view == "groups":
            return {
                **base_payload,
                **self._operator_group_payload_for_llm(self._summarize_operator_groups(filtered), arguments),
            }
        raise ValueError("aggregate_layer_loads view must be summary, ranked, layers, or groups.")

    def _rank_layers(
        self,
        layers: List[Dict[str, Any]],
        rank_by: str,
        top_layers: int,
        metrics: Dict[str, Any],
        fields: set[str],
    ) -> List[Dict[str, Any]]:
        key_fn = self._layer_rank_key(rank_by)
        ordered = sorted(layers, key=key_fn, reverse=True)
        return [
            self._compact_layer_record(
                layer,
                metrics=metrics,
                include_fields=fields,
                rank_metric=rank_by,
                rank_value=key_fn(layer),
            )
            for layer in ordered[:top_layers]
        ]

    def _compact_rank_views(self, rank_views: Any) -> Dict[str, List[Dict[str, Any]]]:
        if not isinstance(rank_views, dict):
            return {}
        compact: Dict[str, List[Dict[str, Any]]] = {}
        for view_name, records in rank_views.items():
            if not isinstance(records, list):
                continue
            compact[str(view_name)] = [
                self._compact_layer_record(
                    record,
                    include_fields={"basic", "placement", "timing", "energy", "root_cause"},
                    rank_metric=str(record.get("rank_metric", view_name)),
                    rank_value=record.get("rank_value"),
                )
                for record in records[:MAX_LAYER_RANK_TOP_LAYERS]
                if isinstance(record, dict)
            ]
        return compact

    def _layer_rank_key(self, rank_by: str):
        rank_by = str(rank_by)
        keys = {
            "latency_sum": lambda layer: float(layer.get("latency_sum", 0.0)),
            "latency": lambda layer: float(layer.get("latency_sum", 0.0)),
            "energy": lambda layer: float(layer.get("energy", 0.0)),
            "critical_end": lambda layer: float(layer.get("critical_end", 0.0)),
            "compute": lambda layer: self._dimension_evidence_value(layer, "compute"),
            "memory": lambda layer: self._dimension_evidence_value(layer, "memory"),
            "communication": lambda layer: self._dimension_evidence_value(layer, "communication"),
            "buffer": lambda layer: self._dimension_evidence_value(layer, "buffer"),
        }
        if rank_by not in keys:
            raise ValueError(f"Unsupported layer rank metric {rank_by!r}; expected one of {sorted(keys)}")
        return keys[rank_by]

    def _dimension_evidence_value(self, layer: Dict[str, Any], dimension: str) -> float:
        time_breakdown = layer.get("time_breakdown", {})
        energy_breakdown = layer.get("energy_breakdown", {})
        if not isinstance(time_breakdown, dict):
            time_breakdown = {}
        if not isinstance(energy_breakdown, dict):
            energy_breakdown = {}
        if dimension == "compute":
            return float(time_breakdown.get("compute", 0.0) or 0.0)
        if dimension == "memory":
            return max(
                float(time_breakdown.get("memory", 0.0) or 0.0),
                float(energy_breakdown.get("memory", 0.0) or 0.0),
            )
        if dimension == "communication":
            return max(
                float(time_breakdown.get("communication", 0.0) or 0.0),
                float(energy_breakdown.get("communication", 0.0) or 0.0),
            )
        if dimension == "buffer":
            return float(energy_breakdown.get("buffer", 0.0) or 0.0)
        return 0.0

    def _root_causes_from_breakdown(self, layer: Dict[str, Any]) -> List[str]:
        evidence = {
            "compute": self._dimension_evidence_value(layer, "compute"),
            "memory": self._dimension_evidence_value(layer, "memory"),
            "communication": self._dimension_evidence_value(layer, "communication"),
            "buffer": self._dimension_evidence_value(layer, "buffer"),
        }
        root_causes = [
            dim
            for dim, value in sorted(evidence.items(), key=lambda item: float(item[1]), reverse=True)
            if float(value) >= 0.2
        ]
        if not root_causes and layer.get("dominant_dimension"):
            root_causes = [str(layer["dominant_dimension"])]
        return root_causes or ["unknown"]

    def _normalize_layer_fields(self, raw_fields: Any, default: set[str]) -> set[str]:
        if raw_fields in (None, ""):
            return set(default)
        if isinstance(raw_fields, str):
            fields = {item.strip() for item in raw_fields.split(",") if item.strip()}
        elif isinstance(raw_fields, list):
            fields = {str(item).strip() for item in raw_fields if str(item).strip()}
        else:
            raise ValueError("include_fields must be a list or comma-separated string.")
        dimension_aliases = {"compute", "memory", "communication", "buffer"}
        requested_dimensions = fields & dimension_aliases
        if requested_dimensions:
            fields -= dimension_aliases
            fields.update({"root_cause", "breakdown", "energy", "energy_components"})
        allowed = {"basic", "shares", "placement", "timing", "energy", "energy_components", "breakdown", "root_cause", "features"}
        unknown = fields - allowed
        if unknown:
            raise ValueError(f"Unknown include_fields values: {sorted(unknown)}")
        fields.add("basic")
        return fields

    def _compact_layer_record(
        self,
        layer: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        include_fields: Optional[set[str]] = None,
        rank_metric: Optional[str] = None,
        rank_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        fields = include_fields or {"basic", "shares", "timing", "breakdown", "root_cause"}
        record: Dict[str, Any] = {
            "layer_id": layer.get("layer_id", layer.get("layerID")),
            "layer_name": layer.get("layer_name", layer.get("layerName")),
            "operator_group": layer.get("group"),
        }
        if rank_metric is not None:
            record["rank_metric"] = rank_metric
            record["rank_value"] = rank_value
        if "shares" in fields and isinstance(metrics, dict):
            latency = max(float(metrics.get("latency", 0.0) or 0.0), 1.0)
            energy = max(float(metrics.get("energy", 0.0) or 0.0), 1.0)
            record["shares"] = {
                "latency_sum_share": float(layer.get("latency_sum", 0.0)) / latency,
                "energy_share": float(layer.get("energy", 0.0)) / energy,
            }
        if "placement" in fields:
            cores = list(layer.get("cores", []) or [])
            batches = list(layer.get("batches", []) or [])
            record["placement"] = {
                "occurrences": layer.get("occurrences", 0),
                "core_count": len(cores),
                "cores": cores[:8],
                "batch_count": len(batches),
            }
        if "timing" in fields:
            record["timing"] = {
                "latency_sum": layer.get("latency_sum"),
                "latency_max": layer.get("latency_max"),
                "critical_end": layer.get("critical_end"),
                "calc_time": layer.get("calc_time"),
                "noc_time": layer.get("noc_time"),
                "dram_time": layer.get("dram_time"),
            }
        if "energy" in fields:
            record["energy"] = {
                "total": layer.get("energy"),
            }
            if "energy_components" in fields:
                record["energy"].update({
                "calc_energy": layer.get("calc_energy"),
                "ubuf_energy": layer.get("ubuf_energy"),
                "noc_energy": layer.get("noc_energy"),
                "dram_energy": layer.get("dram_energy"),
                })
        if "breakdown" in fields:
            record["breakdown"] = {
                "time": layer.get("time_breakdown", {}),
                "energy": layer.get("energy_breakdown", {}),
            }
        if "root_cause" in fields:
            record["root_cause"] = {
                "dominant_dimension": layer.get("dominant_dimension"),
            }
        if "features" in fields:
            features = dict(layer.get("features", {}) or {})
            features.pop("bottleneck_evidence", None)
            record["features"] = features
        return record

    def _operator_group_payload_for_llm(self, rows: List[Dict[str, Any]], arguments: Dict[str, Any]) -> Dict[str, Any]:
        sort_by = str(arguments.get("sort_by", "latency_sum"))
        if sort_by not in {"latency_sum", "energy", "layers", "occurrences"}:
            raise ValueError("summarize_operator_groups sort_by must be latency_sum, energy, layers, or occurrences.")
        top_groups = self._resolve_limit(
            arguments.get("top_groups"),
            default=DEFAULT_TOOL_TOP_ITEMS,
            cap=MAX_TOOL_TOP_ITEMS,
            name="top_groups",
        )
        include_components = self._truthy(arguments.get("include_components"), default=False)
        ordered = sorted(rows, key=lambda item: float(item.get(sort_by, 0.0)), reverse=True)
        compact_rows = []
        for row in ordered[:top_groups]:
            compact = {
                "group": row.get("group"),
                "layers": row.get("layers"),
                "occurrences": row.get("occurrences"),
                "latency_sum": row.get("latency_sum"),
                "energy": row.get("energy"),
                "dominant_dimension": row.get("dominant_dimension"),
            }
            if include_components:
                compact["timing_components"] = {
                    "calc_time": row.get("calc_time"),
                    "noc_time": row.get("noc_time"),
                    "dram_time": row.get("dram_time"),
                }
                compact["energy_components"] = {
                    "calc_energy": row.get("calc_energy"),
                    "ubuf_energy": row.get("ubuf_energy"),
                    "noc_energy": row.get("noc_energy"),
                    "dram_energy": row.get("dram_energy"),
                }
            compact_rows.append(compact)
        return {
            "operator_groups": compact_rows,
            "group_count": len(rows),
            "returned_groups": len(compact_rows),
            "sort_by": sort_by,
        }

    def _monetary_cost_payload_for_llm(self, summary: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
        top_components = self._resolve_limit(
            arguments.get("top_components"),
            default=DEFAULT_TOOL_TOP_ITEMS,
            cap=MAX_TOOL_TOP_ITEMS,
            name="top_components",
        )
        detail = summary.get("detail", {}) if isinstance(summary.get("detail"), dict) else {}
        shares = summary.get("shares", {}) if isinstance(summary.get("shares"), dict) else {}
        cost_items = [
            (key, value)
            for key, value in detail.items()
            if key.startswith("cost_") and key != "cost_overall"
        ]
        cost_items.sort(key=lambda item: float(item[1]), reverse=True)
        return {
            "total": summary.get("total"),
            "available": summary.get("available"),
            "top_components": [
                {
                    "component": key,
                    "value": value,
                    "share": shares.get(f"{key}_share"),
                }
                for key, value in cost_items[:top_components]
            ],
            "component_count": len(cost_items),
        }

    def _resolve_limit(self, value: Any, default: int, cap: int, name: str) -> int:
        limit = default if value in (None, "") else int(value)
        if limit <= 0:
            raise ValueError(f"{name} must be positive, got {limit}")
        return min(limit, cap)

    def _truthy(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    def _argument_signature(self, arguments: Dict[str, Any]) -> str:
        canonical = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:10]
        return f"args_{digest}"

    def _required_metric(self, metrics: Dict[str, float], key: str) -> float:
        if key not in metrics:
            raise KeyError(f"Evaluation metrics missing required key: {key}")
        value = float(metrics[key])
        if value <= 0.0:
            raise ValueError(f"Evaluation metric {key} must be positive, got {value}")
        return value

    def _metrics_with_objective(self, metrics: Dict[str, float]) -> Dict[str, float]:
        enriched = dict(metrics)
        enriched["objective"] = (
            self._required_metric(metrics, "latency")
            * self._required_metric(metrics, "energy")
            * self._required_metric(metrics, "mc")
        )
        return enriched

    def _read_required_detail(self, evaluation: EvaluationResult, key: str) -> Dict[str, Any]:
        path = evaluation.detail_files.get(key)
        if path is None:
            raise ValueError(f"Evaluation detail file missing required key: {key}")
        candidate = Path(path)
        if not candidate.exists():
            raise FileNotFoundError(f"Evaluation detail file not found for {key}: {candidate}")
        return read_json(candidate)

    def _layer_loads(self, evaluation: EvaluationResult) -> List[Dict[str, Any]]:
        latency_detail = self._read_required_detail(evaluation, "latency")
        energy_detail = self._read_required_detail(evaluation, "energy")
        loads = self._aggregate_layers(latency_detail, energy_detail)
        self._derive_layer_signals(loads)
        ordered = sorted(loads.values(), key=lambda item: (item.layer_id, item.layer_name))
        return [item.to_dict() for item in ordered]

    def _select_layers(
        self,
        all_loads: List[Dict[str, Any]],
        layers: Any = None,
        layer_ids: Any = None,
        layer_names: Any = None,
    ) -> List[Dict[str, Any]]:
        ids = set()
        names = set()
        if isinstance(layer_ids, list):
            ids.update(int(item) for item in layer_ids if item is not None)
        if isinstance(layer_names, list):
            names.update(str(item) for item in layer_names if item is not None)
        if isinstance(layers, list):
            for item in layers:
                if not isinstance(item, dict):
                    continue
                if item.get("layer_id") is not None:
                    ids.add(int(item["layer_id"]))
                elif item.get("layerID") is not None:
                    ids.add(int(item["layerID"]))
                if item.get("layer_name") is not None:
                    names.add(str(item["layer_name"]))
                elif item.get("layerName") is not None:
                    names.add(str(item["layerName"]))
        selected = []
        for layer in all_loads:
            layer_id = layer.get("layer_id", layer.get("layerID"))
            layer_name = layer.get("layer_name", layer.get("layerName"))
            if layer_id in ids or layer_name in names:
                selected.append(layer)
        selected.sort(key=lambda item: (int(item.get("layer_id", item.get("layerID", 0))), str(item.get("layer_name", ""))))
        return selected

    def _layer_detail_record(
        self,
        layer: Dict[str, Any],
        metrics: Dict[str, float],
        include_fields: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        objective = self._metrics_with_objective(metrics)["objective"]
        latency = max(self._required_metric(metrics, "latency"), 1.0)
        energy = max(self._required_metric(metrics, "energy"), 1.0)
        root_causes = self._root_causes_from_breakdown(layer)
        impact_types = []
        if float(layer.get("latency_sum", 0.0)) / latency >= 0.005:
            impact_types.append("latency")
        if float(layer.get("energy", 0.0)) / energy >= 0.005:
            impact_types.append("energy")
        fields = include_fields or {"basic", "shares", "placement", "timing", "energy", "breakdown", "root_cause"}
        record = self._compact_layer_record(
            layer,
            metrics=self._metrics_with_objective(metrics),
            include_fields=fields,
        )
        record["impact_types"] = impact_types or ["unknown"]
        record["root_causes"] = root_causes
        record["dominant_root_cause"] = layer.get("dominant_dimension", "unknown")
        record.setdefault("shares", {})
        record["shares"]["objective_reference"] = objective
        return record

    def _layer_table_fields(self) -> List[str]:
        return [
            "layer_id",
            "layer_name",
            "group",
            "occurrences",
            "latency_sum",
            "latency_max",
            "critical_end",
            "calc_time",
            "noc_time",
            "dram_time",
            "energy",
            "calc_energy",
            "ubuf_energy",
            "noc_energy",
            "dram_energy",
            "dominant_dimension",
            "time_breakdown",
            "energy_breakdown",
        ]

    def _build_layer_rank_views(
        self,
        all_loads: List[Dict[str, Any]],
        top_layers: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        views = {
            "latency_sum": lambda layer: float(layer.get("latency_sum", 0.0)),
            "energy": lambda layer: float(layer.get("energy", 0.0)),
            "critical_end": lambda layer: float(layer.get("critical_end", 0.0)),
            "compute": lambda layer: self._dimension_evidence_value(layer, "compute"),
            "memory": lambda layer: self._dimension_evidence_value(layer, "memory"),
            "communication": lambda layer: self._dimension_evidence_value(layer, "communication"),
            "buffer": lambda layer: self._dimension_evidence_value(layer, "buffer"),
        }
        ranked: Dict[str, List[Dict[str, Any]]] = {}
        for view_name, key_fn in views.items():
            ordered = sorted(all_loads, key=key_fn, reverse=True)
            ranked[view_name] = [
                self._rank_view_record(layer, rank_metric=view_name, rank_value=key_fn(layer))
                for layer in ordered[:top_layers]
            ]
        return ranked

    def _rank_view_record(
        self,
        layer: Dict[str, Any],
        rank_metric: str,
        rank_value: float,
    ) -> Dict[str, Any]:
        return self._compact_layer_record(
            layer,
            include_fields={"basic", "placement", "timing", "energy", "root_cause"},
            rank_metric=rank_metric,
            rank_value=rank_value,
        )

    def _search_space_position(
        self,
        hardware: Dict[str, Any],
        search_space: Dict[str, Any],
    ) -> Dict[str, Any]:
        position: Dict[str, Any] = {}
        system_positions: Dict[str, Any] = {}
        for key, candidates in all_system_param_candidates(search_space).items():
            if not candidates or key not in hardware:
                continue
            system_positions[key] = self._candidate_position(hardware[key], candidates)
        if system_positions:
            position["system_params"] = system_positions

        current_shape = hardware_shape(hardware)
        count_space = []
        for item in array_shape_candidates(search_space, hardware):
            shape = (int(item.get("chip_y")), int(item.get("chip_x")))
            count_space.append(
                {
                    "num_chiplets": item.get("num_chiplets"),
                    "derived_shape": item.get("shape"),
                    "is_current": shape == current_shape,
                }
            )
        if count_space:
            position["chiplet_count"] = {
                "current_num_chiplets": hardware.get("num_chiplets"),
                "derived_current_shape": list(current_shape) if current_shape is not None else None,
                "candidate_space": count_space,
                "derived_fields": ["chip_y", "chip_x"],
            }

        chiplets = hardware.get("chiplets", [])
        if isinstance(chiplets, list) and chiplets:
            type_values = Counter(str(chip.get("type")) for chip in chiplets if isinstance(chip, dict))
            compute_values = Counter(str(chip.get("compute_units")) for chip in chiplets if isinstance(chip, dict))
            buffer_values = Counter(str(chip.get("buffer_size")) for chip in chiplets if isinstance(chip, dict))
            position["per_chiplet_architecture"] = {
                "parameters": ["compute_units", "buffer_size", "chiplet_type"],
                "value_counts": {
                    "compute_units": dict(compute_values),
                    "buffer_size": dict(buffer_values),
                    "chiplet_type": dict(type_values),
                },
                "candidate_space": {
                    "compute_units": compute_unit_candidates(search_space),
                    "buffer_size": buffer_size_candidates(search_space),
                    "chiplet_type": chip_type_candidates(search_space),
                },
            }
        return position

    def _candidate_position(self, value: Any, candidates: List[Any]) -> Dict[str, Any]:
        if value in candidates:
            idx = candidates.index(value)
            return {
                "value": value,
                "index": idx,
                "candidate_space": candidates,
                "at_min": idx == 0,
                "at_max": idx == len(candidates) - 1,
            }
        return {"value": value, "candidate_space": candidates, "in_space": False}

    def _read_optional_json(self, path: Path | None) -> Dict[str, Any]:
        if path is None:
            return {}
        candidate = Path(path)
        if not candidate.exists():
            return {}
        return read_json(candidate)

    def _aggregate_layers(
        self,
        latency_detail: Dict[str, List[Dict[str, Any]]],
        energy_detail: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[Tuple[int, str], LayerLoad]:
        loads: Dict[Tuple[int, str], LayerLoad] = {}
        for core, entries in latency_detail.items():
            for entry in entries:
                layer_id = int(entry["layerID"])
                layer_name = str(entry.get("layerName", f"layer{layer_id}"))
                key = (layer_id, layer_name)
                load = loads.setdefault(
                    key,
                    LayerLoad(
                        layer_id=layer_id,
                        layer_name=layer_name,
                        group=layer_group(layer_name),
                        features=operator_features(layer_name),
                    ),
                )
                begin = float(entry.get("latencyBegin", 0.0))
                end = float(entry.get("latencyEnd", begin))
                duration = max(0.0, end - begin)
                load.occurrences += 1
                load.cores.append(core)
                if "batchID" in entry:
                    load.batches.append(int(entry["batchID"]))
                load.latency_sum += duration
                load.latency_max = max(load.latency_max, duration)
                load.critical_end = max(load.critical_end, end)
                load.calc_time += float(entry.get("calcTime", 0.0))
                load.noc_time += float(entry.get("nocTime", 0.0))
                load.dram_time += float(entry.get("dramTime", 0.0))

        for _core, entries in energy_detail.items():
            for entry in entries:
                layer_id = int(entry["layerID"])
                layer_name = str(entry.get("layerName", f"layer{layer_id}"))
                key = (layer_id, layer_name)
                load = loads.setdefault(
                    key,
                    LayerLoad(
                        layer_id=layer_id,
                        layer_name=layer_name,
                        group=layer_group(layer_name),
                        features=operator_features(layer_name),
                    ),
                )
                load.energy += float(entry.get("energy", 0.0))
                load.calc_energy += float(entry.get("calcEnergy", 0.0))
                load.ubuf_energy += float(entry.get("ubufEnergy", 0.0))
                load.noc_energy += float(entry.get("nocEnergy", 0.0))
                load.dram_energy += float(entry.get("dramEnergy", 0.0))
        return loads

    def _derive_layer_signals(self, loads: Dict[Tuple[int, str], LayerLoad]) -> None:
        for item in loads.values():
            time_total = max(item.calc_time + item.noc_time + item.dram_time, 1.0)
            energy_total = max(item.energy, 1.0)
            item.time_breakdown = {
                "compute": item.calc_time / time_total,
                "communication": item.noc_time / time_total,
                "memory": item.dram_time / time_total,
            }
            item.energy_breakdown = {
                "compute": item.calc_energy / energy_total,
                "buffer": item.ubuf_energy / energy_total,
                "communication": item.noc_energy / energy_total,
                "memory": item.dram_energy / energy_total,
            }
            item.dimension_scores = {
                "compute": 0.5 * item.time_breakdown["compute"] + 0.5 * item.energy_breakdown["compute"],
                "memory": 0.5 * item.time_breakdown["memory"] + 0.5 * item.energy_breakdown["memory"],
                "communication": 0.5
                * item.time_breakdown["communication"]
                + 0.5
                * item.energy_breakdown["communication"],
                "buffer": item.energy_breakdown["buffer"],
            }
            item.dominant_dimension = max(item.dimension_scores, key=item.dimension_scores.get)
            item.features["bottleneck_evidence"] = {
                "time_breakdown": item.time_breakdown,
                "energy_breakdown": item.energy_breakdown,
                "dominant_dimension": item.dominant_dimension,
            }

    def _write_statistics(
        self,
        output_dir: Path,
        timeline_rows: List[Dict[str, Any]],
        all_loads: List[Dict[str, Any]],
        candidate_layers: List[Dict[str, Any]],
        analysis_summary: Dict[str, Any],
    ) -> Dict[str, str]:
        stats_dir = output_dir / "analysis"
        stats_dir.mkdir(parents=True, exist_ok=True)

        timeline_path = stats_dir / "execution_timeline.csv"
        write_csv(
            timeline_path,
            timeline_rows,
            [
                "core",
                "batchID",
                "layerID",
                "layerName",
                "group",
                "latencyBegin",
                "latencyEnd",
                "duration",
                "calcTime",
                "nocTime",
                "dramTime",
            ],
        )
        timeline_html = self._write_timeline_html(stats_dir, timeline_rows)

        energy_path = stats_dir / "layer_energy_table.csv"
        write_csv(
            energy_path,
            all_loads,
            [
                "layer_id",
                "layer_name",
                "group",
                "occurrences",
                "latency_sum",
                "latency_max",
                "critical_end",
                "calc_time",
                "noc_time",
                "dram_time",
                "energy",
                "calc_energy",
                "ubuf_energy",
                "noc_energy",
                "dram_energy",
                "dominant_dimension",
                "time_breakdown",
                "energy_breakdown",
            ],
        )

        group_path = stats_dir / "operator_group_summary.csv"
        write_csv(
            group_path,
            analysis_summary.get("operator_groups", []),
            [
                "group",
                "layers",
                "occurrences",
                "latency_sum",
                "energy",
                "calc_time",
                "noc_time",
                "dram_time",
                "calc_energy",
                "ubuf_energy",
                "noc_energy",
                "dram_energy",
                "dominant_dimension",
            ],
        )

        bottleneck_path = stats_dir / "model_bottlenecks.json"
        write_json(bottleneck_path, {"candidate_layers": candidate_layers})
        analysis_summary_path = stats_dir / "analysis_summary.json"
        write_json(analysis_summary_path, analysis_summary)
        return {
            "timeline_csv": str(timeline_path),
            "timeline_html": str(timeline_html),
            "energy_table_csv": str(energy_path),
            "operator_group_csv": str(group_path),
            "bottleneck_json": str(bottleneck_path),
            "analysis_summary_json": str(analysis_summary_path),
        }

    def _build_timeline_rows(self, latency_detail: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        timeline_rows: List[Dict[str, Any]] = []
        for core, entries in latency_detail.items():
            for entry in entries:
                begin = float(entry.get("latencyBegin", 0.0))
                end = float(entry.get("latencyEnd", begin))
                layer_name = str(entry.get("layerName", ""))
                timeline_rows.append(
                    {
                        "core": core,
                        "batchID": entry.get("batchID", ""),
                        "layerID": entry.get("layerID", ""),
                        "layerName": layer_name,
                        "group": layer_group(layer_name),
                        "latencyBegin": begin,
                        "latencyEnd": end,
                        "duration": max(0.0, end - begin),
                        "calcTime": entry.get("calcTime", ""),
                        "nocTime": entry.get("nocTime", ""),
                        "dramTime": entry.get("dramTime", ""),
                    }
                )
        timeline_rows.sort(key=lambda row: (self._core_sort_key(row["core"]), float(row["latencyBegin"] or 0)))
        return timeline_rows

    def _write_timeline_html(self, stats_dir: Path, timeline_rows: List[Dict[str, Any]]) -> Path:
        timeline_path = stats_dir / "execution_timeline.html"
        if not timeline_rows:
            timeline_path.write_text("<!doctype html><title>Execution Timeline</title><p>No timeline rows.</p>")
            return timeline_path

        min_begin = min(float(row["latencyBegin"]) for row in timeline_rows)
        max_end = max(float(row["latencyEnd"]) for row in timeline_rows)
        span = max(max_end - min_begin, 1.0)
        cores = sorted({str(row["core"]) for row in timeline_rows}, key=self._core_sort_key)
        core_to_y = {core: index for index, core in enumerate(cores)}
        colors = {
            "attention": "#4976d0",
            "qkv_projection": "#7b5cc7",
            "output_projection": "#2f9f84",
            "ffn": "#c06a33",
            "elementwise": "#7f8c32",
            "other": "#6f7785",
        }

        bars = []
        for row in timeline_rows[:1200]:
            left = 1.0 + 98.0 * (float(row["latencyBegin"]) - min_begin) / span
            width = max(0.16, 98.0 * float(row["duration"]) / span)
            top = 34 + core_to_y[str(row["core"])] * 24
            group = str(row.get("group", "other"))
            title = html.escape(
                f"{row['core']} | layer {row['layerID']} {row['layerName']} | "
                f"{row['latencyBegin']:.4g}-{row['latencyEnd']:.4g}"
            )
            bars.append(
                "<div class=\"bar\" "
                f"title=\"{title}\" "
                f"style=\"left:{left:.4f}%;top:{top}px;width:{width:.4f}%;"
                f"background:{colors.get(group, colors['other'])};\"></div>"
            )
        labels = [
            f"<div class=\"core-label\" style=\"top:{34 + index * 24}px\">{html.escape(core)}</div>"
            for index, core in enumerate(cores)
        ]
        legend = "".join(
            f"<span><i style=\"background:{color}\"></i>{html.escape(group)}</span>"
            for group, color in colors.items()
        )
        height = 70 + len(cores) * 24
        document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Execution Timeline</title>
<style>
body {{ margin: 24px; font: 13px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #20242a; }}
.summary {{ margin-bottom: 14px; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 10px 0 18px; }}
.legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
.legend i {{ width: 12px; height: 12px; display: inline-block; border-radius: 2px; }}
.timeline {{ position: relative; min-width: 920px; height: {height}px; border: 1px solid #ccd3dd; background: linear-gradient(to right, #f7f8fb 0, #f7f8fb 1px, transparent 1px) 0 0 / 10% 100%; }}
.axis {{ position: absolute; left: 1%; right: 1%; top: 8px; height: 18px; border-bottom: 1px solid #aab3c0; color: #58616f; }}
.core-label {{ position: absolute; left: 6px; width: 68px; height: 16px; color: #58616f; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.bar {{ position: absolute; height: 16px; border-radius: 2px; opacity: 0.86; box-shadow: inset 0 0 0 1px rgba(0,0,0,.12); }}
</style>
</head>
<body>
<h1>Execution Timeline</h1>
<div class="summary">Rows shown: {min(len(timeline_rows), 1200)} / {len(timeline_rows)}. Time span: {min_begin:.4g} to {max_end:.4g}.</div>
<div class="legend">{legend}</div>
<div class="timeline">
<div class="axis">normalized execution time</div>
{''.join(labels)}
{''.join(bars)}
</div>
</body>
</html>
"""
        timeline_path.write_text(document, encoding="utf-8")
        return timeline_path

    def _summarize_timeline(self, timeline_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not timeline_rows:
            return {"rows": 0, "critical_end": 0.0, "critical_core": None, "core_busy_time": {}}
        core_busy: Dict[str, float] = defaultdict(float)
        critical_row: Dict[str, Any] = {}
        for row in timeline_rows:
            core = str(row["core"])
            core_busy[core] += float(row.get("duration", 0.0))
            if not critical_row or float(row["latencyEnd"]) > float(critical_row["latencyEnd"]):
                critical_row = row
        max_end = max(float(row["latencyEnd"]) for row in timeline_rows)
        min_begin = min(float(row["latencyBegin"]) for row in timeline_rows)
        span = max(max_end - min_begin, 1.0)
        return {
            "rows": len(timeline_rows),
            "time_span": span,
            "critical_end": max_end,
            "critical_core": critical_row.get("core"),
            "critical_layer": {
                "layerID": critical_row.get("layerID"),
                "layerName": critical_row.get("layerName"),
                "group": critical_row.get("group"),
            },
            "core_busy_time": {
                core: round(value, 6)
                for core, value in sorted(core_busy.items(), key=lambda item: self._core_sort_key(item[0]))
            },
            "avg_core_utilization": round(sum(core_busy.values()) / (len(core_busy) * span), 6)
            if core_busy
            else 0.0,
        }

    def _summarize_operator_groups(self, all_loads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: Dict[str, Dict[str, Any]] = {}
        dimension_votes: Dict[str, Counter[str]] = defaultdict(Counter)
        for layer in all_loads:
            group = str(layer.get("group", "other"))
            summary = groups.setdefault(
                group,
                {
                    "group": group,
                    "layers": 0,
                    "occurrences": 0,
                    "latency_sum": 0.0,
                    "energy": 0.0,
                    "calc_time": 0.0,
                    "noc_time": 0.0,
                    "dram_time": 0.0,
                    "calc_energy": 0.0,
                    "ubuf_energy": 0.0,
                    "noc_energy": 0.0,
                    "dram_energy": 0.0,
                },
            )
            summary["layers"] += 1
            summary["occurrences"] += int(layer.get("occurrences", 0))
            for key in [
                "latency_sum",
                "energy",
                "calc_time",
                "noc_time",
                "dram_time",
                "calc_energy",
                "ubuf_energy",
                "noc_energy",
                "dram_energy",
            ]:
                summary[key] += float(layer.get(key, 0.0))
            dimension_votes[group][str(layer.get("dominant_dimension", "unknown"))] += 1

        rows = []
        for group, summary in groups.items():
            votes = dimension_votes[group]
            summary["dominant_dimension"] = votes.most_common(1)[0][0] if votes else "unknown"
            rows.append(summary)
        rows.sort(key=lambda item: item["latency_sum"], reverse=True)
        return rows

    def _summarize_breakdowns(self, all_loads: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        time_totals = {"compute": 0.0, "memory": 0.0, "communication": 0.0}
        energy_totals = {"compute": 0.0, "memory": 0.0, "communication": 0.0, "buffer": 0.0}
        count = 0
        for layer in all_loads:
            time_breakdown = layer.get("time_breakdown", {})
            energy_breakdown = layer.get("energy_breakdown", {})
            if not isinstance(time_breakdown, dict) and not isinstance(energy_breakdown, dict):
                continue
            count += 1
            if isinstance(time_breakdown, dict):
                for key in time_totals:
                    time_totals[key] += float(time_breakdown.get(key, 0.0) or 0.0)
            if isinstance(energy_breakdown, dict):
                for key in energy_totals:
                    energy_totals[key] += float(energy_breakdown.get(key, 0.0) or 0.0)
        if count == 0:
            return {"time": time_totals, "energy": energy_totals}
        return {
            "time": {key: round(value / count, 6) for key, value in time_totals.items()},
            "energy": {key: round(value / count, 6) for key, value in energy_totals.items()},
        }

    def _summarize_monetary_cost(
        self,
        monetary_cost_detail: Dict[str, Any],
        metrics: Dict[str, float],
    ) -> Dict[str, Any]:
        numeric = {
            key: float(value)
            for key, value in monetary_cost_detail.items()
            if isinstance(value, (int, float))
        }
        total = float(metrics.get("mc", 0.0) or numeric.get("cost_overall", 0.0) or 0.0)
        shares = {}
        if total > 0.0:
            for key, value in numeric.items():
                if key.startswith("cost_"):
                    shares[f"{key}_share"] = value / total
        return {
            "total": total,
            "detail": numeric,
            "shares": shares,
            "available": bool(numeric),
        }

    def _summarize_hardware(self, hardware: Dict[str, Any], search_space: Dict[str, Any]) -> Dict[str, Any]:
        chiplets = hardware.get("chiplets", [])
        type_counts = Counter(str(chip.get("type", "unknown")) for chip in chiplets if isinstance(chip, dict))
        compute_counts = Counter(str(chip.get("compute_units")) for chip in chiplets if isinstance(chip, dict))
        buffer_counts = Counter(str(chip.get("buffer_size")) for chip in chiplets if isinstance(chip, dict))
        macs_counts = Counter(str(chip.get("macs")) for chip in chiplets if isinstance(chip, dict) and "macs" in chip)
        total_compute = sum(float(chip.get("compute_units", 0.0)) for chip in chiplets if isinstance(chip, dict))
        total_buffer = sum(float(chip.get("buffer_size", 0.0)) for chip in chiplets if isinstance(chip, dict))
        return {
            "num_chiplets": hardware.get("num_chiplets", len(chiplets)),
            "derived_array_shape": [hardware.get("chip_y"), hardware.get("chip_x")],
            "system_params": {
                "dram_bw": hardware.get("dram_bw"),
                "nop_bw": hardware.get("nop_bw"),
                "micro_batch": hardware.get("micro_batch"),
                "tensor_parall": hardware.get("tensor_parall"),
            },
            "per_chiplet_architecture": {
                "compute_units": dict(compute_counts),
                "buffer_size": dict(buffer_counts),
                "chiplet_type": dict(type_counts),
                "macs": dict(macs_counts),
            },
            "total_compute_units": total_compute,
            "total_buffer_size": total_buffer,
            "chiplet_layout": self._chiplet_layout_summary(hardware),
            "full_hardware_request": (
                "This is a compact hardware view. Call summarize_hardware_config with include_full_hardware=true "
                "only when exact raw chiplet fields or simulator-order hardware JSON are needed."
            ),
        }

    def _chiplet_layout_summary(self, hardware: Dict[str, Any]) -> Dict[str, Any]:
        chiplets = hardware.get("chiplets", [])
        if not isinstance(chiplets, list):
            chiplets = []
        type_sequence = [
            str(chip.get("type", "unknown")) if isinstance(chip, dict) else "unknown"
            for chip in chiplets
        ]
        spec_sequence = [
            {
                "index": idx,
                "type": str(chip.get("type", "unknown")),
                "compute_units": chip.get("compute_units"),
                "buffer_size": chip.get("buffer_size"),
                "macs": chip.get("macs"),
            }
            for idx, chip in enumerate(chiplets)
            if isinstance(chip, dict)
        ]
        chip_x = self._optional_positive_int(hardware.get("chip_x"))
        chip_y = self._optional_positive_int(hardware.get("chip_y"))
        grid: List[List[Optional[str]]] = []
        if chip_x and chip_y:
            for y in range(chip_y):
                row: List[Optional[str]] = []
                for x in range(chip_x):
                    idx = y * chip_x + x
                    row.append(type_sequence[idx] if idx < len(type_sequence) else None)
                grid.append(row)
        return {
            "layout_order_assumption": "row_major_y_then_x",
            "layout_complete": bool(chip_x and chip_y and len(type_sequence) == chip_x * chip_y),
            "type_sequence": type_sequence,
            "type_grid": grid,
            "spec_sequence": spec_sequence,
        }

    def _optional_positive_int(self, value: Any) -> Optional[int]:
        try:
            integer = int(value)
        except (TypeError, ValueError):
            return None
        return integer if integer > 0 else None

    def _core_sort_key(self, core: Any) -> Any:
        core = str(core)
        if core.startswith("core"):
            try:
                return (0, int(core.replace("core", "")))
            except ValueError:
                return (1, core)
        return (1, core)
