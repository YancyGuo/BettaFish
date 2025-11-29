# BettaFish 微舆系统 - Claude使用指南

## 🎯 项目概述
**微舆 (BettaFish)** 是一个从0实现的创新型多智能体舆情分析系统，帮助用户破除信息茧房，还原舆情原貌，预测未来走向，辅助决策。

- **官方名称**: 微舆
- **项目名称**: BettaFish
- **访问地址**: http://172.22.99.181:5000 (WSL环境)
- **架构**: Flask主应用 + 3个Streamlit子应用 + PostgreSQL数据库 + AI爬虫集群

## 🚀 快速启动指南

### 环境要求
- Python 3.8+
- PostgreSQL数据库
- WSL2环境 (Windows用户)
- 足够的内存 (推荐8GB+)

### 启动步骤

#### 1. 激活虚拟环境
```bash
cd /home/yancy/all_repo/BettaFish
source .venv/bin/activate
```

#### 2. 检查数据库连接
```bash
PGPASSWORD=bettafish psql -U bettafish -d bettafish -h 127.0.0.1 -p 5432 -c "\dt"
```

#### 3. 启动主应用 (重要启动顺序)
```bash
# 后台启动 (推荐)
source .venv/bin/activate && nohup python app.py > app.log 2>&1 &

# 前台启动 (用于调试)
source .venv/bin/activate && python app.py
```

**⚠️ 重要启动流程说明**:
1. **Flask主应用 (端口5000) 首先启动**
2. **读取.env配置文件** 确定各引擎的LLM配置
3. **等待配置确认** (约30-60秒)
4. **自动启动Streamlit子应用**:
   - Insight Engine (端口8501)
   - Media Engine (端口8502)
   - Query Engine (端口8503)

#### 4. 验证启动状态
```bash
# 检查端口占用
ss -tlnp | grep -E "(5000|8501|8502|8503)"

# 检查应用日志
tail -20 app.log

# 检查子应用日志
tail -10 logs/insight.log  # Insight Engine
tail -10 logs/media.log   # Media Engine
tail -10 logs/query.log   # Query Engine
```

### 🌐 访问地址 (WSL环境)

**主要入口**:
- `http://172.22.99.181:5000` (推荐)
- `http://127.0.0.1:5000` (备选)

**子系统独立访问**:
- **Insight Engine**: `http://172.22.99.181:8501`
- **Media Engine**: `http://172.22.99.181:8502`
- **Query Engine**: `http://172.22.99.181:8503`

**获取WSL IP地址**:
```bash
hostname -I | awk '{print $1}'
# 或者
cat /etc/resolv.conf | grep nameserver | awk '{print $2}'
```

## ⚠️ 常见问题和解决方案

### 1. WSL环境跨域访问问题 (重要)

**问题表现**:
- 主页面能访问 `http://localhost:5000`
- 但iframe无法加载子系统，显示"localhost拒绝了连接请求"
- curl在服务器内部能访问localhost:8501，但浏览器无法访问

**根本原因**:
WSL环境中Streamlit默认只绑定到localhost，导致从Windows浏览器无法访问WSL内的服务。

**解决方案**:
修改 `/home/yancy/all_repo/BettaFish/app.py` 文件，在Streamlit启动命令中添加 `--server.address 0.0.0.0`:

```python
cmd = [
    sys.executable, '-m', 'streamlit', 'run',
    script_path,
    '--server.port', str(port),
    '--server.address', '0.0.0.0',  # 关键修复
    '--server.headless', 'true',
    '--browser.gatherUsageStats', 'false',
    '--logger.level', 'info',
    '--server.enableCORS', 'false'
]
```

**重启应用**:
```bash
pkill -f "python app.py"
sleep 2
source .venv/bin/activate && nohup python app.py > app.log 2>&1 &
```

### 2. 数据库连接问题

**检查数据库连接**:
```bash
PGPASSWORD=bettafish psql -U bettafish -d bettafish -h 127.0.0.1 -p 5432
```

**查看表结构**:
```sql
\dt  -- 查看所��表
SELECT COUNT(*) FROM weibo_note;  -- 查看数据量
```

### 3. 端口占用问题

**查看端口占用**:
```bash
ss -tlnp | grep -E "(5000|8501|8502|8503)"
```

**清理相关进程**:
```bash
pkill -f "python app.py"
pkill -f "streamlit"
```

### 4. 子应用启动失败

**现象**: 主页面显示子系统健康检查失败
**解决**: 检查日志文件，通常是因为端口冲突或依赖缺失

```bash
# 查看具体错误
tail -50 app.log
# 查看子系统日志
ls logs/
```

### 5. LLM配置切换问题 (重要)

**问题表现**:
- 修改.env文件中的LLM配置后重启，系统仍使用旧配置
- Web界面配置更新无法生效，显示CORS错误

**根本原因**:
BettaFish使用Pydantic Settings加载配置，优先级：**环境变量 > .env文件 > 默认值**
当进程启动时会继承父进程的环境变量，即使.env文件已更新，环境变量仍然保持旧值。

