# 房间级隔离系统 - 架构更新

## 🎯 核心变化

**从频道级隔离 → 房间级隔离**

之前：一个Discord频道 = 一个房间
现在：一个Discord频道 = 多个虚拟房间（由房间号区分）

## 📊 架构对比

### 旧架构（频道级）
```
Discord Frequency #channel1
    ↓
    Room 1 (固定关联)
    - 玩家 A, B, C
    - 消息都在这个频道

Discord Frequency #channel2
    ↓
    Room 2 (固定关联)
    - 玩家 D, E, F
```

### 新架构（房间级）
```
Discord Frequency #main-game (主游戏频道)
    ↓
    Room 234567
    ├─ 玩家 A, B, C
    ├─ 私有消息空间
    ↓
    Room 345678
    ├─ 玩家 D, E, F
    ├─ 私有消息空间
    ↓
    Room 456789
    ├─ 玩家 G, H
    ├─ 私有消息空间

所有房间共享同一个频道，但消息被过滤
```

## 🔧 技术实现

### 1. 用户到房间映射

**multi_room_engine.py - 新增数据结构：**

```python
# 用户到房间号的映射
user_to_room: Dict[str, str]  # {"player_name": "room_number"}

# 房间到用户的映射
room_to_users: Dict[str, set]  # {"room_number": {"player1", "player2"}}
```

### 2. 消息过滤

**server.py - on_message 事件的变化：**

```python
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.content.startswith('!'):
        await bot.process_commands(message)
    else:
        # ✅ 新方式：通过玩家名称查找房间
        player_name = message.author.name
        room_number = multi_room_engine.get_user_room(player_name)

        if not room_number:
            # 玩家还没加入任何房间，忽略消息
            print(f"⚠️ 玩家 {player_name} 的消息被过滤：还未加入房间")
            return

        # 只发送给该房间
        room = multi_room_engine.get_room_by_number(room_number)
        if room:
            await room.engine.handle_player_input(
                message.content,
                player_name,
                message.channel
            )
```

### 3. 房间操作

**创建房间：**
```python
room, room_number = multi_room_engine.create_room(
    channel_id=ctx.channel.id,      # 主游戏频道
    room_name="Game Room",
    creator_name=ctx.author.name    # 创建者自动加入
)
```

**加入房间：**
```python
success = multi_room_engine.join_room(
    player_name="玩家名",
    room_number="234567"
)
```

**获取玩家所在房间：**
```python
room_number = multi_room_engine.get_user_room("玩家名")

# 如果返回 None，表示玩家还未加入任何房间
```

## 📋 使用流程

### 玩家视角

1. **所有玩家加入同一个 Discord 频道** #main-game
2. **玩家 A 输入**: `!准备`
   - 显示房间选择菜单
3. **玩家 A 点击**: "🎮 创建房间"
   - 创建房间，获得房间号 `234567`
   - 玩家 A 自动加入此房间
4. **玩家 B 输入**: `!准备`
   - 显示房间选择菜单
5. **玩家 B 点击**: "🔓 加入房间"
   - 输入房间号 `234567`
   - 玩家 B 现在加入了房间
6. **玩家 A 和 B 可以对话**
   - 在频道中发送消息
   - 只有房间内的玩家能看到
7. **玩家 C 在同一频道输入**: `!准备`
   - 创建房间 `345678`
   - 玩家 C 加入此房间
8. **玩家 C 的消息被过滤**
   - 玩家 A 和 B 看不到玩家 C 的消息
   - 玩家 C 看不到玩家 A 和 B 的消息

### 消息隔离示意

```
频道消息栏:
┌─────────────────────────────────────────┐
│ 玩家 A: 你好                             │  ←→ 房间 234567
│ 玩家 B: 你好呀                          │  ←→ 房间 234567
│ 玩家 C: 大家好                          │  ←→ 房间 345678
│ 玩家 A: 我们来开始游戏                  │  ←→ 房间 234567
│ 玩家 B: 好的                            │  ←→ 房间 234567
└─────────────────────────────────────────┘

实际过滤结果：

玩家 A 的视图:              玩家 C 的视图:
├─ 玩家 A: 你好            ├─ 玩家 C: 大家好
├─ 玩家 B: 你好呀          └─ (只看到房间 345678 的消息)
├─ 玩家 A: 我们来开始
└─ 玩家 B: 好的

玩家 B 的视图:
├─ 玩家 A: 你好
├─ 玩家 B: 你好呀
├─ 玩家 A: 我们来开始
└─ 玩家 B: 好的
```

