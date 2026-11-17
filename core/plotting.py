"""One plotting function shared by the live GUI and PDF export.

No pyplot/global figures. A lock serializes font/render work across Qt and the
export worker. Qt canvases are only constructed on the main thread.
"""
from __future__ import annotations
from datetime import date, timedelta
import math
import threading

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib import dates as mdates
from matplotlib.ticker import MaxNLocator

from .analysis import daily_series, trailing_average
from .decoder import timing_fragments
from .parameters import available_fields, catalogue, field_title

PLOT_LOCK=threading.RLock()
COLORS=('#287e9c','#d28a38','#7b65b0','#529472','#c45769','#54708d')
SUMMARY_BAR_COLORS={'Max':'#d8e9f0','95':'#85b4c8','70':'#427e99','50':'#24516d'}
SUMMARY_LINE_COLORS={'Max':'#8ba9bb','95':'#4c86a5','70':'#336b84','50':'#193e55'}


def summary_bar_order(fields):
    """Draw higher summaries first, with opaque lower bars overlaid (not summed)."""
    rank={'Max':100,'95':95,'70':70,'50':50}
    return sorted(fields,key=lambda label:rank.get(label.rsplit('.',1)[-1],0),reverse=True)


def make_figure(dataset, config, spec):
    """Caller holds PLOT_LOCK until it has drawn/saved the returned figure."""
    group=next(group for group in catalogue(dataset) if group.key==spec.group_key)
    figure=Figure(figsize=(10,2.65),dpi=110,facecolor='#ffffff')
    axis=figure.add_subplot(111)
    axis.set_facecolor('#ffffff')
    axis.spines[['top','right']].set_visible(False)
    axis.spines[['bottom','left']].set_color('#bac8cc')
    axis.tick_params(colors='#49616e',labelsize=8)
    axis.grid(axis='y',color='#e2e9ed',linewidth=.7)
    axis.set_axisbelow(True)
    axis.set_title(group.title+'  |  '+spec.period.label,loc='left',fontsize=10,fontweight='bold',color='#234657',pad=30 if group.kind!='timing' else 13)
    rows={row['date']:row for row in dataset.selected(config)}
    if group.kind=='timing':
        days=[];current=spec.period.start
        while current<=spec.period.end:
            days.append(current);current+=timedelta(days=1)
        for i,day in enumerate(days):
            row=rows.get(day.isoformat())
            if row:
                for fragment in timing_fragments(row):
                    if fragment['span_minutes'] is not None:
                        axis.barh(i,fragment['span_minutes']/60,left=fragment['on_offset_minutes']/60,
                                  height=.62,color=COLORS[0],alpha=.85)
        axis.set_yticks(range(len(days)),[day.strftime('%a %d') for day in days],fontsize=7)
        axis.invert_yaxis();axis.set_xlim(0,24);axis.set_xticks(range(0,25,3))
        boundary=dataset.summary_edf['header']['start'][11:16]
        axis.set_xlabel(f'Hours after {boundary} machine time (fragments are not sleep stages)',fontsize=8)
        axis.grid(axis='x',color='#e2e9ed',linewidth=.7)
        if len(days)>10:
            axis.set_yticks(range(0,len(days),2),[days[i].strftime('%d %b') for i in range(0,len(days),2)],fontsize=7)
    else:
        missing_mask=None
        fields=available_fields(group,dataset)
        summary_bars=group.key in ('leak','pressure')
        if summary_bars:fields=summary_bar_order(fields)
        for index,label in enumerate(fields):
            days,values=daily_series(dataset,config,label)
            indices=[i for i,day in enumerate(days) if spec.period.start<=day<=spec.period.end]
            x=[days[i] for i in indices];y=[values[i] for i in indices]
            color=COLORS[index%len(COLORS)]
            suffix=label.rsplit('.',1)[-1]
            if summary_bars:
                color=SUMMARY_BAR_COLORS.get(suffix,color)
                axis.bar(x,y,width=.68,color=color,alpha=1,label=field_title(label))
            elif group.kind=='setting':
                axis.step(x,y,where='mid',linewidth=1.8,color=color,label=field_title(label))
                axis.plot(x,y,'.',color=color,markersize=4)
            elif group.key=='usage' and index==0 or group.key=='events' and label=='AHI':
                axis.bar(x,y,width=.68,color=color,alpha=.7,label=field_title(label))
            else:
                axis.plot(x,y,'o-',color=color,linewidth=1.5,markersize=3,label=field_title(label))
            if config.averaging and group.kind=='measurement':
                average=trailing_average(values,config.average_days)
                line_color=SUMMARY_LINE_COLORS.get(suffix,color) if summary_bars else color
                axis.plot(x,[average[i] for i in indices],color=line_color,linestyle='--',linewidth=1.5,
                          label=f'{field_title(label)} - {config.average_days}d mean')
            if missing_mask is None:missing_mask=[day for day,value in zip(x,y) if not math.isfinite(value)]
        threshold={'usage':config.usage_goal_hours,'events':config.ahi_reference,'leak':config.leak_reference_lpm}.get(group.key)
        if threshold is not None:
            axis.axhline(threshold,color='#b65b55',linestyle=':',linewidth=1,label=f'Reference {threshold:g}')
        if missing_mask:
            axis.plot(missing_mask,[.02]*len(missing_mask),'x',color='#a7aeb5',transform=axis.get_xaxis_transform(),label='Missing')
        axis.set_xlim(mdates.date2num(spec.period.start)-.5,mdates.date2num(spec.period.end)+.5)
        if spec.period.kind=='week':
            axis.xaxis.set_major_locator(mdates.DayLocator())
            axis.xaxis.set_major_formatter(mdates.DateFormatter('%a\n%d %b'))
        else:
            axis.xaxis.set_major_locator(mdates.DayLocator(interval=3 if (spec.period.end-spec.period.start).days>10 else 1))
            axis.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
        if group.kind!='technical':axis.set_ylim(bottom=0)
        if group.kind in ('setting','technical'):axis.yaxis.set_major_locator(MaxNLocator(nbins=5,min_n_ticks=2))
        axis.set_ylabel(group.unit,fontsize=8,color='#49616e')
        handles,labels=axis.get_legend_handles_labels()
        if handles:axis.legend(handles,labels,loc='upper left',bbox_to_anchor=(0,1.24),fontsize=6.8,
                               frameon=False,ncol=min(4,len(handles)),handlelength=2)
    figure.subplots_adjust(left=.085,right=.985,bottom=.23,top=.70 if group.kind!='timing' else .77)
    return figure


def render_png(dataset, config, spec, output, dpi=150):
    with PLOT_LOCK:
        figure=make_figure(dataset,config,spec)
        FigureCanvasAgg(figure)
        figure.savefig(output,format='png',dpi=dpi,facecolor='white')
        figure.clear()
