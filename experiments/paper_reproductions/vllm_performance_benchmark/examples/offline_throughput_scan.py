"""
Offline throughput benchmark for vLLM performance profiling.

Scans a configurable matrix of (input_len, output_len) combinations,
collecting throughput, latency, and GPU memory metrics.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

import torch
import vllm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run offline throughput scan for vLLM baseline profiling."
    )
    parser.add_argument("--model", required=True, help="Local model directory path.")
    parser.add_argument("--scan-config", required=True, help="Scan matrix JSON config.")
    parser.add_argument("--output-dir", required=True, help="Run output directory.")
    parser.add_argument("--variant-name", required=True, help="Label for this variant.")
    parser.add_argument("--variant-description", default="", help="Notes about this variant.")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    parser.add_argument("--max-model-len", type=int, default=2048)
    parser.add_argument("--max-num-seqs", type=int, default=16)
    parser.add_argument("--language-model-only", action="store_true")
    prefix_group = parser.add_mutually_exclusive_group()
    prefix_group.add_argument("--enable-prefix-caching", action="store_true")
    prefix_group.add_argument("--no-enable-prefix-caching", action="store_true")
    return parser.parse_args()


def get_gpu_info() -> dict:
    """Collect GPU info via nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            return {"name": parts[0], "memory_total_mib": parts[1], "memory_free_mib": parts[2]}
    except (subprocess.TimeoutExpired, FileNotFoundError, IndexError):
        pass
    return {"name": "unknown", "memory_total_mib": "unknown", "memory_free_mib": "unknown"}


def run_single_point(
    model: str,
    input_len: int,
    output_len: int,
    num_prompts: int,
    gpu_memory_utilization: float,
    max_model_len: int,
    max_num_seqs: int,
    language_model_only: bool,
    enable_prefix_caching: bool | None,
    random_prefix_len: int = 0,
) -> dict:
    """Run vllm bench throughput for a single scan point. Returns metrics dict."""

    cmd = [
        "vllm", "bench", "throughput",
        "--model", model,
        "--dataset-name", "random",
        "--random-input-len", str(input_len),
        "--random-output-len", str(output_len),
        "--num-prompts", str(num_prompts),
        "--gpu-memory-utilization", str(gpu_memory_utilization),
        "--max-model-len", str(max_model_len),
    ]

    if random_prefix_len > 0:
        cmd.extend(["--random-prefix-len", str(random_prefix_len)])

    if enable_prefix_caching is True:
        cmd.append("--enable-prefix-caching")

    env = {}
    if language_model_only:
        env["VLLM_LANGUAGE_MODEL_ONLY"] = "1"

    started = time.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env={**__import__("os").environ, **env})
        elapsed = time.perf_counter() - started
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - started
        return {
            "input_len": input_len,
            "output_len": output_len,
            "num_prompts": num_prompts,
            "wall_seconds": elapsed,
            "success": False,
            "returncode": -1,
            "error": "subprocess timed out after 600s",
        }

    stdout = result.stdout
    stderr = result.stderr
    combined = stdout + "\n" + stderr

    metrics = {
        "input_len": input_len,
        "output_len": output_len,
        "num_prompts": num_prompts,
        "wall_seconds": elapsed,
        "success": result.returncode == 0,
        "returncode": result.returncode,
    }

    # Parse throughput line: "Throughput: X.XX requests/s, Y.YY total tokens/s, Z.ZZ output tokens/s"
    tp_match = re.search(
        r"Throughput:\s+([\d.]+)\s+requests/s,\s+([\d.]+)\s+total tokens/s,\s+([\d.]+)\s+output tokens/s",
        combined,
    )
    if tp_match:
        metrics["request_throughput"] = float(tp_match.group(1))
        metrics["total_token_throughput"] = float(tp_match.group(2))
        metrics["output_token_throughput"] = float(tp_match.group(3))

    # Parse token counts
    prompt_match = re.search(r"Total num prompt tokens:\s+(\d+)", combined)
    output_match = re.search(r"Total num output tokens:\s+(\d+)", combined)
    if prompt_match:
        metrics["total_prompt_tokens"] = int(prompt_match.group(1))
    if output_match:
        metrics["total_output_tokens"] = int(output_match.group(1))

    # Parse KV cache info
    kv_match = re.search(r"GPU KV cache size:\s+([\d,]+)\s+tokens", combined)
    kv_usage_match = re.search(r"GPU KV cache usage:\s+([\d.]+)%", combined)
    kv_mem_match = re.search(r"Available KV cache memory:\s+([\d.]+)\s+GiB", combined)
    prefix_hit_match = re.search(r"Prefix cache hit rate:\s+([\d.]+)%", combined)
    max_conc_match = re.search(r"Maximum concurrency for.*?:\s+([\d.]+)x", combined)

    if kv_match:
        metrics["kv_cache_tokens"] = int(kv_match.group(1).replace(",", ""))
    if kv_usage_match:
        metrics["kv_cache_usage_pct"] = float(kv_usage_match.group(1))
    if kv_mem_match:
        metrics["kv_cache_memory_gib"] = float(kv_mem_match.group(1))
    if prefix_hit_match:
        metrics["prefix_cache_hit_rate_pct"] = float(prefix_hit_match.group(1))
    if max_conc_match:
        metrics["max_theoretical_concurrency"] = float(max_conc_match.group(1))

    # Parse model loading time
    load_match = re.search(r"Model loading took\s+([\d.]+)\s+GiB memory and\s+([\d.]+)\s+seconds", combined)
    if load_match:
        metrics["model_memory_gib"] = float(load_match.group(1))
        metrics["model_load_seconds"] = float(load_match.group(2))

    if result.returncode != 0:
        metrics["stderr_tail"] = stderr[-500:] if stderr else ""

    return metrics


