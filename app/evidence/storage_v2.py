"""Bounded GDS2 authenticated reader; offline owner keys only. Never RF actions."""
import hashlib, struct, json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding,ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
HEADER=436
MAX_CHUNK=4096

def read_chunks(stream,private_key):
    header=stream.read(HEADER)
    if len(header)!=HEADER or header[:4]not in (b'GDS2',b'GDS3'): raise ValueError('Unsupported sealed header')
    public=private_key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(public).digest()!=header[20:52]:raise ValueError('Wrong recipient')
    if header[:4]==b'GDS2':
        key=private_key.decrypt(header[52:],padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=header[:52]))
    else:
        if not isinstance(private_key,ec.EllipticCurvePrivateKey)or not isinstance(private_key.curve,ec.SECP256R1)or any(header[209:]):raise ValueError('Invalid GDS3 recovery envelope')
        ephemeral=ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),header[52:117])
        shared=private_key.exchange(ec.ECDH(),ephemeral)
        wrap=HKDF(algorithm=hashes.SHA256(),length=32,salt=header[117:149],info=b'GDS3 WRAP V1\0'+header[:117]).derive(shared)
        key=AESGCM(wrap).decrypt(header[149:161],header[161:209],header[:161])
    if len(key)!=32:raise ValueError('Bad key envelope')
    consumed=HEADER
    aes=AESGCM(key);ordinal=0;previous=bytes(16);digest=hashlib.sha256(header).digest()
    while True:
        prefix=stream.read(24)
        if not prefix:return
        if len(prefix)!=24:raise ValueError('Incomplete chunk prefix')
        length,index=struct.unpack_from('<II',prefix)
        if not 0<length<=MAX_CHUNK or index!=ordinal or prefix[8:]!=previous:raise ValueError('Invalid chunk chain')
        consumed+=length+40
        if consumed>0x660000:raise ValueError('Segment exceeds partition bound')
        body=stream.read(length+16)
        if len(body)!=length+16:raise ValueError('Incomplete chunk')
        plain=aes.decrypt(header[4:8]+struct.pack('<Q',ordinal),body,digest+prefix)
        yield plain
        previous=body[-16:];ordinal+=1

def read_records(stream,private_key):
    legacy_variance=False
    synthetic_samples={}
    for chunk in read_chunks(stream,private_key):
        at=0
        while at<len(chunk):
            if at+2>len(chunk):raise ValueError('Truncated record length')
            n=struct.unpack_from('<H',chunk,at)[0];at+=2
            if not 0<n<=1024 or at+n>len(chunk):raise ValueError('Invalid record size')
            b=chunk[at:at+n];at+=n
            if b[0]==0:
                row=json.loads(b[1:])
                if not isinstance(row,dict):raise ValueError('Invalid JSON record')
                if row.get('type')=='config':legacy_variance=row.get('firmware')=='ghost-drop-0.2.0-dev'
                if row.get('type')=='synthetic_fixture':
                    samples=row.get('samples');fixture=row.get('fixture')
                    if not isinstance(samples,list) or len(samples)>3 or not all(isinstance(v,int) and 0<=v<=0xffffffff for v in samples) or not isinstance(fixture,str) or len(fixture)>64:raise ValueError('Invalid synthetic marker')
                    synthetic_samples.update((v,fixture) for v in samples)
                if row.get('type')=='signature' and row.get('sample') in synthetic_samples:row.update(synthetic=True,fixture=synthetic_samples[row['sample']])
                yield row
            elif b[0]==1 and len(b)==33:
                first,span,count=struct.unpack_from('<QII',b,10);last=first+span
                identity=('W-' if b[1]==1 else f'B{b[2]}-')+b[4:10].hex().upper()
                yield dict(type='encounter_delta',id=identity,radio=b[1],address_type=b[2],channel=b[3],first_ms=first,last_ms=last,count=count,rssi=struct.unpack_from('b',b,26)[0],min_rssi=struct.unpack_from('b',b,27)[0],max_rssi=struct.unpack_from('b',b,28)[0],mean_rssi=struct.unpack_from('<h',b,29)[0],**({'variance_upper_bound_db2':struct.unpack_from('<H',b,31)[0],'variance_quality':'legacy_rounding_upper_bound'} if legacy_variance else {'variance_rssi':struct.unpack_from('<H',b,31)[0],'variance_quality':'population_floor_db2'}))
            elif b[0]==2 and len(b)>=46:
                sample=struct.unpack_from('<I',b,4)[0];ms=struct.unpack_from('<Q',b,32)[0]
                wire,n=struct.unpack_from('<HH',b,42)
                if b[1]>2 or n>512 or len(b)!=46+n or wire<n:raise ValueError('Invalid evidence')
                for offset in range(0,n,96):
                    yield dict(type='evidence',v=1,sample=sample,id=b[8:32].split(b'\0',1)[0].decode('ascii'),radio=b[2],address_type=b[3],source=('ble_ad','wifi_mgmt_no_fcs','wifi_data_header')[b[1]],ms=ms,rssi=struct.unpack_from('b',b,40)[0],channel=b[41],wire_len=wire,captured_len=n,truncated=n<wire,offset=offset,hex=b[46+offset:46+min(n,offset+96)].hex(),**(dict(synthetic=True,fixture=synthetic_samples[sample]) if sample in synthetic_samples else {}))
            elif b[0]==3 and len(b) in (45,61):
                names=('drops','evidence_samples','evidence_duplicates','evidence_limited','evidence_write_failures','management_dropped','management_rejected','data_dropped','priority_limited','aggregate_evictions','queue_high_water','scan_cycles')
                yield dict(type='coverage',ms=struct.unpack_from('<Q',b,1)[0],paused=bool(b[9]),ble=bool(b[10]),channels=struct.unpack_from('<H',b,11)[0],**dict(zip(names,struct.unpack_from('<'+str((len(b)-13)//4)+'I',b,13))))
            elif b[0]==4 and len(b)==20:
                if b[1]!=1 or b[2] not in (1,2):raise ValueError('Unsupported radio plan')
                channels=tuple(range(1,12))+(tuple((36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144,149,153,157,161,165)) if b[2]==2 else ())
                stamp,mask=struct.unpack_from('<QQ',b,4)
                if b[3]!=len(channels) or mask>>len(channels):raise ValueError('Invalid radio coverage')
                yield dict(type='radio_plan_coverage',v=1,ms=stamp,radio_plan='US_PASSIVE_'+('DUAL36_V1' if b[2]==2 else '2G11_V1'),channel_mask=mask,covered_channels=[ch for i,ch in enumerate(channels) if mask&(1<<i)])
            else:raise ValueError('Unsupported record')
