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
| 0000 | ok | model_level | react_tool_use | 2.082 | `raw_json/0000_input_model_level_react_tool_use.json` | `raw_json/0000_output_model_level_react_tool_use.json` |
| 0001 | ok | model_level | react_tool_use | 5.166 | `raw_json/0001_input_model_level_react_tool_use.json` | `raw_json/0001_output_model_level_react_tool_use.json` |
| 0002 | ok | model_level | react_tool_use | 2.087 | `raw_json/0002_input_model_level_react_tool_use.json` | `raw_json/0002_output_model_level_react_tool_use.json` |
| 0003 | ok | model_level | react_tool_use | 2.923 | `raw_json/0003_input_model_level_react_tool_use.json` | `raw_json/0003_output_model_level_react_tool_use.json` |
| 0004 | ok | model_level | react_tool_use | 2.936 | `raw_json/0004_input_model_level_react_tool_use.json` | `raw_json/0004_output_model_level_react_tool_use.json` |
| 0005 | ok | model_level | react_tool_use | 9.369 | `raw_json/0005_input_model_level_react_tool_use.json` | `raw_json/0005_output_model_level_react_tool_use.json` |
| 0006 | ok | model_level | react_tool_use | 5.916 | `raw_json/0006_input_model_level_react_tool_use.json` | `raw_json/0006_output_model_level_react_tool_use.json` |
| 0007 | ok | model_level | react_tool_use | 4.537 | `raw_json/0007_input_model_level_react_tool_use.json` | `raw_json/0007_output_model_level_react_tool_use.json` |
| 0008 | ok | model_level | react_tool_use | 8.723 | `raw_json/0008_input_model_level_react_tool_use.json` | `raw_json/0008_output_model_level_react_tool_use.json` |
| 0009 | ok | layer_level | react_tool_use | 2.106 | `raw_json/0009_input_layer_level_react_tool_use.json` | `raw_json/0009_output_layer_level_react_tool_use.json` |
| 0010 | ok | layer_level | react_tool_use | 4.473 | `raw_json/0010_input_layer_level_react_tool_use.json` | `raw_json/0010_output_layer_level_react_tool_use.json` |
| 0011 | ok | layer_level | react_tool_use | 28.203 | `raw_json/0011_input_layer_level_react_tool_use.json` | `raw_json/0011_output_layer_level_react_tool_use.json` |
| 0012 | ok | solution_generation | react_tool_use | 3.805 | `raw_json/0012_input_solution_generation_react_tool_use.json` | `raw_json/0012_output_solution_generation_react_tool_use.json` |
| 0013 | ok | solution_generation | react_tool_use | 3.532 | `raw_json/0013_input_solution_generation_react_tool_use.json` | `raw_json/0013_output_solution_generation_react_tool_use.json` |
| 0014 | ok | solution_generation | react_tool_use | 3.581 | `raw_json/0014_input_solution_generation_react_tool_use.json` | `raw_json/0014_output_solution_generation_react_tool_use.json` |
| 0015 | ok | solution_generation | react_tool_use | 6.466 | `raw_json/0015_input_solution_generation_react_tool_use.json` | `raw_json/0015_output_solution_generation_react_tool_use.json` |
| 0016 | ok | solution_generation | react_tool_use | 2.696 | `raw_json/0016_input_solution_generation_react_tool_use.json` | `raw_json/0016_output_solution_generation_react_tool_use.json` |
| 0017 | ok | solution_generation | react_tool_use | 4.040 | `raw_json/0017_input_solution_generation_react_tool_use.json` | `raw_json/0017_output_solution_generation_react_tool_use.json` |
| 0018 | ok | solution_generation | react_tool_use | 4.783 | `raw_json/0018_input_solution_generation_react_tool_use.json` | `raw_json/0018_output_solution_generation_react_tool_use.json` |
| 0019 | ok | solution_generation | react_tool_use | 3.459 | `raw_json/0019_input_solution_generation_react_tool_use.json` | `raw_json/0019_output_solution_generation_react_tool_use.json` |
| 0020 | ok | solution_generation | react_tool_use | 9.435 | `raw_json/0020_input_solution_generation_react_tool_use.json` | `raw_json/0020_output_solution_generation_react_tool_use.json` |
