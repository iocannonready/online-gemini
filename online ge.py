import streamlit as st
import os
import time
import shutil
import uuid
import json
from google import genai
from google.genai import types

# ================= 0. 版本与配置 =================
APP_VERSION = "v4.5.0-STABLE"
DB_PATH = "chat_storage.json" # 对话存档文件路径

st.set_page_config(page_title=f"凶哥哥的 AI {APP_VERSION}", page_icon="🦁", layout="wide")

# 安全读取 Key
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = None

# ================= 1. 持久化数据管理 =================

def load_all_sessions():
    """从本地 JSON 文件读取所有历史记录"""
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_all_sessions():
    """将当前所有会话保存到 JSON"""
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.all_sessions, f, ensure_ascii=False, indent=2)

# 初始化 Session State
if "all_sessions" not in st.session_state:
    loaded_data = load_all_sessions()
    if loaded_data:
        st.session_state.all_sessions = loaded_data
        st.session_state.current_session_id = list(loaded_data.keys())[0]
    else:
        # 初次运行
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

# 获取当前会话
current_id = st.session_state.current_session_id
if current_id not in st.session_state.all_sessions:
    current_id = list(st.session_state.all_sessions.keys())[0]
    st.session_state.current_session_id = current_id
current_session = st.session_state.all_sessions[current_id]

# ================= 2. 核心功能函数 =================

def safe_upload_handler(client, files):
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True); os.makedirs(temp_dir)
    file_metas = []
    
    with st.status("🛸 正在安全挂载视觉附件...", expanded=True) as status:
        for i, f in enumerate(files):
            ext = os.path.splitext(f.name)[1].lower()
            if not ext: ext = ".pdf" if f.type == "application/pdf" else ".jpg"
            safe_name = f"up_{i}{ext}"
            p = os.path.join(temp_dir, safe_name)
            with open(p, "wb") as b: b.write(f.getbuffer())
            try:
                m_type = "application/pdf" if ext == '.pdf' else "image/jpeg"
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

# ================= 3. 侧边栏 UI =================

with st.sidebar:
    st.markdown("### 🦁 凶哥哥的 AI")
    st.caption(f"持久化稳定版 | {APP_VERSION}")
    
    with st.expander("🛠️ 模型配置", expanded=False):
        model_list = ["gemini-2.5-flash", "gemini-3-flash-preview"]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 1.0, 0.2)

    st.divider()

    # 附件管理区
    st.subheader("📁 本对话附件")
    new_files = st.file_uploader(
        "Upload", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True, 
        key="sidebar_up", label_visibility="collapsed"
    )
    
    if new_files and not current_session["files_meta"]:
        client_tmp = genai.Client(api_key=API_KEY) if API_KEY else None
        if client_tmp:
            current_session["files_meta"] = safe_upload_handler(client_tmp, new_files)
            current_session["files_processed"] = False
            save_all_sessions() # 保存文件引用到本地
            st.rerun()

    if current_session["files_meta"]:
        with st.container(border=True):
            for f in current_session["files_meta"]:
                st.markdown(f"📎 `{f['display_name']}`")
            if st.button("🗑️ 清空附件", use_container_width=True):
                current_session["files_meta"] = []; current_session["files_processed"] = False
                save_all_sessions(); st.rerun()
    else:
        st.caption("暂无附件")

    st.divider()

    # 会话管理
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1: st.caption("💬 历史会话")
    with col_h2:
        if st.button("➕"):
            nid = str(uuid.uuid4())
            st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files_meta": [], "files_processed": False}
            st.session_state.current_session_id = nid
            save_all_sessions(); st.rerun()

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
                if new_n != sess["title"]: 
                    sess["title"] = new_n; save_all_sessions(); st.rerun()
                if st.button("🗑️", key=f"d_{sid}"):
                    if len(st.session_state.all_sessions) > 1:
                        del st.session_state.all_sessions[sid]; save_all_sessions(); st.rerun()

# ================= 4. 主界面对话区 =================

client = genai.Client(api_key=API_KEY) if API_KEY else None

if client:
    # 渲染历史
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            st.markdown(m["content"])

    # 底部输入框
    chat_prompt = st.chat_input("询问任何问题...")

    if chat_prompt:
        user_parts = []
        # 如果有附件且没发过，在第一句注入
        if current_session["files_meta"] and not current_session["files_processed"]:
            for f in current_session["files_meta"]:
                user_parts.append({"file_uri": f["uri"], "mime_type": f["mime_type"]})
            user_parts.append({"text": f"[系统通知：已挂载附件] 用户已提供 {len(current_session['files_meta'])} 份文档。请基于此分析。"})
            current_session["files_processed"] = True
        
        user_parts.append({"text": chat_prompt})
        # 存入历史（简化存文本）
        current_session["history"].append({"role": "user", "content": chat_prompt, "full_parts": user_parts})
        save_all_sessions(); st.rerun()

    # 回复逻辑
    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty()
            with st.spinner("思考中..."):
                full_text = ""
                try:
                    # 构造历史对象
                    history_objs = []
                    for h in current_session["history"][:-1]:
                        # 如果该条历史包含多模态零件
                        if "full_parts" in h:
                            p_objs = []
                            for p in h["full_parts"]:
                                if "text" in p: p_objs.append(types.Part(text=p["text"]))
                                elif "file_uri" in p: p_objs.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))
                            history_objs.append(types.Content(role=h["role"], parts=p_objs))
                        else:
                            history_objs.append(types.Content(role=h["role"], parts=[types.Part(text=h["content"])]))

                    # 构造当前 Payload
                    last_msg = current_session["history"][-1]
                    current_payload = []
                    for p in last_msg.get("full_parts", [{"text": last_msg["content"]}]):
                        if "text" in p: current_payload.append(types.Part(text=p["text"]))
                        elif "file_uri" in p: current_payload.append(types.Part.from_uri(file_uri=p["file_uri"], mime_type=p["mime_type"]))

                    # 智能动态系统指令
                    if current_session["files_meta"]:
                        sys_inst = "你是一个文档分析专家。请仔细阅读附件内容，如果用户的问题与附件相关，请优先从附件中寻找答案。回答务必精准。"
                    else:
                        sys_inst = "你是一个得力的智能助手。请友好且高效地回答用户的问题。"

                    chat_session = client.chats.create(
                        model=selected_model,
                        history=history_objs,
                        config=types.GenerateContentConfig(
                            system_instruction=sys_inst,
                            temperature=temperature,
                            tools=[types.Tool(google_search=types.GoogleSearch())]
                        )
                    )
                    
                    response_stream = chat_session.send_message_stream(message=current_payload)
                    for chunk in response_stream:
                        # 核心修复点：增加安全检查，防止 NoneType 报错
                        if chunk and hasattr(chunk, 'text') and chunk.text:
                            full_text += chunk.text
                            box.markdown(full_text + "▌")
                    
                    box.markdown(full_text)
                    current_session["history"].append({"role": "model", "content": full_text})
                    
                    # 自动命名
                    if len(current_session["history"]) == 2:
                        current_session["title"] = chat_prompt[:10]
                    
                    save_all_sessions(); st.rerun()

                except Exception as e:
                    # 捕捉详细错误，不只是 NoneType
                    st.error(f"对话异常: {str(e)}")
else:
    st.warning("👈 请在 Secrets 中配置 API Key")
