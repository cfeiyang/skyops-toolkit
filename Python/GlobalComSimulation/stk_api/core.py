from __future__ import annotations

from comtypes.client import CreateObject, GetActiveObject

from stk_api.typelib import load_stk_modules, qi


class STKCore:
    @staticmethod
    def start_stk(mode: str = "new"):
        load_stk_modules()
        mode = str(mode).lower()
        if mode == "new":
            print("[STK] 正在新建 STK 12 实例...")
            app = CreateObject("STK12.Application")
            app.Visible = True
            app.UserControl = True
        elif mode == "running":
            print("[STK] 正在连接已运行的 STK 12 实例...")
            app = GetActiveObject("STK12.Application")
            app.Visible = True
        elif mode == "auto":
            try:
                app = GetActiveObject("STK12.Application")
                print("成功连接到已运行的 STK 12.6 实例！")
                app.Visible = True
            except OSError:
                print("未检测到运行中的 STK，正在自动启动新实例...")
                app = CreateObject("STK12.Application")
                app.Visible = True
                app.UserControl = True
        else:
            raise ValueError(f'STKCore.start_stk: mode 必须是 "new"、"running" 或 "auto"，收到：{mode}')

        root = app.Personality2
        print("[STK] 对象根 root 获取成功。")
        return app, root

    @staticmethod
    def create_scenario(root, name: str, start_time: str, stop_time: str):
        stk_objects, _ = load_stk_modules()
        prefs = root.UnitPreferences
        prefs.Item("AngleUnit").SetCurrentUnit("deg")
        prefs.Item("DistanceUnit").SetCurrentUnit("km")
        prefs.Item("TimeUnit").SetCurrentUnit("sec")
        prefs.Item("DateFormat").SetCurrentUnit("UTCG")
        prefs.Item("FrequencyUnit").SetCurrentUnit("MHz")

        if root.CurrentScenario is not None:
            root.CloseScenario()

        root.NewScenario(name)
        scenario = qi(root.CurrentScenario, stk_objects.IAgScenario)
        scenario.SetTimePeriod(start_time, stop_time)
        root.Rewind()
        print(f"[场景] 成功创建 Scenario: {name}")
        return scenario
