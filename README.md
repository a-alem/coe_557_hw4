# coe_557_hw4
COE 557 Lab 4 repository

# Steps
## Prerequisites
For this lab, I have used **Debian 12**, as recommended by proxmox docs.

For deployment, I used a m8i EC2 instance type as it supports nested virtualization.

## Proxmox
Check that you have KVM and virtualization enabled
```bash
sudo apt update
sudo apt install -y cpu-checker
kvm-ok
```

Upgrade your system then reboot
```bash
sudo apt full-upgrade -y
sudo reboot
```

Set hostname and local interface assignment
```bash
sudo hostnamectl set-hostname proxmox-lab4
```

Edit `/etc/hosts` file to include the hostname - ip mapping
```bash
sudo vim /etc/hosts
```

Add to `/etc/hosts` file the following (_don't put localhost or loopback address, use the interface's private ip_):
```text
<your_instance_private_ip>      proxmox-lab4.local proxmox-lab4
```

Add proxmox apt repos
```bash
sudo apt install -y curl wget gnupg lsb-release apt-transport-https ca-certificates
sudo wget https://enterprise.proxmox.com/debian/proxmox-release-bookworm.gpg \
  -O /etc/apt/trusted.gpg.d/proxmox-release-bookworm.gpg
echo "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription" | \
  sudo tee /etc/apt/sources.list.d/pve-install-repo.list
sudo apt update
```

Install proxmox from apt
```bash
sudo apt install -y proxmox-ve postfix open-iscsi chrony
```

During `postfix` installation, a prompt might appear, select the following:
```text
General type of mail configuration: Local only
System mail name: proxmox-lab4.local
```

Another prompt might also appear when installing `proxmox` regarding `grub`, select the following:
```text
keep the local version currently installed
```

Reboot instance
```text
sudo reboot
```

Check proxmox systemd services status
```bash
sudo systemctl status pveproxy
sudo systemctl status pvedaemon
sudo systemctl status pvestatd
```

Verify that a port is bound for web UI access (_assuming proxmox default web UI port of 8006_)
```bash
sudo ss -tulpn | grep 8006
```

It's important that you set a root password, as proxmox uses root user, you can create another user that has sudo access for better security, but for this simple lab demonstration, I will use root, to set a password for root, execute the following:
```bash
sudo passwd root
```

If the instance or VM is remote, you can simply port forward using ssh, as follows:
```bash
ssh -i your-key.pem -N -L 8006:127.0.0.1:8006 <user>@<instance_ip>
```

## Ryu Controller
Clone this repository into the instance, so that you can spin up the Ryu controller and the custom mininet topology.
```bash
git clone this_repo
```


Install Mininet and open vSwitch:
```bash
sudo apt install -y mininet openvswitch-switch tcpdump
```

Start OVS:
```bash
sudo systemctl enable openvswitch-switch
sudo systemctl restart openvswitch-switch
sudo systemctl status openvswitch-switch
```

Create the veth pair so that Mininet's open vSwitch `s1` picks it up`:
```bash
sudo ip link del veth-mn 2>/dev/null || true

sudo ip link add veth-mn type veth peer name veth-pve
sudo ip link set veth-pve master vmbr10
sudo ip link set veth-pve up
sudo ip link set veth-mn up
```

Double check that it was created
```bash
ip -br link show veth-mn
ip -br link show veth-pve
```

For Ryu controller, it's containerized, so you need Docker engine, follow this guide [here to install it](https://docs.docker.com/engine/install/debian/).

Verify that Docker daemon is running:
```bash
sudo docker ps
```

Change directory then into the cloned repository, and run the following to spin up the Ryu controller with docker compose orchestration.
```bash
sudo docker compose up -d
```

If you don't have python installed, run the following commands to install it prior to next step
```bash
sudo apt install -y python3 python3-pip
```

## Network configurations

We need the following interfaces created to manage and use proxmox properly:
- `vmbr10`: client/firewall external network
- `vmbr20`: backend server network
- `vmbr30`: firewall/load-balancer transit network
- `vmbr99`: management NAT network, to enable VMs to communicate with the internet

to create the interfaces needed for proxmox, edit `/etc/network/interfaces` file:
```bash
sudo vim /etc/network/interfaces
```

Append the following to the end:
```text
auto vmbr10
iface vmbr10 inet manual
    bridge-ports none
    bridge-stp off
    bridge-fd 0

auto vmbr20
iface vmbr20 inet manual
    bridge-ports none
    bridge-stp off
    bridge-fd 0

auto vmbr30
iface vmbr30 inet manual
    bridge-ports none
    bridge-stp off
    bridge-fd 0

auto vmbr99
iface vmbr99 inet static
    address 192.168.99.1/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
```

Then reboot the instance
```bash
sudo reboot
```

Check that the interfaces are up, and only interface vmbr99 has an ip address
```bash
sudo ip -br addr show vmbr10
sudo ip -br addr show vmbr20
sudo ip -br addr show vmbr30
sudo ip -br addr show vmbr99
```

Enable ipv4 forwarding:
```bash
sudo tee /etc/sysctl.d/99-lab4-forwarding.conf <<< "net.ipv4.ip_forward=1"
sudo sysctl --system
```

Add NAT, this export a variable in the shell only that has the default gateway exist interface called `EXT_IF`:
```bash
EXT_IF=$(ip route | awk '/default/ {print $5; exit}')

sudo iptables -t nat -A POSTROUTING -s 192.168.99.0/24 -o "$EXT_IF" -j MASQUERADE
sudo iptables -A FORWARD -i vmbr99 -o "$EXT_IF" -j ACCEPT
sudo iptables -A FORWARD -i "$EXT_IF" -o vmbr99 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
```

