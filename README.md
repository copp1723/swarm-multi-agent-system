# Swarm Multi-Agent System v2.0

A production-ready multi-agent collaboration platform with AI-powered agents, persistent memory, filesystem access, and email automation.

## 🚀 Features

### Core Capabilities
- **5 Specialized AI Agents:** Email, Calendar, Code, Debug, and General agents
- **20+ AI Models:** Access to GPT-4, Claude, DeepSeek, and more via OpenRouter
- **Persistent Memory:** Conversation history and context via Supermemory
- **Filesystem Access:** Secure file operations via MCP protocol
- **Email Automation:** AI-powered email composition via Mailgun
- **Real-time Collaboration:** @mention system for multi-agent workflows

### Technical Features
- **Production-Ready:** Designed for Render.com deployment
- **PostgreSQL Database:** Scalable data storage
- **Redis Caching:** High-performance session management
- **Comprehensive API:** 25+ endpoints for all functionality
- **Health Monitoring:** Built-in health checks and monitoring
- **Security:** Rate limiting, input validation, and secure authentication

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend UI   │    │  Flask Backend  │    │   External APIs │
│                 │    │                 │    │                 │
│ • Agent Cards   │◄──►│ • Agent Service │◄──►│ • OpenRouter    │
│ • Chat Interface│    │ • Memory Service│    │ • Supermemory   │
│ • Model Select  │    │ • MCP Filesystem│    │ • Mailgun       │
└─────────────────┘    │ • Email Service │    └─────────────────┘
                       └─────────────────┘
                              │
                       ┌─────────────────┐
                       │   Data Layer    │
                       │                 │
                       │ • PostgreSQL    │
                       │ • Redis Cache   │
                       │ • File Storage  │
                       └─────────────────┘
```

## 🛠️ Installation

### Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/swarm-agents.git
   cd swarm-agents
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run the application:**
   ```bash
   python src/main.py
   ```

6. **Access the application:**
   Open http://localhost:5002 in your browser

### Production Deployment

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for complete Render.com deployment instructions.

## 🔧 Configuration

### Required Environment Variables

```bash
# API Keys
OPENROUTER_API_KEY=your-openrouter-key
SUPERMEMORY_API_KEY=your-supermemory-key
MAILGUN_API_KEY=your-mailgun-key
MAILGUN_DOMAIN=your-domain.com
MAILGUN_WEBHOOK_SIGNING_KEY=your-webhook-key

# Application
SECRET_KEY=your-secret-key
DEBUG=False
HOST=0.0.0.0
PORT=10000

# Database (Production)
DATABASE_URL=postgresql://user:pass@host:port/db
REDIS_URL=redis://host:port
```

### Optional Configuration

```bash
# Service Limits
API_TIMEOUT=30
MAX_RETRIES=3
RATE_LIMIT_PER_MINUTE=60
MAX_CONVERSATION_CONTEXT=20

