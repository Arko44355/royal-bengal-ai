import streamlit as st
import requests
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import matplotlib
matplotlib.use('Agg') # লিনাক্স ক্লাউড সার্ভারের জন্য নন-ইন্টারেক্টিভ ব্যাকএন্ড সেটআপ
import matplotlib.pyplot as plt
from PIL import Image
import os
import pdfplumber
import sqlite3
import base64
from groq import Groq

# ১. পেজ কনফিগারেশন
st.set_page_config(page_title="Royal Bengal AI Machine", page_icon="🐅", layout="wide")

# 🔑 Groq API Key সেটআপ
GROQ_API_KEY = "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"
client = Groq(api_key=GROQ_API_KEY)

# 🗄️ ডেটাবেস সেটআপ
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT,
            password TEXT
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
                    conn = sqlite3.connect("users.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO users (email, name, password) VALUES (?, ?, ?)", (reg_email.strip(), reg_name.strip(), reg_pass.strip()))
                    conn.commit()
                    conn.close()
                    st.success("🎉 অ্যাকাউন্ট সফলভাবে তৈরি হয়েছে! পাশের ট্যাবে গিয়ে লগইন করুন।")
                except sqlite3.IntegrityError:
                    st.error("⚠️ এই ইমেইল দিয়ে অলরেডি অ্যাকাউন্ট তৈরি করা আছে!")
            else:
                st.error("⚠️ দয়া করে ইমেইল এবং পাসওয়ার্ড সঠিকভাবে পূরণ করুন।")
                
    with auth_tab1:
        st.subheader("অ্যাকাউন্টে লগইন করুন")
        login_email = st.text_input("আপনার গুগল ইমেইল (Google Email)", key="login_email", placeholder="যেমন: mohtasim@gmail.com")
        login_pass = st.text_input("পাসওয়ার্ড (Password)", type="password", key="login_pass", placeholder="আপনার পাসওয়ার্ডটি লিখুন")
        
        if st.button("Login & Unlock Machine 🔓"):
            conn = sqlite3.connect("users.db")
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
    st.stop()

# --- মেইন অ্যাপ্লিকেশন ইন্টারফেস ---
st.title(f"🐅 Royal Bengal AI Machine - Welcome {st.session_state.user_profile['name']}!")

# সাইডবার
with st.sidebar:
    st.header("🎛️ Control Panel")
    voice_on = st.checkbox("🎙️ ভয়েস অ্যাসিস্ট্যান্ট অন করুন (Windows Only)")
    if st.button("Logout 🚪"):
        st.session_state.logged_in = False
        st.session_state.messages = []
        st.session_state.math_messages = []
        st.session_state.econ_messages = []
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
        if uploaded_file.name.endswith(".pdf"):
            with pdfplumber.open(uploaded_file) as pdf:
                extracted_context = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
            st.info(f"📄 PDF থেকে তথ্য নেওয়া হয়েছে ({len(extracted_context)} অক্ষরে)")
        elif uploaded_file.name.split('.')[-1] in ["png", "jpg", "jpeg"]:
            st.image(uploaded_file, caption="আপলোড করা স্ক্রিনশট/ছবি", width=300)
            uploaded_file.seek(0)
            image_base64 = base64.b64encode(uploaded_file.read()).decode('utf-8')

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("আপনার প্রশ্নটি লিখুন বা আপলোড করা ফাইলটি ব্যাখ্যা করতে বলুন...", key="tab1_chat"):
        final_prompt = user_input
        if extracted_context:
            final_prompt = f"Context from uploaded file:\n{extracted_context}\n\nUser Question: {user_input}"
            
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            def response_generator():
                try:
                    if image_base64:
                        response = client.chat.completions.create(
                            model="llama-3.2-11b-vision-preview",
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"You are Royal Bengal AI Machine. Default to replying in Bengali script. However, if the user explicitly asks you to reply in English or writes in English, reply in English. User Question: {user_input if user_input else 'এই ছবিটিতে কী আছে বুঝিয়ে বলো বন্ধু।'}"},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                                ]
                            }],
                            stream=True
                        )
                    else:
                        response = client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {
                                    "role": "system", 
                                    "content": "You are Royal Bengal AI Machine, a close friend of the user created by Md Mohtasim Billah. Default to replying in beautiful Bengali script. However, if the user explicitly requests English or writes in English, you MUST reply in English. Wrap math formulas in $$ if needed."
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
            st.session_state.messages.append({"role": "assistant", "content": full_response})

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
            def math_response_generator():
                try:
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {
                                "role": "system", 
                                "content": "You are a Math Expert AI. Default to replying in Bengali script. However, if the user asks in English or requests English, you MUST reply in English. CRITICAL: If the user wants a graph, you MUST write python code using plotly.graph_objects as go and numpy as np. Wrap the code inside triple backticks using the language identifier 'python'. Always name the figure variable 'fig'. Example: fig = go.Figure(). Then st.plotly_chart will render it."
                            },
                            {"role": "user", "content": math_input}
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
            st.session_state.math_messages.append({"role": "assistant", "content": full_response})

# 📈 ৩. Economics Demand Analyzer ট্যাব
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
            def econ_response_generator():
                try:
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {
                                "role": "system", 
                                "content": "You are an Economics Professor AI. Default to replying in Bengali script. However, if the user asks in English or requests English, you MUST reply in English. CRITICAL: If you explain a demand/supply curve, generate Python code using plotly.graph_objects as go to draw the curve. Wrap the code in triple backticks with the 'python' language identifier. Name the figure variable 'fig'."
                            },
                            {"role": "user", "content": econ_input}
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
            st.session_state.econ_messages.append({"role": "assistant", "content": full_response})

# 🎨 ৪. AI Image Generator ট্যাব
with tab4:
    st.subheader("🎨 AI Image Generator")
    st.write("দুঃখিত ! টেক্সট-টু-ইমেজ জেনারেশন মডেলটি এখনো ক্লাউডে কনফিগার করা হচ্ছে। খুব শীঘ্রই এখানে ছবি তৈরির ইঞ্জিন যুক্ত হবে।")