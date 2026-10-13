# Getting Started with SSTED Data Acquisition

Quick guide to setting up and using the SSTED radiation detector UI.

## Installation

### 1. Install Python Dependencies

```bash
pip install matplotlib numpy requests
```

### 2. Configure Detector Connection

Edit `ssted_config.json` to point to your detector server:

```json
{
    "detector_url": "http://192.168.1.3:10001/detector_voltage",
    "test": "false"
}
```

**Parameters:**
- `detector_url` — REST endpoint for your RDS detector server
- `test` — Set to `"true"` for mock data (useful for testing without hardware)

### 3. Verify Configuration

Test the connection (optional):
```bash
python get_remote_data.py
```
You should see timestamped voltage readings printed to console. Press `Ctrl+C` to stop.

## Running the UI

Launch with output directory and filename prefix:
```bash
python take_ssted_data.py <output_path> <prefix>
```

**Example:**
```bash
python take_ssted_data.py ./data/ baseline_test
```

Creates a timestamped session. All files saved to `./data/` with names like:
- `baseline_test-2026-10-13-14-30-00.txt`
- `baseline_test-2026-10-13-14-30-00_rolling.png`
- `baseline_test-2026-10-13-14-30-00_full.png`

## Using the UI

### Interface Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ [Save/Exit] [Snapshot]        [Show: Full Dataset] [Scale: Volts]│
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│                         Live Plot                                 │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Button Functions

**Save/Exit**
- Saves complete dataset to `.txt` file (time, raw volts, scaled units)
- Saves rolling-window image (`_rolling.png`)
- Saves full-dataset image (`_full.png`)
- Closes UI and stops acquisition

**Snapshot**
- Captures current rolling-window view to timestamped PNG
- Filename includes window start time (e.g., `_snapshot_245.300s.png`)
- Does not stop acquisition or change view
- Use for documenting transient events during long runs

**Show: Full Dataset / Rolling Window**
- **Rolling Window** (default) — Last 15 minutes of data
- **Full Dataset** — Complete acquisition from start
- Toggle during acquisition without interrupting data collection
- Full dataset uses min/max decimation to preserve spikes

**Scale: Volts / mR/hr**
- **Volts** (default) — Raw detector voltage
- **mR/hr** — Linear calibration (prompts for slope and offset)
- Click to open calibration dialog
- Conversion: `mR/hr = slope × (volts - offset)`
- Raw voltage always saved in output file

### Calibration Dialog

When switching to **mR/hr** mode, enter calibration parameters:

```
┌───────────────────────────────────┐
│  Slope:  [_____150.5______]       │
│  Offset: [_____0.35_______]       │
│                                    │
│  Units will be set to: mR/hour    │
│                                    │
│     [OK]          [Cancel]        │
└───────────────────────────────────┘
```

**Slope** — Conversion factor (volts to mR/hour)
**Offset** — Zero-point adjustment (volts)

Example calibration: If 0.5V = 0 mR/hr and 3.5V = 450 mR/hr:
- Slope = 450 / (3.5 - 0.5) = 150
- Offset = 0.5

## Output File Format

Tab-delimited text file with header:
```
# Time(s)    Voltage(V)    mR/hour
0.000       2.345         284.250
0.501       2.348         284.700
1.002       2.343         283.950
...
```

Columns:
1. **Time** — Seconds since acquisition start
2. **Voltage** — Raw detector reading (always preserved)
3. **Scaled units** — Calibrated value (label matches active scaling)

## Test Mode

Run without detector hardware:
```json
{
    "detector_url": "http://localhost:10001/detector_voltage",
    "test": "true"
}
```

Generates synthetic signal with slow (20-minute) and fast (30-second) oscillations plus noise. Useful for:
- UI development
- Training new users
- Verifying file output format

## Tips

**For long acquisitions:**
- Use **Snapshot** to document interesting events without stopping
- Toggle to **Full Dataset** periodically to check for long-term trends
- Rolling window updates continuously; full view shows overall context

**For calibration:**
- Run test acquisition with known radiation source
- Compare raw voltages to reference dosimeter
- Calculate slope/offset from two-point calibration
- Switch scaling mid-acquisition if needed

**For data analysis:**
- Raw voltage always in column 2 (reprocess with new calibration later)
- Time column allows synchronization with external event logs
- PNG images provide quick visual QC of data quality

## Troubleshooting

**UI doesn't start:**
- Check Python version (3.7+ required)
- Verify `matplotlib` backend supports Tkinter: `python -c "import tkinter"`
- Install system packages: `apt-get install python3-tk` (Linux) or use Anaconda

**No data appearing:**
- Verify detector URL in `ssted_config.json`
- Check network connectivity to detector server
- Try test mode to isolate hardware vs. software issues
- Console shows error messages from acquisition thread

**Plot lag/freezing:**
- Normal for datasets >100,000 points in full view (decimation is automatic)
- Rolling window remains responsive regardless of total dataset size
- Close other applications to free system resources

**Files not saving:**
- Check write permissions on output directory
- Ensure sufficient disk space
- Output path must exist (not created automatically)

## Next Steps

- Review saved data files to verify calibration accuracy
- Establish standard operating procedures for routine monitoring
- Archive raw data files for long-term trend analysis
- Contact RDS support for detector-specific calibration coefficients
