# TRPGWebDiscord 房间选择系统 - 完成总结

## ✅ 已实现的功能

### 1️⃣ 数字房间号系统
- 每个房间自动获得一个**6位数字房间号**
- 房间号全局唯一，系统自动生成
- 支持通过房间号查找和加入房间

### 2️⃣ 交互菜单界面
用户输入 `!准备` 时会看到：
```
🎮 **欢迎来玩 TRPG 游戏！**

请选择您的操作：
• 创建房间 - 创建一个新的游戏房间（您会得到一个6位房间号）
• 加入房间 - 输入房间号加入现有房间

[🎮 创建房间]  [🔓 加入房间]
```

### 3️⃣ 创建房间功能
点击 **[🎮 创建房间]** 按钮：
```
✅ 房间创建成功！

🎯 房间号: 234567
📍 频道: #game-room-1

请告诉其他玩家房间号，他们可以使用 !准备 然后选择 "加入房间" 来加入！
```

### 4️⃣ 加入房间功能
点击 **[🔓 加入房间]** 按钮：
- 弹出对话框让用户输入房间号
- 系统验证房间号是否存在
- 如果存在，自动加入房间
- 如果不存在，显示错误提示

**房间不存在时**：
```
❌ 房间号不存在！

您输入的房间号是: 999999

请检查房间号是否正确。
```

### 5️⃣ 房间列表命令
新增 `!房间列表` 命令查看所有活跃房间：
```
🏢 所有活跃房间

🎯 房间号: `234567`
状态: 🟢 进行中
玩家: 3
频道: #game-room-1
场景: 黑暗森林

🎯 房间号: `345678`
状态: 🔴 等待中
玩家: 2
频道: #game-room-2
场景: 酒馆大厅
```

## 📁 修改的文件

### 1. `multi_room_engine.py` - 完全重写
**关键改动**：
- 添加**房间号管理系统**
- `generate_room_number()` - 生成唯一的6位房间号
- `get_room_by_number()` - 通过房间号查询
- `get_room_by_channel()` - 通过频道ID查询
- `room_exists()` - 验证房间号是否存在

**新增属性**：
```python
self.rooms_by_number: Dict[str, GameRoom]      # 按房间号索引
self.rooms_by_channel: Dict[int, GameRoom]     # 按频道ID索引
self.channel_to_room_number: Dict[int, str]    # 频道到房间号映射
```

### 2. `server.py` - 大量修改
**新增导入**：
```python
from discord.ui import Button, View, Modal, TextInput
```

**新增类**：
- `JoinRoomModal` - 加入房间的对话框
- `RoomSelectionView` - 创建/加入房间的菜单

**修改的方法**：
- `on_message()` - 使用 `get_room_by_channel()`
- `!准备` 命令 - 显示交互菜单
- `!建议`、`!角色`、`!开始游戏` - 添加房间验证
- Socket.io 处理器 - 使用 `channel_id` 而不是 `room_id`

**新增命令**：
- `!房间列表` - 显示所有活跃房间

## 🎮 使用流程完整示例

### 场景：两个朋友要玩游戏

#### 朋友1（创建房间）
```
1. 在 #game-room-1 输入: !准备
   ↓
2. 看到菜单，点击: [🎮 创建房间]
   ↓
3. 获得房间号: 234567
   ↓
4. 告诉朋友2: "房间号是 234567"
   ↓
5. 等待朋友2加入
   ↓
6. 输入: !建议 科幻冒险
   ↓
7. 输入: !角色 女侠客
   ↓
8. 输入: !开始游戏
   ↓
9. 游戏开始！
```

#### 朋友2（加入房间）
```
1. 在 #game-room-2 输入: !准备
   ↓
2. 看到菜单，点击: [🔓 加入房间]
   ↓
3. 看到对话框，输入房间号: 234567
   ↓
4. 系统验证房间存在
   ↓
5. 自动加入朋友1的房间 #game-room-1
   ↓
6. 看到游戏大厅和朋友1的信息
   ↓
7. 输入: !建议 克苏鲁元素
   ↓
8. 输入: !角色 男侦探
   ↓
9. 等待朋友1 !开始游戏
   ↓
10. 游戏开始！
```

## 🔑 关键开发点

