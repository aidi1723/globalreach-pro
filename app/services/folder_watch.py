from __future__ import annotations

from pathlib import Path


WATCHABLE_SUFFIXES = {".csv", ".xlsx", ".xls"}


class FolderWatcher:
    def __init__(self):
        self._snapshot: dict[str, float] = {}

    def prime(self, folder_path: str):
        self._snapshot = self._scan(folder_path)

    def poll(self, folder_path: str) -> list[str]:
        current = self._scan(folder_path)
        added = []
        for path, mtime in current.items():
            if path not in self._snapshot or mtime > self._snapshot[path]:
                added.append(path)
        self._snapshot = current
        return sorted(added, key=lambda item: current[item])

    def _scan(self, folder_path: str) -> dict[str, float]:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return {}
        results = {}
        for child in folder.iterdir():
            if child.is_file() and child.suffix.lower() in WATCHABLE_SUFFIXES:
                try:
                    results[str(child.resolve())] = child.stat().st_mtime
                except FileNotFoundError:
                    continue
        return results
