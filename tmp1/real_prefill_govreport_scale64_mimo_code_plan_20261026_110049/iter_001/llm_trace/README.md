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
| 0000 | ok | model_level | react_tool_use | 1.800 | `raw_json/0000_input_model_level_react_tool_use.json` | `raw_json/0000_output_model_level_react_tool_use.json` |
| 0001 | ok | model_level | react_tool_use | 2.058 | `raw_json/0001_input_model_level_react_tool_use.json` | `raw_json/0001_output_model_level_react_tool_use.json` |
| 0002 | ok | model_level | react_tool_use | 1.300 | `raw_json/0002_input_model_level_react_tool_use.json` | `raw_json/0002_output_model_level_react_tool_use.json` |
| 0003 | ok | model_level | react_tool_use | 3.681 | `raw_json/0003_input_model_level_react_tool_use.json` | `raw_json/0003_output_model_level_react_tool_use.json` |
| 0004 | ok | model_level | react_tool_use | 5.663 | `raw_json/0004_input_model_level_react_tool_use.json` | `raw_json/0004_output_model_level_react_tool_use.json` |
| 0005 | ok | model_level | react_tool_use | 12.254 | `raw_json/0005_input_model_level_react_tool_use.json` | `raw_json/0005_output_model_level_react_tool_use.json` |
| 0006 | ok | model_level | react_tool_use | 4.921 | `raw_json/0006_input_model_level_react_tool_use.json` | `raw_json/0006_output_model_level_react_tool_use.json` |
| 0007 | ok | model_level | react_tool_use | 4.336 | `raw_json/0007_input_model_level_react_tool_use.json` | `raw_json/0007_output_model_level_react_tool_use.json` |
| 0008 | ok | model_level | react_tool_use | 13.352 | `raw_json/0008_input_model_level_react_tool_use.json` | `raw_json/0008_output_model_level_react_tool_use.json` |
| 0009 | ok | layer_level | react_tool_use | 3.212 | `raw_json/0009_input_layer_level_react_tool_use.json` | `raw_json/0009_output_layer_level_react_tool_use.json` |
| 0010 | ok | layer_level | react_tool_use | 7.783 | `raw_json/0010_input_layer_level_react_tool_use.json` | `raw_json/0010_output_layer_level_react_tool_use.json` |
| 0011 | ok | layer_level | react_tool_use | 3.292 | `raw_json/0011_input_layer_level_react_tool_use.json` | `raw_json/0011_output_layer_level_react_tool_use.json` |
| 0012 | ok | layer_level | react_tool_use | 4.452 | `raw_json/0012_input_layer_level_react_tool_use.json` | `raw_json/0012_output_layer_level_react_tool_use.json` |
| 0013 | ok | layer_level | react_tool_use | 29.937 | `raw_json/0013_input_layer_level_react_tool_use.json` | `raw_json/0013_output_layer_level_react_tool_use.json` |
| 0014 | ok | solution_generation | react_tool_use | 3.025 | `raw_json/0014_input_solution_generation_react_tool_use.json` | `raw_json/0014_output_solution_generation_react_tool_use.json` |
| 0015 | error | solution_generation | react_tool_use | 2.334 | `raw_json/0015_input_solution_generation_react_tool_use.json` | `raw_json/0015_output_solution_generation_react_tool_use.json` |
| 0016 | ok | solution_generation | llm_retry_correction | 1.502 | `raw_json/0016_input_solution_generation_llm_retry_correction.json` | `raw_json/0016_output_solution_generation_llm_retry_correction.json` |
| 0017 | ok | solution_generation | react_tool_use | 2.473 | `raw_json/0017_input_solution_generation_react_tool_use.json` | `raw_json/0017_output_solution_generation_react_tool_use.json` |
| 0018 | ok | solution_generation | react_tool_use | 1.624 | `raw_json/0018_input_solution_generation_react_tool_use.json` | `raw_json/0018_output_solution_generation_react_tool_use.json` |
| 0019 | ok | solution_generation | react_tool_use | 3.244 | `raw_json/0019_input_solution_generation_react_tool_use.json` | `raw_json/0019_output_solution_generation_react_tool_use.json` |
| 0020 | ok | solution_generation | react_tool_use | 2.939 | `raw_json/0020_input_solution_generation_react_tool_use.json` | `raw_json/0020_output_solution_generation_react_tool_use.json` |
| 0021 | error | solution_generation | react_tool_use | 3.723 | `raw_json/0021_input_solution_generation_react_tool_use.json` | `raw_json/0021_output_solution_generation_react_tool_use.json` |
| 0022 | ok | solution_generation | llm_retry_correction | 3.517 | `raw_json/0022_input_solution_generation_llm_retry_correction.json` | `raw_json/0022_output_solution_generation_llm_retry_correction.json` |
| 0023 | ok | solution_generation | react_tool_use | 3.503 | `raw_json/0023_input_solution_generation_react_tool_use.json` | `raw_json/0023_output_solution_generation_react_tool_use.json` |
| 0024 | ok | solution_generation | react_tool_use | 4.333 | `raw_json/0024_input_solution_generation_react_tool_use.json` | `raw_json/0024_output_solution_generation_react_tool_use.json` |
