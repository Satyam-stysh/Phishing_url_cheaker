from __future__ import annotations

import ipaddress
import re
from collections import Counter
from math import log2
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

SUSPICIOUS_KEYWORDS = (
    "login",
    "secure",
    "verify",
    "bank",
    "account",
    "update",
    "confirm",
    "password",
    "signin",
    "auth",
    "pay",
    "billing",
    "wallet",
    "support",
)
SUSPICIOUS_TLDS = {
    "biz",
    "cc",
    "cn",
    "country",
    "gq",
    "info",
    "link",
    "live",
    "ml",
    "ru",
    "tk",
    "top",
    "work",
    "xyz",
}
EDUCATION_DOMAIN_SUFFIXES = {
    "ac.in",
    "edu",
    "edu.au",
    "edu.br",
    "edu.cn",
    "edu.in",
    "edu.pk",
    "edu.sg",
    "edu.tr",
    "edu.tw",
}
GOVERNMENT_DOMAIN_SUFFIXES = {
    "gov",
    "gov.au",
    "gov.in",
    "gov.uk",
    "govt.nz",
}
SHORTENER_DOMAINS = {
    "bit.ly",
    "cutt.ly",
    "goo.gl",
    "is.gd",
    "ow.ly",
    "rb.gy",
    "rebrand.ly",
    "shorturl.at",
    "t.co",
    "tiny.cc",
    "tinyurl.com",
}
TRUSTED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "google.com",
    "wikipedia.org",
    "github.com",
)
INSTITUTION_KEYWORDS = (
    "academy",
    "college",
    "edu",
    "government",
    "gov",
    "iit",
    "institute",
    "institution",
    "ministry",
    "polytechnic",
    "research",
    "school",
    "university",
)

FEATURE_COLUMNS = [
    "url_length",
    "hostname_length",
    "domain_length",
    "path_length",
    "query_length",
    "fragment_length",
    "num_dots",
    "num_hyphens",
    "num_underscores",
    "num_slashes",
    "num_question_marks",
    "num_equal_signs",
    "num_ampersands",
    "num_digits",
    "digit_ratio",
    "num_letters",
    "letter_ratio",
    "num_special_chars",
    "special_char_ratio",
    "has_at",
    "has_tilde",
    "has_percent_encoding",
    "has_double_slash_in_path",
    "has_https_token_in_host_or_path",
    "num_subdomains",
    "subdomain_count",
    "uses_https",
    "has_ip_address",
    "has_port",
    "has_punycode",
    "has_shortener",
    "is_edu_domain",
    "is_gov_domain",
    "tld_length",
    "is_suspicious_tld",
    "hostname_entropy",
    "path_entropy",
    "query_param_count",
    "num_suspicious_keywords",
    "num_suspicious_keywords_host",
    "num_suspicious_keywords_path",
    "has_institution_keyword",
    "institution_keyword_count",
]


def _normalize_url(url: str) -> str:
    value = str(url).strip()
    if not value:
        return value
    if "://" not in value:
        return "http://" + value
    return value


def extract_hostname(url: str) -> str:
    normalized = _normalize_url(url)
    parsed = urlparse(normalized)
    return parsed.netloc.split("@")[-1].split(":")[0].lower()


def extract_registered_domain(host: str) -> str:
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)

    suffix = ".".join(labels[-2:])
    if suffix in {"ac.in", "gov.in", "edu.in"} and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_trusted_domain(url: str) -> bool:
    host = extract_hostname(url)
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in TRUSTED_DOMAINS)


