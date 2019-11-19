import collections
import html
import json
import re

from .utilities import get_error_message_details, InvalidParamsException, ProgrammingError


#####################################################################################
# GENERAL NOTICE
# This code was originally written as part of a larger website based on Django.
# I only made minor changes to make it usable outside of its original context.
# As a result, refactoring is in order.
# However, I won't bother to do that unless it turns out that this library becomes popular.
# (Don't fix what isn't broken.)
#####################################################################################


#####################################################################################
# Node
#####################################################################################


class NodeSubclassDeclarationWatcher(type):
    """
    This is a SubclassDeclarationWatcher for Nodes.
    This class is instantiated whenever a subclass that inherits from Node is declared.
    When it is instantiated, it parses the newly declared class and stores some metadata about it.
    """
    def __init__(cls, name, bases, clsdict):
        # every time this is subclassed for a non-abstract class:
        if not getattr(cls.Meta, 'is_an_abstract_class', False):
            # register the Node
            _register_that_a_node_was_defined(cls)
            # remember the fields of the Node, in the order in which they were defined
            # and also take the most recent value of required_additional_arguments_for_validation
            required_additional_arguments_for_validation = []
            quietly_drop_superfluous_fields = []
            documentation_name = None
            documentation_description = None
            documentation_shortform = None
            if len(cls.mro()) > 2:
                dict_of_fields = {}
                # go through the superclasses in descending order to ensure that fields from subclasses
                # overwrite fields of the same name from superclasses
                for superclass in reversed(cls.mro()):
                    if issubclass(superclass, Node):
                        if hasattr(superclass.Meta, 'required_additional_arguments_for_validation'):
                            required_additional_arguments_for_validation = superclass.Meta.required_additional_arguments_for_validation
                        if hasattr(superclass.Meta, 'quietly_drop_superfluous_fields'):
                            quietly_drop_superfluous_fields += superclass.Meta.quietly_drop_superfluous_fields
                        if hasattr(superclass.Meta, 'documentation_name'):
                            documentation_name = superclass.Meta.documentation_name
                        if hasattr(superclass.Meta, 'documentation_description'):
                            documentation_description = superclass.Meta.documentation_description
                        if hasattr(superclass.Meta, 'documentation_shortform'):
                            documentation_shortform = superclass.Meta.documentation_shortform
                        for k,v in superclass.__dict__.items():
                            if isinstance(v, Field):
                                if k.endswith('_'):
                                    # remove a trailing underscore from the name
                                    # (this is necessary if you use a keyword as the name)
                                    k = k[:-1]
                                if k in dict_of_fields and k not in getattr(cls.Meta, 'overwrites_existing_fields', []):
                                    raise ProgrammingError("field %s in Node %s is already defined. "
                                                             "This error message is just to prevent you from "
                                                             "doing this by accident: "
                                                             "Just set Meta.overwrites_existing_fields "
                                                             "to allow it." % (k, name,))
                                dict_of_fields[k] = v
                # order the fields by their order of creation
                list_of_fields = [(a, b) for a,b in dict_of_fields.items()]
                list_of_fields.sort(key=lambda a: a[1].order_of_creation)
                _value_to_node_fields[cls.Meta.name] = list_of_fields
            # set some inheritable fields of the Meta class
            # (because it might have been set only by a superclass)
            cls.Meta.required_additional_arguments_for_validation = required_additional_arguments_for_validation
            cls.Meta.quietly_drop_superfluous_fields = quietly_drop_superfluous_fields
            cls.Meta.documentation_name = documentation_name
            cls.Meta.documentation_description = documentation_description
            cls.Meta.documentation_shortform = documentation_shortform
            if documentation_name is None or documentation_description is None:
                raise ProgrammingError("these values must be set. Don't forget to add documentation!")
            _register_node_for_documentation(cls)
        super().__init__(name, bases, clsdict)


