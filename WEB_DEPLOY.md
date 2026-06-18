# Web-only TRPG 部署说明

这个复制版已经改成网页端游戏，不需要 Discord Bot、不需要 DISCORD_TOKEN。

## 本地运行

```bash
cd /Users/wholly/Documents/work/TRPGWebDiscordweb
conda activate bumeng
npm run build
python backend/web_server.py
```

打开：

```text
http://localhost:8000
```

网页端主持人指令：

```text
/help
/start
/scene 场景名 | 场景描述
/item 线索名 | 线索详情
/private 玩家名 | 私密内容
```

## 部署结构

Netlify 只部署前端静态文件。

Python 后端需要单独部署到 Render、Railway、Fly.io 或 VPS，因为游戏依赖 Socket.IO 长连接和房间状态。

## 后端部署

推荐 Render Web Service：

Build command:

```bash
pip install -r backend/web_requirements.txt
```

Start command:

```bash
python backend/web_server.py
```

后端会读取平台提供的 `PORT` 环境变量。

## 前端部署到 Netlify

Build command:

```bash
npm run build
```

Publish directory:

```text
dist
```

Netlify 环境变量：

```env
VITE_BACKEND_URL=https://你的后端域名
```

例如：

```env
VITE_BACKEND_URL=https://trpg-web-backend.onrender.com
```

## 本地开发前端连接远程后端

如果只跑前端开发服务器：

```bash
VITE_BACKEND_URL=http://localhost:8000 npm run dev
```

如果前端和后端同域运行，比如 `python backend/web_server.py` 静态托管 `dist`，不用设置 `VITE_BACKEND_URL`。
