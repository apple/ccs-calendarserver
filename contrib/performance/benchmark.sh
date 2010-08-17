#!/bin/bash
sudo PYTHONPATH=$PYTHONPATH:../../../vobject/:../../../../CalDAVClientLibrary/trunk/src:../../../Twisted/ ./benchmark "$@"
