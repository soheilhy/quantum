# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright (C) 2013, University of Toronto
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

# Partly borrowed from flowvisor's fvctl.
# Copyright (c) 2012-2013  The Board of Trustees of The Leland Stanford Junior
# University

import json
import urllib2

from quantum.openstack.common import log as logging

LOG = logging.getLogger(__name__)

class FlowvisorClient(object):
    ''' Flowvisor json rpc client. Created based on Flowvisor's fvctl. '''

    def __init__(self, url, username, password):
        self._url = url
        self._username = username
        self._password = password
        LOG.debug(_('Flowvisor connected to %s with %s:%s' % (url, username,
                                                              password)))

    def send_command(self, cmd, data=None):
        ''' Sends a json rpc command. '''
        LOG.debug(_('Flowvisor connected to %s - %s:%s - %s' % (self._url,
                                                                self._username,
                                                                self._password,
                                                                cmd)))

        try:
            passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
            passman.add_password(None, self._url, self._username,
                                 self._password)
            authhandler = urllib2.HTTPBasicAuthHandler(passman)
            opener = urllib2.build_opener(authhandler)

            req = self._build_request(data, cmd)
            stream = opener.open(req)
            return self._parse_response(stream.read())
        except urllib2.HTTPError, exp:
            if exp.code == 401:
                LOG.error(_('Authentication failed: invalid password'))
            elif exp.code == 504:
                LOG.error(_('HTTP Error 504: Gateway timeout'))
            else:
                LOG.error(exp)
            return None

    def _build_request(self, data, cmd):
        ''' Builds a request to the url. '''
        rpc_header = { "id" : "qclient", "method" : cmd, "jsonrpc" : "2.0" }
        http_options = {"Content-Type" : "application/json"}
        if data is not None:
            rpc_header['params'] = data
        return urllib2.Request(self._url, json.dumps(rpc_header), http_options)

    def _parse_response(self, data):
        ''' Parses a json rpc response. '''
        j = json.loads(data)
        if 'error' in j:
            LOG.error("%s -> %s" % (get_error(j['error']['code']),
                                              j['error']['message']))
            return []
        return j['result']

    def list_slices(self):
        ''' Returns the list of flowvisor slices in the form of:
        [{
            'slice-name': ...,
            'admin-status': ...
        }, ...]
        '''
        return self.send_command('list-slices')

    def add_slice(self, slice_name, controller_host, controller_port,
                  admin_contact):
        ''' Adds a slice to flowvisor. '''
        req_params = {
            'slice-name': slice_name,
            'controller-url': 'tcp:%s:%d' % (controller_host, controller_port),
            'admin-contact': admin_contact,
            'password': self._password,
            'drop-policy': 'exact',
            'recv-lldp': False,
            'rate-limit': -1,
            'flowmod-limit': -1,
            'admin-status': True,
            }
        return self.send_command('add-slice', req_params)

    def update_slice(self, slice_name, controller_host, controller_port,
                     admin_contact):
        ''' Updates a slice. '''
        req_params = {
            'slice-name': slice_name,
            'controller-host': controller_host,
            'controller-port': controller_port,
            'admin-contact': admin_contact,
            'password': self._password,
            'drop-policy': 'exact',
            'recv-lldp': False,
            'rate-limit': -1,
            'flowmod-limit': -1,
            'admin-status': True,
            }
        return self.send_command('update-slice', req_params)

    def remove_slice(self, slice_name):
        ''' Removes a slice. '''
        return self.send_command('remove-slice', {'slice-name': slice_name })

    def get_slice(self, slice_name):
        ''' Retrieves a slice. '''
        return self.send_command('list-slice-info', {'slice-name': slice_name})

    def list_flowspaces(self, slice_name=None, show_disabled=None):
        ''' List flow spaces in a slice. '''
        req_params = {}
        if slice_name is not None:
            req_params['slice-name'] = slice_name
        if show_disabled is not None:
            req_params['show-disabled'] = show_disabled

        return self.send_command('list-flowspace', req_params)

    def add_flowspace(self, name, dpid='all', match={}, priority=10,  # pylint: disable=R0201,C0301
                      slice_permissions=[]):
        ''' Adds a flowspace.
        slice_permissions is a list of tuples (slice, permission). '''
        req_params = [{
            'name': name,
            'dpid': dpid,
            'match': match,
            'priority': priority,
            'slice-action': [{
                'slice-name': slice_name,
                'permission': permission
                } for slice_name, permission in slice_permissions]
            }]
        return self.send_command('add-flowspace', req_params)

    def update_flowspace(self, name, dpid=None, match=None, priority=None,  # pylint: disable=R0913,C0301
                         slice_permissions=None):
        ''' Updates a flowspace. '''
        req_params = { 'name': name }

        if dpid is not None:
            req_params['dpid'] = dpid

        if match is not None:
            req_params['match'] = match

        if priority is not None:
            req_params['priority'] = priority

        if slice_permissions is not None:
            req_params['slice-action'] = [{
                'slice-name': slice_name,
                'permission': permission
                } for slice_name, permission in slice_permissions]

        print req_params

        return self.send_command('update-flowspace', [req_params])

    def remove_flowspace(self, name):
        ''' Removes a flow space. '''
        req_params = [name]
        return self.send_command('remove-flowspace', req_params)


def get_error(code):
    ''' Returns the error description. '''
    try:
        return ERRORS[code]
    except KeyError:
        return "Unknown Error"

ERRORS = {
    -32700 : "Parse Error",
    -32600 : "Invalid Request",
    -32601 : "Method not found",
    -32602 : "Invalid Params",
    -32603 : "Internal Error"
}

