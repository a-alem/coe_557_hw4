sudo iptables -F
sudo iptables -t nat -F

sudo iptables -P FORWARD DROP

# Allow HTTP from client side to load balancer
sudo iptables -A FORWARD -i "$CLIENT_IF" -o "$TRANSIT_IF" -p tcp -d 10.30.30.2 --dport 80 -j ACCEPT

# Allow iperf3 from client side to load balancer
sudo iptables -A FORWARD -i "$CLIENT_IF" -o "$TRANSIT_IF" -p tcp -d 10.30.30.2 --dport 5201 -j ACCEPT

# Allow ICMP to load balancer for latency tests
sudo iptables -A FORWARD -i "$CLIENT_IF" -o "$TRANSIT_IF" -p icmp -d 10.30.30.2 -j ACCEPT

# Allow return traffic
sudo iptables -A FORWARD -i "$TRANSIT_IF" -o "$CLIENT_IF" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT

# Block direct client access to backend server subnet
sudo iptables -A FORWARD -i "$CLIENT_IF" -d 10.20.20.0/24 -j DROP

# DNAT HTTP and iperf3 traffic from firewall external IP to load balancer
sudo iptables -t nat -A PREROUTING -i "$CLIENT_IF" -p tcp --dport 80 -j DNAT --to-destination 10.30.30.2:80
sudo iptables -t nat -A PREROUTING -i "$CLIENT_IF" -p tcp --dport 5201 -j DNAT --to-destination 10.30.30.2:5201

# NAT client network behind firewall transit IP
sudo iptables -t nat -A POSTROUTING -o "$TRANSIT_IF" -j MASQUERADE

sudo netfilter-persistent save