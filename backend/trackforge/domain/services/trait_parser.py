"""
Version trait parser.

Detects structured traits from track/album title strings like:
- "Song (Live at Wembley)"       -> performance/live
- "Song - Remastered 2011"       -> mastering/remastered
- "Song [Explicit]"              -> content/explicit
- "Song (Acoustic)"              -> arrangement/acoustic
- "Song (Radio Edit)"            -> edit/radio_edit
- "Song (Demo)"                  -> source/demo
- "Song (Someone Remix)"         -> derivation/remix
- "Song (Instrumental)"          -> content/instrumental
- "Album (Deluxe Edition)"       -> packaging/deluxe

Returns a cleaned title and a list of detected traits.
"""

import re
from dataclasses import dataclass


@dataclass
class TraitInfo:
    category: str
    name: str
    source: str  # the matched text that produced this trait


# Each pattern: (regex, category, trait_name)
# Order matters — more specific patterns first
_TRAIT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Remastered (with optional year)
    (re.compile(r"\s*[-–]\s*remaster(?:ed)?\s*(?:\d{4})?\s*$", re.IGNORECASE), "mastering", "remastered"),
    (re.compile(r"\s*\(remaster(?:ed)?\s*(?:\d{4})?\)", re.IGNORECASE), "mastering", "remastered"),
    (re.compile(r"\s*\[remaster(?:ed)?\s*(?:\d{4})?\]", re.IGNORECASE), "mastering", "remastered"),

    # Live
    (re.compile(r"\s*\(live(?:\s+(?:at|in|from)\s+[^)]+)?\)", re.IGNORECASE), "performance", "live"),
    (re.compile(r"\s*\[live(?:\s+(?:at|in|from)\s+[^\]]+)?\]", re.IGNORECASE), "performance", "live"),

    # Acoustic
    (re.compile(r"\s*\(acoustic(?:\s+version)?\)", re.IGNORECASE), "arrangement", "acoustic"),
    (re.compile(r"\s*\[acoustic(?:\s+version)?\]", re.IGNORECASE), "arrangement", "acoustic"),

    # Demo
    (re.compile(r"\s*\(demo(?:\s+\d{4})?\)", re.IGNORECASE), "source", "demo"),
    (re.compile(r"\s*\[demo(?:\s+\d{4})?\]", re.IGNORECASE), "source", "demo"),

    # Radio Edit
    (re.compile(r"\s*\(radio\s+edit\)", re.IGNORECASE), "edit", "radio_edit"),
    (re.compile(r"\s*\[radio\s+edit\]", re.IGNORECASE), "edit", "radio_edit"),

    # Explicit
    (re.compile(r"\s*\[explicit\]", re.IGNORECASE), "content", "explicit"),
    (re.compile(r"\s*\(explicit\)", re.IGNORECASE), "content", "explicit"),

    # Clean
    (re.compile(r"\s*\[clean\]", re.IGNORECASE), "content", "clean"),
    (re.compile(r"\s*\(clean\)", re.IGNORECASE), "content", "clean"),

    # Instrumental
    (re.compile(r"\s*\(instrumental\)", re.IGNORECASE), "content", "instrumental"),
    (re.compile(r"\s*\[instrumental\]", re.IGNORECASE), "content", "instrumental"),

    # Remix — must come after more specific patterns
    (re.compile(r"\s*\(([^)]*\s)?remix\)", re.IGNORECASE), "derivation", "remix"),
    (re.compile(r"\s*\[([^\]]*\s)?remix\]", re.IGNORECASE), "derivation", "remix"),

    # Deluxe Edition (typically on album titles)
    (re.compile(r"\s*\(deluxe(?:\s+edition)?\)", re.IGNORECASE), "packaging", "deluxe"),
    (re.compile(r"\s*\[deluxe(?:\s+edition)?\]", re.IGNORECASE), "packaging", "deluxe"),

    # Expanded Edition
    (re.compile(r"\s*\(expanded(?:\s+edition)?\)", re.IGNORECASE), "packaging", "expanded"),

    # Bonus Track Edition
    (re.compile(r"\s*\((?:with\s+)?bonus\s+tracks?\)", re.IGNORECASE), "packaging", "bonus_tracks"),

    # Anniversary Edition
    (re.compile(r"\s*\(\d+(?:th|st|nd|rd)?\s+anniversary(?:\s+edition)?\)", re.IGNORECASE), "packaging", "anniversary"),

    # Special / Limited Edition
    (re.compile(r"\s*\((?:special|limited)\s+edition\)", re.IGNORECASE), "packaging", "special_edition"),
]


def parse_traits(title: str) -> tuple[str, list[TraitInfo]]:
    """
    Parse a title string for version traits.

    Returns:
        (clean_title, traits) where clean_title has trait suffixes removed
        and traits is a list of TraitInfo objects.
    """
    if not title:
        return title, []

    traits: list[TraitInfo] = []
    clean = title

    for pattern, category, trait_name in _TRAIT_PATTERNS:
        match = pattern.search(clean)
        if match:
            traits.append(TraitInfo(
                category=category,
                name=trait_name,
                source=match.group(0).strip(),
            ))
            clean = clean[:match.start()] + clean[match.end():]

    clean = clean.strip()
    # Remove trailing dash/hyphen left after stripping
    clean = re.sub(r"\s*[-–]+\s*$", "", clean)

    return clean, traits
