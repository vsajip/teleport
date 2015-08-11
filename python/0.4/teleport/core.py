from __future__ import unicode_literals

import json
import pyrfc3339
from collections import OrderedDict

from .compat import test_integer, test_long, normalize_string
from .util import utc, format_multiple_errors, ForceReturn, Undefined, ValidationError, error_generator, IterableException



class Type(object):
    """Conceptually, an instance of this class is a value space, a set of
    JSON values. As such, the only method defined by the Teleport specification
    is :meth:`check`, everything else is extentions made by this
    implementation.

    When a type needs to access the :func:`t` function from one of its methods
    (for recursive serialization, for example), it should use the same
    :func:`t` function that was used to create it in the first place.

    Instances of :class:`~teleport.Type` have a :data:`t` attribute that is
    automatically set to this value, so you can access it from one of the
    methods below as :data:`self.t`.


    """

    def check(self, json_value):
        """
        Returns :data:`True` if *json_value* is a member of this type's value
        space and :data:`False` if it is not.

        .. code-block:: python

            >>> t("DateTime").check(u"2015-04-05T14:30")
            True
            >>> t("DateTime").check(u"2007-04-05T14:30 DROP TABLE users;")
            False
        """
        if self.__class__.from_json != Type.from_json:
            try:
                self.from_json(json_value)
                return True
            except Undefined:
                return False
        else:
            raise NotImplementedError("check or from_json necessary")

    def from_json(self, json_value):
        """Convert JSON value to native value. Raises :exc:`Undefined` if
        *json_value* is not a member of this type. By default, this method
        returns the JSON value unchanged.

        .. code-block:: python

            >>> t("DateTime").from_json(u"2015-04-05T14:30")
            datetime.datetime(2015, 4, 5, 14, 30)
        """
        if self.__class__.check != Type.check:
            if self.check(json_value):
                return json_value
            else:
                raise Undefined("Invalid whatever it is")      
        else:
            raise NotImplementedError("check or from_json necessary")

    def to_json(self, native_value):
        """Convert valid native value to JSON value. By default, this method
        returns the native value unchanged, assuming that it is already in
        the format expected by the :mod:`json` module.

        .. code-block:: python

            >>> t("DateTime").to_json(datetime.datetime(2015, 4, 5, 14, 30))
            u"2015-04-05T14:30"


        """
        return native_value



class ConcreteType(Type):
    """Subclass this to tell :class:`~teleport.Teleport` that your custom type
    is concrete.

    """

    def __init__(self, t):
        self.t = t



class GenericType(Type):
    """Subclass this to tell :class:`~teleport.Teleport` that your custom type
    is generic.

    """

    def __init__(self, t, param):
        """Takes a :class:`~teleport.TypeMap` *t*, and a JSON parameter *param*
        Raises :exc:`~teleport.Undefined` if the parameter is invalid. By default,
        the constructor sets :data:`self.param` to *param*. It may be useful to set
        other properties, which may be accessed later by :meth:`from_json` or other 
        methods.

        """
        self.t = t
        self.param = param



class ArrayType(GenericType):

    def __init__(self, t, param):
        self.space = t(param)

    @error_generator
    def from_json(self, json_value):

        if type(json_value) != list:
            yield Undefined("Must be list")
            return

        fail = False
        arr = []
        for i, item in enumerate(json_value):

            try:
                arr.append(self.space.from_json(item))
            except IterableException as errs:
                fail = True
                for err in errs:
                    yield err.prepend_location(i)

        if not fail:
            raise ForceReturn(arr)

    def to_json(self, value):
        return list(map(self.space.to_json, value))


class MapType(GenericType):

    def __init__(self, t, param):
        self.space = t(param)

    @error_generator
    def from_json(self, json_value):

        if type(json_value) != dict:
            yield Undefined("Must be dict")
            return

        fail = False
        m = {}
        for key, val in json_value.items():

            try:
                m[key] = self.space.from_json(val)
            except IterableException as errs:
                fail = True
                for err in errs:
                    yield err.prepend_location(key)

        if not fail:
            raise ForceReturn(m)

    def to_json(self, value):
        ret = {}
        for key, val in value.items():
            ret[key] = self.space.to_json(val)

        return ret


