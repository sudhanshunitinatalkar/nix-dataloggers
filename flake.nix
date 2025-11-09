{
  description = "RPi Home Manager Config";

  inputs = {
    # Using unstable for RPi often gets better ARM support, 
    # but you can stick to a release branch if preferred.
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager = 
    {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = 
  { self, nixpkgs, home-manager, ... }@inputs:
    let
      system = "aarch64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      homeConfigurations."datalogger" = home-manager.lib.homeManagerConfiguration 
      {
        inherit pkgs;
        
        # Pass inputs if your home.nix needs them
        extraSpecialArgs = { inherit inputs; };

        modules = 
        [
          ./home/home.nix
        #   ./modules/watchtower.nix
          {
            home = 
            {
              username = "datalogger";
              homeDirectory = "/home/datalogger";
              stateVersion = "25.05"; # Update this to match your install time
            };

            # Let Home Manager install and manage itself.
            programs.home-manager.enable = true;
          }
        ];
      };
    };
}