"""
游戏流程管理模块
负责游戏的初始化、玩家输入处理、轮次管理等流程控制
"""
import asyncio
import os
import time
import json
from ai_handler import ask_qwen_async
import prompts
from plot_management import PlotManagement

class GameFlow:
    """游戏流程管理器"""

    def __init__(self, manager):
        self.manager = manager
        self.engine = manager.engine

    # === 游戏流程管理 ===
    async def start_lobby(self):
        """开启征集阶段"""
        # 重置游戏流程状态
        self.engine.room_state["status"] = "LOBBY"
        self.engine.room_state["_dm_msg_count"] = 0  # 重置DM消息计数
        self.engine.room_state["_self_intro_done"] = []  # 重置自我介绍状态

        # 重置游戏内容状态
        self.manager.game_state["scene"] = "灵感征集大厅"

        # 更新网页场景
        await self.engine.update_scene(
            "灵感征集大厅",
            "类似2000年前后的游戏厅，几个面容模糊的玩家聚在一个巨大的镜子前，正在讨论着什么",
        )

        await self.engine.sio.emit('stage_change', {
            "to": "LOBBY"

        })
        print("💡 [Manager] Lobby 状态初始化完成")

    async def start_game(self, prefs_str, role_str, player_count):
        """一站式生成：逻辑、Prompt、私信、存库全部集成"""
        self.manager.game_state["player_count"] = player_count

        # 保存玩家建议供后续语义搜索使用
        suggestions = []
        role_prefs = {}

        # 解析世界观建议 (支持逗号或换行符分隔)
        if prefs_str:
            lines = prefs_str.replace('\n', ',').split(',')
            for item in lines:
                item = item.strip()
                if not item:
                    continue
                if ":" in item:
                    suggestions.append(item.split(":", 1)[1].strip())
                else:
                    suggestions.append(item)

        # 解析角色偏好 (支持逗号或换行符分隔)
        if role_str:
            lines = role_str.replace('\n', ',').split(',')
            for item in lines:
                item = item.strip()
                if ":" in item:
                    parts = item.split(":", 1)
                    player_name = parts[0].strip()
                    preference = parts[1].strip()
                    if player_name and preference:
                        role_prefs[player_name] = preference

        self.manager.game_state["suggestions"] = suggestions
        self.manager.game_state["role_prefs"] = role_prefs

        total_rounds = self.manager.game_state.get("total_rounds", 20)

        # 1. 提示用户正在生成（不发TTS，纯文本提示）
        await self.engine.send_to_public("🎲 **DM 正在接入脑机接口，构建世界中...**", tts=False, speaker="DM-bot")

        # 2. 直接在 Manager 内部定义完整的 Prompt
        combined_prompt = f"""
            # Role
            你是一名顶级的角色扮演游戏主持人，擅长构建沉浸感极强的世界。

            # Task
            根据以下信息，为 {player_count} 位玩家生成开场剧情和专属角色卡：
            - 世界观风格：{prefs_str}
            - 玩家角色倾向：{role_str}
            - 本局游戏共{total_rounds}个回合，请据此设计故事节奏

            # Procedure
            1. 请思考如何构建一个能够满足用户的世界观风格，并为每个用户设置一个满足其角色倾向的方案，将你的分析过程写在analysis位置
            2. 请在plot_round_description写出对于剧情基本内容的简要概括，300字以内，作为DM的私密信息。
            3. 请在time_space中写明当前玩家所处的时代、地点，一句话简短说明即可。
            3. 并在public_story位置生成一个 200 字左右的开场剧情，注意不要透露任何有关结局的秘密。
            4. 请为每个玩家生成一个专属角色，用list[dict]的形式写在player_mapping位置，注明其原本的用户名（player_id）、在故事中的身份（character_name）和该角色的基本身份信息，给出一句话的角色介绍。**重要：每个玩家的角色身份必须互不相同（不同的character_name、不同的身份/职业/背景），禁止两个玩家扮演相同或相似的角色。**
            5. 请为这局游戏起一个名字，不超过8个字，并写在title位置。

            # Output Format (必须严格按照以下 JSON 格式回复)
            {{
                "analysis": str,
                "scene": "当前场景名称",
                "plot_round_description": "对于剧情基本内容的简要概括",
                "time_space", "当前玩家所处的时代、地点",
                "public_story": "发在公屏的 300 字左右的世界观介绍和开场事件",
                "player_mapping": [
                    {{ "player_id": str, "character_name": str, "description": str }}
                ],
                "title": "给这局游戏起一个名字"
            }}
        """

        try:
            typing_target = self.engine.main_channel if self.engine.main_channel else self.engine.current_channel
            # 使用 discord 原生打字效果
            async with typing_target.typing():
                # 3. 调用千问（带超时保护：90秒）
                result_str = await asyncio.wait_for(
                    ask_qwen_async(
                        prompt_text=combined_prompt,
                        system_instruction="你是一个只输出标准 JSON 的角色扮演游戏引擎，为多个玩家的角色扮演构建一个世界观",
                        mode="json",
                        model="qwen-turbo",
                        temperature=1
                    ),
                    timeout=90.0
                )

                if not result_str:
                    raise Exception("AI 响应为空")

                # 4. 数据解析
                data = json.loads(result_str)

                # --- A. 数据中心化存储 ---
                mapping = data.get("player_mapping", [])
                for player_dict in mapping:
                    player_id=player_dict.get("player_id", "未知玩家")
                    character_name=player_dict.get("character_name", "未知角色")
                    character_des=player_dict.get("description", "未知描述")
                    self.manager.game_state["player_mapping"][player_id] = character_name

                    player_info_sent=f"👤 玩家 @{player_id} -> 扮演: 【{character_name}】{character_des}"
                    print(player_info_sent)
                    await self.engine.send_to_public(player_info_sent, tts=False, speaker="DM-bot")

                self.manager.game_state["scene"] = data.get("scene", "未知地点")
                rough_description = data.get("plot_round_description", "")
                chat_entry = self.manager.build_chat_entry(rough_description, "DM-bot")
                self.manager.game_state["chat_history"].append(chat_entry)


                time_space = data.get("time_space", "未知时空")

                self.manager.game_state["long_term_memory"]["time_space"] = time_space
                # --- B. 更新公屏剧情 ---
                public_text = data.get("public_story", "故事悄然拉开序幕...")
                # 只发送最后一段，让开场更精炼（避免过长叙述）
                paragraphs = [p.strip() for p in public_text.split("\n\n") if p.strip()]
                if paragraphs:
                    public_text = paragraphs[-1]

                # 为TTS准备纯叙述文本：使用统一清洗函数去除所有非朗读内容
                from engine import clean_tts_text
                tts_text = clean_tts_text(public_text, max_length=500)

                display_text = f"🚀 剧本已生成！\n\n{public_text}\n\n{time_space}"
                tts_only = f"{tts_text}\n{time_space}" if tts_text.strip() else time_space

            # 5. 剧本已生成，立即切换到 PLAYING 状态，让前端先退出等待页面再播报语音
            self.engine.room_state["status"] = "PLAYING"
            await self.engine.sio.emit('stage_change', {"to": "PLAYING"})

            # 短暂等待前端 React 处理 stage_change 并渲染游戏界面（避免消息在等待页面上显示）
            await asyncio.sleep(0.3)

            # 前端显示完整内容，TTS只朗读纯叙述（在游戏界面中播报）
            await self.engine.send_to_public(display_text, tts=True, speaker="DM-bot", tts_override_text=tts_only)

            # --- C. 初始化游戏文件并遍历玩家私发秘密（后台异步，不阻塞玩家体验）---
            # 这里的 Key 是 Discord Name，确保 AI 返回的 Key 对应得上

            # 初始化游戏文件（使用游戏名称和时间戳）
            game_name = data.get("title", "未命名游戏")
            self.manager.plot_management.init_game_files(game_name)

            # --- C2. 初始化长期记忆（带超时保护，失败不阻塞流程）---
            try:
                await asyncio.wait_for(
                    self.manager.plot_management._initialize_long_term_memory(initial_data=data, rough_description=rough_description),
                    timeout=90.0
                )
            except (asyncio.TimeoutError, Exception) as e:
                print(f"⚠️ [Manager] 长期记忆初始化失败（{e}），跳过，继续游戏流程")
                # 不阻塞，继续推进

            # --- D. 并行执行深度剧情推演和开场引导生成（带超时保护）---
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        self.manager.plot_management._generate_deep_plot_inspection(data),
                        self.manager.plot_management._generate_opening_guidance(data, rough_description)
                    ),
                    timeout=120.0  # 深度剧情推演和开场引导总共最多等120秒
                )
            except asyncio.TimeoutError:
                print(f"⚠️ [Manager] 深度剧情推演/开场引导超时（120秒），跳过，直接进入游戏")
                # 不阻塞游戏流程，超时后继续

            # --- E. 保存初始游戏状态到Temp文件夹 ---
            self.manager.plot_management._save_game_state_to_temp()

        except asyncio.TimeoutError:
            print(f"❌ [Manager Error] AI调用超时（90秒）")
            self.engine.room_state["status"] = "LOBBY"
            await self.engine.sio.emit('stage_change', {"to": "LOBBY"})
            await self.engine.send_to_public("⚠️ 剧本生成超时，AI 响应太慢，请稍后重试或减少玩家数量。", speaker="DM-bot")
        except Exception as e:
            print(f"❌ [Manager Error] 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            self.engine.room_state["status"] = "LOBBY"
            # 通知前端回到 LOBBY 状态
            await self.engine.sio.emit('stage_change', {"to": "LOBBY"})
            await self.engine.send_to_public(f"⚠️ 剧本生成出现异常，请检查配置后重试：{str(e)}", speaker="DM-bot")

    async def start_festival_game(self, player_name, total_rounds=15):
        """使用端午节特辑剧本 JSON 直接启动游戏（跳过征集环节）"""
        import json as _json, os as _os

        json_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "DBFestival.json")
        with open(json_path, 'r', encoding='utf-8') as f:
            fd = _json.load(f)

        title = fd.get("title", "端午到，龙舟跑")

        # ===== 构建 player_mapping =====
        self.manager.game_state["player_mapping"][player_name] = "林墨"
        self.manager.game_state["player_count"] = 1
        self.manager.game_state["total_rounds"] = total_rounds
        self.manager.game_state["suggestions"] = ["端午节穿越题材，父子亲情，时空闭环"]
        self.manager.game_state["role_prefs"] = {player_name: f"林墨 - {title}"}

        # ===== 初始化角色属性（从 characterParams 提取）=====
        self.manager.game_state["character_attributes"] = {
            "林墨": {
                "龙舟队鼓手": 10,
                "长命缕": 1,       # 1=佩戴
                "洞察值": 0,
                "因果值": 0,
                "热情值": 0,
            }
        }

        # ===== 提取剧本数据 =====
        characters = fd.get("characters", {}).get("nodes", [])
        locations = fd.get("locations", {}).get("nodes", [])
        items = fd.get("items", {}).get("nodes", [])
        plot_nodes = fd.get("plot", {}).get("graph", {}).get("nodes", [])
        plot_edges = fd.get("plot", {}).get("graph", {}).get("edges", [])
        mechanics = fd.get("mechanics", {})
        char_params = fd.get("characterParams", [])

        # 提取角色信息
        player_chars = {}
        npc_chars = {}
        for node in characters:
            name = (node.get("label") or "").strip()
            data = node.get("data", {})
            if name == "林墨":
                player_chars[name] = {
                    "role_name": name,
                    "identity": "穿越者 / 数据分析师 / 28岁",
                    "public_bio": data.get("appearance", ""),
                    "personal_bio": data.get("description", ""),
                    "secret": data.get("motivation", ""),
                    "goal": "理解父亲，在时空闭环中找回自我",
                    "attributes": data.get("worldParams", {}),
                }
            elif name and name != "林墨":
                desc = data.get("description", "") or data.get("appearance", "") or ""
                npc_chars[name] = {
                    "identity": desc[:100] if desc else "未知身份",
                    "description": (data.get("personality", "") or desc)[:150],
                }

        # 提取地点信息
        scene_map = {}
        first_location_name = ""
        for node in locations:
            name = (node.get("label") or "").strip()
            data = node.get("data", {})
            if not first_location_name:
                first_location_name = name
            scene_map[name] = {
                "detail": data.get("description", "") or data.get("terrain", ""),
            }

        # 提取物品信息
        item_map = {}
        for node in items:
            name = (node.get("label") or "").strip()
            data = node.get("data", {})
            if name:
                item_map[name] = {
                    "description": data.get("function", "") or data.get("appearance", ""),
                    "owner": data.get("initialLocation", "场景"),
                }

        # 提取剧情节点（简化后供 AI 参考）
        first_node = plot_nodes[0] if plot_nodes else {}
        first_scene_desc = first_node.get("data", {}).get("sceneDescription", "")
        
        # 构建剧情节点的路线图（供 AI 主持时参考）
        plot_roadmap = []
        for node in plot_nodes:
            nd = node.get("data", {})
            actions = nd.get("potentialActions", {})
            plot_roadmap.append({
                "label": node.get("label", ""),
                "description": nd.get("description", ""),
                "scene": nd.get("sceneDescription", ""),
                "options": list(actions.keys()) if actions else [],
            })

        # 简化的剧情节点（用于 AI 上下文）
        simplified_plot = []
        for node in plot_nodes:
            nd = node.get("data", {})
            actions = nd.get("potentialActions", {})
            simplified_plot.append({
                "id": node.get("id", ""),
                "name": node.get("label", ""),
                "scene": nd.get("sceneDescription", ""),
                "guide": nd.get("description", ""),
                "choices": {opt: "" for opt in actions.keys()} if actions else {},
            })

        # ===== 构建 plot_inspection（导演手册） =====
        plot_inspection = {
            "main_line_logic": (
                f"【{title}】林墨被父亲系上长命缕后穿越回1996年。"
                "他本想用现代商业思维帮父亲，却发现父亲未来所有让他抓狂的古怪行为"
                "（空出主位、念叨奇怪口诀、做黑暗料理），全是自己穿越时一手造成的宿命闭环。"
                "在龙舟赛的鼓声中，他学会理解与接纳父亲。"
            ),
            "possible_endings": [
                {"ending_name": "定制款老爹（真结局）", "condition": "因果值>=3 且 热情值>=3 且 配合闭环",
                 "description": "完美交付闭环，林墨找回鲜活的生命力。对应结局A：节点13"},
                {"ending_name": "系统崩溃（迷失结局）", "condition": "强行打破闭环（拒绝长命缕）",
                 "description": "存在被抹除，成为游荡在1996年的无效代码。对应结局B：节点14"},
                {"ending_name": "旁观者清（平庸结局）", "condition": "热情值<3",
                 "description": "没有改变历史，历史也没有改变他。对应结局C：节点15"},
            ],
            "round_pacing": {
                "R1-3": "入局：端午节穿越、确认1996年时空、初遇22岁的小林父亲。对应节点1→节点2→节点3",
                "R4-7": "剥茧：改造粽子铺揪出内鬼(节点4)、龙舟训练觉醒节奏感(节点5/6)",
                "R8-11": "变局：发现台词闭环(节点7)→找到旧账本证据(节点8)→顿悟自己才是Bug的源头(节点9)",
                "R12-15": "破局：决战江面(节点10/11)→长命缕死结(节点12)→结局(节点13/14/15)",
            },
            "player_highlight_moments": {
                player_name: (
                    "龙舟鼓点觉醒：从敲代码的手到敲战鼓的手；"
                    "发现旧账本上的丑笑脸：确认时空闭环的瞬间；"
                    "亲手系上长命缕：完成闭环的仪式感。"
                ),
            },
            "festival_plot_graph": simplified_plot,  # 完整剧情图供 AI 逐节点推进
            "character_params": char_params,
            "mechanics_checks": mechanics.get("checks", []),
            "festival_mode": True,  # 标记为剧本模式
        }

        # ===== 设置当前剧情节点追踪 =====
        initial_checkpoint = fd.get("plot", {}).get("initialCheckpoint", "")
        self.manager.game_state["festival_current_node"] = initial_checkpoint or plot_nodes[0].get("id", "")
        self.manager.game_state["festival_node_history"] = []  # 已经过的节点

        # ===== 设置游戏状态 =====
        self.manager.game_state["scene"] = first_location_name or "老林家客厅/厨房"
        self.manager.game_state["scene_description"] = first_scene_desc
        self.manager.game_state["long_term_memory"] = {
            "world_summary": (
                f"【{title}】2026年端午节恰逢父亲节。林墨（玩家）是一名28岁沉迷于写bug的现代青年。"
                f"这天老林在厨房熬煮气味刺鼻的折耳根陈皮腊肉粽，强行给林墨左手腕系上一根"
                f"褪色的五彩长命缕并打死结。钟声响起后，林墨推门走上街道，却发现手机没信号、"
                f"街景变成了1996年的模样……"
            ),
            "time_space": "2026年端午节 → 穿越至 1996年端午节前后",
            "player_characters": player_chars,
            "player_relationships": [],
            "entities": {
                "npc_characters": npc_chars,
                "scenes": scene_map,
                "items": item_map,
                "relationships": [],
            },
            "initial_scene": first_scene_desc,
        }
        self.manager.game_state["plot_inspection"] = plot_inspection

        # 初始化游戏文件
        self.manager.plot_management.init_game_files(title)

        # ===== 保存初始状态 =====
        self.manager.plot_management._save_game_state_to_temp()

        # ===== 立即切换到 PLAYING（让前端在 1秒内退出等待页） =====
        self.engine.room_state["status"] = "PLAYING"
        await self.engine.sio.emit('stage_change', {"to": "PLAYING"})

        # ===== 发送开场白（PLAYING 状态下发送，消息出现在游戏界面中） =====
        preface = (
            f"🚀 **【{title}】** 剧本已装载！\n\n"
            f"📖 **你的角色：林墨**\n"
            f"28岁的现代职场青年，常年熬夜写代码，左手腕上戴着一根五彩长命缕。\n\n"
            f"{first_scene_desc}\n\n"
            f"⏳ 今天是2026年端午节，也是父亲节。故事从你推开家门的那一刻开始……"
        )
        # TTS 设为 False 避免阻塞，后面的 AI 引导语再用 TTS
        await self.engine.send_to_public(preface, tts=False, speaker="DM-bot")

        # ===== 发送角色卡给前端 =====
        char_data = player_chars.get("林墨", {})
        await self.engine.send_player_card({
            "player_id": player_name,
            "role_name": "林墨",
            "identity": char_data.get("identity", ""),
            "public_bio": char_data.get("public_bio", ""),
            "personal_bio": char_data.get("personal_bio", ""),
            "relationships": [],
            "secret": char_data.get("secret", "")[:200] if char_data.get("secret") else "",
            "goal": char_data.get("goal", ""),
            "attributes": self.manager.game_state["character_attributes"].get("林墨", {}),
        })

        # ===== 后台生成开场引导语（不阻塞玩家进入游戏） =====
        _fetch_festival_opening = self._spawn_festival_opening_guidance(
            title, first_location_name, first_scene_desc, player_name
        )

        # ===== 后台生成角色头像（优先读缓存，避免反复调用 AI） =====
        self._spawn_festival_avatar(title, char_data)

        # ===== 保存角色形象描述，用于后续场景图保持人物一致 =====
        self._save_character_visual(title, char_data)

        # ===== 后台生成第一幕场景背景图（立即开始，不等待） =====
        async def _initial_scene_bg():
            try:
                scene_name = self.manager.game_state.get("scene", "老林家客厅/厨房")
                scene_desc = self.manager.game_state.get("scene_description", first_scene_desc)
                if hasattr(self.engine, '_generate_and_send_scene_image'):
                    await self.engine._generate_and_send_scene_image(scene_name, scene_desc)
            except Exception as e:
                print(f"❌ [Festival] 初始场景图生成失败: {e}")
        asyncio.create_task(_initial_scene_bg())

        print(f"✅ [Festival] 端午特辑游戏已启动：{title}")

    def _save_character_visual(self, title, char_data):
        """保存角色形象描述到缓存，供场景图提示词复用"""
        from image_cache import build_character_visual_desc, save_character_visual
        visual_desc = build_character_visual_desc(
            character_name="林墨",
            identity=char_data.get("identity", ""),
            public_bio=char_data.get("public_bio", ""),
        )
        save_character_visual("林墨", title, visual_desc)

    def _spawn_festival_avatar(self, title, char_data):
        """后台任务：生成/读取角色头像（缓存优先）"""
        async def _do():
            try:
                from image_cache import (
                    avatar_cache_exists, avatar_cache_path,
                    download_and_cache, save_character_visual,
                    build_character_visual_desc,
                )
                from ai_handler import generate_image_url_async

                role_name = "林墨"
                identity = char_data.get("identity", "")
                public_bio = char_data.get("public_bio", "")

                # 1. 先检查本地缓存
                if avatar_cache_exists(role_name, title):
                    print(f"📦 [Festival] 使用本地缓存的 {role_name} 头像")
                    cache_path = avatar_cache_path(role_name, title)
                    await self.engine.send_avatar_to_public(role_name, cache_path)
                    return

                # 2. 缓存未命中，调用 AI 生成
                prompt = (
                    f"剧本杀角色头像：{role_name}，职业是{identity}，{public_bio}。"
                    "风格为具有个人特点的角色立绘，正面半身像，高质量，4K画质。"
                )
                print(f"🎨 [Festival] 开始AI生成头像: {role_name}")
                image_url = await generate_image_url_async(prompt)

                if image_url:
                    # 下载并缓存到本地
                    cache_path = avatar_cache_path(role_name, title)
                    if download_and_cache(image_url, cache_path):
                        # 保存角色形象描述（用于后续场景图一致性）
                        visual_desc = build_character_visual_desc(role_name, identity, public_bio)
                        save_character_visual(role_name, title, visual_desc)

                        # 发送头像（兼容 Discord/Web 双端）
                        if os.path.exists(cache_path):
                            await self.engine.send_avatar_to_public(role_name, cache_path)
                            print(f"✅ [Festival] 头像已缓存并发送: {role_name}")
                            return

                print(f"⚠️ [Festival] 头像生成/缓存失败: {role_name}")
            except Exception as e:
                print(f"❌ [Festival] 头像任务异常: {e}")
                import traceback
                traceback.print_exc()

        asyncio.create_task(_do())

    def _spawn_festival_opening_guidance(self, title, location_name, scene_desc, player_name):
        """后台任务：生成并发送开场引导语（不阻塞游戏启动）"""
        async def _do():
            try:
                guidance_prompt = f"""
                    你是角色扮演游戏主持人，游戏现在开始。
                    
                    【游戏信息】:
                    - 剧本：{title}
                    - 场景：{location_name}
                    - 场景描述：{scene_desc}
                    - 玩家：{player_name} 扮演 林墨
                    
                    请生成简短的开场引导语（100字以内）：
                    1. 描述林墨所处的场景
                    2. 2-3个行动选项（→ 开头）
                    
                    直接输出引导语文本，不要JSON。
                """
                from ai_handler import ask_qwen_async as _qwen
                guidance = await asyncio.wait_for(
                    _qwen(
                        prompt_text=guidance_prompt,
                        system_instruction="你是经验丰富的TRPG主持，语言简洁生动。",
                        mode="str",
                        model="qwen-plus",
                        temperature=0.3,
                    ),
                    timeout=30.0,
                )
                if guidance:
                    await self.engine.send_to_public(guidance, tts=True, speaker="DM-bot")
                    print(f"📜 [Festival] 开场引导语已发送")
            except (asyncio.TimeoutError, Exception) as e:
                print(f"⚠️ [Festival] 开场引导生成失败（后台任务）: {e}")

        asyncio.create_task(_do())

    async def reset_game(self):
        """重置游戏"""
        # 重置游戏流程状态
        self.engine.room_state["status"] = "IDLE"

        # 重置游戏内容状态
        self.manager.init_game_state()

        # 重置 PlotManagement 的游戏文件
        self.manager.plot_management.game_start_time = None
        self.manager.plot_management.game_short_name = ""
        self.manager.plot_management.plot_file = None
        self.manager.plot_management.memory_file = None

        # 通知网页端
        await self.engine.sio.emit('stage_change', {
            "to": "IDLE"
        })

        await self.engine.send_to_channel("🧹 **游戏已重置**", speaker="DM-bot")

    # === 后台任务管理 ===
    async def start_background_tasks(self):
        """启动后台监控"""
        # 检查任务是否已经在运行
        if self.manager.background_task and not self.manager.background_task.done():
            print("⚠️ 后台监控已在运行中")
            return

        # 创建新的后台任务
        self.manager.background_task = asyncio.create_task(self._monitor_activity())
        print("💓 后台监控已启动")

    async def stop_background_tasks(self):
        """停止后台监控"""
        if self.manager.background_task and not self.manager.background_task.done():
            self.manager.background_task.cancel()
            try:
                await self.manager.background_task
            except asyncio.CancelledError:
                print("💤 后台监控已停止")
            self.manager.background_task = None

    async def _monitor_activity(self):
        """监控玩家活跃度"""
        max_idle_time=300
        while self.manager.is_running:
            try:
                await asyncio.sleep(max_idle_time/5)  # 每30秒检查一次

                if self.engine.room_state["status"] == "PLAYING":
                    idle_time = time.time() - self.manager.last_action_time

                    if idle_time > max_idle_time:  # 2分钟无活动
                        print("长时间无活动，开启主持人干预")
                        await self._handle_inactivity()
                    else:
                        print(f"当前无活动时间{idle_time}<{max_idle_time}")
                else:
                    print(f"⚡ 游戏未开始，处于{self.engine.room_state['status']}，跳过活跃度监控")
            except Exception as e:
                print(f"❌ 后台监控活跃度失败: {e}")

    async def _handle_inactivity(self):
        """处理玩家不活跃情况"""
        print("⚡ 检测到玩家不活跃，AI主持人将介入...")

        long_term_memory=self.manager.game_state['long_term_memory']
        context=self.manager._build_context()

        prompt = f"""
            玩家长时间没有行动，请参考如下信息进行干预：
            游戏当前状态：{long_term_memory}
            近期用户对话上下文：{context}

            请提供一个自然的环境变化描述或引导，以激发玩家参与感。不要进行实质情节推进。
            严格按照如下步骤进行 JSON 格式回复（不要回复任何 JSON 以外的内容）：
            1. use_environment_description: bool (是否广播环境变化)
            2. environment_description: str (发送到公聊的内容)
            3. use_private_instruction: bool (是否发送私聊引导)
            4. private_instruction: list[dict] (私聊内容，格式参照 PRIVATE_CHAT_DESCRIPTION)

            以下是私信格式要求：{prompts.PRIVATE_CHAT_DESCRIPTION}

            回复格式必须是合法的 JSON 对象。
        """

        system_prompt = "你是一个游戏主持人，负责在停顿时通过环境描写或私下提示来引导玩家继续游戏。"

        try:
            # 1. 确定打字状态显示位置（优先公聊频道）
            typing_target = self.engine.main_channel if self.engine.main_channel else self.engine.current_channel

            # 使用 discord 原生打字效果
            async with typing_target.typing():
                # 2. 调用 Qwen 获取结构化 JSON
                result_str = await ask_qwen_async(
                    prompt_text=prompt,
                    system_instruction=system_prompt,
                    mode="json",
                    model="qwen-max"
                )

                if result_str:
                    ice_breaking_decision = json.loads(result_str)

                    # 3. 解析并分发指令
                    use_env = ice_breaking_decision.get("use_environment_description", False)
                    env_desc = ice_breaking_decision.get("environment_description", "")
                    use_priv = ice_breaking_decision.get("use_private_instruction", False)
                    priv_inst = ice_breaking_decision.get("private_instruction", [])

                    # --- 公共广播部分 ---
                    if use_env and env_desc:
                        print(f"✅ 使用环境变化描述: {env_desc}")
                        await self.engine.send_to_public(env_desc, tts=True, speaker="DM-bot")

                    # --- 私聊引导部分 ---
                    if use_priv and priv_inst:
                        print(f"✅ 使用私聊指令，数量: {len(priv_inst)}")
                        for private_message in priv_inst:
                            await self.manager.plot_management._process_private_message(private_message)
                else:
                    print("❌ AI介入失败: 返回结果为空")
        except Exception as e:
            print(f"❌ AI介入失败: {e}")

    # === 玩家输入处理 ===
    async def handle_player_input(self, content, player_name, channel=None, no_action=False, bypass_batch=False):
        """处理玩家输入"""
        try:
            self.manager.last_action_time = time.time()

            # 更新频道
            if channel:
                self.engine.current_channel = channel

            # 记录对话历史
            chat_entry = self.manager.build_chat_entry(content, player_name, channel)
            self.manager.game_state["chat_history"].append(chat_entry)

            # 如果 bypass_batch=True，直接处理（用于投票结果等系统消息）
            if bypass_batch:
                print(f"🔄 [直通处理] 系统消息: {player_name}")
                # 显示typing并获取AI响应
                typing_gen = self.engine.typing()
                await typing_gen.__anext__()
                new_round, response = await self.check_new_round(content, player_name)
                await typing_gen.aclose()

                if new_round and not no_action:
                    await self.engine.send_to_public(response, tts=True, speaker="DM-bot")
                    print(f"第{self.manager.game_state['round']}轮结束，进入下一轮")
                    self.manager.game_state['round'] += 1
                    await self.manager.plot_management.push_new_round(chat_entry)
                else:
                    await self.engine.send_to_public(response, tts=True, speaker="DM-bot")
                    print(f"不切换轮次，当前轮次：{self.manager.game_state['round']}")
                return

            # 将消息加入待处理队列
            self.manager.pending_messages.append({
                "content": content,
                "player_name": player_name,
                "channel": channel,
                "chat_entry": chat_entry,
                "no_action": no_action
            })

            # 如果没有正在处理的批量任务，启动新的批量处理
            if not self.manager.batch_processing_task or self.manager.batch_processing_task.done():
                self.manager.batch_processing_task = asyncio.create_task(self._process_pending_messages())

        except Exception as e:
            print(f"❌ handle_player_input 错误: {e}")

    async def _process_pending_messages(self):
        """批量处理待处理的玩家消息"""
        try:
            # 等待一段时间收集更多消息
            while True:
                await asyncio.sleep(self.manager.batch_delay)

                # 检查是否有新消息加入
                if len(self.manager.pending_messages) == 0:
                    break

                # 获取当前待处理的所有消息
                messages_to_process = self.manager.pending_messages.copy()
                self.manager.pending_messages.clear()

                # 如果有消息待处理
                if messages_to_process:
                    print(f"📥 批量处理 {len(messages_to_process)} 条玩家消息")

                    # 合并所有玩家发言
                    combined_content = ""
                    for msg in messages_to_process:
                        combined_content += f"{msg['player_name']}: {msg['content']}\n"

                    # 显示typing并获取AI响应
                    typing_gen = self.engine.typing()
                    await typing_gen.__anext__()

                    # 使用最后一条消息的玩家名作为代表
                    last_msg = messages_to_process[-1]
                    new_round, response = await self.check_new_round(combined_content, last_msg['player_name'])
                    await typing_gen.aclose()

                    if new_round and not last_msg['no_action']:
                        await self.engine.send_to_public(response, tts=True, speaker="DM-bot")
                        print(f"第{self.manager.game_state['round']}轮结束，进入下一轮")
                        self.manager.game_state['round'] += 1
                        await self.manager.plot_management.push_new_round(last_msg['chat_entry'])
                    else:
                        await self.engine.send_to_public(response, tts=True, speaker="DM-bot")
                        print(f"不切换轮次，当前轮次：{self.manager.game_state['round']}")

        except Exception as e:
            print(f"❌ 批量处理消息错误: {e}")
            import traceback
            traceback.print_exc()

    async def check_new_round(self, content, player_name):
        """针对玩家的特定输入，检查是否需要切换轮次"""
        long_term_memory=self.manager.game_state['long_term_memory']
        context=self.manager._build_context()

        user_input=f'''
            这是用户进行跑团的长期记录：{long_term_memory}
            这是最近次与用户的对话历史：{context}
            这是用户"{player_name}"的最新输入：{content}
            当前已经到达了轮次：{self.manager.game_state['round']}/{self.manager.game_state['total_rounds']}
        '''
        system_prompt="""
            你是一个跑团机器人助手，面对一或多位玩家主持游戏，使用用户的"角色名字+(账号名)"来称呼用户。现在你需要帮助我判断用户的行为是否构成有效行为，需要切换轮次。
                + 例如，如果用户只是在询问现在的时间、询问之前自己经历了什么或者自己身上有什么东西，则你可以立即回答用户，而不需要切换轮次。
                + 如果用户选择了进行某种行为，如地点切换（打开一扇门等）、与npc对话、使用道具，或者明确要求你推进情节，则需要切换轮次。
                + 在我们的游戏中，用户只能决定自己的行为，而不能取代你进行故事编写或叙述行为的结果。如果用户违反了这一规则，请你礼貌地提醒用户，告知其越界的行为是无效的。
                + 如果用户给出了一些与情节无关的信息，可能是误触，请你用简短的一句话引导玩家回到游戏（例如"你可以四处看看"、"试试和同伴商量一下"），不要静默。quick_public_answer绝对不能为空。
                + 当玩家提出需要集体决策（如"我们想投票决定"、"大家一起投票"）时，不需要切换轮次，而是在quick_public_answer中给出建议的投票选项，但不要直接发起投票。真正的投票会在后续轮次通过指令发起。
            操作步骤：
                1. 在analysis位置用一两句话写出你的判断理由。
                2. 之后，在start_new_round位置写出是否需要切换轮次，true表示需要，false表示不需要。
                3. 如果你选择了不需要切换轮次，请你直接作为DM在公聊频道回答用户的输入，填写在quick_public_answer的位置，仅回答用户问题，不进行任何剧情的推进。在start_of_long_answer位置填写空字符串。quick_public_answer绝对不能为空字符串，至少要有一句引导性的话。
                4. 如果你选择了需要切换轮次，请你仅在现有的人物、物品、场景下描写用户行为的直接后果，或通过渲染环境暂时吸引一下用户的注意力，不进行任何实质性的剧情推进，为后续真正的DM回答拖延一点时间。将你的过渡性引导词写在start_of_long_answer位置，并将quick_public_answer设置为空字符串。
                5. 如果用户要求私发信息，请你在private_message_request位置写true，否则写出false。
                请使用标准的json格式进行回答，结构如下：
            {
                "analysis": str,
                "start_new_round": bool,
                "quick_public_answer": str,
                "start_of_long_answer": str,
                "private_message_request": bool
            }
        """

        try:
            result_str = await ask_qwen_async(prompt_text=user_input, system_instruction=system_prompt, mode="json", model="qwen-plus")
            if result_str:
                command=json.loads(result_str)
            else:
                print("Qwen no response in check new round")
                command={}

            print(f"AI指令: {command}")

            if isinstance(command, dict):
                if command.get("start_new_round"):
                    return True, command.get("start_of_long_answer", "")
                else:
                    private_message_request=command.get("private_message_request", False)
                    if private_message_request:
                        await self.manager.plot_management.quick_private_chat(content, command.get("quick_public_answer", ""), player_name)
                    return False, command.get("quick_public_answer", "")
            else:
                print("❌ AI 未在 check_new_round 中给出有效回应")
                return False, "AI 未给出有效回应"

        except Exception as e:
            print(f"❌ 解析AI响应失败: {e}")
            return False, f"系统出错: {str(e)}"
