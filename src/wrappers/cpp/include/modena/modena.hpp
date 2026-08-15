/**
@cond

   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2026 MoDeNa Consortium, All rights reserved.

License
    This file is part of Modena.

    The Modena interface library is free software; you can redistribute it
    and/or modify it under the terms of the GNU Lesser General Public License
    as published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
    details.

    You should have received a copy of the GNU General Public License along
    with Modena.  If not, see <http://www.gnu.org/licenses/>.

@endcond
@file
Header-only C++17 RAII wrapper around the MoDeNa C interface library.

Include this single header and link against MODENA::modena_cpp:

    #include <modena/modena.hpp>

@author     Sigve Karolius
@copyright  2014-2026, MoDeNa Project. GNU Public License.
@defgroup   Cxx_interface_library
MoDeNa C++ interface library
*/

#pragma once

#include <modena.h>

#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace modena {

// -------------------------------------------------------------------------- //
// Exceptions
// -------------------------------------------------------------------------- //

/**
 * @brief Base exception for all MoDeNa errors.
 *
 * The what() message is retrieved from modena_error_message().
 */
struct Exception : std::runtime_error
{
    int code;

    explicit Exception(int c)
        : std::runtime_error(modena_error_message(c)), code(c)
    {}
};

/**
 * @brief Thrown when the requested model is not found in the database.
 */
struct ModelNotFound : Exception { using Exception::Exception; };

/**
 * @brief Thrown when modena_model_call returns 100.
 *
 * The surrogate model parameters were updated because the current operating
 * point is outside the trained domain.  The caller should propagate this
 * exception up to its time-step loop and retry the step, or return the code
 * to the workflow manager (FireWorks / lpad) for re-initialisation.
 */
struct ParametersUpdated : Exception { using Exception::Exception; };

/**
 * @brief Thrown when modena_model_call returns 200.
 *
 * MoDeNa requires a new Design of Experiments campaign.  The simulation must
 * exit, the workflow manager runs the DoE tasks, and then the simulation is
 * restarted from the beginning.
 */
struct ExitAndRestart : Exception { using Exception::Exception; };

/**
 * @brief Thrown when modena_model_call returns 201.
 *
 * MoDeNa requires new DoE data but the simulation does not need to be
 * restarted — the workflow manager will resume from the current state.
 */
struct ExitNoRestart : Exception { using Exception::Exception; };


// -------------------------------------------------------------------------- //
// Model
// -------------------------------------------------------------------------- //

/**
 * @brief RAII C++ wrapper around modena_model_t.
 *
 * Owns the model handle and the corresponding input and output vectors.
 * Move-only (no copy).
 *
 * @par Typical usage — named access (most readable)
 * @code
 *     modena::Model model("flowRate");
 *
 *     while (/* simulation loop *‌/) {
 *         model["D"]       = D;
 *         model["rho0"]    = rho0;
 *         model["p0"]      = p0;
 *         model["p1Byp0"]  = p1 / p0;
 *
 *         try {
 *             model.call();
 *         } catch (const modena::ParametersUpdated&) {
 *             continue;       // model retrained — retry this time step
 *         }
 *
 *         double mdot = model.output(0);
 *     }
 * @endcode
 *
 * @par Typical usage — positional access (faster in tight loops)
 * @code
 *     modena::Model model("flowRate");
 *
 *     // Cache positions once before the loop.
 *     const std::size_t Dpos      = model.input_pos("D");
 *     const std::size_t rho0Pos   = model.input_pos("rho0");
 *     const std::size_t p0Pos     = model.input_pos("p0");
 *     const std::size_t p1Byp0Pos = model.input_pos("p1Byp0");
 *     model.check();
 *
 *     while (/* simulation loop *‌/) {
 *         model.set(Dpos,      D);
 *         model.set(rho0Pos,   rho0);
 *         model.set(p0Pos,     p0);
 *         model.set(p1Byp0Pos, p1 / p0);
 *
 *         try {
 *             model.call();
 *         } catch (const modena::ParametersUpdated&) {
 *             continue;
 *         }
 *
 *         double mdot = model.output(0);
 *     }
 * @endcode
 */
class Model
{
public:

    // -------------------------------------------------------------------- //
    // Construction and destruction
    // -------------------------------------------------------------------- //

