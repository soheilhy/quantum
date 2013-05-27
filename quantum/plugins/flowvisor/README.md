Introduction
============
FlowVisor is a special purpose controller that acts as a proxy between
network switches and multiple controllers. FlowVisor splits the network
into different slices each controlled by a single OpenFlow controller. A
slice is defined as a combination of flow spaces each representing a flow match
(i.e., switch ports, MAC addresses, IP addresses, etc.). FlowVisor enforces
isolation among slices.
 
This plugin integrates Quantum and FlowVisor and enables OpenStack tenants to
use their own OpenFlow controller for their virtual networks. FlowVisor
guarantees isolation between different controllers.

Design Overview
===============
Since we need to have an OpenFlow controller per Quantum network, we
design the plugin to create a slice for each network. When a port is
created and attached to a network, we create two flow-spaces based on the
port's mac address: One for packets from the port, and one for the
packets to the port. This way all flows from and to the network are sent
to the controller. Note that inter-network communication would have to
go through the gateway, so there would be no conflict among controllers.

API Extension
=============
To embed controller connection info in the API, we extend the 'network'
object and add a 'controller' field to it. The 'controller' field simply
contains the host name or ip address of the controller along with an
optional port. These are some valid entries:

* 10.2.2.2
* somehost:6666
* 10.0.2.2:6667

Flow
====
This is an example data flow for creating a network and a port:

    Quantum             FlowVisor Plugin            FlowVisor
      |                       |                         |
      |---- Create Network -->|                         |
      |                       |------ Create Slice ---->|
      |                       |<----- Slice Created ----|
      |<--- Network Created --|                         |
      |                       |                         |
      |---- Create Port ----->|                         |
      |                       |- Create Src FlowSpace ->|
      |                       |<-- FlowSpace Created ---|
      |                       |- Create Dst FlowSpace ->|
      |                       |<-- FlowSpace Created ---|
      |<--- Port Created -----|                         |


Directory Structure
==============
    quantum/
      etc/
        plugins/
          flowvisor/        # Config Files.
      quantum/
        plugins/
          flowvisor/        # The plugin main directory.
            db/             # The plugin's DB module.
            extensions/     # The flowvisor API extension.

