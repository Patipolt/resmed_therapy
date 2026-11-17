"""Import/export services. Source data is read-only; output writes are atomic."""
from __future__ import annotations
import base64
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile

from .analysis import summary_statistics
from .decoder import DataError, card_inventory, load_summary, parse_edf, settings_changes, timing_fragments
from .models import Patient, PlotConfiguration, TherapyDataset, configuration_dict
from .parameters import catalogue,field_title

SCHEMA = 'resmed-therapy-interpretation/1'


def analyze_folder(path):
    summary = load_summary(path)
    card = card_inventory(summary['root'], include_bytes=True)
    serial = re.search(r'SRN=(\d+)',summary['header']['recording_identification'])
    identity_serial = card['identity'].get('SRN')
    if serial and identity_serial and serial.group(1)!=identity_serial:
        raise DataError('STR.edf and Identification.tgt belong to different machines.')
    dataset=TherapyDataset(summary,card,str(Path(path).resolve()))
    signals={signal['label']:signal for signal in summary['signals']}
    for group in catalogue(dataset):
        for label in group.fields:
            if label in signals:
                signals[label]['meaning_level']=group.kind
                signals[label]['description']=group.title+': '+field_title(label)+('. '+group.note if group.note else '')
    return dataset


def validate_snapshot(summary):
    """Verify saved samples/hash and scaling without needing the original folder."""
    try:
        records = summary['records'];signals = summary['signals'];raw = summary['raw_records']
        if not records or len(records)!=len(raw):
            raise DataError('The snapshot contains no records or incomplete raw samples.')
        dates=[row['date'] for row in records]
        if dates!=sorted(set(dates)):
            raise DataError('Snapshot dates are duplicated or out of order.')
        header = summary['header']
        encoded = header.get('raw_header_base64')
        if encoded:
            data = bytearray(base64.b64decode(encoded,validate=True))
            for row in raw:
                for signal in signals:
                    words=row[signal['label']]
                    if len(words)!=signal['samples_per_record']:
                        raise DataError('Snapshot raw sample count mismatch.')
                    data.extend(struct.pack('<'+('H' if signal['unsigned'] else 'h')*len(words),*words))
            if hashlib.sha256(data).hexdigest()!=header['sha256']:
                raise DataError('Snapshot raw values do not match the original source hash.')
            parsed=parse_edf(Path(header.get('path','STR.edf')),data=bytes(data))
            for stored_signal,decoded_signal in zip(signals,parsed['signals']):
                for key in ('label','unit','physical_min','physical_max','digital_min','digital_max','samples_per_record','unsigned','scale'):
                    if stored_signal.get(key)!=decoded_signal[key]:
                        raise DataError(f'Snapshot EDF signal metadata differs from its original header: {key}.')
            for key in ('start','records','record_duration_seconds','header_bytes','record_bytes','recording_identification','patient_identification'):
                if header.get(key)!=parsed['header'][key]:
                    raise DataError(f'Snapshot EDF metadata differs from its original header: {key}.')
            for stored,decoded in zip(records,parsed['records']):
                for label,value in decoded.items():
                    if stored.get(label)!=value:
                        raise DataError(f'Snapshot scaled value differs from raw samples: {label}.')
        else:
            warning='Snapshot has no original EDF header bytes; bit-level integrity cannot be verified.'
            if warning not in summary.setdefault('warnings',[]):summary['warnings'].append(warning)
        # Validate dates/timing metadata even when the source header is retained.
        from datetime import date, datetime as DateTime, timedelta
        source_start=DateTime.fromisoformat(header['start'])
        for row in records:
            day=date.fromisoformat(row['date'])
            if row.get('Date') is not None and row['Date']!=(day-date(1970,1,1)).days:
                raise DataError('Snapshot machine-day label does not match its Date field.')
            expected=DateTime.combine(day,source_start.time()).isoformat()
            if row.get('day_start')!=expected:
                raise DataError('Snapshot day boundary differs from its EDF header.')
    except (KeyError,TypeError,ValueError,struct.error) as exc:
        if isinstance(exc,DataError):raise
        raise DataError(f'Invalid JSON snapshot: {exc}') from exc


def open_snapshot(path):
    source=Path(path).expanduser().resolve()
    try:
        payload=json.loads(source.read_text())
        if not isinstance(payload,dict) or 'summary_edf' not in payload or 'card' not in payload:
            raise DataError('Select a complete JSON export from this application or the standalone tool.')
        schema=payload.get('schema')
        if schema is not None and schema!=SCHEMA:
            raise DataError(f'Unsupported snapshot schema: {schema}')
        validate_snapshot(payload['summary_edf'])
        serial=re.search(r'SRN=(\d+)',payload['summary_edf']['header'].get('recording_identification',''))
        identity_serial=payload['card'].get('identity',{}).get('SRN')
        if serial and identity_serial and serial.group(1)!=identity_serial:
            raise DataError('Snapshot contains inconsistent device serial numbers.')
        return TherapyDataset(payload['summary_edf'],payload['card'],str(source),
                              payload.get('patient',{}),payload.get('configuration',{}))
    except json.JSONDecodeError as exc:
        raise DataError('The selected file is not valid JSON.') from exc


def validate_output_path(dataset, path, suffix):
    target=Path(path).expanduser().resolve()
    if target.suffix.lower()!=suffix:
        raise DataError(f'Choose a {suffix} output filename.')
    protected={str(Path(dataset.origin).resolve()),str(Path(dataset.summary_edf['header']['path']).resolve())}
    root=Path(dataset.summary_edf.get('root',''))
    protected.update(str((root/item['path']).resolve()) for item in dataset.card['files'])
    if str(target) in protected:
        raise DataError('Choose a new output file; source data cannot be overwritten.')
    target.parent.mkdir(parents=True,exist_ok=True)
    return target


def snapshot_payload(dataset, patient=None, configuration=None):
    patient=patient or Patient()
    payload=dict(schema=SCHEMA,application_version='1.0.0',
                 exported_at=datetime.now().astimezone().isoformat(),
                 summary_edf=dataset.summary_edf,card=dataset.card,
                 patient=asdict(patient),
                 configuration=configuration_dict(configuration) if configuration else {},
                 timing_fragments={row['date']:timing_fragments(row) for row in dataset.records},
                 settings_changes=settings_changes(dataset.records),
                 limitations=['No breath waveforms are available in this AirStart summary.',
                              'Opaque binary log bytes are preserved without clinical interpretation.',
                              'Machine timezone and clock correctness are unverified.'])
    if configuration:
        payload['selected_statistics']=summary_statistics(dataset,configuration)
    return payload


def export_snapshot(path, dataset, patient=None, configuration=None):
    target=validate_output_path(dataset,path,'.json')
    payload=snapshot_payload(dataset,patient,configuration)
    descriptor,temp=tempfile.mkstemp(prefix='.resmed-',suffix='.json',dir=target.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(payload,stream,indent=2,ensure_ascii=True,allow_nan=False)
            stream.write('\n')
        os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return str(target)
