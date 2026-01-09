# Claude Desktop 连接测试指南

## ✅ 前置检查（已完成）

- [x] Python 3.14.2 已安装
- [x] PostgreSQL 数据库连接正常 (blog_small)
- [x] 简单 MCP 服务器启动成功
- [x] 完整 PostgreSQL MCP 服务器启动成功
- [x] 配置文件已生成

## 📋 配置步骤

### 方式 1: 测试简单的加法服务器（推荐先测试）

这个服务器只有一个简单的 `add` 工具，用于验证 Claude Desktop 连接是否正常。

**步骤：**

1. **找到 Claude Desktop 配置文件位置**
   ```bash
   # macOS
   open ~/Library/Application\ Support/Claude/
   ```

2. **编辑配置文件**
   ```bash
   # 如果文件不存在，创建它
   touch ~/Library/Application\ Support/Claude/claude_desktop_config.json

   # 用编辑器打开
   open -a TextEdit ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

3. **复制以下配置**

   将 `claude_desktop_config_simple.json` 的内容复制到 Claude Desktop 配置文件：

   ```json
   {
     "mcpServers": {
       "test-add": {
         "command": "uv",
         "args": [
           "--directory",
           "/Users/ronny/geektime-bootcamp-ai/w5/pg-mcp",
           "run",
           "python",
           "main.py"
         ]
       }
     }
   }
   ```

4. **重启 Claude Desktop**
   - 完全退出 Claude Desktop（Cmd+Q）
   - 重新启动 Claude Desktop

5. **测试连接**

   在 Claude Desktop 中输入：
   ```
   请使用 MCP 工具 add 计算 5 + 3
   ```

   预期结果：Claude 会调用 `add` 工具并返回 42（这是硬编码的测试值）

### 方式 2: 使用完整的 PostgreSQL MCP 服务器

一旦简单服务器测试成功，就可以切换到完整的数据库查询服务器。

**步骤：**

1. **编辑 Claude Desktop 配置文件**
   ```bash
   open -a TextEdit ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

2. **替换为完整配置**

   将 `claude_desktop_config_full.json` 的内容复制进去：

   ```json
   {
     "mcpServers": {
       "postgres": {
         "command": "uv",
         "args": [
           "--directory",
           "/Users/ronny/geektime-bootcamp-ai/w5/pg-mcp",
           "run",
           "python",
           "-m",
           "pg_mcp.server"
         ],
         "env": {
           "DATABASE_HOST": "localhost",
           "DATABASE_PORT": "5432",
           "DATABASE_NAME": "blog_small",
           "DATABASE_USER": "ronny",
           "DATABASE_PASSWORD": "",
           "GEMINI_API_KEY": "AIzaSyAtMnifGw6GEXcf9VE7ulLMFiiUeFsi13o",
           "GEMINI_MODEL": "gemini-2.0-flash-exp",
           "SECURITY_ALLOW_WRITE_OPERATIONS": "false",
           "SECURITY_MAX_ROWS": "10000",
           "CACHE_ENABLED": "true",
           "OBSERVABILITY_LOG_LEVEL": "INFO"
         }
       }
     }
   }
   ```

3. **重启 Claude Desktop**
   - 完全退出 Claude Desktop（Cmd+Q）
   - 重新启动 Claude Desktop

4. **测试数据库查询**

   在 Claude Desktop 中输入以下测试查询：

   **测试 1: 基础查询**
   ```
   数据库中有多少张表？
   ```

   **测试 2: 查看表结构**
   ```
   blog_small 数据库中有哪些表？
   ```

   **测试 3: 数据查询**
   ```
   显示 posts 表的前 5 条记录
   ```

   **测试 4: 仅生成 SQL**
   ```
   生成 SQL 查询所有用户，但不要执行，只返回 SQL
   ```

## 🔍 如何确认连接成功

### 视觉确认

