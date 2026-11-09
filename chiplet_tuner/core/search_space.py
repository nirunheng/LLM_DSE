from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


# 原Compass仿真器搜索候选
COMPUTE_UNIT_CANDIDATES = [1024, 4096, 16384]
BUFFER_SIZE_CANDIDATES = [2048, 8192, 32768]
CHIPLET_TYPE_CANDIDATES = ["ws", "os"]

DEFAULT_ARRAY_SHAPES: List[Tuple[int, int]] = [
    (1, 1),
    (2, 1),
    (2, 2),
    (4, 2),
    (4, 4),
    (8, 4),
    (8, 8),
    (16, 8),
    (16, 16),
]

MACS_BY_COMPUTE_UNITS: Dict[int, Dict[str, str]] = {
    1024: {"ws": "[4,4,8,8]", "os": "[4,4,8,8]"},
    4096: {"ws": "[8,8,8,8]", "os": "[8,8,8,8]"},
    16384: {"ws": "[8,8,16,16]", "os": "[8,8,16,16]"},
}

TASK_MICRO_BATCH_OPTIONS = {
    "prefill": [1, 2, 4],
    "mixed": [1, 2, 3, 6, 11, 22, 33, 66],
    "decode": [1, 2, 4, 8, 16, 32, 64, 128],
    "serving_prefill": [1],
    "serving": [1, 2, 4, 8, 16, 32, 64, 128],
}

SYSTEM_PARAM_SEARCH_SPACE = {
    "dram_bw": [16, 32, 64, 128, 256],
    "nop_bw": [32, 64, 128, 256, 512],
    "micro_batch": TASK_MICRO_BATCH_OPTIONS["decode"],
    "tensor_parall": [4, 8, 16, 32, 64],
}

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
            "description": (
                "Choose a legal total chiplet count. The hardware tools derive "
                "chip_y and chip_x from the selected count."
            ),
        },
        "per_chiplet_architecture": {
            "parameters": ["compute_units", "buffer_size", "chiplet_type"],
            "description": (
                "Each chiplet independently chooses compute capacity, storage capacity, "
                "and dataflow type from the legal candidate sets."
            ),
        },
        "system_params": {
            "parameters": ["dram_bw", "nop_bw", "micro_batch", "tensor_parall"],
        },
    },
    # Backward-compatible aliases for callers that only need candidate lists.
    "dram_bw": SYSTEM_PARAM_SEARCH_SPACE["dram_bw"],
    "nop_bw": SYSTEM_PARAM_SEARCH_SPACE["nop_bw"],
    "micro_batch": SYSTEM_PARAM_SEARCH_SPACE["micro_batch"],
    "tensor_parall": SYSTEM_PARAM_SEARCH_SPACE["tensor_parall"],
    "compute_units": COMPUTE_UNIT_CANDIDATES,
    "buffer_size": BUFFER_SIZE_CANDIDATES,
    "type": CHIPLET_TYPE_CANDIDATES,
}

#接入ATLAS以后的搜索空间更新
ATLAS_MAC_NUM_CANDIDATES = [2048, 4096, 8192, 16384]
ATLAS_VEC_NUM_CANDIDATES = [128, 256, 512, 1024]
ATLAS_BUFFER_SIZE_CANDIDATES = [1024, 2048, 4096, 8192] #单位kb
ATLAS_BUFFER_BW_CANDIDATES = [4, 8, 16, 32]
ATLAS_FREQUENCY_CANDIDATEAS = [500, 1000, 1500] #单位MHz
ATLAS_CORE_NUM_CANDIDATES = [1, 2, 4, 8]

ATLAS_SYSTEM_PARAM_SEARCH_SPACE = {
    "dram_config_path":[
        "configs/architecture/dram/cloud/cloud_0.25TBps.yaml",
        "configs/architecture/dram/cloud/cloud_0.5TBps.yaml",
        "configs/architecture/dram/cloud/cloud_1TBps.yaml",
        "configs/architecture/dram/cloud/cloud_2TBps.yaml",
        "configs/architecture/dram/cloud/cloud_4TBps.yaml",
    ],
    "power":[],
    "area":[],
}

