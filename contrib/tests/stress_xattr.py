import os
from random import choice
from string import uppercase

from xattr import getxattr, listxattr, removexattr, setxattr

def randstr(length):
    return "".join(choice(uppercase) for n in xrange(length))

def main(path):
    while True:
        try:
            filename = os.path.join(path, randstr(8))
            fout = open(filename, "w")
            fout.write("---")
            fout.close()

            print filename
            for n in xrange(1024):
                expectedAttr = {}
                for m in xrange(1024):
                    key, value = randstr(10), randstr(100)
                    expectedAttr[key] = value
                    setxattr(filename, key, value)
                    assert getxattr(filename, key) == value, (key,value)

                attrList = sorted(listxattr(filename))
                expectedAttrList = sorted(expectedAttr.keys())
                assert attrList == expectedAttrList, (attrList, expectedAttrList)
    
                for key, value in expectedAttr.items():
                    assert getxattr(filename, key) == value
                    removexattr(filename, key)

                attrList = listxattr(filename)
                assert not attrList, attrList

                print n          
        finally:
            os.remove(filename)

if __name__ == "__main__":
    import sys
    path = "."
    if len(sys.argv) == 2:
        path = sys.argv[1]
    elif len(sys.argv) > 2:
        print "Usage: python stress_xattr.py [path]"
    main(path)
