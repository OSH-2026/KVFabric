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

payload=$(fetch_metrics)

kv_cache_usage=$(avg_gauge "$payload" "vllm:kv_cache_usage_perc")
prefix_queries=$(sum_metric "$payload" "vllm:prefix_cache_queries_total")
prefix_hits=$(sum_metric "$payload" "vllm:prefix_cache_hits_total")
prefix_hit_rate=$(ratio_or_zero "$prefix_hits" "$prefix_queries")

prompt_tokens=$(sum_metric "$payload" "vllm:prompt_tokens_total")
prompt_tokens_cached=$(sum_metric "$payload" "vllm:prompt_tokens_cached_total")
prompt_tokens_recomputed=$(sum_metric "$payload" "vllm:prompt_tokens_recomputed_total")
generation_tokens=$(sum_metric "$payload" "vllm:generation_tokens_total")
request_success=$(sum_metric "$payload" "vllm:request_success_total")
recompute_ratio=$(ratio_or_zero "$prompt_tokens_recomputed" "$prompt_tokens")
memory_headroom_proxy=$(awk -v usage="$kv_cache_usage" 'BEGIN { print 1 - usage }')

requests_running=$(avg_gauge "$payload" "vllm:num_requests_running")
requests_waiting=$(avg_gauge "$payload" "vllm:num_requests_waiting")

if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    awk \
        -v endpoint="$METRICS_URL" \
        -v requests_running="$requests_running" \
        -v requests_waiting="$requests_waiting" \
        -v kv_cache_usage="$kv_cache_usage" \
        -v memory_headroom_proxy="$memory_headroom_proxy" \
        -v prefix_queries="$prefix_queries" \
        -v prefix_hits="$prefix_hits" \
        -v prefix_hit_rate="$prefix_hit_rate" \
        -v prompt_tokens="$prompt_tokens" \
        -v prompt_tokens_cached="$prompt_tokens_cached" \
        -v prompt_tokens_recomputed="$prompt_tokens_recomputed" \
        -v generation_tokens="$generation_tokens" \
        -v request_success="$request_success" \
        -v recompute_ratio="$recompute_ratio" \
        'BEGIN {
            printf "{\n"
            printf "  \"endpoint\": \"%s\",\n", endpoint
            printf "  \"num_requests_running_avg\": %s,\n", requests_running
            printf "  \"num_requests_waiting_avg\": %s,\n", requests_waiting
            printf "  \"kv_cache_usage_perc_avg\": %s,\n", kv_cache_usage
            printf "  \"memory_headroom_proxy\": %s,\n", memory_headroom_proxy
            printf "  \"prefix_cache_queries\": %s,\n", prefix_queries
            printf "  \"prefix_cache_hits\": %s,\n", prefix_hits
            printf "  \"prefix_token_hit_rate\": %s,\n", prefix_hit_rate
            printf "  \"prompt_tokens_total\": %s,\n", prompt_tokens
            printf "  \"prompt_tokens_cached\": %s,\n", prompt_tokens_cached
            printf "  \"prompt_tokens_recomputed\": %s,\n", prompt_tokens_recomputed
            printf "  \"generation_tokens_total\": %s,\n", generation_tokens
            printf "  \"request_success_total\": %s,\n", request_success
            printf "  \"saved_prefill_tokens_proxy\": %s,\n", prompt_tokens_cached
            printf "  \"recompute_ratio_proxy\": %s\n", recompute_ratio
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

[前缀缓存]
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

cat <<'EOF'

[报告指标覆盖情况]
请求命中率                    当前 /metrics 尚不可直接获得
前缀 token 命中率             上方可获得
block 复用率                  当前 /metrics 尚不可直接获得
节省的 prefill tokens         上方有代理值 prompt_tokens_cached
TTFT / p95 TTFT               上方有平均值；p95 需要 Prometheus histogram_quantile 或离线解析 bucket
TPOT                          上方有代理值 request_time_per_output_token_seconds
E2E latency                   上方有平均值；分位数需要解析 histogram bucket
吞吐                          可用 Prometheus rate() 处理 prompt_tokens/generation_tokens/request_success
驱逐后悔率                    当前 /metrics 尚不可直接获得
重算比例                      上方有代理值 prompt_tokens_recomputed / prompt_tokens
有效 block 利用率             当前 /metrics 尚不可直接获得
显存余量                      上方有代理值 1 - kv_cache_usage_perc
lookup / metadata 开销        当前 /metrics 尚不可直接获得
EOF
