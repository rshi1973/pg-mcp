# 🎯 Claude Desktop MCP 工具使用指南

## ✅ 诊断结果

根据诊断，你的 MCP 服务器已经成功连接到 Claude Desktop！

**证据：**
```
进程列表中显示：
/Applications/Claude.app/Contents/Helpers/disclaimer
/Users/ronny/.local/bin/uv --directory
/Users/ronny/geektime-bootcamp-ai/w5/pg-mcp run python main.py
```

这说明 Claude Desktop 已经启动了你的 MCP 服务器。

## ❓ 为什么 Claude 说"无法访问数据库"？

这是因为 **Claude 不知道你想让它使用 MCP 工具**。你需要明确告诉 Claude 使用 MCP 工具。

## 🔧 正确的使用方式

### ❌ 错误的提问方式

```
你：数据库中有多少张表？
Claude：我无法直接访问您本地的数据库...
```

**问题：** Claude 认为你在问它一个普通问题，它不知道要使用 MCP 工具。

### ✅ 正确的提问方式

#### **方式 1: 明确要求使用 MCP 工具**

```
你：请使用 MCP 工具查询数据库中有多少张表
Claude：[调用 test-add 工具] ...
```

#### **方式 2: 直接要求调用工具**

```
你：请调用 add 工具计算 5 + 3
Claude：[调用 add 工具] 结果是 42
```

#### **方式 3: 询问可用的工具**

```
你：你有哪些 MCP 工具可用？
Claude：我可以使用以下 MCP 工具：
- test-add: add 工具（加法计算）
```

## 📝 测试步骤

### 第 1 步：确认 MCP 工具可见

在 Claude Desktop 中输入：

```
请列出你可以使用的所有 MCP 工具
```

**预期回复：**
```
我可以使用以下 MCP 工具：
- test-add 服务器提供的 add 工具
```

### 第 2 步：测试简单工具

```
请使用 add 工具计算 10 + 20
```

**预期回复：**
```
[调用 add(10, 20)]
结果是 42
```

注意：这个工具硬编码返回 42，这是正常的测试行为。

### 第 3 步：切换到完整数据库服务器

一旦简单工具测试成功，就可以切换到完整的 PostgreSQL 服务器。

**更新配置：**
```bash
./setup_claude_desktop.sh
# 选择 2) 完整 PostgreSQL 服务器
```

**重启 Claude Desktop：**
```bash
killall Claude
sleep 3
open -a Claude
```

### 第 4 步：测试数据库查询

```
请使用 MCP 工具查询 blog_small 数据库中有多少张表
```

**预期回复：**
```
[调用 query 工具]
根据查询结果，blog_small 数据库中有 X 张表。

生成的 SQL:
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = 'public'
```

## 🎨 Claude Desktop UI 提示

### 查找 MCP 图标

1. **输入框附近** - 通常在输入框的左侧或右侧
2. **工具栏** - 可能在顶部工具栏
3. **设置菜单** - 在设置中查看 MCP 连接状态

### MCP 工具调用的视觉反馈

当 Claude 调用 MCP 工具时，你会看到：
- 🔧 工具调用指示器
- 工具名称和参数
- 工具返回的结果

## 📊 测试查询示例

### 简单服务器（test-add）

```
1. 请使用 add 工具计算 5 + 3
2. 调用 add 函数，参数 a=100, b=200
3. 测试 add 工具是否正常工作
```

### 完整服务器（postgres）

```
1. 请使用 query 工具查询数据库中的所有表名
2. 使用 MCP 查询 posts 表的结构
3. 生成 SQL 查询最近 7 天的文章（不执行）
4. 查询 blog_small 数据库中有多少条记录
```

## 🐛 常见问题

### Q1: Claude 说"我没有 MCP 工具"

**原因：** MCP 服务器未连接

**解决：**
```bash
# 1. 检查配置
cat ~/Library/Application\ Support/Claude/claude_desktop_config.json

# 2. 重启 Claude Desktop
killall Claude && sleep 3 && open -a Claude

# 3. 运行诊断
./diagnose_mcp.sh
```

### Q2: Claude 说"无法访问数据库"

**原因：** 你没有明确要求使用 MCP 工具

**解决：** 在提问时加上"请使用 MCP 工具"或"请调用 query 工具"

### Q3: 工具调用失败

**检查：**
```bash
# 查看 MCP 服务器进程
ps aux | grep "main.py"

# 手动测试服务器
uv run python main.py

# 查看日志
tail -f ~/Library/Logs/Claude/mcp*.log
```

### Q4: 数据库连接失败

**检查：**
```bash
# 测试数据库连接
psql -h localhost -U ronny -d blog_small -c "SELECT 1"

# 检查环境变量
cat .env | grep DATABASE
```

## 🎯 关键要点

1. ✅ **MCP 服务器已连接** - 进程列表显示服务器正在运行
2. ✅ **配置正确** - JSON 格式和路径都正确
3. ✅ **数据库正常** - PostgreSQL 连接测试通过
4. ⚠️  **需要明确调用** - 必须告诉 Claude 使用 MCP 工具

## 📞 下一步

1. **在 Claude Desktop 中测试：**
   ```
   请列出可用的 MCP 工具
   ```

2. **如果看到工具列表，测试调用：**
   ```
   请使用 add 工具计算 5 + 3
   ```

3. **如果成功，切换到完整服务器并测试数据库查询**

4. **如果失败，运行诊断脚本并查看日志**

## 💡 提示

- Claude 需要你**明确要求**使用 MCP 工具
- 不要只是问问题，要说"请使用 MCP 工具"或"请调用 XXX 工具"
- 查看 Claude Desktop UI 中的 MCP 图标确认连接状态
- 工具调用会显示在对话中，包括参数和返回值
