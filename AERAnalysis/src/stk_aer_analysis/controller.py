"""在固定工作线程中执行 STK 操作。"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QThread, Signal, Slot

if TYPE_CHECKING:
    from stk_aer_analysis.stk_service import STKService


class ScenarioWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._service: STKService | None = None

    @Slot(object)
    def create(self, request) -> None:
        try:
            if self._service is None:
                from stk_aer_analysis.stk_service import STKService

                self._service = STKService()
            result = self._service.create_scenario(request, self.progress.emit)
        except Exception as error:
            traceback.print_exc()
            self.failed.emit(str(error))
            return
        self.completed.emit(result)

    @Slot()
    def release(self) -> None:
        if self._service is not None:
            self._service.release()
            self._service = None


class ScenarioController(QObject):
    create_requested = Signal(object)
    release_requested = Signal()
    busy_changed = Signal(bool)
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._thread = QThread(self)
        self._worker = ScenarioWorker()
        self._worker.moveToThread(self._thread)
        self.create_requested.connect(self._worker.create)
        self.release_requested.connect(self._worker.release)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.progress.connect(self.progress.emit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    @property
    def is_busy(self) -> bool:
        return self._busy

    def start(self, request) -> None:
        if self._busy:
            raise RuntimeError("已有任务正在执行。")
        self._set_busy(True)
        self.create_requested.emit(request)

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
