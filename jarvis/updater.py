"""
Jarvis Mark II — Auto-Updater.

Checks the GitHub repo for new commits and applies updates.
Two modes: git pull (preferred) or zip-download fallback.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# ── Repo configuration ──────────────────────────────────────────────────
REPO_OWNER = "goldenwolfcheek"
REPO_NAME = "Jarvis-Mark-II"
REPO_FULL = f"{REPO_OWNER}/{REPO_NAME}"
GITHUB_API = "https://api.github.com"
UPDATE_STATE_FILE = "update_state.json"  # stored inside ~/.jarvis/


# ── State persistence ───────────────────────────────────────────────────

def _state_path() -> Path:
    """Return path to update state file inside ~/.jarvis."""
    return Path.home() / ".jarvis" / UPDATE_STATE_FILE


def _load_state() -> dict:
    """Load persisted update state. Returns dict with keys:
    - last_checked_sha: str or None
    - last_checked_at: str (ISO timestamp) or None
    """
    path = _state_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_checked_sha": None, "last_checked_at": None}


def _save_state(**kwargs):
    """Merge kwargs into current state and persist."""
    state = _load_state()
    state.update(kwargs)
    state["last_checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(
        json.dumps(state, indent=2, default=str), encoding="utf-8"
    )


# ── GitHub API helpers ─────────────────────────────────────────────────

def _latest_commit() -> dict | None:
    """Fetch the latest commit on the default branch from GitHub API.

    Returns dict with 'sha', 'message', 'date', 'url', or None on failure.
    """
    url = f"{GITHUB_API}/repos/{REPO_FULL}/commits/master"
    try:
        resp = httpx.get(url, timeout=15, headers={"Accept": "application/vnd.github.v3+json"})
        resp.raise_for_status()
        data = resp.json()
        sha = data.get("sha", "")
        # Extract commit message (first line)
        raw_msg = (data.get("commit") or {}).get("message", "")
        msg = raw_msg.split("\n")[0] if raw_msg else ""
        date = (data.get("commit") or {}).get("committer") or {}
        committed_at = date.get("date", "")
        return {
            "sha": sha,
            "message": msg,
            "date": committed_at,
            "url": data.get("html_url", ""),
        }
    except Exception as e:
        logger.warning("Update check failed: %s", e)
        return None


# ── Public API ──────────────────────────────────────────────────────────

def check_for_updates() -> dict:
    """Check GitHub for newer commits.

    Returns dict with keys:
      - has_update: bool
      - current_version: str (from constants)
      - latest_sha: str or None
      - current_sha: str or None
      - commit_message: str or None
      - commit_date: str or None
      - commit_url: str or None
      - error: str or None (if check failed)
    """
    from .constants import VERSION

    state = _load_state()
    current_sha = state.get("last_checked_sha")

    latest = _latest_commit()
    if latest is None:
        return {
            "has_update": False,
            "current_version": VERSION,
            "latest_sha": None,
            "current_sha": current_sha,
            "commit_message": None,
            "commit_date": None,
            "commit_url": None,
            "error": "Could not reach GitHub API. Check your internet connection.",
        }

    latest_sha = latest["sha"]
    has_update = (current_sha is not None) and (latest_sha != current_sha)

    # Persist the latest SHA for future comparisons
    _save_state(last_checked_sha=latest_sha)

    return {
        "has_update": has_update,
        "current_version": VERSION,
        "latest_sha": latest_sha,
        "current_sha": current_sha,
        "commit_message": latest["message"],
        "commit_date": latest["date"],
        "commit_url": latest["url"],
        "error": None,
    }


def get_update_status() -> dict:
    """Get current update status without hitting GitHub API.

    Returns:
      - current_version: str
      - last_checked_at: str or None
      - last_checked_sha: str or None
    """
    from .constants import VERSION
    state = _load_state()
    return {
        "current_version": VERSION,
        "last_checked_at": state.get("last_checked_at"),
        "last_checked_sha": state.get("last_checked_sha"),
    }


def apply_update(project_root: str | Path | None = None) -> dict:
    """Apply the latest update from GitHub.

    Strategy:
    1. Try 'git pull' in the project directory (cleanest — preserves local commits).
    2. Fall back to downloading & extracting a zip of the repo.

    Returns dict with keys:
      - success: bool
      - method: str ('git_pull' | 'zip_download' | None)
      - message: str
    """
    if project_root is None:
        # Resolve project root: this file is at jarvis/updater.py → parent dir
        project_root = Path(__file__).resolve().parent.parent

    project_root = Path(project_root).resolve()

    if not project_root.joinpath(".git").is_dir():
        logger.info("No .git directory found, trying zip fallback")
        return _apply_zip(project_root)

    return _apply_git_pull(project_root)


def _apply_git_pull(project_root: Path) -> dict:
    """Run git pull in the project directory."""
    from .constants import VERSION

    try:
        # Check git is available
        subprocess.run(
            ["git", "--version"],
            capture_output=True, timeout=10, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        logger.warning("Git not available, falling back to zip download")
        return _apply_zip(project_root)

    # Check local git remote matches our repo
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
            cwd=str(project_root),
        )
        remote_url = result.stdout.strip()
        if REPO_FULL not in remote_url and REPO_NAME not in remote_url:
            return {
                "success": False,
                "method": "git_pull",
                "message": (
                    f"Git remote origin ('{remote_url}') doesn't match "
                    f"expected repo ({REPO_FULL}). Update via git pull manually."
                ),
            }
    except subprocess.CalledProcessError:
        return {
            "success": False,
            "method": "git_pull",
            "message": "No git remote 'origin' configured. Clone the repo first, or update manually.",
        }

    # Run git pull
    try:
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True, text=True, timeout=60,
            cwd=str(project_root),
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0:
            msg = f"Update applied via git pull.\n{stdout}"
            if stderr:
                msg += f"\n{stderr}"
            # Refresh state
            new_sha = _get_git_head_sha(project_root)
            if new_sha:
                _save_state(last_checked_sha=new_sha)
            return {
                "success": True,
                "method": "git_pull",
                "message": msg,
                "version": VERSION,
            }
        else:
            return {
                "success": False,
                "method": "git_pull",
                "message": f"git pull failed (exit {result.returncode}):\n{stderr or stdout}",
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "method": "git_pull",
            "message": "git pull timed out after 60 seconds.",
        }
    except Exception as e:
        return {
            "success": False,
            "method": "git_pull",
            "message": f"git pull error: {e}",
        }


def _apply_zip(project_root: Path) -> dict:
    """Download repo as zip and extract over the project directory.

    This is a fallback when git is not available or the project wasn't cloned.
    """
    from .constants import VERSION

    zip_url = f"https://github.com/{REPO_FULL}/archive/refs/heads/master.zip"
    logger.info("Downloading update from %s", zip_url)

    try:
        resp = httpx.get(zip_url, timeout=120, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        return {
            "success": False,
            "method": "zip_download",
            "message": f"Failed to download update zip: {e}",
        }

    # Extract to a temp directory
    tmp_dir = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis-update-"))
        zip_path = tmp_dir / "update.zip"
        zip_path.write_bytes(resp.content)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        # The zip contains a single top-level folder: Jarvis-Mark-II-master/
        extracted = tmp_dir / f"{REPO_NAME}-main"
        if not extracted.is_dir():
            # Try alternate naming
            dirs = [d for d in tmp_dir.iterdir() if d.is_dir()]
            if dirs:
                extracted = dirs[0]
            else:
                raise FileNotFoundError("Could not find extracted repo directory")

        # Copy files over the project root (overwrite existing)
        for item in extracted.iterdir():
            dest = project_root / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

        # Cleanup
        _save_state(last_checked_sha="zip-applied")
        return {
            "success": True,
            "method": "zip_download",
            "message": "Update applied via zip download. Please restart Jarvis.",
            "version": VERSION,
        }

    except Exception as e:
        return {
            "success": False,
            "method": "zip_download",
            "message": f"Failed to extract update: {e}",
        }
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _get_git_head_sha(project_root: Path) -> str | None:
    """Get the current HEAD commit SHA from the local git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=str(project_root),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None
