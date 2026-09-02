from __future__ import annotations

import pandas as pd

from stk_api.constraints import STKConstraints
from stk_api.objects import STKObjectsAPI as STKObjects
from stk_api.typelib import com_float_array, instance_name, load_stk_modules, qi


class STKCoverage:
    @staticmethod
    def create_coverage_grid_seed(scenario, name: str, min_elevation_deg: float):
        seed = STKObjects.create_facility(scenario, name, 0, 0, 0)
        STKConstraints.set_min_elevation(seed, min_elevation_deg)
        print(f"[覆盖] Grid Seed: {name}, min elevation = {min_elevation_deg:.1f} deg")
        return seed

    @staticmethod
    def create_global_coverage(scenario, name: str, resolution_deg: float, chain, grid_seed):
        stk_objects, _ = load_stk_modules()
        coverage = qi(
            scenario.Children.New(stk_objects.eCoverageDefinition, name),
            stk_objects.IAgCoverageDefinition,
        )
        coverage.Grid.BoundsType = stk_objects.eBoundsGlobal
        resolution = qi(coverage.Grid.Resolution, stk_objects.IAgCvResolutionLatLon)
        resolution.LatLon = resolution_deg
        coverage.PointDefinition.GridClass = stk_objects.eGridClassFacility
        coverage.PointDefinition.UseGridSeed = True
        coverage.PointDefinition.SeedInstance = f"Facility/{instance_name(grid_seed)}"
        coverage.AssetList.Add(f"Chain/{instance_name(chain)}")
        coverage.Graphics.Static.IsPointsVisible = False
        coverage.ComputeAccesses()
        print(
            f"[覆盖] Coverage computed: {name}, {resolution_deg:.2f} deg, "
            f"grid seed = {instance_name(grid_seed)}"
        )
        return coverage

    @staticmethod
    def create_coverage_time_fom(coverage, name: str, min_assets: int):
        stk_objects, _ = load_stk_modules()
        fom = qi(coverage.Children.New(stk_objects.eFigureOfMerit, name), stk_objects.IAgFigureOfMerit)
        fom.SetDefinitionType(stk_objects.eFmCoverageTime)
        definition = qi(fom.Definition, stk_objects.IAgFmDefCompute)
        definition.SetComputeType(stk_objects.eTotalTimeAbove)
        compute = qi(definition.Compute, stk_objects.IAgFmDefDataMinAssets)
        compute.MinAssets = min_assets
        print(f"[品质因数] Coverage Time created: {name}")
        return fom

    @staticmethod
    def read_coverage_time(fom) -> pd.DataFrame:
        dp = fom.DataProviders.Item("Value By Point").Exec()
        lat = com_float_array(dp.DataSets.GetDataSetByName("Latitude").GetValues())
        lon = com_float_array(dp.DataSets.GetDataSetByName("Longitude").GetValues())
        time_sec = com_float_array(dp.DataSets.GetDataSetByName("FOM Value").GetValues())
        return pd.DataFrame(
            {
                "LatitudeDeg": lat,
                "LongitudeDeg": lon,
                "TimeSec": time_sec,
                "TimeHour": time_sec / 3600.0,
            }
        )
