# -*- coding: utf-8 -*-
"""AI 分析结果桥接服务（G1 转单回填 / G2 人工上传共用）。

设计约束（实现期实测，见 docs/AI_IMPLEMENTATION_SPEC.md §8）：
1. 只反查已落库的 ai_analysis JSON，不在请求内抓正文、下附件或调模型。
2. 三张主表 detail_url 为 utf8mb4_unicode_ci，analysis_projects 为
   utf8mb4_general_ci；跨表等值 JOIN 会报 MySQL 1267。这里一律用
   「参数化单表查询」，绝不做跨表列比较。
3. 结论文本统一限长 < 60,000 字节：生产 MariaDB 10.11.14 为
   STRICT_TRANS_TABLES，TEXT 65,536 B 会报 1406（不是静默截断）。
4. 拼接结果只含纯文本与换行，不生成任何 HTML；转义由前端负责。
"""
import datetime
import json
import re
from decimal import Decimal, InvalidOperation

MAIN_TABLES = ('bidding_info', 'jiangsu_bidding_info', 'zhejiang_bidding_info')
MAX_CONTENT_BYTES = 60000
AI_TAG = '\u3014AI \u5206\u6790\u56de\u586b\u3015'
UPLOAD_TAG = '\u3014\u4eba\u5de5\u4e0a\u4f20\u9644\u4ef6\u89e3\u6790\u3015'

_NUM_RE = re.compile(r'\d[\d,]*(?:\.\d+)?')
_AMOUNT_RE = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(\u4ebf\u5143|\u4e07\u5143|\u4e07|\u5143)')
_VAGUE_RE = re.compile(
    r'\u8be6\u89c1|\u4ee5.{0,8}\u4e3a\u51c6|\u89c1\u9644\u4ef6|\u53e6\u884c|\u6807\u6bb5|'
    r'\u5206\u9879|\u5305\u542b|\u4e0d\u542b|\u6682\u65e0|\u672a\u786e\u5b9a')
_UNIT_FACTOR = {
    '\u5143': Decimal('1'),
    '\u4e07': Decimal('10000'),
    '\u4e07\u5143': Decimal('10000'),
    '\u4ebf\u5143': Decimal('100000000'),
}
# decimal(15,2)：整数部分最多 13 位
_DECIMAL_CEILING = Decimal('10000000000000')


def truncate_utf8(text, limit=MAX_CONTENT_BYTES):
    """按 UTF-8 字节截断，不切断多字节字符。"""
    if text is None:
        return ''
    s = str(text)
    raw = s.encode('utf-8')
    if len(raw) <= limit:
        return s
    return raw[:limit].decode('utf-8', errors='ignore')


def normalize_budget(raw):
    """自由文本预算 -> 唯一金额 Decimal；任何歧义一律返回 None。

    "20万元" -> 200000.00；"1,234.56元" -> 1234.56。
    多金额 / 区间 / 多标段 / 含「详见」/ 单位不明 / 越界 -> None。
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in ('\u672a\u83b7\u53d6', '\u65e0', '-', '/', 'N/A'):
        return None
    if _VAGUE_RE.search(s):
        return None
    # 全文数字必须恰好一个：区间(20-30万)、多标段、夹带日期都由此排除
    if len(_NUM_RE.findall(s)) != 1:
        return None
    m = _AMOUNT_RE.search(s)
    if not m:
        return None
    # 数字+单位之外只允许少量修饰（最高限价/约/括号备注等），
    # 剩余文字过长说明还有别的金额表述，判歧义
    rest = (s[:m.start()] + s[m.end():]).strip()
    if len(rest) > 12:
        return None
    try:
        value = Decimal(m.group(1).replace(',', '')) * _UNIT_FACTOR[m.group(2)]
        value = value.quantize(Decimal('0.01'))
    except (InvalidOperation, KeyError, ValueError):
        return None
    if value <= 0 or value >= _DECIMAL_CEILING:
        return None
    return value


def normalize_deadline(raw):
    """投标截止时间 -> YYYY-MM-DD 字符串；非法返回 None。

    语义注意：源字段是投标截止时间，不是开标日，结论里必须标注。
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.startswith('\u672a\u83b7\u53d6'):
        return None
    head = s[:10]
    try:
        return datetime.date.fromisoformat(head).isoformat()
    except ValueError:
        pass
    m = re.match(r'^(\d{4})[-/\u5e74](\d{1,2})[-/\u6708](\d{1,2})', s)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def _as_text(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _as_lines(v):
    """容忍 str / list / None / dict；空值统一返回空列表。"""
    if not v:
        return []
    if isinstance(v, str):
        s = v.strip()
        if not s or s.startswith('\u672a\u83b7\u53d6'):
            return []
        return [s]
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if x is not None and str(x).strip()]
    if isinstance(v, dict):
        return [str(x).strip() for x in v.values() if x is not None and str(x).strip()]
    return []


