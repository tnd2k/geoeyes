"""Small value types used across packages."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from geoeyes.core.errors import ConfigError


class OrbitDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"

    @classmethod
    def parse(cls, value: str) -> OrbitDirection:
        v = str(value).strip().lower()
        aliases = {"asc": cls.ASCENDING, "a": cls.ASCENDING, "desc": cls.DESCENDING, "dsc": cls.DESCENDING,
                   "d": cls.DESCENDING}
        if v in aliases:
            return aliases[v]
        try:
            return cls(v)
        except ValueError:
            raise ConfigError(f"unknown orbit direction {value!r}") from None

    @property
    def short(self) -> str:
        return "asc" if self is OrbitDirection.ASCENDING else "desc"


class LookSide(StrEnum):
    RIGHT = "right"
    LEFT = "left"


@dataclass(frozen=True)
class BBox:
    """Geographic box in degrees (EPSG:4326): west, south, east, north."""

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self):
        if not (-180 <= self.west < self.east <= 180):
            raise ConfigError(f"bbox longitudes must satisfy -180 <= west < east <= 180, got {self}")
        if not (-90 <= self.south < self.north <= 90):
            raise ConfigError(f"bbox latitudes must satisfy -90 <= south < north <= 90, got {self}")

    @classmethod
    def from_sequence(cls, values) -> BBox:
        w, s, e, n = (float(v) for v in values)
        return cls(w, s, e, n)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)

    def buffered(self, deg: float) -> BBox:
        return BBox(max(self.west - deg, -180), max(self.south - deg, -90),
                    min(self.east + deg, 180), min(self.north + deg, 90))

    def contains(self, lon: float, lat: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north