class Node(metaclass=NodeSubclassDeclarationWatcher):
    class Meta:
        is_an_abstract_class = True

    def validate(cls, obj, stack_objects, kwargs):
        """
        takes a value and either returns a new value that is validated, or raises an InvalidParamsException.
        The value must be a dict, unless the Node defines a shortform_field,
        in which case the value can be any other value that is transformed into a dict by the shortform_conversion() function.
        NOTE:
        due to the way the Node.validate() function is used, the following must be true:
        -no part of obj is ever overwritten in-place.
        -the kwargs or any of its contents are never overwritten in-place.
        -stack_objects contains a list 'immutable_fields', consisting of all those objects that can not be altered.
        All other fields are copied using json.loads(json.dumps(x)) when multiple alternatives need to be considered.
        """
        # before calling Node.validate() or any of its field.validate(), call Node.shortform()
        # if it exists and the value is not already a dictionary
        if hasattr(cls.Meta, 'shortform_field') and not isinstance(obj, dict):
            with node_trace_step(stack_objects, 'conversion from shortform', obj):
                tmp = cls.Meta.shortform_field.validate(obj)
                obj = cls.Meta.shortform_conversion(obj)
                if not isinstance(obj, dict):
                    raise ProgrammingError("the shortform conversion did not return a dict")
        # if it doesn't have a shortform, verify that the object is a dict
        elif not isinstance(obj, dict):
            raise InvalidParamsException("the value must be a dictionary")
        # if there is a key in the object that isn't a valid field name, raise an Exception
        ordered_list_of_fields = _value_to_node_fields[cls.Meta.name]
        ordered_field_names = [a for a,b in ordered_list_of_fields]
        for k in obj.keys():
            if k in cls.Meta.quietly_drop_superfluous_fields:
                # special case:
                # some fields are allowed to be there, but they are dropped from the result of the validation
                continue
            if k == 'type' and hasattr(cls.Meta, 'choice_type'):
                # special case: there may be a 'type' field.
                continue
            if k not in ordered_field_names:
                raise InvalidParamsException("'%s' is not a valid field name.\nValid field names are:\n%s" %
                                             (k, '\n'.join(ordered_field_names),))
        # go through each field in the order they were defined
        # (this includes fields of superclasses, which come first in the order)
        res_dict = {}
        for field_name, field in ordered_list_of_fields:
            # for each field, call its validation function and save the validated value
            # special case: field has dont_auto_validate: ignore it. It gets set later.
            # special case: field is not required, so use its default value
            if not field.dont_auto_validate:
                if field_name in obj:
                    field_value = obj[field_name]
                    with node_trace_step(stack_objects, field_name, field_value):
                        res_dict[field_name] = field.validate(field_value, stack_objects=stack_objects, kwargs=kwargs)
                else:
                    if field.required:
                        raise InvalidParamsException("missing value for the required field '%s'" % (field_name,))
                    elif not field.dont_print_default:
                        default_value = field.default
                        if default_value is not None and not isinstance(default_value, (str, int, float, bool)):
                            # if the default value is not a primitive type,
                            # it's a function that returns the actual default value
                            # (to prevent passing a complex object by reference and altering the original by accident)
                            default_value = default_value()
                        res_dict[field_name] = default_value
                # sanity checks
                if not field.dont_print_default:
                    if res_dict[field_name] is None:
                        if not field.null:
                            raise InvalidParamsException("the value must not be null")
        # put the validated result in an OrderedDict and return it
        res = collections.OrderedDict(sorted(res_dict.items(), key=lambda t: ordered_field_names.index(t[0])))
        return res

    def construct_object_visualization_html(cls, obj, stack_objects, kwargs):
        """
        takes an object that has already been validated.
        Constructs an HTML representation for this object in the stack_objects.
        The HTML representation is a python dictionary / a JSON object, which also has some additional HTML tags in it.
        """
        ordered_list_of_fields = _value_to_node_fields[cls.Meta.name]
        html_fragments = stack_objects['html_fragments']
        indent_string = stack_objects['indent_string']
        # add an HTML marker that is displayed next to the text and contains a link
        html_fragments.append(('html', """<span class="syntax-trees-object-dict">"""))
        annotation_attribute = 'value="%s"' % cls.Meta.name
        if hasattr(cls.Meta, 'choice_of'):
            annotation_attribute += ' choice="%s"' % cls.Meta.choice_of
        annotation_link = _doc_string_to_enriched_html("[[%s]]" % cls.Meta.name)
        html_fragments.append(('html', """<span class="syntax-trees-object-dict-annotation" %s>%s</span>""" %
                               (annotation_attribute, annotation_link,)))
        # add the dictionary content of the object
        html_fragments.append("{\n")
        stack_objects['current_indent_level'] += 1
        # print all the fields in the order they should have, skipping the ones that don't have a value set
        fields_to_use = [(field_name, field) for field_name, field in ordered_list_of_fields
                         if not field.dont_print_default or field_name in obj]
        # For each field, check if the value is the default and if so either skip it or mark it for later
        field_value = {}
        field_value_is_default = {}
        tmp = []
        for field_name, field in fields_to_use:
            if field_name in obj:
                field_value[field_name] = obj[field_name]
            else:
                # A quick fix for the sake of convenience:
                # If the value is not defined yet because the syntax has been modified and a field did not exist
                # when the object was first defined, just take the default value and hope for the best.
                field_value[field_name] = field.get_the_default_value()
            # Get the default value and compare it to the actual value
            default_value = field.get_the_default_value()
            field_value_is_default[field_name] = (field_value[field_name] == default_value)
            # If the value is the default and defaults should be skipped, do so
            if not (field_value_is_default[field_name] and stack_objects['skip_default_values']):
                tmp.append((field_name, field))
        fields_to_use = tmp
        # Add the type, if one exists, before the rest of the fields
        if hasattr(cls.Meta, 'choice_of'):
            fields_to_use = [('type', 'dummy_field_for_type')] + fields_to_use
        for i, (field_name, field) in enumerate(fields_to_use):
            html_fragments.append(indent_string * stack_objects['current_indent_level'])
            if field == 'dummy_field_for_type':
                html_fragments.append(html.escape('"type" : "%s"' % cls.Meta.choice_type))
            else:
                if field_value_is_default[field_name]:
                    html_fragments.append(('html', """<span class="syntax-trees-object-field-value-is-default-value">"""))
                field.construct_object_visualization_html(field_name, field_value[field_name], stack_objects)
                if field_value_is_default[field_name]:
                    html_fragments.append(('html', """</span>"""))
            if i != len(fields_to_use) - 1:
                html_fragments.append(",")
            html_fragments.append("\n")
        stack_objects['current_indent_level'] -= 1
        html_fragments.append(indent_string * stack_objects['current_indent_level'] + "}")
        html_fragments.append(('html', "</span>"))


