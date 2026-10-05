from __future__ import annotations
import asyncio
import json
import os
from collections import defaultdict
from typing import Any

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, InputFile, InputMediaPhoto,
)
from telegram.constants import ChatType, ParseMode
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)

from game_engine import GameEngine
from storage import GameStore
from renderer import BoardRenderer
from racers import RACERS
from security import sign, verify

PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')

class BotService:
    def __init__(self, store: GameStore, engine: GameEngine, renderer: BoardRenderer):
        self.store=store; self.engine=engine; self.renderer=renderer
        self.locks=defaultdict(asyncio.Lock)

    async def setup_commands(self, app: Application):
        await app.bot.set_my_commands([
            ('newgame','在群組建立新遊戲'),
            ('status','查看目前遊戲狀態'),
            ('cancel','取消目前遊戲'),
            ('start','啟動私訊選角功能'),
        ])

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type != ChatType.PRIVATE:
            return
        user=update.effective_user
        args=context.args
        msg='🎲 <b>魔法運動員 Bot</b>\n\n私訊已啟用。之後選秀、每場秘密選角與特殊能力選擇都可以在這裡完成。'
        if args and args[0].startswith('g_'):
            try:
                chat_id=int(args[0][2:])
                game=self.store.load(chat_id)
                if game and game.status=='lobby':
                    ok,text=self.engine.join(game,user.id,user.full_name)
                    if ok: self.store.save(game)
                    msg += f'\n\n{text}'
                    if ok:
                        await self._refresh_lobby(context,game)
            except Exception:
                pass
        await update.message.reply_text(msg,parse_mode=ParseMode.HTML)

    async def newgame(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat=update.effective_chat; user=update.effective_user
        if chat.type not in (ChatType.GROUP,ChatType.SUPERGROUP):
            await update.message.reply_text('請在群組裡使用 /newgame。')
            return
        async with self.locks[chat.id]:
            old=self.store.load(chat.id)
            if old and old.status!='finished':
                await update.message.reply_text('這個群組已經有一局進行中；要重開請先 /cancel。')
                return
            game=self.engine.new_game(chat.id,user.id,user.full_name,chat.title or '')
            self.store.save(game)
            sent=await update.message.reply_text(self._lobby_text(game),reply_markup=await self._lobby_keyboard(context,game))
            game.lobby_message_id=sent.message_id
            self.store.save(game)

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        game=self.store.load(update.effective_chat.id)
        if not game:
            await update.message.reply_text('目前沒有遊戲。')
            return
        await update.message.reply_text(self._status_text(game))

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        game=self.store.load(update.effective_chat.id)
        if not game:
            await update.message.reply_text('目前沒有遊戲。')
            return
        if update.effective_user.id != game.creator_id:
            await update.message.reply_text('只有開房者可以取消。')
            return
        self.store.delete(game.chat_id)
        await update.message.reply_text('🗑️ 已取消這局。')

    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q=update.callback_query
        await q.answer()
        data=q.data or ''
        chat_id=q.message.chat_id if q.message else update.effective_chat.id
        # ability choice callback normally arrives from private chat, so payload contains group id.
        if data.startswith('choice|'):
            parts=data.split('|',2)
            chat_id=int(parts[1]); value=parts[2]
            async with self.locks[chat_id]:
                game=self.store.load(chat_id)
                if not game: return
                result=self.engine.resolve_choice(game,q.from_user.id,value)
                self.store.save(game)
                await q.edit_message_reply_markup(reply_markup=None)
                await self._announce_result(context,game,result)
            return

        async with self.locks[chat_id]:
            game=self.store.load(chat_id)
            if not game:
                await q.answer('找不到遊戲',show_alert=True); return
            if data=='join':
                ok,text=self.engine.join(game,q.from_user.id,q.from_user.full_name)
                self.store.save(game)
                await q.answer(text,show_alert=not ok)
                await self._refresh_lobby(context,game)
                if ok:
                    await self._ensure_private(context,q.from_user.id,game.chat_id)
            elif data=='startgame':
                if q.from_user.id != game.creator_id:
                    await q.answer('只有開房者可以開始',show_alert=True); return
                result=self.engine.start_draft(game)
                self.store.save(game)
                await self._send_logs(context,game.chat_id,result.logs)
                if game.status=='drafting':
                    await self._prompt_current_drafter(context,game)
                    await self._refresh_lobby(context,game,force_text=self._draft_text(game))
            elif data=='cancelgame':
                if q.from_user.id != game.creator_id:
                    await q.answer('只有開房者可以取消',show_alert=True); return
                self.store.delete(game.chat_id)
                await q.edit_message_text('🗑️ 本局已取消。')
            elif data=='roll':
                result=self.engine.request_roll(game,q.from_user.id)
                self.store.save(game)
                await self._announce_result(context,game,result)
            elif data=='refresh':
                await self._refresh_status_message(context,game)

    async def web_app_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg=update.effective_message
        if not msg or not msg.web_app_data:
            return
        try:
            payload=json.loads(msg.web_app_data.data)
            action=payload['action']; chat_id=int(payload['chat_id']); racer_key=payload['racer_key']; token=payload.get('token','')
            mode='draft' if action=='draft_pick' else 'race'
            if not verify(chat_id,update.effective_user.id,mode,token):
                await msg.reply_text('⚠️ 選角連結驗證失敗，請重新開啟。'); return
        except Exception:
            await msg.reply_text('⚠️ 無法讀取選角資料。'); return
        async with self.locks[chat_id]:
            game=self.store.load(chat_id)
            if not game:
                await msg.reply_text('這局已不存在。'); return
            if action=='draft_pick':
                result=self.engine.draft_pick(game,update.effective_user.id,racer_key)
                self.store.save(game)
                await msg.reply_text('\n'.join(result.logs))
                await self._send_logs(context,chat_id,result.logs[:1])
                if game.status=='drafting':
                    await self._prompt_current_drafter(context,game)
                    await self._refresh_lobby(context,game,force_text=self._draft_text(game))
                elif game.status=='selecting':
                    await self._refresh_lobby(context,game,force_text=self._selection_text(game))
                    await self._prompt_race_selection_all(context,game)
            elif action=='race_pick':
                result=self.engine.race_select(game,update.effective_user.id,racer_key)
                self.store.save(game)
                await msg.reply_text('\n'.join(result.logs))
                if game.status=='racing':
                    await self._send_logs(context,chat_id,result.logs)
                    await self._send_or_update_board(context,game,force_new=True)
                    await self._refresh_status_message(context,game,force_new=True)
                else:
                    await self._refresh_lobby(context,game,force_text=self._selection_text(game))

    async def _announce_result(self, context: ContextTypes.DEFAULT_TYPE, game, result):
        if result.logs:
            await self._send_logs(context,game.chat_id,result.logs)
        # pending ability decision
        if result.pending:
            await self._send_pending_choice(context,game,result.pending)
        if result.needs_board_refresh and game.race:
            await self._send_or_update_board(context,game)
        if game.status=='racing':
            await self._refresh_status_message(context,game)
        elif game.status=='selecting':
            await self._refresh_lobby(context,game,force_text=self._selection_text(game))
            await self._prompt_race_selection_all(context,game)
        elif game.status=='finished':
            await self._send_logs(context,game.chat_id,[self._final_text(game)])

    async def _send_pending_choice(self, context, game, pending):
        uid=pending['user_id']; kind=pending['kind']; options=pending['options']
        rows=[]
        labels=self._choice_labels(game,kind,options)
        row=[]
        for val,label in labels:
            row.append(InlineKeyboardButton(label,callback_data=f'choice|{game.chat_id}|{val}'))
            if len(row)==2:
                rows.append(row); row=[]
        if row: rows.append(row)
        try:
            await context.bot.send_message(uid,pending['prompt'],reply_markup=InlineKeyboardMarkup(rows))
        except Forbidden:
            await context.bot.send_message(game.chat_id,f'⚠️ {game.players[uid].name} 必須先私訊 Bot /start，才能完成能力選擇。')

    def _choice_labels(self, game, kind, options):
        if kind=='genius': return [(str(x),str(x)) for x in options]
        if kind=='mastermind': return [(str(x),game.players[int(x)].name) for x in options]
        if kind=='cheerleader': return [('yes','📣 加油'),('no','略過')]
        if kind=='flip_flop': return [(str(x),'🎲 正常擲骰' if x=='roll' else f'交換：{game.players[int(x)].name}') for x in options]
        if kind=='hypnotist': return [(str(x),'略過' if x=='skip' else f'🌀 {game.players[int(x)].name}') for x in options]
        if kind=='legs': return [('five','🦵 直接走 5'),('roll','🎲 正常擲骰')]
        if kind=='third_wheel': return [(str(x),'略過' if x=='skip' else f'傳送到第 {x} 格') for x in options]
        if kind=='alchemist': return [('four','⚗️ 改成 4'),('keep','保留骰點')]
        if kind=='reroll': return [('reroll','🎲 重擲'),('keep','✅ 接受')]
        if kind=='rocket_scientist': return [('double','🚀 加倍'),('normal','正常移動')]
        return [(str(x),str(x)) for x in options]

    async def _ensure_private(self, context, user_id:int, chat_id:int):
        try:
            await context.bot.send_message(user_id,'✅ 已加入群組遊戲。選秀開始時我會在這裡通知你。')
        except Forbidden:
            me=await context.bot.get_me()
            url=f'https://t.me/{me.username}?start=g_{chat_id}'
            await context.bot.send_message(chat_id,f'⚠️ 請先開啟 Bot 私訊，否則無法使用圖片選角：{url}')

    async def _prompt_current_drafter(self, context, game):
        uid=self.engine.current_drafter(game)
        if uid is None: return
        await self._send_webapp_button(context,game,uid,'draft','🎴 用圖片選角色')

    async def _prompt_race_selection_all(self, context, game):
        for uid,p in game.players.items():
            if not p.race_choice:
                await self._send_webapp_button(context,game,uid,'race',f'🏁 選第 {game.race_no} 場角色')

    async def _send_webapp_button(self, context, game, uid:int, mode:str, text:str):
        if not PUBLIC_BASE_URL:
            await context.bot.send_message(game.chat_id,'⚠️ 尚未設定 PUBLIC_BASE_URL，圖片選角頁無法開啟。')
            return
        token=sign(game.chat_id,uid,mode)
        url=f'{PUBLIC_BASE_URL}/miniapp?chat_id={game.chat_id}&user_id={uid}&mode={mode}&token={token}'
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(text,web_app=WebAppInfo(url=url))]])
        try:
            extra = '目前輪到你選秀。' if mode=='draft' else '你的選擇是秘密的，等所有人選完才會公開。'
            await context.bot.send_message(uid,extra,reply_markup=kb)
        except Forbidden:
            me=await context.bot.get_me()
            deep=f'https://t.me/{me.username}?start=g_{game.chat_id}'
            await context.bot.send_message(game.chat_id,f'⚠️ {game.players[uid].name} 尚未啟用私訊：{deep}')

    async def _send_or_update_board(self, context, game, force_new=False):
        if not game.race: return
        top,bottom=self.renderer.render(game)
        ids=game.race.group_board_message_ids
        if ids and len(ids)==2 and not force_new:
            try:
                await context.bot.edit_message_media(chat_id=game.chat_id,message_id=ids[0],media=InputMediaPhoto(InputFile(top,filename='board_top.jpg')))
                await context.bot.edit_message_media(chat_id=game.chat_id,message_id=ids[1],media=InputMediaPhoto(InputFile(bottom,filename='board_bottom.jpg')))
                return
            except BadRequest:
                pass
        m1=await context.bot.send_photo(game.chat_id,photo=InputFile(top,filename='board_top.jpg'),caption='🎮 棋盤上半部')
        m2=await context.bot.send_photo(game.chat_id,photo=InputFile(bottom,filename='board_bottom.jpg'),caption='🎮 棋盤下半部')
        game.race.group_board_message_ids=[m1.message_id,m2.message_id]
        self.store.save(game)

    async def _refresh_status_message(self, context, game, force_new=False):
        if not game.race: return
        text=self._race_status_text(game)
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('🎲 擲骰 / 行動',callback_data='roll'),InlineKeyboardButton('🔄 更新',callback_data='refresh')]])
        mid=game.race.group_status_message_id
        if mid and not force_new:
            try:
                await context.bot.edit_message_text(text,game.chat_id,mid,reply_markup=kb)
                return
            except BadRequest:
                pass
        sent=await context.bot.send_message(game.chat_id,text,reply_markup=kb)
        game.race.group_status_message_id=sent.message_id
        self.store.save(game)

    async def _refresh_lobby(self, context, game, force_text=None):
        if not game.lobby_message_id: return
        text=force_text or self._lobby_text(game)
        kb=None
        if game.status=='lobby': kb=await self._lobby_keyboard(context,game)
        try:
            await context.bot.edit_message_text(text,game.chat_id,game.lobby_message_id,reply_markup=kb)
        except BadRequest:
            pass

    async def _lobby_keyboard(self, context, game):
        me=await context.bot.get_me()
        deep=f'https://t.me/{me.username}?start=g_{game.chat_id}'
        return InlineKeyboardMarkup([
            [InlineKeyboardButton('➕ 加入',callback_data='join'),InlineKeyboardButton('💬 開啟私訊',url=deep)],
            [InlineKeyboardButton('🏁 開始選秀',callback_data='startgame'),InlineKeyboardButton('❌ 取消',callback_data='cancelgame')]
        ])

    def _lobby_text(self, game):
        names='\n'.join(f'{i+1}. {p.name}' for i,p in enumerate(game.players.values()))
        return f'🏃 魔法運動員\n\n玩家 {len(game.players)}/6\n{names}\n\n3–6 人即可開始。加入後請先開啟 Bot 私訊。'

    def _draft_text(self, game):
        uid=self.engine.current_drafter(game)
        lines=['🎴 角色選秀',f'第 {game.draft_round+1}/2 輪','']
        for p in game.players.values():
            lines.append(f'{p.name}：{len(p.team)}/4')
        if uid: lines += ['',f'目前輪到：{game.players[uid].name}']
        return '\n'.join(lines)

    def _selection_text(self, game):
        lines=[f'🏁 第 {game.race_no} 場秘密選角','']
        for p in game.players.values(): lines.append(f'{p.name}：{"✅ 已選" if p.race_choice else "⏳ 選擇中"}')
        return '\n'.join(lines)

    def _status_text(self, game):
        if game.status=='lobby': return self._lobby_text(game)
        if game.status=='drafting': return self._draft_text(game)
        if game.status=='selecting': return self._selection_text(game)
        if game.status=='racing': return self._race_status_text(game)
        return self._final_text(game)

    def _race_status_text(self, game):
        r=game.race
        active=game.players[r.turn_order[r.turn_index]].name
        standings=self.engine.standings(game)
        rank='\n'.join(f'{i+1}. {n} — {s}' for i,(n,_,s) in enumerate(standings))
        pending='\n⏳ 等待能力選擇中…' if r.pending_choice else ''
        return f'🏁 第 {game.race_no} 場（{"Mild" if r.track_kind=="mild" else "Wild"}）\n🎯 輪到：{active}{pending}\n\n{rank}'

    def _final_text(self, game):
        scores=sorted(game.players.values(),key=lambda p:p.points,reverse=True)
        return '🏆 最終排名\n'+'\n'.join(f'{i+1}. {p.name} — {p.points} 分' for i,p in enumerate(scores))

    async def _send_logs(self, context, chat_id:int, logs:list[str]):
        if not logs: return
        text='\n'.join(logs)
        # Telegram 單則訊息長度保守切段。
        while text:
            chunk=text[:3500]
            cut=chunk.rfind('\n')
            if cut>2000: chunk=chunk[:cut]
            await context.bot.send_message(chat_id,chunk)
            text=text[len(chunk):].lstrip('\n')


def register_handlers(app: Application, service: BotService):
    app.add_handler(CommandHandler('start',service.start))
    app.add_handler(CommandHandler('newgame',service.newgame))
    app.add_handler(CommandHandler('status',service.status))
    app.add_handler(CommandHandler('cancel',service.cancel))
    app.add_handler(CallbackQueryHandler(service.callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA,service.web_app_data))
