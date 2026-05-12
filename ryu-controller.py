#!/usr/bin/env python3

import subprocess
import sys

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info


VM_BRIDGE = "vmbr10"
VETH_MN = "veth-mn"
VETH_PVE = "veth-pve"


def run_cmd(cmd, check=True):
    info(f"*** Running: {' '.join(cmd)}\n")
    return subprocess.run(cmd, check=check)


def setup_external_veth():
    info("*** Cleaning old veth pair if it exists\n")
    run_cmd(["ip", "link", "del", VETH_MN], check=False)

    info("*** Creating external veth pair\n")
    run_cmd(["ip", "link", "add", VETH_MN, "type", "veth", "peer", "name", VETH_PVE])

    info(f"*** Attaching {VETH_PVE} to {VM_BRIDGE}\n")
    run_cmd(["ip", "link", "set", VETH_PVE, "master", VM_BRIDGE])

    run_cmd(["ip", "link", "set", VETH_PVE, "up"])
    run_cmd(["ip", "link", "set", VETH_MN, "up"])


def attach_veth_to_ovs(switch_name):
    info(f"*** Attaching {VETH_MN} to OVS switch {switch_name}\n")

    run_cmd([
        "ovs-vsctl",
        "--may-exist",
        "add-port",
        switch_name,
        VETH_MN,
    ])

    run_cmd(["ip", "link", "set", VETH_MN, "up"])

    info("*** Current OVS ports:\n")
    subprocess.run(["ovs-vsctl", "list-ports", switch_name], check=False)


def run():
    setup_external_veth()

    net = Mininet(
        controller=RemoteController,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
        build=False,
    )

    info("*** Adding controller\n")
    c0 = net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653,
    )

    info("*** Adding OpenFlow switch\n")
    s1 = net.addSwitch("s1", protocols="OpenFlow13")

    info("*** Adding client hosts\n")
    h1 = net.addHost(
        "h1",
        ip="10.10.10.10/24",
        defaultRoute="via 10.10.10.1",
    )

    h2 = net.addHost(
        "h2",
        ip="10.10.10.11/24",
        defaultRoute="via 10.10.10.1",
    )

    info("*** Adding links\n")
    net.addLink(h1, s1)
    net.addLink(h2, s1)

    info("*** Building network\n")
    net.build()

    info("*** Starting controller and switch\n")
    c0.start()
    s1.start([c0])

    attach_veth_to_ovs("s1")

    info("*** Network ready\n")
    info("*** Test commands:\n")
    info("    sh ovs-vsctl list-ports s1\n")
    info("    h1 ping -c 3 10.10.10.1\n")
    info("    h1 curl http://10.10.10.1\n")
    info("    h1 curl --connect-timeout 3 http://10.20.20.11\n")
    info("    h1 iperf3 -c 10.10.10.1 -p 5201 -t 10\n")

    CLI(net)

    info("*** Stopping network\n")
    net.stop()

    info("*** Cleaning external veth pair\n")
    run_cmd(["ip", "link", "del", VETH_MN], check=False)


if __name__ == "__main__":
    setLogLevel("info")

    if subprocess.run(["id", "-u"], capture_output=True, text=True).stdout.strip() != "0":
        print("Please run with sudo.")
        sys.exit(1)

    run()