def main() -> None:
    args = parse_args()
    model_path = Path(args.model).expanduser().resolve()
    config_path = Path(args.scan_config).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(config_path.read_text(encoding="utf-8"))

    # Resolve scan_config reference if the config is a suite-level file
    if "scan_config" in config and not config.get("scan_points"):
        scan_config_rel = config["scan_config"]
        scan_config_path = (config_path.parent / scan_config_rel).resolve()
        print(f"Resolving scan points from: {scan_config_path}")
        if not scan_config_path.exists():
            print(f"Scan config not found: {scan_config_path}")
            return
        scan_config = json.loads(scan_config_path.read_text(encoding="utf-8"))
        # Merge scan_points into the main config for storage
        config["scan_points"] = scan_config.get("scan_points", [])
        if "random_prefix_len" in scan_config:
            config["random_prefix_len"] = scan_config["random_prefix_len"]

    scan_points = config.get("scan_points", [])

    if not scan_points:
        print("No scan_points defined in config. Exiting.")
        return

    # Save configs and env
    shutil.copy2(config_path, output_dir / "config.json")
    gpu_info = get_gpu_info()
    env_data = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "vllm": vllm.__version__,
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "model": str(model_path),
        "gpu": gpu_info,
        "variant_name": args.variant_name,
        "variant_description": args.variant_description,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "max_model_len": args.max_model_len,
        "max_num_seqs": args.max_num_seqs,
        "language_model_only": args.language_model_only,
        "enable_prefix_caching": args.enable_prefix_caching,
        "disable_prefix_caching": args.no_enable_prefix_caching,
    }
    (output_dir / "env.json").write_text(
        json.dumps(env_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Determine prefix caching flag
    enable_pc: bool | None = None
    if args.enable_prefix_caching:
        enable_pc = True
    elif args.no_enable_prefix_caching:
        enable_pc = False

    # Use prefix_len from config if present, else 0
    prefix_len = config.get("random_prefix_len", 0)

    # Run the scan
    all_metrics = []
    raw_logs = []

    for i, sp in enumerate(scan_points):
        input_len = sp["input_len"]
        output_len = sp["output_len"]
        num_prompts = sp.get("num_prompts", 100)
        point_prefix_len = sp.get("prefix_len", prefix_len)

        print(f"\n[{i+1}/{len(scan_points)}] i={input_len}, o={output_len}, n={num_prompts}")

        try:
            point_metrics = run_single_point(
                model=str(model_path),
                input_len=input_len,
                output_len=output_len,
                num_prompts=num_prompts,
                gpu_memory_utilization=args.gpu_memory_utilization,
                max_model_len=args.max_model_len,
                max_num_seqs=args.max_num_seqs,
                language_model_only=args.language_model_only,
                enable_prefix_caching=enable_pc,
                random_prefix_len=point_prefix_len,
            )
        except Exception as exc:
            point_metrics = {
                "input_len": input_len,
                "output_len": output_len,
                "num_prompts": num_prompts,
                "success": False,
                "error": str(exc),
            }
        all_metrics.append(point_metrics)
        raw_logs.append(point_metrics)
        print(f"  -> {point_metrics.get('request_throughput', 'FAIL'):.2f} req/s"
              if isinstance(point_metrics.get('request_throughput'), float)
              else f"  -> FAILED (rc={point_metrics.get('returncode')})")

    # Save per-point metrics
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(all_metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # Build summary
    successful = [m for m in all_metrics if m.get("success")]
    lines = [
        f"# {config.get('name', 'throughput_scan')}",
        "",
        f"Variant: **{args.variant_name}**",
        f"Description: {args.variant_description}",
        f"Model: {model_path}",
        f"GPU: {gpu_info.get('name', 'unknown')}",
        "",
        "## Scan Results",
        "",
        "| Input | Output | N | Req/s | Total tok/s | Out tok/s | KV Usage% | Prefix Hit% |",
        "|:-----:|:------:|:--:|:-----:|:----------:|:---------:|:---------:|:-----------:|",
    ]

    for m in all_metrics:
        if m.get("success"):
            lines.append(
                f"| {m['input_len']} | {m['output_len']} | {m['num_prompts']} | "
                f"{m.get('request_throughput', 0):.2f} | "
                f"{m.get('total_token_throughput', 0):.2f} | "
                f"{m.get('output_token_throughput', 0):.2f} | "
                f"{m.get('kv_cache_usage_pct', 'N/A')} | "
                f"{m.get('prefix_cache_hit_rate_pct', 'N/A')} |"
            )
        else:
            lines.append(
                f"| {m['input_len']} | {m['output_len']} | {m['num_prompts']} | "
                f"FAILED (rc={m.get('returncode')}) | - | - | - | - |"
            )

    # Add aggregate summary
    if successful:
        avg_req = sum(m.get("request_throughput", 0) for m in successful) / len(successful)
        avg_tot_tok = sum(m.get("total_token_throughput", 0) for m in successful) / len(successful)
        avg_out_tok = sum(m.get("output_token_throughput", 0) for m in successful) / len(successful)
        max_kv = max((m.get("kv_cache_usage_pct", 0) for m in successful), default=0)
        kv_sizes = [m.get("kv_cache_tokens", 0) for m in successful if m.get("kv_cache_tokens")]
        kv_mem = [m.get("kv_cache_memory_gib", 0) for m in successful if m.get("kv_cache_memory_gib")]

        lines += [
            "",
            "## Aggregate Summary",
            "",
            f"- Successful points: {len(successful)}/{len(all_metrics)}",
            f"- Avg request throughput: {avg_req:.2f} req/s",
            f"- Avg total token throughput: {avg_tot_tok:.2f} tok/s",
            f"- Avg output token throughput: {avg_out_tok:.2f} tok/s",
            f"- Peak KV cache usage: {max_kv:.1f}%",
        ]
        if kv_sizes:
            lines.append(f"- KV cache capacity: {max(kv_sizes)} tokens ({max(kv_mem):.2f} GiB)" if kv_mem else f"- KV cache capacity: {max(kv_sizes)} tokens")
        if any(m.get("prefix_cache_hit_rate_pct", 0) > 0 for m in successful):
            hits = [m.get("prefix_cache_hit_rate_pct", 0) for m in successful]
            lines.append(f"- Prefix cache hit rate range: {min(hits):.1f}% - {max(hits):.1f}%")
        else:
            lines.append("- Prefix cache hit rate: 0.0% (no shared prefixes in random dataset)")
    else:
        lines += ["", "## WARNING: All scan points failed.", ""]

    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Print summary to stdout
    print("\n" + "=" * 60)
    print(f"Run complete: {len(successful)}/{len(all_metrics)} points succeeded")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
