import collections
import html
import json
import math
import re

from .utilities import InvalidParamsException, ProgrammingError
from . import basics as syntaxTreesBasics


#####################################################################################
# references
#####################################################################################


class Value(syntaxTreesBasics.Field):
    """
    A reference to one other Node object, referenced by its Meta.name
    This is one of the two main ways to reference another Node. The other is Choice().
    """
    def __init__(self, value, kwargs=None, *args, **kwargs_):
        self.value = value
        self.kwargs = {} if kwargs is None else kwargs
        super().__init__(*args, **kwargs_)
        syntaxTreesBasics.register_that_a_value_was_referenced(value)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        """
        recurse the validation.
        """
        return syntaxTreesBasics.execute_function_on_node('validate', val, stack_objects, _get_kwargs_to_use(kwargs, self.kwargs), value=self.value)

    def get_documentation_description(self, node):
        doc = """An object: [[%s]].""" % (self.value,)
        return doc

    def construct_object_visualization_html_for_value(self, field_value, stack_objects):
        """
        constructs an HTML representation for this field's value in the stack_objects.
        This is called as a helper function of Field.construct_object_visualization_html()
        """
        html_fragments = stack_objects['html_fragments']
        # special case: null value
        if field_value is None:
            html_fragments.append('null');
        else:
            # recurse
            syntaxTreesBasics.execute_function_on_node(value=self.value, function='construct_object_visualization_html',
                                                       obj=field_value, stack_objects=stack_objects, kwargs={})


class Choice(syntaxTreesBasics.Field):
    """
    A reference to one other Node object, which can be one of several possible types,
    referenced by the attribute Meta.choice_of
    After parsing a JSON object of this type, its field 'type' will be set
    to the Meta.choice_type attribute of the matching Node subclass.
    This is one of the two main ways to reference another Node. The other is Value().
    """
    def __init__(self, choice, kwargs=None, *args, **kwargs_):
        self.choice = choice
        self.kwargs = {} if kwargs is None else kwargs
        super().__init__(*args, **kwargs_)
        syntaxTreesBasics.register_that_a_choice_was_referenced(choice)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        """
        recurse the validation.
        """
        return syntaxTreesBasics.execute_function_on_node('validate', val, stack_objects,
                                                          _get_kwargs_to_use(kwargs, self.kwargs),
                                                          choice=self.choice)

    def get_documentation_description(self, node):
        doc = """One of the [[%s]] objects.""" % (self.choice,)
        return doc

    def construct_object_visualization_html_for_value(self, field_value, stack_objects):
        """
        constructs an HTML representation for this field's value in the stack_objects.
        This is called as a helper function of Field.construct_object_visualization_html()
        """
        html_fragments = stack_objects['html_fragments']
        # special case: null value
        if field_value is None:
            html_fragments.append('null');
        else:
            # recurse
            syntaxTreesBasics.execute_function_on_node(choice=self.choice,
                                                       function='construct_object_visualization_html',
                                                       obj=field_value, stack_objects=stack_objects, kwargs={})


