#!/bin/bash

echo "🚀 Setting up Standalone Call Queue System"
echo "==========================================="

# Check if Python 3.11+ is available
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1-2)
echo "🐍 Python version: $python_version"

# Install Redis if not available
if ! command -v redis-server &> /dev/null; then
    echo "📦 Installing Redis..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install redis
        else
            echo "❌ Please install Homebrew first: https://brew.sh"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        sudo apt-get update
        sudo apt-get install -y redis-server
    else
        echo "❌ Please install Redis manually for your OS"
        exit 1
    fi
else
    echo "✅ Redis is already installed"
fi

# Create virtual environment
echo "🔧 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy environment file
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp env.example .env
    echo "⚠️  Please edit .env file with your configuration:"
    echo "   - PLIVO_AUTH_ID"
    echo "   - PLIVO_AUTH_TOKEN"
    echo "   - PLIVO_NUMBER"
    echo "   - AGENT_SERVER_URL"
else
    echo "✅ .env file already exists"
fi

# Start Redis
echo "🚀 Starting Redis..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - start Redis as background service
    brew services start redis
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - start Redis daemon
    redis-server --daemonize yes
else
    echo "⚠️ Please start Redis manually: redis-server"
fi

# Test Redis connection
echo "🧪 Testing Redis connection..."
sleep 2
if redis-cli ping | grep -q PONG; then
    echo "✅ Redis is running"
else
    echo "❌ Redis failed to start"
    echo "💡 Try starting manually: redis-server"
    exit 1
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🎯 Standalone Call Queue System is ready!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your Plivo credentials and agent server URL"
echo "2. Run: python start_queue_system.py"
echo "3. Test: python test_queue_agent_connection.py"
echo "4. Check health: curl http://localhost:8000/api/health"
echo ""
echo "📚 Documentation: README.md"
echo "🔧 No external dependencies - completely standalone!"
echo "" 