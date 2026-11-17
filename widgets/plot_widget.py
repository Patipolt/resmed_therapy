"""Scroll all configured graphs; render only visible cards to bound memory."""
from collections import OrderedDict

from PySide6.QtCore import QTimer,Signal
from PySide6.QtWidgets import QGroupBox,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QScrollArea,QWidget,QFrame
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg,NavigationToolbar2QT

from ..core.plotting import make_figure,PLOT_LOCK
from ..core.parameters import catalogue


class LockedCanvas(FigureCanvasQTAgg):
    def draw(self,*args,**kwargs):
        with PLOT_LOCK:return super().draw(*args,**kwargs)


class PlotCard(QFrame):
    def __init__(self,dataset,config,spec,parent=None):
        super().__init__(parent)
        self.dataset=dataset;self.config=config;self.spec=spec;self.canvas=None;self.toolbar=None
        self.setObjectName('plotCard');self.setFixedHeight(320)
        self.box=QVBoxLayout(self);self.box.setContentsMargins(5,5,5,5);self.box.setSpacing(0)
        group=next(group for group in catalogue(dataset) if group.key==spec.group_key)
        self.placeholder=QLabel(group.title+'\n'+spec.period.label+'\nScroll here to render this graph')
        self.placeholder.setObjectName('plotPlaceholder');self.placeholder.setWordWrap(True)
        self.box.addWidget(self.placeholder,1)

    def mount(self):
        if self.canvas is not None:return
        with PLOT_LOCK:
            figure=make_figure(self.dataset,self.config,self.spec)
            self.canvas=LockedCanvas(figure)
            self.toolbar=NavigationToolbar2QT(self.canvas,self,coordinates=True)
            self.toolbar.setMaximumHeight(30)
            self.placeholder.hide()
            self.box.addWidget(self.canvas,1);self.box.addWidget(self.toolbar)
            self.canvas.draw()

    def unmount(self):
        if self.canvas is None:return
        with PLOT_LOCK:
            self.box.removeWidget(self.toolbar);self.box.removeWidget(self.canvas)
            self.canvas.figure.clear();self.toolbar.deleteLater();self.canvas.deleteLater()
            self.canvas=None;self.toolbar=None;self.placeholder.show()


class PlotWidget(QGroupBox):
    render_error=Signal(str)

    def __init__(self,parent=None):
        super().__init__('Plots and graphs',parent)
        self.cards=[];self.cache=OrderedDict();self.paused=False
        self.setup_ui();self.connect_signals()

    def setup_ui(self):
        layout=QVBoxLayout(self)
        top=QHBoxLayout();self.count_label=QLabel('No data analyzed');top.addWidget(self.count_label,1)
        self.jump_combo=QComboBox();self.jump_combo.setMinimumWidth(220);self.jump_combo.setMaximumWidth(390)
        top.addWidget(self.jump_combo);layout.addLayout(top)
        self.scroll_area=QScrollArea();self.scroll_area.setWidgetResizable(True)
        self.container=QWidget();self.plot_layout=QVBoxLayout(self.container);self.plot_layout.setContentsMargins(4,4,4,4);self.plot_layout.setSpacing(9)
        self.empty_label=QLabel('Import a raw data folder, then click Analyze.\nYour configured graphs will appear here.')
        self.empty_label.setObjectName('emptyPlots');self.empty_label.setWordWrap(True)
        self.plot_layout.addWidget(self.empty_label);self.plot_layout.addStretch()
        self.scroll_area.setWidget(self.container);layout.addWidget(self.scroll_area,1)
        self.render_timer=QTimer(self);self.render_timer.setSingleShot(True);self.render_timer.setInterval(70)

    def connect_signals(self):
        self.scroll_area.verticalScrollBar().valueChanged.connect(lambda:self.render_timer.start())
        self.render_timer.timeout.connect(self.render_visible)
        self.jump_combo.activated.connect(self.jump_to_period)

    def clear(self):
        self.render_timer.stop()
        for card in self.cache.values():card.unmount()
        self.cache.clear();self.cards=[]
        while self.plot_layout.count():
            item=self.plot_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.jump_combo.clear()

    def show_message(self,text):
        self.clear();label=QLabel(text);label.setObjectName('emptyPlots');label.setWordWrap(True)
        self.plot_layout.addWidget(label);self.plot_layout.addStretch();self.count_label.setText('No plots')

    def set_specs(self,dataset,config,specs):
        self.clear()
        previous=None
        for index,spec in enumerate(specs):
            card=PlotCard(dataset,config,spec,self.container)
            self.cards.append(card);self.plot_layout.addWidget(card)
            if spec.period!=previous:
                self.jump_combo.addItem(spec.period.label,index);previous=spec.period
        self.plot_layout.addStretch()
        self.count_label.setText(f'{len(specs)} graphs | {config.start} to {config.end}')
        self.scroll_area.verticalScrollBar().setValue(0)
        self.render_timer.start()

    def render_visible(self):
        if self.paused or not self.cards:return
        low=self.scroll_area.verticalScrollBar().value()-200
        high=low+self.scroll_area.viewport().height()+400
        visible=[(index,card) for index,card in enumerate(self.cards) if card.y()+card.height()>=low and card.y()<=high]
        rendered=0
        try:
            for index,card in visible:
                if card.canvas is None:
                    if rendered>=2:
                        self.render_timer.start();break
                    card.mount();rendered+=1
                self.cache[index]=card;self.cache.move_to_end(index)
            protected={index for index,card in visible}
            for index in list(self.cache):
                if len(self.cache)<=max(10,len(protected)):break
                if index not in protected:self.cache.pop(index).unmount()
        except Exception as error:
            self.render_timer.stop();self.render_error.emit(str(error))

    def set_paused(self,paused):
        self.paused=paused
        if paused:self.render_timer.stop()
        else:self.render_timer.start()

    def jump_to_period(self,index):
        card_index=self.jump_combo.itemData(index)
        if card_index is not None and card_index<len(self.cards):
            self.scroll_area.ensureWidgetVisible(self.cards[card_index],0,10)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'render_timer'):self.render_timer.start()
