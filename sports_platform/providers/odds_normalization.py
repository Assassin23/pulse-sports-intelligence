"""
Odds normalization and change fingerprinting utility — Milestone 7.

Ensures all odds providers (API-Football, CricAPI, Betfair, etc.) map to canonical
market types, outcome labels, and decimal odds format for storage and display.
Computes SHA-256 fingerprints to avoid storing or broadcasting unchanged odds.
"""
import hashlib
import json
from typing import Any, Dict, List, Union


MARKET_TYPE_MAP = {
    # Football markets
    "Match Winner": "match_winner",
    "1X2": "match_winner",
    "Full Time Result": "match_winner",
    "Moneyline": "match_winner",
    "Asian Handicap": "handicap",
    "Handicap": "handicap",
    "AH": "handicap",
    "Goals Over/Under": "over_under",
    "Over/Under": "over_under",
    "OU": "over_under",
    "Both Teams Score": "both_teams_to_score",
    "BTTS": "both_teams_to_score",
    # Cricket markets
    "Match Winner 2-Way": "match_winner",
    "To Win The Match": "match_winner",
    "Top Batsman": "top_batsman",
    "Total Match Sixes": "over_under_sixes",
    # Tennis markets
    "Match Betting": "match_winner",
    "Set Betting": "set_betting",
    "Total Games": "total_games",
}

OUTCOME_LABEL_MAP = {
    "match_winner": {
        "Home": "home_win",
        "Away": "away_win",
        "Draw": "draw",
        "1": "home_win",
        "2": "away_win",
        "X": "draw",
        "Tie": "draw",
    },
    "over_under": {
        "Over": "over",
        "Under": "under",
        "O": "over",
        "U": "under",
    },
    "both_teams_to_score": {
        "Yes": "yes",
        "No": "no",
    },
}


def normalize_market_type(raw_market: str) -> str:
    """Map provider market string to canonical market key."""
    cleaned = raw_market.strip()
    return MARKET_TYPE_MAP.get(cleaned, cleaned.lower().replace(" ", "_").replace("/", "_"))


def normalize_outcome_label(market_type: str, raw_label: str) -> str:
    """Map provider outcome string to canonical outcome label."""
    market_labels = OUTCOME_LABEL_MAP.get(market_type, {})
    return market_labels.get(raw_label.strip(), raw_label.strip().lower().replace(" ", "_"))


def normalize_odds_value(value: Union[float, int, str], odds_format: str = "decimal") -> float:
    """
    Convert all odds values to decimal representation rounded to 2 decimal places.
    - Decimal: e.g. 1.85
    - Fractional: e.g. '9/4' -> 3.25
    - American: e.g. '+250' -> 3.50, '-150' -> 1.67
    """
    if odds_format == "fractional":
        val_str = str(value).strip()
        if "/" in val_str:
            num, den = val_str.split("/")
            return round((float(num) / float(den)) + 1.0, 2)
    elif odds_format == "american":
        num_val = float(value)
        if num_val > 0:
            return round((num_val / 100.0) + 1.0, 2)
        elif num_val < 0:
            return round((100.0 / abs(num_val)) + 1.0, 2)

    return round(float(value), 2)


def compute_odds_fingerprint(outcomes: List[Dict[str, Any]]) -> str:
    """
    Calculate deterministic SHA-256 fingerprint for a list of odds outcomes.
    Ensures identical odds produce identical hashes for change detection.
    """
    sorted_outcomes = sorted(outcomes, key=lambda x: str(x.get("outcome", x.get("label", ""))))
    canonical = json.dumps(sorted_outcomes, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
