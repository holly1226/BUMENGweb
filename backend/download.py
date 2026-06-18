from modelscope import snapshot_download
# 自动下载模型到当前目录下的 models 文件夹
model_dir = snapshot_download('pzc163/chatTTS', cache_dir="./models")
print(f"模型下载完成，路径在: {model_dir}")