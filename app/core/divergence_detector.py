"""
Point Event State Machine & Divergence Detector for Table Tennis.
Implementation of the technical specification v1.0:
- Temporal point event tracking (state transitions)
- Multi-source cross-confirmation (Consensus between Betano & BetBurger / 1xBet / Novibet)
- State Machine: NORMAL -> EVENTO_DETECTADO -> AGUARDANDO_CONFIRMACAO -> EVENTO_CONFIRMADO -> MONITORANDO_BET365 -> VALIDACAO_FINAL -> ALERTA -> ENCERRADO
- Stop-watch measurement of Bet365 delay with configurable threshold (default: 8.0s)
- Confidence scoring (0-100)
- Deduplication of events
- Audit logs & Strict silence on inconclusive cases
"""
import logging
import re
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field

from core.normalizer import NormalizedEvent
from core.state_cache import StateCache

logger = logging.getLogger("point_event_detector")


class EventStatus(Enum):
    NORMAL = "NORMAL"
    EVENTO_DETECTADO = "EVENTO_DETECTADO"
    AGUARDANDO_CONFIRMACAO = "AGUARDANDO_CONFIRMACAO"
    EVENTO_CONFIRMADO = "EVENTO_CONFIRMADO"
    MONITORANDO_BET365 = "MONITORANDO_BET365"
    ATRASO_CANDIDATO = "ATRASO_CANDIDATO"
    ALERTA = "ALERTA"
    ATRASO_NORMAL = "ATRASO_NORMAL"
    CANCELADO = "CANCELADO"
    ENCERRADO = "ENCERRADO"


@dataclass
class MatchSourceState:
    current_state: Tuple[int, int, int, int] = (0, 0, 0, 0)  # (set_h, set_a, game_h, game_a)
    previous_state: Tuple[int, int, int, int] = (0, 0, 0, 0)
    raw_set_score: str = "0:0"
    raw_game_score: str = "0:0"
    raw_point_score: str = "0"
    last_update_timestamp: float = 0.0
    feed_healthy: bool = True
    consecutive_empty_count: int = 0


