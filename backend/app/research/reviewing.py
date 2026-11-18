"""Strict per-batch review boundaries; invalid reviews never imply delivery approval."""
import re
from typing import Literal
from pydantic import create_model, model_validator
from .contracts import ReviewOutput


def review_contract(payload):
    ids = tuple(c['claim_id'] for c in payload['report']['claims'])
    evidence = {e['evidence_id'] for e in payload['evidence']}
    requests = {q['request_id'] for q in payload.get('requested_evidence', [])}
    def validate_batch(self):
        checked, unchecked = set(self.checked_claim_ids), set(self.unchecked_claim_ids)
        if checked & unchecked or checked | unchecked != set(ids) or len(checked)!=len(self.checked_claim_ids) or len(unchecked)!=len(self.unchecked_claim_ids):
            raise ValueError('Audit ONLY this batch. checked and unchecked must be disjoint and together cover exactly batch_claim_ids.')
        for issue in self.issues:
            if issue.claim_id not in ids or set(issue.evidence_ids) - evidence:
                raise ValueError('Issue targets or evidence must belong to this batch; outline entries are not audit targets.')
            if issue.category == 'style' and issue.severity == 'blocking':
                raise ValueError('Style-only advice is warning; if the issue is material, identify it under its factual/citation/scope/comparison category.')
            if issue.severity == 'blocking' and re.search(r'事实(?:均)?无误|无实质错误|事实均有原文支持|可选精修', issue.problem):
                raise ValueError('Issue admits factual support/optional refinement but is blocking. Re-evaluate: classify optional style as style/warning; a real error must identify the specific unsupported proposition. Do not downgrade real factual errors.')
        if any(a.request_id not in requests for a in self.request_assessments):
            raise ValueError('Assess only supplied request IDs.')
        if self.verdict == 'pass' and (unchecked or self.errors or self.status != 'success' or any(i.severity == 'blocking' for i in self.issues)):
            raise ValueError('pass requires successful complete review with no blocking issues; style suggestions alone do not require revise.')
        return self
    return create_model('ReviewOutput', __base__=ReviewOutput,
        checked_claim_ids=(list[Literal[ids]], ...),
        unchecked_claim_ids=(list[Literal[ids]], ...),
        __validators__={'validate_batch':model_validator(mode='after')(validate_batch)})


def incomplete_batch(payload, reason):
    return ReviewOutput(status='partial', verdict='undetermined', checked_claim_ids=[],
        unchecked_claim_ids=[c['claim_id'] for c in payload['report']['claims']],
        issues=[], errors=[reason], question_covered=False)


def merge_reviews(results):
    issues=[i for result in results for i in result.issues]
    unchecked=list(dict.fromkeys(c for r in results for c in r.unchecked_claim_ids))
    return ReviewOutput(status='failed' if any(r.status=='failed' for r in results) else
        'partial' if any(r.status=='partial' for r in results) else 'success',
        verdict='revise' if any(i.severity=='blocking' for i in issues) else
        'undetermined' if unchecked or any(r.verdict=='undetermined' for r in results) else
        'revise' if any(r.verdict=='revise' for r in results) else 'pass',
        checked_claim_ids=list(dict.fromkeys(c for r in results for c in r.checked_claim_ids)),
        unchecked_claim_ids=unchecked, issues=issues,
        errors=list(dict.fromkeys(e for r in results for e in r.errors)),
        question_covered=all(r.question_covered for r in results),
        request_assessments=[a for r in results for a in r.request_assessments])
