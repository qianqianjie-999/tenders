#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_detail_content.py
=======================
抓取 3 省招标信息表中尚未入正文的行的详情页，把纯文本正文回写 detail_content 列。

设计原则：
  1. 只做抓取 + 回写，不涉及任何 AI/LLM。
  2. 温和限速：默认 3 workers × 100ms jitter，且每个 worker 请求间固定 1-2s 间隔。
  3. 幂等：detail_content IS NULL 才拉；--force 可强制重抓。
  4. 支持 --dry-run 只打印不写库。
  5. 单条失败不影响其他；最后输出成功/失败清单。

用法：
    python tools/fetch_detail_content.py --days 7 --limit 50
    python tools/fetch_detail_content.py --tables bidding_info --days 3 --limit 10 --dry-run
    python tools/fetch_detail_content.py --force --limit 20
"""
import argparse
import base64
import io
import os
import re
import sys
import time
import json
import random
import logging
import datetime
import threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urljoin, quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymysql
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry

# 项目根
ROOT = Path(__file__).resolve().parent.parent

# 加载 .env（与 flask_web 的 config.py 一致）
def _load_env():
    env_path = ROOT / '.env'
    if not env_path.exists():
        return
    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

_load_env()

import requests  # noqa: E402  (依赖延迟导入，避免 --help 也拉依赖)
UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
]


# ---------- 日志 ----------
logger: logging.Logger = logging.getLogger('fetch_detail_content')


def setup_logger(name='fetch_detail_content'):
    log_dir = ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)
    log_file = str(log_dir / f'fetch_detail_content_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh = logging.FileHandler(log_file, encoding='utf-8')
    sh = logging.StreamHandler(sys.stdout)
    for h in (fh, sh):
        h.setFormatter(fmt)
        logger.addHandler(h)
    logger.info(f'日志文件: {log_file}')
    return logger


# ---------- DB ----------
def get_conn():
    return pymysql.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        user=os.getenv('DB_USER', 'bidding_user'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'bidding_db'),
        port=int(os.getenv('DB_PORT', 3306)),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def ensure_columns(conn, table: str):
    """确保 4 个新列存在，若缺失则补建（幂等）。"""
    cur = conn.cursor()
    cur.execute(f'SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',
                (os.getenv('DB_NAME', 'bidding_db'), table))
    cols = {r['column_name'] for r in cur.fetchall()}
    required = {
        'detail_content': "ADD COLUMN detail_content MEDIUMTEXT NULL COMMENT '详情页正文（去标签后）'",
        'ai_analysis': "ADD COLUMN ai_analysis JSON NULL COMMENT 'AI 分析结果 JSON'",
        'ai_analysis_status': "ADD COLUMN ai_analysis_status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/ok/failed'",
        'ai_analyzed_at': "ADD COLUMN ai_analyzed_at DATETIME NULL COMMENT '最近一次 AI 分析时间'",
    }
    for col, ddl in required.items():
        if col not in cols:
            sql = f'ALTER TABLE `{table}` {ddl}'
            logger.info(f'[{table}] 缺少列 {col}，自动补建')
            cur.execute(sql)
    conn.commit()
    cur.close()


def _ensure_conn(conn):
    """长任务里连接可能被服务端断开，复用前先探活重连。"""
    try:
        conn.ping(reconnect=True)
    except Exception:
        pass
    return conn


def load_title_keywords(conn) -> list:
    """读取后台维护的高亮关键词，用于标题预筛。"""
    try:
        _ensure_conn(conn)
        cur = conn.cursor()
        cur.execute("SELECT keyword FROM highlight_keywords WHERE keyword IS NOT NULL AND keyword <> ''")
        kws = [str(r['keyword']).strip() for r in cur.fetchall() if str(r['keyword']).strip()]
        cur.close()
        return kws
    except Exception as e:
        logger.warning(f'读取关键词失败，将不按标题过滤: {e}')
        return []


def pick_pending_rows(conn, table: str, days: int, limit: int, force: bool = False,
                      today_only: bool = False, keywords: list = None):
    _ensure_conn(conn)
    cur = conn.cursor()
    if force:
        cond = "(detail_url IS NOT NULL AND detail_url <> '')"
    else:
        cond = "(detail_url IS NOT NULL AND detail_url <> '' AND detail_content IS NULL)"
    params = []
    if today_only:
        date_cond = 'publish_date = CURDATE()'
    else:
        date_cond = 'publish_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)'
        params.append(days)
    # 只抓标题命中关键词的，减少 PDF/附件解析量
    kw_cond = ''
    if keywords:
        kw_cond = ' AND (' + ' OR '.join(['project_name LIKE %s'] * len(keywords)) + ')'
        params += [f'%{k}%' for k in keywords]
    sql = f"""
      SELECT id, project_name, publish_date, detail_url, project_source, project_category, crawl_time
      FROM `{table}`
      WHERE {cond}
        AND {date_cond}{kw_cond}
      ORDER BY crawl_time DESC
      LIMIT %s
    """
    cur.execute(sql, params + [limit])
    rows = cur.fetchall()
    cur.close()
    return rows


def write_back(conn, table: str, rid: int, content: str, meta: dict = None,
               old_publish_date=None):
    """回写正文 + 页头结构化字段（存 ai_analysis.source）。"""
    if content is None:
        return
    text = content or ''
    if len(text.encode('utf-8')) > 200 * 1024:
        text = text[:60000]  # 中文按字符兜底
    meta = {k: v for k, v in (meta or {}).items() if v}
    payload = json.dumps({'source': meta}, ensure_ascii=False) if meta else None
    _ensure_conn(conn)
    cur = conn.cursor()
    cur.execute(
        f"UPDATE `{table}` SET detail_content=%s, ai_analysis=%s, "
        "ai_analysis_status='pending', ai_analyzed_at=NULL "
        "WHERE id=%s",
        (text, payload, rid),
    )
    # 发布日期以页头 PubDate 为准：库里为空时补上
    if meta.get('pub_date') and not old_publish_date:
        cur.execute(
            f"UPDATE `{table}` SET publish_date=%s WHERE id=%s AND publish_date IS NULL",
            (meta['pub_date'], rid),
        )
    conn.commit()
    cur.close()


# ---------- 抓取与解析 ----------
_strip_re = re.compile(r'<(script|style|noscript|iframe|svg|video|audio|form)\b[^>]*>.*?</\1>',
                       re.IGNORECASE | re.DOTALL)
_noise_re = re.compile(r'[\u200b\u200e\u200f\ufeff]')
_ws_re = re.compile(r'[ \t\r\f\v]+')
_blank_lines_re = re.compile(r'\n{3,}')


_BLOCK_TAGS = ['p', 'div', 'br', 'li', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
               'section', 'article', 'table', 'ul', 'ol', 'pre', 'blockquote', 'header',
               'footer', 'nav', 'dd', 'dt', 'hr']


def html_to_text(html: str) -> str:
    """HTML → 纯文本：去 script/style/noscript/form，块级标签转换行，压缩空白。"""
    if not html:
        return ''
    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        soup = BeautifulSoup(html, 'html.parser')
    for bad in soup.find_all(['script', 'style', 'noscript', 'iframe', 'svg', 'video',
                              'audio', 'form', 'canvas', 'template']):
        bad.decompose()
    # 块级元素前后补换行，避免行内标签（<b>/<span>）把句子切碎
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before('\n')
        tag.insert_after('\n')
    text = soup.get_text('')
    text = _noise_re.sub('', text)
    text = _ws_re.sub(' ', text)
    text = re.sub(r'[ ]*\n[ ]*', '\n', text)     # 去行首行尾空格
    text = _blank_lines_re.sub('\n\n', text)     # 折叠空行
    return text.strip()[:200000]


def fetch_html(session: requests.Session, url: str, timeout: int = 20) -> str:
    resp = session.get(url, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    # 修正编码
    if resp.encoding is None or resp.encoding.lower() in ('iso-8859-1',):
        ctype = resp.headers.get('Content-Type', '')
        m = re.search(r'charset=([\w-]+)', ctype, re.IGNORECASE)
        if m:
            resp.encoding = m.group(1)
        else:
            resp.encoding = 'utf-8'
    return resp.text


# ---------- 三地区 adapter ----------
# 山东(省采购网)前端为 SPA，正文走接口；济南公共资源交易中心是普通 HTML 页。
SD_API = 'https://www.ccgp-shandong.gov.cn:8087/api/website/site/getDetail'

# 页头 meta -> 统一字段名（接口/页头能直接拿到的结构化信息，不再交给 AI 猜）
_META_FIELDS = {
    'PubDate': 'pub_date',
    'ColumnType': 'column_type',
    'ColumnName': 'column_name',
    'ContentSource': 'content_source',
    'SiteName': 'site_name',
    'ArticleTitle': 'article_title',
    'ArticleTite': 'article_title',   # 浙江站点拼写如此
}


def _norm_date(s: str) -> str:
    m = re.search(r'(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})', s or '')
    if not m:
        return ''
    return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'


def _page_meta(soup: BeautifulSoup) -> dict:
    """抽取页头 meta 里的发布日期/栏目/来源/标题等结构化字段。"""
    meta = {}
    for tag in soup.find_all('meta'):
        name = (tag.get('name') or tag.get('property') or '').strip()
        key = _META_FIELDS.get(name)
        if not key or key in meta:
            continue
        val = (tag.get('content') or '').strip()
        if val:
            meta[key] = val
    if meta.get('pub_date'):
        meta['pub_date'] = _norm_date(meta['pub_date']) or meta['pub_date']
    if meta.get('article_title'):
        # 浙江标题尾部带 [A33000...] 项目编号，去掉
        meta['article_title'] = re.sub(r'\[[^\]]*\]\s*$', '', meta['article_title']).strip()
    return meta


def _decode_html(raw: bytes) -> str:
    """山东接口返回的 HTML 是 GBK，优先 gb18030，失败再试 utf-8。"""
    for enc in ('gb18030', 'utf-8'):
        try:
            t = raw.decode(enc)
            if any(k in t for k in ('预算', '采购', '招标', '公告')):
                return t
        except Exception:
            continue
    return raw.decode('gb18030', 'ignore')


def fetch_shandong(session: requests.Session, url: str):
    """山东：ccgp-shandong 走 getDetail 接口，其余站点走通用页面跟进。

    返回 (正文, 页头结构化字段)。
    """
    host = urlparse(url).netloc or ''
    if 'ccgp-shandong.gov.cn' not in host:
        return _fetch_page_text(session, url)

    q = parse_qs(urlparse(url).query)
    nid = (q.get('id') or [''])[0]
    col = (q.get('colCode') or ['0301'])[0]
    if not nid:
        raise ValueError('ccgp-shandong url 缺少 id 参数')

    session.headers['Referer'] = url
    resp = session.get(SD_API, params={'id': nid, 'colCode': col}, timeout=25)
    resp.raise_for_status()
    payload = resp.json()
    data = (payload.get('data') or {}).get('data') or {}
    body = data.get('body')
    if not body:
        raise ValueError(f"接口无正文: {((payload.get('data') or {}).get('message')) or 'empty body'}")
    html = _decode_html(base64.b64decode(body))
    text = html_to_text(html)
    title = (data.get('title') or '').strip()
    if title and title not in text[:120]:
        text = title + '\n' + text
    # userName 是代理机构（不是招标人），date 是发布时间
    meta = {
        'title': title,
        'agency': (data.get('userName') or '').strip(),
        'pub_date': _norm_date(data.get('date') or ''),
        'column_type': col,
    }
    return text, meta


def fetch_jiangsu(session: requests.Session, url: str):
    """江苏：正文直接在详情页 HTML 里（附件若有也会一并解析）。"""
    return _fetch_page_text(session, url)


def _pdf_to_text(content: bytes) -> str:
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError('缺少 pdfplumber，请先安装: pip install pdfplumber')
    chunks = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or '')
    text = '\n'.join(chunks)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


_LO_LOCK = threading.Lock()


def _doc_to_text(content: bytes, suffix: str) -> str:
    """用 libreoffice 把 doc/docx/xls 转成 txt（加锁避免并发 profile 冲突）。"""
    import subprocess
    import tempfile
    import uuid
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, 'src' + suffix)
        with open(src, 'wb') as f:
            f.write(content)
        # profile 必须跟随 TemporaryDirectory：原先写死 /tmp/lo_prof_* 会落在
        # 本机 10MB tmpfs，大附件转换直接失败。部署侧把 TMPDIR 指向大分区即可，
        # tempfile 会自动使用该目录，无需新增配置项。
        prof = 'file://' + os.path.join(td, 'lo_prof_%s' % uuid.uuid4().hex[:8])
        with _LO_LOCK:
            subprocess.run(
                ['soffice', '--headless', f'-env:UserInstallation={prof}',
                 '--convert-to', 'txt:Text (encoded):UTF8', '--outdir', td, src],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        out = os.path.join(td, 'src.txt')
        if os.path.exists(out):
            with open(out, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read().strip()
    return ''


def _fetch_file_text(session: requests.Session, link: str) -> str:
    """下载附件并按文件头判断格式：PDF / docx / 老版 doc。"""
    link = link.replace('\\', '/')  # 部分站点 href 里用反斜杠
    resp = session.get(quote(link, safe=':/?&=%#'), timeout=60)
    resp.raise_for_status()
    body = resp.content
    if body[:4] == b'%PDF':
        return _pdf_to_text(body)
    if body[:2] == b'PK':  # docx / xlsx（zip 容器）
        return _doc_to_text(body, '.docx' if link.lower().endswith('.docx') else '.xlsx')
    if body[:4] == b'\xd0\xcf\x11\xe0':  # 老版 doc / xls（OLE2）
        return _doc_to_text(body, '.doc' if re.search(r'\.doc$', link, re.I) else '.xls')
    return ''


def _collect_files(soup: BeautifulSoup, base_url: str) -> list:
    out, seen = [], set()
    for a in soup.find_all('a', href=True):
        href = (a['href'] or '').strip()
        if not href or href.lower().startswith('javascript'):
            continue
        link = urljoin(base_url, href).replace('\\', '/')
        if re.search(r'\.(pdf|docx?|xlsx?)$', link, re.I) and link not in seen:
            seen.add(link)
            out.append(link)
    return out


def _fetch_page_text(session: requests.Session, url: str, depth: int = 0):
    """通用抓取：短页跟「点击查看详情」，并解析页面上的 PDF/DOC 附件。

    返回 (正文, 页头结构化字段)。
    """
    session.headers['Referer'] = url  # 部分站点校验来源
    html = fetch_html(session, url, timeout=25)
    soup = BeautifulSoup(html, 'lxml')
    text = html_to_text(html)
    meta = _page_meta(soup)

    # 外壳页（如济南 soaInfo.do）跟进真实详情
    if depth < 2 and len(text) < 300:
        for a in soup.find_all('a', href=True):
            href = (a['href'] or '').strip()
            if not href or href.lower().startswith('javascript'):
                continue
            if any(k in a.get_text(' ', strip=True) for k in ('点击查看详情', '查看详情', '查看原文')):
                return _fetch_page_text(session, urljoin(url, href), depth + 1)

    parts = []
    for link in _collect_files(soup, url):
        try:
            t = _fetch_file_text(session, link)
            if t:
                parts.append(t)
        except Exception as e:
            logger.warning(f'附件解析失败 {link}: {type(e).__name__}: {e}')

    if parts:
        # 页面正文太短（多为导航壳）时，以附件正文为准
        text = '\n\n'.join(parts) if len(text) < 600 else text + '\n\n' + '\n\n'.join(parts)
    return text, meta


def fetch_zhejiang(session: requests.Session, url: str):
    """浙江：正文是 PDF 附件（页面几乎无正文），走通用抓取。"""
    return _fetch_page_text(session, url)


def fetch_text(row: dict, session: requests.Session):
    """按表分发到对应 adapter，统一返回 (纯文本, 页头字段)。"""
    table, url = row['table'], row['detail_url']
    if table == 'bidding_info':
        return fetch_shandong(session, url)
    if table == 'zhejiang_bidding_info':
        return fetch_zhejiang(session, url)
    return fetch_jiangsu(session, url)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        'User-Agent': random.choice(UA_POOL),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=8, pool_maxsize=8,
        max_retries=Retry(total=2, backoff_factor=0.6,
                          status_forcelist=[502, 503, 504], allowed_methods=['GET'],
                          raise_on_status=False),
    )
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s


_thread_local = threading.local()


def get_session() -> requests.Session:
    """每个线程独享一个 Session（requests.Session 非线程安全）。"""
    s = getattr(_thread_local, 'session', None)
    if s is None:
        s = make_session()
        _thread_local.session = s
    return s


def fetch_one(row: dict, dry_run: bool) -> dict:
    """抓取单条详情，返回结果字典。不抛异常，把错误塞 error 字段。"""
    out = {
        'id': row['id'],
        'table': row['table'],
        'name': row['project_name'][:60],
        'url': row['detail_url'],
        'ok': False,
        'len': 0,
        'meta': {},
        'error': None,
    }
    try:
        text, meta = fetch_text(row, get_session())
        text = text or ''
    except Exception as e:
        out['error'] = f'fetch: {type(e).__name__}: {e}'
        return out
    out['len'] = len(text)
    out['ok'] = len(text) >= 20  # 过短的算抓取失败（可能是反爬/404 页）
    out['meta'] = {k: v for k, v in (meta or {}).items() if v}
    if dry_run:
        return out
    try:
        write_back(row['conn'], row['table'], row['id'], text,
                   out['meta'], row.get('publish_date'))
    except Exception as e:
        out['error'] = f'write_back: {type(e).__name__}: {e}'
        out['ok'] = False
    return out


def process_table(conn, table: str, days: int, limit: int, workers: int,
                  force: bool, dry_run: bool, today_only: bool = False,
                  keywords: list = None) -> dict:
    rows = pick_pending_rows(conn, table, days, limit, force, today_only, keywords)
    if not rows:
        logger.info(f'[{table}] 无待抓取行')
        return {'table': table, 'total': 0, 'ok': 0, 'fail': 0, 'items': []}

    logger.info(f'[{table}] 待抓取 {len(rows)} 行，workers={workers}，dry_run={dry_run}')

    # 每个 worker 独享数据库连接（Session 由线程本地管理）
    conns = [conn] + [get_conn() for _ in range(workers - 1)]

    jobs = []
    for i, r in enumerate(rows):
        r2 = dict(r)
        r2['table'] = table
        r2['conn'] = conns[i % len(conns)]
        jobs.append((i, r2))

    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_one, job[1], dry_run): job[0] for job in jobs}
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            logger.info(f"[{table}] id={res['id']} ok={res['ok']} len={res['len']}"
                        + (f" err={res['error']}" if res['error'] else '')
                        + f" name={res['name']}")
            # 保守限速
            time.sleep(random.uniform(0.3, 0.8))

    ok = sum(1 for r in results if r['ok'])
    fail = len(results) - ok
    for c in conns[1:]:
        try:
            c.close()
        except Exception:
            pass
    return {'table': table, 'total': len(results), 'ok': ok, 'fail': fail, 'items': results}


def main():
    ap = argparse.ArgumentParser(description='抓取 3 省招标表的详情页正文回写')
    ap.add_argument('--days', type=int, default=7, help='近 N 天（默认 7）')
    ap.add_argument('--today', action='store_true', help='只抓当日发布的记录（优先于 --days）')
    ap.add_argument('--title-keywords', action='store_true',
                    help='只抓标题命中后台关键词的记录（减少 PDF 解析量）')
    ap.add_argument('--limit', type=int, default=50, help='每表最多处理行数（默认 50）')
    ap.add_argument('--tables', default='bidding_info,jiangsu_bidding_info,zhejiang_bidding_info',
                    help='要处理的表，逗号分隔')
    ap.add_argument('--workers', type=int, default=3, help='并发 worker 数（默认 3）')
    ap.add_argument('--force', action='store_true', help='强制重抓（无视 detail_content 已有）')
    ap.add_argument('--dry-run', action='store_true', help='只打印不写库')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

    tables = [t.strip() for t in args.tables.split(',') if t.strip()]
    conn = get_conn()
    try:
        for t in tables:
            ensure_columns(conn, t)
        summary = []
        keywords = load_title_keywords(conn) if args.title_keywords else None
        if keywords:
            logger.info(f'标题关键词过滤已启用，共 {len(keywords)} 个')
        for t in tables:
            summary.append(process_table(conn, t, args.days, args.limit,
                                         args.workers, args.force, args.dry_run, args.today,
                                         keywords))
        conn.commit()
    finally:
        conn.close()

    print('\n=== 汇总 ===')
    for s in summary:
        print(f"  {s['table']:<28} total={s['total']:>4}  ok={s['ok']:>4}  fail={s['fail']:>4}")
    total_ok = sum(s['ok'] for s in summary)
    total_fail = sum(s['fail'] for s in summary)
    print(f'  合计 ok={total_ok}  fail={total_fail}')
    # 落一份 JSON 便于后续排查
    log_dir = ROOT / 'logs'
    log_dir.mkdir(exist_ok=True)
    out_file = log_dir / f'fetch_detail_content_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    out_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info(f'JSON 结果已写入 {out_file}')


if __name__ == '__main__':
    setup_logger()
    main()
