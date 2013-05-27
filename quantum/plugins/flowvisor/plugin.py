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

'''
The Quantum plugin for flowvisor.
'''

from oslo.config import cfg

from quantum.common import exceptions
from quantum.common import rpc as quantum_rpc
from quantum.common import topics
from quantum.db import db_base_plugin_v2
from quantum.db import dhcp_rpc_base
from quantum.db import extraroute_db
from quantum.db import l3_db
from quantum.db import l3_gwmode_db
from quantum.db import l3_rpc_base
from quantum.plugins.flowvisor.db import flowvisordb
from quantum.plugins.flowvisor.extensions import flowvisor as fvext
from quantum.extensions import l3
from quantum.extensions import portbindings
from quantum.openstack.common import log as logging
from quantum.openstack.common import rpc
from quantum.openstack.common.rpc import proxy
from quantum.plugins.flowvisor.client import FlowvisorClient


LOG = logging.getLogger(__name__)

FLOWVISOR_OPTS = [
    cfg.StrOpt('jrpc_url', default='https://localhost:8081',
               help=_('The json rpc url for flowvisor.')),
    cfg.StrOpt('username', default='fvadmin',
               help=_('Flowvisor admin username.')),
    cfg.StrOpt('password', default='',
               help=_('Flowvisor admin password')),
]

FULL_PERM = 7

cfg.CONF.register_opts(FLOWVISOR_OPTS, 'FLOWVISOR')


class FlowvisorRpcCallback(dhcp_rpc_base.DhcpRpcCallbackMixin,
                      l3_rpc_base.L3RpcCallbackMixin):
    RPC_API_VERSION = '1.1'

    def __init__(self):
        super(FlowvisorRpcCallback, self).__init__()

    def create_rpc_dispatcher(self):
        return quantum_rpc.PluginRpcDispatcher([self])

class AgentNotifierApi(proxy.RpcProxy):
    BASE_RPC_API_VERSION = '1.0'

    def __init__(self, topic):
        super(AgentNotifierApi, self).__init__(
            topic=topic, default_version=self.BASE_RPC_API_VERSION)
        self.topic_port_update = topics.get_topic_name(topic,
                                                       topics.PORT,
                                                       topics.UPDATE)

    def port_update(self, context, port):
        self.fanout_cast(context,
                         self.make_msg('port_update', port=port),
                         topic=self.topic_port_update)


