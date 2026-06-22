from datetime import datetime
from typing import Dict, Optional, List
from core.normalizer import NormalizedEvent

class StateCache:
    def __init__(self):
        # Format: { match_id: { "bet365": NormalizedEvent, "betburger": NormalizedEvent } }
        self._cache: Dict[str, Dict[str, NormalizedEvent]] = {}
        # Format: { match_id: { "bet365": last_changed_time, "betburger": last_changed_time } }
        self._last_changed: Dict[str, Dict[str, datetime]] = {}

    def update(self, event: NormalizedEvent):
        match_id = event.match_id
        source = event.source
        now = datetime.now()

        if source in ("betburger", "1xbet"):
            best_match_id = match_id
            best_score = 0.0
            
            if match_id not in self._cache:
                import difflib
                
                n2 = event.match_name.lower()
                t2 = set([t for t in n2.replace('/', ' ').replace('-', ' ').replace(',', ' ').split() if len(t) >= 3])
                t2_len = len(t2) if len(t2) > 0 else 1
                
                for existing_id, sources in self._cache.items():
                    if "bet365" in sources:
                        b365_ev = sources["bet365"]
                        n1 = b365_ev.match_name.lower()
                        
                        ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
                        
                        t1 = set([t for t in n1.replace('/', ' ').replace('-', ' ').replace(',', ' ').split() if len(t) >= 3])
                        t1_len = len(t1) if len(t1) > 0 else 1
                        
                        match_count = 0
                        for token1 in t1:
                            for token2 in t2:
                                if token1 in token2 or token2 in token1:
                                    match_count += 1
                                    break
                                    
                        token_ratio = match_count / min(t1_len, t2_len)
                        
                        combined_score = max(ratio, token_ratio)
                        if combined_score > best_score:
                            best_score = combined_score
                            best_match_id = existing_id
                            
                if best_score >= 0.6:
                    match_id = best_match_id
                    event.match_id = match_id # Update the event's internal id to match

        if match_id not in self._cache:
            self._cache[match_id] = {}
            self._last_changed[match_id] = {}

        old_event = self._cache[match_id].get(source)
        self._cache[match_id][source] = event

        # Check if score components actually changed
        if old_event is None or (
            old_event.set_score != event.set_score or
            old_event.game_score != event.game_score or
            old_event.point_score != event.point_score
        ):
            self._last_changed[match_id][source] = now
        elif source not in self._last_changed[match_id]:
            # First initialization without comparison change
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
