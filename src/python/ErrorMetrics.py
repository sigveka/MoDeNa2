'''@cond
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
@endcond'''
"""
@namespace python.ErrorMetrics
@brief     Composable error metric classes for surrogate model fitting.
@details
    Defines ErrorMetricBase and concrete implementations (AbsoluteError,
    RelativeError, NormalizedError).  Kept in a separate file to avoid
    circular imports: SurrogateModel and Strategy both import from here,
    but this module imports from neither.

@author    MoDeNa Consortium
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

import abc
from collections import defaultdict
from fireworks.utilities.fw_utilities import explicit_serialize
from fireworks.utilities.fw_serializers import (
    FWSerializable, serialize_fw, recursive_serialize, recursive_deserialize,
)


class ErrorMetricBase(defaultdict, FWSerializable):
    """
    @brief Base class for error metrics used in surrogate model fitting.

    Subclasses implement `residual()` to compute a per-sample scalar.
    `aggregate()` reduces a sequence of residuals to a single scalar used
    for acceptance decisions (default: max absolute value).
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    @abc.abstractmethod
    def residual(self, predicted: float, measured: float,
                 output_range: float) -> float:
        """Return the residual for a single sample."""
        raise NotImplementedError

    def aggregate(self, residuals) -> float:
        """Reduce a sequence of residuals to a scalar (default: max |r|)."""
        return max((abs(r) for r in residuals), default=0.0)

    @serialize_fw
    @recursive_serialize
    def to_dict(self):
        return dict(self)

    @classmethod
    @recursive_deserialize
    def from_dict(cls, m_dict):
        return cls(m_dict)

    def __repr__(self):
        return f'<{self.fw_name}>:{dict(self)}'


@explicit_serialize
class AbsoluteError(ErrorMetricBase):
    """
    @brief Absolute residual: measured - predicted.
    """

    def __init__(self, *args, **kwargs):
        ErrorMetricBase.__init__(self, *args, **kwargs)

    def residual(self, predicted: float, measured: float,
                 output_range: float) -> float:
        return measured - predicted


@explicit_serialize
class RelativeError(ErrorMetricBase):
    """
    @brief Relative residual: (measured - predicted) / |measured|.

    Falls back to absolute residual when |measured| < 1e-10.
    """

    def __init__(self, *args, **kwargs):
        ErrorMetricBase.__init__(self, *args, **kwargs)

    def residual(self, predicted: float, measured: float,
                 output_range: float) -> float:
        if abs(measured) < 1e-10:
            return measured - predicted
        return (measured - predicted) / abs(measured)


@explicit_serialize
class NormalizedError(ErrorMetricBase):
    """
    @brief Normalized residual: (measured - predicted) / output_range.

    Falls back to absolute residual when output_range < 1e-10.
    """

    def __init__(self, *args, **kwargs):
        ErrorMetricBase.__init__(self, *args, **kwargs)

    def residual(self, predicted: float, measured: float,
                 output_range: float) -> float:
        if output_range < 1e-10:
            return measured - predicted
        return (measured - predicted) / output_range
