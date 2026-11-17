"""Calendar/statistical/export tests independent of a running GUI."""
from dataclasses import replace
from datetime import date,timedelta
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from resmed_therapy_interpretation.core.analysis import calendar_periods,trailing_average,build_plot_specs,daily_series,summary_statistics
from resmed_therapy_interpretation.core.models import TherapyDataset,PlotConfiguration,Patient
from resmed_therapy_interpretation.core.parameters import catalogue,available_fields,display_value
from resmed_therapy_interpretation.core.service import analyze_folder,open_snapshot,export_snapshot,validate_output_path


def sample_dataset():
    labels=['Date','Duration','OnDuration','AHI','Leak.95','Leak.70','TgtIPAP.50','TgtIPAP.95','TgtIPAP.Max','MaskOn','MaskOff']
    units=['','min.','min.','','L/s','L/s','cmH2O','cmH2O','cmH2O','min.','min.']
    signals=[{'label':label,'unit':unit,'samples_per_record':3 if label in ('MaskOn','MaskOff') else 1} for label,unit in zip(labels,units)]
    rows=[]
    for i in range(13):
        day=date(2026,7,29)+timedelta(days=i)
        rows.append(dict(zip(labels,[(day-date(1970,1,1)).days,600,601,.2+i/10,.22,.1,7.44,9.84,9.96,[0,600,None],[100,1000,None]]),
                         date=day.isoformat(),day_start=day.isoformat()+'T12:00:00'))
    return TherapyDataset({'records':rows,'signals':signals,'header':{'start':'2026-07-29T12:00:00','path':'/fake/STR.edf','sha256':'fixture'},'root':'/fake','warnings':[]},
                          {'identity':{'PNA':'AirStart_10_APAP','SRN':'example'},'files':[],'warnings':[]},'/fake')


class CalendarTests(unittest.TestCase):
    def test_calendar_weeks_clip_at_both_selected_edges(self):
        parts=calendar_periods('2026-07-29','2026-08-10','week')
        self.assertEqual([(str(p.start),str(p.end)) for p in parts],
                         [('2026-07-29','2026-08-02'),('2026-08-03','2026-08-09'),('2026-08-10','2026-08-10')])
    def test_months_leap_year_and_partial_edges(self):
        parts=calendar_periods('2024-02-28','2024-03-02','month')
        self.assertEqual([(str(p.start),str(p.end)) for p in parts],[('2024-02-28','2024-02-29'),('2024-03-01','2024-03-02')])
    def test_iso_year_week_label(self):
        parts=calendar_periods('2026-12-31','2027-01-04','week')
        self.assertIn('Week 53, 2026',parts[0].label)
        self.assertIn('Week 01, 2027',parts[1].label)
    def test_both_modes_generate_both_sets(self):
        dataset=sample_dataset();config=PlotConfiguration(dataset.first_date,dataset.last_date,True,True,selected_groups=('events','leak'))
        specs=build_plot_specs(dataset,config)
        self.assertEqual(len(specs),10) # 3 weeks + 2 months, two groups each
    def test_empty_selection_and_no_modes_are_explicit(self):
        dataset=sample_dataset()
        with self.assertRaises(ValueError):build_plot_specs(dataset,PlotConfiguration(dataset.first_date,dataset.last_date,False,False,selected_groups=('events',)))
        with self.assertRaises(ValueError):build_plot_specs(dataset,PlotConfiguration(dataset.first_date,dataset.last_date))
    def test_moving_average_no_lookahead_and_missing_gap(self):
        result=trailing_average([1,3,math.nan,7,9],3)
        self.assertEqual(result[:2],[1,2]);self.assertTrue(math.isnan(result[2]))
        self.assertEqual(result[3:], [5,8])
    def test_average_does_not_reset_on_monday(self):
        dataset=sample_dataset();config=PlotConfiguration(dataset.first_date,dataset.last_date,selected_groups=('events',))
        days,values=daily_series(dataset,config,'AHI');average=trailing_average(values,7)
        monday=days.index(date(2026,8,3))
        self.assertAlmostEqual(average[monday],sum(values[:monday+1])/(monday+1))
    def test_missing_days_are_gaps_not_zero(self):
        dataset=sample_dataset();dataset.records.pop(2)
        config=PlotConfiguration(dataset.first_date,dataset.last_date,selected_groups=('events',))
        days,values=daily_series(dataset,config,'AHI')
        self.assertEqual(len(days),13);self.assertTrue(math.isnan(values[2]))
        self.assertEqual(summary_statistics(dataset,config)['absent_days'],1)
    def test_leak_units_and_summary_match_conventions(self):
        dataset=sample_dataset();config=PlotConfiguration(dataset.first_date,dataset.last_date,selected_groups=('leak',))
        result=summary_statistics(dataset,config)
        self.assertAlmostEqual(display_value('Leak.95',.22,dataset),13.2)
        self.assertAlmostEqual(result['leak_95'],13.2)
        self.assertAlmostEqual(result['pressure_median'],7.44)
    def test_unavailable_ai_is_never_fabricated(self):
        dataset=sample_dataset();group=next(g for g in catalogue(dataset) if g.key=='events')
        self.assertEqual(available_fields(group,dataset),('AHI',))
    def test_age_handles_birthday_and_future_date(self):
        patient=Patient('Example','Patient','1989-10-03')
        self.assertEqual(patient.age_on(date(2026,10,2)),36)
        self.assertEqual(patient.age_on(date(2026,10,3)),37)
        with self.assertRaises(ValueError):Patient(date_of_birth='2030-01-01').age_on(date(2026,1,1))
    def test_source_output_protection(self):
        dataset=sample_dataset()
        with self.assertRaises(ValueError):validate_output_path(dataset,'/fake/STR.edf','.pdf')


