> Bản dịch tiếng Việt của [`docs/en/architecture/migration-map.md`](../../en/architecture/migration-map.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# GeoEyes — Bản đồ di chuyển (tệp cũ → vị trí mới)

> Mỗi tệp/thư mục hiện có ứng với đúng một dòng: chuyển đi đâu, hay bị xoá. Kiến trúc mục tiêu: [`ARCHITECTURE.md`](ARCHITECTURE.md).
> Đường dẫn đích tính từ `src/geoeyes/`, trừ khi bắt đầu bằng `apps/`, `third_party/`, `tests/`, `docs/`, `scripts/` hoặc `$WS` (= `$GEOEYES_WORKSPACE`).
>
> **Hành động**: `move` (chuyển gần như nguyên trạng) · `split` (tách thành nhiều module) · `merge` (gộp nhiều nguồn làm một) · `port` (viết lại theo hợp đồng mới, giữ thuật toán) · `replace` (thay bằng cơ chế mới) · `delete` (xoá) · `legacy` (chỉ giữ trong `io/legacy` để đọc dữ liệu cũ).
>
> Cột **Phase** = pha trong TODO.md phụ trách mục đó.

---

## 1. Thư mục gốc

| Hiện tại | Đích | Hành động | Phase | Ghi chú |
|---|---|---|---|---|
| `vinsar.py` | `controller/runner.py`, `controller/guard.py`, `cli/main.py` | split | 3 | Không giữ shim |
| `phasingpy.py` | `postprocess/*`, `products/*`, `export/*` (chi tiết §6) | split | 6 | |
| `__init__.py` (gốc) | — | delete | 1 | |
| `requirements.txt`, `environment.yml` | `pyproject.toml` (+ `environment.yml` tối giản cho conda) | replace | 1 | |
| `.env`, `.env.example` | `.env.example` với các biến `GEOEYES_*` (§14.2) | replace | 9 | tệp `.env` thật không để trong repo |
| `.gitignore`, `.gitattributes` | giữ, cập nhật | move | 9 | |
| `README.md` | viết lại cho GeoEyes | port | 9 | |
| `.githooks/pre-commit` | giữ (`scripts/check_user_paths.py`) | move | 9 | |
| `.github/` | giữ, đổi tên/cập nhật biến | move | 9 | |
| `.vscode/launch.json` | cập nhật mục `geoeyes` | port | 9 | |
| `.claude/settings.local.json` | dọn dẹp (URL SharePoint, đường dẫn cá nhân, `VINSAR_*`) | port | 9 | |
| `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.cache/` | — | delete | 1 | `.cache/locks`, `jobs` → `$WS` |
| `data/`, `process/`, `results/`, `logs/` | `$WS/archive`, `$WS/projects/<p>/…` | replace | 2/7 | dữ liệu, để ngoài repo |
| `control/<project>/{in,control,config}.json` | `$WS/projects/<p>/project.toml` + `.state/state.json` | replace | 2 | `geoeyes migrate config` |
| `notebooks/` | `notebooks/` (cập nhật import) | move | 9 | `water_mask.ipynb` → `docs/` hoặc `notebooks/ml/` |
| `dev/` | — (cần thì giữ ở ngoài repo) | delete | 1 | script nháp + dữ liệu (zip S1, PNG, `_sct_extract*`) |

## 2. `config/`

| Hiện tại | Đích | Hành động | Phase |
|---|---|---|---|
| `config/parser.py` (1718 dòng) | `config/loader.py` (nạp/ghi đè), `workspace/layout.py` (đường dẫn), `workspace/project.py` (`Initialize` → tạo không gian làm việc), `processing/stack/snap/gpt.py` (hàm trợ giúp gpt) | split | 2 |
| `config/template.json` | `config/schema.py` (giá trị mặc định nằm trong schema) | replace | 2 |
| `config/presets/{s1,tsx,capella,csk}.json` | `config/presets/{sentinel1,terrasar_x,capella,cosmo_skymed}.toml` + `alos.toml` (mới) | port | 2 |
| `config/control.json` | `[pipeline]` trong schema | replace | 2 |
| `config/model_temp.json` | kiểm tra mục đích → đưa vào schema hoặc xoá | ? | 2 |
| `config/README.md` | `docs/user/configuration.md` | port | 9 |
| `config/project.conf` (do StampsPrep sinh ra) | — | delete | 4 |

## 3. `modules/snap2stamps/` → `processing/acquire`, `network`, `stack`

| Hiện tại | Đích | Hành động | Phase |
|---|---|---|---|
| `__init__.py` (`SNAP2STAMPSManager`, `run`) | `controller/phases/*` | replace | 3 |
| `s1/__init__.py` (`run_stages`, các hook merge/synth) | `controller/phases/*`; hook → `network/pairs.py`, `postprocess/geometry/merge_subswath.py` | split | 3–4 |
| `s1/bin/_1_download.py` | `sensors/sentinel1/search.py`, `processing/acquire/download.py` | split | 4 |
| `s1/bin/_2_master_sel.py` | `network/reference.py`, `geometry/orbit.py`, `geometry/baseline.py` | merge | 4 |
| `s1/bin/_3_find_bursts.py` (stsa) | `sensors/sentinel1/bursts.py` (đọc trực tiếp annotation) | port | 4 |
| `s1/bin/_4_splitting_master.py` | — (không nơi nào gọi) | delete | 4 |
| `s1/bin/_5_splitting_slaves.py` | engine snap: `stack/snap/gpt.py`; native: `sensors/sentinel1/safe.py` + `orbits.py` | split | 4/5 |
| `s1/bin/_6_coreg_ifg_topsar.py` | snap: `stack/snap/`; native: `stack/native/{coregister,tops,interferogram}.py` | split | 4/5 |
| `s1/bin/_7_stamps_export.py` | snap: `stack/snap/importer.py` (DIMAP → Zarr); HoA → `geometry/baseline.py` | port | 4 |
| `s1/bin/_8_find_optimal_patches.py` | `selection/tiles.py` | port | 4 |
| `s1/bin/_9_0_stamps_prep_py.py` | `controller/phases/select_candidates.py` | replace | 4 |
| `s1/bin/_shared_repo.py` | `processing/acquire/archive_index.py` (lưu ảnh gốc, không lưu các bản split) | port | 4 |
| `s1/bin/_burst_crop.py` | `sensors/sentinel1/bursts.py` | merge | 4 |
| `tsx/bin/_1_master_sel.py` | `sensors/terrasar_x/annotation.py`, `network/reference.py` | split | 4 |
| `tsx/bin/_2_coreg_ifg.py` | `stack/snap/` (chuyển tiếp) | port | 4 |
| `tsx/bin/_3_stamps_export.py`, `_4_stamps_prep_py.py` | giống S1 | merge | 4 |
| `csk/bin/_1_subset.py` | `sensors/cosmo_skymed/archive.py` (giải nén) ; subset → engine | split | 4 |
| `csk/bin/_2_master_sel.py` | `sensors/cosmo_skymed/hdf5.py`, `network/reference.py`, `geometry/orbit.py` | split | 4 |
| `csk/bin/_3_coreg_ifg.py` | `stack/snap/` → `stack/native/` | port | 4/5 |
| `csk/bin/_4_stamps_export.py`, `_5_stamps_prep_py.py` | giống S1 | merge | 4 |
| `capella/__init__.py` (`CapellaStacCollection`, `CapellaSharedRepo`, `CapellaSceneLayout`) | `sensors/capella/stac.py`, `acquire/archive_index.py` | split | 4 |
| `capella/bin/_1_master_sel.py` | `sensors/capella/slc.py` (JSON mở rộng), `network/reference.py`, `network/pairs.py` | split | 4 |
| `capella/bin/_2_coreg_ifg.py` (7144 dòng) | snap: `stack/snap/`; `PythonTerrainCorrection`, `RangeDopplerGeocoding` → `geometry/rdr2geo.py`, `geo2rdr.py`; `OpenTopographyDem` → `geometry/dem.py`; SBSCC → `stack/native/filters.py` | split | 4/5 |
| `capella/bin/_3_stamps_export.py` | — (Capella không đi qua StaMPS — ADR-020); HoA/góc tới cục bộ nếu cần → `geometry/baseline.py`, `GEOMETRY` | delete | 4 |
| `capella/bin/_4_stamps_prep.py` | — ; logic `write_bperp_and_bpar_in_for_stack` → `geometry/baseline.py` nếu cần | delete | 4 |
| `*/graphs/*.xml` | `stack/snap/graphs/` (chỉ các graph còn dùng) ; `tosubset_model.xml`, `tosubset*.xml` của capella, `export2run.xml` | move / delete | 4 |
| Trùng lặp: `_interpolate_orbit` ×4, `_compute_median_hoa` ×4, `_cleanup_incomplete_dimap` ×4, `_write_orbit_file` ×2, `_maybe_synthesize_redundant_pairs` ×3, `organize_slaves_structure` ×2 | một bản duy nhất trong `geometry/` / `network/` / `stack/snap/` | merge | 4 |

## 4. `modules/python/` → `processing/`

| Hiện tại | Đích | Hành động | Phase |
|---|---|---|---|
| `s1/stamps/flow.py` | **nền tảng** của `processing/ps/*` (steps, driver, sbas, closure, merge) | split | 4 |
| `capella/stamps/flow.py` | — Capella dùng `ps_lite` (ADR-020); nội dung ≈ `csk/stamps/flow.py` (khác nhau 71 dòng) | delete | 4 |
| `csk/stamps/flow.py` | phần khác s1 (bộ lọc trước goldstein — bỏ wavelet/FAMM, không port; trọng số amb, `_build_ifg_coh_grid`, `_boxcar_filt_batch_gpu`, `_regularize_k_ps_spatial`) → tham số trong `ps/steps/s6_unwrap.py`, `s2_gamma.py`; nhiễu rho/weed → `SensorProfile.defaults` | merge | 4 |
| `tsx/stamps/flow.py` | lấy `_destripe_unwrapped_grid`, `_aps_fill_nan`, `_temporal_irls_phase_gpu` nếu cần; xoá phần còn lại | merge/delete | 4 |
| `stamps/sbas_mintpy_mixin.py` | `ps/sbas.py`, `ps/closure.py` (không ai import — đối chiếu với bản sao trong flow) | merge | 4 |
| `s1/stamps/plot_stamps.py` | `ps/plotting.py` | move | 4 |
| `capella/stamps/plot_stamps.py` (shim runpy) | — | delete | 4 |
| `{s1,csk}/stamps/synth_sbas_pairs.py` | `network/pairs.py` | merge | 4 |
| `capella/stamps/synth_sbas_pairs.py` | chỉ lấy `filter_master_pairs_by_extent` → `network/pairs.py`; xoá phần còn lại | merge/delete | 4 |
| `s1/stamps/autorun.py` | — (import một module không tồn tại) | delete | 1 |
| `s1/stamps/console_log.py` | `core/logging.py` | replace | 2 |
| `prestamps/stamps_prep.py` | `selection/*`, pha `select_candidates` | port | 4 |
| `prestamps/calamp.py` | `selection/amplitude.py` | port | 4 |
| `prestamps/ps_parms.py` | `ps/params.py` | move | 4 |
| `prestamps/extract_pixels.py`, `pscands_coh.py`, `pscdem.py`, `psclonlat.py`, `pscphase.py` | `selection/candidates.py` (đọc từ StackStore) | port | 4 |
| `prestamps/rslc_coherence.py`, `rslc_extent.py` | `stack/native/coherence.py`, `network/pairs.py` (phạm vi) | port | 4 |
| `prestamps/capella_pscands_geo.py` | — (Capella không đi qua StaMPS) | delete | 4 |
| `prestamps/psds_prep.py`, `comsar_prep.py` | pha `phase_linking` + `select_candidates` | replace | 4 |
| `prestamps/legacy_layout.py` | `io/legacy/stamps_layout.py` | legacy | 2 |
| các binary `calamp`, `selpsc_patch`, `selsbc_patch`, `psclonlat`, `pscdem`, `pscphase` (+.exe) | — | delete | 4 (sau golden) |
| `s1/tomo/*` | `phase_linking/{shp,estimators,runner}.py` (bwstest, adtest, psds, comsar, input_parm) | merge | 4 |
| `capella/tomo/*` (+ các binary trùng lặp) | — (đối chiếu với s1/tomo, khác biệt nào đáng giá thì lấy) | delete | 4 |
| `s1/vsar/*` (`ifg_loader`, `gpu_phase_linking`, `ds_filter`, `pscands_writer`, `vsar_step`) | `phase_linking/{runner,estimators,ds}.py`; `pscands_writer` → xoá | merge | 4 |

## 5. Các module khác trong `modules/`

| Hiện tại | Đích | Hành động | Phase |
|---|---|---|---|
| `phase_linking/capella.py` (kernel + I/O GAMMA) | `phase_linking/estimators.py`, `shp.py`; I/O GAMMA → `io/legacy/gamma.py` | split | 4 |
| `phase_linking/s1.py`, `csk.py` | `phase_linking/runner.py` | merge | 4 |
| `phase_linking/nlinsar.py`, `gaussian_postfilter.py` | `phase_linking/filters.py` | merge | 4 |
| `unwrap/irls_solver.py`, `irls_solver_capella.py` | `unwrap/irls.py` (`ps_lite` dùng cả hai qua `unwrap_method="s1"|"capella"` → giữ thành tuỳ chọn của một bộ giải chung) | merge | 4 |
| `unwrap/unwrap_2d_pipeline.py` (4913 dòng) + `unwrap_2d_{da,gaussian,geotiff,plot,gis_export}.py` | — quy trình 2D viết riêng cho Capella; Capella nay dùng `ps_lite` (ADR-020) | **delete** | 4 |
| `unwrap/unwrap_2d_goldstein.py` | `stack/native/filters.py` (dùng chung: csk flow, ps_stack, flat_earth) | move | 4 |
| `unwrap/unwrap_2d_coherence.py` | `stack/native/coherence.py` (`prestamps/pscands_coh.py` đang dùng) | move | 4 |
| `_component_relevel_twopi` (nằm trong `unwrap_2d_pipeline`, `tools/phase_link_viewer.py` mượn dùng) | `unwrap/components.py` nếu viewer còn cần, không thì bỏ | move/delete | 4 |
| Các phần phụ thuộc quy trình 2D: nhánh `phuw_2d.mat` trong `phasingpy.ps_export_gis`; các tham số `unwrap_2d_*` trong `prestamps/ps_parms.py`; tuỳ chọn `unwrap_2d_era5_2d_fit` trong `meteo/aps_era5/delays.py`; đoạn bỏ qua thư mục `phase_images` trong `ops/{health,run_report}.py` | — | delete | 4 |
| `meteo/aps_era5/*` | `atmosphere/era5/*` (`capella_time.py`, `csk_time.py` → xoá, dùng `SceneMetadata`) | move | 4 |
| `meteo/aps_gacos/*` | `atmosphere/gacos/*` | move | 4 |
| `meteo/compare_ifg.py`, `compare_tca_stats.py`, `visualize_tca.py`, `sweep.py` | `atmosphere/diagnostics.py` hoặc `apps/gui` | merge | 4 |
| `meteo/orbit_context.py`, `paths.py`, `rslc_dates.py` | `workspace/*` | replace | 2 |
| `meteo/tests/*` | `tests/unit/atmosphere/` | move | 4 |
| `ps_stack/__init__.py` (`run_stack`) | `processing/ps_lite/runner.py` — **quy trình Capella** (ADR-020) | port | 4 |
| `ps_stack/stack.py` (`Pair`, `Epoch`, `MasterGeometry`, `make_ifgs`, `longest_baselines`, `preview`) | đọc chồng ảnh → StackStore; hình học/pha tham chiếu/`kh` → `ps_lite/geometry.py` (+ `geometry/*`); chọn ảnh tham chiếu → `network/reference.py` | split | 4 |
| `ps_stack/ps.py` (`select_and_extract`, `calibration_factors`, `occupied_band`) | `ps_lite/candidates.py` (+ `selection/amplitude.py` cho phần hiệu chỉnh dùng chung) | port | 4 |
| `ps_stack/unwrap.py` (`unwrap_pair`, `filled_grid_stack`, `space_time_costs`) | `ps_lite/unwrap.py` (dùng `unwrap/irls.py`, `unwrap/grid.py`) | port | 4 |
| `ps_stack/invert.py` (`invert_weighted`, `height_error_periodogram`, `reference_phase`, `auto_reference`, `ifg_quality`) | `ps_lite/invert.py` | port | 4 |
| `ps_stack/export.py` (`geolocate`, `write_points`, `quicklooks`, `write_summary`) | `geometry/lut.py` (geolocate), `products/builder.py`, `export/vector.py`, `report/figures` | split | 6 |
| `ps_stack/__main__.py` | preset `capella` + `geoeyes run` | replace | 4 |
| `masking/model.py`, `processor.py`, `static_mask.py` | `masking/model.py`, `masking/water.py` | move | 4 |
| `masking/snap_coreg.py` | — (đọc trực tiếp StackStore) | delete | 4 |
| `masking/checkpoint/` | `$WS/models/water_unet/<ver>/` + manifest | move | 4 |
| `cr_detection/*` | `validation/corner_reflector/detection.py` | move | 6 |
| `cr_report/*` | `validation/corner_reflector/{measure,rcs,report}.py`; `s1slc.py` → `sensors/sentinel1/safe.py` | split | 6 |
| `pta/run_cr_workflow.py` | `validation/corner_reflector/pta.py` + CLI | move | 6 |
| `pta/cr_target_gui.py` | `apps/gui/cr_targets.py` | move | 9 |
| `pta/*.toml`, `pta_target.csv` | `validation/corner_reflector/resources/` | move | 6 |
| `sigsolv/appsigsolv/` | `third_party/appsigsolv/` | move | 6 |
| `qgis/insar_ps_plotter/`, `insar_ts_decompose/` | `apps/qgis/ps_plotter/`, `apps/qgis/ts_decompose/` | move | 9 |
| `triangle/` (binary + mã nguồn) | — thay bằng `scipy.spatial.Delaunay` trong `unwrap/triangulation.py` (ADR-019) | delete | 4 (sau golden) |
| `ops/__init__.py` (`atomic_write_json`, hàm trợ giúp env…) | `io/manifest.py` (ghi nguyên tử), `config/settings.py` | split | 2 |
| `ops/lock.py` | `workspace/lock.py` | move | 3 |
| `ops/run_history.py` | `controller/history.py` | port | 3 |
| `ops/progress.py` | `controller/progress.py` (bỏ StdoutWatcher/monkey-patch) | port | 3 |
| `ops/preflight.py` | `controller/preflight.py` | port | 3 |
| `ops/validation.py` | `config/schema.py` + `controller/planner.py` | replace | 2–3 |
| `ops/scaffold.py` | `controller/scaffold.py` | port | 3 |
| `ops/schedule.py` | `controller/schedule.py` | port | 3 |
| `ops/benchmark.py` | `controller/benchmark.py` | move | 3 |
| `ops/health.py` | `products/metrics.py` | port | 6 |
| `ops/alerts.py` | `postprocess/alerts.py` + `catalog/query.py` (so sánh) | split | 6–7 |
| `ops/log_rotation.py`, `logpaths.py` | `core/logging.py`, `catalog/retention.py` | replace | 2/7 |
| `ops/notify.py` | — | **delete** | 6 |
| `ops/run_report.py` | `report/*` | port | 8 |
| `ops/fonts/` | `report/templates/fonts/` | move | 8 |
| `ops/tests/test_alerts.py`, `test_env_file.py` | `tests/unit/…` | move | 6 |
| `ops/tests/test_notify.py` | — | delete | 6 |

## 6. `phasingpy.py` (`StaMPSEXE`) — chi tiết

| Nhóm phương thức | Đích |
|---|---|
| `_d_column_labels_from_ts_day_array` ở cấp module | — (ngày lưu dạng `datetime64`, không còn dùng ordinal/datenum) |
| `_utm_epsg_for_lonlat`, `_write_gpkg`, `_read_vector`, `_swap_ext`, `_read_export_shp_as_dataframe` | `core/geodesy.py`, `export/vector.py` |
| `_compute_da_from_coreg` | `selection/amplitude.py` |
| `__init__`, `_normalize_to_main_folder`, `_discover_current_result_base`, `_raw_has_rslc_data`, `_detect_result_folders`, `_load_rslcpar`, `_find_latest_result_folders`, `_is_stamps_complete`, `_extract_heading_from_result_folder` | `workspace/*`, `controller/planner.py`, `GEOMETRY` (heading) |
| `_ts_d_cols`, `_ts_update_ts_decomposition`, `update_ts_auto`, `compute_trend_from_result`, `plot_decomposition` | `postprocess/timeseries/decomposition.py` (+ hình → `report/figures`) |
| `_hampel_filter`, `_adaptive_savgol`, `_smooth_timeseries_*`, `_apply_ts_smooth_candidate`, `_auto_select_ts_smooth` | `postprocess/timeseries/smoothing.py` |
| `extract_seasonal`, `_fit_annual_seasonal` | `postprocess/timeseries/seasonal.py` |
| `_recompute_velocity`, `_compute_fit_rmse`, `_compute_psi_from_phuw`, `_apply_dtr_detrend`, `_apply_omt_refinement`, `_build_time_vector_from_displacement`, `_extract_scalar_from_vector` | `postprocess/timeseries/velocity.py` |
| `ps_dem_err`, `_k_ps_uw_per_ps_for_dem`, `_pick_baseline_history_from_ts`, `_estimate_dem_err_time_domain`, `_evaluate_dem_err_rmse`, `_mask_dem_err_outliers` | `postprocess/quality/dem_error.py` |
| `ps_lonlat_err`, `_terrain_slope_aspect_knn` | `postprocess/quality/geolocation.py` |
| `_compute_ps_residuals`, `_compute_residual_sigma`, `_spatial_std_vlos_mm_yr` | `postprocess/quality/residuals.py` |
| `_filter_isolated_points`, `_filter_height_outliers`, `_dedup_by_lonlat_tolerance` | `postprocess/quality/outliers.py` |
| `_apply_sigsol_cleaning` | `postprocess/quality/sigsolv.py` |
| `_zero_reference_first_valid` | `postprocess/reference.py` |
| `_load_alert_config`, `_extract_alert_scalar`, `_apply_alert_levels` | `postprocess/alerts.py` |
| `_load_static_water_mask_path`, `_apply_static_water_mask` | `masking/water.py` |
| `_get_3d_gpu_config`, `_get_3d_array_backend` | `core/compute.py` |
| `_decompose_vlos_and_displacement`, `_compute_has_matrix_eu`, `_fast_interpolate`, `_run_3d_decomposition`, `_finalize_3d_results`, `_apply_ts_decomposition_to_3d` | `postprocess/geometry/decompose3d.py` |
| `_build_3d_source_fingerprint`, `_is_3d_output_fresh`, `_write_3d_output_meta`, `_load_existing_3d_output` | `controller` (fingerprint/manifest dùng chung) |
| `_merge_overlap_timeseries`, `_merge_overlap_seamline` | `postprocess/geometry/overlap.py` |
| `_merge_subswath_outputs`, `_merge_subswath_dem_tifs`, `_subswath_outputs_ready` | `postprocess/geometry/merge_subswath.py` |
| `ps_export_gis` | tách: tạo PointSet → `postprocess` + `products/builder.py`; ghi tệp → `export/vector.py` |
| `ps_export_gis_capella_2d_lon_geo` | — (Capella không đi qua StaMPS; ps_lite xuất trực tiếp một PointSet) — xoá |
| `_csvtoshp`, `_standardize_scalar_export_columns`, `_save_seasonal_shp`, `_save_scn_shp`, `_scn_ifg_to_epochs`, `_save_gnss_calib_shp`, `_ensure_gnss_shp` | `export/vector.py` (+ `products/schema.py` cho tên cột chuẩn) |
| `_write_vlos_qgis_style`, `_backfill_legends_in_folder`, `_pretty_breaks`, `_filter_sparse_pretty_breaks` | `export/styles.py` |
| `rasterize_preserve_and_stack`, `snap_points_to_grid`, `raster_to_points`, `_save_ps_heatmap_tif`, `_save_ps_dem_tif`, `_save_height_3d_map` | `products/builder.py` (raster COG), `export/heatmap.py` |
| `_save_height_point_cloud` | `export/las.py` |
| `_process_single_orbit`, `run` | `controller/phases/{postprocess,merge_subswaths,decompose_3d,build_product}.py` |
| `_archive_settings_to_output`, `_make_export_log_path`, `_print_progress_bar` | manifest, `core/logging.py` |
| `_upload_latest_desc_scalar_to_postgis`, `_publish_desc_heatmap_to_geoserver`, `_publish_project_ids`, `_publish_with_rollback`, `_publish_output`, `_publish_merged_output`, `_merged_publish_ready`, `_latest_scalar_shp_in_output` | **xoá** |

## 7. `modules/utils/`

| Hiện tại | Đích | Hành động | Phase |
|---|---|---|---|
| `_data_detector.py` | `sensors/registry.py` (`detect_sensor`) | port | 4 |
| `calibfcomp.py` | — (không ai gọi) | delete | 1 |
| `check_disk.py` | `controller/preflight.py` | merge | 3 |
| `compare_result.py` | — (đường dẫn viết cứng, không ai gọi) | delete | 1 |
| `compute_cr_comdir.py` | `geometry/los.py` | merge | 4 |
| `compute_cr_ea.py` | `core/geodesy.py`, `geometry/los.py` | merge | 4 |
| `cr_los.py` | `geometry/orbit.py` (`Orbit`, `solve_zero_doppler`), `geometry/los.py`, `io/legacy/gamma.py` (`parse_gamma_par`) | split | 4 |
| `crlink.py` | `validation/gnss/{sources,compare}.py` | port | 6 |
| `dem.py` | `geometry/dem.py` | move | 4 |
| `flat_earth.py` | `stack/native/interferogram.py` | merge | 5 |
| `gnss_los_compare.py` | `validation/gnss/compare.py` | move | 6 |
| `imagery_db.py` | `processing/acquire/archive_index.py` | port | 4 |
| `insarcore.py` | `config/schema.py` (enum `method`) | replace | 2 |
| `kalman_ts.py` | `postprocess/timeseries/kalman.py` | move | 6 |
| `manual_preprocess.py` | — (không ai gọi) | delete | 1 |
| `mat_io.py` | `io/legacy/stamps_mat.py` | legacy | 2 |
| `metadata_writer.py`, `_apiso.xsd` | `io/iso19139.py` (+ xsd) ; bỏ tên tổ chức cũ và e-mail liên hệ cũ đặt làm mặc định | port | 6 |
| `migrate_shared_imagery.py` | — (chỉ dùng một lần, đã chạy xong) hoặc `geoeyes migrate` | delete | 4 |
| `mintpy_flow.py` | `ps/closure.py` | move | 4 |
| `mintpy_l1regls.py` | `inversion/l1regls.py` — **viết lại sạch** từ thuật toán, không giữ mã đã port (ADR-019) | port | 4 |
| `pta.py` | `validation/corner_reflector/pta.py` | move | 6 |
| `radial_heatmap.py` | `export/heatmap.py` | move | 6 |
| `results_versions.py` | `catalog/*` (liệt kê, prune) | replace | 7 |
| `rslc_par_geometry.py` | `stack/snap/importer.py` (vá hình học của SNAP) | move | 4 |
| `sbas_inversion.py` | `inversion/sbas.py` (phần GUI → `apps/gui`) | split | 4 |
| `sbas_temporal.py` | `inversion/temporal.py` | move | 4 |
| `single_search_download.py` | `sensors/sentinel1/search.py`, `acquire/download.py` | split | 4 |
| `step7_velocity.py` | `inversion/velocity.py` | move | 4 |
| `subswath_raster_merge.py` | `stack/native/tops.py` / `postprocess/geometry/merge_subswath.py` | move | 4 |
| `timing_log.py` | `core/logging.py` (sự kiện) | replace | 2 |
| `to_geoserver.py`, `to_postgis.py` | — | **delete** | 6 |
| `togeom.py` | — (không ai gọi) | delete | 1 |
| `ts_decomposition.py` | `postprocess/timeseries/decomposition.py` | move | 6 |
| `unwrap_grid.py` | `unwrap/grid.py` | move | 4 |
| README của `pta.py` / `utils/README.md` | `docs/` | port | 9 |

## 8. `tools/` — bỏ GUI desktop (ADR-022)

Xoá toàn bộ GUI desktop. Chỉ giữ (a) những thuật toán quy trình xử lý thực sự cần, chuyển vào thư viện; (b) các CLI bảo trì, chuyển thành lệnh `geoeyes`. Mã GUI cũ vẫn nằm trong bản sao lưu zip để tham khảo.

| Hiện tại | Đích | Hành động |
|---|---|---|
| `_split_spectrum_common.py` | `atmosphere/ionosphere.py` (split-spectrum — cần cho ALOS băng L, Phase 4b); bộ đọc ENVI/DIMAP → bỏ (dùng StackStore) | port |
| `_cli_common.py` | `cli/` (quy ước `--project` / `--product`) | port |
| `_ifg_common.py`, `_nlinsar_common.py`, `_phaseclean_common.py` | — (filter/NL-InSAR/D_A đã có trong `stack/native/filters.py`, `phase_linking/filters.py`, `selection/amplitude.py`) | delete |
| `phase_link_viewer.py` | — (EVD/EMI/PTA đã có trong `modules/phase_linking`); đối chiếu khác biệt trước khi xoá | delete |
| `ts_analyzer.py` | — ; nếu `postprocess/quality/sigsolv.py` cần thêm chức năng DIA/OMT thì lấy từ `third_party/appsigsolv` | delete |
| `capella_ifg_gui.py` | — (không thuộc quy trình; bản trong bản sao lưu là tài liệu tham khảo cho engine native ở Phase 5) | delete |
| `ps_stack_gui.py` | — (quy trình chạy bằng `geoeyes run`, preset `capella`) | delete |
| `aps_decision_gui.py`, `aps_sarproz_explorer_gui.py`, `spatial_highpass_gui.py`, `ps_ref_explorer_gui.py`, `overlap_merge_preview_gui.py`, `amp_calib_selector_gui.py`, `step8_scn_gui.py`, `closure_check_gui.py`, `cr_los_gui.py`, `double_diff_explorer.py`, `flat_earth_gui.py`, `gnss_insar_los_gui.py`, `ifg_residual_hp_gui.py`, `ifg_smoothing_gui.py`, `kalman_ts_gui.py`, `nlinsar_gui.py`, `phase_clean_gui.py`, `split_spectrum_gui.py`, `vlos_ts_explorer_gui.py`, `plot_final_candidates_amplitude.py` | — | delete |
| `benchmark_report.py` | `geoeyes benchmark` | replace |
| `project_health_check.py` | `geoeyes status` | replace |
| `schedule_monitoring.py` | `geoeyes schedule` | replace |
| `prune_results.py` | `geoeyes catalog prune` | replace |
| `regression_check.py` | `geoeyes catalog diff` | replace |
| `kalman_ts_filter.py`, `vlos_radial_heatmap.py` | — (Kalman nằm trong `postprocess/timeseries/kalman.py`, heatmap trong `export/heatmap.py`) | delete |
| `recompress_pm.py`, `ifg_qc_and_unwrap_test.py` | — | delete |
| `tools/README.md` | — | delete |
| `modules/pta/cr_target_gui.py` | — (sửa danh sách CR ngay trong tệp CSV/TOML) | delete |
| `meteo/sweep.py`, `compare_ifg.py`, `compare_tca_stats.py`, `visualize_tca.py` (phục vụ GUI APS) | — | delete |
| Phụ thuộc GUI: `customtkinter`, `pywinstyles`, `pyperclip`, `opencv-contrib-python` (nếu chỉ GUI dùng) | — | delete |

## 9. `webapp/` — tạm dừng, xây lại sau (ADR-022)

Đợt tái cấu trúc này **không** di chuyển webapp. Chủ dự án sẽ thiết kế và xây lại sau, trên nền API công khai của lõi (`geoeyes.controller`, `geoeyes.catalog`, `geoeyes.report`, JSON Schema của `geoeyes.config`).

| Hiện tại | Đích | Hành động |
|---|---|---|
| `webapp/` (backend + frontend + script) | đóng băng suốt Phases 1–8 (không sửa, không chạy test trong CI); trước `git init` (Phase 9) chuyển ra khỏi repo, giữ trong bản sao lưu để tham khảo | freeze → remove |
| `webapp/backend/tests/*` | loại khỏi bộ test | remove |
| `tests/test_boundaries.py` (lõi ↔ webapp) | — (thay bằng `import-linter`) | delete |
| Logic đáng giữ trong các service (để webapp mới tái sử dụng): `orbit_service` (dự đoán lượt bay S1), `chirps_service` (lượng mưa CHIRPS), `cr_report_service`/`cr_job_runner` (chạy báo cáo CR độc lập) | ghi lại trong `docs/en/refactor/webapp-notes.md` khi bắt đầu xây lại; các phần thuật toán đã nằm trong `geometry/orbit.py`, `validation/corner_reflector` | note |
| `webapp/_inspect_shp.py`, `frontend/dist/` | — | delete (Phase 1) |

## 10. `tests/`, `scripts/`, `docs/`

| Hiện tại | Đích | Hành động |
|---|---|---|
| `tests/test_boundaries.py` | các contract của `import-linter` | replace |
| `tests/test_run_normal_signature.py` | — (chỉ còn một engine) | delete |
| `tests/test_snap_graphs.py`, `test_snap_memory.py` | `tests/unit/stack/snap/` (cho tới khi xoá snap) | move |
| `tests/test_dem.py`, `test_flat_earth.py`, `test_ps_stack.py`, `test_pta_shift.py`, `test_cr_report.py`, `test_crlink.py` | `tests/unit/<package>/` | move |
| `tests/regression/*` | `tests/golden/` + `tests/unit/` | move |
| `scripts/bootstrap.{ps1,sh}` | giữ, cập nhật (`pip install -e .[extras]`, bỏ `VINSAR_PYTHON`, bỏ bước kiểm tra SNAP khi đã chạy native) | port |
| `scripts/check_quality.ps1` | giữ (ruff, mypy, import-linter, pytest, build frontend) | port |
| `scripts/check_user_paths.py` | giữ, áp dụng cho `project.toml` | port |
| `docs/data_layout.md` | thay bằng ARCHITECTURE §11 + `docs/user/workspace.md` | replace |
| `docs/deploy.md` | `docs/user/deploy.md` (bỏ lệnh `git clone` repo cũ dưới tài khoản của tổ chức cũ) | port |
| `docs/feature_map.md`, `docs/interfaces.md` | thay bằng ARCHITECTURE | replace |
| `docs/wiki.html` (354 KB) | `docs/science/` (tách thành markdown theo chủ đề tham số StaMPS) | port |
| Các README con trong `modules/*` | gom vào `docs/` | port |

## 11. Bảng thay thế nhãn (Phase 9)

| Cũ | Mới |
|---|---|
| `VINSAR`, `Vinsar`, `vinsar` (tên sản phẩm) | `GeoEyes` / `geoeyes` |
| `vinsar.py --run P` | `geoeyes run P` |
| env `VINSAR_*` | `GEOEYES_*` hoặc bỏ (§14.2 ARCHITECTURE) |
| `vinsar-webapp`, `vinsar-web`, `vinsar-notify`, `vinsar-build-check` | `geoeyes-webapp`, `geoeyes-web`, (bỏ), `geoeyes-build-check` |
| `vinsar.currentProject` (localStorage) | `geoeyes.currentProject` |
| `v_vinsar_mm_yr`, `mean_v_vinsar`, `vinsarVals` | `vel_los_mm_yr`, `mean_vel_los`, `velVals` |
| `__vinsar_bak` | (bỏ — không còn sao lưu control.json) |
| `demo_vinsar` | `demo_geoeyes` |
| Mã quy trình vận hành cũ, cổng/ký duyệt G0–G6 | xoá (ADR-016) |
| Tên tổ chức cũ và e-mail liên hệ cũ (siêu dữ liệu mặc định) | xoá; `[project].organization` tuỳ chọn (ADR-016) |
| Các chuỗi tiếng Việt trong mã/giao diện/báo cáo | tiếng Anh (ADR-015) |
| Tên riêng của từng máy, đặt theo tên tổ chức cũ (đường dẫn máy thật trong `control/mexico/config.json`) | chuyển vào env `GEOEYES_GNSS_*` của máy đó |
| URL repo cũ (thuộc tài khoản GitHub của tổ chức cũ) | URL repo mới (khi có) |
| `master` / `slave` | `reference` / `secondary` |
| `INSAR_<date>_NORMAL_vN` | `stack_id` / `psrun_id` / `product_id` |
