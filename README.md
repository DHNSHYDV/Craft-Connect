# Desh Ke Haath: Indian Heritage Craft E-commerce

**"Connecting India's Soul to the Digital World"**

Desh Ke Haath is a premium e-commerce platform dedicated to showcasing and selling authentic Indian handicrafts. We bridge the gap between traditional Indian artisans and the modern digital market, celebrating the mantra *"States Alag, Jazba Ek"* (Different States, One Spirit).

## 🚀 Key Features

- **Curated Craft Collection**: Explore high-quality handicrafts categorized by Indian states (Jaipur Blue Pottery, Banarasi Saree, Madhubani Art, etc.).
- **AI-Powered Discovery**: 
  - **Vision Engine**: Real-time analysis of craft patterns and authenticity.
  - **Craft Assistant**: A Gemini-powered AI chatbot to help users learn about heritage and find products.
- **Seamless Shopping Experience**:
  - Dynamic shopping cart with client-side persistence.
  - Robust checkout flow with integrated shipping management.
  - Multiple payment options including a dynamic UPI QR code generator.
- **User Trust & Security**:
  - Secure authentication (Sign Up / Log In).
  - Order history and localized profile management.
- **Premium Aesthetics**: Modern, dark-themed UI with glassmorphism and smooth micro-animations.

## 🛠 Tech Stack

- **Backend**: [Flask](https://flask.palletsprojects.com/) (Python)
- **Database**: [SQLAlchemy](https://www.sqlalchemy.org/) with SQLite
- **Authentication**: [Flask-Login](https://flask-login.readthedocs.io/)
- **Frontend**: HTML5, Vanilla CSS3 (Custom Design System), JavaScript (ES6+)
- **AI Integration**: [SambaNova Systems](https://sambanova.ai/) & [Google Gemini](https://ai.google.dev/)
- **APIs**: [QR Server API](https://goqr.me/api/) for dynamic payment codes

## 📦 Project Structure

```text
├── app.py              # Main Flask application and API routes
├── models.py           # SQLAlchemy database models
├── instance/           # Local SQLite database (site.db)
├── static/
│   ├── css/            # Stylized custom CSS modules
│   ├── js/             # Interactive frontend logic
│   └── uploads/        # User-uploaded profile images
├── templates/          # Jinja2 HTML templates
└── requirements.txt    # Project dependencies
```

## 🛠 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/DHNSHYDV/craft-site.git
   cd craft-site
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables**:
   Create a `.env` file in the root directory and add your keys:
   ```env
   SECRET_KEY=your_secret_key
   SAMBANOVA_API_KEY=your_api_key
   GEMINI_API_KEY=your_api_key
   ```

5. **Run the Application**:
   ```bash
   python app.py
   ```
   *The app will be available at `http://localhost:5001`.*

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details.

---
*Built with ❤️ for Indian Artisans.*
