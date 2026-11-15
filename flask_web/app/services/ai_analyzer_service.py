# -*- coding: utf-8 -*-
"""AI 分析服务

调用本地 Ollama（OpenAI 兼容接口）对招标公告正文做结构化分析，结果写回
ai_analysis / ai_analysis_status / ai_analyzed_at。

环境变量（可写在 tenders/.env）：
    AI_BASE_URL   默认 http://127.0.0.1:11434/v1
    AI_MODEL      默认 qwen3.8:27b
    AI_API_KEY    默认空（本地 Ollama 不校验）
    AI_TIMEOUT    默认 180 秒
"""
import json
import os
import re
import threading
import time
import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.extensions import get_db_connection

# 3 张表 -> 详情页域名前缀（仅用于页面展示时拼链接，不参与请求）
TABLE_PROJECTS = {
    'bidding_info': '山东',
    'jiangsu_bidding_info': '江苏',
    'zhejiang_bidding_info': '浙江',
}

VALID_TABLES = tuple(TABLE_PROJECTS.keys())

ANNOUNCEMENT_TYPES = ['中标公告', '竞争性谈判', '公开招标', '询价公告', '废标公告', '其他']
FOCUS_CATEGORIES = ['交通', '智能化', '信号灯', '监控']

SYSTEM_PROMPT = (
    '你是招投标公告分析助手。只输出 JSON，不要输出任何解释文字、不要使用 Markdown 代码块。'
)

USER_PROMPT_TMPL = """请从下面这条招标公告中抽取核心指标并做业务解读，输出严格 JSON 对象（不要任何额外文字，不要 Markdown 代码块）：

{{
  "project_name": "项目名称，去掉「招标公告/竞争性磋商公告/采购公告」等后缀，只保留项目本体；找不到填 未获取",
  "purchaser": "招标人/采购人/建设单位全称（不要填代理机构），找不到填 未获取",
  "agency": "招标代理机构全称，找不到填 未获取",
  "method": "采购方式，从[公开招标/邀请招标/竞争性磋商/竞争性谈判/单一来源/询价/框架协议/竞价/比选/其他]选一个；未获取填 未获取",
  "budget": "预算金额/最高限价/招标控制价/合同估算价，如 800万元 / 260万元；只给数字+单位；未获取填 未获取",
  "deadline": "投标（响应）文件递交截止时间，格式如 2026-11-20 17:00；若只有相对表述(如 5 日内)按发布日期推算；未获取填 未获取",
  "qualification": "投标人资格要求要点，用 1-3 句中文概括（资质等级、类似业绩、财务、信用记录、项目负责人等）；未获取填 未获取",
  "announcement_type": "从[{types}]中选一个",
  "project_type": "项目类型，如 智能交通/视频监控/安防监控/信息化系统/道路工程/市政工程/设备采购/运维服务/其他",
  "summary": "100-200字中文项目简介，一段话，不要换行",
  "keywords": ["5到12个中文关键词"],
  "categories": {{"交通": true/false, "智能化": true/false, "信号灯": true/false, "监控": true/false}},
  "relevance": 1到10的整数,
  "risk": "针对「交通智能化/信号灯/监控」业务的风险或不确定点，1-3条中文短语，每条 ≤ 25 字，例如：预算偏紧/技术门槛不明/资质要求高/地域限制/时间紧张；若无明显风险则填 无明显风险",
  "compliance": "合规提示，1-3条短语，例如：需具备安防工程资质/需当地业绩/需一般纳税人/需投标保证金；无则填 无特殊合规要求",
  "scoring": "评分规则要点解读，1-3条短语，例如：价格分占 30%、技术分占 50%/业绩加分/本地服务加分；无则填 需查招标文件"
}}

硬性要求：
1. 金额、日期、单位名称、资质条款必须来自公告原文，禁止推测或编造；原文没有就填 未获取。
2. purchaser 与 agency 要区分：招标人/采购人是采购方，代理机构是受托组织招标的公司。
3. relevance 表示与「交通智能化 / 监控 / 智能化 / 交警 / 交管 / 公安局」业务的相关程度，10 为高度相关。
4. risk、compliance、scoring 每条字符串尽量短，不要换行。

公告标题：{title}
公告正文：
{content}
"""

