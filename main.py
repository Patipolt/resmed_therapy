"""Entry point. Run this file or `python -m resmed_therapy_interpretation`."""
from pathlib import Path
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))


def main():
    from PySide6.QtWidgets import QApplication
    from resmed_therapy_interpretation.pages.main_ui import MainUI
    from resmed_therapy_interpretation.styles import stylesheet
    app=QApplication(sys.argv)
    app.setApplicationName('ResMed Therapy Interpretation')
    app.setOrganizationName('ResMedTherapyInterpretationLocal')
    app.setStyle('Fusion');app.setStyleSheet(stylesheet())
    window=MainUI();window.show()
    return app.exec()


if __name__=='__main__':raise SystemExit(main())
