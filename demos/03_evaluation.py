import json
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../..')))

from syntaxTrees import functions


# After validating this structure, we can evaluate it to ask the user for input.
# Try it out.
obj = {
    'type': 'sum',
    'summands': [
        {
            'type': 'constant_multiple',
            'constant': {
                'type': 'sum',
                'summands': [10, 20]
            },
            'rest': 42,
        },
        {
            'message': "Please enter a number.",
            'on_error': {
                'message': "Invalid number. Please try again.",
                'on_error': {
                    'message': "One more try, or I will just pick the number 100.",
                    'on_error': 100,
                    '_comment': "This comment is an optional field that does nothing."
                }
            }
        }
    ]
}
validated_obj = functions.validate_example_object(obj)

evaluation_result = functions.evaluate_numerical_node(validated_obj)
print("result: {}".format(evaluation_result))
