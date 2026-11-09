# Timing Summary

Pipeline timings are local wall-clock durations. LLM API timings are measured per request and include network latency plus provider-side generation time.

## Pipeline By Component

| component | calls | total_s | avg_s | max_s |
|---|---:|---:|---:|---:|
| agent:layer_level | 5 | 201.602 | 40.320 | 49.117 |
| agent:model_level | 5 | 235.586 | 47.117 | 65.175 |
| agent:solution_generation | 5 | 230.561 | 46.112 | 69.408 |
| evaluator | 6 | 944.256 | 157.376 | 270.787 |
| pipeline | 5 | 0.001 | 0.000 | 0.000 |
| rag | 5 | 0.584 | 0.117 | 0.131 |
| trace | 5 | 0.467 | 0.093 | 0.411 |

## LLM API By Agent

| agent | calls | total_s | avg_s | max_s | prompt_tokens | cached_prompt_tokens | completion_tokens | reasoning_tokens | total_tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| layer_level | 24 | 199.521 | 8.313 | 39.368 | 225995 | 102400 | 18510 | N/A | 244505 |
| model_level | 44 | 233.097 | 5.298 | 40.488 | 552319 | 260352 | 15648 | N/A | 567967 |
| solution_generation | 52 | 226.945 | 4.364 | 11.004 | 1049591 | 633856 | 20360 | N/A | 1069951 |

## LLM API By Run

| run_dir | calls | total_s | avg_s | max_s | prompt_tokens | cached_prompt_tokens | completion_tokens | reasoning_tokens | total_tokens | statuses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| iter_001 | 25 | 130.258 | 5.210 | 29.937 | 297863 | 162304 | 10882 | N/A | 308745 | {'ok': 23, 'error': 2} |
| iter_002 | 22 | 132.179 | 6.008 | 39.368 | 281361 | 130816 | 9269 | N/A | 290630 | {'ok': 21, 'error': 1} |
| iter_003 | 25 | 127.055 | 5.082 | 12.235 | 418720 | 229376 | 12138 | N/A | 430858 | {'ok': 25} |
| iter_004 | 21 | 120.317 | 5.729 | 28.203 | 346720 | 194816 | 10429 | N/A | 357149 | {'ok': 21} |
| iter_005 | 27 | 149.754 | 5.546 | 40.488 | 483241 | 279296 | 11800 | N/A | 495041 | {'ok': 26, 'error': 1} |

## Pipeline Events

| iter | component | action | duration_s |
|---:|---|---|---:|
| 0 | evaluator | run initial baseline evaluation | 79.844 |
| 1 | agent:model_level | analyze model-level bottlenecks | 49.942 |
| 1 | agent:layer_level | diagnose candidate layers | 49.117 |
| 1 | agent:solution_generation | retrieve history and propose hardware update | 32.730 |
| 1 | trace | write agent trace and LLM trace index | 0.017 |
| 1 | pipeline | validate hardware proposal uniqueness | 0.000 |
| 1 | evaluator | evaluate proposed hardware | 200.361 |
| 1 | rag | commit evaluated transition to history database | 0.130 |
| 2 | agent:model_level | analyze model-level bottlenecks | 45.177 |
| 2 | agent:layer_level | diagnose candidate layers | 48.132 |
| 2 | agent:solution_generation | retrieve history and propose hardware update | 40.534 |
| 2 | trace | write agent trace and LLM trace index | 0.011 |
| 2 | pipeline | validate hardware proposal uniqueness | 0.000 |
| 2 | evaluator | evaluate proposed hardware | 81.638 |
| 2 | rag | commit evaluated transition to history database | 0.100 |
| 3 | agent:model_level | analyze model-level bottlenecks | 31.045 |
| 3 | agent:layer_level | diagnose candidate layers | 28.475 |
| 3 | agent:solution_generation | retrieve history and propose hardware update | 69.408 |
| 3 | trace | write agent trace and LLM trace index | 0.011 |
| 3 | pipeline | validate hardware proposal uniqueness | 0.000 |
| 3 | evaluator | evaluate proposed hardware | 166.079 |
| 3 | rag | commit evaluated transition to history database | 0.102 |
| 4 | agent:model_level | analyze model-level bottlenecks | 44.246 |
| 4 | agent:layer_level | diagnose candidate layers | 35.205 |
| 4 | agent:solution_generation | retrieve history and propose hardware update | 42.714 |
| 4 | trace | write agent trace and LLM trace index | 0.411 |
| 4 | pipeline | validate hardware proposal uniqueness | 0.000 |
| 4 | evaluator | evaluate proposed hardware | 145.547 |
| 4 | rag | commit evaluated transition to history database | 0.122 |
| 5 | agent:model_level | analyze model-level bottlenecks | 65.175 |
| 5 | agent:layer_level | diagnose candidate layers | 40.672 |
| 5 | agent:solution_generation | retrieve history and propose hardware update | 45.176 |
| 5 | trace | write agent trace and LLM trace index | 0.015 |
| 5 | pipeline | validate hardware proposal uniqueness | 0.000 |
| 5 | evaluator | evaluate proposed hardware | 270.787 |
| 5 | rag | commit evaluated transition to history database | 0.131 |
