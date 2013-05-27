# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright (C) 2013 University of Toronto
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

''' The flowvisor extension extends the current network object model and adds a
field representing controller information. '''

from quantum.api import extensions
from quantum.api.v2 import attributes as attr
from quantum.openstack.common import log as logging


LOG = logging.getLogger(__name__)


# The default openflow port.
DEFAULT_OF_PORT = 6666

# Controller attribute key.
CONTROLLER = 'controller'
# Attribute Map.
EXTENDED_ATTRIBUTES_2_0 = {
    'networks': {
        CONTROLLER: {'allow_post': True,
                     'allow_put': True,
                     'validate': {'type:controller_address': None},
                     'is_visible': True,
                     'default': None},
    }
}

def get_ip_and_port(url):
    ''' Converts a flowvisor controller url into a ip and port tuple. '''
    if not url:  # If it is none or empty.
        return None

    parts = url.split(':')
    return (parts[0], DEFAULT_OF_PORT) if len(parts) == 1 else (parts[0],
                                                                int(parts[1]))

def to_controller_url(data):
    ''' Converts an ip and port tuple into string. '''
    if not data or len(data) != 2:
        return None

    return '%s:%d' % data

def _validate_controller_address_or_none(data, valid_values=None):
    ''' Validates a controller address which should be in the form of ip:port.
    '''
    if data is None:
        return None

    parsed = get_ip_and_port(data)

    return attr.validators['type:ip_address'](parsed[0]) or \
           attr.validators['type:non_negative'](parsed[1])

attr.validators['type:controller_address'] = \
        _validate_controller_address_or_none

class Flowvisor(extensions.ExtensionDescriptor):
    ''' Flowvisor quantum extension. '''

    @classmethod
    def get_name(cls):
        return "Quantum Flowvisor Extension"

    @classmethod
    def get_alias(cls):
        return "flowvisor"

    @classmethod
    def get_description(cls):
        return "Extended controller information for the flowvisor plugin."

    @classmethod
    def get_namespace(cls):
        return "http://docs.openstack.org/ext/quantum/flowvisor/api/v1.0"

    @classmethod
    def get_updated(cls):
        return "2013-06-01T10:00:00-00:00"

    def get_extended_resources(self, version):
        if version == "2.0":
            return EXTENDED_ATTRIBUTES_2_0
        else:
            return {}

