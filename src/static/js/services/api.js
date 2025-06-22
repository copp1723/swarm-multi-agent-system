import { API_ENDPOINTS } from '../utils/constants.js';
import { showToast } from '../utils/helpers.js';

/**
 * API service class for handling backend communication
 */
export class ApiService {
    constructor() {
        this.baseUrl = '';
    }

    /**
     * Generic fetch wrapper with error handling
     * @param {string} url - API endpoint URL
     * @param {Object} options - Fetch options
     * @returns {Promise<Object>} - Response data
     */
    async fetchWithErrorHandling(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            showToast(`API Error: ${error.message}`, 'error');
            throw error;
        }
    }

    /**
     * Load available agents from the backend
     * @returns {Promise<Object[]>} - Array of agent objects
     */
    async loadAgents() {
        const data = await this.fetchWithErrorHandling(API_ENDPOINTS.AGENTS);
        
        if (data.success && data.data.agents) {
            return Object.entries(data.data.agents).map(([id, agent]) => ({
                id: id,
                name: agent.name,
                description: agent.description,
                capabilities: agent.capabilities || [],
                status: 'idle'
            }));
        }
        
        throw new Error('Invalid agents response format');
    }

    /**
     * Send message to collaboration endpoint
     * @param {string} message - The message content
     * @param {string[]} mentionedAgents - Array of mentioned agent IDs
     * @param {string} model - Model ID to use
     * @returns {Promise<Object>} - Response from collaboration endpoint
     */
    async sendCollaborativeMessage(message, mentionedAgents, model) {
        const payload = {
            message: message,
            mentioned_agents: mentionedAgents,
            model: model,
            stream_enabled: false // For collaborative messages, we'll handle streaming differently
        };

        return await this.fetchWithErrorHandling(API_ENDPOINTS.COLLABORATE, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    /**
     * Send message to individual agent endpoint
     * @param {string} agentId - Agent ID to send message to
     * @param {string} message - The message content
     * @param {string} model - Model ID to use
     * @returns {Promise<Object>} - Response from agent endpoint
     */
    async sendAgentMessage(agentId, message, model) {
        const payload = {
            content: message,
            model: model,
            stream_enabled: false // We'll use WebSocket for streaming
        };

        return await this.fetchWithErrorHandling(API_ENDPOINTS.CHAT(agentId), {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    /**
     * Check system health and connectivity
     * @returns {Promise<Object>} - System status
     */
    async checkSystemHealth() {
        try {
            return await this.fetchWithErrorHandling('/api/health');
        } catch (error) {
            return { status: 'error', message: error.message };
        }
    }
}
