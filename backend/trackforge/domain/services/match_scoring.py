"""
Match scoring service.

Provides confidence scoring for matching candidates (NZB results, downloaded files,
Jellyfin items) against target metadata (artist, title, MBID, duration, year, traits).

Reusable across:
- Prowlarr/NZB candidate ranking
- Downloaded file import matching
- Jellyfin library reconciliation
- Admin review suggestions
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from trackforge.domain.services.trait_parser import parse_traits


@dataclass
class MatchTarget:
    """The metadata we're trying to match against."""
    artist: str = ""
    title: str = ""
    mbid: str | None = None
    duration_ms: int | None = None
    year: int | None = None
    traits: list[str] = field(default_factory=list)  # trait names, e.g. ["live", "remastered"]


@dataclass
class MatchCandidate:
    """A candidate that might match the target."""
    artist: str = ""
    title: str = ""
    mbid: str | None = None
    duration_ms: int | None = None
    year: int | None = None
    raw_title: str = ""  # original title before trait stripping


@dataclass
class MatchResult:
    total_score: float  # 0.0 to 1.0
    decision: str  # "auto_accept", "review", "reject"
    components: dict[str, float] = field(default_factory=dict)


# Scoring weights (must sum to 1.0)
WEIGHT_ARTIST = 0.25
WEIGHT_TITLE = 0.25
WEIGHT_MBID = 0.20
WEIGHT_DURATION = 0.15
WEIGHT_YEAR = 0.10
WEIGHT_TRAITS = 0.05

# Decision thresholds
THRESHOLD_AUTO_ACCEPT = 0.90
THRESHOLD_REVIEW = 0.70


def _normalize(s: str) -> str:
    """Lowercase and strip for comparison."""
    return s.strip().lower()


def _string_similarity(a: str, b: str) -> float:
    """Token-sort ratio using SequenceMatcher. Returns 0.0 to 1.0."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # Sort tokens for order-independent matching
    a_sorted = " ".join(sorted(_normalize(a).split()))
    b_sorted = " ".join(sorted(_normalize(b).split()))
    return SequenceMatcher(None, a_sorted, b_sorted).ratio()


def score_match(target: MatchTarget, candidate: MatchCandidate) -> MatchResult:
    """
    Score how well a candidate matches a target.

    Returns a MatchResult with total_score (0.0-1.0), decision, and component breakdown.
    """
    components: dict[str, float] = {}

    # Artist similarity
    components["artist"] = _string_similarity(target.artist, candidate.artist)

    # Title similarity (strip traits from candidate title for fairer comparison)
    candidate_clean_title = candidate.title
    if candidate.raw_title:
        candidate_clean_title, _ = parse_traits(candidate.raw_title)
        if not candidate_clean_title:
            candidate_clean_title = candidate.title

    target_clean, _ = parse_traits(target.title)
    if not target_clean:
        target_clean = target.title

    components["title"] = _string_similarity(target_clean, candidate_clean_title)

    # MBID match (exact or nothing)
    if target.mbid and candidate.mbid:
        components["mbid"] = 1.0 if target.mbid == candidate.mbid else 0.0
    elif not target.mbid and not candidate.mbid:
        components["mbid"] = 0.5  # no data, neutral
    else:
        components["mbid"] = 0.0

    # Duration match (within 30s is full score)
    if target.duration_ms is not None and candidate.duration_ms is not None:
        diff = abs(target.duration_ms - candidate.duration_ms)
        components["duration"] = max(0.0, 1.0 - diff / 30000)
    else:
        components["duration"] = 0.5  # no data, neutral

    # Year proximity (within 5 years is acceptable)
    if target.year is not None and candidate.year is not None:
        diff = abs(target.year - candidate.year)
        components["year"] = max(0.0, 1.0 - diff / 5)
    else:
        components["year"] = 0.5  # no data, neutral

    # Version trait compatibility
    if target.traits:
        candidate_traits = []
        if candidate.raw_title:
            _, parsed = parse_traits(candidate.raw_title)
            candidate_traits = [t.name for t in parsed]

        if candidate_traits:
            matching = len(set(target.traits) & set(candidate_traits))
            total = len(set(target.traits) | set(candidate_traits))
            components["traits"] = matching / total if total > 0 else 0.5
        else:
            # No traits detected in candidate — slight penalty if target has traits
            components["traits"] = 0.3
    else:
        components["traits"] = 0.5  # no target traits, neutral

    # Weighted total
    total = (
        components["artist"] * WEIGHT_ARTIST
        + components["title"] * WEIGHT_TITLE
        + components["mbid"] * WEIGHT_MBID
        + components["duration"] * WEIGHT_DURATION
        + components["year"] * WEIGHT_YEAR
        + components["traits"] * WEIGHT_TRAITS
    )

    # Decision
    if total >= THRESHOLD_AUTO_ACCEPT:
        decision = "auto_accept"
    elif total >= THRESHOLD_REVIEW:
        decision = "review"
    else:
        decision = "reject"

    return MatchResult(
        total_score=round(total, 4),
        decision=decision,
        components={k: round(v, 4) for k, v in components.items()},
    )
