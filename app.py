import streamlit as st
import requests
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import matplotlib
matplotlib.use('Agg') # লিনাক্স ক্লাউড সার্ভারের জন্য নন-ইন্টারেক্টিভ ব্যাকএন্ড সেটআপ
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO
import os
import sqlite3
import base64
import json
import uuid

# 🛡️ বুলেটপ্রুফ ইমপোর্ট গার্ডরেল (কোনো প্যাকেজ মিসিং থাকলেও অ্যাপ ক্র্যাশ করবে না)
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

# ১. পেজ কনফিগারেশন
st.set_page_config(page_title="Royal Bengal AI Machine", page_icon="🐅", layout="wide")

# 🔑 Groq API Key সেটআপ
GROQ_API_KEY = "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"
client = None
if GROQ_SUPPORT:
    try:
        client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        st.error(f"Groq Client ইনিশিয়েলাইজ করতে সমস্যা: {e}")

# 🗄️ ডেটাবেস সেটআপ (Timeout যুক্ত করে থ্রেড-সেফ করা হয়েছে)
def get_db_connection():
    return sqlite3.connect("users.db", timeout=10, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT,
            password TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            email TEXT,
            title TEXT,
            messages_json TEXT,
            tab_name TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ২. সেশন স্টেট ইনিশিয়েলাইজেশন
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

# চ্যাট সেশন আইডি ট্র্যাকিং স্টেট
if "current_session_id_tab1" not in st.session_state:
    st.session_state.current_session_id_tab1 = None
if "current_session_id_tab2" not in st.session_state:
    st.session_state.current_session_id_tab2 = None
if "current_session_id_tab3" not in st.session_state:
    st.session_state.current_session_id_tab3 = None
if "renaming_session_id" not in st.session_state:
    st.session_state.renaming_session_id = None

# 📸 পয়েন্টার ও মেমোরি সেফ আল্ট্রা-কম্প্রেসর (ইমেজ সাইজ কমিয়ে ৩০-৪০ কিলোবাইটে আনবে)
def process_uploaded_image(file_bytes):
    try:
        img = Image.open(BytesIO(file_bytes))
        # ট্রান্সপারেন্ট বা PNG হলে RGB তে রূপান্তর
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # এআই রেট লিমিট এড়াতে ছবিটিকে আরও ছোট করা হলো (600x600)
        img.thumbnail((600, 600))
        buffered = BytesIO()
        # কোয়ালিটি ৬৫% করে সাইজ অত্যন্ত কমানো হলো যেন ক্লাউড রেট লিমিট না খায়
        img.save(buffered, format="JPEG", quality=65)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        st.error(f"⚠️ ইমেজ প্রসেস করতে সমস্যা হয়েছে বন্ধু: {e}")
        return ""

# 🌐 সেফ লাইভ ওয়েব সার্চ করার ফাংশন
def perform_web_search(query, max_results=5):
    if not WEB_SEARCH_SUPPORT:
        return ""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return ""
        search_context = "\n🌐 [লাইভ ইন্টারনেট ও গুগল অনুসন্ধান ফলাফল]:\n"
        for i, r in enumerate(results, 1):
            search_context += f"উৎস [{i}]: {r.get('title')}\nলিংক: {r.get('href')}\nতথ্যসার: {r.get('body')}\n\n"
        return search_context
    except Exception as e:
        return ""

# 👁️ ডাইরেক্ট কানেকশন ও ফলব্যাক চেইন সহ ইমেজ এআই ফাংশন (অত্যন্ত উন্নত ও ক্যাশ-সেফ স্ট্রিম পার্সার)
def vision_response_generator(image_base64, user_prompt):
    models_to_try = ["llama-3.2-11b-vision-preview", "llama-3.2-90b-vision-preview"]
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    text_content = (
        "You are Royal Bengal AI Machine, an Elite Academic Scholar, Research Professor, and close friend of the user created by Md Mohtasim Billah. "
        "Default to replying in beautiful Bengali script. However, if the user explicitly asks you to reply in English or writes in English, reply in English. "
        "Look at the image and provide an EXTREMELY detailed, academic explanation, step-by-step calculations, or rigorous proofs. "
        f"User Question: {user_prompt if user_prompt else 'এই ছবিটিতে কী আছে বিশদভাবে বুঝিয়ে বলো বন্ধু।'}"
    )

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
                break # সফলভাবে স্ট্রিম হয়েছে, লুপ থেকে বের হওয়া হলো
            else:
                last_error = f"Model {model} failed with status {response.status_code}: {response.text}"
        except Exception as e:
            last_error = f"Model {model} error: {str(e)}"
            
    if not success:
        yield f"✨ দুঃখিত ভাই, এআই ক্লাউড ইঞ্জিন ছবি প্রসেস করতে পারেনি। সর্বশেষ সমস্যা: {last_error}"

# 🗄️ চ্যাট হিস্ট্রি ডাটাবেস ফাংশনসমূহ (থ্রেড-সেফ)
def save_session(session_id, email, title, messages, tab_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        messages_json = json.dumps(messages)
        cursor.execute('''
            INSERT OR REPLACE INTO chat_sessions (session_id, email, title, messages_json, tab_name, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (session_id, email, title, messages_json, tab_name))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def get_sessions(email, tab_name):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT session_id, title, messages_json FROM chat_sessions 
            WHERE email = ? AND tab_name = ? 
            ORDER BY updated_at DESC
        ''', (email, tab_name))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return []

def delete_session(session_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM chat_sessions WHERE session_id = ?', (session_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def rename_session(session_id, new_title):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE chat_sessions SET title = ? WHERE session_id = ?', (new_title, session_id))
        conn.commit()
        conn.close()
    except Exception as e:
        pass


# লগইন এবং সাইনআপ ইন্টারফেস
if not st.session_state.logged_in:
    st.title("🔐 Royal Bengal AI - Secure Access Panel")
    st.write("স্বাগতম! অনুগ্রহ করে আপনার অ্যাকাউন্ট দিয়ে লগইন করুন অথবা একটি নতুন অ্যাকাউন্ট তৈরি করুন।")
    
    auth_tab1, auth_tab2 = st.tabs(["🔑 অ্যাকাউন্টে লগইন করুন", "📝 নতুন অ্যাকাউন্ট তৈরি করুন"])
    
    with auth_tab2:
        st.subheader("নতুন অ্যাকাউন্ট তৈরি করুন")
        reg_name = st.text_input("আপনার সম্পূর্ণ নাম (Full Name)", key="reg_name", placeholder="যেমন: Md Mohtasim Billah")
        reg_email = st.text_input("গুগল ইমেইল (Google Email)", key="reg_email", placeholder="যেমন: mohtasim@gmail.com")
        reg_pass = st.text_input("পাসওয়ার্ড (Password)", type="password", key="reg_pass", placeholder="একটি স্ট্রং পাসওয়ার্ড দিন")
        
        if st.button("Sign Up & Create Account 🚀"):
            if reg_email and reg_pass:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO users (email, name, password) VALUES (?, ?, ?)", (reg_email.strip(), reg_name.strip(), reg_pass.strip()))
                    conn.commit()
                    conn.close()
                    st.success("🎉 অ্যাকাউন্ট সফলভাবে তৈরি হয়েছে! পাশের ট্যাবে গিয়ে লগইন করুন।")
                except sqlite3.IntegrityError:
                    st.error("⚠️ এই ইমেইল দিয়ে অলরেডি অ্যাকাউন্ট তৈরি করা আছে!")
                except Exception as e:
                    st.error(f"ডাটাবেস এরর: {e}")
            else:
                st.error("⚠️ দয়া করে ইমেইল এবং পাসওয়ার্ড সঠিকভাবে পূরণ করুন।")
                
    with auth_tab1:
        st.subheader("অ্যাকাউন্টে লগইন করুন")
        login_email = st.text_input("আপনার গুগল ইমেইল (Google Email)", key="login_email", placeholder="যেমন: mohtasim@gmail.com")
        login_pass = st.text_input("পাসওয়ার্ড (Password)", type="password", key="login_pass", placeholder="আপনার পাসওয়ার্ডটি লিখুন")
        
        if st.button("Login & Unlock Machine 🔓"):
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT name, password FROM users WHERE email = ?", (login_email.strip(),))
                user = cursor.fetchone()
                conn.close()
                
                if user and login_pass.strip() == user[1]:
                    st.session_state.logged_in = True
                    st.session_state.user_profile = {"name": user[0], "email": login_email.strip()}
                    st.toast("🔓 Access Granted! Welcome back.", icon="🐅")
                    st.rerun()
                else:
                    st.error("❌ ভুল ইমেইল বা পাসওয়ার্ড! অনুগ্রহ করে সঠিক তথ্য দিন।")
            except Exception as e:
                st.error(f"লগইন করতে সমস্যা হয়েছে: {e}")
    st.stop()

# --- মেইন অ্যাপ্লিকেশন ইন্টারফেস ---
st.title(f"🐅 Royal Bengal AI Machine - Welcome {st.session_state.user_profile['name']}!")

# সাইডবার
with st.sidebar:
    st.header("🎛️ Control Panel")
    voice_on = st.checkbox("🎙️ ভয়েস অ্যাসিস্ট্যান্ট অন করুন (Windows Only)")
    
    # গুগল লাইভ সার্চ অপশন (ইন্টারনেট সার্চ প্যাকেজ ইনস্টল থাকলে সচল হবে)
    if WEB_SEARCH_SUPPORT:
        web_search_enabled = st.checkbox("🌐 গুগল ও ইন্টারনেট লাইভ সার্চ অন করুন", value=True, help="এআই প্রতিটি উত্তরের জন্য লাইভ ইন্টারনেট ব্রাউজ করে নিখুঁত ও আপ-টু-ডেট ডাটা সংগ্রহ করবে।")
    else:
        st.warning("⚠️ ক্লাউড সার্ভারে লাইভ সার্চ এই মুহূর্তে নিষ্ক্রিয় আছে বন্ধু। তবে অফলাইন রিসার্চ ইঞ্জিন সচল আছে!")
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
    st.subheader("📱 মোবাইল কুইক কন্ট্রোল")
    
    if st.button("🔄 অ্যাপ রিফ্রেশ করুন (Rerun)", use_container_width=True):
        st.rerun()
        
    if st.button("🧹 ক্যাশ সাফ করুন (Clear Cache)", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.toast("ক্যাশ সফলভাবে সাফ করা হয়েছে ভাই!", icon="🗑️")
        st.rerun()
        
    st.markdown("---")
    st.subheader("📁 আমার সংরক্ষিত চ্যাট হিস্ট্রি")
    
    # ক্যাটাগরি ১: AI Assistant চ্যাট হিস্ট্রি
    with st.sidebar.expander("💬 AI Assistant চ্যাটসমূহ", expanded=False):
        if st.button("➕ নতুন AI চ্যাট শুরু করুন", key="new_chat_t1", use_container_width=True):
            st.session_state.messages = []
            st.session_state.current_session_id_tab1 = None
            st.rerun()
            
        sessions_t1 = get_sessions(st.session_state.user_profile['email'], "tab1")
        for s_id, title, msg_json in sessions_t1:
            col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
            is_active = (s_id == st.session_state.current_session_id_tab1)
            btn_label = f"📍 {title}" if is_active else title
            
            with col1:
                if st.button(btn_label, key=f"load_t1_{s_id}", use_container_width=True, help="চ্যাটটি লোড করুন"):
                    st.session_state.messages = json.loads(msg_json)
                    st.session_state.current_session_id_tab1 = s_id
                    st.rerun()
            with col2:
                if st.button("✏️", key=f"ren_btn_t1_{s_id}", help="নাম পরিবর্তন করুন"):
                    st.session_state.renaming_session_id = s_id
                    st.rerun()
            with col3:
                if st.button("🗑️", key=f"del_t1_{s_id}", help="মুছে ফেলুন"):
                    delete_session(s_id)
                    if is_active:
                        st.session_state.messages = []
                        st.session_state.current_session_id_tab1 = None
                    st.rerun()
                    
            if st.session_state.renaming_session_id == s_id:
                new_name = st.text_input("নতুন নাম দিন:", value=title, key=f"new_name_val_t1_{s_id}")
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("সংরক্ষণ", key=f"save_ren_t1_{s_id}", use_container_width=True):
                        if new_name.strip():
                            rename_session(s_id, new_name.strip())
                        st.session_state.renaming_session_id = None
                        st.rerun()
                with col_cancel:
                    if st.button("বাতিল", key=f"cancel_ren_t1_{s_id}", use_container_width=True):
                        st.session_state.renaming_session_id = None
                        st.rerun()

    # ক্যাটাগরি ২: Math Wave Solver হিস্ট্রি
    with st.sidebar.expander("📊 Math Wave চ্যাটসমূহ", expanded=False):
        if st.button("➕ নতুন Math চ্যাট শুরু করুন", key="new_chat_t2", use_container_width=True):
            st.session_state.math_messages = []
            st.session_state.current_session_id_tab2 = None
            st.rerun()
            
        sessions_t2 = get_sessions(st.session_state.user_profile['email'], "tab2")
        for s_id, title, msg_json in sessions_t2:
            col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
            is_active = (s_id == st.session_state.current_session_id_tab2)
            btn_label = f"📍 {title}" if is_active else title
            
            with col1:
                if st.button(btn_label, key=f"load_t2_{s_id}", use_container_width=True, help="চ্যাটটি লোড করুন"):
                    st.session_state.math_messages = json.loads(msg_json)
                    st.session_state.current_session_id_tab2 = s_id
                    st.rerun()
            with col2:
                if st.button("✏️", key=f"ren_btn_t2_{s_id}", help="নাম পরিবর্তন করুন"):
                    st.session_state.renaming_session_id = s_id
                    st.rerun()
            with col3:
                if st.button("🗑️", key=f"del_t2_{s_id}", help="মুছে ফেলুন"):
                    delete_session(s_id)
                    if is_active:
                        st.session_state.math_messages = []
                        st.session_state.current_session_id_tab2 = None
                    st.rerun()
                    
            if st.session_state.renaming_session_id == s_id:
                new_name = st.text_input("নতুন নাম দিন:", value=title, key=f"new_name_val_t2_{s_id}")
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("সংরক্ষণ", key=f"save_ren_t2_{s_id}", use_container_width=True):
                        if new_name.strip():
                            rename_session(s_id, new_name.strip())
                        st.session_state.renaming_session_id = None
                        st.rerun()
                with col_cancel:
                    if st.button("বাতিল", key=f"cancel_ren_t2_{s_id}", use_container_width=True):
                        st.session_state.renaming_session_id = None
                        st.rerun()

    # ক্যাটাগরি ৩: Economics Demand হিস্ট্রি
    with st.sidebar.expander("📈 Economics চ্যাটসমূহ", expanded=False):
        if st.button("➕ নতুন Economics চ্যাট শুরু করুন", key="new_chat_t3", use_container_width=True):
            st.session_state.econ_messages = []
            st.session_state.current_session_id_tab3 = None
            st.rerun()
            
        sessions_t3 = get_sessions(st.session_state.user_profile['email'], "tab3")
        for s_id, title, msg_json in sessions_t3:
            col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
            is_active = (s_id == st.session_state.current_session_id_tab3)
            btn_label = f"📍 {title}" if is_active else title
            
            with col1:
                if st.button(btn_label, key=f"load_t3_{s_id}", use_container_width=True, help="চ্যাটটি লোড করুন"):
                    st.session_state.econ_messages = json.loads(msg_json)
                    st.session_state.current_session_id_tab3 = s_id
                    st.rerun()
            with col2:
                if st.button("✏️", key=f"ren_btn_t3_{s_id}", help="নাম পরিবর্তন করুন"):
                    st.session_state.renaming_session_id = s_id
                    st.rerun()
            with col3:
                if st.button("🗑️", key=f"del_t3_{s_id}", help="মুছে ফেলুন"):
                    delete_session(s_id)
                    if is_active:
                        st.session_state.econ_messages = []
                        st.session_state.current_session_id_tab3 = None
                    st.rerun()
                    
            if st.session_state.renaming_session_id == s_id:
                new_name = st.text_input("নতুন নাম দিন:", value=title, key=f"new_name_val_t3_{s_id}")
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("সংরক্ষণ", key=f"save_ren_t3_{s_id}", use_container_width=True):
                        if new_name.strip():
                            rename_session(s_id, new_name.strip())
                        st.session_state.renaming_session_id = None
                        st.rerun()
                with col_cancel:
                    if st.button("বাতিল", key=f"cancel_ren_t3_{s_id}", use_container_width=True):
                        st.session_state.renaming_session_id = None
                        st.rerun()


# প্রধান ফিচার ট্যাব সমূহ
tab1, tab2, tab3, tab4 = st.tabs(["💬 AI Assistant & Upload Solver", "📊 Math Wave", "📈 Economics Demand", "🎨 AI Image Generator"])

# helper ফাংশন গ্রাফ এক্সিকিউট করার জন্য
def try_execute_graph(full_response):
    if "fig =" in full_response or "go.Figure" in full_response or "plt." in full_response:
        try:
            if "```python" in full_response:
                code_block = full_response.split("```python")[1].split("```")[0]
            elif "```" in full_response:
                code_block = full_response.split("```")[1].split("```")[0]
            else:
                code_block = full_response
            
            code_block = code_block.replace("fig.show()", "")
            code_block = code_block.replace("plt.show()", "")

            exec_env = {}
            exec_env.update(globals())
            exec_env.update({
                "np": np,
                "go": go,
                "px": px,
                "plt": plt,
                "st": st
            })
            
            exec(code_block, exec_env)
            
            if "fig" in exec_env:
                st.plotly_chart(exec_env["fig"], use_container_width=True)
            elif "plt" in exec_env and plt.get_fignums():
                st.pyplot(plt.gcf())
                plt.clf()
        except Exception as e:
            st.warning(f"⚠️ গ্রাফ রেন্ডার করতে সমস্যা হয়েছে বন্ধু। ট্রাই করছি... এরর: {e}")

# 📂 ১. ফাইল ও ইমেজ আপলোড সমাধান ট্যাব
with tab1:
    st.subheader("📁 ডকুমেন্ট/স্ক্রিনশট আপলোড এবং সমাধান প্যানেল")
    uploaded_file = st.file_uploader("PDF, টেক্সট ফাইল অথবা গণিতের স্ক্রিনশট এখানে আপলোড করুন:", type=["pdf", "txt", "png", "jpg", "jpeg"], key="tab1_uploader")
    
    extracted_context = ""
    image_base64 = ""
    
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue() # একদম শুরুতে ডাইরেক্ট বাইট স্ট্রিম কপি করা হচ্ছে
        
        if uploaded_file.name.lower().endswith(".pdf") and PDF_SUPPORT:
            try:
                with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                    extracted_context = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
                st.info(f"📄 PDF থেকে তথ্য নেওয়া হয়েছে ({len(extracted_context)} অক্ষরে)")
            except Exception as e:
                st.error(f"PDF রিড করতে সমস্যা হয়েছে: {e}")
        elif uploaded_file.name.split('.')[-1].lower() in ["png", "jpg", "jpeg"]:
            st.image(file_bytes, caption="আপলোড করা স্ক্রিনশট/ছবি", width=300)
            # রিসাইজ এবং অত্যন্ত কম্প্রেস করে বেস৬৪ জেনারেট করা হচ্ছে
            image_base64 = process_uploaded_image(file_bytes)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("আপনার প্রশ্নটি লিখুন বা আপলোড করা ফাইলটি ব্যাখ্যা করতে বলুন...", key="tab1_chat"):
        final_prompt = user_input
        
        # 🌐 গুগল সার্চ করা হচ্ছে যদি অপশন অন থাকে
        search_info = ""
        if web_search_enabled and WEB_SEARCH_SUPPORT:
            with st.spinner("🌐 গুগল ও ইন্টারনেট ব্রাউজ করে গবেষণা করা হচ্ছে... অনুগ্রহ করে একটু অপেক্ষা করুন..."):
                search_info = perform_web_search(user_input)

        if extracted_context:
            final_prompt = f"Context from uploaded file:\n{extracted_context}\n\n{search_info}\nUser Question: {user_input}"
        elif search_info:
            final_prompt = f"{search_info}\nUser Question: {user_input}"
            
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            if image_base64:
                # 👁️ ইমেজ থাকলে সরাসরি HTTP POST কানেকশন দিয়ে ২-মডেল মেগা চেইনে সমাধান আনা হবে
                full_response = st.write_stream(vision_response_generator(image_base64, user_input))
            else:
                # 💬 শুধু টেক্সটের ক্ষেত্রে নরমাল Groq SDK ব্যবহার হবে
                def response_generator():
                    try:
                        if not client:
                            yield "⚠️ দুঃখিত ভাই, এআই ইঞ্জিন এই মুহূর্তে সচল নেই। লাইব্রেরি আপলোড সম্পন্ন হতে দিন।"
                            return
                        response = client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {
                                    "role": "system", 
                                    "content": (
                                        "You are Royal Bengal AI Machine, an Elite Academic Scholar, Research Professor, and close friend of the user created by Md Mohtasim Billah. "
                                        "CRITICAL INSTRUCTION: Your primary goal is to provide **highly detailed, comprehensive, exhaustive, and deeply researched answers** on all subjects (Science, Humanities, Arts, Business Studies, History, Mathematics, etc.). "
                                        "Never write short or medium summaries unless explicitly requested. Always write comprehensive solutions like a university-level lecture note or textbook. "
                                        "Structure your answers using professional Markdown headings, bullet points, and numbered lists. Include definitions, historical contexts, core theories, step-by-step math breakdowns, case studies/examples, and robust conclusions. "
                                        "If Web Search Results are provided, analyze and synthesize them masterfully, cite the key facts, and present the most accurate, comprehensive, and up-to-date answer. "
                                        "Default to replying in beautiful Bengali script. However, if the user requests English or writes in English, you MUST reply in highly articulate English. Wrap all mathematical or scientific formulas in LaTeX display style using $$."
                                    )
                                },
                                {"role": "user", "content": final_prompt}
                            ],
                            stream=True
                        )
                        for chunk in response:
                            content = chunk.choices[0].delta.content
                            if content: yield content
                    except Exception as e:
                        yield f"✨ ক্লাউড এপিআই রেসপন্স করতে পারেনি ভাই। এরর: {e}"

                full_response = st.write_stream(response_generator())
                
            if "$$" in full_response:
                try: st.latex(full_response.split("$$")[1])
                except: pass
            try_execute_graph(full_response)
            
            # --- ডাটাবেসে সেভ করার মেকানিজম ---
            session_id = st.session_state.current_session_id_tab1
            if not session_id:
                session_id = str(uuid.uuid4())
                st.session_state.current_session_id_tab1 = session_id
                title = user_input[:30] + ("..." if len(user_input) > 30 else "")
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT title FROM chat_sessions WHERE session_id = ?", (session_id,))
                    row = cursor.fetchone()
                    conn.close()
                    title = row[0] if row else (user_input[:30] + ("..." if len(user_input) > 30 else ""))
                except:
                    title = user_input[:30] + ("..." if len(user_input) > 30 else "")
            
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            save_session(session_id, st.session_state.user_profile['email'], title, st.session_state.messages, "tab1")
            st.rerun()

# 📊 ২. Math Wave Solver ট্যাব
with tab2:
    st.subheader("📊 Math Wave Solver")
    st.write("এখানে আপনি গণিত, ক্যালকুলাস বা তরঙ্গ সংক্রান্ত যেকোনো প্রশ্ন করতে পারেন। AI আপনার জন্য লাইভ গ্রাফ এঁকে দেবে।")
    
    for message in st.session_state.math_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
    if math_input := st.chat_input("গণিত বা তরঙ্গের সমীকরণটি লিখুন (যেমন: sin(x) এর গ্রাফ আঁকো)...", key="tab2_chat"):
        st.session_state.math_messages.append({"role": "user", "content": math_input})
        with st.chat_message("user"):
            st.markdown(math_input)
            
        with st.chat_message("assistant"):
            # 🌐 ম্যাথের জন্যও লাইভ সার্চ করা হচ্ছে
            search_info = ""
            if web_search_enabled and WEB_SEARCH_SUPPORT:
                with st.spinner("🌐 গাণিতিক তথ্য গুগলে অনুসন্ধান করা হচ্ছে..."):
                    search_info = perform_web_search(math_input)
            
            final_math_prompt = math_input
            if search_info:
                final_math_prompt = f"{search_info}\nUser Question: {math_input}"

            def math_response_generator():
                try:
                    if not client:
                        yield "⚠️ এআই লাইব্রেরি লোড হচ্ছে।"
                        return
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {
                                "role": "system", 
                                "content": (
                                    "You are an Elite Mathematician and University Math Professor. "
                                    "Your goal is to provide EXTREMELY thorough, detailed, and rigorous mathematical solutions. "
                                    "Explain the mathematical principles step-by-step with proofs, theorems, and real-world applications. "
                                    "Always write the equations in LaTeX style using $$. "
                                    "Default to replying in Bengali script. However, if the user asks in English or requests English, you MUST reply in English. "
                                    "CRITICAL: If the user wants a graph, you MUST write python code using plotly.graph_objects as go and numpy as np. "
                                    "Wrap the code inside triple backticks using the language identifier 'python'. Always name the figure variable 'fig'. Example: fig = go.Figure()."
                                )
                            },
                            {"role": "user", "content": final_math_prompt}
                        ],
                        stream=True
                    )
                    for chunk in response:
                        content = chunk.choices[0].delta.content
                        if content: yield content
                except Exception as e:
                    yield f"✨ এরর: {e}"
            
            full_response = st.write_stream(math_response_generator())
            try_execute_graph(full_response)
            
            # --- ডাটাবেসে সেভ করার মেকানিজম ---
            session_id = st.session_state.current_session_id_tab2
            if not session_id:
                session_id = str(uuid.uuid4())
                st.session_state.current_session_id_tab2 = session_id
                title = math_input[:30] + ("..." if len(math_input) > 30 else "")
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT title FROM chat_sessions WHERE session_id = ?", (session_id,))
                    row = cursor.fetchone()
                    conn.close()
                    title = row[0] if row else (math_input[:30] + ("..." if len(math_input) > 30 else ""))
                except:
                    title = math_input[:30] + ("..." if len(math_input) > 30 else "")
                
            st.session_state.math_messages.append({"role": "assistant", "content": full_response})
            save_session(session_id, st.session_state.user_profile['email'], title, st.session_state.math_messages, "tab2")
            st.rerun()

