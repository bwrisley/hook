#!/bin/bash
# HOOK Custom Docker Image — Build Script
# Usage: cd ~/PROJECTS/hook && ./config/build.sh
#
# After building, restart the gateway with the custom image:
#   openclaw gateway stop
#   openclaw gateway start --image hook-openclaw:latest

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_NAME="hook-openclaw"
IMAGE_TAG="latest"

echo "🪝 Building HOOK custom Docker image..."
echo "   Dockerfile: $SCRIPT_DIR/Dockerfile.hook"
echo "   Image:      $IMAGE_NAME:$IMAGE_TAG"
echo ""

docker build \
  -f "$SCRIPT_DIR/Dockerfile.hook" \
  -t "$IMAGE_NAME:$IMAGE_TAG" \
  "$SCRIPT_DIR/"

echo ""
echo "✅ Build complete: $IMAGE_NAME:$IMAGE_TAG"
echo ""
echo "Next steps:"
echo "  1. Stop gateway:   openclaw gateway stop"
echo "  2. Start with image: openclaw gateway start --image $IMAGE_NAME:$IMAGE_TAG"
echo "  3. Verify agents:  openclaw agents list --bindings"
echo "  4. Test tools:     @HOOK run: dig google.com +short"
echo ""
echo "To verify tools inside the container:"
echo "  docker exec -it hook jq --version"
echo "  docker exec -it hook dig -v"
echo "  docker exec -it hook nmap --version"
