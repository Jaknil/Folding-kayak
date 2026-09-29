import adsk.core, adsk.fusion, adsk.cam
import os, json, traceback

_app = None
_ui = None
_handlers = []

CMD_ID = 'MassGoalSeekSolver'
CMD_NAME = 'Mass Goal Seek'
CMD_TOOLTIP = 'Adjust a parameter until a body reaches a target mass'
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mass_goal_seek_settings.json')
ATTR_GROUP = 'MassGoalSeekSolver'

DEFAULT_TOLERANCE_G = 50.0
DEFAULT_MAX_ITERS = 15
DEFAULT_STEP_MM = 5.0
DEFAULT_TARGET_MASS_G = 82000.0


def _load_user_defaults():
    defaults = {
        'toleranceG': DEFAULT_TOLERANCE_G,
        'maxIters': DEFAULT_MAX_ITERS,
        'stepMm': DEFAULT_STEP_MM,
        'targetMassG': DEFAULT_TARGET_MASS_G,
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            defaults.update({k: data.get(k, v) for k, v in defaults.items()})
    except Exception:
        pass
    return defaults


def _save_user_defaults(tolerance_g, max_iters, step_mm, target_mass_g):
    data = {
        'toleranceG': tolerance_g,
        'maxIters': max_iters,
        'stepMm': step_mm,
        'targetMassG': target_mass_g,
    }
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _load_doc_defaults(design):
    result = {'paramName': '', 'bodyName': ''}
    try:
        attrs = design.attributes
        p = attrs.itemByName(ATTR_GROUP, 'paramName')
        b = attrs.itemByName(ATTR_GROUP, 'bodyName')
        if p:
            result['paramName'] = p.value
        if b:
            result['bodyName'] = b.value
    except Exception:
        pass
    return result


def _save_doc_defaults(design, param_name, body_name):
    try:
        design.attributes.add(ATTR_GROUP, 'paramName', param_name)
        design.attributes.add(ATTR_GROUP, 'bodyName', body_name)
    except Exception:
        pass


def _all_parameters(design):
    names = []
    for p in design.allParameters:
        if p.name not in names:
            names.append(p.name)
    return names


def _all_body_names(root):
    names = []
    for b in root.bRepBodies:
        if b.name not in names:
            names.append(b.name)
    for occ in root.allOccurrences:
        for b in occ.component.bRepBodies:
            if b.name not in names:
                names.append(b.name)
    return names


def _get_parameter(design, name):
    for p in design.allParameters:
        if p.name == name:
            return p
    return None


def _get_body(root, name):
    for b in root.bRepBodies:
        if b.name == name:
            return b
    for occ in root.allOccurrences:
        for b in occ.component.bRepBodies:
            if b.name == name:
                return b
    return None


def _mass_g(body):
    return body.physicalProperties.mass * 1000.0

def _solve(design, param, body, target_mass_g, tol_g, max_iters, step_cm, log):
    x0 = param.value
    m0 = _mass_g(body)
    log.append(f'Iter 0: {param.name}={x0*10:.4f} mm, mass={m0:.2f} g')

    if abs(m0 - target_mass_g) <= tol_g:
        log.append('Already within tolerance.')
        return x0, m0, True

    step = -step_cm if m0 > target_mass_g else step_cm
    x1 = x0 + step
    param.value = x1
    design.computeAll()
    m1 = _mass_g(body)
    log.append(f'Iter 1 (probe): {param.name}={x1*10:.4f} mm, mass={m1:.2f} g')

    sensitivity = (m1 - m0) / (x1 - x0)
    if sensitivity == 0:
        log.append('ERROR: zero sensitivity detected, cannot converge. Reverting.')
        param.value = x0
        design.computeAll()
        return x0, m0, False

    prev_x, prev_m = x0, m0
    cur_x, cur_m = x1, m1
    converged = False

    for i in range(2, max_iters + 1):
        denom = (cur_m - prev_m)
        if denom == 0:
            log.append(f'Iter {i}: zero denominator, stopping secant.')
            break
        next_x = cur_x - (cur_m - target_mass_g) * (cur_x - prev_x) / denom

        param.value = next_x
        design.computeAll()
        next_m = _mass_g(body)
        log.append(f'Iter {i}: {param.name}={next_x*10:.4f} mm, mass={next_m:.2f} g')

        prev_x, prev_m = cur_x, cur_m
        cur_x, cur_m = next_x, next_m

        if abs(cur_m - target_mass_g) <= tol_g:
            converged = True
            log.append(f'Converged at iter {i}.')
            break

    if not converged:
        log.append(f'Did NOT converge within {max_iters} iterations. diff={cur_m-target_mass_g:.2f} g')

    return cur_x, cur_m, converged

class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            ui = app.userInterface
            design = adsk.fusion.Design.cast(app.activeProduct)
            root = design.rootComponent

            inputs = args.command.commandInputs
            param_input = inputs.itemById('paramDropdown')
            body_input = inputs.itemById('bodyDropdown')
            target_input = inputs.itemById('targetMass')
            tol_input = inputs.itemById('tolerance')
            iters_input = inputs.itemById('maxIters')
            step_input = inputs.itemById('stepSize')

            param_name = param_input.selectedItem.name if param_input.selectedItem else ''
            body_name = body_input.selectedItem.name if body_input.selectedItem else ''
            # target_input uses unitType 'kg'; .value is in internal database units (kg)
            target_mass_g = target_input.value * 1000.0
            tol_g = tol_input.value
            max_iters = int(iters_input.value)
            step_mm = step_input.value

            param = _get_parameter(design, param_name)
            body = _get_body(root, body_name)

            if param is None or body is None:
                ui.messageBox('Could not resolve the selected parameter or body.')
                return

            log = []
            final_x, final_m, converged = _solve(
                design, param, body, target_mass_g, tol_g, max_iters, step_mm / 10.0, log
            )

            app.activeViewport.fit()

            _save_doc_defaults(design, param_name, body_name)
            _save_user_defaults(tol_g, max_iters, step_mm, target_mass_g)

            status = 'Converged' if converged else 'Did NOT converge'
            msg = f'{status}.\n{param.name} = {final_x*10:.4f} mm\n{body.name} mass = {final_m:.2f} g\n\n' + '\n'.join(log)
            ui.messageBox(msg)
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                'Mass Goal Seek failed:\n{}'.format(traceback.format_exc())
            )

