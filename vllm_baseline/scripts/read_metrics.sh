#!/usr/bin/env bash

set -euo pipefail

OUTPUT_FORMAT="text"
METRICS_URL="http://127.0.0.1:8000/metrics"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)
            OUTPUT_FORMAT="json"
            shift
            ;;
        --text)
            OUTPUT_FORMAT="text"
            shift
            ;;
        --url)
            METRICS_URL="$2"
            shift 2
            ;;
        http://*|https://*)
            METRICS_URL="$1"
            shift
            ;;
        *)
            echo "用法: $0 [--text|--json] [--url METRICS_URL]" >&2
            exit 1
            ;;
    esac
done

fetch_metrics() {
    curl -fsS "$METRICS_URL"
}

sum_metric() {
    local payload="$1"
    local metric_name="$2"

    awk -v metric_name="$metric_name" '
        $0 !~ /^#/ && $1 ~ ("^" metric_name "(\\{|$)") { sum += $NF; seen = 1 }
        END {
            if (seen) {
                print sum + 0
            } else {
                print 0
            }
        }
    ' <<< "$payload"
}

avg_gauge() {
    local payload="$1"
    local metric_name="$2"

    awk -v metric_name="$metric_name" '
        $0 !~ /^#/ && $1 ~ ("^" metric_name "(\\{|$)") { sum += $NF; count += 1 }
        END {
            if (count > 0) {
                print sum / count
            } else {
                print 0
            }
        }
    ' <<< "$payload"
}

ratio_or_zero() {
    local numerator="$1"
    local denominator="$2"
    awk -v n="$numerator" -v d="$denominator" 'BEGIN { if (d > 0) print n / d; else print 0 }'
}

print_hist_summary() {
    local payload="$1"
    local metric_name="$2"
    local label="$3"
    local count
    local sum
    local avg

    count=$(sum_metric "$payload" "${metric_name}_count")
    sum=$(sum_metric "$payload" "${metric_name}_sum")
    avg=$(ratio_or_zero "$sum" "$count")
    printf '%-30s samples=%-10s avg=%s\n' "$label" "$count" "$avg"
}

hist_count() {
    local payload="$1"
    local metric_name="$2"
    sum_metric "$payload" "${metric_name}_count"
}

hist_avg() {
    local payload="$1"
    local metric_name="$2"
    local count
    local sum
    count=$(sum_metric "$payload" "${metric_name}_count")
    sum=$(sum_metric "$payload" "${metric_name}_sum")
    ratio_or_zero "$sum" "$count"
}

payload=$(fetch_metrics)

kv_cache_usage=$(avg_gauge "$payload" "vllm:kv_cache_usage_perc")
kv_block_free=$(avg_gauge "$payload" "vllm:kv_block_free")
kv_block_total=$(avg_gauge "$payload" "vllm:kv_block_total")
kv_block_active=$(avg_gauge "$payload" "vllm:kv_block_active")
kv_block_peak_active=$(avg_gauge "$payload" "vllm:kv_block_peak_active")
kv_block_cached_entries=$(avg_gauge "$payload" "vllm:kv_block_cached_entries")
kv_block_active_ratio=$(ratio_or_zero "$kv_block_active" "$kv_block_total")
kv_block_cached_entry_ratio=$(ratio_or_zero "$kv_block_cached_entries" "$kv_block_total")

prefix_requests=$(sum_metric "$payload" "vllm:prefix_cache_requests_total")
prefix_request_hits=$(sum_metric "$payload" "vllm:prefix_cache_request_hits_total")
request_hit_rate=$(ratio_or_zero "$prefix_request_hits" "$prefix_requests")
prefix_queries=$(sum_metric "$payload" "vllm:prefix_cache_queries_total")
prefix_hits=$(sum_metric "$payload" "vllm:prefix_cache_hits_total")
prefix_hit_rate=$(ratio_or_zero "$prefix_hits" "$prefix_queries")

kv_block_lookup_queries=$(sum_metric "$payload" "vllm:kv_block_lookup_queries_total")
kv_block_lookup_hits=$(sum_metric "$payload" "vllm:kv_block_lookup_hits_total")
kv_block_lookup_hit_rate=$(ratio_or_zero "$kv_block_lookup_hits" "$kv_block_lookup_queries")
kv_block_allocations=$(sum_metric "$payload" "vllm:kv_block_allocations_total")
kv_block_cached=$(sum_metric "$payload" "vllm:kv_block_cached_total")
kv_block_evictions_total=$(sum_metric "$payload" "vllm:kv_block_evictions_total")
kv_block_reuse_per_allocation=$(ratio_or_zero "$kv_block_lookup_hits" "$kv_block_allocations")

