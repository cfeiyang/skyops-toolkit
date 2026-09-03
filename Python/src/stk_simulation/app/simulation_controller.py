"""统一调度两个仿真功能的 STK 工作线程。"""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QThread, Signal, Slot

class STKWorker(QObject):
    completed = Signal(str, object)
    failed = Signal(str, str)
    status_changed = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._session = None

    @Slot(str, object, bool)
    def run(self, feature_key: str, config, batch: bool) -> None:
        try:
            if self._session is None:
                from stk_simulation.stk.session import STKSession

                self._session = STKSession()
            root = self._session.connect(config.stk.mode)
            if feature_key == "global_coverage":
                from stk_simulation.simulations.global_coverage.service import (
                    compute_global_coverage,
                    run_global_coverage_batch,
                )

                if batch:
                    result = run_global_coverage_batch(
                        root,
                        config,
                        lambda text: self.status_changed.emit(feature_key, text),
                    )
                else:
                    result = compute_global_coverage(root, config)
            elif feature_key == "gps_visibility":
                from stk_simulation.simulations.gps_visibility.service import (
                    compute_gps_visibility,
                )

                result = compute_gps_visibility(root, config)
            else:
                raise ValueError(f"未知仿真功能：{feature_key}")
        except Exception as error:
            traceback.print_exc()
            self.failed.emit(feature_key, str(error))
            return
        self.completed.emit(feature_key, result)

    @Slot()
    def release(self) -> None:
        if self._session is not None:
            self._session.release()
            self._session = None


class SimulationController(QObject):
    run_requested = Signal(str, object, bool)
    release_requested = Signal()
    busy_changed = Signal(bool)
    completed = Signal(str, object)
    failed = Signal(str, str)
    status_changed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._thread = QThread(self)
        self._worker = STKWorker()
        self._worker.moveToThread(self._thread)
        self.run_requested.connect(self._worker.run)
        self.release_requested.connect(self._worker.release)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.status_changed.connect(self.status_changed.emit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start(self, feature_key: str, config, batch: bool = False) -> None:
        if self._busy:
            raise RuntimeError("已有仿真任务正在运行。")
        self._set_busy(True)
        self.run_requested.emit(feature_key, config, batch)

    def shutdown(self) -> None:
        self.release_requested.emit()
        self._thread.quit()
        self._thread.wait()

    @Slot(str, object)
    def _on_completed(self, feature_key: str, result) -> None:
        self._set_busy(False)
        self.completed.emit(feature_key, result)

    @Slot(str, str)
    def _on_failed(self, feature_key: str, message: str) -> None:
        self._set_busy(False)
        self.failed.emit(feature_key, message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)
