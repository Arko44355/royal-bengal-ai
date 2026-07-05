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

# 🛡️ Library Imports with Safeguards
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

# 1. Page Configuration
st.set_page_config(page_title="Royal Bengal AI Machine", page_icon="🐅", layout="wide")

# 2. Database Management
def get_db_connection():
    return sqlite3.connect("users.db", timeout=10, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY, name TEXT, password TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY, email TEXT, title TEXT, 
            messages_json TEXT, tab_name TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 3. Session State Initialization
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "math_messages" not in st.session_state:
    st.session_state.math_messages = []
if "econ_messages" not in st.session_state:
    st.session_state.econ_messages = []

# Session Tracking
if "current_session_id_tab1" not in st.session_state:
    st.session_state.current_session_id_tab1 = None
if "current_session_id_tab2" not in st.session_state:
    st.session_state.current_session_id_tab2 = None
if "current_session_id_tab3" not in st.session_state:
    st.session_state.current_session_id_tab3 = None
if "renaming_session_id" not in st.session_state:
    st.session_state.renaming_session_id = None

# 4. Sidebar Controller Panel
with st.sidebar:
    st.header("🎛️ Control Panel")
    
    st.subheader("🔑 API Key Controller")
    user_key = st.text_input("Groq API Key (Optional)", type="password")
    
    if user_key.strip():
        GROQ_API_KEY = user_key.strip()
    elif "GROQ_API_KEY" in st.secrets:
        GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    else:
        GROQ_API_KEY = "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"

    voice_on = st.checkbox("🎙️ ভয়েস অ্যাসিস্ট্যান্ট (Windows)")
    
    if WEB_SEARCH_SUPPORT:
        web_search_enabled = st.checkbox("🌐 লাইভ সার্চ অন করুন", value=True)
    else:
        web_search_enabled = False
    
    if st.button("Logout 🚪", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.messages = []
        st.session_state.math_messages = []
        st.session_state.econ_messages = []
        st.session_state.current_session_id_tab1 = None
        st.session_state.current_session_id_tab2 = None
        st.session_state.current_session_id_tab3 = None
        st.rerun()
        
    st.markdown("---")
    if st.button("🔄 Quick Rerun", use_container_width=True):
        st.rerun()
    if st.button("🧹 Clear Cache", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.toast("ক্যাশ সাফ করা হয়েছে।")
        st.rerun()

# 5. Global Client Init
client = None
if GROQ_SUPPORT and GROQ_API_KEY:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        st.sidebar.error(f"Client Init Error: {e}")

# Image Compression Utility
def process_uploaded_image(file_bytes):
    try:
        img = Image.open(BytesIO(file_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((600, 600))
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=60)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except:
        return ""

# Live Web Search
def perform_web_search(query, max_results=5):
    if not WEB_SEARCH_SUPPORT:
        return ""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return ""
        context = "\n🌐 [লাইভ সার্চ ফলাফল]:\n"
        for i, r in enumerate(results, 1):
            context += f"উৎস [{i}]: {r.get('title')}\nতথ্য: {r.get('body')}\n\n"
        return context
    except:
        return ""

# Database CRUD Operations for Session History
def save_session(session_id, email, title, messages, tab_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO chat_sessions (session_id, email, title, messages_json, tab_name, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (session_id, email, title, json.dumps(messages), tab_name))
        conn.commit()
        conn.close()
    except:
        pass

def get_sessions(email, tab_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT session_id, title, messages_json FROM chat_sessions WHERE email = ? AND tab_name = ? ORDER BY updated_at DESC', (email, tab_name))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except:
        return []

def delete_session(session_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM chat_sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
    except:
        pass

def rename_session(session_id, new_title):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE chat_sessions SET title = ? WHERE session_id = ?', (new_title, session_id))
        conn.commit()
        conn.close()
    except:
        pass

# Authentication Middleware Interface
if not st.session_state.logged_in:
    st.title("🔐 Secure Access Panel")
    auth_tab1, auth_tab2 = st.tabs(["🔑 Login", "📝 Sign Up"])
    
    with auth_tab2:
        reg_name = st.text_input("Name", key="reg_name")
        reg_email = st.text_input("Email", key="reg_email")
        reg_pass = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Create Account"):
            if reg_email and reg_pass:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO users (email, name, password) VALUES (?, ?, ?)", (reg_email.strip(), reg_name.strip(), reg_pass.strip()))
                    conn.commit()
                    conn.close()
                    st.success("অ্যাকাউন্ট তৈরি হয়েছে! লগইন করুন।")
                except sqlite3.IntegrityError:
                    st.error("ইমেইলটি ইতিমধ্যে নিবন্ধিত।")
            else:
                st.error("সব ঘর পূরণ করুন।")
                
    with auth_tab1:
        login_email = st.text_input("Email", key="login_email")
        login_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Unlock Dashboard"):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name, password FROM users WHERE email = ?", (login_email.strip(),))
            user = cursor.fetchone()
            conn.close()
            if user and login_pass.strip() == user[1]:
                st.session_state.logged_in = True
                st.session_state.user_profile = {"name": user[0], "email": login_email.strip()}
                st.rerun()
            else:
                st.error("ভুল ইমেইল বা পাসওয়ার্ড।")
    st.stop()

# --- Main Application Interface ---
st.title(f"🐅 Royal Bengal AI Machine — Active Session: {st.session_state.user_profile['name']}")

# Render History Items inside Sidebar Safely
with st.sidebar:
    st.markdown("---")
    st.subheader("📁 সংরক্ষিত চ্যাট হিস্ট্রি")
    
    for t_idx, (t_name, m_key, s_key) in enumerate([("tab1", "messages", "current_session_id_tab1"), ("tab2", "math_messages", "current_session_id_tab2"), ("tab3", "econ_messages", "current_session_id_tab3")], 1):
        with st.sidebar.expander(f"Category {t_idx} History", expanded=False):
            if st.button("➕ New Chat Instance", key=f"new_{t_name}"):
                st.session_state[m_key] = []
                st.session_state[s_key] = None
                st.rerun()
            for s_id, title, msg_json in get_sessions(st.session_state.user_profile['email'], t_name):
                col1, col2 = st.columns([0.8, 0.2])
                with col1:
                    if st.button(title, key=f"load_{t_name}_{s_id}", use_container_width=True):
                        st.session_state[m_key] = json.loads(msg_json)
                        st.session_state[s_key] = s_id
                        st.rerun()
                with col2:
                    if st.button("🗑️", key=f"del_{t_name}_{s_id}"):
                        delete_session(s_id)
                        if st.session_state[s_key] == s_id:
                            st.session_state[m_key] = []
                            st.session_state[s_key] = None
                        st.rerun()

# Create App Navigation Tabs
tab1, tab2, tab3, tab4 = st.tabs(["💬 AI Assistant & Docs", "📊 Math Wave", "📈 Economics Demand", "🎨 AI Image"])

def run_embedded_graph(full_response):
    if any(k in full_response for k in ["fig =", "go.Figure", "plt."]):
        try:
            code_block = full_response.split("```python")[1].split("```")[0] if "```python" in full_response else (full_response.split("```")[1].split("```")[0] if "```" in full_response else full_response)
            code_block = code_block.replace("fig.show()", "").replace("plt.show()", "")
            env = {}
            env.update(globals())
            env.update({"np": np, "go": go, "px": px, "plt": plt, "st": st})
            exec(code_block, env)
            if "fig" in env:
                st.plotly_chart(env["fig"], use_container_width=True)
            elif "plt" in env and plt.get_fignums():
                st.pyplot(plt.gcf())
                plt.clf()
        except:
            pass

# 💬 Tab 1: AI Assistant (Vision Support)
with tab1:
    st.subheader("📁 মাল্টিমোডাল ফাইল ও ইমেজ এনালাইজার")
    uploaded_file = st.file_uploader("Upload PDF or Image", type=["pdf", "txt", "png", "jpg", "jpeg"])
    
    extracted_text, image_base64 = "", ""
    if uploaded_file:
        fb = uploaded_file.getvalue()
        if uploaded_file.name.lower().endswith(".pdf") and PDF_SUPPORT:
            with pdfplumber.open(BytesIO(fb)) as pdf:
                extracted_text = "\n".join([p.extract_text() for p in pdf.pages if p.extract_text()])
            st.info("📄 PDF কনটেন্ট লোড করা হয়েছে।")
        elif uploaded_file.name.split('.')[-1].lower() in ["png", "jpg", "jpeg"]:
            st.image(fb, width=250)
            image_base64 = process_uploaded_image(fb)

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if u_input := st.chat_input("Ask anything...", key="t1_chat"):
        st.session_state.messages.append({"role": "user", "content": u_input})
        with st.chat_message("user"): st.markdown(u_input)
        
        with st.chat_message("assistant"):
            if not client:
                st.error("API client configuration missing.")
            else:
                try:
                    s_info = perform_web_search(u_input) if web_search_enabled else ""
                    prompt = f"{s_info}\nContext:\n{extracted_text}\n\nQuestion: {u_input}" if extracted_text else (f"{s_info}\nQuestion: {u_input}" if s_info else u_input)
                    
                    if image_base64:
                        res = client.chat.completions.create(
                            model="llama-3.2-11b-vision-preview",
                            messages=[{"role": "user", "content": [{"type": "text", "text": f"Provide comprehensive solution in Bengali. {u_input}"}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}]}],
                            stream=False
                        )
                        full_res = res.choices[0].message.content
                        st.markdown(full_res)
                    else:
                        # ⚡ DeepSeek-style UI Real-time Token Streaming Block
                        res_stream = client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[{"role": "system", "content": "You are Royal Bengal AI, answering elegantly in Bengali with precise technical execution."}, {"role": "user", "content": prompt}],
                            stream=True
                        )
                        full_res = st.write_stream(res_stream)
                    
                    run_embedded_graph(full_res)
                    
                    s_id = st.session_state.current_session_id_tab1 or str(uuid.uuid4())
                    st.session_state.current_session_id_tab1 = s_id
                    st.session_state.messages.append({"role": "assistant", "content": full_res})
                    save_session(s_id, st.session_state.user_profile['email'], u_input[:30], st.session_state.messages, "tab1")
                except Exception as e:
                    st.error(f"Error generation: {e}")

# 📊 Tab 2: Math Wave Solver (With DeepSeek Streaming)
with tab2:
    st.subheader("📊 Math Wave Core")
    for msg in st.session_state.math_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
        
    if m_input := st.chat_input("Enter math equation...", key="t2_chat"):
        st.session_state.math_messages.append({"role": "user", "content": m_input})
        with st.chat_message("user"): st.markdown(m_input)
        
        with st.chat_message("assistant"):
            if not client: st.error("Client Error.")
            else:
                try:
                    s_info = perform_web_search(m_input) if web_search_enabled else ""
                    m_stream = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "system", "content": "You are an expert Math professor. Output detailed LaTeX steps using $$. If rendering plot, generate valid python plotly code with fig object."}, {"role": "user", "content": f"{s_info}\nMath Query: {m_input}"}],
                        stream=True
                    )
                    # Real-time token by token print output on screen
                    full_res = st.write_stream(m_stream)
                    run_embedded_graph(full_res)
                    
                    s_id = st.session_state.current_session_id_tab2 or str(uuid.uuid4())
                    st.session_state.current_session_id_tab2 = s_id
                    st.session_state.math_messages.append({"role": "assistant", "content": full_res})
                    save_session(s_id, st.session_state.user_profile['email'], m_input[:30], st.session_state.math_messages, "tab2")
                except Exception as e:
                    st.error(f"Execution failed: {e}")

# 📈 Tab 3: Economics Analyzer (With DeepSeek Streaming)
with tab3:
    st.subheader("📈 Economics Demand Analyzer")
    for msg in st.session_state.econ_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
        
    if e_input := st.chat_input("Enter economics problem...", key="t3_chat"):
        st.session_state.econ_messages.append({"role": "user", "content": e_input})
        with st.chat_message("user"): st.markdown(e_input)
        
        with st.chat_message("assistant"):
            if not client: st.error("Client offline.")
            else:
                try:
                    s_info = perform_web_search(e_input) if web_search_enabled else ""
                    e_stream = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "system", "content": "You are an Economics Professor. Explain curves with text first, then generate valid plotly visualization code using fig variable."}, {"role": "user", "content": f"{s_info}\nEcon Query: {e_input}"}],
                        stream=True
                    )
                    full_res = st.write_stream(e_stream)
                    run_embedded_graph(full_res)
                    
                    s_id = st.session_state.current_session_id_tab3 or str(uuid.uuid4())
                    st.session_state.current_session_id_tab3 = s_id
                    st.session_state.econ_messages.append({"role": "assistant", "content": full_res})
                    save_session(s_id, st.session_state.user_profile['email'], e_input[:30], st.session_state.econ_messages, "tab3")
                except Exception as e:
                    st.error(f"Error processing: {e}")

# 🎨 Tab 4: AI Image Framework
with tab4:
    st.subheader("🎨 AI Image Generation Hub")
    st.write("Image model cloud infrastructure connection establishing...")