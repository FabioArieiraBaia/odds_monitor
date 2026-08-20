import time
from datetime import datetime
from core.state_cache import StateCache
from core.normalizer import NormalizedEvent
from core.divergence_detector import PointEventTracker, EventStatus

def test_point_event_specification_flow():
    cache = StateCache()
    tracker = PointEventTracker(
        state_cache=cache,
        min_delay_seconds=8.0,
        sync_window_seconds=3.0,
        min_confidence_score=70.0
    )

    match_id = "jiri_tichy_vs_petr_orlowski"

    # 1. Initial State: All sources at 5-4 (Set 1, game 5:4)
    print("--- 1. Initial state (5-4 on all houses) ---")
    now = datetime.now()
    cache.update(NormalizedEvent(match_id=match_id, match_name="Jiri Tichy vs Petr Orlowski", sport="tabletennis", source="bet365", set_score="0:0", game_score="5:4", point_score="0", timestamp=now))
    cache.update(NormalizedEvent(match_id=match_id, match_name="Jiri Tichy vs Petr Orlowski", sport="tabletennis", source="betano", set_score="0:0", game_score="5:4", point_score="0", timestamp=now))
    cache.update(NormalizedEvent(match_id=match_id, match_name="Jiri Tichy vs Petr Orlowski", sport="tabletennis", source="betburger", set_score="0:0", game_score="5:4", point_score="0", timestamp=now))

    alerts = tracker.process_cycle()
    assert len(alerts) == 0, f"Expected 0 alerts on initial sync, got {len(alerts)}"
    print("[OK] Initial state ok: 0 alerts")

    # 2. Only Betano changes to 6-4 (Single source error / not confirmed yet)
    print("--- 2. Betano moves to 6-4 alone ---")
    cache.update(NormalizedEvent(match_id=match_id, match_name="Jiri Tichy vs Petr Orlowski", sport="tabletennis", source="betano", set_score="0:0", game_score="6:4", point_score="0", timestamp=datetime.now()))
    alerts = tracker.process_cycle()
    assert len(alerts) == 0, f"Single source should never alert, got {len(alerts)}"
    print("[OK] Single source protection ok: 0 alerts")

    # 3. BetBurger also confirms 6-4 -> CONSENSUS REACHED!
    print("--- 3. BetBurger confirms 6-4 -> Consensus ---")
    cache.update(NormalizedEvent(match_id=match_id, match_name="Jiri Tichy vs Petr Orlowski", sport="tabletennis", source="betburger", set_score="0:0", game_score="6:4", point_score="0", timestamp=datetime.now()))
    alerts = tracker.process_cycle()
    assert len(alerts) == 0, f"No alert immediately (< 8s), got {len(alerts)}"
    event = tracker._active_events.get(match_id)
    assert event is not None, "Event should be active in tracker"
    assert event.status == EventStatus.EVENTO_CONFIRMADO, f"Expected EVENTO_CONFIRMADO, got {event.status}"
    print("[OK] Consensus reached: Event created & confirmed, stopwatch started, 0 alerts before 8s")

    # 4. Check at T + 4s -> Still no alert
    print("--- 4. At T+4s (delay < 8s) ---")
    # Simulate time advancing 4s
    event.detected_at -= 4.0
    event.confirmed_at -= 4.0
    alerts = tracker.process_cycle()
    assert len(alerts) == 0, f"No alert at 4s, got {len(alerts)}"
    print("[OK] T+4s ok: 0 alerts")

    # 5. Check at T + 8.5s (Bet365 still on 5-4) -> ALERTA DISPARADO!
    print("--- 5. At T+8.5s (delay >= 8s) ---")
    event.detected_at -= 4.5
    event.confirmed_at -= 4.5
    alerts = tracker.process_cycle()
    assert len(alerts) == 1, f"Expected 1 alert at >= 8s delay, got {len(alerts)}"
    assert alerts[0]["delay_seconds"] >= 8.0, f"Expected delay >= 8s, got {alerts[0]['delay_seconds']}"
    assert "Betano" in alerts[0]["leading_houses"] and "BetBurger" in alerts[0]["leading_houses"]
    print(f"[OK] Alert fired successfully! Delay: {alerts[0]['delay_seconds']}s, Confidence: {alerts[0]['confidence']}%, Leading: {alerts[0]['leading_houses']}")

    # 6. Bet365 updates to 6-4 -> Event Encerrado
    print("--- 6. Bet365 updates to 6-4 -> Closed ---")
    cache.update(NormalizedEvent(match_id=match_id, match_name="Jiri Tichy vs Petr Orlowski", sport="tabletennis", source="bet365", set_score="0:0", game_score="6:4", point_score="0", timestamp=datetime.now()))
    alerts = tracker.process_cycle()
    assert len(alerts) == 0, "No active alert once B365 is synchronized"
    assert match_id not in tracker._active_events, "Active event should be popped/closed"
    print("[OK] Event synchronized and closed!")

    # 7. Deduplication test: readings of 6-4 do not re-trigger
    print("--- 7. Deduplication test ---")
    alerts = tracker.process_cycle()
    assert len(alerts) == 0, "Deduplication: same point must never re-trigger"
    print("[OK] Deduplication verified!")

    print("\n==========================================")
    print("🎉 ALL SPECIFICATION TESTS PASSED 100%!")
    print("==========================================")

if __name__ == "__main__":
    test_point_event_specification_flow()
