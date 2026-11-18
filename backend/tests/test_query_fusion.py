from app.library import SearchIndex


def chunks():
    return [{'id':name,'paper':{'id':doc,'title':'Neutral'},'paper_id':doc,'document_id':doc,
        'page':page,'text':text} for name,doc,page,text in [
            ('a','d1',1,'alpha mechanism definition'),('b','d1',2,'alpha further method'),
            ('c','d2',1,'beta mechanism definition'),('d','d2',1,'beta overlapping passage')]]


def test_fusion_reserves_coverage_for_distinct_subquestions():
    result=SearchIndex(chunks()).search_many(['alpha','beta'],2)
    assert {c['document_id'] for c in result}=={'d1','d2'}


def test_fusion_respects_document_scope_and_deduplicates_page():
    result=SearchIndex(chunks()).search_many(['alpha','beta','beta'],6,document_ids=['d2'])
    assert len(result)==1 and result[0]['document_id']=='d2'


def test_fusion_empty_or_zero_limit_is_empty():
    index=SearchIndex(chunks())
    assert not index.search_many(['alpha'],0)
    assert not index.search_many([' ',''])