prompt_tokens=$(sum_metric "$payload" "vllm:prompt_tokens_total")
prompt_tokens_cached=$(sum_metric "$payload" "vllm:prompt_tokens_cached_total")
prompt_tokens_recomputed=$(sum_metric "$payload" "vllm:prompt_tokens_recomputed_total")
generation_tokens=$(sum_metric "$payload" "vllm:generation_tokens_total")
request_success=$(sum_metric "$payload" "vllm:request_success_total")
recompute_ratio=$(ratio_or_zero "$prompt_tokens_recomputed" "$prompt_tokens")
memory_headroom_proxy=$(awk -v usage="$kv_cache_usage" 'BEGIN { print 1 - usage }')

requests_running=$(avg_gauge "$payload" "vllm:num_requests_running")
requests_waiting=$(avg_gauge "$payload" "vllm:num_requests_waiting")

ttft_count=$(hist_count "$payload" "vllm:time_to_first_token_seconds")
ttft_avg=$(hist_avg "$payload" "vllm:time_to_first_token_seconds")
tpot_count=$(hist_count "$payload" "vllm:request_time_per_output_token_seconds")
tpot_avg=$(hist_avg "$payload" "vllm:request_time_per_output_token_seconds")
e2e_latency_count=$(hist_count "$payload" "vllm:e2e_request_latency_seconds")
e2e_latency_avg=$(hist_avg "$payload" "vllm:e2e_request_latency_seconds")
prefill_time_count=$(hist_count "$payload" "vllm:request_prefill_time_seconds")
prefill_time_avg=$(hist_avg "$payload" "vllm:request_prefill_time_seconds")
decode_time_count=$(hist_count "$payload" "vllm:request_decode_time_seconds")
decode_time_avg=$(hist_avg "$payload" "vllm:request_decode_time_seconds")
kv_block_lifetime_count=$(hist_count "$payload" "vllm:kv_block_lifetime_seconds")
kv_block_lifetime_avg=$(hist_avg "$payload" "vllm:kv_block_lifetime_seconds")
kv_block_idle_before_evict_count=$(hist_count "$payload" "vllm:kv_block_idle_before_evict_seconds")
kv_block_idle_before_evict_avg=$(hist_avg "$payload" "vllm:kv_block_idle_before_evict_seconds")
kv_block_recompute_cost_count=$(hist_count "$payload" "vllm:kv_block_recompute_cost_tokens")
kv_block_recompute_cost_avg=$(hist_avg "$payload" "vllm:kv_block_recompute_cost_tokens")
kv_block_branch_factor_count=$(hist_count "$payload" "vllm:kv_block_branch_factor")
kv_block_branch_factor_avg=$(hist_avg "$payload" "vllm:kv_block_branch_factor")
kv_block_lookup_time_count=$(hist_count "$payload" "vllm:kv_block_lookup_time_seconds")
kv_block_lookup_time_avg=$(hist_avg "$payload" "vllm:kv_block_lookup_time_seconds")
kv_metadata_update_time_count=$(hist_count "$payload" "vllm:kv_metadata_update_time_seconds")
kv_metadata_update_time_avg=$(hist_avg "$payload" "vllm:kv_metadata_update_time_seconds")
kv_block_regrets=$(sum_metric "$payload" "vllm:kv_block_eviction_regrets_total")
kv_block_regret_rate=$(ratio_or_zero "$kv_block_regrets" "$kv_block_evictions_total")

