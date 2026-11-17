"""Centralized colours and Qt styles; adjust here instead of editing each widget."""
from pathlib import Path


def stylesheet():
    calendar=(Path(__file__).parent/'assets'/'calendar.svg').as_posix()
    return '''
    QWidget { background: #222a33; color: #e2e8ee; font-family: "Arial"; font-size: 12px; }
    QMainWindow, #centralWidget { background: #1b222b; }
    #appTitle { font-size: 21px; font-weight: bold; color: #f4f6f8; }
    #muted { color: #a3b0bd; font-size: 11px; }
    QGroupBox { border: 1px solid #455160; border-radius: 7px; margin-top: 13px; padding-top: 6px; font-weight: bold; }
    QGroupBox::title { subcontrol-origin: margin; left: 11px; padding: 0 5px; color: #f2bf7d; }
    QPushButton { background: #efad61; color: #17222d; border: 1px solid #e9a452; border-radius: 4px; padding: 5px 10px; font-weight: bold; }
    QPushButton:hover { background: #ffc77f; }
    QPushButton:pressed { background: #d98e3f; }
    QPushButton:disabled { background: #39434e; color: #7b8998; border-color: #455160; }
    QLineEdit, QDateEdit, QDoubleSpinBox, QComboBox { background: #333f4c; color: #eef2f6; border: 1px solid #4d5c6e; border-radius: 4px; padding: 5px; min-height: 19px; font-weight: normal; }
    QLineEdit:focus, QDateEdit:focus { border-color: #f2bf7d; }
    QLineEdit:disabled, QDateEdit:disabled { color: #788797; background: #2a333e; }
    QLineEdit[readOnly="true"] { color: #bdcad7; }
    QComboBox QAbstractItemView { background: #333f4c; color: white; selection-background-color: #566b80; }
    QCheckBox { font-weight: normal; spacing: 6px; }
    QCheckBox::indicator { width: 14px; height: 14px; }
    QCheckBox:disabled { color: #7d8a98; }
    #parameterHeading { font-weight: bold; color: #e9c18f; }
    #parameterFrame { background: #293440; border-radius: 4px; }
    QScrollArea { border: none; }
    QScrollBar:vertical { background: #222a33; width: 12px; margin: 0; }
    QScrollBar::handle:vertical { background: #62758a; min-height: 25px; border-radius: 5px; }
    QScrollBar::handle:vertical:hover { background: #efad61; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    #plotCard, #plotPlaceholder { background: white; color: #536d7a; border-radius: 5px; }
    #plotPlaceholder { padding: 24px; font-size: 15px; }
    #emptyPlots { color: #b5c5d4; font-size: 16px; padding: 30px; }
    #dataSummary { background: #293440; padding: 7px; border-radius: 4px; font-weight: normal; }
    QProgressBar { border: 1px solid #516274; border-radius: 4px; text-align: center; }
    QProgressBar::chunk { background: #efad61; }
    QToolTip { background: #f1f5f9; color: #223545; border: 1px solid #9aafc2; padding: 6px; }
    QCalendarWidget QAbstractItemView { background: #333f4c; color: #f2f4f6; selection-background-color: #d28a38; }
    ''' + f'QDateEdit::down-arrow {{ image: url("{calendar}"); width: 15px; height: 15px; }}'
