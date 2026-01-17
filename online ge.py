import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用新版 SDK
from google import genai
from google.genai import types

# ================= 1. 初始化与安全配置 =================

# 优先从 Streamlit Secrets 读取 Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = "" # 本地调试可用，云端必须设在 Secrets 里

st.set_page_config(page_title="凶哥哥的 AI", page_icon="🦁", layout="wide")

# 状态初始化
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {"title": "新对话", "history": [], "files": [], "processed": False}
    }
    st.session_state.current_session_id = default_id

# 获取当前会话数据
def get_session():
    sid = st.session_state.current_session_id
    if sid not in st.session_state.all_sessions:
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_session()

# ================= 2. 侧边栏 (云端精简版) =================

with st.sidebar:
    st.title("🦁 凶哥哥的 AI")
    st.caption("云端直连模式 (免翻墙)")
    
    with st.expander("⚙️ 设置与模型", expanded=True):
        # 模型列表 (2026年最新)
        model_list = [
            "gemini-1.5-flash",        # 免费配额最足
            "gemini-2.5-pro",           # 20张图片OCR首选
            "gemini-2.5-flash",         # 最新平衡款
            "gemini-3.0-flash-preview", # 最新尝鲜款
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.7)
        # 默认开启联网，不显示开关以保持简洁
        
    st.divider()

    # 会话管理
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1: st.caption("对话列表")
    with col_h2: 
        if st.button("➕"):
            nid = str(uuid.uuid4())
            st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files": [], "processed": False}
            st.session_state.current_session_id = nid
            st.rerun()

    for sid in list(st.session_state.all_sessions.keys()):
        sess = st.session_state.all_sessions[sid]
        active = (sid == st.session_state.current_session_id)
        c1, c2 = st.columns([0.8, 0.2])
        with c1:
            if st.button(sess["title"], key=f"s_{sid}", type="primary" if active else "secondary", use_container_width=True):
                st.session_state.current_session_id = sid
                st.rerun()
        with c2:
            with st.popover("⋮"):
                new_n = st.text_input("重命名", value=sess["title"], key=f"rn_{sid}")
                if new_n != sess["title"]: sess["title"] = new_n; st.rerun()
                if st.button("🗑️", key=f"del_{sid}"):
                    if len(st.session_state.all_sessions) > 1:
                        del st.session_state.all_sessions[sid]; st.rerun()

# ================= 3. 核心功能 (新版 SDK) =================

def get_client():
    if not API_KEY:
        st.error("❌ 请在 Streamlit Secrets 中配置 GOOGLE_API_KEY")
        return None
    # 云端不需要 os.environ 代理设置，直接初始化
    return genai.Client(api_key=API_KEY)

def upload_handler(client, files):
    temp = "cloud_tmp"
    if os.path.exists(temp): shutil.rmtree(temp)
    os.makedirs(temp)
    
    refs = []
    status = st.empty()
    for i, f in enumerate(files):
        path = os.path.join(temp, f.name)
        with open(path, "wb") as b: b.write(f.getbuffer())
        status.caption(f"正在读取 {f.name}...")
        try:
            res = client.files.upload(path=path)
            refs.append(res)
        except Exception as e: st.error(f"上传出错: {e}")
    
    if refs:
        status.caption("AI 正在解析内容...")
        while True:
            ready = True
            for r in refs:
                if client.files.get(name=r.name).state == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(1)
    status.empty()
    return refs

# ================= 4. 对话逻辑 =================

client = get_client()
if not client: st.stop()

# 渲染历史
for m in current_session["history"]:
    with st.chat_message(m["role"]): st.markdown(m["content"])

# 输入区
with st.container():
    if current_session["files"]:
        st.success(f"📎 已挂载 {len(current_session['files'])} 个附件")
        if st.button("清空附件"):
            current_session["files"] = []; current_session["processed"] = False; st.rerun()

    c_up, c_in = st.columns([0.15, 0.85])
    with c_up:
        with st.popover("📎 附件"):
            fs = st.file_uploader("上传材料", accept_multiple_files=True, label_visibility="collapsed")
            if fs and st.button("确认"):
                current_session["files"] = upload_handler(client, fs)
                current_session["processed"] = False
                st.rerun()
    with c_in:
        prompt = st.chat_input("输入问题或指令...")

if prompt:
    current_session["history"].append({"role": "user", "content": prompt})
    st.rerun()

if current_session["history"] and current_session["history"][-1]["role"] == "user":
    with st.chat_message("assistant"):
        box = st.empty(); full = ""
        
        # 准备内容：新版 SDK 混合发送模式
        payload = []
        if current_session["files"] and not current_session["processed"]:
            payload.extend(current_session["files"])
            current_session["processed"] = True
        payload.append(current_session["history"][-1]["content"])

        # 转换历史
        h_objs = []
        for h in current_session["history"][:-1]:
            h_objs.append(types.Content(
                role="user" if h["role"] == "user" else "model",
                parts=[types.Part(text=h["content"])]
            ))

        try:
            # 默认隐形开启联网
            chat = client.chats.create(
                model=selected_model,
                history=h_objs,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            
            stream = chat.send_message_stream(message=payload)
            for chunk in stream:
                if chunk.text:
                    full += chunk.text
                    box.markdown(full + "▌")
            box.markdown(full)
            current_session["history"].append({"role": "assistant", "content": full})
            
            if len(current_session["history"]) == 2:
                current_session["title"] = current_session["history"][0]["content"][:10]
            st.rerun()
        except Exception as e:
            st.error(f"对话异常: {e}")
