#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo: sudo ./install.sh" >&2
    exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install_dir=/opt/eversolo-scrobbler
config_file=/etc/eversolo-scrobbler.toml
service_file=/etc/systemd/system/eversolo-scrobbler.service

echo "Installing required Python support..."
apt-get update
apt-get install -y python3-venv

if ! id eversolo-scrobbler >/dev/null 2>&1; then
    useradd --system --home /nonexistent --shell /usr/sbin/nologin eversolo-scrobbler
fi

mkdir -p "$install_dir"
python3 -m venv "$install_dir/venv"
"$install_dir/venv/bin/pip" install --upgrade "$project_dir"

if [ ! -f "$config_file" ]; then
    "$install_dir/venv/bin/eversolo-scrobbler" --config "$config_file" configure
else
    echo "Keeping existing configuration: $config_file"
fi

install -m 0644 "$project_dir/deploy/eversolo-scrobbler.service" "$service_file"
systemctl daemon-reload
systemctl enable --now eversolo-scrobbler

echo
echo "Installation complete."
echo "Status: sudo systemctl status eversolo-scrobbler"
echo "Logs:   sudo journalctl -u eversolo-scrobbler -f"
