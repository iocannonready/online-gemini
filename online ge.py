import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 官方最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本与配置 =================
APP_VERSION = "v5.4.0-CLOUD-MODELS"
st.set_page_config(page_title=f"凶哥哥 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# --- 云端安全读取 Key ---
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("❌ 未检测到 API Key。请在 Streamlit App Settings -> Secrets 中配置 GOOGLE_API_KEY。")
    st.stop()

# ================= 1. Session 初始化 =================
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话",
            "history": [], 
            "files_meta": [], 
            "processed": False
        }
    }
    st.session_state.current_session_id = default_id

def get_current_session():
    sid = st.session_state.current_session_id
    if sid not in st.session_state.all_sessions:
        # 容错：如果当前ID不存在，重置或回退
        if not st.session_state.all_sessions:
             new_id = str(uuid.uuid4())
             st.session_state.all_sessions[new_id] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        sid = list(st.session_state.all_sessions.keys())[0]
        st.session_state.current_session_id = sid
    return st.session_state.all_sessions[sid]

current_session = get_current_session()

# ================= 2. 核心功能 (云端直连) =================

def get_client():
    return genai.Client(api_key=API_KEY)

def upload_handler_cloud(client, files):
    """
    云端文件上传逻辑：重命名 -> 上传 -> 轮询状态
    """
    temp_dir = "cloud_upload_tmp"
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    file_metas = []
    
    with st.status("☁️ 正在同步文件至 Google...", expanded=True) as status:
        for i, f in enumerate(files):
            # 1. 安全重命名 (防止中文编码错误)
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            safe_name = f"up_{int(time.time())}_{i}{ext}"
            p = os.path.join(temp_dir, safe_name)
            
            with open(p, "wb") as b: b.write(f.getbuffer())
            
            try:
                # 2. 识别 MIME
                mime = "application/pdf" if ext == ".pdf" else "image/jpeg"
                if "png" in ext: mime = "image/png"
                
                # 3. 上传
                r = client.files.upload(file=p, config={"mime_type": mime})
                
                file_metas.append({
                    "uri": r.uri, 
                    "mime_type": r.mime_type, 
                    "name": r.name,
                    "display_name": f.name
                })
                st.write(f"✅ 已挂载: {f.name}")
            except Exception as e:
                st.error(f"❌ 上传 {f.name} 失败: {e}")
        
        # 4. 状态轮询
        st.write("⏳ 等待 Google 视觉引擎索引...")
        while True:
            all_active = True
            for meta in file_metas:
                try:
                    f_info = client.files.get(name=meta["name"])
                    if f_info.state.name == "PROCESSING":
                        all_active = False; break
                    elif f_info.state.name == "FAILED":
                        st.error(f"文件处理失败: {meta['display_name']}")
                except: pass
            if all_active: break
            time.sleep(2)
            
        status.update(label="✅ 文件已就绪", state="complete", expanded=False)
        
    shutil.rmtree(temp_dir)
    return file_metas

# ================= 3. 侧边栏 UI =================
with st.sidebar:
    st.header("🦁 凶哥哥的 AI")
    st.caption(f"Cloud Ver | {APP_VERSION}")
    
    with st.expander("⚙️ 模型配置", expanded=True):
        # 【关键更新】根据您 API 返回的真实列表定制
        model_map = {
            "gemini-2.5-flash": "🏆 2.5 Flash (综合最强/推荐)",
            "gemini-2.5-flash-lite": "⚡ 2.5 Flash Lite (极速/高配额)",
            "gemini-2.5-pro": "🧠 2.5 Pro (深度推理/识图)",
            "gemini-3-flash-preview": "🧪 3.0 Flash (最新预览)",
            "gemini-3-pro-preview": "🚀 3.0 Pro (最强逻辑预览)",
            "gemini-2.0-flash": "🛡️ 2.0 Flash (经典稳定)"
        }
        
        selected_key = st.selectbox(
            "选择模型", 
            options=list(model_map.keys()),
            format_func=lambda x: f"{x.replace('gemini-', '')} | {model_map[x].split('(')[1][:-1]}",
            index=0 # 默认选 2.5-flash
        )
        st.info(f"当前: {model_map[selected_key]}")
        
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)
        enable_search = st.toggle("联网搜索", value=True)

    st.divider()
    
    # 附件管理区
    st.subheader("📁 附件管理")
