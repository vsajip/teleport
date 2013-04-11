import sys
import json
import base64


class ValidationError(Exception):
    """Raised by the model system. Stores the location of the error in the
    JSON document relative to its root for a more useful stack trace.

    First parameter is the error *message*, second optional parameter is the
    object that failed validation.
    """

    def __init__(self, message, *args):
        super(ValidationError, self).__init__(message)
        self.stack = []
        # Just the message or was there also an object passed in?
        self.has_obj = len(args) > 0
        if self.has_obj:
            self.obj = args[0]

    def _print_with_format(self, func):
        # Returns the full error message with the representation
        # of its literals determined by the passed in function.
        ret = ""
        # If there is a stack, preface the message with a location
        if self.stack:
            stack = ""
            for item in reversed(self.stack):
                stack += '[' + func(item) + ']'
            ret += "Item at %s " % stack
        # Main message
        ret += self.message
        # If an object was passed in, represent it at the end
        if self.has_obj:
            ret += ": %s" % func(self.obj)
        return ret

    def __str__(self):
        return self._print_with_format(repr)

    def print_json(self):
        """Print the same message as the one you would find in a
        console stack trace, but using JSON to output all the language
        literals. This representation is used for sending error
        messages over the wire.
        """
        return self._print_with_format(json.dumps)

class UnicodeDecodeValidationError(ValidationError):
    """A subclass of :exc:`~cosmic.exceptions.ValidationError` raised
    in place of a :exc:`UnicodeDecodeError`.
    """


class BaseModel(object):

    def __init__(self, data, **kwargs):
        self.data = data

    def serialize(self):
        """Serialize could be a classmethod like normalize, but by defining it
        this way, we are allowing a more natural syntax. Both of these work
        identically:
         
            >>> Animal.serialize(cat)
            >>> cat.serialize()

        """
        return self.data

    @classmethod
    def normalize(cls, datum): # pragma: no cover
        cls.validate(datum)
        return datum

    @classmethod
    def validate(cls, datum):
        pass


class Model(BaseModel):

    def serialize(self):
        # Serialize against model schema
        schema = self.get_schema()
        return schema.serialize_data(self.data)

    @classmethod
    def normalize(cls, datum):
        # Normalize against model schema
        schema = cls.get_schema()
        datum = schema.normalize_data(datum)
        cls.validate(datum)
        return cls(datum)

    @classmethod
    def get_schema(cls):
        return cls.schema



class Schema(Model):

    def __init__(self, data=None, **kwargs):
        # It is okay to omit type in the constructor, the Schema
        # will know its type from the match_type attibute
        if data == None:
            data = {u"type": self.match_type}
        super(Schema, self).__init__(data, **kwargs)
        # Everything except for the type becomes an option
        self.opts = self.data.copy()
        self.opts.pop("type", None)

    @classmethod
    def validate(cls, datum):
        if datum["type"] != cls.match_type:
            raise ValidationError("%s expects type=%s" % (cls, cls.match_type,))


    def normalize_data(self, datum):
        return self.model_cls.normalize(datum, **self.opts)

    def serialize_data(self, datum):
        return self.model_cls.serialize(datum, **self.opts)

    @classmethod
    def normalize(cls, datum):

        invalid = ValidationError("Invalid schema", datum)

        # Peek into the object before letting the real models
        # do proper validation
        if type(datum) != dict or "type" not in datum.keys():
            raise invalid
        st = datum["type"]

        # Simple model?
        simple = [
            IntegerSchema,
            FloatSchema,
            StringSchema,
            BinarySchema,
            BooleanSchema,
            ArraySchema,
            ObjectSchema,
            JSONDataSchema,
            SchemaSchema
        ]
        for simple_cls in simple:
            if st == simple_cls.match_type:
                return simple_cls.normalize(datum)

        # Model?
        if '.' in st:
            schema = SimpleSchema({"type": st})
            schema.match_type = st
            schema.model_cls = None
            return schema

        raise ValidationError("Unknown type", st)



class SimpleSchema(Schema):

    # COPY-PASTE
    @classmethod
    def normalize(cls, datum):
        # Normalize against model schema
        schema = cls.get_schema()
        datum = schema.normalize_data(datum)
        # Validate against model's custom validation function
        cls.validate(datum)
        # Instantiate
        return cls(datum)

    @classmethod
    def get_schema(cls):
        return ObjectSchema({
            "type": "object",
            "properties": [
                {
                    "name": "type",
                    "required": True,
                    "schema": StringSchema()
                }
            ]
        })

    def resolve(self, fetcher):
        if self.model_cls == None:
            self.model_cls = fetcher(self.match_type)


class SchemaSchema(SimpleSchema):
    match_type = "schema"
    model_cls = Schema




