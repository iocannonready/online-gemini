import streamlit as st
import os
import time
import shutil
import uuid
# 使用 2026 最新版 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.0.1-PRO"
BUILD_DATE = "2026-01-17"

# ================= 1. 初始化页面与安全配置 =================
st.set_page_config(
    page_title=f"凶哥哥的 AI {APP_VERSION}", 
    page_icon="🦁", 
    layout="wide"
)

# --- 安全读取 API KEY ---
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session State
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话", 
            "history": [], 
            "files": [], 
            "processed": False 
        }
    }
    st.session_state.current_session_id = default_id

# 获取当前会话数据
def get_current_session():
    sid = st.session_state.current_session_id
    if sid not in st.session_state.all_sessions:
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.title("🦁 凶哥哥的 AI")
    st.status(f"云端直连模式 | {APP_VERSION}", state="complete")
    
    with st.expander("⚙️ 模型与参数", expanded=True):
        model_list = [
            "gemini-1.5-pro",           # 处理 20-30 张文字图片首选
            "gemini-2.5-flash",         # 2026 稳定主力
            "gemini-3-flash-preview",   # 最新极速模型
            "gemini-2.0-flash",         # 经典型号
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力 (Temp)", 0.0, 2.0, 0.7)
        enable_search = st.toggle("🌍 开启联网搜索", value=True)

    st.divider()

    # 会话管理
    st.caption("💬 会话管理")
    if st.button("➕ 新建对话", use_container_width=True):
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
                st.session_state.current_session_id = sid; st.rerun()
        with c2:
            with st.popover("⋮"):
                new_n = st.text_input("重命名", value=sess["title"], key=f"r_{sid}")
                if new_n != sess["title"]: sess["title"] = new_n; st.rerun()
                if st.button("🗑️", key=f"d_{sid}"):
                    if len(st.session_state.all_sessions) > 1: del st.session_state.all_sessions[sid]; st.rerun()

    # --- 修正后的版本核对区域 ---
    st.markdown(f"""
    <div style='position: fixed; bottom: 10px; font-size: 12px; color: gray;'>
    软件版本: {APP_VERSION}<br>
    构建日期: {BUILD_DATE}<br>
    SDK: {genai.__version__}
    </div>
    """, unsafe_allow_html=True)

# ================= 3. 核心功能函数 =================

def get_client():
    if not API_KEY:
        st.error("❌ 未检测到 API KEY。请检查 Secrets 设置。")
        return None
    return genai.Client(api_key=API_KEY)

def upload_handler_v4(client, files):
    temp_dir = "cloud_tmp"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir)
    
    with st.status("🚀 AI 正在深度阅读附件...", expanded=True) as status:
        uploaded_refs = []
        local_paths = []
        for f in files:
            p = os.path.join(temp_dir, f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            local_paths.append(p)
        local_paths.sort()
        
        for i, path in enumerate(local_paths):
            try:
                r = client.files.upload(path=path)
                uploaded_refs.append(r)
                st.write(f"已就绪: {os.path.basename(path)}")
            except Exception as e:
                st.error(f"出错: {e}")
        
        while True:
            ready = True
            for r in uploaded_refs:
                if client.files.get(name=r.name).state == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(2)
        status.update(label="✅ 附件处理完成", state="complete", expanded=False)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return uploaded_refs

# ================= 4. 主对话逻辑 =================

client = get_client()
if client:
    for m in current_session["history"]:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    with st.container():
        if current_session["files"]:
            with st.expander(f"📁 当前已挂载附件 ({len(current_session['files'])} 个)", expanded=False):
                cols = st.columns(2)
                for idx, f_ref in enumerate(current_session["files"]):
                    cols[idx % 2].caption(f"📄 {f_ref.display_name}")
                if st.button("🗑️ 清空当前附件"):
                    current_session["files"] = []; current_session["processed"] = False; st.rerun()

        c
