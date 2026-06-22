from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class NormalizedEvent:
    match_id: str           # Unique matching key (normalized lowercase names)
    match_name: str         # Full display name: e.g. "J Silva/T Silva vs I Haddouch/C Shalmi"
    sport: str              # "tennis", "basketball", "tabletennis", etc.
    source: str             # "betburger" or "bet365"
    
    # Live stats
    set_score: str          # "0:0", "1:1", "Q4", "P3", etc.
    game_score: str         # "5:4", "88:92", etc.
    point_score: str        # "40:30", "Ad:40", "0" for non-tennis
    
    # Capture Metadata
    timestamp: datetime     # Local time of scrape / ingestion
    
    # Deep link to the specific event page on the bookmaker site
    deep_link: Optional[str] = None
    
    # Extra metadata (odds, market info, etc.)
    extra_data: Dict[str, Any] = field(default_factory=dict)

def test():
    try:
        now = datetime.now()
        event = NormalizedEvent(
            match_id="test_id",
            match_name="Test Match",
            sport="tennis",
            source="betburger",
            set_score="0:0",
            game_score="0:0",
            point_score="0",
            timestamp=now,
            deep_link="http://link",
            extra_data={"raw_text": "test"}
        )
        print("Success:", event)
    except Exception as e:
        print("Failed:", repr(e))

if __name__ == '__main__':
    test()
