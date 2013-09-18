# -*- sh-basic-offset: 2 -*-

##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

. "${wd}/support/py.sh";

echo_header () {
  if ! "${print_path}"; then
    echo "$@";
    echo "";
  fi;
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

find_header () {
  local sysheader="$1"; shift;
  echo "#include <${sysheader}>" | cc -x c -c - -o /dev/null 2> /dev/null;
  return "$?";
}

# Initialize all the global state required to use this library.
init_build () {
            verbose="";
             do_get="true";
           do_setup="true";
             do_run="true";
          do_bundle="false";
        force_setup="false";
      disable_setup="false";
         print_path="false";
  print_environment="false";
            install="";
          daemonize="-X -L";
               kill="false";
            restart="false";
        plugin_name="caldav";
       service_type="Combined";
           read_key="";
            profile="";
            reactor="";

  # These variables are defaults for things which might be configured by
  # environment; only set them if they're un-set.
  conditional_set wd "$(pwd)";
  conditional_set config "${wd}/conf/caldavd-dev.plist";
  conditional_set caldav "${wd}";
  conditional_set CALENDARSERVER_BUILD_DEPS "${caldav}/..";

  if [ -z "${CALENDARSERVER_CACHE_DEPS-}" ]; then
    cache_deps="${wd}/.dependencies";
  else
    cache_deps="${CALENDARSERVER_CACHE_DEPS}";
  fi;

  mkdir -p "${CALENDARSERVER_BUILD_DEPS}";
  top="$(cd "${CALENDARSERVER_BUILD_DEPS}" && pwd -L)";

  if [ -z "${caldavd_wrapper_command:-}" ]; then
    if [ "$(uname -s)" == "Darwin" ] && [ "$(uname -r | cut -d . -f 1)" -ge 9 ]; then
      caldavd_wrapper_command="launchctl bsexec /";
    else
      caldavd_wrapper_command="";
    fi;
  fi;

  patches="${caldav}/lib-patches";

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

  if [ -n "${install}" ] && ! echo "${install}" | grep '^/' > /dev/null; then
    install="$(pwd)/${install}";
  fi;

  svn_uri_base="$(svn info "${caldav}" --xml 2> /dev/null | sed -n 's|^.*<root>\(.*\)</root>.*$|\1|p')";

  conditional_set svn_uri_base "http://svn.calendarserver.org/repository/calendarserver";
}


# This is a hack, but it's needed because installing with --home doesn't work
# for python-dateutil.
do_home_install () {
  install -d "${install_home}";
  install -d "${install_home}/bin";
  install -d "${install_home}/conf";
  install -d "${install_home}/lib/python";

  rsync -av "${install}${py_prefix}/bin/" "${install_home}/bin/";
  rsync -av "${install}${py_libdir}/" "${install_home}/lib/python/";
  rsync -av "${install}${py_prefix}/caldavd/" "${install_home}/caldavd/";

  rm -rf "${install}";
}


# Apply patches from lib-patches to the given dependency codebase.
apply_patches () {
  local name="$1"; shift;
  local path="$1"; shift;

  if [ -d "${patches}/${name}" ]; then
    echo "";
    echo "Applying patches to ${name} in ${path}...";

    cd "${path}";
    find "${patches}/${name}"                  \
        -type f                                \
        -name '*.patch'                        \
        -print                                 \
        -exec patch -p0 --forward -i '{}' ';';
    cd /;

  fi;

  echo "";
  if [ -e "${path}/setup.py" ]; then
    echo "Removing build directory ${path}/build...";
    rm -rf "${path}/build";
    echo "Removing pyc files from ${path}...";
    find "${path}" -type f -name '*.pyc' -print0 | xargs -0 rm -f;
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

  if "${force_setup}" || [ ! -d "${path}" ]; then
    local ext="$(echo "${url}" | sed 's|^.*\.\([^.]*\)$|\1|')";

    case "${ext}" in
      gz|tgz) decompress="gzip -d -c"; ;;
      bz2)    decompress="bzip2 -d -c"; ;;
      tar)    decompress="cat"; ;;
      *)
        echo "Error in www_get of URL ${url}: Unknown extension ${ext}";
        exit 1;
        ;;
    esac;

    echo "";

    if [ -n "${cache_deps}" ] && [ -n "${hash}" ]; then
      mkdir -p "${cache_deps}";

      local cache_basename="${name}-$(echo "${url}" | hash)-$(basename "${url}")";
      local cache_file="${cache_deps}/${cache_basename}";

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
    get | ${decompress} | tar -xvf -;
    apply_patches "${name}" "${path}";
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

      apply_patches "${name}" "${path}";
    else
      if ! "${print_path}"; then
        # Verify that we have a working copy checked out from the correct URI
        if [ "${wc_uri}" != "${uri}" ]; then
          echo "Current working copy (${path}) is from the wrong URI: ${wc_uri} != ${uri}";
          echo "Performing repository switch for ${name}...";
          svn switch -r "${revision}" "${uri}" "${path}";

          apply_patches "${name}" "${path}";
        else
          local svnversion="$(svnversion "${path}")";
          if [ "${svnversion%%[M:]*}" != "${revision}" ]; then
            echo "Updating ${name}...";
            svn update -r "${revision}" "${path}";

            apply_patches "${name}" "${path}";
          fi;
        fi;
      fi;
    fi;
  else
    checkout () {
      echo "Checking out ${name}...";
      svn checkout -r "${revision}" "${uri}@${revision}" "${path}";
    }

    if [ "${revision}" != "HEAD" ] && \
       [ -n "${cache_deps}" ] && \
       [ -n "${hash}" ] \
    ; then
      local cacheid="${name}-$(echo "${uri}" | hash)";
      local cache_file="${cache_deps}/${cacheid}@r${revision}.tgz";

      mkdir -p "${cache_deps}";

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

    apply_patches "${name}" "${path}";
  fi;
}


