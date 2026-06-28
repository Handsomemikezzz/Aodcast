from __future__ import annotations

import hashlib
import json
import re
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

from app.domain.common import is_within_days_since, utc_now_iso
from app.domain.memory import (
    ForgetFingerprint,
    MemoryEntry,
    MemoryEvidence,
    MemoryOrigin,
    MemorySettings,
    MemoryState,
    MemoryType,
    PendingJob,
    WorkerState,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


_HOT_INDEX_LIMIT = 200
_SENSITIVE_PLACEHOLDER = "（敏感背景，未授权时仅提供占位）"


def content_fingerprint(body: str) -> str:
    return hashlib.sha1(body.strip().encode("utf-8")).hexdigest()


class MemoryFileStore:
    """File-native long-term memory store.

    `entries/*.md` is the only source of truth. `catalog.json` and `MEMORY.md`
    are rebuildable indexes. All writes go staging -> lock -> atomic replace ->
    rebuild indexes, mirroring the request-state store's fcntl + atomic pattern.
    """

    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "memory"
        self.entries_dir = self.root / "entries"
        self.superseded_dir = self.root / "superseded"
        self.pending_dir = self.root / "pending"
        self.quarantine_dir = self.root / "quarantine"
        self.staging_dir = self.root / "staging"
        self.state_file = self.root / "state.json"
        self.worker_file = self.root / "worker.json"
        self.forget_file = self.root / "forget.json"
        self.catalog_file = self.root / "catalog.json"
        self.hot_index_file = self.root / "MEMORY.md"
        self.lock_file = self.root / "memory.lock"
        self._thread_lock = threading.RLock()

    # ------------------------------------------------------------------ setup
    def bootstrap(self) -> None:
        for directory in (
            self.root,
            self.entries_dir,
            self.superseded_dir,
            self.pending_dir,
            self.quarantine_dir,
            self.staging_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.state_file.exists():
            self.save_settings(MemorySettings())
        if not self.forget_file.exists():
            self._write_json(self.forget_file, {"fingerprints": []})
        self.rebuild_indexes()

    @contextmanager
    def _locked(self):
        with self._thread_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            if fcntl is None:
                yield
                return
            with self.lock_file.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    # ----------------------------------------------------------------- entries
    def list_entries(
        self, *, type: MemoryType | None = None, search: str | None = None
    ) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for path in sorted(self.entries_dir.glob("mem_*.md")):
            entry = self._read_entry_file(path, quarantine_on_error=False)
            if entry is None:
                continue
            if type is not None and entry.type != type:
                continue
            if search:
                needle = search.strip().lower()
                haystack = " ".join(
                    [entry.name, entry.description, entry.body, " ".join(entry.keywords)]
                ).lower()
                if needle not in haystack:
                    continue
            entries.append(entry)
        entries.sort(key=self._sort_key)
        return entries

    def get_entry(self, memory_id: str) -> MemoryEntry | None:
        path = self.entries_dir / f"{memory_id}.md"
        if not path.is_file():
            return None
        return self._read_entry_file(path, quarantine_on_error=False)

    def save_entry(self, entry: MemoryEntry) -> MemoryEntry:
        entry.updated_at = utc_now_iso()
        markdown = self._entry_to_markdown(entry)
        # Validate roundtrip before committing.
        parsed = self._markdown_to_entry(markdown)
        if parsed is None:
            raise ValueError(f"Refusing to save unparseable memory entry {entry.id}.")
        with self._locked():
            staging_path = self.staging_dir / f"{entry.id}.md"
            self._write_text(staging_path, markdown)
            target = self.entries_dir / f"{entry.id}.md"
            staging_path.replace(target)
            self._rebuild_indexes_unlocked()
        return entry

    def move_to_superseded(self, memory_id: str) -> None:
        with self._locked():
            source = self.entries_dir / f"{memory_id}.md"
            if not source.is_file():
                return
            entry = self._read_entry_file(source, quarantine_on_error=False)
            target = self.superseded_dir / f"{memory_id}.md"
            if entry is not None:
                # Stamp the supersede time so the 30-day GC has an anchor (§15.3).
                entry.superseded_at = utc_now_iso()
                self._write_text(target, self._entry_to_markdown(entry))
                source.unlink(missing_ok=True)
            else:
                source.replace(target)
            self._rebuild_indexes_unlocked()

    def list_superseded(self) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        for path in sorted(self.superseded_dir.glob("mem_*.md")):
            entry = self._read_entry_file(path, quarantine_on_error=False)
            if entry is not None:
                entries.append(entry)
        # Most recently superseded first.
        entries.sort(key=lambda e: _reverse_str(e.superseded_at or ""))
        return entries

    def purge_superseded(self, *, days: int = 30) -> int:
        """Physically delete superseded entries older than `days`, leaving an
        irreversible forget fingerprint (§15.3). Returns the number purged."""
        removed = 0
        with self._locked():
            for path in list(self.superseded_dir.glob("mem_*.md")):
                entry = self._read_entry_file(path, quarantine_on_error=False)
                if entry is None:
                    continue
                stamp = entry.superseded_at
                # Keep entries still inside the window; purge those past it.
                if stamp and is_within_days_since(stamp, days=days):
                    continue
                self._append_forget_unlocked(
                    ForgetFingerprint(
                        content_hash=content_fingerprint(entry.body),
                        turn_ids=[ev.turn_id for ev in entry.evidence if ev.turn_id],
                    )
                )
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def delete_entry(self, memory_id: str, *, forget: bool = True) -> bool:
        with self._locked():
            path = self.entries_dir / f"{memory_id}.md"
            if not path.is_file():
                return False
            entry = self._read_entry_file(path, quarantine_on_error=False)
            # §15.4: episode-delete source removal passes forget=False so the same
            # evidence can rebuild the memory if the episode is restored / re-told.
            if forget and entry is not None:
                self._append_forget_unlocked(
                    ForgetFingerprint(
                        content_hash=content_fingerprint(entry.body),
                        turn_ids=[ev.turn_id for ev in entry.evidence if ev.turn_id],
                    )
                )
            path.unlink(missing_ok=True)
            self._rebuild_indexes_unlocked()
            return True

    def count_entries(self, *, origin: MemoryOrigin | None = None) -> int:
        if origin is None:
            return len(self.list_entries())
        return sum(1 for e in self.list_entries() if e.origin == origin)

    def clear_all(self) -> None:
        with self._locked():
            for directory in (self.entries_dir, self.superseded_dir, self.pending_dir):
                for path in directory.glob("*"):
                    path.unlink(missing_ok=True)
            self.forget_file.unlink(missing_ok=True)
            self._write_json(self.forget_file, {"fingerprints": []})
            self.save_settings(MemorySettings())
            self.save_worker_state(WorkerState())
            self._rebuild_indexes_unlocked()

    # -------------------------------------------------------------------- state
    def load_state(self) -> MemoryState:
        """Settings live in state.json; worker status lives in worker.json so the
        background worker never clobbers user-written settings (and vice versa)."""
        settings_payload = self._read_json(self.state_file)
        worker_payload = self._read_json(self.worker_file)
        state = MemoryState()
        if isinstance(settings_payload, dict):
            # Tolerate the legacy combined shape ({"settings": ..., "worker": ...}).
            if "settings" in settings_payload:
                state = MemoryState.from_dict(settings_payload)
            else:
                state.settings = MemorySettings.from_dict(settings_payload)
        if isinstance(worker_payload, dict):
            state.worker = WorkerState.from_dict(worker_payload)
        return state

    def save_settings(self, settings: MemorySettings) -> None:
        self._write_json(self.state_file, settings.to_dict())

    def save_worker_state(self, worker: WorkerState) -> None:
        self._write_json(self.worker_file, worker.to_dict())

    def note_change(self, n: int = 1) -> None:
        """Count a new/updated memory unit toward the next maintenance gate (§9.2)."""
        with self._locked():
            state = self.load_state()
            state.settings.changes_since_maintenance += n
            self.save_settings(state.settings)

    def mark_maintained(self) -> None:
        with self._locked():
            state = self.load_state()
            state.settings.last_maintenance_at = utc_now_iso()
            state.settings.changes_since_maintenance = 0
            self.save_settings(state.settings)

    # ------------------------------------------------------------------ pending
    def enqueue(self, job: PendingJob) -> PendingJob:
        with self._locked():
            self._write_json(self.pending_dir / f"{job.job_id}.json", job.to_dict())
        return job

    def list_pending(self) -> list[PendingJob]:
        jobs: list[PendingJob] = []
        for path in self.pending_dir.glob("job_*.json"):
            payload = self._read_json(path)
            if isinstance(payload, dict):
                try:
                    jobs.append(PendingJob.from_dict(payload))
                except (KeyError, ValueError):
                    continue
        # Fresh jobs (low retry_count) before repeatedly-failing ones; FIFO within.
        jobs.sort(key=lambda j: (j.retry_count, j.created_at))
        return jobs

    def claim_next(self) -> PendingJob | None:
        jobs = self.list_pending()
        return jobs[0] if jobs else None

    def complete(self, job_id: str) -> None:
        with self._locked():
            (self.pending_dir / f"{job_id}.json").unlink(missing_ok=True)

    def fail(self, job_id: str, error: str) -> None:
        with self._locked():
            path = self.pending_dir / f"{job_id}.json"
            payload = self._read_json(path)
            if not isinstance(payload, dict):
                return
            job = PendingJob.from_dict(payload)
            job.retry_count += 1
            job.last_error = error
            self._write_json(path, job.to_dict())

    def cancel_jobs(self, *, kinds: set[str]) -> int:
        removed = 0
        with self._locked():
            for path in list(self.pending_dir.glob("job_*.json")):
                payload = self._read_json(path)
                if isinstance(payload, dict) and str(payload.get("kind")) in kinds:
                    path.unlink(missing_ok=True)
                    removed += 1
        return removed

    # ------------------------------------------------------------------- forget
    def has_forget_fingerprint(
        self, *, content_hash: str | None = None, turn_ids: list[str] | None = None
    ) -> bool:
        fingerprints = self._load_forget()
        turn_set = set(turn_ids or [])
        for fp in fingerprints:
            if content_hash and fp.content_hash == content_hash:
                return True
            if turn_set and turn_set.intersection(fp.turn_ids):
                return True
        return False

    def _load_forget(self) -> list[ForgetFingerprint]:
        payload = self._read_json(self.forget_file)
        if not isinstance(payload, dict):
            return []
        return [ForgetFingerprint.from_dict(item) for item in payload.get("fingerprints", []) or []]

    def _append_forget_unlocked(self, fingerprint: ForgetFingerprint) -> None:
        fingerprints = self._load_forget()
        fingerprints.append(fingerprint)
        self._write_json(
            self.forget_file, {"fingerprints": [fp.to_dict() for fp in fingerprints]}
        )

    # ------------------------------------------------------------------ indexes
    def rebuild_indexes(self) -> None:
        with self._locked():
            self._rebuild_indexes_unlocked()

    def _rebuild_indexes_unlocked(self) -> None:
        entries: list[MemoryEntry] = []
        for path in sorted(self.entries_dir.glob("mem_*.md")):
            entry = self._read_entry_file(path, quarantine_on_error=True)
            if entry is not None:
                entries.append(entry)
        entries.sort(key=self._sort_key)
        catalog = [self._catalog_row(entry) for entry in entries]
        self._write_json(self.catalog_file, {"entries": catalog})
        self._write_text(self.hot_index_file, self._render_hot_index(entries))

    def _catalog_row(self, entry: MemoryEntry) -> dict[str, object]:
        return {
            "id": entry.id,
            "name": entry.name,
            "description": entry.description,
            "type": entry.type.value,
            "origin": entry.origin.value,
            "sensitive": entry.sensitive,
            "keywords": list(entry.keywords),
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "last_used_at": entry.last_used_at,
            "use_count": entry.use_count,
            "source_count": entry.source_count,
        }

    def _render_hot_index(self, entries: list[MemoryEntry]) -> str:
        lines = ["# MEMORY", ""]
        for entry in entries[:_HOT_INDEX_LIMIT]:
            description = _SENSITIVE_PLACEHOLDER if entry.sensitive else entry.description
            keywords = "" if entry.sensitive else ", ".join(entry.keywords)
            sensitive = "sensitive" if entry.sensitive else "normal"
            lines.append(
                f"{entry.id} | {entry.type.value} | {sensitive} | {entry.name} | {description} | {keywords}"
            )
        return "\n".join(lines) + "\n"

    def _sort_key(self, entry: MemoryEntry) -> tuple:
        # §13.2 deterministic ordering: explicit first, recently used, more
        # sources, recently updated. (Topic-relevance is applied at query time.)
        return (
            0 if entry.origin == MemoryOrigin.EXPLICIT else 1,
            _reverse_str(entry.last_used_at or ""),
            -entry.source_count,
            _reverse_str(entry.updated_at or ""),
        )

    # ------------------------------------------------------------ md (de)serialize
    def _entry_to_markdown(self, entry: MemoryEntry) -> str:
        last_used = entry.last_used_at or ""
        frontmatter = [
            "---",
            f"id: {entry.id}",
            f"name: {_one_line(entry.name)}",
            f"description: {_one_line(entry.description)}",
            f"type: {entry.type.value}",
            f"origin: {entry.origin.value}",
            f"sensitive: {'true' if entry.sensitive else 'false'}",
            f"created_at: {entry.created_at}",
            f"updated_at: {entry.updated_at}",
            f"last_used_at: {last_used}",
            f"use_count: {entry.use_count}",
            f"source_count: {entry.source_count}",
            f"superseded_at: {entry.superseded_at or ''}",
            "---",
        ]
        body_section = ["", "## Memory", "", entry.body.strip(), ""]
        keywords_section = ["## Keywords", "", ", ".join(entry.keywords), ""]
        evidence_lines = ["## Evidence", ""]
        for ev in entry.evidence[:3]:
            evidence_lines.append(f"- session: {ev.session_id}")
            evidence_lines.append(f"  turn: {ev.turn_id}")
            evidence_lines.append(f"  observed_at: {ev.observed_at}")
            evidence_lines.append(f"  quote: {_quote(ev.quote)}")
        return "\n".join(frontmatter + body_section + keywords_section + evidence_lines) + "\n"

    def _markdown_to_entry(self, text: str) -> MemoryEntry | None:
        try:
            front, body_text = _split_frontmatter(text)
            if front is None:
                return None
            sections = _split_sections(body_text)
            payload = {
                "id": front.get("id", ""),
                "name": front.get("name", ""),
                "description": front.get("description", ""),
                "type": front.get("type", ""),
                "origin": front.get("origin", "auto"),
                "sensitive": front.get("sensitive", "false") == "true",
                "created_at": front.get("created_at", utc_now_iso()),
                "updated_at": front.get("updated_at", utc_now_iso()),
                "last_used_at": front.get("last_used_at") or None,
                "use_count": int(front.get("use_count", "0") or "0"),
                "superseded_at": front.get("superseded_at") or None,
                "body": sections.get("Memory", "").strip(),
                "keywords": [
                    kw.strip()
                    for kw in sections.get("Keywords", "").replace("\n", " ").split(",")
                    if kw.strip()
                ],
                "evidence": _parse_evidence(sections.get("Evidence", "")),
            }
            if payload["type"] not in {t.value for t in MemoryType}:
                return None
            if not payload["id"]:
                return None
            return MemoryEntry.from_dict(payload)
        except (KeyError, ValueError):
            return None

    def _read_entry_file(self, path: Path, *, quarantine_on_error: bool) -> MemoryEntry | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        entry = self._markdown_to_entry(text)
        if entry is None and quarantine_on_error:
            self._quarantine(path)
        return entry

    def _quarantine(self, path: Path) -> None:
        try:
            self.quarantine_dir.mkdir(parents=True, exist_ok=True)
            path.replace(self.quarantine_dir / path.name)
        except OSError:
            pass

    # ----------------------------------------------------------------- io utils
    def _read_json(self, path: Path) -> object:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_json(self, path: Path, payload: object) -> None:
        self._write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(text)
                temp_path = handle.name
            Path(temp_path).replace(path)
        finally:
            if temp_path and Path(temp_path).exists():
                Path(temp_path).unlink(missing_ok=True)


def _reverse_str(value: str) -> str:
    # Sort helper: invert each codepoint so a plain ascending sort yields
    # descending order for ISO timestamps without parsing.
    return "".join(chr(0x10FFFF - ord(ch)) for ch in value)


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _quote(value: str) -> str:
    cleaned = _one_line(value).replace('"', "'")
    return f'"{cleaned}"'


def _split_frontmatter(text: str) -> tuple[dict[str, str] | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    front: dict[str, str] = {}
    body_start = len(lines)
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            body_start = index + 1
            break
        raw = lines[index]
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        front[key.strip()] = value.strip()
    else:
        return None, text
    return front, "\n".join(lines[body_start:])


def _split_sections(body_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in body_text.splitlines():
        match = re.match(r"^##\s+(.*)$", line)
        if match:
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = match.group(1).strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return sections


def _parse_evidence(text: str) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- session:"):
            if current:
                evidence.append(current)
            current = {"session_id": stripped[len("- session:"):].strip()}
        elif current is not None and stripped.startswith("turn:"):
            current["turn_id"] = stripped[len("turn:"):].strip()
        elif current is not None and stripped.startswith("observed_at:"):
            current["observed_at"] = stripped[len("observed_at:"):].strip()
        elif current is not None and stripped.startswith("quote:"):
            quote = stripped[len("quote:"):].strip()
            if len(quote) >= 2 and quote[0] == '"' and quote[-1] == '"':
                quote = quote[1:-1]
            current["quote"] = quote
    if current:
        evidence.append(current)
    return evidence[:3]