class List(syntaxTreesBasics.Field):
    """
    A list of several objects that are either of type 'value' or of type 'choice'.
    Optionally, may also have a 'primitive' version as well, which is not a list but a (str, int, float, bool).
    """
    def __init__(self, value=None, choice=None, primitive=None, min_length=None, kwargs=None, *args, **kwargs_):
        self.min_length = min_length
        self.value = value
        self.choice = choice
        self.primitive = primitive
        self.kwargs = {} if kwargs is None else kwargs
        super().__init__(*args, **kwargs_)
        if value is not None and choice is not None:
            raise ProgrammingError("A list field must reference either one Node via 'value' "
                                   "or multiple Nodes via 'choice', not both.")
        if value is None and choice is None and primitive is None:
            raise ProgrammingError("A list field must reference either one Node via 'value' "
                                   "or multiple Nodes via 'choice' or a primitive.")
        if value is not None:
            syntaxTreesBasics.register_that_a_value_was_referenced(value)
        if choice is not None:
            syntaxTreesBasics.register_that_a_choice_was_referenced(choice)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        """
        recurse the validation.
        """
        if not isinstance(val, list):
            raise InvalidParamsException("the value must be a list")
        if self.min_length is not None and len(val) < self.min_length:
            raise InvalidParamsException("the list must have at least %d element%s" % (self.min_length, "" if
                                            self.min_length == 1 else "s"))
        res = []
        for i, element in enumerate(val):
            # append the index to the node_trace, then recurse
            with syntaxTreesBasics.node_trace_step(stack_objects, "index %d" % i, element):
                # If a self.primitive is given and the object is a primitive value, use that field.
                # Otherwise use the node identified by 'value' or 'choice'
                check_for_primitive = isinstance(element, (str, int, float, bool))
                if self.primitive is None:
                    check_for_primitive = False
                elif self.value is None and self.choice is None:
                    check_for_primitive = True
                if check_for_primitive:
                    validated_element = self.primitive.validate(element, stack_objects=stack_objects, kwargs=kwargs)
                else:
                    validated_element = syntaxTreesBasics.execute_function_on_node('validate', element, stack_objects,
                                                                                   _get_kwargs_to_use(kwargs, self.kwargs),
                                                                                   value=self.value, choice=self.choice)
                res.append(validated_element)
        return res

    def get_documentation_description(self, node):
        if self.value is not None or self.choice is not None:
            if self.value is not None:
                doc = """A list of [[%s]] objects""" % (self.value,)
            else:
                doc = """A list of [[%s]] objects""" % (self.choice,)
            if self.primitive is not None:
                doc += " or %s" % (self.primitive.help,)
        else:
            doc = """A list of %s""" % (self.primitive.help,)
        doc += "."
        return doc

    def construct_object_visualization_html_for_value(self, field_value, stack_objects):
        """
        constructs an HTML representation for this field's value in the stack_objects.
        This is called as a helper function of Field.construct_object_visualization_html()
        """
        # special case: null
        if field_value is None:
            super().construct_object_visualization_html_for_value(field_value, stack_objects)
            return
        html_fragments = stack_objects['html_fragments']
        indent_string = stack_objects['indent_string']
        if len(field_value) == 0: # if the list is empty, don't add a linebreak
            html_fragments.append("""[]""")
        else:
            html_fragments.append("""[\n""")
            stack_objects['current_indent_level'] += 1
            for i, list_item in enumerate(field_value):
                html_fragments.append(indent_string * stack_objects['current_indent_level'])
                # recurse
                if self.primitive is not None and isinstance(list_item, (str, int, float, bool)):
                    self.primitive.construct_object_visualization_html_for_value(list_item, stack_objects)
                else:
                    syntaxTreesBasics.execute_function_on_node(value=self.value, choice=self.choice,
                                                               function='construct_object_visualization_html',
                                                               obj=list_item, stack_objects=stack_objects, kwargs={})
                if i != len(field_value) - 1:
                    html_fragments.append(",")
                html_fragments.append("\n")
            stack_objects['current_indent_level'] -= 1
            html_fragments.append(indent_string * stack_objects['current_indent_level'] + "]")


def _get_kwargs_to_use(given_kwargs, field_kwargs):
    """
    note that the field_kwargs are used by default, not the given_kwargs.
    field_kwargs can have PASS_ARG_ALONG to defer to given_kwargs,
    and given_kwargs can use OverwriteKeywordArgOfField to force an overwrite.
    """
    res = {}
    for k,v in field_kwargs.items():
        if v == syntaxTreesBasics.PASS_ARG_ALONG:
            res[k] = given_kwargs[k]
        else:
            res[k] = v
    for k,v in given_kwargs.items():
        if isinstance(v, syntaxTreesBasics.OverwriteKeywordArgOfField):
            res[k] = v.value
    return res


#####################################################################################
# special cases
#####################################################################################


