"""支持「全球覆盖」与「星地建链」双业务、「STK」与「纯 Python」双引擎的异步工作线程控制器。"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal, Slot

if TYPE_CHECKING:
    from stk_simulation.stk.session import STKSession


class SimulationWorker(QObject):
    completed = Signal(object, str)  # (result, task_type)
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._session: STKSession | None = None

    def _ensure_stk_root(self, stk_mode: str):
        if self._session is None:
            from stk_simulation.stk.session import STKSession

            self._session = STKSession()
        return self._session.connect(stk_mode)

    @Slot(str, object, str)
    def run_task(self, task_type: str, config: object, run_mode: str) -> None:
        try:
            engine = getattr(getattr(config, "stk", None), "engine", "python")
            needs_stk = (engine == "stk") or (run_mode == "compare")
            root = self._ensure_stk_root(config.stk.mode) if needs_stk else None

            if task_type == "link_visibility":
                from stk_simulation.simulations.link_visibility.service import (
                    run_link_visibility,
                )

                result = run_link_visibility(
                    root, config, run_mode=run_mode, progress=self.status_changed.emit
                )
            else:
                from stk_simulation.simulations.global_coverage.service import (
                    compute_global_coverage,
                    run_document_scenarios,
                    run_station_gain,
                )

                if run_mode == "document":
                    result = run_document_scenarios(root, config, self.status_changed.emit)
                elif run_mode == "gain":
                    result = run_station_gain(root, config, self.status_changed.emit)
                else:
                    result = compute_global_coverage(
                        root, config, progress=self.status_changed.emit
                    )
        except Exception as error:
            traceback.print_exc()
            self.failed.emit(str(error))
            return
        self.completed.emit(result, task_type)

    @Slot()
    def release(self) -> None:
        if self._session is not None:
            self._session.release()
            self._session = None


class SimulationController(QObject):
    run_requested = Signal(str, object, str)
    release_requested = Signal()
    busy_changed = Signal(bool)
    completed = Signal(object, str)
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._thread = QThread(self)
        self._worker = SimulationWorker()
        self._worker.moveToThread(self._thread)
        self.run_requested.connect(self._worker.run_task)
        self.release_requested.connect(self._worker.release)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.status_changed.connect(self.status_changed.emit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start(self, config, run_mode: str = "normal", task_type: str = "global_coverage") -> None:
        if self._busy:
            raise RuntimeError("已有仿真任务正在运行，请稍候。")
        self._set_busy(True)
        self.run_requested.emit(task_type, config, run_mode)

    def shutdown(self) -> None:
        self.release_requested.emit()
        self._thread.quit()
        self._thread.wait()

    @Slot(object, str)
    def _on_completed(self, result, task_type: str) -> None:
        self._set_busy(False)
        self.completed.emit(result, task_type)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.failed.emit(message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)
