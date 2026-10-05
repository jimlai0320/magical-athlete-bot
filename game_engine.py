from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from models import GameState, PlayerState, RaceState, RacerRuntime
from racers import RACERS, RACER_ORDER

FINISH_POS = 31
SECOND_CORNER = 15
RACE_TRACKS = ['mild', 'wild', 'mild', 'wild']
FIRST_POINTS = [3, 4, 4, 5]
SECOND_POINTS = [1, 2, 2, 3]

# 這是目前美術棋盤的 Wild 設定。之後若你重畫正式 Mild/Wild 棋盤，只改這裡即可。
WILD_SPACES: dict[int, tuple[str, int | None]] = {
    2: ('banana', -2),
    5: ('dice', None),
    8: ('portal', 18),
    10: ('trip', None),
    12: ('star', 1),
    15: ('arrow', 2),
    18: ('portal', 23),
    20: ('trip', None),
    23: ('dice', None),
    25: ('arrow', 2),
    27: ('star', 1),
}

@dataclass
class EngineResult:
    logs: list[str] = field(default_factory=list)
    pending: Optional[dict[str, Any]] = None
    race_finished: bool = False
    game_finished: bool = False
    needs_board_refresh: bool = False

class GameEngine:
    def new_game(self, chat_id: int, creator_id: int, creator_name: str, chat_title: str = '') -> GameState:
        g = GameState(chat_id=chat_id, chat_title=chat_title, creator_id=creator_id)
        g.players[creator_id] = PlayerState(user_id=creator_id, name=creator_name)
        return g

    def join(self, game: GameState, user_id: int, name: str) -> tuple[bool, str]:
        if game.status != 'lobby':
            return False, '遊戲已經開始。'
        if user_id in game.players:
            return False, '你已經在房間裡了。'
        if len(game.players) >= 6:
            return False, '這局已經滿 6 人。'
        game.players[user_id] = PlayerState(user_id=user_id, name=name)
        return True, f'{name} 已加入。'

    def start_draft(self, game: GameState) -> EngineResult:
        out = EngineResult()
        n = len(game.players)
        if n < 3:
            out.logs.append('目前版本先支援 3–6 人標準模式。')
            return out
        if game.status != 'lobby':
            out.logs.append('遊戲已經開始。')
            return out
        game.deck = RACER_ORDER.copy()
        random.shuffle(game.deck)
        player_ids = list(game.players.keys())
        random.shuffle(player_ids)
        rolls = {uid: random.randint(1, 6) for uid in player_ids}
        # 同點用隨機後的順序當 tiebreak，避免無限重骰。
        player_ids.sort(key=lambda uid: rolls[uid], reverse=True)
        game.draft_order = player_ids
        game.starting_player_id = player_ids[0]
        game.draft_round = 0
        game.status = 'drafting'
        self._prepare_draft_round(game)
        out.logs.append('🎴 選秀開始！每人最後會拿到 4 名角色。')
        out.logs.append('起始擲骰：' + '、'.join(f'{game.players[u].name}={rolls[u]}' for u in player_ids))
        out.logs.append(f'目前輪到 {game.players[self.current_drafter(game)].name} 選角色。')
        return out

    def _prepare_draft_round(self, game: GameState):
        n = len(game.players)
        need = n * 2
        game.draft_pool = [game.deck.pop() for _ in range(min(need, len(game.deck)))]
        order = game.draft_order[:]
        if game.draft_round == 1:
            order = order[1:] + order[:1]
        game.draft_sequence = order + list(reversed(order))
        game.draft_cursor = 0

    def current_drafter(self, game: GameState) -> Optional[int]:
        if game.status != 'drafting' or game.draft_cursor >= len(game.draft_sequence):
            return None
        return game.draft_sequence[game.draft_cursor]

    def draft_pick(self, game: GameState, user_id: int, racer_key: str) -> EngineResult:
        out = EngineResult()
        if game.status != 'drafting':
            out.logs.append('現在不是選秀階段。')
            return out
        if self.current_drafter(game) != user_id:
            out.logs.append('還沒輪到你選。')
            return out
        if racer_key not in game.draft_pool:
            out.logs.append('這個角色已經被選走了。')
            return out
        game.players[user_id].team.append(racer_key)
        game.draft_pool.remove(racer_key)
        out.logs.append(f'✅ {game.players[user_id].name} 選了 {RACERS[racer_key].name_zh}。')
        game.draft_cursor += 1
        if game.draft_cursor >= len(game.draft_sequence):
            if game.draft_round == 0:
                game.draft_round = 1
                self._prepare_draft_round(game)
                out.logs.append('🔄 第二輪蛇形選秀開始。')
            else:
                game.status = 'selecting'
                game.race_no = 1
                for p in game.players.values():
                    p.race_choice = None
                out.logs.append('🏁 選秀完成！請到私訊選第 1 場要派出的角色。')
                return out
        uid = self.current_drafter(game)
        if uid is not None:
            out.logs.append(f'現在輪到 {game.players[uid].name}。')
        return out

    def race_select(self, game: GameState, user_id: int, racer_key: str) -> EngineResult:
        out = EngineResult()
        if game.status != 'selecting':
            out.logs.append('現在不是選角階段。')
            return out
        p = game.players.get(user_id)
        if not p:
            out.logs.append('你不是這局玩家。')
            return out
        if racer_key not in p.team or racer_key in p.used:
            out.logs.append('這個角色不能在本場使用。')
            return out
        p.race_choice = racer_key
        out.logs.append(f'✅ {p.name} 已完成秘密選角。')
        if all(x.race_choice for x in game.players.values()):
            out.logs.extend(self._start_race(game))
            out.needs_board_refresh = True
        return out

    def _start_race(self, game: GameState) -> list[str]:
        logs: list[str] = []
        track = RACE_TRACKS[game.race_no - 1]
        rs = RaceState(race_no=game.race_no, track_kind=track)
        # 第一場用 draft 起始者；之後由上一場最落後者邏輯可再強化，這版採輪替避免卡局。
        ids = list(game.players.keys())
        if game.starting_player_id in ids:
            i = ids.index(game.starting_player_id)
            ids = ids[i:] + ids[:i]
        rotate = (game.race_no - 1) % len(ids)
        rs.turn_order = ids[rotate:] + ids[:rotate]
        for uid, p in game.players.items():
            key = p.race_choice
            assert key
            rr = RacerRuntime(player_id=uid, racer_key=key)
            rs.racers[uid] = rr
            p.used.append(key)
            p.race_choice = None
            if key == 'sisyphus':
                p.points += 4
                rr.metadata['sisyphus_bonus'] = 4
            if key == 'egg':
                candidates = [k for k in game.deck if k != 'egg']
                random.shuffle(candidates)
                if candidates:
                    rr.metadata['borrowed_power'] = candidates[0]
                    logs.append(f'🥚 {p.name} 的「蛋」本場暫時獲得 {RACERS[candidates[0]].name_zh} 的能力。')
            if key == 'twin' and game.past_winners:
                rr.metadata['borrowed_power'] = game.past_winners[-1]
                logs.append(f'👯 {p.name} 的「雙胞胎」本場模仿上一位冠軍 {RACERS[game.past_winners[-1]].name_zh}。')
        game.race = rs
        game.status = 'racing'
        names = '、'.join(f'{game.players[u].name}＝{RACERS[rs.racers[u].racer_key].name_zh}' for u in rs.turn_order)
        logs.append(f'🏁 第 {game.race_no} 場開始（{"Mild" if track == "mild" else "Wild"}）！')
        logs.append('本場角色：' + names)
        logs.append(f'輪到 {game.players[self.active_player_id(game)].name}。')
        return logs

    def active_player_id(self, game: GameState) -> int:
        assert game.race
        return game.race.turn_order[game.race.turn_index % len(game.race.turn_order)]

    def effective_power(self, game: GameState, rr: RacerRuntime) -> str:
        borrowed = rr.metadata.get('borrowed_power')
        if borrowed:
            return borrowed
        if rr.racer_key != 'copy_cat':
            return rr.racer_key
        active = [r for r in game.race.racers.values() if not r.eliminated and r.finished_place is None and r.player_id != rr.player_id] if game.race else []
        if not active:
            return 'copy_cat'
        lead_pos = max(r.position for r in active)
        leaders = [r for r in active if r.position == lead_pos]
        chosen = rr.metadata.get('copy_choice')
        if chosen and any(r.player_id == chosen for r in leaders):
            return self.effective_power(game, next(r for r in leaders if r.player_id == chosen))
        target = leaders[0]
        rr.metadata['copy_choice'] = target.player_id
        power = self.effective_power(game, target)
        return power if power != 'copy_cat' else target.racer_key

    def request_roll(self, game: GameState, user_id: int) -> EngineResult:
        out = EngineResult()
        if game.status != 'racing' or not game.race:
            out.logs.append('目前沒有進行中的比賽。')
            return out
        if game.race.pending_choice:
            out.logs.append('目前還有一個選擇尚未完成。')
            return out
        if self.active_player_id(game) != user_id:
            out.logs.append('現在不是你的回合。')
            return out
        rr = game.race.racers[user_id]
        if rr.eliminated or rr.finished_place:
            self._advance_turn(game, out.logs)
            return out
        game.race.turn_start_position = rr.position
        power = self.effective_power(game, rr)

        # 絆倒：跳過主移動，但仍算一個回合。
        if rr.tripped:
            rr.tripped = False
            out.logs.append(f'💫 {game.players[user_id].name} 從絆倒中恢復，本回合跳過主移動。')
            self._end_turn(game, rr, out)
            out.needs_board_refresh = True
            return out

        # 每回合前自動能力
        if power == 'loveable_loser' and self._alone_last(game, rr):
            game.players[user_id].points += 1
            out.logs.append('💗 可愛輸家單獨最後一名，獲得 1 分。')
            self._power_happened(game, rr, out.logs)
        if power == 'party_animal':
            self._party_pull(game, rr, out.logs)
            self._power_happened(game, rr, out.logs)
        if power == 'hare' and self._alone_lead(game, rr):
            out.logs.append('🐇 野兔單獨領先，因自滿跳過主移動。')
            self._power_happened(game, rr, out.logs)
            self._end_turn(game, rr, out)
            out.needs_board_refresh = True
            return out

        # 需要玩家決定的「主移動前」能力
        if power == 'mastermind' and not rr.metadata.get('mastermind_prediction'):
            opts = [x.player_id for x in game.race.racers.values() if not x.eliminated]
            return self._set_pending(game, user_id, 'mastermind', opts, '🧠 選擇你預測的本場冠軍。')
        if power == 'genius' and not rr.metadata.get('genius_pred_turn'):
            return self._set_pending(game, user_id, 'genius', [1,2,3,4,5,6], '🧠 預測這次主移動會骰到幾點。')
        if power == 'cheerleader':
            return self._set_pending(game, user_id, 'cheerleader', ['yes','no'], '📣 要替最後一名加油嗎？')
        if power == 'flip_flop':
            opts = ['roll'] + [x.player_id for x in game.race.racers.values() if x.player_id != user_id and not x.eliminated and not x.finished_place]
            return self._set_pending(game, user_id, 'flip_flop', opts, '🩴 要正常擲骰，還是與其他角色交換位置？')
        if power == 'hypnotist':
            opts = ['skip'] + [x.player_id for x in game.race.racers.values() if x.player_id != user_id and not x.eliminated and not x.finished_place]
            return self._set_pending(game, user_id, 'hypnotist', opts, '🌀 要催眠並把一名角色傳送到你的位置嗎？')
        if power == 'legs':
            return self._set_pending(game, user_id, 'legs', ['five','roll'], '🦵 要直接主移動 5 格，還是正常擲骰？')
        if power == 'third_wheel':
            positions: dict[int, list[int]] = {}
            for x in game.race.racers.values():
                if x.eliminated or x.finished_place:
                    continue
                positions.setdefault(x.position, []).append(x.player_id)
            targets = [pos for pos, ids in positions.items() if len(ids) == 2]
            if targets:
                return self._set_pending(game, user_id, 'third_wheel', ['skip'] + targets, '💡 要傳送到剛好有兩名角色的格子嗎？')

        return self._roll_now(game, rr)

    def resolve_choice(self, game: GameState, user_id: int, value: Any) -> EngineResult:
        out = EngineResult()
        if not game.race or not game.race.pending_choice:
            out.logs.append('目前沒有等待中的選擇。')
            return out
        p = game.race.pending_choice
        if p['user_id'] != user_id:
            out.logs.append('這不是你的選擇。')
            return out
        kind = p['kind']
        rr = game.race.racers[user_id]
        game.race.pending_choice = None

        if kind == 'mastermind':
            target = int(value)
            rr.metadata['mastermind_prediction'] = target
            out.logs.append(f'🧠 {game.players[user_id].name} 已完成冠軍預測。')
            self._power_happened(game, rr, out.logs)
            return self.request_roll(game, user_id)
        if kind == 'genius':
            rr.metadata['genius_prediction'] = int(value)
            rr.metadata['genius_pred_turn'] = True
            out.logs.append(f'🧠 天才預測：{value}。')
            self._power_happened(game, rr, out.logs)
            return self._roll_now(game, rr)
        if kind == 'cheerleader':
            if value == 'yes':
                lasts = self._last_place_racers(game)
                for x in lasts:
                    self._move(game, x, 2, out.logs, reason='啦啦隊加油')
                self._move(game, rr, 1, out.logs, reason='啦啦隊跟進')
                self._power_happened(game, rr, out.logs)
            return self._roll_now(game, rr)
        if kind == 'flip_flop':
            if value != 'roll':
                target = game.race.racers[int(value)]
                rr.position, target.position = target.position, rr.position
                out.logs.append(f'🩴 {game.players[user_id].name} 與 {game.players[target.player_id].name} 交換位置。')
                self._power_happened(game, rr, out.logs)
                self._end_turn(game, rr, out)
                out.needs_board_refresh = True
                return out
            return self._roll_now(game, rr)
        if kind == 'hypnotist':
            if value != 'skip':
                target = game.race.racers[int(value)]
                target.position = rr.position
                out.logs.append(f'🌀 {game.players[target.player_id].name} 被傳送到 {rr.position} 格。')
                self._power_happened(game, rr, out.logs)
                self._after_stop(game, target, out.logs)
            return self._roll_now(game, rr)
        if kind == 'legs':
            if value == 'five':
                self._power_happened(game, rr, out.logs)
                return self._execute_main_move(game, rr, roll=5, base_amount=5, logs=out.logs, synthetic_roll=True)
            return self._roll_now(game, rr)
        if kind == 'third_wheel':
            if value != 'skip':
                rr.position = int(value)
                out.logs.append(f'💡 電燈泡傳送到第 {value} 格。')
                self._power_happened(game, rr, out.logs)
                self._after_stop(game, rr, out.logs)
            return self._roll_now(game, rr)
        if kind in ('alchemist','reroll','rocket_scientist'):
            roll = int(p['roll'])
            if kind == 'alchemist':
                amount = 4 if value == 'four' else roll
                if value == 'four':
                    self._power_happened(game, rr, out.logs)
                return self._execute_main_move(game, rr, roll=roll, base_amount=amount, logs=out.logs)
            if kind == 'reroll':
                if value == 'reroll':
                    rr.metadata['rerolls_this_turn'] = int(rr.metadata.get('rerolls_this_turn', 0)) + 1
                    # Dicemonger: 別人重擲時先移動 1。
                    for x in self._active_racers(game):
                        if x.player_id != user_id and self.effective_power(game, x) == 'dicemonger':
                            self._move(game, x, 1, out.logs, reason='骰子商人交易')
                            self._power_happened(game, x, out.logs)
                    return self._roll_now(game, rr, reroll=True)
                return self._post_roll_or_move(game, rr, roll, out.logs, skip_reroll=True)
            if kind == 'rocket_scientist':
                amount = roll * 2 if value == 'double' else roll
                if value == 'double':
                    rr.metadata['trip_after_main'] = True
                    self._power_happened(game, rr, out.logs)
                return self._execute_main_move(game, rr, roll=roll, base_amount=amount, logs=out.logs)

        out.logs.append('未知選擇。')
        return out

    def _set_pending(self, game: GameState, user_id: int, kind: str, options: list[Any], prompt: str, **extra) -> EngineResult:
        assert game.race
        pending = {'user_id': user_id, 'kind': kind, 'options': options, 'prompt': prompt, **extra}
        game.race.pending_choice = pending
        return EngineResult(logs=[prompt], pending=pending)

    def _roll_now(self, game: GameState, rr: RacerRuntime, reroll: bool = False) -> EngineResult:
        out = EngineResult()
        rr.metadata.setdefault('rerolls_this_turn', 0)
        roll = random.randint(1, 6)
        out.logs.append(f'🎲 {game.players[rr.player_id].name} {"重擲" if reroll else "擲出"} {roll}。')
        power = self.effective_power(game, rr)

        # 任何人骰出 1：尺蠖先截斷主移動；船長改變下一位。
        if roll == 1:
            for x in self._active_racers(game):
                if x.player_id != rr.player_id and self.effective_power(game, x) == 'inchworm':
                    self._move(game, x, 1, out.logs, reason='尺蠖蠕動')
                    self._power_happened(game, x, out.logs)
                    out.logs.append('🪱 尺蠖取消了這次主移動。')
                    self._prepare_skipper(game, rr, roll)
                    self._end_turn(game, rr, out)
                    out.needs_board_refresh = True
                    return out
            self._prepare_skipper(game, rr, roll)
        if roll == 6:
            for x in self._active_racers(game):
                if x.player_id != rr.player_id and self.effective_power(game, x) == 'lackey':
                    self._move(game, x, 2, out.logs, reason='跟班先行')
                    self._power_happened(game, x, out.logs)

        if power == 'sisyphus' and roll == 6:
            rr.position = 0
            game.players[rr.player_id].points = max(0, game.players[rr.player_id].points - 1)
            out.logs.append('🪨 薛西弗斯骰出 6，回到起點並失去 1 分。')
            self._power_happened(game, rr, out.logs)
            self._end_turn(game, rr, out)
            out.needs_board_refresh = True
            return out

        # 天才猜中：先記錄額外回合。
        if power == 'genius' and rr.metadata.get('genius_prediction') == roll:
            rr.metadata['extra_turn'] = True
            out.logs.append('✨ 天才猜中了！本回合結束後再行動一次。')
        rr.metadata.pop('genius_prediction', None)

        return self._post_roll_or_move(game, rr, roll, out.logs)

    def _post_roll_or_move(self, game: GameState, rr: RacerRuntime, roll: int, logs: list[str], skip_reroll: bool = False) -> EngineResult:
        power = self.effective_power(game, rr)
        if power == 'alchemist' and roll in (1, 2):
            return self._set_pending(game, rr.player_id, 'alchemist', ['four','keep'], '⚗️ 鍊金術士要把這次移動改成 4 嗎？', roll=roll)
        # 魔術師可重擲兩次；骰子商人在場時所有人都至少有一次重擲。
        max_rerolls = 2 if power == 'magician' else (1 if any(self.effective_power(game, x) == 'dicemonger' for x in self._active_racers(game)) else 0)
        if not skip_reroll and int(rr.metadata.get('rerolls_this_turn', 0)) < max_rerolls:
            return self._set_pending(game, rr.player_id, 'reroll', ['reroll','keep'], f'🎲 要重擲嗎？目前結果是 {roll}。', roll=roll)
        if power == 'rocket_scientist':
            return self._set_pending(game, rr.player_id, 'rocket_scientist', ['double','normal'], f'🚀 要把 {roll} 加倍成 {roll*2} 嗎？使用後會絆倒。', roll=roll)
        return self._execute_main_move(game, rr, roll, roll, logs)

    def _execute_main_move(self, game: GameState, rr: RacerRuntime, roll: int, base_amount: int, logs: list[str], synthetic_roll: bool = False) -> EngineResult:
        out = EngineResult(logs=logs)
        power = self.effective_power(game, rr)
        amount = base_amount
        if power == 'blimp':
            amount += 3 if rr.position < SECOND_CORNER else -1
            self._power_happened(game, rr, out.logs)
        if power == 'hare':
            amount += 2
            self._power_happened(game, rr, out.logs)
        # Coach 同格加成。
        for x in self._active_racers(game):
            if x.position == rr.position and self.effective_power(game, x) == 'coach':
                amount += 1
                self._power_happened(game, x, out.logs)
        # Gunk 對所有其他人 -1。
        for x in self._active_racers(game):
            if x.player_id != rr.player_id and self.effective_power(game, x) == 'gunk':
                amount -= 1
                self._power_happened(game, x, out.logs)
        if power == 'party_animal':
            sharing = sum(1 for x in self._active_racers(game) if x.player_id != rr.player_id and x.position == rr.position)
            amount += sharing
        amount = max(0, amount)
        out.logs.append(f'➡️ 主移動：{amount} 格。')
        self._move(game, rr, amount, out.logs, reason='主移動', main_move=True)
        if rr.metadata.pop('trip_after_main', False):
            rr.tripped = True
            out.logs.append('💥 火箭科學家爆衝後絆倒。')
        out.needs_board_refresh = True
        if self._check_race_end(game, out.logs):
            out.race_finished = True
            if game.status == 'finished':
                out.game_finished = True
            return out
        self._end_turn(game, rr, out)
        return out

    def _move(self, game: GameState, rr: RacerRuntime, steps: int, logs: list[str], reason: str = '移動', main_move: bool = False, depth: int = 0):
        if not game.race or rr.eliminated or rr.finished_place or steps == 0 or depth > 15:
            return
        start = rr.position
        power = self.effective_power(game, rr)

        # Stickler：其他人要剛好抵達終點。
        if steps > 0 and start < FINISH_POS and start + steps >= FINISH_POS:
            sticklers = [x for x in self._active_racers(game) if x.player_id != rr.player_id and self.effective_power(game, x) == 'stickler']
            if sticklers and start + steps != FINISH_POS:
                logs.append('📏 吹毛求疵鬼：步數超過終點，這次不移動。')
                for s in sticklers:
                    self._power_happened(game, s, logs)
                return

        # Leaptoad：有人的格子不計步數，直接跳過。
        if power == 'leaptoad':
            direction = 1 if steps > 0 else -1
            remaining = abs(steps)
            pos = start
            skipped = 0
            while remaining > 0 and -10 < pos < FINISH_POS + 10:
                pos += direction
                occupied = any(x.player_id != rr.player_id and not x.eliminated and not x.finished_place and x.position == pos for x in game.race.racers.values())
                if occupied:
                    skipped += 1
                    continue
                remaining -= 1
            end = pos
            if skipped:
                logs.append(f'🐸 跳跳蟾蜍跳過 {skipped} 個有人停留的格子。')
                self._power_happened(game, rr, logs)
        else:
            end = start + steps
        end = max(0, end)

        # 超越判定以本次完整移動前後為準。
        passed = []
        if end > start:
            for other in self._active_racers(game):
                if other.player_id == rr.player_id:
                    continue
                if start < other.position < end:
                    passed.append(other)

        # 到終點。
        if end >= FINISH_POS:
            rr.position = FINISH_POS
            if rr.finished_place is None:
                rr.finished_place = len(game.race.finishers) + 1
                game.race.finishers.append(rr.player_id)
                logs.append(f'🏆 {game.players[rr.player_id].name} 抵達終點，暫列第 {rr.finished_place} 名！')
                # Mastermind 預測命中時，第一名一產生就直接讓 Mastermind 第二。
                if rr.finished_place == 1:
                    for m in self._active_racers(game):
                        if self.effective_power(game, m) == 'mastermind' and m.metadata.get('mastermind_prediction') == rr.player_id and m.finished_place is None:
                            m.finished_place = 2
                            game.race.finishers.append(m.player_id)
                            logs.append(f'🧠 智多星猜中冠軍，{game.players[m.player_id].name} 直接取得第二名！')
                            self._power_happened(game, m, logs)
            return

        rr.position = end
        logs.append(f'📍 {game.players[rr.player_id].name}：{start} → {rr.position}（{reason}）')

        # 超越相關能力。
        if passed:
            if power == 'centaur':
                for other in passed:
                    old = other.position
                    other.position = max(0, other.position - 2)
                    logs.append(f'🐎 半人馬踢了 {game.players[other.player_id].name}：{old} → {other.position}。')
                self._power_happened(game, rr, logs)
            for other in passed:
                if self.effective_power(game, other) == 'banana':
                    rr.tripped = True
                    logs.append(f'🍌 超越香蕉，{game.players[rr.player_id].name} 絆倒了。')
                    self._power_happened(game, other, logs)

        # Huge Baby：落在它的格子時改停後一格。
        for baby in self._active_racers(game):
            if baby.player_id != rr.player_id and self.effective_power(game, baby) == 'huge_baby' and baby.position == rr.position and rr.position != 0:
                rr.position = max(0, baby.position - 1)
                logs.append(f'👶 巨大嬰兒太巨大，{game.players[rr.player_id].name} 改停在第 {rr.position} 格。')
                self._power_happened(game, baby, logs)
                break

        # Wild 賽道先處理格子，再處理角色停格能力。
        if game.race.track_kind == 'wild':
            self._apply_track_space(game, rr, logs, depth)
            if rr.finished_place or rr.eliminated:
                return
        self._after_stop(game, rr, logs, depth)

        # 吸盤魚：簡化為「若同格角色向前移動，自動跟隨」，日後可改為詢問式。
        if end > start:
            for fish in self._active_racers(game):
                if fish.player_id != rr.player_id and self.effective_power(game, fish) == 'suckerfish' and fish.position == start:
                    fish.position = rr.position
                    logs.append(f'🐟 吸盤魚跟著 {game.players[rr.player_id].name} 到第 {rr.position} 格。')
                    self._power_happened(game, fish, logs)
                    self._after_stop(game, fish, logs, depth + 1)

    def _apply_track_space(self, game: GameState, rr: RacerRuntime, logs: list[str], depth: int):
        effect = WILD_SPACES.get(rr.position)
        if not effect:
            return
        kind, value = effect
        if kind == 'trip':
            rr.tripped = True
            logs.append('🟤 踩到泥巴：絆倒！')
        elif kind == 'star':
            game.players[rr.player_id].points += int(value or 1)
            logs.append('⭐ 星星格：獲得 1 分！')
        elif kind == 'arrow':
            logs.append(f'💨 加速格：再前進 {value} 格。')
            self._move(game, rr, int(value or 0), logs, reason='加速格', depth=depth+1)
        elif kind == 'banana':
            logs.append('🍌 香蕉格：向後滑 2 格。')
            self._move(game, rr, int(value or -2), logs, reason='香蕉格', depth=depth+1)
        elif kind == 'portal':
            target = int(value or rr.position)
            rr.position = target
            logs.append(f'🌀 傳送門：傳送到第 {target} 格。')
        elif kind == 'dice':
            extra = random.randint(1, 6)
            logs.append(f'🎲 骰子格：額外擲出 {extra}，再移動 {extra} 格。')
            self._move(game, rr, extra, logs, reason='骰子格', depth=depth+1)

    def _after_stop(self, game: GameState, rr: RacerRuntime, logs: list[str], depth: int = 0):
        if not game.race or rr.eliminated or rr.finished_place or depth > 15:
            return
        sharing = [x for x in self._active_racers(game) if x.player_id != rr.player_id and x.position == rr.position]
        power = self.effective_power(game, rr)

        # Baba Yaga 自己停到別人的格子。
        if power == 'baba_yaga' and sharing:
            for other in sharing:
                other.tripped = True
                logs.append(f'🧹 芭芭雅嘎使 {game.players[other.player_id].name} 絆倒。')
            self._power_happened(game, rr, logs)
        # 別人停到 Baba Yaga 的格子。
        for other in sharing:
            if self.effective_power(game, other) == 'baba_yaga':
                rr.tripped = True
                logs.append(f'🧹 停到芭芭雅嘎的格子，{game.players[rr.player_id].name} 絆倒。')
                self._power_happened(game, other, logs)

        # MOUTH：剛好一人同格，吞掉對方。
        if power == 'mouth' and len(sharing) == 1:
            victim = sharing[0]
            victim.eliminated = True
            logs.append(f'👄 大嘴把 {game.players[victim.player_id].name} 淘汰出局！')
            self._power_happened(game, rr, logs)

        # Duelist：簡化為自動決鬥，避免 Telegram 回合卡住。
        duelists = []
        if power == 'duelist' and sharing:
            duelists.append((rr, sharing[0]))
        for other in sharing:
            if self.effective_power(game, other) == 'duelist':
                duelists.append((other, rr))
        seen = set()
        for duelist, foe in duelists:
            sig = tuple(sorted((duelist.player_id, foe.player_id)))
            if sig in seen:
                continue
            seen.add(sig)
            a, b = random.randint(1,6), random.randint(1,6)
            win = duelist if a >= b else foe
            logs.append(f'⚔️ 決鬥！{game.players[duelist.player_id].name}={a}、{game.players[foe.player_id].name}={b}，{game.players[win.player_id].name} 前進 2。')
            self._power_happened(game, duelist, logs)
            self._move(game, win, 2, logs, reason='決鬥勝利', depth=depth+1)

        # Romantic：任何剛好兩人同格觸發。
        if len([x for x in self._active_racers(game) if x.position == rr.position]) == 2:
            for romantic in self._active_racers(game):
                if romantic.player_id not in [x.player_id for x in sharing] + [rr.player_id] or True:
                    if self.effective_power(game, romantic) == 'romantic':
                        self._move(game, romantic, 2, logs, reason='浪漫派', depth=depth+1)
                        self._power_happened(game, romantic, logs)

    def _power_happened(self, game: GameState, source: RacerRuntime, logs: list[str]):
        # Scoocher：其他角色能力發動就前進 1。避免由 Scoocher 自己觸發自己。
        if not game.race:
            return
        if self.effective_power(game, source) == 'scoocher':
            return
        for x in list(self._active_racers(game)):
            if x.player_id != source.player_id and self.effective_power(game, x) == 'scoocher':
                # 這裡直接位移，不再呼叫 _power_happened，避免無限迴圈。
                old = x.position
                x.position = min(FINISH_POS, x.position + 1)
                logs.append(f'🦥 挪挪怪因能力發動而移動：{old} → {x.position}。')
                if x.position >= FINISH_POS and x.finished_place is None:
                    x.finished_place = len(game.race.finishers) + 1
                    game.race.finishers.append(x.player_id)

    def _party_pull(self, game: GameState, rr: RacerRuntime, logs: list[str]):
        assert game.race
        for other in self._active_racers(game):
            if other.player_id == rr.player_id:
                continue
            if other.position < rr.position:
                other.position += 1
            elif other.position > rr.position:
                other.position -= 1
        logs.append('🎉 派對動物把所有角色朝自己拉近 1 格。')

    def _prepare_skipper(self, game: GameState, roller: RacerRuntime, roll: int):
        if roll != 1 or not game.race:
            return
        for x in self._active_racers(game):
            if self.effective_power(game, x) == 'skipper':
                game.race.skipper_next = x.player_id
                return

    def _end_turn(self, game: GameState, rr: RacerRuntime, out: EngineResult):
        if not game.race:
            return
        # Heckler：回合結束位置距回合起點 <= 1。
        if abs(rr.position - game.race.turn_start_position) <= 1:
            for x in self._active_racers(game):
                if x.player_id != rr.player_id and self.effective_power(game, x) == 'heckler':
                    self._move(game, x, 2, out.logs, reason='嘲諷者')
                    self._power_happened(game, x, out.logs)
        rr.metadata['rerolls_this_turn'] = 0
        rr.metadata.pop('genius_pred_turn', None)
        if rr.metadata.pop('extra_turn', False) and not rr.eliminated and not rr.finished_place:
            out.logs.append(f'🔁 {game.players[rr.player_id].name} 立刻再獲得一個回合！')
            return
        self._advance_turn(game, out.logs)

    def _advance_turn(self, game: GameState, logs: list[str]):
        assert game.race
        order = game.race.turn_order
        if game.race.skipper_next in order:
            game.race.turn_index = order.index(game.race.skipper_next)
            game.race.skipper_next = None
        else:
            # 找下一個尚未出局/完賽的玩家。
            for _ in range(len(order)):
                game.race.turn_index = (game.race.turn_index + 1) % len(order)
                uid = order[game.race.turn_index]
                rr = game.race.racers[uid]
                if not rr.eliminated and not rr.finished_place:
                    break
        if game.status == 'racing' and game.race:
            logs.append(f'➡️ 下一位：{game.players[self.active_player_id(game)].name}')

    def _check_race_end(self, game: GameState, logs: list[str]) -> bool:
        if not game.race:
            return False
        active_left = [x for x in game.race.racers.values() if not x.eliminated and not x.finished_place]
        if len(game.race.finishers) < 2 and len(active_left) > 1:
            return False
        if len(game.race.finishers) == 1 and len(active_left) == 1:
            # 已有冠軍且只剩一人，自動視為第二。
            last = active_left[0]
            last.finished_place = 2
            game.race.finishers.append(last.player_id)
        elif len(game.race.finishers) == 0 and len(active_left) == 1:
            # 其他人都被淘汰，只剩一人，該角色取得第一名。
            last = active_left[0]
            last.finished_place = 1
            game.race.finishers.append(last.player_id)
        if not game.race.finishers:
            logs.append('本場沒有角色完成比賽。')
        if len(game.race.finishers) >= 1:
            first_uid = game.race.finishers[0]
            game.players[first_uid].points += FIRST_POINTS[game.race_no - 1]
            winner_key = game.race.racers[first_uid].racer_key
            game.past_winners.append(winner_key)
            logs.append(f'🥇 {game.players[first_uid].name} +{FIRST_POINTS[game.race_no - 1]} 分')
        if len(game.race.finishers) >= 2:
            second_uid = game.race.finishers[1]
            game.players[second_uid].points += SECOND_POINTS[game.race_no - 1]
            logs.append(f'🥈 {game.players[second_uid].name} +{SECOND_POINTS[game.race_no - 1]} 分')
        if game.race_no >= 4:
            game.status = 'finished'
            scores = sorted(game.players.values(), key=lambda p: p.points, reverse=True)
            logs.append('🎊 四場比賽全部結束！')
            logs.append('最終積分：' + '、'.join(f'{p.name} {p.points}分' for p in scores))
        else:
            game.race_no += 1
            game.status = 'selecting'
            for p in game.players.values():
                p.race_choice = None
            logs.append(f'➡️ 請到私訊選擇第 {game.race_no} 場的角色。')
        return True

    def _active_racers(self, game: GameState) -> list[RacerRuntime]:
        if not game.race:
            return []
        return [x for x in game.race.racers.values() if not x.eliminated and not x.finished_place]

    def _alone_lead(self, game: GameState, rr: RacerRuntime) -> bool:
        active = self._active_racers(game)
        return bool(active) and rr.position == max(x.position for x in active) and sum(x.position == rr.position for x in active) == 1

    def _last_place_racers(self, game: GameState) -> list[RacerRuntime]:
        active = self._active_racers(game)
        if not active:
            return []
        pos = min(x.position for x in active)
        return [x for x in active if x.position == pos]

    def _alone_last(self, game: GameState, rr: RacerRuntime) -> bool:
        lasts = self._last_place_racers(game)
        return len(lasts) == 1 and lasts[0].player_id == rr.player_id

    def standings(self, game: GameState) -> list[tuple[str, int, str]]:
        if not game.race:
            return []
        rows = []
        for rr in game.race.racers.values():
            status = '淘汰' if rr.eliminated else (f'第{rr.finished_place}名' if rr.finished_place else f'{rr.position}格')
            rows.append((game.players[rr.player_id].name, rr.position, status))
        return sorted(rows, key=lambda r: r[1], reverse=True)
