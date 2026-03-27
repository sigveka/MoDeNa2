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
@namespace python.SurrogateModel
@brief     Module providing functions and models
@details

@author    Henrik Rusche
@author    Sigve Karolius
@author    Mandar Thombre
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

import logging
import os
import abc
import hashlib
from copy import deepcopy
from pathlib import Path
import modena

_log = logging.getLogger('modena.surrogate')
from modena.Strategy import *
import weakref
import re
import random
from mongoengine import connect
from mongoengine import DoesNotExist
from mongoengine import Document, DynamicDocument, DynamicEmbeddedDocument, \
 EmbeddedDocument
from mongoengine import DateTimeField, DictField, EmbeddedDocumentField, \
 FloatField, IntField, ListField, MapField, StringField, ReferenceField
from mongoengine.document import TopLevelDocumentMetaclass
from mongoengine.base import BaseField
import pymongo
from fireworks import Firework, FireTaskBase, Workflow
from fireworks.utilities.fw_serializers import load_object
from collections import defaultdict
import jinja2

__all__ = (
  "IndexSet", "ForwardMappingModel", "BackwardMappingModel", "CFunction",
  "SurrogateFunction", "Function", "SurrogateModel", "MODENA_URI",
  "MODENA_PARSED_URI", "DoesNotExist",
)

# Create connection to database
MODENA_URI = os.environ.get('MODENA_URI', 'mongodb://localhost:27017/test')
(uri, database) = MODENA_URI.rsplit('/', 1)
connect(
    database,
    host=MODENA_URI,
    serverSelectionTimeoutMS=5000,   # fail fast if MongoDB is unreachable
    connectTimeoutMS=5000,
)

MODENA_PARSED_URI = pymongo.uri_parser.parse_uri(
    MODENA_URI,
    default_port=27017
)
MODENA_PARSED_URI['host'], MODENA_PARSED_URI['port'] = \
    MODENA_PARSED_URI.pop('nodelist')[0]
MODENA_PARSED_URI['name'] = MODENA_PARSED_URI.pop('database')
del MODENA_PARSED_URI['collection'], MODENA_PARSED_URI['options'], MODENA_PARSED_URI['fqdn']

##
# @addtogroup python_interface_library
# @{

class ArgPosNotFound(Exception):
    pass

def existsAndHasArgPos(i: dict, name: str) -> int:
    """Function checking whether the model inputs corresponds to the arguments.

    @param i     dict  inputs, output or paramteers of a surrogate model.
    @param name  str   obtained from regex, (.*), of function arguments.

    @return int        argument position of the 'name' in the function
    """
    if name not in i or 'argPos' not in i[name]:
        raise ArgPosNotFound(f"[{name}]['argPos'] not found")
    return i[name]['argPos']


def checkAndConvertType(kwargs, name, cls):
    """
    @brief    Method used to prepare the method to be stored in the database

    @details
              The function operates on the dictionary 'kwargs' by checking if
              the key 'name' and the class 'cls', as well as the value of the
              key in the dictionary is the same.
              Subsequently, the method changes the name of the key, this is
              done for practical purposes.

    @param kwargs (dict) dictionary containing the key to be transformed
    @param name   (str)  name of strategy, i.e. the key in kwargs
    @param cls    class type
    """
    if name not in kwargs:
        raise TypeError(
            f"'{name}' is a required argument of type {cls.__name__}"
        )
    if not isinstance(kwargs[name], cls):
        raise TypeError(
            f"'{name}' must be of type {cls.__name__}, "
            f"got {type(kwargs[name]).__name__}"
        )
    kwargs['meth_' + name] = kwargs[name].to_dict()
    del kwargs[name]


def loadType(obj, name, cls):
    """Function that helps loading strategy "name" from model "obj".
    Returns an instance of the type "cls" appropriate strategy.

    @param obj (instance) instance of surrogate model
    @param name (str) name of the strategy
    @param cls (class type) strategy class type

    @returns instance of a strategy
    """
    #print 'In loadType ' + name
    n = '___' + name
    if hasattr(obj, n):
        return getattr(obj, n)
    else:
        var = getattr(obj, 'meth_' + name)            # get strategy dictionary
        #print obj._get_changed_fields()
        var = load_object(var)            # de-serialise object from dictionary
        #print obj._get_changed_fields()
        setattr(obj, n, var)
        return var


class EmbDoc(DynamicEmbeddedDocument):
    """Class wrapper for DynamicEmbeddedDocument from MongeEngine"""
    meta = {'allow_inheritance': False}


class GrowingList(list):
    """Class list that is automatically extended when index is out of range."""
    def __setitem__(self, index, value):
        if index >= len(self):
            self.extend([None]*(index + 1 - len(self)))
        list.__setitem__(self, index, value)


class IndexSet(Document):
    """Class based on 'Document' from MongoEngine.



    @var name
    @var names (list) list of specie names (strings)
    @var meta
    """
    # Database definition
    name  = StringField(primary_key=True)
    names = ListField(StringField(required=True))
    meta  = {'allow_inheritance': True}

    @abc.abstractmethod
    def __init__(self, *args, **kwargs):
        """Constructor

        @var ___index___ (dict) key value pairs for species: "name: index".
        """
        self.___index___ = {j: i for i, j in enumerate(kwargs['names'])}
        super().__init__(*args, **kwargs)
        self.save()


    def get_name(self, index):
        """Method obtaining name of a specie in the index set.

        @param index (int) index for of a specie in the index set.
        @returns (str) name of the specie "index".
        """
        try:
            return self.names[index]
        except IndexError:
            raise IndexError(f'{index} is not in index set {self.name!r}') from None


    def get_index(self, name):
        """Method obtaining index for a specie in the index set.

        @param name (str) name of a specie in the index set.
        @returns (int) index for specie "name" in "names" list
        """
        try:
            return self.___index___[name]
        except KeyError:
            raise KeyError(f'{name!r} is not in index set {self.name!r}') from None


    def iterator_end(self):
        """Method returning length of the "names" list."""
        return len(self.names)


    def iterator_size(self):
        """Method returning length of the "names" list."""
        return len(self.names)


    @classmethod
    def exceptionLoad(self, indexSetId):
        """Method raising a exception when a surrogate model has not been
        instantiated
        """
        return 401


    @classmethod
    def load(self, indexSetId):
        """Method loading a index set object from the database.
        @param indexSetId (str) id of the index set that is to be loaded.
        """
        return self.objects.get(name=indexSetId)


# Fitting data is not stored here to allow excluding it in load since it
# is not possible to exclude inputs.*.fitData
class MinMax(EmbeddedDocument):
    """Class containing minimum and maximum values of the variables in a
    surrogate function.

    The parent class comes from MongoEngine and makes it possible to embed the
    document into a existing database collection.

    @var min (float) MongoEngine data field for a float, required by default
    @var max (float) MongoEngine data field for a float, required by default
    """
    min = FloatField(required=True)
    max = FloatField(required=True)


