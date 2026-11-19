"""STK Desktop 会话和 Scenario 生命周期（支持无 STK 环境安全导入）。"""

from __future__ import annotations


class STKSession:
    """在创建它的工作线程中持有并复用 STK Desktop 对象。"""

    def __init__(self) -> None:
        self.application = None
        self.root = None
        self.mode: str | None = None

    def connect(self, mode: str = "new"):
        normalized_mode = str(mode).lower()
        if self.root is not None and normalized_mode == self.mode:
            return self.root

        try:
            from agi.stk12.stkdesktop import STKDesktop  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "当前环境未安装 STK 12 Python API (agi.stk12)。"
                "请切换至顶部的「⚡ 纯 Python 极速引擎」运行，或在装有 STK 12.6 的环境中运行。"
            ) from exc

        if normalized_mode == "new":
            print("[STK] 正在新建 STK 12 实例...")
            application = STKDesktop.StartApplication(visible=True, userControl=True)
        elif normalized_mode == "running":
            print("[STK] 正在连接已运行的 STK 12 实例...")
            application = STKDesktop.AttachToApplication()
        else:
            raise ValueError(
                'STKSession.connect: mode 必须是 "new" 或 "running"，'
                f"收到：{mode}"
            )

        self.application = application
        self.root = application.Root
        self.mode = normalized_mode
        print("[STK] 对象根 root 获取成功。")
        return self.root

    def release(self) -> None:
        """释放 Python 侧引用；由用户控制的 STK Desktop 保持打开。"""
        self.root = None
        self.application = None
        self.mode = None

    @staticmethod
    def create_scenario(root, name: str, start_time: str, stop_time: str):
        preferences = root.UnitPreferences
        preferences.Item("AngleUnit").SetCurrentUnit("deg")
        preferences.Item("DistanceUnit").SetCurrentUnit("km")
        preferences.Item("TimeUnit").SetCurrentUnit("sec")
        preferences.Item("DateFormat").SetCurrentUnit("UTCG")
        preferences.Item("FrequencyUnit").SetCurrentUnit("MHz")

        if root.CurrentScenario is not None:
            root.CloseScenario()

        root.NewScenario(name)
        scenario = root.CurrentScenario
        scenario.SetTimePeriod(start_time, stop_time)
        root.Rewind()
        print(f"[场景] 成功创建 Scenario: {name}")
        return scenario
