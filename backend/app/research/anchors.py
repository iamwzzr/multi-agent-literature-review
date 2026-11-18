"""Deterministic quote anchors. No fuzzy match is ever promoted to verified evidence."""
import re


def locate_quote(text, quote, expected_start=None):
    words=list(re.finditer(r'\S+',text))
    normalized=' '.join(word[0] for word in words)
    quote=' '.join(quote.split())
    if not quote:
        return {'status':'missing','candidates':[]}
    starts=[]
    if expected_start is not None:
        if type(expected_start) is not int or expected_start<0 or normalized[expected_start:expected_start+len(quote)]!=quote:
            return {'status':'mismatch','candidates':[]}
        starts=[expected_start]
    else:
        offset=0
        while len(starts)<101:
            position=normalized.find(quote,offset)
            if position<0: break
            starts.append(position);offset=position+1
    mapping=[]
    for word in words:
        if mapping: mapping.append(word.start()-1)
        mapping.extend(range(word.start(),word.end()))
    candidates=[]
    for start in starts[:100]:
        end=start+len(quote)
        raw_start=mapping[start];raw_end=mapping[end-1]+1
        candidates.append({'start':start,'end':end,'basis':'normalized-page-text-v1',
            'raw_start':raw_start,'raw_end':raw_end,
            'line_start':text.count('\n',0,raw_start)+1,'line_end':text.count('\n',0,raw_end)+1,
            'selector':{'type':'TextQuoteSelector','exact':quote,
                'prefix':normalized[max(0,start-80):start],'suffix':normalized[end:end+80]}})
    return {'status':'matched' if len(starts)==1 else 'ambiguous' if starts else 'missing',
            'candidates':candidates,'truncated':len(starts)>100}
