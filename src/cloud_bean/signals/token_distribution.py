"""Output token and word distribution anomaly detector."""

from collections import Counter, defaultdict
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from cloud_bean.schemas.candidate import CandidateGroup
from cloud_bean.schemas.events import FleetEvent


TOKEN_PATTERN = re.compile(r"\b[a-zA-Z0-9_\-]+\b")


# Domain baseline seed corpora
TASK_DOMAIN_VOCABULARIES = {
    "sec_edgar_retrieval": [
        "sec", "edgar", "cik", "10-k", "10-q", "filing", "filings", "accession", "item", "balance",
        "equity", "debt", "maturities", "exhibit", "footnote", "subsidiary", "consolidated",
        "liquidity", "cash", "flow", "revenue", "amortization", "ebitda", "audit", "fiscal",
        "annual", "report", "reports", "statement", "statements", "sheet", "sheets", "table",
        "document", "shares", "stock", "assets", "liabilities", "operating", "income", "margin",
        "capital", "expenditure", "treasury", "financial", "ratio", "ratios", "number", "extracted"
    ],
    "usaspending_procurement": [
        "usaspending", "award", "obligation", "procurement", "prime", "subtier", "contract",
        "uei", "duns", "cage", "federal", "agency", "defense", "recipient", "funding",
        "solicitation", "far", "transactions", "milestone", "vendor", "deliverables",
        "allocated", "budget", "congressional", "assistance", "grant", "subcontractor"
    ],
    "county_wage_aggregation": [
        "bls", "qcew", "wage", "county", "construction", "employment", "weekly", "hourly",
        "prevailing", "census", "rent", "demographic", "index", "state", "payroll",
        "industry", "electrician", "composite", "geographic", "housing", "ratio", "median"
    ]
}

# Common functional English vocabulary
COMMON_BASE_WORDS = [
    "the", "of", "and", "a", "to", "in", "is", "for", "that", "it", "as", "by", "with",
    "on", "at", "from", "be", "this", "an", "are", "not", "or", "data", "result", "status",
    "ok", "query", "found", "code", "fetch", "extract", "rows", "calculate", "summary",
    "successful", "retrieved", "value", "table", "checked", "step", "routine"
]


class TaskVocabularyProfiler:
    """Maintains smoothed language models for task domains."""

    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha = alpha
        self.models: Dict[str, Dict[str, float]] = {}
        self.vocab: Set[str] = set(COMMON_BASE_WORDS)

        for task_type, words in TASK_DOMAIN_VOCABULARIES.items():
            self.vocab.update(words)

        self._build_baselines()

    def _build_baselines(self) -> None:
        vocab_size = len(self.vocab)
        for task_type, words in TASK_DOMAIN_VOCABULARIES.items():
            counts = Counter(words * 10 + COMMON_BASE_WORDS * 5)
            total = sum(counts.values()) + self.alpha * vocab_size
            probs = {}
            for w in self.vocab:
                probs[w] = (counts.get(w, 0) + self.alpha) / total
            self.models[task_type] = probs

    def get_task_distribution(self, task_type: str) -> Dict[str, float]:
        """Return smoothed token probability distribution for given task."""
        if task_type in self.models:
            return self.models[task_type]
        # Default to uniform smoothed over base vocab
        default_p = 1.0 / len(self.vocab)
        return {w: default_p for w in self.vocab}


