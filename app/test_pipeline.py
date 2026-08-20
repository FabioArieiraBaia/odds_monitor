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

    # 1. Setup single reference event (BetBurger only ahead 5:4 vs Bet365 4:4)
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

    # 1. Single reference source advancing triggers immediately when freeze_threshold_seconds=0.0
    divergences_single = detector.check_divergences()
    assert len(divergences_single) == 1, "Single advancing reference source triggers when freeze_threshold=0"
    assert divergences_single[0]["match_id"] == "silva vs haddouch"

    # 2. Add second reference source (1xBet also confirms 5:4) -> Dual Validation!
    event_1xbet = NormalizedEvent(
        match_id="silva vs haddouch",
        match_name="Silva vs Haddouch",
        sport="tabletennis",
        source="1xbet",
        set_score="0:0",
        game_score="5:4",
        point_score="0",
        timestamp=now
    )
    cache.update(event_1xbet)

    # Detect dual confirmed divergence
    divergences = detector.check_divergences()
    assert len(divergences) == 1, "Dual confirmation (BetBurger + 1xBet) must maintain alert"
    assert divergences[0]["match_id"] == "silva vs haddouch"
    assert "BET365" in divergences[0]["target_house"]
    assert divergences[0]["priority"] in ("CRITICAL", "HIGH")


def test_home_away_swapped_alignment():
    """Validates that when a reference house lists players in inverted order, scores auto-align."""
    cache = StateCache()
    detector = DivergenceDetector(state_cache=cache, freeze_threshold_seconds=0.0, min_game_difference=1)
    now = datetime.now()

    # Bet365: Silva vs Haddouch | Set 1:0 | Game 8:4
    event_b365 = NormalizedEvent(
        match_id="raw_b365_1",
        match_name="Silva vs Haddouch",
        sport="tabletennis",
        source="bet365",
        set_score="1:0",
        game_score="8:4",
        point_score="0",
        timestamp=now
    )
    cache.update(event_b365)

    # 1xBet: Haddouch vs Silva (SWAPPED!) | Set 0:1 | Game 4:8 (Actual same score!)
    event_1xbet = NormalizedEvent(
        match_id="raw_1x_1",
        match_name="Haddouch vs Silva",
        sport="tabletennis",
        source="1xbet",
        set_score="0:1",
        game_score="4:8",
        point_score="0",
        timestamp=now
    )
    cache.update(event_1xbet)

    # 1xBet event in cache must be automatically flipped to Set 1:0, Game 8:4
    stored_1x = cache.get_event(event_b365.match_id, "1xbet")
    assert stored_1x is not None
    assert stored_1x.set_score == "1:0", f"Expected set 1:0 but got {stored_1x.set_score}"
    assert stored_1x.game_score == "8:4", f"Expected game 8:4 but got {stored_1x.game_score}"

    # No false divergence must occur since both houses are actually on the exact same score
    divergences = detector.check_divergences()
    assert len(divergences) == 0, "Swapped order must be aligned and produce ZERO false divergence"


def test_seven_seconds_freeze_rule():
    """Validates the strict 7.0s freeze rule: no alert under 7s, alert at >= 7s, auto-clear on catch-up."""
    cache = StateCache()
    detector = DivergenceDetector(state_cache=cache, freeze_threshold_seconds=7.0, min_game_difference=1)
    now = datetime.now()

    # Bet365 is at Set 1:1, Game 2:2
    b365_ev = NormalizedEvent(
        match_id="banot vs tyn",
        match_name="Petr Banot vs Daniel Tyn",
        sport="tabletennis",
        source="bet365",
        set_score="1:1",
        game_score="2:2",
        point_score="0",
        timestamp=now
    )
    # 1xBet advances to Game 3:2
    xbet_ev = NormalizedEvent(
        match_id="banot vs tyn",
        match_name="Petr Banot vs Daniel Tyn",
        sport="tabletennis",
        source="1xbet",
        set_score="1:1",
        game_score="3:2",
        point_score="0",
        timestamp=now
    )
    cache.update(b365_ev)
    cache.update(xbet_ev)

    # 1. Immediate cycle: Point is detected, but 0.0s elapsed < 7.0s threshold -> NO ALERT
    alerts = detector.check_divergences()
    assert len(alerts) == 0, "Should not alert immediately (< 7.0s)"

    # Verify event is in active tracking
    active_ev = detector.tracker._active_events.get("banot vs tyn")
    assert active_ev is not None, "Event must be actively tracked"

    # 2. Simulate 5.0 seconds elapsed (< 7.0s) -> NO ALERT
    active_ev.detected_at -= 5.0
    if active_ev.confirmed_at:
        active_ev.confirmed_at -= 5.0
    alerts_5s = detector.check_divergences()
    assert len(alerts_5s) == 0, "Should not alert at 5.0s (< 7.0s)"

    # 3. Simulate 7.1 seconds elapsed (>= 7.0s) -> ALERT FIRES!
    active_ev.detected_at -= 2.2
    if active_ev.confirmed_at:
        active_ev.confirmed_at -= 2.2
    alerts_7s = detector.check_divergences()
    assert len(alerts_7s) == 1, "Alert must fire when Bet365 has been frozen for >= 7.0s"
    assert alerts_7s[0]["match_name"] == "Petr Banot vs Daniel Tyn"
    assert alerts_7s[0]["target_house"] == "BET365"
    assert alerts_7s[0]["delay_seconds"] >= 7.0

    # 4. Bet365 catches up to 3:2 -> Divergence resolves and clears
    b365_synced = NormalizedEvent(
        match_id="banot vs tyn",
        match_name="Petr Banot vs Daniel Tyn",
        sport="tabletennis",
        source="bet365",
        set_score="1:1",
        game_score="3:2",
        point_score="0",
        timestamp=datetime.now()
    )
    cache.update(b365_synced)
    alerts_after_sync = detector.check_divergences()
    assert len(alerts_after_sync) == 0, "Alert must clear when Bet365 catches up"
    assert "banot vs tyn" not in detector.tracker._active_events


