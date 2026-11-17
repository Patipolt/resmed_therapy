"""Parameter catalogue. Edit this file to add or regroup related EDF fields.

Unavailable fields remain visible but disabled. Unknown scalar labels are added
automatically as technical groups; unknown arrays are preserved in JSON/appendix.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterGroup:
    key: str
    title: str
    fields: tuple[str, ...]
    unit: str = ''
    default: bool = False
    kind: str = 'measurement'
    note: str = ''


GROUPS = (
    ParameterGroup('events', 'AHI & apnea indices', ('AHI','AI','HI','OAI','CAI','UAI'), 'events/hour', True,
                   note='Only recorded indices are plotted. Combined AHI cannot be split into apnea types.'),
    ParameterGroup('leak', 'Leak', ('Leak.95','Leak.70','Leak.50','Leak.Max'), 'L/min', True,
                   note='Daily leak summaries. Leak.95 is the 95th percentile; Leak.70 is an original field label whose exact definition is unverified. Missing maximum/median are not inferred.'),
    ParameterGroup('pressure', 'Therapy pressure', ('TgtIPAP.50','TgtIPAP.95','TgtIPAP.Max'), 'cmH2O', True,
                   note='Target inspiratory pressure: daily median, 95th and maximum where recorded.'),
    ParameterGroup('usage', 'Total daily usage', ('Duration','OnDuration'), 'hours', True,
                   note='Therapy duration and separate device-on duration. These do not measure time asleep.'),
    ParameterGroup('timing', 'Usage timing / mask on-off', ('MaskOn','MaskOff'), 'machine clock', True, 'timing',
                   'Minute-resolution mask fragments within each noon-to-noon machine day; not awakenings.'),
    ParameterGroup('cumulative', 'Cumulative therapy usage', ('@cumulative_usage',), 'hours', False, 'cumulative',
                   'Running sum from the selected start date. Unknown days leave the sum unchanged and are marked as gaps.'),
    ParameterGroup('epap', 'Target expiratory pressure', ('TgtEPAP.50','TgtEPAP.95','TgtEPAP.Max'), 'cmH2O'),
    ParameterGroup('mask_pressure', 'Mask pressure', ('MaskPress.50','MaskPress.95','MaskPress.Max'), 'cmH2O'),
    ParameterGroup('blower_pressure', 'Blower pressure', ('BlowPress.95','BlowPress.5'), 'cmH2O', note='Suffix .5 is retained without an independently verified percentile meaning.'),
    ParameterGroup('flow', 'Flow summaries', ('Flow.95','Flow.5'), 'L/min', note='Daily scalar summaries, not recorded breath waveforms. Suffix .5 semantics are unverified.'),
    ParameterGroup('blower_flow', 'Blower flow summary', ('BlowFlow.50',), 'L/min'),
    ParameterGroup('humidity', 'Ambient humidity summary', ('AmbHumidity.50',), 'mg/L'),
    ParameterGroup('temperature', 'Humidifier temperature summary', ('HumTemp.50',), 'deg C', note='Device-related temperature, not patient body temperature.'),
    ParameterGroup('power', 'Humidifier power summary', ('HumPow.50',), 'original units'),
    ParameterGroup('mask_events', 'Mask transition count', ('MaskEvents',), 'count', kind='technical', note='Mask transitions are not respiratory events or a count of awakenings.'),
    ParameterGroup('patient_hours', 'Patient-hours counter', ('PatientHours',), 'hours', kind='technical'),
    ParameterGroup('pressure_settings', 'Recorded pressure settings', ('S.AS.StartPress','S.AS.MinPress','S.AS.MaxPress','S.C.StartPress','S.C.Press'), 'cmH2O', kind='setting', note='Recorded daily settings. Fixed-CPAP settings may be inactive in APAP mode.'),
    ParameterGroup('epr', 'Expiratory pressure relief', ('S.EPR.ClinEnable','S.EPR.EPREnable','S.EPR.Level','S.EPR.EPRType'), 'codes / level', kind='setting'),
    ParameterGroup('ramp', 'Ramp settings', ('S.RampEnable','S.RampTime'), 'codes / minutes', kind='setting'),
    ParameterGroup('humidifier', 'Humidifier settings', ('S.HumEnable','S.HumLevel','Humidifier'), 'codes / level', kind='setting'),
    ParameterGroup('mode', 'Therapy mode', ('Mode',), 'code', kind='setting'),
    ParameterGroup('mask_tube', 'Mask, tube and filter settings', ('S.Mask','S.Tube','S.ABFilter','S.PtAccess'), 'code', kind='setting'),
    ParameterGroup('faults', 'Daily fault words', ('Fault.Device','Fault.Alarm','Fault.Humidifier','Fault.HeatedTube'), 'code', kind='technical'),
    ParameterGroup('checksum', 'Daily checksum word', ('Crc16',), 'signed word', kind='technical', note='Opaque checksum word; not a physiological measurement. Its CRC16 algorithm is not validated.'),
    ParameterGroup('date_counter', 'Machine-day counter', ('Date',), 'days since epoch', kind='technical'),
)

FRIENDLY = {
    'AHI':'AHI', 'AI':'Apnea index', 'HI':'Hypopnea index', 'OAI':'Obstructive apnea index',
    'CAI':'Central apnea index', 'UAI':'Unclassified apnea index',
    'Duration':'Therapy duration', 'OnDuration':'Device-on duration',
    'MaskOn':'Mask-on times', 'MaskOff':'Mask-off times',
    'Leak.95':'95th percentile', 'Leak.70':'Raw .70 summary', 'Leak.50':'Median', 'Leak.Max':'Maximum',
    'TgtIPAP.50':'Median', 'TgtIPAP.95':'95th percentile', 'TgtIPAP.Max':'Maximum',
    '@cumulative_usage':'Running therapy total',
}


def field_title(label):
    return FRIENDLY.get(label, label)


def catalogue(dataset):
    result = list(GROUPS)
    known = {field for group in result for field in group.fields}
    for signal in dataset.summary_edf['signals']:
        label = signal['label']
        if label not in known and label != 'Date':
            result.append(ParameterGroup('extra:'+label, label, (label,), signal['unit'] or 'original units',
                                         kind='technical', note='Original EDF field; clinical meaning is not independently validated.'))
    return tuple(result)


def available_fields(group, dataset):
    if group.kind == 'cumulative':
        return group.fields if 'Duration' in dataset.labels else ()
    return tuple(field for field in group.fields if field in dataset.labels)


def display_value(label, value, dataset):
    if value is None:
        return None
    units = {signal['label']:signal['unit'] for signal in dataset.summary_edf['signals']}
    if label in ('Duration', 'OnDuration'):
        return value / 60
    if (label.startswith('Leak.') or label.startswith('Flow.')) and units.get(label) == 'L/s':
        return value * 60
    return value
