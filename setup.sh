#!/bin/bash

# Swarm Multi-Agent System v2.0 - Quick Setup Script
# Built with usability, reliability, and intelligence first

echo "🚀 Setting up Swarm Multi-Agent System v2.0..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run this from the project directory."
    exit 1
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚙️  Creating environment configuration..."
    cp .env.example .env
    echo "✅ Created .env file from template"
    echo "📝 Please edit .env with your API keys:"
    echo "   - OPENROUTER_API_KEY (required)"
    echo "   - SUPERMEMORY_API_KEY (optional)"
    echo "   - MAILGUN_API_KEY (optional)"
    echo "   - MAILGUN_DOMAIN (optional)"
    echo ""
fi

# Install any missing dependencies
echo "📚 Checking dependencies..."
pip install -q -r requirements.txt

# Run health check
echo "🔍 Running system health check..."
python -c "
import sys
sys.path.insert(0, 'src')
try:
    from src.config import config
    print('✅ Configuration loaded successfully')
    
    from src.services.agent_service import AgentService
    from src.services.openrouter_service import OpenRouterService
    
    openrouter = OpenRouterService()
    agent_service = AgentService(openrouter)
    agents = agent_service.list_all_agents()
    print(f'✅ {len(agents)} agents registered successfully')
    
    print('✅ System health check passed')
except Exception as e:
    print(f'⚠️  Health check warning: {e}')
    print('   This is normal if API keys are not configured yet')
"

echo ""
echo "🎉 Setup complete!"
echo ""
echo "🚀 To start the system:"
echo "   python src/main.py"
echo ""
echo "🌐 Then open: http://localhost:5000"
echo ""
echo "📖 For more information, see README.md"
echo ""
echo "💡 Remember to configure your API keys in .env for full functionality!"

