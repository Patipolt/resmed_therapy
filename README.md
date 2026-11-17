# ResMed Therapy Interpretation

A single-window **PySide6 + Matplotlib** application for importing ResMed
AirStart daily SD-card data, inspecting calendar-based plots, and exporting PDF
reports or complete JSON snapshots. Source files are read-only. All source code,
assets, tests and application output live in this folder.

The organization follows the EvoFlow reference: small widget classes with
`setup_ui()` / `connect_signals()`, a `Logic` coordinator, and background workers.
The reference project itself has not been modified or imported.

## Run on this Mac

A local environment has already been installed in `.venv/`. From this folder:

```bash
.venv/bin/python main.py
```

Or double-click **launch.command**. This launcher does not install anything or
change machine settings. The local `.venv` is disposable and is not portable to
another computer.

## Fresh installation / another computer

Python **3.10 or newer**:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

On Windows use `.venv\Scripts\activate` instead. From this folder's parent,
`python -m resmed_therapy_interpretation` also works. The application needs
PySide6, Matplotlib and ReportLab. It does not require ResScan, an account,
network access at runtime, or the earlier CLI scripts.

## Workflow

1. Click **Import** and choose the raw card root containing `STR.edf`. This only
   selects a path. Click **Analyze** to decode it in a background thread.
2. The application displays model, serial, source coverage and missing-data
   counts. By default it shows the last 30 calendar days, partitioned by month.
   Use the calendar date editors or Last 30 / Last 90 / All data shortcuts.
3. Enter optional patient name, surname and date of birth. The report calculates
   age **at report date**, not at the date of therapy. Patient ID, clinician and
   free-text notes are under **ID / clinician / notes**. No DOB is assumed if
   its checkbox is unchecked.
4. Choose calendar-week and/or calendar-month views. Either or both may be
   enabled. If neither is enabled, the plot area explains what to select.
5. Choose parameter groups in the scrollable, searchable list. Changing any
   available child checkbox selects/unselects its related group. Defaults select
   AHI, leak, therapy pressure, daily usage and mask timing. Missing AI, leak
   maximum or leak median are visibly disabled, never plotted as zero.
6. Enable **Trailing average** and enter 1-365 days if desired. Changes refresh
   automatically after a short debounce. Use graph toolbar pan/zoom and the
   period jump menu to inspect long histories.
7. Click **Export plots + daily appendix to PDF**. The first page contains
   patient/device details and a selected-period summary. Subsequent pages contain
   coverage notes, the configured plots, and daily tables at the end. Choose
   **Selected parameters** or **All decoded fields** for the appendix.
8. **Export JSON** in the Import group saves *all source records and maximum
   decoded data*, even when plots are filtered to a shorter range. **Open JSON**
   reopens that snapshot without the original raw folder and restores saved
   patient/configuration choices. Full exports from the latest standalone CLI
   tool (`summary_edf` + `card` schema) can also be opened.

Only choosing **Analyze** imports the selected raw path. Changing the folder
clears the old dataset so stale plots cannot be mistaken for the new folder.

## Calendar and averaging rules

- **By week** partitions Monday-Sunday. If a range starts on Wednesday, the
  first plot shows Wednesday-Sunday; full weeks follow. The last plot stops on
  the selected end date. ISO week labels handle year boundaries.
- **By month** partitions calendar months and similarly clips both edges. Leap
  days are handled normally. Both modes together produce both sets of plots.
- All plots show **daily records** within each period. Choosing a month does not
  replace its 30/31 daily values with one monthly average.
- Average lines are **trailing N-calendar-day arithmetic means**, available
  measurements only, within the selected range. They have no look-ahead and do
  not restart at a Monday or month boundary. The first N-1 days use partial
  windows. A missing current day remains a gap rather than becoming an invented
  observation. Gaps are marked on plots.
- Settings, fault/checksum words, cumulative totals and mask timings are not
  averaged. These are not quantities for which a daily mean necessarily has a
  useful physiological meaning.
