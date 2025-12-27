#!/bin/bash
# Arnold Quick Setup Script
# This script sets up Arnold with an isolated Python environment

set -e  # Exit on error

echo "========================================"
echo "Arnold Setup - Cyberdyne Systems"
echo "========================================"
echo ""

# Check for required tools
echo "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found"
    echo "Please install Python 3.10 or higher"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "⚠️  Warning: docker not found"
    echo "You'll need Docker to run Neo4j"
    echo "Continue anyway? (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "✓ Prerequisites OK"
echo ""

# Check Python version
python_version=$(python3 --version | cut -d' ' -f2)
echo "Python version: $python_version"

# Check if conda is available
if command -v conda &> /dev/null; then
    echo "Environment manager: conda (preferred)"
    ENV_TYPE="conda"
else
    echo "Environment manager: venv"
    ENV_TYPE="venv"
fi

echo ""
echo "========================================"
echo "Step 1: Environment Setup"
echo "========================================"

make env-create

echo ""
echo "========================================"
echo "Step 2: Configure Neo4j Password"
echo "========================================"
echo ""

if [ -f .env ]; then
    echo "✓ .env file already exists"
else
    echo "Setting Neo4j password..."
    echo "Enter a password for Neo4j (or press Enter for default 'arnold123'):"
    read -r -s password
    echo ""

    if [ -z "$password" ]; then
        password="arnold123"
        echo "Using default password: arnold123"
    fi

    cp .env.example .env
    echo "NEO4J_PASSWORD=$password" >> .env
    export NEO4J_PASSWORD="$password"

    echo "✓ .env file created"
fi

echo ""
echo "========================================"
echo "Step 3: User Profile"
echo "========================================"
echo ""

if [ -f data/user/profile.yaml ]; then
    echo "✓ User profile already exists"
else
    echo "Create user profile now? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        cp data/user/profile.yaml.example data/user/profile.yaml
        echo "✓ Profile created at data/user/profile.yaml"
        echo "⚠️  Edit this file to customize your profile before importing"
        echo ""
        echo "Continue with setup? (y/n)"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo ""
            echo "Setup paused. Edit data/user/profile.yaml then run:"
            echo "  make quickstart"
            exit 0
        fi
    else
        echo "Skipping profile creation"
        echo "You can create it later with:"
        echo "  cp data/user/profile.yaml.example data/user/profile.yaml"
    fi
fi

echo ""
echo "========================================"
echo "Step 4: Start Neo4j & Import Data"
echo "========================================"
echo ""
echo "This will:"
echo "  - Start Neo4j in Docker"
echo "  - Install Python dependencies"
echo "  - Import anatomy, exercises, and your profile"
echo ""
echo "Continue? (y/n)"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    # Source the .env file to get NEO4J_PASSWORD
    if [ -f .env ]; then
        export $(cat .env | grep -v '^#' | xargs)
    fi

    make quickstart
else
    echo ""
    echo "Setup incomplete. To finish later, run:"
    echo "  make quickstart"
    echo ""
    echo "Or run steps individually:"
    echo "  export NEO4J_PASSWORD=your_password"
    echo "  make docker-start"
    echo "  make install"
    echo "  make setup"
    echo "  make import"
fi

echo ""
echo "========================================"
echo "Setup complete!"
echo "========================================"
echo ""
echo "To activate the environment:"
if [ "$ENV_TYPE" = "conda" ]; then
    echo "  conda activate arnold"
else
    echo "  source .venv/bin/activate"
fi
echo ""
echo "Useful commands:"
echo "  make help       - Show all commands"
echo "  make env-info   - Show environment status"
echo "  make validate   - Test the installation"
echo ""
