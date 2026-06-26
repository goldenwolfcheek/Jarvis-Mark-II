"""
Jarvis Mark II — Dynamic skill loader.
Loads Python skills from the configured skills directory and provides
a unified interface for discovery and invocation.
"""

import importlib.util
import inspect
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from ..constants import SKILLS_DIR

logger = logging.getLogger(__name__)


class Skill:
    """Represents a single loaded skill with its metadata."""

    def __init__(
        self,
        name: str,
        module_path: Path,
        description: str = "",
        functions: Optional[dict[str, Callable]] = None,
    ):
        self.name = name
        self.module_path = module_path
        self.description = description
        self.functions = functions or {}

    def __repr__(self) -> str:
        return f"Skill(name='{self.name}', functions={list(self.functions.keys())})"


class SkillLoader:
    """Discovers and loads Python skill modules from the skills directory.

    Each skill is a ``.py`` file placed in ``~/.jarvis/skills/``.
    The loader expects an optional module-level ``__skill_name__``,
    ``__skill_desc__`` strings and any number of top-level async functions.
    """

    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self._skills_dir = skills_dir
        self._lock = threading.RLock()
        self._skills: dict[str, Skill] = {}
        self._loaded = False

    def _ensure_dir(self):
        self._skills_dir.mkdir(parents=True, exist_ok=True)

    def discover(self) -> list[str]:
        """Scan the skills dir for ``.py`` files and return their names."""
        self._ensure_dir()
        return sorted(
            f.stem
            for f in self._skills_dir.iterdir()
            if f.suffix == ".py" and not f.stem.startswith("_")
        )

    def load_all(self, reload: bool = False):
        """Load (or reload) all skills from the skills directory."""
        with self._lock:
            if reload:
                self._skills.clear()
            self._ensure_dir()
            names = self.discover()
            for name in names:
                if name not in self._skills or reload:
                    self._load_single(name)
            self._loaded = True

    def _load_single(self, name: str) -> Optional[Skill]:
        """Load a single skill module by name."""
        module_path = self._skills_dir / f"{name}.py"
        if not module_path.exists():
            return None

        try:
            spec = importlib.util.spec_from_file_location(f"jarvis_skills.{name}", module_path)
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            # Add skills dir to sys.path so relative imports work
            sys.path.insert(0, str(self._skills_dir))
            spec.loader.exec_module(mod)
        except Exception as exc:
            logger.error("[Jarvis] Failed to load skill '%s': %s", name, exc)
            return None
        finally:
            # Clean up sys.path
            if self._skills_dir in sys.path:
                sys.path.remove(str(self._skills_dir))

        # Extract metadata
        skill_name = getattr(mod, "__skill_name__", name)
        skill_desc = getattr(mod, "__skill_desc__", "")

        # Find public callable functions (not dunder, not imported)
        functions: dict[str, Callable] = {}
        for attr_name in dir(mod):
            if attr_name.startswith("_"):
                continue
            attr = getattr(mod, attr_name)
            if inspect.isfunction(attr) or inspect.iscoroutinefunction(attr):
                # Only include functions defined in this module
                try:
                    mod_file = inspect.getfile(attr)
                    if Path(mod_file).resolve() == module_path.resolve():
                        functions[attr_name] = attr
                except (TypeError, OSError):
                    continue

        skill = Skill(
            name=skill_name,
            module_path=module_path,
            description=skill_desc,
            functions=functions,
        )
        self._skills[name] = skill
        return skill

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a loaded skill by name."""
        self._ensure_loaded()
        with self._lock:
            return self._skills.get(name)

    def get_all_skills(self) -> list[Skill]:
        """Return all loaded skills."""
        self._ensure_loaded()
        with self._lock:
            return list(self._skills.values())

    def get_skill_names(self) -> list[str]:
        """Return names of all loaded skills."""
        self._ensure_loaded()
        with self._lock:
            return list(self._skills.keys())

    def has_skill(self, name: str) -> bool:
        """Check if a skill is loaded."""
        self._ensure_loaded()
        with self._lock:
            return name in self._skills

    def call_function(self, skill_name: str, func_name: str, *args: Any, **kwargs: Any) -> Any:
        """Call a function within a loaded skill.

        Args:
            skill_name: Name of the skill (file stem).
            func_name: Name of the function to call.
            *args, **kwargs: Passed to the function.

        Returns:
            The return value of the called function.

        Raises:
            ValueError: If the skill or function is not found.
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            raise ValueError(f"Skill '{skill_name}' not found. Available: {self.get_skill_names()}")

        func = skill.functions.get(func_name)
        if func is None:
            raise ValueError(
                f"Function '{func_name}' not found in skill '{skill_name}'. "
                f"Available: {list(skill.functions.keys())}"
            )

        return func(*args, **kwargs)

    def get_tool_definitions(self) -> list[dict]:
        """Generate OpenAI-compatible tool definitions for all skill functions.

        Returns a list of dicts suitable for inclusion in an LLM API call.
        """
        definitions = []
        for skill in self.get_all_skills():
            for func_name, func in skill.functions.items():
                sig = inspect.signature(func)
                properties = {}
                required = []
                for param_name, param in sig.parameters.items():
                    if param_name == "self":
                        continue
                    # Guess schema from annotation
                    param_type = "string"
                    if param.annotation is not inspect.Parameter.empty:
                        ann = str(param.annotation)
                        if "int" in ann:
                            param_type = "integer"
                        elif "float" in ann:
                            param_type = "number"
                        elif "bool" in ann:
                            param_type = "boolean"
                        elif "list" in ann or "dict" in ann:
                            param_type = "object"
                    properties[param_name] = {
                        "type": param_type,
                        "description": f"Parameter '{param_name}'",
                    }
                    if param.default is inspect.Parameter.empty:
                        required.append(param_name)

                definitions.append({
                    "type": "function",
                    "function": {
                        "name": f"skill_{skill.name}_{func_name}",
                        "description": skill.description or f"Skill: {skill.name} — {func_name}",
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    },
                })
        return definitions

    def _ensure_loaded(self):
        """Lazy-load if not yet loaded."""
        if not self._loaded:
            self.load_all()

    def reload_skill(self, name: str) -> Optional[Skill]:
        """Reload a single skill."""
        with self._lock:
            self._skills.pop(name, None)
        return self._load_single(name)


# ── Singleton ─────────────────────────────────────────────────────────────
_skill_loader_instance: Optional[SkillLoader] = None
_skill_loader_lock = threading.Lock()


def get_skill_loader() -> SkillLoader:
    """Return the global SkillLoader singleton."""
    global _skill_loader_instance
    if _skill_loader_instance is None:
        with _skill_loader_lock:
            if _skill_loader_instance is None:
                _skill_loader_instance = SkillLoader()
    return _skill_loader_instance
