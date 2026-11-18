"""Readable delivery views; immutable audited records remain unchanged."""
import html

LABELS = {'model': '模型', 'task': '任务', 'metric': '指标',
          'source_type': '来源性质', 'trigger_threshold_semantics': '触发阈值含义'}
PRECISION_PENDING = '模型建议的短引文未能唯一定位，已退回登记原文片段；该发现仍须原文审核。'
PRECISION_REVIEWED = '短引文未能唯一定位，证据采用登记原文片段；本轮原文审核已完成，引用精度仍建议人工复核。'


def readable(text):
    # Decode PDF/model serialization artifacts only in the display view.
    return html.unescape(text)


def conditions_text(conditions):
    return '；'.join(f"{LABELS.get(key, key)}：{readable(value)}"
                    for key, value in conditions.items() if value is not None and value.strip())


def visible_claims(claims):
    return [claim for claim in claims if claim.get('presentation') not in ('limitation', 'comparison_row')]


def library_scope_issues(report, task):
    """A passage or shortlist cannot certify whole-library nonexistence."""
    import re
    if not task.get('local_library_selection'):
        return []
    pattern = r'(?:本地(?:文献|资料|论文|库)?|本地库|local (?:library|corpus))\s*(?:中|里|内|目前|并|也|尚|仍|暂|确实|\s)*(?:无|没有|不存在|未包含|缺少|缺乏|does not contain|has no|lacks)'
    issues = []
    for claim in report['claims']:
        text = readable(str(claim.get('scope', '')) + '。' + claim['text'])
        if re.search(pattern + r'[^。；\n]{0,100}(?:论文|文献|稿件|papers?|stud(?:y|ies)|manuscript)', text, re.I):
            issues.append({'claim_id': claim['claim_id'], 'evidence_ids': claim['evidence_ids'],
                'owner': 'reporter', 'severity': 'blocking', 'category': 'scope',
                'problem': '将本轮未取得证据扩大为本地全库不存在相关论文，超出了原文证据支持范围。',
                'required_fix': '核对 task.local_library_selection 的目录和选入范围；改为准确的本轮证据缺口说明。不得依据选入列表或片段断言本地全库不存在论文。'})
    return issues


def readable_scope(scope):
    """Render accidental serialized flat condition dictionaries without exposing None."""
    import ast
    if scope.strip().startswith('{') and scope.strip().endswith('}'):
        try:
            value = ast.literal_eval(scope)
        except (ValueError, SyntaxError, RecursionError):
            return readable(scope)
        if isinstance(value, dict) and all(isinstance(k, str) and (v is None or isinstance(v, str)) for k,v in value.items()):
            return conditions_text(value)
    return readable(scope)


def task_scope_issues(report, task):
    """Reject fabricated two-paper premises for a question about one work's components."""
    import re
    question = task.get('question','')
    single_work = bool(re.match(r'^[A-Za-z][A-Za-z0-9-]*\s*的.+(?:与|和).+各', question))
    issues = []
    for claim in report['claims']:
        text = claim['text']
        if single_work and re.search(r'另一篇.{0,30}(?:论文|原文|无法|定位)|两篇(?:论文|都在本地)', text):
            issues.append({'claim_id':claim['claim_id'],'evidence_ids':claim['evidence_ids'],
                'owner':'reporter','severity':'blocking','category':'scope',
                'problem':'题目询问同一研究中的两个组件，却新增了另一篇论文或缺失原文的任务前提。',
                'required_fix':'删除无来源的第二篇论文及资源缺失说明，按原问题解释同一研究中两个组件的职责与关系。'})
    return issues


def bibliography_view(front_evidence):
    """One bibliographic entry per actual document/version, retaining every evidence anchor."""
    entries = {}
    for index, card in enumerate(front_evidence, 1):
        document = card['paper']['id']
        if document not in entries:
            entries[document] = {'document_id': document, 'paper': dict(card['paper']), 'citations': []}
        entries[document]['citations'].append({'index':index, 'evidence_id':card['evidenceId'],
            'page':card['page'], 'location':card['location']})
    return list(entries.values())
