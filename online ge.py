import streamlit as st
import os
import time
import shutil
import uuid
import json
from google import genai
from google.genai import types

# ================= 0. 版本配置 =================
APP_VERSION = "v4.6.0-Custom"
DB_PATH = "chat_storage.json"

st.set_page_config(page_title=f"凶哥哥的 AI {APP_VERSION}", page_icon="🦁", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# ================= 1. 持久化数据管理 =================
def load_data():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {}
    return {}

def save_data():
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.all_sessions, f, ensure_ascii=False, indent=2)

if "all_sessions" not in st.session_state:
    loaded = load_data()
    if loaded:
        st.session_state.all_sessions = loaded
        st.session_state.current_session_id = list(loaded.keys())[0]
    else:
        default_id = str(uuid.uuid4())
        st.session_state.all_sessions = {
            default_id: {"title": "新对话", "history": [], "files_meta": [], "files_processed": False}
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
    st.caption(f"定制版 | {APP_VERSION}")
    
    with st.expander("⚙️ 模型选择 (基于您的配额)", expanded=True):
        # 根据截图定制的列表
        model_options = {
            "gemini-2.5-flash-lite": "⚡ 日常对话 (配额 10/分)",
            "gemini-2.5-flash": "📄 文档分析 (配额 5/分)",
            "gemini-3-flash": "🧪 尝鲜预览 (配额 5/分)",
            "gemini-1.5-pro": "🧠 复杂推理 (保底方案)"
        }
        
        selected_model_key = st.selectbox(
            "选择模型", 
            options=list(model_options.keys()), 
            format_func=lambda x: f"{x} - {model_options[x]}",
            index=0 # 默认选 Lite，配额最多
        )
        
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)

    st.divider()
    # 附件管理
    st.subheader("📁 本对话附件")
    new_files = st.file_uploader("Upload", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True, key="side_up", label_visibility="collapsed")
    
    # 自动上传逻辑
    if new_files:
        client_tmp = genai.Client(api_key=API_KEY) if API_KEY else None
        # 只有当新文件没被处理过时才上传
        current_names = [f['display_name'] for f in current_session["files_meta"]]
        new_to_upload = [f for f in new_files if f.name not in current_names]
        
        if client_tmp and new_to_upload:
            with st.status("🛸 正在上传...", expanded=True):
                temp_dir = "cloud_tmp"; os.makedirs(temp_dir, exist_ok=True)
                for i, f in enumerate(new_to_upload):
                    # 编码安全处理
                    ext = os.path.splitext(f.name)[1].lower()
                    if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
                    safe_path = os.path.join(temp_dir, f"up_{int(time.time())}_{i}{ext}")
                    
                    with open(safe_path, "wb") as b: b.write(f.getbuffer())
                    try:
                        m_type = "application/pdf" if ext == '.pdf' else "image/jpeg"
                        r = client_tmp.files.upload(file=safe_path, config={"mime_type": m_type})
                        
                        # 轮询激活
                        while True:
                            if client_tmp.files.get(name=r.name).state.name == "ACTIVE": break
                            time.sleep(1)
                            
                        current_session["files_meta"].append({
                            "uri": r.uri, "mime_type": r.mime_type, "display_name": f.name
                        })
                    except Exception as e: st.error(f"{f.name} 失败: {e}")
                
                current_session["files_processed"] = False # 标记有新文件未读
                save_data()
                shutil.rmtree(temp_dir, ignore_errors=True)
            st.rerun()

    if current_session["files_meta"]:
        with st.container(border=True):
            for f in current_session["files_meta"]: st.markdown(f"📎 `{f['display_name']}`")
            if st.button("🗑️ 清空附件", use_container_width=True):
                current_session["files_meta"] = []; current_session["files_processed"] = False
                save_data(); st.rerun()
    else:
        st.caption("暂无附件")

    st.divider()
    # 会话管理
    col_1, col_2 = st.columns([4,1])
    with col_1: st.caption("历史会话")
    with col_2: 
        if st.button("➕"):
            nid = str(uuid.uuid4())
            st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "files_processed": False}
            st.session_state.current_session_id = nid; save_data(); st.rerun()

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
                if new_n != sess["title"]: sess["title"] = new_n; save_data(); st.rerun()
                if st.button("🗑️", key=f"d_{sid}"):
                    del st.session_state.all_sessions[sid]; save_data(); st.rerun()

# ================= 3. 主对话区 =================

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            st.markdown(m["content"])

    chat_prompt = st.chat_input("输入问题...")

    if chat_prompt:
        user_parts = []
        # 智能挂载：仅在有新文件且未处理时发送文件
        if current_session["files_meta"] and not current_session["files_processed"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            user_parts.append({"text": f"[系统通知] 用户上传了 {len(current_session['files_meta'])} 份文档。请基于此回答。"})
            current_session["files_processed"] = True
        
        user_parts.append({"text": chat_prompt})
        current_session["history"].append({"role": "user", "content": chat_prompt, "full_parts": user_parts})
        save_data(); st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty()
            with st.spinner("思考中..."):
                full_text = ""
                try:
                    # 构造历史
                    history_objs = []
                    for h in current_session["history"][:-1]:
                        if "full_parts" in h:
                            p_objs = []
                            for p in h["full_parts"]:
                                if "text" in p: p_objs.append(types.Part(text=p["text"]))
                                elif "file_uri" in p: p_objs.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
                            history_objs.append(types.Content(role=h["role"], parts=p_objs))
                        else:
                            history_objs.append(types.Content(role=h["role"], parts=[types.Part(text=h["content"])]))

                    # 构造 Payload
                    last_msg = current_session["history"][-1]
                    current_payload = []
                    for p in last_msg.get("full_parts", [{"text": last_msg["content"]}]):
                        if "text" in p: current_payload.append(types.Part(text=p["text"]))
                        elif "file_uri" in p: current_payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                    # 智能系统指令
                    sys_inst = "你是一个全能助手。"
                    if current_session["files_meta"]:
                        sys_inst = "你是一个文档专家。请优先根据附件内容回答问题。"

                    # 发送请求
                    chat = client.chats.create(
                        model=selected_model_key,
                        history=history_objs,
                        config=types.GenerateContentConfig(
                            system_instruction=sys_inst,
                            temperature=temperature,
                            tools=[types.Tool(google_search=types.GoogleSearch())]
                        )
                    )
                    
                    response = chat.send_message_stream(message=current_payload)
                    for chunk in response:
                        if chunk.text:
                            full_text += chunk.text
                            box.markdown(full_text + "▌")
                    
                    box.markdown(full_text)
                    current_session["history"].append({"role": "model", "content": full_text})
                    
                    if len(current_session["history"]) == 2:
                        current_session["title"] = chat_prompt[:10]
                    
                    save_data(); st.rerun()

                except Exception as e:
                    st.error(f"出错: {str(e)}")
else:
    st.warning("👈 请在 Secrets 中配置 API Key")