# 标题关键词兜底：采购方式在标题里通常写作「XX项目公开招标公告」
METHOD_KEYWORDS = (
    ('竞争性磋商', '竞争性磋商'), ('磋商', '竞争性磋商'),
    ('竞争性谈判', '竞争性谈判'), ('谈判', '竞争性谈判'),
    ('单一来源', '单一来源'), ('询价', '询价'),
    ('邀请招标', '邀请招标'), ('公开招标', '公开招标'),
    ('框架协议', '框架协议'), ('竞价', '竞价'), ('比选', '比选'),
)


def method_from_title(title: str) -> str:
    """从标题解析采购方式（确定性规则，仅用于 AI 未给出时的兜底）。"""
    t = title or ''
    for kw, val in METHOD_KEYWORDS:
        if kw in t:
            return val
    return ''


# ----------------------------------------------------------------- 配置
def _cfg(name: str, default: str = '') -> str:
    return (os.environ.get(name) or default).strip()


def ai_config() -> Dict[str, Any]:
    return {
        'base_url': _cfg('AI_BASE_URL', 'http://127.0.0.1:11434/v1').rstrip('/'),
        'model': _cfg('AI_MODEL', 'qwen3.8:27b'),
        'api_key': _cfg('AI_API_KEY', ''),
        'timeout': int(_cfg('AI_TIMEOUT', '180') or 180),
    }


# ----------------------------------------------------------------- G3 健康检查 / 错误分类
_UNAVAILABLE_HINTS = (
    'ConnectionError', 'ConnectTimeout', 'ReadTimeout', 'Timeout',
    'ConnectionRefused', 'NameResolutionError', 'Max retries',
    'NewConnectionError', 'ProtocolError', 'RemoteDisconnected',
)
_health_cache: Dict[str, Any] = {'at': 0.0, 'value': None}


def _health_url() -> str:
    """AI_BASE_URL 的 /v1 前缀换成 Ollama 的轻量 /api/tags 端点。"""
    base = ai_config()['base_url']
    return base.rsplit('/v1', 1)[0].rstrip('/') + '/api/tags'


def check_model_health(force: bool = False, ttl: float = 60.0,
                       timeout: float = 3.0) -> Dict[str, Any]:
    """短超时探测模型主机；结果缓存 ttl 秒，避免页面每次请求都等 3 秒。

    不新增配置项：探测超时是固定短值，批量分析仍用 AI_TIMEOUT。
    """
    now = time.time()
    if (not force and _health_cache['value'] is not None
            and now - _health_cache['at'] < ttl):
        return dict(_health_cache['value'])

    url = _health_url()
    result: Dict[str, Any] = {
        'reachable': False,
        'status': 'unavailable',
        'message': '',
        'url': url,
        'model': ai_config()['model'],
        'checked_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code < 400:
            result.update(reachable=True, status='ok', message='模型服务在线')
        else:
            result.update(status='failed',
                          message='健康检查 HTTP %s' % resp.status_code)
    except Exception as e:
        result['message'] = '模型主机关机或服务不可达（%s）' % type(e).__name__

    _health_cache['at'] = now
    _health_cache['value'] = result
    try:
        _set_state(model_status=result['status'])
    except Exception:
        pass
    return dict(result)


def classify_error(err: Optional[str]) -> str:
    """unavailable（可重试，不写 failed） / bad_request / failed。"""
    s = str(err or '')
    if any(h in s for h in _UNAVAILABLE_HINTS):
        return 'unavailable'
    m = re.search(r'\b([45]\d{2})\b', s)
    if m:
        return 'bad_request' if m.group(1).startswith('4') else 'failed'
    return 'failed'


# ----------------------------------------------------------------- 解析
_FENCE_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.IGNORECASE)


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """从模型输出里挖出第一个完整 JSON 对象。"""
    if not raw:
        return None
    text = _FENCE_RE.sub('', raw.strip()).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    # 退化为括号扫描
    start = text.find('{')
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None


