import pytest
from app.protocol import *
def slots():return [{'product':'ghost','callsign':'STONEY','lead':True},{'product':'ghost','callsign':'BETTY','profile':'xl'},{'product':'drop','callsign':'gh05t-we4zR'}]
def test_preplanned_before_binding():
 p=new_plan('Tonight',slots());assert len(p['members'])==3
 assert all(m['binding']is None for m in p['members'])
 b=package(p,p['members'][0],'02:00:00:00:00:01','esp32s3','original');assert len(b)==1737
 verify(bytes.fromhex(p['root_public']),signature(b[-73:]),b'WZL ONE VISIT PACKAGE V2\0'+digest(b[:-73]))
 assert bytes.fromhex(p['members'][1]['secret'])not in b
 assert p['root_secret']not in str(public_plan(p))
 verify(bytes.fromhex(p['root_public']),signature(bytes.fromhex(p['roster'])[-73:]),b'WZL TEAM ROSTER V2\0'+bytes.fromhex(p['roster'])[:638])
@pytest.mark.parametrize('change',['six','duplicate','no-lead','drop-lead'])
def test_plan_rejects_bad_roles(change):
 s=slots()
 if change=='six':s=s*2
 if change=='duplicate':s[1]['callsign']='STONEY'
 if change=='no-lead':s[0]['lead']=False
 if change=='drop-lead':s[0]['lead']=False;s[2]['lead']=True
 with pytest.raises(ValueError):new_plan('Tonight',s)
def test_v2_unknown_physical_chip_and_fleet_keys():
 a=new_plan('Tonight',slots());b=new_plan('Tomorrow',slots());assert a['id']!=b['id'];assert a['members'][0]['secret']!=b['members'][0]['secret']
 wire=bytes.fromhex(a['roster'])
 assert wire[:8]==b'WZLTP002'
 for i in range(3):assert wire[198+88*i+74]==0