class MinMaxOpt(EmbeddedDocument):
    """Class containing minimum and maximum values of the variables in a
    surrogate function.

    The parent class comes from MongoEngine and makes it possible to embed the
    document into a existing database collection.

    @var min (float) MongoEngine data field for a float (not required)
    @var max (float) MongoEngine data field for a float (not required)
    """
    min = FloatField()
    max = FloatField()


class MinMaxArgPos(EmbeddedDocument):
    """Class containing minimum and maximum values of the variables in a
    surrogate function.

    The parent class comes from MongoEngine and makes it possible to embed the
    document into a existing database collection.

    @var min (float) MongoEngine data field for a float, required by default
    @var max (float) MongoEngine data field for a float, required by default
    @var argPos (int) MongoEngine data field, specifies argument position
    @var index (document) Reference to a "IndexSet" document.
    """
    min = FloatField(required=True, default=None)
    max = FloatField(required=True, default=None)
    argPos = IntField(required=True)
    index = ReferenceField(IndexSet)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def printIndex(self):
        _log.debug('%s', self.index)


class MinMaxArgPosOpt(EmbeddedDocument):
    """
    @brief  Class containing minimum and maximum values of the variables in a
            surrogate function.

    The parent class comes from MongoEngine and makes it possible to embed the
    document into a existing database collection.

    @var min (float) MongoEngine data field for a float, required by default
    @var max (float) MongoEngine data field for a float, required by default
    @var argPos (int) MongoEngine data field, specifies argument position
    @var index (document) Reference to a "IndexSet" document.
    """

    min = FloatField()
    max = FloatField()
    argPos = IntField()
    index = ReferenceField(IndexSet)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def printIndex(self):
        _log.debug('%s', self.index)

'''
Currently not working
'''
class IOP(DictField):

    def __init__(self, field=None, *args, **kwargs):
        #if not isinstance(field, BaseField):
        #    self.error('Argument to MapField constructor must be a valid '
        #               'field')
        super().__init__(field=field, *args, **kwargs)


    def size(self):
        size = 0
        for k in self._fields.keys():
            if 'index' in v:
                size += v.index.iterator_size()
            else:
                size += 1

        return size


    def iteritems(self):
        for k in self._fields.keys():
            if 'index' in v:
                for idx in v.index.names:
                    yield f'{k}[{idx}]', v
            else:
                yield k, v


    def keys(self):
        for k, v in self._fields.items():
            if 'index' in v:
                for idx in v.index.names:
                    yield f'{k}[{idx}]'
            else:
                yield k


class SurrogateFunction(DynamicDocument):
    """Base class for surrogate functions.

    @brief   A surrogate function contains the algebraic representation of the
             surrogate model, i.e. the actual code that is employed by the
             surrogate model. It also contains the global boundaries defining
             the space in which the surrogate model is valid.

    @var     name (str) Name of the surrogate function ('_id' of the function)
    @var     parameters (field) Maps a embedded document field.
    @var     functionName (string) Name of the surrogate function.
    @var     libraryName (string) Collection name.
    @var     indices (field) Reference to 'IndexSet' document.
    @var     meta mongoengine-specific variable
    """

    name = StringField(primary_key=True)
    inputs = MapField(EmbeddedDocumentField(MinMaxArgPosOpt))
    outputs = MapField(EmbeddedDocumentField(MinMaxArgPos))
    parameters = MapField(EmbeddedDocumentField(MinMaxArgPos))
    functionName = StringField(required=True)
    libraryName = StringField(required=True)
    indices = MapField(ReferenceField(IndexSet))
    Ccode = StringField()
    meta = {'allow_inheritance': True}

    @abc.abstractmethod
    def __init__(self, *args, **kwargs):
        """
        @brief   Initialise a surrogate model from module or database.
        """
        if '_cls' in kwargs:
            _needs_save = False
            if not Path(kwargs["libraryName"]).is_file():
                ln = self.compileCcode(kwargs)
                kwargs["libraryName"] = ln
                _needs_save = True
            super().__init__(*args, **kwargs)
            if _needs_save:
                # Persist the compiled library path to MongoDB so subsequent
                # loads find the library without recompiling.
                # surrogateFunction is a ReferenceField (separate document) —
                # updating kwargs alone only affects this in-memory instance.
                # We do this after super().__init__() so self.pk is available.
                type(self).objects(pk=self.pk).update_one(
                    set__libraryName=ln
                )
        else:
            super().__init__()

            argPos = kwargs.pop('argPos', False)
            if not argPos:
                nInp = 0;
                for k, v in kwargs['inputs'].items():
                    if 'argPos' in v:
                        raise Exception(
                            f'argPos in function for inputs {k} (old format)'
                            ' -- delete argPos from function'
                        )
                    if not 'index' in v:
                        v['argPos'] = nInp
                        nInp += 1

            for k, v in kwargs['inputs'].items():
                if 'index' in v:
                    v['argPos'] = nInp
                    nInp += v['index'].iterator_size()

            for k, v in kwargs['inputs'].items():
                if not isinstance(v, MinMaxArgPosOpt):
                    self.inputs[k] = MinMaxArgPosOpt(**v)

            for k, v in kwargs['outputs'].items():
                if not isinstance(v, MinMaxArgPos):
                    self.outputs[k] = MinMaxArgPos(**v)

            for k, v in kwargs['parameters'].items():
                if not isinstance(v, MinMaxArgPos):
                    self.parameters[k] = MinMaxArgPos(**v)

            if 'indices' in kwargs:
                for k, v in kwargs['indices'].items():
                    self.indices[k] = kwargs['indices'][k]

            self.initKwargs(kwargs)

            for k in self.inputs.keys():
                self.checkVariableName(k)

            for k in self.outputs.keys():
                self.checkVariableName(k)

            for k in self.parameters.keys():
                self.checkVariableName(k)

            self.Ccode = kwargs['Ccode']
            self.save()


    @abc.abstractmethod
    def initKwargs(self, kwargs):
        """
        @brief   Method that is overwritten by children.
        """
        raise NotImplementedError('initKwargs not implemented!')


    def indexSet(self, name):
        """
        @brief   Method returning index for a specie in IndexSet.
        @param   name (str) Name of a specie in 'IndexSet'.
        @return  index (int) of specie 'name'.
        """
        return self.indices[name]


    def checkVariableName(self, name):
        """
        @brief   Method checking whether 'name' exists in the 'IndexSet'
        """
        m = re.search(r'[(.*)]', name)
        if m and not m.group(1) in self.indices:
            raise Exception(f'Index {m.group(1)} not defined')


    def inputs_iterAll(self):
        """
        @brief   Method returning an iterator over the SurrogateFunction inputs
        """
        for k, v in self.inputs.items():
            if 'index' in v:
                for idx in v.index.names:
                    yield f'{k}[{idx}]', v
            else:
                yield k, v


    def inputs_size(self):
        """
        @brief   Calculate the size of the input vector
        @return  (int) number of arguments the function takes
        """
        size = 0
        for k, v in self.inputs.items():
            if 'index' in v:
                size += v.index.iterator_size()
            else:
                size += 1

        return size


    @classmethod
    def exceptionLoad(self, surrogateFunctionId):
        """Method raising exception when a surrogate function is not
        instantiated.
        """
        return 201


    @classmethod
    def load(self, surrogateFunctionId):
        """Method loading a surrogate function from the database.

        @param surrogateFunctionId (str) name ('_id') of a surrogate function.
        @returns instance of surrogate function
        """
        return self.objects.get(_id=surrogateFunctionId)


