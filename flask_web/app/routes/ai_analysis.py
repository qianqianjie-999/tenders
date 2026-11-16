# -*- coding: utf-8 -*-
"""AI 分析页面与接口"""
import json
import os
import re
import sys
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app.extensions import get_db_connection
from app.decorators import require_auth_write
from app.services import ai_analyzer_service as ai
from app.services import analysis_bridge_service as bridge

ai_analysis_bp = Blueprint('ai_analysis', __name__, url_prefix='/ai-analysis')

TABLE_LIST = list(ai.TABLE_PROJECTS.keys())

# G2 人工上传：只存解析文本，不落盘原件（绕开 /static 被 Apache Alias 直出
# 绕过鉴权、以及生产 apache 用户对附件目录写权限两个坑）
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _document_parsers():
    """惰性加载 tools/fetch_detail_content.py 的解析函数（不重复实现）。"""
    root = Path(__file__).resolve().parents[3]
    tools = str(root / 'tools')
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import fetch_detail_content as fdc
    return fdc


def _safe_filename(name):
    """文件名仅用于展示；去掉路径与标签字符，不用于落盘。"""
    base = os.path.basename(name or '').replace('\\', '/').split('/')[-1]
    return re.sub(r'[<>\r\n\t]', '', base)[:120]


def _bytes_to_text(body, filename):
    """按文件头判定格式，不信任扩展名。返回 (text, kind)。"""
    fdc = _document_parsers()
    if body[:4] == b'%PDF':
        return fdc._pdf_to_text(body), 'pdf'
    lower = filename.lower()
    if body[:2] == b'PK':
        suffix = '.docx' if lower.endswith('.docx') else '.xlsx'
        return fdc._doc_to_text(body, suffix), 'office'
    if body[:4] == b'\xd0\xcf\x11\xe0':
        suffix = '.doc' if re.search(r'\.doc$', lower) else '.xls'
        return fdc._doc_to_text(body, suffix), 'office'
    # 纯文本兜底：便于直接上传已复制的公告正文
    try:
        text = body.decode('utf-8')
    except UnicodeDecodeError:
        text = body.decode('gbk', errors='ignore')
    if text.lstrip().startswith('<') or '\x00' in text[:200]:
        return '', 'unsupported'
    return text.strip(), 'text'


