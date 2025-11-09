{ config, pkgs, lib, ... }:

{
  # Install mosquitto client tools
  home.packages = [ pkgs.mosquitto ];

  # --- SERVICE: MQTT Instant Listener ---
  systemd.user.services.mqtt-watchtower = {
    Unit = {
      Description = "MQTT Instant Update Listener";
      After = [ "network-online.target" ];
      # Keep trying to restart indefinitely if network connection is lost
      StartLimitIntervalSec = 0;
    };

    Install = { WantedBy = [ "default.target" ]; };

    Service = {
      Restart = "always";
      # Wait a bit before restarting to avoid hammering the broker if down
      RestartSec = "30s";

      # Load the secrets securely at runtime
      EnvironmentFile = "%h/.config/datalogger/mqtt.env";

      ExecStart = pkgs.writeShellScript "mqtt-listener" ''
        set -e
        # Ensure standard paths for tools
        export PATH=${lib.makeBinPath [ pkgs.mosquitto pkgs.systemd ]}:$PATH

        echo "Starting MQTT Watchtower on $MQTT_HOST:8883..."

        while true; do
          # -h : Broker Host
          # -p : 8883 (Standard TLS port)
          # --capath /etc/ssl/certs : Tells mosquitto to trust standard public CAs (Raspberry Pi OS default)
          # -u / -P : Authentication from env file
          # -C 1 : Exit successfully after receiving ONE message
          
          mosquitto_sub \
            -h "$MQTT_HOST" \
            -p 8883 \
            --capath /etc/ssl/certs \
            -u "$MQTT_USER" \
            -P "$MQTT_PASS" \
            -t "$MQTT_TOPIC" \
            -C 1

          echo "TRIGGER RECEIVED. Starting update routine..."
          
          # Trigger the separate updater service and wait for it to finish
          # before listening again.
          systemctl --user start --wait watchtower-update.service || echo "Update failed, returning to listen mode."
          
          # Small cooldown to prevent rapid-fire triggers
          sleep 5
        done
      '';
    };
  };

  # --- SERVICE: The Actual Updater ---
  # Separated so it can be triggered manually if needed without killing MQTT
  systemd.user.services.watchtower-update = {
    Unit.Description = "Perform Git Pull and Nix Switch";
    Service = {
      Type = "oneshot";
      # Increase timeout for slow package downloads on RPi
      TimeoutStartSec = "10m";
      ExecStart = pkgs.writeShellScript "do-update" ''
        set -e
        export PATH=${lib.makeBinPath [ pkgs.git pkgs.nix pkgs.home-manager ]}:$PATH
        
        cd ~/nix-dataloggers
        
        # Use specific GIT_SSH_COMMAND if you use deploy keys, 
        # otherwise standard HTTPS git pull works if credentials are saved.
        echo "Fetching origin..."
        git fetch origin main
        
        LOCAL=$(git rev-parse @)
        REMOTE=$(git rev-parse @{u})
        
        if [ "$LOCAL" != "$REMOTE" ]; then
           echo "Changes detected (Local: $LOCAL -> Remote: $REMOTE). Switching..."
           git pull
           # The critical line that updates the system
           nix run home-manager -- switch --flake .#datalogger
           echo "Upgrade complete successfully."
        else
           echo "System already up to date."
        fi
      '';
    };
  };
}