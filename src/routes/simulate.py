import logging
import time

from fastapi import APIRouter, HTTPException

from src.competitions import collection_for, competition_document_id, find_competition_document, require_competition
from src.services.monte_carlo import simulate_knockout
from src.services.ucl_simulation import simulate_ucl_tournament

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
        if comp.id == "ucl2026":
            return get_ucl_simulation(runs=runs, competition=comp.id)
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

    @router.get("/simulate_ucl")
    def get_ucl_simulation(
        runs: int = 20_000,
        competition: str | None = None,
    ):
        """Run the local UCL simulation from the cache-only fixture snapshot."""
        comp = require_competition(competition)
        if comp.id != "ucl2026":
            raise HTTPException(status_code=400, detail="simulate_ucl requires competition=ucl2026")
        cache_store = collection_for(cache_collection, comp)
        cached = find_competition_document(cache_store, comp, "matches_cache") or {}
        fixtures = cached.get("data") or []
        if not isinstance(fixtures, list):
            return {"status": "unavailable", "reason": "UCL fixture cache is unavailable", "runs": runs, "seed": 20260908}
        teams = cached.get("teams") or sorted({team for fixture in fixtures for team in (fixture.get("home_team"), fixture.get("away_team")) if team})
        matrices = cached.get("score_matrices") or {}
        return simulate_ucl_tournament(teams, fixtures, matrices, n_runs=runs)

    return router
