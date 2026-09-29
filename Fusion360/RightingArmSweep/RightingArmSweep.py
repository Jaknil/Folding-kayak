import adsk.core, adsk.fusion, adsk.cam
import os, sys, json, csv, traceback

_app = None
_ui = None
_handlers = []

CMD_ID = 'RightingArmSweep'
CMD_NAME = 'Righting Arm Sweep'
CMD_TOOLTIP = 'Sweep a parameter and log world-space center of mass X into a CSV, reusing Mass Goal Seek settings'
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'righting_arm_sweep_settings.json')
ATTR_GROUP = 'RightingArmSweep'

DEFAULT_START = 0.0
DEFAULT_END = 90.0
DEFAULT_STEP = 1.0
DEFAULT_LABEL = 'Run 1'

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ADDINS_DIR = os.path.dirname(_THIS_DIR)
_MGS_DIR = os.path.join(_ADDINS_DIR, 'MassGoalSeekSolver')
if _MGS_DIR not in sys.path:
    sys.path.append(_MGS_DIR)

try:
    import MassGoalSeekSolver as mgs
except Exception:
    mgs = None

def _load_user_defaults():
    defaults = {
        'start': DEFAULT_START,
        'end': DEFAULT_END,
        'step': DEFAULT_STEP,
        'label': DEFAULT_LABEL,
        'csvPath': '',
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            defaults.update({k: data.get(k, v) for k, v in defaults.items()})
    except Exception:
        pass
    return defaults


def _save_user_defaults(start, end, step, label, csv_path):
    data = {'start': start, 'end': end, 'step': step, 'label': label, 'csvPath': csv_path}
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _load_doc_defaults(design):
    result = {'sweepParamName': ''}
    try:
        attrs = design.attributes
        p = attrs.itemByName(ATTR_GROUP, 'sweepParamName')
        if p:
            result['sweepParamName'] = p.value
    except Exception:
        pass
    return result


def _save_doc_defaults(design, sweep_param_name):
    try:
        design.attributes.add(ATTR_GROUP, 'sweepParamName', sweep_param_name)
    except Exception:
        pass

def _get_body_and_occ(root, name):
    for occ in root.allOccurrences:
        for b in occ.component.bRepBodies:
            if b.name.lower() == name.lower():
                return b, occ
    for b in root.bRepBodies:
        if b.name.lower() == name.lower():
            return b, None
    return None, None


def _com_x_mm_world(body, occ):
    if occ is not None:
        proxy = body.createForAssemblyContext(occ)
        return proxy.physicalProperties.centerOfMass.x * 10.0
    return body.physicalProperties.centerOfMass.x * 10.0


def _round_key(x, ndigits=3):
    return round(x, ndigits)

def _check_csv_writable(csv_path):
    """Returns (True, '') if csv_path can be written to right now, else (False, reason).
    Non-destructive: uses append mode on existing files, a throwaway probe file otherwise."""
    directory = os.path.dirname(csv_path) or '.'

    if not os.path.isdir(directory):
        return False, f'Folder does not exist: {directory}'

    if os.path.exists(csv_path):
        if os.path.isdir(csv_path):
            return False, 'The selected path is a folder, not a file.'
        try:
            with open(csv_path, 'a', encoding='utf-8'):
                pass
        except PermissionError:
            return False, (
                'The file is open in another program (e.g. Excel) or is read-only.\n'
                'Please close it and try again.'
            )
        except OSError as e:
            return False, f'Cannot write to file: {e}'
        return True, ''

    probe_path = os.path.join(directory, f'.riarm_write_probe_{os.getpid()}.tmp')
    try:
        with open(probe_path, 'w', encoding='utf-8') as f:
            f.write('probe')
        os.remove(probe_path)
    except PermissionError:
        return False, f'No write permission in folder: {directory}'
    except OSError as e:
        return False, f'Cannot write in folder {directory}: {e}'

    return True, ''

def _merge_into_csv(csv_path, x_values, y_values, x_col_name, run_label):
    existing_header = None
    existing_rows = {}

    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            rows = list(reader)
        if rows:
            existing_header = rows[0]
            for r in rows[1:]:
                if not r:
                    continue
                key = _round_key(float(r[0]))
                row_dict = {}
                for i, col in enumerate(existing_header[1:], start=1):
                    row_dict[col] = r[i] if i < len(r) else ''
                existing_rows[key] = row_dict

    if existing_header is None:
        existing_header = [x_col_name]

    data_cols = existing_header[1:]

    label = run_label
    suffix = 2
    while label in data_cols:
        label = f'{run_label} ({suffix})'
        suffix += 1

    new_header = existing_header + [label]

    all_keys = set(existing_rows.keys())
    new_by_key = {}
    for x, y in zip(x_values, y_values):
        key = _round_key(x)
        new_by_key[key] = y
        all_keys.add(key)

    sorted_keys = sorted(all_keys)

    out_rows = []
    for key in sorted_keys:
        row_dict = existing_rows.get(key, {})
        row = [key]
        for col in data_cols:
            row.append(row_dict.get(col, ''))
        row.append(new_by_key.get(key, ''))
        out_rows.append(row)

    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(new_header)
        writer.writerows(out_rows)

    return label

class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            design = adsk.fusion.Design.cast(app.activeProduct)

            cmd = args.command
            inputs = cmd.commandInputs

            doc_defaults = _load_doc_defaults(design)
            user_defaults = _load_user_defaults()

            param_names = mgs._all_parameters(design) if mgs else []

            preferred = doc_defaults['sweepParamName'] or 'HeelAngle'

            param_dropdown = inputs.addDropDownCommandInput(
                'sweepParamDropdown', 'Parameter', adsk.core.DropDownStyles.TextListDropDownStyle)
            for name in param_names:
                param_dropdown.listItems.add(name, name == preferred)
            if preferred not in param_names and param_dropdown.listItems.count > 0:
                param_dropdown.listItems.item(0).isSelected = True

            unit_label = ''
            if mgs:
                p = mgs._get_parameter(design, preferred)
                if p:
                    unit_label = p.unit

            inputs.addValueInput(
                'startValue', f'Start ({unit_label})' if unit_label else 'Start',
                '', adsk.core.ValueInput.createByReal(user_defaults['start']))
            inputs.addValueInput(
                'endValue', f'End ({unit_label})' if unit_label else 'End',
                '', adsk.core.ValueInput.createByReal(user_defaults['end']))
            inputs.addValueInput(
                'stepValue', f'Step ({unit_label})' if unit_label else 'Step',
                '', adsk.core.ValueInput.createByReal(user_defaults['step']))

            inputs.addStringValueInput('runLabel', 'Run Label', user_defaults['label'])

            inputs.addStringValueInput('csvPath', 'CSV Path', user_defaults['csvPath'])
            inputs.addBoolValueInput('browseCsv', 'Browse...', False, '', False)

            on_execute = CommandExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)

            on_input_changed = CommandInputChangedHandler()
            cmd.inputChanged.add(on_input_changed)
            _handlers.append(on_input_changed)
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                'Command creation failed:\n{}'.format(traceback.format_exc())
            )

