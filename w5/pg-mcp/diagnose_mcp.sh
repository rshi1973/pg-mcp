#!/bin/bash

# MCP 连接诊断脚本
# 用于诊断 Claude Desktop 和 MCP 服务器的连接问题

echo "🔍 MCP 连接诊断工具"
echo "================================"
echo ""

# 1. 检查配置文件
echo "1️⃣ 检查 Claude Desktop 配置文件"
echo "--------------------------------"
CONFIG_FILE="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

if [ -f "$CONFIG_FILE" ]; then
    echo "✅ 配置文件存在: $CONFIG_FILE"
    echo ""
    echo "配置内容："
    cat "$CONFIG_FILE"
    echo ""

    # 验证 JSON 格式
    if python3 -m json.tool "$CONFIG_FILE" > /dev/null 2>&1; then
        echo "✅ JSON 格式正确"
    else
        echo "❌ JSON 格式错误！"
        python3 -m json.tool "$CONFIG_FILE"
        exit 1
    fi
else
    echo "❌ 配置文件不存在"
    exit 1
fi

echo ""
echo "2️⃣ 测试 MCP 服务器手动启动"
echo "--------------------------------"

cd /Users/ronny/geektime-bootcamp-ai/w5/pg-mcp

echo "测试命令: uv run python main.py"
echo ""

# 启动服务器并在 3 秒后终止
timeout 3 uv run python main.py 2>&1 &
SERVER_PID=$!

sleep 3

if ps -p $SERVER_PID > /dev/null 2>&1; then
    echo "✅ MCP 服务器成功启动"
    kill $SERVER_PID 2>/dev/null
else
    echo "⚠️  服务器已退出（可能是正常的，因为没有 stdin 输入）"
fi

echo ""
echo "3️⃣ 检查 Claude Desktop 进程"
echo "--------------------------------"

if pgrep -x "Claude" > /dev/null; then
    echo "✅ Claude Desktop 正在运行"
    echo ""
    echo "Claude Desktop 进程信息："
    ps aux | grep -i claude | grep -v grep
else
    echo "❌ Claude Desktop 未运行"
    echo "   请启动 Claude Desktop"
fi

echo ""
echo "4️⃣ 检查端口占用"
echo "--------------------------------"

if lsof -i :9090 > /dev/null 2>&1; then
    echo "⚠️  端口 9090 已被占用："
    lsof -i :9090
    echo ""
    echo "   如果不是 MCP 服务器占用，可能需要更改端口"
else
    echo "✅ 端口 9090 可用"
fi

echo ""
echo "5️⃣ 数据库连接测试"
echo "--------------------------------"

if psql -h localhost -U ronny -d blog_small -c "SELECT 1" > /dev/null 2>&1; then
    echo "✅ 数据库连接正常"
else
    echo "❌ 数据库连接失败"
    echo "   请检查数据库是否运行"
fi

echo ""
echo "================================"
echo "📋 诊断总结"
echo "================================"
echo ""
echo "如果所有检查都通过，但 Claude Desktop 仍然无法使用 MCP 工具，"
echo "请尝试以下步骤："
echo ""
echo "1. 完全退出 Claude Desktop："
echo "   killall Claude"
echo ""
echo "2. 等待 5 秒"
echo ""
echo "3. 重新启动 Claude Desktop："
echo "   open -a Claude"
echo ""
echo "4. 在 Claude Desktop 中查找 MCP 图标（通常在输入框附近）"
echo ""
echo "5. 测试查询："
echo "   - 简单测试: '请列出可用的 MCP 工具'"
echo "   - 工具测试: '请使用 add 工具计算 5 + 3'"
echo ""
echo "6. 如果仍然不工作，查看 Claude Desktop 日志："
echo "   tail -f ~/Library/Logs/Claude/mcp*.log"
echo ""