def _compile_c_surrogate(source_c, output_so, include_dir, lib_dir):
    """Compile a single-file C surrogate to a shared library.

    Uses the C compiler that built the current Python interpreter (via
    sysconfig) so the ABI is guaranteed to match.  No CMake required.

    Args:
        source_c:    Path to the rendered .c file.
        output_so:   Destination path for the compiled .so / .dylib.
        include_dir: Directory containing modena.h directly (i.e. <prefix>/include/modena, not <prefix>/include).
        lib_dir:     Directory containing libmodena.so.

    Raises:
        RuntimeError: if the compiler exits non-zero or times out.
    """
    import sys
    import sysconfig
    import shutil
    from subprocess import run, CalledProcessError, TimeoutExpired

    cc_raw   = sysconfig.get_config_var('CC') or shutil.which('cc') or 'cc'
    ccshared = sysconfig.get_config_var('CCSHARED') or '-fPIC'
    shared   = '-dynamiclib' if sys.platform == 'darwin' else '-shared'

    python_include = sysconfig.get_path('include')

    cmd = (
        cc_raw.split()
        + ccshared.split()
        + [shared, '-O2',
           '-o', str(output_so),
           str(source_c),
           f'-I{include_dir}',
           f'-I{python_include}',
           f'-L{lib_dir}', '-lmodena']
    )

    _log.debug('compile surrogate: %s', ' '.join(cmd))
    try:
        result = run(cmd, capture_output=True, text=True, timeout=60, check=True)
        if result.stderr:
            _log.debug('compiler stderr:\n%s', result.stderr.rstrip())
    except CalledProcessError as exc:
        if exc.stdout:
            _log.error('compiler stdout:\n%s', exc.stdout)
        if exc.stderr:
            _log.error('compiler stderr:\n%s', exc.stderr)
        raise RuntimeError(
            f'Compiler failed for surrogate {Path(source_c).name} '
            f'(exit {exc.returncode})'
        ) from exc
    except TimeoutExpired as exc:
        raise RuntimeError(
            f'Compiler timed out (>60 s) for surrogate {Path(source_c).name}'
        ) from exc


