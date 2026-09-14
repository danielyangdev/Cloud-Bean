"""Ingestion modules for Cloud-Bean."""

from cloud_bean.ingestion.collusion_wiki import CollusionWikiLoader
from cloud_bean.ingestion.dedup import IdempotentEventDeduplicator

__all__ = ["CollusionWikiLoader", "IdempotentEventDeduplicator"]
