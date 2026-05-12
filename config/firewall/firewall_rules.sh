#!/usr/bin/env bash

CLIENT_IF="enp6s19"
TRANSIT_IF="enp6s20"

sudo sysctl -w net.ipv4.ip_forward=1

sudo iptables -F
sudo iptables -t nat -F

sudo iptables -P INPUT ACCEPT
sudo iptables -P OUTPUT ACCEPT
sudo iptables -P FORWARD DROP

# DNAT HTTP traffic from client side to HAProxy
sudo iptables -t nat -A PREROUTING -i "$CLIENT_IF" \
  -p tcp -d 10.10.10.1 --dport 80 \
  -j DNAT --to-destination 10.30.30.2:80

# DNAT iperf traffic from client side to HAProxy
sudo iptables -t nat -A PREROUTING -i "$CLIENT_IF" \
  -p tcp -d 10.10.10.1 --dport 5201 \
  -j DNAT --to-destination 10.30.30.2:5201

# Allow HTTP after DNAT
sudo iptables -A FORWARD -i "$CLIENT_IF" -o "$TRANSIT_IF" \
  -p tcp -d 10.30.30.2 --dport 80 \
  -j ACCEPT

# Allow iperf after DNAT
sudo iptables -A FORWARD -i "$CLIENT_IF" -o "$TRANSIT_IF" \
  -p tcp -d 10.30.30.2 --dport 5201 \
  -j ACCEPT

# Allow ICMP to load balancer
sudo iptables -A FORWARD -i "$CLIENT_IF" -o "$TRANSIT_IF" \
  -p icmp -d 10.30.30.2 \
  -j ACCEPT

# IMPORTANT FIX:
# Allow return traffic from load balancer side back to client side
sudo iptables -A FORWARD -i "$TRANSIT_IF" -o "$CLIENT_IF" \
  -m conntrack --ctstate RELATED,ESTABLISHED \
  -j ACCEPT

# Block direct access to backend network
sudo iptables -A FORWARD -i "$CLIENT_IF" -d 10.20.20.0/24 \
  -j DROP

# Masquerade client traffic behind firewall transit IP
sudo iptables -t nat -A POSTROUTING -o "$TRANSIT_IF" \
  -j MASQUERADE