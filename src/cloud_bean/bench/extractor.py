"""Extraction of top 50 active agents and their real board actions from Collusion Wiki."""

from typing import Any, Dict, List, Optional
from cloud_bean.ingestion.collusion_wiki import CollusionWikiLoader


class TopAgentsExtractor:
    """Extracts top 50 active agent handles and their historical revisions from Collusion Wiki."""

    def __init__(self, loader: Optional[CollusionWikiLoader] = None) -> None:
        self.loader = loader or CollusionWikiLoader()

    def get_top_50_agents(self) -> List[Dict[str, Any]]:
        """Return the top 50 non-human agent labels by revision count."""
        return self.loader.get_top_agents(limit=50)

    def get_agent_history(self, agent_label: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return chronological real revisions saved by this agent."""
        revisions = list(self.loader.iter_revisions(limit=limit, agent=agent_label))
        results = []
        for r in revisions:
            results.append(
                {
                    "revision_id": r["revision_id"],
                    "page_name": r["page_name"],
                    "sequence": r["sequence"],
                    "time": r["time"],
                    "change_summary": r["change_summary"] or "",
                    "body_snippet": (r["body"] or "")[:400],
                    "body_sha256": r["body_sha256"],
                    "body_len": r["body_len"],
                }
            )
        return results

    def extract_full_corpus(self, limit_per_agent: int = 15) -> Dict[str, Dict[str, Any]]:
        """Extract top 50 agent profiles paired with their real board activity."""
        top_agents = self.get_top_50_agents()
        corpus: Dict[str, Dict[str, Any]] = {}

        for profile in top_agents:
            label = profile["label"]
            revisions = self.get_agent_history(label, limit=limit_per_agent)
            corpus[label] = {
                "profile": profile,
                "revisions": revisions,
                "revision_count": len(revisions),
            }

        return corpus
