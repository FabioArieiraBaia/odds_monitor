from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

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
