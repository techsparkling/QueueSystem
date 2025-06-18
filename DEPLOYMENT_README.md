# CallQueueSystem - Deployment Scripts

This directory contains automated deployment scripts for deploying the CallQueueSystem to Google Cloud Run.

## 📋 Available Scripts

### 1. `deploy-to-cloudrun.sh` - Full Deployment Script

The comprehensive deployment script with full error checking and verbose output.

```bash
./deploy-to-cloudrun.sh [--logs]
```

**Features:**
- ✅ Dependency checking (Docker, gcloud CLI)
- ✅ Docker daemon validation
- ✅ Comprehensive error handling
- ✅ Color-coded output
- ✅ Automatic testing after deployment
- ✅ Timestamped image tagging
- ✅ Service URL display

**Options:**
- `--logs`: Show recent service logs after deployment

### 2. `quick-deploy.sh` - Simple & Fast

Quick deployment script for rapid iterations.

```bash
./quick-deploy.sh
```

**Features:**
- 🚀 Fast deployment
- 📦 Build, push, and deploy in one command
- ✅ Basic health check
- 📋 Reads from `deploy.config`

### 3. `dev-deploy.sh` - Development Script

Development-focused script with advanced options.

```bash
./dev-deploy.sh [--skip-build] [--logs]
```

**Features:**
- 🛠️ Development-friendly
- ⏭️ Option to skip Docker build
- 📊 Enhanced testing (health + queue status)
- 📋 Optional log viewing
- 🎯 Quieter output for faster cycles

**Options:**
- `--skip-build`: Deploy without rebuilding Docker image
- `--logs`: Show recent logs after deployment

## ⚙️ Configuration

All scripts read from `deploy.config` for environment variables and settings.

### Key Configuration Sections:

```bash
# Google Cloud Configuration
PROJECT_ID="posibldashboard"
SERVICE_NAME="queue-system"
REGION="us-east1"

# Container Resources
MEMORY="2Gi"
CPU="2"
MIN_INSTANCES="0"
MAX_INSTANCES="10"

# Environment Variables
PLIVO_AUTH_ID="your_auth_id"
PLIVO_AUTH_TOKEN="your_auth_token"
AGENT_SERVER_URL="your_ngrok_url"
```

## 🚀 Quick Start

1. **First-time setup:**
   ```bash
   # Make scripts executable
   chmod +x *.sh
   
   # Edit configuration
   nano deploy.config
   ```

2. **For regular deployments:**
   ```bash
   # Quick deployment
   ./quick-deploy.sh
   
   # Or development deployment
   ./dev-deploy.sh
   ```

3. **For production deployments:**
   ```bash
   # Full deployment with validation
   ./deploy-to-cloudrun.sh
   ```

## 📁 File Structure

```
CallQueueSystem/
├── deploy-to-cloudrun.sh   # Full deployment script
├── quick-deploy.sh         # Simple deployment  
├── dev-deploy.sh          # Development script
├── deploy.config          # Configuration file
├── Dockerfile.cloudrun    # Cloud Run optimized Dockerfile
└── DEPLOYMENT_README.md   # This file
```

## 🔧 Common Use Cases

### Making Code Changes
```bash
# Edit your code files...
# Then deploy quickly:
./dev-deploy.sh
```

### Updating Environment Variables
```bash
# Edit deploy.config
nano deploy.config

# Deploy with config-only change (skip build)
./dev-deploy.sh --skip-build
```

### Production Deployment
```bash
# Full validation and deployment
./deploy-to-cloudrun.sh --logs
```

### Debugging Issues
```bash
# Deploy and immediately check logs
./dev-deploy.sh --logs

# Or check logs separately
gcloud run services logs read queue-system --region=us-east1 --limit=50
```

## 🏥 Health Checks

All scripts include automatic health checks:

1. **Service Health:** `GET /api/health`
2. **Queue Status:** `GET /api/queue/status`

## 🔍 Troubleshooting

### Common Issues:

1. **Docker not running:**
   ```bash
   # macOS with Colima
   colima start
   
   # Docker Desktop
   # Start Docker Desktop application
   ```

2. **Wrong Google Cloud project:**
   ```bash
   # Check current project
   gcloud config get-value project
   
   # Set correct project
   gcloud config set project posibldashboard
   ```

3. **Authentication issues:**
   ```bash
   # Re-authenticate
   gcloud auth login
   gcloud auth configure-docker
   ```

4. **VPC connectivity issues:**
   ```bash
   # Check VPC connector
   gcloud compute networks vpc-access connectors list --region=us-east1
   ```

## 📊 Service Information

**Current Deployment:**
- **Service URL:** `https://queue-system-443142017693.us-east1.run.app`
- **Region:** `us-east1`
- **Project:** `posibldashboard`

**Key Endpoints:**
- Health: `/api/health`
- Queue Status: `/api/queue/status`
- Queue Call: `/api/calls/outbound`
- Call Status: `/api/calls/{id}/status`

## 🔄 Automated Workflows

### Example: Update Agent Server URL
```bash
# 1. Update ngrok URL in deploy.config
sed -i 's/424c-106-51-170-188/NEW_NGROK_ID/g' deploy.config

# 2. Deploy with new config (no rebuild needed)
./dev-deploy.sh --skip-build

# 3. Test the change
curl -s https://queue-system-443142017693.us-east1.run.app/api/health
```

### Example: Code Change Workflow
```bash
# 1. Edit your Python files
nano call_queue_manager.py

# 2. Test locally (optional)
python -m pytest

# 3. Deploy to Cloud Run
./dev-deploy.sh

# 4. Test the deployment
curl -X POST https://queue-system-443142017693.us-east1.run.app/api/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+919123456789", "campaign_id": "test"}'
```

## 🎯 Best Practices

1. **Use dev-deploy.sh for iterative development**
2. **Use quick-deploy.sh for stable builds**
3. **Use deploy-to-cloudrun.sh for production releases**
4. **Always update deploy.config when URLs change**
5. **Test health endpoints after deployment**
6. **Use --logs flag when debugging issues**

---

**Need help?** Check the logs: `./dev-deploy.sh --logs` 