# 📈 ৩. Economics Demand Analyzer ট্যাব (completions টাইপো স্থায়ী ফিক্সড)
with tab3:
    st.subheader("📈 Economics Demand Analyzer")
    st.write("অর্থনীতি, চাহিদা (Demand), জোগান (Supply) এবং মার্কেট গ্রাফ বিশ্লেষণ করার প্যানেল।")
    
    for message in st.session_state.econ_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
    if econ_input := st.chat_input("অর্থনীতি বা চাহিদা রেখার প্রশ্নটি লিখুন (যেমন: একটি চাহিদা রেখা বা Demand Curve আঁকো)...", key="tab3_chat"):
        st.session_state.econ_messages.append({"role": "user", "content": econ_input})
        with st.chat_message("user"):
            st.markdown(econ_input)
            
        with st.chat_message("assistant"):
            # 🌐 ইকোনমিক্সের জন্যও লাইভ সার্চ করা হচ্ছে
            search_info = ""
            if web_search_enabled and WEB_SEARCH_SUPPORT:
                with st.spinner("🌐 অর্থনীতি সংক্রান্ত লাইভ তথ্য গুগলে অনুসন্ধান করা হচ্ছে..."):
                    search_info = perform_web_search(econ_input)
            
            final_econ_prompt = econ_input
            if search_info:
                final_econ_prompt = f"{search_info}\nUser Question: {econ_input}"

            def econ_response_generator():
                try:
                    if not client:
                        yield "⚠️ এআই ইঞ্জিন লোড হচ্ছে।"
                        return
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {
                                "role": "system", 
                                "content": (
                                    "You are an Economics Professor and Nobel Laureate level Researcher AI. "
                                    "Provide highly structured, long, and comprehensive economic analyses. "
                                    "Use detailed market models, demand/supply elasticity theories, historical context, and mathematical equations (wrapped in $$). "
                                    "Default to replying in Bengali script. However, if the user asks in English or requests English, you MUST reply in English. "
                                    "CRITICAL: If you explain a demand/supply curve, generate Python code using plotly.graph_objects as go to draw the curve. "
                                    "Wrap the code in triple backticks with the 'python' language identifier. Name the figure variable 'fig'."
                                )
                            },
                            {"role": "user", "content": final_econ_prompt}
                        ],
                        stream=True
                    )
                    for chunk in response:
                        content = chunk.choices[0].delta.content
                        if content: yield content
                except Exception as e:
                    yield f"✨ এরর: {e}"
            
            full_response = st.write_stream(econ_response_generator())
            try_execute_graph(full_response)
            
            # --- ডাটাবেসে সেভ করার মেকানিজম ---
            session_id = st.session_state.current_session_id_tab3
            if not session_id:
                session_id = str(uuid.uuid4())
                st.session_state.current_session_id_tab3 = session_id
                title = econ_input[:30] + ("..." if len(econ_input) > 30 else "")
            else:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT title FROM chat_sessions WHERE session_id = ?", (session_id,))
                    row = cursor.fetchone()
                    conn.close()
                    title = row[0] if row else (econ_input[:30] + ("..." if len(econ_input) > 30 else ""))
                except:
                    title = econ_input[:30] + ("..." if len(econ_input) > 30 else "")
                
            st.session_state.econ_messages.append({"role": "assistant", "content": full_response})
            save_session(session_id, st.session_state.user_profile['email'], title, st.session_state.econ_messages, "tab3")
            st.rerun()

# 🎨 ৪. AI Image Generator ট্যাব
with tab4:
    st.subheader("🎨 AI Image Generator")
    st.write("দুঃখিত ! টেক্সট-টু-ইমেজ জেনারেশন মডেলটি এখনো ক্লাউডে কনফিগার করা হচ্ছে। খুব শীঘ্রই এখানে ছবি তৈরির ইঞ্জিন যুক্ত হবে।")