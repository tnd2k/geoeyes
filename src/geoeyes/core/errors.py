"""Exception hierarchy. Library code raises these instead of printing and calling ``sys.exit``."""


class GeoEyesError(Exception):
    """Base class of every error raised on purpose by GeoEyes."""


class ConfigError(GeoEyesError):
    """Invalid or inconsistent project configuration."""


class DataError(GeoEyesError):
    """Input data missing, unreadable or inconsistent with the metadata."""


class SensorError(DataError):
    """Product not recognised or not supported by a sensor reader."""


class StoreError(GeoEyesError):
    """A store (stack, state, points, raster, manifest) cannot be read or written."""


class PhaseError(GeoEyesError):
    """A processing phase failed; ``phase`` names it for the run record."""

    def __init__(self, phase: str, message: str):
        super().__init__(f"{phase}: {message}")
        self.phase = phase


class LockedError(GeoEyesError):
    """Another run holds the lock of this project/track."""
