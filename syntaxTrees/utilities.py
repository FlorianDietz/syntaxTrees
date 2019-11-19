import traceback
import sys


def get_error_message_details(exception=None):
    """
    Get a nicely formatted string for an error message collected with sys.exc_info().
    """
    if exception is None:
        exception = sys.exc_info()
    exc_type, exc_obj, exc_trace = exception
    trace = traceback.extract_tb(exc_trace)
    error_msg = "Traceback is:\n"
    for (file,linenumber,affected,line) in trace:
        error_msg += "\t> Error at function %s\n" % (affected)
        error_msg += "\t  At: %s:%s\n" % (file,linenumber)
        error_msg += "\t  Source: %s\n" % (line)
    error_msg += "%s\n%s" % (exc_type, exc_obj,)
    return error_msg


class InvalidParamsException(Exception):
    """
    An exception that indicates that a parameter given to the server is invalid.
    This exception is the standard exception generated when a user does anything incorrectly.
    """
    pass


class ProgrammingError(Exception):
    """
    This exception shouldn't happen during the normal course of operations at all.
    If it does, it means that a programming mistake has been made.
    """
    pass
