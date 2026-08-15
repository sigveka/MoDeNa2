% test_matlab_smoke.m
%
% MATLAB/Octave smoke test for the Modena wrapper.
%
% Loads the ``flowRate`` surrogate via the MEX gateway, evaluates it at
% a known-good point, and asserts the resulting mass flow rate is
% finite and positive.  Also exercises the Phase 3 named-parameter
% accessors that this session added (``parameters()``, ``get_parameter``).
%
% Same coverage as ``test_cpp_smoke.C`` and ``test_fortran_smoke.f90``
% but via the MATLAB/Octave binding, so a regression that only
% surfaces on the MEX side (e.g. mex-to-C ABI drift, mkoctfile flag
% breakage) gets caught here.
%
% Requires ``flowRate`` to be initialized in the MongoDB pointed to by
% MODENA_URI.  The runner script (invoked by ctest via
% ``octave --eval ...``) prepends the MEX + Modena.m install directory
% to the octave path before calling this file.
%
% Exit code (via the caller): 0 on success, non-zero on any assertion
% or MEX error.

fprintf(1, '-- test_matlab_smoke --\n');

% ── Load ─────────────────────────────────────────────────────────────
m = Modena('flowRate');
fprintf(1, 'loaded flowRate\n');

% ── Metadata sanity ──────────────────────────────────────────────────
assert(m.inputs_size()  == 4, 'expected 4 inputs, got %d',  m.inputs_size());
assert(m.outputs_size() == 1, 'expected 1 output, got %d',  m.outputs_size());
assert(m.parameters_size() == 2, ...
       'expected 2 parameters, got %d', m.parameters_size());

% ── Cache positions ──────────────────────────────────────────────────
pos_D       = m.input_pos('D');
pos_rho0    = m.input_pos('rho0');
pos_p0      = m.input_pos('p0');
pos_p1Byp0  = m.input_pos('p1Byp0');
pos_mdot    = m.output_pos('flowRate');
m.check();

% ── Evaluate at a known-good point (matches the C++/Fortran smokes) ──
m.set_input(pos_D,      0.01);
m.set_input(pos_rho0,   3.4);
m.set_input(pos_p0,     3.0e5);
m.set_input(pos_p1Byp0, 0.03);

code = m.call();
assert(code == 0, 'modena_model_call returned non-zero: %d', code);

mdot = m.get_output(pos_mdot);
assert(isfinite(mdot),        'output must be finite');
assert(mdot > 0.0,            'flow rate must be positive');
assert(mdot > 1e-4 && mdot < 1.0, ...
       'flow rate out of loose range [1e-4, 1.0]: %g', mdot);

% ── Phase 3: named-parameter accessors ───────────────────────────────
% ``parameters()`` returns a struct keyed by declared parameter name.
p = m.parameters();
assert(isstruct(p),        'parameters() must return a struct');
assert(isfield(p, 'P0'),   'expected field P0');
assert(isfield(p, 'P1'),   'expected field P1');
assert(isfinite(p.P0),     'P0 must be finite');
assert(isfinite(p.P1),     'P1 must be finite');

% ``get_parameter(name)`` returns a scalar; must match the struct field.
p0_via_getter = m.get_parameter('P0');
assert(abs(p0_via_getter - p.P0) < 1e-12, ...
       'get_parameter and parameters() must agree');

% Unknown name must raise (mexErrMsgIdAndTxt → error).  Octave and
% MATLAB both raise a catchable error object.
threw = false;
try
    m.get_parameter('does_not_exist');
catch
    threw = true;
end
assert(threw, 'get_parameter on unknown name should throw');

fprintf(1, 'PASS  test_matlab_smoke  (flowRate mdot = %.6f kg/s)\n', mdot);
