# TRPGWebDiscord 多房间实现总结

## ✅ 已完成的改动

### 1. 创建了 MultiRoomEngine
**文件**: `backend/multi_room_engine.py`

- GameRoom 类：代表单个游戏房间
- MultiRoomEngine 类：管理所有房间的生命周期
- 每个房间都有独立的 GameEngine 实例

### 2. 修改了服务器
**文件**: `backend/server.py`

**Discord 命令隔离**：
```python
room_id = ctx.channel.id  # 获取频道 ID 作为房间标识
await multi_room_engine.start_lobby(room_id, ctx.channel)
```

**消息路由**：
```python
room = multi_room_engine.get_room(room_id)
if room:
    await room.engine.handle_player_input(...)
```

**Socket.io Web 客户端支持**：
```python
web_client_room_mapping = {}  # 追踪客户端属于哪个房间

# Web 客户端需要在事件中提供 room_id
socket.emit('set_nickname', { room_id: channel_id, ... })
```

## 🎯 核心工作原理

```
1. 用户在 #Game-Room-1 执行 !准备
   ↓
2. 获取频道 ID: room_id = 123456
   ↓
3. MultiRoomEngine 创建 GameRoom(123456)
   ↓
4. GameRoom 包含独立的 GameEngine 实例
   ↓
5. 该房间的所有操作都在这个独立的 GameEngine 中进行
   ↓
6. 同时，#Game-Room-2 的操作完全独立运行
```

## 🔑 关键特性

| 特性 | 说明 |
|------|------|
| **房间隔离** | 每个频道 = 一个房间，完全独立 |
| **自动创建** | 首次使用时自动创建房间 |
| **独立状态** | 每个房间有独立的游戏状态和管理器 |
| **并发支持** | 无限数量的并发房间 |
| **Web 客户端** | 需要提供 `room_id` 参数参与 |

## 📋 使用清单

### 对于 Discord 用户
```
在频道 #game-1:
  !准备          → 创建游戏大厅
  !建议 ...      → 提交世界观建议
  !角色 ...      → 提交角色要求
  !开始游戏      → 启动游戏

在频道 #game-2:
  !准备          → 创建独立的大厅（不受 #game-1 影响！）
  ...            → 其他命令
```

### 对于前端（Web 客户端）开发者
```javascript
// 1. 连接时提供 room_id
socket.emit('set_nickname', {
    nickname: 'My Nickname',
    room_id: channelId  // 关键！
});

// 2. 接收房间特定的事件
socket.on('stage_change', (data) => {
    // 更新 UI 为该房间的场景
});

// 3. 发送消息时也需要 room_id（在 set_nickname 时已关联）
socket.emit('send_message', {
    content: 'Hello',
    room: 'public'  // 房间已通过之前的 set_nickname 关联
});
```

## ⚡ 快速开始

1. **运行服务器**
   ```bash
   cd TRPGWebDiscord/backend
   python server.py
   ```

2. **创建两个测试频道**
   - 创建 Discord 频道 `#test-room-1`
   - 创建 Discord 频道 `#test-room-2`

3. **同时在两个频道运行游戏**
   ```
   #test-room-1:
   > !准备
   > 任意玩家: !建议 科幻冒险
   > 任意玩家: !角色 女侠客
   > 任意玩家: !开始游戏

   #test-room-2:
   > !准备
   > 任意玩家: !建议 恐怖怪诞
   > 任意玩家: !角色 男侦探
   > 任意玩家: !开始游戏
   ```

4. **验证隔离**
   - 两个房间应该互不干扰
   - 各自有独立的游戏状态和进度

## 🔧 常见问题

### Q: 为什么我的命令在另一个频道不工作？
A: 这是正常的！每个频道是独立的房间。在那个频道也执行一遍命令即可。

### Q: 多个房间会占用很多资源吗？
A: 是的。每个房间都有独立的 GameEngine 和 GameManager。建议：
- 监控内存使用情况
- 定期清理空闲房间（可添加自动清理功能）

### Q: 如何查看所有活跃房间？
A: 在代码中执行：
```python
rooms_info = multi_room_engine.get_all_rooms_info()
print(rooms_info)
```

或添加一个 Discord 命令：
```python
@bot.command(name="房间")
async def list_rooms(ctx):
    info = multi_room_engine.get_all_rooms_info()
    msg = 'f"**活跃房间: {len(info)} 个**\n"'
    for room_id, data in info.items():
        msg += f"\n📍 {data['room_name']}: {data['status']}"
    await ctx.send(msg)
```

### Q: Web 客户端如何知道 room_id？
A: 您需要在前端处理这个问题，可能的方案：
1. 从 URL 参数获取
2. 让用户选择频道
3. 从 Discord 集成中获取当前频道 ID

## 📊 架构对比

### 改动前（单房间）
```
server.py
  ↓
GameEngine (全局) ← 所有房间共享
  ↓
GameManager (全局) ← 所有房间共享
  ↓
game_state (单一)
```

### 改动后（多房间）
```
server.py
  ↓
MultiRoomEngine
  ├─ GameRoom #1
  │   └─ GameEngine ← 独立
  │       └─ GameManager ← 独立
  │           └─ game_state (房间1)
  │
  ├─ GameRoom #2
  │   └─ GameEngine ← 独立
  │       └─ GameManager ← 独立
  │           └─ game_state (房间2)
  │
  └─ ...
```

## 🚀 后续优化建议

1. **自动房间清理**
   ```python
   # 清理 24 小时没有活动的房间
   async def cleanup_idle_rooms(self):
       current_time = time.time()
       for room_id, room in list(self.rooms.items()):
           if current_time - room.created_at > 86400:
               self.delete_room(room_id)
   ```

2. **房间持久化**
   - 将房间状态保存到数据库
   - 程序重启后恢复房间

3. **房间访问控制**
   - 只允许频道成员访问该房间
   - 添加房间密码保护

4. **监控和统计**
   - 显示活跃房间数
   - 显示总玩家数
   - 显示运行时间

## ✨ 验证清单

- [x] MultiRoomEngine 创建完成
- [x] server.py 已更新使用多房间引擎
- [x] Discord 命令按房间隔离
- [x] Socket.io 支持多房间
- [ ] 前端 Web 客户端已更新（需要您的前端确认）
- [ ] 已在两个频道同时测试
- [ ] 内存使用正常
- [ ] 没有状态污染

## 📝 测试命令

```bash
# 专用日志输出
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from backend.server import multi_room_engine
print(f'房间数: {multi_room_engine.get_room_count()}')
print(f'活跃房间: {multi_room_engine.get_active_room_count()}')
print(f'房间信息: {multi_room_engine.get_all_rooms_info()}')
"
```

## 🎊 完成！

现在 TRPGWebDiscord 支持完整的多房间功能，可以在 Discord 的多个频道同时运行独立的游戏！