class FlowvisorPluginV2(db_base_plugin_v2.QuantumDbPluginV2,
                        extraroute_db.ExtraRoute_db_mixin,
                        flowvisordb.FlowvisorDbMixin,
                        l3_gwmode_db.L3_NAT_db_mixin):
    ''' The quantum plugin for flowvisor. '''

    supported_extension_aliases = ['binding',
                                   'ext-gw-mode',
                                   'extraroute',
                                   'flowvisor',
                                   'router']

    def __init__(self):
        super(FlowvisorPluginV2, self).__init__()
        # Flowvisor client init.
        self._client = FlowvisorClient(cfg.CONF.FLOWVISOR.jrpc_url,
                                       cfg.CONF.FLOWVISOR.username,
                                       cfg.CONF.FLOWVISOR.password)

        # DHCP inits.
        self.conn = rpc.create_connection(new=True)
        self.notifier = AgentNotifierApi(topics.AGENT)
        self.callbacks = FlowvisorRpcCallback()
        self.dispatcher = self.callbacks.create_rpc_dispatcher()
        self.conn.create_consumer(topics.PLUGIN, self.dispatcher, fanout=False)
        self.conn.consume_in_thread()

    def create_network(self, context, network):
        #tenant_id = self._get_tenant_id_for_create(context, network['network'])
        session = context.session
        with session.begin(subtransactions=True):
            # create network in DB
            new_net = super(FlowvisorPluginV2, self).create_network(context,
                                                                    network)
            net_id = new_net['id']
            self._process_l3_create(context, network['network'], net_id)
            self._extend_network_dict_l3(context, new_net)

            self._create_or_update_ctrl_info(context, network['network'],
                                             net_id)
            self._extend_network_dict_fv(context, new_net)
            self._add_or_update_slice(context, new_net)

        return new_net

    def update_network(self, context, net_id, network):
        session = context.session
        with session.begin(subtransactions=True):
            orig_net = super(FlowvisorPluginV2, self).get_network(context,
                                                                  net_id)
            new_net = super(FlowvisorPluginV2, self).update_network(context,
                                                                    net_id,
                                                                    network)
            self._process_l3_update(context, network['network'], net_id)
            self._extend_network_dict_l3(context, new_net)

            self._create_or_update_ctrl_info(context, network['network'],
                                             net_id)
            self._extend_network_dict_fv(context, new_net)
            self._add_or_update_slice(context, new_net)

        return new_net

    def delete_network(self, context, net_id):
        # Validate args
        orig_net = super(FlowvisorPluginV2, self).get_network(context, net_id)
        tenant_id = orig_net['tenant_id']

        filter = {'network_id': [net_id]}
        ports = self.get_ports(context, filters=filter)

        # check if there are any tenant owned ports in-use
        auto_delete_port_owners = db_base_plugin_v2.AUTO_DELETE_PORT_OWNERS
        only_auto_del = all(p['device_owner'] in auto_delete_port_owners
                            for p in ports)

        if not only_auto_del:
            raise exceptions.NetworkInUse(net_id=net_id)

        session = context.session
        with session.begin(subtransactions=True):
            ret = super(FlowvisorPluginV2, self).delete_network(context, net_id)
            slice_name, controller_info, controller_email = \
                    self._get_slice_info(context, orig_net)
            self._delete_ctrl_info(context, net_id)
            self._client.remove_slice(slice_name)

        return ret

    def get_network(self, context, net_id, fields=None):
        session = context.session
        with session.begin(subtransactions=True):
            net = super(FlowvisorPluginV2, self).get_network(context, net_id,
                                                             None)
            self._extend_network_dict_l3(context, net)
            self._extend_network_dict_fv(context, net)

        return self._fields(net, fields)

    def get_networks(self, context, filters=None,
                     fields=None, sorts=None, limit=None, marker=None,
                     page_reverse=False):
        session = context.session
        with session.begin(subtransactions=True):
            nets = super(FlowvisorPluginV2, self).get_networks(
                    context, filters, None, sorts, limit, marker, page_reverse)
            for net in nets:
                self._extend_network_dict_l3(context, net)
                self._extend_network_dict_fv(context, net)

        return [self._fields(net, fields) for net in nets]

    def create_port(self, context, port):
        # Update DB
        port['port']['admin_state_up'] = False
        new_port = super(FlowvisorPluginV2, self).create_port(context, port)
        net = super(FlowvisorPluginV2, self).get_network(context,
                                                         new_port['network_id'])

        #if new_port['device_owner'] == 'network:dhcp':
            #destination = METADATA_SERVER_IP + '/32'
            #self._add_host_route(context, destination, new_port)

        # Set port state up and return that port
        port_update = {'port': {'admin_state_up': True}}
        new_port = super(FlowvisorPluginV2, self).update_port(context,
                                                              new_port['id'],
                                                              port_update)

        flowspace_name, match, slice_name, slice_permission = \
                self._get_dst_flowspace_info(new_port)
        self._add_flow_space(flowspace_name, match, slice_name,
                             slice_permission)

        flowspace_name, match, slice_name, slice_permission = \
                self._get_src_flowspace_info(new_port)
        self._add_flow_space(flowspace_name, match, slice_name,
                             slice_permission)

        return self._extend_port_dict_binding(context, new_port)

    def _extend_port_dict_binding(self, context, port):
        ''' Extends a port binding. '''
        port[portbindings.VIF_TYPE] = portbindings.VIF_TYPE_OVS
        port[portbindings.CAPABILITIES] = {
            portbindings.CAP_PORT_FILTER: False}
        return port

    def get_port(self, context, port_id, fields=None):
        with context.session.begin(subtransactions=True):
            port = super(FlowvisorPluginV2, self).get_port(context, port_id,
                                                           fields)
            self._extend_port_dict_binding(context, port)
        return self._fields(port, fields)

    def get_ports(self, context, filters=None, fields=None):
        with context.session.begin(subtransactions=True):
            ports = super(FlowvisorPluginV2, self).get_ports(context, filters,
                                                             fields)
            for port in ports:
                self._extend_port_dict_binding(context, port)
        return [self._fields(port, fields) for port in ports]

    def update_port(self, context, port_id, port):
        # Validate Args
        orig_port = super(FlowvisorPluginV2, self).get_port(context, port_id)

        # Update DB
        new_port = super(FlowvisorPluginV2, self).update_port(context,
                                                              port_id, port)

        if orig_port['admin_state_up'] != new_port['admin_state_up']:
            self.notifier.port_update(context, new_port)

        # return new_port
        return self._extend_port_dict_binding(context, new_port)


    def delete_port(self, context, port_id, l3_port_check=True):
        # if needed, check to see if this is a port owned by
        # and l3-router.  If so, we should prevent deletion.
        if l3_port_check:
            self.prevent_l3_port_deletion(context, port_id)

        self.disassociate_floatingips(context, port_id)

        orig_port = super(FlowvisorPluginV2, self).get_port(context, port_id)

        super(FlowvisorPluginV2, self).delete_port(context, port_id)

        flowspace_name, match, slice_name, slice_permission = \
                self._get_dst_flowspace_info(orig_port)
        self._remove_flow_space(flowspace_name)

        flowspace_name, match, slice_name, slice_permission = \
                self._get_src_flowspace_info(orig_port)
        self._remove_flow_space(flowspace_name)


    def create_subnet(self, context, subnet):
        # create subnet in DB
        new_subnet = super(FlowvisorPluginV2, self).create_subnet(context,
                                                                  subnet)
        return new_subnet

    def update_subnet(self, context, subnet_id, subnet):
        orig_subnet = super(FlowvisorPluginV2, self)._get_subnet(context,
                                                                 subnet_id)

        # update subnet in DB
        new_subnet = super(FlowvisorPluginV2, self).update_subnet(context,
                                                                  subnet_id,
                                                                  subnet)
        return new_subnet

    def delete_subnet(self, context, subnet_id):
        orig_subnet = super(FlowvisorPluginV2, self).get_subnet(context,
                                                                subnet_id)
        # delete subnet in DB
        super(FlowvisorPluginV2, self).delete_subnet(context, subnet_id)

    def _get_slice_info(self, context, net):
        ''' Returns the controller info for a network. The return value is a
        tuple of (slice_name, controller openflow url, contact info)
        '''
        net_id = net['id']
        ctrl = fvext.get_ip_and_port(net.get(fvext.CONTROLLER)) or (net_id, 0)
        return (net_id, ctrl, 'of@ofc')

    def _add_or_update_slice(self, context, net):
        ''' Adds or update a flowvisor slice. '''
        slice_name, ctrl_info, admin_email = self._get_slice_info(context,
                                                                  net)
        the_slice = self._client.get_slice(slice_name)
        if not the_slice:
            self._client.add_slice(slice_name, ctrl_info[0], ctrl_info[1],
                                   admin_email)
        else:
            self._client.update_slice(slice_name, ctrl_info[0], ctrl_info[1],
                                      admin_email)

    def _get_src_flowspace_info(self, port):
        ''' Generates the flow space for network -> external direction. '''
        return ('src' + port['mac_address'], {'dl_src': port['mac_address']},
                port['network_id'], FULL_PERM)

    def _get_dst_flowspace_info(self, port):
        ''' Generates the flow space for external -> network direction. '''
        return ('dst' + port['mac_address'], {'dl_dst': port['mac_address']},
                port['network_id'], FULL_PERM)

    def _add_flow_space(self, name, match, slice_name, slice_permission):
        ''' Adds a flow space to flowvisor. '''
        self._client.add_flowspace(name, match=match,
                                   slice_permissions=[(slice_name,
                                                       slice_permission)])

    def _remove_flow_space(self, name):
        ''' Deletes a flow space to flowvisor. '''
        self._client.remove_flowspace(name)

