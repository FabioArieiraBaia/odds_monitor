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

    # 1. Setup single reference event (BetBurger only ahead 6:4 vs Bet365 4:4 - gap 2)
    event_burger = NormalizedEvent(
        match_id="silva vs haddouch",
        match_name="Silva vs Haddouch",
        sport="tabletennis",
        source="betburger",
        set_score="0:0",
        game_score="6:4",
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

    # 1. Single reference source (BetBurger alone) MUST NOT trigger (waiting for 2nd house confirmation)
    divergences_single = detector.check_divergences()
    assert len(divergences_single) == 0, "BetBurger alone without 2nd confirming house must NOT trigger alert"

    # 2. Add second reference source (1xBet also confirms 6:4) -> Tríade Completa!
    event_1xbet = NormalizedEvent(
        match_id="silva vs haddouch",
        match_name="Silva vs Haddouch",
        sport="tabletennis",
        source="1xbet",
        set_score="0:0",
        game_score="6:4",
        point_score="0",
        timestamp=now
    )
    cache.update(event_1xbet)

    # Detect dual confirmed divergence (BetBurger + 1xBet)
    divergences = detector.check_divergences()
    assert len(divergences) == 1, "Dual confirmation (BetBurger + 1xBet) must trigger alert"
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


def test_twenty_seconds_freeze_rule():
    """Validates the strict 20.0s freeze rule: no alert under 20s, alert at >= 20s, auto-clear on catch-up."""
    cache = StateCache()
    detector = DivergenceDetector(state_cache=cache, freeze_threshold_seconds=20.0, min_game_difference=1)
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
    # BetBurger and 1xBet both advance to Game 4:2 (gap=2, meets minimum)
    burger_ev = NormalizedEvent(
        match_id="banot vs tyn",
        match_name="Petr Banot vs Daniel Tyn",
        sport="tabletennis",
        source="betburger",
        set_score="1:1",
        game_score="4:2",
        point_score="0",
        timestamp=now
    )
    xbet_ev = NormalizedEvent(
        match_id="banot vs tyn",
        match_name="Petr Banot vs Daniel Tyn",
        sport="tabletennis",
        source="1xbet",
        set_score="1:1",
        game_score="4:2",
        point_score="0",
        timestamp=now
    )
    cache.update(b365_ev)
    cache.update(burger_ev)
    cache.update(xbet_ev)

    # 1. Immediate cycle: Point is detected, but 0.0s elapsed < 20.0s threshold -> NO ALERT
    alerts = detector.check_divergences()
    assert len(alerts) == 0, "Should not alert immediately (< 20.0s)"

    # Verify event is in active tracking
    active_ev = detector.tracker._active_events.get("banot vs tyn")
    assert active_ev is not None, "Event must be actively tracked"

    # 2. Simulate 15.0 seconds elapsed (< 20.0s) -> NO ALERT
    active_ev.detected_at -= 15.0
    if active_ev.confirmed_at:
        active_ev.confirmed_at -= 15.0
    alerts_15s = detector.check_divergences()
    assert len(alerts_15s) == 0, "Should not alert at 15.0s (< 20.0s)"

    # 3. Simulate 20.2 seconds elapsed (>= 20.0s) -> ALERT FIRES!
    active_ev.detected_at -= 5.2
    if active_ev.confirmed_at:
        active_ev.confirmed_at -= 5.2
    alerts_20s = detector.check_divergences()
    assert len(alerts_20s) == 1, "Alert must fire when Bet365 has been frozen for >= 20.0s"
    assert alerts_20s[0]["match_name"] == "Petr Banot vs Daniel Tyn"
    assert alerts_20s[0]["target_house"] == "BET365"
    assert alerts_20s[0]["delay_seconds"] >= 20.0

    # 4. Bet365 catches up to 4:2 -> Divergence resolves and clears
    b365_synced = NormalizedEvent(
        match_id="banot vs tyn",
        match_name="Petr Banot vs Daniel Tyn",
        sport="tabletennis",
        source="bet365",
        set_score="1:1",
        game_score="4:2",
        point_score="0",
        timestamp=datetime.now()
    )
    cache.update(b365_synced)
    alerts_after_sync = detector.check_divergences()
    assert len(alerts_after_sync) == 0, "Alert must clear when Bet365 catches up"
    assert "banot vs tyn" not in detector.tracker._active_events


def test_single_point_gap_ignored():
    """Validates that a single-point gap (normal latency) does NOT generate any alert."""
    cache = StateCache()
    detector = DivergenceDetector(state_cache=cache, freeze_threshold_seconds=0.0, min_game_difference=1)
    now = datetime.now()

    # Bet365 at Game 2:2, references at Game 3:2 (gap = 1 point)
    b365_ev = NormalizedEvent(
        match_id="test_gap",
        match_name="Player A vs Player B",
        sport="tabletennis",
        source="bet365",
        set_score="1:1",
        game_score="2:2",
        point_score="0",
        timestamp=now
    )
    burger_ev = NormalizedEvent(
        match_id="test_gap",
        match_name="Player A vs Player B",
        sport="tabletennis",
        source="betburger",
        set_score="1:1",
        game_score="3:2",
        point_score="0",
        timestamp=now
    )
    betano_ev = NormalizedEvent(
        match_id="test_gap",
        match_name="Player A vs Player B",
        sport="tabletennis",
        source="betano",
        set_score="1:1",
        game_score="3:2",
        point_score="0",
        timestamp=now
    )
    cache.update(b365_ev)
    cache.update(burger_ev)
    cache.update(betano_ev)

    # Even with dual confirmation, gap=1 must be IGNORED (normal latency)
    alerts = detector.check_divergences()
    assert len(alerts) == 0, "Single-point gap (gap=1) must be ignored as normal latency"


def test_triad_betburger_alone_rejected_and_dual_accepted():
    """Verifies that BetBurger alone never alerts (even if frozen > 20s), but BetBurger + 2nd house alerts."""
    cache = StateCache()
    detector = DivergenceDetector(state_cache=cache, freeze_threshold_seconds=20.0, min_game_difference=1)
    now = datetime.now()

    # Bet365: 1:1 Game 1:1 | References: 1:1 Game 3:1 (gap=2)
    b365_ev = NormalizedEvent(
        match_id="malachowski vs rutkowski",
        match_name="Michal Malachowski x Mateusz Rutkowski",
        sport="tabletennis",
        source="bet365",
        set_score="1:1",
        game_score="1:1",
        point_score="0",
        timestamp=now
    )
    burger_ev = NormalizedEvent(
        match_id="malachowski vs rutkowski",
        match_name="Michal Malachowski x Mateusz Rutkowski",
        sport="tabletennis",
        source="betburger",
        set_score="1:1",
        game_score="3:1",
        point_score="0",
        timestamp=now
    )
    cache.update(b365_ev)
    cache.update(burger_ev)

    # BetBurger alone: Even after delay -> ZERO ALERTS!
    alerts = detector.check_divergences()
    assert len(alerts) == 0, "BetBurger alone MUST NEVER trigger an alert"

    # Now Betano ALSO confirms 3:1 -> 2 bets confirming (BetBurger + Betano)!
    betano_ev = NormalizedEvent(
        match_id="malachowski vs rutkowski",
        match_name="Michal Malachowski x Mateusz Rutkowski",
        sport="tabletennis",
        source="betano",
        set_score="1:1",
        game_score="3:1",
        point_score="0",
        timestamp=now
    )
    cache.update(betano_ev)

    # Initial check (0s elapsed) -> no alert yet
    alerts = detector.check_divergences()
    assert len(alerts) == 0, "No alert before 20s threshold"

    # Fast-forward 20.5s delay with Triad active -> ALERT FIRES!
    active_ev = detector.tracker._active_events.get("malachowski vs rutkowski")
    assert active_ev is not None
    active_ev.detected_at -= 20.5
    if active_ev.confirmed_at:
        active_ev.confirmed_at -= 20.5

    alerts_20s = detector.check_divergences()
    assert len(alerts_20s) == 1, "Alert must fire when BetBurger + 2nd house confirm and delay >= 20s"
    assert "BetBurger" in alerts_20s[0]["leading_houses"]
    assert "Betano" in alerts_20s[0]["leading_houses"]



