"""Translate audited internal IDs to the existing UI's numeric citation protocol."""
import re

from ..errors import AppError


EVIDENCE_ID = re.compile(r'\bevidence-[A-Za-z0-9_-]+\b')
NUMERIC_CITATION = re.compile(r'\[\[\d+\]\]')
BRACKETED = re.compile(r'\[\[?([^\[\]\n]+)\]\]?')


def validate_citations(text, declared_ids, registered_ids):
    """Inline citations may only refer to the claim's declared evidence."""
    mentioned = set(EVIDENCE_ID.findall(text))
    if mentioned - set(registered_ids) or mentioned - set(declared_ids):
        raise AppError('UNKNOWN_EVIDENCE', '正文引用了未登记或未关联到本条主张的证据，已拒绝交付。', 422)
    if NUMERIC_CITATION.search(text):
        raise AppError('INVALID_CITATION_FORMAT', '模型不得自行分配展示引用编号，请使用证据 ID。', 422)


def display_citations(text, references):
    """Only transform citation notation; never rewrite a reviewed conclusion."""
    def number(identifier):
        if identifier not in references:
            raise AppError('UNKNOWN_EVIDENCE', '交付文本包含无法定位的证据引用。', 422)
        return f'[[{references[identifier]}]]'

    def brackets(match):
        content = match[1]
        identifiers = EVIDENCE_ID.findall(content)
        remainder = EVIDENCE_ID.sub('', content)
        # Handle [id], [[id]], [id1, id2] without changing normal prose brackets.
        if identifiers and not remainder.strip(' ,;，；、`\t'):
            return ''.join(number(item) for item in dict.fromkeys(identifiers))
        return match[0]

    text = BRACKETED.sub(brackets, text)
    text = re.sub(r'`(evidence-[A-Za-z0-9_-]+)`', lambda m: number(m[1]), text)
    return EVIDENCE_ID.sub(lambda m: number(m[0]), text)


def cited_paragraph(text, evidence_ids, references):
    text = display_citations(text, references)
    used = {int(match) for match in re.findall(r'\[\[(\d+)\]\]', text)}
    suffix = []
    for identifier in dict.fromkeys(evidence_ids):
        index = references[identifier]
        if index not in used:
            suffix.append(f'[[{index}]]')
            used.add(index)
    return text + ''.join(suffix)
