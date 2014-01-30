# -*- sh-basic-offset: 2 -*-
##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

. "${wd}/bin/_py.sh";


echo_header () {
  echo "$@";
  echo "";
}


using_system () {
  local name="$1"; shift;
  echo_header "Using system version of ${name}.";
}


# Provide a default value: if the variable named by the first argument is
# empty, set it to the default in the second argument.
conditional_set () {
  local var="$1"; shift;
  local default="$1"; shift;
  if [ -z "$(eval echo "\${${var}:-}")" ]; then
    eval "${var}=\${default:-}";
  fi;
}


# Checks for presence of a C header, optionally with a version comparison.
# With only a header file name, try to include it, returning nonzero if absent.
# With 3 params, also attempt a version check, returning nonzero if too old.
# Param 2 is a minimum acceptable version number
# Param 3 is a #define from the source that holds the installed version number
# Examples:
#   Assert that ldap.h is present
#     find_header "ldap.h"
#   Assert that ldap.h is present with a version >= 20344
#     find_header "ldap.h" 20344 "LDAP_VENDOR_VERSION"
find_header () {
  local sys_header="$1"; shift;
  if [ $# -ge 1 ]; then
      local   min_version="$1"; shift;
      local version_macro="$1"; shift;
  fi;

  # No min_version given:
  # Check for presence of a header. We use the "-c" cc option because we don't
  # need to emit a file; cc exits nonzero if it can't find the header
  if [ -z "${min_version:-}" ]; then
    echo "#include <${sys_header}>" | cc -x c -c - -o /dev/null 2> /dev/null;
    return "$?";
  fi;

  # Check for presence of a header of specified version
  local found_version="$(printf "#include <${sys_header}>\n${version_macro}\n" | cc -x c -E - | tail -1)";

  if [ "${found_version}" == "${version_macro}" ]; then
    # Macro was not replaced
    return 1;
  fi;

  if cmp_version "${min_version}" "${found_version}"; then
    return 0;
  else
    return 1;
  fi;
};


# Initialize all the global state required to use this library.
init_build () {
  init_py;

       do_get="true";
     do_setup="true";
  force_setup="false";

      dev_home="${wd}/.develop";
     dev_roots="${dev_home}/roots";
  dep_packages="${dev_home}/pkg";
   dep_sources="${dev_home}/src";

    py_root="${dev_roots}/py_modules";
  py_libdir="${py_root}/lib/python";
  py_bindir="${py_root}/bin";

  mkdir -p "${dep_sources}";

  if "${force_setup}"; then
    rm -rf "${py_root}";
  fi;

  # Set up virtual environment

  "${bootstrap_python}" -m virtualenv "${py_root}";

  python="${py_bindir}/python";

  # Make sure setup got called enough to write the version file.

  "${python}" "${wd}/setup.py" check > /dev/null;

  # These variables are defaults for things which might be configured by
  # environment; only set them if they're un-set.

  conditional_set wd "$(pwd)";

  # Find some hashing commands
  # sha1() = sha1 hash, if available
  # md5()  = md5 hash, if available
  # hash() = default hash function
  # $hash  = name of the type of hash used by hash()

  hash="";

  if type -ft openssl > /dev/null; then
    if [ -z "${hash}" ]; then hash="md5"; fi;
    md5 () { "$(type -p openssl)" dgst -md5 "$@"; }
  elif type -ft md5 > /dev/null; then
    if [ -z "${hash}" ]; then hash="md5"; fi;
    md5 () { "$(type -p md5)" "$@"; }
  elif type -ft md5sum > /dev/null; then
    if [ -z "${hash}" ]; then hash="md5"; fi;
    md5 () { "$(type -p md5sum)" "$@"; }
  fi;

  if type -ft sha1sum > /dev/null; then
    if [ -z "${hash}" ]; then hash="sha1sum"; fi;
    sha1 () { "$(type -p sha1sum)" "$@"; }
  fi;
  if type -ft shasum > /dev/null; then
    if [ -z "${hash}" ]; then hash="sha1"; fi;
    sha1 () { "$(type -p shasum)" "$@"; }
  fi;

  if [ "${hash}" == "sha1" ]; then
    hash () { sha1 "$@"; }
  elif [ "${hash}" == "md5" ]; then
    hash () { md5 "$@"; }
  elif type -t cksum > /dev/null; then
    hash="hash";
    hash () { cksum "$@" | cut -f 1 -d " "; }
  elif type -t sum > /dev/null; then
    hash="hash";
    hash () { sum "$@" | cut -f 1 -d " "; }
  else
    hash () { echo "INTERNAL ERROR: No hash function."; exit 1; }
  fi;
}


# If do_get is turned on, get an archive file containing a dependency via HTTP.
www_get () {
  if ! "${do_get}"; then return 0; fi;

  local  md5="";
  local sha1="";

  OPTIND=1;
  while getopts "m:s:" option; do
    case "${option}" in
      'm')  md5="${OPTARG}"; ;;
      's') sha1="${OPTARG}"; ;;
    esac;
  done;
  shift $((${OPTIND} - 1));

  local name="$1"; shift;
  local path="$1"; shift;
  local  url="$1"; shift;

  if "${force_setup}"; then
    rm -rf "${path}";
  fi;
  if [ ! -d "${path}" ]; then
    local ext="$(echo "${url}" | sed 's|^.*\.\([^.]*\)$|\1|')";

    untar () { tar -xvf -; }
    unzipstream () { tmp="$(mktemp -t ccsXXXXX)"; cat > "${tmp}"; unzip "${tmp}"; rm "${tmp}"; }
    case "${ext}" in
      gz|tgz) decompress="gzip -d -c"; unpack="untar"; ;;
      bz2)    decompress="bzip2 -d -c"; unpack="untar"; ;;
      tar)    decompress="untar"; unpack="untar"; ;;
      zip)    decompress="cat"; unpack="unzipstream"; ;;
      *)
        echo "Error in www_get of URL ${url}: Unknown extension ${ext}";
        exit 1;
        ;;
    esac;

    echo "";

    if [ -n "${dep_packages}" ] && [ -n "${hash}" ]; then
      mkdir -p "${dep_packages}";

      local cache_basename="$(echo ${name} | tr '[ ]' '_')-$(echo "${url}" | hash)-$(basename "${url}")";
      local cache_file="${dep_packages}/${cache_basename}";

      check_hash () {
        local file="$1"; shift;

        local sum="$(md5 "${file}" | perl -pe 's|^.*([0-9a-f]{32}).*$|\1|')";
        if [ -n "${md5}" ]; then
          echo "Checking MD5 sum for ${name}...";
          if [ "${md5}" != "${sum}" ]; then
            echo "ERROR: MD5 sum for downloaded file is wrong: ${sum} != ${md5}";
            return 1;
          fi;
        else
          echo "MD5 sum for ${name} is ${sum}";
        fi;

        local sum="$(sha1 "${file}" | perl -pe 's|^.*([0-9a-f]{40}).*$|\1|')";
        if [ -n "${sha1}" ]; then
          echo "Checking SHA1 sum for ${name}...";
          if [ "${sha1}" != "${sum}" ]; then
            echo "ERROR: SHA1 sum for downloaded file is wrong: ${sum} != ${sha1}";
            return 1;
          fi;
        else
          echo "SHA1 sum for ${name} is ${sum}";
        fi;
      }

      if [ ! -f "${cache_file}" ]; then
        echo "No cache file: ${cache_file}";

        echo "Downloading ${name}...";

        local pkg_host="static.calendarserver.org";
        local pkg_path="/pkg";

        #
        # Try getting a copy from calendarserver.org.
        #
        local tmp="$(mktemp "/tmp/${cache_basename}.XXXXXX")";
        curl -L "http://${pkg_host}${pkg_path}/${cache_basename}" -o "${tmp}" || true;
        echo "";
        if [ ! -s "${tmp}" ] || grep '<title>404 Not Found</title>' "${tmp}" > /dev/null; then
          rm -f "${tmp}";
          echo "${name} is not available from calendarserver.org; trying upstream source.";
        elif ! check_hash "${tmp}"; then
          rm -f "${tmp}";
          echo "${name} from calendarserver.org is invalid; trying upstream source.";
        fi;

        #
        # That didn't work. Try getting a copy from the upstream source.
        #
        if [ ! -f "${tmp}" ]; then
          curl -L "${url}" -o "${tmp}";
          echo "";

          if [ ! -s "${tmp}" ] || grep '<title>404 Not Found</title>' "${tmp}" > /dev/null; then
            rm -f "${tmp}";
            echo "${name} is not available from upstream source: ${url}";
            exit 1;
          elif ! check_hash "${tmp}"; then
            rm -f "${tmp}";
            echo "${name} from upstream source is invalid: ${url}";
            exit 1;
          fi;

          if egrep "^${pkg_host}" "${HOME}/.ssh/known_hosts" > /dev/null 2>&1; then
            echo "Copying cache file up to ${pkg_host}.";
            if ! scp "${tmp}" "${pkg_host}:/var/www/static${pkg_path}/${cache_basename}"; then
              echo "Failed to copy cache file up to ${pkg_host}.";
            fi;
            echo ""
          fi;
        fi;

        #
        # OK, we should be good
        #
        mv "${tmp}" "${cache_file}";
      else
        #
        # We have the file cached, just verify hash
        #
        if ! check_hash "${cache_file}"; then
          exit 1;
        fi;
      fi;

      echo "Unpacking ${name} from cache...";
      get () { cat "${cache_file}"; }
    else
      echo "Downloading ${name}...";
      get () { curl -L "${url}"; }
    fi;

    rm -rf "${path}";
    cd "$(dirname "${path}")";
    get | ${decompress} | ${unpack};
    cd /;
  fi;
}