class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            design = adsk.fusion.Design.cast(app.activeProduct)
            changed = args.input
            inputs = args.inputs

            if changed.id == 'sweepParamDropdown':
                dropdown = adsk.core.DropDownCommandInput.cast(changed)
                sel = dropdown.selectedItem.name if dropdown.selectedItem else ''
                unit_label = ''
                if mgs:
                    p = mgs._get_parameter(design, sel)
                    if p:
                        unit_label = p.unit
                start_in = inputs.itemById('startValue')
                end_in = inputs.itemById('endValue')
                step_in = inputs.itemById('stepValue')
                start_in.name = f'Start ({unit_label})' if unit_label else 'Start'
                end_in.name = f'End ({unit_label})' if unit_label else 'End'
                step_in.name = f'Step ({unit_label})' if unit_label else 'Step'

            elif changed.id == 'browseCsv':
                browse_input = adsk.core.BoolValueCommandInput.cast(changed)
                browse_input.value = False
                file_dlg = ui.createFileDialog()
                file_dlg.isMultiSelectEnabled = False
                file_dlg.title = 'Select or create CSV file'
                file_dlg.filter = 'CSV files (*.csv)'
                csv_input = inputs.itemById('csvPath')
                if csv_input.value:
                    file_dlg.initialFilename = csv_input.value
                result = file_dlg.showSave()
                if result == adsk.core.DialogResults.DialogOK:
                    csv_input.value = file_dlg.filename
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                'Input changed handler failed:\n{}'.format(traceback.format_exc())
            )

