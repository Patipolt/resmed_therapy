"""PDF export of the configured plots plus daily appendices.

Uses the same PlotSpec and renderer as the GUI, including period boundaries and
averaging. All output is generated from the imported in-memory dataset.
"""
from __future__ import annotations
from datetime import date
from io import BytesIO
import os
import tempfile
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak, Image, KeepTogether, Spacer

from .analysis import build_plot_specs, summary_statistics
from .decoder import display, hours_minutes, rounded, numeric, settings_changes, timing_fragments
from .parameters import catalogue, available_fields, field_title
from .plotting import render_png
from .service import validate_output_path


def export_report(path, dataset, patient, config, progress=None):
    config.validate()
    target=validate_output_path(dataset,path,'.pdf')
    specs=build_plot_specs(dataset,config)
    rows=dataset.selected(config)
    if not rows:raise ValueError('No daily records in this interval.')
    today=date.today();age=patient.age_on(today)
    width=A4[0]-72
    styles={
        'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=21,leading=25,textColor=colors.HexColor('#234657'),spaceAfter=10),
        'heading':ParagraphStyle('heading',fontName='Helvetica-Bold',fontSize=12,leading=16,textColor=colors.HexColor('#234657'),spaceBefore=10,spaceAfter=7),
        'body':ParagraphStyle('body',fontName='Helvetica',fontSize=9,leading=13,spaceAfter=7),
        'small':ParagraphStyle('small',fontName='Helvetica',fontSize=7.5,leading=10,spaceAfter=6),
        'cell':ParagraphStyle('cell',fontName='Helvetica',fontSize=7,leading=9),
    }
    story=[];buffers=[]
    def p(text,style='body'):
        return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    def add(text,style='body'):story.append(p(text,style))
    def heading(text):
        story.append(PageBreak());add(text,'title')
    def table(data,widths=None):
        table=Table([[p(display(value),'cell') for value in row] for row in data],
                    colWidths=widths or [width/len(data[0])]*len(data[0]),repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4eef1')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f8f9')]),
            ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        story.append(table)
    identity=dataset.identity;s=summary_statistics(dataset,config)
    add('Therapy overview','title')
    add(patient.full_name or 'Patient name not provided','heading')
    table([['Patient information','Value'],['Date of birth',patient.date_of_birth or 'Not provided'],
           ['Age at report date',str(age) if age is not None else 'Not provided'],['Patient ID',patient.patient_id or 'Not provided'],
           ['Clinician',patient.clinician or 'Not provided'],['Report date',today.isoformat()],
           ['Device',identity.get('PNA','Unknown').replace('_',' ')],['Serial number',identity.get('SRN','Unknown')],
           ['Selected machine days',config.start+' to '+config.end]])
    add('Selected-period summary','heading')
    table([['Usage','Value','Therapy summaries','Value'],
        ['Days used / selected calendar days',f"{s['used_days']} / {s['calendar_days']}",'Daily AHI median',rounded(s['ahi_median'])],
        [f'Days at least {config.usage_goal_hours:g} h',s['goal_days'],'Target pressure median',rounded(s['pressure_median'])+' cmH2O'],
        ['Total usage h:min',hours_minutes(s['total_minutes']),'Target pressure 95th*',rounded(s['pressure_95'])+' cmH2O'],
        ['Median / mean usage h:min',hours_minutes(s['median_minutes'])+' / '+hours_minutes(s['mean_minutes']),'Maximum target pressure',rounded(s['pressure_max'])+' cmH2O'],
        ['Missing duration / absent day records',f"{s['missing_duration_days']} / {s['absent_days']}",'Leak 95th*',rounded(s['leak_95'])+' L/min']])
    if patient.notes:add('Notes: '+patient.notes,'small')
    add('*Period values are medians of daily summary values, not pooled breath-level percentiles. Usage is therapy time, not sleep time. AHI is the machine-reported index; missing values are not zero.','small')
    add(f"Views: {', '.join(kind for kind,enabled in [('calendar weeks',config.weekly),('calendar months',config.monthly)] if enabled)}. "
        +(f'Trailing {config.average_days}-calendar-day averages enabled.' if config.averaging else 'Averaging disabled.'),'small')

    heading('Recording coverage and interpretation')
    add(f"Available machine-day coverage: {dataset.first_date} to {dataset.last_date}. {len(dataset.records)} daily records; "
        f"{len(dataset.summary_edf['signals'])} source fields. The final source day may be incomplete.")
    add('This AirStart dataset contains daily summaries and minute-level mask timing. It does not supply individual breath shapes or respiratory-event timestamps. Unavailable event indices and leak statistics are not invented. All clocks are machine time; timezone and clock correctness are unverified.')
    add('Averages are trailing arithmetic means across the configured number of calendar days, using available values within the selected interval. They continue across week/month boundaries. Partial initial windows are used; a missing current day remains a gap. Settings, fault/checksum words, cumulative totals and mask timing do not receive average overlays.')
    add('Recorded settings changes','heading')
    changes=settings_changes(rows)
    settings=[['First observed day','Field','Previous','Recorded value']]
    for event in changes:
        for label,value in event['changes'].items():
            if value['before'] is not None:settings.append([event['first_observed_date'],label,value['before'],value['after']])
    if len(settings)>1:table(settings,[85,220,95,width-400])
    else:add('No changes observed between available selected daily settings. This does not establish exact change times.')
    if dataset.warnings:
        add('Source notes','heading')
        for warning in dataset.warnings:add(warning,'small')
    add('Additional technical values and proprietary configuration codes are preserved in the complete JSON export. Binary service logs are retained without a clinical interpretation; daily CRC16 words are not independently checked.','small')
    add('Source fingerprint: '+dataset.summary_edf['header']['sha256'],'small')

    previous_period=None
    plots_on_page=0
    for index,spec in enumerate(specs):
        if spec.period!=previous_period:
            heading('Plots - '+spec.period.label)
            plots_on_page=0
        elif plots_on_page==4:
            heading('Plots - '+spec.period.label+' (continued)')
            plots_on_page=0
        if progress:progress(int(index/max(1,len(specs))*90),f'Rendering plot {index+1} of {len(specs)}')
        buffer=BytesIO();render_png(dataset,config,spec,buffer,dpi=180);buffer.seek(0);buffers.append(buffer)
        image=Image(buffer,width=width,height=width*2.65/10)
        story.append(KeepTogether([image,Spacer(1,10)]))
        plots_on_page+=1
        previous_period=spec.period

    heading('Daily data appendix')
    add('All selected machine days are retained, including missing values. Core-table pressure units are cmH2O; leak is L/min. A dash means missing. A partial source day remains a partial record.','small')
    data=[['Machine day','Therapy h:min','AHI','Pressure median','Pressure 95th','Pressure max','Leak 95th L/min']]
    for row in rows:
        data.append([row['date'],hours_minutes(row.get('Duration')),row.get('AHI'),row.get('TgtIPAP.50'),row.get('TgtIPAP.95'),
                     row.get('TgtIPAP.Max'),row['Leak.95']*60 if numeric(row.get('Leak.95')) else None])
    table(data,[78,72,40,78,78,78,width-424])
    groups={group.key:group for group in catalogue(dataset)}
    if config.appendix=='All decoded fields':
        labels=[signal['label'] for signal in dataset.summary_edf['signals'] if signal['label'] not in ('Date','MaskOn','MaskOff')]
    else:
        labels=[]
        for key in config.selected_groups:
            for label in available_fields(groups[key],dataset):
                if label not in labels and not label.startswith('@') and label not in ('MaskOn','MaskOff'):
                    labels.append(label)
    units={signal['label']:signal['unit'] for signal in dataset.summary_edf['signals']}
    for start in range(0,len(labels),5):
        group=labels[start:start+5]
        heading('Daily fields - '+str(start//5+1))
        add('Original EDF units and field labels are retained here. In particular, raw leak fields use L/s rather than the converted L/min shown in the core table. Coded settings may be inactive in the current mode.','small')
        table([['Machine day']+[label+'\n'+(units.get(label) or 'unitless') for label in group]]+
              [[row['date']]+[row.get(label) for label in group] for row in rows],[80]+[(width-80)/len(group)]*len(group))
    if 'timing' in config.selected_groups or config.appendix=='All decoded fields':
        heading('Daily mask timing appendix')
        add('Offsets are minutes from the EDF day boundary. Fragment spans are not substituted for therapy duration. Day-boundary fragments remain separate; they do not establish an awakening or respiratory event.','small')
        data=[['Machine day / slot','On / off minute offsets','Machine-clock start','Machine-clock end','Span min']]
        for row in rows:
            for fragment in timing_fragments(row):
                data.append([row['date']+f" / {fragment['slot']}",f"{display(fragment['on_offset_minutes'])} / {display(fragment['off_offset_minutes'])}",
                             fragment['start_machine_time'],fragment['end_machine_time'],fragment['span_minutes']])
        if len(data)>1:table(data,[90,95,135,135,width-455])

    def footer(canvas,document):
        canvas.saveState();canvas.setStrokeColor(colors.HexColor('#c7d6dc'));canvas.line(36,32,A4[0]-36,32)
        canvas.setFont('Helvetica',7);canvas.drawString(36,20,'ResMed Therapy Interpretation | Machine time | '+today.isoformat())
        canvas.drawRightString(A4[0]-36,20,f'Page {document.page}');canvas.restoreState()
    class ReportDocument(SimpleDocTemplate):
        def afterFlowable(self,flowable):
            if isinstance(flowable,Paragraph) and flowable.style.name=='title':
                bookmark=f'section-{self.page}';self.canv.bookmarkPage(bookmark)
                self.canv.addOutlineEntry(flowable.getPlainText(),bookmark,level=0)
    descriptor,temp=tempfile.mkstemp(prefix='.resmed-',suffix='.pdf',dir=target.parent);os.close(descriptor)
    try:
        if progress:progress(92,'Building PDF and appendices')
        ReportDocument(temp,pagesize=A4,leftMargin=36,rightMargin=36,topMargin=36,bottomMargin=48,
                       title='Therapy report - '+(patient.full_name or 'Patient'),author='ResMed Therapy Interpretation').build(story,onFirstPage=footer,onLaterPages=footer)
        os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)
        for buffer in buffers:buffer.close()
    if progress:progress(100,'PDF exported')
    return str(target)