# If do_get is turned on, check a name out from SVN.
svn_get () {
  if ! "${do_get}"; then
    return 0;
  fi;

  local     name="$1"; shift;
  local     path="$1"; shift;
  local      uri="$1"; shift;
  local revision="$1"; shift;

  if [ -d "${path}" ]; then
    local wc_uri="$(svn info --xml "${path}" 2> /dev/null | sed -n 's|^.*<url>\(.*\)</url>.*$|\1|p')";

    if "${force_setup}"; then
      # Verify that we have a working copy checked out from the correct URI
      if [ "${wc_uri}" != "${uri}" ]; then
        echo "Current working copy (${path}) is from the wrong URI: ${wc_uri} != ${uri}";
        rm -rf "${path}";
        svn_get "${name}" "${path}" "${uri}" "${revision}";
        return $?;
      fi;

      echo "Reverting ${name}...";
      svn revert -R "${path}";

      echo "Updating ${name}...";
      svn update -r "${revision}" "${path}";
    else
      # Verify that we have a working copy checked out from the correct URI
      if [ "${wc_uri}" != "${uri}" ]; then
        echo "Current working copy (${path}) is from the wrong URI: ${wc_uri} != ${uri}";
        echo "Performing repository switch for ${name}...";
        svn switch -r "${revision}" "${uri}" "${path}";
      else
        local svnversion="$(svnversion "${path}")";
        if [ "${svnversion%%[M:]*}" != "${revision}" ]; then
          echo "Updating ${name}...";
          svn update -r "${revision}" "${path}";
        fi;
      fi;
    fi;
  else
    checkout () {
      echo "Checking out ${name}...";
      svn checkout -r "${revision}" "${uri}@${revision}" "${path}";
    }

    if [ "${revision}" != "HEAD" ] && \
       [ -n "${dep_packages}" ] && \
       [ -n "${hash}" ] \
    ; then
      local cacheid="${name}-$(echo "${uri}" | hash)";
      local cache_file="${dep_packages}/${cacheid}@r${revision}.tgz";

      mkdir -p "${dep_packages}";

      if [ -f "${cache_file}" ]; then
        echo "Unpacking ${name} from cache...";
        mkdir -p "${path}";
        tar -C "${path}" -xvzf "${cache_file}";
      else
        checkout;
        echo "Caching ${name}...";
        tar -C "${path}" -cvzf "${cache_file}" .;
      fi;
    else
      checkout;
    fi;
  fi;
}


