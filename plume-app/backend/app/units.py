"""单位换算常量，集中定义避免散落魔数。

排放率输入单位：克每秒 (g/s)
浓度输出单位：  微克每立方米 (μg/m³)
1 g = 1e6 μg
"""
from __future__ import annotations

GRAMS_TO_MICROGRAMS = 1.0e6
MICROGRAMS_TO_GRAMS = 1.0e-6
