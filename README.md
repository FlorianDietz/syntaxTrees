# syntaxTrees


This library allows you to define schemas for parsing JSON objects. It is similar to [json-schema](https://json-schema.org/). However, schemas are defined as classes instead of JSON objects and have some additional features:

* You can make objects depend on each other, automatically fill in missing fields with defaults, and even programmatically generate fields based on context. Since it's class-based, it is easy to write extensions simply by overwriting the validate() method.
* The error messages are very understandable, and they even make context-dependent suggestions for fixing errors.
* You can define arbitrary methods to operate on parsed JSON objects that match the schema. In the example nodesExample.py, this is demonstrated on math functions, but you can also implement much more complex functions. In my startup [elody.com](https://elody.com), this was used to implement the entire control logic of an AI and to decide under which circumstances which software is appropriate to use.
* Automatically generate documentation that describes exactly how the syntax tree elements are connected. This documentation is generated as HTML, and contains links to make it very easy to navigate. See here for an example: <https://elody.com/tutorial/documentation_objects/>
* You can also create HTML visualizations of an individual JSON object. This is an HTML page that displays the JSON element, and also contains links back to the documentation. See here for an example: <https://elody.com/rule/view/353/#default-values-hidden>


## Short example

You can define the syntactical logic through classes like this:

```python
class MyExampleNode(syntaxTreesBasics.Node):
    field_1 = fields.Float()
    field_2 = fields.String()
    field_3 = fields.Value('my_example_node', null=True, default=None)
    class Meta:
        name = 'my_example_node'
```

or with more details, like this:

```python
class MyExampleNode(syntaxTreesBasics.Node):
    field_1 = fields.Float(default=0, min=-1000, max=1000, help="Comments like this one will appear in the automatically generated HTML documentation.")
    field_2 = fields.String()
    field_3 = fields.Value('my_example_node', null=True, default=None, help="This field is recursive and defines another Node of the same type as this one.")
    class Meta:
        name = 'my_example_node'
        documentation_name = "My Example Node"
        documentation_description = """This text appears in the automatically generated HTML documentation. It can even contain links to other parts of the documentation, [my_example_node|like so]."""
    def an_example_function(cls, obj, stack_objects, kwargs):
        """
        This is an example of a function that can operate on any JSON object that has been parsed correctly.
        Because each type of Node can define its own functions, this is a very flexible way to associate logic with JSON objects.
        Note that this class never actually gets instantiated. It just acts as a pattern for operating on JSON objects. That's why many of its functions have 'cls' (the class) as the first argument and not 'self'.
        This example function just returns the depth of the JSON object, since my_example_node is recursive.
        """
        if obj['field_3'] is None:
            return 1
        else:
            return 1 + syntaxTreesBasics.execute_function_on_node(value='my_example_node', function='an_example_function', obj=obj['field_3'], stack_objects=stack_objects, kwargs=kwargs)
```

which can then parse and validate JSON blocks like this while filling in missing default values:

```python
{
    'field_1' : 5,
    'field_2' : "foo",
    'field_3' : {
        'field_2' : "bar",
        'field_3' : {
            'field_2' : "baz"
        }
    }
}
```


## Installation

`pip install syntaxTrees`

## Usage


Have a look at the files syntaxTrees/nodesExample.py and syntaxTrees/functions.py

The former defines an example of a syntax tree, while the latter defines functions that operate on these syntax trees.

This example defines a tree of mathematical functions, where each leaf node is either a constant, or a request to get data from the user through the console.

Run the files in the /demos/ folder to test it.


## Note

Some advanced features of this project are admittedly not as well documented as they should be.

If you want help with using any of the advanced features, write me an email and I will search out the code you need and explain things.

I originally wrote all of this code as part of my own startup [elody.com](https://elody.com), and only decided to make a library out of it later. I didn't want to spend too much time on prettying this up, before I know if people are actually going to use this.
