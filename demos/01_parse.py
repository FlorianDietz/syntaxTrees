import json
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../..')))

from syntaxTrees import functions


# Note how the types of each object in the below JSON get inferred and defaults get set automatically.
# Try changing something, and you will see a useful error message telling you exactly where things have become unclear.
# (When a 'type' field is set explicitly, the error message will be more useful since the program will now which
# of the possible numerical fields the dictionary is supposed to be.)
obj = {
    'type': 'sum',
    'summands': [
        {
            'type': 'constant_multiple',
            'constant': {
                'type': 'sum',
                # These first get interpreted as shortforms of a 'constant' Node,
                # then evaluated and simplified into 30,
                # which then gets expanded into a 'constant' node again.
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
print(json.dumps(validated_obj, indent=4))
