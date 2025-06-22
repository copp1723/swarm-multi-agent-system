// Professional icon mappings
export const agentIcons = {
    comms_agent: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path><line x1="9" y1="10" x2="15" y2="10"></line><line x1="9" y1="14" x2="15" y2="14"></line></svg>',
    email_agent: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>',
    calendar_agent: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>',
    code_agent: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>',
    debug_agent: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>',
    general_agent: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M8 14s1.5 2 4 2 4-2 4-2"></path><line x1="9" y1="9" x2="9.01" y2="9"></line><line x1="15" y1="9" x2="15.01" y2="9"></line></svg>'
};

export const models = [
    { id: 'openai/gpt-4o', name: 'GPT-4o', description: 'Most capable OpenAI model' },
    { id: 'anthropic/claude-3.5-sonnet', name: 'Claude 3.5 Sonnet', description: 'Advanced reasoning and analysis' },
    { id: 'deepseek/deepseek-chat', name: 'DeepSeek Chat', description: 'Efficient and capable' },
    { id: 'google/gemini-pro', name: 'Gemini Pro', description: 'Google\'s advanced model' },
    { id: 'openai/gpt-4o-mini', name: 'GPT-4o Mini', description: 'Fast and efficient' },
    { id: 'meta-llama/llama-3.1-70b-instruct', name: 'Llama 3.1 70B', description: 'Open source powerhouse' }
];

// @mention regex pattern for collecting agent IDs
export const MENTION_REGEX = /@([a-zA-Z0-9_]+)/g;

// API endpoints
export const API_ENDPOINTS = {
    AGENTS: '/api/agents/',
    COLLABORATE: '/api/agents/collaborate',
    CHAT: (agentId) => `/api/agents/${agentId}/chat`
};

// WebSocket events
export const SOCKET_EVENTS = {
    CONNECT: 'connect',
    DISCONNECT: 'disconnect',
    SEND_MESSAGE: 'send_message',
    RESPONSE_STREAM_START: 'response_stream_start',
    RESPONSE_STREAM_CHUNK: 'response_stream_chunk',
    RESPONSE_STREAM_COMPLETE: 'response_stream_complete',
    RESPONSE_STREAM_ERROR: 'response_stream_error'
};
