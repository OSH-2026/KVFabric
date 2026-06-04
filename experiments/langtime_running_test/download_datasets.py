#!/usr/bin/env python3
"""预下载 config.json 中声明的所有数据集到 data/ 目录。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import load_config
from src.datasets import DatasetManager


def main():
    config = load_config("config.json")
    mgr = DatasetManager(config.datasets.cache_dir, config.datasets.sources)

    print(f"缓存目录: {mgr.cache_dir}")
    print(f"数据集数量: {len(mgr.sources)}\n")

    mgr.download_all()

    print("\n数据集预备完成。")
    for f in sorted(mgr.cache_dir.iterdir()):
        if f.suffix == ".json":
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
