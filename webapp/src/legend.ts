// A legend as data: what the web page shows (Hazard, thematic layers) and what the map export draws on the sheet
// come from the same description, so the printed legend is the one of the page.

export interface LegendItem {
  rgb: number[];
  label: string;
  alpha?: number;
}

export interface LegendSpec {
  title: string;
  head?: string;                       // a line above the items
  items?: LegendItem[];                // classes, top to bottom
  ramp?: { stops: number[][]; lo: string; hi: string; unit: string };
  notes?: string[];                    // lines under the items
  matrix?: number[][];                 // hazard: the intensity × damage-potential matrix of levels
  matrixRgb?: number[][];              // the colour of each level of the matrix
  text?: string;                       // nothing to colour: this sentence instead
}
