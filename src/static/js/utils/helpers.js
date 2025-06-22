// Helper utility functions for the Swarm application

/**
 * Parse @mentions from a message and return mentioned agent IDs
 * @param {string} message - The message to parse
 * @returns {string[]} - Array of mentioned agent IDs
 */
export function parseMentions(message) {
    const mentionRegex = /@([a-zA-Z0-9_]+)/g;
    const mentions = [];
    let match;
    
    while ((match = mentionRegex.exec(message)) !== null) {
        mentions.push(match[1]);
    }
    
    return [...new Set(mentions)]; // Remove duplicates
}

/**
 * Escape HTML entities for safe rendering
 * @param {string} text - Text to escape
 * @returns {string} - HTML-escaped text
 */
export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format timestamp for display
 * @param {Date} date - Date to format
 * @returns {string} - Formatted time string
 */
export function formatTime(date = new Date()) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Generate unique ID for DOM elements
 * @param {string} prefix - Prefix for the ID
 * @returns {string} - Unique ID
 */
export function generateId(prefix = 'id') {
    return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Debounce function to limit function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} - Debounced function
 */
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Show toast notification
 * @param {string} message - Message to display
 * @param {string} type - Type of notification (success, error, warning, info)
 * @param {number} duration - Duration in milliseconds
 */
export function showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <span class="toast-message">${escapeHtml(message)}</span>
            <button class="toast-close" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
    `;
    
    // Add to DOM
    const container = getOrCreateToastContainer();
    container.appendChild(toast);
    
    // Animate in
    toast.style.transform = 'translateX(100%)';
    toast.style.opacity = '0';
    setTimeout(() => {
        toast.style.transform = 'translateX(0)';
        toast.style.opacity = '1';
    }, 10);
    
    // Auto remove
    setTimeout(() => {
        toast.style.transform = 'translateX(100%)';
        toast.style.opacity = '0';
        setTimeout(() => {
            if (toast.parentElement) {
                toast.parentElement.removeChild(toast);
            }
        }, 300);
    }, duration);
}

/**
 * Get or create toast container
 * @returns {HTMLElement} - Toast container element
 */
function getOrCreateToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    return container;
}

/**
 * Validate agent ID format
 * @param {string} agentId - Agent ID to validate
 * @returns {boolean} - Whether the agent ID is valid
 */
export function isValidAgentId(agentId) {
    return /^[a-zA-Z0-9_]+$/.test(agentId);
}

/**
 * Create loading indicator element
 * @returns {HTMLElement} - Loading indicator element
 */
export function createLoadingIndicator() {
    const loading = document.createElement('div');
    loading.className = 'loading-indicator';
    loading.innerHTML = `
        <div class="loading-dots">
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
        </div>
    `;
    return loading;
}

/**
 * Animate element scroll to bottom
 * @param {HTMLElement} element - Element to scroll
 * @param {boolean} smooth - Whether to use smooth scrolling
 */
export function scrollToBottom(element, smooth = true) {
    if (smooth) {
        element.scrollTo({
            top: element.scrollHeight,
            behavior: 'smooth'
        });
    } else {
        element.scrollTop = element.scrollHeight;
    }
}
