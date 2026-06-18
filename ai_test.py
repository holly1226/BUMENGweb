import os
from dotenv import load_dotenv
from openai import OpenAI

# 加载配置
load_dotenv()
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com" # DeepSeek 的官方服务器地址
)

def test_ai_dm():
    print("正在连接 DeepSeek 大脑...")
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的剧本杀 DM。请根据玩家的要求，构思一个简短的悬疑背景。"},
                {"role": "user", "content": "我想玩一个发生在 1920 年代上海滩的剧本。"}
            ],
            stream=False
        )
        print("\n--- AI 生成的开场白 ---")
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"连接失败：{e}")

if __name__ == "__main__":
    test_ai_dm()