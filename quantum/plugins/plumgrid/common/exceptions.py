# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 PLUMgrid, Inc. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Edgar Magana, emagana@plumgrid.com, PLUMgrid, Inc.


"""Quantum PLUMgrid Plugin exceptions"""

from quantum.common import exceptions as base_exec


class PLUMgridException(base_exec.QuantumException):
    message = _("An unexpected error occurred in the PLUMgrid Plugin: "
                "%(err_msg)s")


class PLUMgridConnectionFailed(PLUMgridException):
    message = _("Connection failed with PLUMgrid NOS: %(err_msg)s")
