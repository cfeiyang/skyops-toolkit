"""STK Coverage Definition、Grid Seed 和 Figure Of Merit 封装。"""

from __future__ import annotations

import pandas as pd
from agi.stk12.stkobjects import (
    AgECvBounds,#type:ignore
    AgECvGridClass,#type:ignore
    AgEFmCompute,#type:ignore
    AgEFmDefinitionType,#type:ignore
    AgESTKObjectType,#type:ignore
)

from stk_simulation.stk.constraints import STKConstraints
from stk_simulation.stk.data import instance_name, numeric_dataset
from stk_simulation.stk.objects import STKObjects


class STKCoverage:
    @staticmethod
    def create_coverage_grid_seed(
        scenario, name: str, min_elevation_deg: float
    ):
        seed = STKObjects.create_facility(scenario, name, 0, 0, 0)
        STKConstraints.set_min_elevation(seed, min_elevation_deg)
        print(
            f"[覆盖] Grid Seed: {name}, "
            f"min elevation = {min_elevation_deg:.1f} deg"
        )
        return seed

    @staticmethod
    def create_global_coverage(
        scenario,
        name: str,
        resolution_deg: float,
        chains,
        grid_seed,
    ):
        coverage = scenario.Children.New(AgESTKObjectType.eCoverageDefinition, name)
        coverage.Grid.BoundsType = AgECvBounds.eBoundsGlobal
        coverage.Grid.Resolution.LatLon = resolution_deg
        coverage.PointDefinition.GridClass = AgECvGridClass.eGridClassFacility
        coverage.PointDefinition.UseGridSeed = True
        coverage.PointDefinition.SeedInstance = (
            f"Facility/{instance_name(grid_seed)}"
        )
        if not isinstance(chains, (list, tuple)):
            chains = [chains]
        for chain in chains:
            coverage.AssetList.Add(f"Chain/{instance_name(chain)}")
        coverage.Graphics.Static.IsPointsVisible = False
        coverage.ComputeAccesses()
        print(
            f"[覆盖] Coverage computed: {name}, {resolution_deg:.2f} deg, "
            f"assets = {len(chains)}, grid seed = {instance_name(grid_seed)}"
        )
        return coverage

    @staticmethod
    def create_coverage_time_fom(coverage, name: str, min_assets: int):
        fom = coverage.Children.New(AgESTKObjectType.eFigureOfMerit, name)
        fom.SetDefinitionType(AgEFmDefinitionType.eFmCoverageTime)
        fom.Definition.SetComputeType(AgEFmCompute.eTotalTimeAbove)
        fom.Definition.Compute.MinAssets = min_assets
        print(f"[品质因数] Coverage Time created: {name}")
        return fom

    @staticmethod
    def read_coverage_time(fom) -> pd.DataFrame:
        result = fom.DataProviders.Item("Value By Point").Exec()
        latitude = numeric_dataset(result, "Latitude")
        longitude = numeric_dataset(result, "Longitude")
        time_seconds = numeric_dataset(result, "FOM Value")
        return pd.DataFrame(
            {
                "LatitudeDeg": latitude,
                "LongitudeDeg": longitude,
                "TimeSec": time_seconds,
                "TimeHour": time_seconds / 3600.0,
            }
        )
