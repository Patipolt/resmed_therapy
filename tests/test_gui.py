"""Headless Qt integration tests; exercise the actual widgets and worker signals."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('MPLCONFIGDIR','/tmp/resmed-mpl-test')
from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest

from PySide6.QtCore import QDate,QEvent,QCoreApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from resmed_therapy_interpretation.core.analysis import build_plot_specs
from resmed_therapy_interpretation.pages.main_ui import MainUI
from resmed_therapy_interpretation.styles import stylesheet
from resmed_therapy_interpretation.core.models import Patient,PlotConfiguration
from resmed_therapy_interpretation.tests.test_core import sample_dataset


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.app.setStyle('Fusion');cls.app.setStyleSheet(stylesheet())

    def setUp(self):
        self.window=MainUI();self.window.show();self.errors=[]
        self.window.logic.error_requested.disconnect(self.window.show_error)
        self.window.logic.error_requested.connect(self.errors.append)
        self.window.plot_widget.render_error.disconnect(self.window.show_error)
        self.window.plot_widget.render_error.connect(self.errors.append)
        dataset=sample_dataset();self.window.logic.dataset=dataset;self.window.set_dataset(dataset)
        QTest.qWait(350)

    def tearDown(self):
        self.wait_for_idle()
        self.window.close();self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def wait_for_idle(self,timeout=15):
        # processEvents + Python sleep releases the GIL for Python QThread work.
        # Tight QTest.qWait loops in recent PySide can starve a pure-Python worker.
        stop=time.monotonic()+timeout
        while self.window.logic.busy and time.monotonic()<stop:
            self.app.processEvents();time.sleep(.01)
        self.app.processEvents()
        self.assertFalse(self.window.logic.busy,'Background task did not finish')

    def test_group_children_toggle_together(self):
        widget=self.window.parameters_widget
        self.assertTrue(widget.field_checks[('leak','Leak.95')].isChecked())
        widget.field_checks[('leak','Leak.70')].setChecked(False)
        self.assertFalse(widget.field_checks[('leak','Leak.95')].isChecked())
        self.assertFalse(widget.group_checks['leak'].isChecked())
        widget.field_checks[('leak','Leak.95')].setChecked(True)
        self.assertTrue(widget.field_checks[('leak','Leak.70')].isChecked())
        self.assertFalse(widget.field_checks[('events','AI')].isEnabled())
        self.assertFalse(widget.field_checks[('events','AI')].isChecked())

    def test_dates_and_modes_update_graphs(self):
        config=self.window.configuration_widget
        config.start_edit.setDate(QDate(2026,7,30));config.end_edit.setDate(QDate(2026,8,4))
        config.week_check.setChecked(True);config.month_check.setChecked(False)
        QTest.qWait(400)
        specs=[card.spec for card in self.window.plot_widget.cards]
        self.assertEqual(len(specs),10)
        self.assertEqual(str(specs[0].period.start),'2026-07-30')
        self.assertEqual(str(specs[0].period.end),'2026-08-02')
        self.assertEqual(str(specs[-1].period.end),'2026-08-04')

    def test_no_modes_is_empty_not_an_exception(self):
        self.window.configuration_widget.month_check.setChecked(False)
        QTest.qWait(300)
        self.assertEqual(len(self.window.plot_widget.cards),0)
        self.assertFalse(self.window.configuration_widget.export_button.isEnabled())
        self.assertIn('Select By week',self.window.status_label.text())

    def test_optional_birth_date_and_disabled_average(self):
        widget=self.window.configuration_widget
        self.assertIsNone(widget.patient().date_of_birth)
        widget.birth_known.setChecked(True)
        self.assertIsNone(widget.patient().date_of_birth)
        widget.birth_edit.setDate(QDate(1989,10,3))
        self.assertEqual(widget.patient().date_of_birth,'1989-10-03')
        widget.average_edit.clear()
        config=widget.configuration(self.window.parameters_widget.selected_groups())
        self.assertFalse(config.averaging)
        widget.average_check.setChecked(True)
        with self.assertRaises(ValueError):widget.configuration(self.window.parameters_widget.selected_groups())

    def test_rendering_is_lazy_and_bounded(self):
        self.window.plot_widget.render_visible()
        self.assertLessEqual(len(self.window.plot_widget.cache),10)
        self.assertGreater(len(self.window.plot_widget.cache),0)
        self.assertEqual(self.errors,[])

    def test_new_folder_clears_stale_dataset(self):
        self.window.import_widget.set_folder('/new/card/path')
        self.assertIsNone(self.window.logic.dataset)
        self.assertFalse(self.window.import_widget.export_button.isEnabled())
        self.assertEqual(self.window.plot_widget.cards,[])

    def test_background_pdf_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'therapy.pdf'
            dataset=self.window.logic.dataset
            config=PlotConfiguration(dataset.first_date,dataset.first_date,selected_groups=('events','leak'),averaging=True)
            self.window.logic.export_pdf(str(path),Patient('Test','Patient','1989-10-03'),config)
            self.wait_for_idle()
            self.assertTrue(path.read_bytes().startswith(b'%PDF'))
            self.assertEqual(self.errors,[])
            self.assertTrue(self.window.open_export_button.isVisible())
            try:from pypdf import PdfReader
            except ImportError:return
            text='\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
            self.assertIn('Test Patient',text);self.assertIn('1989-10-03',text)
            self.assertNotIn('ResScan',text);self.assertNotIn('representative',text)

    @unittest.skipUnless(os.environ.get('CPAP_GUI_TEST_ROOT'),'Set CPAP_GUI_TEST_ROOT for background import/export')
    def test_background_analyze_json_export_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.window.import_widget.set_folder(os.environ['CPAP_GUI_TEST_ROOT'])
            self.window.logic.analyze(os.environ['CPAP_GUI_TEST_ROOT'])
            self.assertTrue(self.window.logic.busy)
            self.wait_for_idle()
            self.assertEqual(len(self.window.logic.dataset.records),489)
            QTest.qWait(300)
            path=Path(tmp)/'complete.json'
            config=self.window.configuration_widget.configuration(self.window.parameters_widget.selected_groups())
            self.window.logic.export_json(str(path),self.window.configuration_widget.patient(),config)
            self.wait_for_idle()
            self.assertTrue(path.exists())
            self.window.logic.open_json(str(path))
            self.wait_for_idle()
            self.assertFalse(self.window.logic.busy);self.assertEqual(self.errors,[])
            self.assertEqual(len(self.window.logic.dataset.records),489)
            self.assertFalse(self.window.import_widget.analyze_button.isEnabled())


if __name__=='__main__':unittest.main()
