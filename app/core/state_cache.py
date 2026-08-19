"""
State cache for multi-source live events with strict fuzzy name matching.
Only merges sources when BOTH player sides match — no fake pairings.
"""
import re
import difflib
from datetime import datetime
from typing import Dict, Optional, List, Set, Tuple
from core.normalizer import NormalizedEvent


def _tokens(name: str) -> Set[str]:
    n = name.lower()
    n = n.replace("/", " ").replace("-", " ").replace(",", " ").replace(".", " ")
    n = re.sub(r"\s+v(?:s)?\.?\s+|\s+x\s+", " ", n)
    # Keep tokens length >= 3 to avoid initial-only false positives (J, A, …)
    return {t for t in n.split() if len(t) >= 3 and not t.isdigit()}


def _sides(name: str) -> Optional[Tuple[Set[str], Set[str]]]:
    parts = re.split(r"\s+v(?:s)?\.?\s+|\s+x\s+", name.strip(), flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    left, right = _tokens(parts[0]), _tokens(parts[1])
    if not left or not right:
        return None
    return left, right


def _side_overlap(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    hits = 0
    for t1 in a:
        for t2 in b:
            if t1 == t2 or (len(t1) >= 4 and len(t2) >= 4 and (t1 in t2 or t2 in t1)):
                hits += 1
                break
    return hits / min(len(a), len(b))


def _flip_tokens(side: Set[str]) -> Set[str]:
    """Also match 'Steffan Jan' vs 'Jan Steffan' by treating order as irrelevant."""
    return side  # token set already order-independent


def match_similarity(name1: str, name2: str) -> float:
    """
    Similarity in [0, 1].
    Requires both player sides to overlap — prevents pairing unrelated matches.
    """
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0

    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()

    s1 = _sides(name1)
    s2 = _sides(name2)
    if s1 and s2:
        # Token sets ignore first/last name order within a side
        a0, a1 = _flip_tokens(s1[0]), _flip_tokens(s1[1])
        b0, b1 = _flip_tokens(s2[0]), _flip_tokens(s2[1])
        direct = (_side_overlap(a0, b0) + _side_overlap(a1, b1)) / 2.0
        swapped = (_side_overlap(a0, b1) + _side_overlap(a1, b0)) / 2.0
        side_score = max(direct, swapped)
        # Hard reject if either orientation fails to cover both sides reasonably
        if side_score < 0.5:
            return min(ratio * 0.4, 0.4)  # cap so threshold never auto-accepts
        return min(1.0, max(ratio, side_score))

    # Fallback when sides cannot be parsed
    t1, t2 = _tokens(n1), _tokens(n2)
    if not t1 or not t2:
        return ratio
    match_count = 0
    for token1 in t1:
        for token2 in t2:
            if token1 == token2 or token1 in token2 or token2 in token1:
                match_count += 1
                break
    token_ratio = match_count / min(len(t1), len(t2))
    return max(ratio, token_ratio)


class StateCache:
    def __init__(self, match_threshold: float = 0.72):
        # { match_id: { "bet365": NormalizedEvent, "betburger": ..., "betano": ... } }
        self._cache: Dict[str, Dict[str, NormalizedEvent]] = {}
        self._last_changed: Dict[str, Dict[str, datetime]] = {}
        self.match_threshold = match_threshold

    def _find_best_existing_id(self, event: NormalizedEvent) -> Optional[str]:
        """Fuzzy-match event against existing cache keys that have other sources."""
        best_id = None
        best_score = 0.0

        for existing_id, sources in self._cache.items():
            ref = sources.get("bet365") or next(iter(sources.values()), None)
            if not ref:
                continue

            score = match_similarity(ref.match_name, event.match_name)
            for src_ev in sources.values():
                score = max(score, match_similarity(src_ev.match_name, event.match_name))

            if score > best_score:
                best_score = score
                best_id = existing_id

        if best_id is not None and best_score >= self.match_threshold:
            return best_id
        return None

    def update(self, event: NormalizedEvent):
        match_id = event.match_id
        source = event.source
        now = datetime.now()

        if source != "bet365":
            already_paired = match_id in self._cache and "bet365" in self._cache.get(match_id, {})
            if not already_paired:
                best = self._find_best_existing_id(event)
                if best:
                    match_id = best
                    event.match_id = match_id
        else:
            if match_id not in self._cache:
                best = self._find_best_existing_id(event)
                if best:
                    match_id = best
                    event.match_id = match_id

        if match_id not in self._cache:
            self._cache[match_id] = {}
            self._last_changed[match_id] = {}

        old_event = self._cache[match_id].get(source)
        self._cache[match_id][source] = event

        if old_event is None or (
            old_event.set_score != event.set_score
            or old_event.game_score != event.game_score
            or old_event.point_score != event.point_score
        ):
            self._last_changed[match_id][source] = now
        elif source not in self._last_changed[match_id]:
            self._last_changed[match_id][source] = now

    def get_event(self, match_id: str, source: str) -> Optional[NormalizedEvent]:
        return self._cache.get(match_id, {}).get(source)

    def get_last_changed(self, match_id: str, source: str) -> Optional[datetime]:
        return self._last_changed.get(match_id, {}).get(source)

    def get_all_active_match_ids(self) -> List[str]:
        return list(self._cache.keys())

    def clear_stale(self, max_age_seconds: float = 120.0):
        """Clears events/sources that haven't been polled/updated recently."""
        now = datetime.now()
        to_delete_matches = []

        for match_id, sources in list(self._cache.items()):
            to_delete_sources = []
            for source, event in sources.items():
                if (now - event.timestamp).total_seconds() > max_age_seconds:
                    to_delete_sources.append(source)

            for source in to_delete_sources:
                sources.pop(source, None)
                if match_id in self._last_changed and source in self._last_changed[match_id]:
                    self._last_changed[match_id].pop(source, None)

            if not sources:
                to_delete_matches.append(match_id)

        for match_id in to_delete_matches:
            self._cache.pop(match_id, None)
            self._last_changed.pop(match_id, None)

    def purge_source_missing(self, source: str, active_match_ids: Set[str]):
        """Remove source data for matches that are no longer active in the current scrape."""
        to_delete_matches = []
        for match_id, sources in list(self._cache.items()):
            if source in sources and match_id not in active_match_ids:
                sources.pop(source)
                if match_id in self._last_changed:
                    self._last_changed[match_id].pop(source, None)
            if not sources:
                to_delete_matches.append(match_id)
                
        for match_id in to_delete_matches:
            self._cache.pop(match_id, None)
            self._last_changed.pop(match_id, None)