@unittest.skipUnless(os.environ.get('CPAP_GUI_TEST_ROOT'),'Set CPAP_GUI_TEST_ROOT for real-card integration')
class RealCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.dataset=analyze_folder(os.environ['CPAP_GUI_TEST_ROOT'])
    def test_known_statistics(self):
        config=PlotConfiguration('2026-07-26','2026-09-30',selected_groups=('events',))
        result=summary_statistics(self.dataset,config)
        self.assertEqual(result['total_minutes'],35002)
        self.assertEqual(result['goal_days'],65)
        self.assertEqual(result['ahi_median'],.8)
        self.assertEqual(result['pressure_95'],9.84)
        self.assertAlmostEqual(result['leak_95'],13.2)
    def test_complete_json_roundtrip_without_source_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'snapshot.json'
            export_snapshot(path,self.dataset,Patient('Test','Patient'),PlotConfiguration('2026-07-26','2026-09-30',selected_groups=('events',)))
            loaded=open_snapshot(path)
            self.assertEqual(loaded.summary_edf['raw_records'],self.dataset.summary_edf['raw_records'])
            self.assertEqual(len(loaded.records),489)
            self.assertEqual(loaded.saved_patient['surname'],'Patient')
            self.assertIn('Journal.dat',loaded.card['opaque_files'])
            with self.assertRaises(ValueError):export_snapshot(path,loaded)
    def test_json_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'snapshot.json';export_snapshot(path,self.dataset)
            payload=json.loads(path.read_text());payload['summary_edf']['records'][0]['AHI']=999
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):open_snapshot(path)
    def test_json_units_and_identity_cannot_silently_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'snapshot.json';export_snapshot(path,self.dataset)
            original=path.read_text();payload=json.loads(original)
            next(signal for signal in payload['summary_edf']['signals'] if signal['label']=='Leak.95')['unit']='L/min'
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):open_snapshot(path)
            payload=json.loads(original);payload['card']['identity']['SRN']='different-device'
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):open_snapshot(path)
    def test_crc_checks_and_maximum_fields(self):
        self.assertEqual(len(self.dataset.labels),51)
        self.assertTrue(all(item['crc32_check']['matches'] for item in self.dataset.card['files'] if 'crc32_check' in item))


if __name__=='__main__':unittest.main()
