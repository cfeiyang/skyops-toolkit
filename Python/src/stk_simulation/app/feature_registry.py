"""主窗口中的仿真功能注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Type

from PySide6.QtWidgets import QWidget

from stk_simulation.app.pages.global_coverage_page import GlobalCoveragePage
from stk_simulation.app.pages.gps_visibility_page import GPSVisibilityPage
from stk_simulation.simulations.global_coverage.config import config_global_coverage
from stk_simulation.simulations.gps_visibility.config import config_gps_visibility


@dataclass(frozen=True)
class FeatureDefinition:
    key: str
    title: str
    description: str
    page_type: Type[QWidget]
    config_factory: Callable[[], object]


FEATURES = (
    FeatureDefinition(
        key="global_coverage",
        title="全球通信时长",
        description="地面站与卫星组合的全球通信时长分析",
        page_type=GlobalCoveragePage,
        config_factory=config_global_coverage,
    ),
    FeatureDefinition(
        key="gps_visibility",
        title="GPS 可见数量",
        description="目标卫星 24 小时 GPS 可见数量分析",
        page_type=GPSVisibilityPage,
        config_factory=config_gps_visibility,
    ),
)

