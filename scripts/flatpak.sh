#!/bin/bash
set -e # Exit immediately if a command fails

echo "Installing Flatpak..."
sudo apt update && sudo apt install flatpak -y

# Make sure Flathub is added (system-wide and user-level)
sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

echo "Installing Flatpak Builder..."
flatpak install --user -y flathub org.flatpak.Builder

echo "Building with flatpak builder..."
# --install-deps-from=flathub automatically fetches org.kde.Sdk 6.11
flatpak run org.flatpak.Builder \
  --force-clean \
  --install-deps-from=flathub \
  --repo=repo \
  --subject="Bengal Download Manager" \
  build \
  flatpak/io.github.tazihad.bengal-download-manager.yml

echo "✓ Build successful"

echo "Creating single-file bundle (.flatpak)..."
mkdir -p dist
flatpak build-bundle repo dist/bengal-download-manager.flatpak io.github.tazihad.bengal-download-manager
echo "✓ Bundle created: dist/bengal-download-manager.flatpak"

echo "Cleanup..."
rm -rf build repo
echo "✓ Cleanup complete"