# scaling_definitions.py
"""
Scaling definitions for the SSTED data acquisition UI.

This module provides the ScalingDefinition abstract base class and concrete
subclasses that convert raw voltage values (as returned by the hardware) into
display and save units.

Usage
-----
Import the desired class and pass an instance to ProcessPlotter:

    from scaling_definitions import MillivoltsScaling
    ProcessPlotter(file_name_prefix, scaling=MillivoltsScaling())

Creating a custom scaling
-------------------------
Subclass ScalingDefinition and implement the two required attributes:

    class MyScaling(ScalingDefinition):
        units = "my_units"

        def scale(self, y):
            return y * my_conversion_factor
"""


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base class
# ─────────────────────────────────────────────────────────────────────────────

class ScalingDefinition:
    """
    Abstract base for Y-axis scaling.

    Subclass this to inject a custom unit conversion into ProcessPlotter.
    The raw voltage is always preserved in _record_y so saves contain the
    original hardware values alongside the scaled values.

    Attributes
    ----------
    units : str
        Human-readable label for the scaled unit.  Used as the Y-axis label
        and as the column header in saved data files.

    Methods
    -------
    scale(y)
        Convert a raw voltage value (or array of values) to display units.

    Subclass example — millivolts:

        class MillivoltsScaling(ScalingDefinition):
            units = "mV"

            def scale(self, y):
                return y * 1000.0
    """

    units: str = "Volts"

    def scale(self, y):
        """
        Scale *y* (a float or numpy array of raw volts) to display/save units.

        Parameters
        ----------
        y : float | numpy.ndarray
            Raw voltage value(s) as returned by the hardware.

        Returns
        -------
        float | numpy.ndarray
            Scaled value(s) in self.units.

        Raises
        ------
        NotImplementedError
            Always raised by this base implementation; subclasses must
            override this method.
        """
        raise NotImplementedError("Subclasses must implement scale()")


# ─────────────────────────────────────────────────────────────────────────────
# Concrete subclasses
# ─────────────────────────────────────────────────────────────────────────────

class VoltsScaling(ScalingDefinition):
    """
    Default (identity) scaling — Y values are displayed as-is in Volts.

    Using this class leaves every plot and saved file identical to the
    behaviour before scaling support was added.
    """

    units = "Volts"

    def scale(self, y):
        """Return *y* unchanged."""
        return y

class LinearScaling(ScalingDefinition):
    """
    General-purpose linear scaling of the form:

        scaled = slope * (x - offset)

    Parameters
    ----------
    slope : float
        Multiplicative factor applied to the raw voltage.
    offset : float
        Additive offset applied to the incoming x value to offset the voltage that should represent the "Zero" value for the linear transformation.
    units : str
        Label for the resulting unit (e.g. "°C", "Pa", "A").

    Example
    -------
    Convert a 0–5 V signal that represents 0–100 °C:

        temp_scaling = LinearScaling(slope=20.0, offset=0.0, units="°C")
        ProcessPlotter(file_name_prefix, scaling=temp_scaling)
    """

    def __init__(self, slope: float, offset: float, units: str):
        self.slope  = slope
        self.offset = offset
        self.units  = units

    def scale(self, x):
        """Apply the linear transformation slope * (x - offset)."""
        return self.slope * (x - self.offset)