#####################################################################################
# Field
#####################################################################################


_field_creation_order_counter = 0


class Field:
    """
    defines a Field.
    Each Node in a syntaxTree consists of several Fields.
    Each Field has its own validation logic.
    """
    def __init__(self, null=False, default=None, dont_auto_validate=False, derived_field=False,
                 dont_print_default=False, validation_accepts_nulls=False, help="TODO"):
        self.null = null
        self.default = default
        self.dont_auto_validate = dont_auto_validate
        self.derived_field = derived_field
        self.dont_print_default = dont_print_default
        self.validation_accepts_nulls = validation_accepts_nulls
        self.help = help
        # the Field is required if no default is provided and it must not be null
        self.required = default is None and not null
        # if the default value is not a primitive type, it's a function that returns the actual default value
        # (to prevent passing a complex object by reference and altering the original by accident)
        if default is not None and not isinstance(default, (str, int, float, bool)) and not callable(default):
            raise ProgrammingError("the default must be None, or a primitive, or a function")
        # if the Field is not required, verify that the defaut value is allowed
        if not self.required:
            val = self.get_the_default_value()
            stack_objects = {
                'node_trace': [],
                'current_object': None,
                'immutable_fields': [],
            }
            kwargs = {}
            self.validate(val, stack_objects, kwargs)
        # store the order_of_creation for each field, which is used to make sure that Fields are ordered in the way
        # in which they are defined, because classes do not keep track of the order of their fields
        global _field_creation_order_counter
        self.order_of_creation = _field_creation_order_counter
        _field_creation_order_counter += 1

    def get_the_default_value(self):
        """
        Returns an instance of the default value.
        """
        if callable(self.default):
            return self.default()
        else:
            return self.default

    def validate(self, val, stack_objects=None, kwargs=None, allow_null=None):
        """
        Subclasses should NOT overwrite this function.
        It acts as a wrapper around helper_for_validation(), which should be implemented by all subclasses.
        This function should be called on every value that could potentially be the value of the Field.
        It raises an InvalidParamsException if this is not valid.
        It checks the self.null field to determine whether or not to raise an exception on None,
        unless this is overwritten by setting allow_null.
        This returns a cleaned version of the value it is given.
        NOTE:
        This may not be intuitive, but the kwargs values passed here are ignored by many types of Fields.
        They are only used if the Field's own kwargs values say they should be used,
        via PASS_ARG_ALONG and OverwriteKeywordArgOfField.
        """
        if allow_null is None:
            allow_null = self.null
        if val is None:
            if not allow_null:
                raise InvalidParamsException("the value is not allowed to be null.")
            if self.validation_accepts_nulls:
                return self.helper_for_validation(val, stack_objects=stack_objects, kwargs=kwargs)
            return None
        else:
            return self.helper_for_validation(val, stack_objects=stack_objects, kwargs=kwargs)

    def helper_for_validation(self, val, stack_objects=None, kwargs=None):
        """
        overwrite this in each subclass.
        It should raise an InvalidParamsException if the value is invalid.
        This returns a cleaned version of the value it is given.
        """
        raise NotImplementedError("this method is not implemented")

    def get_documentation_purpose(self, node):
        """
        This returns a string describing the purpose of the Field.
        """
        return self.help

    def get_documentation_description(self, node):
        """
        overwrite this in each subclass.
        returns a string describing what the field may contain.
        """
        raise NotImplementedError("this method is not implemented")

    def get_full_documentation_html(self, node):
        """
        combines the text from get_documentation_purpose() and get_documentation_description()
        and wraps it in an HTML block.
        """
        purpose = _doc_string_to_enriched_html(self.get_documentation_purpose(node))
        description = _doc_string_to_enriched_html(self.get_documentation_description(node))
        res = """<div class="field-documentation"><div class="field-documentation-purpose">%s</div><div class="field-documentation-description">%s</div></div>""" % (purpose, description,)
        return res

    def construct_object_visualization_html(self, field_name, field_value, stack_objects):
        """
        constructs an HTML representation for this field in the stack_objects.
        This is called as a subroutine of Node.construct_object_visualization_html().
        """
        html_fragments = stack_objects['html_fragments']
        # Turn the name of the field into valid JSON.
        # Be careful to escape any special characters.
        field_name = html.escape(json.dumps(field_name, ensure_ascii=False))
        html_fragments.append(field_name)
        html_fragments.append(" : ")
        self.construct_object_visualization_html_for_value(field_value, stack_objects)

    def construct_object_visualization_html_for_value(self, field_value, stack_objects):
        """
        constructs an HTML representation for this field's value in the stack_objects.
        This is called as a helper function of Field.construct_object_visualization_html()
        and is overwritten by several subclasses of Field.
        """
        html_fragments = stack_objects['html_fragments']
        # turn the value of the field into valid JSON.
        # Be careful to escape any special characters if it is a string.
        if isinstance(field_value, str):
            field_value = html.escape(json.dumps(field_value, ensure_ascii=False))
        else:
            field_value = json.dumps(field_value)
        html_fragments.append(field_value)


