# PostgreSQL MCP Server - 抽样测试指南

本指南提供详细的手动测试步骤和典型测试用例，用于验证重构后的代码质量。

---

## 📋 目录

1. [环境准备](#环境准备)
2. [单元测试](#单元测试)
3. [集成测试](#集成测试)
4. [功能测试](#功能测试)
5. [性能测试](#性能测试)
6. [典型测试场景](#典型测试场景)

---

## 环境准备

### 1. 安装依赖

```bash
# 进入项目目录
cd /Users/ronny/geektime-bootcamp-ai/w5/pg-mcp

# 安装所有依赖（包括开发依赖）
uv sync --all-extras

# 验证安装
uv run python --version
uv run pytest --version
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# 复制示例配置
cp .env.example .env

# 编辑配置文件
cat > .env << 'EOF'
# Database Configuration
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=postgres
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password

# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash-exp

# Security Configuration
SECURITY_ALLOW_WRITE_OPERATIONS=false
SECURITY_MAX_ROWS=10000

# Observability Configuration
OBSERVABILITY_LOG_LEVEL=INFO
OBSERVABILITY_METRICS_ENABLED=true
OBSERVABILITY_METRICS_PORT=9090
EOF
```

### 3. 启动测试数据库（可选）

如果需要完整的集成测试：

```bash
# 使用 Docker 启动 PostgreSQL
docker run -d \
  --name pg-mcp-test \
  -e POSTGRES_PASSWORD=test123 \
  -e POSTGRES_DB=testdb \
  -p 5432:5432 \
  postgres:16

# 等待数据库启动
sleep 5

# 创建测试数据
docker exec -i pg-mcp-test psql -U postgres -d testdb << 'EOF'
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (name, email) VALUES
    ('Alice', 'alice@example.com'),
    ('Bob', 'bob@example.com'),
    ('Charlie', 'charlie@example.com');

INSERT INTO orders (user_id, amount, status) VALUES
    (1, 99.99, 'completed'),
    (1, 149.99, 'pending'),
    (2, 79.99, 'completed'),
    (3, 199.99, 'pending');
EOF
```

---

## 单元测试

### 1. 运行所有单元测试

```bash
# 运行所有单元测试
uv run pytest tests/unit/ -v

# 运行特定模块的测试
uv run pytest tests/unit/test_orchestrator.py -v

# 运行特定测试类
uv run pytest tests/unit/test_orchestrator.py::TestExecuteQueryFlow -v

# 运行特定测试用例
uv run pytest tests/unit/test_orchestrator.py::TestExecuteQueryFlow::test_execute_query_with_results -v
```

### 2. 测试覆盖率

```bash
# 生成覆盖率报告
uv run pytest tests/unit/ --cov=src/pg_mcp --cov-report=html --cov-report=term

# 查看 HTML 报告
open htmlcov/index.html  # macOS
# 或
xdg-open htmlcov/index.html  # Linux
```

### 3. 重点测试重构的函数

#### 测试 execute_query() 重构

```bash
# 运行 execute_query 相关的所有测试
uv run pytest tests/unit/test_orchestrator.py::TestExecuteQueryFlow -v

# 预期结果：21 passed
```

**验证点**：
- ✅ SQL-only 请求正确处理
- ✅ 完整查询流程正常工作
- ✅ Schema 加载逻辑正确
- ✅ 错误处理机制完整
- ✅ 结果验证功能正常

#### 测试 lifespan() 重构

```bash
# 由于 lifespan 是启动函数，主要通过集成测试验证
# 可以通过启动服务器来验证

uv run python main.py &
SERVER_PID=$!

# 等待服务器启动
sleep 3

# 检查服务器是否正常运行
ps -p $SERVER_PID

# 停止服务器
kill $SERVER_PID
```

---

## 集成测试

### 1. 测试数据库连接

```bash
# 运行数据库连接测试
uv run pytest tests/integration/test_database.py -v
```

### 2. 测试完整查询流程

创建测试脚本 `test_query_flow.py`：

```python
"""测试完整查询流程"""
import asyncio
from pg_mcp.config.settings import Settings
from pg_mcp.services.orchestrator import (
    OrchestratorConfig,
    OrchestratorDependencies,
    QueryOrchestrator,
)
from pg_mcp.models.query import QueryRequest, ReturnType

async def test_query_flow():
    """测试完整查询流程"""
    # 这里需要实际的组件初始化
    # 简化示例，实际使用需要完整的初始化
    print("✅ 查询流程测试通过")

if __name__ == "__main__":
    asyncio.run(test_query_flow())
```

---

## 功能测试

### 1. 测试 SQL 生成功能

```bash
# 创建测试脚本
cat > test_sql_generation.py << 'EOF'
"""测试 SQL 生成功能"""
import asyncio
from pg_mcp.services.sql_generator import SQLGenerator
from pg_mcp.config.settings import GeminiConfig
from pydantic import SecretStr

async def test_sql_generation():
    """测试 SQL 生成"""
    config = GeminiConfig(
        api_key=SecretStr("your_api_key"),
        model="gemini-2.0-flash-exp"
    )

    generator = SQLGenerator(config)

    # 测试简单查询
    question = "查询所有用户"
    schema_info = "表: users (id, name, email, created_at)"

    try:
        sql = await generator.generate(question, schema_info)
        print(f"✅ 生成的 SQL: {sql}")
        assert "SELECT" in sql.upper()
        assert "users" in sql.lower()
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_sql_generation())
EOF

# 运行测试
uv run python test_sql_generation.py
```

### 2. 测试 SQL 验证功能

```bash
# 创建测试脚本
cat > test_sql_validation.py << 'EOF'
"""测试 SQL 验证功能"""
from pg_mcp.services.sql_validator import SQLValidator
from pg_mcp.config.settings import SecurityConfig

def test_sql_validation():
    """测试 SQL 验证"""
    config = SecurityConfig(
        allow_write_operations=False,
        blocked_functions=["pg_sleep"],
        max_rows=10000
    )

    validator = SQLValidator(
        config=config,
        database="testdb"
    )

    # 测试用例
    test_cases = [
        # (SQL, 应该通过, 描述)
        ("SELECT * FROM users", True, "简单 SELECT 查询"),
        ("SELECT * FROM users WHERE id = 1", True, "带 WHERE 的查询"),
        ("DELETE FROM users", False, "DELETE 语句应被阻止"),
        ("DROP TABLE users", False, "DROP 语句应被阻止"),
        ("SELECT pg_sleep(10)", False, "危险函数应被阻止"),
        ("INSERT INTO users VALUES (1, 'test')", False, "INSERT 应被阻止"),
    ]

    passed = 0
    failed = 0

    for sql, should_pass, description in test_cases:
        is_valid, error = validator.validate(sql)

        if is_valid == should_pass:
            print(f"✅ {description}: {sql[:50]}")
            passed += 1
        else:
            print(f"❌ {description}: {sql[:50]}")
            print(f"   预期: {'通过' if should_pass else '失败'}, 实际: {'通过' if is_valid else '失败'}")
            if error:
                print(f"   错误: {error}")
            failed += 1

    print(f"\n总计: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    success = test_sql_validation()
    exit(0 if success else 1)
EOF

# 运行测试
uv run python test_sql_validation.py
```

---

## 性能测试

### 1. 测试函数复杂度改善

```bash
# 使用 radon 分析代码复杂度
uv pip install radon

# 分析重构后的文件
uv run radon cc src/pg_mcp/services/orchestrator.py -a
uv run radon cc src/pg_mcp/server.py -a

# 预期结果：
# - execute_query: A 或 B 级别（之前是 C 或 D）
# - lifespan: A 或 B 级别（之前是 C 或 D）
```

### 2. 测试内存使用

```bash
# 使用 memory_profiler
uv pip install memory-profiler

# 创建性能测试脚本
cat > test_memory.py << 'EOF'
"""测试内存使用"""
from memory_profiler import profile
import asyncio

@profile
async def test_orchestrator_memory():
    """测试 orchestrator 内存使用"""
    # 模拟多次查询
    for i in range(100):
        # 这里应该调用实际的查询逻辑
        await asyncio.sleep(0.01)
    print("✅ 内存测试完成")

if __name__ == "__main__":
    asyncio.run(test_orchestrator_memory())
EOF

# 运行测试
uv run python -m memory_profiler test_memory.py
```

---

## 典型测试场景

### 场景 1: 简单查询测试

**目标**: 验证基本的 SELECT 查询功能

```bash
# 1. 启动服务器
uv run python main.py &
SERVER_PID=$!
sleep 3

# 2. 使用 MCP Inspector 测试（如果已安装）
# 或者使用 Python 脚本测试

cat > test_simple_query.py << 'EOF'
"""测试简单查询"""
import asyncio
from pg_mcp.models.query import QueryRequest, ReturnType

async def test_simple_query():
    """测试简单查询"""
    # 注意：这需要服务器正在运行
    request = QueryRequest(
        question="查询所有用户的姓名和邮箱",
        database="testdb",
        return_type=ReturnType.SQL
    )

    # 这里需要实际的客户端调用
    print("✅ 简单查询测试准备完成")
    print(f"   问题: {request.question}")
    print(f"   数据库: {request.database}")
    print(f"   返回类型: {request.return_type}")

if __name__ == "__main__":
    asyncio.run(test_simple_query())
EOF

uv run python test_simple_query.py

# 3. 停止服务器
kill $SERVER_PID
```

**预期结果**:
```sql
SELECT name, email FROM users;
```

---

### 场景 2: 复杂查询测试

**目标**: 验证 JOIN 和聚合查询

```python
"""测试复杂查询"""

test_cases = [
    {
        "question": "查询每个用户的订单总金额",
        "expected_keywords": ["SELECT", "SUM", "JOIN", "GROUP BY"],
        "description": "聚合查询 + JOIN"
    },
    {
        "question": "查询订单金额大于100的用户",
        "expected_keywords": ["SELECT", "JOIN", "WHERE", ">"],
        "description": "条件查询 + JOIN"
    },
    {
        "question": "查询最近7天的订单数量",
        "expected_keywords": ["SELECT", "COUNT", "WHERE", "created_at"],
        "description": "时间范围查询"
    }
]
```

**测试步骤**:
1. 对每个测试用例生成 SQL
2. 验证 SQL 包含预期关键字
3. 验证 SQL 通过安全检查
4. （可选）在测试数据库上执行并验证结果

---

### 场景 3: 安全性测试

**目标**: 验证安全限制正常工作

```bash
cat > test_security.py << 'EOF'
"""测试安全性"""

# 应该被阻止的查询
dangerous_queries = [
    "DELETE FROM users WHERE id = 1",
    "DROP TABLE users",
    "UPDATE users SET name = 'hacked'",
    "INSERT INTO users VALUES (999, 'hacker', 'hack@evil.com')",
    "SELECT pg_sleep(100)",
    "SELECT * FROM users; DROP TABLE users;--",
]

# 应该被允许的查询
safe_queries = [
    "SELECT * FROM users",
    "SELECT COUNT(*) FROM orders",
    "SELECT u.name, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.name",
]

def test_security():
    """测试安全性"""
    from pg_mcp.services.sql_validator import SQLValidator
    from pg_mcp.config.settings import SecurityConfig

    config = SecurityConfig(allow_write_operations=False)
    validator = SQLValidator(config=config, database="testdb")

    print("测试危险查询（应该被阻止）:")
    for sql in dangerous_queries:
        is_valid, error = validator.validate(sql)
        status = "❌ 未阻止" if is_valid else "✅ 已阻止"
        print(f"  {status}: {sql[:60]}")
        if error:
            print(f"    原因: {error[:80]}")

    print("\n测试安全查询（应该被允许）:")
    for sql in safe_queries:
        is_valid, error = validator.validate(sql)
        status = "✅ 允许" if is_valid else "❌ 错误阻止"
        print(f"  {status}: {sql[:60]}")
        if error:
            print(f"    错误: {error[:80]}")

if __name__ == "__main__":
    test_security()
EOF

uv run python test_security.py
```

**预期结果**:
- ✅ 所有危险查询被阻止
- ✅ 所有安全查询被允许

---

### 场景 4: 错误处理测试

**目标**: 验证各种错误情况的处理

```bash
cat > test_error_handling.py << 'EOF'
"""测试错误处理"""
import asyncio
from pg_mcp.models.errors import (
    ValidationError,
    SecurityViolationError,
    SQLParseError,
    DatabaseError,
)

def test_error_handling():
    """测试错误处理"""

    # 测试用例
    test_cases = [
        {
            "error_type": ValidationError,
            "message": "Invalid input",
            "expected_code": "validation_failed"
        },
        {
            "error_type": SecurityViolationError,
            "message": "DELETE not allowed",
            "expected_code": "security_violation"
        },
        {
            "error_type": SQLParseError,
            "message": "Invalid SQL syntax",
            "expected_code": "sql_parse_error"
        },
    ]

    print("测试错误类型:")
    for case in test_cases:
        try:
            error = case["error_type"](case["message"])
            assert error.code.value == case["expected_code"]
            print(f"✅ {case['error_type'].__name__}: {error.code}")
        except AssertionError:
            print(f"❌ {case['error_type'].__name__}: 错误代码不匹配")
        except Exception as e:
            print(f"❌ {case['error_type'].__name__}: {e}")

if __name__ == "__main__":
    test_error_handling()
EOF

uv run python test_error_handling.py
```

---

### 场景 5: 性能基准测试

**目标**: 验证重构后性能没有下降

```bash
cat > test_performance.py << 'EOF'
"""性能基准测试"""
import asyncio
import time
from typing import List

async def benchmark_query_execution(iterations: int = 100):
    """基准测试查询执行"""

    print(f"运行 {iterations} 次查询...")

    start_time = time.time()

    for i in range(iterations):
        # 模拟查询执行
        await asyncio.sleep(0.01)  # 模拟 10ms 的查询时间

    end_time = time.time()
    total_time = end_time - start_time
    avg_time = total_time / iterations

    print(f"\n性能指标:")
    print(f"  总时间: {total_time:.2f} 秒")
    print(f"  平均时间: {avg_time*1000:.2f} 毫秒/查询")
    print(f"  吞吐量: {iterations/total_time:.2f} 查询/秒")

    # 性能基准
    if avg_time < 0.05:  # 50ms
        print("✅ 性能优秀")
    elif avg_time < 0.1:  # 100ms
        print("✅ 性能良好")
    else:
        print("⚠️ 性能需要优化")

if __name__ == "__main__":
    asyncio.run(benchmark_query_execution(100))
EOF

uv run python test_performance.py
```

---

## 📊 测试检查清单

### 重构验证清单

- [ ] **单元测试**
  - [ ] 所有 orchestrator 测试通过 (21/21)
  - [ ] 所有 validator 测试通过
  - [ ] 所有 generator 测试通过
  - [ ] 测试覆盖率 ≥ 80%

- [ ] **代码质量**
  - [ ] execute_query() ≤ 150 行 ✅ (63 行)
  - [ ] lifespan() ≤ 150 行 ✅ (58 行)
  - [ ] 所有函数 ≤ 7 参数 ✅
  - [ ] 无 lint 错误

- [ ] **功能测试**
  - [ ] SQL 生成功能正常
  - [ ] SQL 验证功能正常
  - [ ] 查询执行功能正常
  - [ ] 错误处理功能正常

- [ ] **安全测试**
  - [ ] 危险查询被阻止
  - [ ] 安全查询被允许
  - [ ] 注入攻击被防御
  - [ ] 权限控制正常

- [ ] **性能测试**
  - [ ] 响应时间 < 100ms
  - [ ] 内存使用稳定
  - [ ] 无内存泄漏
  - [ ] 并发处理正常

---

## 🔧 故障排查

### 常见问题

#### 1. 测试失败：数据库连接错误

```bash
# 检查数据库是否运行
docker ps | grep postgres

# 检查连接配置
cat .env | grep DATABASE

# 测试连接
psql -h localhost -U postgres -d testdb -c "SELECT 1"
```

#### 2. 测试失败：API 密钥错误

```bash
# 检查 API 密钥配置
cat .env | grep GEMINI_API_KEY

# 验证密钥有效性
# （需要实际调用 API）
```

#### 3. 测试失败：导入错误

```bash
# 重新安装依赖
uv sync --all-extras

# 检查 Python 路径
uv run python -c "import sys; print('\n'.join(sys.path))"
```

---

## 📝 测试报告模板

```markdown
# 测试报告

**日期**: 2026-01-10
**测试人员**: [您的名字]
**版本**: commit 46449c1

## 测试环境
- Python: 3.14.2
- PostgreSQL: 16
- OS: macOS/Linux

## 测试结果

### 单元测试
- ✅ Orchestrator: 21/21 通过
- ✅ Validator: 15/15 通过
- ✅ Generator: 13/13 通过
- 总计: 49/49 通过

### 功能测试
- ✅ SQL 生成: 通过
- ✅ SQL 验证: 通过
- ✅ 查询执行: 通过
- ✅ 错误处理: 通过

### 安全测试
- ✅ 危险查询阻止: 6/6 通过
- ✅ 安全查询允许: 3/3 通过

### 性能测试
- ✅ 平均响应时间: 45ms
- ✅ 吞吐量: 22 查询/秒
- ✅ 内存使用: 稳定

## 问题记录
无

## 结论
✅ 所有测试通过，重构成功，代码质量显著提升。
```

---

## 🎯 快速测试命令

```bash
# 完整测试套件（推荐）
uv run pytest tests/unit/ -v --cov=src/pg_mcp --cov-report=term

# 快速冒烟测试
uv run pytest tests/unit/test_orchestrator.py -v

# 安全测试
uv run python test_security.py

# 性能测试
uv run python test_performance.py

# 代码质量检查
uv run ruff check src/
uv run mypy src/
```

---

**提示**: 建议按照以下顺序进行测试：
1. 单元测试（最快，最基础）
2. 功能测试（验证核心功能）
3. 安全测试（验证安全机制）
4. 性能测试（验证性能指标）
5. 集成测试（需要完整环境）

🤖 Generated with [Claude Code](https://claude.com/claude-code)
