import json
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../..')))

from syntaxTrees import functions


# This demonstrates custom extra validation code.
# This object is invalid because we use a user_input Node inside the 'constant' part of a 'constant_multiple'
obj = {
    'type': 'constant_multiple',
    'constant': {
        'type': 'user_input',
        'message': "Please enter a number. Nobody will ever read this message, because it's invalid!",
    },
    'rest': 42,
}
validated_obj = functions.validate_example_object(obj)
print(json.dumps(validated_obj, indent=4))