# Run 'make' with the given command line, prepending a -j option appropriate to
# the number of CPUs on the current machine, if that can be determined.
jmake () {
  case "$(uname -s)" in
    Darwin|Linux)
      ncpu="$(getconf _NPROCESSORS_ONLN)";
      ;;
    FreeBSD)
      ncpu="$(sysctl hw.ncpu)";
      ncpu="${ncpu##hw.ncpu: }";
      ;;
  esac;

  if [ -n "${ncpu:-}" ] && [[ "${ncpu}" =~ ^[0-9]+$ ]]; then
    make -j "${ncpu}" "$@";
  else
    make "$@";
  fi;
}

# Declare a dependency on a C project built with autotools.
c_dependency () {
  local f_hash="";

  OPTIND=1;
  while getopts "m:s:" option; do
    case "${option}" in
      'm') f_hash="-m ${OPTARG}"; ;;
      's') f_hash="-s ${OPTARG}"; ;;
    esac;
  done;
  shift $((${OPTIND} - 1));

  local name="$1"; shift;
  local path="$1"; shift;
  local  uri="$1"; shift;

  # Extra arguments are processed below, as arguments to './configure'.

  srcdir="${dep_sources}/${path}";
  # local dstroot="${srcdir}/_root";
  local dstroot="${dev_roots}/${name}";

  www_get ${f_hash} "${name}" "${srcdir}" "${uri}";

  export              PATH="${dstroot}/bin:${PATH}";
  export    C_INCLUDE_PATH="${dstroot}/include:${C_INCLUDE_PATH:-}";
  export   LD_LIBRARY_PATH="${dstroot}/lib:${dstroot}/lib64:${LD_LIBRARY_PATH:-}";
  export          CPPFLAGS="-I${dstroot}/include ${CPPFLAGS:-} ";
  export           LDFLAGS="-L${dstroot}/lib -L${dstroot}/lib64 ${LDFLAGS:-} ";
  export DYLD_LIBRARY_PATH="${dstroot}/lib:${dstroot}/lib64:${DYLD_LIBRARY_PATH:-}";
  export PKG_CONFIG_PATH="${dstroot}/lib/pkgconfig:${PKG_CONFIG_PATH:-}";

  if "${do_setup}"; then
    if "${force_setup}"; then
        rm -rf "${dstroot}";
    fi;
    if [ ! -d "${dstroot}" ]; then
      echo "Building ${name}...";
      cd "${srcdir}";
      ./configure --prefix="${dstroot}" "$@";
      jmake;
      jmake install;
    else
      echo "Using built ${name}.";
      echo "";
    fi;
  fi;
}


