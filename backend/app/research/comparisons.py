"""Conservative consistency checks, not automatic judgments of scientific truth."""
import re
from collections import defaultdict


def overlap_issues(report,evidence):
    entries=[]
    stop={'task','tasks','dataset','datasets','and','or','etc','six','four','three','two','one','unknown','none','selected','custom'}
    for item in evidence:
        for key,value in item.get('conditions',{}).items():
            if re.search(r'dataset|task|数据集|任务',key,re.I) and isinstance(value,str):
                names={t.casefold() for t in re.findall(r'[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*',value)}-stop
                entries.append((item['paper_id'],item['evidence_id'],names))
    pattern=(r'(?:任务|数据集|评测|datasets?|tasks?).{0,40}'
             r'(?:互不重叠|完全不重叠|不重合|无重合|没有重叠|无交集|disjoint|non.overlapping|no overlap)|'
             r'(?:no shared|no common|disjoint|non.overlapping).{0,40}(?:tasks?|datasets?)')
    issues=[]
    limited_reading=any(re.search(r'未(?:核对|检查|阅读|读取).*(?:其余|完整|全文|全部|附录)|'
                                  r'(?:not|without).*(?:full text|entire paper|appendix)',s,re.I)
                       for s in report.get('limitations',[]))
    for claim in report['claims']:
        if (limited_reading and not re.search(r'所检查|已检查|已提供的证据|所提供.*(?:片段|证据)|provided excerpts',claim['text'],re.I)
            and re.search(r'没有任何一篇|没有任何论文|所有论文均未|no (?:paper|study)|none of the (?:papers|studies)',claim['text'],re.I)):
            issues.append({'claim_id':claim['claim_id'],'evidence_ids':claim['evidence_ids'],
                'owner':'reporter','severity':'blocking','problem':'报告承认未检查完整正文或附录，却作出了整篇论文范围的否定。',
                'required_fix':'将否定结论限定到实际检查过的证据范围，或补齐足以支持整篇范围结论的核查。'})
        if re.search(pattern,claim['text'],re.I):
            groups=defaultdict(set)
            support=[]
            for paper,eid,names in entries:
                if eid in claim['evidence_ids']:
                    groups[paper].update(names)
                    support.append(eid)
            overlaps=set()
            for left in groups:
                for right in groups:
                    if left!=right: overlaps.update(groups[left]&groups[right])
            if not overlaps: continue
            issues.append({'claim_id':claim['claim_id'],'evidence_ids':list(dict.fromkeys(support)),
                'owner':'reporter','severity':'blocking',
                'problem':'报告声称任务/数据集完全不重叠，但登记条件中存在同名项目：'+', '.join(sorted(overlaps))+ '。需要回查原文。',
                'required_fix':'核对这些共同项目，区分任务重叠与模型/指标/协议不匹配；移除不成立的完全不重叠断言。'})
    return issues
