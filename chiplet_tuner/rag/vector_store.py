from __future__ import annotations

import copy
import hashlib
import json
import math
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from chiplet_tuner.rag.embeddings import HashingEmbeddingModel, Vector


BOTTLENECK_VECTOR_WEIGHT = 0.75
HARDWARE_VECTOR_WEIGHT = 0.25


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def hardware_fingerprint(hardware: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(hardware).encode("utf-8")).hexdigest()[:16]


def summarize_hardware(hardware: Dict[str, Any]) -> Dict[str, Any]:
    chiplets = hardware.get("chiplets", [])
    if not isinstance(chiplets, list):
        chiplets = []
    chiplet_types = Counter(str(chip.get("type", "unknown")) for chip in chiplets if isinstance(chip, dict))
    compute_units = Counter(str(chip.get("compute_units")) for chip in chiplets if isinstance(chip, dict))
    buffer_sizes = Counter(str(chip.get("buffer_size")) for chip in chiplets if isinstance(chip, dict))
    total_compute = sum(float(chip.get("compute_units", 0.0)) for chip in chiplets if isinstance(chip, dict))
    total_buffer = sum(float(chip.get("buffer_size", 0.0)) for chip in chiplets if isinstance(chip, dict))
    return {
        "fingerprint": hardware_fingerprint(hardware),
        "num_chiplets": hardware.get("num_chiplets", len(chiplets)),
        "derived_array_shape": [hardware.get("chip_y"), hardware.get("chip_x")],
        "system_params": {
            "dram_bw": hardware.get("dram_bw"),
            "nop_bw": hardware.get("nop_bw"),
            "micro_batch": hardware.get("micro_batch"),
            "tensor_parall": hardware.get("tensor_parall"),
        },
        "per_chiplet_architecture": {
            "chiplet_type": dict(chiplet_types),
            "compute_units": dict(compute_units),
            "buffer_size": dict(buffer_sizes),
        },
        "total_compute_units": total_compute,
        "total_buffer_size": total_buffer,
    }


def _positive_int_or_none(value: Any) -> Optional[int]:
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    return integer if integer > 0 else None


@dataclass
class HistoryRecord:
    record_id: str
    vector: Vector
    bottleneck_description: str
    hardware: Dict[str, Any]
    solution: Dict[str, Any]
    metrics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    bottleneck_state: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class RetrievedCase:
    score: float
    record: HistoryRecord


