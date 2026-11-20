import pytest
from app.handout import validate_names,validate_phrases,publication,uses_handout
from app.protocol import new_plan,PHRASES

def test_legacy_and_custom_plans():
    slots=[dict(product='ghost',callsign='BETTY',lead=True),dict(product='drop',callsign='gh05t-BLOCK')]
    assert not uses_handout(new_plan('Standard',slots))
    slots[0]['callsign']='RAVEN'
    plan=new_plan('Custom',slots)
    a,b=(publication(plan,plan['members'][0]) for _ in range(2))
    assert uses_handout(plan) and a['manifest']==b['manifest'] and a['envelope']!=b['envelope']
    assert bytes.fromhex(a['peers'])==bytes(32)
    assert b'RAVEN' not in bytes.fromhex(a['envelope'])
    assert len(bytes.fromhex(plan['roster']))==711

@pytest.mark.parametrize('names',[['RAVEN','raven'],['12345678901234567'],[''],['bad name'],['a\n']])
def test_invalid_names(names):
    with pytest.raises(ValueError):validate_names(names)

@pytest.mark.parametrize('text',['a'*85,' ','', 'x\ny'])
def test_invalid_phrase(text):
    with pytest.raises(ValueError):validate_phrases([text,*PHRASES[1:]])
