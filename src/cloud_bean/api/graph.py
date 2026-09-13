"""Graph builder generating node-link topology for fleet visualization."""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import EventType, FleetEvent
from cloud_bean.schemas.finding import Finding


def build_interaction_graph(
    events: List[FleetEvent],
    candidates: Optional[List[CandidateGroup]] = None,
    findings: Optional[List[Finding]] = None,
) -> Dict[str, Any]:
    """Convert events, candidate groups, and findings into node-link graph data."""
    if candidates is None:
        candidates = []
    if findings is None:
        findings = []

    # Map actors to their findings and candidate memberships
    actor_concerning: Dict[str, List[str]] = defaultdict(list)
    for f in findings:
        for actor in f.actors:
            actor_concerning[actor].append(f.pattern.value)

    actor_candidate: Set[str] = set()
    for c in candidates:
        for actor in c.actors:
            actor_candidate.add(actor)

    # Resource statuses: emerging hub, conflict hotspot, or low traffic
    resource_statuses: Dict[str, str] = {}
    for c in candidates:
        if c.trigger_signal == "conflicting_writes":
            for r in c.target_resources:
                resource_statuses[r] = "conflict_hotspot"
        elif c.trigger_signal == "emerging_hub":
            for r in c.target_resources:
                if resource_statuses.get(r) != "conflict_hotspot":
                    resource_statuses[r] = "emerging_hub"

    # Count actor actions and resource interactions
    actor_event_counts: Dict[str, int] = defaultdict(int)
    resource_event_counts: Dict[str, int] = defaultdict(int)
    # (actor, target, edge_type) -> weight
    edge_weights: Dict[tuple, int] = defaultdict(int)

    for e in events:
        actor_id = e.actor_id
        target = e.target
        actor_event_counts[actor_id] += 1
        if target:
            resource_event_counts[target] += 1
            edge_type = "WRITES" if e.event_type == EventType.resource_write else "READS"
            edge_weights[(f"agent:{actor_id}", f"resource:{target}", edge_type)] += 1

    # Build nodes list
    nodes: List[Dict[str, Any]] = []

    # Agent nodes
    for actor_id, count in actor_event_counts.items():
        if actor_id in actor_concerning:
            status = "concerning"
        elif actor_id in actor_candidate:
            status = "candidate"
        else:
            status = "normal"

        nodes.append(
            {
                "id": f"agent:{actor_id}",
                "label": actor_id,
                "type": "agent",
                "status": status,
                "event_count": count,
                "patterns": actor_concerning.get(actor_id, []),
            }
        )

    # Resource nodes
    for target, count in resource_event_counts.items():
        status = resource_statuses.get(target, "low_traffic")
        res_type = "wiki" if target.startswith("wiki:") else "api"
        nodes.append(
            {
                "id": f"resource:{target}",
                "label": target,
                "type": "resource",
                "resource_type": res_type,
                "status": status,
                "event_count": count,
            }
        )

    # Build edges list
    edges: List[Dict[str, Any]] = []

    # Agent -> Resource edges
    for (src, dst, edge_type), weight in edge_weights.items():
        edge_id = f"edge_{src}_{dst}_{edge_type}"
        edges.append(
            {
                "id": edge_id,
                "source": src,
                "target": dst,
                "type": edge_type,
                "weight": weight,
            }
        )

    # Inter-agent conflict and shared artifact edges from candidates
    for c in candidates:
        if c.trigger_signal == "conflicting_writes" and len(c.actors) >= 2:
            sorted_actors = sorted(c.actors)
            for i in range(len(sorted_actors) - 1):
                src = f"agent:{sorted_actors[i]}"
                dst = f"agent:{sorted_actors[i+1]}"
                edge_id = f"conflict_{src}_{dst}_{c.group_id}"
                edges.append(
                    {
                        "id": edge_id,
                        "source": src,
                        "target": dst,
                        "type": "CONFLICTS",
                        "weight": c.metrics.get("rapid_overwrites", 1),
                    }
                )
        elif c.trigger_signal == "shared_artifact_reuse" and len(c.actors) >= 2:
            sorted_actors = sorted(c.actors)
            for i in range(len(sorted_actors) - 1):
                src = f"agent:{sorted_actors[i]}"
                dst = f"agent:{sorted_actors[i+1]}"
                edge_id = f"shared_art_{src}_{dst}_{c.group_id}"
                edges.append(
                    {
                        "id": edge_id,
                        "source": src,
                        "target": dst,
                        "type": "SHARED_ARTIFACT",
                        "weight": c.metrics.get("shared_artifact_matches", 1),
                    }
                )

    return {"nodes": nodes, "edges": edges}
