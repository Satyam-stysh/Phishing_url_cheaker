from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from feature_extraction import extract_hostname

LOGGER = logging.getLogger("phishguard.trust")

DEFAULT_TRUSTED_DOMAIN_PATTERNS = (
    "iitm.ac.in",
    "*.iitm.ac.in",
    "*.ac.in",
    "*.edu",
    "*.edu.*",
    "*.gov",
    "*.gov.*",
    "*.gov.in",
)

DEFAULT_TRUST_CONFIG_PATH = Path("data/trusted_domains.txt")


def _normalize_pattern(pattern: str) -> str:
    return pattern.strip().lower()


def _match_domain_pattern(host: str, pattern: str) -> bool:
    normalized = _normalize_pattern(pattern)
    if not normalized:
        return False
    if normalized.startswith("*."):
        suffix = normalized[2:]
        return host == suffix or host.endswith(f".{suffix}")
    return host == normalized


@lru_cache(maxsize=8)
def load_trusted_domain_patterns(config_path: str | None = None) -> tuple[str, ...]:
    patterns = list(DEFAULT_TRUSTED_DOMAIN_PATTERNS)
    override_path = config_path or os.getenv("TRUSTED_DOMAINS_FILE")
    path = Path(override_path) if override_path else DEFAULT_TRUST_CONFIG_PATH
    if not path.exists():
        return tuple(patterns)

    try:
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                patterns.extend(str(item) for item in payload)
        else:
            patterns.extend(
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            )
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Failed to load trusted domain patterns from %s: %s", path, exc)
        return tuple(DEFAULT_TRUSTED_DOMAIN_PATTERNS)

    unique_patterns = []
    seen: set[str] = set()
    for pattern in patterns:
        normalized = _normalize_pattern(pattern)
        if normalized and normalized not in seen:
            unique_patterns.append(normalized)
            seen.add(normalized)
    return tuple(unique_patterns)


def is_whitelisted_domain(
    url: str,
    *,
    config_path: str | None = None,
    patterns: tuple[str, ...] | None = None,
) -> bool:
    host = extract_hostname(url)
    if not host:
        return False
    candidate_patterns = patterns or load_trusted_domain_patterns(config_path)
    return any(_match_domain_pattern(host, pattern) for pattern in candidate_patterns)


def compute_trust_score(
    url: str,
    features: dict[str, Any],
    *,
    config_path: str | None = None,
    patterns: tuple[str, ...] | None = None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    if is_whitelisted_domain(url, config_path=config_path, patterns=patterns):
        score += 1.0
        reasons.append("domain is on the trusted whitelist")
    if int(features.get("is_edu_domain", 0)):
        score += 0.4
        reasons.append("education-domain suffix detected")
    if int(features.get("is_gov_domain", 0)):
        score += 0.45
        reasons.append("government-domain suffix detected")
    if int(features.get("has_institution_keyword", 0)):
        score += min(0.25, 0.08 * float(features.get("institution_keyword_count", 0)))
        reasons.append("institution-related keyword detected")
    if int(features.get("uses_https", 0)):
        score += 0.08
    if int(features.get("has_ip_address", 0)):
        score -= 0.35
    if int(features.get("has_shortener", 0)):
        score -= 0.25
    if int(features.get("is_suspicious_tld", 0)):
        score -= 0.2

    return score, reasons


def apply_trust_adjustment(probability: float, trust_score: float) -> float:
    if trust_score <= 0:
        return probability
    adjusted = probability - min(0.45, trust_score * 0.18)
    return max(0.01, adjusted)


def looks_like_trusted_institutional_url(
    url: str,
    features: dict[str, Any],
    *,
    config_path: str | None = None,
    patterns: tuple[str, ...] | None = None,
) -> bool:
    trust_score, _ = compute_trust_score(url, features, config_path=config_path, patterns=patterns)
    return trust_score >= 0.4
