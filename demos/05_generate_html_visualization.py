import json
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../..')))

from syntaxTrees import functions


# Generate HTML code that represents the below object and includes links to the documentation.
# (This requires CSS / JS to show up properly, which does not come with this project)
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

html = functions.visualize_numerical_node_in_html(validated_obj)

print(html)