#####################################################################################
# execute_function_on_node()
#####################################################################################


def execute_function_on_node(function, obj, stack_objects, kwargs, value=None, choice=None):
    """
    References a Node by either 'value' or 'choice' and executes a named function on it
    with the given object and keyword parameters.
    The targeted function needs to have this format:
    res_obj = function(cls, obj, stack_objects, kwargs)
    The parameter stack_objects should be a dict that is altered in-place by recursive calls.
    In contrast, the parameter kwargs should not be altered
    and is only for immediate use by the selected function, not recursive calls.
    """
    if (value is None) == (choice is None):
        raise ProgrammingError("the Node or group of nodes must be identified by either a 'value' or a 'choice' of values.")
    if not isinstance(stack_objects, dict) or not isinstance(kwargs, dict):
        raise ProgrammingError("the stack_objects and kwargs must both be dictionaries")
    # get the list of Nodes that might be a good fit
    if value is not None:
        candidate_nodes = [_value_to_node[value]]
    else:
        candidate_nodes = [_value_to_node[v] for k,v in _choice_to_type_to_values[choice].items()]
    # a helper feature to get documentation if an empty dict is submitted when several differen types are possible:
    if len(candidate_nodes) > 1 and isinstance(obj, dict) and len(obj) == 0:
        raise InvalidParamsException("""submitted an empty dictionary.\nValid types are: %s\nSelect one of the valid types for a description of its fields.""" %
                                     ', '.join(a.Meta.name for a in candidate_nodes))
    # if this is the validation function, verify for each candidate node that the kwargs have the right format
    # (all required_additional_arguments_for_validation are given, and no others)
    if function == 'validate':
        for candidate_node in candidate_nodes:
            required_additional_arguments_for_validation = candidate_node.Meta.required_additional_arguments_for_validation
            if len(required_additional_arguments_for_validation) != len(kwargs) \
                    or any(k not in kwargs for k in required_additional_arguments_for_validation):
                raise ProgrammingError("the kwargs don't match for node %s.\nWas: %s\nShould be: %s" %
                                        (candidate_node.Meta.name, ', '.join(kwargs.keys()),
                                         ', '.join(required_additional_arguments_for_validation),))
    selected_node = None
    # if there is only one possible node, pick it
    if len(candidate_nodes) == 1:
        selected_node = candidate_nodes[0]
    elif isinstance(obj, dict) and 'type' in obj:
        # pick the correct 'value' based on the 'type' attribute
        valid_types_to_value = _choice_to_type_to_values[choice]
        provided_type = obj['type']
        if provided_type not in valid_types_to_value:
            raise InvalidParamsException("the type '%s' is not valid.\nValid types are: %s" %
                                         (provided_type, ', '.join(valid_types_to_value.keys()),))
        selected_node = _value_to_node[valid_types_to_value[provided_type]]
    if selected_node is not None:
        # run the selected function on the selected_node
        res_obj = getattr(selected_node, function)(selected_node, obj, stack_objects, kwargs)
        if function == 'validate':
            # if the Node is one of several choices, add the 'type' to the result
            if hasattr(selected_node.Meta, 'choice_type'):
                if isinstance(obj, dict) and 'type' in obj and obj['type'] != selected_node.Meta.choice_type:
                    raise ProgrammingError("the type was already given, but after validating "
                                             "it is not the value of the selected Node. "
                                             "This should not be possible.")
                # some Nodes can actually replace themselves with a different Node when validating.
                # (example: copy_message_component)
                # in those cases, leave the type as it is
                if 'type' in res_obj:
                    # verify that the type is one of the types that were originally requested
                    if res_obj['type'] not in [a.Meta.choice_type for a in candidate_nodes]:
                        raise ProgrammingError("after validating the type was already set, "
                                                "but is not one of the ones that was requested.")
                else:
                    res_obj['type'] = selected_node.Meta.choice_type
                res_obj.move_to_end('type', last=False) # make sure the 'type' is listed first
        return res_obj
    else:
        # there is ambiguity.
        # If the function to call is not the validation function, this is an error
        # (the validation function should have been called before,
        # and should have cleared up the ambiguity by creating a 'type' field)
        if function != 'validate':
            raise ProgrammingError("it is ambiguous which Node to use and the requested function was not"
                                     " 'validate', which is the function used to clear up ambiguity. "
                                     "Validate() should have been called beforehand to clean this up.")
        # go through all candidates and attempt to validate them
        successful_parsing_values = []
        for candidate_node in candidate_nodes:
            # note: while it is computationally expensive to use a try/except block for parsing something,
            # this code should not get executed all that often.
            # it will only be executed the first time something needs to be validated,
            # as the 'type' fields will be set afterwards,
            # so the next time it is validated, the type is already known and no experimenting is necessary.
            try:
                # This can be reassigned below,
                # so rename it first so other loops aren't stuck with the new value by accident
                tmp_obj = obj
                # make a copy of stack_objects before recursing, as the validate() method may alter the values in there
                immutable_fields = stack_objects['immutable_fields']
                copy_of_stack_objects = {}
                for k,v in stack_objects.items():
                    copy_of_stack_objects[k] = v if k in immutable_fields else json.loads(json.dumps(v))
                # A small security measure to prevent errors other than InvalidParamsException:
                # Nodes are usually written with the assumption that objects they test are a dict,
                # and validate() actually tests for that.
                # However, validate() can be overwritten by a Node,
                # so we should make sure that the value is always a dict (or a valid shortform value).
                if hasattr(candidate_node.Meta, 'shortform_field') and not isinstance(tmp_obj, dict):
                    tmp = candidate_node.Meta.shortform_field.validate(tmp_obj)
                    tmp_obj = candidate_node.Meta.shortform_conversion(tmp_obj)
                    if not isinstance(tmp_obj, dict):
                        raise ProgrammingError("the shortform conversion did not return a dict")
                elif not isinstance(tmp_obj, dict):
                    # This error will immediately be caught by the surrounding try/except clause.
                    raise InvalidParamsException("the value must be a dictionary")
                # try to validate the object, and if no error occurred then append the result to the list of successes
                res_obj = candidate_node.validate(candidate_node, tmp_obj, copy_of_stack_objects, kwargs)
                successful_parsing_values.append((candidate_node, res_obj, copy_of_stack_objects))
            except InvalidParamsException:
                pass
        # if exactly one of the candidates is a match:
        # set the 'type' field,
        # overwrite stack_objects to match that candidate's stack_objects,
        # and return its result
        if len(successful_parsing_values) == 1:
            candidate_node, res_obj, copy_of_stack_objects = successful_parsing_values[0]
            res_obj['type'] = candidate_node.Meta.choice_type
            res_obj.move_to_end('type', last=False) # make sure the 'type' is listed first
            stack_objects.clear()
            for k,v in copy_of_stack_objects.items():
                stack_objects[k] = v
            return res_obj
        # if none or more than one candidate are a match, raise an Exception
        if len(successful_parsing_values) == 0:
            raise InvalidParamsException("no valid way to parse this value could be found."
                                         "Please manually specify a 'type' field for a more detailed error message.\n"
                                         "Possible types are: %s" %
                                         (', '.join(candidate_node.Meta.choice_type for
                                                    candidate_node in candidate_nodes)))
        raise InvalidParamsException("the value is ambiguous and matched several possible types. "
                                     "Please specify the 'type' field manually with one of the valid values: %s" %
                                     (', '.join(["'%s'" % a[0].Meta.choice_type for a in successful_parsing_values])))


