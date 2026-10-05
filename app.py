from __future__ import annotations
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update
from telegram.ext import Application

from bot_handlers import BotService, register_handlers
from game_engine import GameEngine
from renderer import BoardRenderer
from storage import GameStore
from racers import RACERS
from security import verify

BASE_DIR=Path(__file__).resolve().parent
BOT_TOKEN=os.getenv('BOT_TOKEN','')
PUBLIC_BASE_URL=os.getenv('PUBLIC_BASE_URL','').rstrip('/')
WEBHOOK_URL=os.getenv('WEBHOOK_URL','').rstrip('/') or (f'{PUBLIC_BASE_URL}/telegram' if PUBLIC_BASE_URL else '')
WEBHOOK_SECRET=os.getenv('WEBHOOK_SECRET','')

if not BOT_TOKEN:
    raise RuntimeError('缺少 BOT_TOKEN 環境變數')

store=GameStore()
engine=GameEngine()
renderer=BoardRenderer()
service=BotService(store,engine,renderer)
ptb=Application.builder().token(BOT_TOKEN).build()
register_handlers(ptb,service)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await ptb.initialize()
    await ptb.start()
    await service.setup_commands(ptb)
    if WEBHOOK_URL:
        kwargs={}
        if WEBHOOK_SECRET:
            kwargs['secret_token']=WEBHOOK_SECRET
        await ptb.bot.set_webhook(WEBHOOK_URL,drop_pending_updates=False,**kwargs)
    yield
    if WEBHOOK_URL:
        try: await ptb.bot.delete_webhook(drop_pending_updates=False)
        except Exception: pass
    await ptb.stop()
    await ptb.shutdown()

app=FastAPI(title='Magical Athlete Telegram Bot',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=BASE_DIR/'static'),name='static')

@app.get('/',response_class=HTMLResponse)
async def root():
    return '<h2>Magical Athlete Bot is alive ✅</h2>'

@app.get('/health')
async def health():
    return {'ok':True}

@app.get('/miniapp',response_class=HTMLResponse)
async def miniapp():
    return (BASE_DIR/'templates'/'index.html').read_text(encoding='utf-8')

@app.get('/api/options')
async def api_options(chat_id:int,user_id:int,mode:str,token:str):
    if mode not in ('draft','race') or not verify(chat_id,user_id,mode,token):
        raise HTTPException(403,'驗證失敗')
    game=store.load(chat_id)
    if not game:
        raise HTTPException(404,'找不到遊戲')
    if user_id not in game.players:
        raise HTTPException(403,'你不是這局玩家')
    if mode=='draft':
        if game.status!='drafting' or engine.current_drafter(game)!=user_id:
            raise HTTPException(409,'目前還沒輪到你選秀')
        keys=list(game.draft_pool)
        notice=f'目前可選 {len(keys)} 名角色；選下去後不能更改。'
    else:
        if game.status!='selecting':
            raise HTTPException(409,'目前不是比賽選角階段')
        p=game.players[user_id]
        keys=[k for k in p.team if k not in p.used]
        notice=f'第 {game.race_no} 場：選擇一名尚未使用的角色。'
    return {
        'notice':notice,
        'options':[
            {'key':k,'name':RACERS[k].name_zh,'power':RACERS[k].power_zh,'image':f'/static/roles/{k}.png'}
            for k in keys
        ]
    }

@app.post('/telegram')
async def telegram_webhook(request: Request):
    if WEBHOOK_SECRET:
        supplied=request.headers.get('X-Telegram-Bot-Api-Secret-Token','')
        if supplied!=WEBHOOK_SECRET:
            raise HTTPException(403,'bad webhook secret')
    payload=await request.json()
    update=Update.de_json(payload,ptb.bot)
    await ptb.process_update(update)
    return {'ok':True}

if __name__=='__main__':
    import uvicorn
    uvicorn.run('app:app',host='0.0.0.0',port=int(os.getenv('PORT','10000')),reload=False)