def _clean_str(v: Any, cap: int = 200) -> str:
    s = str(v or '').strip().replace('\n', ' ')
    if len(s) > cap:
        s = s[:cap]
    return s


def _clean_list(v: Any, cap_each: int = 60, max_n: int = 5) -> List[str]:
    """把模型输出的数组/字符串规整成列表。"""
    out: List[str] = []
    if isinstance(v, str):
        # 模型可能把数组输出成字符串（如 "a/b/c" 或 "a, b, c"）
        s = v.strip()
        # 若整体为「无明显风险 / 无特殊合规要求 / 需查招标文件 / 未获取」这类占位
        if s in ('', '无明显风险', '无特殊合规要求', '需查招标文件', '未获取', '无', 'N/A'):
            return []
        for part in re.split(r'[;；、,，|/]+', s):
            p = _clean_str(part, cap_each)
            if p and p not in out:
                out.append(p)
        return out[:max_n]
    if isinstance(v, list):
        for x in v:
            p = _clean_str(x, cap_each)
            if not p:
                continue
            if p in ('无明显风险', '无特殊合规要求', '需查招标文件', '未获取', '无'):
                continue
            if p not in out:
                out.append(p)
        return out[:max_n]
    return []


def normalize_analysis(obj: Dict[str, Any]) -> Dict[str, Any]:
    """把模型输出规整成固定结构，缺字段给默认值。"""
    ann = str(obj.get('announcement_type') or '').strip()
    if ann not in ANNOUNCEMENT_TYPES:
        # 模糊匹配，如「中标（成交）公告」
        for t in ANNOUNCEMENT_TYPES:
            if t[:2] and t[:2] in ann:
                ann = t
                break
        else:
            ann = '其他'

    summary = str(obj.get('summary') or '').strip().replace('\n', ' ')
    if len(summary) > 260:
        summary = summary[:260]

    kws: List[str] = []
    raw_kws = obj.get('keywords') or []
    if isinstance(raw_kws, str):
        raw_kws = re.split(r'[，,、;；\s]+', raw_kws)
    if isinstance(raw_kws, list):
        for k in raw_kws:
            k = str(k).strip()
            if k and k not in kws:
                kws.append(k)
    kws = kws[:15]

    cats_in = obj.get('categories') or {}
    cats: Dict[str, bool] = {}
    if isinstance(cats_in, dict):
        for c in FOCUS_CATEGORIES:
            v = cats_in.get(c)
            cats[c] = bool(v) if v is not None else False
    elif isinstance(cats_in, list):
        joined = ''.join(str(x) for x in cats_in)
        cats = {c: (c in joined) for c in FOCUS_CATEGORIES}
    else:
        cats = {c: False for c in FOCUS_CATEGORIES}

    try:
        rel = int(round(float(obj.get('relevance'))))
    except Exception:
        rel = 1
    rel = max(1, min(10, rel))

    return {
        'project_name': _clean_str(obj.get('project_name'), cap=200) or '未获取',
        'purchaser': _clean_str(obj.get('purchaser'), cap=200) or '未获取',
        'agency': _clean_str(obj.get('agency'), cap=200) or '未获取',
        'method': _clean_str(obj.get('method'), cap=30) or '未获取',
        'budget': _clean_str(obj.get('budget'), cap=80) or '未获取',
        'deadline': _clean_str(obj.get('deadline'), cap=40) or '未获取',
        'qualification': _clean_str(obj.get('qualification'), cap=500) or '未获取',
        'announcement_type': ann,
        'project_type': str(obj.get('project_type') or '其他').strip()[:50],
        'summary': summary,
        'keywords': kws,
        'categories': cats,
        'relevance': rel,
        'risk': _clean_list(obj.get('risk'), cap_each=60, max_n=5),
        'compliance': _clean_list(obj.get('compliance'), cap_each=60, max_n=5),
        'scoring': _clean_list(obj.get('scoring'), cap_each=70, max_n=5),
        'model': ai_config()['model'],
    }


