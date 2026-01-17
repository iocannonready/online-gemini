import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 官方最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.2.8-PRO"
BUILD_DATE = "2026-01-18"

# ================= 1. 页面初始化 =================
st.set_page_config(page_title=f"凶哥哥的 AI {APP_VERSION}", page_icon="🦁", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# 初始化 Session
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话", 
            "history": [], 
            "files_meta": [], 
            "files_processed": False 
        }
    }
    st.session_state.current_session_id = default_id

def get_current_session():
    sid = st.session_state.current_session_id
    return st.session_state.all_sessions.get(sid, list(st.session_state.all_sessions.values())[0])

current_session = get_current_session()

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.title("🦁 凶哥哥的 AI")
    st.status(f"v4.2.8 | 自动视觉增强版", state="complete")
    
    with st.expander("⚙️ 模型配置", expanded=True):
        model_list = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.0) 
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

# ================= 3. 核心功能函数 =================

def auto_upload_handler(client, files):
    """无需点按钮，自动上传并锁定状态"""
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True); os.makedirs(temp_dir)
    file_metas = []
    
    with st.status("🛸 AI 正在扫描附件通道...", expanded=True) as status:
        local_files = []
        for f in files:
            p = os.path.join(temp_dir, f.name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            local_files.append(p)
        local_files.sort()

        for path in local_files:
            try:
                m_type = "application/pdf" if path.lower().endswith(".pdf") else "image/jpeg"
                r = client.files.upload(file=path, config={"mime_type": m_type})
                file_metas.append({"uri": r.uri, "mime_type": r.mime_type, "name": os.path.basename(path)})
                st.write(f"✔️ {os.path.basename(path)} 已就绪")
            except Exception as e: st.error(f"传输失败: {e}")
        
        while True:
            ready = True
            for meta in file_metas:
                f_id = meta["uri"].split("/")[-1] 
                if client.files.get(name=f_id).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(2)
        status.update(label="✅ 视觉对象已挂载", state="complete", expanded=False)
    
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

    # 2. 底部控制区 (自动上传逻辑)
    chat_prompt = None
    with st.container():
        # 如果有文件挂载，显示状态
        if current_session["files_meta"]:
            cols = st.columns([0.8, 0.2])
            cols[0].success(f"📎 视觉通道已锁定 {len(current_session['files_meta'])} 个文件")
            if cols[1].button("🗑️ 清空"):
                current_session["files_meta"] = []; current_session["files_processed"] = False; st.rerun()

        # 上传区 (只要有文件变动，就会触发上传逻辑)
        up_fs = st.file_uploader(
            "PDF 或 图片 (拖入即自动分析)", 
            type=['pdf', 'png', 'jpg', 'jpeg'], 
            accept_multiple_files=True, 
            key="v16_up", 
            label_visibility="collapsed"
        )
        
        # 核心逻辑：如果检测到新上传，且当前会话没存过，则自动开始上传
        if up_fs and not current_session["files_meta"]:
            current_session["files_meta"] = auto_upload_handler(client, up_fs)
            current_session["files_processed"] = False
            st.rerun()

        chat_prompt = st.chat_input("针对附件提问（例如：总结全文）")

    # 3. 对话执行
    if chat_prompt:
        user_parts = []
        # 第一轮发送：强制将文件 URI 放在文字前面
        if current_session["files_meta"] and not current_session["files_processed"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"], "name": f["name"]})
            # 加入视觉觉醒指令
            user_parts.append({"text": f"系统指令：我已为你提供 {len(current_session['files_meta'])} 份文档/图片。请将其作为核心依据，开始分析。"})
            current_session["files_processed"] = True
        
        user_parts.append({"text": chat_prompt})
        current_session["history"].append({"role": "user", "parts": user_parts})
        st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full_text = ""
            try:
                # 转换历史
                history_objs = []
                for h in current_session["history"][:-1]:
                    parts_objs = []
                    for p in h["parts"]:
                        if "text" in p: parts_objs.append(types.Part(text=p["text"]))
                        elif "file_uri" in p: parts_objs.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
                    history_objs.append(types.Content(role=h["role"], parts=parts_objs))

                # 构建当前 Payload
                last_user_msg = current_session["history"][-1]
                current_payload = []
                for p in last_user_msg["parts"]:
                    if "text" in p: current_payload.append(types.Part(text=p["text"]))
                    elif "file_uri" in p: current_payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []
                
                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个全能文档分析专家。如果你在消息中收到了 file_uri，这意味着你有权直接通过视觉接口访问这些内容。绝对不要回答我看不到文件。请通过深度视觉扫描给出答案。",
                        temperature=temperature,
                        tools=tools
                    )
                )
                
                response = chat_session.send_message_stream(message=current_payload)
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text; box.markdown(full_text + "▌")
                box.markdown(full_text)
                
                current_session["history"].append({"role": "model", "parts": [{"text": full_text}]})
                if len(current_session["history"]) <= 2:
                    current_session["title"] = chat_prompt[:10]
                st.rerun()
            except Exception as e:
                st.error(f"对话异常: {e}")
                current_session["files_processed"] = False
else:
    st.warning("👈 请在 Secrets 中配置 API Key")
