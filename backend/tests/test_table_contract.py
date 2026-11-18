import pytest
from pydantic import ValidationError
from app.research.contracts import report_contract


def draft():
    return {'status':'success','claims':[{'text':'Fact','kind':'finding','evidence_ids':['e'],'scope':'Scope'}]}


@pytest.mark.parametrize('question',['给一个对照表','生成对比表','给出比较矩阵','Provide a comparison table'])
def test_requested_table_synonyms_are_allowed_and_required(question):
    schema=report_contract({'question':question,'output_requirements':{}})
    with pytest.raises(ValidationError):schema.model_validate(draft())
    data=draft();data['comparison_table']=[{'cells':{'method':'A'},'evidence_ids':['e']}]
    assert schema.model_validate(data).comparison_table


@pytest.mark.parametrize('question',['不要生成比较表','无需表格','no comparison table'])
def test_explicit_no_table_is_respected(question):
    schema=report_contract({'question':question,'output_requirements':{}})
    assert not schema.model_validate(draft()).comparison_table
    data=draft();data['comparison_table']=[{'cells':{'method':'A'},'evidence_ids':['e']}]
    with pytest.raises(ValidationError):schema.model_validate(data)


def test_structured_zero_row_override_is_preserved():
    schema=report_contract({'question':'给一个对照表','output_requirements':{'max_comparison_rows':0}})
    assert not schema.model_validate(draft()).comparison_table
