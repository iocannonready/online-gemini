import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 官方最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.2.7-PRO"
BUILD_DATE = "2026-01-18"

# ================= 1. 页面初始化 =================
st.set_page_config(
    page_title=f"凶哥哥的 AI {APP_VERSION}", 
    page_icon="🦁", 
    layout="wide"
)

# 读取 API Key
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
            "files_meta": [], 
            "processed": False 
        }
    }
    st.session_state.current_session_id = default_id

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
    st.status(f"v4.2.7 | 视觉通道已修复", state="complete")
    
    with st.expander("⚙️ 模型配置", expanded=True):
        model_list = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.0) 
        enable_search = st.toggle("🌍 开启联网搜索", value=True)

    st.divider()
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "processed": False}
        st.session_state.current_session_id = nid; st.rerun()

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
                if st.button("🗑️ 删除", key=f"d_{sid}"):
                    if len(st.session_state.all_sessions) > 1: del st.session_state.all_sessions[sid]; st.rerun()

    st.markdown(f"<div style='position: fixed; bottom: 10px; font-size: 11px; color: gray;'>Build: {APP_VERSION}</div>", unsafe_allow_html=True)

# ================= 3. 核心工具函数 =================

def upload_handler_final(client, files):
    """
    修正参数后的最终上传函数
    """
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True); os.makedirs(temp_dir)
    file_metas = []
    
    with st.status("🚀 正在建立视觉连接...", expanded=True) as status:
        local_files = []
        for f in files:
            p = os.path.join(temp_dir, f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            local_files.append(p)
        local_files.sort()

        for path in local_files:
            try:
                # 显式识别 mime_type
                ext = path.lower().split('.')[-1]
                m_type = "application/pdf" if ext == 'pdf' else f"image/{ext.replace('jpg','jpeg')}"
                
                # 【关键修复点】
                # 新版 SDK 的参数名是 file，而不是 path
                r = client.files.upload(file=path, config={"mime_type": m_type})
                
                file_metas.append({"uri": r.uri, "mime_type": r.mime_type, "name": os.path.basename(path)})
                st.write(f"✅ Google 已就绪: `{os.path.basename(path)}`")
            except Exception as e:
                st.error(f"❌ 传输失败: {e}")
        
        # 等待 ACTIVE
        st.write("📖 AI 正在阅读文档...")
        while True:
            ready = True
            for meta in file_metas:
                f_id = meta["uri"].split("/")[-1] 
                f_info = client.files.get(name=f_id)
                if f_info.state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(2)
        status.update(label="✅ 视觉对象挂载成功", state="complete", expanded=False)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return file_metas

# ================= 4. 主对话逻辑 =================

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    # 1. 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            for part in m["parts"]:
                if "text" in part: st.markdown(part["text"])
                if "file_uri" in part: st.info(f"📎 已读取附件: {part.get('name')}")

    # 2. 底部控制区
    chat_prompt = None
    with st.container():
        if current_session["files_meta"]:
            st.success(f"📂 视觉槽位：{len(current_session['files_meta'])} 个附件已在 AI 记忆中。")
            if st.button("🗑️ 清空当前附件"):
                current_session["files_meta"] = []; current_session["processed"] = False; st.rerun()

        up_fs = st.file_uploader(
            "PDF 或 图片 (支持 20+ 材料)", 
            type=['pdf', 'png', 'jpg', 'jpeg'], 
            accept_multiple_files=True, 
            key="v15_up", 
            label_visibility="collapsed"
        )
        
        if up_fs and not current_session["files_meta"]:
            if st.button("🚀 激活视觉分析", use_container_width=True, type="primary"):
                current_session["files_meta"] = upload_handler_final(client, up_fs)
                current_session["processed"] = False; st.rerun()

        chat_prompt = st.chat_input("请对附件下达分析指令...")

    # 3. 对话逻辑
    if chat_prompt:
        user_parts = []
        # 将附件放入第一条历史记录
        if current_session["files_meta"] and not current_session["processed"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"], "name": f["name"]})
            current_session["processed"] = True
        
        user_parts.append({"text": chat_prompt})
        current_session["history"].append({"role": "user", "parts": user_parts})
        st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full_text = ""
            try:
                # 对象转换
                history_objs = []
                for h in current_session["history"][:-1]:
                    parts_objs = []
                    for p in h["parts"]:
                        if "text" in p: parts_objs.append(types.Part(text=p["text"]))
                        elif "file_uri" in p: parts_objs.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
                    history_objs.append(types.Content(role=h["role"], parts=parts_objs))

                last_user_msg = current_session["history"][-1]
                payload = []
                for p in last_user_msg["parts"]:
                    if "text" in p: payload.append(types.Part(text=p["text"]))
                    elif "file_uri" in p: payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []
                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个全能文档分析专家。你会收到图片或PDF，请优先基于这些视觉附件回答。严禁回答'我看不到文件'。",
                        temperature=temperature,
                        tools=tools
                    )
                )
                
                response = chat_session.send_message_stream(message=payload)
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text; box.markdown(full_text + "▌")
                box.markdown(full_text)
                current_session["history"].append({"role": "model", "parts": [{"text": full_text}]})
                st.rerun()
            except Exception as e:
                st.error(f"对话异常: {e}")
else:
    st.warning("👈 请先配置 API Key")
