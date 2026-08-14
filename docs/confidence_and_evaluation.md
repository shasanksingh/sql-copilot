# Confidence And Evaluation

Confidence is evidence-based. The system does not use model self-reported confidence as the final answer.

## Signals

The response tracks:

- intent confidence
- entity confidence
- column confidence
- join confidence
- aggregation confidence
- semantic coverage confidence
- validator confidence
- planner confidence
- model confidence
- system confidence

The model confidence is advisory. SQL validity and planner/schema alignment are deterministic gates.

## Bands

Defaults:

| Range | Band | Behavior |
| --- | --- | --- |
| `90-100` | `HIGH` | Return normally |
| `75-89` | `MEDIUM` | Return with visible confidence context |
| `0-74` | `LOW` | Ask for clarification or refuse unsafe output |

Configure bands with `CONFIDENCE_LOW_THRESHOLD` and `CONFIDENCE_HIGH_THRESHOLD`. Configure component weights with `CONFIDENCE_WEIGHTS_JSON`, for example `{"intent":0.25,"entity":0.2,"column":0.15,"join":0.15,"aggregation":0.1,"semantic":0.1,"validation":0.05}`.

## Benchmark

Run the 120-case enterprise benchmark:

```powershell
python tools\enterprise_query_benchmark.py
```

Run the configured NVIDIA provider only when credentials are intentionally present:

```powershell
python tools\enterprise_query_benchmark.py --with-provider
```

The script writes:

- `reports/enterprise_query_planning_before_after.md`
- `reports/nvidia_gpt_oss_20b_evaluation.md`

If NVIDIA is not configured, the report explicitly says the provider run was not executed. It does not fabricate accuracy, latency, token, fallback, or hallucination metrics.

## Ablations

Experimental runs can set `USE_SCHEMA_GRAPH`, `USE_BUSINESS_LOGIC`, `USE_HYBRID_RETRIEVAL`, `USE_LLM_PLANNER`, `USE_LLM_CRITIC`, and `USE_VALIDATOR`. Production keeps validator safety locked on even if `USE_VALIDATOR=false` is present.
