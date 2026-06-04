from __future__ import annotations

import random

_FALLBACK_TOPICS = [
    "Python 装饰器的用法",
    "HTTP 和 HTTPS 的区别",
    "什么是微服务架构",
    "数据库索引的原理",
    "Linux 常用命令",
    "机器学习的基本概念",
    "Git 分支管理策略",
    "Docker 和虚拟机的区别",
]


def random_topic() -> str:
    """Return a random fallback topic string."""
    return random.choice(_FALLBACK_TOPICS)