class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            design = adsk.fusion.Design.cast(app.activeProduct)
            root = design.rootComponent

            cmd = args.command
            inputs = cmd.commandInputs

            doc_defaults = _load_doc_defaults(design)
            user_defaults = _load_user_defaults()

            param_names = _all_parameters(design)
            body_names = _all_body_names(root)

            param_dropdown = inputs.addDropDownCommandInput(
                'paramDropdown', 'Parameter', adsk.core.DropDownStyles.TextListDropDownStyle)
            for name in param_names:
                param_dropdown.listItems.add(name, name == doc_defaults['paramName'])
            if doc_defaults['paramName'] not in param_names and param_dropdown.listItems.count > 0:
                param_dropdown.listItems.item(0).isSelected = True

            body_dropdown = inputs.addDropDownCommandInput(
                'bodyDropdown', 'Body', adsk.core.DropDownStyles.TextListDropDownStyle)
            for name in body_names:
                body_dropdown.listItems.add(name, name == doc_defaults['bodyName'])
            if doc_defaults['bodyName'] not in body_names and body_dropdown.listItems.count > 0:
                body_dropdown.listItems.item(0).isSelected = True

            inputs.addValueInput(
                'targetMass', 'Target Mass', 'kg',
                adsk.core.ValueInput.createByReal(user_defaults['targetMassG'] / 1000.0))

            inputs.addValueInput(
                'tolerance', 'Tolerance (g)', '',
                adsk.core.ValueInput.createByReal(user_defaults['toleranceG']))

            inputs.addValueInput(
                'maxIters', 'Max Iterations', '',
                adsk.core.ValueInput.createByReal(user_defaults['maxIters']))

            inputs.addValueInput(
                'stepSize', 'Probe Step (mm)', '',
                adsk.core.ValueInput.createByReal(user_defaults['stepMm']))

            on_execute = CommandExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                'Command creation failed:\n{}'.format(traceback.format_exc())
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
            _ui.messageBox('Failed to start Mass Goal Seek add-in:\n{}'.format(traceback.format_exc()))


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
            _ui.messageBox('Failed to stop Mass Goal Seek add-in:\n{}'.format(traceback.format_exc()))
