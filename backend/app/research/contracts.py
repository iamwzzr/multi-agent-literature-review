from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
import re


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Budget(Contract):
    documents: int = Field(default=20, ge=1, le=40)
    feedback_batches: int = Field(default=2, ge=0, le=3)
    model_calls: int = Field(default=60, ge=1, le=60)
    tool_calls: int = Field(default=150, ge=1, le=150)
    seconds: int = Field(default=600, ge=1, le=600)


class EvidenceDraft(Contract):
    span_id: str
    finding: str = Field(max_length=1600)
    conditions: dict[str, str | None] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list, max_length=10)


class ResearchOutput(Contract):
    status: Literal['success', 'partial', 'failed']
    outcome: Literal['evidence_found','insufficient_evidence','execution_error'] | None = None
    evidence: list[EvidenceDraft] = Field(max_length=12)
    coverage_by_question: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ClaimDraft(Contract):
    text: str = Field(min_length=1, max_length=3000)
    kind: Literal['finding', 'synthesis', 'proposal']
    evidence_ids: list[str] = Field(max_length=12)
    scope: str = Field(max_length=1500)


class ComparisonRow(Contract):
    cells: dict[str, str | None]
    evidence_ids: list[str] = Field(min_length=1)
    conditions: dict[str, str | None] = Field(default_factory=dict)


class ReportOutput(Contract):
    status: Literal['success', 'partial', 'failed']
    claims: list[ClaimDraft] = Field(min_length=1, max_length=30)
    comparison_table: list[ComparisonRow] = Field(default_factory=list, max_length=20)
    evidence_requests: list[str] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    errors: list[str] = Field(default_factory=list)


def report_contract(task):
    """Enforce requested output size before a draft reaches the audit queue."""
    requirements=task.get('output_requirements',{})
    claims=requirements.get('max_claims',30)
    claims=claims if type(claims) is int and 1<=claims<=30 else 30
    question=task.get('question','')
    rows=requirements.get('max_comparison_rows')
    if type(rows) is not int or not 0<=rows<=20:
        numbers={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
        match=re.search(r'([一二三四五六七八九十]|\d+)\s*行',question)
        rows=numbers.get(match[1],int(match[1]) if match and match[1].isdigit() else 1) if match else (
            20 if re.search(r'表格|比较表|comparison table',question,re.I) else 0)
        rows=min(rows,20)
    return create_model('ReportOutput',__base__=ReportOutput,
        claims=(list[ClaimDraft],Field(min_length=1,max_length=claims)),
        comparison_table=(list[ComparisonRow],Field(default_factory=list,max_length=rows)))


class IssueDraft(Contract):
    claim_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    owner: Literal['researcher', 'reporter']
    severity: Literal['blocking', 'warning']
    category: Literal['factual','citation','scope','comparison','style'] = 'factual'
    problem: str
    required_fix: str

    @model_validator(mode='after')
    def factual_issues_block_delivery(self):
        # A pass accompanied by unsupported factual claims is not a safe pass.
        # Only presentation/naming preferences may remain non-blocking warnings.
        if self.category != 'style' and self.severity == 'warning':
            self.severity='blocking'
        return self


class ReviewOutput(Contract):
    status: Literal['success', 'partial', 'failed']
    verdict: Literal['pass', 'revise', 'undetermined']
    checked_claim_ids: list[str]
    issues: list[IssueDraft]
    unchecked_claim_ids: list[str]
    errors: list[str] = Field(default_factory=list)


def delivery_allowed(report, review, evidence, papers):
    if report.get('status', 'success') != 'success':
        return False
    if review['status'] != 'success' or review['verdict'] != 'pass':
        return False
    if review['reviewed_report_version'] != report['report_version'] or review['reviewed_evidence_snapshot_id'] != report['evidence_snapshot_id']:
        return False
    ids = {c['claim_id'] for c in report['claims']}
    if set(review['checked_claim_ids']) != ids or review['unchecked_claim_ids']:
        return False
    if any(i['severity'] == 'blocking' and i['status'] != 'resolved' for i in review['issues']):
        return False
    by_id = {e['evidence_id']: e for e in evidence}
    by_paper = {p['paper_id']: p for p in papers}
    for claim in report['claims']:
        if claim['kind'] != 'proposal' and not claim['evidence_ids']:
            return False
        for identifier in claim['evidence_ids']:
            item = by_id.get(identifier)
            if not item:
                return False
            paper = by_paper.get(item['paper_id'])
            if not paper or (paper['source'] == 'online' and paper['identity_status'] != 'verified'):
                return False
            if item['correspondence'] not in ('matched', 'user_provided'):
                return False
    return True
