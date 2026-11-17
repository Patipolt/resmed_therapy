"""Single-window GUI: compose widgets and connect them to the Logic coordinator."""
from pathlib import Path

from PySide6.QtCore import QTimer,Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGroupBox,QSplitter,
                              QScrollArea,QLabel,QProgressBar,QFileDialog,QMessageBox,QPushButton)

from ..core.analysis import build_plot_specs,summary_statistics
from ..core.decoder import hours_minutes,rounded
from ..logic.logic import Logic
from ..widgets.import_widget import ImportWidget
from ..widgets.configuration_widget import ConfigurationWidget
from ..widgets.parameters_widget import ParametersWidget
from ..widgets.plot_widget import PlotWidget


class MainUI(QMainWindow):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('ResMed Therapy Interpretation')
        self.resize(1480,980);self.setMinimumSize(1100,720)
        self.logic=Logic(self);self._closing=False;self._updating_dataset=False
        self._current_config=None;self._last_export=None
        self.setup_ui();self.connect_signals()

    def setup_ui(self):
        central=QWidget();central.setObjectName('centralWidget');main=QVBoxLayout(central)
        main.setContentsMargins(12,10,12,8);main.setSpacing(8)
        title=QHBoxLayout();brand=QLabel('ResMed Therapy Interpretation');brand.setObjectName('appTitle')
        title.addWidget(brand);title.addStretch();self.coverage_label=QLabel('Local analysis | Source files are read-only');self.coverage_label.setObjectName('muted')
        title.addWidget(self.coverage_label);main.addLayout(title)
        self.import_widget=ImportWidget();main.addWidget(self.import_widget)
        self.analysis_box=QGroupBox('Analyzing data');analysis=QVBoxLayout(self.analysis_box);analysis.setContentsMargins(9,10,9,8)
        self.data_label=QLabel('No data loaded. Select the SD-card root folder, then Analyze.');self.data_label.setWordWrap(True);self.data_label.setObjectName('dataSummary')
        analysis.addWidget(self.data_label)
        self.splitter=QSplitter(Qt.Orientation.Horizontal)
        sidebar=QWidget();side_layout=QVBoxLayout(sidebar);side_layout.setContentsMargins(0,0,0,0);side_layout.setSpacing(7)
        self.configuration_widget=ConfigurationWidget();self.parameters_widget=ParametersWidget()
        self.configuration_widget.setMinimumHeight(380)
        side_layout.addWidget(self.configuration_widget,3);side_layout.addWidget(self.parameters_widget,2)
        sidebar.setMinimumWidth(350)
        self.plot_widget=PlotWidget();self.splitter.addWidget(sidebar);self.splitter.addWidget(self.plot_widget)
        self.splitter.setSizes([375,1050]);self.splitter.setStretchFactor(0,0);self.splitter.setStretchFactor(1,1)
        analysis.addWidget(self.splitter,1);main.addWidget(self.analysis_box,1)
        bottom=QHBoxLayout();self.status_label=QLabel('Ready');bottom.addWidget(self.status_label,1)
        self.open_export_button=QPushButton('Open last export');self.open_export_button.hide();bottom.addWidget(self.open_export_button)
        self.progress_bar=QProgressBar();self.progress_bar.setMaximumWidth(240);self.progress_bar.hide();bottom.addWidget(self.progress_bar)
        main.addLayout(bottom);self.setCentralWidget(central)
        self.update_timer=QTimer(self);self.update_timer.setSingleShot(True);self.update_timer.setInterval(220)

    def connect_signals(self):
        self.import_widget.folder_selected.connect(self._folder_selected)
        self.import_widget.analyze_requested.connect(self.logic.analyze)
        self.import_widget.open_json_requested.connect(self.logic.open_json)
        self.import_widget.export_requested.connect(self.export_json)
        self.configuration_widget.configuration_changed.connect(self.request_update)
        self.parameters_widget.selection_changed.connect(self.request_update)
        self.configuration_widget.export_requested.connect(self.export_pdf)
        self.logic.dataset_updated.connect(self.set_dataset)
        self.logic.busy_changed.connect(self.set_busy)
        self.logic.progress_updated.connect(self.show_progress)
        self.logic.status_message.connect(self.status_label.setText)
        self.logic.error_requested.connect(self.show_error)
        self.logic.export_finished.connect(self.export_finished)
        self.plot_widget.render_error.connect(self.show_error)
        self.update_timer.timeout.connect(self.refresh_plots)
        self.open_export_button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_export)) if self._last_export else None)

    def _folder_selected(self,path):
        self.logic.clear_dataset()
        self.status_label.setText('Folder selected. Click Analyze to decode it.')

    def set_dataset(self,dataset):
        self._updating_dataset=True
        self.configuration_widget.set_dataset(dataset)
        self.parameters_widget.set_dataset(dataset)
        self.import_widget.set_data_available(dataset is not None)
        self._updating_dataset=False
        if dataset is None:
            self._current_config=None;self.data_label.setText('No data loaded. Click Analyze to decode the selected folder.')
            self.plot_widget.show_message('Import a raw data folder, then click Analyze.')
            self.coverage_label.setText('Local analysis | Source files are read-only');return
        self.coverage_label.setText(f'{dataset.first_date} to {dataset.last_date} | {len(dataset.records)} recorded days')
        if Path(dataset.origin).is_file():self.import_widget.path_edit.setText(dataset.origin)
        missing=sum(row.get('Duration') is None for row in dataset.records)
        identity=dataset.identity
        detailed=any(item['path'].upper().startswith('DATALOG/') and item['path'].lower().endswith(('.edf','.gz')) for item in dataset.card['files'])
        capability=('Additional detailed files detected; their clinical waveforms are outside this decoder.' if detailed
                    else 'Daily summaries + mask timing; breath waveforms are not present in this copy.')
        if 'AI' not in dataset.labels:capability+=' Separate AI is not recorded.'
        self.data_label.setText(f"{identity.get('PNA','Unknown device').replace('_',' ')} | S/N {identity.get('SRN','unknown')} | "
                               f"{len(dataset.summary_edf['signals'])} fields | {missing} missing-duration days. "
                               + capability
                               + (f' Source notices: {len(dataset.warnings)} (included in PDF/JSON).' if dataset.warnings else ''))
        self.data_label.setToolTip('\n'.join(dataset.warnings) or 'Source dates and timestamps are machine time; timezone is unverified.')
        self.request_update()

    def request_update(self,*args):
        if not self._updating_dataset and self.logic.dataset is not None:self.update_timer.start()

    def refresh_plots(self):
        if self.logic.busy:return
        dataset=self.logic.dataset
        if dataset is None:return
        try:
            config=self.configuration_widget.configuration(self.parameters_widget.selected_groups())
            specs=build_plot_specs(dataset,config)
        except ValueError as error:
            self._current_config=None;self.plot_widget.show_message(str(error))
            self.configuration_widget.export_button.setEnabled(False)
            self.status_label.setText(str(error));return
        self._current_config=config
        self.configuration_widget.export_button.setEnabled(True)
        self.plot_widget.set_specs(dataset,config,specs)
        summary=summary_statistics(dataset,config)
        self.status_label.setText(f"{len(specs)} graphs | Total therapy {hours_minutes(summary['total_minutes'])} h:min | "
                                  f"Median daily AHI {rounded(summary['ahi_median'])} | Missing values remain gaps")

    def set_busy(self,busy,operation):
        self.import_widget.set_busy(busy)
        self.configuration_widget.setEnabled(not busy)
        self.parameters_widget.setEnabled(not busy)
        self.plot_widget.set_paused(busy)
        self.progress_bar.setVisible(busy)
        if busy:
            self.update_timer.stop();self.progress_bar.setRange(0,0);self.status_label.setText(operation+'...')
        else:
            self.progress_bar.setRange(0,100)
            if self._closing:self.close()
            elif self.logic.dataset is not None:self.request_update()

    def show_progress(self,value,message):
        self.progress_bar.setRange(0,100);self.progress_bar.setValue(value);self.status_label.setText(message)

    def show_error(self,message):
        self.status_label.setText(message)
        QMessageBox.critical(self,'Operation could not be completed',message)

    def _save_path(self,title,suffix):
        name='therapy_report' if suffix=='.pdf' else 'therapy_complete_snapshot'
        patient=self.configuration_widget.patient()
        if patient.full_name:name+='_'+patient.full_name.replace(' ','_')
        path,_=QFileDialog.getSaveFileName(self,title,name+suffix,'PDF (*.pdf)' if suffix=='.pdf' else 'JSON (*.json)')
        if path and not path.lower().endswith(suffix):path+=suffix
        return path

    def export_json(self):
        if self.logic.dataset is None or self.logic.busy:return
        path=self._save_path('Export complete decoded data','.json')
        if not path:return
        try:config=self.configuration_widget.configuration(self.parameters_widget.selected_groups())
        except ValueError:config=None
        self.logic.export_json(path,self.configuration_widget.patient(),config)

    def export_pdf(self):
        if self.logic.dataset is None or self.logic.busy:return
        try:
            config=self.configuration_widget.configuration(self.parameters_widget.selected_groups())
            config.validate()
        except ValueError as error:
            self.show_error(str(error));return
        path=self._save_path('Export configured plots and daily appendix','.pdf')
        if path:self.logic.export_pdf(path,self.configuration_widget.patient(),config)

    def export_finished(self,path):
        self._last_export=path;self.open_export_button.show()
        self.open_export_button.setToolTip(path)
        self.status_label.setText('Exported '+path)

    def closeEvent(self,event):
        if self.logic.busy:
            self._closing=True;self.status_label.setText('Finishing the current file operation before closing...')
            event.ignore();return
        self.update_timer.stop();self.plot_widget.render_timer.stop();self.plot_widget.clear()
        event.accept()