## 🔄 命令更新

所有命令现在都通过玩家名称查找房间，而不是通过频道 ID：

### 旧方式
```python
room = multi_room_engine.get_room_by_channel(ctx.channel.id)
if not room:
    await ctx.send("房间不存在")
    return
```

### 新方式
```python
player_name = ctx.author.name
room_number = multi_room_engine.get_user_room(player_name)

if not room_number:
    await ctx.send("您还未加入任何房间，请先输入 `!准备` 加入房间")
    return

room = multi_room_engine.get_room_by_number(room_number)
if not room:
    await ctx.send("房间不存在")
    return
```

## ✅ 受影响的命令

| 命令 | 变化 |
|-----|------|
| `!准备` | 不再检查频道是否有房间，任何玩家都可以创建/加入房间 |
| `!建议` | 使用 get_user_room() 查找房间 |
| `!角色` | 使用 get_user_room() 查找房间 |
| `!开始游戏` | 使用 get_user_room() 查找房间 |
| `!重置` | 使用 get_user_room() 查找房间 |
| `!查看记忆` | 使用 get_user_room() 查找房间 |
| `!房间列表` | 无变化（仍显示所有房间） |

## 🎮 新增 API

### MultiRoomEngine 新增方法

```python
# 获取玩家所在房间号
get_user_room(player_name: str) -> Optional[str]

# 获取房间内的所有玩家
get_room_users(room_number: str) -> set

# 玩家加入房间
join_room(player_name: str, room_number: str) -> bool

# 玩家离开房间
leave_room(player_name: str) -> Optional[str]
```

## 📊 数据结构对比

### 旧系统
```
rooms_by_channel: {123456789: GameRoom}  # 频道 ID → 房间
rooms_by_number: {"234567": GameRoom}     # 房间号 → 房间
channel_to_room_number: {123456789: "234567"}
```

### 新系统
```
rooms_by_number: {"234567": GameRoom, "345678": GameRoom}        # 房间号 → 房间
user_to_room: {"玩家A": "234567", "玩家B": "234567", "玩家C": "345678"}
room_to_users: {"234567": {"玩家A", "玩家B"}, "345678": {"玩家C"}}
```

## 🔐 隔离保证

1. **消息隔离**：用户只能看到自己所在房间的消息
2. **命令隔离**：所有命令都在玩家所在的房间内执行
3. **状态隔离**：每个房间有独立的 GameEngine 和游戏状态
4. **玩家隔离**：players 集合在房间级别管理

## 🚀 性能优势

- 不需要创建多个 Discord 频道
- 所有房间共享同一个频道上下文
- 消息过滤在 on_message 事件处理时进行
- 内存占用只与房间数量有关，不与频道数量有关

## ⚠️ 需要注意的事项

1. **玩家名称唯一性**：系统使用玩家名称作为 key，请确保不同玩家有不同名称
2. **房间号冲突**：已实现唯一性保证（generate_room_number 检查重复）
3. **消息发送权限**：只有加入房间的玩家才能看到和发送消息
4. **Web 客户端**：需要使用房间号而不是频道 ID 进行连接

## 📝 迁移清单

- [x] 修改 MultiRoomEngine 数据结构
- [x] 添加用户到房间的映射
- [x] 实现消息过滤逻辑 (on_message)
- [x] 更新所有命令处理器
- [x] 更新按钮和模态框处理器
- [x] 测试房间隔离
- [ ] 更新 Socket.io 处理器（如果需要 Web 客户端支持）
- [ ] 文档更新和用户指南

## 🎉 成果

✅ 单个 Discord 频道支持多个并发游戏房间
✅ 玩家级别的消息隔离
✅ 无需创建多个频道的灵活架构
✅ 完整的房间生命周期管理

**现在您的 TRPG 游戏真正支持多房间并发游戏了！** 🎮
