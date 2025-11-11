{ config, pkgs, ... }:

{
  # Essential Packages for an IoT Device
  home.packages = with pkgs; 
  [
    # System Utilities
    htop      # Interactive process viewer
    curl      # Data transfer tool
    wget      # File retrieval

    # Development/Debugging
    git       # Version control

    vim
    util-linux
    gptfdisk
    fastfetch
    sops
  ];

  # Let Home Manager manage itself
  programs.home-manager.enable = true;

}