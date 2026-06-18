import asyncio
import os
import random
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

import socketio
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# 必须在导入 engine 之前加载 .env，因为 engine 链式导入 ai_handler，后者在模块级别初始化 AI 客户端
load_dotenv(os.path.join(BACKEND_DIR, "..", ".env"))

from engine import GameEngine
import base64 as _base64

# 尝试导入 EdgeTTS
try:
    from chat_tts_handler import EdgeTTSManager, EDGETTS_AVAILABLE
    _web_tts_manager = EdgeTTSManager()
except ImportError:
    EDGETTS_AVAILABLE = False
    _web_tts_manager = None
    print("⚠️ [Web TTS] edge-tts 未安装，语音功能不可用")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app = FastAPI(title="Web TRPG Server")
socket_app = socketio.ASGIApp(sio, app)

rooms: dict[str, dict[str, Any]] = {}
sid_to_room: dict[str, str] = {}
sid_to_name: dict[str, str] = {}


def now_label() -> str:
    return time.strftime("%H:%M:%S")


_DM_STATUS_PHRASES = [
    "主持人正在清嗓...",
    "主持人翻开剧本中...",
    "主持人抿了一口茶...",
    "主持人正在掷骰子...",
    "主持人推了推眼镜...",
    "主持人在翻找线索卡...",
    "主持人正在酝酿台词...",
    "主持人轻敲桌面思考中...",
    "主持人正在描绘场景...",
    "主持人翻阅规则书...",
    "主持人调试氛围灯光...",
    "主持人正在整理笔记...",
    "主持人轻咳一声准备发言...",
    "主持人召唤灵感中...",
    "主持人摩挲着水晶球...",
]


def random_dm_status() -> str:
    return random.choice(_DM_STATUS_PHRASES)


def make_room_number() -> str:
    while True:
        room_number = str(random.randint(100000, 999999))
        if room_number not in rooms:
            return room_number


def chat_payload(user: str, content: str) -> dict[str, str]:
    return {"user": user, "content": content, "time": now_label()}


class WebMember:
    def __init__(self, name: str, sid: str):
        self.name = name
        self.nick = None
        self.id = sid
        self.sid = sid
        self.bot = False

    async def send(self, content=None, **kwargs):
        room_number = sid_to_room.get(self.sid)
        if room_number:
            await sio.emit(
                "private_message",
                {"player_name": self.name, "content": str(content or ""), "timestamp": now_label()},
                room=self.sid,
            )


class WebChannel:
    def __init__(self, room_number: str, name: str):
        self.id = room_number
        self.name = name
        self.recipient = None
        self.members: list[WebMember] = []

    @asynccontextmanager
    async def typing(self):
        await sio.emit("dm_status", {"message": random_dm_status()}, room=self.id)
        try:
            yield
        finally:
            await sio.emit("dm_status", {"message": ""}, room=self.id)

    async def send(self, content=None, file=None, **kwargs):
        if file is not None:
            file_ref = getattr(file, "fp", None)
            filename = getattr(file_ref, "name", None) or getattr(file, "filename", "") or ""
            filename = os.path.basename(filename)
            if filename:
                await sio.emit("image_message", {"url": f"/{filename}"}, room=self.id)
            return

        payload = chat_payload("DM", str(content or ""))
        await sio.emit("chat_message", payload, room=self.id)


class FakeBot:
    guilds: list[Any] = []

    def get_channel(self, channel_id):
        room = rooms.get(str(channel_id))
        return room.get("channel") if room else None

    def is_closed(self):
        return False


class ScopedSio:
    def __init__(self, base_sio, room_number: str):
        self.base_sio = base_sio
        self.room_number = room_number

    async def emit(self, event, data=None, room=None, **kwargs):
        target_room = room or self.room_number
        await self.base_sio.emit(event, data, room=target_room, **kwargs)

    async def enter_room(self, sid, room):
        await self.base_sio.enter_room(sid, room)

    async def leave_room(self, sid, room):
        await self.base_sio.leave_room(sid, room)

    def rooms(self, sid):
        return self.base_sio.rooms(sid)


async def web_send_to_person(engine: GameEngine, room_number: str, player_name: str, content: str, speaker=None):
    room = rooms[room_number]
    target_sid = None
    for sid, nickname in room["players"].items():
        if nickname == player_name:
            target_sid = sid
            break

    if not target_sid:
        mapping = engine.manager.game_state.get("player_mapping", {})
        for discord_name, character_name in mapping.items():
            if discord_name == player_name or character_name == player_name:
                for sid, nickname in room["players"].items():
                    if nickname == discord_name:
                        target_sid = sid
                        break
            if target_sid:
                break

    # 第三层：通过 player_characters 角色名反查
    if not target_sid:
        chars = engine.manager.game_state.get("long_term_memory", {}).get("player_characters", {})
        for p_name, char_data in chars.items():
            if char_data.get("role_name") == player_name:
                for sid, nickname in room["players"].items():
                    if nickname == p_name:
                        target_sid = sid
                        break
            if target_sid:
                break

    if not target_sid:
        print(f"❌ [Web] 找不到网页玩家: {player_name}")
        return False

    await sio.emit(
        "private_message",
        {"player_name": player_name, "content": content, "timestamp": now_label()},
        room=target_sid,
    )

    if speaker:
        chat_entry = engine.manager.build_chat_entry(content, speaker, channel=player_name)
        engine.manager.game_state["chat_history"].append(chat_entry)

    return True


