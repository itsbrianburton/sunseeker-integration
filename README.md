# Sunseeker Lawn Mower Home Assistant Integration

Sunseeker lawn mowers are low-cost, white labeled robot lawn mowers sold under a variety of brand names.  One big negative of these lawnmowers is that it communicates with an unsecure public MQTT broker and transmits personal information including your Wifi SSID with plaintext password.

This integration was built for my own needs because I redirected all MQTT traffic from my lawn mower to a local MQTT broker.  This integration monitors the MQTT traffic and updates various sensor entity states.

**Note: This is not a simple integration!**  In order to use this integration you must redirect your Sunseeker's MQTT traffic to a local MQTT broker.

## Requirements
1. Configurable firewall, preferably iptables.
2. Configurable DHCP server
3. Local MQTT broker

## Preparation
1. Install a local MQTT broker on your network and give it a fixed IP address.  It should be unsecured and not require a username or password.  I recommend you only use it for this purpose.
2. Assign a fixed IP address to your Sunseeker lawn mower.  The easiest way is to give it a static lease on your DHCP server.

## Redirecting MQTT Traffic
This integration is expecting a local MQTT broker to connect with and that he lawn mower's traffic is redirected towards this broker.  Below are a few different options to achieve this. 

### Option 1: UCI in OpenWrt

SSH into your router and run the following commands, replacing `LAWNMOWER_IP` and `MQTT_SERVER_IP` with the correct values:

```
uci add firewall redirect
uci set firewall.@redirect[-1].name='Redirect_MQTT'
uci set firewall.@redirect[-1].src='lan'
uci set firewall.@redirect[-1].src_ip='LAWNMOWER_IP'
uci set firewall.@redirect[-1].src_dport='1883'
uci set firewall.@redirect[-1].dest='lan'
uci set firewall.@redirect[-1].dest_ip='MQTT_SERVER_IP'
uci set firewall.@redirect[-1].dest_port='1883'
uci set firewall.@redirect[-1].proto='tcp'
uci set firewall.@redirect[-1].target='DNAT'

uci commit firewall
/etc/init.d/firewall restart
```

### Option 2: Direct IPTables Commands
SSH into your router and run the following commands, replacing `LAWNMOWER_IP` and `MQTT_SERVER_IP` with the correct values:
```
# Redirect MQTT traffic (port 1883)
iptables -t nat -I PREROUTING -s LAWNMOWER_IP -p tcp --dport 1883 -j DNAT --to-destination MQTT_SERVER_IP:1883
# Enable masquerading for return traffic
iptables -t nat -I POSTROUTING -s LAWNMOWER_IP -d MQTT_SERVER_IP -p tcp --dport 1883 -j MASQUERADE
```
Then restart your firewall: `/etc/init.d/firewall restart`

### Option 3: Edit /etc/firewall/config
SSH into your router and edit the /etc/firewall/config adding these lines:
```
config redirect
    option name 'Redirect_MQTT'
    option src 'lan'
    option src_ip 'LAWNMOWER_IP'
    option src_dport '1883'
    option dest 'lan'
    option dest_ip 'MQTT_SERVER_IP'
    option dest_port '1883'
    option proto 'tcp'
    option target 'DNAT'
```   

Then restart your firewall:
`/etc/init.d/firewall restart`

### Test the Changes
1. Turn your lawn mower off then back on.
2. SSH into your MQTT server and monitor the traffic with the command: `mosquitto_sub -h MQTT_SERVER_IP -t "/device/+/update" -v`
3. If you see messages from the mower, that means it's working.

## Installation

1. Open HACS
2. At the top right click on the three vertical dots and select "Custom Repository"
3. Enter the URL `https://github.com/itsbrianburton/sunseeker-integration` and select "Integration".
4. Search for "Sunseeker" and this integration should appear.
5. Click "Install"
6. Go to "Settings" -> "Devices & Services" and click on "+ Add Integration"
7. Search for "Sunseeker" and complete the configuration process.