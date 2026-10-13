# Mass Goal Seek

A Fusion 360 add-in that automatically adjusts a chosen parameter until a chosen
body reaches a target mass, using an iterative secant-method solver.

## What it does

Given:
- A **parameter** to adjust (e.g. `Freeboard`)
- A **body** to measure (e.g. `bouyancy`)
- A **target mass**

The add-in repeatedly nudges the parameter, recomputes the model, and measures
the body's mass until it converges within a tolerance of the target — removing
the need to manually guess-and-check dimensions to hit a mass target.

## Installation

1. Create a folder named `MassGoalSeekSolver`.
2. Save the add-in's `.py` file and `.manifest` file inside it (same base name
   as the folder).
3. In Fusion: **Utilities → Add-Ins → Scripts and Add-Ins** (`Shift+S`), add the
   `MassGoalSeekSolver` folder under **My Add-Ins**, select it, and click **Run**.
   Check **Run on Startup** to have it load automatically.
4. The command appears as **Mass Goal Seek** under the Solid tab's
   Add-Ins panel.

## Dialog inputs

| Field | Description |
|---|---|
| **Parameter** | Dropdown of all parameters in the design. The one that will be adjusted. |
| **Body** | Dropdown of all bodies in the design. The one whose mass is measured. |
| **Target Mass** | Desired mass, entered with units (defaults to kg). |
| **Tolerance (g)** | Acceptable deviation from the target mass, in grams. |
| **Max Iterations** | Safety cap on solver iterations. |
| **Probe Step (mm)** | Initial step size used to estimate sensitivity before the solver's main iterations. |

## How the solver works

1. Reads the current parameter value and body mass.
2. If already within tolerance, stops immediately.
3. Takes one small probe step (in the direction that should move mass toward
   the target) to estimate how sensitive mass is to the parameter.
4. Uses the **secant method** to iteratively converge on the parameter value
   that produces the target mass, recomputing the model at each step.
5. Reports the final parameter value, final mass, number of iterations, and
   whether it converged.

If the probe step produces **zero change in mass** (the parameter doesn't
actually affect that body), the add-in reports this and reverts the parameter
to its original value without modifying the model further.

## Persistence

- **Per-document** (stored in the Fusion file itself via `design.attributes`):
  the last-used **Parameter** and **Body** selections. Reopening the same
  design pre-fills these dropdowns automatically.
- **Per-user** (stored in `mass_goal_seek_settings.json`, created automatically
  next to the add-in script): the last-used **Target Mass**, **Tolerance**,
  **Max Iterations**, and **Probe Step**. These apply as defaults across any
  document you open.

## Limitations

- Only works on parameters that actually drive the measured body's geometry
  (directly or indirectly). If there's no relationship, the solver detects
  zero sensitivity and stops safely.
- Assumes a roughly monotonic relationship between the parameter and mass in
  the region being solved. Highly non-linear or non-monotonic relationships
  may require more iterations or may not converge within `Max Iterations`.
- Designed for single-parameter, single-body goal-seeking — not simultaneous
  multi-variable optimization.

## Related add-in

**Righting Arm Sweep** builds on this add-in: it sweeps a second parameter
(e.g. heel angle) across a range, calling Mass Goal Seek's solver at each step
and logging a resulting measurement (e.g. center of mass) to a CSV for plotting.
