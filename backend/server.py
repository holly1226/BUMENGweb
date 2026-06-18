import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import asyncio
import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from dotenv import load_dotenv

# 导入核心模块
from engine import GameEngine
from multi_room_engine import MultiRoomEngine
# 导入 ChatTTS
from chat_tts_handler import initialize_tts

# --- 配置 ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
proxy_url = os.getenv("DISCORD_PROXY")

# 机器人配置
intents = discord.Intents.default()
intents.message_content = True
intents.members = True          # 必须在这
intents.presences = True        # 建议同时开启这个，有助于成员列表同步

# 调试：打印 intents 配置
print("\n=== Discord Intents 配置 ===")
print(f"message_content: {intents.message_content}")
print(f"members: {intents.members}")
print(f"presences: {intents.presences}")
print(f"guilds: {intents.guilds}")
print("=")

# 实例化 Bot 时必须把定义好的 intents 传进去
bot = commands.Bot(
    command_prefix="!",
    intents=intents,  # 确保这里传入了上面配置的对象
    proxy=proxy_url
)

# --- 初始化 Socket.io 和 FastAPI ---
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
socket_app = socketio.ASGIApp(sio, app)

# --- 初始化游戏引擎 ---
game_engine = GameEngine(bot, sio)
# 多房间管理器
multi_room_engine = MultiRoomEngine(bot, sio)

# === 房间选择菜单和模态框 ===

