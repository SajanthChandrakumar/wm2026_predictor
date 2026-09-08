import logging
import time

from fastapi import APIRouter, HTTPException

from src.competitions import collection_for, competition_document_id, find_competition_document, require_competition
from src.services.monte_carlo import simulate_knockout

logger = logging.getLogger(__name__)

_CACHE_ID = "ko_simulation"
_CACHE_TTL = 300  # 5min — Elo ändert sich nur nach einem Sync


def init_router(math_engine, cache_collection):
    router = APIRouter(prefix="/api")

    @router.get("/simulate_knockout")
    def get_knockout_simulation(
        runs: int = 20_000,
        force: bool = False,
        competition: str | None = None,
    ):
        comp = require_competition(competition)
        cache_store = collection_for(cache_collection, comp)
        cache_id = competition_document_id(comp, _CACHE_ID)
        runs = max(1_000, min(runs, 100_000))

        if not force:
            try:
                cached = find_competition_document(cache_store, comp, _CACHE_ID)
                if cached and cached.get("runs") == runs and time.time() - cached.get("timestamp", 0) < _CACHE_TTL:
                    return cached["data"]
            except Exception:
                pass

        math_engine.reload_elo_data()
        elo_df = math_engine.elo_df
        ratings = dict(zip(elo_df["team_name"], elo_df["elo_rating"]))

        try:
            result = simulate_knockout(ratings, n_runs=runs)
        except Exception as e:
            logger.error(f"Monte-Carlo-Simulation fehlgeschlagen: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Simulation fehlgeschlagen")

        try:
            cache_store.update_one(
                {"_id": cache_id},
                {"$set": {"timestamp": time.time(), "runs": runs, "data": result}},
                upsert=True,
            )
        except Exception:
            pass

        return result

    return router