def extract_url_features(url: str) -> dict[str, int]:
    raw = str(url)
    normalized = _normalize_url(raw)
    parsed = urlparse(normalized)
    host = extract_hostname(raw)
    host_without_port = parsed.netloc.split("@")[-1]
    has_port = int(":" in host_without_port and not host_without_port.endswith("]"))
    path = parsed.path or ""
    query = parsed.query or ""
    fragment = parsed.fragment or ""
    lower_url = raw.lower()
    lower_host = host.lower()
    lower_path = path.lower()
    registered_domain = extract_registered_domain(host)

    labels = [label for label in host.split(".") if label]
    num_subdomains = max(len(labels) - 2, 0)
    tld = labels[-1] if labels else ""
    num_digits = sum(ch.isdigit() for ch in raw)
    num_letters = sum(ch.isalpha() for ch in raw)
    num_special_chars = sum(not ch.isalnum() for ch in raw)
    raw_length = max(len(raw), 1)
    query_param_count = len(parse_qs(query, keep_blank_values=True))
    institution_keyword_count = _keyword_count(lower_url, INSTITUTION_KEYWORDS)
    host_suffix = ".".join(labels[-2:]) if len(labels) >= 2 else tld
    host_suffix_3 = ".".join(labels[-3:]) if len(labels) >= 3 else host_suffix
    is_edu_domain = int(
        host_suffix in EDUCATION_DOMAIN_SUFFIXES
        or host_suffix_3 in EDUCATION_DOMAIN_SUFFIXES
        or lower_host.endswith(".edu")
        or lower_host.endswith(".ac.in")
        or lower_host.endswith(".edu.in")
    )
    is_gov_domain = int(
        host_suffix in GOVERNMENT_DOMAIN_SUFFIXES
        or host_suffix_3 in GOVERNMENT_DOMAIN_SUFFIXES
        or lower_host.endswith(".gov")
        or lower_host.endswith(".gov.in")
    )

    return {
        "url_length": len(raw),
        "hostname_length": len(host),
        "domain_length": len(registered_domain),
        "path_length": len(path),
        "query_length": len(query),
        "fragment_length": len(fragment),
        "num_dots": raw.count("."),
        "num_hyphens": raw.count("-"),
        "num_underscores": raw.count("_"),
        "num_slashes": raw.count("/"),
        "num_question_marks": raw.count("?"),
        "num_equal_signs": raw.count("="),
        "num_ampersands": raw.count("&"),
        "num_digits": num_digits,
        "digit_ratio": num_digits / raw_length,
        "num_letters": num_letters,
        "letter_ratio": num_letters / raw_length,
        "num_special_chars": num_special_chars,
        "special_char_ratio": num_special_chars / raw_length,
        "has_at": int("@" in raw),
        "has_tilde": int("~" in raw),
        "has_percent_encoding": int("%" in raw),
        "has_double_slash_in_path": int("//" in path),
        "has_https_token_in_host_or_path": int("https" in lower_host or "https" in lower_path),
        "num_subdomains": num_subdomains,
        "subdomain_count": num_subdomains,
        "uses_https": int(parsed.scheme.lower() == "https"),
        "has_ip_address": _contains_ip(host),
        "has_port": has_port,
        "has_punycode": int("xn--" in lower_host),
        "has_shortener": int(any(lower_host == domain or lower_host.endswith(f".{domain}") for domain in SHORTENER_DOMAINS)),
        "is_edu_domain": is_edu_domain,
        "is_gov_domain": is_gov_domain,
        "tld_length": len(tld),
        "is_suspicious_tld": int(tld in SUSPICIOUS_TLDS),
        "hostname_entropy": _shannon_entropy(lower_host),
        "path_entropy": _shannon_entropy(lower_path),
        "query_param_count": query_param_count,
        "num_suspicious_keywords": _suspicious_keyword_count(lower_url),
        "num_suspicious_keywords_host": _suspicious_keyword_count(lower_host),
        "num_suspicious_keywords_path": _suspicious_keyword_count(lower_path),
        "has_institution_keyword": int(institution_keyword_count > 0),
        "institution_keyword_count": institution_keyword_count,
    }


def extract_features_for_series(url_series: pd.Series) -> pd.DataFrame:
    rows = [extract_url_features(url) for url in url_series.astype(str)]
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS)


def infer_label_column(df: pd.DataFrame) -> str:
    candidates = ["label", "target", "class", "is_phishing", "phishing"]
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(
        f"Could not find label column. Tried {candidates}. "
        f"Available columns: {list(df.columns)}"
    )


def infer_url_column(df: pd.DataFrame) -> str:
    candidates = ["url", "URL", "link", "domain"]
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(
        f"Could not find URL column. Tried {candidates}. "
        f"Available columns: {list(df.columns)}"
    )


def normalize_labels(y: pd.Series, phishing_label: str | int | None = None) -> np.ndarray:
    lowered = y.astype(str).str.strip().str.lower()
    if phishing_label is not None:
        normalized_positive = str(phishing_label).strip().lower()
        observed_values = sorted(set(lowered.tolist()))
        if normalized_positive not in observed_values:
            raise ValueError(
                f"Configured phishing label {phishing_label!r} was not found. "
                f"Observed labels: {observed_values}"
            )
        if len(observed_values) != 2:
            raise ValueError(
                "Expected a binary label column when using --phishing-label. "
                f"Observed labels: {observed_values}"
            )
        return (lowered == normalized_positive).to_numpy(dtype=int)

    mapping = {
        "1": 1,
        "0": 0,
        "phishing": 1,
        "legitimate": 0,
        "safe": 0,
        "malicious": 1,
        "true": 1,
        "false": 0,
    }
    mapped = lowered.map(mapping)
    if mapped.isnull().any():
        bad_values = sorted(set(lowered[mapped.isnull()].tolist()))
        raise ValueError(
            f"Found unmapped label values: {bad_values}. "
            "Use binary labels (0/1) or supported strings."
        )
    return mapped.to_numpy(dtype=int)


def _contains_ip(host: str) -> int:
    if not host:
        return 0
    candidate = host.strip("[]")
    try:
        ipaddress.ip_address(candidate)
        return 1
    except ValueError:
        return 0


def _suspicious_keyword_count(url_lower: str) -> int:
    return _keyword_count(url_lower, SUSPICIOUS_KEYWORDS)


def _keyword_count(url_lower: str, keywords: tuple[str, ...]) -> int:
    tokens = re.findall(r"[a-z]+", url_lower)
    return int(sum(1 for token in tokens if token in keywords))


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    total = len(value)
    return float(-sum((count / total) * log2(count / total) for count in counts.values()))