class JoinRoomModal(Modal, title="加入游戏房间"):
    """加入房间的模态框"""
    room_number = TextInput(
        label="房间号",
        placeholder="请输入6位房间号（例如：234567）",
        max_length=6,
        min_length=6,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        """用户提交房间号时的处理"""
        print(f"\n🔍 [Modal] 用户 {interaction.user.name} 开始加入房间...")

        try:
            room_num = self.room_number.value.strip()
            print(f"🔍 [Modal] 输入的房间号: {room_num}")

            # 首先立即延迟响应，避免3秒超时
            await interaction.response.defer(thinking=True)
            print(f"✅ [Modal] 已延迟响应")

            # 检查房间是否存在
            if not multi_room_engine.room_exists(room_num):
                print(f"❌ [Modal] 房间不存在: {room_num}")
                error_msg = (
                    f"❌ **房间号不存在！**\n\n"
                    f"您输入的房间号是: `{room_num}`\n\n"
                    f"💡 **可能的原因**：\n"
                    f"  • 房间号输入错误\n"
                    f"  • 房间已被删除\n"
                    f"  • Bot已重启\n\n"
                    f"📋 请使用 `!房间列表` 查看所有活跃房间"
                )
                # 用私信而不是 ephemeral
                await interaction.user.send(error_msg)
                return

            # 获取房间对象
            room = multi_room_engine.get_room_by_number(room_num)
            print(f"✅ [Modal] 房间存在: {room_num}")

            # 获取房间的频道
            channel = bot.get_channel(room.channel_id)
            if not channel:
                print(f"❌ [Modal] 频道不存在或已删除: {room.channel_id}")
                error_msg = (
                    f"❌ **房间的频道已被删除！**\n\n"
                    f"房间号 `{room_num}` 对应的频道不再存在。\n"
                    f"💡 请联系房间创建者重新创建房间。"
                )
                # 用私信而不是 ephemeral
                await interaction.user.send(error_msg)
                return

            # 玩家加入房间
            player_name = interaction.user.name
            multi_room_engine.join_room(player_name, room_num)

            # 确保房间引擎有正确的Thread设置
            if room.thread:
                room.engine.room_thread = room.thread
                print(f"✅ [Modal] 已为玩家 {player_name} 设置房间 Thread")

            print(f"✅ [Modal] 正在启动大厅...")

            # 在房间 Thread 中发送加入通知
            if room.thread:
                join_notification = (
                    f"👋 **玩家加入**\n\n"
                    f"🎯 房间号: `{room_num}`\n"
                    f"👤 玩家: **{player_name}**\n"
                    f"👥 当前房间人数: {room.get_player_count()} 人"
                )
                try:
                    await room.thread.send(join_notification)
                    print(f"📢 [Thread] 已在房间 {room_num} 的 Thread 中发送加入通知")
                except Exception as e:
                    print(f"⚠️ [Thread] 发送加入通知失败: {e}")

            # 构建成功消息（包含 Thread 链接）
            thread_mention = f"<#{room.thread.id}>" if room.thread else "（Thread 创建中...）"
            success_msg = (
                f"✅ **成功加入房间！**\n\n"
                f"🎯 房间号: `{room_num}`\n"
                f"🧵 **请在 Thread 中发送消息**: {thread_mention}\n\n"
                f"💡 发送消息步骤：\n"
                f"  1️⃣ 点击上面的 Thread 链接进入\n"
                f"  2️⃣ 在 Thread 中输入消息\n"
                f"  3️⃣ 其他房间的玩家看不到您的消息\n\n"
                f"🎮 游戏命令：\n"
                f"  • `!建议 [内容]` - 提交世界观建议\n"
                f"  • `!角色 [性别/性格]` - 提交角色要求\n"
                f"  • `!开始游戏` - 开始游戏（创建者）"
            )

            # 用私信而不是 ephemeral
            await interaction.user.send(success_msg)
            print(f"✅ [Modal] 加入房间成功！")

        except Exception as e:
            print(f"\n❌ [Modal Error] 发生异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

            # 用私信发送错误消息
            try:
                error_msg = (
                    f"❌ **加入房间时出错**\n\n"
                    f"错误信息: `{type(e).__name__}: {str(e)}`\n\n"
                    f"💡 请稍后重试或联系管理员。"
                )
                await interaction.user.send(error_msg)
            except Exception as err:
                print(f"❌ [Modal] 无法发送错误消息: {err}")


class RoomSelectionView(View):
    """房间选择菜单"""

    def __init__(self, ctx_channel):
        super().__init__(timeout=300)  # 5分钟超时
        self.ctx_channel = ctx_channel

    @discord.ui.button(label="🎮 创建房间", style=discord.ButtonStyle.primary)
    async def create_room(self, interaction: discord.Interaction, button: Button):
        """创建新房间"""
        if interaction.user.bot:
            return

        print(f"\n🎮 [CreateRoom] 用户 {interaction.user.name} 开始创建房间...")

        try:
            # 立即延迟响应，避免3秒超时
            await interaction.response.defer(thinking=True)
            print(f"✅ [CreateRoom] 已延迟响应")

            # 创建房间
            player_name = interaction.user.name
            room, room_number = multi_room_engine.create_room(
                self.ctx_channel.id,
                self.ctx_channel.name,
                player_name  # 添加创建者名称
            )
            print(f"✅ [CreateRoom] 房间已创建，房间号: {room_number}")

            # 为房间创建 Discord Thread
            try:
                thread_name = f"🎮 房间 {room_number} - {self.ctx_channel.name}"
                thread = await self.ctx_channel.create_thread(
                    name=thread_name,
                    auto_archive_duration=10080  # 7 天后自动归档
                )
                room.thread = thread
                room.engine.room_thread = thread  # 设置房间引擎的Thread
                print(f"✅ [CreateRoom] 已为房间 {room_number} 创建 Thread: {thread.name}")
            except Exception as e:
                print(f"⚠️ [CreateRoom] 创建 Thread 失败: {e}")
                # 即使Thread创建失败，也继续流程

            # 启动大厅
            await room.engine.start_lobby(self.ctx_channel)
            print(f"✅ [CreateRoom] 大厅已启动")

            # 在房间 Thread 中发送房间创建通知
            if room.thread:
                create_notification = (
                    f"🎮 **房间已创建**\n\n"
                    f"🎯 房间号: `{room_number}`\n"
                    f"👤 房间创建者: **{player_name}**\n"
                    f"💬 欢迎来到房间！请等待其他玩家加入..."
                )
                try:
                    await room.thread.send(create_notification)
                    print(f"📢 [Thread] 已在房间 {room_number} 的 Thread 中发送创建通知")
                except Exception as e:
                    print(f"⚠️ [Thread] 发送创建通知失败: {e}")

            # 构建成功消息（包含 Thread 链接）
            thread_mention = f"<#{room.thread.id}>" if room.thread else "（Thread 创建中...）"
            success_msg = (
                f"✅ **房间创建成功！**\n\n"
                f"🎯 **房间号**: `{room_number}`\n"
                f"🧵 **房间 Thread**: {thread_mention}\n\n"
                f"📝 **分享给其他玩家**：\n"
                f"  1️⃣ 告诉他们房间号 `{room_number}`\n"
                f"  2️⃣ 他们使用 `!准备` → 加入房间 → 输入房间号\n"
                f"  3️⃣ 他们会得到 Thread 链接\n\n"
                f"💬 **发送消息**：\n"
                f"  • 创建者和玩家都应该在 Thread 中发送消息\n"
                f"  • 其他房间的玩家看不到这个 Thread 的消息"
            )

            # 用私信发送成功信息，而不是公屏 ephemeral（避免被所有人看到）
            await interaction.user.send(success_msg)
            print(f"✅ [CreateRoom] 已通过私信发送房间创建成功信息")

        except Exception as e:
            print(f"\n❌ [CreateRoom Error] 发生异常: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

            try:
                error_msg = (
                    f"❌ **创建房间时出错**\n\n"
                    f"错误信息: `{type(e).__name__}: {str(e)}`\n\n"
                    f"💡 请稍后重试或联系管理员。"
                )
                await interaction.user.send(error_msg)
            except Exception as err:
                print(f"❌ [CreateRoom] 无法发送错误消息: {err}")

    @discord.ui.button(label="🔓 加入房间", style=discord.ButtonStyle.secondary)
    async def join_room(self, interaction: discord.Interaction, button: Button):
        """显示加入房间的模态框"""
        if interaction.user.bot:
            return

        await interaction.response.send_modal(JoinRoomModal())


# --- Discord 事件和命令处理 ---
@bot.event
async def on_ready():
    print(f"✅ Discord Bot 已上线: {bot.user.name}")

    # 初始化 ChatTTS（在后台线程中运行，不阻塞 Bot）
    def init_tts():
        print("🎤 正在初始化 EdgeTTS...")
        initialize_tts()
        print("🎤 EdgeTTS 初始化完成！")

    # 在后台线程初始化
    import threading
    tts_thread = threading.Thread(target=init_tts, daemon=True)
    tts_thread.start()

    await multi_room_engine.start_background_tasks()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.content.startswith('!'):
        await bot.process_commands(message)
    else:
        # 根据玩家名称找到玩家所在的房间
        player_name = message.author.name
        room_number = multi_room_engine.get_user_room(player_name)

        if not room_number:
            # 玩家还没有加入任何房间，忽略消息
            print(f"⚠️ [Message Filter] 玩家 {player_name} 的消息被过滤：还未加入房间")
            return

        # 获取房间对象
        room = multi_room_engine.get_room_by_number(room_number)
        if not room:
            print(f"⚠️ [Message Filter] 玩家 {player_name} 的房间不存在：{room_number}")
            return

        # 检查消息是否来自房间的 Thread
        if room.thread and message.channel.id == room.thread.id:
            # 消息来自房间的 Thread，正常处理
            print(f"✅ [Message] 玩家 {player_name} 在房间 {room_number} 的 Thread 中发送消息")
            await room.engine.handle_player_input(message.content, player_name, message.channel)
        elif not isinstance(message.channel, discord.Thread):
            # 消息来自主频道（不是 Thread），提示玩家应该在 Thread 中发送
            print(f"⚠️ [Message Filter] 玩家 {player_name} 的消息来自主频道，应该在 Thread 中发送")

            # 发送私信提示用户
            if room.thread:
                await message.author.send(
                    f"💡 **请在房间的 Thread 中发送消息**\n\n"
                    f"🎯 房间号: `{room_number}`\n"
                    f"🧵 Thread: <#{room.thread.id}>\n\n"
                    f"请点击 Thread 链接进去，在那里发送您的消息。"
                )
        else:
            # 消息来自某个 Thread，但不是这个房间的 Thread，忽略
            print(f"⚠️ [Message Filter] 玩家 {player_name} 的消息来自其他 Thread，被忽略")

@bot.command(name="准备")
async def start_lobby(ctx):
    """房间准备命令 - 显示创建/加入房间菜单"""
    print(f"\n📢 [准备] 用户 {ctx.author.name} 执行 !准备")

    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("❌ 该指令只能在公聊频道使用！")
        return

    print(f"✅ [准备] 显示房间选择菜单")
    # 显示房间选择菜单
    view = RoomSelectionView(ctx.channel)
    await ctx.author.send(
        "🎮 **欢迎来玩 TRPG 游戏！**\n\n"
        "请选择您的操作：\n"
        "• **创建房间** - 创建一个新的游戏房间（您会得到一个6位房间号）\n"
        "• **加入房间** - 输入房间号加入现有房间\n\n"
        "除非大家进入同一房间，否则不可以看到对方的留言",
        view=view
    )

@bot.command(name="建议")
async def add_suggestion(ctx, *, keyword: str):
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("❌ 该指令只能在公聊频道使用！")
        return

    player_name = ctx.author.name
    room_number = multi_room_engine.get_user_room(player_name)

    if not room_number:
        await ctx.send("❌ 您还未加入任何房间，请先输入 `!准备` 加入房间")
        return

    room = multi_room_engine.get_room_by_number(room_number)
    if not room:
        await ctx.send("❌ 房间不存在")
        return

    await room.engine.add_player_suggestion(player_name, keyword, ctx.channel)

@bot.command(name="角色")
async def role(ctx, *, pref: str):
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("❌ 该指令只能在公聊频道使用！")
        return

    player_name = ctx.author.name
    room_number = multi_room_engine.get_user_room(player_name)

    if not room_number:
        await ctx.send("❌ 您还未加入任何房间，请先输入 `!准备` 加入房间")
        return

    room = multi_room_engine.get_room_by_number(room_number)
    if not room:
        await ctx.send("❌ 房间不存在")
        return

    await room.engine.add_player_role_pref(player_name, pref, ctx.channel)

@bot.command(name="开始游戏")
async def start_game(ctx):
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("❌ 该指令只能在公聊频道使用！")
        return

    player_name = ctx.author.name
    room_number = multi_room_engine.get_user_room(player_name)

    if not room_number:
        await ctx.send("❌ 您还未加入任何房间，请先输入 `!准备` 加入房间")
        return

    room = multi_room_engine.get_room_by_number(room_number)
    if not room:
        await ctx.send("❌ 房间不存在")
        return

    print(f"🎯 [Server] 用户 {player_name} 在房间 {room_number} 触发了 !开始游戏 指令")
    await room.engine.start_game(ctx.channel)

@bot.command(name="重置")
async def reset_game(ctx):
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send("❌ 该指令只能在公聊频道使用！")
        return

    player_name = ctx.author.name
    room_number = multi_room_engine.get_user_room(player_name)

    if not room_number:
        await ctx.send("❌ 您还未加入任何房间，请先输入 `!准备` 加入房间")
        return

    room = multi_room_engine.get_room_by_number(room_number)
    if not room:
        await ctx.send("❌ 房间不存在")
        return

    await room.engine.reset_game(ctx.channel)

@bot.command(name="查看记忆")
async def show_long_term_memory(ctx):
    player_name = ctx.author.name
    room_number = multi_room_engine.get_user_room(player_name)

    if not room_number:
        await ctx.send("❌ 您还未加入任何房间，请先输入 `!准备` 加入房间")
        return

    room = multi_room_engine.get_room_by_number(room_number)
    if not room:
        await ctx.send("❌ 房间不存在")
        return

    memory = room.engine.manager.game_state.get("long_term_memory", {})

    if not memory or "entities" not in memory:
        await ctx.send("📭 数据库目前是空的，请先开始游戏。")
        return

    entities = memory.get("entities", {})

    # 构造展示文本
    msg = "📖 **【当前世界存档档案】**\n"
    msg += f"📜 **世界概括**: {memory.get('world_summary', '未知')}\n"
    msg += "---"

    # 提取角色、物品、场景
    chars = ", ".join(entities.get("characters", {}).keys()) or "无"
    items = ", ".join(entities.get("items", {}).keys()) or "无"
    scenes = ", ".join(entities.get("scenes", {}).keys()) or "无"

    msg += f"\n👥 **关键人物**: {chars}"
    msg += f"\n📦 **关键物品**: {items}"
    msg += f"\n📍 **已知场景**: {scenes}"

    await ctx.send(msg)

@bot.event
async def on_command_error(ctx, error):
    print(f"❌ [Discord Error] 指令执行出错: {error}")

@bot.command(name="房间列表")
async def list_all_rooms(ctx):
    """查看所有活跃房间"""
    rooms_info = multi_room_engine.get_all_rooms_info()

    if not rooms_info:
        await ctx.send("📭 当前没有任何活跃房间。")
        return

    embed = discord.Embed(
        title="🏢 所有活跃房间",
        description="这些是当前所有的游戏房间，您可以使用 `!准备` 然后输入房间号加入。",
        color=discord.Color.blurple()
    )

    for room_num, info in rooms_info.items():
        status = "🟢 进行中" if info["is_active"] else "🔴 等待中"
        channel_mention = f"<#{info['channel_id']}>"
        thread_mention = f"<#{info['thread_id']}>" if info.get('thread_id') else "无"

        embed.add_field(
            name=f"🎯 房间号: `{room_num}`",
            value=f"状态: {status}\n玩家: {info['players']}\n频道: {channel_mention}\nThread: {thread_mention}\n场景: {info['scene']}",
            inline=False
        )

    await ctx.send(embed=embed)


# --- Socket.io 事件处理 ---
# 追踪每个 Web 客户端连接到的房间
web_client_room_mapping = {}  # {sid: room_number}

@sio.event
async def connect(sid, environ):
    print(f"🌐 [WebSocket] 客户端已连接: {sid}")
    web_client_room_mapping[sid] = None

@sio.on('set_nickname')
async def set_nickname(sid, data):
    # 支持 channel_id 或 room_id（房间号）
    room_number = data.get("room_id") or data.get("room_number")
    channel_id = data.get("channel_id")

    if not room_number and not channel_id:
        print(f"⚠️ [Socket.io] set_nickname 缺少 room_id 或 channel_id，sid: {sid}")
        return

    web_client_room_mapping[sid] = room_number
    room = multi_room_engine.get_room_by_number(room_number) if room_number else None

    if not room:
        print(f"⚠️ [Socket.io] set_nickname - 房间不存在，room_number: {room_number}")
        return

    await room.engine.handle_set_nickname(sid, data)

@sio.on('join_room')
async def join_room(sid, data):
    # 支持 channel_id 或 room_id（房间号）
    room_number = data.get('room_id') or data.get('room_number')
    channel_id = data.get('channel_id')

    if not room_number and not channel_id:
        print(f"⚠️ [Socket.io] join_room 缺少 room_id 或 channel_id，sid: {sid}")
        return

    web_client_room_mapping[sid] = room_number
    room = multi_room_engine.get_room_by_number(room_number) if room_number else None

    if not room:
        print(f"⚠️ [Socket.io] join_room - 房间不存在，room_number: {room_number}")
        return

    web_room_id = data.get('web_room_id', 'public')
    await room.engine.handle_join_web_room(sid, web_room_id)

@sio.on('send_message')
async def handle_web_message(sid, data):
    room_number = web_client_room_mapping.get(sid)

    if not room_number:
        print(f"⚠️ [Socket.io] send_message - 客户端 {sid} 未指定房间")
        return

    room = multi_room_engine.get_room_by_number(room_number)

    if not room:
        print(f"⚠️ [Socket.io] send_message - 房间不存在: {room_number}")
        return

    user = room.engine.room_state["active_users"].get(sid, f"访客_{sid[:4]}")
    content = data.get("content")
    target_room = data.get("room", "public")

    if data.get("to_sid"):
        target_room = data["to_sid"]
        await room.engine.broadcast_chat(user, content, room_id=target_room)
        await room.engine.broadcast_chat(user, content, room_id=sid)
    else:
        await room.engine.broadcast_chat(user, content, room_id=target_room)

# --- 静态文件服务 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
dist_path = os.path.join(root_path, "dist")

print(f"📂 正在检查前端路径: {dist_path}")

assets_path = os.path.join(dist_path, "assets")
if os.path.exists(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

@app.get("/")
async def serve_index():
    index_file = os.path.join(dist_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": "找不到 index.html"}

@app.get("/{catchall:path}")
async def read_index(catchall: str):
    return FileResponse(os.path.join(dist_path, "index.html"))

# --- 主启动函数 ---
async def main():
    await multi_room_engine.start_background_tasks()

    config = uvicorn.Config(socket_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    # 启动 Web 服务器
    web_task = asyncio.create_task(server.serve())

    # 尝试启动 Discord Bot
    try:
        print(f"🔌 [Discord] 尝试连接，Token: {TOKEN[:20]}...{TOKEN[-10:]}")
        print(f"🌐 [Discord] 代理配置: {proxy_url if proxy_url else '无'}")
        await bot.start(TOKEN)
        await web_task
    except Exception as e:
        print(f"⚠️ Discord 连接失败： {e}")
        import traceback
        traceback.print_exc()
        # Web 服务继续运行
        await web_task
    finally:
        # 确保正确关闭 bot，清理连接器
        if not bot.is_closed():
            await bot.close()
        print("👋 程序正常退出")

    # 等待 Web 服务器（Bot 失败后 Web 继续运行）
    

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🚪 安全关闭")