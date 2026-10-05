from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

@dataclass
class PlayerState:
    user_id: int
    name: str
    team: list[str] = field(default_factory=list)
    used: list[str] = field(default_factory=list)
    points: int = 0
    race_choice: Optional[str] = None

@dataclass
class RacerRuntime:
    player_id: int
    racer_key: str
    position: int = 0
    tripped: bool = False
    eliminated: bool = False
    finished_place: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class RaceState:
    race_no: int = 1
    track_kind: str = 'mild'
    racers: dict[int, RacerRuntime] = field(default_factory=dict)
    turn_order: list[int] = field(default_factory=list)
    turn_index: int = 0
    finishers: list[int] = field(default_factory=list)
    turn_start_position: int = 0
    pending_choice: Optional[dict[str, Any]] = None
    group_board_message_ids: list[int] = field(default_factory=list)
    group_status_message_id: Optional[int] = None
    skipper_next: Optional[int] = None

@dataclass
class GameState:
    chat_id: int
    chat_title: str = ''
    status: str = 'lobby'  # lobby/drafting/selecting/racing/finished
    creator_id: int = 0
    players: dict[int, PlayerState] = field(default_factory=dict)
    deck: list[str] = field(default_factory=list)
    draft_pool: list[str] = field(default_factory=list)
    draft_order: list[int] = field(default_factory=list)
    draft_sequence: list[int] = field(default_factory=list)
    draft_cursor: int = 0
    draft_round: int = 0
    race_no: int = 0
    race: Optional[RaceState] = None
    past_winners: list[str] = field(default_factory=list)
    starting_player_id: Optional[int] = None
    lobby_message_id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'GameState':
        players = {
            int(k): PlayerState(**v)
            for k, v in (data.get('players') or {}).items()
        }
        race_data = data.get('race')
        race = None
        if race_data:
            racers = {
                int(k): RacerRuntime(**v)
                for k, v in (race_data.get('racers') or {}).items()
            }
            rd = dict(race_data)
            rd['racers'] = racers
            race = RaceState(**rd)
        obj = cls(
            chat_id=int(data['chat_id']),
            chat_title=data.get('chat_title', ''),
            status=data.get('status', 'lobby'),
            creator_id=int(data.get('creator_id', 0)),
            players=players,
            deck=list(data.get('deck') or []),
            draft_pool=list(data.get('draft_pool') or []),
            draft_order=[int(x) for x in (data.get('draft_order') or [])],
            draft_sequence=[int(x) for x in (data.get('draft_sequence') or [])],
            draft_cursor=int(data.get('draft_cursor', 0)),
            draft_round=int(data.get('draft_round', 0)),
            race_no=int(data.get('race_no', 0)),
            race=race,
            past_winners=list(data.get('past_winners') or []),
            starting_player_id=(int(data['starting_player_id']) if data.get('starting_player_id') is not None else None),
            lobby_message_id=data.get('lobby_message_id'),
        )
        return obj
