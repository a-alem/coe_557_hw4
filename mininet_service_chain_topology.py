#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink, Intf
from mininet.cli import CLI
from mininet.log import setLogLevel, info


def run():
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
    c0.start()
    s1.start([c0])

    info("*** Attaching external interface veth-mn to s1\n")
    Intf("veth-mn", node=s1)

    info("*** Network ready\n")
    info("*** Test commands:\n")
    info("    h1 curl http://10.10.10.1\n")
    info("    h1 curl --connect-timeout 3 http://10.20.20.11\n")
    info("    h1 iperf3 -c 10.10.10.1 -p 5201 -t 10\n")

    CLI(net)

    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    run()