def patch_engine_for_web(engine: GameEngine, room_number: str) -> None:
    async def send_to_person(player_name, content, tts=False, speaker=None, use_EdgeTTS=True):
        return await web_send_to_person(engine, room_number, player_name, content, speaker=speaker)

    async def send_image(image_url: str, room_id="public"):
        """发送图片：强制转 base64，绝不发送原始 HTTPS URL"""
        from image_cache import url_to_base64, _url_to_base64_sync

        if not image_url:
            print("⚠️ [Web-send_image] image_url 为空，跳过")
            return

        print(f"📷 [Web-send_image] 收到场景图: url={image_url[:80] if image_url else 'None'}...")

        # 强制转换为 base64
        result_b64 = await url_to_base64(image_url)
        if not result_b64:
            result_b64 = await asyncio.to_thread(_url_to_base64_sync, image_url)

        if result_b64:
            await sio.emit("image_message", {"url": result_b64, "label": "场景图"}, room=room_number)
            print(f"📤 [Web-send_image] base64 场景图已发送")
        else:
            print(f"⚠️ [Web-send_image] base64 转换失败，不发送原始 URL（已拦截）")

    # 覆盖 send_to_channel：发送到 Web 公屏
    async def send_to_channel_web(message, speaker=None):
        payload = chat_payload("DM", str(message))
        await sio.emit("chat_message", payload, room=room_number)
        if speaker:
            chat_entry = engine.manager.build_chat_entry(message, speaker)
            engine.manager.game_state["chat_history"].append(chat_entry)

    # 覆盖 send_to_public：发送到 Web 公屏（带 TTS 语音输出）
    async def send_to_public_web(content, tts=False, speaker=None, use_EdgeTTS=True, tts_override_text=None):
        payload = chat_payload("DM", str(content))
        await sio.emit("chat_message", payload, room=room_number)
        if speaker:
            chat_entry = engine.manager.build_chat_entry(content, speaker)
            engine.manager.game_state["chat_history"].append(chat_entry)

        # TTS 语音：异步生成并发送音频给前端
        # 如果有 tts_override_text，则用它替代 content 做 TTS
        tts_content = tts_override_text if tts_override_text else content
        if tts and EDGETTS_AVAILABLE and _web_tts_manager:
            async def _gen_and_send_tts():
                try:
                    # 根据 speaker 推断语音参数
                    voice = "zh-CN-XiaoxiaoNeural"  # 默认女声
                    style = None
                    rate = "+0%"
                    pitch = "+0Hz"
                    
                    if speaker == "DM-bot":
                        # DM旁白用深情男声，根据内容推断情绪
                        voice = "zh-CN-YunxiNeural"
                        text_lower = tts_content.lower()
                        if any(k in text_lower for k in ["愤怒", "怒", "危险", "警告"]):
                            style = "angry"
                        elif any(k in text_lower for k in ["悲伤", "难过", "痛苦", "哀"]):
                            style = "sad"
                        elif any(k in text_lower for k in ["开心", "恭喜", "欢呼", "庆祝"]):
                            style = "cheerful"
                        elif any(k in text_lower for k in ["神秘", "悄悄", "秘密"]):
                            style = "whispering"
                        elif any(k in text_lower for k in ["冷静", "分析", "观察"]):
                            style = "calm"
                    else:
                        # 玩家角色：用女声（EdgeTTS 中文女声表现更好）
                        voice = "zh-CN-XiaoxiaoNeural"
                    
                    # ===== 统一 TTS 文本清洗（写死逻辑，确保只读文字内容）=====
                    from engine import clean_tts_text
                    clean_text = clean_tts_text(tts_content, max_length=500)
                    
                    if not clean_text:
                        return
                    
                    print(f"🎤 [Web TTS] 生成语音: voice={voice}, style={style}, text={clean_text[:40]}...")
                    audio_data = await _web_tts_manager.text_to_speech(
                        clean_text, voice=voice, style=style, rate=rate, pitch=pitch
                    )
                    
                    if audio_data:
                        audio_b64 = _base64.b64encode(audio_data).decode("utf-8")
                        await sio.emit("tts_audio", {
                            "audio": audio_b64,
                            "text": clean_text[:100],
                        }, room=room_number)
                        print(f"✅ [Web TTS] 语音已发送 ({len(audio_data)} 字节)")
                except Exception as e:
                    print(f"❌ [Web TTS] 语音生成失败: {e}")
            
            asyncio.create_task(_gen_and_send_tts())

        # 场景图生成已统一由 plot_management.py 在每个 DM 回合结束后触发，
        # 避免 web_server.py 重复触发导致背景图切换两次。

    # 覆盖 typing：返回一个兼容 __anext__/aclose 和 async with 两种用法的上下文管理器
    class WebTypingContext:
        def __init__(self):
            self._entered = False

        async def __aenter__(self):
            self._entered = True
            await sio.emit("dm_status", {"message": random_dm_status()}, room=room_number)
            return self

        async def __aexit__(self, *args):
            if self._entered:
                await sio.emit("dm_status", {"message": ""}, room=room_number)
                self._entered = False

        # 兼容 __anext__/aclose 用法（旧版代码）
        async def __anext__(self):
            await self.__aenter__()

        async def aclose(self):
            await self.__aexit__()

    def typing_web():
        return WebTypingContext()

    # 覆盖 send_avatar_to_public：Web 端使用 send_image 发送图片 URL
    async def send_avatar_to_public_web(role_name, image_path):
        import os as _os
        if _os.path.exists(image_path):
            import base64 as _b64
            with open(image_path, "rb") as _f:
                _data = _b64.b64encode(_f.read()).decode()
            await sio.emit("image_message", {
                "url": f"data:image/png;base64,{_data}",
                "label": f"角色头像: {role_name}"
            }, room=room_number)
            print(f"✅ [Web] 已发送 {role_name} 头像到网页")
            return True
        print(f"❌ [Web] 图片文件不存在: {image_path}")
        return False

    # 覆盖 send_avatar_to_person：Web 端通过 private_message 发送图片
    async def send_avatar_to_person_web(player_name, image_path):
        import os as _os
        target_sid = None
        for sid, nickname in rooms[room_number]["players"].items():
            if nickname == player_name:
                target_sid = sid
                break
        if not target_sid:
            mapping = engine.manager.game_state.get("player_mapping", {})
            for discord_name, character_name in mapping.items():
                if discord_name == player_name or character_name == player_name:
                    for sid, nickname in rooms[room_number]["players"].items():
                        if nickname == discord_name:
                            target_sid = sid
                            break
        if not target_sid:
            print(f"❌ [Web] 找不到网页玩家发头像: {player_name}")
            return False
        if _os.path.exists(image_path):
            import base64 as _b64
            with open(image_path, "rb") as _f:
                _data = _b64.b64encode(_f.read()).decode()
            await sio.emit("private_message", {
                "player_name": player_name,
                "content": f"[角色头像图片]",
                "image": f"data:image/png;base64,{_data}",
                "timestamp": now_label()
            }, room=target_sid)
            return True
        return False

    # 覆盖 start_lobby：Web 版本不依赖 Discord
    async def start_lobby_web(channel):
        engine.current_channel = channel
        engine.main_channel = channel
        engine.room_state["status"] = "LOBBY"
        print("📡 [Engine-Web] Lobby 初始化中...")

        await engine.manager.start_lobby()

        guide_msg = (
            "📢 **灵感与角色征集开启！**\n\n"
            "1️⃣ **世界观建议**：在左侧面板输入世界观偏好\n"
            "   *例子：废土朋克，克苏鲁元素*\n\n"
            "2️⃣ **角色要求**：在左侧面板输入角色偏好\n"
            "   *例子：男，冷酷医生* 注意：在开始游戏前都可以修改，以最后一次为准\n\n"
            "💡 所有人准备好后，房主点击 **开始游戏** 正式开局！"
        )
        await send_to_channel_web(guide_msg, speaker="DM-bot")

        # 发送静态图片（通过 send_image 而非 discord.File）
        import os as _os
        img_path = _os.path.join(_os.path.dirname(__file__), "..", "img", "灵感收集大厅.png")
        if _os.path.exists(img_path):
            import base64 as _b64
            with open(img_path, "rb") as _f:
                _data = _b64.b64encode(_f.read()).decode()
            await sio.emit("image_message", {
                "url": f"data:image/png;base64,{_data}",
                "label": "灵感收集大厅"
            }, room=room_number)
        else:
            print(f"⚠️ 图片不存在: {img_path}")

    # 覆盖 start_game：Web 版本（不检查 suggestions 非空 - Web 端可以直接开始）
    async def start_game_web(channel):
        engine.current_channel = channel
        # 从 room dict 同步玩家到 game_state["players"]（Web 端玩家管理在 room dict）
        actual_room_players = {k: v for k, v in sid_to_name.items() if sid_to_room.get(k) == room_number}
        for name in actual_room_players.values():
            if name not in engine.manager.game_state["players"]:
                engine.manager.game_state["players"][name] = {"status": "joined"}

        player_names = list(engine.manager.game_state["players"].keys())
        player_count = len(player_names)
        print(f"\n--- [🚀 游戏正式启动-Web] ---")
        print(f"👥 最终锁定名单: {player_names}")
        print(f"🔢 最终人数: {player_count}")

        if player_count == 0:
            await send_to_channel_web("❌ **无法开始游戏**：当前还没有玩家报名！请先提交角色偏好。")
            return

        # Web 模式：允许无灵感池开始（使用默认世界观）
        if not engine.manager.game_state["suggestions"] and not engine.manager.game_state.get("custom_script"):
            print("⚠️ 灵感池为空，使用默认世界观")
            # 不阻止，直接继续

        # 重置 DM 消息计数（确保场景图生成从0开始计数）
        engine.room_state["_dm_msg_count"] = 0
        engine.room_state["_self_intro_done"] = []

        await send_to_channel_web(f"检测到共有 {player_count} 位已报名玩家，正在构建专属剧本...", speaker="DM-bot")

        prefs_str = " | ".join(engine.manager.game_state["suggestions"]) if engine.manager.game_state["suggestions"] else "奇幻冒险"

        role_dict = engine.manager.game_state.get('role_prefs', {})
        role_parts = []
        for name in player_names:
            pref = role_dict.get(name, "未设定具体要求（请 DM 根据世界观分配身份）")
            role_parts.append(f"玩家 [{name}]: {pref}")
        role_summary = "\n".join(role_parts)

        print(f"🚀 正在将数据发送至 Manager...")
        await engine.manager.start_game(prefs_str, role_summary, player_count)
        print(f"✅ [Engine-Web] manager.start_game 调用完成")

    # 覆盖 send_ai_vote：Web 端通过 chat_message 发送投票信息（简化版，无按钮）
    async def send_ai_vote_web(channel, title, options):
        async with engine.vote_lock:
            if engine.active_vote_view is not None:
                await send_to_channel_web("⚠️ 当前有正在进行的投票，请等待当前投票结束后再发起新投票。")
                return
            engine.active_vote_view = True  # 标记有活跃投票

            options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
            vote_msg = (
                f"🗳️ **请玩家投票决定：{title}**\n\n"
                f"{options_text}\n\n"
                f"请在公屏输入你的选择（如 \"1\" 或选项名称），30秒后截止。"
            )
            await send_to_channel_web(vote_msg, speaker="DM-bot")

            async def process_web_votes():
                await asyncio.sleep(30)
                engine.active_vote_view = None
                await send_to_channel_web(f"⏲️ 投票【{title}】已结束（Web 模式下暂不支持自动统计，请 DM 手动汇总结果）。", speaker="DM-bot")

            asyncio.create_task(process_web_votes())

    # 覆盖 send_player_card：定向发送给对应玩家（不再广播）
    async def send_player_card_web(card_data: dict):
        room = rooms[room_number]
        player_id = card_data.get("player_id", "")
        target_sid = None

        # 第一层：直接在 players 中按名字匹配
        for sid, nickname in room["players"].items():
            if nickname == player_id:
                target_sid = sid
                break

        # 第二层：通过 player_mapping 映射（discord_name -> 角色名）
        if not target_sid:
            mapping = engine.manager.game_state.get("player_mapping", {})
            for disc_name, char_name in mapping.items():
                if disc_name == player_id or char_name == card_data.get("role_name", ""):
                    for sid, nickname in room["players"].items():
                        if nickname == disc_name:
                            target_sid = sid
                            break
                if target_sid:
                    break

        # 第三层：通过 player_characters 中的角色名反查
        if not target_sid:
            chars = engine.manager.game_state.get("long_term_memory", {}).get("player_characters", {})
            for p_name, char_data in chars.items():
                if char_data.get("role_name") == card_data.get("role_name", ""):
                    for sid, nickname in room["players"].items():
                        if nickname == p_name:
                            target_sid = sid
                            break
                if target_sid:
                    break

        if target_sid:
            print(f"✅ [Web] 角色卡已发送给 {player_id} (sid={target_sid})")
            await sio.emit("player_card", card_data, room=target_sid)
        else:
            print(f"❌ [Web] 找不到玩家 sid 来发送角色卡: player_id={player_id}, role_name={card_data.get('role_name')}")
            print(f"   当前房间玩家: {list(room['players'].values())}")
            print(f"   player_mapping: {engine.manager.game_state.get('player_mapping', {})}")

    engine.send_to_person = send_to_person
    engine.send_image = send_image
    engine.send_player_card = send_player_card_web
    engine.send_to_channel = send_to_channel_web
    engine.send_to_public = send_to_public_web
    engine.typing = typing_web
    engine.send_avatar_to_public = send_avatar_to_public_web
    engine.send_avatar_to_person = send_avatar_to_person_web
    engine.start_lobby = start_lobby_web
    engine.start_game = start_game_web
    engine.send_ai_vote = send_ai_vote_web

    # 回合变更通知（Web端）
    async def send_round_change_web(current_round, total_rounds, scene_name, scene_description):
        await sio.emit("round_change", {
            "current_round": current_round,
            "total_rounds": total_rounds,
            "scene_name": scene_name,
            "scene_description": scene_description,
            "is_final_round": current_round >= total_rounds,
        }, room=room_number)
        print(f"🔄 [Web] round_change 事件已发送: 第{current_round}/{total_rounds}轮")
    engine.send_round_change = send_round_change_web

    # 结局卡片发送（Web端）— 强制转 base64，绝不发送原始 HTTPS URL
    async def send_game_ending_web(card_data: dict):
        from image_cache import url_to_base64, _url_to_base64_sync

        raw_url = card_data.get("image_url", "")
        if raw_url and not raw_url.startswith("data:"):
            print(f"🃏 [Web] 结局卡片图片转 base64: url={raw_url[:80]}...")
            result_b64 = await url_to_base64(raw_url)
            if not result_b64:
                result_b64 = await asyncio.to_thread(_url_to_base64_sync, raw_url)
            if result_b64:
                card_data = {**card_data, "image_url": result_b64}
                print(f"✅ [Web] 结局卡片 base64 转换成功")
            else:
                # 转换失败则移除 image_url，避免前端渲染失败
                card_data = {k: v for k, v in card_data.items() if k != "image_url"}
                print(f"⚠️ [Web] 结局卡片 base64 转换失败，已移除 image_url")
        await sio.emit("game_ending", card_data, room=room_number)
        print(f"🃏 [Web] game_ending 事件已发送到房间 {room_number}")
    engine.send_game_ending = send_game_ending_web


