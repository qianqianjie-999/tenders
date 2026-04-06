# 测试和监控工具使用指南

本指南提供了系统优化功能的测试验证、性能监控、告警配置和日志分析的详细说明。

## 📋 目录

1. [测试验证](#测试验证)
2. [性能监控](#性能监控)
3. [告警配置](#告警配置)
4. [日志分析](#日志分析)

---

## 🧪 测试验证

### 运行测试脚本

测试脚本会自动验证所有优化功能是否正常工作。

```bash
# 基本测试（默认本地服务器）
python tools/test_optimizations.py

# 测试远程服务器
python tools/test_optimizations.py http://your-server:5000
```

### 测试项目

测试脚本会验证以下功能：

1. ✅ **健康检查接口** - 验证系统健康状态
2. ✅ **系统性能指标** - 验证CPU、内存、磁盘监控
3. ✅ **告警接口** - 验证告警API功能
4. ✅ **缓存功能** - 验证Flask-Caching工作正常
5. ✅ **布隆过滤器** - 验证去重机制
6. ✅ **密码强度验证** - 验证密码验证逻辑
7. ✅ **异常处理机制** - 验证全局异常处理
8. ✅ **结构化日志** - 验证JSON格式日志

### 测试结果

测试完成后会显示：
- 总测试数
- 通过数量
- 失败数量
- 通过率
- 失败详情（如有）

---

## 📊 性能监控

### 基本监控

```bash
# 持续监控1小时，每分钟采集一次
python tools/performance_monitor.py

# 自定义监控参数
python tools/performance_monitor.py --interval 30 --duration 1800  # 30分钟，每30秒采集
```

### 仅生成报告

```bash
# 快速收集数据并生成报告
python tools/performance_monitor.py --report
```

### 监控输出

监控脚本会生成两个文件：

1. **performance_report.json** - 性能分析报告
   - CPU、内存、磁盘使用率统计
   - 平均值、最大值、最小值
   - 告警数量统计
   - 优化建议

2. **performance_chart.png** - 性能图表
   - CPU使用率趋势
   - 内存使用率趋势
   - 磁盘使用率趋势
   - 进程数量变化

### 性能指标说明

| 指标 | 说明 | 建议阈值 |
|------|------|----------|
| CPU使用率 | 系统CPU占用百分比 | < 80% |
| 内存使用率 | 系统内存占用百分比 | < 85% |
| 磁盘使用率 | 根分区磁盘占用百分比 | < 90% |
| 进程数量 | 系统运行进程总数 | 视系统而定 |

---

## 🚨 告警配置

### 交互式配置

```bash
# 启动交互式配置工具
python tools/alert_configurator.py
```

交互式菜单选项：
1. 查看当前配置
2. 修改配置
3. 应用推荐配置
4. 测试告警功能
5. 保存配置
6. 退出

### 快速配置

```bash
# 查看当前配置
python tools/alert_configurator.py --show

# 应用推荐配置
python tools/alert_configurator.py --recommend general           # 通用配置
python tools/alert_configurator.py --recommend high_performance  # 高性能服务器
python tools/alert_configurator.py --recommend low_resource      # 低资源环境
```

### 告警阈值说明

| 配置项 | 说明 | 默认值 | 推荐范围 |
|--------|------|--------|----------|
| ALERT_CPU_THRESHOLD | CPU使用率告警阈值 | 80% | 70-90% |
| ALERT_MEMORY_THRESHOLD | 内存使用率告警阈值 | 85% | 75-90% |
| ALERT_DISK_THRESHOLD | 磁盘使用率告警阈值 | 90% | 85-95% |
| ALERT_ERROR_RATE_THRESHOLD | 错误率告警阈值 | 10% | 5-15% |
| ALERT_MIN_ITEMS_PER_SECOND | 最小爬取速度 | 0.1 | 0.05-1.0 |

### 推荐配置类型

1. **general** - 通用配置
   - 适用于大多数服务器
   - 平衡性能和资源使用

2. **high_performance** - 高性能配置
   - 适用于高性能服务器
   - 更高的资源使用阈值
   - 更严格的错误率要求

3. **low_resource** - 低资源配置
   - 适用于资源受限环境
   - 较低的资源使用阈值
   - 更宽松的错误率要求

---

## 📝 日志分析

### 基本使用

```bash
# 交互式分析
python tools/log_analyzer.py /path/to/logfile.log

# 按日志级别分析
python tools/log_analyzer.py /path/to/logfile.log --level

# 按日志器分析
python tools/log_analyzer.py /path/to/logfile.log --logger

# 查找错误日志
python tools/log_analyzer.py /path/to/logfile.log --errors

# 搜索关键词
python tools/log_analyzer.py /path/to/logfile.log --search "error"
```

### 分析功能

1. **按日志级别分析**
   - 统计各级别日志数量
   - INFO、WARNING、ERROR、CRITICAL

2. **按日志器分析**
   - 统计各模块日志数量
   - 显示Top 10日志器

3. **按时间分析**
   - 按小时/天/分钟统计
   - 显示日志时间分布

4. **查找错误日志**
   - 快速定位ERROR和CRITICAL日志
   - 显示详细错误信息

5. **查找日志模式**
   - 识别常见日志模式
   - 帮助发现系统问题

6. **搜索日志**
   - 关键词搜索
   - 支持级别和日志器过滤

### 日志格式

结构化日志格式（JSON）：
```json
{
  "timestamp": "2024-01-01T12:00:00",
  "logger": "app.routes.main",
  "level": "INFO",
  "message": "用户登录成功",
  "extra": {
    "user_id": 123,
    "ip": "192.168.1.1"
  }
}
```

---

## 🔧 实际使用场景

### 场景1：部署后验证

```bash
# 1. 运行测试验证所有功能
python tools/test_optimizations.py http://your-server:5000

# 2. 检查系统健康状态
curl http://your-server:5000/api/monitor/health

# 3. 查看系统性能指标
curl http://your-server:5000/api/monitor/system
```

### 场景2：性能问题排查

```bash
# 1. 启动性能监控
python tools/performance_monitor.py --interval 10 --duration 600

# 2. 分析日志
python tools/log_analyzer.py /var/log/tenders/app.log --errors

# 3. 查看告警
curl http://your-server:5000/api/monitor/alerts
```

### 场景3：调整告警配置

```bash
# 1. 查看当前配置
python tools/alert_configurator.py --show

# 2. 根据实际情况调整
python tools/alert_configurator.py

# 3. 测试告警功能
# 在交互式菜单中选择"测试告警功能"
```

### 场景4：日常运维

```bash
# 1. 定期生成性能报告
python tools/performance_monitor.py --report

# 2. 分析日志趋势
python tools/log_analyzer.py /var/log/tenders/app.log --level

# 3. 检查系统健康
curl http://your-server:5000/api/monitor/health | jq
```

---

## 📈 监控API接口

### 健康检查
```bash
GET /api/monitor/health
```
返回系统健康状态，无需登录。

### 系统指标
```bash
GET /api/monitor/system
```
返回CPU、内存、磁盘等系统性能指标，需要登录。

### 告警列表
```bash
GET /api/monitor/alerts?level=error&limit=50
```
返回告警列表，支持按级别过滤，需要登录。

### 指标摘要
```bash
GET /api/monitor/summary
```
返回性能指标摘要统计，需要登录。

---

## ⚠️ 注意事项

1. **测试环境优先**
   - 先在测试环境验证所有功能
   - 确认无问题后再部署到生产环境

2. **监控频率**
   - 不要设置过高的监控频率
   - 建议间隔至少30秒

3. **日志文件大小**
   - 定期清理或归档日志文件
   - 避免磁盘空间不足

4. **告警阈值**
   - 根据实际服务器配置调整
   - 避免误报或漏报

5. **性能影响**
   - 监控本身会消耗一定资源
   - 在高负载时适当降低监控频率

---

## 🆘 故障排查

### 问题1：测试失败

**可能原因：**
- 服务器未启动
- 网络连接问题
- 依赖包未安装

**解决方案：**
```bash
# 检查服务器状态
systemctl status httpd

# 检查依赖
pip install -r requirements.txt

# 检查网络
curl http://localhost:5000/api/monitor/health
```

### 问题2：监控无数据

**可能原因：**
- psutil未安装
- 权限不足

**解决方案：**
```bash
# 安装psutil
pip install psutil

# 检查权限
ls -la /proc/
```

### 问题3：告警不触发

**可能原因：**
- 阈值设置过高
- 监控未启动

**解决方案：**
```bash
# 检查配置
python tools/alert_configurator.py --show

# 手动测试告警
curl -X POST http://localhost:5000/api/monitor/alerts/test
```

---

## 📚 相关文档

- [优化总结](../docs/OPTIMIZATION_SUMMARY.md)
- [部署指南](../docs/DEPLOYMENT.md)
- [API文档](../docs/API.md)
