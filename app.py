import streamlit as st
import requests
import numpy as np
import plotly.graph_objects as go
from PIL import Image
import os
import pdfplumber
import win32com.client
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

# লগইন এবং সাইনআপ ইন্টারফেস
if not st.session_state.logged_in:
    st.title("🔐 Royal Bengal AI - Secure Access Panel")
    st.write("স্বাগতম! অনুগ্রহ করে আপনার অ্যাকাউন্ট দিয়ে লগইন করুন অথবা একটি নতুন অ্যাকাউন্ট তৈরি করুন।")
    
    auth_tab1, auth_tab2 = st.tabs(["🔑 অ্যাকাউন্টে লগইন করুন", "📝 নতুন অ্যাকাউন্ট তৈরি করুন"])
    
    with auth_tab2:
        st.subheader("নতুন অ্যাকাউন্ট তৈরি করুন")
        reg_name = st.text_input("আপনার সম্পূর্ণ নাম (Full Name)", key="reg_name", placeholder="যেমন: Md Mohtasim Billah")
        reg_email = st.text_input("গুগল ইমেইল (Google Email)", key="reg_email", placeholder="যেমন: mohtasim@gmail.com")
        reg_pass = st.text_input("পাসওয়ার্ড (Password)", type="password", key="reg_pass", placeholder="একটি স্ট্রং পাসওয়ার্ড দিন")
        
        if st.button("Sign Up & Create Account 🚀"):
            if reg_email and reg_pass:
                try:
                    conn = sqlite3.connect("users.db")
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO users (email, name, password) VALUES (?, ?, ?)", (reg_email.strip(), reg_name.strip(), reg_pass.strip()))
                    conn.commit()
                    conn.close()
                    st.success("🎉 অ্যাকাউন্ট সফলভাবে তৈরি হয়েছে! পাশের ট্যাবে গিয়ে লগইন করুন।")
                except sqlite3.IntegrityError:
                    st.error("⚠️ এই ইমেইল দিয়ে অলরেডি অ্যাকাউন্ট তৈরি করা আছে!")
            else:
                st.error("⚠️ দয়া করে ইমেইল এবং পাসওয়ার্ড সঠিকভাবে পূরণ করুন।")
                
    with auth_tab1:
        st.subheader("অ্যাকাউন্টে লগইন করুন")
        login_email = st.text_input("আপনার গুগল ইমেইল (Google Email)", key="login_email", placeholder="যেমন: mohtasim@gmail.com")
        login_pass = st.text_input("পাসওয়ার্ড (Password)", type="password", key="login_pass", placeholder="আপনার পাসওয়ার্ডটি লিখুন")
        
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
                st.error("❌ ভুল ইমেইল বা পাসওয়ার্ড! অনুগ্রহ করে সঠিক তথ্য দিন।")
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
        st.rerun()

# প্রধান ফিচার ট্যাব সমূহ
tab1, tab2, tab3, tab4 = st.tabs(["💬 AI Assistant & Upload Solver", "📊 Math Wave", "📈 Economics Demand", "🎨 AI Image Generator"])