- The same `PlotSpec` and renderer generate GUI and PDF plots. On-screen pan/zoom
  is exploratory; PDF exports the full configured date interval of each plot,
  not a temporary toolbar zoom.
- Leak and therapy-pressure summaries use overlaid, non-additive bars. Maximum
  is lightest, 95th percentile is medium and median is darkest when those fields
  exist. The separate raw `.70` leak summary has its own darker shade and is not
  relabelled as a median or maximum. Average overlays remain dashed lines.
- Every calendar week/month starts on a new PDF page. If one period needs more
  than four plots, its following pages keep that same period's heading; the next
  period always starts separately.

## Information actually present

The current AirStart card has 51 source fields, 489 daily records and no detailed
files in DATALOG. The application exposes all existing fields, including:

- Therapy duration, separate on-duration, patient-hours counter, mask-transition
  count and up to ten mask-on/off slots per day.
- Combined AHI and the target inspiratory / target expiratory / mask / blower
  pressure summaries as separate groups.
- Leak `.95` and `.70`, flow summaries, blower flow, humidity, temperature and
  humidifier power summaries.
- Pressure, EPR, ramp, humidifier, mask/tube/filter and mode settings; daily fault
  words and the raw daily checksum word.
- All identification / SETTINGS text codes and opaque service-log bytes in JSON.

**No breath-by-breath waveform or respiratory-event timestamps can be recovered
from this AirStart summary.** `Flow.95` is a daily scalar, not a breathing trace.
AI/HI/central/obstructive indices and unrecorded leak percentiles cannot be
inferred from combined AHI or two leak statistics. A mask transition does not
establish an awakening. Unknown technical codes are not relabelled as clinical
measurements. Original suffix `.5` fields remain explicitly named because their
percentile semantics have not been independently verified.

Timing offsets are minutes from each EDF day boundary (12:00 machine time on
this card). Day-boundary fragments remain separate. Their spans do not replace
recorded `Duration`; no daily AHI is allocated to individual fragments. The
machine timezone and clock correctness are not known from these files.

If additional EDF/gzip files appear on a future card, the decoder inventories
them and reports that detailed waveform/event interpretation is outside this
application's scope. Do not assume that it is a full AirSense/AirCurve loader.

## Statistics and report behavior

Period therapy statistics use **medians of daily AHI and daily target-pressure
`.50` / `.95` values**. Leak `.95` is converted from L/s to L/min where needed,
then summarized by the median. Maximum target pressure is the maximum of the
daily `TgtIPAP.Max` fields. These are not pooled breath-level distributions.
Arithmetic daily AHI mean is separately available in the analysis model.

Usage totals come from `Duration`, never from the separate `OnDuration`. Missing
days are not converted to zero use. The mean usage excludes unknown-duration
days; the median uses positive-use days. Calendar-day counts, absent records
and missing durations are kept distinct.

**Show analysis references** exposes adjustable usage-goal, AHI-line and
leak-line values. They are display/analysis choices only. The application cannot
calculate time above a leak line from one daily percentile, and it cannot write
therapy settings to the machine.

The GUI does not import the representative's PDF. Reports contain no comparison
or matching section. The current statistical conventions were independently
checked against known raw-data totals during development; automated tests keep
those checks out of the patient-facing report.

The complete JSON includes original digital samples, original header bytes,
scaled values, units, patient/configuration state, all source records, timing
fragments, settings history, source hashes, parsed configuration codes and opaque
binary bytes. Date filtering affects plots/PDF, **not the completeness of JSON**.
Take that into account when sharing a snapshot.

## Safety of file operations and responsiveness

- Analysis and file exports run in `QThread` workers; Qt widgets stay on the main
  thread. An operation's patient/configuration snapshot remains fixed during
  export. Controls are temporarily disabled while a task is running.
- Graph cards are created for the full selection, but only visible figures are
  rendered. Approximately ten rendered cards are kept in memory, preventing a
  long history from creating hundreds of live Matplotlib canvases.
