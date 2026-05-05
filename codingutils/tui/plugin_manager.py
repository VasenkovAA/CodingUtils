from __future__ import annotations

import hashlib
import importlib.util
import sys
import types
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .plugin_api import PluginMeta, PluginSpec


@dataclass(slots=True)
class PluginLoadError:
    path: Path
    module_name: str
    error: str
    traceback: str = ""


class PluginManager:
    def __init__(self, plugin_dirs: List[Path]) -> None:
        self.plugin_dirs = plugin_dirs

    def discover(self) -> tuple[list[PluginSpec], list[PluginLoadError]]:
        specs: List[PluginSpec] = []
        errors: List[PluginLoadError] = []

        for base in self.plugin_dirs:
            try:
                base = base.resolve()
            except Exception:
                base = Path(base)

            if not base.exists():
                continue

            # 1) single-file plugins (*.py)
            for p in sorted(base.glob("*.py")):
                if p.name.startswith("_"):
                    continue
                spec, err = self._load_plugin_from_file(p, package_dir=None)
                if spec:
                    specs.append(spec)
                else:
                    errors.append(err)  # type: ignore[arg-type]

            # 2) package plugins (dir with __init__.py)
            for d in sorted([x for x in base.iterdir() if x.is_dir()]):
                if d.name.startswith("_"):
                    continue
                init = d / "__init__.py"
                if init.exists():
                    spec, err = self._load_plugin_from_file(init, package_dir=d)
                    if spec:
                        specs.append(spec)
                    else:
                        errors.append(err)  # type: ignore[arg-type]

        # unique by plugin id
        uniq: Dict[str, PluginSpec] = {s.meta.id: s for s in specs}
        return list(uniq.values()), errors

    @staticmethod
    def _ensure_runtime_package(fullname: str) -> None:
        """
        Создаёт runtime-пакет в sys.modules, если его нет.
        Нужно для того, чтобы плагины грузились как `codingutils.tui._plugins.*`
        и у них работали относительные импорты.
        """
        if fullname in sys.modules:
            return
        pkg = types.ModuleType(fullname)
        pkg.__path__ = []  # mark as package
        sys.modules[fullname] = pkg

    def _load_plugin_from_file(
        self,
        file_path: Path,
        package_dir: Optional[Path] = None,
    ) -> tuple[Optional[PluginSpec], Optional[PluginLoadError]]:
        mod_name = "<unknown>"
        try:
            file_path = file_path.resolve()
            if package_dir is not None:
                package_dir = package_dir.resolve()

            mod_name = self._make_module_name(file_path, package_dir)

            # гарантируем существование namespace-пакета для плагинов
            # (не требуем реального каталога codingutils/tui/_plugins на диске)
            self._ensure_runtime_package("codingutils.tui._plugins")

            # Создаём spec
            if package_dir is not None:
                spec = importlib.util.spec_from_file_location(
                    mod_name,
                    str(file_path),
                    submodule_search_locations=[str(package_dir)],
                )
            else:
                spec = importlib.util.spec_from_file_location(mod_name, str(file_path))

            if spec is None or spec.loader is None:
                return None, PluginLoadError(file_path, mod_name, "spec_from_file_location failed")

            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)  # type: ignore[attr-defined]

            meta_raw: Any = getattr(module, "PLUGIN_META", None)
            if not isinstance(meta_raw, dict):
                return None, PluginLoadError(
                    file_path,
                    mod_name,
                    f"PLUGIN_META not found or not dict (type={type(meta_raw)!r}, value={meta_raw!r})",
                )

            pid = str(meta_raw.get("id", "")).strip()
            name = str(meta_raw.get("name", "")).strip()
            if not pid or not name:
                return None, PluginLoadError(file_path, mod_name, "PLUGIN_META must include non-empty 'id' and 'name'")

            create_ui = getattr(module, "create_ui", None)
            if not callable(create_ui):
                return None, PluginLoadError(file_path, mod_name, "create_ui(ctx) not found or not callable")

            meta = PluginMeta(
                id=pid,
                name=name,
                version=str(meta_raw.get("version", "") or ""),
                description=str(meta_raw.get("description", "") or ""),
            )

            return PluginSpec(meta=meta, path=file_path, module_name=mod_name, create_ui=create_ui), None

        except Exception as e:
            tb = traceback.format_exc()
            return None, PluginLoadError(Path(file_path), mod_name, repr(e), tb)

    @staticmethod
    def _make_module_name(file_path: Path, package_dir: Optional[Path]) -> str:
        """
        Важно: имя модуля должно лежать под `codingutils.tui._plugins.*`,
        чтобы внутри плагина работали импорты вида `from ..plugin_api import ...`
        """
        key = f"{str(package_dir) if package_dir else ''}|{str(file_path)}"
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return f"codingutils.tui._plugins.plugin_{h}"