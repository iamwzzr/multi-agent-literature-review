from app.library import SearchIndex, tokens
from app.research.anchors import locate_quote


def index(text):
    return SearchIndex([{'id':'s','paper':{'id':'p','title':'Neutral'},'paper_id':'p','document_id':'d','page':1,'text':text}])


def test_dehyphenation_improves_recall_without_rewriting_source():
    text='The encoder is multi-\nlingual and searches documents.'
    hits=index(text).search('multilingual')
    assert hits and hits[0]['text']==text
    assert locate_quote(text,'multi- lingual')['status']=='matched'
    assert locate_quote(text,'multilingual')['status']=='missing'


def test_unicode_ligature_is_searchable_but_source_stays_original():
    text='The method improves efﬁciency.'
    assert index(text).search('efficiency')[0]['text']==text


def test_chinese_domain_paraphrase_can_find_english_original():
    assert index('The system conditionally acquires documents.').search('需不需要查资料')


def test_hyphen_alias_retains_component_words_and_does_not_invent_a_hit():
    values=tokens('retrieval- augmented')
    assert {'retrieval','augmented','retrievalaugmented'}<=set(values)
    assert not index('The encoder uses attention.').search('multilingual')