ATLAS_DEFAULT_HARDWARE_SEARCH_SPACE : Dict[str, Any] = {
    "design_space_kind": "atlas_chip_yaml",
    "compute_scale": None,
    "array_shapes":[],
    "num_chiplet_candidates": [],
    "num_mac_candidates": ATLAS_MAC_NUM_CANDIDATES,
    "num_vector_candidates": ATLAS_VEC_NUM_CANDIDATES,
    "buffer_size_candidates": ATLAS_BUFFER_SIZE_CANDIDATES,
    "buffer_bw_candidates": ATLAS_BUFFER_BW_CANDIDATES,
    "core_num_candidates" : ATLAS_CORE_NUM_CANDIDATES,
    "frequency_candidates" : ATLAS_FREQUENCY_CANDIDATEAS,
    "system_params" : ATLAS_SYSTEM_PARAM_SEARCH_SPACE,
    "tunable_categories" : {
        "compute" : {
            "parameters" : ["mac_num", "vec_num", "frequency"],
            "description" : "Core compute resourcces, including MAC/VEC/FREQUENCY",
        },
        "memory" : {
            "parameters" : ["buffer_size", "buffer_read_bw", "buffer_write_bw"],
            "description" : "Per-core SRAM: capacity(KB), read/write bandwidth(Byte/cycle)",
        },
        "core_count" : {
            "parameters" : ["core_num"],
            "description" : "Number of cores per chip",
        },
        "dram" : {
            "parameters" : ["dram_config_path"],
            "description" : "only focus on config path",
        }
    },
    # 向后兼容别名（供工具函数使用）
    "mac_num": ATLAS_MAC_NUM_CANDIDATES,
    "vec_num": ATLAS_VEC_NUM_CANDIDATES,
    "buffer_size": ATLAS_BUFFER_SIZE_CANDIDATES,
    "buffer_read_bw": ATLAS_BUFFER_BW_CANDIDATES,
    "buffer_write_bw": ATLAS_BUFFER_BW_CANDIDATES,
    "core_num": ATLAS_CORE_NUM_CANDIDATES,
    "frequency": ATLAS_FREQUENCY_CANDIDATEAS,
}


def make_hardware_search_space(
    task_type: str = "decode",
    compute_scale: Optional[int | str] = None,
) -> Dict[str, Any]:
    search_space = copy.deepcopy(DEFAULT_HARDWARE_SEARCH_SPACE)
    micro_batch = micro_batch_options_for_task(task_type)
    search_space["system_params"]["micro_batch"] = micro_batch
    search_space["micro_batch"] = micro_batch
    search_space["task_type"] = task_type
    if compute_scale is not None:
        search_space["compute_scale"] = str(compute_scale)
    return search_space


def micro_batch_options_for_task(task_type: str) -> List[int]:
    if task_type in TASK_MICRO_BATCH_OPTIONS:
        return list(TASK_MICRO_BATCH_OPTIONS[task_type])
    if str(task_type).startswith("serving"):
        return list(TASK_MICRO_BATCH_OPTIONS["serving"])
    raise ValueError(
        f"Unsupported task_type={task_type!r}; "
        f"legal values are {sorted(TASK_MICRO_BATCH_OPTIONS)} or serving*"
    )


def system_param_candidates(search_space: Mapping[str, Any], key: str) -> List[Any]:
    system_params = search_space.get("system_params", {})
    if isinstance(system_params, Mapping) and isinstance(system_params.get(key), Sequence):
        return list(system_params[key])
    candidates = search_space.get(key)
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        return list(candidates)
    return []


def all_system_param_candidates(search_space: Mapping[str, Any]) -> Dict[str, List[Any]]:
    return {
        key: system_param_candidates(search_space, key)
        for key in ["dram_bw", "nop_bw", "micro_batch", "tensor_parall"]
    }


def compute_unit_candidates(search_space: Mapping[str, Any]) -> List[int]:
    return _int_candidates(search_space.get("compute_unit_candidates", search_space.get("compute_units")), COMPUTE_UNIT_CANDIDATES)


def buffer_size_candidates(search_space: Mapping[str, Any]) -> List[int]:
    return _int_candidates(search_space.get("buffer_size_candidates", search_space.get("buffer_size")), BUFFER_SIZE_CANDIDATES)


def chip_type_candidates(search_space: Mapping[str, Any]) -> List[str]:
    candidates = search_space.get("chiplet_type_candidates", search_space.get("type", CHIPLET_TYPE_CANDIDATES))
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return list(CHIPLET_TYPE_CANDIDATES)
    values = [str(item) for item in candidates if str(item)]
    return values or list(CHIPLET_TYPE_CANDIDATES)


