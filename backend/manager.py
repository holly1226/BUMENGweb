"""
游戏管理器核心模块
负责整合各个子模块，提供统一的游戏管理接口
"""
import time
import random


class GameManager:
    """游戏管理器：负责整合各个子模块，统一管理游戏状态"""

    def __init__(self, engine):
        self.engine = engine
        self.last_action_time = time.time()
        self.is_running = True
        self.background_task = None

        # 消息缓冲机制
        self.pending_messages = []  # 待处理的玩家消息列表
        self.batch_processing_task = None
        self.batch_delay = 3.0  # 3秒延迟

        # 游戏内容状态（Manager 管理的游戏内数据）
        self.init_game_state()

        # 初始化子模块
        from game_flow import GameFlow
        from plot_management import PlotManagement
        self.game_flow = GameFlow(self)
        self.plot_management = PlotManagement(self)

    def init_game_state(self):
        """初始化游戏"""
        self.game_state = {
            "round": 0,
            "scene": "未开始",          # 当前故事场景（森林、地牢等）
            "suggestions": [],          # 玩家建议
            "role_prefs" : {},          #玩家身份
            "players": {},               # 玩家数据
            "inventory": [],            # 道具
            "chat_history": [],          # 最近对话
            "long_term_memory": {},     # 长期记忆
            "plot_inspection": {},       # 用一个深度模型初始化剧情的长期走向，剧情监控
            "player_mapping": {},     # 玩家的discord名称与扮演的角色
            "total_rounds": 15
        }

    # === 后台任务管理 ===
    async def start_background_tasks(self):
        """启动后台监控"""
        await self.game_flow.start_background_tasks()

    async def stop_background_tasks(self):
        """停止后台监控"""
        await self.game_flow.stop_background_tasks()

    # === 游戏流程管理 ===
    async def start_lobby(self):
        """开启征集阶段"""
        await self.game_flow.start_lobby()

    async def start_game(self, prefs_str, role_str, player_count):
        """一站式生成：逻辑、Prompt、私信、存库全部集成"""
        await self.game_flow.start_game(prefs_str, role_str, player_count)

    async def reset_game(self):
        """重置游戏"""
        await self.game_flow.reset_game()

    # === 玩家输入处理 ===
    async def handle_player_input(self, content, player_name, channel=None, no_action=False, bypass_batch=False):
        """处理玩家输入"""
        await self.game_flow.handle_player_input(content, player_name, channel, no_action, bypass_batch)

    async def check_new_round(self, content, player_name):
        """检查是否需要切换轮次"""
        return await self.game_flow.check_new_round(content, player_name)

    # === AI响应处理 ===
    async def _process_ai_response(self, response, action):
        """处理AI返回的响应和指令"""
        if action:
            await self._execute_ai_action(action)

        # 发送AI回应到Discord
        await self.engine.send_to_public(f"**DM:** {response}", tts=True, speaker="DM-bot")

    async def _execute_ai_action(self, action):
        """执行AI指令"""
        if not action: return

        # 1. 兼容性检查：如果 AI 直接返回了剧情大纲，立即保存
        if "plot_inspection" in action:
            self.game_state["plot_inspection"] = action["plot_inspection"]
            print("📖 [Manager] 剧情大纲已同步")

        if "scene" in action:
            self.game_state["scene"] = action["scene"]

        action_type = action.get("type")
        params = action.get("params", {})

        if action_type == "change_scene":
            scene_name = params.get("name")
            scene_desc = params.get("description", "")
            # 记录当前场景信息（供回合变更时使用）
            self.game_state["scene"] = scene_name
            self.game_state["scene_description"] = scene_desc
            await self.engine.update_scene(
                scene_name,
                scene_desc
            )

        elif action_type == "add_item":
            await self.engine.add_inventory_item(
                params.get("item_name"),
                params.get("detail")
            )

            self.game_state["scene"] = params.get("name")

        elif action_type == "roll_dice":
            print(f"🎲 [Dice] 收到骰子指令，params: {params}")
            result = random.randint(0, 10)    # 十面骰
            reason=params.get("reason", "未知判定")
            difficulty = params.get("difficulty", 5)
            success = result >= difficulty

            if success:
                result_str=f"{reason}\n **成功** 骰子结果：掷出{result}>=难度{difficulty}"
            else:
                result_str=f"{reason}\n **失败** 骰子结果：掷出{result}<难度{difficulty}"

            print(f"🎲 [Dice] 判定结果: {result_str}", flush=True)
            await self.engine.send_to_public(result_str, tts=True, speaker="roll-dice")
            # await self.handle_player_input(content=result_str, player_name="roll_dice", no_action=True)
            await self.engine.trigger_dice_roll(result, success, reason)
            print(f"🎲 [Dice] 骰子处理完成", flush=True)

        elif action_type == "start_vote":
            # 投票功能
            title = params.get("title", "投票")
            options = params.get("options", [])
            target_channel = self.engine.main_channel if self.engine.main_channel else self.engine.current_channel

            if target_channel and options:
                await self.engine.send_ai_vote(target_channel, title, options)

        # === 剧本模式专属指令 ===
        elif action_type == "update_festival_node":
            node_id = params.get("node_id", "")
            reason = params.get("reason", "")
            if node_id:
                old_node = self.game_state.get("festival_current_node", "")
                self.game_state["festival_current_node"] = node_id
                if old_node and old_node != node_id:
                    history = self.game_state.get("festival_node_history", [])
                    history.append(old_node)
                    self.game_state["festival_node_history"] = history
                print(f"🔄 [Festival] 剧情节点切换: {old_node} → {node_id} ({reason})")

        elif action_type == "update_attribute":
            char_name = params.get("character", "林墨")
            attr_name = params.get("attr_name", "")
            delta = params.get("delta", 0)
            if char_name and attr_name:
                attrs = self.game_state.get("character_attributes", {})
                char_attrs = attrs.get(char_name, {})
                old_val = char_attrs.get(attr_name, 0)
                new_val = max(0, min(10, old_val + delta))  # 限制 0-10
                char_attrs[attr_name] = new_val
                attrs[char_name] = char_attrs
                self.game_state["character_attributes"] = attrs
                print(f"📊 [Festival] {char_name}.{attr_name}: {old_val} → {new_val} ({delta:+d})")

        elif action_type == "festival_check":
            check_id = params.get("check_id", "")
            description = params.get("description", "未知检定")
            # 从 mechanics_checks 中查找匹配的检定
            checks = self.game_state.get("plot_inspection", {}).get("mechanics_checks", [])
            check_def = None
            for c in checks:
                if c.get("id") == check_id:
                    check_def = c
                    break
            if check_def:
                difficulty = check_def.get("difficulty", 5)
                target_attr = check_def.get("checkTarget", "洞察值")
                desc = check_def.get("description", "randint(0, 检定对象)>=难度 则成功")
                success_effect = check_def.get("successEffect", "成功")
                failure_effect = check_def.get("failureEffect", "失败")

                # 获取当前属性值
                char_attrs = self.game_state.get("character_attributes", {}).get("林墨", {})
                attr_value = char_attrs.get(target_attr.strip(), 0)

                # 根据检定描述判断判定方式
                if ">=" in desc:
                    result = random.randint(0, attr_value)
                    success = result >= difficulty
                elif "<=" in desc:
                    result = random.randint(0, attr_value)
                    success = result <= difficulty
                else:
                    result = random.randint(0, max(1, attr_value))
                    success = result >= difficulty

                result_str = (
                    f"🎲 **检定：【{check_def.get('name', description)}】**\n"
                    f"📊 检定属性: {target_attr.strip()}={attr_value} | 难度: {difficulty}\n"
                    f"🎯 掷骰结果: {result} → {'✅ 成功' if success else '❌ 失败'}\n"
                    f"📖 {'成功效果: ' + success_effect if success else '失败效果: ' + failure_effect}"
                )
                await self.engine.send_to_public(result_str, tts=True, speaker="roll-dice")
                await self.engine.trigger_dice_roll(result, success, description)
                print(f"🎲 [Festival Check] {check_def.get('name')}: 掷{result}, {'成功' if success else '失败'}")
            else:
                print(f"⚠️ [Festival Check] 未找到检定: {check_id}")

    # === 上下文构建 ===
    def _build_context(self):
        """构建对话上下文"""
        context = {
            "recent_chat": self.game_state["chat_history"][-10:],  # 最近10条对话
            "inventory": self.game_state["inventory"],
            "current_scene": self.game_state["scene"]
        }
        return context

    # === 对话记录 ===
    def build_chat_entry(self, content, player_name, channel=None):
        """
        构建聊天记录条目
        
        Args:
            content (str): 聊天内容文本
            player_name (str): 发送消息的玩家名称
            channel (str, optional): 频道ID，默认为当前频道
        
        Returns:
            dict: 包含聊天记录的字典，包含以下键：
                - player: 玩家名称
                - content: 消息内容
                - timestamp: 时间戳(HH-MM-SS格式)
                - round: 当前游戏轮次
                - channel: 频道ID
        """
        chat_entry = {
            "player": player_name,
            "content": content,
            "timestamp": time.strftime("%H-%M-%S"),
            "round": self.game_state["round"],
            "channel": channel if channel else self.engine.current_channel.id
        }
        return chat_entry