class Mapping(syntaxTreesBasics.Field):
    """
    A dictionary-like mapping from String fields to arbitrary other fields.
    For example, Mapping(fields.String(), fields.Integer()) matches a JSON dict like the following:
    {
        'foo' : 1,
        'bar' : 2,
    }
    """
    def __init__(self, string_key, content, *args, **kwargs):
        self.string_key = string_key
        self.content = content
        if not isinstance(string_key, String) or not isinstance(content, syntaxTreesBasics.Field):
            raise ProgrammingError("the mapping must map a String field to an arbitrary field.")
        super().__init__(*args, **kwargs)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        if not isinstance(val, dict):
            raise InvalidParamsException("the value must be a dictionary")
        # note that IntegerAsString can turn different strings into the same one: ' 1', '1'
        # so you can't rely on this working out properly.
        res = {}
        for k,v in val.items():
            try:
                with syntaxTreesBasics.node_trace_step(stack_objects, 'key', k):
                    validated_key = self.string_key.validate(k, stack_objects=stack_objects, kwargs=kwargs)
            except InvalidParamsException as e:
                # we can assume that k is a string if it is provided by a user
                # because the dictionary was encoded as a JSON during server communication,
                # and JSON requires keys to be strings
                raise InvalidParamsException("could not parse the key '%s'. Exception was:\n%s" % (k, e,))
            with syntaxTreesBasics.node_trace_step(stack_objects, "value for key '%s'" % k, v):
                validated_value = self.content.validate(v, stack_objects=stack_objects, kwargs=kwargs)
            if validated_key in res:
                raise InvalidParamsException("after validating and simplifying, the key '%s' occurs more than once." % validated_key)
            res[validated_key] = validated_value
        # order the resulting dict
        # if the self.string_key is an IntegerAsString, transform the key to int first before sorting
        if isinstance(self.string_key, IntegerAsString):
            res = collections.OrderedDict(sorted(res.items(), key=lambda t: int(t[0])))
        else:
            res = collections.OrderedDict(sorted(res.items(), key=lambda t: t[0]))
        return res

    def get_documentation_description(self, node):
        keys = """<div class="nested-field-documentation">%s</div>""" % self.string_key.get_full_documentation_html(node)
        content = """<div class="nested-field-documentation">%s</div>""" % self.content.get_full_documentation_html(node)
        doc = """A mapping from string keys to content.\nThe string keys are:\n%s\nThe content is:\n%s""" % (keys, content,)
        return doc

    def construct_object_visualization_html_for_value(self, field_value, stack_objects):
        """
        constructs an HTML representation for this field's value in the stack_objects.
        This is called as a helper function of Field.construct_object_visualization_html()
        """
        # special case: null
        if field_value is None:
            super().construct_object_visualization_html_for_value(field_value, stack_objects)
            return
        html_fragments = stack_objects['html_fragments']
        indent_string = stack_objects['indent_string']
        if len(field_value) == 0: # if the list is empty, don't add a linebreak
            html_fragments.append("""{}""")
        else:
            html_fragments.append("""{\n""")
            stack_objects['current_indent_level'] += 1
            for i, (k, v) in enumerate(field_value.items()):
                html_fragments.append(indent_string * stack_objects['current_indent_level'])
                # escape special characters in the key
                k = html.escape(json.dumps(k, ensure_ascii=False))
                html_fragments.append('%s' % k)
                html_fragments.append(" : ")
                # recurse
                self.content.construct_object_visualization_html_for_value(v, stack_objects)
                if i != len(field_value) - 1:
                    html_fragments.append(",")
                html_fragments.append("\n")
            stack_objects['current_indent_level'] -= 1
            html_fragments.append(indent_string * stack_objects['current_indent_level'] + "}")


class PrimitiveValueOrGetter(syntaxTreesBasics.Field):
    """
    combines two Fields into one.
    If the value is a primitive (str, int, float, bool), uses the first field, otherwise the second field.
    This is intended for situations where you can either describe a variable quickly through a constant,
    or through a complex rule that describes how to derive the variable.
    """
    def __init__(self, primitive_field, complex_field, *args, **kwargs):
        self.primitive_field = primitive_field
        self.complex_field = complex_field
        super().__init__(*args, **kwargs)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        if isinstance(val, (str, int, float, bool)):
            return self.primitive_field.validate(val, stack_objects=stack_objects, kwargs=kwargs)
        else:
            return self.complex_field.validate(val, stack_objects=stack_objects, kwargs=kwargs)

    def get_documentation_description(self, node):
        simple = """<div class="nested-field-documentation">%s</div>""" % self.primitive_field.get_full_documentation_html(node)
        complex = """<div class="nested-field-documentation">%s</div>""" % self.complex_field.get_full_documentation_html(node)
        doc = """The simple variant is:\n%s\nThe complex variant is:\n%s""" % (simple, complex,)
        return doc

    def construct_object_visualization_html_for_value(self, field_value, stack_objects):
        """
        constructs an HTML representation for this field's value in the stack_objects.
        This is called as a helper function of Field.construct_object_visualization_html()
        """
        # special case: null
        if field_value is None:
            super().construct_object_visualization_html_for_value(field_value, stack_objects)
            return
        # if it's a primitive, use the primitive variant, else use the complex variant
        if isinstance(field_value, (str, int, float, bool)):
            self.primitive_field.construct_object_visualization_html_for_value(field_value, stack_objects)
        else:
            self.complex_field.construct_object_visualization_html_for_value(field_value, stack_objects)