class CFunction(SurrogateFunction):
    """
    @brief   Class for defining Surrogate Functions where the executable code
             is a C-function.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def initKwargs(self, kwargs):
        """
        @brief   Prepare meta-information about the function for the purpose of
                 instantiating a new object.

        @param   kwargs (dict) initialisation dictionary.
        """
        if 'Ccode' not in kwargs:
            raise TypeError("CFunction requires a 'Ccode' keyword argument")

        ln = self.compileCcode(kwargs)
        fn = re.search(
            r'void\s*(.*)\s*\('
            r'\s*const\s*modena_model_t\s*\*\s*model\s*,'
            r'\s*const\s*double\s*\*\s*inputs\s*,'
            r'\s*double\s*\*\s*outputs\s*\)',
            kwargs['Ccode']
        ).group(1)
        fn = fn.strip(' \t\n\r')

        self.name = fn
        self.libraryName = ln
        self.functionName = fn


    def compileCcode(self, kwargs):
        """
        @brief   Helper function to compile a model into local library.
        @return  (str) path to the compiled surrogate shared library.
        """
        m = hashlib.sha256()
        m.update(kwargs['Ccode'].encode('utf-8'))
        h = m.hexdigest()[:32]

        # Resolve the output directory from the registry so the user can
        # override via modena.toml [surrogate_functions] lib_dir or the
        # MODENA_SURROGATE_LIB_DIR env var.
        from modena.Registry import ModelRegistry
        surrogate_dir = ModelRegistry().surrogate_lib_dir
        func_dir  = surrogate_dir / ('func_' + h)
        source_c  = func_dir / (h + '.c')
        output_so = func_dir / ('lib' + h + '.so')

        if not output_so.exists():
            func_dir.mkdir(parents=True, exist_ok=True)

            env   = jinja2.Environment(lstrip_blocks=True, trim_blocks=True)
            child = env.from_string(r'''
{% extends Ccode %}
{% block variables %}
const double* parameters = model->parameters;
{% for k, v in pFunction.inputs.items() %}
{% if 'index' in v %}
const size_t {{k}}_argPos = {{v.argPos}};
const double* {{k}} = &inputs[{{k}}_argPos];
const size_t {{k}}_size = {{ v.index.iterator_size() }};
{% else %}
const size_t {{k}}_argPos = {{v['argPos']}};
const double {{k}} = inputs[{{k}}_argPos];
{% endif %}
{% endfor %}
{% endblock %}
            ''')
            parent = env.from_string(kwargs['Ccode'])
            child.stream(pFunction=kwargs, Ccode=parent).dump(str(source_c))

            _compile_c_surrogate(
                source_c  = source_c,
                output_so = output_so,
                include_dir = Path(modena.MODENA_INCLUDE_DIR),
                lib_dir     = Path(modena.MODENA_LIB_DIR),
            )

        return str(output_so)


class Function(CFunction):
    """
    @todo This is a draft for a class that can parse simple functions and
          write the Ccode that is compiled by CFunction.
    """
    def __init__(self, *args, **kwargs):
        if '_cls' in kwargs:
            super().__init__(*args, **kwargs)
        if 'libraryName' in kwargs:
            super().__init__(*args, **kwargs)
        else:
            # This is a bad check, make a better one...
            if 'function' not in kwargs:
                raise Exception('Algebraic representation not found')

            def cDouble(VAR):
                return '\n'.join(
                    f'const double {V} = {VAR}[{kwargs[VAR][V]["argPos"]}];'
                    for V in kwargs[VAR]
                )

            def outPut(OUT):
                return '\n'.join(
                    f'outputs[{kwargs["outputs"][O]["argPos"]}] = {self.Parse(kwargs["function"][O])};'
                    for O in kwargs[OUT]
                )

            # Main body of the Ccode
            Ccode='''
#include "modena.h"
#include "math.h"

void {name}
(
    const modena_model* model,
    const double* inputs,
    double *outputs
)
{{
{inputs}
{parameters}
{outputs}
}}
'''
            kwargs['Ccode'] = Ccode.format(
                name=kwargs['function']['name'],
                inputs=cDouble('inputs'),
                parameters=cDouble('parameters'),
                outputs=outPut('outputs')
            )

            super().__init__(*args, **kwargs)


    def Parse(self, formula, debug=False, model='', stack={}, delim=0, \
              var=r'[A-Za-z]+\d*',add=r'\+',sub=r'-',mul=r'\*',\
              div=r'/',pow=r'\^',dig=r'\d+\.?\d*'\
        ):
        operators = rf'{add}|{sub}|{mul}|{div}|{pow}'
        ldel=r'\('
        rdel=r'\)'

        #Test explicitly for empty string. Returning error.
        empty = re.match(r'\s',formula)
        if empty:
            _log.error('surrogate Ccode string is empty')
            return

        formula = re.sub(r'\s+','',formula)

        # Initialise a dictionary stack.
        stack = stack or {}

        # Python has no  switch - case construct.  Match all possibilities first and
        # test afterwards:
        re_var = re.match(var,formula)
        re_dig = re.match(dig,formula)
        re_ldel = re.match(ldel,formula)
        re_rdel = re.match(rdel,formula)
        re_oper = re.match(operators,formula)

        # Parameter followed by an optional number. Allow 'p' or 'p0' as variable names
        if re_var:
            tail = formula[len(re_var.group(0)):]
            head = re_var.group(0)

        elif re_dig:
            tail = formula[len(re_dig.group(0)):]
            head = re_dig.group(0)

        elif re_oper:
            head = re_oper.group(0)
            tail = formula[1:]

        # Left delimiter.
        elif re_ldel:
            head = re_ldel.group(0)
            tail  = formula[1:]
            delim += 1

        # Right delimiter followed by an optional number (default is 1).
        elif re_rdel:
            head = re_rdel.group(0)
            tail  = formula[len(re_rdel.group(0)):]
            delim -= 1

            # Testing if there is a parenthesis imbalance.
            if delim < 0:
                raise Exception('Unmatched parenthesis.')

        # Wrong syntax. Returning an error message.
        else:
            raise Exception('The expression syntax is not suported.')

        model += head

        # The formula has not been consumed yet. Continue recursive parsing.
        if len(tail) > 0:
            return self.Parse(tail,debug,model,stack,delim)

        # Nothing left to parse. Stop recursion.
        else:
            return model


class SurrogateModel(DynamicDocument):
    """
    @brief  The surrogate model is the workhorse of the MoDeNa framework.
            It contains strategies for:
              * Initialisation
              * Parameter fitting
              * Out of bounds
            That are necessary in order to ensure that the parameters of the
            surrogate function is valid.
            It contains the "local boundaries", i.e. the space in which the 
            parameters of the surrogate model has been fitted and validated,
            for inputs, outputs and parameters.

    @var    ___refs___ (list) list of references to all instances of the class
    @var    _id (str) database collection definition
    @var    surrogateFunction reference to 'modena.SurrogateFunction' object
    @var    parameters (list) parameter values surrogate function from MBDoE
    @var    meta ensures surrogate models are saved in the same collection
    """
    ___refs___ = []

    _id = StringField(primary_key=True)
    surrogateFunction = ReferenceField(SurrogateFunction, required=True)
    parameters = ListField(FloatField())
    documentation = StringField(default='')
    last_fitted = DateTimeField()
    meta = {'allow_inheritance': True}

    def __init__(self, *args, **kwargs):
        """
        @brief     Create a new Surrogate Model instance
        @details
                   This method is called also when a surrogate model is loaded
                   from the database.
        """
        self.___refs___.append(weakref.ref(self))


        if '_cls' in kwargs:
            super().__init__(*args, **kwargs)
            self.___indices___ = self.parseIndices(self._id)
            _log.info('Loaded model %s', self._id)

            if hasattr(self, 'importFrom'):
                __import__(self.importFrom)

        else:
            if '_id' not in kwargs:
                raise Exception('Need _id')

            _log.info('Initialising model %s', kwargs['_id'])

            if 'surrogateFunction' not in kwargs:
                raise Exception('Need surrogateFunction')
            if not isinstance(kwargs['surrogateFunction'], SurrogateFunction):
                raise TypeError('Need surrogateFunction')

            self.___indices___ = self.parseIndices(kwargs['_id'])

            if isinstance(kwargs.get('documentation'), Path):
                kwargs['documentation'] = kwargs['documentation'].read_text()

            kwargs['fitData'] = {}
            kwargs['inputs'] = {}
            for k, v in kwargs['surrogateFunction'].inputs_iterAll():
                kwargs['inputs'][k] = v.to_mongo()
                if 'index' in kwargs['inputs'][k]:
                    del kwargs['inputs'][k]['index']
                if 'argPos' in kwargs['inputs'][k]:
                    del kwargs['inputs'][k]['argPos']

            kwargs['outputs'] = {}
            for k, v in kwargs['surrogateFunction'].outputs.items():
                k = self.expandIndices(k)
                kwargs['fitData'][k] = []
                kwargs['outputs'][k] = MinMaxArgPosOpt(**{})

            for k, v in kwargs['inputs'].items():
                kwargs['fitData'][k] = []
                kwargs['inputs'][k] = MinMaxArgPosOpt(**v)

            for k, v in kwargs['inputs'].items():
                if 'argPos' in v and not v['argPos'] == kwargs['surrogateFunction'].inputs[k].argPos:
                    raise Exception('argPos in function and model must be the same -- delete argPos from model')

            self.initKwargs(kwargs)

            checkAndConvertType(
                kwargs,
                'initialisationStrategy',
                InitialisationStrategy
            )

            super().__init__(*args, **kwargs)

            subOutputs = {}
            for m in self.substituteModels:
                if not isinstance(m, SurrogateModel):
                    raise TypeError(
                        'Elements of substituteModels '
                        'must be derived from SurrogateModel'
                    )
                subOutputs.update(m.outputsToModels())

            # print('inputs for', self._id)
            # print('subOutputs=', subOutputs.keys())
            # print('inputs =', self.inputs.keys())

            # For each output in subsititute model, check if output in
            # defined in input list, if not add the output as an input.
            nInp = len(self.inputs)
            for o in subOutputs.keys():
                try:
                    self.inputs_argPos(o)
                    del self.inputs[o]
                    del self.fitData[o]

                    # For each input in substitute model
                    # check if input defined, if not add to input list
                    for k, v in subOutputs[o].inputs.items():
                        try:
                            self.inputs_argPos(k)
                        except ArgPosNotFound:
                            self.inputs[k] = subOutputs[o].inputs[k]
                            self.inputs[k].argPos = nInp
                            self.fitData[k] = subOutputs[o].fitData[k]
                            nInp += 1

                except ArgPosNotFound:
                    pass
                    #for k, v in subOutputs[o].outputs.items():
                    #    self.inputs[k] = subOutputs[o].outputs[k]
                    #    self.inputs[k].argPos = nInp
                    #    self.surrogateFunction.inputs[k] = subOutputs[o].outputs[k]
                    #    self.surrogateFunction.inputs[k].argPos = nInp
                    #    nInp += 1

            # print('inputs for', self._id)
            # print('subOutputs=', subOutputs.keys())
            # print('inputs =', self.inputs.keys())

            #self.surrogateFunction.save()
            # Only insert when the model doesn't already exist in the database.
            # Re-importing a model package (e.g. in a FireWorks subprocess) must
            # not overwrite fitted parameters or accumulated fitData.
            if not type(self).objects.filter(_id=self._id).count():
                self.save()

        # for k, v in self.inputs.items():
        #     print('inputs in model', k, self.inputs_argPos(k))
        # for k, v in self.surrogateFunction.inputs_iterAll():
        #     print('inputs in function', k, v.argPos)
        # print('parameters = [%s]' % ', '.join('%g' % v for v in self.parameters))


    @abc.abstractmethod
    def initKwargs(self, kwargs):
        raise NotImplementedError('initKwargs not implemented!')


    def parseIndices(self, name):
        """
        @brief    Parse the name of a function to determine the species, i.e.
                  indices, defined in the surrogate model '_id'.
        @param    name (str) name of a function, may or may not contain indexes
        @returns  (dict) indices {"A": "..."}
        """
        indices = {}
        m = re.search(r'\[(.*)\]', name)
        if m:
            for exp in m.group(1).split(','):
                m = re.search(r'(.*)=(.*)', exp)
                if m:
                    indices[m.group(1)] = m.group(2)
                else:
                    raise Exception(f'Unable to parse {exp}')

        return indices


    def expandIndices(self, name):
        """
        @brief    Method expanding the index sets in the surrogate model '_id'
        @param    name (str) name of a function, may or may not contain indexes
        @returns  name 
        """
        m = re.search(r'\[(.*)\]', name)
        if not m:
            ret = name
        else :
            try:
                ret = re.sub(
                    r'\[(.*)\]',
                    '[{}]'.format(','.join(
                        str(self.___indices___[exp])
                            for exp in m.group(1).split(',')
                    )),
                    name
                )
            except ArgPosNotFound as e:
                raise ArgPosNotFound(f'Unable to expand indices in {name}') from e

        return ret


    def expandIndicesWithName(self, name):
        """
        @brief   Parse "_id"
        """
        m = re.search(r'\[(.*)\]', name)
        if not m:
            ret = name
        else:
            try:
                ret = re.sub(
                    r'\[(.*)\]',
                    '[' + ','.join(
                        f'{exp}={self.___indices___[exp]}'
                        for exp in m.group(1).split(',')
                    ) + ']',
                    name
                )
            except ArgPosNotFound as e:
                raise ArgPosNotFound(f'Unable to expand indices in {name}') from e

        return ret


    def outputsToModels(self):
        """
        @brief   Map outputs to substitute models.
        @description
                      
        @returns (dict) outputs from the surrogate model.
        """
        o = { k: self for k in self.outputs.keys() }
        for m in self.substituteModels:
            o.update(m.outputsToModels())
        return o


    def inputsMinMax(self):
        """
        @brief    Determine input min and max accounting for substitute models
        @returns  (dict) dictionary of MinMax objects for each input.
        """

        def new(Min, Max):
            """
            @brief    Function creating a instance of a 'MinMax' object
            @returns  (obj) instance of MinMax
            """
            obj = type(str('MinMax'), (object,), {})
            obj.min = Min
            obj.max = Max
            return obj

        i = { k: new(v.min, v.max) for k, v in self.surrogateFunction.inputs_iterAll() }

        for m in self.substituteModels:
            for k, v in m.inputsMinMax().items():
                if k in i:
                    v.min = max(v.min, i[k].min)
                    v.max = min(v.max, i[k].max)
                else:
                    i[k] = new(v.min, v.max)

        return i


    def inputs_argPos(self, name: str) -> int:
        """
        @brief   Method mapping input argument position.
        @param   name  string  name of surrogate model (NOT function)
        @description

        """
        m = re.search(r'(.*)\[(.*=)?(.*)]', name)
        if m:
            try:
                base = m.group(1)
                return existsAndHasArgPos(self.surrogateFunction.inputs, base) \
                    + self.surrogateFunction.inputs[base].index.get_index(m.group(3))
            except (ArgPosNotFound, KeyError, AttributeError):
                raise ArgPosNotFound(f'argPos for {name} not found in inputs')
        else:
            try:
                return existsAndHasArgPos(self.inputs, name)
            except ArgPosNotFound:
                try:
                    return existsAndHasArgPos(self.surrogateFunction.inputs, name)
                except ArgPosNotFound:
                    raise ArgPosNotFound(f'argPos for {name} not found in inputs')


    def outputs_argPos(self, name: str) -> int:
        """
        @brief   Method mapping output argument positions.
        """
        try:
            return existsAndHasArgPos(self.outputs, name)
        except ArgPosNotFound:
            try:
                return existsAndHasArgPos(
                    self.surrogateFunction.outputs,
                    name
                )
            except ArgPosNotFound:
                raise ArgPosNotFound(f'argPos for {name} not found in outputs')


    def parameters_argPos(self, name: str) -> int:
        """
        @brief   Mapping parameter argument position.
        """
        try:
            return existsAndHasArgPos(self.parameters, name)
        except ArgPosNotFound:
            try:
                return existsAndHasArgPos(
                    self.surrogateFunction.parameters,
                    name
                )
            except ArgPosNotFound:
                raise ArgPosNotFound(f'argPos for {name} not found in parameters')


    def calculate_maps(self, sm):
        """
        @brief   Method mapping outputs to inputs wrt. 'substitute models'
        """
        map_outputs = []
        map_inputs = []

        for k in self.inputs:
            try:
                map_inputs.extend([self.inputs_argPos(k), sm.inputs_argPos(k)])
            except ArgPosNotFound:
                pass

        for k, v in sm.surrogateFunction.outputs.items():
            try:
                map_outputs.extend(
                    [v.argPos, self.inputs_argPos(sm.expandIndices(k))]
                )
            except ArgPosNotFound:
                pass

        return map_outputs, map_inputs


    def minMax(self) -> tuple:
        """
        @brief   Return min and max of input variables

        ── ABI CONTRACT ──────────────────────────────────────────────────────
        This tuple is consumed BY POSITION in src/src/model.c by
        modena_model_get_minMax() using PyTuple_GET_ITEM(tuple, index).
        The C code reads fields by raw integer index — there is no named
        access.  Reordering or inserting before the last element silently
        corrupts bounds and/or causes a segfault in the C application.

        Current layout (indices 0–4):
          0  list[float]   input minimums     (argPos-ordered)
          1  list[float]   input maximums     (argPos-ordered)
          2  keys view     input names        (argPos-ordered)
          3  keys view     output names       (argPos-ordered)
          4  keys view     parameter names    (argPos-ordered)

        To extend: append new elements at the END and update
        modena_model_get_minMax() in src/src/model.c in the same commit.
        ──────────────────────────────────────────────────────────────────────
        """
        l = self.surrogateFunction.inputs_size()
        minValues = [-9e99] * l
        maxValues = [9e99] * l

        for k, v in self.inputs.items():
            minValues[self.inputs_argPos(k)] = v.min
            maxValues[self.inputs_argPos(k)] = v.max

        return minValues, maxValues, \
            self.inputs.keys(), \
            self.outputs.keys(), \
            self.surrogateFunction.parameters.keys()


    def updateMinMax(self):
        """
        @brief   Update min and max bounds of the design and response space
        """
        if not self.nSamples:
            for v in self.inputs.values():
                v.min = 9e99
                v.max = -9e99

            for v in self.outputs.values():
                v.min = 9e99
                v.max = -9e99

            return

        for k, v in self.inputs.items():
            v.min = min(self.fitData[k])
            v.max = max(max(self.fitData[k]), v.min*1.000001)

        for k, v in self.outputs.items():
            v.min = min(self.fitData[k])
            v.max = max(self.fitData[k])


    def error(self, cModel, **kwargs):
        """
        @brief Generate an iterator that yields the error for each sample and output.

        @param cModel (modena_model_t)
        @param idxGenerator  iterator of sample indices (default: all samples)
        @param checkBounds   whether to check input bounds (default: True)
        @param metric        ErrorMetricBase instance; None → absolute residual
        @returns (iterator) yields one residual per (sample, output) combination
        """
        idxGenerator = kwargs.pop('idxGenerator', range(self.nSamples))
        checkBounds  = kwargs.pop('checkBounds', True)
        metric       = kwargs.pop('metric', None)

        i = [0.0] * self.surrogateFunction.inputs_size()

        # Precompute argPos and output ranges once — avoids repeated dict lookups
        # inside the innermost loop (O(nSamples × nInputs/nOutputs) saved).
        input_keys_and_pos = [(k, self.inputs_argPos(k)) for k in self.inputs]
        if metric is None:
            output_info = [(name, self.outputs_argPos(name)) for name in self.outputs]
        else:
            output_info = [
                (name, self.outputs_argPos(name),
                 v.max - v.min if v.max != v.min else 1.0)
                for name, v in self.outputs.items()
            ]

        for idx in idxGenerator:
            for k, pos in input_keys_and_pos:
                i[pos] = self.fitData[k][idx]

            out = cModel(i, checkBounds=checkBounds)

            if metric is None:
                for name, argPos in output_info:
                    yield self.fitData[name][idx] - out[argPos]
            else:
                for name, argPos, rng in output_info:
                    yield metric.residual(out[argPos], self.fitData[name][idx], rng)


    def __getattribute__(self, name):
        """Modified magic method. Call __getattribute__ from parent class, i.e.
        DynamocDocument, when accessing instance variables not starting with
        '___', e.g. ___index___ and ___references___.

        """
        if name.startswith( '___' ):
            return object.__getattribute__(self, name)
        else:
            return super().__getattribute__(name)


    def __setattribute__(self, name, value):
        """Modified magic method. Call __setattribute__ from parent class, i.e.
        DynamocDocument, when accessing instance variables not starting with
        '___', e.g. ___index___ and ___references___.
        """
        if name.startswith( '___' ):
            object.__setattribute__(self, name, value)
        else:
            super().__setattribute__(name, value)


    def exceptionOutOfBounds(self, oPoint):
        """
        @brief Returning exception when a surrogate function is out of bounds
        @returns (int) error code
        """
        oPointDict = {
            k: oPoint[self.inputs_argPos(k)] for k in self.inputs.keys()
        }
        self.outsidePoint = EmbDoc(**oPointDict)
        self.save()
        return 200


    @classmethod
    def exceptionLoad(cls, surrogateModelId):
        """
        @brief  Return exception when a surrogate model is not in the database.

        Writes a raw marker document (no ``_cls`` field) so that
        :meth:`loadFromModule` can identify which model needs initialisation
        after the binary exits with return code 201.

        @return (int) error code 201
        """
        collection = cls._get_collection()
        # replace_one with upsert creates a minimal document that deliberately
        # lacks the MongoEngine '_cls' field, used as a marker by loadFromModule.
        collection.replace_one(
            { '_id': surrogateModelId },
            { '_id': surrogateModelId },
            upsert=True
        )
        return 201


    @classmethod
    def exceptionParametersNotValid(cls, surrogateModelId):
        """
        @brief Return error code implying SurrogateModel parameters are invalid
        """
        return 202


    def callModel(self, inputs):
        """
        @brief    Calling surrogate model with inputs as a dict or sequence.
        @param    inputs  dict mapping input names to values, or a sequence
                  of floats already ordered by argPos.
        @details
                  The surrogate model is called
        @returns  outputs (dict) outputs from the surrogate model
        """
        _log.debug('callModel %s', self._id)
        # Instantiate the surrogate model
        cModel = modena.libmodena.modena_model_t(model=self)

        if isinstance(inputs, dict):
            i = [0.0] * self.surrogateFunction.inputs_size()
            for k, v in self.inputs.items():
                i[self.inputs_argPos(k)] = inputs[k]
        else:
            i = list(inputs)
            expected = self.surrogateFunction.inputs_size()
            if len(i) != expected:
                raise ValueError(
                    f"Model '{self._id}' expects {expected} inputs, got {len(i)}."
                )

        # Call the surrogate model
        out = cModel(i)

        outputs = {
            self.expandIndices(k): out[v.argPos]
            for k, v in self.surrogateFunction.outputs.items()
        }

        # print('outputs', outputs.keys())

        return outputs

    def __call__(self, inputs):
        """Alias for :meth:`callModel` — allows ``outputs = model(inputs)``."""
        return self.callModel(inputs)


    def updateFitDataFromFwSpec(self, fw_spec):
        """
        @brief   Method updating database with new input/output data from a
                 detailed simulation.

        @param   fw_spec  dict

