"""Parallel execution utilities for tool calls.

Provides simple thread-based parallelism for I/O-bound tasks like
RDKit matching + NN matching that should run concurrently.
"""

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def run_parallel(*tasks: tuple[Callable[..., T], tuple, dict]) -> list[T | Exception]:
    """Run multiple callables in parallel and return results in order.

    Args:
        *tasks: Each task is (func, args_tuple, kwargs_dict).
                Shorthand: (func,) or (func, args_tuple) also accepted.

    Returns:
        List of results (or Exception instances) in the same order as input tasks.

    Example:
        results = run_parallel(
            (rdkit_tool.match, (caption, smiles), {}),
            (nn_tool.match, (caption, smiles), {}),
        )
        rdkit_result, nn_result = results
    """
    normalized: list[tuple[Callable, tuple, dict]] = []
    for task in tasks:
        if len(task) == 1:
            normalized.append((task[0], (), {}))
        elif len(task) == 2:
            normalized.append((task[0], task[1], {}))
        else:
            normalized.append((task[0], task[1], task[2]))

    results: list[Any] = [None] * len(normalized)
    with ThreadPoolExecutor(max_workers=len(normalized)) as executor:
        future_to_idx = {}
        for i, (func, args, kwargs) in enumerate(normalized):
            future = executor.submit(func, *args, **kwargs)
            future_to_idx[future] = i
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = e
    return results
