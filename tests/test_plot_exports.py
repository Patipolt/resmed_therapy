"""Visual data contracts: overlaid summary bars and per-period PDF pagination."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from matplotlib.backends.backend_agg import FigureCanvasAgg

from resmed_therapy_interpretation.core.analysis import build_plot_specs
from resmed_therapy_interpretation.core.models import PlotConfiguration,Patient
from resmed_therapy_interpretation.core.plotting import make_figure,PLOT_LOCK
from resmed_therapy_interpretation.core.report import export_report
from resmed_therapy_interpretation.tests.test_core import sample_dataset


class PlotExportTests(unittest.TestCase):
    def test_pressure_bars_preserve_values_and_shade_order(self):
        dataset=sample_dataset()
        config=PlotConfiguration(dataset.first_date,dataset.last_date,selected_groups=('pressure',))
        with PLOT_LOCK:
            figure=make_figure(dataset,config,build_plot_specs(dataset,config)[0])
            FigureCanvasAgg(figure).draw()
            bars=figure.axes[0].containers
            self.assertEqual([bar.get_label() for bar in bars],['Maximum','95th percentile','Median'])
            self.assertEqual([bar.patches[0].get_height() for bar in bars],[9.96,9.84,7.44])
            self.assertTrue(all(patch.get_y()==0 for bar in bars for patch in bar.patches))
            brightness=[sum(bar.patches[0].get_facecolor()[:3]) for bar in bars]
            self.assertGreater(brightness[0],brightness[1]);self.assertGreater(brightness[1],brightness[2])
            figure.clear()

    def test_leak_bars_only_show_recorded_summaries(self):
        dataset=sample_dataset()
        config=PlotConfiguration(dataset.first_date,dataset.last_date,selected_groups=('leak',))
        with PLOT_LOCK:
            figure=make_figure(dataset,config,build_plot_specs(dataset,config)[0])
            bars=figure.axes[0].containers
            self.assertEqual([bar.get_label() for bar in bars],['95th percentile','Raw .70 summary'])
            self.assertAlmostEqual(bars[0].patches[0].get_height(),13.2)
            self.assertAlmostEqual(bars[1].patches[0].get_height(),6)
            figure.clear()

    def test_pdf_calendar_periods_never_share_a_page(self):
        try:from pypdf import PdfReader
        except ImportError:self.skipTest('Install requirements-dev.txt for PDF pagination checks')
        dataset=sample_dataset()
        config=PlotConfiguration(dataset.first_date,dataset.last_date,weekly=True,monthly=True,
                                 selected_groups=('events','leak','pressure','usage','timing'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'periods.pdf';export_report(path,dataset,Patient(),config)
            reader=PdfReader(path)
            headings=[item for item in reader.outline if item.title.startswith('Plots - ')]
            self.assertEqual(len(headings),10) # five periods, two pages each
            pages=[reader.get_destination_page_number(item) for item in headings]
            self.assertEqual(len(pages),len(set(pages)))
            starts=[item for item in headings if '(continued)' not in item.title]
            self.assertEqual(len(starts),5)
            # Every new interval is a true new PDF page with a single interval heading.
            for item in starts:
                text=reader.pages[reader.get_destination_page_number(item)].extract_text()
                self.assertEqual(text.count('Plots - '),1)


if __name__=='__main__':unittest.main()
