"""Bounded views; immutable source records remain complete in the workspace."""
import json
import threading
import hashlib
from .workspace import identifier
from ..errors import AppError
from .anchors import locate_quote
from .presentation import readable_scope


def scoped_claim_text(claim):
    """The reader must see the same qualification that the reviewer evaluates."""
    scope=readable_scope(claim.get('scope','').strip()) if claim.get('presentation')!='limitation' else ''
    return f"适用范围：{scope.rstrip('。.!！')}。{claim['text']}" if scope else claim['text']


class EvidenceRegistry:
    def __init__(self, spans, documents, workspace, items, limit=12):
        self.spans,self.documents,self.workspace,self.items,self.limit=spans,documents,workspace,items,limit
        self.lock=threading.RLock()
        self.extra_spans={}

    def add(self,span_id,finding,conditions,limitations=None,quote=None):
        with self.lock:
            span=self.spans().get(span_id) or self.extra_spans.get(span_id)
            if not span:
                raise AppError('UNKNOWN_SPAN','证据引用了未登记原文片段。',422)
            selected=' '.join((quote if quote is not None else span['text']).split())
            match=locate_quote(span['text'],selected,0 if quote is None else None)
            if match['status']!='matched' and quote is not None:
                # A model may select the right quote but the wrong chunk in this PDF.
                # Relocate only a unique exact occurrence, never across documents.
                document=self.documents[span['document_id']]
                occurrences=[]
                for page,text in enumerate(document.get('pages',[]),1):
                    located=locate_quote(text,selected)
                    for candidate in located['candidates']:
                        occurrences.append((page,text,candidate))
                        if len(occurrences)>1: break
                    if len(occurrences)>1: break
                if len(occurrences)==1:
                    page,text,anchor=occurrences[0]
                    actual=' '.join(text.split())[anchor['start']:anchor['end']]
                    repaired=dict(span,id=f"{span['document_id']}-p{page}-q{anchor['start']}-{anchor['end']}",
                        page=page,start=anchor['start'],end=anchor['end'],text=actual)
                    from ..library import content_regions
                    repaired['content_region']=list(content_regions(document['pages']))[page-1]
                    self.spans()[repaired['id']]=repaired
                    self.extra_spans[repaired['id']]=repaired
                    self.workspace.save('source_span',repaired,repaired['id'])
                    self.workspace.save('quote_relocation',{'requested_span_id':span_id,
                        'resolved_span_id':repaired['id'],'method':'unique_exact_in_same_document'})
                    span=repaired;span_id=span['id'];selected=actual
                    match=locate_quote(span['text'],selected,0)
            if match['status']!='matched':
                raise AppError('INVALID_EVIDENCE_QUOTE','短引文未唯一匹配登记片段或同一原始文档，不能作为已核验证据。',422)
            location={'page':span['page']}
            if 'start' in span:
                location.update(start=span['start']+match['candidates'][0]['start'],
                    end=span['start']+match['candidates'][0]['end'],basis='normalized-page-text-v1')
            old=next((e for e in self.items if e['span_ids']==[span_id] and e['quote']==selected),None)
            if old: return old
            if len(self.items)>=self.limit: return None
            card={'evidence_id':identifier('evidence'),'document_id':span['document_id'],
                'paper_id':span['paper_id'],'span_ids':[span_id],'quote':selected,
                'location':location,'finding':finding,'conditions':conditions,
                'limitations':limitations or [],'correspondence':self.documents[span['document_id']]['correspondence']}
            self.workspace.save('evidence',card,card['evidence_id'])
            self.items.append(card)
            return card


def condition_view(conditions):
    """Expose useful extracted conditions without unbounded model-written metadata."""
    result={}
    for key,value in list(conditions.items())[:8]:
        candidate={**result,key:value[:300] if isinstance(value,str) else value}
        if len(json.dumps(candidate,ensure_ascii=False))>1200: break
        result=candidate
    return result


def evidence_view(items,include_quote=True):
    return [{'evidence_id':e['evidence_id'],'document_id':e['document_id'],'paper_id':e['paper_id'],
             'location':e['location'],**({'quote':e['quote']} if include_quote else {'quote_available_via_query_evidence':True}),
             'finding_preview':e['finding'][:240],
             'conditions_preview':condition_view(e.get('conditions',{})),
             'conditions_are_extracted_not_verified':True,
             'conditions_available_via_query_evidence':True} for e in items]


def report_view(report, issue_claim_ids=()):
    if not report: return None
    return {'report_id':report['report_id'],'report_version':report['report_version'],
            'claims':[{'claim_id':c['claim_id'],'kind':c['kind'],'text_preview':c['text'][:200],
                       **({'text':c['text'],'needs_correction':True} if c['claim_id'] in issue_claim_ids else {}),
                       'evidence_ids':c['evidence_ids']} for c in report['claims']],
            'is_preview':True,'full_claims_available_via_read_report_claim':True}


def history_view(history):
    return [{'question':h.question,'sections':[{'id':s.id,'heading':s.heading,
             'paragraph_previews':[p[:120] for p in s.paragraphs[:2]]} for s in h.sections],
             'is_preview':True} for h in history[-1:]]


def paper_view(papers):
    return [{k:v for k,v in p.items() if k in ('paper_id','title','authors','year','source','identity_status','source_label','arxiv_id')}
            for p in papers]