    /**
     * @brief Construct by fetching @p id from the MoDeNa database.
     *
     * All input and output positions are resolved once at construction
     * time and cached, so subsequent named access via operator[] and
     * output(std::string_view) is a plain hash-map lookup — no Python
     * calls, and safe to use after check() has released the GIL.
     *
     * @throws ModelNotFound if the model does not exist.
     */
    explicit Model(const std::string& id)
        : model_(modena_model_new(id.c_str()))
    {
        if (modena_error_occurred())
            throw ModelNotFound(modena_error());

        inputs_  = modena_inputs_new(model_);
        outputs_ = modena_outputs_new(model_);

        // Cache all input, output, and parameter positions up front.
        // These calls go through libmodena's Python bindings, so they
        // must happen BEFORE any downstream check() releases the GIL
        // for the time-step loop.  Parameter positions are the argPos
        // ordering derived from SurrogateFunction dict-key order.
        const std::size_t nin    = inputs_size();
        const std::size_t nout   = outputs_size();
        const std::size_t nparam = parameters_size();
        const char** in_names    = modena_model_inputs_names(model_);
        const char** out_names   = modena_model_outputs_names(model_);
        const char** param_names = modena_model_parameters_names(model_);
        input_pos_.reserve(nin);
        output_pos_.reserve(nout);
        parameter_pos_.reserve(nparam);
        for (std::size_t i = 0; i < nin;  ++i)
            input_pos_.emplace(in_names[i],
                               modena_model_inputs_argPos(model_, in_names[i]));
        for (std::size_t i = 0; i < nout; ++i)
            output_pos_.emplace(out_names[i],
                                modena_model_outputs_argPos(model_, out_names[i]));
        for (std::size_t i = 0; i < nparam; ++i)
            parameter_pos_.emplace(param_names[i], i);   // argPos == index
    }

    ~Model()
    {
        if (model_)
        {
            modena_inputs_destroy(inputs_);
            modena_outputs_destroy(outputs_);
            modena_model_destroy(model_);
        }
    }

    Model(const Model&)            = delete;
    Model& operator=(const Model&) = delete;

    Model(Model&& o) noexcept
        : model_(o.model_), inputs_(o.inputs_), outputs_(o.outputs_),
          input_pos_(std::move(o.input_pos_)),
          output_pos_(std::move(o.output_pos_)),
          parameter_pos_(std::move(o.parameter_pos_))
    {
        o.model_ = nullptr; o.inputs_ = nullptr; o.outputs_ = nullptr;
    }

    Model& operator=(Model&& o) noexcept
    {
        if (this != &o)
        {
            if (model_)
            {
                modena_inputs_destroy(inputs_);
                modena_outputs_destroy(outputs_);
                modena_model_destroy(model_);
            }
            model_         = o.model_;
            inputs_        = o.inputs_;
            outputs_       = o.outputs_;
            input_pos_     = std::move(o.input_pos_);
            output_pos_    = std::move(o.output_pos_);
            parameter_pos_ = std::move(o.parameter_pos_);
            o.model_ = nullptr; o.inputs_ = nullptr; o.outputs_ = nullptr;
        }
        return *this;
    }

    // -------------------------------------------------------------------- //
    // Metadata
    // -------------------------------------------------------------------- //

    std::size_t inputs_size()     const { return modena_model_inputs_size(model_); }
    std::size_t outputs_size()    const { return modena_model_outputs_size(model_); }
    std::size_t parameters_size() const { return modena_model_parameters_size(model_); }

    std::vector<std::string> inputs_names()     const
    { return names_from(modena_model_inputs_names(model_),     inputs_size()); }

    std::vector<std::string> outputs_names()    const
    { return names_from(modena_model_outputs_names(model_),    outputs_size()); }

    std::vector<std::string> parameters_names() const
    { return names_from(modena_model_parameters_names(model_), parameters_size()); }

    // -------------------------------------------------------------------- //
    // Fitted parameters — named access
    // -------------------------------------------------------------------- //

    /**
     * @brief One fitted parameter value by argPos index.
     */
    double parameter(std::size_t i) const
    {
        return modena_model_parameters_get(model_, i);
    }

    /**
     * @brief One fitted parameter value by declared name.
     *
     * O(1) via the cache built at construction time.
     *
     * @throws std::out_of_range if @p name is not a declared parameter.
     */
    double parameter(std::string_view name) const
    {
        auto it = parameter_pos_.find(std::string(name));
        if (it == parameter_pos_.end())
            throw std::out_of_range(
                "modena: unknown parameter '" + std::string(name) + "'"
            );
        return modena_model_parameters_get(model_, it->second);
    }

    /**
     * @brief All fitted parameters as a ``{name: value}`` map.
     *
     * Iteration order matches ``parameters_names()`` (argPos-ordered).
     */
    std::unordered_map<std::string, double> parameters() const
    {
        std::unordered_map<std::string, double> out;
        const std::size_t n = parameters_size();
        const char** names = modena_model_parameters_names(model_);
        out.reserve(n);
        for (std::size_t i = 0; i < n; ++i)
            out.emplace(names[i], modena_model_parameters_get(model_, i));
        return out;
    }