class StructType(GenericType):

    def __init__(self, t, param):
        expected = {'required', 'optional'}

        if type(param) != dict or not expected.issubset(set(param.keys())):
            raise Undefined()

        self.schemas = {}
        for kind in expected:
            if type(param[kind]) != dict:
                raise Undefined()

            for k, s in param[kind].items():
                self.schemas[k] = t(s)

        self.opt = set(param['optional'].keys())
        self.req = set(param['required'].keys())

        if not self.opt.isdisjoint(self.req):
            raise Undefined()

    @error_generator
    def from_json(self, json_value):

        if type(json_value) != dict:
            yield Undefined("Dict expected")
            return

        fail = False

        for k in self.req:
            if k not in json_value:
                fail = True
                yield Undefined("Missing field: {}".format(json.dumps(k)))

        for k in json_value.keys():
            if k not in self.schemas.keys():
                fail = True
                yield Undefined("Unexpected field: {}".format(json.dumps(k)))

        struct = {}
        for k, v in json_value.items():
            if k not in self.schemas.keys():
                continue

            try:
                struct[k] = self.schemas[k].from_json(v)
            except IterableException as errs:
                fail = True
                for err in errs:
                    yield err.prepend_location(k)

        if not fail:
            raise ForceReturn(struct)


    def to_json(self, value):
        ret = {}
        for k, v in value.items():
            ret[k] = self.schemas[k].to_json(v)

        return ret


class JSONType(ConcreteType):
    def check(self, value):
        return True


class IntegerType(ConcreteType):
    def check(self, value):
        return test_integer(value)


class DecimalType(ConcreteType):
    def check(self, value):
        return test_long(value)


class StringType(ConcreteType):

    def from_json(self, value):
        s = normalize_string(value)
        if s is not None:
            return s
        raise Undefined("Not a string")


class BooleanType(ConcreteType):
    def check(self, value):
        return type(value) == bool


class DateTimeType(ConcreteType):

    def from_json(self, value):
        try:
            return pyrfc3339.parse(value)
        except (TypeError, ValueError):
            raise Undefined("Invalid DateTime")

    def to_json(self, value):
        return pyrfc3339.generate(value, accept_naive=True, microseconds=True)


class SchemaType(ConcreteType):

    def check(self, value):
        try:
            t(value)
            return True
        except Undefined:
            return False


CORE_TYPES = {
    "JSON": JSONType,
    "Integer": IntegerType,
    "Decimal": DecimalType,
    "String": StringType,
    "Boolean": BooleanType,
    "DateTime": DateTimeType,
    "Schema": SchemaType,
    "Array": ArrayType,
    "Map": MapType,
    "Struct": StructType
}


class TypeMap(object):

    def __init__(self):
        self.type_map = {}
        self.type_map.update(CORE_TYPES)

    def __call__(self, schema):
        """When you call the :func:`t` function, you are actually calling this
        method. You will rarely want to override this directly.

        :param schema: a JSON value
        :return: a :class:`~teleport.Type` instance

        """
        s = normalize_string(schema)

        if s is not None:
            return self.concrete_type(s)
        elif type(schema) == dict and len(schema) == 1:
            name = list(schema)[0]
            param = schema[name]
            return self.generic_type(name, param)
        else:
            raise Undefined("Unrecognized schema {}".format(schema))

    def get_type_or_fail(self, name):
        cls = self.type_map.get(name, None)
        if cls is None:
            cls = self.get_custom_type(name)
        if cls is None:
            raise Undefined("Unknown type {}".format(name))
        return cls

    def concrete_type(self, name):
        cls = self.get_type_or_fail(name)
        if issubclass(cls, ConcreteType):
            return cls(self)
        else:
            raise Undefined("Not a concrete type: \"{}\"".format(name))

    def generic_type(self, name, param):
        cls = self.get_type_or_fail(name)
        if issubclass(cls, GenericType):
            return cls(self, param)
        else:
            raise Undefined("Not a generic type: \"{}\"".format(name))

    def get_custom_type(self, name):
        """Override this method to enable dynamic type search. It gets called
        if the requested type is neither a core type nor a type added by
        :meth:`register`. In that case, this is the last resort before
        :exc:`~teleport.core.Undefined` is thrown.

        :param name: a string
        :return: a subclass of :class:`~teleport.Type` or None
        """
        return None

    def register(self, name):
        """Used as a decorator to add a type to the type map.

        .. code-block:: python

            @t.register("Truth")
            class TruthType(ConcreteType):

                def check(self, value):
                    return value is True
        """
        def decorator(type_cls):
            self.type_map[name] = type_cls
            return type_cls
        return decorator


t = TypeMap()


