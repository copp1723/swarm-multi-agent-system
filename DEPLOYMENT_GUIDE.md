# Swarm Multi-Agent System - Render Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the Swarm Multi-Agent System to Render.com with PostgreSQL database, Redis cache, and all service integrations.

## Prerequisites

- Render.com account
- GitHub repository with the code
- API keys for OpenRouter, Supermemory, and Mailgun
- Domain configured for Mailgun (if using email features)

## Deployment Steps

### Step 1: Prepare Repository

1. **Push code to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit - Swarm Multi-Agent System"
   git remote add origin https://github.com/yourusername/swarm-agents.git
   git push -u origin main
   ```

2. **Verify required files are present:**
   - `requirements.txt`
   - `Dockerfile`
   - `render.yaml`
   - `.env.production` (template)
   - `migrate_db.py`

### Step 2: Create Render Services

#### 2.1 Create PostgreSQL Database

1. Go to Render Dashboard → New → PostgreSQL
2. Configure:
   - **Name:** `swarm-agents-db`
   - **Database Name:** `swarm_agents`
   - **User:** `swarm_user`
   - **Region:** Oregon (US West)
   - **Plan:** Starter ($7/month)

3. **Save the connection details** (Render will provide):
   - Internal Database URL
   - External Database URL
   - Connection parameters

#### 2.2 Create Redis Instance

1. Go to Render Dashboard → New → Redis
2. Configure:
   - **Name:** `swarm-agents-redis`
   - **Region:** Oregon (US West)
   - **Plan:** Starter ($7/month)

3. **Save the Redis URL** for later use

#### 2.3 Create Web Service

1. Go to Render Dashboard → New → Web Service
2. Connect your GitHub repository
3. Configure:
   - **Name:** `swarm-agents-web`
   - **Environment:** Python 3
   - **Region:** Oregon (US West)
   - **Branch:** main
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 src.main:app`

### Step 3: Configure Environment Variables

In the Render Web Service settings, add these environment variables:

#### Application Configuration
```
SECRET_KEY=your-production-secret-key-here-make-it-long-and-random
DEBUG=False
HOST=0.0.0.0
PORT=10000
```

#### Database Configuration
```
DATABASE_URL=[Use the Internal Database URL from Step 2.1]
REDIS_URL=[Use the Redis URL from Step 2.2]
```

#### API Keys
```
OPENROUTER_API_KEY=your-openrouter-api-key-here
SUPERMEMORY_API_KEY=your-supermemory-api-key-here
MAILGUN_API_KEY=your-mailgun-api-key-here
MAILGUN_DOMAIN=your-mailgun-domain-here
MAILGUN_WEBHOOK_SIGNING_KEY=your-mailgun-webhook-key-here
```

#### Service Configuration
```
API_TIMEOUT=30
MAX_RETRIES=3
RATE_LIMIT_PER_MINUTE=60
MAX_CONVERSATION_CONTEXT=20
```

### Step 4: Configure Health Checks

1. In Web Service settings, set:
   - **Health Check Path:** `/health`
   - **Health Check Interval:** 30 seconds

### Step 5: Deploy and Test

1. **Trigger deployment** by pushing to GitHub or manually in Render
2. **Monitor deployment logs** for any issues
3. **Test the deployment:**
   ```bash
   curl https://your-app-name.onrender.com/health
   ```

### Step 6: Database Migration (if needed)

If you have existing data to migrate:

1. **Connect to your Render PostgreSQL:**
   ```bash
   psql [External Database URL from Step 2.1]
   ```

2. **Run migration script locally:**
   ```bash
   DATABASE_URL=[External Database URL] python migrate_db.py
   ```

### Step 7: Configure Custom Domain (Optional)

1. In Render Web Service settings → Custom Domains
2. Add your domain (e.g., `swarm.yourdomain.com`)
3. Configure DNS records as instructed by Render
4. SSL certificate will be automatically provisioned

### Step 8: Configure Mailgun Webhooks

1. In Mailgun dashboard, go to Webhooks
2. Add webhook URL: `https://your-app-name.onrender.com/api/email/webhooks/mailgun`
3. Select events: delivered, bounced, failed, complained
4. Use the webhook signing key from your environment variables

## Monitoring and Maintenance

### Health Monitoring

The application provides several health check endpoints:

- **Main health:** `GET /health`
- **MCP filesystem:** `GET /api/mcp/health`
- **Email service:** `GET /api/email/health`
- **Memory service:** `GET /api/memory/health`

### Logs and Debugging

1. **View logs in Render dashboard:** Services → Your Service → Logs
2. **Log levels:** INFO (production), DEBUG (development)
3. **Structured logging** for better parsing and analysis

### Performance Monitoring

Monitor these metrics in Render dashboard:
- **Response times:** Should be < 2 seconds
- **Memory usage:** Should be < 80%
- **CPU usage:** Should be < 70%
- **Error rates:** Should be < 1%

### Scaling

The service is configured to auto-scale based on:
- **CPU usage > 70%** for 5 minutes
- **Memory usage > 80%** for 5 minutes
- **Response time > 2 seconds** for 10 requests

## Cost Estimation

### Monthly Costs (Starter Plans)
- **Web Service:** $7/month
- **PostgreSQL:** $7/month
- **Redis:** $7/month
- **Total:** ~$21/month

### Scaling Costs
- **Standard Web Service:** $25/month (more CPU/memory)
- **Pro PostgreSQL:** $20/month (more storage/connections)
- **Pro Redis:** $15/month (more memory)

## Troubleshooting

### Common Issues

1. **Build failures:**
   - Check `requirements.txt` for correct versions
   - Verify Python version compatibility
   - Check build logs for specific errors

2. **Database connection issues:**
   - Verify `DATABASE_URL` is correctly set
   - Check database service status
   - Ensure database is in same region

3. **API integration failures:**
   - Verify all API keys are correctly set
   - Check API service status
   - Review error logs for specific issues

4. **Health check failures:**
   - Verify health check path is `/health`
   - Check application startup logs
   - Ensure all services are initialized

### Support Resources

- **Render Documentation:** https://render.com/docs
- **Render Community:** https://community.render.com
- **Application Logs:** Available in Render dashboard
- **Database Logs:** Available in PostgreSQL service logs

## Security Considerations

1. **Environment Variables:** Never commit API keys to repository
2. **Database Access:** Use internal URLs when possible
3. **HTTPS:** Automatically enabled by Render
4. **CORS:** Configured for specific domains only
5. **Rate Limiting:** Implemented to prevent abuse

## Backup and Recovery

1. **Database Backups:** Automatic daily backups by Render
2. **Point-in-time Recovery:** Available for PostgreSQL
3. **Code Backups:** Stored in GitHub repository
4. **Configuration Backups:** Document all environment variables

This deployment guide ensures a production-ready, scalable, and maintainable deployment of your Swarm Multi-Agent System on Render.com.

