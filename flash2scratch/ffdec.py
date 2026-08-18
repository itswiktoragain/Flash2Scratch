from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class FFDecError(RuntimeError):
    pass


@dataclass
class FFDecResult:
    root: Path
    scripts: Path
    frames: Path
    sprites: Path
    sounds: Path
    xml: Path


@dataclass(frozen=True)
class SWFRuntime:
    vm: str
    swf_version: int

    @property
    def actionscript(self) -> str:
        if self.vm == "avm2":
            return "ActionScript 3 / AVM2"
        if self.vm == "avm1":
            return "ActionScript 1/2 / AVM1"
        return "No ActionScript detected"


_RELEASE_API = "https://api.github.com/repos/jindrapetrik/jpexs-decompiler/releases/latest"
_RELEASE_PREFIX = "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/"
StatusCallback = Callable[[str], None]


def _app_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "Flash2Scratch"


def _cached_ffdec_root() -> Path:
    return _app_data_dir() / "ffdec"


def _runner_names() -> tuple[str, ...]:
    if platform.system() == "Windows":
        return ("ffdec.exe", "ffdec.bat", "ffdec.cmd", "ffdec")
    return ("ffdec", "ffdec.sh")


def _locate_in(root: Path) -> Path | None:
    if not root.exists():
        return None
    names = _runner_names()
    found: list[Path] = []
    for name in names:
        found.extend(root.rglob(name))
    if not found:
        return None
    order = {name: i for i, name in enumerate(names)}
    found.sort(
        key=lambda p: (
            order.get(p.name.lower(), 99),
            len(p.relative_to(root).parts),
            str(p).lower(),
        )
    )
    return found[0]


def find_ffdec(explicit: str | None = None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    if os.getenv("FFDEC"):
        candidates.append(os.environ["FFDEC"])
    candidates += list(_runner_names())
    candidates += ["ffdec-cli.exe"]

    for candidate in candidates:
        path = candidate if Path(candidate).exists() else shutil.which(candidate)
        if path:
            return str(Path(path).expanduser().resolve())

    cached = _locate_in(_cached_ffdec_root())
    if cached:
        return str(cached.resolve())

    raise FFDecError(
        "JPEXS FFDec not found. The desktop app can install it automatically, "
        "or you can set FFDEC / choose an FFDec executable manually."
    )


def _request_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Flash2Scratch",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except Exception as exc:
        raise FFDecError(f"Could not query the latest FFDec release: {exc}") from exc


def _select_portable_asset(release: dict) -> tuple[str, str]:
    choices: list[tuple[str, str]] = []
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        lower = name.lower()
        url = str(asset.get("browser_download_url", ""))
        if (
            lower.startswith("ffdec_")
            and lower.endswith(".zip")
            and not lower.startswith("ffdec_lib_")
            and "_macosx" not in lower
            and "_lang" not in lower
            and url.startswith(_RELEASE_PREFIX)
        ):
            choices.append((name, url))

    if not choices:
        raise FFDecError("The latest FFDec release has no standard portable ZIP asset.")

    choices.sort(key=lambda item: (len(item[0]), item[0]))
    return choices[0]


def _download(url: str, destination: Path, status: StatusCallback | None = None) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Flash2Scratch"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else 0
            done = 0
            last_percent = -1
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if status and total:
                    percent = int(done * 100 / total)
                    if percent >= last_percent + 10 or percent == 100:
                        last_percent = percent
                        status(f"Downloading FFDec… {percent}%")
    except Exception as exc:
        raise FFDecError(f"Could not download FFDec: {exc}") from exc


def _safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (destination / member.filename).resolve()
            if target != destination and destination not in target.parents:
                raise FFDecError("The FFDec archive contains an unsafe path.")
        zf.extractall(destination)


def install_ffdec(status: StatusCallback | None = None) -> str:
    if status:
        status("FFDec is not installed — fetching the latest stable release…")

    release = _request_json(_RELEASE_API)
    tag = str(release.get("tag_name") or "latest")
    asset_name, download_url = _select_portable_asset(release)

    install_root = _cached_ffdec_root() / tag.replace("/", "_")
    existing = _locate_in(install_root)
    if existing:
        if status:
            status(f"Using cached FFDec {tag}.")
        return str(existing.resolve())

    install_root.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="flash2scratch-ffdec-") as temp_dir:
        archive = Path(temp_dir) / asset_name
        if status:
            status(f"Downloading {asset_name}…")
        _download(download_url, archive, status=status)

        staging = Path(temp_dir) / "unpacked"
        staging.mkdir(parents=True, exist_ok=True)
        if status:
            status("Installing FFDec into the Flash2Scratch app-data folder…")
        try:
            _safe_extract(archive, staging)
        except (OSError, zipfile.BadZipFile) as exc:
            raise FFDecError(f"Could not unpack FFDec: {exc}") from exc

        runner = _locate_in(staging)
        if runner is None:
            raise FFDecError("FFDec downloaded successfully, but its command-line launcher was not found.")

        if install_root.exists():
            shutil.rmtree(install_root)
        shutil.copytree(staging, install_root)

    runner = _locate_in(install_root)
    if runner is None:
        raise FFDecError("FFDec was installed, but its launcher could not be found afterwards.")

    if platform.system() != "Windows":
        for name in ("ffdec", "ffdec.sh"):
            for path in install_root.rglob(name):
                try:
                    path.chmod(path.stat().st_mode | 0o111)
                except OSError:
                    pass

    if status:
        status(f"FFDec {tag} installed automatically.")
    return str(runner.resolve())


