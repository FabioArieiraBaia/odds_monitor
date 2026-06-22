"""
Divergence Detector — Compares live events from Bet365 and BetBurger
to detect score freezes and disparities in real-time.
"""
import logging
from datetime import datetime
from typing import Dict, List
from core.normalizer import NormalizedEvent
from core.state_cache import StateCache

logger = logging.getLogger(__name__)


class DivergenceDetector:
    def __init__(self, state_cache: StateCache, freeze_threshold_seconds: float = 8.0, min_game_difference: int = 1):
        self.state_cache = state_cache
        self.freeze_threshold_seconds = freeze_threshold_seconds
        self.min_game_difference = min_game_difference
        self._alerts_cooldown: Dict[str, datetime] = {}  # { match_id: last_alert_time }
        self._alerted_hashes = set()

    def _safe_int(self, val: str) -> int:
        """Safely parse a string to int, returning 0 on failure."""
        try:
            return int(val.strip())
        except (ValueError, AttributeError):
            return 0

    def _parse_score_pair(self, score: str) -> tuple:
        """Parse 'H:A' into (home, away) ints. Returns (0,0) on failure."""
        try:
            parts = score.split(":")
            if len(parts) >= 2:
                return self._safe_int(parts[0]), self._safe_int(parts[1])
        except Exception:
            pass
        return 0, 0

    def _is_burger_ahead(self, b365_sets: str, b365_score: str, burger_sets: str, burger_score: str) -> bool:
        """Checks if BetBurger is strictly ahead of Bet365 (sets or game score)."""
        try:
            # 1. Compare total completed sets
            b365_s_h, b365_s_a = self._parse_score_pair(b365_sets)
            burger_s_h, burger_s_a = self._parse_score_pair(burger_sets)
            
            b365_total_sets = b365_s_h + b365_s_a
            burger_total_sets = burger_s_h + burger_s_a
            
            if burger_total_sets > b365_total_sets:
                return True
            if burger_total_sets < b365_total_sets:
                return False
                
            # 2. If same set count, compare game/point scores
            b365_g_h, b365_g_a = self._parse_score_pair(b365_score)
            burger_g_h, burger_g_a = self._parse_score_pair(burger_score)
            
            # BetBurger total must be higher (more action has happened)
            burger_total = burger_g_h + burger_g_a
            b365_total = b365_g_h + b365_g_a
            
            return burger_total > b365_total
        except Exception:
            return False

    def _parse_game_diff(self, b365_sets: str, b365_score: str, burger_sets: str, burger_score: str) -> int:
        """Calculate overall divergence magnitude between the two sources."""
        try:
            # Set difference
            b365_s_h, b365_s_a = self._parse_score_pair(b365_sets)
            burger_s_h, burger_s_a = self._parse_score_pair(burger_sets)
            set_diff = abs((burger_s_h + burger_s_a) - (b365_s_h + b365_s_a))
            
            # Game/score difference
            b365_g_h, b365_g_a = self._parse_score_pair(b365_score)
            burger_g_h, burger_g_a = self._parse_score_pair(burger_score)
            score_diff = abs((burger_g_h + burger_g_a) - (b365_g_h + b365_g_a))
            
            # Sets are worth more — each set is at least ~10 games
            return set_diff * 10 + score_diff
        except Exception:
            return 0

    def check_divergences(self) -> List[dict]:
        now = datetime.now()
        divergences = []
        
        match_ids = self.state_cache.get_all_active_match_ids()
        for match_id in match_ids:
            b365_event = self.state_cache.get_event(match_id, "bet365")
            burger_event = self.state_cache.get_event(match_id, "betburger")
            
            if not b365_event or not burger_event:
                continue

            surebet_perc = burger_event.extra_data.get("surebet_percentage", 0.0)
            
            # Check for High Surebet Disparity
            if surebet_perc >= 1.0:
                alert_id = f"surebet_{match_id}_{surebet_perc}"
                if alert_id not in self._alerted_hashes:
                    bet365_link = b365_event.deep_link or ""
                    betburger_link = burger_event.deep_link or ""
                    divergences.append({
                        "match_id": match_id,
                        "match_name": b365_event.match_name,
                        "sport": b365_event.sport,
                        "priority": "HIGH",
                        "bet365_score": f"{b365_event.set_score} ({b365_event.game_score})",
                        "betburger_score": f"{burger_event.set_score} ({burger_event.game_score})",
                        "bet365_points": b365_event.point_score,
                        "betburger_points": burger_event.point_score,
                        "freeze_seconds": 0.0,
                        "game_diff": 0,
                        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "bet365_link": bet365_link,
                        "betburger_link": betburger_link,
                        "type": "alta_disparidade",
                        "message": f"🔥 Alta Disparidade: {surebet_perc}%",
                    })
                    self._alerted_hashes.add(alert_id)
                    continue # Skip other alerts for this match

            # Compare scores: BetBurger must be strictly ahead
            burger_ahead = self._is_burger_ahead(
                b365_event.set_score, b365_event.game_score,
                burger_event.set_score, burger_event.game_score
            )
            game_diff = self._parse_game_diff(
                b365_event.set_score, b365_event.game_score,
                burger_event.set_score, burger_event.game_score
            )
            
            # Check freeze duration on Bet365
            b365_last_changed = self.state_cache.get_last_changed(match_id, "bet365")
            freeze_duration = 0.0
            if b365_last_changed:
                freeze_duration = (now - b365_last_changed).total_seconds()
            
            is_frozen = freeze_duration >= self.freeze_threshold_seconds
            is_divergent = game_diff >= self.min_game_difference and burger_ahead

            # Alert condition: divergence where Burger is ahead, OR frozen while Burger is ahead
            if is_divergent or (is_frozen and burger_ahead):
                # Determine Priority
                priority = "MEDIUM"
                if is_divergent and is_frozen:
                    priority = "CRITICAL"
                elif is_divergent:
                    priority = "HIGH"

                # Deduplicate/Cooldown check
                last_alert = self._alerts_cooldown.get(match_id)
                if last_alert and (now - last_alert).total_seconds() < 30.0:
                    continue  # Cooldown active, skip

                self._alerts_cooldown[match_id] = now

                # Use real deep links from scraped data
                bet365_link = b365_event.deep_link or ""
                betburger_link = burger_event.deep_link or ""

                divergences.append({
                    "match_id": match_id,
                    "match_name": b365_event.match_name,
                    "sport": b365_event.sport,
                    "bet365_score": f"{b365_event.set_score} ({b365_event.game_score})",
                    "betburger_score": f"{burger_event.set_score} ({burger_event.game_score})",
                    "bet365_points": b365_event.point_score,
                    "betburger_points": burger_event.point_score,
                    "freeze_seconds": round(freeze_duration, 1),
                    "game_diff": game_diff,
                    "priority": priority,
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "bet365_link": bet365_link,
                    "betburger_link": betburger_link,
                })

                logger.info(
                    f"🚨 DIVERGÊNCIA [{priority}] {b365_event.match_name} | "
                    f"B365: {b365_event.game_score} vs BB: {burger_event.game_score} | "
                    f"Freeze: {freeze_duration:.1f}s"
                )

        return divergences
