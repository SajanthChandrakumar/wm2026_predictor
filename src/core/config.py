import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# API Keys
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")

# TTL Configs
TOTALS_CACHE_TTL = 3600   # 1h per match
SCORES_CACHE_TTL = 1800   # 30 min — avoids burning quota on repeated manual syncs

# File Paths
MATCHES_CACHE_PATH = os.path.join(DATA_DIR, 'matches_cache.json')
TOTALS_CACHE_PATH = os.path.join(DATA_DIR, 'totals_cache.json')
SCORES_CACHE_PATH = os.path.join(DATA_DIR, 'scores_cache.json')
QUOTA_PATH = os.path.join(DATA_DIR, 'api_quota.json')
QUOTA_ODDS_PATH = os.path.join(DATA_DIR, 'api_quota_odds.json')
H2H_CACHE_PATH = os.path.join(DATA_DIR, 'h2h_cache.json')
LINEUPS_CACHE_PATH = os.path.join(DATA_DIR, 'lineups_cache.json')
FIXTURES_MAP_CACHE_PATH = os.path.join(DATA_DIR, 'fixtures_map_cache.json')
PROCESSED_MATCHES_PATH = os.path.join(DATA_DIR, 'processed_matches.json')
PREDICTION_ARCHIVE_PATH = os.path.join(DATA_DIR, 'prediction_archive.json')
ELO_HISTORY_PATH = os.path.join(DATA_DIR, 'elo_history.json')
ELO_RATINGS_PATH = os.path.join(DATA_DIR, 'elo_ratings.csv')
TEAM_IDS_CACHE_PATH = os.path.join(DATA_DIR, 'team_ids_cache.json')

def get_data_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)
