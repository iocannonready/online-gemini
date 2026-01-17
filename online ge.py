import streamlit as st
import os
import time
import shutil
import uuid
from google import genai
from google.genai import types

# ================= 0. 版本与配置 =================
APP_VERSION = "v4.4.0-UI"
BUILD_DATE = "2026-01-18"

st.set_page_config(page_title=f"凶哥哥的 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# 安全读取 Key
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

# ================= 1. 核心功能函数 =================

def safe_upload_handler(client, files):
    """
    文件名脱敏自动上传
    """
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True); os.makedirs(temp_dir)
    file_metas = []
    
    with st.status("🛸 正在挂载视觉附件...", expanded=True) as status:
        for i, f in enumerate(files):
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            safe_name = f"up_{i}{ext}"
            p = os.path.join(temp_dir, safe_name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            
            try:
                m_type = "application/pdf" if ext == '.pdf' else "image/jpeg"
                # 2026 新版 SDK 上传参数名为 file
                r = client.files.upload(file=p, config={"mime_type": m_type})
                file_metas.append({"uri": r.uri, "mime_type": r.mime_type, "display_name": f.name})
                st.write(f"✔️ {f.name} 已就绪")
            except Exception as e:
                st.error(f"上传失败: {f.name}")
        
        while True:
            ready = True
            for meta in file_metas:
                f_id = meta["uri"].split("/")[-1] 
                if client.files.get(name=f_id).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(1.5)
        status.update(label="✅ 附件解析成功", state="complete", expanded=False)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    return file_metas

# ================= 2. 侧边栏 (UI 彻底重构) =================

with st.sidebar:
    # 缩小顶部间距
    st.markdown("### 🦁 凶哥哥的 AI")
    st.status(f"v4.4.0 极速版", state="complete")
    
    # 1. 模型参数 (改为更紧凑的折叠)
    with st.expander("🛠️ 模型设置", expanded=False):
        model_list = ["gemini-2.5-flash", "gemini-3-flash-preview"]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)

    st.divider()

    # 2. 附件管理区 (核心修改点：放到侧边栏)
    st.subheader("📁 附件管理")
    
    # 上传组件
    new_files = st.file_uploader(
        "Upload", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True, 
        key="sidebar_up", label_visibility="collapsed"
    )
    
    if new_files and not current_session["files_meta"]:
        # 自动触发上传逻辑
        client_tmp = genai.Client(api_key=API_KEY) if API_KEY else None
        if client_tmp:
            current_session["files_meta"] = safe_upload_handler(client_tmp, new_files)
            current_session["files_processed"] = False
            st.rerun()

    # 已挂载文件列表展示
    if current_session["files_meta"]:
        with st.container(border=True):
            st.caption("当前已加载:")
            for f in current_session["files_meta"]:
                st.markdown(f"📎 `{f['display_name']}`")
            if st.button("🗑️ 清空所有附件", use_container_width=True):
                current_session["files_meta"] = []; current_session["files_processed"] = False; st.rerun()
    else:
        st.caption("暂无附件")

    st.divider()

    # 3. 会话管理
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1: st.caption("💬 历史会话")
    with col_h2:
        if st.button("➕", help="新建对话"):
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
                if st.button("🗑️", key=f"d_{sid}"):
                    if len(st.session_state.all_sessions) > 1: del st.session_state.all_sessions[sid]; st.rerun()

# ================= 3. 主界面对话区 =================

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    # 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            for part in m["parts"]:
                if "text" in part: st.markdown(part["text"])

    # 底部输入框 (Streamlit 自动置底)
    chat_prompt = st.chat_input("询问 AI 关于附件或任何问题...")

    # 执行逻辑
    if chat_prompt:
        user_parts = []
        # 处理首次包含文件的情况
        if current_session["files_meta"] and not current_session["files_processed"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            user_parts.append({"text": f"[VISION_ACTIVE] 用户已提供 {len(current_session['files_meta'])} 份文档。请优先基于附件回答。"})
            current_session["files_processed"] = True
        
        user_parts.append({"text": chat_prompt})
        current_session["history"].append({"role": "user", "parts": user_parts})
        st.rerun()

    # AI 生成回复逻辑
    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            # 1. 建立空占位符和思考指示器
            box = st.empty()
            with st.spinner("AI 正在分析文档并思考中..."):
                full_text = ""
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
                    current_payload = []
                    for p in current_session["history"][-1]["parts"]:
                        if "text" in p: current_payload.append(types.Part(text=p["text"]))
                        elif "file_uri" in p: current_payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                    # 创建 Chat
                    chat_session = client.chats.create(
                        model=selected_model,
                        history=history_objs,
                        config=types.GenerateContentConfig(
                            system_instruction="你是一个文档分析专家。请精准识别提供的附件。如有必要，请调用联网搜索补充背景。",
                            temperature=temperature,
                            tools=[types.Tool(google_search=types.GoogleSearch())]
                        )
                    )
                    
                    # 2. 流式发送并回显 (打字机效果)
                    response = chat_session.send_message_stream(message=current_payload)
                    for chunk in response:
                        if chunk.text:
                            full_text += chunk.text
                            box.markdown(full_text + "▌") # 动态显示
                    
                    # 3. 最终显示
                    box.markdown(full_text)
                    
                    # 记录历史
                    current_session["history"].append({"role": "model", "parts": [{"text": full_text}]})
                    
                    # 自动重命名
                    if len(current_session["history"]) <= 2:
                        current_session["title"] = chat_prompt[:10]
                    st.rerun()

                except Exception as e:
                    st.error(f"对话异常: {e}")
                    current_session["files_processed"] = False
else:
    st.warning("👈 请在 Secrets 中配置 API Key")
