# ChatTTS 集成指南

## 📦 安装 ChatTTS

### 1️⃣ 基础安装

```bash
pip install ChatTTS
```

### 2️⃣ 可选：安装音频处理库（用于更好的音频支持）

```bash
pip install numpy
pip install scipy
pip install pydub
```

### 3️⃣ 完整依赖清单

```bash
pip install ChatTTS numpy scipy pydub
```

## 🚀 使用说明

### 启用 ChatTTS

在 `server.py` 中的 `on_ready` 事件中初始化 ChatTTS：

```python
@bot.event
async def on_ready():
    print(f"✅ Discord Bot 已上线: {bot.user.name}")

    # 初始化 ChatTTS
    from chat_tts_handler import initialize_chattts
    initialize_chattts()

    await multi_room_engine.start_background_tasks()
```

### 现有代码中使用 ChatTTS

#### 在 game_flow.py 或其他地方发送语音消息：

```python
# 发送公屏消息（带 ChatTTS）
await engine.send_to_public(
    content="这是一条语音消息",
    tts=True,  # 启用 TTS
    use_ChatTTS=True,  # 使用 ChatTTS
    speaker="narrator"
)

# 发送私聊消息（带 ChatTTS）
await engine.send_to_person(
    player_name="玩家名称",
    content="私密信息",
    tts=True,  # 启用 TTS
    use_ChatTTS=True,  # 使用 ChatTTS
    speaker="DM-bot"
)

# 降级到 Discord 原生 TTS（如果 ChatTTS 失败）
await engine.send_to_public(
    content="消息内容",
    tts=True,
    use_ChatTTS=False  # 使用 Discord 原生 TTS
)
```

## 🎤 ChatTTS vs Discord TTS 对比

| 特性 | ChatTTS | Discord TTS |
|------|---------|------------|
| 费用 | 免费 | 免费 |
| 自托管 | ✅ 是 | ❌ 否 |
| 语音质量 | ⭐⭐⭐⭐ 高 | ⭐⭐⭐ 中等 |
| 中文支持 | ✅ 优秀 | ⭐ 一般 |
| 首次启动 | ⏱️ 需要加载模型 | ⚡ 即时 |
| 依赖 | Python/PyTorch | Discord API |

## ⚙️ 性能优化

### 首次运行
- ChatTTS 第一次运行时需要下载并加载模型（约 100-300MB）
- 初始化时间为 30-60 秒
- **建议在 Bot 启动时初始化，而不是在用户请求时**

### GPU 支持
如果你的系统有 NVIDIA GPU，可以启用 GPU 加速：

编辑 `chat_tts_handler.py`，在 `initialize()` 方法中：

```python
# 启用 GPU（如果可用）
self.chat_tts = ChatTTS.ChatTTS()
self.chat_tts.load_models(compile=False, device="cuda")  # 使用 GPU
```

### CPU 模式
默认使用 CPU，如果你的服务器只有 CPU 也没问题，只是会稍微慢一些。

## 🐛 故障排查

### 问题 1: "未安装 ChatTTS"
**解决方案**：
```bash
pip install ChatTTS --upgrade
```

### 问题 2: "初始化失败"
**解决方案**：
- 检查网络连接（需要下载模型）
- 检查磁盘空间（需要至少 500MB）
- 查看日志输出了什么错误

### 问题 3: "音频生成失败"
**解决方案**：
- 确保输入文本不为空
- 检查文本长度（不要超过 1000 个字符）
- 降级到 Discord TTS

### 问题 4: "Bot 响应变慢"
**解决方案**：
- 启用 GPU 加速
- 增加服务器资源
- 考虑使用线程池处理语音生成

## 📝 配置选项

### 在 engine.py 中全局启用 ChatTTS

修改所有 `send_to_public` 和 `send_to_person` 调用，设置 `use_ChatTTS=True`（默认值）。

### 根据场景选择 TTS

```python
# 重要场景使用 ChatTTS（质量更好）
if important:
    await engine.send_to_public(
        content=message,
        tts=True,
        use_ChatTTS=True  # 使用高质量 ChatTTS
    )
else:
    # 低优先级场景使用 Discord TTS（更快）
    await engine.send_to_public(
        content=message,
        tts=True,
        use_ChatTTS=False  # 使用快速 Discord TTS
    )
```

## 🎯 最佳实践

1. **在 Bot 启动时初始化 ChatTTS**
   - 这样用户首次请求时不会遇到延迟

2. **为私聊消息使用 ChatTTS**
   - 私密信息更重要，值得用更好的语音

3. **为公屏消息提供选择**
   - 可以根据情况选择快速 Discord TTS 或高质量 ChatTTS

4. **监控日志**
   - 启用详细日志（已在代码中实现）
   - 监视初始化和生成过程

## 📞 获取帮助

如果遇到问题：

1. 查看服务器日志中的 `[ChatTTS]` 标记
2. 检查 python 版本（建议 3.8+）
3. 使用 `pip list | grep ChatTTS` 验证安装
4. 尝试重新安装：`pip uninstall ChatTTS && pip install ChatTTS --upgrade`

---

**现在你的 TRPG 游戏拥有了高质量的中文 AI 语音！** 🎉