if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    awk \
        -v endpoint="$METRICS_URL" \
        -v requests_running="$requests_running" \
        -v requests_waiting="$requests_waiting" \
        -v kv_cache_usage="$kv_cache_usage" \
        -v kv_block_free="$kv_block_free" \
        -v kv_block_total="$kv_block_total" \
        -v kv_block_active="$kv_block_active" \
        -v kv_block_peak_active="$kv_block_peak_active" \
        -v kv_block_cached_entries="$kv_block_cached_entries" \
        -v kv_block_active_ratio="$kv_block_active_ratio" \
        -v kv_block_cached_entry_ratio="$kv_block_cached_entry_ratio" \
        -v memory_headroom_proxy="$memory_headroom_proxy" \
        -v prefix_requests="$prefix_requests" \
        -v prefix_request_hits="$prefix_request_hits" \
        -v request_hit_rate="$request_hit_rate" \
        -v prefix_queries="$prefix_queries" \
        -v prefix_hits="$prefix_hits" \
        -v prefix_hit_rate="$prefix_hit_rate" \
        -v kv_block_lookup_queries="$kv_block_lookup_queries" \
        -v kv_block_lookup_hits="$kv_block_lookup_hits" \
        -v kv_block_lookup_hit_rate="$kv_block_lookup_hit_rate" \
        -v kv_block_allocations="$kv_block_allocations" \
        -v kv_block_cached="$kv_block_cached" \
        -v kv_block_evictions_total="$kv_block_evictions_total" \
        -v kv_block_reuse_per_allocation="$kv_block_reuse_per_allocation" \
        -v prompt_tokens="$prompt_tokens" \
        -v prompt_tokens_cached="$prompt_tokens_cached" \
        -v prompt_tokens_recomputed="$prompt_tokens_recomputed" \
        -v generation_tokens="$generation_tokens" \
        -v request_success="$request_success" \
        -v recompute_ratio="$recompute_ratio" \
        -v ttft_count="$ttft_count" \
        -v ttft_avg="$ttft_avg" \
        -v tpot_count="$tpot_count" \
        -v tpot_avg="$tpot_avg" \
        -v e2e_latency_count="$e2e_latency_count" \
        -v e2e_latency_avg="$e2e_latency_avg" \
        -v prefill_time_count="$prefill_time_count" \
        -v prefill_time_avg="$prefill_time_avg" \
        -v decode_time_count="$decode_time_count" \
        -v decode_time_avg="$decode_time_avg" \
        -v kv_block_lifetime_count="$kv_block_lifetime_count" \
        -v kv_block_lifetime_avg="$kv_block_lifetime_avg" \
        -v kv_block_idle_before_evict_count="$kv_block_idle_before_evict_count" \
        -v kv_block_idle_before_evict_avg="$kv_block_idle_before_evict_avg" \
        -v kv_block_recompute_cost_count="$kv_block_recompute_cost_count" \
        -v kv_block_recompute_cost_avg="$kv_block_recompute_cost_avg" \
        -v kv_block_branch_factor_count="$kv_block_branch_factor_count" \
        -v kv_block_branch_factor_avg="$kv_block_branch_factor_avg" \
        -v kv_block_lookup_time_count="$kv_block_lookup_time_count" \
        -v kv_block_lookup_time_avg="$kv_block_lookup_time_avg" \
        -v kv_metadata_update_time_count="$kv_metadata_update_time_count" \
        -v kv_metadata_update_time_avg="$kv_metadata_update_time_avg" \
        -v kv_block_regrets="$kv_block_regrets" \
        -v kv_block_regret_rate="$kv_block_regret_rate" \
        'BEGIN {
            printf "{\n"
            printf "  \"endpoint\": \"%s\",\n", endpoint
            printf "  \"num_requests_running_avg\": %s,\n", requests_running
            printf "  \"num_requests_waiting_avg\": %s,\n", requests_waiting
            printf "  \"kv_cache_usage_perc_avg\": %s,\n", kv_cache_usage
            printf "  \"kv_block_free_avg\": %s,\n", kv_block_free
            printf "  \"kv_block_total_avg\": %s,\n", kv_block_total
            printf "  \"kv_block_active_avg\": %s,\n", kv_block_active
            printf "  \"kv_block_peak_active\": %s,\n", kv_block_peak_active
            printf "  \"kv_block_cached_entries_avg\": %s,\n", kv_block_cached_entries
            printf "  \"kv_block_active_ratio\": %s,\n", kv_block_active_ratio
            printf "  \"kv_block_cached_entry_ratio\": %s,\n", kv_block_cached_entry_ratio
            printf "  \"memory_headroom_proxy\": %s,\n", memory_headroom_proxy
            printf "  \"prefix_cache_requests\": %s,\n", prefix_requests
            printf "  \"prefix_cache_request_hits\": %s,\n", prefix_request_hits
            printf "  \"request_hit_rate\": %s,\n", request_hit_rate
            printf "  \"prefix_cache_queries\": %s,\n", prefix_queries
            printf "  \"prefix_cache_hits\": %s,\n", prefix_hits
            printf "  \"prefix_token_hit_rate\": %s,\n", prefix_hit_rate
            printf "  \"kv_block_lookup_queries\": %s,\n", kv_block_lookup_queries
            printf "  \"kv_block_lookup_hits\": %s,\n", kv_block_lookup_hits
            printf "  \"kv_block_lookup_hit_rate\": %s,\n", kv_block_lookup_hit_rate
            printf "  \"kv_block_allocations\": %s,\n", kv_block_allocations
            printf "  \"kv_block_cached\": %s,\n", kv_block_cached
            printf "  \"kv_block_evictions_total\": %s,\n", kv_block_evictions_total
            printf "  \"kv_block_reuse_per_allocation_proxy\": %s,\n", kv_block_reuse_per_allocation
            printf "  \"prompt_tokens_total\": %s,\n", prompt_tokens
            printf "  \"prompt_tokens_cached\": %s,\n", prompt_tokens_cached
            printf "  \"prompt_tokens_recomputed\": %s,\n", prompt_tokens_recomputed
            printf "  \"generation_tokens_total\": %s,\n", generation_tokens
            printf "  \"request_success_total\": %s,\n", request_success
            printf "  \"saved_prefill_tokens_proxy\": %s,\n", prompt_tokens_cached
            printf "  \"recompute_ratio_proxy\": %s,\n", recompute_ratio
            printf "  \"ttft_seconds_count\": %s,\n", ttft_count
            printf "  \"ttft_seconds_avg\": %s,\n", ttft_avg
            printf "  \"tpot_seconds_count\": %s,\n", tpot_count
            printf "  \"tpot_seconds_avg\": %s,\n", tpot_avg
            printf "  \"e2e_latency_seconds_count\": %s,\n", e2e_latency_count
            printf "  \"e2e_latency_seconds_avg\": %s,\n", e2e_latency_avg
            printf "  \"prefill_time_seconds_count\": %s,\n", prefill_time_count
            printf "  \"prefill_time_seconds_avg\": %s,\n", prefill_time_avg
            printf "  \"decode_time_seconds_count\": %s,\n", decode_time_count
            printf "  \"decode_time_seconds_avg\": %s,\n", decode_time_avg
            printf "  \"kv_block_lifetime_seconds_count\": %s,\n", kv_block_lifetime_count
            printf "  \"kv_block_lifetime_seconds_avg\": %s,\n", kv_block_lifetime_avg
            printf "  \"kv_block_idle_before_evict_seconds_count\": %s,\n", kv_block_idle_before_evict_count
            printf "  \"kv_block_idle_before_evict_seconds_avg\": %s,\n", kv_block_idle_before_evict_avg
            printf "  \"kv_block_recompute_cost_tokens_count\": %s,\n", kv_block_recompute_cost_count
            printf "  \"kv_block_recompute_cost_tokens_avg\": %s,\n", kv_block_recompute_cost_avg
            printf "  \"kv_block_branch_factor_count\": %s,\n", kv_block_branch_factor_count
            printf "  \"kv_block_branch_factor_avg\": %s,\n", kv_block_branch_factor_avg
            printf "  \"kv_block_lookup_time_seconds_count\": %s,\n", kv_block_lookup_time_count
            printf "  \"kv_block_lookup_time_seconds_avg\": %s,\n", kv_block_lookup_time_avg
            printf "  \"kv_metadata_update_time_seconds_count\": %s,\n", kv_metadata_update_time_count
            printf "  \"kv_metadata_update_time_seconds_avg\": %s,\n", kv_metadata_update_time_avg
            printf "  \"kv_block_eviction_regrets\": %s,\n", kv_block_regrets
            printf "  \"kv_block_eviction_regret_rate\": %s\n", kv_block_regret_rate
            printf "}\n"
        }'
    exit 0
