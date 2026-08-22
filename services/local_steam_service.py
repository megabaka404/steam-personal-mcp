from __future__ import annotations

import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

from errors import AppError


class LocalSteamService:
    """Read-only Steam installation data plus explicit, guarded cleanup."""

    def __init__(self, *, store=None, roots: list[str | Path] | None = None, platform_name: str | None = None) -> None:
        self.store = store
        self._configured_roots = [Path(value) for value in roots] if roots is not None else None
        self.platform_name = (platform_name or platform.system()).casefold()

    @property
    def is_windows(self) -> bool:
        return self.platform_name.startswith("win")

    def discover_library_roots(self) -> list[Path]:
        if self._configured_roots is not None:
            return _unique_paths(self._configured_roots)
        if not self.is_windows:
            return []
        candidates = []
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            value = os.environ.get(variable)
            if value:
                candidates.append(Path(value) / "Steam")
        roots: list[Path] = []
        for candidate in candidates:
            if (candidate / "steamapps").is_dir():
                roots.append(candidate)
            vdf = candidate / "steamapps" / "libraryfolders.vdf"
            if vdf.exists():
                roots.extend(_parse_libraryfolders(vdf))
        return _unique_paths(roots)

    def scan(self, *, include_actual_size: bool = False) -> dict[str, Any]:
        if not self.is_windows:
            return {
                "available": False,
                "reason": "Local Steam scanning currently supports Windows only.",
                "platform": self.platform_name,
                "locations": [],
                "installed_games": [],
                "residuals": [],
                "source": "local Steam files",
            }
        roots = self.discover_library_roots()
        installed: list[dict[str, Any]] = []
        residuals: list[dict[str, Any]] = []
        locations: list[dict[str, Any]] = []
        installed_ids: set[int] = set()
        installed_names: dict[int, str] = {}
        library_records: list[tuple[Path, Path, list[tuple[Path, dict[str, str], int]]]] = []
        for root in roots:
            steamapps = root / "steamapps"
            if not steamapps.is_dir():
                continue
            locations.append({"path": str(root), "steamapps": str(steamapps)})
            manifests: list[tuple[Path, dict[str, str], int]] = []
            for manifest in sorted(steamapps.glob("appmanifest_*.acf")):
                state = _parse_acf(manifest)
                appid = _int_or_none(state.get("appid")) or _appid_from_name(manifest.name)
                if not appid:
                    continue
                installed_ids.add(appid)
                installed_names.setdefault(appid, state.get("name") or f"App {appid}")
                manifests.append((manifest, state, appid))
            library_records.append((root, steamapps, manifests))

        # Residual status must use the union of valid manifests from every
        # Steam Library. A shadercache can live in one root while the game is
        # installed in another root.
        for root, steamapps, manifests in library_records:
            for manifest, state, appid in manifests:
                installdir = str(state.get("installdir") or "").strip()
                install_path = steamapps / "common" / installdir if installdir else None
                shader_path = steamapps / "shadercache" / str(appid)
                compat_path = steamapps / "compatdata" / str(appid)
                size_on_disk = _int_or_none(state.get("SizeOnDisk"))
                actual_size = _directory_size(install_path) if include_actual_size and install_path and install_path.is_dir() else None
                installed.append({
                    "appid": appid,
                    "name": state.get("name") or f"App {appid}",
                    "installed": True,
                    "install_path": str(install_path) if install_path else None,
                    "size_on_disk": size_on_disk,
                    "actual_directory_size": actual_size,
                    "shadercache_path": str(shader_path) if shader_path.is_dir() else None,
                    "shadercache_size": _directory_size(shader_path) if shader_path.is_dir() else 0,
                    "compatdata_status": "not_applicable",
                    "compatdata_path": None,
                    "compatdata_size": None,
                    "source": "appmanifest_<appid>.acf",
                })
            shadercache = steamapps / "shadercache"
            if shadercache.is_dir():
                for child in sorted(shadercache.iterdir()):
                    appid = _int_or_none(child.name)
                    if appid and appid not in installed_ids:
                        residuals.append(_residual(child, appid, "shadercache", installed_names.get(appid, f"App {appid}")))
        return {
            "available": True,
            "platform": "windows",
            "locations": locations,
            "count": len(installed),
            "installed_games": sorted(installed, key=lambda item: (item["name"].casefold(), item["appid"])),
            "residuals": sorted(residuals, key=lambda item: (item["appid"], item["target"])),
            "source": "local Steam files: libraryfolders.vdf and appmanifest_<appid>.acf",
            "notes": [
                "SizeOnDisk is Steam's manifest value; actual_directory_size is an optional filesystem scan.",
                "compatdata is not applicable in the Windows first version.",
            ],
        }

    def game_info(self, appid: int, *, include_actual_size: bool = False) -> dict[str, Any]:
        result = self.scan(include_actual_size=include_actual_size)
        if not result.get("available"):
            return {"available": False, "appid": appid, "reason": result.get("reason"), "source": result.get("source")}
        item = next((game for game in result["installed_games"] if game["appid"] == int(appid)), None)
        if item:
            return {"available": True, **item}
        return {
            "available": True,
            "appid": int(appid),
            "installed": False,
            "install_path": None,
            "size_on_disk": None,
            "actual_directory_size": None,
            "shadercache_size": 0,
            "compatdata_status": "not_applicable",
            "compatdata_size": None,
            "source": "local Steam files",
        }

    def storage_scan(self) -> dict[str, Any]:
        result = self.scan(include_actual_size=False)
        if not result.get("available"):
            return result
        return {
            "available": True,
            "residuals": result["residuals"],
            "count": len(result["residuals"]),
            "total_shadercache_bytes": sum(item["size_bytes"] for item in result["residuals"] if item["target"] == "shadercache"),
            "total_compatdata_bytes": 0,
            "source": "MCP local scan; scan never deletes",
            "safety": "Only uninstalled residuals are candidates. Windows compatdata is not applicable.",
        }

    def storage_preview(self, *, appids: list[int] | None = None, targets: list[str] | None = None) -> dict[str, Any]:
        scan = self.storage_scan()
        if not scan.get("available"):
            return scan
        selected = self._select_residuals(scan["residuals"], appids=appids, targets=targets)
        return {
            **scan,
            "preview": selected,
            "selected_count": len(selected),
            "will_delete": False,
            "requires_confirmation": True,
        }

    def storage_clean(self, *, appids: list[int] | None, targets: list[str] | None, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise AppError("CONFIRMATION_REQUIRED", "Cleaning is disabled unless confirm=true is explicitly supplied.")
        if not appids:
            raise AppError("INVALID_ARGUMENT", "clean requires an explicit non-empty appids list.")
        if not targets:
            raise AppError("INVALID_ARGUMENT", "clean requires an explicit targets list.")
        invalid = sorted(set(targets) - {"shadercache", "compatdata"})
        if invalid:
            raise AppError("INVALID_ARGUMENT", "targets may only contain shadercache or compatdata.", {"invalid_targets": invalid})
        preview = self.storage_preview(appids=appids, targets=targets)
        if not preview.get("available"):
            return preview
        cleaned = []
        for item in preview["preview"]:
            if item["target"] == "compatdata":
                cleaned.append({**item, "cleaned": False, "reason": "compatdata is not applicable on Windows."})
                continue
            path = Path(item["path"])
            if not _safe_residual_path(path, self.discover_library_roots(), item["appid"], item["target"]):
                cleaned.append({**item, "cleaned": False, "reason": "Safety check rejected the path."})
                continue
            try:
                shutil.rmtree(path)
                cleaned.append({**item, "cleaned": True})
            except OSError as exc:
                cleaned.append({**item, "cleaned": False, "reason": f"{type(exc).__name__}: {exc}"})
        return {
            "available": True,
            "cleaned": True,
            "confirmed": True,
            "items": cleaned,
            "source": "Explicit local cleanup after scan/preview confirmation",
        }

    def _select_residuals(self, residuals: list[dict[str, Any]], *, appids: list[int] | None, targets: list[str] | None) -> list[dict[str, Any]]:
        ids = {int(value) for value in (appids or [])}
        target_set = set(targets or {"shadercache"})
        return [item for item in residuals if (not ids or item["appid"] in ids) and item["target"] in target_set]

    @staticmethod
    def _name_for(appid: int, installed: list[dict[str, Any]]) -> str:
        return next((item["name"] for item in installed if item["appid"] == appid), f"App {appid}")


def _parse_libraryfolders(path: Path) -> list[Path]:
    text = path.read_text(encoding="utf-8", errors="replace")
    paths = []
    for raw in re.findall(r'"path"\s+"([^"]+)"', text, flags=re.IGNORECASE):
        value = raw.replace("\\\\", "\\")
        candidate = Path(value)
        if (candidate / "steamapps").is_dir():
            paths.append(candidate)
    return paths


def _parse_acf(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {key: value for key, value in re.findall(r'"([^"]+)"\s+"([^"]*)"', text)}


def _directory_size(path: Path | None) -> int:
    if path is None or not path.is_dir():
        return 0
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _residual(path: Path, appid: int, target: str, name: str) -> dict[str, Any]:
    return {
        "appid": appid,
        "game_name": name,
        "installed": False,
        "target": target,
        "path": str(path),
        "size_bytes": _directory_size(path),
        "last_modified": path.stat().st_mtime if path.exists() else None,
        "risk": "low" if target == "shadercache" else "high",
    }


def _safe_residual_path(path: Path, roots: list[Path], appid: int, target: str) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if not resolved.is_dir() or resolved.name != str(appid):
        return False
    if target == "shadercache":
        expected_parents = {(root / "steamapps" / "shadercache").resolve() for root in roots}
    else:
        expected_parents = {(root / "steamapps" / "compatdata").resolve() for root in roots}
    return resolved.parent in expected_parents


def _appid_from_name(name: str) -> int | None:
    match = re.search(r"appmanifest_(\d+)\.acf$", name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _unique_paths(values: list[Path]) -> list[Path]:
    result = []
    seen = set()
    for value in values:
        try:
            key = str(value.resolve())
        except OSError:
            key = str(value)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