def select_original_items(spans,evidence,document_id,page,span_id=None,evidence_id=None):
    """Resolve only task-admitted source IDs; never guess another paper/version."""
    if evidence_id or (span_id and span_id.startswith('evidence-')):
        key=evidence_id or span_id
        card=next((e for e in evidence if e['evidence_id']==key),None)
        if not card: return [],'UNKNOWN_EVIDENCE'
        if card['document_id']!=document_id or card['location']['page']!=page:
            return [],'REFERENCE_LOCATION_MISMATCH'
        return [card],None
    if span_id:
        span=spans.get(span_id)
        selected=[span] if span and span['document_id']==document_id and span['page']==page else []
    else:
        cards=[e for e in evidence if e['document_id']==document_id and e['location']['page']==page][:3]
        if cards:return cards,None
        selected=[c for c in spans.values() if c['document_id']==document_id and c['page']==page][:2]
    if not selected:return [],'UNKNOWN_SPAN'
    return [{'evidence_id':c['id'],'document_id':document_id,
        'location':{'page':page,**({'start':c['start']} if 'start' in c else {})},'quote':c['text']} for c in selected],None


def original_windows(originals, evidence):
    """Return explicitly labelled source windows read from the PDF, never rewritten summaries."""
    result=[]
    for original in originals:
        data=original['data']
        page_text=' '.join(data['text'].split())
        matching=[e for e in evidence if e['document_id']==data['document_id'] and e['location']['page']==data['page']]
        windows=[]
        for e in matching:
            quote=' '.join(e['quote'].split())
            anchor=locate_quote(data['text'],quote,e['location'].get('start'))
            position=anchor['candidates'][0]['start'] if anchor['status']=='matched' else -1
            if position<0:
                raise AppError('EVIDENCE_ORIGINAL_MISMATCH','登记证据与当前原文页不一致，拒绝审核。',409)
            start=max(0,position-300);end=min(len(page_text),position+len(quote)+300)
            windows.append({'evidence_id':e['evidence_id'],'start':start,'end':end,'text':page_text[start:end]})
        if windows:
            result.append({'document_id':data['document_id'],'page':data['page'],
                'content_hash':data['content_hash'],'windows':windows,'is_excerpt':True,
                'adjacent_pages':[p for p in data.get('adjacent_pages',[]) if
                    (p['page']<data['page'] and any(w['start']==0 for w in windows)) or
                    (p['page']>data['page'] and any(w['end']>=len(page_text)-300 for w in windows))],
                'full_page_available_via_read_original':False,'more_passages_available_via_read_original':True})
    return result


def review_payloads(task,report,evidence,papers,originals,pending,max_chars):
    by_id={e['evidence_id']:e for e in evidence}
    outline=[]
    for claim in report['claims']:
        entry={'claim_id':claim['claim_id'],'text_preview':claim['text'][:200]}
        if len(json.dumps(outline+[entry],ensure_ascii=False))>min(8000,max_chars//4): break
        outline.append(entry)
    # A batch must still see the other comparison conditions. Otherwise it
    # cannot notice a claimed lack of overlap contradicting a neighboring row.
    comparison=[]
    for row in report.get('comparison_table',[])[:20]:
        entry={key:{k:str(v)[:400] if v is not None else None for k,v in list(row.get(key,{}).items())[:8]}
               for key in ('cells','conditions')}
        if len(json.dumps(comparison+[entry],ensure_ascii=False))>min(10000,max_chars//4):
            break
        comparison.append(entry)
    def pack(claims):
        ids=list(dict.fromkeys(eid for c in claims for eid in c['evidence_ids']))
        selected=[by_id[eid] for eid in ids if eid in by_id]
        return {'task':task,'batch_claim_ids':[c['claim_id'] for c in claims],
            'audit_boundary':'Only report.claims are audit targets. Other outline entries are coverage context: never put their IDs in checked/unchecked/issues.',
            'report':{k:v for k,v in report.items() if k in
                ('report_id','report_version','evidence_snapshot_id')} | {'claims':[dict(c,text=scoped_claim_text(c)) for c in claims]},
            'evidence':[{'evidence_id':e['evidence_id'],'document_id':e['document_id'],
                'paper_id':e['paper_id'],'location':e['location'],'span_ids':e.get('span_ids',[]),'quote_in_original_windows':True}
                for e in selected],
            'papers':paper_view(papers),'original_pages':original_windows(originals,selected),
            'comparison_context':comparison,
            'requested_evidence':report.get('evidence_requests',[]),
            'report_outline':outline,
            'outline_is_preview_not_source':True,
            'extracted_condition_context':[{'evidence_id':e['evidence_id'],'paper_id':e['paper_id'],
                 'conditions_preview':condition_view(e.get('conditions',{})),
                 'must_check_against_original':True} for e in evidence],
            'comparison_context_is_preview':True,
            'more_comparison_context_available_via_read_report_claim':True,
            'previous_issues':[{'issue_id':i.get('issue_id'),'owner':i.get('owner'),
                'problem_preview':i.get('problem','')[:500],'required_fix_preview':i.get('required_fix','')[:500]} for i in pending]}
    groups=[];current=[]
    for claim in report['claims']:
        candidate=pack(current+[claim])
        if len(json.dumps(candidate,ensure_ascii=False))>max_chars or len(current)>=6:
            if current: groups.append(pack(current));current=[]
            candidate=pack([claim])
            if len(json.dumps(candidate,ensure_ascii=False))>max_chars:
                raise AppError('CONTEXT_TOO_LARGE','单条主张所需原文超过审核预算，请拆分研究问题。',400)
        current.append(claim)
    if current: groups.append(pack(current))
    return groups
