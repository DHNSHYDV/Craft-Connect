document.addEventListener('DOMContentLoaded', () => {
    // Mobile Menu Toggle
    const menuToggle = document.querySelector('.mobile-menu-toggle');
    const nav = document.querySelector('.main-nav');

    if (menuToggle) {
        menuToggle.addEventListener('click', () => {
            nav.classList.toggle('active');
            menuToggle.classList.toggle('active');
        });
    }

    // Smooth Scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Intersection Observer for fade-in animations
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, {
        threshold: 0.1
    });

    document.querySelectorAll('.animate-on-scroll').forEach((el) => {
        observer.observe(el);
    });

    // Profile Dropdown Toggle
    const profileMenu = document.querySelector('.profile-menu');
    const profileIcon = document.querySelector('.profile-icon');

    if (profileIcon) {
        profileIcon.addEventListener('click', (e) => {
            e.stopPropagation();
            profileMenu.classList.toggle('active');
        });

        document.addEventListener('click', (e) => {
            if (profileMenu && !profileMenu.contains(e.target)) {
                profileMenu.classList.remove('active');
            }
        });
    }

    // Quantity Selector (generic .quantity-selector)
    const quantitySelector = document.querySelector('.quantity-selector');
    if (quantitySelector) {
        const input = quantitySelector.querySelector('input');
        const minusBtn = quantitySelector.querySelector('button:first-child');
        const plusBtn = quantitySelector.querySelector('button:last-child');

        if (input && minusBtn && plusBtn) {
            minusBtn.addEventListener('click', () => {
                let val = parseInt(input.value) || 1;
                if (val > 1) input.value = val - 1;
            });
            plusBtn.addEventListener('click', () => {
                let val = parseInt(input.value) || 1;
                if (val < 10) input.value = val + 1;
            });
        }
    }

    // PDP Quantity Selector (.pdp-count-selector on product detail page)
    const pdpQtyInput = document.getElementById('pdpQty');
    const qtyMinus = document.getElementById('qtyMinus');
    const qtyPlus = document.getElementById('qtyPlus');
    if (pdpQtyInput && qtyMinus && qtyPlus) {
        qtyMinus.addEventListener('click', () => {
            let val = parseInt(pdpQtyInput.value) || 1;
            if (val > 1) pdpQtyInput.value = val - 1;
        });
        qtyPlus.addEventListener('click', () => {
            let val = parseInt(pdpQtyInput.value) || 1;
            if (val < 10) pdpQtyInput.value = val + 1;
        });
    }

    // Chatbot Widget Logic
    const chatFab = document.getElementById('chatFab');
    const chatWindow = document.getElementById('chatWindow');
    const closeChat = document.getElementById('closeChat');
    const chatInput = document.querySelector('.chat-input-area input');
    const sendBtn = document.querySelector('.chat-input-area button');
    const chatBody = document.getElementById('chatBody');
    const optionBtns = document.querySelectorAll('.chat-option-btn');

    if (chatFab && chatWindow && closeChat) {
        // Enable input
        if (chatInput) chatInput.disabled = false;
        if (sendBtn) sendBtn.disabled = false;

        function toggleChat() {
            chatWindow.classList.toggle('active');
            if (chatWindow.classList.contains('active') && chatInput) {
                chatInput.focus();
            }
        }

        chatFab.addEventListener('click', toggleChat);
        closeChat.addEventListener('click', toggleChat);

        // Chat Logic
        function addMessage(text, isUser = false) {
            const msgDiv = document.createElement('div');
            msgDiv.classList.add('message');
            msgDiv.classList.add(isUser ? 'user-message' : 'bot-message');
            msgDiv.textContent = text;
            chatBody.insertBefore(msgDiv, chatBody.querySelector('.chat-options')); // Insert before options or at end if options moved
            // Better: just append to chatBody, but keep options at bottom? 
            // Actually, usually options scroll up. Let's append to chatBody.
            // But we have options in the HTML. Let's re-structure: 
            // We'll insert before the options div if it exists, or just append.
            // Simplified: Append to chatBody.
            chatBody.appendChild(msgDiv);
            chatBody.scrollTop = chatBody.scrollHeight;
        }

        function getBotResponse(input) {
            const lowerInput = input.toLowerCase();
            if (lowerInput.includes('hello') || lowerInput.includes('hi')) return "Namasate! How can I help you explore Indian crafts?";
            if (lowerInput.includes('track') || lowerInput.includes('order')) return "Please provide your Order ID (e.g., #12345) to track your shipment.";
            if (lowerInput.includes('return') || lowerInput.includes('refund')) return "We accept returns within 7 days of delivery for damaged items. Please visit our Returns page.";
            if (lowerInput.includes('price') || lowerInput.includes('cost')) return "Prices vary by artist and craft. You can filter products by price on the Products page.";
            if (lowerInput.includes('shipping') || lowerInput.includes('delivery')) return "We ship across India! Delivery usually takes 5-7 business days.";
            if (lowerInput.includes('craft') || lowerInput.includes('art')) return "We feature 10+ authentic Indian art forms like Madhubani, Warli, and Blue Pottery.";
            return "I'm still learning! You can browse our Products section or contact support@deshkehaath.in.";
        }

        function handleSend() {
            const text = chatInput.value.trim();
            if (text) {
                addMessage(text, true);
                chatInput.value = '';

                // Simulate typing delay
                setTimeout(() => {
                    const response = getBotResponse(text);
                    addMessage(response, false);
                }, 1000); // 1 second delay
            }
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', handleSend);
        }

        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') handleSend();
            });
        }

        // Handle Option Buttons
        optionBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const text = btn.textContent;
                addMessage(text, true);
                setTimeout(() => {
                    const response = getBotResponse(text);
                    addMessage(response, false);
                }, 800);
            });
        });
    }

    // Dark Mode Toggle
    const themeToggle = document.querySelector('.theme-toggle');
    const body = document.body;
    const sunIcon = document.querySelector('.sun-icon');
    const moonIcon = document.querySelector('.moon-icon');

    // Check local storage
    if (localStorage.getItem('theme') === 'dark') {
        body.classList.add('dark-mode');
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'block';
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            body.classList.toggle('dark-mode');

            if (body.classList.contains('dark-mode')) {
                localStorage.setItem('theme', 'dark');
                sunIcon.style.display = 'none';
                moonIcon.style.display = 'block';
            } else {
                localStorage.setItem('theme', 'light');
                sunIcon.style.display = 'block';
                moonIcon.style.display = 'none';
            }
        });
    }

    // --- CART LOGIC ---
    window.updateCartBadge = function () {
        const cart = JSON.parse(localStorage.getItem('cart') || '[]');
        const count = cart.reduce((total, item) => total + (item.quantity || 1), 0);
        const badges = document.querySelectorAll('.cart-count');
        badges.forEach(badge => {
            badge.textContent = count;
            badge.style.display = count > 0 ? 'flex' : 'none';
        });
    };

    window.addToCart = function (product) {
        let cart = JSON.parse(localStorage.getItem('cart') || '[]');
        const existingItem = cart.find(item => item.id === product.id);

        if (existingItem) {
            existingItem.quantity += (product.quantity || 1);
        } else {
            cart.push({
                id: product.id,
                name: product.name,
                price: product.price,
                image: product.image,
                state: product.state,
                quantity: (product.quantity || 1)
            });
        }

        localStorage.setItem('cart', JSON.stringify(cart));
        window.updateCartBadge();

        // Visual feedback
        const btn = event.target.closest('button');
        if (btn) {
            const originalContent = btn.innerHTML;
            btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
            const originalBg = btn.style.background;
            btn.style.background = '#388e3c';
            btn.style.borderColor = '#388e3c';
            btn.style.color = 'white';
            setTimeout(() => {
                btn.innerHTML = originalContent;
                btn.style.background = originalBg;
                btn.style.borderColor = '';
                btn.style.color = '';
            }, 1000);
        }
    };

    // Global listener for generic 'add-to-cart-btn' (e.g. from grid)
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.add-to-cart-btn');
        if (btn) {
            e.preventDefault();
            const productData = {
                id: parseInt(btn.dataset.id),
                name: btn.dataset.name,
                price: parseInt(btn.dataset.price),
                image: btn.dataset.image,
                state: btn.dataset.state,
                quantity: 1
            };
            window.addToCart(productData);
        }
    });

    // Specific listener for PDP 'Add to Cart'
    const pdpAddToCartBtn = document.querySelector('.btn-primary[onclick^="addToCart"]');
    // Note: I'll remove the inline onclick later, but for now let's handle the PDP quantity selector
    const pdpBuyNowBtn = document.querySelector('.btn-secondary'); // PDP Buy Now

    // Initialize badge
    window.updateCartBadge();
});