# 📂 ফাইল ও ইমেজ আপলোড সমাধান ট্যাব
with tab1:
    st.subheader("📁 ডকুমেন্ট/স্ক্রিনশট আপলোড এবং সমাধান প্যানেল")
    uploaded_file = st.file_uploader("PDF, টেক্সট ফাইল অথবা গণিতের স্ক্রিনশট এখানে আপলোড করুন:", type=["pdf", "txt", "png", "jpg", "jpeg"])
    
    extracted_context = ""
    image_base64 = ""
    
    if uploaded_file is not None:
        if uploaded_file.name.endswith(".pdf"):
            with pdfplumber.open(uploaded_file) as pdf:
                extracted_context = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
            st.info(f"📄 PDF থেকে তথ্য নেওয়া হয়েছে ({len(extracted_context)} অক্ষরে)")
        elif uploaded_file.name.split('.')[-1] in ["png", "jpg", "jpeg"]:
            st.image(uploaded_file, caption="আপলোড করা স্ক্রিনশট/ছবি", width=300)
            # ছবিটিকে ক্লাউডে পাঠানোর জন্য Base64 ফরম্যাটে কনভার্ট করা
            uploaded_file.seek(0)
            image_base64 = base64.b64encode(uploaded_file.read()).decode('utf-8')

    # চ্যাট ইন্টারফেস হিস্ট্রি
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # ইউজারের ইনপুট প্রসেস
    if user_input := st.chat_input("আপনার প্রশ্নটি লিখুন বা আপলোড করা ফাইলটি ব্যাখ্যা করতে বলুন..."):
        final_prompt = user_input
        if extracted_context:
            final_prompt = f"Context from uploaded file:\n{extracted_context}\n\nUser Question: {user_input}"
            
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            def response_generator():
                try:
                    # 👁️ ইমেজ আপলোড করা থাকলে Groq Llama-3.2-Vision মডেল রান হবে
                    if image_base64:
                        response = client.chat.completions.create(
                            model="llama-3.2-11b-vision-preview",
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": (
                                            "You are Royal Bengal AI Machine, a close friend of the user created by Md Mohtasim Billah. "
                                            "Look at the uploaded image carefully. Answer the user's question based on this image. "
                                            "CRITICAL RULE: Reply ONLY in beautiful, friendly, and natural Bengali script (বাংলা হরফ). Do NOT use Banglish. "
                                            f"User Question: {user_input if user_input else 'এই ছবিটিতে কী আছে বুঝিয়ে বলো বন্ধু।'}"
                                        )},
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/jpeg;base64,{image_base64}",
                                            },
                                        },
                                    ],
                                }
                            ],
                            stream=True
                        )
                    # 💬 শুধু নরমাল টেক্সট বা PDF চ্যাট হলে Groq Llama 3 8B মডেল রান হবে
                    
                    else:
                        response = client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {
                                    "role": "system", 
                                    "content": (
                                        "You are Royal Bengal AI Machine, a close and warm friend of the user, created by Md Mohtasim Billah. "
                                        "CRITICAL RULE: You must write your entire response ONLY using the Bengali script/alphabet (বাংলা হরফ). "
                                        "NEVER use Banglish or English. Reply in heartwarming, sweet, and friendly Bengali. "
                                        "If the user asks for math or economics formulas, wrap them in LaTeX style using $$."
                                    )
                                },
                                {"role": "user", "content": final_prompt}
                            ],
                            stream=True
                        )
                        
                    for chunk in response:
                        content = chunk.choices[0].delta.content
                        if content:
                            yield content
                        
                except Exception as e:
                    yield f"✨ ক্লাউড এপিআই রেসপন্স করতে পারেনি ভাই। এরর: {e}"

            full_response = st.write_stream(response_generator())
            
            # 📊 LaTeX গাণিতিক ডিসপ্লে ডিটেক্টর
            if "$$" in full_response:
                try:
                    latex_part = full_response.split("$$")[1]
                    st.latex(latex_part)
                except:
                    pass

            # 🎙️ উইন্ডোজ ভয়েস অ্যাসিস্ট্যান্ট
            if voice_on:
                try:
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    speaker.Speak(full_response, 1)
                except:
                    pass
                    
            # লাইভ গ্রাফ এক্সিকিউটর
            if "fig =" in full_response or "go.Figure" in full_response:
                try:
                    code_block = full_response.split("```python")[1].split("```")[0] if "```python" in full_response else full_response
                    local_vars = {"np": np, "go": go, "st": st}
                    exec(code_block, globals(), local_vars)
                    if "fig" in local_vars:
                        st.plotly_chart(local_vars["fig"], use_container_width=True)
                except:
                    pass
                    
        st.session_state.messages.append({"role": "assistant", "content": full_response})

# 📊 বাকি ট্যাবগুলোর বেসিক স্ট্রাকচার (আগের মতোই থাকবে)
with tab2:
    st.subheader("📊 Math Wave Solver")
with tab3:
    st.subheader("📈 Economics Demand Analyzer")
with tab4:
    st.subheader("🎨 AI Image Generator")