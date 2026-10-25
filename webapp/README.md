# GeoEyes web app — front end

> Tiếng Việt: [README.vi.md](README.vi.md)

React + TypeScript + Vite, MapLibre + deck.gl for the map, TanStack Query, uPlot, Tailwind. It is a thin client
of the API in `src/geoeyes/api` (FastAPI), which reads the workspace through the core and starts runs as
`geoeyes run` subprocesses. Plan and design: `docs/en/refactor/webapp-plan.md`.

## Use

```
geoeyes serve            # http://localhost:8765 — API + built front end on one port, this machine only
geoeyes serve --open     # also opens the browser
```

Needs the `web` extra (`pip install -e .[web]`: fastapi, uvicorn, tomlkit). `geoeyes serve --host 0.0.0.0`
opens it to the network and then asks for a login token (`GEOEYES_WEB_TOKEN`, else a random one printed at start). No Node: the build is committed in
`src/geoeyes/api/static/`. API documentation: http://localhost:8765/api/docs.

## Develop

```
cd webapp
npm install
geoeyes serve            # API on 8765 (other terminal)
npm run dev              # http://127.0.0.1:8766, hot reload, /api proxied to 8765
npm run build            # type-check, then write the build into src/geoeyes/api/static
```

Ports: 8765 (`geoeyes serve`), 8766 (dev server), 8767 (`vite preview`). Vite's default 5173 is never used
(`strictPort`: a busy port is an error, not a silent switch).

## Layout

| File | Role |
|---|---|
| `src/api.ts` | API types and calls |
| `src/state.tsx` | route (`#/`, `#/explorer`, `#/project/<name>/<tab>`, `#/map/<project>/<product>`) and map layers (kept in `localStorage`) |
| `src/components/ProjectTree.tsx` | project tree: folders (drag and drop, rename, new), projects, tracks, products with eye toggle, report, context menu |
| `src/pages/Overview.tsx` | every project at a glance: KPIs, cards, latest runs |
| `src/pages/Explorer.tsx` | map: products as layers (opacity), legend (Pretty Breaks, jet_r), point → time series, drawn area → mean series, compare two products (swipe / difference) |
| `src/pages/Project.tsx` | pipeline cards with the plan's reasons, Run / Stop, live log, baselines, runs, validation, settings |
| `src/pages/NewProject.tsx` | new-project wizard: AOI drawn on the map, Sentinel-1 tracks over it, ASF preview |
| `src/components/SettingsForm.tsx` | settings form from the schema (own vs preset values, reset) and raw `project.toml` |
| `src/components/Validation.tsx` | corner reflector reports |
| `src/pages/Compose.tsx`, `src/compose.ts` | map composer: sheet layout drawn on a canvas, PNG / PDF export at print size |
| `src/components/Monitor.tsx` | next Sentinel-1 acquisitions, scheduled run, deformation alerts |
| `src/map.ts` | base maps, product layers (binary points or PMTiles vector tiles), velocity colours |
| `src/components/TimeSeries.tsx` | uPlot displacement chart |
| `src/ui.tsx` | status chips (colour + icon + label), buttons, formatting |

Points reach the map as one binary array per product (`float32` lon/lat offsets + velocity, about 12 bytes per
point; a cache under `<workspace>/cache/web/` built on first view), or, above 2.5 M points (or when chosen in the
layer panel), as PMTiles vector tiles served tile by tile (`exports/<id>/<id>.pmtiles`, else built once in the
cache). Time series and area means are read from a memory-mapped matrix of the same cache.