# (optionally) Invoke 'python setup.py build' on the given python project.
py_build () {
  local     name="$1"; shift;
  local     path="$1"; shift;
  local optional="$1"; shift;

  if "${do_setup}"; then
    echo_header "Building ${name}...";
    cd "${path}";
    if ! "${python}" ./setup.py -q build \
        --build-lib "build/${py_platform_libdir}" "$@"; then
      if "${optional}"; then
        echo "WARNING: ${name} failed to build.";
        echo "WARNING: ${name} is not required to run the server;"\
             "continuing without it.";
      else
        return $?;
      fi;
    fi;
    cd /;
  fi;
}

# If in install mode, install the given package from the given path.
# (Otherwise do nothing.)
py_install () {
  local name="$1"; shift;
  local path="$1"; shift;

  if [ -n "${install}" ]; then
    echo "";
    echo "Installing ${name}...";
    cd "${path}";
    if "${do_bundle}"; then
      # Since we've built our own Python, an option-free installation is the
      # best bet.
      "${python}" ./setup.py install;
    else
      "${python}" ./setup.py install "${install_flag}${install}";
    fi;
    cd /;
  fi;
}


# Declare a dependency on a Python project.
py_dependency () {
  local optional="false"; # Is this dependency optional?
  local override="false"; # Do I need to get this dependency even if the system
                          # already has it?
  local  inplace="";      # Do development in-place; don't run setup.py to
                          # build, and instead add the source directory plus the
                          # given relative path directly to sys.path.  twisted
                          # and pycalendar are developed often enough that this is
                          # convenient.
  local skip_egg="false"; # Skip even the 'egg_info' step, because nothing needs
                          # to be built.
  local revision="0";     # Revision (if svn)
  local get_type="www";   # Protocol to use
  local  version="";      # Minimum version required
  local   f_hash="";      # Checksum flag

  OPTIND=1;
  while getopts "ofi:er:v:m:s:" option; do
    case "${option}" in
      'o') optional="true"; ;;
      'f') override="true"; ;;
      'e') skip_egg="true"; ;;
      'r') get_type="svn"; revision="${OPTARG}"; ;;
      'v')  version="-v ${OPTARG}"; ;;
      'm')   f_hash="-m ${OPTARG}"; ;;
      's')   f_hash="-s ${OPTARG}"; ;;
      'i')
        if [ -z "${OPTARG}" ]; then
          inplace=".";
        else
          inplace="${OPTARG}";
        fi;
        ;;
    esac;
  done;
  shift $((${OPTIND} - 1));

  # args
  local         name="$1"; shift; # the name of the package (for display)
  local       module="$1"; shift; # the name of the python module.
  local distribution="$1"; shift; # the name of the directory to put the
                                  # distribution into.
  local      get_uri="$1"; shift; # what URL should be fetched?

  local srcdir="${top}/${distribution}"

  if "${override}" || ! py_have_module ${version} "${module}"; then
    "${get_type}_get" ${f_hash} "${name}" "${srcdir}" "${get_uri}" "${revision}"
    if [ -n "${inplace}" ]; then
      if "${do_setup}" && "${override}" && ! "${skip_egg}"; then
        echo;
        if py_have_module setuptools; then
          echo_header "Building ${name}... [overrides system, building egg-info only]";
          cd "${srcdir}";
          "${python}" ./setup.py -q egg_info 2>&1 | (
            grep -i -v 'Unrecognized .svn/entries' || true);
          cd /;
        fi;
      fi;
    else
      py_build "${name}" "${srcdir}" "${optional}";
    fi;
    py_install "${name}" "${srcdir}";

    if [ -n "${inplace}" ]; then
      if [ "${inplace}" == "." ]; then
        local add_pythonpath="${srcdir}";
      else
        local add_pythonpath="${srcdir}/${inplace}";
      fi;
      local add_path="${srcdir}/bin";
    else
      local add_pythonpath="${srcdir}/build/${py_platform_libdir}";
      local add_path="${srcdir}/build/${py_platform_scripts}";
    fi;
    export PYTHONPATH="${add_pythonpath}:${PYTHONPATH:-}";
    if [ -d "${add_path}" ]; then
      export PATH="${add_path}:${PATH}";
    fi;
  else
    using_system "${name}";
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

  if "${do_bundle}"; then
    local dstroot="${install}";
    srcdir="${install}/src/${path}";
  else
    srcdir="${top}/${path}";
    local dstroot="${srcdir}/_root";
  fi;

  www_get ${f_hash} "${name}" "${srcdir}" "${uri}";

  export              PATH="${dstroot}/bin:${PATH}";
  export    C_INCLUDE_PATH="${dstroot}/include:${C_INCLUDE_PATH:-}";
  export   LD_LIBRARY_PATH="${dstroot}/lib:${LD_LIBRARY_PATH:-}";
  export          CPPFLAGS="-I${dstroot}/include ${CPPFLAGS:-} ";
  export           LDFLAGS="-L${dstroot}/lib ${LDFLAGS:-} ";
  export DYLD_LIBRARY_PATH="${dstroot}/lib:${DYLD_LIBRARY_PATH:-}";

  if "${do_setup}"; then
    if "${force_setup}" || "${do_bundle}" || [ ! -d "${dstroot}" ]; then
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

