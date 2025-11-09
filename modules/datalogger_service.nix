{ config, pkgs, lib, ... }:

let
  # Define the python environment with necessary libraries
  pythonEnv = pkgs.python3.withPackages 
  (ps: with ps; 
    [
      paho-mqtt
      pymodbus
      schedule
      requests
    ]
  );

  # Assuming your python files are in ~/nix-dataloggers/datalogger
  dataloggerDir = "${config.home.homeDirectory}/nix-dataloggers/datalogger";
in
{
  # Define the systemd service
  systemd.user.services.datalogger = {
    Unit = 
    {
      Description = "Python Modbus Datalogger Service";
      After = [ "network-online.target" "mosquitto.service" ];
    };

    Install = 
    {
      WantedBy = [ "default.target" ];
    };

    Service = 
    {
      # Restart indefinitely if it crashes
      Restart = "always";
      RestartSec = "10s";
      
      # Load MQTT credentials if you use them in publish.py
      EnvironmentFile = "%h/.config/datalogger/mqtt.env";
      
      # set PYTHONPATH so python can find the modules in the same directory
      Environment = "PYTHONPATH=${dataloggerDir}";

      # Run main.py using our custom python environment
      ExecStart = "${pythonEnv}/bin/python3 ${dataloggerDir}/main.py";
    };
  };
}