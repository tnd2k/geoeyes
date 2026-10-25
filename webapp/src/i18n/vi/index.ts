// Vietnamese dictionary, one module per part of the interface (keys: the English text, as written in the code):
// app (shell, notifications), workspace (overview, tree, new project, map image, ui), explorer, project (project
// page, settings, monitoring, validation, GNSS), hazard, server (messages written by the API, with patterns).
// Terminology: docs/vi/GLOSSARY.md.
import { APP } from "./app";
import { EXPLORER } from "./explorer";
import { HAZARD } from "./hazard";
import { PROJECT } from "./project";
import { SERVER, SERVER_PATTERNS } from "./server";
import { WORKSPACE } from "./workspace";

export const VI: Record<string, string> = { ...APP, ...WORKSPACE, ...EXPLORER, ...PROJECT, ...HAZARD, ...SERVER };
export const VI_PATTERNS: [RegExp, string][] = SERVER_PATTERNS;