    // -------------------------------------------------------------------- //
    // ArgPos API — cache positions once, use in the hot loop
    // -------------------------------------------------------------------- //

    /**
     * @brief Return the argument position of input variable @p name.
     *
     * O(1) hash-map lookup against the cache built at construction time.
     * Safe to call after check() has released the GIL.
     *
     * @throws std::out_of_range if @p name is not a declared input.
     */
    std::size_t input_pos(std::string_view name) const
    {
        return input_pos_.at(std::string(name));
    }

    /**
     * @brief Return the argument position of output variable @p name.
     *
     * O(1) hash-map lookup against the cache built at construction time.
     * Safe to call after check() has released the GIL.
     *
     * @throws std::out_of_range if @p name is not a declared output.
     */
    std::size_t output_pos(std::string_view name) const
    {
        return output_pos_.at(std::string(name));
    }

    /**
     * @brief Assert that every input position has been claimed.
     *
     * With the position-caching ctor above this is now a no-op contract
     * (all positions are claimed during construction) but the call
     * still forwards to modena_model_argPos_check so libmodena can
     * release the GIL for a subsequent multi-threaded time-step loop.
     */
    void check() const { modena_model_argPos_check(model_); }

    // -------------------------------------------------------------------- //
    // I/O — positional (fast path, use with cached positions)
    // -------------------------------------------------------------------- //

    void   set   (std::size_t pos, double v) { modena_inputs_set(inputs_, pos, v); }
    double get   (std::size_t pos) const     { return modena_inputs_get(inputs_, pos); }
    double output(std::size_t pos) const     { return modena_outputs_get(outputs_, pos); }

    // -------------------------------------------------------------------- //
    // I/O — named (ergonomic, resolves name on every access)
    // -------------------------------------------------------------------- //

    /**
     * @brief Proxy returned by operator[] to support `model["D"] = value`.
     */
    struct InputProxy
    {
        Model&      m;
        std::size_t pos;

        InputProxy& operator=(double v)  { m.set(pos, v); return *this; }
        operator double() const          { return m.get(pos); }
    };

    /**
     * @brief Named input setter.  Returns a proxy for assignment.
     *
     *     model["D"] = 0.01;
     */
    InputProxy operator[](std::string_view name)
    {
        return {*this, input_pos(name)};
    }

    /**
     * @brief Named output getter.
     *
     *     double mdot = model.output("mdot");
     */
    double output(std::string_view name) const
    {
        return modena_outputs_get(outputs_, output_pos(name));
    }

    // -------------------------------------------------------------------- //
    // Evaluation
    // -------------------------------------------------------------------- //

    /**
     * @brief Call the surrogate model.
     *
     * @throws ParametersUpdated (ret == 100) The surrogate was retrained.
     *         Discard this call's outputs and retry the current time step.
     * @throws ExitAndRestart    (ret == 200) Exit and restart the simulation.
     * @throws ExitNoRestart     (ret == 201) Exit; no restart needed.
     * @throws Exception         on any other non-zero return or C-level error.
     */
    void call()
    {
        const int ret = modena_model_call(model_, inputs_, outputs_);
        if (ret == 100) throw ParametersUpdated(ret);
        if (ret == 200) throw ExitAndRestart(ret);
        if (ret == 201) throw ExitNoRestart(ret);
        if (ret != 0 || modena_error_occurred())
            throw Exception(modena_error_occurred() ? modena_error() : ret);
    }

private:

    modena_model_t   *model_;
    modena_inputs_t  *inputs_;
    modena_outputs_t *outputs_;

    // Position caches — populated once at construction time from
    // modena_model_inputs_argPos / modena_model_outputs_argPos so
    // named access via operator[] / output(name) is a pure C++
    // lookup, safe after check() has released the GIL.
    std::unordered_map<std::string, std::size_t> input_pos_;
    std::unordered_map<std::string, std::size_t> output_pos_;
    // Parameter positions are the argPos ordering derived from the
    // SurrogateFunction's parameter dict-key order (Phase 3), which
    // matches iteration order of modena_model_parameters_names().
    std::unordered_map<std::string, std::size_t> parameter_pos_;

    static std::vector<std::string>
    names_from(const char** arr, std::size_t n)
    {
        std::vector<std::string> v;
        v.reserve(n);
        for (std::size_t i = 0; i < n; ++i)
            v.emplace_back(arr[i]);
        return v;
    }
};

} // namespace modena

// ************************************************************************* //
