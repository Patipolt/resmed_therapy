"""Import controls: selecting a path is separate from analyzing its contents."""
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QPushButton, QLineEdit, QFileDialog


class ImportWidget(QGroupBox):
    folder_selected=Signal(str)
    analyze_requested=Signal(str)
    export_requested=Signal()
    open_json_requested=Signal(str)

    def __init__(self,parent=None):
        super().__init__('Import',parent)
        self._has_data=False
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout=QHBoxLayout(self)
        self.import_button=QPushButton('Import')
        self.path_edit=QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText('Choose the raw SD-card folder containing STR.edf')
        self.analyze_button=QPushButton('Analyze')
        self.analyze_button.setEnabled(False)
        self.export_button=QPushButton('Export JSON')
        self.export_button.setEnabled(False)
        self.open_json_button=QPushButton('Open JSON')
        for button in (self.import_button,self.analyze_button,self.export_button,self.open_json_button):
            button.setMinimumHeight(30)
        self.export_button.setToolTip('Export ALL decoded source records, original samples, headers and binary logs, regardless of plot date range.')
        layout.addWidget(self.import_button)
        layout.addWidget(self.path_edit,1)
        layout.addWidget(self.analyze_button)
        layout.addWidget(self.export_button)
        layout.addWidget(self.open_json_button)

    def connect_signals(self):
        self.import_button.clicked.connect(self.select_folder)
        self.analyze_button.clicked.connect(lambda:self.analyze_requested.emit(self.path_edit.text()))
        self.export_button.clicked.connect(self.export_requested)
        self.open_json_button.clicked.connect(self.select_json)

    def select_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Select raw ResMed data folder',self.path_edit.text())
        if path:self.set_folder(path)

    def set_folder(self,path):
        self.path_edit.setText(path)
        self._has_data=False
        self.analyze_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.folder_selected.emit(path)

    def select_json(self):
        path,_=QFileDialog.getOpenFileName(self,'Open complete JSON snapshot','','JSON files (*.json)')
        if path:self.open_json_requested.emit(path)

    def set_data_available(self,available):
        self._has_data=available
        self.export_button.setEnabled(available)

    def set_busy(self,busy):
        self.import_button.setEnabled(not busy)
        self.open_json_button.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy and bool(self.path_edit.text()) and Path(self.path_edit.text()).is_dir())
        self.export_button.setEnabled(not busy and self._has_data)
