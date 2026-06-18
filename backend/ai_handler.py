import os
import json
import re
import httpx
from openai import AsyncOpenAI, OpenAI
from dotenv import load_dotenv
import re # 导入正则
import asyncio
import dashscope
import base64
from dashscope import MultiModalConversation
import prompts
import requests

# 必须在所有客户端初始化之前加载 .env
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(_ENV_PATH)

# client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1" 
qwen_client=OpenAI(base_url=qwen_base_url,api_key=os.getenv("QWEN_SECRET"),timeout=60)  
dashscope.api_key = os.getenv("QWEN_SECRET")

# 客户端初始化
proxy_url = os.getenv("DISCORD_PROXY")
http_client = httpx.AsyncClient(proxy=proxy_url, timeout=60.0) if proxy_url else httpx.AsyncClient(timeout=60.0)

client = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    http_client=http_client
)

gpt_client = OpenAI(base_url="https://api.wlai.vip/v1", api_key=os.getenv("GPT_SECRET"), timeout=60)

async def ask_gpt_async(prompt_text, history=[], system_instruction="", model="gpt-4o", mode="json", temperature=0.):
    """异步版本的 GPT 调用"""
    if mode == "json":
        response_format = {"type": "json_object"}
    else:
        response_format = None

    message = [{"role": "system", "content": system_instruction}]
    for d in history:
        message.append({"role": "user", "content": d["user"]})
        message.append({"role": "assistant", "content": d["bot"]})
    message.append({"role": "user", "content": prompt_text})

    try:
        loop = asyncio.get_event_loop()
        def sync_call():
            completion = gpt_client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format=response_format,
                messages=message
            )
            if completion.choices:
                return completion.choices[0].message.content
            else:
                print("GPT no reply")
                return None

        result = await loop.run_in_executor(None, sync_call)
        return result
    except Exception as e:
        print(f"gpt error {e}")
        return None

async def get_ai_response(user_input, history, mode="PLAY", model="deepseek-chat", historys=""):
    # 1. 选择基础提示词
    if mode == "SETUP":
        base_system = prompts.GAME_SETUP_SYSTEM
    else:
        base_system = prompts.GAME_PLAY_SYSTEM

    # 2. 注入变量 (注意缩进)
    try:
        # 如果 base_system 里没有 {historys}，这一步会自动跳入 except
        final_system_prompt = base_system.format(historys=historys)
    except Exception as e:
        # 如果格式化失败（例如没有占位符），回退到原始提示词
        final_system_prompt = base_system

    # 3. 构建消息体
    messages = [{"role": "system", "content": final_system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    full_content = ""
    
    try:
        # 4. 异步流式调用
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.8 if mode == "SETUP" else 0.5,
            stream=True
        )

        async for chunk in stream:
            if not chunk.choices: continue
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full_content += delta
                yield delta, None

    except Exception as e:
        yield f"\n❌ AI 传输错误: {str(e)}", None
        return

    # 5. 解析 JSON 指令
    json_part = {}
    match = re.search(r"\[\[(.*?)\]\]", full_content, re.DOTALL)
    if match:
        json_str = match.group(1).strip().replace("```json", "").replace("```", "").strip()
        try:
            json_part = json.loads(json_str)
        except:
            print(f"❌ JSON 解析失败: {json_str[:100]}")
    
    # 最终输出 JSON
    yield "", json_part

def ask_qwen(prompt_text, history=[], system_instruction="", model="qwen-turbo",
             mode="str", temperature=0., enable_search=False, enable_citaton=False):
    "直接返回字符串"
    if mode=="json":
        response_format={ "type": "json_object" }
    else:
        response_format=None
    message=[{"role": "system", "content": system_instruction}]    # 角色包含system、user和assistant三种
    for d in history:  # 把通义千问的历史格式转化为GPT的历史格式
        message.append({"role":"user","content":d["user"]})
        message.append({"role":"assistant","content":d["bot"]})
    message.append({"role":"user","content":prompt_text})
    try:
        completion = qwen_client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format=response_format,
            messages=message,
            extra_body={
                "enable_search": enable_search,
                "search_options": {
                    "enable_source": True,
                    "enable_citation": enable_citaton,
                    "citation_format": "[<number>]",
                    "forced_search": False
                    }
                }
            )
        # print(completion)
        if completion.choices:
            return completion.choices[0].message.content
        else:
            print("Qwen no reply")
    except Exception as e:
        print(f"Qwen error {e}")

def generate_image_url(prompt_text: str, api_key:str=os.getenv("QWEN_SECRET"), 
                          model="qwen-image-plus-2026-01-09", size="1024*1024"):
    "使用通义千问文生图功能，返回一个图像的下载网址"
    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {"text": prompt_text}
                ]
            }
        ]

        response = MultiModalConversation.call(
            api_key=api_key,
            model=model,
            messages=messages,
            result_format='message',
            stream=False,
            watermark=False,
            prompt_extend=True,
            negative_prompt="低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。",
            size=size
        )
        
        if response.status_code == 200:
            # print(json.dumps(response, ensure_ascii=False))
            image_url=response['output']['choices'][0]['message']['content'][0]['image']
            return image_url
        else:
            print(f"HTTP返回码：{response}")
    except Exception as e:
        print(f"图像生成失败：Qwen error {e}")
        return ""