# ----------------------------------------------------------------- 单条分析
def _call_model(user_prompt: str, max_tokens: int = 2000) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """调用本地模型并解析 JSON，返回 (obj, 错误信息)。"""
    cfg = ai_config()
    payload = {
        'model': cfg['model'],
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.1,
        # qwen3.8 是思考型模型：不关思考时 token 全耗在 reasoning 上，
        # content 会是空串（表现为「分析失败」）。think=False + 足够额度。
        'max_tokens': max_tokens,
        'stream': False,
        'think': False,
        'response_format': {'type': 'json_object'},
    }
    headers = {'Content-Type': 'application/json'}
    if cfg['api_key']:
        headers['Authorization'] = f"Bearer {cfg['api_key']}"

    url = f"{cfg['base_url']}/chat/completions"

    def _post(p):
        return requests.post(url, json=p, headers=headers, timeout=cfg['timeout'])

    try:
        resp = _post(payload)
        if resp.status_code >= 400:
            # 部分 Ollama 版本不支持 response_format / think，逐项去掉重试
            p2 = dict(payload)
            p2.pop('response_format', None)
            resp = _post(p2)
            if resp.status_code >= 400:
                p3 = dict(p2)
                p3.pop('think', None)
                resp = _post(p3)
        resp.raise_for_status()
        data = resp.json()
        choice = (data.get('choices') or [{}])[0]
        msg = choice.get('message', {}) or {}
        raw = msg.get('content') or ''
        # 思考型模型偶发 content 为空、正文落在 reasoning 里
        if not raw.strip():
            raw = msg.get('reasoning') or msg.get('reasoning_content') or ''
        if not raw.strip():
            return None, (f"模型未返回内容(finish_reason={choice.get('finish_reason')})")
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'

    obj = _extract_json(raw)
    if not obj:
        return None, f'模型输出不是合法 JSON: {(raw or "")[:200]}'
    return obj, None


