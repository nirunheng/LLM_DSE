# ATLAS 集成修订日志

## 修订内容总览

### 1. `chiplet_tuner/simulators/atlas_config.py`
- **MODEL_PRESENTS → MODEL_PRESETS**: 修复变量名拼写错误
- **resolve_model_path → resolve_model_preset**: 函数重命名
- **batchsize → batch_size**: 修复字段名
- **`sorted{MODEL_PRESENTS}` → `sorted(MODEL_PRESETS)`**: 修复语法错误（花括号改圆括号）
- 添加 `resolved_config_path` 字段并写入 `model_info` 字典
- 修复 `modle_path` → `model_path` 拼写错误
- 添加完整的类型注解
- 完善 `hardware_dict_to_chip_yaml()`: 补全 NoC、DRAM、buffer 等预设，DRAM config_path 改为 `configs/architecture/dram/cloud/cloud_1TBps.yaml`
- **build_system_yaml() 参数类型**: `chip_yaml_path: Path` → `chip_yaml_path: str`（与内部 `str(Path(...).resolve())` 兼容）

### 2. `chiplet_tuner/simulators/atlas_simulator.py`
- **import 路径修复**: 
  - `chiplet_tuner.core.simulators.base` → `chiplet_tuner.simulators.base`
  - `chiplet_tuner.core.schemes` → `chiplet_tuner.core.schemas`
- **output_path → output_root**: 避免与 `EvaluationResult` 的 `run_dir` 冲突
- **返回类型**: `-> Dict[str, Any]` → `-> EvaluationResult`
- **`exec_rsc.csv` → `exec_res.csv`**: 修复文件名
- **system YAML 生成**: Adapter 不再提前生成 system.yaml，交给 wrapper 脚本处理
- **`cwd=self.atlas_root` → `cwd=project_root`**，并增加 `env` 传递 `PYTHONPATH`/`LD_LIBRARY_PATH`
- **`project_root`**: 修正为 `parents[2]`（之前用了 `parents[1]` 指向了 `chiplet_tuner/`）
- **`check=True`**: 添加 subprocess.run 的 check 参数
- **解析 csv 移出 `with exec_log.open(...)` 块**: 避免上下文管理器关闭后文件描述符问题

### 3. `chiplet_tuner/simulators/run_atlas.py`
- **所有 pybind11 kwargs 修复**: `hardware_parser.py` 中 `ControllerConfig(power=..., area=...)` 改为 `obj = ControllerConfig(); obj.power = ...; obj.area = ...`（因为 pybind11 绑定只支持无参构造 + 属性赋值）
- **`model_present = Path(sys.argv[3])` → `model_preset = sys.argv[3]`**: 修复变量名
- **chip YAML 写入路径**: 从 `chip_json_path` 改为独立 `chip.yaml` 文件
- **`context_length_lis` → `context_length_list`**: 修复参数名
- **`itermediate_result` → `intermediate_result_dir`**: 修复参数名
- **`chdir` 后 `sys.path.insert` 移除**: 改为模块顶层插入，确保 multiprocessing `spawn` context 的 worker 进程能找到 `frontend` 模块
- 添加 `atlas_root` 模块级变量：`_atlas_root_path`
- 生成 `exec_res.csv`（Compass 兼容格式）：`latency, energy, edp, mc`
- 生成简化的 detail JSONs

### 4. `chiplet_tuner/pipeline/tuner.py`
- **`_validate_required_metrics` 不再强制 mc**: 第 1549 行移除 `mc` 必须在 metrics 中的要求（改为可选，默认 1.0）

### 5. `chiplet_tuner/cli.py`
- **`--atlas-root` 默认路径修复**: `ATLAS_MICRO-2026-main` → `ATLAS-MICRO-2026-main`（下划线改连字符）
- **添加 `--atlas-model` 参数**: 可选值 `[opt_66b, opt_6.7b, llama3_8b, llama3_70b]`
- **修复 `wrapper_script` 路径**: `simulate/run_atlas.py` → `simulators/run_atlas.py`
- **`output_path` → `output_root`**: 与 adapter 构造对齐

### 6. `chiplet_tuner/simulators/__init__.py`
- 导出 `AtlasSimulatorAdapter`

