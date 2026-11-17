"""Grouped checkbox selection. Any related checkbox toggles its whole group."""
from PySide6.QtCore import Signal,QSignalBlocker
from PySide6.QtWidgets import QGroupBox,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,QScrollArea,QWidget,QCheckBox,QLabel,QFrame

from ..core.parameters import catalogue,available_fields,field_title


class ParametersWidget(QGroupBox):
    selection_changed=Signal()

    def __init__(self,parent=None):
        super().__init__('Parameters',parent)
        self.dataset=None;self.groups=();self.group_checks={};self.field_checks={};self.frames={}
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout=QVBoxLayout(self);layout.setSpacing(6)
        self.search_edit=QLineEdit();self.search_edit.setPlaceholderText('Find a parameter...')
        layout.addWidget(self.search_edit)
        buttons=QHBoxLayout();self.defaults_button=QPushButton('Defaults');self.all_button=QPushButton('All');self.clear_button=QPushButton('Clear')
        for button in (self.defaults_button,self.all_button,self.clear_button):buttons.addWidget(button)
        layout.addLayout(buttons)
        self.scroll_area=QScrollArea();self.scroll_area.setWidgetResizable(True);self.scroll_area.setMinimumHeight(150)
        self.container=QWidget();self.check_layout=QVBoxLayout(self.container);self.check_layout.setContentsMargins(4,4,4,4);self.check_layout.setSpacing(6)
        self.check_layout.addWidget(QLabel('Analyze a raw folder to see available fields.'))
        self.check_layout.addStretch()
        self.scroll_area.setWidget(self.container);layout.addWidget(self.scroll_area,1)

    def connect_signals(self):
        self.search_edit.textChanged.connect(self.filter_groups)
        self.defaults_button.clicked.connect(lambda:self.set_selection([group.key for group in self.groups if group.default]))
        self.all_button.clicked.connect(lambda:self.set_selection([group.key for group in self.groups]))
        self.clear_button.clicked.connect(lambda:self.set_selection([]))

    def set_dataset(self,dataset):
        self.dataset=dataset
        while self.check_layout.count():
            item=self.check_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.group_checks={};self.field_checks={};self.frames={}
        if dataset is None:
            self.groups=();self.check_layout.addWidget(QLabel('Analyze a raw folder to see available fields.'));self.check_layout.addStretch();return
        self.groups=catalogue(dataset)
        for group in self.groups:
            frame=QFrame();frame.setObjectName('parameterFrame');inside=QVBoxLayout(frame);inside.setContentsMargins(7,6,7,6);inside.setSpacing(3)
            header=QCheckBox(group.title);header.setObjectName('parameterHeading')
            available=available_fields(group,dataset);header.setEnabled(bool(available));header.setToolTip(group.note)
            self.group_checks[group.key]=header;self.frames[group.key]=frame;inside.addWidget(header)
            checks=[]
            for label in group.fields:
                is_available=label in available
                text=field_title(label)+(f' ({label})' if field_title(label)!=label and not label.startswith('@') else '')
                if not is_available:text+=' - not recorded'
                checkbox=QCheckBox(text);checkbox.setEnabled(is_available)
                checkbox.setToolTip(group.note if is_available else 'This field was not recorded by this machine; it is not plotted as zero.')
                checkbox.setContentsMargins(15,0,0,0)
                self.field_checks[(group.key,label)]=checkbox;checks.append(checkbox);inside.addWidget(checkbox)
                checkbox.toggled.connect(lambda checked,key=group.key:self.toggle_group(key,checked))
            header.toggled.connect(lambda checked,key=group.key:self.toggle_group(key,checked))
            self.check_layout.addWidget(frame)
        self.check_layout.addStretch()
        selected=dataset.saved_configuration.get('selected_groups')
        self.set_selection(selected if selected is not None else [group.key for group in self.groups if group.default])
        self.filter_groups(self.search_edit.text())

    def toggle_group(self,key,checked,emit=True):
        header=self.group_checks[key]
        group=next(group for group in self.groups if group.key==key)
        available=set(available_fields(group,self.dataset))
        # Parent controls are temporarily disabled during background import.
        # Availability is a data property, not QWidget.isEnabled() ancestry.
        if not available:return
        with QSignalBlocker(header):header.setChecked(checked)
        for label in group.fields:
            checkbox=self.field_checks[(key,label)]
            if label in available:
                with QSignalBlocker(checkbox):checkbox.setChecked(checked)
        if emit:self.selection_changed.emit()

    def set_selection(self,keys):
        keys=set(keys)
        for group in self.groups:self.toggle_group(group.key,group.key in keys,emit=False)
        self.selection_changed.emit()

    def selected_groups(self):
        return tuple(group.key for group in self.groups if self.group_checks[group.key].isChecked())

    def filter_groups(self,text):
        needle=text.strip().lower()
        for group in self.groups:
            self.frames[group.key].setVisible(not needle or needle in (group.title+' '+' '.join(group.fields)).lower())
