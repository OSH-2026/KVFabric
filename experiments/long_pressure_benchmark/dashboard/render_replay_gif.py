#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from kv_cache_replay import STATE_COLORS, STATE_ORDER, ReplayState, apply_event  # noqa: E402
from kvfabric_run_reader import read_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render KVFabric lifecycle GIF.")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--policy", default="shared_aware")
    parser.add_argument("--output", default="")
    parser.add_argument("--duration-seconds", type=float, default=20.0)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--max-events", type=int, default=200000)
    return parser.parse_args()


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def state_image(state: ReplayState, title: str):
    import numpy as np

    blocks = state.blocks
    if not blocks:
        return np.zeros((8, 8, 3), dtype=float), ["No block events"]
    block_ids = sorted(blocks)
    width = max(8, math.ceil(math.sqrt(len(block_ids))))
    height = math.ceil(len(block_ids) / width)
    image = np.zeros((height, width, 3), dtype=float)
    for idx, block_id in enumerate(block_ids):
        row, col = divmod(idx, width)
        block = blocks[block_id]
        state_name = block.display_state()
        rgb = hex_to_rgb(STATE_COLORS.get(state_name, "#94a3b8"))
        intensity = block.intensity()
        image[row, col, :] = [channel * intensity for channel in rgb]
    caption = [
        title,
        f"t={state.elapsed_seconds:.1f}s events={state.counters['events']}",
        (
            f"hit={state.prefix_hit_rate * 100:.2f}% "
            f"evicted={state.counters['evicted_blocks']} "
            f"rebuilt={state.counters['rebuilt_from_eviction']}"
        ),
    ]
    return image, caption


def render(args: argparse.Namespace) -> Path:
    import imageio.v2 as imageio
    import matplotlib.pyplot as plt
    import numpy as np

    run_root = Path(args.run_root).expanduser().resolve()
    lifecycle_path = run_root / args.policy / "kvfabric_lifecycle.jsonl"
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else run_root / "visuals" / f"replay_{args.policy}.gif"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    events, bad_lines = read_jsonl(lifecycle_path, limit=args.max_events)
    if not events:
        raise SystemExit(f"No lifecycle events found: {lifecycle_path}")

    total_frames = max(int(args.duration_seconds * args.fps), 1)
    events_per_frame = max(math.ceil(len(events) / total_frames), 1)
    state = ReplayState(bad_lines=bad_lines)
    frames = []
    for frame_no in range(total_frames):
        start = frame_no * events_per_frame
        end = min((frame_no + 1) * events_per_frame, len(events))
        for event in events[start:end]:
            apply_event(state, event)
        image, caption = state_image(state, f"{args.policy} KV cache replay")
        fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
        ax.imshow(image, interpolation="nearest")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_facecolor("#0b1020")
        fig.patch.set_facecolor("#0b1020")
        ax.set_title("\n".join(caption), color="#e5e7eb", loc="left", fontsize=12)
        legend_text = "  ".join(f"{name}" for name in STATE_ORDER)
        ax.text(
            0.01,
            -0.06,
            legend_text,
            transform=ax.transAxes,
            color="#cbd5e1",
            fontsize=8,
            va="top",
        )
        fig.canvas.draw()
        frame = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
        frames.append(frame)
        plt.close(fig)
        if end >= len(events):
            break

    imageio.mimsave(output, frames, fps=args.fps)
    return output


def main() -> None:
    output = render(parse_args())
    print(output)


if __name__ == "__main__":
    main()