class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            design = adsk.fusion.Design.cast(app.activeProduct)
            root = design.rootComponent
            um = design.unitsManager

            if mgs is None:
                ui.messageBox('Could not import MassGoalSeekSolver. Ensure both add-ins are installed as sibling folders.')
                return

            inputs = args.command.commandInputs
            sweep_param_input = inputs.itemById('sweepParamDropdown')
            start_input = inputs.itemById('startValue')
            end_input = inputs.itemById('endValue')
            step_input = inputs.itemById('stepValue')
            label_input = inputs.itemById('runLabel')
            csv_input = inputs.itemById('csvPath')

            sweep_param_name = sweep_param_input.selectedItem.name if sweep_param_input.selectedItem else ''
            start_display = start_input.value
            end_display = end_input.value
            step_display = step_input.value
            run_label = label_input.value.strip() or DEFAULT_LABEL
            csv_path = csv_input.value.strip()

            if not csv_path:
                ui.messageBox('Please choose a CSV path (use Browse...).')
                return
            if step_display == 0:
                ui.messageBox('Step cannot be zero.')
                return

            writable, reason = _check_csv_writable(csv_path)
            if not writable:
                ui.messageBox(f'Cannot write to the CSV file:\n\n{reason}\n\nFile: {csv_path}')
                return

            sweep_param = mgs._get_parameter(design, sweep_param_name)
            if sweep_param is None:
                ui.messageBox(f'Could not resolve sweep parameter: {sweep_param_name}')
                return

            param_unit = sweep_param.unit or ''

            def to_internal(display_value):
                if param_unit:
                    return um.evaluateExpression(f'{display_value} {param_unit}', param_unit)
                return display_value

            # Capture the sweep parameter's value BEFORE the sweep so it can be restored after,
            # regardless of whether the sweep completes normally or is cancelled partway through.
            initial_internal_value = sweep_param.value

            mgs_doc_defaults = mgs._load_doc_defaults(design)
            mgs_user_defaults = mgs._load_user_defaults()

            gs_param_name = mgs_doc_defaults['paramName']
            gs_body_name = mgs_doc_defaults['bodyName']
            target_mass_g = mgs_user_defaults['targetMassG']
            tol_g = mgs_user_defaults['toleranceG']
            max_iters = int(mgs_user_defaults['maxIters'])
            step_mm = mgs_user_defaults['stepMm']

            gs_param = mgs._get_parameter(design, gs_param_name)
            gs_body, gs_occ = _get_body_and_occ(root, gs_body_name)

            if gs_param is None or gs_body is None:
                ui.messageBox('Mass Goal Seek has no saved parameter/body for this document. Run Mass Goal Seek once first.')
                return

            n_steps = int(round((end_display - start_display) / step_display)) + 1
            if n_steps <= 0 or n_steps > 100000:
                ui.messageBox(f'Invalid sweep range/step producing {n_steps} points.')
                return

            progress = ui.createProgressDialog()
            progress.isCancelButtonShown = True
            progress.cancelButtonText = 'Cancel'
            progress.show(
                'Righting Arm Sweep',
                f'Solving point %v of %m ({sweep_param_name} = ' + '{:.3f})'.format(start_display),
                0, n_steps, 0
            )

            x_values = []
            y_values = []
            fail_count = 0
            cancelled = False

            for i in range(n_steps):
                if progress.wasCancelled:
                    cancelled = True
                    break

                x_display = start_display + i * step_display
                progress.message = f'Solving point %v of %m ({sweep_param_name} = {x_display:.3f})'
                progress.progressValue = i

                sweep_param.value = to_internal(x_display)
                design.computeAll()

                fx, fm, converged = mgs._solve(
                    design, gs_param, gs_body, target_mass_g, tol_g, max_iters, step_mm / 10.0, []
                )

                com_x_world = _com_x_mm_world(gs_body, gs_occ)
                x_values.append(x_display)
                y_values.append(com_x_world)
                if not converged:
                    fail_count += 1

            progress.progressValue = n_steps
            progress.hide()

            # Restore the sweep parameter to its pre-sweep value, whether the sweep
            # completed normally or was cancelled partway through.
            sweep_param.value = initial_internal_value
            design.computeAll()

            app.activeViewport.fit()

            if not x_values:
                ui.messageBox('Sweep cancelled before any points were solved. Nothing written.')
                return

            writable_now, reason_now = _check_csv_writable(csv_path)
            if not writable_now:
                ui.messageBox(
                    f'Solved {len(x_values)} point(s), but the CSV became unwritable before saving:\n\n'
                    f'{reason_now}\n\nFile: {csv_path}\n\n'
                    'Close the file elsewhere and use Mass Goal Seek / Righting Arm Sweep again;\n'
                    'the solved points were not saved.'
                )
                return

            final_label = _merge_into_csv(csv_path, x_values, y_values, sweep_param_name, run_label)

            _save_doc_defaults(design, sweep_param_name)
            _save_user_defaults(start_display, end_display, step_display, run_label, csv_path)

            status_line = 'Sweep CANCELLED by user.' if cancelled else 'Sweep complete.'
            msg = (
                f'{status_line}\n'
                f'Parameter: {sweep_param_name}\n'
                f'Points solved: {len(x_values)} of {n_steps} (failed convergence: {fail_count})\n'
                f'Column written: {final_label}\n'
                f'CSV: {csv_path}\n'
                f'{sweep_param_name} restored to its pre-sweep value.'
            )
            ui.messageBox(msg)
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                'Righting Arm Sweep failed:\n{}'.format(traceback.format_exc())
            )

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        cmd_defs = _ui.commandDefinitions
        existing = cmd_defs.itemById(CMD_ID)
        if existing:
            existing.deleteMe()

        cmd_def = cmd_defs.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TOOLTIP)

        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)

        panel = _ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        if panel:
            control = panel.controls.itemById(CMD_ID)
            if not control:
                panel.controls.addCommand(cmd_def)

    except Exception:
        if _ui:
            _ui.messageBox('Failed to start Righting Arm Sweep add-in:\n{}'.format(traceback.format_exc()))


def stop(context):
    try:
        panel = _ui.allToolbarPanels.itemById('SolidScriptsAddinsPanel')
        if panel:
            control = panel.controls.itemById(CMD_ID)
            if control:
                control.deleteMe()

        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
    except Exception:
        if _ui:
            _ui.messageBox('Failed to stop Righting Arm Sweep add-in:\n{}'.format(traceback.format_exc()))
