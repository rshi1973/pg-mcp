#!/bin/bash

# Claude Desktop MCP 配置助手
# 用于快速配置和测试 MCP 服务器连接

set -e

CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"
PROJECT_DIR="/Users/ronny/geektime-bootcamp-ai/w5/pg-mcp"

echo "🚀 Claude Desktop MCP 配置助手"
echo "================================"
echo ""

# 检查 Claude Desktop 配置目录
if [ ! -d "$CLAUDE_CONFIG_DIR" ]; then
    echo "❌ Claude Desktop 配置目录不存在: $CLAUDE_CONFIG_DIR"
    echo "   请确保已安装 Claude Desktop"
    exit 1
fi

echo "✅ Claude Desktop 配置目录存在"

# 备份现有配置
if [ -f "$CLAUDE_CONFIG_FILE" ]; then
    BACKUP_FILE="$CLAUDE_CONFIG_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    echo "📦 备份现有配置到: $BACKUP_FILE"
    cp "$CLAUDE_CONFIG_FILE" "$BACKUP_FILE"
fi

# 显示菜单
echo ""
echo "请选择要配置的 MCP 服务器："
echo "1) 简单测试服务器 (add 工具)"
echo "2) 完整 PostgreSQL 服务器 (query 工具)"
echo "3) 查看当前配置"
echo "4) 测试服务器启动"
echo "5) 退出"
echo ""
read -p "请输入选项 (1-5): " choice

case $choice in
    1)
        echo ""
        echo "📝 配置简单测试服务器..."
        cp "$PROJECT_DIR/claude_desktop_config_simple.json" "$CLAUDE_CONFIG_FILE"
        echo "✅ 配置已更新"
        echo ""
        echo "📋 下一步："
        echo "   1. 完全退出 Claude Desktop (Cmd+Q)"
        echo "   2. 重新启动 Claude Desktop"
        echo "   3. 在对话中输入: 请使用 add 工具计算 5 + 3"
        ;;
    2)
        echo ""
        echo "📝 配置完整 PostgreSQL 服务器..."
        cp "$PROJECT_DIR/claude_desktop_config_full.json" "$CLAUDE_CONFIG_FILE"
        echo "✅ 配置已更新"
        echo ""
        echo "📋 下一步："
        echo "   1. 完全退出 Claude Desktop (Cmd+Q)"
        echo "   2. 重新启动 Claude Desktop"
        echo "   3. 在对话中输入: 数据库中有多少张表？"
        ;;
    3)
        echo ""
        echo "📄 当前配置："
        echo "================================"
        if [ -f "$CLAUDE_CONFIG_FILE" ]; then
            cat "$CLAUDE_CONFIG_FILE" | python3 -m json.tool
        else
            echo "配置文件不存在"
        fi
        ;;
    4)
        echo ""
        echo "🧪 测试服务器启动..."
        echo ""
        echo "测试 1: 简单服务器"
        echo "================================"
        cd "$PROJECT_DIR"
        timeout 3 uv run python main.py 2>&1 | head -20 || echo "✅ 简单服务器启动正常"
        echo ""
        echo "测试 2: 完整 PostgreSQL 服务器"
        echo "================================"
        timeout 5 uv run python -m pg_mcp.server 2>&1 | head -30 || echo "✅ 完整服务器启动正常"
        ;;
    5)
        echo "👋 退出"
        exit 0
        ;;
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac

echo ""
echo "✨ 完成！"