**解决方案 - 强制配置更新**:
```bash
# 1. 完全关闭所有相关进程
pkill -f "python app.py"
pkill -f "streamlit"

# 2. 清除旧的LLM环境变量 (重要!)
unset INSIGHT_ENGINE_API_KEY INSIGHT_ENGINE_BASE_URL INSIGHT_ENGINE_MODEL_NAME

# 3. 使用正确的环境变量启动
export INSIGHT_ENGINE_API_KEY="sk-c53cb7edd79547eab5f96ad6bec7c8b3"
export INSIGHT_ENGINE_BASE_URL="https://api.deepseek.com/v1"
export INSIGHT_ENGINE_MODEL_NAME="deepseek-chat"
source .venv/bin/activate && nohup python app.py > app.log 2>&1 &

# 4. 验证配置生效
curl -s http://localhost:5000/api/config | python3 -c "
import json, sys
data = json.load(sys.stdin)
insight = {k: v for k, v in data['config'].items() if 'INSIGHT' in k}
for k, v in insight.items():
    print(f'{k}: {v}')
"
```

**Web界面配置更新失败处理**:
如果Web界面无法同步.env文件变更 (显示CORS错误)，需要手动编辑.env文件，然后按上述步骤重启。

**当前LLM配置状态** (2025-11-29更新):
- **Insight Engine**: DeepSeek-chat (已从kimi切换)
- **Media Engine**: Gemini-2.5-pro
- **Query Engine**: DeepSeek-chat
- **Report Engine**: Gemini-2.5-pro

## 📊 系统架构说明

### 核心组件
1. **Flask主应用** (端口5000): 统一入口和页面管理
2. **Insight Engine** (端口8501): 洞察分析引擎
3. **Media Engine** (端口8502): 媒体分析引擎
4. **Query Engine** (端口8503): 查询分析引擎
5. **PostgreSQL**: 数据存储
6. **MindSpider**: AI爬虫集群

### 数据库主要表结构
```sql
-- 主要内容表
weibo_note             -- 微博内容
zhihu_content          -- 知乎内容
kuaishou_video         -- 快手视频
douyin_aweme           -- 抖音视频
xhs_note               -- 小红书笔记

-- 评论表
weibo_note_comment     -- 微博评论
zhihu_comment          -- 知乎评论
kuaishou_video_comment -- 快手评论

-- 项目管理
daily_topics           -- 分析主题和关键词
```

## 🗄️ 数据库操作示例

### 检查数据量
```sql
SELECT
  'weibo_note' as table_name, COUNT(*) as count FROM weibo_note
UNION ALL
SELECT 'zhihu_content' as table_name, COUNT(*) as count FROM zhihu_content
UNION ALL
SELECT 'kuaishou_video' as table_name, COUNT(*) as count FROM kuaishou_video;
```

### 查看最新数据
```sql
SELECT source_keyword, LEFT(content, 80) as preview, liked_count
FROM weibo_note
ORDER BY add_ts DESC
LIMIT 5;
```

## 📝 日志和调试

### 应用日志位置
- **主应用日志**: `app.log`
- **子系统日志**: `logs/` 目录下各应用日志文件
- **论坛日志**: `ForumEngine/logs/forum.log`

### 实时查看日志
```bash
# 主应用日志
tail -f app.log

# 查看特定组件日志
tail -f logs/insight.log
```

## 🔧 开发和调试

### 手动启动子系统
```bash
# 单独启动Insight Engine
streamlit run SingleEngineApp/insight_engine_streamlit_app.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.enableCORS false

# 单独启动Media Engine
streamlit run SingleEngineApp/media_engine_streamlit_app.py \
  --server.port 8502 \
  --server.address 0.0.0.0 \
  --server.enableCORS false

# 单独启动Query Engine
streamlit run SingleEngineApp/query_engine_streamlit_app.py \
  --server.port 8503 \
  --server.address 0.0.0.0 \
  --server.enableCORS false
```

### 测试API接口
```bash
# 测试主页面
curl -I http://127.0.0.1:5000

# 测试子系统健康检查
curl http://127.0.0.1:8501/_stcore/health
curl http://127.0.0.1:8502/_stcore/health
curl http://127.0.0.1:8503/_stcore/health
```

## 💡 使用建议

1. **推荐访问方式**: 使用WSL IP地址 `http://172.22.99.181:5000` 避免跨域问题
2. **浏览器选择**: Chrome/Edge对iframe支持较好
3. **性能优化**: 系统启动后等待1-2分钟让所有组件完全初始化
4. **数据监控**: 定期检查数据库存储情况，避免磁盘空间不足

## 🆘 故障排除清单

遇到问题时按以下顺序检查：

1. ✅ **检查进程**: `ps aux | grep -E "(python|streamlit)"`
2. ✅ **检查端口**: `ss -tlnp | grep -E "(5000|8501|8502|8503)"`
3. ✅ **检查数据库**: `PGPASSWORD=bettafish psql -U bettafish -d bettafish -h 127.0.0.1 -p 5432 -c "\dt"`
4. ✅ **检查日志**: `tail -20 app.log`
5. ✅ **检查网络**: `curl -I http://172.22.99.181:5000`

---

*文档创建时间: 2025-11-29*
*维护者: Claude*
*版本: v1.0*