#####################################################################################
# documentation
#####################################################################################


_documentation_html_builder = {}
_final_documentation_html = None
_current_documentation_page = None
_documentation_target_to_page = {}

def set_current_documentation_page(name):
    """
    this needs to be called in between definitions of nodes in order to set on which page their documentation will go.
    Names must correspond to the url of the page the documentation should be on.
    """
    global _documentation_html_builder
    global _current_documentation_page
    # initialize a list, which will be turned into a single string in finalize()
    _documentation_html_builder[name] = []
    _current_documentation_page = name


def get_final_documentation_html(page):
    """
    returns the documentation pages.
    This is cached, so that it is only calculated once,
    but it is only evaluated the first time the documentation is actually requested,
    because calculating this when loading the server results in circular import errors
    because the URLs are needed for the documentation,
    but they are only set after the syntaxTrees files have been loaded.
    """
    global _documentation_html_builder
    global _final_documentation_html
    choices_documented_so_far = {}
    if _final_documentation_html is None:
        # generate documentation for each Node
        # and the first time a new choice is encountered in a Node, generate its documentation
        for node in _all_nodes:
            if hasattr(node.Meta, 'choice_of') and node.Meta.choice_of not in choices_documented_so_far:
                choices_documented_so_far[node.Meta.choice_of] = True
                _generate_documentation_for_choice(node.Meta.choice_of)
            _generate_documentation_for_node(node)
        # turn the entries in _documentation_html_builder from list of code pieces
        # into a single large html string element
        _final_documentation_html = {}
        for k,v in _documentation_html_builder.items():
            _final_documentation_html[k] = ''.join(v)
    # return the result
    return _final_documentation_html[page]


_documentation_target_to_hierarchy_level = {}


def _register_node_for_documentation(node):
    """
    registers information about a node for the purpose of generating documentation later.
    This needs to be called for each node before _generate_documentation_for_node() can be called,
    because otherwise references to Nodes that are defined later will not have been set yet.
    """
    # remember on which page this entry can be found
    global _documentation_target_to_page
    if node.Meta.name in _documentation_target_to_page:
        raise ProgrammingError("this error is for debugging only. A duplicate value here should be impossible.")
    if hasattr(node.Meta, 'choice_of') and node.Meta.choice_of != _stack_of_choices_for_documentation_hierarchy[-1]:
        raise ProgrammingError("this is not the currently active block of choices!. Was %s, should be %s" %
                                         (node.Meta.choice_of, _stack_of_choices_for_documentation_hierarchy[-1]))
    _documentation_target_to_page[node.Meta.name] = _current_documentation_page
    _documentation_target_to_hierarchy_level[node.Meta.name] = 10 * (1 + len(_stack_of_choices_for_documentation_hierarchy))