# Security
CORS_ORIGINS=https://yourdomain.com
TRUSTED_HOSTS=yourdomain.com
```

## 📚 API Documentation

### Agent Endpoints

- `GET /api/agents` - List all available agents
- `POST /api/agents/chat` - Send message to agent
- `GET /api/agents/models` - Get available AI models
- `POST /api/agents/suggest` - Get agent suggestions

### Memory Endpoints

- `POST /api/memory/store` - Store conversation
- `GET /api/memory/retrieve` - Retrieve conversation history
- `POST /api/memory/search` - Search memory
- `DELETE /api/memory/clear` - Clear agent memory

### Filesystem Endpoints

- `POST /api/mcp/files/read` - Read file content
- `POST /api/mcp/files/write` - Write file content
- `POST /api/mcp/files/list` - List directory contents
- `POST /api/mcp/files/delete` - Delete file/directory
- `GET /api/mcp/workspace/stats` - Get workspace statistics

### Email Endpoints

- `POST /api/email/send` - Send email
- `POST /api/email/compose-ai` - AI-compose email
- `POST /api/email/send-template` - Send template email
- `GET /api/email/templates` - Get email templates
- `GET /api/email/stats` - Get domain statistics

### Health Endpoints

- `GET /health` - Main application health
- `GET /api/mcp/health` - Filesystem service health
- `GET /api/email/health` - Email service health
- `GET /api/memory/health` - Memory service health

## 🤖 Agent Capabilities

### Email Agent
- AI-powered email composition
- Template management
- Delivery tracking
- Webhook handling

### Calendar Agent
- Schedule management
- Meeting coordination
- Reminder systems
- Time zone handling

### Code Agent
- Code analysis and generation
- File operations
- Debugging assistance
- Documentation generation

### Debug Agent
- Error analysis
- Log file processing
- System diagnostics
- Performance monitoring

### General Agent
- Task coordination
- Information synthesis
- Multi-agent orchestration
- General assistance

## 🔒 Security

### Authentication & Authorization
- Secure API key management
- Environment variable protection
- Rate limiting per endpoint
- Input validation and sanitization

### Data Protection
- Encrypted data transmission (HTTPS)
- Secure database connections
- File access sandboxing
- Audit logging for all operations

### Infrastructure Security
- Container isolation
- Network security groups
- Regular security updates
- Monitoring and alerting

## 📊 Monitoring

### Health Checks
- Application health monitoring
- Service dependency checks
- Database connectivity
- External API availability

### Performance Metrics
- Response time tracking
- Memory and CPU usage
- Database query performance
- API call success rates

### Logging
- Structured JSON logging
- Error tracking and alerting
- Audit trail for all operations
- Performance profiling

## 🚀 Deployment

### Render.com (Recommended)
- **Cost:** ~$21/month (starter plans)
- **Features:** Auto-scaling, SSL, monitoring
- **Setup Time:** 2-3 hours
- **Maintenance:** Minimal

### Docker Deployment
```bash
# Build image
docker build -t swarm-agents .

# Run container
docker run -p 10000:10000 --env-file .env swarm-agents
```

### Manual Deployment
```bash
# Install dependencies
pip install -r requirements.txt

# Run with Gunicorn
gunicorn --bind 0.0.0.0:10000 --workers 2 src.main:app
```

## 🧪 Testing

### Run Tests
```bash
# Install test dependencies
pip install pytest pytest-flask

# Run all tests
pytest

# Run with coverage
pytest --cov=src
```

### Manual Testing
```bash
# Test health endpoint
curl http://localhost:5002/health

# Test agent chat
curl -X POST http://localhost:5002/api/agents/chat \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "general", "message": "Hello", "model": "gpt-4"}'
```

## 📈 Performance

### Benchmarks
- **Response Time:** < 2 seconds average
- **Throughput:** 100+ requests/minute
- **Memory Usage:** < 512MB typical
- **CPU Usage:** < 50% under normal load

### Optimization
- Redis caching for frequent queries
- Database connection pooling
- Async processing for heavy operations
- CDN for static assets

## 🤝 Contributing

### Development Setup
1. Fork the repository
2. Create feature branch
3. Make changes with tests
4. Submit pull request

### Code Standards
- Python 3.11+ compatibility
- Type hints for all functions
- Comprehensive error handling
- Unit tests for new features

### Documentation
- Update README for new features
- Add API documentation
- Include deployment notes
- Provide usage examples

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Documentation
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [API Documentation](API_DOCS.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)

### Community
- GitHub Issues for bug reports
- GitHub Discussions for questions
- Email support: support@yourdomain.com

### Professional Support
- Custom deployment assistance
- Feature development
- Performance optimization
- Training and consultation

## 🎯 Roadmap

### Version 2.1 (Next Release)
- [ ] Advanced agent collaboration workflows
- [ ] Real-time WebSocket communication
- [ ] Enhanced UI with drag-and-drop
- [ ] Mobile application support

### Version 2.2 (Future)
- [ ] Custom agent creation
- [ ] Workflow automation builder
- [ ] Advanced analytics dashboard
- [ ] Enterprise authentication (SSO)

### Version 3.0 (Long-term)
- [ ] Multi-tenant architecture
- [ ] Marketplace for custom agents
- [ ] Advanced AI model fine-tuning
- [ ] Enterprise compliance features

---

**Built with ❤️ for the future of AI collaboration**

