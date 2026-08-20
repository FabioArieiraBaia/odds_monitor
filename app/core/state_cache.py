"""
State cache for multi-source live events with inverted token indexing,
strict fuzzy name matching and synchronous reactive score-change event bus.
"""
import re
import difflib
from functools import lru_cache
from datetime import datetime
from typing import Dict, Optional, List, Set, Tuple, Callable
from core.normalizer import NormalizedEvent


@lru_cache(maxsize=8192)
def _tokens_cached(name: str) -> Tuple[str, ...]:
    n = name.lower()
    n = n.replace("/", " ").replace("-", " ").replace(",", " ").replace(".", " ")
    n = re.sub(r"\s+v(?:s)?\.?\s+|\s+x\s+", " ", n)
    tokens = [t for t in n.split() if len(t) >= 3 and not t.isdigit()]
    return tuple(sorted(set(tokens)))


def _tokens(name: str) -> Set[str]:
    return set(_tokens_cached(name))


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


@lru_cache(maxsize=16384)
def _match_similarity_cached(name1: str, name2: str) -> float:
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0

    s1 = _sides(name1)
    s2 = _sides(name2)
    if s1 and s2:
        a0, a1 = s1[0], s1[1]
        b0, b1 = s2[0], s2[1]
        direct = (_side_overlap(a0, b0) + _side_overlap(a1, b1)) / 2.0
        swapped = (_side_overlap(a0, b1) + _side_overlap(a1, b0)) / 2.0
        side_score = max(direct, swapped)
        if side_score < 0.5:
            ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
            return min(ratio * 0.4, 0.4)
        ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
        return min(1.0, max(ratio, side_score))

    t1, t2 = _tokens(n1), _tokens(n2)
    if not t1 or not t2:
        return difflib.SequenceMatcher(None, n1, n2).ratio()
    match_count = 0
    for token1 in t1:
        for token2 in t2:
            if token1 == token2 or token1 in token2 or token2 in token1:
                match_count += 1
                break
    token_ratio = match_count / min(len(t1), len(t2))
    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    return max(ratio, token_ratio)


def match_similarity(name1: str, name2: str) -> float:
    """Similarity in [0, 1] with fast LRU caching and strict player side overlap."""
    return _match_similarity_cached(name1, name2)


def are_sides_swapped(ref_name: str, candidate_name: str) -> bool:
    """Returns True if candidate_name has Home and Away swapped relative to ref_name."""
    s1 = _sides(ref_name)
    s2 = _sides(candidate_name)
    if not s1 or not s2:
        return False
    a0, a1 = s1[0], s1[1]
    b0, b1 = s2[0], s2[1]
    direct = (_side_overlap(a0, b0) + _side_overlap(a1, b1)) / 2.0
    swapped = (_side_overlap(a0, b1) + _side_overlap(a1, b0)) / 2.0
    return swapped > direct and swapped >= 0.5


def _flip_score_str(score_str: str) -> str:
    """Flips 'X:Y' or 'X-Y' to 'Y:X'."""
    if not score_str:
        return score_str
    parts = re.split(r"[:\-]", score_str.strip())
    if len(parts) == 2:
        return f"{parts[1].strip()}:{parts[0].strip()}"
    return score_str


def _flip_event_orientation(ev: NormalizedEvent, target_name: str):
    """Flips score and aligns name for a swapped event."""
    ev.set_score = _flip_score_str(ev.set_score)
    ev.game_score = _flip_score_str(ev.game_score)
    if ev.extra_data and "home_odd" in ev.extra_data and "away_odd" in ev.extra_data:
        ev.extra_data["home_odd"], ev.extra_data["away_odd"] = ev.extra_data["away_odd"], ev.extra_data["home_odd"]
    ev.match_name = target_name


