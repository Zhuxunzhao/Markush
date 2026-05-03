"""Structured logging for Multi-Agent for Markush pipeline.

Provides colored console output with step tracking for pipeline execution.
"""

from __future__ import annotations
import logging
import sys
import time
from threading import Lock
from contextlib import contextmanager
from typing import Callable, Optional


class PipelineLogger:
    """Logger tailored for multi-step pipeline execution."""

    def __init__(self, name: str = "markush", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
            )
        self.logger.addHandler(handler)
        self._step = 0
        self._total_steps = 0
        self._listeners: list[Callable[[dict], None]] = []
        self._listener_lock = Lock()

    def set_total_steps(self, total: int):
        self._total_steps = total
        self._step = 0
        self._emit("reset", total_steps=total)

    def step(self, msg: str):
        self._step += 1
        prefix = f"[{self._step}/{self._total_steps}]" if self._total_steps else f"[{self._step}]"
        self.logger.info(f"{prefix} {msg}")
        self._emit("step", message=msg, step=self._step, total_steps=self._total_steps)

    def info(self, msg: str):
        self.logger.info(msg)
        self._emit("info", message=msg, step=self._step, total_steps=self._total_steps)

    def warning(self, msg: str):
        self.logger.warning(msg)
        self._emit("warning", message=msg, step=self._step, total_steps=self._total_steps)

    def error(self, msg: str):
        self.logger.error(msg)
        self._emit("error", message=msg, step=self._step, total_steps=self._total_steps)

    def debug(self, msg: str):
        self.logger.debug(msg)
        self._emit("debug", message=msg, step=self._step, total_steps=self._total_steps)

    def add_listener(self, listener: Callable[[dict], None]) -> Callable[[], None]:
        with self._listener_lock:
            self._listeners.append(listener)

        def remove() -> None:
            with self._listener_lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return remove

    def _emit(self, level: str, **payload) -> None:
        event = {"level": level, **payload}
        with self._listener_lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                continue

    @contextmanager
    def timed(self, label: str):
        """Context manager that logs elapsed time."""
        start = time.time()
        self.info(f"  \u25ba {label}...")
        try:
            yield
        finally:
            elapsed = time.time() - start
            self.info(f"  \u2713 {label} done ({elapsed:.1f}s)")


# Singleton
log = PipelineLogger()