To persist these rules, install the following package and save the current configurations:
```bash
sudo apt update
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

Setup dhcp for VMs when they connect to `vmbr99` interface to access the internet:
```bash
sudo apt install -y dnsmasq

sudo tee /etc/dnsmasq.d/vmbr99.conf > /dev/null <<'EOF'
interface=vmbr99
bind-interfaces

dhcp-range=192.168.99.100,192.168.99.200,255.255.255.0,12h
dhcp-option=option:router,192.168.99.1
dhcp-option=option:dns-server,1.1.1.1
EOF

sudo systemctl restart dnsmasq
sudo systemctl status dnsmasq
```

## VM creation
Check that proxmox displays storage layers properly
```bash
sudo pvesm status
```

Export the storage layer in a variable just in case, usually it's called `local`, it's also a good idea to export it as well in `~/.bashrc`:
```bash
export STORAGE=local
```

Generate SSH key to access VMs, you can go for multiple keys with strong 1-1 mapping association between key-VM, but I will keep it simple and use one for all VMs for this lab purposes:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/lab4_vm_key
```

For ISO image for VMs, I used Ubuntu22.04 server image, I didn't upload it through the web UI as it's very slow, so I used the cli instead, as follows:
```bash
sudo mkdir -p /var/lib/vz/template/iso
sudo cd /var/lib/vz/template/iso
wget -c https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso
```

Once the download finished, you should see the ISO image appearing in proxmox web UI under local storage - ISO section of the lab node.

For the VM installation, install the first VM thoroughly from the web UI and configure Ubuntu as you please, I recommend using the username `lab4`, then save that VM as a base template image, so that it's easier to deploy the other VMs (skipping the installation process entirely).

After the first VM (template) is installed, run the following inside of it to convert it into a template ready VM
```bash
sudo apt update
sudo apt install -y qemu-guest-agent net-tools curl wget vim iperf3
sudo systemctl enable qemu-guest-agent
sudo systemctl start qemu-guest-agent
sudo cloud-init clean --logs 2>/dev/null || true
sudo truncate -s 0 /etc/machine-id
sudo rm -f /var/lib/dbus/machine-id
sudo ln -sf /etc/machine-id /var/lib/dbus/machine-id
history -c
sudo shutdown now
```

Once the VM is fully turned off, convert it into a template from proxmox web UI

From there, create the VMs as needed.

Console into each VM, and set the hostname and IP addressing schemes as needed, I added some configuration files for netplan in `/config/netplan` directory.

Usually, this is how to do it:
```bash
sudo hostnamectl set-hostname <host_name>
sudo vim /etc/netplan/00-installer-config.yaml # Paste the config of your choice here in this file
sudo netplan apply
```
### Server VMs Configs
Install the following in both servers VMs to spin up nginx and serve a simple web page
```bash
sudo apt install -y nginx
echo "Server <number>" | sudo tee /var/www/html/index.html
sudo systemctl enable nginx
sudo systemctl restart nginx
```

After that, initiate an `iperf3` bound process for benchmarking
```bash
iperf3 -s -D -p 5201
```

### Load Balancer VM Configs
Install `haproxy` to the load balancer vnf VM
```bash
sudo apt install -y haproxy
```

Edit the `haproxy` configs and add the configs of your choosing, I added a config example in `/config/haproxy`:
```bash
sudo vim /etc/haproxy/haproxy.cfg
```

### Firewall VM Config
Install ip table persistence
```bash
sudo apt install -y iptables-persistent
```

Enable IPv4 forwarding:
```bash
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-forwarding.conf
```

Check what interfaces you have set for both the 10.10.10.0/24 and the 10.30.30.0/24 networks, and assign them in variables as following, this is used to simply the next step:
```bash
sudo ip -br addr
```

For my setup, it was:en
```text
ens19 = 10.10.10.1
ens20 = 10.30.30.1
```

So I assigned the variables as follows:
```bash
CLIENT_IF="enp6s19"
TRANSIT_IF="enp6s20"
```

After that, apply the rules found in `/config/firewall/firewall_rules.sh`, then:
```bash
sudo netfilter-persistent save
```

## Mininet
Now that the cluster is ready, in another terminal of the main instance, spin up the custom Mininet topology using the `mininet_service_chain_topology.py` file in the cloned repository, **make sure that Ryu is up and running prior**:
```bash
sudo ./mininet_service_chain_topology.py
```

Inside mininet, try a simple ping test to check connectivity
```bash
h1 ping -c 3 10.10.10.1
```

Then, test the service chain with this commands inside mininet:
```bash
h1 curl http://10.10.10.1 # This should work, it passes through the chain as designed
h1 curl --connect-timeout 3 http://10.20.20.11 # This will be blocked, here we are jumping the service chain by some layers, which is not allowed
h1 ping -c 3 10.20.20.11 # This will also be blocked for the same reason
```

In the Ryu controller logs, you should see some traffic monitoring logs like:
```text
BLOCKED bypass attempt: client 10.10.10.10 tried direct access to backend 10.20.20.11
```

## Testing
### Latency and Throughput
Inside of Mininet, run the following:
```bash
h1 ping -c 10 10.30.30.1
h1 iperf3 -c 10.30.30.1 -p 5201 -t 10
```

This should record the latency, metrics such as min/avg/max/mdev, throughput, number of retries (re-transmissions) and duration.

## Load Balancer Behavior
Inside of Mininet, run:
```bash
for i in $(seq 1 10); do h1 curl -s http://10.10.10.1; done
```

Depending on your selected alrogirithm for load balancer, the result should be visible from here.
For example, if you went with round-robin, you should see that the result forms a circular looping sequence, first result from server1, second from server2, third from server1 and so on

