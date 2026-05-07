import functools


def doLog(project, *args, **kwargs):
    '''Prints arguments to stdout with tag'''
    try:
        kwargs_str = repr(kwargs) if kwargs else ''
        args_str = ' '.join([unicode(s) for s in args])
        print '[%s] %s %s' % (project, args_str, kwargs_str)
    except:
        try:
            print '[%s] %s' % (project, str(args))
        except:
            pass


LOG_NOTE = functools.partial(doLog, '[NOTE]')
LOG_DEBUG = functools.partial(doLog, '[DEBUG]')