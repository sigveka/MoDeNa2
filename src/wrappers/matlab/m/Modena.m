classdef Modena < handle
% MODENA  MoDeNa surrogate-model handle for MATLAB and Octave.
%
% Wraps libmodena via the modena_gateway MEX/OCT extension.
% Pointer handles are managed internally as uint64 scalars; all memory is
% freed automatically when the object is deleted (RAII via destructor).
%
% Quick start
% ───────────
%   m      = Modena('flowRate');
%   D_pos  = input_pos(m, 'D');
%   p0_pos = input_pos(m, 'p0');
%   check(m);
%
%   while t < tend
%       t = t + dt;
%       set_input(m, D_pos,  D);
%       set_input(m, p0_pos, p0);
%       code = call(m);
%       if code == 100,              t = t - dt; continue; end  % retrained
%       if code == 200 || code == 201, exit(code); end
%       mdot = get_output(m, 0);
%   end
%
% Return codes from call()
%   0    success
%   100  surrogate retrained mid-run — retry this step; do NOT exit
%   200  out of bounds; new DoE then restart — call exit(code)
%   201  model not in database, initialise from its module — call exit(code)
%   202  model has no fitted parameters — call exit(code)
%
% See also: modena_gateway

    properties (Constant)
        % Workflow protocol status codes.  Mirrors enum modena_status_t in
        % global.h and the constants in src/python/Strategy.py, which is
        % where they are defined.  Compare call() against these rather than
        % writing 100/200/201/202 inline.
        %
        % RETRAINED is only ever a call result: exiting with it is treated as
        % an unrecognised failure and terminates the workflow.
        %
        % See docs/return-codes.md.
        OK                    = 0
        RETRAINED             = 100
        OUT_OF_BOUNDS         = 200
        MODEL_NOT_IN_DATABASE = 201
        PARAMETERS_NOT_VALID  = 202
        INDEX_SET_NOT_IN_DATABASE = 401
        INTERNAL_ERROR        = 1
    end

    properties (Access = private)
        model_ptr    % uint64 — modena_model_t *
        inputs_ptr   % uint64 — modena_inputs_t *
        outputs_ptr  % uint64 — modena_outputs_t *
    end

    methods

        %-- Constructor ────────────────────────────────────────────────────────
        function obj = Modena(modelId)
        % MODENA  Load surrogate model modelId from the database.
            obj.model_ptr   = modena_gateway('model_new',   modelId);
            obj.inputs_ptr  = modena_gateway('inputs_new',  obj.model_ptr);
            obj.outputs_ptr = modena_gateway('outputs_new', obj.model_ptr);
        end

        %-- Destructor ─────────────────────────────────────────────────────────
        function delete(obj)
        % DELETE  Free inputs, outputs, and model (in that order).
        %   Guard against double-delete: if model_ptr is already zero (or
        %   empty) the gateway has already been called; skip silently.
            if isempty(obj.model_ptr) || obj.model_ptr == 0, return; end
            modena_gateway('model_destroy', ...
                obj.model_ptr, obj.inputs_ptr, obj.outputs_ptr);
            obj.model_ptr   = 0;
            obj.inputs_ptr  = 0;
            obj.outputs_ptr = 0;
        end

        %-- Positional queries ─────────────────────────────────────────────────
        function pos = input_pos(obj, name)
        % INPUT_POS  Return 0-based position of input 'name'.
        %   Cache before the simulation loop; use set_input(m, pos, val).
            pos = modena_gateway('input_pos', obj.model_ptr, name);
        end

        function pos = output_pos(obj, name)
        % OUTPUT_POS  Return 0-based position of output 'name'.
            pos = modena_gateway('output_pos', obj.model_ptr, name);
        end

        %-- Post-query validation ──────────────────────────────────────────────
        function check(obj)
        % CHECK  Verify that every input has been queried via input_pos.
        %   Call once after all input_pos calls, before the simulation loop.
            modena_gateway('argpos_check', obj.model_ptr);
        end

        %-- I/O access ─────────────────────────────────────────────────────────
        function set_input(obj, pos, value)
        % SET_INPUT  Set input at 0-based position pos to value.
            modena_gateway('inputs_set', obj.inputs_ptr, pos, value);
        end

        function value = get_output(obj, pos)
        % GET_OUTPUT  Get output at 0-based position pos after a successful call.
            value = modena_gateway('outputs_get', obj.outputs_ptr, pos);
        end

        %-- Evaluation ─────────────────────────────────────────────────────────
        function code = call(obj)
        % CALL  Evaluate the surrogate model.  Returns an integer code.
            code = modena_gateway('model_call', ...
                obj.model_ptr, obj.inputs_ptr, obj.outputs_ptr);
        end

        %-- Metadata ───────────────────────────────────────────────────────────
        function n = inputs_size(obj)
        % INPUTS_SIZE  Number of inputs the model expects.
            n = modena_gateway('inputs_size', obj.model_ptr);
        end

        function n = outputs_size(obj)
        % OUTPUTS_SIZE  Number of outputs the model produces.
            n = modena_gateway('outputs_size', obj.model_ptr);
        end

        function n = parameters_size(obj)
        % PARAMETERS_SIZE  Number of fitted parameters.
            n = modena_gateway('parameters_size', obj.model_ptr);
        end

        function names = inputs_names(obj)
        % INPUTS_NAMES  Cell array of input names in positional order.
            names = modena_gateway('inputs_names', obj.model_ptr);
        end

        function names = outputs_names(obj)
        % OUTPUTS_NAMES  Cell array of output names in positional order.
            names = modena_gateway('outputs_names', obj.model_ptr);
        end

        function names = parameters_names(obj)
        % PARAMETERS_NAMES  Cell array of parameter names in positional order.
            names = modena_gateway('parameters_names', obj.model_ptr);
        end

        %-- Named parameter access (Phase 3) ───────────────────────────────────
        function s = parameters(obj)
        % PARAMETERS  Fitted parameter values as a MATLAB struct keyed by name.
        %
        % Field names come from the SurrogateFunction's parameter declaration
        % order (which is the argPos ordering post Phase 3).  Equivalent to
        % Python's ``model.named_parameters()`` and R's ``m$parameters()``.
        %
        % Example:
        %   >> p = m.parameters()
        %   p =
        %     struct with fields:
        %       P0: 0.6134
        %       P1: 0.6143
            s = modena_gateway('parameters', obj.model_ptr);
        end

        function v = get_parameter(obj, name)
        % GET_PARAMETER  Look up one fitted parameter value by declared name.
        %
        % Errors with 'Modena:parameter' if NAME is not a declared parameter.
        %
        % Example:
        %   >> m.get_parameter('P0')
        %   ans = 0.6134
            v = modena_gateway('parameter', obj.model_ptr, name);
        end

    end % methods
end % classdef
