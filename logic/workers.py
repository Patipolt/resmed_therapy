"""Background jobs never touch QWidget objects."""
from PySide6.QtCore import QThread, Signal


class TaskWorker(QThread):
    result_ready=Signal(object)
    failed=Signal(str)
    progress=Signal(int,str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task=task

    def run(self):
        try:
            result=self.task(self.progress.emit)
        except Exception as error:
            self.failed.emit(f'{type(error).__name__}: {error}')
        else:
            self.result_ready.emit(result)
