# -*- sh-basic-offset: 2 -*-

##
# Copyright (c) 2005-2011 Apple Inc. All rights reserved.
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

  if [ -z "${CALENDARSERVER_CACHE_DEPS-}" ]; then
    cache_deps="${wd}/.dependencies";
  else
    cache_deps="${CALENDARSERVER_CACHE_DEPS}";
  fi;

  if [ -z "${caldavd_wrapper_command:-}" ]; then
    if [ "$(uname -s)" == "Darwin" ] && [ "$(uname -r | cut -d . -f 1)" -ge 9 ]; then
      caldavd_wrapper_command="launchctl bsexec /";
    else
      caldavd_wrapper_command="";
    fi;
  fi;

      top="$(cd "${caldav}/.." && pwd -L)";
  patches="${caldav}/lib-patches";

  # Find a command that can hash up a string for us
  if type -t openssl > /dev/null; then
    hash="md5";
    hash () { openssl dgst -md5 "$@"; }
  elif type -t md5 > /dev/null; then
    hash="md5";
    hash () { md5 "$@"; }
  elif type -t md5sum > /dev/null; then
    hash="md5";
    hash () { md5sum "$@"; }
  elif type -t cksum > /dev/null; then
    hash="hash";
    hash () { cksum "$@" | cut -f 1 -d " "; }
  elif type -t sum > /dev/null; then
    hash="hash";
    hash () { sum "$@" | cut -f 1 -d " "; }
  else
    hash="";
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

  local md5="";

  OPTIND=1;
  while getopts "m:" option; do
    case "${option}" in
      'm') md5="${OPTARG}"; ;;
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

        if [ "${hash}" == "md5" ]; then
          local sum="$(hash "${file}" | perl -pe 's|^.*([0-9a-f]{32}).*$|\1|')";
          if [ -n "${md5}" ]; then
            echo "Checking MD5 sum for ${name}...";
            if [ "${md5}" != "${sum}" ]; then
              echo "ERROR: MD5 sum for downloaded file is wrong: ${sum} != ${md5}";
              return 1;
            fi;
          else
            echo "MD5 sum for ${name} is ${sum}";
          fi;
        fi;
      }

      if [ ! -f "${cache_file}" ]; then
        echo "Downloading ${name}...";

        local pkg_host="static.calendarserver.org";
        local pkg_path="/pkg";

        #
        # Try getting a copy from calendarserver.org.
        #
        local tmp="$(mktemp "/tmp/${cache_basename}.XXXXX")";
        curl -L "http://${pkg_host}${pkg_path}/${cache_basename}" -o "${tmp}";
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

          if egrep '^${pkg_host} ' "${HOME}/.ssh/known_hosts" > /dev/null 2>&1; then
            echo "Copying cache file up to ${pkg_host}.";
            if ! scp "${tmp}" "${pkg_host}:/www/hosts/${pkg_host}${pkg_path}/${cache_basename}"; then
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

    if [ "${revision}" != "HEAD" ] && [ -n "${cache_deps}" ] \
        && [ -n "${hash}" ]; then
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
    echo "Building ${name}...";
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
  local   f_hash="";      # Checksum

  OPTIND=1;
  while getopts "ofi:er:v:m:" option; do
    case "${option}" in
      'o') optional="true"; ;;
      'f') override="true"; ;;
      'e') skip_egg="true"; ;;
      'r') get_type="svn"; revision="${OPTARG}"; ;;
      'v')  version="-v ${OPTARG}"; ;;
      'm')   f_hash="-m ${OPTARG}"; ;;
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

  if ! "${print_path}"; then
    echo "";
  fi;
  if "${override}" || ! py_have_module ${version} "${module}"; then
    "${get_type}_get" ${f_hash} "${name}" "${srcdir}" "${get_uri}" "${revision}"
    if [ -n "${inplace}" ]; then
      if "${do_setup}" && "${override}" && ! "${skip_egg}"; then
        echo;
        if py_have_module setuptools; then
          echo "Building ${name}... [overrides system, building egg-info only]";
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
    if ! "${print_path}"; then
      echo "Using system version of ${name}.";
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
      ncpu="${cpu##hw.ncpu: }";
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
  while getopts "m:" option; do
    case "${option}" in
      'm') f_hash="-m ${OPTARG}"; ;;
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

  if "${do_setup}" && (
      "${force_setup}" || "${do_bundle}" || [ ! -d "${dstroot}" ]); then
    echo "Building ${name}...";
    cd "${srcdir}";
    ./configure --prefix="${dstroot}" "$@";
    jmake;
    jmake install;
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
    local pyfn="Python-2.7.1";
    c_dependency -m "aa27bc25725137ba155910bd8e5ddc4f" \
        "Python" "${pyfn}" \
        "http://www.python.org/ftp/python/2.7.1/${pyfn}.tar.bz2" \
        --enable-shared;
    # Be sure to use the Python we just built.
    export PYTHON="$(type -p python)";
    init_py;
  fi;

  if ! type -P memcached > /dev/null; then
    local le="libevent-2.0.17-stable";
    local mc="memcached-1.4.13";
    c_dependency -m "dad64aaaaff16b5fbec25160c06fee9a" \
      "libevent" "${le}" \
      "https://github.com/downloads/libevent/libevent/${le}.tar.gz";
    c_dependency -m "6d18c6d25da945442fcc1187b3b63b7f" \
      "memcached" "${mc}" \
      "http://memcached.googlecode.com/files/${mc}.tar.gz";
  fi;

  if ! type -P postgres > /dev/null; then
    local pgv="9.1.2";
    local pg="postgresql-${pgv}";

    if type -P dtrace > /dev/null; then
      local enable_dtrace="--enable-dtrace";
    else
      local enable_dtrace="";
    fi;

    c_dependency -m "fe01293f96e04da9879840b1996a3d2c" \
      "PostgreSQL" "${pg}" \
      "ftp://ftp5.us.postgresql.org/pub/PostgreSQL/source/v${pgv}/${pg}.tar.gz" \
      --with-python ${enable_dtrace};
    :;
  fi;

  if ! find_header ldap.h; then
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

  local zv="3.3.0";
  local zi="zope.interface-${zv}";
  py_dependency -m "93668855e37b4691c5c956665c33392c" \
    "Zope Interface" "zope.interface" "${zi}" \
    "http://www.zope.org/Products/ZopeInterface/${zv}/${zi}.tar.gz";

  local po="pyOpenSSL-0.13";
  py_dependency -v 0.13 -m "767bca18a71178ca353dff9e10941929" \
    "PyOpenSSL" "OpenSSL" "${po}" \
    "http://pypi.python.org/packages/source/p/pyOpenSSL/${po}.tar.gz";

  if type -P krb5-config > /dev/null; then
    py_dependency -r 8679 \
      "PyKerberos" "kerberos" "PyKerberos" \
      "${svn_uri_base}/PyKerberos/trunk";
  fi;

  if [ "$(uname -s)" == "Darwin" ]; then
    py_dependency -r 6656 \
      "PyOpenDirectory" "opendirectory" "PyOpenDirectory" \
      "${svn_uri_base}/PyOpenDirectory/trunk";
  fi;

  py_dependency -v 0.5 -r 1038 \
    "xattr" "xattr" "xattr" \
    "http://svn.red-bean.com/bob/xattr/releases/xattr-0.6.1/";

  if [ -n "${ORACLE_HOME:-}" ]; then
      local cx="cx_Oracle-5.1";
      py_dependency -v 5.1 -m "d2697493a40c9d46c9b7c1c210b61671" \
          "cx_Oracle" "cx_Oracle" "${cx}" \
          "http://${sf}/project/cx-oracle/5.1/${cx}.tar.gz";
  fi;

  local pg="PyGreSQL-4.0";
  py_dependency -v 4.0 -m "1aca50e59ff4cc56abe9452a9a49c5ff" -o \
    "PyGreSQL" "pgdb" "${pg}" \
    "${pypi}/P/PyGreSQL/${pg}.tar.gz";

  py_dependency -v 12 -r HEAD \
    "Twisted" "twisted" "Twisted" \
    "svn://svn.twistedmatrix.com/svn/Twisted/tags/releases/twisted-12.0.0";

  local du="python-dateutil-1.5";
  py_dependency -m "35f3732db3f2cc4afdc68a8533b60a52" \
    "dateutil" "dateutil" "${du}" \
    "http://www.labix.org/download/python-dateutil/${du}.tar.gz";

  local lv="2.3.13";
  local ld="python-ldap-${lv}";
  py_dependency -v "${lv}" -m "895223d32fa10bbc29aa349bfad59175" \
    "python-ldap" "ldap" "${ld}" \
    "${pypi}/p/python-ldap/${ld}.tar.gz";

  # XXX actually PyCalendar should be imported in-place.
  py_dependency -fe -i "src" -r 190 \
    "pycalendar" "pycalendar" "pycalendar" \
    "http://svn.mulberrymail.com/repos/PyCalendar/branches/server";

  #
  # Tool dependencies.  The code itself doesn't depend on these, but
  # they are useful to developers.
  #

  local sv="0.1.2";
  local sq="sqlparse-${sv}";
  py_dependency -o -v "${sv}" -m "aa9852ad81822723adcd9f96838de14e" \
    "SQLParse" "sqlparse" "${sq}" \
    "http://python-sqlparse.googlecode.com/files/${sq}.tar.gz";

  local fv="0.5.0";
  local fl="pyflakes-${fv}";
  py_dependency -o -v "${fv}" -m "568dab27c42e5822787aa8a603898672" \
    "Pyflakes" "pyflakes" "${fl}" \
    "${pypi}/p/pyflakes/${fl}.tar.gz";
 
  py_dependency -o -r HEAD \
    "CalDAVClientLibrary" "caldavclientlibrary" "CalDAVClientLibrary" \
    "${svn_uri_base}/CalDAVClientLibrary/trunk";

  # Can't add "-v 2011g" to args because the version check expects numbers.
  local tz="pytz-2011n";
  py_dependency -o -m "75ffdc113a4bcca8096ab953df746391" \
    "pytz" "pytz" "${tz}" \
    "http://pypi.python.org/packages/source/p/pytz/${tz}.tar.gz";

  local pv="2.5";
  local pc="pycrypto-${pv}";
  py_dependency -o -v "${pv}" -m "783e45d4a1a309e03ab378b00f97b291" \
    "PyCrypto" "pycrypto" "${pc}" \
    "http://ftp.dlitz.net/pub/dlitz/crypto/pycrypto/${pc}.tar.gz";

  local v="0.1.2";
  local p="pyasn1-${v}";
  py_dependency -o -v "${v}" -m "a7c67f5880a16a347a4d3ce445862a47" \
    "pyasn1" "pyasn1" "${p}" \
    "http://pypi.python.org/packages/source/p/pyasn1/pyasn1-0.1.2.tar.gz";

  svn_get "CalDAVTester" "${top}/CalDAVTester" \
      "${svn_uri_base}/CalDAVTester/trunk" HEAD;

  local pd="pydoctor-0.3";
  py_dependency -o -m "b000aa1fb458fe25952dadf26049ae68" \
    "pydoctor" "pydoctor" "${pd}" \
    "http://launchpadlibrarian.net/42323121/${pd}.tar.gz";

  if "${do_setup}"; then
    cd "${caldav}";
    echo "Building our own extension modules...";
    "${python}" setup.py build_ext --inplace;
  fi;
}

# Actually do the initialization, once all functions are defined.
init_build;