def _parse_json_field(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return None


def _table_or_none(name):
    return name if name in ai.VALID_TABLES else None


@ai_analysis_bp.route('/')
@login_required
def index():
    return render_template('ai_analysis.html')


@ai_analysis_bp.route('/api/stats')
@login_required
def api_stats():
    """三张表的分析进度统计。"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        result = {}
        for t in TABLE_LIST:
            cur.execute(
                f"SELECT "
                f"COUNT(*) AS total, "
                f"SUM(detail_content IS NOT NULL AND detail_content <> '') AS has_content, "
                f"SUM(ai_analysis_status = 'ok') AS analyzed, "
                f"SUM(ai_analysis_status = 'failed') AS failed, "
                f"SUM(ai_analysis_status = 'pending' OR ai_analysis_status IS NULL) AS pending "
                f"FROM `{t}` WHERE publish_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)")
            row = cur.fetchone() or {}
            result[t] = {
                'label': ai.TABLE_PROJECTS[t],
                'total': int(row.get('total') or 0),
                'has_content': int(row.get('has_content') or 0),
                'analyzed': int(row.get('analyzed') or 0),
                'failed': int(row.get('failed') or 0),
                'pending': int(row.get('pending') or 0),
            }
        cur.close()
        return jsonify({'success': True, 'data': result,
                        'task': ai.get_task_state(),
                        'model': ai.ai_config()['model'],
                        'model_status': ai.check_model_health()})
    except Exception as e:
        return jsonify({'success': False, 'message': f'统计失败: {e}'}), 500


@ai_analysis_bp.route('/api/list')
@login_required
def api_list():
    """分页查询分析结果。"""
    try:
        table = request.args.get('table', 'all')
        status = request.args.get('status', 'all')
        ann_type = request.args.get('announcement_type', '')
        min_rel = int(request.args.get('min_relevance', 0) or 0)
        category = request.args.get('category', '')
        keyword = request.args.get('keyword', '').strip()
        start_date = (request.args.get('start_date') or '').strip()
        end_date = (request.args.get('end_date') or '').strip()
        days = int(request.args.get('days', 0) or 0)
        page = max(1, int(request.args.get('page', 1) or 1))
        page_size = min(100, max(1, int(request.args.get('page_size', 20) or 20)))
        offset = (page - 1) * page_size

        tables = TABLE_LIST if table in ('all', '', None) else [_table_or_none(table)]
        tables = [t for t in tables if t]
        if not tables:
            return jsonify({'success': False, 'message': '未知的表'}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        rows_all = []
        for t in tables:
            conds = []
            params = []
            if start_date and end_date:
                conds.append('publish_date BETWEEN %s AND %s')
                params += [start_date, end_date]
            elif start_date:
                conds.append('publish_date >= %s')
                params.append(start_date)
            elif end_date:
                conds.append('publish_date <= %s')
                params.append(end_date)
            else:
                conds.append('publish_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)')
                params.append(days or 7)
            if status != 'all':
                if status == 'pending':
                    conds.append("(ai_analysis_status = 'pending' OR ai_analysis_status IS NULL)")
                else:
                    conds.append('ai_analysis_status = %s')
                    params.append(status)
            if ann_type:
                conds.append("JSON_UNQUOTE(JSON_EXTRACT(ai_analysis, '$.announcement_type')) = %s")
                params.append(ann_type)
            if min_rel > 0:
                conds.append("CAST(JSON_UNQUOTE(JSON_EXTRACT(ai_analysis, '$.relevance')) AS UNSIGNED) >= %s")
                params.append(min_rel)
            if category in ai.FOCUS_CATEGORIES:
                conds.append("JSON_UNQUOTE(JSON_EXTRACT(ai_analysis, '$.categories.%s')) IN ('true', '1')" % category)
            if keyword:
                conds.append('project_name LIKE %s')
                params.append(f'%{keyword}%')

            where = ' AND '.join(conds)
            cur.execute(
                f"SELECT id, project_name, publish_date, project_source, project_category, "
                f"detail_url, ai_analysis, ai_analysis_status, ai_analyzed_at, "
                f"(detail_content IS NOT NULL AND detail_content <> '') AS has_content "
                f"FROM `{t}` WHERE {where} "
                f"ORDER BY CAST(JSON_UNQUOTE(JSON_EXTRACT(ai_analysis, '$.relevance')) AS UNSIGNED) DESC, "
                f"publish_date DESC, id DESC", params)
            for r in cur.fetchall():
                r['_table'] = t
                rows_all.append(r)
        cur.close()

        # 内存合并分页（3 表合计通常不大）
        total = len(rows_all)
        rows_all = rows_all[offset:offset + page_size]

        data = []
        for r in rows_all:
            a = _parse_json_field(r['ai_analysis']) or {}
            data.append({
                'id': r['id'],
                'table': r['_table'],
                'region': ai.TABLE_PROJECTS.get(r['_table'], ''),
                'project_name': r['project_name'],
                'publish_date': r['publish_date'].strftime('%Y-%m-%d') if r['publish_date'] else '',
                'project_source': r['project_source'] or '',
                'project_category': r['project_category'] or '',
                'detail_url': r['detail_url'] or '',
                'status': r['ai_analysis_status'] or 'pending',
                'analyzed_at': r['ai_analyzed_at'].strftime('%Y-%m-%d %H:%M') if r['ai_analyzed_at'] else '',
                'has_content': bool(r['has_content']),
                'announcement_type': a.get('announcement_type', ''),
                'project_type': a.get('project_type', ''),
                'summary': a.get('summary', ''),
                'keywords': a.get('keywords', []),
                'categories': a.get('categories', {}),
                'relevance': a.get('relevance'),
                'purchaser': a.get('purchaser', '未获取'),
                'agency': a.get('agency', '未获取'),
                'method': a.get('method', '未获取'),
                'budget': a.get('budget', '未获取'),
                'deadline': a.get('deadline', '未获取'),
                'qualification': a.get('qualification', '未获取'),
                'matched_keywords': a.get('matched_keywords', []),
                'fit_score': (a.get('deep') or {}).get('fit_score'),
                'has_deep': bool(a.get('deep')),
                'risk': a.get('risk', []),
                'compliance': a.get('compliance', []),
                'scoring': a.get('scoring', []),
                'error': a.get('error'),
            })

        return jsonify({
            'success': True,
            'data': data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size,
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {e}'}), 500


@ai_analysis_bp.route('/api/detail/<table>/<int:rid>')
@login_required
def api_detail(table, rid):
    """单条详情（含正文全文）。"""
    t = _table_or_none(table)
    if not t:
        return jsonify({'success': False, 'message': '未知的表'}), 400
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, project_name, publish_date, project_source, project_category, detail_url, "
            f"detail_content, ai_analysis, ai_analysis_status, ai_analyzed_at "
            f"FROM `{t}` WHERE id=%s", (rid,))
        r = cur.fetchone()
        cur.close()
        if not r:
            return jsonify({'success': False, 'message': '记录不存在'}), 404
        a = _parse_json_field(r['ai_analysis']) or {}
        return jsonify({
            'success': True,
            'data': {
                'id': r['id'],
                'table': t,
                'region': ai.TABLE_PROJECTS.get(t, ''),
                'project_name': r['project_name'],
                'publish_date': r['publish_date'].strftime('%Y-%m-%d') if r['publish_date'] else '',
                'project_source': r['project_source'] or '',
                'project_category': r['project_category'] or '',
                'detail_url': r['detail_url'] or '',
                'detail_content': r['detail_content'] or '',
                'status': r['ai_analysis_status'] or 'pending',
                'analyzed_at': r['ai_analyzed_at'].strftime('%Y-%m-%d %H:%M:%S') if r['ai_analyzed_at'] else '',
                'analysis': a,
                'source': a.get('source') or {},
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'查询失败: {e}'}), 500


@ai_analysis_bp.route('/api/analyze', methods=['POST'])
@login_required
def api_analyze():
    """启动后台批量分析。"""
    payload = request.get_json(silent=True) or {}
    table = payload.get('table', 'all')
    limit = max(1, min(200, int(payload.get('limit', 20) or 20)))
    status = payload.get('content_filter', 'has_content')  # has_content / no_content / all（不限）
    force = bool(payload.get('force', False))

    tables = TABLE_LIST if table in ('all', '', None) else [_table_or_none(table)]
    tables = [t for t in tables if t]
    if not tables:
        return jsonify({'success': False, 'message': '未知的表'}), 400

    if status == 'all':
        status = ''  # 空串表示不限制正文有无

    # G3：关机时直接拒绝，不启动线程、不写 failed，避免 180s 空等
    health = ai.check_model_health(force=True)
    if not health['reachable']:
        return jsonify({
            'success': False,
            'message': '模型主机关机，本次批量未启动；待分析记录保持 pending（%s）'
                       % health['message'],
            'model_status': health,
        }), 503

    # 只分析「当日发布 + 命中关键词」的记录；默认先自动补正文再分析，
    # 前端不必再单独点「抓取详情正文」（2026-11-16 生产上因此 0 条空跑）
    ok = ai.start_batch_async(tables, 1, limit, status, force,
                              today_only=True, keywords_only=True,
                              auto_fetch=bool(payload.get('auto_fetch', True)))
    if not ok:
        return jsonify({'success': False, 'message': '已有分析任务在运行，请稍后再试',
                        'task': ai.get_task_state()}), 409
    return jsonify({'success': True, 'message': '分析任务已启动', 'task': ai.get_task_state()})


@ai_analysis_bp.route('/api/task')
@login_required
def api_task():
    return jsonify({'success': True, 'task': ai.get_task_state(),
                    'model_status': ai.check_model_health()})


@ai_analysis_bp.route('/api/model-health')
@login_required
def api_model_health():
    """G3：显式健康检查；force=1 跳过缓存立即探测。"""
    force = request.args.get('force') in ('1', 'true', 'yes')
    return jsonify({'success': True, 'health': ai.check_model_health(force=force)})


@ai_analysis_bp.route('/api/analyze-one/<table>/<int:rid>', methods=['POST'])
@login_required
def api_analyze_one(table, rid):
    """同步分析单条（页面「重新分析」按钮）。命中关键词会自动追加深入分析。"""
    t = _table_or_none(table)
    if not t:
        return jsonify({'success': False, 'message': '未知的表'}), 400
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT detail_content FROM `{t}` WHERE id=%s", (rid,))
        r = cur.fetchone()
        cur.close()
        conn.close()
        if not r:
            return jsonify({'success': False, 'message': '记录不存在'}), 404
        if not (r['detail_content'] or '').strip():
            return jsonify({'success': False,
                            'message': '该记录还没有正文，请先抓取详情页正文'}), 400
        # G3：同步单条接口不能为主机关机空等 AI_TIMEOUT(180s)
        health = ai.check_model_health(force=True)
        if not health['reachable']:
            return jsonify({
                'success': False,
                'message': '模型主机关机，单条分析未执行（%s）' % health['message'],
                'model_status': health,
            }), 503
        result, err = ai.analyze_and_save(t, rid)
        if result is None:
            return jsonify({'success': False, 'message': err or '分析失败'}), 500
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': f'分析失败: {e}'}), 500


@ai_analysis_bp.route('/api/deep-analyze/<table>/<int:rid>', methods=['POST'])
@login_required
def api_deep_analyze(table, rid):
    """对单条做深入分析：资格/评分 vs 我方公司资质。"""
    t = _table_or_none(table)
    if not t:
        return jsonify({'success': False, 'message': '未知的表'}), 400
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT project_name, detail_content, ai_analysis FROM `{t}` WHERE id=%s", (rid,))
        r = cur.fetchone()
        cur.close()
        conn.close()
        if not r:
            return jsonify({'success': False, 'message': '记录不存在'}), 404
        if not (r['detail_content'] or '').strip():
            return jsonify({'success': False, 'message': '该记录还没有正文，请先抓取'}), 400
        basic = _parse_json_field(r['ai_analysis']) or {}
        if not any(basic.get(k) for k in ('summary', 'purchaser', 'bidder')):
            return jsonify({'success': False, 'message': '请先做基础分析，再深入分析'}), 400
        deep, err = ai.deep_analyze_text(r['project_name'], r['detail_content'], basic)
        if deep is None:
            ai.save_deep(t, rid, None, err)
            return jsonify({'success': False, 'message': err or '深入分析失败'}), 500
        ai.save_deep(t, rid, deep)
        return jsonify({'success': True, 'data': deep})
    except Exception as e:
        return jsonify({'success': False, 'message': f'深入分析失败: {e}'}), 500


@ai_analysis_bp.route('/api/company-profile', methods=['GET', 'POST'])
@login_required
def api_company_profile():
    """我方公司资质档案（深入分析时用于逐条对比）。"""
    if request.method == 'GET':
        try:
            return jsonify({'success': True, 'data': ai.load_company_profile(),
                            'labels': ai.COMPANY_LABELS})
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取失败: {e}'}), 500

    payload = request.get_json(silent=True) or {}
    try:
        data = ai.save_company_profile(payload)
        return jsonify({'success': True, 'data': data, 'message': '已保存'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存失败: {e}'}), 500


@ai_analysis_bp.route('/api/fetch-detail', methods=['POST'])
@login_required
def api_fetch_detail():
    """后台抓取详情正文（调用 tools/fetch_detail_content.py）。"""
    payload = request.get_json(silent=True) or {}
    table = payload.get('table', 'all')
    limit = max(1, min(200, int(payload.get('limit', 20) or 20)))

    tables = TABLE_LIST if table in ('all', '', None) else [_table_or_none(table)]
    tables = [t for t in tables if t]
    if not tables:
        return jsonify({'success': False, 'message': '未知的表'}), 400

    state = ai.get_task_state()
    if state.get('running'):
        return jsonify({'success': False, 'message': '已有 AI 分析任务在运行，请等它结束'}), 409

    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    script = root / 'tools' / 'fetch_detail_content.py'
    if not script.exists():
        return jsonify({'success': False, 'message': '抓取脚本不存在'}), 500

    cmd = [sys.executable, str(script), '--today', '--title-keywords',
           '--limit', str(limit), '--tables', ','.join(tables)]
    log_path = root / 'logs' / 'fetch_detail_content_web.log'
    log_path.parent.mkdir(exist_ok=True)
    log_file = open(log_path, 'ab')
    subprocess.Popen(cmd, cwd=str(root), stdout=log_file, stderr=subprocess.STDOUT,
                     env={**os.environ, 'PYTHONUNBUFFERED': '1'}, start_new_session=True)
    return jsonify({'success': True,
                    'message': f'已启动正文抓取（{",".join(tables)}，仅当日发布且标题命中关键词，最多 {limit} 条/表）',
                    'log': str(log_path)})


@ai_analysis_bp.route('/api/upload-source/<int:analysis_id>', methods=['POST'])
@require_auth_write
def api_upload_source(analysis_id):
    """G2：人工上传公告正文/附件，只把解析文本追加进 analysis_content。

    不调用模型、不抓外网、不落盘原件 —— 模型主机关机期间唯一可用输入。
    """
    import logging

    upload = request.files.get('file')
    if upload is None:
        return jsonify({'success': False, 'message': '请选择文件'}), 400
    filename = _safe_filename(upload.filename)
    body = upload.read(MAX_UPLOAD_BYTES + 1)
    if not body:
        return jsonify({'success': False, 'message': '文件为空'}), 400
    if len(body) > MAX_UPLOAD_BYTES:
        return jsonify({'success': False, 'message': '文件超过 20 MB 上限'}), 413

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT analysis_content FROM analysis_projects WHERE id = %s",
                    (analysis_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': '分析记录不存在'}), 404

        text, kind = _bytes_to_text(body, filename)
        if kind == 'unsupported':
            return jsonify({'success': False,
                            'message': '不支持的文件格式（仅 PDF / Word / Excel / 纯文本）'}), 400
        if not text.strip():
            return jsonify({'success': False,
                            'message': '未能提取文本（扫描件需 OCR，当前不支持）'}), 400

        existing = row.get('analysis_content') or ''
        merged = bridge.append_uploaded_text(existing, text, filename)
        cur.execute(
            "UPDATE analysis_projects SET analysis_content = %s, operator = %s, "
            "updated_time = NOW() WHERE id = %s",
            (merged, getattr(request, 'auth_user', None) or '人工上传', analysis_id))
        conn.commit()

        combined = len(text.encode('utf-8')) + len(existing.encode('utf-8'))
        return jsonify({
            'success': True,
            'message': '附件解析文本已追加到分析结论',
            'data': {
                'filename': filename,
                'kind': kind,
                'extracted_chars': len(text),
                'stored_bytes': len(merged.encode('utf-8')),
                'truncated': combined > bridge.MAX_CONTENT_BYTES,
            },
        })
    except RuntimeError as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    except Exception as e:
        logging.getLogger(__name__).exception('G2 upload-source failed: %s', analysis_id)
        return jsonify({'success': False,
                        'message': '上传解析失败: %s' % type(e).__name__}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
