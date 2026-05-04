document.addEventListener('DOMContentLoaded', () => {
    const attachButton = document.getElementById('attachButton');
    const fileInput = document.getElementById('fileInput');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const messagesContainer = document.getElementById('messagesContainer');
    const filePreviewContainer = document.getElementById('filePreviewContainer');

    let selectedFiles = [];

    // Trigger file selection
    attachButton.addEventListener('click', () => {
        fileInput.click();
    });

    // Handle file selection
    fileInput.addEventListener('change', (e) => {
        const files = Array.from(e.target.files);
        files.forEach(file => {
            if (!selectedFiles.find(f => f.name === file.name)) {
                selectedFiles.push(file);
                addFilePreview(file);
            }
        });
        updatePreviewContainerVisibility();
        fileInput.value = '';
    });

    // Add visual preview for file
    function addFilePreview(file) {
        const fileCard = document.createElement('div');
        fileCard.className = 'file-preview-card';
        fileCard.dataset.filename = file.name;

        let iconHtml = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--primary-color)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>`;

        let displayName = file.name;
        if (displayName.length > 15) {
            displayName = displayName.substring(0, 12) + '...';
        }

        fileCard.innerHTML = `
            ${iconHtml}
            <span style="color: var(--text-primary); font-size: 0.8rem;">${displayName}</span>
            <button class="remove-btn" title="Remove">✕</button>
        `;

        const removeBtn = fileCard.querySelector('.remove-btn');
        removeBtn.addEventListener('click', () => {
            selectedFiles = selectedFiles.filter(f => f.name !== file.name);
            fileCard.remove();
            updatePreviewContainerVisibility();
        });

        filePreviewContainer.appendChild(fileCard);
    }

    function updatePreviewContainerVisibility() {
        filePreviewContainer.style.display = selectedFiles.length > 0 ? 'flex' : 'none';
    }

    // Handle Send
    async function sendMessage() {
        const text = messageInput.value.trim();
        const hasFiles = selectedFiles.length > 0;

        if (!text && !hasFiles) return;

        // 1. Render User Message
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user-message';
        messageDiv.innerHTML = `
            <div class="avatar user-avatar">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
            <div class="message-content">
                ${text}
            </div>
        `;
        messagesContainer.appendChild(messageDiv);

        // Clear UI Inputs
        messageInput.value = '';
        selectedFiles = [];
        filePreviewContainer.innerHTML = '';
        updatePreviewContainerVisibility();
        scrollToBottom();

        // 2. Render "Typing" Indicator
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message bot-message';
        typingDiv.id = 'typingIndicator';
        typingDiv.innerHTML = `
            <div class="avatar bot-avatar">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
            </div>
            <div class="message-content" style="opacity: 0.7; font-style: italic;">
                AI is thinking and researching...
            </div>
        `;
        messagesContainer.appendChild(typingDiv);
        scrollToBottom();

        // 3. Call the Backend API
        try {
            const response = await fetch('http://127.0.0.1:8001/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: text })
            });
            
            const data = await response.json();
            
            // Remove typing indicator
            document.getElementById('typingIndicator').remove();

            // 4. Render Bot Response
            const botMessageDiv = document.createElement('div');
            botMessageDiv.className = 'message bot-message';
            
            // Convert standard markdown newlines to HTML breaks
            const formattedText = data.response.replace(/\n/g, '<br>');

            botMessageDiv.innerHTML = `
                <div class="avatar bot-avatar">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
                </div>
                <div class="message-content">
                    ${formattedText}
                </div>
            `;
            messagesContainer.appendChild(botMessageDiv);
            scrollToBottom();

        } catch (error) {
            document.getElementById('typingIndicator').remove();
            alert("Connection Error. Make sure bridge_api.py is running on port 8001!");
        }
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
});