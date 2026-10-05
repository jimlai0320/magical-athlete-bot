from __future__ import annotations
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

from models import GameState
from racers import RACERS

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / 'assets'
ROLE_DIR = BASE_DIR / 'static' / 'roles'
FONT_REG = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
FONT_BOLD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'

# 對應目前兩張 941x1672 直式棋盤。之後換美術時只要調這張表。
POS_1 = {
    0:(150,330), 1:(350,300), 2:(500,300), 3:(645,300), 4:(795,330),
    5:(790,555), 6:(790,760), 7:(790,960), 8:(790,1180),
    9:(210,1420), 10:(190,1240), 11:(190,1060), 12:(190,900),
    13:(190,750), 14:(190,610), 15:(190,470),
}
POS_2 = {
    16:(220,300), 17:(220,445), 18:(220,595), 19:(220,760), 20:(220,920),
    21:(220,1080), 22:(220,1235), 23:(790,560), 24:(790,735), 25:(790,900),
    26:(790,1060), 27:(790,1225), 28:(790,1390), 29:(610,1460), 30:(440,1460),
    31:(170,1450),
}
PLAYER_COLORS = ['#e74c3c','#3498db','#2ecc71','#9b59b6','#f39c12','#16a085']

class BoardRenderer:
    def __init__(self):
        self.base1 = Image.open(ASSET_DIR / 'board_part1.png').convert('RGBA')
        self.base2 = Image.open(ASSET_DIR / 'board_part2.png').convert('RGBA')

    def render(self, game: GameState) -> tuple[BytesIO, BytesIO]:
        a = self.base1.copy()
        b = self.base2.copy()
        if game.race:
            ids = list(game.race.turn_order)
            for i, uid in enumerate(ids):
                rr = game.race.racers[uid]
                color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
                if rr.position <= 15:
                    self._paste_token(a, rr.position, rr.racer_key, game.players[uid].name, color, uid == game.race.turn_order[game.race.turn_index])
                else:
                    self._paste_token(b, min(rr.position,31), rr.racer_key, game.players[uid].name, color, uid == game.race.turn_order[game.race.turn_index])
            self._draw_hud(a, game)
            self._draw_hud(b, game, compact=True)
        return self._to_png(a), self._to_png(b)

    def _paste_token(self, img: Image.Image, pos: int, racer_key: str, player_name: str, color: str, active: bool):
        coord = POS_1.get(pos) if pos <= 15 else POS_2.get(pos)
        if not coord:
            return
        role_path = ROLE_DIR / f'{racer_key}.png'
        token_size = 108 if pos not in (0,31) else 118
        if role_path.exists():
            token = Image.open(role_path).convert('RGBA')
            token = ImageOps.fit(token, (token_size, token_size), method=Image.Resampling.LANCZOS)
        else:
            token = Image.new('RGBA',(token_size,token_size),(0,0,0,0))
            d = ImageDraw.Draw(token)
            d.ellipse((4,4,token_size-4,token_size-4), fill=color, outline='white', width=8)
            f = ImageFont.truetype(FONT_BOLD, 28)
            text = RACERS[racer_key].name_zh[:2]
            box = d.textbbox((0,0),text,font=f)
            d.text(((token_size-(box[2]-box[0]))/2,(token_size-(box[3]-box[1]))/2-4),text,font=f,fill='white')
        # 外框表示玩家顏色，金框表示當前回合。
        framed = Image.new('RGBA',(token_size+14,token_size+14),(0,0,0,0))
        fd = ImageDraw.Draw(framed)
        fd.ellipse((1,1,token_size+12,token_size+12), fill=color, outline=('#ffd700' if active else '#ffffff'), width=(7 if active else 4))
        mask = Image.new('L',(token_size,token_size),0)
        md = ImageDraw.Draw(mask); md.ellipse((0,0,token_size-1,token_size-1),fill=255)
        token.putalpha(Image.composite(token.getchannel('A'), Image.new('L',(token_size,token_size),0), mask))
        framed.alpha_composite(token,(7,7))
        x,y=coord
        img.alpha_composite(framed,(int(x-framed.width/2),int(y-framed.height/2)))
        # 名字短標籤
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(FONT_BOLD, 22)
        label = player_name[:8]
        bb = d.textbbox((0,0),label,font=f)
        w=bb[2]-bb[0]+18; h=34
        lx=int(x-w/2); ly=int(y+framed.height/2-8)
        d.rounded_rectangle((lx,ly,lx+w,ly+h),radius=10,fill=(255,255,255,235),outline=color,width=3)
        d.text((lx+9,ly+2),label,font=f,fill='#111111')

    def _draw_hud(self, img: Image.Image, game: GameState, compact: bool=False):
        d = ImageDraw.Draw(img)
        f1 = ImageFont.truetype(FONT_BOLD, 27 if not compact else 23)
        f2 = ImageFont.truetype(FONT_REG, 21 if not compact else 19)
        title = f'第 {game.race_no} 場  {"Mild" if game.race.track_kind=="mild" else "Wild"}'
        active = game.players[game.race.turn_order[game.race.turn_index]].name
        scores = sorted(game.players.values(), key=lambda p:p.points, reverse=True)
        score_text='  '.join(f'{p.name}:{p.points}' for p in scores)
        x,y=(330,560) if not compact else (330,680)
        w,h=(420,150) if not compact else (420,128)
        d.rounded_rectangle((x,y,x+w,y+h),radius=24,fill=(255,255,255,225),outline='#111111',width=4)
        d.text((x+18,y+12),title,font=f1,fill='#111111')
        d.text((x+18,y+55),f'輪到：{active}',font=f2,fill='#111111')
        d.text((x+18,y+88),f'積分：{score_text[:28]}',font=f2,fill='#111111')

    @staticmethod
    def _to_png(img: Image.Image) -> BytesIO:
        buf=BytesIO(); img.convert('RGB').save(buf,format='JPEG',quality=90,optimize=True); buf.seek(0); buf.name='board.jpg'; return buf
