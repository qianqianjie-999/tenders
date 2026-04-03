# 用户登录系统使用说明

## 概述

分析标书页面 (`/analysis/`) 和投标页面 (`/bidding/`) 已添加用户名 + 密码登录保护，防止未授权访问。

## 快速开始

### 1. 生成密码哈希

使用提供的工具脚本生成密码哈希：

```bash
# 方法一：交互式输入
python tools/generate_password.py

# 方法二：命令行参数
python tools/generate_password.py admin admin123
```

示例输出：
```
============================================================
密码哈希生成工具
============================================================

用户名：admin
密码哈希：pbkdf2:sha256:600000$...

配置示例（添加到 .env 文件）：
------------------------------------------------------------
USERS_CONFIG=admin:pbkdf2:sha256:600000$...
------------------------------------------------------------
```

### 2. 配置用户

编辑 `.env` 文件，添加用户配置：

```env
# 单个用户
USERS_CONFIG=admin:pbkdf2:sha256:600000$4x78kXrMugIOo5lq$be349a94d55cf9e1c78992e96c37925823efa1508a4a127d4b8e7fb3961ae734

# 多个用户（用分号分隔）
USERS_CONFIG=admin:hash1;user2:hash2;user3:hash3
```

### 3. 重启 Flask 服务

```bash
cd flask_web
python run.py
```

### 4. 访问受保护页面

访问以下页面会自动重定向到登录页：
- `/analysis/` - 分析标书页面
- `/analysis/api/detail/<id>` - 查看詳情
- `/analysis/api/update/<id>` - 更新信息
- `/analysis/api/delete/<id>` - 删除记录
- `/bidding/` - 投标项目页面
- `/bidding/api/detail/<id>` - 查看詳情
- `/bidding/api/update/<id>` - 更新信息
- `/bidding/api/convert/<id>` - 转换为投标项目

### 5. 登录

1. 访问 `/auth/login`
2. 输入用户名和密码
3. 点击"登录"按钮
4. 登录成功后会自动跳转到首页

### 6. 退出登录

点击右上角的用户名或访问 `/auth/logout` 退出登录。

---

## 受保护的操作

以下操作需要登录后才能执行：

### 分析标书页面
- 查看项目详情
- 更新分析信息（决定、原因、分析内容等）
- 删除分析项目
- 转换为投标项目

### 投标项目页面
- 查看项目详情
- 更新投标信息（报价、状态、总结等）

### 自动记录操作人

登录后，所有更新操作会自动记录当前登录用户名为操作人，无需手动填写。

---

## 多用户管理

### 添加新用户

1. 生成新用户的密码哈希：
   ```bash
   python tools/generate_password.py newuser password123
   ```

2. 编辑 `.env` 文件，添加新用户：
   ```env
   USERS_CONFIG=admin:hash1;newuser:hash2
   ```

3. 重启 Flask 服务

### 修改密码

1. 生成新的密码哈希
2. 更新 `.env` 文件中的 `USERS_CONFIG`
3. 重启 Flask 服务

### 删除用户

从 `.env` 文件的 `USERS_CONFIG` 中删除相应用户 entry，重启服务即可。

---

## 安全建议

1. **不要使用弱密码**：密码应至少 8 位，包含大小写字母、数字和特殊字符
2. **定期更换密码**：建议每 3 个月更换一次
3. **不要共享账号**：每个用户应有独立账号，便于追踪操作记录
4. **生产环境使用 HTTPS**：防止密码在传输过程中被窃取
5. **不要提交 `.env` 文件到 Git**：`.env` 包含敏感信息，已在 `.gitignore` 中忽略

---

## 故障排除

### 问题：无法登录，提示"用户名或密码错误"

**解决方法**：
1. 检查 `.env` 文件中的 `USERS_CONFIG` 格式是否正确
2. 确认密码哈希生成正确
3. 检查 Flask 服务是否已重启（修改 `.env` 后需要重启）

### 问题：访问页面没有重定向到登录页

**解决方法**：
1. 清除浏览器缓存和 Cookie
2. 检查是否已经登录
3. 确认 `@login_required` 装饰器已正确添加

### 问题：登录后操作人显示错误

**解决方法**：
1. 确认已正确登录
2. 检查 session 是否过期
3. 重新登录后重试

---

## 技术细节

- **认证框架**：Flask-Login 0.6.3
- **密码加密**：Werkzeug 的 `generate_password_hash` / `check_password_hash`
- **会话管理**：基于 Cookie 的 session
- **"记住我"功能**：支持长期会话（默认 1 年）

---

## 从旧版本升级

如果您之前使用访问口令 (`ANALYSIS_ACCESS_CODE`) 系统：

1. 保留 `ANALYSIS_ACCESS_CODE` 配置（向后兼容）
2. 添加 `USERS_CONFIG` 配置启用新登录系统
3. 前端页面会自动使用新的登录系统
4. API 接口的 `X-Access-Code` 验证已移除，改为 `@login_required` 装饰器

---

## 文件结构

```
flask_web/
├── app/
│   ├── models/
│   │   └── user.py              # 用户模型
│   ├── services/
│   │   └── auth_service.py      # 认证服务
│   ├── routes/
│   │   ├── auth.py              # 认证路由
│   │   ├── analysis.py          # 分析标书路由（已添加登录保护）
│   │   └── bidding.py           # 投标项目路由（已添加登录保护）
│   └── __init__.py              # Flask 应用初始化
└── templates/
    └── auth/
        └── login.html           # 登录页面
tools/
└── generate_password.py         # 密码生成工具
```