def array_shape_candidates(
    search_space: Mapping[str, Any],
    hardware: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    raw_shapes = search_space.get("array_shapes", search_space.get("shape_candidates", DEFAULT_ARRAY_SHAPES))
    shapes: List[Tuple[int, int]] = []
    if isinstance(raw_shapes, Sequence) and not isinstance(raw_shapes, (str, bytes)):
        shapes = [_parse_shape_item(item) for item in raw_shapes]
    if not shapes and hardware is not None:
        current = hardware_shape(hardware)
        if current is not None:
            shapes = [current]
    candidates: List[Dict[str, Any]] = []
    for h, w in shapes:
        candidates.append(
            {
                "shape": [h, w],
                "chip_y": h,
                "chip_x": w,
                "num_chiplets": h * w,
            }
        )
    return candidates


def shape_candidates(
    search_space: Mapping[str, Any],
    hardware: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Backward-compatible alias for the explicit array-shape candidates."""

    return array_shape_candidates(search_space, hardware)


def hardware_shape(hardware: Mapping[str, Any]) -> Optional[Tuple[int, int]]:
    try:
        h = int(hardware.get("chip_y"))
        w = int(hardware.get("chip_x"))
    except (TypeError, ValueError):
        return None
    if h <= 0 or w <= 0:
        return None
    return h, w


def num_chiplet_candidates(search_space: Mapping[str, Any]) -> List[int]:
    return [int(item["num_chiplets"]) for item in array_shape_candidates(search_space, None)]


def shape_candidate_for_request(
    search_space: Mapping[str, Any],
    hardware: Optional[Mapping[str, Any]],
    shape: Any = None,
    chip_y: Any = None,
    chip_x: Any = None,
    num_chiplets: Any = None,
) -> Dict[str, Any]:
    candidates = array_shape_candidates(search_space, hardware)
    if not candidates:
        raise ValueError("No legal array_shape candidates can be derived from the design space.")

    requested_shape = _shape_tuple_from_values(shape=shape, chip_y=chip_y, chip_x=chip_x)
    if requested_shape is not None:
        for candidate in candidates:
            if (int(candidate["chip_y"]), int(candidate["chip_x"])) == requested_shape:
                return copy.deepcopy(candidate)
        nearest = min(candidates, key=lambda item: _shape_distance(requested_shape, (int(item["chip_y"]), int(item["chip_x"]))))
        return copy.deepcopy(nearest)

    if num_chiplets not in (None, ""):
        requested_num = int(num_chiplets)
        matching = [item for item in candidates if int(item["num_chiplets"]) == requested_num]
        if matching:
            current = hardware_shape(hardware or {})
            if current is not None:
                return copy.deepcopy(min(matching, key=lambda item: _shape_distance(current, (int(item["chip_y"]), int(item["chip_x"])))))
            return copy.deepcopy(matching[0])
        return copy.deepcopy(min(candidates, key=lambda item: abs(int(item["num_chiplets"]) - requested_num)))

    current_shape = hardware_shape(hardware or {})
    if current_shape is not None:
        for candidate in candidates:
            if (int(candidate["chip_y"]), int(candidate["chip_x"])) == current_shape:
                return copy.deepcopy(candidate)
    return copy.deepcopy(candidates[0])


def step_array_shape(
    hardware: Mapping[str, Any],
    search_space: Mapping[str, Any],
    direction: int,
) -> Dict[str, Any]:
    candidates = array_shape_candidates(search_space, hardware)
    if not candidates:
        raise ValueError("No legal array_shape candidates can be derived from the design space.")
    ordered = sorted(candidates, key=lambda item: (int(item["num_chiplets"]), int(item["chip_y"]), int(item["chip_x"])))
    current = hardware_shape(hardware)
    current_idx = 0
    if current is not None:
        for idx, item in enumerate(ordered):
            if (int(item["chip_y"]), int(item["chip_x"])) == current:
                current_idx = idx
                break
        else:
            current_idx = min(
                range(len(ordered)),
                key=lambda idx: _shape_distance(current, (int(ordered[idx]["chip_y"]), int(ordered[idx]["chip_x"]))),
            )
    next_idx = max(0, min(len(ordered) - 1, current_idx + (1 if direction > 0 else -1)))
    return copy.deepcopy(ordered[next_idx])


def materialize_hardware(
    template: Mapping[str, Any],
    chip_size: Optional[int] = None,
    chiplet_types: Optional[Sequence[Any]] = None,
    system_params: Optional[Mapping[str, Any]] = None,
    search_space: Optional[Mapping[str, Any]] = None,
    chiplet_type_strategy: str = "preserve_prefix",
    chiplet_type_fill: Optional[Any] = None,
    shape: Any = None,
    chip_y: Any = None,
    chip_x: Any = None,
    num_chiplets: Any = None,
    compute_units: Any = None,
    buffer_size: Any = None,
    per_chiplet_specs: Optional[Sequence[Mapping[str, Any]]] = None,
    chiplet_spec_strategy: str = "preserve_prefix",
    compute_unit_fill: Optional[Any] = None,
    buffer_size_fill: Optional[Any] = None,
) -> Dict[str, Any]:
    search_space = search_space or DEFAULT_HARDWARE_SEARCH_SPACE
    if chip_size is not None:
        legacy_compute, legacy_buffer = _legacy_chip_size_to_resources(chip_size, search_space)
        compute_units = legacy_compute if compute_units is None else compute_units
        buffer_size = legacy_buffer if buffer_size is None else buffer_size

    shape_candidate = shape_candidate_for_request(
        search_space=search_space,
        hardware=template,
        shape=shape,
        chip_y=chip_y,
        chip_x=chip_x,
        num_chiplets=num_chiplets,
    )
    count = int(shape_candidate["num_chiplets"])
    hardware = copy.deepcopy(dict(template))
    hardware["num_chiplets"] = count
    hardware["chip_y"] = int(shape_candidate["chip_y"])
    hardware["chip_x"] = int(shape_candidate["chip_x"])

    for key, candidates in all_system_param_candidates(search_space).items():
        source_value = (system_params or {}).get(key, hardware.get(key))
        if candidates:
            hardware[key] = coerce_to_candidates(source_value, hardware.get(key), candidates)
        elif source_value is not None:
            hardware[key] = source_value

    requested_compute = _requested_field_values(
        scalar_or_list=compute_units,
        per_chiplet_specs=per_chiplet_specs,
        field="compute_units",
    )
    requested_buffer = _requested_field_values(
        scalar_or_list=buffer_size,
        per_chiplet_specs=per_chiplet_specs,
        field="buffer_size",
    )
    requested_types = _requested_chiplet_types_from_inputs(chiplet_types, per_chiplet_specs)

    compute_values = _normalized_chiplet_field_values(
        template=template,
        requested_values=requested_compute,
        field="compute_units",
        count=count,
        candidates=compute_unit_candidates(search_space),
        strategy=chiplet_spec_strategy,
        fill_value=compute_unit_fill,
    )
    buffer_values = _normalized_chiplet_field_values(
        template=template,
        requested_values=requested_buffer,
        field="buffer_size",
        count=count,
        candidates=buffer_size_candidates(search_space),
        strategy=chiplet_spec_strategy,
        fill_value=buffer_size_fill,
    )
    type_values = _normalized_chiplet_types(
        template=template,
        chiplet_types=requested_types,
        count=count,
        legal_types=chip_type_candidates(search_space),
        strategy=chiplet_type_strategy,
        fill_type=chiplet_type_fill,
    )
    hardware["chiplets"] = [
        get_chiplet_spec(
            chip_type=type_values[idx],
            compute_units=compute_values[idx],
            buffer_size=buffer_values[idx],
            search_space=search_space,
        )
        for idx in range(count)
    ]
    return hardware


def normalize_hardware_to_design_space(
    proposed: Mapping[str, Any],
    current: Mapping[str, Any],
    search_space: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    search_space = search_space or DEFAULT_HARDWARE_SEARCH_SPACE
    notes: List[str] = []
    if not isinstance(proposed, Mapping):
        return copy.deepcopy(dict(current)), ["proposal is not a hardware object; kept current hardware"]

    shape_request = _requested_shape(proposed)
    shape_candidate = shape_candidate_for_request(
        search_space=search_space,
        hardware=current,
        shape=shape_request.get("shape"),
        chip_y=shape_request.get("chip_y"),
        chip_x=shape_request.get("chip_x"),
        num_chiplets=shape_request.get("num_chiplets"),
    )
    _add_shape_notes(current, shape_candidate, notes)

    system_params: Dict[str, Any] = {}
    for key, candidates in all_system_param_candidates(search_space).items():
        if key in proposed:
            system_params[key] = coerce_to_candidates(proposed[key], current.get(key), candidates, key=key, notes=notes)
        elif key in current:
            system_params[key] = coerce_to_candidates(current[key], current.get(key), candidates, key=key, notes=notes)

    legacy_chip_size = _requested_legacy_chip_size(proposed, notes)
    compute_units = proposed.get("compute_units", proposed.get("chiplet_compute_units"))
    buffer_size = proposed.get("buffer_size", proposed.get("chiplet_buffer_size"))
    if legacy_chip_size is not None:
        legacy_compute, legacy_buffer = _legacy_chip_size_to_resources(legacy_chip_size, search_space)
        compute_units = legacy_compute if compute_units is None else compute_units
        buffer_size = legacy_buffer if buffer_size is None else buffer_size
        notes.append("interpreted legacy chip_size as uniform compute_units and buffer_size")

    per_chiplet_specs = _requested_per_chiplet_specs(proposed)
    chiplet_types = _requested_chiplet_types(proposed)
    chiplet_type_strategy = _requested_chiplet_type_strategy(proposed)
    chiplet_type_fill = _requested_chiplet_type_fill(proposed)
    chiplet_spec_strategy = _requested_chiplet_spec_strategy(proposed)

    updated = materialize_hardware(
        template=current,
        shape=shape_candidate["shape"],
        system_params=system_params,
        search_space=search_space,
        chiplet_types=chiplet_types,
        chiplet_type_strategy=chiplet_type_strategy,
        chiplet_type_fill=chiplet_type_fill,
        compute_units=compute_units,
        buffer_size=buffer_size,
        per_chiplet_specs=per_chiplet_specs,
        chiplet_spec_strategy=chiplet_spec_strategy,
        compute_unit_fill=proposed.get("compute_unit_fill", proposed.get("uniform_compute_units")),
        buffer_size_fill=proposed.get("buffer_size_fill", proposed.get("uniform_buffer_size")),
    )
    _add_resource_notes(current, updated, notes)
    return updated, notes


def get_chiplet_spec(
    chip_type: Any,
    compute_units: Any,
    buffer_size: Any,
    search_space: Mapping[str, Any],
) -> Dict[str, Any]:
    legal_types = chip_type_candidates(search_space)
    chip_type_str = str(chip_type)
    if chip_type_str not in legal_types:
        chip_type_str = legal_types[0]
    compute = int(coerce_to_candidates(compute_units, None, compute_unit_candidates(search_space)))
    buffer = int(coerce_to_candidates(buffer_size, None, buffer_size_candidates(search_space)))
    macs = macs_for_compute_units(compute, chip_type_str, search_space)
    result = {
        "type": chip_type_str,
        "buffer_size": buffer,
        "compute_units": compute,
    }
    if macs is not None:
        result["macs"] = macs
    return result


def macs_for_compute_units(compute_units: int, chip_type: str, search_space: Mapping[str, Any]) -> Optional[Any]:
    raw = search_space.get("macs_by_compute_units", MACS_BY_COMPUTE_UNITS)
    lookup: Any = None
    if isinstance(raw, Mapping):
        lookup = raw.get(str(compute_units), raw.get(int(compute_units)))
    if isinstance(lookup, Mapping):
        return lookup.get(str(chip_type), lookup.get("default"))
    if lookup is not None:
        return lookup
    return MACS_BY_COMPUTE_UNITS.get(int(compute_units), {}).get(str(chip_type))


def coerce_to_candidates(
    value: Any,
    current_value: Any,
    candidates: Sequence[Any],
    key: str = "",
    notes: Optional[List[str]] = None,
) -> Any:
    if not candidates:
        return value
    if value in candidates:
        return value
    numeric = _numeric_candidates(candidates)
    if numeric:
        try:
            source = float(value)
            coerced = min(numeric, key=lambda item: abs(item - source))
            result: Any = int(coerced) if float(coerced).is_integer() else coerced
            if notes is not None:
                notes.append(f"clamped {key or 'value'}={value} to nearest legal value {result}")
            return result
        except (TypeError, ValueError):
            pass
    if current_value in candidates:
        if notes is not None:
            notes.append(f"kept current {key or 'value'} because proposed value {value} is invalid")
        return current_value
    if notes is not None:
        notes.append(f"replaced invalid {key or 'value'}={value} with first legal value {candidates[0]}")
    return copy.deepcopy(candidates[0])


def step_chiplet_resource(
    hardware: Dict[str, Any],
    search_space: Mapping[str, Any],
    field: str,
    direction: int,
    scope: str = "first",
) -> Tuple[Dict[str, Any], List[str]]:
    if field not in {"compute_units", "buffer_size"}:
        raise ValueError(f"Unsupported chiplet resource field: {field}")
    candidates = compute_unit_candidates(search_space) if field == "compute_units" else buffer_size_candidates(search_space)
    chiplets = hardware.get("chiplets", [])
    if not isinstance(chiplets, list) or not chiplets:
        raise ValueError("Current hardware does not contain chiplet information.")
    updated = copy.deepcopy(hardware)
    indices = range(len(chiplets)) if scope == "all" else range(1)
    actions: List[str] = []
    for idx in indices:
        chip = updated["chiplets"][idx]
        if not isinstance(chip, dict):
            continue
        old = int(chip.get(field, candidates[0]))
        new = _step_value(old, candidates, direction)
        if new == old:
            continue
        chip[field] = new
        if field == "compute_units":
            chip["macs"] = macs_for_compute_units(new, str(chip.get("type", "ws")), search_space)
        actions.append(f"chiplets[{idx}].{field}: {old}->{new}")
        if scope != "all":
            break
    return updated, actions


def summarize_chiplet_resources(hardware: Mapping[str, Any]) -> Dict[str, Any]:
    chiplets = hardware.get("chiplets", [])
    compute_counts: Counter[str] = Counter()
    buffer_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    if isinstance(chiplets, Sequence) and not isinstance(chiplets, (str, bytes)):
        for chip in chiplets:
            if not isinstance(chip, Mapping):
                continue
            compute_counts[str(chip.get("compute_units"))] += 1
            buffer_counts[str(chip.get("buffer_size"))] += 1
            type_counts[str(chip.get("type"))] += 1
    return {
        "compute_units": dict(compute_counts),
        "buffer_sizes": dict(buffer_counts),
        "chiplet_types": dict(type_counts),
    }


# Legacy helpers retained so older traces/configs can still be summarized.
def chip_specs(search_space: Mapping[str, Any]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    idx = 0
    for compute in compute_unit_candidates(search_space):
        for buffer in buffer_size_candidates(search_space):
            specs.append(
                {
                    "chip_size": idx,
                    "name": f"compute{compute}_buffer{buffer}",
                    "compute_units": compute,
                    "buffer_size": buffer,
                    "macs_by_type": {
                        chip_type: macs_for_compute_units(compute, chip_type, search_space)
                        for chip_type in chip_type_candidates(search_space)
                    },
                }
            )
            idx += 1
    return specs


def chip_spec_by_size(search_space: Mapping[str, Any], chip_size: int) -> Dict[str, Any]:
    specs = chip_specs(search_space)
    idx = int(chip_size)
    if idx < 0 or idx >= len(specs):
        raise ValueError(f"Unknown legacy chip_size {chip_size}; legal legacy indices are 0..{len(specs) - 1}")
    return specs[idx]


def chip_size_candidates(
    search_space: Mapping[str, Any],
    hardware: Optional[Mapping[str, Any]],
) -> List[int]:
    return list(range(len(chip_specs(search_space))))


def infer_chip_size(hardware: Mapping[str, Any], search_space: Mapping[str, Any]) -> Optional[int]:
    chiplets = hardware.get("chiplets", [])
    if not isinstance(chiplets, Sequence) or isinstance(chiplets, (str, bytes)) or not chiplets:
        return None
    compute = _most_common_int([chip.get("compute_units") for chip in chiplets if isinstance(chip, Mapping)])
    buffer = _most_common_int([chip.get("buffer_size") for chip in chiplets if isinstance(chip, Mapping)])
    if compute is None or buffer is None:
        return None
    for spec in chip_specs(search_space):
        if int(spec["compute_units"]) == compute and int(spec["buffer_size"]) == buffer:
            return int(spec["chip_size"])
    return None


def step_chip_size(
    hardware: Mapping[str, Any],
    search_space: Mapping[str, Any],
    direction: int,
) -> int:
    current = infer_chip_size(hardware, search_space)
    candidates = chip_size_candidates(search_space, hardware)
    if not candidates:
        raise ValueError("No legacy chip_size candidates can be derived from the design space.")
    if current not in candidates:
        current = candidates[0]
    idx = max(0, min(len(candidates) - 1, candidates.index(current) + (1 if direction > 0 else -1)))
    return candidates[idx]


def _int_candidates(raw: Any, fallback: Sequence[int]) -> List[int]:
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        values = [int(item) for item in raw]
        if values:
            return values
    return list(fallback)


def _numeric_candidates(candidates: Sequence[Any]) -> List[float]:
    numeric: List[float] = []
    for item in candidates:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return []
        numeric.append(float(item))
    return numeric


def _parse_shape_item(item: Any) -> Tuple[int, int]:
    if isinstance(item, Mapping):
        if "chip_y" in item and "chip_x" in item:
            return int(item["chip_y"]), int(item["chip_x"])
        if "H" in item and "W" in item:
            return int(item["H"]), int(item["W"])
    if isinstance(item, str) and "x" in item.lower():
        left, right = item.lower().split("x", 1)
        return int(left), int(right)
    if isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) >= 2:
        return int(item[0]), int(item[1])
    raise ValueError(f"Invalid array shape item: {item!r}")


def _shape_tuple_from_values(shape: Any = None, chip_y: Any = None, chip_x: Any = None) -> Optional[Tuple[int, int]]:
    if shape not in (None, ""):
        return _parse_shape_item(shape)
    if chip_y not in (None, "") and chip_x not in (None, ""):
        return int(chip_y), int(chip_x)
    return None


def _shape_distance(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    return abs(a[0] * a[1] - b[0] * b[1]) * 1000 + abs(a[0] - b[0]) + abs(a[1] - b[1])


def _requested_shape(proposed: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key in ["shape", "array_shape", "chip_shape"]:
        if key in proposed:
            result["shape"] = proposed[key]
            return result
    for key in ["chip_y", "chip_x", "num_chiplets"]:
        if key in proposed:
            result[key] = proposed[key]
    return result


def _requested_legacy_chip_size(proposed: Mapping[str, Any], notes: List[str]) -> Optional[int]:
    for key in ["chip_size", "chip_spec", "compute_spec"]:
        if key in proposed:
            value = proposed[key]
            if isinstance(value, Mapping) and "chip_size" in value:
                return int(value["chip_size"])
            try:
                return int(value)
            except (TypeError, ValueError):
                notes.append(f"ignored unknown legacy chip_size value {value!r}")
    return None


def _legacy_chip_size_to_resources(chip_size: int, search_space: Mapping[str, Any]) -> Tuple[int, int]:
    compute = compute_unit_candidates(search_space)
    buffer = buffer_size_candidates(search_space)
    idx = max(0, min(len(compute) - 1, int(chip_size)))
    bidx = max(0, min(len(buffer) - 1, int(chip_size)))
    return int(compute[idx]), int(buffer[bidx])


def _requested_per_chiplet_specs(proposed: Mapping[str, Any]) -> Optional[List[Mapping[str, Any]]]:
    for key in ["per_chiplet_specs", "chiplet_specs", "chiplets"]:
        value = proposed.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return [item for item in value if isinstance(item, Mapping)]
    return None


def _requested_field_values(
    scalar_or_list: Any,
    per_chiplet_specs: Optional[Sequence[Mapping[str, Any]]],
    field: str,
) -> Optional[List[Any]]:
    if isinstance(scalar_or_list, Sequence) and not isinstance(scalar_or_list, (str, bytes)):
        return list(scalar_or_list)
    if scalar_or_list not in (None, ""):
        return [scalar_or_list]
    if per_chiplet_specs:
        values = [spec.get(field) for spec in per_chiplet_specs if spec.get(field) is not None]
        return values or None
    return None


def _requested_chiplet_types(proposed: Mapping[str, Any]) -> Optional[List[Any]]:
    raw_types = proposed.get("chiplet_types", proposed.get("chiplet_type"))
    if isinstance(raw_types, str):
        return [raw_types]
    if isinstance(raw_types, Sequence) and not isinstance(raw_types, (str, bytes)):
        return list(raw_types)
    chiplets = proposed.get("chiplets")
    if isinstance(chiplets, Sequence) and not isinstance(chiplets, (str, bytes)):
        types = [chip.get("type") for chip in chiplets if isinstance(chip, Mapping) and chip.get("type") is not None]
        return types or None
    return None


def _requested_chiplet_types_from_inputs(
    chiplet_types: Optional[Sequence[Any]],
    per_chiplet_specs: Optional[Sequence[Mapping[str, Any]]],
) -> Optional[List[Any]]:
    if chiplet_types is not None:
        return list(chiplet_types)
    if per_chiplet_specs:
        values = [spec.get("type", spec.get("chiplet_type")) for spec in per_chiplet_specs]
        values = [value for value in values if value is not None]
        return values or None
    return None


def _requested_chiplet_type_strategy(proposed: Mapping[str, Any]) -> str:
    raw = proposed.get("chiplet_type_strategy", proposed.get("type_strategy", "preserve_prefix"))
    return _normalize_strategy(raw, "chiplet_type_strategy")


def _requested_chiplet_type_fill(proposed: Mapping[str, Any]) -> Optional[Any]:
    for key in ["chiplet_type_fill", "fill_chiplet_type", "uniform_chiplet_type"]:
        if proposed.get(key) is not None:
            return proposed[key]
    strategy = _requested_chiplet_type_strategy(proposed)
    if strategy == "uniform":
        raw_types = proposed.get("chiplet_types", proposed.get("chiplet_type"))
        if isinstance(raw_types, str):
            return raw_types
        if isinstance(raw_types, Sequence) and not isinstance(raw_types, (str, bytes)) and raw_types:
            return raw_types[0]
    return None


def _requested_chiplet_spec_strategy(proposed: Mapping[str, Any]) -> str:
    raw = proposed.get("chiplet_spec_strategy", proposed.get("resource_strategy", "preserve_prefix"))
    return _normalize_strategy(raw, "chiplet_spec_strategy")


def _current_chiplet_field_values(hardware: Mapping[str, Any], field: str) -> List[Any]:
    chiplets = hardware.get("chiplets", [])
    if not isinstance(chiplets, Sequence) or isinstance(chiplets, (str, bytes)):
        return []
    return [chip.get(field) for chip in chiplets if isinstance(chip, Mapping) and chip.get(field) is not None]


def _current_chiplet_types(hardware: Mapping[str, Any]) -> List[Any]:
    return _current_chiplet_field_values(hardware, "type")


def _normalized_chiplet_field_values(
    template: Mapping[str, Any],
    requested_values: Optional[Sequence[Any]],
    field: str,
    count: int,
    candidates: Sequence[int],
    strategy: str = "preserve_prefix",
    fill_value: Optional[Any] = None,
) -> List[int]:
    source = list(requested_values or _current_chiplet_field_values(template, field))
    legal = [int(item) for item in candidates]
    if not legal:
        raise ValueError(f"{field} candidate list cannot be empty.")
    strategy = _normalize_strategy(strategy, "chiplet_spec_strategy")
    requested_fill = int(coerce_to_candidates(fill_value, None, legal)) if fill_value is not None else None
    default_value = requested_fill or _most_common_legal_int(source, legal) or legal[len(legal) // 2]
    if strategy == "uniform":
        return [default_value for _ in range(count)]
    if strategy == "majority":
        majority = _most_common_legal_int(source, legal) or default_value
        return [majority for _ in range(count)]
    normalized: List[int] = []
    for idx in range(count):
        value = source[idx] if idx < len(source) and source[idx] is not None else default_value
        normalized.append(int(coerce_to_candidates(value, default_value, legal)))
    return normalized


def _normalized_chiplet_types(
    template: Mapping[str, Any],
    chiplet_types: Optional[Sequence[Any]],
    count: int,
    legal_types: Sequence[str],
    strategy: str = "preserve_prefix",
    fill_type: Optional[Any] = None,
) -> List[str]:
    source = list(chiplet_types or _current_chiplet_types(template))
    legal = [str(item) for item in legal_types]
    if not legal:
        raise ValueError("chiplet type candidate list cannot be empty.")
    strategy = _normalize_strategy(strategy, "chiplet_type_strategy")
    requested_fill = str(fill_type) if fill_type is not None else None
    if requested_fill is not None and requested_fill not in legal:
        raise ValueError(f"Invalid chiplet_type_fill {requested_fill!r}; legal values are {legal}")
    default_type = requested_fill or _most_common_legal_type(source, legal) or legal[0]
    if strategy == "uniform":
        return [default_type for _ in range(count)]
    if strategy == "majority":
        majority_type = _most_common_legal_type(source, legal) or default_type
        return [majority_type for _ in range(count)]
    normalized: List[str] = []
    for idx in range(count):
        value = str(source[idx]) if idx < len(source) and source[idx] is not None else default_type
        normalized.append(value if value in legal else default_type)
    return normalized


def _normalize_strategy(raw_strategy: Any, label: str) -> str:
    strategy = str(raw_strategy or "preserve_prefix").strip().lower()
    aliases = {
        "preserve": "preserve_prefix",
        "preserve_prefix": "preserve_prefix",
        "prefix": "preserve_prefix",
        "prefix_majority": "preserve_prefix",
        "current": "preserve_prefix",
        "majority": "majority",
        "majority_fill": "majority",
        "most_common": "majority",
        "mainstream": "majority",
        "uniform": "uniform",
        "all": "uniform",
        "set_all": "uniform",
        "same": "uniform",
    }
    if strategy not in aliases:
        raise ValueError(
            f"Unsupported {label} {raw_strategy!r}; "
            "legal values are preserve_prefix, majority, uniform"
        )
    return aliases[strategy]


def _most_common_legal_type(values: Sequence[Any], legal_types: Sequence[str]) -> Optional[str]:
    counts: Counter[str] = Counter(str(item) for item in values if str(item) in legal_types)
    return counts.most_common(1)[0][0] if counts else None


def _most_common_legal_int(values: Sequence[Any], legal_values: Sequence[int]) -> Optional[int]:
    legal = {int(item) for item in legal_values}
    counts: Counter[int] = Counter()
    for value in values:
        try:
            integer = int(value)
        except (TypeError, ValueError):
            continue
        if integer in legal:
            counts[integer] += 1
    return counts.most_common(1)[0][0] if counts else None


def _most_common_int(values: Sequence[Any]) -> Optional[int]:
    counts: Counter[int] = Counter()
    for value in values:
        try:
            counts[int(value)] += 1
        except (TypeError, ValueError):
            continue
    return counts.most_common(1)[0][0] if counts else None


def _step_value(value: int, candidates: Sequence[int], direction: int) -> int:
    ordered = sorted(set(int(v) for v in candidates))
    if value not in ordered:
        return min(ordered, key=lambda x: abs(x - value))
    idx = ordered.index(value)
    idx = max(0, min(len(ordered) - 1, idx + (1 if direction > 0 else -1)))
    return ordered[idx]


def _add_shape_notes(
    old: Mapping[str, Any],
    shape_candidate: Mapping[str, Any],
    notes: List[str],
) -> None:
    old_shape = hardware_shape(old)
    new_shape = (int(shape_candidate["chip_y"]), int(shape_candidate["chip_x"]))
    if old_shape != new_shape:
        notes.append(
            f"array_shape changed {old_shape[0] if old_shape else None}x{old_shape[1] if old_shape else None}"
            f"->{new_shape[0]}x{new_shape[1]}; "
            f"num_chiplets {old.get('num_chiplets')}->{shape_candidate['num_chiplets']}"
        )


def _add_resource_notes(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    notes: List[str],
) -> None:
    for field, label in [("compute_units", "compute_units"), ("buffer_size", "buffer_size"), ("type", "chiplet_type")]:
        old_counts = Counter(str(value) for value in _current_chiplet_field_values(old, field))
        new_counts = Counter(str(value) for value in _current_chiplet_field_values(new, field))
        if old_counts != new_counts:
            notes.append(f"chiplets.{label} distribution changed {dict(old_counts)}->{dict(new_counts)}")
