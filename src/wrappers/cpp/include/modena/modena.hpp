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
     * @throws ModelNotFound if the model does not exist.
     */
    explicit Model(const std::string& id)
        : model_(modena_model_new(id.c_str()))
    {
        if (modena_error_occurred())
            throw ModelNotFound(modena_error());

        inputs_  = modena_inputs_new(model_);
        outputs_ = modena_outputs_new(model_);
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
        : model_(o.model_), inputs_(o.inputs_), outputs_(o.outputs_)
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
            model_   = o.model_;
            inputs_  = o.inputs_;
            outputs_ = o.outputs_;
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
    // ArgPos API — cache positions once, use in the hot loop
    // -------------------------------------------------------------------- //

    /**
     * @brief Return the argument position of input variable @p name.
     *
     * Cache the result before the time-step loop and pass it to set() for
     * zero-overhead indexed access.
     */
    std::size_t input_pos(std::string_view name) const
    {
        // string_view::data() is not null-terminated; build a std::string to
        // ensure the C API receives a proper null-terminated string.
        return modena_model_inputs_argPos(model_, std::string(name).c_str());
    }

    /**
     * @brief Return the argument position of output variable @p name.
     */
    std::size_t output_pos(std::string_view name) const
    {
        return modena_model_outputs_argPos(model_, std::string(name).c_str());
    }

    /**
     * @brief Assert that every input and output position has been queried.
     *
     * Call once after all input_pos() / output_pos() calls to guard against
     * typos in variable names.
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
