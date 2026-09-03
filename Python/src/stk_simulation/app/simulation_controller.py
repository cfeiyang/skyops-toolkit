"""在固定工作线程中调度全球覆盖仿真。"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal, Slot

if TYPE_CHECKING:
    from stk_simulation.stk.session import STKSession


class STKWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._session: STKSession | None = None

    @Slot(object, bool)
    def run(self, config, document_scenarios: bool) -> None:
        try:
            if self._session is None:
                from stk_simulation.stk.session import STKSession

                self._session = STKSession()
            root = self._session.connect(config.stk.mode)
            from stk_simulation.simulations.global_coverage.service import (
                compute_global_coverage,
                run_document_scenarios,
            )

            if document_scenarios:
                result = run_document_scenarios(
                    root, config, self.status_changed.emit
                )
            else:
                result = compute_global_coverage(root, config)
        except Exception as error:
            traceback.print_exc()
            self.failed.emit(str(error))
            return
        self.completed.emit(result)

    @Slot()
    def release(self) -> None:
        if self._session is not None:
            self._session.release()
            self._session = None


class SimulationController(QObject):
    run_requested = Signal(object, bool)
    release_requested = Signal()
    busy_changed = Signal(bool)
    completed = Signal(object)
    failed = Signal(str)
    status_changed = Signal(str)

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

    def start(self, config, document_scenarios: bool = False) -> None:
        if self._busy:
            raise RuntimeError("已有仿真任务正在运行。")
        self._set_busy(True)
        self.run_requested.emit(config, document_scenarios)

    def shutdown(self) -> None:
        self.release_requested.emit()
        self._thread.quit()
        self._thread.wait()

    @Slot(object)
    def _on_completed(self, result) -> None:
        self._set_busy(False)
        self.completed.emit(result)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.failed.emit(message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)
