"""让耗时 STK 计算不阻塞 Tkinter 主线程。"""

from __future__ import annotations

import queue
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from stk_api.core import STKCore


class AsyncSTKApp:
    """在一个固定工作线程中创建并使用全部 STK 对象。"""

    def __init__(self, window: tk.Tk):
        self.window = window
        self.stk_application = None
        self.stk_root = None
        self._events: queue.SimpleQueue = queue.SimpleQueue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stk")
        self._closed = False
        self.window.after(50, self._drain_events)
        self.window.protocol("WM_DELETE_WINDOW", self._close)

    def get_stk_root(self, mode: str):
        if self.stk_root is None:
            self.stk_application, self.stk_root = STKCore.start_stk(mode)
        return self.stk_root

    def submit(
        self,
        task: Callable,
        on_success: Callable,
        on_error: Callable,
    ) -> None:
        future = self._executor.submit(task)
        future.add_done_callback(
            lambda completed: self._events.put(
                (self._deliver_result, (completed, on_success, on_error))
            )
        )

    def post(self, callback: Callable, *args) -> None:
        self._events.put((callback, args))

    @staticmethod
    def _deliver_result(
        future: Future, on_success: Callable, on_error: Callable
    ) -> None:
        try:
            on_success(future.result())
        except Exception as error:
            on_error(error)

    def _drain_events(self) -> None:
        while True:
            try:
                callback, args = self._events.get_nowait()
            except queue.Empty:
                break
            callback(*args)
        if not self._closed:
            self.window.after(50, self._drain_events)

    def _close(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()
