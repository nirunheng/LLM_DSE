workload=prefill
dataset=govreport
compute_scale=64
llm_profile=mimo_code_plan

ts=$(date +%Y%m%d_%H%M%S)
run_name="real_${workload}_${dataset}_scale${compute_scale}_${llm_profile}_${ts}"
out_dir="tmp1/${run_name}"
log_file="${out_dir}/run.log"

mkdir -p "$out_dir"

python3 main.py \
  --iterations 5 \
  --workload "$workload" \
  --dataset "$dataset" \
  --compute-scale "$compute_scale" \
  --llm-config key.json \
  --llm-profile "$llm_profile" \
  --embedding-model hashing \
  --output-dir "$out_dir" \
  2>&1 | tee "$log_file"