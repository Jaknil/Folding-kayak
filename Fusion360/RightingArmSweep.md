# Righting Arm Sweep

A Fusion 360 add-in that sweeps a chosen parameter across a range of values,
re-solving a mass target at each step (via the **Mass Goal Seek** add-in), and
logs a resulting world-space measurement to a CSV file — built for generating
righting-arm (or similar) curves for boat hull analysis.

##  Requires Mass Goal Seek

**This add-in depends on `MassGoalSeekSolver` and will not function without it.**

- `MassGoalSeekSolver` must be installed as a **sibling folder** (same parent
  Add-Ins directory) alongside `RightingArmSweep`. The add-in imports it
  directly as a Python module.
- `MassGoalSeekSolver` must have been **run at least once in the current
  document**, with a parameter and body selected and solved successfully.
  Righting Arm Sweep reads Mass Goal Seek's **persisted settings** for the
  current document (which parameter/body to goal-seek) and for the current
  user (target mass, tolerance, max iterations, probe step) — it does not ask
  for these again.

If `MassGoalSeekSolver` cannot be imported, or has no saved parameter/body for
the active document, Righting Arm Sweep will stop and show a message telling
you to run Mass Goal Seek first.

## What it does

Given:
- A **parameter** to sweep (e.g. `HeelAngle`), with a start value, end value,
  and step
- A **run label** (used as a column header)
- A **CSV file** to write results into

The add-in steps the parameter from start to end, and at each step:
1. Sets the parameter to the current sweep value.
2. Calls Mass Goal Seek's solver (using its persisted parameter/body/target
   settings) to re-converge the mass.
3. Measures the goal-seek body's **world-space** (assembly-context) center of
   mass X coordinate — i.e. its real position in the assembly, accounting for
   any rotation/translation of the component the body lives in.
4. Records the sweep value and the measured X coordinate.

When the sweep finishes, results are merged into the CSV as a new column.

## Installation

1. Create a folder named `RightingArmSweep`, **as a sibling of your existing
   `MassGoalSeekSolver` folder** (both under the same Add-Ins directory).
2. Save the add-in's `.py` file and `.manifest` file inside it (same base name
   as the folder).
3. In Fusion: **Utilities → Add-Ins → Scripts and Add-Ins** (`Shift+S`), add
   the `RightingArmSweep` folder under **My Add-Ins**, select it, and click
   **Run**.
4. The command appears as **Righting Arm Sweep** under the Solid tab's
   Add-Ins panel.

## Dialog inputs

| Field | Description |
|---|---|
| **Parameter** | Dropdown of all parameters in the design. The one that will be swept. Unit labels on the fields below update automatically based on this selection (e.g. degrees, mm). |
| **Start / End / Step** | The sweep range, in the sweep parameter's own display units. |
| **Run Label** | Text used as the new CSV column header for this run. If it duplicates an existing column, a numeric suffix is auto-appended, e.g. `Run 1 (2)`. |
| **CSV Path** | Path to the output CSV. Use **Browse...** to pick or create a file. |

## CSV output format

Results are stored **wide-format**, one column per run, keyed by the swept
value (rounded to 3 decimal places) so multiple runs with the same range align
into the same rows:

HeelAngle_deg, Run 1, +10kg ballast 0, 0.0, 0.0 1, 1.77, 2.10 ... 90, -138.55, -142.30

- Each new run adds a column; existing columns and rows are preserved.
- If a run's swept values don't match previously logged values exactly, new
  rows are added and unmatched cells are left blank.

## Progress and cancellation

- A progress dialog shows which point is currently being solved
  (`Solving point X of Y (Parameter = value)`).
- A **Cancel** button is available. If clicked, the sweep stops after the
  current point; whatever points were already solved are still written to the
  CSV, and the summary message notes the run was cancelled.

## Write-access checks

Before starting the sweep, and again right before saving results, the add-in
checks that the CSV file can actually be written to (e.g. not open in Excel,
not read-only, parent folder exists). If the file becomes locked mid-sweep,
solved points are reported but not silently lost — you'll be told how many
points were solved and asked to free the file and try again.

## Parameter restoration

After the sweep completes — or is cancelled — the swept **parameter** is
automatically restored to the value it had before the sweep started. Note that
this only applies to the swept parameter itself; the Mass Goal Seek target
parameter (e.g. `Freeboard`) is left at whatever value converged for the last
solved point, since it's a dependent result of the sweep, not a value you set
directly.

## Persistence

- **Per-document** (via `design.attributes`): the last-used **Parameter**
  selection for the sweep.
- **Per-user** (via `righting_arm_sweep_settings.json`, created next to the
  add-in script): the last-used **Start**, **End**, **Step**, **Run Label**,
  and **CSV Path**.

Mass Goal Seek's own settings (target mass, tolerance, etc.) are read directly
from *its* persisted settings — Righting Arm Sweep does not duplicate or
override them.

## Limitations

- Requires `MassGoalSeekSolver` installed as a sibling folder and already
  configured/run once for the active document (see warning above).
- World-space center-of-mass calculation assumes the measured body lives
  inside an **occurrence** with a transform relative to the root component.
  If the body is directly in the root component (no occurrence), its
  component-local and world-space values are the same.
- Large sweeps (many points, each requiring several solver iterations) can
  take a noticeable amount of time — the progress dialog's Cancel button is
  there for exactly this case.
