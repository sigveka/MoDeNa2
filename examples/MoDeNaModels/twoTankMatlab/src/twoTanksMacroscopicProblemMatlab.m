%{
@file   twoTanksMacroscopicProblemMatlab.m
@brief  Two-tank pressure equilibration — MATLAB/Octave counterpart of twoTankCxx.

Demonstrates the Modena wrapper for MATLAB and Octave.  The workflow is
identical to the C++ and Julia examples:
  1. Load the surrogate model.
  2. Cache input argument positions once before the loop.
  3. Call check() to verify all positions have been queried.
  4. Run the time-stepping loop.
  5. Handle the three non-zero return codes from call().

Return codes from call()
  0    success
  100  surrogate was retrained — decrement time, retry this step
  200  exit and restart the simulation
  201  exit without restart

@author    MoDeNa Project
@copyright 2014-2016, MoDeNa Project. GNU Public License.
@ingroup   twoTanksMatlab
%}

% ── Physical parameters ──────────────────────────────────────────────────────
R      = 287.1;   % specific gas constant for air [J/(kg K)]
T_gas  = 300.0;   % temperature [K]
D      = 0.01;    % orifice diameter [m]
V0     = 0.1;     % volume of tank 0 [m^3]
V1     = 1.0;     % volume of tank 1 [m^3]
deltat = 1e-3;    % time step [s]
tend   = 5.5;     % end time  [s]

p0 = 3e5;         % initial pressure tank 0 [Pa]
p1 = 1e4;         % initial pressure tank 1 [Pa]
m0 = p0 * V0 / R / T_gas;
m1 = p1 * V1 / R / T_gas;
rho0 = m0 / V0;
rho1 = m1 / V1;

% ── Load surrogate model ─────────────────────────────────────────────────────
model = Modena('flowRate');

fprintf('inputs:\n');
for n = inputs_names(model);  fprintf('  %s\n', n{1}); end
fprintf('outputs:\n');
for n = outputs_names(model); fprintf('  %s\n', n{1}); end
fprintf('parameters:\n');
for n = parameters_names(model); fprintf('  %s\n', n{1}); end

% Cache argument positions once before the loop.
Dpos      = input_pos(model, 'D');
rho0Pos   = input_pos(model, 'rho0');
p0Pos     = input_pos(model, 'p0');
p1Byp0Pos = input_pos(model, 'p1Byp0');
check(model);

% ── Time-stepping loop ───────────────────────────────────────────────────────
t = 0.0;
while t + deltat < tend + 1e-10
    t = t + deltat;

    % Set inputs — always flow from high to low pressure.
    if p0 > p1
        set_input(model, Dpos,      D);
        set_input(model, rho0Pos,   rho0);
        set_input(model, p0Pos,     p0);
        set_input(model, p1Byp0Pos, p1 / p0);
    else
        set_input(model, Dpos,      D);
        set_input(model, rho0Pos,   rho1);
        set_input(model, p0Pos,     p1);
        set_input(model, p1Byp0Pos, p0 / p1);
    end

    code = call(model);

    if code == 100
        t = t - deltat;   % stay at the same time step and retry
        continue
    elseif code == 200 || code == 201
        exit(code);
    elseif code ~= 0
        error('Modena:call', 'modena_model_call returned %d', code);
    end

    mdot = get_output(model, 0);

    if p0 > p1
        m0 = m0 - mdot * deltat;
        m1 = m1 + mdot * deltat;
    else
        m0 = m0 + mdot * deltat;
        m1 = m1 - mdot * deltat;
    end

    rho0 = m0 / V0;
    rho1 = m1 / V1;
    p0   = m0 / V0 * R * T_gas;
    p1   = m1 / V1 * R * T_gas;

    fprintf('t = %f  rho0 = %f  p0 = %f  p1 = %f\n', t, rho0, p0, p1);
end

delete(model);