def analyze_text(title: str, content: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """调用本地模型分析一条公告。返回 (结果, 错误信息)。"""
    body_text = (content or '').strip()
    if not body_text:
        body_text = title or ''
    # 控制上下文长度：本地模型运行时窗口 64K，12000 字约 8-10K token，留足余量
    if len(body_text) > 12000:
        body_text = body_text[:7000] + '\n……\n' + body_text[-4500:]

    obj, err = _call_model(USER_PROMPT_TMPL.format(
        types='/'.join(ANNOUNCEMENT_TYPES),
        title=(title or '')[:200],
        content=body_text,
    ))
    if obj is None:
        return None, err

    result = normalize_analysis(obj)
    # 兜底：项目名称取公告标题（去掉公告后缀），采购方式从标题关键词解析
    if result['project_name'] == '未获取' and title:
        result['project_name'] = _clean_str(re.sub(
            r'(招标公告|竞争性磋商公告|竞争性谈判公告|询价公告|采购公告|公开招标公告)$', '', title.strip()),
            cap=200) or '未获取'
    if result['method'] == '未获取':
        m = method_from_title(title)
        if m:
            result['method'] = m
    return result, None


# ----------------------------------------------------------------- 关键词命中 + 深入分析
DEEP_PROMPT_TMPL = """你是投标顾问。下面是招标公告的已抽取指标、AI 初判结果，以及我方公司的资质情况。
请判断我方能否参与投标，并给出可执行的投标策略。输出严格 JSON（不要任何额外文字）：

{{
  "fit_score": 1到10的整数（我方与该项目匹配度）,
  "qualification_match": [{{"requirement": "招标文件的资格要求要点（原文口径）", "status": "满足/不满足/需确认", "note": "判断依据，≤40字"}}],
  "scoring_analysis": ["评分规则解读与我方优劣势，1-3条，每条≤40字"],
  "bid_advice": ["投标策略/报价/材料准备建议，1-4条，每条≤40字"],
  "gaps": ["必须补齐的差距或风险，1-3条，每条≤40字"],
  "summary": "80-120字结论：是否建议投标、关键前提"
}}

规则：
1. 资格要求逐条对照我方资质：有明确依据才写 满足，缺证据一律写 需确认，禁止臆断。
2. 我方资料缺失时，在 note 里写明需要补充什么材料。
3. 只依据给定信息判断，不要编造证书、业绩或评分条款。

【招标公告】
标题：{title}
已抽取指标：{indicators}

【我方公司情况】
{company}

公告正文（节选）：
{content}
"""

COMPANY_FIELDS = ['company_name', 'qualifications', 'certificates',
                  'performance', 'personnel', 'finance', 'advantages']
COMPANY_LABELS = {
    'company_name': '公司名称',
    'qualifications': '资质证书（如安防、电子与智能化、建筑智能化、信息系统集成等）',
    'certificates': '体系认证/信用（如 ISO、CMMI、信用等级）',
    'performance': '类似业绩（近三年同类项目）',
    'personnel': '人员团队（项目经理、技术负责人及其证书）',
    'finance': '财务与信用（营收、纳税、无重大违法记录）',
    'advantages': '核心优势与短板',
}


def load_keywords() -> List[str]:
    """读取后台维护的高亮关键词（命中即触发深入分析）。"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT keyword FROM highlight_keywords WHERE keyword IS NOT NULL AND keyword <> ''")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [str(r['keyword']).strip() for r in rows if str(r['keyword']).strip()]
    except Exception:
        return []


def match_keywords(text: str, keywords: List[str]) -> List[str]:
    """返回正文/标题命中的关键词。"""
    hay = text or ''
    return [k for k in keywords if k and k in hay]


def ensure_company_table():
    """公司资质档案表（单行 id=1），首次访问自动建表。"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS company_profile ("
            " id TINYINT PRIMARY KEY,"
            " company_name VARCHAR(200) NOT NULL DEFAULT '',"
            " qualifications TEXT,"
            " certificates TEXT,"
            " performance TEXT,"
            " personnel TEXT,"
            " finance TEXT,"
            " advantages TEXT,"
            " updated_at DATETIME NULL"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='我方公司资质档案'")
        cur.execute("INSERT IGNORE INTO company_profile (id) VALUES (1)")
        conn.commit()
        cur.close()
    finally:
        conn.close()


def load_company_profile() -> Dict[str, str]:
    try:
        ensure_company_table()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM company_profile WHERE id=1")
        row = cur.fetchone() or {}
        cur.close()
        conn.close()
        return {k: str(row.get(k) or '').strip() for k in COMPANY_FIELDS}
    except Exception:
        return {k: '' for k in COMPANY_FIELDS}


def save_company_profile(data: Dict[str, Any]) -> Dict[str, str]:
    ensure_company_table()
    values = {k: str(data.get(k) or '').strip()[:2000] for k in COMPANY_FIELDS}
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE company_profile SET company_name=%s, qualifications=%s, certificates=%s,"
            " performance=%s, personnel=%s, finance=%s, advantages=%s, updated_at=%s WHERE id=1",
            (values['company_name'], values['qualifications'], values['certificates'],
             values['performance'], values['personnel'], values['finance'],
             values['advantages'], datetime.datetime.now()))
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return values


def _company_text(company: Dict[str, str]) -> str:
    lines = []
    for k in COMPANY_FIELDS:
        v = (company or {}).get(k)
        if v:
            lines.append(f"{COMPANY_LABELS.get(k, k)}：{v}")
    return '\n'.join(lines) if lines else '（我方公司资质档案尚未填写，全部资格项按 需确认 处理）'


def normalize_deep(obj: Dict[str, Any]) -> Dict[str, Any]:
    try:
        fit = int(round(float(obj.get('fit_score'))))
    except Exception:
        fit = 1
    fit = max(1, min(10, fit))

    qm = []
    for item in obj.get('qualification_match') or []:
        if isinstance(item, dict):
            status = str(item.get('status') or '').strip()
            if status not in ('满足', '不满足', '需确认'):
                status = '需确认'
            req = _clean_str(item.get('requirement'), cap=150)
            if req:
                qm.append({'requirement': req, 'status': status,
                           'note': _clean_str(item.get('note'), cap=100)})
        elif isinstance(item, str) and item.strip():
            qm.append({'requirement': _clean_str(item, cap=150),
                       'status': '需确认', 'note': ''})

    return {
        'fit_score': fit,
        'qualification_match': qm[:8],
        'scoring_analysis': _clean_list(obj.get('scoring_analysis'), cap_each=80, max_n=4),
        'bid_advice': _clean_list(obj.get('bid_advice'), cap_each=80, max_n=5),
        'gaps': _clean_list(obj.get('gaps'), cap_each=80, max_n=4),
        'summary': _clean_str(obj.get('summary'), cap=300),
        'analyzed_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'model': ai_config()['model'],
    }


