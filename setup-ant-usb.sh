#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Linux ]]; then
    echo "ANT USB udev setup is only available on Linux." >&2
    exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
    echo "Please install sudo or run this script as root." >&2
    exit 1
fi

rule_file="$(mktemp)"
trap 'rm -f "$rule_file"' EXIT
cat >"$rule_file" <<'EOF'
# Access rules for Dynastream/Garmin ANT USB sticks.
ACTION!="add", GOTO="ant_inspector_end"
SUBSYSTEM!="usb", GOTO="ant_inspector_end"
ATTR{idVendor}=="0fcf", ATTR{idProduct}=="1008", ENV{ID_ANT_DEVICE}="1", TAG+="uaccess", GROUP="plugdev", MODE="0666"
ATTR{idVendor}=="0fcf", ATTR{idProduct}=="1009", ENV{ID_ANT_DEVICE}="1", TAG+="uaccess", GROUP="plugdev", MODE="0666"
LABEL="ant_inspector_end"
EOF

sudo install -o root -g root -m 0644 "$rule_file" /etc/udev/rules.d/42-ant-usb-sticks.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=0fcf --action=add

echo "Installed ANT USB udev rules. Unplug and reconnect the ANT stick, then run:"
echo "  uv run ant-inspector"
