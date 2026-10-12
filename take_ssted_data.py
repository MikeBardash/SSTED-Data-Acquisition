import datetime
import json
import os.path
import sys
import threading
import time
import warnings

import matplotlib
matplotlib.use("TkAgg")

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np

from matplotlib.widgets import Button
from matplotlib.gridspec import GridSpec

# Imports from other files in this package
import get_remote_data as vlt
from scaling_definitions import ScalingDefinition, VoltsScaling, LinearScaling

matplotlib.rcParams["path.simplify"] = False


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
PLOT_INTERVAL_MS        = 500
SKIP_POINTS             = 10
ROLLING_WINDOW_SEC      = 900.00
MAX_FULL_DRAW_POINTS    = 4000
MIN_SAMPLE_INTERVAL_SEC = 0.0
ERROR_RETRY_DELAY_SEC   = 0.1

LINEAR_SCALING_UNITS    = "mR/hour"


# ─────────────────────────────────────────────────────────────────────────────
# Save callback  (Save/Exit button)
# ─────────────────────────────────────────────────────────────────────────────

class SaveCallback:
    def __init__(self, filepath, datasource, scaling: ScalingDefinition):
        self.filepath   = filepath
        self.datasource = datasource
        self.scaling    = scaling
        self.start_time = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

    def save(self, event):
        # ── Save data (complete, undecimated, raw + scaled) ──────────────────
        file_name = os.path.normpath(self.filepath + self.start_time + ".txt")
        x_data, y_raw = self.datasource.get_full_data_snapshot()
        y_scaled = [self.datasource.scaling.scale(v) for v in y_raw]

        with open(file_name, "w") as f:
            f.write(f"# Time(s)\tVoltage(V)\t{self.datasource.scaling.units}\n")
            for xv, yr, ys in zip(x_data, y_raw, y_scaled):
                f.write(f"{xv}\t{yr}\t{ys}\n")

        print(f"Saved {len(x_data)} data points to {file_name}")

        # ── Save rolling-window image ─────────────────────────────────────────
        self.datasource.force_view(show_full=False)
        rolling_img = os.path.normpath(
            self.filepath + self.start_time + "_rolling.png"
        )
        plt.savefig(rolling_img)
        print(f"Saved rolling-window image to {rolling_img}")

        # ── Save full-dataset image ───────────────────────────────────────────
        self.datasource.force_view(show_full=True)
        full_img = os.path.normpath(
            self.filepath + self.start_time + "_full.png"
        )
        plt.savefig(full_img)
        print(f"Saved full-dataset image to {full_img}")

        self.datasource.terminate()


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot callback  (Snapshot button)
#
# Saves a single image of the rolling window as it exists at the moment the
# button is pressed.  The view is restored to whatever the user had before.
#
# Filename format:
#   <prefix><session-timestamp>_snapshot_<window-start-seconds>s.png
#
# where <window-start-seconds> is the time (relative to acquisition start) of
# the oldest sample currently visible in the rolling window.  This makes every
# snapshot filename unique and tells the reader exactly which slice of the
# full dataset the image covers.
# ─────────────────────────────────────────────────────────────────────────────

class SnapshotCallback:
    def __init__(self, filepath, datasource, scaling: ScalingDefinition):
        self.filepath   = filepath
        self.datasource = datasource
        self.scaling    = scaling
        self.start_time = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

    def snapshot(self, event):
        # Remember which view the user was in so we can restore it afterward.
        previous_view_was_full = self.datasource.force_view(show_full=False)

        # Oldest timestamp visible in the rolling window at this instant.
        window_start = self.datasource.get_rolling_window_start()

        img_file = os.path.normpath(
            self.filepath
            + self.start_time
            + f"_snapshot_{window_start:.3f}s.png"
        )
        plt.savefig(img_file)
        print(f"Saved snapshot image to {img_file}")

        # Restore whatever view the user had before the snapshot.
        self.datasource.force_view(show_full=previous_view_was_full)


