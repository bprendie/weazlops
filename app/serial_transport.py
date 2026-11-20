"""Explicit identity-bound USB station operations; no RF commands."""
import re,time
from pathlib import Path
import serial
from serial.tools import list_ports

def normalized(value):return re.sub('[^0-9A-F]','',value.upper())
class USB:
    def __init__(self,port,expected_mac):
        resolved=Path(port).resolve(strict=True)
        matches=[p for p in list_ports.comports() if Path(p.device).resolve()==resolved]
        if len(matches)!=1 or normalized(matches[0].serial_number or '')!=normalized(expected_mac):raise ValueError('USB descriptor identity differs from exact authorized MAC')
        self.mac=expected_mac.upper();self.port=str(resolved)
        self.device=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2,exclusive=True)
        self.device.dtr=True;self.device.rts=False;self.device.port=self.port;self.device.open();self.device.reset_input_buffer();self.pending=bytearray()
    def close(self):self.device.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def exchange(self,command,prefix=None,timeout=20,multiline=False,required_prefixes=(),terminal_prefix=None):
        if len(command)>1024 or '\n' in command or '\r' in command:raise ValueError('Invalid command')
        max_response=9000 if command in ('planned export','planned assignments') else 8192 if command.startswith('recon export ') else 4096
        self.device.write((command+'\n').encode());deadline=time.monotonic()+timeout;keepalive=time.monotonic()+.1;lines=[];quiet=None;received_bytes=0;received_lines=0;max_pending=0
        while time.monotonic()<deadline:
            # read(n) waits for all n bytes or timeout. A192-byte binary chunk is
            # a<512-byte hex reply, so always asking512 added100ms per command.
            # Drain only buffered bytes; otherwise wait for the first byte. The
            # existing bounded line buffer and CR keepalive still own framing.
            received=self.device.read(max(1,min(512,self.device.in_waiting)))
            if received:quiet=time.monotonic()+1.2;received_bytes+=len(received)
            self.pending.extend(received);max_pending=max(max_pending,len(self.pending))
            if len(self.pending)>max_response:raise ValueError('USB response exceeds bound')
            while b'\n' in self.pending:
                received_lines+=1
                raw,_,remaining=self.pending.partition(b'\n');self.pending=bytearray(remaining);line=raw.decode('utf-8','strict').strip()
                if getattr(self,'observer',None):self.observer(line)
                if line.startswith('ERR'):raise ValueError(line)
                if line and (prefix is None or line.startswith(prefix)):
                    lines.append(line);quiet=time.monotonic()+1.2
                    if not multiline:return line
                    if len(lines)>8:raise ValueError('Too many USB response lines')
                    if terminal_prefix and line==terminal_prefix:return lines
            if lines and multiline and not self.pending:
                if required_prefixes and all(any(line.startswith(wanted) for line in lines) for wanted in required_prefixes):return lines
                if not required_prefixes and time.monotonic()>quiet:return lines
            if time.monotonic()>keepalive:self.device.write(b'\r');keepalive=time.monotonic()+.1
        category=' '.join(command.split()[:2])
        raise TimeoutError(f'USB reply deadline ({category}; bytes={received_bytes}; lines={received_lines}; matched={len(lines)}; maximum_pending={max_pending}; expected_prefix={prefix!r}); disconnect before retrying')
    def stage(self,kind,data,prefix='recon'):
        for i in range(0,len(data),32):self.exchange(f'{prefix} {kind} {i//32} {data[i:i+32].hex()}','RECON ' if prefix=='recon' else 'PROVISION ')
    def identity(self):
        if getattr(self,'identity_namespace','recon')=='buddy':
            lines=self.exchange('buddy identity','BUDDY ',multiline=True,terminal_prefix='BUDDY IDENTITY_END')
            public=[l for l in lines if l.startswith('BUDDY PUBLIC ')]
            if len(public)!=1:raise ValueError('Missing or ambiguous public identity')
            _,_,member,key=public[0].split();parts={}
            for line in lines:
                if line.startswith('BUDDY CERT '):
                    _,_,index,data=line.split();index=int(index)
                    if index in parts and parts[index]!=data:raise ValueError('Conflicting certificate parts')
                    parts[index]=data
            if parts and (set(parts)!={0,1} or any(len(v)!=384 for v in parts.values())):raise ValueError('Incomplete certificate')
            return {'member_id':member,'public_key':bytes.fromhex(key),'certificate':bytes.fromhex(parts[0]+parts[1]) if parts else None}
        lines=self.exchange('recon identity','RECON ',multiline=True,terminal_prefix='RECON IDENTITY_END');public=next((l for l in lines if l.startswith('RECON PUBLIC ')),None)
        if not public:raise ValueError('Missing public identity')
        _,_,member,key=public.split();cert=next((l[11:] for l in lines if l.startswith('RECON CERT ')),None)
        return {'member_id':member,'public_key':bytes.fromhex(key),'certificate':bytes.fromhex(cert) if cert else None}
    def attest(self,challenge):
        namespace=getattr(self,'identity_namespace','recon')
        response=self.exchange(namespace+' attest '+challenge,namespace.upper()+' PROOF ');parts=response.split()
        if len(parts)!=4:raise ValueError('Invalid identity attestation')
        return parts[2],parts[3]
