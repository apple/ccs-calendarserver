#! /bin/bash
# -*- sh-basic-offset: 2 -*-

##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

# Echo the major.minor version of the given Python interpreter.

py_version () {
  local python="$1"; shift;
  echo "$("${python}" -c "from distutils.sysconfig import get_python_version; print get_python_version()")";
}

# Test if a particular python interpreter is available, given the full path to
# that interpreter.

try_python () {
  local python="$1"; shift;

  if [ -z "${python}" ]; then
    return 1;
  fi;

  if ! type "${python}" > /dev/null 2>&1; then
    return 1;
  fi;

  local py_version="$(py_version "${python}")";
  if [ "${py_version/./}" -lt "25" ]; then
    return 1;
  fi;
  return 0;
}


# Detect which version of Python to use, then print out which one was detected.

detect_python_version () {
  for v in "2.7" "2.6" ""
  do
    for p in                                                            \
      "${PYTHON:=}"                                                     \
      "python${v}"                                                      \
      "/usr/local/bin/python${v}"                                       \
      "/usr/local/python/bin/python${v}"                                \
      "/usr/local/python${v}/bin/python${v}"                            \
      "/opt/bin/python${v}"                                             \
      "/opt/python/bin/python${v}"                                      \
      "/opt/python${v}/bin/python${v}"                                  \
      "/Library/Frameworks/Python.framework/Versions/${v}/bin/python"   \
      "/opt/local/bin/python${v}"                                       \
      "/sw/bin/python${v}"                                              \
      ;
    do
      if try_python "${p}"; then
        echo "${p}";
        return 0;
      fi;
    done;
  done;
  return 1;
}

# Detect if the given Python module is installed in the system Python configuration.
py_have_module () {
  local version=""; # Minimum version required

  OPTIND=1;
  while getopts "v:" option; do
    case "${option}" in
      'v') version="${OPTARG}"; ;;
    esac;
  done;
  shift $((${OPTIND} - 1));

  local module="$1"; shift;

  "${python}" -c "import ${module}" > /dev/null 2>&1;
  result=$?;

  if [ $result == 0 ] && [ -n "${version}" ]; then
    for symbol in "xxxx" "__version__" "version"; do
      if module_version="$(
        "${python}" -c \
        'print __import__("'"${module}"'").'"$symbol"';' \
        2>/dev/null
      )"; then
        break;
      fi;
    done;

    if [ -z "${module_version}" ]; then
      if ! "${print_path}"; then
        echo "Unable to determine version for ${module}.";
      fi;
      result=1;
    elif ! cmp_version "${version}" "${module_version}"; then
      if ! "${print_path}"; then
        echo "A system version of ${module} exists, but version is ${module_version} (< ${version}).";
      fi;
      result=1;
    fi;
  fi;

  return ${result};
}

# Compare version numbers

cmp_version () {
  local  v="$1"; shift;
  local mv="$1"; shift;

  local result;

  while true; do
     vh="${v%%.*}"; # Get highest-order segment
    mvh="${mv%%.*}";

    if [ "${vh}" -gt "${mvh}" ]; then
      result=1;
      break;
    fi;

    if [ "${vh}" -lt "${mvh}" ]; then
      result=0;
      break;
    fi;

    if [ "${v}" == "${v#*.}" ]; then
      # No dots left, so we're ok
      result=0;
      break;
    fi;

    if [ "${mv}" == "${mv#*.}" ]; then
      # No dots left, so we're not gonna match
      result=1;
      break;
    fi;

     v="${v#*.}";
    mv="${mv#*.}";
  done;

  return ${result};
}

# Detect which python to use, and store it in the 'python' variable, as well as
# setting up variables related to version and build configuration.

init_py () {
  # First, detect the appropriate version of Python to use, based on our version
  # requirements and the environment.  Note that all invocations of python in
  # our build scripts should therefore be '"${python}"', not 'python'; this is
  # important on systems with older system pythons (2.4 or earlier) with an
  # alternate install of Python, or alternate python installation mechanisms
  # like virtualenv.
  python="$(detect_python_version)";

  # Set the $PYTHON environment variable to an absolute path pointing at the
  # appropriate python executable, a standard-ish mechanism used by certain
  # non-distutils things that need to find the "right" python.  For instance,
  # the part of the PostgreSQL build process which builds pl_python.  Note that
  # detect_python_version, above, already honors $PYTHON, so if this is already
  # set it won't be stomped on, it will just be re-set to the same value.
  export PYTHON="$(type -p ${python})";

  if [ -z "${python:-}" ]; then
    echo "No suitable python found. Python 2.6 is required.";
    exit 1;
  fi

          py_platform="$("${python}" -c "from distutils.util import get_platform; print get_platform()")";
           py_version="$(py_version "${python}")";
   py_platform_libdir="lib.${py_platform}-${py_version}";
  py_platform_scripts="scripts-${py_version}";
            py_prefix="$("${python}" -c "import sys; print sys.prefix;")";
            py_libdir="$("${python}" -c "from distutils.sysconfig import get_python_lib; print get_python_lib(1);")";
}

init_py;

