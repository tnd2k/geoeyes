// Vietnamese dictionary, one module per part of the interface (keys: the English text, as written in the code):
// app (shell, notifications), opendata (open-data hub), workspace (overview, tree, new project, map image, ui), explorer, project (project
// page, settings, monitoring, validation, GNSS), hazard, ai, learn, server (messages written by the API, with patterns).
// Terminology: docs/vi/GLOSSARY.md.
import { AI } from "./ai";
import { APP } from "./app";
import { ATMOSPHERE } from "./atmosphere";
import { CORRIDOR } from "./corridor";
import { EXPLORER } from "./explorer";
import { HAZARD } from "./hazard";
import { LEARN } from "./learn";
import { LEARN_IONOSPHERE } from "./learnIonosphere";
import { LEARN_SCIENCE } from "./learnScience";
import { OPENDATA } from "./opendata";
import { PROJECT } from "./project";
import { SERVER, SERVER_PATTERNS } from "./server";
import { SETTINGS } from "./settings";
import { WORKSPACE } from "./workspace";

export const VI: Record<string, string> = { ...APP, ...WORKSPACE, ...EXPLORER, ...PROJECT, ...HAZARD, ...AI, ...LEARN, ...LEARN_SCIENCE, ...LEARN_IONOSPHERE, ...OPENDATA, ...ATMOSPHERE, ...CORRIDOR, ...SERVER, ...SETTINGS };
export const VI_PATTERNS: [RegExp, string][] = SERVER_PATTERNS;
