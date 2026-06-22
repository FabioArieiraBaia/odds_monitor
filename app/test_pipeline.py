import pytest
import asyncio
from datetime import datetime
from core.normalizer import NormalizedEvent
from core.state_cache import StateCache
from core.divergence_detector import DivergenceDetector

def test_cache_and_detector():
    cache = StateCache()
    detector = DivergenceDetector(state_cache=cache, freeze_threshold_seconds=2.0, min_game_difference=1)

    now = datetime.now()

    # Setup normal events
    event_burger = NormalizedEvent(
        match_id="silva vs haddouch",
        match_name="Silva vs Haddouch",
        sport="tennis",
        source="betburger",
        set_score="0:0",
        game_score="5:4",
        point_score="40:30",
        timestamp=now
    )

    event_bet365 = NormalizedEvent(
        match_id="silva vs haddouch",
        match_name="Silva vs Haddouch",
        sport="tennis",
        source="bet365",
        set_score="0:0",
        game_score="4:4",
        point_score="0",
        timestamp=now
    )

    cache.update(event_burger)
    cache.update(event_bet365)

    # Detect divergence (game_score diff is 1 set of games: 5 vs 4)
    divergences = detector.check_divergences()
    assert len(divergences) == 1
    assert divergences[0]["match_id"] == "silva vs haddouch"
    assert divergences[0]["game_diff"] == 1
    assert divergences[0]["priority"] == "HIGH"
