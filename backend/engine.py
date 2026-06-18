import asyncio
import time
from contextlib import asynccontextmanager
from collections import Counter
try:
    import discord
    from discord.ui import View, Button
    DISCORD_AVAILABLE = True
except ImportError:
    discord = None
    View = None
    Button = None
    DISCORD_AVAILABLE = False
from manager import GameManager
import re

# ============================================================
# 统一 TTS 文本清洗函数（写死，确保只读可朗读的文字内容）
# 所有 TTS 播报都必须经过此函数清洗
# ============================================================
def clean_tts_text(text: str, max_length: int = 500) -> str:
    """
    统一清洗 TTS 文本，确保只朗读文字内容，去除所有格式标记和噪音。
    
    清洗策略（按顺序执行）：
    1. 删除 URL / 路径 / 代码块 / HTML标签 / Markdown链接
    2. 删除整行格式标记（分隔线、选项行、序号行）
    3. 清理行内格式标记（**粗体**、*斜体*、#标题、>引用、emoji短码）
    4. 暴力白名单兜底：只保留中文+英文+数字+常用标点+空格换行
    5. 删除括号内容
    6. 收尾：去空行、去引导前缀、截断过长文本
    """
    if not text or not isinstance(text, str):
        return ""
    
    clean = str(text)
    
    # ===== 第一步：暴力删除所有 URL、路径、代码块、HTML =====
    clean = re.sub(r'https?://\S+', '', clean)          # URL
    clean = re.sub(r'www\.\S+', '', clean)               # www链接
    clean = re.sub(r'[\w\-\.]+\.(com|cn|org|net|io|gg|dev|app|co|me|xyz|top|info|biz|tv|cc)/\S*', '', clean)  # 域名+路径
    clean = re.sub(r'/\S*/\S*', '', clean)                # 路径如 /xxx/yyy (至少两个斜杠)
    clean = clean.replace('\\', '')                        # 反斜杠
    clean = re.sub(r'```[\s\S]*?```', '', clean)           # 代码块
    clean = re.sub(r'`([^`]+)`', r'\1', clean)             # 行内代码（保留内容）
    clean = re.sub(r'<[^>]+>', '', clean)                  # HTML标签
    clean = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', clean) # Markdown链接 [text](url) → text
    clean = re.sub(r'\[[^\]]+\]', '', clean)               # 方括号内容（残留）
    
    # ===== 第二步：删除整行格式标记行 =====
    clean = re.sub(r'^[\-*_]{3,}\s*$', '', clean, flags=re.MULTILINE)    # 分隔线 --- *** ___
    clean = re.sub(r'^={3,}\s*$', '', clean, flags=re.MULTILINE)          # 等号分隔线
    clean = re.sub(r'^[→\-–—>]\s+.+$', '', clean, flags=re.MULTILINE)     # 选项行 → xxx
    clean = re.sub(r'^\d+[\.\)、．]\s*.+$', '', clean, flags=re.MULTILINE) # 序号行 1. xxx
    
    # ===== 第三步：行内格式标记清理 =====
    clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)                      # **粗体**
    clean = re.sub(r'__([^_]+)__', r'\1', clean)                          # __下划线__
    clean = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', clean)             # *斜体*
    clean = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'\1', clean)                 # _斜体_
    clean = re.sub(r'~~([^~]+)~~', r'\1', clean)                          # ~~删除线~~
    clean = re.sub(r'^#{1,6}\s+', '', clean, flags=re.MULTILINE)          # # ## ### 标题
    clean = re.sub(r'^>\s*', '', clean, flags=re.MULTILINE)               # > 引用
    clean = re.sub(r'(?<!\w):\w+:(?!\w)', '', clean)                      # :emoji: 短码
    
    # ===== 第四步：暴力白名单（最终兜底）=====
    # 只保留：中文、英文、数字、常用中文标点、英文标点、空格、换行
    allowed_pattern = re.compile(
        r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef'   # 中文+中文标点
        r'a-zA-Z0-9'                                      # 英文+数字
        r'。，！？；：""''【】《》（）—…·'                  # 中文标点
        r'.,!?;:\s\n\-'                                  # 英文标点+空格+换行+连字符
        r']'
    )
    clean = allowed_pattern.sub('', clean)
    
    # ===== 第五步：删除括号内容 =====
    clean = re.sub(r'（[^）]*）', '', clean)  # 全角括号
    clean = re.sub(r'\([^)]*\)', '', clean)   # 半角括号
    
    # ===== 第六步：收尾清理 =====
    # 删除"你们可以："之类的引导前缀行
    clean = re.sub(r'^[你您]们可以[：:]\s*$', '', clean, flags=re.MULTILINE)
    # 删除连续3个以上换行
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    # 逐行 strip
    clean = '\n'.join(line.strip() for line in clean.split('\n') if line.strip())
    # 合并多余空格（2个以上空格合并为1个）
    clean = re.sub(r'[ \t]{2,}', ' ', clean)
    clean = clean.strip()
    
    # 再次去空行
    clean = '\n'.join(line.strip() for line in clean.split('\n') if line.strip())
    clean = re.sub(r'[ \t]{2,}', ' ', clean)
    clean = clean.strip()
    
    # 如果清洗后内容太短，返回空（不播报）
    if not clean or len(clean) < 2:
        return ""
    
    # 限制文本长度
    if len(clean) > max_length:
        clean = clean[:max_length] + "..."
    
    return clean


