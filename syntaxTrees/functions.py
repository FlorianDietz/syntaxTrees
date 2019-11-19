import collections
import json

from . import basics
from .utilities import InvalidParamsException, ProgrammingError

#####################################################################################
# import the files defining the Nodes and finalize them
#####################################################################################


from . import nodesExample

basics.finalize()


#####################################################################################
# rules and options
#####################################################################################


def validate_example_object(obj):
    """
    Takes a dictionary describing an object described in nodesExample.py and validates it.
    Returns the validated object.
    If it fails, raises a descriptive InvalidParamsException.
    """
    try:
        if not isinstance(obj, dict):
            raise InvalidParamsException("the value needs to be a dictionary")
        # A simple stack_objects group.
        # These are the minimal values needed by the validation logic.
        # You can also put additional variables in here, so that you can access them in your own functions.
        stack_objects = {
            # Keeps track of what has happened so far, for more useful error messages
            'node_trace': [],
            # Keeps track of the object currently under scrutiny, for more useful error messages
            'current_object': None,
            # If you put more fields in this dictionary and you don't want them to be messed with automatically,
            # put their names in this list.
            'immutable_fields': [],
        }
        kwargs = {
            # We defined this as a required_additional_arguments_for_validation in nodesExample.py,
            # so we have to give a start value for this kwarg here.
            'allow_user_input_node': True
        }
        # Validate the object
        validated_object = basics.execute_function_on_node(choice='numerical_node', function='validate',
                                                           obj=obj, stack_objects=stack_objects, kwargs=kwargs)
        # Error checking
        if len(stack_objects['node_trace']) != 0:
            raise ProgrammingError("the node_trace is imbalanced. A Node adds to it without removing it.")

        def _recursive_dict_check(a, l):
            if isinstance(a, dict):
                if not isinstance(a, collections.OrderedDict):
                    raise ProgrammingError("the validation function should always return OrderedDicts, "
                                           "not normal dicts, so that they can be displayed properly:\n%s\n%s" %
                                           (', '.join(l), a,))
                for k,v in a.items():
                    l.append(k)
                    _recursive_dict_check(v, l)
                    l.pop()
            elif isinstance(a, list):
                for i, b in enumerate(a):
                    l.append(str(i))
                    _recursive_dict_check(b, l)
                    l.pop()
        _recursive_dict_check(validated_object, [])
        return validated_object
    except Exception as e:
        basics.detailed_error_handler_with_node_trace(e, stack_objects)


def evaluate_numerical_node(obj):
    """
    Takes a dictionary describing 'numerical_node' and applies the 'evaluate' function to it,
    which is implemented differently for each subclass of numerical_node.
    """
    stack_objects = {
        'node_trace': ['evaluating numerical_node'],
        'current_object': None,
        'immutable_fields': [],
    }
    # Call the 'evaluate' function
    res = basics.execute_function_on_node(choice='numerical_node', function='evaluate',
                                          obj=obj, stack_objects=stack_objects, kwargs={})
    return res


#####################################################################################
# documentation
#####################################################################################


basics.set_function_to_convert_page_name_to_url(lambda page_name: "my/example/url")


def get_documentation_of_numerical_nodes():
    """
    Returns a piece of HTML code that describes the documentation of the numerical_nodes.
    """
    return basics.get_final_documentation_html('numerical_nodes')


#####################################################################################
# visualization
#####################################################################################


def visualize_numerical_node_in_html(obj_dict):
    """
    Returns HTML code that nicely visualizes an object.
    It is text that can be selected and forms a valid JSON description of the object,
    but it also has highlighting to make it more understandable.
    """
    # Generate a nice visualization for the object
    stack_objects = {
        'node_trace': ['visualizing numerical_node'],
        'current_object': None,
        'html_fragments': [],
        'indent_string': " " * 4,
        'current_indent_level': 0,
        'skip_default_values': False,
        'immutable_fields': [],
    }
    kwargs = {}
    basics.execute_function_on_node(choice='numerical_node', function='construct_object_visualization_html',
                                    obj=obj_dict, stack_objects=stack_objects, kwargs=kwargs)
    # Put the fragments together to form a complete string
    # Do this in several different ways:
    # The first includes the html elements.
    # The second filters out the html tags and is only text.
    # (note that in both cases html.escape() has already been called, so it's safe)
    all_html_fragments = ''.join(a if isinstance(a, str) else a[1] for a in stack_objects['html_fragments'])
    pure_text = ''.join(a for a in stack_objects['html_fragments'] if isinstance(a, str))
    # Do the whole thing again, but this time skip default values
    stack_objects['html_fragments'] = []
    stack_objects['skip_default_values'] = True
    basics.execute_function_on_node(choice='numerical_node', function='construct_object_visualization_html', obj=obj_dict,
                                    stack_objects=stack_objects, kwargs=kwargs)
    all_html_fragments_nondefault = ''.join(a if isinstance(a, str) else a[1] for a in stack_objects['html_fragments'])
    pure_text_nondefault = ''.join(a for a in stack_objects['html_fragments'] if isinstance(a, str))
    # create a button to copy the pure text to your clipboard
    # and a div to display the annotated text with links.
    html_elements = []
    for text, visualization in [(pure_text, all_html_fragments), (pure_text_nondefault, all_html_fragments_nondefault)]:
        button_to_copy_text = """<button class="clipboard-button" data-clipboard-text="%s">Copy to clipboard</button>""" % text
        syntax_trees_object_visualization = """<div class="syntax-trees-object-visualization">%s</div>""" % visualization
        html_elements.append((button_to_copy_text, syntax_trees_object_visualization))
    res = """<div class="syntax-trees-object">
                <p>The below is the JSON description of this object.</p>
                <p>It is annotated with links to the documentation of each component.</p>
                <p>You can hide fields with default values to make things clearer, and copy it to a clipboard to make creating similar Rules and Options easier.<p>
                <ul class="nav nav-tabs">
                    <li class="active"><a data-toggle="tab" href="#default-values-hidden">Hide default values</a></li>
                    <li><a data-toggle="tab" href="#default-values-shown">Show default values</a></li>
                </ul>
                <div class="tab-content">
                    <div id="default-values-hidden" class="tab-pane fade in active">
                        %s
                        %s
                    </div>
                    <div id="default-values-shown" class="tab-pane fade">
                        %s
                        %s
                    </div>
                </div>
            </div>""" % (html_elements[1][0], html_elements[1][1], html_elements[0][0], html_elements[0][1],)
    return res
