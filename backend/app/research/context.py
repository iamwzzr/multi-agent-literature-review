"""Bounded views; immutable source records remain complete in the workspace."""
import json
import threading
from .workspace import identifier
from ..errors import AppError


class EvidenceRegistry:
    def __init__(self, spans, documents, workspace, items, limit=12):
        self.spans,self.documents,self.workspace,self.items,self.limit=spans,documents,workspace,items,limit
        self.lock=threading.RLock()

    def add(self,span_id,finding,conditions,limitations=None):
        with self.lock:
            span=self.spans().get(span_id)
            if not span:
                raise AppError('UNKNOWN_SPAN','证据引用了未登记原文片段。',422)
            old=next((e for e in self.items if e['span_ids']==[span_id]),None)
            if old: return old
            if len(self.items)>=self.limit: return None
            card={'evidence_id':identifier('evidence'),'document_id':span['document_id'],
                'paper_id':span['paper_id'],'span_ids':[span_id],'quote':span['text'],
                'location':{'page':span['page']},'finding':finding,'conditions':conditions,
                'limitations':limitations or [],'correspondence':self.documents[span['document_id']]['correspondence']}
            self.workspace.save('evidence',card,card['evidence_id'])
            self.items.append(card)
            return card


def evidence_view(items):
    return [{'evidence_id':e['evidence_id'],'document_id':e['document_id'],'paper_id':e['paper_id'],
             'location':e['location'],'quote':e['quote'],'finding_preview':e['finding'][:240],
             'conditions_available_via_query_evidence':True} for e in items]


def report_view(report):
    if not report: return None
    return {'report_id':report['report_id'],'report_version':report['report_version'],
            'claims':[{'claim_id':c['claim_id'],'kind':c['kind'],'text_preview':c['text'][:200],
                       'evidence_ids':c['evidence_ids']} for c in report['claims']],
            'is_preview':True,'full_claims_available_via_read_report_claim':True}


def history_view(history):
    return [{'question':h.question,'sections':[{'id':s.id,'heading':s.heading,
             'paragraph_previews':[p[:120] for p in s.paragraphs[:2]]} for s in h.sections],
             'is_preview':True} for h in history[-1:]]


def paper_view(papers):
    return [{k:v for k,v in p.items() if k in ('paper_id','title','authors','year','source','identity_status','source_label','arxiv_id')}
            for p in papers]


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
            position=page_text.find(quote)
            if position<0:
                raise AppError('EVIDENCE_ORIGINAL_MISMATCH','登记证据与当前原文页不一致，拒绝审核。',409)
            start=max(0,position-300);end=min(len(page_text),position+len(quote)+300)
            windows.append({'evidence_id':e['evidence_id'],'start':start,'end':end,'text':page_text[start:end]})
        if windows:
            result.append({'document_id':data['document_id'],'page':data['page'],
                'content_hash':data['content_hash'],'windows':windows,'is_excerpt':True,
                'full_page_available_via_read_original':False,'more_passages_available_via_read_original':True})
    return result


def review_payloads(task,report,evidence,papers,originals,pending,max_chars):
    by_id={e['evidence_id']:e for e in evidence}
    def pack(claims):
        ids={eid for c in claims for eid in c['evidence_ids']}
        selected=[by_id[eid] for eid in ids if eid in by_id]
        return {'task':task,'report':{k:v for k,v in report.items() if k in
                ('report_id','report_version','evidence_snapshot_id')} | {'claims':claims},
            'evidence':[{'evidence_id':e['evidence_id'],'document_id':e['document_id'],
                'paper_id':e['paper_id'],'location':e['location'],'quote_in_original_windows':True}
                for e in selected],
            'papers':paper_view(papers),'original_pages':original_windows(originals,selected),
            'previous_issues':[{'issue_id':i.get('issue_id'),'owner':i.get('owner'),
                'problem_preview':i.get('problem','')[:500],'required_fix_preview':i.get('required_fix','')[:500]} for i in pending]}
    groups=[];current=[]
    for claim in report['claims']:
        candidate=pack(current+[claim])
        if len(json.dumps(candidate,ensure_ascii=False))>max_chars or len(current)>=3:
            if current: groups.append(pack(current));current=[]
            candidate=pack([claim])
            if len(json.dumps(candidate,ensure_ascii=False))>max_chars:
                raise AppError('CONTEXT_TOO_LARGE','单条主张所需原文超过审核预算，请拆分研究问题。',400)
        current.append(claim)
    if current: groups.append(pack(current))
    return groups
