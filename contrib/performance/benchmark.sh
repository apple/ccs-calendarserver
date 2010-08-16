#!/bin/bash
sudo PYTHONPATH=$PYTHONPATH:../../../vobject/:../../../../CalDAVClientLibrary/trunk/src:../../../Twisted/ python -i mkcal.py "$@"

