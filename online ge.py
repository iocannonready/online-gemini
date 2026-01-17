import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 官方最新 SDK (pip install -U google-genai)
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.2.0-PRO"
BUILD_DATE = "2026-01-17"

# ================= 1. 页面初始化 =================
st.set_page_config(
    page_title=f"凶哥哥的 AI {APP_VERSION}", 
    page_icon="🦁", 
    layout="wide"
)

# 安全读取 Secrets
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
            "history": [], # 存储结构：{"role": "user/model", "parts": [{"text": "..."}, {"file_uri": "...", "mime_type": "..."}]}
            "files_meta": [], # 存储已上传文件的元数据 (uri 和 mime_type)
            "files_processed": False 
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
    st.status(f"v4.2.0 | 视觉增强型", state="complete")
    
    with st.expander("⚙️ 模型配置", expanded=True):
        model_list = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.1) 
        enable_search = st.toggle("🌍 开启联网搜索", value=True)

    st.divider()
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "files_processed": False}
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

# ================= 3. 核心功能函数 =================

def get_client():
    if not API_KEY: return None
    return genai.Client(api_key=API_KEY)

def upload_handler_v11(client, files):
    """
    上传文件并提取持久化元数据
    """
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True); os.makedirs(temp_dir)
    file_metas = []
    
    with st.status("🚀 视觉文件解析中...", expanded=True) as status:
        local_files = []
        for f in files:
            p = os.path.join(temp_dir, f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            local_files.append(p)
        local_files.sort()

        for path in local_files:
            try:
                m_type = "application/pdf" if path.lower().endswith(".pdf") else "image/jpeg"
                r = client.files.upload(path=path, config={"mime_type": m_type})
                # 我们只存最关键的 URI 和 Mime，方便跨 Session 序列化
                file_metas.append({"uri": r.uri, "mime_type": r.mime_type, "name": os.path.basename(path)})
                st.write(f"✅ 解析成功: {os.path.basename(path)}")
            except Exception as e: st.error(f"出错: {e}")
        
        while True:
            ready = True
            for meta in file_metas:
                # 轮询时需提取 name (以 files/ 开头的 ID)
                f_name = meta["uri"].split("/")[-1] 
                if client.files.get(name=f_name).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(2)
        status.update(label="✅ 视觉权限已锁定", state="complete", expanded=False)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return file_metas

# ================= 4. 主对话逻辑 =================

client = get_client()
if client:
    # 1. 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            for part in m["parts"]:
                if "text" in part: st.markdown(part["text"])
                if "file_uri" in part: st.caption(f"📎 引用附件: {part.get('name', '文件')}")

    # 2. 底部控制
    chat_prompt = None
    with st.container():
        if current_session["files_meta"]:
            st.info(f"📂 已挂载 {len(current_session['files_meta'])} 个附件")
            if st.button("🗑️ 清空附件"):
                current_session["files_meta"] = []; current_session["files_processed"] = False; st.rerun()

        up_fs = st.file_uploader("拖拽或浏览 (20+ 图片/PDF)", accept_multiple_files=True, key="v11_up", label_visibility="collapsed")
        if up_fs and not current_session["files_meta"]:
            if st.button("🚀 激活并上传", use_container_width=True, type="primary"):
                current_session["files_meta"] = upload_handler_v11(client, up_fs)
                current_session["files_processed"] = False; st.rerun()

        chat_prompt = st.chat_input("针对附件提问...")

    # 3. 对话执行逻辑
    if chat_prompt:
        # 【核心重构】构造包含 Part 的历史记录
        user_parts = [{"text": chat_prompt}]
        
        # 如果是第一次发送且有附件，将附件 Part 永久封印在这一条历史里
        if current_session["files_meta"] and not current_session["files_processed"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"], "name": f["name"]})
            current_session["files_processed"] = True
            
        current_session["history"].append({"role": "user", "parts": user_parts})
        st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full_text = ""
            
            try:
                # --- 历史记录对象化转换 (严格匹配官方 types.Content 规范) ---
                history_objs = []
                for h in current_session["history"][:-1]:
                    parts_objs = []
                    for p in h["parts"]:
                        if "text" in p:
                            parts_objs.append(types.Part(text=p["text"]))
                        elif "file_uri" in p:
                            parts_objs.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
                    
                    history_objs.append(types.Content(role=h["role"], parts=parts_objs))

                # 构建本次发送的 Payload (最后一条 user 消息)
                last_user_msg = current_session["history"][-1]
                current_payload = []
                for p in last_user_msg["parts"]:
                    if "text" in p: current_payload.append(types.Part(text=p["text"]))
                    elif "file_uri" in p: current_payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                # 配置
                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []
                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个具备视觉能力的文档分析专家。请仔细阅读用户在历史记录或当前消息中提供的所有图片/PDF附件。如果看到附件，必须优先基于附件内容回答。严禁说你看不到文件。",
                        temperature=temperature,
                        tools=tools
                    )
                )
                
                response = chat_session.send_message_stream(message=current_payload)
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text; box.markdown(full_text + "▌")
                
                box.markdown(full_text)
                
                # 记录回复
                current_session["history"].append({"role": "model", "parts": [{"text": full_text}]})
                
                if len(current_session["history"]) <= 2:
                    current_session["title"] = chat_prompt[:10]
                st.rerun()

            except Exception as e:
                st.error(f"对话异常: {e}")