def _parse_ai(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, (bytes, bytearray)):
        v = v.decode('utf-8', 'ignore')
    if isinstance(v, str):
        try:
            obj = json.loads(v)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def lookup_ai_result(cursor, detail_url, project_name=None, publish_date=None):
    """按 detail_url 逐表反查 ok 的 AI 结果；查不到再试 (项目名, 发布日期)。

    返回 {'table', 'rid', 'ai', 'analyzed_at'} 或 None。
    表名来自白名单常量，值一律参数化，避免 1267 与注入。
    """
    queries = []
    if detail_url:
        queries.append(('detail_url = %s', (str(detail_url).strip(),)))
    if project_name and publish_date:
        queries.append(('project_name = %s AND publish_date = %s',
                        (str(project_name).strip(), publish_date)))
    if not queries:
        return None

    for where, params in queries:
        for table in MAIN_TABLES:
            sql = ("SELECT id, ai_analysis, ai_analyzed_at FROM `%s` "
                   "WHERE %s AND ai_analysis_status = 'ok' "
                   "AND ai_analysis IS NOT NULL "
                   "ORDER BY ai_analyzed_at DESC, id DESC LIMIT 1" % (table, where))
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if not row:
                continue
            ai = _parse_ai(row.get('ai_analysis'))
            if not ai:
                continue
            at = row.get('ai_analyzed_at')
            return {
                'table': table,
                'rid': row.get('id'),
                'ai': ai,
                'analyzed_at': at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(at, 'strftime') else '',
            }
    return None


def build_summary(ai, model='', analyzed_at=''):
    """拼接纯文本结论；固定段序，容忍空数组，末尾附溯源。"""
    budget_raw = _as_text(ai.get('budget'))
    deadline_raw = _as_text(ai.get('deadline'))
    lines = [AI_TAG]

    summary = _as_text(ai.get('summary'))
    if summary:
        lines.append('\u6458\u8981\uff1a' + summary)

    for label, key in (('\u98ce\u9669', 'risk'),
                       ('\u5408\u89c4', 'compliance'),
                       ('\u8bc4\u5206', 'scoring')):
        items = _as_lines(ai.get(key))
        if items:
            lines.append(label + '\uff1a')
            lines.extend('  - ' + x for x in items)

    lines.append('--- \u6eaf\u6e90 ---')
    lines.append('\u6a21\u578b\uff1a' + (_as_text(model) or '\u672a\u8bb0\u5f55'))
    lines.append('\u5206\u6790\u65f6\u95f4\uff1a' + (_as_text(analyzed_at) or '\u672a\u8bb0\u5f55'))
    if budget_raw:
        lines.append('\u9884\u7b97\u539f\u6587\uff1a' + budget_raw)
    if deadline_raw:
        lines.append('\u622a\u6b62\u65f6\u95f4\u539f\u6587\uff1a' + deadline_raw
                     + '\uff08\u6e90\u5b57\u6bb5\u4e3a\u6295\u6807\u622a\u6b62\u65f6\u95f4\uff0c\u975e\u5f00\u6807\u65e5\uff09')
    lines.append('\u7ed3\u6784\u5316\u5b57\u6bb5\u7531\u7cfb\u7edf\u53cd\u67e5\u56de\u586b\uff0c\u4eba\u5de5\u53ef\u4fee\u6539\uff1b\u6295/\u4e0d\u6295\u51b3\u7b56\u4e0d\u81ea\u52a8\u5199\u5165\u3002')
    return truncate_utf8('\n'.join(lines))


def _tenderer(ai):
    """只取 purchaser；agency 是代理机构，绝不映射到 tenderer。"""
    v = _as_text(ai.get('purchaser'))
    if not v or v.startswith('\u672a\u83b7\u53d6'):
        return None
    return v[:200] or None


def fill_from_ai(cursor, analysis_id, detail_url,
                 project_name=None, publish_date=None, model=''):
    """G1 主逻辑：在调用方事务内反查并回填；异常由调用方兜底。

    返回状态字典，供接口/日志使用。不抛异常给转单主流程。
    """
    cursor.execute("SELECT analysis_content FROM analysis_projects WHERE id = %s",
                   (analysis_id,))
    row = cursor.fetchone() or {}
    if (row.get('analysis_content') or '').strip():
        return {'filled': False, 'reason': 'manual_content_exists'}

    hit = lookup_ai_result(cursor, detail_url, project_name, publish_date)
    if not hit:
        return {'filled': False, 'reason': 'no_ai_result'}

    ai = hit['ai']
    content = build_summary(ai, model=model, analyzed_at=hit['analyzed_at'])
    cursor.execute(
        "UPDATE analysis_projects "
        "SET control_price = %s, bid_open_date = %s, tenderer = %s, "
        "    analysis_content = %s, updated_time = NOW() "
        "WHERE id = %s",
        (normalize_budget(ai.get('budget')),
         normalize_deadline(ai.get('deadline')),
         _tenderer(ai),
         content,
         analysis_id))
    return {
        'filled': True,
        'source_table': hit['table'],
        'source_rid': hit['rid'],
        'control_price': str(normalize_budget(ai.get('budget')) or ''),
        'bid_open_date': normalize_deadline(ai.get('deadline')) or '',
        'tenderer': _tenderer(ai) or '',
        'bytes': len(content.encode('utf-8')),
    }


def append_uploaded_text(existing, new_text, filename=''):
    """G2：人工主动上传是追加语义（区别于 G1 的 AI 自动回填非空不覆盖）。

    总长始终 <= MAX_CONTENT_BYTES；空间不足时保留已有人工结论。
    """
    head = (existing or '').rstrip()
    block = (UPLOAD_TAG + _as_text(filename) + '\n' + (new_text or '').strip()).strip()
    if not block:
        return truncate_utf8(head)
    if not head:
        return truncate_utf8(block)
    sep = '\n'
    room = MAX_CONTENT_BYTES - len(head.encode('utf-8')) - len(sep.encode('utf-8'))
    if room <= 0:
        return truncate_utf8(head)
    return truncate_utf8(head + sep + truncate_utf8(block, room))
