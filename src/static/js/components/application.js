import { ApiService } from '../services/api.js';
import { agentIcons, models, SOCKET_EVENTS } from '../utils/constants.js';
import { parseMentions, escapeHtml, formatTime, showToast, scrollToBottom, createLoadingIndicator } from '../utils/helpers.js';

/**
 * SwarmApp class for main application logic
 */
export class SwarmApp {
    constructor() {
        this.apiService = new ApiService();
        this.agents = [];
        this.currentAgent = null;
        this.selectedModel = models[0];
        this.socket = null;
        this.isStreaming = false;
        this.currentStreamingMessage = null;
        this.conversations = {};
        this.collaborativeResponses = new Map(); // Store responses by agent ID
        this.init();
    }

    async init() {
        try {
            await this.loadAgents();
            this.initializeSocket();
            this.setupEventListeners();
            this.renderModelDropdown();
            this.loadThemePreference();
            this.restoreConversations();
        } catch (error) {
            console.error('Initialization error:', error);
            showToast('Failed to initialize application', 'error');
        }
    }

    async loadAgents() {
        this.agents = await this.apiService.loadAgents();
        this.renderAgents();
    }

    renderAgents() {
        const agentGrid = document.getElementById('agentGrid');
        agentGrid.innerHTML = '';

        this.agents.forEach(agent => {
            const agentCard = document.createElement('div');
            agentCard.className = 'agent-card';
            agentCard.onclick = () => this.selectAgent(agent.id);
            agentCard.id = `agent-${agent.id}`;

            agentCard.innerHTML = `
                <div class="agent-icon">
                    ${agentIcons[agent.id] || agentIcons.general_agent}
                </div>
                <div class="agent-info">
                    <div class="agent-name">${agent.name}</div>
                    <div class="agent-description">${agent.description}</div>
                </div>
                <div class="agent-status-badge" id="status-${agent.id}"></div>
            `;

            agentGrid.appendChild(agentCard);
        });
    }

    selectAgent(agentId) {
        this.currentAgent = this.agents.find(agent => agent.id === agentId);
        document.getElementById('chatAgentName').textContent = this.currentAgent.name;
        document.querySelectorAll('.agent-card').forEach(card => card.classList.remove('active'));
        document.getElementById(`agent-${agentId}`).classList.add('active');
    }

    initializeSocket() {
        this.socket = io('/swarm', {
            transports: ['websocket', 'polling']
        });

        this.socket.on(SOCKET_EVENTS.CONNECT, () => {
            console.log('Connected');
        });

        this.socket.on(SOCKET_EVENTS.DISCONNECT, () => {
            console.log('Disconnected');
        });

        this.socket.on(SOCKET_EVENTS.RESPONSE_STREAM_START, (data) => {
            this.startStreamingResponse(data.agent_id);
        });

        this.socket.on(SOCKET_EVENTS.RESPONSE_STREAM_ERROR, (error) => {
            console.error('Stream error:', error);
        });

        this.socket.on(SOCKET_EVENTS.RESPONSE_STREAM_COMPLETE, (data) => {
            this.endStreamingResponse(data.agent_id);
        });

        this.socket.on(SOCKET_EVENTS.RESPONSE_STREAM_CHUNK, (chunk) => {
            this.appendStreamingChunk(chunk);
        });
    }

