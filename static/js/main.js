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

    // Mobile Dropdown Toggle
    const dropdownToggles = document.querySelectorAll('.nav-item-has-dropdown > a');
    dropdownToggles.forEach(toggle => {
        toggle.addEventListener('click', (e) => {
            if (window.innerWidth <= 768) {
                e.preventDefault();
                const parent = toggle.parentElement;
                parent.classList.toggle('active');
            }
        });
    });

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
            const opts = chatBody.querySelector('.chat-options');
            if (opts) chatBody.insertBefore(msgDiv, opts);
            else chatBody.appendChild(msgDiv);
            chatBody.scrollTop = chatBody.scrollHeight;
        }

        async function getBotResponse(input) {
            const url = (typeof window.CHAT_API_URL !== 'undefined' && window.CHAT_API_URL) || '/api/chat';
            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: input })
                });
                if (!resp.ok) {
                    return "Server error. Make sure Flask is running (flask run) and refresh the page.";
                }
                const data = await resp.json();
                return data.reply || "I couldn't process that. Please try again or contact support@deshkehaath.in.";
            } catch (e) {
                return "Connection failed. Start the server with: flask run. Then refresh and try again.";
            }
        }

        async function handleSend() {
            const text = chatInput.value.trim();
            if (text) {
                addMessage(text, true);
                chatInput.value = '';

                const typingIndicator = document.createElement('div');
                typingIndicator.classList.add('message', 'bot-message');
                typingIndicator.textContent = '...';
                typingIndicator.dataset.typing = '1';
                chatBody.appendChild(typingIndicator);
                chatBody.scrollTop = chatBody.scrollHeight;

                const response = await getBotResponse(text);
                typingIndicator.remove();
                addMessage(response, false);
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
            btn.addEventListener('click', async () => {
                const text = btn.textContent;
                addMessage(text, true);
                const typingIndicator = document.createElement('div');
                typingIndicator.classList.add('message', 'bot-message');
                typingIndicator.textContent = '...';
                typingIndicator.dataset.typing = '1';
                chatBody.appendChild(typingIndicator);
                chatBody.scrollTop = chatBody.scrollHeight;
                const response = await getBotResponse(text);
                typingIndicator.remove();
                addMessage(response, false);
            });
        });
    }

    // Dark Mode Toggle
    const themeToggle = document.querySelector('.theme-toggle');
    const body = document.body;
    const sunIcon = document.querySelector('.sun-icon');
    const moonIcon = document.querySelector('.moon-icon');

    // Check local storage (Default to Dark)
    const currentTheme = localStorage.getItem('theme');
    if (currentTheme === 'dark' || !currentTheme) {
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

    // --- INTERACTIVE INDIA MAP LOGIC ---
    const mapTooltip = document.getElementById('map-tooltip');
    const statePaths = document.querySelectorAll('#india-map-wrapper path');
    const connectorSvg = document.getElementById('map-connector-svg');
    const connectorLine = document.getElementById('map-connector-line');
    const connectorDot = document.getElementById('map-connector-dot');

    // Quick mapping of State Names to popular handicrafts (sync with heritage data)
    const stateHandicrafts = {
        "Andhra Pradesh": ["Kondapalli Toys", "Uppada Silk", "Temple Jewellery"],
        "Arunachal Pradesh": ["Bamboo Crafts", "Bead Jewellery", "Wooden Masks"],
        "Assam": ["Jaapi Hat", "Muga Silk", "Bell Metal Crafts"],
        "Bihar": ["Madhubani Painting", "Tussar Silk", "Sikki Grass Crafts"],
        "Chhattisgarh": ["Dhokra Metal", "Kosa Silk", "Wrought Iron"],
        "Goa": ["Coconut Shell Crafts", "Azulejos Tiles", "Kunbi Saree"],
        "Gujarat": ["Bandhani Textile", "Patola Saree", "Kutch Embroidery"],
        "Haryana": ["Phulkari", "Jhajjar Pottery", "Brass Utensils"],
        "Himachal Pradesh": ["Kullu Shawls", "Chamba Rumal", "Silver Jewellery"],
        "Jharkhand": ["Sohrai Painting", "Tussar Silk", "Bamboo Crafts"],
        "Karnataka": ["Mysore Silk", "Channapatna Toys", "Sandalwood Carvings"],
        "Kerala": ["Kasavu Saree", "Coir Crafts", "Nettur Petti"],
        "Madhya Pradesh": ["Gond Art", "Chanderi Saree", "Maheshwari Fabric"],
        "Maharashtra": ["Warli Art", "Paithani Saree", "Kolhapuri Jewellery"],
        "Meghalaya": ["Bamboo Bowls", "Eri Silk", "Black Pottery"],
        "Mizoram": ["Puan Saree", "Bamboo Hats", "Beadwork"],
        "Nagaland": ["Warrior Shawls", "Hornbill Art", "Beaded Necklaces"],
        "Odisha": ["Pattachitra", "Sambalpuri Saree", "Silver Filigree"],
        "Punjab": ["Phulkari", "Punjabi Jutti", "Parandi"],
        "Rajasthan": ["Blue Pottery", "Bandhani", "Thewa Jewellery"],
        "Sikkim": ["Thangka Painting", "Lepcha Weaving", "Wooden Tables"],
        "Tamil Nadu": ["Kanchipuram Silk", "Tanjore Painting", "Temple Jewellery"],
        "Telangana": ["Pochampally Ikat", "Bidriware", "Nirmal Paintings"],
        "Tripura": ["Bamboo Art", "Handloom", "Cane Furniture"],
        "Uttar Pradesh": ["Chikan Embroidery", "Banarasi Silk", "Brassware"],
        "Uttarakhand": ["Pichora Saree", "Ringaal Basketry", "Aipan Art"],
        "West Bengal": ["Baluchari Silk", "Terracotta Horse", "Kantha Embroidery"],
        "Jammu and Kashmir": ["Pashmina Shawl", "Papier Mache", "Walnut Carving"],
        "Ladakh": ["Tibetan Jewelry", "Woolen Rugs", "Prayer Wheels"]
    };

    if (statePaths.length > 0 && mapTooltip) {
        const tooltipState = mapTooltip.querySelector('.tooltip-state');
        const tooltipItems = mapTooltip.querySelector('.tooltip-items');

        statePaths.forEach(path => {
            path.addEventListener('mouseenter', (e) => {
                const stateName = path.getAttribute('name');
                const crafts = stateHandicrafts[stateName] || ["Traditional Handicrafts", "Heritage Textiles"];

                tooltipState.textContent = stateName;
                tooltipItems.innerHTML = crafts.map(item => `<li>• ${item}</li>`).join('');

                mapTooltip.classList.add('active');

                if (connectorLine && connectorDot) {
                    connectorLine.style.opacity = '0.5';
                    connectorDot.style.opacity = '1';
                }
            });

            path.addEventListener('mousemove', (e) => {
                const mouseX = e.clientX;
                const mouseY = e.clientY;

                // Offset below and to the right of cursor
                let x = mouseX + 25;
                let y = mouseY + 25;

                const tooltipWidth = mapTooltip.offsetWidth;
                const tooltipHeight = mapTooltip.offsetHeight;
                const windowWidth = window.innerWidth;
                const windowHeight = window.innerHeight;

                // Improved Viewport Bounds Checking
                if (x + tooltipWidth > windowWidth - 20) {
                    x = mouseX - tooltipWidth - 25;
                }

                if (y + tooltipHeight > windowHeight - 20) {
                    y = mouseY - tooltipHeight - 25;
                }

                if (x < 20) x = 20;
                if (y < 20) y = 20;

                mapTooltip.style.left = `${x}px`;
                mapTooltip.style.top = `${y}px`;

                // Update Connector Line
                if (connectorLine && connectorSvg && path) {
                    const svgRect = connectorSvg.getBoundingClientRect();
                    const pathRect = path.getBoundingClientRect();

                    // State attachment (center)
                    const startX = pathRect.left + pathRect.width / 2 - svgRect.left;
                    const startY = pathRect.top + pathRect.height / 2 - svgRect.top;

                    // Tooltip attachment (center)
                    const endX = x + tooltipWidth / 2 - svgRect.left;
                    const endY = y + tooltipHeight / 2 - svgRect.top;

                    connectorLine.setAttribute('x1', startX);
                    connectorLine.setAttribute('y1', startY);
                    connectorLine.setAttribute('x2', endX);
                    connectorLine.setAttribute('y2', endY);

                    connectorDot.setAttribute('cx', startX);
                    connectorDot.setAttribute('cy', startY);
                }
            });

            path.addEventListener('mouseleave', () => {
                mapTooltip.classList.remove('active');
                if (connectorLine && connectorDot) {
                    connectorLine.style.opacity = '0';
                    connectorDot.style.opacity = '0';
                }
            });

            // Add Click Event for Redirection
            path.addEventListener('click', () => {
                const stateName = path.getAttribute('name');
                if (stateName) {
                    window.location.href = `/products?state=${encodeURIComponent(stateName)}`;
                }
            });
        });
    }
});
