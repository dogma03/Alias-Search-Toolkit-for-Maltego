"""Core alias search integration for Sherlock and Maigret.

The module deliberately has no Maltego imports. It can be used by the
transform server and by ``scripts/search_alias.py`` without importing the SDK.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import re
import shutil
import signal
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

_MAX_RAW_RESULT = 100_000


class AliasSearchError(RuntimeError):
    """A user-facing error from a search engine."""


@dataclass
class Profile:
    site: str
    url: str
    username: str
    sources: set[str] = field(default_factory=set)
    http_status: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def merge(self, other: "Profile") -> None:
        self.sources.update(other.sources)
        if self.http_status is None:
            self.http_status = other.http_status
        for key, value in other.metadata.items():
            self.metadata.setdefault(key, value)


@dataclass
class SearchOutcome:
    engine: str
    alias: str
    profiles: list[Profile]
    duration_seconds: float
    scope: str
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    raw_result: str = ""


def _env_int(
    name: str,
    default: int,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _env_float(
    name: str,
    default: float,
    minimum: float = 1.0,
    maximum: float | None = None,
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_binary(
    env_name: str,
    fallback_paths: Sequence[str],
    fallback_commands: Sequence[str],
) -> str:
    explicit = (os.getenv(env_name) or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path)
        found = shutil.which(explicit)
        if found:
            return found
        raise AliasSearchError(
            f"{env_name} указывает на несуществующий исполняемый файл: {explicit}"
        )

    for raw_path in fallback_paths:
        path = Path(raw_path).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    for command in fallback_commands:
        found = shutil.which(command)
        if found:
            return found

    raise AliasSearchError(
        f"Не найден {env_name}. Установите инструмент или задайте "
        f"{env_name} полным путём к исполняемому файлу."
    )


def _sherlock_binary() -> str:
    return _resolve_binary(
        "SHERLOCK_BIN",
        (
            "~/Tools/Sherlock/.venv/bin/sherlock",
            "~/.local/bin/sherlock",
        ),
        ("sherlock",),
    )


def _maigret_binary() -> str:
    return _resolve_binary(
        "MAIGRET_BIN",
        (
            "~/.local/bin/maigret",
            "~/.local/share/pipx/venvs/maigret/bin/maigret",
        ),
        ("maigret",),
    )


def normalize_alias(value: Any) -> str:
    alias = str(value or "").strip()
    if alias.startswith("@"):
        alias = alias[1:]

    if not alias:
        raise ValueError("Значение Alias пустое: укажите ник без @.")
    if len(alias) > 64:
        raise ValueError("Ник слишком длинный (максимум 64 символа).")
    if alias.startswith(("http://", "https://")):
        raise ValueError(
            "В Alias нужно указывать ник, а не URL профиля. "
            "Например: torvalds, а не https://github.com/torvalds."
        )
    if any(ch.isspace() or ord(ch) < 32 for ch in alias):
        raise ValueError("Ник не должен содержать пробелы или управляющие символы.")
    if "/" in alias or "\\" in alias or alias in {".", ".."}:
        raise ValueError("Ник содержит недопустимые для поиска символы.")

    return alias


def parse_engines() -> list[str]:
    raw = os.getenv("ALIAS_ENGINES", "sherlock,maigret")
    engines: list[str] = []
    for item in raw.split(","):
        engine = item.strip().lower()
        if not engine:
            continue
        if engine not in {"sherlock", "maigret"}:
            raise ValueError(
                f"Неизвестный движок в ALIAS_ENGINES: {engine!r}. "
                "Допустимы sherlock и maigret."
            )
        if engine not in engines:
            engines.append(engine)
    if not engines:
        raise ValueError("ALIAS_ENGINES не содержит ни одного движка.")
    return engines


async def _run_command(
    command: Sequence[str],
    cwd: Path,
    timeout: float,
) -> tuple[str, str, int, float]:
    environment = os.environ.copy()
    environment.update(
        {
            "NO_COLOR": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )

    started = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise AliasSearchError(
            f"Не найден исполняемый файл: {command[0]}"
        ) from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()
        raise AliasSearchError(
            f"Поиск превысил лимит {timeout:.0f} секунд и был остановлен."
        ) from None

    duration = time.monotonic() - started
    return (
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
        process.returncode,
        duration,
    )


def _normalise_url(raw: str | None) -> str | None:
    if not raw:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        return None

    parts = urlsplit(value)
    if not parts.netloc:
        return None

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host
    if parts.port is not None and parts.port not in {80, 443}:
        netloc = f"{host}:{parts.port}"

    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            netloc,
            path,
            parts.query,
            "",
        )
    )


def _is_root_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.path in {"", "/"} and not parts.query


def _site_from_url(url: str) -> str:
    return urlsplit(url).netloc or "unknown"


def _profile(
    site: str,
    url: str,
    alias: str,
    source: str,
    *,
    http_status: int | None = None,
    metadata: dict[str, str] | None = None,
) -> Profile | None:
    normalised = _normalise_url(url)
    if not normalised or _is_root_url(normalised):
        return None

    data = dict(metadata or {})
    data["alias_in_url"] = (
        "yes" if alias.lower() in normalised.lower() else "no"
    )
    return Profile(
        site=site.strip() or _site_from_url(normalised),
        url=normalised,
        username=alias,
        sources={source},
        http_status=http_status,
        metadata=data,
    )


def _parse_sherlock_csv(
    directory: Path,
    alias: str,
    stdout: str,
) -> tuple[list[Profile], str]:
    profiles: list[Profile] = []
    seen: set[str] = set()
    raw_parts: list[str] = []

    for csv_path in sorted(directory.glob("*.csv")):
        try:
            text = csv_path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        raw_parts.append(text)
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            exists = (row.get("exists") or "").strip().lower()
            if exists and exists not in {"claimed", "found", "yes", "true"}:
                continue

            url = row.get("url_user") or row.get("url_main") or ""
            site = row.get("name") or row.get("site") or ""
            if not url:
                continue

            http_status: int | None = None
            raw_status = (row.get("http_status") or "").strip()
            if raw_status.isdigit():
                http_status = int(raw_status)

            metadata: dict[str, str] = {}
            response_time = (row.get("response_time_s") or "").strip()
            if response_time:
                metadata["response_time_s"] = response_time

            profile = _profile(
                site,
                url,
                alias,
                "Sherlock",
                http_status=http_status,
                metadata=metadata,
            )
            if profile is None or profile.url in seen:
                continue
            seen.add(profile.url)
            profiles.append(profile)

    # Fallback for unusual Sherlock versions that print results but do not
    # create a CSV file.
    if not profiles:
        for line in stdout.splitlines():
            match = re.match(
                r"^\[\+\]\s+(?P<site>.+?):\s+(?P<url>https?://\S+)\s*$",
                line,
            )
            if not match:
                continue
            profile = _profile(
                match.group("site"),
                match.group("url"),
                alias,
                "Sherlock",
            )
            if profile is None or profile.url in seen:
                continue
            seen.add(profile.url)
            profiles.append(profile)

    return profiles, "\n".join(raw_parts) or stdout


def _maigret_metadata(item: dict[str, Any]) -> dict[str, str]:
    status = item.get("status")
    ids = status.get("ids") if isinstance(status, dict) else item.get("ids")
    if not isinstance(ids, dict):
        return {}

    metadata: dict[str, str] = {}
    for key, value in ids.items():
        if str(key).startswith("_") or value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            text = ", ".join(str(part) for part in value if part not in (None, ""))
        else:
            text = str(value)
        text = text.strip()
        if not text:
            continue
        metadata[str(key)] = text[:500]
        if len(metadata) >= 12:
            break
    return metadata


def _parse_maigret_json(
    directory: Path,
    alias: str,
) -> tuple[list[Profile], str]:
    profiles: list[Profile] = []
    seen: set[str] = set()
    raw_parts: list[str] = []

    for report_path in sorted(directory.glob("report_*_simple.json")):
        try:
            text = report_path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(text)
        except (OSError, json.JSONDecodeError):
            continue
        raw_parts.append(text)
        if not isinstance(data, dict):
            continue

        for site_key, item in data.items():
            if not isinstance(item, dict):
                continue

            status = item.get("status")
            status_data = status if isinstance(status, dict) else {}
            status_text = str(
                status_data.get("status") or item.get("status") or ""
            ).strip().lower()
            if status_text not in {"claimed", "found"}:
                continue

            site_info = item.get("site") if isinstance(item.get("site"), dict) else {}
            url = (
                item.get("url_user")
                or status_data.get("url")
                or site_info.get("url")
                or ""
            )
            url = str(url).replace("{username}", alias)
            if not url:
                continue

            site = (
                status_data.get("site_name")
                or item.get("site_name")
                or site_key
            )

            http_status: int | None = None
            raw_status = item.get("http_status")
            try:
                if raw_status is not None:
                    http_status = int(raw_status)
            except (TypeError, ValueError):
                pass

            metadata = _maigret_metadata(item)
            tags = status_data.get("tags") or item.get("tags")
            if isinstance(tags, (list, tuple)) and tags:
                metadata["tags"] = ", ".join(str(tag) for tag in tags)[:300]
            if item.get("is_similar"):
                metadata["is_similar"] = "yes"

            profile = _profile(
                str(site),
                url,
                alias,
                "Maigret",
                http_status=http_status,
                metadata=metadata,
            )
            if profile is None or profile.url in seen:
                continue
            seen.add(profile.url)
            profiles.append(profile)

    return profiles, "\n".join(raw_parts)


async def search_sherlock(alias: str, timeout: float | None = None) -> SearchOutcome:
    alias = normalize_alias(alias)
    binary = _sherlock_binary()
    timeout = timeout or _env_float("SHERLOCK_TIMEOUT", 150.0, 10.0, 600.0)
    request_timeout = _env_int("SHERLOCK_REQUEST_TIMEOUT", 15, 3, 120)
    sites = _env_list("SHERLOCK_SITES")
    scope = f"sites: {', '.join(sites)}" if sites else "all Sherlock sites"

    command = [
        binary,
        "--csv",
        "--print-found",
        "--no-color",
        "--timeout",
        str(request_timeout),
    ]
    for site in sites:
        command.extend(["--site", site])
    command.append(alias)

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="maltego-sherlock-") as temp_dir:
        directory = Path(temp_dir)
        try:
            stdout, stderr, returncode, duration = await _run_command(
                command,
                directory,
                timeout,
            )
        except AliasSearchError as exc:
            return SearchOutcome(
                engine="Sherlock",
                alias=alias,
                profiles=[],
                duration_seconds=time.monotonic() - started,
                scope=scope,
                command=command,
                error=str(exc),
            )

        profiles, raw_result = _parse_sherlock_csv(directory, alias, stdout)
        error = None
        if returncode != 0 and not profiles:
            error = (
                f"Sherlock завершился с кодом {returncode}: "
                f"{(stderr or stdout).strip()[-500:]}"
            )

        return SearchOutcome(
            engine="Sherlock",
            alias=alias,
            profiles=profiles,
            duration_seconds=duration,
            scope=scope,
            command=command,
            stdout=stdout[:_MAX_RAW_RESULT],
            stderr=stderr[:_MAX_RAW_RESULT],
            error=error,
            raw_result=raw_result[:_MAX_RAW_RESULT],
        )


async def search_maigret(alias: str, timeout: float | None = None) -> SearchOutcome:
    alias = normalize_alias(alias)
    binary = _maigret_binary()
    timeout = timeout or _env_float("MAIGRET_TIMEOUT", 240.0, 20.0, 900.0)
    request_timeout = _env_int("MAIGRET_REQUEST_TIMEOUT", 10, 3, 120)
    top_sites = _env_int("MAIGRET_TOP_SITES", 100, 1, 1000)
    max_connections = _env_int("MAIGRET_MAX_CONNECTIONS", 20, 1, 100)
    sites = _env_list("MAIGRET_SITES")
    scope = (
        f"sites: {', '.join(sites)}"
        if sites
        else f"top {top_sites} sites"
    )

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="maltego-maigret-") as temp_dir:
        directory = Path(temp_dir)
        command = [binary]
        if sites:
            for site in sites:
                command.extend(["--site", site])
        else:
            command.extend(["--top-sites", str(top_sites)])

        command.extend(
            [
                "--no-recursion",
                "--no-progressbar",
                "--no-color",
                "--timeout",
                str(request_timeout),
                "--max-connections",
                str(max_connections),
                "--no-autoupdate",
                "-J",
                "simple",
                "--folderoutput",
                str(directory),
            ]
        )
        if _env_bool("MAIGRET_ENRICH"):
            command.append("--enrich")
        command.append(alias)

        try:
            stdout, stderr, returncode, duration = await _run_command(
                command,
                directory,
                timeout,
            )
        except AliasSearchError as exc:
            return SearchOutcome(
                engine="Maigret",
                alias=alias,
                profiles=[],
                duration_seconds=time.monotonic() - started,
                scope=scope,
                command=command,
                error=str(exc),
            )

        profiles, raw_result = _parse_maigret_json(directory, alias)
        error = None
        if returncode != 0 and not profiles:
            error = (
                f"Maigret завершился с кодом {returncode}: "
                f"{(stderr or stdout).strip()[-500:]}"
            )
        elif not profiles and not raw_result:
            error = (
                "Maigret не создал JSON-отчёт. "
                f"{(stderr or stdout).strip()[-500:]}"
            )

        return SearchOutcome(
            engine="Maigret",
            alias=alias,
            profiles=profiles,
            duration_seconds=duration,
            scope=scope,
            command=command,
            stdout=stdout[:_MAX_RAW_RESULT],
            stderr=stderr[:_MAX_RAW_RESULT],
            error=error,
            raw_result=raw_result[:_MAX_RAW_RESULT],
        )


async def run_alias_search(alias: str) -> list[SearchOutcome]:
    alias = normalize_alias(alias)
    engines = parse_engines()
    tasks = []
    for engine in engines:
        if engine == "sherlock":
            tasks.append(search_sherlock(alias))
        elif engine == "maigret":
            tasks.append(search_maigret(alias))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    outcomes: list[SearchOutcome] = []
    for engine, result in zip(engines, results):
        if isinstance(result, BaseException):
            outcomes.append(
                SearchOutcome(
                    engine=engine.capitalize(),
                    alias=alias,
                    profiles=[],
                    duration_seconds=0.0,
                    scope="unknown",
                    command=[],
                    error=str(result),
                )
            )
        else:
            outcomes.append(result)
    return outcomes


def merge_profiles(outcomes: Iterable[SearchOutcome]) -> list[Profile]:
    merged: dict[str, Profile] = {}
    order: list[str] = []
    for outcome in outcomes:
        for profile in outcome.profiles:
            existing = merged.get(profile.url)
            if existing is None:
                merged[profile.url] = profile
                order.append(profile.url)
            else:
                existing.merge(profile)
    return [merged[url] for url in order]


def limit_profiles(profiles: list[Profile]) -> tuple[list[Profile], bool]:
    limit = _env_int("ALIAS_MAX_PROFILES", 150, 1, 1000)
    if len(profiles) <= limit:
        return profiles, False
    return profiles[:limit], True


def format_profile_note(profile: Profile) -> str:
    lines = [
        f"Site: {profile.site}",
        f"URL: {profile.url}",
        f"Sources: {', '.join(sorted(profile.sources))}",
    ]
    if profile.http_status is not None:
        lines.append(f"HTTP status: {profile.http_status}")
    for key, value in profile.metadata.items():
        if not value:
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def format_summary_note(
    alias: str,
    outcomes: Sequence[SearchOutcome],
    profiles: Sequence[Profile],
    truncated: bool,
) -> str:
    total_duration = sum(outcome.duration_seconds for outcome in outcomes)
    lines = [
        f"Alias: {alias}",
        "Engines:",
    ]
    for outcome in outcomes:
        status = "error" if outcome.error else f"{len(outcome.profiles)} profile(s)"
        lines.append(
            f"- {outcome.engine}: {status}; scope={outcome.scope}; "
            f"{outcome.duration_seconds:.1f}s"
        )

    lines.extend(
        [
            f"Unique profiles: {len(profiles)}",
            f"Total engine time: {total_duration:.1f}s",
        ]
    )
    if truncated:
        lines.append(
            "Result list was truncated by ALIAS_MAX_PROFILES; increase it if needed."
        )

    if profiles:
        lines.append("")
        lines.append("Profiles:")
        for profile in profiles:
            lines.append(f"- {profile.site}: {profile.url}")
            if profile.metadata:
                selected = []
                for key in (
                    "fullname",
                    "location",
                    "company",
                    "bio",
                    "created_at",
                    "follower_count",
                ):
                    value = profile.metadata.get(key)
                    if value:
                        selected.append(f"{key}={value}")
                if selected:
                    lines.append(f"  {', '.join(selected)}")
            sources = ", ".join(sorted(profile.sources))
            if sources:
                lines.append(f"  sources={sources}")

    errors = [outcome for outcome in outcomes if outcome.error]
    if errors:
        lines.append("")
        lines.append("Errors / warnings:")
        for outcome in errors:
            lines.append(f"- {outcome.engine}: {outcome.error}")

    return "\n".join(lines)


def combined_raw_result(outcomes: Sequence[SearchOutcome]) -> str:
    parts = []
    for outcome in outcomes:
        if outcome.raw_result:
            parts.append(f"# {outcome.engine}\n{outcome.raw_result}")
    return "\n\n".join(parts)
