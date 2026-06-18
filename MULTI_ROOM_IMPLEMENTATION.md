# TRPGWebDiscord 多房间功能实现方案

## 概述

本方案为 TRPGWebDiscord 项目添加多房间功能，允许在 Discord 的不同频道同时进行多个独立的游戏，每个房间的游戏状态完全隔离，多组玩家可同时进行游戏而互不影响。

## 核心改动

### 1. 多房间引擎管理器 (`multi_room_engine.py`) ✅
**文件**: `TRPGWebDiscord/backend/multi_room_engine.py`

创建了新的多房间管理系统：

**GameRoom 类** - 单个游戏房间：
- `room_id`: 房间唯一标识（Discord 频道 ID）
- `room_name`: 房间名称
- `engine`: 该房间的独立 GameEngine 实例
- `is_active`: 房间是否有活跃游戏
- `players`: 房间内的玩家集合

**MultiRoomEngine 类** - 多房间管理器：
- `create_room()` - 创建新房间
- `get_room()` / `get_or_create_room()` - 获取或创建房间
- `delete_room()` - 删除房间
- `get_active_rooms()` - 获取所有活跃房间
- `get_all_rooms_info()` - 获取所有房间信息
- 以及针对 Discord 命令和 Socket.io 事件的便捷方法

### 2. 服务器改进 (`server.py`) ✅
**文件**: `TRPGWebDiscord/backend/server.py`

**主要改动**：

1. **引入 MultiRoomEngine**
   ```python
   from multi_room_engine import MultiRoomEngine
   multi_room_engine = MultiRoomEngine(bot, sio)
   ```

2. **Discord 命令按房间隔离**
   - `!准备` - 在当前频道创建大厅
   - `!建议` - 向当前频道的房间添加建议
   - `!角色` - 向当前频道的房间添加角色
   - `!开始游戏` - 在当前频道启动游戏
   - `!重置` - 停止当前频道的游戏
   - `!查看记忆` - 查看当前频道房间的游戏记忆

3. **房间路由逻辑**
   ```python
   # 获取频道 ID
   room_id = ctx.channel.id

   # 路由到对应房间
   await multi_room_engine.start_lobby(room_id, ctx.channel)
   ```

4. **Socket.io Web 客户端支持**
   - 添加了 `web_client_room_mapping` 字典追踪每个客户端属于哪个房间
   - Web 客户端需要在 `set_nickname` 或 `join_room` 事件中提供 `room_id` 参数

### 3. 房间隔离机制

**关键特性**：

| 方面 | 说明 |
|------|------|
| **游戏状态隔离** | 每个房间有独立的 GameEngine 和 GameManager |
| **消息隔离** | 消息根据房间 ID 路由到对应的房间 |
| **后台任务** | 每个房间的后台任务独立运行 |
| **频道绑定** | 每个频道对应一个独立的房间 |

## 使用场景

### 场景 1: 多频道同时游戏

```
频道 #Game-Room-1:
  用户输入: !准备
  → 创建房间1，启动大厅
  用户输入: !开始游戏
  → 房间1启动游戏，房间1的状态完全隔离

频道 #Game-Room-2:
  用户输入: !准备
  → 创建房间2，启动大厅（完全独立）
  用户输入: !开始游戏
  → 房间2启动游戏，房间2状态与房间1完全隔离

结果: 两个房间的游戏互不影响，可同时进行
```

### 场景 2: Web 客户端多房间支持

前端在连接时需要提供 `room_id`：

```javascript
// Web 客户端连接时
socket.emit('set_nickname', {
    nickname: "玩家名称",
    room_id: 频道ID  // 关键：指定房间
});

// 或者 join_room 时
socket.emit('join_room', {
    room_id: 频道ID,
    web_room_id: 'public'
});
```

### 场景 3: 查看所有房间状态

创建一个新的 Discord 命令来查看所有活跃房间：

```python
@bot.command(name="房间列表")
async def list_all_rooms(ctx):
    rooms_info = multi_room_engine.get_all_rooms_info()

    msg = "**📊 所有活跃房间:\n**"
    for room_id, info in rooms_info.items():
        msg += f"\n🎮 {info['room_name']}\n"
        msg += f"   状态: {info['status']}\n"
        msg += f"   玩家: {info['players']}\n"
        msg += f"   场景: {info['scene']}\n"

    await ctx.send(msg)
```

## 架构图

```
server.py (主入口)
    ↓
MultiRoomEngine (多房间管理器)
    ├─ GameRoom (频道 #game-1)
    │   └─ GameEngine
    │       ├─ GameManager
    │       │   ├─ game_state (房间1的游戏状态)
    │       │   ├─ GameFlow
    │       │   └─ PlotManagement
    │       └─ room_state (房间1的房间状态)
    │
    ├─ GameRoom (频道 #game-2)
    │   └─ GameEngine
    │       ├─ GameManager
    │       │   ├─ game_state (房间2的游戏状态)
    │       │   ├─ GameFlow
    │       │   └─ PlotManagement
    │       └─ room_state (房间2的房间状态)
    │
    └─ ... 更多房间
```

## 关键改动点

### 1. 频道 ID 作为房间标识
```python
room_id = ctx.channel.id  # 使用频道ID作为房间ID
room = multi_room_engine.get_or_create_room(room_id, channel_name)
```

### 2. 后台任务管理
```python
# 启动所有房间的后台任务
await multi_room_engine.start_background_tasks()

# 停止所有房间的后台任务
await multi_room_engine.stop_background_tasks()
```

### 3. Web 客户端需要指定房间
```python
# Socket.io 事件中需要包含 room_id
data = {
    "room_id": channel_id,  # 必须！
    "content": "消息内容"
}
```

## 迁移检查清单

- [ ] 导入了 `MultiRoomEngine`
- [ ] 创建了 `multi_room_engine` 实例
- [ ] 所有 Discord 命令都使用 `room_id = ctx.channel.id`
- [ ] 所有命令都调用 `multi_room_engine.方法()` 而不是 `game_engine.方法()`
- [ ] Web 前端已更新: 发送事件时包含 `room_id` 参数
- [ ] 测试: 在两个频道同时运行游戏

## 后续可选功能

1. **房间清理**: 自动删除空闲房间
2. **房间持久化**: 保存房间状态到数据库
3. **房间访问控制**: 限制谁可以查看/加入房间
4. **房间统计**: 显示活跃房间数、总玩家数等
5. **跨房间赛事**: 多个房间间的联动内容

## 常见问题

### Q: 如何在频道间切换游戏？
A: 每个频道是独立的房间。在不同频道执行 `!准备` 会创建不同的游戏房间。

### Q: 旧代码能否继续使用？
A: 可以。旧的 `GameEngine` 实例仍然存在为 `game_engine`，但建议全部迁移到多房间系统。

### Q: Web 客户端如何知道房间 ID？
A: 需要前端提供。可以从 URL 参数、用户选择或 Discord 频道 ID 中获取。

### Q: 多房间会增加内存占用吗？
A: 是的。每个房间都有独立的 GameEngine 和 GameManager。建议监控内存使用情况。

## 调试提示

启用调试日志查看房间操作：
```python
print(f"[MultiRoom] 创建房间: {room_name} (ID: {room_id})")
print(f"[MultiRoom] 活跃房间数: {multi_room_engine.get_active_room_count()}")
print(f"[MultiRoom] 房间信息: {multi_room_engine.get_all_rooms_info()}")
```