def _generate_documentation_for_node(node):
    """
    takes a Node and generates documentation for it, adding it to the _documentation_html_builder.
    This is called once for each non-abstract Node, in the order in which they are defined.
    """
    anchor_name = node.Meta.name
    anchor = """<a id="%s" class="internal-link-anchor"></a>""" % (anchor_name,)
    if hasattr(node.Meta, 'choice_of'):
        node_header_choice_addendum = " (A type of [[%s]])" % node.Meta.choice_of
    else:
        node_header_choice_addendum = ""
    name_in_navbar = node.Meta.documentation_name
    node_header = _doc_string_to_enriched_html("[[%s]]%s" % (node.Meta.name, node_header_choice_addendum,))
    level_of_hierarchy = _documentation_target_to_hierarchy_level[node.Meta.name]
    node_header = """<h3 class="node-name" level-of-hierarchy="%d" name-in-navbar="%s">%s%s</h3>""" % \
                  (level_of_hierarchy, name_in_navbar, anchor, node_header,)
    node_doc = node.Meta.documentation_description
    if node.Meta.documentation_shortform is not None:
        node_doc += "\nThis Node has a shortform (instead of specifying a JSON object / a dictionary, you can specify only a constant):\n%s" % \
                    node.Meta.documentation_shortform
    node_doc = _doc_string_to_enriched_html(node_doc)
    node_description = """<div class="node-description">%s</div>""" % (node_doc,)
    field_descriptions = []
    field_table_header = """<tr><th class="field-cell-name">Fields</th><th/ class="field-cell-dummy"><th class="field-cell-null"></th><th class="field-cell-default"></th></tr>"""
    field_descriptions.append(field_table_header)
    for field_name, field in _value_to_node_fields[node.Meta.name]:
        # add the name and general information of the field
        default_value = json.dumps(field.default()) if callable(field.default) else json.dumps(field.default)
        if field.derived_field:
            default_or_required = "derived field, do not set!"
        elif field.required:
            default_or_required = 'this field is required'
        else:
            default_or_required = "default value: %s" % default_value
        null = "can be null" if field.null else ""
        extra_classes = "field-is-derived" if field.derived_field else ""
        field_html_1 = """<tr class="field %s"><td class="field-cell-name">%s</td><td/ class="field-cell-dummy"><td class="field-cell-null">%s</td><td class="field-cell-default">%s</td></tr>""" % \
                       (extra_classes, field_name, null, default_or_required,)
        field_descriptions.append(field_html_1)
        # add the field documentation
        full_documentation_html = field.get_full_documentation_html(node)
        field_html_2 = """<tr class="field %s"><td/ class="field-documentation-table-cell-dummy"><td colspan=3 class="field-documentation-table-cell-main"><table style="width:100%%">%s</table></td></tr>""" % \
                       (extra_classes, full_documentation_html,)
        field_descriptions.append(field_html_2)
    field_descriptions = """<table class="fields">%s</table>""" % (''.join(field_descriptions),)
    res = """<div class="node">%s%s%s</div>""" % (node_header, node_description, field_descriptions)
    # add the entry to the list of documentations for this page
    _documentation_html_builder[_documentation_target_to_page[node.Meta.name]].append(res)


_choice_to_description = {}
_stack_of_choices_for_documentation_hierarchy = []


def register_choice_for_documentation(choice, readable_name, description):
    """
    analogous to _register_node_for_documentation(), but for choice-summaries instead of Nodes.
    Marks the Beginning of a block of choices.
    """
    # remember on which page this entry can be found
    global _documentation_target_to_page
    if choice in _documentation_target_to_page:
        raise ProgrammingError("this error is for debugging only. A duplicate value here should be impossible.")
    _documentation_target_to_page[choice] = _current_documentation_page
    # remember the entry
    global _choice_to_description
    _choice_to_description[choice] = (readable_name, description)
    _documentation_target_to_hierarchy_level[choice] = 10 * (1 + len(_stack_of_choices_for_documentation_hierarchy))
    _stack_of_choices_for_documentation_hierarchy.append(choice)


def register_end_of_choices(choice):
    """
    marks the end of a block of choices.
    """
    if _stack_of_choices_for_documentation_hierarchy[-1] != choice:
        raise ProgrammingError("wrong choice. Selected %s, but most recent choice is %s." %
                                 (choice, _stack_of_choices_for_documentation_hierarchy[-1]))
    _stack_of_choices_for_documentation_hierarchy.pop()