# Used only when bundling: write out, into the bundle, an 'environment.sh' file
# that contains all the environment variables necessary to invoke commands in
# the deployed bundle.

write_environment () {
  local dstroot="${install}";
  cat > "${dstroot}/environment.sh" << __EOF__
export              PATH="${dstroot}/bin:\${PATH}";
export    C_INCLUDE_PATH="${dstroot}/include:\${C_INCLUDE_PATH:-}";
export   LD_LIBRARY_PATH="${dstroot}/lib:\${LD_LIBRARY_PATH:-}:\$ORACLE_HOME";
export          CPPFLAGS="-I${dstroot}/include \${CPPFLAGS:-} ";
export           LDFLAGS="-L${dstroot}/lib \${LDFLAGS:-} ";
export DYLD_LIBRARY_PATH="${dstroot}/lib:\${DYLD_LIBRARY_PATH:-}:\$ORACLE_HOME";
__EOF__
}


#
# Enumerate all the dependencies with c_dependency and py_dependency;
# depending on options parsed by ../run:parse_options and on-disk
# state, this may do as little as update the PATH, DYLD_LIBRARY_PATH,
# LD_LIBRARY_PATH and PYTHONPATH, or, it may do as much as download
# and install all dependencies.
#
dependencies () {

  #
  # Dependencies compiled from C source code
  #


  if "${do_bundle}"; then
    # First a bit of bootstrapping: fill out the standard directory structure.
    for topdir in bin lib include share src; do
      mkdir -p "${install}/${topdir}";
    done;

    # Normally we depend on the system Python, but a bundle install should be as
    # self-contained as possible.
    local pyfn="Python-2.7.5";
    c_dependency -m "6334b666b7ff2038c761d7b27ba699c1" \
        "Python" "${pyfn}" \
        "http://www.python.org/ftp/python/2.7.5/${pyfn}.tar.bz2" \
        --enable-shared;
    # Be sure to use the Python we just built.
    export PYTHON="$(type -p python)";
    init_py;
  fi;

  if type -P memcached > /dev/null; then
    using_system "memcached";
  else
    local le="libevent-2.0.17-stable";
    local mc="memcached-1.4.13";
    c_dependency -m "dad64aaaaff16b5fbec25160c06fee9a" \
      "libevent" "${le}" \
      "https://github.com/downloads/libevent/libevent/${le}.tar.gz";
    c_dependency -m "6d18c6d25da945442fcc1187b3b63b7f" \
      "memcached" "${mc}" \
      "http://memcached.googlecode.com/files/${mc}.tar.gz";
  fi;

  if type -P postgres > /dev/null; then
    using_system "Postgres";
  else
    local pgv="9.2.4";
    local pg="postgresql-${pgv}";

    if type -P dtrace > /dev/null; then
      local enable_dtrace="--enable-dtrace";
    else
      local enable_dtrace="";
    fi;

    c_dependency -m "52df0a9e288f02d7e6e0af89ed4dcfc6" \
      "PostgreSQL" "${pg}" \
      "ftp://ftp5.us.postgresql.org/pub/PostgreSQL/source/v${pgv}/${pg}.tar.gz" \
      --with-python ${enable_dtrace};
    :;
  fi;

  if find_header ldap.h; then
    using_system "OpenLDAP";
  else
    c_dependency -m "ec63f9c2add59f323a0459128846905b" \
      "OpenLDAP" "openldap-2.4.25" \
      "http://www.openldap.org/software/download/OpenLDAP/openldap-release/openldap-2.4.25.tgz" \
      --disable-bdb --disable-hdb;
  fi;

  #
  # Python dependencies
  #

  # First, let's make sure that we ourselves are on PYTHONPATH, in case some
  # code (like, let's say, trial) decides to chdir somewhere.
  export PYTHONPATH="${wd}:${PYTHONPATH:-}";

  # Sourceforge mirror hostname.
  local sf="superb-sea2.dl.sourceforge.net";
  local st="setuptools-0.6c11";
  local pypi="http://pypi.python.org/packages/source";

  py_dependency -m "7df2a529a074f613b509fb44feefe74e" \
    "setuptools" "setuptools" "${st}" \
    "$pypi/s/setuptools/${st}.tar.gz";

  local v="4.0.3";
  local n="zope.interface";
  local p="${n}-${v}";
  py_dependency -v 4 -m "1ddd308f2c83703accd1696158c300eb" \
    "Zope Interface" "${n}" "${p}" \
    "http://pypi.python.org/packages/source/z/${n}/${p}.tar.gz";

  local v="0.10";
  local n="pyOpenSSL";
  local p="${n}-${v}";
  py_dependency -v 0.9 -m "34db8056ec53ce80c7f5fc58bee9f093" \
    "${n}" "OpenSSL" "${p}" \
    "http://pypi.python.org/packages/source/p/${n}/${p}.tar.gz";

  local n="PyKerberos";
  if type -P krb5-config > /dev/null; then
    py_dependency -r 9409 \
      "${n}" "kerberos" "${n}" \
      "${svn_uri_base}/${n}/trunk";
  fi;

  local v="0.6.1";
  local n="xattr";
  local p="${n}-${v}";
  py_dependency -v 0.5 -r 1038 \
    "${n}" "${n}" "${n}" \
    "http://svn.red-bean.com/bob/${n}/releases/${p}/";

  if [ -n "${ORACLE_HOME:-}" ]; then
    local v="5.1";
    local n="cx_Oracle";
    local p="${n}-${v}";
    py_dependency -v "${v}" -m "d2697493a40c9d46c9b7c1c210b61671" \
      "${n}" "${n}" "${p}" \
      "http://${sf}/project/cx-oracle/${v}/${p}.tar.gz";
  fi;

  local v="4.1.1";
  local n="PyGreSQL";
  local p="${n}-${v}";
  py_dependency -v "${v}" -m "71d0b8c5a382f635572eb52fee47cd08" -o \
    "${n}" "pgdb" "${p}" \
    "${pypi}/P/${n}/${p}.tgz";

  # Maintenance note: next time the Twisted dependency gets updated, check out
  # twext/patches.py.
  local v="12.3.0";
  local n="Twisted";
  local p="${n}-${v}";
  py_dependency -v 12.2 -m "6e289825f3bf5591cfd670874cc0862d" \
    "${n}" "twisted" "${p}" \
    "${pypi}/T/${n}/${p}.tar.bz2";

  local v="1.5";
  local n="python-dateutil";
  local p="${n}-${v}";
  py_dependency -m "35f3732db3f2cc4afdc68a8533b60a52" \
    "${n}" "dateutil" "${p}" \
    "http://www.labix.org/download/${n}/${p}.tar.gz";

  local v="0.6.1";
  local n="psutil";
  local p="${n}-${v}";
  py_dependency -m "3cfcbfb8525f6e4c70110e44a85e907e" \
    "${n}" "${n}" "${p}" \
    "http://${n}.googlecode.com/files/${p}.tar.gz";

  local v="2.3.13";
  local n="python-ldap";
  local p="${n}-${v}";
  py_dependency -v "${v}" -m "895223d32fa10bbc29aa349bfad59175" \
    "Python-LDAP" "ldap" "${p}" \
    "${pypi}/p/${n}/${p}.tar.gz";

  # XXX actually PyCalendar should be imported in-place.
  py_dependency -fe -i "src" -r 11458 \
    "PyCalendar" "pycalendar" "pycalendar" \
    "${svn_uri_base}/PyCalendar/trunk";

  #
  # Tool dependencies.  The code itself doesn't depend on these, but
  # they are useful to developers.
  #

  local v="0.1.2";
  local n="sqlparse";
  local p="${n}-${v}";
  py_dependency -o -v "${v}" -s "978874e5ebbd78e6d419e8182ce4fb3c30379642" \
    "SQLParse" "${n}" "${p}" \
    "http://python-sqlparse.googlecode.com/files/${p}.tar.gz";

  if type -P pyflakes > /dev/null; then
    using_system "PyFlakes";
  else
    local v="0.6.1";
    local n="pyflakes";
    local p="${n}-${v}";
    py_dependency -o -v "${v}" -m "00debd2280b962e915dfee552a675915" \
      "Pyflakes" "${n}" "${p}" \
      "${pypi}/p/${n}/${p}.tar.gz";
  fi;
 
  py_dependency -o -r HEAD \
    "CalDAVClientLibrary" "caldavclientlibrary" "CalDAVClientLibrary" \
    "${svn_uri_base}/CalDAVClientLibrary/trunk";

  # Can't add "-v 2011g" to args because the version check expects numbers.
  local n="pytz";
  local p="${n}-2011n";
  py_dependency -o -m "75ffdc113a4bcca8096ab953df746391" \
    "${n}" "${n}" "${p}" \
    "${pypi}/p/${n}/${p}.tar.gz";

  local v="2.5";
  local n="pycrypto";
  local p="${n}-${v}";
  py_dependency -o -v "${v}" -m "783e45d4a1a309e03ab378b00f97b291" \
    "PyCrypto" "${n}" "${p}" \
    "http://ftp.dlitz.net/pub/dlitz/crypto/${n}/${p}.tar.gz";

  local v="0.1.2";
  local n="pyasn1";
  local p="${n}-${v}";
  py_dependency -o -v "${v}" -m "a7c67f5880a16a347a4d3ce445862a47" \
    "${n}" "${n}" "${p}" \
    "${pypi}/p/${n}/${p}.tar.gz";

  local v="1.1.6";
  local n="setproctitle";
  local p="${n}-${v}";
  py_dependency -o -v "1.0" -m "1e42e43b440214b971f4b33c21eac369" \
    "${n}" "${n}" "${p}" \
    "${pypi}/s/${n}/${p}.tar.gz";

  local v="0.6";
  local n="cffi";
  local p="${n}-${v}";
  py_dependency -v "0.6" -m "5be33b1ab0247a984d42b27344519337" \
    "${n}" "${n}" "${p}" \
    "${pypi}/c/${n}/${p}.tar.gz";

  local v="2.09.1";
  local n="pycparser";
  local p="${n}-${v}";
  py_dependency -v "0.6" -m "74aa075fc28b7c24a4426574d1ac91e0" \
    "${n}" "${n}" "${p}" \
    "${pypi}/p/${n}/${p}.tar.gz";

  svn_get "CalDAVTester" "${top}/CalDAVTester" \
      "${svn_uri_base}/CalDAVTester/trunk" HEAD;

  local v="3.0.1";
  local n="epydoc";
  local p="${n}-${v}";
  py_dependency -o -m "36407974bd5da2af00bf90ca27feeb44" \
    "Epydoc" "${n}" "${p}" \
    "https://pypi.python.org/packages/source/e/${n}/${p}.tar.gz";

  local v="0.10.0";
  local n="Nevow";
  local p="${n}-${v}";
  py_dependency -o -m "66dda2ad88f42dea05911add15f4d1b2" \
    "${n}" "${n}" "${p}" \
    "https://pypi.python.org/packages/source/N/${n}/${p}.tar.gz";

  local v="0.4";
  local n="pydoctor";
  local p="${n}-${v}";
  py_dependency -o -m "b7564e12b5d35d4cb529a2c220b25d3a" \
    "${n}" "${n}" "${p}" \
    "https://pypi.python.org/packages/source/p/${n}/${p}.tar.gz";

  if "${do_setup}"; then
    cd "${caldav}";
    echo "Building our own extension modules...";
    "${python}" setup.py build_ext --inplace;
  fi;
}

# Actually do the initialization, once all functions are defined.
init_build;
