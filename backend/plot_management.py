"""
剧情推演和记忆管理模块
负责AI剧情生成、长期记忆管理、私信处理等
"""
import asyncio
import time
import json
import os
import tempfile
import requests
from ai_handler import ask_deepseek_async, ask_qwen_async, ask_gpt_async, generate_image_url_async
from utils.find_json import get_dict_from_str
import prompts
from literature_search import get_search_engine

class PlotManagement:
    """剧情推演和记忆管理器"""

    def __init__(self, manager):
        self.manager = manager
        self.engine = manager.engine
        self.temp_dir = os.path.join(os.path.dirname(__file__), "Temp")
        self._ensure_temp_dir()
        self.game_start_time = None
        self.game_short_name = ""
        self.plot_file = None
        self.memory_file = None

    def _ensure_temp_dir(self):
        """确保Temp文件夹存在"""
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
            print(f"📁 [Temp] 创建Temp文件夹: {self.temp_dir}")

    def _save_game_state_to_temp(self):
        """保存游戏状态（plot_inspection和long_term_memory）到Temp文件夹，更新固定文件"""
        try:
            # 如果尚未初始化游戏文件，则跳过
            if not self.plot_file or not self.memory_file:
                print("⚠️ [Save] 游戏文件尚未初始化，跳过保存")
                return

            round_num = self.manager.game_state.get('round', 0)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

            # 保存 plot_inspection（添加元数据）
            plot_data = self.manager.game_state.get('plot_inspection', {})
            plot_data['_meta'] = {
                'last_updated': timestamp,
                'round': round_num,
                'game_start_time': self.game_start_time,
                'game_name': self.game_short_name
            }
            with open(self.plot_file, 'w', encoding='utf-8') as f:
                json.dump(plot_data, f, ensure_ascii=False, indent=2)

            # 保存 long_term_memory（添加元数据）
            memory_data = self.manager.game_state.get('long_term_memory', {})
            memory_data['_meta'] = {
                'last_updated': timestamp,
                'round': round_num,
                'game_start_time': self.game_start_time,
                'game_name': self.game_short_name
            }
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)

            print(f"💾 [Save] 第{round_num}轮状态已更新:")
            print(f"   - {self.plot_file}")
            print(f"   - {self.memory_file}")

        except Exception as e:
            print(f"❌ [Save] 保存游戏状态失败: {e}")
            import traceback
            traceback.print_exc()

    def init_game_files(self, game_name: str):
        """初始化游戏文件，用游戏开始时间和简略名称标记"""
        try:
            self.game_start_time = time.strftime("%Y%m%d_%H%M%S")

            # 简化游戏名称（移除特殊字符，限制长度）
            import re
            # 移除或替换特殊字符，只保留中英文、数字和下划线
            simplified_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', game_name)
            # 限制长度，最多20个字符
            simplified_name = simplified_name[:20]

            self.game_short_name = simplified_name

            # 生成固定的文件名
            file_prefix = f"{self.game_start_time}_{self.game_short_name}"
            self.plot_file = os.path.join(self.temp_dir, f"plot_inspection_{file_prefix}.json")
            self.memory_file = os.path.join(self.temp_dir, f"long_term_memory_{file_prefix}.json")

            print(f"📁 [Game] 初始化游戏文件:")
            print(f"   - 游戏名称: {game_name}")
            print(f"   - 简略名称: {self.game_short_name}")
            print(f"   - 开始时间: {self.game_start_time}")
            print(f"   - plot_inspection: {self.plot_file}")
            print(f"   - long_term_memory: {self.memory_file}")

        except Exception as e:
            print(f"❌ [Game] 初始化游戏文件失败: {e}")
            import traceback
            traceback.print_exc()

    # === 剧情初始化 ===
    async def _initialize_long_term_memory(self, initial_data, rough_description):
        """将初始剧情转化为结构化的长期记忆库，同时完成角色卡发放"""

        extraction_input = f"""
            请分析以下剧本数据并整理成结构化实体库。

            【核心任务】:
            1. 首先对于现有的信息进行梳理，将你对于情节的理解和设想写在analysis位置。
            2. 给出world_summary概括当前故事的局势，以及你认为这个故事应该有怎样的亮点。
            3. 建立玩家的详细角色卡，填写在player_characters位置，以便为玩家发放。**重要：每个玩家（player_id）必须对应一个独立的、不同的角色卡，角色身份、职业、背景故事必须各不相同，禁止合并或重复。**
            4. 列出所有玩家之间的人物关系（每人至少一个，除非只有一个玩家），并给出他们之间的关系性质。
            5. 列出所有非玩家角色（npc_characters）、他们之间和他们与玩家的关系（relationships）、物品（items）和场景（scene）在entities位置，并给出关于他们基本情况的介绍。

            【初始数据】:
            剧情简介：{rough_description}
            初始化数据：{initial_data}

            请严格按照以下 JSON 格式回复：
            {{
                "analysis": str,
                "world_summary": str,
                "player_characters": {{
                    "玩家的player_id": {{
                        "role_name": "扮演的角色名",
                        "identity": "职业/身份",
                        "public_bio": "其他玩家能看到的形象",
                        "personal_bio": "玩家自己的详细背景故事，如身世、经历、性格、爱好、弱点、优点",
                        "secret": "角色的核心秘密（仅用于私聊，切勿公开给玩家之外的角色）",
                        "goal": "角色的驱动目标",
                        "attributes": {{"属性名称": "属性值"}}
                    }}
                }},
                "player_relationships": [
                    {{ "from": "人物A", "to": "人物B", "relation": "描述关系性质", "status": "友好/敌对/中立/复杂" }}
                ]
                "entities": {{
                    "npc_characters": {{
                        "角色名": {{ "identity": "身份", "description": "特征" }}
                    }},
                    "relationships": [
                        {{ "from": "人物A", "to": "人物B", "relation": "描述关系性质", "status": "友好/敌对/中立/复杂" }}
                    ],
                    "items": {{
                        "物品名": {{ "description": "描述", "owner": "持有者角色名或具体场景名" }}
                    }},
                    "scenes": {{ "场景名": {{ "detail": "描述" }} }}
                }}
            }}
        """

        try:
            memory_json_str = await asyncio.wait_for(
                ask_qwen_async(
                    prompt_text=extraction_input,
                    system_instruction="你是一个精密的角色扮演游戏档案管理员，擅长梳理复杂的人物关系和物品归属。",
                    mode="json",
                    model="deepseek-v3"
                ),
                timeout=90.0
            )

            if memory_json_str:
                extracted_memory_list = get_dict_from_str(memory_json_str)
                if extracted_memory_list:
                    extracted_memory = extracted_memory_list[0]
                else:
                    print("！警告！长期记忆初始化 json 解析失败")
                    return
                self.manager.game_state["long_term_memory"].update({
                    "world_summary": extracted_memory.get("world_summary", ""),
                    "player_characters": extracted_memory.get("player_characters", {}),
                    "player_relationships": extracted_memory.get("player_relationships", []),
                    "entities": extracted_memory.get("entities", {}),
                })

                # --- 增强版控制台打印逻辑 ---
                print("\n" + "📜" + "="*50)
                print("🧠 [Memory Check] 长期记忆库初始化成功！")

                # 1. 玩家详细信息
                player_mapping = self.manager.game_state.get("player_mapping", {})
                player_relationships = extracted_memory.get("player_relationships", [])
                all_relationships = extracted_memory.get("entities", {}).get("relationships", [])

                def infer_tts_profile(char: dict) -> dict:
                    """根据角色描述自动推断 TTS 音色/语气/语速配置"""
                    text = "".join([
                        str(char.get("identity", "")),
                        str(char.get("public_bio", "")),
                        str(char.get("personal_bio", "")),
                    ])
                    t = text.lower()

                    # 语音（男/女）
                    voice = None
                    if any(k in t for k in ["男", "先生", "男性", "大叔"]):
                        voice = "zh-CN-YunxiNeural"
                    elif any(k in t for k in ["女", "小姐", "女性", "姑娘"]):
                        voice = "zh-CN-XiaoxiaoNeural"

                    # 情绪/语气
                    style = None
                    if any(k in t for k in ["愤怒", "怒", "愤慨", "暴躁", "激动"]):
                        style = "angry"
                    elif any(k in t for k in ["悲伤", "难过", "悲哀", "痛苦"]):
                        style = "sad"
                    elif any(k in t for k in ["开心", "快乐", "喜悦", "欢快", "兴奋"]):
                        style = "cheerful"
                    elif any(k in t for k in ["冷静", "镇定", "理智", "沉稳"]):
                        style = "calm"
                    elif any(k in t for k in ["神秘", "阴沉", "低沉", "深沉"]):
                        style = "sad"

                    # 语速
                    rate = "+0%"
                    if any(k in t for k in ["急促", "快速", "飞快", "狼狈"]):
                        rate = "+15%"
                    elif any(k in t for k in ["缓慢", "慢", "迟缓", "拖沓"]):
                        rate = "-15%"

                    # 音调（男性角色略低一些）
                    pitch = "+0Hz"
                    if voice == "zh-CN-YunxiNeural":
                        pitch = "-2Hz"

                    profile = {"voice": voice, "style": style, "rate": rate, "pitch": pitch}
                    # 只保留有设置的值，避免覆盖默认
                    return {k: v for k, v in profile.items() if v}

                for p_name, char in self.manager.game_state["long_term_memory"]["player_characters"].items():
                    # 自动为该角色生成 TTS 参数（用于后续自动 TTS 播报）
                    tts_profile = infer_tts_profile(char)
                    if tts_profile:
                        self.manager.engine.set_character_tts_profile(char.get("role_name", p_name), **tts_profile)

                    # 构建该玩家的人际关系部分
                    relationship_section = ""
                    player_rels = []

                    # 收集与该玩家相关的所有关系
                    for rel in all_relationships:
                        if rel['from'] == char['role_name'] or rel['to'] == char['role_name']:
                            other_person = rel['to'] if rel['from'] == char['role_name'] else rel['from']
                            direction = "你 → " if rel['from'] == char['role_name'] else "← "
                            status_icon = "🤝" if rel['status'] == "友好" else "⚔️" if rel['status'] == "敌对" else "❓"
                            player_rels.append(f"{direction}{other_person}: {rel['relation']} {status_icon}")

                    if player_rels:
                        relationship_section = f"🔗 **人际关系**：\n" + "\n".join(f"   - {r}" for r in player_rels) + "\n"
                    else:
                        relationship_section = "🔗 **人际关系**：暂无已知关系\n"

                    private_card = (
                        f"🎭 **【{char['role_name']}】角色文档**\n\n"
                        f"🔹 **身份**：{char['identity']}\n"
                        f"🔹 **公开人设**：{char['public_bio']}\n"
                        f"🔹 **背景故事**：{char['personal_bio']}\n"
                        f"{relationship_section}"
                        f"🤫 **核心秘密**：{char['secret']}\n"
                        f"🎯 **个人目标**：{char['goal']}\n"
                        f"📊 **初始属性**：{char['attributes']}"
                    )

                    # 尝试找到对应的 Discord 用户名
                    discord_username = p_name
                    for disc_name, role_name in player_mapping.items():
                        if role_name == char['role_name']:
                            discord_username = disc_name
                            break

                    # 发送私聊到Discord
                    await self.engine.send_to_person(discord_username, private_card, speaker="DM-bot")
                    print(f"📧 [Success] 已私信玩家: {discord_username} (角色: {char['role_name']})")

                    # 生成并发送头像到公共聊天框
                    await self._send_character_avatar_to_public(char)

                    # 发送角色卡到网页端（包含关系信息）
                    await self.engine.send_player_card({
                        "player_id": discord_username,
                        "role_name": char['role_name'],
                        "identity": char['identity'],
                        "public_bio": char['public_bio'],
                        "personal_bio": char['personal_bio'],
                        "relationships": player_rels,
                        "secret": char['secret'],
                        "goal": char['goal'],
                        "attributes": char['attributes']
                    })

                # --- 所有头像发送完成后，根据玩家数量决定是否播报自我介绍引导 ---
                player_count = self.manager.game_state.get("player_count", 0)
                if player_count > 1:
                    await self.engine.send_to_public(
                        "🎤 **现在请各位玩家依次自我介绍！**\n\n"
                        "介绍内容包括：你的角色名称、身份背景、以及你想让其他玩家了解的信息。\n"
                        "介绍完毕后，请点击下方的 **\"完成自我介绍\"** 按钮，等所有人都完成后游戏将正式开始。",
                        tts=True, speaker="DM-bot"
                    )
                    # 通知前端显示自我介绍界面
                    await self.engine.sio.emit('self_intro_start', {
                        "players": list(self.manager.game_state.get("player_mapping", {}).keys())
                    })
                    print(f"📢 [Introduction] 已发送自我介绍引导 ({player_count} 位玩家)")
                else:
                    print(f"📢 [Introduction] 单人模式，跳过自我介绍环节")

                # 2. 打印人物关系
                rels = extracted_memory.get("entities", {}).get("relationships", [])
                print(f"🔗 人际关系网 ({len(rels)} 条):")
                for rel in rels:
                    status_icon = "🤝" if rel['status'] == "友好" else "⚔️" if rel['status'] == "敌对" else "❓"
                    print(f"   - {rel['from']} {status_icon} {rel['to']}: {rel['relation']}")

                # 3. 打印物品归属
                items = extracted_memory.get("entities", {}).get("items", {})
                print(f"📦 关键物品持有情况:")
                for item_name, info in items.items():
                    print(f"   - [{item_name}] -> 持有者: {info.get('owner', '场景')}")

                print("="*52 + "\n")

        except Exception as e:
            print(f"⚠️ 提取长期记忆失败: {e}")

    async def _generate_deep_plot_inspection(self, initial_data):
        """调用 AI (如 DeepSeek) 进行深度剧情推演，生成导演视角的全局剧本"""

        try:
            # 1. 获取长期记忆数据
            long_term_memory = self.manager.game_state.get('long_term_memory', {})

            # 1.5. 提取玩家建议和角色偏好
            suggestions = self.manager.game_state.get("suggestions", [])
            role_prefs = self.manager.game_state.get("role_prefs", {})

            # 1.5. 规范化role_prefs,使用player_mapping中的标准player_id
            player_mapping = initial_data.get("player_mapping", [])
            normalized_role_prefs = {}

            for player_dict in player_mapping:
                player_id = player_dict.get("player_id", "")
                if not player_id:
                    continue

                # 尝试从role_prefs中找到匹配的偏好
                matched_pref = ""
                for key, value in role_prefs.items():
                    if player_id in key or key == player_id:
                        matched_pref = value
                        break

                # 使用标准的player_id作为键
                normalized_role_prefs[player_id] = matched_pref

            # 如果有玩家在role_prefs中但不在player_mapping中,也加入
            for key, value in role_prefs.items():
                already_matched = any(key in mapped_key or mapped_key in key
                                     for mapped_key in normalized_role_prefs.keys())
                if not already_matched:
                    normalized_role_prefs[key] = value

            role_prefs = normalized_role_prefs

            print("\n" + "="*80)
            print("📋 [Debug] 玩家输入信息")
            print("="*80)
            print(f"玩家建议(suggestions): {suggestions}")
            print(f"角色偏好(role_prefs): {role_prefs}")
            print(f"实际玩家列表: {[p.get('player_id') for p in player_mapping]}")

            # 2. 进行语义搜索
            print("\n🔍 [Plot Inspection] 正在检索文学参考资料...")
            search_engine = await get_search_engine()
            search_results = await search_engine.search_for_game_init(
                suggestions=suggestions if suggestions else ["奇幻冒险"],
                role_prefs=role_prefs,
                literature_top_k=5,
                highpoint_top_k=3
            )

            # 3. 格式化检索结果
            reference_text = search_engine.format_for_prompt(search_results)

            print("\n" + "="*80)
            print("📚 [Debug] 检索到的文学作品")
            print("="*80)
            for i, work in enumerate(search_results["literature_recommendations"], 1):
                print(f"{i}. 《{work['title']}》 - {work['author']} (相似度: {work['similarity_score']:.3f})")

            print("\n" + "="*80)
            print("✨ [Debug] 检索到的高光时刻")
            print("="*80)
            for player, highpoints in search_results["player_highpoints"].items():
                print(f"\n玩家 {player}:")
                for hp in highpoints:
                    print(f"  - [{hp['category']}] {hp['key']} (相似度: {hp['similarity_score']:.3f})")

            # 4. 构建增强版Prompt
            story_context = f"""
                你是一个富有人性理解和社会洞察的文学编剧。请基于以下已生成的角色扮演游戏开场数据，进行深度的剧情推演。

                【世界概况】: {long_term_memory.get('world_summary', '')}

                【公共背景】: {initial_data.get('public_story')}

                【玩家详细角色卡】: {json.dumps(long_term_memory.get('player_characters', {}), ensure_ascii=False)}

                【玩家关系】: {json.dumps(long_term_memory.get('player_relationships', []), ensure_ascii=False)}

                【NPC人物】: {json.dumps(long_term_memory.get('entities', {}).get('npc_characters', {}), ensure_ascii=False)}

                【人物关系】: {json.dumps(long_term_memory.get('entities', {}).get('relationships', []), ensure_ascii=False)}

                【关键物品】: {json.dumps(long_term_memory.get('entities', {}).get('items', {}), ensure_ascii=False)}

                【场景信息】: {json.dumps(long_term_memory.get('entities', {}).get('scenes', {}), ensure_ascii=False)}

                【当前场景】: {initial_data.get('scene')}

                【文学参考资料】(用于激发创作灵感，不要照搬):
                {reference_text}

                请根据以上信息进行深度思考，参考文学作品的经典手法和玩家期望的高光时刻，设计出精彩的剧情走向。

                # 叙事框架指引 (The Director's Vision)
                你将作为沉浸式 AI DM，游戏共20回合，请在设计剧情时遵循以下节奏：

                ## 回合节奏控制
                1. **R1-3 (入局)**: 制造悬念，引入危机。设定核心矛盾。
                2. **R4-10 (剥茧)**: 投放复杂线索，加深谜题。让玩家感受到信息的缺失。
                3. **R11-15 (变局)**: 剧情反转，必须迫使玩家做出道德/利益抉择。
                4. **R16-20 (破局)**: 收束线索，根据玩家过往选择判定结局。

                ## 叙事要求
                - **清晰叙述**: 用简洁直接的语言描述故事主干和关键事件，让玩家容易理解。
                - **互动友好**: NPC的反应要自然、易于理解，避免过于复杂或隐晦的心理分析。
                - **冲突驱动**: 确保 NPC 的反应带有明确的利益动机或情感冲动。
                - **规则判定**: 检查玩家行动是否符合物理逻辑及世界观禁忌。若违规，用平实的语言直接说明原因。

                ## 抉择设计原则
                为每个关键节点设计至少3种行动路径：
                - **[激进项]**: 高风险高回报的行动建议
                - **[稳健项]**: 侧重观察与分析的行动建议
                - **[博弈项]**: 涉及利用 NPC 关系或规则漏洞的建议

                严格按照以下 JSON 格式返回你的"导演手册"：
                {{
                    "main_line_logic": "核心冲突的本质是什么？（暗线真相）",
                    "possible_endings": [
                        {{ "ending_name": "结局 A", "condition": "触发条件", "description": "结局内容" }}
                    ],
                    "next_stage_hints": "下一阶段可能发生的三个关键反转点",
                    "npc_hidden_motives": {{ "重要NPC名": "他的真实目的和后手" }},
                    "player_highlight_moments": {{ "玩家名": "为该玩家预留的高光时刻设计" }},
                    "round_pacing": {{
                        "R1-3": "入局阶段的关键事件与悬念设计",
                        "R4-10": "剥茧阶段的线索投放计划",
                        "R11-15": "变局阶段的核心反转点",
                        "R16-20": "破局阶段的结局收束逻辑"
                    }},
                    "atmosphere_tags": ["回合1-5的氛围标签", "回合6-10的氛围标签", "..."],
                    "decision_checkpoints": [
                        {{ "round": 5, "decision_type": "激进/稳健/博弈", "description": "关键抉择点描述" }}
                    ]
                }}
            """

            # ===== 新增: 打印完整的Prompt =====
            print("\n" + "="*80)
            print("🤖 [Debug] 发送给 AI 的完整 Prompt")
            print("="*80)
            print("【System Instruction】:")
            system_instruction = "你是一个清晰的文学编剧，负责设计有趣的剧情走向和结局。用直接明了的方式为玩家设计专属的高光时刻，避免过于隐晦或故弄玄虚的表达。以json形式返回。"
            print(system_instruction)
            print("\n【User Prompt】:")
            print(story_context)
            print("="*80 + "\n")

            # ===== 尝试多次调用AI =====
            deep_plot = None
            models_to_try = ["deepseek-reasoner", "gpt-4o"]

            for attempt, model in enumerate(models_to_try, 1):
                try:
                    print(f"\n🎬 [Plot Inspection] 尝试 {model} (第{attempt}/{len(models_to_try)}次)...")

                    if model == "deepseek-reasoner":
                        inspection_str = await asyncio.wait_for(
                            ask_deepseek_async(
                                prompt_text=story_context,
                                system_instruction=system_instruction,
                                mode="json",
                                model="deepseek-reasoner"
                            ),
                            timeout=60.0
                        )
                    elif model == "gpt-4o":
                        inspection_str = await asyncio.wait_for(
                            ask_gpt_async(
                                prompt_text=story_context,
                                system_instruction=system_instruction,
                                model="gpt-4o",
                                mode="json",
                                temperature=0.1
                            ),
                            timeout=60.0
                        )
                    else:
                        continue

                    if inspection_str:
                        print("\n" + "="*80)
                        print(f"📥 [Debug] {model} 返回的原始结果")
                        print("="*80)
                        print(inspection_str[:500] + "..." if len(inspection_str) > 500 else inspection_str)
                        print("="*80 + "\n")

                        temp_plot = json.loads(inspection_str)

                        # 验证必需字段
                        required_fields = ["main_line_logic", "possible_endings", "round_pacing"]
                        if all(field in temp_plot for field in required_fields):
                            deep_plot = temp_plot
                            print(f"✅ [Plot] {model} 成功生成剧情推演！")
                            break
                        else:
                            print(f"⚠️ [Plot] {model} 返回结果缺少必需字段: {required_fields}")
                    else:
                        print(f"⚠️ [Plot] {model} 未返回有效结果")

                except json.JSONDecodeError as e:
                    print(f"⚠️ [Plot] {model} JSON解析失败: {e}")
                    continue
                except Exception as e:
                    print(f"⚠️ [Plot] {model} 调用失败: {e}")
                    continue

            # 如果所有模型都失败，抛出异常
            if deep_plot is None:
                raise Exception("所有模型均未能生成有效的剧情推演结果")

            # 附加检索到的参考资料
            deep_plot["_references"] = {
                "literature": search_results["literature_recommendations"],
                "highpoints": search_results["player_highpoints"]
            }

            # 覆盖原本简单的 plot_inspection，存入更深度的内容
            self.manager.game_state["plot_inspection"].update(deep_plot)

            print("🎭 [Plot] 深度剧情推演已入库（导演手册已就绪）")
            print(f"核心逻辑: {deep_plot.get('main_line_logic', 'N/A')[:50]}...")
            print(f"推演结局: {[e.get('ending_name') for e in deep_plot.get('possible_endings', [])]}")
            print(f"后续埋伏: {deep_plot.get('next_stage_hints', 'N/A')[:60]}...")
            print(f"参考作品: {len(search_results['literature_recommendations'])} 部")

            # 打印玩家高光时刻
            if "player_highlight_moments" in deep_plot:
                print("\n💫 [Plot] 为玩家设计的高光时刻:")
                for player, moment in deep_plot["player_highlight_moments"].items():
                    if isinstance(moment, str):
                        print(f"  - {player}: {moment[:60]}...")
                    else:
                        print(f"  - {player}: {moment}")

            print("🎬" + "·"*50 + "\n")

        except Exception as e:
            print(f"⚠️ 深度剧情推演失败: {e}")
            import traceback
            traceback.print_exc()

    async def _generate_opening_guidance(self, initial_data, rough_description):
        """
        生成游戏开场引导语，告诉玩家他们可以做什么、选择什么
        在所有角色卡发放完成后调用
        """
        try:
            long_term_memory = self.manager.game_state.get('long_term_memory', {})

            guidance_prompt = f"""
                你是一个角色扮演游戏的主持人，现在游戏刚刚开始，所有玩家已经收到了自己的角色卡。

                【当前游戏状态】:
                - 剧情简介: {rough_description}
                - 初始场景: {initial_data.get('scene', '未知场景')}
                - 时空背景: {long_term_memory.get('time_space', '未知')}
                - 玩家角色: {initial_data.get('player_mapping', [])}
                - 世界概况: {long_term_memory.get('world_summary', '')}

                【你的任务】:
                生成一段简短的**开场引导语**（150字以内），告诉玩家:
                1. 他们现在所处的具体场景（例如:你们站在废弃医院的门口/你们围坐在酒馆的圆桌前）
                2. 他们可以观察到什么（环境细节、NPC、物品等）
                3. 他们可以采取哪些行动（2-3个选项，用简洁的方式列出）

                【示例格式】:
                "你们站在废弃医院的锈蚀铁门前，门缝中透出微弱的绿光。远处传来机械运转的声音。
                你们可以：
                → 推开铁门直接进入
                → 绕到侧面寻找其他入口
                → 先观察周围环境，寻找线索"

                【输出要求】:
                - 直接输出引导语文本，不要包含任何 JSON 格式
                - 语言要简洁、生动、有画面感
                - 给玩家明确的行动选项，激发他们的参与感
                - 使用"你们"来称呼玩家
            """

            print("\n🎬 [Opening] 正在生成开场引导...")

            guidance_text = await asyncio.wait_for(
                ask_qwen_async(
                    prompt_text=guidance_prompt,
                    system_instruction="你是一个经验丰富的角色扮演游戏主持人，擅长用简洁生动的语言引导玩家进入游戏。",
                    mode="str",
                    model="qwen-plus",
                    temperature=0.3
                ),
                timeout=60.0
            )

            if guidance_text:
                print(f"✅ [Opening] 引导语生成成功")
                print(f"📝 [Opening] 内容: {guidance_text[:100]}...")

                # 发送到公共频道（带 TTS，不加标签前缀）
                await self.engine.send_to_public(guidance_text, tts=True, speaker="DM-bot")
            else:
                print("⚠️ [Opening] 引导语生成失败，跳过")

        except Exception as e:
            print(f"⚠️ 开场引导生成失败: {e}")
            import traceback
            traceback.print_exc()

    async def quick_private_chat(self, content, quick_public_answer, player_name):
        """被check_new_round唤醒的一个私聊功能"""

        long_term_memory=self.manager.game_state['long_term_memory']
        context=self.manager._build_context()
        user_input=f'''
            这是用户进行跑团的长期记录：{long_term_memory}
            这是最近次与用户的对话历史：{context}
            这是用户"{player_name}"的最新输入：{content}
            这是你之前在公聊频道已经发送出去的消息：{quick_public_answer}
            现在你要决定是否要私聊该用户，来进行某种回答。注意，私聊中仅能交流信息，不能推进任何剧情。
        '''

        system_prompt=f"""
            + 你是一个跑团机器人助手，面对一或多位玩家主持游戏
            + 用户{player_name}现在给出了一个可能需要私聊来回答的问题。请判断你是否可以回答这个问题（考虑你是否知道这个信息、用户是否有权知道该信息、是否会造成剧情泄密等），如果可以，请提供私聊回复内容。注意，私聊中仅能交流信息，不能推进任何剧情。
            + 请按照如下步骤进行回复：
                1. 判断该用户的最新输入是否需要私聊来解答，如果需要请在need_private_chat位置填写true，如果不需要私聊则填写false。
                2. 如果你认为需要私聊才能满足用户需求，请在private_chat_content位置填写私聊回复内容。
                3. 如果你认为你刚刚生成的私聊内容是恰当的，即确实是用户有权知道的、与游戏相关的信息，而不会造成剧情泄露，请在proper_to_send_private_chat位置填写true，否则填写false。
            + 请严格按照如下的json标准格式进行回复：
                {{
                    "need_private_chat": bool,
                    "private_chat_content": str,
                    "proper_to_send_private_chat": bool
                }}
        """

        try:
            result_str = await ask_qwen_async(prompt_text=user_input, system_instruction=system_prompt, mode="json", model="qwen-plus")
            if result_str:
                qwen_dict=json.loads(result_str)
                print(qwen_dict)
                need_private_chat=qwen_dict.get("need_private_chat", False)
                private_chat_content=qwen_dict.get("private_chat_content", "")
                proper_to_send_private_chat=qwen_dict.get("proper_to_send_private_chat", False)
                if need_private_chat and proper_to_send_private_chat:
                    await self.engine.send_to_person(player_name, private_chat_content, speaker="DM-bot")
            else:
                print("Qwen no response in quick_private_chat")
                qwen_dict={}

        except Exception as e:
            print(f"Qwen error: {e}")
            qwen_dict={}

    async def _generate_episode_response(self, chat_entry: dict):
        """
        第一部分：生成当前回合的公开响应和指令
        返回: (response, commands, private_messages, is_ending, ending_info)
        """
        long_term_memory = self.manager.game_state['long_term_memory']
        plot_inspection = self.manager.game_state['plot_inspection']
        context = self.manager._build_context()
        current_round = self.manager.game_state['round']
        total_rounds = self.manager.game_state['total_rounds']
        possible_endings = plot_inspection.get('possible_endings', [])

        reminder_text=""
        if 0<(total_rounds-current_round)<5:
            reminder_text=f"距离结局回合限制还有{total_rounds-current_round}回合，请尽快推进剧情结束游戏！"
            print(reminder_text)
        elif (total_rounds-current_round)<=0:
            reminder_text=f"游戏已经超时{current_round-total_rounds}个回合，请确保本回合或下个回合可以结束游戏！"
            print(reminder_text)
        
        # ===== 剧本模式（端午特辑等）：构建额外的剧情节点指引 =====
        festival_guidance = ""
        is_festival = plot_inspection.get("festival_mode", False)
        if is_festival:
            festival_graph = plot_inspection.get("festival_plot_graph", [])
            current_node_id = self.manager.game_state.get("festival_current_node", "")
            node_history = self.manager.game_state.get("festival_node_history", [])
            char_attrs = self.manager.game_state.get("character_attributes", {}).get("林墨", {})
            mechanics_checks = plot_inspection.get("mechanics_checks", [])

            # 找到当前节点详情
            current_node_info = "（未知节点）"
            next_candidates = []
            for node in festival_graph:
                if node.get("id") == current_node_id:
                    current_node_info = (
                        f"节点名称: {node.get('name', '?')}\n"
                        f"场景描述: {node.get('scene', '?')}\n"
                        f"AI指引: {node.get('guide', '?')}\n"
                        f"提供给玩家的选项: {list(node.get('choices', {}).keys())}"
                    )
                    next_candidates = list(node.get("choices", {}).keys())
                    break

            festival_guidance = f"""
        【⚠️ 剧本模式 - 必须严格遵守以下规则】:
        当前剧本: 端午到，龙舟跑
        已走过的节点: {node_history}
        当前所在节点: {current_node_info}
        玩家属性: 因果值={char_attrs.get('因果值', 0)}, 热情值={char_attrs.get('热情值', 0)}, 洞察值={char_attrs.get('洞察值', 0)}, 龙舟队鼓手={char_attrs.get('龙舟队鼓手', 0)}, 长命缕={'佩戴' if char_attrs.get('长命缕', 0) == 1 else '未佩戴'}
        
        【强制要求 - 不遵守则游戏出错】:
        1. 你的DM_response必须基于当前场景描述展开，不要跳到其他场景
        2. 你必须在DM_response末尾给出下一轮的行动选项，选项应该引导玩家走向剧本预设的分支
        3. 如果玩家选择了某个分支选项，请在commands中通过"update_festival_node"指令更新当前节点
        4. 如果玩家行为触发了检定机制，请在commands中通过"festival_check"指令发起检定
        5. 每轮结束后，根据玩家选择更新角色属性值（因果值/热情值/洞察值），在commands中使用"update_attribute"指令
        6. 不要跳过剧情节点！确保每个节点都被玩家经历过后再进入下一个

        【检定机制参考】:
        {json.dumps(mechanics_checks[:3], ensure_ascii=False) if mechanics_checks else '无'}
        """

        prompt_text = f'''
        请根据以下信息，生成当前回合的DM响应。
            长期记忆：{long_term_memory}
            上下文：{context}
            最新聊天：{chat_entry}
            剧情监控：{plot_inspection}
            可用结局列表：{possible_endings}
        {festival_guidance}
        {reminder_text}
        请按照如下步骤分析：
            1. **结局判定**：检查当前情况是否满足某个结局条件。检查顺序：
                a. 是否触发了某个结局的condition条件
                b. 是否到达了总回合数限制（当前{current_round}/{total_rounds}回合）
                c. 是否出现关键剧情节点（如真相揭露、最终决战、核心矛盾解决等）
                d. 玩家主动要求提前结局
            2. 如果满足结局条件：
                - 在is_ending位置填写true
                - 在ending_info位置填写触发的结局信息，包括ending_name和description
                - 在DM_response位置填写结局宣布文本，告知玩家到达了什么结局
                - commands和private_messages保持为空
                - 直接跳过后续分析步骤
            3. 如果未满足结局条件：
                - 在is_ending位置填写false
                - 在ending_info位置填写null
                - 对玩家行为进行分析，分析其是否符合之前剧情监控中所预测的故事走向，写在analysis位置
                - 评估每位玩家的当前状态（位置、情绪、身体状况、人际关系变化、目标进展），写在player_status位置
                - 遵循之前的剧情监控和长期记忆等信息，分析接下来发生的事件，写在following_events位置。尽量按照剧情监控中的预设逻辑展开，如非必要，不要增加新的人物、地点或物品。如果当前剧情进展过慢，可以适当加速推进。
                - 写出DM的公开主持词，写在DM_response位置（简洁、直接、清晰），让玩家看到自己可以采取行动的对象（例如你们面前有什么、谁在朝你们走来等等），确保你给玩家的各种选项有助于剧情按照剧情监控中的提示展开。如果有必要，可以操控npc进行互动。请确保该文本可以直接被朗读。由于你正面对一或多位玩家主持游戏，使用用户的"角色名字+(账号名)"来称呼用户。
                - **重要：必须在DM_response末尾添加2-4个明确的行动选项**，用"→ "开头（例如：→ 上前与神秘人交谈\n→ 悄悄绕到建筑后方\n→ 先观察四周环境），让玩家可以直接选择而无需自己构思。选项应覆盖激进、稳健、博弈三种风格。
                - 如需私信玩家，在private_messages中编写。可以提示玩家可以采取哪些下一轮的行动。仅在必要的触发条件下，告知玩家一些理应他知晓而其他人不知晓的信息。避免引入过多的剧情细节，以免剧情过度复杂。如没有私信必要，留空即可。
                - 如需执行特殊的命令，在commands中编写。例如如果玩家来到了新的场景，请进行必要的场景切换。

        【结局判定原则】
        - 只有在真正抵达结局节点时才触发结局，不要在剧情中期过早结束
        - 如果到达回合上限但尚未满足任何结局条件，应根据玩家表现选择最接近的结局或生成自然结局
        - 结局宣布后，不再发送任何后续剧情推演内容

        以下是private_messages格式：{prompts.PRIVATE_CHAT_DESCRIPTION}
        以下是可用command及其格式：{prompts.COMMANDS_DESCRIPTION}

        请按以下json格式回答：
            {{
                "is_ending": bool,
                "ending_info": {{
                    "ending_name": str,
                    "description": str
                }},
                "analysis": str,
                "player_status": {{
                    "玩家角色名": {{
                        "location": "当前位置",
                        "mood": "情绪状态",
                        "health": "身体状况",
                        "goal_progress": "目标进展"
                    }}
                }},
                "following_events": str,
                "DM_response": str,
                "private_messages": list[dict],
                "commands": list[dict]
            }}'''

        system_instruction = "你是专业的跑团DM主持人，面对一位或多位玩家，合理推进剧情，确保连贯性和体验。在关键时刻准确判断结局条件。"

        typing_gen = self.engine.typing()
        await typing_gen.__anext__()

        response_str = await ask_qwen_async(
            prompt_text=prompt_text,
            system_instruction=system_instruction,
            model="deepseek-v3",
            mode="json",
            temperature=0.1
        )

        await typing_gen.aclose()

        response_dict = {}
        response = ""
        commands = []
        private_messages = []
        is_ending = False
        ending_info = None

        dict_list = get_dict_from_str(response_str)
        if dict_list:
            response_dict = dict_list[0]
            print(f"📝 [Episode] AI响应: {response_dict}")

            is_ending = response_dict.get("is_ending", False)
            ending_info = response_dict.get("ending_info")
            response = response_dict.get("DM_response", "")
            commands = response_dict.get("commands", [])
            private_messages = response_dict.get("private_messages", [])

        return response, commands, private_messages, is_ending, ending_info

    async def _update_long_term_memory(self, chat_entry: dict, episode_result: dict, model_used: str = "", retry_count: int = 0):
        """
        第二部分：根据第一部分的结果，更新长期记忆和剧情监控
        使用多模型并发请求，哪个先响应就使用哪个。支持失败重试。

        参数:
            chat_entry: 用户聊天记录
            episode_result: 上一回合处理结果
            model_used: 指定使用的模型（"gpt-4o" / "deepseek-reasoner" / "qwen3-max"），
                        如果为 None 则并发请求所有模型，使用最先响应的
            retry_count: 当前重试次数（内部使用）
        """
        MAX_RETRIES = 2
        
        long_term_memory = self.manager.game_state['long_term_memory']
        plot_inspection = self.manager.game_state['plot_inspection']
        context = self.manager._build_context()
        current_round = self.manager.game_state['round']
        total_rounds = self.manager.game_state['total_rounds']

        # 根据当前轮次生成节奏提示
        round_phase_hint = ""
        if current_round <= 3:
            round_phase_hint = "当前处于【入局阶段】，请重点记录角色登场、初始关系和世界观的建立。"
        elif current_round <= 10:
            round_phase_hint = "当前处于【剥茧阶段】，请重点记录线索发现、谜题展开和NPC关系的深化。"
        elif current_round <= 15:
            round_phase_hint = "当前处于【变局阶段】，请重点记录剧情反转、角色抉择和矛盾激化。"
        else:
            round_phase_hint = "当前处于【破局阶段】，请重点记录结局推进、真相揭露和最终选择。"

        prompt_text = f'''
        请根据以下信息更新长期记忆和剧情监控。

            当前长期记忆（long_term_memory）：{long_term_memory}
            当前剧情监控（plot_inspection）：{plot_inspection}
            当前已经到达了轮次：{current_round}/{total_rounds}
            上下文：{context}
            上一回合用户的行动：{chat_entry}
            上一回合你对于用户行为已经作出的回应：{episode_result}
            {round_phase_hint}

        请按以下步骤：
            1. 分析需要更新哪些长期记忆，比如物品所有权的转移、人物身体状况和人物关系的变化、npc对于玩家的关于和态度的改变等，在long_term_memory_modify_plan位置写出计划。
            2. 写出更新后的长期记忆，在原有的基础上根据情节发展情况进行必要的记录，不可以删掉任何已经存在的人和物品，写在long_term_memory位置。
            3. 思考剧情走向是否需要调整，在plot_inspection_modify_plan位置写出分析。注意：
                + 仅对未来的可能情况进行必要的调整和节奏把控
                + 不能更改任何已经向用户传达过的事实
                + 尽量不要删去已有的情节，围绕主线
            4. 写出更新后的剧情监控，记录整体剧情的构想、当前剧情的进度、后续预计的发展可能性以及用户在下一轮可能面临的典型选择和可能的结果，在原有的剧情监控上进行调整，写在plot_inspection位置（如无需调整则重复）。如果当前剧情进度过慢，可以考虑设计加速剧情推进的改动，并在plot_inspection_modify_plan中写出调整的理由。
            5. 你生成的新字典会被用来update之前的字典，因此如果要删除原来字典中的某些键值对，请在返回的字典中给出这些键，并将其值设为空。
            6. 请在player_status位置总结每位玩家的当前状态（如位置、情绪、身体状况、目标进展等）。

        请按以下json格式回答（确保 long_term_memory 和 plot_inspection 都是有效的JSON对象，不能为null或空字符串）：
            {{
                "long_term_memory_modify_plan": str,
                "long_term_memory": {{}},
                "plot_inspection_modify_plan": str,
                "plot_inspection": {{}},
                "player_status": {{}}
            }}
        '''

        system_instruction = "你是专业的DM，合理更新记忆和剧情监控。必须以标准JSON格式回答问题，long_term_memory和plot_inspection字段必须是有效对象。"

        async def _try_parse_response(result_str, model_name):
            """尝试解析单个模型的响应，返回 (memory_dict, None) 或 (None, error_msg)"""
            if not result_str or not isinstance(result_str, str):
                return None, f"响应为空或类型错误"
            
            temp_str = result_str.strip()
            if not temp_str:
                return None, f"响应为空字符串"
            
            # 尝试多种解析方式
            temp_dict_list = get_dict_from_str(temp_str)
            
            if not temp_dict_list:
                # 尝试直接 json.loads
                try:
                    direct_dict = json.loads(temp_str)
                    if isinstance(direct_dict, dict):
                        temp_dict_list = [direct_dict]
                except:
                    pass
            
            if not temp_dict_list or len(temp_dict_list) == 0:
                # 最后尝试：查找 JSON 块
                import re
                json_match = re.search(r'\{[^{}]*"long_term_memory"[^{}]*\}', temp_str, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        if isinstance(parsed, dict):
                            temp_dict_list = [parsed]
                    except:
                        pass
            
            if not temp_dict_list or len(temp_dict_list) == 0:
                return None, f"JSON解析失败（原始响应前200字: {temp_str[:200]}）"
            
            temp_dict = temp_dict_list[0]
            if not isinstance(temp_dict, dict) or not temp_dict:
                return None, f"解析结果不是有效字典"
            
            # 验证关键字段
            new_memory = temp_dict.get("long_term_memory")
            new_plot = temp_dict.get("plot_inspection")
            
            if not isinstance(new_memory, dict) or not new_memory:
                print(f"🧠 [Memory] {model_name} long_term_memory 无效: {type(new_memory)}")
                # 不立即拒绝，检查 plot_inspection 是否有效
            if not isinstance(new_plot, dict) or not new_plot:
                print(f"🧠 [Memory] {model_name} plot_inspection 无效: {type(new_plot)}")
            
            # 只要至少有一个字段有效就接受
            if (isinstance(new_memory, dict) and new_memory) or (isinstance(new_plot, dict) and new_plot):
                return temp_dict, None
            
            return None, f"两个关键字段都无效"
        
        # 根据 model_used 决定是单模型还是多模型并发请求
        try:
            model_tasks = {}

            if model_used:
                # 指定模型：只尝试该模型
                print(f"🧠 [Memory] 指定模型: {model_used}")
                if model_used == "gpt-4o":
                    model_tasks[model_used] = asyncio.create_task(
                        ask_gpt_async(prompt_text, [], system_instruction, model="gpt-4o", mode="json", temperature=0.1)
                    )
                elif model_used == "deepseek-reasoner":
                    model_tasks[model_used] = asyncio.create_task(
                        ask_deepseek_async(prompt_text, system_instruction, mode="json", model="deepseek-reasoner")
                    )
                else:
                    model_tasks[model_used] = asyncio.create_task(
                        ask_qwen_async(prompt_text, [], system_instruction, model=model_used, mode="json", temperature=0.1)
                    )
            else:
                # 未指定模型：多模型并发请求，哪个先响应就使用哪个
                model_tasks = {
                    "gpt-4o": asyncio.create_task(ask_gpt_async(prompt_text, [], system_instruction, model="gpt-4o", mode="json", temperature=0.1)),
                    "deepseek-reasoner": asyncio.create_task(ask_deepseek_async(prompt_text, system_instruction, mode="json", model="deepseek-reasoner")),
                    "qwen3-max": asyncio.create_task(ask_qwen_async(prompt_text, [], system_instruction, model="qwen3-max", mode="json", temperature=0.1))
                }
                print(f"🧠 [Memory] 发起多模型并发请求: {list(model_tasks.keys())}")

            # 使用 asyncio.wait 等待所有任务完成（因为需要遍历所有找到有效结果）
            done_set, pending_tasks = await asyncio.wait(
                set(model_tasks.values()),
                return_when=asyncio.FIRST_COMPLETED,
                timeout=30  # 30秒超时
            )

            # 找出第一个有效的结果
            memory_dict = None
            winning_model = None
            
            # 先检查已完成的任务
            for model_name, task in model_tasks.items():
                if task in done_set:
                    try:
                        result = task.result()
                        parsed, error = await _try_parse_response(result, model_name)
                        if parsed is not None:
                            memory_dict = parsed
                            winning_model = model_name
                            break
                        else:
                            print(f"🧠 [Memory] {model_name} 解析失败: {error}")
                    except asyncio.TimeoutError:
                        print(f"🧠 [Memory] {model_name} 任务超时")
                        continue
                    except Exception as e:
                        print(f"🧠 [Memory] {model_name} 任务异常: {e}")
                        continue

            # 如果第一个完成的任务无效，等待其他任务
            if not memory_dict:
                # 再等待剩余任务（总共再等最多20秒）
                if pending_tasks:
                    try:
                        more_done, still_pending = await asyncio.wait(
                            pending_tasks,
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=20
                        )
                        for model_name, task in model_tasks.items():
                            if task in more_done and not memory_dict:
                                try:
                                    result = task.result()
                                    parsed, error = await _try_parse_response(result, model_name)
                                    if parsed is not None:
                                        memory_dict = parsed
                                        winning_model = model_name
                                        break
                                    else:
                                        print(f"🧠 [Memory] {model_name} 第二轮解析失败: {error}")
                                except Exception as e:
                                    print(f"🧠 [Memory] {model_name} 第二轮异常: {e}")
                    except asyncio.TimeoutError:
                        print(f"🧠 [Memory] 等待额外任务超时")

            # 取消所有未完成的任务
            for task in pending_tasks:
                if not task.done():
                    task.cancel()

            if not memory_dict:
                # 所有模型都失败了，尝试重试
                if retry_count < MAX_RETRIES:
                    print(f"🧠 [Memory] ⚠️ 所有模型都失败，第{retry_count + 1}次重试...")
                    await asyncio.sleep(2)  # 等待2秒再重试
                    return await self._update_long_term_memory(chat_entry, episode_result, model_used="qwen3-max", retry_count=retry_count + 1)
                else:
                    # 最终失败，做最小化更新（只记录本轮关键信息）
                    print(f"🧠 [Memory] ❌ 已达最大重试次数，执行最小化记忆更新")
                    self._minimal_memory_update(chat_entry, episode_result)
                    return

            print(f"🧠 [Memory] 🏆 {winning_model} 最先有效响应！")

            # 数据已通过验证，直接更新
            new_memory = memory_dict.get("long_term_memory")
            new_plot = memory_dict.get("plot_inspection")

            if new_memory and isinstance(new_memory, dict):
                self.manager.game_state["long_term_memory"].update(new_memory)
                print(f"🧠 [Memory] 长期记忆已更新 (来源: {winning_model})")

            if new_plot and isinstance(new_plot, dict):
                self.manager.game_state["plot_inspection"].update(new_plot)
                print(f"🧠 [Plot] 剧情监控已更新 (来源: {winning_model})")

            # 保存当前游戏状态到Temp文件夹
            self._save_game_state_to_temp()

        except Exception as e:
            print(f"❌ [Memory] 多模型请求失败: {e}")
            import traceback
            traceback.print_exc()
            # 即使出错也尝试最小化更新
            if retry_count < MAX_RETRIES:
                print(f"🧠 [Memory] ⚠️ 异常后重试，第{retry_count + 1}次...")
                await asyncio.sleep(2)
                await self._update_long_term_memory(chat_entry, episode_result, model_used="qwen3-max", retry_count=retry_count + 1)
            else:
                self._minimal_memory_update(chat_entry, episode_result)

    def _minimal_memory_update(self, chat_entry: dict, episode_result: dict):
        """最小化记忆更新：当所有AI调用都失败时的降级方案"""
        try:
            # 记录本轮对话摘要到长期记忆
            player_name = chat_entry.get("player", "未知玩家")
            content = chat_entry.get("content", "")
            round_num = self.manager.game_state.get("round", 0)
            
            # 在长期记忆中记录本轮的基本信息
            if "round_history" not in self.manager.game_state["long_term_memory"]:
                self.manager.game_state["long_term_memory"]["round_history"] = []
            
            self.manager.game_state["long_term_memory"]["round_history"].append({
                "round": round_num,
                "player": player_name,
                "action_summary": content[:200] if content else "无操作",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            
            # 限制历史记录长度
            if len(self.manager.game_state["long_term_memory"]["round_history"]) > 50:
                self.manager.game_state["long_term_memory"]["round_history"] = \
                    self.manager.game_state["long_term_memory"]["round_history"][-50:]
            
            # 尝试保存
            self._save_game_state_to_temp()
            print(f"📝 [Memory] 最小化更新完成（已记录第{round_num}轮摘要）")
        except Exception as e:
            print(f"❌ [Memory] 最小化更新也失败了: {e}")

    async def push_new_round(self, chat_entry: dict):
        """
        推进对新轮次的处理（主流程）
        步骤：1.生成回合响应 → 2.检查结局 → 3.发送消息 → 4.更新长期记忆（后台）
        """
        current_round = self.manager.game_state['round']
        total_rounds = self.manager.game_state['total_rounds']
        
        # 步骤0：强制结局检查（如果已超回合数）
        if current_round >= total_rounds:
            print(f"🏁 [Round] 已达到回合上限 ({current_round}/{total_rounds})，强制触发结局")
            await self.ending_preparation({
                "ending_name": "命运之终",
                "description": f"经过{current_round}轮的冒险，你们的故事走到了尽头。无论是否达成了目标，这段旅程中的每一个选择都铸就了你们的命运。"
            })
            await asyncio.sleep(2)
            await self.ending_summary()
            return
        
        # 步骤1：生成回合响应
        print(f"\n🔄 [第{current_round}轮] 开始生成回合响应...")
        response, commands, private_messages, is_ending, ending_info = await self._generate_episode_response(chat_entry)

        # 步骤2：检查是否触发结局
        if is_ending and ending_info:
            print(f"🏁 [Round] 检测到结局触发！")
            # 执行结局准备流程
            await self.ending_preparation(ending_info)
            # 生成并发送结局总结
            await asyncio.sleep(2)  # 给玩家一点时间消化结局
            await self.ending_summary()
            # 结局处理完成，不再继续正常流程
            return

        # 步骤3：发送DM响应
        if response:
            await self.engine.send_to_public(response, tts=True, speaker="DM-bot")

        # 步骤3.5：回合变更通知 + 新回合背景图生成
        # 关键：必须用当前回合DM响应纯叙述文本（去除选项）确保图文匹配
        scene_name = self.manager.game_state.get("scene", "未知场景")
        # 从response中提取纯叙述部分：裁掉末尾的"→ 选项"部分
        raw_desc = response or ""
        option_idx = raw_desc.find("\n→ ")
        if option_idx > 0:
            raw_desc = raw_desc[:option_idx]
        scene_desc = raw_desc.strip()[:300]
        # 检查是否有 change_scene 指令（会由 _execute_ai_action 统一触发生成）
        has_scene_change = any(cmd.get("type") == "change_scene" for cmd in (commands or []))
        if has_scene_change:
            # 有场景切换指令时，从指令中提取新场景信息并更新 game_state
            # 背景图由 _execute_ai_action -> update_scene 统一生成
            for cmd in (commands or []):
                if cmd.get("type") == "change_scene":
                    p = cmd.get("params", {})
                    scene_name = p.get("name", scene_name)
                    scene_desc = p.get("description", "")[:300] or scene_desc
                    break
        # 兜底
        if not scene_desc:
            scene_desc = self.manager.game_state.get("scene_description", "")
        # 发送回合变更事件给前端（含场景信息，前端据此切换BGM和背景）
        if hasattr(self.engine, 'send_round_change'):
            await self.engine.send_round_change(current_round, total_rounds, scene_name, scene_desc)
        # 异步生成新回合背景图（仅在无场景切换时生成，有切换则由 change_scene 指令触发）
        if hasattr(self.engine, '_generate_and_send_scene_image') and not has_scene_change:
            asyncio.create_task(self.engine._generate_and_send_scene_image(scene_name, scene_desc))

        # 步骤4：发送私信
        if private_messages:
            for private_message in private_messages:
                await self._process_private_message(private_message)

        # 步骤5：执行AI指令
        if commands:
            for command in commands:
                await self.manager._execute_ai_action(command)

        # 步骤6：后台异步更新长期记忆和剧情监控（不阻塞）
        # 使用多模型竞速策略，提高成功率
        episode_result = {
            "analysis": response[:500] if response else "已处理回合",
            "following_events": "已记录事件"
        }
        asyncio.create_task(self._update_long_term_memory(chat_entry, episode_result, model_used=""))

        print(f"✅ [第{current_round}轮] 完成（记忆后台更新中）\n")

    async def _process_private_message(self, private_message: dict):
        """处理标准化的私信字典"""
        player_id = private_message.get("player_id")
        message_content = private_message.get("message", "")

        print(f"🔍 私信发送: player_id={player_id}, message={message_content}")

        if player_id and message_content:
            await self.engine.send_to_person(player_id, message_content, speaker="DM-bot")
        else:
            print(f"❌ 私信数据不完整: {private_message}")

    async def ending_preparation(self, ending_info: dict):
        """
        结局准备函数：处理结局触发后的逻辑
        Args:
            ending_info: 包含ending_name和description的字典
        """
        try:
            ending_name = ending_info.get("ending_name", "未知结局")
            ending_description = ending_info.get("description", "")

            print(f"\n🏁 [Ending] 触发结局: {ending_name}")
            print(f"📜 [Ending] 结局描述: {ending_description}")

            # 标记游戏已结束
            self.manager.game_state["is_ended"] = True
            self.manager.game_state["ending_name"] = ending_name

            # 发送结局宣布到公共频道（简洁版）
            await self.engine.send_to_public(
                f"🎭 **【游戏结束】**\n\n"
                f"你们到达了结局：**{ending_name}**\n\n"
                f"📖 {ending_description}",
                tts=False,
                speaker="DM-bot"
            )

            print(f"✅ [Ending] 结局宣布已发送")

        except Exception as e:
            print(f"❌ [Ending] 结局准备失败: {e}")
            import traceback
            traceback.print_exc()

    async def ending_summary(self):
        """
        结局总结功能：为玩家生成回顾和总结
        包括：故事主线回顾、关键决策节点、玩家表现、最终结局解释
        同时生成结构化卡片数据，通过 game_ending 事件发送给前端渲染精美结局卡片
        """
        try:
            print("\n📚 [Summary] 开始生成结局总结...")

            long_term_memory = self.manager.game_state.get('long_term_memory', {})
            plot_inspection = self.manager.game_state.get('plot_inspection', {})
            chat_history = self.manager.game_state.get('chat_history', [])
            ending_name = self.manager.game_state.get('ending_name', '未知结局')
            current_round = self.manager.game_state.get('round', 0)
            total_rounds = self.manager.game_state.get('total_rounds', 20)

            # 获取所有玩家角色信息
            player_characters = long_term_memory.get('player_characters', {})
            # 收集玩家名列表（用于卡片）
            player_names = list(player_characters.keys())

            # 游戏完成时间
            complete_time = time.strftime("%Y-%m-%d %H:%M:%S")
            game_start_time_display = self.game_start_time or "未知"
            # 格式化游戏开始时间（从 YYYYMMDD_HHMMSS 转为可读格式）
            if self.game_start_time and len(self.game_start_time) == 15:
                try:
                    gst = self.game_start_time
                    game_start_time_display = f"{gst[:4]}-{gst[4:6]}-{gst[6:8]} {gst[9:11]}:{gst[11:13]}:{gst[13:15]}"
                except:
                    pass

            # ========== 第一步：生成文本总结 ==========
            summary_prompt = f'''
                你是一位经验丰富的角色扮演游戏主持人，现在游戏已经结束，需要为玩家生成一份精彩的冒险总结回顾。

                【游戏基本信息】:
                - 结局名称: {ending_name}
                - 持续回合: {current_round}/{total_rounds}
                - 参与玩家: {player_names}

                【玩家角色信息】: {player_characters}

                【长期记忆】: {long_term_memory}

                【剧情监控】: {plot_inspection}

                【聊天历史（最近20条）】: {chat_history[-20:]}

                请按照以下结构生成一份精简的结局总结（直接输出文本，不要JSON格式）：

                📖 **{ending_name}**

                简述整个冒险的结局，包含故事主线、关键转折点和角色命运，给玩家一个温暖而有力的告别。

                要求：
                - 语言生动简洁，有沉浸感
                - 直接进入主题，不要问候语和开场白
                - **字数严格控制在200字以内**
                - 以一句简洁的告别语结束，如"感谢各位冒险者"
            '''

            print("📝 [Summary] 正在请求AI生成总结...")

            summary_text = await ask_qwen_async(
                prompt_text=summary_prompt,
                system_instruction="你是一位温暖而专业的角色扮演游戏主持人，擅长为玩家创作深刻的冒险总结和回忆。",
                mode="str",
                model="qwen-plus",
                temperature=0.7
            )

            # ========== 第二步：生成卡片结构化数据 ==========
            card_data = None
            card_prompt = f'''
                你是一位角色扮演游戏的数据整理助手。请根据以下游戏信息，输出一份JSON格式的结局卡片数据。

                【游戏信息】:
                - 结局名称: {ending_name}
                - 持续回合: {current_round}/{total_rounds}
                - 参与玩家: {player_names}
                - 玩家角色信息: {player_characters}

                【长期记忆】: {long_term_memory}

                【剧情监控】: {plot_inspection}

                【已生成的总结文本（参考）】: {summary_text[:500] if summary_text else "无"}

                请严格按照以下JSON格式输出（只输出JSON，不要其他内容）：

                {{
                    "ending_name": "结局名称（简洁，不超过15字）",
                    "story_ending": "故事结局简述（1-2句话，概括最终结局，不超过80字）",
                    "character_fates": [
                        {{"player": "玩家名", "role": "角色名", "fate": "角色命运简述（不超过30字）"}}
                    ],
                    "epilogue": "一段温暖的告别语（不超过60字）"
                }}

                要求：
                - 只输出JSON，不要任何其他文字
                - 结局名称要简洁有力
                - 故事结局要能打动人心
                - 角色命运要针对每位玩家
            '''

            try:
                print("🃏 [Summary] 正在生成卡片数据...")
                card_result = await ask_qwen_async(
                    prompt_text=card_prompt,
                    system_instruction="你是一个数据整理助手，只输出JSON格式的数据，不输出任何其他内容。",
                    mode="str",
                    model="qwen-plus",
                    temperature=0.3
                )
                if card_result:
                    card_data = get_dict_from_str(card_result)
                    print(f"✅ [Summary] 卡片数据生成成功: {card_data}")
            except Exception as ce:
                print(f"⚠️ [Summary] 卡片数据生成失败（不影响主流程）: {ce}")
                card_data = None

            # 如果卡片数据生成失败，构建一个基本版本
            if not card_data:
                card_data = {
                    "ending_name": ending_name,
                    "story_ending": f"经历了{current_round}轮的冒险，你们的故事在{ending_name}中画上了句号。",
                    "character_fates": [
                        {"player": pname, "role": pdata.get("role_name", pname), "fate": "命运之轮已停止转动。"}
                        for pname, pdata in player_characters.items()
                    ],
                    "epilogue": "感谢各位玩家的精彩冒险！"
                }

            # 组装完整的卡片数据（补充系统级字段）
            full_card_data = {
                "ending_name": card_data.get("ending_name", ending_name),
                "story_ending": card_data.get("story_ending", ""),
                "character_fates": card_data.get("character_fates", []),
                "epilogue": card_data.get("epilogue", "感谢各位玩家的精彩冒险！"),
                "players": player_names,
                "game_rounds": f"{current_round}/{total_rounds}",
                "complete_time": complete_time,
                "game_start_time": game_start_time_display,
                "game_name": self.game_short_name or "未知冒险",
            }

            # ========== 第三步：生成结局卡片图片（AI 文生图） ==========
            card_image_url = None
            try:
                print("🎨 [Summary] 正在生成结局卡片图片...")
                # 构建角色命运文本（用于嵌入到图片提示词中）
                fates_text = ""
                for cf in full_card_data.get("character_fates", []):
                    role = cf.get("role", cf.get("player", ""))
                    fate = cf.get("fate", "")
                    fates_text += f"• {role}：{fate}\n"

                image_prompt = (
                    f"精美游戏结局卡片设计，竖版正方形布局，深色羊皮纸纹理背景，"
                    f"带有哥特式金色边框和装饰花纹。"
                    f"卡片顶部居中位置用优雅哥特式大字体写标题：【{full_card_data['ending_name']}】。"
                    f"标题下方是一行小字：{'、'.join(player_names[:4])} 的冒险。"
                    f"卡片中间主体区域左侧用清晰字体列出角色命运：\n{fates_text}"
                    f"卡片右下角写故事概要：{full_card_data['story_ending']}。"
                    f"卡片底部居中写告别语：{full_card_data['epilogue']}。"
                    f"整体风格：魔幻史诗、复古中世纪卷轴、烛光色调、神秘氛围、"
                    f"暗金与深蓝配色、高清精细纹理、文字清晰可读、无中文乱码、"
                    f"画面干净整洁、文字排版工整、留白适当。"
                    f"图片规格：正方形 1:1 比例，1024x1024 像素，"
                    f"适合打印和保存。禁止出现模糊、杂乱、扭曲的文字。"
                )

                card_image_url = await generate_image_url_async(
                    prompt_text=image_prompt,
                    size="1024*1024"
                )
                if card_image_url:
                    print(f"✅ [Summary] 结局卡片图片生成成功: {card_image_url[:80]}...")
                    full_card_data["image_url"] = card_image_url
                else:
                    print("⚠️ [Summary] 结局卡片图片生成失败（不影响主流程）")
            except Exception as ie:
                print(f"⚠️ [Summary] 结局卡片图片生成异常（不影响主流程）: {ie}")

            # 无论总结文本是否生成成功，都发送结局卡片给前端
            if summary_text:
                print(f"✅ [Summary] 总结生成成功，长度: {len(summary_text)} 字符")
            else:
                print("⚠️ [Summary] 总结文本生成失败，使用 fallback 数据发送结局卡片")

            # 直接发送结局卡片（图片+数据），不再发送大段文字
            if hasattr(self.engine, 'send_game_ending'):
                await self.engine.send_game_ending(full_card_data)
                print("🃏 [Summary] 结局卡片数据已发送给前端")

            print(f"✅ [Summary] 结局总结已发送给玩家")

            # 保存最终游戏状态到Temp文件夹
            self._save_game_state_to_temp()
            print(f"💾 [Summary] 最终游戏状态已保存")

            # 保存总结文本到Temp文件夹（如果有的话）
            if summary_text:
                summary_file = os.path.join(self.temp_dir, f"ending_summary_{time.strftime('%Y%m%d_%H%M%S')}.txt")
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write(f"游戏结束时间: {complete_time}\n")
                    f.write(f"游戏开始时间: {game_start_time_display}\n")
                    f.write(f"结局: {ending_name}\n")
                    f.write(f"持续回合: {current_round}/{total_rounds}\n")
                    f.write(f"{'='*60}\n\n")
                    f.write(summary_text)
                print(f"💾 [Summary] 总结文本已保存: {summary_file}")

        except Exception as e:
            print(f"❌ [Summary] 结局总结失败: {e}")
            import traceback
            traceback.print_exc()

    async def _send_character_avatar_to_public(self, char: dict):
        """为玩家角色生成头像并发送到公共聊天框（带缓存）"""
        try:
            from image_cache import (
                avatar_cache_exists, avatar_cache_path,
                download_and_cache, save_character_visual,
                build_character_visual_desc, cached_file_base64,
            )

            role_name = char['role_name']
            identity = char['identity']
            public_bio = char['public_bio']
            scenario_name = self.game_short_name or "default"

            # 1. 先检查本地缓存
            if avatar_cache_exists(role_name, scenario_name):
                print(f"📦 [Avatar] 使用本地缓存的头像: {role_name}")
                cache_path = avatar_cache_path(role_name, scenario_name)
                # 使用现有的 send_avatar_to_public，兼容 Discord/Web 双端
                await self.engine.send_avatar_to_public(role_name, cache_path)
                return

            # 构建头像生成提示词
            prompt = f"剧本杀角色头像：{role_name}，职业是{identity}，{public_bio}。风格为具有个人特点的角色立绘，不一定要特别好看，正面半身像，高质量，4K画质。"

            print(f"🎨 [Avatar] 开始AI生成头像: {role_name}")

            # 2. 异步生成图片URL
            image_url = await generate_image_url_async(prompt)

            if image_url:
                print(f"✅ [Avatar] 头像生成成功: {image_url[:80]}...")

                # 下载并缓存到本地
                cache_path = avatar_cache_path(role_name, scenario_name)
                download_and_cache(image_url, cache_path)

                # 保存角色形象描述（用于后续场景图一致性）
                visual_desc = build_character_visual_desc(role_name, identity, public_bio)
                save_character_visual(role_name, scenario_name, visual_desc)
                print(f"💾 [Avatar] 角色形象描述已保存: {role_name}")

                # 使用现有的 send_avatar_to_public（兼容 Discord/Web 双端发送）
                if os.path.exists(cache_path):
                    await self.engine.send_avatar_to_public(role_name, cache_path)
                    print(f"✅ [Avatar] 头像已缓存并发送: {role_name}")
                else:
                    # 缓存失败则回退到旧临时文件方式
                    response = requests.get(image_url, stream=True)
                    if response.status_code == 200:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                            for chunk in response.iter_content(1024):
                                tmp_file.write(chunk)
                            tmp_file.close()
                            await self.engine.send_avatar_to_public(role_name, tmp_file.name)
                            os.unlink(tmp_file.name)
                            print(f"✅ [Avatar] 头像已发送（临时文件）: {role_name}")
                    else:
                        print(f"⚠️ [Avatar] 头像下载失败: {role_name}")
            else:
                print(f"⚠️ [Avatar] 头像生成失败: {role_name}")

        except Exception as e:
            print(f"❌ [Avatar] 头像生成异常: {e}")
            import traceback
            traceback.print_exc()
