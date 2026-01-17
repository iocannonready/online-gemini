import streamlit as st
import os
import time
import shutil
import uuid
# 核心：使用 2026 官方最新 SDK
from google import genai
from google.genai import types

# ================= 0. 版本元数据 =================
APP_VERSION = "v4.0.9-PRO"
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

# 初始化 Session State (关键：统一使用字典格式，防止 AttributeError)
if "all_sessions" not in st.session_state:
    default_id = str(uuid.uuid4())
    st.session_state.all_sessions = {
        default_id: {
            "title": "新对话", 
            "history": [], # 存储结构：{"role": "user" 或 "model", "content": str}
            "files": [],   # 存储已上传的 File 引用
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
    st.status(f"版本: {APP_VERSION}", state="complete")
    
    with st.expander("⚙️ 模型配置", expanded=True):
        model_list = [
            "gemini-2.0-flash",           # 推荐
            "gemini-2.5-flash",           
            "gemini-3-flash-preview",     
            "gemini-1.5-flash",           
        ]
        selected_model = st.selectbox("选择模型", model_list, index=0)
        temperature = st.slider("创造力", 0.0, 2.0, 0.1) 
        enable_search = st.toggle("🌍 开启联网搜索", value=True)

    st.divider()
    if st.button("➕ 新建对话", use_container_width=True):
        nid = str(uuid.uuid4())
        st.session_state.all_sessions[nid] = {"title": "新对话", "history": [], "files": [], "processed": False}
        st.session_state.current_session_id = nid; st.rerun()

    # 会话列表渲染
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

    st.markdown(f"<div style='position: fixed; bottom: 10px; font-size: 11px; color: gray;'>{APP_VERSION} | SDK: {genai.__version__}</div>", unsafe_allow_html=True)

# ================= 3. 核心功能函数 =================

def get_client():
    if not API_KEY:
        st.error("❌ 尚未配置 API KEY")
        return None
    return genai.Client(api_key=API_KEY)

def upload_handler_v9(client, files):
    temp_dir = "cloud_tmp"
    shutil.rmtree(temp_dir, ignore_errors=True); os.makedirs(temp_dir)
    uploaded_refs = []
    file_names = [f.name for f in files]
    
    with st.status("🚀 正在激活视觉处理通道...", expanded=True) as status:
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
                uploaded_refs.append(r)
                st.write(f"✅ 已载入: {os.path.basename(path)}")
            except Exception as e: st.error(f"上传出错: {e}")
        
        while True:
            ready = True
            for r in uploaded_refs:
                if client.files.get(name=r.name).state.name == "PROCESSING":
                    ready = False; break
            if ready: break
            time.sleep(2)
        status.update(label="✅ 视觉权限激活成功", state="complete", expanded=False)
    
    # 存入字典格式的历史记录
    hint = f"📎 **[系统：多模态附件已就绪]**\n\n已成功识别 {len(file_names)} 个文件。请基于这些文件回答后续提问。"
    current_session["history"].append({"role": "model", "content": hint})
    shutil.rmtree(temp_dir, ignore_errors=True)
    return uploaded_refs

# ================= 4. 主对话逻辑 =================

client = get_client()
if client:
    # 1. 渲染历史 (使用字典访问方式，防止 AttributeError)
    for m in current_session["history"]:
        with st.chat_message("assistant" if m["role"] == "model" else "user"):
            st.markdown(m["content"])

    # 2. 底部控制区
    chat_prompt = None
    with st.container():
        if current_session["files"]:
            st.info(f"📂 附件就绪：{len(current_session['files'])} 个文件。AI 准备进行深度识图。")
            if st.button("🗑️ 卸载附件"):
                current_session["files"] = []; current_session["processed"] = False; st.rerun()

        up_fs = st.file_uploader("拖拽或浏览文件 (支持 20+ 图片/PDF)", accept_multiple_files=True, key="v9_up", label_visibility="collapsed")
        
        if up_fs and not current_session["files"]:
            if st.button("🚀 确认上传并开始分析", use_container_width=True, type="primary"):
                current_session["files"] = upload_handler_v9(client, up_fs)
                current_session["processed"] = False; st.rerun()

        chat_prompt = st.chat_input("请对附件提问，或直接输入指令...")

    # 3. 发送逻辑
    if chat_prompt:
        current_session["history"].append({"role": "user", "content": chat_prompt}); st.rerun()

    if current_session["history"] and current_session["history"][-1]["role"] == "user":
        with st.chat_message("assistant"):
            box = st.empty(); full_text = ""
            
            # 构造 Payload
            payload_parts = []
            if current_session["files"] and not current_session["processed"]:
                payload_parts.append(types.Part(text="[Vision Active] Please analyze the attached documents/images as the primary context for the following question."))
                for f_ref in current_session["files"]:
                    payload_parts.append(types.Part.from_uri(file_uri=f_ref.uri, mime_type=f_ref.mime_type))
            
            payload_parts.append(types.Part(text=current_session["history"][-1]["content"]))

            try:
                # 转换字典历史为 API 对象
                history_objs = []
                for h in current_session["history"][:-1]:
                    history_objs.append(types.Content(
                        role=h["role"],
                        parts=[types.Part(text=h["content"])]
                    ))

                tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else []

                # 创建 Chat
                chat_session = client.chats.create(
                    model=selected_model,
                    history=history_objs,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个拥有视觉能力的文档专家。请优先根据用户上传的附件（图片或PDF）进行回答。严禁回答'我看不到文件'。",
                        temperature=temperature,
                        tools=tools
                    )
                )
                
                # 发送流式
                response = chat_session.send_message_stream(message=payload_parts)
                for chunk in response:
                    if chunk.text:
                        full_text += chunk.text; box.markdown(full_text + "▌")
                
                box.markdown(full_text)
                
                # 成功后标记与存储
                current_session["processed"] = True 
                current_session["history"].append({"role": "model", "content": full_text})
                
                if len(current_session["history"]) <= 3:
                    current_session["title"] = chat_prompt[:10]
                st.rerun()

            except Exception as e:
                st.error(f"对话异常: {e}")
