# ---- 构建阶段：Node.js 构建前端 ----
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# ---- 运行阶段：Python 后端 ----
FROM python:3.11-slim
WORKDIR /app

# 安装 Python 依赖
COPY backend/web_requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/web_requirements.txt

# 复制后端代码
COPY backend/ ./backend/
COPY img/ ./img/
COPY DBFestival.json ./

# 复制前端构建产物
COPY --from=frontend-builder /app/dist ./dist

# 创建 Temp 目录
RUN mkdir -p backend/Temp

EXPOSE 8000

CMD ["python", "backend/web_server.py"]