### 房间号生成算法
```python
def generate_room_number(self) -> str:
    """生成唯一的6位房间号"""
    while True:
        room_number = f"{random.randint(100000, 999999)}"
        if room_number not in self.rooms_by_number:
            return room_number
```

### 房间验证
```python
def room_exists(self, room_number: str) -> bool:
    """检查房间号是否存在"""
    return room_number in self.rooms_by_number
```

### 交互菜单实现
```python
class RoomSelectionView(View):
    @discord.ui.button(label="🎮 创建房间", style=discord.ButtonStyle.primary)
    async def create_room(self, interaction, button):
        # 创建房间、生成房间号、启动大厅

    @discord.ui.button(label="🔓 加入房间", style=discord.ButtonStyle.secondary)
    async def join_room(self, interaction, button):
        # 显示模态框让用户输入房间号
```

### 房间号验证
```python
class JoinRoomModal(Modal):
    async def on_submit(self, interaction: discord.Interaction):
        room_num = self.room_number.value.strip()

        if not multi_room_engine.room_exists(room_num):
            await interaction.response.send_message("❌ 房间号不存在！", ephemeral=True)
            return

        # 房间存在，加入房间
```

## 📋 命令总结

| 命令 | 说明 |
|------|------|
| `!准备` | 显示房间选择菜单（创建/加入房间） |
| `!房间列表` | 查看所有活跃房间及其房间号 |
| `!建议 [内容]` | 提交世界观建议 |
| `!角色 [性别/性格]` | 提交角色要求 |
| `!开始游戏` | 启动游戏 |
| `!重置` | 重置游戏状态 |
| `!查看记忆` | 查看游戏历史记录 |

## 🚀 部署和测试

### 启动服务器
```bash
cd TRPGWebDiscord/backend
python server.py
```

### 测试创建房间
```
1. 在任意文本频道输入: !准备
2. 点击: [🎮 创建房间]
3. 应该看到房间号 (例如: 234567)
4. 检查该频道有没有出现大厅公告
```

### 测试加入房间
```
1. 在另一个频道输入: !准备
2. 点击: [🔓 加入房间]
3. 输入房间号: 234567
4. 应该成功加入房间
5. 能看到房间的游戏信息
```

### 测试错误处理
```
1. 输入: !准备 然后 [🔓 加入房间]
2. 输入错误的房间号: 999999
3. 应该看到错误提示: "房间号不存在"
```

## 💾 数据结构

### GameRoom 对象
```python
room.room_number      # "234567"
room.channel_id       # 12345678901234567
room.room_name        # "game-room-1"
room.engine           # GameEngine instance
room.is_active        # False / True
room.players          # {user_id1, user_id2, ...}
```

### MultiRoomEngine 索引
```python
# 按房间号查询
rooms_by_number = {
    "234567": GameRoom(...),
    "345678": GameRoom(...),
}

# 按频道ID查询
rooms_by_channel = {
    123456789: GameRoom(...),
    987654321: GameRoom(...),
}

# 频道到房间号映射
channel_to_room_number = {
    123456789: "234567",
    987654321: "345678",
}
```

## ⚠️ 注意事项

1. **房间号不会永久保存** - Bot重启后房间消失
   - 如需持久化，需要添加数据库支持

2. **6位数字房间号** - 最多支持900,000个并发房间
   - 对于大多数用途足够了

3. **频道删除** - 如果频道被删除，房间会变得无法访问
   - 系统会给出错误提示

4. **Web 客户端** - 需要使用 `channel_id` 而不是 `room_id`
   - Socket.io 事件中提供 `channel_id` 参数

## 🔧 后续可能的改进

- [ ] 添加数据库持久化房间状态
- [ ] 实现房间自动清理（删除24小时未活动的房间）
- [ ] 添加房间密码保护
- [ ] 实现房间访问权限控制
- [ ] 添加房间最大人数限制
- [ ] 房间搜索功能（按名称/描述搜索）

## 📞 支援

如有问题，请检查：
1. 是否输入了完整的6位房间号
2. 房间号是否仍然存在（使用 `!房间列表` 验证）
3. Bot 是否还在运行
4. 频道是否被删除

---

**🎊 房间选择系统实现完成！** 现在所有玩家都可以轻松创建和加入游戏房间了！
