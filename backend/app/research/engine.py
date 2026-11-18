import asyncio
import hashlib
import re
import json
from pathlib import Path
from importlib.metadata import version

from ..errors import AppError
from ..library import SearchIndex, digest_file, normalize, parse_pdf, content_regions
from ..metadata import bibliography
from ..workflow import phase
from .agents import ThreeAgents
from .context import EvidenceRegistry,evidence_view,report_view,history_view,paper_view,review_payloads,original_windows,scoped_claim_text,select_original_items
from .citations import validate_citations, display_citations, cited_paragraph
from .contracts import Budget, ResearchOutput, ReportOutput, ReviewOutput, IssueDraft, delivery_allowed, report_contract
from .comparisons import overlap_issues
from .reviewing import review_contract, incomplete_batch, merge_reviews
from .presentation import readable, conditions_text, visible_claims, PRECISION_PENDING, PRECISION_REVIEWED, library_scope_issues, task_scope_issues, bibliography_view
from .sources import AcademicSources
from .workspace import Workspace, Meter, identifier, content_hash


class ThreeAgentWorkflow:
    def __init__(self, config, store, library, model, run_id, agents=None, sources_factory=AcademicSources):
        self.config, self.store, self.library, self.run_id = config, store, library, run_id
        self.agents = agents or ThreeAgents(config)
        self.sources_factory = sources_factory
        self.report = None

    async def run(self, request, scope):
        ws = Workspace(self.store, request.project.id, self.run_id)
        budget = request.research_budget or Budget()
        meter = Meter(budget, ws)
        constrained_amount = bool(re.search(r'(?:禁止|不要|不得).{0,20}(?:估算|换算|补写金额)', request.question))
        task = {'task_id': identifier('task'), 'question': request.question,
                'subquestions': [{'id':identifier('question'),'question':q['question']} for q in request.subquestions] or [{'id':identifier('question'),'question':request.question}],
                'source_mode': request.source_mode, 'allow_local_metadata_lookup': request.allow_local_metadata_lookup,
                'scope': request.research_scope, 'output_requirements': {'max_claims':2 if constrained_amount else 4, **request.output_requirements},
                'answer_policy': {'no_estimation':constrained_amount,
                    'focus':'Determine what the collected evidence can establish about the requested quantity; leave unsupported values unknown. Do not expand into hardware specifications, complete dataset inventories or pricing recipes.' if constrained_amount else 'Answer only the requested entities and relationships.'},
                'budget': budget.model_dump(), 'uploaded_file_ids': request.uploaded_file_ids}
        ws.save('task_spec', task, task['task_id'])
        sources = self.sources_factory(self.config, ws, meter)
        papers, documents, chunks, evidence, limitations = [], {}, [], [], []
        report = review = None
        research_gaps = []
        try:
            async with asyncio.timeout(budget.seconds):
                yield phase('研究员读取资料', ['search'], summary='三 Agent：Researcher 研究；Reporter 报告；Reviewer 审核。')
                if request.source_mode != 'online':
                    selection, warnings = await self.select_local_sources(
                        request, scope, papers, documents, chunks, sources, ws, meter
                    )
                    limitations.extend(warnings)
                    ws.save('local_library_selection', selection)
                    task['local_library_selection'] = {k:v for k,v in selection.items() if k != 'catalog_titles'} | {
                        'catalog_is_preview': True, 'full_catalog_record': 'local_library_selection'}
                    if selection['strategy'] == 'bm25':
                        scope_note = (f"在本地索引的 {selection['indexed_papers']} 篇可检索文献中，"
                                      f"本轮选入 {len(selection['selected_library_papers'])} 篇目录文献供全文核查。")
                        task['local_library_scope'] = scope_note
                        yield phase('本地文献筛选完成', ['search'], summary=scope_note)
                if request.source_mode == 'online' or (request.source_mode == 'hybrid' and not chunks):
                    query = request.online_query or request.question
                    candidates, gaps = await sources.discover(query, request.source_mode)
                    limitations.extend(gaps)
                    known = {p['paper_id'] for p in papers}
                    for candidate in candidates:
                        ws.save('paper_candidate', candidate)
                        if candidate['identity_status'] != 'verified':
                            limitations.append(f"{candidate['title']}: identity={candidate['identity_status']}")
                            continue
                        if candidate['paper_id'] in known or len(papers) >= budget.documents:
                            continue
                        document, error = await sources.fetch(candidate)
                        if error:
                            limitations.append(candidate['title'] + ': ' + error)
                            continue
                        known.add(candidate['paper_id'])
                        papers.append(candidate)
                        documents[document['document_id']] = document
                        self.add_chunks(document, candidate, chunks)
                if not chunks:
                    limitations.append('当前资料中没有可检索的原文文本；请检查目录、文件可读性和来源模式。')
                    self.report = {'sections': [{'id': 'insufficient-material', 'heading': '资料不足', 'paragraphs':
                                   ['未取得当前来源政策允许使用的原文，未生成综述。'] + limitations}],
                                   'evidence': [], 'verification': 'no_evidence', 'task_status': 'blocked',
                                   'source_mode': request.source_mode, 'unresolved': limitations}
                    ws.save('delivery', self.report)
                    for event in self.deliver():
                        yield event
                    return
                index = await asyncio.to_thread(SearchIndex, chunks)
                by_span = {c['id']: c for c in chunks}
                registry=EvidenceRegistry(lambda:by_span,documents,ws,evidence)
                from langchain_core.tools import tool

                @tool
                async def search_document(query: str, document_ids: list[str] | None = None) -> dict:
                    """Search admitted documents, optionally scoped to document_ids. Use English terms for English papers. Returns real span IDs."""
                    if document_ids is not None and set(document_ids)-set(documents):
                        return {'status':'error','data':None,'error':{'code':'OBJECT_NOT_FOUND'}}
                    results = await asyncio.to_thread(index.search, query, 6, document_ids)
                    return {'status': 'ok' if results else 'empty', 'data': results, 'error': None}

                parsed_originals = {}
                async def load_original_page(document_id: str, page: int) -> dict:
                    document = documents.get(document_id)
                    if not document or not 1 <= page <= len(document['pages']):
                        return {'status': 'error', 'data': None, 'error': {'code': 'OBJECT_NOT_FOUND'}}
                    actual = await asyncio.to_thread(digest_file, Path(document['path']))
                    if actual != document['content_hash']:
                        raise AppError('ORIGINAL_CHANGED', '原始文档已变化，不能继续审核。', 409)
                    if document_id not in parsed_originals:
                        parsed_originals[document_id] = await parse_pdf(Path(document['path']), self.config)
                    parsed = parsed_originals[document_id]
                    adjacent=[]
                    for number in (page-1,page+1):
                        if 1<=number<=len(parsed['pages']):
                            text=normalize(parsed['pages'][number-1])
                            start=max(0,len(text)-2200) if number<page else 0
                            end=len(text) if number<page else min(2200,len(text))
                            adjacent.append({'page':number,'start':start,'end':end,'text':text[start:end]})
                    return {'status': 'ok', 'data': {'document_id': document_id, 'page': page,
                            'text': parsed['pages'][page-1], 'content_hash': actual,
                            'adjacent_pages':adjacent}, 'error': None}

                review_read_spans: dict[str, None] = {}

                def original_reader(collect_review_spans=False):
                    @tool
                    async def read_original(document_id: str, page: int, span_id: str | None = None,
                                            evidence_id: str | None = None) -> dict:
                        """Read bounded freshly parsed original passages. Prefer evidence_id for an evidence card or span_id for a registered source span. Full pages stay local."""
                        if document_id not in documents:
                            matches = [d['document_id'] for d in documents.values() if d['paper_id'] == document_id]
                            if len(matches) == 1:
                                document_id = matches[0]
                        original = await load_original_page(document_id, page)
                        if original['status'] != 'ok':
                            return original
                        spans = {**by_span, **registry.extra_spans}
                        items, error = select_original_items(spans, evidence, document_id, page, span_id, evidence_id)
                        if error:
                            return {'status': 'error', 'data': None, 'error': {'code': error}}
                        windows = original_windows([original], items)
                        if collect_review_spans:
                            # Citation cards are already registered. Retain only the actual source spans read.
                            review_read_spans.update(dict.fromkeys(item['evidence_id'] for item in items
                                                                  if item['evidence_id'] in spans))
                        return {'status': 'ok', 'data': windows, 'error': None}
                    return read_original

                read_original = original_reader()
                review_read_original = original_reader(collect_review_spans=True)

                @tool
                def query_evidence(evidence_id: str | None = None) -> dict:
                    """Read the current program-registered evidence snapshot; never changes evidence."""
                    if evidence_id:
                        item=next((e for e in evidence if e['evidence_id']==evidence_id),None)
                        return {'status':'ok' if item else 'error','data':item,'error':None if item else {'code':'OBJECT_NOT_FOUND'}}
                    return {'status': 'ok' if evidence else 'empty', 'data': evidence_view(evidence), 'error': None}

                @tool
                def list_project_papers() -> dict:
                    """List admitted project papers with program-controlled identity and provenance."""
                    return {'status':'ok' if papers else 'empty','data':papers,'error':None}

                @tool
                def get_paper_record(paper_id: str) -> dict:
                    """Read a paper record only from the current task."""
                    found=next((p for p in papers if p['paper_id']==paper_id),None)
                    return {'status':'ok' if found else 'error','data':found,
                            'error':None if found else {'code':'OBJECT_NOT_FOUND'}}

                @tool
                def get_verification_log(paper_id: str) -> dict:
                    """Read authoritative identity evidence for an admitted project paper."""
                    if not any(p['paper_id']==paper_id for p in papers):
                        return {'status':'error','data':None,'error':{'code':'OBJECT_NOT_FOUND'}}
                    with ws.store.connect() as db:
                        rows=db.execute("SELECT payload FROM research_objects WHERE project=? AND kind='identity_check'",(ws.project,)).fetchall()
                    matches=[json.loads(r['payload']) for r in rows if json.loads(r['payload']).get('paper_id')==paper_id]
                    return {'status':'ok' if matches else 'empty','data':matches,'error':None}

                @tool
                def record_evidence(span_id: str, finding: str, conditions: dict[str,str | None], quote: str | None = None) -> dict:
                    """Register evidence from an existing span. Quotes and location are copied by the program, never supplied by the model."""
                    try:
                        card=registry.add(span_id,finding,conditions,quote=quote)
                    except AppError as error:
                        if error.code!='INVALID_EVIDENCE_QUOTE': raise
                        return {'status':'error','data':None,'error':{'code':error.code,
                            'message':'Quote is not an exact unique source match. Read the original or omit quote to retain the registered passage.'}}
                    return {'status':'ok' if card else 'error','data':card,
                            'error':None if card else {'code':'EVIDENCE_BUDGET'}}

                @tool
                def read_report_claim(claim_id: str) -> dict:
                    """Read the complete previous draft claim by ID; initial draft context is only a preview."""
                    claim=next((c for c in (report or {}).get('claims',[]) if c['claim_id']==claim_id),None)
                    return {'status':'ok' if claim else 'error','data':claim,'error':None if claim else {'code':'OBJECT_NOT_FOUND'}}

                discovered={p['paper_id']:p for p in papers}
                online_admission = asyncio.Lock()
                @tool
                async def search_verified_papers(query: str) -> dict:
                    """Search authoritative online paper records under the immutable task source policy. Return each candidate's verification status."""
                    if request.source_mode=='local':
                        return {'status':'error','data':None,'error':{'code':'SOURCE_POLICY_DENIED'}}
                    found,gaps=await sources.discover(query,request.source_mode)
                    for item in found: discovered[item['paper_id']]=item
                    return {'status':'ok' if found else 'error' if gaps else 'empty','data':found,
                            'error':{'code':gaps[0]} if gaps else None}

                @tool
                async def fetch_paper_content(paper_id: str) -> dict:
                    """Fetch only a registered verified online candidate, check PDF correspondence, and admit matching text."""
                    nonlocal index,by_span
                    candidate=discovered.get(paper_id)
                    if request.source_mode=='local' or not candidate or candidate.get('source')!='online' or candidate['identity_status']!='verified':
                        return {'status':'error','data':None,'error':{'code':'SOURCE_POLICY_DENIED'}}
                    async with online_admission:
                        if len(papers)>=budget.documents:
                            return {'status':'error','data':None,'error':{'code':'DOCUMENT_BUDGET'}}
                        if any(p['paper_id']==paper_id for p in papers):
                            return {'status':'ok','data':candidate,'error':None}
                        document,error=await sources.fetch(candidate)
                        if error:
                            return {'status':'error','data':None,'error':{'code':error}}
                        papers.append(candidate)
                        documents[document['document_id']]=document
                        self.add_chunks(document,candidate,chunks)
                        index=await asyncio.to_thread(SearchIndex,chunks)
                        by_span={c['id']:c for c in chunks}
                        return {'status':'ok','data':{k:v for k,v in document.items() if k not in ('pages','path')},'error':None}

                researcher_tools=[search_document,read_original,record_evidence,query_evidence,list_project_papers,get_paper_record,get_verification_log]
                if request.source_mode!='local': researcher_tools.extend([search_verified_papers,fetch_paper_content])
                pending, feedback = [], 0
                revision_evidence_ids = []
                need_research = True
                while True:
                    if need_research:
                        if pending and request.source_mode == 'hybrid' and len(papers) < budget.documents:
                            candidates, gaps = await sources.discover(' '.join(i['required_fix'] for i in pending)[:1000], 'hybrid')
                            limitations.extend(gaps)
                            for candidate in candidates:
                                ws.save('paper_candidate', candidate)
                                if candidate['identity_status'] != 'verified' or any(p['paper_id'] == candidate['paper_id'] for p in papers) or len(papers) >= budget.documents:
                                    continue
                                document, error = await sources.fetch(candidate)
                                if error:
                                    limitations.append(error)
                                    continue
                                if any(d['content_hash'] == document['content_hash'] for d in documents.values()):
                                    ws.save('version_link', {'paper_id': candidate['paper_id'], 'content_hash': document['content_hash'], 'reason': 'identical document bytes'})
                                    continue
                                papers.append(candidate)
                                documents[document['document_id']] = document
                                self.add_chunks(document, candidate, chunks)
                            index = await asyncio.to_thread(SearchIndex, chunks)
                            by_span = {c['id']: c for c in chunks}
                        if sum(len(d['pages']) for d in documents.values()) > self.config.max_total_pages:
                            raise AppError('BUDGET_EXHAUSTED', '总页数预算耗尽。', 409)
                        yield phase('Researcher 提取原文证据', ['analysis', 'search'], summary='记录原文片段、实验条件和资料缺口。')
                        initial_passages=await asyncio.to_thread(index.search_many,
                            [request.question,*[entry['question'] for entry in request.subquestions]],6)
                        condition_passages=[]
                        if re.search(r'可比|条件|数据集|指标|comparab|conditions|datasets|metrics',request.question,re.I):
                            seen={c['id'] for c in initial_passages}
                            for document_id in list(documents)[:budget.documents]:
                                for query in ('base model generator architecture parameters',
                                              'datasets benchmarks evaluation metrics experimental setup'):
                                    hits=await asyncio.to_thread(index.search,query,1,[document_id],content_region='body')
                                    if not hits:
                                        hits=await asyncio.to_thread(index.search,query,1,[document_id])
                                    if hits and hits[0]['id'] not in seen and len(condition_passages)<6:
                                        seen.add(hits[0]['id']);condition_passages.append(hits[0])
                            meter.charge('tool','comparison_condition_retrieval')
                            ws.save('condition_retrieval',{'queries_per_document':2,
                                'span_ids':[c['id'] for c in condition_passages]})
                        initial_originals=[]
                        for doc_id,page in dict.fromkeys((c['document_id'],c['page']) for c in initial_passages):
                            meter.charge('tool','researcher_read_original')
                            initial_originals.append(await load_original_page(doc_id,page))
                        initial_cards=[{'evidence_id':c['id'],'document_id':c['document_id'],
                                        'location':{'page':c['page'],**({'start':c['start']} if 'start' in c else {})},'quote':c['text']} for c in initial_passages]
                        result = await self.agents.invoke('researcher', {'task': task, 'papers': paper_view(papers),
                            'documents': [{k: v for k,v in d.items() if k not in ('pages','path')} for d in documents.values()],
                            'initial_passages': initial_passages,
                            'condition_passages':condition_passages,
                            # The same quotations are already in initial_passages;
                            # retain their hashes and neighboring context without duplicating them.
                            'initial_context': [{k:v for k,v in window.items() if k!='windows'}
                                                for window in original_windows(initial_originals,initial_cards)],
                            'issues': pending, 'existing_evidence': evidence_view(evidence,include_quote=False)}, ResearchOutput,
                            researcher_tools, meter)
                        ws.save('researcher_result', dict(result.model_dump(), task_id=task['task_id'],
                            paper_ids=[p['paper_id'] for p in papers], issue_responses=[dict(i,status='addressed') for i in pending]))
                        insufficient=(not result.evidence and not evidence and bool(result.unresolved_gaps)
                                      and not result.errors and result.outcome!='execution_error')
                        if result.status == 'failed' and not insufficient:
                            raise AppError('AGENT_FAILED', 'Researcher 执行失败，未形成有效研究结果。', 503)
                        if result.outcome=='execution_error':
                            raise AppError('AGENT_FAILED','Researcher 记录了实际执行错误。',503)
                        research_gaps=list(dict.fromkeys(research_gaps+result.unresolved_gaps))
                        drafts=list(result.evidence)
                        invalid=[d for d in drafts if d.span_id not in by_span and d.span_id not in registry.extra_spans]
                        if invalid:
                            import difflib
                            candidates={}
                            for item in invalid:
                                close=difflib.get_close_matches(item.span_id,list(by_span),n=2,cutoff=.4)
                                for key in close: candidates[key]=by_span[key]
                                for chunk in index.search(item.finding,2): candidates[chunk['id']]=chunk
                            candidates=dict(list(candidates.items())[:12])
                            for chunk in initial_passages+condition_passages:
                                if len(candidates)>=12: break
                                candidates.setdefault(chunk['id'],chunk)
                            ws.save('span_repair_request',{'invalid_span_ids':[d.span_id for d in invalid],
                                'candidate_span_ids':list(candidates)})
                            repaired=await self.agents.invoke('researcher',{'task':task,
                                'repair_instruction':'Repair only invalid span references using these actual originals. '
                                    'Read the text; keep only supported findings. Never guess IDs. Return empty evidence with scoped gaps if unsupported.',
                                'invalid_drafts':[d.model_dump() for d in invalid],
                                'candidate_originals':list(candidates.values())},ResearchOutput,[],meter)
                            ws.save('span_repair_result',repaired.model_dump())
                            if repaired.status=='failed' or repaired.outcome=='execution_error' or repaired.errors:
                                raise AppError('AGENT_FAILED','片段 ID 纠正未成功，拒绝登记修复结果。',503)
                            if any(d.span_id not in by_span and d.span_id not in registry.extra_spans for d in repaired.evidence):
                                raise AppError('UNKNOWN_SPAN','片段 ID 纠正后仍无效，拒绝登记证据。',422)
                            research_gaps.extend(repaired.unresolved_gaps)
                            drafts=[d for d in drafts if d.span_id in by_span]+list(repaired.evidence)
                        for item in drafts:
                            try:
                                card=registry.add(item.span_id,item.finding,item.conditions,item.limitations,quote=item.quote)
                            except AppError as error:
                                if error.code!='INVALID_EVIDENCE_QUOTE': raise
                                note='模型建议的短引文未能唯一定位，已退回登记原文片段；该发现仍须原文审核。'
                                limitations.append(note)
                                ws.save('quote_precision_fallback',{'span_id':item.span_id,'reason':error.code})
                                card=registry.add(item.span_id,item.finding,item.conditions,item.limitations+[note])

                            if card is None:
                                limitations.append('本轮证据数量上限已到，额外材料未进入当前证据快照。')
                    if not evidence:
                        limitations.append('研究未取得可登记的原文证据，未生成正常综述。')
                        self.report = self.render(None,None,evidence,papers,documents,'blocked',limitations+[
                            '在本次允许的资料及已执行的检索范围内，未取得能回答该问题的可登记原文证据；'
                            '这不证明整篇文献或整个领域不存在相关信息。'],meter)
                        self.report.update(verification='no_evidence',stop_reason='insufficient_evidence')
                        self.report['unverified_research_notes']=research_gaps
                        ws.save('delivery',self.report)
                        for event in self.deliver(): yield event
                        return
                    ws.save('researcher_handoff', {'task_id':task['task_id'], 'paper_ids':[p['paper_id'] for p in papers],
                        'evidence_ids':[e['evidence_id'] for e in evidence], 'status':'partial' if limitations else 'success'})
                    snapshot_id = identifier('snapshot')
                    ws.save('evidence_snapshot', {'evidence_ids': [e['evidence_id'] for e in evidence],
                            'hash': content_hash(evidence)}, snapshot_id)
                    yield phase('Reporter 综合报告', ['writing'], ['search', 'analysis'])
                    task['execution_scope'] = {'evidence_papers': [
                        {'paper_id':p['paper_id'],'title':p['title'],
                         'pages':sorted({e['location']['page'] for e in evidence if e['paper_id']==p['paper_id']})}
                        for p in papers if any(e['paper_id']==p['paper_id'] for e in evidence)],
                        'evidence_count':len(evidence), 'is_exhaustive_library_audit':False}
                    ws.save('report_scope',{'snapshot_id':snapshot_id, **task['execution_scope']})
                    reporter_payload = {'task': task, 'papers': paper_view(papers),
                        'evidence': evidence_view(evidence), 'previous_report': report_view(report,[i.get('claim_id') for i in pending]), 'issues': pending,
                        'research_gaps':research_gaps,
                        'history': history_view(request.history)}
                    if revision_evidence_ids:
                        reporter_payload['reviewer_evidence_ids'] = revision_evidence_ids
                    written = await self.agents.invoke('reporter', reporter_payload,
                        report_contract(task), [query_evidence, read_original, get_paper_record, read_report_claim], meter)
                    if written.status == 'failed':
                        raise AppError('AGENT_FAILED', 'Reporter 执行失败。', 503)
                    allowed_ids = {e['evidence_id'] for e in evidence}
                    if any(set(c.evidence_ids) - allowed_ids for c in written.claims) or any(set(r.evidence_ids)-allowed_ids for r in written.comparison_table):
                        raise AppError('UNKNOWN_EVIDENCE', '报告包含未登记证据 ID，已拒绝交付。', 422)
                    for claim in written.claims:
                        validate_citations(claim.text, claim.evidence_ids, allowed_ids)
                        validate_citations(claim.scope, claim.evidence_ids, allowed_ids)
                    for row in written.comparison_table:
                        for value in list(row.cells.values()) + list(row.conditions.values()):
                            if value:
                                validate_citations(value, row.evidence_ids, allowed_ids)
                    for limitation in written.limitations:
                        validate_citations(limitation, allowed_ids, allowed_ids)
                    review = None  # A previous verdict never belongs to this new draft.
                    report = {'report_id': identifier('report'), 'report_version': feedback+1,
                              'evidence_snapshot_id': snapshot_id,
                              'claims': [dict(c.model_dump(), claim_id=identifier('claim')) for c in written.claims],
                              'comparison_table': [r.model_dump() for r in written.comparison_table], 'limitations': written.limitations,
                              'evidence_requests':[{'request_id':f'request-{n}','question':q}
                                                   for n,q in enumerate(written.evidence_requests,1)],
                              'status': written.status, 'errors':written.errors, 'task_id':task['task_id'],
                              'issue_responses':[dict(i,status='addressed') for i in pending]}
                    for row in report['comparison_table']:
                        report['claims'].append({'claim_id': identifier('claim'), 'kind': 'synthesis',
                            'text': '；'.join(f"{k}: {v if v is not None else '未知（未报告）'}" for k,v in row['cells'].items()),
                            'evidence_ids': row['evidence_ids'], 'scope': conditions_text(row['conditions']),
                            'presentation': 'comparison_row'})
                    # Model-written limitations are not an unreviewed prose escape hatch.
                    for text in report['limitations']:
                        cited=re.findall(r'\bevidence-[A-Za-z0-9_-]+\b',text)
                        report['claims'].append({'claim_id':identifier('claim'),'kind':'synthesis',
                            'presentation':'limitation','text':text,
                            'evidence_ids':list(dict.fromkeys(cited)),
                            'scope':'Check the factual support and the stated scope of this limitation.'})
                    ws.save('report_draft', report, report['report_id'])
                    yield phase('Reviewer 回读原文审核', ['verification'], ['search', 'analysis', 'writing'])
                    originals = []
                    for document_id, page in dict.fromkeys((e['document_id'], e['location']['page']) for e in evidence):
                        meter.charge('tool', 'reviewer_read_original')
                        originals.append(await load_original_page(document_id,page))
                    # Keep original pages intact; split the audit by claims instead of truncating source text.
                    results = []
                    feedback_source_spans: dict[str, None] = {}
                    for batch_number, review_payload in enumerate(review_payloads(task,report,evidence,papers,originals,pending,self.config.max_prompt_chars-2000),1):
                        batch_id = f"{report['report_id']}-batch-{batch_number}"
                        review_payload['batch_id'] = batch_id
                        ws.save('review_context',{'batch_id':batch_id,'report_version':report['report_version'],
                            'characters':len(json.dumps(review_payload,ensure_ascii=False)),
                            'claim_ids':[c['claim_id'] for c in review_payload['report']['claims']],
                            'evidence_ids':[e['evidence_id'] for e in review_payload['evidence']]})
                        schema = review_contract(review_payload)
                        result = None
                        for attempt in range(2):
                            review_read_spans.clear()
                            ws.save('review_batch_input',{'batch_id':batch_id,'attempt':attempt+1,'payload':review_payload})
                            try:
                                returned = await self.agents.invoke('reviewer',review_payload,
                                    schema,[review_read_original,query_evidence,get_paper_record,get_verification_log,read_report_claim],meter)
                                ws.save('review_batch_output',{'batch_id':batch_id,'attempt':attempt+1,
                                    'report_version':report['report_version'],'result':returned.model_dump()})
                                result = schema.model_validate(returned.model_dump())
                                break
                            except ValueError as error:
                                ws.save('review_batch_invalid',{'batch_id':batch_id,'reason':str(error)[:1500]})
                                review_payload['protocol_correction'] = str(error)[:1500]
                            except AppError as error:
                                if error.code != 'AGENT_SCHEMA_INVALID': raise
                                ws.save('review_batch_invalid',{'batch_id':batch_id,'reason':error.code})
                                break
                        result = result or incomplete_batch(review_payload,'INVALID_REVIEW_BATCH')
                        if any(issue.severity == 'blocking' for issue in result.issues) or any(
                                assessment.necessary for assessment in result.request_assessments):
                            feedback_source_spans.update(review_read_spans)
                        ws.save('review_batch_result',{'batch_id':batch_id,'report_version':report['report_version'],
                            'claim_ids':[c['claim_id'] for c in review_payload['report']['claims']],
                            'evidence_ids':[e['evidence_id'] for e in review_payload['evidence']],
                            'result':result.model_dump()})
                        results.append(result)
                    checked = merge_reviews(results)
                    conflicts=overlap_issues(report,evidence,task) + library_scope_issues(report,task) + task_scope_issues(report,task)
                    for claim in report['claims']:
                        if claim.get('presentation')=='limitation' and not claim['evidence_ids']:
                            conflicts.append({'claim_id':claim['claim_id'],'evidence_ids':[],
                                'owner':'reporter','severity':'blocking','category':'citation',
                                'problem':'限制说明没有明确的原文证据引用；程序不会自动把全部证据分配给它。',
                                'required_fix':'若保留这条事实限制，请在 limitations 字符串中写出支持它的 [evidence-ID]；'
                                    '删除不必要的自述或无证据断言，不要添加无关引用。'})
                    if conflicts:
                        checked.issues.extend(IssueDraft(**i) for i in conflicts)
                        checked.verdict='revise'
                    claim_ids = {c['claim_id'] for c in report['claims']}
                    if set(checked.checked_claim_ids) - claim_ids or set(checked.unchecked_claim_ids) - claim_ids:
                        raise AppError('UNKNOWN_CLAIM', '审核引用了不存在的主张 ID。', 422)
                    if any(i.claim_id not in claim_ids or set(i.evidence_ids)-allowed_ids for i in checked.issues):
                        raise AppError('UNKNOWN_CLAIM', '审核问题包含无效对象 ID。', 422)
                    review = dict(checked.model_dump(), task_id=task['task_id'],
                                  claim_checks=[{'claim_id':c,'checked':True} for c in checked.checked_claim_ids],
                                  reviewed_report_version=report['report_version'],
                                  reviewed_evidence_snapshot_id=snapshot_id)
                    review['issues'] = [dict(i, issue_id=identifier('issue'), status='open') for i in review['issues']]
                    if any(set(re.findall(r'\bevidence-[A-Za-z0-9_-]+\b',i['problem']+' '+i['required_fix']))-allowed_ids for i in review['issues']):
                        review['verdict']='undetermined'
                        review['errors'].append('UNKNOWN_REVIEW_EVIDENCE')
                    known_requests={q['request_id'] for q in report['evidence_requests']}
                    if any(a['request_id'] not in known_requests for a in review['request_assessments']):
                        review['status']='partial'
                        review['verdict']='undetermined'
                        review['errors'].append('UNKNOWN_REQUEST')
                        limitations.append('审核引用了不存在的补证请求ID，当前草稿尚未完成有效审核。')
                    required_requests=[]
                    for supplement in report['evidence_requests']:
                        assessments=[a for a in review['request_assessments'] if a['request_id']==supplement['request_id']]
                        if not review['question_covered'] or not assessments or any(a['necessary'] for a in assessments):
                            required_requests.append(supplement)
                    if required_requests:
                        review['verdict']='undetermined'
                    ws.save('request_assessment',{'report_version':report['report_version'],
                        'assessments':review['request_assessments'],'required_request_ids':[q['request_id'] for q in required_requests]})
                    ws.save('review_result', review)
                    if delivery_allowed(report, review, evidence, papers):
                        ws.save('completion_decision',{'report_id':report['report_id'],'report_version':report['report_version'],
                            'evidence_snapshot_id':snapshot_id,'producer_status':report['status'],
                            'question_covered':review['question_covered'],'basis':'complete_valid_review_and_source_version_gates'})
                        for issue in pending:
                            ws.save('issue_resolution', dict(issue, status='resolved', report_version=report['report_version']))
                        self.report = self.render(report, review, evidence, papers, documents, 'completed', limitations, meter)
                        break
                    if feedback >= budget.feedback_batches or checked.status == 'failed':
                        self.report = self.render(report, review, evidence, papers, documents, 'partial', limitations, meter)
                        break
                    pending = [i for i in review['issues'] if i['severity']=='blocking']+[{'issue_id':identifier('issue'),'owner':'researcher',
                        'problem':q['question'],'required_fix':q['question'],'status':'open'} for q in required_requests]
                    revision_evidence_ids = []
                    if pending and feedback_source_spans:
                        # The reviewed snapshot stays immutable. New originals belong to the next draft.
                        for span_id in feedback_source_spans:
                            card = registry.add(span_id, 'Original passage located during review for this revision.', {})
                            if card is None:
                                break
                            if card['evidence_id'] not in allowed_ids:
                                revision_evidence_ids.append(card['evidence_id'])
                        ws.save('review_evidence_handoff', {'from_snapshot_id': snapshot_id,
                            'next_report_version': report['report_version'] + 1,
                            'source_span_ids': list(feedback_source_spans), 'evidence_ids': revision_evidence_ids})
                    for issue in pending:
                        ws.save('issue_response', dict(issue, status='addressed', next_report_version=report['report_version']+1))
                    need_research = any(i['owner'] == 'researcher' for i in pending) or bool(checked.unchecked_claim_ids)
                    feedback += 1
                    ws.save('feedback_batch', {'batch': feedback, 'issues': pending})
                    yield phase('按责任方返工', ['search' if need_research else 'writing'], ['verification'], feedback=True)
        except (AppError, TimeoutError) as error:
            if isinstance(error, TimeoutError) or getattr(error, 'code', '') == 'BUDGET_EXHAUSTED':
                limitations.append('预算或时间已耗尽；停止执行不代表审核通过。')
                self.report = self.render(report, review, evidence, papers, documents, 'partial' if report else 'blocked', limitations, meter)
            else:
                raise
        ws.save('delivery', self.report)
        for event in self.deliver():
            yield event

    async def select_local_sources(self, request, scope, papers, documents, chunks, sources, ws, meter):
        meter.charge('tool', 'index_local')
        local_chunks, warnings = await self.library.index(request.project.id, scope)
        indexed_papers = {chunk['paper']['id']: chunk['paper'] for chunk in local_chunks}
        uploads = []
        for file_id in request.uploaded_file_ids:
            upload = ws.get(file_id)
            if upload.get('kind') != 'upload':
                raise AppError('OBJECT_NOT_FOUND', '上传对象无效。', 404)
            uploads.append(Path(upload['path']))

        limit = meter.limit.documents
        shortlist = len(indexed_papers) + len(uploads) > limit
        candidates = list(indexed_papers)
        if shortlist:
            # Explicit uploads come first when the directory cannot fit.
            for path in uploads:
                await self.add_local(path, None, papers, documents, chunks, sources, request, ws, meter)
            uploads = []
            if request.source_mode == 'hybrid' and len(papers) + 1 < limit:
                limit -= 1
            if len(papers) < limit and candidates:
                meter.charge('tool', 'search_local_library')
                queries = [request.question, *(entry['question'] for entry in request.subquestions)]
                candidates = await asyncio.to_thread(lambda: SearchIndex(local_chunks).rank_papers(queries))

        before_directory = len(papers)
        for paper_id in candidates:
            if len(papers) >= limit:
                break
            path = await asyncio.to_thread(self.library.source, request.project.id, paper_id)
            await self.add_local(path, indexed_papers[paper_id], papers, documents, chunks, sources, request, ws, meter)
        selected = [{'paper_id': paper['paper_id'], 'title': paper['title']} for paper in papers[before_directory:]]
        for path in uploads:
            await self.add_local(path, None, papers, documents, chunks, sources, request, ws, meter)

        return {
            'strategy': 'bm25' if shortlist else 'all',
            'indexed_papers': len(indexed_papers),
            'selected_library_papers': selected,
            'catalog_titles': [p['title'] for p in indexed_papers.values()],
            'coverage_note': '目录仅表示已索引文件；选入不等于已阅读，已阅读不等于取得支持证据。未取得证据不能推出本地不存在该论文。',
            'admitted_local_papers': len(papers),
            'document_budget': meter.limit.documents,
        }, warnings

    async def add_local(self, path, metadata, papers, documents, chunks, sources, request, ws, meter):
        meter.charge('tool', 'register_local_document')
        raw = await asyncio.to_thread(Path(path).read_bytes)
        digest = hashlib.sha256(raw).hexdigest()
        if any(d['content_hash'] == digest and d['source'] == 'user_upload' for d in documents.values()):
            return
        if len(papers) >= meter.limit.documents:
            raise AppError('BUDGET_EXHAUSTED', '文档数量预算耗尽。', 409)
        folder = self.config.runtime_dir / 'originals' / hashlib.sha256(ws.project.encode()).hexdigest()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (digest+'.pdf')
        if not target.exists():
            target.write_bytes(raw)
        parsed = await parse_pdf(target, self.config)
        paper = {'paper_id': 'local-'+digest, 'source': 'local',
                 'title': (metadata or {}).get('title') or parsed['title'] or Path(path).stem,
                 'authors': [parsed['author']] if parsed['author'] else [], 'year': None,
                 'identity_status': 'unresolved', 'publication_status': None,
                 'source_label': '用户提供的文档；公开发表身份未外部核实。'}
        supplied=bibliography(path,digest)
        if supplied:
            paper.update(supplied)
            paper['source_label']='用户提供的文档及哈希绑定题录；公开发表身份未外部核实。'
        if request.allow_local_metadata_lookup:
            lookup = await sources.lookup_local(parsed['pages'][0], True)
            paper['identity_status'] = lookup['identity_status']
            paper['verification_record'] = lookup
            if lookup['identity_status'] == 'verified':
                paper['source_label'] = '用户提供的文档；公开身份已与 Crossref 权威记录匹配。'
        document = {'document_id': 'document-'+hashlib.sha256((digest+paper['paper_id']+version('pypdf')).encode()).hexdigest(), 'paper_id': paper['paper_id'], 'content_hash': digest,
                    'path': str(target), 'source': 'user_upload', 'version': digest,
                    'parser_version': 'pypdf:'+version('pypdf')+';chunks-v1', 'content_scope': 'user_document',
                    'correspondence': 'user_provided', 'pages': parsed['pages']}
        ws.save('paper_record', paper)
        ws.save('document', document, document['document_id'])
        papers.append(paper)
        documents[document['document_id']] = document
        self.add_chunks(document, paper, chunks)

    @staticmethod
    def add_chunks(document, paper, chunks):
        for page, (text,region) in enumerate(zip(document['pages'],content_regions(document['pages'])), 1):
            text = normalize(text)
            for offset in range(0, len(text), 1300):
                raw_passage = text[offset:offset+1600]
                passage = raw_passage.strip()
                if len(passage) < 20:
                    continue
                chunks.append({'id': f"{document['document_id']}-p{page}-o{offset}",
                    'document_id': document['document_id'], 'paper_id': paper['paper_id'], 'page': page, 'text': passage,
                    'start':offset+len(raw_passage)-len(raw_passage.lstrip()),
                    'end':offset+len(raw_passage.rstrip()),'content_region':region,
                    'paper': {'id': paper['paper_id'], 'title': paper['title']}})

    @staticmethod
    def render(report, review, evidence, papers, documents, status, limitations, meter):
        report = report or {'claims': [], 'comparison_table': [], 'limitations': []}
        references, front_evidence = {}, []
        by_id = {e['evidence_id']: e for e in evidence}
        by_paper = {p['paper_id']: p for p in papers}
        sections = []
        # Allocate one stable display index per evidence card before converting prose.
        keys = list(dict.fromkeys(
            [key for claim in report['claims'] for key in claim['evidence_ids']] +
            [key for row in report['comparison_table'] for key in row['evidence_ids']] +
            [key for value in limitations + report['limitations'] +
             [i['problem'] for i in (review or {}).get('issues', [])]
             for key in re.findall(r'\bevidence-[A-Za-z0-9_-]+\b', value) if key in by_id]))
        for key in keys:
            if key not in by_id:
                raise AppError('UNKNOWN_EVIDENCE', '交付包含无法定位的证据引用。', 422)
            e = by_id[key]
            p = by_paper[e['paper_id']]
            d = documents[e['document_id']]
            references[key] = len(references) + 1
            front_evidence.append({'paper': {'id': d['document_id'], 'title': p['title'],
                'author': ', '.join(p['authors']) or '作者未知', 'year': p['year'], 'pages': len(d['pages']),
                'summary': p.get('source_label', '在线权威记录已核验；结论须另行审核。'), 'pdfAvailable': True},
                'page': e['location']['page'], 'excerpt': e['quote'],'evidenceId':e['evidence_id'],'location':e['location'],
                'context': display_citations(e['finding'], references) if not re.search(r'\bevidence-', e['finding']) else '原文证据'})
        headings = {'finding': '研究发现', 'synthesis': '综合分析与比较', 'proposal': '研究建议'}
        groups = {}
        for claim in visible_claims(report['claims']):
            heading = headings.get(claim['kind'], claim['kind'])
            if heading not in groups:
                groups[heading] = {'id': claim['claim_id'], 'heading': heading, 'paragraphs': []}
                sections.append(groups[heading])
            groups[heading]['paragraphs'].append(readable(cited_paragraph(
                scoped_claim_text(claim), claim['evidence_ids'], references)))
        display_table = [dict(row,
            cells={k: readable(display_citations(v, references)) if v is not None else '未知（未报告）' for k, v in row['cells'].items()},
            conditions={k: readable(display_citations(v, references)) for k, v in row.get('conditions', {}).items() if v is not None and v.strip()})
            for row in report['comparison_table']]
        warnings = list(dict.fromkeys(limitations + report['limitations'] +
                    [i['problem'] for i in (review or {}).get('issues', [])]))
        # Preserve raw review objects for audit, but do not treat an invented
        # identifier in reviewer commentary as a registered report citation.
        warnings = [display_citations(re.sub(r'\bevidence-[A-Za-z0-9_-]+\b',
            lambda m:m[0] if m[0] in by_id else '（未登记的证据标识）',value), references) for value in warnings]
        warnings = [readable(PRECISION_REVIEWED if status == 'completed' and value == PRECISION_PENDING else value) for value in warnings]
        if status != 'completed':
            warnings.insert(0, '以下为未通过最终审核的部分草稿，不能作为已审核报告使用。')
        if warnings or not sections:
            sections.append({'id': 'unresolved', 'heading': '状态与未解决问题', 'paragraphs': warnings or ['资料不足。']})
        return {'sections': sections, 'evidence': front_evidence, 'bibliography':bibliography_view(front_evidence), 'claims': report['claims'],
                'followup_requests':report.get('evidence_requests',[]),
                'comparison_table': display_table, 'review': review,
                'report_version': report.get('report_version'), 'evidence_snapshot_id': report.get('evidence_snapshot_id'),
                'producer_status':report.get('status'), 'task_status': status, 'verification': 'passed' if status == 'completed' else 'with_warnings',
                'unresolved': warnings, 'usage': {'model_calls': meter.models, 'tool_calls': meter.tools, 'tokens': meter.tokens}}

    def deliver(self):
        for n, item in enumerate(self.report['evidence'], 1):
            yield {'type': 'evidence', 'index': n, 'item': item}
        for section in self.report['sections']:
            yield {'type': 'section', 'id': section['id'], 'heading': section['heading']}
            for n, text in enumerate(section['paragraphs']):
                yield {'type': 'delta', 'sectionId': section['id'], 'paragraph': n, 'text': text}
        yield {'type': 'done', 'runId': self.run_id, 'verification': self.report['verification'],
               'taskStatus': self.report['task_status']}