    setupEventListeners() {
        const chatInput = document.getElementById('chatInput');
        
        // Handle Enter key for message submission
        chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSubmitMessage();
            }
        });
        
        // Monitor input for @mentions and auto-resize
        chatInput.addEventListener('input', () => {
            this.checkForMentions();
            this.autoResizeTextarea();
        });
        
        // Send button click handler
        document.getElementById('sendButton').addEventListener('click', () => this.handleSubmitMessage());
        
        // Close mention suggestions when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#mentionSuggestions') && !e.target.closest('#chatInput')) {
                this.hideMentionSuggestions();
            }
        });
    }

    async handleSubmitMessage() {
        const chatInput = document.getElementById('chatInput');
        const message = chatInput.value.trim();

        if (!message) return;

        // Use regex /@([a-zA-Z0-9_]+)/g to collect agent IDs
        const mentionedAgents = parseMentions(message);
        
        // Add user message immediately
        this.addMessage(message, 'user');
        chatInput.value = '';
        
        // Show loading indicator
        this.showLoadingIndicator();

        try {
            if (mentionedAgents.length > 0) {
                // POST to /api/agents/collaborate with {message, mentioned_agents}
                const response = await this.apiService.sendCollaborativeMessage(
                    message, 
                    mentionedAgents, 
                    this.selectedModel.id
                );
                
                // Render each agent response in its own message bubble with agent badge
                await this.handleCollaborativeResponse(response);
            } else if (this.currentAgent) {
                // POST to /api/agents/<active>/chat
                const response = await this.apiService.sendAgentMessage(
                    this.currentAgent.id, 
                    message, 
                    this.selectedModel.id
                );
                
                // Handle single agent response
                await this.handleSingleAgentResponse(response, this.currentAgent.id);
            } else {
                showToast('Please select an agent first', 'warning');
            }
        } catch (error) {
            console.error('Error sending message:', error);
            showToast('Failed to send message', 'error');
        } finally {
            this.hideLoadingIndicator();
        }
    }

    addMessage(content, type) {
        const messagesContainer = document.getElementById('chatMessages');
        const messageElement = document.createElement('div');
        messageElement.className = `message ${type}`;

        if (type === 'user') {
            messageElement.innerHTML = `
                <div class="message-avatar user">U</div>
                <div class="message-content">
                    <div class="message-text">${escapeHtml(content)}</div>
                    <div class="message-time">${formatTime()}</div>
                </div>
            `;
        }

        messagesContainer.appendChild(messageElement);
        scrollToBottom(messagesContainer);
    }

    showLoadingIndicator() {
        document.querySelector('.loading-indicator').style.display = 'block';
    }

    hideLoadingIndicator() {
        document.querySelector('.loading-indicator').style.display = 'none';
    }

    startStreamingResponse(agentId) {
        this.isStreaming = true;
        alert(`Starting streaming from ${agentId}`);
    }

    endStreamingResponse(agentId) {
        this.isStreaming = false;
        alert(`Ending streaming for ${agentId}`);
    }

    appendStreamingChunk(chunk) {
        alert(`Received chunk: ${chunk}`);
    }

    /**
     * Handle collaborative response with multiple agents
     * @param {Object} response - API response from collaboration endpoint
     */
    async handleCollaborativeResponse(response) {
        if (response.success && response.data) {
            const { results } = response.data;
            
            // Render each agent response in its own message bubble with agent badge
            if (results && Array.isArray(results)) {
                for (const result of results) {
                    if (result.agent_id && result.response) {
                        this.addAgentMessage(result.response, result.agent_id);
                    }
                }
            } else if (response.data.response) {
                // Single collaborative response
                this.addAgentMessage(response.data.response, 'collaboration');
            }
        } else {
            showToast('Collaboration request failed', 'error');
        }
    }

    /**
     * Handle single agent response
     * @param {Object} response - API response from individual agent
     * @param {string} agentId - ID of the responding agent
     */
    async handleSingleAgentResponse(response, agentId) {
        if (response.success && response.data) {
            this.addAgentMessage(response.data.response, agentId);
        } else {
            showToast('Agent request failed', 'error');
        }
    }

    /**
     * Add agent message with proper badge and styling
     * @param {string} content - Message content
     * @param {string} agentId - Agent ID for styling and badge
     */
    addAgentMessage(content, agentId) {
        const messagesContainer = document.getElementById('chatMessages');
        const messageElement = document.createElement('div');
        messageElement.className = 'message agent';
        
        const agent = this.agents.find(a => a.id === agentId) || 
                     { id: agentId, name: agentId.replace(/_/g, ' ').toUpperCase() };
        
        const agentIcon = agentIcons[agentId] || agentIcons.general_agent;
        
        messageElement.innerHTML = `
            <div class="message-avatar agent">
                ${agentIcon}
            </div>
            <div class="message-content">
                <div class="agent-badge">
                    <span class="agent-badge-icon">${agentIcon}</span>
                    <span class="agent-badge-name">${agent.name}</span>
                </div>
                <div class="message-text">${escapeHtml(content)}</div>
                <div class="message-time">${formatTime()}</div>
            </div>
        `;
        
        messagesContainer.appendChild(messageElement);
        scrollToBottom(messagesContainer);
    }

    /**
     * Render model selection dropdown
     */
    renderModelDropdown() {
        const modelSelect = document.getElementById('modelSelect');
        if (modelSelect) {
            modelSelect.innerHTML = '';
            
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;
                option.textContent = model.name;
                option.selected = model.id === this.selectedModel.id;
                modelSelect.appendChild(option);
            });
            
            modelSelect.addEventListener('change', (e) => {
                this.selectedModel = models.find(m => m.id === e.target.value) || models[0];
            });
        }
    }

    /**
     * Load theme preference from localStorage
     */
    loadThemePreference() {
        const savedTheme = localStorage.getItem('swarm_theme');
        if (savedTheme === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
        }
    }

    /**
     * Restore conversations from localStorage
     */
    restoreConversations() {
        this.agents.forEach(agent => {
            const saved = localStorage.getItem(`swarm_conversation_${agent.id}`);
            if (saved) {
                try {
                    this.conversations[agent.id] = JSON.parse(saved);
                } catch (error) {
                    console.error('Error parsing saved conversation:', error);
                }
            }
        });
    }

    /**
     * Check for @mentions in input and show suggestions
     */
    checkForMentions() {
        const input = document.getElementById('chatInput');
        const text = input.value;
        const lastAtIndex = text.lastIndexOf('@');
        
        if (lastAtIndex >= 0 && (lastAtIndex === text.length - 1 || 
            text.substring(lastAtIndex).match(/^@\w*$/))) {
            this.showMentionSuggestions(text.substring(lastAtIndex + 1));
        } else {
            this.hideMentionSuggestions();
        }
    }

    /**
     * Show mention suggestions dropdown
     * @param {string} query - Current query string
     */
    showMentionSuggestions(query) {
        const suggestions = document.getElementById('mentionSuggestions');
        if (!suggestions) return;
        
        suggestions.innerHTML = '';
        
        const filtered = this.agents.filter(agent => 
            agent.name.toLowerCase().includes(query.toLowerCase()) ||
            agent.id.toLowerCase().includes(query.toLowerCase())
        );
        
        filtered.forEach(agent => {
            const option = document.createElement('div');
            option.className = 'mention-option';
            option.innerHTML = `
                <div class="mention-option-icon">
                    ${agentIcons[agent.id] || agentIcons.general_agent}
                </div>
                <div class="mention-option-info">
                    <div class="mention-option-name">${agent.name}</div>
                    <div class="mention-option-description">${agent.description}</div>
                </div>
            `;
            option.onclick = () => this.insertMention(agent);
            suggestions.appendChild(option);
        });
        
        if (filtered.length > 0) {
            suggestions.classList.add('show');
        }
    }

    /**
     * Hide mention suggestions dropdown
     */
    hideMentionSuggestions() {
        const suggestions = document.getElementById('mentionSuggestions');
        if (suggestions) {
            suggestions.classList.remove('show');
        }
    }

    /**
     * Insert selected mention into input
     * @param {Object} agent - Selected agent object
     */
    insertMention(agent) {
        const input = document.getElementById('chatInput');
        const text = input.value;
        const lastAtIndex = text.lastIndexOf('@');
        
        input.value = text.substring(0, lastAtIndex) + `@${agent.id} `;
        this.hideMentionSuggestions();
        input.focus();
        this.autoResizeTextarea();
    }

    /**
     * Auto-resize textarea based on content
     */
    autoResizeTextarea() {
        const textarea = document.getElementById('chatInput');
        if (textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
        }
    }
}

// Initialize the app and expose it globally
window.onload = () => {
    const swarmApp = new SwarmApp();
    window.swarmAppInstance = swarmApp;
    window.app = swarmApp; // Legacy alias for quick start cards
};