1. **查看 MCP 图标**
   - Claude Desktop 界面上应该显示一个 MCP 连接图标（通常是 🔌 或类似图标）
   - 点击图标可以看到已连接的服务器列表

2. **查看可用工具**
   - 简单服务器：应该看到 `add` 工具
   - 完整服务器：应该看到 `query` 工具

### 功能测试

**简单服务器测试：**
```
你：请使用 add 工具计算任意两个数
Claude：[调用 add 工具] 结果是 42
```

**完整服务器测试：**
```
你：数据库中有多少张表？
Claude：[调用 query 工具]
根据查询结果，blog_small 数据库中有 X 张表。
生成的 SQL: SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'
```

## 🐛 故障排查

### 问题 1: Claude Desktop 看不到 MCP 服务器

**可能原因：**
- 配置文件路径错误
- JSON 格式错误
- 没有完全重启 Claude Desktop

**解决方法：**
```bash
# 1. 验证配置文件存在
ls -la ~/Library/Application\ Support/Claude/claude_desktop_config.json

# 2. 验证 JSON 格式
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json | python -m json.tool

# 3. 完全退出并重启 Claude Desktop
killall Claude
open -a Claude
```

### 问题 2: MCP 服务器启动失败

**检查日志：**
```bash
# 查看 Claude Desktop 日志
tail -f ~/Library/Logs/Claude/mcp*.log
```

**手动测试服务器：**
```bash
cd /Users/ronny/geektime-bootcamp-ai/w5/pg-mcp

# 测试简单服务器
uv run python main.py

# 测试完整服务器
uv run python -m pg_mcp.server
```

### 问题 3: 数据库连接失败

**验证数据库连接：**
```bash
psql -h localhost -U ronny -d blog_small -c "SELECT 1"
```

**检查环境变量：**
- 确保 `DATABASE_PASSWORD` 正确（当前为空）
- 确保 `GEMINI_API_KEY` 有效

### 问题 4: 工具调用失败

**检查 Gemini API：**
```bash
# 测试 API 密钥是否有效
curl -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"test"}]}]}' \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=AIzaSyAtMnifGw6GEXcf9VE7ulLMFiiUeFsi13o"
```

## 📊 监控和调试

### 查看 Prometheus 指标

```bash
# 服务器运行时，访问指标端点
curl http://localhost:9090/metrics
```

### 查看服务器日志

完整服务器会输出详细的日志：
```
2026-01-09 12:14:56 [INFO] __main__ - Server ready to accept requests
2026-01-09 12:14:56 [INFO] __main__ - databases: ['blog_small']
```

## ✅ 成功标志

当你看到以下情况时，说明连接成功：

1. ✅ Claude Desktop 显示 MCP 图标
2. ✅ 可以在对话中看到 MCP 工具
3. ✅ Claude 能够成功调用工具并返回结果
4. ✅ 数据库查询返回正确的数据
5. ✅ 日志显示 "Server ready to accept requests"

## 📝 测试清单

- [ ] 简单服务器配置完成
- [ ] Claude Desktop 重启
- [ ] 看到 MCP 图标
- [ ] `add` 工具测试成功
- [ ] 切换到完整服务器配置
- [ ] Claude Desktop 重启
- [ ] 数据库表数量查询成功
- [ ] 查看表结构成功
- [ ] 数据查询成功
- [ ] 仅 SQL 模式测试成功

## 🎯 下一步

连接成功后，你可以：

1. **探索数据库**
   ```
   blog_small 数据库的表结构是什么？
   ```

2. **执行分析查询**
   ```
   统计每个作者发布的文章数量
   ```

3. **测试安全限制**
   ```
   删除所有数据（应该被阻止）
   ```

4. **查看生成的 SQL**
   ```
   生成 SQL 查找最近 7 天的文章，但不执行
   ```

## 📞 需要帮助？

如果遇到问题：
1. 查看本指南的故障排查部分
2. 检查服务器日志
3. 手动测试服务器启动
4. 验证数据库连接