def _generate_documentation_for_choice(choice):
    """
    analogous to _generate_documentation_for_node(), but for choice-summaries instead of Nodes.
    """
    # get the description that was saved earlier and enrich it
    readable_name = _doc_string_to_enriched_html("[[%s]] (a choice of several types)" % choice)
    description = _doc_string_to_enriched_html(_choice_to_description[choice][1])
    # create a header and description for the choice, and list all possible options of the choice
    anchor_name = choice
    anchor = """<a id="%s" class="internal-link-anchor"></a>""" % anchor_name
    level_of_hierarchy = _documentation_target_to_hierarchy_level[choice]
    name_in_navbar = _choice_to_description[choice][0]
    choice_header = """<h3 class="choice-name" level-of-hierarchy="%d" name-in-navbar="%s">%s%s</h3>""" % \
                    (level_of_hierarchy, name_in_navbar, anchor, readable_name,)
    choice_description = """<div class="choice-description">%s</div>""" % (description,)
    choice_options = []
    table_header = """<tr><th class="choice-option-cell-type">type</th><th class="choice-option-cell-name">name</th><th class="choice-option-cell-description">description</th></tr>"""
    for node in _all_nodes:
        if hasattr(node.Meta, 'choice_of') and node.Meta.choice_of == choice:
            choice_option_type = """[[%s|%s]]""" % (node.Meta.name, node.Meta.choice_type)
            choice_option_type = _doc_string_to_enriched_html(choice_option_type)
            choice_option_name = """[[%s|%s]]""" % (node.Meta.name, node.Meta.documentation_name)
            choice_option_name = _doc_string_to_enriched_html(choice_option_name)
            choice_option_description = node.Meta.documentation_description
            choice_option_description = _doc_string_to_enriched_html(choice_option_description)
            option_html = """<tr class="choice-option"><td>%s</td><td>%s</td><td>%s</td></tr>""" % \
                          (choice_option_type, choice_option_name, choice_option_description,)
            choice_options.append(option_html)
    choice_options = """<table class="choice-options">%s%s</table>""" % (table_header, ''.join(choice_options),)
    res = """<div class="choice">%s%s%s</div>""" % (choice_header, choice_description, choice_options)
    # add the entry to the list of documentations for this page
    _documentation_html_builder[_documentation_target_to_page[choice]].append(res)


def _doc_string_to_enriched_html(s):
    """
    takes a documentation string and turns it into an enriched HTML string that can contain links.
    """
    # turn strings of this form into links: [[name|optional_text_of_link]]
    link_shortforms = re.findall(r"(\[\[([a-zA-Z_\-]+)(\|([a-zA-Z_\-() ]+))?\]\])", s)
    for link_shortform in link_shortforms:
        target = link_shortform[1]
        text = link_shortform[3]
        # find out on which page the referenced value/choice is defined and set the link accordingly
        page = _documentation_target_to_page[target]
        global _page_to_url
        if _page_to_url is None:
            raise ProgrammingError("_page_to_url is not defined. "
                                   "You need to call syntaxTrees.basics.set_function_to_convert_page_name_to_url() "
                                   "to assign a URL to each page.")
        url = _page_to_url(page)
        href = "%s#%s" % (url, target)
        if text == '':
            # if the text is not given explicitly, use the documentation name corresponding to the Node or to the Choice
            if target in _choice_to_description:
                text = _choice_to_description[target][0]
            else:
                text = _value_to_node[target].Meta.documentation_name
        # build a link out of this and replace the link_shortform with the finished link in the text
        final_link = """<a href="%s">%s</a>""" % (href, text)
        s = s.replace(link_shortform[0], final_link)
    # replace linebreaks with paragraphs
    s = ''.join("<p>%s</p>" % a.lstrip().rstrip() for a in s.split("\n") if a.lstrip().rstrip() != "")
    return s


_page_to_url = None


def set_function_to_convert_page_name_to_url(func):
    """
    Set a function that can be used to convert from a website's name to its URL.
    This can be a simple dictionary lookup.
    If you are using Django, just use reverse_lazy as the input of this function.
    """
    global _page_to_url
    _page_to_url = func


#####################################################################################
# references and consistency checks
#####################################################################################


# all of these are set while the Nodes in syntaxTrees are defined.
# They are used to map values, choices, and classes to each other.
_all_nodes = []
_value_to_node = {}
_value_to_choice = {}
# for each Node, stores a list of tuples of (field_name, Field)
_value_to_node_fields = {}
# a dict mapping 'choice_of' to a dict mapping 'choice_type' to 'name'
_choice_to_type_to_values = collections.defaultdict(dict)
# these exist for debugging purposes
_debug_referenced_values = {}
_debug_referenced_choices = {}
_finalize_has_been_called = False


def register_that_a_value_was_referenced(value):
    """
    remembers that an entity in syntaxTrees or its derivatives made a reference to a Node by its 'value'.
    This is used by finalize() for confirming that all usages add up properly.
    """
    _debug_referenced_values[value] = True


def register_that_a_choice_was_referenced(choice):
    """
    remembers that an entity in syntaxTrees or its derivatives made a reference to a group of Nodes by their 'choice'.
    This is used by finalize() for confirming that all references add up properly.
    """
    _debug_referenced_choices[choice] = True


def _register_that_a_node_was_defined(cls):
    """
    registers that a Node was defined.
    This sets various mappings so that nodes can later be referenced by their 'name' or 'choice'.
    This is also used by finalize() for confirming that all usages add up properly.
    """
    if _finalize_has_been_called:
        raise ProgrammingError("can't define any more Nodes! finalize() has already been called!")
    value = cls.Meta.name
    choice_of = getattr(cls.Meta, 'choice_of', None)
    choice_type = getattr(cls.Meta, 'choice_type', None)
    _all_nodes.append(cls)
    if value in _value_to_node:
        raise ProgrammingError("can't define two nodes with the same name/value: %s" % value)
    _value_to_node[value] = cls
    if choice_of is not None:
        if choice_type is None:
            raise ProgrammingError("if a 'choice_of' is given, a 'choice_type' must also be given.")
        _value_to_choice[value] = (choice_of, choice_type)
        type_to_value = _choice_to_type_to_values[choice_of]
        if choice_type in type_to_value:
            raise ProgrammingError("can't define the type '%s' of choice '%s' twice" %
                                             (choice_type, choice_of,))
        type_to_value[choice_type] = value


