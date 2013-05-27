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

''' Flowvisor plugin db functionality. '''

import sqlalchemy as sa

from quantum.db import model_base
from quantum.plugins.flowvisor.extensions import flowvisor as fvext
from quantum.openstack.common import log as logging


LOG = logging.getLogger(__name__)


class NetworkControllerInfo(model_base.BASEV2):
    ''' The model object for storing controller info for each network. '''
    network_id = sa.Column(sa.String(36),
                           sa.ForeignKey("networks.id", ondelete="CASCADE"),
                           nullable=False,
                           primary_key=True)
    controller_host = sa.Column(sa.String(128), nullable=True)
    controller_port = sa.Column(sa.Integer, nullable=True)

class FlowvisorDbMixin(object):
    ''' Flowvisor db mixin. '''

    def _extend_network_dict_fv(self, context, network):
        ''' Adds controller information to the network object. '''
        if network.get(fvext.CONTROLLER) is not None:
            return

        network[fvext.CONTROLLER] = fvext.to_controller_url(
                self._get_ctrl_info(context, network['id']))

    def __do_delete_ctrl_info(self, context, network_id):
        ''' Deletes a controller info. '''
        context.session.query(NetworkControllerInfo).filter_by(
                network_id=network_id).delete()

    def __do_add_ctrl_info(self, context, network_id, controller):
        ''' Adds a controller info. '''
        ctrl_info = NetworkControllerInfo(network_id=network_id,
                                          controller_host=controller[0],
                                          controller_port=controller[1])
        context.session.add(ctrl_info)


    def _create_or_update_ctrl_info(self, context, network, network_id):
        ''' Flowvisor functionality called upon create_network or
            update_network. '''
        controller = network.get(fvext.CONTROLLER)
        if controller is None:
            return

        with context.session.begin(subtransactions=True):
            self.__do_delete_ctrl_info(context, network_id)
            self.__do_add_ctrl_info(context, network_id,
                                    fvext.get_ip_and_port(controller))

    def _delete_ctrl_info(self, context, network_id):
        ''' Flowvisor functionality called upon delete_network. '''
        with context.session.begin(subtransactions=True):
            self.__do_delete_ctrl_info(context, network_id)

    def _get_ctrl_info(self, context, network_id):
        ''' Flowvisor functionality called upon get_network. '''
        session = context.session
        with session.begin(subtransactions=True):
            ctrl =  session.query(NetworkControllerInfo.controller_host,
                                  NetworkControllerInfo.controller_port) \
                            .filter_by(network_id=network_id).first()
            return ctrl if ctrl else None

