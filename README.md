# 魔法運動員 Telegram Bot

這是一個可直接部署到 Render 的 Telegram 群組遊戲 Bot 第一版。

## 目前已完成

- 群組 `/newgame` 開房、加入、開始、取消
- 3–6 人標準模式
- 36 名角色資料（中文名稱＋中文能力摘要）
- 兩輪蛇形選秀，每人 4 名角色
- **私訊 Mini App 圖片選角**：選秀與每場秘密出角都用圖片點選
- 四場比賽：Mild → Wild → Mild → Wild
- 每名角色只能使用一次
- 群組顯示兩張直式連續棋盤，格子較大
- 棋盤會把玩家角色圖示疊到目前格子上
- 每回合群組按「🎲 擲骰 / 行動」
- 需要決策的能力會私訊按鈕詢問玩家
- SQLite 保存進度；Render 可掛 Persistent Disk

## 角色圖片怎麼換

`static/roles/` 裡現在放的是 **36 張測試用佔位圖**。

之後我們每設計好一個正式角色圖，只要用同名 PNG 覆蓋就會自動套用到：

1. 私訊圖片選角頁
2. 群組棋盤上的角色棋子

例如：

```text
static/roles/alchemist.png
static/roles/banana.png
static/roles/rocket_scientist.png
```

完整檔名對照請看 `ROLE_ASSET_NAMES.md`。

## Render 部署

### 1. 建立 Telegram Bot

到 `@BotFather` 建立 Bot，取得 `BOT_TOKEN`。

### 2. 上傳這個專案到 GitHub

Render 建立 **Web Service**，連到這個 Repository。

若使用專案內 `render.yaml`，Render 可直接用 Blueprint 建立。

### 3. 設定環境變數

```env
BOT_TOKEN=你的 Telegram Bot Token
PUBLIC_BASE_URL=https://你的服務名稱.onrender.com
WEBHOOK_SECRET=自己設定一串亂碼
MINIAPP_SECRET=另一串亂碼
DB_PATH=/var/data/magical_athlete.db
```

`PUBLIC_BASE_URL` 必須是 HTTPS，因為 Telegram Mini App 需要 HTTPS。

### 4. Render 啟動指令

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

部署完成後 Bot 啟動時會自動設定 webhook：

```text
https://你的服務名稱.onrender.com/telegram
```

## 群組玩法

```text
/newgame   建立房間
/status    查看目前狀態
/cancel    開房者取消遊戲
```

流程：

```text
開房
→ 玩家加入並先開啟 Bot 私訊
→ 兩輪蛇形選秀
→ 私訊圖片秘密選第 1 場角色
→ 群組公開角色並開始比賽
→ 群組擲骰 / 私訊處理能力選擇
→ 第 1、2 名抵達後結束該場
→ 再私訊選下一名角色
→ 共 4 場
→ 總積分結算
```

## 目前 V1 的幾個簡化

這版的目的先讓整個 Telegram 流程真正跑起來。幾個互動最複雜的能力目前採簡化自動處理，之後可以再逐一改成完全忠於桌遊的互動：

- `Egg`：目前自動抽一個能力，之後可改成私訊 3 選 1
- `Twin`：目前自動模仿上一位冠軍角色，之後可改成私訊選過往冠軍
- `Duelist`：目前同格自動決鬥，之後可改成玩家決定是否決鬥
- `Suckerfish`：目前向前移動時自動跟隨，之後可改成私訊詢問
- `Copy Cat`：並列領先時目前自動選一名，之後可改成私訊選擇
- 現在的 `Wild` 特殊格是配合我們目前畫的 30 格棋盤圖；之後重畫正式 Wild Wilds 圖時，只要修改 `game_engine.py` 的 `WILD_SPACES`

## 專案結構

```text
app.py                 FastAPI + Telegram webhook + Mini App API
bot_handlers.py        Telegram 指令、按鈕、群組/私訊流程
game_engine.py         遊戲規則與角色能力
racers.py              36 名角色資料
models.py              遊戲狀態資料類別
storage.py             SQLite 保存
renderer.py            兩張直式棋盤動態合成角色圖示
security.py            Mini App 選角簽章
assets/
  board_part1.png      棋盤 1–15
  board_part2.png      棋盤 16–30
static/roles/          36 個角色 PNG（之後直接替換成正式圖）
templates/index.html   私訊圖片選角 Mini App
```
