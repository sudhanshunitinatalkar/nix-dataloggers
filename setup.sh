#!/bin/bash

# This script is designed to set up a Raspberry Pi for production use.
# It MUST be run with root privileges (e.g., "sudo ./raspberry_pi_setup.sh")
#
# set -e : Exit immediately if a command exits with a non-zero status.
# set -u : Treat unset variables as an error when substituting.
# set -o pipefail : The return value of a pipeline is the status of
#                   the last command to exit with a non-zero status,
#                   or zero if no command exited with a non-zero status.
set -euo pipefail

# --- [Step 0/8] Root User Check ---
if [ "$(id -u)" -ne 0 ]; then
  echo "!!! This script must be run as root (with sudo). Exiting. !!!"
  exit 1
fi

echo "--- [Step 1/8] Starting Full System Update & Upgrade ---"
# This updates the package lists and upgrades all installed packages.
# This also updates the Raspberry Pi firmware to the latest stable version.
apt update
apt upgrade -y
echo "--- System update complete. ---"
echo ""

echo "--- [Step 2/8] Cleaning up previous Nix install artifacts ---"
# The installer will fail if old backup files exist from a previous
# or failed installation. We remove them to ensure this script is
# rerunnable and the installation is clean.
rm -f /etc/bashrc.backup-before-nix
rm -f /etc/profile.d/nix.sh.backup-before-nix
rm -f /etc/zshrc.backup-before-nix
rm -f /etc/bash.bashrc.backup-before-nix
echo "--- Old artifact cleanup complete. ---"
echo ""

echo "--- [Step 3/8] Installing Nix Package Manager (Daemon) ---"
# This runs the official installer script for Nix in daemon (multi-user) mode.
# We pipe the curl download directly into sh.
curl --proto '=https' --tlsv1.2 -L https://nixos.org/nix/install | sh -s -- --daemon
echo "--- Nix installation complete. ---"
echo ""

echo "--- [Step 4/8] Configuring Nix for Flakes ---"
# This enables experimental features like flakes, which are
# essential for modern Nix-based dataloggers.
NIX_CONF_FILE="/etc/nix/nix.conf"
NIX_CONF_LINE="experimental-features = nix-command flakes"

# Ensure the directory and file exist
mkdir -p /etc/nix
touch "$NIX_CONF_FILE"

# Append the line only if it doesn't already exist
if ! grep -qF "$NIX_CONF_LINE" "$NIX_CONF_FILE"; then
    echo "Adding '$NIX_CONF_LINE' to $NIX_CONF_FILE..."
    echo "$NIX_CONF_LINE" >> "$NIX_CONF_FILE"
    echo "--- Nix configuration updated. ---"
else
    echo "--- Nix configuration already set for flakes. Skipping. ---"
fi
echo ""


echo "--- [Step 5/8] Enabling Automatic Security Updates ---"
# This installs and configures 'unattended-upgrades' to automatically
# apply security updates in the background.
apt install unattended-upgrades -y
# Set DEBIAN_FRONTEND=noninteractive to prevent any TUI confirmation
DEBIAN_FRONTEND=noninteractive dpkg-reconfigure -plow unattended-upgrades
echo "--- Automatic updates enabled. ---"
echo ""


echo "--- [Step 6/8] Enabling User Services on Boot (Linger) ---"
# This allows systemd user services (like those Nix may create)
# to start at boot, even before a user logs in.
# We will automatically use the user who invoked 'sudo' ($SUDO_USER).

# Check if $SUDO_USER is set and not empty
if [ -z "$SUDO_USER" ]; then
    echo "!!! Could not find \$SUDO_USER. Skipping linger step. !!!"
    echo "Please run 'sudo loginctl enable-linger <username>' manually after reboot."
# Check if the user is 'root' - we don't want to linger root.
elif [ "$SUDO_USER" == "root" ]; then
    echo "!!! Script was run by root directly, not via sudo. Skipping linger step. !!!"
    echo "Please run 'sudo loginctl enable-linger <username>' manually after reboot."
# Check if the user actually exists (pre-flight check)
elif id -u "$SUDO_USER" >/dev/null 2>&1; then
    echo "--- Automatically enabling linger for user '$SUDO_USER'... ---"
    loginctl enable-linger "$SUDO_USER"
    echo "--- User services (linger) enabled for '$SUDO_USER'. ---"
else
    # This case should rarely happen if sudo is set up correctly
    echo "!!! User '$SUDO_USER' does not seem to exist. Skipping linger step. !!!"
    echo "Please run 'sudo loginctl enable-linger <username>' manually after reboot."
fi
echo ""

echo "--- [Step 7/8] Setup Complete. Rebooting... ---"
echo "The system will reboot in 10 seconds. Press Ctrl+C to cancel."
sleep 10
reboot