def ensure_ffdec(explicit: str | None = None, status: StatusCallback | None = None) -> str:
    try:
        path = find_ffdec(explicit)
        if status:
            status(f"FFDec ready: {path}")
        return path
    except FFDecError:
        if explicit:
            raise
        return install_ffdec(status=status)


def _run(ffdec: str, args: list[str]) -> str:
    try:
        process = subprocess.run(
            [ffdec, "-cli", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError as exc:
        raise FFDecError(f"Could not start FFDec: {exc}") from exc

    if process.returncode != 0:
        extra = ""
        lower = process.stdout.lower()
        if "java" in lower and ("not found" in lower or "not recognized" in lower):
            extra = "\nFFDec requires Java; install a Java runtime and try again."
        raise FFDecError(f"FFDec failed ({process.returncode}):\n{process.stdout}{extra}")
    return process.stdout


def swf_version(swf: Path) -> int:
    try:
        with swf.open("rb") as handle:
            header = handle.read(4)
    except OSError as exc:
        raise FFDecError(f"Could not read SWF header: {exc}") from exc
    if len(header) < 4 or header[:3] not in (b"FWS", b"CWS", b"ZWS"):
        raise FFDecError("The selected file is not a valid SWF file (bad SWF header).")
    return header[3]


def detect_runtime(ffdec: str, swf: Path) -> SWFRuntime:
    version = swf_version(swf)
    tags = _run(ffdec, ["-dumpSWF", str(swf)])
    if "DoABC" in tags or "DoABCDefine" in tags:
        return SWFRuntime("avm2", version)
    if "DoAction" in tags or "DoInitAction" in tags or version <= 8:
        return SWFRuntime("avm1", version)
    return SWFRuntime("none", version)


def assert_as3(ffdec: str, swf: Path) -> None:
    """Compatibility helper retained for callers that explicitly require AS3."""
    runtime = detect_runtime(ffdec, swf)
    if runtime.vm != "avm2":
        raise FFDecError(
            f"This is a valid SWF v{runtime.swf_version}, but it uses "
            f"{runtime.actionscript}, not ActionScript 3 / AVM2."
        )


def export_swf(ffdec: str, swf: Path, root: Path) -> FFDecResult:
    root.mkdir(parents=True, exist_ok=True)
    _run(
        ffdec,
        [
            "-format",
            "script:as,frame:png,sprite:png,sound:mp3_wav",
            "-export",
            "script,frame,sprite,sound,symbolClass",
            str(root),
            str(swf),
        ],
    )
    xml = root / "movie.xml"
    _run(ffdec, ["-swf2xml", str(swf), str(xml)])
    return FFDecResult(root, root / "scripts", root / "frames", root / "sprites", root / "sounds", xml)
