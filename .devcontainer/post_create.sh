#!/bin/bash

# Development container setup script for the code reviewer project
set -e

echo "🚀 Setting up code reviewer development environment..."

# Ensure uv is in PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Install project dependencies
echo "📦 Installing Python dependencies..."
cd /workspaces/code_reviewer

# Check if uv is available, if not install it
if ! command -v uv &> /dev/null; then
    echo "🐍 Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

export UV_LINK_MODE=copy
# Sync dependencies
uv sync

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p .vscode

# Set proper permissions
echo "🔒 Setting permissions..."
chmod +x /workspaces/code_reviewer/.devcontainer/post_create.sh

for script in \
    /workspaces/developer-productivity/bin/env \
    /workspaces/developer-productivity/bin/help \
    /workspaces/developer-productivity/bin/test \
    /workspaces/developer-productivity/bin/lint/all \
    /workspaces/developer-productivity/bin/lint/py \
    /workspaces/developer-productivity/bin/lint/md
do
    if [ -f "$script" ]; then
        chmod +x "$script"
    fi
done

# Create a sample .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "🔐 Creating .env file from template..."
    if [ -f ".env.template" ]; then
        cp .env.template .env
    else
        cat > .env <<'EOF'
# Add environment variables for local development here.
EOF
    fi
fi

echo "✅ Developer environment setup complete!"
echo ""
echo "🎯 Next steps:"
echo "1. Configure your .env file with actual credentials"
echo "2. Run 'uv run python -m src.main --help' to see available commands"
echo "3. Start coding! 🚀"
echo ""

echo "📝 Available commands:"
echo "  - bin/help                    # Shows help options"
echo "  - bin/env                     # Exports variables from an environment file"

echo "  - bin/lint/all                # Run all linting"
echo "  - bin/lint/md                 # Lint all Markdown files"
echo "  - bin/lint/py                 # Format, line and type check all Python files"
echo "  - bin/test                    # Run all unit tests"

echo "  - uv sync                     # Install/update dependencies"
echo "  - uv run ruff check           # Lint code"
echo "  - uv run ruff format          # Format code"
echo "  - uv run pyright              # Type checking"
echo "  - uv run python -m src.main   # Run main application"