def build_bottleneck_text(
    bottleneck_description: str,
    bottleneck_state: Optional[Dict[str, Any]] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> str:
    payload: Dict[str, Any] = {"bottleneck_description": bottleneck_description}
    if bottleneck_state:
        payload["bottleneck_state"] = bottleneck_state
    if extra_context:
        payload["extra_context"] = extra_context
    return canonical_json(payload)


def build_hardware_text(hardware: Dict[str, Any]) -> str:
    return canonical_json({"hardware": hardware})


def build_retrieval_text(
    bottleneck_description: str,
    hardware: Dict[str, Any],
    extra_context: Optional[Dict[str, Any]] = None,
    bottleneck_state: Optional[Dict[str, Any]] = None,
) -> str:
    return canonical_json(
        {
            "bottleneck_channel": json.loads(
                build_bottleneck_text(
                    bottleneck_description=bottleneck_description,
                    bottleneck_state=bottleneck_state,
                    extra_context=extra_context,
                )
            ),
            "hardware_channel": {"hardware": hardware},
        }
    )


class HistoryVectorStore:
    """SQLite-backed vector database for previous tuning cases."""

    schema_version = 2

    def __init__(
        self,
        path: Path | str,
        embedding_model: Optional[Any] = None,
        embedding_fn: Optional[Callable[[str], Vector]] = None,
    ) -> None:
        self.path = Path(path)
        if self.path.suffix.lower() == ".json":
            raise ValueError(
                "HistoryVectorStore now uses SQLite only. "
                f"Use a .sqlite path instead of {self.path}."
            )
        self.embedding_model = embedding_model or HashingEmbeddingModel()
        self.embedding_fn = embedding_fn or self.embedding_model.embed
        self.embedding_model_name = getattr(self.embedding_model, "model_name", type(self.embedding_model).__name__)
        self.records: List[HistoryRecord] = []
        self._connect()
        self._setup()
        self.load()

    def _connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row

    def _setup(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS store_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS history_cases (
                record_id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                bottleneck_description TEXT NOT NULL,
                bottleneck_state_json TEXT NOT NULL,
                hardware_json TEXT NOT NULL,
                solution_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS history_embeddings (
                record_id TEXT PRIMARY KEY,
                embedding_model TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                FOREIGN KEY(record_id) REFERENCES history_cases(record_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_history_cases_created_at
                ON history_cases(created_at);
            CREATE INDEX IF NOT EXISTS idx_history_embeddings_model
                ON history_embeddings(embedding_model);
            """
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO store_metadata(key, value) VALUES (?, ?)",
            ("schema_version", str(self.schema_version)),
        )
        self.conn.commit()

    def load(self) -> None:
        rows = self.conn.execute(
            """
            SELECT c.record_id, c.created_at, c.bottleneck_description, c.bottleneck_state_json,
                   c.hardware_json, c.solution_json, c.metrics_json, c.metadata_json, e.vector_json
            FROM history_cases c
            JOIN history_embeddings e ON e.record_id = c.record_id
            ORDER BY c.created_at ASC
            """
        ).fetchall()
        self.records = []
        for row in rows:
            hardware = _loads_json(row["hardware_json"], {})
            solution = _loads_json(row["solution_json"], {})
            metadata = _loads_json(row["metadata_json"], {})
            metadata.setdefault("hardware_fingerprint", hardware_fingerprint(hardware))
            updated_hardware = solution.get("updated_hardware") if isinstance(solution, dict) else None
            if isinstance(updated_hardware, dict):
                metadata.setdefault("solution_hardware_fingerprint", hardware_fingerprint(updated_hardware))
            self.records.append(
                HistoryRecord(
                    record_id=str(row["record_id"]),
                    vector=[float(value) for value in _loads_json(row["vector_json"], [])],
                    bottleneck_description=str(row["bottleneck_description"]),
                    bottleneck_state=_loads_json(row["bottleneck_state_json"], {}),
                    hardware=hardware,
                    solution=solution,
                    metrics=_loads_json(row["metrics_json"], {}),
                    metadata=metadata,
                    created_at=float(row["created_at"]),
                )
            )

    def save(self) -> None:
        self.conn.commit()
        self.load()

    def embed_state(
        self,
        bottleneck_description: str,
        hardware: Dict[str, Any],
        extra_context: Optional[Dict[str, Any]] = None,
        bottleneck_state: Optional[Dict[str, Any]] = None,
    ) -> Vector:
        bottleneck_text = build_bottleneck_text(bottleneck_description, bottleneck_state, extra_context)
        hardware_text = build_hardware_text(hardware)
        bottleneck_vector = self.embedding_fn(bottleneck_text)
        hardware_vector = self.embedding_fn(hardware_text)
        return _concat_weighted_vectors(
            bottleneck_vector,
            hardware_vector,
            bottleneck_weight=BOTTLENECK_VECTOR_WEIGHT,
            hardware_weight=HARDWARE_VECTOR_WEIGHT,
        )

    def add_case(
        self,
        bottleneck_description: str,
        hardware: Dict[str, Any],
        solution: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        bottleneck_state: Optional[Dict[str, Any]] = None,
        record_id: Optional[str] = None,
        created_at: Optional[float] = None,
        save: bool = True,
    ) -> HistoryRecord:
        metrics = copy.deepcopy(metrics or {})
        solution = _clean_solution_for_storage(copy.deepcopy(solution or {}))
        hardware = copy.deepcopy(hardware or {})
        bottleneck_state = copy.deepcopy(bottleneck_state or {})
        metadata = copy.deepcopy(metadata or {})
        metadata.setdefault("hardware_fingerprint", hardware_fingerprint(hardware))
        updated_hardware = solution.get("updated_hardware") if isinstance(solution, dict) else None
        if isinstance(updated_hardware, dict):
            metadata.setdefault("solution_hardware_fingerprint", hardware_fingerprint(updated_hardware))
        vector = self.embed_state(
            bottleneck_description=bottleneck_description,
            hardware=hardware,
            bottleneck_state=bottleneck_state,
        )
        if record_id is None:
            basis = canonical_json(
                {
                    "bottleneck_description": bottleneck_description,
                    "bottleneck_state": bottleneck_state,
                    "hardware": hardware,
                    "solution": solution,
                    "metrics": metrics,
                }
            )
            record_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
        existing = self._get_record(record_id)
        if existing is not None:
            return existing
        created = float(created_at if created_at is not None else time.time())
        self.conn.execute(
            """
            INSERT INTO history_cases(
                record_id, created_at, bottleneck_description, bottleneck_state_json,
                hardware_json, solution_json, metrics_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                created,
                bottleneck_description,
                canonical_json(bottleneck_state),
                canonical_json(hardware),
                canonical_json(solution),
                canonical_json(metrics),
                canonical_json(metadata),
            ),
        )
        self.conn.execute(
            """
            INSERT INTO history_embeddings(record_id, embedding_model, dimension, vector_json)
            VALUES (?, ?, ?, ?)
            """,
            (record_id, self.embedding_model_name, len(vector), canonical_json(vector)),
        )
        if save:
            self.save()
        else:
            self.records.append(
                HistoryRecord(
                    record_id=record_id,
                    vector=vector,
                    bottleneck_description=bottleneck_description,
                    bottleneck_state=bottleneck_state,
                    hardware=hardware,
                    solution=solution,
                    metrics=metrics,
                    metadata=metadata,
                    created_at=created,
                )
            )
        return self._get_record(record_id) or self.records[-1]

    def search(
        self,
        bottleneck_description: str,
        hardware: Dict[str, Any],
        top_k: int = 5,
        min_score: float = -1.0,
        metadata_filter: Optional[Dict[str, Any]] = None,
        exclude_hardware_fingerprints: Optional[set[str]] = None,
        bottleneck_state: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedCase]:
        if top_k <= 0 or not self.records:
            return []
        query_vector = self.embed_state(
            bottleneck_description=bottleneck_description,
            hardware=hardware,
            bottleneck_state=bottleneck_state,
        )
        hits = []
        for record in self.records:
            if metadata_filter and not self._metadata_matches(record.metadata, metadata_filter):
                continue
            if exclude_hardware_fingerprints and record.metadata.get(
                "hardware_fingerprint"
            ) in exclude_hardware_fingerprints:
                continue
            try:
                score = cosine_similarity(query_vector, record.vector)
            except ValueError:
                continue
            if score >= min_score:
                hits.append(RetrievedCase(score=score, record=record))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:top_k]

    def hardware_seen(self, hardware: Dict[str, Any]) -> bool:
        fingerprint = hardware_fingerprint(hardware)
        return any(record.metadata.get("hardware_fingerprint") == fingerprint for record in self.records)

    def all_hardware_fingerprints(self) -> set[str]:
        return {
            str(record.metadata["hardware_fingerprint"])
            for record in self.records
            if record.metadata.get("hardware_fingerprint")
        }

    def _get_record(self, record_id: str) -> Optional[HistoryRecord]:
        for record in self.records:
            if record.record_id == record_id:
                return record
        row = self.conn.execute(
            """
            SELECT c.record_id, c.created_at, c.bottleneck_description, c.bottleneck_state_json,
                   c.hardware_json, c.solution_json, c.metrics_json, c.metadata_json, e.vector_json
            FROM history_cases c
            JOIN history_embeddings e ON e.record_id = c.record_id
            WHERE c.record_id = ?
            """,
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return HistoryRecord(
            record_id=str(row["record_id"]),
            vector=[float(value) for value in _loads_json(row["vector_json"], [])],
            bottleneck_description=str(row["bottleneck_description"]),
            bottleneck_state=_loads_json(row["bottleneck_state_json"], {}),
            hardware=_loads_json(row["hardware_json"], {}),
            solution=_loads_json(row["solution_json"], {}),
            metrics=_loads_json(row["metrics_json"], {}),
            metadata=_loads_json(row["metadata_json"], {}),
            created_at=float(row["created_at"]),
        )

    def _metadata_matches(self, metadata: Dict[str, Any], expected: Dict[str, Any]) -> bool:
        for key, value in expected.items():
            if isinstance(value, (list, tuple, set)):
                if metadata.get(key) not in value:
                    return False
            elif metadata.get(key) != value:
                return False
        return True

    def import_jsonl(self, path: Path | str, save: bool = True) -> int:
        imported = 0
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                self.add_case(
                    bottleneck_description=item["bottleneck_description"],
                    bottleneck_state=item.get("bottleneck_state"),
                    hardware=item["hardware"],
                    solution=item["solution"],
                    metrics=item.get("metrics"),
                    metadata=item.get("metadata"),
                    save=False,
                )
                imported += 1
        if save:
            self.save()
        return imported

    def __len__(self) -> int:
        return len(self.records)


def summarize_cases(cases: Iterable[RetrievedCase]) -> List[Dict[str, Any]]:
    return [_case_digest(case) for case in cases]


def _case_digest(case: RetrievedCase) -> Dict[str, Any]:
    solution = case.record.solution if isinstance(case.record.solution, dict) else {}
    return {
        "score": round(case.score, 4),
        "bottleneck_description": _truncate_text(case.record.bottleneck_description, 1200),
        "bottleneck_state": _agent_bottleneck_state(case.record.bottleneck_state),
        "hardware_summary": summarize_hardware(case.record.hardware),
        "solution_summary": _agent_solution(solution),
        "evaluation_result": _agent_metrics(case.record.metrics),
        "metadata": _agent_metadata(case.record.metadata),
    }


def _concat_weighted_vectors(
    bottleneck_vector: Sequence[float],
    hardware_vector: Sequence[float],
    bottleneck_weight: float,
    hardware_weight: float,
) -> Vector:
    if len(bottleneck_vector) != len(hardware_vector):
        raise ValueError(
            f"Embedding dimension mismatch: bottleneck={len(bottleneck_vector)}, hardware={len(hardware_vector)}"
        )
    bottleneck_scale = math.sqrt(bottleneck_weight)
    hardware_scale = math.sqrt(hardware_weight)
    return [float(value) * bottleneck_scale for value in bottleneck_vector] + [
        float(value) * hardware_scale for value in hardware_vector
    ]


def _loads_json(text: Any, default: Any) -> Any:
    if not isinstance(text, str):
        return copy.deepcopy(default)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return copy.deepcopy(default)


def _clean_solution_for_storage(solution: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = copy.deepcopy(solution)
    cleaned.pop("improvement", None)
    cleaned.pop("updated_hardware_fingerprint", None)
    return cleaned


def _agent_solution(solution: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(solution, dict):
        return {}
    summary: Dict[str, Any] = {}
    for key in ["strategy", "actions"]:
        if key in solution:
            summary[key] = copy.deepcopy(solution[key])
    rationale = solution.get("rationale")
    if isinstance(rationale, str) and rationale:
        summary["rationale"] = _truncate_text(rationale, 900)
    notes = solution.get("notes") if isinstance(solution.get("notes"), dict) else {}
    for key in ["history_usage", "cost_risk", "expected_objective_direction", "risk"]:
        value = notes.get(key)
        if isinstance(value, str) and value:
            summary.setdefault("notes", {})[key] = _truncate_text(value, 700)
    hardware_update = solution.get("hardware_update")
    if isinstance(hardware_update, dict):
        summary["hardware_update"] = copy.deepcopy(hardware_update)
    updated_hardware = solution.get("updated_hardware")
    if isinstance(updated_hardware, dict):
        summary["updated_hardware_summary"] = summarize_hardware(updated_hardware)
    return summary


def _agent_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    keep = [
        "phase",
        "source_iteration",
        "base_iteration",
        "before_objective",
        "after_objective",
        "objective_change_ratio",
        "objective_improvement_ratio",
        "primary_impact",
        "dominant_root_cause",
        "top_layers",
    ]
    compact = {key: copy.deepcopy(metadata[key]) for key in keep if key in metadata}
    analysis_base = metadata.get("analysis_base")
    if isinstance(analysis_base, dict):
        compact["analysis_base"] = {
            key: copy.deepcopy(analysis_base[key])
            for key in ["source", "base_key", "iteration", "objective", "metrics"]
            if key in analysis_base
        }
    return compact


def _agent_bottleneck_state(state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    compact: Dict[str, Any] = {}
    for key in ["primary_impact", "dominant_root_cause", "root_cause_summary", "recommended_focus"]:
        if key in state:
            compact[key] = copy.deepcopy(state[key])
    diagnoses = state.get("layer_diagnoses")
    if isinstance(diagnoses, list):
        compact["key_layers"] = [_compact_layer_diagnosis(item) for item in diagnoses[:5] if isinstance(item, dict)]
    return compact


def _compact_layer_diagnosis(item: Dict[str, Any]) -> Dict[str, Any]:
    compact = {
        key: copy.deepcopy(item[key])
        for key in [
            "layerID",
            "layerName",
            "operator_group",
            "impact_types",
            "root_causes",
            "dominant_root_cause",
            "root_cause_ratios",
        ]
        if key in item
    }
    features = item.get("load_features")
    if isinstance(features, dict):
        keep = [
            "latency_sum",
            "latency_share",
            "energy",
            "energy_share",
            "critical_end",
            "compute_time_share",
            "memory_time_share",
            "communication_time_share",
        ]
        compact["load_features"] = {key: features[key] for key in keep if key in features}
    diagnosis = item.get("diagnosis")
    if isinstance(diagnosis, str) and diagnosis:
        compact["diagnosis"] = _truncate_text(diagnosis, 400)
    return compact


def _agent_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(metrics, dict):
        return {}
    keep_metric_keys = ["latency", "energy", "mc", "objective", "edp"]
    keep_improvement_keys = [
        "latency_change_ratio",
        "energy_change_ratio",
        "mc_change_ratio",
        "objective_change_ratio",
        "latency_improvement_ratio",
        "energy_improvement_ratio",
        "mc_improvement_ratio",
        "objective_improvement_ratio",
    ]
    if any(key in metrics for key in ["before", "after", "improvement"]):
        compact: Dict[str, Any] = {}
        for key in ["before", "after"]:
            value = metrics.get(key)
            if isinstance(value, dict):
                compact[key] = {name: value[name] for name in keep_metric_keys if name in value}
        improvement = metrics.get("improvement")
        if isinstance(improvement, dict):
            compact["improvement"] = {name: improvement[name] for name in keep_improvement_keys if name in improvement}
        return compact
    return {name: metrics[name] for name in keep_metric_keys if name in metrics}


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."
