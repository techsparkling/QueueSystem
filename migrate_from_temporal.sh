#!/bin/bash

# Migration Script: Temporal → CallQueueSystem
# This script helps migrate from Temporal workers to CallQueueSystem

echo "🔄 Migrating from Temporal to CallQueueSystem..."

# 1. Update environment variables in Backend
echo "📝 Updating Backend environment..."
cd ../Backend-optimized

# Backup current .env
if [ -f .env ]; then
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    echo "✅ Backed up existing .env file"
fi

# Update environment variables
cat > .env.queue-migration << 'EOF'
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_USERNAME=postgres
DB_PASSWORD=your_password
DB_DATABASE=posibl-voice

# Server Configuration
PORT=3000
NODE_ENV=development

# JWT Configuration
JWT_SECRET=your-super-secret-jwt-key-here
JWT_EXPIRES_IN=24h

# CallQueueSystem Configuration (Replaces Temporal)
EXTERNAL_CALL_API_URL=http://localhost:8000
VOICE_AI_URL=http://localhost:8765
BACKEND_API_URL=http://localhost:3000

# AI Configuration (Gemini API key is hardcoded in service)
# GOOGLE_AI_API_KEY=your-gemini-api-key
EOF

echo "✅ Created .env.queue-migration file"
echo "📋 Please review and update .env file with CallQueueSystem configuration"

# 2. Set up CallQueueSystem environment
echo "📝 Setting up CallQueueSystem environment..."
cd ../CallQueueSystem

# Create .env for CallQueueSystem
cat > .env << 'EOF'
# Redis Configuration
REDIS_URL=redis://localhost:6379

# Queue Configuration
QUEUE_WORKERS=10
MAX_CONCURRENT_CALLS=100
RATE_LIMIT_PER_SECOND=10

# Plivo Configuration
PLIVO_AUTH_ID=your_plivo_auth_id
PLIVO_AUTH_TOKEN=your_plivo_auth_token
PLIVO_PHONE_NUMBER=your_plivo_number

# Agent Server Configuration
AGENT_SERVER_URL=http://localhost:8765
SERVER_URL=http://localhost:8765

# Backend API Configuration
BACKEND_API_URL=http://localhost:3000

# API Configuration
HOST=0.0.0.0
PORT=8000
EOF

echo "✅ Created CallQueueSystem .env file"

# 3. Install dependencies
echo "📦 Installing CallQueueSystem dependencies..."
pip install -r requirements.txt

# 4. Test connections
echo "🧪 Testing system connections..."

# Test Redis connection
python3 -c "
import redis
try:
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    r.ping()
    print('✅ Redis connection successful')
except Exception as e:
    print(f'❌ Redis connection failed: {e}')
    print('💡 Please start Redis: redis-server')
"

# 5. Update PipecatPlivoOutbound if needed
echo "📝 Checking PipecatPlivoOutbound configuration..."
cd ../PipecatPlivoOutbound

# Ensure start-call endpoint is properly configured for call_id tracking
echo "✅ PipecatPlivoOutbound should already support the new call_id tracking"

# 6. Create startup script
cd ../CallQueueSystem
cat > start_migration.sh << 'EOF'
#!/bin/bash
echo "🚀 Starting CallQueueSystem Migration Environment..."

# Start Redis if not running
if ! pgrep -x "redis-server" > /dev/null; then
    echo "📦 Starting Redis..."
    redis-server --daemonize yes
fi

# Start CallQueueSystem
echo "🔄 Starting CallQueueSystem..."
python3 start_queue_system.py &
QUEUE_PID=$!

# Start Backend (in separate terminal)
echo "🌐 Please start Backend in separate terminal:"
echo "  cd Backend-optimized && npm run dev"

# Start PipecatPlivoOutbound (in separate terminal) 
echo "🤖 Please start Voice AI in separate terminal:"
echo "  cd PipecatPlivoOutbound && python3 server.py"

echo "✅ CallQueueSystem started with PID: $QUEUE_PID"
echo "📋 Use 'kill $QUEUE_PID' to stop"

# Wait for user input
read -p "Press Enter to stop CallQueueSystem..."
kill $QUEUE_PID
EOF

chmod +x start_migration.sh

echo ""
echo "🎉 Migration setup complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Update your .env files with actual credentials"
echo "2. Start Redis: redis-server"
echo "3. Start services:"
echo "   - CallQueueSystem: ./start_migration.sh"
echo "   - Backend: cd Backend-optimized && npm run dev"
echo "   - Voice AI: cd PipecatPlivoOutbound && python3 server.py"
echo ""
echo "🧪 Test the integration:"
echo "   - Create a campaign in the frontend"
echo "   - Check CallQueueSystem logs for call processing"
echo "   - Verify call_id tracking across all systems"
echo ""
echo "🔍 Monitor logs:"
echo "   - Backend: Check console for external service notifications"
echo "   - CallQueueSystem: Check queue processing logs"
echo "   - Voice AI: Check call_id tracking and variables"
echo "" 