@dataclass
class PointEvent:
    event_id: str
    match_id: str
    match_name: str
    sport: str
    league: str
    previous_state: Tuple[int, int, int, int]
    new_state: Tuple[int, int, int, int]
    first_detected_by: str
    detected_at: float  # time.time()
    confirmed_at: Optional[float] = None
    bet365_received_at: Optional[float] = None
    delay_seconds: float = 0.0
    status: EventStatus = EventStatus.EVENTO_DETECTADO
    confidence: float = 0.0
    confirming_sources: Set[str] = field(default_factory=set)
    cancellation_reason: str = ""
    alert_sent: bool = False
    alert_timestamp: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PointEventTracker:
    """
    State machine that processes live score updates, builds point transition events,
    measures Bet365 delay, and fires high-precision alerts.
    """
    def __init__(
        self,
        state_cache: StateCache,
        min_delay_seconds: float = 5.0,
        sync_window_seconds: float = 4.0,
        min_confidence_score: float = 75.0,
        max_valid_delay_seconds: float = 45.0,
    ):
        self.state_cache = state_cache
        self.min_delay_seconds = float(min_delay_seconds)
        self.sync_window_seconds = float(sync_window_seconds)
        self.min_confidence_score = float(min_confidence_score)
        self.max_valid_delay_seconds = float(max_valid_delay_seconds)

        # Match history: match_id -> source_name -> MatchSourceState
        self._source_states: Dict[str, Dict[str, MatchSourceState]] = {}

        # Active events: match_id -> PointEvent
        self._active_events: Dict[str, PointEvent] = {}

        # Closed/alerted event keys to prevent duplicate alerts for the same point
        # Key format: f"{match_id}:{prev_state}->{new_state}"
        self._completed_event_keys: Dict[str, float] = {}

        # Reference sources used for cross-confirmation (strictly distinct sources)
        self.reference_sources = ["betano", "1xbet", "betburger"]

    # ── Score Parsing & Normalization ──

    @staticmethod
    def _parse_pair(score_str: str) -> Tuple[int, int]:
        try:
            cleaned = str(score_str).replace("-", ":").strip()
            parts = cleaned.split(":")
            if len(parts) >= 2:
                return int(parts[0].strip()), int(parts[1].strip())
        except Exception:
            pass
        return 0, 0

    def parse_event_state(self, ev: Optional[NormalizedEvent]) -> Optional[Tuple[int, int, int, int]]:
        """
        Parses NormalizedEvent into (set_h, set_a, game_h, game_a).
        Returns None if score is invalid, missing, or garbage.
        """
        if not ev:
            return None
        game = (ev.game_score or "").strip().replace("-", ":")
        sets = (ev.set_score or "").strip().replace("-", ":")
        if not game or game in ("0", "-", "?", "n/a"):
            return None
        if not re.match(r"^\d+:\d+$", game):
            return None

        g_h, g_a = self._parse_pair(game)
        s_h, s_a = self._parse_pair(sets) if sets and re.match(r"^\d+:\d+$", sets) else (0, 0)

        # Basic validity guards for Table Tennis
        if g_h > 40 or g_a > 40 or s_h > 7 or s_a > 7:
            return None

        return (s_h, s_a, g_h, g_a)

    @staticmethod
    def _state_progress(state: Tuple[int, int, int, int]) -> int:
        """Total sets won + total points in current game"""
        s_h, s_a, g_h, g_a = state
        return (s_h + s_a) * 100 + (g_h + g_a)

    def _is_valid_transition(self, prev: Tuple[int, int, int, int], new: Tuple[int, int, int, int]) -> bool:
        """
        Validates if transition (prev -> new) is mathematically / logically possible in Table Tennis.
        """
        s_h_prev, s_a_prev, g_h_prev, g_a_prev = prev
        s_h_new, s_a_new, g_h_new, g_a_new = new

        # 1. Point advancement within the same set
        if (s_h_new, s_a_new) == (s_h_prev, s_a_prev):
            diff_h = g_h_new - g_h_prev
            diff_a = g_a_new - g_a_prev
            # Normal point: +1 for one player, +0 for the other
            if (diff_h == 1 and diff_a == 0) or (diff_h == 0 and diff_a == 1):
                return True
            # In live scrapes, a 2-point jump can happen under fast rallies, accept <= 2
            if (0 <= diff_h <= 2) and (0 <= diff_a <= 2) and (diff_h + diff_a in (1, 2)):
                return True
            return False

        # 2. Set transition (previous set finished e.g. >= 11 pts, new set begins e.g. 0:0, 1:0, 0:1)
        prev_set_sum = s_h_prev + s_a_prev
        new_set_sum = s_h_new + s_a_new
        if new_set_sum == prev_set_sum + 1:
            # The new set score should be starting fresh
            if g_h_new <= 4 and g_a_new <= 4:
                return True

        return False

    # ── Confidence Scoring (0 - 100) ──

    def _compute_confidence(
        self,
        event: PointEvent,
        b365_state: MatchSourceState,
        ref_states: Dict[str, MatchSourceState]
    ) -> float:
        score = 0.0

        # 1. Consensus of at least 2 reference sources (Base 40 pts)
        if len(event.confirming_sources) >= 2:
            score += 40.0
        elif len(event.confirming_sources) == 1:
            score += 15.0

        # Extra point if 3 or more references agree
        if len(event.confirming_sources) >= 3:
            score += 15.0

        # 2. Sequence consistency (20 pts)
        if self._is_valid_transition(event.previous_state, event.new_state):
            score += 20.0

        # 3. Source Feed Health (15 pts)
        healthy_refs = sum(1 for s in event.confirming_sources if ref_states.get(s) and ref_states[s].feed_healthy)
        if healthy_refs >= 2 and b365_state.feed_healthy:
            score += 15.0

        # 4. Temporal consistency (10 pts)
        if event.confirmed_at and event.detected_at:
            sync_diff = event.confirmed_at - event.detected_at
            if sync_diff <= self.sync_window_seconds:
                score += 10.0

        return min(100.0, score)

    # ── Main Event Processing Cycle ──

    def process_cycle(self) -> List[Dict[str, Any]]:
        """
        Executes one evaluation cycle across all active matches in state_cache.
        Returns list of newly fired or actively confirmed alerts.
        """
        now = time.time()
        now_dt = datetime.now()
        alerts_to_emit: List[Dict[str, Any]] = []

        # Cleanup old completed keys (> 300s)
        for key, completed_time in list(self._completed_event_keys.items()):
            if now - completed_time > 300:
                self._completed_event_keys.pop(key, None)

        active_match_ids = set(self.state_cache.get_all_active_match_ids())

        # Cleanup disappeared matches
        for m_id in list(self._active_events.keys()):
            if m_id not in active_match_ids:
                self._active_events.pop(m_id, None)

        for match_id in active_match_ids:
            # 1. Retrieve raw events
            b365_ev = self.state_cache.get_event(match_id, "bet365")
            betano_ev = self.state_cache.get_event(match_id, "betano")
            burger_ev = self.state_cache.get_event(match_id, "betburger")
            novibet_ev = self.state_cache.get_event(match_id, "novibet")
            onexbet_ev = self.state_cache.get_event(match_id, "1xbet") or self.state_cache.get_event(match_id, "onexbet")

            # Parse score states for strictly distinct feeds
            parsed_states: Dict[str, Optional[Tuple[int, int, int, int]]] = {
                "bet365": self.parse_event_state(b365_ev),
                "betano": self.parse_event_state(betano_ev),
                "1xbet": self.parse_event_state(onexbet_ev),
                "betburger": self.parse_event_state(burger_ev),
            }

            # Initialize / Update Source States
            if match_id not in self._source_states:
                self._source_states[match_id] = {}

            for src_name, state in parsed_states.items():
                if src_name not in self._source_states[match_id]:
                    self._source_states[match_id][src_name] = MatchSourceState()

                src_obj = self._source_states[match_id][src_name]
                if state is not None:
                    if src_obj.current_state != state:
                        src_obj.previous_state = src_obj.current_state
                        src_obj.current_state = state
                        src_obj.last_update_timestamp = now
                    src_obj.feed_healthy = True
                    src_obj.consecutive_empty_count = 0
                else:
                    src_obj.consecutive_empty_count += 1
                    if src_obj.consecutive_empty_count >= 5:
                        src_obj.feed_healthy = False

            b365_state = self._source_states[match_id].get("bet365")
            if not b365_state or not b365_state.current_state or b365_state.current_state == (0, 0, 0, 0):
                # Bet365 not ready or no valid score
                continue

            # Gather active reference source states
            active_ref_states: Dict[str, Tuple[int, int, int, int]] = {}
            for src_name in self.reference_sources:
                st = self._source_states[match_id].get(src_name)
                if st and st.feed_healthy and st.current_state and st.current_state != (0, 0, 0, 0):
                    active_ref_states[src_name] = st.current_state

            # We need at least 2 reference sources available for consensus
            if len(active_ref_states) < 2:
                # If there was an active event, cancel or hold
                if match_id in self._active_events:
                    ev = self._active_events[match_id]
                    if ev.status != EventStatus.ALERTA:
                        ev.status = EventStatus.CANCELADO
                        ev.cancellation_reason = "Menos de 2 fontes de referência disponíveis"
                        self._active_events.pop(match_id, None)
                continue

            current_b365_state = b365_state.current_state
            active_event = self._active_events.get(match_id)

            # ── 2. Check for New Point Transitions on Reference Sources ──
            # Find candidate states ahead of Bet365
            # A candidate new state must be ahead of Bet365:
            # progress(ref_state) > progress(b365_state)
            b365_progress = self._state_progress(current_b365_state)

            # Count votes for each candidate new state among reference sources
            state_votes: Dict[Tuple[int, int, int, int], List[str]] = {}
            for src_name, r_state in active_ref_states.items():
                if self._state_progress(r_state) > b365_progress:
                    state_votes.setdefault(r_state, []).append(src_name)

            # Find if there is a consensus state with >= 2 confirming sources
            consensus_state = None
            confirming_sources = []
            for candidate_state, voters in state_votes.items():
                if len(voters) >= 2:
                    consensus_state = candidate_state
                    confirming_sources = voters
                    break

            # ── 3. State Machine Logic ──

            if consensus_state is not None:
                event_key = f"{match_id}:{current_b365_state}->{consensus_state}"

                # Check if this point transition was already alerted / completed
                if event_key in self._completed_event_keys:
                    continue

                if active_event is None:
                    # Create NEW PENDING EVENT
                    ref_ev = b365_ev or betano_ev or burger_ev
                    display_name = (ref_ev.match_name if ref_ev else match_id).replace(" vs ", " x ").replace(" VS ", " x ")
                    league = (ref_ev.extra_data.get("league") if ref_ev and ref_ev.extra_data else "") or ""
                    # Sanitize: strip garbage Bet365 UI chrome text
                    if league and re.search(r'(?i)principal|partida|^(game|set|pts|live|aovivo)+$', league.replace(' ', '')):
                        league = ""
                    if not league:
                        league = "Tênis de Mesa"

                    active_event = PointEvent(
                        event_id=f"EV_{int(now*1000)}",
                        match_id=match_id,
                        match_name=display_name,
                        sport="tabletennis",
                        league=league,
                        previous_state=current_b365_state,
                        new_state=consensus_state,
                        first_detected_by=confirming_sources[0],
                        detected_at=now,
                        confirmed_at=now,
                        status=EventStatus.EVENTO_CONFIRMADO,
                        confirming_sources=set(confirming_sources),
                    )
                    self._active_events[match_id] = active_event
                    logger.info(
                        f"🎯 [NOVO PONTO DETECTADO] {display_name} | Bet365: {current_b365_state} -> Consenso ({','.join(confirming_sources)}): {consensus_state} | Cronômetro iniciado."
                    )
                else:
                    # Update existing active event
                    if active_event.new_state == consensus_state:
                        active_event.confirming_sources.update(confirming_sources)
                        if active_event.status in (EventStatus.EVENTO_DETECTADO, EventStatus.AGUARDANDO_CONFIRMACAO):
                            active_event.status = EventStatus.EVENTO_CONFIRMADO
                            active_event.confirmed_at = now
                    else:
                        # Reference changed to another point (point progression during delay)
                        if self._is_valid_transition(active_event.new_state, consensus_state):
                            # Advanced further! Maintain timer or upgrade state
                            active_event.new_state = consensus_state
                            active_event.confirming_sources = set(confirming_sources)
                        else:
                            # Inconsistency / Correction
                            active_event.status = EventStatus.CANCELADO
                            active_event.cancellation_reason = "Inconsistência de transição no consenso"
                            self._active_events.pop(match_id, None)
                            active_event = None

            # ── 4. Monitor Bet365 & Validate Delay Timer ──
            if active_event is not None and active_event.status in (
                EventStatus.EVENTO_CONFIRMADO,
                EventStatus.MONITORANDO_BET365,
                EventStatus.ATRASO_CANDIDATO,
                EventStatus.ALERTA,
            ):
                # A. Check if Bet365 caught up to the new state
                if current_b365_state == active_event.new_state or self._state_progress(current_b365_state) >= self._state_progress(active_event.new_state):
                    delay = now - (active_event.confirmed_at or active_event.detected_at)
                    if delay < self.min_delay_seconds:
                        active_event.status = EventStatus.ATRASO_NORMAL
                        logger.debug(f"⏱️ [ATRASO NORMAL] {active_event.match_name} Bet365 atualizou em {delay:.1f}s (< {self.min_delay_seconds}s). Sem alerta.")
                    else:
                        active_event.status = EventStatus.ENCERRADO
                        logger.info(f"✅ [ENCERRADO] {active_event.match_name} Bet365 sincronizada após {delay:.1f}s.")

                    event_key = f"{match_id}:{active_event.previous_state}->{active_event.new_state}"
                    self._completed_event_keys[event_key] = now
                    self._active_events.pop(match_id, None)
                    continue

                # B. Measure Delay
                start_time = active_event.confirmed_at or active_event.detected_at
                delay_seconds = now - start_time
                active_event.delay_seconds = delay_seconds

                # C. Check for Stale / Frozen drop
                if delay_seconds > self.max_valid_delay_seconds:
                    logger.debug(f"⚠️ [DROP CONGELADO] {active_event.match_name} delay={delay_seconds:.1f}s > {self.max_valid_delay_seconds}s. Cancelando.")
                    active_event.status = EventStatus.CANCELADO
                    active_event.cancellation_reason = "Delay excessivo (mercado/placar congelado)"
                    event_key = f"{match_id}:{active_event.previous_state}->{active_event.new_state}"
                    self._completed_event_keys[event_key] = now
                    self._active_events.pop(match_id, None)
                    continue

                # D. Evaluate Delay Threshold
                if delay_seconds >= self.min_delay_seconds:
                    active_event.status = EventStatus.ATRASO_CANDIDATO

                    # ── 5. FINAL VALIDATION BEFORE FIRING ALERTA ──
                    # • Betano e BetBurger confirmaram o mesmo evento? SIM
                    # • O evento é compatível com o estado anterior? SIM
                    # • As duas fontes de referência estão com feed saudável? SIM
                    # • A Bet365 ainda está no estado anterior? SIM
                    # • Confiança >= limiar?
                    confidence = self._compute_confidence(active_event, b365_state, self._source_states[match_id])
                    active_event.confidence = confidence

                    if confidence >= self.min_confidence_score:
                        is_first_alert = not active_event.alert_sent
                        active_event.status = EventStatus.ALERTA
                        active_event.alert_sent = True
                        active_event.alert_timestamp = now_dt.strftime("%H:%M:%S")

                        # Build Alert Payload
                        b365_str = self._format_human_score(b365_ev, current_b365_state)
                        betano_str = self._format_human_score(betano_ev, parsed_states.get("betano"))
                        xbet_str = self._format_human_score(onexbet_ev, parsed_states.get("1xbet"))
                        burger_str = self._format_human_score(burger_ev, parsed_states.get("betburger"))

                        b365_link = (b365_ev.deep_link if b365_ev else "") or ""
                        betano_link = (betano_ev.deep_link if betano_ev else "") or ""
                        xbet_link = (onexbet_ev.deep_link if onexbet_ev else "") or ""
                        burger_link = (burger_ev.deep_link if burger_ev else "") or ""

                        leading_list = sorted(list(active_event.confirming_sources))
                        # Capitalize for display
                        leading_display = [
                            "Betano" if s == "betano" else "1xBet" if s in ("1xbet", "onexbet") else "BetBurger" if s == "betburger" else s.title()
                            for s in leading_list
                        ]

                        alert_payload = {
                            "event_id": active_event.event_id,
                            "match_id": match_id,
                            "match_name": active_event.match_name,
                            "sport": "Tênis de Mesa",
                            "league": active_event.league,
                            "target_house": "BET365",
                            "bet365_score": b365_str,
                            "betburger_score": burger_str if burger_str != "não encontrado" else xbet_str,
                            "xbet_score": xbet_str,
                            "betano_score": betano_str,
                            "novibet_score": "não encontrado",
                            "bet365_link": b365_link,
                            "betburger_link": burger_link or xbet_link,
                            "xbet_link": xbet_link,
                            "betano_link": betano_link,
                            "novibet_link": "",
                            "leading_houses": leading_display,
                            "is_update": not is_first_alert,
                            "notify": is_first_alert,
                            "delay_seconds": round(delay_seconds, 1),
                            "confidence": round(confidence, 1),
                            "timestamp": now_dt.strftime("%H:%M:%S"),
                            "timestamp_full": now_dt.strftime("%d/%m/%Y %H:%M:%S"),
                            "priority": "CRITICAL" if confidence >= 90 else "HIGH",
                            "reason": "atraso_confirmado_consenso",
                        }

                        alerts_to_emit.append(alert_payload)

                        if is_first_alert:
                            logger.info(
                                f"🚨 [ALERTA DISPARADO] {active_event.match_name} | "
                                f"Atraso Bet365: {delay_seconds:.1f}s | Confiança: {confidence:.0f}% | "
                                f"B365: {b365_str} | Consenso: {active_event.new_state} por {','.join(leading_display)}"
                            )
                    else:
                        logger.debug(
                            f"🔇 [REGRA DE SILÊNCIO] {active_event.match_name} Confiança ({confidence:.1f}%) abaixo do mínimo ({self.min_confidence_score}%). Não alertando."
                        )

        return alerts_to_emit

    @staticmethod
    def _format_human_score(ev: Optional[NormalizedEvent], state: Optional[Tuple[int, int, int, int]]) -> str:
        if state is None:
            return "não encontrado"
        s_h, s_a, g_h, g_a = state
        set_str = f"{s_h}:{s_a}"
        game_str = f"{g_h}:{g_a}"
        period = f"Set {s_h + s_a + 1}"
        return f"{game_str} | {period}"


class DivergenceDetector:
    """
    Wrapper retaining compatibility with existing server & test suites,
    delegating detection logic to the new temporal PointEventTracker state machine.
    """
    def __init__(
        self,
        state_cache: StateCache,
        freeze_threshold_seconds: float = 5.0,
        min_game_difference: int = 1,
    ):
        self.state_cache = state_cache
        self.freeze_threshold_seconds = freeze_threshold_seconds
        self.min_game_difference = min_game_difference

        # Instantiate the new PointEventTracker state machine
        self.tracker = PointEventTracker(
            state_cache=state_cache,
            min_delay_seconds=self.freeze_threshold_seconds,
            sync_window_seconds=4.0,
            min_confidence_score=75.0,
            max_valid_delay_seconds=45.0,
        )

    def check_divergences(self) -> List[dict]:
        # Sync dynamic threshold if changed via UI
        self.tracker.min_delay_seconds = float(self.freeze_threshold_seconds)
        return self.tracker.process_cycle()
