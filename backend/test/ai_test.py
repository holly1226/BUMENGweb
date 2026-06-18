import asyncio
import json
import sys
# 确保从 ai_handler 导入的是新写的流式函数
from ai_handler import get_ai_response_stream

async def test_setup_mode_stream():
    print("🧪 正在测试 [流式 SETUP 模式] - 剧本生成阶段...")
    print("提示：文本将实时跳出，JSON 指令将在最后解析。\n")
    
    mock_preferences = "背景是赛博朋克，带点克苏鲁恐怖，需要 3 个角色，包含一个背叛者情节。"
    
    full_text = ""
    final_action = {}

    print("-" * 30 + " AI 开始传输 " + "-" * 30)

    # 调用异步生成器
    # 注意：这里的 get_ai_response_stream 对应你 ai_handler 里的新函数名
    async for text_chunk, json_part in get_ai_response_stream(mock_preferences, [], mode="SETUP"):
        if text_chunk:
            full_text += text_chunk
            # 实时打印出每一个字，就像打字机一样
            sys.stdout.write(text_chunk)
            sys.stdout.flush()
        
        if json_part:
            final_action = json_part

    print("\n" + "-" * 30 + " 传输结束 " + "-" * 30)

    # 验证测试结果
    print("\n📦 解析出的最终结构化指令 (JSON):")
    if final_action:
        print(json.dumps(final_action, indent=2, ensure_ascii=False))
        
        if final_action.get("type") == "init_game":
            chars = final_action["params"].get("characters", [])
            print(f"\n✅ 测试成功！生成了剧本《{final_action['params'].get('title')}》及 {len(chars)} 个角色。")
    else:
        print("\n❌ 警告：未检测到有效的 JSON 指令包 [[ ]]。")
        print("请检查 prompts.py 是否强制要求了 JSON 格式。")

if __name__ == "__main__":
    try:
        asyncio.run(test_setup_mode_stream())
    except KeyboardInterrupt:
        print("\n测试已手动停止")
    except Exception as e:
        print(f"\n❌ 运行出错: {e}")