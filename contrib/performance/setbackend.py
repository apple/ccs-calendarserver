import sys
from xml.etree import ElementTree
from xml.etree import ElementPath

def main():
    conf = ElementTree.parse(file(sys.argv[1]))
    if sys.argv[2] == 'database':
        value = 'true'
    else:
        value = 'false'
    replace(conf.getiterator(), value)
    conf.write(sys.stdout)


def replace(elements, value):
    found = False
    for ele in elements:
        if found:
            ele.tag = value
            return
        if ele.tag == 'key' and ele.text == 'UseDatabase':
            found = True
    raise RuntimeError("Failed to find <key>UseDatabase</key>")