def deep_analyze_text(title: str, content: str, basic: Dict[str, Any],
                      company: Optional[Dict[str, str]] = None
                      ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """命中关键词后的深入分析：资格/评分与我方公司资质逐条对比。"""
    if company is None:
        company = load_company_profile()
    indicators = {k: basic.get(k) for k in
                  ('project_name', 'purchaser', 'method', 'budget', 'deadline',
                   'qualification', 'announcement_type', 'summary')}
    body_text = (content or '').strip()
    if len(body_text) > 12000:
        body_text = body_text[:7000] + '\n……\n' + body_text[-4500:]

    obj, err = _call_model(DEEP_PROMPT_TMPL.format(
        title=(title or '')[:200],
        indicators=json.dumps(indicators, ensure_ascii=False),
        company=_company_text(company),
        content=body_text,
    ), max_tokens=2400)
    if obj is None:
        # 模型偶尔输出分析过程而非 JSON：缩短输入 + 强硬格式要求后重试一次
        retry_prompt = (
            '只输出一个 JSON 对象，不要任何分析过程、不要 Markdown、不要解释。字段：'
            'fit_score(1-10整数), qualification_match([{requirement,status,note}]), '
            'scoring_analysis[], bid_advice[], gaps[], summary。\n'
            f'标题：{(title or "")[:150]}\n'
            f'指标：{json.dumps(indicators, ensure_ascii=False)}\n'
            f'我方资质：{_company_text(company)[:1500]}\n'
            f'正文节选：{body_text[:4000]}'
        )
        obj, err = _call_model(retry_prompt, max_tokens=2400)
    if obj is None:
        return None, err
    return normalize_deep(obj), None


def save_deep(table: str, rid: int, deep: Optional[Dict[str, Any]],
              error: Optional[str] = None) -> None:
    """把深入分析结果合并到 ai_analysis.deep。"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT ai_analysis FROM `{table}` WHERE id=%s', (rid,))
        row = cur.fetchone() or {}
        val = row.get('ai_analysis')
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                val = None
        analysis = val if isinstance(val, dict) else {}
        if deep is not None:
            analysis['deep'] = deep
            analysis.pop('deep_error', None)
        elif error:
            analysis['deep_error'] = error[:500]
        cur.execute(f'UPDATE `{table}` SET ai_analysis=%s WHERE id=%s',
                    (json.dumps(analysis, ensure_ascii=False), rid))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def analyze_and_save(table: str, rid: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """分析单条：基础抽取 + 命中关键词时自动深入分析，并写库。"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT id, project_name, detail_content FROM `{table}` WHERE id=%s', (rid,))
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    if not row:
        return None, '记录不存在'

    result, err = analyze_text(row['project_name'], row.get('detail_content') or '')
    if result is None:
        save_analysis(table, rid, None, err)
        return None, err

    keywords = load_keywords()
    matched = match_keywords(f"{row['project_name']}\n{(row.get('detail_content') or '')[:4000]}", keywords)
    if matched:
        result['matched_keywords'] = matched
        deep, derr = deep_analyze_text(row['project_name'], row.get('detail_content') or '', result)
        if deep:
            result['deep'] = deep
        elif derr:
            result['deep_error'] = derr
    save_analysis(table, rid, result, None)
    return result, None


# ----------------------------------------------------------------- 数据库
def ensure_columns(table: str):
    """确保 4 个新列存在（幂等）。"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT column_name FROM information_schema.columns '
            'WHERE table_schema=%s AND table_name=%s',
            (os.environ.get('DB_NAME', 'bidding_db'), table))
        cols = {r['column_name'] for r in cur.fetchall()}
        ddl_map = {
            'detail_content': "ADD COLUMN detail_content MEDIUMTEXT NULL COMMENT '详情页正文（去标签后）'",
            'ai_analysis': "ADD COLUMN ai_analysis JSON NULL COMMENT 'AI 分析结果 JSON'",
            'ai_analysis_status': "ADD COLUMN ai_analysis_status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/ok/failed'",
            'ai_analyzed_at': "ADD COLUMN ai_analyzed_at DATETIME NULL COMMENT '最近一次 AI 分析时间'",
        }
        for col, ddl in ddl_map.items():
            if col not in cols:
                cur.execute(f'ALTER TABLE `{table}` {ddl}')
        conn.commit()
        cur.close()
    finally:
        conn.close()


def pick_rows(table: str, days: int, limit: int, status: str, force: bool,
              today_only: bool = False) -> List[Dict[str, Any]]:
    """挑出待分析的行：优先已有正文、未分析的。today_only 只取当日发布。"""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        conds = []
        params: List[Any] = []
        if not force:
            conds.append("(ai_analysis_status <> 'ok' OR ai_analysis_status IS NULL)")
        if status == 'has_content':
            conds.append('detail_content IS NOT NULL')
        elif status == 'no_content':
            conds.append('(detail_content IS NULL OR detail_content = %s)')
            params.append('')
        conds.append('detail_url IS NOT NULL')
        if today_only:
            conds.append('publish_date = CURDATE()')
        else:
            conds.append('publish_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)')
            params.append(days)
        where = ' AND '.join(conds)
        cur.execute(
            f'SELECT id, project_name, detail_url, detail_content, ai_analysis_status '
            f'FROM `{table}` WHERE {where} ORDER BY publish_date DESC, id DESC LIMIT %s',
            params + [limit])
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def save_analysis(table: str, rid: int, result: Optional[Dict[str, Any]], error: Optional[str]):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # 抓取阶段写入的 source（接口/页头结构化字段）不能被 AI 结果覆盖
        cur.execute(f'SELECT ai_analysis FROM `{table}` WHERE id=%s', (rid,))
        old = cur.fetchone() or {}
        old_val = old.get('ai_analysis')
        if isinstance(old_val, str):
            try:
                old_val = json.loads(old_val)
            except Exception:
                old_val = None
        source = old_val.get('source') if isinstance(old_val, dict) else None

        if result is not None:
            if source:
                result = {**result, 'source': source}
            cur.execute(
                f"UPDATE `{table}` SET ai_analysis=%s, ai_analysis_status='ok', ai_analyzed_at=%s WHERE id=%s",
                (json.dumps(result, ensure_ascii=False), datetime.datetime.now(), rid))
        else:
            cur.execute(
                f"UPDATE `{table}` SET ai_analysis_status='failed', ai_analyzed_at=%s WHERE id=%s",
                (datetime.datetime.now(), rid))
            # 失败原因记到 ai_analysis 里便于排查
            err_obj: Dict[str, Any] = {'error': (error or '')[:500]}
            if source:
                err_obj['source'] = source
            cur.execute(
                f"UPDATE `{table}` SET ai_analysis=%s WHERE id=%s",
                (json.dumps(err_obj, ensure_ascii=False), rid))
        conn.commit()
        cur.close()
    finally:
        conn.close()


# ----------------------------------------------------------------- 批量任务
_task_lock = threading.Lock()
_task_state: Dict[str, Any] = {
    'running': False,
    'total': 0,
    'done': 0,
    'ok': 0,
    'failed': 0,
    'deep_ok': 0,
    'current': '',
    'started_at': None,
    'finished_at': None,
    'message': '',
    'model_status': 'unknown',
}


def get_task_state() -> Dict[str, Any]:
    with _task_lock:
        return dict(_task_state)


def _set_state(**kw):
    with _task_lock:
        _task_state.update(kw)


def run_batch(tables: List[str], days: int = 3, limit_per_table: int = 20,
              status: str = 'has_content', force: bool = False,
              today_only: bool = False, keywords_only: bool = False) -> int:
    """同步批量分析（调用方自行放线程里跑）。返回分析成功条数。

    today_only=True 只分析当日发布；keywords_only=True 只分析命中后台关键词的。
    """
    # G3：开机探测。主机关机时整批跳过，一条 failed 都不写，
    # 避免一次停机把全部 pending 污染成 failed（failed=0 掩盖停机的老问题）。
    health = check_model_health()
    if not health['reachable']:
        _set_state(running=False, current='',
                   finished_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   message='模型主机关机，跳过本次批量；待分析记录保持 pending（%s）'
                           % health['message'],
                   model_status=health['status'])
        return 0

    valid = [t for t in tables if t in VALID_TABLES]
    for t in valid:
        ensure_columns(t)

    keywords = load_keywords()
    company = load_company_profile()
    total = 0
    rows_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for t in valid:
        pool = limit_per_table * 10 if keywords_only else limit_per_table
        rows = pick_rows(t, days, pool, status, force, today_only)
        if keywords_only:
            rows = [r for r in rows if match_keywords(
                f"{r['project_name']}\n{(r.get('detail_content') or '')[:4000]}", keywords)][:limit_per_table]
        rows_by_table[t] = rows
        total += len(rows)

    _set_state(running=True, total=total, done=0, ok=0, failed=0, deep_ok=0, current='',
               started_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
               finished_at=None, message='开始分析', model_status='ok')

    ok_cnt = 0
    fail_cnt = 0
    deep_cnt = 0
    aborted = False
    for t, rows in rows_by_table.items():
        for r in rows:
            _set_state(current=f"{t}#{r['id']} {r['project_name'][:40]}")
            content = r.get('detail_content') or ''
            result, err = analyze_text(r['project_name'], content)
            # G3：运行中途主机不可达 -> 立即中止，剩余记录保持 pending
            if result is None and classify_error(err) == 'unavailable':
                _set_state(message='模型服务不可达，中止批量；未处理记录保持 pending',
                           model_status='unavailable')
                aborted = True
                break
            # 命中后台关键词 -> 追加深入分析（资格/评分 vs 我方资质）
            if result is not None:
                matched = match_keywords(f"{r['project_name']}\n{content[:4000]}", keywords)
                if matched:
                    result['matched_keywords'] = matched
                    _set_state(current=f"{t}#{r['id']} 深入分析 {r['project_name'][:32]}")
                    deep, derr = deep_analyze_text(r['project_name'], content, result, company)
                    if deep:
                        result['deep'] = deep
                        deep_cnt += 1
                    elif derr:
                        result['deep_error'] = derr
            try:
                save_analysis(t, r['id'], result, err)
            except Exception as e:
                err = f'save: {e}'
            if result is not None:
                ok_cnt += 1
            else:
                fail_cnt += 1
            _set_state(done=ok_cnt + fail_cnt, ok=ok_cnt, failed=fail_cnt, deep_ok=deep_cnt)
            # 本地 27B 模型连续跑，留一点喘息
            time.sleep(0.3)
        if aborted:
            break

    if aborted:
        _set_state(running=False, current='',
                   finished_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   message='已中止：模型主机关机，成功 %d 条，其余保持 pending' % ok_cnt)
        return ok_cnt

    _set_state(running=False, current='',
               finished_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
               message=f'完成：成功 {ok_cnt}，失败 {fail_cnt}，深入分析 {deep_cnt}')
    return ok_cnt


def start_batch_async(tables: List[str], days: int, limit_per_table: int,
                      status: str, force: bool,
                      today_only: bool = False, keywords_only: bool = False) -> bool:
    """起后台线程跑批量任务；已有任务在跑则返回 False。"""
    with _task_lock:
        if _task_state['running']:
            return False
        _task_state.update(running=True, total=0, done=0, ok=0, failed=0, deep_ok=0,
                           current='', message='任务启动中',
                           started_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                           finished_at=None)

    def _worker():
        try:
            run_batch(tables, days, limit_per_table, status, force, today_only, keywords_only)
        except Exception as e:
            _set_state(running=False, message=f'任务异常: {e}',
                       finished_at=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    threading.Thread(target=_worker, name='ai-analysis-batch', daemon=True).start()
    return True