fi

cat <<EOF
== vLLM 指标摘要 ==
端点: $METRICS_URL

[调度器]
num_requests_running_avg        $requests_running
num_requests_waiting_avg        $requests_waiting
kv_cache_usage_perc_avg         $kv_cache_usage
memory_headroom_proxy           $memory_headroom_proxy
kv_block_free_avg               $kv_block_free
kv_block_total_avg              $kv_block_total
kv_block_active_avg             $kv_block_active
kv_block_peak_active            $kv_block_peak_active
kv_block_cached_entries_avg     $kv_block_cached_entries
kv_block_active_ratio           $kv_block_active_ratio
kv_block_cached_entry_ratio     $kv_block_cached_entry_ratio

[前缀缓存]
prefix_cache_requests           $prefix_requests
prefix_cache_request_hits       $prefix_request_hits
request_hit_rate                $request_hit_rate
prefix_cache_queries            $prefix_queries
prefix_cache_hits               $prefix_hits
prefix_token_hit_rate           $prefix_hit_rate
prompt_tokens_total             $prompt_tokens
prompt_tokens_cached            $prompt_tokens_cached
prompt_tokens_recomputed        $prompt_tokens_recomputed
generation_tokens_total         $generation_tokens
request_success_total           $request_success
saved_prefill_tokens_proxy      $prompt_tokens_cached
recompute_ratio_proxy           $recompute_ratio

