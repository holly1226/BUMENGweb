# 🎭 捕梦（BUMENG）— AI 驱动的多人 TRPG 跑团游戏

一款基于大语言模型的**多人文字冒险游戏**。你和朋友们在 AI 主持人（DM）的引导下，扮演不同角色，共同探索由 AI 实时生成的奇幻世界。

> 支持多人房间、实时对话、场景生图、角色语音等沉浸式 TRPG 体验。

---

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/holly1226/BUMENGweb.git
cd BUMENGweb

# 2. 安装依赖
pip install -r backend/web_requirements.txt
npm install

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 AI API 密钥

# 4. 构建前端
npm run build

# 5. 启动
python backend/web_server.py
```

浏览器打开 → **http://localhost:8000**

> 📖 完整安装说明见 [安装指南](docs/INSTALL.md)

---

## 怎么玩

| 步骤 | 操作 |
|------|------|
| 1️⃣ | 打开页面，输入玩家名 |
| 2️⃣ | 点击「创建房间」生成6位房号 |
| 3️⃣ | 分享房号给朋友，其他人点「加入房间」输入房号 |
| 4️⃣ | 在等待大厅提交世界观偏好和角色意愿 |
| 5️⃣ | 房主（👑标识）点击「开始游戏」 |
| 6️⃣ | 输入行动描述，AI 实时推进剧情 |

> 📖 完整游戏说明见 [游戏指南](docs/GAME_GUIDE.md)

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + Vite + TailwindCSS |
| 后端 | Python + python-socketio + FastAPI |
| AI | DeepSeek / Qwen / GPT-4o |
| 语音 | edge-tts |

---

## 功能特性

- 🏠 **多人房间** — 创建/加入房间，朋友一起玩
- 👑 **房主机制** — 房主控制游戏开始，断线自动转移
- 🎨 **AI 场景生图** — 关键场景自动生成配图
- 🎤 **DM 语音播报** — AI 旁白支持文字转语音
- 🎭 **独立角色卡** — 每个玩家拥有独特角色身份
- 💬 **公屏 + 私密消息** — 公开行动 + DM 悄悄话
- 📱 **移动端适配** — 手机也能流畅游玩

---

## 项目结构

```
BUMENGweb/
├── backend/           # Python 后端
│   ├── web_server.py  # WebSocket + HTTP 服务
│   ├── game_flow.py   # 游戏流程控制
│   ├── engine.py      # 游戏引擎核心
│   ├── ai_handler.py  # AI 接口封装
│   ├── plot_management.py  # 剧情/角色生成
│   └── prompts.py     # AI Prompt 模板
├── src/               # React 前端
│   ├── App.jsx        # 主界面组件
│   └── index.css      # 样式
├── public/            # 静态资源
├── docs/              # 文档
├── package.json       # Node 依赖
└── .env.example       # 配置模板
```

---

*Licensed under MIT*