{'_tasks': [{'surrogateModelId': 'flowRate', '_fw_name': '{{modena.Strategy.ParameterFitting}}'}], 'D': [0.01, 0.01, 0.01, 0.01], 'rho0': [3.5, 3.4, 3.5, 3.4], 'p0': [320000.0, 280000.0, 320000.0, 280000.0], 'p1Byp0': [0.04, 0.04, 0.03, 0.03], 'flowRate': [0.165409, 0.1525, 0.165409, 0.1525], '_fw_env': {}}

        @details
                  The method unpacks inputs and outputs from the fw_spec object
                  and extends the corresponding entry in the objects fitData
                  entry.
        """
        # Load the fitting data
        if not self["fitData"]:
            self.reload("fitData")

        #print(self.inputs.items())
        #print(self.fitData)
        for k, v in self.inputs.items():
            if type(fw_spec[k][0]) is list:
                self["fitData"][k].extend(fw_spec[k][0])
            else:
                self.fitData[k].extend(fw_spec[k])

        for k in self.outputs:
            if type(fw_spec[k][0]) is list:
                self.fitData[k].extend(fw_spec[k][0])
            else:
                self.fitData[k].extend(fw_spec[k])

        # Get first set
        #print(self.fitData)
        self.nSamples = len(next(iter(self.fitData.values())))


    def append_fit_data_point(self, point: dict) -> None:
        """Atomically append one simulation result to fitData in MongoDB.

        Uses a single ``$push`` so concurrent workers writing in parallel
        cannot interleave partial records — each complete data point lands
        atomically.  Only keys that are recognised inputs or outputs of
        this model are written; values added by substitute models are
        silently ignored.

        Args:
            point: dict mapping variable names to float values after one
                   simulation (inputs + outputs, as populated by task()).
        """
        push_ops = {}
        for k, v in point.items():
            if k in self.inputs or k in self.outputs:
                push_ops[f'fitData.{k}'] = float(v)
        if not push_ops:
            _log.warning(
                'append_fit_data_point: no recognised keys in point %s '
                'for model %s', list(point), self._id,
            )
            return
        type(self)._get_collection().update_one(
            {'_id': self._id},
            {'$push': push_ops},
        )

    def initialisationStrategy(self):
        """
        @brief   Load and return the initialisation strategy
        """
        return loadType(self, 'initialisationStrategy', InitialisationStrategy)


    def puts(self, verbose=0):
        """
        """

        lines = ["# " + "- - - "*10 + "#"]
        lines.append(f"Surrogate model id: {self._id}")
        lines.append(f"Model type:         {self.__class__.__name__}")

        sf = self.surrogateFunction.name
        if self.surrogateFunction.indices:
            sf = sf + "[" + ", ".join(self.surrogateFunction.indices.keys()) + "]"
            g = [
                " "*20 + f"{i} : {{ " + ", ".join(self.surrogateFunction.indices[i].names) + " }"
                for i in self.surrogateFunction.indices
            ]
            lines.append(f"Surrogate Function: {sf}")
            for gi in g:
                lines.append(gi)
        else:
            lines.append(f"Surrogate Function: {sf}")

        lines.append("\nInput-Output mapping:")
        lines.append("\t" + self._id + " : [" + ", ".join(self["inputs"].keys()) +
            "] --> [" + ", ".join(self["outputs"].keys()) + "]")

        sms = self.substituteModels
        if sms:
            for sm in sms:
                lines.append("\t" + sm._id + " : [" + ", ".join(sm["inputs"].keys()) +
                    "] --> [" + ", ".join(sm["outputs"].keys()) + "]")

        lines.append("\nFunction Signature:")
        lines.append("\t" + ", ".join(self["outputs"].keys()) +
            " = " + self.surrogateFunction.name +
            "(" + ", ".join(self["inputs"].keys()) +
            " ; " + ", ".join(self.surrogateFunction.parameters.keys()) + ")")

        lines.append("Inputs:")

        for (inp, mmp) in self.inputs.items():
            fi = self.surrogateFunction.inputs[inp]
            lines.append(f"        {inp} = [{mmp['min']:g}, {mmp['max']:g}] \\subset [{fi['min']:g}, {fi['max']:g}]")

            self.reload("fitData")
        lines.append("")
        lines.append("Outputs:")
        for (inp, mmp) in self.outputs.items():
            fo = self.surrogateFunction.outputs[inp]
            lines.append(f"        {inp} [{fo['min']:g}, {fo['max']:g}]")

        _log.info('%s', '\n'.join(lines))

    @staticmethod
    def to_str(bytes_or_str):
        if isinstance(bytes_or_str, bytes):             
            value = bytes_or_str.decode('utf-8')
        else:
            value = bytes_or_str
        return value    # Instance of str

    @staticmethod
    def to_bytes(bytes_or_str):
        if isinstance(bytes_or_str, str):
            value = bytes_or_str.encode('utf-8')
        else:
            value = bytes_or_str
        return value    # Instance of bytes

    @classmethod
    def load(cls, surrogateModelId: str) -> 'SurrogateModel':
        """
        @brief     Load SurrogateModel from database by "_id"
        @parameter surrogateModelId string _id field of the surrogate model
        @details
                   The load method excludes the 'fitData' field of the SM in
                   order to reduce the network traffic.

        @return    object  'SurrogateModel' or 'None'
        """
        try:
            return cls.objects.get(_id=surrogateModelId)
        except DoesNotExist:
            raise DoesNotExist(
                f"SurrogateModel '{surrogateModelId}' not found in database. "
                "Has it been initialised?"
            )


    @classmethod
    def loadFailing(cls) -> 'SurrogateModel | None':
        """
        @brief   Load all objects that have a 'outside point' key
        """
        return cls.objects(
            __raw__={'outsidePoint': {'$exists': True}}
        ).first()


    @classmethod
    def loadFromModule(cls):
        """
        @brief   Find the in-memory model instance for the model marked by
                 :meth:`exceptionLoad` and return it so the caller can build
                 an initialisation workflow.

        Reads the marker document written by :meth:`exceptionLoad` (a raw
        MongoDB document without a ``_cls`` field), imports the model package
        by the base name of the model ID, then searches all
        :meth:`get_instances` (both Forward and Backward mapping models) for
        the exact ``_id`` match.
        """
        collection = cls._get_collection()
        doc = collection.find_one({ '_cls': { '$exists': False}})
        if doc is None:
            raise RuntimeError(
                'loadFromModule: no marker document found — '
                'exceptionLoad may have failed'
            )
        model_id = doc['_id']
        # Strip any [key=value] index suffix to get the importable package name.
        mod_name = re.search(r'^(\w+)', model_id).group(1)
        _log.info('loadFromModule: importing %r for model %r', mod_name, model_id)
        try:
            __import__(mod_name)
        except ImportError:
            _log.error("loadFromModule: cannot import package %r", mod_name)
            raise
        # Search all registered model instances (Forward and Backward).
        instance = next(
            (m for m in cls.get_instances() if m._id == model_id),
            None,
        )
        if instance is None:
            raise RuntimeError(
                f"loadFromModule: model {model_id!r} not found in get_instances() "
                f"after importing {mod_name!r}"
            )
        return instance


    @classmethod
    def loadParametersNotValid(cls) -> 'SurrogateModel | None':
        """
        @brief   Method importing a surrogate model module.
        """
        return cls.objects(
            __raw__={'parameters': {'$size': 0}}
        ).exclude('fitData').first()


    @classmethod
    def get_instances(cls):
        """
        @brief   Iterate over all instances of SurrogateModel
        """
        for inst_ref in cls.___refs___:
            inst = inst_ref()
            if inst is not None:
                yield inst



class ForwardMappingModel(SurrogateModel):
    """
    @brief    A forward mapping model can be thought of as a constitutive
              equation, or a scaling function.
    @details
              @verbatim
                            f(X) => Y = 2 * X
                     +---------------------+
                     |                     |
                     |                     v
                   |-o---|             |---x------|
                      U                      Y
              @endverbatim
    """

    inputs = MapField(EmbeddedDocumentField(MinMaxArgPosOpt))
    outputs = MapField(EmbeddedDocumentField(MinMaxArgPosOpt))
    substituteModels = ListField(ReferenceField(SurrogateModel))
    meta = {'allow_inheritance': True}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def initKwargs(self, kwargs):
        if 'initialisationStrategy' not in kwargs:
            kwargs['initialisationStrategy'] = \
                EmptyInitialisationStrategy()


    def exactTasks(self, points):
        """
        @brief    Return Empty Fireworks workflow
        @details
                  In the SurrogateModel the exact task is responsible for
                  returning a computational workflow of detailed simulations.
                  However, Forward Mapping Models are **not** associated with
                  a detailed model. Consequently, this method should return an
                  empty workflow.
        """
        return Workflow([ Firework([ EmptyFireTask() ],
                                   name=f'{self._id} — (forward mapping)') ])


class BackwardMappingModel(SurrogateModel):
    """
    @brief   Definition of 'backward mapping' models.
    """
    # Database definition
    inputs = IOP(EmbeddedDocumentField(MinMaxArgPosOpt))
    outputs = MapField(EmbeddedDocumentField(MinMaxArgPosOpt))
    fitData = MapField(ListField(FloatField(required=True)))
    substituteModels = ListField(ReferenceField(SurrogateModel))
    outsidePoint = EmbeddedDocumentField(EmbDoc)
    meta = {'allow_inheritance': True}


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    def initKwargs(self, kwargs):
        """
        @brief   Prepare arguments
        """
        checkAndConvertType(kwargs, 'exactTask', FireTaskBase)

        checkAndConvertType(kwargs, 'outOfBoundsStrategy', OutOfBoundsStrategy)

        checkAndConvertType(kwargs,
            'parameterFittingStrategy',
            ParameterFittingStrategy
        )

        if 'nonConvergenceStrategy' in kwargs:
            checkAndConvertType(
                kwargs, 'nonConvergenceStrategy', NonConvergenceStrategy
            )


    def exactTasks(self, points):
        """
        @brief     Build a workflow, execute detailed simulation for each point
        @parameter points list new points
        @details
                   The input point is sent to the detailed simulation through
                   Fireworks 'fw_spec' variable.
        """
        nPoints = set(map(len,points.values()))
        assert len(nPoints) == 1, "Number of values not equal in all parameters"

        # De-serialise the exact task from dict
        et = load_object(self.meth_exactTask)

        n = nPoints.pop()
        tl = []
        for i in range(n):
            t = deepcopy(et)
            t['point']   = { k: points[k][i] for k in points }
            t['indices'] = self.___indices___
            t['modelId'] = self._id
            fw = Firework(t, name=f'{self._id} — sim {i + 1}/{n}')
            tl.append(fw)

        return Workflow(tl, name=f'{self._id} — exact simulations')


    def parameterFittingStrategy(self):
        """
        @brief  Load parameter fitting strategy
        """
        pfs = loadType(
            self,
            'parameterFittingStrategy',
            ParameterFittingStrategy
        )

        # Mongoengine injects strategy sub-object field paths into
        # _changed_fields when it encounters nested dicts it has not seen
        # before (new fields) or whose _fw_name changed (existing fields).
        # These paths do not correspond to model-level attributes and cause
        # AttributeError in _delta() during model.save().
        # Filter by root segment so both 'crossValidation' and
        # 'crossValidation._fw_name' are removed.
        _strategy_roots = {
            'improveErrorStrategy', 'crossValidation', 'acceptanceCriterion',
            'metric', 'optimizer', 'sampler',
        }
        # MongoEngine only sets _changed_fields as an instance attribute after
        # save() is called.  Unsaved model objects (first-time registration)
        # have no instance _changed_fields; fall back to empty list.
        self._changed_fields = [
            f for f in getattr(self, '_changed_fields', [])
            if f.split('.')[0] not in _strategy_roots
        ]

        return pfs


    def outOfBoundsStrategy(self):
        return loadType(self, 'outOfBoundsStrategy', OutOfBoundsStrategy)


    def nonConvergenceStrategy(self):
        """Return the strategy to apply when an exact simulation fails.

        Defaults to ``SkipPoint()`` when no strategy has been stored
        (i.e. models created before this field existed).
        """
        try:
            return loadType(self, 'nonConvergenceStrategy', NonConvergenceStrategy)
        except AttributeError:
            return SkipPoint()


    def extendedRange(self, outsidePoint, expansion_factor=1.2):
        """
                  Method expanding the design space. The method ONLY operates
                  on 'self.dict', this means that the database is NOT updated.
                  This is performed afterwards by 'run_task'.

                  The method will update the 'inputRanges' key in the
                  'self.dict'. Moreover, it will ensure that the min/max values
                  in'sampleRange' are consistent, meaning that the sampling is
                  performed in the correct region.

                              +------------+....+
                              |  *    *    |    .
                              |         *  |    .
                              |     *      |    .
                              |  *     *   |  X .
                              +------------+....+ <- new global max
                              ^            ^
                        global min      new min (temporary, only for sampling)

        @param    outsidePoint     The point that where found to be outside (X)
        @retval   expansion_factor The ratio that is used to expand the space beyond X

        @author   Sigve Karolius
        @author   Mandar Thombre
        @todo     Document...
        """

        sampleRange = {}
        limitPoint = {}

        for k, v in self.inputs.items():
            sampleRange[k] = {}
            outsideValue = outsidePoint[k]
            inputsMinMax = self.inputsMinMax()

            # If the value outside point is outside the range, set the
            # "localdict" max to the outside point value

            if outsideValue > v['max']:
                if outsideValue > inputsMinMax[k].max:
                    raise OutOfBounds(
                        'new value is larger than function min for %s' % k
                    )

                value = min(
                    outsideValue*expansion_factor,
                    inputsMinMax[k].max
                )

                sampleRange[k]['min'] = v['max']
                sampleRange[k]['max'] = value
                limitPoint[k] = value

            elif outsideValue < v['min']:
                if outsideValue < inputsMinMax[k].min:
                    raise OutOfBounds(
                        'new value is smaller than function max for %s' % k
                    )

                value = max(
                    outsideValue/expansion_factor,
                    inputsMinMax[k].min
                )

                sampleRange[k]['min'] = value
                sampleRange[k]['max'] = v['min']
                limitPoint[k] = value

            else:
                sampleRange[k]['min'] = v['min']
                sampleRange[k]['max'] = v['max']
                limitPoint[k] = random.uniform(v['min'], v['max'])

        return sampleRange, limitPoint


##
# @} # end of python_interface_library
# vim: filetype=python fileencoding=utf-8 syntax=on colorcolumn=79
# vim: ff=unix tabstop=4 softtabstop=0 expandtab shiftwidth=4 smarttab
# vim: nospell spelllang=en_us