def finalize():
    """
    finalizes the registration of Nodes
    Once this is called, no new Nodes can be registered.
    Also verifies that the connections between all registered Nodes make sense and nothing is missing.
    """
    # debugging
    global _finalize_has_been_called
    _finalize_has_been_called = True
    for used_value in _debug_referenced_values:
        if used_value not in _value_to_node:
            raise ProgrammingError("the value '%s' was referenced but never defined" % used_value)
    for used_choice in _debug_referenced_choices:
        if used_choice not in _choice_to_type_to_values:
            raise ProgrammingError("the choice '%s' was referenced but never defined" % used_choice)
    for choice in _choice_to_type_to_values.keys():
        for value in _value_to_node.keys():
            if choice == value:
                raise ProgrammingError("there are both a choice and a value called '%s'." % choice)
        if choice not in _choice_to_description:
            raise ProgrammingError("missing documentation for choice: %s" % choice)


#####################################################################################
# helper functions
#####################################################################################


def simplify_stack_objects_current_object_for_display(stack_objects):
    """
    simplifies the current_object used by the stack_objects,
    to make it smaller and more suitable for being displayed in error messages.
    The simplified object should have a limited size no matter what.
    All strings gets shortened, all oversized dicts or lists get shortened.
    """
    current_object = stack_objects['current_object']
    max_dict_field_count = 10
    max_list_length = 3
    max_string_length = 100
    depth = 2

    def _rec_shortener(obj, remaining_depth):
        if isinstance(obj, dict):
            res = {}
            if len(obj) > max_dict_field_count:
                return "[a dictionary with %d fields, which is too many to display here]" % len(obj)
            for k,v in obj.items():
                if remaining_depth <= 0:
                    res[k] = '...'
                else:
                    res[k] = _rec_shortener(v, remaining_depth - 1)
            return res
        elif isinstance(obj, list):
            res = []
            for i,v in enumerate(obj):
                if i >= max_list_length:
                    break
                res.append(_rec_shortener(v, remaining_depth - 1))
            if len(obj) > max_list_length:
                res.append("[%d additional elements]" % (len(obj)-max_list_length))
            return res
        elif isinstance(obj, str):
            if len(obj) > max_string_length:
                return obj[:max_string_length-3] + "..."
            else:
                return obj
        return obj
    current_object = _rec_shortener(current_object, depth)
    current_object = json.dumps(current_object, indent=4)
    stack_objects['current_object'] = current_object


class node_trace_step:
    """
    Context manager for finding out where an error occurred.
    Can be used for adding a string to the node_trace and making sure it gets removed again,
    and also for setting the current_object to display along with the error message.
    """
    def __init__(self, stack_objects, new_value, object):
        # remember the stack_objects, not the stack_objects['node_trace'], since those can be overwritten!
        self.stack_objects = stack_objects
        self.new_value = new_value
        self.object = object

    def __enter__(self):
        self.stack_objects['node_trace'].append(self.new_value)
        self.previous_object = self.stack_objects['current_object']
        self.stack_objects['current_object'] = self.object

    def __exit__(self, etype, value, traceback):
        """
        if no error occurred, undo the changes.
        """
        if etype is None:
            self.stack_objects['node_trace'].pop()
            self.stack_objects['current_object'] = self.previous_object


def get_list_of_fields_for_node(node_name):
    """
    a helper function that returns the fields of a Node as a list of tuples of (field_name, field).
    """
    return _value_to_node_fields[node_name]


def detailed_error_handler_with_node_trace(e, stack_objects):
    """
    a helper function for more detailed error messages.
    Catches the exception, enriches it with more information about where the error occurred,
    logs it if it wasn't an InvalidParamsException,
    then raises it again as an InvalidParamsException.
    """
    node_trace = stack_objects['node_trace']
    simplify_stack_objects_current_object_for_display(stack_objects)
    current_object = stack_objects['current_object']
    trace_message = " - ".join(["%s" % a for a in node_trace])
    if isinstance(e, InvalidParamsException):
        error_message = str(e)
    else:
        error_message = get_error_message_details()
    error_message = "exception at the following position:\n%s\n-----\nfor object:\n%s\n-----\n%s" % \
                    (trace_message, current_object, error_message,)
    # Raise the error again, either as an InvalidParamsException or a ServersideProgrammingError
    # the functions in collabtoolsApi.py will react differently to these
    # (the former is just passed to the user as is. The latter is again enriched with the stacktrace and also logged.)
    if isinstance(e, InvalidParamsException):
        raise InvalidParamsException(error_message)
    else:
        raise ProgrammingError(error_message)


#####################################################################################
# miscellaneous
#####################################################################################


# A constant with a special meaning. Needs to be identical to itself, and nothing else.
PASS_ARG_ALONG = object()
# this also has a special meaning, and contains a value


class OverwriteKeywordArgOfField:
    def __init__(self, value):
        self.value = value
