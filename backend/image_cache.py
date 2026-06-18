"""
图片本地缓存模块
- 头像缓存：按 角色名_剧本名 存储，避免每次 AI 重新生成
- 场景图缓存：按 场景名 存储，同一场景复用
- 角色形象描述缓存：用于后续场景图保持同一人物外观
"""
import os
import hashlib
import json
import requests
import asyncio
import base64

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
CACHE_DIR = os.path.join(ROOT_DIR, "img", "cache")
VISUAL_FILE = os.path.join(CACHE_DIR, "character_visuals.json")


def ensure_cache_dir():
    """确保缓存目录存在"""
    os.makedirs(CACHE_DIR, exist_ok=True)


def _make_key(*parts: str) -> str:
    """生成安全的文件名 key"""
    raw = "_".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def avatar_cache_path(character_name: str, scenario_name: str = "default") -> str:
    """头像缓存文件路径"""
    ensure_cache_dir()
    key = _make_key("avatar", character_name, scenario_name)
    return os.path.join(CACHE_DIR, f"avatar_{key}.png")


def scene_cache_path(scene_name: str) -> str:
    """场景图缓存文件路径"""
    ensure_cache_dir()
    # 统一 scene name（去除空格、转小写）
    normalized = scene_name.strip()
    key = _make_key("scene", normalized)
    return os.path.join(CACHE_DIR, f"scene_{key}.png")


def avatar_cache_exists(character_name: str, scenario_name: str = "default") -> bool:
    """检查头像缓存是否存在"""
    return os.path.exists(avatar_cache_path(character_name, scenario_name))


def scene_cache_exists(scene_name: str) -> bool:
    """检查场景图缓存是否存在"""
    return os.path.exists(scene_cache_path(scene_name))


def get_cached_avatar_base64(character_name: str, scenario_name: str = "default") -> str | None:
    """读取缓存的头像是 base64"""
    path = avatar_cache_path(character_name, scenario_name)
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{data}"
    return None


def get_cached_scene_base64(scene_name: str) -> str | None:
    """读取缓存的场景图 base64"""
    path = scene_cache_path(scene_name)
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{data}"
    return None


def download_and_cache(image_url: str, cache_path: str) -> bool:
    """下载图片并保存到缓存路径"""
    try:
        ensure_cache_dir()
        resp = requests.get(image_url, stream=True, timeout=30)
        if resp.status_code == 200:
            with open(cache_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            print(f"💾 [Cache] 图片已缓存: {os.path.basename(cache_path)}")
            return True
        else:
            print(f"⚠️ [Cache] 下载失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ [Cache] 下载异常: {e}")
        return False


async def url_to_base64(image_url: str) -> str | None:
    """异步下载图片 URL 并返回 base64 data URI（用于直接发送，不走文件缓存）"""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    b64 = base64.b64encode(data).decode()
                    return f"data:image/png;base64,{b64}"
                else:
                    print(f"⚠️ [Base64] 下载失败: HTTP {resp.status}")
                    return None
    except Exception as e:
        print(f"❌ [Base64] 下载异常: {e}")
        return None


def _url_to_base64_sync(image_url: str) -> str | None:
    """同步下载图片 URL 并返回 base64 data URI（url_to_base64 的兜底方案）"""
    try:
        resp = requests.get(image_url, timeout=30)
        if resp.status_code == 200:
            b64 = base64.b64encode(resp.content).decode()
            return f"data:image/png;base64,{b64}"
        else:
            print(f"⚠️ [Base64-Sync] 下载失败: HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"❌ [Base64-Sync] 下载异常: {e}")
        return None


def cached_file_base64(cache_path: str) -> str | None:
    """读取缓存文件返回 base64 data URI"""
    if not os.path.exists(cache_path):
        return None
    with open(cache_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{data}"


# ===== 角色形象描述缓存（用于场景一致性） =====

def load_character_visuals() -> dict:
    """加载所有已存储的角色形象描述"""
    ensure_cache_dir()
    if os.path.exists(VISUAL_FILE):
        with open(VISUAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_character_visual(character_name: str, scenario_name: str, visual_desc: str):
    """保存角色形象描述"""
    ensure_cache_dir()
    visuals = load_character_visuals()
    key = f"{character_name}::{scenario_name}"
    visuals[key] = visual_desc
    with open(VISUAL_FILE, "w", encoding="utf-8") as f:
        json.dump(visuals, f, ensure_ascii=False, indent=2)
    print(f"💾 [Cache] 角色形象描述已保存: {character_name}")


def get_character_visual(character_name: str, scenario_name: str = "default") -> str | None:
    """获取已保存的角色形象描述"""
    visuals = load_character_visuals()
    key = f"{character_name}::{scenario_name}"
    return visuals.get(key)


def build_character_visual_desc(character_name: str, identity: str, public_bio: str) -> str:
    """根据角色数据构建简洁的角色形象描述（用于场景图生成提示词）"""
    parts = [f"主角{character_name}"]
    if identity:
        parts.append(f"身份{identity}")
    if public_bio:
        # 取前200字符的关键描述
        desc = public_bio.replace("\n", " ").strip()[:200]
        parts.append(f"{desc}")
    return "，".join(parts)
