import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 官方最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.2.9-PRO"
BUILD_DATE = "2026-01-18"

# ================= 1. 页面初始化 =================
st.set_page_config(page_title=f"凶哥哥的 AI {APP_VERSION}", page_icon="🦁", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

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
    st.status(f"v4.2.9 | 编码免疫版", state="complete")
    
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

    st.markdown(f"<div style='position: fixed; bottom: 10px; font-size: 11px; color: gray;'>Build: {APP_VERSION}</div>", unsafe_allow_html=True)

# ================= 3. 核心功能函数 (编码加固版) =================

def safe_upload_handler(client, files):
    """
    文件名脱敏上传：解决中文文件名导致的 'ascii' codec 报错
    """
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True); os.makedirs(temp_dir)
    file_metas = []
    
    with st.status("🚀 正在安全挂载视觉对象...", expanded=True) as status:
        # 1. 物理保存：使用安全的文件名（纯数字）
        st.write("正在预处理中文文件名...")
        for i, f in enumerate(files):
            # 提取后缀名
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            
            # 使用简单的安全名，彻底避开 ASCII 编码问题
            safe_name = f"upload_{i}{ext}"
            p = os.path.join(temp_dir, safe_name)
            
            with open(p, "wb") as b: b.write(f.getbuffer())
            
            # 2. 上传到 Google
            try:
                m_type = "application/pdf" if ext == '.pdf' else "image/jpeg"
                # 传入 safe_name 给 Google，不会报错
                r = client.files.upload(file=p, config={"mime_type": m_type})
                
                # 记录时：uri 用 Google 的，name 依然存用户看到的中文名
                file_metas.append({
                    "uri": r.uri, 
                    "mime_type": r.mime_type, 
                    "display_name": f.name # 保留中文名用于显示
                })
                st.write(f"✔️ {f.name} 已安全入库")
            except Exception as e:
                st.error(f"传输失败 ({f.name}): {str(e)}")
        
        # 3. 状态检查
        while True:
            ready = True
            for meta in file_metas:
                f_id = meta["uri"].split("/")[-1] 
                if client.files.get(name=f_id).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(2)
        status.update(label="✅ 视觉通道已建立", state="complete", expanded=False)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return file_metas

# ================= 4. 主对话逻辑 =================

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    # 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            for part in m["parts"]:
                if "text" in part: st.markdown(part["text"])

    chat_prompt = None
    with st.container():
        # 显示已挂载文件
        if current_session["files_meta"]:
            cols = st.columns([0.8, 0.2])
            cols[0].success(f"📎 视觉通道已锁定 {len(current_session['files_meta'])} 个文件")
            if cols[1].button("🗑️ 清空"):
                current_session["files_meta"] = []; current_session["files_processed"] = False; st.rerun()

        # 上传区
        up_fs = st.file_uploader(
            "PDF 或 图片 (拖入即自动分析)", 
            type=['pdf', 'png', 'jpg', 'jpeg'], 
            accept_multiple_files=True, 
            key="v17_up", 
            label_visibility="collapsed"
        )
        
        if up_fs and not current_session["files_meta"]:
            # 使用修复后的安全上传函数
            current_session["files_meta"] = safe_upload_handler(client, up_fs)
            current_session["files_processed"] = False
            st.rerun()

        chat_prompt = st.chat_input("针对附件提问（例如：总结全文）")

    if chat_prompt:
        user_parts = []
        if current_session["files_meta"] and not current_session["files_processed"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            # 强化指令
            user_parts.append({"text": f"[VISION_ACTIVE] 我提供了 {len(current_session['files_meta'])} 个关键文档。请深度扫描并基于此回答。"})
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

                # 构建 Payload
                current_payload = []
                for p in current_session["history"][-1]["parts"]:
                    if "text" in p: current_payload.append(types.Part(text=p["text"]))
                    elif "file_uri" in p: current_payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []
                
                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个全能文档分析专家。无论收到图片还是PDF，你都能通过视觉接口精准识别。严禁回答我看不到文件。",
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
