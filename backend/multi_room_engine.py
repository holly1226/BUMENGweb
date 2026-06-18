"""
多房间游戏引擎 - 支持数字房间号系统
负责管理多个并发的游戏房间，每个房间有独立的游戏状态、房间号和管理器
"""
import asyncio
import random
from typing import Dict, Optional
from engine import GameEngine


class GameRoom:
    """单个游戏房间"""
    def __init__(self, room_number: str, channel_id: int, room_name: str, bot, sio):
        self.room_number = room_number          # 房间号（6位数字）
        self.channel_id = channel_id            # Discord 频道 ID
        self.room_name = room_name              # 房间名称
        self.engine = GameEngine(bot, sio)      # 该房间的独立游戏引擎
        self.is_active = False                  # 房间是否有活跃游戏
        self.created_at = None
        self.players = set()                    # 房间内的玩家 ID
        self.thread = None                      # 房间专属的 Discord Thread

    def add_player(self, player_id):
        """添加玩家"""
        self.players.add(player_id)

    def remove_player(self, player_id):
        """移除玩家"""
        self.players.discard(player_id)

    def get_player_count(self) -> int:
        """获取房间内玩家数"""
        return len(self.players)


class MultiRoomEngine:
    """多房间游戏引擎管理器"""

    def __init__(self, bot, sio):
        self.bot = bot
        self.sio = sio

        # 按房间号存储房间 (主要索引方式)
        self.rooms_by_number: Dict[str, GameRoom] = {}   # {room_number: GameRoom}

        # 用户到房间号的映射 - 跟踪每个玩家在哪个房间
        self.user_to_room: Dict[str, str] = {}  # {player_name: room_number}

        # 房间号到玩家集合的映射
        self.room_to_users: Dict[str, set] = {}  # {room_number: {player_names}}

        self.current_room_id: Optional[str] = None  # 当前操作的房间号 (改为房间号而不是频道号)

    def generate_room_number(self) -> str:
        """生成一个6位数字房间号"""
        while True:
            room_number = f"{random.randint(100000, 999999)}"
            if room_number not in self.rooms_by_number:
                return room_number

    def create_room(self, channel_id: int, room_name: str, creator_name: str) -> tuple[GameRoom, str]:
        """创建一个新的游戏房间

        Args:
            channel_id: 主游戏频道 ID
            room_name: 房间名称
            creator_name: 房间创建者名称

        Returns:
            (room, room_number) - 房间对象和房间号
        """
        # 生成房间号
        room_number = self.generate_room_number()

        # 创建房间
        room = GameRoom(room_number, channel_id, room_name, self.bot, self.sio)

        # 存储房间
        self.rooms_by_number[room_number] = room
        self.room_to_users[room_number] = set()

        # 创建者加入房间
        self.user_to_room[creator_name] = room_number
        self.room_to_users[room_number].add(creator_name)
        room.add_player(creator_name)

        print(f"✅ [MultiRoom] 创建房间: {room_name} | 房间号: {room_number} | 频道ID: {channel_id} | 创建者: {creator_name}")

        return room, room_number

    def get_room_by_number(self, room_number: str) -> Optional[GameRoom]:
        """通过房间号获取房间"""
        return self.rooms_by_number.get(room_number)

    def get_user_room(self, player_name: str) -> Optional[str]:
        """获取玩家当前所在的房间号"""
        return self.user_to_room.get(player_name)

    def get_room_users(self, room_number: str) -> set:
        """获取房间内的所有玩家"""
        return self.room_to_users.get(room_number, set())

    def room_exists(self, room_number: str) -> bool:
        """检查房间号是否存在"""
        return room_number in self.rooms_by_number

    def join_room(self, player_name: str, room_number: str) -> bool:
        """玩家加入房间

        Args:
            player_name: 玩家名称
            room_number: 房间号

        Returns:
            是否成功加入
        """
        if not self.room_exists(room_number):
            return False

        # 如果玩家已在其他房间，先移出
        old_room = self.user_to_room.get(player_name)
        if old_room and old_room in self.room_to_users:
            self.room_to_users[old_room].discard(player_name)
            room_obj = self.rooms_by_number.get(old_room)
            if room_obj:
                room_obj.remove_player(player_name)

        # 加入新房间
        self.user_to_room[player_name] = room_number
        self.room_to_users[room_number].add(player_name)

        room = self.rooms_by_number[room_number]
        room.add_player(player_name)

        print(f"👤 [MultiRoom] 玩家 {player_name} 加入房间 {room_number}")
        return True

    def leave_room(self, player_name: str) -> Optional[str]:
        """玩家离开房间

        Returns:
            玩家离开的房间号，如果玩家不在任何房间返回 None
        """
        room_number = self.user_to_room.get(player_name)
        if not room_number:
            return None

        # 移除玩家
        self.user_to_room.pop(player_name, None)
        if room_number in self.room_to_users:
            self.room_to_users[room_number].discard(player_name)

        room = self.rooms_by_number.get(room_number)
        if room:
            room.remove_player(player_name)

        print(f"👤 [MultiRoom] 玩家 {player_name} 离开房间 {room_number}")
        return room_number

    def get_active_rooms(self) -> Dict[str, GameRoom]:
        """获取所有活跃房间（按房间号）"""
        return {room_num: room for room_num, room in self.rooms_by_number.items() if room.is_active}

    def get_room_count(self) -> int:
        """获取房间总数"""
        return len(self.rooms_by_number)

    def get_active_room_count(self) -> int:
        """获取活跃房间数"""
        return len(self.get_active_rooms())

    def get_all_rooms_info(self) -> Dict:
        """获取所有房间信息"""
        return {
            room_num: {
                "room_number": room_num,
                "room_name": room.room_name,
                "is_active": room.is_active,
                "players": room.get_player_count(),
                "status": room.engine.room_state.get("status", "IDLE"),
                "scene": room.engine.manager.game_state.get("scene", "未知"),
                "channel_id": room.channel_id,
                "thread_id": room.thread.id if room.thread else None
            }
            for room_num, room in self.rooms_by_number.items()
        }

    # === 便捷方法 ===

    async def start_lobby(self, channel_id: int, channel, creator_name: str):
        """启动大厅（在主游戏频道中创建一个新房间和对应的 Thread）"""
        room, room_number = self.create_room(channel_id, channel.name, creator_name)
        self.current_room_id = room_number

        # 为房间创建 Discord Thread
        try:
            thread_name = f"🎮 房间 {room_number} - {channel.name}"
            thread = await channel.create_thread(
                name=thread_name,
                auto_archive_duration=10080  # 7 天后自动归档
            )
            room.thread = thread
            print(f"🧵 [Thread] 为房间 {room_number} 创建了 Thread: {thread.name} (ID: {thread.id})")
        except Exception as e:
            print(f"❌ [Thread] 创建 Thread 失败: {e}")

        # 在房间的 GameEngine 中存储 thread 引用
        room.engine.room_thread = thread

        await room.engine.start_lobby(channel)


    async def start_game(self, room_number: str, channel):
        """启动游戏"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            room.is_active = True
            await room.engine.start_game(channel)

    async def stop_game(self, room_number: str, channel):
        """停止房间的游戏"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            room.is_active = False
            await room.engine.reset_game(channel)

    async def handle_player_input(self, room_number: str, content: str, player_name: str, channel):
        """处理玩家输入"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            await room.engine.handle_player_input(content, player_name, channel)

    async def add_player_suggestion(self, room_number: str, player_name: str, keyword: str, channel):
        """添加玩家建议"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            await room.engine.add_player_suggestion(player_name, keyword, channel)

    async def add_player_role_pref(self, room_number: str, player_name: str, pref: str, channel):
        """添加玩家角色偏好"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            await room.engine.add_player_role_pref(player_name, pref, channel)

    async def on_web_client_connect(self, room_number: str, sid: str):
        """Web客户端连接"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            await room.engine.on_web_client_connect(sid)

    async def handle_set_nickname(self, room_number: str, sid: str, data):
        """处理昵称设置"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            await room.engine.handle_set_nickname(sid, data)

    async def handle_join_web_room(self, room_number: str, sid: str, web_room_id: str):
        """Web客户端加入房间"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            await room.engine.handle_join_web_room(sid, web_room_id)

    async def broadcast_chat(self, room_number: str, user: str, content: str, room_info: str = "public"):
        """广播聊天消息到指定房间"""
        room = self.get_room_by_number(room_number)
        if room:
            self.current_room_id = room_number
            await room.engine.broadcast_chat(user, content, room_id=room_info)

    async def start_background_tasks(self):
        """启动所有房间的后台任务"""
        tasks = []
        for room in self.rooms_by_number.values():
            tasks.append(room.engine.manager.start_background_tasks())

        if tasks:
            await asyncio.gather(*tasks)
        print(f"💓 所有房间的后台任务已启动 ({len(tasks)} 个房间)")

    async def stop_background_tasks(self):
        """停止所有房间的后台任务"""
        tasks = []
        for room in self.rooms_by_number.values():
            tasks.append(room.engine.manager.stop_background_tasks())

        if tasks:
            await asyncio.gather(*tasks)
        print(f"⏹️ 所有房间的后台任务已停止")
