"""Patient details and plot controls, exposed as ordinary editable Qt widgets."""
from pathlib import Path

from PySide6.QtCore import QDate, Signal, QSignalBlocker
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QGroupBox,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QLineEdit,
                              QDateEdit,QCheckBox,QComboBox,QPushButton,QDoubleSpinBox,QToolButton,QWidget,QScrollArea)

from ..core.models import Patient,PlotConfiguration


class ConfigurationWidget(QGroupBox):
    configuration_changed=Signal()
    export_requested=Signal()
    patient_changed=Signal()

    def __init__(self,parent=None):
        super().__init__('Plot configuration',parent)
        self.dataset=None
        self.setup_ui()
        self.connect_signals()
        self.set_data_available(False)

    def date_edit(self):
        edit=QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat('yyyy-MM-dd')
        edit.setMinimumWidth(135)
        return edit

    def setup_ui(self):
        outer=QVBoxLayout(self);outer.setSpacing(7)
        body=QWidget();layout=QVBoxLayout(body);layout.setSpacing(7);layout.setContentsMargins(2,2,2,2)
        self.controls_scroll=QScrollArea();self.controls_scroll.setWidgetResizable(True);self.controls_scroll.setWidget(body)
        self.controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(self.controls_scroll,1)
        self.patient_box=QGroupBox('Patient information (optional)')
        grid=QGridLayout(self.patient_box);grid.setHorizontalSpacing(7);grid.setVerticalSpacing(5)
        self.name_edit=QLineEdit();self.name_edit.setPlaceholderText('Name')
        self.surname_edit=QLineEdit();self.surname_edit.setPlaceholderText('Surname')
        grid.addWidget(self.name_edit,0,0);grid.addWidget(self.surname_edit,0,1)
        self.birth_known=QCheckBox('Date of birth')
        self.birth_edit=self.date_edit();self.birth_edit.setMinimumDate(QDate(1900,1,1))
        self.birth_edit.setSpecialValueText('Not specified');self.birth_edit.setDate(self.birth_edit.minimumDate())
        self.birth_edit.setMaximumDate(QDate.currentDate());self.birth_edit.setEnabled(False)
        grid.addWidget(self.birth_known,1,0);grid.addWidget(self.birth_edit,1,1)
        self.patient_id_edit=QLineEdit();self.patient_id_edit.setPlaceholderText('Patient ID (optional)')
        self.clinician_edit=QLineEdit();self.clinician_edit.setPlaceholderText('Clinician (optional)')
        self.patient_extra=QWidget();extra_grid=QGridLayout(self.patient_extra);extra_grid.setContentsMargins(0,0,0,0)
        extra_grid.addWidget(self.patient_id_edit,0,0);extra_grid.addWidget(self.clinician_edit,0,1)
        self.notes_edit=QLineEdit();self.notes_edit.setPlaceholderText('Report notes (optional)');self.notes_edit.setMaxLength(2000)
        extra_grid.addWidget(self.notes_edit,1,0,1,2)
        self.patient_extra_button=QPushButton('ID / clinician / notes');self.patient_extra_button.setCheckable(True)
        grid.addWidget(self.patient_extra_button,2,0,1,2);grid.addWidget(self.patient_extra,3,0,1,2);self.patient_extra.hide()
        layout.addWidget(self.patient_box)
        dates=QGridLayout()
        self.start_edit=self.date_edit();self.end_edit=self.date_edit()
        dates.addWidget(QLabel('Starting date'),0,0);dates.addWidget(QLabel('Ending date'),0,1)
        dates.addWidget(self.start_edit,1,0);dates.addWidget(self.end_edit,1,1)
        layout.addLayout(dates)
        self.quick_range=QComboBox();self.quick_range.addItems(['Last 30 days','Last 90 days','All data','Custom'])
        layout.addWidget(self.quick_range)
        modes=QHBoxLayout()
        self.week_check=QCheckBox('By week');self.month_check=QCheckBox('By month');self.month_check.setChecked(True)
        modes.addWidget(self.week_check);modes.addWidget(self.month_check);modes.addStretch()
        layout.addLayout(modes)
        average=QHBoxLayout()
        self.average_check=QCheckBox('Trailing average')
        self.average_edit=QLineEdit('7');self.average_edit.setValidator(QIntValidator(1,365,self));self.average_edit.setFixedWidth(52)
        self.average_edit.setEnabled(False)
        average.addWidget(self.average_check);average.addWidget(self.average_edit);average.addWidget(QLabel('calendar days'));average.addStretch()
        layout.addLayout(average)
        self.average_hint=QLabel('Available-day mean; continues across weeks/months.\nSettings and timing are not averaged.')
        self.average_hint.setObjectName('muted');self.average_hint.setWordWrap(True)
        layout.addWidget(self.average_hint)
        self.appendix_combo=QComboBox();self.appendix_combo.addItems(['Selected parameters','All decoded fields'])
        appendix=QHBoxLayout();appendix.addWidget(QLabel('Daily appendix'));appendix.addWidget(self.appendix_combo,1)
        layout.addLayout(appendix)
        self.advanced_button=QPushButton('Show analysis references')
        self.advanced_button.setCheckable(True)
        layout.addWidget(self.advanced_button)
        self.advanced_box=QGroupBox('Display references - no device changes')
        advanced=QGridLayout(self.advanced_box)
        self.usage_goal=QDoubleSpinBox();self.usage_goal.setRange(.1,24);self.usage_goal.setValue(4);self.usage_goal.setSuffix(' h')
        self.ahi_reference=QDoubleSpinBox();self.ahi_reference.setRange(0,240);self.ahi_reference.setValue(5)
        self.leak_reference=QDoubleSpinBox();self.leak_reference.setRange(0,200);self.leak_reference.setValue(24);self.leak_reference.setSuffix(' L/min')
        for i,(label,widget) in enumerate([('Usage goal',self.usage_goal),('AHI line',self.ahi_reference),('Leak .95 line',self.leak_reference)]):
            advanced.addWidget(QLabel(label),i,0);advanced.addWidget(widget,i,1)
        self.advanced_box.hide();layout.addWidget(self.advanced_box)
        self.export_button=QPushButton('Export plots + daily appendix to PDF')
        self.export_button.setMinimumHeight(34);outer.addWidget(self.export_button)

    def connect_signals(self):
        self.patient_extra_button.toggled.connect(self.patient_extra.setVisible)
        self.start_edit.dateChanged.connect(lambda:self._date_changed('start'))
        self.end_edit.dateChanged.connect(lambda:self._date_changed('end'))
        self.quick_range.currentTextChanged.connect(self.apply_quick_range)
        for check in (self.week_check,self.month_check):check.toggled.connect(self.configuration_changed)
        self.average_check.toggled.connect(self.average_edit.setEnabled)
        self.average_check.toggled.connect(self.configuration_changed)
        self.average_edit.editingFinished.connect(self.configuration_changed)
        self.average_edit.textEdited.connect(self.configuration_changed)
        self.appendix_combo.currentTextChanged.connect(self.configuration_changed)
        self.advanced_button.toggled.connect(self.advanced_box.setVisible)
        self.advanced_button.toggled.connect(lambda state:self.advanced_button.setText('Hide analysis references' if state else 'Show analysis references'))
        for spin in (self.usage_goal,self.ahi_reference,self.leak_reference):spin.valueChanged.connect(self.configuration_changed)
        self.export_button.clicked.connect(self.export_requested)
        self.birth_known.toggled.connect(self.birth_edit.setEnabled)
        self.birth_known.toggled.connect(self.patient_changed)
        self.birth_edit.dateChanged.connect(self.patient_changed)
        for edit in (self.name_edit,self.surname_edit,self.patient_id_edit,self.clinician_edit,self.notes_edit):edit.textChanged.connect(self.patient_changed)

    def _date_changed(self,which):
        if self.dataset is None:return
        if self.start_edit.date()>self.end_edit.date():
            other=self.end_edit if which=='start' else self.start_edit
            with QSignalBlocker(other):other.setDate(self.start_edit.date() if which=='start' else self.end_edit.date())
        with QSignalBlocker(self.quick_range):self.quick_range.setCurrentText('Custom')
        self.configuration_changed.emit()

    def apply_quick_range(self,text):
        if self.dataset is None or text=='Custom':return
        first=QDate.fromString(self.dataset.first_date,'yyyy-MM-dd');last=QDate.fromString(self.dataset.last_date,'yyyy-MM-dd')
        start=first if text=='All data' else max(first,last.addDays(-29 if text=='Last 30 days' else -89))
        with QSignalBlocker(self.start_edit),QSignalBlocker(self.end_edit):
            self.start_edit.setDate(start);self.end_edit.setDate(last)
        self.configuration_changed.emit()

    def set_dataset(self,dataset):
        self.dataset=dataset
        self.set_data_available(dataset is not None)
        if dataset is None:return
        first=QDate.fromString(dataset.first_date,'yyyy-MM-dd');last=QDate.fromString(dataset.last_date,'yyyy-MM-dd')
        with QSignalBlocker(self.start_edit),QSignalBlocker(self.end_edit):
            for edit in (self.start_edit,self.end_edit):edit.setDateRange(first,last)
        self.apply_quick_range('Last 30 days')
        with QSignalBlocker(self.quick_range):self.quick_range.setCurrentText('Last 30 days')
        if dataset.saved_patient:self.restore_patient(dataset.saved_patient)
        if dataset.saved_configuration:self.restore_configuration(dataset.saved_configuration)

    def set_data_available(self,available):
        for widget in (self.start_edit,self.end_edit,self.quick_range,self.week_check,self.month_check,
                       self.average_check,self.appendix_combo,self.advanced_button,self.export_button):widget.setEnabled(available)
        self.average_edit.setEnabled(available and self.average_check.isChecked())

    def patient(self):
        return Patient(self.name_edit.text().strip(),self.surname_edit.text().strip(),
                       self.birth_edit.date().toString('yyyy-MM-dd') if self.birth_known.isChecked() and self.birth_edit.date()!=self.birth_edit.minimumDate() else None,
                       self.patient_id_edit.text().strip(),self.clinician_edit.text().strip(),self.notes_edit.text().strip())

    def configuration(self,selected_groups):
        if self.average_check.isChecked() and not self.average_edit.hasAcceptableInput():
            raise ValueError('Enter an averaging window from 1 to 365 days.')
        average_days=int(self.average_edit.text()) if self.average_edit.hasAcceptableInput() else 7
        config=PlotConfiguration(self.start_edit.date().toString('yyyy-MM-dd'),self.end_edit.date().toString('yyyy-MM-dd'),
                                 self.week_check.isChecked(),self.month_check.isChecked(),self.average_check.isChecked(),
                                 average_days,tuple(selected_groups),self.usage_goal.value(),
                                 self.ahi_reference.value(),self.leak_reference.value(),self.appendix_combo.currentText())
        config.validate();return config

    def restore_patient(self,patient):
        for key,edit in [('name',self.name_edit),('surname',self.surname_edit),('patient_id',self.patient_id_edit),
                         ('clinician',self.clinician_edit),('notes',self.notes_edit)]:edit.setText(str(patient.get(key,'')))
        born=patient.get('date_of_birth');self.birth_known.setChecked(bool(born))
        if born:
            day=QDate.fromString(born,'yyyy-MM-dd')
            if day.isValid():self.birth_edit.setDate(day)

    def restore_configuration(self,config):
        with QSignalBlocker(self.start_edit),QSignalBlocker(self.end_edit):
            for key,widget in [('start',self.start_edit),('end',self.end_edit)]:
                day=QDate.fromString(config.get(key,''),'yyyy-MM-dd')
                if day.isValid():widget.setDate(day)
        for key,widget in [('weekly',self.week_check),('monthly',self.month_check),('averaging',self.average_check)]:
            if key in config:widget.setChecked(bool(config[key]))
        self.average_edit.setText(str(config.get('average_days',7)))
        for key,widget in [('usage_goal_hours',self.usage_goal),('ahi_reference',self.ahi_reference),('leak_reference_lpm',self.leak_reference)]:
            if key in config:widget.setValue(float(config[key]))
        self.appendix_combo.setCurrentText(config.get('appendix','Selected parameters'))
        with QSignalBlocker(self.quick_range):self.quick_range.setCurrentText('Custom')
