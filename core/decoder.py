"""Low-level read-only EDF/card decoder. No GUI or PDF dependencies.

Digital samples, original headers, unit scaling and opaque card logs are retained.
This module is standalone; it does not import the earlier CLI tool.
"""
from __future__ import annotations
import base64
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import math
from pathlib import Path
import re
import struct
import zlib

DESCRIPTIONS = {}  # Friendly display definitions live in parameters.py.

class DataError(ValueError):
    pass


def rounded(value, places=1):
    if value is None:
        return 'missing'
    return str(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def hours_minutes(value):
    if value is None:
        return 'missing'
    value = int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return f'{value // 60}:{value % 60:02d}'


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def edf_date(date, time):
    day, month, year = map(int, date.split('.'))
    year += 1900 if year >= 85 else 2000
    hour, minute, second = map(int, time.split('.'))
    return dt.datetime(year, month, day, hour, minute, second)


def header_text(value):
    # ResMed's temperature unit uses UTF-8 degrees despite EDF's ASCII convention.
    try:return value.decode('utf-8').strip()
    except UnicodeDecodeError:return value.decode('latin-1').strip()


def parse_edf(path, include_samples=True, data=None):
    """Strict structural reader for 16-bit EDF; retains original bytes as raw ints.

    ResMed declares some nonnegative counters with dmax > 32767. Those channels
    use unsigned words; 65535 is then out of range, rather than a valid -1.
    All unknown labels are preserved. EDF+/BDF time-series interpretation is
    deliberately not implemented by this daily STR reporter.
    """
    path = Path(path)
    b = path.read_bytes() if data is None else data
    try:
        if len(b) < 256 or b[:8].strip() != b'0':
            raise DataError('Expected 16-bit EDF version 0')
        n = int(b[252:256]); header_bytes = int(b[184:192])
        count = int(b[236:244]); seconds = float(b[244:252])
        if not 1 <= n <= 4096 or header_bytes != 256 * (n + 1) or len(b) < header_bytes:
            raise DataError('Invalid or truncated EDF signal header')
        if not math.isfinite(seconds) or seconds <= 0:
            raise DataError('Invalid EDF record duration')
        fields = {}; p = 256
        for key, width in [('label',16),('transducer',80),('unit',8),('physical_min',8),('physical_max',8),('digital_min',8),('digital_max',8),('prefilter',80),('samples_per_record',8),('reserved',32)]:
            fields[key] = [header_text(b[p+i*width:p+(i+1)*width]) for i in range(n)]
            p += width * n
        if len(set(fields['label'])) != n:
            raise DataError('Duplicate EDF labels would make field lookup ambiguous')
        signals = []
        for i in range(n):
            sig = {key: fields[key][i] for key in fields}
            for key in ['physical_min','physical_max','digital_min','digital_max']:
                sig[key] = float(sig[key])
                if not math.isfinite(sig[key]):
                    raise DataError('Non-finite EDF scaling')
            sig['samples_per_record'] = int(sig['samples_per_record'])
            if sig['samples_per_record'] < 1 or sig['digital_max'] <= sig['digital_min']:
                raise DataError('Invalid EDF sample count or digital range')
            sig['unsigned'] = sig['digital_min'] >= 0 and sig['digital_max'] > 32767
            if sig['digital_min'] < -32768 or sig['digital_max'] > (65535 if sig['unsigned'] else 32767):
                raise DataError('Unsupported EDF integer range')
            sig['scale'] = (sig['physical_max']-sig['physical_min'])/(sig['digital_max']-sig['digital_min'])
            if sig['scale'] == 0:
                raise DataError('Invalid EDF physical range')
            sig['meaning_level'], sig['description'] = DESCRIPTIONS.get(sig['label'], ('unknown','Unknown field; scaled using its EDF header without clinical interpretation.'))
            signals.append(sig)
        record_bytes = 2 * sum(s['samples_per_record'] for s in signals)
        actual, remainder = divmod(len(b)-header_bytes, record_bytes)
        if remainder or count < -1 or (count >= 0 and count != actual):
            raise DataError(f'EDF size mismatch: header says {count} records; found {actual} plus {remainder} trailing bytes')
        warnings = ['Record count inferred from file size (-1 in header).'] if count == -1 else []
        count = actual
        header = dict(path=str(path.resolve()), sha256=hashlib.sha256(b).hexdigest(),
            size_bytes=len(b),header_bytes=header_bytes,record_bytes=record_bytes,records=count,
            record_duration_seconds=seconds,start=edf_date(b[168:176].decode(),b[176:184].decode()).isoformat(),
            patient_identification=b[8:88].decode('latin-1').strip(),recording_identification=b[88:168].decode('latin-1').strip(),
            reserved=b[192:236].decode('latin-1').strip())
        if include_samples:header['raw_header_base64']=base64.b64encode(b[:header_bytes]).decode()
        result = {'header':header,'signals':signals,'warnings':warnings,'records':[],'raw_records':[]}
        if not include_samples:
            return result
        for record in range(count):
            values = {}; raw = {}
            for sig in signals:
                width = sig['samples_per_record']; label=sig['label']
                words = list(struct.unpack_from('<'+('H' if sig['unsigned'] else 'h')*width,b,p))
                p += width*2
                scaled = [None if x < sig['digital_min'] or x > sig['digital_max'] else
                    round(sig['physical_min']+(x-sig['digital_min'])*sig['scale'],12) for x in words]
                raw[label] = words
                values[label] = scaled[0] if width == 1 else scaled
            result['records'].append(values); result['raw_records'].append(raw)
        return result
    except (ValueError, OverflowError, struct.error) as exc:
        raise DataError(f'{path.name}: {exc}') from exc


def load_summary(root):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise DataError(f'Input folder does not exist: {root}')
    candidates=[p for p in root.iterdir() if p.is_file() and p.name.lower()=='str.edf']
    if len(candidates)!=1:
        raise DataError('Select the card root containing exactly one STR.edf file')
    doc=parse_edf(candidates[0]); header=doc['header']
    if header['record_duration_seconds'] != 86400 or header['reserved'].startswith('EDF+'):
        raise DataError('This reporter supports continuous daily STR EDF records only')
    if not doc['records'] or 'Duration' not in doc['records'][0]:
        raise DataError('STR has no daily Duration field or no records')
    start=dt.datetime.fromisoformat(header['start']); seen=set()
    for i,row in enumerate(doc['records']):
        derived=start+dt.timedelta(days=i); date=derived.date()
        if numeric(row.get('Date')):
            if int(row['Date'])!=row['Date']:
                raise DataError('Non-integer Date field')
            encoded=dt.date(1970,1,1)+dt.timedelta(days=int(row['Date']))
            if encoded!=date:
                doc['warnings'].append(f'Date channel disagrees with EDF header on record {i}; Date channel retained.')
                date=encoded
        if date in seen:
            raise DataError(f'Duplicate machine day: {date}')
        seen.add(date);row['date']=date.isoformat()
        row['day_start']=dt.datetime.combine(date,start.time()).isoformat()
        row['source_record_index']=i
    doc['records'].sort(key=lambda r:r['date'])
    doc['root']=str(root)
    return doc


def card_inventory(root, include_bytes=True):
    """Only card namespaces are scanned: generated reports/source code excluded."""
    root=Path(root); paths=[]
    for p in root.iterdir():
        if p.is_file() and (p.name.lower().startswith(('str.','identification.')) or p.name.lower()=='journal.dat'):
            paths.append(p)
        elif p.is_dir() and p.name.upper() in ('SETTINGS','DATALOG'):
            paths.extend(q for q in p.rglob('*') if q.is_file())
    inventory=[]; text_files={}; opaque={}; warnings=[]
    for p in sorted(paths):
        rel=p.relative_to(root).as_posix();b=p.read_bytes()
        item=dict(path=rel,size_bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
        suffix=p.suffix.lower()
        if suffix=='.tgt':
            text=b.decode('latin-1');pairs=re.findall(r'^#(\S+)\s+([^\r\n]*)',text,re.M)
            text_files[rel]={'text':text,'codes':[{'key':k,'value':v} for k,v in pairs], 'interpretation':'Raw device codes; hex-like numbers not assigned unverified meanings.'}
        if suffix=='.crc':
            target=p.with_suffix('.tgt')
            if target.exists() and len(b)==4:
                expected=int.from_bytes(b,'little'); actual=zlib.crc32(target.read_bytes())
                item['crc32_check']={'target':target.relative_to(root).as_posix(),'stored':expected,'computed':actual,'matches':expected==actual}
                if expected!=actual:warnings.append(f'CRC32 mismatch: {rel}')
        if suffix in ('.edf','.gz') and p.parent.name.upper()!='SETTINGS' and p.name.lower()!='str.edf':
            try:item['edf_header']=parse_edf(p,False)['header'];item['signals']=parse_edf(p,False)['signals']
            except DataError as exc:item['inspection_error']=str(exc)
            warnings.append(f'Additional data file detected: {rel}. Detailed waveform/event interpretation is not implemented; do not assume a complete summary-only report for this card.')
        if suffix in ('.dat','.log','.crc') and include_bytes:
            opaque[rel]={'base64':base64.b64encode(b).decode(),'meaning':'Opaque bytes retained; proprietary log/checksum not clinically decoded.'}
        inventory.append(item)
    identity={}
    for name,entry in text_files.items():
        if name.lower()=='identification.tgt':identity={x['key']:x['value'] for x in entry['codes']}
    return dict(files=inventory,text_files=text_files,opaque_files=opaque,identity=identity,warnings=warnings)


def timing_fragments(row, clock_shift=0):
    """Never stitch slots across days or allocate daily AHI to fragments."""
    on=row.get('MaskOn',[]);off=row.get('MaskOff',[])
    if not isinstance(on,list):on=[on]
    if not isinstance(off,list):off=[off]
    result=[];start=dt.datetime.fromisoformat(row['day_start'])+dt.timedelta(minutes=clock_shift)
    for index in range(max(len(on),len(off))):
        a=on[index] if index<len(on) else None;b=off[index] if index<len(off) else None
        if a is None and b is None:continue
        valid=numeric(a) and numeric(b) and 0<=a<=b<=1440
        result.append(dict(slot=index+1,on_offset_minutes=a,off_offset_minutes=b,
            start_machine_time=(start+dt.timedelta(minutes=a)).isoformat() if numeric(a) else None,
            end_machine_time=(start+dt.timedelta(minutes=b)).isoformat() if numeric(b) else None,
            span_minutes=b-a if valid else None,
            status=('day-boundary fragment' if valid and (a==0 or b>=1439) else 'paired fragment') if valid else 'incomplete or reversed slot'))
    return result


def settings_changes(rows):
    keys=[k for k in rows[0] if k.startswith('S.') or k in ('Mode','Humidifier')]
    previous={};result=[];last_date=None
    for row in rows:
        current={k:row[k] for k in keys if numeric(row.get(k))}
        if not current:continue
        changes={k:{'before':previous.get(k),'after':v} for k,v in current.items() if k not in previous or v!=previous[k]}
        if changes:result.append({'first_observed_date':row['date'],'previous_observation':last_date,'changes':changes})
        previous.update(current);last_date=row['date']
    return result


def display(value):
    if value is None:return '-'
    if isinstance(value,list):return ', '.join(display(x) for x in value)
    if isinstance(value,float):return f'{value:.3f}'.rstrip('0').rstrip('.')
    return str(value)
