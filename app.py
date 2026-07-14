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
import tempfile  # ✅ MinerU-এর জন্য

# 🛡️ MinerU ইমপোর্ট
try:
    from mineru import MinerU
    MINERU_SUPPORT = True
except ImportError:
    MINERU_SUPPORT = False

# 🛡️ Safe imports
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
    .stApp { background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%); }
    .main-header {
        font-size: 2.8rem;
        font-weight: bold;
        background: linear-gradient(45deg, #FF6B35, #F7931E, #FFD700);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1.5rem;
        text-shadow: 0 0 30px rgba(255, 107, 53, 0.3);
    }
    .stChatMessage {
        background: rgba(255, 255, 255, 0.05) !important;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 1rem;
        margin: 0.5rem 0;
        color: #ffffff !important;
    }
    div[data-testid="stChatMessage"][data-role="user"] {
        background: linear-gradient(135deg, #FF6B35, #F7931E) !important;
        border: none;
        color: white !important;
    }
    div[data-testid="stChatMessage"][data-role="assistant"] {
        background: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 107, 53, 0.3);
        color: #e0e0e0 !important;
    }
    .css-1d391kg { background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%) !important; border-right: 1px solid rgba(255, 255, 255, 0.05); }
    .css-1d391kg, .css-1d391kg p, .css-1d391kg h1, .css-1d391kg h2, .css-1d391kg h3 { color: #ffffff !important; }
    .stTextInput > div > div > input {
        background: rgba(255, 255, 255, 0.1) !important;
        border: 1px solid rgba(255, 107, 53, 0.3) !important;
        border-radius: 25px !important;
        color: white !important;
        padding: 0.75rem 1.5rem !important;
    }
    .stTextInput > div > div > input:focus { border-color: #FF6B35 !important; box-shadow: 0 0 20px rgba(255, 107, 53, 0.2) !important; }
    .stButton > button {
        background: linear-gradient(45deg, #FF6B35, #F7931E) !important;
        color: white !important;
        font-weight: bold !important;
        border: none !important;
        border-radius: 25px !important;
        padding: 0.6rem 1.5rem !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(255, 107, 53, 0.3) !important;
    }
    .stButton > button:hover { transform: translateY(-2px) scale(1.02) !important; box-shadow: 0 6px 25px rgba(255, 107, 53, 0.5) !important; }
    .streamlit-expanderHeader { background: rgba(255, 255, 255, 0.05) !important; border-radius: 10px !important; color: white !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] { background: rgba(255, 255, 255, 0.05) !important; border-radius: 10px !important; color: #aaa !important; padding: 0.5rem 1.5rem !important; }
    .stTabs [aria-selected="true"] { background: linear-gradient(135deg, #FF6B35, #F7931E) !important; color: white !important; }
    .stAlert { background: rgba(255, 255, 255, 0.05) !important; backdrop-filter: blur(10px) !important; border: 1px solid rgba(255, 255, 255, 0.1) !important; color: white !important; }
    .stCodeBlock { background: rgba(0, 0, 0, 0.3) !important; border-radius: 10px !important; }
    .footer { text-align: center; color: #888; padding: 2rem; border-top: 1px solid rgba(255, 255, 255, 0.05); margin-top: 2rem; }
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.05); border-radius: 10px; }
    ::-webkit-scrollbar-thumb { background: linear-gradient(45deg, #FF6B35, #F7931E); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #FF6B35; }
</style>
""", unsafe_allow_html=True)

# ============ SESSION STATE ============
def init_session_state():
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
        "web_search_enabled": True
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
init_session_state()

# ============ DATABASE ============
def get_db_connection():
    return sqlite3.connect("users.db", timeout=10, check_same_thread=False)

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, name TEXT NOT NULL, password TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS chat_sessions (session_id TEXT PRIMARY KEY, email TEXT NOT NULL, title TEXT NOT NULL, messages_json TEXT NOT NULL, tab_name TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (email) REFERENCES users(email))')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_email_tab ON chat_sessions(email, tab_name, updated_at DESC)')
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return False
init_db()

# ============ HELPER FUNCTIONS ============

def extract_text_with_mineru(file_bytes):
    """MinerU Flash Mode দিয়ে PDF থেকে টেক্সট এক্সট্র্যাক্ট করুন (ফ্রি!)"""
    if not MINERU_SUPPORT:
        return "⚠️ MinerU ইনস্টল করা নেই। `pip install mineru-open-sdk` দিন।"
    
    try:
        # টেম্পোরারি ফাইল তৈরি করুন
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name
        
        # MinerU Flash Mode - কোনো API key লাগে না!
        client = MinerU()
        result = client.flash_extract(tmp_path)
        
        # টেম্প ফাইল ডিলিট করুন
        os.unlink(tmp_path)
        
        if result and result.markdown:
            return result.markdown
        else:
            return "⚠️ MinerU থেকে কোনো টেক্সট পাওয়া যায়নি। PDF টি স্ক্যান করা বা খালি হতে পারে।"
            
    except Exception as e:
        return f"⚠️ MinerU Error: {str(e)}\n\n💡 নিশ্চিত করুন PDF টি ১০MB এর কম এবং ২০ পৃষ্ঠার বেশি নয়।"

def perform_web_search(query, max_results=3):
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

def get_api_key():
    if "user_api_key" in st.session_state and st.session_state.user_api_key:
        return st.session_state.user_api_key
    elif "GROQ_API_KEY" in st.secrets:
        return st.secrets["GROQ_API_KEY"]
    elif "GROQ_API_KEY" in os.environ:
        return os.environ["GROQ_API_KEY"]
    else:
        return None

# ============ AI GENERATORS ============

def safe_text_stream(prompt, api_key):
    if not GROQ_SUPPORT or not api_key:
        yield "⚠️ Groq API key needed."
        return
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # ✅ কম টোকেন খরচ
            messages=[
                {"role": "system", "content": """You are Royal Bengal AI, created by Md Mohtasim Billah.
                Always respond in Bengali script. Be friendly, helpful, and professional.
                Provide step-by-step solutions with clear explanations.
                Always output COMPLETE LaTeX code for all mathematical expressions using $$ ... $$ format.
                After the solution, provide a separate section with the complete LaTeX code."""},
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
        yield f"⚠️ AI Error: {str(e)}"

def safe_math_stream(prompt, api_key):
    if not GROQ_SUPPORT or not api_key:
        yield "⚠️ Groq API key needed."
        return
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # ✅ কম টোকেন খরচ
            messages=[
                {"role": "system", "content": """You are an expert Mathematics professor.
                Respond in Bengali script. Provide detailed step-by-step solutions.
                Use proper LaTeX formatting with $$ for equations.
                Always output COMPLETE LaTeX code at the end."""},
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
    if not GROQ_SUPPORT or not api_key:
        yield "⚠️ Groq API key needed."
        return
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # ✅ কম টোকেন খরচ
            messages=[
                {"role": "system", "content": """You are an Economics professor.
                Respond in Bengali script. Provide detailed economic analysis.
                Use LaTeX for formulas.
                Always output COMPLETE LaTeX code at the end."""},
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
        yield f"⚠️ Econ Error: {str(e)}"

def save_session(session_id, email, title, messages, tab_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO chat_sessions (session_id, email, title, messages_json, tab_name, updated_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)', (session_id, email, title, json.dumps(messages), tab_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Save error: {str(e)}")
        return False

def get_sessions(email, tab_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT session_id, title, messages_json FROM chat_sessions WHERE email = ? AND tab_name = ? ORDER BY updated_at DESC', (email, tab_name))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        st.error(f"Load error: {str(e)}")
        return []

def delete_session(session_id):
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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?', (new_title, session_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Rename error: {str(e)}")
        return False

def try_execute_graph(full_response):
    try:
        if "```python" in full_response:
            code_blocks = full_response.split("```python")
            for block in code_blocks[1:]:
                code = block.split("```")[0].strip()
                if "fig" in code or "plt" in code:
                    env = {"np": np, "go": go, "px": px, "plt": plt, "st": st}
                    exec(code, env)
                    if "fig" in env and isinstance(env["fig"], go.Figure):
                        st.plotly_chart(env["fig"], use_container_width=True)
                    elif "plt" in env and plt.get_fignums():
                        st.pyplot(plt.gcf())
                        plt.clf()
                    break
    except Exception as e:
        pass

# ============ UI COMPONENTS ============

def render_auth():
    st.markdown('<h1 class="main-header">🐅 Royal Bengal AI Machine</h1>', unsafe_allow_html=True)
    st.markdown("### 🔐 Secure Access Panel")
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Sign Up"])
    
    with tab2:
        st.markdown("#### Create New Account")
        reg_name = st.text_input("Full Name", key="reg_name")
        reg_email = st.text_input("Email", key="reg_email")
        reg_pass = st.text_input("Password", type="password", key="reg_pass")
        reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm")
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
                    cursor.execute("INSERT INTO users (email, name, password) VALUES (?, ?, ?)", (reg_email.strip().lower(), reg_name.strip(), reg_pass.strip()))
                    conn.commit()
                    conn.close()
                    st.success("✅ Account created! Please login.")
                    st.balloons()
                except sqlite3.IntegrityError:
                    st.error("❌ Email already registered.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
    
    with tab1:
        st.markdown("#### Welcome Back!")
        login_email = st.text_input("Email", key="login_email")
        login_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("🔓 Unlock Dashboard", use_container_width=True):
            if not all([login_email, login_pass]):
                st.error("❌ Please enter both email and password.")
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, password FROM users WHERE email = ?", (login_email.strip().lower(),))
                    user = cursor.fetchone()
                    conn.close()
                    if user and login_pass.strip() == user[1]:
                        st.session_state.logged_in = True
                        st.session_state.user_profile = {"name": user[0], "email": login_email.strip().lower()}
                        st.rerun()
                    else:
                        st.error("❌ Invalid email or password.")
                except Exception as e:
                    st.error(f"❌ Login error: {str(e)}")

def render_sidebar():
    with st.sidebar:
        st.markdown(f"""<div style="text-align:center;padding:1rem;"><h2 style="color:#FF6B35;">🐅 Royal Bengal AI</h2><p style="color:#aaa;">Welcome, {st.session_state.user_profile.get('name', 'User')}!</p></div>""", unsafe_allow_html=True)
        st.markdown("---")
        
        with st.expander("🔑 API Configuration", expanded=True):
            api_key = st.text_input("Groq API Key", type="password", placeholder="Enter Groq API key...")
            if api_key:
                st.session_state.user_api_key = api_key
                st.success("✅ Groq API Key configured!")
            elif get_api_key():
                st.success("✅ Groq API Key found in secrets")
            else:
                st.warning("⚠️ Please add Groq API key")
        
        st.markdown("---")
        if WEB_SEARCH_SUPPORT:
            st.session_state.web_search_enabled = st.checkbox("🌐 Live Web Search", value=st.session_state.get("web_search_enabled", True))
        
        st.markdown("---")
        st.markdown("### 📁 Chat History")
        tabs = [("💬 AI Assistant", "tab1", "messages", "current_session_id_tab1"), ("📊 Math Wave", "tab2", "math_messages", "current_session_id_tab2"), ("📈 Economics", "tab3", "econ_messages", "current_session_id_tab3")]
        for tab_name, tab_id, msg_key, session_key in tabs:
            with st.expander(f"📂 {tab_name}", expanded=False):
                if st.button(f"➕ New Chat", key=f"new_{tab_id}", use_container_width=True):
                    st.session_state[msg_key] = []
                    st.session_state[session_key] = None
                    st.rerun()
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
                        if st.session_state.renaming_session_id == s_id:
                            new_title = st.text_input("New title:", value=title, key=f"rename_input_{s_id}")
                            if st.button("Save", key=f"save_rename_{s_id}"):
                                if rename_session(s_id, new_title):
                                    st.session_state.renaming_session_id = None
                                    st.rerun()
        
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
        
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            for key in ["logged_in", "user_profile", "messages", "math_messages", "econ_messages"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

def render_chat_interface():
    st.markdown('<h1 class="main-header">🐅 Royal Bengal AI Machine</h1>', unsafe_allow_html=True)
    st.markdown(f"""<div style="text-align:center;padding:0.5rem;background:rgba(255,255,255,0.05);border-radius:10px;margin-bottom:1rem;">👋 Welcome, {st.session_state.user_profile.get('name', 'User')}! <span style="background:#4caf50;color:white;padding:0.2rem 0.8rem;border-radius:20px;font-size:0.8rem;">● Online</span></div>""", unsafe_allow_html=True)
    
    groq_key = get_api_key()
    if not groq_key:
        st.warning("⚠️ Groq API key needed for AI features")
    
    tab1, tab2, tab3 = st.tabs(["💬 AI Assistant", "📊 Math Solver", "📈 Economics"])
    
    # Tab 1: AI Assistant
    with tab1:
        st.markdown("### 💬 AI Assistant with Document Support")
        st.info("📄 PDF আপলোড করুন (MinerU Flash Mode - ফ্রি! ১০MB/২০ পৃষ্ঠা পর্যন্ত)")
        
        uploaded_file = st.file_uploader(
            "📎 Upload PDF",
            type=["pdf"],
            key="tab1_uploader",
            help="PDF আপলোড করুন (সর্বোচ্চ ১০MB, ২০ পৃষ্ঠা)"
        )
        
        extracted_text = ""
        
        if uploaded_file:
            file_bytes = uploaded_file.getvalue()
            
            with st.spinner("📖 MinerU দিয়ে PDF পড়া হচ্ছে (ফ্রি!)..."):
                extracted_text = extract_text_with_mineru(file_bytes)
                
                if extracted_text and "⚠️" not in extracted_text:
                    st.success(f"✅ PDF প্রসেস সম্পন্ন! {len(extracted_text)} অক্ষর")
                    with st.expander("📄 এক্সট্র্যাক্ট করা টেক্সট দেখুন"):
                        st.text(extracted_text[:2000] + "..." if len(extracted_text) > 2000 else extracted_text)
                else:
                    st.error(extracted_text)
                    st.info("💡 PDF টি স্ক্যান করা বা ইমেজ-ভিত্তিক হতে পারে। অথবা সাইজ/পৃষ্ঠা ১০MB/২০ এর বেশি।")
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        if prompt := st.chat_input("আপনার প্রশ্ন লিখুন...", key="t1_chat"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            with st.chat_message("assistant"):
                if not groq_key:
                    st.error("⚠️ Groq API key required")
                else:
                    try:
                        with st.spinner("🤔 Thinking..."):
                            context = ""
                            if extracted_text:
                                context += f"📄 Document context:\n{extracted_text}\n\n"
                            
                            if st.session_state.get("web_search_enabled", False):
                                search_result = perform_web_search(prompt)
                                if search_result:
                                    context += search_result + "\n\n"
                            
                            final_prompt = f"{context}User question: {prompt}\n\nPlease provide complete LaTeX code at the end."
                            
                            stream = safe_text_stream(final_prompt, groq_key)
                            full_response = st.write_stream(stream)
                            
                            try_execute_graph(full_response)
                            
                            if "\\documentclass" in full_response:
                                st.markdown("---")
                                st.markdown("### 📝 LaTeX Code to Copy")
                                st.code(full_response, language="latex")
                            
                            session_id = st.session_state.current_session_id_tab1 or str(uuid.uuid4())
                            st.session_state.current_session_id_tab1 = session_id
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                            save_session(session_id, st.session_state.user_profile['email'], prompt[:50], st.session_state.messages, "tab1")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
    
    # Tab 2: Math Solver
    with tab2:
        st.markdown("### 📊 Advanced Math Solver")
        st.info("📝 Math problems with step-by-step LaTeX solutions")
        
        for msg in st.session_state.math_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        if prompt := st.chat_input("গাণিতিক সমস্যা লিখুন...", key="t2_chat"):
            st.session_state.math_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            with st.chat_message("assistant"):
                if not groq_key:
                    st.error("⚠️ Groq API key required")
                else:
                    try:
                        with st.spinner("🧮 Solving..."):
                            context = ""
                            if st.session_state.get("web_search_enabled", False):
                                search_result = perform_web_search(prompt)
                                if search_result:
                                    context += search_result + "\n\n"
                            
                            final_prompt = f"{context}Math problem: {prompt}\n\nPlease provide complete LaTeX code at the end."
                            stream = safe_math_stream(final_prompt, groq_key)
                            full_response = st.write_stream(stream)
                            
                            try_execute_graph(full_response)
                            
                            if "\\documentclass" in full_response:
                                st.markdown("---")
                                st.markdown("### 📝 LaTeX Code to Copy")
                                st.code(full_response, language="latex")
                            
                            session_id = st.session_state.current_session_id_tab2 or str(uuid.uuid4())
                            st.session_state.current_session_id_tab2 = session_id
                            st.session_state.math_messages.append({"role": "assistant", "content": full_response})
                            save_session(session_id, st.session_state.user_profile['email'], prompt[:50], st.session_state.math_messages, "tab2")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
    
    # Tab 3: Economics
    with tab3:
        st.markdown("### 📈 Economics Analysis")
        st.info("📊 Economic analysis with LaTeX formulas and graphs")
        
        for msg in st.session_state.econ_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        
        if prompt := st.chat_input("অর্থনীতির প্রশ্ন লিখুন...", key="t3_chat"):
            st.session_state.econ_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            with st.chat_message("assistant"):
                if not groq_key:
                    st.error("⚠️ Groq API key required")
                else:
                    try:
                        with st.spinner("📈 Analyzing..."):
                            context = ""
                            if st.session_state.get("web_search_enabled", False):
                                search_result = perform_web_search(prompt)
                                if search_result:
                                    context += search_result + "\n\n"
                            
                            final_prompt = f"{context}Economics question: {prompt}\n\nPlease provide complete LaTeX code at the end."
                            stream = safe_econ_stream(final_prompt, groq_key)
                            full_response = st.write_stream(stream)
                            
                            try_execute_graph(full_response)
                            
                            if "\\documentclass" in full_response:
                                st.markdown("---")
                                st.markdown("### 📝 LaTeX Code to Copy")
                                st.code(full_response, language="latex")
                            
                            session_id = st.session_state.current_session_id_tab3 or str(uuid.uuid4())
                            st.session_state.current_session_id_tab3 = session_id
                            st.session_state.econ_messages.append({"role": "assistant", "content": full_response})
                            save_session(session_id, st.session_state.user_profile['email'], prompt[:50], st.session_state.econ_messages, "tab3")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

# ============ MAIN ============
def main():
    if not st.session_state.logged_in:
        render_auth()
        return
    render_sidebar()
    render_chat_interface()
    st.markdown("---")
    st.markdown("""<div style="text-align:center;color:#888;padding:1rem;"><p>Made with ❤️ by Md Mohtasim Billah | 🐅 Royal Bengal AI Machine</p><p style="font-size:0.8rem;">Powered by Groq AI + MinerU (FREE) • PDF Support • LaTeX Export</p></div>""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()