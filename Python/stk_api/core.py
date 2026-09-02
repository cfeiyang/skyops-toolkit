"""STK Desktop 启动、连接和 Scenario 创建。"""

from __future__ import annotations

from agi.stk12.stkdesktop import STKDesktop


class STKCore:
    @staticmethod
    def start_stk(mode: str = "new"):
        normalized_mode = str(mode).lower()

        if normalized_mode == "new":
            print("[STK] 正在新建 STK 12 实例...")
            application = STKDesktop.StartApplication(visible=True, userControl=True)
        elif normalized_mode == "running":
            print("[STK] 正在连接已运行的 STK 12 实例...")
            application = STKDesktop.AttachToApplication()
        else:
            raise ValueError(
                'STKCore.start_stk: mode 必须是 "new" 或 "running"，'
                f"收到：{mode}"
            )

        root = application.Root
        print("[STK] 对象根 root 获取成功。")
        return application, root

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
