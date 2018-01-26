#!/usr/bin/env python

# Contributors Listed Below - COPYRIGHT 2016
# [+] International Business Machines Corp.
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

import obmc.mapper
import obmc.utils.dtree
import obmc.utils.pathtree
import dbus
import os
import subprocess
import tempfile


def transform(path, o):
    if not o:
        # discard empty path elements
        # and empty objects
        return None

    for name, value in o.items():
        if any(value == x for x in ['', []]):
            # discard empty properties
            del o[name]
            continue

        if any(name == x for x in ['endpoints']):
            # discard associations
            del o[name]
            continue

        # fix up properties/values to follow DT conventions
        rename = name
        revalue = value

        # convert to lower case
        rename = rename.lower()

        # force name to be a string
        if rename == 'name' and isinstance(revalue, list):
            revalue = ''.join([str(x) for x in revalue])

        # make is-fru a real boolean
        if rename == 'is_fru':
            revalue = 'True' if revalue == 1 else 'False'

        # swap underscore/space for dash in property name
        rename = rename.replace('_', '-')
        rename = rename.replace(' ', '-')

        # strip trailing whitespace from strings
        rename = rename.rstrip()
        if isinstance(revalue, basestring):
            revalue = revalue.rstrip()

        # update if any changes were made
        if name != rename or value != revalue:
            o[rename] = revalue
            del o[name]

    path_elements = filter(bool, path.split('/'))
    path = "/%s" % '/'.join(path_elements[4:-1])
    # inject the location property
    o['location'] = "Physical:%s" % path

    # flatten the tree into a single 'bmc/inventory' node
    path = "/%s" % '/'.join(['bmc', 'inventory', path_elements[-1]])
    return path, o


if __name__ == '__main__':
    bus = dbus.SystemBus()
    objs = obmc.utils.pathtree.PathTree()

    mapper = obmc.mapper.Mapper(bus)
    for path, props in \
            mapper.enumerate_subtree(
                path='/org/openbmc/inventory/system').iteritems():
        item = transform(path, props)
        if item:
            objs[item[0]] = item[1]

    rpipe, wpipe = os.pipe()
    rpipe = os.fdopen(rpipe, 'r')
    wpipe = os.fdopen(wpipe, 'a')

    wpipe.write('/dts-v1/;')
    obmc.utils.dtree.dts_encode(objs.dumpd(), wpipe)
    wpipe.close()
    h, tmpfile = tempfile.mkstemp()
    try:
        wfile = os.fdopen(h, 'w')
        subprocess.call(
            ['dtc', '-O', 'dtb'],
            stdin=rpipe,
            stdout=wfile)
        rpipe.close()
        wfile.close()

        print "Uploading inventory to PNOR in dtb format..."
        subprocess.call(['pflash', '-f', '-e', '-p', tmpfile, '-P', 'BMC_INV'])
    except Exception:
        os.remove(tmpfile)
        raise

    os.remove(tmpfile)