[KV block 复用与分配]
kv_block_lookup_queries         $kv_block_lookup_queries
kv_block_lookup_hits            $kv_block_lookup_hits
kv_block_lookup_hit_rate        $kv_block_lookup_hit_rate
kv_block_allocations            $kv_block_allocations
kv_block_cached                 $kv_block_cached
kv_block_evictions_total        $kv_block_evictions_total
kv_block_reuse_per_allocation   $kv_block_reuse_per_allocation

[延迟直方图]
EOF

print_hist_summary "$payload" "vllm:time_to_first_token_seconds" "ttft_seconds"
print_hist_summary "$payload" "vllm:request_time_per_output_token_seconds" "time_per_output_token"
print_hist_summary "$payload" "vllm:e2e_request_latency_seconds" "e2e_latency_seconds"
print_hist_summary "$payload" "vllm:inter_token_latency_seconds" "inter_token_latency"
print_hist_summary "$payload" "vllm:request_prefill_time_seconds" "prefill_time_seconds"
print_hist_summary "$payload" "vllm:request_decode_time_seconds" "decode_time_seconds"
print_hist_summary "$payload" "vllm:request_prefill_kv_computed_tokens" "prefill_kv_computed"

cat <<EOF

[KV block 生命周期直方图]
EOF

print_hist_summary "$payload" "vllm:kv_block_lifetime_seconds" "block_lifetime"
print_hist_summary "$payload" "vllm:kv_block_idle_before_evict_seconds" "block_idle_before_evict"
print_hist_summary "$payload" "vllm:kv_block_reuse_gap_seconds" "block_reuse_gap"
print_hist_summary "$payload" "vllm:kv_block_access_count_before_evict" "block_access_count"
print_hist_summary "$payload" "vllm:kv_block_peak_ref_count" "block_peak_ref_count"
print_hist_summary "$payload" "vllm:kv_block_cache_depth_blocks" "block_cache_depth"
print_hist_summary "$payload" "vllm:kv_block_recompute_cost_tokens" "block_recompute_cost"
print_hist_summary "$payload" "vllm:kv_block_branch_factor" "block_branch_factor"
print_hist_summary "$payload" "vllm:kv_block_rebuild_gap_seconds" "block_rebuild_gap"
print_hist_summary "$payload" "vllm:kv_block_lookup_time_seconds" "block_lookup_time"
print_hist_summary "$payload" "vllm:kv_metadata_update_time_seconds" "metadata_update_time"
print_hist_summary "$payload" "vllm:kv_waiting_time_seconds" "waiting_time"
print_hist_summary "$payload" "vllm:kv_waiting_requests" "waiting_requests"

kv_block_evictions=$(sum_metric "$payload" "vllm:kv_block_evictions_total")
kv_block_eviction_samples=$(sum_metric "$payload" "vllm:kv_block_lifetime_seconds_count")
kv_block_regrets=$(sum_metric "$payload" "vllm:kv_block_eviction_regrets_total")
kv_block_regret_rate=$(ratio_or_zero "$kv_block_regrets" "$kv_block_evictions")

cat <<EOF
kv_block_evictions              $kv_block_evictions
kv_block_eviction_samples       $kv_block_eviction_samples
kv_block_eviction_regrets       $kv_block_regrets
kv_block_eviction_regret_rate   $kv_block_regret_rate
EOF

cat <<'EOF'

[报告指标覆盖情况]
请求命中率                    上方可获得 request_hit_rate
前缀 token 命中率             上方可获得
block 复用率                  上方有代理值 kv_block_lookup_hit_rate / kv_block_reuse_per_allocation
节省的 prefill tokens         上方有代理值 prompt_tokens_cached
TTFT / p95 TTFT               上方有平均值；p95 需要 Prometheus histogram_quantile 或离线解析 bucket
TPOT                          上方有代理值 request_time_per_output_token_seconds
E2E latency                   上方有平均值；分位数需要解析 histogram bucket
吞吐                          可用 Prometheus rate() 处理 prompt_tokens/generation_tokens/request_success
驱逐后悔率                    上方可获得，需启用 KV_CACHE_METRICS
重算比例                      上方有代理值 prompt_tokens_recomputed / prompt_tokens
有效 block 利用率             部分覆盖：active/free/cached/peak 水位可得，token 填充率尚不可得
显存余量                      上方有代理值 1 - kv_cache_usage_perc
lookup / metadata 开销        上方可获得，需启用 KV_CACHE_METRICS
EOF