class ObjectModel(BaseModel):

    @classmethod
    def normalize(cls, datum, properties):
        """If *datum* is a dict, normalize it against *properties* and return
        the resulting dict. Otherwise raise a
        :exc:`~cosmic.exceptions.ValidationError`.

        *properties* must be a list of dicts, where each dict has three
        attributes: *name*, *required* and *schema*. *name* is a string
        representing the property name, *required* is a boolean specifying
        whether *datum* needs to contain this property in order to pass
        validation and *schema* is an instance of a
        :class:`~cosmic.models.Schema` subclass, such as :class:`IntegerSchema`.

        A :exc:`~cosmic.exceptions.ValidationError` will be raised if:

        1. *datum* is missing a required property
        2. *datum* has a property not declared in *properties*
        3. One of the properties of *datum* does not pass validation as defined
           by the corresponding *schema*

        """
        if type(datum) == dict:
            ret = {}
            required = {}
            optional = {}
            for prop in properties:
                if prop["required"] == True:
                    required[prop["name"]] = prop["schema"]
                else:
                    optional[prop["name"]] = prop["schema"]
            missing = set(required.keys()) - set(datum.keys())
            if missing:
                raise ValidationError("Missing properties", list(missing))
            extra = set(datum.keys()) - set(required.keys() + optional.keys())
            if extra:
                raise ValidationError("Unexpected properties", list(extra))
            for prop, schema in optional.items() + required.items():
                if prop in datum.keys():
                    try:
                        ret[prop] = schema.normalize_data(datum[prop])
                    except ValidationError as e:
                        e.stack.append(prop)
                        raise
            return ret
        raise ValidationError("Invalid object", datum)

    @classmethod
    def serialize(cls, datum, properties):
        """For each property in *properties*, serialize the corresponding
        value in *datum* (if the value exists) against the property schema.
        Return the resulting dict.
        """
        ret = {}
        for prop in properties:
            name = prop['name']
            if name in datum.keys() and datum[name] != None:
                ret[name] = prop['schema'].serialize_data(datum[name])
        return ret


class ObjectSchema(SimpleSchema):
    model_cls = ObjectModel
    match_type = "object"

    @classmethod
    def get_schema(cls):
        return ObjectSchema({
            "type": "object",
            "properties": [
                {
                    "name": "type",
                    "required": True,
                    "schema": StringSchema()
                },
                {
                    "name": "properties",
                    "required": True,
                    "schema": ArraySchema({
                        "items": ObjectSchema({
                            "properties": [
                                {
                                    "name": "name",
                                    "required": True,
                                    "schema": StringSchema()
                                },
                                {
                                    "name": "required",
                                    "required": True,
                                    "schema": BooleanSchema()
                                },
                                {
                                    "name": "schema",
                                    "required": True,
                                    "schema": SchemaSchema()
                                }
                            ]
                        })
                    })
                }
            ]
        })

    @classmethod
    def validate(cls, datum):
        """Raises :exc:`~cosmic.exception.ValidationError` if there are two
        properties with the same name.
        """
        super(ObjectSchema, cls).validate(datum)
        # Additional validation to check for duplicate properties
        props = [prop["name"] for prop in datum['properties']]
        if len(props) > len(set(props)):
            raise ValidationError("Duplicate properties")

    def resolve(self, fetcher):
        super(ObjectSchema, self).resolve(fetcher)
        for prop in self.opts["properties"]:
            prop["schema"].resolve(fetcher)



class ArrayModel(BaseModel):

    @classmethod
    def normalize(cls, datum, items):
        """If *datum* is a list, construct a new list by putting each element
        of *datum* through a schema provided as *items*. This schema may raise
        :exc:`~cosmic.exceptions.ValidationError`. If *datum* is not a list,
        :exc:`~cosmic.exceptions.ValidationError` will be raised.
        """
        if type(datum) == list:
            ret = []
            for i, item in enumerate(datum):
                try:
                    ret.append(items.normalize_data(item))
                except ValidationError as e:
                    e.stack.append(i)
                    raise
            return ret
        raise ValidationError("Invalid array", datum)

    @classmethod
    def serialize(cls, datum, items):
        """Serialize each item in the *datum* list using the schema provided
        in *items*. Return the resulting list.
        """
        return [items.serialize_data(item) for item in datum]

class ArraySchema(SimpleSchema):
    model_cls = ArrayModel
    match_type = u"array"

    @classmethod
    def get_schema(cls):
        return ObjectSchema({
            "properties": [
                {
                    "name": "type",
                    "required": True,
                    "schema": StringSchema()
                },
                {
                    "name": "items",
                    "required": True,
                    "schema": SchemaSchema()
                }
            ]
        })

    def resolve(self, fetcher):
        super(ArraySchema, self).resolve(fetcher)
        self.opts["items"].resolve(fetcher)





class IntegerModel(BaseModel):

    @classmethod
    def normalize(cls, datum, **kwargs):
        """If *datum* is an integer, return it; if it is a float with a 0 for
        its fractional part, return the integer part as an int. Otherwise,
        raise a
        :exc:`~cosmic.exceptions.ValidationError`.
        """
        if type(datum) == int:
            return datum
        if type(datum) == float and datum.is_integer():
            return int(datum)
        raise ValidationError("Invalid integer", datum)

    @classmethod
    def serialize(cls, datum):
        return datum