# 导入 ChatTTS 模块
try:
    from chat_tts_handler import edge_tts_manager, EDGETTS_AVAILABLE, send_with_tts
except ImportError:
    edge_tts_manager = None
    EDGETTS_AVAILABLE = False
    send_with_tts = None

class GameEngine:
    def __init__(self, bot, sio):
        self.bot = bot
        self.sio = sio
        self.manager = GameManager(self) 
        self.room_state = {
            "status": "IDLE",
            "web_rooms": ["public"],  # 已创建的房间列表
            "active_users": {},       # 格式 {sid: nickname}
            "messages": {"public": []} # 消息历史：{room_id: [msg1, msg2]}
        }
        self.current_channel = None
        self.main_channel = None  # 【新增】专门记录公聊大厅频道
        self.room_thread = None   # 【新增】房间专属的 Discord Thread

        # 角色->TTS参数映射（可用于剧本角色音色/语气/语速）
        # 例如: {"侦探": {"voice": "zh-CN-YunxiNeural", "style": "calm", "rate": "-10%"}}
        self.character_tts_profiles = {}

        # 投票状态追踪
        self.active_vote_view = None  # 当前活跃的投票 View
        self.vote_lock = asyncio.Lock()  # 投票互斥锁
    
    # === 生命周期管理 ===
    async def start_background_tasks(self):
        """启动后台监控任务"""
        print("💓 后台监控已启动")
        await self.manager.start_background_tasks()
    
    async def on_bot_ready(self):
        """Bot准备就绪"""
        print("🎮 游戏引擎已就绪")
    
    # === 游戏流程控制 ===
    # async def start_lobby(self, channel):
    #     """开启征集阶段"""
    #     self.current_channel = channel
    #     self.room_state["status"] = "LOBBY"
    #     await self.manager.start_lobby()

    async def start_lobby(self, channel):
        """开启征集阶段（仅在公聊频道执行）"""
        # 检查是否为 DM 频道（私信）
        if isinstance(channel, discord.DMChannel):
            await channel.send("❌ 该指令只能在公聊频道使用！请到**综合**频道执行 `!准备`")
            return

        if self.main_channel is None:
            # 第一次运行时锁定主channel，即公聊频道
            self.main_channel = channel
            channel_name = getattr(channel, 'name', '未知频道')
            print(f"📍 [Engine] 已锁定主频道: {channel_name} (IDLE -> LOBBY)")
        elif channel.id != self.main_channel.id:
            # 如果在其他频道执行，提示用户
            await channel.send(f"⚠️ 游戏正在 **{self.main_channel.name}** 频道进行，请到该频道执行指令")
            return

        self.current_channel = channel
        self.room_state["status"] = "LOBBY"
        print("📡 [Engine] 收到指令，正在尝试获取名单...")

        members = getattr(channel, 'members', []) 
        active_members = [m for m in members if not getattr(m, 'bot', False)]
        
        player_names = [m.name for m in active_members]
        player_count = len(active_members)

        # 这里的打印非常重要，用来确认程序是否活着的
        print(f"✅ [Engine] 流程继续！当前检测到人数: {player_count}")


        # 触发 Manager 初始化
        await self.manager.start_lobby()

        # --- 优化后的公告 ---
        guide_msg = (
            "📢 **灵感与角色征集开启！**\n\n"
            f"📊 **当前识别到玩家 ({player_count}人)**：`{', '.join(player_names) if player_names else '无'}`\n\n"
            "1️⃣ **世界观建议**：输入 `!建议 [内容]`\n"
            "   *例子：!建议 废土朋克，克苏鲁元素*\n\n"
            "2️⃣ **个人要求**：输入 `!角色 [性别/性格]`\n"
            "   *例子：!角色 男，冷酷医生* 注意：在开始游戏前都可以修改，以最后一次为准\n\n"
            "💡 所有人准备好后，输入 `!开始游戏` 正式开局！"
        )
        await self.send_to_channel(guide_msg)

        # --- 发送静态图片（放在文字下方） ---
        import os
        img_path = os.path.join(os.path.dirname(__file__), "..", "img", "灵感收集大厅.png")
        if os.path.exists(img_path):
            target_channel = self.room_thread if self.room_thread else self.current_channel
            await target_channel.send(file=discord.File(img_path))
        else:
            print(f"⚠️ 图片不存在: {img_path}")
    
    async def send_to_public(self, content, tts=False, speaker=None, use_EdgeTTS=True):
        """向房间内发送消息到 Thread（房间隔离）

        Args:
            content: 要发送的消息内容
            tts: 是否启用文字转语音
            speaker: 说话人标识，如果提供则自动记录到 chat_history
                    None 表示不记录，其他值如 'DM-bot', 'roll-dice' 等会按指定名称记录
            use_EdgeTTS: 是否使用 EdgeTTS（True）还是 Discord 原生 TTS（False）
        """
        print(f"📡 [TTS] 准备向房间发送消息，TTS: {tts}，使用 EdgeTTS: {use_EdgeTTS and EDGETTS_AVAILABLE}")

        # 优先使用 room_thread（隔离消息），然后是 main_channel，最后才是 current_channel
        target = self.room_thread or self.main_channel or self.current_channel

        if target:
            try:
                if tts:
                    # 发送文字到Thread
                    await target.send(content)

                    # 如果是 DM 语音，根据剧情文本自动推断 TTS 参数，否则使用角色映射
                    if speaker == "DM-bot":
                        tts_profile = self.infer_dm_tts_profile(content)
                    else:
                        tts_profile = self.get_tts_profile_for_character(speaker) if speaker else {}

                    voice = tts_profile.get("voice")
                    style = tts_profile.get("style")
                    rate = tts_profile.get("rate")
                    pitch = tts_profile.get("pitch")

                    # 发送语音MP3到Thread
                    if use_EdgeTTS and EDGETTS_AVAILABLE and edge_tts_manager.initialized:
                        await send_with_tts(
                            target,
                            content,
                            use_EdgeTTS=True,
                            voice=voice or "zh-CN-XiaoxiaoNeural",
                            style=style,
                            rate=rate or "+0%",
                            pitch=pitch or "+0Hz",
                        )
                    print(f"🔊 [TTS] 已发送文字和语音到Thread")
                else:
                    await target.send(content)

                print(f"📢 [Public] 消息已同步至房间 | TTS: {tts}")

                # 如果提供了 speaker 参数，自动记录到 chat_history
                if speaker:
                    chat_entry = self.manager.build_chat_entry(content, speaker)
                    self.manager.game_state["chat_history"].append(chat_entry)
                    print(f"📝 [History] 已记录 {speaker} 的消息到聊天历史")

            except Exception as e:
                print(f"❌ [Public Error] 发送失败: {e}")
        else:
            print("⚠️ [Public] 未找到主频道记录")
    
    async def add_player_suggestion(self, player_name, keyword, channel):
        """添加玩家灵感建议"""
        self.current_channel = channel

        if self.room_state["status"] != "LOBBY":
            print("❌ 当前不在征集阶段")
            await self.send_to_channel("❌ 当前不在征集阶段")
            return

        suggestion = f"{player_name}: {keyword}"
        self.manager.game_state["suggestions"].append(suggestion)
        # 通知网页端更新
        await self.sio.emit('lobby_update', {
            "suggestions": self.manager.game_state["suggestions"]
        })

        count = len(self.manager.game_state["suggestions"])
        await self.send_to_channel(f"✅ {player_name} 提供了灵感：{keyword}\n当前灵感池：{count}")


    async def add_player_role_pref(self, player_name, pref, channel):
        """添加玩家角色偏好（随时可以调用）"""
        self.current_channel = channel
        
        # 1. 存入角色偏好
        self.manager.game_state["role_prefs"][player_name] = pref

        # 2. 【核心修改】：只要调用该指令，就将玩家存入 players 字典完成"报名"
        if player_name not in self.manager.game_state["players"]:
            self.manager.game_state["players"][player_name] = {"status": "joined"}
        
        # 3. 【同步修改】：从 players 字典获取已报名的成员名单
        submitted_players = list(self.manager.game_state["players"].keys())
        players_str = "，".join(submitted_players)
        
        # 4. 反馈内容保持原样
        feedback = (
            f"👤 **{player_name}** 已设定角色要求：{pref}\n"
            f"📌 当前提交角色池的用户有：{players_str}"
        )
        await self.send_to_channel(feedback)

    def get_all_members_mapping(self):
        """获取所有服务器成员的 {用户名/昵称: Member对象} 映射字典"""
        mapping = {}
        for guild in self.bot.guilds:
            for member in guild.members:
                # 使用用户名作为主键
                mapping[member.name] = member
                # 如果有昵称，也添加映射
                if member.nick:
                    mapping[member.nick] = member
        return mapping

    def print_member_info(self):
        """打印所有成员信息（调试用）"""
        print("\n=== 当前服务器成员列表 ===")
        for guild in self.bot.guilds:
            print(f"\n📌 服务器: {guild.name} (ID: {guild.id})")
            for member in guild.members:
                nick_info = f"昵称: {member.nick}" if member.nick else "无昵称"
                print(f"  - 用户名: {member.name} | {nick_info} | ID: {member.id}")

    async def send_to_person(self, player_name, content, tts=False, speaker=None, use_EdgeTTS=True):
        """
        主动给 Discord 玩家发送私聊消息

        Args:
            player_name: 玩家在 Discord 的用户名 (Username) 或 昵称 (Nickname)
            content: 消息内容
            tts: 是否启用文字转语音
            speaker: 说话人标识，如果提供则自动记录到 chat_history
                    None 表示不记录，其他值如 'DM-bot' 等会按指定名称记录
            use_EdgeTTS: 是否使用 EdgeTTS（True）还是 Discord 原生 TTS（False）
        Returns:
            bool 是否发送成功
        """

        import re
        import asyncio

        print(f"📡 [TTS] 准备向玩家 {player_name} 发送私聊，TTS: {tts}，使用 EdgeTTS: {use_EdgeTTS and EDGETTS_AVAILABLE}")
        target_member = None

        # 1. 遍历机器人所在的所有服务器，寻找匹配的成员
        for guild in self.bot.guilds:
            # 优先尝试匹配昵称，其次匹配全球用户名
            target_member = discord.utils.get(guild.members, nick=player_name)
            if not target_member:
                target_member = discord.utils.get(guild.members, name=player_name)

            if target_member:
                break

        if not target_member:
            print(f"❌ 找不到玩家: {player_name}")
            # 调试：打印所有成员信息
            self.print_member_info()
            return False

        try:
            formatted_msg = f"🔍 **【私密情报】**\n{content}"

            # 2. 如果开启了 TTS，使用新的 send_with_tts 函数
            if tts:
                await send_with_tts(target_member, formatted_msg, use_EdgeTTS=use_EdgeTTS)
                print(f"✅ 已使用 TTS 向 {player_name} 发送消息")
            else:
                # 如果不开启 TTS，直接发送完整格式
                await target_member.send(formatted_msg, tts=False)
                print(f"✅ 已向 {player_name} 发送纯文本消息")

            # 如果提供了 speaker 参数，自动记录到 chat_history
            if speaker:
                chat_entry = self.manager.build_chat_entry(content, speaker, channel=player_name)
                self.manager.game_state["chat_history"].append(chat_entry)
                print(f"📝 [History] 已记录 {speaker} 的私信到聊天历史")

            # 同时发送到网页端
            await self.sio.emit('private_message', {
                "player_name": player_name,
                "content": content,
                "timestamp": time.strftime("%H:%M:%S")
            })

            return True

        except discord.Forbidden:
            print(f"❌ 发送失败：玩家 {player_name} 可能关闭了'允许来自服务器成员的私聊，或 Bot 的 TTS 被该用户端屏蔽")
        except Exception as e:
            print(f"❌ 私聊发送时发生未知错误: {e}")

        return False

    async def send_avatar_to_person(self, player_name, image_path):
        """向 Discord 玩家发送头像图片"""
        import os

        target_member = None

        # 1. 遍历机器人所在的所有服务器，寻找匹配的成员
        for guild in self.bot.guilds:
            target_member = discord.utils.get(guild.members, nick=player_name)
            if not target_member:
                target_member = discord.utils.get(guild.members, name=player_name)

            if target_member:
                break

        if not target_member:
            print(f"❌ 找不到玩家: {player_name}")
            return False

        try:
            if os.path.exists(image_path):
                await target_member.send(file=discord.File(image_path))
                print(f"✅ 已成功向 {player_name} 发送头像")
                return True
            else:
                print(f"❌ 图片文件不存在: {image_path}")
                return False
        except Exception as e:
            print(f"❌ 发送头像失败: {e}")
            return False

    async def send_avatar_to_public(self, role_name, image_path):
        """向公共聊天框发送带角色名字水印的头像图片"""
        import os

        target_channel = self.room_thread if self.room_thread else self.main_channel if self.main_channel else self.current_channel

        if not target_channel:
            print("❌ 未找到公共频道")
            return False

        try:
            if os.path.exists(image_path):
                # 在图片左上角添加角色名字水印
                from PIL import Image, ImageDraw, ImageFont

                # 打开图片
                img = Image.open(image_path)

                # 创建绘图对象
                draw = ImageDraw.Draw(img)

                # 设置字体大小（根据图片大小调整）
                img_size = max(img.size)
                font_size = int(img_size * 0.05)  # 字体大小为图片尺寸的5%

                # 尝试加载中文字体
                try:
                    font = ImageFont.truetype("msyh.ttc", font_size)  # 微软雅黑
                except:
                    try:
                        font = ImageFont.truetype("simhei.ttf", font_size)  # 黑体
                    except:
                        font = ImageFont.load_default()

                # 获取文字大小
                bbox = draw.textbbox((0, 0), role_name, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                # 添加阴影效果（黑色）
                padding = font_size // 2
                shadow_offset = 3
                draw.text(
                    (padding + shadow_offset, padding + shadow_offset),
                    role_name,
                    font=font,
                    fill=(0, 0, 0, 255)  # 黑色阴影
                )

                # 添加文字（白色）
                draw.text(
                    (padding, padding),
                    role_name,
                    font=font,
                    fill=(255, 255, 255, 255)  # 白色文字
                )

                # 保存到临时文件
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                    img.save(tmp_file, 'PNG')
                    tmp_path = tmp_file.name

                # 发送到公共频道
                await target_channel.send(file=discord.File(tmp_path))

                # 删除临时文件
                os.unlink(tmp_path)

                print(f"✅ 已向公共频道发送 {role_name} 的头像")
                return True
            else:
                print(f"❌ 图片文件不存在: {image_path}")
                return False
        except Exception as e:
            print(f"❌ 发送头像到公共频道失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def start_game(self, channel):
        """汇总并开始"""
        self.current_channel = channel

        # === 【核心修改：从 players 字典获取已报名的真实玩家】 ===
        # 不再使用 active_members = [m for m in channel.members if not m.bot]
        player_names = list(self.manager.game_state["players"].keys())
        player_count = len(player_names)
        # =====================================================
        
        print(f"\n--- [🚀 游戏正式启动] ---")
        channel_name = getattr(channel, 'name', f'DM频道({channel.recipient})') if hasattr(channel, 'recipient') else getattr(channel, 'name', '未知频道')
        print(f"📍 频道: {channel_name}")
        print(f"👥 最终锁定名单: {player_names}")
        print(f"🔢 最终人数: {player_count}")

        # 检查：必须有玩家报名才能开始
        if player_count == 0:
            await self.send_to_channel("❌ **无法开始游戏**：当前还没有玩家报名！请参赛者先使用 `!角色` 提交偏好。")
            return
        
        # 检查：如果有自定义剧本或建议，才能开始游戏
        custom_script = self.manager.game_state.get("custom_script")
        if not self.manager.game_state["suggestions"] and not custom_script:
            await self.send_to_channel("⚠️ 灵感池为空且无自定义剧本，请先使用 !建议 提供关键词，或使用 !提交剧本 提交自定义剧本")
            return

        await self.send_to_channel(f"检测到共有 {player_count} 位已报名玩家，正在构建专属剧本...")

        # 汇总灵感 (suggestions)
        prefs_str = " | ".join(self.manager.game_state["suggestions"])
        print(f"💡 汇总灵感池: {prefs_str}")

        # 3. 【核心修改】精准对齐玩家与角色偏好
        # 我们以频道里的 player_names 为准，去查 role_prefs 字典
        role_parts = []
        role_dict = self.manager.game_state.get('role_prefs', {})
        
        for name in player_names:
            # 如果字典里有该玩家的要求就用，没有就给个"随机背景"
            pref = role_dict.get(name, "未设定具体要求（请 DM 根据世界观分配身份）")
            role_parts.append(f"玩家 [{name}]: {pref}")
        
        role_summary = "\n".join(role_parts) # 用换行符 AI 看得更清楚
        print(f"👤 最终汇总角色表:\n{role_summary}")

        # 4. 进入调用阶段
        print(f"🚀 正在将数据发送至 Manager... (player_count={player_count})")
        print(f"---------------------------------\n")

        # 呼叫 Manager (确保 manager.py 的 start_game 接收这三个参数)
        print(f"📤 [Engine] 正在调用 manager.start_game...")
        await self.manager.start_game(prefs_str, role_summary, player_count)
        print(f"✅ [Engine] manager.start_game 调用完成，当前状态: {self.room_state['status']}")
        
    async def handle_player_input(self, content, player_name, channel=None, no_action=False):
        """处理玩家输入"""
        if channel:
            self.current_channel = channel
        print(f"从{self.current_channel}收到玩家{player_name}信息：{content}")
        await self.manager.handle_player_input(content, player_name, channel, no_action)
    
    async def reset_game(self, channel):
        """重置游戏"""
        self.current_channel = channel
        await self.manager.reset_game()
    
    # === 状态同步方法 ===
    def set_character_tts_profile(self, character_name: str, voice: str = None, style: str = None, rate: str = None, pitch: str = None):
        """设置角色的 TTS 参数。

        这可以让不同角色使用不同的音色/情绪/语速。
        """
        self.character_tts_profiles[character_name] = {
            "voice": voice,
            "style": style,
            "rate": rate,
            "pitch": pitch,
        }

    def get_tts_profile_for_character(self, character_name: str):
        """获取指定角色的 TTS 参数（如果有的话）。"""
        return self.character_tts_profiles.get(character_name, {})

    def infer_dm_tts_profile(self, message: str) -> dict:
        """根据 DM 的文本内容自动推断 DM 语音参数（情绪/语速/音色）。"""
        t = message.lower()

        # 默认作为男性叙述声音
        profile = {
            "voice": "zh-CN-YunxiNeural",
            "style": None,
            "rate": "+0%",
            "pitch": "-2Hz",
        }

        # 关键词触发情绪和语速
        if any(k in t for k in ["废土", "荒芜", "残破", "危险", "黑暗", "恐惧", "末日", "绝望"]):
            profile["style"] = "sad"
            profile["rate"] = "-10%"

        if any(k in t for k in ["爆发", "激烈", "冲突", "怒火", "枪战", "愤怒", "崩溃"]):
            profile["style"] = "angry"
            profile["rate"] = "+10%"

        if any(k in t for k in ["希望", "光明", "奇迹", "胜利", "荣耀", "庆祝"]):
            profile["style"] = "cheerful"
            profile["rate"] = "+5%"

        if any(k in t for k in ["冷静", "沉稳", "理智", "平静", "分析"]):
            profile["style"] = "calm"
            profile["rate"] = "-5%"

        return {k: v for k, v in profile.items() if v is not None}

    async def send_to_channel(self, message, speaker=None):
        """发送消息到 Discord Thread（房间隔离）

        Args:
            message: 要发送的消息内容
            speaker: 说话人标识，如果提供则自动记录到 chat_history
                    None 表示不记录，其他值如 'DM-bot', 'roll-dice' 等会按指定名称记录
        """
        # 优先使用 room_thread（隔离消息），如果没有则使用 current_channel（后向兼容）
        target = self.room_thread or self.current_channel

        if not target:
            print("⚠️ [Engine] 未设置频道或 Thread，无法发送消息")
            return
        try:
            await target.send(message)

            # 如果提供了 speaker 参数，自动记录到 chat_history
            if speaker:
                chat_entry = self.manager.build_chat_entry(message, speaker)
                self.manager.game_state["chat_history"].append(chat_entry)
                print(f"📝 [History] 已记录 {speaker} 的消息到聊天历史")
        except Exception as e:
            print(f"❌ [Engine] 发送消息失败: {e}")
    
    async def typing(self):
        """显示正在输入提示"""
        if self.current_channel:
            async with self.current_channel.typing():
                yield
    
    async def update_scene(self, scene_name, description):
        """更新场景（同步到网页并发送场景图）"""
        # 同步到网页
        await self.sio.emit('scene_update', {
            "name": scene_name,
            "description": description
        })
        # 异步生成并发送场景图片
        asyncio.create_task(self._generate_and_send_scene_image(scene_name, description))
    
    async def add_inventory_item(self, item_name, detail):
        """添加道具（同步到网页并发送道具图）"""
        self.manager.game_state["inventory"].append(item_name)
        await self.sio.emit('item_update', {
            "name": item_name,
            "detail": detail
        })
        # 异步生成并发送道具图片
        asyncio.create_task(self._generate_and_send_item_image(item_name, detail))
    
    async def trigger_dice_roll(self, result, success, reason):
        """触发骰子事件（同步到网页）"""
        await self.sio.emit('dice_event', {
            "result": result, 
            "success": success,
            "reason": reason
        })

    # === 用户与房间管理 ===
    async def on_web_client_connect(self, sid):
        """当网页用户连接时，默认加入 public 房间"""
        await self.sio.enter_room(sid, 'public')
        # 同步当前状态给新连接的用户
        await self.sio.emit('init_sync', {
            "scene": self.manager.game_state.get("scene", "等待中"),
            "rooms": self.room_state["web_rooms"],
            "current_room": "public",
            "online_users": [{"sid": s, "nickname": n} for s, n in self.room_state["active_users"].items()]
        }, room=sid)

    async def handle_set_nickname(self, sid, nickname):
        """设置用户昵称并通知全场"""
        # 检查游戏状态中是否有匹配的角色名
        player_characters = self.manager.game_state.get("long_term_memory", {}).get("player_characters", {})
        player_mapping = self.manager.game_state.get("player_mapping", {})

        # 如果输入的昵称匹配到游戏中的角色名，使用角色名作为昵称
        final_nickname = nickname
        for discord_name, char_name in player_mapping.items():
            if discord_name == nickname:
                final_nickname = char_name
                break

        # 同时检查角色卡中的角色名
        for player_id, char_data in player_characters.items():
            if player_id == nickname or char_data.get('role_name') == nickname:
                final_nickname = char_data.get('role_name', nickname)
                break

        self.room_state["active_users"][sid] = final_nickname
        print(f"👤 用户上线: {final_nickname} (输入: {nickname}, sid: {sid})")
        await self.sync_initial_state(sid)
        await self.broadcast_chat("系统", f"欢迎 {final_nickname} 加入游戏", room_id="public")

    async def handle_join_web_room(self, sid, room_id):
        """处理加入/创建房间"""
        if not room_id: return
        
        if room_id not in self.room_state["web_rooms"]:
            self.room_state["web_rooms"].append(room_id)
            self.room_state["messages"][room_id] = []
            await self.sio.emit('room_list_update', self.room_state["web_rooms"])

        rooms = self.sio.rooms(sid)
        for r in rooms:
            if r != sid: await self.sio.leave_room(sid, r)
            
        await self.sio.enter_room(sid, room_id)
        history = self.room_state["messages"].get(room_id, [])
        await self.sio.emit('history_sync', {"room": room_id, "msgs": history}, room=sid)
        print(f"👤 用户 {sid} 加入了网页房间: {room_id}")

    # === 统一消息分发系统 ===
    async def broadcast_chat(self, user, content, room_id="public"):
        """统一的消息发送出口"""
        payload = {
            "user": user,
            "content": content,
            "room": room_id,
            "time": time.strftime("%H:%M:%S")
        }
        if room_id not in self.room_state["messages"]:
            self.room_state["messages"][room_id] = []
        self.room_state["messages"][room_id].append(payload)
        self.room_state["messages"][room_id] = self.room_state["messages"][room_id][-50:]
        await self.sio.emit('chat_message', payload, room=room_id)
        
    async def send_image(self, image_url: str, room_id="public"):
        """将一个图片发送到指定房间或者展示在前端"""
        try:
            # 发送到前端
            await self.sio.emit('image_message', {"url": image_url}, room=room_id)

            # 发送到 Discord（优先房间Thread，其次公聊频道）
            target_channel = self.room_thread if self.room_thread else self.main_channel if self.main_channel else self.current_channel
            if target_channel:
                await target_channel.send(image_url)
                print(f"📷 图片已发送到频道: {image_url[:100]}...")
        except Exception as e:
            print(f"❌ 发送图片失败: {e}")

    async def send_player_card(self, card_data: dict):
        """发送角色卡到网页端（Discord模式广播给所有玩家）"""
        await self.sio.emit('player_card', card_data)

    async def send_round_change(self, current_round, total_rounds, scene_name, scene_description):
        """发送回合变更事件给前端（含场景信息，前端据此切换BGM和背景）"""
        await self.sio.emit('round_change', {
            "current_round": current_round,
            "total_rounds": total_rounds,
            "scene_name": scene_name,
            "scene_description": scene_description,
            "is_final_round": current_round >= total_rounds,
        })

    async def _generate_and_send_scene_image(self, scene_name, description):
        """生成场景图片并发送（异步任务），每次对话生成全新背景，仅头像缓存"""
        if scene_name == "灵感征集大厅":
            print(f"🎨 [Scene] 跳过灵感征集大厅的场景图生成")
            return
        # 场景切换后停留 2s，让玩家先阅读文本再出背景图
        await asyncio.sleep(2)
        try:
            from ai_handler import generate_image_url_async
            from image_cache import (
                get_character_visual, url_to_base64, _url_to_base64_sync,
            )

            # 1. 构建提示词（强制图文对应：描述词必须来自当前回合DM响应）
            desc_text = description[:300] if description else ""
            prompt = f"请严格按照以下描述生成场景画面，必须与描述内容完全一致：地点「{scene_name}」。画面内容：{desc_text}。"
            
            # 加入主角形象描述（保持同一人物外观）
            scenario = self.manager.game_state.get("long_term_memory", {}).get("world_summary", "")[:50] or "default"
            for prefix in ["【", "《"]:
                end = scenario.find("】" if prefix == "【" else "》")
                if end > 0:
                    scenario = scenario[len(prefix):end]
                    break
            
            char_visual = get_character_visual("林墨", scenario) or get_character_visual("林墨", "default")
            if char_visual:
                prompt += f" 场景中出现主角：{char_visual}。"
                print(f"👤 [Scene] 已加入角色形象描述以保持一致性")
            
            prompt += " 风格为角色扮演游戏，写实风格，电影感，细节丰富，4K画质。"
            
            print(f"🎨 [Scene] 开始生成场景图片: scene={scene_name}, desc={desc_text[:80]}...")
            
            # 2. 异步生成图片URL
            image_url = await generate_image_url_async(prompt)
            
            if image_url:
                print(f"✅ [Scene] 场景图片URL生成成功: {image_url[:100]}...")
                # 下载并转为 base64 直接发送（不缓存，每次对话全新背景）
                # 强制 base64：先用异步 aiohttp，失败则用同步 requests 重试，绝不发送原始 URL
                result_b64 = await url_to_base64(image_url)
                if not result_b64:
                    result_b64 = await asyncio.to_thread(_url_to_base64_sync, image_url)
                if result_b64:
                    await self.sio.emit("image_message", {
                        "url": result_b64,
                        "label": f"场景图: {scene_name}",
                    })
                    print(f"📤 [Scene] 场景图片已发送: {scene_name}")
                else:
                    print(f"⚠️ [Scene] base64 转换失败，跳过场景图: {scene_name}")
            else:
                print(f"⚠️ [Scene] 场景图片生成返回空URL: {scene_name}")

        except Exception as e:
            print(f"❌ [Scene] 场景图片生成异常: {e}")
            import traceback
            traceback.print_exc()

    async def _generate_and_send_item_image(self, item_name, detail):
        """生成物品图片并发送（异步任务）"""
        try:
            from ai_handler import generate_image_url_async

            print(f"🎨 开始生成物品图片: {item_name}")

            # 构建图片生成提示词
            prompt = f"物品道具图：{item_name}。所处的时代：{self.manager.game_state.get('long_term_memory', {}).get('time_space', '未知')}。{detail}。写实风格，4K画质。"

            # 异步生成图片URL
            image_url = await generate_image_url_async(prompt)

            if image_url:
                print(f"✅ 物品图片生成成功: {image_url[:80]}...")
                # 发送图片
                await self.send_image(image_url, "public")
            else:
                print(f"⚠️ 物品图片生成失败: {item_name}")

        except Exception as e:
            print(f"❌ 物品图片生成异常: {e}")

    # --- 辅助方法 ---
    async def sync_initial_state(self, sid):
        """给新登录的用户发送当前全局状态"""
        users = [{"sid": s, "nickname": n} for s, n in self.room_state["active_users"].items()]
        await self.sio.emit('init_sync', {
            "rooms": self.room_state["web_rooms"],
            "online_users": users
        }, room=sid)

    def get_game_state(self):
        """获取当前游戏内容状态"""
        return self.manager.game_state.copy()

    def get_game_status(self):
        """获取当前游戏流程状态"""
        return self.room_state["status"]
    
    # === Token 监控 ===
    async def show_token_stats(self, channel=None):
        """
            显示 Token 使用统计信息并输出到指定频道或控制台
            
            Args:
                channel (Optional[discord.Channel]): 要发送统计信息的 Discord 频道对象，如果为 None 则打印到控制台
            
            Returns:
                None: 无返回值
            
            Note:
                统计信息包括:
                - 总调用次数
                - 总 Token 消耗
                - 按模型分类的调用次数和 Token 消耗
        """
        from token_monitor import get_monitor
        
        monitor = get_monitor()
        stats = monitor.get_daily_stats()
        
        stats_msg = (
            f"📊 **Token 使用统计** ({stats['date']})\n\n"
            f"🔢 总调用次数: {stats['total_calls']}\n"
            f"💰 总 Token 消耗: {stats['total_tokens']:,}\n\n"
            f"**按模型统计:**\n"
        )
        
        for model, data in stats['model_stats'].items():
            stats_msg += f"- {model}: {data['calls']} 次调用, {data['tokens']:,} tokens\n"
        
        if channel:
            await channel.send(stats_msg)
        else:
            print(stats_msg)
    
    async def show_session_summary(self, channel=None):
        """显示当前会话的 Token 汇总"""
        from token_monitor import get_monitor
        
        monitor = get_monitor()
        records = monitor.get_session_records()
        
        if not records:
            summary_msg = "📊 当前会话无 AI 调用记录"
        else:
            total_tokens = sum(r['total_tokens'] for r in records)
            summary_msg = (
                f"📊 **当前会话 Token 汇总**\n\n"
                f"🔢 总调用次数: {len(records)}\n"
                f"💰 总 Token 消耗: {total_tokens:,}\n\n"
                f"**详细记录:**\n"
            )
            
            for i, record in enumerate(records[-10:], 1):  # 只显示最近 10 条
                summary_msg += (
                    f"{i}. {record['timestamp']} | {record['operation']}\n"
                    f"   {record['model']}: {record['prompt_tokens']}↓ / {record['completion_tokens']}↑ = {record['total_tokens']}\n"
                )
            
            if len(records) > 10:
                summary_msg += f"\n... 还有 {len(records) - 10} 条记录\n"
        
        if channel:
            await channel.send(summary_msg)
        else:
            print(summary_msg)
    
    # async def reset_token_session(self, channel=None):
    #     """重置当前会话的 Token 记录"""
    #     from token_monitor import get_monitor
        
    #     monitor = get_monitor()
    #     monitor.reset_session()
        
    #     reset_msg = "📊 当前会话的 Token 记录已重置"
        
    #     if channel:
    #         await channel.send(reset_msg)
    #     else:
    #         print(reset_msg)

    # === 投票功能 ===
    async def send_ai_vote(self, channel, title, options):
        """
        供 AI 调用：发送一个带有选项按钮的投票界面

        参数:
            channel: Discord 频道对象
            title: 投票标题 (str)
            options: 选项列表 (list[str])

        功能:
            1. 在频道发送带有按钮的投票界面
            2. 记录玩家的投票选择（仅限已报名玩家）
            3. 30秒后统计并公布结果
            4. 将投票结果反馈给 AI 继续推进剧情
        """
        # 使用互斥锁防止并发投票
        async with self.vote_lock:
            # 检查是否已有活跃投票
            if self.active_vote_view is not None:
                print(f"⚠️ [Vote] 已有活跃投票，拒绝新投票请求：{title}")
                await channel.send("⚠️ 当前有正在进行的投票，请等待当前投票结束后再发起新投票。")
                return

            # 获取已报名的玩家列表
            registered_players = list(self.manager.game_state["players"].keys())

            async def process_results(votes):
                """处理投票结果"""
                # 清除活跃投票引用
                self.active_vote_view = None

                if not votes:
                    await channel.send(f"⏲️ 投票【{title}】已结束，无人参与。")
                    return

                # 统计票数
                counts = Counter(votes.values())
                winner = counts.most_common(1)[0][0]
                vote_details = "\n".join([f"- {opt}: {counts.get(opt, 0)} 票" for opt in options])

                # 发送投票结果
                result_msg = (
                    f"📊 **投票结果：{title}**\n"
                    f"{vote_details}\n\n"
                    f"🏆 最终决定：**{winner}**"
                )
                await channel.send(result_msg)

                # 将结果反馈给 AI（绕过批量处理，立即处理）
                feedback = f"【系统消息】关于\"{title}\"的投票已结束。玩家集体决定：{winner}。请根据此结果继续推进剧情。"
                await self.manager.handle_player_input(feedback, "SYSTEM", channel=None, no_action=False, bypass_batch=True)

            # 创建投票视图
            view = AI_VoteView(options, process_results, registered_players)
            self.active_vote_view = view  # 记录活跃投票
            await channel.send(f"🗳️ **请已报名玩家投票决定：{title}**", view=view)
            print(f"🗳️ [Vote] 新投票已发起：{title}，选项：{options}")


if DISCORD_AVAILABLE:
    class AI_VoteView(View):
        """AI 投票界面视图（仅限已报名玩家参与）"""

        def __init__(self, options: list, callback_coro, allowed_players: list, timeout=30):
            super().__init__(timeout=timeout)
            self.callback_coro = callback_coro
            self.results = {}  # {user_name: choice}
            self.message = None
            self.allowed_players = set(allowed_players)  # 已报名玩家列表（转为集合提高查找效率）

            for option in options:
                # 为每个选项创建一个按钮
                button = Button(label=option, style=discord.ButtonStyle.primary, custom_id=option)
                button.callback = self.create_button_callback(option)
                self.add_item(button)

        def create_button_callback(self, option):
            """创建按钮回调函数"""
            async def callback(interaction: discord.Interaction):
                user_name = interaction.user.name

                # 检查用户是否为已报名玩家
                if user_name not in self.allowed_players:
                    await interaction.response.send_message(
                        f"❌ 只有已报名的玩家才能参与投票！请先使用 `!角色` 指令报名。",
                        ephemeral=True
                    )
                    return

                # 检查用户是否已经投过票（防止重复投票）
                if user_name in self.results:
                    await interaction.response.send_message(
                        f"⚠️ 你已经投过票了！当前选择：{self.results[user_name]}",
                        ephemeral=True
                    )
                    return

                # 记录该用户的选择 (使用用户名，方便 AI 识别)
                self.results[user_name] = option
                
                # 检查是否所有玩家都已投票，如果是则提前结束投票
                if len(self.results) == len(self.allowed_players):
                    # 禁用所有按钮
                    for item in self.children:
                        item.disabled = True
                    if self.message:
                        await self.message.edit(view=self)
                    
                    # 调用回调处理结果
                    await self.callback_coro(self.results)
                    
                    # 停止 View 监听
                    self.stop()
                    
                    # 发送确认消息
                    await interaction.response.send_message(
                        f"✅ 所有玩家已完成投票，投票提前结束！你投给：{option}",
                        ephemeral=True
                    )
                    return

                # 告知用户投票成功 (ephemeral=True 只有本人可见)
                await interaction.response.send_message(
                    f"✅ 你已投给：{option}（{len(self.results)}/{len(self.allowed_players)} 玩家已投票）",
                    ephemeral=True
                )
            return callback

        async def on_timeout(self):
            """超时处理：统计投票并调用回调"""
            # 禁用所有按钮
            for item in self.children:
                item.disabled = True
            if self.message:
                await self.message.edit(view=self)

            # 调用回调处理结果
            await self.callback_coro(self.results)
else:
    class AI_VoteView:
        """Web 模式下的空投票视图（投票功能不可用）"""
        pass