async def emit_room_state(room_number: str, sid: str | None = None) -> None:
    room = rooms[room_number]
    engine = room["engine"]
    owner_sid = room.get("owner_sid")
    owner_name = sid_to_name.get(owner_sid, "") if owner_sid else ""
    payload = {
        "room_number": room_number,
        "room_name": room["name"],
        "players": list(room["players"].values()),
        "owner_name": owner_name,
        "stage": engine.room_state.get("status", "IDLE"),
        "scene": {
            "name": engine.manager.game_state.get("scene", "等待开场"),
            "description": engine.manager.game_state.get("long_term_memory", {}).get(
                "time_space", "玩家正在提交世界观和角色偏好。"
            ),
        },
        "suggestions": engine.manager.game_state.get("suggestions", []),
        "role_prefs": engine.manager.game_state.get("role_prefs", {}),
    }
    await sio.emit("room_state", payload, room=sid or room_number)


async def create_game_room(room_name: str | None = None) -> dict[str, Any]:
    room_number = make_room_number()
    scoped_sio = ScopedSio(sio, room_number)
    engine = GameEngine(FakeBot(), scoped_sio)
    channel = WebChannel(room_number, room_name or f"网页房间 {room_number}")
    engine.current_channel = channel
    engine.main_channel = channel
    engine.room_thread = channel
    patch_engine_for_web(engine, room_number)

    room = {
        "room_number": room_number,
        "name": channel.name,
        "engine": engine,
        "channel": channel,
        "players": {},
        "owner_sid": None,  # 房主 sid（第一个加入的玩家）
    }
    rooms[room_number] = room

    try:
        await engine.start_lobby(channel)
    except Exception as e:
        print(f"❌ [Web] start_lobby 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        # 清理已创建的房间
        del rooms[room_number]
        raise

    return room


async def join_player_to_room(sid: str, room_number: str, nickname: str) -> None:
    if room_number not in rooms:
        await sio.emit("join_error", {"message": f"房间 {room_number} 不存在。"}, room=sid)
        return

    old_room_number = sid_to_room.get(sid)
    if old_room_number and old_room_number in rooms:
        old_room = rooms[old_room_number]
        await sio.leave_room(sid, old_room_number)
        old_room["players"].pop(sid, None)
        old_room["channel"].members = [m for m in old_room["channel"].members if m.sid != sid]
        await emit_room_state(old_room_number)

    room = rooms[room_number]
    sid_to_room[sid] = room_number
    sid_to_name[sid] = nickname
    room["players"][sid] = nickname
    # 如果还没有房主，第一个加入的人自动成为房主
    if not room.get("owner_sid"):
        room["owner_sid"] = sid
    # 同步到 game_state["players"]（供 game_flow 使用）
    if nickname not in room["engine"].manager.game_state["players"]:
        room["engine"].manager.game_state["players"][nickname] = {"status": "joined"}
    room["channel"].members = [m for m in room["channel"].members if m.sid != sid]
    room["channel"].members.append(WebMember(nickname, sid))
    await sio.enter_room(sid, room_number)
    await sio.emit("chat_message", chat_payload("系统", f"{nickname} 加入了房间。"), room=room_number)
    await emit_room_state(room_number)


@app.get("/health")
async def health():
    return {"ok": True, "rooms": len(rooms)}


@app.get("/api/rooms")
async def list_rooms():
    return [
        {
            "room_number": number,
            "name": room["name"],
            "players": len(room["players"]),
            "stage": room["engine"].room_state.get("status", "IDLE"),
        }
        for number, room in rooms.items()
    ]


@app.get("/api/proxy-image")
async def proxy_image(url: str):
    """前端兜底：将外部 HTTPS URL 通过后端代理转 base64，避免 CORS 泄漏"""
    import base64
    import aiohttp
    from urllib.parse import unquote
    try:
        target = unquote(url)
        if not (target.startswith("http://") or target.startswith("https://")):
            return PlainTextResponse("invalid url", status_code=400)
        async with aiohttp.ClientSession() as session:
            async with session.get(target, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    img_bytes = await resp.read()
                    b64 = base64.b64encode(img_bytes).decode()
                    return PlainTextResponse(f"data:image/png;base64,{b64}")
                else:
                    return PlainTextResponse("download failed", status_code=502)
    except Exception as e:
        print(f"❌ [Proxy] 图片代理失败: {e}")
        return PlainTextResponse("proxy error", status_code=500)


from fastapi.responses import PlainTextResponse


# 重连缓冲：disconnect 后保留 N 秒，connect 时可以恢复
_PENDING_RECONNECT: dict[str, tuple[str, str, float]] = {}  # sid -> (room_number, nickname, disconnect_time)


@sio.event
async def connect(sid, environ):
    print(f"🌐 客户端连接: {sid}")
    # 检查是否有待恢复的重连（同 sid 重连场景，如短时断网）
    pending = _PENDING_RECONNECT.pop(sid, None)
    if pending:
        room_number, nickname, _ = pending
        if room_number in rooms:
            print(f"🔄 [重连] {nickname} 恢复加入房间 {room_number}")
            await _restore_player(sid, room_number, nickname)
            return


@sio.event
async def disconnect(sid):
    room_number = sid_to_room.get(sid)
    nickname = sid_to_name.get(sid, f"访客_{sid[:4]}")
    if room_number and room_number in rooms:
        # 暂存到重连缓冲（30秒宽限期）
        _PENDING_RECONNECT[sid] = (room_number, nickname, time.time())
        room = rooms[room_number]
        was_owner = (room.get("owner_sid") == sid)
        room["players"].pop(sid, None)
        room["channel"].members = [m for m in room["channel"].members if m.sid != sid]
        sid_to_room.pop(sid, None)
        sid_to_name.pop(sid, None)

        # 房主离开时，转移给下一个玩家
        if was_owner and room["players"]:
            new_owner_sid = next(iter(room["players"].keys()))
            new_owner_name = room["players"][new_owner_sid]
            room["owner_sid"] = new_owner_sid
            await sio.emit("chat_message", chat_payload("系统", f"👑 {nickname} 离开了房间，房主变更为 {new_owner_name}。"), room=room_number)
            print(f"👑 [Owner] 房主从 {nickname} 转移给 {new_owner_name}")
        elif was_owner and not room["players"]:
            room["owner_sid"] = None
            await sio.emit("chat_message", chat_payload("系统", f"👑 房主 {nickname} 离开了房间，房间内暂无玩家。"), room=room_number)
        else:
            await sio.emit("chat_message", chat_payload("系统", f"{nickname} 离开了房间。"), room=room_number)

        await emit_room_state(room_number)
    else:
        sid_to_room.pop(sid, None)
        sid_to_name.pop(sid, None)
    print(f"🌐 客户端断开: {sid}")


async def _restore_player(sid: str, room_number: str, nickname: str):
    """静默恢复玩家（不发送加入/离开消息）"""
    room = rooms[room_number]
    sid_to_room[sid] = room_number
    sid_to_name[sid] = nickname
    room["players"][sid] = nickname
    # 检查 member 是否已存在
    existing = [m for m in room["channel"].members if m.sid == sid]
    if not existing:
        room["channel"].members.append(WebMember(nickname, sid))
    await sio.enter_room(sid, room_number)
    # 发送完整状态恢复
    await emit_room_state(room_number, sid=sid)
    # 单独发送玩家角色卡（如果有）
    engine = room["engine"]
    mgr = engine.manager
    mapping = mgr.game_state.get("player_mapping", {})
    chars = mgr.game_state.get("long_term_memory", {}).get("player_characters", {})
    if nickname in mapping:
        char_name = mapping[nickname]
        char_data = chars.get(char_name, {})
        if char_data:
            await sio.emit("player_card", {
                "player_id": nickname,
                "role_name": char_data.get("role_name", char_name),
                "identity": char_data.get("identity", ""),
                "public_bio": char_data.get("public_bio", ""),
                "personal_bio": char_data.get("personal_bio", ""),
                "relationships": char_data.get("relationships", []),
                "secret": char_data.get("secret", ""),
                "goal": char_data.get("goal", ""),
                "attributes": char_data.get("attributes", {}),
            }, room=sid)


@sio.on("reconnect_room")
async def reconnect_room(sid, data):
    """前端刷新页面后自动重连"""
    data = data or {}
    nickname = data.get("nickname", "").strip()
    room_number = str(data.get("room_number", "")).strip()
    if not nickname or not room_number:
        await sio.emit("join_error", {"message": "重连信息不完整，请手动加入。"}, room=sid)
        return
    if room_number not in rooms:
        await sio.emit("join_error", {"message": f"房间 {room_number} 已不存在。"}, room=sid)
        return
    room = rooms[room_number]
    # 检查昵称是否在玩家列表中
    if nickname not in room["players"].values():
        await sio.emit("join_error", {"message": f"玩家 {nickname} 不在房间中，请重新加入。"}, room=sid)
        return
    print(f"🔄 [重连] {nickname} 通过前端请求恢复房间 {room_number}")
    await _restore_player(sid, room_number, nickname)
    await sio.emit("room_joined", {"room_number": room_number, "room_name": room["name"]}, room=sid)


@sio.on("create_room")
async def create_room(sid, data):
    data = data or {}
    nickname = data.get("nickname", "").strip() or f"访客_{sid[:4]}"
    try:
        room = await create_game_room(data.get("room_name"))
        await join_player_to_room(sid, room["room_number"], nickname)
        room["owner_sid"] = sid  # 第一加入者为房主
        await sio.emit("room_created", {"room_number": room["room_number"], "room_name": room["name"], "is_owner": True}, room=sid)
    except Exception as e:
        print(f"❌ [Web] 创建房间失败: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit("join_error", {"message": f"创建房间失败：{str(e)}"}, room=sid)


# 端午特辑房间（快速开始，跳过征集环节）
_FESTIVAL_SCRIPT = None

def _load_festival_script():
    global _FESTIVAL_SCRIPT
    if _FESTIVAL_SCRIPT is not None:
        return _FESTIVAL_SCRIPT
    import json, os
    json_path = os.path.join(os.path.dirname(__file__), "..", "DBFestival.json")
    with open(json_path, "r", encoding="utf-8") as f:
        _FESTIVAL_SCRIPT = json.load(f)
    return _FESTIVAL_SCRIPT


def _create_festival_room_fast(room_name: str) -> dict[str, Any]:
    """为节日模式快速创建房间（纯同步，<1ms，跳过所有 I/O）"""
    room_number = make_room_number()
    scoped_sio = ScopedSio(sio, room_number)
    engine = GameEngine(FakeBot(), scoped_sio)
    channel = WebChannel(room_number, room_name or f"网页房间 {room_number}")
    engine.current_channel = channel
    engine.main_channel = channel
    engine.room_thread = channel
    patch_engine_for_web(engine, room_number)

    # 最小化初始化：只设置状态，不发送 lobby 引导消息和图片
    engine.room_state["status"] = "LOBBY"
    engine.room_state["_dm_msg_count"] = 0
    engine.room_state["_self_intro_done"] = []
    engine.manager.game_state["scene"] = "端午龙舟"

    room = {
        "room_number": room_number,
        "name": channel.name,
        "engine": engine,
        "channel": channel,
        "players": {},
    }
    rooms[room_number] = room
    print(f"🐉 [Festival] 快速房间已创建: {room_number}")
    return room


@sio.on("create_festival_room")
async def create_festival_room(sid, data):
    """端午特辑快速游戏：创建房间 + 直接启动剧本"""
    data = data or {}
    nickname = data.get("nickname", "").strip() or f"访客_{sid[:4]}"
    total_rounds = min(max(int(data.get("total_rounds", 15)), 5), 30)
    t_start = time.time()

    try:
        # === 阶段1：创建房间（纯同步，< 1ms） ===
        room = _create_festival_room_fast(f"端午特辑-{nickname[:6]}房")
        room["engine"].manager.game_state["total_rounds"] = total_rounds

        # === 阶段2：立即通知前端（不等任何 I/O，先清空15秒超时！） ===
        await sio.emit("room_created", {
            "room_number": room["room_number"],
            "room_name": room["name"],
            "festival_mode": True,
        }, room=sid)
        print(f"🐉 [Festival] room_created 已发出 ({time.time()-t_start:.2f}s)")

        # === 阶段3：加入玩家（前端超时已清除，不着急） ===
        await join_player_to_room(sid, room["room_number"], nickname)

        # === 阶段4：启动剧本（前端超时已清除，不着急） ===
        await room["engine"].manager.game_flow.start_festival_game(nickname, total_rounds)

        await emit_room_state(room["room_number"])
        print(f"🐉 [Festival] 端午特辑游戏已启动：{room['room_number']}，玩家：{nickname} ({time.time()-t_start:.2f}s)")
    except Exception as e:
        print(f"❌ [Festival] 端午特辑房间创建失败: {e} ({time.time()-t_start:.2f}s)")
        import traceback
        traceback.print_exc()
        await sio.emit("join_error", {"message": f"端午特辑启动失败：{str(e)}"}, room=sid)


@sio.on("join_room")
async def join_room(sid, data):
    data = data or {}
    nickname = data.get("nickname", "").strip() or f"访客_{sid[:4]}"
    room_number = str(data.get("room_number", "")).strip()
    if not room_number:
        await sio.emit("join_error", {"message": "请输入房间号。"}, room=sid)
        return
    await join_player_to_room(sid, room_number, nickname)
    if room_number in rooms:
        await sio.emit("room_joined", {"room_number": room_number, "room_name": rooms[room_number]["name"]}, room=sid)


@sio.on("submit_preference")
async def submit_preference(sid, data):
    data = data or {}
    room_number = sid_to_room.get(sid)
    if not room_number or room_number not in rooms:
        await sio.emit("join_error", {"message": "请先创建或加入房间。"}, room=sid)
        return

    room = rooms[room_number]
    engine = room["engine"]
    player_name = sid_to_name.get(sid, f"访客_{sid[:4]}")
    worldview = data.get("worldview", "").strip()
    role = data.get("role", "").strip()

    if worldview:
        await engine.add_player_suggestion(player_name, worldview, room["channel"])
    if role:
        await engine.add_player_role_pref(player_name, role, room["channel"])

    await emit_room_state(room_number)


@sio.on("start_game")
async def start_game(sid, data=None):
    room_number = sid_to_room.get(sid)
    if not room_number or room_number not in rooms:
        await sio.emit("join_error", {"message": "请先创建或加入房间。"}, room=sid)
        return

    room = rooms[room_number]
    # 只有房主可以开始游戏
    if room.get("owner_sid") and room["owner_sid"] != sid:
        await sio.emit("chat_message", chat_payload("系统", "⚠️ 只有房主才能开始游戏。"), room=sid)
        return

    data = data or {}
    total_rounds = int(data.get("total_rounds", 15))
    # 限制回合数范围
    total_rounds = max(5, min(30, total_rounds))
    room["engine"].manager.game_state["total_rounds"] = total_rounds
    print(f"🎮 [Web] 设置游戏回合数: {total_rounds}")
    # 通知所有玩家进入等待状态
    await sio.emit("game_generating", {}, room=room_number)
    try:
        await room["engine"].start_game(room["channel"])
    except Exception as e:
        print(f"❌ [Web] start_game 异常: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit("stage_change", {"to": "LOBBY"}, room=room_number)
        await sio.emit("chat_message", chat_payload("DM", f"⚠️ 游戏启动失败: {str(e)}"), room=room_number)
    await emit_room_state(room_number)


@sio.on("send_message")
async def send_message(sid, data):
    content = (data or {}).get("content", "").strip()
    if not content:
        return
    room_number = sid_to_room.get(sid)
    if not room_number or room_number not in rooms:
        await sio.emit("join_error", {"message": "请先创建或加入房间。"}, room=sid)
        return

    room = rooms[room_number]
    engine = room["engine"]
    player_name = sid_to_name.get(sid, f"访客_{sid[:4]}")

    await sio.emit("chat_message", chat_payload(player_name, content), room=room_number)
    if engine.room_state.get("status") == "PLAYING":
        await engine.handle_player_input(content, player_name, room["channel"])


@sio.on("self_intro_done")
async def self_intro_done(sid, data):
    """玩家完成自我介绍"""
    room_number = sid_to_room.get(sid)
    if not room_number or room_number not in rooms:
        return
    room = rooms[room_number]
    engine = room["engine"]
    player_name = sid_to_name.get(sid, f"访客_{sid[:4]}")

    # 记录已完成自我介绍的玩家
    intro_done = engine.room_state.get("_self_intro_done", [])
    if player_name not in intro_done:
        intro_done.append(player_name)
        engine.room_state["_self_intro_done"] = intro_done
        print(f"✅ [Intro] {player_name} 完成自我介绍 ({len(intro_done)}/{len(room['players'])})")

    # 检查是否所有玩家都完成了
    if len(intro_done) >= len(room["players"]):
        await sio.emit("self_intro_complete", {}, room=room_number)
        engine.room_state["_self_intro_done"] = []  # 重置
        print(f"✅ [Intro] 所有玩家完成自我介绍，游戏继续")

        # 游戏正式开始：重新播报开场剧情（之前被自我介绍全屏遮挡了）
        scene_name = engine.manager.game_state.get("scene", "未知场景")
        scene_desc = engine.manager.game_state.get("scene_description", "")
        time_space = engine.manager.game_state.get("long_term_memory", {}).get("time_space", "")

        # 更新场景背景图（触发 scene_update 事件 + 图片生成）
        await engine.update_scene(scene_name, scene_desc or scene_name)

        # 重新发送开场剧情（让玩家能看到）
        await sio.emit("chat_message", chat_payload("DM", f"🎉 **所有玩家已完成自我介绍！冒险正式开始！**\n\n🌍 {time_space}\n📍 {scene_name}"), room=room_number)

        # 从 chat_history 中找到开场剧情并重新发送
        chat_history = engine.manager.game_state.get("chat_history", [])
        # 倒序查找最近的 DM-bot 开场消息（包含"剧本已生成"或 public_story）
        for entry in reversed(chat_history):
            if entry.get("role") == "DM-bot" and ("🚀" in entry.get("content", "") or "剧本" in entry.get("content", "")):
                # 重新发送完整的开场剧情（不含"🚀 剧本已生成"的装饰语）
                full_story = entry.get("content", "")
                # 只提取故事本体部分，去除非故事的系统提示
                lines = full_story.split("\n")
                story_lines = []
                for line in lines:
                    if line.strip() and not line.strip().startswith("🚀") and "剧本已生成" not in line:
                        story_lines.append(line)
                if story_lines:
                    story_text = "\n".join(story_lines)
                    await sio.emit("chat_message", chat_payload("DM-bot", story_text), room=room_number)
                    print(f"📖 [Intro] 已重新播报开场剧情 ({len(story_text)} 字)")
                break

        print(f"🎬 [Intro] 游戏正式开始，场景: {scene_name}")
    else:
        # 通知房间内其他人
        await sio.emit("chat_message", chat_payload("DM", f"✅ {player_name} 已完成自我介绍，等待其他玩家...（{len(intro_done)}/{len(room['players'])}）"), room=room_number)


current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
dist_path = os.path.join(root_path, "dist")
assets_path = os.path.join(dist_path, "assets")

if os.path.exists(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

public_files = {"vite.svg", "灵感收集大厅.png", "logo.png"}


@app.get("/")
@app.head("/")
async def serve_index():
    index_file = os.path.join(dist_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": "请先运行 npm run build 生成 dist。"}


@app.head("/health")
async def health_head():
    return {}


@app.get("/{path:path}")
async def serve_static_or_index(path: str):
    if path in public_files:
        file_path = os.path.join(dist_path, path)
        if os.path.exists(file_path):
            return FileResponse(file_path)
    index_file = os.path.join(dist_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": "请先运行 npm run build 生成 dist。"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(socket_app, host="0.0.0.0", port=port)
