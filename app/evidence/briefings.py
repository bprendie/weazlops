"""Verify bounded, source-signed handheld debriefs; preserve custody distinctions."""
import hashlib,re,struct,time,uuid
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from .trust import roster,capability,public
from .policy import REPORT_RULES,PRIORITY_POLICY
RULES={i+1:r for i,r in enumerate(REPORT_RULES)}
def binary(value,name,size=None,maximum=None):
    s=value.get(name)
    if not isinstance(s,str) or len(s)%2 or len(s)>((maximum or size or 4096)*2) or not re.fullmatch('[0-9a-fA-F]*',s):raise ValueError('Invalid '+name)
    result=bytes.fromhex(s)
    if size is not None and len(result)!=size:raise ValueError('Invalid '+name+' size')
    return result

def verify_report(value,team):
    if type(value.get('schema')) is not int or value.get('schema')!=1:raise ValueError('Unsupported report schema')
    header=binary(value,'header_hex',48);snapshot=binary(value,'snapshot_hex',maximum=200);signature=binary(value,'signature_hex',maximum=72);pub=binary(value,'source_public_key_hex',65);certificate=binary(value,'certificate_hex',384);cap=binary(value,'capability_hex',144)
    current=bytes.fromhex(team['certificate_hex']);root=bytes.fromhex(team['root_public_key_hex']);current_info=roster(current,root,team['roster_epoch']);reported=roster(certificate,root)
    if len(snapshot)<32 or header[:4]!=b'RC01' or any(header[4:6]) or struct.unpack_from('<H',header,6)[0]!=len(snapshot):raise ValueError('Invalid capsule header')
    group,source,reader,epoch,snapshot_id=struct.unpack_from('<QQQQQ',header,8)
    if not source or not reader or source==reader or not epoch or str(group)!=team['group_id'] or epoch>current_info['epoch'] or not epoch<=reported['epoch']<=current_info['epoch']:raise ValueError('Report context or signed epoch mismatch')
    if str(source)!=str(value.get('source_id')) or str(reader)!=str(value.get('reader_id')) or str(reader) not in current_info['members']:raise ValueError('Report source/reader binding mismatch')
    if value.get('directory_hex'):
        from .setup_wire import verify_directory
        directory=binary(value,'directory_hex',711)
        if not 1<=directory[197]<=5:raise ValueError('Invalid signed directory membership')
        members={str(struct.unpack_from('<Q',directory,198+i*88)[0]):directory[206+i*88:271+i*88] for i in range(directory[197])}
        verify_directory(directory,root,members)
        if {m:hashlib.sha256(p).hexdigest() for m,p in members.items()}!=current_info['members'] or members.get(str(source))!=pub:raise ValueError('Directory differs from pinned membership')
        roles={str(struct.unpack_from('<Q',directory,198+i*88)[0]):directory[271+i*88] for i in range(directory[197])}
        if roles.get(str(source))!=2 or roles.get(str(reader))!=1:raise ValueError('Directory product roles invalid')
    else:capability(cap,current,source,pub,2)
    if reported['group_id']!=team['group_id'] or reported['members'].get(str(source))!=hashlib.sha256(pub).hexdigest() or str(reader) not in reported['members']:raise ValueError('Report roster binding mismatch')
    if not 8<=len(signature)<=72:raise ValueError('Invalid DER signature size')
    public(pub).verify(signature,header+snapshot,ec.ECDSA(hashes.SHA256()))
    count=snapshot[1]
    if snapshot[0]!=1 or count>3 or snapshot[3] or len(snapshot)!=32+56*count or not snapshot_id or struct.unpack_from('<Q',snapshot,4)[0]!=snapshot_id:raise ValueError('Invalid bounded snapshot')
    digest=value.get('capsule_sha256')
    if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Invalid full capsule digest')
    digest_quality='RECOMPUTED_CIPHERTEXT_SHA256'
    if 'capsule_hex' not in value:raise ValueError('Full encrypted capsule required for digest validation')
    if 'capsule_hex' in value:
        capsule=binary(value,'capsule_hex',maximum=448)
        if len(capsule)!=230+len(snapshot) or capsule[:48]!=header or hashlib.sha256(capsule).hexdigest()!=digest:raise ValueError('Full capsule digest or header mismatch')
        digest_quality='RECOMPUTED_CIPHERTEXT_SHA256'
    state=value.get('reader_state',{'known':False})
    if not isinstance(state,dict) or type(state.get('known')) is not bool:raise ValueError('Invalid reader-state assertion')
    if state['known']:
        for name,maximum in (('flags',15),('source_uptime_ms',0xffffffff),('recent_loss',65535)):
            if type(state.get(name)) is not int or not 0<=state[name]<=maximum:raise ValueError('Invalid reader-state field')
        pages=state.get('backlog_pages')
        if pages is not None and (type(pages) is not int or not 0<=pages<=65535):raise ValueError('Invalid reader backlog assertion')
        state={'known':True,'flags':state['flags'],'backlog_pages':pages,'source_uptime_ms':state['source_uptime_ms'],'recent_loss':state['recent_loss']}
    else:state={'known':False}
    mask=value.get('reviewed_mask')
    if type(mask) is not int or mask<0 or mask>=(1<<count):raise ValueError('Invalid reader reviewed mask')
    cards=[];events=set()
    for i in range(count):
        raw=snapshot[32+i*56:88+i*56];event,revision,rule=struct.unpack_from('<QIH',raw);priority,flags=raw[14:16]
        if not event or event in events or not revision or not rule or priority>100 or any(raw[46:48]):raise ValueError('Invalid exact card schema')
        events.add(event);segment,sample,first,last,observations=struct.unpack_from('<QIIIH',raw,16)
        summary_only=bool(flags&32)
        if (not segment and not summary_only) or not observations or first>last or raw[41] not in (0,1):raise ValueError('Invalid evidence/time/radio reference')
        if summary_only and (segment or sample or any(raw[48:56])):raise ValueError('Summary-only card has an archive reference')
        low,high,latest=struct.unpack_from('<bbb',raw,38)
        if not -127<=low<=high<=0 or not low<=latest<=high:raise ValueError('Invalid RSSI envelope')
        cards.append({'event_id':str(event),'revision':revision,'rule_code':rule,'rule':RULES.get(rule,f'UNSUPPORTED-RULE-{rule}'),'interpretation_supported':rule in RULES,'evidence_availability':'SUMMARY_ONLY' if summary_only else 'NOT_RECOVERED','priority':priority,'flags':flags,'archive_session_id':str(segment),'archive_session_hex':f'{segment:x}' if segment else None,'evidence_sample':sample,'first_ms':first,'last_ms':last,'observations':observations,'min_rssi':low,'max_rssi':high,'last_rssi':latest,'radio':raw[41],'channel':struct.unpack_from('<H',raw,42)[0],'coverage_flags':struct.unpack_from('<H',raw,44)[0],'evidence_hash8':raw[48:56].hex(),'synthetic':bool(flags&128),'card_sha256':hashlib.sha256(raw).hexdigest(),'card_hex':raw.hex()})
    return {'source_id':str(source),'reader_id':str(reader),'snapshot_id':str(snapshot_id),'snapshot_epoch':epoch,'snapshot_flags':snapshot[2],'cutoff_ms':struct.unpack_from('<I',snapshot,12)[0],'pending':struct.unpack_from('<H',snapshot,16)[0],'pending_quality':'UNKNOWN_AT_CHECKPOINT' if struct.unpack_from('<H',snapshot,16)[0]==65535 else 'SIGNED_SNAPSHOT_COUNT_NOT_LIVE','evicted':struct.unpack_from('<H',snapshot,18)[0],'radio_plan_mask':str(struct.unpack_from('<Q',snapshot,20)[0]),'coverage_gaps':struct.unpack_from('<I',snapshot,28)[0],'cards':cards,'card_count':count,'capsule_sha256':digest,'capsule_digest_quality':digest_quality,'signed_payload_sha256':hashlib.sha256(header+snapshot).hexdigest(),'source_authentication':'VERIFIED_SOURCE_SIGNATURE','signature_scope':'RC01_HEADER48_AND_SNAPSHOT_ONLY','capsule_aead_verification':'READER_CLAIM_NOT_SERVER_VERIFIED','priority_policy':PRIORITY_POLICY,'source_public_fingerprint':hashlib.sha256(pub).hexdigest(),'reader_reviewed_mask':mask,'reader_state':state,'reader_state_authentication':'USB_EXPORT_ASSERTION_NOT_SOURCE_SIGNED','time_quality':'source monotonic milliseconds; no wall time or location inferred','synthetic':bool(snapshot[2]&128) or any(c['synthetic'] for c in cards)}
