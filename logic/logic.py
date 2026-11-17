"""Application coordinator, following the widget/logic separation in EvoFlow."""
from PySide6.QtCore import QObject, Signal, Slot

from ..core.service import analyze_folder, open_snapshot, export_snapshot
from ..core.report import export_report
from .workers import TaskWorker


class Logic(QObject):
    dataset_updated=Signal(object)
    busy_changed=Signal(bool,str)
    progress_updated=Signal(int,str)
    status_message=Signal(str)
    error_requested=Signal(str)
    export_finished=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.dataset=None
        self.worker=None
        self._operation=''

    @property
    def busy(self):
        return self.worker is not None

    def _start(self, operation, task):
        if self.busy:
            return
        self._operation=operation
        self.worker=TaskWorker(task,self)
        self.worker.result_ready.connect(self._result)
        self.worker.failed.connect(self.error_requested)
        self.worker.progress.connect(self.progress_updated)
        self.worker.finished.connect(self._finished)
        self.busy_changed.emit(True,operation)
        self.worker.start()

    @Slot(object)
    def _result(self,result):
        if self._operation in ('Analyzing raw data','Opening JSON'):
            self.dataset=result
            self.dataset_updated.emit(result)
        else:
            self.export_finished.emit(str(result))

    @Slot()
    def _finished(self):
        worker=self.worker
        self.worker=None
        if worker is not None:worker.deleteLater()
        self.busy_changed.emit(False,self._operation)
        self.status_message.emit('Ready')

    def clear_dataset(self):
        if self.busy:return
        self.dataset=None
        self.dataset_updated.emit(None)

    def analyze(self,path):
        self._start('Analyzing raw data',lambda progress:analyze_folder(path))

    def open_json(self,path):
        self._start('Opening JSON',lambda progress:open_snapshot(path))

    def export_json(self,path,patient,configuration):
        dataset=self.dataset
        if dataset is not None:
            self._start('Exporting complete JSON',lambda progress:export_snapshot(path,dataset,patient,configuration))

    def export_pdf(self,path,patient,configuration):
        dataset=self.dataset
        if dataset is not None:
            self._start('Exporting PDF',lambda progress:export_report(path,dataset,patient,configuration,progress))

    def shutdown(self):
        # MainUI waits for the bounded file operation; never terminate a writer.
        if self.worker is not None:self.worker.wait()