# ─────────────────────────────────────────────────────────────────────────────
# Main plotter
# ─────────────────────────────────────────────────────────────────────────────

class ProcessPlotter:
    """
    Real-time data acquisition UI.

    Parameters
    ----------
    filepath : str
        Directory + filename prefix for saved files.
    config : dict
        Configuration dictionary containing scaling parameters. 
    scaling : ScalingDefinition, optional
        Scaling object that converts raw volts to display units.
        Defaults to VoltsScaling() — identity, no change to current behaviour.
    """

    def __init__(self, filepath: str, config: dict, scaling: ScalingDefinition | None = None):
        self.filepath   = filepath
        self.config     = config
        self.scaling    = scaling if scaling is not None else VoltsScaling()
        self.start_time = time.monotonic()

        # ── Data buffers (all guarded by _record_lock) ───────────────────────
        # _record_x / _record_y  : complete history, raw voltage
        # _display_x / _display_y: rolling time window, scaled for display
        self._record_x    = []
        self._record_y    = []
        self._display_x   = []
        self._display_y   = []
        self._record_lock = threading.Lock()

        self._last_drawn_count  = -1
        self._show_full_dataset = False

        self.detector = vlt.RemoteVoltage(url=self.config.get("detector_url"), test=self.config.get("test") )

        self._stop_event = threading.Event()
        self._acq_thread = threading.Thread(
            target=self._acquisition_loop,
            name="AcquisitionThread",
            daemon=True,
        )

        self._build_ui()
        self._acq_thread.start()

        self._ani = animation.FuncAnimation(
            self.fig,
            self._update_plot,
            interval=PLOT_INTERVAL_MS,
            blit=False,
            cache_frame_data=False,
        )

        plt.show()          # blocks until window is closed
        self.terminate()    # clean up if user closes window directly

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.fig = plt.figure()
        self.fig.canvas.manager.set_window_title("SSTED Data Acquisition")

        # Five columns: Save/Exit | Snapshot | spacer | Toggle view | Scale toggle
        gs = GridSpec(
            nrows=2, ncols=5,
            height_ratios=[1, 10],
            hspace=0.4,
        )

        # ── Data axes (spans all 5 columns in row 1) ─────────────────────────
        self.ax = self.fig.add_subplot(gs[1, :])
        (self.line,) = self.ax.plot([], [], "-r", linewidth=1)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel(f"{self.scaling.units}")

        # ── Button axes (row 0) ───────────────────────────────────────────────
        ax_save     = self.fig.add_subplot(gs[0, 0])
        ax_snapshot = self.fig.add_subplot(gs[0, 1])
        ax_spacer   = self.fig.add_subplot(gs[0, 2])   # empty spacer
        ax_toggle   = self.fig.add_subplot(gs[0, 3])
        ax_scale    = self.fig.add_subplot(gs[0, 4])
        ax_spacer.set_visible(False)

        # Save/Exit button
        self._save_button = Button(
            ax_save, "Save/Exit", color="w", hovercolor="#cceeff"
        )
        self._save_button.on_clicked(
            SaveCallback(self.filepath, self, self.scaling).save
        )

        # Snapshot button
        self._snapshot_button = Button(
            ax_snapshot, "Snapshot", color="w", hovercolor="#fff0cc"
        )
        self._snapshot_button.on_clicked(
            SnapshotCallback(self.filepath, self, self.scaling).snapshot
        )

        # View toggle button
        self._toggle_button = Button(
            ax_toggle, "Show: Full Dataset", color="w", hovercolor="#ccffcc"
        )
        self._toggle_button.on_clicked(self._toggle_view)

        # Scale toggle button
        self._scale_button = Button(
            ax_scale, "Scale: Volts", color="w", hovercolor="#ffccff"
        )
        self._scale_button.on_clicked(self._toggle_scale)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.fig.tight_layout()

        self._update_title(total=0, shown=0)

    # ─────────────────────────────────────────────────────────────────────────
    # View toggle
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_view(self, event):
        self._show_full_dataset = not self._show_full_dataset

        if self._show_full_dataset:
            self._toggle_button.label.set_text("Show: Rolling Window")
            new_color = "#ccffcc"
        else:
            self._toggle_button.label.set_text("Show: Full Dataset")
            new_color = "w"

        self._toggle_button.color = new_color
        self._toggle_button.ax.set_facecolor(new_color)

        self._refresh_plot()
        self.fig.canvas.draw_idle()

    # ─────────────────────────────────────────────────────────────────────────
    # Scale toggle helper  (tkinter dialog, runs on the main thread)
    # ─────────────────────────────────────────────────────────────────────────
    def _ask_linear_params(self):
        """
        Open a small modal dialog to collect slope and offset for LinearScaling.

        Returns
        -------
        (float, float) if the user clicked OK and both values are valid floats.
        None           if the user cancelled or entered non-numeric text.
        """
        import tkinter as tk
        from tkinter import messagebox

        result = {}

        dialog = tk.Toplevel()
        dialog.title("Linear Scaling Parameters")
        dialog.resizable(False, False)
        dialog.grab_set()           # make it modal

        tk.Label(dialog, text="Slope:").grid(
            row=0, column=0, padx=10, pady=8, sticky="e"
        )
        slope_var = tk.StringVar()
        tk.Entry(dialog, textvariable=slope_var, width=16).grid(
            row=0, column=1, padx=10, pady=8
        )

        tk.Label(dialog, text="Offset:").grid(
            row=1, column=0, padx=10, pady=8, sticky="e"
        )
        offset_var = tk.StringVar()
        tk.Entry(dialog, textvariable=offset_var, width=16).grid(
            row=1, column=1, padx=10, pady=8
        )

        tk.Label(
            dialog,
            text=f"Units will be set to:  {LINEAR_SCALING_UNITS}",
            fg="grey"
        ).grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 8))

        def _on_ok():
            try:
                result["slope"]  = float(slope_var.get())
                result["offset"] = float(offset_var.get())
                dialog.destroy()
            except ValueError:
                messagebox.showerror(
                    "Invalid input",
                    "Slope and offset must both be numbers.",
                    parent=dialog,
                )

        def _on_cancel():
            dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(0, 10))
        tk.Button(btn_frame, text="OK",     width=8, command=_on_ok    ).pack(side="left",  padx=6)
        tk.Button(btn_frame, text="Cancel", width=8, command=_on_cancel).pack(side="right", padx=6)

        dialog.wait_window()
        return (result["slope"], result["offset"]) if "slope" in result else None

    # ─────────────────────────────────────────────────────────────────────────
    # Scale toggle
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_scale(self, event):
        """
        Switch between VoltsScaling and LinearScaling.

        When switching to LinearScaling a modal dialog collects the slope and
        offset.  If the user cancels the dialog the scaling is left unchanged.
        """
        if isinstance(self.scaling, LinearScaling):
            # ── Switch back to raw Volts ──────────────────────────────────────
            self.scaling = VoltsScaling()
            self._scale_button.label.set_text("Scale: Volts")
            self._scale_button.color = "w"
            self._scale_button.ax.set_facecolor("w")
            self.ax.set_ylabel(self.scaling.units)
            self._rebuild_display_buffer()
            self._refresh_plot()
            self.fig.canvas.draw_idle()
            print("Scaling switched to Volts.")
        else:
            # ── Collect parameters then switch to LinearScaling ───────────────
            params = self._ask_linear_params()
            if params is None:
                print("Linear scaling cancelled — scaling unchanged.")
                return

            slope, offset = params
            self.scaling = LinearScaling(
                slope=slope, offset=offset, units=LINEAR_SCALING_UNITS
            )
            self._scale_button.label.set_text("Scale: mR/hr")
            new_color = "#ffccff"
            self._scale_button.color = new_color
            self._scale_button.ax.set_facecolor(new_color)
            self.ax.set_ylabel(self.scaling.units)
            self._rebuild_display_buffer()
            self._refresh_plot()
            self.fig.canvas.draw_idle()
            print(
                f"Scaling switched to LinearScaling — "
                f"slope={slope}, offset={offset}, "
                f"units={LINEAR_SCALING_UNITS}."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Rebuild the rolling-window display buffer after a scaling change
    # ─────────────────────────────────────────────────────────────────────────
    def _rebuild_display_buffer(self):
        """
        Recompute _display_y from the stored raw _record_y values using the
        current scaling, and repopulate _display_x / _display_y to match the
        rolling window that would have been built had this scaling been active
        from the start.

        Must be called with the _record_lock *not* held (it acquires the lock
        internally).
        """
        with self._record_lock:
            if not self._record_x:
                return

            latest  = self._record_x[-1]
            cutoff  = latest - ROLLING_WINDOW_SEC

            new_display_x = []
            new_display_y = []
            for t, v in zip(self._record_x, self._record_y):
                if t >= cutoff:
                    new_display_x.append(t)
                    new_display_y.append(self.scaling.scale(v))

            self._display_x = new_display_x
            self._display_y = new_display_y

            # Force a full redraw on the next animation tick.
            self._last_drawn_count = -1

    # ─────────────────────────────────────────────────────────────────────────
    # Forced view switch (used by SaveCallback and SnapshotCallback)
    # ─────────────────────────────────────────────────────────────────────────
    def force_view(self, show_full: bool) -> bool:
        """
        Switch to the requested view and perform a synchronous redraw so that
        plt.savefig() captures the correct content immediately afterward.

        Parameters
        ----------
        show_full : bool
            True  → full-dataset view
            False → rolling-window view

        Returns
        -------
        bool
            The view state that was active *before* this call, so the caller
            can restore it with a second call to force_view() if desired.
        """
        previous = self._show_full_dataset
        self._show_full_dataset = show_full

        if show_full:
            self._toggle_button.label.set_text("Show: Rolling Window")
            self._toggle_button.color = "#ccffcc"
            self._toggle_button.ax.set_facecolor("#ccffcc")
        else:
            self._toggle_button.label.set_text("Show: Full Dataset")
            self._toggle_button.color = "w"
            self._toggle_button.ax.set_facecolor("w")

        self._refresh_plot()
        self.fig.canvas.draw()

        return previous

    # ─────────────────────────────────────────────────────────────────────────
    # Acquisition loop  (runs in its own thread)
    # ─────────────────────────────────────────────────────────────────────────
    def _acquisition_loop(self):
        skip_remaining = SKIP_POINTS

        while not self._stop_event.is_set():
            t_before = time.monotonic()

            try:
                volts = self.detector.get_remote_voltage()
            except Exception as exc:
                print(f"[AcquisitionThread] ERROR: {exc}", flush=True)
                self._stop_event.wait(ERROR_RETRY_DELAY_SEC)
                continue

            t_after   = time.monotonic()
            timestamp = 0.5 * (t_before + t_after) - self.start_time

            if skip_remaining > 0:
                skip_remaining -= 1
            else:
                scaled_volts = self.scaling.scale(volts)

                with self._record_lock:
                    self._record_x.append(timestamp)
                    self._record_y.append(volts)

                    self._display_x.append(timestamp)
                    self._display_y.append(scaled_volts)

                    # Prune samples older than the rolling window.
                    cutoff = timestamp - ROLLING_WINDOW_SEC
                    while self._display_x and self._display_x[0] < cutoff:
                        self._display_x.pop(0)
                        self._display_y.pop(0)

            if MIN_SAMPLE_INTERVAL_SEC > 0:
                remaining = MIN_SAMPLE_INTERVAL_SEC - (
                    time.monotonic() - t_before
                )
                if remaining > 0:
                    self._stop_event.wait(remaining)

    # ─────────────────────────────────────────────────────────────────────────
    # Plot helpers
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _decimate_minmax(x, y, max_points):
        """
        Reduce (x, y) to at most ~max_points while preserving every local
        minimum and maximum so spikes are never lost.
        """
        n = len(x)
        if n <= max_points:
            return np.asarray(x), np.asarray(y)

        x = np.asarray(x)
        y = np.asarray(y)

        step   = int(np.ceil(n / (max_points // 2)))
        usable = (n // step) * step

        yb      = y[:usable].reshape(-1, step)
        base    = np.arange(0, usable, step)
        idx_min = base + yb.argmin(axis=1)
        idx_max = base + yb.argmax(axis=1)
        idx_list = [idx_min, idx_max]

        if usable < n:
            idx_list.append(np.arange(usable, n))

        idx = np.unique(np.concatenate(idx_list))
        return x[idx], y[idx]

    def _update_title(self, total, shown):
        if self._show_full_dataset:
            if shown < total:
                mode = (
                    f"Full dataset  ({total} pts, "
                    f"drawing {shown} min/max-decimated)"
                )
            else:
                mode = f"Full dataset  ({total} pts)"
        else:
            mode = (
                f"Rolling window  {ROLLING_WINDOW_SEC:.0f}s  "
                f"(showing {shown} pts of {total} total)"
            )
        self.ax.set_title(f"SSTED Real-Time Acquisition — {mode}")

    def _refresh_plot(self):
        with self._record_lock:
            total = len(self._record_x)
            if self._show_full_dataset:
                x_vals = list(self._record_x)
                y_vals = [self.scaling.scale(v) for v in self._record_y]
            else:
                x_vals = list(self._display_x)
                y_vals = list(self._display_y)
            self._last_drawn_count = total

        if self._show_full_dataset:
            x_vals, y_vals = self._decimate_minmax(
                x_vals, y_vals, MAX_FULL_DRAW_POINTS
            )

        self.line.set_data(x_vals, y_vals)

        if len(y_vals) > 0:
            y_min = float(np.min(y_vals))
            y_max = float(np.max(y_vals))
            x_min = float(np.min(x_vals))
            x_max = float(np.max(x_vals))

            y_margin = (y_max - y_min) * 0.05 if y_max != y_min else 0.5
            x_margin = (x_max - x_min) * 0.05 if x_max != x_min else 0.5

            self.ax.set_xlim(x_min - x_margin, x_max + x_margin)
            self.ax.set_ylim(y_min - y_margin, y_max + y_margin)
        else:
            self.ax.set_xlim(0, 1)
            self.ax.set_ylim(0, 1)

        self._update_title(total=total, shown=len(x_vals))

    # ─────────────────────────────────────────────────────────────────────────
    # FuncAnimation callback  (main thread)
    # ─────────────────────────────────────────────────────────────────────────
    def _update_plot(self, _frame):
        with self._record_lock:
            count = len(self._record_x)
        if count != self._last_drawn_count:
            self._refresh_plot()

    # ─────────────────────────────────────────────────────────────────────────
    # Public helpers
    # ─────────────────────────────────────────────────────────────────────────
    def get_full_data_snapshot(self):
        """Return (x_times, y_raw_volts) for the complete unscaled record."""
        with self._record_lock:
            return list(self._record_x), list(self._record_y)

    def get_rolling_window_start(self) -> float:
        """
        Return the timestamp (seconds since acquisition start) of the oldest
        sample currently in the rolling window.

        Returns 0.0 if the rolling window is empty.
        """
        with self._record_lock:
            return self._display_x[0] if self._display_x else 0.0

    def terminate(self):
        self._stop_event.set()
        self._acq_thread.join(timeout=2.0)
        plt.close("all")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) != 3:
        print("Usage: python take_ssted_data.py <path> <prefix>")
        sys.exit(1)

    data_dir = sys.argv[1]
    prefix   = sys.argv[2]
    file_name_prefix = os.path.join(data_dir, prefix + "-")

    with open( "ssted_config.json", "r") as f:
        config = json.load(f)

    # ── Default: identity scaling (raw volts, behaviour unchanged) ───────────
    ProcessPlotter(file_name_prefix, config )


if __name__ == "__main__":
    main()