TEAM_MAPPING = {
    "United States": "United States", "USA": "United States",
    "Korea Republic": "South Korea", "South Korea": "South Korea",
    "Czech Republic": "Czech Republic", "Czechia": "Czech Republic",
    "IR Iran": "Iran", "Côte d'Ivoire": "Ivory Coast", "Ivory Coast": "Ivory Coast",
    "Saudi Arabia": "Saudi Arabia", "KSA": "Saudi Arabia",
    "Turkey": "Türkiye", "Türkiye": "Türkiye",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina"
}

DISPLAY_MAPPING = {
    "United States": "USA", "USA": "USA",
    "South Korea": "South Korea", "Korea Republic": "South Korea",
    "Iran": "Iran", "IR Iran": "Iran",
    "Czech Republic": "Czech Republic", "Czechia": "Czech Republic",
    "Ivory Coast": "Ivory Coast", "Côte d'Ivoire": "Ivory Coast",
}

TOTALS_CACHE_TTL = 3600   # 1h per match
SCORES_CACHE_TTL = 1800   # 30 min — avoids burning quota on repeated manual syncs

_KO_ROUND_KEYWORDS = {"round of 16", "quarter", "semi", "final", "3rd place"}


def _is_ko_round(round_str: str) -> bool:
    if not round_str:
        return False
    lower = round_str.lower()
    return any(kw in lower for kw in _KO_ROUND_KEYWORDS)
