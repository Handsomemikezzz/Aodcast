from __future__ import annotations

from app.domain.common import is_within_days_since, utc_now_iso
from app.domain.memory import (
    MemoryEntry,
    MemoryEvidence,
    MemoryOrigin,
)
from app.orchestration.memory_validation import (
    MAX_BODY,
    MAX_DESCRIPTION,
    MAX_NAME,
)
from app.orchestration.sensitive import contains_forbidden
from app.providers.llm.base import MemoryMergeRequest
from app.providers.llm.factory import build_llm_provider
from app.storage.config_store import ConfigStore
from app.storage.memory_file_store import MemoryFileStore

_MAINTENANCE_INTERVAL_DAYS = 1  # 24h (§17.3)
_MIN_CHANGES = 5
_MIN_TOTAL_AUTO = 10
_FORCE_AT = 180  # hot-index pressure (§17.3)
_MAX_FILES_PER_BATCH = 10  # §17.4
_EVICT_PRESSURE = 180
_MAX_EVICTIONS_PER_BATCH = 5


class MemoryMaintenance:
    """Periodic consolidation: model-driven merge of duplicates + rule-based
    eviction of low-value auto memories, with deterministic gating (§17)."""

    def __init__(self, store: MemoryFileStore, config_store: ConfigStore) -> None:
        self.store = store
        self.config_store = config_store

    # ----------------------------------------------------------------- gating
    def should_run(self) -> bool:
        settings = self.store.load_state().settings
        if settings.changes_since_maintenance <= 0:
            return False  # §17.3: requires content change since last maintenance

        total = self.store.count_entries()
        if total >= _FORCE_AT:
            # Forced by index pressure — but skip if the overflow is entirely
            # non-evictable explicit memory (the hot index already truncates).
            if self.store.count_entries(origin=MemoryOrigin.AUTO) == 0:
                return False
            return True

        last = settings.last_maintenance_at
        if last and is_within_days_since(last, days=_MAINTENANCE_INTERVAL_DAYS):
            return False  # too soon

        return (
            settings.changes_since_maintenance >= _MIN_CHANGES
            or self.store.count_entries(origin=MemoryOrigin.AUTO) >= _MIN_TOTAL_AUTO
        )

    # ------------------------------------------------------------------ batch
    def run_batch(self) -> bool:
        """Run one maintenance batch. Returns True if more work likely remains."""
        provider = build_llm_provider(self.config_store.load_llm_config())
        entries = self.store.list_entries()
        groups = self._group(entries)

        processed_files = 0
        more_remains = False
        for group in groups:
            if len(group) < 2:
                continue
            if processed_files >= _MAX_FILES_PER_BATCH:
                more_remains = True
                break
            try:
                decision = provider.merge_memories(
                    MemoryMergeRequest(entries=[self._index(e) for e in group])
                )
            except Exception:
                # Provider failure on one group must not abort the batch.
                continue
            if not decision.primary_id:
                continue
            if not self._validate_merge(decision, group):
                continue
            self._commit_merge(decision, group)
            processed_files += len(group)

        self._evict_if_pressure()

        if not more_remains:
            self.store.mark_maintained()
        return more_remains

    # --------------------------------------------------------------- grouping
    def _group(self, entries: list[MemoryEntry]) -> list[list[MemoryEntry]]:
        """Greedy clustering by (type, sensitive) with shared-keyword membership.

        Sensitive entries only cluster with other sensitive entries so a merge
        can never downgrade sensitivity.
        """
        clusters: list[list[MemoryEntry]] = []
        for entry in sorted(entries, key=lambda e: e.created_at):
            keywords = {kw.lower() for kw in entry.keywords if kw.strip()}
            placed = False
            for cluster in clusters:
                head = cluster[0]
                if head.type != entry.type or head.sensitive != entry.sensitive:
                    continue
                cluster_keywords = {kw.lower() for c in cluster for kw in c.keywords}
                if keywords & cluster_keywords:
                    cluster.append(entry)
                    placed = True
                    break
            if not placed:
                clusters.append([entry])
        return [cluster for cluster in clusters if len(cluster) >= 2]

    def _index(self, entry: MemoryEntry) -> dict:
        return {
            "id": entry.id,
            "type": entry.type.value,
            "name": entry.name,
            "description": entry.description,
            "body": entry.body,
            "keywords": list(entry.keywords),
            "created_at": entry.created_at,
            "evidence": [{"turn_id": ev.turn_id, "quote": ev.quote} for ev in entry.evidence],
        }

    # ------------------------------------------------------------- validation
    def _validate_merge(self, decision, group: list[MemoryEntry]) -> bool:
        group_ids = {e.id for e in group}
        if decision.primary_id not in group_ids:
            return False
        if any(d not in group_ids for d in decision.drop_ids):
            return False
        if decision.primary_id in decision.drop_ids:
            return False
        if not decision.name.strip() or len(decision.name) > MAX_NAME:
            return False
        if not decision.description.strip() or len(decision.description) > MAX_DESCRIPTION:
            return False
        if not decision.body.strip() or len(decision.body) > MAX_BODY:
            return False
        # §17.5: no fabricated evidence — every turn_id must already exist in the group.
        group_turn_ids = {ev.turn_id for e in group for ev in e.evidence}
        if not decision.evidence_turn_ids:
            return False
        if any(tid not in group_turn_ids for tid in decision.evidence_turn_ids):
            return False
        if contains_forbidden(" ".join([decision.name, decision.description, decision.body])):
            return False
        return True

    # ----------------------------------------------------------------- commit
    def _commit_merge(self, decision, group: list[MemoryEntry]) -> None:
        primary = next((e for e in group if e.id == decision.primary_id), None)
        if primary is None:
            return
        # Gather the full evidence objects for the chosen turn_ids from the group.
        evidence_by_turn: dict[str, MemoryEvidence] = {}
        for entry in group:
            for ev in entry.evidence:
                evidence_by_turn.setdefault(ev.turn_id, ev)
        merged_evidence = [
            evidence_by_turn[tid] for tid in decision.evidence_turn_ids if tid in evidence_by_turn
        ][:3]

        primary.name = decision.name.strip()
        primary.description = decision.description.strip()
        primary.body = decision.body.strip()
        primary.keywords = [kw for kw in decision.keywords if kw.strip()][:12]
        primary.evidence = merged_evidence
        # Merged result keeps explicit origin if any member was explicit (§10.2/§17.5).
        if any(e.origin == MemoryOrigin.EXPLICIT for e in group):
            primary.origin = MemoryOrigin.EXPLICIT
        primary.updated_at = utc_now_iso()

        self.store.save_entry(primary)
        for drop_id in decision.drop_ids:
            self.store.move_to_superseded(drop_id)

    # --------------------------------------------------------------- eviction
    def _evict_if_pressure(self) -> None:
        entries = self.store.list_entries()
        if len(entries) < _EVICT_PRESSURE:
            return
        # §17.6 order: long-unused, then single-evidence, then recently-updated last.
        candidates = [e for e in entries if e.origin == MemoryOrigin.AUTO and not e.sensitive]
        candidates.sort(
            key=lambda e: (e.last_used_at or "", e.source_count, e.updated_at)
        )
        for entry in candidates[:_MAX_EVICTIONS_PER_BATCH]:
            if len(self.store.list_entries()) < _EVICT_PRESSURE:
                break
            # Eviction is capacity hygiene, not a user "forget" — allow re-formation.
            self.store.delete_entry(entry.id, forget=False)
