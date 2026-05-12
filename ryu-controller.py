import ipaddress
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, arp
from ryu.ofproto import ofproto_v1_3


class ServiceChainController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    CLIENT_NET = ipaddress.ip_network("10.10.10.0/24")
    BACKEND_NET = ipaddress.ip_network("10.20.20.0/24")
    FIREWALL_IP = "10.10.10.1"

    def __init__(self, *args, **kwargs):
        super(ServiceChainController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.packet_count = 0
        self.flow_count = {}

    def add_flow(self, datapath, priority, match, actions, idle_timeout=30, hard_timeout=0):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        inst = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )

        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Table-miss: send unknown packets to controller
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]

        self.add_flow(
            datapath=datapath,
            priority=0,
            match=match,
            actions=actions,
            idle_timeout=0,
        )

        # Proactive SDN firewall rule:
        # Clients must not directly access backend subnet.
        # Traffic must go through Firewall -> LB -> Servers.
        backend_block_match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=("10.10.10.0", "255.255.255.0"),
            ipv4_dst=("10.20.20.0", "255.255.255.0"),
        )

        self.add_flow(
            datapath=datapath,
            priority=200,
            match=backend_block_match,
            actions=[],
            idle_timeout=0,
        )

        self.logger.info("Switch connected. Table-miss and backend-block rules installed.")

    def is_client_to_backend(self, src_ip, dst_ip):
        try:
            src = ipaddress.ip_address(src_ip)
            dst = ipaddress.ip_address(dst_ip)
            return src in self.CLIENT_NET and dst in self.BACKEND_NET
        except ValueError:
            return False

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        start_time = time.time()
        self.packet_count += 1

        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        src_mac = eth.src
        dst_mac = eth.dst

        self.mac_to_port[dpid][src_mac] = in_port

        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        if arp_pkt:
            self.logger.info(
                "ARP packet #%d: src_mac=%s dst_mac=%s in_port=%s",
                self.packet_count,
                src_mac,
                dst_mac,
                in_port,
            )

        if ip_pkt:
            src_ip = ip_pkt.src
            dst_ip = ip_pkt.dst

            flow_key = f"{src_ip}->{dst_ip}"
            self.flow_count[flow_key] = self.flow_count.get(flow_key, 0) + 1

            self.logger.info(
                "IPv4 packet #%d: %s -> %s, flow_packets=%d",
                self.packet_count,
                src_ip,
                dst_ip,
                self.flow_count[flow_key],
            )

            # Runtime safety check in addition to proactive drop rule
            if self.is_client_to_backend(src_ip, dst_ip):
                self.logger.warning(
                    "BLOCKED bypass attempt: client %s tried direct access to backend %s",
                    src_ip,
                    dst_ip,
                )
                return

        # L2 forwarding
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [
            parser.OFPActionOutput(out_port)
        ]

        # Install learning flow only after policy checks
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_src=src_mac,
                eth_dst=dst_mac,
            )

            self.add_flow(
                datapath=datapath,
                priority=10,
                match=match,
                actions=actions,
                idle_timeout=30,
            )

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=in_port,
            actions=actions,
            data=msg.data,
        )

        datapath.send_msg(out)

        decision_time_ms = (time.time() - start_time) * 1000
        self.logger.info("Controller decision time: %.3f ms", decision_time_ms)