def save_image_from_url(image_url, save_path="generated_image.png"):
    """从URL下载并保存图像"""
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            print(f"图像已保存到: {save_path}")
            return save_path
        else:
            print(f"下载失败，状态码: {response.status_code}")
            return None
    except Exception as e:
        print(f"下载图像时出错: {e}")
        return None

async def generate_image_url_async(prompt_text: str, api_key: str = os.getenv("QWEN_SECRET"),
                                    model="qwen-image-plus-2026-01-09", size="1024*1024"):
    """异步版本：使用通义千问文生图功能，返回图像的下载网址"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: generate_image_url(prompt_text, api_key, model, size)
    )

def ask_qwen_vl(prompt_text, files=[], history=[], system_instruction="", model="qwen-vl-max",
                mode="str", temperature=0, enable_search=False, enable_citation=False):
    """
    支持多模态输入的 Qwen-VL 调用函数。
    files: 支持以下类型元素的列表：
        - 本地图像路径（str）
        - 图像的 base64 编码字符串（str，需以 data:image/... 开头 或 纯 base64）
        - 二进制图像数据（bytes）
    """
    if mode == "json":
        response_format = {"type": "json_object"}
    else:
        response_format = None

    # 构建用户消息内容：文本 + 所有图像
    user_content = []

    # 添加文本 prompt
    user_content.append({"type": "text", "text": prompt_text})

    # 处理每个文件/图像
    for file in files:
        image_url = None
        if isinstance(file, str):
            if file.startswith(("http://", "https://")):
                # 公网 URL
                image_url = file
            elif os.path.isfile(file):
                # 本地路径 → 转 base64
                with open(file, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                image_url = f"data:image/jpeg;base64,{b64}"
            elif file.startswith("data:image"):
                # 已是 data URL
                image_url = file
            else:
                # 假设是纯 base64 字符串
                image_url = f"data:image/jpeg;base64,{file}"
        elif isinstance(file, bytes):
            b64 = base64.b64encode(file).decode("utf-8")
            image_url = f"data:image/jpeg;base64,{b64}"
        else:
            raise ValueError(f"Unsupported file type: {type(file)}")

        user_content.append({"type": "image_url", "image_url": {"url": image_url}})

    # 构建消息历史
    message = []
    if system_instruction:
        message.append({"role": "system", "content": system_instruction})
    
    for d in history:
        message.append({"role": "user", "content": d["user"]})
        message.append({"role": "assistant", "content": d["bot"]})
    
    # 添加当前带图的用户消息
    message.append({"role": "user", "content": user_content})

    try:
        completion = qwen_client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format=response_format,
            messages=message,
            extra_body={
                "enable_search": enable_search,
                "enable_citation": enable_citation
            }
        )
        if completion.choices:
            return completion.choices[0].message.content
        else:
            print("Qwen VL no reply")
            return None
    except Exception as e:
        print(f"Qwen VL error: {e}")
        return None
    
def get_qwen_embedding(
    text: str,
    model: str = "text-embedding-v3",
    dimensions: int = 512
) -> list:
    """
    获取通义千问的文本嵌入向量
    
    参数:
    text -- 需要编码的文本内容（必填）
    model -- 模型名称（默认text-embedding-v3）
    dimensions -- 向量维度（默认1024，可选64/128/256/512/1024/1536）
    encoding_format -- 编码格式（默认float）
    
    返回:
    list -- 文本嵌入向量
    """
    # 长度限制
    if len(text)<1 or len(text)>8191:
        return []
    
    try:
        response = qwen_client.embeddings.create(
            model=model,
            input=text,
            dimensions=dimensions,
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None
    
semaphore = asyncio.Semaphore(5)

async def ask_qwen_async(*args, **kwargs):
    return await asyncio.to_thread(ask_qwen, *args, **kwargs)

async def ask_qwen_vl_async(*args, **kwargs):
    return await asyncio.to_thread(ask_qwen, *args, **kwargs)

async def get_qwen_embedding_async(*args, **kwargs):
    """
    异步获取Qwen模型的嵌入向量
    
    Args:
        *args: 传递给get_qwen_embedding的位置参数
        **kwargs: 传递给get_qwen_embedding的关键字参数
    
    Returns:
        Any: 返回get_qwen_embedding函数的计算结果
    
    Note:
        此函数通过asyncio.to_thread将同步函数get_qwen_embedding转换为异步执行
    """
    return await asyncio.to_thread(get_qwen_embedding, *args, **kwargs)

async def ask_deepseek_async(prompt_text, system_instruction="", mode="str", model="deepseek-chat"):
    """
    专门为剧情推演设计的 DeepSeek 异步调用函数
    """
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": prompt_text}
    ]
    
    try:
        # 使用你已经定义好的全局 client (AsyncOpenAI)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.5, # 降低随机性，减少"故弄玄虚"的倾向
            response_format={"type": "json_object" } if mode == "json" else None
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ DeepSeek Error: {e}")
        return None