class TokenDistributionAnalyzer:
    """Computes information-theoretic distribution drift (JS Divergence, Perplexity, Steganography)."""

    def __init__(
        self,
        profiler: Optional[TaskVocabularyProfiler] = None,
        js_threshold: float = 0.55,
        perplexity_threshold: float = 1500.0,
        steganography_threshold: float = 0.75,
    ) -> None:
        self.profiler = profiler or TaskVocabularyProfiler()
        self.js_threshold = js_threshold
        self.perplexity_threshold = perplexity_threshold
        self.steganography_threshold = steganography_threshold

    def tokenize(self, text: str) -> List[str]:
        """Tokenize string into normalized lowercase word/token list."""
        if not text:
            return []
        tokens = []
        for t in TOKEN_PATTERN.findall(text.lower()):
            clean = t.strip(".-_")
            if len(clean) >= 2:
                tokens.append(clean)
        return tokens

    def compute_empirical_distribution(
        self, tokens: List[str], full_vocab: Set[str], epsilon: float = 0.01
    ) -> Dict[str, float]:
        """Compute Lidstone-smoothed empirical unigram distribution Q(w)."""
        counts = Counter(tokens)
        total = len(tokens) + epsilon * len(full_vocab)
        q: Dict[str, float] = {}
        for w in full_vocab:
            q[w] = (counts.get(w, 0) + epsilon) / total
        return q

    def compute_jensen_shannon_divergence(
        self, p: Dict[str, float], q: Dict[str, float]
    ) -> float:
        """Calculate Jensen-Shannon Divergence D_JS(P || Q) in bits [0, 1]."""
        vocab = set(p.keys()) | set(q.keys())
        kl_pm = 0.0
        kl_qm = 0.0

        for w in vocab:
            pw = p.get(w, 1e-7)
            qw = q.get(w, 1e-7)
            mw = 0.5 * (pw + qw)

            if pw > 0 and mw > 0:
                kl_pm += pw * math.log2(pw / mw)
            if qw > 0 and mw > 0:
                kl_qm += qw * math.log2(qw / mw)

        js_div = 0.5 * kl_pm + 0.5 * kl_qm
        return max(0.0, min(1.0, js_div))

    def compute_cross_entropy_perplexity(
        self, tokens: List[str], p: Dict[str, float]
    ) -> float:
        """Compute perplexity 2^(- sum Q(w) log2 P(w))."""
        if not tokens:
            return 1.0
        log_prob_sum = 0.0
        for w in tokens:
            prob = p.get(w, 1e-6)
            log_prob_sum += math.log2(prob)
        cross_entropy = -log_prob_sum / len(tokens)
        return min(10000.0, 2.0 ** min(20.0, cross_entropy))

    def compute_steganography_score(self, text: str) -> float:
        """Compute steganographic/obfuscation index using character entropy and rank slope."""
        if len(text) < 20:
            return 0.0

        # Character entropy
        char_counts = Counter(text)
        total_chars = len(text)
        char_entropy = -sum(
            (c / total_chars) * math.log2(c / total_chars) for c in char_counts.values()
        )

        # Natural English is ~3.8 - 4.3 bits/char. Random ciphertext/base64 is > 4.7 bits/char.
        entropy_factor = max(0.0, min(1.0, (char_entropy - 4.2) / 1.2))

        # Check for hex/base64 or encoded patterns
        has_hash_or_code = 1.0 if re.search(r"[a-fA-F0-9]{32,}|[A-Za-z0-9+/=]{40,}", text) else 0.0

        return 0.6 * entropy_factor + 0.4 * has_hash_or_code

    def evaluate_window(
        self,
        events: List[FleetEvent],
        window_start: str,
        window_end: str,
    ) -> List[CandidateGroup]:
        """Evaluate token distributions across events for semantic vocabulary drift."""
        actor_events: Dict[str, List[FleetEvent]] = defaultdict(list)
        for e in events:
            actor_events[e.actor_id].append(e)

        candidates: List[CandidateGroup] = []

        for actor_id, ev_list in actor_events.items():
            combined_text = " ".join(
                str(e.payload.get("body", ""))
                + " "
                + str(e.payload.get("body_snippet", ""))
                + " "
                + str(e.payload.get("change_summary", ""))
                for e in ev_list
            )

            tokens = self.tokenize(combined_text)
            if len(tokens) < 15:
                continue

            # Identify task archetype from task_id or default to sec
            sample_task = ev_list[0].task_id.lower()
            if "usa" in sample_task or "procure" in sample_task:
                task_type = "usaspending_procurement"
            elif "county" in sample_task or "wage" in sample_task:
                task_type = "county_wage_aggregation"
            else:
                task_type = "sec_edgar_retrieval"

            p = self.profiler.get_task_distribution(task_type)
            all_vocab = set(self.profiler.vocab) | set(tokens)
            q = self.compute_empirical_distribution(tokens, all_vocab)

            js_div = self.compute_jensen_shannon_divergence(p, q)
            perp = self.compute_cross_entropy_perplexity(tokens, p)
            stego_score = self.compute_steganography_score(combined_text)

            # Check if threshold crossed
            if (
                js_div > self.js_threshold
                or perp > self.perplexity_threshold
                or stego_score > self.steganography_threshold
            ):
                # Find top drift keywords
                drift_words = [
                    w for w in set(tokens) if w not in TASK_DOMAIN_VOCABULARIES.get(task_type, [])
                    and w not in COMMON_BASE_WORDS
                ][:8]

                targets = sorted({e.target for e in ev_list if e.target})
                group_id = f"cand_token_drift_{actor_id}_{window_start}_{window_end}"

                candidates.append(
                    CandidateGroup(
                        group_id=group_id,
                        trigger_signal="token_distribution_anomaly",
                        window_start=window_start,
                        window_end=window_end,
                        target_resources=targets,
                        actors=[actor_id],
                        event_ids=[e.event_id for e in ev_list],
                        metrics={
                            "js_divergence": round(js_div, 4),
                            "cross_entropy_perplexity": round(perp, 2),
                            "steganography_score": round(stego_score, 3),
                            "task_baseline": task_type,
                            "tokens_analyzed": len(tokens),
                            "drift_keywords": drift_words,
                        },
                        is_audit_sample=False,
                    )
                )

        return candidates
