#!/bin/bash

# This script is designed to set up a Raspberry Pi for production datalogger use.
# It MUST be run with root privileges (e.g., "sudo ./raspberry_pi_setup.sh")
#
# set -e : Exit immediately if a command exits with a non-zero status.
# set -u : Treat unset variables as an error when substituting.
# set -o pipefail : The return value of a pipeline is the status of
#                   the last command to exit with a non-zero status,
#                   or zero if no command exited with a non-zero status.
set -euo pipefail

# --- [Step 0/11] Root User Check ---
if [ "$(id -u)" -ne 0 ]; then
  echo "!!! This script must be run as root (with sudo). Exiting. !!!"
  exit 1
fi

echo "--- [Step 1/11] Starting Full System Update & Upgrade ---"
# This updates the package lists and upgrades all installed packages.
apt update
apt upgrade -y
echo "--- System update complete. ---"
echo ""

echo "--- [Step 2/11] Applying Raspberry Pi EEPROM Firmware Updates ---"
# This attempts to apply any pending bootloader/EEPROM firmware updates.
# We first check if the 'rpi-eeprom-update' command exists.
# This check prevents errors on older Pi models that don't have this tool.
if command -v rpi-eeprom-update >/dev/null 2>&1; then
  echo "Found rpi-eeprom-update. Applying any pending firmware updates..."
  # The -a flag automatically applies any available updates
  rpi-eeprom-update -a
else
  echo "rpi-eeprom-update tool not found. Skipping (this is normal for older Pi models)."
fi
echo "--- EEPROM update check complete. ---"
echo ""

echo "--- [Step 3/11] Cleaning up previous Nix install artifacts ---"
# The installer will fail if old backup files exist from a previous
# or failed installation. We remove them to ensure this script is
# rerunnable and the installation is clean.
rm -f /etc/bashrc.backup-before-nix
rm -f /etc/profile.d/nix.sh.backup-before-nix
rm -f /etc/zshrc.backup-before-nix
rm -f /etc/bash.bashrc.backup-before-nix
echo "--- Old artifact cleanup complete. ---"
echo ""

echo "--- [Step 4/11] Installing Nix Package Manager (Daemon) ---"
# Check if Nix is already installed by looking for the /nix directory
if [ -d "/nix" ]; then
    echo "The /nix directory already exists."
    echo "--- Nix appears to be already installed. Skipping installation. ---"
else
    echo "No existing /nix directory found. Starting new installation..."
    # This runs the official installer script for Nix in daemon (multi-user) mode.
    # We pipe the curl download directly into sh.
    curl --proto '=https' --tlsv1.2 -L https://nixos.org/nix/install | sh -s -- --daemon
    echo "--- Nix installation complete. ---"
fi
echo ""

echo "--- [Step 5/11] Configuring Nix for Flakes ---"
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


echo "--- [Step 6/11] Enabling Automatic Security Updates ---"
# This installs and configures 'unattended-upgrades' to automatically
# apply security updates in the background.
apt install unattended-upgrades -y
# Set DEBIAN_FRONTEND=noninteractive to prevent any TUI confirmation
DEBIAN_FRONTEND=noninteractive dpkg-reconfigure -plow unattended-upgrades
echo "--- Automatic updates enabled. ---"
echo ""


echo "--- [Step 7/11] Enabling User Services on Boot (Linger) ---"
# This allows systemd user services (like those Nix may create)
# to start at boot, even before a user logs in.
# We will automatically use the user who invoked 'sudo' ($SUDO_USER).

# Check if $SUDO_USER is set and not empty
if [ -z "$SUDO_USER" ]; then
    echo "!!! Could not find \$SUDO_USER. Skipping linger step. !!!"
    echo "Please run 'sudo loginctl enable-linger <username>' manually after reboot."
# Check if the user is 'root' - we don't want to linger root.
# FIX 1: Changed '==' to '=' for POSIX compatibility with sh/dash
elif [ "$SUDO_USER" = "root" ]; then
    echo "!!! Script was run by root directly, not via sudo. Skipping linger step. !!!"
    echo "Please run 'sudo loginctl enable-linger <username>' manually after reboot."
# Check if the user actually exists (pre-flight check)
elif id -u "$SUDO_USER" >/dev/null 2>&1; then
    echo "--- Automatically enabling linger for user '$SUDO_USER'... ---"
    # FIX 2: Changed 'logctl' to 'loginctl'
    loginctl enable-linger "$SUDO_USER"
    echo "--- User services (linger) enabled for '$SUDO_USER'. ---"
else
    # This case should rarely happen if sudo is set up correctly
    echo "!!! User '$SUDO_USER' does not seem to exist. Skipping linger step. !!!"
    echo "Please run 'sudo loginctl enable-linger <username>' manually after reboot."
fi
echo ""

echo "--- [Step 8/11] Enabling Hardware Datalogger Interfaces ---"
# We need to enable hardware interfaces for sensors.
# We use raspi-config's non-interactive 'nonint' mode.
# 0 = enable, 1 = disable
if command -v raspi-config >/dev/null 2>&1; then
  echo "Enabling I2C..."
  raspi-config nonint do_i2c 0
  echo "Enabling SPI..."
  raspi-config nonint do_spi 0
  echo "Enabling Serial Hardware (disabling serial console)..."
  # This enables serial for hardware (like GPS) and disables the login shell
  raspi-config nonint do_serial_hw 0
  echo "--- Hardware interfaces enabled. ---"
else
  echo "--- raspi-config not found. Skipping hardware interface setup. ---"
fi
echo ""

echo "--- [Step 9/11] Enabling Hardware Watchdog ---"
# This enables the hardware watchdog to automatically reboot the Pi if it freezes.
# This is a critical feature for production dataloggers.
if command -v raspi-config >/dev/null 2>&1; then
  echo "Enabling hardware watchdog..."
  raspi-config nonint do_watchdog 0
  echo "--- Hardware watchdog enabled. ---"
else
  echo "--- raspi-config not found. Skipping hardware watchdog setup. ---"
fi
echo ""

echo "--- [Step 10/11] Setup Complete. Rebooting... ---"
# The final reboot is required to apply firmware, hardware, and service changes.
echo "The system will reboot in 10 seconds. Press Ctrl+C to cancel."
sleep 10
reboot