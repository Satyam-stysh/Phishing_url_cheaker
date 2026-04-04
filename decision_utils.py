from __future__ import annotations

from typing import Any

from feature_extraction import is_trusted_domain
from trust_layer import apply_trust_adjustment, compute_trust_score, is_whitelisted_domain


def suspicious_signal_score(features: dict[str, Any]) -> int:
    score = 0
    score += int(features.get("has_at", 0)) * 4
    score += int(features.get("has_ip_address", 0)) * 4
    score += int(features.get("has_punycode", 0)) * 3
    score += int(features.get("has_shortener", 0)) * 3
    score += int(features.get("has_double_slash_in_path", 0)) * 3
    score += int(features.get("has_https_token_in_host_or_path", 0)) * 2
    score += int(features.get("is_suspicious_tld", 0)) * 2
    score += min(int(features.get("num_suspicious_keywords_host", 0)), 2) * 2
    score += min(int(features.get("num_suspicious_keywords_path", 0)), 2)
    score += int(features.get("path_length", 0) >= 24)
    score += int(features.get("num_slashes", 0) >= 5)
    score += int(features.get("has_percent_encoding", 0))
    score += int(features.get("has_port", 0))
    score += int(features.get("num_subdomains", 0) >= 3)
    score += int(not features.get("uses_https", 0))
    return score


def decide_prediction(
    url: str,
    probability: float,
    threshold: float,
    features: dict[str, Any],
) -> tuple[str, float, float, int, str | None]:
    score = suspicious_signal_score(features)
    trust_score, trust_reasons = compute_trust_score(url, features)
    adjusted_probability = apply_trust_adjustment(probability, trust_score)
    has_no_red_flags = (
        score == 0
        and int(features.get("uses_https", 0)) == 1
        and int(features.get("num_suspicious_keywords", 0)) == 0
        and int(features.get("has_ip_address", 0)) == 0
        and int(features.get("has_shortener", 0)) == 0
        and int(features.get("is_suspicious_tld", 0)) == 0
    )

    if is_whitelisted_domain(url):
        return "safe", min(adjusted_probability, 0.03), max(1.0 - adjusted_probability, 0.97), min(int(round(adjusted_probability * 100)), 3), (
            "Trusted-domain whitelist override applied"
        )

    if is_trusted_domain(url):
        return "safe", min(adjusted_probability, 0.05), max(1.0 - adjusted_probability, 0.95), min(int(round(adjusted_probability * 100)), 5), (
            "Trusted domain safeguard applied"
        )

    if score >= 4 and adjusted_probability >= 0.25:
        return "phishing", max(adjusted_probability, 0.9), max(adjusted_probability, 0.9), max(int(round(adjusted_probability * 100)), 90), (
            "Multiple URL-level phishing signals detected"
        )

    if adjusted_probability >= max(threshold, 0.9):
        reason = "High model confidence supported by suspicious URL structure"
        if score == 0:
            reason = "High model confidence despite limited handcrafted URL red flags"
        if trust_reasons:
            reason = f"{reason}; trust layer noted " + ", ".join(trust_reasons)
        return "phishing", adjusted_probability, adjusted_probability, int(round(adjusted_probability * 100)), (
            reason
        )

    if adjusted_probability >= threshold:
        reason = None if score >= 2 else "Model probability exceeded threshold even though heuristic red flags were limited"
        if reason and trust_reasons:
            reason = f"{reason}; trust layer noted " + ", ".join(trust_reasons)
        return "phishing", adjusted_probability, adjusted_probability, int(round(adjusted_probability * 100)), reason

    if has_no_red_flags:
        reason = "No strong phishing signals detected in the URL"
        if trust_reasons:
            reason = f"{reason}; trust layer noted " + ", ".join(trust_reasons)
        return "safe", min(adjusted_probability, 0.1), max(1.0 - adjusted_probability, 0.9), min(int(round(adjusted_probability * 100)), 10), (
            reason
        )

    reason = "Model score was overridden because URL-level phishing signals were weak"
    if trust_reasons:
        reason = f"{reason}; trust layer noted " + ", ".join(trust_reasons)
    return "safe", min(adjusted_probability, 0.35), max(1.0 - adjusted_probability, 0.7), min(int(round(adjusted_probability * 100)), 35), (
        reason
    )

    
