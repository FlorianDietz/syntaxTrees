import numbers

from . import basics
from . import fields


#####################################################################################
# We define the following nodes for illustration purposes:
# * constant: represents a hardcoded number
# * user_input: represents a number that is obtained by asking the user for input.
# Optionally has an extra field to define what to do on an invalid input.
# * sum: take the sum of any number of other nodes
# * constant_multiple: multiply two numbers. The first of these must be known at compile-time.
# Because of constant_multiple, we have an additional parameter that disallows a user_input node anywhere
# in the tree that must be known at compile-time. We can implement this by just adding an extra parameter
# that is passed down the tree: allow_user_input_node.
# We can also compress a tree of this type at compile-time.
#####################################################################################



# Register all following Nodes for the appropriate HTML documentation page
# (If you define multiple independent syntaxTrees,
# use this to switch on what page the documentation will be generated.)
basics.set_current_documentation_page('numerical_nodes')


#####################################################################################
# This class is used to make it possible to allow an optional '_comment' field
# on every class that is derived from this one.
# It also declares that every derived class should expect a allow_user_input_node kwargs parameter.
# (This declaration is not strictly necessary, but helps a lot with debugging,
# because you will get an error message
# if you forget to define a value for this parameter anywhere where it is needed.
# You can use basics.PASS_ARG_ALONG to copy the value of the own kwargs
# that the current node received from its own parent.)
#####################################################################################


class AbstractNodeForNumbers(basics.Node):
    """
    This class is used to add a _comment field to every subclass
    """
    _comment = fields.String(default=None, null=True, dont_print_default=True, max_length=10*1000,
                             help="An optional textual comment. This does not do anything, "
                                  "but will appear in the automatically generated HTML documentation.")

    class Meta:
        is_an_abstract_class = True
        required_additional_arguments_for_validation = ['allow_user_input_node']


basics.register_choice_for_documentation('numerical_node', "Numerical Node", """
Here we register a list of Classes that belong together because they often represent alternatives of each other.
Wherever one of them is a valid entry, the others are also valid.
This is indicated in fields with the keyword 'choice', as opposed to 'value', which indicates that only a single Class is a valid match.
All of the alternatives for this group will be grouped together in the generated HTML documentation.
""")


#####################################################################################
# Begin of the actual Nodes we need
#####################################################################################


class ConstantNode(AbstractNodeForNumbers):
    val = fields.Float(null=False, default=None, min=-1000, max=1000, help="The value represented by this constant.")

    class Meta:
        name = 'constant'
        choice_of = 'numerical_node'
        choice_type = 'constant'
        documentation_name = "Constant"
        shortform_field = fields.Float(null=False)
        documentation_description = """A [[constant]] represents a single hardcoded number."""
        documentation_shortform = "If only a number is given, it is automatically expanded " \
                                  "and used as the value of this Constant."

        def shortform_conversion(shortform_value):
            """
            The ConstantNode can be defined as just a number, and will expand to JSON form automatically.
            This makes it possible to define a JSON concisely, while still keeping all the functions of the ConstantNode class.
            """
            return {
                'val': shortform_value,
            }
    def validate(cls, obj, stack_objects, kwargs):
        """
        This class doesn't need to do anything in its validation method,
        so I'm using this space to explain how the validation method works:
        * cls is the current class (ConstantNode)
        * obj is the JSON object the user entered.
        * stack_objects is a dictionary that contains objects you want to keep track of during the function call.
        For example, if you want to create backreferences in the parsed object,
        you can keep track of these backreferences here.
        Note that this object must be JSON-serializable because it is frequently copied by super.validate()
        using json.loads(json.dumps(stack_objects)).
        This is done in order to automatically determine if the object that is being validated fits more
        than one of the possible schemas, which can require experimentation and needs to be reversible.
        * kwargs is similar to stack_objects, but it is only handed down the recursive calls,
        while stack_objects is persistent and keeps a changed state even after going back up.
        If a class has two fields A and B, then after validating field A, field B will receive the same kwargs
        as field A, but the stack_objects it receives may have been altered by field A.

        super.validate() will validate the 'obj' against all fields of this class.
        The rest of this function can be used for custom code. Set dont_auto_validate=True on a field
        if you don't want to test that field automatically.
        Call cls.<field_name>.validate(<field_value>, stack_objects=stack_objects, kwargs=kwargs)
        to validate the field manually.

        The validate() function should return the fully validated object.
        """
        obj = super().validate(cls, obj, stack_objects, kwargs)
        return obj

    def evaluate(cls, obj, stack_objects, kwargs):
        """
        When evaluating the syntax tree, just return the value.
        """
        return obj['val']


