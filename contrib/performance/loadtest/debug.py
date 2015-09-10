def printargs(func):
    """
    This decorator prints the arguments passed to a function before calling it

    Example:
        @printargs
        def foo(a, b, c, *args, **kwargs):
            pass

        foo(1, 2, 3, 4, 5, x=6, y=7)
        # prints `foo(a:1, b:2, c:3, args=(4, 5), kwargs={'y': 7, 'x': 6})`

    """
    fname = func.func_name
    fc = func.func_code
    argcount = fc.co_argcount
    argnames = fc.co_varnames[:argcount]
    def wrapper(*args, **kwargs):
        named_args = ', '.join(['{0}: {1}'.format(arg, val) for arg, val in zip(argnames, args[:argcount])])
        print "{0}({1}, args={2}, kwargs={3})".format(
            fname,
            named_args,
            args[argcount:],
            kwargs
        )
        return func(*args, **kwargs)
    return wrapper