class ArbitraryJson(syntaxTreesBasics.Field):
    def __init__(self, *args, **kwargs):
        for a in ['null']:
            if a in kwargs:
                raise ProgrammingError("can't overwrite this kwarg: %s" % a)
        kwargs['null'] = True
        super().__init__(*args, **kwargs)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        try:
            # dump to JSON and read again while preserving the order
            return json.loads(json.dumps(val, sort_keys=True), object_pairs_hook=collections.OrderedDict)
        except Exception as e:
            raise InvalidParamsException("the value must be JSON-serializable")

    def get_documentation_description(self, node):
        doc = "An arbitrary JSON-like object."
        return doc


#####################################################################################
# primitives
#####################################################################################


class Integer(syntaxTreesBasics.Field):
    def __init__(self, min=None, max=None, *args, **kwargs):
        self.min = min
        self.max = max
        super().__init__(*args, **kwargs)
        self.validate(min, allow_null=True)
        self.validate(max, allow_null=True)
        if min is not None and max is not None and min > max:
            raise ProgrammingError("the minimum is greater than the maximum")

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        if not isinstance(val, int):
            raise InvalidParamsException("the value must be an integer")
        if self.min is not None and self.min > val:
            raise InvalidParamsException("the value is below the minimum of %s" % self.min)
        if self.max is not None and self.max < val:
            raise InvalidParamsException("the value is above the maximum of %s" % self.max)
        return val

    def get_documentation_description(self, node):
        if self.min is not None and self.max is not None:
            doc = """An Integer in the range [%d ; %d].""" % (self.min, self.max,)
        elif self.min is not None:
            doc = """An Integer with minimum value %d.""" % self.min
        elif self.max is not None:
            doc = """An Integer with maximum value %d.""" % self.max
        else:
            doc = """An Integer value."""
        return doc


class Float(syntaxTreesBasics.Field):
    def __init__(self, min=None, max=None, *args, **kwargs):
        self.min = min
        self.max = max
        super().__init__(*args, **kwargs)
        self.validate(min, allow_null=True)
        self.validate(max, allow_null=True)
        if min is not None and max is not None and min > max:
            raise ProgrammingError("the minimum is greater than the maximum")

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        if not isinstance(val, (int, float)):
            raise InvalidParamsException("the value must be an int or a float")
        if isinstance(val, float):
            if math.isnan(val):
                raise InvalidParamsException("the value must not be NaN.")
            if math.isinf(val):
                raise InvalidParamsException("the value must not be infinite.")
        if self.min is not None and self.min > val:
            raise InvalidParamsException("the value is below the minimum of %s" % self.min)
        if self.max is not None and self.max < val:
            raise InvalidParamsException("the value is above the maximum of %s" % self.max)
        return val

    def get_documentation_description(self, node):
        if self.min is not None and self.max is not None:
            doc = """A Float in the range [%d ; %d].""" % (self.min, self.max,)
        elif self.min is not None:
            doc = """A Float with minimum value %d.""" % self.min
        elif self.max is not None:
            doc = """A Float with maximum value %d.""" % self.max
        else:
            doc = """A Float value."""
        doc += " Infinity and NaN are invalid."
        return doc


class Boolean(syntaxTreesBasics.Field):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        if not isinstance(val, bool):
            raise InvalidParamsException("the field must be a boolean value")
        return val

    def get_documentation_description(self, node):
        doc = """A Boolean value."""
        return doc


class MultipleChoiceSelection(syntaxTreesBasics.Field):
    """
    Matches any one value out of a hardcoded list of values.
    """
    def __init__(self, choices, *args, **kwargs):
        super().__init__(*args, null=True, validation_accepts_nulls=True, **kwargs)
        self.choices = choices

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        # Turn the value into a list
        if val is None:
            val = []
        if isinstance(val, str):
            val = [val]
        # Check that the value is acceptable
        if not isinstance(val, list) or any([a for a in val if a not in self.choices]):
            raise InvalidParamsException("The value is not valid. Acceptable values are None, "
                                         "one of the following values, or a list of any number of the following values:"
                                         "\n%s" % (', '.join(["'%s'" % a for a in self.choices]),))
        # Remove duplicates and ensure it's well-ordered
        if len(val) != 0:
            tmp = []
            for a in self.choices:
                if a in val:
                    tmp.append(a)
            val = tmp
        # Return the list
        return val

    def get_documentation_description(self, node):
        doc = "Acceptable values are None, one of the following values, " \
              "or a list of any number of the following values:" \
              "\n%s" % (', '.join(["'%s'" % a for a in self.choices]),)
        return doc


