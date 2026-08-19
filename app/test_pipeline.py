import pytest
import time
from datetime import datetime
from core.normalizer import NormalizedEvent
from core.state_cache import StateCache
from core.divergence_detector import DivergenceDetector

def test_cache_and_detector():
    cache = StateCache()
    # 0.0s delay so divergence fires immediately in test
    detector = DivergenceDetector(state_cache=cache, freeze_threshold_seconds=0.0, min_game_difference=1)

    now = datetime.now()

    # Setup reference event with score ahead (5:4) vs Bet365 (4:4)
    event_burger = NormalizedEvent(
        match_id="silva vs haddouch",
        match_name="Silva vs Haddouch",
        sport="tabletennis",
        source="betburger",
        set_score="0:0",
        game_score="5:4",
        point_score="0",
        timestamp=now
    )

    event_bet365 = NormalizedEvent(
        match_id="silva vs haddouch",
        match_name="Silva vs Haddouch",
        sport="tabletennis",
        source="bet365",
        set_score="0:0",
        game_score="4:4",
        point_score="0",
        timestamp=now
    )

    cache.update(event_burger)
    cache.update(event_bet365)

    # Detect divergence
    divergences = detector.check_divergences()
    assert len(divergences) == 1
    assert divergences[0]["match_id"] == "silva vs haddouch"
    assert "BET365" in divergences[0]["target_house"]
    assert divergences[0]["priority"] in ("CRITICAL", "HIGH")