class IntegerSchema(SimpleSchema):
    model_cls = IntegerModel
    match_type = "integer"




class FloatModel(BaseModel):

    @classmethod
    def normalize(cls, datum, **kwargs):
        """If *datum* is a float, return it; if it is an integer, cast it to a
        float and return it. Otherwise, raise a
        :exc:`~cosmic.exceptions.ValidationError`.
        """
        if type(datum) == float:
            return datum
        if type(datum) == int:
            return float(datum)
        raise ValidationError("Invalid float", datum)

    @classmethod
    def serialize(cls, datum):
        return datum

class FloatSchema(SimpleSchema):
    model_cls = FloatModel
    match_type = "float"




class StringModel(BaseModel):

    @classmethod
    def normalize(cls, datum, **kwargs):
        """If *datum* is of unicode type, return it. If it is a string, decode
        it as UTF-8 and return the result. Otherwise, raise a
        :exc:`~cosmic.exceptions.ValidationError`. Unicode errors are dealt
        with strictly by raising
        :exc:`~cosmic.exceptions.UnicodeDecodeValidationError`, a
        subclass of the above.
        """
        if type(datum) == unicode:
            return datum
        if type(datum) == str:
            try:
                return datum.decode('utf_8')
            except UnicodeDecodeError as inst:
                raise UnicodeDecodeValidationError(unicode(inst))
        raise ValidationError("Invalid string", datum)

    @classmethod
    def serialize(cls, datum):
        return datum

class StringSchema(SimpleSchema):
    model_cls = StringModel
    match_type = "string"





class BinaryModel(BaseModel):

    @classmethod
    def normalize(cls, datum, **kwargs):
        """If *datum* is a base64-encoded string, decode and return it. If not
        a string, or encoding is wrong, raise
        :exc:`~cosmic.exceptions.ValidationError`.
        """
        if type(datum) in (str, unicode,):
            try:
                return base64.b64decode(datum)
            except TypeError:
                raise ValidationError("Invalid base64 encoding", datum)
        raise ValidationError("Invalid binary data", datum)

    @classmethod
    def serialize(cls, datum):
        """Encode *datum* in base64."""
        return base64.b64encode(datum)

class BinarySchema(SimpleSchema):
    model_cls = BinaryModel
    match_type = "binary"




class BooleanModel(BaseModel):

    @classmethod
    def normalize(cls, datum, **kwargs):
        """If *datum* is a boolean, return it. Otherwise, raise a
        :exc:`~cosmic.exceptions.ValidationError`.
        """
        if type(datum) == bool:
            return datum
        raise ValidationError("Invalid boolean", datum)

    @classmethod
    def serialize(cls, datum):
        return datum

class BooleanSchema(SimpleSchema):
    model_cls = BooleanModel
    match_type = "boolean"





class JSONData(BaseModel):

    def __repr__(self):
        contents = json.dumps(self.data)
        if len(contents) > 60:
            contents = contents[:56] + " ..."
        return "<JSONData %s>" % contents

    @classmethod
    def from_string(cls, s):
        if s == "":
            return None
        return cls.normalize(json.loads(s))

    @classmethod
    def normalize(cls, datum):
        # No need to validate
        return cls(datum)

    @classmethod
    def to_string(cls, s):
        if s == None:
            return ""
        return json.dumps(s.serialize())

class JSONDataSchema(SimpleSchema):
    model_cls = JSONData
    match_type = "json"



class ClassModel(ObjectModel):

    def __init__(self, **kwargs):
        self.data = {}
        self.props = {}
        for prop in self.properties:
            self.props[prop["name"]] = prop
        for key, value in kwargs.items():
            if key in self.props.keys():
                self.data[key] = value
            else:
                raise TypeError("Unexpected keyword argument '%s'" % key)

    def __getattr__(self, key):
        for prop in self.properties:
            if prop["name"] == key:
                return self.data.get(key, None)
        raise AttributeError()

    def __setattr__(self, key, value):
        for prop in self.properties:
            if prop["name"] == key:
                if value == None:
                    del self.data[key]
                else:
                    self.data[key] = value
                return
        super(ObjectModel, self).__setattr__(key, value)

    @classmethod
    def normalize(cls, datum):
        datum = cls.get_schema().normalize_data(datum)
        cls.validate(datum)
        return cls(**datum)

    def serialize(self):
        return self.get_schema().serialize_data(self.data)

    @classmethod
    def get_schema(cls):
        return ObjectSchema({
            "type": "object",
            "properties": cls.properties
        })


def normalize_json(schema, datum):
    if schema and not datum:
        raise ValidationError("Expected JSONData, found None")
    if datum and not schema:
        raise ValidationError("Expected None, found JSONData")
    if schema and datum:
        return schema.normalize_data(datum.data)
    return None

def serialize_json(schema, datum):
    if schema and not datum:
        raise ValidationError("Expected data, found None")
    if datum and not schema:
        raise ValidationError("Expected None, found data")
    if schema and datum:
        return JSONData(schema.serialize_data(datum))
    return None

