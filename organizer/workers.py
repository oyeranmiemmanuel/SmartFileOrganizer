"""Run slow jobs on a background thread and hand results to the UI thread.

The UI never shares widgets or Tk variables with the worker. It calls
``poll()`` from a timer on the main thread and receives plain events:

* progress events are coalesced: only the newest one is kept, so a fast job
  cannot flood the interface;
* the final event is either ``result`` or ``error`` and is always delivered.
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable, NamedTuple

PROGRESS = "progress"
RESULT = "result"
ERROR = "error"


class TaskEvent(NamedTuple):
    kind: str
    payload: Any


ProgressFn = Callable[[Any], None]
CancelFn = Callable[[], bool]


class BackgroundTask:
    """``job(progress, cancel_requested)`` runs on its own thread after ``start()``."""

    def __init__(self, job: Callable[[ProgressFn, CancelFn], Any], name: str = "worker") -> None:
        self._job = job
        self._events: "queue.Queue[TaskEvent]" = queue.Queue()
        self._lock = threading.Lock()
        self._latest_progress: Any = None
        self._has_progress = False
        self._cancel = threading.Event()
        self._finished = False
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    @property
    def finished(self) -> bool:
        """True once the final event (result or error) has been handed out by poll()."""
        return self._finished

    def _post_progress(self, payload: Any) -> None:
        with self._lock:
            self._latest_progress = payload
            self._has_progress = True

    def _run(self) -> None:
        try:
            result = self._job(self._post_progress, self._cancel.is_set)
        except BaseException as exc:  # a thread must always report back
            self._events.put(TaskEvent(ERROR, exc))
        else:
            self._events.put(TaskEvent(RESULT, result))

    def poll(self) -> list[TaskEvent]:
        """Return new events without blocking. Call only from the UI thread."""
        if self._finished:
            return []
        events: list[TaskEvent] = []
        with self._lock:
            if self._has_progress:
                events.append(TaskEvent(PROGRESS, self._latest_progress))
                self._latest_progress = None
                self._has_progress = False
        try:
            while True:
                event = self._events.get_nowait()
                events.append(event)
                if event.kind in (RESULT, ERROR):
                    self._finished = True
                    break
        except queue.Empty:
            pass
        return events