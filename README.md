# nix-datalogger

fleet-repo/
├── flake.nix             # The entry point
├── flake.lock
├── pkgs/
│   └── data-logger/      # Your python application
│       └── default.nix
└── hosts/
    └── rpi-generic.nix   # Common configuration for all Pis
