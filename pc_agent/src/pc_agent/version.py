"""Thông tin phiên bản của PC Agent (A-9-3).

Mục đích: khi sự cố xảy ra trên máy chủ rack, cần biết **chính xác** đang
chạy phiên bản nào — mã nguồn commit bao nhiêu, build lúc nào. Không có
thông tin này thì việc truy vết là đoán mò.

Nguồn thông tin, theo thứ tự ưu tiên:
  1. `importlib.metadata.version("pc-agent")` — version do pip ghi vào
     metadata lúc cài đặt.
  2. File `_version.py` sinh sẵn trong package (nếu đóng gói bằng
     `setuptools-scm` hoặc cài đặt tay).
  3. Biến môi trường `PC_AGENT_VERSION` — tiện cho container/CI.

Git commit SHA:
  - ưu tiên biến môi trường `PC_AGENT_GIT_COMMIT` (do CI/Dockerfile set khi build);
  - nếu không có, thử đọc từ `.git/HEAD` + `.git/refs/...` khi chạy trong
    working tree (tiện cho việc phát triển);
  - nếu không có → `"unknown"`.

Không bao giờ `raise` — endpoint `/api/health` phải luôn trả lời, kể cả khi
mọi thứ về version đều hỏng.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

LOG = logging.getLogger("pc_agent.version")

FALLBACK_VERSION = "0.0.0+unknown"
UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
def package_version() -> str:
    """Version của package (không bao giờ raise)."""
    env = os.environ.get("PC_AGENT_VERSION")
    if env:
        return env

    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("pc-agent")
    except Exception:  # noqa: BLE001 - PackageNotFoundError và mọi lỗi khác
        pass

    try:
        from ._version import __version__  # type: ignore

        return str(__version__)
    except Exception:  # noqa: BLE001
        pass

    return FALLBACK_VERSION


# --------------------------------------------------------------------------- #
def _read_git_dir(git_dir: Path) -> Optional[str]:
    """Đọc commit SHA từ `.git` (HEAD → ref → packed-refs)."""
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None

    # HEAD trỏ tới branch: "ref: refs/heads/main"
    if head.startswith("ref:"):
        ref = head.split(":", 1)[1].strip()
        try:
            sha = (git_dir / ref).read_text(encoding="utf-8").strip()
            if len(sha) >= 7:
                return sha
        except OSError:
            pass
        # Ref có thể nằm trong packed-refs
        try:
            packed = (git_dir / "packed-refs").read_text(encoding="utf-8")
            for line in packed.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[1].strip() == ref:
                    return parts[0].strip()[:40]
        except OSError:
            pass
        return None

    # HEAD trỏ thẳng tới SHA (detached HEAD)
    if len(head) >= 7:
        return head
    return None


def git_commit() -> str:
    """Commit SHA hiện tại (hoặc `"unknown"`)."""
    env = os.environ.get("PC_AGENT_GIT_COMMIT")
    if env:
        return env

    # Đi tìm .git từ thư mục package ra ngoài (repo nguồn).
    here = Path(__file__).resolve()
    for parent in list(here.parents)[:6]:
        git_path = parent / ".git"
        if git_path.is_dir():
            sha = _read_git_dir(git_path)
            if sha:
                return sha
        elif git_path.is_file():
            # Worktree/submodule: file ".git" chứa "gitdir: <path>"
            try:
                content = git_path.read_text(encoding="utf-8").strip()
                if content.startswith("gitdir:"):
                    real = Path(content.split(":", 1)[1].strip())
                    if not real.is_absolute():
                        real = (parent / real).resolve()
                    sha = _read_git_dir(real)
                    if sha:
                        return sha
            except OSError:
                pass
    return UNKNOWN


# --------------------------------------------------------------------------- #
def build_timestamp() -> str:
    """Thời điểm build (ISO-8601), lấy từ biến môi trường hoặc mtime của file."""
    env = os.environ.get("PC_AGENT_BUILD_TIME")
    if env:
        return env

    try:
        import datetime

        mtime = Path(__file__).resolve().stat().st_mtime
        return datetime.datetime.fromtimestamp(
            mtime, tz=datetime.timezone.utc
        ).isoformat()
    except (OSError, ValueError):
        return UNKNOWN


# --------------------------------------------------------------------------- #
def version_info() -> Dict[str, Any]:
    """Thông tin phiên bản dạng dict — dùng cho `/api/health`."""
    return {
        "version": package_version(),
        "git_commit": git_commit(),
        "build_time": build_timestamp(),
        "python": f"{os.sys.version_info.major}.{os.sys.version_info.minor}"
                   f".{os.sys.version_info.micro}",
    }
