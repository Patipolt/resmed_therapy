"""Calendar boundaries and statistics, independent of the GUI and renderer."""
from __future__ import annotations
import calendar
from datetime import date, timedelta
import math
import statistics

from .decoder import numeric
from .models import CalendarPeriod, PlotSpec
from .parameters import available_fields, catalogue, display_value


def calendar_periods(start: str, end: str, kind: str):
    current, last = date.fromisoformat(start), date.fromisoformat(end)
    if current > last:
        raise ValueError('Start must not exceed end.')
    if kind not in ('week', 'month'):
        raise ValueError('Period must be week or month.')
    periods = []
    while current <= last:
        boundary = (current + timedelta(days=6-current.weekday()) if kind == 'week' else
                    current.replace(day=calendar.monthrange(current.year,current.month)[1]))
        stop = min(boundary,last)
        periods.append(CalendarPeriod(kind,current,stop))
        current = stop + timedelta(days=1)
    return periods


def build_plot_specs(dataset, config):
    config.validate()
    if config.start < dataset.first_date or config.end > dataset.last_date:
        raise ValueError('The selected range exceeds available data.')
    groups = {group.key:group for group in catalogue(dataset)}
    active = [key for key in config.selected_groups if key in groups and available_fields(groups[key],dataset)]
    if not active:
        raise ValueError('None of the selected parameters is available.')
    periods = []
    if config.weekly:
        periods += calendar_periods(config.start,config.end,'week')
    if config.monthly:
        periods += calendar_periods(config.start,config.end,'month')
    return [PlotSpec(period,key) for period in periods for key in active]


def daily_series(dataset, config, label):
    """Reindex calendar days so missing days remain gaps, not zero measurements."""
    lookup = {row['date']:row for row in dataset.selected(config)}
    current, last = date.fromisoformat(config.start), date.fromisoformat(config.end)
    days, values, total = [], [], 0.0
    while current <= last:
        row = lookup.get(current.isoformat(),{})
        if label == '@cumulative_usage':
            raw = row.get('Duration')
            if numeric(raw):
                total += raw/60
                value = total
            else:
                value = math.nan
        else:
            raw = row.get(label)
            value = display_value(label,raw,dataset) if numeric(raw) else math.nan
        days.append(current);values.append(value)
        current += timedelta(days=1)
    return days, values


def trailing_average(values, window):
    """Trailing N-calendar-day arithmetic mean, available days only.

    No look-ahead; partial windows at the selected start. A missing current day
    stays missing even if earlier observations exist. Does not reset at a week
    or month boundary because it is computed before calendar partitioning.
    """
    result = []
    for index, value in enumerate(values):
        chunk = [v for v in values[max(0,index-window+1):index+1] if math.isfinite(v)]
        result.append(statistics.mean(chunk) if chunk and math.isfinite(value) else math.nan)
    return result


def summary_statistics(dataset, config):
    rows = dataset.selected(config)
    used = [row for row in rows if numeric(row.get('Duration')) and row['Duration'] > 0]
    known = [row for row in rows if numeric(row.get('Duration'))]
    duration = [row['Duration'] for row in used]
    days = (date.fromisoformat(config.end)-date.fromisoformat(config.start)).days+1
    result = dict(calendar_days=days, records=len(rows), absent_days=days-len(rows),
                  used_days=len(used), zero_usage_days=sum(row['Duration']==0 for row in known),
                  missing_duration_days=len(rows)-len(known), total_minutes=sum(duration),
                  goal_days=sum(value>=config.usage_goal_hours*60 for value in duration),
                  median_minutes=statistics.median(duration) if duration else None,
                  mean_minutes=sum(duration)/len(known) if known else None)
    for label,key,factor in [('AHI','ahi_median',1),('TgtIPAP.50','pressure_median',1),
                             ('TgtIPAP.95','pressure_95',1),('Leak.95','leak_95',60)]:
        values=[row[label] for row in used if numeric(row.get(label))]
        result[key]=(statistics.median([display_value(label,value,dataset) for value in values]) if label=='Leak.95'
                     else statistics.median(values)*factor) if values else None
    ahi = [row['AHI'] for row in used if numeric(row.get('AHI'))]
    result['ahi_mean'] = statistics.mean(ahi) if ahi else None
    result['pressure_max'] = max((row['TgtIPAP.Max'] for row in used if numeric(row.get('TgtIPAP.Max'))),default=None)
    return result
