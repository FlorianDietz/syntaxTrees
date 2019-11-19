import json
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(__file__, '../..')))

from syntaxTrees import functions


# Generate documentation in HTML
# (This requires CSS/JS to show up properly, which does not come with this project)
html = functions.get_documentation_of_numerical_nodes()

print(html)