"""
Respect Linux demanding "user." namespace for xattr
"""

__all__ = [
    "xattr",
]

from xattr import xattr as superxattr


class xattr (superxattr):
    """
    override with "user." namespace.
    """
    def set(self, name, value, options=0):
        """
        Set the extended attribute ``name`` to ``value``
        Raises ``IOError`` on failure.
        """
        self._set("user." + name, value, 0, options | self.options)


def listxattr(f, symlink=False):
    __doc__ = xattr.list.__doc__
    return tuple(xattr(f).list(options=symlink and XATTR_NOFOLLOW or 0))

def getxattr(f, attr, symlink=False):
    __doc__ = xattr.get.__doc__
    return xattr(f).get(attr, options=symlink and XATTR_NOFOLLOW or 0)

def setxattr(f, attr, value, options=0, symlink=False):
    __doc__ = xattr.set.__doc__
    if symlink:
        options |= XATTR_NOFOLLOW
    return xattr(f).set(attr, value, options=options)

def removexattr(f, attr, symlink=False):
    __doc__ = xattr.remove.__doc__
    options = symlink and XATTR_NOFOLLOW or 0
    return xattr(f).remove(attr, options=options)
