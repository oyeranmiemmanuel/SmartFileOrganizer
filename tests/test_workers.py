import threading
import time

from organizer.workers import ERROR, PROGRESS, RESULT, BackgroundTask, TaskEvent


def drain(task, timeout=5.0):
    events = []
    deadline = time.monotonic() + timeout
    while not task.finished and time.monotonic() < deadline:
        events.extend(task.poll())
        time.sleep(0.01)
    return events


def test_result_is_delivered_and_poll_then_returns_nothing():
    def job(progress, cancelled):
        progress("halfway")
        return 42

    task = BackgroundTask(job)
    task.start()
    events = drain(task)
    assert events[-1] == TaskEvent(RESULT, 42)
    assert task.finished
    assert task.poll() == []


def test_errors_are_delivered_not_raised():
    def job(progress, cancelled):
        raise ValueError("boom")

    task = BackgroundTask(job)
    task.start()
    events = drain(task)
    assert events[-1].kind == ERROR
    assert isinstance(events[-1].payload, ValueError)


def test_cancellation_reaches_the_job():
    started = threading.Event()

    def job(progress, cancelled):
        started.set()
        while not cancelled():
            time.sleep(0.005)
        return "stopped"

    task = BackgroundTask(job)
    task.start()
    assert started.wait(2)
    task.cancel()
    events = drain(task)
    assert task.cancel_requested
    assert events[-1] == TaskEvent(RESULT, "stopped")


def test_only_the_newest_progress_is_kept():
    posted = threading.Event()
    release = threading.Event()

    def job(progress, cancelled):
        for number in range(1, 101):
            progress(number)
        posted.set()
        release.wait(2)
        return "done"

    task = BackgroundTask(job)
    task.start()
    assert posted.wait(2)
    assert task.poll() == [TaskEvent(PROGRESS, 100)]
    release.set()
    events = drain(task)
    assert events[-1] == TaskEvent(RESULT, "done")