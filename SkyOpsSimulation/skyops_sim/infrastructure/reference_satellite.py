"""The shared satellite identity and source used by the three desktop tools."""

from dataclasses import dataclass

from skyops_sim.infrastructure.tle import resolve_tle


@dataclass(frozen=True)
class ReferenceSatellite:
    name: str = "TN01A"
    ssc: int = 59705
    tle_url: str = ""
    tle_file: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} · SSC {self.ssc}"

    def load_tle(self, cache_dir):
        return resolve_tle(self.ssc, cache_dir, url=self.tle_url, local_file=self.tle_file)

