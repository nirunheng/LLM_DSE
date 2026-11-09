# LLM Trace

`raw_json/` stores raw request/response JSON for every LLM call. `view_md/` stores readable per-agent dialogue expansions.

## Readable Dialogues

| agent | dialogue |
|---|---|
| model_level | `view_md/model_level_agent_dialogue.md` |
| layer_level | `view_md/layer_level_agent_dialogue.md` |
| solution_generation | `view_md/solution_generation_agent_dialogue.md` |

## Raw Calls

| call | status | agent | task | duration_s | raw input | raw output |
|---:|---|---|---|---:|---|---|
| 0000 | ok | model_level | react_tool_use | 1.521 | `raw_json/0000_input_model_level_react_tool_use.json` | `raw_json/0000_output_model_level_react_tool_use.json` |
| 0001 | ok | model_level | react_tool_use | 3.107 | `raw_json/0001_input_model_level_react_tool_use.json` | `raw_json/0001_output_model_level_react_tool_use.json` |
| 0002 | ok | model_level | react_tool_use | 2.240 | `raw_json/0002_input_model_level_react_tool_use.json` | `raw_json/0002_output_model_level_react_tool_use.json` |
| 0003 | ok | model_level | react_tool_use | 2.560 | `raw_json/0003_input_model_level_react_tool_use.json` | `raw_json/0003_output_model_level_react_tool_use.json` |
| 0004 | ok | model_level | react_tool_use | 3.929 | `raw_json/0004_input_model_level_react_tool_use.json` | `raw_json/0004_output_model_level_react_tool_use.json` |
| 0005 | ok | model_level | react_tool_use | 3.065 | `raw_json/0005_input_model_level_react_tool_use.json` | `raw_json/0005_output_model_level_react_tool_use.json` |
| 0006 | ok | model_level | react_tool_use | 3.563 | `raw_json/0006_input_model_level_react_tool_use.json` | `raw_json/0006_output_model_level_react_tool_use.json` |
| 0007 | ok | model_level | react_tool_use | 4.364 | `raw_json/0007_input_model_level_react_tool_use.json` | `raw_json/0007_output_model_level_react_tool_use.json` |
| 0008 | ok | model_level | react_tool_use | 40.488 | `raw_json/0008_input_model_level_react_tool_use.json` | `raw_json/0008_output_model_level_react_tool_use.json` |
| 0009 | ok | layer_level | react_tool_use | 7.545 | `raw_json/0009_input_layer_level_react_tool_use.json` | `raw_json/0009_output_layer_level_react_tool_use.json` |
| 0010 | ok | layer_level | react_tool_use | 2.972 | `raw_json/0010_input_layer_level_react_tool_use.json` | `raw_json/0010_output_layer_level_react_tool_use.json` |
| 0011 | ok | layer_level | react_tool_use | 2.505 | `raw_json/0011_input_layer_level_react_tool_use.json` | `raw_json/0011_output_layer_level_react_tool_use.json` |
| 0012 | ok | layer_level | react_tool_use | 4.859 | `raw_json/0012_input_layer_level_react_tool_use.json` | `raw_json/0012_output_layer_level_react_tool_use.json` |
| 0013 | ok | layer_level | react_tool_use | 3.131 | `raw_json/0013_input_layer_level_react_tool_use.json` | `raw_json/0013_output_layer_level_react_tool_use.json` |
| 0014 | error | layer_level | react_tool_use | 3.285 | `raw_json/0014_input_layer_level_react_tool_use.json` | `raw_json/0014_output_layer_level_react_tool_use.json` |
| 0015 | ok | layer_level | llm_retry_correction | 4.237 | `raw_json/0015_input_layer_level_llm_retry_correction.json` | `raw_json/0015_output_layer_level_llm_retry_correction.json` |
| 0016 | ok | layer_level | llm_retry_correction | 11.753 | `raw_json/0016_input_layer_level_llm_retry_correction.json` | `raw_json/0016_output_layer_level_llm_retry_correction.json` |
| 0017 | ok | solution_generation | react_tool_use | 4.987 | `raw_json/0017_input_solution_generation_react_tool_use.json` | `raw_json/0017_output_solution_generation_react_tool_use.json` |
| 0018 | ok | solution_generation | react_tool_use | 3.299 | `raw_json/0018_input_solution_generation_react_tool_use.json` | `raw_json/0018_output_solution_generation_react_tool_use.json` |
| 0019 | ok | solution_generation | react_tool_use | 3.590 | `raw_json/0019_input_solution_generation_react_tool_use.json` | `raw_json/0019_output_solution_generation_react_tool_use.json` |
| 0020 | ok | solution_generation | react_tool_use | 3.000 | `raw_json/0020_input_solution_generation_react_tool_use.json` | `raw_json/0020_output_solution_generation_react_tool_use.json` |
| 0021 | ok | solution_generation | react_tool_use | 3.817 | `raw_json/0021_input_solution_generation_react_tool_use.json` | `raw_json/0021_output_solution_generation_react_tool_use.json` |
| 0022 | ok | solution_generation | react_tool_use | 3.587 | `raw_json/0022_input_solution_generation_react_tool_use.json` | `raw_json/0022_output_solution_generation_react_tool_use.json` |
| 0023 | ok | solution_generation | react_tool_use | 5.795 | `raw_json/0023_input_solution_generation_react_tool_use.json` | `raw_json/0023_output_solution_generation_react_tool_use.json` |
| 0024 | ok | solution_generation | react_tool_use | 4.351 | `raw_json/0024_input_solution_generation_react_tool_use.json` | `raw_json/0024_output_solution_generation_react_tool_use.json` |
| 0025 | ok | solution_generation | react_tool_use | 6.488 | `raw_json/0025_input_solution_generation_react_tool_use.json` | `raw_json/0025_output_solution_generation_react_tool_use.json` |
| 0026 | ok | solution_generation | react_tool_use | 5.719 | `raw_json/0026_input_solution_generation_react_tool_use.json` | `raw_json/0026_output_solution_generation_react_tool_use.json` |
