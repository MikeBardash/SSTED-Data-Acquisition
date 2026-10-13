# SSTED Data Acquisition

## Overview

Python-based real-time data acquisition UI for RDS/Mike Bardash proprietary radiation detector systems. Acquires voltage readings from remote Solid State Tissue Equivalent Detectors (SSTEDs) and provides live visualization with configurable scaling and data export.

## Features

- **Real-time plotting** — Live visualization with 500ms refresh rate
- **Dual view modes** — Toggle between rolling 15-minute window and full dataset
- **Flexible scaling** — Display raw volts or apply linear calibration (e.g., mR/hour)
- **Snapshot capability** — Save timestamped rolling-window images during acquisition
- **Data export** — Save complete dataset (raw + scaled) with both view images on exit
- **Test mode** — Built-in mock signal generator for development/testing
- **Min/max decimation** — Efficient rendering of large datasets without losing spikes

## Requirements

- Python 3.7+
- `matplotlib` — UI and plotting
- `numpy` — Data processing
- `requests` — Network communication with detector server

Install dependencies:
```bash
pip install matplotlib numpy requests
```

## Quick Start

1. Configure detector endpoint in `ssted_config.json`:
   ```json
   {
       "detector_url": "http://192.168.1.3:10001/detector_voltage",
       "test": "false"
   }
   ```

2. Run the acquisition UI:
   ```bash
   python take_ssted_data.py <output_directory> <filename_prefix>
   ```

Example:
```bash
python take_ssted_data.py ./data/ experiment_01
```

For detailed usage instructions, see [GettingStarted.md](GettingStarted.md).

## Project Structure

```
.
├── take_ssted_data.py          # Main UI and acquisition loop
├── get_remote_data.py          # Remote detector interface
├── scaling_definitions.py      # Unit conversion classes
└── ssted_config.json           # Detector configuration
```

## Output Files

All files are timestamped with session start time (`YYYY-MM-DD-HH-MM-SS`):

- `<prefix>-<timestamp>.txt` — Tab-delimited data (time, raw volts, scaled units)
- `<prefix>-<timestamp>_rolling.png` — Final rolling-window view
- `<prefix>-<timestamp>_full.png` — Complete dataset plot
- `<prefix>-<timestamp>_snapshot_<window_start>s.png` — On-demand snapshots

## Hardware Requirements

- Network connectivity to RDS detector server (default: port 10001)
- Compatible SSTED detector hardware with REST API endpoint
