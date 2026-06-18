# 🔧 安装与启动指南

## 环境要求

- **Python** ≥ 3.9
- **Node.js** ≥ 18
- **Git**

---

## 一、首次安装

### 1. 克隆项目

```bash
git clone https://github.com/holly1226/BUMENGweb.git
cd BUMENGweb
```

### 2. 安装 Python 依赖

```bash
pip install -r backend/web_requirements.txt
```

### 3. 安装 Node 依赖

```bash
npm install
```

### 4. 配置 API 密钥

```bash
# 复制模板文件
cp .env.example .env
```

编辑 `.env` 文件，填入你的 AI API Key（**至少配一个**）：

```env
# 三选一即可
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
QWEN_SECRET=your-qwen-key
GPT_SECRET=sk-xxxxxxxxxxxxxxxx
```

> 💡 **获取 API Key**：
> - DeepSeek：https://platform.deepseek.com
> - 通义千问（Qwen）：https://dashscope.aliyun.com
> - OpenAI（GPT）：https://platform.openai.com

> ⚠️ `.env` 已加入 `.gitignore`，不会被提交到 Git。请勿泄露密钥。

### 5. 构建前端

```bash
npm run build
```

---

## 二、启动游戏

```bash
python backend/web_server.py
```

浏览器打开：**http://localhost:8000**

### 指定端口

```bash
AGENT_PORT=8080 python backend/web_server.py
# 然后访问 http://localhost:8080
```

---

## 三、后续启动（已安装过）

无需重新安装依赖。直接启动：

```bash
cd BUMENGweb
python backend/web_server.py
```

---

## 四、更新代码后的启动

拉取最新代码后如有前端变更，需重新构建：

```bash
git pull
npm install          # 如有新依赖
npm run build        # 重新构建前端
python backend/web_server.py
```

---

## 五、多人联机

1. 启动服务器（只需一台电脑运行）
2. 确保其他玩家在**同一局域网**，或服务器有公网 IP
3. 其他玩家浏览器访问：`http://你的IP地址:8000`
4. 房主创建房间 → 分享6位房号 → 其他人加入

---

## 常见问题

### Q: 端口被占用？

```bash
AGENT_PORT=8080 python backend/web_server.py
```

### Q: `npm run build` 报错？

```bash
rm -rf node_modules
npm install
npm run build
```

### Q: AI 不回复？

1. 检查 `.env` 中 API Key 是否正确
2. 确认 API 账户有余额
3. 查看终端日志排查具体错误

### Q: 如何卸载？

```bash
# 删除项目目录即可，无其他残留
cd .. && rm -rf BUMENGweb
```
