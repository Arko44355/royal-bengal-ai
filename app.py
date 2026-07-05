# app.py
import streamlit as st
import requests
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO
import sqlite3
import base64
import json
import uuid
import os
from datetime import datetime

# 🛡️ Safe imports with fallback
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from groq import Groq
    GROQ_SUPPORT = True
except ImportError:
    GROQ_SUPPORT = False

try:
    from duckduckgo_search import DDGS
    WEB_SEARCH_SUPPORT = True
except ImportError:
    WEB_SEARCH_SUPPORT = False

# ============ PAGE CONFIG ============
st.set_page_config(
    page_title="Royal Bengal AI Machine 🐅",
    page_icon="🐅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ CUSTOM CSS ============
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(45deg, #FF6B35, #F7931E);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        background: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .user-message {
        background: #e3f2fd;
        border-left: 4px solid #1976d2;
    }
    .assistant-message {
        background: #f5f5f5;
        border-left: 4px solid #ff6f00;
    }
    .stButton > button {
        background: linear-gradient(45deg, #FF6B35, #F7931E);
        color: white;
        font-weight: bold;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: scale(1.05);
        box-shadow: 0 4px 12px rgba(255, 107, 53, 0.3);
    }
    .sidebar-content {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .status-online {
        background: #4caf50;
        color: white;
    }
    .status-offline {
        background: #f44336;
        color: white;
    }
    div[data-testid="stExpander"] {
        background: white;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ============ DATABASE FUNCTIONS ============
def get_db_connection():
    """Create database connection with timeout"""
    return sqlite3.connect("users.db", timeout=10, check_same_thread=False)

def init_db():
    """Initialize database tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Chat sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                title TEXT NOT NULL,
                messages_json TEXT NOT NULL,
                tab_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (email) REFERENCES users(email)
            )
        ''')
        
        # Create index for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sessions_email_tab 
            ON chat_sessions(email, tab_name, updated_at DESC)
        ''')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database initialization error: {str(e)}")
        return False

# Initialize database
init_db()

# ============ SESSION STATE INITIALIZATION ============
def init_session_state():
    """Initialize all session state variables"""
    defaults = {
        "logged_in": False,
        "user_profile": {},
        "messages": [],
        "math_messages": [],
        "econ_messages": [],
        "current_session_id_tab1": None,
        "current_session_id_tab2": None,
        "current_session_id_tab3": None,
        "renaming_session_id": None,
        "image_uploaded": False,
        "uploaded_image": None,
        "api_key_configured": False
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ============ HELPER FUNCTIONS ============

def process_uploaded_image(file_bytes):
    """Process and compress uploaded image"""
    try:
        img = Image.open(BytesIO(file_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((800, 800), Image.Resampling.LANCZOS)
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=70, optimize=True)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        st.error(f"Image processing error: {str(e)}")
        return ""

def perform_web_search(query, max_results=3):
    """Perform web search using DuckDuckGo"""
    if not WEB_SEARCH_SUPPORT:
        return ""
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        
        if not results:
            return ""
        
        context = "\n🌐 **লাইভ সার্চ ফলাফল:**\n\n"
        for i, r in enumerate(results, 1):
            context += f"📌 **উৎস {i}:** {r.get('title', 'শিরোনাম নেই')}\n"
            context += f"📝 {r.get('body', 'বিবরণ নেই')}\n\n"
        
        return context
    except Exception as e:
        st.warning(f"Search error: {str(e)}")
        return ""

def save_session(session_id, email, title, messages, tab_name):
    """Save chat session to database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO chat_sessions 
            (session_id, email, title, messages_json, tab_name, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (session_id, email, title, json.dumps(messages), tab_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Save error: {str(e)}")
        return False

def get_sessions(email, tab_name):
    """Get all sessions for a user and tab"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT session_id, title, messages_json 
            FROM chat_sessions 
            WHERE email = ? AND tab_name = ? 
            ORDER BY updated_at DESC
        ''', (email, tab_name))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        st.error(f"Load error: {str(e)}")
        return []

def delete_session(session_id):
    """Delete a session from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM chat_sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Delete error: {str(e)}")
        return False

def rename_session(session_id, new_title):
    """Rename a session"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE chat_sessions 
            SET title = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE session_id = ?
        ''', (new_title, session_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Rename error: {str(e)}")
        return False

def get_api_key():
    """Get API key from various sources"""
    # Priority: 1. User input, 2. Secrets, 3. Environment variable
    if "user_api_key" in st.session_state and st.session_state.user_api_key:
        return st.session_state.user_api_key
    elif "GROQ_API_KEY" in st.secrets:
        return st.secrets["GROQ_API_KEY"]
    elif "GROQ_API_KEY" in os.environ:
        return os.environ["GROQ_API_KEY"]
    else:
        return None

# ============ AI RESPONSE GENERATORS ============

def safe_text_stream(prompt, api_key):
    """Generate text response with streaming"""
    if not GROQ_SUPPORT:
        yield "⚠️ Groq library not installed. Please install: pip install groq"
        return
    
    if not api_key:
        yield "⚠️ API key not configured. Please add your Groq API key in the sidebar."
        return
    
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": """You are Royal Bengal AI, created by Md Mohtasim Billah. 
                Always respond in Bengali script. Be friendly, helpful, and professional. 
                Explain concepts clearly with step-by-step reasoning. 
                Use $$ LaTeX $$ for mathematical expressions. 
                If the user asks about yourself, introduce as 'Royal Bengal AI Machine'."""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2048,
            stream=True
        )
        
        for chunk in response:
            if chunk and chunk.choices:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
    except Exception as e:
        yield f"⚠️ AI Error: {str(e)}. Please try again or check your API key."

def safe_math_stream(prompt, api_key):
    """Generate math solution with streaming"""
    if not GROQ_SUPPORT or not api_key:
        yield "⚠️ API not configured. Please check your Groq API key."
        return
    
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": """You are an expert Mathematics professor. 
                Respond in Bengali script. Provide detailed step-by-step solutions. 
                Use proper LaTeX formatting with $$ for equations. 
                If visualization is needed, include Python code for plots using matplotlib or plotly."""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=2048,
            stream=True
        )
        
        for chunk in response:
            if chunk and chunk.choices:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
    except Exception as e:
        yield f"⚠️ Math Error: {str(e)}"

def safe_econ_stream(prompt, api_key):
    """Generate economics analysis with streaming"""
    if not GROQ_SUPPORT or not api_key:
        yield "⚠️ API not configured. Please check your Groq API key."
        return
    
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": """You are an Economics professor. 
                Respond in Bengali script. Provide detailed economic analysis. 
                Include supply-demand curves, market equilibrium, and economic theories. 
                Use LaTeX for formulas and include Python code for visualizations."""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=2048,
            stream=True
        )
        
        for chunk in response:
            if chunk and chunk.choices:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
    except Exception as e:
        yield f"⚠️ Economics Error: {str(e)}"

def vision_response_generator(image_base64, user_prompt, api_key):
    """Generate response for image analysis"""
    if not GROQ_SUPPORT or not api_key:
        yield "⚠️ API not configured. Please check your Groq API key."
        return
    
    if not image_base64:
        yield "⚠️ No image found. Please upload an image first."
        return
    
    models_to_try = [
        "llama-3.2-11b-vision-preview",
        "llama-3.2-90b-vision-preview"
    ]
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    text_content = f"""You are Royal Bengal AI Machine, created by Md Mohtasim Billah. 
    Respond in Bengali script. Analyze the image carefully and provide detailed explanation.
    If it's a math problem, solve it step by step with LaTeX.
    If it's a document, summarize the key points.
    User question: {user_prompt if user_prompt else 'বিশ্লেষণ করে বলুন এই ছবিতে কী আছে।'}"""
    
    success = False
    last_error = ""
    
    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text_content},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                    ]
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1024,
            "stream": True
        }
        
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=30
            )
            
            if response.status_code == 200:
                success = True
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8').strip()
                        if decoded_line.startswith("data:"):
                            data_str = decoded_line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_str)
                                content = chunk_json['choices'][0]['delta'].get('content', '')
                                if content:
                                    yield content
                            except:
                                pass
                break
            else:
                last_error = f"Model {model} failed: {response.status_code}"
        except Exception as e:
            last_error = f"Model {model} error: {str(e)}"
    
    if not success:
        yield f"⚠️ Image analysis failed. Last error: {last_error}"

def try_execute_graph(full_response):
    """Extract and execute Python code for graphs from response"""
    try:
        # Check if response contains plotting code
        if "```python" in full_response:
            code_blocks = full_response.split("```python")
            for block in code_blocks[1:]:
                code = block.split("```")[0].strip()
                if "fig" in code or "plt" in code:
                    # Execute the plotting code
                    env = {
                        "np": np, 
                        "go": go, 
                        "px": px, 
                        "plt": plt,
                        "st": st
                    }
                    exec(code, env)
                    
                    # Display the plot
                    if "fig" in env and isinstance(env["fig"], go.Figure):
                        st.plotly_chart(env["fig"], use_container_width=True)
                    elif "plt" in env and plt.get_fignums():
                        st.pyplot(plt.gcf())
                        plt.clf()
                    break
    except Exception as e:
        # Silently fail if graph execution fails
        pass

# ============ UI COMPONENTS ============

def render_auth():
    """Render authentication page"""
    st.markdown('<h1 class="main-header">🐅 Royal Bengal AI Machine</h1>', unsafe_allow_html=True)
    st.markdown("### 🔐 Secure Access Panel")
    
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Sign Up"])
    
    with tab2:
        st.markdown("#### Create New Account")
        reg_name = st.text_input("Full Name", key="reg_name", placeholder="Your full name")
        reg_email = st.text_input("Email Address", key="reg_email", placeholder="your@email.com")
        reg_pass = st.text_input("Password", type="password", key="reg_pass", placeholder="Choose a strong password")
        reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm", placeholder="Re-enter password")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("📝 Create Account", use_container_width=True):
                if not all([reg_name, reg_email, reg_pass]):
                    st.error("❌ Please fill all fields.")
                elif reg_pass != reg_confirm:
                    st.error("❌ Passwords don't match.")
                elif len(reg_pass) < 6:
                    st.error("❌ Password must be at least 6 characters.")
                else:
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO users (email, name, password) VALUES (?, ?, ?)",
                            (reg_email.strip().lower(), reg_name.strip(), reg_pass.strip())
                        )
                        conn.commit()
                        conn.close()
                        st.success("✅ Account created successfully! Please login.")
                        st.balloons()
                    except sqlite3.IntegrityError:
                        st.error("❌ This email is already registered.")
                    except Exception as e:
                        st.error(f"❌ Registration error: {str(e)}")
    
    with tab1:
        st.markdown("#### Welcome Back!")
        login_email = st.text_input("Email", key="login_email", placeholder="your@email.com")
        login_pass = st.text_input("Password", type="password", key="login_pass", placeholder="Enter your password")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🔓 Unlock Dashboard", use_container_width=True):
                if not all([login_email, login_pass]):
                    st.error("❌ Please enter both email and password.")
                else:
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT name, password FROM users WHERE email = ?",
                            (login_email.strip().lower(),)
                        )
                        user = cursor.fetchone()
                        conn.close()
                        
                        if user and login_pass.strip() == user[1]:
                            st.session_state.logged_in = True
                            st.session_state.user_profile = {
                                "name": user[0],
                                "email": login_email.strip().lower()
                            }
                            st.rerun()
                        else:
                            st.error("❌ Invalid email or password.")
                    except Exception as e:
                        st.error(f"❌ Login error: {str(e)}")
        
        with col2:
            if st.button("🔄 Reset Password", use_container_width=True):
                st.info("📧 Password reset link will be sent to your email.")

def render_sidebar():
    """Render sidebar with controls"""
    with st.sidebar:
        st.markdown(f"""
        <div style="text-align: center; padding: 1rem;">
            <h2>🐅 Royal Bengal AI</h2>
            <p style="color: #666;">Welcome, {st.session_state.user_profile.get('name', 'User')}!</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # API Key Configuration
        with st.expander("🔑 API Configuration", expanded=True):
            api_key = st.text_input(
                "Groq API Key",
                type="password",
                placeholder="Enter your Groq API key...",
                help="Get your API key from console.groq.com"
            )
            
            if api_key:
                st.session_state.user_api_key = api_key
                st.session_state.api_key_configured = True
                st.success("✅ API Key configured!")
            elif get_api_key():
                st.success("✅ API Key found in secrets/environment")
                st.session_state.api_key_configured = True
            else:
                st.warning("⚠️ Please add your Groq API key")
                st.session_state.api_key_configured = False
            
            # Test API key button
            if st.button("🔍 Test API Key", use_container_width=True):
                if st.session_state.api_key_configured:
                    with st.spinner("Testing API key..."):
                        try:
                            client = Groq(api_key=get_api_key())
                            response = client.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                messages=[{"role": "user", "content": "Say 'API working!'"}],
                                max_tokens=10
                            )
                            st.success("✅ API Key is working!")
                        except Exception as e:
                            st.error(f"❌ API Key test failed: {str(e)}")
                else:
                    st.error("❌ Please configure API key first")
        
        # Voice Assistant
        st.markdown("---")
        voice_on = st.checkbox("🎙️ Voice Assistant", help="Enable voice input/output")
        if voice_on:
            st.info("🎤 Voice feature coming soon!")
        
        # Web Search
        if WEB_SEARCH_SUPPORT:
            web_search_enabled = st.checkbox(
                "🌐 Live Web Search",
                value=True,
                help="Enable DuckDuckGo search for real-time information"
            )
        else:
            web_search_enabled = False
            st.warning("⚠️ Web search not available. Install duckduckgo-search")
        
        # Chat History
        st.markdown("---")
        st.markdown("### 📁 Chat History")
        
        # Display sessions for each tab
        tabs = [
            ("💬 AI Assistant", "tab1", "messages", "current_session_id_tab1"),
            ("📊 Math Wave", "tab2", "math_messages", "current_session_id_tab2"),
            ("📈 Economics", "tab3", "econ_messages", "current_session_id_tab3")
        ]
        
        for tab_name, tab_id, msg_key, session_key in tabs:
            with st.expander(f"📂 {tab_name}", expanded=False):
                # New chat button
                if st.button(f"➕ New Chat", key=f"new_{tab_id}", use_container_width=True):
                    st.session_state[msg_key] = []
                    st.session_state[session_key] = None
                    st.rerun()
                
                # List sessions
                sessions = get_sessions(st.session_state.user_profile['email'], tab_id)
                if not sessions:
                    st.info("No saved chats")
                else:
                    for s_id, title, msg_json in sessions:
                        col1, col2, col3 = st.columns([0.7, 0.15, 0.15])
                        with col1:
                            if st.button(f"📄 {title[:25]}...", key=f"load_{tab_id}_{s_id}", use_container_width=True):
                                try:
                                    msgs = json.loads(msg_json)
                                    st.session_state[msg_key] = msgs
                                    st.session_state[session_key] = s_id
                                    st.rerun()
                                except:
                                    st.error("Failed to load chat")
                        
                        with col2:
                            if st.button("✏️", key=f"rename_{tab_id}_{s_id}", help="Rename"):
                                st.session_state.renaming_session_id = s_id
                                st.rerun()
                        
                        with col3:
                            if st.button("🗑️", key=f"del_{tab_id}_{s_id}", help="Delete"):
                                if delete_session(s_id):
                                    if st.session_state[session_key] == s_id:
                                        st.session_state[msg_key] = []
                                        st.session_state[session_key] = None
                                    st.rerun()
                        
                        # Show rename input if this session is being renamed
                        if st.session_state.renaming_session_id == s_id:
                            new_title = st.text_input("New title:", value=title, key=f"rename_input_{s_id}")
                            if st.button("Save", key=f"save_rename_{s_id}"):
                                if rename_session(s_id, new_title):
                                    st.session_state.renaming_session_id = None
                                    st.rerun()
        
        # Quick Controls
        st.markdown("---")
        st.markdown("### ⚡ Quick Controls")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("🧹 Clear Cache", use_container_width=True):
                st.cache_data.clear()
                st.cache_resource.clear()
                st.toast("Cache cleared!")
                st.rerun()
        
        # Logout
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            for key in ["logged_in", "user_profile", "messages", "math_messages", "econ_messages"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

def render_chat_interface():
    """Main chat interface"""
    st.markdown('<h1 class="main-header">🐅 Royal Bengal AI Machine</h1>', unsafe_allow_html=True)
    
    # Show user info
    st.markdown(f"""
    <div style="text-align: center; padding: 0.5rem; background: rgba(255,255,255,0.5); border-radius: 10px;">
        👋 Welcome, {st.session_state.user_profile.get('name', 'User')}! 
        <span class="status-badge status-online">● Online</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Check API key
    api_key = get_api_key()
    if not api_key:
        st.warning("⚠️ Please add your Groq API key in the sidebar to use AI features.")
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "💬 AI Assistant",
        "📊 Math Solver",
        "📈 Economics",
        "🎨 Image AI"
    ])
    
    # Tab 1: AI Assistant
    with tab1:
        st.markdown("### 💬 AI Assistant with Document Support")
        
        # File upload
        uploaded_file = st.file_uploader(
            "📎 Upload PDF or Image",
            type=["pdf", "txt", "png", "jpg", "jpeg"],
            key="tab1_uploader",
            help="Upload PDF for text extraction or images for AI analysis"
        )
        
        extracted_text = ""
        image_base64 = ""
        
        if uploaded_file:
            file_bytes = uploaded_file.getvalue()
            file_name = uploaded_file.name.lower()
            
            # Handle PDF
            if file_name.endswith(".pdf") and PDF_SUPPORT:
                try:
                    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                        extracted_text = "\n".join([
                            p.extract_text() or "" 
                            for p in pdf.pages
                        ])
                    st.success(f"✅ PDF processed: {len(extracted_text)} characters extracted")
                    with st.expander("📄 View extracted text"):
                        st.text(extracted_text[:1000] + "..." if len(extracted_text) > 1000 else extracted_text)
                except Exception as e:
                    st.error(f"PDF processing error: {str(e)}")
            
            # Handle Image
            elif file_name.split('.')[-1] in ["png", "jpg", "jpeg"]:
                st.image(file_bytes, width=300, caption="Uploaded Image")
                image_base64 = process_uploaded_image(file_bytes)
                if image_base64:
                    st.success("✅ Image processed successfully!")
        
        # Display chat history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        # Chat input
        if prompt := st.chat_input("আপনার প্রশ্ন লিখুন...", key="t1_chat"):
            # Add user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Generate response
            with st.chat_message("assistant"):
                if not api_key:
                    st.error("⚠️ Please configure Groq API key in sidebar")
                    full_response = "API key not configured. Please add your Groq API key."
                else:
                    try:
                        with st.spinner("🤔 চিন্তা করছি..."):
                            # Prepare context
                            context = ""
                            if extracted_text:
                                context += f"📄 Document context:\n{extracted_text}\n\n"
                            
                            if web_search_enabled:
                                search_result = perform_web_search(prompt)
                                if search_result:
                                    context += search_result + "\n\n"
                            
                            final_prompt = f"{context}User question: {prompt}"
                            
                            # Generate response
                            if image_base64:
                                stream = vision_response_generator(image_base64, prompt, api_key)
                            else:
                                stream = safe_text_stream(final_prompt, api_key)
                            
                            full_response = st.write_stream(stream)
                            
                            # Try to render graphs if any
                            try_execute_graph(full_response)
                            
                            # Save session
                            session_id = st.session_state.current_session_id_tab1 or str(uuid.uuid4())
                            st.session_state.current_session_id_tab1 = session_id
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                            save_session(
                                session_id,
                                st.session_state.user_profile['email'],
                                prompt[:50],
                                st.session_state.messages,
                                "tab1"
                            )
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        full_response = f"⚠️ Error occurred: {str(e)}"
    
    # Tab 2: Math Solver
    with tab2:
        st.markdown("### 📊 Advanced Math Solver")
        st.info("📝 Ask any math problem - algebra, calculus, statistics, or complex equations!")
        
        # Display chat history
        for msg in st.session_state.math_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        # Chat input
        if prompt := st.chat_input("গাণিতিক সমস্যা লিখুন...", key="t2_chat"):
            # Add user message
            st.session_state.math_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Generate response
            with st.chat_message("assistant"):
                if not api_key:
                    st.error("⚠️ Please configure Groq API key")
                    full_response = "API key not configured."
                else:
                    try:
                        with st.spinner("🧮 সমাধান করছি..."):
                            # Add web search if enabled
                            context = ""
                            if web_search_enabled:
                                search_result = perform_web_search(prompt)
                                if search_result:
                                    context += search_result + "\n\n"
                            
                            final_prompt = f"{context}Math problem: {prompt}"
                            stream = safe_math_stream(final_prompt, api_key)
                            full_response = st.write_stream(stream)
                            
                            # Try to render graphs
                            try_execute_graph(full_response)
                            
                            # Save session
                            session_id = st.session_state.current_session_id_tab2 or str(uuid.uuid4())
                            st.session_state.current_session_id_tab2 = session_id
                            st.session_state.math_messages.append({"role": "assistant", "content": full_response})
                            save_session(
                                session_id,
                                st.session_state.user_profile['email'],
                                prompt[:50],
                                st.session_state.math_messages,
                                "tab2"
                            )
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        full_response = f"⚠️ Error occurred: {str(e)}"
    
    # Tab 3: Economics
    with tab3:
        st.markdown("### 📈 Economics Analysis")
        st.info("📊 Ask about supply-demand, market equilibrium, macroeconomics, or any economic concept!")
        
        # Display chat history
        for msg in st.session_state.econ_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        # Chat input
        if prompt := st.chat_input("অর্থনীতির প্রশ্ন লিখুন...", key="t3_chat"):
            # Add user message
            st.session_state.econ_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Generate response
            with st.chat_message("assistant"):
                if not api_key:
                    st.error("⚠️ Please configure Groq API key")
                    full_response = "API key not configured."
                else:
                    try:
                        with st.spinner("📈 বিশ্লেষণ করছি..."):
                            # Add web search if enabled
                            context = ""
                            if web_search_enabled:
                                search_result = perform_web_search(prompt)
                                if search_result:
                                    context += search_result + "\n\n"
                            
                            final_prompt = f"{context}Economics question: {prompt}"
                            stream = safe_econ_stream(final_prompt, api_key)
                            full_response = st.write_stream(stream)
                            
                            # Try to render graphs
                            try_execute_graph(full_response)
                            
                            # Save session
                            session_id = st.session_state.current_session_id_tab3 or str(uuid.uuid4())
                            st.session_state.current_session_id_tab3 = session_id
                            st.session_state.econ_messages.append({"role": "assistant", "content": full_response})
                            save_session(
                                session_id,
                                st.session_state.user_profile['email'],
                                prompt[:50],
                                st.session_state.econ_messages,
                                "tab3"
                            )
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        full_response = f"⚠️ Error occurred: {str(e)}"
    
    # Tab 4: Image AI
    with tab4:
        st.markdown("### 🎨 AI Image Analysis")
        st.info("📸 Upload images for AI-powered analysis and description!")
        
        # Image upload
        uploaded_image = st.file_uploader(
            "📸 Upload Image",
            type=["png", "jpg", "jpeg", "gif", "bmp"],
            key="tab4_uploader",
            help="Upload any image for AI analysis"
        )
        
        if uploaded_image:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(uploaded_image, width=300, caption="Your Image")
            
            with col2:
                with st.spinner("🧠 Analyzing image..."):
                    if not api_key:
                        st.error("⚠️ Please configure Groq API key")
                    else:
                        # Process image
                        img_base64 = process_uploaded_image(uploaded_image.getvalue())
                        if img_base64:
                            # Ask for analysis
                            analysis_prompt = st.text_input(
                                "What would you like to know about this image?",
                                placeholder="e.g., Describe this image, Solve the math problem, etc."
                            )
                            
                            if st.button("🔍 Analyze Image", use_container_width=True):
                                with st.chat_message("assistant"):
                                    stream = vision_response_generator(
                                        img_base64,
                                        analysis_prompt or "বিশ্লেষণ করে বলুন এই ছবিতে কী আছে",
                                        api_key
                                    )
                                    response = st.write_stream(stream)
                                    
                                    # Save to chat history
                                    if response:
                                        st.session_state.messages.append({
                                            "role": "assistant",
                                            "content": f"🖼️ Image Analysis: {response}"
                                        })
                        else:
                            st.error("Failed to process image")

# ============ MAIN APP ============

def main():
    """Main application entry point"""
    
    # Check login status
    if not st.session_state.logged_in:
        render_auth()
        return
    
    # Render sidebar
    render_sidebar()
    
    # Render main interface
    render_chat_interface()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; padding: 1rem;">
        <p>Made with ❤️ by Md Mohtasim Billah | 🐅 Royal Bengal AI Machine</p>
        <p style="font-size: 0.8rem;">Powered by Groq AI • Secure • Fast • Intelligent</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()