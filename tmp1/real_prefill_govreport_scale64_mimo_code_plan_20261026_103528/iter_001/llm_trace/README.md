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
| 0000 | error | model_level | react_tool_use | 1.412 | `raw_json/0000_input_model_level_react_tool_use.json` | `raw_json/0000_output_model_level_react_tool_use.json` |
| 0001 | error | model_level | llm_retry_correction | 1.363 | `raw_json/0001_input_model_level_llm_retry_correction.json` | `raw_json/0001_output_model_level_llm_retry_correction.json` |
| 0002 | error | model_level | llm_retry_correction | 1.295 | `raw_json/0002_input_model_level_llm_retry_correction.json` | `raw_json/0002_output_model_level_llm_retry_correction.json` |
