"""ASF HyP3 as an external reference (TODO item 12): the owner's starting script, 2026-11-03. Not run yet.

Submits 10 consecutive ~12-day Sentinel-1 IW SLC pairs over Ho Chi Minh City (2024, one ascending path) to HyP3
(GAMMA InSAR, looks 10x2, displacement maps, water mask) and downloads the products. Needs `asf_search` and
`hyp3_sdk`, and the Earthdata login in ~/.netrc (_netrc on Windows).
"""
from collections import Counter

import asf_search as asf
import hyp3_sdk as sdk

aoi = "POLYGON((106.5 10.7, 106.9 10.7, 106.9 10.9, 106.5 10.9, 106.5 10.7))"
results = asf.search(
    platform=asf.PLATFORM.SENTINEL1,
    processingLevel=asf.PRODUCT_TYPE.SLC,
    beamMode=asf.BEAMMODE.IW,
    intersectsWith=aoi,
    start="2024-01-01", end="2024-12-31",
    flightDirection=asf.FLIGHT_DIRECTION.ASCENDING,
)
# keep a single path so that every pair has the same geometry
path = Counter(r.properties["pathNumber"] for r in results).most_common(1)[0][0]
scenes = sorted((r for r in results if r.properties["pathNumber"] == path),
                key=lambda r: r.properties["startTime"])
names = [r.properties["sceneName"] for r in scenes]
print(f"Path {path}: {len(names)} SLC scenes")

hyp3 = sdk.HyP3()                  # Earthdata login from ~/.netrc
jobs = sdk.Batch()
for ref, sec in zip(names[:10], names[1:11], strict=True):      # 10 consecutive pairs (~12 days)
    jobs += hyp3.submit_insar_job(ref, sec, name="hcm-insar", looks="10x2",
                                  include_displacement_maps=True,
                                  apply_water_mask=True)
jobs = hyp3.watch(jobs)            # tens of minutes
jobs.download_files("./hyp3_hcm")