class UserInputNode(AbstractNodeForNumbers):
    message = fields.String(help="This message is shown to the user when he is asked to enter input.")
    on_error = fields.PrimitiveValueOrGetter(
                    primitive_field=fields.Integer(help="This is the value that is used if the user fails to input an integer."),
                    complex_field=fields.Value('user_input', kwargs={'allow_user_input_node': basics.PASS_ARG_ALONG},
                                               help="This recursive [[user_input]] is shown "
                                                    "if the users fails to input an integer."),
                    default=0,
                    help="This specified what happens if the user fails to enter a valid number as input."
                    )

    class Meta:
        name = 'user_input'
        choice_of = 'numerical_node'
        choice_type = 'user_input'
        documentation_name = "User Input"
        documentation_description = """Represents a number that is obtained by asking the user for input.
        Optionally has an extra field to define what to do on an invalid input."""

    def validate(cls, obj, stack_objects, kwargs):
        """
        Raise an exception if allow_user_input_node is False.
        """
        obj = super().validate(cls, obj, stack_objects, kwargs)
        if not kwargs['allow_user_input_node']:
            raise Exception("You can't ask for input in this branch!")
        return obj

    def evaluate(cls, obj, stack_objects, kwargs):
        """
        Show the user a message, then wait for input.
        If the input is a number, return it.
        Else perform whatever action on_error requires.
        """
        print(obj['message'])
        try:
            return float(input())
        except:
            on_error = obj['on_error']
            if isinstance(on_error, numbers.Number):
                return on_error
            else:
                # By calling basics.execute_function_on_node() instead of calling evaluate() directly,
                # we implicitly perform checks and automatically delegate to the correct class
                # in cases where a field can map to one of multiple different classes.
                # (this happens below, where we use 'choice' instead of 'value' to refer to a group of possible classes.)
                return basics.execute_function_on_node(value='user_input', function='evaluate', obj=on_error,
                                                       stack_objects=stack_objects, kwargs=kwargs)


class SumNode(AbstractNodeForNumbers):
    summands = fields.List(choice='numerical_node', kwargs={'allow_user_input_node': basics.PASS_ARG_ALONG},
                           help="A list of values that are added together. "
                                "Each of these can be any class of type 'numerical_node'.")

    class Meta:
        name = 'sum'
        choice_of = 'numerical_node'
        choice_type = 'sum'
        documentation_name = "Sum"
        documentation_description = """A [[sum]] represents a sum of other numbers."""

    def validate(cls, obj, stack_objects, kwargs):
        obj = super().validate(cls, obj, stack_objects, kwargs)
        return obj

    def evaluate(cls, obj, stack_objects, kwargs):
        """
        Evaluate all objects in the list and return their sum.
        """
        res = 0
        for a in obj['summands']:
            res += basics.execute_function_on_node(choice='numerical_node', function='evaluate', obj=a,
                                                   stack_objects=stack_objects, kwargs=kwargs)
        return res


class ConstantMultipleNode(AbstractNodeForNumbers):
    constant = fields.Choice('numerical_node', kwargs={'allow_user_input_node': False},
                             help="A [[numerical_node]] that must evaluate to a constant,"
                                  " i.e. that mustn't contain a [[user_input]] anywhere.")
    rest = fields.Choice('numerical_node', kwargs={'allow_user_input_node': basics.PASS_ARG_ALONG},
                         help="A [[numerical_node]] of any type.")

    class Meta:
        name = 'constant_multiple'
        choice_of = 'numerical_node'
        choice_type = 'constant_multiple'
        documentation_name = "Constant Multiple"
        documentation_description = """A [[constant_multiple]] consists of one constant value and one value that may contain [[user_input]]."""

    def validate(cls, obj, stack_objects, kwargs):
        """
        During validation, replace the 'constant' with its evaluation.
        """
        # This validates that the 'constant' field is valid.
        # Because it has allow_user_input_node:False, this will raise an Exception if it contains a user_input Node.
        obj = super().validate(cls, obj, stack_objects, kwargs)
        # Evaluate the constant
        # ---
        # This helper keeps track of what is happening in the stack trace, so that error messages become more useful.
        # Putting these wherever we expect things to go wrong is helpful both for debugging our own code,
        # and for showing useful error message to endusers.
        with basics.node_trace_step(stack_objects, "[validating constant_multiple, evaluating constant part]", obj['constant']):
            constant = basics.execute_function_on_node(choice='numerical_node', function='evaluate', obj=obj['constant'],
                                                       stack_objects=stack_objects, kwargs={})
        # Validate the number we just received as a 'constant' Node, to ensure it has the right format.
        with basics.node_trace_step(stack_objects, "[validating constant_multiple, re-validating constant part after validation]", constant):
            obj['constant'] = basics.execute_function_on_node(value='constant', function='validate', obj=constant,
                                                              stack_objects=stack_objects, kwargs={ 'allow_user_input_node': False })
        # Just for good measure, validate the entire object and its fields again, to make sure we didn't miss anything.
        obj = super().validate(cls, obj, stack_objects, kwargs)
        return obj

    def evaluate(cls, obj, stack_objects, kwargs):
        """
        Evaluate both objects and return their product.
        """
        with basics.node_trace_step(stack_objects, "[evaluating constant_multiple]", obj):
            with basics.node_trace_step(stack_objects, "[evaluating constant_multiple, constant part]", obj['constant']):
                constant = basics.execute_function_on_node(choice='numerical_node', function='evaluate', obj=obj['constant'],
                                                           stack_objects=stack_objects, kwargs=kwargs)
            with basics.node_trace_step(stack_objects, "[evaluating constant_multiple, non-constant part]", obj['rest']):
                rest = basics.execute_function_on_node(choice='numerical_node', function='evaluate', obj=obj['rest'],
                                                       stack_objects=stack_objects, kwargs=kwargs)
        return constant * rest
