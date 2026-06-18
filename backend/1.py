import ChatTTS
import soundfile as sf
import numpy as np
import torch

# 初始化
chat = ChatTTS.Chat()

# 先尝试 CPU 加载，排除 GPU 问题
chat.load(source="local", device="cpu")

print("加载成功，开始推理...")

try:
    wavs = chat.infer(["你好，很高兴见到你。"])
    if wavs:
        audio_data = np.array(wavs[0]).flatten()
        sf.write("test.wav", audio_data, 24000)
        print("成功！请检查 test.wav")
except Exception as e:
    print(f"错误详情: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()