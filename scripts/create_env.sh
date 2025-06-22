#!/bin/bash

# Swarm Multi-Agent System - Environment Setup Script
# This script copies .env.example to .env and prompts for required API keys
# 
# Usage: ./scripts/create_env.sh

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Print styled messages
print_header() {
    echo -e "${BLUE}${BOLD}==========================================${NC}"
    echo -e "${BLUE}${BOLD}  Swarm Multi-Agent System Setup${NC}"
    echo -e "${BLUE}${BOLD}==========================================${NC}"
    echo
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if .env.example exists
check_env_example() {
    if [ ! -f ".env.example" ]; then
        print_error ".env.example file not found!"
        print_info "Please make sure you're running this script from the project root directory."
        exit 1
    fi
    print_success "Found .env.example file"
}

# Copy .env.example to .env
copy_env_file() {
    if [ -f ".env" ]; then
        print_warning ".env file already exists!"
        read -p "Do you want to overwrite it? (y/N): " -r
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Skipping .env file creation. You can manually edit your existing .env file."
            return 1
        fi
        print_info "Creating backup of existing .env file..."
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        print_success "Backup created"
    fi
    
    cp .env.example .env
    print_success "Created .env file from template"
    return 0
}

# Prompt for API key with validation
prompt_for_key() {
    local key_name="$1"
    local description="$2"
    local optional="$3"
    local current_value="$4"
    
    echo
    print_info "Setting up: ${BOLD}${key_name}${NC}"
    if [ -n "$description" ]; then
        echo "   $description"
    fi
    
    if [ "$optional" = "true" ]; then
        echo "   (Optional - press Enter to skip)"
    fi
    
    if [ -n "$current_value" ] && [ "$current_value" != "your_${key_name,,}_here" ]; then
        echo "   Current value: ${current_value:0:10}..."
        read -p "   Enter new value (or press Enter to keep current): " -r
        if [ -z "$REPLY" ]; then
            return 0
        fi
    else
        read -p "   Enter value: " -r
    fi
    
    if [ -n "$REPLY" ]; then
        # Escape special characters for sed
        local escaped_value=$(printf '%s\n' "$REPLY" | sed 's/[[\.*^$()+?{|]/\\&/g')
        local escaped_key=$(printf '%s\n' "$key_name" | sed 's/[[\.*^$()+?{|]/\\&/g')
        
        # Update the .env file
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/^${escaped_key}=.*/${escaped_key}=${escaped_value}/" .env
        else
            # Linux
            sed -i "s/^${escaped_key}=.*/${escaped_key}=${escaped_value}/" .env
        fi
        print_success "Set ${key_name}"
    elif [ "$optional" != "true" ]; then
        print_warning "No value provided for required key: ${key_name}"
    fi
}

# Get current value from .env file
get_current_value() {
    local key="$1"
    grep "^${key}=" .env 2>/dev/null | cut -d'=' -f2- || echo ""
}

# Main setup function
setup_environment() {
    print_header
    
    print_info "This script will help you set up the environment configuration."
    print_warning "${BOLD}IMPORTANT: Never commit API keys to version control!${NC}"
    echo
    
    # Check for .env.example
    check_env_example
    
    # Copy template
    if ! copy_env_file; then
        print_info "Using existing .env file for configuration."
    fi
    
    echo
    print_info "Now let's configure your API keys and settings..."
    print_info "You can find these keys from the respective service providers:"
    echo "   • OpenRouter: https://openrouter.ai/keys"
    echo "   • Supermemory: https://supermemory.ai/dashboard"
    echo "   • Mailgun: https://app.mailgun.com/app/dashboard"
    
    # Required API Keys
    echo
    print_info "${BOLD}=== REQUIRED API KEYS ===${NC}"
    
    prompt_for_key "OPENROUTER_API_KEY" \
        "Required for AI model access (get from https://openrouter.ai/keys)" \
        "false" \
        "$(get_current_value "OPENROUTER_API_KEY")"
    
    prompt_for_key "SUPERMEMORY_API_KEY" \
        "Required for persistent memory (get from https://supermemory.ai/dashboard)" \
        "false" \
        "$(get_current_value "SUPERMEMORY_API_KEY")"
    
    # Optional API Keys  
    echo
    print_info "${BOLD}=== EMAIL SERVICE (OPTIONAL) ===${NC}"
    print_info "Mailgun is only needed if you want email functionality"
    
    prompt_for_key "MAILGUN_API_KEY" \
        "For email automation (get from https://app.mailgun.com/app/dashboard)" \
        "true" \
        "$(get_current_value "MAILGUN_API_KEY")"
    
    prompt_for_key "MAILGUN_DOMAIN" \
        "Your Mailgun domain (e.g., mg.yourdomain.com)" \
        "true" \
        "$(get_current_value "MAILGUN_DOMAIN")"
    
    # Application Configuration
    echo
    print_info "${BOLD}=== APPLICATION SETTINGS ===${NC}"
    
    prompt_for_key "SECRET_KEY" \
        "Application secret key (generate a random string)" \
        "false" \
        "$(get_current_value "SECRET_KEY")"
    
    # Generate a random secret key if none provided
    current_secret=$(get_current_value "SECRET_KEY")
    if [ "$current_secret" = "your_secret_key_here" ] || [ -z "$current_secret" ]; then
        print_info "Generating random SECRET_KEY..."
        random_secret=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "$(date +%s)_$(whoami)_$(hostname)" | sha256sum | cut -d' ' -f1)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/^SECRET_KEY=.*/SECRET_KEY=${random_secret}/" .env
        else
            sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${random_secret}/" .env
        fi
        print_success "Generated SECRET_KEY"
    fi
    
    # Final steps
    echo
    print_info "${BOLD}=== SETUP COMPLETE ===${NC}"
    print_success "Environment configuration saved to .env"
    print_warning "Remember to:"
    echo "   • Never commit .env to version control"
    echo "   • Keep your API keys secure"
    echo "   • Use different keys for development and production"
    echo "   • Regularly rotate your API keys"
    
    echo
    print_info "Next steps:"
    echo "   1. Review your .env file: ${BOLD}cat .env${NC}"
    echo "   2. Install dependencies: ${BOLD}pip install -r requirements.txt${NC}"
    echo "   3. Run the application: ${BOLD}python src/main.py${NC}"
    
    echo
    print_success "Setup completed successfully! 🚀"
}

# Run the setup
setup_environment