class StateCache:
    def __init__(self, match_threshold: float = 0.72):
        # { match_id: { "bet365": NormalizedEvent, "1xbet": ..., "betburger": ..., "betano": ... } }
        self._cache: Dict[str, Dict[str, NormalizedEvent]] = {}
        self._last_changed: Dict[str, Dict[str, datetime]] = {}
        # Mapping from raw source match_id -> canonical matched match_id
        self._id_mappings: Dict[str, Dict[str, str]] = {}  # { source: { raw_id: canonical_id } }
        # Inverted index for O(1) candidate lookup by player token/surname
        self._player_index: Dict[str, Set[str]] = {}  # { token: { canonical_match_id } }
        self.match_threshold = match_threshold
        # Synchronous reactive event listeners
        self._score_listeners: List[Callable] = []

    def register_score_listener(self, callback: Callable):
        """Register a callback for instantaneous push notifications on score changes."""
        if callback not in self._score_listeners:
            self._score_listeners.append(callback)

    def _index_match_tokens(self, canonical_id: str, match_name: str):
        """Indexes match player tokens into the inverted index for O(1) lookups."""
        tokens = _tokens_cached(match_name)
        for t in tokens:
            if t not in self._player_index:
                self._player_index[t] = set()
            self._player_index[t].add(canonical_id)

    def _remove_from_index(self, canonical_id: str):
        """Removes a match from the inverted index upon purge."""
        for t in list(self._player_index.keys()):
            self._player_index[t].discard(canonical_id)
            if not self._player_index[t]:
                del self._player_index[t]

    def _find_best_existing_id(self, event: NormalizedEvent) -> Optional[str]:
        """Fast lookup using inverted token index first, falling back to full scan if needed."""
        tokens = _tokens_cached(event.match_name)
        
        # 1. Fast path: check candidate IDs that share tokens
        candidate_ids = set()
        for t in tokens:
            if t in self._player_index:
                candidate_ids.update(self._player_index[t])

        search_pool = candidate_ids if candidate_ids else self._cache.keys()
        
        best_id = None
        best_score = 0.0

        for existing_id in search_pool:
            sources = self._cache.get(existing_id)
            if not sources:
                continue
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
        raw_id = event.match_id
        source = event.source
        now = datetime.now()

        if source not in self._id_mappings:
            self._id_mappings[source] = {}

        # 1. Resolve canonical ID
        canonical_id = raw_id
        if source != "bet365":
            already_paired = (
                canonical_id in self._cache
                and "bet365" in self._cache.get(canonical_id, {})
            )
            if not already_paired:
                prev = self._id_mappings[source].get(raw_id)
                if prev and prev in self._cache:
                    canonical_id = prev
                else:
                    best = self._find_best_existing_id(event)
                    if best:
                        canonical_id = best
                        self._id_mappings[source][raw_id] = canonical_id
        else:
            if canonical_id not in self._cache:
                best = self._find_best_existing_id(event)
                if best:
                    canonical_id = best
                    self._id_mappings[source][raw_id] = canonical_id

        event.match_id = canonical_id

        # 2. Check and align Home/Away player orientation
        if canonical_id in self._cache and self._cache[canonical_id]:
            ref_ev = self._cache[canonical_id].get("bet365") or next(iter(self._cache[canonical_id].values()), None)
            if ref_ev and ref_ev.match_name:
                if source != "bet365":
                    if are_sides_swapped(ref_ev.match_name, event.match_name):
                        _flip_event_orientation(event, ref_ev.match_name)
                else:
                    # Bet365 is the gold standard orientation. Re-align existing sources if needed.
                    for other_src, other_ev in list(self._cache[canonical_id].items()):
                        if other_src != "bet365" and are_sides_swapped(event.match_name, other_ev.match_name):
                            _flip_event_orientation(other_ev, event.match_name)

        # 3. Check for score change and previous state
        if canonical_id not in self._cache:
            self._cache[canonical_id] = {}
            self._last_changed[canonical_id] = {}

        old_ev = self._cache[canonical_id].get(source)
        score_changed = (
            old_ev is None
            or old_ev.game_score != event.game_score
            or old_ev.set_score != event.set_score
        )

        if score_changed:
            self._last_changed[canonical_id][source] = now

        # Update cache and inverted index
        self._cache[canonical_id][source] = event
        self._index_match_tokens(canonical_id, event.match_name)

        # 3. Synchronous reactive event notification (< 50µs)
        if score_changed and self._score_listeners:
            for listener in self._score_listeners:
                try:
                    listener(canonical_id, source, event, old_ev)
                except Exception:
                    pass

    def get_event(self, match_id: str, source: str) -> Optional[NormalizedEvent]:
        return self._cache.get(match_id, {}).get(source)

    def get_all_active_match_ids(self) -> List[str]:
        return list(self._cache.keys())

    def get_last_changed(self, match_id: str, source: str) -> Optional[datetime]:
        return self._last_changed.get(match_id, {}).get(source)

    def clear_stale(self, max_age_seconds: int = 120):
        now = datetime.now()
        for match_id in list(self._cache.keys()):
            sources = self._cache.get(match_id, {})
            # Only clear if all sources are old
            all_stale = True
            for ev in sources.values():
                age = (now - ev.timestamp).total_seconds()
                if age < max_age_seconds:
                    all_stale = False
                    break
            if all_stale:
                del self._cache[match_id]
                self._last_changed.pop(match_id, None)
                self._remove_from_index(match_id)

    def purge_source_missing(self, source: str, current_ids: Set[str]):
        """
        Removes source data from cache keys not present in current_ids.
        Uses canonical ID mappings to ensure accurate tracking.
        """
        source_mapping = self._id_mappings.get(source, {})
        valid_canonical_ids = set()
        for raw_id in current_ids:
            canonical = source_mapping.get(raw_id, raw_id)
            valid_canonical_ids.add(canonical)

        for match_id in list(self._cache.keys()):
            if match_id not in valid_canonical_ids and source in self._cache[match_id]:
                del self._cache[match_id][source]
                if source in self._last_changed.get(match_id, {}):
                    del self._last_changed[match_id][source]
                
                # If match has no more sources, drop it completely
                if not self._cache[match_id]:
                    del self._cache[match_id]
                    self._last_changed.pop(match_id, None)
                    self._remove_from_index(match_id)