class String(syntaxTreesBasics.Field):
    def __init__(self, min_length=None, max_length=None, *args, **kwargs):
        self.min_length = min_length
        self.max_length = max_length
        super().__init__(*args, **kwargs)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        if not isinstance(val, str):
            raise InvalidParamsException("the value must be a string")
        if self.min_length is not None and self.min_length > len(val):
            raise InvalidParamsException("the value is below the minimum length of %d characters by %d characters" %
                                         (self.min_length, self.min_length - len(val),))
        if self.max_length is not None and self.max_length < len(val):
            raise InvalidParamsException("the value exceeds the maximum length of %d characters by %d characters" %
                                         (self.max_length, len(val) - self.max_length,))
        return val

    def get_documentation_description(self, node):
        if self.min_length is not None and self.max_length is not None:
            doc = """A String with minimum length %d and maximum length %d.""" % (self.min_length, self.max_length,)
        elif self.min_length is not None:
            doc = """A String with minimum length %d.""" % self.min_length
        elif self.max_length is not None:
            doc = """A String with maximum length %d.""" % self.max_length
        else:
            doc = """A String."""
        return doc


class RegexString(String):
    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        val = super().helper_for_validation(val, stack_objects=None, kwargs=None)
        try:
            re.compile(val)
        except re.error:
            raise InvalidParamsException("This is not a valid regular expression.")
        return val

    def check_regex_for_match(self, regex, s):
        return re.match(regex, s)

    def get_documentation_description(self, node):
        doc = """A Regular Expression. This uses Python's re.match() function in the backend."""
        return doc


class IntegerAsString(String):
    """
    this is basically an Integer() Field, but the value must be given as a string instead of a number.
    This is necessary because JSON does not allow non-string values as keys of mappings,
    so this is used to enable the Mapping Field to work with Integer values.
    """
    def __init__(self, min=None, max=None, *args, **kwargs):
        self.min = min
        self.max = max
        super().__init__(*args, **kwargs)
        self.validate(None if min is None else str(min), allow_null=True)
        self.validate(None if max is None else str(max), allow_null=True)
        if min is not None and max is not None and min > max:
            raise ProgrammingError("the minimum is greater than the maximum")

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        try:
            val = super().helper_for_validation(val)
            val = int(val)
        except (InvalidParamsException, ValueError):
            raise InvalidParamsException("the value must be a string that can be parsed into an integer")
        if self.min is not None and self.min > val:
            raise InvalidParamsException("the value is below the minimum of %s" % self.min)
        if self.max is not None and self.max < val:
            raise InvalidParamsException("the value is above the maximum of %s" % self.max)
        # return the integer as a string again, but possibly more nicely formatted this time
        val = str(val)
        return val

    def get_documentation_description(self, node):
        doc = """An Integer value, given as a String. This is necessary because JSON does not allow 
        non-string values as keys of mappings."""
        return doc


class StringFromSelection(String):
    def __init__(self, selection, *args, **kwargs):
        self.selection = selection
        super().__init__(*args, **kwargs)
        for a in selection:
            self.validate(a)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        val = super().helper_for_validation(val)
        if val not in self.selection:
            raise InvalidParamsException("the value '%s' is not valid. Valid values are:\n%s" %
                                         (val, ', '.join(["'%s'" % a for a in self.selection]),))
        return val

    def get_documentation_description(self, node):
        doc = """One of the following String values: %s""" % ', '.join("'%s'" % a for a in self.selection)
        return doc


class StringVariableName(String):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        val = super().helper_for_validation(val)
        syntaxTreesBasics.verify_variable_name_is_valid(val)
        return val

    def get_documentation_description(self, node):
        # use the error message you get when entering a wrong value as the documentation
        try:
            self.helper_for_validation("1*/-_!?[]aA.")
        except InvalidParamsException as e:
            doc = str(e)
            return doc
        return "error. failed to fail."
