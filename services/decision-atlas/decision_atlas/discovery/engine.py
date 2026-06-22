"""Discovery engine.

Crawls every configured connector, normalizes the firehose of events into a
canonical stream, clusters them into distinct *decisions*, derives signals, and
runs the rung-recommendation engine. The output is a live map of decisions
grouped by business domain — ready for a domain owner to annotate and approve.
"""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from typing import Any, Iterable

from ..connectors.base import Connector, build_connector
from ..models import Decision, DecisionEvent, Domain
from ..rung.engine import recommend
from .signals import derive_signals


def _decision_id(domain: str, key: str) -> str:
    h = hashlib.sha1(f"{domain}::{key}".encode()).hexdigest()[:10]
    return f"dec_{h}"


def _humanize(key: str) -> str:
    words = key.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return words.title() if words else key


class DiscoveryEngine:
    def __init__(self, connectors: Iterable[Connector] | None = None) -> None:
        self.connectors: list[Connector] = list(connectors or [])

    @classmethod
    def from_config(cls, config: dict[str, Any],
                    base_dir: str | None = None) -> "DiscoveryEngine":
        """Build an engine from a config dict with a ``sources`` list.

        Relative ``path`` options inside each source spec are resolved against
        ``base_dir`` (typically the directory of the config file) so configs are
        portable.
        """
        specs = config.get("sources") or config.get("connectors") or []
        resolved: list[dict[str, Any]] = []
        for spec in specs:
            spec = dict(spec)
            path = spec.get("path")
            if base_dir and isinstance(path, str) and not os.path.isabs(path):
                spec["path"] = os.path.join(base_dir, path)
            resolved.append(spec)
        return cls([build_connector(spec) for spec in resolved])

    def crawl(self) -> list[DecisionEvent]:
        events: list[DecisionEvent] = []
        for connector in self.connectors:
            events.extend(connector.fetch_events())
        return events

    def discover(self) -> list[Domain]:
        events = self.crawl()
        return self.build_decisions(events)

    # ------------------------------------------------------------------ #

    def build_decisions(self, events: list[DecisionEvent]) -> list[Domain]:
        # Cluster events by (domain, decision_key).
        clusters: dict[tuple[str, str], list[DecisionEvent]] = defaultdict(list)
        for e in events:
            domain = e.domain or "Unassigned"
            clusters[(domain, e.decision_key)].append(e)

        domains: dict[str, Domain] = {}
        for (domain_name, key), cluster in sorted(clusters.items()):
            decision = self._build_one(domain_name, key, cluster)
            domains.setdefault(domain_name, Domain(domain_name)).decisions.append(
                decision
            )

        # Stable, useful ordering: highest-volume decisions first within a domain.
        result = sorted(domains.values(), key=lambda d: d.name.lower())
        for dom in result:
            dom.decisions.sort(key=lambda d: d.event_count, reverse=True)
        return result

    def _build_one(self, domain: str, key: str,
                   cluster: list[DecisionEvent]) -> Decision:
        signals = derive_signals(cluster)
        rec = recommend(signals, event_count=len(cluster))

        sources = sorted({e.source for e in cluster if e.source})
        actors = sorted({e.actor for e in cluster if e.actor})
        roles = [e.role for e in cluster if e.role]
        input_data = sorted({f for e in cluster for f in e.input_fields})

        # Best-guess owner: most frequent role, else most frequent actor.
        owner_role = _most_common(roles)
        owner = _most_common([e.actor for e in cluster if e.actor])

        return Decision(
            id=_decision_id(domain, key),
            key=key,
            name=_humanize(key),
            domain=domain,
            description=(
                f"Auto-discovered from {len(cluster)} events across "
                f"{', '.join(sources) or 'unknown sources'}."
            ),
            owner=owner,
            owner_role=owner_role,
            input_data=input_data,
            sources=sources,
            actors=actors,
            event_count=len(cluster),
            signals=signals,
            recommendation=rec,
            evidence_event_ids=[e.id for e in cluster],
        )


def _most_common(values: list[str]) -> str | None:
    if not values:
        return None
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=counts.get)
