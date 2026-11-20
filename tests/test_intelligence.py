import struct,secrets,hashlib,pytest
from app.protocol import *
from app.intelligence import Intelligence
from app.store import Store

def fixture(plan,rule=1,revision=1):
 reader=plan['members'][0];source=plan['members'][1];card=bytearray(56);struct.pack_into('<QIHBBQIIIHbbbBHH',card,0,77,revision,rule,50,32,0,0,100,200,3,-80,-40,-60,0,1,0)
 snapshot=bytearray(88);snapshot[:3]=bytes([1,1,0]);struct.pack_into('<QIHHQI',snapshot,4,99,200,0,0,3,0);snapshot[32:]=card
 header=bytearray(48);header[:4]=b'RC01';group=int.from_bytes(bytes.fromhex(plan['certificate'])[8:16],'little');struct.pack_into('<HQQQQQ',header,6,88,group,int(source['id']),int(reader['id']),1,99)
 sig=sign(load(bytes.fromhex(source['secret'])),bytes(header+snapshot));capsule=bytes(header)+secrets.token_bytes(270)
 return {'schema':1,'source_id':source['id'],'reader_id':reader['id'],'header_hex':header.hex(),'snapshot_hex':snapshot.hex(),'signature_hex':sig.hex(),'source_public_key_hex':source['public'],'certificate_hex':plan['certificate'],'directory_hex':plan['roster'],'capability_hex':bytes(144).hex(),'capsule_sha256':digest(capsule).hex(),'capsule_hex':capsule.hex(),'reviewed_mask':0}
@pytest.fixture
def context(tmp_path):
 key=tmp_path/'key';key.write_bytes(secrets.token_bytes(32));store=Store(tmp_path/'db',key);p=new_plan('Evidence',[{'product':'ghost','callsign':'STONEY','lead':True},{'product':'drop','callsign':'gh05t-we4zR'}]);return store,p,Intelligence(store)
@pytest.mark.parametrize('rule',range(1,19))
def test_all_supported_rules_accept_valid_summary_only(context,rule):
 s,p,i=context;r=i.ingest(p,fixture(p,rule));assert r['card_count']==1;assert r['cards'][0]['interpretation_supported'];assert r['cards'][0]['evidence_availability']=='SUMMARY_ONLY'
def test_review_watch_exact_revision_and_reopening(context):
 s,p,i=context;report=fixture(p,5);i.ingest(p,report);card=s.all('finding')[0];i.review(card['id'],1,'expected','Venue confirmed this exact equipment','operator');i.ingest(p,report);assert len(s.all('finding'))==1;assert s.all('finding')[0]['disposition']=='expected'
 i.ingest(p,fixture(p,5,2));new=s.all('finding')[0];assert new['reopened']and new['disposition']=='unreviewed';assert new['previous_disposition']=='expected'
 with pytest.raises(ValueError):i.review(card['id'],1,'expected','stale','operator')
 report['signature_hex']='00'*70
 with pytest.raises(Exception):i.ingest(p,report)
