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

    # Tennis point ordering: Ad > 40 > 30 > 15 > 0
    _TENNIS_PTS_ORDER = {'0': 0, '15': 1, '30': 2, '40': 3, 'ad': 4, 'adv': 4, 'a': 4}

    def _tennis_pt_value(self, pt: str) -> int:
        """Convert a tennis point string to a numeric order value."""
        return self._TENNIS_PTS_ORDER.get(str(pt).lower().strip(), -1)

    def _is_burger_ahead(self, b365_sets: str, b365_score: str, burger_sets: str, burger_score: str,
                         b365_points: str = "0", burger_points: str = "0") -> bool:
        """Checks if BetBurger is strictly ahead of Bet365 (sets, games, or points)."""
        try:
            # 1. Compare total completed sets
            b365_s_h, b365_s_a = self._parse_score_pair(b365_sets)
            burger_s_h, burger_s_a = self._parse_score_pair(burger_sets)

            b365_total_sets = b365_s_h + b365_s_a
            burger_total_sets = burger_s_h + burger_s_a
            
            b365_g_h, b365_g_a = self._parse_score_pair(b365_score)
            burger_g_h, burger_g_a = self._parse_score_pair(burger_score)
            b365_max_game = max(b365_g_h, b365_g_a)
            burger_max_game = max(burger_g_h, burger_g_a)

            if burger_total_sets > b365_total_sets:
                # If BetBurger has more sets, but Bet365 is showing a finished set score (>= 6),
                # Bet365 is just delayed in updating its set counter. Not a real live divergence.
                if b365_max_game >= 6:
                    return False
                return True
                
            if burger_total_sets < b365_total_sets:
                return False

            burger_game_total = burger_g_h + burger_g_a
            b365_game_total = b365_g_h + b365_g_a

            if burger_game_total > b365_game_total:
                # Set transition heuristic: If Bet365 has reset for a new set (score <= 2)
                # and BetBurger is showing a high score typical of a finished set (>= 6),
                # Bet365 is actually ahead in time, so BetBurger is NOT ahead.
                if b365_game_total <= 2 and max(burger_g_h, burger_g_a) >= 6:
                    return False
                return True
            if burger_game_total < b365_game_total:
                return False

            # 3. Games equal — compare point scores
            # Handle tennis-style points (0, 15, 30, 40, Ad)
            b365_pts_parts = str(b365_points).split(':') if b365_points and b365_points != '0' else []
            burger_pts_parts = str(burger_points).split(':') if burger_points and burger_points != '0' else []

            if b365_pts_parts and burger_pts_parts and len(b365_pts_parts) == 2 and len(burger_pts_parts) == 2:
                # Check if tennis-style (contains 15, 30, 40, Ad)
                is_tennis_pts = any(
                    p.lower() in self._TENNIS_PTS_ORDER
                    for p in b365_pts_parts + burger_pts_parts
                    if not p.isdigit() or int(p) in (0, 15, 30, 40)
                )

                if is_tennis_pts:
                    b365_pt_h = self._tennis_pt_value(b365_pts_parts[0])
                    b365_pt_a = self._tennis_pt_value(b365_pts_parts[1])
                    burger_pt_h = self._tennis_pt_value(burger_pts_parts[0])
                    burger_pt_a = self._tennis_pt_value(burger_pts_parts[1])
                    b365_pt_total = b365_pt_h + b365_pt_a
                    burger_pt_total = burger_pt_h + burger_pt_a
                    return burger_pt_total > b365_pt_total
                else:
                    # Numeric points (e.g. basketball or other sports)
                    try:
                        b365_pt_total = int(b365_pts_parts[0]) + int(b365_pts_parts[1])
                        burger_pt_total = int(burger_pts_parts[0]) + int(burger_pts_parts[1])
                        return burger_pt_total > b365_pt_total
                    except ValueError:
                        pass

            return False
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
            
            # ── Surebet Disparity check ──
            # ONLY trigger if BetBurger is STRICTLY AHEAD in the score.
            # Identical scores mean both bookmakers are synchronized — no advantage.
            if surebet_perc >= 1.0:
                burger_ahead = self._is_burger_ahead(
                    b365_event.set_score, b365_event.game_score,
                    burger_event.set_score, burger_event.game_score,
                    b365_event.point_score, burger_event.point_score
                )
                game_diff = self._parse_game_diff(
                    b365_event.set_score, b365_event.game_score,
                    burger_event.set_score, burger_event.game_score
                )
                
                # Sanity check to avoid BetBurger parsing bugs (e.g., 211:1 in soccer)
                max_diff = 60 if b365_event.sport == "basketball" else 30
                if game_diff > max_diff:
                    continue

                if not burger_ahead:
                    # Scores are equal or Bet365 is ahead — this is NOT a real divergence.
                    logger.debug(
                        f"[Surebet] {b365_event.match_name}: surebet={surebet_perc}% "
                        f"but scores are tied/equal. Skipping alert."
                    )
                    continue

                alert_id = f"surebet_{match_id}_{surebet_perc}_{burger_event.game_score}"
                if alert_id not in self._alerted_hashes:
                    bet365_link = b365_event.deep_link or ""
                    # Fallback to BetBurger's extracted bet365_link (Method B)
                    if (not bet365_link or "EV" not in bet365_link) and burger_event:
                        bb_b365_link = burger_event.extra_data.get("bet365_link")
                        if bb_b365_link:
                            bet365_link = bb_b365_link
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
                        "game_diff": game_diff,
                        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "bet365_link": bet365_link,
                        "betburger_link": betburger_link,
                        "type": "alta_disparidade",
                        "message": f"🔥 Alta Disparidade: {surebet_perc}%",
                        "needs_verification": bool(bet365_link and b365_event.source == "bet365"),
                    })
                    self._alerted_hashes.add(alert_id)
                    logger.info(
                        f"🚨 SUREBET [{surebet_perc}%] {b365_event.match_name} | "
                        f"BB: {burger_event.game_score} vs B365: {b365_event.game_score}"
                    )
                    continue  # Skip regular divergence check for this match

            # Compare scores: BetBurger must be strictly ahead
            burger_ahead = self._is_burger_ahead(
                b365_event.set_score, b365_event.game_score,
                burger_event.set_score, burger_event.game_score,
                b365_event.point_score, burger_event.point_score
            )
            game_diff = self._parse_game_diff(
                b365_event.set_score, b365_event.game_score,
                burger_event.set_score, burger_event.game_score
            )
            
            # Sanity check to avoid BetBurger parsing bugs (e.g., 211:1 in soccer)
            max_diff = 60 if b365_event.sport == "basketball" else 30
            if game_diff > max_diff:
                continue
            
            # Check freeze duration on Bet365
            b365_last_changed = self.state_cache.get_last_changed(match_id, "bet365")
            freeze_duration = 0.0
            if b365_last_changed:
                freeze_duration = (now - b365_last_changed).total_seconds()
            
            is_frozen = freeze_duration >= self.freeze_threshold_seconds
            is_point_divergent = (game_diff == 0 and burger_ahead)
            is_divergent = (game_diff >= self.min_game_difference or is_point_divergent) and burger_ahead

            # Alert condition: divergence where Burger is ahead AND (Bet365 is frozen OR game difference is high)
            if is_divergent and (is_frozen or game_diff >= self.min_game_difference):
                
                # ── Triangulation with 1xBet ──
                xbet_event = self.state_cache.get_event(match_id, "1xbet")
                is_triangulated = False
                xbet_score = ""
                if xbet_event:
                    xbet_score = f"{xbet_event.set_score} ({xbet_event.game_score})"
                    xbet_ahead_or_equal = not self._is_burger_ahead(
                        xbet_event.set_score, xbet_event.game_score,
                        burger_event.set_score, burger_event.game_score,
                        xbet_event.point_score, burger_event.point_score
                    )
                    if xbet_ahead_or_equal:
                        is_triangulated = True

                # Determine Priority
                is_golden = False
                if burger_event.extra_data.get("is_fresh", False):
                    b365_arrow = burger_event.extra_data.get("bet365_arrow", "none")
                    target_arrow = burger_event.extra_data.get("target_arrow", "none")
                    if b365_arrow in ["grey", "none"] and target_arrow in ["green", "red"]:
                        is_golden = True
                        
                priority = "MEDIUM"
                if is_golden:
                    priority = "GOLDEN"
                elif is_triangulated:
                    priority = "CRITICAL"
                elif is_divergent and is_frozen:
                    priority = "CRITICAL"
                elif is_divergent:
                    priority = "HIGH"

                # Deduplicate/Cooldown check
                last_alert = self._alerts_cooldown.get(match_id)
                if last_alert and (now - last_alert).total_seconds() < 30.0:
                    continue  # Cooldown active, skip

                self._alerts_cooldown[match_id] = now

                bet365_link = b365_event.deep_link or ""
                # Fallback to BetBurger's extracted bet365_link (Method B)
                if (not bet365_link or "EV" not in bet365_link) and burger_event:
                    bb_b365_link = burger_event.extra_data.get("bet365_link")
                    if bb_b365_link:
                        bet365_link = bb_b365_link
                betburger_link = burger_event.deep_link or ""
                
                needs_verification = bool(bet365_link and b365_event.source == "bet365")

                divergences.append({
                    "match_id": match_id,
                    "match_name": b365_event.match_name,
                    "sport": b365_event.sport,
                    "bet365_score": f"{b365_event.set_score} ({b365_event.game_score})",
                    "betburger_score": f"{burger_event.set_score} ({burger_event.game_score})",
                    "xbet_score": xbet_score,
                    "bet365_points": b365_event.point_score,
                    "betburger_points": burger_event.point_score,
                    "freeze_seconds": round(freeze_duration, 1),
                    "game_diff": game_diff,
                    "priority": priority,
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "bet365_link": bet365_link,
                    "betburger_link": betburger_link,
                    "needs_verification": needs_verification,
                    "is_triangulated": is_triangulated
                })

                logger.info(
                    f"🚨 DIVERGÊNCIA [{priority}] {b365_event.match_name} | "
                    f"B365: {b365_event.game_score} vs BB: {burger_event.game_score} | "
                    f"Freeze: {freeze_duration:.1f}s"
                )

        return divergences
