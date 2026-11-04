#!/usr/bin/env bash
# Install files; enable services separately after reviewing README.md.
set -euo pipefail
if (( EUID != 0 )); then
    printf 'Run with sudo: sudo ./install.sh\n' >&2
    exit 1
fi
target_user=${SCREENSAVER_USER:-${SUDO_USER:-}}
if [[ -z $target_user || $target_user == root ]] || ! id "$target_user" >/dev/null 2>&1; then
    printf 'Set SCREENSAVER_USER to an existing non-root desktop account.\n' >&2
    exit 1
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
target_group=$(id -gn "$target_user")
target_uid=$(id -u "$target_user")
target_home=$(getent passwd "$target_user" | cut -d: -f6)
install -d -m 0755 /opt/met-screensaver /opt/met-screensaver/assets
for script in met_fetch.py met_curator.py art_sources.py idle_slideshow.sh slideshow.py auto_captions.py caption_reference.py clean_images.py build_context_bank.py; do
    install -m 0755 "$source_dir/$script" "/opt/met-screensaver/$script"
done
for data in captions.json caption-sources.json context-bank.json context-sources.json README.md AGENTS.md; do
    install -m 0644 "$source_dir/$data" "/opt/met-screensaver/$data"
done
for asset in "$source_dir"/assets/*-cover.png; do
    [[ -f $asset ]] && install -m 0644 "$asset" /opt/met-screensaver/assets/
done
install -d -o "$target_user" -g "$target_group" -m 0755 /srv/screensaver /srv/screensaver/exhibits /srv/screensaver/state
sed "s/@USER@/$target_user/g" "$source_dir/met-curator.service" > /etc/systemd/system/met-curator.service
install -m 0644 "$source_dir/met-curator.timer" /etc/systemd/system/met-curator.timer
install -d -o "$target_user" -g "$target_group" -m 0755 "$target_home/.config/systemd/user"
cat > "$target_home/.config/systemd/user/met-slideshow.service" <<UNIT
[Unit]
Description=Open-collection Mediterranean idle slideshow (Wayland)
After=graphical-session.target
PartOf=graphical-session.target
[Service]
Type=simple
Environment=IMG_DIR=/srv/screensaver/current
Environment=IDLE_MIN=5
Environment=SLIDE_SECONDS=12
Environment=XDG_RUNTIME_DIR=/run/user/$target_uid
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$target_uid/bus
ExecStart=/opt/met-screensaver/idle_slideshow.sh
Restart=always
RestartSec=5
[Install]
WantedBy=graphical-session.target
UNIT
chown "$target_user:$target_group" "$target_home/.config/systemd/user/met-slideshow.service"
systemctl daemon-reload
printf 'Installed for %s. See README.md to build an exhibit and enable the services.\n' "$target_user"
