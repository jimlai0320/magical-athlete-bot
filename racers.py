from dataclasses import dataclass

@dataclass(frozen=True)
class RacerDef:
    key: str
    name_en: str
    name_zh: str
    power_zh: str
    power_key: str

RACERS = {
    r.key: r for r in [
        RacerDef('alchemist','Alchemist','鍊金術士','主移動骰出 1 或 2 時，可改成移動 4。','alchemist'),
        RacerDef('blimp','Blimp','飛艇','回合開始時若仍在第二個彎道前，主移動 +3；之後主移動 -1。','blimp'),
        RacerDef('coach','Coach','教練','與教練停在同一格的角色（包含教練）主移動 +1。','coach'),
        RacerDef('baba_yaga','Baba Yaga','芭芭雅嘎','有人停到你的格子，或你停到別人的格子時，使對方絆倒。','baba_yaga'),
        RacerDef('centaur','Centaur','半人馬','你超越其他角色時，對方後退 2 格，不會退到起點之前。','centaur'),
        RacerDef('copy_cat','Copy Cat','複製貓','持續擁有目前領先角色的能力；並列領先時由你選擇。','copy_cat'),
        RacerDef('banana','Banana','香蕉','任何超越你的角色都會絆倒。','banana'),
        RacerDef('cheerleader','Cheerleader','啦啦隊長','主移動前，可讓目前最後一名（並列則全部）前進 2 格；若使用，你再前進 1 格。','cheerleader'),
        RacerDef('dicemonger','Dicemonger','骰子商人','所有角色每回合可重擲一次主移動；其他角色重擲時，你前進 1 格。','dicemonger'),
        RacerDef('duelist','Duelist','決鬥者','與其他角色同格時可決鬥；雙方擲骰，較高者前進 2 格，平手你獲勝。','duelist'),
        RacerDef('genius','Genius','天才','主移動前可預測骰點；猜中則本回合結束後再獲得一個回合。','genius'),
        RacerDef('heckler','Heckler','嘲諷者','任何角色回合結束時距離其回合起點不超過 1 格，你前進 2 格。','heckler'),
        RacerDef('egg','Egg','蛋','比賽開始前，從未使用角色中抽 3 個並選 1 個，暫時獲得其能力。','egg'),
        RacerDef('gunk','Gunk','黏液怪','其他角色的主移動 -1。','gunk'),
        RacerDef('huge_baby','Huge Baby','巨大嬰兒','除了起點外，其他角色不能停在你的格子；若將停到此格，改停到你後一格。','huge_baby'),
        RacerDef('flip_flop','Flip Flop','翻翻鞋','可放棄擲骰主移動，改與任一角色交換位置（傳送）。','flip_flop'),
        RacerDef('hare','Hare','野兔','主移動 +2；若回合開始時單獨領先，跳過主移動。','hare'),
        RacerDef('hypnotist','Hypnotist','催眠師','主移動前，可把一名其他角色傳送到你的格子。','hypnotist'),
        RacerDef('inchworm','Inchworm','尺蠖','其他角色主移動骰出 1 時，取消其主移動，你前進 1 格。','inchworm'),
        RacerDef('legs','Legs','大長腿','可不擲骰，直接把主移動視為 5。','legs'),
        RacerDef('mastermind','Mastermind','智多星','自己的第一回合開始時預測本場冠軍；若猜中，比賽在該角色奪冠時立刻結束，你取得第二名。','mastermind'),
        RacerDef('lackey','Lackey','跟班','其他角色主移動骰出 6 時，在對方移動前你先前進 2 格。','lackey'),
        RacerDef('loveable_loser','Loveable Loser','可愛輸家','主移動前若你單獨最後一名，獲得 1 分。','loveable_loser'),
        RacerDef('mouth','M.O.U.T.H.','大嘴','你停在一格且該格剛好只有另一名角色時，淘汰那名角色。','mouth'),
        RacerDef('leaptoad','Leaptoad','跳跳蟾蜍','移動時跳過所有有其他角色停留的格子；向後移動也一樣。','leaptoad'),
        RacerDef('magician','Magician','魔術師','主移動最多可重擲 2 次，最後一次骰點必須接受。','magician'),
        RacerDef('party_animal','Party Animal','派對動物','主移動前，所有角色向你移動 1 格；同格的其他角色每位讓你主移動 +1。','party_animal'),
        RacerDef('rocket_scientist','Rocket Scientist','火箭科學家','主移動骰出結果後，可把移動值加倍；若加倍，本次移動後你會絆倒。','rocket_scientist'),
        RacerDef('sisyphus','Sisyphus','薛西弗斯','比賽開始前先得 4 分；主移動骰出 6 時不移動，傳送回起點並失去 1 分。','sisyphus'),
        RacerDef('suckerfish','Suckerfish','吸盤魚','與你同格的角色移動時，你可跟著移動到其新位置。','suckerfish'),
        RacerDef('romantic','Romantic','浪漫派','任何角色停在一格且該格剛好有另一名角色時，你前進 2 格。','romantic'),
        RacerDef('skipper','Skipper','船長','任何角色主移動骰出 1 時，你成為下一位行動者。','skipper'),
        RacerDef('third_wheel','Third Wheel','電燈泡','主移動前，可傳送到任一剛好有 2 名角色的格子。','third_wheel'),
        RacerDef('scoocher','Scoocher','挪挪怪','其他角色的能力發動時，你前進 1 格。','scoocher'),
        RacerDef('stickler','Stickler','吹毛求疵鬼','其他角色只有用剛好足夠的移動數才能越過終點；超過所需步數則不移動。','stickler'),
        RacerDef('twin','Twin','雙胞胎','比賽開始前，可選一名之前曾奪冠的角色，暫時獲得其能力。','twin'),
    ]
}

RACER_ORDER = list(RACERS.keys())
