"""Plain Python state objects shared by the UI, analysis and exports."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass(frozen=True)
class Patient:
    name: str = ''
    surname: str = ''
    date_of_birth: str | None = None
    patient_id: str = ''
    clinician: str = ''
    notes: str = ''

    @property
    def full_name(self):
        return ' '.join(part.strip() for part in (self.name, self.surname) if part.strip())

    def age_on(self, day: date):
        if not self.date_of_birth:
            return None
        born = date.fromisoformat(self.date_of_birth)
        if born > day:
            raise ValueError('Date of birth cannot be in the future.')
        return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


@dataclass(frozen=True)
class PlotConfiguration:
    start: str
    end: str
    weekly: bool = False
    monthly: bool = True
    averaging: bool = False
    average_days: int = 7
    selected_groups: tuple[str, ...] = ()
    usage_goal_hours: float = 4.0
    ahi_reference: float = 5.0
    leak_reference_lpm: float = 24.0
    appendix: str = 'Selected parameters'

    def validate(self):
        start, end = date.fromisoformat(self.start), date.fromisoformat(self.end)
        if start > end:
            raise ValueError('Start date must be on or before end date.')
        if not self.weekly and not self.monthly:
            raise ValueError('Select By week, By month, or both.')
        if not self.selected_groups:
            raise ValueError('Select at least one available parameter group.')
        if not 1 <= self.average_days <= 365:
            raise ValueError('The averaging window must be 1-365 calendar days.')
        if not 0 < self.usage_goal_hours <= 24:
            raise ValueError('Usage goal must be greater than zero and at most 24 hours.')


@dataclass
class TherapyDataset:
    summary_edf: dict
    card: dict
    origin: str
    saved_patient: dict = field(default_factory=dict)
    saved_configuration: dict = field(default_factory=dict)

    @property
    def records(self):
        return self.summary_edf['records']

    @property
    def first_date(self):
        return self.records[0]['date']

    @property
    def last_date(self):
        return self.records[-1]['date']

    @property
    def labels(self):
        return {signal['label'] for signal in self.summary_edf['signals']}

    @property
    def identity(self):
        return self.card.get('identity', {})

    @property
    def warnings(self):
        return self.summary_edf.get('warnings', []) + self.card.get('warnings', [])

    def selected(self, configuration):
        return [row for row in self.records if configuration.start <= row['date'] <= configuration.end]


@dataclass(frozen=True)
class CalendarPeriod:
    kind: str
    start: date
    end: date

    @property
    def label(self):
        if self.kind == 'week':
            year, week, _ = self.start.isocalendar()
            return f'Week {week:02d}, {year} | {self.start:%d %b} - {self.end:%d %b %Y}'
        return f'{self.start:%B %Y} | {self.start:%d %b} - {self.end:%d %b}'


@dataclass(frozen=True)
class PlotSpec:
    period: CalendarPeriod
    group_key: str


def configuration_dict(configuration):
    result = asdict(configuration)
    result['selected_groups'] = list(configuration.selected_groups)
    return result