- A shared lock serializes Matplotlib rendering across the GUI and PDF worker.
- Output is written to a temporary file and atomically replaced only on success.
  Source card files and a loaded source JSON cannot be overwritten by export.
- Reopening complete snapshots verifies the EDF source hash, original words,
  scaling metadata and decoded values. Serial inconsistencies are rejected.
  Older snapshots without original header bytes are explicitly flagged as
  unverifiable at the bit level, rather than silently described as verified.
- Closing while an operation is running waits for it to finish; it never kills
  a thread mid-write. Patient details are not automatically written to a global
  preferences file. The program makes no network calls at runtime.

Daily CRC16 words and proprietary service-log formats are not fully decoded.
Paired `.tgt` / `.crc` files are checked as little-endian CRC32. The application
is an independent inspection/reporting tool, not a validated medical device.

## Folder structure and where to edit

```text
resmed_therapy_interpretation/
├── main.py                         # Start the GUI
├── __main__.py                     # python -m entry point
├── launch.command                  # macOS launcher using this folder's .venv
├── styles.py                       # Shared dark/orange Qt styling
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── assets/
│   └── calendar.svg
├── pages/
│   └── main_ui.py                  # Single window; widget/logic connections
├── widgets/
│   ├── import_widget.py
│   ├── configuration_widget.py     # Patient, dates, average and export controls
│   ├── parameters_widget.py        # Search and synchronized checkboxes
│   └── plot_widget.py              # Scrollable, lazy-rendered Qt canvases
├── logic/
│   ├── logic.py                    # Application coordinator
│   └── workers.py                  # Background tasks and progress signals
├── core/
│   ├── decoder.py                  # Standalone raw EDF/card reader
│   ├── models.py                   # Patient, plot configuration, dataset
│   ├── parameters.py               # Parameter groups, defaults and units
│   ├── analysis.py                 # Calendar periods, averages and statistics
│   ├── service.py                  # Analyze, JSON import/export, integrity
│   ├── plotting.py                 # Shared Matplotlib renderer
│   └── report.py                   # PDF cover, plots and daily appendices
├── tests/
│   ├── test_core.py
│   ├── test_gui.py
│   └── test_plot_exports.py        # Bar values/shades and per-period pages
└── output/
    └── example_therapy_report.pdf   # Example generated from the current card
```

`__init__.py` files identify Python packages. `.venv/` and `__pycache__/` are
generated/disposable and excluded by `.gitignore`. The application does not
depend on `cpap_report_tool/`, `decode_cpap.py`, `build_report.py` or
`evoflow_control_entity/`.

To add a parameter group, edit `core/parameters.py`: `ParameterGroup` defines the
title, related fields, units, default selection and kind. Unknown scalar fields
are automatically exposed as technical groups. For new clinical field types,
verify their semantics and units before assigning a friendly meaning. To change
the PDF layout use `core/report.py`; to change both screen and PDF plots use
`core/plotting.py`.

## Tests

From the **parent** of this folder, after activating this environment:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s resmed_therapy_interpretation/tests -v
```

For integration tests on the supplied card as well:

```bash
QT_QPA_PLATFORM=offscreen CPAP_GUI_TEST_ROOT="/path/to/CPAP" \
  python -m unittest discover -s resmed_therapy_interpretation/tests -v
```

Core tests cover clipped calendar weeks/months, ISO years, leap days, rolling
means across boundaries, gaps, unit conversion, age calculation, known card
totals, complete JSON reopening and tamper detection. Qt tests cover linked
checkboxes, unavailable AI, dates/modes, lazy plots, stale-data clearing,
background raw import, JSON export/reopen and PDF export.

Optional `requirements-dev.txt` adds pypdf for exported-PDF text assertions.
Matplotlib/PySide may emit an upstream high-DPI deprecation notice on newer Qt;
it does not affect the generated data or plots.