### 7. `chiplet_tuner/core/search_space.py`
- 添加 `ATLAS_DEFAULT_HARDWARE_SEARCH_SPACE`（mac_num, vec_num, buffer_size, buffer_bw, frequency, core_num 的候选值集）

### 8. `ATLAS-MICRO-2026-main/frontend/hardware_parser.py`
- **所有 `XXXConfig(kwargs)` → `obj = XXXConfig(); obj.attr = value`**:
  - `load_controller_config_from_yaml`
  - `load_matrix_config_from_yaml`
  - `load_vector_config_from_yaml`
  - `load_buffer_config_from_yaml`
  - `load_dram_config_from_yaml`
  - `load_noc_config_from_yaml`
  - `load_chip_config_from_yaml`

---

## 当前阻塞点

### ATLAS GEMM Tiling Exploration Multiprocessing 死锁

**症状**:
- `run_atlas.py` 或直接调用 ATLAS 时，卡在第一个 GEMM 算子 `qkv_proj` 的 tiling exploration
- 打印 `Processing operator qkv_proj` 后无后续输出
- 产生大量 worker 子进程（51 个），都处于 sleep 状态

**根本原因**:
- ATLAS 的 `tiling_explorer_cloud.py` 第 344-345 行强制使用 `multiprocessing.get_context('spawn')` 创建 Pool
- `spawn` context 在 Python 3.12 下需要子进程能完整 import 父模块
- worker 函数 `explore_gemm_comp_worker` 中的 `set_pdeathsig` 在处理 GEMM 算子时打印 `Find unsupported operator type: SimulatorOperatorType.GEMM` 并退出
- `Pool.starmap()` 等待所有 worker 完成，但某些 worker 提前退出导致死锁

**之前成功运行（2026-11-06 14:04）**:
- 使用 ATLAS 自带的 `inference_test_auto.py` + `test_cloud_system.yaml`（引用 `test_chip_16ch.yaml`）成功跑出 `opt_66b` 的完整结果
- 结果：latency=0.00254s, energy=0.306J

**可能解决方案**:
1. 在 run_atlas.py 中设置环境变量 `OMP_NUM_THREADS=1` 或限制 CPU 数量
2. 修改 `tiling_explorer_cloud.py` 第 2267 行的 `num_workers` 默认值或使用 `fork` context
3. 使用 `simplejson` 或其他序列化库替代 pickle（`spawn` 依赖 pickle）

### langgraph.checkpoint.sqlite 缺失
- 不影响运行，自动回退到 `MemorySaver`
- 如需持久化，需 `pip install langgraph-checkpoint-sqlite`

---

## 已验证的导入/语法检查

```
OK: chiplet_tuner/simulators/atlas_config.py
OK: chiplet_tuner/simulators/atlas_simulator.py
OK: chiplet_tuner/simulators/run_atlas.py
OK: chiplet_tuner/simulators/__init__.py
OK: chiplet_tuner/cli.py

All imports OK
MODEL_PRESETS keys: ['llama3_70b', 'llama3_8b', 'opt_6.7b', 'opt_66b']
Chip YAML generated OK
```

## DSE 执行状态

### ATLAS DSE
- CLI 参数解析 ✅
- adapter → subprocess ✅
- chip YAML 生成 ✅
- system YAML 生成 ✅
- **ATLAS inference 执行**: ❌ (卡在 multiprocessing tiling exploration)

### Compass DSE
- 未测试（需要 Compass 环境）

## 文件结构总览

```
chiplet_tuner/
├── cli.py                                    # 入口：增加 --atlas-root/--atlas-model 参数
├── core/
│   ├── search_space.py                       # ATLAS 搜索空间候选值
│   └── schemas.py                            # EvaluationResult
├── pipeline/
│   └── tuner.py                              # _validate_required_metrics 不强制 mc
└── simulators/
    ├── __init__.py                           # 导出 AtlasSimulatorAdapter
    ├── atlas_config.py                       # 模型预设 + chip YAML 转换
    ├── atlas_simulator.py                    # SimulatorAdapter 实现
    └── run_atlas.py                          # 命令行包装脚本

ATLAS-MICRO-2026-main/
└── frontend/
    └── hardware_parser.py                    # 修复: kwargs → 属性赋值
```