ruler () {
  echo "____________________________________________________________";
  echo "";

  if [ $# -gt 0 ]; then
    echo "$@";
  fi;
}



#
# Build C dependencies
#
c_dependencies () {
  if ! "${do_setup}"; then return 0; fi;

     c_glue_root="${dev_roots}/c_glue";
  c_glue_include="${c_glue_root}/include";

  export C_INCLUDE_PATH="${c_glue_include}:${C_INCLUDE_PATH:-}";

  ruler;
  if find_header ffi.h; then
    using_system "libffi";
  elif find_header ffi/ffi.h; then
    mkdir -p "${c_glue_include}";
    echo "#include <ffi/ffi.h>" > "${c_glue_include}/ffi.h"
    using_system "libffi";
  else
    c_dependency -m "45f3b6dbc9ee7c7dfbbbc5feba571529" \
      "libffi" "libffi-3.0.13" \
      "ftp://sourceware.org/pub/libffi/libffi-3.0.13.tar.gz"
  fi;

  ruler;
  if find_header ldap.h 20428 LDAP_VENDOR_VERSION; then
    using_system "OpenLDAP";
  else
    local v="2.4.38";
    local n="openldap";
    local p="${n}-${v}";
    c_dependency -m "39831848c731bcaef235a04e0d14412f" \
      "OpenLDAP" "${p}" \
      "http://www.openldap.org/software/download/OpenLDAP/${n}-release/${p}.tgz" \
      --disable-bdb --disable-hdb;
  fi;

  ruler;
  if find_header sasl.h; then
    using_system "SASL";
  elif find_header sasl/sasl.h; then
    mkdir -p "${c_glue_include}";
    echo "#include <sasl/sasl.h>" > "${c_glue_include}/sasl.h"
    using_system "SASL";
  else
    local v="2.1.26";
    local n="cyrus-sasl";
    local p="${n}-${v}";
    c_dependency -m "a7f4e5e559a0e37b3ffc438c9456e425" \
      "Cyrus SASL" "${p}" \
      "ftp://ftp.cyrusimap.org/cyrus-sasl/${p}.tar.gz" \
      --disable-macos-framework;
  fi;

  ruler;
  if type -P memcached > /dev/null; then
    using_system "memcached";
  else
    local le="libevent-2.0.21-stable";
    local mc="memcached-1.4.16";
    c_dependency -m "b2405cc9ebf264aa47ff615d9de527a2" \
      "libevent" "${le}" \
      "http://github.com/downloads/libevent/libevent/${le}.tar.gz";
    c_dependency -m "1c5781fecb52d70b615c6d0c9c140c9c" \
      "memcached" "${mc}" \
      "http://www.memcached.org/files/${mc}.tar.gz";
  fi;

  ruler;
  if type -P postgres > /dev/null; then
    using_system "Postgres";
  else
    local v="9.3.1";
    local n="postgresql";
    local p="${n}-${v}";

    if type -P dtrace > /dev/null; then
      local enable_dtrace="--enable-dtrace";
    else
      local enable_dtrace="";
    fi;

    c_dependency -m "c003d871f712d4d3895956b028a96e74" \
      "PostgreSQL" "${p}" \
      "http://ftp.postgresql.org/pub/source/v${v}/${p}.tar.bz2" \
      --with-python ${enable_dtrace};
  fi;

}


#
# Build Python dependencies
#
py_dependencies () {
  export PATH="${py_root}/bin:${PATH}";

  if ! "${do_setup}"; then return 0; fi;

  for requirements in "${wd}/requirements/py_"*".txt"; do

    ruler "Preparing Python requirements: ${requirements}";
    echo "";

    if ! "${python}" -m pip install               \
        --requirement "${requirements}"           \
        --download-cache "${dev_home}/pip_cache"  \
        --log "${dev_home}/pip.log"               \
    ; then
      err=$?;
      echo "Unable to set up Python requirements: ${requirements}";
      if [ "${requirements#${wd}/requirements/py_opt_}" != "${requirements}" ]; then
        echo "Requirements ${requirements} are optional; continuing.";
      else
        echo "";
        echo "pip log: ${dev_home}/pip.log";
        return 1;
      fi;
    fi;

  done;

  echo "";
}



#
# Set up for development
#
develop () {
  init_build;
  c_dependencies;
  py_dependencies;
}
