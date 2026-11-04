#!/usr/bin/env bash
# Install on Ubuntu GNOME Wayland as pompeii (uid 1000):
#   sudo apt install python3-pil imv
#   sudo ./install.sh
#   mkdir -p ~/.config/systemd/user
#   sed -n '/^# \[Unit\]/,$s/^# \{0,1\}//p' /opt/met-screensaver/idle_slideshow.sh > ~/.config/systemd/user/met-slideshow.service
# From a terminal INSIDE the logged-in GNOME Wayland session:
#   systemctl --user import-environment WAYLAND_DISPLAY XDG_SESSION_TYPE DISPLAY
#   systemctl --user daemon-reload
#   systemctl --user enable --now met-slideshow.service
# Build exhibits separately with met_curator.py; see README.md for the timer.
# This script never changes GNOME blanking, locking, or DPMS settings.

set -u
set -o pipefail

IMG_DIR=${IMG_DIR:-/srv/screensaver/current}
IDLE_MIN=${IDLE_MIN:-5}
SLIDE_SECONDS=${SLIDE_SECONDS:-12}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}

log() {
    printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*" >&2
}

if [[ ! $IDLE_MIN =~ ^[0-9]+$ || ! $SLIDE_SECONDS =~ ^[0-9]+$ ]]; then
    log 'IDLE_MIN must be a nonnegative integer; SLIDE_SECONDS must be a positive integer.'
    exit 1
fi
idle_threshold_ms=$((10#$IDLE_MIN * 60000))
if (( idle_threshold_ms < 0 || 10#$SLIDE_SECONDS < 1 )); then
    log 'Invalid timing settings.'
    exit 1
fi

for command in gdbus python3 find shuf readlink; do
    if ! command -v "$command" >/dev/null 2>&1; then
        log "Required command is missing: $command"
        exit 1
    fi
done
if [[ -z ${WAYLAND_DISPLAY:-} ]]; then
    log 'WAYLAND_DISPLAY is missing; import the GNOME session environment as shown above.'
    exit 1
fi
# Absolute paths also prevent image filenames from being treated as viewer options.
[[ $IMG_DIR = /* ]] || IMG_DIR=$PWD/$IMG_DIR

viewer_pid=''
last_idle_ms=''
monitor_state=''
catalog_state=''
idle_pattern='^\([[:space:]]*uint64[[:space:]]+([0-9]+),[[:space:]]*\)$'

stop_slideshow() {
    local reason=$1
    if [[ -n $viewer_pid ]]; then
        kill "$viewer_pid" 2>/dev/null || :
        wait "$viewer_pid" 2>/dev/null || :
        viewer_pid=''
        log "Slideshow stopped: $reason"
    fi
}

trap 'exit 0' INT TERM HUP
trap 'stop_slideshow "service stopping"' EXIT

log "Idle slideshow ready: directory=$IMG_DIR, idle=${IDLE_MIN}min, slide=${SLIDE_SECONDS}s"
while :; do
    idle_reply=''
    if idle_reply=$(gdbus call --session \
        -d org.gnome.Mutter.IdleMonitor \
        -o /org/gnome/Mutter/IdleMonitor/Core \
        -m org.gnome.Mutter.IdleMonitor.GetIdletime 2>/dev/null) \
        && [[ $idle_reply =~ $idle_pattern ]]; then
        idle_ms=$((10#${BASH_REMATCH[1]}))
        if [[ $monitor_state = failed ]]; then
            log 'GNOME idle monitor recovered.'
        fi
        monitor_state=ok
    else
        if [[ $monitor_state != failed ]]; then
            log 'GNOME idle monitor unavailable or returned an invalid response; waiting.'
        fi
        monitor_state=failed
        last_idle_ms=''
        stop_slideshow 'idle monitor unavailable'
        sleep 5
        continue
    fi

    if [[ -n $viewer_pid ]]; then
        if ! kill -0 "$viewer_pid" 2>/dev/null; then
            wait "$viewer_pid" 2>/dev/null
            viewer_status=$?
            viewer_pid=''
            log "Slideshow exited: status=$viewer_status"
        elif (( idle_ms < 2000 )) \
            || { [[ -n $last_idle_ms ]] && (( idle_ms < last_idle_ms )); }; then
            # A counter decrease catches isolated input between 5-second polls,
            # even if the next sample is already above the 2000 ms threshold.
            stop_slideshow 'user input'
        fi
    fi

    if [[ -z $viewer_pid ]] && (( idle_ms >= idle_threshold_ms )); then
        images=()
        resolved_dir=''
        # Resolve again for every start so a newly published exhibit is picked up.
        if resolved_dir=$(readlink -f -- "$IMG_DIR" 2>/dev/null) \
            && [[ -d $resolved_dir && -r $resolved_dir && -x $resolved_dir ]]; then
            # NUL delimiters preserve spaces and newlines in image filenames.
            mapfile -d '' -t images < <(
                find "$resolved_dir" -maxdepth 1 -type f -readable ! -name '000_title.jpg' \
                    \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' \
                    -o -iname '*.webp' \) -print0 2>/dev/null | shuf -z
            )
            if [[ -f $resolved_dir/000_title.jpg && -r $resolved_dir/000_title.jpg ]]; then
                images=("$resolved_dir/000_title.jpg" "${images[@]}")
            fi
        fi
        if (( ${#images[@]} == 0 )); then
            if [[ $catalog_state != empty ]]; then
                log "No readable images in $IMG_DIR; waiting."
            fi
            catalog_state=empty
        else
            catalog_state=ready
            # Our own full-screen GTK window: nothing to pan, zoom or skip; any input closes it (imv could be
            # dragged and zoomed for up to 5 s before this loop noticed the input).
            python3 "$(dirname "$(readlink -f "$0")")/slideshow.py" --seconds "$SLIDE_SECONDS" "${images[@]}" &
            viewer_pid=$!
            log "Slideshow started: pid=$viewer_pid, images=${#images[@]}"
        fi
    fi
    last_idle_ms=$idle_ms
    if [[ -n $viewer_pid ]]; then sleep 1; else sleep 5; fi
done

# Ready-to-use ~/.config/systemd/user/met-slideshow.service (run as pompeii).
# Import WAYLAND_DISPLAY from the actual GNOME terminal; do not guess its name.
# [Unit]
# Description=Open-collection Mediterranean idle slideshow (Wayland)
# After=graphical-session.target
# PartOf=graphical-session.target
#
# [Service]
# Type=simple
# Environment=IMG_DIR=/srv/screensaver/current
# Environment=IDLE_MIN=5
# Environment=SLIDE_SECONDS=12
# Environment=XDG_RUNTIME_DIR=/run/user/1000
# Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
# ExecStart=/opt/met-screensaver/idle_slideshow.sh
# Restart=always
# RestartSec=5
#
# [Install]
# WantedBy=graphical-session.target
