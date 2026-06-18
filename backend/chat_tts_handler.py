"""
EdgeTTS 文本转语音集成模块
使用 Microsoft Edge TTS 提供高质量语音合成
"""
import io
import os
import asyncio
import tempfile
from pathlib import Path

try:
    import edge_tts
    EDGETTS_AVAILABLE = True
except ImportError:
    EDGETTS_AVAILABLE = False
    print("⚠️ [EdgeTTS] 未安装 edge-tts，请运行: pip install edge-tts")


class EdgeTTSManager:
    """Edge TTS 管理器"""

    def __init__(self):
        self.initialized = EDGETTS_AVAILABLE

    async def text_to_speech(
        self,
        text: str,
        voice: str = "zh-CN-XiaoxiaoNeural",
        style: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        """将文本转换为语音 (MP3 格式)

        Args:
            text: 要转换的文本
            voice: 语音类型，默认为中文女声
            style: EdgeTTS 情绪/语气（如 "cheerful"、"sad"、"angry" 等），如果为 None 则不使用情绪
            rate: 语速（例如 "+0%"、"-10%"、"+20%"）
            pitch: 音调（例如 "+0Hz"、"-5Hz"、"+10Hz"）

        Returns:
            MP3 音频字节数据，如果失败返回 None
        """
        if not self.initialized:
            print("❌ [EdgeTTS] 未初始化")
            return None

        try:
            print(f"🎤 [EdgeTTS] 正在生成语音: {text[:30]}...")

            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tmp_path = tmp_file.name

            # 构建 SSML（可支持“情绪/语气”）
            ssml_text = text
            if style:
                ssml_text = (
                    f"<speak version=\"1.0\" xmlns=\"http://www.w3.org/2001/10/synthesis\" "
                    f"xmlns:mstts=\"https://www.w3.org/2001/mstts\">"
                    f"<voice name=\"{voice}\">"
                    f"<mstts:express-as style=\"{style}\">{text}</mstts:express-as>"
                    f"</voice></speak>"
                )

            # 使用 edge-tts 生成语音
            communicate = edge_tts.Communicate(ssml_text, voice, rate=rate, pitch=pitch)
            await communicate.save(tmp_path)

            # 读取音频数据
            with open(tmp_path, 'rb') as f:
                audio_data = f.read()

            # 删除临时文件
            os.unlink(tmp_path)

            print(f"✅ [EdgeTTS] 语音生成成功，大小: {len(audio_data)} 字节")
            return audio_data

        except Exception as e:
            print(f"❌ [EdgeTTS] 生成语音失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def generate_and_send(
        self,
        text: str,
        channel,
        voice: str = "zh-CN-XiaoxiaoNeural",
        style: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ):
        """生成语音并发送到 Discord 频道

        Args:
            text: 要转换的文本
            channel: Discord 频道对象
            voice: 语音类型
            style: EdgeTTS 情绪/语气（如 "cheerful"、"sad"、"angry" 等）
            rate: 语速（例如 "+0%"、"-10%"）
            pitch: 音调（例如 "+0Hz"、"-5Hz"）
        """
        if not self.initialized:
            print("❌ [EdgeTTS] EdgeTTS 未初始化")
            await channel.send("❌ 语音功能未启用")
            return

        try:
            # 生成语音
            audio_data = await self.text_to_speech(text, voice, style=style, rate=rate, pitch=pitch)

            if not audio_data:
                await channel.send("❌ 语音生成失败")
                return

            # 创建 Discord 文件对象
            import discord
            audio_file = discord.File(
                io.BytesIO(audio_data),
                filename="speech.mp3"
            )

            # 发送语音文件
            await channel.send(
                file=audio_file,
                content="🔊 **语音合成消息**"
            )
            print(f"✅ [EdgeTTS] 已发送语音到频道")

        except Exception as e:
            print(f"❌ [EdgeTTS] 发送失败: {e}")
            await channel.send(f"❌ 发送语音失败: {str(e)}")


# 全局实例
edge_tts_manager = EdgeTTSManager()


def initialize_tts():
    """初始化全局 TTS 管理器"""
    if not edge_tts_manager.initialized:
        print("❌ [EdgeTTS] 初始化失败")
    else:
        print("✅ [EdgeTTS] 初始化成功")


async def send_with_tts(
    channel,
    text: str,
    use_EdgeTTS: bool = True,
    voice: str = "zh-CN-XiaoxiaoNeural",
    style: str | None = None,
    rate: str = "+0%",
    pitch: str = "+0Hz",
):
    """发送带 TTS 的消息

    Args:
        channel: Discord 频道
        text: 消息文本
        use_EdgeTTS: 是否使用 EdgeTTS（True）还是 Discord TTS（False）
        voice: EdgeTTS 语音类型
        style: EdgeTTS 情绪/语气（如 "cheerful"、"sad"、"angry" 等）
        rate: 语速（例如 "+0%"、"-10%"）
        pitch: 音调（例如 "+0Hz"、"-5Hz"）
    """
    if use_EdgeTTS and EDGETTS_AVAILABLE and edge_tts_manager.initialized:
        print(f"🎤 [EdgeTTS Mode] 使用 EdgeTTS 发送")
        await edge_tts_manager.generate_and_send(
            text,
            channel,
            voice,
            style=style,
            rate=rate,
            pitch=pitch,
        )
    else:
        print(f"🔊 [Discord TTS Mode] 使用 Discord 原生 TTS")
        await channel.send(text, tts=True)
